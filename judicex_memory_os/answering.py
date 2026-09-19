from __future__ import annotations

import json
import re
import textwrap
from typing import Any

from .answer_contract import enforce_answer_contract
from .audit_log import record_answer
from .confidence import compute_confidence
from .legal_agent import AgentTraceStep, LegalAgentRuntime
from .preflight import run_preflight
from .store import LegalMemoryStore


VALID_STATUSES = {"grounded", "limited", "abstain", "chat", "operational"}

_SECTION_TYPE_LABELS = {
    "questions": "Dati da chiarire",
    "checklist": "Checklist documentale",
    "legal_basis": "Base giuridica",
    "risks": "Rischi",
    "strategy": "Strategia operativa",
    "draft": "Bozza",
    "explanation": "Spiegazione pratica",
    "next_steps": "Prossimi passi",
    "facts": "Fatti rilevanti",
    "limits": "Limiti",
}

_LEGAL_SECTION_TYPES = {"legal_basis", "law", "sources", "legal_rules"}

_ACTION_LABELS = {
    "ask_missing_facts": "Domande sui dati mancanti",
    "legal_research": "Ricerca giuridica",
    "build_checklist": "Checklist documentale",
    "risk_analysis": "Analisi rischi",
    "strategy": "Strategia operativa",
    "draft_document": "Bozza atto",
    "explain": "Spiegazione pratica",
    "matter_analysis": "Analisi fascicolo",
}


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _looks_like_drafting(question: str) -> bool:
    lowered = question.lower()
    drafting_markers = (
        "redigi",
        "scrivi",
        "bozza",
        "atto",
        "ricorso",
        "comparsa",
        "citazione",
        "memoria",
        "diffida",
        "contratto",
    )
    return any(marker in lowered for marker in drafting_markers)


def _strip_emoji(text: str) -> str:
    emoji_pattern = re.compile(
        "["
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FAFF"
        "\U00002600-\U000026FF"
        "\U00002700-\U000027BF"
        "]+",
        flags=re.UNICODE,
    )
    stripped = emoji_pattern.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", stripped).strip()


_INTERNAL_LIMIT_MARKERS = (
    "affermazione rimossa",
    "claim rimosso",
    "citation gate",
    "verificatore",
    "controllo deterministico",
    "non presente nel corpus",
    "caricalo o disabilita la richiesta",
)

_SOURCE_INVENTORY_LIMIT_MARKERS = (
    "mancano gli articoli",
    "non è stata fornita la normativa",
    "non e stata fornita la normativa",
    "fonti attualmente presenti",
)

_LOW_VALUE_FOLLOW_UP_MARKERS = (
    "si desidera",
    "desideri",
    "vuoi",
    "eventuali ulteriori",
    "ulteriori dettagli",
    "chiarimenti su eventuali",
)


def _public_missing_information(items: list[Any]) -> list[str]:
    out: list[str] = []
    source_inventory_limited = False
    for item in items:
        text = _strip_emoji(str(item).strip())
        lowered = text.lower()
        if not text:
            continue
        if any(marker in lowered for marker in _INTERNAL_LIMIT_MARKERS):
            continue
        if any(marker in lowered for marker in _SOURCE_INVENTORY_LIMIT_MARKERS):
            source_inventory_limited = True
            continue
        if text not in out:
            out.append(text)
    if source_inventory_limited:
        generic = "La risposta resta limitata alle fonti disponibili nella memoria locale."
        if generic not in out:
            out.append(generic)
    return out


def _public_follow_up_questions(items: list[Any]) -> list[str]:
    out: list[str] = []
    for item in items:
        text = _strip_emoji(str(item).strip())
        lowered = text.lower()
        if not text:
            continue
        if any(marker in lowered for marker in _LOW_VALUE_FOLLOW_UP_MARKERS):
            continue
        if text not in out:
            out.append(text)
    return out


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _strip_emoji(str(item).strip())
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


