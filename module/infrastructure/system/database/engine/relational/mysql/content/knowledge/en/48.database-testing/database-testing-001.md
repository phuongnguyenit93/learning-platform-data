# Choosing a Version, Storage Engine, and Configuration Matching the Target Environment

A MySQL test is only reliable when the database used for testing shares the important characteristics of the environment where the application will run. A test suite can pass on a developer's machine yet fail in production due to differences in MySQL version, storage engine, collation, SQL mode, transaction isolation, plugins, or resource configuration.

The goal is not always to replicate all of production. You need to identify the factors that can alter SQL results, consistency, performance, or connectivity, and then build a test environment close enough to the target. When investigating a specific bug, reproduce the exact patch version, engine, configuration, and data characteristics that produced it.

## 1. Why Does MySQL Environment Parity Matter?

Different environments can yield different results even when running the same SQL statement:

- A newer MySQL version may change supported syntax, default SQL modes, the optimizer, or feature behavior.
- `InnoDB` and `MyISAM` behave differently regarding transactions, locking, crash recovery, and foreign keys.
- Different collations can produce different results for string comparisons, `ORDER BY`, and unique indexes.
- `ONLY_FULL_GROUP_BY` or strict SQL modes can cause queries or data to be rejected.
- Different session time zones can cause `TIMESTAMP` values to display or be interpreted differently.
- Transaction isolation and durability settings can affect concurrency, deadlocks, and crash outcomes.
- Differences in memory, disk, and connection pool configuration can hide timeouts or alter execution plans.

For example, tests using in-memory H2 may accept SQL syntax or expressions that MySQL does not support. Even when using MySQL in a container, testing with the `mysql:latest` tag may run on a newer version than production and change over time. Therefore, the test database must be pinned to a specific version and a reproducible configuration.

## 2. Layers to Compare

Inspect the environment layer by layer, from the server down to schema and data:

| Layer | Information to compare | Why it affects tests |
|---|---|---|
| Server binary | MySQL version, patch, edition/distribution, OS, CPU architecture | Determines features, bug fixes, optimizer behavior, and compatibility. |
| Storage engine | Default engine and actual engine per table | Determines transactions, locking, foreign keys, crash recovery, and indexes. |
| Schema | Data types, charset, collation, indexes, constraints, partitions | Determines how data is stored, compared, validated, and queried. |
| Session | `sql_mode`, `time_zone`, isolation level, character set | Can differ across connections within the same server. |
| Server configuration | Buffer pool, redo/binlog, max connections, temporary tables, optimizer | Affects load, durability, execution plans, and limits. |
| Plugin/security | Authentication plugin, components, UDFs, TLS, accounts/grants | Affects login, privileges, and plugin-dependent features. |
| Topology | Binary log, GTID, replication, Group Replication, Router | Necessary for testing failover, replication, and read/write routing. |
| Runtime resources | CPU, RAM, disk type/latency, filesystem, container limits | Affects latency, concurrency, and behavior under resource exhaustion. |
| Data shape | Row count, cardinality, data distribution, edge-case data | Affects the optimizer, index selectivity, and business code paths. |

Not every test needs replication or production-scale data. Build a parity checklist based on your testing goals instead of assuming every test must spin up a full production cluster.

## 3. Choosing the Right MySQL Version

### Pin the Patch Version

Record the exact version on the target environment:

```sql
SELECT
    VERSION() AS mysql_version,
    @@version_comment AS distribution,
    @@version_compile_os AS compile_os,
    @@version_compile_machine AS compile_machine;
```

For example, if production runs MySQL `8.4.x`, pre-release tests should use the exact patch version running in production or the approved target patch version. When investigating a bug, prioritize reproducing the exact patch version where the bug occurred. Do not use the `latest` tag for tests requiring reproducibility.

Container tags should be explicitly pinned:

```text
mysql:8.4.4
```

