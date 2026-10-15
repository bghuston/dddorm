# Architecture notes

## Domain choices and implementation choices

DDD gives us identity, values, aggregate boundaries, repositories, and coordinated
units of work. SQLAlchemy declarative inheritance, UUID keys, Pydantic, eager
relationship loading, and context variables are implementation choices. None
defines DDD itself.

`Order` owns all of its `OrderLine` entities. There is no `OrderLineRepository`.
An order's finalisation rule must be checked alongside changes to its lines. A
transaction persists the aggregate's writes atomically; a version assertion
prevents two cooperating writers from applying decisions based on incompatible
snapshots. A transaction may touch several aggregates, but that does not make
their cross-aggregate invariants automatically safe under concurrent writers.

## Mapping and identity

`Entity` is the single abstract declarative base; its metadata includes all
imported domain tables. Concrete classes choose table names. Python construction
assigns a UUID immediately; the column default is a fallback for ORM insertion.
SQLAlchemy materialises loaded instances without calling domain constructors.
Entity equality uses the concrete Python class and UUID, including across
sessions. If an ID is absent, only the same object is equal to itself. Entities
are unhashable to avoid mutable-primary-key hash problems. IDs must not be
changed by application code. Complex inheritance mappings are out of scope.

`AggregateRoot` supplies mapper version configuration through `declared_attr`.
Subclasses that override `__mapper_args__` must preserve `version_id_col`.
SQLAlchemy performs version checking on ORM instance UPDATE and DELETE during
flush. The abstraction re-exports `StaleDataError`; it does not replace SQLAlchemy's
error with a custom exception that might lose useful context.

`Money` is represented by scalar amount and currency columns on a line. The
`unit_price` property reconstructs an immutable Pydantic value. Frozen Pydantic
models prevent field reassignment, but do not deeply freeze a list or dictionary;
new value types should use immutable nested fields. Decimal values avoid binary
floating-point arithmetic in the illustrative domain; callers should supply
Decimals or decimal strings. No JSON-encoding or ORM composite framework is needed.

The `_lines` relationship uses `selectin` loading so domain methods on a loaded
order do not trigger synchronous lazy IO. SQLAlchemy also queries related lines
when needed for ORM cascading deletion. The line foreign key has no database
`ON DELETE CASCADE`; this example relies on ORM cascades. Database setup must
enable and honour foreign-key enforcement, including SQLite's opt-in enforcement.
No engine, migrations, schema bootstrap, or executable entry point is supplied.

## Write protocol

1. Enter a Unit of Work and load the root through its repository.
2. Call domain methods while that root is attached to the active session.
3. Validate the complete command before modifying any state.
4. Call `_mark_changed()` and apply changes to the root or its children.
5. Flush and commit once at the application boundary.

The root version is advanced explicitly for persistent roots. Transient and
pending roots rely on INSERT's initial version of 1. If an initial flush has
already made a new root persistent, later commands advance the version normally.
Direct scalar updates also use SQLAlchemy's automatic version generator.
Child-only updates need the explicit hook because relationship or child dirtiness
alone does not guarantee a root UPDATE. The hook intentionally increments for an
otherwise unchanged command, making the loaded version part of that operation.

The mutation hook rejects detached roots. Detached mutation and merge are not
the supported write protocol. Reload inside
a Unit of Work and apply the command to that attached root. A `ValueError` or
`KeyError` leaves a rejected domain command unchanged. Exceptions escaping the
scope roll back outstanding SQL, including child writes, and dispose of the
session. Do not continue to use objects after rollback without an async reload.

The public `lines` view is a tuple; line properties are read-only. These are API
conventions, not an enforcement layer against deliberate private-field access,
direct SQL, or constructing and adding an orphan line. Database constraints cover
simple positive-quantity and status rules, not the full aggregate protocol.

## Task and resource ownership

The context variable contains a session and owning task. Repository lookup first
checks that `asyncio.current_task()` is that owner. Without this check,
`asyncio.create_task()` would copy a reference to the parent's session and permit
unsafe concurrent use. Sibling task scopes each create a fresh session. A child
scope restores its inherited binding on exit, but lookup of that binding remains
forbidden. A context with a copied binding is never permission to reuse it.

The injected factory must return a fresh, unshared AsyncSession each time; do not
inject a singleton, task-scoped proxy, or a session already managed elsewhere.
Explicit repository session injection is useful at infrastructure boundaries
and in the conflict illustration. That path does not promise automatic task
protection: the caller owns exclusive access, transaction handling, and closing.
Likewise, retrieving `uow.session` and then manually passing it to another task
bypasses the intended ownership model.

Same-task nesting is rejected before allocating a second session. Reusing an
active Unit of Work instance is rejected even from another task. No implicit
savepoints, ambient transaction joining, or shared transaction ownership is
implemented. To compose services within one atomic command, let the outer
boundary own the Unit of Work and have inner operations use repositories.

Scope entry allocates a session, not a mandatory database connection. SQLAlchemy
autobegin creates a transaction when required. Exiting always attempts session
closure and resets the context token in a `finally` block, including flush and
commit failures and ordinary cancellation. Like any async cleanup, database
rollback/close may itself fail or be interrupted by repeated cancellation; the
context is still reset, but resource reclamation also depends on the driver and
connection pool. Cleanup failure can replace an earlier exception, which remains
available as Python's exception context.

## Version conflict illustration

`illustrate_conflict()` creates an order, loads its current version in two
separate sessions, finalises both copies, commits the first, and attempts to
commit the second. The second UPDATE compares against the old version and should
raise `StaleDataError`; the illustration explicitly rolls it back.

This example uses independent sessions sequentially to make the stale snapshots
visible without sharing state across tasks. It assumes database isolation that
permits both reads and the first write. SQLite locking or snapshot upgrades,
REPEATABLE READ, or SERIALIZABLE configurations can produce different database
errors. An async driver and provisioned schema are external prerequisites, not
instructions to execute this inspection-only repository.

Optimistic version checks protect cooperating aggregate writes, not all read
decisions or every invariant across rows. Bulk ORM DML and Core statements do
not follow per-instance version checking. Writer discipline, appropriate
constraints, locks, and isolation are separate design responsibilities.
