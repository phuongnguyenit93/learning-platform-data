# Static Privileges, Dynamic Privileges, and Restricting Administrative Accounts

In MySQL, access privileges determine which data an account can read, which objects it can modify, and which operational actions it can perform on the server. Privilege design should go hand in hand with table design, queries, and operational procedures: application accounts should only have privileges on the schemas the application uses, reporting accounts should only read necessary data, and administrative operations should be split into granular privileges granted to the right people or services.

This lesson focuses on MySQL's two privilege categories—**static privileges** and **dynamic privileges**—and then applies them to build clearly scoped administrative accounts. The illustrative statements target MySQL 8.0 and later. The list of dynamic privileges varies by version and installed components/plugins, so verify directly on the target server before deploying.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish static privileges from dynamic privileges and explain the grant scope of each category.
- Select privileges based on the operations required rather than granting an overly broad administrative privilege.
- Use roles to group privileges, create separate accounts per task, and restrict connection sources.
- Inspect granted privileges, revoke unneeded privileges, and lock accounts when necessary.

## 1. Accounts, Authentication, and Authorization

MySQL checks an account's identity when a client connects, then checks the account's privileges for each statement and data object. These two steps serve different purposes:

- **Authentication** answers whether the client can prove the account's identity via a password or configured authentication mechanism.
- **Authorization** decides what an authenticated account is allowed to do on the server.

A MySQL account is identified by both name and host, in the form `'user'@'host'`. For example, `'dba'@'localhost'` and `'dba'@'192.0.2.25'` are two distinct accounts, even though both share the name `dba`. When restricting administrative accounts, pay close attention to the host portion because it defines where the account is permitted to connect from.

Privileges are granted with `GRANT`, revoked with `REVOKE`, and can be grouped into roles for reuse. Do not edit privilege tables in the `mysql` schema directly; use MySQL's account management statements so the server updates metadata and checks privileges consistently.

## 2. Static Privileges

**Static privileges** are built-in system privileges in MySQL. The server predefines these privileges; plugins or components cannot register a new static privilege at runtime. This is the familiar group of privileges used to read, write, create, and modify database objects, as well as perform certain administrative operations.

Some examples:

| Static Privilege | Common Purpose | Risk Notes |
|---|---|---|
| `SELECT` | Read data | Can expose sensitive data if granted on overly broad schemas or tables |
| `INSERT`, `UPDATE`, `DELETE` | Insert, update, delete rows | Can alter or destroy business data |
| `CREATE`, `ALTER`, `DROP`, `INDEX` | Create, alter, drop tables or indexes | Can affect application structure and performance |
| `CREATE USER` | Create and manage accounts | Can expand access if the grantee creates arbitrary accounts |
| `FILE` | Read/write certain files accessible to the MySQL process | Sensitive global privilege; can expose or write files on the server |
| `PROCESS` | View process list and running queries | Can expose activity from other sessions |
| `RELOAD`, `SHUTDOWN` | Perform server operational actions | Grant only to operational roles that genuinely require them |
| `GRANT OPTION` | Allow granting onward the privileges the account can grant | Can cause privileges to spread unexpectedly |

### 2.1. Grant Scopes for Static Privileges

Static privileges can be granted at multiple scopes. The wider the scope, the more objects are affected.

| Scope | `ON` Syntax | Meaning |
|---|---|---|
| Global (server-wide) | `*.*` | Applies to all databases and objects applicable to that privilege |
| Database | `database_name.*` | Applies to objects within a single database |
| Table | `database_name.table_name` | Applies to a specific table |
| Column | `database_name.table_name (col1, col2)` | Restricts certain read or write privileges to the listed columns |
| Stored routine | `PROCEDURE database_name.routine_name` or `FUNCTION ...` | Applies to a specific routine, such as `EXECUTE` |

Not every privilege supports every scope. For instance, `FILE` is a global privilege; column-level read/write privileges apply only to privileges that support column grants. When designing privileges, pick the smallest scope under which the task can operate.

For example, a reporting account that only needs to read two columns in the orders table:

```sql
CREATE USER 'report_reader'@'10.30.5.20'
  IDENTIFIED BY '<password-from-secret-manager>'
  REQUIRE SSL;

GRANT SELECT (order_id, total_amount)
  ON sales.orders
  TO 'report_reader'@'10.30.5.20';

SHOW GRANTS FOR 'report_reader'@'10.30.5.20';
```

