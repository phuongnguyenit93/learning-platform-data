# Common Users, Local Users, Common Roles, and Local Roles in Oracle CDB/PDB

In the **Oracle Multitenant** architecture, a **container database (CDB)** can contain multiple **pluggable databases (PDBs)**. Each PDB has its own business data and objects, while PDBs within the same CDB share certain infrastructure and administrative components. Therefore, when creating accounts or granting privileges, the question is not only **"what can the user do?"** but also **"in which container does this user or role exist, and in which container do the privileges take effect?"**

Oracle distinguishes four key concepts:

- **Common user**: an identity created at a common container level, present across multiple containers within that common scope.
- **Local user**: an identity created and managed strictly within **one PDB**.
- **Common role**: a role with a shared name and definition across multiple containers, used as a basis for authorization across the CDB or corresponding application container scope.
- **Local role**: a role that exists only within one PDB, suitable for authorization tailored to that PDB's business needs.

A user is an **identity that can log in** if it satisfies authentication mechanisms and holds the session privilege. A role is a **collection of privileges that can be granted to a user or another role**; a role itself is not an application login account. And most importantly: **a common user does not automatically have privileges to read data in every PDB; nor does a common role automatically carry all privileges in every PDB.** The scope of *identity/role existence* and the scope of *each grant's effect* must be examined separately.

## 1. Context: CDB Root and PDBs

A typical Oracle CDB comprises **`CDB$ROOT`** (root), **`PDB$SEED`** (system template PDB), and one or more application PDBs. For example:

```text
                         CDB: SALES_CDB
                               |
           +-------------------+--------------------+
           |                   |                    |
       CDB$ROOT             PDB$SEED           Application PDBs
     CDB administration   System template PDB        |
                                                  +-- SALES_DEV
                                                  |    Own schemas, tables, users, roles
                                                  |
                                                  +-- SALES_TEST
                                                  |    Own schemas, tables, users, roles
                                                  |
                                                  +-- SALES_PROD
                                                       Own schemas, tables, users, roles
```

The diagram only illustrates logical containers. In real deployments, **do not share a CDB across DEV/TEST/PROD just because it is technically possible**: PDBs in the same CDB still share risks at the instance, storage, maintenance, and administration levels. In this lesson, the names `SALES_DEV`, `SALES_TEST`, and `SALES_PROD` illustrate **privilege boundaries**; real environments must determine isolation levels based on security, availability, and governance requirements.

A CDB can also contain an **application root/application PDB** in an *application container* architecture. *Application common users/roles* are created in the **application root** and are scoped to that application container. This lesson first explains **CDB common users/roles created in `CDB$ROOT`** and **local users/roles in regular PDBs**, and then highlights the differences for application containers later.

### 1.1. First Question: Which Container Is the Session In?

In SQL*Plus or SQLcl, you can use the tool command:

```text
SHOW CON_NAME
```

With standard Oracle SQL, the following read-only query is useful even when executed over JDBC:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
```

`CON_NAME` distinguishes root from PDBs; `SERVICE_NAME` shows the service the session is using; `SESSION_USER` indicates the login identity. `CURRENT_SCHEMA` can differ from `SESSION_USER` if a session changes the default schema for object name resolution; **changing `CURRENT_SCHEMA` does not grant additional privileges**.

Operators or developers must verify the **correct service/PDB** before creating users, granting roles, or running migrations. Having the same username in two PDBs does not guarantee it is the same identity.

## 2. Distinguishing *User* and *Role* Before Examining Common/Local

| Aspect | User | Role |
|---|---|---|
| Nature | Database identity, can have authentication mechanisms and a schema owning objects | Set of privileges defined to be granted to other principals |
| Login | Can create a session if account is valid, authenticates, and holds `CREATE SESSION` when required | A role is not a login account |
| Object ownership | Its corresponding schema can own tables, views, packages, sequences, etc. per privileges | A role does not own schemas/tables like a user |
| Privilege assignment | Can receive system, object, and role privileges | Can receive privileges and be granted to users/other roles per Oracle rules |
| Administration | `CREATE USER`, `ALTER USER`, `DROP USER` | `CREATE ROLE`, `ALTER ROLE` when appropriate, `DROP ROLE` |
| Common/local | Determines which containers the user exists in | Determines which containers the role exists in |

For example, an application typically logs in with user `APP_RUNTIME`; report-reading privileges can be packaged in role `APP_REPORT_READER`. An account can receive this role, but receiving a role alone does not allow login: `CREATE SESSION` and authentication requirements must still be met. Also keep in mind that **standard definer-rights PL/SQL units do not use privileges granted through roles to check direct object access**; if a package needs to access tables in another schema, check the appropriate privilege mechanism and required direct grants.

## 3. Common User: Shared Identity of the CDB

A **CDB common user** is created in **`CDB$ROOT`** and shares the same name across containers in the CDB. Typically, it is an identity for administration, monitoring, or operational tasks that need to span multiple PDBs within permitted scopes.

User-created common usernames usually begin with **`C##`**, the default prefix from Oracle's `COMMON_USER_PREFIX` parameter; Oracle-managed system users like `SYS` and `SYSTEM` follow their own rules. Do not change the prefix parameter just to bypass the naming convention. Exact naming rules also depend on Oracle configuration and version.

Illustrative example for an authorized administrator **after confirming the session is in `CDB$ROOT`**:

```sql
-- Executed by an authorized DBA in CDB root.
-- Replace <SECRET_DO_DBA_CAP> with a real secure credential through an approved process.
CREATE USER C##LAB_AUDITOR
IDENTIFIED BY "<SECRET_DO_DBA_CAP>"
CONTAINER = ALL;
```

