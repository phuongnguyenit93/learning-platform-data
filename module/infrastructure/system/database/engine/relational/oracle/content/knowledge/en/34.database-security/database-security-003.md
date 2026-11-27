# System Privileges, Object Privileges, Roles, and Grant Delegation

## 1. Privilege Model in Oracle Database

Oracle Database uses privileges to control which operations a user is allowed to perform and on which scope of objects. A user can receive privileges directly, through a role, or publicly through `PUBLIC`.

There are two fundamental categories of privileges:

- **System privileges** allow performing an action at the database level or across a broad scope of objects, such as connecting to the database, creating tables in one's own schema, or creating users.
- **Object privileges** allow performing a specific action on a specific object, such as reading the `HR.EMPLOYEES` table, updating specific columns, or executing a package.

A **Role** is a named collection of privileges and/or other roles used to manage, grant, and revoke privileges in groups. A role is not a third type of privilege; it is a mechanism for bundling and distributing privileges.

Oracle also provides two concepts related to delegation (re-granting):

- `WITH ADMIN OPTION`: applies when granting a system privilege or role, allowing the grantee to further grant that system privilege/role to another grantee.
- `WITH GRANT OPTION`: applies when granting an object privilege to a user, allowing that user to further grant the corresponding object privilege on the same object.

Understanding these scopes accurately helps avoid granting overly broad privileges, avoids relying on roles inside PL/SQL unexpectedly, and clarifies the impact before revoking privileges.

## 2. System Privileges

### 2.1. Scope of System Privileges

System privileges allow a user to perform a category of actions in the database. Some privileges only permit operations within the user's own schema; others include the `ANY` keyword and permit operations on objects across many other schemas.

Examples:

| System privilege | Primary capability |
|---|---|
| `CREATE SESSION` | Log in to the database |
| `CREATE TABLE` | Create tables in the user's own schema |
| `CREATE VIEW` | Create views in the user's own schema |
| `CREATE PROCEDURE` | Create procedures, functions, and packages in the user's own schema |
| `CREATE SEQUENCE` | Create sequences in the user's own schema |
| `CREATE USER` | Create database users |
| `ALTER USER` | Modify user attributes within the scope of granted privileges |
| `CREATE ANY TABLE` | Create tables in other users' schemas |
| `ALTER ANY TABLE` | Alter tables belonging to other schemas |
| `DROP ANY TABLE` | Drop tables belonging to other schemas |
| `SELECT ANY TABLE` | Query tables/views belonging to other schemas, within the privilege's scope |
| `GRANT ANY OBJECT PRIVILEGE` | Grant object privileges on objects not owned by the grantor, within the privilege's scope |
| `SELECT ANY DICTIONARY` | Read many data dictionary objects within the privilege's scope |

`ANY` privileges have a broad scope and can cross schema ownership boundaries. Grant them only when there is a clear administrative need; do not use them to replace narrow object privileges on a handful of tables.

### 2.2. CREATE TABLE and CREATE ANY TABLE

Two similarly named privileges with different scopes:

```sql
GRANT CREATE TABLE TO app_user;
```

Allows `APP_USER` to create tables in its own schema. The user also needs an appropriate tablespace quota or `UNLIMITED TABLESPACE` to allocate segments.

```sql
GRANT CREATE ANY TABLE TO deployment_user;
```

Allows `DEPLOYMENT_USER` to create tables in other schemas. This is a broader administrative privilege and should not be granted to standard application accounts.

Similarly, `CREATE VIEW` only allows creating views in one's own schema; `CREATE ANY VIEW` expands the scope to other schemas. When designing privileges, distinguish actions within an owned schema from database-wide actions.

### 2.3. Granting System Privileges

Basic syntax:

```sql
GRANT CREATE SESSION TO app_user;
GRANT CREATE TABLE, CREATE VIEW TO app_developer;
GRANT SELECT ANY TABLE TO reporting_admin;
```

The grantor must hold appropriate administrative privileges, such as having received that system privilege with `ADMIN OPTION` or holding `GRANT ANY PRIVILEGE`. These administrative privileges carry broad scope; granting them must be tightly controlled.

### 2.4. System Privileges Do Not Automatically Grant All Operation Types

Some privilege names are easily misunderstood as broader than their actual scope:

- `CREATE TABLE` does not allow a user to create tables in another user's schema.
- `CREATE SESSION` only allows opening a session; it does not grant read access to business tables.
- `SELECT ANY TABLE` does not imply permission to modify or delete data.
- `UNLIMITED TABLESPACE` relates to tablespace quota, not object privileges on tables.
- `GRANT ANY OBJECT PRIVILEGE` is the privilege to grant privileges on objects, not permission to use every object on the owner's behalf in all situations.

Do not infer privileges from similar-sounding names. Check the specific privilege in the documentation for your Oracle version and inspect current privilege views.

## 3. Object Privileges

### 3.1. Scope of Object Privileges

An object privilege grants permission to perform an action on a specified object. The object can be a table, view, materialized view, sequence, procedure, function, package, directory, or other Oracle-supported object type.

Examples:

```sql
GRANT SELECT ON hr.employees TO reporting_user;
GRANT INSERT, UPDATE ON sales.orders TO order_app;
GRANT EXECUTE ON hr.payroll_api TO payroll_app;
GRANT SELECT ON sales.order_seq TO order_app;
```

These privileges apply strictly to the specified object. `SELECT ON HR.EMPLOYEES` does not grant read access to other tables in the `HR` schema.

### 3.2. Common Object Privileges

| Privilege | Commonly applicable objects | Capability |
|---|---|---|
| `SELECT` | Table, view, sequence, and certain compatible objects | Read data/values depending on object type |
| `READ` | Table, view, external table in supported versions | Read data without permitting `SELECT ... FOR UPDATE` |
| `INSERT` | Table, view | Insert rows |
| `UPDATE` | Table, view | Update permitted rows/columns |
| `DELETE` | Table, view | Delete rows |
| `ALTER` | Table, sequence, and certain compatible objects | Modify attributes/definitions depending on object type |
| `INDEX` | Table | Create indexes on the table |
| `REFERENCES` | Table | Create foreign keys referencing the granted table/columns |
| `EXECUTE` | Procedure, function, package, type | Invoke programs or use types per granted privilege |
| `READ`, `WRITE` | Directory | Read/write files in the directory object per granted capabilities |

The exact privilege set depends on the object type and Oracle version. For example, not every object supports `INSERT`, `UPDATE`, or `DELETE`.

### 3.3. Granting Object Privileges

```sql
GRANT SELECT ON hr.employees TO analyst_user;

GRANT SELECT, INSERT, UPDATE, DELETE
ON sales.orders
TO order_app;

GRANT EXECUTE ON hr.employee_api TO hr_app;
```

The object owner can grant object privileges on their own objects. Others can grant them if they received the privilege with `GRANT OPTION` or hold an appropriate administrative system privilege, such as `GRANT ANY OBJECT PRIVILEGE` within Oracle's permitted scope.

### 3.4. Restricting UPDATE Privileges by Column

Oracle allows restricting `UPDATE` to specific columns:

```sql
GRANT UPDATE (email, phone_number)
ON hr.employees
TO hr_support;
```

User `HR_SUPPORT` can update the two specified columns, but cannot update `SALARY` or other columns through this grant. This grants privileges more narrowly to match business needs compared to table-wide `UPDATE`.

Similarly, `INSERT` can be restricted to a column list:

```sql
GRANT INSERT (customer_id, order_date, status)
ON sales.orders
TO order_app;
```

When granting column-level privileges, verify that the application's actual SQL statements specify the matching columns.

