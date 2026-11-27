# Database Compatibility Assessment and Schema Conversion

Migrating a database to AWS or switching between two database management systems (DBMS) changes data, SQL, application behavior, and operations. A schema can convert syntactically yet still break the application due to differences in data types, collations, transactions, sequences, stored procedures, privileges, or timestamp handling. Therefore, the project team must assess compatibility before choosing a target and before scheduling cutover.

This lesson explains how to inventory a source database, assess compatibility with the target database, use schema conversion tools within an AWS migration workflow, remediate objects that cannot convert automatically, and validate the schema after deployment. The content is framed within AWS infrastructure—Regions/AZs, VPCs, IAM, RDS, Aurora, hybrid connectivity, and data migration services—to help you select the right target, reduce conversion risk, and preserve data integrity, security, and observability.

## 1. Learning Objectives

After completing this lesson, you will be able to:

- Build a source database and schema inventory covering engine version, extensions, objects, capacity, workloads, and application dependencies.
- Distinguish compatibility across engine, schema, data, SQL, application, performance, security, and operations layers.
- Identify key differences among Oracle, SQL Server, PostgreSQL, MySQL, and Amazon Aurora.
- Interpret assessment reports and classify objects as automatically convertible, requiring modification, or unsupported.
- Use AWS Schema Conversion Tool (AWS SCT) or AWS DMS Schema Conversion appropriately for supported source/target pairs.
- Understand the boundary between schema conversion and data movement via AWS Database Migration Service (AWS DMS).
- Design a workflow for conversion, manual remediation, deployment, and target schema testing.
- Validate data, constraints, indexes, stored code, privileges, and application behavior before cutover.
- Plan rollback, hybrid connectivity security, and post-migration monitoring.

## 2. Why Assess Compatibility Before Converting

A schema defines a database's structure and rules: tables, columns, data types, keys, constraints, indexes, views, sequences, functions, procedures, triggers, privileges, and other objects. Every DBMS has its own SQL dialect, data types, storage engine, and features. Identical SQL syntax can carry different meanings across engines.

Examples:
- Oracle treats empty strings as `NULL` in many contexts; PostgreSQL and MySQL distinguish empty strings from `NULL`.
- SQL Server uses `uniqueidentifier`; PostgreSQL uses `uuid`; generation and serialization formats must be supported by the application.
- Oracle uses packages and PL/SQL; PostgreSQL lacks packages in the same model, and its procedures/functions differ in syntax and behavior.
- SQL Server uses `IDENTITY`; PostgreSQL typically uses identity columns or sequences; MySQL uses `AUTO_INCREMENT`.
- Date/time types, collations, string comparisons, time zone handling, and numeric rounding can behave differently.
- An index or partitioning strategy optimal on source may perform poorly under the target's optimizer and storage engine.

A tool can translate DDL, but it cannot infer business rules. For instance, if the source uses `NUMBER(1)` for status flags, a tool cannot reliably decide whether the target column should be a boolean, integer, or enum without business context.

Early assessment helps the project team:
1. Choose a target engine aligned with workload needs and operational skills.
2. Estimate effort for converting code and database objects.
3. Identify source features with no direct target equivalent.
4. Budget for refactoring, testing, and downtime windows.
5. Avoid committing cutover dates based solely on automated conversion percentages.
6. Define target security, licensing, HA, backup, and DR requirements.

**Schema conversion does not mean database migration is complete.** Schema conversion builds or adapts target structures and database code. Data migration moves the data. Application migration updates drivers, SQL, configurations, secrets, connection pools, and error handling. All three must be validated together.

## 3. Compatibility Layers to Assess

A thorough assessment splits compatibility into distinct layers so a "schema converted successfully" report never hides application or operational gaps.

| Layer | What to Examine | Example Risks |
|---|---|---|
| Engine/platform | Engine, version, edition, extensions, licensing, target service limits | Source version outside supported upgrade path or unsupported by target |
| Schema/object | Tables, columns, constraints, indexes, views, sequences, routines, triggers | PL/SQL packages have no direct conversion |
| Data type/value | Precision, scale, range, encoding, `NULL`, time zones, LOBs | Timestamps shift time zones or decimals lose precision |
| SQL semantics | Syntax, functions, transactions, locking, isolation | Query runs on source and target but returns different rows |
| Application | Drivers, ORMs, stored code calls, generated keys, error handling | Newer JDBC driver returns a different Java type |
| Performance | Query plans, indexes, partitions, statistics, concurrency | Queries slow down because optimizer picks a different plan |
| Security | Users, roles, privileges, encryption, authentication | Source user held broad privileges while target role lacks required grants |
| Operations | Backups, restores, HA, monitoring, maintenance, DR | Failover behavior and endpoints differ from application assumptions |
| Migration path | Downtime, CDC, replication, networking, cutover, rollback | DDL changes during active CDC cause schema drift or task failure |

Never collapse everything into a single score. Record evidence, impact severity, remediation approach, and owner for every difference.

## 4. Collecting Source Database Inventory

Start with verifiable facts. Do not merely ask "how many GB is the database?"; capture structure, load, dependencies, and actual behavior.

### 4.1 Engine and Environment Details

Record:
- DBMS, major/minor version.
- Edition, license model, patch level, and key parameters.
- Operating system, filesystem, storage, and current topology.
- Character set, national character set, collation, and database time zone.
- Extensions, plugins, add-on packages, and native libraries.
- Number of databases, schemas, owners, users, roles, and privileges.
- HA, replication, backup, retention, and DR configuration.
- Storage growth rate, write rate, connection counts, and peak workloads.
- Jobs, schedulers, ETLs, batches, CDC consumers, and BI tools connecting to the database.

Source version matters when evaluating source/target pairs. Two systems sharing the same engine name across different major versions can differ in syntax, system catalogs, data types, and features.

### 4.2 Object Inventory

Count objects by schema and object type:

| Object | Details to Record | Assessment Points |
|---|---|---|
| Table | Table count, columns, partitions, row estimates, size | Data types, defaults, identity, generated columns |
| Primary/foreign keys | Count, columns, state, cascade rules | Creation feasibility and validation timing |
| Check/unique constraints | Expressions, enabled/validated status | Syntax and semantic differences |
| Index | Type, columns, expressions, partial/filtered, included columns | Whether equivalent index types exist on target |
| View | SQL, dependencies, permissions | Functions/dialect and creation order |
| Materialized view | Query, refresh mode, schedule | Target refresh mechanisms |
| Sequence | Start, increment, cache, cycle | ID generation and post-load synchronization |
| Procedure/function | Language, dependencies, exceptions, dynamic SQL | Code rewrite effort |
| Trigger | Event, timing, row vs. statement level | Execution order and side effects |
| Synonym/package | Scope, dependencies, contents | Potential architectural refactoring |
| Partition | Key, strategy, retention, subpartitions | Implementation and partition pruning |
| User/role/grant | Owner, privileges, role inheritance | Target privilege model |
| Job/scheduler | Schedule, time zone, retries, credentials | Mapping to target schedulers/workflows |

Beyond objects, note special data such as XML, JSON, spatial, binary, LOBs, encrypted columns, user-defined types, and uncommon encodings.

