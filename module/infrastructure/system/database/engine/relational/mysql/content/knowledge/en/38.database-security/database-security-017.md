# Auditing Anonymous Accounts, Excessive Privileges, and Unused Accounts

In the `DATABASE_MYSQL` module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, privilege management, backups, and handling operational issues. This lesson covers inventorying accounts, detecting anonymous accounts, identifying excessive privileges, recognizing accounts that may have outlived their purpose, and revoking privileges under a controlled workflow.

Examples use MySQL 8.0. Inspecting account metadata requires appropriate read privileges on system objects. Only run modifying statements on verified accounts within your environment and governance procedures.

## 1. Why Conduct Periodic Account Reviews?

Every MySQL account is a potential entry point into the system. Over time, test accounts, accounts belonging to personnel who changed roles, legacy service accounts, or temporary privileges granted during incident response can remain behind. Left unreviewed, they increase the number of identities open to abuse and complicate access investigations.

A review cycle should answer four questions:

- Which accounts can log in, and from which hosts are they permitted to connect?
- Are there anonymous accounts or accounts using overly broad hosts?
- Which direct privileges and role-inherited privileges does each account hold?
- Which accounts no longer have a confirmed owner, dependent application, or business justification?

You cannot conclude an account is unused solely from its username, password change date, or the absence of an active session right now. Combine MySQL metadata with login logs, service catalogs, assigned owners, and owner confirmation.

## 2. Inventorying Accounts and Detecting Anonymous Accounts

In MySQL, an account identity comprises both username and host. For example, `'app_user'@'localhost'` and `'app_user'@'10.20.5.12'` are two distinct accounts. Therefore, every inventory report and revocation operation must record both components in full.

### Listing Accounts

On MySQL 8.0, you can list accounts along with their authentication plugin and lock state as follows:

```sql
SELECT
    User,
    Host,
    plugin,
    account_locked,
    password_expired,
    password_last_changed
FROM mysql.user
ORDER BY User, Host;
```

Do not query or include `authentication_string` in routine inventory reports. That is sensitive credential data; review reports need only attributes required for identification and governance.

### Finding Anonymous Accounts

Anonymous accounts have an empty string for `User`. The following query lists all such accounts:

```sql
SELECT
    User,
    Host,
    plugin,
    account_locked
FROM mysql.user
WHERE User = ''
ORDER BY Host;
```

An anonymous account does not require the client to supply a specific MySQL username to match that identity. When paired with a matching host configuration, it can create an unexpected login path—especially if administrators mistakenly assume every connection must match a named user.

If an anonymous account is found, determine its host, status, usage history, and reason for existing. In typical application environments, anonymous accounts rarely have a valid need; confirm with owners and assess impact before removing them.

Once verified as no longer needed, drop the exact user/host pair returned. For example, only when the inventory returns this exact account:

```sql
DROP USER ''@'localhost';
```

Do not assume an anonymous account's host is `localhost`. Multiple anonymous accounts with different hosts can exist; handle each verified identity individually. If logins need to be paused during investigation, use `ALTER USER ''@'localhost' ACCOUNT LOCK` with the account's actual host.

### Reviewing Overly Broad Hosts

Check accounts with host `%`:

```sql
SELECT User, Host, account_locked
FROM mysql.user
WHERE Host = '%'
ORDER BY User;
```

Host `%` matches many connection sources, making the login surface wider than intended. However, not every account using `%` is automatically wrong: some systems may need connections from multiple application hosts. Cross-check against network diagrams, firewalls, TLS, granted privileges, and approved connection-source lists. Where possible, narrow the host to specific hostnames or addresses matching the architecture.

## 3. Reviewing Direct Privileges Across Each Scope

MySQL can grant privileges at multiple scopes: global (server-wide), schema, table, and column. An account may show only a few direct privileges at one level while holding broader privileges at another. Thus, checking a single privilege level or looking only at the username is insufficient.

### Checking Global Privileges

Example checking global privileges for `orders_app`:

```sql
SELECT
    GRANTEE,
    PRIVILEGE_TYPE,
    IS_GRANTABLE
FROM information_schema.USER_PRIVILEGES
WHERE GRANTEE = CONCAT(QUOTE('orders_app'), '@', QUOTE('10.20.5.12'))
ORDER BY PRIVILEGE_TYPE;
```

Global privileges apply across the entire server and usually deserve closer scrutiny than privileges confined to one schema or table. Administrative privileges, server file read/write privileges, account management privileges, or delegation rights require a clear business justification and owner. In particular, `IS_GRANTABLE = 'YES'` indicates the account can grant that privilege onward; this attribute requires dedicated inspection.

### Checking Schema Privileges

```sql
SELECT
    TABLE_SCHEMA,
    PRIVILEGE_TYPE,
    IS_GRANTABLE
FROM information_schema.SCHEMA_PRIVILEGES
WHERE GRANTEE = CONCAT(QUOTE('orders_app'), '@', QUOTE('10.20.5.12'))
ORDER BY TABLE_SCHEMA, PRIVILEGE_TYPE;
```

