# Principle of Least Privilege and Separation of Administrative and Application Accounts

In Oracle Database, account security is not just about setting strong passwords. A secure design must restrict each account to the exact work it needs to perform, separate administrative privileges from application runtime privileges, control how privileges are granted, and maintain traceability of actions. The two foundational principles are **least privilege** and **separation of duties**.

An application account typically only needs to connect and perform a defined set of business operations. An administrative account requires broader privileges for deployment, operations, or troubleshooting, but should only be used by responsible personnel and authorized processes. If an application runs under a DBA account or shares a password with a deployment account, a SQL injection vulnerability, leaked secret, or code bug can turn into near-complete control over the database.

Proper design in Oracle requires combining users/schemas, roles, system privileges, object privileges, PL/SQL execution privileges, secret management, auditing, and operational procedures.

## 1. What is Least Privilege?

Least privilege means that a user, service, or process is granted only the privileges necessary to complete its defined task, within the required data scope and timeframe.

For example, a sales application might need to:

- Read certain lookup/catalog tables.
- Call a package to create orders.
- Call a procedure to update payment status.
- Read a view to look up orders for the current customer.

That application usually does not need:

- CREATE USER or ALTER USER.
- DROP ANY TABLE or ALTER ANY TABLE.
- SELECT ANY TABLE or UPDATE ANY TABLE.
- DBA or SYSDBA privileges.
- Privileges to read every schema in the database.
- Privileges to alter instance parameters or listener configuration.

An account with more privileges than needed increases the blast radius if its password is compromised, the application has a bug, or a SQL statement is exploited.

### Principles to Apply

1. Grant privileges for specific tasks, not for temporary convenience.
2. Prefer privileges on specific objects over broad system privileges.
3. Grant privileges through named roles with clear ownership.
4. Separate human accounts, application accounts, deployment accounts, and operational accounts.
5. Use separate accounts per environment and per service when possible.
6. Revoke privileges that are no longer needed and review them periodically.
7. Record who granted the privilege, where it is used, and who is responsible for it.

## 2. Users and Schemas in Oracle

In Oracle Database, a user is an identity used for authentication and owning database objects. A schema is the collection of objects owned by that user. Therefore, when a new user is created, Oracle simultaneously creates a schema with the same name.

Example:

~~~sql
CREATE USER app_owner
  IDENTIFIED BY "Replace-With-A-Managed-Secret";
~~~

The user APP_OWNER has the schema APP_OWNER and can own tables, views, sequences, packages, or other objects. However, creating a user does not automatically mean the user can log in or create objects. Appropriate privileges must be granted.

In an application architecture, you can separate:

| User/schema | Role |
|---|---|
| APP_OWNER | Owns business tables, sequences, views, and PL/SQL |
| APP_RUNTIME | Connection account used by the application during business execution |
| APP_DEPLOY | Account or identity used to deploy schema changes during release windows |
| APP_READONLY | Read-only account for reporting or support |
| DBA_NAMED_USER | Individual named account for a DBA |
| MONITOR_USER | Monitoring identity with approved read privileges |

Not every system must have these exact users. The goal is to clearly separate object ownership, application runtime identity, deployment identity, and administrative identity.

### Why Shouldn't the Application Own the Schema?

If an application connects using the user that owns all tables and packages, any SQL running under that user can use the privileges the owner holds. If runtime credentials are exposed, an attacker can read or modify data, create objects, alter packages, or drop objects depending on the owner's privileges.

A tighter design uses APP_OWNER as the schema owner and APP_RUNTIME as the connection account. APP_RUNTIME only receives CREATE SESSION and the privileges required to call published packages/views.

## 3. Separating Administrative Accounts and Application Accounts

Administrative accounts and application accounts serve different purposes:

| Characteristic | Administrative account | Application account |
|---|---|---|
| User or process | DBA, operations, approved release automation | Application service |
| Purpose | Managing the database, schemas, backups, configuration, and incidents | Executing application business logic |
| Privileges | Only administrative privileges required for the task and scope | Connection privileges and privileges on published database APIs |
| Authentication method | Personal identity, MFA at the access layer, wallet, or appropriate secure method | Secret manager, wallet, or service authentication mechanism |
| Usage duration | Per work session or change window | Per service lifecycle |
| Audit | Must be traceable to an individual or administrative process | Must be traceable to service/module and request where possible |

Do not use SYS, SYSTEM, or users with the DBA role as credentials in an application connection pool. These accounts have very broad privilege scopes and are designed for database administration.

The application account should also not be shared with the deployment account. Deployment requires modifying objects and sometimes executing DDL; normal runtime only needs to read/write data through business APIs. If the same user is used, runtime will hold unnecessary DDL privileges.

## 4. System Privileges and Object Privileges

Oracle has two important categories of privileges:

### System Privileges

A system privilege allows performing a type of action within the database or across many objects. For example:

- CREATE SESSION: log in to the database.
- CREATE TABLE: create tables in the user's own schema, when appropriate quota exists.
- CREATE VIEW: create views in the user's schema.
- CREATE PROCEDURE: create procedures, functions, or packages in the user's schema.
- CREATE USER: create users.
- ALTER USER: modify user attributes.
- DROP ANY TABLE: drop tables in any schema.
- SELECT ANY TABLE: read tables/views across many schemas according to the privilege scope.

Some system privileges with the ANY suffix have a very broad scope. Do not grant these privileges to APP_RUNTIME just to make a SQL query run.

### Object Privileges

An object privilege grants access to a specific object:

- SELECT on a table or view.
- INSERT, UPDATE, DELETE on a table or view when the operation is supported.
- EXECUTE on a procedure, function, or package.
- REFERENCES on an appropriate table or column.
- READ or WRITE on certain objects such as DIRECTORY depending on object type and version.

Example:

~~~sql
GRANT SELECT ON app_owner.product_catalog TO app_runtime;
GRANT EXECUTE ON app_owner.order_api TO app_runtime;
~~~

APP_RUNTIME can only read PRODUCT_CATALOG and call ORDER_API. It does not automatically have SELECT privilege on all tables of APP_OWNER.

### Prefer Narrow Privileges

If an application only needs to read a view that restricts columns or rows, consider granting SELECT on the view instead of the base table. If an application only needs to perform a business operation, granting EXECUTE on an API package can limit the access surface better than granting direct INSERT/UPDATE/DELETE on multiple tables.

## 5. Designing Task-Based Roles

A role is a collection of privileges that can be granted to users or other roles. Using roles helps manage privileges by function rather than granting individual privileges to each user.

Example of creating a role for runtime:

~~~sql
CREATE ROLE app_runtime_role;

GRANT CREATE SESSION TO app_runtime_role;
GRANT SELECT ON app_owner.product_catalog TO app_runtime_role;
GRANT EXECUTE ON app_owner.order_api TO app_runtime_role;

GRANT app_runtime_role TO app_runtime;
~~~

The APP_RUNTIME account receives privileges through APP_RUNTIME_ROLE. When runtime group privileges need to change, the DBA can update the role instead of managing each user independently.

Multiple roles can be designed:

| Role | Typical privileges |
|---|---|
| APP_RUNTIME_ROLE | CREATE SESSION, SELECT on lookup views, EXECUTE on business packages |
| APP_REPORT_ROLE | SELECT on approved reporting views |
| APP_SUPPORT_READ_ROLE | Read selected application diagnostic views |
| APP_DEPLOY_ROLE | Required DDL privileges within the application schema, used only during deployment |
| APP_BATCH_ROLE | Privileges for specific batch jobs |

Avoid creating an APP_ALL_ROLE containing DBA, SELECT ANY TABLE, CREATE ANY PROCEDURE, and many broad privileges and granting it to every user. Roles should represent specific duties and be reviewed like a privilege contract.

### Default Roles and Roles

