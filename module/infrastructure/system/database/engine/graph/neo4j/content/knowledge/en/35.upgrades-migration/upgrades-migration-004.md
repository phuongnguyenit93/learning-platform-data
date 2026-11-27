# Auditing Deprecated Syntax, Procedures, and Configuration

A Neo4j system can run smoothly for years, yet during a database upgrade, part of an old Cypher syntax stops being valid, an APOC procedure becomes **deprecated**, or a key in `neo4j.conf` is renamed. If you only start the server and call `RETURN 1`, the application can still fail in rarely exercised business paths: batch imports, full-text search, auto-generated repository queries, or maintenance operations.

This lesson belongs to the **Upgrades and Migration** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module, where applications use property graphs, Cypher, indexes/constraints, query tuning, data ingestion, Java Driver, and Spring Data Neo4j (SDN). The goal is to build a **systematic audit of deprecated features** before changing versions of Neo4j or related libraries, rather than discovering breakage only after deploying to production.

> **Version scope:** Migration examples in this lesson span **Neo4j 4.4 → Neo4j 5** and **Cypher 5 → Cypher 25** across the Neo4j 2025/2026 release families. Cypher 25 appeared in **Neo4j 2025.06**; on databases in the **Neo4j 2026.02+** generation, Cypher 25 is the default language per version policy. Syntax, deprecation/removal timelines, and APOC behavior evolve continuously. **Do not assume every example runs on every release**; confirm your exact source version, target version, edition, and Cypher version before applying changes.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **deprecated**, **removed**, **changed behavior**, and **not supported**.
2. Inventory Cypher queries, schema DDL, procedures/functions, and configuration settings at risk during upgrades.
3. Use `SHOW PROCEDURES`, `SHOW FUNCTIONS`, `SHOW SETTINGS`, and query execution warnings to locate deprecated features when supported by the server.
4. Recognize common changes such as `exists(n.prop)`, `USING PERIODIC COMMIT`, `ON ... ASSERT`, `id(n)`, and `CALL` subquery syntax.
5. Distinguish APOC Core vs. Extended and select pure Cypher when an equivalent replacement exists.
6. Migrate legacy configuration keys to new namespaces, validate with `neo4j-admin server validate-config`, and avoid disabling strict validation to hide errors.
7. Build test matrices, cutover/rollback plans, deprecation warning tracking, and post-upgrade data correctness checks.

## 2. Understanding the Lifecycle of a Feature

Not every warning means the application will stop running immediately:

| Status | Meaning | Appropriate action |
|---|---|---|
| **Supported** | Feature is supported on the current version | Still verify exact semantics and performance |
| **Deprecated** | Still works for now, but the vendor recommends migrating to a new alternative | Schedule replacement and add tests before the next upgrade |
| **Removed** | Syntax or procedure is no longer supported by the target version/language | Must be updated beforehand or covered by a supported compatibility mode |
| **Behavior changed** | Still runs, but results, defaults, data types, or query plans differ | Test semantics, data, performance, and edge cases |
| **Unavailable in target environment** | Managed tier/edition lacks the plugin, privileges, or configuration | Choose an alternative, upgrade tiers, or adjust architecture |

**Deprecated is not an error.** A query that succeeds can still return **warning notifications**. Conversely, `CALL apoc.foo(...)` throwing "procedure not found" may mean the plugin is not installed or permissions are missing, not necessarily that the procedure was removed in that version.

### Four Questions Before Replacing Anything

1. Was the feature deprecated in **Cypher 5**, **Cypher 25**, or the entire Neo4j DBMS?
2. **In which version** was it deprecated and **in which version** removed, if announced?
3. Does the replacement preserve **identical results, ordering, data types, and transaction boundaries**?
4. Does it depend on **APOC Core/Extended**, index providers, edition, permissions, or server configuration?

Do not rewrite code solely because two API names look similar. For bulk data ingestion and updates, switching from an APOC procedure to Cypher can alter batching, error handling, and the number of committed transactions.

## 3. Overall Audit Workflow

~~~mermaid
flowchart TD
    A["Lock source/target versions<br/>DBMS, Cypher, APOC, Java Driver, SDN"] --> B["Inventory Cypher queries,<br/>schema, procedures, config"]
    B --> C["Cross-check changelogs and<br/>deprecation warnings"]
    C --> D{"Will features be affected?"}
    D -->|"No"| E["Keep as-is, build regression tests"]
    D -->|"Yes"| F["Choose replacement syntax/API/config"]
    F --> G["Test on staging with representative data"]
    G --> H{"Results, permissions, and SLOs pass?"}
    H -->|"Not yet"| F
    H -->|"Pass"| I["Canary / cutover with runbook"]
    E --> I
    I --> J["Monitor warnings, errors, performance<br/>and rollback readiness"]
~~~

The workflow should produce a **compatibility register**: a list of risky items with owners, priorities, remediation plans, and test evidence. Simply noting "version upgraded successfully" does not tell you whether business logic still behaves accurately.

## 4. Identify the Exact Environment Before Auditing

The same query can run with **different Cypher defaults** across two databases, or on one instance whose APOC build differs from another. At minimum record:

| Item | Verification source | Why is it needed? |
|---|---|---|
| Neo4j DBMS version | `CALL dbms.components()` or deployment inventory | Determines syntax, procedure, and admin tool limits |
| Edition / deployment model | Deployment manifest, console/DBMS metadata | Community/Enterprise/Aura expose different features |
| Active Cypher language | Database version policy and query checks | Cypher 5 differs from Cypher 25 |
| APOC Core/Extended version | Plugin inventory, procedure catalog, install docs | Plugins may split packages or alter procedures |
| Java Driver / SDN / Spring Boot | Application dependency declarations / BOM | Client APIs and generated queries may change |
| Database list & aliases | Database admin commands per privileges | Queries might target a different database than assumed |
| Permission policy | Roles/privileges and actual execution user | Missing privileges can look like removed procedures |
| Server configuration | `neo4j.conf`, `apoc.conf`, env vars, `SHOW SETTINGS` | Keys may be renamed, re-defaulted, or ignored |

