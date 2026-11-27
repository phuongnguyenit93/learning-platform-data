# Database Links, Fixed/Current Users, and Access Privilege Scope in Oracle

## 1. What Are Database Links Used For?

An Oracle architecture may separate data across multiple databases: an operational database, a reporting database, a data warehouse, or another business unit's database. When an application needs to query data in another database, Oracle provides a **database link** so SQL in the current database can reference remote objects.

A database link is a schema object in the local database that stores the details needed to connect to a remote database. Once the link is created, SQL can use the syntax:

~~~sql
SELECT employee_id, first_name, last_name
FROM hr.employees@hr_link;
~~~

In this example:

- `HR.EMPLOYEES` is a table in the remote database.
- `HR_LINK` is a database link created in the local database.
- The local database opens a connection to the target database using the connection details and identity configured in the link.

Database links are commonly used to query data across multiple databases in a single SQL statement, synchronize data, run DML against remote tables, build local views/synonyms, or join transactional data with reference data residing in different databases.

A crucial point is that a database link has two independent dimensions:

1. **Link visibility scope:** private or public.
2. **Identity used to log into the remote database:** connected user, fixed user, or current user.

Link visibility scope does not automatically grant privileges on remote tables. Remote data access is checked according to the identity the link uses to connect.

> This lesson uses Oracle Database 19c. Database, user, and table names below are illustrative examples. Create links and grant privileges only in a lab environment or per system governance procedures.

## 2. Object Naming Structure Over a Database Link

A remote object is typically referenced as:

~~~sql
schema_name.object_name@database_link_name
~~~

Example:

~~~sql
SELECT *
FROM hr.employees@hr_link;
~~~

If the object resides in the remote user's own schema and the table name needs no explicit schema, you can write:

~~~sql
SELECT *
FROM employees@hr_link;
~~~

The schema name before the dot is the schema **in the remote database**, not the current schema in the local database.

A database link is not a table or schema in the remote database. It is a connection object defined in the local database; the part after @ specifies the connection path Oracle uses to locate objects on the remote side.

### 2.1. Testing Connectivity

After creating a link, try querying DUAL on the remote side:

~~~sql
SELECT *
FROM dual@hr_link;
~~~

You can check the remote login identity:

~~~sql
SELECT USER AS remote_user
FROM dual@hr_link;
~~~

Or:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS remote_session_user
FROM dual@hr_link;
~~~

The result shows the user of the remote session. This is a quick way to verify the link connects using the intended identity.

### 2.2. Using Database Links in DML

Database links are not limited to SELECT. Example:

~~~sql
INSERT INTO hr.remote_audit@hr_link
       (event_id, event_text, created_at)
VALUES (1001, 'LOCAL IMPORT', SYSTIMESTAMP);

UPDATE hr.employees@hr_link
SET    salary = salary * 1.05
WHERE  employee_id = 100;

DELETE FROM hr.expired_sessions@hr_link
WHERE  expires_at < SYSDATE;
~~~

The remote account must hold the corresponding INSERT, UPDATE, or DELETE privileges on the remote object. DML over a database link also involves distributed transactions, covered later.

## 3. Two Classification Axes: Private/Public and Connected/Fixed/Current

These are two distinct concepts and should not be conflated.

### 3.1. Link Usage Scope

| Link Type | Who Can Reference It? | Meaning |
| --- | --- | --- |
| Private database link | Schema owner that created the link | The link belongs strictly to the owning schema |
| Public database link | Users in the local database | The link is published at local database scope |

### 3.2. Remote Login Identity

| Authentication Type | Syntax | Remote User Used |
| --- | --- | --- |
| Connected user | No CONNECT TO clause | The user currently connected to the local database |
| Fixed user | CONNECT TO user IDENTIFIED BY password | A fixed remote user declared in the link |
| Current user | CONNECT TO CURRENT_USER | The current user per execution context, subject to Oracle global user authentication |

For example, you can create a private fixed-user link, a public fixed-user link, or a private current-user link. Private/public governs who can use the link object; connected/fixed/current governs which identity the remote session logs in with.

~~~text
LOCAL DATABASE
  |
  +-- Private link: used by schema owner
  |
  +-- Public link: local users can reference
           |
           +-- Connected user: locally connected user's identity
           +-- Fixed user: a declared remote account
           +-- Current user: current global user per context
                    |
                    v
              REMOTE DATABASE
                    |
          Check remote privileges
                    |
           Schema / object / DML
