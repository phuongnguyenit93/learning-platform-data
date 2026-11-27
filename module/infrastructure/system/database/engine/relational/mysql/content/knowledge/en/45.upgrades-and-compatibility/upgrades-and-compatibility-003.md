# Pre-Upgrade Checks Using Version-Appropriate Tools

Upgrading MySQL can alter SQL behavior, configuration, authentication plugins, the data dictionary, storage engines, and how the server handles existing objects. Just because an instance starts after an upgrade does not guarantee the application will still function properly. Therefore, before upgrading, you must evaluate the source version, target version, supported upgrade path, and compatibility issues in data, schema, configuration, and applications.

The appropriate tool for pre-upgrade assessment is **MySQL Shell Upgrade Checker** (`util.checkForServerUpgrade`). It inspects the current instance against a target MySQL version and reports errors, warnings, or notices that require attention. Additional table-level checks can be run using `mysqlcheck` with `--check-upgrade`, though table checks do not replace Upgrade Checker. The checker tool also does not perform the server upgrade itself.

Within the `DATABASE_MYSQL` module, this lesson connects version management, schema, configuration, replication, backups, and operations. After completing this lesson, you will be able to:

- Select the appropriate MySQL Shell version and target version for the check.
- Run Upgrade Checker against a source instance and save the report.
- Classify errors, warnings, and notices by impact level.
- Perform additional checks on tables, configurations, plugins, applications, and topology.
- Prepare a staging environment, backups, and a rehearsal plan prior to upgrading production.
- Define the readiness criteria required before authorizing an upgrade.

## 1. Why Are Pre-Upgrade Compatibility Checks Needed?

A new MySQL version may remove deprecated syntax, configuration variables, plugins, or features. Some identifiers may become reserved keywords; data types, collations, authentication, or SQL behavior may change. A schema that is valid on the source version may no longer be compatible with the target version.

Common risk categories:

| Category | Example | Consequence |
|---|---|---|
| Version and upgrade path | Source version is not on a directly supported upgrade path | Upgrade is rejected or requires an intermediate version |
| Configuration | Variables or options were removed/renamed | Server fails to start or uses unexpected values |
| Schema and data | Column names collide with new keywords, incompatible partitions or data types | Check failures or inability to open objects |
| SQL and stored programs | Views, routines, or triggers rely on legacy syntax or behavior | Queries or background jobs fail after upgrade |
| Plugins and authentication | Plugins are no longer supported or clients are incompatible | Users cannot log in |
| Applications and drivers | Older connectors/clients do not support new protocols or authentication | Application connection errors or altered behavior |
| Replication and HA | Replicas, Router, Shell, or admin tools run incompatible versions | Topology loses sync or role-switching capability |

Pre-upgrade checks uncover issues early while the system is still running the old version. This reduces the risk of having to fix schemas or configurations after the upgrade window has already begun.

## 2. Identifying Source Version, Target Version, and Upgrade Path

Before running the tool, record the exact running version and the planned target version:

```sql
SELECT VERSION() AS server_version,
       @@version_comment AS distribution;

SHOW VARIABLES LIKE 'version_compile%';
```

Also identify:

- Whether it is MySQL Community Server or another compatible distribution.
- The full patch version, not just major/minor numbers.
- Operating system, CPU architecture, and installation method.
- Versions of MySQL Shell, Router, connectors/drivers, and active plugins.
- Source and target versions for every node in the topology.

### 2.1. Do Not Infer Upgrade Paths from Version Numbers

Supported upgrade paths depend on the source version, target version, and release-series guidelines. Do not assume you can upgrade directly across any major release. Read the target version's upgrade documentation and relevant release notes to determine:

- Whether the source version is permitted to upgrade directly or must go through an intermediate version.
- Whether a minimum patch version is required before switching major versions.
- Whether there are changes to data formats, the data dictionary, or pre-upgrade configuration requirements.
- Whether there are restrictions when upgrading from a fork or a third-party distribution.
- Whether there is a specific upgrade order for source, replicas, Router, Shell, or plugins.

For example, `8.4.0` can be used as an illustrative target in the commands below. In real deployments, substitute the exact target version chosen by your organization and confirm that the official upgrade path supports the current source version.

### 2.2. Choosing the Appropriate MySQL Shell Version

