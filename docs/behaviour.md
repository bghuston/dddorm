# Expected behaviour for inspection

These scenarios describe the intended contract. They are not automated tests,
and none has been executed or verified. No tests were added, as requested.

| Scenario | Intended result |
| --- | --- |
| Construct an entity | UUID available before flush |
| Compare two same-type entities with the same UUID | Equal even if attributes differ |
| Compare different entity types with the same UUID | Unequal |
| Change a Money field | Pydantic rejects assignment |
| Create negative money, oversized amount, or malformed currency | Validation rejects it |
| Add a zero/negative/non-integer quantity or mismatched currency | Command rejected without mutation |
| Finalise an empty order | Command rejected |
| Add, remove, or change a line after finalisation | Command rejected |
| Add and modify a new root before first flush | Initial INSERT uses version 1 |
| Change a line on an attached persisted order | Root version advances alongside the child write |
| Set a line to its current quantity on a persisted order | Root version still advances |
| Modify a root after its initial INSERT was flushed | Root participates in normal version checking |
| Two sessions mutate the same loaded aggregate version | First commit wins; second flush/commit conflicts under suitable isolation |
| A flush fails after some child SQL was issued | Transaction rollback discards all outstanding writes |
| A scope raises before commit | Outstanding transaction rolled back |
| Normal default exit | Outstanding writes rolled back |
| Normal commit exit | Outstanding writes flushed and committed |
| Normal flush exit | Writes flushed and then rolled back |
| Commit explicitly, then raise | Earlier committed transaction remains durable |
| Lookup a repository session outside a scope | RuntimeError |
| Nest a Unit of Work in the same task | RuntimeError before allocating an inner session |
| Re-enter an active Unit of Work instance | RuntimeError |
| Parent scope spawns a task that uses its ambient repository | RuntimeError on session lookup |
| Each child task opens its own scope with a fresh-session factory | Independent sessions and transactions |
| Scope exits successfully or exceptionally | Session close attempted; prior context restored |
| Query triggers autoflush of a stale root | Conflict may surface before explicit commit |
| Read without a root write | No version assertion |
| Direct child SQL or bulk UPDATE bypasses root methods | Aggregate version protection is not automatic |

Inspection should consider the root's SQL writes and the child writes as one
transaction, while distinguishing this from business-wide serializability.
The documentation does not establish correctness, driver compatibility, or
production readiness.