Roles can be configured as default or non-default for a user. Default roles are enabled when the user logs in according to the configuration. You can check a user's roles and role status in the appropriate dictionary views.

Example of restricting default roles:

~~~sql
ALTER USER app_runtime
  DEFAULT ROLE app_runtime_role;
~~~

In some sessions, a user can use SET ROLE to enable or disable granted roles if configuration allows. However, disabling a role should not be treated as a strong security boundary if the user can simply re-enable that role.

## 6. Runtime Account Calling Only Database APIs

A useful design pattern is having the schema owner own the tables and packages, while the runtime user only gets EXECUTE on the packages. The packages define valid business operations.

Example where the owner creates a package:

~~~sql
CREATE OR REPLACE PACKAGE app_owner.order_api AS
  PROCEDURE create_order(
    p_order_id    IN NUMBER,
    p_customer_id IN NUMBER
  );
END order_api;
/

CREATE OR REPLACE PACKAGE BODY app_owner.order_api AS
  PROCEDURE create_order(
    p_order_id    IN NUMBER,
    p_customer_id IN NUMBER
  ) IS
  BEGIN
    INSERT INTO app_owner.orders (
      order_id,
      customer_id,
      status
    )
    VALUES (
      p_order_id,
      p_customer_id,
      'NEW'
    );
  END create_order;
END order_api;
/
~~~

Then grant the privilege:

~~~sql
GRANT EXECUTE ON app_owner.order_api TO app_runtime;
~~~

APP_RUNTIME can call:

~~~sql
BEGIN
  app_owner.order_api.create_order(
    p_order_id    => 10001,
    p_customer_id => 501
  );
END;
/
~~~

If APP_RUNTIME is not granted direct INSERT on APP_OWNER.ORDERS, the application can only create orders through the published API. This helps centralize business rule checks, auditing, and validation in one place.

### Definer Rights and Invoker Rights

PL/SQL stored units can execute with the privileges of the owner or the privileges of the invoker:

- **Definer rights:** the default for procedures/functions/packages when no other AUTHID is declared. Code runs with the privileges of the schema owner; roles are normally disabled inside named definer-rights PL/SQL units. Privileges required for static SQL inside the unit must be granted directly to the owner according to Oracle rules.
- **Invoker rights:** declared with AUTHID CURRENT_USER. Code uses the invoker's privilege context during execution according to invoker-rights rules; currently enabled roles of the invoker can be taken into account. Name resolution and access rights are also affected by current user/current schema.

Example of invoker rights:

~~~sql
CREATE OR REPLACE PROCEDURE app_owner.show_user_objects
AUTHID CURRENT_USER
AS
BEGIN
  -- Dynamic queries will run under the invoker's privilege context.
  NULL;
END;
/
~~~

Do not choose AUTHID CURRENT_USER just to avoid granting privileges directly. Invoker-rights units can expand the scope of actions according to the caller's privileges, so they must be designed and tested carefully. For business APIs that access owner tables, definer rights is usually the deliberate choice: runtime only needs EXECUTE on the package, while the package uses the owner's direct privileges.

## 7. Why Roles Do Not Replace Direct Grants in Definer-Rights PL/SQL

An important distinction in Oracle is that roles enabled in a session do not apply in the usual way inside named definer-rights PL/SQL units. Therefore, a package owner might be able to run a SELECT statement directly in a worksheet via a role, yet encounter privilege errors when compiling or executing the package.

Example:

~~~sql
-- Suppose APP_OWNER needs to read a table owned by REFERENCE_OWNER.
GRANT SELECT ON reference_owner.countries TO app_owner;
~~~

If privileges are only granted to APP_OWNER via a role, static SQL inside a definer-rights package may lack the required privilege. Grant object privileges directly to the owner for objects that definer-rights code needs to access.

This is why two layers should be separated:

- Roles are used to manage user/session privileges.
- Direct grants to the schema owner ensure stored definer-rights PL/SQL has the necessary privileges at compile time and runtime.

