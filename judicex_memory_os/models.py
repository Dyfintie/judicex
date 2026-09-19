from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

JsonDict = dict[str, Any]


@dataclass(slots=True)
class Document:
    id: str
    title: str
    kind: str
    area: str
    content: str
    source_type: str = "official"
    source_ref: str = ""
    authority: str = ""
    effective_from: str = ""
    effective_to: str = ""
    metadata: JsonDict = field(default_factory=dict)


@dataclass(slots=True)
class Entity:
    id: str
    name: str
    kind: str
    area: str
    summary: str
    metadata: JsonDict = field(default_factory=dict)


@dataclass(slots=True)
class Edge:
    id: str
    source_id: str
    target_id: str
    relation: str
    weight: float = 1.0
    summary: str = ""
    metadata: JsonDict = field(default_factory=dict)


@dataclass(slots=True)
class LegalAtom:
    id: str
    document_id: str
    document_version_id: str
    area: str
    atom_type: str
    subject: str
    action: str
    value: str = ""
    unit: str = ""
    temporal_anchor: str = ""
    condition_text: str = ""
    source_quote: str = ""
    confidence: float = 1.0
    metadata: JsonDict = field(default_factory=dict)


@dataclass(slots=True)
class Matter:
    id: str
    title: str
    client_name: str = ""
    area: str = ""
    status: str = "open"
    summary: str = ""
    metadata: JsonDict = field(default_factory=dict)


@dataclass(slots=True)
class MatterDocument:
    id: str
    matter_id: str
    title: str
    kind: str
    content: str
    source_path: str = ""
    content_sha256: str = ""
    metadata: JsonDict = field(default_factory=dict)


@dataclass(slots=True)
class MatterFact:
    id: str
    matter_id: str
    document_id: str
    fact_type: str
    label: str
    text: str
    value: str = ""
    unit: str = ""
    date_value: str = ""
    confidence: float = 1.0
    source_quote: str = ""
    metadata: JsonDict = field(default_factory=dict)
