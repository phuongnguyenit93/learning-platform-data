# Version and Schema Compatibility in PostgreSQL Logical Replication

## 1. Why Is Compatibility Critical?

PostgreSQL logical replication transfers published data changes from a publisher to a subscriber. The two sides do not need identical physical layouts, yet they must agree on the same data contract: which relations are synchronized, which columns map to which, whether values convert cleanly, and whether subscriber constraints accept the incoming data.

There are two dimensions of compatibility to manage:

- **Version compatibility:** whether the major versions of publisher, subscriber, output plugin, and replication protocol support the deployed combination.
- **Schema compatibility:** whether tables, columns, data types, replica identities, partitioning, constraints, and dependent objects are suitable to apply the data.

Logical replication primarily synchronizes row changes. It does not automatically copy all DDL, schema objects, roles, grants, sequence states, extension binaries, or database configurations. Thus, two databases can both participate in a WAL logical stream yet the subscriber still fails during apply if schemas drift.

This lesson explains how to design compatibility before creating a subscription, how to deploy schema changes safely, how to detect drift, and how to organize a major-version upgrade.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Explain publisher/subscriber compatibility limits across PostgreSQL major versions.
2. Distinguish logical data replication from schema/DDL migrations.
3. Understand how tables and columns map between publisher and subscriber.
4. Evaluate data type conversions, defaults, generated/identity columns, and constraints.
5. Manage primary keys/replica identities for UPDATE and DELETE.
6. Design schema evolution using expand-and-contract.
7. Handle partitioning, row filters, column lists, enums, collations, and extensions.
8. Plan a major-version upgrade using logical replication.
9. Detect schema drift and subscription apply errors.
10. Execute preflight checks, lab exercises, and controlled cutovers.

### 1.2. Foundational Principles

- Logical replication transfers changes via publications/subscriptions; it does not automatically synchronize DDL.
- Publisher and subscriber must have compatible table mappings at apply time.
- Column names are the basis for mapping; do not assume tables match by positional column order.
- Differing data types are safe only when actual values convert accurately on the subscriber.
- Adding a column on the publisher does not automatically create the matching column on the subscriber.
- Replica identity determines how the subscriber locates the old row for UPDATE/DELETE.
- Sequence values, large objects, and many database object types are outside the normal row replication stream.
- A schema migration must be deployed in an order compatible with both sides.
- A subscriber should not be treated as a writable multi-master peer of the publisher.
- Always test on exact target PostgreSQL versions, extensions, and representative data before cutover.

---

## 2. Publisher, Subscriber, and Boundaries of Logical Replication

### 2.1. Publisher

The publisher is the PostgreSQL server/database creating publications and emitting logical changes. A publication defines which tables or operations are published.

Example:

~~~sql
CREATE PUBLICATION app_pub
FOR TABLE app.customers, app.orders;
~~~

Publications can restrict operations such as INSERT, UPDATE, DELETE, and TRUNCATE depending on capability/version. Row filters and column lists may also be supported in corresponding versions.

### 2.2. Subscriber

The subscriber is the database creating a subscription to connect to the publisher and apply changes into matching tables.

~~~sql
CREATE SUBSCRIPTION app_sub
CONNECTION 'host=publisher.example.net port=5432 dbname=appdb user=replicator'
PUBLICATION app_pub;
~~~

The subscriber needs corresponding schemas and tables prepared beforehand. Logical replication does not automatically create table definitions from the publisher.

### 2.3. A Publication Is Not a Schema Migration

A publication describes which data and operations are emitted. It is not a migration script and does not automatically synchronize:
- CREATE/ALTER/DROP TABLE.
- CREATE/ALTER TYPE.
- Indexes, constraints, and triggers.
- Roles, grants, policies, and ownership.
- Extensions and extension binaries.
- Sequence definitions/current values.
- Views, materialized views, and functions.

These objects must be deployed via migration tooling or separate administrative workflows.

### 2.4. The Subscriber Table Must Exist

When a subscription copies initial data, the apply worker needs a target relation to write rows into. If the table does not yet exist or the schema is incompatible, initial table synchronization or the apply phase will fail.

Schemas can be pre-created using migration tools, schema dumps, or deployment scripts. Avoid letting both sides evolve schemas independently without version control.

### 2.5. Logical Replication Is Not Bidirectional Replication

A standard subscription streams changes from publisher to subscriber. If applications write independently on both sides, issues arise:
- Row conflicts.
- Duplicate primary keys.
- Divergent values.
- Sequence collisions.
- No generic conflict resolution mechanism like a distributed multi-master database.

Default designs should enforce a single write authority for replicated tables at any given time.

### 2.6. Distinguishing Logical Replication from Logical Decoding

Logical decoding is the mechanism that reads WAL and transforms changes into a logical representation via an output plugin. Logical replication is one consumer of logical decoding that transfers changes to a subscriber and applies them into tables.

Output plugins/protocols form part of the compatibility surface. Custom consumers may have separate version requirements beyond built-in pgoutput.

---

## 3. Major Version Compatibility Between Publisher and Subscriber

### 3.1. Basic Deployment Rule

Built-in PostgreSQL logical replication is commonly used to replicate from an older major version publisher to a newer major version subscriber during major upgrades. The subscriber should run the same major version as or newer than the publisher per PostgreSQL compatibility policy.

Do not assume a newer publisher can safely replicate to an older subscriber. Logical replication protocols, message fields, type behaviors, and publication features can change across major releases.

Before deploying, check documentation for both major versions and verify the replication direction. Do not infer compatibility merely because a TCP connection or replication slot creation succeeded.

### 3.2. Why Is Old-to-New Direction Useful?

A major upgrade workflow might:
1. Provision a subscriber on the new major version.
2. Install extensions and create compatible schemas.
3. Copy initial data.
4. Stream changes from the old publisher.
5. Wait for the subscriber to catch up.
6. Stop writes during the cutover window.
7. Verify final LSN/data parity.
8. Switch the application to the new subscriber.

This approach can reduce downtime compared to offline dump/restore for large databases, yet requires schema compatibility and an explicit cutover runbook.

### 3.3. Do Not Check Major Versions Alone

Preflight must check:
- Exact publisher and subscriber server versions.
- Replication protocol/output plugin.
- Publication options in use.
- Row filter/column list support.
- Partition replication behavior.
- Type definitions and extension versions.
- Encoding/collation.
- Replication slot/plugin compatibility.
- Client tools and migration tooling.

### 3.4. Version-Gated Features

Logical replication has expanded across major versions. Features such as row filters, column lists, partition-root publication behavior, parallel apply, streaming in-progress transactions, two-phase replication, and failover slots may be added or altered across releases.

Do not copy configuration from newer PostgreSQL onto older servers without verification. Consult release-specific documentation for:
- CREATE PUBLICATION options.
- CREATE SUBSCRIPTION options.
- ALTER SUBSCRIPTION syntax.
- Monitoring view columns.
- Replication protocol capabilities.

### 3.5. pgoutput and Custom Output Plugins

Built-in logical replication typically uses the pgoutput plugin. If using another plugin, verify:
- Whether the plugin is installed on the publisher.
- Whether plugin binaries are compatible with the server major version.
- Whether the consumer understands the message format/version.
- Consumer schema/type mapping.
- Upgrade/rollback paths when the plugin changes.

Custom consumers may rely on protocol details already handled by built-in subscribers.

### 3.6. PostgreSQL Upgrades Do Not Automatically Upgrade Extensions

Logical replication transmits row changes; it does not install shared libraries or upgrade extension binaries. When the subscriber runs a newer major version:
- Install extension packages compatible with the new major version.
- Create extensions in the subscriber database.
- Verify extension SQL objects and versions.
- Confirm types/operators/functions used by schemas.
- Test applying rows containing extension types before cutover.

### 3.7. System Catalogs Differ

Do not directly replicate system catalogs to upgrade versions. PostgreSQL major versions can alter catalog layouts and internal representations. Use logical replication at the table-change layer, migration scripts, and supported tools.

### 3.8. Version Compatibility Matrix

Maintain an internal matrix for each pipeline:

| Publisher | Subscriber | Purpose | Verification status |
|---|---|---|---|
| PG 14 | PG 15 | Major upgrade | Tested in staging |
| PG 15 | PG 16 | Major upgrade | Not yet tested |
| PG 16 | PG 15 | Reverse direction | Do not assume supported |
| PG 16 | PG 16 | Same-major replication | Tested |

Versions shown are illustrative examples. Replace with actual versions and verified support status.

---

## 4. Table Mapping and Schema Matching

### 4.1. Relation Names

The subscriber needs target tables matching those emitted by the publication. Relation mapping uses schema/table identity per logical replication configuration; subscriber tables are not inferred from similar names or creation order.

If a table is renamed on the publisher, the subscriber does not automatically rename along with it. Coordinate two-sided migrations and publication/subscription refreshes when table membership changes.

### 4.2. Column Mapping by Name

Logical replication maps columns by name, not by ordinal position in the table. Thus column ordering may differ, provided column names and value conversion align.

Do not rely on identically named columns that carry different semantics. For instance, if the publisher stores amount in cents while the subscriber stores amount in dollars, data types may match while business meaning is corrupted.

### 4.3. Publisher Adds an Extra Column

If the publisher sends a column absent on the subscriber, that column is not created automatically on the subscriber. In supported mapping scenarios, publisher-side columns lacking a target counterpart may be handled/ignored according to logical replication rules; however, this change must still be verified against publication column lists, table mapping, and version.

It is safer to deploy the new column on the subscriber before the publisher begins writing values into it.

### 4.4. Subscriber Has Extra Columns

The subscriber can have additional columns beyond replicated columns, provided they can receive valid values when applying rows:
- Nullable columns are generally easier to keep compatible.
- Columns with defaults can receive defaults when no replicated value is supplied per insert semantics.
- NOT NULL columns without defaults can cause INSERT apply to fail.
- Generated columns follow their own rules and are computed locally by the subscriber per its expression.

Do not rely on subscriber defaults as a substitute for publisher data if business semantics require matching values.

### 4.5. Column Renames

Renaming a column on the publisher does not automatically rename it on the subscriber. While names diverge between sides, mapping cannot find the matching target column and apply can fail or stop replicating that column as intended.

