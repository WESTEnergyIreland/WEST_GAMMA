# WEST writing style

Applies to the paper, the supplementary material, README files and the changelog. If you use an AI assistant, this file overrides its personal style settings for WEST documents.

Status: draft for group agreement, 30 October 2026.

## Language

- Irish English spelling (organise, modelling, programme, licence as a noun).
- If a journal requires another spelling, follow the journal at submission, not before.

## Sentences

- Plain declarative statements of fact. The plainest sentence in a paragraph carries its main point.
- No rhetorical questions.
- No dramatic flourishes, metaphors or figurative constructions.
- No clichés or filler: "it is worth noting", "plays a crucial role", "in today's rapidly evolving", "a key driver", "paves the way", "landscape", "robust" (unless statistical), "significant" (unless statistical).
- Keep dashes to a minimum. Use a full stop, comma or brackets instead.
- No enthusiasm or salesmanship. Let the numbers make the case.
- If something is not known, say so.

Rejected: "As Ireland races towards its renewable future, a hidden crisis is unfolding on the grid."

Accepted: "In 2024 Ireland lost 5.1% of available wind energy to transmission constraint. Northern Ireland lost 26.4%."

Rejected: "But what happens when wind capacity doubles?"

Accepted: "Doubling wind capacity raises dispatch down from X% to Y% under the EirGrid_Extended scenario."

## Numbers

- Every result quoted in the paper comes from the current `main` branch outputs. Name the scenario and the year.
- When a result changes, the old and new values go in `CHANGELOG.md`, then the paper is updated.
- State the basis of every percentage: share of available energy, share of demand, IE, NI or all-island.
- Units: MW, GW, MWh, TWh. SI spacing between number and unit (6.5 GW), none before % (75%).

## Terms

| Use | Meaning |
|---|---|
| dispatch down | constraint plus curtailment |
| constraint | loss due to transmission limits (local) |
| curtailment | loss due to system-wide limits (SNSP, minimum generation, RoCoF, inertia) |
| residual curtailment | recorded curtailment the model's operating rules do not simulate |
| SNSP | System Non-Synchronous Penetration; define at first use |
| IE, NI, all-island | Ireland, Northern Ireland, both |
| full decarbonisation | not "net zero" |
| Gamma | the model; not "the demonstrator" in new text |

Scenario names are written exactly as in `Data_inputs/scenariosXLSX.xlsx` (for example EirGrid_Extended, Historical_Trend).

## References

- Harvard style.
- In-text: one author (Smith, 2024); two authors (Smith and Jones, 2024); three or more (Smith *et al.*, 2024), with *et al.* in italics.
- Cite primary sources (EirGrid, SONI, SEAI, CRU, peer-reviewed papers) over news and blogs.
