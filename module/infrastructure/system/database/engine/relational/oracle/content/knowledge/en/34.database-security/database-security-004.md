# GRANT, REVOKE, WITH ADMIN OPTION, and WITH GRANT OPTION in Oracle

## 1. Managing Access Control in Oracle Database

Oracle Database uses privileges and roles to control who can connect, create objects, read data, modify data, or execute programs in the database.

Three concepts to distinguish:

- **System privilege:** permission to perform a category of operations in the database, such as CREATE SESSION, CREATE TABLE, or CREATE PROCEDURE.
- **Object privilege:** permission to perform an operation on a specific object, such as SELECT on HR.EMPLOYEES or EXECUTE on a package.
- **Role:** a named group of privileges and other roles bundled together to be granted to users or other roles.

Two delegation options have similar names but apply to two different privilege categories:

- **WITH ADMIN OPTION:** used when granting a system privilege or role. The grantee is allowed to administer and further grant that privilege/role to other users or roles.
- **WITH GRANT OPTION:** used when granting an object privilege. The grantee is allowed to further grant that object privilege to other users or roles.

Do not treat these two options as identical. Choosing the wrong option can create broader administrative powers than intended or cause an invalid GRANT statement.

~~~text
                    ORACLE DATABASE
                           |
              +------------+------------+
              |            |            |
              v            v            v
        SYSTEM PRIVILEGE  OBJECT PRIVILEGE   ROLE
              |            |                 |
              |            |                 |
       WITH ADMIN OPTION   WITH GRANT OPTION  WITH ADMIN OPTION
              |            |                 |
              v            v                 v
       Delegate/manage    Delegate object    Delegate/manage
       system privilege   privilege on the   role to user/role
       or role            object
~~~

> This lesson uses Oracle Database 19c. Actual effective privileges also depend on the schema owner, whether privileges are granted directly or through roles, role status in the session, administrative privileges, and multitenant configuration. Run examples in a lab schema with appropriate privileges.

## 2. System Privileges, Object Privileges, and Roles

### 2.1. System Privileges

A system privilege permits a user to perform an action or group of actions at the database or schema level.

Examples:

| System privilege | General meaning |
| --- | --- |
| CREATE SESSION | Connect to the database |
| CREATE TABLE | Create tables in the user's schema |
| CREATE VIEW | Create views in the user's schema |
| CREATE PROCEDURE | Create procedures, functions, and packages in the user's schema |
| CREATE SEQUENCE | Create sequences in the user's schema |
| CREATE ANY TABLE | Create tables in other schemas within privilege scope |
| SELECT ANY TABLE | Query most tables/views across schemas per Oracle rules |
| GRANT ANY PRIVILEGE | Grant or revoke system privileges on behalf of the administrative mechanism |
| GRANT ANY ROLE | Grant or revoke roles within privilege scope |
| GRANT ANY OBJECT PRIVILEGE | Grant or revoke object privileges within privilege scope |

System privileges can have a very broad scope. In particular, privileges containing ANY such as SELECT ANY TABLE, UPDATE ANY TABLE, or CREATE ANY PROCEDURE must be granted very cautiously. They are not equivalent to privileges on a single specific table.

Some ANY system privileges do not apply to objects owned by SYS or dictionary objects protected by separate privileges. Do not assume ANY automatically means every object without exception.

### 2.2. Object Privileges

An object privilege allows performing operations on a specific object.

Examples:

~~~sql
GRANT SELECT ON hr.employees TO analyst;
GRANT INSERT, UPDATE ON hr.orders TO order_app;
GRANT EXECUTE ON hr.order_api TO order_app;
~~~

Common object privileges:

| Object privilege | Object/operation |
| --- | --- |
| SELECT | Read data from a table, view, or materialized view |
| READ | Read data without certain row-locking capabilities such as SELECT FOR UPDATE |
| INSERT | Insert rows |
| UPDATE | Update rows; can be restricted by column |
| DELETE | Delete rows |
| REFERENCES | Reference columns via a foreign key |
| EXECUTE | Execute a procedure, function, or package |
| ALTER | Alter object structure within supported scope |
| INDEX | Create an index on another schema's table |

The valid privilege list depends on the object type. Not every object supports all of SELECT, INSERT, UPDATE, or DELETE.

### 2.3. Roles

A role is a group of privileges and can contain other roles. Instead of granting many individual object privileges to each user, a DBA can grant privileges to a role and then grant the role to users.

Example:

~~~sql
CREATE ROLE reporting_role;

GRANT CREATE SESSION TO reporting_role;
GRANT SELECT ON hr.employees TO reporting_role;
GRANT SELECT ON hr.departments TO reporting_role;

GRANT reporting_role TO analyst;
~~~

When the role is enabled in a session, the user can exercise the privileges contained in the role. Roles help manage privileges by function, such as REPORTING_ROLE, ORDER_READ_ROLE, or ORDER_WRITE_ROLE.

A role can also be granted to another role. Oracle does not allow granting a role to itself or creating circular role grant chains.

### 2.4. Direct Privileges vs. Role-Based Privileges

Privileges can be granted directly to a user or through a role:

~~~sql
-- Direct object privilege
GRANT SELECT ON hr.employees TO analyst;

-- Object privilege granted to a role
GRANT SELECT ON hr.employees TO reporting_role;
GRANT reporting_role TO analyst;
~~~

Both approaches can allow querying the same object in a session, yet they are not equivalent in all contexts. Compiling certain definer-rights stored PL/SQL requires privileges granted directly to the owner, not merely through a role.

## 3. The GRANT Statement

GRANT is used to:

1. Grant system privileges to a user or role.
2. Grant roles to a user, role, or program unit using supported Oracle syntax.
3. Grant object privileges on a specific object to a user or role.

### 3.1. Granting System Privileges

Basic syntax:

~~~sql
GRANT system_privilege [, system_privilege ...]
TO user_or_role [, user_or_role ...];
~~~

Example:

~~~sql
GRANT CREATE SESSION TO app_user;
GRANT CREATE TABLE, CREATE SEQUENCE TO app_owner;
GRANT CREATE VIEW TO reporting_owner;
~~~

A user receiving a system privilege can perform the corresponding action once the privilege takes effect.

### 3.2. Granting Object Privileges

Basic syntax:

~~~sql
GRANT object_privilege [, object_privilege ...]
ON schema.object
TO user_or_role [, user_or_role ...];
~~~

Example:

~~~sql
GRANT SELECT ON hr.employees TO analyst;
GRANT SELECT, INSERT ON hr.orders TO order_app;
GRANT EXECUTE ON hr.order_api TO order_app;
~~~

An object privilege is always tied to a specific object. SELECT on HR.EMPLOYEES does not automatically allow SELECT on HR.DEPARTMENTS.

### 3.3. Granting Column-Level Privileges

Oracle allows restricting certain object privileges by column, specifically UPDATE, INSERT, and REFERENCES:

~~~sql
GRANT UPDATE (salary)
ON hr.employees
TO payroll_operator;
~~~

The payroll operator can only UPDATE the SALARY column under this grant. The privilege does not expand to other columns.

Example granting INSERT on a subset of columns:

~~~sql
GRANT INSERT (employee_id, first_name, last_name)
ON hr.employees
TO hr_importer;
~~~

Column restriction reduces the scope of data that can be modified.

### 3.4. Granting READ or SELECT

Oracle 19c provides both READ and SELECT object privileges for tables/views:

~~~sql
GRANT READ ON hr.employees TO report_viewer;
GRANT SELECT ON hr.employees TO report_operator;
~~~

Both allow querying data via SELECT. SELECT also permits operations such as SELECT ... FOR UPDATE or LOCK TABLE within supported scope; READ does not grant those locking capabilities.

If a user only needs to read data, READ can be a narrower choice. Check whether the application uses SELECT FOR UPDATE before replacing SELECT with READ.

### 3.5. Granting Privileges on a View

Example:

~~~sql
GRANT SELECT ON hr.employee_directory_v TO reporting_role;
~~~

If a view references objects in another schema, the view owner needs appropriate privileges on the underlying objects. To grant SELECT on the view to another user, Oracle requires the view owner to own the underlying objects or hold SELECT WITH GRANT OPTION on all relevant underlying objects. The fact that the recipient already has direct privileges on the underlying tables does not replace the view owner's grant requirement.

This is a common cause of error ORA-01720 when granting privileges on a view.

### 3.6. Granting Roles

Syntax:

~~~sql
GRANT role_name TO user_or_role;
~~~

Example:

~~~sql
CREATE ROLE app_read_role;
GRANT SELECT ON hr.products TO app_read_role;
GRANT SELECT ON hr.categories TO app_read_role;

GRANT app_read_role TO app_user;
~~~

A user holding the role can enable it and use the privileges contained in the role.

### 3.7. Who Is Allowed to GRANT?

Requirements depend on the privilege category:

| Privilege type granted | Who can grant it? |
| --- | --- |
| System privilege | A user holding that system privilege WITH ADMIN OPTION or holding GRANT ANY PRIVILEGE |
| Role | The role creator, a user directly granted the role WITH ADMIN OPTION, or a user holding GRANT ANY ROLE |
| Object privilege | The object owner, a user who received the object privilege WITH GRANT OPTION, or a user holding GRANT ANY OBJECT PRIVILEGE per Oracle constraints |

GRANT ANY PRIVILEGE, GRANT ANY ROLE, and GRANT ANY OBJECT PRIVILEGE are high-power administrative system privileges. Do not grant them merely for operational convenience.

## 4. WITH ADMIN OPTION

### 4.1. Meaning

WITH ADMIN OPTION applies to system privileges and roles. It grants the grantee administrative authority over that privilege/role, including the ability to grant or revoke that privilege/role to/from other users or roles.

Example granting a system privilege:

~~~sql
GRANT CREATE TABLE
TO schema_manager
WITH ADMIN OPTION;
~~~

Schema manager has CREATE TABLE and can grant CREATE TABLE to other users or roles.

Example granting a role:

~~~sql
GRANT reporting_role
TO reporting_manager
WITH ADMIN OPTION;
~~~

Reporting manager can grant or revoke REPORTING_ROLE for other users/roles within delegated authority.

### 4.2. ADMIN OPTION Is Not for Object Privileges

Do not use WITH ADMIN OPTION for SELECT ON table:

~~~sql
-- Invalid: SELECT ON table is an object privilege
GRANT SELECT ON hr.employees
TO analyst
WITH ADMIN OPTION;
~~~

For object privileges, the proper option is WITH GRANT OPTION.

### 4.3. WITH ADMIN OPTION for System Privileges

~~~sql
GRANT CREATE SESSION
TO user_admin
WITH ADMIN OPTION;
~~~

User admin can grant CREATE SESSION to other users/roles and revoke that privilege from other grantees.

This does not mean user admin can grant every system privilege. ADMIN OPTION is tied to the specific privilege. To grant another system privilege, the user must hold ADMIN OPTION on that privilege or hold GRANT ANY PRIVILEGE.

### 4.4. WITH ADMIN OPTION for Roles

~~~sql
GRANT app_read_role
TO team_lead
WITH ADMIN OPTION;
~~~

Team lead can grant the role to other users or roles and revoke that role with administrative authority. This delegates role administration per team instead of granting GRANT ANY ROLE broadly.

### 4.5. ADMIN OPTION Grants Broader Administration Beyond Re-Granting

Oracle documents that ADMIN OPTION for a system privilege/role permits the grantee to:

- Grant the privilege or role to other users/roles, except restrictions on global roles.
- Revoke the privilege or role from other users/roles.
- Alter or drop the privilege/role within Oracle's permitted scope.
- For roles, grant/revoke the role to/from program units in the grantee's schema per supported rules.

Therefore, ADMIN OPTION is administrative delegation, not just an informational flag.