Use expand-and-contract:
1. Add the new column on both sides.
2. Backfill/dual-write or migrate data in a controlled manner.
3. Update publication column lists/mappings if applicable in supported versions.
4. Switch applications to the new column.
5. Drop the old column only once all consumers have transitioned.

### 4.6. Dropping Columns

Dropping a column on the publisher before subscribers/applications stop depending on it can cause missing data or apply mismatches. Dropping columns is the final contract step after observation confirms all consumers upgraded.

### 4.7. Table/Schema Renames

DDL renames do not propagate automatically. Coordinate migrations, update publication membership if needed, and verify subscription relation mappings. For table renames, you may need to drop/add the table in the publication and refresh the publication on the subscriber per version/operations.

### 4.8. Intentional Schema Differences

Publisher and subscriber may have managed differences—for instance, extra read indexes or a different tablespace on the subscriber. Document those differences explicitly in the schema contract. Prevent accidental drift because a local change can break apply.

---

## 5. Data Type Compatibility and Value Conversion

### 5.1. Identical Type Names Are Not Enough

Two columns with the same name and type can still differ semantically due to:
- Different precision/scale.
- Different length constraints.
- Different collations.
- Different domain constraints.
- Different enum labels.
- Different extension type versions.
- Different time zone interpretations.

Compatibility checks must inspect both metadata and actual data.

### 5.2. Differing Types

Logical replication can transfer values via type output/input representations per protocol and server behavior. Some differing source/target types are compatible if the target parses the representation; others fail during apply.

Examples:
- integer to bigint is usually a safe widening if values fit in range.
- bigint to integer can overflow.
- text to uuid succeeds only if every value has valid UUID format.
- smaller numeric precision may round or be rejected depending on values/constraints.
- timestamp and timestamptz cannot be treated as equivalent when timezone semantics differ.

Always test on representative data and boundary values.

### 5.3. Numeric Precision/Scale

The publisher may use numeric(18,2) while the subscriber uses numeric(12,2). Values exceeding target precision will fail or behave per conversion semantics; never assume the subscriber fits the full publisher range.

To widen capacity, it is generally safer to widen the target type first (making it wider or equal), then update the publisher after the subscriber is ready.

### 5.4. Integer Ranges

- smallint: narrow range.
- integer: wider range than smallint.
- bigint: wider range than integer.

When the subscriber uses a narrower type, a new row can make the apply worker fail. Check min/max values before narrowing types.

### 5.5. Character Data

varchar(n)/char(n)/text can differ in length semantics and padding. If the subscriber enforces a shorter limit than the publisher, long values cause errors. Check Unicode characters, byte length, and character length; they are not identical.

### 5.6. Timestamps and Timezones

timestamp without time zone stores date/time values without timezone attachment. timestamptz represents an instant displayed per session timezone. Converting between the two can alter temporal meaning.

For events, payment timestamps, and audit records, align semantics before migrating. Check TimeZone settings, client input formats, and values around daylight-saving transitions if timezone rules apply.

### 5.7. Boolean, UUID, and Binary

Simple types usually replicate cleanly when both sides share representations. Still, inspect custom casts, domains, and client encodings. bytea payloads can be large; test throughput, memory, and WAL/replication lag with realistic payloads.

### 5.8. Arrays, Composites, and Ranges

Complex types depend on compatible type definitions. The subscriber needs matching types and nested element types. If a composite type alters field names/order/types, deploy synchronized migrations and test old/new values.

### 5.9. Domains

A domain type combines a base type and constraints. Matching domain names do not guarantee identical definitions. If the subscriber domain is stricter, publisher rows can be rejected. Compare pg_type, pg_constraint, and domain base types/check constraints.

### 5.10. Enums

Enum labels must exist on the subscriber before the publisher emits rows with new labels. Adding an enum value on the publisher does not add the label on the subscriber. Adding the label on the subscriber first is the standard rollout order.

Enum label order also carries ordering semantics. Two sides with identical labels in different order can produce differing comparison/sort results. Do not treat enum definitions as equivalent merely because their label sets match.

### 5.11. Collations

Collations affect sort order, comparisons, and uniqueness behavior. Differing locales, libc/ICU versions, or collation providers can cause subscriber behavior to diverge from the publisher, even affecting unique indexes. Check collation definitions/versions and reindex requirements per PostgreSQL docs.

### 5.12. Extension Types

Types such as geography/geometry or extension-defined types require compatible extensions on the subscriber. Do not create columns by type name alone; install matching extension versions, check casts/operators/functions, and test real payload apply.

### 5.13. Type Conversion Checklist

Before permitting any type mismatch:
- Check source/target types and typmods.
- Check min/max values and null distributions.
- Check text/binary representation behavior by version.
- Test boundary and malformed values.
- Check domain/enum/collation dependencies.
- Test initial copy and streaming updates.
- Confirm conversion errors are caught before cutover.

---

## 6. Replica Identity, Primary Keys, and Row Matching

### 6.1. Why Do UPDATE/DELETE Need Row Identification?

When the publisher emits INSERT, the subscriber adds the new row from sent data. For UPDATE or DELETE, the subscriber must know which old row to modify/remove. PostgreSQL uses replica identity to locate that row.

Normally replica identity is the primary key. A table without a primary key can still be published, provided you choose an appropriate strategy if the publication emits UPDATE/DELETE.

### 6.2. Replica Identity Modes

- DEFAULT: uses the primary key if present.
- USING INDEX: uses a designated eligible unique index.
- FULL: sends old row values to identify the row.
- NOTHING: sends no replica identity; suited for INSERT-only workloads where old-row identity is unnecessary.

Example:

~~~sql
ALTER TABLE app.events REPLICA IDENTITY DEFAULT;

ALTER TABLE app.audit_log REPLICA IDENTITY FULL;
~~~

USING INDEX syntax requires an index meeting PostgreSQL rules, such as unique, non-partial, and having required attributes.

### 6.3. Publisher and Subscriber Must Agree on Row Identity

The publisher decides which old-row identity is sent in logical changes. The subscriber must have a way to locate the target row. For critical tables, keep compatible primary/unique keys on both sides and ensure key values are not altered during type conversions.

If the subscriber cannot locate the row, UPDATE/DELETE apply can fail reporting tuple not found or missing replica identity. Some operations may not expose drift immediately if data already diverged; check row counts and keys prior to subscription/cutover.

### 6.4. REPLICA IDENTITY FULL

FULL transmits more old-row data and can enlarge WAL/logical stream size, especially on wide rows. It also makes row identification costlier if the subscriber lacks a suitable index.

Use FULL only when genuinely needed and measure overhead. A stable primary key is normally far more efficient.

### 6.5. Changing a Primary Key

Changing a primary key while logical replication is running is a multi-step migration:
1. Create a candidate unique key on both publisher and subscriber.
2. Backfill/validate uniqueness and NOT NULL.
3. Deploy compatible application changes.
4. Switch replica identity per plan.
5. Verify apply worker continues normally.
6. Drop the old key only once all consumers have transitioned.

Never drop a primary key on the publisher while a publication requires UPDATE/DELETE without an alternative replica identity in place.

### 6.6. Subscriber Has a Different Primary Key

If publisher and subscriber use different keys, prove the subscriber can locate the exact same row from transmitted identity data. Never change keys arbitrarily just to make schemas look similar; test UPDATE/DELETE with realistic data on exact target versions.

---

## 7. Defaults, Generated Columns, Identity, and Sequences

### 7.1. Default Values

Defaults run when an INSERT omits a column value. In logical replication, the subscriber receives row values from the publisher for replicated columns; do not assume subscriber defaults replace values sent by the publisher.

A subscriber with an extra column having a default can evaluate that default when the column is absent from target INSERTs, though behavior must be tested with specific publication column lists and versions.

### 7.2. Defaults Must Be Semantically Compatible

Both sides might define DEFAULT now(), yet timestamps can be generated at different instants if the column is not replicated and the default evaluates locally. If values must match, replicate the value from the publisher or use an explicit source of time/IDs.

Defaults calling nextval() also have a dedicated caveat: sequence state does not replicate automatically like row data.

### 7.3. Generated Columns

Generated columns are computed from other columns via expressions in each database. Logical replication does not transmit generated-column values like ordinary columns in documented scenarios; the subscriber can compute generated values using its own definition.

Therefore, generated expressions must be semantically compatible. If expressions differ between publisher and subscriber, identical input rows yield different results. Check version support and generated expressions before cutover.

### 7.4. Identity Columns

Identity columns can use sequences to generate values on local INSERTs. In logical replication, row values arrive from the publisher; the subscriber must be configured to accept replicated values according to identity semantics and PostgreSQL version.

Do not assume GENERATED ALWAYS and GENERATED BY DEFAULT are interchangeable without testing. Test applying explicit identity values in staging before enabling subscriptions.

### 7.5. Sequence State Is Not Synchronized Like Row Changes

Logical replication does not automatically synchronize sequence state. After initial copy or while receiving identity/serial values from the publisher, subscriber sequences can sit at different positions than the highest row value.

If the subscriber will be promoted and accept writes:
- Stop writes/cut over per runbook.
- Determine current/maximum used values.
- Synchronize sequences via setval() or suitable migration tools.
- Verify sequence increment/min/max/cache/cycle.
- Test issuing new IDs before opening traffic.

Never run setval in production while writes continue without locking/coordination procedures.

### 7.6. Serial and Identity Differ

serial is shorthand creating an integer column, sequence, and default nextval. Identity is a more standard SQL feature with separate metadata. Both have sequence state that logical replication does not synchronize automatically.

### 7.7. Large Objects

Large objects are managed via a separate mechanism and sit outside standard logical replication row changes. If schemas/applications use large objects, prepare a dedicated copy/validation workflow or choose a suitable migration solution.

---

## 8. Constraints, Indexes, Triggers, and Object Dependencies

### 8.1. Constraints Are Not Created Automatically

The subscriber needs desired constraints deployed separately. If the subscriber lacks a constraint, it may accept data the publisher would reject. If the subscriber has a stricter constraint, apply can fail even when the publisher committed cleanly.

Compatibility is not just "having tables and columns"; it also covers constraint behavior.

### 8.2. NOT NULL