Do not resolve the error by granting DBA or SELECT ANY TABLE to the owner. Identify the specific object and grant the exact privilege needed.

## 8. Phased Privilege Provisioning Pattern

A privilege provisioning process can be divided into phases:

### Phase 1: Create owner and runtime users

~~~sql
CREATE USER app_owner
  IDENTIFIED BY "Use-A-Secret-Manager";

CREATE USER app_runtime
  IDENTIFIED BY "Use-A-Different-Secret";
~~~

In production systems, passwords must be generated, stored, and delivered through a secret manager or secure process. Do not store real passwords in source code, committed SQL files, tickets, or CI/CD logs.

### Phase 2: Grant object creation privileges to the owner

Grant only the DDL privileges needed for the deployment window or scope:

~~~sql
GRANT CREATE SESSION TO app_owner;
GRANT CREATE TABLE TO app_owner;
GRANT CREATE VIEW TO app_owner;
GRANT CREATE SEQUENCE TO app_owner;
GRANT CREATE PROCEDURE TO app_owner;
~~~

APP_OWNER needs a tablespace quota to create segments:

~~~sql
ALTER USER app_owner
  QUOTA 500M ON app_data;
~~~

The 500M quota example is illustrative only; calculate it based on capacity, growth, tablespace policy, and environment. Do not grant UNLIMITED TABLESPACE without an approved reason.

If the owner does not need to log in on its own after deployment, the account can be locked according to operational procedures. Locking the user that owns a schema does not delete the schema or the objects owned by that user.

### Phase 3: Create objects and the runtime role

The schema owner deploys tables, sequences, views, and packages. Then create the runtime role:

~~~sql
CREATE ROLE app_runtime_role;

GRANT CREATE SESSION TO app_runtime_role;
GRANT SELECT ON app_owner.product_catalog TO app_runtime_role;
GRANT SELECT ON app_owner.order_status_v TO app_runtime_role;
GRANT EXECUTE ON app_owner.order_api TO app_runtime_role;

GRANT app_runtime_role TO app_runtime;
~~~

If the application does not need to read a table directly, do not grant SELECT on that table. If an API package already performs the data reads/writes, grant only EXECUTE on the package.

### Phase 4: Revoke deployment privileges not needed at runtime

APP_RUNTIME must not receive CREATE TABLE, CREATE PROCEDURE, ALTER ANY TABLE, DROP ANY TABLE, or DBA privileges. DDL privileges belong to a separate deployment process.

## 9. Separating Deployment Accounts and Application Runtime Accounts

A common design mistake is granting DDL privileges to runtime because the application automatically creates or alters tables at startup. This approach gives every application instance permission to modify the schema.

A deployment pipeline should use a separate identity:

1. Release automation authenticates with managed credentials.
2. The deployment account executes reviewed migrations.
3. Migrations create or modify objects in the owner schema.
4. The pipeline grants or verifies the required runtime privileges.
5. The application starts with APP_RUNTIME and performs only the granted DML/APIs.
6. After the deployment window, deployment credentials are locked or restricted to controlled use.

Applications should not run CREATE TABLE, ALTER TABLE, or CREATE OR REPLACE PACKAGE using the runtime account. Schema migrations should be versioned, logged, verifiable, and have an appropriate rollback procedure.

## 10. Separating Accounts by Service and Environment

Do not use a single database user for all microservices or environments if services have different privilege requirements.

Example:

| Account | Scope |
|---|---|
| ORDER_RUNTIME | Calls order APIs and reads required catalog data |
| BILLING_RUNTIME | Calls billing APIs and reads authorized payment data |
| REPORT_RUNTIME | Reads reporting views |
| ORDER_DEPLOY | Executes order schema migrations |
| ORDER_DEV_RUNTIME | Connects to the development environment |
| ORDER_TEST_RUNTIME | Connects to the test environment |
| ORDER_PROD_RUNTIME | Connects to the production environment |

Separating credentials by service helps:

- Revoke one service without disrupting other services.
- Audit the source of access.
- Limit impact if one secret is compromised.
- Configure separate quotas, profiles, roles, and policies.
- Prevent accessing production data with development credentials.

In Oracle, MODULE/ACTION can be set via DBMS_APPLICATION_INFO or the driver to attach application metadata to a session. This is metadata for observability and auditing, not a replacement for database identity authentication.

## 11. Password and Secret Management

Database user passwords should not be hard-coded in:

- Source code.
- Committed configuration files.
- Docker images or container layers.
- Long-lived deployment scripts.
- Application logs, pipeline logs, or exceptions.
- Widely shared documentation.

Instead:

- Store credentials in a secret manager or an appropriate Oracle wallet / secure external password store.
- Restrict who can read secrets and which services are allowed to retrieve them.
- Use separate secrets per environment and per service.
- Rotate credentials according to policy and application capability.
- Do not pass passwords via command line arguments or environment variables if doing so exposes them in process lists/logs.
- Maintain a process to revoke/rotate immediately when a secret leak is detected.

When using a connection pool, understand how changing a password affects existing connections and how the pool creates new connections. Test the rotation procedure before applying it to production to avoid outages.

### Profiles and Password Policies

Oracle profiles can control certain resource limits and password policies such as lifetime, failed login attempts, lock time, or password reuse according to configuration.

Illustrative example:

~~~sql
CREATE PROFILE app_user_profile LIMIT
  FAILED_LOGIN_ATTEMPTS 5
  PASSWORD_LOCK_TIME 1
  PASSWORD_LIFE_TIME 90;

ALTER USER app_runtime
  PROFILE app_user_profile;
~~~

The values above are examples only, not fixed recommendations for every system. Password expiration policies may not fit service credentials if automated rotation is designed differently. Align with organizational security policies and Oracle version specifics.

Profiles do not replace MFA at the administrative tier, secret managers, or network controls. For service accounts, design rotation so the application can update credentials without storing long-lived passwords in code.

## 12. Personal Administrative Accounts and Special Privileges

DBAs should use personal named accounts so administrative actions can be traced back to the person who performed them. Avoid sharing a single DBA user across a team whenever possible.

Privileges such as SYSDBA, SYSOPER, or equivalent administrative privileges have special scopes. They can be authenticated via a password file, OS authentication, or other administrative mechanisms depending on configuration.

Principles:

- Do not use SYS/SYSTEM as application accounts.
- Do not grant SYSDBA to developers or runtime services.
- Use named DBA accounts for day-to-day operations.
- Use special privileges only when the task requires them.
- Use approval and audit processes for sensitive operations.
- Protect the password file, OS groups, and database host access.
- Consider dedicated break-glass accounts with controlled secret storage, used only during incidents.

A personal DBA account may still hold broad privileges, but accountability and actions must be tied to a specific identity. Separating accounts is meaningless if everyone knows the same user's password.

## 13. Inspecting Granted Privileges

Oracle provides data dictionary views to inspect users, roles, and privileges. Access to these views depends on the account and administrative scope.

### Viewing a user's system privileges

~~~sql
SELECT grantee,
       privilege,
       admin_option
  FROM dba_sys_privs
 WHERE grantee IN ('APP_OWNER', 'APP_RUNTIME')
 ORDER BY grantee, privilege;
~~~

### Viewing granted roles

~~~sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role
  FROM dba_role_privs
 WHERE grantee IN ('APP_OWNER', 'APP_RUNTIME')
 ORDER BY grantee, granted_role;
~~~

### Viewing object privileges

~~~sql
SELECT grantee,
       owner,
       table_name,
       privilege,
       grantable
  FROM dba_tab_privs
 WHERE grantee IN ('APP_OWNER', 'APP_RUNTIME')
 ORDER BY grantee, owner, table_name, privilege;
~~~

### Viewing column-level privileges

Some object privileges can be granted at the column level, such as UPDATE or REFERENCES when syntax and object support it:

~~~sql
SELECT grantee,
       owner,
       table_name,
       column_name,
       privilege
  FROM dba_col_privs
 WHERE grantee IN ('APP_OWNER', 'APP_RUNTIME')
 ORDER BY grantee, owner, table_name, column_name;
~~~

### Viewing roles and system privileges active in the session

~~~sql
SELECT * FROM session_roles;

SELECT * FROM session_privs;
~~~

The SESSION_* views only show privileges/roles currently active in the current session. They do not replace checking all direct grants, role-based grants, inherited privileges, and special privileges.

If you do not have access to DBA_* views, you can use certain USER_* or ALL_* views within the scope visible to the account.

## 14. Revoking Privileges and Cleaning Up Excess Privileges

When a service no longer needs a privilege, revoke it:

~~~sql
REVOKE SELECT ON app_owner.product_catalog FROM app_runtime_role;
REVOKE app_runtime_role FROM app_runtime;
~~~

If a privilege was granted directly to a user, revoke it directly. If the privilege comes through a role, check nested roles and default roles as well. A privilege may be granted from multiple sources, so revoking one grant does not necessarily remove all effective privileges.

Before revoking in production:

1. Identify the object and the user/role receiving the privilege.
2. Check dependencies in packages, views, jobs, and applications.
3. Identify direct grants, role grants, and nested role grants.
4. Test in a test or staging environment.
5. Revoke during an appropriate change window.
6. Verify logins, APIs, and jobs after the change.
7. Document the outcome and update privilege documentation.

Do not keep excess privileges out of fear of change. Plan verification and controlled revocation instead.

## 15. ANY Privileges and DBA Privileges Require Strict Control

Broad system privileges such as SELECT ANY TABLE, INSERT ANY TABLE, UPDATE ANY TABLE, DELETE ANY TABLE, EXECUTE ANY PROCEDURE, CREATE ANY PROCEDURE, ALTER ANY TABLE, and DROP ANY TABLE must be strictly reviewed.

Some privileges may be requested by administrative tools or deployment automation, but must be constrained by:

- Granted identity.
- Grant duration.
- Permitted environment.
- Relevant schema or objects if a narrower restriction is possible.
- Approver and accountable owner.
- Auditing and revocation method.

The DBA role typically contains many system privileges. Do not grant DBA to APP_RUNTIME just to work around an ORA-01031 error. Read the error message, identify the operation being attempted, and grant only the narrowest required privilege.

## 16. Privilege Separation in Oracle Multitenant

In a multitenant architecture, distinguish between the CDB root and pluggable databases (PDBs). Some users/roles are common users/roles at the container scope; others are local users/roles that exist only inside a single PDB.

For business applications, you should generally create a local user inside the PDB that holds the application schema and connect to that PDB's service name. Avoid granting common privileges or creating broad common users if the application only needs access to one PDB.

Example of creating a local user inside a PDB:

~~~sql
-- Connect to the right PDB before running:
CREATE USER app_runtime
  IDENTIFIED BY "Managed-Secret-For-This-PDB";

GRANT CREATE SESSION TO app_runtime;
~~~

Usernames, common/local rules, and user creation privileges depend on the current container and configuration. DBAs must verify they are in the right PDB before running DDL.

An application that uses only one PDB should not have access to multiple PDBs or the CDB root. Isolating local users per PDB narrows the scope and reduces the risk of accessing the wrong container.

## 17. Separating Privileges at the Application and Database Layers

Database privileges are only part of security. The application must still control end users and tenants:

- The database user APP_RUNTIME identifies the service connecting to the database.
- End users are authenticated at the application identity provider or application login mechanism.
- The application checks which business operations the user is authorized to perform.
- Queries must restrict data by tenant or user.
- Database APIs can accept verified tenant/user context and re-validate it by design.

Do not treat every request coming through the same APP_RUNTIME account as the same user. If all requests share a connection pool, the database sees the same database user by default. Pass context safely and provide a way to audit requests, modules, actions, or client identifiers.

