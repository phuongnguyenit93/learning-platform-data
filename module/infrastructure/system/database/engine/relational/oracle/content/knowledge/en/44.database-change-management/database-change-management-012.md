# Verifying SQL Plans, Drivers, Timezones, Privileges, and Applications After an Oracle Upgrade

## 1. Goal of Post-Upgrade Verification

Upgrading Oracle Database can alter the database release, Release Update (RU), optimizer behavior, data dictionary, timezone files, driver compatibility, and configuration defaults. An application may still start cleanly yet suffer slower queries, mis-mapped timestamps, stored procedures missing privileges, or connection pools retaining sessions created before the upgrade.

Therefore, post-upgrade verification does not stop at "is the database OPEN?" You must prove that critical business flows continue returning accurate results with performance and access permissions within agreed bounds.

This lesson belongs to the **Database Engine Relational Oracle** module, **Change and Upgrade** chapter, focusing on **verifying SQL plans, drivers, timezones, privileges, and applications after an upgrade**.

Five areas to verify:

1. **SQL plans:** critical SQL queries still use suitable plans, with cardinality and runtime staying within thresholds.
2. **Drivers:** Oracle JDBC, JDK, connection pools, ORMs, and TLS/wallet configurations are compatible with the new database.
3. **Timezones:** database, session, JVM, and applications interpret timestamps consistently, especially across DST regions.
4. **Privileges:** runtime accounts still hold exact object/system privileges, roles, synonyms, and package execution rights.
5. **Applications:** transactions, connection pools, batch jobs, schedulers, integrations, and business workflows all operate properly.

A solid verification effort includes a pre-upgrade baseline, a representative test environment, pass/fail criteria, post-upgrade evidence, and a rollback or mitigation plan.

## 2. Verification Scope and Principles

Before running tests, clearly establish:
- Which databases were upgraded and which CDBs/PDBs are affected.
- Oracle Database release, RU, and timezone file version before/after.
- Java runtime, Oracle JDBC driver, UCP, or other pools.
- Spring Boot, Hibernate/JPA, frameworks, and integration libraries.
- Involved schemas, service accounts, database links, jobs, and external dependencies.
- Critical SQL statements, APIs, and transactions.
- SLAs for latency, throughput, error rates, and recovery time.

### 2.1. Risk-Based Verification

Not every SQL query needs equal measurement. Prioritize:
- High-runtime or high-CPU SQL.
- High-frequency SQL.
- SQL with skewed bind value distributions.
- SQL using partitioning, functions, analytics, parallelism, or database links.
- Transactions updating balances, inventory, payments, and order states.
- Queries performing timezone conversions or date comparisons.
- Procedures/packages using dynamic SQL or definer/invoker rights.
- Flows passing through connection pools and multiple tenants.

### 2.2. Distinguishing Database Issues from Application Issues

A post-upgrade failure may originate from:
- Database or optimizer.
- Driver/protocol.
- Datasource/pool configuration.
- ORM mappings.
- Privilege changes.
- Data or statistics.
- DNS, listeners, TLS, or wallets.
- JVM, framework, or deployment configuration changes.

Record the layer where the error occurred, `SQL_ID` if available, Oracle error code, service, module/action, and request ID. Avoid blaming "the Oracle upgrade" before gathering evidence.

### 2.3. Testing on a Production-Comparable Environment

Staging should mirror production closely in:
- Database release/RU and initialization parameters.
- Schemas, objects, indexes, partitions, and statistics.
- Representative data scale and distributions.
- Services, PDBs, networking, and authentication.
- Java/JDBC/pool/ORM versions.
- Concurrency and workload.

A tiny database with minimal test data cannot prove SQL plans or pool behavior will match production.

## 3. Collecting the Pre-Upgrade Baseline

A baseline is reference data showing what changed. Measuring only after the upgrade makes it hard to separate new regressions from pre-existing issues.

### 3.1. Database Identity and Version

Capture version details:

```sql
SELECT banner_full
FROM v$version
ORDER BY banner_full;
```

```sql
SELECT instance_name,
       host_name,
       version,
       version_full,
       status
FROM v$instance;
```

In a CDB/PDB, record the current container:

```sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'CON_ID') AS con_id
FROM dual;
```

Record database identity:

```sql
SELECT name,
       db_unique_name,
       open_mode,
       database_role,
       log_mode
FROM v$database;
```

Dynamic performance views require appropriate privileges. If the runtime account lacks access, DBAs run the inventory and supply approved results.

### 3.2. Initialization Parameters

Save parameters affecting the optimizer, memory, parallelism, cursors, and sessions:

```sql
SELECT name,
       value,
       isdefault,
       issys_modifiable,
       ispdb_modifiable
FROM v$parameter
WHERE name IN (
    'compatible',
    'optimizer_features_enable',
    'optimizer_mode',
    'cursor_sharing',
    'statistics_level',
    'parallel_degree_policy',
    'pga_aggregate_target',
    'sga_target',
    'open_cursors',
    'processes',
    'sessions',
    'timezone'
)
ORDER BY name;
```

Do not copy an entire parameter file to a new environment without checking changed defaults and unsupported parameters. The baseline aims to surface differences and identify which parameters to keep or tune.

### 3.3. Objects and Invalid Objects

Capture object counts by owner/type/status:

```sql
SELECT owner,
       object_type,
       status,
       COUNT(*) AS object_count
FROM dba_objects
GROUP BY owner, object_type, status
ORDER BY owner, object_type, status;
```

Capture the invalid object list:

```sql
SELECT owner,
       object_name,
       object_type,
       status
FROM dba_objects
WHERE status <> 'VALID'
ORDER BY owner, object_type, object_name;
```

Not every invalid object stems from the upgrade, so compare against the baseline. Post-upgrade, identify which objects need recompiling and investigate compile errors rather than running mass compiles and ignoring output.

### 3.4. SQL and Application Baselines

