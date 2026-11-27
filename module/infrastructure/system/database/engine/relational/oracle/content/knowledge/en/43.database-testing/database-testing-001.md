# Selecting Oracle Release, Edition, and Compatibility Parameters for the Test Suite

When building a test suite for an Oracle application, choosing the right database version and test configuration directly determines the reliability of the results. A test suite that passes on Oracle Database Free or a latest Enterprise Edition release does not necessarily prove that the application will work properly in a production environment running a different release, Release Update (RU), edition, and parameter set.

In the testing topic for Database Engine Relational Oracle, database configuration should be treated as part of the test conditions. Identify the target release and edition, record the patch level, compatibility parameters, NLS configuration, CDB/PDB architecture, and related options. Then build a test matrix that reflects the deployment environment and the changes the system is about to undergo.

## 1. Distinguishing release, edition, patch level, and compatibility

The following concepts are related but not interchangeable:

| Concept | Illustrative example | Significance for testing |
|---|---|---|
| Database release | Oracle Database 19c, 21c, or 23ai | Determines the product family, behavior, and feature set by release |
| Edition | Enterprise Edition, Standard Edition 2, Express Edition, or Oracle Database Free | Determines the feature set and limits by edition |
| Patch level | Applied Release Update (RU), one-off patches, and SQL patches | Determines the exact fix level and behavior of the running database |
| `COMPATIBLE` | A version value supported by the installed release | Controls the compatibility level of database structures and the ability to use certain features |
| `OPTIMIZER_FEATURES_ENABLE` | Value corresponding to an optimizer release | Controls the optimizer behavior set by release to test execution plans |
| Database configuration | CDB/PDB, character set, timezone file, NLS, and initialization parameters | Affects data, statements, sessions, and test results |

**Release is not edition.** Two servers can both run Oracle Database 19c, yet one is Enterprise Edition and the other is Standard Edition 2. They can differ in supported features, limits, and licensing terms.

**Edition is not patch level.** Two databases both running Enterprise Edition can still run two different RUs. A bug fixed in a newer RU may still occur in an environment running an older RU.

**`COMPATIBLE` is not the software version.** A database can run the binaries of a new release while keeping `COMPATIBLE` at a lower value to defer using new formats or features. Do not use this parameter alone to conclude the actual release of the server.

**`OPTIMIZER_FEATURES_ENABLE` is also not `COMPATIBLE`.** This optimizer parameter controls query optimization behavior; it does not revert the data dictionary or database file formats to an older release.

## 2. Selecting the Oracle release as the baseline for the test suite

### 2.1. Start from the deployment environment

If the test suite serves an operating application, the production release is the primary benchmark. Collect at least:

- Installed Oracle Database release and full version.
- Database edition.
- Applied RU, one-off patches, and SQL patches.
- Operating system, hardware architecture, and deployment model (physical server, virtual machine, container, or cloud service).
- CDB/PDB configuration and how the application connects to the service.
- Character set, NCHAR character set, timezone file, and NLS settings.
- Client/driver version used by the application, such as JDBC, OCI, or ODP.NET.
- Initialization parameters that affect SQL, memory, concurrency, and application features.

If production does not exist yet, identify the lowest release the product commits to supporting. This is a critical benchmark for compatibility testing. An application declared to support multiple releases should be tested on each release in the support matrix, or at least on representative milestones approved by the product team.

Do not select a release just because it is the latest image a CI tool can download. A newer release can change optimizer behavior, reject legacy syntax, alter defaults, or no longer provide an edition the project uses. Before deciding, verify the support lifecycle, certified platforms, and application requirements.

### 2.2. Match RU and patches

The same release name does not guarantee identical behavior between two databases. An RU can contain fixes for the optimizer, SQL engine, PL/SQL, security, and other components. A one-off patch can fix a specific bug not yet included in the standard RU.

For regression testing, use the same RU and critical patches as production. When testing before an upgrade, create an additional environment running the target RU to compare results before and after the change. Record the patch inventory so others can reproduce the environment.