If the publisher sends NULL into a subscriber NOT NULL column, apply will fail. Before adding NOT NULL on the subscriber:
1. Backfill existing data.
2. Verify no NULLs remain.
3. Deploy publisher/app updates so valid values are always written.
4. Apply the constraint per migration plan.
5. Monitor apply errors.

### 8.3. CHECK Constraints

A CHECK constraint on the subscriber can reject rows if conditions differ from the publisher. For example, publisher allows status pending, paid, while subscriber allows only paid, cancelled. Align constraint semantics before publishing new values.

### 8.4. Foreign Keys

Foreign keys on the subscriber can cause apply failures if referenced rows have not been applied yet, are excluded from the publication, or change ordering is incompatible. When replicating multiple related tables, verify publication membership, transaction ordering, and FK actions.

Never disable constraints to mask apply errors without a validation/re-enable plan. Subscriber data can become inconsistent.

### 8.5. Unique Indexes

Unique constraints/indexes can raise conflicts if the subscriber already holds local rows or data differing from the publisher. A subscription does not auto-resolve duplicate key conflicts. Before initial copy:
- Check whether subscriber tables already hold data.
- Use empty targets or a designed seeding procedure.
- Check for duplicate keys.
- Control all local writes to replicated tables.

### 8.6. Indexes

Indexes are not created by publications. The subscriber can hold different indexes, though indexes increase write/apply overhead. A unique index differing from the publisher can reject rows the publisher accepted. Balance query performance against apply throughput.

### 8.7. Triggers

Subscriber triggers can execute when applying rows depending on trigger type/replication role semantics. Triggers can:
- Produce duplicate side effects.
- Write audit/outbox entries a second time.
- Call external systems.
- Reject rows.
- Mutate subscriber data away from the publisher.

Design triggers to respect replication context, use appropriate trigger enable/replica semantics, and test thoroughly. Never let subscriber triggers fire emails/payments/webhooks on replicated rows.

### 8.8. Rules, Policies, and Row-Level Security

Views/rules/RLS policies do not replicate automatically. Verify apply worker privileges and subscriber table behavior under your version's role/replication context. Do not assume RLS automatically filters changes like application SELECTs.

### 8.9. Views and Materialized Views

Logical replication does not automatically sync view definitions or refresh materialized views. Deploy definitions on the subscriber and determine who refreshes materialized views, how often, and at what cost.

### 8.10. Functions and Procedures

Function definitions, procedures, event triggers, and scheduled jobs must be deployed separately. If a trigger or default calls a function, that function must exist on the subscriber with compatible semantics.

---

## 9. Partitioning, Row Filters, and Column Lists

### 9.1. Partitioned Tables

Publications can publish partitioned tables per configuration/version. Partitioning on publisher and subscriber does not always require identical physical layouts in supported topologies, yet relation mapping and partition add/drop behavior must be understood.

### 9.2. publish_via_partition_root

Supporting PostgreSQL versions provide this option to publish partitioned table changes under the partition root identity instead of leaf partitions. That affects relation mapping on the subscriber and how subscriber table/partition layouts are structured.

Verify version, publication definition, and subscriber partitioning before using. Do not assume every version shares identical behavior.

### 9.3. Differing Partition Layouts

The subscriber may need custom partitioning for read workloads or retention. When layouts differ from the publisher, verify:
- Root table mapping.
- Leaf partition mapping.
- Partition key/type.
- Routing rules on the subscriber.
- Behavior when new partitions are created.
- DDL deployment order.
- Initial table synchronization.

### 9.4. Row Filters

Row filters restrict published rows by condition. Filters must use supported columns/types/functions and appropriate semantics. If a filter relies on a renamed/dropped column or changing expression, the publication may need updating.

Row filters are not a standalone security boundary. Subscribers still require access controls and network isolation.

### 9.5. Column Lists

Column lists allow a publication to send only a subset of columns. Subscriber mappings must include required columns, and applications must understand which columns are not replicated. Column lists do not automatically populate defaults/data mappings for omitted columns.

### 9.6. TRUNCATE and Filters

TRUNCATE is a table-level operation, not a row-by-row DELETE. Never assume a row filter turns TRUNCATE into a subset deletion. Check version semantics and publication options; if the subscriber holds rows outside the publication filter, TRUNCATE can have a wider impact than intended.

### 9.7. Adding New Partitions

New partitions may be attached on the publisher and can alter publication membership/mapping in version-dependent ways. Check subscription table sync state and confirm new rows route to the right target. Deploy partition DDL via runbooks; never treat partition creation as an automatically replicated DML event.

---

## 10. Schema Evolution: Expand-and-Contract

### 10.1. Why Is a Multi-Step Rollout Needed?

While publisher and subscriber run concurrently, two schema versions coexist for a window. Migrations must keep all DML during that window applyable. Expand-and-contract adds new structures first, transitions applications, and only then removes old structures.

### 10.2. Adding a New Column

Suppose you need to add customer_tier:

**Step 1 — Expand subscriber first**

~~~sql
ALTER TABLE app.customers
ADD COLUMN customer_tier text;
~~~

**Step 2 — Expand publisher**

~~~sql
ALTER TABLE app.customers
ADD COLUMN customer_tier text;
~~~

**Step 3 — Deploy compatible application**

Old applications continue working while the column is nullable; new applications can start writing values once both schemas are ready.

**Step 4 — Backfill and validate**

Verify null counts, value domains, and publisher/subscriber parity.

**Step 5 — Contract when safe**

Add NOT NULL/drop old columns only after all application versions and subscribers have transitioned.

Exact ordering may vary by migration architecture, yet the subscriber must be ready before the apply worker receives rows needing the new column.

### 10.3. Renaming a Column

Do not rename directly on one side expecting logical replication to map automatically. Use two columns temporarily:
1. Add the new column on both sides.
2. Dual-write or backfill.
3. Update publication column list/mapping if applicable.
4. Switch consumers.
5. Stop writing the old column.
6. Drop the old column in the contract phase.

### 10.4. Type Widening

For example, integer to bigint:
1. Widen the subscriber column first.
2. Confirm the target accepts all publisher values.
3. Widen the publisher column.
4. Deploy application support for bigint.
5. Verify indexes/foreign keys/functions/casts.
6. Measure apply throughput and query plans.

Type narrowing requires range checks first and should generally be avoided while replication is active.

### 10.5. Enum Evolution

When adding an enum label:
1. Add the label on the subscriber first.
2. Check label order/semantics.
3. Add the label on the publisher.
4. Only then let applications write the new label.
5. Monitor apply errors and query behavior.

Never emit a new label on the publisher before the subscriber recognizes it.

### 10.6. Constraint Tightening

If adding NOT NULL/unique/check:
1. Backfill.
2. Verify existing data.
3. Create/validate constraints appropriately.
4. Deploy application changes.
5. Synchronize constraints on both sides.
6. Monitor apply errors.

### 10.7. Dropping Tables/Columns

Dropping is the final step after:
- No application version still uses the object.
- Publication/subscription membership is updated.
- Initial sync/refresh has completed.
- Backup/rollback paths are ready.
- Monitoring no longer references the object.
- Downstream consumers have switched.

### 10.8. Migration Version Tables

You can maintain a migration version table per database, though logical replication does not sync migration history automatically unless that table belongs to a publication. Manage migration state independently and record schema versions of publisher/subscriber in deployment inventories.

### 10.9. DDL Coordination Runbook

Each migration needs:
- Compatibility window.
- Order of apply on publisher/subscriber.
- Backward/forward compatibility assumptions.
- Initial sync/refresh requirements.
- Rollback plan.
- Data backfill strategy.
- Expected replication lag impact.
- Validation queries.
- Owner and cutover criteria.

---

## 11. Publication Changes and Subscription Refresh

### 11.1. Adding a Table to a Publication

When adding a table to a publication after a subscription already exists, the subscriber needs to refresh the publication to discover the new table. Example on publisher:

~~~sql
ALTER PUBLICATION app_pub
ADD TABLE app.invoices;
~~~

Then on subscriber:

~~~sql
ALTER SUBSCRIPTION app_sub
REFRESH PUBLICATION;
~~~

Depending on version and options, refresh can trigger table synchronization/initial data copy. Check exact syntax and copy_data behavior of your running release.

### 11.2. Refresh Does Not Create Schemas

REFRESH PUBLICATION updates the list of published relations tracked by the subscription. It does not automatically run CREATE TABLE or ALTER TABLE on the subscriber. Create target schemas before refreshing.

### 11.3. Removing a Table from a Publication

When removing a table from a publication, future changes for that table stop being sent under the new membership. Rows already on the subscriber generally remain; do not assume removing a table implies DELETing target tables/data.

If dropping or keeping subscriber data is needed, perform a separate migration after checking downstream consumers.

### 11.4. Changing Column Lists

If a publication uses a column list, list changes must be deployed alongside subscriber schemas. When adding a column to the list, the target must be ready before the publisher emits values. When removing a column, applications and subscriber schemas can retain that column during a compatibility window.

### 11.5. Changing Row Filters

Row filters change the row scope in the stream. They do not automatically delete previously copied rows that no longer satisfy the filter. If data reconciliation is needed, plan separate cleanup/backfill; never assume refresh automatically resyncs full table state.

### 11.6. pg_publication_tables

You can inspect table membership and row filters/column lists per version capabilities:

~~~sql
SELECT *
FROM pg_publication_tables
WHERE pubname = 'app_pub'
ORDER BY schemaname, tablename;
~~~

This view is useful for confirming which relations the publisher is publishing. Output fields can vary by version.

### 11.7. pg_publication

~~~sql
SELECT *
FROM pg_publication
WHERE pubname = 'app_pub';
~~~

Inspect publish operation flags and current options. Do not rely solely on migration source code; inspect live catalog state.

### 11.8. Table Synchronization State

On the subscriber, pg_subscription_rel stores sync state of relations in a subscription. Inspect via:

~~~sql
SELECT
    srrelid::regclass AS relation_name,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY relation_name;
~~~

State codes have version-specific meanings; consult documentation. Consider a table ready only after initial copy/sync finishes and apply is keeping up.

---

## 12. Initial Table Synchronization and Schema Readiness

### 12.1. Two Data Phases