### 4.6. System Privileges Granted to Roles and ADMIN OPTION

Oracle 19c has a nuance to note when granting system privileges to a role:

- If the grantor holds the system privilege with ADMIN OPTION, a user granted a role containing that privilege may possess the privilege even when the role is not yet enabled.
- If the grantor granted the system privilege using GRANT ANY PRIVILEGE, the user must enable the role to use the privilege via the role.

This is a difference in privilege domains and how Oracle evaluates the grant source. When designing role-based privileges, verify how privileges were granted into the role and the session's role status.

### 4.7. You Cannot Revoke ADMIN OPTION Alone

Oracle does not support a single operation that keeps a privilege/role while stripping only ADMIN OPTION. You must revoke the entire privilege/role from the user, then grant it again without ADMIN OPTION:

~~~sql
REVOKE CREATE TABLE FROM schema_manager;

GRANT CREATE TABLE TO schema_manager;
~~~

After this step, schema_manager still has CREATE TABLE but no longer has ADMIN OPTION from that grant.

For a role:

~~~sql
REVOKE reporting_role FROM reporting_manager;
GRANT reporting_role TO reporting_manager;
~~~

Check for other independent grants the user may receive through another role or direct grant. REVOKING one grant does not automatically eliminate all other privilege paths.

## 5. WITH GRANT OPTION

### 5.1. Meaning

WITH GRANT OPTION applies to object privileges. It allows the recipient to further grant that object privilege to other users or roles.

Example:

~~~sql
GRANT SELECT ON hr.employees
TO data_steward
WITH GRANT OPTION;
~~~

Data steward has SELECT on HR.EMPLOYEES and can further grant SELECT on that object.

### 5.2. Delegation Scope Is Tied to the Specific Object

If data steward is granted SELECT WITH GRANT OPTION on HR.EMPLOYEES, that does not allow granting SELECT on HR.DEPARTMENTS or UPDATE on HR.EMPLOYEES.

To delegate other privileges, they must hold the corresponding privilege and grant option, or hold a broader administrative system privilege.

### 5.3. Grantee Granting Further to a User or Role

Example grant chain:

~~~sql
-- HR is the owner
GRANT SELECT ON hr.employees
TO data_steward
WITH GRANT OPTION;

-- Data steward grants further
GRANT SELECT ON hr.employees
TO report_reader;

-- Data steward can also grant to a role
GRANT SELECT ON hr.employees
TO report_role;
~~~

REPORT_READER and REPORT_ROLE receive SELECT. They do not automatically receive GRANT OPTION unless their corresponding grant specifies WITH GRANT OPTION and meets Oracle restrictions.

### 5.4. WITH GRANT OPTION Is Not Used for System Privileges

Do not write:

~~~sql
-- Invalid for system privileges
GRANT CREATE TABLE TO schema_manager
WITH GRANT OPTION;
~~~

System privileges use WITH ADMIN OPTION.

### 5.5. Do Not Grant WITH GRANT OPTION to a Role

Oracle 19c does not allow specifying WITH GRANT OPTION when an object privilege is granted to a role:

~~~sql
-- Invalid: grantee is a role
GRANT SELECT ON hr.employees
TO reporting_role
WITH GRANT OPTION;
~~~

If an individual needs permission to delegate an object privilege, grant the object privilege directly to that user with WITH GRANT OPTION. Grant the standard privilege to a role for other members to use.

Oracle SQL Language Reference 19c states that the grantee of WITH GRANT OPTION can be a user or PUBLIC, not a role. Granting to PUBLIC propagates privileges to all users, so avoid using it as a standard application authorization pattern.

### 5.6. You Cannot Revoke GRANT OPTION Alone

Oracle does not allow revoking the option alone while keeping the object privilege. You must revoke the privilege and then re-grant it without WITH GRANT OPTION:

~~~sql
REVOKE SELECT ON hr.employees FROM data_steward;

GRANT SELECT ON hr.employees TO data_steward;
~~~

Note: revoking an object privilege from a grantor can cause downstream grants issued via WITH GRANT OPTION to be revoked in cascade. Inspect the grant chain before executing.

## 6. Comparing WITH ADMIN OPTION and WITH GRANT OPTION

| Criterion | WITH ADMIN OPTION | WITH GRANT OPTION |
| --- | --- | --- |
| Applies to | System privileges and roles | Object privileges |
| Scope | A category of operation/role in the database | A privilege on a specific object |
| Allows delegating | System privilege or role | Object privilege |
| Allows revoking downstream | Yes, for the delegated privilege/role | Grantee can delegate; revocation follows grantor/owner and Oracle rules |
| Can be granted to a role? | Roles can receive system privileges/roles with ADMIN OPTION per supported syntax | Object privileges cannot be granted WITH GRANT OPTION to a role |
| Revoke option alone? | No; revoke privilege/role then re-grant without option | No; revoke object privilege then re-grant without option |
| Revocation effect | No grant-chain cascade like object grant option; privileges dependent on role/system privilege may affect objects/code using it | Revoking a grantor's object privilege can cascade grants passed via GRANT OPTION |

A mnemonic:

- ADMIN = administrative right to grant/revoke a system privilege or role.
- GRANT = right to delegate a specific object privilege.

Do not guess the option from similar names. Identify the privilege category first.

## 7. REVOKE: Revoking Privileges

### 7.1. Revoking System Privileges

Syntax:

~~~sql
REVOKE system_privilege
FROM user_or_role;
~~~

Example:

~~~sql
REVOKE CREATE TABLE FROM app_user;
REVOKE CREATE SESSION FROM temporary_user;
~~~

To revoke a system privilege, the executor needs ADMIN OPTION on that privilege or GRANT ANY PRIVILEGE.

### 7.2. Revoking Object Privileges

Syntax:

~~~sql
REVOKE object_privilege
ON schema.object
FROM user_or_role;
~~~

Example:

~~~sql
REVOKE SELECT ON hr.employees FROM analyst;
REVOKE INSERT, UPDATE ON hr.orders FROM order_app;
REVOKE EXECUTE ON hr.order_api FROM old_app_role;
~~~

Normally the object owner can revoke grants they issued. A user with GRANT ANY OBJECT PRIVILEGE can also revoke within Oracle's defined scope.

### 7.3. Revoking Roles

~~~sql
REVOKE reporting_role FROM analyst;
~~~

The user no longer receives privileges through that role. If the user holds the same privilege via a direct grant or another role, effective privileges may remain.

To revoke a role, the executor must have been directly granted the role with ADMIN OPTION, have created the role, or hold GRANT ANY ROLE within supported scope.

### 7.4. Revoking Multiple Privileges

~~~sql
REVOKE SELECT, INSERT
ON hr.orders
FROM order_reader, order_importer;
~~~

ALL can be used to revoke all object privileges granted on the object:

~~~sql
REVOKE ALL ON hr.orders FROM legacy_role;
~~~

ALL is shorthand for granted privileges; it is not an independent privilege.

### 7.5. Revoking REFERENCES and CASCADE CONSTRAINTS

If the grantee used the REFERENCES privilege to create an existing foreign key constraint, Oracle requires CASCADE CONSTRAINTS when revoking:

~~~sql
REVOKE REFERENCES ON hr.departments
FROM app_schema
CASCADE CONSTRAINTS;
~~~

CASCADE CONSTRAINTS drops foreign key constraints depending on the REFERENCES grant. This is a structural data change, not just a privilege change. Evaluate affected constraints before running.

## 8. Cascading Behavior When Revoking Privileges

This is a major difference between object privilege grant options and system privilege/role admin options.

### 8.1. Object Privileges with a Grant Chain

Suppose:

1. HR is the owner of HR.EMPLOYEES.
2. HR grants SELECT WITH GRANT OPTION to DATA_STEWARD.
3. DATA_STEWARD grants SELECT to REPORT_READER.
4. REPORT_READER can use the privilege under that grant.

~~~text
HR (object owner)
  |
  | SELECT WITH GRANT OPTION
  v
DATA_STEWARD
  |
  | SELECT
  v
REPORT_READER
~~~

If HR revokes SELECT from DATA_STEWARD:

~~~sql
REVOKE SELECT ON hr.employees
FROM data_steward;
~~~

Oracle cascades the revoke of SELECT on HR.EMPLOYEES from REPORT_READER if REPORT_READER's grant was passed through DATA_STEWARD. Downstream grants depending on that grant chain are revoked.

### 8.2. Independent Grants Can Still Persist

If HR also granted SELECT directly to REPORT_READER:

~~~sql
GRANT SELECT ON hr.employees TO report_reader;
~~~

When the grant from DATA_STEWARD is cascade-revoked, the independent direct grant from HR remains. Oracle tracks grants by grantor/grantee, so do not assume revoking one path removes all other grant paths.

### 8.3. Revoking System Privileges Differs from Object Grant Cascades

Oracle does not apply the same grant-chain cascade mechanism of WITH GRANT OPTION to system privileges granted with ADMIN OPTION.

Example with a DDL system privilege:

~~~sql
GRANT CREATE TABLE TO schema_manager WITH ADMIN OPTION;
GRANT CREATE TABLE TO app_owner;

REVOKE CREATE TABLE FROM schema_manager;
~~~

Revoking CREATE TABLE from SCHEMA_MANAGER does not automatically cascade-revoke CREATE TABLE previously granted by SCHEMA_MANAGER to APP_OWNER. Already-created objects are not automatically dropped either.

However, revoking a DML system privilege can cause stored procedures/functions/packages depending on that privilege to fail execution. Distinguish grant-chain revocation from impact on objects/code using the privilege.

### 8.4. Revoking Roles

Revoking a role from a user removes privileges received from that role. If the role contains other roles or multiple object/system privileges, all privileges originating from that role leave the user's privilege domain once the role is revoked/disabled.

A role's ADMIN OPTION cannot be revoked individually. To remove ADMIN OPTION, revoke the role from the user and re-grant the role without the option.

### 8.5. Revoking Object Privileges Can Impact Stored Objects

If a definer-rights procedure or package depends on an object privilege revoked from the stored object's owner, the procedure/package may fail to execute. Dependent views can also become invalidated.

Therefore, revoking does not affect only directly logged-in users. It can impact applications and stored code.

## 9. Column Privileges and REVOKE Limitations

Oracle allows granting certain privileges at the column level:

~~~sql
GRANT UPDATE (salary, commission_pct)
ON hr.employees
TO payroll_operator;
~~~

However, REVOKE cannot be used to revoke a single column privilege in the corresponding manner. For example, there is no standard syntax to revoke UPDATE only on SALARY while keeping UPDATE on COMMISSION_PCT from the same grant.

To change the column scope:

~~~sql
REVOKE UPDATE ON hr.employees
FROM payroll_operator;

GRANT UPDATE (commission_pct)
ON hr.employees
TO payroll_operator;
~~~

The first statement revokes object-level UPDATE from the grantee; the second re-grants only the column to retain.

## 10. Direct Privileges, Roles, and Stored PL/SQL

### 10.1. Roles Are Convenient for Sessions but Do Not Replace All Direct Grants

A user can query a table via an enabled role:

~~~sql
GRANT SELECT ON hr.employees TO reporting_role;
GRANT reporting_role TO analyst;
~~~

In a session, ANALYST can enable REPORTING_ROLE to query.

### 10.2. Definer-Rights PL/SQL

Stored procedures/functions/packages default to definer-rights unless AUTHID CURRENT_USER is declared. When compiling and executing definer-rights program units, the owner's regular roles are disabled.

If a procedure in schema APP_OWNER needs SELECT on HR.EMPLOYEES, grant it directly:

~~~sql
GRANT SELECT ON hr.employees TO app_owner;
~~~

Do not only grant SELECT to a role and grant that role to APP_OWNER if the privilege is needed to compile definer-rights stored code.

