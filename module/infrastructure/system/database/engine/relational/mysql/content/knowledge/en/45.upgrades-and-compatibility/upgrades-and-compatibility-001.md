# Building a Compatibility Matrix for Server, Connector/J, Tools, and Applications

A MySQL system consists of more than just the database server. Java applications connect via Connector/J, ORM frameworks generate SQL, connection pools manage sessions, migration tools alter schemas, and backup, monitoring, and proxy systems participate in operations. When upgrading one component, the remaining components must still remain compatible with the new version and with each other.

A compatibility matrix is a document that records the versions currently in use, target versions, support conditions, test results, and evidence for each component. The matrix helps answer three questions: which combinations are vendor-supported, which combinations have been tested by the project team, and which combinations are approved for production deployment. These three statuses must be clearly distinguished; a driver might connect in testing yet not belong to an officially supported combination.

This lesson falls within the scope of mastering MySQL from table design, data types, and SQL to query optimization, access control, backups, and operations. The focus is on building a matrix that can be used in upgrade assessments and change control.

## 1. Layers Required in the Matrix

A complete matrix must cover components that affect connections, SQL statements, data, and operational processes:

| Layer | Components to Record | Example Version Information |
|---|---|---|
| Database server | MySQL Community/Enterprise, version, patch level, edition | Current version and target version |
| Java runtime | JDK/JRE, vendor, version, TLS provider | Java runtime running the application |
| JDBC driver | MySQL Connector/J, artifact, and version | com.mysql:mysql-connector-j |
| Application framework | Spring Boot, Spring Framework, Hibernate/JPA, MyBatis | Framework version and dialect |
| Connection pool | HikariCP, Apache DBCP, or other pools | Version, timeout configuration, and validation |
| Migration/schema | Flyway, Liquibase, internal tools | Parser, plugin, and migration scripts version |
| Proxy/routing | MySQL Router, proxy, or service discovery | Version and routing mode |
| Operations | MySQL Shell, client, backup, restore, monitoring, CDC | Tool versions and data formats |
| Infrastructure | Operating system, CPU architecture, container image, TLS, network | Operating system and image versions |

Do not overlook transitive dependencies. For example, an application may declare a Connector/J version compatible with the server, while the Spring Boot version in use pins a different driver version; or a driver may work with the JDK, while an older connection pool has issues closing connections. The matrix must reflect the actual dependencies packaged and executed, not just directly declared versions.

## 2. Distinguishing Supported, Compatible, and Tested

Statuses should be defined consistently:

| Status | Meaning | Usage |
|---|---|---|
| Supported | The vendor publishes support for that combination or version | Entry requirement for production consideration |
| Compatible | The protocol or API can work together according to documentation | Not sufficient to conclude suitability for a specific workload |
| Tested | The project team has run the test suite on the exact version combination | Backed by test evidence, logs, and results |
| Approved | The organization has approved the combination for a specific environment | Permitted for deployment under the change process |
| Blocked | Has bugs, lacks support, or has unresolved risks | Must not be deployed to production |
| Unknown | Insufficient documentation or test results | Requires additional evidence before approval |

A combination may be vendor-supported yet still untested by the application. Conversely, a combination may run in a test environment yet fall outside the vendor's support scope. Do not merge these statuses into a single "OK" column.

Each row in the matrix should contain at minimum:

- Component and role.
- Current version, target version, and actual version in the test environment.
- Minimum/maximum supported versions per documentation, if applicable.
- Compatibility conditions such as JDK, operating system, TLS, authentication plugin, or server features.
- Support status, test results, and deployment decision.
- Links to release notes, compatibility matrices, or official documentation.
- Verification date, verifier, test run, and open issues.

## 3. Compatibility Matrix Template

The template below is a structure to be filled in according to the real environment. "Unverified" cells are not compatibility conclusions; they must be replaced with specific versions, vendor evidence, and test results.

