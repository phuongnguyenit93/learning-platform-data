# Upgrades and Compatibility

## Checking Plugins/Components, Stored Objects, and Operational Tools

A MySQL upgrade does more than swap server binaries. Applications also rely on plugins, components, stored objects, and tools for connectivity, backups, replication, monitoring, and schema administration. A server may start cleanly yet fail to load a plugin, break a view whose `DEFINER` is missing, fail to run an event, or render a backup tool incompatible with the new format. Therefore, compatibility verification must cover every component participating in the data lifecycle.

In the **DATABASE_MYSQL** module, you learn to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control. You also practice reading execution plans, query tuning, access control, backups, and handling relational database operational issues. These skills help you assess upgrade impact across server, metadata, security, and operational layers.

This lesson focuses on three groups to verify before and after an upgrade: plugins/components loaded into the server, stored objects executed inside the database, and operational tools/clients connecting to MySQL. Examples primarily target MySQL 8.0/8.4; syntax and support must be verified against your exact version, edition, operating system, and vendor.

### 1. Mapping Dependencies Before Upgrading

Compatibility cannot be verified without knowing what the system currently uses. Build an inventory on the source server and store it alongside the upgrade plan.

Categories to inventory:

| Category | Items to Record | Upgrade Risks |
|---|---|---|
| Plugins | Name, type, status, library, version, vendor, and loading mechanism | Plugin lacks a compatible binary, is deprecated, or is no longer supported |
| Components | Installed component, library, dependencies, and startup load configuration | Component fails to initialize, service dependencies changed, or registry differs |
| Stored objects | Views, procedures, functions, triggers, events, `DEFINER`, SQL mode, and security type | Objects compile/create but fail at runtime, lack privileges, or behave differently |
| Clients/drivers | `mysql` client, connectors, ORMs, driver versions, auth plugins, and TLS | Cannot log in or incompatible protocol/authentication |
| Backup/restore | `mysqldump`, MySQL Shell, Enterprise Backup, XtraBackup, and `mysqlbinlog` | Backups fail to restore or cannot read binlogs after upgrade |
| Replication/HA | Router, Group Replication, Shell AdminAPI, proxies, and orchestrators | Topology stops functioning or failover/metadata upgrade fails |
| Schema tooling | Migration runners, `pt-online-schema-change`, `gh-ost`, and DDL scripts | Tools do not support new version, triggers, FKs, or binlog formats |
| Monitoring | Agents, exporters, dashboards, alerts, and Performance Schema queries | Renamed metrics, changed instruments, or false/broken alerts |

Record the exact MySQL version, edition, operating system, CPU architecture, package repository, and `plugin_dir` path. A plugin compiled for Linux x86-64 cannot be used by default on Windows or ARM; Community and Enterprise binaries are likewise not interchangeable by default.

### 2. Distinguishing Plugins and Components

Both plugins and components extend MySQL Server capabilities, but they use different interfaces and management mechanisms.

| Characteristic | Plugin | Component |
|---|---|---|
| Model | Traditional Plugin API, typically registering one feature type such as authentication, storage engine, or audit | Component service architecture, able to provide and consume internal services |
| Registration | Metadata stored in system table `mysql.plugin` when installed via `INSTALL PLUGIN` | Dedicated registry in `mysql.component` |
| Installation | `INSTALL PLUGIN` with plugin name and library | `INSTALL COMPONENT` with component URI |
| Uninstallation | `UNINSTALL PLUGIN` | `UNINSTALL COMPONENT` |
| Startup loading | Can use `plugin-load-add` or equivalent mechanism | Can configure `component_load_add` or version-supported startup mechanism |
| Compatibility | Depends on plugin API/ABI, binary, server version, and vendor | Depends on component service API, dependencies, and server version |

The component architecture was introduced so extensions can interact through more structured service interfaces. Do not treat components merely as another syntax for plugins or assume both share the same lifecycle.

### 3. Inventorying Plugins on the Source Server