Similarly, system privileges needed to create stored program units must be granted directly to the owner per Oracle rules, rather than relying on regular roles.

### 10.3. Invoker-Rights and Code-Based Access Control

A program unit declared with AUTHID CURRENT_USER runs with the invoker's privileges under the invoker-rights model. Oracle also supports granting roles to program units (code-based access control), allowing roles to be enabled when the program unit runs per the corresponding rules.

Example syntax granting a role to a procedure:

~~~sql
GRANT app_read_role
TO PROCEDURE app_owner.read_dashboard;
~~~

This is a separate mechanism. Do not confuse granting a role to a program unit with granting a role to a user.

### 10.4. What Is WITH DELEGATE OPTION?

Oracle 19c also has WITH DELEGATE OPTION when granting a role directly to a user. This option lets the user grant/revoke that role to/from program units in their own schema, without conferring full rights to grant/revoke the role to other users or roles like ADMIN OPTION.

Example:

~~~sql
GRANT app_read_role
TO app_owner
WITH DELEGATE OPTION;
~~~

WITH DELEGATE OPTION is not the main focus of this lesson, but should be distinguished from ADMIN OPTION. Both involve roles, yet have different delegation scopes.

## 11. GRANT ANY PRIVILEGE, GRANT ANY ROLE, and GRANT ANY OBJECT PRIVILEGE

These are system privileges for administering grants and revokes:

| System privilege | Scope |
| --- | --- |
| GRANT ANY PRIVILEGE | Grant or revoke system privileges per Oracle scope |
| GRANT ANY ROLE | Grant or revoke roles per Oracle scope |
| GRANT ANY OBJECT PRIVILEGE | Grant or revoke object privileges per Oracle scope |

They have a very broad scope and must be protected.

### 11.1. GRANT ANY PRIVILEGE

A user with GRANT ANY PRIVILEGE can grant system privileges to users/roles without holding ADMIN OPTION on each individual privilege.

### 11.2. GRANT ANY ROLE

A user with GRANT ANY ROLE can grant or revoke roles for other users/roles, except for restrictions on global roles.

### 11.3. GRANT ANY OBJECT PRIVILEGE

A user with GRANT ANY OBJECT PRIVILEGE can grant object privileges on behalf of the object owner within the owner's right to grant. When using this privilege, Oracle still enforces constraints on object privilege types and objects.

### 11.4. Do Not Use ANY Privileges Instead of Role Design

For example, if an application only needs SELECT on HR.EMPLOYEES, grant:

~~~sql
GRANT SELECT ON hr.employees TO app_reader;
~~~

instead of:

~~~sql
GRANT SELECT ANY TABLE TO app_reader;
~~~

ANY privileges expand scope to many objects beyond application requirements. Least privilege reduces the blast radius if an account or application is abused.

## 12. Inspecting Privileges Using the Data Dictionary

Oracle provides USER_, ALL_, DBA_, and ROLE_ views to inspect grants.

### 12.1. DBA_SYS_PRIVS

View system privileges granted to users/roles:

~~~sql
SELECT grantee,
       privilege,
       admin_option
FROM dba_sys_privs
WHERE grantee IN ('APP_OWNER', 'SCHEMA_MANAGER')
ORDER BY grantee, privilege;
~~~

ADMIN_OPTION = YES indicates the grant includes ADMIN OPTION.

### 12.2. DBA_TAB_PRIVS

View object privileges:

~~~sql
SELECT grantee,
       owner,
       table_name,
       grantor,
       privilege,
       grantable,
       hierarchy
FROM dba_tab_privs
WHERE owner = 'HR'
  AND table_name = 'EMPLOYEES'
ORDER BY grantee, privilege;
~~~

GRANTABLE = YES indicates the object privilege was granted with GRANT OPTION. HIERARCHY indicates the WITH HIERARCHY OPTION status where applicable.

### 12.3. DBA_ROLE_PRIVS

View roles granted to users/roles:

~~~sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role,
       delegate_option
FROM dba_role_privs
WHERE grantee IN ('ANALYST', 'REPORTING_MANAGER')
ORDER BY grantee, granted_role;
~~~

ADMIN_OPTION = YES indicates the role grant has ADMIN OPTION. DEFAULT_ROLE indicates whether the role is enabled by default on user login per configuration.

### 12.4. DBA_COL_PRIVS

View column-level grants:

~~~sql
SELECT grantee,
       owner,
       table_name,
       column_name,
       privilege,
       grantor
FROM dba_col_privs
WHERE owner = 'HR'
  AND table_name = 'EMPLOYEES'
ORDER BY grantee, column_name;
~~~

### 12.5. ROLE_SYS_PRIVS and ROLE_TAB_PRIVS

ROLE_SYS_PRIVS and ROLE_TAB_PRIVS let you see system/object privileges granted to roles. You can trace:

1. Which roles are granted to which user.
2. Which child roles a role contains.
3. Which system privileges a role contains.
4. Which object privileges a role contains.

When investigating effective privileges, check both the role hierarchy and roles enabled in the session.

### 12.6. SESSION_PRIVS and SESSION_ROLES

~~~sql
SELECT *
FROM session_privs
ORDER BY privilege;

SELECT *
FROM session_roles
ORDER BY role;
~~~

SESSION_PRIVS shows system privileges currently active in the session. SESSION_ROLES shows currently enabled roles. This is useful for distinguishing privileges granted but not enabled from privileges actually usable right now.

### 12.7. USER_ and ALL_ Views

Without DBA dictionary privileges:

- USER_SYS_PRIVS: system privileges related to the current user.
- USER_TAB_PRIVS: object privileges within the current user's scope per view definition.
- USER_ROLE_PRIVS: roles granted to the current user.
- USER_COL_PRIVS: relevant column privileges.
- ALL_TAB_PRIVS and ALL_TAB_PRIVS_RECD: object grants visible within the corresponding scope.