| Component | Current | Target | Conditions to Verify | Result |
|---|---|---|---|---|
| MySQL Server | server-current | server-target | Upgrade path, removed features, default configuration, and data format | Unverified |
| Connector/J | connector-current | connector-target | Supported servers, minimum JDK, authentication, TLS, and connection property changes | Unverified |
| JDK | jdk-current | jdk-target | Connector/J, framework, TLS provider, certificates, and runtime container | Unverified |
| Spring Boot/Framework | framework-current | framework-target | Java version, dependency management, auto-configuration, and managed driver | Unverified |
| Hibernate/JPA | orm-current | orm-target | Dialect, generated SQL, data types, schema validation, and transaction behavior | Unverified |
| Connection pool | pool-current | pool-target | JDBC API, timeout, validation, failover, and leak detection | Unverified |
| Flyway/Liquibase | migration-current | migration-target | Server support, parser, transactional DDL, and migration history | Unverified |
| MySQL Shell/Router | tools-current | tools-target | Server version, metadata, topology, and administrative operations | Unverified |
| Backup/restore | backup-current | backup-target | Format readability, physical/logical compatibility, and restore test | Unverified |
| Monitoring/CDC | monitor-current | monitor-target | Performance Schema, status variables, binlog format, and authentication | Unverified |

Two matrices can be maintained: an environment matrix (development, staging, production) and a software stack matrix. If production has multiple clusters running different versions, each cluster must be recorded explicitly; do not record a single generic version when some nodes actually run a different patch level.

## 4. Verifying MySQL Server and the Upgrade Path

### 4.1. Recording the Baseline

On each instance, gather information about the running server:

~~~sql
SELECT
  VERSION() AS mysql_version,
  @@version_comment AS distribution,
  @@version_compile_os AS compile_os,
  @@version_compile_machine AS compile_machine;

SHOW VARIABLES
WHERE Variable_name IN (
  'sql_mode',
  'character_set_server',
  'collation_server',
  'lower_case_table_names',
  'default_authentication_plugin',
  'require_secure_transport'
);
~~~

The variable list changes across versions; some variables may no longer exist or may have different names. When querying multiple variables in a single statement, adjust according to the actual server rather than treating an "unknown variable" error as an application error.

Also record configuration from config files, startup parameters, plugins, components, storage engines, replication/Group Replication, and features actively used by the application. The `VERSION()` output alone is not enough to describe the entire environment because nodes may differ in configuration, plugins, or patch levels.

### 4.2. Checking Supported Upgrade Paths

Not every source version can be upgraded directly to every target version. Before scheduling, consult the upgrade documentation for the exact MySQL series and verify:

1. Whether the source version is supported as a starting point for the target version.
2. Whether an upgrade to an intermediate version is required.
3. Whether the operating system, architecture, package repository, and data format are supported.
4. Whether changes to default configuration, system tables, data dictionary, or plugins need to be handled.
5. Whether MySQL Shell, Router, backup agents, or other tools must be upgraded at the same time.
6. Whether there are compatibility constraints when nodes in the topology run different versions during a rolling upgrade.

Read the release notes for the source version, any intermediate version, and the target version. Pay attention to sections on incompatibilities, removed/deprecated features, changed defaults, upgrade procedures, and known issues. Do not infer an upgrade path solely from a higher version number.

### 4.3. Running Upgrade Checker and Manual Checks

MySQL Shell includes the Upgrade Checker Utility to check for several issues that may block an upgrade. It can be run from MySQL Shell after connecting to the source instance:

~~~javascript
util.checkForServerUpgrade();
~~~

Cross-check the utility's syntax and options against the installed MySQL Shell version. The checker output is an important input, but it does not replace application testing. The tool cannot know every dynamic query, all real-world data, or the behavior of external libraries.

Additional items to review:

- Deprecated or removed configuration options and system variables.
- Column, table, alias, or identifier names that may become reserved keywords.
- Data types, default values, type casting, and date/time behavior.
- SQL mode and data validation changes.
- Authentication plugins, accounts, and password policies.
- Charset/collation, string comparisons, and sort order.
- Plugins, components, UDFs, and external storage engines.
- Replication filters, binlog format, GTID, and HA topology.

## 5. MySQL Server and Connector/J

Connector/J is the JDBC driver for Java. The driver translates JDBC calls into the MySQL protocol and handles authentication, TLS, data types, and connection properties. The server and the driver have independent release lifecycles, so check the Connector/J compatibility matrix and release notes rather than matching version numbers by guesswork.