For critical SQL, save:
- Normalized SQL text or `SQL_ID`.
- Plan hash value and execution plan.
- Bind data types and representative bind value sets.
- Elapsed time, CPU, buffer gets, and physical reads.
- Rows processed and execution counts.
- Parse count and version count if applicable.
- Notable wait events.
- Application-tier p50/p95/p99 latency.

At the application tier, save:
- Request success/failure rates.
- Throughput.
- API p50/p95/p99 latency.
- Pool active/idle/pending counts and acquisition latency.
- Batch durations, record counts, and errors.
- Transaction rollbacks/deadlocks.
- Scheduler/job durations.
- JDBC error rates and Oracle vendor codes.

Tie baselines explicitly to timestamps, workloads, datasets, and configurations.

## 4. Verifying the Database Post-Upgrade

Before testing applications, confirm the database is serviceable and required components are complete.

### 4.1. Check Database and PDBs

```sql
SELECT name,
       open_mode,
       database_role
FROM v$database;
```

In a CDB:

```sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
```

Confirm the right PDB, service, and open mode. A PDB opened `READ ONLY` or `RESTRICTED` can break application operations even when the instance is `OPEN`.

### 4.2. Check Registry and Components

```sql
SELECT comp_id,
       comp_name,
       version,
       status
FROM dba_registry
ORDER BY comp_id;
```

Check SQL patch status:

```sql
SELECT patch_id,
       patch_type,
       action,
       status,
       action_time,
       description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
```

Exact names/columns and view access depend on release. Cross-check against the upgrade guide and upgrade tool output for your deployed release.

### 4.3. Check Invalid Objects Post-Upgrade

```sql
SELECT owner,
       object_type,
       COUNT(*) AS invalid_count
FROM dba_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY owner, object_type;
```

If recompilation is needed, follow DBA-approved procedures such as `utlrp.sql` per Oracle documentation for that release. Afterward, re-query `DBA_OBJECTS` and `DBA_ERRORS`. Never treat script completion as proof every object is valid.

### 4.4. Alert Log and Services

Check:
- Alert log contains no unresolved startup/upgrade errors.
- Listeners register the expected services.
- PDB services are active.
- Required jobs are enabled per plan.
- Archives/FRA, Data Guard, or backup jobs operate if in scope.
- Security components/wallets open per procedure.

Database `OPEN` is only an initial precondition, not final acceptance.

## 5. Verifying SQL Execution Plans Post-Upgrade

The optimizer may pick different plans post-upgrade due to release changes, `OPTIMIZER_FEATURES_ENABLE`, statistics, histograms, adaptive features, cardinality estimates, or system settings.

A changed plan hash does not automatically mean a regression. Conversely, an identical plan hash does not guarantee identical latency if data, caching, concurrency, or I/O changed.

### 5.1. Selecting Critical SQL

Build a SQL list by business function:
- Login and dashboard loading.
- Customer/order searches.
- Order creation, inventory updates, and payments.
- Daily/monthly reports.
- Batch imports/exports.
- Scheduled stored procedures.
- SQL querying database links.
- SQL with heavily skewed bind values.

Each SQL query needs a business owner and performance criteria.

### 5.2. Inspecting Actual Plans

After running a representative SQL query with runtime statistics enabled, display the cursor plan:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :sql_id,
        :child_number,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
```

For the session's current `SQL_ID`, retrieve it from `V$SQL` or monitoring tools. `ALLSTATS LAST` is helpful when execution statistics are collected, such as via `GATHER_PLAN_STATISTICS` or appropriate configuration.

You need privileges to read cursors and related views. Never include sensitive bind values in shared reports or logs.

### 5.3. Comparing Before/After Plans

Compare:
- Plan hash value.
- Join order and join methods.
- Access paths: index range scan, unique scan, full scan, partition scan.
- Predicate access/filter operations.
- Estimated rows vs. actual rows.
- Buffer gets and physical reads.
- Sort/hash operations and spills to disk.
- Remote operations if database links are used.
- Parallel execution.
- Adaptive plans and child cursors.

Never compare plan hashes alone. Inspect the actual operations and execution metrics.

### 5.4. Estimated Rows vs. Actual Rows

Large discrepancies between `E-Rows` and `A-Rows` can cause the optimizer to pick poor join methods or access paths.

Potential causes:
- Stale or unrepresentative statistics.
- Missing or inappropriate histograms.
- Data skew.
- Bind peeking / adaptive cursor sharing.
- Multi-column correlations.
- Predicates wrapping columns in functions or implicit conversions.
- Missing partition pruning.

Post-upgrade, avoid hastily gathering statistics across an entire production schema without assessment. Gathering stats can shift plans en masse. Use a controlled statistics plan, compare results, and maintain a recovery path.

### 5.5. Testing Multiple Bind Value Groups

A query may perform well for common bind values yet crawl for rare values or large tenants.

Test with:
- High-selectivity values.
- Low-selectivity values.
- Small tenants and large tenants.
- Short and long date ranges.
- `NULL` if supported by the SQL.
- Actual JDBC bind types.

Never test a single sample input and declare the SQL stable.

### 5.6. SQL Plan Management

SQL Plan Management (SPM) helps manage and stabilize accepted SQL plans. DBAs can inventory SQL plan baselines:

```sql
SELECT sql_handle,
       plan_name,
       enabled,
       accepted,
       fixed,
       reproduced
FROM dba_sql_plan_baselines
ORDER BY sql_handle, plan_name;
```

SPM helps preserve verified plans during transition. However:
- Baselines must be captured/transported and verified for the exact SQL.
- Old plans must remain reproducible on the new database.
- Never pin a bad plan just because it existed pre-upgrade.
- Baselines do not replace workload and data testing.
- Manage lifecycle to avoid accumulating stale baselines.

Follow SPM procedures and privilege rules for your Oracle release.

### 5.7. Optimizer Parameters Are Not a Universal Rollback Button

`OPTIMIZER_FEATURES_ENABLE` controls release-level optimizer features, yet lowering it globally is not a clean fix for every regression. Parameter changes can affect many unrelated queries.

If mitigation is needed:
1. Isolate the specific regressing SQL.
2. Collect plan and runtime evidence.
3. Diagnose the root cause.
4. Test statistics, SQL patches/baselines, or SQL tuning in staging.
5. Assess broad impact before deploying to production.

## 6. Verifying Statistics, Indexes, and Partitions

### 6.1. Statistics

Check statistics freshness:

```sql
SELECT owner,
       table_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM dba_tab_statistics
