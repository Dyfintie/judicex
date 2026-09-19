from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import Document


NORMATTIVA_API_BASE = "https://api.normattiva.it/t/normattiva.api"
NORMATTIVA_DETAIL_URN_PATH = "/bff-opendata/v1/api/v1/atto/dettaglio-atto-urn"
NORMATTIVA_PORTAL_BASE = "https://www.normattiva.it/uri-res/N2Ls?"


@dataclass(frozen=True)
class BundleItem:
    key: str
    area: str
    urn_candidates: tuple[str, ...]
    kind: str = "norma"


@dataclass(frozen=True)
class Bundle:
    name: str
    description: str
    items: tuple[BundleItem, ...]


OFFICIAL_BUNDLES: dict[str, Bundle] = {
    "lavoro_core": Bundle(
        name="lavoro_core",
        description=(
            "Nucleo ufficiale per licenziamento individuale: Statuto Lavoratori artt. 7, 18, 19, 28; "
            "c.c. artt. 2118, 2119; L. 604/1966 artt. 1, 2, 3, 5, 8 (licenziamenti individuali); "
            "Riforma Fornero L. 92/2012 art. 1; Jobs Act dlgs 23/2015 artt. 1, 2, 3, 9; "
            "Cost. artt. 4, 24, 35, 36."
        ),
        items=(
            # Statuto Lavoratori (L. 300/1970)
            BundleItem(
                key="statuto_art7",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:legge:1970-05-20;300~art7!vig={as_of}",
                    "urn:nir:stato:legge:1970-05-20;300~art7",
                ),
            ),
            BundleItem(
                key="statuto_art18",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:legge:1970-05-20;300~art18!vig={as_of}",
                    "urn:nir:stato:legge:1970-05-20;300~art18",
                ),
            ),
            BundleItem(
                key="statuto_art19",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:legge:1970-05-20;300~art19!vig={as_of}",
                    "urn:nir:stato:legge:1970-05-20;300~art19",
                ),
            ),
            BundleItem(
                key="statuto_art28",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:legge:1970-05-20;300~art28!vig={as_of}",
                    "urn:nir:stato:legge:1970-05-20;300~art28",
                ),
            ),
            # Codice civile
            BundleItem(
                key="codice_civile_art2118",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2118!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2118",
                ),
            ),
            BundleItem(
                key="codice_civile_art2119",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2119!vig={as_of}",
                    "urn:nir:stato:codice.civile:1942-03-16;262~art2119!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2119",
                ),
            ),
            # Licenziamenti individuali (L. 604/1966)
            BundleItem(
                key="licenziamenti_art1",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:legge:1966-07-15;604~art1!vig={as_of}",
                    "urn:nir:stato:legge:1966-07-15;604~art1",
                ),
            ),
            BundleItem(
                key="licenziamenti_art2",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:legge:1966-07-15;604~art2!vig={as_of}",
                    "urn:nir:stato:legge:1966-07-15;604~art2",
                ),
            ),
            BundleItem(
                key="licenziamenti_art3",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:legge:1966-07-15;604~art3!vig={as_of}",
                    "urn:nir:stato:legge:1966-07-15;604~art3",
                ),
            ),
            BundleItem(
                key="licenziamenti_art5",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:legge:1966-07-15;604~art5!vig={as_of}",
                    "urn:nir:stato:legge:1966-07-15;604~art5",
                ),
            ),
            BundleItem(
                key="licenziamenti_art6",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:legge:1966-07-15;604~art6!vig={as_of}",
                    "urn:nir:stato:legge:1966-07-15;604~art6",
                ),
            ),
            BundleItem(
                key="licenziamenti_art8",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:legge:1966-07-15;604~art8!vig={as_of}",
                    "urn:nir:stato:legge:1966-07-15;604~art8",
                ),
            ),
            # Riforma Fornero (L. 92/2012, art. 1 commi sul licenziamento)
            BundleItem(
                key="fornero_art1",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:legge:2012-06-28;92~art1!vig={as_of}",
                    "urn:nir:stato:legge:2012-06-28;92~art1",
                ),
            ),
            # Jobs Act tutele crescenti (dlgs 23/2015)
            BundleItem(
                key="jobs_act_art1",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:decreto.legislativo:2015-03-04;23~art1!vig={as_of}",
                    "urn:nir:stato:decreto.legislativo:2015-03-04;23~art1",
                ),
            ),
            BundleItem(
                key="jobs_act_art2",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:decreto.legislativo:2015-03-04;23~art2!vig={as_of}",
                    "urn:nir:stato:decreto.legislativo:2015-03-04;23~art2",
                ),
            ),
            BundleItem(
                key="jobs_act_art3",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:decreto.legislativo:2015-03-04;23~art3!vig={as_of}",
                    "urn:nir:stato:decreto.legislativo:2015-03-04;23~art3",
                ),
            ),
            BundleItem(
                key="jobs_act_art9",
                area="lavoro",
                urn_candidates=(
                    "urn:nir:stato:decreto.legislativo:2015-03-04;23~art9!vig={as_of}",
                    "urn:nir:stato:decreto.legislativo:2015-03-04;23~art9",
                ),
            ),
            # Costituzione (diritti fondamentali del lavoro)
            BundleItem(
                key="costituzione_art4",
                area="costituzionale",
                urn_candidates=(
                    "urn:nir:stato:costituzione:1947-12-27~art4!vig={as_of}",
                    "urn:nir:stato:costituzione:1947-12-27~art4",
                ),
            ),
            BundleItem(
                key="costituzione_art24",
                area="costituzionale",
                urn_candidates=(
                    "urn:nir:stato:costituzione:1947-12-27~art24!vig={as_of}",
                    "urn:nir:stato:costituzione:1947-12-27~art24",
                ),
            ),
            BundleItem(
                key="costituzione_art35",
                area="costituzionale",
                urn_candidates=(
                    "urn:nir:stato:costituzione:1947-12-27~art35!vig={as_of}",
                    "urn:nir:stato:costituzione:1947-12-27~art35",
                ),
            ),
            BundleItem(
                key="costituzione_art36",
                area="costituzionale",
                urn_candidates=(
                    "urn:nir:stato:costituzione:1947-12-27~art36!vig={as_of}",
                    "urn:nir:stato:costituzione:1947-12-27~art36",
                ),
            ),
        ),
    ),
    "civile_recupero_crediti": Bundle(
        name="civile_recupero_crediti",
        description=(
            "Nucleo ufficiale minimo per il procedimento monitorio (decreto ingiuntivo): "
            "c.p.c. artt. 633, 634, 641, 642, 645, 647, 648 e c.c. artt. 1218, 1219, 2697."
        ),
        items=(
            BundleItem(
                key="cpc_art633",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art633!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art633",
                ),
            ),
            BundleItem(
                key="cpc_art634",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art634!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art634",
                ),
            ),
            BundleItem(
                key="cpc_art641",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art641!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art641",
                ),
            ),
            BundleItem(
                key="cpc_art642",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art642!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art642",
                ),
            ),
            BundleItem(
                key="cpc_art645",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art645!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art645",
                ),
            ),
            BundleItem(
                key="cpc_art647",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art647!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art647",
                ),
            ),
            BundleItem(
                key="cpc_art648",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art648!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art648",
                ),
            ),
            BundleItem(
                key="cc_art1218",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art1218!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art1218",
                ),
            ),
            BundleItem(
                key="cc_art1219",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art1219!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art1219",
                ),
            ),
            BundleItem(
                key="cc_art2697",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2697!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2697",
                ),
            ),
            BundleItem(
                key="cpc_art635",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art635!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art635",
                ),
            ),
            BundleItem(
                key="cpc_art637",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art637!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art637",
                ),
            ),
            BundleItem(
                key="cpc_art638",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art638!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art638",
                ),
            ),
            BundleItem(
                key="cpc_art643",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art643!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art643",
                ),
            ),
            BundleItem(
                key="cpc_art644",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art644!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art644",
                ),
            ),
            BundleItem(
                key="cpc_art649",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art649!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art649",
                ),
            ),
            BundleItem(
                key="cpc_art650",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art650!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art650",
                ),
            ),
            BundleItem(
                key="cpc_art653",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art653!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art653",
                ),
            ),
            BundleItem(
                key="cpc_art654",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art654!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art654",
                ),
            ),
            BundleItem(
                key="cc_art1282",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art1282!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art1282",
                ),
            ),
            BundleItem(
                key="cc_art1284",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art1284!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art1284",
                ),
            ),
            BundleItem(
                key="cc_art2946",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2946!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2946",
                ),
            ),
            BundleItem(
                key="cc_art2948",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2948!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2948",
                ),
            ),
        ),
    ),
    "locazioni_sfratto": Bundle(
        name="locazioni_sfratto",
        description=(
            "Nucleo ufficiale per locazioni e sfratto per morosità: c.p.c. artt. 658, 660, "
            "663, 664, 665, 666; L. 392/1978 artt. 5, 27, 55 (gravità inadempimento, "
            "durata non abitative, sanatoria); c.c. artt. 1571, 1587, 1591."
        ),
        items=(
            BundleItem(
                key="cpc_art658",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art658!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art658",
                ),
            ),
            BundleItem(
                key="cpc_art660",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art660!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art660",
                ),
            ),
            BundleItem(
                key="cpc_art663",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art663!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art663",
                ),
            ),
            BundleItem(
                key="cpc_art664",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art664!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art664",
                ),
            ),
            BundleItem(
                key="cpc_art665",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art665!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art665",
                ),
            ),
            BundleItem(
                key="cpc_art666",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art666!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1940-10-28;1443:1~art666",
                ),
            ),
            BundleItem(
                key="legge392_art5",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:legge:1978-07-27;392~art5!vig={as_of}",
                    "urn:nir:stato:legge:1978-07-27;392~art5",
                ),
            ),
            BundleItem(
                key="legge392_art27",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:legge:1978-07-27;392~art27!vig={as_of}",
                    "urn:nir:stato:legge:1978-07-27;392~art27",
                ),
            ),
            BundleItem(
                key="legge392_art55",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:legge:1978-07-27;392~art55!vig={as_of}",
                    "urn:nir:stato:legge:1978-07-27;392~art55",
                ),
            ),
            BundleItem(
                key="cc_art1571",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art1571!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art1571",
                ),
            ),
            BundleItem(
                key="cc_art1587",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art1587!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art1587",
                ),
            ),
            BundleItem(
                key="cc_art1591",
                area="civile",
                urn_candidates=(
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art1591!vig={as_of}",
                    "urn:nir:stato:regio.decreto:1942-03-16;262:2~art1591",
                ),
            ),
        ),
    ),
    "costituzione_core": Bundle(
        name="costituzione_core",
        description=(
            "Costituzione italiana — diritti fondamentali e garanzie processuali rilevanti per il "
            "lavoro forense: artt. 2, 3, 24, 25, 27, 32, 36-41, 97, 101, 111, 113."
        ),
        items=tuple(
            BundleItem(
                key=f"costituzione_art{n}",
                area="costituzionale",
                urn_candidates=(
                    f"urn:nir:stato:costituzione:1947-12-27~art{n}!vig={{as_of}}",
                    f"urn:nir:stato:costituzione:1947-12-27~art{n}",
                ),
            )
            for n in (2, 3, 13, 24, 25, 27, 29, 32, 36, 37, 38, 39, 40, 41, 42, 47, 97, 101, 111, 113)
        ),
    ),
    "penale_base": Bundle(
        name="penale_base",
        description=(
            "Codice penale — parte generale: principio di legalità e personalità (artt. 1, 2, 3, 4), "
            "elemento soggettivo (42, 43), tentativo (56), concorso (110-119), imputabilità (85-90), "
            "circostanze (61-62-bis), pena (132-133). Da estendere con parte speciale per area."
        ),
        items=tuple(
            BundleItem(
                key=f"cp_art{n}",
                area="penale",
                urn_candidates=(
                    f"urn:nir:stato:regio.decreto:1930-10-19;1398~art{n}!vig={{as_of}}",
                    f"urn:nir:stato:regio.decreto:1930-10-19;1398~art{n}",
                ),
            )
            for n in (1, 2, 3, 4, 27, 42, 43, 56, 85, 110, 111, 112, 113, 114, 115, 132, 133)
        ),
    ),
    "tributario_core": Bundle(
        name="tributario_core",
        description=(
            "Nucleo tributario: TUIR (DPR 917/86) artt. 1-3, 8-13, 49, 81; DPR 633/72 IVA artt. 1, 17, 21; "
            "dlgs 472/97 sanzioni artt. 5, 6, 7; statuto contribuente L. 212/2000 artt. 3, 7, 10."
        ),
        items=tuple(
            [
                BundleItem(
                    key=f"tuir_art{n}",
                    area="tributario",
                    urn_candidates=(
                        f"urn:nir:stato:decreto.del.presidente.della.repubblica:1986-12-22;917~art{n}!vig={{as_of}}",
                        f"urn:nir:stato:decreto.del.presidente.della.repubblica:1986-12-22;917~art{n}",
                    ),
                )
                for n in (1, 2, 3, 8, 9, 10, 11, 12, 13, 49, 81)
            ]
            + [
                BundleItem(
                    key=f"iva_art{n}",
                    area="tributario",
                    urn_candidates=(
                        f"urn:nir:stato:decreto.del.presidente.della.repubblica:1972-10-26;633~art{n}!vig={{as_of}}",
                        f"urn:nir:stato:decreto.del.presidente.della.repubblica:1972-10-26;633~art{n}",
                    ),
                )
                for n in (1, 17, 21)
            ]
            + [
                BundleItem(
                    key=f"dlgs472_art{n}",
                    area="tributario",
                    urn_candidates=(
                        f"urn:nir:stato:decreto.legislativo:1997-12-18;472~art{n}!vig={{as_of}}",
                        f"urn:nir:stato:decreto.legislativo:1997-12-18;472~art{n}",
                    ),
                )
                for n in (5, 6, 7)
            ]
            + [
                BundleItem(
                    key=f"statuto_contribuente_art{n}",
                    area="tributario",
                    urn_candidates=(
                        f"urn:nir:stato:legge:2000-07-27;212~art{n}!vig={{as_of}}",
                        f"urn:nir:stato:legge:2000-07-27;212~art{n}",
                    ),
                )
                for n in (3, 7, 10)
            ]
        ),
    ),
}


