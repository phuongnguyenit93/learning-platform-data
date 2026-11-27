# Release Notes, Removed Features, and Changed Configuration Variables

In the `DATABASE_MYSQL` module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, access control, backups, and handling relational database operational issues. This lesson guides you through reading release notes and translating information about new features, deprecated features, removed features, and configuration variable changes into a testable upgrade plan.

Upgrading MySQL is not merely replacing the server binary. A new version can remove startup options, rename statements, change authentication plugins, alter default variable values, or modify optimizer behavior. These changes can prevent the server from starting, break application logins, stop replication, or change workload performance. Therefore, you must cross-check release notes version by version, inventory active configuration, and test compatibility before upgrading production.

## 1. What Do Release Notes Tell You?

Release notes document the changes in a release. For MySQL, read the server release notes, the Reference Manual, and the documentation for any connectors or plugins used by your system.

Key sections typically include:

| Change Category | Meaning | Questions to Answer During an Upgrade |
|---|---|---|
| Added | New features, statements, variables, or options. | Which features can benefit the system? Are new configurations or privileges required? |
| Changed | Changes to behavior, default values, limits, or execution methods. | Will the current workload be affected even without changing configuration? |
| Deprecated | Features that still work but are marked obsolete and may be removed in a future release. | Which source code, scripts, configs, and tools still use this feature? |
| Removed | Features, variables, options, or syntax that have been removed. | Which components will fail immediately when running on the target version? |
| Fixed | Bugs that have been resolved. | Does a fix alter behavior that the application or a workflow relies on? |
| Security | Vulnerabilities or security changes. | Do plugins, certificates, privileges, protocols, or operational procedures need to change? |

Do not read only the "What is New" section. Read deprecation/removal notes, configuration notes, security notes, replication notes, InnoDB notes, SQL syntax notes, and bug fixes relevant to your active workload. A default value change can be just as consequential as a removed feature, even if it produces no syntax errors.

## 2. Identifying the Exact Source and Target Versions

Before comparing release notes, record the exact version of each environment:

```sql
SELECT VERSION() AS server_version,
       @@version_comment AS distribution;
```

Also check the server and client binary versions:

```bash
mysqld --version
mysql --version
```

These two values can differ because the client and server may be installed from different packages or upgrade schedules. In a multi-node system, list the versions of the source, replicas, backup servers, administrative tools, and application connectors.

### Reading Release Notes Step by Step

Do not compare only the source version's release notes with the target version's if the upgrade spans multiple branches. Read the changes for every intermediate version along the supported upgrade path, especially when moving from MySQL 5.7 to 8.0 or from 8.0 to 8.4.

For example, a system upgrading from 8.0.22 to 8.4 must review changes from subsequent 8.0 releases, changes in the 8.1/8.2/8.3 series if they are part of the chosen path, and requirements specific to 8.4. Never assume a feature that works in the source version still exists in the target version.

MySQL has release series with different support policies. Determine whether the LTS or Innovation series fits your operational policy, then select the documentation for that series. Read the release notes page for the actual version rather than copying configuration from an older article solely because the major version number matches.

## 3. Distinguishing Deprecated, Removed, and Changed Defaults

These three states carry different levels of impact:

1. **Deprecated:** the feature still works, but warnings appear or documentation recommends migrating to a new approach. This is the right time to update code and configs before the next upgrade.
2. **Removed:** the feature is no longer provided by the server. Statements, variables, or options can cause errors at startup or during application execution.
3. **Changed default:** the variable name remains valid, but its default value has changed. The server may start normally while performance, replication behavior, security, or resource usage changes.

Do not treat deprecation warnings as errors that can be ignored indefinitely. Continuing to use deprecated features compounds the risk and remediation cost of every subsequent upgrade. Maintain a list of deprecations, owners, target replacement versions, and deadlines.

## 4. Practical Changes to Know When Moving from MySQL 8.0 to 8.4