WHERE owner IN ('APP', 'SALES')
ORDER BY owner, table_name;
```

Schema names are illustrative. Check:
- Table statistics.
- Column statistics.
- Histograms.
- Index statistics.
- Partition/subpartition statistics.
- Extended statistics if present.

Never treat `NUM_ROWS` as an exact real-time row count; it is a collected statistical estimate.

### 6.2. Index Status

```sql
SELECT owner,
       index_name,
       table_name,
       status,
       visibility,
       uniqueness
FROM dba_indexes
WHERE owner IN ('APP', 'SALES')
ORDER BY owner, table_name, index_name;
```

For partitioned indexes, also inspect partition/subpartition statuses via the corresponding dictionary views. Unexpected `UNUSABLE` or invisible indexes can shift execution plans.

### 6.3. Partition Pruning

If queries filter by partition keys, confirm plans perform expected pruning. Predicates with implicit conversions or functions around columns can defeat pruning.

Compare accessed partitions before/after and test across multiple date ranges. Do not just verify row output; confirm the query does not scan excessive partitions.

### 6.4. Do Not Rebuild Every Index Habitually Post-Upgrade

Rebuilding indexes is not a default chore to "make the database faster" after every upgrade. Rebuild only with technical evidence and an approved change plan. Rebuilds consume I/O, redo, and space, and can disrupt active workloads.

## 7. Verifying the Oracle JDBC Driver and Java Runtime

A database upgrade may require or recommend a different Oracle JDBC driver version. The driver must be compatible with:
- Oracle Database release/RU.
- Java/JDK version.
- JDBC API level.
- Thin or OCI mode.
- UCP / connection pool.
- TLS, wallets, and authentication.
- ORM frameworks and dependent libraries.

### 7.1. Inventorying the Running Driver

In Java, inspect metadata:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println(metadata.getDatabaseProductVersion());
    System.out.println(metadata.getDriverName());
    System.out.println(metadata.getDriverVersion());
    System.out.println(metadata.getJDBCMajorVersion());
    System.out.println(metadata.getJDBCMinorVersion());
}
```

In production, log metadata to protected diagnostics without printing credentials or sensitive data.

Also record:
- JDK vendor/version.
- Oracle JDBC artifact/version.
- UCP version if used.
- HikariCP or pool version.
- Spring Boot version.
- Hibernate version.
- Custom extensions/type handlers.

### 7.2. Checking the Dependency Tree

Ensure the application does not accidentally bundle two versions of `ojdbc` or conflicting Oracle libraries via transitive dependencies.

With Maven:

```bash
mvn dependency:tree
```

With Gradle:

```bash
./gradlew dependencies
```

Inspect actual runtime artifacts inside the deployed container/package, as build-time dependency trees may differ from the running classpath.

### 7.3. Checking Driver/Database Compatibility

Consult the official Oracle support matrix for:
- Database release and RU.
- JDK release.
- JDBC driver family.
- UCP if used.
- Required authentication/TLS features.

Never upgrade a driver merely because it has a higher version number. Newer drivers can change behaviors, deprecate APIs, or require a newer JDK.

### 7.4. Basic JDBC Smoke Test

Run through the application's actual datasource/pool:

```java
try (Connection connection = dataSource.getConnection()) {
    if (!connection.isValid(3)) {
        throw new IllegalStateException("Oracle connection is not valid");
    }

    try (PreparedStatement statement =
                 connection.prepareStatement("SELECT 1 FROM dual");
         ResultSet resultSet = statement.executeQuery()) {

        if (!resultSet.next() || resultSet.getInt(1) != 1) {
            throw new IllegalStateException("Unexpected Oracle response");
        }
    }
}
```

`Connection.isValid()` behavior varies by driver and may incur a network round-trip. Never use it as the sole test; test transactions, fetches, binds, LOBs, and stored procedures.

### 7.5. Testing JDBC Data Type Mappings

Prioritize testing mappings the application actually uses:
- `NUMBER` ↔ `BigDecimal`.
- `DATE`/`TIMESTAMP` ↔ Java date/time types.
- `CLOB`/`BLOB`.
- `RAW`/UUID mappings if used.
- `ARRAY`/`STRUCT` or Oracle-specific types.
- `REF CURSOR`.
- Boolean mappings via `NUMBER`/`CHAR` if used by convention.
- Generated keys and sequences/identity columns.
- Batch updates and `OUT` parameters.

Check nulls, precision, scale, timezones, and boundary values.

### 7.6. Testing TLS, Wallets, and Authentication

If using TCPS, Oracle Wallet, mTLS, Kerberos, tokens, or external authentication, test inside the real runtime/container:
- Trust chain and certificate expiration.
- Wallet paths and file permissions.
- Aliases/service descriptors.
- JDK truststore.
- Permitted TLS protocols and ciphers.
- Certificate/secret rotation.
- Driver authentication modes.

A working SQL Developer connection on a DBA's laptop does not prove Java containers have the right wallet or truststore.

## 8. Verifying Connection Pools and Session Behavior

A new driver or database upgrade can expose pool issues:
- Idle connections dropped by firewalls.
- Changed validation behavior.
- Unreset session state.
- Statement caches retaining stale cursors.
- Altered timeout or failover behavior.
- Pools opening connections past session limits.

### 8.1. Checking Pool Metrics

Track:
- Active/idle/total connections.
- Pending borrowers.
- Acquisition latency.
- Connection creation latency.
- Validation failures.
- Evicted connections.
- Connection timeout counts.
- Leak detection warnings.
- Maximum lifetime and idle timeouts.

Compare before/after under identical concurrency and workloads.

### 8.2. Testing Stale Connections and Restarts/Failovers