Example query on versions supporting the procedure:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

This is one way to identify DBMS components; in restricted environments or managed services, use the official UI or version metadata provided.

**Especially in clusters:** never assume every member runs the same plugins, versions, and config just because one member reports cleanly. Inspect the rolling upgrade plan, member uniformity, and allowed transitional differences.

## 5. Scanning Legacy Cypher Syntax in Source, Query Logs, and Ops Jobs

Cypher lives in many places beyond `.cypher` files:

- Strings in Java Driver code: `tx.run("MATCH ...")`, `driver.executableQuery(...)`.
- `@Query` annotations in Spring Data Neo4j and derived repository method queries.
- Migration scripts creating indexes/constraints, CSV imports, and seed data.
- APOC `apoc.periodic.iterate` embedding Cypher inside two string arguments.
- Scheduled jobs, shell scripts, BI dashboards, and ETL pipelines.
- Queries logged by Neo4j server or application instrumentation.

Not finding a string in source code **does not prove the application doesn't use it**: a repository method can generate Cypher at runtime, or an external job may live outside the current repository. For complete coverage, combine **source scanning**, **live query observation**, and **catalogs of permitted functions/procedures**.

### Initial Audit Keyword Table

| Keyword / pattern | Risk | How to verify |
|---|---|---|
| `USING PERIODIC COMMIT` | Removed in Neo4j 5 | Inspect `LOAD CSV` pipelines and convert batching |
| `exists(n.someProperty)` | Legacy property check removed in Neo4j 5 | Convert to `IS NOT NULL` |
| `CREATE CONSTRAINT ... ON ... ASSERT` | Legacy DDL removed in Neo4j 5 | Use `FOR ... REQUIRE` |
| `CREATE INDEX ON :Label(prop)` | Legacy index syntax removed | Select appropriate RANGE/TEXT/POINT index |
| `CREATE BTREE INDEX` | Legacy B-tree indexes behave differently/removed | Plan index conversion based on queries |
| `SHOW INDEXES BRIEF`/`VERBOSE` | Legacy command removed | Use `SHOW INDEXES`/`YIELD *` |
| `id(n)`/`id(r)` | Internal ID function deprecated | Review `elementId` and business keys |
| `CALL { WITH x ... }` | Legacy variable import deprecated since 5.23 | Use scope clause `CALL (x) { ... }` |
| `apoc.*` | Some procedures/functions replaced by native Cypher | Check changelog, language mode, and Core/Extended |
| `db.index.vector.queryNodes` | Deprecated in Cypher 25 releases starting 2026.04 | Check `SEARCH` syntax and target version |
| `db.index.fulltext.queryNodes` | Deprecated starting Neo4j 2026.10 per Cypher manual | Check target release's `SEARCH` support |

This is an **exploratory checklist**, not an exhaustive list of every removed feature. A keyword might appear inside comments, legacy tests, or documentation; evaluate **actually executed queries** and **the target Cypher language** before changing code.

## 6. Example 1 — Replacing Property Existence Checks with `IS NOT NULL`

In Neo4j 4.4, the following syntax was used:

~~~cypher
// Legacy syntax; DO NOT run on Neo4j 5.
MATCH (c:Customer)
WHERE exists(c.email)
RETURN c.customerId AS customerId;
~~~

From Neo4j 5 onward, the equivalent syntax is:

~~~cypher
MATCH (c:Customer)
WHERE c.email IS NOT NULL
RETURN c.customerId AS customerId;
~~~

Finding missing properties:

~~~cypher
MATCH (c:Customer)
WHERE c.email IS NULL
RETURN c.customerId AS customerId;
~~~

**Why test this?** A property holding an empty string `''` **differs** from a missing property. `c.email IS NOT NULL` still matches empty strings; if business rules require a non-empty email, add explicit validation. **Do not blindly replace every `exists(...)`** via text search because Cypher also has the `EXISTS { ... }` pattern subquery — that is a **different feature**, not the legacy property check.

## 7. Example 2 — Migrating Legacy Constraint and Index DDL

### 7.1. `ON ... ASSERT` Constraints

Legacy Neo4j syntax:

~~~cypher
// LEGACY: do not use for new creation on Neo4j 5.
CREATE CONSTRAINT ON (c:Customer)
ASSERT c.customerId IS UNIQUE;
~~~

Neo4j 5 syntax:

~~~cypher
CREATE CONSTRAINT customer_customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

Then inspect the schema:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
RETURN name, type, labelsOrTypes, properties
ORDER BY name;
~~~

**Note:** `IF NOT EXISTS` prevents the DDL statement from failing if an equivalent object already exists, but it **does not prove** the schema has the exact name, type, or properties your application expects. During migration, reconcile the actual created constraints—especially if source data already contains duplicate IDs preventing the new constraint from being created.

### 7.2. From Legacy Indexes to New Indexes

Before Neo4j 5, some systems used:

~~~cypher
// LEGACY:
CREATE INDEX ON :Customer(name);
~~~

Depending on workload, the new index may be:

~~~cypher
CREATE RANGE INDEX customer_name_range IF NOT EXISTS
FOR (c:Customer) ON (c.name);
~~~

Or, if query predicates and requirements fit:

~~~cypher
CREATE TEXT INDEX customer_name_text IF NOT EXISTS
FOR (c:Customer) ON (c.name);
~~~

There is no rule that "every BTREE becomes TEXT". **RANGE/TEXT/POINT** serve different predicate types; **FULLTEXT** and **VECTOR** serve specialized search workloads. Choose index types based on real queries and verify with `EXPLAIN`/`PROFILE`.

~~~cypher
SHOW INDEXES
YIELD name, type, state, labelsOrTypes, properties
RETURN name, type, state, labelsOrTypes, properties
ORDER BY name;
~~~

Before declaring success, ensure indexes transition to `ONLINE`. Do not merely check that DDL returned success and assume the query planner will use the index.

## 8. Example 3 — Replacing `USING PERIODIC COMMIT`

In Neo4j 4.4 and older documentation, large CSV imports could use:

~~~cypher
// LEGACY: removed in Neo4j 5.
USING PERIODIC COMMIT 1000
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
CREATE (:Customer {customerId: row.customerId});
~~~

Neo4j 5 supports batching via `CALL { ... } IN TRANSACTIONS`. On **Neo4j 5.23+**, use a scope clause:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
CALL (row) {
    MERGE (c:Customer {customerId: row.customerId})
    SET c.name = row.name
} IN TRANSACTIONS OF 1000 ROWS;
~~~

**Important conditions:**

1. Queries containing `CALL ... IN TRANSACTIONS` must run in an **implicit/auto-commit transaction**, not wrapped inside an outer explicit/managed transaction.
2. In Neo4j Browser, depending on version, prefix with `:auto` to run with the right transaction mode; in Java Driver, check the appropriate implicit transaction API.
3. `MERGE` on a stable key should be paired with a **uniqueness constraint** and checks for rows missing IDs; never run `MERGE` blindly on uncleaned data.
4. Earlier **committed** batches remain persisted even if a later batch fails. Never assume the entire CSV rolls back like a single transaction.
5. `CALL (row) { ... }` is the new scope clause syntax in 5.23+; on earlier Neo4j 5 releases, use compatible subquery syntax or upgrade to a supporting release.

**Required tests:** source row count, valid ID count, target node count post-import; mid-batch failure injection; re-running the same file; checkpoints/identity keys; verifying zero duplicate nodes and no unintended aggregate inflation.

## 9. Example 4 — New Scope Clause in `CALL` Subqueries

Neo4j 5.23 deprecated importing variables with `WITH` at the start of a subquery:

~~~cypher
// Old form: may still run in matching Cypher/versions,
// but deprecated on Neo4j 5.23+.
UNWIND [1, 2, 3] AS x
CALL {
    WITH x
    RETURN x * 10 AS y
}
RETURN x, y;
~~~

Replace by declaring imported variables explicitly:

~~~cypher
UNWIND [1, 2, 3] AS x
CALL (x) {
    RETURN x * 10 AS y
}
RETURN x, y
ORDER BY x;
~~~

Expected output: `(1,10)`, `(2,20)`, `(3,30)`. When migrating complex queries, compare **row counts**, **ordering**, **grouping/aggregation levels**, and **variable scopes**. Swapping `CALL { ... }` to `CALL (x) { ... }` does not automatically guarantee identical results if you accidentally omit an imported variable.

## 10. `id()`, `elementId()`, and Business Identity Keys

`id(node)` and `id(relationship)` are deprecated; use `elementId()` when you need to reference a Neo4j entity within vendor-documented boundaries.

~~~cypher
MATCH (c:Customer)
RETURN elementId(c) AS elementId,
       c.customerId AS customerId
LIMIT 10;
~~~

**However, do not merely switch from "storing `id(c)` as a business key" to "storing `elementId(c)` as a business key"** and assume the risk is gone. Internal/element IDs are not guaranteed to remain stable across all transactions, delete/recreate operations, backups/restores, or database migrations.

If `customerId` identifies a customer, pair it with a uniqueness constraint:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

MATCH (c:Customer {customerId: $customerId})
RETURN c;
~~~

Java Driver/SDN applications should pass `customerId` as a query parameter rather than embedding old environment internal IDs into REST/API paths. This is a **data model change** requiring data migration and mapping tests, not merely swapping a Cypher function.

## 11. Auditing Procedures and Functions with `SHOW`

On Neo4j 5.9+ and releases supporting the `isDeprecated` column:

~~~cypher
SHOW PROCEDURES
YIELD name, signature, isDeprecated
WHERE isDeprecated
RETURN name, signature
ORDER BY name;
~~~

~~~cypher
SHOW FUNCTIONS
YIELD name, signature, isDeprecated
WHERE isDeprecated
RETURN name, signature
ORDER BY name;
~~~

These commands return **features currently present and visible** on the connected server/account. They **cannot** discover names already **removed** completely: a missing procedure could also mean an uninstalled plugin, missing privileges, or a different Cypher language mode.

On newer versions exposing `deprecatedBy`, you can inspect replacement hints:

~~~cypher
SHOW PROCEDURES
YIELD name, isDeprecated, deprecatedBy
WHERE isDeprecated
RETURN name, deprecatedBy
ORDER BY name;
~~~

~~~cypher
SHOW FUNCTIONS
YIELD name, isDeprecated, deprecatedBy
WHERE isDeprecated
RETURN name, deprecatedBy
ORDER BY name;
~~~

`deprecatedBy` can be `null` even when a function is deprecated, because not every feature has a single one-to-one replacement name. On older Neo4j 5 releases lacking these columns, run `SHOW ... YIELD *` to inspect the actual output schema first.

### Filtering by Library Prefix

~~~cypher
SHOW PROCEDURES
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
   OR name STARTS WITH 'gds.'