### SQL Injection and Bind Variables

Least privilege reduces the impact of SQL injection, but does not replace preventing injection. Do not concatenate user input directly into SQL:

~~~sql
-- Do not build SQL by concatenating strings from input.
-- l_sql := 'SELECT ... WHERE customer_id = ' || p_customer_id;
~~~

Use bind variables:

~~~sql
SELECT order_id,
       status
  FROM app_owner.orders
 WHERE customer_id = :customer_id;
~~~

If using dynamic SQL in PL/SQL, bind data using USING and allow dynamic object/column names only from a controlled allowlist. Bind variables cannot replace dynamic table or column names; dynamic identifiers must be validated and restricted separately.

Even if APP_RUNTIME only has SELECT privilege on a single view, SQL injection can still read all data exposed by that view. Therefore, combine least privilege, bind variables, application-layer authorization, and tenant controls.

## 18. Auditing and Traceability

A least-privilege system needs to know:

- Who logged in.
- Which account performed the operation.
- Which operation was performed on which object.
- When, from which client, module, and with what outcome.
- Who granted or revoked privileges.

Oracle Unified Auditing can help record login activity, privilege changes, and object access according to configured policies. Audit scope should be designed around risk and storage requirements; overly broad auditing can generate excessive data and overhead.

Illustrative example of creating an audit policy for certain operations on a table:

~~~sql
CREATE AUDIT POLICY app_orders_read_pol
  ACTIONS SELECT ON app_owner.orders;

AUDIT POLICY app_orders_read_pol;
~~~

Audit policy syntax and capabilities depend on the Oracle version and active auditing mode. DBAs should test in the target environment and confirm the output audit views and retention before deployment.

For administrative accounts, audit sensitive actions such as user creation, privilege grants, role changes, and configuration changes. For runtime accounts, consider auditing by module/action or targeted policies to support investigations without excessive logging.

Do not store passwords, tokens, or unnecessary sensitive data in MODULE, ACTION, CLIENT_IDENTIFIER, or logs.

## 19. Proxy Authentication and Application Identities

Oracle supports proxy authentication in certain architectures, allowing one user to connect on behalf of another user according to granted configuration. This mechanism can be useful when a middle tier needs to manage connections while still letting the database recognize the end user or a representative schema.

Proxy authentication should not be enabled indiscriminately. Define:

- Which user is allowed to proxy for which user.
- Whether the proxy user is granted session privileges or other privileges.
- How auditing displays the proxy identity and client identity.
- Whether the application can protect the end-user identity from spoofing.
- Whether the connection pool properly resets context when reusing connections.

If there is no requirement for end-user database-level tracing, a dedicated runtime account per service combined with MODULE/ACTION and request auditing may already satisfy requirements. Choose proxy authentication when the identity and operational model genuinely require it.

## 20. Least Privilege Architecture Example

An order application can be deployed according to the following diagram:

~~~text
             Personal DBA
                  |
       approved admin privileges
                  |
                  v
           Oracle Database
                  |
        +---------+---------+
        |                   |
        v                   v
     APP_OWNER           APP_RUNTIME
  owns tables/packages  CREATE SESSION
        |                   |
        |                   v
        |              APP_RUNTIME_ROLE
        |                   |
        |            EXECUTE ORDER_API
        |            SELECT catalog view
        |                   |
        +------ package API +
                   |
                   v
            Business tables
~~~

In this model:

- APP_OWNER owns objects and holds direct privileges needed for packages.
- APP_RUNTIME only connects and calls published APIs.
- APP_RUNTIME_ROLE groups runtime privileges.
- Personal DBAs perform administration under individual identities.
- APP_DEPLOY is a separate identity for migrations, not used in the runtime connection pool.
- Secrets are managed outside source code with a rotation process.

This is a reference pattern. Depending on architecture, you can add accounts for reporting, batch jobs, integrations, or separate schemas per service.

## 21. Periodic Privilege Reviews

