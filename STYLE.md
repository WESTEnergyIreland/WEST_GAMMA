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
| residual curtailment | recorded curtailment the model's operating rules do not simulate (not in the model since 14 November 2026) |
| SNSP | System Non-Synchronous Penetration; define at first use |
| IE, NI, all-island | Ireland, Northern Ireland, both |
| full decarbonisation | not "net zero" |
| surplus | output above demand and exports; not "oversupply" |
| TPE | Total Primary Energy; every energy share names its denominator |
| Gamma | the model; not "the demonstrator" in new text |

Scenario names: in the paper and supplement, EirGrid Extended (EE) and Historical Trend (HT), defined at first use in the abstract and again in the main text; never "pathway" where scenario is meant. In code, the workbook and the changelog, the row names EirGrid_Extended and Historical_Trend.

## References

- The Phase 1 paper uses numbered references in order of first appearance; Energy Policy sets no format at submission and applies its own author-year style at proof. Other WEST documents use Harvard style.
- Harvard in-text: one author (Smith, 2024); two authors (Smith and Jones, 2024); three or more (Smith *et al.*, 2024), with *et al.* in italics. In the numbered style, write Smith *et al.* [12].
- Web references give the full URL and the date last accessed (day, month and year).
- Cite primary sources (EirGrid, SONI, SEAI, CRU, peer-reviewed papers) over news and blogs.