In staging:
1. Open connections through the pool.
2. Leave them idle for a controlled period.
3. Simulate network interruption or database service restart.
4. Borrow connections again.
5. Confirm broken connections are detected and evicted.
6. Confirm the pool opens fresh connections and requests recover within deadlines.

Never run fault injection in production without change approval and safeguards.

### 8.3. Session State

Verify:
- NLS session parameters.
- `CURRENT_SCHEMA`.
- `SESSIONTIMEZONE`.
- Application contexts.
- `CLIENT_IDENTIFIER`, module/action.
- Auto-commit/isolation levels.
- Temporary tables or package state if used.

Ensure any request-specific state is set and reset across the connection lifecycle. Pools do not automatically know every `ALTER SESSION` or `DBMS_SESSION.SET_CONTEXT` issued by the application.

### 8.4. Statement Cache

Oracle JDBC implicit/explicit statement caches affect parsing and cursor reuse. After an upgrade or driver change:
- Verify cache size and configuration.
- Check statement close lifecycles.
- Check child cursor/version counts.
- Verify bind metadata stability.
- Watch for invalid cursor or statement reuse errors.
- Measure parse counts and latency.

Never raise cache size solely to reduce parses without checking `open_cursors` and workload memory.

## 9. Verifying Timezones Across Oracle, JDBC, and the JVM

Timezones are a common source of silent bugs because one instant can be represented via local time, fixed offset, or timezone region.

Distinguish:
- Database time zone.
- Session time zone.
- Oracle timezone file.
- JVM default time zone.
- Application/user time zone.
- Timezone regions vs. UTC offsets.

### 9.1. Checking Timezone Settings in Oracle

```sql
SELECT dbtimezone,
       sessiontimezone
FROM dual;
```

Timezone file/version:

```sql
SELECT filename,
       version
FROM v$timezone_file;
```

`DBTIMEZONE` and `SESSIONTIMEZONE` mean different things. Never assume session timezone matches database timezone or JVM timezone.

### 9.2. Checking JVM Timezone

In Java:

```java
ZoneId systemZone = ZoneId.systemDefault();
ZoneId utc = ZoneId.of("UTC");

System.out.println(systemZone);
System.out.println(ZoneRulesProvider.getVersions(systemZone.getId()).lastKey());
```

Check the JVM timezone inside the actual runtime container, not just on a build machine. `TZ`, JVM flags, and base images can give different default zones across environments.

### 9.3. Distinguishing Oracle Temporal Types

| Oracle Type | Characteristics |
|---|---|
| `DATE` | Date and time to seconds; stores no timezone |
| `TIMESTAMP` | Date/time with fractional seconds; stores no timezone |
| `TIMESTAMP WITH TIME ZONE` | Stores timezone offset or region info |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Normalized to database time zone on write; displayed in session time zone on read |

Never alter column types or ORM mappings during an upgrade without verifying current data semantics.

### 9.4. DST and Timezone Regions

An offset like `+07:00` carries no historical or future daylight saving rules for a locality. A timezone region like `Europe/Paris` encodes DST rules that shift by date and can change by legislation.

When storing future location-based schedules or appointments, regions carry richer semantics than fixed offsets. When recording past instants, UTC instants simplify comparison and exchange.

### 9.5. Checking the Timezone File Post-Upgrade

Oracle timezone files are independently versioned. Database upgrades or RUs may ship updated timezone files and DST upgrade steps. You should:
- Record before/after versions.
- Read the release Upgrade Guide.
- Identify timezone-sensitive columns and data.
- Plan a timezone file upgrade if needed.
- Follow the release-appropriate `DBMS_DST` workflow.
- Test data across DST transition timestamps.
- Never run `DBMS_DST` in production outside a change plan.

A newer timezone file can alter how Oracle interprets specific historical or future region/date values. Do not treat it as merely cosmetic.

### 9.6. TIMESTAMP WITH LOCAL TIME ZONE

Values are normalized to the database time zone when stored and converted to the session time zone when queried. Thus, the exact same stored data displays differently across two session timezones while representing the identical instant.

Test with:
- Session timezone UTC.
- Business session timezone.
- Timestamps before/after DST transitions.
- Values near midnight.
- Data with fractional seconds.

Never compare formatted display strings to check whether two timestamps represent the same instant.

## 10. Java Time and JDBC Mapping Post-Upgrade

The Java Time API provides distinct types:

| Java Type | Meaning |
|---|---|
| `Instant` | A point on the UTC timeline |
| `OffsetDateTime` | Date/time with a fixed UTC offset |
| `ZonedDateTime` | Date/time with a timezone region and rules |
| `LocalDateTime` | Date/time without a timezone |
| `LocalDate` | Date only |
| `LocalTime` | Time only |

### 10.1. Choosing Types by Semantics

- Past events needing global comparison: consider `Instant`.
- Timestamps with a known offset: `OffsetDateTime`.
- Local schedules tied to regions and DST: store the region separately or model with `ZonedDateTime` in domain logic.
- Business dates without times: `LocalDate`.
- Opening hours without dates: `LocalTime`.
- `LocalDateTime` fits only when business semantics truly lack timezones; never use it as an instant.

### 10.2. JDBC 4.2 and Typed Mappings

JDBC 4.2 drivers support `setObject`/`getObject` with selected Java Time types. Exact behavior depends on the Oracle JDBC version and Oracle column type.

Example to test against your actual driver:

```java
OffsetDateTime input = OffsetDateTime.now(ZoneOffset.UTC);

try (PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO app.event_log(event_time_tz) VALUES (?)")) {
    statement.setObject(1, input);
    statement.executeUpdate();
}
```

Read back:

```java
try (PreparedStatement statement = connection.prepareStatement(
        "SELECT event_time_tz FROM app.event_log WHERE event_id = ?")) {
    statement.setLong(1, eventId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            OffsetDateTime value =
                    resultSet.getObject(1, OffsetDateTime.class);
        }
    }
}
```