### 4.3 Workload and Application Inventory

Identify who uses the database and how:

- Java, .NET, Python, Node.js, or packaged applications.
- JDBC/ODBC drivers and versions.
- ORMs, migration frameworks, query builders, and SQL dialects.
- Stored procedures invoked by applications.
- Dynamic SQL generated by reports, BI tools, or stored code.
- Batch jobs, cron jobs, ETL pipelines, replication, and data warehouses.
- Connections arriving from on-premises, VPCs, other accounts, or SaaS.
- Authentication mechanisms, secret rotation, and certificates.
- Latency, throughput, RPO, RTO, and maintenance window requirements.

A practical inventory table might look like:

| Attribute | Example |
|---|---|
| Database | `orders_prod` |
| Source engine | Oracle 19c |
| Target candidate | Amazon Aurora PostgreSQL-Compatible |
| Schemas | `ORDER_APP`, `BILLING` |
| Data size | 3 TB |
| Peak connections | 1,200 |
| Peak write rate | 8,000 transactions/minute |
| Critical objects | 25 packages, 80 triggers |
| Downtime objective | Under 15 minutes |
| RPO/RTO | 1 minute / 30 minutes |
| Application owner | Commerce Platform |
| Evidence | Inventory export, query logs, AWR/monitoring, source code |

Numbers in this example illustrate inventory structure only, not sizing recommendations.

## 5. Choosing a Target Database and Verifying the Engine Pair

Targets can be Amazon RDS, Amazon Aurora, or self-managed databases on Amazon EC2. Each choice carries different limits, administrative privileges, and operational responsibilities.

| Target | When Appropriate | What to Verify |
|---|---|---|
| Amazon RDS for PostgreSQL/MySQL | Want a standard managed database engine | Versions, extensions, parameter groups, superuser restrictions |
| Amazon Aurora PostgreSQL-Compatible | Need distributed storage architecture, scalability, and Aurora features | Version-specific PostgreSQL compatibility, extensions, Aurora-specific behavior |
| Amazon Aurora MySQL-Compatible | Workloads fit MySQL and benefit from Aurora capabilities | MySQL compatibility version, behavioral differences, parameters |
| Amazon RDS for Oracle/SQL Server | Want to keep the engine or minimize application changes | Edition, licensing, options, feature support, and RDS limitations |
| Database on EC2 | Need deep OS/engine control or specialized features | Self-managed patching, backups, HA, monitoring, and recovery |

"Compatible" does not mean every feature, extension, or behavior of the original engine is identical. Aurora PostgreSQL-Compatible tracks published PostgreSQL version compatibility, yet still has architectural, extension, and AWS-managed differences. RDS also restricts certain OS-level and superuser administrative privileges.

Before locking the target:
1. Confirm the source/target engine pair is supported by your migration tools.
2. Verify the target engine version supports all features required by the application.
3. Cross-check extensions, plugins, collations, encodings, and index types.
4. Review limits on connections, storage, transactions, logs, and replication.
5. Evaluate licensing, cost, HA, backups, encryption, and DR.
6. Test with a representative schema containing complex objects.

Never select a target based solely on engine name or instance price. Compatibility gaps and code conversion effort can outweigh compute cost differences.

## 6. AWS Tools for Schema Assessment and Conversion

### 6.1 AWS Schema Conversion Tool (AWS SCT)

AWS SCT assists with assessing and converting schemas and database code across heterogeneous DBMS engines. Depending on the source/target pair and tool version, SCT can:
- Connect to source and target databases.
- Analyze objects and engine features.
- Generate assessment reports.
- Categorize what converts automatically vs. what requires manual action.
- Generate target DDL or code for supported objects.
- Assist in converting supported application SQL or ancillary artifacts in supported scenarios.

SCT cannot fully understand the business intent of every stored procedure, trigger, or dynamic SQL statement. Its output must be reviewed by DBAs and application owners.

### 6.2 AWS DMS Schema Conversion

AWS DMS Schema Conversion provides schema assessment and conversion within AWS DMS migration workflows for supported engine pairs. Capabilities, interfaces, object types, and supported engine pairs evolve across releases and services. Always verify current support matrices in AWS documentation before designing the workflow.

When selecting tools:
- Use the tool suited to your specific source/target pair.
- Verify engine versions and privileges needed to read metadata.
- Evaluate handling of stored code, packages, triggers, and specialized objects.
- Record the exact tool version and assessment settings for reproducibility.
- Run trials against a clone or staging environment.

### 6.3 AWS Database Migration Service (AWS DMS)

AWS DMS primarily moves data from source to target. Depending on engine and configuration, DMS supports full load, ongoing replication / change data capture (CDC), or both combined.

DMS does not automatically translate source database logic into equivalent target logic. DDL and stored code must be assessed and converted using schema conversion tools or manual engineering. DMS tasks also require proper configuration of mappings, table selections, endpoints, networking, replication instance/serverless capacity, LOB modes, and error handling.

### 6.4 Distinguishing Responsibilities

| Component | Role | Do Not Assume |
|---|---|---|
| Schema assessment | Identify differences between source and target | High assessment score means the app runs cleanly |
| Schema conversion | Generate/convert supported DDL and code | All business logic translated accurately |
| DMS full load | Load existing baseline data | All schemas and objects were converted completely |
| DMS CDC | Sync ongoing changes during migration | Arbitrary DDL changes replicate safely |
| Application refactor | Update SQL, drivers, configs, and logic | Changing only the connection string is enough |
| Validation | Verify schemas, data, and runtime behavior | Matching row counts prove full integrity |

## 7. Interpreting the Assessment Report

An assessment report lists conversion findings and required remediation actions. Category names, scoring, and granularity vary by tool and version, but look for these finding types during review:

- Objects that convert automatically.
- Objects that convert partially.
- Unsupported objects or items lacking direct mappings.
- SQL syntax requiring rewrite.
- Built-in functions requiring replacement.
- Data types needing mapping or precision/range confirmation.
- Stored procedures/packages containing complex logic.
- Source features relying on special extensions or privileges.
- Objects dependent on other unconverted objects.

Never use automated conversion percentage as your sole KPI. A schema with 98% auto-converted objects can still contain one critical settlement or tax-calculation package that fails to convert. Conversely, hundreds of unused auxiliary objects can drag down the percentage while posing minimal real risk.

### 7.1 Classifying by Impact

Maintain a dedicated remediation register:

| Severity | Definition | Example | Handling |
|---|---|---|---|
| P0 - Blocker | Cannot cut over until resolved | Transaction-posting procedure has no mapping | Redesign, rewrite, and business test |
| P1 - High | Impacts correctness, security, or core workloads | `NULL`, time zone, or precision discrepancies | Remediate and enforce regression tests |
| P2 - Medium | Impacts a subset of features or performance | Non-equivalent index type | Replace and benchmark |
| P3 - Low | Rarely used or clear workaround exists | Comments or unreferenced legacy objects | Verify dependencies and retire cleanly |

For every finding, document:
- Specific object/schema and location.
- Source construct and target limitation.
- Impact on business or application.
- Proposed remediation.
- Assigned owner and reviewer.
- Test case proving resolution.
- Current status and evidence.