You can check SQL patch history using the following query on releases that provide this view:

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

This view records SQL patch operations applied inside the database. To fully confirm binary patches and one-off patches in the Oracle Home, the operations team also needs to save the patch tool inventory output on the server. Do not infer the entire patch level solely from the release name in the banner.

### 2.3. Match platform and data configuration

If the application will deploy on Linux but the test suite only runs on Windows, the results remain useful for SQL logic but are insufficient to verify behaviors dependent on the operating system, filesystem, file paths, permissions, or operational tooling.

Similarly, testing on a database with a different character set from production can miss character conversion, string length, and sorting bugs. For applications with multilingual data, use a character set and NCHAR character set close to the target environment. Also check the timezone file and datetime data involving daylight saving if business logic depends on local timestamps.

For applications running in a PDB, test through the exact service type and container that the application will use. Privileges, PDB-modifiable parameters, connection services, and resource manager configuration can make results differ from a test session in the CDB root.

## 3. Selecting the appropriate edition

The edition determines the feature set supported by the database and usage limits. Choose the edition based on the target environment and the features the application actually requires.

| Edition or distribution | When it may be appropriate | Points to verify |
|---|---|---|
| Enterprise Edition (EE) | Production or tests needing to simulate Enterprise features | Verify entitlement for options and management packs; do not assume every feature is included in the base license |
| Standard Edition 2 (SE2) | Systems deployed within the feature scope and limits of SE2 | Verify that the release provides this edition, hardware limits, and restricted features per release documentation |
| Express Edition (XE) | Certain tutorials, local experiments, or basic tests on releases where XE is available | Has resource and feature limits; do not use results to replace testing on the production edition if differences exist |
| Oracle Database Free | Learning, development, and testing within the Free license terms | Verify resource limits, features, platforms, and release; do not assume Free is equivalent to EE or SE2 |

Edition names, scopes, and availability vary by release and distribution method. Not every edition exists on every release, operating system, or cloud service. Before building the matrix, verify that the edition can actually be installed and is supported for the target platform.

### 3.1. Do not treat Free/XE results as sufficient evidence for EE or SE2

Free or XE is useful for fast development cycles, testing SQL logic, and local experiments. However, they may impose limits on CPU, memory, data storage, features, and configuration. A test passing on Free does not prove that a query will produce the same plan or that the application will behave the same on Enterprise Edition.

If production runs SE2, perform at least one test pass on SE2 to detect usage of features unsupported by that edition. If production runs EE and the application depends on an EE feature or option, test on the corresponding EE configuration. For features requiring separate licenses, confirm entitlement before introducing them into the test environment.

### 3.2. Distinguish features present in binaries from usage entitlement

Some views can indicate whether an option or component is present in the installation. For example, `V$OPTION` reflects information about options installed in the database. This result is not proof that the organization has purchased or has the right to use that option.

Features and packs such as Partitioning, Advanced Compression, Real Application Clusters, Active Data Guard, Diagnostics Pack, or Tuning Pack have specific support and licensing conditions depending on the release, product, and contract. Do not enable a feature simply because it appears in a UI or system view. The project team must cross-check current licensing documentation and contracts before using them in production or test.

`DBA_FEATURE_USAGE_STATISTICS` can help inventory the usage of certain features, but it does not replace entitlement verification. Whether a feature is reported as used, unused, or installed does not by itself determine licensing status.

For cloud databases, check both the edition/service tier and the billing model: license included or Bring Your Own License (BYOL). A test environment provisioned on a different cloud service may have different entitlements and limits than an on-premises database.

## 4. Understanding the COMPATIBLE parameter properly

### 4.1. Role of COMPATIBLE

`COMPATIBLE` is an initialization parameter that controls the database's compatibility level with an Oracle version. It affects whether the database can use certain features and storage structures introduced in a new release. This value helps administrators control when the database begins relying on changes that could impact downgrade capability.