The following examples illustrate how to read version milestones. This list does not replace the full release notes for the target version.

### Replication Statements Changed Terminology

Starting in MySQL 8.0.23, `CHANGE MASTER TO` was marked deprecated; the new statement is `CHANGE REPLICATION SOURCE TO`. Names such as `START SLAVE`, `STOP SLAVE`, and `SHOW SLAVE STATUS` also have corresponding new names:

| Old Syntax | New Syntax to Use |
|---|---|
| `CHANGE MASTER TO` | `CHANGE REPLICATION SOURCE TO` |
| `START SLAVE` | `START REPLICA` |
| `STOP SLAVE` | `STOP REPLICA` |
| `SHOW SLAVE STATUS` | `SHOW REPLICA STATUS` |
| `RESET SLAVE` | `RESET REPLICA` |

Example of configuring a replica connection using the new syntax:

```sql
CHANGE REPLICATION SOURCE TO
    SOURCE_HOST = 'mysql-source.example.net',
    SOURCE_USER = 'replication_user',
    SOURCE_PASSWORD = 'GET_FROM_SECRET_STORE',
    SOURCE_AUTO_POSITION = 1;

START REPLICA;
SHOW REPLICA STATUS\G
```

The password in the example is just a placeholder. Retrieve secrets from a secret manager and avoid writing credentials into migration files or logs. During an upgrade, search for legacy statements in deployment scripts, runbooks, scheduled jobs, monitoring tools, and operational documentation. A command may not appear in application code yet still be executed whenever a DBA handles an incident.

### The mysql_native_password Authentication Plugin

`mysql_native_password` was marked deprecated in MySQL 8.0.34, disabled by default in MySQL 8.4.0, and removed from the server in MySQL 9.0.0. Accounts still using this plugin may fail to log in after upgrading to 8.4 unless the plugin is re-enabled.

Check which plugin each account uses:

```sql
SELECT user, host, plugin
FROM mysql.user
ORDER BY user, host;
```

Check the list of active plugins:

```sql
SHOW PLUGINS;
```

The migration plan typically involves confirming that drivers/clients support `caching_sha2_password`, upgrading connectors if necessary, and then switching accounts in a test environment:

```sql
ALTER USER 'app_user'@'10.20.5.18'
    IDENTIFIED WITH caching_sha2_password
    BY 'NEW_PASSWORD_FROM_VAULT';
```

Test TLS connections, public key retrieval mechanisms where needed, connection pools, and background jobs before applying changes to production accounts. Do not re-enable the legacy plugin as a long-term workaround if the goal is to upgrade to a version that removes it.

### Removal of the default_authentication_plugin Variable

The `default_authentication_plugin` variable was marked deprecated in MySQL 8.0.27 and removed in MySQL 8.4.0. The MySQL 8.4 documentation instructs using `authentication_policy` instead.

If a configuration file still contains:

```ini
[mysqld]
default_authentication_plugin=caching_sha2_password
```

review and migrate it to an authentication policy configuration matching the target version's actual requirements. Do not rename the variable mechanically without understanding the syntax and semantics of `authentication_policy`; read the variable description in the Reference Manual for the exact version. Also check how users are created in provisioning scripts, because existing accounts do not automatically change their authentication plugin simply because the server default changes.

### Removal of the expire_logs_days Variable

`expire_logs_days` was removed in MySQL 8.2.0. Binary log retention should be configured using `binlog_expire_logs_seconds`:

```ini
[mysqld]
binlog_expire_logs_seconds=1209600
```

The value above corresponds to 14 days. Choose the retention period based on how long a replica may be offline, rebuild times, delayed replicas, CDC consumers, and point-in-time recovery requirements. Before upgrading, inspect all configuration files, automation, and dashboards that still read or write `expire_logs_days`.

### Legacy SSL Options and TLS Status Variables