When a subscription starts with copy_data enabled, PostgreSQL can:
1. Copy the initial snapshot of the table.
2. Concurrently track changes occurring during the copy.
3. Synchronize remaining changes.
4. Transition the table to normal replication state.

Worker/process details and state names vary by version. Schemas must be ready before copying starts.

### 12.2. Avoiding Conflicting Data on Subscriber

If target tables already contain data, initial copy can hit duplicate keys or unique conflicts. Choose one approach:
- Empty subscriber tables prior to initial copy.
- Seed data via a supported workflow and disable copy_data where appropriate.
- Use migration tooling capable of validating/coordinating snapshots.
- Restore/seed following an explicit protocol before enabling the subscription.

Never build an "almost identical" subscriber via manual copies expecting logical replication to reconcile all rows automatically.

### 12.3. copy_data=false

Depending on version, subscriptions offer copy_data to skip copying initial table contents. When choosing false, operators are responsible for ensuring the target already holds a baseline dataset matching the publisher with no data gap before streaming begins.

This is a high-risk option without snapshot/LSN coordination. Never enable it merely to bypass duplicate key errors.

### 12.4. Initial Copy and Schema Drift

If initial copy fails due to missing columns, type conversions, NOT NULL, unique constraints, or extensions, repair schemas/targets and follow the proper procedure to resume/reinitialize table sync. Never drop subscriptions/slots arbitrarily before recording slot ownership and restart positions.

### 12.5. Subscription State

Observe via:

~~~sql
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, relid;
~~~

Columns can differ across PostgreSQL releases. Combine pg_subscription_rel, subscriber logs, and pg_stat_activity to inspect table sync/apply workers.

### 12.6. Table Sync Does Not Equal Application Ready

A table may finish initial sync yet the application is still not ready if:
- Related tables have not finished syncing.
- Constraints/indexes have not been built.
- Sequence states are unsynchronized.
- Views/functions/extensions are missing.
- Business invariants fail.
- Apply lag remains.

A system-level readiness gate is required.

---

## 13. Detecting Schema Drift Between Publisher and Subscriber

### 13.1. What Is Schema Drift?

Schema drift is any unintended difference between the two sides. It can be:
- Missing/extra/renamed columns.
- Differing data types/typmods.
- Differing nullability/defaults.
- Differing replica identities/primary keys.
- Differing constraints/indexes.
- Differing enum/domain definitions.
- Differing extension/collation versions.
- Differing publication membership/filters.

Some differences are intentional, such as extra read indexes on the subscriber. Maintain an allowlist to separate intentional differences from bugs.

### 13.2. Comparing Columns

Run on both publisher and subscriber, export results, and diff:

~~~sql
SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_schema,
    udt_name,
    character_maximum_length,
    numeric_precision,
    numeric_scale,
    is_nullable,
    column_default,
    is_identity,
    identity_generation,
    is_generated,
    generation_expression
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
~~~

information_schema can filter by privileges and some fields depend on version. Use the exact same query and sufficiently privileged roles on both sides.

### 13.3. Comparing Replica Identity and Primary Keys

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relreplident AS replica_identity,
    i.indisprimary,
    i.indisunique,
    pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_index i ON i.indrelid = c.oid
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname, i.indisprimary DESC;
~~~

Catalog queries must account for partitioned/inherited tables and index validity. Never rely on a single output row as sole proof of complete replica identity behavior.

### 13.4. Comparing Constraints

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    con.conname,
    con.contype,
    con.convalidated,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname, con.conname;
~~~

Constraint definitions can differ in name/formatting even when semantics match. Review diffs carefully rather than doing blind text comparisons.

### 13.5. Comparing Indexes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, indexname;
~~~

The subscriber may carry extra indexes for read workloads; compare against an allowlist rather than requiring every index to be identical.

### 13.6. Comparing Publications and Subscriptions

On the publisher:

~~~sql
SELECT *
FROM pg_publication_tables
ORDER BY pubname, schemaname, tablename;
~~~

On the subscriber:

~~~sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications
FROM pg_subscription;
~~~

Catalog fields change across versions and can contain sensitive connection metadata. Never output connection strings/secrets into logs or tickets.

### 13.7. Schema Fingerprints

You can compute a schema fingerprint by normalizing relevant metadata (tables, columns, types, constraints, replica identity, publication membership) and hashing the output. Fingerprints should:
- Include only compatibility-relevant fields.
- Exclude OIDs and environment-specific metadata.
- Normalize ordering.
- Apply an allowlist for subscriber-only indexes/tables.
- Store schema version alongside the hash.
- Run after every migration.

Fingerprints detect drift; they do not replace semantic reviews and data conversion tests.

### 13.8. Schema Contracts

A schema contract should document:
- Replicated tables/columns.
- Data types and business meaning.
- Nullable/default rules.
- Primary keys/replica identities.
- Publication filters/column lists.
- Partitioning behavior.
- Required extensions/collations/enums.
- Subscriber-only objects.
- Migration ordering and compatibility windows.

---

## 14. Monitoring Apply Errors and Replication Health

### 14.1. Subscriber Logs

Apply worker errors are usually logged on the subscriber. Watch for:
- Missing target relations/columns.
- Type input/conversion failures.
- NOT NULL/CHECK/foreign key violations.
- Duplicate key conflicts.
- Replica identity lookup failures.
- Missing enum labels/extensions/functions.
- Permission errors.
- Worker exit/restart loops.

An apply error can stop subscription apply; replication lag then grows.

### 14.2. pg_stat_subscription

This view tracks subscription workers, received LSNs, and last message timestamps. Combine with logs to distinguish:
- No connection.
- Connected yet receiving no data.
- Receive advancing yet table sync unfinished.
- Apply worker erroring and restarting.
- Subscriber received data yet apply/commit is slow.

### 14.3. pg_stat_subscription_stats

Some PostgreSQL versions include a subscription error stats view, such as apply errors and sync errors. Check availability/columns by release. Track stats resets to calculate accurate deltas.

### 14.4. Publisher-Side Monitoring

Combine:
- pg_stat_replication for walsender connections where applicable.
- pg_replication_slots to inspect logical slot active/restart_lsn.
- pg_stat_wal to understand WAL generation.
- Publisher logs for slot/output plugin errors.
- pg_wal disk usage to catch slot-retained WAL.

### 14.5. Slot Retention

Logical replication slots retain WAL needed for subscriber decoding. If the subscriber stops or lags for long, slots can grow pg_wal. Never drop a slot without confirming the subscription/consumer and reinitialization impact.

### 14.6. Lag Metrics

You can measure LSN distance between current WAL and received/replayed positions, but do not convert it naively into time if WAL generation rates fluctuate widely. LSN distance is byte distance; time lag requires timestamps/heartbeats and workload context.

### 14.7. Heartbeat Tables

A published heartbeat table can measure end-to-end apply latency:
- Publisher updates heartbeat at intervals.
- Subscriber observes latest timestamp/sequence.
- Dashboard measures elapsed time from source marker to apply.
- Heartbeat rows must stay in the publication and schema contract.
- Never use heartbeats as a substitute for WAL LSN/slot monitoring.

### 14.8. Alerting

Useful alerts:
- Subscription disabled/disconnected.
- New apply worker error.
- Last received/applied heartbeat stale while publisher has writes.
- Inactive replication slot retaining WAL beyond budget.
- pg_wal disk pressure.
- Table sync state not completing within SLA.
- Schema fingerprint changed outside a migration.
- Version pair outside compatibility matrix.

Alerts must include cluster, subscription, table, error context, and runbook owner.

---

## 15. Troubleshooting Schema Compatibility

### 15.1. Column Does Not Exist

Causes:
- DDL not yet run on subscriber.
- Publisher column list recently changed.
- Uncoordinated rename.
- Table sync using an old schema.

Resolution: read subscriber logs, identify relation/column, check publication column list, deploy compatible subscriber schema, and resume/retry per procedure.

### 15.2. Type Conversion Failure

Causes:
- Unparseable value.
- Smaller target range/precision.
- Missing enum label.
- Domain/check constraint rejection.
- Incompatible extension type/input function.

Resolution: extract sanitized sample row/key from logs, inspect source/target definitions, test conversion in staging, and backfill/normalize data before resuming.

### 15.3. Duplicate Key

Causes:
- Subscriber already held seed/local rows.
- Applications wrote to the subscriber.
- Initial copy re-ran on a non-empty table.
- Incorrect key mapping/sequence strategy.

Resolution: identify conflicting rows, compare against the authoritative source, stop local writes, and choose controlled reseed or reconciliation. Never delete rows merely to let the worker continue without knowing ownership.

### 15.4. UPDATE/DELETE Cannot Find Row

Causes:
- Subscriber data drifted.
- Incompatible replica identity.
- Row deleted by a local process.
- Type conversion altered keys.
- Mismatched initial copy/slot start position.

Resolution: check keys/replica identity on both sides, row presence, and subscription state; resync/reseed if necessary.

### 15.5. Foreign Key Violation

Causes:
- Referenced table omitted from publication.
- Target rows not seeded yet.
- Incompatible apply order/transaction behavior.
- Differing schema constraints.

Resolution: inspect publication scope, FK graph, and data baselines. Never permanently disable FKs to mask errors.

### 15.6. Table Sync Incomplete

Check pg_subscription_rel, sync worker logs, table sizes, lock contention, network throughput, disk space, conflicts, and schemas. Before restarting table sync, understand copy_data, slot state, and duplicate risks.

### 15.7. Subscriber Version Older Than Publisher

Verify compatibility direction and protocol support. Do not work around it by downgrading schemas or hacking replication protocols. Use a supported subscriber version or choose another migration strategy.

### 15.8. Publication Refresh Does Not See New Table

Check:
- Did ALTER PUBLICATION succeed?
- Did the subscription run REFRESH PUBLICATION?
- Does the table have proper permissions/owner and schema?
- Does the subscriber target table already exist?
- Is the subscription enabled and are workers running?
- Does the version support the publication options used?

---

## 11. Publication Changes and Subscription Refresh

### 11.1. Adding a Table to a Publication

When adding a table to a publication after a subscription already exists, the subscriber needs to refresh the publication to discover the new table. Example on publisher:

~~~sql
ALTER PUBLICATION app_pub
ADD TABLE app.invoices;
~~~

Then on subscriber:

~~~sql
ALTER SUBSCRIPTION app_sub
REFRESH PUBLICATION;
~~~

Depending on version and options, refresh can trigger table synchronization/initial data copy. Check exact syntax and copy_data behavior of your running release.

### 11.2. Refresh Does Not Create Schemas

REFRESH PUBLICATION updates the list of published relations tracked by the subscription. It does not automatically run CREATE TABLE or ALTER TABLE on the subscriber. Create target schemas before refreshing.

### 11.3. Removing a Table from a Publication

When removing a table from a publication, future changes for that table stop being sent under the new membership. Rows already on the subscriber generally remain; do not assume removing a table implies DELETing target tables/data.

If dropping or keeping subscriber data is needed, perform a separate migration after checking downstream consumers.

### 11.4. Changing Column Lists

If a publication uses a column list, list changes must be deployed alongside subscriber schemas. When adding a column to the list, the target must be ready before the publisher emits values. When removing a column, applications and subscriber schemas can retain that column during a compatibility window.

### 11.5. Changing Row Filters

Row filters change the row scope in the stream. They do not automatically delete previously copied rows that no longer satisfy the filter. If data reconciliation is needed, plan separate cleanup/backfill; never assume refresh automatically resyncs full table state.

### 11.6. pg_publication_tables

You can inspect table membership and row filters/column lists per version capabilities:

~~~sql
SELECT *
FROM pg_publication_tables
WHERE pubname = 'app_pub'
ORDER BY schemaname, tablename;
~~~

This view is useful for confirming which relations the publisher is publishing. Output fields can vary by version.

### 11.7. pg_publication

~~~sql
SELECT *
FROM pg_publication
WHERE pubname = 'app_pub';
~~~

Inspect publish operation flags and current options. Do not rely solely on migration source code; inspect live catalog state.

### 11.8. Table Synchronization State

On the subscriber, pg_subscription_rel stores sync state of relations in a subscription. Inspect via:

~~~sql
SELECT
    srrelid::regclass AS relation_name,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY relation_name;
~~~

State codes have version-specific meanings; consult documentation. Consider a table ready only after initial copy/sync finishes and apply is keeping up.

---

## 12. Initial Table Synchronization and Schema Readiness

### 12.1. Two Data Phases

When a subscription starts with copy_data enabled, PostgreSQL can:
1. Copy the initial snapshot of the table.
2. Concurrently track changes occurring during the copy.
3. Synchronize remaining changes.
4. Transition the table to normal replication state.

Worker/process details and state names vary by version. Schemas must be ready before copying starts.

### 12.2. Avoiding Conflicting Data on Subscriber

If target tables already contain data, initial copy can hit duplicate keys or unique conflicts. Choose one approach:
- Empty subscriber tables prior to initial copy.
- Seed data via a supported workflow and disable copy_data where appropriate.
- Use migration tooling capable of validating/coordinating snapshots.
- Restore/seed following an explicit protocol before enabling the subscription.

Never build an "almost identical" subscriber via manual copies expecting logical replication to reconcile all rows automatically.

### 12.3. copy_data=false

Depending on version, subscriptions offer copy_data to skip copying initial table contents. When choosing false, operators are responsible for ensuring the target already holds a baseline dataset matching the publisher with no data gap before streaming begins.

This is a high-risk option without snapshot/LSN coordination. Never enable it merely to bypass duplicate key errors.

### 12.4. Initial Copy and Schema Drift

If initial copy fails due to missing columns, type conversions, NOT NULL, unique constraints, or extensions, repair schemas/targets and follow the proper procedure to resume/reinitialize table sync. Never drop subscriptions/slots arbitrarily before recording slot ownership and restart positions.

### 12.5. Subscription State

Observe via:

~~~sql
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, relid;
~~~

Columns can differ across PostgreSQL releases. Combine pg_subscription_rel, subscriber logs, and pg_stat_activity to inspect table sync/apply workers.

### 12.6. Table Sync Does Not Equal Application Ready

A table may finish initial sync yet the application is still not ready if:
- Related tables have not finished syncing.
- Constraints/indexes have not been built.
- Sequence states are unsynchronized.
- Views/functions/extensions are missing.
- Business invariants fail.
- Apply lag remains.

A system-level readiness gate is required.

---

## 13. Detecting Schema Drift Between Publisher and Subscriber

### 13.1. What Is Schema Drift?

Schema drift is any unintended difference between the two sides. It can be:
- Missing/extra/renamed columns.
- Differing data types/typmods.
- Differing nullability/defaults.
- Differing replica identities/primary keys.
- Differing constraints/indexes.
- Differing enum/domain definitions.
- Differing extension/collation versions.
- Differing publication membership/filters.

Some differences are intentional, such as extra read indexes on the subscriber. Maintain an allowlist to separate intentional differences from bugs.

### 13.2. Comparing Columns

Run on both publisher and subscriber, export results, and diff:

~~~sql
SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_schema,
    udt_name,
    character_maximum_length,
    numeric_precision,
    numeric_scale,
    is_nullable,
    column_default,
    is_identity,
    identity_generation,
    is_generated,
    generation_expression
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
~~~

information_schema can filter by privileges and some fields depend on version. Use the exact same query and sufficiently privileged roles on both sides.

### 13.3. Comparing Replica Identity and Primary Keys

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relreplident AS replica_identity,
    i.indisprimary,
    i.indisunique,
    pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_index i ON i.indrelid = c.oid
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname, i.indisprimary DESC;
~~~

Catalog queries must account for partitioned/inherited tables and index validity. Never rely on a single output row as sole proof of complete replica identity behavior.

### 13.4. Comparing Constraints

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    con.conname,
    con.contype,
    con.convalidated,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname, con.conname;
~~~

Constraint definitions can differ in name/formatting even when semantics match. Review diffs carefully rather than doing blind text comparisons.

### 13.5. Comparing Indexes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, indexname;
~~~

The subscriber may carry extra indexes for read workloads; compare against an allowlist rather than requiring every index to be identical.

### 13.6. Comparing Publications and Subscriptions

On the publisher:

~~~sql
SELECT *
FROM pg_publication_tables
ORDER BY pubname, schemaname, tablename;
~~~

On the subscriber:

~~~sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications
FROM pg_subscription;
~~~

Catalog fields change across versions and can contain sensitive connection metadata. Never output connection strings/secrets into logs or tickets.

### 13.7. Schema Fingerprints

You can compute a schema fingerprint by normalizing relevant metadata (tables, columns, types, constraints, replica identity, publication membership) and hashing the output. Fingerprints should:
- Include only compatibility-relevant fields.
- Exclude OIDs and environment-specific metadata.
- Normalize ordering.
- Apply an allowlist for subscriber-only indexes/tables.
- Store schema version alongside the hash.
- Run after every migration.

Fingerprints detect drift; they do not replace semantic reviews and data conversion tests.

### 13.8. Schema Contracts

A schema contract should document:
- Replicated tables/columns.
- Data types and business meaning.
- Nullable/default rules.
- Primary keys/replica identities.
- Publication filters/column lists.
- Partitioning behavior.
- Required extensions/collations/enums.
- Subscriber-only objects.
- Migration ordering and compatibility windows.

---

## 14. Monitoring Apply Errors and Replication Health

### 14.1. Subscriber Logs

Apply worker errors are usually logged on the subscriber. Watch for:
- Missing target relations/columns.
- Type input/conversion failures.
- NOT NULL/CHECK/foreign key violations.
- Duplicate key conflicts.
- Replica identity lookup failures.
- Missing enum labels/extensions/functions.
- Permission errors.
- Worker exit/restart loops.

An apply error can stop subscription apply; replication lag then grows.

### 14.2. pg_stat_subscription

This view tracks subscription workers, received LSNs, and last message timestamps. Combine with logs to distinguish:
- No connection.
- Connected yet receiving no data.
- Receive advancing yet table sync unfinished.
- Apply worker erroring and restarting.
- Subscriber received data yet apply/commit is slow.

### 14.3. pg_stat_subscription_stats

Some PostgreSQL versions include a subscription error stats view, such as apply errors and sync errors. Check availability/columns by release. Track stats resets to calculate accurate deltas.

### 14.4. Publisher-Side Monitoring

Combine:
- pg_stat_replication for walsender connections where applicable.
- pg_replication_slots to inspect logical slot active/restart_lsn.
- pg_stat_wal to understand WAL generation.
- Publisher logs for slot/output plugin errors.
- pg_wal disk usage to catch slot-retained WAL.

### 14.5. Slot Retention

Logical replication slots retain WAL needed for subscriber decoding. If the subscriber stops or lags for long, slots can grow pg_wal. Never drop a slot without confirming the subscription/consumer and reinitialization impact.

### 14.6. Lag Metrics

You can measure LSN distance between current WAL and received/replayed positions, but do not convert it naively into time if WAL generation rates fluctuate widely. LSN distance is byte distance; time lag requires timestamps/heartbeats and workload context.

### 14.7. Heartbeat Tables

A published heartbeat table can measure end-to-end apply latency:
- Publisher updates heartbeat at intervals.
- Subscriber observes latest timestamp/sequence.
- Dashboard measures elapsed time from source marker to apply.
- Heartbeat rows must stay in the publication and schema contract.
- Never use heartbeats as a substitute for WAL LSN/slot monitoring.

### 14.8. Alerting

Useful alerts:
- Subscription disabled/disconnected.
- New apply worker error.
- Last received/applied heartbeat stale while publisher has writes.
- Inactive replication slot retaining WAL beyond budget.
- pg_wal disk pressure.
- Table sync state not completing within SLA.
- Schema fingerprint changed outside a migration.
- Version pair outside compatibility matrix.

Alerts must include cluster, subscription, table, error context, and runbook owner.

---

## 15. Troubleshooting Schema Compatibility

### 15.1. Column Does Not Exist

Causes:
- DDL not yet run on subscriber.
- Publisher column list recently changed.
- Uncoordinated rename.
- Table sync using an old schema.

Resolution: read subscriber logs, identify relation/column, check publication column list, deploy compatible subscriber schema, and resume/retry per procedure.

### 15.2. Type Conversion Failure