~~~

## 4. Connected User Database Links

### 4.1. Concept

A connected user database link omits user/password in the CONNECT TO clause. Oracle uses the credentials of the user currently connected to the local database to open a session on the remote database.

This means the remote database must recognize the same username and password (or corresponding authentication mechanism) for that user. If local user APP_USER connects through the link, the remote database must also have an APP_USER account able to log in with the required privileges.

### 4.2. Creating a Connected User Link

~~~sql
CREATE DATABASE LINK hr_connected_link
USING 'HRPDB';
~~~

Without CONNECT TO, the link uses the connected user. HRPDB is a connect identifier resolved by the local database server to the remote Oracle service.

### 4.3. Usage

~~~sql
SELECT employee_id, first_name, last_name
FROM hr.employees@hr_connected_link
WHERE department_id = 50;
~~~

The remote database authenticates using the connected user's identity. That remote user must be able to log into the remote database, hold SELECT on HR.EMPLOYEES, and hold any DML privileges needed if SQL executes INSERT, UPDATE, or DELETE.

### 4.4. When to Use

Connected user links fit when users have matching accounts on both local and remote databases, each person should retain their individual identity when accessing remote data, or security policies require remote permissions to depend on the locally authenticated user.

### 4.5. Operational Limitations

If the local user exists but the remote side lacks a matching account or credentials do not match, connections fail. Password management and account lifecycles across both databases must also stay synchronized.

## 5. Fixed User Database Links

### 5.1. Concept

A fixed user database link declares a specific remote username/password. Any local session permitted to use that link connects to the remote database using that fixed identity.

Example:

~~~sql
CREATE DATABASE LINK hr_report_link
CONNECT TO report_reader IDENTIFIED BY "ReplaceWithSecret"
USING 'HRPDB';
~~~

In this example, every use of HR_REPORT_LINK logs into the remote database as REPORT_READER, regardless of which local user executes the SQL (assuming that local user can access the link).

### 5.2. Querying Through a Fixed User Link

~~~sql
SELECT employee_id, first_name, salary
FROM hr.employees@hr_report_link
WHERE department_id = 50;
~~~

The remote database checks REPORT_READER's privileges. If the remote user holds only SELECT on HR.EMPLOYEES, the query can read that table but cannot UPDATE or DELETE from it.

### 5.3. Granting Privileges on the Remote Database

Example executed on the remote database by a DBA or appropriate owner:

~~~sql
CREATE USER report_reader IDENTIFIED BY "ReplaceWithSecret";
GRANT CREATE SESSION TO report_reader;
GRANT SELECT ON hr.employees TO report_reader;
~~~

If the user already exists, omit CREATE USER and grant only the required privileges:

~~~sql
GRANT CREATE SESSION TO report_reader;
GRANT SELECT ON hr.employees TO report_reader;
~~~

If the link needs to update data, the remote account must hold the corresponding DML privileges:

~~~sql
GRANT INSERT, UPDATE, DELETE
ON hr.employee_notes
TO report_writer;
~~~

Never grant DBA, SELECT ANY TABLE, or broad privileges just to make one query work. Use a dedicated remote account with least privilege.

### 5.4. Fixed User Links Can Share a Remote Identity

If a fixed-user link is private, only the schema owner can reference it. If the link is public, many local users can reference the same link and all share the fixed remote account.

This is a critical security distinction:

- A private fixed-user link restricts callers to the schema owner.
- A public fixed-user link opens access through that remote account to many local users.
- Privileges on remote objects remain those of the fixed remote account; they are not narrowed per local user.

Therefore, a public fixed-user link can let many local users leverage broader remote privileges than intended. Publish a link publicly only after evaluating all consumers and the remote account's privileges.

## 6. Current User Database Links

### 6.1. Concept

A current user database link is created with:

~~~sql
CREATE DATABASE LINK hr_current_link
CONNECT TO CURRENT_USER
USING 'HRPDB';
~~~

When the link is used, Oracle uses the current user in the execution context to determine the remote connection identity. Unlike a fixed user link, the link does not hardcode a fixed remote username/password.

Current user database links are intended for Oracle's global user authentication model. The current user must be a global user authenticated via a supported enterprise authentication mechanism (such as directory-based authentication, SSL, or Kerberos as configured). It is not a way to turn an arbitrary local database username into a remote account automatically.

### 6.2. Current User Is Not Synonymous with CURRENT_SCHEMA