`CONTAINER = ALL` in the **create common user** statement specifies creation scope across the CDB root and associated PDBs. This is a syntax example for learning; **do not run the placeholder password literally**, and do not store real passwords in committed SQL files or shared terminal history.

### 3.1. Where Does a Common User Exist?

```text
CDB$ROOT:    C##LAB_AUDITOR   (common user)
                  |
                  +---- PDB_A: C##LAB_AUDITOR
                  |
                  +---- PDB_B: C##LAB_AUDITOR
                  |
                  +---- PDB_C: C##LAB_AUDITOR
```

This identity is managed centrally from the root. Creating a common user does not mean it owns one shared set of tables across all PDBs: if permitted to create objects, the schema bearing that name in each PDB has its own separate object scope. Likewise, using the same identity does not automatically **switch sessions** to another PDB or automatically read tables in other PDBs.

To access a PDB, the account still needs valid authentication, session-creation privileges, and an appropriate connection route. Other privileges can be **granted commonly** from root or **granted locally** inside each PDB. Thus, a common user can hold many privileges in PDB A while having very few in PDB B.

### 3.2. When Is a Common User Appropriate?

- Administrative/monitoring identities whose workload spans multiple PDBs and is controlled by the DBA team.
- Management tools needing one consistent identity across multiple containers, with per-PDB privileges explicitly designed.
- CDB administrative workflows that genuinely require common privilege management from the root.

Do not use a common user just to "avoid creating users in each PDB" when an application serves only a single PDB. A common identity widens the **blast radius of privilege-granting mistakes, leaked credentials, or misconfigurations**. A single-PDB application's runtime account is normally best implemented as a local user.

### 3.3. Does a Common User Have Administrative Privileges by Default?

**No.** The `C##` prefix or common status does not automatically make an account a DBA/SYSDBA. Only grant the privileges required for the job. The following is a **local grant** to a common user, executed in the target PDB by an authorized user:

```sql
-- Connected directly to PDB_A via PDB_A's service.
GRANT CREATE SESSION TO C##LAB_AUDITOR CONTAINER = CURRENT;
```

This grant applies only to the current container. If PDB B has not granted the corresponding privilege, do not assume the common user can log into PDB B. Never grant `CREATE SESSION` or data-access privileges across all PDBs using `CONTAINER = ALL` just to fix an application issue in one PDB.

## 4. Local User: Dedicated Identity of a Single PDB

A **local user** is created **inside a single PDB** and exists only in that PDB. This is the right user type for application accounts, schema owners, migration accounts, or business users tied to a specific PDB.

Example in PDB `SALES_DEV`:

```sql
-- Before running: ensure CON_NAME = SALES_DEV.
-- Intended for someone authorized to create users in the DEV PDB.
CREATE USER SALES_APP
IDENTIFIED BY "<SECRET_DO_DBA_CAP>"
CONTAINER = CURRENT;

GRANT CREATE SESSION TO SALES_APP CONTAINER = CURRENT;
```

`CONTAINER = CURRENT` indicates an operation in the current container. With a local user created in a PDB, the `SALES_APP` account does not automatically appear in other PDBs. If `SALES_TEST` also has a user `SALES_APP`, that is a **different local user**, which can have an independent password, status, profile, schema objects, and privileges.

```text
PDB SALES_DEV:   SALES_APP  (local user A)
PDB SALES_TEST:  SALES_APP  (local user B)
PDB SALES_PROD:  SALES_APP  (local user C)

Same name != same account or same privileges.
```

### 4.1. Local Users Do Not Control the Root

A local user is not created in the root to "replicate" across PDBs. The account only has an identity within its own PDB. `CREATE SESSION`, `CREATE TABLE`, `SELECT` on business tables, tablespace quotas, and role memberships are all evaluated within that PDB's scope.

In Oracle, operations from one PDB session do not automatically write to a same-named schema in another PDB. If a DEV application tries to connect to a production PDB using DEV credentials, you must separately examine what matching user and privileges exist in the production PDB; endpoint, network, and secret isolation should be added to reduce misconfiguration risk.

### 4.2. Reasons to Use Local Users for Applications

- **Clear data boundary:** the identity has meaning only within one PDB, matching a single workload or environment.
- **Least privilege:** easy to restrict DML or `EXECUTE` privileges to the exact objects the application needs.
- **Independent lifecycle:** a local user can be locked, have its password rotated, or be revoked when an application is retired without altering CDB common identities.
- **Environment isolation:** DEV/TEST/PROD have separate credentials, quotas, roles, and access policies.

This does not mean a local user is a complete infrastructure isolation boundary: multiple PDBs in the same CDB still share higher-level resources. Operational and availability concerns still require evaluating deployment architecture.

## 5. Common Role: A Role Present Across Multiple Containers

A **CDB common role** is created from `CDB$ROOT`, has the same name across containers in the CDB, and usually carries the `C##` prefix per common role naming rules. It is useful when an organization wants a **shared administrative or monitoring role** to grant to multiple principals while still controlling which privileges apply in each container.

Example creating a common role in the root:

```sql
-- Executed in CDB$ROOT by an authorized account.
CREATE ROLE C##LAB_OBSERVER CONTAINER = ALL;
```

Successfully creating the role only creates the **name and role object** in the common scope. It does not inherently contain `SELECT ANY TABLE`, `DBA`, `CREATE USER`, or any other privilege. Privileges and memberships must be explicitly designed.

### 5.1. How Is a Common Role Granted?

Two concepts must be separated:

1. **Common grant:** executed from the root with `CONTAINER = ALL` per Oracle rules, typically granting a privilege/role to a common principal and taking effect across the relevant containers.
2. **Local grant:** executed inside the current container with `CONTAINER = CURRENT`, taking effect only in that container, even when the grantee principal is a **common user or common role**.

For example, after creating `C##LAB_OBSERVER` and `C##LAB_AUDITOR` in the root:

```sql
-- Executed in CDB$ROOT: common membership for a common user.
GRANT C##LAB_OBSERVER TO C##LAB_AUDITOR CONTAINER = ALL;
```

This role membership has common scope. However, if the newly created role has not yet been granted any query privileges, having the role **still does not allow reading any tables**. An individual PDB can grant appropriate object read privileges to this role **within that PDB**, for example:

```sql
-- Executed in PDB_A with grant privileges on APP_OWNER.AUDIT_EVENTS.
GRANT SELECT ON APP_OWNER.AUDIT_EVENTS
TO C##LAB_OBSERVER;
```

The example above is a **local object privilege grant in PDB_A**; it does not make PDB_A's `AUDIT_EVENTS` table a shared table across all PDBs. The key indicator is the **session location and grant scope**, not merely the `C##` prefix.

> **Scope Warning:** a `GRANT ... CONTAINER = ALL` statement in the root can propagate privileges to multiple existing PDBs and future PDBs per common grant rules. Only apply it when the privilege truly must be effective across that entire scope and has been approved. Never use a common grant to fix a local privilege error.

### 5.2. Can a Common Role Be Granted to a Local User?

**Yes, via a local grant in the appropriate PDB.** For example, in `PDB_A`:

```sql
-- In PDB_A, APP_REPORTER is a previously created local user.
GRANT C##LAB_OBSERVER TO APP_REPORTER CONTAINER = CURRENT;
```

This is a role grant **exclusively for PDB_A's local user `APP_REPORTER`**. `APP_REPORTER` in PDB_B, if one exists, does not automatically receive this role. A common role can be reused across multiple PDBs, but **who receives the role and what privileges the role holds in each PDB must still be reviewed**.

### 5.3. When to Use a Common Role?

- You want to standardize the name and structure of a monitoring or operational role managed from the root.
- There is a genuine shared administrative requirement across multiple PDBs, with scope-controlled grants.
- You want to reuse the same common role for different local users in each PDB while still authorizing locally.

For business logic belonging to only one PDB, a **local role** is usually easier to administer and less likely to unintentionally widen boundaries.

## 6. Local Role: Dedicated Privilege Group Inside a PDB

A **local role** is created **inside a single PDB** and exists only in that PDB. Local roles are ideal for modeling application-specific privileges, such as `ORDER_READER`, `ORDER_WRITER`, `REPORT_VIEWER`, or privilege sets for batch jobs.

Example creating a user and role in `SALES_TEST`:

```sql
-- Confirm connected to SALES_TEST before running.
CREATE ROLE SALES_REPORT_READER CONTAINER = CURRENT;

CREATE USER REPORT_APP
IDENTIFIED BY "<SECRET_DO_DBA_CAP>"
CONTAINER = CURRENT;

GRANT CREATE SESSION TO REPORT_APP CONTAINER = CURRENT;

GRANT SALES_REPORT_READER TO REPORT_APP CONTAINER = CURRENT;
```

Then, the schema owner or an account with grant privileges on the object can grant the required table read privilege to the role:

```sql
-- APP_OWNER.ORDERS must exist in SALES_TEST.
GRANT SELECT ON APP_OWNER.ORDERS TO SALES_REPORT_READER;
```

When `REPORT_APP` logs into `SALES_TEST` and the role is enabled, it can use the privileges granted through the role according to Oracle's role activation rules. This **does not create** any corresponding user, role, or privilege in `SALES_DEV` or `SALES_PROD`.

A local role **cannot be granted commonly from CDB root to all PDBs** because it does not exist as a common role at the CDB level. If two PDBs both need a business role named `SALES_REPORT_READER`, the DBA/application team creates and manages two independent local roles via appropriate migrations or IaC.

### 6.1. Using Roles Instead of Granting Broad Privileges to Individual Users

Avoid granting excessive privileges beyond what is needed, such as:

```sql
-- Examples NOT RECOMMENDED for runtime accounts:
-- GRANT DBA TO REPORT_APP;
-- GRANT SELECT ANY TABLE TO REPORT_APP;
```

Instead, bundle the required object privileges into a local role, e.g. `GRANT SELECT ON APP_OWNER.ORDERS TO SALES_REPORT_READER`. When a new approved reporting table is added, grant access to the role and audit the list of principals holding the role. Never use `SELECT ANY TABLE` just to "avoid granting per table," as it opens a much broader scope than business needs require.

### 6.2. Roles Do Not Replace All Direct Grants

If a **definer-rights PL/SQL package** executes SQL referencing another schema's table, granting privileges only via a role to the package owner is usually **insufficient** to compile or run that logic. You must check the package owner, authid (definer/invoker), direct object privileges, and how Oracle evaluates privileges in the execution context. Direct grants to the package-owning schema may be required. This is a SQL/PLSQL authorization rule, not a common/local bug.

## 7. Comparison Table of the Four Entity Types