This parameter does not turn the database binaries into an older release. Nor does it guarantee that every SQL statement, execution plan, PL/SQL package, or application will behave identically to an older release. To test application compatibility, you still need to run the test suite on the actual release and configuration.

### 4.2. Choosing a value for the test environment

Do not copy a `COMPATIBLE` value from an online example and apply it to every system. Valid values depend on the installed release, upgrade history, compatibility requirements, and Oracle documentation for that version.

For production regression testing, use the current value of the production environment as the baseline. When preparing an upgrade, create a separate test branch to evaluate the planned post-upgrade `COMPATIBLE` value. Only raise the value when the target release supports it, upgrade steps are complete, and the operations team accepts the consequences for the downgrade plan.

`COMPATIBLE` is a static parameter: changing the value takes effect when the database restarts. Example syntax for changing it in the SPFILE:

```sql
ALTER SYSTEM SET compatible = '<approved_value>'
  SCOPE = SPFILE;
```

The value in the example is a placeholder, not a configuration value to copy verbatim. Before making the change, confirm the value is supported by the release and that the restart procedure is scheduled.

### 4.3. Why caution is required when increasing COMPATIBLE

When `COMPATIBLE` is raised, the database can start using new structures or features. Once it relies on those structures, lowering the value back to an older level may not be supported. Reverting to an older release may require a prepared restore or migration plan instead of merely changing the parameter back.

Therefore:

- Do not increase `COMPATIBLE` just to make the number match the new release.
- Do not use a test database with an already increased `COMPATIBLE` to simulate a production environment that still keeps a lower value.
- Test the upgrade on a recoverable clone, then run application tests and downgrade/restore tests following supported procedures.
- Record the values before and after the change along with the timestamp, operator, reason, and test results.

If the goal is to verify whether the application runs on a new release, create a new database or clone suitable for the target release and configure `COMPATIBLE` according to the upgrade plan. Never alter this parameter on production solely for a test.

## 5. Compatibility parameters and parameters affecting test results

### 5.1. OPTIMIZER_FEATURES_ENABLE

`OPTIMIZER_FEATURES_ENABLE` controls the optimizer feature set corresponding to an Oracle release. It is commonly used to assess the impact of optimizer changes during an upgrade. For instance, the team can compare execution plans under the current optimizer configuration versus the target release configuration in a controlled test environment.

This parameter does not replace testing on the target release and does not turn a new database into an old database. Results also depend on statistics, bind variables, data, schema, indexes, system statistics, other parameters, and cache state. If you alter the parameter at the session or system level for an A/B run, record the value and restore it properly after the test.

When performance testing, save the SQL text, bind values, execution plan, estimated and actual cardinalities, elapsed time, logical reads, physical reads, and cache state. Compare on the same dataset and execution conditions to avoid false conclusions caused by environment differences.

### 5.2. Parameters affecting data semantics

Several parameters can alter results or how the application interprets data:

| Parameter or setting | Effect to test |
|---|---|
| `NLS_CHARACTERSET` | Character storage and conversion capability in the database |
| `NLS_NCHAR_CHARACTERSET` | NCHAR, NVARCHAR2, and NCLOB data types |
| `NLS_LENGTH_SEMANTICS` | How CHAR/VARCHAR2 lengths are declared in BYTE or CHAR when creating objects |
| `NLS_COMP`, `NLS_SORT` | String comparison and sorting in NLS-affected contexts |
| `NLS_DATE_FORMAT`, `NLS_TIMESTAMP_FORMAT` | Date/time representation and conversion if the application relies on implicit conversion |
| `TIME_ZONE` and timezone file | Conversion of timestamps with time zones and local time rules |
| `MAX_STRING_SIZE` | SQL string type limits and configuration migration requirements |
| Client character set | Data conversion between application, driver, and database |

Applications should use strongly typed bind variables and explicit date/time conversions instead of relying on default session formats. Even so, the test suite must still record NLS settings to detect environment discrepancies and test legacy code relying on implicit conversion.