Oracle distinguishes these concepts:

- SESSION_USER: the user that logged in and created the database session.
- CURRENT_USER: the active identity/privilege context; inside PL/SQL it can change according to the program unit's execution rights.
- CURRENT_SCHEMA: the schema used to resolve unqualified object names.

ALTER SESSION SET CURRENT_SCHEMA = ... changes only the default schema for finding unqualified objects; it does not re-authenticate to the database or turn that user into a remote authentication identity.

Consequently, a current-user database link must not be misunderstood as "take the currently selected schema and connect remotely as that schema."

### 6.3. Current User in Definer-Rights and Invoker-Rights PL/SQL

PL/SQL execution rights affect the current user:

- Default program units use **definer's rights** (AUTHID DEFINER): privileges are evaluated under the program unit's owner/definer.
- Program units declared with **invoker's rights** (AUTHID CURRENT_USER): privileges are evaluated under the invoker calling the program unit.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE list_remote_employees
AUTHID CURRENT_USER
AS
    l_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM hr.employees@hr_current_link;

    DBMS_OUTPUT.PUT_LINE('Remote employee count: ' || l_count);
END;
/
~~~

In an invoker-rights routine, the caller's current user context is used per Oracle rules. In a definer-rights routine, the current user context is the definer. When designing current-user links inside stored code, verify AUTHID, global identities, and privileges on both databases.

### 6.4. When to Use

Current user links fit when a system uses centrally authenticated enterprise/global users, wants the remote identity to track the actual caller rather than a shared fixed account, requires a remote audit trail tied to real users, and has global authentication and user mappings configured across participating databases.

If the system uses ordinary local database accounts only, fixed-user or connected-user links are usually more appropriate.

## 7. Comparing Connected, Fixed, and Current Users

| Criterion | Connected User | Fixed User | Current User |
| --- | --- | --- | --- |
| CONNECT TO clause | Omitted | Fixed username/password | CURRENT_USER |
| Remote identity | Locally connected user | A remote account configured in the link | Current global user per execution context |
| Remote account requirement | Matching user must be able to log in remotely | Fixed account must exist remotely | Global user must be recognized remotely |
| Password in link | Not specified | Stores fixed user credentials | No fixed password specified |
| Best suited for | Uniform accounts across both DBs | Applications using a scoped service account | Enterprise/global identity and invoker-scoped privileges |
| Primary risk | Account/credential sync across two DBs | Many local users sharing remote privileges if link is public | Depends on global auth setup and execution context |

No link type is automatically secure in every scenario. Choose based on identity model, audit requirements, privilege design, and usage scope.

## 8. Private vs. Public Database Links

### 8.1. Private Database Links

Create a private link:

~~~sql
CREATE DATABASE LINK hr_private_link
CONNECT TO report_reader IDENTIFIED BY "ReplaceWithSecret"
USING 'HRPDB';
~~~

The link belongs to the schema of the user who created it. Other users cannot directly reference that private link merely because they hold SELECT on the remote table.

Private links fit when an application schema needs to connect to a remote database using a privately managed identity.

### 8.2. Public Database Links

Creating a public link requires the CREATE PUBLIC DATABASE LINK system privilege:

~~~sql
CREATE PUBLIC DATABASE LINK hr_public_link
CONNECT TO report_reader IDENTIFIED BY "ReplaceWithSecret"
USING 'HRPDB';
~~~

A public link is published at the local database scope. Local users can reference the link name without owning a private link.

Public does not mean the remote database is open to everyone. The remote database still authenticates via connected/fixed/current user and checks that remote identity's privileges.

### 8.3. Privilege Scope When Combining Public and Fixed User

Suppose HR_PUBLIC_LINK is a public fixed-user link connecting as REPORT_READER.

~~~sql
SELECT *
FROM hr.employees@hr_public_link;
~~~

Both local user A and local user B can execute the statement. The remote database sees both as REPORT_READER because the link uses a fixed user.

Implications:

- Remote audits record the same remote username.
- REPORT_READER's remote privileges apply to both local users.
- Local link access does not filter remote object privileges.
- If REPORT_READER holds broad privileges, any local user able to use the public link can reach that data.

For per-user authorization requirements, consider connected/current user links or private links scoped within appropriate schemas.

### 8.4. Can a Private Database Link Be Granted to Another User?

A private database link is not an object privilege that can be granted like a table or view. If another user needs a connection:

- Create a private link in that user's schema.
- Or have a DBA create a public link after reviewing scope and remote identity.
- Or expose a controlled local API/view/procedure rather than letting multiple schemas access a remote account directly.

Never grant overly broad privileges merely to avoid managing per-schema links.

## 9. Privileges Required on Local and Remote Databases

Database links span two separate privilege systems.

### 9.1. Privileges to Create Links on the Local Database

| Goal | System Privilege |
| --- | --- |
| Create private database link | CREATE DATABASE LINK |
| Create public database link | CREATE PUBLIC DATABASE LINK |
| Drop public database link | DROP PUBLIC DATABASE LINK |

Regular users can create private links if granted CREATE DATABASE LINK. Creating public links requires a separate privilege because public links have wider blast radius.

Example DBA granting private link creation:

~~~sql
GRANT CREATE DATABASE LINK TO app_owner;
~~~

Grant public link creation only to appropriate administrative roles:

~~~sql
GRANT CREATE PUBLIC DATABASE LINK TO db_admin_role;
~~~

### 9.2. Login and Object Privileges on the Remote Database

The remote user needs session creation privilege:

~~~sql
GRANT CREATE SESSION TO report_reader;
~~~

Then grant minimal object privileges:

~~~sql
GRANT SELECT ON hr.employees TO report_reader;
GRANT SELECT ON hr.departments TO report_reader;
~~~

If DML is required:

~~~sql
GRANT INSERT, UPDATE ON hr.employee_notes TO report_writer;
~~~

The remote account does not need DBA privileges. A read-only reporting account should receive only CREATE SESSION and SELECT on the required objects.

### 9.3. Local Users Do Not Inherit Remote Privileges Automatically

Suppose local user APP_USER has SELECT on a local view. If the view queries a remote table over a fixed-user link, remote privileges are still evaluated under the link's remote identity.

Conversely, granting a local user SELECT on a remote table locally does not automatically grant that privilege to the remote account. Both privilege sets must be managed explicitly.

### 9.4. Privileges in Stored Program Units

Stored procedures, functions, and packages can execute under definer's rights or invoker's rights. Local and remote object access must be designed alongside AUTHID and link identity.

For objects referenced inside stored code, grant necessary object privileges directly to the appropriate owner/invoker rather than relying loosely on roles. Verify Oracle's privilege rules for the specific program unit type before deployment.

## 10. Creating a Database Link: End-to-End Local to Remote Flow

### 10.1. Prepare the Connect Identifier

The USING clause specifies a connect string or net service name so the local database server can locate the remote service.

Example:

~~~sql
USING 'HRPDB'
~~~

HRPDB must be configured and resolvable on the local database server host (for example via Oracle Net naming/TNS configuration), not merely on a client workstation running SQL Developer.

If a DBA provides a full connect descriptor, an appropriate connect string can replace the alias:

~~~sql
USING '(DESCRIPTION=
  (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost.example.com)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=hrpdb.example.com))
)'
~~~

Never place passwords inside the connect descriptor. Authentication credentials belong in CONNECT TO or configured authentication mechanisms.

### 10.2. Create a Private Fixed-User Link

Run in the local database as a schema owner holding CREATE DATABASE LINK:

~~~sql
CREATE DATABASE LINK hr_report_link
CONNECT TO report_reader IDENTIFIED BY "ReplaceWithSecret"
USING 'HRPDB';
~~~

In real environments, use organization-managed secrets and secure deployment pipelines. Never store real passwords in source code, shared scripts, tickets, or study materials.

### 10.3. Verify

~~~sql
SELECT USER AS remote_user
FROM dual@hr_report_link;

SELECT employee_id, first_name
FROM hr.employees@hr_report_link
WHERE ROWNUM <= 5;
~~~

If the identity check returns REPORT_READER and the remote query succeeds, the link connects with the expected remote identity.

### 10.4. Create a Local Synonym (Optional)

To avoid typing long link suffixes in every query:

~~~sql
CREATE SYNONYM remote_employees
FOR hr.employees@hr_report_link;
~~~

Then you can query:

~~~sql
SELECT employee_id, first_name
FROM remote_employees;
~~~

A synonym is only an object name alias. It does not change remote identity or grant additional access privileges.

## 11. Managing and Inspecting Database Links

Oracle provides data dictionary views:

| View | Scope |
| --- | --- |
| USER_DB_LINKS | Database links owned by the current schema |
| ALL_DB_LINKS | Database links accessible to the current user per view rules |
| DBA_DB_LINKS | All database links in the database; requires appropriate privileges |