### 5.1. Items to Verify

| Item | Verification Question |
|---|---|
| Server support | Does the Connector/J version support the target MySQL Server version? |
| Java support | What minimum JDK/JRE does the driver require, and does it support the runtime in use? |
| JDBC API | Are the JDBC version and the APIs used by the application compatible? |
| Authentication | Does the driver support the authentication plugin enabled on the server? |
| TLS | Do the driver and JDK support the protocol/ciphers; are hostname and CA verification performed? |
| Data types | Have mappings for JSON, temporal, decimal, bit, enum, spatial, and unsigned types changed? |
| Connection properties | Are legacy properties still supported, renamed, or changed in their defaults? |
| Behavior | Have prepared statements, batching, generated keys, metadata, and transactions changed? |

Modern Connector/J uses the driver class:

~~~java
com.mysql.cj.jdbc.Driver
~~~

Modern JDBC frameworks typically auto-detect the driver via the JDBC service provider when the dependency is on the classpath. If configuring the driver class explicitly, use the name appropriate for the selected Connector/J version. Do not retain an old class name simply because a legacy configuration still works in one environment.

The Maven dependency looks like:

~~~xml
<dependency>
  <groupId>com.mysql</groupId>
  <artifactId>mysql-connector-j</artifactId>
  <version>DRIVER_VERSION_APPROVED_FOR_THIS_PROJECT</version>
</dependency>
~~~

The version value must be replaced with a verified version and locked in dependency management. Do not use dynamic versions or let the environment automatically download the latest release outside the dependency management process.

### 5.2. Authentication and TLS

MySQL Server can use different authentication plugins depending on version and configuration. Check each account's plugin:

~~~sql
SELECT
  user,
  host,
  plugin
FROM mysql.user
ORDER BY user, host;
~~~

This query requires appropriate read privileges; do not export or share password hashes. Confirm that Connector/J, the JDK, and the server configuration all support the active plugin. During an upgrade, check application accounts as well as migration, monitoring, backup, and replication accounts.

When connecting over a network, configure TLS with a trusted CA and server identity verification. For Connector/J versions supporting the `sslMode` property, configuration with hostname verification can be declared in the JDBC URL:

~~~properties
spring.datasource.url=jdbc:mysql://mysql.internal.example:3306/appdb?sslMode=VERIFY_IDENTITY
~~~

The hostname in the URL must match the certificate's Subject Alternative Name. Configure the trust store, CA, and client certificate if required by policy. Do not downgrade certificate verification modes just to bypass hostname or CA errors; fix DNS, certificates, or the trust chain for the environment instead.

### 5.3. Checking Connection Properties

Connector/J has many properties that affect behavior, for example:

- `connectTimeout` and `socketTimeout`.
- `sslMode` and trust store configuration.
- `connectionTimeZone` and time handling.
- `useServerPrepStmts` and `cachePrepStmts`.
- `rewriteBatchedStatements`.
- `allowPublicKeyRetrieval`.
- `characterEncoding` and session-related properties.

Do not copy an entire legacy JDBC URL to a new driver without checking it. A property may be deprecated, renamed, changed in default value, or no longer have any effect. In particular, do not enable `allowPublicKeyRetrieval` arbitrarily to work around authentication; prefer verified TLS and configure authentication according to server/driver documentation.

## 6. Java Runtime, Frameworks, and Connection Pools

### 6.1. Java Runtime

Check the actual JDK running in the production environment, not just the JDK on a developer workstation:

~~~bash
java -version
~~~

Cross-check Java requirements for Connector/J, Spring Boot, Hibernate, Flyway/Liquibase, the connection pool, and internal libraries. Verify the JDK vendor, TLS provider, trust store, container base image, and JVM arguments. Upgrading the JDK at the same time as the server and driver makes it harder to isolate the root cause of failures; split changes into independently testable steps whenever possible.

### 6.2. Frameworks and ORM

Spring Boot may manage the Connector/J version via dependency management. Inspect the dependency tree to see the actual artifact:

~~~bash
mvn dependency:tree
~~~