This account can read the granted columns in `sales.orders`; it does not automatically get read access to all tables in the `sales` database, nor can it modify data. In real environments, replace the password placeholder with a secret generated and distributed through a secret management system; never commit real passwords into source code or documentation.

If an application needs to read and write several tables in a schema, privileges can be granted at the database scope:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE
  ON sales.*
  TO 'sales_app'@'10.30.8.14';
```

This statement grants privileges for tables in `sales`. Only add `CREATE`, `ALTER`, or `DROP` if the application genuinely has to alter database structure at runtime. Usually, use a dedicated deployment account for migrations rather than granting schema-modification privileges to the account serving daily traffic.

## 3. Dynamic Privileges

**Dynamic privileges** are privileges that can be registered while the server is running, typically by MySQL or a component/plugin. This mechanism enables specialized administrative privileges without bundling many unrelated operations into one broad privilege like `SUPER`.

Dynamic privileges are granted globally using `ON *.*`; they cannot be restricted to `sales.*`, a single table, or a column. Therefore, even if a privilege name describes a narrow task, administrators must still evaluate its instance-wide impact.

Common examples in MySQL 8.0 releases:

| Dynamic Privilege | General Purpose |
|---|---|
| `CONNECTION_ADMIN` | Allows certain administrative connection operations, including handling situations where normal connection limits are reached |
| `SYSTEM_VARIABLES_ADMIN` | Manages global system variables according to defined rules |
| `SESSION_VARIABLES_ADMIN` | Manages certain session variables that ordinary accounts are not allowed to change |
| `BACKUP_ADMIN` | Performs administrative operations related to backup locks |
| `ROLE_ADMIN` | Manages granting and revoking roles |
| `BINLOG_ADMIN` | Performs certain binary log administrative operations |
| `SYSTEM_USER` | Distinguishes system accounts and controls administrative operations affecting them |

The list above is illustrative, not exhaustive. Some privileges appear only in specific versions or when the corresponding component/plugin is installed. Do not assume every MySQL server has the exact same set of dynamic privileges.

Inspect the privileges supported by the current instance:

```sql
SHOW PRIVILEGES;
```

For example, suppose the `maintenance_operator` account has been created. An operations engineer uses this account to modify system variables and needs administrative connection capability when the server reaches its regular connection limit:

```sql
GRANT SYSTEM_VARIABLES_ADMIN, CONNECTION_ADMIN
  ON *.*
  TO 'maintenance_operator'@'192.0.2.26';
```

Both privileges are granted globally. Do not grant them to an application account merely because the application occasionally needs to inspect server status. If a task only requires backups, evaluate `BACKUP_ADMIN` and the specific additional privileges required by that backup tool, rather than granting full operational privileges.

In MySQL 8.0.31, `SUPER` was deprecated. For new designs, identify the exact operation needed and choose the corresponding dynamic privilege if available. Retaining a broad privilege solely because a legacy configuration used it increases the blast radius if an account is compromised or misused.

## 4. Comparing Static and Dynamic Privileges

| Criterion | Static Privileges | Dynamic Privileges |
|---|---|---|
| Definition source | Built into the server | Can be registered by the server, components, or plugins |
| Privilege set | Fixed per MySQL release | Can vary by version and installed components/plugins |
| Grant scope | Depends on privilege: global, database, table, column, or routine | Global (`ON *.*`) |
| Examples | `SELECT`, `INSERT`, `CREATE`, `FILE`, `PROCESS` | `BACKUP_ADMIN`, `CONNECTION_ADMIN`, `SYSTEM_VARIABLES_ADMIN` |
| How to choose | Based on data or objects to manipulate | Based on the specialized administrative task to perform |

Both privilege categories can be granted together to an account or role. They do not wholly replace each other: `SELECT` on a table is a scoped data privilege, whereas `SYSTEM_VARIABLES_ADMIN` is an instance-wide operational privilege.

## 5. Restricting Administrative Accounts

Administrative accounts often have the ability to affect multiple databases or the operation of the server itself. A compromised broadly privileged account can cause service outages, alter configuration, delete data, or escalate privileges for other accounts. Restrict accounts according to the following principles.

### 5.1. Separate Accounts by Task

An operator can have an ordinary account for running read queries and a separate account for performing administrative changes. Likewise, applications, reporting, backups, and migrations should use separate accounts. That way, leaking application credentials does not hand an attacker administrative control over the instance.

Do not share a single `root` or DBA account across applications, cron jobs, and human operators. Avoid embedding administrative credentials in configuration files deployed alongside applications.

### 5.2. Use Roles to Bundle Least Privilege

Roles let you define a task-based privilege set and assign that set to multiple accounts. For example, a read-only role for sales data:

```sql
CREATE ROLE 'r_sales_reader'@'%';