MySQL Shell has included the Upgrade Checker utility since the 8.0.13 series. Use a MySQL Shell version recent enough to recognize the target version and support the corresponding checks. For a target in a newer release series, do not use an overly old Shell and conclude the instance has no issues simply because the tool lacks the newer checks.

Check the Shell version:

```bash
mysqlsh --version
```

Use a supported MySQL Shell compatible with the target MySQL version. Read the Shell release notes if you need to run the checker against an older server to prepare for a newer target.

## 3. MySQL Shell Upgrade Checker

Upgrade Checker analyzes a MySQL Server instance to find issues that could block or affect an upgrade to the specified version. Check categories can include:

- Server version and upgrade prerequisites.
- Deprecated or removed configuration variables and options.
- Database, table, column, or routine names colliding with new keywords.
- Data types, partitioning, engines, and schema attributes requiring attention.
- Views, stored procedures, functions, triggers, and events with compatibility issues.
- Features or syntax no longer supported in the target version.
- Configuration or data conditions required by the target version.

The scope of checks varies by MySQL Shell version and target version. Review the checklist for the Shell version in use and read the full report rather than looking only at the summary line.

### 3.1. Running from the Command Line

Example of running the checker from a machine with MySQL Shell installed:

```bash
mysqlsh upgrade_check@mysql-source.example:3306 \
  -- util check-for-server-upgrade \
  --target-version=8.4.0 \
  --output-format=JSON
```

The command connects to the specified instance and checks against the target version. The `upgrade_check` account needs privileges to read metadata and run the check queries required by the utility. Avoid using the `root` account when a dedicated least-privilege account can be granted per the Shell version's documentation.

If you need to inspect the server configuration file, specify the config path using the option supported by your utility version, for example:

```bash
mysqlsh upgrade_check@mysql-source.example:3306 \
  -- util check-for-server-upgrade \
  --target-version=8.4.0 \
  --config-path=/etc/my.cnf \
  --output-format=JSON
```

The `/etc/my.cnf` path is a Linux example only. On Windows or other installations, specify the exact configuration file the instance actually uses. If the server starts with multiple configuration files or command-line arguments, inspect all configuration sources rather than supplying a single unrepresentative file.

Command-line option names can change across MySQL Shell releases. If a command does not accept an option, run the help output for that exact Shell version:

```bash
mysqlsh -- util check-for-server-upgrade --help
```

### 3.2. Running via the JavaScript API

You can connect with MySQL Shell and invoke the utility in JavaScript mode:

```javascript
util.checkForServerUpgrade(null, {
    targetVersion: "8.4.0",
    outputFormat: "TEXT"
});
```

Passing `null` uses Shell's current active connection. If passing separate connection details, use the `util.checkForServerUpgrade(connectionData, options)` form per the Shell version's API. Consult the API documentation when using options like `configPath`, `include`, or `exclude`, as supported options and behavior may change across releases.

### 3.3. Choosing the Report Format

`TEXT` is convenient for reading directly in a terminal. `JSON` is useful for storing artifacts, automated processing, or comparing results across runs.

Store the report along with:

- Checked host/instance and execution timestamp.
- Source server version.
- MySQL Shell version.
- Target version.
- Analyzed configuration file (if applicable).
- Account or identity running the check, per audit policy.
- Errors, warnings, notices, and any excluded checks.

Reports may contain hostnames, schema names, table names, and configuration details. Store them with appropriate access controls; do not include passwords or secrets.

## 4. Reading and Classifying Results

Do not look solely at an "upgrade check completed" message. Read every item and classify it by impact.

| Result | Interpretation | Action |
|---|---|---|
| ERROR | Issue that may block the upgrade or prevent the target from working properly | Investigate and resolve before proceeding |
| WARNING | Risk or change requiring evaluation; does not always block the upgrade | Identify affected applications/objects, test, and record a decision |
| NOTICE/INFO | Information about changes or points to be aware of | Read release notes, update runbooks, and test if relevant |
| Check could not execute | Missing privileges, unreadable config, or unmet check preconditions | Fix privileges/connectivity and re-run; never treat as PASS |

Severity names and formatting depend on the version. Some reports may use different labels. What matters is understanding the substance, scope, and remediation requirements of each finding.

### 4.1. Creating a Remediation List

For each finding, record:

1. Finding code or title in the report.
2. Affected database, table, column, routine, or configuration variable.
3. Source version and target version.
4. Consequence if left unchanged.
5. Remediation steps and corresponding migration/configuration change.
6. Owner and verified environment.
7. Checker result after remediation.

Example tracking table:

| Finding | Classification | Action Required | Closure Criteria |
|---|---|---|---|
| Column name collides with target keyword | ERROR/WARNING depending on finding | Rename via a compatible migration | Checker no longer flags it; application switched to the new name |
| Removed configuration variable | ERROR/WARNING | Remove or replace with a supported equivalent | New config tested on staging and server starts cleanly |
| Unsupported plugin | ERROR/WARNING | Replace plugin or confirm compatibility plan | Login and related features work on target |
| Legacy routine syntax | WARNING | Fix and run business tests | Routines, triggers, and events work properly on target |

Do not close a finding simply because the config file or schema was edited. Re-run the checker and perform functional tests to confirm.

## 5. Additional Table-Level Checks

In some cases, tables must be checked individually for compatibility. MySQL provides `CHECK TABLE ... FOR UPGRADE` and the `mysqlcheck` utility with the `--check-upgrade` option on supported versions.

Example of checking a single table:

```sql
CHECK TABLE shop.orders FOR UPGRADE;
```

Or checking tables across databases:

```bash
mysqlcheck --all-databases --check-upgrade \
  --user=upgrade_check --password
```

`mysqlcheck` can prompt for the password interactively. Do not pass passwords directly on the command line. Run checks with an appropriately privileged account and inspect results for each table.

Table checking has a narrower scope than Upgrade Checker. It does not replace checking configuration variables, plugins, keywords, stored programs, drivers, or upgrade paths. For large systems, assess load and runtime before checking all tables in production.

## 6. Items to Check Beyond Automated Reports

Upgrade Checker is a vital tool, but it does not know every behavior of your applications and infrastructure. Supplement it with the following checks.

### 6.1. Server Configuration

Save critical configuration variables:

```sql
SHOW VARIABLES;
```

In practice, export the output safely and focus on these groups:

- `sql_mode`, charset, and collation.
- InnoDB buffer pool, redo log, undo, flushing, and durability.
- Binary logs, GTID, retention, and replication.
- TLS, authentication plugins, and connection limits.
- Paths for data directory, temporary directory, logs, and plugin directory.
- Variables that are deprecated or have changed defaults between the two versions.

Do not copy the entire old configuration file onto the target and only fix lines that throw errors. Compare each option against the target version's documentation and keep only configurations that are genuinely needed.

### 6.2. Schema and Data

Inspect objects that could be affected:

- Database, table, column, index, constraint, and routine names that may collide with new keywords.
- Legacy data types, out-of-range values, and invalid data.
- Partitioning, storage engines, and indexes.
- Views, triggers, events, stored procedures, and stored functions.
- Charset/collation and string comparison rules.
- Foreign keys, CHECK constraints, and generated columns.

Metadata queries against `INFORMATION_SCHEMA` help inventory the schema. For critical tables, save `SHOW CREATE TABLE` and compare before/after in a test environment.

### 6.3. Plugins and Authentication

List active plugins and components:

```sql
SHOW PLUGINS;
```

Check compatibility of authentication plugins, audit plugins, keyrings, additional storage engines, UDFs, and third-party components. Confirm that application client libraries support the authentication method used by the target. Specifically, test logging in with actual application accounts rather than testing only administrative accounts.

### 6.4. Applications and Drivers

List every component connecting to MySQL:

- JDBC drivers, PHP drivers, Python connectors, Node.js drivers, or native clients.
- ORMs, migration frameworks, and query builders.
- Background jobs, ETL pipelines, CDC connectors, and backup tools.
- Dashboards, BI tools, monitoring agents, and administrative scripts.

Verify that driver versions support the target server, authentication, TLS, and active data types. Run tests for key queries under target-equivalent `sql_mode`, collation, and settings. A server-side checker cannot prove application code does not rely on legacy behavior.

### 6.5. Replication and HA

For source-replica topologies, InnoDB Cluster, or ClusterSet, check:

- Supported upgrade path for each node and the upgrade order.
- Version compatibility among source, replicas, MySQL Shell, and Router.
- GTIDs, replication channels, Group Replication plugin, and quorum state.
- Whether CDC connectors support the target version and binlog events.
- Role-switch, failover, and rollback plans across the topology.