This query finds privileges applying to an entire schema. For instance, if a service only reads data in `shop`, schema-level `SELECT` may fit; `INSERT`, `UPDATE`, `DELETE`, `DROP`, or `ALTER` should be checked against actual functionality.

### Checking Table and Column Privileges

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    PRIVILEGE_TYPE,
    IS_GRANTABLE
FROM information_schema.TABLE_PRIVILEGES
WHERE GRANTEE = CONCAT(QUOTE('orders_app'), '@', QUOTE('10.20.5.12'))
ORDER BY TABLE_SCHEMA, TABLE_NAME, PRIVILEGE_TYPE;
```

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    PRIVILEGE_TYPE
FROM information_schema.COLUMN_PRIVILEGES
WHERE GRANTEE = CONCAT(QUOTE('orders_app'), '@', QUOTE('10.20.5.12'))
ORDER BY TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, PRIVILEGE_TYPE;
```

Table or column privileges often let you restrict an application to the exact data it needs. During reviews, pay close attention to write, delete, schema-altering privileges, and access to sensitive columns. A reporting account that only reads a few tables should not routinely hold data-modification rights or read access across all schemas.

### Cross-Checking with SHOW GRANTS

`SHOW GRANTS` presents the privileges granted to an account:

```sql
SHOW GRANTS FOR 'orders_app'@'10.20.5.12';
```

This is a helpful verification step because the output displays corresponding `GRANT` statements, including role assignments. Save output into audit records per internal policy and avoid placing unnecessary sensitive details into shared logs.

## 4. Reviewing Roles and Inherited Privileges

Since MySQL 8.0, roles group privileges by function and assign those groups to multiple accounts. When auditing an account, inspect both direct grants and assigned roles. An account may appear minimally privileged when looking only at direct grants, yet an activated role can confer broad read or write privileges.

List roles directly assigned to an account:

```sql
SELECT
    FROM_USER AS role_name,
    FROM_HOST AS role_host,
    WITH_ADMIN_OPTION
FROM mysql.role_edges
WHERE TO_USER = 'orders_app'
  AND TO_HOST = '10.20.5.12'
ORDER BY FROM_USER, FROM_HOST;
```

In `mysql.role_edges`, `FROM_USER`/`FROM_HOST` is the granted role and `TO_USER`/`TO_HOST` is the recipient account or role. `WITH_ADMIN_OPTION` indicates whether the recipient can administer assigning that role. If a role is granted to another role, continue tracing the inheritance chain.

Check an account's default roles:

```sql
SELECT
    USER,
    HOST,
    DEFAULT_ROLE_USER,
    DEFAULT_ROLE_HOST
FROM mysql.default_roles
WHERE USER = 'orders_app'
  AND HOST = '10.20.5.12';
```

Within a login session, you can see the currently active roles with:

```sql
SELECT CURRENT_ROLE();
```

For a complete assessment, inspect `SHOW GRANTS` for the account, its assigned roles, and `SHOW GRANTS` for each related role. Never conclude an account is safe merely because its direct privileges are sparse; inherited privileges can substantially expand access scope.

## 5. Identifying Unused Accounts

MySQL does not provide a reliable `last_login` field in `mysql.user` for administrators to conclude which accounts are unused. `password_last_changed` is when the password was last changed, not when the account last logged in. Not seeing an account in `SHOW PROCESSLIST` only shows no session is currently visible; it does not prove the account is dormant.

### Using Connection Counters as a Reference Signal

If Performance Schema is enabled and account summary tables are populated, you can inspect current connections and total connections recorded since statistics were initialized or reset:

```sql
SELECT
    USER,
    HOST,
    CURRENT_CONNECTIONS,
    TOTAL_CONNECTIONS
FROM performance_schema.accounts
ORDER BY TOTAL_CONNECTIONS, USER, HOST;
```

These counters help spot accounts with few or zero connections during the current statistics window. They do not record a last-login timestamp and can reset on server restart or statistics reset. Therefore, never use `TOTAL_CONNECTIONS = 0` as the sole evidence to drop an account.

### Combining Logs and Service Catalogs

To confirm whether an account is still active, combine multiple sources:

- Audit logs or connection logs recording successful logins, failed logins, and disconnections.
- Service catalogs, deployment configs, secret managers, and cron schedules to find applications still referencing the account.
- Application owners or operations teams confirming purpose, usage schedule, and replacement plans.
- Performance Schema counters and active session lists as supplementary recent-activity signals.

If the system lacks login logs covering a long enough window, document this limitation and observe across an appropriate business cycle before revoking. Never enable the general log in production solely to hunt for old accounts without evaluating performance impact, disk volume, sensitive data exposure, and retention policies. Prefer already-operated, approved audit logs or connection log sources.