Example:

~~~sql
SELECT db_link,
       username,
       host,
       created
FROM user_db_links
ORDER BY db_link;
~~~

DBAs can inspect:

~~~sql
SELECT owner,
       db_link,
       username,
       host,
       created
FROM dba_db_links
ORDER BY owner, db_link;
~~~

These views display link names, remote usernames, and host/connection info according to visibility privileges. Do not treat them as a way to extract or recover passwords.

### 11.1. Check the Database Global Name

~~~sql
SELECT *
FROM global_name;
~~~

When GLOBAL_NAMES is enabled, the database link name must match the remote database's global database name per Oracle rules. DBAs can check the setting:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'global_names';
~~~

Accessing V$PARAMETER requires appropriate privileges. Do not disable GLOBAL_NAMES merely to make an improperly named link work; confirm the system's naming convention.

### 11.2. Dropping a Private Link

The owner of a private link can drop it:

~~~sql
DROP DATABASE LINK hr_report_link;
~~~

### 11.3. Dropping a Public Link

A DBA or appropriately privileged user can drop a public link:

~~~sql
DROP PUBLIC DATABASE LINK hr_public_link;
~~~

Dropping a database link does not delete tables or data on the remote database. It removes only the connection object on the local database.

### 11.4. Remote Password Changes

If the remote account changes its password, a fixed-user database link storing the old credential can no longer connect. Update or recreate the link via approved procedures, and verify applications and stored objects depending on the link.

Never print new passwords to logs or terminal output. Follow organizational secret management and credential rotation processes.

## 12. Authorization and Security Boundaries

A database link forms a security boundary between two databases. Privilege design must account for both local users and remote identities.

### 12.1. Public Link Does Not Mean Public Remote Data

A public database link only makes the link name referenceable by multiple local users. The remote database still validates the remote username and privileges.

However, a public fixed-user link lets many local users share one remote account. If that account has SELECT on sensitive data, every local user able to invoke the link gains a path to that data.

### 12.2. Use Least-Privilege Remote Accounts

A reporting account needing to read only two tables:

~~~sql
GRANT CREATE SESSION TO report_reader;
GRANT SELECT ON hr.employees TO report_reader;
GRANT SELECT ON hr.departments TO report_reader;
~~~

Do not grant access to payroll tables, personal identifiers, or other data the report does not need.

### 12.3. Never Use Administrative Accounts as Fixed Users

Never configure links using SYS, SYSTEM, or broadly privileged DBA accounts. If the link is misused, the blast radius is severe.

### 12.4. Audits Must Distinguish Local and Remote Users

With a fixed-user link, remote audits see only the fixed account. If you must track which local user initiated an action, add local auditing or pass controlled application context/tags; do not assume the remote database automatically identifies local users.

Connected/current user links preserve individual identities better, provided authentication and user mapping are properly architected.

### 12.5. Protect Transit and Credentials

- Enable Oracle Net encryption or TLS per system policy.
- Restrict hosts/services that links are allowed to reach.
- Manage passwords and rotation through secure processes.
- Prevent untrusted users from holding public link creation privileges.
- Monitor creation, modification, and deletion of database links.
- Audit remote grants periodically.

## 13. Distributed Transactions for DML Over Database Links

A SELECT from a remote database is a distributed query. When a transaction updates data across multiple databases, Oracle coordinates a distributed transaction.

Example:

~~~sql
UPDATE local_orders
SET status = 'SENT'
WHERE order_id = 1001;

INSERT INTO remote_audit@hr_link
       (event_id, event_text)
VALUES (1001, 'ORDER SENT');

COMMIT;
~~~

This transaction affects both the local and remote databases. Oracle uses **two-phase commit (2PC)** to coordinate commits:

1. **Prepare phase:** the coordinator asks participants to prepare to commit and guarantee they can finish.
2. **Commit phase:** once participants are ready, the coordinator issues the commit decision.

The goal is preventing a split state where local commits while remote rolls back (or vice versa) in a properly managed distributed transaction.

### 13.1. COMMIT and ROLLBACK

When a transaction contains both local and remote DML:

- COMMIT drives the distributed transaction to completion per the 2PC protocol.
- ROLLBACK cancels uncommitted changes across the distributed transaction.
- Never attempt partial commits if business logic requires local and remote updates to succeed atomically.

### 13.2. In-Doubt Transactions

