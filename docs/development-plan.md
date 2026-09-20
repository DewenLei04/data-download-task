# Development plan

Build two independently designed, GUI-accessible data websites in one deployable
Flask application. Every published dataset must be newly generated with the supplied
generate-contextual-dirty-data skill; original downloads are reference inputs only.
Prominent, keyboard-accessible download links must trigger real browser downloads.

1. Review ALE contracts, execution, GUI, images, networking, artifacts and verification.
2. Acquire bounded historical source snapshots and record provenance.
3. Profile local inputs with the supplied skill, declare v4 source-conditioned models,
   generate clean files, author contextual patches, and pass both validation and audit.
4. Build transport and climate websites with search, filters, details and downloads.
5. Test browser click/download flows, payload hashes and private-file exclusion.
6. Author six portable ALE task folders, install a real browser in their task image,
   and validate empty/oracle outputs and deliberately incorrect outputs.
7. Run a real GUI agent after model credentials are available. Report this separately
   from scripted browser tests and oracle validation.
8. Deploy to Vercel only after local review, as requested by the owner.

The source repository was public at initialization. Source inputs, clean/dirty audit
materials and run evidence remain ignored until a private storage decision is made.
Vercel must use `website/` as its project root, never the repository root.