### 7.2 Verifying Whether Objects Are Still Used

Not every object in the catalog is still used by applications. However, never drop an object simply because a conversion tool flagged it as hard to convert.

Combine multiple sources of evidence:
- In-catalog dependencies.
- Query/statement logs and database monitoring.
- Source code repositories and application configs.
- Job schedulers, ETLs, and BI metadata.
- Interviews with application owners and DBAs.
- Observation across a sufficiently long business cycle, including month-end/quarter-end batches.

An object absent from daily logs might still be invoked by a quarterly close or disaster recovery process. Removing an object requires owner sign-off and a rollback plan.

## 8. Data Type and Value Differences

Data type mapping is one of the easiest places to introduce silent bugs. Inspect not only type names, but also value ranges, precision, scale, encoding, and how applications bind and read values.

The table below shows common mapping directions. Exact target types must be selected based on engine pair, version, real data, and application requirements.

| Common Source | PostgreSQL / Aurora PostgreSQL Target | MySQL / Aurora MySQL Target | Verification Points |
|---|---|---|---|
| Oracle `NUMBER(p,s)` | `numeric(p,s)` or appropriate integer | `DECIMAL(p,s)` or integer | Precision, scale, overflow, rounding |
| Oracle unparameterized `NUMBER` | `numeric` or specific numeric type | `DECIMAL` or specific numeric type | Actual value range and semantics |
| SQL Server `DECIMAL(p,s)` | `numeric(p,s)` | `DECIMAL(p,s)` | Never reduce precision during mapping |
| Oracle `VARCHAR2(n)` | `varchar(n)` / `text` | `varchar(n)` / `text` | Character vs. byte semantics, encoding |
| Oracle `NVARCHAR2` | `varchar` with proper encoding | `varchar` with proper charset | Unicode and byte limits |
| SQL Server `NVARCHAR` | `varchar` / `text` in UTF-8 database | `varchar` with proper charset | Collation, Unicode, length |
| Oracle `DATE` | `timestamp` or `date` per actual semantics | `datetime` / `date` | Oracle `DATE` includes hours/minutes/seconds |
| Oracle `TIMESTAMP WITH TIME ZONE` | `timestamptz` after confirming semantics | `timestamp` with explicit time zone convention | Offset, zone ID, DST |
| SQL Server `DATETIME2` | `timestamp` | `datetime(precision)` matching need | Precision and range |
| SQL Server `BIT` | `boolean` or `smallint` | `boolean` / `tinyint(1)` per convention | ORM, driver, and legacy values |
| SQL Server `UNIQUEIDENTIFIER` | `uuid` | `char(36)` or `binary(16)` by design | Sorting/order, representation, indexing |
| Oracle `RAW` / SQL Server `VARBINARY` | `bytea` | `varbinary` / `blob` | Size, LOBs, and transport |
| Oracle `CLOB` / SQL Server `NVARCHAR(MAX)` | `text` | `longtext` | LOB streaming and limits |
| Oracle `BLOB` / SQL Server `VARBINARY(MAX)` | `bytea` or large object by design | `longblob` | Size, memory, and driver API |
| JSON | `json` / `jsonb` | `JSON` | Validation, indexing, and query semantics |
| XML | `xml` or text/JSON by design | MySQL lacks native `xml` type; store as text | Queries, validation, and namespaces |
| Spatial types | PostGIS if supported/installed | Corresponding spatial types | SRID, indexes, and functions |
| Arrays / user-defined types | PostgreSQL arrays/types if appropriate | Table redesign / JSON / custom types | Serialization and application handling |

### 8.1 Precision and Scale

In `DECIMAL(p,s)`, `p` is total digits and `s` is fractional digits after the decimal point. If the source permits wider values than the target, loads can fail or values can be rounded.

Example:

~~~sql
-- PostgreSQL/Aurora PostgreSQL
CREATE TABLE invoice_line (
    amount numeric(18, 4) NOT NULL
);
~~~

~~~sql
-- MySQL/Aurora MySQL
CREATE TABLE invoice_line (
    amount DECIMAL(18, 4) NOT NULL
);
~~~

Before mapping, query actual min/max values, integer digit counts, fractional digit counts, and out-of-range values. Never blindly convert `NUMBER` to `INTEGER` just because current sample rows happen to be whole numbers.

### 8.2 Date, Time, and Time Zones

Distinguish among:
- Calendar dates without time-of-day.
- Timestamps without time zone.
- Timestamps with offset/time zone.
- UTC instants stored by application convention.
- Local business wall-clock times.

Questions that must be answered:
1. Does the source store values in UTC or local time?
2. Does session time zone affect query results?
3. Are calculations affected by daylight saving time (DST)?
4. Does the application compare timestamps across multiple Regions?
5. Must the target preserve the instant, offset, or named time zone?
6. Does historical data contain ambiguous DST transition timestamps?

For transactional systems, standardize on storing instants in UTC while storing business time zones separately when local display is required. Never migrate timestamps simply by renaming column types.

### 8.3 NULL, Empty Strings, and Defaults

Oracle treats empty character strings as `NULL` in many contexts. PostgreSQL and MySQL distinguish `''` from `NULL`.

If an application relies on empty strings to mean "no data," migration can alter:
- `IS NULL` predicates.
- Unique constraints.
- Filters and aggregates.
- `COALESCE` / `NVL` logic.
- ORM and API validation.

Establish explicit rules defining which values represent `NULL` vs. empty string and how historical data is normalized. Inspect default expressions and whether applications omit columns or explicitly pass `NULL`.

### 8.4 Character Sets and Collations

Check:
- Database and column encodings.
- Case-sensitive vs. case-insensitive comparisons.
- Accent-sensitive vs. accent-insensitive behavior.
- Sort order and locale.
- Character length vs. byte length.
- Collation-dependent indexes.
- Unicode normalization and special characters.

Two databases both storing UTF-8 strings can still produce different `ORDER BY`, `LIKE`, or unique constraint behavior due to collations. If applications depend on sorting or comparison rules, build tests using accented Vietnamese strings, mixed case, combining diacritics, and non-BMP characters.

## 9. Object and SQL Dialect Differences

### 9.1 Identity, Sequences, and Generated Keys

DBMS engines generate IDs differently:
- Oracle commonly uses sequences, often paired with triggers.
- SQL Server provides `IDENTITY` and sequences.
- PostgreSQL supports sequences and identity columns.
- MySQL uses `AUTO_INCREMENT`.

PostgreSQL example:

~~~sql
CREATE TABLE customer (
    customer_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email varchar(320) NOT NULL
);
~~~

MySQL example:

~~~sql
CREATE TABLE customer (
    customer_id BIGINT NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    PRIMARY KEY (customer_id)
);
~~~

After full load, sequences or identity counters must be synchronized past the highest loaded value. Otherwise, subsequent inserts collide with existing keys. Also verify whether applications assign IDs themselves, use `RETURNING`, call `LAST_INSERT_ID()`, or read generated keys via JDBC.

### 9.2 Constraints