| Characteristic | Common User | Local User | Common Role | Local Role |
|---|---|---|---|---|
| Object type | Identity/schema | Identity/schema | Privilege group | Privilege group |
| Where created (standard CDB) | `CDB$ROOT` | PDB | `CDB$ROOT` | PDB |
| Typical scope syntax | `CREATE USER C##... CONTAINER=ALL` | `CREATE USER ... CONTAINER=CURRENT` | `CREATE ROLE C##... CONTAINER=ALL` | `CREATE ROLE ... CONTAINER=CURRENT` |
| Existence scope | Containers of the CDB | One PDB | Containers of the CDB | One PDB |
| Common naming convention | Starts with `C##` | Does not use the reserved common prefix | Starts with `C##` | Does not use the reserved common prefix |
| Can log in? | When authenticated and holding required privileges | When authenticated and holding required privileges | No | No |
| Do privileges arise automatically? | No | No | No | No |
| Can receive local grants? | Yes, in the target PDB | Yes, in its own PDB | Yes, in the target PDB | Yes, in its own PDB |
| Can receive common grants? | Yes, when meeting common grant conditions from root | No, local principals do not exist across all PDBs | Yes, when meeting common grant conditions from root | No |
| Typical use | Multi-PDB administrative work | Single-PDB application/business unit | Standardized multi-PDB admin/monitoring roles | Business access privileges within one PDB |

**Two axes to read separately:** `USER`/`ROLE` indicates **principal vs. privilege group**; `COMMON`/`LOCAL` indicates **existence scope**. Grants then have their own axis for **effective scope**: common grant or local grant.

## 8. `CONTAINER = ALL` and `CONTAINER = CURRENT`: Do Not Confuse Them

In statements that create principals or grant privileges, Oracle supports the `CONTAINER` clause to specify scope, but **valid combinations depend on the command, principal type, and current container**. You cannot arbitrarily write `CONTAINER=ALL` in any PDB.

### 8.1. Creating Identities/Roles

```text
In CDB$ROOT:
    CREATE USER C##OPS_... CONTAINER = ALL    -> common user
    CREATE ROLE C##OPS_... CONTAINER = ALL    -> common role

In PDB_A:
    CREATE USER APP_... CONTAINER = CURRENT   -> local user
    CREATE ROLE APP_... CONTAINER = CURRENT   -> local role
```

Creating common users/roles is a root administrative action. You cannot create a CDB common user from inside a PDB by adding `CONTAINER=ALL`. And you should not treat the root as a place to create local PDB application accounts.

### 8.2. `GRANT` Scope

Example of the same common user receiving `CREATE SESSION` in two ways:

```sql
-- In CDB$ROOT, if approved for a common grant:
GRANT CREATE SESSION TO C##LAB_AUDITOR CONTAINER = ALL;

-- In PDB_A, if privileges are only needed in PDB_A:
GRANT CREATE SESSION TO C##LAB_AUDITOR CONTAINER = CURRENT;
```

The two statements express **two different privilege policies**, not two equivalent ways of writing the same thing. A common grant from the root applies across the common scope; a local grant applies only to the current container. A common privilege can also appear in `DBA_SYS_PRIVS` inside a PDB marked `COMMON = YES`, whereas a privilege granted only inside that PDB typically shows `COMMON = NO`.

The same applies to **role membership**: a common role granted commonly to a common user in the root takes effect commonly; a role granted only inside a PDB takes effect in that PDB. **A local user cannot receive a CDB-wide common grant** since it exists only in its own PDB.

### 8.3. Distinguishing Common Grants and Common Principals

```text
COMMON PRINCIPAL        SCOPE OF GRANT
------------------      ---------------------------
C##LAB_AUDITOR          CREATE SESSION [PDB_A: LOCAL]
  exists in all PDBs    SELECT ...      [PDB_A: LOCAL]
                        CREATE SESSION [PDB_B: NOT GRANTED]
                        CREATE SESSION [ROOT: NOT GRANTED]

Role C##LAB_OBSERVER    Can receive local privileges
  exists in all PDBs    separately in PDB_A, PDB_B, ...
```

This is the conceptual model. Just because a principal is defined as common does not mean locally granted privileges propagate to other PDBs. The reverse is also true: a user named `APP_RUNTIME` that exists only in PDB_A cannot become a common user via a `GRANT ... CONTAINER=ALL`.

## 9. Inspecting Common/Local via the Data Dictionary

`DBA_*` views allow DBAs to inspect metadata **within the currently connected container**. The following queries are intended for users with appropriate data dictionary read privileges; runtime applications should not be granted administrative privileges just to view these reports.

### 9.1. Determining Local vs. Common Users

```sql
SELECT username, common, oracle_maintained, account_status
FROM dba_users
WHERE username IN ('C##LAB_AUDITOR', 'SALES_APP', 'REPORT_APP')
ORDER BY username;
```

`COMMON = YES` indicates a common user, while `COMMON = NO` indicates a local user. `ORACLE_MAINTAINED` identifies Oracle-managed users. **Do not decide to drop or modify a user's privileges based solely on name prefixes**: metadata and ownership scope are the authoritative evidence.

When run in **PDB_A**, you can see common users and PDB_A's local users; that does not imply PDB_B's local users are also present in PDB_A.

### 9.2. Checking Common/Local Roles

```sql
SELECT role, common, oracle_maintained
FROM dba_roles
WHERE role IN ('C##LAB_OBSERVER', 'SALES_REPORT_READER')
ORDER BY role;
```

`COMMON = YES/NO` distinguishes the role's origin. A newly created common role with no privileges yet still appears as a valid role: **the presence of a role does not prove it allows access to any table**.

### 9.3. Checking Whether System Privileges Were Granted Locally or Commonly

```sql
SELECT grantee, privilege, admin_option, common
FROM dba_sys_privs
WHERE grantee IN ('C##LAB_AUDITOR', 'SALES_APP', 'REPORT_APP')
ORDER BY grantee, privilege;
```