RETURN name, signature
ORDER BY name;
~~~

~~~cypher
SHOW FUNCTIONS
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
   OR name STARTS WITH 'gds.'
RETURN name, signature
ORDER BY name;
~~~

Zero `gds.*` results do not automatically mean GDS was removed: Graph Data Science might simply not be installed in that environment. On Neo4j Aura, Core/Extended and GDS availability also depend on **product/tier**.

**Reliable procedure verification workflow:**

1. Extract **exact full names and signatures** from applications/jobs in use.
2. Check source-version docs to understand behavior and output structure.
3. Verify the target environment **has and permits calling** those exact procedures/functions.
4. Check **deprecations/removals** in release notes for the exact Cypher version.
5. Run tests comparing outputs and side effects using the real application user, not only an admin account.

## 12. APOC Core, APOC Extended, and Cypher 25

Starting with Neo4j 5, APOC was split into **APOC Core** (officially supported by Neo4j) and **APOC Extended** (community-maintained). An older system using "APOC Full" cannot assume dropping in a single Core JAR on the new release suffices.

When upgrading APOC, audit **both the Neo4j version and the Cypher language**:

- Neo4j 2025.06 introduced **Cypher 25**, while allowing **Cypher 5** selection in supported ways.
- APOC changes from the 2025.07+ generation onward target **Cypher 25**; APOC functionality for Cypher 5 is frozen at its corresponding milestone.
- A procedure lacking Cypher 25 support may still run under `CYPHER 5` **when the environment supports that language mode and the procedure is still shipped**. This is a conditional compatibility bridge, not a long-term migration plan.
- Several APOC utilities have complete or near-equivalent **pure Cypher** alternatives, though semantics must be checked case by case.

Example observing language mode:

~~~cypher
// Only available on DBMS releases supporting Cypher version selection (Neo4j 2025.06+).
CYPHER 5
RETURN randomUUID() AS requestId;
~~~

~~~cypher
CYPHER 25
RETURN randomUUID() AS requestId;
~~~

Both queries illustrate selecting the **language version per query**. You cannot prefix `CYPHER 25` on Neo4j 5.26 and expect the driver to translate it; that server does not support the language.

### Common APOC Replacement Options

| Legacy pattern | New direction / condition | Migration notes |
|---|---|---|
| `apoc.create.uuid()` | `randomUUID()` when a UUID string is needed | Does not replace business ID uniqueness constraints |
| `apoc.coll.contains(list, x)` | `x IN list`; APOC docs note deprecation in Cypher 25 | Check `null` handling and data types |
| `apoc.do.when`/`apoc.do.case` | Conditional queries in Cypher 25 where supported | Check write branches, return values, and row counts |
| `apoc.periodic.iterate` | `CALL { ... } IN TRANSACTIONS`; consider `IN CONCURRENT TRANSACTIONS` where Cypher 25 supports it | Differs in batch config, transaction boundaries, retries, and commits |
| `apoc.import.csv` | `LOAD CSV` when functional scope fits | Verify file/URL sources and import conventions |
| `apoc.load.json` | Parse in Java/application or retain APOC if environment allows | No universal single `LOAD JSON` equivalent across all versions |

Notably, `apoc.periodic.iterate` is marked deprecated in **Cypher 25 starting in APOC/Neo4j 2026.04**. This **does not mean** you must immediately halt a live production pipeline; verify your actual version, the risk of the target removing support, and build a tested migration plan.

### Do Not Mechanically Swap for a Similar-Looking Query

Suppose a legacy job uses `apoc.periodic.iterate` with `batchSize=1000`, `parallel=true`, `retries`, and string-interpolated queries. When rewriting to Cypher:

1. Define the **source row stream** and variable imports.
2. Choose sequential vs. concurrent execution as supported by your version.
3. Define **batch size**, single-batch failures, and `ON ERROR` strategy if available.
4. Inspect already **committed batches** if the job aborts midway.
5. Design **idempotency/checkpoints** so retries never create duplicates.
6. Measure resource usage, lock contention, node/relationship counts, and business aggregates.

Changing batching mechanics affects both performance and **correctness**, so test on sufficiently large sample data and failure cases.

## 13. GQLSTATUS, Deprecation Notifications, and Live Execution

Some deprecated syntax is still accepted by Neo4j while emitting **notifications**. To detect them, execute the **exact queries your application runs**, not rewritten test approximations.

### 13.1. `EXPLAIN` as an Initial Compatibility Probe

~~~cypher
EXPLAIN
MATCH (c:Customer)
WHERE c.customerId = $customerId
RETURN c.email AS email;
~~~

`EXPLAIN` compiles the query and shows the planned execution without **running it**. If syntax is invalid, it errors early; for certain discouraged constructs, it can emit notifications.

However, `EXPLAIN` **does not prove** write transactions, side-effecting procedures, permissions, real data, or Java object mappings are correct. To verify runtime behavior, run integration tests and inspect graph state.

### 13.2. Observing Notifications in Java Driver

Neo4j Java Driver exposes `ResultSummary`, including notifications/server status objects from execution. On older driver versions supporting the legacy API:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

void inspectQuery(Driver driver) {
    try (Session session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        var result = session.run("""
            EXPLAIN
            MATCH (n:Customer)
            RETURN n.email AS email
            LIMIT 10
            """);

        var summary = result.consume();
        summary.notifications().forEach(notification -> {
            System.out.println(notification.code());
            System.out.println(notification.description());
        });
    }
}
~~~

In newer driver releases, `ResultSummary.gqlStatusObjects()` is the direction for GQL-aligned status observation; `notifications()` may be a legacy/deprecated compatibility API depending on version. In production code, **pin your Java Driver version**, use the matching notification API, and collect structured events rather than parsing human-readable strings.