Check:
- Primary keys and unique constraints.
- Foreign keys and cascade actions.
- Check constraints.
- Deferrable / deferred constraints.
- Disabled, non-validated constraints, or legacy violating rows.
- Order of constraint creation and validation during full load.

Some engines allow constraints in a non-validated state or handle deferred checking differently. If application logic relies on constraints being checked at transaction commit, test that exact behavior on target.

### 9.3 Indexes

An index is more than a column list. Evaluate:
- B-tree, hash, bitmap, full-text, spatial, and specialized indexes.
- Unique, composite, partial/filtered, and expression indexes.
- Included columns, clustered vs. nonclustered indexes.
- Sort direction, null ordering, and collations.
- Indexes on functions or generated columns.
- Maintenance overhead and write amplification.

A bitmap index on source may have no direct equivalent on target. Design indexes for target workloads and engine capabilities rather than mechanically translating source index definitions.

### 9.4 Partitioning

Inventory partition keys, range/list/hash strategies, subpartitions, intervals, retention, and query patterns. Verify partition pruning support and partition management operations on target.

For example, daily date partitioning on source may map to range partitioning in PostgreSQL or an appropriate partitioning scheme in MySQL. Syntax, partition count limits, and attach/detach/drop operations vary by engine and version.

### 9.5 Views and Materialized Views

Views often depend on functions, schemas, synonyms, and privileges. Materialized views may have distinct refresh mechanics, indexes, and refresh schedules.

After conversion:
- Verify dependencies and creation order.
- Run queries to confirm results match source.
- Check owner vs. invoker privileges.
- Define target refresh mechanics and schedules.
- Evaluate query plan impact.

### 9.6 Stored Procedures, Functions, and Packages

This is typically the highest-effort conversion area in heterogeneous migrations.

Differences may include:
- Procedural languages (PL/SQL, T-SQL, PL/pgSQL).
- Exception handling and error codes.
- Cursors, bulk operations, and dynamic SQL.
- Temporary tables and table variables.
- Transaction control inside procedures.
- Packages, global variables, and session state.
- Function determinism, side effects, and execution privileges.
- Schedulers, jobs, and external procedures.
- Built-in functions and date arithmetic.

Oracle example:

~~~sql
CREATE OR REPLACE PROCEDURE close_order (
    p_order_id IN NUMBER
) AS
BEGIN
    UPDATE orders
       SET status = 'CLOSED'
     WHERE order_id = p_order_id;
END;
/
~~~

Illustrative PostgreSQL version:

~~~sql
CREATE OR REPLACE PROCEDURE close_order(p_order_id bigint)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE orders
       SET status = 'CLOSED'
     WHERE order_id = p_order_id;
END;
$$;
~~~

These two snippets share similar intent, but do not prove equivalence in all cases. Test parameter types, transactions, privileges, exceptions, fired triggers, affected row counts, and how applications invoke the procedure.

### 9.7 Triggers

Triggers can fire before or after insert/update/delete, per row or per statement depending on the engine. Execution ordering among multiple triggers, recursion, transition tables, and transaction semantics can differ.

Pay special attention to triggers that:
- Generate keys.
- Write audit trails.
- Maintain summary/aggregate tables.
- Enforce business rules.
- Emit external side effects.
- Sync data to other tables.

While DMS full load or CDC runs, know whether target triggers are enabled and whether they risk duplicating rows or firing unintended side effects. Your migration plan must dictate when triggers are created/enabled and how trigger-generated data is handled.

### 9.8 Synonyms, Packages, and Database Links

Source-coupled objects such as synonyms, packages, database links, external tables, or linked servers usually require redesign. Alternatives include:
- Schema-qualified names.
- Views or wrappers.
- API or service boundaries.
- Federation or integration services.
- ETL or replication pipelines.
- Equivalent database links where supported by target and allowed by security posture.

Never expand network trust between two databases merely to preserve a database link without reviewing trust boundaries.

## 10. SQL Semantics and Behavioral Differences

A query can execute without syntax errors yet return different results. Test semantics, not just syntax.

| Topic | Differences to Check | Recommended Tests |
|---|---|---|
| Case folding | How unquoted identifiers are folded | Create mixed-case tables/columns and query them |
| Identifier length | Object name length limits | Test long names and collisions after truncation |
| `NULL` | Three-valued logic, empty strings, aggregates | Compare `IS NULL`, `COUNT`, `COALESCE` |
| String comparison | Collation, accents, case, trailing spaces | Test Vietnamese accents and trailing whitespace |
| Date arithmetic | Adding months, month-end, time zones | Test month-end dates and DST boundaries |
| Numeric rounding | Precision, scale, rounding modes | Test boundary and midpoint values |
| Pagination | `ROWNUM`, `TOP`, `LIMIT`, `OFFSET`, window functions | Check deterministic ordering and duplicates |
| Upsert/merge | `MERGE`, `ON CONFLICT`, `ON DUPLICATE KEY` | Test concurrent inserts and updates |
| Sequences | ID generation, caching, restarts, sync | Test after full load and failover |
| Locking | Row/table locks, deadlock detection | Test concurrency and retry behavior |
| Isolation | Read committed, repeatable read, serializable | Test concurrent transactions |
| Temporary objects | Session vs. global temp table semantics | Test with connection pooling and cleanup |
| Error handling | `SQLSTATE`, vendor codes, exceptions | Verify retry logic and error mapping |
| JSON | Path syntax, null vs. missing, comparisons, indexes | Test missing fields, null values, and arrays |
| Regex | Dialect and collation | Test production regex patterns |

### 10.1 Identifiers and Schema Naming

PostgreSQL folds unquoted identifiers to lowercase; Oracle traditionally folds unquoted identifiers to uppercase. MySQL identifier behavior depends on OS platform and configuration. Therefore:
- Avoid relying on inconsistent casing.
- Standardize naming conventions.
- Audit quoted identifiers in code.
- Check for name collisions or truncation after mapping.
- Replace dynamic SQL that builds object names using legacy casing assumptions.

### 10.2 SQL Functions

Functions with similar names do not always share identical semantics:
- `NVL` typically maps to `COALESCE` or an equivalent expression.
- `SYSDATE`, `CURRENT_TIMESTAMP`, and `GETDATE()` differ in time zone and evaluation timing.
- `DECODE` may require `CASE`.
- `LISTAGG`, `STRING_AGG`, and `GROUP_CONCAT` differ in syntax and ordering.
- Date/time, regex, substring, and type conversion functions can yield different results.

Never run bulk search-and-replace without testing. Validate nulls, data types, locales, and precision for each function conversion.

### 10.3 Transactions and Locking

Assess:
- Default isolation level.
- Snapshot/MVCC behavior.
- Row-level vs. table-level locking.
- Deadlock detection and victim selection.
- Lock timeouts and statement timeouts.
- Transactional DDL support.
- Savepoints and nested transaction behavior.
- Autocommit behavior in drivers.
- Application retry logic.

An application may implicitly depend on lock escalation or source-specific concurrent update semantics. After migration, test concurrent clients updating the same row, updating shared aggregates, and running batches during peak hours.

## 11. Application and Driver Compatibility

