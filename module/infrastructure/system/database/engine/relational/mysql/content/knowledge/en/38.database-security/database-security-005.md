# GRANT, REVOKE, and Privileges by Server, Database, Table, Column, and Routine

In MySQL, logging in successfully only verifies the identity of the connection. Users also need the right privileges to read or modify data, manage structures, and invoke stored routines. `GRANT` assigns privileges and `REVOKE` removes them; the privilege scope determines which resources an account can affect.

This lesson belongs to the **Security** chapter of the `DATABASE_MYSQL` module. The material progresses from server-wide privileges down to database, table, column, and routine levels, then combines them with roles to build an auditable and maintainable authorization design. Examples use MySQL 8.0+ syntax; some dynamic privileges and features may vary depending on the server version or installed plugins.

After this lesson, you will be able to:

- Distinguish a MySQL account from the privileges granted to it.
- Choose the smallest privilege scope that satisfies a task.
- Grant and revoke privileges using `GRANT` and `REVOKE`.
- Use roles to group privileges by job function.
- Inspect effective privileges and diagnose overly broad privilege grants.
- Evaluate the security risks of granting privileges to invoke stored procedures or functions.

## 1. Accounts and Privileges Are Two Separate Layers

MySQL identifies an account by a **user and host** pair, typically written as:

```sql
'app_reader'@'10.20.%'
```

The `app_reader` part is the account name; the `10.20.%` part restricts connection sources according to MySQL's host-matching rules. Two accounts with the same username but different hosts are two distinct accounts that can have different passwords and privileges. Therefore, when granting or revoking privileges, you must specify the exact user/host pair.

Create the account first, then grant privileges:

```sql
CREATE USER 'app_reader'@'10.20.%'
  IDENTIFIED BY 'replace-with-a-unique-secret';
```

The password in the example is just a placeholder; in deployment, use a strong, unique secret and follow your system's secret management process. Restrict the host to the address or network range genuinely required. Avoid using `%` if the application does not need to connect from every source.

Do not use the `root` account for applications. Create separate accounts for applications, reporting, backups, migrations, and operations. Each account should have only the privileges required for its specific task.

Two functions are routinely helpful when checking connection identity:

```sql
SELECT USER(), CURRENT_USER();
```

- `USER()` reports the username sent by the client together with the connection origin recognized by the server.
- `CURRENT_USER()` reports the actual MySQL account used to check privileges. Inside a stored routine executing with `DEFINER` rights, this value may be the `DEFINER` account.

If privileges were granted to `'app_reader'@'localhost'` while the connection matches `'app_reader'@'10.20.%'`, results may differ from expectations. Check `CURRENT_USER()` before concluding that `GRANT` had no effect.

## 2. Understanding the Five Privilege Scopes

MySQL allows granting privileges at multiple levels. The `ON` clause in a `GRANT` statement defines that scope.

| Scope | Object Syntax | Meaning |
|---|---|---|
| Global (server-wide) | `*.*` | Privileges apply across the entire MySQL instance; largest impact scope. |
| Database | `sales.*` | Privileges apply to objects in the `sales` database, including objects created later. |
| Table | `sales.orders` | Privileges apply to a specific table or view. |
| Column | `sales.orders (order_id, status)` | Applies only to the listed columns; suitable for restricting readable or modifiable data. |
| Routine | `PROCEDURE sales.close_order` or `FUNCTION sales.calculate_tax` | Privileges apply to a specific stored procedure or stored function. |

The wider the scope, the greater the impact of a misconfigured grant. For example, `SELECT ON *.*` allows reading data across the entire server; `SELECT ON sales.*` allows reading every table in the `sales` database; `SELECT ON sales.orders` allows reading only the `orders` table.

Privileges at broader scopes contribute to effective privileges at narrower scopes. If an account already holds `SELECT ON *.*`, additionally granting `SELECT ON sales.orders` does not restrict the account to that table: the server-wide privilege still permits reading other tables. When designing privileges, examine all privilege sources for an account, including direct grants and active roles.

### 2.1. Server-Level Privileges

Global privileges are typically reserved for administrators or dedicated operational accounts. Examples include `CREATE USER`, `PROCESS`, `RELOAD`, `SHUTDOWN`, `FILE`, and dynamic privileges such as `BACKUP_ADMIN` or `CONNECTION_ADMIN`.

Example of granting process inspection privileges:

```sql
GRANT PROCESS ON *.* TO 'ops_observer'@'10.20.%';
```

`PROCESS` can expose information about the activity and queries of other connections. Consider what data operators need to see before granting it. Privileges such as `FILE`, `SHUTDOWN`, `CREATE USER`, or system administration privileges can have major impact and should not be present on normal application accounts.

### 2.2. Database-Level Privileges

Database-level privileges fit when an application or user group works with many tables within the same database.

```sql
GRANT SELECT, INSERT, UPDATE
ON sales.*
TO 'sales_app'@'10.20.%';
```

The account can read, insert, and update data in the `sales` database. The statement does not grant `DELETE`, `DROP`, `ALTER`, or other administrative privileges. Granting only the operations actually required limits damage if application credentials leak or a query has a bug.

Database-level privileges also apply to objects created in that database in the future. Thus, if an account only needs to work with a few stable tables, a database-level grant may be broader than necessary.

### 2.3. Table-Level Privileges

When access to only one table is needed, grant privileges directly on that table:

```sql
GRANT SELECT
ON sales.orders
TO 'order_reporter'@'10.20.%';
```

The account can read `sales.orders` without automatically gaining read access to every other table in `sales`. Separate write operations can be added if the job requires them:

```sql
GRANT INSERT, UPDATE
ON sales.orders
TO 'order_processor'@'10.20.%';
```

Do not grant `DELETE`, `ALTER`, or `DROP` merely because the application already has `INSERT` and `UPDATE`. Those operations carry different purposes and risks.

### 2.4. Column-Level Privileges

Column-level privileges are used when a person or service only needs a subset of columns. MySQL supports column-level privileges for `SELECT`, `INSERT`, `UPDATE`, and `REFERENCES`.

For example, support staff only need the order ID and status, without reading addresses or payment details:

```sql
GRANT SELECT (order_id, status)
ON sales.orders
TO 'support_agent'@'10.20.%';
```

If they are only allowed to change order status:

```sql
GRANT UPDATE (status)
ON sales.orders
TO 'support_agent'@'10.20.%';
```

Column-level privileges do not override broader privileges already held. If the account also holds `SELECT ON sales.orders` or `SELECT ON sales.*`, the two-column grant above no longer restricts what data can be read. When investigating column privileges, inspect global, database, table, and role grants together.

### 2.5. Privileges on Stored Procedures and Functions

Stored routines have their own privilege scope. Two common privileges are:

- `EXECUTE`: allows invoking the routine.
- `ALTER ROUTINE`: allows altering or dropping the routine according to MySQL privilege rules.

Example of granting execution privilege on a procedure:

```sql
GRANT EXECUTE
ON PROCEDURE sales.close_order
TO 'batch_runner'@'10.20.%';
```

For a function:

```sql
GRANT EXECUTE
ON FUNCTION sales.calculate_tax
TO 'checkout_app'@'10.20.%';
```

`CREATE ROUTINE` and `ALTER ROUTINE` can also be granted at the database scope when managing routine lifecycles. Separate routine deployment privileges from routine execution privileges: application accounts typically need only `EXECUTE`, whereas migration accounts or maintainers need privileges to create and alter routines.

## 3. Granting Privileges with GRANT

General syntax:

```sql
GRANT privilege_list
ON object
TO 'user'@'host'
[WITH GRANT OPTION];
```

`privilege_list` is one or more privileges permitted at the chosen scope; `object` specifies the scope; `TO` specifies the recipient account.

Complete example for a reporting account:

```sql
CREATE USER 'report_user'@'10.20.%'
  IDENTIFIED BY 'replace-with-a-unique-secret';

GRANT SELECT
ON sales.orders
TO 'report_user'@'10.20.%';
```

The account can only read the orders table. If requirements change, grant the exact operations on the exact objects instead of expanding to `ALL PRIVILEGES`.

### 3.1. Choosing Privileges by Task

| Task | Privileges Typically Considered | Avoid Granting by Default |
|---|---|---|
| Reading reports | `SELECT` on reporting tables or databases | `INSERT`, `UPDATE`, `DELETE`, `DROP` |
| Application data writes | `SELECT`, `INSERT`, `UPDATE` on required tables | `ALTER`, `DROP`, `CREATE USER`, `FILE` |
| Running an order-closing job | `EXECUTE` on the designated procedure | Routine modification or server-wide privileges |
| Schema deployment | DDL privileges needed for migrations on the target database | Server-wide administrative privileges unless required |
| Operational monitoring | Specific monitoring privileges such as `PROCESS` when justified | Data modification or server shutdown privileges |