Never assume every driver version maps every Java Time type identically. You may need `getTimestamp`, `Calendar`, or explicit column/driver mappings.

### 10.3. Do Not Use java.sql.Timestamp to Carry Timezone Regions

`java.sql.Timestamp` represents a timestamp but cannot carry timezone regions like `Europe/Paris`. If regions must be preserved, store the region ID separately or use an explicit domain mapping.

### 10.4. Checking Spring/Hibernate Mappings

After upgrading drivers or Hibernate:
- Check the JDBC type bound for `LocalDateTime`, `OffsetDateTime`, and `Instant`.
- Check actual database column types.
- Check Hibernate timezone storage strategies if configured.
- Check `hibernate.jdbc.time_zone` if used.
- Check JSON serialization/deserialization.
- Check fractional second precision.
- Check nulls and boundary cases.

Never change `hibernate.jdbc.time_zone` blindly just to make one test pass; verify data semantics first.

## 11. Verifying Privileges and Runtime Identity

Post-upgrade, application accounts may hit `ORA-01031`, `ORA-00942`, `PLS-00201`, or package execution errors even when schema objects exist.

Common causes:
- Missing grants or differences across PDBs.
- Users/roles missing in the right container.
- Privileges granted via roles where definer-rights PL/SQL requires direct grants.
- Synonyms pointing to wrong or invalid objects.
- Locked or expired accounts.
- Proxy authentication or common/local user changes.
- Missing privileges on sequences, directories, DB links, or network ACLs.

### 11.1. Confirm Identity Inside the Application Session

From the application's actual connection:

```sql
SELECT sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'CURRENT_USER') AS current_user,
       sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
```

Never log into SQL Developer with a similar account and assume the application account's privileges are intact.

### 11.2. Checking Object Privileges

DBAs can inspect:

```sql
SELECT grantee,
       owner,
       table_name,
       privilege,
       grantable
FROM dba_tab_privs
WHERE grantee IN ('APP_RUNTIME', 'APP_ROLE')
ORDER BY grantee, owner, table_name, privilege;
```

Column-level grants:

```sql
SELECT grantee,
       owner,
       table_name,
       column_name,
       privilege
FROM dba_col_privs
WHERE grantee IN ('APP_RUNTIME', 'APP_ROLE')
ORDER BY grantee, owner, table_name, column_name;
```

### 11.3. Checking System Privileges and Roles

```sql
SELECT grantee,
       privilege,
       admin_option
FROM dba_sys_privs
WHERE grantee IN ('APP_RUNTIME', 'APP_ROLE')
ORDER BY grantee, privilege;
```

```sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role
FROM dba_role_privs
WHERE grantee IN ('APP_RUNTIME', 'APP_ROLE')
ORDER BY grantee, granted_role;
```

Inside the application session:

```sql
SELECT * FROM session_roles;
SELECT * FROM session_privs;
```

Compare active privileges after login, not merely expected grant scripts.

### 11.4. Direct Grants and Definer-Rights PL/SQL

Stored procedures/packages default to definer's rights (`AUTHID DEFINER`). Static SQL inside definer-rights units cannot use privileges inherited solely through roles of the owner under Oracle rules.

If a package owner accesses a table in another schema, the owner needs direct object grants. An application may run `SELECT` directly via a role yet fail with insufficient privileges when invoking a procedure.

Example DBA direct grant:

```sql
GRANT SELECT ON sales.customer TO app_owner;
```

Never resolve this by granting `DBA` or overly broad `ANY` privileges. Grant exact object privileges needed.

### 11.5. AUTHID DEFINER vs. AUTHID CURRENT_USER

- `AUTHID DEFINER`: execution privileges derive from the program unit owner per definer-rights rules.
- `AUTHID CURRENT_USER`: executes under the invoker/current user with invoker-rights semantics.

Changing `AUTHID` alters security boundaries. Never switch it just to bypass post-upgrade permission errors; conduct security reviews and full testing.

### 11.6. Checking Objects, Synonyms, and Sequences

```sql
SELECT owner,
       object_name,
       object_type,
       status
FROM dba_objects
WHERE owner IN ('APP', 'SALES')
  AND status <> 'VALID'
ORDER BY owner, object_type, object_name;
```

Check synonyms:

```sql
SELECT owner,
       synonym_name,
       table_owner,
       table_name,
       db_link
FROM dba_synonyms
WHERE owner IN ('APP', 'PUBLIC')
ORDER BY owner, synonym_name;
```

Check sequence privileges and objects referenced by packages. A metadata-valid synonym does not guarantee the runtime account holds privileges on the underlying target object.

### 11.7. PDBs and Common/Local Users

In multitenant databases, distinguish:
- Common users/roles at the CDB level.
- Local users/roles inside a PDB.
- Common grants vs. local grants.
- Objects residing in a specific PDB.
- Services routing to the exact PDB.

A grant in one container does not automatically mean runtime sessions in another PDB hold identical rights. Run checks inside the exact target container and application service.

### 11.8. Account Status and Password Policies

Check account status, expiration, profiles, proxy authentication, and password rotation per policy. Never include passwords in verification reports. Confirm secret managers, wallets, or vaults are updated for applications post-deployment.

## 12. Verifying Stored Procedures, Jobs, and External Access

Many applications do more than query tables:
- Calling packages/procedures/functions.
- Using sequences/identities.
- Writing files via directory objects.
- Calling external procedures.
- Querying database links.
- Calling HTTP endpoints via ACLs/network packages.
- Running scheduler jobs.

Inventory all used database APIs and test using the exact runtime identity. Check:
- Package/function `VALID` status.
- `EXECUTE` privileges.
- Direct grants for definer-rights owners.
- Argument data types and overloads.
- `OUT` parameters/cursors.
- Scheduler credentials/job states.
- Directory objects and underlying OS permissions.
- DB link services/credentials.
- Network ACLs/host permissions where used.

Do not stop at unit tests doing repository `SELECT`s. Reporting packages, batch routines, or overnight jobs are often the first places permission errors surface.

## 13. Verifying Spring Boot/JPA Applications Post-Upgrade