The schema is only half the contract between application and database. Audit the entire data access path.

### 11.1 JDBC and ORMs

For Java applications:
- Confirm the JDBC driver version supports the target engine/version.
- Update JDBC URL, TLS, authentication, and connection properties.
- Verify mappings for `NUMERIC`, `TIMESTAMP`, `UUID`, `BLOB`, `CLOB`, and `JSON`.
- Verify generated keys, batch inserts, callable statements, and cursors.
- Review Hibernate/JPA dialects or MyBatis type handlers.
- Check ORM schema validation or auto-generation settings.
- Review connection pools, validation queries, timeouts, and retries.
- Verify exception translation and `SQLState` handling.

Never swap just the driver and hostname and push straight to production. Run integration tests with the exact driver and framework versions slated for deployment.

### 11.2 Dynamic SQL and Queries Outside Repositories

Queries may live in:
- Configuration files.
- Reporting tools.
- Stored procedures.
- ETL scripts.
- BI dashboards.
- Batch jobs.
- Operational notebooks and scripts.
- Partner applications.

Use query history logs, code search, and owner interviews to uncover hidden SQL. Build a query catalog tracking query ID, caller, criticality, engine-specific syntax, and conversion status.

### 11.3 Connections and Authentication

Verify:
- Writer and reader endpoints.
- DNS resolution and failover behavior.
- Ports and network paths.
- TLS modes and certificate trust chains.
- Password authentication, IAM database authentication, or other supported mechanisms.
- Secret rotation.
- Connection pool lifetimes and stale connection eviction.
- JVM/runtime DNS caching.
- Timeouts, keepalives, and retry policies.

Aurora cluster endpoints and RDS endpoints serve distinct roles. Applications must use the endpoint matching their read/write behavior and handle reconnects cleanly after failover.

## 12. Post-Conversion Performance Assessment

A syntactically valid schema does not guarantee workloads will run as fast as on source. Optimizers, statistics, storage, CPU, memory, connection limits, and concurrency differ.

### 12.1 Workload Baseline

Before migration, capture:
- Top SQL by total elapsed time, CPU, reads, and executions.
- p50/p95/p99 latency.
- Throughput and transaction rates.
- Peak connections and active sessions.
- Lock waits, deadlocks, and long-running transactions.
- Buffer/cache hit ratios.
- Storage IOPS, throughput, and queue depth.
- Batch durations and business completion windows.

Select baselines representing peak hours, batches, reporting, and financial close periods.

### 12.2 Indexes and Query Plans

After conversion:
1. Update statistics per target engine guidelines.
2. Run `EXPLAIN` / execution plans for top SQL.
3. Compare scan types, join orders, and estimated vs. actual rows.
4. Identify obsolete indexes or missing new indexes.
5. Benchmark both reads and writes since extra indexes increase write overhead.
6. Verify partition pruning and parameter-sensitive plans where supported.

Do not recreate every source index blindly. Use target query workloads and data distribution to guide index design.

### 12.3 Checking Skewed Data Distributions

Optimizers choose poor plans when statistics do not reflect real data. For large tables:
- Collect statistics after full load.
- Check data skew in filter/join columns.
- Consider histograms or extended statistics where supported.
- Check partition-level statistics.
- Benchmark using production-scale volume and realistic data distribution.

## 13. Security and Privileges on the Target Database

Never copy all privileges verbatim from source. Redesign around least privilege and workload responsibilities.

Review:
- Users, roles, schema owners, and object owners.
- `SELECT`/`INSERT`/`UPDATE`/`DELETE`/`EXECUTE` grants.
- DDL/object creation and administrative privileges.
- Row-level security or equivalent policies.
- Encryption at rest and in transit.
- KMS keys, key policies, and usage grants.
- Audit logging and log export.
- Secret storage and rotation.
- DMS replication user privileges.
- S3 access permissions if staging/exports are used.
- Network permissions between on-premises and VPC.

Never hardcode database credentials in migration scripts or source repositories. Use AWS Secrets Manager or an approved secret store. If applications use IAM database authentication, verify engine/instance/driver support and token lifetimes before rollout.

## 14. Designing the Schema Conversion Plan

A controlled conversion workflow follows these steps.

### Step 1: Lock Source and Target Scope

Document engine/version, schema scope, target engine/version, Region, VPC, HA, encryption, and owners. Confirm the source/target pair is tool-supported.

### Step 2: Prepare the Assessment Environment

- Grant required metadata read permissions.
- Establish secure connectivity to source and target.
- Create a test target database/schema.
- Install or open the right tool version.
- Record configuration, timestamp, and operator identity.
- Use a clone or snapshot when production load must be protected.

### Step 3: Run the Assessment

Run the assessment across all in-scope schemas. Archive raw reports, logs, and object inventories—do not save only summary scores or percentages.

### Step 4: Classify and Prioritize

Categorize findings into blocker, high, medium, and low; verify whether objects are actively used; assign owners and due dates. Group findings by root cause such as data types, functions, packages, collations, or security.

### Step 5: Automated Conversion

Use AWS SCT or AWS DMS Schema Conversion for supported engine pairs. Output DDL/code into a test target or reviewable artifacts. Never apply generated scripts directly to production solely because a tool produced them.

### Step 6: Manual Remediation

DBAs and application owners remediate items that do not auto-convert:
- Rewrite routines.
- Redesign sequences/identities.
- Finalize data types.
- Replace indexes/partitions.
- Migrate schedulers and jobs.
- Redesign database links or external dependencies.
- Update roles and grants.
- Update SQL inside applications.

Every manual change requires test cases and peer review.

### Step 7: Deploy in Dependency Order

Create extensions, custom types, and schemas before dependent objects. Then deploy tables, sequences, constraints, indexes, views, and routines in dependency order. Heavy constraints or indexes may require staggered creation to speed up data loading.

### Step 8: Re-Run Assessment and Review

Re-run assessment after changes. Compare reports to confirm blockers are resolved and no new issues were introduced.

### Step 9: Freeze Schema for Migration Rehearsal

Define the DDL freeze window, change approval workflow, and hotfix rules. Unplanned DDL changes during full load or CDC can break mappings or fail tasks.

## 15. Example Workflow: Converting Oracle to Aurora PostgreSQL-Compatible

Hypothetical scenario: an order system runs on Oracle and the project team evaluates Amazon Aurora PostgreSQL-Compatible as the target to reduce licensing dependence and standardize on a platform for Java applications.

### 15.1 Inventory

The team collects:
- Oracle version and character set configuration.
- List of schemas, tables, partitions, and indexes.
- PL/SQL packages, procedures, functions, and triggers.
- Sequences and key-generation triggers.
- Materialized views, scheduler jobs, and database links.
- Top SQL, transaction rates, and peak connections.
- JDBC drivers, ORMs, and stored procedure calls in applications.

### 15.2 Assessment

The assessment tool identifies:
- Most table and column mappings convert automatically.
- Several `NUMBER` columns require explicit precision decisions.
- Some `DATE` columns store time-of-day components.
- PL/SQL packages require rewriting.
- Functions using `NVL`, `DECODE`, and `CONNECT BY` need replacement.
- Database links and scheduler jobs require redesign.
- Specialized indexes require re-evaluation.

