from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from judicex_memory_os.store import LegalMemoryStore


DEMO_TEXT = """Alfa Corp issued invoice no. 42 on January 15, 2026 for $8,500.00 to Beta LLC.

The invoice was due by February 15, 2026.
Beta LLC has failed to make payment. Alfa Corp sent a written payment reminder on February 28, 2026 and a formal default notice on March 10, 2026.
The contract stipulates statutory interest and late penalties.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Judicex English demo database.")
    parser.add_argument("--db", default="./memory.demo.db")
    args = parser.parse_args()

    db_path = Path(args.db)
    with LegalMemoryStore(db_path) as store:
        matter = store.create_matter(
            "Debt Recovery Demo (Alfa v. Beta)",
            client_name="Alfa Corp",
            area="civil",
            summary="Sample matter file to test Judicex without sensitive client data.",
        )
        folder = store.create_matter_folder(matter["id"], "Demo Documents")
        document = store.add_matter_document(
            matter["id"],
            title="Debt Recovery Memorandum - Alfa & Beta",
            kind="memo",
            content=DEMO_TEXT,
            metadata={"folder_id": folder.get("id", "")},
        )["document"]
        review = store.create_tabular_review(matter["id"], title="Debt Review", query="invoice payment")
        store.save_tabular_review_view(
            review["id"],
            name="Amounts and Deadlines View",
            filter_text="",
            sort_key="document",
            columns=review.get("columns") or [],
        )
        store.create_custom_workflow_pack(
            label="Debt Recovery Workflow",
            match_terms=["debt recovery", "payment order", "invoice", "recupero credito"],
            requirements=[
                {
                    "id": "invoice",
                    "label": "Invoice or Proof of Debt",
                    "fact_terms": ["invoice", "amount", "fattura"],
                    "document_terms": ["invoice", "debt", "amount", "credito"],
                    "required": True,
                    "suggestion": "Upload invoice, statement of account, or contract.",
                },
                {
                    "id": "notice_of_default",
                    "label": "Demand Letter or Default Notice",
                    "fact_terms": ["demand", "reminder", "notice", "diffida"],
                    "document_terms": ["demand", "notice", "default", "sollecito"],
                    "required": False,
                    "suggestion": "Upload demand letter or record date of payment reminder.",
                },
            ],
        )
        store.save_custom_draft_template(
            title="Formal Payment Demand Letter",
            name="formal_demand_letter_demo",
            body=(
                "To: {debtor}\n\n"
                "Please be advised that {creditor} hereby demands immediate payment of ${amount} "
                "due by {deadline}, reserving all rights and legal remedies.\n"
            ),
            required_params=["creditor", "debtor", "amount", "deadline"],
        )
        print(
            f"Demo created in {db_path}. Matter: {matter['id']}. Document: {document['id']}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
