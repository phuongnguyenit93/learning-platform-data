# Principle of Least Privilege and Separation of Administrative/Application Accounts

## Objectives

In MySQL, an account being able to connect successfully does not mean that account should be allowed to do everything on the server. Good privilege design starts by identifying which operations each component needs to perform, on which data, and from which connection source. Then, grant only the necessary privileges to each identity and verify them using that very account.

This lesson belongs to the **DATABASE_MYSQL** module, which focuses on table design, data types, keys, SQL queries, indexes, transactions, concurrency control, and relational database operational tasks. Within the scope of security, the principle of least privilege helps protect data and reduce the blast radius when a password, application server, or process is compromised. Separating administrative accounts from application accounts also helps limit configuration errors and clarify the responsibilities of each component.

After this lesson, you will be able to:

- Explain the principle of least privilege and the privilege scope levels in MySQL.
- Design separate accounts for continuously running applications, deployment tasks, and administrators.
- Grant, inspect, and revoke privileges using `CREATE USER`, `GRANT`, `SHOW GRANTS`, and `REVOKE`.
- Use roles to manage consistent privilege sets on MySQL 8.0 and later.
- Verify the actual account that MySQL used to authenticate and apply privileges.

## 1. Least Privilege in MySQL

**Least privilege** means each account receives only the privileges needed for a defined task, within the smallest possible data scope. If a service only reads a product catalog, its account typically only needs `SELECT` on the relevant tables or views. It does not need `DROP`, `ALTER`, `CREATE USER`, or server-wide administrative privileges.

MySQL manages accounts as a pair of username and source host, in the form `'user_name'@'host_name'`. Therefore, `'orders_app'@'10.20.30.15'` and `'orders_app'@'%'` are two distinct accounts. The `host_name` portion restricts where connections are allowed from; use an IP address, hostname, or network range that matches your actual infrastructure. The `%` wildcard matches multiple hosts, so use it only when there is a clear reason and additional network control layers.

Two steps should be distinguished:

- **Authentication:** MySQL determines whether the connection can log in with a matching account.
- **Authorization:** after logging in, MySQL checks whether the account has the privileges to execute the statement on the requested object.

Privileges can be granted at multiple scopes:

| Scope | Example | When to Use |
|---|---|---|
| Global (server-wide) | `ON *.*` | Only for administrative tasks that genuinely require privileges across multiple schemas |
| Schema | `ON orders.*` | Services that only operate within the `orders` schema |
| Table or view | `ON orders.customer` | Only need access to a specific object |
| Column | `GRANT SELECT (id, display_name) ON orders.customer` | Only need certain columns; useful when restricting sensitive data |
| Stored procedure or function | `GRANT EXECUTE ON PROCEDURE orders.rebuild_summary` | Only need to invoke a controlled routine |

Do not grant global privileges just because the statement is easier to write. Privileges on `orders.*` can also be too broad if the application only needs a few tables. Choose the narrowest scope under which the application still operates reliably.

## 2. Why Separate Administrative and Application Accounts?

Application accounts are used automatically, frequently, and may be opened from multiple instances in a deployment cluster. Administrative accounts are used by operational personnel, typically to create accounts, alter structures, troubleshoot incidents, or adjust configuration. These two types of work have very different risk profiles and privilege requirements.

If an application runs as `root` or an account with global privileges, a SQL injection bug, leaked secret, or bug in application code can lead to schema changes, data deletion, or creation of additional accounts. If the application uses a dedicated account with limited DML privileges, the blast radius is usually smaller and easier to investigate.

A common separation model:

| Identity | User or Process | Typical Privileges |
|---|---|---|
| `dba_operator` | DBA or on-call operator | Necessary administrative privileges for the task; used during controlled operations |
| `orders_app` | Application runtime process | `SELECT`, `INSERT`, `UPDATE`, `DELETE` on required schemas or tables |
| `orders_migrator` | Deployment pipeline or migration tool | Only the DDL privileges needed for the deployment window; not used for day-to-day traffic |
| `orders_report` | Reporting service | Typically only `SELECT` on reporting views or tables |
| Backup/monitoring accounts | Backup or monitoring tools | Least privilege based on the tool, MySQL version, and chosen operational method |

Do not share a single account across administrators, applications, and deployment pipelines. Separate accounts make it easier to trace activity, rotate secrets independently, and lock only the affected component during an incident.

## 3. Creating an Application Account with Required DML Privileges

Suppose the `orders` schema contains order data and the application runs from host `10.20.30.15`. The application runtime account only needs to read and update data in this schema.

```sql
CREATE USER 'orders_app'@'10.20.30.15'
  IDENTIFIED BY '<secret-from-secret-manager>'
  REQUIRE SSL;

GRANT SELECT, INSERT, UPDATE, DELETE
  ON orders.*
  TO 'orders_app'@'10.20.30.15';
```