The server options `--ssl`, `--admin-ssl` and the variables `have_ssl`, `have_openssl` were marked deprecated in MySQL 8.0.26 and removed in MySQL 8.4.0. Release notes instruct using `--tls-version` and `--admin-tls-version` to configure TLS protocol versions. When checking connection status, use the TLS variables and metrics currently supported in the target version instead of relying on `have_ssl` or `have_openssl`.

For application connections, verify the CA, certificate, private key, TLS version, ciphers, and server identity verification. Do not merely delete old options and assume connections remain encrypted as expected.

## 5. InnoDB Default Value Changes in MySQL 8.4

An upgrade can complete without errors yet still alter workload behavior because variables keep the same names while taking on different defaults. For example, several InnoDB defaults in MySQL 8.4 differ from MySQL 8.0:

| Variable | MySQL 8.0 Default | MySQL 8.4 Default | Aspects to Test |
|---|---:|---:|---|
| `innodb_change_buffering` | `all` | `none` | Write behavior and I/O with secondary indexes. |
| `innodb_adaptive_hash_index` | `ON` | `OFF` | Performance of read workloads with repeated lookups. |
| `innodb_log_buffer_size` | 16 MiB | 64 MiB | Memory usage and large write transactions. |
| `innodb_io_capacity` | 200 | 10000 | Background I/O rate and storage capability. |
| `innodb_flush_method` on Linux | `fsync` | `O_DIRECT` if supported, otherwise `fsync` | I/O behavior, OS cache, and storage devices. |
| `temptable_max_ram` | 1 GiB | 3% of total memory, default value between 1–4 GiB | RAM consumption by temporary tables. |

The values in the table are defaults for the stated versions, not universal recommendations for every server. If the configuration file does not set a variable, the new version may adopt the new default. If the configuration file sets an explicit value, the server may continue using that value, provided the variable is still supported. Therefore, compare both default values and actual runtime values.

## 6. Inventorying Effective Configuration Variables

Do not look only in `my.cnf` or `my.ini`. Configuration values can come from included files, command-line flags, runtime variables, `SET PERSIST`, or server defaults.

### Retrieving Runtime Variables

```sql
SHOW GLOBAL VARIABLES;
```

Or a query that can be sorted/filtered:

```sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.global_variables
ORDER BY VARIABLE_NAME;
```

### Finding Where Variables Are Set

On versions that support `performance_schema.variables_info`, you can view the source of each current value:

```sql
SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH,
    SET_TIME,
    SET_USER,
    SET_HOST
FROM performance_schema.variables_info
WHERE VARIABLE_NAME IN (
    'default_authentication_plugin',
    'binlog_expire_logs_seconds',
    'innodb_change_buffering',
    'innodb_adaptive_hash_index'
)
ORDER BY VARIABLE_NAME;
```

Removed variable names may no longer appear in the target version's runtime views. On the older version, `VARIABLE_SOURCE` and `VARIABLE_PATH` help identify whether a value comes from the command line, an option file, a persisted value, or a default. Check the Performance Schema table structure for your exact server version.

### Checking Values Saved with SET PERSIST

```sql
SELECT *
FROM performance_schema.persisted_variables
ORDER BY VARIABLE_NAME;
```

Persisted values are stored separately from ordinary configuration files. A variable that no longer exists can trigger warnings or prevent the server from starting depending on the version and configuration. Inspect this list before upgrading, and save a copy for cross-checking and controlled remediation.

### Searching for Options in Config Files and Scripts

Inventory all primary configuration files, included files, service units, container entrypoints, Helm charts, Ansible/Terraform manifests, backup/restore scripts, provisioning, monitoring, and runbooks. Example of searching for known names in Linux configuration directories:

```bash
grep -RniE 'default_authentication_plugin|expire_logs_days|have_ssl|have_openssl|master_info_repository|relay_log_info_repository' /etc/mysql /etc/my.cnf* 2>/dev/null
```

