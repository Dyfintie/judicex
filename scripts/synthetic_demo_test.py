#!/usr/bin/env python3
"""Synthetic Demo Test for Judicex Legal OS.

Demonstrates the core lifecycle:
1. Initializing legal memory store and private matter.
2. Ingesting factual evidence documents.
3. Extracting structured case facts (parties, dates, amounts, deadlines).
4. Performing deterministic workflow analysis against legal proof profiles.
5. Executing live AI answering with Groq in English.
6. Generating an official legal draft notice.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from judicex_memory_os.agent_runtime import JudicexAgentRuntime
from judicex_memory_os.llm_provider import default_settings, make_client, normalize_settings
from judicex_memory_os.store import LegalMemoryStore


DEMO_CONTRACT = """Commercial Supply & Services Agreement
Date: January 15, 2026
Parties:
- Claimant / Creditor: Alfa Corp (Delaware, USA)
- Respondent / Debtor: Beta LLC (New York, USA)

Terms:
1. Alfa Corp agrees to provide enterprise cloud infrastructure services for $8,500.00.
2. Payment is strictly due within 30 days of invoice issuance (Due Date: February 15, 2026).
3. In case of payment default, statutory interest at 5% per annum shall apply immediately upon notice.
"""

DEMO_DEMAND_LETTER = """Formal Demand Notice & Notice of Default
Date: March 10, 2026
To: Beta LLC

Please be formally advised that Invoice #42 for the principal sum of $8,500.00 remains past due since February 15, 2026.
Alfa Corp hereby demands full settlement of the outstanding principal together with accrued interest within seven (7) business days.
Failure to remit payment will result in immediate commencement of formal debt recovery and injunctive relief proceedings.
"""


def run_synthetic_demo() -> None:
    print("=" * 70)
    print("⚖️  JUDICEX LEGAL MEMORY OS — SYNTHETIC DEMO TEST")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "demo_synthetic.db"

        with LegalMemoryStore(db_path) as store:
            print("\n[Step 1] Initializing Private Matter File...")
            matter = store.create_matter(
                title="Commercial Debt Recovery - Alfa Corp v. Beta LLC",
                client_name="Alfa Corp",
                area="civil",
                summary="Breach of commercial supply contract for non-payment of $8,500.00 invoice.",
            )
            print(f" ✓ Matter Created: {matter['title']} (ID: {matter['id']})")

            print("\n[Step 2] Ingesting Matter Exhibits & Documents...")
            folder = store.create_matter_folder(matter["id"], "Contract & Pleadings")
            doc1 = store.add_matter_document(
                matter["id"],
                title="Commercial Supply Agreement (Jan 2026)",
                kind="contract",
                content=DEMO_CONTRACT,
                metadata={"folder_id": folder.get("id", "")},
            )["document"]
            doc2 = store.add_matter_document(
                matter["id"],
                title="Formal Demand & Default Notice (Mar 2026)",
                kind="notice",
                content=DEMO_DEMAND_LETTER,
                metadata={"folder_id": folder.get("id", "")},
            )["document"]
            print(f" ✓ Attached: {doc1['title']} ({doc1['id']})")
            print(f" ✓ Attached: {doc2['title']} ({doc2['id']})")

            print("\n[Step 3] Extracting Deterministic Case Facts...")
            facts = store.build_matter_context(matter["id"]).get("facts", [])
            print(f" ✓ Total Facts Extracted: {len(facts)}")
            for fact in facts[:5]:
                print(f"   • [{fact['fact_type'].upper()}] {fact['label']}: {fact['value']}")

            print("\n[Step 4] Running Matter Workflow Analysis against Proof Profile...")
            analysis = store.analyze_matter(
                matter["id"],
                thesis="debt recovery and payment order injunction",
            )
            profile_label = analysis["profile"]["label"]
            readiness = analysis.get("readiness_score", 1.0)
            print(f" ✓ Profile Matched: {profile_label}")
            print(f" ✓ Evidentiary Readiness Score: {int(readiness * 100)}%")
            print("   Requirements Status:")
            for req in analysis["requirements"]:
                status_icon = "✅" if req["status"] == "satisfied" else "⚠️"
                print(f"   {status_icon} {req['label']}: {req['status']}")

            print("\n[Step 5] Querying AI Agent with Groq LLM (English)...")
            settings = normalize_settings(default_settings())
            client = make_client(settings)
            runtime = JudicexAgentRuntime(
                store=store,
                client=client,
                model=settings["model"],
                area="civil",
                matter_id=matter["id"],
            )

            question = "What is the status of this debt recovery matter and what are our immediate next actions?"
            print(f" User Query: \"{question}\"")
            response = runtime.answer(question)

            print(f" ✓ Provider: {settings.get('provider_label')} ({settings.get('model')})")
            print(f" ✓ Status: {response.get('status')}")
            answer_text = response.get("answer") or response.get("intro") or ""
            print("\n--- AI Response ---")
            print(answer_text.strip()[:600] + ("..." if len(answer_text) > 600 else ""))

            if response.get("sections"):
                print("\nGenerated Structured Sections:")
                for sec in response["sections"]:
                    print(f"   📌 {sec.get('title')} ({sec.get('type')})")

            print("\n[Step 6] Rendering Formal Legal Draft Template...")
            draft_template = store.save_custom_draft_template(
                title="Notice Before Legal Action",
                name="notice_before_action",
                body=(
                    "FINAL DEMAND NOTICE BEFORE LEGAL ACTION\n\n"
                    "TO: {debtor}\n"
                    "FROM: {creditor}\n"
                    "AMOUNT DUE: ${amount}\n\n"
                    "Take notice that unless the aforementioned principal sum is paid in full "
                    "within 5 days, proceedings for an injunction and payment order will be initiated.\n"
                ),
                required_params=["debtor", "creditor", "amount"],
            )
            rendered_draft = draft_template["body"].format(
                debtor="Beta LLC",
                creditor="Alfa Corp",
                amount="8,500.00",
            )
            print(" ✓ Draft Template Instantiated:")
            for line in rendered_draft.strip().splitlines()[:6]:
                print(f"   | {line}")

    print("\n" + "=" * 70)
    print("✅  SYNTHETIC DEMO TEST PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_synthetic_demo()