The tag above is only an illustrative example. Replace it with the actual patch version of your target environment. If you need to test an upgrade path, create an additional job that runs the source and target versions for comparison; do not replace tests on the current production version with an arbitrary newer version.

### Patch, Minor, and Major Versions

- **Patch release** typically contains bug fixes and security fixes within the same release series. Some changes can still affect behavior, so verify the exact patch when reproducing an incident.
- **Minor release** in modern MySQL lines may add features, change the optimizer, or alter defaults; check the release notes and compatibility.
- **Major release** may change internal formats, data dictionary, plugins, syntax, or upgrade procedures; dedicated upgrade testing is required.

Do not assume compatibility merely because both servers report `8.x`. Record the full version, distribution, and OS architecture.

### Version Matrix Testing

A project may require several types of jobs:

| Job | Database version | Purpose |
|---|---|---|
| Pull request | Project's standard patch version | Fast, stable feedback for code changes. |
| Compatibility | Minimum supported version | Detect usage of syntax or features that are too new. |
| Pre-release | Planned target deployment version | Validate before upgrading production. |
| Upgrade test | Source version then upgraded to target | Verify data and application work after upgrade. |
| Incident reproduction | Exact patch/version where the bug occurred | Reproduce and verify the fix. |

Keep the matrix bounded reasonably. You do not need to run every combination of version × OS × engine × config on every pull request; you can run fast smoke tests on every commit and deeper tests on a schedule or before releases.

## 4. Checking the Storage Engine

The storage engine determines how MySQL stores and processes each table's data. A single server can have multiple tables using different engines, so do not check only the default engine.

List engines supported by the server:

```sql
SHOW ENGINES;
```

Check the default engine:

```sql
SHOW VARIABLES LIKE 'default_storage_engine';
```

Inventory the engines of existing tables:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    ROW_FORMAT,
    TABLE_COLLATION
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA NOT IN (
      'mysql', 'sys', 'performance_schema', 'information_schema'
  )
ORDER BY TABLE_SCHEMA, TABLE_NAME;
```

For typical transactional applications, `InnoDB` is the standard choice and the default engine in modern MySQL. InnoDB supports transactions, row-level locking, foreign keys, crash recovery, and MVCC. If production uses InnoDB, tests for transactional workflows also need InnoDB to properly test commit/rollback, deadlocks, and constraints.

Key differences include:

| Engine | Characteristics | What to test |
|---|---|---|
| `InnoDB` | Transactional, MVCC, row-level locking, foreign keys, and crash recovery | Isolation, deadlocks, rollback, foreign keys, redo/undo, and durability. |
| `MyISAM` | No transaction or foreign key support; table-level locking | Do not use InnoDB tests to infer MyISAM behavior. Test table locks and failure consequences. |
| `MEMORY` | Data resides in memory and is lost on server restart; supports specific index types | Test size limits, data types, and data lifecycle. |
| `NDB` | Distributed engine for MySQL Cluster with its own architecture and limits | Requires a real NDB environment; an InnoDB container cannot substitute. |

If tests use temporary or staging tables with a different engine from production, document the reason clearly. Do not rely on `default_storage_engine` to assume all tables use the same engine.

Inspect the DDL of critical tables:

```sql
SHOW CREATE TABLE appdb.orders;
SHOW CREATE TABLE appdb.order_items;
```

DDL is where you verify the actual engine, charset, collation, indexes, constraints, partitions, and defaults. Compare the DDL in test against production or the planned migrations.

## 5. Collecting Server-Level and Session-Level MySQL Configuration

Some variables have both global and session scopes. An administrative connection might observe the global value, while the application runs with a different session value due to the driver or connection initialization.

View global variables:

```sql
SHOW GLOBAL VARIABLES;
```

View variables for the current connection:

```sql
SHOW SESSION VARIABLES;
```

You do not need to save all thousands of variables for every test. Filter the groups that directly affect the application:

```sql
SHOW GLOBAL VARIABLES LIKE 'character_set%';
SHOW GLOBAL VARIABLES LIKE 'collation%';
SHOW GLOBAL VARIABLES LIKE 'sql_mode';
SHOW GLOBAL VARIABLES LIKE 'time_zone';
SHOW GLOBAL VARIABLES LIKE 'transaction_isolation';
SHOW GLOBAL VARIABLES LIKE 'default_storage_engine';
SHOW GLOBAL VARIABLES LIKE 'lower_case_table_names';
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
SHOW GLOBAL VARIABLES LIKE 'tmp_table_size';
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW GLOBAL VARIABLES LIKE 'sync_binlog';
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
SHOW GLOBAL VARIABLES LIKE 'optimizer_switch';
```

Check the session of the application connection itself:

```sql
SELECT
    @@SESSION.sql_mode AS session_sql_mode,
    @@SESSION.time_zone AS session_time_zone,
    @@SESSION.character_set_client AS client_charset,
    @@SESSION.character_set_connection AS connection_charset,
    @@SESSION.character_set_results AS result_charset,
    @@SESSION.collation_connection AS connection_collation;