Do not run the checker on a single node and treat that result as representative of the entire topology. Check each instance and each component type according to the upgrade plan.

## 7. Legacy Tools and Usage Limitations

### 7.1. `mysql_upgrade`

Starting in MySQL 8.0.16, many system upgrade tasks are performed automatically by the server when starting on the new version; the `mysql_upgrade` utility was deprecated and is no longer a mandatory step in the modern MySQL 8.0 workflow. In MySQL 8.4, `mysql_upgrade` was removed.

Do not use `mysql_upgrade` as a pre-upgrade compatibility evaluation tool. Use MySQL Shell Upgrade Checker to find issues to resolve before starting the target version. For older versions, strictly follow that version's upgrade documentation.

### 7.2. `mysqlcheck --check-upgrade`

This option supports table-level compatibility checking on supported versions. It is useful as a supplementary step, but does not replace the checker because it does not fully analyze configuration, plugins, stored programs, or application behavior.

### 7.3. Do Not Confuse the Checker with an Upgrade Tool

Upgrade Checker evaluates compatibility and reports issues. It does not automatically fix everything, does not migrate data to a new version, does not guarantee application compatibility, and does not replace backups. An error-free report is an important condition, but not a certificate guaranteeing the upgrade will succeed.

## 8. Pre-Upgrade Check Workflow

A repeatable workflow includes the following steps:

1. **Inventory:** record versions, configuration, schema, plugins, applications, drivers, topology, and data size.
2. **Select target:** confirm the target version and officially supported upgrade path.
3. **Prepare tools:** install an appropriate MySQL Shell and verify permissions for the checker account.
4. **Capture state:** save configs, plugin lists, schema DDL, GTID/replication status, and current backups.
5. **Run Upgrade Checker:** check each instance against the target version, saving TEXT/JSON output and config files if needed.
6. **Run supplementary checks:** check tables, applications, drivers, authentication, plugins, replication, and integrations.
7. **Classify findings:** resolve ERRORs, evaluate WARNINGs, and record NOTICEs and checks that could not run.
8. **Remediate:** apply reviewed migrations/configuration changes; do not edit things directly without recording them.
9. **Re-run checker:** confirm issues are resolved and save the updated report.
10. **Rehearse in staging:** restore a backup or production-like clone, execute the upgrade following the planned procedure, and run business tests.
11. **Assess readiness:** confirm backup/restore, timings, disk space, monitoring, rollback/failover, and owners.
12. **Decide production window:** begin only when acceptance criteria are met and an incident handling plan is ready.

## 9. Testing in a Staging Environment

The checker does not replace a trial upgrade. Staging should closely mirror production in versions, configuration, plugins, schema, data volume, and data characteristics. Use a sanitized backup or clone compliant with security policy.

During the rehearsal:

- Follow the exact planned upgrade sequence.
- Measure downtime, startup time, and post-upgrade task completion time.
- Inspect error logs and warnings after the first startup.
- Run smoke tests for connections, read/write queries, transactions, and stored programs.
- Test critical business flows such as order creation, payments, refunds, and reporting.
- Check background jobs, event scheduler, replication, CDC, backups, and monitoring.
- Measure key query performance and compare against the pre-upgrade baseline.
- Test restoring backups into a separate environment to confirm recoverability.

Do not rehearse solely on an empty database. Some errors appear only with real data containing edge-case values, large tables, partitions, or large numbers of objects.

## 10. Backups, Rollback, and Recovery Plans

Before upgrading production:

- Have a complete backup with verified integrity.
- Have copies of required keyrings/KMS materials if data is encrypted.
- Have tested restoring the backup into an independent environment.
- Identify binlogs/GTIDs to retain if PITR is required.
- Record pre-upgrade configurations, accounts, plugins, and versions.
- Define a supported path to return to the old version.

Do not assume you can downgrade by reinstalling the old MySQL binary over a data directory already upgraded by the new version. Downgrades may be unsupported or require a dedicated procedure. The safe approach is usually restoring a pre-upgrade backup into an environment running the old version, then switching traffic according to a tested plan.

If using replication to assist version cutover, check source/replica compatibility limits and failover behavior at each stage. Do not allow a newer-version node to accept writes and expect an older-version node to resume acting as primary without a supported procedure.

## 11. Pre-Upgrade Readiness Criteria

Use the following conditions as a decision gate:

| Condition | Required Evidence |
|---|---|
| Supported upgrade path | Target documentation confirms source version and intermediate steps |
| Appropriate tools | MySQL Shell with Upgrade Checker supporting the target, and report saved |
| No blocking errors | All ERRORs resolved and checker re-run |
| Warnings evaluated | Every WARNING has an owner, decision, and corresponding test |
| Compatible configuration | Configuration files reviewed for target and tested on staging |
| Compatible applications | Drivers, plugins, queries, and business flows tested |
| Topology ready | Every node, replication, Router, and failover plan evaluated |
| Usable backups | Backup completed, checksum/validation passed, and test restore succeeded |
| Clear runbook | Sequence of operations, monitoring, abort criteria, and recovery plan documented |
| Accountable owners | Operations owner, business sign-off owner, and communication channels assigned |

Do not mark an untestable item as PASS. Document limitations and risk acceptance decisions per organizational process.

## 12. Common Issues When Running Upgrade Checker

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Utility does not recognize target version | MySQL Shell is too old or target is unsupported by utility | Install an appropriate Shell and verify target release |
| Cannot connect to server | Wrong endpoint, TLS, firewall, or authentication | Check connectivity and test with a compatible client |
| Checker reports insufficient privileges | Account cannot read metadata needed for checks | Grant minimum privileges per utility docs and re-run |
| Cannot parse config | Wrong path or file does not reflect actual config | Identify the active config file and startup arguments |
| Many warnings reported | Server uses deprecated features or soon-to-change behavior | Evaluate each finding for target, remediate, and test |
| Checker misses application errors | Checker evaluates only server/schema/config within its scope | Add driver, query, stored program, and business tests |
| Results differ across nodes | Topology configuration or schema has drifted | Run checker separately on each node and compare reports |
| `mysqlcheck --check-upgrade` reports table errors | Table or format requires handling before target | Read details, verify backups, and follow version guidance |

Preserve original reports prior to fixes for comparison. Do not ignore a finding just because it appears on a lightly used node; that node could become primary after a failover.

## 13. Practical Scenario

A commerce system runs MySQL 8.0 and plans to move to MySQL 8.4. The system has one source, two replicas, MySQL Router, a CDC connector, and multiple JDBC applications. The operations team needs to confirm compatibility before scheduling the upgrade.

Execute in a lab environment:

1. Record exact versions of all MySQL Servers, MySQL Shell, Router, JDBC drivers, and the CDC connector.
2. Read the target upgrade documentation to confirm the upgrade path from the source version.
3. Install a compatible MySQL Shell and run `mysqlsh --version`.
4. Run Upgrade Checker on the source and each replica with the chosen target version; save JSON reports.
5. If configuration files exist, also run the checker with `--config-path` pointing to each instance's actual file.
6. Classify every ERROR, WARNING, NOTICE, and unexecuted check.
7. Run `mysqlcheck --all-databases --check-upgrade` or `CHECK TABLE ... FOR UPGRADE` on appropriate tables.
8. Inspect plugins, authentication, views, routines, triggers, events, SQL mode, collation, and critical queries.
9. Remediate issues via reviewed migrations/configuration changes, then re-run the checker.
10. Restore a backup into staging, test the upgrade, run smoke tests, verify replication/Router/CDC, and test restoring the pre-upgrade backup.
11. Produce a readiness report with timings, remaining risks, RPO/RTO, and sign-off owners.

**Self-assessment questions:**

- Why must the supported upgrade path be confirmed before running the checker?
- What does MySQL Shell Upgrade Checker verify, and what can it not prove?
- Why does `mysqlcheck --check-upgrade` not replace Upgrade Checker?
- Why must the checker be run on every node in the topology?
- Why is an ERROR-free report still insufficient to authorize a production upgrade?
- Since MySQL 8.0.16, how has the role of `mysql_upgrade` changed?
- Why should you not assume you can downgrade by reinstalling old binaries over a newer data directory?
- What evidence is required before marking a system ready for upgrade?

## Conclusion

Pre-upgrade checking must combine MySQL Shell Upgrade Checker, table checks, configuration and plugin reviews, application testing, and topology evaluation. Confirm the supported upgrade path, remediate and re-check every finding, rehearse on staging with production-like data, and prove backups can be restored. Begin the upgrade only when reports, tests, and the runbook all confirm the system is ready.