Never print sensitive data or full query text with parameters to logs. If CI collects deprecation warnings, record **code, category, location, test name, and environment version**; deduplicate cleanly, but never suppress new warnings.

### 13.3. Do Not Silence Warnings Just to Get "Green Tests"

Raising notification severity thresholds or disabling a warning category reduces log noise, yet **never fixes** deprecated features. During migration, capture full warning telemetry in test environments and **turn relevant warnings into tracked engineering tasks** with owners and deadlines.

## 14. Auditing Renamed or Obsolete Configuration Keys

Between Neo4j 4.4 and 5, many `neo4j.conf` keys were reorganized into namespaces such as `server`, `dbms`, `db`, `initial`, `browser`, and `client`. Several defaults and value types also changed.

### Common Renames to Recognize

| Legacy key | Example Neo4j 5 key | Purpose |
|---|---|---|
| `dbms.memory.heap.initial_size` | `server.memory.heap.initial_size` | Initial JVM heap |
| `dbms.memory.heap.max_size` | `server.memory.heap.max_size` | Maximum JVM heap |
| `dbms.memory.pagecache.size` | `server.memory.pagecache.size` | Page cache |
| `dbms.connector.bolt.listen_address` | `server.bolt.listen_address` | Bolt listen address |
| `dbms.logs.query.enabled` | `db.logs.query.enabled` | Query logging |
| `metrics.enabled` | `server.metrics.enabled` | Metrics subsystem per supported version |
| `dbms.config.strict_validation` | `server.config.strict_validation.enabled` | Startup config validation; semantics/default changed |

This table is a **directional guide** for 4.4 → 5 migration, not an exhaustive mapping, and does not apply blindly to all 2025/2026 releases. Some keys were **removed**, some changed **semantics or valid values**, and some apply only to Enterprise. Cross-check the official *Changes to configuration settings in Neo4j 5* reference before migrating.

### Principles for Updating Configuration

1. **Inspect source and target builds**: know the exact config files, container env vars, Helm chart values, and overrides in play.
2. **Diff explicitly declared keys**, separating defaults from customized settings.
3. **Map keys individually** against official tables rather than running global search-and-replace from `dbms.` to `server.`.
4. **Verify new values and defaults**, especially memory, timeouts, logging, clustering, and security.
5. **Validate before startup**, then verify runtime values after boot.
6. **In clusters, verify every member**; a config working on the first node does not guarantee the entire cluster matches.

Do not copy `internal.*` keys from changelogs into production merely because their names resemble replacements. Neo4j neither supports nor recommends tuning internal settings; they can change without notice.

## 15. Inspecting Runtime Configuration with `SHOW SETTINGS`

When authorized to view settings, you can list **deprecated** settings:

~~~cypher
SHOW SETTINGS
YIELD name, value, defaultValue, isExplicitlySet, isDeprecated
WHERE isDeprecated
RETURN name, value, defaultValue, isExplicitlySet
ORDER BY name;
~~~

Or focus on critical settings:

~~~cypher
SHOW SETTINGS
YIELD name, value, startupValue, isExplicitlySet
WHERE name STARTS WITH 'server.memory.'
   OR name STARTS WITH 'server.bolt.'
   OR name STARTS WITH 'db.logs.query.'
RETURN name, value, startupValue, isExplicitlySet
ORDER BY name;
~~~

**Three important limitations:**

- `SHOW SETTINGS` includes the `isDeprecated` column in supporting Neo4j 5 releases (5.9+); older versions may omit it.
- `SHOW SETTINGS` reflects configuration on **the server handling the query**, **not an aggregate across all members**. To inspect a specific member, connect directly via `bolt://` with appropriate privileges per ops docs.
- This command **is unavailable on Neo4j Aura** per current Operations documentation. On Aura, use the provider's configuration surfaces rather than mistaking a `SHOW SETTINGS` error for database corruption.

`isExplicitlySet = false` means the setting uses the current version's default, not necessarily an "ignored setting". A default value change during an upgrade can alter system behavior even when operators **did not touch** the config file.

## 16. Validate Config Files Before Startup

On self-managed Neo4j environments providing the admin subcommand:

~~~bash
bin/neo4j-admin server validate-config
~~~

For detailed output:

~~~bash
bin/neo4j-admin server validate-config --verbose
~~~

This command checks Neo4j and Log4j configurations as supported by that installation; run it inside **the target version's image/container/host** using the exact config intended for deployment. "Validation successful" **does not prove** APOC procedures are installed properly, licenses are valid, clusters hold quorum, stores are compatible, or Java Driver works. It is a **config validation gate**, not a complete migration test.

### Do Not Disable Strict Validation to Bypass Errors

Neo4j 5 enables strict configuration validation by default:

~~~properties
# Default behavior in Neo4j 5; keep true whenever possible.
server.config.strict_validation.enabled=true
~~~

Leaving a legacy key inside `neo4j.conf` can cause the server to **refuse to start**. The fix is migrating to the proper key, not flipping `strict_validation` to `false` and treating the issue as solved. In certain config scenarios, disabling strict validation causes invalid settings to be **silently ignored**, producing an unintended runtime state.

## 17. Special Case: `apoc.conf` Settings No Longer Go in `neo4j.conf`

Starting with APOC/Neo4j 5, `apoc.*` options belong in **`apoc.conf`** (in the same config directory as `neo4j.conf`), or in APOC-supported **environment variables**.

**Wrong on Neo4j 5:**

~~~properties
# neo4j.conf -- legacy, DO NOT keep apoc.* here.
apoc.import.file.enabled=true
apoc.export.file.enabled=true
~~~