### 3.5. READ vs. SELECT

`READ` was added to allow reading data without granting the ability to lock rows via `SELECT ... FOR UPDATE`. If an application only needs to query data and never locks rows, `READ` can be a narrower privilege than `SELECT` in supported versions.

Example:

```sql
GRANT READ ON hr.employees TO report_reader;
```

If the application needs `SELECT ... FOR UPDATE`, the appropriate privilege is `SELECT` along with the other requirements of the statement. Check your database version and privilege documentation before using `READ`.

## 4. Roles: Grouping Privileges

### 4.1. Why Use Roles?

If an administrator grants individual object privileges directly to hundreds of users, onboarding, changing job functions, and revoking access become complex. Roles allow modeling privileges by responsibility:

```text
report_reader_role
  ├── CREATE SESSION
  ├── SELECT ON HR.EMPLOYEES
  └── SELECT ON SALES.ORDERS

report_writer_role
  ├── CREATE SESSION
  ├── SELECT ON SALES.ORDERS
  └── INSERT, UPDATE ON SALES.ORDERS

Users
  ├── analyst_01  -> report_reader_role
  ├── analyst_02  -> report_reader_role
  └── order_app   -> report_writer_role
```

When a user changes roles, the DBA can swap granted roles instead of editing each privilege directly. Roles also separate privileges for applications, business users, and administrators.

### 4.2. Creating Roles and Granting Privileges to Roles

```sql
CREATE ROLE report_reader_role;

GRANT CREATE SESSION TO report_reader_role;
GRANT SELECT ON hr.employees TO report_reader_role;
GRANT SELECT ON sales.orders TO report_reader_role;
```

Then grant the role to users:

```sql
GRANT report_reader_role TO analyst_01;
GRANT report_reader_role TO analyst_02;
```

Users receive the privileges in the role when the role is enabled in their session. A user can be granted multiple roles.

### 4.3. Roles Can Contain Other Roles

Oracle allows granting a role to another role, creating a nested role structure:

```sql
CREATE ROLE order_read_role;
CREATE ROLE order_write_role;
CREATE ROLE order_app_role;

GRANT SELECT ON sales.orders TO order_read_role;
GRANT INSERT, UPDATE ON sales.orders TO order_write_role;

GRANT order_read_role TO order_app_role;
GRANT order_write_role TO order_app_role;

GRANT order_app_role TO order_app;
```

`ORDER_APP` receives privileges from `ORDER_APP_ROLE` and its nested roles. Nested roles help reuse privilege bundles, but also make traceability harder. Keep the role tree simple, use names that reflect function, and avoid overly deep dependency chains.

### 4.4. Default Roles and Non-Default Roles

Upon login, Oracle enables a user's default roles. Non-default roles can be enabled via `SET ROLE` if the user is allowed to use them:

```sql
ALTER USER analyst_01
  DEFAULT ROLE report_reader_role;
```

In a session:

```sql
SET ROLE report_reader_role;
```

You can inspect currently enabled roles:

```sql
SELECT role
FROM session_roles
ORDER BY role;
```

`DBA_ROLE_PRIVS` shows which roles are granted to a user/role and their default status; `SESSION_ROLES` shows the roles currently enabled in the session. The two views answer different questions.

### 4.5. Password-Protected Roles and Secure Application Roles

Oracle supports roles that require a password to enable, as well as secure application roles that can only be enabled through a configured PL/SQL package. Secure application roles help an application decide when and under what conditions to activate a role, such as allowing sensitive privileges only after the user passes an additional authentication step.

Conceptual example:

```sql
CREATE ROLE payroll_sensitive_role
  IDENTIFIED USING security_admin.role_guard;
```

The `SECURITY_ADMIN.ROLE_GUARD` package is configured as the verification mechanism when the role is enabled. You must properly implement the secure package, execute privileges, and validation logic; merely creating a role with `IDENTIFIED USING` is not enough to build a complete security policy.

## 5. WITH ADMIN OPTION and WITH GRANT OPTION

Both options allow delegating privileges, but they apply to two different grant types and have different revocation rules.

### 5.1. WITH ADMIN OPTION for System Privileges

Example:

```sql
GRANT CREATE SESSION TO security_admin
WITH ADMIN OPTION;
```

`SECURITY_ADMIN` is allowed to use `CREATE SESSION` and further grant this system privilege to other users/roles:

```sql
CONNECT security_admin/...

GRANT CREATE SESSION TO app_user;
```

`ADMIN OPTION` is a grant administration privilege. The recipient can grant the system privilege to others and manage corresponding grants per Oracle rules. Grant this option only to accounts responsible for privilege administration.

### 5.2. WITH GRANT OPTION for Object Privileges

Example:

```sql
GRANT SELECT ON hr.employees TO hr_reporting_admin
WITH GRANT OPTION;
```

`HR_REPORTING_ADMIN` can read the table and further grant `SELECT` on that exact object:

```sql
CONNECT hr_reporting_admin/...

GRANT SELECT ON hr.employees TO report_user;
```

The delegation right is tied to the specific object privilege. Having `SELECT ... WITH GRANT OPTION` on `HR.EMPLOYEES` does not mean the user is granted privileges on `HR.DEPARTMENTS` or `UPDATE` on `HR.EMPLOYEES`.

Oracle does not allow granting object privileges with `WITH GRANT OPTION` to a role or to `PUBLIC`. If you need to distribute object privileges through a role, grant the privilege to the role without the grant option, then grant the role to users.

### 5.3. ADMIN OPTION When Granting a Role

A role can also be granted with `ADMIN OPTION`:

```sql
GRANT report_reader_role TO department_admin
WITH ADMIN OPTION;
```

`DEPARTMENT_ADMIN` can grant that role to other users or roles per Oracle rules. This is a privilege to manage role distribution, not a right to re-grant individual object privileges inside the role as direct grants.

### 5.4. Comparing the Two Options

| Attribute | `WITH ADMIN OPTION` | `WITH GRANT OPTION` |
|---|---|---|
| Used for | System privileges and roles | Object privileges |
| Allows delegating | The corresponding system privilege/role | The corresponding object privilege on the same object |
| Can be granted to a role? | Can be used when granting system privileges/roles per Oracle syntax and rules | Object privileges cannot be granted with grant option to a role |
| Main risk | Expands administrative and privilege distribution rights | Creates object privilege grant chains that must be tracked on revoke |
| Example statement | `GRANT CREATE SESSION TO admin WITH ADMIN OPTION` | `GRANT SELECT ON hr.employees TO admin WITH GRANT OPTION` |

Do not confuse `ADMIN OPTION` with `GRANT OPTION`. Using the wrong option can give a user broader privilege-delegation powers than intended.

## 6. Who Can Grant Privileges?

### 6.1. Granting System Privileges

A system privilege can be granted by a user with appropriate administrative privileges, for example:

- A user who received that exact system privilege with `ADMIN OPTION`.
- A user who holds `GRANT ANY PRIVILEGE`.
- An administrative account such as `SYS` acting under database administration policies.

### 6.2. Granting Object Privileges

An object privilege can be granted by:

- The object owner.
- A user who received the corresponding object privilege with `GRANT OPTION`.
- A user who holds the `GRANT ANY OBJECT PRIVILEGE` system privilege within the scope permitted by Oracle.

A user who only receives `SELECT` through a role cannot automatically grant `SELECT ON object` to another user. To re-grant directly, the user must hold the appropriate granting authority per Oracle rules; merely being able to use a privilege in a session does not confer grant administration rights.

### 6.3. Granting Roles