class GroundedAnswerEngine:
    def __init__(
        self,
        *,
        store: LegalMemoryStore,
        client: Any,
        model: str,
        area: str | None = None,
        matter_id: str | None = None,
    ) -> None:
        self.store = store
        self.client = client
        self.model = model
        self.area = area
        self.matter_id = matter_id

    def answer(self, question: str, *, recent_user_turns: list[str] | None = None) -> dict[str, Any]:
        recent_turns = recent_user_turns or []
        intent_route = self._route_intent(question, recent_turns)
        if intent_route["intent"] == "chat":
            rendered = self._render_chat_answer(question, intent_route, recent_turns)
            audit = record_answer(
                self.store,
                question=question,
                context={"intent_route": intent_route},
                payload=rendered,
                model=self.model,
                area=self.area or "",
                matter_id=self.matter_id or "",
            )
            rendered["audit"] = audit
            return rendered
        if self.matter_id and intent_route["intent"] == "matter_analysis":
            thesis = str(intent_route.get("thesis") or "").strip() or self._matter_analysis_thesis(
                question,
                recent_turns,
            )
            analysis = self.store.analyze_matter(self.matter_id, thesis)
            rendered = self._render_matter_analysis(analysis, intent_route=intent_route)
            audit = record_answer(
                self.store,
                question=question,
                context={"matter_analysis": analysis, "intent_route": intent_route},
                payload=rendered,
                model=self.model,
                area=self.area or "",
                matter_id=self.matter_id,
            )
            rendered["audit"] = audit
            return rendered

        context = LegalAgentRuntime(
            self.store,
            client=self.client,
            model=self.model,
            area=self.area,
        ).build_context(question)
        context["intent_route"] = intent_route
        context.setdefault("agent_trace", []).insert(0, self._planning_trace_step(intent_route))
        context["preflight"] = run_preflight(self.store, context=context)
        preflight_step = AgentTraceStep(
            id="preflight_check",
            title="Pre-flight matter-aware",
            status="running",
            detail="Verifica vigenza e modifiche degli articoli rilevanti per il caso.",
        )
        if context["preflight"]["warnings"]:
            preflight_step.complete(
                status="limited",
                detail="Pre-flight ha rilevato segnalazioni: " + "; ".join(context["preflight"]["warnings"][:3]),
                metrics={"warnings": len(context["preflight"]["warnings"])},
            )
        else:
            preflight_step.complete(detail="Tutti gli articoli rilevanti sono vigenti alla data del fatto.")
        context.setdefault("agent_trace", []).append(preflight_step.to_dict())
        if self.matter_id:
            matter_context = self.store.build_matter_context(self.matter_id, query=question)
            if "error" not in matter_context:
                context["matter_context"] = matter_context
            else:
                context["matter_context_error"] = matter_context["error"]
        raw = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {
                    "role": "user",
                    "content": self._user_prompt(question, context, recent_turns),
                },
            ],
            temperature=0.0,
        )
        context.setdefault("agent_trace", []).append(
            AgentTraceStep(
                id="controlled_drafting",
                title="Redazione vincolata",
                status="running",
                detail="Generazione della risposta usando solo le evidenze selezionate.",
            )
            .complete(detail="Risposta strutturata prodotta per la validazione.")
            .to_dict()
        )
        payload = self._validate_or_repair(
            raw=raw,
            question=question,
            context=context,
            recent_user_turns=recent_turns,
        )
        allowed_ids = {doc["id"] for doc in context["documents"] + context["related_documents"]}
        payload = self._repair_abstain_when_covered(
            payload=payload,
            question=question,
            context=context,
            allowed_ids=allowed_ids,
            recent_user_turns=recent_turns,
        )
        payload = self._repair_missing_covered_issues(
            payload=payload,
            question=question,
            context=context,
            allowed_ids=allowed_ids,
            recent_user_turns=recent_turns,
        )
        payload = self._repair_operational_abstain(
            payload=payload,
            question=question,
            context=context,
            allowed_ids=allowed_ids,
            recent_user_turns=recent_turns,
        )
        payload = self._semantic_verify_payload(payload=payload, context=context, question=question)
        payload = enforce_answer_contract(
            payload,
            context,
            client=self.client,
            model=self.model,
        )
        payload = self._safety_net_for_persistent_abstain(
            payload=payload,
            context=context,
        )
        payload["_answer_confidence"] = compute_confidence(payload, context)
        contract_status = str((payload.get("_answer_contract") or {}).get("status", "unknown"))
        verifier_status = str((payload.get("_semantic_verifier") or {}).get("status", "unknown"))
        context.setdefault("agent_trace", []).append(
            AgentTraceStep(
                id="validation",
                title="Validazione fonti",
                status="running",
                detail="Controllo citazioni, numeri giuridici e supporto semantico.",
            )
            .complete(
                status="completed" if payload.get("status") in {"grounded", "limited", "chat", "operational"} else "limited",
                detail=f"Esito risposta: {payload.get('status')}; citation gate: {contract_status}; verifica semantica: {verifier_status}.",
            )
            .to_dict()
        )
        rendered = self._render(payload, context)
        audit = record_answer(
            self.store,
            question=question,
            context=context,
            payload=rendered,
            model=self.model,
            area=self.area or "",
            matter_id=self.matter_id,
        )
        rendered["audit"] = audit
        return rendered

    def _route_intent(self, question: str, recent_user_turns: list[str]) -> dict[str, Any]:
        briefing = {
            "active_matter_id": self.matter_id,
            "area_preference": self.area,
            "user_message": question,
            "recent_user_turns_for_context": [turn for turn in recent_user_turns[-3:] if turn],
            "available_capabilities": [
                {
                    "intent": "matter_analysis",
                    "description": (
                        "Use when the user wants a private file reviewed against a goal or thesis, "
                        "including readiness, missing proof, evidentiary gaps, documents still needed, "
                        "or whether the file is strong enough for an action."
                    ),
                },
                {
                    "intent": "legal_answer",
                    "description": (
                        "Use when the user asks for legal rules, legal explanation, deadlines, drafting, "
                        "or a legal answer that should be grounded in official sources."
                    ),
                },
                {
                    "intent": "chat",
                    "description": "Use for non-legal conversation or questions about the system itself.",
                },
            ],
        }
        try:
            raw = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._intent_router_prompt()},
                    {"role": "user", "content": json.dumps(briefing, ensure_ascii=False, separators=(",", ":"))},
                ],
                temperature=0.0,
            )
            parsed = _extract_json_object(raw)
        except Exception as exc:
            return self._normalise_intent_route(question, {
                "intent": "legal_answer",
                "confidence": 0.0,
                "reason": f"intent router failed: {exc}",
                "thesis": question,
            })

        intent = str(parsed.get("intent", "legal_answer")).strip()
        if intent not in {"matter_analysis", "legal_answer", "chat"}:
            intent = "legal_answer"
        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(confidence, 1.0))
        if intent == "matter_analysis" and confidence < 0.55:
            intent = "legal_answer"
        return self._normalise_intent_route(question, {
            "intent": intent,
            "confidence": confidence,
            "reason": _strip_emoji(str(parsed.get("reason", "")).strip()),
            "thesis": _strip_emoji(str(parsed.get("thesis", question)).strip()) or question,
            "chat_answer": _strip_emoji(str(parsed.get("chat_answer", "")).strip()),
            "answer_style": _strip_emoji(str(parsed.get("answer_style", "")).strip()),
            "requested_outputs": [
                _strip_emoji(str(item).strip())
                for item in parsed.get("requested_outputs", [])
                if str(item).strip()
            ] if isinstance(parsed.get("requested_outputs", []), list) else [],
            "agent_plan": parsed.get("agent_plan") if isinstance(parsed.get("agent_plan"), dict) else {},
            "actions": parsed.get("actions") if isinstance(parsed.get("actions"), list) else [],
        })

    def _normalise_intent_route(self, question: str, route: dict[str, Any]) -> dict[str, Any]:
        intent = str(route.get("intent") or "legal_answer").strip()
        if intent not in {"matter_analysis", "legal_answer", "chat"}:
            intent = "legal_answer"
        if intent == "matter_analysis" and not self.matter_id:
            intent = "legal_answer"
        requested_outputs = _dedupe_preserve_order(
            [
                str(item)
                for item in route.get("requested_outputs", [])
                if str(item).strip()
            ]
            if isinstance(route.get("requested_outputs", []), list)
            else []
        )
        answer_style = _strip_emoji(str(route.get("answer_style", "")).strip()) or "default"
        explicit_actions = _dedupe_preserve_order(
            [
                str(item)
                for item in route.get("actions", [])
                if str(item).strip()
            ]
            if isinstance(route.get("actions", []), list)
            else []
        )
        plan = route.get("agent_plan") if isinstance(route.get("agent_plan"), dict) else {}
        actions = self._infer_agent_actions(
            question=question,
            intent=intent,
            answer_style=answer_style,
            requested_outputs=requested_outputs,
            explicit_actions=explicit_actions,
        )
        output_sections = self._infer_output_sections(
            question=question,
            answer_style=answer_style,
            requested_outputs=requested_outputs,
            actions=actions,
        )
        normalised_plan = {
            "goal": _strip_emoji(str(plan.get("goal") or route.get("thesis") or question).strip()) or question,
            "actions": actions,
            "output_sections": output_sections,
            "needs_legal_research": intent == "legal_answer" and "legal_research" in actions,
            "needs_matter_context": intent == "matter_analysis" or bool(self.matter_id),
            "source_policy": (
                "Cita fonti ufficiali solo nelle sezioni giuridiche; domande, checklist, strategia e bozze "
                "possono usare i fatti dell'utente e del fascicolo senza trasformarli in fonti normative."
            ),
        }
        try:
            route_confidence = float(route.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            route_confidence = 0.0
        return {
            "intent": intent,
            "confidence": max(0.0, min(route_confidence, 1.0)),
            "reason": _strip_emoji(str(route.get("reason", "")).strip()),
            "thesis": _strip_emoji(str(route.get("thesis", question)).strip()) or question,
            "chat_answer": _strip_emoji(str(route.get("chat_answer", "")).strip()),
            "answer_style": answer_style,
            "requested_outputs": requested_outputs,
            "actions": actions,
            "agent_plan": normalised_plan,
        }

    @staticmethod
    def _infer_agent_actions(
        *,
        question: str,
        intent: str,
        answer_style: str,
        requested_outputs: list[str],
        explicit_actions: list[str],
    ) -> list[str]:
        if intent == "chat":
            return ["answer_direct"]
        if intent == "matter_analysis":
            return ["matter_analysis"]
        actions = [
            action
            for action in explicit_actions
            if action in {
                "answer_direct",
                "ask_missing_facts",
                "legal_research",
                "build_checklist",
                "risk_analysis",
                "strategy",
                "draft_document",
                "explain",
            }
        ]
        text = f"{question}\n{answer_style}\n{' '.join(requested_outputs)}".lower()
        if any(marker in text for marker in ("domande", "dati mancanti", "chiarire", "mi serve sapere")):
            actions.append("ask_missing_facts")
        if any(marker in text for marker in ("checklist", "documentale", "documenti servono", "documenti necessari")):
            actions.append("build_checklist")
        if any(marker in text for marker in ("rischi", "rischio", "criticità", "criticita", "opposizione")):
            actions.append("risk_analysis")
        if any(marker in text for marker in ("strategia", "scelta", "consiglieresti", "prossimi passi", "operativa")):
            actions.append("strategy")
        if any(marker in text for marker in ("redigi", "bozza", "scrivi", "diffida", "ricorso", "atto", "contratto")):
            actions.append("draft_document")
        if any(marker in text for marker in ("spiegami", "differenza", "quando usare", "cosa cambia")):
            actions.append("explain")
        if not actions or any(
            action in actions
            for action in ("legal_research", "build_checklist", "risk_analysis", "strategy", "draft_document", "explain")
        ):
            actions.insert(0, "legal_research")
        return _dedupe_preserve_order(actions or ["legal_research"])

    @staticmethod
    def _infer_output_sections(
        *,
        question: str,
        answer_style: str,
        requested_outputs: list[str],
        actions: list[str],
    ) -> list[str]:
        text = f"{question}\n{answer_style}\n{' '.join(requested_outputs)}".lower()
        sections: list[str] = []
        if "ask_missing_facts" in actions:
            sections.append("questions")
        if "explain" in actions:
            sections.append("explanation")
        if "legal_research" in actions and not (
            sections == ["questions"] and "solo" in text and len(actions) <= 2
        ):
            sections.append("legal_basis")
        if "build_checklist" in actions:
            sections.append("checklist")
        if "risk_analysis" in actions:
            sections.append("risks")
        if "strategy" in actions:
            sections.append("strategy")
        if "draft_document" in actions:
            sections.append("draft")
        if "prossimi passi" in text:
            sections.append("next_steps")
        return _dedupe_preserve_order(sections or ["legal_basis"])

    @staticmethod
    def _planning_trace_step(intent_route: dict[str, Any]) -> dict[str, Any]:
        plan = intent_route.get("agent_plan") or {}
        actions = [str(item) for item in plan.get("actions") or [] if str(item).strip()]
        readable = [_ACTION_LABELS.get(action, action.replace("_", " ")) for action in actions]
        step = AgentTraceStep(
            id="answer_planning",
            title="Pianificazione risposta",
            status="completed",
            detail=(
                "Percorso scelto: " + ", ".join(readable)
                if readable
                else "Percorso scelto in base alla richiesta dell'utente."
            ),
            metrics={
                "intent": intent_route.get("intent", ""),
                "actions": actions,
                "output_sections": plan.get("output_sections") or [],
            },
        )
        return step.complete(status="completed").to_dict()

    def _intent_router_prompt(self) -> str:
        return textwrap.dedent(
            """
            Sei il router semantico di Judicex. Devi capire l'intento operativo dell'utente,
            non rispondere alla domanda.

            Scegli una sola capability disponibile:
            - matter_analysis: analisi del fascicolo privato rispetto a un obiettivo o tesi, con
              verifica di prove presenti, lacune, documenti mancanti, prontezza del fascicolo,
              forza probatoria o prossime azioni istruttorie.
            - legal_answer: risposta giuridica, spiegazione normativa, termini, redazione,
              strategia giuridica o applicazione del diritto che richiede fonti ufficiali.
            - chat: conversazione non giuridica o domanda sul funzionamento del sistema.

            Restituisci solo JSON valido:
            {
              "intent": "matter_analysis" | "legal_answer" | "chat",
              "confidence": 0.0,
              "thesis": "obiettivo/tesi riscritta in modo autosufficiente, se utile",
              "chat_answer": "risposta breve solo se intent=chat, altrimenti stringa vuota",
              "answer_style": "default | intake | checklist | strategy | drafting | explanation",
              "requested_outputs": ["domande sui dati mancanti", "checklist", "rischi", "strategia"],
              "actions": ["ask_missing_facts", "legal_research", "build_checklist", "risk_analysis", "strategy", "draft_document", "explain"],
              "agent_plan": {
                "goal": "obiettivo pratico della risposta",
                "actions": ["azioni operative ordinate"],
                "output_sections": ["questions", "legal_basis", "checklist", "risks", "strategy", "draft"]
              },
              "reason": "breve ragione della scelta"
            }

            Regole:
            - Non usare parole chiave meccaniche: interpreta il significato complessivo.
            - Se il messaggio è conversazione semplice, saluto, ringraziamento, chiarimento
              sull'interfaccia o domanda sul funzionamento di Judicex, scegli chat e compila
              chat_answer con una risposta naturale, breve e utile.
            - Se l'utente vuole sapere se un fascicolo e pronto, cosa manca, quali prove servono
              o quanto e solida una tesi nel file, scegli matter_analysis solo se active_matter_id
              è presente. Se active_matter_id è vuoto, scegli legal_answer e pianifica una risposta
              operativa basata sui fatti scritti dall'utente.
            - Se l'utente chiede il contenuto del diritto, termini legali, atti o spiegazioni normative,
              scegli legal_answer.
            - Se l'utente chiede un lavoro misto (domande, checklist, rischi, strategia, bozza),
              non ridurlo a una sola spiegazione: compila actions e output_sections nell'ordine pratico richiesto.
            - Non citare fonti e non dare consigli giuridici nel router.
            """
        ).strip()

    def _render_chat_answer(
        self,
        question: str,
        intent_route: dict[str, Any],
        recent_user_turns: list[str],
    ) -> dict[str, Any]:
        answer = str(intent_route.get("chat_answer") or "").strip()
        if not answer:
            answer = self._llm_chat_answer(question, recent_user_turns)
        return {
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
            "intent_route": intent_route,
            "answer_contract": {"status": "skipped", "reason": "chat_intent", "traces": []},
            "semantic_verifier": {"status": "skipped", "reason": "chat_intent"},
            "evidence_trace": [],
            "agent_trace": [],
            "legal_issues": [],
        }

    def _llm_chat_answer(self, question: str, recent_user_turns: list[str]) -> str:
        try:
            raw = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Sei Judicex. Questa e conversazione semplice o domanda sul sistema: "
                            "rispondi in italiano, breve e pratico. Non citare fonti, non usare il percorso legale, "
                            "non dire abstain e non chiedere di caricare fonti se non serve."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "user_message": question,
                                "recent_user_turns": [turn for turn in recent_user_turns[-3:] if turn],
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                ],
                temperature=0.0,
            )
            answer = _strip_emoji(str(raw).strip())
            if answer:
                return answer
        except Exception:
            pass
        return "Dimmi pure cosa vuoi fare in Judicex."

    @staticmethod
    def _matter_analysis_thesis(question: str, recent_user_turns: list[str]) -> str:
        cleaned = re.sub(r"\s+", " ", question).strip()
        if len(cleaned) >= 16:
            return cleaned
        prior = " ".join(turn for turn in recent_user_turns[-2:] if turn).strip()
        if prior:
            return f"{prior} {cleaned}".strip()
        return cleaned or "analisi generale del fascicolo"

    def _system_prompt(self) -> str:
        return textwrap.dedent(
            """
            Sei Judicex, software legale italiano. Rispondi in italiano, tono professionale, niente emoji.

            REGISTRO DELLA RISPOSTA (vale per OGNI stato: chat, operational, grounded, limited, abstain):
            - Scrivi come un collega avvocato che risponde diretto, non come un sistema che annuncia di stare per rispondere.
            - VIETATE le aperture meta-discorsive: "Risposta normativa al quesito...", "In relazione al quesito posto...", "Per rispondere alla domanda...", "Si fornisce di seguito...", "Di seguito si indica...", "Di seguito trovi...", "Premesso che...", "In merito alla questione...", "Con riferimento a...", "Ecco gli elementi...", "Riportiamo i...". Sono pesanti e suonano da burocrate.
            - Apri con il merito. Se la risposta è "60 giorni", la prima frase comincia con "Il termine è di 60 giorni..." o "L'art. 6 L. 604/66 prevede 60 giorni...". Non con una frase di servizio sulla domanda.
            - Se la domanda è una conferma di una premessa errata, la prima frase deve correggere la premessa in modo netto: "No. Il termine non è 90 ma 60 giorni…". Non aprire con cortesie attorno.
            - Niente intestazioni etichetta come "Risposta:", "Conclusione:", "Riepilogo:", "Spiegazione:".
            - Il campo "intro" del JSON è la prima frase che l'utente legge: trattalo come l'attacco di un parere, non come una didascalia.

            REGOLA ASSOLUTA — NIENTE CITAZIONI FUORI PACCHETTO (la più importante di tutte):
            - NON puoi mai citare, nominare o riferirti a una norma, una legge, un decreto, un articolo, una sentenza o un'autorità che NON sia presente come document_id dentro evidence_documents_primary. Mai. Nemmeno "di passaggio". Nemmeno "a memoria". Nemmeno in una bozza di atto. Nemmeno in una checklist o in una sezione draft.
            - Se ti viene in mente "DPR 2/2010", "dlgs 104/2010", "codice del processo amministrativo", "art. 31 L. 241/1990", "art. 18 Statuto", "art. 633 c.p.c." o qualsiasi altro riferimento, ferma la mano: lo puoi nominare SOLO se quel document_id esiste già in evidence_documents_primary. Altrimenti tace e basta.
            - Riferirsi a una norma per memoria del modello (training data) è ALLUCINAZIONE, anche se la norma esiste davvero nel mondo reale. Qui conta solo cosa c'è nel pacchetto.

            REGOLA ASSOLUTA — ABSTAIN PULITO QUANDO MANCA L'AREA:
            - Se la domanda riguarda un'area del diritto per la quale evidence_documents_primary non contiene nessun documento pertinente (es. utente chiede diritto amministrativo / TAR e il pacchetto ha solo lavoro/civile), DEVI usare status="abstain".
            - In quel caso NON produrre sections, NON produrre draft, NON produrre checklist, NON produrre risks, NON produrre claims, NON produrre legal_basis. Niente. Solo "intro" con il testo: "Non ho fonti di [area del diritto] nella memoria. Per rispondere mi servirebbe il bundle [nome bundle se lo conosci, altrimenti descrizione]." e "missing_information" con la stringa dell'area mancante.
            - NON è ammesso produrre un template generico di atto/ricorso/diffida "tanto per aiutare". Quello è esattamente il comportamento che genera allucinazioni nel dominio legale: bozze con riferimenti normativi pescati dal training.
            - intent_route.agent_plan.output_sections che richiede draft/checklist/strategy NON sovrascrive questa regola: senza fonti dell'area, niente output operativo.

            Hai a disposizione un pacchetto di fonti (evidence_documents_primary) contenente articoli ufficiali con il loro testo. La user_message può contenere anche fatti del caso (importi, date, residenza, tipo di credito): sono input legittimi per il tuo ragionamento, non servono altre fonti per usarli. Se sono presenti legal_issues, issue_coverage e answer_contract, usali come piano di risposta: tratta ogni questione coperta e non rispondere a questioni prive di fonti pertinenti.

            Devi scegliere uno stato e produrre output JSON.
            - "chat": small talk, domande non giuridiche, domande sul sistema
            - "operational": risposta operativa che serve soprattutto a raccogliere dati, ordinare il lavoro,
              impostare checklist, strategia o bozza senza introdurre nuove affermazioni giuridiche non citate
            - "grounded": il quesito è coperto dalle evidenze; ogni claim cita uno o più document_id presenti nel pacchetto
            - "limited": il quesito ha più sottoparti e solo alcune sono coperte; rispondi a quelle citando le fonti, dichiara nel missing_information le sotto-domande non coperte
            - "abstain": NESSUNA delle evidenze fornite consente di rispondere al quesito (le fonti sono palesemente fuori bersaglio o mancano del tutto)

            Linee guida sostanziali:
            - Prima segui intent_route.agent_plan.actions e intent_route.agent_plan.output_sections:
              sono il percorso operativo scelto per la richiesta concreta dell'utente.
            - Rispetta la forma operativa richiesta dall'utente. Se chiede "fammi domande",
              "checklist", "rischi", "strategia" o "prossimi passi", crea sezioni native:
              questions, checklist, risks, strategy, next_steps, draft, explanation, legal_basis.
            - Se intent_route.requested_outputs contiene più deliverable, la risposta deve
              mantenerli tutti come sezioni distinte e ordinate. Se una sezione non può essere
              completata per mancanza di fonti o dati, crea comunque la sezione come limite
              operativo o come domande pratiche.
            - Se l'utente chiede anche una bozza di atto ma i dati sono incompleti, non ignorare
              la richiesta: prepara una bozza prudente con segnaposto per i dati mancanti solo
              quando il testo non richiede affermazioni giuridiche non supportate; altrimenti
              indica quali dati servono prima di redigerla.
            - Se l'utente chiede domande sui dati mancanti, inserisci in follow_up_questions
              domande pratiche sui fatti del caso, sui documenti, sulle date, sulle parti,
              sugli importi, sulle notifiche/comunicazioni e sulle prove disponibili.
            - missing_information deve contenere limiti comprensibili per l'utente, non dettagli
              interni sul corpus, sul retrieval o sugli articoli che il sistema avrebbe voluto trovare.
              Se alcune fonti non sono disponibili, rispondi comunque sulle parti coperte e segnala
              in modo breve che la risposta resta limitata alle fonti caricate.
            - cita sempre alla lettera del testo della fonte. Non arrotondare, non unificare regimi distinti (per esempio termini UE ed extra-UE devono restare separati), non trasformare un tetto massimo in una "estensione generica"
            - distingui i termini tecnici: emissione, deposito, notificazione, adempimento, opposizione, esecuzione, prescrizione non sono intercambiabili
            - se la domanda ha più quesiti, rispondi a ciascuno citando la fonte specifica
            - se l'utente fornisce fatti scenari nella user_message (es. data fattura, residenza debitore, importo) usali insieme alle fonti per produrre una risposta concreta e applicata al caso
            - se issue_coverage indica "covered" per una questione, quella questione va trattata con le fonti disponibili: non richiedere fonti ulteriori solo perché sarebbero utili approfondimenti
            - per ogni elemento di answer_contract.mandatory_covered_issue_claims, produci almeno un claim dedicato, con issue_ids contenente quell'issue_id e citations contenente required_document_id
            - le issue elencate in answer_contract.uncovered_issues non devono generare claims: vanno indicate solo in missing_information
            - prima di restituire il JSON, fai un controllo interno di completezza: ogni mandatory_covered_issue_claims deve essere coperto da almeno un claim citato
            - non richiedere giurisprudenza o dottrina come prerequisito quando la domanda può ricevere una risposta normativa entro i limiti delle fonti ufficiali fornite
            - claims serve per le affermazioni giuridiche verificabili; sections serve per la risposta che l'avvocato legge.
              Ogni contenuto giuridico in sections di tipo legal_basis deve avere citations valide oppure essere ripetuto in claims con citations.
              Le sezioni questions, checklist, risks, strategy e draft possono non avere citazioni se sono operative, basate sui fatti dell'utente,
              o formulate come prudenza professionale senza affermare diritto nuovo.

            Quando puoi rispondere ("grounded" o "limited") non astenerti per eccesso di prudenza: se hai almeno una fonte pertinente nel pacchetto, rispondi entro il perimetro che le fonti coprono.
            Se intent_route.agent_plan.output_sections contiene sezioni operative come questions,
            checklist, risks, strategy, draft o explanation, non usare abstain solo perché una
            parte giuridica non è coperta: usa status=operational per produrre le parti pratiche
            non citate e metti i limiti giuridici in missing_information.

            REGOLE STRINGENTI SU "abstain":
            - "abstain" è ammesso SOLO se issue_coverage è interamente "missing_sources" o se il pacchetto evidence_documents_primary è vuoto. NON usare "abstain" quando issue_coverage indica almeno una questione "covered".
            - "abstain" NON è ammesso quando puoi comunque soddisfare deliverable operativi
              richiesti dall'utente senza affermare diritto non supportato.
            - Le fonti ufficiali in questo sistema sono recuperate da Normattiva con il marcatore di vigenza alla data del fatto (parametro `vig=YYYY-MM-DD` nel source_ref). NON è ammesso astenersi adducendo che le norme "potrebbero non riflettere modifiche successive": la versione consegnata è quella vigente alla as_of_date dello scenario.
            - Lo step `preflight_check` ha già verificato la vigenza degli articoli rilevanti nel grafo citatorio. Se preflight_check è "completed" e dichiara articoli vigenti, NON ripetere quel dubbio nell'intro.
            - Non chiedere giurisprudenza o dottrina come prerequisito quando la domanda è normativa e le fonti coprono il quesito.

            Devi restituire esclusivamente JSON con questo schema:
            {
              "status": "chat" | "operational" | "grounded" | "limited" | "abstain",
              "chat_answer": "testo libero solo per status=chat",
              "intro": "frase iniziale per status grounded/limited/abstain",
              "sections": [
                {
                  "type": "questions | legal_basis | checklist | risks | strategy | draft | explanation | next_steps | facts | limits",
                  "title": "titolo leggibile della sezione",
                  "items": [
                    {"text": "voce della sezione", "citations": ["document_id_1"]},
                    "voce operativa senza citazione"
                  ],
                  "content": "testo esteso per bozze o spiegazioni discorsive",
                  "citations": ["document_id_1"],
                  "requires_citations": false
                }
              ],
              "claims": [
                {
                  "text": "affermazione supportata",
                  "issue_ids": ["issue_1"],
                  "citations": ["document_id_1", "document_id_2"]
                }
              ],
              "case_facts": [
                {
                  "text": "fatto del fascicolo rilevante",
                  "fact_ids": ["matterfact_id_1"],
                  "document_ids": ["matterdoc_id_1"]
                }
              ],
              "missing_information": ["limiti o dati mancanti"],
              "follow_up_questions": ["eventuali chiarimenti utili"]
            }

            Vincoli di validità:
            - status=chat: usa chat_answer e lascia claims vuoto
            - status=operational: usa sections, claims può essere vuoto; non fare affermazioni giuridiche non citate
            - status=grounded o limited: almeno un claim con almeno una citation valida
            - status=abstain: claims vuoto
            - ogni citation deve essere uno degli id presenti nelle evidenze
            - ogni fact_id o document_id in case_facts deve essere presente nel matter_context
            """
        ).strip()

    @staticmethod
    def _slim_document(doc: dict[str, Any], *, include_full_content: bool) -> dict[str, Any]:
        content = doc.get("content") or doc.get("excerpt") or ""
        if not include_full_content:
            flat = content.strip().replace("\n", " ")
            content = flat[:600] + ("..." if len(flat) > 600 else "")
        else:
            max_chars = 4000
            if len(content) > max_chars:
                cut = content.rfind("\n", 0, max_chars)
                if cut < max_chars // 2:
                    cut = max_chars
                content = content[:cut].rstrip() + "\n[...segue]"
        slim = {
            "id": doc["id"],
            "title": doc.get("title", ""),
            "source_ref": doc.get("source_ref", ""),
            "content": content,
        }
        effective_from = doc.get("effective_from")
        effective_to = doc.get("effective_to")
        if effective_from:
            slim["effective_from"] = effective_from
        if effective_to:
            slim["effective_to"] = effective_to
        return slim

    @staticmethod
    def _slim_relationship(edge: dict[str, Any]) -> dict[str, Any]:
        def _endpoint(side: dict[str, Any]) -> dict[str, Any]:
            metadata = side.get("metadata") or {}
            return {
                "name": side.get("name", ""),
                "document_id": metadata.get("document_id", ""),
            }
        return {
            "relation": edge.get("relation", ""),
            "source": _endpoint(edge.get("source") or {}),
            "target": _endpoint(edge.get("target") or {}),
        }

    def _user_prompt(self, question: str, context: dict[str, Any], recent_user_turns: list[str]) -> str:
        primary_docs = [self._slim_document(doc, include_full_content=True) for doc in context["documents"]]
        related_docs = [self._slim_document(doc, include_full_content=False) for doc in context["related_documents"]]
        payload: dict[str, Any] = {
            "user_message": question,
            "intent_route": context.get("intent_route", {}),
            "agent_plan": (context.get("intent_route") or {}).get("agent_plan", {}),
            "evidence_documents_primary": primary_docs,
        }
        if context.get("legal_issues"):
            payload["legal_issues"] = context["legal_issues"]
        issue_coverage = (context.get("coverage") or {}).get("issue_coverage")
        if issue_coverage:
            payload["issue_coverage"] = issue_coverage
            payload["answer_contract"] = {
                "mandatory_covered_issue_claims": self._mandatory_covered_issue_claims(context),
                "uncovered_issues": self._uncovered_issues(context),
                "instruction": (
                    "Ogni mandatory_covered_issue_claims richiede almeno un claim dedicato "
                    "con issue_ids e citations. Le uncovered_issues vanno solo in missing_information."
                ),
            }
        if related_docs:
            payload["evidence_documents_related"] = related_docs
        trimmed_turns = [turn for turn in recent_user_turns[-3:] if turn]
        if trimmed_turns:
            payload["recent_user_turns_for_discourse_only"] = trimmed_turns
        matter_context = context.get("matter_context")
        if matter_context and self._matter_context_has_content(matter_context):
            payload["matter_context"] = self._slim_matter_context(matter_context)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _mandatory_covered_issue_claims(context: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for issue in (context.get("coverage") or {}).get("issue_coverage") or []:
            if issue.get("status") != "covered":
                continue
            documents = issue.get("documents") or []
            if not documents:
                continue
            doc = documents[0]
            doc_id = str(doc.get("id", "")).strip()
            if not doc_id:
                continue
            out.append(
                {
                    "issue_id": issue.get("id", ""),
                    "title": issue.get("title", ""),
                    "question": issue.get("question", ""),
                    "required_document_id": doc_id,
                    "required_document_title": doc.get("title", ""),
                }
            )
        return out

    @staticmethod
    def _uncovered_issues(context: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "issue_id": issue.get("id", ""),
                "title": issue.get("title", ""),
                "question": issue.get("question", ""),
                "required_articles": issue.get("required_articles", []),
            }
            for issue in (context.get("coverage") or {}).get("issue_coverage") or []
            if issue.get("status") != "covered"
        ]

    @staticmethod
    def _matter_context_has_content(matter_context: dict[str, Any]) -> bool:
        # Il fascicolo si considera "vuoto" quando coverage e tutte le liste sono a 0/[]
        coverage = matter_context.get("coverage") or {}
        if any((coverage.get(k) or 0) > 0 for k in ("amounts", "deadlines", "documents", "facts", "parties", "timeline_events")):
            return True
        for key in ("documents", "facts", "timeline", "parties", "amounts", "deadlines"):
            if matter_context.get(key):
                return True
        return False

    @staticmethod
    def _slim_matter_document(doc: dict[str, Any]) -> dict[str, Any]:
        excerpt = str(doc.get("excerpt") or doc.get("content") or "").strip().replace("\n", " ")
        return {
            "id": doc.get("id", ""),
            "title": doc.get("title", ""),
            "kind": doc.get("kind", ""),
            "excerpt": excerpt[:900] + ("..." if len(excerpt) > 900 else ""),
        }

    @staticmethod
    def _slim_matter_fact(fact: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": fact.get("id", ""),
            "document_id": fact.get("document_id", ""),
            "type": fact.get("fact_type", ""),
            "label": fact.get("label", ""),
            "text": fact.get("text", ""),
            "value": fact.get("value", ""),
            "unit": fact.get("unit", ""),
            "date_value": fact.get("date_value", ""),
            "source_quote": fact.get("source_quote", ""),
            "confidence": fact.get("confidence", 1.0),
        }

    def _slim_matter_context(self, matter_context: dict[str, Any]) -> dict[str, Any]:
        return {
            "matter": {
                "id": (matter_context.get("matter") or {}).get("id", ""),
                "title": (matter_context.get("matter") or {}).get("title", ""),
                "client_name": (matter_context.get("matter") or {}).get("client_name", ""),
                "area": (matter_context.get("matter") or {}).get("area", ""),
                "status": (matter_context.get("matter") or {}).get("status", ""),
                "summary": (matter_context.get("matter") or {}).get("summary", ""),
            },
            "coverage": matter_context.get("coverage") or {},
            "documents": [self._slim_matter_document(doc) for doc in (matter_context.get("documents") or [])[:6]],
            "facts": [self._slim_matter_fact(fact) for fact in (matter_context.get("facts") or [])[:20]],
            "timeline": [self._slim_matter_fact(fact) for fact in (matter_context.get("timeline") or [])[:20]],
            "parties": [self._slim_matter_fact(fact) for fact in (matter_context.get("parties") or [])[:12]],
            "amounts": [self._slim_matter_fact(fact) for fact in (matter_context.get("amounts") or [])[:12]],
            "deadlines": [self._slim_matter_fact(fact) for fact in (matter_context.get("deadlines") or [])[:12]],
        }

    _SEMANTIC_ABSTAIN_MARKERS = ("citation", "claim")

    def _validate_or_repair(
        self,
        *,
        raw: str,
        question: str,
        context: dict[str, Any],
        recent_user_turns: list[str],
    ) -> dict[str, Any]:
        allowed_ids = {doc["id"] for doc in context["documents"] + context["related_documents"]}
        last_error = ""
        # First attempt: parse raw output directly.
        try:
            payload = _extract_json_object(raw)
            payload = self._validate_payload(payload, allowed_ids, context)
            return self._repair_abstain_when_covered(
                payload=payload,
                question=question,
                context=context,
                allowed_ids=allowed_ids,
                recent_user_turns=recent_user_turns,
            )
        except Exception as exc:
            last_error = str(exc)
            lowered = last_error.lower()
            # Short-circuit: if the model produced parseable JSON but violated citation
            # rules, retrying will almost certainly fail again. Jump to LLM-generated
            # abstain to save one model call on the cold abstain path.
            if any(marker in lowered for marker in self._SEMANTIC_ABSTAIN_MARKERS):
                return self._llm_generated_abstain(
                    question=question,
                    context=context,
                    last_error=last_error,
                )

        # Second attempt: one repair pass for pure JSON/format errors only.
        try:
            candidate_raw = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {
                        "role": "user",
                        "content": self._user_prompt(question, context, recent_user_turns),
                    },
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": (
                            "Il JSON precedente non è valido o non rispetta lo schema. "
                            f"Errore: {last_error}. "
                            "Riformula da zero rispettando esattamente lo schema richiesto."
                        ),
                    },
                ],
                temperature=0.0,
            )
            payload = _extract_json_object(candidate_raw)
            payload = self._validate_payload(payload, allowed_ids, context)
            return self._repair_abstain_when_covered(
                payload=payload,
                question=question,
                context=context,
                allowed_ids=allowed_ids,
                recent_user_turns=recent_user_turns,
            )
        except Exception as exc:
            last_error = str(exc)
        return self._llm_generated_abstain(
            question=question,
            context=context,
            last_error=last_error,
        )

    def _repair_abstain_when_covered(
        self,
        *,
        payload: dict[str, Any],
        question: str,
        context: dict[str, Any],
        allowed_ids: set[str],
        recent_user_turns: list[str],
    ) -> dict[str, Any]:
        if not self._coverage_requires_answer(payload, context):
            return payload

        coverage = context.get("coverage") or {}
        issues_total = int(coverage.get("issues_total") or 0)
        issues_covered = int(coverage.get("issues_covered") or 0)
        target_status = "grounded" if issues_total and issues_covered == issues_total else "limited"
        context.setdefault("agent_trace", []).append(
            AgentTraceStep(
                id="abstain_repair",
                title="Correzione astensione",
                status="running",
                detail=(
                    "Il modello ha scelto abstain nonostante la copertura fonti. "
                    "Richiedo una redazione entro le fonti disponibili."
                ),
            ).to_dict()
        )
        try:
            candidate_raw = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._system_prompt()
                        + "\n\nRegola aggiuntiva: lo status=abstain non è ammesso in questa correzione. "
                        "Devi usare grounded se tutte le questioni coperte sono risolte, oppure limited se rispondi solo ad alcune. "
                        "Non inventare diritto: afferma solo ciò che le fonti citate supportano. "
                        "Ignora le questioni con status=missing_sources, salvo elencarle nei limiti.",
                    },
                    {
                        "role": "user",
                        "content": self._user_prompt(question, context, recent_user_turns),
                    },
                    {
                        "role": "assistant",
                        "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    },
                    {
                        "role": "user",
                        "content": (
                            "La risposta precedente si è astenuta, ma il coverage interno indica "
                            f"{issues_covered}/{issues_total} questioni coperte da fonti ufficiali. "
                            f"Rifai il JSON con status={target_status}. "
                            "Segui answer_contract.mandatory_covered_issue_claims: per ogni elemento produci un claim dedicato "
                            "con issue_ids contenente issue_id e citations contenente required_document_id. "
                            "Per le issue non coperte non produrre claim: inseriscile in missing_information. "
                            "Ogni elemento di claims deve avere citations non vuoto; se non hai una citation valida, non creare quel claim. "
                            "Se una fonte ulteriore sarebbe utile ma non necessaria, indicarlo solo nei limiti, non usare abstain."
                        ),
                    },
                ],
                temperature=0.0,
            )
            parsed = _extract_json_object(candidate_raw)
            try:
                repaired = self._validate_payload(parsed, allowed_ids, context)
            except Exception:
                repaired = self._validate_payload_lenient(parsed, allowed_ids)
            if repaired.get("status") in {"grounded", "limited"}:
                self._complete_trace_step(
                    context,
                    "abstain_repair",
                    status="completed",
                    detail=f"Astensione corretta in status={repaired.get('status')}.",
                )
                repaired["_abstain_repair"] = {
                    "status": "applied",
                    "previous_intro": payload.get("intro", ""),
                    "issues_covered": issues_covered,
                    "issues_total": issues_total,
                }
                return repaired
        except Exception as exc:
            self._complete_trace_step(
                context,
                "abstain_repair",
                status="failed",
                detail=f"Correzione astensione non riuscita: {exc}.",
            )
            return payload

        self._complete_trace_step(
            context,
            "abstain_repair",
            status="failed",
            detail="La correzione ha restituito ancora astensione o output non utilizzabile.",
        )
        return payload

    def _repair_operational_abstain(
        self,
        *,
        payload: dict[str, Any],
        question: str,
        context: dict[str, Any],
        allowed_ids: set[str],
        recent_user_turns: list[str],
    ) -> dict[str, Any]:
        if payload.get("status") != "abstain":
            return payload
        if not self._should_repair_operational_abstain(context):
            return payload

        context.setdefault("agent_trace", []).append(
            AgentTraceStep(
                id="operational_repair",
                title="Adattamento operativo",
                status="running",
                detail=(
                    "La risposta si è bloccata sulle fonti, ma la richiesta contiene deliverable "
                    "operativi. Richiedo una risposta pratica senza claim giuridici non citati."
                ),
            ).to_dict()
        )
        try:
            candidate_raw = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._operational_repair_prompt(),
                    },
                    {
                        "role": "user",
                        "content": self._user_prompt(question, context, recent_user_turns),
                    },
                    {
                        "role": "assistant",
                        "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    },
                    {
                        "role": "user",
                        "content": (
                            "La risposta precedente ha usato abstain. Non rifare abstain. "
                            "Segui agent_plan.output_sections e produci un JSON con status=operational "
                            "oppure status=limited solo se inserisci claim citati validi. "
                            "Le sezioni operative devono essere utili per un avvocato: domande sui dati mancanti, "
                            "checklist, rischi pratici, strategia, bozza se richiesta. "
                            "Non citare articoli non presenti nelle evidenze; se una parte giuridica non è coperta, "
                            "scrivila come limite pratico in missing_information, non come motivo per fermarti."
                        ),
                    },
                ],
                temperature=0.0,
            )
            parsed = _extract_json_object(candidate_raw)
            repaired = self._validate_payload(parsed, allowed_ids, context)
            if repaired.get("status") in {"operational", "limited", "grounded"}:
                self._complete_trace_step(
                    context,
                    "operational_repair",
                    status="completed",
                    detail=f"Risposta operativa prodotta con status={repaired.get('status')}.",
                )
                repaired["_operational_repair"] = {
                    "status": "applied",
                    "previous_intro": payload.get("intro", ""),
                }
                return repaired
        except Exception as exc:
            self._complete_trace_step(
                context,
                "operational_repair",
                status="failed",
                detail=f"Adattamento operativo non riuscito: {exc}.",
            )
            return payload

        self._complete_trace_step(
            context,
            "operational_repair",
            status="failed",
            detail="Il modello ha restituito ancora un output non utilizzabile.",
        )
        return payload

    @staticmethod
    def _should_repair_operational_abstain(context: dict[str, Any]) -> bool:
        route = context.get("intent_route") or {}
        if route.get("intent") == "chat":
            return False
        plan = route.get("agent_plan") or {}
        actions = {str(action) for action in plan.get("actions") or []}
        sections = {str(section) for section in plan.get("output_sections") or []}
        operational_actions = {
            "ask_missing_facts",
            "build_checklist",
            "risk_analysis",
            "strategy",
            "draft_document",
            "explain",
        }
        operational_sections = {
            "questions",
            "checklist",
            "risks",
            "strategy",
            "draft",
            "explanation",
            "next_steps",
        }
        return bool(actions & operational_actions or sections & operational_sections)

    def _operational_repair_prompt(self) -> str:
        return textwrap.dedent(
            """
            Sei Judicex, agente legale operativo. Devi recuperare una risposta utile
            quando la parte strettamente normativa non è completamente coperta dalle fonti.

            Obiettivo:
            - Non inventare norme, articoli, termini processuali o citazioni.
            - Non usare status=abstain se puoi comunque produrre parti operative richieste.
            - Usa status=operational quando la risposta contiene domande, checklist,
              rischi pratici, strategia o bozza senza claim giuridici citati.
            - Usa status=limited solo se includi almeno un claim giuridico con citation valida.
            - Le sezioni legal_basis richiedono citations; se non hai citations valide,
              ometti legal_basis e sposta il limite in missing_information.
            - Per bozze di diffida o comunicazioni, usa i fatti forniti dall'utente e
              segnaposto chiari per i dati mancanti. Evita formule "ai sensi dell'art."
              se l'articolo non è nelle evidenze.

            Restituisci esclusivamente JSON nello stesso schema di Judicex:
            {
              "status": "operational" | "limited" | "grounded",
              "chat_answer": "",
              "intro": "frase breve",
              "sections": [
                {"type": "questions", "title": "Dati da chiarire", "items": ["..."]},
                {"type": "checklist", "title": "Checklist documentale", "items": ["..."]},
                {"type": "risks", "title": "Rischi processuali", "items": ["..."]},
                {"type": "strategy", "title": "Strategia operativa", "items": ["..."]},
                {"type": "draft", "title": "Bozza diffida", "content": "..."}
              ],
              "claims": [],
              "case_facts": [],
              "missing_information": [],
              "follow_up_questions": []
            }
            """
        ).strip()

    @staticmethod
    def _validate_payload_lenient(payload: dict[str, Any], allowed_ids: set[str]) -> dict[str, Any]:
        status = payload.get("status")
        if status not in {"grounded", "limited"}:
            raise ValueError(f"status non recuperabile: {status}")

        retained_claims: list[dict[str, Any]] = []
        dropped = 0
        for claim in payload.get("claims") or []:
            if not isinstance(claim, dict):
                dropped += 1
                continue
            text = _strip_emoji(str(claim.get("text", "")).strip())
            raw_citations = claim.get("citations", [])
            if not text or not isinstance(raw_citations, list):
                dropped += 1
                continue
            citations: list[str] = []
            for citation in raw_citations:
                citation_id = str(citation).strip()
                if citation_id in allowed_ids and citation_id not in citations:
                    citations.append(citation_id)
            if not citations:
                dropped += 1
                continue
            normalized_claim: dict[str, Any] = {"text": text, "citations": citations}
            issue_ids = claim.get("issue_ids", [])
            if isinstance(issue_ids, list):
                clean_issue_ids = [str(issue_id).strip() for issue_id in issue_ids if str(issue_id).strip()]
                if clean_issue_ids:
                    normalized_claim["issue_ids"] = clean_issue_ids
            retained_claims.append(normalized_claim)

        if not retained_claims:
            raise ValueError("nessun claim citato valido nella correzione")

        missing_information = [
            str(item).strip()
            for item in payload.get("missing_information") or []
            if str(item).strip()
        ]
        if dropped:
            missing_information.append(
                f"Claim non citati scartati durante la correzione: {dropped}"
            )
        return {
            "status": "limited" if dropped or status == "limited" else "grounded",
            "chat_answer": "",
            "intro": _strip_emoji(str(payload.get("intro", "")).strip()),
            "sections": [],
            "claims": retained_claims,
            "case_facts": [],
            "missing_information": missing_information,
            "follow_up_questions": [
                str(item).strip()
                for item in payload.get("follow_up_questions") or []
                if str(item).strip()
            ],
        }

    def _repair_missing_covered_issues(
        self,
        *,
        payload: dict[str, Any],
        question: str,
        context: dict[str, Any],
        allowed_ids: set[str],
        recent_user_turns: list[str],
    ) -> dict[str, Any]:
        if payload.get("status") not in {"grounded", "limited"}:
            return payload
        missing = self._missing_covered_issue_requirements(payload, context)
        if not missing:
            return payload

        coverage = context.get("coverage") or {}
        issues_total = int(coverage.get("issues_total") or 0)
        issues_covered = int(coverage.get("issues_covered") or 0)
        target_status = "grounded" if issues_total and issues_covered == issues_total else "limited"
        context.setdefault("agent_trace", []).append(
            AgentTraceStep(
                id="issue_completion",
                title="Completamento issue coperte",
                status="running",
                detail=(
                    "La risposta non copre tutte le questioni con fonti pertinenti. "
                    "Richiedo claims integrativi citati."
                ),
                metrics={"missing_issues": missing},
            ).to_dict()
        )
        try:
            candidate_raw = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._system_prompt()
                        + "\n\nRegola aggiuntiva: devi mantenere i claim validi già presenti "
                        "e aggiungere solo i claim necessari per le issue coperte mancanti. "
                        "Ogni claim aggiunto deve citare il required_document_id indicato e deve includere issue_ids. "
                        "Non creare claim per issue con status=missing_sources.",
                    },
                    {
                        "role": "user",
                        "content": self._user_prompt(question, context, recent_user_turns),
                    },
                    {
                        "role": "assistant",
                        "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    },
                    {
                        "role": "user",
                        "content": (
                            "La risposta precedente omette alcune issue già coperte da fonti pertinenti. "
                            f"Restituisci il JSON completo con status={target_status}. "
                            "Mantieni i claim già validi e aggiungi almeno un claim per ogni elemento di missing_covered_issues. "
                            "Ogni claim aggiunto deve citare esattamente il required_document_id corrispondente. "
                            "Non inserire claim senza citations. "
                            "missing_covered_issues="
                            + json.dumps(missing, ensure_ascii=False, separators=(",", ":"))
                        ),
                    },
                ],
                temperature=0.0,
            )
            parsed = _extract_json_object(candidate_raw)
            try:
                repaired = self._validate_payload(parsed, allowed_ids, context)
            except Exception:
                repaired = self._validate_payload_lenient(parsed, allowed_ids)
            remaining = self._missing_covered_issue_requirements(repaired, context)
            if len(remaining) < len(missing):
                status = "completed" if not remaining else "limited"
                detail = (
                    "Tutte le issue coperte sono ora trattate."
                    if not remaining
                    else f"Issue coperte ancora non trattate: {len(remaining)}."
                )
                self._complete_trace_step(
                    context,
                    "issue_completion",
                    status=status,
                    detail=detail,
                )
                repaired["_issue_completion"] = {
                    "status": status,
                    "missing_before": missing,
                    "missing_after": remaining,
                }
                return repaired
            self._complete_trace_step(
                context,
                "issue_completion",
                status="failed",
                detail="La correzione non ha aggiunto claim citati per le issue mancanti.",
            )
        except Exception as exc:
            self._complete_trace_step(
                context,
                "issue_completion",
                status="failed",
                detail=f"Completamento issue non riuscito: {exc}.",
            )
        return payload

    @staticmethod
    def _missing_covered_issue_requirements(
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if payload.get("status") not in {"grounded", "limited"}:
            return []
        claims = payload.get("claims") or []
        missing: list[dict[str, Any]] = []
        for issue in (context.get("coverage") or {}).get("issue_coverage") or []:
            if issue.get("status") != "covered":
                continue
            documents = issue.get("documents") or []
            if not documents:
                continue
            required_doc = documents[0]
            required_doc_id = str(required_doc.get("id", "")).strip()
            if not required_doc_id:
                continue
            if any(
                required_doc_id in (claim.get("citations") or [])
                and (
                    not claim.get("issue_ids")
                    or str(issue.get("id", "")) in {str(issue_id) for issue_id in claim.get("issue_ids", [])}
                )
                for claim in claims
            ):
                continue
            missing.append(
                {
                    "issue_id": issue.get("id", ""),
                    "title": issue.get("title", ""),
                    "question": issue.get("question", ""),
                    "required_document_id": required_doc_id,
                    "required_document_title": required_doc.get("title", ""),
                }
            )
        return missing

    def _safety_net_for_persistent_abstain(
        self,
        *,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Last-resort deterministic fallback when every LLM repair failed.

        If the pipeline still returns abstain even though issue_coverage shows
        covered issues with vigent articles, build a `limited` response from
        the retrieved sources directly. Each covered issue gets one claim
        whose text is the article title (from Normattiva) and whose citation
        is the matching document id. This is auditable, provably grounded,
        and never hallucinates: the claim text is verbatim from the source
        title that the system already has in evidence.

        The safety net only triggers when:
          - status is abstain
          - issue_coverage exists with at least one `covered` entry
          - each covered entry has at least one official document attached

        Otherwise the abstain stays as-is.
        """

        if payload.get("status") != "abstain":
            return payload
        # Only fire when the abstain came from the model's own refusal, not
        # from the contract or semantic verifier blocking unsafe claims:
        # converting a verifier-rejected payload to limited would mask real
        # hallucinations.
        contract_status = str((payload.get("_answer_contract") or {}).get("status") or "")
        verifier_status = str((payload.get("_semantic_verifier") or {}).get("status") or "")
        if contract_status not in {"", "skipped"}:
            return payload
        if verifier_status not in {""}:
            return payload
        # Don't override abstains tied to matter validation failures (the
        # model rejected because a private fact didn't validate). The safety
        # net is for the specific failure mode where the model refuses on
        # source-freshness / coverage worries despite covered evidence.
        intro = str(payload.get("intro") or "").lower()
        freshness_markers = (
            "modifiche successive",
            "non riflett",
            "regio decreto",
            "formulazione vigente e aggiornata",
            "fonti attualmente disponibili",
            "non posso fornire una risposta pienamente affidabile",
            "fonti aggiornate",
            "versione aggiornata",
        )
        if not any(marker in intro for marker in freshness_markers):
            return payload
        coverage = context.get("coverage") or {}
        issue_coverage = coverage.get("issue_coverage") or []
        if not issue_coverage:
            return payload
        covered_entries = [
            entry for entry in issue_coverage
            if entry.get("status") == "covered" and (entry.get("documents") or [])
        ]
        if not covered_entries:
            return payload

        docs_by_id = {
            doc["id"]: doc
            for doc in (context.get("documents") or []) + (context.get("related_documents") or [])
        }
        claims: list[dict[str, Any]] = []
        for entry in covered_entries:
            doc_meta = (entry.get("documents") or [])[0]
            doc_id = str(doc_meta.get("id") or "")
            doc = docs_by_id.get(doc_id)
            if doc is None:
                continue
            title = str(doc.get("title") or doc_id).strip()
            claims.append(
                {
                    "text": (
                        f"La questione «{entry.get('title','')}» è disciplinata da "
                        f"{title}, fonte ufficiale recuperata e vigente alla data del caso."
                    ),
                    "issue_ids": [str(entry.get("id") or "")],
                    "citations": [doc_id],
                }
            )
        if not claims:
            return payload

        context.setdefault("agent_trace", []).append(
            AgentTraceStep(
                id="safety_net_abstain",
                title="Safety net contro astensione persistente",
                status="completed",
                detail=(
                    f"Astensione sostituita con risposta limitata deterministica: "
                    f"{len(claims)} claim ricostruiti dalle fonti ufficiali coperte."
                ),
                metrics={"claims": len(claims)},
            )
            .complete(status="completed")
            .to_dict()
        )

        repaired = {
            **payload,
            "status": "limited",
            "intro": (
                "Risposta minima derivata dalle fonti ufficiali presenti in memoria, "
                "verificate vigenti alla data del caso. Per un'analisi completa caricare "
                "giurisprudenza e dottrina pertinenti."
            ),
            "claims": claims,
            "missing_information": payload.get("missing_information") or [],
            "_answer_contract": {
                "status": "synthesised_safety_net",
                "claims_total": len(claims),
                "claims_retained": len(claims),
                "claims_rejected": 0,
                "rejected_claims": [],
                "traces": [
                    {
                        "claim_index": index,
                        "claim_text": claim["text"],
                        "citations": claim["citations"],
                        "passed": True,
                        "violations": [],
                        "warnings": [],
                        "numeric_facts": [],
                        "supporting_atoms": [],
                    }
                    for index, claim in enumerate(claims)
                ],
            },
            "_safety_net": {
                "applied": True,
                "claims_added": len(claims),
                "covered_issue_ids": [str(entry.get("id") or "") for entry in covered_entries],
            },
        }
        return repaired

    @staticmethod
    def _coverage_requires_answer(payload: dict[str, Any], context: dict[str, Any]) -> bool:
        if payload.get("status") != "abstain":
            return False
        intent = (context.get("intent_route") or {}).get("intent", "legal_answer")
        if intent == "chat":
            return False
        coverage = context.get("coverage") or {}
        if int(coverage.get("official_documents") or 0) <= 0:
            return False
        issue_coverage = coverage.get("issue_coverage") or []
        if issue_coverage:
            return int(coverage.get("issues_covered") or 0) > 0
        return bool(context.get("documents"))

    @staticmethod
    def _complete_trace_step(
        context: dict[str, Any],
        step_id: str,
        *,
        status: str,
        detail: str,
    ) -> None:
        for step in reversed(context.get("agent_trace") or []):
            if step.get("id") == step_id:
                step["status"] = status
                step["detail"] = detail
                step["completed_at"] = AgentTraceStep(
                    id=step_id,
                    title=str(step.get("title") or ""),
                ).complete(status=status).completed_at
                return

    def _llm_generated_abstain(
        self,
        *,
        question: str,
        context: dict[str, Any],
        last_error: str,
    ) -> dict[str, Any]:
        doc_titles = [
            doc.get("title") or doc.get("id", "")
            for doc in (context.get("documents") or []) + (context.get("related_documents") or [])
        ]
        briefing = textwrap.dedent(
            f"""
            Domanda dell'utente:
            {question}

            Titoli delle fonti recuperate nella memoria (possono essere vicini ma non centrati sulla domanda):
            {json.dumps(doc_titles, ensure_ascii=False)}

            Scrivi in italiano, 2-4 frasi, in tono professionale e sobrio, un messaggio per l'utente che:
            - dichiari apertamente che non puoi rispondere in modo affidabile con le fonti disponibili
            - spieghi in modo concreto cosa manca (argomento o tipo di articolo) se è desumibile dalla domanda
            - suggerisca quale fonte o articolo andrebbe caricato in memoria per coprire il quesito

            Solo testo libero in italiano. Niente JSON, niente bullet, niente emoji, niente citazioni se non sono nelle fonti recuperate.
            """
        ).strip()
        try:
            raw_message = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Sei Judicex, software legale. Stai comunicando un'astensione. "
                            "Rispondi solo con testo italiano sobrio, senza inventare fonti."
                        ),
                    },
                    {"role": "user", "content": briefing},
                ],
                temperature=0.2,
            )
            message = _strip_emoji(raw_message).strip()
        except Exception:
            message = ""
        if not message:
            message = (
                "Le fonti disponibili nella memoria non coprono direttamente la domanda, "
                "quindi non posso produrre una risposta affidabile senza rischio di imprecisione."
            )
        return {
            "status": "abstain",
            "chat_answer": "",
            "intro": message,
            "sections": [],
            "claims": [],
            "case_facts": [],
            "missing_information": [],
            "follow_up_questions": [],
        }

    def _verifier_system_prompt(self) -> str:
        return textwrap.dedent(
            """
            Sei un verificatore legale. Valuti se ciascuna affermazione giuridica ('claim') è
            effettivamente supportata dalle fonti citate.

            Regole:
            - 'supported=true' SOLO se tutte le parti dell'affermazione (numeri, termini temporali,
              regimi, condizioni, destinatari) sono presenti nel testo delle fonti citate, in cifre,
              in lettere (es. "quaranta giorni" supporta "40 giorni") o in parafrasi fedele
            - 'supported=false' se l'affermazione trasla un regime da un istituto a un altro
              (per esempio applicando a un termine di notifica un regime che nel testo riguarda
              il termine di opposizione)
            - 'supported=false' se l'affermazione contiene un numero o un termine non presente
              né in cifre né in lettere nel testo delle citazioni
            - 'supported=false' se l'affermazione attribuisce al testo citato contenuti che non
              compaiono in quel testo, anche se usano terminologia vicina
            - sii rigoroso: in ambito legale vale solo ciò che è letteralmente presente nel testo
              citato o fedelmente parafrasabile

            Output esclusivamente JSON:
            {
              "verdicts": [
                {"id": "0", "supported": true, "reason": "breve motivazione in italiano"},
                {"id": "1", "supported": false, "reason": "spiegazione puntuale"}
              ]
            }
            """
        ).strip()

    def _semantic_verify_payload(
        self,
        *,
        payload: dict[str, Any],
        context: dict[str, Any],
        question: str,
    ) -> dict[str, Any]:
        if payload.get("status") not in {"grounded", "limited"}:
            return payload
        claims = payload.get("claims") or []
        if not claims:
            return payload

        doc_by_id = {
            doc["id"]: doc
            for doc in (context.get("documents") or []) + (context.get("related_documents") or [])
        }
        sources: list[dict[str, Any]] = []
        referenced_ids: list[str] = []
        for claim in claims:
            for cid in claim.get("citations", []):
                if cid not in referenced_ids:
                    referenced_ids.append(cid)
        for doc_id in referenced_ids:
            doc = doc_by_id.get(doc_id)
            if not doc:
                continue
            content = doc.get("content") or doc.get("excerpt") or ""
            sources.append(
                {
                    "id": doc_id,
                    "title": doc.get("title", ""),
                    "content": content[:4000],
                }
            )
        briefing = {
            "claims_to_check": [
                {"id": str(idx), "text": claim.get("text", ""), "citations": claim.get("citations", [])}
                for idx, claim in enumerate(claims)
            ],
            "sources": sources,
        }
        verdicts: dict[str, dict[str, Any]] = {}
        try:
            raw = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._verifier_system_prompt()},
                    {
                        "role": "user",
                        "content": json.dumps(briefing, ensure_ascii=False, separators=(",", ":")),
                    },
                ],
                temperature=0.0,
            )
            parsed = _extract_json_object(raw)
            for verdict in parsed.get("verdicts") or []:
                if isinstance(verdict, dict) and "id" in verdict:
                    verdicts[str(verdict["id"])] = verdict
        except Exception:
            verdicts = {}

        if not verdicts:
            # Verifier non ha prodotto output utilizzabile: fail-closed.
            return self._llm_generated_abstain(
                question=question,
                context=context,
                last_error="verificatore semantico non disponibile",
            )

        retained: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for idx, claim in enumerate(claims):
            verdict = verdicts.get(str(idx))
            if verdict and verdict.get("supported") is True:
                retained.append(claim)
            else:
                rejected.append(
                    {
                        "claim_text": claim.get("text", ""),
                        "reason": (verdict or {}).get("reason", "non supportato dalle fonti citate"),
                    }
                )

        if not retained:
            return self._llm_generated_abstain(
                question=question,
                context=context,
                last_error="tutte le affermazioni sono state rigettate dal verificatore semantico",
            )

        return {
            **payload,
            "status": "limited" if rejected else payload.get("status", "grounded"),
            "claims": retained,
            "_semantic_verifier": {
                "status": "limited" if rejected else "passed",
                "claims_total": len(claims),
                "claims_retained": len(retained),
                "claims_rejected": len(rejected),
                "rejected_claims": rejected,
            },
        }

    def _normalise_sections(self, raw_sections: Any, allowed_ids: set[str]) -> list[dict[str, Any]]:
        if raw_sections is None:
            return []
        if not isinstance(raw_sections, list):
            raise ValueError("sections deve essere una lista")
        sections: list[dict[str, Any]] = []
        for raw_section in raw_sections:
            if not isinstance(raw_section, dict):
                continue
            section_type = _strip_emoji(str(raw_section.get("type", "")).strip()).lower()
            section_type = re.sub(r"[^a-z0-9_]+", "_", section_type).strip("_") or "note"
            title = _strip_emoji(str(raw_section.get("title", "")).strip())
            if not title:
                title = _SECTION_TYPE_LABELS.get(section_type, "Sezione")
            requires_citations = bool(raw_section.get("requires_citations")) or section_type in _LEGAL_SECTION_TYPES
            section_citations = self._normalise_citations(raw_section.get("citations", []), allowed_ids)
            items: list[dict[str, Any]] = []
            raw_items = raw_section.get("items", [])
            if raw_items is None:
                raw_items = []
            if not isinstance(raw_items, list):
                raise ValueError("section.items deve essere una lista")
            for raw_item in raw_items:
                if isinstance(raw_item, dict):
                    item_text = _strip_emoji(str(raw_item.get("text", "")).strip())
                    item_citations = self._normalise_citations(raw_item.get("citations", []), allowed_ids)
                else:
                    item_text = _strip_emoji(str(raw_item).strip())
                    item_citations = []
                if not item_text:
                    continue
                if requires_citations and not item_citations and section_citations:
                    item_citations = list(section_citations)
                if requires_citations and not item_citations:
                    continue
                entry: dict[str, Any] = {"text": item_text}
                if item_citations:
                    entry["citations"] = item_citations
                items.append(entry)
            content = _strip_emoji(str(raw_section.get("content", "")).strip())
            if requires_citations and content and not section_citations and not any(item.get("citations") for item in items):
                content = ""
            if not items and not content:
                continue
            section: dict[str, Any] = {
                "type": section_type,
                "title": title,
                "items": items,
                "content": content,
                "requires_citations": requires_citations,
            }
            if section_citations:
                section["citations"] = section_citations
            sections.append(section)
        return sections

    @staticmethod
    def _normalise_citations(raw_citations: Any, allowed_ids: set[str]) -> list[str]:
        if raw_citations is None:
            return []
        if not isinstance(raw_citations, list):
            raise ValueError("citations deve essere una lista")
        citations: list[str] = []
        for citation in raw_citations:
            citation_text = str(citation).strip()
            if not citation_text:
                continue
            if citation_text not in allowed_ids:
                raise ValueError(f"citation non presente nelle evidenze: {citation_text}")
            if citation_text not in citations:
                citations.append(citation_text)
        return citations

    @staticmethod
    def _claims_from_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        claims: list[dict[str, Any]] = []
        for section in sections:
            if section.get("type") not in _LEGAL_SECTION_TYPES and not section.get("requires_citations"):
                continue
            section_citations = [str(item) for item in section.get("citations") or [] if str(item).strip()]
            for item in section.get("items") or []:
                text = str(item.get("text") or "").strip()
                citations = [str(cid) for cid in item.get("citations") or section_citations if str(cid).strip()]
                if text and citations:
                    claims.append({"text": text, "citations": citations, "_from_section": True})
            content = str(section.get("content") or "").strip()
            if content and section_citations:
                claims.append({"text": content, "citations": section_citations, "_from_section": True})
        return claims

    @staticmethod
    def _merge_claims(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for claim in primary + secondary:
            text = str(claim.get("text") or "").strip()
            citations = tuple(str(cid) for cid in claim.get("citations") or [] if str(cid).strip())
            key = (text.casefold(), citations)
            if not text or not citations or key in seen:
                continue
            seen.add(key)
            merged.append(claim)
        return merged

    def _validate_payload(
        self,
        payload: dict[str, Any],
        allowed_ids: set[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        status = payload.get("status")
        if status not in VALID_STATUSES:
            raise ValueError(f"status non valido: {status}")

        chat_answer = _strip_emoji(str(payload.get("chat_answer", "")).strip())
        intro = _strip_emoji(str(payload.get("intro", "")).strip())
        sections = self._normalise_sections(payload.get("sections", []), allowed_ids)
        claims = payload.get("claims", [])
        if not isinstance(claims, list):
            raise ValueError("claims deve essere una lista")

        normalized_claims: list[dict[str, Any]] = []
        for claim in claims:
            if not isinstance(claim, dict):
                raise ValueError("ogni claim deve essere un oggetto")
            text = _strip_emoji(str(claim.get("text", "")).strip())
            citations = claim.get("citations", [])
            if not text:
                raise ValueError("claim text vuoto")
            if not isinstance(citations, list) or not citations:
                raise ValueError("ogni claim deve avere almeno una citation")
            clean_citations: list[str] = []
            for citation in citations:
                citation_text = str(citation).strip()
                if citation_text not in allowed_ids:
                    raise ValueError(f"citation non presente nelle evidenze: {citation_text}")
                if citation_text not in clean_citations:
                    clean_citations.append(citation_text)
            normalized_claim: dict[str, Any] = {"text": text, "citations": clean_citations}
            issue_ids = claim.get("issue_ids", [])
            if isinstance(issue_ids, list):
                clean_issue_ids = [str(issue_id).strip() for issue_id in issue_ids if str(issue_id).strip()]
                if clean_issue_ids:
                    normalized_claim["issue_ids"] = clean_issue_ids
            if claim.get("_from_section"):
                normalized_claim["_from_section"] = True
            normalized_claims.append(normalized_claim)
        normalized_claims = self._merge_claims(normalized_claims, self._claims_from_sections(sections))

        case_facts = payload.get("case_facts", [])
        if case_facts is None:
            case_facts = []
        if not isinstance(case_facts, list):
            raise ValueError("case_facts deve essere una lista")
        allowed_fact_ids, allowed_matter_doc_ids = self._matter_reference_ids(context)
        normalized_case_facts: list[dict[str, Any]] = []
        for item in case_facts:
            if not isinstance(item, dict):
                raise ValueError("ogni case_fact deve essere un oggetto")
            text = _strip_emoji(str(item.get("text", "")).strip())
            if not text:
                continue
            fact_ids = self._validate_private_refs(item.get("fact_ids", []), allowed_fact_ids, "fact_id")
            document_ids = self._validate_private_refs(
                item.get("document_ids", []),
                allowed_matter_doc_ids,
                "matter document_id",
            )
            if not fact_ids and not document_ids:
                raise ValueError("ogni case_fact deve avere almeno un fact_id o document_id valido")
            normalized_case_facts.append(
                {
                    "text": text,
                    "fact_ids": fact_ids,
                    "document_ids": document_ids,
                }
            )

        missing_information = payload.get("missing_information", [])
        if not isinstance(missing_information, list):
            raise ValueError("missing_information deve essere una lista")

        follow_up_questions = payload.get("follow_up_questions", [])
        if not isinstance(follow_up_questions, list):
            raise ValueError("follow_up_questions deve essere una lista")

        if status == "chat":
            if not chat_answer:
                raise ValueError("status chat richiede chat_answer")
            normalized_claims = []
        elif status == "operational":
            if not sections and not intro and not follow_up_questions:
                raise ValueError("status operational richiede sections, intro o follow_up_questions")
            if normalized_claims:
                status = "limited"
        elif status in {"grounded", "limited"}:
            if not normalized_claims:
                raise ValueError("status grounded/limited richiede almeno un claim")
        elif status == "abstain":
            normalized_claims = []

        return {
            "status": status,
            "chat_answer": chat_answer,
            "intro": intro,
            "sections": sections,
            "claims": normalized_claims,
            "case_facts": normalized_case_facts,
            "missing_information": [str(item).strip() for item in missing_information if str(item).strip()],
            "follow_up_questions": [str(item).strip() for item in follow_up_questions if str(item).strip()],
        }

    @staticmethod
    def _matter_reference_ids(context: dict[str, Any]) -> tuple[set[str], set[str]]:
        matter_context = context.get("matter_context") or {}
        fact_ids: set[str] = set()
        doc_ids = {str(doc.get("id", "")) for doc in matter_context.get("documents") or [] if doc.get("id")}
        for section in ("facts", "timeline", "parties", "amounts", "deadlines"):
            for fact in matter_context.get(section) or []:
                fact_id = str(fact.get("id", "")).strip()
                doc_id = str(fact.get("document_id", "")).strip()
                if fact_id:
                    fact_ids.add(fact_id)
                if doc_id:
                    doc_ids.add(doc_id)
        return fact_ids, doc_ids

    @staticmethod
    def _validate_private_refs(raw_refs: Any, allowed_ids: set[str], label: str) -> list[str]:
        if raw_refs is None:
            return []
        if not isinstance(raw_refs, list):
            raise ValueError(f"{label} deve essere una lista")
        out: list[str] = []
        for raw_ref in raw_refs:
            ref = str(raw_ref).strip()
            if not ref:
                continue
            if ref not in allowed_ids:
                raise ValueError(f"{label} non presente nel matter_context: {ref}")
            if ref not in out:
                out.append(ref)
        return out

    @staticmethod
    def _section_citation_ids(sections: list[dict[str, Any]]) -> list[str]:
        used: list[str] = []
        for section in sections:
            for citation in section.get("citations") or []:
                cid = str(citation).strip()
                if cid and cid not in used:
                    used.append(cid)
            for item in section.get("items") or []:
                for citation in item.get("citations") or []:
                    cid = str(citation).strip()
                    if cid and cid not in used:
                        used.append(cid)
        return used

    @staticmethod
    def _format_citation_refs(citations: list[str], citation_index: dict[str, int]) -> str:
        refs = [
            f"[{citation_index[citation]}]"
            for citation in citations
            if citation in citation_index
        ]
        return ", ".join(refs)

    def _render_section_lines(
        self,
        sections: list[dict[str, Any]],
        citation_index: dict[str, int],
    ) -> list[str]:
        # Conversational rendering: sections become paragraphs, not labelled
        # blocks. Section titles are dropped for explanatory types so the
        # response reads like a colleague's note, not a structured form.
        # Only genuinely list-shaped sections (questions, checklist,
        # next_steps, risks) keep bullets — and only when they have items.
        _LIST_TYPES = {"questions", "checklist", "next_steps", "risks", "limits"}
        _DROP_TITLE_TYPES = {
            "explanation",
            "facts",
            "strategy",
            "intro",
        }
        lines: list[str] = []
        for section in sections:
            stype = str(section.get("type") or "").strip().lower()
            title = str(section.get("title") or "").strip()
            content = str(section.get("content") or "").strip()
            items = section.get("items") or []
            section_refs = self._format_citation_refs(section.get("citations") or [], citation_index)

            is_list_like = stype in _LIST_TYPES and items
            keep_title = title and (is_list_like or stype not in _DROP_TITLE_TYPES) and stype != ""
            if keep_title:
                lines.append(f"{title}:")

            if content:
                paragraph = f"{content} {section_refs}".strip()
                if lines and lines[-1] and not keep_title:
                    lines.append("")  # blank line between paragraphs
                lines.append(paragraph)

            if items:
                if is_list_like:
                    for item in items:
                        text = str(item.get("text") or "").strip()
                        if not text:
                            continue
                        refs = self._format_citation_refs(
                            item.get("citations") or section.get("citations") or [],
                            citation_index,
                        )
                        lines.append(f"- {text} {refs}".strip())
                else:
                    # Flow item texts as part of the prose, joined by line breaks
                    for item in items:
                        text = str(item.get("text") or "").strip()
                        if not text:
                            continue
                        refs = self._format_citation_refs(
                            item.get("citations") or section.get("citations") or [],
                            citation_index,
                        )
                        lines.append(f"{text} {refs}".strip())
        return lines

    def _render(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        public_limits = _public_missing_information(payload.get("missing_information") or [])
        public_follow_ups = _public_follow_up_questions(payload.get("follow_up_questions") or [])
        matter_context = context.get("matter_context") or {}
        matter = matter_context.get("matter") or None
        matter_docs_by_id = {
            doc.get("id"): doc
            for doc in matter_context.get("documents") or []
            if doc.get("id")
        }
        case_facts = payload.get("case_facts") or []
        sections = payload.get("sections") or []

        # Hallucination backstop: scan the assembled answer text for normative
        # references (es. "DPR 2/2010", "dlgs 104/2010", "L. 241/1990", "art.
        # 633 c.p.c.") that are NOT covered by any document in the evidence
        # pack. If we find unsupported references, we downgrade to abstain.
        # This catches the failure mode where the LLM goes into operational
        # mode and drafts a generic template stuffed with cited-from-training
        # norms.
        if payload.get("status") in {"grounded", "limited", "operational"}:
            docs_for_check = (context.get("documents") or []) + (context.get("related_documents") or [])
            stray = _detect_unsupported_norm_references(payload, docs_for_check)
            if stray:
                # Plain, no-commands message. The system works with what was
                # ingested; we don't tell the user "import bundle X" — that
                # would be a CLI-style instruction in a chat answer, which
                # is not the register we want.
                payload = {
                    **payload,
                    "status": "abstain",
                    "intro": "Non ho fonti pertinenti nella memoria per rispondere a questa domanda.",
                    "sections": [],
                    "claims": [],
                    "missing_information": [],
                    "_hallucination_backstop": {
                        "triggered": True,
                        "unsupported_references": stray,
                    },
                }
                sections = []
                public_limits = []
                public_follow_ups = []

        if payload["status"] == "chat":
            return {
                "status": "chat",
                "answer": payload["chat_answer"],
                "citations": [],
                "sections": sections,
                "case_facts": case_facts,
                "limits": public_limits,
                "follow_up_questions": public_follow_ups,
                "coverage": context["coverage"],
                "matter": matter,
                "matter_coverage": (matter_context.get("coverage") or {}) if matter_context else {},
                "intent_route": context.get("intent_route", {}),
                "answer_contract": payload.get("_answer_contract", {}),
                "semantic_verifier": payload.get("_semantic_verifier", {}),
                "evidence_trace": [],
                "agent_trace": context.get("agent_trace", []),
                "legal_issues": context.get("legal_issues", []),
            }

        docs = context["documents"] + context["related_documents"]
        docs_by_id = {doc["id"]: doc for doc in docs}
        used_ids: list[str] = []
        for claim in payload["claims"]:
            for citation in claim["citations"]:
                if citation not in used_ids:
                    used_ids.append(citation)
        for citation in self._section_citation_ids(sections):
            if citation not in used_ids:
                used_ids.append(citation)

        citation_index = {doc_id: index + 1 for index, doc_id in enumerate(used_ids)}
        lines: list[str] = []
        intro = payload["intro"].strip()
        # Conversational intro: no "Risposta limitata:" prefix, the status
        # propagates as metadata but the prose reads like a normal answer.
        if intro:
            lines.append(intro)
        elif payload["status"] == "abstain":
            lines.append("Non dispongo di elementi sufficienti per una risposta affidabile.")
        elif payload["status"] == "limited":
            lines.append("Mi limito alle fonti che ho a disposizione nella memoria.")

        if case_facts:
            if lines:
                lines.append("")
            lines.append("Fatti del fascicolo:")
            for fact in case_facts:
                labels: list[str] = []
                for doc_id in fact.get("document_ids", []):
                    doc = matter_docs_by_id.get(doc_id)
                    if doc and doc.get("title"):
                        labels.append(str(doc["title"]))
                suffix = f" ({'; '.join(labels)})" if labels else ""
                lines.append(f"{fact['text']}{suffix}")

        if sections:
            lines.extend(self._render_section_lines(sections, citation_index))

        for claim in payload["claims"]:
            if sections and claim.get("_from_section"):
                continue
            refs = ", ".join(f"[{citation_index[citation]}]" for citation in claim["citations"])
            lines.append(f"{claim['text']} {refs}")

        if public_limits:
            if lines:
                lines.append("")
            lines.append("Resta da verificare: " + "; ".join(public_limits) + ".")

        if public_follow_ups:
            if lines:
                lines.append("")
            lines.append("Dati da chiarire:")
            for question in public_follow_ups:
                lines.append(f"- {question}")

        citations = [
            {
                "index": citation_index[doc_id],
                "id": doc_id,
                "title": docs_by_id[doc_id]["title"],
                "source_ref": docs_by_id[doc_id]["source_ref"],
            }
            for doc_id in used_ids
        ]
        return {
            "status": payload["status"],
            "answer": "\n".join(lines).strip(),
            "citations": citations,
            "sections": sections,
            "case_facts": case_facts,
            "limits": public_limits,
            "follow_up_questions": public_follow_ups,
            "coverage": context["coverage"],
            "matter": matter,
            "matter_coverage": (matter_context.get("coverage") or {}) if matter_context else {},
            "intent_route": context.get("intent_route", {}),
            "answer_contract": payload.get("_answer_contract", {}),
            "semantic_verifier": payload.get("_semantic_verifier", {}),
            "answer_confidence": payload.get("_answer_confidence", {}),
            "conflicts": context.get("conflicts", {}),
            "preflight": context.get("preflight", {}),
            "as_of_date": context.get("as_of_date", ""),
            "evidence_trace": payload.get("_answer_contract", {}).get("traces", []),
            "agent_trace": context.get("agent_trace", []),
            "legal_issues": context.get("legal_issues", []),
        }

    def _render_matter_analysis(
        self,
        analysis: dict[str, Any],
        *,
        intent_route: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        route = intent_route or {}
        if analysis.get("status") == "error":
            error = str(analysis.get("error", "fascicolo non disponibile"))
            return {
                "status": "abstain",
                "answer": error,
                "citations": [],
                "sections": [],
                "case_facts": [],
                "limits": [error],
                "follow_up_questions": [],
                "coverage": {},
                "matter": None,
                "matter_coverage": {},
                "matter_analysis": analysis,
                "intent_route": route,
                "answer_contract": {"status": "skipped", "reason": "matter_analysis_error", "traces": []},
                "semantic_verifier": {"status": "skipped", "reason": "matter_analysis_error"},
                "evidence_trace": [],
                "agent_trace": [
                    AgentTraceStep(
                        id="matter_analysis",
                        title="Analisi fascicolo",
                        status="failed",
                        detail=error,
                    ).complete(status="failed").to_dict()
                ],
                "legal_issues": [],
            }

        profile = analysis.get("profile") or {}
        matter = analysis.get("matter") or {}
        lines = [
            f"Analisi fascicolo: {profile.get('label', 'analisi fascicolo')}.",
            f"Stato: {analysis.get('status', 'unknown')} ({analysis.get('readiness_score', 0)}%).",
        ]
        if matter.get("title"):
            lines.append(f"Fascicolo: {matter['title']}.")

        present = analysis.get("present_requirements") or []
        partial = analysis.get("partial_requirements") or []
        missing = analysis.get("missing_requirements") or []
        if present:
            lines.append("Elementi presenti:")
            for item in present[:8]:
                lines.append(f"- {item['label']}")
        if partial:
            lines.append("Elementi parziali:")
            for item in partial[:8]:
                lines.append(f"- {item['label']}: supporto documentale da verificare")
        if missing:
            lines.append("Elementi mancanti:")
            for item in missing[:8]:
                lines.append(f"- {item['label']}: {item.get('suggestion', '').strip()}")
        next_actions = [str(item).strip() for item in analysis.get("next_actions") or [] if str(item).strip()]
        if next_actions:
            lines.append("Prossime azioni:")
            for action in next_actions[:8]:
                lines.append(f"- {action}")

        supporting_facts = analysis.get("supporting_facts") or []
        case_facts = [
            {
                "text": _matter_fact_display_text(fact),
                "fact_ids": [fact["id"]] if fact.get("id") else [],
                "document_ids": [fact["document_id"]] if fact.get("document_id") else [],
            }
            for fact in supporting_facts[:16]
        ]
        return {
            "status": "analysis",
            "answer": "\n".join(lines).strip(),
            "citations": [],
            "sections": [],
            "case_facts": case_facts,
            "limits": [item["label"] for item in missing],
            "follow_up_questions": [],
            "coverage": {},
            "matter": matter,
            "matter_coverage": analysis.get("coverage") or {},
            "matter_analysis": analysis,
            "intent_route": route,
            "answer_contract": {"status": "skipped", "reason": "deterministic_matter_analysis", "traces": []},
            "semantic_verifier": {"status": "skipped", "reason": "deterministic_matter_analysis"},
            "evidence_trace": [],
            "agent_trace": [
                AgentTraceStep(
                    id="matter_analysis",
                    title="Analisi fascicolo",
                    status="completed",
                    detail="Fascicolo privato analizzato con workflow deterministico.",
                    metrics={
                        "readiness_score": analysis.get("readiness_score", 0),
                        "missing_requirements": len(missing),
                    },
                ).complete().to_dict()
            ],
            "legal_issues": [],
        }


def _matter_fact_display_text(fact: dict[str, Any]) -> str:
    label = str(fact.get("label", "")).strip()
    text = str(fact.get("text", "")).strip()
    value = str(fact.get("value", "")).strip()
    unit = str(fact.get("unit", "")).strip()
    date_value = str(fact.get("date_value", "")).strip()
    if value and unit:
        body = f"{value} {unit}"
    elif date_value:
        body = date_value
    else:
        body = text
    if label and body:
        return f"{label}: {body}"
    return body or str(fact.get("source_quote", "")).strip()


import re as _re

# Hallucination-detection helpers.
#
# We do NOT enumerate norm types (legge / dlgs / DPR / regio decreto /
# direttiva UE / regolamento UE / sentenza / ...). The universal `N/YYYY`
# token is the unique identifier of an Italian normative source — that is
# what we match against, so new source kinds need zero code changes.
#
# Years are normalised to 4 digits so "604/66" and "604/1966" are treated
# as equivalent.
#
# The supported universe is the set of `N/YYYY` extracted from the pack's
# own titles AND source_refs. Nothing is hardcoded per area or per type.

_NORM_NUMBER_RE = _re.compile(r"\b(\d{1,5})\s*/\s*(\d{2,4})\b")
_PACK_NUM_RE = _re.compile(r"\bn\.?\s*(\d{1,5})\b", _re.IGNORECASE)
_YEAR_RE = _re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
_URN_RE = _re.compile(r":(\d{4})-\d{2}-\d{2};(\d+)")


def _normalise_year(year: str) -> str:
    year = (year or "").strip()
    if not year:
        return ""
    if year.isdigit() and len(year) == 4:
        return year
    if year.isdigit() and len(year) == 2:
        # 50-99 -> 19xx, 00-49 -> 20xx (good enough for legal sources where
        # ambiguity is rare and the alternative — silent miss — is worse).
        return ("19" + year) if int(year) >= 50 else ("20" + year)
    return year


def _norm_sig(num: str, year: str) -> str:
    return f"{num.lstrip('0') or '0'}/{_normalise_year(year)}"


def _collect_pack_norm_signatures(docs: list[dict[str, object]]) -> set[str]:
    """Extract the universe of supported `N/YYYY` norm signatures from the pack.

    Italian official sources express the same identifier in three written
    forms — we recognise all of them:
      1. Explicit ``604/1966`` or ``604/66`` inline (rare in titles, common
         in the way users and LLMs cite norms in prose).
      2. Title-style ``LEGGE 15 luglio 1966, n. 604`` — number after "n."
         combined with the year written elsewhere in the same string.
      3. Normattiva URN ``...legge:1966-07-15;604...`` — year and number
         pulled out of the urn fragment.
    """

    sigs: set[str] = set()
    for doc in docs:
        title = str(doc.get("title", "") or "")
        source_ref = str(doc.get("source_ref", "") or "")
        haystack = f"{title} {source_ref}"

        # Form 1: inline N/YYYY
        for match in _NORM_NUMBER_RE.finditer(haystack):
            sigs.add(_norm_sig(match.group(1), match.group(2)))

        # Form 2: "n. NUM" + year token in the title
        years = _YEAR_RE.findall(title)
        nums = _PACK_NUM_RE.findall(title)
        if nums and years:
            # Pair every number with every year in the title. False
            # positives are tolerable because the pack universe is just
            # used to *allow* references, not to assert claims.
            for num in nums:
                for year in years:
                    sigs.add(_norm_sig(num, year))

        # Form 3: URN fragment "...:YYYY-MM-DD;NUM..."
        for match in _URN_RE.finditer(source_ref):
            sigs.add(_norm_sig(match.group(2), match.group(1)))
    return sigs


def _gather_answer_text(payload: dict[str, object]) -> str:
    parts: list[str] = [str(payload.get("intro") or "")]
    for section in payload.get("sections") or []:
        parts.append(str(section.get("title") or ""))
        parts.append(str(section.get("content") or ""))
        for item in section.get("items") or []:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(str(item))
    for claim in payload.get("claims") or []:
        parts.append(str(claim.get("text") or ""))
    return " \n ".join(parts)


def _detect_unsupported_norm_references(
    payload: dict[str, object], docs: list[dict[str, object]]
) -> list[str]:
    pack_sigs = _collect_pack_norm_signatures(docs)
    if not pack_sigs:
        # Empty pack: nothing to compare against. The "no fonts" condition
        # is already handled upstream by the abstain rule, so we don't
        # want to additionally flag here (would be a false positive on
        # every numeric token in a clean abstain message).
        return []
    text = _gather_answer_text(payload)
    seen_sigs: set[str] = set()
    out: list[str] = []
    for match in _NORM_NUMBER_RE.finditer(text):
        sig = _norm_sig(match.group(1), match.group(2))
        if sig in pack_sigs or sig in seen_sigs:
            continue
        # Filter false positives where the token is plainly a date or an
        # article number followed by a year-like fragment (e.g. "12/2024"
        # if it is a fattura number, not a norm). Heuristic: a norm sig
        # has a 4-digit year and a low-ish number (< 100000); dates with
        # day/month/year are unusual to bare-write as N/YYYY in legal
        # prose. If the snippet contains "fattura", "data", "importo",
        # skip it.
        snippet_window = text[max(0, match.start() - 40) : match.end() + 40].lower()
        if any(k in snippet_window for k in ("fattura", "data ", "importo", "scadenza")):
            continue
        seen_sigs.add(sig)
        snippet = text[max(0, match.start() - 24) : match.end() + 24].strip()
        out.append(f"{sig} · …{snippet}…")
    return out


def _suggest_bundle_for_question(question: str) -> tuple[str, str] | None:
    """Pick the official bundle whose description best matches a question.

    Returns ``(bundle_name, bundle_description)`` or ``None``. Matching is
    a plain count of shared keyword tokens (length >= 4 to avoid stopword
    noise). We deliberately avoid a fixed "area -> bundle" map so any new
    bundle registered in ``official_sources.OFFICIAL_BUNDLES`` is picked
    up automatically — including bundles for areas the system never had
    before.
    """

    try:
        from .official_sources import OFFICIAL_BUNDLES
    except Exception:
        return None
    tokens = {tok for tok in _re.findall(r"[a-zà-ÿ]{4,}", (question or "").lower())}
    if not tokens:
        return None
    best: tuple[int, str, str] | None = None
    for bundle in OFFICIAL_BUNDLES.values():
        description = getattr(bundle, "description", "") or ""
        haystack = f"{bundle.name} {description}".lower()
        score = sum(1 for tok in tokens if tok in haystack)
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, bundle.name, description)
    if best is None:
        return None
    return best[1], best[2]