Least privilege must be maintained throughout the application lifecycle. Granting the right privileges at deployment does not guarantee they remain appropriate after months of changes.

A review schedule should include:

1. Listing users, roles, and granted system privileges.
2. Listing direct and role-based object privileges.
3. Finding ANY, DBA, SYSDBA, and sensitive administrative privileges.
4. Identifying unused users, decommissioned accounts, or roles without owners.
5. Comparing actual privileges against the list of APIs and service duties.
6. Checking for shared accounts, stale secrets, and credentials in pipelines.
7. Verifying runtime accounts do not hold DDL or administrative privileges.
8. Revoking excess privileges through the change process.
9. Saving review evidence, approvals, and results.

Additional reviews should be triggered after events such as major releases, service splits, DBA staffing changes, database migrations, cloud environment changes, or credential exposure incidents.

## 22. Common Design Mistakes

**Application using a DBA user:** runtime can read, modify, or delete data outside business scope. Create a dedicated runtime user and grant narrow privileges.

**Using one user for multiple services:** makes it hard to identify access sources and revoke individually. Separate service accounts when privileges or lifecycles differ.

**Granting SELECT ANY TABLE to fix an access error:** far broader than a single missing object. Grant SELECT on the specific table/view.

**Granting CREATE ANY or DROP ANY to pipelines:** pipelines can affect unintended schemas. Limit to the schema owner and necessary DDL privileges.

**Using roles and definer-rights packages fail:** static SQL in named definer-rights units needs direct privileges for the owner per Oracle rules. Check specific grants instead of granting DBA.

**Not separating owner and runtime:** the application has permission to alter objects or structural data that it never needs to change at runtime.

**Hard-coding passwords:** secrets can leak via Git, logs, images, or artifacts. Use a secret manager/wallet and rotation.

**Not locking or disabling old accounts:** credentials with no active duty can still be abused. Maintain offboarding and revocation procedures.

**Auditing only logins:** privilege grants, DDL, or sensitive data access may go unrecorded. Design auditing based on risk.

**Treating the database user as the end user:** a single connection pool may represent thousands of users. Pass context safely and enforce authorization at the application layer.

## 23. Safe Implementation Sequence

When provisioning privileges for a new application, follow this order:

1. List application functions and actual SQL operations.
2. Classify objects to be read, written, or invoked.
3. Identify the schema owner and runtime account.
4. Identify the deployment account and administrative identities.
5. Create task-based roles, avoiding overly broad catch-all roles.
6. Grant object creation privileges to the owner within the needed scope.
7. Deploy tables, views, and packages.
8. Grant direct privileges to the owner for cross-schema objects accessed by definer-rights code.
9. Grant object privileges or EXECUTE through the runtime role.
10. Verify runtime holds no DDL/ANY/DBA privileges beyond approved needs.
11. Test connectivity, APIs, transactions, permission errors, and auditing.
12. Store credentials in a secret manager/wallet and test rotation.
13. Document privileges, owners, approvers, and review schedules.

When encountering ORA-01031 (insufficient privileges), do not immediately grant broader privileges. Identify which statement or stored unit failed, which user is actually executing it, whether the required privilege is a system or object privilege, whether the privilege comes from a role or direct grant, and the smallest possible object scope.

## 24. Conclusion

The principle of least privilege requires each account to have only the privileges needed for its specific task. Separating administrative, schema owner, deployment, and runtime accounts limits the blast radius of bugs or leaked credentials while clarifying accountability and auditing.

In Oracle Database, use roles to manage task-based privileges, object privileges to restrict access to individual tables/views/packages, direct grants to the schema owner when definer-rights PL/SQL needs access, and restrict broad system privileges such as ANY or DBA. Manage secrets separately, isolate users by service/environment, control privileges per PDB, and conduct periodic reviews. Applications should run under a runtime user that has only CREATE SESSION and permission to call published database APIs; DDL and administrative operations must go through separate, controlled deployment or administrative identities.