## 6. Narrowing Privileges and Revoking Accounts

Once excessive privileges are identified, determine which privileges are no longer needed and at what exact scope before running `REVOKE`. For example, revoking `UPDATE` on the orders table:

```sql
REVOKE UPDATE
ON shop.orders
FROM 'orders_app'@'10.20.5.12';
```

If an account holds a role that is no longer needed, revoke that role separately:

```sql
REVOKE 'reporting_role'@'localhost'
FROM 'orders_app'@'10.20.5.12';
```

Replace `reporting_role` and the host with the exact role found in your inventory. Revoking direct privileges does not substitute for revoking roles; likewise, revoking a role does not automatically remove privileges granted directly to the account.

If you need to revoke all direct privileges and delegation options from an account, MySQL supports:

```sql
REVOKE ALL PRIVILEGES, GRANT OPTION
FROM 'orders_app'@'10.20.5.12';
```

This statement does not replace revoking assigned roles. Re-check `SHOW GRANTS` and role edges after making changes to verify the final state. Revoking privileges can break an application if a feature still depends on them; test with the service owner and monitor after deployment.

### Locking an Account Before Dropping It

For an account suspected of being unused that cannot yet be immediately verified, lock it to block new logins during an observation window:

```sql
ALTER USER 'old_batch_app'@'10.20.5.30' ACCOUNT LOCK;
```

Locking an account does not terminate previously connected sessions. If active access must be cut off, inspect and terminate existing sessions per operational procedures. Unlocking can be performed with:

```sql
ALTER USER 'old_batch_app'@'10.20.5.30' ACCOUNT UNLOCK;
```

Drop the account only after owners confirm it is no longer used, applications have migrated to new identities if needed, privileges and dependencies have been audited, and the observation window showed no impact:

```sql
DROP USER 'old_batch_app'@'10.20.5.30';
```

`DROP USER` removes the account and its attached privileges; it does not delete data in schemas or tables the account previously accessed. Nor does it automatically terminate already-open sessions. For automation scripts that might encounter an already-dropped account, `DROP USER IF EXISTS` can be used while still logging the identity and reason for removal.

Never drop or modify system accounts created and used by MySQL, such as `mysql.session`, `mysql.sys`, and `mysql.infoschema`, unless official documentation for your exact version instructs a specific action. Also verify standby administrative accounts and accounts used for backup, monitoring, and replication before making changes.

## 7. Auditable Periodic Review Workflow

A practical workflow can be structured into the following steps:

1. **Build an account inventory.** Export `User`, `Host`, authentication plugin, and lock state; exclude sensitive credential fields from reports.
2. **Flag anomalous accounts.** Check for empty users, `%` hosts, duplicate-purpose accounts, and accounts lacking a clear owner.
3. **Map privileges.** Cross-check global, schema, table, column, role, grant-option, and default-role assignments.
4. **Verify usage.** Combine audit logs, connection counters, application configs, schedules, and owner confirmation.
5. **Propose actions.** Document privileges to revoke, accounts to lock or drop, rationale, expected impact, and approver.
6. **Execute in batches.** Prioritize narrowing privileges; lock uncertain accounts for monitoring when appropriate; drop only after confirming dependencies.
7. **Verify post-change state.** Re-run inventory queries, `SHOW GRANTS`, role checks, and critical application smoke tests.
8. **Retain evidence.** Record timestamp, operator, `user`/`host` identity, changes made, test outcomes, and sign-off.

A review report should contain at minimum these columns: account, host, owner, purpose, allowed connection sources, direct privileges, assigned roles, usage signals, findings, recommended action, approver, and remediation status. Authentication secrets and deployment credentials do not belong in this report.

## 8. Hands-on Exercise

Suppose a test server contains accounts for a sales application, reporting, a batch job, and a legacy user account. Practice the following steps:

1. List accounts from `mysql.user`; find rows where `User = ''` and inspect accounts where `Host = '%'`.
2. Pick a test application account and use `USER_PRIVILEGES`, `SCHEMA_PRIVILEGES`, `TABLE_PRIVILEGES`, and `COLUMN_PRIVILEGES` to list its direct privileges.
3. Use `SHOW GRANTS`, `mysql.role_edges`, and `mysql.default_roles` to inspect assigned roles, role admin options, and default roles.
4. Check `performance_schema.accounts` if populated; explain why connection counters alone are insufficient to conclude an account is abandoned.
5. Choose an unneeded write privilege, revoke it with `REVOKE`, then re-run `SHOW GRANTS` and test application functionality.
6. For the legacy account, verify logs and owners, lock it in the test environment, test new connections, and drop it only after confirming no dependencies remain.

At the end of the exercise, be able to explain the difference between direct privileges and role-based privileges, between locking and dropping an account, and what evidence is required before concluding an account is unused. This is the foundation for keeping MySQL identities and access privileges strictly at what is needed throughout operations.