Applications must be tested along the exact production execution path: same container image, JDK, datasource, pool, ORM, secrets, and service name.

### 13.1. Startup Smoke Test

Verify:
- Application context initializes cleanly.
- DataSource establishes connections.
- Flyway/Liquibase migrations do not run unexpectedly.
- Hibernate schema validation succeeds if enabled.
- Health/readiness endpoints report healthy.
- Zero classloading or driver incompatibility errors.
- Zero connection pool leaks at startup.

Never allow automatic migrations to run in production if the release plan mandates separate migration management.

### 13.2. Repository and Transaction Tests

Test:
- `SELECT` by primary key and filters.
- `INSERT`/`UPDATE`/`DELETE`.
- Transaction rollback.
- Unique/foreign keys.
- Optimistic locking.
- Pessimistic locking if used.
- Batch operations.
- Stored procedure calls.
- Pagination/sorting.
- Native queries.
- LOBs/large result sets.
- Lazy/eager loading.
- Multi-tenant/VPD contexts if used.

Verify both data accuracy and query counts/latency. A repository returning right results while firing extra queries post-upgrade still causes regressions.

### 13.3. Transaction Boundaries

Confirm `@Transactional` behaves as designed:
- Right transaction manager.
- Right datasource/persistence unit.
- Proxies invoked properly.
- Rollback rules unchanged.
- Appropriate isolation levels.
- Connections returned cleanly to the pool.
- No self-invocation bypassing transaction proxies.

### 13.4. Batches and Schedulers

Test:
- Scheduled jobs.
- Batch imports/exports.
- Job retries/restarts.
- Concurrency locks preventing duplicate runs.
- Checkpoints and resumability.
- Runtimes against representative data volumes.
- File/directory or remote database permissions if applicable.

Never run two production jobs simultaneously just for testing if jobs are non-idempotent or lack duplicate guards.

### 13.5. End-to-End Business Flows

Pick representative flows:
1. Authenticate and establish session.
2. Read reference data.
3. Create transaction.
4. Update status and write audit trail.
5. Publish event or invoke external system.
6. Read back results.
7. Reporting/reconciliation.

Check final data state, side effects, latency, and log correlation. Tests must confirm business correctness, not merely HTTP 200.

## 14. Verifying Connection Pools and Session State Post-Deployment

When deploying a new application version, pools typically open fresh connections, though rolling deployments keep old processes running alongside new ones. Verify both old and new processes per rollout plan.

Check:
- Pool sizes/connection timeouts.
- Validation and stale connection eviction.
- Max lifetime/idle timeouts.
- Driver socket/connect/read timeouts.
- Statement caches.
- Session NLS baselines.
- Application context initialization/reset.
- `CLIENT_IDENTIFIER`, module/action.
- Session timezones.
- Connection leaks and transaction durations.

### 14.1. Do Not Test Only the First Connection

Pools hold multiple physical connections that may carry differing session state. Test repeated borrow/return cycles, force connection reuse in test environments, and inspect state each time.

### 14.2. Resetting Session State

If the application issues `ALTER SESSION`, modifies NLS, sets application contexts, or tags module/action, reset them when requests/transactions end. `Connection.close()` in a pool generally returns the logical handle to the pool without guaranteeing all Oracle session state is wiped.

### 14.3. Rolling Deployments

In multi-instance rollouts:
- Confirm every pod/process uses the approved driver and configuration.
- Monitor per-instance pool metrics.
- Prevent old versions from connecting to the new database unless covered by the compatibility matrix.
- Drain connections and in-flight requests before stopping instances.
- Track errors segmented by application version.

## 15. Functional and Boundary Data Testing

Post-upgrade, run regression tests with boundary data:
- High-precision/scale `NUMBER` values.
- `NULL` and empty strings under Oracle semantics.
- Unicode and collations.
- `DATE`/`TIMESTAMP` with fractional seconds.
- Timestamps with timezone regions/offsets.
- Data near DST transitions.
- Large `CLOB`/`BLOB` payloads.
- Long strings and special characters.
- Partition boundaries.
- Multi-tenant and skewed datasets.
- Constraints and concurrent updates.

Inspect implicit conversions closely. SQL may compile fine yet return different results if NLS settings or bind types shifted.

## 16. Performance Testing and Pass/Fail Criteria

### 16.1. Comparing Workloads Under Identical Conditions

Hold constant:
- Dataset and data distributions.
- Warm vs. cold cache states (or document differences).
- Concurrency.
- Test duration.
- Bind value mix.
- JVM heap/CPU.
- Pool sizes.
- Network paths.
- Background job load.

Never compare a warm-cache test run against a cold-cache run and claim a regression.

### 16.2. Metrics to Compare

| Metric | Purpose |
|---|---|
| API p50/p95/p99 | User-perceived latency |
| Throughput | Processing capacity |
| SQL elapsed/CPU | Query cost |
| Buffer gets | Logical I/O |
| Physical reads | Storage I/O |
| Rows processed | Result volume |
| Parse count | Parse overhead |
| Pool acquisition latency | Connection contention |
| Active sessions | Database concurrency |
| Wait events | Bottlenecks |
| Error/rollback rate | Business stability |
| Batch duration | Background processing capacity |

### 16.3. Set Thresholds Before Testing

Illustrative criteria:
- Zero business errors or data corruption.
- Zero unexpected permission errors outside accepted exceptions.
- API p95 latency stays within approved SLA bounds.
- Critical SQL logical I/O stays within thresholds.
- Batch jobs finish within their windows.
- Pools show no sustained pending borrowers.
- Zero unexpected timezone offsets.

Thresholds must be approved by system/business owners. Do not apply one arbitrary percentage across every application.

## 17. Canary and Phased Rollouts

Where architecture permits, rollouts can proceed in phases:
1. Verify on clone/staging.
2. Run smoke and regression suites.
3. Shift one canary workload/instance.
4. Monitor errors, latency, SQL plans, and pool metrics.
5. Expand group by group.
6. Verify batches/schedulers once traffic stabilizes.
7. Complete rollout and archive evidence.