The team refuses to rely solely on the automated conversion percentage. Packages handling order states and fee calculations are classified P0 because they directly govern correctness.

### 15.3 Conversion and Manual Remediation

- Create schemas and tables on Aurora PostgreSQL.
- Map `NUMBER` columns based on verified actual value ranges.
- Convert sequence/trigger key generation to identity columns or sequences matching application ID logic.
- Rewrite procedures/packages into PostgreSQL functions/procedures.
- Replace Oracle SQL functions and hierarchical queries.
- Redesign database links into service/API calls or controlled integration pipelines.
- Design indexes based on target workload and benchmarks.

### 15.4 Testing

- Compare row counts and checksums per partition.
- Test extreme decimals, `NULL`, empty strings, and timestamps.
- Run order lifecycle, refund, settlement, and batch tests.
- Compare query plans and latency.
- Verify permissions, auditing, and secret rotation.
- Run full load + CDC + cutover rehearsals.

### 15.5 Cutover Decision

Cut over only when:
- Zero unapproved unresolved blockers remain.
- Critical stored code passes business tests.
- Data validation meets agreed thresholds.
- Application integration and performance meet acceptance criteria.
- On-call owners, runbooks, and rollback plans are in place.
- RPO/RTO and downtime windows are confirmed.

This illustrates the workflow only, not an automated conversion prescription for every Oracle database.

## 16. Data Migration and Coordination with AWS DMS

Once the target schema is ready, the migration team plans data movement. AWS DMS is commonly used for full load and CDC in supported scenarios.

### 16.1 High-Level Sequence

~~~text
Source database
      |
      | Schema assessment / conversion
      v
Target schema (RDS / Aurora)
      |
      | DMS full load
      v
Initial target data
      |
      | DMS CDC from source logs
      v
Target catches up
      |
      | Validation + application tests
      v
Cutover
      |
      v
Target becomes primary
~~~

### 16.2 Full Load

Full load copies existing rows for selected tables. Before starting:
- Verify schema, type mappings, and `TargetTablePrepMode`.
- Configure table mappings and transformation rules.
- Evaluate LOB modes, batch sizes, and parallel load settings.
- Check whether FKs, triggers, and constraints impede loading.
- Monitor task logs, table statistics, and per-table errors.
- Decide how to handle very large tables or tables lacking primary keys.

Never assume all tables load simultaneously with zero source impact. Benchmark and throttle load on production.

### 16.3 Change Data Capture

CDC reads source transaction logs to sync changes occurring after full load starts. Requirements depend on engine:
- Sufficient log retention.
- Privileges to read logs/transactions.
- Supplemental logging or change tracking if required by the engine.
- Stable network connectivity.
- Adequate DMS capacity for the change rate.
- Target schema ready for mappings.
- Monitoring replication lag and apply errors.

DDL changes may not be handled like DML across all configurations. Enforce a DDL freeze or sync schema changes separately. Never run ad-hoc schema migrations during active CDC without testing.

### 16.4 Validation

AWS DMS provides validation capabilities depending on engine and task configuration. Teams must also execute independent business validation. Validation adds load to both source and target, so factor it into capacity planning.

## 17. Post-Conversion Schema and Data Verification

Do not stop at "the script ran without errors." Verify structure, values, relationships, and runtime behavior.

### 17.1 Schema Validation

Verify:
- Object counts and names.
- Columns, types, precision, scale, and nullability.
- Default and generated expressions.
- PK/FK/unique/check constraints.
- Indexes, partitions, and sequences.
- Views and materialized views.
- Procedures, functions, and triggers.
- Users, roles, owners, and grants.
- Extensions and database settings.

You can export target DDL and compare it against the expected schema after normalizing non-semantic formatting differences.

### 17.2 Data Validation

Baseline validation suite:

| Check | Method | Catches |
|---|---|---|
| Row counts | Count by table/partition | Missing or extra rows |
| Aggregates | `SUM`, `MIN`, `MAX`, `COUNT` by business key | Summary discrepancies |
| Null distribution | Count `NULL` vs. empty strings | Mapping discrepancies |
| Ranges | Min/max, string lengths, precision | Overflow or truncation |
| Referential integrity | Orphan row and FK checks | Broken relationships |
| Hash/checksum | Hash by key or chunk | Content corruption |
| Sample comparison | Compare representative records and edge cases | Column-level mapping bugs |
| Business reconciliation | Order totals, balances, settlements | Business logic discrepancies |

For large tables, chunk by primary key or partition to avoid full-table scans impacting performance. Hashing requires canonical serialization rules; time zones, decimal scales, and collations can alter hashes even when business values match.

### 17.3 Boundary Data Testing

Create test cases for:
- `NULL`, empty strings, whitespace.
- Unicode strings and special characters.
- Decimals near max precision.
- Negative numbers, zero, and extreme values.
- Timestamps across midnight, month-end, leap years, and DST.
- Empty, small, large, and oversized LOBs.
- UUIDs, binary blobs, and JSON with missing/null fields.
- Sequences immediately after data load.
- FK, unique, and check constraints.
- Transaction rollbacks and concurrent updates.

## 18. Application and Business Testing

Build a test suite exercising the target using the exact application version, drivers, ORMs, and production-like configuration.

Test groups:

1. Smoke tests: connectivity, basic reads/writes, health checks.
2. CRUD tests: insert, update, delete, select, and pagination.
3. Transaction tests: commit, rollback, savepoints, concurrency.
4. Stored code tests: procedures/functions/triggers and error paths.
5. Integration tests: queues, caches, search, ETLs, payments, dependent services.
6. Security tests: roles, privileges, TLS, secret rotation, auditing.
7. Performance tests: throughput, latency, connection pools, batches.
8. Recovery tests: failover, reconnect, backup/restore, rollback.

### 18.1 Business Transaction Verification

For example, creating an order may require:
- Writing the order header.
- Writing order line items.
- Deducting inventory.
- Recording a payment intent.
- Writing an audit log.

If the source executes all steps inside one transaction, the target must preserve equivalent invariants or adopt an approved consistency design. Test mid-transaction failures, retries, duplicate requests, and concurrent checkouts.

### 18.2 Compare Results, Not Just Speed

For every test case, compare:
- Result sets.
- Row counts.
- Error behavior.
- Side effects.
- Transaction boundaries.
- Latency and resource consumption.

A faster query that returns different data is not a pass. A query returning identical data much more slowly must also be tuned before cutover.

## 19. Cutover and Rollback Planning

Cutover redirects applications to the target database. Maintain an explicit checklist and named decision-makers.

### 19.1 Pre-Cutover

- Schema conversion and peer reviews complete.
- Full load/CDC rehearsed.
- Replication lag within threshold.
- Data validation and application tests passed criteria.
- DDL frozen.
- Policy-compliant backups/snapshots confirmed.
- DNS, secrets, certificates, and endpoints staged.
- Source write-stop and connection-draining procedures rehearsed.
- Owners, incident bridge, timeline, and abort criteria confirmed.

### 19.2 Sample Cutover Sequence