This is a starting point for analysis, not an automatic grant checklist. Inspect the actual SQL statements each component executes; some statements require more privileges than the primary operation name suggests.

### 3.2. GRANT OPTION

`WITH GRANT OPTION` allows the recipient to grant onward the privileges they hold at that corresponding scope. Example:

```sql
GRANT SELECT
ON sales.*
TO 'team_lead'@'10.20.%'
WITH GRANT OPTION;
```

`team_lead` can grant the delegated `SELECT` privilege within that scope to others. This is a delegation privilege, not merely a data-read privilege. If granted to many accounts, tracking who granted privileges to whom becomes much harder.

`ALL PRIVILEGES` does not automatically include `GRANT OPTION`. If an account needs delegation rights, decide deliberately and specify it with `WITH GRANT OPTION`. Dynamic privileges are also managed separately; do not assume `ALL PRIVILEGES` includes every privilege provided by the server or plugins.

## 4. Revoking Privileges with REVOKE

Basic syntax:

```sql
REVOKE privilege_list
ON object
FROM 'user'@'host';
```

Example of revoking update privileges while keeping read privileges:

```sql
REVOKE UPDATE
ON sales.orders
FROM 'order_processor'@'10.20.%';
```

Revoking column privileges:

```sql
REVOKE UPDATE (status)
ON sales.orders
FROM 'support_agent'@'10.20.%';
```

Revoking routine execution privileges:

```sql
REVOKE EXECUTE
ON PROCEDURE sales.close_order
FROM 'batch_runner'@'10.20.%';
```

Revoking delegation rights while keeping usage privileges:

```sql
REVOKE GRANT OPTION FOR SELECT
ON sales.*
FROM 'team_lead'@'10.20.%';
```

In the last example, `team_lead` loses the ability to delegate that `SELECT` privilege; the account's own `SELECT` privilege remains unless separately revoked.

To revoke all direct privileges and grant options from an account:

```sql
REVOKE ALL PRIVILEGES, GRANT OPTION
FROM 'report_user'@'10.20.%';
```

This statement does not remove the account. If the account no longer needs to exist, an administrator may consider `DROP USER` after verifying which services still use it.

### 4.1. REVOKE Does Not Always Remove Effective Privileges

MySQL aggregates privileges from multiple sources. If an account holds `SELECT` server-wide, revoking `SELECT` at the database level does not remove the privilege granted at the global level. Likewise, revoking a column privilege does not restrict an account that holds a broader table or database privilege.

Example:

```sql
GRANT SELECT ON *.* TO 'auditor'@'10.20.%';
REVOKE SELECT ON sales.* FROM 'auditor'@'10.20.%';
```

When partial revokes are not enabled, the global `SELECT` privilege still allows the account to read the `sales` database. Therefore, when a `REVOKE` appears to have no effect, inspect all privilege levels and active roles before making further changes.

MySQL does not provide a general-purpose `DENY` mechanism equivalent to some other database management systems. The standard design pattern is to avoid granting broad privileges up front and instead grant only what is needed.

## 5. Using Roles for Role-Based Access Control

When multiple accounts perform the same job, granting individual privileges separately to each account easily leads to drift. A role groups privileges under a named role; you then grant that role to the accounts that need it.

Example of creating a report-reading role:

```sql
CREATE ROLE 'sales_reader';

GRANT SELECT
ON sales.orders
TO 'sales_reader';

GRANT 'sales_reader'
TO 'analyst'@'10.20.%';

SET DEFAULT ROLE 'sales_reader'
TO 'analyst'@'10.20.%';
```

The `sales_reader` role holds read access on `sales.orders`. The `analyst` account is granted the role, and the role is set as default so it activates automatically when the account logs in.

Within the current session, you can inspect or change active roles:

```sql
SELECT CURRENT_ROLE();
SET ROLE DEFAULT;
SET ROLE NONE;
SET ROLE ALL;
```

- `CURRENT_ROLE()` shows the roles currently active in the session.
- `SET ROLE DEFAULT` activates the default roles.
- `SET ROLE NONE` deactivates roles in the current session.
- `SET ROLE ALL` activates all roles granted to the account that can be activated.

To revoke a role:

```sql
REVOKE 'sales_reader'
FROM 'analyst'@'10.20.%';
```

`WITH ADMIN OPTION` on a role grant allows the recipient to administer granting that role to others. Distinguish clearly:

- `WITH GRANT OPTION` applies to privileges on data objects.
- `WITH ADMIN OPTION` applies to role administration.

Name roles after functions, such as `sales_reader`, `sales_writer`, `routine_executor`, or `schema_migrator`. Avoid naming roles after individuals, as that becomes hard to maintain when personnel or responsibilities change.

## 6. Dynamic Privileges and Specialized Administrative Privileges

Beyond familiar static privileges such as `SELECT`, `INSERT`, and `UPDATE`, MySQL has **dynamic privileges**. They are registered by the server version or plugins and are typically granted globally. Examples include `BACKUP_ADMIN`, `CONNECTION_ADMIN`, `ROLE_ADMIN`, `SYSTEM_USER`, and `BINLOG_ADMIN`.

Example of granting a specialized backup privilege:

```sql
GRANT BACKUP_ADMIN
ON *.*
TO 'backup_operator'@'10.20.%';
```

Dynamic privilege names and requirements depend on the MySQL version and installed components. Before granting, check the list of privileges supported by your instance and the documentation for your exact version or plugin. Do not treat a dynamic privilege list from a different server as an absolute reference.

Sensitive privileges such as `SYSTEM_USER`, `ROLE_ADMIN`, `CONNECTION_ADMIN`, or `BINLOG_ADMIN` can affect accounts, connections, roles, or binary logs. Grant them strictly by task, separate operational accounts from application accounts, and document the reason for the grant.

## 7. Partial Revokes: Controlled Exceptions

Since MySQL 8.0.16, `partial_revokes` allows restricting specific globally granted privileges for a particular database. This is an important exception to the additive privilege model.

For example, suppose an account holds server-wide `SELECT` privileges but must be restricted from the `payroll` database. When `partial_revokes` is enabled, an administrator can run:

```sql
REVOKE SELECT
ON payroll.*
FROM 'auditor'@'10.20.%';
```

This option must be configured and verified for your MySQL version; its default value is typically off. Administrators can check its status with:

```sql
SHOW VARIABLES LIKE 'partial_revokes';
```

Partial revokes have specific scopes and rules, not a general `DENY` across every privilege level. Overusing them also makes the privilege model harder to read. For new systems, designing accounts and roles with only the required privileges is usually easier to audit than granting broad global access and layering many exceptions.

## 8. Security Risks of Stored Routines

The `EXECUTE` privilege only indicates that an account may invoke the routine. Which privileges the routine uses when running depends on the routine's SQL security mode.

### 8.1. SQL SECURITY DEFINER

`SQL SECURITY DEFINER` executes the routine with the privileges of the account declared as `DEFINER`. This is the default mode if no other mode is specified. The caller only needs `EXECUTE` on the routine; the routine can operate on data using the `DEFINER`'s privileges.

Illustrative example:

```sql
DELIMITER //

CREATE DEFINER = 'routine_owner'@'localhost'
PROCEDURE sales.close_order(IN p_order_id BIGINT)
SQL SECURITY DEFINER
BEGIN
  UPDATE sales.orders
  SET status = 'closed'
  WHERE order_id = p_order_id;
END//

DELIMITER ;
```

The `routine_owner` account needs appropriate privileges to update the table. The batch account only needs:

```sql
GRANT EXECUTE
ON PROCEDURE sales.close_order
TO 'batch_runner'@'10.20.%';
```

This pattern can be useful when exposing a controlled business operation without granting direct table-update privileges to the application. However, the routine becomes a security boundary: if the routine accepts unsafe input, allows arbitrary data updates, or executes uncontrolled dynamic SQL, callers can abuse the `DEFINER`'s higher privileges.

Use a dedicated, narrowly privileged `DEFINER` account—never `root`; carefully validate parameters and routine logic; and review routines whenever the `DEFINER`'s privileges change. Also manage the lifecycle of `DEFINER` accounts so routines do not depend on a personal account that could unexpectedly be dropped or modified.

### 8.2. SQL SECURITY INVOKER

`SQL SECURITY INVOKER` executes the routine using the caller's privileges. Example:

```sql
CREATE PROCEDURE sales.read_order(IN p_order_id BIGINT)
SQL SECURITY INVOKER
SELECT order_id, status
FROM sales.orders
WHERE order_id = p_order_id;
```