A role is granted by a user authorized to manage that role, such as its creator/owner or a user who received the role with `ADMIN OPTION`, depending on the case. `GRANT ANY ROLE` is a broad system privilege to grant/revoke roles; do not grant it to application accounts.

## 7. REVOKE and Revocation Effects

### 7.1. Revoking System Privileges

```sql
REVOKE CREATE SESSION FROM app_user;
REVOKE SELECT ANY TABLE FROM reporting_admin;
```

Revoking a system privilege from a grantee removes that grant from the grantee. For system privileges granted with `ADMIN OPTION`, revoking does not automatically cascade to revoke the privilege from other users/roles to whom the grantee previously granted it. Downstream grants must be inspected and managed separately.

This differs from object privileges with `GRANT OPTION`. Do not assume every grant chain behaves identically with cascading on revoke.

### 7.2. Revoking Object Privileges with Grant Option

Suppose:

```sql
-- HR is the owner
GRANT SELECT ON hr.employees TO user_a WITH GRANT OPTION;

-- USER_A delegates further
GRANT SELECT ON hr.employees TO user_b WITH GRANT OPTION;

-- USER_B delegates further
GRANT SELECT ON hr.employees TO user_c;
```

If the owner `HR` revokes the privilege from `USER_A`:

```sql
REVOKE SELECT ON hr.employees FROM user_a;
```

Oracle cascades the revoke to dependent object privileges granted down that chain, including the grants to `USER_B` and `USER_C` in this example. This is why grant chains must be tracked when using `WITH GRANT OPTION`.

If a user holds a direct privilege and simultaneously receives the same privilege via a role, revoking one source does not necessarily remove the other source. Check all privilege paths before concluding a user has lost access.

### 7.3. Revoking Privileges from a Role

```sql
REVOKE SELECT ON hr.employees FROM report_reader_role;
```

Users receiving the privilege through `REPORT_READER_ROLE` will no longer have that privilege from the role once the change takes effect in the appropriate session. However, if a user still holds `SELECT` directly or through another role, access may still remain.

### 7.4. Revoking a Role from a User

```sql
REVOKE report_reader_role FROM analyst_01;
```

The user loses privileges originating from this role once the role is no longer granted/enabled. Privileges granted directly or through other roles are not automatically removed.

### 7.5. REFERENCES and CASCADE CONSTRAINTS

When granted `REFERENCES` on a table, a grantee can create foreign keys referencing the granted columns. If `REFERENCES` is revoked while dependent foreign key constraints exist, Oracle may require `CASCADE CONSTRAINTS`:

```sql
REVOKE REFERENCES ON hr.departments
FROM hr_app
CASCADE CONSTRAINTS;
```

This clause allows revoking dependent constraints per Oracle rules. Because it affects data structures, identify impacted foreign keys before executing it.

## 8. Roles and Privileges in PL/SQL

### 8.1. Definer's Rights: Roles Are Disabled

Stored PL/SQL units default to running with the owner's privileges (definer's rights, `AUTHID DEFINER`). In this execution context, user roles are not used to determine the unit's access rights; privileges required for static SQL must be granted directly to the PL/SQL unit's owner (or via `PUBLIC` where applicable).

For example, if a package in schema `APP_OWNER` reads `HR.EMPLOYEES`:

```sql
GRANT SELECT ON hr.employees TO app_owner;
```

Granting `SELECT ON HR.EMPLOYEES` only to a role and granting that role to `APP_OWNER` may suffice for interactive queries in a session, but is not enough for a definer-rights PL/SQL unit to use that privilege. A direct grant to the owner is required.

### 8.2. Invoker's Rights: Privileges Follow the Caller

A PL/SQL unit declared with `AUTHID CURRENT_USER` runs under the invoker's privileges. In an invoker's rights context, the caller's enabled roles can be evaluated per Oracle rules. This is useful when a single unit needs to execute with the distinct privileges of different callers.

```sql
CREATE OR REPLACE PROCEDURE read_employee_data
AUTHID CURRENT_USER
AS
BEGIN
  -- SQL executes using invoker's privilege context.
  NULL;
END;
/
```

Choosing between `AUTHID DEFINER` and `AUTHID CURRENT_USER` is a security design decision. Invoker's rights is not simply a way to turn on roles arbitrarily; you must analyze schema resolution, the invoker's privileges, and access to all objects referenced by the unit.

### 8.3. Checking Session Roles Does Not Replace PL/SQL Verification

`SESSION_ROLES` displays roles enabled in the interactive session. Upon entering a definer-rights unit, the effective role set changes according to the PL/SQL execution context. Therefore, do not use `SESSION_ROLES` results from outside the unit to conclude that a package definitely has permission to run its internal SQL.

## 9. Data Dictionary Views for Inspecting Privileges

### 9.1. System Privileges Granted Directly to Users

```sql
SELECT grantee,
       privilege,
       admin_option
FROM dba_sys_privs
WHERE grantee IN ('APP_USER', 'REPORT_READER_ROLE')
ORDER BY grantee, privilege;
```

`DBA_SYS_PRIVS` displays system privileges granted to users/roles. `USER_SYS_PRIVS` and `SESSION_PRIVS` provide narrower views of the current user and currently active session privileges.

### 9.2. Object Privileges

```sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM dba_tab_privs
WHERE owner = 'HR'
  AND table_name = 'EMPLOYEES'
ORDER BY grantee, privilege;
```

`GRANTABLE='YES'` indicates the object privilege was granted with the grant option. You can also use `USER_TAB_PRIVS` and `ALL_TAB_PRIVS` depending on your privilege scope and the objects to inspect.

### 9.3. Roles Granted to Users/Roles

```sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role
FROM dba_role_privs
WHERE grantee IN ('APP_USER', 'APP_ROLE')
ORDER BY grantee, granted_role;
```

`ADMIN_OPTION='YES'` indicates the role was granted with delegation rights; `DEFAULT_ROLE` indicates whether the role is enabled by default on login. Nested roles may require tracing further through rows where the grantee is itself a role.

### 9.4. Privileges Inside a Role

```sql
SELECT role, privilege, admin_option
FROM role_sys_privs
WHERE role = 'REPORT_READER_ROLE'
ORDER BY privilege;

SELECT role, owner, table_name, privilege
FROM role_tab_privs
WHERE role = 'REPORT_READER_ROLE'
ORDER BY owner, table_name, privilege;
```

`ROLE_SYS_PRIVS`, `ROLE_TAB_PRIVS`, and `ROLE_ROLE_PRIVS` help inspect system privileges, object privileges, and nested roles inside a role.

### 9.5. Active Privileges in the Session

```sql
SELECT * FROM session_privs ORDER BY privilege;
SELECT * FROM session_roles ORDER BY role;
```

`SESSION_PRIVS` reflects effective system privileges in the session; `SESSION_ROLES` lists currently enabled roles. To investigate a specific access right, combine these views with direct grants, object grants, and the role hierarchy.

`DBA_*` views require appropriate data dictionary read privileges. In production environments, grant access to administrative metadata via a dedicated DBA/audit role rather than granting `SELECT ANY DICTIONARY` just to inspect a few views.

## 10. Privilege Design Patterns Following Least Privilege

### 10.1. Separating Owner Schema and Application Schema

A common pattern is having the schema owner hold tables/packages while the application user receives only the necessary privileges:

```text
HR_OWNER
  ├── owns EMPLOYEES, DEPARTMENTS
  └── owns EMPLOYEE_API package

HR_APP_ROLE
  ├── EXECUTE ON HR_OWNER.EMPLOYEE_API
  └── CREATE SESSION

HR_APP_USER
  └── receives HR_APP_ROLE
```

The application calls APIs/packages instead of having direct update privileges on every table. This creates a business control boundary and narrows data privilege scope.