With Gradle, use the corresponding dependency report command for the application's configuration. Do not look only at `pom.xml` or `build.gradle`: transitive dependencies, BOMs, plugins, and dependency overrides can cause the runtime to load a different version than expected.

With Hibernate/JPA, check:

- The selected dialect and its ability to detect the server version.
- Generated SQL for pagination, locking, JSON, sequence/identity, and generated keys.
- Mappings for `java.time`, `BigDecimal`, `boolean`, `enum`, and unsigned numeric types.
- Schema validation and schema generation.
- Transaction isolation, flush mode, batching, and optimistic/pessimistic locking.

Do not modify the dialect to mask SQL errors before determining whether the change comes from the server, driver, or framework. Run integration tests on the exact target version to detect differences.

### 6.3. Connection Pool

A connection pool keeps JDBC sessions alive longer than a single request. When upgrading, check whether the pool is compatible with the new JDBC driver and properly handles connection errors, server restarts, failovers, and timeouts.

Parameters to record in the matrix:

| Parameter | Aspect to Evaluate |
|---|---|
| maximumPoolSize | Concurrent connection limit and total load on MySQL |
| connectionTimeout | Wait time to acquire a connection from the pool |
| validation/keepalive | How dead or dropped connections are detected |
| maxLifetime | Connection lifetime relative to server/proxy timeouts |
| idleTimeout | How long idle connections are retained |
| leakDetectionThreshold | Detecting connections held too long in appropriate environments |

Example HikariCP configuration:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://mysql.internal.example:3306/appdb?sslMode=VERIFY_IDENTITY
    username: app_user
    hikari:
      maximum-pool-size: 20
      connection-timeout: 30000
      max-lifetime: 1500000
      validation-timeout: 5000
~~~

The numbers above are examples only, not a universal optimal configuration. Size the pool based on the number of application instances, MySQL's maximum connections, actual workload, and other services sharing the database. A pool that is too large can overload the server; a pool that is too small can cause queuing in the application.

## 7. Migration, Backup, Router, and Monitoring Tools

### 7.1. Schema Change Tools

Flyway and Liquibase must be checked against the server version and Java runtime. Verify whether the parser understands new syntax, how DDL is handled, metadata locking, migration checksums, and the ability to resume after a failed migration.

Many MySQL DDL operations cause an implicit commit or cannot be rolled back like an ordinary InnoDB transaction. Do not assume a migration script can be undone merely by `ROLLBACK`. Every significant schema change needs an expand/contract plan, a backup, or a forward-fix plan.

### 7.2. Backup and Restore Tools

Check whether the backup tool supports the source/target MySQL versions, physical backup formats, and recording of GTID/binlog coordinates. A successfully created backup does not prove it can be restored to the target version.

Perform a restore test in an isolated environment and check:

- Whether the backup can be decrypted and read.
- Whether the target version supports the backup format.
- Whether system tables, data dictionary, and plugins are compatible.
- Whether GTID, binary logs, and recovery coordinates are properly preserved.
- Whether the restore duration meets RTO.

### 7.3. MySQL Shell and MySQL Router

For InnoDB Cluster or Group Replication, check MySQL Shell and MySQL Router versions against the corresponding compatibility matrix. Verify cluster metadata, discovery, role routing, failover, and reconnection after a primary role change.

A router may keep its port open yet route to the wrong role or hold stale connections. Test new connections, existing connections, primary switchover, and scenarios where a node leaves the group.

### 7.4. Monitoring and CDC

Dashboards may depend on Performance Schema, status variables, system tables, or internal queries that change across versions. Review exporters, agents, alert rules, and dashboards. For CDC, verify binlog format, row image, GTID, retention, and how the connector handles DDL or server restarts.

## 8. Checking SQL Behavior and Data Changes

Successfully establishing a connection does not prove application compatibility. A new server version can change SQL behavior, defaults, or data validation rules.

### 8.1. SQL Mode and Syntax

Compare `@@sql_mode` between the current and target environments. Check whether the application relies on accepting invalid data, implicit conversions, special date/time values, or non-standard `GROUP BY` behavior.

Review SQL statements containing:

- Table/column/alias names that may collide with reserved keywords.
- Deprecated or changed functions or syntax.
- `GROUP BY`, `ORDER BY`, `LIMIT`, window functions, and CTEs.
- Locking clauses such as `FOR UPDATE` or `SKIP LOCKED`.
- JSON, generated columns, functional indexes, and expressions.
- DDL, partitioning, check constraints, and foreign keys.

### 8.2. Charset and Collation

Charset/collation affects storage, comparison, unique keys, and sort order. When changing collation, two strings that were previously distinct may be treated as equal, or vice versa. This can cause duplicate key errors when creating unique indexes or alter search results.

Check charsets at the server, database, table, column, and connection session levels. Test with accented characters, emojis, non-BMP characters, combining characters, and strings differing in case or diacritics.

### 8.3. Data Types and Time Handling

Check mappings between MySQL and Java:

| MySQL | Common Java/JDBC Type | Risks to Test |
|---|---|---|
| DECIMAL | BigDecimal | Precision, scale, and rounding |
| BIGINT | Long | Boundary values and type overflow |
| TINYINT(1) | Boolean or numeric | Mapping depends on driver/framework |
| DATETIME | LocalDateTime | Carries no timezone |
| TIMESTAMP | Instant/OffsetDateTime or other types | Conversion based on session/server timezone |
| JSON | String or framework JSON mapping | Serialization, null, and data types |
| BIT | Boolean/byte array | Mapping and ResultSet reading behavior |
| ENUM | String or application enum | New values and enum ordering |

Pay special attention to JVM, server, session, and data timezones. A timezone configuration change can shift displayed or stored timestamps even while queries continue to succeed.

## 9. Process for Building and Approving the Matrix

A repeatable process:

1. **Inventory:** collect server, JDK, driver, framework, pool, migration tool, backup, router, and monitoring versions from real environments.
2. **Select target:** determine the planned target versions and the vendor-supported upgrade path.
3. **Check support:** read the compatibility matrix and release notes for each component, saving links and verification dates.
4. **Analyze dependencies:** inspect BOMs, dependency trees, container images, plugins, and transitive libraries.
5. **Document conditions:** specify minimum JDK, TLS, authentication, SQL mode, dialect, configuration, and operational requirements.
6. **Build test matrix:** identify the version combinations to test; prioritize the target production combination and transitional combinations if rolling out in phases.
7. **Test:** run unit, integration, migration, performance, failover, backup/restore, and security tests.
8. **Resolve discrepancies:** classify failures by server, driver, framework, schema, data, configuration, or network; record workarounds and owners.
9. **Approve:** mark as Approved only when all mandatory checks pass and a rollback plan exists.
10. **Lock versions:** update BOMs, lockfiles, container images, and deployment configurations so every environment uses the exact approved combination.

## 10. Test Suite for the New Stack

A matrix is only valuable when tied to concrete testing. It can be organized into the following layers:

| Test Group | Scope | Pass Criteria |
|---|---|---|
| Connectivity | DNS, TCP, TLS, certificate verification, authentication, and reconnect | Connects to the right server without weakening security |
| JDBC | Prepared statements, batch, generated keys, metadata, ResultSet | Behavior matches the APIs used by the application |
| SQL | Read/write queries, joins, pagination, locking, JSON, and DDL | Results and errors match expectations |
| Transaction | Commit, rollback, isolation, deadlock, and retry | No lost transactions, controlled retries |
| ORM | Mapping, lazy loading, flush, schema validation, and dialect | No incorrect SQL generated or unintended data changes |
| Pool | Timeout, stale connections, server restart, failover | Pool recovers within SLO |
| Migration | Running from old schema to new schema, resume, and checksum | Deterministic migration, repeatable operationally |
| Backup/restore | Restore from backup and PITR if applicable | Recovered data meets RPO/RTO |
| Performance | Throughput, p95/p99 latency, CPU, I/O, and connection count | Within agreed thresholds |
| Security | Authentication, TLS, grants, secret rotation | No excess privileges or unverified connections |