-- MySQL 8.0+: transaction_isolation
SHOW SESSION VARIABLES LIKE 'transaction_isolation';
-- MySQL 5.7: tx_isolation
SHOW SESSION VARIABLES LIKE 'tx_isolation';
```

Variable names and scopes can change across versions. If a variable does not exist on the MySQL version in use, check `SHOW VARIABLES LIKE 'pattern'` and the documentation for that exact version; do not let a shared inventory query break tests merely because a variable was renamed or removed.

## 6. Settings That Easily Make Test Differ From Production

### Character Set and Collation

Check server defaults:

```sql
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
```

Check databases, tables, and columns because they can override server defaults:

```sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME = 'appdb';

SELECT
    TABLE_NAME,
    TABLE_COLLATION
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_TYPE = 'BASE TABLE';
```

Collation affects `WHERE`, `JOIN`, `GROUP BY`, `ORDER BY`, and unique keys. Tests need accented characters, mixed case, Unicode characters, and near-duplicate values to catch differences. Do not only verify that the charset is `utf8mb4`; two different `utf8mb4` collations can still yield different comparison results.

### SQL Mode

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
```

`STRICT_TRANS_TABLES`, `ONLY_FULL_GROUP_BY`, `NO_ZERO_DATE`, and other modes can alter whether data or queries are accepted. Tests must initialize the session like the application does, rather than checking only the global value. When a connection pool initializes sessions with custom statements, verify that those statements run on every new connection.

### Time Zone

```sql
SELECT
    @@GLOBAL.time_zone AS global_time_zone,
    @@SESSION.time_zone AS session_time_zone,
    @@system_time_zone AS system_time_zone,
    NOW() AS session_now,
    UTC_TIMESTAMP() AS utc_now;
```

Test `TIMESTAMP` and `DATETIME` with the proper time zone. `TIMESTAMP` is converted between the session time zone and UTC; `DATETIME` preserves the calendar value without automatic time zone conversion. If the application uses named zones like `Asia/Ho_Chi_Minh`, the corresponding time zone tables are required.

### Transaction Isolation and Durability

Check the isolation level and durability settings relevant to the workload:

```sql
SHOW GLOBAL VARIABLES LIKE 'transaction_isolation';
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW GLOBAL VARIABLES LIKE 'sync_binlog';
```

The isolation level affects snapshot visibility, locking, and concurrency. `innodb_flush_log_at_trx_commit` together with `sync_binlog` affect how MySQL flushes redo/binlogs and data durability on power loss or crash. A test run with relaxed durability settings may fail to catch issues that happen in production, or conversely exhibit very different latency.

Do not alter durability variables to speed up tests and then use those results as evidence for production. If you need performance tests with lighter settings, clearly distinguish functional logic tests from durability/performance tests.

### File Names and Table Names