If a database or network fails during commit coordination, a distributed transaction can enter an in-doubt state. DBAs can investigate using views such as:

~~~sql
SELECT *
FROM dba_2pc_pending;
~~~

and:

~~~sql
SELECT *
FROM dba_2pc_neighbors;
~~~

These administrative views require appropriate privileges. Never manually purge or force commit/rollback an in-doubt transaction without verifying the coordinator and participant state; DBAs must follow recovery procedures.

### 13.3. Application Design When Remote Databases Lose Connectivity

An operation over a database link can fail due to remote database downtime, network outages, unavailable listeners/services, expired/changed credentials, locked remote accounts, or remote lock waits.

Applications must define whether operations can be retried safely. For DML, design idempotency keys or business keys so retries do not create duplicate records.

## 14. Example Combining Local and Remote Data

Suppose the local database stores orders and the remote database stores customer details. We need a report of total order amount per customer:

~~~sql
SELECT c.customer_id,
       c.customer_name,
       SUM(o.order_total) AS total_amount
FROM crm.customers@crm_link c
JOIN local_orders o
  ON o.customer_id = c.customer_id
WHERE o.order_date >= DATE '2026-01-01'
GROUP BY c.customer_id, c.customer_name
ORDER BY total_amount DESC;
~~~

The query combines data from two databases. Oracle may push part of the processing to the remote database or pick another execution strategy depending on the optimizer, statistics, network, and query shape. Do not assume all remote rows are pulled locally before filtering, nor assume the optimizer always pushes predicates optimally.

When remote datasets are large:

- Filter early on the remote side when appropriate.
- Select only required columns.
- Avoid pulling entire tables across the network.
- Inspect execution plans and row counts transferred over the link.
- Consider materialized views or ETL if cross-database queries are frequent and high-volume.

### 14.1. Local View Over Remote Data

~~~sql
CREATE OR REPLACE VIEW v_remote_employees AS
SELECT employee_id, first_name, department_id
FROM hr.employees@hr_link;
~~~

Views encapsulate remote names and query logic. However, a view does not alter the link's remote identity; remote privileges are still evaluated under the link's user; local privileges to query the view must still be granted; and if the remote schema changes or the link breaks, dependent views fail too.

## 15. GLOBAL_NAMES and Database Link Names

Oracle provides the GLOBAL_NAMES parameter to require database link names to match the remote database's global database name.

Example:

~~~sql
SELECT *
FROM global_name;
~~~

Suppose the remote global name is:

~~~text
HRPDB.EXAMPLE.COM
~~~

When GLOBAL_NAMES = TRUE, the link name must align with this global name per Oracle naming rules. Mismatched link names can raise:

~~~text
ORA-02085: database link ... connects to ...
~~~

In multi-database environments, DBAs often enforce link naming standards to clearly identify targets and domains. Do not disable GLOBAL_NAMES casually, as it serves as a naming and routing safeguard.

## 16. Common Errors

| Error | Possible Cause | Resolution |
| --- | --- | --- |
| ORA-12154 | Cannot resolve connect identifier in USING | Check Oracle Net naming on the local database server |
| ORA-12514 | Listener does not know requested service | Check SERVICE_NAME and remote listener |
| ORA-01017 | Invalid remote username/password or auth failure | Check fixed/connected identity and account status |
| ORA-02019 | Connection description for remote database not found | Check link, USING clause, and Oracle Net config |
| ORA-02085 | Link name does not match global name when GLOBAL_NAMES is on | Check GLOBAL_NAME and database link name |
| ORA-00942 | Remote object missing, wrong schema, or remote user lacks privileges | Check schema.object and grant proper object privileges |
| ORA-01031 | Missing privilege to create link or access remote/local object | Check local system privileges and remote privileges |
| ORA-02049 | Distributed transaction timed out waiting for lock | Check blocking remote transactions and timeout |
| ORA-02068 | Severe error forwarded from remote database over link | Inspect subsequent remote error in stack and fix remotely |
| ORA-02055 | Distributed update failed and transaction must roll back | ROLLBACK at transaction boundary and investigate root error |
| Slow query | Excessive rows transferred over network or poor remote plan | Filter early, project needed columns, inspect execution plan |
| Public link exposes remote identity too broadly | Public link uses an overly privileged fixed account | Restrict link, narrow remote grants, consider user-specific identities |
| Local user cannot use another schema's private link | Private links belong to their owning schema | Create a separate link or use a governed API/public link |