1. Announce the maintenance window.
2. Stop or restrict writes on the source application.
3. Wait for in-flight transactions to complete.
4. Wait for CDC to catch up and confirm lag within threshold.
5. Run final data validation.
6. Switch application configuration to target endpoints.
7. Start workloads in controlled groups.
8. Execute smoke tests and business transactions.
9. Monitor error rates, latency, database metrics, and replication.
10. Declare cutover successful against approved criteria.

Exact sequencing depends on engine and architecture. Never assume CDC can simply reverse direction once target accepts new writes.

### 19.3 Rollback

Rollback must be designed upfront. The hardest question: what happens to data written to target after cutover?

Once target receives new writes, reverting to source risks data loss or divergence. Determine:
- Can target writes be halted?
- Is reverse replication supported and tested?
- Can transactions be replayed or reconciled?
- At what point is rollback no longer safe?
- Who holds authority to call rollback?
- What data loss tolerance exists?

Never treat flipping DNS back to the old endpoint as a complete rollback. Require an explicit data consistency plan.

## 20. Hybrid Connectivity and Securing the Migration Path

Sources may reside on-premises, in colocation data centers, other clouds, or other VPCs. Hybrid connectivity typically uses AWS Site-to-Site VPN, AWS Direct Connect, or a combined design.

Evaluate:
- Real-world latency and throughput.
- Bandwidth for full load and CDC.
- Routing, subnets, and DNS.
- Security groups, NACLs, firewalls, and ports.
- TLS and certificate trust.
- Network segmentation.
- Connectivity permissions for the DMS replication environment.
- Transfer windows and link constraints.
- Redundancy if VPN/Direct Connect drops.

The DMS replication instance or environment needs network paths to both source and target. Never open inbound rules to all CIDRs "just to make it work." Restrict security groups and firewall rules strictly to required endpoints, ports, and sources.

When using VPN/Direct Connect, test MTU, packet loss, throughput, and route failover. Full load can saturate bandwidth and impact other workloads; apply throttling or batch scheduling as needed.

## 21. Observability and Error Handling

Monitor both migration progress and target database health.

### 21.1 Migration Metrics

- Full load progress and active table count.
- CDC latency / replication lag.
- Throughput and backlog.
- Task/table errors and suspended tables.
- DMS CPU/memory/storage where applicable.
- Network throughput and packet loss.
- Remaining source log retention.
- Target write pressure and lock waits.

### 21.2 Target Database Metrics

- CPU, memory, storage, IOPS, and throughput.
- Database connections and connection saturation.
- Query latency and top SQL.
- Deadlocks, lock waits, and long transactions.
- Cache hit ratios, temp file spills, and vacuum/analyze metrics by engine.
- Error logs and failover events.
- Backup status and replication health.

Amazon CloudWatch monitors RDS/Aurora and DMS metrics. Combine database logs, Performance Insights / Database Insights where supported and configured, and application logs to correlate migration events with business impact.

### 21.3 Troubleshooting Common Issues

| Symptom | Possible Cause | Investigation Approach |
|---|---|---|
| Object fails to convert | Source feature lacks mapping | Read detailed assessment, redesign, or rewrite manually |
| Precision error on insert | Target type narrower than value range | Check min/max, precision/scale, and mappings |
| Character corruption | Charset/encoding/collation mismatch | Check byte lengths, Unicode, and connection encoding |
| Duplicate key after load | Sequence/identity out of sync | Check current values and generated key behavior |
| Growing CDC lag | Source logs, network, or slow target apply | Inspect DMS metrics/logs, workload, and capacity |
| FK validation fails | Pre-existing source violations or incomplete load | Locate orphan rows and enforce data policy |
| Slow queries | Different indexes/statistics/plans | Inspect execution plans and benchmark |
| Connection resets | Timeouts, DNS, failover, or stale pools | Check endpoints, TLS, pool lifetimes, and retries |
| Wrong stored procedure output | Semantics/exception/transaction differences | Write business tests and compare side effects |
| Rising deadlocks | Different lock ordering and concurrency | Capture deadlock graphs; adjust transactions/retries |

## 22. Governing Post-Migration Schema Changes

Once the target becomes primary, schemas continue evolving over the application lifecycle. Allowing teams to run ad-hoc DDL creates drift and inconsistent environments.

Establish:
- A schema migration tool (such as Flyway or Liquibase) compatible with the target engine.
- Version control for DDL and database code.
- Pull request reviews for schema changes.
- Backward-compatible change standards.
- Expand-and-contract patterns when modifying columns or APIs.
- Staging tests against production-like data.
- Backup/restore and rollback scripts where appropriate.
- Schema drift detection across dev, staging, and production.

Expand-and-contract pattern:
1. Add new columns or structures compatible with old code.
2. Deploy application code capable of reading/writing both old and new structures.
3. Backfill data.
4. Switch traffic to the new structure.
5. Verify no consumers still read the old structure.
6. Drop the old structure in a separate release.

Never drop or rename columns immediately when deploying new code if older instances remain running or rollback still requires the old schema.

## 23. Compatibility Assessment Checklist

Use this checklist before approving target selection and conversion plans.

- [ ] Source engine, version, edition, and patch level documented.
- [ ] Target engine/version confirmed supported by AWS and migration tools.
- [ ] Region, VPC, subnets, security groups, and hybrid connectivity verified.
- [ ] Character sets, collations, and time zones inventoried.
- [ ] Tables, columns, constraints, indexes, and partitions fully inventoried.
- [ ] Sequences, identity columns, and generated key behavior evaluated.
- [ ] Views, materialized views, procedures, functions, packages, and triggers inventoried.
- [ ] Extensions, plugins, spatial, XML, JSON, LOB, and user-defined types evaluated.
- [ ] SQL dialects and built-in functions have remediation plans.
- [ ] Transactions, isolation levels, locking, and retry semantics tested.
- [ ] JDBC/ODBC drivers, ORMs, ETLs, BI tools, and dynamic SQL reviewed.
- [ ] Users, roles, grants, encryption, secrets, and auditing redesigned.
- [ ] Assessment reports archived and findings classified by impact.
- [ ] All blockers have assigned owners, remediation plans, and test cases.
- [ ] Performance baselines and workload tests defined.
- [ ] DMS full load/CDC plan includes capacity, log retention, and network sizing.
- [ ] Data validation, business reconciliation, and acceptance criteria agreed.
- [ ] Cutover, rollback, and point-of-no-return boundaries documented.
- [ ] Runbooks, on-call owners, and post-cutover monitoring in place.

## 24. Practice Exercises

### Exercise 1: Selecting a Database Target

A Java application uses Oracle with numerous PL/SQL packages, database links, and materialized views. The team wants to move to a PostgreSQL-compatible database.

Tasks:
1. List at least five facts to gather before choosing the target.
2. Identify three object types likely requiring refactoring.
3. Explain why changing only the JDBC URL will fail.

Suggested answers:
- Gather Oracle version, edition, character set, time zone, data volume, workload, package dependencies, database links, materialized views, JDBC/ORM versions, RPO/RTO, and downtime window.
- PL/SQL packages, database links, and materialized views require careful inspection.
- SQL dialects, stored code, type mappings, generated keys, drivers, and transaction semantics differ.

