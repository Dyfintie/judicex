from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from judicex_memory_os.store import LegalMemoryStore


DEMO_TEXT = """Alfa S.r.l. ha emesso fattura n. 42 del 15 gennaio 2026 per Euro 8.500,00 nei confronti di Beta S.r.l.

La fattura doveva essere pagata entro il 15 febbraio 2026.
Beta S.r.l. non ha pagato. Alfa S.r.l. ha inviato sollecito scritto il 28 febbraio 2026 e diffida il 10 marzo 2026.
Il contratto prevede foro di Milano e interessi moratori in caso di ritardo.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a fake Judicex demo database.")
    parser.add_argument("--db", default="./memory.demo.db")
    args = parser.parse_args()

    db_path = Path(args.db)
    with LegalMemoryStore(db_path) as store:
        matter = store.create_matter(
            "Demo recupero credito",
            client_name="Alfa S.r.l.",
            area="civile",
            summary="Fascicolo fittizio per provare Judicex senza dati privati.",
        )
        folder = store.create_matter_folder(matter["id"], "Documenti demo")
        document = store.add_matter_document(
            matter["id"],
            title="Promemoria credito Alfa Beta",
            kind="memo",
            content=DEMO_TEXT,
            metadata={"folder_id": folder.get("id", "")},
        )["document"]
        review = store.create_tabular_review(matter["id"], title="Review credito", query="fattura pagamento")
        store.save_tabular_review_view(
            review["id"],
            name="Vista importi e scadenze",
            filter_text="",
            sort_key="document",
            columns=review.get("columns") or [],
        )
        store.create_custom_workflow_pack(
            label="Demo recupero credito",
            match_terms=["recupero credito", "decreto ingiuntivo", "fattura"],
            requirements=[
                {
                    "id": "fattura",
                    "label": "Fattura o prova del credito",
                    "fact_terms": ["fattura", "importo"],
                    "document_terms": ["fattura", "euro", "credito"],
                    "required": True,
                    "suggestion": "Caricare fattura, estratto conto o contratto.",
                },
                {
                    "id": "messa_in_mora",
                    "label": "Sollecito o diffida",
                    "fact_terms": ["diffida", "sollecito"],
                    "document_terms": ["diffida", "sollecito", "mora"],
                    "required": False,
                    "suggestion": "Caricare la diffida o indicare la data del sollecito.",
                },
            ],
        )
        store.save_custom_draft_template(
            title="Diffida pagamento demo",
            name="diffida_pagamento_demo",
            body=(
                "Spett.le {debitore},\n\n"
                "Con la presente {creditore} Vi invita al pagamento di Euro {importo} "
                "entro {termine}, salvo ogni diritto.\n"
            ),
            required_params=["creditore", "debitore", "importo", "termine"],
        )
        print(
            f"Demo creata in {db_path}. Matter: {matter['id']}. Documento: {document['id']}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