**Correct configuration placement:**

~~~properties
# apoc.conf -- example restrictive defaults.
apoc.import.file.enabled=false
apoc.export.file.enabled=false
~~~

`apoc.conf` may not exist out of the box when installing the plugin; deployment teams must manage the file if custom options are needed. Leaving `apoc.*` inside `neo4j.conf` on version 5 can cause strict validation to reject startup or **silently ignore** them if validation is disabled.

**Do not flip file import/export to `true` just to pass a test error.** File access, URL loading, and extended procedures require security review. Neo4j settings controlling procedure allowlists/unrestricted procedures belong to Neo4j configuration policy, not blindly moved into `apoc.conf`.

## 18. Java Driver and Spring Data Neo4j Must Also Be Audited

Even when hand-written Cypher is compatible, an application can still hit:

- Legacy driver APIs deprecated or renamed across major upgrades.
- Different transaction retry, callback, and timeout mechanics.
- Derived repository queries generating new Cypher patterns.
- `@Query` calling a removed procedure or one available only in APOC Extended.
- Entity mappings, relationship loading, or custom queries dropping returned fields.
- Newer Spring Boot/SDN layers using different packages, modules, and BOM dependencies.

### Java Driver Managed Transaction Example

Recommended modern API:

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    return session.executeRead(tx -> tx.run("""
        MATCH (c:Customer {customerId: $customerId})
        RETURN c.name AS name
        """, Map.of("customerId", customerId))
        .single().get("name").asString());
}
~~~

If the application still uses legacy APIs like `readTransaction(...)`/`writeTransaction(...)`, check the migration guide for the **exact Java Driver version** you are adopting; `executeRead`/`executeWrite` are the modern equivalents. Do not merely rename methods while forgetting that managed transaction callbacks **may retry**, as retrying non-idempotent writes can create duplicate data or repeat external side effects.

### With Spring Data Neo4j

1. Pin and cross-check the **Spring Boot BOM + SDN + Neo4j Java Driver + Java runtime** combination.
2. Run `@DataNeo4jTest` and integration tests against the **target Neo4j version**.
3. Inspect the **actual Cypher** emitted by SDN via logging/query logs rather than guessing from repository method names.
4. Test **derived queries**, `@Query`, read-only transactions, and node/relationship mappings.
5. Compare node/relationship counts and aggregations to catch row multiplication or result drift.
6. For server-side deprecations, collect notifications from real repository calls rather than only Neo4j Browser queries.

If a managed tier restricts access to server query logs or settings, add application-layer instrumentation to gather compatibility evidence without attempting unauthorized server inspection.

## 19. Migration Test Matrix

| Item | Pre-upgrade test | Target-version test | PASS condition |
|---|---|---|---|
| Cypher read queries | Parameter sets and baseline results | Execute real queries + capture notifications | Identical business data and zero removed/blocking deprecations |
| Write queries | Before/after state, business keys | Replay on test graph | No duplicate nodes/relationships, accurate transactions |
| `CALL` subqueries | Variable imports, aggregation, cardinality | Compare old/new syntax | Same row counts, types, values, and side effects |
| CSV imports | Valid/duplicate/malformed rows, batch checkpoints | Run `IN TRANSACTIONS` | Exact row/node/edge counts, clean recovery after failure |
| Indexes/constraints | `SHOW INDEXES`/`SHOW CONSTRAINTS` | Create and verify status | Equivalent schema, indexes ONLINE |
| APOC/GDS | List of actually used procedures/functions | Check presence/deprecation and execute APIs | Compatible behavior, permissions, and results |
| Config | List of source overrides and defaults | `validate-config` + runtime settings | No removed keys or misapplied semantics |
| Java Driver/SDN | Regression tests and query logs | Run against target server | Correct outputs, mappings, and retries |
| Security | Roles, procedure privileges, TLS | Positive/negative authorization tests | No excessive privileges or data leaks |
| Performance | p50/p95/p99, DB Hits, throughput | Benchmark on representative data | Meets SLO within accepted tolerance |
| Recovery | Backup/restore and cutover runbook | Restore rehearsal, rollback dry-run | RPO/RTO and reconciliation pass |

**Why use identical data and parameters?** A `MATCH` query can change plans due to index statistics or different relationship distributions. Testing source on 100 nodes and target on 10 million nodes makes it impossible to distinguish version regressions from data-scale effects.

### Small Regression Test Example

Test dataset:

~~~cypher
CREATE CONSTRAINT mig_customer_id_unique IF NOT EXISTS
FOR (c:MigCustomer)
REQUIRE c.customerId IS UNIQUE;
~~~

~~~cypher
MERGE (a:MigCustomer {customerId: 'C01'})
SET a.email = 'an@example.test'
MERGE (b:MigCustomer {customerId: 'C02'})
SET b.email = null
MERGE (o:MigOrder {orderId: 'O01'})
SET o.amount = 120000
MERGE (a)-[:PLACED]->(o);
~~~

Verify invariant outputs:

~~~cypher
MATCH (c:MigCustomer)
RETURN count(c) AS customers,
       count(c.email) AS withEmail;
// customers = 2, withEmail = 1
~~~

~~~cypher
MATCH (c:MigCustomer)-[:PLACED]->(o:MigOrder)
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       o.amount AS amount;
// C01, O01, 120000
~~~

When replacing `exists(c.email)` with `c.email IS NOT NULL`, node sets must match across missing, empty, and null values. When migrating `CALL` queries, add tests with multiple relationships, aggregations, and ordering—testing a single node often misses cardinality bugs.

## 20. Warning Prioritization and Compatibility Register

