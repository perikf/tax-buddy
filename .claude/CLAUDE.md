# Working principles

- **Simplest possible solution.** Less is more. Keep it simple and concise. Avoid unnecessary complexity.
- **No technical debt.** Don't take shortcuts that cost later.
- **Modular.** Keep code modularised.
- **Simple docs.** Document functions simply. Don't write thorough/explanatory comments — no comments justifying *why* a choice was made.
- **Forward-looking docs.** Write docs as direct instructions for what to build. Don't reference, compare against, or explain provenance from prior implementations (no "v1 did X", no "distilled from `<file>`").
- **Simple folder structure.** Avoid unnecessary nesting and extra folder levels.
- **Keep the README current.** Update it whenever setup instructions change.
- **Keep docs in sync.** After any change, read the relevant docs files. If anything in the change contradicts or should be reflected in a doc, update that doc.
- **Match the codebase.** Read neighbouring code first, then mirror its patterns and naming.
- **One source of truth.** Check what's already there before adding; edit or extend rather than add a parallel copy.
- **One-way dependencies.** Keep clear layering and no cycles; cross module boundaries through narrow interfaces.
- **Fail loud, not silent.** Handle edges and errors deliberately.
- **Push back when you disagree.** If a request looks wrong or risky, say so with your reasoning before acting.
- **Verify before you claim done.** Run it; never assert a success you haven't observed.
