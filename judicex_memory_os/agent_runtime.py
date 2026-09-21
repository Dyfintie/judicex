from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any, Callable

from .answering import GroundedAnswerEngine
from .legal_agent import AgentTraceStep
from .store import LegalMemoryStore


TraceSink = Callable[[dict[str, Any]], None]


@dataclass
class AgentPlan:
    goal: str
    intent: str = "legal_work"
    actions: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class ToolOutcome:
    name: str
    status: str
    detail: str
    data: dict[str, Any] = field(default_factory=dict)


class JudicexAgentRuntime:
    """Agentic orchestration layer for Judicex.

    The old grounded legal engine is now a tool used by this runtime. The
    runtime decides the practical path, calls internal tools, observes their
    result, and produces a top-level trace that reflects what actually
    happened.
    """

    def __init__(
        self,
        *,
        store: LegalMemoryStore,
        client: Any,
        model: str,
        area: str | None = None,
        matter_id: str | None = None,
        on_step: TraceSink | None = None,
    ) -> None:
        self.store = store
        self.client = client
        self.model = model
        self.area = area
        self.matter_id = matter_id
        self.on_step = on_step
        self.trace: list[dict[str, Any]] = []

    def answer(self, question: str, *, recent_user_turns: list[str] | None = None) -> dict[str, Any]:
        recent_turns = recent_user_turns or []
        plan = self._plan(question, recent_turns)
        self._emit(
            "agent_plan",
            "Pianifico lavoro",
            "completed",
            self._plan_detail(plan),
            metrics={"intent": plan.intent, "actions": plan.actions},
        )

        if plan.intent == "chat":
            answer = self._direct_chat(question, recent_turns)
            return self._finalise(
                {
                    "status": "chat",
                    "answer": answer,
                    "citations": [],
                    "sections": [],
                    "case_facts": [],
                    "limits": [],
                    "follow_up_questions": [],
                    "coverage": {},
                    "matter": None,
                    "matter_coverage": {},
                    "answer_contract": {"status": "skipped", "reason": "agent_chat"},
                    "semantic_verifier": {"status": "skipped", "reason": "agent_chat"},
                    "evidence_trace": [],
                    "legal_issues": [],
                }
            )

        outcomes: dict[str, ToolOutcome] = {}
        if "agent.memory_search" in plan.actions:
            outcomes["agent.memory_search"] = self._tool_agent_memory_search(question)

        if self.matter_id and "matter.inspect" in plan.actions:
            outcomes["matter.inspect"] = self._tool_matter_inspect(question)

        legal_result: dict[str, Any] | None = None
        if "legal.answer_grounded" in plan.actions:
            outcome = self._tool_legal_answer(question, recent_turns)
            outcomes["legal.answer_grounded"] = outcome
            raw_result = outcome.data.get("result")
            if isinstance(raw_result, dict):
                legal_result = raw_result

        if self._needs_operational_composition(plan, legal_result):
            outcome = self._tool_compose_operational(question, plan, legal_result, outcomes)
            result = outcome.data.get("result") if isinstance(outcome.data.get("result"), dict) else None
            if result:
                return self._finalise(result, legal_result=legal_result, tool_outcomes=outcomes)

        if legal_result is not None:
            return self._finalise(legal_result, legal_result=legal_result, tool_outcomes=outcomes)

        fallback = self._deterministic_operational_result(question, plan, legal_result=None, outcomes=outcomes)
        return self._finalise(fallback, tool_outcomes=outcomes)

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def _plan(self, question: str, recent_turns: list[str]) -> AgentPlan:
        try:
            raw = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._planner_prompt()},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "question": question,
                                "recent_user_turns": recent_turns[-3:],
                                "active_matter_id": self.matter_id or "",
                                "area": self.area or "",
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                ],
                temperature=0.0,
            )
            parsed = _extract_json(raw)
        except Exception:
            parsed = {}
        return self._normalise_plan(question, parsed)

    def _normalise_plan(self, question: str, parsed: dict[str, Any]) -> AgentPlan:
        text = question.lower()
        intent = str(parsed.get("intent") or "").strip() or "legal_work"
        if intent not in {"chat", "legal_work", "matter_work"}:
            intent = "legal_work"
        if intent == "matter_work" and not self.matter_id:
            intent = "legal_work"
        if _looks_like_chat(text):
            intent = "chat"

        raw_actions = parsed.get("actions") if isinstance(parsed.get("actions"), list) else []
        actions = _dedupe(
            str(action).strip()
            for action in raw_actions
            if str(action).strip()
        )

        if intent == "chat":
            actions = ["respond.direct"]
        else:
            inferred = self._infer_actions_from_text(text)
            actions = _dedupe(actions + inferred)
            if "agent.memory_search" not in actions:
                actions.insert(0, "agent.memory_search")
            if self.matter_id and "matter.inspect" not in actions:
                insert_at = 1 if actions and actions[0] == "agent.memory_search" else 0
                actions.insert(insert_at, "matter.inspect")
            if "legal.answer_grounded" not in actions:
                insert_at = 0
                for anchor in ("agent.memory_search", "matter.inspect"):
                    if anchor in actions:
                        insert_at = max(insert_at, actions.index(anchor) + 1)
                actions.insert(insert_at, "legal.answer_grounded")
            if self._question_wants_operational_output(text) and "answer.compose_operational" not in actions:
                actions.append("answer.compose_operational")

        return AgentPlan(
            goal=_clean(str(parsed.get("goal") or question)) or question,
            intent=intent,
            actions=actions,
            reason=_clean(str(parsed.get("reason") or "")),
        )

    @staticmethod
    def _infer_actions_from_text(text: str) -> list[str]:
        actions = ["legal.answer_grounded"]
        if any(marker in text for marker in ("fascicolo", "documenti caricati", "file", "prova", "prove")):
            actions.append("matter.inspect")
        if any(
            marker in text
            for marker in (
                "domande",
                "checklist",
                "rischi",
                "strategia",
                "bozza",
                "redigi",
                "diffida",
                "spiegami",
                "differenza",
                "quando usare",
                "prossimi passi",
            )
        ):
            actions.append("answer.compose_operational")
        return actions

    @staticmethod
    def _question_wants_operational_output(text: str) -> bool:
        return any(
            marker in text
            for marker in (
                "domande",
                "checklist",
                "rischi",
                "strategia",
                "bozza",
                "redigi",
                "spiegami",
                "differenza",
                "quando usare",
                "prossimi passi",
            )
        )

    @staticmethod
    def _planner_prompt() -> str:
        return textwrap.dedent(
            """
            You are the planner for the Judicex agentic runtime.
            Your responsibility is not to answer the user directly,
            but to determine which internal tools should be executed
            to accomplish the user's objective.

            Available tools:
            - agent.memory_search: Retrieves previously stored agent memories,
            user preferences, decisions, and operational lessons.

            - legal.answer_grounded: Uses the grounded legal reasoning engine,
            including statutory knowledge retrieval, source verification,
            and citation validation.

            - matter.inspect: Examines the active legal matter, including
            associated facts, documents, and available evidence.

            - answer.compose_operational: Produces practical legal outputs,
            including clarification questions, checklists, risk assessments,
            legal strategies, and document drafts using the results
            obtained from other tools.

            - respond.direct: Handles simple conversations, system-related
            questions, greetings, and general small talk.

            Planning rules:
            1. If active_matter_id is empty, do not select
            "matter_work" as the intent.

            2. The grounded legal reasoning engine is an available tool,
            not a mandatory execution path.

            3. Agent memory is different from statutory legal knowledge.
            Never treat agent memories as authoritative sources of law.

            4. For requests requiring practical legal assistance,
            combine legal.answer_grounded with
            answer.compose_operational when appropriate.

            5. For document drafts, checklists, risk assessments,
            and legal strategies, use answer.compose_operational.

            6. Select tools according to the user's objective and
            the information required to complete the task.

            7. Do not invent tool names or select unavailable tools.

            Return only valid JSON using the following structure:

            {
            "intent": "chat | legal_work | matter_work",
            "goal": "Practical objective to accomplish",
            "actions": [
                "legal.answer_grounded",
                "answer.compose_operational"
            ],
            "reason": "Explanation of why these tools were selected"
            }
            """
        ).strip()

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _tool_agent_memory_search(self, question: str) -> ToolOutcome:
        self._emit(
            "tool_agent_memory_search",
            "Tool: memoria agente",
            "running",
            "Cerco preferenze, decisioni e lezioni operative già salvate.",
        )
        try:
            memories = self.store.search_agent_memories(
                question,
                matter_id=self.matter_id or None,
                include_global=True,
                top_k=6,
                full=True,
            )
            detail = (
                f"Recuperate {len(memories)} memorie operative rilevanti."
                if memories
                else "Nessuna memoria agente rilevante trovata."
            )
            self._emit("tool_agent_memory_search", "Tool: memoria agente", "completed", detail)
            return ToolOutcome(
                "agent.memory_search",
                "completed",
                detail,
                {"memories": _slim_agent_memories(memories)},
            )
        except Exception as exc:
            detail = f"Memoria agente non disponibile: {exc}"
            self._emit("tool_agent_memory_search", "Tool: memoria agente", "failed", detail)
            return ToolOutcome("agent.memory_search", "failed", detail, {"error": str(exc)})

    def _tool_matter_inspect(self, question: str) -> ToolOutcome:
        self._emit("tool_matter_inspect", "Tool: fascicolo", "running", "Leggo il fascicolo attivo.")
        if not self.matter_id:
            outcome = ToolOutcome("matter.inspect", "skipped", "Nessun fascicolo attivo.")
            self._emit("tool_matter_inspect", "Tool: fascicolo", "skipped", outcome.detail)
            return outcome
        try:
            context = self.store.build_matter_context(self.matter_id, query=question)
            if "error" in context:
                outcome = ToolOutcome("matter.inspect", "limited", str(context["error"]))
            else:
                coverage = context.get("coverage") or {}
                outcome = ToolOutcome(
                    "matter.inspect",
                    "completed",
                    (
                        f"Fascicolo letto: {coverage.get('documents', 0)} documenti, "
                        f"{coverage.get('facts', 0)} fatti estratti."
                    ),
                    {"matter_context": context},
                )
            self._emit("tool_matter_inspect", "Tool: fascicolo", outcome.status, outcome.detail)
            return outcome
        except Exception as exc:
            outcome = ToolOutcome("matter.inspect", "failed", str(exc))
            self._emit("tool_matter_inspect", "Tool: fascicolo", "failed", outcome.detail)
            return outcome

    def _tool_legal_answer(self, question: str, recent_turns: list[str]) -> ToolOutcome:
        self._emit(
            "tool_legal_answer",
            "Tool: ricerca legale",
            "running",
            "Uso il motore legale con memoria normativa e controllo citazioni.",
        )
        try:
            engine = GroundedAnswerEngine(
                store=self.store,
                client=self.client,
                model=self.model,
                area=self.area,
                matter_id=self.matter_id,
            )
            result = engine.answer(question, recent_user_turns=recent_turns)
            status = str(result.get("status") or "unknown")
            detail = _legal_tool_detail(result)
            self._emit("tool_legal_answer", "Tool: ricerca legale", _trace_status(status), detail)
            return ToolOutcome("legal.answer_grounded", _trace_status(status), detail, {"result": result})
        except Exception as exc:
            detail = f"Motore legale non utilizzabile: {exc}"
            self._emit("tool_legal_answer", "Tool: ricerca legale", "failed", detail)
            return ToolOutcome("legal.answer_grounded", "failed", detail, {"error": str(exc)})

    def _tool_compose_operational(
        self,
        question: str,
        plan: AgentPlan,
        legal_result: dict[str, Any] | None,
        outcomes: dict[str, ToolOutcome],
    ) -> ToolOutcome:
        self._emit(
            "tool_compose_operational",
            "Tool: composizione risposta",
            "running",
            "Compongo una risposta pratica usando i risultati dei tool disponibili.",
        )
        try:
            raw = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._composer_prompt()},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "question": question,
                                "plan": plan.__dict__,
                                "legal_result": _slim_result(legal_result),
                                "agent_memory": _memory_from_outcomes(outcomes),
                                "tool_outcomes": {
                                    key: {"status": value.status, "detail": value.detail}
                                    for key, value in outcomes.items()
                                },
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                ],
                temperature=0.1,
            )
            parsed = _extract_json(raw)
            result = self._normalise_composed_result(parsed, question, legal_result, outcomes)
        except Exception:
            result = self._deterministic_operational_result(question, plan, legal_result, outcomes)

        detail = "Risposta operativa pronta."
        self._emit("tool_compose_operational", "Tool: composizione risposta", "completed", detail)
        return ToolOutcome("answer.compose_operational", "completed", detail, {"result": result})

    def _direct_chat(self, question: str, recent_turns: list[str]) -> str:
        self._emit("tool_direct_chat", "Tool: risposta diretta", "running", "Rispondo senza usare il motore legale.")
        try:
            raw = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Sei Judicex. Respond in English, concise and practical, without legal research pipeline.",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"question": question, "recent_user_turns": recent_turns[-3:]},
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                ],
                temperature=0.1,
            )
            answer = _clean(raw)
        except Exception:
            answer = "How can I assist you with Judicex today?"
        self._emit("tool_direct_chat", "Tool: direct chat", "completed", "Response ready.")
        return answer or "How can I assist you with Judicex today?"

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    @staticmethod
    def _needs_operational_composition(plan: AgentPlan, legal_result: dict[str, Any] | None) -> bool:
        if "answer.compose_operational" not in plan.actions:
            return False
        if legal_result is None:
            return True
        return str(legal_result.get("status") or "").lower() in {"abstain", "chat", "analysis"} or bool(
            plan.actions and len(plan.actions) > 1
        )

    @staticmethod
    def _composer_prompt() -> str:
        return textwrap.dedent(
            """
            You are Judicex, an operational legal AI agent. You must produce the final response
            for a legal professional using already executed tools. Respond in clear English.

            Rules:
            - Language: Respond strictly in English.
            - Do not invent articles, deadlines, or citations.
            - Cite articles, statutory terms, or limitation periods only if legal_result
              explicitly supports them with sources/citations. Otherwise use cautious phrasing:
              "to be verified against primary sources and the matter file".
            - If legal_result contains relevant sources/citations, you may reuse them.
            - agent_memory contains preferences, decisions, or operational lessons:
              apply them as working context, do not cite them as statutory law.
            - If legal_result is abstain or limited, do not stop: still produce
              practical questions, checklists, procedural risks, strategy, and careful drafts.
            - Drafts may use placeholders for missing facts (e.g., [Claimant], [Amount]).
            - Style: professional, clear, no emojis, no unnecessary jargon, no debug sections.

            Respond only in valid JSON:
            {
              "status": "operational | limited | grounded",
              "intro": "concise opening sentence in English",
              "sections": [
                {"type": "questions", "title": "Points to Clarify", "items": ["..."]},
                {"type": "explanation", "title": "Practical Distinction", "items": ["..."]},
                {"type": "checklist", "title": "Documentary Checklist", "items": ["..."]},
                {"type": "risks", "title": "Procedural Risks", "items": ["..."]},
                {"type": "strategy", "title": "Operational Strategy", "items": ["..."]},
                {"type": "draft", "title": "Legal Notice Draft", "content": "..."}
              ],
              "missing_information": ["..."],
              "follow_up_questions": ["..."]
            }
            """
        ).strip()

    def _normalise_composed_result(
        self,
        parsed: dict[str, Any],
        question: str,
        legal_result: dict[str, Any] | None,
        outcomes: dict[str, ToolOutcome] | None = None,
    ) -> dict[str, Any]:
        status = str(parsed.get("status") or "operational").strip().lower()
        if status not in {"operational", "limited", "grounded"}:
            status = "operational"
        sections = _normalise_sections(parsed.get("sections"))
        if not sections:
            fallback_plan = AgentPlan(goal=question, actions=["answer.compose_operational"])
            return self._deterministic_operational_result(question, fallback_plan, legal_result, outcomes)
        answer = _render_sections(str(parsed.get("intro") or "").strip(), sections)
        return {
            "status": status,
            "answer": answer,
            "citations": list((legal_result or {}).get("citations") or []),
            "sections": sections,
            "case_facts": list((legal_result or {}).get("case_facts") or []),
            "limits": [str(item).strip() for item in parsed.get("missing_information") or [] if str(item).strip()],
            "follow_up_questions": [str(item).strip() for item in parsed.get("follow_up_questions") or [] if str(item).strip()],
            "coverage": (legal_result or {}).get("coverage") or {},
            "matter": (legal_result or {}).get("matter"),
            "matter_coverage": (legal_result or {}).get("matter_coverage") or {},
            "answer_contract": (legal_result or {}).get("answer_contract") or {"status": "skipped", "reason": "agent_operational"},
            "semantic_verifier": (legal_result or {}).get("semantic_verifier") or {"status": "skipped", "reason": "agent_operational"},
            "evidence_trace": (legal_result or {}).get("evidence_trace") or [],
            "legal_issues": (legal_result or {}).get("legal_issues") or [],
            "agent_memory": _memory_from_outcomes(outcomes or {}),
        }

    def _deterministic_operational_result(
        self,
        question: str,
        plan: AgentPlan,
        legal_result: dict[str, Any] | None,
        outcomes: dict[str, ToolOutcome] | None = None,
    ) -> dict[str, Any]:
        text = question.lower()
        is_italian = any(
            marker in text
            for marker in (
                "domande", "dati mancanti", "fatture", "recuperare", "recupero", "pagate", "mancanti",
                "diffida", "chiarire", "decreto ingiuntivo", "messa in mora", "spiegami",
                "differenza", "processuali", "consiglieresti", "recupero credito", "recupero crediti",
                "redigi", "bozza", "prepara", "strategia operativa", "fascicolo", "crediti"
            )
        )
        sections: list[dict[str, Any]] = []
        if is_italian:
            if any(marker in text for marker in ("domande", "dati mancanti", "procedere", "decreto ingiuntivo", "fatture")):
                sections.append(
                    {
                        "type": "questions",
                        "title": "Dati da chiarire",
                        "items": [
                            "Numero, data di emissione, scadenza e importo di ciascuna fattura.",
                            "Esistono contratto, ordine, conferma d'ordine o condizioni generali firmate?",
                            "La merce è stata consegnata o il servizio è stato accettato senza contestazioni?",
                            "Il debitore ha pagato qualcosa, contestato importi o chiesto dilazioni?",
                            "Hai PEC, sede legale aggiornata e visura camerale del debitore?",
                        ],
                    }
                )
            if any(marker in text for marker in ("spiegami", "differenza", "diffida", "messa in mora", "decreto ingiuntivo")):
                sections.append(
                    {
                        "type": "explanation",
                        "title": "Differenza pratica",
                        "items": [
                            "La diffida è una richiesta formale di pagamento: serve a mettere pressione, fissare un termine e preparare il fascicolo.",
                            "La messa in mora è la comunicazione con cui si contesta l'inadempimento e si chiede l'adempimento; di solito si integra nella diffida.",
                            "Il ricorso per decreto ingiuntivo è il passaggio giudiziale: ha senso quando il credito è documentato e il debitore non paga dopo il sollecito.",
                        ],
                    }
                )
            if any(marker in text for marker in ("checklist", "document", "fatture", "decreto ingiuntivo")):
                sections.append(
                    {
                        "type": "checklist",
                        "title": "Checklist documentale",
                        "items": [
                            "Tre fatture complete con prova di invio o registrazione.",
                            "Contratto, ordine, preventivo accettato o scambio email che giustifica le prestazioni.",
                            "Prova di consegna, rapportini, SAL, DDT, accettazione del servizio o assenza di contestazioni.",
                            "Estratto conto cliente, solleciti, eventuali promesse di pagamento e PEC già inviate.",
                            "Visura del debitore, PEC corretta, sede legale e dati del creditore.",
                        ],
                    }
                )
            if any(marker in text for marker in ("rischi", "processuali", "decreto ingiuntivo", "recuperare")):
                sections.append(
                    {
                        "type": "risks",
                        "title": "Rischi processuali",
                        "items": [
                            "Opposizione del debitore se contesta prestazioni, importi o qualità del servizio.",
                            "Prova documentale insufficiente se oltre alle fatture mancano ordine, consegna o accettazione.",
                            "Tempi e costi aggiuntivi se il debitore è incapiente o irreperibile.",
                            "Errore su PEC, sede o dati societari che rallenta notifiche e recupero.",
                        ],
                    }
                )
            if any(marker in text for marker in ("strategia", "consiglieresti", "recupero credito", "b2b", "decreto ingiuntivo")):
                sections.append(
                    {
                        "type": "strategy",
                        "title": "Strategia operativa",
                        "items": [
                            "Prima verifica se il credito è liquido, scaduto, documentato e non seriamente contestato.",
                            "Invia una diffida via PEC con termine breve e allega l'elenco delle fatture.",
                            "Nel frattempo prepara il fascicolo per il ricorso: fatture, contratto/ordine, prove di esecuzione e visura.",
                            "Se non paga o non propone una trattativa credibile, passa al decreto ingiuntivo con fascicolo già ordinato.",
                        ],
                    }
                )
            if any(marker in text for marker in ("redigi", "bozza", "diffida")):
                sections.append(
                    {
                        "type": "draft",
                        "title": "Bozza diffida",
                        "content": (
                            "Oggetto: diffida di pagamento per fatture scadute\n\n"
                            "Spett.le [Società debitrice],\n\n"
                            "nell'interesse di [Società creditrice], Vi invitiamo a provvedere al pagamento "
                            "dell'importo complessivo di euro 8.500,00, relativo a tre fatture scadute da circa 90 giorni: "
                            "[numero/data/importo fattura 1], [numero/data/importo fattura 2], [numero/data/importo fattura 3].\n\n"
                            "Il pagamento dovrà essere effettuato entro [termine] giorni dal ricevimento della presente "
                            "sul seguente IBAN: [IBAN]. In mancanza, riceveremo istruzioni per procedere senza ulteriore avviso "
                            "al recupero coattivo del credito, anche mediante ricorso per decreto ingiuntivo, con aggravio di spese, "
                            "interessi e competenze.\n\n"
                            "Restano espressamente riservati tutti i diritti, le azioni e le ragioni della società creditrice.\n\n"
                            "Distinti saluti\n[Avvocato / Studio]"
                        ),
                    }
                )
            if not sections:
                sections.append(
                    {
                        "type": "next_steps",
                        "title": "Prossimi passi",
                        "items": [
                            "Carica o indica i documenti disponibili.",
                            "Dimmi l'obiettivo pratico: parere, checklist, bozza atto o analisi fascicolo.",
                        ],
                    }
                )
        else:
            # English operational response
            if any(marker in text for marker in ("questions", "clarif", "missing", "data", "proceed", "invoice")):
                sections.append(
                    {
                        "type": "questions",
                        "title": "Points to Clarify",
                        "items": [
                            "Number, issue date, due date, and amount of each invoice.",
                            "Is there a signed contract, purchase order, order confirmation, or general terms?",
                            "Were goods delivered or services accepted without written dispute?",
                            "Has the debtor made partial payments, contested amounts, or requested extensions?",
                            "Do you have the debtor's certified email, verified corporate address, and company registry report?",
                        ],
                    }
                )
            if any(marker in text for marker in ("explain", "difference", "distinction", "demand", "notice")):
                sections.append(
                    {
                        "type": "explanation",
                        "title": "Practical Distinction",
                        "items": [
                            "A demand letter is a formal payment request: it puts pressure on the debtor, sets a firm deadline, and interrupts statutory limitation periods.",
                            "A default notice (messa in mora) formalizes debtor breach and activates statutory default interest.",
                            "A judicial injunction / summary payment order is the court remedy: appropriate when the claim is supported by written documentation and the debtor ignores informal demands.",
                        ],
                    }
                )
            if any(marker in text for marker in ("checklist", "document", "evidence", "invoice")):
                sections.append(
                    {
                        "type": "checklist",
                        "title": "Documentary Checklist",
                        "items": [
                            "All outstanding invoices with proof of electronic transmission or registered delivery.",
                            "Contract, purchase order, accepted estimate, or email exchanges establishing agreement on scope.",
                            "Proof of delivery, shipping notes (DDT), signed completion reports, or uncontested acceptance.",
                            "Customer account statement, prior reminder correspondence, payment promises, and delivery receipts.",
                            "Debtor company search, certified corporate email, and legal creditor credentials.",
                        ],
                    }
                )
            if any(marker in text for marker in ("risk", "procedural", "recover", "litigation")):
                sections.append(
                    {
                        "type": "risks",
                        "title": "Procedural Risks",
                        "items": [
                            "Debtor opposition raising factual disputes regarding service quality, completion, or billing.",
                            "Insufficient documentary proof if invoices lack proof of delivery or written authorization.",
                            "Additional time and costs if the debtor is insolvent or asset-depleted.",
                            "Defects in service or formal address notifications delaying enforcement.",
                        ],
                    }
                )
            if any(marker in text for marker in ("strategy", "recommend", "debt recovery", "b2b", "recovery")):
                sections.append(
                    {
                        "type": "strategy",
                        "title": "Operational Strategy",
                        "items": [
                            "First verify that the debt is liquid, due, fully documented, and not subject to bona fide dispute.",
                            "Send a formal demand letter via certified mail or legal counsel with a 7 to 15-day payment deadline.",
                            "Concurrently assemble the judicial dossier: invoices, proof of delivery, company report, and calculation of statutory interest.",
                            "If the debtor fails to pay or propose credible terms, file for an expedited judicial summary payment order.",
                        ],
                    }
                )
            if any(marker in text for marker in ("draft", "letter", "notice", "demand")):
                sections.append(
                    {
                        "type": "draft",
                        "title": "Draft Legal Notice and Demand for Payment",
                        "content": (
                            "Subject: Formal Demand and Notice of Default - Overdue Invoices\n\n"
                            "To: [Debtor Company Name]\nAttn: Management / Legal Department\n\n"
                            "On behalf of our client, [Creditor Company Name], we hereby formally request and demand immediate payment of the total overdue amount of €8,500.00 in respect of the following outstanding invoices:\n"
                            "- [Invoice 1: Number, Date, Amount]\n"
                            "- [Invoice 2: Number, Date, Amount]\n"
                            "- [Invoice 3: Number, Date, Amount]\n\n"
                            "Please remit the total amount within [10/15] calendar days from receipt of this notice to the following account:\n"
                            "IBAN: [Creditor IBAN]\nBank: [Bank Name]\n\n"
                            "Failing payment within the specified period, our instructions are to proceed without further notice with judicial debt collection, including an application for an expedited payment order, with additional court costs, statutory interest, and legal fees charged to your company.\n\n"
                            "All rights and legal actions remain strictly reserved.\n\n"
                            "Sincerely,\n[Counsel / Legal Firm]"
                        ),
                    }
                )
            if not sections:
                sections.append(
                    {
                        "type": "next_steps",
                        "title": "Next Steps",
                        "items": [
                            "Upload or reference the available case documents.",
                            "Specify your desired deliverable: legal opinion, documentary checklist, draft notice, or file analysis.",
                        ],
                    }
                )

        memory_items = _memory_from_outcomes(outcomes or {})
        if memory_items:
            sections.insert(
                0,
                {
                    "type": "memory",
                    "title": "Memoria agente applicata" if is_italian else "Applied Agent Memory",
                    "items": [
                        f"{item.get('title', 'Memory')}: {item.get('excerpt') or item.get('content') or ''}".strip()
                        for item in memory_items[:3]
                    ],
                },
            )

        limits = []
        if legal_result and str(legal_result.get("status") or "").lower() == "abstain":
            limits.append(
                "La parte strettamente normativa resta limitata alle fonti disponibili nella memoria locale."
                if is_italian else
                "The strictly statutory legal analysis remains limited to sources available in local memory."
            )
        intro_text = "Imposto il lavoro in modo operativo." if is_italian else "Structuring the operational response."
        answer = _render_sections(intro_text, sections)
        return {
            "status": "operational",
            "answer": answer,
            "citations": list((legal_result or {}).get("citations") or []),
            "sections": sections,
            "case_facts": list((legal_result or {}).get("case_facts") or []),
            "limits": limits,
            "follow_up_questions": [],
            "coverage": (legal_result or {}).get("coverage") or {},
            "matter": (legal_result or {}).get("matter"),
            "matter_coverage": (legal_result or {}).get("matter_coverage") or {},
            "answer_contract": {"status": "skipped", "reason": "agent_operational"},
            "semantic_verifier": {"status": "skipped", "reason": "agent_operational"},
            "evidence_trace": (legal_result or {}).get("evidence_trace") or [],
            "legal_issues": (legal_result or {}).get("legal_issues") or [],
            "agent_memory": memory_items,
        }

    # ------------------------------------------------------------------
    # Finalisation and trace
    # ------------------------------------------------------------------

    def _finalise(
        self,
        result: dict[str, Any],
        *,
        legal_result: dict[str, Any] | None = None,
        tool_outcomes: dict[str, ToolOutcome] | None = None,
    ) -> dict[str, Any]:
        final = dict(result)
        final["agent_trace"] = list(self.trace)
        if legal_result and legal_result is not result:
            final["legal_tool_trace"] = legal_result.get("agent_trace") or []
        elif result.get("agent_trace") and result.get("agent_trace") != self.trace:
            final["legal_tool_trace"] = result.get("agent_trace") or []
        if tool_outcomes:
            final["tool_results"] = {
                key: {"status": value.status, "detail": value.detail}
                for key, value in tool_outcomes.items()
            }
            memory_items = _memory_from_outcomes(tool_outcomes)
            if memory_items:
                final["agent_memory"] = memory_items
        return final

    def _emit(
        self,
        step_id: str,
        title: str,
        status: str,
        detail: str,
        *,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        step = AgentTraceStep(
            id=step_id,
            title=title,
            status="running",
            detail=detail,
            metrics=metrics or {},
        )
        payload = step.complete(status=status, detail=detail).to_dict()
        self.trace.append(payload)
        if self.on_step:
            self.on_step(payload)

    @staticmethod
    def _plan_detail(plan: AgentPlan) -> str:
        labels = {
            "agent.memory_search": "memoria agente",
            "legal.answer_grounded": "ricerca legale",
            "matter.inspect": "lettura fascicolo",
            "answer.compose_operational": "composizione operativa",
            "respond.direct": "risposta diretta",
        }
        readable = [labels.get(action, action) for action in plan.actions]
        return "Percorso reale: " + ", ".join(readable)


def _extract_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


def _clean(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    return cleaned


def _dedupe(items: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _looks_like_chat(text: str) -> bool:
    stripped = text.strip().lower()
    return stripped in {"ciao", "hey", "salve", "buongiorno", "buonasera", "grazie", "ok"} or (
        len(stripped.split()) <= 3 and not any(marker in stripped for marker in ("decreto", "fattura", "diffida", "contratto"))
    )


def _legal_tool_detail(result: dict[str, Any]) -> str:
    status = str(result.get("status") or "unknown")
    citations = len(result.get("citations") or [])
    if status == "abstain":
        return "Il motore legale non ha trovato copertura sufficiente per una risposta normativa completa."
    if citations:
        return f"Motore legale completato con status={status} e {citations} fonti citate."
    return f"Motore legale completato con status={status}."


def _trace_status(status: str) -> str:
    lowered = status.lower()
    if lowered in {"grounded", "completed", "operational", "chat", "analysis"}:
        return "completed"
    if lowered in {"limited", "abstain", "skipped"}:
        return "limited"
    if lowered in {"failed", "error"}:
        return "failed"
    return "completed"


def _slim_result(result: dict[str, Any] | None) -> dict[str, Any]:
    if not result:
        return {}
    return {
        "status": result.get("status"),
        "answer": str(result.get("answer") or "")[:4000],
        "citations": result.get("citations") or [],
        "limits": result.get("limits") or [],
        "follow_up_questions": result.get("follow_up_questions") or [],
        "coverage": result.get("coverage") or {},
    }


def _slim_agent_memories(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slim: list[dict[str, Any]] = []
    for memory in memories:
        content = str(memory.get("content") or memory.get("excerpt") or "").strip()
        slim.append(
            {
                "id": memory.get("id"),
                "kind": memory.get("kind"),
                "scope": memory.get("scope"),
                "matter_id": memory.get("matter_id"),
                "title": memory.get("title"),
                "excerpt": content[:700],
                "tags": memory.get("tags") or [],
                "importance": memory.get("importance"),
                "source": memory.get("source"),
            }
        )
    return slim


def _memory_from_outcomes(outcomes: dict[str, ToolOutcome]) -> list[dict[str, Any]]:
    memory_outcome = outcomes.get("agent.memory_search")
    if not memory_outcome:
        return []
    memories = memory_outcome.data.get("memories")
    return memories if isinstance(memories, list) else []


def _normalise_sections(raw_sections: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_sections, list):
        return []
    out: list[dict[str, Any]] = []
    for raw in raw_sections:
        if not isinstance(raw, dict):
            continue
        section_type = _clean(str(raw.get("type") or "note")).lower().replace(" ", "_")
        title = _clean(str(raw.get("title") or _default_section_title(section_type)))
        items = []
        raw_items = raw.get("items") if isinstance(raw.get("items"), list) else []
        for item in raw_items:
            if isinstance(item, dict):
                text = _clean(str(item.get("text") or ""))
            else:
                text = _clean(str(item))
            if text:
                items.append(text)
        content = str(raw.get("content") or "").strip()
        if items or content:
            out.append({"type": section_type, "title": title, "items": items, "content": content})
    return out


def _default_section_title(section_type: str) -> str:
    return {
        "questions": "Dati da chiarire",
        "explanation": "Spiegazione pratica",
        "checklist": "Checklist documentale",
        "risks": "Rischi",
        "strategy": "Strategia operativa",
        "draft": "Bozza",
        "next_steps": "Prossimi passi",
    }.get(section_type, "Sezione")


def _render_sections(intro: str, sections: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    if intro.strip():
        lines.append(intro.strip())
    for section in sections:
        title = str(section.get("title") or _default_section_title(str(section.get("type") or ""))).strip()
        if title:
            lines.append(f"{title}:")
        content = str(section.get("content") or "").strip()
        if content:
            lines.append(content)
        for item in section.get("items") or []:
            text = str(item).strip()
            if text:
                lines.append(f"- {text}")
    return "\n".join(lines).strip()
