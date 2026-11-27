# Collation Changes, Reindexing, and Risks After an Operating System Upgrade

PostgreSQL uses collations to determine how text is compared and sorted according to a locale. These rules can come from the operating system's locale library such as glibc or from ICU. When upgrading the operating system, glibc or ICU may change character comparison rules. An index built under old rules may no longer be ordered correctly under new rules.

This is a real data correctness risk: queries using indexes may return wrong or incomplete results; unique indexes may uncover new conflicts when rebuilt; and replicas may behave differently if nodes run different locale versions. PostgreSQL records collation versions to warn about mismatches, yet updating metadata does not automatically repair indexes.

This lesson explains collation providers, version tracking, how to detect mismatches, identifying collation-dependent indexes, choosing `REINDEX` options, resolving unique conflicts, and planning OS/ICU/glibc upgrades across primary, standbys, and logical subscribers. Examples target PostgreSQL on Linux; catalog columns, provider support, and administrative commands should be verified against your exact running major version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain collations and their impact on text comparison/sorting.
2. Distinguish `libc`, `ICU`, and other providers where supported by version.
3. Understand why OS/ICU upgrades can alter collation behavior.
4. Read stored collation versions and actual runtime versions.
5. Detect mismatches in database default collations and named collations.
6. Identify indexes using changed collations.
7. Sequence reindexing and refreshing collation metadata safely.
8. Understand impacts on unique indexes, constraints, partitioning, and query results.
9. Compare regular `REINDEX` with `REINDEX CONCURRENTLY`.
10. Coordinate reindexing across primary, physical standbys, and logical subscribers.
11. Build pre-/post-OS-upgrade runbooks.
12. Test locale behavior, index correctness, replication, and rollback readiness.

## 2. What is a collation?

A collation is a set of rules used to compare and sort character strings according to a specific locale or rule set. For instance, rules govern:

- How uppercase and lowercase letters sort.
- Where accented characters are placed.
- How two strings order relative to one another.
- Whether certain characters or strings are considered equal under collation comparison.

No single alphabetical ordering fits every language. Results can differ between English, Vietnamese, German, or Turkish locales, or across versions of locale data.

### Collation is not encoding

Encoding defines how characters are represented as bytes, such as `UTF8`. Collation defines how text values are compared/sorted. A `UTF8` database can still change `ORDER BY` results when the collation provider or version changes.

### Collations and comparisons

Collations affect text operations that rely on locale rules. Exactly which expressions are affected depends on the collation attached to the expression, operator class, and database. Do not assume all byte comparisons depend on collation.

## 3. Where are collations used?

Collations can affect:

- `ORDER BY` on text.
- Text comparisons in predicates and joins.
- B-tree indexes on `text`/`varchar`/`char` and expression indexes.
- Unique indexes/unique constraints whose keys use collation.
- `DISTINCT`, `GROUP BY`, and various other text operations.
- Partition bounds or application logic relying on text ordering.
- Results of locale-dependent queries.

Some operations may use binary comparison or an explicitly specified collation. Determine the actual collation of each expression rather than assuming all text columns follow one rule.

## 4. Database collation and expression collation

When creating a database, you can select the locale/provider for the default collation. Columns and expressions typically inherit the default collation per PostgreSQL rules, though a different collation can be specified.

Example:

```sql
CREATE TABLE customer (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name text COLLATE "en_US"
);
```

An expression can also choose a collation:

```sql
SELECT display_name
FROM customer
ORDER BY display_name COLLATE "C";
```

The `"C"` collation generally uses byte/code-point order per encoding rather than locale-aware collation rules. Exact semantics depend on encoding/platform.

## 5. Collation providers: `libc` and ICU

PostgreSQL can obtain collation rules from different providers:

| Provider | Rule source | Key considerations |
|---|---|---|
| `libc` | Operating system locale library, typically glibc on Linux | Can change during OS/glibc upgrades |
| `ICU` | International Components for Unicode | Can change during ICU or locale data upgrades |
| `builtin`/other | Provider supported in certain newer releases | Check feature support per PostgreSQL version |

Available providers depend on how PostgreSQL was built and its version. Not every cluster supports ICU.

### `libc`

`libc` collations rely on OS locales. Distribution upgrades can update glibc or locale data, changing versions and sort ordering. Two servers on different OS releases may behave differently even with identical database catalogs.

### ICU

ICU provides locale-aware sorting and tailoring. ICU versions or locale data can change across releases. Named ICU collations normally store provider, locale, and version metadata in PostgreSQL catalogs.

### Choosing a provider

ICU can deliver more consistent cross-OS behavior if deployment and versions are controlled, yet ICU also undergoes version changes. No provider eliminates the need to check collation versions and reindex when rules change.

## 6. Deterministic and nondeterministic collations

PostgreSQL supports deterministic and nondeterministic collations in versions with ICU support.

- A deterministic collation distinguishes two strings that differ at the byte level even if the provider assigns them equal sort weights.
- A nondeterministic collation can treat certain byte-distinct strings as equal under ICU rules—for example, certain case or accent differences depending on locale/rules.

Illustrative ICU collation creation in a supported version:

```sql
CREATE COLLATION app_case_insensitive (
    provider = icu,
    locale = 'und-u-ks-level2',
    deterministic = false
);
```

This is an illustrative example; supported ICU locale keywords and features depend on PostgreSQL/ICU versions. Nondeterministic collations have restrictions on certain index/operator operations; read your version's documentation before using them.

## 7. Why do OS upgrades affect collations?

PostgreSQL does not bundle the entire `libc` locale database inside the data directory. For the `libc` provider, the server uses the locale implementation from the runtime host. When OS packages update, locale rules can change.

Changes can stem from:

- glibc updates.
- ICU library updates.
- Locale definition/data updates.
- OS distribution/release changes.
- Container base image changes.
- Provider or locale configuration changes during cluster/database creation.

Even a new container image can ship a different ICU/glibc version while keeping the PostgreSQL major version unchanged.

## 8. Risks when indexes were built under an old collation

A B-tree index stores entries ordered by the comparator/collation active at build time. If the comparator changes, the index's physical order may no longer match the order used by the current server during lookups.

Consequences can include:

- Index scans missing rows or returning wrong results.
- `ORDER BY` via an index producing an order inconsistent with the current comparator.
- Range predicates on text behaving incorrectly.
- Unique indexes discovering new duplicates upon rebuild.
- Application results shifting when a query switches from an index scan to a sequential scan or vice versa.

This is a correctness bug, not merely a performance issue. When PostgreSQL warns of a collation version mismatch, resolve it before trusting collation-dependent indexes.

## 9. Unique indexes and duplicate conflicts

Suppose before an upgrade, two strings were treated as distinct by the old collation; after the upgrade, the new collation treats them as equal in a unique index. When running `REINDEX` on that unique index, PostgreSQL can detect duplicates and refuse to complete.

### Why prepare ahead?

- Existing data may contain two values previously accepted that now collide.
- Unique constraints are enforced by unique indexes, so rebuilding can fail.
- PostgreSQL cannot automatically decide which record to keep.
- The application may need to merge/rename data before the index can be rebuilt.

Before cutover, test for pairs that may become equal under the new collation using a clone running the target provider/version. Never rely on old-collation equality to predict new outcomes.

## 10. Version tracking in PostgreSQL

PostgreSQL records the known collation version at database/collation creation time. At runtime, it can compare the recorded version against the actual version reported by the current provider.

Two key metadata areas:

- Database default collation version in `pg_database`.
- Individual named collation versions in `pg_collation`.

Exact fields/functions vary by major version. On supported versions, use the actual-version functions to detect mismatches.

## 11. Checking database default collation version

Query on supported PostgreSQL versions:

```sql
SELECT
    datname,
    datcollate,
    datctype,
    datlocprovider,
    datcollversion,
    pg_catalog.pg_database_collation_actual_version(oid)
        AS actual_collation_version
FROM pg_catalog.pg_database
WHERE datallowconn
  AND datcollversion IS DISTINCT FROM
      pg_catalog.pg_database_collation_actual_version(oid)
ORDER BY datname;
```

Verify `datlocprovider`/`datcollversion` columns and the actual-version function for your PostgreSQL major version. If the query reports missing columns/functions, consult that version's docs/catalog rather than assuming no mismatch exists.

### Meaning

- `datcollversion`: version recorded in the database catalog.
- `actual version`: version currently reported by the provider for that locale.
- `IS DISTINCT FROM`: compares safely even when one side is `NULL`.

This query detects database default collation mismatches. It does not replace checking individual named collations.

## 12. Checking named collations

In each database:

```sql
SELECT
    oid,
    collname,
    collprovider,
    collcollate,
    collctype,
    colliculocale,
    collversion,
    pg_catalog.pg_collation_actual_version(oid)
        AS actual_collation_version
FROM pg_catalog.pg_collation
WHERE collversion IS DISTINCT FROM
      pg_catalog.pg_collation_actual_version(oid)
ORDER BY collname;
```

Some columns such as `colliculocale` exist only in PostgreSQL versions supporting ICU metadata. Adjust the `SELECT` list to match your major version's catalog schema.

### Why run in every database?

Collations are database-local objects. One database can define its own named collations even if its default locale matches another database. Cluster-wide inventory requires connecting to every accessible database.

## 13. Viewing all collations and providers

To inventory before upgrading:

```sql
SELECT
    collname,
    collprovider,
    collisdeterministic,
    collcollate,
    collctype,
    collversion
FROM pg_catalog.pg_collation
ORDER BY collprovider, collname;
```

Columns vary by version/provider. The inventory aims to identify:

- Which collation is the default.
- Which collations were created by applications.
- Which providers are used.
- Which locales/rules are configured.
- Which versions are recorded.
- Which schemas/tables/indexes depend on them.

## 14. Detecting a mismatch does not mean you found all indexes

A database-level mismatch shows the locale version differs from the recorded version. A named collation mismatch shows a collation object needs attention. However, to plan reindexing, you must identify the specific indexes depending on those collations.

Indexes can involve text key columns, expression keys, or explicitly specified collations. Query index catalogs rather than merely searching for text column names.

## 15. Finding indexes using mismatched named collations

On versions providing `pg_collation_actual_version`:

```sql
WITH mismatched_collations AS (
    SELECT oid, collname
    FROM pg_catalog.pg_collation
    WHERE collversion IS DISTINCT FROM
          pg_catalog.pg_collation_actual_version(oid)
)
SELECT DISTINCT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    mc.collname AS collation_name
FROM pg_catalog.pg_index AS ix
JOIN pg_catalog.pg_class AS idx
  ON idx.oid = ix.indexrelid
JOIN pg_catalog.pg_class AS tbl
  ON tbl.oid = ix.indrelid
JOIN pg_catalog.pg_namespace AS ns
  ON ns.oid = tbl.relnamespace
CROSS JOIN LATERAL unnest(ix.indcollation) AS ic(collation_oid)
JOIN mismatched_collations AS mc
  ON mc.oid = ic.collation_oid
ORDER BY schema_name, table_name, index_name;
```

This query finds collations declared in index key metadata. Verify `unnest` compatibility with the catalog type on your specific major version. For database default collation mismatches, also check `datcollversion` and indexes using the default collation; do not rely solely on the named-collation query.

## 16. Inspecting index definitions