Before upgrading, capture the plugin list and status:

~~~sql
SHOW PLUGINS;
~~~

You can query detailed metadata:

~~~sql
SELECT
  PLUGIN_NAME,
  PLUGIN_VERSION,
  PLUGIN_STATUS,
  PLUGIN_TYPE,
  PLUGIN_LIBRARY,
  LOAD_OPTION
FROM INFORMATION_SCHEMA.PLUGINS
ORDER BY PLUGIN_TYPE, PLUGIN_NAME;
~~~

Columns and values can vary by version. Record `ACTIVE`, `INACTIVE`, and errored plugins alike; an inactive plugin might still be configured to load on the next restart.

Inspect plugin loading configuration and the library directory:

~~~sql
SHOW VARIABLES LIKE 'plugin_dir';
SHOW VARIABLES LIKE 'plugin_load%';
~~~

Cross-check server configuration on the filesystem, including `plugin-load-add` options. Do not rely solely on `SHOW PLUGINS`, because startup options and libraries on disk govern the next restart.

Traditional plugin management statements:

~~~sql
INSTALL PLUGIN plugin_name SONAME 'plugin_library.so';

UNINSTALL PLUGIN plugin_name;
~~~

This is illustrative syntax. Replace `plugin_name` and the library name with vendor-supplied values for your exact platform. On Windows, libraries typically use the `.dll` extension. Never rename or copy a shared library from a different server version.

Plugins installed via `INSTALL PLUGIN` are registered so MySQL reloads them at startup. `plugin-load-add` settings can also load libraries at startup; understand the active loading method to avoid duplicate or conflicting configs. If a plugin is mandatory for startup or data decryption, test startup on a clone before making changes.

### 4. Inventorying Components and Dependencies

On versions supporting components, inspect the registry:

~~~sql
SELECT * FROM mysql.component;
~~~

The registry table shows registered components; column layouts may change across versions. Combine this output with startup configs, startup logs, and vendor documentation to verify which components actually initialized.

Components can be installed via library URI:

~~~sql
INSTALL COMPONENT 'file://component_name';

UNINSTALL COMPONENT 'file://component_name';
~~~

The component name and library location must match the installed package. Some components depend on other services or dedicated settings; successful installation does not guarantee the component provides every capability the application expects.

To load components at startup, MySQL offers `component_load_add` in supported versions. Check syntax and declaration format in the configuration documentation for your exact version; never copy raw configurations across MySQL series without checking.

Before uninstalling a component, determine which other components depend on its services. If a component provides encryption, key management, authentication, or auditing, removing it can render data unreadable or alter security policy. Never uninstall in production just to test whether the server still starts.

### 5. Plugin/Component Groups Requiring Attention

#### 5.1. Authentication

Authentication plugins determine how MySQL validates account credentials. When upgrading the server, check:

- Whether each account's authentication plugin remains supported and loads cleanly.
- Whether application drivers/connectors support that authentication method.
- Whether TLS, certificates, RSA key exchange, and password settings are compatible.
- Whether administrative, replication, backup, and application accounts can log in after the upgrade.

Example inventory of account authentication plugins:

~~~sql
SELECT
  user,
  host,
  plugin,
  account_locked,
  password_expired
FROM mysql.user
ORDER BY user, host;
~~~

Read access to `mysql.user` is restricted; use an appropriate administrative account and never export password hashes into unprotected reports.

MySQL 8.0 uses `caching_sha2_password` as the default authentication method for new accounts. `mysql_native_password` was deprecated in MySQL 8.0.34, disabled by default in MySQL 8.4, and removed in MySQL 9.0. Before upgrading, identify accounts still using the legacy plugin, check connectors, and build a migration plan. Do not re-enable the legacy method server-wide just to accommodate one un-updated client.

#### 5.2. Keyring and Encryption

Keyring plugins/components may manage keys for tablespace encryption, redo/undo encryption, or other security features. Key accessibility is a prerequisite for reading encrypted data.