### 10.2. Do Not Grant DBA or ANY Privileges to Application Accounts

The `DBA` role contains many powerful system privileges. `SELECT ANY TABLE`, `UPDATE ANY TABLE`, `DROP ANY TABLE`, `GRANT ANY OBJECT PRIVILEGE`, and similar privileges can expand the impact radius across multiple schemas.

A typical application should receive:

- `CREATE SESSION` to connect.
- Minimal object privileges on the tables/views/packages it needs to use.
- Dedicated sequence or directory privileges if functionally required.
- Task-specific roles with clear owners and administrators.

Do not grant `CREATE TABLE`, `CREATE PROCEDURE`, or DDL privileges to a runtime account if the application does not need to create objects during operation. Separating deployment/migration accounts from runtime accounts reduces risk.

### 10.3. Task-Based Roles, Not Per-User Roles

Role names should reflect business functions, such as `ORDER_READ_ROLE`, `ORDER_WRITE_ROLE`, and `PAYROLL_APPROVER_ROLE`. Users receive one or more roles corresponding to their duties. Avoid creating individual roles per user or overly broad catch-all roles without clear ownership.

### 10.4. Periodic Reviews

Periodically check:

- Decommissioned users that still retain roles/privileges.
- Roles with strong privileges or nested roles that are no longer needed.
- Where `ADMIN_OPTION` and `GRANTABLE` are enabled.
- Application users holding `ANY`, DDL, or administrative system privileges beyond need.
- Direct object privileges granted outside the role model.
- Grant-option chains creating dependencies during revocation.
- Access used by definer-rights PL/SQL having complete direct grants.

## 11. Complete Example: Creating a Reporting Role with Controlled Delegation

Suppose schema `HR` owns the `EMPLOYEES` table; the reporting team needs to read the table, and a department administrator is allowed to grant the role to members of the team.

```sql
-- 1. DBA creates the functional role
CREATE ROLE hr_report_reader;

-- 2. Owner grants connection and required data read privileges
GRANT CREATE SESSION TO hr_report_reader;
GRANT SELECT ON hr.employees TO hr_report_reader;

-- 3. DBA grants the role to an end user
GRANT hr_report_reader TO analyst_01;

-- 4. DBA grants the role to the department admin with ADMIN OPTION
GRANT hr_report_reader TO department_admin
WITH ADMIN OPTION;

-- 5. Department admin can distribute the role to other staff
-- (executed in department_admin's session)
GRANT hr_report_reader TO analyst_02;

-- 6. Inspect role grants
SELECT grantee, granted_role, admin_option, default_role
FROM dba_role_privs
WHERE granted_role = 'HR_REPORT_READER';

-- 7. When analyst_01 transfers teams, DBA revokes the role
REVOKE hr_report_reader FROM analyst_01;
```

In this example, `DEPARTMENT_ADMIN` can re-grant the role because it was granted with `ADMIN OPTION`. End users receive privileges through the role and cannot themselves grant the `SELECT ON HR.EMPLOYEES` object privilege to others. If an object privilege must be revoked from all role users, the owner can revoke it from the role; if only one user leaves the group, revoke the role from that user.

## 12. Key Principles to Remember

1. System privileges allow actions at database/schema scope; object privileges allow operations on specific objects.
2. `CREATE TABLE` differs from `CREATE ANY TABLE`; privileges with `ANY` typically expand blast radius significantly.
3. Roles bundle system privileges, object privileges, and other roles for functional management.
4. Privileges received via roles may depend on enabled roles; direct grants and role grants must be distinguished.
5. `WITH ADMIN OPTION` is for system privileges/roles; `WITH GRANT OPTION` is for object privileges.
6. Object privileges cannot be granted to a role with `WITH GRANT OPTION`.
7. Revoking an object privilege granted with grant option can cascade to dependent grants; revoking a system privilege does not auto-cascade the same way.
8. Definer-rights PL/SQL does not use the owner's roles during execution; grant required privileges directly to the owner.
9. Inspect `DBA_SYS_PRIVS`, `DBA_TAB_PRIVS`, `DBA_ROLE_PRIVS`, `ROLE_*`, and `SESSION_*` views to trace privileges.
10. Design with least privilege, limit `ANY`/admin privileges, and review delegation chains periodically.

## Oracle Reference Documentation

- [Oracle Database 19c SQL Language Reference — GRANT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/GRANT.html)
- [Oracle Database 19c SQL Language Reference — REVOKE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/REVOKE.html)
- [Oracle Database 19c Security Guide — Configuring Privilege and Role Authorization](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/configuring-privilege-and-role-authorization.html)
- [Oracle Database 19c Database Reference — DBA_SYS_PRIVS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_SYS_PRIVS.html)
- [Oracle Database 19c Database Reference — DBA_TAB_PRIVS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TAB_PRIVS.html)
- [Oracle Database 19c Database Reference — DBA_ROLE_PRIVS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_ROLE_PRIVS.html)
# System Privileges, Object Privileges, Roles, and Grant Delegation

Oracle Database manages access control across multiple layers. A user can be allowed to log in to the database without being able to create tables; allowed to call a package without being able to read the underlying tables directly; or receive privileges through a role enabled in the session. When administering privileges, you must clearly distinguish **system privileges**, **object privileges**, **roles**, and delegation options such as `WITH ADMIN OPTION` or `WITH GRANT OPTION`.

These concepts determine who can perform which operation, within what scope, and who is permitted to pass those privileges to others. Lumping them together into a generic notion of "user permissions" easily leads to over-privileged accounts, hard-to-trace effective rights, and confusing errors when executing PL/SQL.

## 1. Privilege Model in Oracle

The privilege model can be viewed in three components:

- **Privilege:** permission to perform an operation. A privilege can be a system privilege or an object privilege.
- **Role:** a group containing system privileges, object privileges, and other roles. Roles enable granting privileges by function or responsibility.
- **Grantee:** a user, role, or `PUBLIC` receiving a privilege or role.

For example, a sales application might be structured as follows:

| Component | Role |
|---|---|
| `DATA_OWNER` | Owns business tables |
| `APP_OWNER` | Owns application packages and objects |
| `APP_RUNTIME` | User the application uses to connect |
| `ORDER_ENTRY_ROLE` | Role allowing creation and updating of orders |
| `ORDER_REPORT_ROLE` | Read-only role for reporting data |

Privileges can be organized into chains:

```text
System privileges ───────┐
                         ├──> Role ───> User
Object privileges ───────┘       │
                                 └──> Another role (nested role)

System/Object privilege ─────────────> Direct to user
System/Object privilege ─────────────> PUBLIC
```

Privileges granted directly to a user and privileges received through roles can coexist. Effective privileges in a session also depend on which roles are enabled and the execution context (direct SQL, definer-rights PL/SQL, or invoker-rights PL/SQL).

## 2. System Privileges: Permissions to Perform Database-Level Operations

A system privilege allows a user to perform a type of operation on the database or across schemas specified by the privilege. It is not tied to a single table or package.

Common system privileges:

| System privilege | General meaning |
|---|---|
| `CREATE SESSION` | Connect to the database |
| `CREATE TABLE` | Create tables in the user's own schema |
| `CREATE VIEW` | Create views in the user's own schema |
| `CREATE SEQUENCE` | Create sequences in the user's own schema |
| `CREATE PROCEDURE` | Create procedures, functions, and packages in the user's own schema |
| `CREATE TRIGGER` | Create triggers in the user's own schema |
| `CREATE SYNONYM` | Create synonyms in the user's own schema |
| `CREATE ANY TABLE` | Create tables in other schemas within the `ANY` system privilege scope |
| `ALTER ANY TABLE` | Alter table structures across schemas within the privilege scope |
| `SELECT ANY TABLE` | Read tables/views within the privilege scope across multiple schemas |
| `CREATE ANY PROCEDURE` | Create program units in other schemas within the privilege scope |
| `GRANT ANY PRIVILEGE` | Grant system privileges that the grantor is authorized to administer under this privilege |
| `GRANT ANY ROLE` | Grant roles within role administration privilege scope |
| `ALTER SYSTEM` | Perform system operations permitted by this privilege |