To view index definitions in schemas:

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, indexname;
```

Index definitions reveal expressions, `COLLATE` clauses, operator classes, and unique constraints. Combine with `pg_index.indcollation` to determine exact collation OIDs used by each index.

Do not search only for text keywords in `indexdef`; collations can be inherited from columns/expressions.

## 17. Database default mismatch vs. named collation mismatch

Two mismatch types must be managed separately:

| Type | Metadata | Refresh command |
|---|---|---|
| Database default collation | `pg_database.datcollversion` | `ALTER DATABASE ... REFRESH COLLATION VERSION` |
| Named collation | `pg_collation.collversion` | `ALTER COLLATION ... REFRESH VERSION` |

Refreshing only updates version metadata. It does not rebuild indexes or fix data ordered under old rules.

### Mandatory order

1. Detect mismatches.
2. Identify dependent indexes/objects.
3. Rebuild needed indexes under the new provider version.
4. Verify unique conflicts and correctness.
5. Only after reindexing completes, refresh the recorded collation version.

If you refresh metadata before reindexing, PostgreSQL may stop warning about mismatches even though indexes remain built under old sort orders.

## 18. `ALTER COLLATION REFRESH VERSION`

For a named collation:

```sql
ALTER COLLATION app_schema.app_locale REFRESH VERSION;
```

Schema/collation names must uniquely identify the object. The command updates the recorded version to match the current actual provider version.

### What this command does not do

- Does not run `REINDEX`.
- Does not change collation locales/rules.
- Does not check or resolve duplicate values.
- Does not fix other databases.

Run only after dependent indexes have been rebuilt and verified.

## 19. `ALTER DATABASE REFRESH COLLATION VERSION`

For a database default collation:

```sql
ALTER DATABASE appdb REFRESH COLLATION VERSION;
```

This command updates the version metadata of the database's default collation. It does not rebuild indexes and does not refresh separate named collations.

### Scope

Run for each mismatched database. Refreshing one database does not automatically update other databases or template databases.

## 20. What is `REINDEX`?

`REINDEX` rebuilds an index from current table data. When collation ordering changes, rebuilding recreates index entries under the new comparator.

Common forms:

```sql
REINDEX INDEX app_schema.customer_name_idx;
REINDEX TABLE app_schema.customer;
REINDEX SCHEMA app_schema;
REINDEX DATABASE appdb;
```

`REINDEX DATABASE` affects only the current database; connect to the target database and execute in the right context. `REINDEX DATABASE` cannot run inside a transaction block. Syntax/permissions/behavior may vary by PostgreSQL version.

## 21. `REINDEX INDEX` vs. `REINDEX TABLE`

`REINDEX INDEX` targets a specific index. This fits well when affected indexes are accurately identified.

`REINDEX TABLE` rebuilds all indexes on a table. It is broader than necessary if only one index uses the changed collation, though it can simplify runbooks for a given table.

### Choosing scope

- Specific index: saves time and WAL when the dependency inventory is reliable.
- Table: helpful when multiple indexes on one table are affected.
- Schema/database: fits maintenance windows or when rebuilding all indexes within a defined scope.

Do not pick `REINDEX DATABASE` merely because it is shorter to type if the cluster handles heavy workloads and downtime must be controlled.

## 22. `REINDEX DATABASE` and every database in the cluster

A PostgreSQL cluster can contain multiple databases. `REINDEX DATABASE appdb` rebuilds indexes only inside `appdb`. Repeat for every database with mismatches/relevant indexes.

The inventory should cover:

- Application databases.
- Databases holding extensions or shared application objects.
- `template1` if it holds collations/indexes used as a template for new databases.
- Maintenance/monitoring databases if they contain user-defined collations.

`template0` is normally kept pristine and disallows normal connections. Do not modify `template0` as a routine step; follow PostgreSQL documentation for your version.

## 23. `REINDEX SYSTEM`

`REINDEX SYSTEM` rebuilds indexes on system catalogs in the current database. Most catalog indexes use internal semantics independent of application locales, so do not run `REINDEX SYSTEM` by default solely because OS collation versions changed.

Use only with a specific reason or when required by PostgreSQL/vendor runbooks. `REINDEX SYSTEM` has broad impact and may require elevated privileges and maintenance planning.

## 24. `REINDEX CONCURRENTLY`

On supported PostgreSQL versions, `REINDEX CONCURRENTLY` reduces write-blocking duration on tables/indexes by building a new index while permitting concurrent operations across multiple phases.

Example:

```sql
REINDEX INDEX CONCURRENTLY app_schema.customer_name_idx;
```

Advantages:

- Minimizes blocking writes during most of the operation.
- Helpful for production tables requiring high availability.

Costs/constraints:

- Requires extra disk space during the build.
- Generates extra I/O, CPU, and WAL.
- Involves multiple phases and can take longer.
- Can fail and leave an invalid index requiring cleanup.
- Cannot run inside a transaction block.
- Has restrictions on certain index types/constraints and catalog indexes.

Read the documentation for your exact PostgreSQL version before using. Never assume `CONCURRENTLY` means lock-free or zero operational impact.

## 25. Choosing regular `REINDEX` vs. `CONCURRENTLY`

| Criterion | Regular `REINDEX` | `REINDEX CONCURRENTLY` |
|---|---|---|
| Write blocking | Can block writes on the table during rebuild | Reduces write blocking; still acquires locks in phases |
| Duration | Usually shorter | Usually longer due to multiple phases |
| Temp disk space | Needs space for rebuild | Typically requires larger extra space |
| WAL/I/O | Can be heavy | Also heavy, potentially over a longer span |
| Transaction block | Disallowed for some forms | Cannot run inside a transaction block |
| Operational complexity | Simpler | Must monitor phases/invalid indexes |

If a clear maintenance window exists and locks are acceptable, regular `REINDEX` can be simpler. If writes must continue, `CONCURRENTLY` fits when index types/versions support it and capacity is sufficient.

## 26. Disk space and WAL during reindexing

Reindexing can require building the new index copy before removing the old one. Required space depends on index size, concurrency, temporary build files, and storage layout.

Account for:

- Current index size.
- New index copy during build.
- WAL generation.
- WAL archive backlog.
- Replication slot retention.
- Standby catch-up capacity.
- Temp files and free space on each mount.

Never start bulk reindexing when `pg_wal` or archive destinations are nearly full. Reindexing on the primary can generate substantial WAL and cause standby lag.

## 27. Reindexing and replication

With physical streaming replication, index changes on the primary are written to WAL and replayed on standbys. A standby in recovery mode does not run `REINDEX` independently for the same physical cluster.

Before/after reindexing:

- Check standby streaming state.
- Monitor replay lag.
- Check WAL archiving and replication slots.
- Ensure standbys run the exact same OS/ICU/libc collation version as the primary.
- Keep any standby with a locale mismatch out of index-dependent read traffic.

If primary and standby run different provider versions, the same index structure can be interpreted by different comparators on each node. Keeping runtime locale versions uniform is critical.

## 28. Logical replication

Logical replication does not automatically replicate all DDL/index maintenance operations. Subscribers can maintain independently created indexes and must be reindexed locally if their collation versions change.

Plan for logical replication:

1. Inventory publisher and subscribers.
2. Identify OS/ICU/libc versions on each node.
3. Reindex collation-dependent indexes in each subscriber database.
4. Check constraints/unique conflicts separately.
5. Synchronize DDL/schema changes per logical replication procedures.
6. Monitor apply workers and lag.

Never assume reindexing on the publisher automatically repairs indexes on subscribers.

## 29. Partitioned tables and collations

If partition keys or expressions use text collations, changes in comparison order can affect partition bound comparisons and routing of new rows.

After upgrading:

- Inspect partition key definitions.
- Identify collations bound to partition key expressions.
- Check partition bounds under the new comparator.
- Confirm existing rows still belong in the right partitions per policy.
- Test insert/update routing on a clone.
- Check unique constraints/indexes on partitioned tables per version limits.

Reindexing does not automatically move rows across partitions if partition bound semantics changed. Evaluate data and routing logic separately.

## 30. Constraints and existing data

Unique constraints typically rely on unique indexes. When a new collation treats two values as equal, reindexing can fail due to duplicate keys.

Check constraints can contain text comparison expressions. Changing collations does not automatically re-validate all check constraints across existing data.

### Before reindexing

- Locate collation-dependent unique indexes.
- Locate constraints using text comparisons.
- Test duplicate detection under the new collation on a clone.
- Define business rules to merge/rename data if conflicts arise.
- Prepare a downtime/transaction plan for data cleanup.

Never automatically delete or edit one of the duplicate records. That decision belongs to the business data owner.

## 31. Impact on query plans and results

After reindexing, the planner may pick a different plan because index statistics/sizes changed or a rebuilt index looks more attractive. However, reindexing does not replace `ANALYZE` when statistics need refreshing.

Check:

- Text `ORDER BY` before/after.
- Range predicates on text.
- Equality/uniqueness behavior.
- Index scans and bitmap scans.
- Query plans for critical workloads.
- Latency/throughput after rebuilding.

Run `ANALYZE` on relevant tables if statistics need updating; do not confuse `ANALYZE` with `REINDEX`.

## 32. Collation mismatch warnings

PostgreSQL may log a database/collation version mismatch warning at startup or when using a collation. The warning states that the recorded version differs from the actual provider version.

A warning does not guarantee every index is already returning wrong results, yet it must be treated as a correctness risk for dependent objects. Never silence the warning by refreshing metadata before rebuilding.

### Procedure for handling warnings

1. Record database/collation/provider.
2. Identify the changed OS/ICU/glibc version.
3. Identify dependent indexes/objects.
4. Assess duplicate conflicts and capacity.
5. Reindex.
6. Verify.
7. Refresh version metadata.
8. Restart/recheck logs if required by runbook.

## 33. Checking locale runtime on Linux

Helpful inventory commands:

```sh
ldd --version
locale
locale -a
```

If using ICU, tools such as `icuinfo` or the package manager can report the ICU library version, depending on distribution.

### Container images

Inspect inside the actual container image/pod running PostgreSQL, not just on the host. Containers can bundle different ICU/glibc versions than the host; dynamic linking and mounted libraries can also affect runtime behavior.

Record:

- OS release.
- glibc version.
- ICU version/package.
- PostgreSQL build/version.
- Locale definitions.
- Container image digest.

## 34. Checking PostgreSQL builds and collation providers

```sql
SELECT version();

