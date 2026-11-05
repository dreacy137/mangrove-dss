"""Draft knowledge base of common Philippine mangrove species used in rehabilitation.

Each species lists the zones where it typically grows and its preferred substrate.
DRAFT: verify every row against Primavera (2009) "Field Guide to Philippine
Mangroves" and other published zonation studies before the defense, and add
species found at the study sites.

zones: "seaward", "middle", "landward", "riverine"
  primary  = where the species is most typical
  secondary = where it also occurs
substrate: "sandy", "muddy", "firm" (firm, well-drained mud), or "any"
"""

SPECIES = [
    {
        "name": "Avicennia marina",
        "local": "Bungalon",
        "primary": ["seaward"],
        "secondary": ["middle", "riverine"],
        "substrate": ["sandy", "muddy"],
        "note": "Pioneer species of exposed, frequently flooded fronts; tolerates high salinity.",
    },
    {
        "name": "Sonneratia alba",
        "local": "Pagatpat",
        "primary": ["seaward"],
        "secondary": [],
        "substrate": ["sandy"],
        "note": "Seaward edge on sandy or coralline ground with full sea-water salinity.",
    },
    {
        "name": "Rhizophora stylosa",
        "local": "Bakauan bato",
        "primary": ["seaward"],
        "secondary": ["middle"],
        "substrate": ["sandy"],
        "note": "Sandy and coralline substrates; more tolerant of exposure than other Rhizophora.",
    },
    {
        "name": "Rhizophora apiculata",
        "local": "Bakauan lalaki",
        "primary": ["middle"],
        "secondary": ["seaward"],
        "substrate": ["muddy"],
        "note": "Deep, soft mud in the middle zone; often over-planted on unsuitable mudflats.",
    },
    {
        "name": "Rhizophora mucronata",
        "local": "Bakauan babae",
        "primary": ["middle", "riverine"],
        "secondary": [],
        "substrate": ["muddy"],
        "note": "Soft mud along creeks and river banks in the middle zone.",
    },
    {
        "name": "Bruguiera gymnorhiza",
        "local": "Busain",
        "primary": ["landward"],
        "secondary": ["middle"],
        "substrate": ["firm", "muddy"],
        "note": "Firmer, less frequently flooded ground behind the Rhizophora zone.",
    },
    {
        "name": "Ceriops tagal",
        "local": "Tangal",
        "primary": ["landward"],
        "secondary": [],
        "substrate": ["firm"],
        "note": "Well-drained landward ground, often with high soil salinity.",
    },
    {
        "name": "Xylocarpus granatum",
        "local": "Tabigi",
        "primary": ["landward", "riverine"],
        "secondary": [],
        "substrate": ["firm", "muddy"],
        "note": "Back mangrove and river banks with lower salinity.",
    },
    {
        "name": "Lumnitzera racemosa",
        "local": "Kulasi",
        "primary": ["landward"],
        "secondary": [],
        "substrate": ["firm", "sandy"],
        "note": "Landward edge, rarely flooded.",
    },
    {
        "name": "Nypa fruticans",
        "local": "Nipa",
        "primary": ["riverine"],
        "secondary": [],
        "substrate": ["muddy"],
        "note": "Brackish, low-salinity river banks and estuaries.",
    },
    {
        "name": "Avicennia officinalis",
        "local": "Api-api",
        "primary": ["riverine"],
        "secondary": ["landward"],
        "substrate": ["muddy"],
        "note": "River banks and estuaries with lower salinity.",
    },
]

ZONE_LABELS = {
    "seaward": "Seaward (low) zone: flooded at most high tides",
    "middle": "Middle zone: flooded at normal high tides",
    "landward": "Landward (high) zone: flooded only at spring tides",
    "riverine": "Riverine zone: brackish river banks and estuaries",
}
