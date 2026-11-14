# Graphite workspace redesign

The user-provided reference video showed a monochrome finance workspace: near-black surfaces, subtle card borders, a narrow sidebar, white trend lines, restrained typography, and rounded controls. FlakeGuard adopts that visual language for QA investigation rather than copying financial content or embedding the video. The reference video remains local and is not included in the repository.

## Implemented changes

- Graphite/black palette with white chart lines and limited semantic status colors.
- Compact navigation with decorative SVG icons and preserved native radio keyboard behavior.
- A workspace filter drawer that keeps the navigation clear. Scope and synthetic/injected provenance stay visible outside the drawer.
- Observed final pass rate as the main trend card, with chart-window controls based on the latest observed execution.
- A first-attempt reliability ring derived from actual known-attempt metrics. It is not a confidence or progress estimate.
- Compact run activity, investigation queue, and suite views using API results.
- Project labels for otherwise ambiguous test variants, scored table columns, and a CSV export of the currently scoped reliability data.
- Header actions for refresh and report import; the import action navigates to the actual upload form.
- Responsive two-column metric cards on phones, collapsible navigation, visible keyboard focus, and reduced-motion support.
- Read-only deployment mode that disables imports/sync in the UI and enforces that restriction in the API.

All five investigation pages remain functional. Existing parsing, reliability formulas, fingerprinting, and classification rules are unchanged. The dashboard continues to call the backend API; no display numbers were hardcoded for the redesign.

## Validation

`scripts/browser_check.py` renders each page to completion, captures actual screenshots, uploads a report through the UI, and verifies persistence. `scripts/ui_interactions.py` checks keyboard navigation, header actions, scoped API counts, CSV export, and mobile overflow/layout. Their machine-readable outcomes are stored under `docs/evidence/`. The CSS asset ships as package data and is included in the Docker source tree.