`COMMON` in this output indicates whether the **grant** is common or local, not the common/local status of the user. Also cross-check the current container. Similarly for role membership:

```sql
SELECT grantee, granted_role, admin_option, default_role, common
FROM dba_role_privs
WHERE grantee IN ('C##LAB_AUDITOR', 'SALES_APP', 'REPORT_APP')
ORDER BY grantee, granted_role;
```

A common user can appear with a **`COMMON=NO` grant** in PDB_A; this is completely normal when an organization wants to grant privileges only in that PDB.

### 9.4. Observing Across Multiple Containers from Root

When connected to `CDB$ROOT` with a sufficiently privileged account, a DBA can use `CDB_*` views to inspect metadata across multiple containers. For example:

```sql
-- Run in CDB$ROOT by a DBA with appropriate privileges.
SELECT con_id, username, common, oracle_maintained
FROM cdb_users
WHERE username IN ('C##LAB_AUDITOR', 'SALES_APP')
ORDER BY con_id, username;
```

`CON_ID` locates the container owning each metadata row; it can be cross-referenced against the container list using appropriate admin tools. `CDB_*` views have privilege and container-context requirements; visible rows also depend on session privileges, PDB state, and Oracle version. Do not treat the absence of a PDB in the output as proof that the PDB does not exist before verifying privileges and metadata access.

## 10. Common User Privileges per PDB: Complete Example

Suppose a CDB has two business PDBs: `PDB_SALES` and `PDB_SUPPORT`. The operations team wants account `C##AUDIT_OPERATOR` to use a single shared identity to check business logs, but only be allowed to **read** approved audit tables in each PDB, without arbitrary access to all tables.

```text
                                  CDB$ROOT
                         C##AUDIT_OPERATOR (common user)
                         C##AUDIT_READ     (common role)
                                   |
              common grant: role -> user (CONTAINER=ALL)
                                   |
                     +-------------+-------------+
                     |                           |
                 PDB_SALES                   PDB_SUPPORT
             CREATE SESSION (local)       CREATE SESSION (local)
             SELECT AUDIT_LOG (local)     SELECT EVENT_LOG (local)
                     |                           |
               user uses role              user uses role
               in PDB_SALES                in PDB_SUPPORT
```

### Step 1 – DBA Defines Common Principals in the Root

```sql
-- Run in CDB$ROOT by an account with assigned administrative privileges.
CREATE USER C##AUDIT_OPERATOR
IDENTIFIED BY "<SECRET_DO_DBA_CAP>"
CONTAINER = ALL;

CREATE ROLE C##AUDIT_READ CONTAINER = ALL;

GRANT C##AUDIT_READ TO C##AUDIT_OPERATOR CONTAINER = ALL;
```

At this point, the common role has no privileges to read any business table, and the lab **has not granted persistent `CREATE SESSION` across all PDBs**. The administrator assigns privileges in the required PDBs.

### Step 2 – Grant Specific Privileges in PDB_SALES

```sql
-- Administrative session currently in PDB_SALES.
GRANT CREATE SESSION TO C##AUDIT_OPERATOR CONTAINER = CURRENT;

-- Example table must actually exist and grantor must have grant rights on the table.
GRANT SELECT ON SALES_OWNER.AUDIT_LOG TO C##AUDIT_READ;
```

### Step 3 – Grant Different Privileges in PDB_SUPPORT

```sql
-- Administrative session currently in PDB_SUPPORT.
GRANT CREATE SESSION TO C##AUDIT_OPERATOR CONTAINER = CURRENT;

GRANT SELECT ON SUPPORT_OWNER.EVENT_LOG TO C##AUDIT_READ;
```

When logging into `PDB_SALES`'s service, the account can only use the privileges available in `PDB_SALES`; when logging into `PDB_SUPPORT`, object privileges are governed by the grants in `PDB_SUPPORT`. **A common role shares one name, yet its object privileges can differ by PDB**. Do not interpret results from one PDB as CDB-wide.

### Step 4 – Block Unauthorized Scope

If `PDB_FINANCE` exists outside the monitoring scope, the organization **does not grant `CREATE SESSION` or data-read privileges in that PDB**. Also restrict network routes/services and secret distribution so no one assumes a common account can freely access everything. Any other privileged access policies must be evaluated separately.

### Step 5 – Verify the Grants

For each PDB, the DBA checks `DBA_USERS`, `DBA_ROLES`, `DBA_SYS_PRIVS`, `DBA_ROLE_PRIVS`, and the relevant object grants. The tester logs in using the actual common user via the provisioned service and runs approved read queries; never test as `SYS`, because high privileges will mask authorization errors on the real account.

## 11. Counter-Example: Local Roles for a Single-PDB Application

A Spring Boot service `order-api` only works with the `ORDER_OWNER` schema in `PDB_ORDERS`. The project team creates local users and roles:

```text
PDB_ORDERS
  |
  +-- ORDER_OWNER        : schema containing tables
  +-- ORDER_API          : local runtime user
  +-- ORDER_API_READ     : local role
  +-- ORDER_API_WRITE    : local role

PDB_BILLING
  |
  +-- Does not automatically have ORDER_API or the roles above
```

Example local statements, executed by an authorized user in `PDB_ORDERS`:

```sql
CREATE ROLE ORDER_API_READ CONTAINER = CURRENT;
CREATE ROLE ORDER_API_WRITE CONTAINER = CURRENT;

CREATE USER ORDER_API
IDENTIFIED BY "<SECRET_DO_DBA_CAP>"
CONTAINER = CURRENT;

GRANT CREATE SESSION TO ORDER_API CONTAINER = CURRENT;

-- Object owner or user with grant privileges executes the grants.
GRANT SELECT ON ORDER_OWNER.ORDERS TO ORDER_API_READ;
GRANT INSERT, UPDATE ON ORDER_OWNER.ORDERS TO ORDER_API_WRITE;

GRANT ORDER_API_READ, ORDER_API_WRITE TO ORDER_API;
```

