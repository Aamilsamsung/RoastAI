# Dependency licence inventory

DEPENDENCIES.json records installed Python and npm packages and their declared licences, including development dependencies. React/Next.js/TypeScript commonly declare MIT; FastAPI/Pydantic/SQLAlchemy declare MIT; Google SDKs declare Apache-2.0; Uvicorn declares BSD. Read exact inventory entries and upstream notices before redistribution. Missing declarations are flagged, not assumed permissive. Node platform binaries may carry separate third-party notices. Preserve COPYRIGHT/NOTICE files from distributed dependencies. This inventory is not a legal clearance or a licence for RoastAI proprietary source/branding.

Frontend npm audit --omit=dev returned zero known vulnerabilities during this audit. The initial Python scan found advisories only in the inherited pip 25.0.1 installer; pip is now pinned to 26.2.1, and the patched installed environment rescan returned zero known vulnerabilities. declared licence inventory is not a security audit.