Before upgrading:

1. Identify the active keyring implementation and how it loads at startup.
2. Save configurations, key store paths, filesystem permissions, and dependencies.
3. Verify key store backups and key recovery procedures independently of data backups.
4. Test starting the upgrade using a copy of the data directory and a matching copy of the key store.
5. Confirm encrypted data remains readable after restarts and after a test restore.

Do not remove or replace a keyring simply because the plugin/component name changed. Do not delete, overwrite, or move a key store before having a restorable copy. A database backup without its required keys may be unrecoverable.

#### 5.3. Audit and Password Validation

Audit plugins/components record security events such as connections, statements, or object operations. Check versions, editions, filters, log paths, write permissions, and centralized log shipping.

If an upgrade renames variables, filter structures, or log formats, SIEM pipelines and parsers may fail to ingest data as before. Generate test events, inspect new logs, and confirm alerts still fire.

Password validation may be implemented as a plugin or component depending on version and installation. Check current policies, configuration variables, and password creation/change behavior. Do not merely check that the plugin is `ACTIVE`; test creating a lab account with both compliant and non-compliant passwords.

### 6. Stored Objects Affected by Upgrades

Stored objects include views, stored procedures, stored functions, triggers, and events. Stored routines, triggers, and events capture `SQL_MODE` at creation time; views store `DEFINER`/security context and charset/collation context. All of them can reference column names or functions that have changed.

Some errors surface only when an object is invoked or when an event runs on schedule. Therefore, post-upgrade object checks must cover both metadata and runtime execution.

#### 6.1. Inventorying Objects

List routines:

~~~sql
SELECT
  ROUTINE_SCHEMA,
  ROUTINE_NAME,
  ROUTINE_TYPE,
  DEFINER,
  SECURITY_TYPE,
  SQL_MODE,
  CHARACTER_SET_CLIENT,
  COLLATION_CONNECTION,
  DATABASE_COLLATION
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA NOT IN
  ('mysql', 'information_schema', 'performance_schema', 'sys')
ORDER BY ROUTINE_SCHEMA, ROUTINE_NAME;
~~~

List triggers:

~~~sql
SELECT
  TRIGGER_SCHEMA,
  TRIGGER_NAME,
  EVENT_MANIPULATION,
  EVENT_OBJECT_TABLE,
  ACTION_TIMING,
  DEFINER,
  SQL_MODE,
  CHARACTER_SET_CLIENT,
  COLLATION_CONNECTION
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA NOT IN
  ('mysql', 'information_schema', 'performance_schema', 'sys')
ORDER BY TRIGGER_SCHEMA, EVENT_OBJECT_TABLE, TRIGGER_NAME;
~~~

List events:

~~~sql
SELECT
  EVENT_SCHEMA,
  EVENT_NAME,
  DEFINER,
  STATUS,
  TIME_ZONE,
  SQL_MODE,
  ON_COMPLETION
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA NOT IN
  ('mysql', 'information_schema', 'performance_schema', 'sys')
ORDER BY EVENT_SCHEMA, EVENT_NAME;
~~~

List views:

~~~sql
SELECT
  TABLE_SCHEMA,
  TABLE_NAME,
  DEFINER,
  SECURITY_TYPE,
  CHARACTER_SET_CLIENT,
  COLLATION_CONNECTION
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA NOT IN
  ('mysql', 'information_schema', 'performance_schema', 'sys')
ORDER BY TABLE_SCHEMA, TABLE_NAME;
~~~

`INFORMATION_SCHEMA` queries depend on metadata viewing privileges and server version. For critical objects, also save definitions with `SHOW CREATE VIEW`, `SHOW CREATE PROCEDURE`, `SHOW CREATE FUNCTION`, `SHOW CREATE TRIGGER`, and `SHOW CREATE EVENT`. Do not rely solely on `ROUTINE_DEFINITION`, as metadata text may be truncated or insufficient to recreate the object.