In this mode, the caller must hold the necessary privileges on objects accessed by the routine, in addition to the `EXECUTE` privilege required by MySQL. This is the right choice when a routine does not need to elevate the caller's privileges.

When reviewing a routine, check at least: who the `DEFINER` is, which `SQL SECURITY` mode the routine uses, which accounts hold `EXECUTE` on it, and what data the statements inside can affect.

## 9. Verifying Privileges and Troubleshooting Errors

After granting or revoking privileges, read back the state from the server. Useful verification statements include:

```sql
-- View privileges of a specific account
SHOW GRANTS FOR 'report_user'@'10.20.%';

-- View privileges of the currently logged-in account
SHOW GRANTS FOR CURRENT_USER;

-- View the identity used for privilege checking
SELECT USER(), CURRENT_USER(), CURRENT_ROLE();

-- Check partial_revokes status
SHOW VARIABLES LIKE 'partial_revokes';
```

`SHOW GRANTS` is a good starting point for reviewing direct grants and assigned roles. When you need to confirm actual behavior, connect using that exact application or test account and run representative read/write queries. Testing from an administrator session does not prove the application account has the same privileges.

`GRANT` and `REVOKE` update privileges through MySQL's management layer and take effect without running `FLUSH PRIVILEGES`. Do not edit grant tables in the `mysql` schema directly; direct edits can leave inconsistent, hard-to-audit state.

### 9.1. Common Errors

| Symptom | Common Cause | How to Check |
|---|---|---|
| `Access denied` on connect | Wrong password, host mismatch, or account does not exist | Verify the exact `'user'@'host'` pair, authentication policy, and `CURRENT_USER()` once connected. |
| `SELECT command denied` | Missing `SELECT` on the required database, table, or column | Run `SHOW GRANTS`; identify the exact database, table, and columns used by the query. |
| `UPDATE command denied` | Missing `UPDATE` at the appropriate scope or missing privileges required by other parts of the statement | Check the updated columns, filter conditions, and privileges needed by the full SQL statement. |
| Role granted, yet application is still denied | Role is not set as default or is not active in the session | Check `CURRENT_ROLE()` and `SET DEFAULT ROLE` configuration. |
| `REVOKE` executed, yet user can still read | Privilege still comes from a global grant, table grant, another role, or another host account | Inspect all `SHOW GRANTS`, active roles, and `CURRENT_USER()`. |
| Procedure call denied | Missing `EXECUTE`, calling the wrong routine, or an issue with the routine/`DEFINER` | Check routine privileges, routine name, `DEFINER`, and `SQL SECURITY`. |
| User can grant privileges to others | `GRANT OPTION` or a role with `ADMIN OPTION` was granted | Run `SHOW GRANTS` and revoke the delegation privilege if unnecessary. |

## 10. Practical Authorization Workflow

A practical workflow should follow this order:

1. **List tasks.** Identify what the account is for: reading reports, processing transactions, executing routines, migrations, or operations.
2. **Identify objects.** Specify the exact databases, tables, columns, or routines the task must access.
3. **Select minimum privileges.** Choose only `SELECT`, `INSERT`, `UPDATE`, `EXECUTE`, or other privileges the statements genuinely require.
4. **Choose the narrowest scope.** Prefer routine, column, or table level where appropriate; use database or global level only when the task demands it.
5. **Use roles for task groups.** Grant privileges to roles and assign roles to accounts; configure default roles if the application expects automatic activation.
6. **Verify effective privileges.** Inspect `SHOW GRANTS`, `CURRENT_USER()`, and `CURRENT_ROLE()`; check for broader grants that could defeat narrower restrictions.
7. **Test with the actual account.** Verify both allowed operations and operations that must be denied in an appropriate environment.
8. **Review periodically.** Revoke privileges no longer needed, unused accounts, and delegation rights lacking clear justification.

### 10.1. Example Role Design for a Sales Application

Suppose a system has three responsibilities: analysts reading orders, an order-processing service updating orders, and a batch job closing orders via a procedure. You can design it as follows:

```sql
CREATE ROLE 'sales_reader';
CREATE ROLE 'sales_order_writer';
CREATE ROLE 'sales_close_executor';

GRANT SELECT
ON sales.orders
TO 'sales_reader';

GRANT SELECT, INSERT, UPDATE
ON sales.orders
TO 'sales_order_writer';

GRANT EXECUTE
ON PROCEDURE sales.close_order
TO 'sales_close_executor';

CREATE USER 'analyst'@'10.20.%'
  IDENTIFIED BY 'replace-with-a-unique-secret';
CREATE USER 'order_api'@'10.20.%'
  IDENTIFIED BY 'replace-with-a-unique-secret';
CREATE USER 'batch_runner'@'10.20.%'
  IDENTIFIED BY 'replace-with-a-unique-secret';

GRANT 'sales_reader' TO 'analyst'@'10.20.%';
GRANT 'sales_order_writer' TO 'order_api'@'10.20.%';
GRANT 'sales_close_executor' TO 'batch_runner'@'10.20.%';

SET DEFAULT ROLE 'sales_reader' TO 'analyst'@'10.20.%';
SET DEFAULT ROLE 'sales_order_writer' TO 'order_api'@'10.20.%';
SET DEFAULT ROLE 'sales_close_executor' TO 'batch_runner'@'10.20.%';
```

This design separates data readers, data-writing services, and jobs limited to calling a procedure. If `order_api` does not need to read all columns, you can split read access by column or provide a dedicated routine; before doing so, confirm the account does not hold broader read access from another role or grant.

In production, use a separate migration account for schema changes. Running applications should not retain `ALTER`, `DROP`, or `CREATE USER` merely for deployment convenience.

## 11. Hands-on Exercises

### Exercise 1: Single-Table Read-Only Account

Create the `inventory_viewer` account for host `10.30.%` and allow it to read only the `warehouse.stock` table.

```sql
CREATE USER 'inventory_viewer'@'10.30.%'
  IDENTIFIED BY 'replace-with-a-unique-secret';

GRANT SELECT
ON warehouse.stock
TO 'inventory_viewer'@'10.30.%';

SHOW GRANTS FOR 'inventory_viewer'@'10.30.%';
```

Test with this account: reading `warehouse.stock` must succeed; reading other tables and updating `warehouse.stock` must be denied, provided the account receives no extra privileges from other sources.

### Exercise 2: Restricting Visible Columns

A support agent should only view `order_id` and `status` in `sales.orders`:

```sql
GRANT SELECT (order_id, status)
ON sales.orders
TO 'support_agent'@'10.20.%';
```

Try querying the two granted columns and another sensitive column. If the sensitive column can still be read, check whether the account holds `SELECT` at the table, database, global level, or via a role.

### Exercise 3: Allowing Only Procedure Execution

A batch job may call `sales.close_order` but may not update `sales.orders` directly:

```sql
GRANT EXECUTE
ON PROCEDURE sales.close_order
TO 'batch_runner'@'10.20.%';
```

Inspect the procedure's `SQL SECURITY` and `DEFINER`. For `SQL SECURITY DEFINER`, evaluate the `DEFINER`'s privileges and the routine's internal logic; for `SQL SECURITY INVOKER`, inspect the privileges the batch job needs on accessed objects.

### Exercise 4: Revoking Delegation Rights

A team lead still needs to read `sales.*` but must no longer be able to grant privileges to others:

```sql
REVOKE GRANT OPTION FOR SELECT
ON sales.*
FROM 'team_lead'@'10.20.%';

SHOW GRANTS FOR 'team_lead'@'10.20.%';
```

Verify that read access remains and delegation rights have been revoked. If the result is unexpected, check other grants and roles.

## 12. Pre-Production Authorization Checklist

- Account names and hosts match expected connection sources.
- Neither `root` nor administrative accounts are used by applications.
- Each account serves one clear purpose.
- Granted scope is the smallest that satisfies the task.
- `ALL PRIVILEGES`, `GRANT OPTION`, and sensitive dynamic privileges are not granted by habit.
- Required roles are assigned and properly set as defaults.
- Routine `DEFINER` privileges and `SQL SECURITY` modes have been reviewed.
- `SHOW GRANTS`, `CURRENT_USER()`, and `CURRENT_ROLE()` have been verified.
- Both allowed operations and operations that must be denied have been tested with the actual account.
- A revocation process exists when an application, person, or task ends.

Good privilege management limits the blast radius of application bugs, unexpected queries, and leaked credentials. Treat authorization as part of system design: define the task, choose the right objects, grant the exact operations, and verify using the account that will actually run in production.