def list_official_bundles(store: Any | None = None) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    if store is not None:
        try:
            counts = count_imported_bundle_documents(store)
        except Exception:
            counts = {}
    return [
        {
            "name": bundle.name,
            "description": bundle.description,
            "documents": len(bundle.items),
            "imported": counts.get(bundle.name, 0),
            "areas": sorted({item.area for item in bundle.items}),
        }
        for bundle in OFFICIAL_BUNDLES.values()
    ]


def count_imported_bundle_documents(store: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    conn = getattr(store, "conn", None) or getattr(store, "connection", None) or store
    cursor = conn.execute(
        "SELECT id FROM documents WHERE id LIKE 'normattiva:%'"
    )
    for (doc_id,) in cursor.fetchall():
        parts = doc_id.split(":", 2)
        if len(parts) < 3:
            continue
        bundle_name = parts[1]
        counts[bundle_name] = counts.get(bundle_name, 0) + 1
    return counts


def make_document_id(urn: str, *, prefix: str = "normattiva") -> str:
    slug = urn.lower()
    slug = slug.replace("urn:nir:", "")
    slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
    if len(slug) > 96:
        digest = hashlib.sha1(urn.encode("utf-8")).hexdigest()[:12]
        slug = f"{slug[:80]}_{digest}"
    return f"{prefix}:{slug}"


def canonical_portal_url(urn: str) -> str:
    return f"{NORMATTIVA_PORTAL_BASE}{urn}"


def _iso_today() -> str:
    return date.today().isoformat()


def _compact_whitespace(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _normalize_vigenza(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text or text in {"0", "99999999"}:
        return ""
    if re.fullmatch(r"\d{8}", text):
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text


def _extract_article_heading(plain_text: str) -> tuple[str, str]:
    lines = [line.strip() for line in plain_text.splitlines() if line.strip()]
    article_label = ""
    article_heading = ""
    if lines and lines[0].lower().startswith("art."):
        article_label = lines[0]
        if len(lines) > 1 and not re.match(r"^\d+[.)]?\s", lines[1]):
            article_heading = lines[1]
    return article_label, article_heading


def _normalize_reference_list(references: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for item in references:
        urn = item.get("urn", "").strip()
        text = _compact_whitespace(item.get("text", ""))
        if not urn:
            continue
        key = (urn, text)
        if key in seen:
            continue
        seen.add(key)
        out.append({"urn": urn, "text": text, "source_ref": canonical_portal_url(urn)})
    return out


def _pick_document_payload(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data") or {}
    if data.get("atto"):
        return data["atto"]
    lista = data.get("lista") or []
    if len(lista) == 1:
        return lista[0]
    if lista:
        raise RuntimeError(
            "Normattiva ha restituito risultati multipli per la URN richiesta; occorre una URN più specifica."
        )
    raise RuntimeError("Normattiva non ha restituito alcun atto per la URN richiesta.")


def _response_error_message(payload: dict[str, Any]) -> str:
    if payload.get("message"):
        return str(payload["message"])
    if payload.get("code"):
        return f"Errore API Normattiva codice {payload['code']}"
    return "Risposta non valida da Normattiva."


def _html_to_text_and_refs(raw_html: str) -> tuple[str, list[dict[str, str]]]:
    parser = _NormattivaArticleParser()
    parser.feed(raw_html or "")
    parser.close()
    return parser.text(), _normalize_reference_list(parser.references)


class _NormattivaArticleParser(HTMLParser):
    _BLOCK_TAGS = {"div", "p", "section", "article", "h1", "h2", "h3", "h4", "h5", "li", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._parts: list[str] = []
        self.references: list[dict[str, str]] = []
        self._link_href: str | None = None
        self._link_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key: value or "" for key, value in attrs}
        if tag == "a":
            self._link_href = html.unescape(attrs_map.get("href", ""))
            self._link_buffer = []
        if tag in self._BLOCK_TAGS or tag == "br":
            self._newline()

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            href = self._link_href or ""
            text = _compact_whitespace("".join(self._link_buffer))
            urn_match = re.search(r"urn:nir:[^\"'&<>\s]+", href)
            if urn_match:
                self.references.append({"urn": urn_match.group(0), "text": text})
            self._link_href = None
            self._link_buffer = []
        if tag in self._BLOCK_TAGS:
            self._newline()

    def handle_entityref(self, name: str) -> None:
        self.handle_data(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.handle_data(html.unescape(f"&#{name};"))

    def handle_data(self, data: str) -> None:
        value = html.unescape(data)
        if not value:
            return
        self._parts.append(value)
        if self._link_href is not None:
            self._link_buffer.append(value)

    def text(self) -> str:
        raw = "".join(self._parts)
        raw = raw.replace("\r", "")
        raw = re.sub(r"\n[ \t]+", "\n", raw)
        return _compact_whitespace(raw)

    def _newline(self) -> None:
        if not self._parts:
            return
        if not self._parts[-1].endswith("\n"):
            self._parts.append("\n")


class NormattivaClient:
    def __init__(self, base_url: str = NORMATTIVA_API_BASE) -> None:
        self.base_url = base_url.rstrip("/")

    def fetch_article(
        self,
        urn: str,
        *,
        area: str,
        kind: str = "norma",
        document_id: str | None = None,
    ) -> Document:
        payload = self._post_json(NORMATTIVA_DETAIL_URN_PATH, {"urn": urn})
        success = payload.get("success")
        if success is False and not payload.get("data"):
            raise RuntimeError(_response_error_message(payload))
        atto = _pick_document_payload(payload)
        article_html = atto.get("articoloHtml") or ""
        plain_text, references = _html_to_text_and_refs(article_html)
        if not plain_text:
            raise RuntimeError("Normattiva ha restituito un articolo vuoto.")

        article_label, article_heading = _extract_article_heading(plain_text)
        title_main = _compact_whitespace(str(atto.get("titolo") or "Atto Normattiva"))
        title_bits = [title_main]
        if article_label:
            title_bits.append(article_label)
        if article_heading:
            title_bits.append(article_heading)
        title = " - ".join(title_bits)

        selected_document_id = document_id or make_document_id(urn)
        metadata = {
            "official": True,
            "provider": "normattiva",
            "provider_api": f"{self.base_url}{NORMATTIVA_DETAIL_URN_PATH}",
            "urn": urn,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "references": references,
            "raw_identifiers": {
                "tipoProvvedimentoCodice": atto.get("tipoProvvedimentoCodice"),
                "numeroProvvedimento": atto.get("numeroProvvedimento"),
                "annoProvvedimento": atto.get("annoProvvedimento"),
                "numeroGU": atto.get("numeroGU"),
            },
            "content_sha256": hashlib.sha256(plain_text.encode("utf-8")).hexdigest(),
        }
        return Document(
            id=selected_document_id,
            title=title,
            kind=kind,
            area=area,
            content=plain_text,
            source_type="official",
            source_ref=canonical_portal_url(urn),
            authority="Normattiva",
            effective_from=_normalize_vigenza(atto.get("articoloDataInizioVigenza")),
            effective_to=_normalize_vigenza(atto.get("articoloDataFineVigenza")),
            metadata=metadata,
        )

    def fetch_first_available(
        self,
        urn_candidates: list[str] | tuple[str, ...],
        *,
        area: str,
        kind: str = "norma",
        document_id: str | None = None,
    ) -> Document:
        last_error: Exception | None = None
        for urn in urn_candidates:
            try:
                return self.fetch_article(urn, area=area, kind=kind, document_id=document_id)
            except Exception as exc:
                last_error = exc
        if last_error is None:
            raise RuntimeError("Nessuna URN candidata fornita.")
        raise RuntimeError(f"Nessuna URN candidata ha prodotto un risultato valido: {last_error}")

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code} da Normattiva: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Connessione a Normattiva fallita: {exc}") from exc


def _render_urn_candidates(candidates: tuple[str, ...], as_of_date: str) -> list[str]:
    rendered: list[str] = []
    for candidate in candidates:
        rendered.append(candidate.format(as_of=as_of_date))
    return rendered


def ingest_normattiva_urn(
    store: Any,
    *,
    urn: str,
    area: str,
    document_id: str | None = None,
    kind: str = "norma",
) -> dict[str, Any]:
    client = NormattivaClient()
    document = client.fetch_article(urn, area=area, kind=kind, document_id=document_id)
    store.upsert_document(document)
    store.replace_document_references(document.id, document.area, document.metadata.get("references", []))
    store.commit()
    return {"document_id": document.id, "urn": urn, "health": store.health()}


def sync_official_bundle(
    store: Any,
    *,
    bundle_name: str,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    try:
        bundle = OFFICIAL_BUNDLES[bundle_name]
    except KeyError as exc:
        raise ValueError(f"bundle sconosciuto: {bundle_name}") from exc

    effective_date = as_of_date or _iso_today()
    client = NormattivaClient()
    ingested: list[dict[str, str]] = []

    for item in bundle.items:
        document_id = f"normattiva:{bundle.name}:{item.key}"
        candidates = _render_urn_candidates(item.urn_candidates, effective_date)
        document = client.fetch_first_available(
            candidates,
            area=item.area,
            kind=item.kind,
            document_id=document_id,
        )
        document.metadata["bundle"] = bundle.name
        document.metadata["bundle_key"] = item.key
        store.upsert_document(document)
        store.replace_document_references(document.id, document.area, document.metadata.get("references", []))
        ingested.append(
            {
                "document_id": document.id,
                "title": document.title,
                "urn": str(document.metadata.get("urn", "")),
                "area": document.area,
            }
        )

    store.commit()
    return {
        "bundle": bundle.name,
        "as_of_date": effective_date,
        "documents": ingested,
        "health": store.health(),
    }