SELECT
    collprovider,
    count(*) AS collation_count
FROM pg_catalog.pg_collation
GROUP BY collprovider
ORDER BY collprovider;
```

Check PostgreSQL version, build platform, and provider inventory. Do not infer runtime locale data solely from a single package version.

## 35. Testing collation behavior before/after upgrading

Create a test dataset representing real languages/data:

```sql
CREATE TEMP TABLE collation_probe (
    value text COLLATE "default"
);

INSERT INTO collation_probe(value)
VALUES
    ('a'),
    ('A'),
    ('á'),
    ('ä'),
    ('z'),
    ('đ'),
    ('Đ'),
    ('I'),
    ('i'),
    ('ı');

SELECT value
FROM collation_probe
ORDER BY value;
```

Exact output depends on database locale/provider. Save outputs on the old environment, run the same test on an upgraded clone, and compare. Add domain-specific data—especially personal names, addresses, SKUs/text keys, and supported application languages.

## 36. Testing uniqueness under the new collation

On a clone running the new provider, test creating a unique index on a representative dataset:

```sql
CREATE TEMP TABLE unique_probe (
    value text COLLATE "default"
);

INSERT INTO unique_probe(value)
VALUES ('A'), ('a'), ('á'), ('Á');

CREATE UNIQUE INDEX unique_probe_value_idx
ON unique_probe(value);
```

If index creation fails, the data contains values treated as equal under the new comparator. This is an illustrative test; use your application's actual target collations and unique index definitions.

## 37. Backup and rollback planning

Before an OS/ICU upgrade:

- Take a base backup/physical snapshot per policy.
- Confirm continuous WAL archiving.
- Ensure a recent restore test passed.
- Record PostgreSQL config and OS package versions.
- Save collation inventory/version query outputs.
- Save index inventory and sizes.
- Define the rollback boundary.

### Rollback is not merely downgrading packages

If the data directory has been used under the new collation runtime, reverting to old OS/libraries can create a reverse mismatch. If you already reindexed under the new collation, the old runtime might misinterpret those rebuilt indexes under old rules.

A safe rollback may require restoring a snapshot/backup or reverting both OS/libraries and index state per a tested plan. Never assume package downgrade alone suffices.

## 38. Separating OS upgrades from PostgreSQL major upgrades

Do not bundle an OS upgrade, a PostgreSQL major upgrade, and collation changes into a single step where root causes cannot be isolated.

Recommendations:

- Build an OS/PostgreSQL/extensions compatibility matrix.
- Test the OS upgrade on the same PostgreSQL major version first if possible.
- Plan the major upgrade separately afterward.
- Record collation versions before/after each step.
- Reindex per documentation for each transition.

`pg_upgrade` can detect collation version mismatches and emit warnings; follow its output and version-specific docs. Never ignore warnings just because the server still starts.

## 39. Upgrading primary and standbys

With physical replication, nodes need identical collation semantics so queries on standbys use indexes safely.

A reference sequence:

1. Confirm target OS/ICU/glibc versions.
2. Verify compatibility on a clone.
3. Drain a standby out of read traffic.
4. Upgrade the standby via orchestration and verify provider versions.
5. Keep the standby out of collated read traffic while versions mismatch index state.
6. Upgrade the primary per a tested failover/maintenance plan.
7. Reindex on the writable primary per plan.
8. Monitor WAL replay so standbys receive index rebuilds.
9. Synchronize runtime locale versions across all nodes.
10. Refresh metadata and confirm mismatches clear.
11. Return nodes to read traffic only after validation completes.

Exact order depends on HA manager, synchronous replication, downtime budget, and OS/storage upgrade mechanics. Never leave primary and standbys on differing locale versions while serving queries relying on collated indexes.

## 40. Rolling upgrades and read traffic

If OS upgrades are rolled out sequentially:

- Upgraded nodes may use the new comparator.
- Un-upgraded nodes still use the old comparator.
- Physical standbys replay index pages written by the primary, yet query comparators on the standby come from its local runtime.
- A read query on a standby can evaluate an index using mismatched semantics.

Therefore, during mixed-version phases, exclude mismatched nodes from read routing for affected workloads. Gate maintenance/health readiness on collation alignment, not merely TCP/replication health.

## 41. Reindexing on the primary: overall workflow

1. Identify all databases with default/named collation mismatches.
2. List affected indexes and unique constraints.
3. Test for duplicate conflicts on a clone using the new locale.
4. Assess disk, WAL, archive, slot, and standby capacity.
5. Choose targeted `REINDEX` vs. database-wide `REINDEX`.
6. Choose regular vs. `CONCURRENTLY` based on availability/version constraints.
7. Reindex indexes/tables in each database.
8. Verify indexes are valid and queries return expected results.
9. Update statistics as needed.
10. Refresh named collations.
11. Refresh database default collations.
12. Perform a final check for warnings/version mismatches.

Refreshing metadata must come last after dependent indexes are processed.

## 42. Refreshing versions for multiple named collations

After reindexing dependent indexes, run `ALTER COLLATION ... REFRESH VERSION` for each mismatched collation.

You can generate command lists from catalogs, yet always review names/schemas and order before running. Never execute generated SQL blindly in production.

Example generating command text:

```sql
SELECT format(
    'ALTER COLLATION %I.%I REFRESH VERSION;',
    n.nspname,
    c.collname
)
FROM pg_catalog.pg_collation AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.collnamespace
WHERE c.collversion IS DISTINCT FROM
      pg_catalog.pg_collation_actual_version(c.oid)