Causes:
- Unparseable value.
- Smaller target range/precision.
- Missing enum label.
- Domain/check constraint rejection.
- Incompatible extension type/input function.

Resolution: extract sanitized sample row/key from logs, inspect source/target definitions, test conversion in staging, and backfill/normalize data before resuming.

### 15.3. Duplicate Key

Causes:
- Subscriber already held seed/local rows.
- Applications wrote to the subscriber.
- Initial copy re-ran on a non-empty table.
- Incorrect key mapping/sequence strategy.

Resolution: identify conflicting rows, compare against the authoritative source, stop local writes, and choose controlled reseed or reconciliation. Never delete rows merely to let the worker continue without knowing ownership.

### 15.4. UPDATE/DELETE Cannot Find Row

Causes:
- Subscriber data drifted.
- Incompatible replica identity.
- Row deleted by a local process.
- Type conversion altered keys.
- Mismatched initial copy/slot start position.

Resolution: check keys/replica identity on both sides, row presence, and subscription state; resync/reseed if necessary.

### 15.5. Foreign Key Violation

Causes:
- Referenced table omitted from publication.
- Target rows not seeded yet.
- Incompatible apply order/transaction behavior.
- Differing schema constraints.

Resolution: inspect publication scope, FK graph, and data baselines. Never permanently disable FKs to mask errors.

### 15.6. Table Sync Incomplete

Check pg_subscription_rel, sync worker logs, table sizes, lock contention, network throughput, disk space, conflicts, and schemas. Before restarting table sync, understand copy_data, slot state, and duplicate risks.

### 15.7. Subscriber Version Older Than Publisher

Verify compatibility direction and protocol support. Do not work around it by downgrading schemas or hacking replication protocols. Use a supported subscriber version or choose another migration strategy.

### 15.8. Publication Refresh Does Not See New Table

Check:
- Did ALTER PUBLICATION succeed?
- Did the subscription run REFRESH PUBLICATION?
- Does the table have proper permissions/owner and schema?
- Does the subscriber target table already exist?
- Is the subscription enabled and are workers running?
- Does the version support the publication options used?

---

## 16. Major Version Upgrade Using Logical Replication

### 16.1. When to Choose Logical Replication?

Logical replication can fit when:
- The database is large and downtime must be minimized compared to dump/restore.
- Old publisher and new subscriber can run side by side.
- Applications tolerate a short cutover window.
- Schemas can be prepared compatibly.
- There is no reliance on objects/data not transferred automatically by logical replication.
- Capacity exists to run two clusters plus initial copy.

### 16.2. When to Consider Alternatives?

Logical replication may not fit if:
- Applications use many large objects needing separate transfer.
- Complex schemas/types make compatibility hard to maintain.
- Workloads run frequent uncoordinated DDL migrations.
- The subscriber needs exact live sequence states mid-run.
- Heavy local writes occur on the subscriber.
- Downtime is acceptable and dump/restore or pg_upgrade is simpler.

### 16.3. Comparing Major Upgrade Methods

| Method | Characteristics | Considerations |
|---|---|---|
| pg_upgrade | In-place/side-by-side major upgrade via supported mechanics | Downtime, extension compatibility, rollback window |
| Dump/restore | Logical export/import | Dump/restore duration, object coverage, sequence/global state |
| Logical replication | Copy baseline then stream changes | Schema coordination, unsupported objects, cutover correctness |
| Physical replica upgrade workflow | Tool/vendor-specific supported procedure | WAL format/major version restrictions, tool-specific process |

No single method is best for every system. Choose by downtime budget, database size, feature usage, and verifiability.

### 16.4. Pre-Upgrade Inventory

Inventory:
- PostgreSQL major/minor versions.
- Database encoding/collation.
- Extensions and versions.
- Tables/partitioned tables.
- Primary keys/replica identities.
- Sequences/identity columns.
- Large objects.
- Unlogged/temp tables.
- Publications/subscriptions/slots.
- Pending DDL migrations.
- Custom types/domains/enums.
- Triggers/functions/rules.
- Foreign keys and unique constraints.
- Roles/grants/RLS.
- Jobs/schedulers/external integrations.

### 16.5. Provisioning the New Subscriber

1. Install target PostgreSQL major version.
2. Install matching extension packages/binaries.
3. Create roles, schemas, types, and tables.
4. Create indexes/constraints compatible with initial copy/apply.
5. Create publication-compatible mappings.
6. Configure WAL, replication privileges, and networking.
7. Create the subscription.
8. Monitor initial table synchronization.
9. Validate counts/keys/business invariants.
10. Wait for streaming catch-up.

### 16.6. Publications in Upgrades

You can create an explicit publication:

~~~sql
CREATE PUBLICATION upgrade_pub
FOR TABLE app.customers, app.orders, app.order_items;
~~~

Or use FOR ALL TABLES when appropriate for version, ownership, and scope. ALL TABLES publications can automatically include new tables per semantics; you still must create target schemas on the subscriber and respect object restrictions.

### 16.7. Creating the Subscription

~~~sql
CREATE SUBSCRIPTION upgrade_sub
CONNECTION 'host=old-primary.example.net port=5432 dbname=appdb user=replicator'
PUBLICATION upgrade_pub
WITH (copy_data = true, create_slot = true, enabled = true);
~~~

Examples use illustrative names/credentials. In production:
- Store secrets in a secret manager.
- Use TLS/verify-ca or verify-full appropriately.
- Configure pg_hba.conf/roles with least privilege.
- Verify the slot was created properly and has an owner.
- Account for heavy publisher load during initial copy.

### 16.8. Capacity During Dual-Cluster Operation

Initial copy and logical decoding add load:
- Read I/O on the publisher.
- Network throughput.
- Disk/write I/O on the subscriber.
- WAL retention via logical slots.
- CPU for decoding/apply/index maintenance.
- Increased storage for two live copies.
- Monitoring/backups for both clusters.

Provision ample disk headroom. If the subscriber lags, logical slots can retain WAL on the publisher and fill pg_wal.

### 16.9. Schema Changes During Upgrade

Keep applications compatible with both schemas during migration. If the target major version alters behaviors/types, test queries, casts, collations, extensions, and functions. Logical replication does not automatically fix schemas or application SQL.

### 16.10. Cutover

A controlled cutover:
1. Freeze DDL and deployment windows.
2. Stop new writes on the publisher or put applications into maintenance/read-only mode.
3. Wait for open transactions to finish.
4. Record final publisher LSN/marker.
5. Wait for subscriber apply to finish up to the final marker/LSN using appropriate origin progress.
6. Verify table sync states, row counts, and business checks.
7. Stop/disable the subscription per runbook.
8. Update application connections/routing to the subscriber.
9. Open writes on the new cluster.
10. Monitor errors, sequence values, latency, and business metrics.

pg_stat_subscription.latest_end_lsn shows reported progress, yet should not be used alone as proof every transaction applied. Use replication-origin progress/apply state and a confirmed marker transaction.

### 16.11. Sequence Handoff

Before opening writes on the subscriber, synchronize sequence values so new IDs do not collide with replicated IDs. Account for:
- Current maximum keys.
- Increment/min/max.
- is_called.
- Cache/preallocated values.
- Sequences shared across multiple tables.
- Sequence cycling.

### 16.12. Post-Cutover Rollback

Once the subscriber starts accepting independent writes, you cannot simply route traffic back to the old publisher because the publisher missed those new writes. You must:
- Keep the old publisher read-only.
- Save final cutover markers.
- Define a rollback window and clear criteria.
- If writes already occurred on the subscriber, have a reconciliation/reverse-replication or restore/replay plan.
- Never open concurrent writes on both sides without a designed conflict strategy.

---

## 17. Security and Operational Boundaries

### 17.1. Replication Role

Create a dedicated role with minimum required privileges. Logical replication needs replication/connection privileges and table read privileges for initial copy per version/config. Never use superuser as a replication account merely for convenience.

### 17.2. pg_hba.conf and Network

Permit only exact source IPs/subscriber hosts, databases, and replication users. Use TLS across untrusted networks; verify certificates/hostnames and rotate credentials per policy.

### 17.3. Passwords/Connection Strings

Connection strings can contain secrets stored in catalog metadata. Restrict catalog access, avoid logging raw conninfo, follow secret rotation procedures, and ensure backups/exports do not leak credentials.

### 17.4. Publication Scope

Publish only required tables/columns. Unnecessary data should not traverse replication merely because FOR ALL TABLES was used. Row filters/column lists reduce scope, yet do not replace security design.

### 17.5. Subscriber Access

Subscribers are typically read by applications. Restrict local writes on replicated tables and isolate local-only schemas/tables. Use role privileges to prevent accidental edits to replicated data.

---

## 18. Preflight Checklist Before Enabling Subscriptions

### 18.1. Version

- [ ] Publisher/subscriber major versions follow a supported direction.
- [ ] Replication protocol/output plugin is compatible.
- [ ] Publication options exist on the publisher version.
- [ ] Monitoring views/columns exist on both sides.
- [ ] Extensions installed at matching major versions.

### 18.2. Schema

- [ ] Target tables exist.
- [ ] Published columns have valid mappings.
- [ ] Data types/typmods are compatible.
- [ ] Nullability/default/generated/identity semantics tested.
- [ ] Primary key/replica identity appropriate for UPDATE/DELETE.
- [ ] Enum/domain/collation definitions compatible.
- [ ] Constraints do not reject publisher rows.
- [ ] Subscriber-only columns have proper default/nullable/generated behavior.
- [ ] Partition mapping and publication options verified.

### 18.3. Data Baseline

- [ ] Subscriber tables empty or seeded in a controlled manner.
- [ ] Initial copy/copy_data policy clear.
- [ ] Duplicate key risks checked.
- [ ] Foreign key dependencies in scope or handled.
- [ ] Sequence state has a handoff plan.
- [ ] Large objects/unsupported objects have a migration plan.

### 18.4. Operations

- [ ] Replication role, pg_hba, and TLS working.
- [ ] Slot owner/restart position recorded.
- [ ] Disk/WAL headroom sufficient.
- [ ] Initial copy bandwidth estimated.
- [ ] Apply errors/lag alerts configured.
- [ ] DDL change process frozen/coordinated.
- [ ] Rollback/cutover owner and criteria clear.