Do not assume a single USER_ view always shows every indirect privilege from all nested roles.

## 13. Designing Role-Based Authorization

A common organization:

~~~text
                  USERS
                    |
        +-----------+-----------+
        |                       |
        v                       v
   APP_READ_ROLE           APP_WRITE_ROLE
        |                       |
        v                       v
  SELECT on view         INSERT/UPDATE via API
  EXECUTE read API       EXECUTE write API
~~~

### 13.1. Create Functional Roles

~~~sql
CREATE ROLE app_read_role;
CREATE ROLE app_write_role;
CREATE ROLE app_support_role;
~~~

### 13.2. Grant Object Privileges to Roles

~~~sql
GRANT SELECT ON hr.employee_directory_v
TO app_read_role;

GRANT EXECUTE ON hr.employee_api
TO app_write_role;

GRANT SELECT ON hr.application_audit_v
TO app_support_role;
~~~

### 13.3. Grant Roles to Users

~~~sql
GRANT app_read_role TO app_reader_01;
GRANT app_write_role TO app_writer_01;
GRANT app_support_role TO app_support_01;
~~~

### 13.4. Separate Role Administrators

If a team lead needs to manage members of a role:

~~~sql
GRANT app_read_role
TO app_role_manager
WITH ADMIN OPTION;
~~~

Grant ADMIN OPTION only for the specific role the person is responsible for. Do not grant GRANT ANY ROLE if only a single role needs administration.

### 13.5. Do Not Grant DBA Privileges to Applications

Runtime applications typically need only CREATE SESSION and business object privileges/roles. Do not grant DBA, SELECT ANY TABLE, UPDATE ANY TABLE, GRANT ANY PRIVILEGE, or GRANT ANY OBJECT PRIVILEGE just to resolve privilege errors.

If an application needs to create objects, separate schema owner/deployment from the application runtime account. Runtime accounts generally do not need DDL privileges.

## 14. Privilege Inspection and Review Workflow

When reviewing a user:

1. Identify direct system privileges.
2. Identify direct object privileges.
3. Identify granted roles and whether any have ADMIN OPTION.
4. Trace nested roles.
5. Check which roles are default/enabled.
6. Check privileges coming from PUBLIC.
7. Check GRANTABLE and ADMIN_OPTION.
8. Check stored procedures/packages/views depending on grants.
9. Identify ANY privileges and grant/revoke administrative privileges.
10. Compare privileges against actual application functionality.

Do not look solely at DBA_TAB_PRIVS and conclude a user has all effective privileges shown. Privileges can come from roles, PUBLIC, system privileges, or other mechanisms.

### 14.1. Finding Object Privileges with Grant Option

~~~sql
SELECT grantee,
       owner,
       table_name,
       privilege,
       grantor
FROM dba_tab_privs
WHERE grantable = 'YES'
ORDER BY owner, table_name, grantee;
~~~

### 14.2. Finding System Privileges with Admin Option

~~~sql
SELECT grantee,
       privilege
FROM dba_sys_privs
WHERE admin_option = 'YES'
ORDER BY grantee, privilege;
~~~

### 14.3. Finding Roles with Admin Option

~~~sql
SELECT grantee,
       granted_role
FROM dba_role_privs
WHERE admin_option = 'YES'
ORDER BY grantee, granted_role;
~~~

### 14.4. Inspecting PUBLIC Grants

~~~sql
SELECT owner,
       table_name,
       privilege,
       grantor
FROM dba_tab_privs
WHERE grantee = 'PUBLIC'
ORDER BY owner, table_name, privilege;
~~~

Grants to PUBLIC can expose privileges to all users. Review write, execute, and delegable privileges especially carefully.

## 15. Common Errors

| Error/symptom | Cause | Resolution approach |
| --- | --- | --- |
| ORA-01031: insufficient privileges | User lacks required privilege for GRANT/REVOKE or object operation | Identify privilege type and grant the exact required privilege |
| ORA-01932: ADMIN option not granted for role | User running GRANT/REVOKE role lacks ADMIN OPTION | Check DBA_ROLE_PRIVS or involve role owner/DBA |
| ORA-01924: role does not exist or is not granted | Role does not exist or role management authority is missing | Check role name, schema, and direct grant |
| ORA-01720: grant option does not exist | View owner lacks grant option on underlying object when granting view privilege | Grant appropriate grant option to view owner or redesign privileges |
| ORA-01919: role does not exist | Role name in GRANT/REVOKE does not exist | Verify role was created and check spelling |
| ORA-01933: cannot create a stored object using privileges from a role | Stored object requires privilege granted via a role | Grant privilege directly to the schema owner |
| User still has access after REVOKE | Another grant exists via a role, direct grant, or PUBLIC | Inspect all grant paths and session roles |
| User unexpectedly loses access after REVOKE | Downstream object grant cascaded or role containing privilege was revoked | Inspect grant chain and dependent objects |
| Cannot revoke ADMIN OPTION alone | Oracle requires revoking the full privilege/role and re-granting | Revoke and re-grant without option |
| Cannot revoke GRANT OPTION alone | Oracle requires revoking the object privilege and re-granting without option | Assess cascade impact before executing |
| FK constraint dropped when revoking REFERENCES | REVOKE used CASCADE CONSTRAINTS | Check dependent constraints before revoking |
| Procedure compile fails even though user can query table | User has privilege via role, but definer-rights code needs direct grant | Grant object privilege directly to procedure owner |

## 16. Anti-Patterns and Security Principles

### 16.1. Granting ADMIN OPTION to Too Many Users

Every user with ADMIN OPTION can expand privilege distribution. Grant it only to people genuinely responsible for administering that privilege or role.

### 16.2. Granting GRANT OPTION to Application Accounts

Application runtime typically only needs to use object privileges. Do not grant delegation rights unless the application is truly a designed, controlled privilege-management layer.

### 16.3. Using ANY Privileges Instead of Specific Object Privileges

If only one table is needed, grant privileges on that table. Do not grant SELECT ANY TABLE or UPDATE ANY TABLE to avoid managing multiple object grants.