Canaries must be isolatable and rollback-capable. Once the database is upgraded, if old and new applications cannot coexist per compatibility matrix, use an appropriate cutover strategy rather than arbitrarily mixing versions.

### 17.1. Rollout Stop Criteria

Halt expansion if:
- Data corruption or wrong timezones appear.
- Privileges expand unexpectedly.
- Critical SQL regresses past thresholds.
- JDBC error rates spike.
- Pools exhaust or session counts surge abnormally.
- Batches/jobs fail to finish.
- Signs of in-doubt transactions or consistency errors appear.

### 17.2. Rollback and Forward Fixes

Rolling back an application image is often simpler than rolling back a database upgrade. Once the data dictionary or compatibility level changes, never assume you can downgrade simply by swapping binaries or restoring snapshots arbitrarily.

Runbooks must specify:
- Can the application be rolled back?
- Is database downgrade supported for this upgrade path?
- Are backups/restore points ready?
- Are data migrations backward-compatible?
- Can credentials/drivers/schemas coexist?
- Who decides rollback vs. forward fix?

## 18. Ordered Verification Runbook

A practical sequence:

### Pre-Upgrade
1. Inventory databases, PDBs, services, versions/RUs, and timezone files.
2. Inventory JDK, JDBC, pools, Spring Boot, Hibernate, and deployment artifacts.
3. Save critical SQL, execution plans, runtime metrics, and bind data types.
4. Save NLS/timezone/session parameters.
5. Save object statuses, grants, roles, synonyms, jobs, and account statuses.
6. Save application smoke/regression results.
7. Confirm backups and rollback/restore plans.

### Post-Database Upgrade
1. Confirm database/PDB/service states.
2. Check registry, SQL patches, and alert logs.
3. Check invalid objects and compile errors.
4. Check timezone files and DST status.
5. Check schemas, indexes, partitions, and statistics.
6. Check privileges and runtime identity in the right PDB.

### Post-Application/Driver Upgrade
1. Confirm actual runtime JDK and JDBC driver versions.
2. Open connections through production-like pools.
3. Test TLS/wallets/authentication.
4. Test NLS/session contexts.
5. Test typed JDBC mappings, transactions, and procedures.
6. Test pool reuse and stale connection eviction.
7. Test repositories, batches, and schedulers.

### Acceptance
1. Run representative SQL workloads.
2. Compare plans and runtimes against baselines.
3. Run end-to-end business flows.
4. Measure p50/p95/p99, throughput, and pool health.
5. Reconcile timezones, privileges, and data.
6. Collect evidence, log deviations, and make the go/no-go decision.

## 19. Verification Matrix

| Area | Checks | Evidence to Archive |
|---|---|---|
| Database | Version, RU, PDB/service, registry | Query output and change record |
| Objects | Invalid objects, index/partition status | Dictionary queries and compile logs |
| SQL plans | Plans, actual rows, buffer gets, latency | `DBMS_XPLAN` and workload reports |
| Statistics | Last analyzed, stale stats, histograms | DBA statistics views |
| JDBC | Driver/JDK/versions, connect, bind/fetch | Runtime metadata and integration tests |
| Pool | Active/idle/pending, eviction, timeouts | Pool metrics and test logs |
| Timezone | DB/session/JVM/file versions, DST | SQL/Java test outputs |
| Privileges | Session user, roles, direct grants, object access | Dictionary views and runtime tests |
| Application | APIs, transactions, batches, schedulers | Regression results and app logs |
| Operations | Alert logs, monitoring, rollback readiness | Runbook sign-off |

## 20. Troubleshooting by Symptom

| Symptom | First Place to Check |
|---|---|
| Query returns right data but is slow | Plan, actual rows, statistics, wait events, bind mix |
| `ORA-01031` | Runtime principal, direct grants, roles, definer-rights packages |
| `ORA-00942` | Current schema, synonyms, PDB, object owner, and privileges |
| `ORA-01882` or timezone region error | Timezone region/file version, JVM tzdata, driver |
| Date/time offset mismatch | `DATE`/`TIMESTAMP` semantics, session timezone, JVM zone, mappings |
| Numeric conversion differences | NLS numeric characters, implicit conversion, bind types |
| App starts yet queries fail | Driver compatibility, service/PDB, accounts/grants |
| Intermittent failures | Pool session state, connection reuse, child cursors/bind skew |
| Stored procedure fails while `SELECT` works | Direct grants, `AUTHID`, package status |
| Slow or timing-out batches | Plans, fetch/batch sizes, pool, locks, and commit frequency |
| TLS handshake fails | Wallets/truststores, certificates, protocols, driver/JDK |
| Some pods fail while others succeed | Runtime images, secret/config drift, driver classpath |

Investigate by timestamp and application version. Compare a succeeding request against a failing request to pinpoint differences in service, session, binds, context, and connections.

## 21. Anti-Patterns to Avoid

| Anti-Pattern | Risk | Better Practice |
|---|---|---|
| Checking only whether database is `OPEN` | Misses driver, privilege, plan, and business errors | Use a multi-layer verification matrix |
| Comparing plan hashes alone | Misses runtime cost and cardinality | Inspect plans, A-Rows, I/O, and latency |
| Gathering stats across everything post-upgrade | Can trigger widespread plan regressions | Assess and gather stats selectively |
| Lowering optimizer features globally for one SQL | Impacts unrelated queries | Fix per SQL with evidence |
| Using newest driver without checking JDK | Runtime incompatibilities | Follow compatibility matrices |
| Testing JDBC via SQL Developer | Does not test real Java driver stack | Test through real datasource/containers |
| Testing timestamps only in UTC | Misses DST and region rules | Test multiple timezones and boundaries |
| Treating `DBTIMEZONE` as `SESSIONTIMEZONE` | Misinterprets temporal data | Verify each timezone layer separately |
| Checking privileges only via roles | Definer-rights packages may lack direct grants | Test with runtime accounts and packages |
| Granting `DBA` to fix `ORA-01031` | Excessive privilege exposure | Grant exact object/system privileges |
| Skipping pool drain post-deploy | Old sessions retain stale state/driver behavior | Drain/recycle connections cleanly |
| Running only unit tests | Misses Oracle driver/database semantics | Run integration and end-to-end tests |
| Skipping pre-upgrade baseline | Cannot tell what changed | Capture baselines pre-upgrade |
| Rolling back via app binary swap alone | Database/schema may not be backward-compatible | Use rollback matrices and restore plans |