This authorization tightly fits one PDB and the exact operations the application needs. Depending on the architecture, the runtime account can receive direct grants or roles, especially if calling definer-rights PL/SQL where direct grants must be checked. Do not convert all these users/roles to common just because the company has multiple PDBs: local entities minimize blast radius and simplify lifecycle management.

## 12. Key Points About Container Switching

In a multitenant environment, many administrative operations depend on the **current container**. A DBA can switch containers with the appropriate statement when the account holds the required privileges:

```sql
-- Example for an administrative account granted the required SET CONTAINER privilege.
ALTER SESSION SET CONTAINER = PDB_ORDERS;
```

Not every user is permitted to execute this statement. And **switching containers does not replace being granted privileges in the target PDB**; identity, state, session privileges, and policies are still enforced by Oracle.

For applications, the standard pattern is connecting directly to the **target PDB's service**:

```text
jdbc:oracle:thin:@//db-host.internal:1521/order_pdb_service
```

`order_pdb_service` is an illustrative name. An application connection pool should consistently connect to its configured and authorized PDB; ordinary applications should not use container-switching privileges to access multiple PDBs. Having a common user does not mean an application can run cross-PDB queries with a simple SQL statement as if all tables belonged to the same schema.

When operating multiple PDBs, record the **PDB/service** in audit logs, incident records, and deployment metadata. Logging only `username = APP_USER` is incomplete if each PDB has a local user with the same name.

## 13. PDB Lifecycle and Implications for Common/Local

Common/local characteristics also appear when creating, cloning, unplugging/plugging, or dropping a PDB:

| Activity | Common User/Role | Local User/Role |
|---|---|---|
| Creating an additional PDB in the CDB | CDB-scoped common principals are recognized via common mechanisms | The new PDB does not automatically receive manually created local principals from other PDBs |
| Granting privileges in PDB A | Can receive local grants in PDB A; does not imply privileges in PDB B | Only affects local principals in PDB A |
| Cloning a PDB | Common principals remain subject to metadata rules and target CDB compatibility | Local users/roles are part of the cloned metadata/data per the PDB clone process |
| Unplugging/plugging a PDB into another CDB | Must evaluate common principal compatibility between source/target CDBs and any Oracle-reported sync/violation issues | Local principals stay attached to the moved PDB, though privileges and dependencies still need verification |
| Revoking privileges in one PDB | Local grants can be revoked in that PDB | Local grants are managed in that exact PDB |

Actual lifecycle behavior depends on Oracle version, PDB type, and migration method; do not assume clone/plug will keep **every** privilege and credential working identically without checks. When moving a PDB across CDBs, the DBA must review plug-in violations, common principal states, privileges, and security before opening the service.

Dropping a **common user or common role** in the root is a broad-scope operation that can affect multiple PDBs. Do not run `DROP USER C##...` or `DROP ROLE C##...` routinely to clean up test data without verifying all dependencies and impact scope.

## 14. Application Common Users/Roles as an Extended Case

An **application container** has an **application root** and application PDBs. Oracle supports **application common users and application common roles**, managed within the scope of the corresponding application container. These are neither CDB common principals in `CDB$ROOT` nor local principals of a single PDB.

```text
CDB$ROOT
  |
  +-- APP_ROOT (application root)
  |     |
  |     +-- APP_PDB_1
  |     +-- APP_PDB_2
  |     +-- Application common principals scoped to APP_ROOT
  |
  +-- OTHER_PDB (outside the application container)
```

Application common principals are used to share administration/application objects among related application PDBs. **They do not automatically exist or hold privileges in PDBs outside the application container**. Syntax, metadata sharing modes, and application sync workflows follow their own rules; consult exact documentation for your Oracle version and container type when using them. Do not mechanically apply the `CREATE USER C##... CONTAINER=ALL` recipe meant for CDB root inside an application root.

## 15. Hands-On Lab: Distinguishing Identities and Grant Scope

This lab requires **an Oracle CDB with at least two test PDBs** and a DBA or authorized person to create principals. Creating common users/roles in the root has broad scope; only execute this in an approved lab, **never in production**, and never use built-in system accounts like `SYS` as an application identity.

### Step 1 – Observe the Container Before Acting

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
```

Record whether this is `CDB$ROOT`, `PDB_A`, or `PDB_B`, and what privileges the session holds. Do not run commands to create common principals while inside a regular PDB.

### Step 2 – DBA Creates a Common User and Common Role in the Root

```sql
-- CDB$ROOT, only execute if the lab scope is approved.
CREATE USER C##LAB_REVIEWER
IDENTIFIED BY "<SECRET_LAB>"
CONTAINER = ALL;

CREATE ROLE C##LAB_READ_ONLY CONTAINER = ALL;

GRANT C##LAB_READ_ONLY TO C##LAB_REVIEWER CONTAINER = ALL;
```

At this stage, **by default** the new account does not have `CREATE SESSION` nor does the role have `SELECT` on any object. Creating common users/roles and granting privileges are two separate actions.

### Step 3 – In PDB_A, Create a Local User and Local Role

```sql
-- PDB_A, requires CREATE USER / CREATE ROLE privileges in this PDB.
CREATE USER LAB_REPORT_A
IDENTIFIED BY "<SECRET_LAB_A>"
CONTAINER = CURRENT;