#### 6.2. Checking DEFINER and Execution Privileges

`DEFINER` is the account some stored objects use as their security context. If that account does not exist after restore/upgrade, the object may error when invoked, or behave differently if the account's privileges changed.

Objects with `SQL SECURITY DEFINER` execute with the definer's privileges; `SQL SECURITY INVOKER` executes with the caller's privileges in supported contexts. Views, routines, and other objects can carry different security types. Inspect each object rather than assuming all share the same policy.

Find definers and verify accounts:

~~~sql
SELECT DISTINCT DEFINER
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'appdb'
UNION
SELECT DISTINCT DEFINER
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'appdb'
UNION
SELECT DISTINCT DEFINER
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'appdb'
UNION
SELECT DISTINCT DEFINER
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = 'appdb';
~~~

Cross-check every `user@host` value against managed accounts on the target server. Avoid creating a broad-privilege definer account just to silence object errors. Create a dedicated least-privilege account, or switch to `INVOKER` if the security model and application behavior permit.

During dump/restore, review the tool's `DEFINER`-handling options. Stripping `DEFINER` can cause objects to use a default context or alter security semantics; keeping `DEFINER` can create references to nonexistent accounts. This is a security decision requiring testing, not a mechanical string replacement.

#### 6.3. SQL Mode Stored with Stored Programs

MySQL saves the `SQL_MODE` active when a stored procedure, function, trigger, or event is created. When the object executes, it can use that saved mode instead of the calling session's current mode.

Consequently, two servers with identical `@@GLOBAL.sql_mode` can still exhibit different stored program behavior if objects were created at different times or under different modes.

Compare:

~~~sql
SELECT
  @@GLOBAL.sql_mode AS global_sql_mode,
  @@SESSION.sql_mode AS session_sql_mode;

SELECT ROUTINE_NAME, ROUTINE_TYPE, SQL_MODE
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'appdb';

SELECT TRIGGER_NAME, SQL_MODE
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'appdb';

SELECT EVENT_NAME, SQL_MODE
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'appdb';
~~~

Before recreating objects, set the agreed baseline SQL mode in the deployment session. Afterward, re-read metadata and run tests to confirm objects carry the expected mode. Do not alter global SQL mode merely to let a legacy routine execute.

#### 6.4. Charset, Collation, and Object Names

Stored objects save charset/collation context at creation time; views also store client charset and connection collation metadata. If an upgrade also changes collations, string comparisons inside views/routines may produce different results.

Check:

- Charset/collation of databases, tables, and columns referenced by the object.
- `CHARACTER_SET_CLIENT` and `COLLATION_CONNECTION` of the object.
- Column names, function names, or identifiers that may become reserved words in the new version.
- Data types, precision, and implicit casting in expressions.
- Comparison, sorting, and unique key behavior under the new collation.

Compare `SHOW CREATE` outputs and run test cases with accented characters, case variations, `NULL`s, dates/times, and boundary values. If definitions must change, create new reviewable and rollbackable migrations per schema change policy.

#### 6.5. Event Scheduler and Automated Jobs

Events can run on schedule once the server restarts. Check the event scheduler and individual event statuses:

~~~sql
SHOW VARIABLES LIKE 'event_scheduler';

SELECT
  EVENT_SCHEMA,
  EVENT_NAME,
  STATUS,
  LAST_EXECUTED,
  TIME_ZONE,
  DEFINER
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'appdb';
~~~

Before cutover, clearly decide which events are enabled on the new primary. If both the old source and new target execute data-modifying events simultaneously, jobs may run twice. If an event is unexpectedly disabled, summary tables, cleanups, or scheduled jobs may stop updating.

Verify each event's timezone, definer, privileges, and next execution schedule. Test the logic in a test environment or invoke the underlying procedure in a controlled manner; do not wait for production schedules to uncover failures.

### 7. Checking Client and Connector Compatibility

A new server may reject older client connections due to authentication plugins, TLS protocols, ciphers, certificates, or protocol changes. Check these components:

- MySQL command-line client and client libraries used by applications.
- Connector/J, Connector/NET, Node.js, Python, Go, and ORM drivers.
- Connection pools, proxies, and health checks.
- Authentication plugin of each account.
- TLS CAs, certificates, hostname verification, and cipher suites.
- Default charset, timezone, and session SQL mode.

Record client versions:

~~~bash
mysql --version
mysqlsh --version
~~~

Test connections using the exact binary/driver the application will run, not just a newly installed `mysql` client on a DBA workstation. Test at minimum login flows, queries, transactions, prepared statements, bulk loads, and failover reconnects.

If using `caching_sha2_password`, verify the driver supports this method and key exchange aligns with TLS or RSA configuration. Do not weaken authentication system-wide just to retain an outdated client; upgrading connectors and testing is the sustainable fix.

### 8. Checking Backup, Restore, and Replication Tools

#### 8.1. Logical Backup Tools

`mysqldump` and MySQL Shell dump/load utilities have distinct lifecycles and capabilities. Before upgrading, verify that client tools can connect to the target server, understand data types/collations, and produce dumps importable into the target version.

For `mysqldump`, check active options such as `single-transaction`, `routines`, `triggers`, `events`, `source-data`/`master-data`, `set-gtid-purged`, and `DEFINER` handling. Options may be renamed, deprecated, or change behavior across versions.

MySQL Shell provides dump/load utilities for large schemas, parallelism, and cross-version data transfers. Check MySQL Shell version, target version, compatibility options, and Upgrade Checker output. Never assume a dump created by a newer MySQL Shell can always be loaded into an older server.

#### 8.2. Physical Backup Tools

MySQL Enterprise Backup and Percona XtraBackup have compatibility matrices covering server versions, data formats, encryption plugins, and platforms. Physical backups depend on file layouts, redo/undo logs, data dictionary, and storage engine features.

Before upgrading:

1. Verify the exact backup/prepare/restore tool version for the source server version.
2. Confirm support for the target version and planned upgrade path.
3. Check encryption plugins, keyrings, compression, and page size.
4. Perform a full backup, prepare, and test restore in an isolated environment.
5. Record backup/restore durations, errors, and data verification results.

Never treat a physical backup as if it were a logical dump loadable into arbitrary versions. When upgrading major versions, follow the tool's upgrade path and documentation.

#### 8.3. Binlogs and Replication

`mysqlbinlog` must be able to read the binlog format produced by the server. When major versions, row events, checksums, GTIDs, or replication command names change, verify client utility compatibility and test replaying a log segment on a lab instance.

Replication status/control commands renamed across MySQL versions:

| Purpose | Old Version | New Version |
|---|---|---|
| View source binlog status | `SHOW MASTER STATUS` | `SHOW BINARY LOG STATUS` in MySQL 8.4 |
| View replica status | `SHOW SLAVE STATUS` | `SHOW REPLICA STATUS` since MySQL 8.0.22 |
| Start/stop replica | `START SLAVE` / `STOP SLAVE` | `START REPLICA` / `STOP REPLICA` |
| Configure source | `CHANGE MASTER TO` | `CHANGE REPLICATION SOURCE TO` since MySQL 8.0.23 |

Operational scripts must check the version before invoking commands. An old statement may still exist yet be deprecated in an intermediate release; in a newer release, it may be removed entirely.

### 9. Router, Shell, and HA Tools

If the system uses InnoDB Cluster or Group Replication, check synchronized compatibility across MySQL Server, MySQL Shell, and MySQL Router.

Items to verify:

- MySQL Shell AdminAPI recognizes the server version and metadata schema properly.
- MySQL Router supports the cluster's metadata version and active topology.
- Router bootstrap/configuration points to the right metadata servers and endpoints.
- Router's TLS, authentication, and metadata user remain valid.
- Metadata upgrades are executed per MySQL Shell instructions when required by the version.
- Health checks and read/write routing still distinguish primary from secondaries.