Names containing `ANY` generally allow actions beyond the user's own schema and have broad scope. Do not grant `CREATE ANY TABLE`, `SELECT ANY TABLE`, `ALTER ANY TABLE`, or other `ANY` privileges just to make an application work. Identify the specific objects and grant object privileges if the requirement is limited to specific objects.

### 2.1. Distinguishing Own-Schema Privileges from ANY Privileges

Example:

```sql
-- APP_DEVELOPER only creates tables in its own schema.
GRANT CREATE TABLE TO app_developer;

-- Broader privilege: can create tables in other schemas under ANY scope.
GRANT CREATE ANY TABLE TO app_admin;
```

`CREATE TABLE` does not mean a user can create tables in any schema. Likewise, `CREATE PROCEDURE` permits creating program units in the user's own schema; `CREATE ANY PROCEDURE` has a wider scope.

Object creation privileges also relate to tablespace quotas and other conditions. Having `CREATE TABLE` does not automatically guarantee the user has enough quota to allocate segments in a tablespace. Administrators must verify both object creation privileges and storage limits.

### 2.2. Granting System Privileges

Basic syntax:

```sql
GRANT CREATE SESSION TO app_runtime;
GRANT CREATE TABLE TO app_developer;
```

System privileges can be granted to a role for group management:

```sql
CREATE ROLE schema_developer_role;

GRANT CREATE TABLE,
      CREATE VIEW,
      CREATE SEQUENCE,
      CREATE PROCEDURE
TO schema_developer_role;

GRANT schema_developer_role TO app_developer;
```

In this example, `APP_DEVELOPER` receives the privileges via a role. If the role is enabled in the session, the user can exercise those system privileges in standard SQL contexts where roles take effect.

### 2.3. Who Can Grant System Privileges?

Normally, a system privilege can be granted by a user with appropriate administrative privileges, such as a user holding `GRANT ANY PRIVILEGE`, or a user who received that system privilege with `ADMIN OPTION`. Such powerful administrative privileges should be kept on controlled administrative accounts.

A system privilege can be granted with `WITH ADMIN OPTION`:

```sql
GRANT CREATE TABLE
TO team_lead
WITH ADMIN OPTION;
```

`TEAM_LEAD` can use `CREATE TABLE` and re-grant this system privilege to other users or roles. This is an administrative right, not merely a usage right. Grant it only when the recipient is genuinely responsible for managing privileges for another group.

## 3. Object Privileges: Permissions on a Specific Object

An object privilege permits performing an operation on a designated object, such as a table, view, sequence, procedure, function, package, or directory.

For example, a reporting user only needs to read `APP.ORDERS`:

```sql
GRANT SELECT
ON app.orders
TO report_user;
```

This privilege applies only to `APP.ORDERS`. It does not grant read access to all other tables in the `APP` schema or the database.

### 3.1. Common Object Privileges by Object Type

| Object type | Commonly used object privileges |
|---|---|
| Table/view/materialized view | `SELECT`, `READ`, `INSERT`, `UPDATE`, `DELETE`, `ALTER`, `INDEX`, `REFERENCES`, `FLASHBACK`, `DEBUG` (varies by object/version) |
| Sequence | `SELECT`, `ALTER` |
| Procedure/function/package | `EXECUTE`, `DEBUG` |
| Type | `EXECUTE`, `UNDER` where supported |
| Directory | `READ`, `WRITE`, `EXECUTE` as required |

Not every privilege in the table applies to every object type. Check the object type and Oracle version before granting privileges.

### 3.2. Table and View Privileges

| Privilege | Effect |
|---|---|
| `SELECT` | Query data from a table/view |
| `READ` | Read data with narrower scope than `SELECT`, e.g. disallowing `SELECT FOR UPDATE` |
| `INSERT` | Insert rows |
| `UPDATE` | Update granted rows or columns |
| `DELETE` | Delete rows |
| `ALTER` | Alter object definition within permitted scope |
| `INDEX` | Create indexes on a table within privilege scope |
| `REFERENCES` | Create foreign keys referencing granted columns |
| `FLASHBACK` | Perform flashback queries permitted by the privilege |

Example granting read and insert on orders:

```sql
GRANT SELECT, INSERT
ON app.orders
TO order_entry_user;
```

Example granting update on specific columns:

```sql
GRANT UPDATE (order_status, total_amount)
ON app.orders
TO order_entry_user;
```

Column-level privileges restrict the scope of modification. `ORDER_ENTRY_USER` can update the status and total amount, but is not automatically allowed to update every other column in the table.

Oracle supports granting certain object privileges at the column level, such as `INSERT`, `UPDATE`, and `REFERENCES`. Example:

```sql
GRANT INSERT (customer_id, order_date, total_amount)
ON app.orders
TO order_entry_user;
```

Not every privilege has a column-level form. Use only the syntax supported for the corresponding privilege.

### 3.3. Sequence Privileges

Sequences are commonly used to generate IDs. A user needs `SELECT` privilege to call `NEXTVAL` or `CURRVAL` on a sequence they do not own; `ALTER` permits modifying sequence attributes within the granted scope.

```sql
GRANT SELECT
ON app.order_id_seq
TO app_runtime;
```

The user can then reference the sequence:

```sql
SELECT app.order_id_seq.NEXTVAL
FROM dual;
```

Read access on a sequence does not imply `INSERT` privilege on the table that uses the sequence. These two privileges govern two separate objects.

### 3.4. EXECUTE Privilege on Packages, Procedures, and Functions

To allow a user to invoke a package owned by another schema, the owner can grant `EXECUTE`:

```sql
GRANT EXECUTE
ON app_owner.order_api
TO app_runtime;
```

`EXECUTE` allows calling public subprograms declared in the package specification. It does not expose private procedures/functions declared only in the package body.

Permission to call a package also does not mean the caller can directly read the tables used inside the package. This is especially important for `AUTHID DEFINER` packages: the package can operate on objects using the owner's privileges while the caller holds only `EXECUTE`. However, the package must validate inputs and never turn the owner's privileges into an arbitrary SQL execution path.

## 4. Owners, Grantees, and Default Object Privileges

The user who creates an object is its owner. The owner has full authority to manage the object and can grant appropriate object privileges to users, roles, or `PUBLIC`.

For example, `APP` creates the `ORDERS` table. `APP` can query and modify the table by ownership without granting `SELECT`, `INSERT`, or `UPDATE` to itself.

When other users need access, the owner grants specific privileges:

```sql
GRANT SELECT
ON app.orders
TO reporting_role;

GRANT INSERT, UPDATE (order_status)
ON app.orders
TO order_entry_role;
```

If recipients need to reference the object without a schema prefix, a private or public synonym can be created. A synonym is purely an alias; it does not grant privileges. Users still need privileges on the target object.

```sql
CREATE SYNONYM orders FOR app.orders;
```

Creating a synonym does not give a user permission to read `APP.ORDERS` if `SELECT` or another appropriate privilege has not been granted.

## 5. Roles: Grouping Privileges by Function

A role is a security object used to group system privileges, object privileges, and other roles. Rather than granting individual privileges to many users, an administrator can grant privileges to a role and then grant the role to users.