CREATE ROLE LAB_REPORT_VIEW CONTAINER = CURRENT;

GRANT CREATE SESSION TO LAB_REPORT_A CONTAINER = CURRENT;
GRANT LAB_REPORT_VIEW TO LAB_REPORT_A CONTAINER = CURRENT;
```

### Step 4 – In PDB_A, Locally Grant Usage of the Common Role

```sql
-- Only allow the common user to open sessions in PDB_A.
GRANT CREATE SESSION TO C##LAB_REVIEWER CONTAINER = CURRENT;

-- A common role can be granted to a local user solely within PDB_A.
GRANT C##LAB_READ_ONLY TO LAB_REPORT_A CONTAINER = CURRENT;
```

These roles do not yet necessarily hold object privileges. To test SQL execution privileges, you can create a dummy data table **inside an authorized lab schema**, then have the object owner grant `SELECT` to the appropriate role. Never use real tables, the `DBA` role, or `SELECT ANY TABLE` for illustration.

### Step 5 – Inspect Metadata in PDB_A

```sql
-- DBA or user permitted to view the relevant metadata.
SELECT username, common
FROM dba_users
WHERE username IN ('C##LAB_REVIEWER', 'LAB_REPORT_A');

SELECT role, common
FROM dba_roles
WHERE role IN ('C##LAB_READ_ONLY', 'LAB_REPORT_VIEW');

SELECT grantee, privilege, common
FROM dba_sys_privs
WHERE grantee IN ('C##LAB_REVIEWER', 'LAB_REPORT_A');

SELECT grantee, granted_role, common
FROM dba_role_privs
WHERE grantee IN ('C##LAB_REVIEWER', 'LAB_REPORT_A');
```

Point out the difference between `DBA_USERS.COMMON` and `DBA_SYS_PRIVS.COMMON`: one value describes **the user type**, while the other describes **the grant scope**. When inspected in PDB B, the common user/role may still be present, whereas PDB A's local `LAB_REPORT_A`/`LAB_REPORT_VIEW` will not automatically exist in PDB B.

### Step 6 – Inspect in PDB_B

In PDB_B, the DBA confirms the common principals exist, then checks whether `CREATE SESSION` was granted locally in PDB B. Because the lab did not grant common `CREATE SESSION` in the root, **do not assume the common user can log into PDB B successfully**. Likewise, role `LAB_REPORT_VIEW` created in PDB A is not a role in PDB B.

If you need further practice in PDB B, create **dedicated local principals** and grant selectively in PDB B as required. Do not copy secrets or automatically issue common grants just to make a lab "easier to run."

### Step 7 – Record Findings

| Question | Key Observation to Record |
|---|---|
| What type of user is `C##LAB_REVIEWER`? | Common user because it was created in root, showing `COMMON=YES` |
| Where does `LAB_REPORT_A` exist? | Only inside PDB A where the user was created |
| What type of role is `C##LAB_READ_ONLY`? | Common role; can receive local grants or common grants |
| Does `LAB_REPORT_VIEW` appear in PDB B? | Does not appear automatically because it is a local role of PDB A |
| Does granting `CREATE SESSION` in PDB A automatically grant it in PDB B? | No; that is a local grant `CONTAINER=CURRENT` |
| Can a common user read all tables in a PDB? | No; must inspect object/system privileges, role memberships, and grant scopes |

When cleaning up the lab, **only authorized administrators** may drop objects after verifying there are no remaining dependencies and nothing is shared with other exercises; in particular, common principals have a CDB scope wider than one PDB. Save reports using metadata and query outputs, never real credentials.

## 16. Error-Prone Scenarios in Development and Operations

### Scenario A – Application Reports `ORA-01017` Even Though DEV Connects Fine

User `APP_API` is a **local user** in `PDB_DEV` and `PDB_TEST`. The two PDBs have accounts with the same name but different passwords. When the TEST configuration accidentally points to DEV credentials, Oracle may reject authentication with `ORA-01017`.

**Resolution:** verify `SERVICE_NAME`, `CON_NAME`, secret source, and user identity in the right PDB; do not create a common user to "sync passwords" or grant admin rights. Separate secrets per environment and control connections from workloads.

### Scenario B – Common User Exists, Yet `ORA-01045` Occurs

A DBA creates `C##MONITOR` in CDB root, then a tool tries to log into a new PDB and encounters `ORA-01045` due to missing `CREATE SESSION` in that context. A common name only indicates the identity exists, **not that session-creation privileges have been granted**.

**Resolution:** check grants in the target PDB and request the narrowest appropriate privilege. If a privilege needs to exist in multiple PDBs, the DBA must separately evaluate a common grant request; never open privileges CDB-wide just to handle one PDB.

### Scenario C – Common Role Has the Right Name, Yet User Still Cannot Read Table

`C##READ_AUDIT` exists in every PDB and was granted to a local user in PDB B. However, `SELECT ON OWNER.AUDIT_LOG` was only granted to that role in PDB A.

**Resolution:** check `DBA_ROLE_PRIVS`, object grants, and **the container executing the query**. Grant the object privilege in PDB B if approved; never grant `SELECT ANY TABLE` CDB-wide.

### Scenario D – `ORA-00942` When Package Runs, Yet Direct Query Succeeds

A user receives `SELECT` via a role and runs direct SQL successfully. Later, a definer-rights PL/SQL package in that schema referencing another schema's table fails with an object or privilege error.

**Resolution:** recognize the difference between role-based privileges and direct privileges when compiling/executing definer-rights PL/SQL; the DBA or owner grants the appropriate direct object privilege. Making the role common will not resolve this execution rule.