Run tests with representative data, including boundary values, NULLs, Unicode strings, decimals, dates/times, and records with foreign key relationships. Testing against an empty database is insufficient to uncover bugs caused by years of accumulated production data.

## 11. Example Test Matrix for an Upgrade Wave

Suppose a project team plans to upgrade MySQL Server while also changing Connector/J, the JDK, and the framework. Separate the changes so failures can be attributed:

| Run | Server | JDK/Connector/J | Framework | Purpose |
|---|---|---|---|---|
| A | Current version | Current stack | Current | Baseline and performance measurement |
| B | Target version | Current stack if supported | Current | Isolate server impact |
| C | Target version | Target Connector/J | Current | Test driver and JDBC |
| D | Target version | Target JDK + target driver | Current | Test runtime and TLS |
| E | Target version | Target stack | Target framework | Test the full production combination |

This is an illustrative testing sequence. If the vendor does not support an intermediate combination in Run B or C, do not deploy that combination to production; use it only in test environments if feasible and consistent with support terms. When technical constraints force simultaneous upgrades, strengthen integration testing and keep clear evidence for each change.

For each run, record:

- Application commit and tested artifact.
- Container image or JDK build.
- Exact MySQL version on each node.
- Connector/J and actual dependency tree.
- Server configuration, SQL mode, charset, collation, and TLS.
- Dataset, migration scripts, and test suite.
- Test results, error logs, latency, and resource usage.

## 12. Risk Management and Production Decisions

Approval should not be based solely on every dependency being at its latest version. New versions can change APIs, defaults, authentication, SQL generation, or Java requirements. Choose a combination that is supported, tested, and aligned with the organization's maintenance lifecycle.

Conditions that should block deployment:

- The target server is outside a supported upgrade path.
- Connector/J does not support the target server or JDK.
- The framework/ORM does not yet support the selected runtime or driver.
- TLS or authentication does not meet security policy.
- The migration tool cannot read/write the target schema in a tested manner.
- Backups cannot be restored on a compatible environment.
- There are data, transaction, or deadlock errors, or performance exceeds thresholds.
- No rollback plan or decision owner is established.

Once the matrix is approved, store the versions along with the verification date and evidence. Update the matrix whenever there is a server patch, JDK change, framework upgrade, driver update, CA/certificate change, or addition of operational tools.

## 13. Practical Scenario

A Java application has been running MySQL Server, Connector/J, Spring Boot, Hibernate, and HikariCP on versions that have been stable for years. The operations team wants to upgrade the server to a new series while also updating the JDK to meet security policy.

Build a plan:

1. Collect actual versions from the server, runtime, dependency tree, container image, and pool configuration.
2. Consult support documentation for the target server, Connector/J, JDK, Spring Boot, Hibernate, and HikariCP.
3. Document constraints regarding authentication plugins, TLS, timezone, SQL mode, charset, and dialect.
4. Check migration tools, backup/restore, monitoring, and MySQL Router if the system uses them.
5. Create isolated test runs to distinguish whether errors stem from the server, driver, runtime, or framework.
6. Run integration tests with representative data, especially temporal, decimal, JSON, and Unicode types.
7. Run performance tests, failover tests, and restore tests.
8. Mark as Approved only when the full combination meets criteria and a rollback plan is in place.

The output must be a matrix that others can read and reproduce, rather than a disconnected list of versions. Every compatibility conclusion must point to supporting documentation or a proving test run.

## 14. Self-Check Questions

1. Why is "the driver can connect" insufficient proof that a server and Connector/J combination is supported?
2. Which components besides MySQL Server and the JDBC driver should the matrix record?
3. Why must you inspect the dependency tree rather than reading only the build file?
4. What failures can authentication plugins and TLS cause after an upgrade?
5. How can SQL mode, collation, and timezone alter application behavior?
6. Why must backup/restore and migration tools be tested alongside the target server?
7. What evidence does a combination need in order to move from Tested to Approved?
8. When upgrading the server, JDK, Connector/J, and framework together, how do you isolate faults?

A compatibility matrix is part of MySQL change management. When versions, support conditions, actual dependencies, test results, and production decisions are recorded together, the project team can upgrade under control and detect risks early across the database, Java driver, framework, and operational tools.