### 16.4. Using the DBA Role for Applications

The DBA role covers a very broad administrative scope. Business applications should never run under an account with DBA just to bypass missing-privilege errors.

### 16.5. Granting Privileges to PUBLIC

PUBLIC encompasses every user. Avoid granting sensitive data, DML, or sensitive EXECUTE to PUBLIC. Audit existing PUBLIC grants in the system.

### 16.6. Failing to Check Cascades Before Revoking

Revoking an object privilege with GRANT OPTION can strip access from many downstream users and break stored objects. Before revoking, query DBA_TAB_PRIVS to map the grant chain, inspect dependent views/procedures, and prepare a re-grant plan if needed.

### 16.7. Using Roles Instead of Direct Grants for Definer-Rights Code

Stored definer-rights PL/SQL does not use the owner's regular roles during execution. Grant required privileges directly to the program unit's owner.

### 16.8. Using GRANT ALL Mechanically

ALL has different meanings for system privileges vs. object privileges. Grant the explicit list of required privileges, especially for runtime accounts and objects containing sensitive data.

## 17. Lab: GRANT, REVOKE, and Both Option Types

This lab uses a dedicated schema. Users GRANT_LAB_USER, GRANT_LAB_USER_2, GRANT_LAB_MANAGER, and GRANT_LAB_STEWARD must be prepared beforehand by the DBA with CREATE SESSION. The executor needs privileges to create roles, tables, and grant appropriate object privileges. Adjust schema names if your environment differs. Run only in a test database.

### 17.1. Create a Test Table

In the owner schema:

~~~sql
CREATE TABLE grant_lab_employees (
    employee_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(100) NOT NULL,
    salary NUMBER(10,2)
);

INSERT INTO grant_lab_employees
VALUES (1, 'Nguyen An', 1500);

INSERT INTO grant_lab_employees
VALUES (2, 'Tran Binh', 2000);

COMMIT;
~~~

### 17.2. Create Roles and Grant Object Privileges

~~~sql
CREATE ROLE grant_lab_reader;
CREATE ROLE grant_lab_reader_2;

GRANT SELECT ON grant_lab_employees
TO grant_lab_reader;
~~~

Then the DBA or schema owner grants the role to a test user:

~~~sql
GRANT grant_lab_reader TO grant_lab_user;
~~~

Log in as GRANT_LAB_USER and check roles:

~~~sql
SELECT *
FROM session_roles;
~~~

Query the object with schema qualification:

~~~sql
SELECT *
FROM grant_lab_owner.grant_lab_employees;
~~~

### 17.3. Test WITH ADMIN OPTION on a Role

In the owner schema:

~~~sql
GRANT grant_lab_reader
TO grant_lab_manager
WITH ADMIN OPTION;
~~~

Log in as GRANT_LAB_MANAGER and grant the role to another user:

~~~sql
GRANT grant_lab_reader TO grant_lab_user_2;
~~~

Verify:

~~~sql
SELECT username,
       granted_role,
       admin_option
FROM user_role_privs
ORDER BY username, granted_role;
~~~

### 17.4. Test WITH GRANT OPTION on an Object Privilege

In the owner schema:

~~~sql
GRANT SELECT ON grant_lab_employees
TO grant_lab_steward
WITH GRANT OPTION;
~~~

Log in as GRANT_LAB_STEWARD:

~~~sql
GRANT SELECT ON grant_lab_owner.grant_lab_employees
TO grant_lab_reader_2;
~~~

Verify in the owner schema or a user with dictionary privileges:

~~~sql
SELECT grantee,
       grantor,
       privilege,
       grantable
FROM dba_tab_privs
WHERE owner = 'GRANT_LAB_OWNER'
  AND table_name = 'GRANT_LAB_EMPLOYEES'
ORDER BY grantee;
~~~

GRANTABLE = YES on GRANT_LAB_STEWARD's grant indicates the steward holds GRANT OPTION.

### 17.5. Test Cascading Revoke

In the owner schema:

~~~sql
REVOKE SELECT ON grant_lab_employees
FROM grant_lab_steward;
~~~

Check DBA_TAB_PRIVS again. The downstream grant from GRANT_LAB_STEWARD to GRANT_LAB_READER_2 will be cascade-revoked if no other independent grant exists.

### 17.6. Remove ADMIN OPTION by Revoking and Re-Granting

In the owner schema:

~~~sql
REVOKE grant_lab_reader
FROM grant_lab_manager;

GRANT grant_lab_reader
TO grant_lab_manager;
~~~

Check ADMIN_OPTION in DBA_ROLE_PRIVS or USER_ROLE_PRIVS. The role remains granted, but the new grant has no ADMIN OPTION.

### 17.7. Lab Cleanup

After verification, revoke remaining grants and drop lab-created objects:

~~~sql
REVOKE grant_lab_reader FROM grant_lab_user;
REVOKE grant_lab_reader FROM grant_lab_user_2;
REVOKE grant_lab_reader FROM grant_lab_manager;

DROP ROLE grant_lab_reader;
DROP ROLE grant_lab_reader_2;
DROP TABLE grant_lab_employees PURGE;
~~~

If the role is still granted to other users/roles, revoke those grants before dropping. Never run cleanup commands on shared application roles or tables.

## 18. Checklist Before GRANT or REVOKE