`lower_case_table_names` affects how MySQL stores and compares database and table names. Its default values and restrictions depend on the operating system and filesystem; this variable must be configured before initializing the data directory and cannot be arbitrarily changed on an instance that already contains data.

If developers use Windows or macOS while production runs on Linux, table names differing in letter case may work on a developer machine but fail in production. Check:

```sql
SHOW VARIABLES LIKE 'lower_case_table_names';
```

Use consistent lowercase schema and table names and do not rely on the case-insensitive behavior of a specific operating system.

### Optimizer and Resources

Variables such as `optimizer_switch`, `innodb_buffer_pool_size`, `tmp_table_size`, `max_connections`, and `max_allowed_packet` can change execution plans or processing limits. Not every value has to match identically if the test machine is smaller than production, but you must know which differences could affect the outcome under test.

For performance tests, CPU, RAM, storage latency, filesystem, container limits, and data size all need to closely resemble production. A MySQL container running on a laptop cannot accurately represent production storage if disk performance, caching, and CPU limits differ substantially.

## 7. Spinning Up Test MySQL with Docker Using Fixed Tags

Docker makes it easy to spin up a database quickly and isolate it from any MySQL installed on the developer's machine. Example `compose.yaml`:

```yaml
services:
  mysql-test:
    image: mysql:${MYSQL_IMAGE_TAG}
    container_name: mysql-test
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: appdb
      MYSQL_USER: app_test
      MYSQL_PASSWORD: ${MYSQL_TEST_PASSWORD}
    ports:
      - "3307:3306"
    volumes:
      - mysql-test-data:/var/lib/mysql
      - ./mysql-test.cnf:/etc/mysql/conf.d/zz-test.cnf:ro
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "-uroot", "-p${MYSQL_ROOT_PASSWORD}"]
      interval: 5s
      timeout: 3s
      retries: 20

volumes:
  mysql-test-data:
```

An `.env` file for local environments—do not commit real secrets:

```dotenv
MYSQL_IMAGE_TAG=8.4.4
MYSQL_ROOT_PASSWORD=local-root-password
MYSQL_TEST_PASSWORD=local-test-password
```

Replace `8.4.4` with the verified target patch version. If you want to reset test data, delete the volume using a procedure dedicated to the local environment; removing the volume deletes all data inside that volume. Do not use production project names, volumes, or credentials for test configurations.

The `mysql-test.cnf` file can contain settings matching the test target:

```ini
[mysqld]
default_storage_engine = InnoDB
character_set_server = utf8mb4
collation_server = utf8mb4_0900_ai_ci
default-time-zone = '+00:00'
max_connections = 100
```

The values in the example must be replaced with your target configuration. In particular, `lower_case_table_names` must be decided before the data directory is initialized and must suit the platform; do not add or change this value on an already-created volume without rebuilding the environment. Across MySQL versions, a collation might not exist; verify before starting.

Start and verify:

```bash
docker compose up -d
docker compose ps
docker compose logs mysql-test
```

Connect on host port `3307`, then run the inventory queries from the sections above. Pinning the image tag ensures version reproducibility; for stricter control in pipelines, you can pin the image digest once the image is approved.

## 8. Using Testcontainers in Java Integration Tests

For Spring Boot applications, Testcontainers can start a real MySQL instance during tests and provide a dynamic JDBC URL. This reduces reliance on a database pre-installed on the developer's machine.

Example with JUnit 5 and the Testcontainers 1.x API:

```java
@Testcontainers
@SpringBootTest
class CustomerRepositoryIT {

    @Container
    static final MySQLContainer<?> MYSQL =
            new MySQLContainer<>("mysql:8.4.4")
                    .withDatabaseName("appdb")
                    .withUsername("app_test")
                    .withPassword("test-password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
    }

    @Test
    void savesAndReadsCustomer() {
        // Call the real repository and verify data in the MySQL container.
    }
}
```