Example creating a reporting read role:

```sql
CREATE ROLE order_report_role;

GRANT SELECT
ON app.orders
TO order_report_role;

GRANT SELECT
ON app.customers
TO order_report_role;

GRANT order_report_role
TO report_user;
```

When `ORDER_REPORT_ROLE` is enabled, `REPORT_USER` can read both granted objects. When a user moves to another job, the administrator can revoke the role without having to revoke each individual privilege.

### 5.1. Nested Roles

One role can be granted to another role. This allows building layered privilege groups:

```sql
CREATE ROLE order_read_role;
CREATE ROLE customer_read_role;
CREATE ROLE sales_report_role;

GRANT SELECT ON app.orders TO order_read_role;
GRANT SELECT ON app.customers TO customer_read_role;

GRANT order_read_role TO sales_report_role;
GRANT customer_read_role TO sales_report_role;

GRANT sales_report_role TO report_user;
```

`REPORT_USER` receives read access to both tables through the composite role `SALES_REPORT_ROLE`. This organization promotes reuse of privilege sets, though deeply nested roles can make tracing effective privileges harder. Name roles by function and keep the structure simple.

### 5.2. Default Roles and Active Roles

Roles granted to a user can be configured as default roles. Default roles are enabled when the user logs in, unless configuration or session actions alter their state.

You can specify default roles:

```sql
ALTER USER report_user
DEFAULT ROLE order_report_role;
```

Or disable all default roles:

```sql
ALTER USER report_user DEFAULT ROLE NONE;
```

Within a session, a user can enable or disable allowed roles:

```sql
SET ROLE order_report_role;
```

```sql
SET ROLE NONE;
```

Multiple roles can be enabled:

```sql
SET ROLE order_report_role, customer_read_role;
```

Having a role granted does not guarantee it is always enabled. When a SQL statement reports insufficient privileges, check currently active roles and effective privileges in the session.

### 5.3. Password-Protected Roles and Secure Application Roles

Oracle supports mechanisms to control role activation, including password-protected roles and secure application roles enabled through an authenticating package. Secure application roles are typically suited when an application should only activate privileges after satisfying business or security conditions.

Conceptual example:

```sql
CREATE ROLE order_approval_role
IDENTIFIED USING app_owner.role_guard;
```

The `ROLE_GUARD` package is responsible for validating context before calling `DBMS_SESSION.SET_ROLE` for the protected role. Exact syntax and design details must follow the requirements of your deployed Oracle Database version. Secure application roles should not be treated as a substitute for application-tier user authentication or least privilege.

### 5.4. PUBLIC as a Special Role

`PUBLIC` is a special grantee representing all database users. When a privilege or role is granted to `PUBLIC`, every user can receive that privilege via the corresponding mechanism.

Example:

```sql
GRANT SELECT ON app.reference_codes TO PUBLIC;
```

This may suit certain database-wide public reference data, but should not be used just to simplify application configuration. For business data or sensitive packages, grant privileges to specific roles or users.

## 6. WITH GRANT OPTION and WITH ADMIN OPTION

Both options deal with forwarding privileges, but apply to different privilege categories.

| Criterion | `WITH GRANT OPTION` | `WITH ADMIN OPTION` |
|---|---|---|
| Applies to | Object privileges | System privileges and roles |
| What can the recipient do? | Re-grant the corresponding object privilege to another user per Oracle rules | Grant the corresponding privilege/role to another user or role; administer grants/revokes within permitted scope |
| Commonly used for | Delegation on a specific object | Delegating administration of a system privilege or role |
| Can it be granted to a role/PUBLIC? | Do not use `WITH GRANT OPTION` when the grantee is a role or `PUBLIC` | `ADMIN OPTION` can be granted when the grantee is a user or role per supported syntax |

### 6.1. WITH GRANT OPTION for Object Privileges

Example where an owner grants table read access to a user and allows that user to re-grant it:

```sql
GRANT SELECT
ON app.orders
TO team_lead
WITH GRANT OPTION;
```

`TEAM_LEAD` can pass `SELECT` on that exact object to others:

```sql
GRANT SELECT
ON app.orders
TO analyst_01;
```

The delegation right is bounded by the object privilege `TEAM_LEAD` received. It does not create `INSERT`, `UPDATE`, or privileges on other objects.

`WITH GRANT OPTION` cannot be used when granting object privileges to a role or `PUBLIC`. If multiple users need the same privilege, a clearer approach is usually granting the object privilege to a role and then granting the role to those users.

### 6.2. WITH ADMIN OPTION for System Privileges

Example:

```sql
GRANT CREATE TABLE
TO team_lead
WITH ADMIN OPTION;
```

`TEAM_LEAD` can grant `CREATE TABLE` to another user:

```sql
GRANT CREATE TABLE TO developer_01;
```

`ADMIN OPTION` does not mean the user receives administrative rights over all system privileges. The recipient can only re-grant the privilege granted with this option, unless they hold other administrative privileges.

### 6.3. WITH ADMIN OPTION for Roles

Roles can also be granted with `ADMIN OPTION`:

```sql
GRANT order_report_role
TO team_lead
WITH ADMIN OPTION;
```

`TEAM_LEAD` can grant `ORDER_REPORT_ROLE` to other users or roles. Therefore, role administration rights must be tightly managed: a role containing many privileges can spread more widely than expected if a recipient holds `ADMIN OPTION`.

### 6.4. Do Not Confuse Delegation Options with Usage Privileges

A user with `SELECT ON APP.ORDERS` only has permission to read the object. With `WITH GRANT OPTION`, the user additionally gains the ability to re-grant that read privilege. Likewise, a user with `CREATE TABLE` only has permission to create tables in their own schema; with `WITH ADMIN OPTION`, the user also gains the ability to re-grant that system privilege.

Because delegation expands administrative scope, grant these options only when there is an explicit delegation requirement. Runtime application accounts normally need only usage privileges, never grant options.

## 7. Revoking Privileges and Cascading Effects

Privilege administration is not just about granting. When a user changes roles, leaves, or an application no longer needs an object, privileges must be revoked to the right scope.

### 7.1. Revoking System Privileges

```sql
REVOKE CREATE TABLE
FROM app_developer;
```

If a system privilege was granted to a role, it can be revoked from the role:

```sql
REVOKE CREATE TABLE
FROM schema_developer_role;
```

Revoking a direct privilege from a user does not automatically remove privileges the user still receives through another role. Check all privilege paths before concluding a user has lost access.

Revoking a system privilege granted with `ADMIN OPTION` does not have the same cascading behavior as revoking an object privilege with `GRANT OPTION`. Users who received the system privilege from the grantee with admin option can still retain their own granted privilege. Thus, when revoking administrative privileges, review downstream grants and revoke them separately as policy requires.

### 7.2. Revoking Object Privileges

```sql
REVOKE UPDATE
ON app.orders
FROM order_entry_user;
```

If an object privilege was granted with `WITH GRANT OPTION` and the recipient re-granted it to others, revoking a grant in the chain by the owner can trigger dependent grants to be revoked in cascade (*cascading revoke*).

Example:

```text
APP (owner)
  │ GRANT SELECT WITH GRANT OPTION
  ▼
TEAM_LEAD
  │ GRANT SELECT
  ▼
ANALYST_01
```

If `APP` revokes `SELECT` from `TEAM_LEAD`, the grant that `TEAM_LEAD` issued to `ANALYST_01` is also revoked because it depended on the original grant option. This is an important detail when managing object privilege delegation chains.

### 7.3. Revoking Roles

```sql
REVOKE order_report_role
FROM report_user;
```