GRANT SELECT, SHOW VIEW
  ON sales.*
  TO 'r_sales_reader'@'%';

CREATE USER 'reporter'@'10.30.5.20'
  IDENTIFIED BY '<password-from-secret-manager>'
  REQUIRE SSL
  WITH MAX_USER_CONNECTIONS 3;

GRANT 'r_sales_reader'@'%'
  TO 'reporter'@'10.30.5.20';

SET DEFAULT ROLE 'r_sales_reader'@'%'
  TO 'reporter'@'10.30.5.20';
```

The `r_sales_reader` role only holds read privileges and view-definition access in the `sales` database. `SET DEFAULT ROLE` sets this role as the default when the account logs in. If a role is not activated, privileges granted through the role may not be in the session's active privilege set; therefore, check active roles after connecting.

Administrative roles can be created separately by task. The example below bundles two dynamic privileges for an operations team:

```sql
CREATE USER 'dba_ops'@'192.0.2.25'
  IDENTIFIED BY '<password-from-secret-manager>'
  REQUIRE SSL
  WITH MAX_USER_CONNECTIONS 2;

CREATE ROLE 'r_mysql_ops'@'%';

GRANT CONNECTION_ADMIN, SYSTEM_VARIABLES_ADMIN
  ON *.*
  TO 'r_mysql_ops'@'%';

GRANT 'r_mysql_ops'@'%'
  TO 'dba_ops'@'192.0.2.25';

SET DEFAULT ROLE 'r_mysql_ops'@'%'
  TO 'dba_ops'@'192.0.2.25';
```

This is an example for an operations team with those exact two requirements, not a full DBA privilege set. Only add `ROLE_ADMIN`, `BACKUP_ADMIN`, `BINLOG_ADMIN`, `SYSTEM_USER`, or other static privileges when a specific procedure requires them. In particular, `SYSTEM_USER` affects the administration of system accounts; do not grant it routinely to every DBA.

### 5.3. Restrict Hosts and Encrypt Connections

An account's host portion must match the actual connection origin. Prefer specific hosts/IPs or controlled network ranges. Avoid creating administrative accounts with host `%` without clear justification, as that configuration allows login attempts from more sources than intended. The `dba_ops` account in the example above is restricted to host `192.0.2.25` and requires TLS at creation time.

`REQUIRE SSL` forces connections to use TLS. If policy requires client certificate verification, consider `REQUIRE X509` and configure the appropriate CA and certificates. TLS protects the transport layer; it does not replace host restrictions, credential protection, or least-privilege grants.

`MAX_USER_CONNECTIONS` in the account creation example caps concurrent connections for `dba_ops`. This is a helpful resource control layer, though it does not replace application-tier limits, connection pooling, or load monitoring.

### 5.4. Restrict Delegation and Broad Administrative Privileges

Do not add `WITH GRANT OPTION` unless the account is responsible for granting privileges to others. When an account holds both broad privileges and `GRANT OPTION`, it can pass those privileges on to other accounts, making access control harder to govern.

Grant `CREATE USER` or `ROLE_ADMIN` only to the team responsible for identity and role management. Grant `FILE`, `SHUTDOWN`, `RELOAD`, `PROCESS`, or sensitive global privileges only when required by the task. For `SUPER` on legacy systems, catalog the operations still depending on it and gradually transition them to the finer-grained privileges supported by the current version.

### 5.5. Lock Unused Accounts and Revoke Privileges

Standby or break-glass administrative accounts can be kept locked until needed:

```sql
ALTER USER 'dba_breakglass'@'localhost' ACCOUNT LOCK;

-- Unlock only under controlled operational procedures
ALTER USER 'dba_breakglass'@'localhost' ACCOUNT UNLOCK;
```

Locking an account blocks logins with that account; granted privileges remain stored. When an account changes duties or no longer needs a privilege, revoke the corresponding privilege or role:

```sql
REVOKE SYSTEM_VARIABLES_ADMIN
  ON *.*
  FROM 'dba_ops'@'192.0.2.25';

REVOKE 'r_mysql_ops'@'%'
  FROM 'dba_ops'@'192.0.2.25';
