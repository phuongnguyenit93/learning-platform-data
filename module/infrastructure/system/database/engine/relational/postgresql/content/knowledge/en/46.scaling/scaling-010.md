# Evaluating Reliability, Performance, and Portability Before Depending on a PostgreSQL Extension

PostgreSQL has a rich ecosystem of extensions. An extension can add data types, functions, operators, index access methods, background workers, search capabilities, geospatial processing, job scheduling, observability, or external service integrations. The right extension can solve a problem quickly and effectively. Yet once an extension enters production, both the database and the application begin depending on its source code, binaries, schema objects, release cadence, and support policy.

The cost of a choice goes beyond installation time. An extension can impact backend stability, query latency, WAL volume, vacuuming, backup/restore, failover, major upgrades, security, and database portability to another platform. An extension that works smoothly on a developer laptop may lack packages for the production operating system, be disallowed by a managed PostgreSQL service, or lack builds for the next major version.

Therefore, before depending on an extension, systematically evaluate three pillars: **reliability** (maintainers, quality, security, support, and failure modes), **performance** (overhead, latency, throughput, I/O, WAL, and operations), and **portability** (PostgreSQL versions, OS/architecture, packaging, managed services, backup/restore, replication, and upgrade paths). Then prove viability with tests using a representative workload and clear acceptance criteria.

This lesson belongs to the **Scaling** chapter of the *Database Engine Relational PostgreSQL* module. It focuses on PostgreSQL extensions and database-coupled extensibility components. The principles also apply when evaluating foreign data wrappers, procedural languages, plugins, drivers, or supporting services that the system will rely on.

> **Principle:** Never ask only whether an extension solves the use case. Determine who maintains it, what happens when it fails, what resources it consumes, and how the system can upgrade or exit from it.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what an extension is and how it differs from built-in PostgreSQL features.
2. Identify SQL-only, C/shared library, procedural language, and background worker extensions.
3. Inspect installed extensions, versions, dependencies, and installation state.
4. Evaluate maintainers, release cadence, issue trackers, security policies, and support.
5. Read licenses and identify distribution or operational constraints.
6. Assess installation privileges, trusted status, and risks of executing code inside the database backend.
7. Verify package provenance, build provenance, ABI, and dependencies.
8. Evaluate compatibility across PostgreSQL major and minor versions.
9. Check support across operating systems, CPU architectures, and managed services.
10. Determine impacts on backup, restore, replication, failover, and `pg_upgrade`.
11. Design benchmarks with baselines and representative workloads.
12. Measure latency, throughput, CPU, memory, I/O, WAL, and impact on replicas.
13. Evaluate index/operator classes, vacuum, bloat, and maintenance costs.
14. Execute a proof of concept with acceptance criteria and failure scenarios.
15. Build a dependency inventory, risk register, and migration/exit plan.
16. Decide whether to adopt, pilot, defer, or reject an extension based on evidence.

## 2. What Is a PostgreSQL Extension?

An extension is a package of database objects and/or executable code installed into PostgreSQL to add functionality. An extension may provide:
- SQL functions and procedures.
- Data types, casts, and operators.
- Operator classes/families and index support.
- Views, tables, and metadata.
- Triggers.
- Procedural language handlers.
- Background workers.
- Shared libraries loaded by PostgreSQL on demand or at server startup.
- Administrative or integration utilities.

An extension is typically declared via a control file and one or more SQL installation scripts. For extensions with native code, the package also includes shared libraries loaded by PostgreSQL on demand or at server startup.

### 2.1. Extensions vs. Self-Written Database Objects

A hand-written SQL/PLpgSQL function can be managed as an ordinary schema object. An extension bundles objects into a single versioned release unit with its own dependencies and upgrade scripts.

PostgreSQL records installed extensions in the `pg_extension` catalog. Objects owned by an extension hold dependency links to that extension. While this simplifies package-level updates and drops, it also means extension operations can affect many objects at once.

### 2.2. Extensions Are Not Installed Automatically Just Because Metadata Exists

`CREATE EXTENSION` reads control files and SQL scripts on the server. If an extension includes native code, the corresponding shared library must also exist on every PostgreSQL host that loads it. These files do not reside inside database catalogs and are not shipped to standbys via WAL replication like an OS package.

### 2.3. An Extension Is Not Automatically a Safe Plugin

Extensions can execute code inside PostgreSQL backend processes. A memory bug, crash, or deadlock in native code can bring down a backend or the entire server. Treat evaluating an extension with the same rigor as evaluating any dependency running inside critical database infrastructure.

## 3. Extension Types and Operational Implications

| Type | Characteristics | What to evaluate |
|---|---|---|
| SQL-only | Primarily SQL objects/functions | Scripts, dependencies, query cost, SQL upgrades |
| PL/pgSQL or procedural language | Runs code via a language handler | Runtime, permissions, trust model, sandbox |
| C/shared library | Native code loaded into PostgreSQL | ABI, memory safety, crash risk, per-major builds |
| Index/operator extension | Adds access methods, opclasses, or operators | Index correctness, build/reindex, planner, vacuum |
| Background worker | Runs processes/workers alongside the server | Lifecycle, restart, CPU/memory, failure handling |
| FDW/integration | Connects to external systems | Network, credentials, consistency, timeouts, remote availability |
| Observability/admin | Exposes views, stats, or helper functions | Privileges, overhead, version-specific catalogs |

An extension can span multiple categories—for example, SQL objects, a native library, and a background worker. Evaluate every component.

### 3.1. SQL-Only Does Not Mean Zero Overhead

SQL functions can perform expensive joins, scans, or acquire locks. A view can hide a very costly query. Measure on a real workload.

### 3.2. Native Code Carries Distinct Risks

C extensions can access PostgreSQL internals and execute inside the backend's address space. Bugs can cause segmentation faults, memory corruption, or server instability. Native code requires reviewing build provenance, compatibility, and security response.

### 3.3. FDWs Depend on External Systems Too

An FDW can make PostgreSQL queries depend on networks, remote credentials, remote schemas, and external system behavior. Local database availability does not guarantee remote source availability.

## 4. Defining the Use Case and Actual Requirements

Before searching for an extension, document the exact problem to solve.

Describe:
- Required business capability.
- Workload and data shape.
- Expected queries/operations.
- Throughput and latency targets.
- Data freshness/consistency requirements.
- Security boundaries.
- Availability/RPO/RTO.
- Data retention.
- Growth forecast.
- Operational owner.

### 4.1. Define Measurable Success Criteria

Examples:
- Query p95 under 100 ms at concurrency 50.
- Ingest reaches 20,000 rows/second in a test workload.
- Existing transaction p99 latency increases by no more than 5%.
- Replica lag stays within SLA.
- Staging restore completes within target RTO.
- Packages exist for all supported PostgreSQL versions.