---

## 19. Lab: Schema Compatibility and Publication Refresh

### 19.1. Prepare the Publisher

~~~sql
CREATE SCHEMA IF NOT EXISTS compat_lab;

CREATE TABLE compat_lab.accounts (
    account_id bigint PRIMARY KEY,
    display_name text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE PUBLICATION compat_pub
FOR TABLE compat_lab.accounts;
~~~

### 19.2. Prepare the Subscriber

Create the matching schema/table before creating the subscription:

~~~sql
CREATE SCHEMA IF NOT EXISTS compat_lab;

CREATE TABLE compat_lab.accounts (
    account_id bigint PRIMARY KEY,
    display_name text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

### 19.3. Create the Subscription

~~~sql
CREATE SUBSCRIPTION compat_sub
CONNECTION 'host=publisher.lab port=5432 dbname=appdb user=replicator'
PUBLICATION compat_pub;
~~~

Monitor initial sync and inspect rows after the table reaches ready state.

### 19.4. Add a Subscriber-Only Column

On the subscriber:

~~~sql
ALTER TABLE compat_lab.accounts
ADD COLUMN local_note text;
~~~

Test an INSERT on the publisher. Observe the subscriber receiving the row with local_note set to NULL/default per its schema. Do not treat local_note as authoritative source data if it is not published.

### 19.5. Add a New Column in the Right Order

On the subscriber first:

~~~sql
ALTER TABLE compat_lab.accounts
ADD COLUMN tier text;
~~~

Then on the publisher:

~~~sql
ALTER TABLE compat_lab.accounts
ADD COLUMN tier text;
~~~

Insert a new row with tier and verify apply succeeds.

### 19.6. Type Widening

On the subscriber, widen a display or numeric test column first; then alter the publisher per plan. Test large values and confirm the subscriber does not reject conversions. Do not test type narrowing in this lab without backing up test data/rollback paths.

### 19.7. Publication Refresh

On the publisher:

~~~sql
CREATE TABLE compat_lab.regions (
    region_id integer PRIMARY KEY,
    region_name text NOT NULL
);

ALTER PUBLICATION compat_pub
ADD TABLE compat_lab.regions;
~~~

Create the target table on the subscriber, then run:

~~~sql
ALTER SUBSCRIPTION compat_sub
REFRESH PUBLICATION;
~~~

Monitor pg_subscription_rel to confirm table sync state completes.

### 19.8. Compare Schema Metadata

Run the information_schema.columns query on both databases, export results, and diff. Document intentional differences such as local_note; do not treat every difference as an error.

---

## 20. Lab: Replica Identity and Apply Behavior

### 20.1. Create a Table Without a Primary Key

On the publisher:

~~~sql
CREATE TABLE compat_lab.no_key (
    code text NOT NULL,
    payload text NOT NULL
);

ALTER PUBLICATION compat_pub
ADD TABLE compat_lab.no_key;
~~~

Create the matching target on the subscriber. When needing to publish UPDATE/DELETE, choose an appropriate replica identity before running DML.

### 20.2. Test REPLICA IDENTITY FULL

~~~sql
ALTER TABLE compat_lab.no_key
REPLICA IDENTITY FULL;
~~~

Perform INSERT, UPDATE, and DELETE on the publisher; observe apply on the subscriber. Measure the growth in data/logical WAL and compare against a table with a primary key.

### 20.3. Test a Unique Index

Create a unique index eligible as replica identity on both publisher and subscriber; switch to REPLICA IDENTITY USING INDEX. Verify index validity, uniqueness, NOT NULL semantics, and UPDATE/DELETE apply.

### 20.4. Test a Controlled Mismatch

In an isolated lab:
- Add a stricter CHECK constraint on the subscriber.
- Emit a row violating that condition from the publisher.
- Observe the apply error in subscriber logs.
- Record subscription state/worker behavior.
- Repair the schema or data per your chosen plan and resume using the version-appropriate procedure.

Never run mismatch tests on a shared subscription carrying data you need to keep.

---

## 21. Practice Exercises

Questions use a PostgreSQL lab. Never alter production schemas/replication merely to test a hypothesis.

### Exercise 1 — Logical Replication

What does logical replication synchronize? Which object types require separate migrations?

### Exercise 2 — Publisher and Subscriber

Distinguish publisher, publication, subscriber, and subscription.

### Exercise 3 — Version Direction

Why is an older major version publisher and newer major version subscriber typically used during upgrades?

### Exercise 4 — DDL

Do CREATE TABLE or ALTER TABLE statements on the publisher automatically appear on the subscriber? What must be done?

### Exercise 5 — Column Mapping

Are columns mapped by name or ordinal position? Why does this matter when adding columns?

### Exercise 6 — Extra Subscriber Column

The subscriber has an extra nullable column excluded from the publication. What happens when the publisher INSERTs a row?

### Exercise 7 — Missing Subscriber Column

The publisher begins emitting a new column that the subscriber lacks. Why must schemas be prepared beforehand?

### Exercise 8 — Type Widening

Why is integer to bigint usually easier to roll out than bigint to integer?

### Exercise 9 — Type Conversion

Is publisher text to subscriber uuid always safe? State the conditions.

### Exercise 10 — Timestamps

Why should timestamp without time zone and timestamptz not be treated as semantically identical?

### Exercise 11 — Enum

The publisher adds a new enum label. What is the safe deployment order on subscriber and publisher?

### Exercise 12 — Domain

A subscriber domain has a stricter CHECK constraint than the publisher. What can happen during row apply?

### Exercise 13 — Collation

Which behaviors can differing collation/ICU versions affect?

### Exercise 14 — Replica Identity

What is replica identity used for? How do DEFAULT, USING INDEX, FULL, and NOTHING differ?

### Exercise 15 — Primary Key

Why do UPDATE/DELETE require an appropriate replica identity? What happens if subscriber data has drifted?

### Exercise 16 — Sequence

Does logical replication synchronize current sequence values? What must be done before promoting a subscriber?

### Exercise 17 — Generated Columns

Why must generated expressions match between both sides?

### Exercise 18 — Triggers

What side effects can subscriber triggers cause when applying replicated rows?

### Exercise 19 — Foreign Keys

The subscriber has an FK referencing an unpublished table. What error can occur?

### Exercise 20 — Partitioning

What does publish_via_partition_root control? Why is version-gating necessary?

### Exercise 21 — Row Filters

If a row filter changes, are previously copied rows that no longer satisfy the filter automatically deleted from the subscriber?

### Exercise 22 — TRUNCATE

Why must special caution be taken with TRUNCATE in publications with row filters?

### Exercise 23 — Publication Refresh

After ADD TABLE to a publication, what action does the subscriber need? Does that action create the target schema?

### Exercise 24 — Initial Copy

What must operators guarantee when using copy_data=false?

### Exercise 25 — Duplicate Key

Initial copy hits a duplicate key. List possible causes and safe resolutions.

### Exercise 26 — Schema Drift

List at least six types of schema drift that can break apply or alter data semantics.

### Exercise 27 — Schema Fingerprint

Which fields should a schema fingerprint include and which metadata should it exclude?

### Exercise 28 — Monitoring

Explain the roles of pg_stat_subscription, pg_subscription_rel, and subscriber logs.

### Exercise 29 — Slot Retention

Why can a logical replication slot cause pg_wal to grow? Should an inactive slot be dropped immediately?

### Exercise 30 — Major Upgrade

List the phases of a major upgrade using logical replication from preflight to cutover.

### Exercise 31 — Final LSN

Why should pg_stat_subscription.latest_end_lsn alone not be used as proof all transactions applied?

### Exercise 32 — Cutover Writes

Why must writes on the publisher stop before switching applications to the subscriber?

### Exercise 33 — Rollback

After the subscriber accepts new writes, why can you not simply switch back to the old publisher?

### Exercise 34 — Extensions

Why must extension binaries be installed separately on a new major version subscriber?

### Exercise 35 — Large Objects

Does logical replication automatically transfer large objects? What must be prepared?

### Exercise 36 — Schema Contract

What should a schema contract document to reduce drift?

### Exercise 37 — Subscriber-Only Index

The subscriber adds an index for reads. Is this necessarily a schema incompatibility? What must be considered?

### Exercise 38 — DDL Deployment

Write an expand-and-contract sequence for adding a new NOT NULL column.

### Exercise 39 — Apply Error

Subscriber logs report invalid input syntax for type uuid. Outline the investigation and repair steps.

### Exercise 40 — Comprehensive

A subscriber is newer than the publisher; initial copy succeeded, yet after a new enum migration the apply worker fails. Identify the root cause, resolution, and prevention steps.

---

## 22. Solutions — Exercises 1 to 20

### Exercise 1 — Logical Replication

It synchronizes row changes for tables in the publication for enabled operations. DDL, roles/grants, indexes, constraints, functions, views, extension binaries, sequence states, and large objects require separate workflows.

### Exercise 2 — Publisher and Subscriber

The publisher creates publications and emits changes; a publication defines tables/operations; the subscriber creates a subscription to connect and apply changes into target tables.

### Exercise 3 — Version Direction

Newer subscribers generally support the replication protocols/features of older publishers and suit major upgrades. Newer-publisher to older-subscriber is not supported by default; check release-specific compatibility docs.

### Exercise 4 — DDL

No. Logical replication does not automatically synchronize DDL. Use migration tools/deployment scripts to create/alter compatible schemas on the subscriber in a safe order.

### Exercise 5 — Column Mapping

Mapped by column name, not ordinal position. Thus column reordering is not a mapping strategy; matching names, types, and semantics are what matter.

### Exercise 6 — Extra Subscriber Column

If the column is nullable or can be supplied with a valid value, the subscriber can apply the row and the extra column receives NULL/default per insert behavior. Test with the exact publication column list and version; NOT NULL without default can fail apply.

### Exercise 7 — Missing Subscriber Column

The subscriber does not create columns automatically. Once the publisher begins sending values for the new column, target mapping/schema can be incompatible. Add and verify the column on the subscriber before publishing new writes.

### Exercise 8 — Type Widening

Bigint contains the entire integer range; integer does not contain the entire bigint range. Widening preserves existing values, whereas narrowing risks overflow.

### Exercise 9 — Type Conversion

No. Every source value must be parseable as a UUID and accepted by target constraints. Audit historical/new data and malformed strings before migrating.

### Exercise 10 — Timestamps

timestamp without time zone represents a local date/time without an attached instant; timestamptz represents an instant displayed per session timezone. Converting can shift temporal meaning.

### Exercise 11 — Enum

Add the label on the subscriber first, confirm definition/order, then add it on the publisher, and only afterward let applications emit the new label.

### Exercise 12 — Domain

Row apply can be rejected by the subscriber due to stricter CHECK/domain constraints, causing apply worker errors and rising lag. Align semantics or normalize data before publishing.

### Exercise 13 — Collation

Can alter sort order, equality/comparisons, unique index behavior, and query results. Check provider/locale/version and reindex requirements.

### Exercise 14 — Replica Identity

Provides old-row identity for UPDATE/DELETE. DEFAULT uses primary key; USING INDEX uses an eligible unique index; FULL sends old row values; NOTHING sends no identity and fits only when UPDATE/DELETE identity is unneeded.

### Exercise 15 — Primary Key

Apply must locate target rows. If subscriber data drifted or keys differ, UPDATE/DELETE can miss rows or alter wrong rows; validate key parity and resync if needed.

### Exercise 16 — Sequence

No. Before promotion, synchronize sequence state/next values using setval or appropriate tools after stopping writes and checking used IDs; verify increment/cache/is_called.

### Exercise 17 — Generated Columns

The subscriber computes expressions from input columns locally; differing expressions produce results diverging from the publisher. Align definitions and test values.

### Exercise 18 — Triggers

Triggers can write duplicate audit/outbox entries, trigger emails/payments/webhooks, reject rows, or mutate other tables. Design triggers to respect replication roles and block unintended side effects.

### Exercise 19 — Foreign Keys

Row apply can fail FK checks if referenced rows do not exist/are unpublished or baselines are unsynced. Verify publication scope, ordering, and data baselines.

### Exercise 20 — Partitioning

The option decides whether changes are published under the partition root identity or leaf relations, affecting target mapping. Behavior and option support vary by major version, so version-gating is essential.

---

## 23. Solutions — Exercises 21 to 40

### Exercise 21 — Row Filters

No. Changing a filter adjusts future emitted changes; previously copied rows that no longer satisfy the filter usually remain on the subscriber. Separate cleanup/reconciliation is required if business rules demand it.

### Exercise 22 — TRUNCATE

TRUNCATE is a table-level operation, not a row-level delete. Row filters do not turn TRUNCATE into a subset deletion; the subscriber may truncate the whole matching table. Check semantics/version and avoid publishing TRUNCATE if the subscriber holds rows outside the filtered set that must remain.

### Exercise 23 — Publication Refresh

After ADD TABLE on the publisher, run ALTER SUBSCRIPTION ... REFRESH PUBLICATION on the subscriber. Refresh updates membership and can initiate table sync; it does not create target schemas.

### Exercise 24 — Initial Copy

Operators must ensure the subscriber baseline matches the publisher at the streaming start point with zero missing or duplicate rows and clear snapshot/LSN coordination. Otherwise, data gaps or divergence occur.

### Exercise 25 — Duplicate Key

Causes include pre-seeded/local subscriber rows, application writes on the subscriber, re-running initial copy, or incorrect key mapping. Compare against the authoritative source, stop local writes, choose empty target/controlled reseed/reconciliation, and verify slot/sync state before retrying.

### Exercise 26 — Schema Drift

Examples: missing/renamed columns, differing types/typmods, differing nullability/defaults, differing replica identity/PKs, differing enums/domains, differing collations/extensions, differing constraints/indexes, and differing publication filters/membership.

### Exercise 27 — Schema Fingerprint

Include relation/column names, types/typmods, nullability/defaults/generated expressions, replica identity/PKs, constraints, required indexes, enums/domains/collations, and publication membership/filters/column lists. Exclude OIDs, physical file locations, and environment-varying metadata; apply an allowlist for subscriber-only objects.

### Exercise 28 — Monitoring

pg_stat_subscription shows worker/receive progress; pg_subscription_rel shows table sync states; subscriber logs show exact apply errors such as type/constraint/identity failures. Combine all three to know how far data was received and applied.

### Exercise 29 — Slot Retention

Logical slots retain WAL needed to decode from the restart position. Subscriber lag/disconnects can cause slots to hold large WAL volumes. Do not drop an inactive slot immediately; verify owner/consumer, reconnect prospects, and reinitialization impacts first.

### Exercise 30 — Major Upgrade

Preflight inventory/versions/schemas/extensions; provision new subscriber; create schemas/roles/publication/subscription; initial copy; monitor apply/lag; validate data; freeze DDL/writes; wait for final marker/LSN apply; sync sequences; cut over app; monitor; retain a controlled rollback window.

### Exercise 31 — Final LSN

latest_end_lsn is progress/feedback reported from the publisher, not standalone proof the final transaction applied/committed on the subscriber. Use apply/origin progress, table sync state, and a marker transaction.

### Exercise 32 — Cutover Writes

If the publisher continues accepting writes after the subscriber becomes primary, the subscriber misses those new changes. Stopping writes and draining transactions establishes a final boundary confirming all pre-cutover changes applied.

### Exercise 33 — Rollback

The old publisher lacks writes created on the subscriber after cutover. Routing traffic back loses those writes or causes divergence. Reverse replication/reconciliation or a planned restore/replay is required.

### Exercise 34 — Extensions

Logical replication transfers row data; it does not install shared libraries/binaries. A new major version needs compatible extension packages, SQL extension objects, and type/function/operator definitions before applying data using them.

### Exercise 35 — Large Objects

Large objects do not transfer automatically like ordinary row changes. Separate export/copy/restore, OID/reference mapping checks, and application read verification on the subscriber are needed.

### Exercise 36 — Schema Contract

Document tables/columns, types/business meaning, nullability/defaults, primary keys/replica identities, publication filters/column lists, partitioning, enums/domains/extensions/collations, subscriber-only objects, migration order, compatibility windows, and validation criteria.

### Exercise 37 — Subscriber-Only Index

Not necessarily. Extra indexes can be intentional differences supporting reads. Ensure no unique constraint is added that rejects rows accepted by the publisher, and measure write/apply overhead.

### Exercise 38 — DDL Deployment

1. Add nullable column on subscriber.
2. Add nullable column on publisher.
3. Deploy compatible application.
4. Backfill data and check parity.
5. Ensure all writes supply valid values.
6. Validate zero NULLs remain.
7. Add NOT NULL via an appropriate workflow on subscriber/publisher.
8. Monitor apply and app.
9. Contract/drop old fields only once consumers have transitioned.

### Exercise 39 — Apply Error

Identify the failing relation/column/key from subscriber logs. Inspect source values, target UUID type, malformed strings, nulls, and casts. Normalize publisher data before emitting, or use a controlled migration/canonical column. Then fix target/schema if needed, resume the worker per version procedure, and verify row parity.

### Exercise 40 — Enum Migration

The subscriber lacked the new enum label because DDL does not replicate. The apply worker received a text label absent from the target enum and errored. Add the label on the subscriber first, verify order/semantics, and only then emit the label from publisher/app. Prevent recurrence via migration ordering, schema contracts, preflight enum diffs, and staging tests.

---

## 24. Compatibility Reference Table

| Component | Automatically replicated? | Required action |
|---|---|---|
| INSERT/UPDATE/DELETE rows | Yes if publication enables operation | Ensure compatible schemas/identities |
| TRUNCATE | Yes if publication enables operation | Check table-level impact and row filters |
| CREATE/ALTER/DROP TABLE | No | Run DDL migrations on both sides |
| Column definitions/types | No | Schema contract and migrations |
| Indexes/constraints | No | Create/validate separately |
| Triggers/functions | No | Deploy separately, avoid side effects |
| Sequence state | No | Synchronize at seed/cutover |
| Large objects | Not via standard row replication | Copy/validate separately |
| Roles/grants | No | Provision separately |
| Extensions/binaries | No | Install compatible versions |
| Views/materialized views | No | Deploy/refresh separately |
| Publication membership | Configured on publisher | Refresh subscription when needed |
| Row filter/column list | Publication config | Version-gate and coordinate schemas |
| Replica identity | Must be configured properly | Verify publisher and target row matching |

---

## 25. Summary

Logical replication compatibility goes beyond two servers simply connecting. It requires alignment across versions/protocols, publication membership, relation/column mappings, type conversions, replica identities, and dependent constraints/objects.

Key takeaways:

1. Subscribers generally must run the same major version as or newer than the publisher per compatibility policy; verify exact direction/version pairs.
2. Logical replication transfers row changes; DDL, sequence state, large objects, extensions, and schema objects require separate management.
3. Columns map by name, not position; every migration must keep mapping applyable.
4. Differing data types are safe only after testing conversion, range, precision, and semantics.
5. UPDATE/DELETE require an appropriate replica identity; a stable primary key is usually best.
6. Defaults, generated columns, identity, and sequences carry distinct semantics; sequence state does not sync automatically.
7. Constraints, indexes, and triggers on the subscriber can reject rows or trigger side effects during apply.
8. Partitioning, row filters, column lists, and TRUNCATE must be checked against your PostgreSQL version.
9. Use expand-and-contract so old and new schemas coexist safely during migration windows.
10. REFRESH PUBLICATION updates membership; it does not create target schemas.
11. Initial copy requires a clean baseline and must avoid duplicate/local writes.
12. Schema fingerprints and contracts detect drift before apply fails.
13. Monitor pg_stat_subscription, pg_subscription_rel, logs, replication slots, and WAL retention.
14. Major upgrades require preflight, initial sync, data validation, final markers, sequence handoffs, and cutover.
15. Post-cutover rollbacks must handle new writes; you cannot simply revert to the old publisher.
16. Test restores, cutovers, and schema migrations on exact target versions/extensions before production.

Safe workflow: **confirm version pair → inventory schemas and objects → build contract → deploy subscriber schema → configure publication/subscription → initial copy → monitor apply and drift → validate data → freeze writes/DDL → wait for final apply marker → hand off sequences → cut over → monitor and keep rollback plan**.