Replace the placeholder string with a secret generated and stored in your environment's secret management system. Do not put real passwords in source code, Git, logs, or documentation. `REQUIRE SSL` requires the account's connections to use TLS; both server and client must have TLS configured accordingly before enabling this requirement in production.

The example above permits normal data operations without granting privileges to create tables, alter structure, drop schemas, create accounts, or grant privileges to others. If the application only reads data, omit `INSERT`, `UPDATE`, and `DELETE`. If the application only accesses specific tables, replace `orders.*` with the individual objects needed, such as `orders.order_header` or `orders.order_item`.

A reporting service can use a separate account:

```sql
CREATE USER 'orders_report'@'10.20.30.25'
  IDENTIFIED BY '<report-secret-from-secret-manager>'
  REQUIRE SSL;

GRANT SELECT
  ON orders.v_order_summary
  TO 'orders_report'@'10.20.30.25';
```

In this example, the reporting account only reads a selected view. The view can expose only the columns and records required for reporting, helping reduce direct privilege grants on tables containing sensitive data.

## 4. Separating Schema Deployment Privileges from Application Runtime Privileges

Migration tools may need `CREATE`, `ALTER`, or `INDEX` to create and update table structures. These privileges are usually unnecessary once deployment finishes. Create a separate account for the pipeline and grant only the DDL privileges that migrations actually use.

```sql
CREATE USER 'orders_migrator'@'10.20.30.40'
  IDENTIFIED BY '<deployment-secret-from-secret-manager>'
  REQUIRE SSL;

GRANT CREATE, ALTER, INDEX
  ON orders.*
  TO 'orders_migrator'@'10.20.30.40';
```

This is a minimal example; the exact set of privileges depends on the migration. Only add `DROP`, `CREATE VIEW`, `TRIGGER`, `CREATE ROUTINE`, or other privileges once you have confirmed the migration requires them. Do not configure the day-to-day application to use the migration account. After a deployment window, temporary DDL privileges can be revoked or the account can be locked according to operational procedures.

DBA accounts must also be managed separately. Avoid using `GRANT ALL PRIVILEGES ON *.*` or `WITH GRANT OPTION` as a default granting pattern. Grant administrative privileges according to job role, restrict who can use them, require strong authentication, and protect administrative connection paths. Privileges that allow creating accounts or granting privileges to other accounts require special control.

## 5. Using Roles to Manage Privileges Consistently

On MySQL 8.0 and later, a **role** is a named collection of privileges. You can grant the same role to multiple accounts instead of repeating the privilege list for each user. When privileges in the role change, accounts assigned that role receive the changes according to MySQL's role activation mechanism.

Example of creating a role for an application with read and write privileges:

```sql
CREATE ROLE 'orders_runtime_rw'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE
  ON orders.*
  TO 'orders_runtime_rw'@'%';

GRANT 'orders_runtime_rw'@'%'
  TO 'orders_app'@'10.20.30.15';

SET DEFAULT ROLE 'orders_runtime_rw'@'%'
  TO 'orders_app'@'10.20.30.15';
```

Here, the role represents the privilege set; the actual login account remains `'orders_app'@'10.20.30.15'`. The `SET DEFAULT ROLE` statement activates the role by default when the account logs in. If a role has been assigned but is not a default role, check the role activation configuration or activate the role within the session according to your system design.

Roles are helpful when multiple instances or multiple services need the same set of privileges. However, roles do not replace privilege scope design: a role containing overly broad privileges still introduces risk for every account assigned that role. On MySQL versions that do not support roles, privileges can be granted directly to each account and changes managed via version-controlled procedures.

## 6. Verifying the Actual Account and Privileges

After creating an account, connect using that account's credentials and verify the identity MySQL recognizes:

```sql
SELECT USER() AS connection_identity,
       CURRENT_USER() AS privilege_identity;
```

`USER()` shows the connecting username and source host as seen by the server. `CURRENT_USER()` shows the MySQL account matched for authentication and privilege enforcement. These two values can differ due to host-based account matching rules. When diagnosing privilege errors, `CURRENT_USER()` is especially useful to avoid inspecting the wrong account.

A DBA can inspect granted privileges with:

```sql
SHOW GRANTS FOR 'orders_app'@'10.20.30.15';
SHOW GRANTS FOR 'orders_report'@'10.20.30.25';
```

If roles are used, check both the assigned roles and the privileges inside each role. You can view an account's privileges with a specific role using `SHOW GRANTS FOR 'orders_app'@'10.20.30.15' USING 'orders_runtime_rw'@'%';`. Verification should cover direct privileges, default roles, schema/table scopes, and privileges arising from views or routines.

Perform both positive and negative checks:

1. Log in as `orders_app` and run the operations the application requires, such as reading and updating a test record.
2. Attempt an out-of-scope operation, such as `CREATE TABLE` in the `orders` schema; this must be denied if the account lacks DDL privileges.
3. Log in as `orders_report`, verify it can read the reporting view and cannot write data.
4. Confirm the application and pipeline are using the intended accounts and not accidentally using a DBA account via environment configuration.

Do not rely solely on a `GRANT` statement succeeding. Effective privileges also depend on the actual matched account, activated roles, target objects, and mechanisms such as views or stored routines.

## 7. Revoking Privileges and Handling Unneeded Accounts

When a task ends or a privilege is no longer needed, revoke the corresponding privileges:

```sql
REVOKE CREATE, ALTER, INDEX
  ON orders.*
  FROM 'orders_migrator'@'10.20.30.40';
```

If you need to prevent an account from opening new connections during an investigation, MySQL 8.0 supports account locking:

```sql
ALTER USER 'orders_app'@'10.20.30.15' ACCOUNT LOCK;
```

Locking an account blocks new connections; active sessions must be inspected and terminated separately if incident response procedures require it. When an account is no longer used, it can be removed with `DROP USER` after confirming no operational dependencies remain. If an account is assigned a role, you can revoke the role with `REVOKE role_name FROM user_name`.

Account management statements such as `CREATE USER`, `GRANT`, `REVOKE`, `ALTER USER`, and `DROP USER` automatically update MySQL's privilege state. You do not need to run `FLUSH PRIVILEGES` after these statements. Avoid editing system tables such as `mysql.user` directly; use the administrative statements provided by MySQL to keep privilege state consistent.

## 8. Common Design Mistakes

- **Using `root` in application configuration:** a bug in the application can impact the entire server. Create a dedicated runtime account.
- **Granting `ALL PRIVILEGES` or privileges on `*.*` to a service:** the scope is far wider than the task requires. Choose specific privileges and schemas.
- **Sharing one account for both application and migrations:** the application retains DDL privileges throughout runtime. Separate accounts by lifecycle.
- **Allowing connections from any host without justification:** the account can be used from unexpected sources. Restrict hosts and combine with firewall/network policies.
- **Forgetting to activate default roles:** roles are assigned, but privileges do not appear in the session as expected. Check `SET DEFAULT ROLE` and the current session.
- **Storing passwords in repositories or logs:** secrets are easily copied and persist long after exposure. Use a secret manager, restrict read access, and maintain a rotation schedule.
- **Checking only direct privileges:** views, stored procedures, functions, and `DEFINER` can create indirect access paths. Check both execution privileges and the security context of those objects.
- **Failing to revoke temporary privileges:** deployment or support accounts may retain elevated privileges longer than needed. Build revocation into post-deployment procedures.

## 9. Adoption Workflow in a Project

When onboarding a new service to MySQL, you can apply the following workflow:

1. List the statements and data objects the service needs across each business flow.
2. Categorize accounts by purpose: runtime, reporting, migration, backup, monitoring, and administration.
3. Choose the source host, TLS requirement, and schema/table scope for each account.
4. Create accounts and grant privileges directly or via roles; store secrets in a secret management system.
5. Check `CURRENT_USER()` and `SHOW GRANTS`, then run both allowed operations and operations that must be denied.
6. Monitor account usage, rotate secrets, review privileges periodically, and revoke unneeded accounts or privileges.

For backup and monitoring accounts, do not mechanically copy DBA privileges. Required privileges depend on the tool, MySQL version, storage engine, and data consistency options. Clearly identify the features the tool uses, test in a production-like environment, and grant only verified privileges.

## 10. Hands-on Exercise

In a test MySQL environment, create the `orders` schema and three separate accounts: `orders_app`, `orders_report`, and `orders_migrator`. Use test host addresses appropriate for your client machine.

- Grant `orders_app` read and write privileges on the required business tables.
- Grant `orders_report` `SELECT` on a summary view.
- Grant `orders_migrator` the DDL privileges required to create or alter tables.
- Use `SELECT USER(), CURRENT_USER()` and `SHOW GRANTS` to verify identities and privileges.
- Test valid and invalid operations with each account; record expected and actual results.
- Revoke DDL privileges from `orders_migrator`, lock a test account, and verify that the locked account can no longer open new connections.

**Completion criteria:** each account can perform its intended tasks, over-privileged operations are denied, the application does not require an administrative account, and you can explain why each privilege was granted at its scope.

## Conclusion

Least privilege narrows the impact when bugs or security incidents occur. Separating runtime, migration, reporting, and administrative accounts ensures each process has only the capabilities required for its task. In MySQL, manage accounts by user/host pair, grant privileges at a narrow scope, use roles to standardize privilege sets when needed, and always verify effective privileges using the active account.