`MAX_STRING_SIZE` requires special handling. Switching from `STANDARD` to `EXTENDED` has specific prerequisites and conversion steps, affecting compatibility and rollback plans. Do not change this parameter arbitrarily in a shared test pipeline; provision an isolated environment and follow the exact supported procedure for that release.

### 5.3. Parameters affecting load and resources

Parameters such as `PROCESSES`, `SESSIONS`, `OPEN_CURSORS`, `SGA_TARGET`, `PGA_AGGREGATE_TARGET`, `MEMORY_TARGET`, `UNDO_RETENTION`, `PARALLEL_DEGREE_POLICY`, and `STATISTICS_LEVEL` can affect load capacity, concurrency, memory, runtime, or how metrics are collected.

You do not need to copy every production value into a small test environment. However, you must understand which differences can skew conclusions. For example, concurrency testing on a database allowing only a few sessions will not reflect production load; performance testing on a machine with significantly more memory can mask resource bottlenecks.

For functional testing, prioritize a stable configuration with sufficient resources for reproducible test results. For load testing, clearly define targets, concurrent load, session limits, memory, and I/O. Record actual limits rather than just saving parameter values.

### 5.4. Distinguishing system, PDB, and session parameters

Some parameters can be modified at the system level, while others can be set specifically at the PDB or session level; scope and modifiability depend on the parameter and release. When an application connects via a service to a PDB, verify the values that the session actually sees.

Do not simply read an init parameter file and conclude that every session uses that value. SPFILE, runtime values, PDB parameters, session parameters, and settings configured by the connection pool can all differ. The test suite must record the configuration at the exact container and session used by the application.

## 6. Collecting database configuration before running tests

### 6.1. Check release and edition

The following query displays the database banner:

```sql
SELECT banner
FROM v$version
ORDER BY banner;
```

The banner typically shows the release and edition in the product description string. You can view additional component details:

```sql
SELECT product, version, status
FROM product_component_version
ORDER BY product;
```

Save the verbatim output along with the Oracle Home details and patch inventory provided by the operations team. Do not infer the edition solely from the SQL client version or service name.

### 6.2. Check active parameters

The following example retrieves a set of parameters commonly needing capture:

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
  'max_string_size',
  'processes',
  'sessions',
  'open_cursors',
  'parallel_degree_policy'
)
ORDER BY name;
```

These columns show current values and partial information about parameter modifiability. Querying dynamic views may require appropriate data dictionary privileges. In a multitenant environment, run the query in the appropriate container or also inspect the corresponding CDB-level views as permitted.

### 6.3. Check NLS

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
  'NLS_CHARACTERSET',
  'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;

SELECT name, value
FROM v$parameter
WHERE name = 'nls_length_semantics';

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
  'NLS_DATE_FORMAT',
  'NLS_TIMESTAMP_FORMAT',
  'NLS_COMP',
  'NLS_SORT',
  'NLS_LANGUAGE',
  'NLS_TERRITORY'
)
ORDER BY parameter;
```

The first query records the database-level character sets, the second records the default `NLS_LENGTH_SEMANTICS`, and the third records the NLS settings of the current session. Session results are critical when the application uses a connection pool because each connection may be initialized or configured differently.

### 6.4. Record container and service

In a multitenant environment, you can inspect the current container:

```sql
SELECT sys_context('USERENV', 'DB_NAME')       AS db_name,
       sys_context('USERENV', 'CON_NAME')       AS container_name,
       sys_context('USERENV', 'SERVICE_NAME')   AS service_name,
       sys_context('USERENV', 'INSTANCE_NAME')  AS instance_name
FROM dual;
```

Save this output with the test logs to identify which database, PDB, service, and instance the test ran against. With RAC or multi-service environments, check connection distribution and configuration consistency across instances.

## 7. Designing a test matrix by objective

Not every test run requires building the full combination of release, edition, and parameters. Group them by risk and objective.