These are illustrative examples. Every system must choose thresholds grounded in its actual SLOs and baselines.

### 4.2. Check Built-In Features First

Before adding a dependency, check whether PostgreSQL core already provides an adequate capability. Built-in features benefit from compatibility, security reviews, and upgrade lifecycles tied directly to PostgreSQL releases.

Built-in is not always superior—an extension may offer specialized algorithms or capabilities. The goal is understanding incremental benefits relative to dependency costs.

### 4.3. Compare Alternatives

Compare:
- PostgreSQL built-in features.
- Custom SQL/PLpgSQL implementations.
- Community extensions.
- Commercially supported extensions.
- External services or application-layer processing.

Evaluate total cost of ownership (TCO), including licensing, infrastructure, on-call burden, upgrades, migrations, and exit costs.

## 5. Inventorying Existing Extensions

For each database/cluster, collect installed extensions and versions:

```sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS extension_schema
FROM pg_extension AS e
JOIN pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
```

List extension packages available on the current server:

```sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
```

Available versions and properties:

```sql
SELECT
    name,
    version,
    installed,
    superuser,
    trusted,
    relocatable,
    schema,
    requires,
    comment
FROM pg_available_extension_versions
ORDER BY name, version;
```

Schemas/columns can vary across PostgreSQL major versions; check catalogs for the exact version. Properties such as `trusted` can also vary by version.

### 5.1. Inventory by Cluster and Database

Extensions are created per database, whereas shared libraries and control files are installed per host. A single cluster may host multiple databases with different extension lists.

Inventory:
- Production primary.
- All standby/failover nodes.
- DR clusters.
- Staging and pre-production.
- Reporting/analytics clusters.
- Development/test clusters.
- Across regions and cloud environments.

### 5.2. Extensions Preloaded Without CREATE EXTENSION

A module may appear in `shared_preload_libraries` without an extension entry in a database. Conversely, an extension may be installed while its library loads lazily when a function is called. Inspect both catalogs and active runtime settings.

```sql
SHOW shared_preload_libraries;
SHOW session_preload_libraries;
SHOW local_preload_libraries;
```

### 5.3. Inspect Package Files

On the host, verify:
- Control files.
- SQL installation/update scripts.
- Shared library files.
- Runtime libraries.
- Package versions/builds.
- Package owner/repository.
- File permissions and checksums.

Use the package manager and `pg_config` belonging to the running instance. Never copy a shared library built for another major version into the library directory to test loading.

## 6. Evaluating Maintainer and Project Reliability

An extension with strong features but no accountable maintainer becomes a long-term liability.

### 6.1. Ownership and Governance

Investigate:
- Who is the primary maintainer?
- Are there multiple independent maintainers or just one individual?
- Is an organization or vendor backing it?
- How are changes reviewed and merged?
- Are governance and release authority clear?
- Who takes over if a maintainer steps down?
- Is there a production support channel?

A low bus factor raises dependency risk. A single-maintainer project may still fit small use cases if paired with a clear exit plan.

### 6.2. Release Cadence

Examine:
- Latest release date.
- Cadence between releases.
- Whether releases track each new PostgreSQL major version.
- How security fixes are released.
- Whether older release branches are maintained.
- Whether releases include changelogs and upgrade instructions.

Frequent releases alone do not prove quality, nor do slow releases automatically signal abandonment. Weigh cadence against change volume and support commitments.

### 6.3. Issue and Pull Request Health

Observe:
- Open issue count and age.
- Whether critical bugs are acknowledged.
- Whether security issues are handled privately.
- Whether pull requests receive thorough reviews.
- Whether release notes reflect key fixes.
- Whether maintainers respond to user reports.
- Whether bug fixes include regression tests.

Never use GitHub stars or download counts as the sole metric. They measure popularity, not correctness or production readiness.

### 6.4. Quality Signals

Positive signals include:
- Automated tests and a CI matrix.
- Testing across multiple PostgreSQL major versions.
- Static analysis and clean compiler warnings.
- Fuzz/property-based tests where relevant.
- Documented upgrade paths.
- Reproducible builds.
- A security policy and disclosure contact.
- Signed or checksummed release artifacts.
- Changelogs highlighting breaking changes.

### 6.5. Support Model

Identify whether support comes from:
- Best-effort community.
- Maintainer sponsorship.
- Commercial vendor.
- Internal fork/team.
- Managed database provider.

If an extension is a critical dependency, know response SLAs, fix timelines, support windows, and escalation paths. Opening a GitHub issue is not equivalent to an SLA.

## 7. Evaluating Licenses and Usage Rights

Licensing governs usage, modification, binary redistribution, container packaging, and offering hosted services.

Inspect:
- License file in the repository.
- Licenses of transitive dependencies.
- `NOTICE`/copyright obligations.
- Rules for distributing modified builds.
- SaaS/hosted service restrictions if any.
- Patent clauses or trademark terms.
- Commercial vendor terms.
- Internal open-source approval policies.

Never infer a license merely from a project name or README badge. Read the actual license text and involve legal/compliance teams when distribution obligations or special terms apply.

### 7.1. Source-Available Is Not Open Source

A public repository may use a source-available or custom license. Verify production usage rights and rights to maintain forks.

### 7.2. Forks Create Ongoing Obligations

Modifying an extension and maintaining a fork requires owning patch management, security fixes, upstream merges, build matrices, release artifacts, on-call support, and compatibility testing.

Never treat a fork's cost as a one-time code edit.

## 8. Evaluating Security and Trust Boundaries

Extensions can hold extensive privileges inside the database server.

### 8.1. Installation Privileges

Extension attributes can include:
- `superuser`: whether installation requires superuser.
- `trusted`: whether non-superusers with `CREATE` privilege may install the extension.
- `relocatable`: whether objects can be installed into another schema via extension mechanisms.
- `requires`: dependent extensions.

Inspect metadata via `pg_available_extension_versions` and extension documentation.

### 8.2. Trusted Is Not a Security Certification

`trusted = true` is an installation attribute declared by the extension author controlling install eligibility. It does not prove the code was audited, is free of CVEs, or fits every threat model.

### 8.3. Native Code and Backend Processes

C extensions execute inside the PostgreSQL process. Memory bugs or invalid pointer handling can crash backends. A severe bug in a library can disrupt multiple connections or the entire instance.

Evaluate:
- Source code review.
- Dependency scanning.
- Compiler/build flags.
- Memory-safety testing.
- Privilege boundaries.
- Input validation.
- Error handling.
- Crash and restart behavior.

### 8.4. SECURITY DEFINER and Privileges

Audit `SECURITY DEFINER` functions, owners, `search_path`, and `EXECUTE` grants. Functions running with owner privileges can introduce privilege escalation if object resolution is unsafe.