1. **What privilege category is it?** System privilege, object privilege, or role?
2. **Who is the grantee?** User, role, or PUBLIC?
3. **Is the privilege scope accurate?** A single object or database-wide?
4. **Is a delegation option needed?** ADMIN OPTION for system/role; GRANT OPTION for object.
5. **Who is authorized to grant?** Owner, grantor with option, or user with matching GRANT ANY privilege?
6. **Can it be granted via a role?** Grant through a role to manage privilege groups when individual delegation is not needed.
7. **Is a direct grant needed for a PL/SQL owner?** Especially for definer-rights stored code.
8. **Is there a grant chain?** Check DBA_TAB_PRIVS and GRANTABLE before revoking.
9. **Are there dependent downstream users or stored objects?** Assess the impact.
10. **Are there REFERENCES constraints?** Check before using CASCADE CONSTRAINTS.
11. **Are ANY or GRANT ANY privileges involved?** Confirm a genuine administrative need.
12. **Are PUBLIC privileges involved?** Avoid exposing privileges to all users.
13. **Is auditing needed?** Track privilege changes per security policy.
14. **Have effective privileges been verified?** Check direct grants, enabled roles, nested roles, and PUBLIC.
15. **Have changes been verified afterward?** Re-query the dictionary and test with the actual account.

## 19. Self-Check Questions

**Question 1.** How does a system privilege differ from an object privilege?

**Question 2.** What problem do roles solve?

**Question 3.** Which privilege types does WITH ADMIN OPTION apply to?

**Question 4.** Which privilege types does WITH GRANT OPTION apply to?

**Question 5.** Why cannot WITH ADMIN OPTION be used for SELECT ON table?

**Question 6.** What privilege can a user with CREATE TABLE WITH ADMIN OPTION grant?

**Question 7.** What privilege can a user with SELECT ON HR.EMPLOYEES WITH GRANT OPTION further grant?

**Question 8.** Can an object privilege WITH GRANT OPTION be granted to a role?

**Question 9.** Which grantee types does Oracle 19c SQL Reference allow for WITH GRANT OPTION?

**Question 10.** Why can revoking SELECT from a user with GRANT OPTION affect other users?

**Question 11.** Can ADMIN OPTION be revoked alone while keeping the role/system privilege?

**Question 12.** Can GRANT OPTION be revoked alone while keeping the object privilege?

**Question 13.** How does GRANT ANY ROLE differ from ADMIN OPTION on a specific role?

**Question 14.** Why might an object privilege granted via a role be insufficient for definer-rights PL/SQL?

**Question 15.** What is DBA_SYS_PRIVS used to inspect?

**Question 16.** Which column in DBA_TAB_PRIVS indicates a grant has GRANT OPTION?

**Question 17.** Which column in DBA_ROLE_PRIVS indicates a role grant has ADMIN OPTION?

**Question 18.** When is CASCADE CONSTRAINTS required when revoking REFERENCES?

**Question 19.** Why should SELECT ANY TABLE not be granted if an application only needs to read one table?

**Question 20.** Why should you check direct grants, roles, and PUBLIC when investigating why a user can still access an object after REVOKE?

<details>
<summary>Suggested answers</summary>

1. A system privilege permits performing a type of operation at database/schema scope; an object privilege permits operations on a specific object.
2. Grouping privileges together to grant and manage them by function.
3. System privileges and roles.
4. Object privileges.
5. SELECT ON table is an object privilege; the appropriate option is WITH GRANT OPTION.
6. That CREATE TABLE privilege to other users or roles, within delegated authority.
7. SELECT on HR.EMPLOYEES to other users or roles.
8. No. Oracle does not allow WITH GRANT OPTION when the grantee is a role.
9. User or PUBLIC; not a role.
10. Object privilege grants forwarded via grant option can be cascade-revoked.
11. No. You must revoke the privilege/role and re-grant it without ADMIN OPTION.
12. No. You must revoke the object privilege and re-grant it without GRANT OPTION.
13. ADMIN OPTION is tied to a specific privilege/role; GRANT ANY ROLE is a broader administrative system privilege.
14. Regular roles are disabled in definer-rights compile/execute contexts; the owner needs a direct grant.
15. System privileges granted to users/roles and ADMIN_OPTION.
16. GRANTABLE.
17. ADMIN_OPTION.
18. When the grantee has used the REFERENCES privilege to create an existing foreign key constraint.
19. SELECT ANY TABLE opens read access to many objects beyond requirements.
20. Because the privilege may remain effective through another independent grant path.

</details>

## 20. Official Oracle Documentation

1. [Oracle Database 19c SQL Language Reference — GRANT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/GRANT.html): GRANT syntax, WITH ADMIN OPTION, WITH GRANT OPTION, grantee restrictions, and prerequisites.
2. [Oracle Database 19c SQL Language Reference — REVOKE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/REVOKE.html): REVOKE syntax, required privileges, and CASCADE CONSTRAINTS.
3. [Oracle Database 19c Security Guide — Managing System Privileges](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-system-privileges.html): system privileges, ANY privileges, and managing grants/revokes.
4. [Oracle Database 19c Security Guide — Managing Object Privileges](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-object-privileges.html): object privileges, grant option, and READ/SELECT.
5. [Oracle Database 19c Security Guide — Granting and Revoking Roles](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/granting-and-revoking-roles1.html): role hierarchy, ADMIN OPTION, and roles for program units.
6. [Oracle Database 19c Security Guide — Revokes of Privileges and Roles from a User](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/revokes-privileges-and-roles-user.html): revoke requirements, cascading effects, and REFERENCES constraints.
7. [Oracle Database 19c Reference — DBA_SYS_PRIVS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_SYS_PRIVS.html): system privilege grants.
8. [Oracle Database 19c Reference — DBA_TAB_PRIVS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TAB_PRIVS.html): object privilege grants.
9. [Oracle Database 19c Reference — DBA_ROLE_PRIVS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_ROLE_PRIVS.html): role grants and options.

**Key principle to remember:** GRANT grants privileges, REVOKE removes them. System privileges and roles use WITH ADMIN OPTION; object privileges use WITH GRANT OPTION. ADMIN OPTION grants authority to manage the privilege/role; GRANT OPTION grants authority to delegate a specific object privilege. Oracle does not allow revoking the option alone while keeping the privilege. In particular, revoking an object privilege from a grantor with GRANT OPTION can cascade to downstream grantees. Design roles by function, apply least privilege, avoid ANY privileges and PUBLIC, and inspect direct grants, role hierarchies, and grant chains before making privilege changes.