```

If an account is no longer used, consider locking and then dropping it in line with your system's retention policy and change workflow. Do not drop shared or system accounts before verifying all services that depend on them.

## 6. Inspecting and Auditing Privileges

After granting privileges, verify the configuration from the perspective of the target account. The following statements assist verification:

```sql
-- List directly granted privileges and assigned roles
SHOW GRANTS FOR 'dba_ops'@'192.0.2.25';

-- View privileges supported by the current instance
SHOW PRIVILEGES;

-- Run while logged in as the account being verified
SELECT CURRENT_USER(), CURRENT_ROLE();
```

`SHOW GRANTS` confirms the privileges and roles assigned to an account. `CURRENT_ROLE()` shows the roles active in the current session. Afterward, test the actual business operations using that very account: required read queries must succeed, while out-of-scope writes or administrative actions must be denied. Looking solely at the `GRANT` statement without testing as the target account can miss issues such as unactivated roles or connections matching a different host entry.

Privilege audits should be conducted periodically and after personnel, application, or infrastructure changes:

1. List accounts and identify the owner, application, or process using each account.
2. Compare current privileges against actual tasks; look for global privileges, `GRANT OPTION`, and accounts with overly broad hosts.
3. Refactor shared privileges into task-based roles, then assign roles to the appropriate accounts.
4. Revoke redundant privileges and lock accounts that are no longer used.
5. Re-verify using `SHOW GRANTS`, `CURRENT_ROLE()`, and controlled test operations.

`GRANT`, `REVOKE`, `CREATE USER`, and `ALTER USER` are the proper privilege administration interfaces. You do not need to run `FLUSH PRIVILEGES` after these statements. `FLUSH PRIVILEGES` is mainly used to reload grant tables after direct edits outside supported SQL mechanisms; avoid editing system tables directly so you do not create inconsistent, hard-to-audit privilege states.

## 7. Common Design Mistakes

- **Granting `ALL PRIVILEGES` or `SUPER` for convenience:** overly broad privileges mean a misconfiguration or leaked credential can compromise the entire instance. Identify the exact statements that must run and grant the right privileges.
- **Assuming dynamic privileges can be scoped by database:** dynamic privileges are granted globally. Evaluate instance-wide impact before granting.
- **Confusing two accounts with the same name:** `'admin'@'localhost'` and `'admin'@'%'` are separate account entries. Check both user and host when auditing.
- **Creating roles but forgetting activation:** assigned roles do not always activate automatically in every configuration. Use `SET DEFAULT ROLE` and verify `CURRENT_ROLE()`.
- **Granting `GRANT OPTION` unnecessarily:** users can delegate privileges onward, expanding the access footprint.
- **Testing only with a DBA account:** a DBA account has broad privileges and does not reflect the experience of an application or reporting account. Always test with the target account.
- **Assuming every version shares the same dynamic privileges:** check `SHOW PRIVILEGES` and version-specific documentation, especially when moving between MySQL 5.7, MySQL 8.0/8.4, or MySQL-compatible distributions.

## 8. Hands-on Exercise

A sales system has a `sales` database. The web application needs to read, insert, and update orders; the reporting service only needs to read data; and an operations engineer needs to change system variables during occasional maintenance windows. Design three separate identities and answer the following questions:

1. Which static privileges should the application account receive and at what scope? Does it need `DROP`, `ALTER`, or `CREATE USER`?
2. What role could the reporting account receive for read-only access? Can read access be restricted further on certain sensitive columns?
3. Which dynamic privilege does the operations account need to change system variables? Why should `SUPER` or `ALL PRIVILEGES` not be granted?
4. Which hosts should be allowed to connect, is `REQUIRE SSL` or `REQUIRE X509` needed, and should `MAX_USER_CONNECTIONS` be capped?
5. Which statements will you use to verify granted privileges and prove that the reporting account cannot write data?

A solid design must be able to explain which specific operation each privilege supports. If you cannot name a task that requires a privilege, treat it as a candidate for removal from the role or account.

## Conclusion

Static privileges control MySQL's built-in operations on data and objects; dynamic privileges add specialized administrative capabilities, typically at the server-wide scope. By combining both privilege groups with roles, host restrictions, TLS, resource limits, and audit procedures, a system can grant applications and operators the exact capabilities they need while maintaining clear access boundaries. Check the privilege list on the exact MySQL version you run and verify the result using the actual account that will exercise those privileges.