### Exercise 2: Handling Empty Strings

An Oracle source has a `customer_code` column containing both `NULL` and empty strings. The PostgreSQL target distinguishes the two.

Task: propose a handling process.

Answer:
- Clarify the business meaning of `NULL` vs. empty string.
- Count and sample existing rows.
- Agree on normalization rules with the application owner.
- Transform data per approved rules.
- Update queries and validation logic.
- Test `IS NULL`, unique constraints, filters, and API serialization.

### Exercise 3: Synchronizing Sequences

After full load, the target table has a maximum ID of 950,000, but its sequence still yields 1.

Task: what can happen and what must be checked?

Answer: new inserts will collide with existing primary keys. Synchronize sequence/identity counters past loaded data using target engine syntax, then test concurrent inserts and driver generated-key retrieval.

### Exercise 4: High Assessment Score

A tool reports 97% of objects convert automatically, but a payment settlement package is unsupported.

Task: can cutover be approved?

Answer: not yet. The payment package is a blocker if it affects correctness. Verify dependencies, rewrite it, test settlement/refund/error paths, and obtain business owner sign-off.

### Exercise 5: Choosing a Validation Strategy

A transaction table holds 800 million rows. Running one full-table checksum query does not fit inside the maintenance window.

Task: propose a strategy.

Answer:
- Split validation by partition or primary key ranges.
- Use row counts and aggregates grouped by date/status.
- Hash chunks using canonical serialization rules.
- Run weighted sampling and edge-case tests.
- Execute incremental validation prior to cutover, leaving only final delta validation for the cutover window.
- Measure query load to protect production.

### Exercise 6: CDC Lag

During rehearsal, CDC lag grows steadily whenever batch workloads start.

Task: list root-cause categories and telemetry to inspect.

Answer:
- Source log throughput and retention.
- Network bandwidth and latency.
- DMS capacity, task logs, and backlog.
- Target CPU, IOPS, lock waits, indexes/FKs, and write throughput.
- Transaction sizes and batch patterns.
- Test adjusting capacity, batch windows, or load strategies in a test environment.

### Exercise 7: Time Zones

An application stores payment timestamps in local times across multiple countries. After conversion, reports are off by one hour on certain dates.

Task: identify factors to investigate.

Answer:
- Source and target session time zones.
- DST transitions and time zone database versions.
- Timestamp types with vs. without time zone.
- JDBC mappings and serialization.
- How the application converts local time to instants.
- Historical rows falling inside DST transition windows.

### Exercise 8: Rollback After Target Receives Writes

After cutover, several new orders were written to target. The application hits an error and the team wants to flip endpoints back to source.

Task: why is this dangerous?

Answer: source lacks the new target writes, so the two databases have diverged. Switching endpoints risks losing transactions or creating duplicates on retries. Stop writes, evaluate tested reverse replication or reconciliation, confirm the authoritative data source, and follow the rollback runbook.

## 25. Self-Check Questions

1. How does schema conversion differ from data migration?
2. Why is an assessment score insufficient to approve cutover?
3. Which compatibility layers should be evaluated?
4. Why must stored procedures and triggers be inventoried?
5. How can Oracle `DATE` differ from PostgreSQL `date`?
6. Why do Oracle empty strings require special handling?
7. How do precision and scale affect financial data?
8. When must collations be evaluated?
9. What error can identity columns and sequences cause after full load?
10. Why shouldn't source indexes simply be recreated verbatim on target?
11. What roles do AWS SCT / AWS DMS Schema Conversion and AWS DMS play?
12. What conditions does CDC require on source and network?
13. What risks arise from DDL changes during active CDC?
14. Do matching row counts prove full data accuracy?
15. What must be tested beyond SQL syntax?
16. Why must the exact target JDBC driver and ORM version be tested?
17. What problem must rollback solve once target accepts writes?
18. Why is a schema migration tool needed after cutover?
19. What factors must be checked for hybrid connectivity?
20. What governance metadata should every schema conversion blocker carry?

Suggested answers:

1. Schema conversion translates structures/code; data migration transfers data.
2. One incompatible critical object can break business logic even when automated conversion count is high.
3. Engine, schema, data type, SQL semantics, application, performance, security, operations, and migration path.
4. They often embed business logic and differ substantially across dialects.
5. Oracle `DATE` includes hours/minutes/seconds; PostgreSQL `date` represents calendar dates only.
6. Oracle treats empty character strings as `NULL` in many contexts; PostgreSQL distinguishes them.
7. Mismatches can cause overflow, rounding, or digit truncation.
8. Whenever string sorting/comparison, unique keys, or queries depend on locale, case, or accents.
9. Generating IDs that collide with loaded rows.
10. Index types and optimizers differ; design indexes for target workloads.
11. SCT/DMS Schema Conversion assess/convert schemas; DMS moves data and runs CDC.
12. Proper log settings/permissions, stable networking, adequate capacity, and ready target schemas.
13. Tasks may fail or schema mappings may drift out of alignment.
14. No; checksums, aggregates, edge cases, and business reconciliation are also needed.
15. Result sets, transactions, side effects, error handling, concurrency, and performance.
16. Drivers/ORMs differ in type mapping, generated keys, timeouts, and SQL dialects.
17. Handling new writes committed on target and preserving consistency with source.
18. To version-control DDL, enforce reviews, and prevent schema drift.
19. Routing, DNS, latency, throughput, MTU, firewalls, security groups, TLS, and failover.
20. Object, discrepancy, impact, owner, remediation plan, test evidence, and status.

## 26. Official References

Consult AWS documentation to confirm current engine pairs, versions, tools, and limits before implementation:

- [AWS Schema Conversion Tool](https://docs.aws.amazon.com/SchemaConversionTool/latest/userguide/Welcome.html)
- [AWS DMS Schema Conversion](https://docs.aws.amazon.com/dms/latest/userguide/schema-conversion.html)
- [AWS Database Migration Service User Guide](https://docs.aws.amazon.com/dms/latest/userguide/Welcome.html)
- [AWS DMS supported source and target databases](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Introduction.Sources.html)
- [AWS DMS data validation](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Validating.html)
- [AWS DMS best practices](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_BestPractices.html)
- [Amazon RDS DB engine versions](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_DBEngineVersions.html)
- [Amazon Aurora PostgreSQL-Compatible documentation](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.AuroraPostgreSQL.html)
- [Amazon Aurora MySQL-Compatible documentation](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.AuroraMySQL.html)
- [Amazon RDS security](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.html)
- [AWS Site-to-Site VPN](https://docs.aws.amazon.com/vpn/latest/s2svpn/VPC_VPN.html)
- [AWS Direct Connect](https://docs.aws.amazon.com/directconnect/latest/UserGuide/Welcome.html)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
- [Amazon CloudWatch monitoring for Amazon RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/monitoring-cloudwatch.html)

Supported features and engine pairs change across tool versions, engines, and Regions. Always verify documentation matching your actual environment, run assessments on a representative schema, and confirm outcomes through independent testing prior to cutover.