| Objective | Priority configuration | What needs to be proven |
|---|---|---|
| Frequent functional testing | Release, edition, RU, and settings close to production | Core business flows and SQL work on the target environment |
| Multi-release compatibility | Each release within the supported scope | No syntax, data types, or features exceeding the supported baseline are used |
| Edition testing | Production edition and a more restricted edition if supported by the product | The application does not depend on unlicensed or unsupported features |
| Upgrade testing | Source clone and target release environment | Data, schema, PL/SQL, jobs, and application work after the upgrade |
| COMPATIBLE change testing | Recoverable clone, aligned with upgrade plan | New features, operability, and recovery plan are verified |
| Optimizer testing | Same release and data, comparing optimizer configurations | Execution plans and performance change within acceptable thresholds |
| Load testing | Defined resource and concurrency configuration | Database meets load, latency, and resource targets |

A sample matrix for an application running on a production release:

| Environment | Release/edition | RU | COMPATIBLE | Purpose |
|---|---|---|---|---|
| Fast CI | Free edition or approved test edition | Locked patch level | Valid configuration per distribution | Fast feedback for basic unit/integration tests |
| Regression | Same release and edition as production | Same RU as production | Equal to production | Confirm current behavior |
| Upgrade candidate | Planned deployment release and edition | Target RU | Planned post-upgrade value | Detect compatibility bugs before release |
| Edition boundary | More restricted edition, if within product support scope | Locked patch | Valid for release | Detect edition feature dependencies |

This is a reference structure, not a requirement to maintain four physical databases. You can use database clones, isolated PDBs, or ephemeral environments if that approach satisfies data isolation and reproducibility requirements. Do not share a single PDB across tests that can mutate each other's parameters, schemas, or data.

## 8. Process for provisioning and locking the test environment

### Step 1: Define support scope

Document the minimum release, production release, and planned target release. Specify the edition, platform, deployment type, and application driver. If the product supports multiple configurations, explicitly state which configurations are mandatory and which are supplementary tests.

### Step 2: Select edition and verify usage entitlement

Select the edition based on the features the application needs and the deployment environment. Check options, packs, and cloud service terms if applicable. Include the verification result in the environment record so developers do not inadvertently rely on an unapproved feature.

### Step 3: Lock release and patch level

Choose the specific release and RU. Save the banner, patch inventory, SQL patch history, Oracle Home, and platform. Do not automatically update images or Oracle Home between test runs without recording the change.

### Step 4: Configure COMPATIBLE and parameters

Use the production configuration as the baseline when the goal is regression. For upgrade environments, use the approved configuration for the target release. Save optimizer, NLS, memory, concurrency, and application-specific parameters. Changes that can affect downgrade capability or data structures must be controlled separately.

### Step 5: Standardize data and schema

Use the same version of DDL, PL/SQL, indexes, constraints, statistics, and test data when comparing two configurations. For upgrade testing, create a representative data copy, including boundary data and near-realistic volume. Anonymize sensitive data according to organizational policy.

### Step 6: Run tests and archive evidence

Save test results, connection logs, database configuration, Oracle errors, execution plans, and required performance metrics. Tag each result with an environment ID or configuration ID so the exact release, edition, patch, and parameters used can be traced.

### Step 7: Clean up and recreate

After testing, destroy ephemeral environments or restore from snapshots according to defined procedures. For tests requiring data retention for investigation, keep the clone and related configuration for an approved retention period. Do not let an environment whose `COMPATIBLE`, `MAX_STRING_SIZE`, or schema was modified become a shared baseline without updating the record.

## 9. Testing release upgrades and parameter changes

Upgrade testing must isolate changes so the root cause can be identified when failures occur:

1. Run the test suite on the source release with the current configuration and save the baseline.
2. Clone the source database to obtain equivalent data and schema.
3. Upgrade the clone using the supported procedure for the target release.
4. Record edition, RU, SQL patches, `COMPATIBLE`, NLS, timezone file, and post-upgrade parameters.
5. Run checks for database components, invalid objects, jobs, database links, privileges, and connection services.
6. Re-run the same functional test suite and compare results.
7. Run performance tests with comparable data, bind values, and load conditions.
8. Test backup/restore or downgrade procedures in a separate environment if required by the release plan.

Do not change release, edition, RU, `COMPATIBLE`, `OPTIMIZER_FEATURES_ENABLE`, and data simultaneously and only compare the final outcome. When multiple variables change at once, it is very hard to isolate the factor causing discrepancies. Use separate test branches to evaluate individual changes and a combined verification pass after each impact is understood.

If tests fail, categorize before fixing:

- Incompatibility errors in syntax, packages, data types, or features.
- Errors caused by missing edition or option in the environment.
- Errors caused by patch level or release regression.
- Errors caused by optimizer parameters, statistics, or execution plans.
- Errors caused by NLS, character set, timezone, or implicit conversion.
- Errors caused by privileges, PDB/service configuration, resources, or OS differences.
- Errors caused by non-equivalent test data or mutated environment state.

## 10. Common mistakes

| Mistake | Consequence | Mitigation |
|---|---|---|
| Recording only "Oracle 19c" without edition and RU | Impossible to reproduce the exact environment | Save release, edition, patch inventory, and SQL patch history |
| Using Free/XE as the sole environment for an EE production app | Misses features, limits, or optimizer differences | Add testing on the production edition or an equivalently configured environment |
| Assuming `V$OPTION` proves a license exists | Risk of using unlicensed options | Cross-check licensing guide and contracts |
| Increasing `COMPATIBLE` to "match" the new release | May lose ability to revert to the previous state | Perform on a clone according to upgrade and restore plans |
| Using `OPTIMIZER_FEATURES_ENABLE` to simulate an entire older release | Ignores engine, data dictionary, and feature differences | Test directly on the target release |
| Failing to record NLS and timezone | Results depend on session or server settings | Capture database/session NLS and timezone |
| Running tests on auto-updating images | Results fluctuate across runs | Lock image, RU, and patch inventory |
| Sharing a database across destructive tests | Tests interfere with each other | Isolate by schema, PDB, or separate database depending on risk level |
| Comparing performance with different data or statistics | Unreliable optimizer conclusions | Standardize data, statistics, bind values, and load |

## 11. Checklist before accepting test results

- [ ] Target release and product-supported release scope identified.
- [ ] Edition recorded and entitled options/packs verified.
- [ ] Required RU, one-off patches, and SQL patches locked.
- [ ] `COMPATIBLE` recorded and confirmed to align with the upgrade plan.
- [ ] `OPTIMIZER_FEATURES_ENABLE` and related optimizer parameters recorded.
- [ ] Character set, NCHAR character set, NLS, and timezone verified.
- [ ] Actual CDB/PDB, service, and instance connected by the application confirmed.
- [ ] Driver/client version and connection pool configuration recorded.
- [ ] Resource differences between test and production environments identified.
- [ ] Schema, data, statistics, and execution conditions standardized when comparing.
- [ ] Configuration logs saved alongside test results for reproducibility.
- [ ] Clone, backup/restore, or recovery plan prepared for upgrade tests and high-risk parameter changes.

## 12. Practical selection principles

For regular testing, use a version-locked environment as close to production as possible. If fast runs using Oracle Database Free or XE are needed, treat them as an early feedback layer and still maintain a regression pass on the target edition. When testing upgrades, provision a dedicated clone for the target release and manage `COMPATIBLE` according to the approved plan. When testing performance, freeze RU, data, statistics, bind values, and optimizer parameters so comparisons are meaningful.

A test result is only valid within the scope of the configuration on which it ran. Clearly documenting release, edition, patch level, `COMPATIBLE`, key parameters, NLS, container/service, and driver helps the team know precisely what has been proven while avoiding overgeneralizing compatibility conclusions for the Oracle application from a different environment.