## 17. Self-Contained Lab Exercises

The steps below require two independent Oracle databases or two PDBs/services you administer. Names like LOCALDB, HRPDB, users, and passwords are examples only. Never use production accounts or passwords.

### Exercise A — Create Remote User and Grant Privileges

On the remote database, as a DBA or privileged user:

~~~sql
CREATE USER report_reader IDENTIFIED BY "LabOnlyPassword";
GRANT CREATE SESSION TO report_reader;
GRANT SELECT ON hr.employees TO report_reader;
~~~

If the user already exists, omit CREATE USER and grant only the required privileges.

### Exercise B — Create a Private Fixed-User Link

On the local database, in a lab setup:

~~~sql
GRANT CREATE DATABASE LINK TO app_owner;
~~~

Then as APP_OWNER:

~~~sql
CREATE DATABASE LINK hr_report_link
CONNECT TO report_reader IDENTIFIED BY "LabOnlyPassword"
USING 'HRPDB';
~~~

Verify:

~~~sql
SELECT USER FROM dual@hr_report_link;

SELECT COUNT(*)
FROM hr.employees@hr_report_link;
~~~

The expected remote user is REPORT_READER.

### Exercise C — Compare Private and Public

A DBA can create a public fixed-user link in the lab environment:

~~~sql
GRANT CREATE PUBLIC DATABASE LINK TO db_admin_role;
~~~

Then:

~~~sql
CREATE PUBLIC DATABASE LINK hr_public_link
CONNECT TO report_reader IDENTIFIED BY "LabOnlyPassword"
USING 'HRPDB';
~~~

Log in as another local user and test:

~~~sql
SELECT USER
FROM dual@hr_public_link;
~~~

Observe that multiple local users can reference the public link while the remote session still runs as REPORT_READER. Drop the public link after finishing the exercise.

### Exercise D — Connected User Link

Create a user with identical name and credentials on both local and remote databases, granting CREATE SESSION remotely and SELECT on the target table. Then as the local user:

~~~sql
CREATE DATABASE LINK hr_connected_link
USING 'HRPDB';

SELECT USER
FROM dual@hr_connected_link;
~~~

Observe that the remote identity matches the connected user. If usernames/passwords mismatch or the remote account does not exist, authentication fails.

### Exercise E — Current User Link

Perform this only when the lab system has global users and enterprise authentication configured:

~~~sql
CREATE DATABASE LINK hr_current_link
CONNECT TO CURRENT_USER
USING 'HRPDB';

SELECT USER
FROM dual@hr_current_link;
~~~

Test within definer-rights and invoker-rights PL/SQL contexts if permitted. Compare remote identities by current user context. Do not substitute local schema names or ALTER SESSION SET CURRENT_SCHEMA for this exercise.

### Exercise F — Dictionary Views

~~~sql
SELECT db_link, username, host, created
FROM user_db_links;
~~~

With DBA privileges:

~~~sql
SELECT owner, db_link, username, host, created
FROM dba_db_links
ORDER BY owner, db_link;
~~~

Identify which links are private, which are public, and which remote usernames are configured.

### Exercise G — DML and Distributed Transactions

In the lab schema, create a remote audit table and grant INSERT to the remote account. Then test a transaction spanning both local and remote DML:

~~~sql
INSERT INTO local_audit_lab (event_id, event_text)
VALUES (9001, 'LOCAL');

INSERT INTO hr.remote_audit_lab@hr_report_link
       (event_id, event_text)
VALUES (9001, 'REMOTE');

COMMIT;
~~~

Query both databases to reconcile. Then test ROLLBACK instead of COMMIT in another transaction and inspect both sides.

## 18. Database Link Design Checklist

1. **What is the remote database/service?** Confirm host, port, service name, and connect identifier.
2. **Which schema owns the link?** Default to private if only one schema needs access.
3. **Is public truly required?** Public allows broad local users to reference the link.
4. **Which remote identity fits?** Connected, fixed, or current user.
5. **Does the remote user have least privilege?** Grant only CREATE SESSION and required object privileges.
6. **Could a fixed account be shared unintentionally?** Scrutinize public fixed-user links closely.
7. **Is current user a properly authenticated global user?** Never confuse it with CURRENT_SCHEMA.
8. **What AUTHID does stored code use?** Check current user/definer/invoker context.
9. **Can individual callers be audited?** Fixed users may cause remote audits to show only one shared account.
10. **Does DML span multiple databases?** Account for distributed transactions and two-phase commit.
11. **Are retry/idempotency mechanisms in place?** Prevent duplicate writes on network or remote failures.
12. **Are synonyms/views needed?** They encapsulate names but do not grant privileges.
13. **Is GLOBAL_NAMES enabled?** Name links according to convention.
14. **How are credentials managed?** Keep passwords out of code and logs; enforce rotation procedures.
15. **Have dictionary views and live connectivity been verified?** Test USER@link and object queries before releasing to applications.