### 8.5. Dynamic Loading and Preloading

`shared_preload_libraries` loads libraries at server startup. A broken library or missing dependency can prevent PostgreSQL from starting. Test restarts and ensure a recovery procedure exists to remove the library from config on boot failure.

### 8.6. Secrets and External Connections

FDWs or extensions integrating remote systems may store credentials or open outbound connections. Check:
- Credential storage.
- Rotation.
- TLS verification.
- Network egress.
- Timeouts.
- Auditing.
- Secret exposure via logs or catalogs.
- Least privilege on remote systems.

### 8.7. Security Response

Define how CVEs/advisories are tracked, who triages impact, patch rollout timelines, and package rebuild workflows. Native extensions require patching and process restarts to load updated binaries.

## 9. Evaluating Quality and Correctness

Reliability is more than avoiding crashes. An extension must return accurate results, preserve invariants, and handle edge cases.

### 9.1. Correctness Contract

Verify:
- Function semantics.
- `NULL` behavior.
- Type coercion.
- Collation and locale assumptions.
- Transaction semantics.
- Concurrency behavior.
- Determinism.
- Error/exception behavior.
- Index consistency.
- Data format and versioning.

### 9.2. Test Edge Cases

Depending on the use case, test empty inputs, `NULL`s, Unicode, very large values, numeric boundaries, duplicates, concurrent updates, long transactions, crashes/restarts, disk full, network timeouts, and malformed/corrupted inputs.

### 9.3. Data Integrity and Index Correctness

If an extension provides an index access method or custom operator class, verify:
- Index results match sequential scans.
- Inserts/updates/deletes keep indexes consistent.
- Vacuum and reindex operate cleanly.
- Crash recovery leaves indexes uncorrupted.
- Operator semantics match index ordering.
- Backup/restore preserves index objects.

### 9.4. Deterministic Output

If an extension supports ranking, similarity, or analytics, determine whether outputs are deterministic. Version or algorithm changes can shift outputs; does the application require stable pagination or reproducible results?

### 9.5. Failure Modes

Document what happens when an extension function times out, a background worker crashes, a remote service disconnects, an extension library fails to load, an upgrade script fails mid-flight, an index build cancels, or the database restarts mid-operation.

Never accept a critical dependency without knowing how to detect and recover from its failures.

## 10. Evaluating Performance: What Costs Must Be Measured

Extension performance must be measured in the context of the overall system workload.

Metric groups:
- Query latency: p50, p95, p99, max.
- Throughput: requests/transactions/rows per second.
- CPU time and CPU utilization.
- Memory usage and allocations.
- Shared buffers / cache hit behavior.
- Disk I/O and IOPS.
- Temporary files / spills.
- WAL bytes and replication lag.
- Lock waits and contention.
- Index size, table bloat, and vacuum work.
- Background worker activity.
- Network traffic when calling external systems.

### 10.1. Measure a Baseline Before Installing

Capture metrics on the same dataset and workload without the extension or with its feature disabled. Never compare runs across clusters with differing hardware.

### 10.2. Separate Install Cost from Runtime Cost

An extension may add install/upgrade time, slow startup, spawn background workers, add per-transaction overhead, consume resources only when specific functions/indexes run, or create periodic maintenance load.

Measure each aspect separately.

### 10.3. Measure Existing Workloads Too

An extension accelerating one new query can slow down every other query via CPU, memory, lock, or I/O contention. Assess impact on critical existing workloads.

## 11. Designing Controlled Benchmarks

A sound benchmark reproduces a representative workload repeatably.

### 11.1. Define Test Cases

Include typical reads, typical writes, peak concurrency, bulk ingestion, updates/deletes, large scans, worst-case inputs, mixed workloads, background maintenance, and recovery/restarts as appropriate.

### 11.2. Hold Comparison Conditions Constant

Fix or record:
- PostgreSQL version.
- Extension version.
- Hardware/VM/container limits.
- Storage type.
- Dataset size and distribution.
- `shared_buffers`, `work_mem`, parallel settings.
- Connection counts and pooler settings.
- Cache state.
- Statistics state.
- Query parameters.
- Network topology.

### 11.3. Run Multiple Trials

Warm up caches, execute multiple iterations, and record distributions rather than averages alone. Avoid drawing conclusions from a single warm-cache run or anomalous background activity.

### 11.4. Avoid Tiny Datasets

Datasets fitting entirely in RAM can hide disk I/O and cache pressure. Use data volumes, skew, and cardinalities resembling production.

### 11.5. Separate Microbenchmarks from End-to-End Tests

Microbenchmarks illuminate individual functions/operators. End-to-end tests show whether the extension improves business paths once network, application, pooler, and database contention are included.

## 12. Measuring Query Performance in PostgreSQL