### Scenario E – After Plugging a PDB into a New CDB, Common Privileges Behave Differently

A PDB moved to another CDB may encounter differences in common users/roles or common grants. The DBA must verify metadata compatibility and post-plug check messages, then test privileges and connections with the actual principal.

**Resolution:** review the migration procedure; do not assume a common role brings all grants from the old CDB into the new CDB. Test with the least-privileged application/monitoring account; also check secret policies and target services.

## 17. Security Principles for CDB/PDB Authorization

Common scope can be convenient for administration, yet it also increases the impact of a mis-granted privilege or compromised credential. A secure design generally follows these principles:

1. **Prefer local users for runtime accounts** of applications using only one PDB; use common users when there is a clear cross-container requirement.
2. **Prefer local roles for business privileges** within one PDB; common roles are mainly for reusable administrative/monitoring policies.
3. **Grant least privilege**, distinguishing system privileges (`CREATE SESSION`, `CREATE TABLE`), object privileges (`SELECT`, `UPDATE`, `EXECUTE`), and role memberships.
4. **Do not confuse common principals with common grants**; requests must explicitly specify `CONTAINER=ALL` or `CURRENT` per business need and approval policy.
5. **Separate application runtime accounts from migration/DBA accounts**; runtime users do not need `CREATE USER`, `ALTER SYSTEM`, `DBA`, or `SYSDBA`.
6. **Isolate passwords, secrets, networks, and services per environment**; merely naming two PDBs differently does not guarantee isolation.
7. **Audit broad-scope operations** from CDB root, especially `GRANT ... CONTAINER=ALL`, modifying common users/roles, and PDB lifecycle operations.
8. **Test privileges using the actual identity** of the application or tool; a query succeeding under `SYS` does not prove a runtime account has privileges.
9. **Assess impact when adding new PDBs**, changing operational tools, or moving PDBs between CDBs: common grants and local grants have different lifecycles.

| Common Mistake | Consequence | Correct Understanding |
|---|---|---|
| "The name has `C##`, so it must be a DBA." | Over-privileging or misdiagnosis | `C##` usually reflects common naming; privileges are determined by grants |
| "A common user automatically logs in and reads all PDBs." | Overlooking `CREATE SESSION`, roles, and object grants | Common identity exists in multiple places, while privileges may be local only |
| "A common role inherently contains all privileges in all PDBs." | Under- or over-authorizing | A role holds only granted privileges; object privileges can differ per PDB |
| "The same user `APP_API` in two PDBs is the same account." | Confusing passwords/secrets and ownership | Two same-named local users remain independent |
| "A local role in PDB A can use `GRANT ... CONTAINER=ALL` for PDB B." | Syntax/scope error, flawed mental model of local roles | A local role exists and takes effect only within its own PDB |
| "`DBA_USERS.COMMON=YES` means the grant is also `COMMON=YES`." | Misinterpreting effective privileges | Must read the `COMMON` column of **each grant** |
| "Having privileges via a role means a definer-rights package always runs." | PL/SQL compile/runtime errors | Some cases require direct grants to the owner |
| "Routing to a PDB by service name is enough isolation." | Misconfiguration/shared secrets can cause cross-access | Combine endpoint, secret, network, privilege, and audit controls |

## 18. Case-Based Exercises

### Question 1 – Choosing a User Type

A system has 12 PDBs for 12 customers. Each application only accesses its corresponding customer's PDB. Should runtime accounts start with common or local users?

**Hint:** local users are more appropriate because access is scoped to one PDB; use distinct identities and secrets per tenant if policy requires. Common users can be reserved for multi-PDB administration with tightly controlled privileges.

### Question 2 – Choosing a Role Type

The monitoring team has a metadata-reading role that needs to exist across multiple PDBs, yet each PDB only permits reading an appropriate set of views. Choose a common or local role?

**Hint:** a common role can standardize the role identity, combined with **local object grants** in each PDB. If root-level management is not needed, it can also be organized with separate local roles; clearly state who approves scope and privileges.

### Question 3 – Reading Dictionary Information

In PDB A, `DBA_USERS` returns `C##ADMIN_A / COMMON=YES`, while `DBA_SYS_PRIVS` records `CREATE SESSION / COMMON=NO`. Is this contradictory?

**Answer:** no. The user is a common principal, while the `CREATE SESSION` grant was issued **locally in PDB A**.

### Question 4 – Same Name in Two PDBs

`REPORT_USER` exists in PDB A and B, each with a different password and different roles. Is this a common user?

**Answer:** no. Two local users were created independently in two PDBs and simply happen to share the same name.

### Question 5 – Misconception About Roles

A development team creates `C##REPORT_READER` in the root and immediately believes users in all PDBs can run `SELECT` on the `ORDERS` table. What is missing?

**Answer:** you must check which users were granted the role, **membership scope**, which object privileges were granted to the role in which PDB, and whether the role is enabled during SQL execution. Creating a common role creates no grants on its own.

## Conclusion

In Oracle Multitenant, **common/local defines the existence scope of a user or role**, whereas **`CONTAINER=ALL`/`CONTAINER=CURRENT` defines the scope of applicable operations and grants**. **Common users** and **common roles** are managed at the root for multi-container scope; **local users** and **local roles** belong solely to their PDB. A common principal can still receive only local privileges in one PDB, and two same-named local principals in two PDBs remain independent.

When deploying applications or administering Oracle, always verify the **current container, principal type, scope of each grant, and actual required privileges**. This distinction prevents `CREATE SESSION` failures, data-access privilege errors, confusion after PDB migrations, and especially accidental over-privileging from the CDB root.