The tag `mysql:8.4.4` is an example; replace it with the exact target patch version. Add the appropriate Testcontainers JUnit Jupiter and MySQL modules to your test dependencies. The package import for `MySQLContainer` changes across Testcontainers major versions; use the API/import matching the dependency version locked in the project.

By default, Testcontainers creates a new instance per test class/container lifecycle. If you use reusable containers or share a container for speed, avoid letting test data from an earlier case affect later cases. Use separate schemas/databases, transaction rollbacks, or explicit cleanup. Do not implicitly enable reuse in CI when you need a clean, reproducible environment.

### Configuring the MySQL Container to Match the Target

You can mount a MySQL config file or server flags appropriate for the Testcontainers API version in use. Once the container is ready, verify via SQL instead of assuming the configuration took effect. For example:

```java
try (Connection connection = DriverManager.getConnection(
        MYSQL.getJdbcUrl(), MYSQL.getUsername(), MYSQL.getPassword());
     Statement statement = connection.createStatement();
     ResultSet rs = statement.executeQuery("SELECT VERSION(), @@sql_mode, @@time_zone")) {

    if (rs.next()) {
        System.out.println("version=" + rs.getString(1));
        System.out.println("sql_mode=" + rs.getString(2));
        System.out.println("time_zone=" + rs.getString(3));
    }
}
```

In real tests, assert the expected version/config instead of only printing to the console. Do not log credentials or URLs containing passwords.

## 9. Test Data Must Match Both Structure and Distribution

An empty database can verify table-creation migrations, but it does not represent queries in production with millions of rows. Query plans depend on cardinality, histograms, selectivity, and data distribution.

A valuable test dataset should include:

- Scale close to the target for performance tests; at minimum, large enough to expose the scan/index paths being tested.
- Key distribution and data skew, such as one customer having far more orders than other customers.
- Null, empty, minimum/maximum values, and Unicode data.
- Groups with case or accent collisions if collation affects behavior.
- Records with parent-child relationships, foreign keys, and rare business states.
- Data that creates contention on hot rows when testing concurrency.
- Temporal data around day boundaries, time zones, and daylight-saving transitions if the domain uses time zones.

Do not copy production data containing personal information or secrets into test environments without proper protection processes. You can use synthetic data or masked data as long as it preserves the distribution, relationships, and cardinality needed for the test.

After loading large datasets, update statistics appropriately and run representative queries. `ANALYZE TABLE` can refresh optimizer statistics; use it intentionally and compare against production when reproducing execution plans.

## 10. Testing Engine and Configuration According to Purpose

Not every test needs to match production in every aspect. Tie parity requirements to the type of test:

| Test type | What must match production most closely |
|---|---|
| Unit tests for logic without DB access | Mocks/fakes can be used; MySQL is unnecessary if SQL is out of scope. |
| Repository/integration tests | MySQL version, engine, schema, collation, SQL mode, time zone, and Connector/J. |
| Transaction/concurrency tests | InnoDB, isolation level, lock behavior, connection count, and contention data. |
| Migration tests | Source/target versions, engine, DDL, collation, existing data, and migration privileges. |
| Replication/failover tests | Binary log, GTID, topology, server ID/UUID, Router, and network behavior. |
| Performance tests | Version, optimizer settings, data size/distribution, CPU, RAM, storage latency, and concurrency. |
| Backup/restore tests | Tool version, engine, encryption/keyring, binary log/GTID metadata, and storage. |

H2 or mocks can still be useful for fast unit tests. However, if a test verifies MySQL SQL, MySQL data types, locks, or migrations, there must be at least one integration test running on real MySQL.

## 11. Generating Automated Parity Reports

You can save source/target inventory outputs as pipeline artifacts and compare critical values. Example SQL script to collect configuration:

```sql
SELECT 'version' AS item, VERSION() AS value
UNION ALL
SELECT 'version_comment', @@version_comment
UNION ALL
SELECT 'default_storage_engine', @@GLOBAL.default_storage_engine
UNION ALL
SELECT 'character_set_server', @@GLOBAL.character_set_server
UNION ALL
SELECT 'collation_server', @@GLOBAL.collation_server
UNION ALL
SELECT 'sql_mode', @@GLOBAL.sql_mode
UNION ALL
SELECT 'time_zone', @@GLOBAL.time_zone
UNION ALL
SELECT 'lower_case_table_names', CAST(@@GLOBAL.lower_case_table_names AS CHAR);
```

This query is only a small subset of an inventory; variables missing on older versions can cause the entire query to fail. In multi-version pipelines, use capability-aware queries or read `SHOW VARIABLES` and filter on the client side to avoid assuming every variable always exists.

A parity report should classify discrepancies:

- **Must match**: differences that make test results untrustworthy, such as target version, storage engine of transactional tables, critical collations, or application SQL mode.
- **Must be documented**: acceptable differences that must be noted explicitly, such as smaller RAM/CPU in a unit integration environment.
- **Not required for this test**: components out of scope, such as not standing up replication in simple CRUD tests.

Do not compare configuration strings alone. Verify enforcement by behavior: test transaction rollbacks, check foreign keys, compare strings according to collation, read `TIMESTAMP` under the session time zone, and run queries with critical execution plans.

## 12. Common Mismatches That Cause False Confidence

| Mismatch | Why tests can still pass | How to improve |
|---|---|---|
| Using `mysql:latest` | Developers and CI may run different versions at different times. | Pin a patch tag or digest. |
| Using H2 instead of MySQL | H2 has different syntax, data types, and locking. | Use a MySQL container for SQL-related integration tests. |
| Comparing only server defaults | Tables/columns/sessions can override server values. | Inspect DDL and the actual session of the application connection. |
| Checking only the default engine | Existing tables may use a different engine. | Inventory `INFORMATION_SCHEMA.TABLES.ENGINE`. |
| Test data too small | The optimizer picks a different plan and fails to expose scale issues. | Use data representative in cardinality and skew for performance tests. |
| Test machine too powerful or different storage | Production latency and contention are not reproduced. | Document resource limits; benchmark on infrastructure close to target. |
| Session SQL mode differs | Tests run via an admin connection while the app uses a different mode. | Inspect the session through the application's own pool/driver. |
| Different `lower_case_table_names` | Table names may work on a developer machine but fail on Linux. | Standardize naming and run tests aligned with the target platform. |
| Not checking plugins/authentication | Tests use a simple user while the production connector cannot log in. | Test actual driver, auth plugin, TLS, and grants. |
| Sharing the same database across all tests | Leftover data makes tests depend on execution order. | Create clean schemas/containers or perform controlled cleanup. |

## 13. Checklist Before Accepting a Test Environment

- [ ] Recorded full MySQL version, patch, distribution, and platform.
- [ ] Image/container or package is pinned; `latest` is not used for reproducible tests.
- [ ] Default engine and engine of each critical table match the target.
- [ ] DDL, charset, collation, indexes, and constraints have been compared.
- [ ] `sql_mode`, time zone, transaction isolation, and session initialization match the application.
- [ ] `lower_case_table_names` matches the platform and was decided before creating the data directory.
- [ ] Plugins, authentication, TLS, users/grants, and Connector/J have been verified.
- [ ] Durability, binary log, and GTID settings fit the type of test being run.
- [ ] Test data has cardinality, skew, and edge-case values matching the target.
- [ ] CPU, RAM, disk, and container limits are documented for performance tests.
- [ ] Tests run on a clean database or with independent cleanup, without order dependency.
- [ ] The pipeline stores version/config reports and detects critical discrepancies.

A good test environment does not merely share the MySQL product name. It must accurately reproduce the factors that can affect the behavior under test: version, engine, schema, session, configuration, and data. Pin your version, inventory actual engines, verify the application's session, and document accepted differences. Only then will test results be reliable enough to catch bugs before deploying to the target environment.