Not every deprecated feature carries equal risk:

| Priority | Condition | Example | Action |
|---|---|---|---|
| **P0 — Upgrade blocker** | Target already removed the feature and critical flows rely on it | `USING PERIODIC COMMIT` moving to Neo4j 5 | Fix and test before cutover |
| **P1 — Near-term risk** | Deprecated in target or nearing removal deadline, affecting data | `apoc.periodic.iterate` in relevant Cypher 25 releases | Assign owner and migration date, test before release |
| **P2 — Operational risk** | Legacy config/default changed, risking downtime or drift | Legacy `dbms.logs.query.enabled` | Migrate config and validate |
| **P3 — Tracked tech debt** | Deprecated with no immediate deadline / low impact | APOC helper with pure Cypher equivalent | Track and avoid adding new usage |

Sample register:

| ID | Usage location | Feature/config | Source → Target | Risk | Replacement | Owner | Evidence |
|---|---|---|---|---|---|---|---|
| MIG-001 | Import job | `USING PERIODIC COMMIT` | 4.4 → 5.26 | Removed | `CALL ... IN TRANSACTIONS` | Data team | Batch replay PASS |
| MIG-002 | Repository `@Query` | `id(n)` | 5 → 2026.x | Deprecated | Business ID / `elementId` per scope | API team | Integration test PASS |
| MIG-003 | APOC job | `apoc.periodic.iterate` | Cypher 5 → 25 | Deprecated per release | Cypher batch + redesigned retries | Platform | Load test PENDING |
| MIG-004 | Deployment config | `apoc.import.file.enabled` in `neo4j.conf` | 4.4 → 5 | Wrong config file | `apoc.conf` | SRE | validate-config PASS |

The PASS/PENDING statuses above are **illustrative examples**, not evidence from a real tested system.

## 21. Controlled Upgrade and Rollback Plan

### Step 1 — Baseline and Backup

Capture versions, schemas, plugin lists, overridden settings, existing warnings, and critical queries. Create backups using supported procedures and **rehearse restoring** into a clean environment. Understand the vendor-supported upgrade path; **never assume you can downgrade an upgraded store simply by swapping Docker images**.

### Step 2 — Run the Compatibility Audit

Scan source code/query logs, use `SHOW` commands to surface deprecations, and review source/target changelogs. Mark **removed** dependencies as blockers and turn risky deprecations into concrete tasks. Update configurations in a version-controlled branch or manifest.

### Step 3 — Remediate and Test on Staging

Provision a staging database close to production data, run schema scripts, imports, and Java/SDN integration tests. Collect notifications and compare data, outputs, and permissions. Measure p95/p99, throughput, contention, locks, and rollback under load.

### Step 4 — Canary and Rollback Checks

Depending on standalone/cluster/managed architecture, prepare canary or rolling upgrades matching **topology and version documentation**. Define explicit stop criteria: Cypher errors, data loss, abnormal failover, timeout spikes, or p99 breaches.

Rollback must account for **data written on the new version**. If store format changed or new writes arrived, **reverting binaries to the old version** may not be supported. You may need to restore backups onto an older environment and replay/reconcile post-cutover writes.

### Step 5 — Post-Cutover

- Watch for new exceptions and deprecation warnings.
- Verify ETL jobs, CSV imports, GDS/APOC jobs, and rarely executed scheduled tasks.
- Compare query/transaction/lock dashboards against baseline.
- Verify procedure privileges and TLS without loosening permissions to "paper over" upgrade errors.
- Reconcile nodes/relationships/indexes once load stabilizes.
- Close the compatibility register only with verified evidence, not merely because deployment reported "success".

## 22. Common Pitfalls

| Pitfall | Why is it dangerous? | How to avoid |
|---|---|---|
| Upgrading container and running only `RETURN 1` | Misses app queries, plugins, jobs, and data bugs | Integration tests and compatibility inventory |
| Treating deprecated as immediately removed | Triggers rushed rewrites or misses planned migrations | Read exact version/changelog milestones |
| Assuming "procedure not found" always means removed | May be missing plugin, missing privileges, or Cypher mode | `SHOW PROCEDURES`, install checks, RBAC, and docs |
| Replacing every `id(n)` with `elementId(n)` for business IDs | Still couples logic to DB-managed IDs | Use durable business keys |
| Switching BTREE to TEXT without checking queries | Filters/sorts may stop using indexes | Choose RANGE/TEXT/POINT per predicates |
| Replacing `USING PERIODIC COMMIT` without batch-commit handling | Risks partial writes and duplicates on retry | Checkpoints/idempotency, test mid-job failures |
| Keeping `apoc.*` in `neo4j.conf` | Startup fails or settings ignored on Neo4j 5 | Move properly to `apoc.conf`/env |
| Disabling strict validation | Masks config errors and causes drift | Fix keys and use `validate-config` |
| Auditing only one cluster member | Other members may have different plugins/configs/versions | Inspect every member per topology |
| Skipping SDN query/notification logging | Misses framework-generated queries | Log and test real emitted queries |
| Running `PROFILE` on write queries in production | `PROFILE` executes the query with side effects | Use staging/backups, `EXPLAIN` first |
| Rolling back purely via Docker tag swap | Upgraded store/new writes may lack backward compatibility | Backup/restore, reconciliation, and runbook |

## 23. Self-Practice Exercises

### Exercise 1 — Identifying Syntax to Fix

A Neo4j 4.4 system contains:

~~~cypher
MATCH (c:Customer)
WHERE exists(c.email)
RETURN id(c) AS id, c.email AS email;
~~~

When migrating to Neo4j 5, what will you change? Should you return `elementId(c)` instead of `id(c)` and keep using it as a business key?