ORDER BY n.nspname, c.collname;
```

This query generates command text for review only. Do not run commands automatically if reindexing is incomplete.

## 43. Refreshing database default collation

After handling indexes depending on the default collation:

```sql
ALTER DATABASE appdb REFRESH COLLATION VERSION;
```

Execute from a session connected to another database or per PostgreSQL version restrictions. This command does not rebuild indexes and does not refresh named collations.

## 44. Post-refresh verification

Re-run both the database mismatch query and the named collation mismatch query. Expected outcome: zero unresolved mismatches in scope.

Also check:

- PostgreSQL logs show no remaining collation version mismatch warnings for handled objects.
- Relevant indexes are valid/ready.
- Unique constraints remain valid.
- Query results/ordering match expected behavior.
- Physical standbys finished replaying WAL.
- Logical subscribers were reindexed separately.

Never rely on "no warnings left" as sole proof that data semantics are intact; validate against actual workloads.

## 45. `REINDEX` failing due to duplicate keys

If rebuilding a unique index fails:

1. Record the index/constraint and duplicate key error.
2. Identify the actual new collation in use.
3. Find rows considered equal under the new comparator.
4. Consult business ownership and semantics.
5. Decide with the data owner how to merge/rename/normalize records.
6. Check foreign keys/references and application dependencies.
7. Perform cleanup with backups and auditing.
8. Rebuild the unique index.
9. Verify the constraint and application behavior.
10. Only then refresh collation metadata.

Never drop a unique constraint just to let reindexing pass and forget to restore integrity. If a temporary constraint-free window is needed, put alternative guards/maintenance controls in place.

## 46. `REINDEX CONCURRENTLY` failures

Concurrent reindexing can fail due to duplicate keys, cancellation, deadlocks, disk exhaustion, or runtime errors. It can leave an invalid index requiring investigation.

Check:

```sql
SELECT
    ns.nspname,
    idx.relname AS index_name,
    ix.indisvalid,
    ix.indisready,
    ix.indislive