After a role is revoked from a user, privileges received solely through that role are no longer effective via that grant path. However, if the user still receives the same privilege directly or through another role, the user can still exercise that privilege.

When auditing after a revoke, distinguish:

- Direct privileges granted to the user.
- Privileges granted via direct roles.
- Privileges inherited via nested roles.
- Privileges granted to `PUBLIC`.
- Privileges arising from broad system privileges.

A successful `REVOKE` command alone does not prove a user has lost all paths to an object.

## 8. Direct Privileges vs. Role Privileges in PL/SQL

This is one of the most important points when troubleshooting privilege errors in packages, procedures, functions, triggers, and views.

In SQL executed directly in a session, enabled roles can supply privileges. However, inside named PL/SQL units running under definer's rights (`AUTHID DEFINER`, the default), session roles are disabled during unit execution. Therefore, code needing object privileges must receive direct grants to the schema owning the unit, or use supported program-unit role mechanisms such as Code Based Access Control.

Example:

```sql
-- DATA_OWNER owns the table.
GRANT SELECT ON data_owner.orders TO app_owner;
```

Then `APP_OWNER`'s package can query the table with definer's rights:

```sql
CREATE OR REPLACE PACKAGE app_owner.order_query_api
AUTHID DEFINER
AS
    PROCEDURE show_orders;
END order_query_api;
/

CREATE OR REPLACE PACKAGE BODY app_owner.order_query_api
AS
    PROCEDURE show_orders
    IS
        l_count NUMBER;
    BEGIN
        SELECT COUNT(*)
        INTO l_count
        FROM data_owner.orders;
    END show_orders;
END order_query_api;
/
```

If `SELECT ON DATA_OWNER.ORDERS` is only granted to a role held by `APP_OWNER`, static SQL inside a definer-rights unit cannot rely on that session role. Grant it directly to `APP_OWNER` if the package requires this access.

### 8.1. Invoker-Rights Units

With `AUTHID CURRENT_USER`, privileges are checked against the invoker's context. The invoker's enabled roles can participate in privilege checks when the unit executes. This is useful when a package is designed to operate using each caller's individual privileges.

```sql
CREATE OR REPLACE PACKAGE app_owner.report_api
AUTHID CURRENT_USER
AS
    PROCEDURE show_report;
END report_api;
/
```

When caller `REPORT_USER` invokes the package, the objects accessed by the package require appropriate privileges for the invoker per Oracle rules. Do not assume granting `EXECUTE` alone is sufficient for every invoker-rights unit.

`CURRENT_USER` and `CURRENT_SCHEMA` are two distinct concepts. `CURRENT_USER` governs the privilege-checking context; `CURRENT_SCHEMA` affects name resolution for unqualified objects. Changing `CURRENT_SCHEMA` does not grant privileges.

### 8.2. Code Based Access Control (CBAC)

Oracle supports granting roles to a program unit in versions with Code Based Access Control. The role is enabled within the execution scope of the unit, allowing a specific privilege set to be attached to a package/procedure rather than granting all those privileges to the schema owner.

Illustrative example:

```sql
GRANT order_data_reader TO PACKAGE app_owner.order_query_api;
```

CBAC must be configured and tested for your specific Oracle version. Do not use CBAC to obscure an unclear privilege matrix. Identify precisely which privileges the package needs and ensure the role holds only those minimal privileges.

### 8.3. Privileges When Creating Views and Compiling Stored Code

When creating a view based on objects in another schema, the view owner needs the required object privileges granted directly per Oracle rules; privileges received only via roles are insufficient for certain view privilege validations.

Similarly, when compiling stored PL/SQL with static SQL referencing cross-schema objects, the owner needs appropriate direct privileges. On compile errors like `PLS-00201` or `ORA-00942`, do not rush to grant `SELECT ANY TABLE`; verify object existence, schema qualification, and direct grants.

## 9. Distinguishing Object Privileges from Object Creation Privileges

A common design mistake is granting broad system privileges when an application only needs operations on a specific object.

For example, the application only needs to read `APP.ORDERS`:

```sql
-- Narrow scope.
GRANT SELECT ON app.orders TO app_runtime;
```

Do not replace this with:

```sql
-- Broad scope across many objects.
GRANT SELECT ANY TABLE TO app_runtime;
```

Similarly, if a user needs to update a specific table, grant `UPDATE ON schema.table` or appropriate column-level privileges. Do not grant system privileges like `UPDATE ANY TABLE` just to handle one table.

A system privilege like `CREATE TABLE` is also not equivalent to an object privilege on an existing table. `CREATE TABLE` allows creating objects in the user's schema; `SELECT ON APP.ORDERS` allows reading the designated object. The two privileges solve different goals.

## 10. Querying Granted Privileges and Effective Privileges

Oracle provides data dictionary views to inspect grants. Choose the view matching your scope: current user privileges, object privileges, role privileges, or database-wide privileges.

### 10.1. Checking System Privileges

Commonly used views:

| View | Scope |
|---|---|
| `USER_SYS_PRIVS` | System privileges granted directly to the current user |
| `ROLE_SYS_PRIVS` | System privileges granted to roles visible to the user |
| `DBA_SYS_PRIVS` | System privileges granted in the database; requires DBA view access |
| `SESSION_PRIVS` | System privileges currently active in the session |

Example:

```sql
SELECT privilege,
       admin_option
FROM user_sys_privs
ORDER BY privilege;
```

Viewing system privileges granted across the database:

```sql
SELECT grantee,
       privilege,
       admin_option
FROM dba_sys_privs
WHERE grantee IN ('APP_RUNTIME', 'SCHEMA_DEVELOPER_ROLE')
ORDER BY grantee, privilege;
```

### 10.2. Checking Object Privileges

| View | Scope |
|---|---|
| `USER_TAB_PRIVS_MADE` | Object privileges granted by the current user to others |
| `USER_TAB_PRIVS_RECD` | Object privileges received by the current user |
| `USER_TAB_PRIVS` | Object privileges related to objects in the current user's scope per view definition |
| `USER_COL_PRIVS` | Column-level object privileges in the current user's scope |
| `ALL_TAB_PRIVS` | Object privileges on objects whose metadata the user can access |
| `DBA_TAB_PRIVS` | Object privileges granted in the database |
| `DBA_COL_PRIVS` | Column-level object privileges granted in the database |

Example viewing privileges on a table:

```sql
SELECT grantee,
       owner,
       table_name,
       privilege,
       grantable
FROM all_tab_privs
WHERE owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY grantee, privilege;
```

`GRANTABLE = 'YES'` indicates the object privilege was granted with the grant option. This differs from `ADMIN_OPTION` on system privileges or roles.

### 10.3. Checking Granted Roles

| View | Scope |
|---|---|
| `USER_ROLE_PRIVS` | Roles granted to the current user |
| `ROLE_ROLE_PRIVS` | Roles granted to roles |
| `DBA_ROLE_PRIVS` | Roles granted to users and roles in the database |
| `SESSION_ROLES` | Roles currently enabled in the session |

Example:

```sql
SELECT granted_role,
       admin_option,
       default_role
FROM user_role_privs
ORDER BY granted_role;
```

Checking enabled roles:

```sql
SELECT role
FROM session_roles
ORDER BY role;
```

### 10.4. Viewing Privileges Inside a Role

To understand what privileges a role carries, check both system privileges and object privileges of the role:

```sql
SELECT role,
       privilege,
       admin_option
FROM role_sys_privs
ORDER BY role, privilege;
```

```sql
SELECT role,
       owner,
       table_name,
       privilege
FROM role_tab_privs
ORDER BY role, owner, table_name, privilege;
```