On Windows, check `my.ini`, the MySQL configuration directory, and the service command line. The `grep` command is a Linux example only; use search tools appropriate for your operating system and actual deployment layout.

## 7. Pre-Upgrade Compatibility Checks

### Using MySQL Shell Upgrade Checker

MySQL Shell provides the `util.checkForServerUpgrade()` utility to check a source server against a target version, detecting structural, syntax, feature, and configuration issues that could block an upgrade.

Example in MySQL Shell in JavaScript mode, after connecting to the source server:

```javascript
util.checkForServerUpgrade({
    targetVersion: "8.4.0"
});
```

Replace `8.4.0` with the actual target version. Read the full output and address every error and warning. Upgrade Checker does not replace reading release notes, testing applications, verifying third-party plugins, or testing backup restores.

### Validating Server Configuration Before Restart

On supported versions, you can run:

```bash
mysqld --defaults-file=/etc/my.cnf --validate-config
```

This command checks for certain errors in option files without starting the server normally. Adjust the path syntax to match your operating system and config file location. Passing config validation does not prove that all plugins, applications, or replication will be compatible.

### Checking Connections and Plugins

List drivers and connectors by application: Java Connector/J, .NET, Python, Node.js, PHP, ODBC, JDBC pools, ORMs, proxies, and administrative tools. Verify that driver versions support the target authentication protocols, TLS, and server version. Inspect plugins, components, UDFs, and third-party engines, as some plugins may have changed APIs or been removed between versions.

## 8. Safe Configuration Migration Process

A practical process can follow these steps:

1. **Snapshot the source state.** Record the version, runtime variables, persisted variables, plugins, components, accounts, and file configurations.
2. **Read release notes per stage.** Build a table of added/changed/deprecated/removed items for every version along the path.
3. **Build a configuration matrix.** For each variable, record its current value, source, status in the target version, replacement value, owner, and required tests.
4. **Remediate deprecations early.** Update deprecated statements, plugins, variables, and options in code, scripts, automation, and runbooks while they can still be tested on the source version.
5. **Handle removals.** Remove or replace unsupported options; verify new configuration against the target version's documentation.
6. **Evaluate changed defaults.** Compare runtime values against new defaults, run benchmarks, and tune deliberately rather than blindly preserving every old value.
7. **Test in staging.** Restore a copy of production data, upgrade along the planned path, run Upgrade Checker, and test applications, replication, and backups.
8. **Prepare rollback.** Verify backups can be restored, retain binary logs, keep pre-upgrade configs, and define abort criteria. Do not assume a data directory can be downgraded directly to an older version.
9. **Deploy to production.** Follow the runbook, monitoring startup logs, error logs, application connections, replication lag, performance, and disk usage.
10. **Post-upgrade reconciliation.** Confirm versions, plugins, runtime variables, data, fresh backups, and recovery capability; update operational documentation.

## 9. Sample Configuration Compatibility Matrix

Example matrix when preparing to migrate a system from MySQL 8.0 to 8.4:

| Component | Status/Change | Pre-Upgrade Action | Completion Evidence |
|---|---|---|---|
| `CHANGE MASTER TO` | Deprecated since 8.0.23 | Change to `CHANGE REPLICATION SOURCE TO` in scripts and runbooks. | Replication configured and started on staging. |
| `mysql_native_password` | Deprecated 8.0.34; disabled by default 8.4 | Inventory users, upgrade connectors, and migrate accounts to an appropriate plugin. | All applications log in successfully with real accounts. |
| `default_authentication_plugin` | Deprecated 8.0.27; removed 8.4 | Migrate policy to `authentication_policy`, review provisioning. | Server starts and new accounts are created with the right plugin. |
| `expire_logs_days` | Removed 8.2 | Switch to `binlog_expire_logs_seconds`. | Retention meets replica and PITR requirements. |
| `have_ssl`, `have_openssl` | Removed 8.4 | Update monitoring to current TLS checks. | Dashboards and alerts reflect actual TLS status. |
| InnoDB defaults | Several defaults changed in 8.4 | Benchmark workload, review buffer, I/O, and temporary tables. | Before/after comparison of latency, throughput, I/O, and memory. |

