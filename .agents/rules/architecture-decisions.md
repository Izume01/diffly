---
description: Maintain and continuously update architecture decision records (ADRs) whenever major technical, architectural, or infrastructure choices are made.
always_on: true
---

# Architecture Decision Records (ADR) Rule

### Mandatory Continuous Maintenance
Whenever any architectural, infrastructure, library, or design decision is discussed and agreed upon with the user:

1. **Proactively update [`docs/decisions.md`](file:///home/nyx/lab/diffly/docs/decisions.md)** immediately—do not wait for the user to ask.
2. **Follow the standard ADR format**:
   - **Title**: `ADR-XXXX: <Title>`
   - **Date & Status**: (`Accepted`, `Proposed`, `Deprecated`, `Superseded by ADR-XXXX`)
   - **Context**: Problem statement, background, and constraints.
   - **Options Considered**: Each candidate evaluated with pros and cons.
   - **Decision & Trade-offs**: Why the option was chosen over alternatives and what trade-offs were accepted.
   - **Consequences**: What becomes easier or harder as a result.
3. **Keep the Table of Contents / Index** at the top of [`docs/decisions.md`](file:///home/nyx/lab/diffly/docs/decisions.md) in sync.
4. If an existing decision changes or is superseded, update its status to `Superseded by ADR-XXXX` and link to the replacement decision.