Do not upgrade Router or Shell independently in production without testing against actual cluster metadata. An older Router may fail to understand new metadata; a newer Shell may require upgrading metadata before certain AdminAPI operations work.

### 10. Schema Migration and Online DDL Tools

Tools such as `pt-online-schema-change` and `gh-ost` alter how DDL executes: creating a shadow table, copying data in chunks, syncing ongoing changes, and swapping table names. They carry specific restrictions regarding triggers, foreign keys, partitions, binlog formats, GTIDs, replication topology, and privileges.

Before using them on a new version:

- Check the official support matrix for the tool version.
- Identify whether target tables have triggers, foreign keys, generated columns, or partitions.
- Verify binlog format, GTID, and that replicas receive changes properly.
- Assess metadata locks during the cutover/rename step.
- Verify privileges for creating/dropping/renaming tables, triggers, and replication.
- Test on a clone matching production size and workload.

Do not treat online schema change as zero-downtime. These tools reduce long lock holds, yet still require a metadata lock at cutover; copy and sync overhead can also increase replica lag.

### 11. Upgrade Checker and Verification Workflow

MySQL Shell includes the Upgrade Checker Utility to scan for pre-upgrade compatibility issues. Run it inside MySQL Shell:

~~~javascript
util.checkForServerUpgrade(
  'admin@mysql-source.example.net:3306',
  { targetVersion: '8.4.0' }
);
~~~

Substitute the account, host, and `targetVersion` from your actual plan. Results depend on MySQL Shell version, access privileges, and target version. Read every warning/error, save the report, and resolve blockers before proceeding. Upgrade Checker does not replace testing third-party vendor plugins, stored objects, applications, or backup tools.

For MySQL 8.0.16 and later, the server automatically handles system table/data dictionary upgrades on startup per supported workflows; do not assume `mysql_upgrade` must be run manually as in older versions. Check version documentation and startup logs instead of keeping an obsolete step in runbooks.

Recommended workflow:

1. **Inventory:** record server versions, plugins/components, stored objects, drivers, tools, Router, and monitoring.
2. **Compatibility matrix:** mark supported, unsupported, deprecated, needs configuration, or unverified for each component.
3. **Pre-upgrade checks:** run Upgrade Checker and check deprecated features, reserved words, collations, and data formats.
4. **Backups and rehearsal:** take full backups, preserve keyrings, test-restore on a clone, and run application tests.
5. **Trial upgrade:** upgrade a staging environment containing the same plugins, objects, tools, and critical workloads.
6. **Post-upgrade inventory:** compare plugin/component status, `DEFINER`, SQL mode, charset/collation, and tools.
7. **Functional tests:** invoke routines, views, triggers, events; test authentication, backup/restore, replication, monitoring, and failover.
8. **Cutover:** deploy to production only after blockers are resolved and a recovery plan is verified.

### 12. Testing Stored Objects After Upgrade

Checking metadata is only the first step. Every critical object needs test cases confirming output and privileges.

| Object | Suggested Test Cases |
|---|---|
| View | `SELECT` using the application account; verify `SQL SECURITY`, `DEFINER`, columns, and collation |
| Procedure | Call with valid inputs, `NULL`, and boundary data; verify transactions and privileges |
| Function | Verify return values, type casting, SQL mode, and deterministic behavior if applicable |
| Trigger | `INSERT`/`UPDATE`/`DELETE` on a test table; verify side effects fire exactly once |
| Event | Verify scheduler, status, timezone, definer, and scheduled job execution |

Test with the exact application account. An object running under a DBA account does not prove production accounts hold the required privileges. For triggers and events, verify no duplicate records are generated when old and new systems overlap.