This is a sample matrix. Add every variable, plugin, and option present in your specific system. Do not mark a row complete merely because the old config line was deleted; tests must prove the new behavior meets requirements.

## 10. Common Upgrade Failures

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Server fails to start after upgrade | Removed option or variable, misspelled name, invalid value, or missing plugin. | Read the error log, inspect config files and persisted variables, and replace with supported options. |
| Application reports authentication errors | Account uses a disabled plugin or client does not support the new plugin. | Check `mysql.user.plugin`, driver version, and TLS; test migrating the account on staging. |
| Replication fails to run | Scripts still use old syntax, replication plugins or variables changed, or connection settings are incompatible. | Use new source/replica statements, inspect error fields and GTID state. |
| Binary logs expire early or setting has no effect | Removed `expire_logs_days` is used or new retention was not converted properly. | Configure `binlog_expire_logs_seconds`, verify runtime value and retention policy. |
| Performance changes despite unchanged config | InnoDB default values or optimizer behavior changed. | Compare runtime variables, benchmark the same workload, and tune in a controlled manner. |
| Monitoring reports unknown TLS status | Dashboards rely on removed `have_ssl` or `have_openssl`. | Switch to currently supported TLS variables, connection states, and metrics. |
| Staging passes but production fails | Staging lacks matching plugins, data, configs, connectors, or workload. | Increase environment parity and rehearse on a closer copy of production. |

## 11. Practical Exercise

A system is running MySQL 8.0 and plans to upgrade to MySQL 8.4. Its configuration still includes `default_authentication_plugin`, `expire_logs_days`, some accounts using `mysql_native_password`, and replication scripts using `CHANGE MASTER TO`. Perform the following in a test environment:

1. Record the source version using `SELECT VERSION()` and export the lists of runtime variables, persisted variables, plugins, and authentication accounts.
2. Read the release notes from the source version to the target version; record relevant deprecated, removed, and changed-default milestones.
3. Build a compatibility matrix for the four items above, identifying replacements and owners.
4. Convert replication scripts to the new source/replica syntax; configure binary log retention using the supported variable.
5. Upgrade application connectors if needed, migrate a test account to `caching_sha2_password`, and verify connectivity.
6. Test the authentication policy using `authentication_policy`; remove the legacy variable from configuration and provisioning.
7. Run MySQL Shell Upgrade Checker, validate option files, upgrade staging, and run smoke tests.
8. Benchmark a representative workload before and after, paying special attention to InnoDB variables with changed defaults.
9. Test backup restore and verify replication, binary logs, privileges, TLS, data, and the application.
10. Finalize a report covering discovered issues, configuration changes, test results, remaining risks, and criteria for approving the production upgrade.

After completing the exercise, learners should be able to explain why release notes must be read stage by stage, why deprecated differs from removed, why default changes can affect performance without causing startup errors, and why inventorying runtime/persisted configuration matters more than merely searching for a line in `my.cnf`. This is the foundation for turning MySQL upgrades into a predictable, testable, and controllable process.

## Official References

- [MySQL 8.4 Reference Manual: What Is New in MySQL 8.4 since MySQL 8.0](https://dev.mysql.com/doc/refman/8.4/en/mysql-nutshell.html)
- [MySQL 8.4 Reference Manual: Server and Status Variables and Options Added, Deprecated, or Removed](https://dev.mysql.com/doc/refman/8.4/en/added-deprecated-removed.html)
- [MySQL 8.0 Release Notes: Changes in MySQL 8.0.23](https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-23.html)
- [MySQL 8.4 Reference Manual: Native Pluggable Authentication](https://dev.mysql.com/doc/refman/8.4/en/native-pluggable-authentication.html)