### 12.1. EXPLAIN

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT ...
FROM ...
WHERE ...;
```

`EXPLAIN ANALYZE` executes the query. Run it only on safe statements in test workloads or per approved production procedures.

Inspect actual times, estimated vs. actual rows, loops, shared/local/temp buffers, I/O timing if enabled, sort/hash spills, parallel workers, and function/operator execution paths.

### 12.2. pg_stat_statements

When installed and configured, `pg_stat_statements` tracks query workloads by normalized query identity.

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

View schemas and columns vary by extension version. The query above illustrates versions providing these fields; check the actual view definition.

### 12.3. Before/After Comparisons

Collect snapshots before and after enabling the extension. Compare delta counters and workload-normalized rates. Avoid comparing cumulative counters spanning mismatched durations.

### 12.4. Application-Layer p95/p99

PostgreSQL statistics views generally do not provide full per-business-request latency percentiles. Combine application tracing/metrics to measure tail latency and end-to-end impact.

### 12.5. Query Plans Shift with Statistics

Run `ANALYZE` appropriately and record data distributions and planner settings. If an extension adds an operator/index, confirm the planner actually uses it on target queries.

## 13. Evaluating Indexes and Write Amplification

Extensions adding indexes or access methods can speed up reads while making writes costlier.

Measure:
- Index size.
- Build duration.
- Insert/update/delete throughput.
- WAL bytes per row/transaction.
- Vacuum duration.
- Reindex duration.
- Cache footprint.
- Index bloat.
- Replication lag.
- Query plan stability.

### 13.1. Read Gains Trade Off Against Write Costs

If an extension index accelerates reads substantially yet every write incurs extra index maintenance, evaluate against the read/write ratio. A write-heavy system may not benefit.

### 13.2. Index Builds and Rebuilds

Determine whether the extension index supports concurrent builds, resumes after failures, requires heavy locks, and how `REINDEX` works during upgrades.

### 13.3. Operator Class Semantics

Custom operator classes must match operator and ordering semantics. If an extension changes algorithms or binary representations, older indexes may require rebuilding per release notes.

### 13.4. Vacuum and Maintenance

Verify whether the extension requires dedicated vacuum/analyze routines, retention cleanup, compaction, or background maintenance. Factor maintenance windows into operational capacity.

## 14. CPU, Memory, and Background Workers

An extension can impose resource overhead invisible in a simple query microbenchmark.

Inspect:
- Background worker count.
- Worker restart policy.
- Memory contexts.
- Shared memory requirements.
- `shared_preload_libraries`.
- Interaction with parallel workers.
- CPU saturation.
- Scheduler behavior.
- Long-lived memory allocations.
- Worker shutdown/restart behavior.

### 14.1. Shared Memory Requirements

Some extensions require raising shared memory or worker-count parameters. Check parameter context (`postmaster`/reload/user), restart requirements, and total memory budget.

### 14.2. Worker Capacity

PostgreSQL enforces worker/process limits. Extension workers can compete with parallel queries, logical replication, autovacuum, or other extensions' workers. Never evaluate worker counts in isolation.

### 14.3. Startup and Recovery

Preloaded extensions can lengthen startup, recovery, or failover times. Test restarts after enabling the extension and measure recovery duration.

## 15. WAL, Replication, and Durability Overhead

Extensions may write extra tables/indexes, alter write patterns, or run background updates.

Measure WAL bytes per business operation, checkpoint frequency/pressure, replica receive/replay lag, archive volume, slot retention, logical decoding behavior, and crash recovery duration.

### 15.1. Physical Standbys

Physical replication ships database changes via WAL, yet shared libraries and OS packages are not replicated. Install matching extension binaries on every standby prior to failover/promotion if nodes must load the extension.

### 15.2. Logical Replication

Logical replication does not automatically distribute extension packages, shared libraries, or all DDL. Provision corresponding extensions on subscribers, synchronize schemas via separate procedures, and check extension-specific data/objects.

### 15.3. Synchronous Replication

If an extension increases WAL generation or lengthens transactions, commit latency under synchronous replication can rise. Measure the write path on a production-like topology.

### 15.4. Replication Slots and WAL Retention

Extensions with background workers/consumers or logical decoding integration may create and hold replication slots. Monitor slot ownership, inactive slots, restart LSNs, and retained WAL.

## 16. Evaluating PostgreSQL Version Compatibility

An extension needs an explicit compatibility matrix.

Verify:
- Supported PostgreSQL major versions.
- Minor version constraints if any.
- Extension releases supporting the target major version.
- Usage of PostgreSQL internal APIs.
- Upgrade scripts from the installed version.
- Downgrade policy.
- Known incompatibilities.
- Support window.

### 16.1. Native Extensions and ABI

C extensions generally must be compiled for each PostgreSQL major version because PostgreSQL server internals and extension ABIs are not guaranteed compatible across major versions. Never assume a shared library compiled for PG16 loads safely on PG17.

### 16.2. Minor Updates

Binary compatibility within the same major version is generally expected, yet follow package/vendor support matrices and security advisories. Scrutinize extensions calling internal APIs or custom builds even more closely.

### 16.3. SQL-Only Extensions

SQL-only extensions have fewer ABI dependencies yet still depend on catalogs, function signatures, SQL syntax, planner behavior, and extension update scripts. Never assume portability merely because there is no shared library.

### 16.4. Compatibility Matrix

| Component | Source | Target | Evidence |
|---|---|---|---|
| PostgreSQL major | Running version | Planned version | Extension support matrix |
| Extension release | Installed version | Supported release | Changelog / update path |
| Native library | Source binary build | Target build | Package / build artifact |
| Dependencies | OS libraries | Target libraries | Package metadata / SBOM |
| Upgrade path | Current extension version | Target extension version | SQL update scripts |
| Managed service | Current platform | Target platform/version | Provider allowlist |

## 17. Operating System, Architecture, and Packaging

Portability also depends on the runtime environment.

Check Linux distribution/version, Windows/macOS if applicable, CPU architecture (`x86_64`, `ARM64`...), libc/toolchain, compiler version, OpenSSL/ICU and related libraries, kernel/syscalls, package manager, container base image, file paths and permissions, and runtime service account.

### 17.1. Package Source

Prefer packages from trusted sources with verifiable provenance and regular updates. Record repository/vendor, package name/version, build target, checksum/signature, dependencies, patch set, and support lifecycle.

### 17.2. Building from Source

If you must build from source:
- Pin source commit/tag.
- Pin compiler/toolchain.
- Use `pg_config` from the exact target PostgreSQL installation.
- Record build flags.
- Save build logs.
- Scan dependencies.
- Produce reproducible artifacts.
- Test install/upgrade/restart.
- Store SBOMs and checksums per policy.

Example PGXS build:

```bash
make USE_PGXS=1 PG_CONFIG=/usr/pgsql-17/bin/pg_config
make USE_PGXS=1 PG_CONFIG=/usr/pgsql-17/bin/pg_config install
```

These paths are examples. Point `pg_config` to the actual target installation and follow the extension's build instructions. Never build/install directly on production as an experiment.

### 17.3. Container Images

Bundling extensions into the PostgreSQL container image pins versions cleanly, provided you track:
- Maintained base images.
- Extension packages matching the major version.
- Security patches.
- Image digests.
- Multi-architecture builds.
- Startup and health checks.
- Reproducible deployments.
- Rollback images.

### 17.4. Every Failover Node Must Have Dependencies

If an extension is preloaded or used by the application after promotion, standby and DR nodes must carry identical binaries and dependencies. Verify package parity via automation rather than manual checklists alone.

## 18. Managed PostgreSQL and Cloud Portability

Not every managed PostgreSQL service permits installing every extension.

Providers may enforce an extension allowlist, restrict extension versions, require parameter groups/flags, block `shared_preload_libraries`, withhold true superuser access, cap background workers or shared memory, offer extensions only in specific regions/instance tiers, update extensions on provider schedules, or enforce custom major-upgrade rules.

### 18.1. Check the Allowlist Before Designing

Confirm the extension is available on your target:
- Engine major/minor version.
- Region.
- Instance class/tier.
- Deployment mode (single/HA/serverless).
- Read replicas.
- DR region.

An extension available in one region is not guaranteed to exist in another.

### 18.2. Privilege Limitations

Managed services rarely grant OS access or true database superuser. Extensions requiring filesystem access, preloading, or custom OS packages may be unsupported.

### 18.3. Provider-Managed Versions

Providers often dictate available extension versions. Confirm upgrade schedules, deprecation windows, and how to inspect active versions.

### 18.4. Multi-Cloud Strategy

If portability across cloud providers is required, select only extensions supported across all targets—or design an abstraction/fallback. Otherwise, explicitly document the extension as a provider-specific dependency and assess exit cost.

## 19. Backup, Restore, and Disaster Recovery

An extension can store state across multiple places:
- PostgreSQL tables/indexes/catalogs.
- Shared libraries on the host.
- Configuration files.
- External services.
- Filesystem paths.
- Remote object stores.
- Credentials/secrets.
- Background worker checkpoints.

A database backup does not automatically capture all of these.

### 19.1. pg_dump/pg_restore

Logical dumps typically preserve `CREATE EXTENSION` and dependent objects per extension rules, yet omit shared libraries and control files. The restore host must have compatible packages installed before restoring the extension.

Extensions with configuration tables or non-catalog state require checking dedicated backup mechanisms. Never assume `pg_dump` captures external state.

### 19.2. Physical Backups

Physical backups capture data files and WAL per backup tooling, yet never replace managing OS packages, shared libraries, and configs needed for server startup and extension loading.

### 19.3. Restore Drills

Rehearse restoring onto a fresh host:
1. Install target PostgreSQL.
2. Install required extension packages/versions.
3. Restore the database.
4. Verify `CREATE EXTENSION` and library loading.
5. Run extension-specific validation.
6. Check indexes, types, and functions.
7. Verify external credentials and services.
8. Run application smoke tests.

### 19.4. RPO/RTO

Measure the time to restore extension state, rebuild indexes, catch up background workers, and recover remote dependencies. Update RTO plans if the extension increases restore duration.

### 19.5. External State

FDWs, search engines, object stores, or external schedulers may hold state outside PostgreSQL. A database backup does not guarantee a consistent cross-system snapshot. Design separate snapshot and reconciliation procedures.

## 20. Extension Upgrade and Migration Paths

PostgreSQL major upgrades and extension upgrades are related yet distinct steps.

### 20.1. Inspect Extension Update Paths

List update paths installed on the server:

```sql
SELECT *
FROM pg_extension_update_paths('extension_name');
```

Function results depend on version and packaging. A path present on a source host does not guarantee the target package includes those scripts.

### 20.2. Inspect Extension Metadata

```sql
SELECT
    e.extname,
    e.extversion,
    e.extrelocatable,
    e.extnamespace::regnamespace AS extension_schema