## 19. Self-Check Questions

**Question 1.** In which database is a database link created?

**Question 2.** What is the syntax for referencing a remote table?

**Question 3.** How do private and public database links differ?

**Question 4.** Where does a connected user link obtain its remote identity?

**Question 5.** Which user does a fixed user link connect as?

**Question 6.** Does a current user link use CURRENT_SCHEMA to determine the remote identity?

**Question 7.** Which authentication model does a current user database link require?

**Question 8.** If a public link is a fixed-user link, can multiple local users share that remote account?

**Question 9.** Does a public link automatically grant SELECT on remote tables to all local users?

**Question 10.** Is the CREATE DATABASE LINK privilege granted on the local or remote database?

**Question 11.** What privileges does a remote user need to log in and read a table?

**Question 12.** How do USER_DB_LINKS and DBA_DB_LINKS differ?

**Question 13.** Do database links support remote INSERT/UPDATE/DELETE?

**Question 14.** Why do local and remote DML in the same transaction involve two-phase commit?

**Question 15.** Does creating a synonym over a remote table change the remote identity?

<details>
<summary>Suggested answers</summary>

1. The local database; the link is stored in a local schema or local public scope.
2. SCHEMA_NAME.OBJECT_NAME@DATABASE_LINK_NAME.
3. Private belongs only to the schema owner; public can be referenced by many local users.
4. From the user currently connected to the local database; the remote database needs a matching account/authentication.
5. The fixed remote username declared in CONNECT TO.
6. No. CURRENT_SCHEMA only changes the default schema for resolving local unqualified object names.
7. Oracle-supported and properly configured global user/enterprise authentication.
8. Yes. Any user allowed to invoke the public link connects remotely using that fixed remote identity.
9. No. The remote database still checks the remote account's privileges; public only widens link visibility.
10. Local database.
11. CREATE SESSION and object privileges such as SELECT on the table to read.
12. USER_DB_LINKS lists links owned by the current schema; DBA_DB_LINKS lists all links across the database with DBA privileges.
13. Yes, provided the remote identity holds DML privileges and transactions are handled properly.
14. Because commit must coordinate participants across multiple databases to maintain distributed consistency.
15. No. A synonym is strictly an object name alias.

</details>

## 20. Official Oracle Documentation

1. [Oracle Database 19c SQL Language Reference — CREATE DATABASE LINK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-DATABASE-LINK.html): syntax for creating private/public links, connected/fixed/current users, and connect strings.
2. [Oracle Database 19c SQL Language Reference — DROP DATABASE LINK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DROP-DATABASE-LINK.html): dropping private and public database links.
3. [Oracle Database 19c Administrator's Guide — Managing a Distributed Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-a-distributed-database.html): database links, distributed queries, distributed transactions, and network configuration.
4. [Oracle Database 19c Concepts — Distributed Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/distributed-database-concepts.html): distributed database architecture and access models.
5. [Oracle Database 19c SQL Language Reference — CREATE SYNONYM](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-SYNONYM.html): synonyms and referencing objects over database links.
6. [Oracle Database 19c Reference — USER_DB_LINKS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_DB_LINKS.html): user-owned database link dictionary view.
7. [Oracle Database 19c Reference — DBA_DB_LINKS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DB_LINKS.html): administrative database link dictionary view.
8. [Oracle Database 19c PL/SQL Language Reference — Invoker's Rights and Definer's Rights](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights-authid-property.html): AUTHID, current user, and privilege context for stored program units.

**Key takeaway:** private/public answers who may reference a database link; connected/fixed/current user answers which identity the remote database sees. Remote table privileges are evaluated under the remote identity, never automatically granted simply because local users can see the link. Default to private links and least-privilege remote accounts; use public fixed-user links only after assessing credential and privilege sharing risks. Current-user links are designed for global user authentication and require understanding PL/SQL current user context rather than confusing it with CURRENT_SCHEMA. When running DML across databases, design distributed transaction handling and retries deliberately.