**Suggested answer:** Replace `exists(c.email)` with `c.email IS NOT NULL`; `id(c)` is deprecated—`elementId(c)` can replace it when a DB-provided identifier is strictly needed, yet it **should not** serve as a long-term business key. Use a business `customerId` backed by a uniqueness constraint.

### Exercise 2 — Missing Procedure

After upgrading to a new environment, `CALL apoc.load.json(...)` throws "procedure not found". Name at least four possible causes and how to verify each.

**Suggested answer:** Core/Extended plugin not installed; APOC version mismatches Neo4j; procedure unsupported in the active Cypher language mode; blocked by allowlist/permissions; or genuinely removed in the target version. Check `SHOW PROCEDURES`, versions, role/procedure privileges, release notes, and managed service support lists.

### Exercise 3 — Replacing Batching

A legacy job used `USING PERIODIC COMMIT 1000`. When converting to `CALL { ... } IN TRANSACTIONS OF 1000 ROWS`, why must you test resuming after a failure in batch three?

**Suggested answer:** Because earlier batches may have committed while the failing batch rolled back; non-idempotent reruns can create duplicates or double-count aggregates. You need uniqueness constraints, `MERGE` by business key, checkpoints, and post-resume reconciliation.

### Exercise 4 — "Ignored" Configuration

An operator keeps `apoc.import.file.enabled=true` in `neo4j.conf` after upgrading to Neo4j 5, then disables `server.config.strict_validation.enabled` so the server starts. What is wrong?

**Suggested answer:** `apoc.*` settings belong in `apoc.conf` or matching environment variables. Disabling strict validation can cause invalid settings to be silently ignored, making runtime behavior diverge and weakening safety. Move the setting to the valid file and enable file import only under proper security policy.

### Exercise 5 — Zero Warnings Seen

The team runs `SHOW PROCEDURES` and sees no procedure with `isDeprecated=true`. Can they conclude the application uses zero deprecated features?

**Suggested answer:** No. That list only covers existing visible procedures; deprecated Cypher syntax may sit in queries, deprecated functions live in a separate view, removed procedures will not appear, and unexecuted jobs were not audited. Source inventory and runtime notifications from real app calls are required.

### Exercise 6 — Behavioral Change After Migration

A query rewritten from `CALL { WITH x ... }` to `CALL (x) { ... }` executes without errors, yet row count triples. Can migration be considered successful?

**Suggested answer:** No. Reconcile imported variables, grouping, relationship expansion, and aggregation, comparing outputs on identical datasets. Successful compilation is only one check; **semantics and business outputs** determine PASS.

### Exercise 7 — Post-Upgrade Rollback

A team upgrades Neo4j, lets the application write data for a day, and then tries swapping binaries back to the old version after spotting a bug. Why is this plan unsafe?

**Suggested answer:** The store may have been upgraded and lack direct downgrade support; newly written data does not exist in pre-cutover backups. You need a supported restore/failback plan, synchronization/reconciliation of new writes, and verification before routing traffic back to the old environment.

## 24. Official References for Version Cross-Checking

- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/)
- [Breaking changes between Neo4j 4.4 and Neo4j 5](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/migration/breaking-changes/)
- [Changes to configuration settings in Neo4j 5](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/changelogs/configuration-settings/)
- [Cypher additions, deprecations, removals and compatibility](https://neo4j.com/docs/cypher-manual/current/deprecations-additions-removals-compatibility/)
- [Cypher — Show functions](https://neo4j.com/docs/cypher-manual/current/functions/show-functions/)
- [Neo4j Operations — Show procedures](https://neo4j.com/docs/operations-manual/current/procedures/show-procedures/)
- [Neo4j Operations — Show configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/show-settings/)
- [Neo4j Operations — Validate configurations](https://neo4j.com/docs/operations-manual/current/configuration/validate-config/)
- [APOC Core — Migration Guide](https://neo4j.com/docs/apoc/current/migration-guide/)
- [APOC and Cypher versions](https://neo4j.com/docs/apoc/current/apoc-and-cypher/cypher-versions/)
- [Migrate APOC procedures/functions to Cypher](https://neo4j.com/docs/apoc/current/apoc-and-cypher/cypher-migration/)
- [Neo4j Java Driver — Result summaries and notifications](https://neo4j.com/docs/java-manual/current/result-summary/)
- [Spring Data Neo4j reference](https://docs.spring.io/spring-data/neo4j/reference/)

`current` URLs update with each release. During implementation, **lock documentation to your exact source/target versions**, especially across Neo4j 5 → 2025/2026 and Cypher 5 → Cypher 25. A feature may be deprecated yet still work, or removed in Cypher 25 while remaining available under `CYPHER 5` where supported by the server and APOC.

## 25. Key Takeaways

- **Deprecated is a warning to manage**, whereas **removed is a compatibility blocker to resolve** before upgrading.
- **Audit Cypher, schema DDL, procedures/functions, configuration, plugins, and client libraries**; never check server startup alone.
- **`SHOW PROCEDURES`, `SHOW FUNCTIONS`, `SHOW SETTINGS`, and runtime notifications** help uncover deprecations, yet do not replace source inventories and integration tests.
- **Cypher 5 and Cypher 25 have distinct lifecycles**; `CYPHER 5` is a conditional compatibility bridge, not a permanent strategy to avoid migration.
- **Audit APOC Core/Extended and `apoc.conf` independently** from `neo4j.conf`; never loosen plugin permissions or disable strict validation just to mask errors.
- **Semantic and rollback testing** matter as much as syntax: node/relationship counts, data, transactions, privileges, latency, and recovery must all be verified.