FROM pg_extension AS e
ORDER BY e.extname;
```

### 20.3. ALTER EXTENSION UPDATE

Once the update path and target package are confirmed, update the extension:

```sql
ALTER EXTENSION extension_name UPDATE TO '2.0';
```

Replace `extension_name` and version with real values. Read the extension's release notes for ordering, preconditions, locks, and data migrations.

### 20.4. pg_upgrade Does Not Replace Extension Packages

`pg_upgrade` migrates the database cluster per PostgreSQL procedures. Native extension binaries, control files, and SQL scripts must be provisioned properly on target hosts. Extension SQL updates may be a separate step after cluster upgrade per documentation.

### 20.5. Never Assume Downgrades Are Supported

Extensions can have one-way upgrade paths. If a target extension version alters data formats or catalog objects, rollback may require restoring a backup. Verify downgrade policy beforehand.

### 20.6. Upgrade Rehearsals

Test upgrading from the exact installed extension version to the target on a restored clone. Verify pre-upgrade checks, package installation, `pg_upgrade` or dump/restore, `ALTER EXTENSION UPDATE`, reindexing if needed, application behavior, restarts/failovers, backup/restore, and rollback/recovery.

## 21. Dependency Graph and Blast Radius

An extension rarely stands alone. It can depend on:
- Another extension.
- Shared libraries.
- Procedural languages.
- PostgreSQL internal APIs.
- OS packages.
- Remote services.
- Credentials.
- Background workers.
- Custom operators/types/indexes.
- Monitoring tools.

### 21.1. Document the Dependency Graph

For each dependency, record version range, owner, source, update cadence, and failure mode. Flag critical dependencies and single points of failure.

### 21.2. Extension Dependencies in Catalogs

`pg_available_extension_versions.requires` lists extension dependencies declared in installation metadata. Catalog dependencies do not capture OS libraries, network services, or operational dependencies.

### 21.3. Blast Radius

Evaluate the impact if the extension crashes a backend, breaks startup, saturates CPU, holds locks, triggers WAL bursts, returns wrong index results, lacks target compatibility, or fails to install on DR nodes.

### 21.4. Isolation

If an extension is untrusted or carries too large a failure blast radius, consider executing that logic in an application or external service rather than loading native code into the database. Weigh that against the latency, network, and consistency costs of an external service.

## 22. Designing a Proof of Concept (PoC)

A PoC must validate key hypotheses rather than merely proving `CREATE EXTENSION` runs.

### 22.1. Scope

Document use case, extension/version, PostgreSQL version, environment, dataset, workload, baseline, metrics, acceptance thresholds, failure scenarios, and test owner.

### 22.2. PoC Environment

Use an isolated environment with policy-compliant representative data, production-like settings, and identical packaging/OS. Never test unreviewed native extensions directly on production.

### 22.3. Test Cases

- Install/uninstall.
- Restart.
- Extension upgrade.
- Application integration.
- Concurrent workload.
- Peak load.
- Backup/restore.
- Physical failover.
- Logical replication if used.
- Managed-service restrictions.
- Failure injection.
- Resource exhaustion.
- Security and privilege tests.

### 22.4. PoC Exit Criteria

Every test must have clear pass/fail criteria. Never accept subjective criteria like "looks fast" or "saw no errors."

### 22.5. Never Use Production Data Carelessly

Mask or anonymize data per policy. If statistical distribution matters, preserve distribution properties without exposing sensitive data.

## 23. Benchmark Matrix

A practical benchmark matrix:

| Scenario | Workload | Metrics | Goal |
|---|---|---|---|
| Baseline | Extension disabled | Latency, throughput, CPU, I/O | Reference point |
| Typical | Normal traffic | p50/p95/p99, error rate | Real-world performance |
| Peak | High concurrency | Queueing, CPU, locks | Capacity |
| Write-heavy | Inserts/updates | WAL, IOPS, replication lag | Write amplification |
| Read-heavy | Searches/scans | Buffers, CPU, p95 | Query benefit |
| Mixed | Concurrent reads/writes | Throughput, tail latency | Production realism |
| Restart | Restart/failover | Recovery time, worker state | Reliability |
| Restore | Restore from backup | RTO, missing dependencies | Portability/recovery |
| Upgrade | Version transition | Duration, errors, reindex | Lifecycle |
| Failure | Remote/service/library fault | Detection, blast radius, recovery | Resilience |

### 23.1. Measure Across Concurrency Levels

An extension may perform well at concurrency 1 yet lose throughput at high concurrency due to lock or shared resource contention.

### 23.2. Monitor the Entire System

Capture PostgreSQL metrics, OS/container metrics, application tracing, and external service metrics along a synchronized timeline.

### 23.3. Record Benchmark Configuration

Save exact SQL, parameters, dataset generators, random seeds if used, PostgreSQL settings, extension versions, and hardware specs. Non-reproducible results make poor decision evidence.

## 24. Reliability Testing and Failure Injection

Perform controlled failure testing to observe recovery behavior.

### 24.1. Restarts and Crashes

Verify whether the extension reloads after restart, background workers resume, persistent state stays consistent, and startup depends on external services.

Never deliberately kill production backends or servers for testing.

### 24.2. Remote Dependency Failures

For FDWs/integrations, simulate DNS failure, connection refused, timeouts, invalid TLS certificates, expired credentials, overloaded remote services, and partial responses.

Verify timeouts, retries, circuit breakers, and transaction behavior.

### 24.3. Disk/Memory Pressure

Evaluate behavior when temporary storage, memory, or filesystems approach capacity. Extensions may create spill files or internal caches.

### 24.4. Worker Crashes

Inspect restart loops, log noise, duplicate processing, checkpoint recovery, and how operators can disable workers.

### 24.5. Corrupted Inputs

Test malformed data and oversized payloads. Extensions must surface handleable errors rather than crashing or corrupting state.

### 24.6. Failure Recovery Criteria

Record detection time, alerts, user impact, recovery steps, data loss/duplication, manual interventions, and time to restore normal service.

## 25. Observability and Operations

Before adopting, confirm operations teams can observe extension health.

Visibility should cover active extension versions, worker status, queues/backlogs, error/retry counts, resource consumption, index/maintenance state, external dependency health, and upgrade status.

### 25.1. Logging

Logs should include extension name/version, operation, error category, and correlation identifiers where appropriate. Never log raw secrets or sensitive payloads.

### 25.2. Metrics

Prioritize SLO-meaningful metrics:
- Operation count/rate.
- Success/error rate.
- Queue depth.
- Processing lag.
- Latency distributions.
- Cache hit/miss.
- Worker restarts.
- External request latency.
- Resource usage.

### 25.3. Health Checks

Health checks must verify actual processing capability. A loaded extension library does not prove a remote service or background worker is healthy.

### 25.4. Runbooks

Write runbooks for install/update, restart/reload, stuck workers, queue backlogs, invalid/corrupt indexes, expired remote credentials, upgrade failures, disable/rollback, and failover/restore.

### 25.5. On-Call Readiness

Designate an owner and on-call responders capable of diagnosing the extension. If only one developer knows how to fix it, log that as an operational risk.

## 26. Managed Service vs. Self-Managed Deployment: Comparison

| Criterion | Self-managed | Managed PostgreSQL |
|---|---|---|
| OS package install | Full control | Depends on provider |
| Shared libraries | Can build/install custom ones | Typically allowlisted |
| Superuser | Host-managed admin privileges | Usually restricted |
| Preload settings | Self-configured | Via parameter groups/allowlist |
| Version cadence | Self-determined | Controlled by provider |
| OS portability | Managed by ops team | Abstracted away |
| Failover nodes | Sync packages manually/via automation | Provider manages nodes, still verify support |
| Extension updates | Self-managed | May be provider-managed/restricted |

### 26.1. Managed Services Do Not Eliminate Extension Risk

Providers may manage binaries, yet your organization remains responsible for query behavior, data correctness, schema dependencies, backup policies, and exit costs.

### 26.2. Portability Between Self-Managed and Managed

If you plan to switch deployment models, test extensions on both environments early. Never wait until migration day to discover the target lacks support.

## 27. Exit Strategy: Can You Leave the Extension Behind?

Every sound dependency needs a viable exit path.

### 27.1. Data Export

Verify how to export tables/data, custom types, index definitions, extension-owned metadata, external state, configs, and credentials.

### 27.2. Replacement Path

When replacing an extension with built-in features or another service:
- Map data types.
- Map operators/functions.
- Rebuild indexes.
- Recompute derived data.
- Refactor application queries.
- Validate output equivalence.
- Plan dual-run and cutover.

### 27.3. Extension-Specific Storage Formats

Some extensions store data in custom binary formats or specialized index structures. Verify whether formats can dump/restore or require rebuilding. Never assume database dumps are portable across all extension versions.

### 27.4. Exit Cost

Estimate engineering effort, migration duration, downtime, data conversion, reindexing/recomputing, performance impact, temporary infrastructure, rollback complexity, and contract/vendor costs.

### 27.5. Avoid Unnecessary Coupling

Keep extension-specific SQL behind repository or service boundaries where sensible. Avoid leaking extension-specific types and operators into public APIs, event schemas, and every application module unnecessarily.

## 28. Example: Evaluating a Vector Search Extension

Suppose an application plans to add vector similarity search inside PostgreSQL.

### 28.1. Reliability Questions

- Which PostgreSQL major versions does the extension support?
- Who maintains and publishes binaries?
- How does the index behave under concurrent inserts/updates/deletes?
- Does crash/restart preserve index consistency?
- Are reindex and upgrade procedures documented?
- Do packages exist for every architecture and DR region?
- Does the managed provider allow it?

### 28.2. Performance Questions

- What is query p95 on a realistic dataset?
- How long does index building take?
- How do recall and accuracy vary with index parameters?
- How much does insert throughput drop?
- What are index size and memory footprint?
- What happens to WAL volume and replica lag?
- Does the query planner use the index across filter combinations?

### 28.3. Portability Questions

- Can we migrate between self-managed and managed?
- Must indexes be rebuilt when upgrading extension versions?
- Can vectors be exported and indexes rebuilt cleanly?
- Does logical migration transfer all data and schemas?
- Does the target architecture have matching binaries?

### 28.4. Acceptance Criteria

Examples:
- Recall meets product acceptance thresholds.
- p95 latency satisfies SLOs at target concurrency.
- Write throughput regression stays within budget.
- Backup/restore and failover tests pass.
- Extension has support path for the next two major versions.
- A documented procedure exists to rebuild indexes from source data.

Thresholds must match product requirements; these are not universal defaults for vector extensions.

## 29. Example: Evaluating an External-System FDW

A foreign data wrapper lets PostgreSQL query remote data as foreign tables.

Evaluate remote server availability and latency, remote schema, authentication, network egress/ingress, timeouts, retries, transaction semantics, snapshot consistency, query fan-out, connection pooling, data residency, and backup/recovery of the remote source.

### 29.1. Pushdown

Check whether filters, joins, and aggregates push down to the remote source or execute locally. An innocent-looking query can pull an entire remote table into PostgreSQL.

### 29.2. Transaction Consistency

Never assume local and remote transactions share single-database atomicity. Check FDW capabilities and remote transaction semantics.

### 29.3. Remote Outages

Define whether local queries fail, time out, or serve cached/stale data. Set sensible timeouts so remote outages do not tie up connections and backends indefinitely.

## 30. Example: Evaluating an Observability Extension

Monitoring extensions expose views/functions, yet require assessing overhead and permissions.

Evaluate sampling frequency, shared memory requirements, data retention, query cost, cardinality and label explosion, permissions, exposure of query text/PII, exporter compatibility, restart requirements, and stats reset semantics.

A query-tracking extension can increase shared memory usage or retain sensitive query text. Configure retention, masking, and role permissions per policy.

## 31. Evaluation and Adoption Workflow

A practical workflow:

1. **Define use case:** document requirements, SLOs, data shapes, and alternatives.
2. **Identify candidates:** record name, source, license, current release, and owner.
3. **Inspect project health:** maintainers, release cadence, issues, tests, and support.
4. **Review security:** code kind, privileges, trust, CVEs, build provenance, and external access.
5. **Check compatibility:** PostgreSQL versions, OS, architecture, packages, and managed services.
6. **Review lifecycle:** install, upgrade, backup, restore, failover, and rollback.
7. **Run PoC:** representative workload, failure tests, and benchmarks.
8. **Calculate TCO:** engineering, infrastructure, support, operations, and exit costs.
9. **Record decision:** adopt, pilot, defer, or reject with evidence and owner.
10. **Set review date:** re-evaluate whenever PostgreSQL major version, extension version, provider, or workload changes.

## 32. Decision Matrix

Score each criterion on a 1–5 scale, backed by concrete evidence.

| Criterion | Question | Evidence |
|---|---|---|
| Maintainer health | Are active maintainers responsive? | Maintainers, release history, issue responses |
| Security | Are policies, advisories, and patching solid? | Security policy, CVE review, code/build scans |
| Correctness | Do edge cases behave accurately? | Test suite, PoC, data validation |
| Performance | Does it meet SLOs without hurting existing workloads? | Benchmarks, p95/p99, resource metrics |
| Version support | Are target PostgreSQL versions supported? | Compatibility matrix |
| Platform | Do packages exist for OS/architecture/provider? | Build artifacts, provider allowlist |
| Recovery | Do backup/restore and failover work? | Restore/failover rehearsals |
| Operations | Are metrics, logs, runbooks, and owners ready? | Dashboards, runbooks, on-call plan |
| License | Are usage and distribution rights compliant? | License/legal review |
| Exit | Can data be exported and the extension replaced? | Migration plan, rebuild tests |

### 32.1. Never Let Total Scores Hide a Blocker

An extension scoring 5/5 on performance but lacking a binary for the target major version is still blocked. Define hard gates before totaling scores.

### 32.2. Decision Outcomes

- **Adopt:** passes all hard gates, SLOs, and operational criteria; has an assigned owner.
- **Pilot:** promising but lacks complete evidence; restrict blast radius.
- **Defer:** dependencies are unready or target platforms lack support yet.
- **Reject:** risk/cost outweighs benefits or violates mandatory requirements.

## 33. Extension Compatibility Register

Maintain a record for each dependency:

| Field | Contents |
|---|---|
| Extension | Name and purpose |
| Source | Repository/vendor/package |
| Installed/target version | Current and planned versions |
| PostgreSQL range | Supported major versions |
| Platform | OS/architecture/provider |
| Extension type | SQL-only, native, worker, FDW... |
| Dependencies | Extensions, OS libraries, external services |
| License | License and legal approval |
| Maintainer/support | Owner, SLA/support model |
| Security | Advisories, CVEs, trust, privileges |
| Performance | Benchmark baselines and results |
| Recovery | Backup/restore/failover evidence |
| Upgrade path | Extension updates and PG major upgrades |
| Exit path | Replacement/export/rebuild |
| Risk/owner | Severity, mitigation, responsible team |
| Decision | Adopt/Pilot/Defer/Reject |

Each record must capture review date and referenced documentation version. Re-validate whenever PostgreSQL or extension versions change.

## 34. Production Rollout and Change Management

Even after a successful PoC, roll out in controlled stages.

### 34.1. Pre-Production

- Pin extension version.
- Install packages across all nodes.
- Configure preloads and settings.
- Verify privileges.
- Run restore tests.
- Verify monitoring.
- Review runbooks.
- Stage rollback artifacts.

### 34.2. Canary

Enable the extension or feature on a single cluster, database, tenant, or small slice of traffic if architecture permits. Compare metrics against baselines and validate correctness.

### 34.3. Gradual Rollout

Increase traffic/usage incrementally. Watch latency, errors, resource utilization, WAL, replica lag, and external dependencies.

### 34.4. Full Adoption

Promote cluster-wide only after canary and acceptance tests pass. Record exact package/image digests and configurations.

### 34.5. Post-Deploy Review

After an observation window:
- Compare production metrics against benchmarks.
- Review incidents and errors.
- Confirm backup/restore readiness.
- Update the dependency inventory.
- Confirm owners and on-call readiness.
- Update the exit plan and next review date.

## 35. Runbook: Extension Fails to Load After Restart

1. Inspect PostgreSQL startup logs.
2. Verify `shared_preload_libraries` and load order.
3. Confirm the shared library exists in the expected library directory.
4. Check binary ABI and major version alignment.
5. Check OS shared-library dependencies.
6. Check file permissions and service account.
7. If the server fails to start, follow recovery procedures to remove the extension from preload configuration.
8. Install a compatible package/build on the host.
9. Restart staging and verify worker/function loading.
10. Execute production remediation under an approved rollback plan.

Never delete an active binary or modify library paths randomly in production.

## 36. Runbook: Extension Upgrade Failure

1. Halt the rollout and preserve logs.
2. Identify PostgreSQL version and before/after extension versions.
3. Inspect package, control file, and SQL update scripts.
4. Determine whether the migration committed partially or rolled back cleanly.
5. Inspect extension catalogs and dependent objects.
6. Consult vendor upgrade instructions.
7. Restore a staging clone and reproduce the failure.
8. Choose forward-fix or restore per the recovery plan.
9. Verify fresh backups before resuming production changes.
10. Run validation functions/queries and application tests.

Never manually edit `pg_extension` catalogs to force version metadata to match binaries.

## 37. Runbook: Performance Regression

1. Identify affected workload/query fingerprints.
2. Compare current metrics against baseline.
3. Run `EXPLAIN`/`BUFFERS` on representative queries.
4. Verify the planner uses extension indexes/operators properly.
5. Inspect CPU, memory, I/O, locks, WAL, and background workers.
6. Check data distributions and statistics.
7. Dial back or disable feature flags if possible.
8. Throttle or pause new workloads if SLOs breach.
9. Revert configuration or extension usage per the rollback plan.
10. Record post-remediation benchmarks.

Never drop an extension immediately while database objects or indexes depend on it.

## 38. Runbook: Preparing to Exit an Extension

1. Inventory all dependent objects, types, functions, operators, and indexes.
2. Identify data and external state needing export.
3. Choose replacement features and semantic mappings.
4. Create new schemas using an expand/contract pattern.
5. Backfill or rebuild indexes and derived data.
6. Dual-read and compare outputs where appropriate.
7. Shift traffic via canary rollout.
8. Confirm zero remaining extension-specific calls.
9. Back up and verify rollback readiness.
10. Drop dependent objects in order, then run `DROP EXTENSION` once dependencies are gone.
11. Remove preload settings and packages after all databases/clusters stop using the extension.
12. Update dependency inventories and security/packaging automation.

`DROP EXTENSION ... CASCADE` can delete numerous dependent objects. Always inspect the dependency graph and rely on `RESTRICT`/default behavior to surface dependencies before dropping.

## 39. Reliability Checklist

- [ ] Maintainers and ownership identified.
- [ ] Release cadence and support window acceptable.
- [ ] Issue and security response processes verified.
- [ ] Test suite and compatibility matrix exist.
- [ ] License reviewed.
- [ ] Native code, procedural language, and trust boundaries assessed.
- [ ] Privileges and `SECURITY DEFINER` functions audited.
- [ ] Failure modes and recovery behaviors tested.
- [ ] Backup/restore and failover evidence collected.
- [ ] On-call owners and runbooks ready.

## 40. Performance Checklist

- [ ] Baseline workload recorded.
- [ ] Dataset and concurrency representative of production.
- [ ] p50/p95/p99 latencies measured.
- [ ] Throughput and error rates measured.
- [ ] CPU/memory/I/O monitored.
- [ ] WAL and replica lag measured.
- [ ] Index build and write amplification evaluated.
- [ ] Vacuum/reindex/maintenance costs measured.
- [ ] Background worker overhead measured.
- [ ] Existing workloads stay within regression budget.

## 41. Portability and Lifecycle Checklist

- [ ] PostgreSQL major/minor support verified.
- [ ] Native binaries built for exact major version/architecture.
- [ ] OS/runtime dependencies packaged.
- [ ] Managed-service allowlist verified.
- [ ] All standby/DR nodes have compatible packages.
- [ ] Logical replication/migration behavior verified.
- [ ] Backup/restore hosts have required extension files.
- [ ] Restore and failover rehearsals passed.
- [ ] Extension update paths documented.
- [ ] `pg_upgrade`/dump-restore paths tested.
- [ ] Exit strategy and data export proven.
- [ ] Version pinning and package provenance recorded.

## 42. Common Misconceptions

### 42.1. “A popular extension must be safe”

Popularity does not substitute for security reviews, support matrices, workload benchmarks, or restore rehearsals.

### 42.2. “CREATE EXTENSION succeeded, so the dependency is ready”

Successful installation proves only that the server found control/SQL files and ran the script. It does not prove performance, HA, backups, portability, or correctness.

### 42.3. “SQL-only extensions carry no risk”

SQL can trigger costly queries, locks, recursive execution, or privilege changes. SQL objects still require correctness and performance testing.

### 42.4. “One binary works across every PostgreSQL major version”

Native extensions typically must be built and packaged per major version. Never copy binaries across major versions.

### 42.5. “Physical standbys already have the extension because WAL replicates”

WAL replicates database changes and catalog metadata, not shared libraries or OS packages. Every failover host requires matching binaries and dependencies.

### 42.6. “pg_dump backs up the extension completely”

Dumps include `CREATE EXTENSION` and eligible database objects/data, yet omit native binaries, control files, and external state.

### 42.7. “A fast query benchmark is enough”

You must measure mixed workloads, writes, tail latencies, WAL, replicas, memory, maintenance, and failure scenarios.

### 42.8. “We can always drop the extension to roll back”

Dependent objects and indexes may break, and extension-specific data may need export/rebuild. Dropping is not a safe default rollback.

### 42.9. “Trusted means security-audited”

`trusted` is metadata governing installation privileges, not a security certification.

### 42.10. “Managed services handle all compatibility automatically”

Providers manage hosts, yet do not guarantee application semantics, specific extension versions, restore workflows, or portability to another provider.

## 43. Official Reference Documentation

- [PostgreSQL — Packaging Related Objects into an Extension](https://www.postgresql.org/docs/current/extend-extensions.html): extension structure, control files, scripts, and versioning.
- [PostgreSQL — CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html): installing extensions and their properties.
- [PostgreSQL — ALTER EXTENSION](https://www.postgresql.org/docs/current/sql-alterextension.html): updating extensions.
- [PostgreSQL — DROP EXTENSION](https://www.postgresql.org/docs/current/sql-dropextension.html): removing extensions and dependent objects.
- [PostgreSQL — Extension Building Infrastructure](https://www.postgresql.org/docs/current/extend-pgxs.html): PGXS and building extensions.
- [PostgreSQL — C Language Functions](https://www.postgresql.org/docs/current/xfunc-c.html): native C functions and runtime considerations.
- [PostgreSQL — System Catalogs](https://www.postgresql.org/docs/current/catalogs.html): `pg_extension` and related metadata.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): workload and system statistics.
- [PostgreSQL — pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html): logical backups.
- [PostgreSQL — pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html): major version upgrades.
- [PostgreSQL — Foreign Data Wrappers](https://www.postgresql.org/docs/current/ddl-foreign-data.html): foreign tables and external data access.

The `/current/` links track current PostgreSQL documentation. Before deciding, read documentation matching your exact PostgreSQL major version, extension release, and managed-service provider. Extension/vendor compatibility matrices are essential references, yet must still be verified via a PoC.

## 44. Summary

A PostgreSQL extension can solve challenging problems, yet adds dependencies across the database engine, deployment pipeline, backups, HA, and upgrade workflows. Adoption decisions must rest on evidence across reliability, performance, and portability.

1. **Reliability:** verify maintainers, release cadence, support, licensing, security, correctness, and failure modes.
2. **Performance:** measure baselines and representative workloads; evaluate latency, throughput, CPU, memory, I/O, WAL, replication, indexes, and maintenance overhead.
3. **Portability:** confirm PostgreSQL versions, ABI, OS/architecture, packaging, managed-service support, standby parity, and upgrade paths.
4. **Recovery:** prove backup/restore, failover, external state handling, and RTO/RPO.
5. **Operations:** ensure metrics, logs, runbooks, owners, and security patching processes exist.
6. **Exit:** know how to export/rebuild data, replace APIs/indexes, and remove the dependency.
7. **Decision:** adopt only when hard gates pass, benchmarks align, and residual risks have assigned owners and mitigations.

Before depending on an extension, prove that your system can install, run, observe, recover, upgrade, and exit from it through repeatable procedures.