FROM pg_catalog.pg_index AS ix
JOIN pg_catalog.pg_class AS idx
  ON idx.oid = ix.indexrelid
JOIN pg_catalog.pg_namespace AS ns
  ON ns.oid = idx.relnamespace
WHERE NOT ix.indisvalid
   OR NOT ix.indisready
ORDER BY ns.nspname, idx.relname;
```

Catalog flags have specific meanings and can vary by version. Identify indexes marked invalid by a failed concurrent build, inspect logs, and drop/rebuild per documented procedure. Never refresh collation metadata while required indexes remain invalid.

## 47. Reindex progress monitoring

Recent PostgreSQL versions provide progress views for several maintenance commands, including `REINDEX`. Check the catalog view for your version—for example, `pg_stat_progress_create_index` for index build progress.

```sql
SELECT *
FROM pg_catalog.pg_stat_progress_create_index;
```

Monitor:

- Index/table currently building.
- Current phase.
- Command age.
- Wait events/locks.
- Free disk space and WAL generation.
- Standby replay lag.

Never kill a backend merely because progress pauses briefly in a phase; inspect wait events, locks, and storage I/O.

## 48. Reindexing and locks

Regular `REINDEX` can block writes on tables/indexes depending on command/version. `REINDEX CONCURRENTLY` reduces blocking yet still acquires locks across phases and can wait on long transactions.

Before running:

- Inspect long-running transactions.
- Inspect idle-in-transaction sessions.
- Check DDL/deploy windows.
- Set `lock_timeout`/`statement_timeout` per runbook.
- Run in small batches.
- Monitor lock waits and application latency.

Avoid timeouts so short that concurrent builds constantly restart, as well as unbounded waits.

## 49. Reindexing and bloat

Reindexing can remove index bloat by rebuilding indexes from heap data. However, the primary goal in collation upgrades is ordering correctness. Do not confuse every bloat issue with a collation mismatch.

### Comparison

- `REINDEX` for collation change: mandatory when index semantics are affected.
- `REINDEX` for bloat: decided based on index size, page density, and workload.
- `VACUUM`: cleans dead tuples/reclaims reusable space; does not replace `REINDEX` for updating collation ordering.
- `ANALYZE`: updates planner statistics; does not rebuild indexes.

## 50. Collation changes and application behavior

Applications may rely on stable text ordering in:

- Pagination based on text `ORDER BY`.
- Keyset pagination.
- Cursor tokens.
- Deduplication by case/accent behavior.
- Search/sort UI.
- Deterministic export file ordering.
- Text-based partition routing.

After an OS/ICU upgrade, sort order can shift even when underlying data is unchanged. Test API pagination and cursor continuation; a cursor issued before the upgrade may no longer match the post-upgrade order.

## 51. `"C"` and `"POSIX"` collations

`"C"` and `"POSIX"` collations generally use binary/code-point ordering and do not depend on locale language rules like `libc` locale-aware collations. They suit technical keys needing stable ordering, though they are not automatically right for every text field.

### Notes when switching collations

Changing a column/expression to `"C"` can alter application equality/ordering semantics. Matching indexes must be created and query behavior tested. Never alter collation metadata merely to dodge reindexing without evaluating business semantics.

## 52. ICU custom rules and locale identifiers

ICU collations can use locale identifiers and custom tailoring/rules in supported versions. Upgrading ICU can change sort results even when the locale identifier stays identical.

The inventory should store:

- Collation name.
- Provider.
- ICU locale identifier.
- Deterministic setting.
- Custom rules if any.
- Recorded version.
- Actual version.

Avoid changing ICU locales/rules in the same change window as an OS upgrade whenever possible; separating them simplifies root-cause analysis and rollback.

## 53. Multiple databases and `template1`

Collations and indexes are database-local objects. A cluster can have mismatches across multiple databases with different custom collations.

Inventory workflow:

1. List databases and default locales/providers/versions.
2. Connect to each database.
3. List named collation mismatches.
4. Build the index dependency list.
5. Reindex and refresh within each database.
6. Check `template1` if used to create new databases.

If `template1` keeps an old recorded version, newly created databases cloned from it may need similar handling. Avoid touching `template0` routinely.

## 54. Monitoring during and after an OS upgrade

Monitor:

- PostgreSQL startup warnings/errors.
- Collation mismatch inventory.
- `REINDEX` progress/failures.
- Invalid index count.
- Unique constraint errors.
- Free disk bytes/inodes.
- WAL generation/archive backlog.
- Physical standby replay lag.
- Logical replication lag/apply errors.
- Query latency, error rates, and pagination correctness.

Configure alerts for near-full filesystems and replication lag before starting reindexing. Reindexing can sharply raise WAL and disk pressure.

## 55. Production change plan

A change request should document:

- Cluster/database scope.
- OS, glibc, ICU, and PostgreSQL versions before/after.
- Involved collation providers/locales.
- Affected indexes and constraints.
- Disk/WAL estimates.
- Chosen `REINDEX` mode and lock impact.
- Primary/standby/logical subscriber sequencing.
- Application traffic/read-routing plan.
- Backup/restore checkpoint.
- Validation criteria.
- Rollback decision point and owner.

Never start based only on "OS upgrade completed"; require a version inventory and collation comparison.

## 56. Runbook: before an OS upgrade

1. Record PostgreSQL major/minor version and package source.
2. Record OS release, glibc, ICU, and locale data versions.
3. Inventory databases, providers, and collations.
4. Save outputs of database/named collation version queries.
5. Build an index dependency inventory.
6. Check unique indexes and constraints.
7. Clone production to staging.
8. Upgrade OS/ICU on the clone.
9. Reproduce collation mismatches.
10. Test reindexing, duplicates, query ordering, and application behavior.
11. Estimate disk/WAL/replication impact.
12. Finalize maintenance/failover/rollback plans.

## 57. Runbook: after an OS upgrade

1. Record actual glibc/ICU/locale versions on each node.
2. Confirm PostgreSQL starts and read logs.
3. Run the database default collation mismatch query.
4. Run the named collation mismatch query in every database.
5. Build the index list by collation OIDs.
6. Remove nodes with runtime mismatches from affected read traffic.
7. Assess duplicate conflicts and index build capacity.
8. Reindex dependent indexes on the writable primary.
9. Monitor WAL/archive/standby replay.
10. Reindex logical subscribers separately.
11. Verify indexes and query behavior.
12. Refresh named collation versions.
13. Refresh database default versions.
14. Re-run mismatch queries and inspect logs.
15. Restore traffic once all nodes align and validation passes.

## 58. Runbook: duplicate conflicts when reindexing a unique index

1. Pause the metadata refresh step.
2. Save error details and the index definition.
3. Identify the actual new collation/provider version.
4. Reproduce on a clone or query with an explicit collation.
5. Find colliding rows under the new comparator.
6. Consult the data owner on canonical values.
7. Check foreign keys/references and application dependencies.
8. Back up/record affected rows.
9. Merge/rename/normalize data per approved change.
10. Rebuild the unique index/constraint.
11. Verify uniqueness and application behavior.
12. Proceed with refreshing version metadata.

## 59. Runbook: standby has a different collation version than primary

1. Check provider/runtime versions on primary and standby.
2. Check recorded/actual versions on the standby.
3. Stop routing collated reads to the mismatched node.
4. Confirm the OS/ICU upgrade plan across the entire topology.
5. Reindex on the primary once the target provider version is standardized.
6. Monitor WAL replay completion on the standby.
7. Verify standby runtime versions match the primary.
8. Run query probes on the standby.
9. Return the node to the read pool only after validation.

Never run `REINDEX` independently on a physical standby in recovery.

## 60. Runbook: `REINDEX CONCURRENTLY` fails

1. Record command, index, PostgreSQL version, and error.
2. Inspect logs and lock waits.
3. Check disk/inodes/WAL capacity.
4. Inspect `pg_index` flags for the index.
5. Determine whether the concurrent build left an invalid index.
6. Check for duplicate conflicts if it is a unique index.
7. Drop/rebuild invalid indexes per documented procedure.
8. Adjust workload/window/timeouts if needed.
9. Re-run and monitor progress.
10. Refresh collation metadata only once all dependent indexes are valid.

## 61. Collation upgrade checklist

### Inventory

- OS/glibc/ICU/PostgreSQL versions recorded.
- Database default locales/providers/versions inventoried.
- Named collations and custom ICU rules inventoried.
- Dependent indexes/constraints listed.
- Primary, physical standbys, and logical subscribers accounted for.

### Capacity and availability

- Backup/restore checkpoint ready.
- Disk space/inodes sufficient for rebuilds.
- WAL/archive/replication slots have headroom.
- Standby replay capacity verified.
- `REINDEX` mode and lock impact approved.
- Read routing can exclude misaligned nodes.

### Execution

- Reindex before refreshing metadata.
- Duplicate conflicts resolved with approval.
- Physical standbys received WAL replay.
- Logical subscribers reindexed separately.
- Database and named collation versions refreshed separately.

### Validation

- Zero unresolved mismatches remain.
- Indexes are valid/ready.
- Unique constraints verified.
- `ORDER BY`/range/pagination probes pass.
- Replication and application SLOs stable.
- Logs clean of unexplained warnings.

## 62. Practice exercises

### Exercise 1 — Collation

Explain what a collation is and how it differs from `UTF8` encoding.

### Exercise 2 — Providers

Compare `libc` and ICU providers. Which OS upgrade changes can alter collation versions?

### Exercise 3 — Collation usage

List query/index/constraint operations that can depend on collation.

### Exercise 4 — Default vs. named collations

Distinguish database default collation from a named collation attached to a column/expression.

### Exercise 5 — Deterministic

Compare deterministic and nondeterministic ICU collations. What limitations must be checked?

### Exercise 6 — Version mismatch

Explain recorded collation version vs. actual provider version. Why must mismatches be addressed?

### Exercise 7 — Database inventory

Write a query listing database default collation versions and actual versions on a supported PostgreSQL version.

### Exercise 8 — Named collation inventory

Write a query finding `pg_collation` rows where `collversion` differs from actual version.

### Exercise 9 — Index dependencies

Explain how `pg_index.indcollation` helps locate indexes using specific collations.

### Exercise 10 — Unique conflicts

Two strings previously unique become equal under a new collation. What can happen when running `REINDEX` on a unique index?

### Exercise 11 — Refreshing versions

Distinguish `ALTER COLLATION REFRESH VERSION` from `ALTER DATABASE REFRESH COLLATION VERSION`.

### Exercise 12 — Operation order

Why must `REINDEX` run before refreshing recorded collation versions?

### Exercise 13 — `REINDEX INDEX`

Write the command to rebuild a specific index and state when targeted reindexing should be chosen.

### Exercise 14 — `REINDEX DATABASE`

A cluster has five databases. Why does a single `REINDEX DATABASE` command process only one database?

### Exercise 15 — `REINDEX SYSTEM`

Explain the scope of `REINDEX SYSTEM` and why it should not be run by default for every collation mismatch.

### Exercise 16 — `CONCURRENTLY`

Compare `REINDEX INDEX` and `REINDEX INDEX CONCURRENTLY` across locks, disk, WAL, and operational complexity.

### Exercise 17 — Disk budget

A database has 400 GB of indexes needing rebuilds. List the disk/WAL/archive headroom items to calculate before starting.

### Exercise 18 — Physical replication

Why does a physical standby not run `REINDEX` independently? How do index rebuilds reach the standby?

### Exercise 19 — Mixed OS versions

Primary runs a new ICU version, standby runs an old version. Why should collated reads stop routing to the standby?

### Exercise 20 — Logical replication

Why does reindexing on the publisher not automatically rebuild indexes on a logical subscriber?

### Exercise 21 — Partitioning

How can a collation change affect partition bounds/routing for a text partition key?

### Exercise 22 — Check constraints

A `CHECK` constraint uses text comparison. Why does reindexing not automatically re-validate all existing rows?

### Exercise 23 — Query correctness

Design tests for `ORDER BY`, range predicates, and keyset pagination before/after an ICU upgrade.

### Exercise 24 — Locale probes

Create a dataset containing uppercase/lowercase letters, accents, and Vietnamese characters to compare sort behavior.

### Exercise 25 — Unique probes

Design a unique index test on a clone running the new collation to uncover duplicate conflicts.

### Exercise 26 — OS inventory

Write commands to collect OS release, glibc, locale list, and ICU version on Linux.

### Exercise 27 — Container images

Why is the host OS version insufficient to determine the collation runtime of a PostgreSQL container?

### Exercise 28 — `pg_upgrade`

Describe how to handle collation mismatch warnings after `pg_upgrade` and why they must not be ignored.

### Exercise 29 — Rollback

Why can downgrading glibc/ICU after reindexing create a mismatch in the reverse direction?

### Exercise 30 — Template databases

Why check `template1` in the inventory and avoid routinely editing `template0`?

### Exercise 31 — Invalid indexes

Write a query checking `indisvalid`/`indisready` and describe how to handle an invalid index left by concurrent reindexing.

### Exercise 32 — Progress

Use `pg_stat_progress_create_index` to monitor `REINDEX`. Which system metrics should be tracked alongside it?

### Exercise 33 — Lock planning

Design a maintenance window for regular `REINDEX` on a large table with heavy write traffic.

### Exercise 34 — Bloat

Distinguish `REINDEX` for collation correctness from `REINDEX` for bloat, `VACUUM`, and `ANALYZE`.

### Exercise 35 — Application behavior

An API uses keyset pagination on a text name column. Why might old cursors become unstable after a collation change?

### Exercise 36 — Multi-database runbook

Design a workflow to run inventory, reindexing, and version refreshing across multiple databases in one cluster.

### Exercise 37 — Standby readiness

Design a health/readiness gate preventing queries from routing to a standby with a mismatched collation version.

### Exercise 38 — Concurrent failure

`REINDEX CONCURRENTLY` fails due to disk full and leaves an invalid index. Write the remediation runbook before refreshing metadata.

### Exercise 39 — Duplicate cleanup

Rebuilding a unique index discovers duplicates under the new collation. Design a workflow involving the data owner to merge records and restore the constraint.

### Exercise 40 — End-to-end production OS upgrade

A system has:

- A PostgreSQL primary and three physical standbys.
- Two logical subscribers for reporting/analytics.
- Unchanged PostgreSQL major version.
- An OS upgrade changing glibc and ICU versions.
- Database default collation using `libc`.
- Several application schemas using named ICU collations.
- Multiple unique indexes on customer names and product labels.
- One standby serving read traffic.
- WAL archive and replication slots with bounded retention.
- A 30-minute downtime budget.

Design:

1. Inventory of OS, providers, locales, and recorded/actual versions.
2. Clone-based tests for sorting, uniqueness, and query plans.
3. Index dependency and unique conflict discovery.
4. Disk/WAL/archive/standby capacity plan.
5. Primary/standby OS upgrade sequence and read traffic gating.
6. Targeted `REINDEX` vs. database-wide strategy.
7. Regular `REINDEX` vs. `CONCURRENTLY` per downtime budget.
8. Physical standby WAL replay and logical subscriber reindexing.
9. `ALTER COLLATION`/`ALTER DATABASE` refresh sequence.
10. Validation, rollback decision point, and post-upgrade monitoring.

## Conclusion

**An OS or ICU upgrade can change the collation semantics that existing indexes rely on.** PostgreSQL stores recorded versions and can warn of mismatches, yet warnings only reveal the risk—they do not rebuild indexes automatically. Database default collations and named collations maintain separate metadata, so check both in every database.

When versions change, identify collation-dependent indexes and constraints, assess duplicate conflicts, capacity, and replication impact, and run `REINDEX` before refreshing version metadata. Regular `REINDEX` can block writes; `REINDEX CONCURRENTLY` reduces blocking yet requires more disk/WAL and carries version/index-type limits. Physical standbys receive index changes via WAL, while logical subscribers require separate handling.

OS/ICU versions must remain consistent across nodes serving the same data. During rolling upgrades, never route collated reads to a node whose runtime comparator differs from the index state. Test on a clone with representative data, keep backups/rollback plans ready, and verify query ordering, uniqueness, indexes, replication, and application behavior.

**Metadata refresh is the final step after reindexing.** Following the proper order ensures PostgreSQL catalogs reflect the new runtime provider only after indexes have been rebuilt under those exact same rules.