If roles are nested across multiple levels, trace roles granted to other roles. A user may hold privileges through multiple paths; checking only `USER_SYS_PRIVS` or `USER_TAB_PRIVS_RECD` may not explain all effective privileges.

### 10.5. Querying Administrative and Delegation Privileges

Key columns generally include:

- `ADMIN_OPTION` in `DBA_SYS_PRIVS` or `DBA_ROLE_PRIVS` indicates whether the recipient can re-grant the system privilege/role.
- `GRANTABLE` in `DBA_TAB_PRIVS` indicates whether the object privilege was granted with the grant option.
- `DEFAULT_ROLE` in `DBA_ROLE_PRIVS` indicates whether the role is enabled by default on login.

When auditing a user, cross-check direct grants, granted roles, enabled roles, `PUBLIC` privileges, and broad system privileges. Never inspect a single view and conclude a user does or does not have access.

## 11. Designing a Role-Based Privilege Matrix

A system should maintain a privilege matrix showing which user/role is allowed to perform which operations on which objects.

Example:

| Role | ORDERS | CUSTOMERS | ORDER_API |
|---|---|---|---|
| `ORDER_ENTRY_ROLE` | `SELECT`, `INSERT`, `UPDATE(status)` | `SELECT` | `EXECUTE` |
| `ORDER_REPORT_ROLE` | `SELECT` | `SELECT` | Not needed |
| `ORDER_SUPPORT_ROLE` | `SELECT`, `UPDATE(status)` | `SELECT` | `EXECUTE` |

Runtime accounts should receive only the roles needed for their business flows. Avoid using a single shared role containing read, write, DDL, and database admin privileges for all accounts.

Helpful principles:

1. Separate the object-owning user from the application runtime user.
2. Grant `CREATE SESSION` and required connectivity privileges.
3. Grant object privileges per specific object or API.
4. Use functional roles to group privileges with a shared purpose.
5. Do not grant `ANY` privileges when narrow object privileges suffice.
6. Grant `ADMIN OPTION` or `GRANT OPTION` only when the recipient needs to delegate privileges.
7. Avoid granting to `PUBLIC` without clear business and security justification.
8. Review default roles and enabled roles in connection pools.
9. Document the owner, rationale, and expiration of special privileges.
10. Test using the actual application user and roles, not just a DBA account.

## 12. End-to-End Implementation Example

Suppose there is a data schema `DATA_OWNER`, a package schema `APP_OWNER`, and an application connection user `APP_RUNTIME`.

### 12.1. Granting Privileges to the Package Owner

`APP_OWNER` needs direct privileges on tables operated on by its packages:

```sql
GRANT SELECT, INSERT, UPDATE
ON data_owner.orders
TO app_owner;
```

### 12.2. Granting Package Execution to the Runtime Role

```sql
CREATE ROLE order_api_executor;

GRANT EXECUTE
ON app_owner.order_api
TO order_api_executor;

GRANT order_api_executor
TO app_runtime;
```

### 12.3. Granting Connection Privilege

```sql
GRANT CREATE SESSION TO app_runtime;
```

In this model, `APP_RUNTIME` can call the package through `ORDER_API_EXECUTOR`. `APP_OWNER` holds direct privileges on `DATA_OWNER.ORDERS`. If the package uses definer's rights, the code runs with `APP_OWNER`'s privileges under the API contract.

### 12.4. Verifying from the Runtime Account

Log in as `APP_RUNTIME` and check active roles:

```sql
SELECT role
FROM session_roles;
```

Call the API:

```sql
BEGIN
    app_owner.order_api.create_order(
        p_customer_id => 1001,
        p_product_id  => 501,
        p_quantity    => 2
    );
END;
/
```

Then attempt to query `DATA_OWNER.ORDERS` directly. If the design did not grant `SELECT` to runtime, the direct query must be rejected. This confirms the API boundary works as intended.

## 13. Common Privilege Errors

| Symptom | Possible cause | Investigation approach |
|---|---|---|
| `ORA-01031: insufficient privileges` | Missing system/object privilege or role is not enabled in the current context | Identify executing user, `AUTHID`, roles, and direct grants |
| `ORA-00942: table or view does not exist` | Wrong schema/object name or missing privilege to see the object | Check object and direct grants; do not rush to grant `SELECT ANY TABLE` |
| `PLS-00201: identifier must be declared` | Object/package not visible at compile time or missing required privilege | Check owner, synonyms, direct grants, and compile errors |
| User can run SQL directly, but package fails | Package runs with definer's rights so session roles are disabled | Grant privileges directly to owner or use CBAC in a controlled way |
| User still has access after revoke | Privilege remains via another role, direct grant, `PUBLIC`, or broad system privilege | Trace all privilege paths |
| User has the role but cannot use privileges | Role is not default or is disabled in the session | Check `SESSION_ROLES`, `SET ROLE`, and connection pool |
| Cannot re-grant an object privilege | Grantor is not owner, lacks grant option, or lacks appropriate admin privilege | Check `GRANTABLE`, grantor, and administrative privileges |

Do not fix privilege errors by granting sweeping system privileges. Identify the exact failing operation, involved object, executing user, PL/SQL context, and privilege path.

## 14. Periodic Privilege Review Process

A privilege review process can follow these steps:

1. **List users and accounts:** identify application users, owners, operations users, and admin users.
2. **List system privileges:** look for `ANY`, DDL, and sensitive administrative privileges.
3. **List object privileges:** identify which objects are shared and with which grantees.
4. **Inspect roles:** check direct roles, nested roles, default roles, and active roles.
5. **Inspect delegation rights:** find `ADMIN_OPTION = 'YES'` and `GRANTABLE = 'YES'`.
6. **Inspect PUBLIC:** review privileges/roles granted to `PUBLIC`.
7. **Cross-check with functionality:** confirm each privilege still serves an existing business need.
8. **Revoke excess privileges:** execute under change control and verify applications after revoking.
9. **Test execution contexts:** test using the runtime user and exact roles, especially for stored PL/SQL.
10. **Retain evidence:** record grantor, justification, timestamp, scope, and approver for special privileges.

## 15. Misconceptions to Avoid

| Misconception | Reality |
|---|---|
| `CREATE TABLE` lets you create tables in any schema | Only creates in the user's own schema; `CREATE ANY TABLE` has broader scope |
| `SELECT ON APP.ORDERS` lets you read all APP tables | Applies only to the designated object |
| A synonym automatically grants access | A synonym only aliases the reference; privileges are still needed separately |
| A role is a system privilege | A role is a container holding privileges and other roles |
| A granted role is always enabled | A role may not be default or may be disabled in the session |
| `WITH GRANT OPTION` and `WITH ADMIN OPTION` are the same | Grant option is for object privileges; admin option is for system privileges and roles |
| Having `EXECUTE` on a package means you can read its internal tables | Internal access depends on `AUTHID` and owner/invoker privileges |
| If a DBA can run it, the runtime user can too | DBAs may have far broader privileges than the app; test with the actual runtime account |
| Revoking one role removes all privileges | Privileges may remain via direct grants, other roles, PUBLIC, or system privileges |
| Granting `ANY` privileges is the fastest fix | `ANY` vastly expands scope; grant narrow object privileges whenever possible |

System privileges, object privileges, and roles address different privilege scopes. `WITH ADMIN OPTION` and `WITH GRANT OPTION` add delegation capability, so they must be treated as administrative privileges carrying higher risk than standard usage rights. Designing for least privilege, separating privileges by function, tracing all grant paths, and testing in the exact session/PL/SQL context makes systems easier to administer and prevents over-privileged access.