### 13. Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Server fails to start after upgrade | Incompatible plugin/component binary or missing dependency | Read error log, check `plugin_dir` and startup options; use version-matched binary or roll back per plan |
| Plugin enters errored state | Missing library, ABI mismatch, wrong permissions, or unsupported on new server | Verify package/vendor support, paths, and permissions; never copy libraries arbitrarily |
| Component fails to initialize | Wrong URI, missing dependency, or bad `component_load_add` | Check registry, startup logs, and version-exact configuration |
| Client reports authentication plugin cannot be loaded | Outdated driver or incompatible auth plugin | Upgrade connector, inspect account plugin and TLS; avoid weakening server-wide security |
| View/procedure reports definer does not exist | `DEFINER` account missing on target | Assess security semantics, create least-privilege definer, or adjust object in a controlled way |
| Stored routine produces different results | Different `SQL_MODE` or charset/collation saved at creation | Compare `INFORMATION_SCHEMA` and `SHOW CREATE`; recreate object in a properly configured session |
| Event does not run or runs twice | `event_scheduler`, timezone, or two nodes both enabling events | Enable events only on the designated role node; verify scheduler and event state |
| Backup fails prepare/restore | Tool incompatible with server, format, or keyring | Use a supported tool version; verify keys and run a restore rehearsal |
| Router fails to recognize primary | Incompatible metadata version, Router version, or cluster state | Check Shell/Router/metadata, upgrade per runbook, and verify routing |
| Online schema tool fails | Incompatible triggers, FKs, binlogs, GTIDs, or privileges | Check tool limitations, test in staging, and use a suitable DDL approach |

### 14. Upgrade Acceptance Checklist

- [ ] Recorded MySQL version, edition, OS, architecture, and `plugin_dir`.
- [ ] Inventoried plugins and components, including status, libraries, and startup loading.
- [ ] Plugin/component binaries confirmed by vendor to support target.
- [ ] Keyring and encrypted data backed up, test-restored, and verified readable.
- [ ] Account authentication plugins and application connectors are compatible.
- [ ] Views, routines, triggers, and events inventoried; `DEFINER`s exist with least privilege.
- [ ] `SQL_MODE`, charset/collation, and security type of stored objects reconciled.
- [ ] Event scheduler and schedules run only on the designated node.
- [ ] `mysqldump`/MySQL Shell/physical backup/`mysqlbinlog` tested against target version.
- [ ] MySQL Router, Shell, AdminAPI, and cluster metadata are compatible.
- [ ] Online schema change tools, migration runners, and monitoring agents tested.
- [ ] Upgrade Checker and rehearsals have zero unresolved blockers.
- [ ] Backup/restore, authentication, replication, stored objects, and applications passed functional tests.
- [ ] Logs, compatibility reports, rollback/recovery plan, and accountable owners documented.

### 15. Practical Exercise

A system runs MySQL 8.0 and plans to upgrade to MySQL 8.4. It uses a legacy authentication plugin, a key-management component, an audit plugin, several procedures whose `DEFINER` is a retired DBA account, an hourly event, MySQL Router, and a physical backup tool.

1. Which queries will you use to inventory plugins and components? Why must you also check startup configuration?
2. What must be verified regarding binaries and vendor support before loading plugins on MySQL 8.4?
3. Why must keyring backup and restore be verified independently of data backups?
4. How do you identify procedures depending on a `DEFINER` that no longer exists?
5. Why does an identical global SQL mode still not guarantee identical stored routine behavior?
6. How do you prevent events from running twice during cutover?
7. Which parts of the MySQL Shell, Router, and backup stack must be upgraded or tested alongside the server?
8. Build a test matrix covering authentication, stored objects, backup/restore, replication, and monitoring prior to approving the upgrade.

### 16. Operational Principles

Upgrading MySQL modifies a dependent ecosystem, not just the server version. Plugins and components need matching binaries, dependencies, and loading configs; stored objects need valid `DEFINER`s, privileges, SQL modes, and charsets/collations; clients and operational tools must understand the new version's protocols, data formats, and metadata. Inventory upfront, cross-check compatibility matrices, test-restore backups, and test every function in staging. Bring the system into production service only after critical components are verified with real evidence.