## 22. Go/No-Go Checklist

### Database
- Right version/RU and PDB/service.
- Registry and SQL patch statuses clean.
- Zero invalid objects outside accepted exceptions.
- Alert log free of unresolved errors.
- Indexes/partitions/statistics verified.
- Backup/restore and rollback plans confirmed.

### SQL Plans
- Critical SQL has before/after baselines.
- Zero regressions beyond thresholds.
- Representative bind values tested.
- Actual rows/cardinality and I/O reviewed.
- SQL Plan Baselines/mitigations managed if needed.

### Drivers and Pools
- JDK/JDBC/pool/ORM match compatibility matrices.
- Runtime driver versions verified.
- TLS/wallet/authentication succeed.
- Bind/fetch/LOB/batch/procedure tests pass.
- Pool health and stale connection recovery pass.
- Session state resets properly.

### Timezones
- `DBTIMEZONE` and `SESSIONTIMEZONE` recorded.
- Timezone file version verified.
- JVM timezone/tzdata verified.
- DST boundaries and region mappings tested.
- Java/JDBC/ORM mappings preserve semantics.

### Privileges
- Runtime principal and PDB confirmed.
- Object/system privileges and roles reconciled.
- Definer-rights packages hold required direct grants.
- Synonyms, sequences, jobs, DB links, and ACLs work.
- Zero unnecessary elevated privileges.

### Applications
- Startup/readiness checks pass.
- Repository and transaction tests pass.
- API business flows pass.
- Batches/schedulers/message consumers pass.
- Latency/throughput meet SLAs.
- Logs, alerts, and rollback readiness confirmed.

## 23. Self-Check Questions

**Question 1.** Why is a pre-upgrade baseline needed?

**Answer:** To compare plans, latency, privileges, timezones, and application behavior, pinpointing real regressions instead of guessing causes.

**Question 2.** Is a changed plan hash always an error?

**Answer:** No. Compare operations, actual rows, I/O, latency, and workloads before and after.

**Question 3.** Why test multiple bind values?

**Answer:** Selectivity and data skew can make the optimizer choose different plans for the same SQL.

**Question 4.** What does `DBMS_XPLAN.DISPLAY_CURSOR` provide?

**Answer:** Displays a cursor's execution plan along with runtime statistics and predicates when collected.

**Question 5.** Why avoid arbitrarily gathering statistics across an entire schema?

**Answer:** Fresh statistics can shift plans across many SQL statements, causing unverified regressions.

**Question 6.** What must the JDBC driver be verified against?

**Answer:** Database release/RU, JDK, JDBC API level, pool/UCP, ORM, TLS/wallets, and authentication.

**Question 7.** Why is testing in SQL Developer insufficient?

**Answer:** SQL Developer uses a different driver, runtime, and configuration than production Java applications.

**Question 8.** Are `DBTIMEZONE` and `SESSIONTIMEZONE` the same?

**Answer:** No. They represent two separate timezone layers and can hold different values.

**Question 9.** Why test DST transitions?

**Answer:** Timezone region rules shift by calendar; timestamps near DST transitions may be interpreted differently if timezone data changes.

**Question 10.** Why does `TIMESTAMP WITH LOCAL TIME ZONE` display differently across two sessions?

**Answer:** Values normalize to the database time zone on write and display in each session's time zone on read.

**Question 11.** Why can a definer-rights package fail even when the user can `SELECT` the table?

**Answer:** Static SQL inside definer-rights units requires direct privileges for the owner; role-granted privileges do not apply under Oracle rules.

**Question 12.** How do you verify permissions accurately?

**Answer:** Inspect the session principal, container, role/system/object grants, and run tests using the actual runtime account.

**Question 13.** Why drain/recycle connection pools after deployment?

**Answer:** To clear old sessions, ensure new connections use the deployed driver/configuration, and eliminate stale session state.

**Question 14.** Is an HTTP 200 API test sufficient for sign-off?

**Answer:** No. Verify data integrity, transactions, side effects, latency, privileges, and full business workflows.

**Question 15.** When should you use a canary rollout?

**Answer:** When a subset of workload/instances can be isolated to verify live behavior before scaling out the rollout.

**Question 16.** Why can't you always roll back via database downgrade?

**Answer:** Downgrades are supported only for specific upgrade paths and conditions; rely on the upgrade guide, backups, and verified rollback plans.

## 24. Conclusion

Post-upgrade verification in Oracle must cover the database, SQL optimizer, JDBC drivers, timezones, privileges, and applications. An `OPEN` database and `SELECT 1 FROM dual` prove only basic connectivity. They do not prove critical SQL retains performance, Java mappings preserve data, session timezones match, stored procedures retain privileges, or business transactions work.

Capture pre-upgrade baselines, and verify release/RU, PDBs, registry, invalid objects, statistics, and indexes post-upgrade. Compare execution plans alongside actual rows, buffer gets, and latency across diverse bind value sets. Verify JDBC/JDK/ORM/pool versions against compatibility matrices and test with actual runtime artifacts. Inspect DB/session/JVM timezones, timezone files, and DST transitions separately. Verify privileges using the true runtime principal inside the target PDB, especially direct grants for definer-rights PL/SQL.

Finally, run regression and end-to-end flows through real datasources/pools—including transactions, batches, schedulers, LOBs, procedures, and integrations. Establish go/no-go criteria before rollout, monitor canaries, archive evidence, and keep rollback or forward-fix plans ready. Sign off only when data, privileges, timestamps, plans, and SLAs all pass on representative workloads.
