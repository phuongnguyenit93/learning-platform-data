# Periodic privilege reviews, dormant accounts, and PUBLIC access

In Oracle Database, security does not stop at creating users and granting roles during application deployment. Over time, personnel change, old services are replaced, projects end, temporary privileges are not revoked, and new objects may be granted to `PUBLIC`. Without reviews, a database accumulates ownerless accounts, privileges broader than needed, and access paths whose purpose no one remembers.

A sound security process periodically reviews **accounts**, **roles**, **system privileges**, **object privileges**, **privileges granted to PUBLIC**, **inactive accounts**, and **audit evidence**. The goal is knowing which identities can access which data, whether through direct or inherited grants, why those privileges exist, and who owns them.

In Oracle, `PUBLIC` is a pseudo-role implicitly granted to every database user. Consequently, privileges granted to `PUBLIC` have very broad reach: every existing user and every future user created later inherits those privileges. This is one of the primary areas requiring attention during periodic privilege reviews.

## 1. Why conduct periodic privilege reviews?

Database privileges shift continuously across an application's lifecycle:

- A developer receives production support privileges during an incident, and those privileges are never revoked.
- A legacy service is retired, yet its user and password remain active.
- A deployment account is granted `CREATE ANY TABLE` or broad rights and then reused as a runtime account.
- A new package or view is granted `EXECUTE`/`SELECT` to `PUBLIC` as a quick fix for an access error.
- A role is granted to another user, and later additional system privileges are added to that role.
- An account belonging to a departed employee remains `OPEN`.
- A user has not logged in interactively for a long time, yet is still used by a scheduled batch job.

Inspecting only the user list misses role-inherited privileges, `PUBLIC` grants, and active sessions under service accounts. Inspecting only direct grants misses privileges coming through nested roles or `ANY`-scoped system privileges.

Periodic reviews help:

1. Revoke privileges no longer needed.
2. Lock ownerless or unused accounts.
3. Detect shared accounts or uncontrolled privileged accounts.
4. Detect objects granted to `PUBLIC` beyond legitimate requirements.
5. Reduce unauthorized access blast radius if credentials leak.
6. Provide evidence for audits and incident investigations.
7. Keep database privileges aligned with current application architecture.

Reviews should run on an organizational schedule and after major events such as major releases, personnel changes, database migrations, project closures, or credential exposures. There is no single cadence suited to every system; frequency should reflect data sensitivity and governance policy.

## 2. Understanding PUBLIC in Oracle

`PUBLIC` is a special pseudo-role implicitly granted by Oracle to every user. There is no `GRANT PUBLIC TO user`; every user automatically holds privileges granted to `PUBLIC`.

Example:

~~~sql
GRANT SELECT ON app_owner.public_reference_codes TO PUBLIC;
~~~

After this statement, every database user can exercise `SELECT` on that object, including existing users and future users. This privilege is not scoped by application schema or user group.

`PUBLIC` is not an ordinary database account:

- It has no password for logging in.
- It owns no separate session.
- It does not represent a user group managed via ordinary role membership.
- Privileges granted to `PUBLIC` take effect for all users under Oracle's special role mechanism.

### PUBLIC vs. regular roles

Regular roles are created and granted to users or other roles. Administrators can configure default roles, enable/disable roles in a session, or revoke a role from a user. `PUBLIC` differs in that it always applies to every user.

Therefore, when a privilege is granted to `PUBLIC`, you cannot fix it merely by revoking a role from one user. You must inspect grants where `grantee = 'PUBLIC'` and revoke the grant itself if no valid justification remains.

### PUBLIC grants are not PUBLIC synonyms

`PUBLIC` synonyms and privileges granted to `PUBLIC` are two different concepts:

- A `PUBLIC` synonym provides a shared name to reference an object.
- Object privileges determine whether a user may read, write, or execute that object.

Creating a `PUBLIC` synonym does not automatically grant access to the target object. Conversely, granting `SELECT` or `EXECUTE` to `PUBLIC` allows every user to access the object even when referencing `schema.object` directly instead of the synonym.

During reviews, inspect both `PUBLIC` grants and `PUBLIC` synonyms, without mistaking a synonym for an access privilege.

## 3. Types of privileges to review

Oracle has multiple privilege layers. A complete review should examine at least:

| Category | Common view | Contents |
|---|---|---|
| Direct system privileges | `DBA_SYS_PRIVS` | Privileges like `CREATE SESSION`, `SELECT ANY TABLE`, `ALTER USER` |
| Roles granted to users/roles | `DBA_ROLE_PRIVS` | Relationships between grantee and `granted_role`, `ADMIN_OPTION`, `DEFAULT_ROLE` |
| Object privileges | `DBA_TAB_PRIVS` | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `EXECUTE`, and object grants |
| Column privileges | `DBA_COL_PRIVS` | Privileges granted on specific columns |
| System privileges on roles | `DBA_SYS_PRIVS` | System privileges granted to roles |
| Object privileges on roles | `DBA_TAB_PRIVS` | Object privileges granted to roles |
| Privileges active in session | `SESSION_PRIVS`, `SESSION_ROLES` | Privileges and roles active in the current session |
| Users/accounts | `DBA_USERS` | Account status, profile, creation date, and authentication attributes |
| Current sessions | `V$SESSION` | Connected users, programs, modules, status, and logon times |

`DBA_*` views typically require administrative privileges or appropriate dictionary read privileges. Without those privileges, use `USER_*` or `ALL_*` within permitted scope, or ask a DBA to run the queries and supply results.

Never deduce effective privileges from a single view alone. A user can receive the same privilege from multiple sources: direct grants, directly granted roles, nested roles, `PUBLIC`, or broad system privileges.

## 4. Inventorying users and account statuses

`DBA_USERS` is the starting point for listing accounts:

~~~sql
SELECT username,
       account_status,
       created,
       lock_date,
       expiry_date,
       profile,
       authentication_type,
       common,
       oracle_maintained
  FROM dba_users
 ORDER BY username;
~~~

Key columns:

- `USERNAME`: user name.
- `ACCOUNT_STATUS`: statuses like `OPEN`, `LOCKED`, `EXPIRED`, or combined states.
- `CREATED`: account creation timestamp.
- `LOCK_DATE`: lock timestamp if locked.
- `EXPIRY_DATE`: password expiration date if applicable.
- `PROFILE`: profile assigned to the account.
- `AUTHENTICATION_TYPE`: authentication method, such as `PASSWORD` or `EXTERNAL` per configuration.
- `COMMON`: indicates whether the user is common or local in a multitenant environment.
- `ORACLE_MAINTAINED`: indicates accounts supplied and maintained by Oracle on versions supporting this column.

`ORACLE_MAINTAINED` and certain other columns depend on version. On older databases lacking a column, adjust the `SELECT` list to match that release's data dictionary.

To focus on non-Oracle-maintained users on versions with `ORACLE_MAINTAINED`:

~~~sql
SELECT username,
       account_status,
       created,
       lock_date,
       profile,
       authentication_type
  FROM dba_users
 WHERE oracle_maintained = 'N'
 ORDER BY created;
~~~

Never bulk-delete or bulk-lock accounts based solely on username or account age. Classify accounts first by whether they belong to applications, humans, tools, integrations, monitoring, or Oracle itself.

## 5. Finding inactive accounts

An account with `ACCOUNT_STATUS = OPEN` is not necessarily still needed. Conversely, an account without recent logins is not automatically abandoned: a batch job might run monthly, a standby service account might activate only on failover, or an account might serve period-end processing.

### Using LAST_LOGIN when supported by the version

Some Oracle versions provide `LAST_LOGIN` in `DBA_USERS` recording the most recent login. Inspect it:

~~~sql
SELECT username,
       account_status,
       created,
       last_login,
       profile,
       authentication_type
  FROM dba_users
 WHERE oracle_maintained = 'N'
 ORDER BY last_login NULLS FIRST;
~~~

`LAST_LOGIN` may not exist in older releases, and not all authentication types populate it identically. `NULL` does not automatically mean the user was never used or can be dropped. Cross-check with audits, sessions, batch schedules, and application owners.

### Inspecting currently connected sessions

`V$SESSION` helps identify accounts with active sessions:

~~~sql
SELECT username,
       status,
       logon_time,
       machine,
       program,
       module,
       service_name,
       sql_id
  FROM v$session
 WHERE username IS NOT NULL
 ORDER BY username, logon_time;
~~~

This view shows only sessions present at query time. It does not show full account history. A user without a session during inspection may still be used by jobs or applications at other times.

### Combining multiple evidence sources

Before marking an account unused, check:

- `LAST_LOGIN` if available.
- Audit trail over a suitable timeframe.
- Active sessions and connection pools.
- Scheduler jobs and related job classes.
- Database links or external authentication.
- Application config docs, secret managers, and deployment pipelines.
- Business owners and service maintainers.
- Month-end, quarter-end, year-end batch schedules, or standby tasks.
- Package, procedure, view, synonym, and integration dependencies.

An account may never log in directly yet still own a schema containing critical objects. Locking or dropping an owner improperly can break applications even if that account is never used for runtime connections.

## 6. Finding roles and directly granted privileges

### System privileges

~~~sql
SELECT grantee,
       privilege,
       admin_option
  FROM dba_sys_privs
 ORDER BY grantee, privilege;
~~~

Focus on broad-scope privileges:

~~~sql
SELECT grantee,
       privilege,
       admin_option
  FROM dba_sys_privs
 WHERE privilege LIKE '%ANY%'
    OR privilege IN (
         'DBA',
         'ALTER USER',
         'CREATE USER',
         'DROP USER',
         'GRANT ANY PRIVILEGE',
         'GRANT ANY ROLE'
       )
 ORDER BY grantee, privilege;
~~~

This list is a starting point, not an exhaustive catalog of sensitive privileges. Review actual privileges against the release and the user's duties.

### Roles granted to users or other roles

~~~sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role
  FROM dba_role_privs
 ORDER BY grantee, granted_role;
~~~

`ADMIN_OPTION` indicates whether the grantee can further grant the role to others. `DEFAULT_ROLE` indicates whether the role is enabled by default on login. Nested role grants can form multi-tier privilege chains.

### Object privileges

~~~sql
SELECT grantee,
       owner,
       table_name,
       privilege,
       grantable
  FROM dba_tab_privs
 ORDER BY grantee, owner, table_name, privilege;
~~~

`GRANTABLE` indicates whether the recipient can pass on the object privilege within granted scope.

### Column privileges

~~~sql
SELECT grantee,
       owner,
       table_name,
       column_name,
       privilege,
       grantable
  FROM dba_col_privs
 ORDER BY grantee, owner, table_name, column_name;
~~~

Reviewing column privileges is especially helpful when a user should update only certain sensitive columns or reference only a designated column.

## 7. Accounting for nested roles and effective privileges

If `APP_RUNTIME` is granted `APP_RUNTIME_ROLE`, and `APP_RUNTIME_ROLE` is granted `DATA_READ_ROLE`, privileges from `DATA_READ_ROLE` can become effective through the role chain, depending on role state and execution context.

Trace the role hierarchy starting from a user using a hierarchical query:

~~~sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role,
       LEVEL AS role_depth
  FROM dba_role_privs
 START WITH grantee = 'APP_RUNTIME'
 CONNECT BY NOCYCLE PRIOR granted_role = grantee
 ORDER BY role_depth, grantee, granted_role;
~~~

Replace `APP_RUNTIME` with the user under review. This query follows directly granted roles and roles granted to parent roles. `PUBLIC` is an implicitly applied pseudo-role, so grants to `PUBLIC` must be reviewed separately.

To inspect active privileges in the current session, query:

~~~sql
SELECT * FROM session_roles;

SELECT * FROM session_privs;
~~~

These two views are useful when logged in as the user being audited. They are not a comprehensive report of every potentially enableable privilege or every grant path across the database.

### Definer-rights PL/SQL is a special case

Inside named definer-rights PL/SQL units, regular roles are disabled per Oracle rules. Static SQL inside the unit requires direct grants to the owner. Therefore, when reviewing a package owner's privileges, distinguish:

- Privileges a user has in an interactive session.
- Privileges granted via roles.
- Direct grants required by stored units to compile and run.

Never grant broad privileges just because a package hits insufficient privileges. Identify the accessed object and grant the targeted direct privilege to the owner if justified.

## 8. Reviewing privileges granted to PUBLIC

This is a focal area because a single grant to `PUBLIC` opens access to every database user.

### System privileges granted to PUBLIC

~~~sql
SELECT grantee,
       privilege,
       admin_option
  FROM dba_sys_privs
 WHERE grantee = 'PUBLIC'
 ORDER BY privilege;
~~~

Each row is a system privilege granted to `PUBLIC`. Closely examine privileges permitting object creation, broad data access, or further privilege delegation. Do not assume every `PUBLIC` grant is wrong; some may be required by Oracle or installed products. Determine owner, origin, purpose, and impact before revoking.

### Object privileges granted to PUBLIC

~~~sql
SELECT owner,
       table_name,
       privilege,
       grantable
  FROM dba_tab_privs
 WHERE grantee = 'PUBLIC'
 ORDER BY owner, table_name, privilege;
~~~

Objects warranting close attention:

- Tables or views containing business data.
- Packages/functions capable of reading files, accessing the network, executing dynamic SQL, or performing system operations.
- Objects belonging to application or integration schemas.
- Directory objects and objects able to access data outside the database.
- Custom objects granted to `PUBLIC` for convenience.

Several Oracle-supplied packages have `EXECUTE` granted to `PUBLIC` by product design. Never bulk-revoke solely because an object belongs to `SYS` or sounds sensitive. Improper revokes can break components, utilities, or database features. Consult Oracle documentation and verify dependencies.

### Column privileges granted to PUBLIC

~~~sql
SELECT owner,
       table_name,
       column_name,
       privilege,
       grantable
  FROM dba_col_privs
 WHERE grantee = 'PUBLIC'
 ORDER BY owner, table_name, column_name, privilege;
~~~

Column privileges must also be reviewed because a single column can hold personal details, identifiers, or sensitive values. Check both table-level and column-level grants.

### Why are PUBLIC grants dangerous?

Suppose `APP_OWNER.PAYROLL` stores employee salaries:

~~~sql
GRANT SELECT ON app_owner.payroll TO PUBLIC;
~~~

Every user can query the table under this grant. Even a user created solely to run a simple batch job can read `PAYROLL` if able to connect to the database.

If a package with broad execution privileges is granted to `PUBLIC`, every user can invoke it. Thus, `PUBLIC` reviews must evaluate both the direct privilege and the behavior of the exposed object.

## 9. Finding PUBLIC synonyms and public database links

`PUBLIC` synonyms make object names easily referenceable across schemas:

~~~sql
SELECT synonym_name,
       table_owner,
       table_name,
       db_link
  FROM dba_synonyms
 WHERE owner = 'PUBLIC'
 ORDER BY synonym_name;
~~~

A `PUBLIC` synonym does not itself grant privileges on the target object. However, synonyms make objects easier to discover and invoke once users hold corresponding privileges. Identify which synonyms are application-created, Oracle-created, and unused.

Public database links must be reviewed separately:

~~~sql
SELECT owner,
       db_link,
       username,
       host
  FROM dba_db_links
 WHERE owner = 'PUBLIC'
 ORDER BY db_link;
~~~

A `PUBLIC` database link can be used by any user per link privileges and configuration. If the link stores fixed credentials, evaluate remote privileges, credentials, target host, and accessible data scope. Never share link passwords or sensitive details in review reports.

Never drop synonyms or database links based solely on name. Check dependencies in code, jobs, views, packages, and application configs first.

## 10. Distinguishing application-created grants from Oracle-managed grants

A database contains many system-schema objects and `PUBLIC` grants created during installation or component configuration. Some grants are essential for the database or features to function properly.

Before revoking a grant:

1. Identify the owner and object.
2. Determine whether the object belongs to an Oracle-maintained schema.
3. Locate documentation for the component or feature using the object.
4. Check application and package dependencies.
5. Determine whether the grant came from install scripts, applications, or manual changes.
6. Test in an equivalent test environment.
7. Prepare a rollback plan and verify functionality after revoking.

On supported releases, `DBA_OBJECTS` provides `ORACLE_MAINTAINED` to help identify Oracle-supplied objects. This column is a classification signal, not a substitute for reading documentation and checking dependencies.

Example listing objects granted to `PUBLIC` with owner metadata:

~~~sql
SELECT p.owner,
       p.table_name,
       p.privilege,
       o.oracle_maintained,
       o.object_type,
       o.status
  FROM dba_tab_privs p
  LEFT JOIN dba_objects o
    ON o.owner = p.owner
   AND o.object_name = p.table_name
 WHERE p.grantee = 'PUBLIC'
 ORDER BY p.owner, p.table_name, p.privilege;
~~~

Some object privileges may apply to objects without a direct one-to-one row in `DBA_OBJECTS` under this simple join, or metadata may vary by object type. Use this query as an initial investigative inventory, not exhaustive proof of dependencies.

## 11. Reviewing broad privileges and delegable privileges

The following privileges require close scrutiny:

- `SELECT ANY TABLE`, `READ ANY TABLE`.
- `INSERT ANY TABLE`, `UPDATE ANY TABLE`, `DELETE ANY TABLE`.
- `EXECUTE ANY PROCEDURE`.
- `CREATE ANY PROCEDURE`, `CREATE ANY TABLE`.
- `ALTER ANY TABLE`, `DROP ANY TABLE`.
- `GRANT ANY PRIVILEGE`, `GRANT ANY ROLE`.
- Any broad administrative role such as `DBA`.
- `ADMIN_OPTION` on roles or system privileges.
- `GRANTABLE` on object privileges.

Query for broad-scope system privileges:

~~~sql
SELECT grantee,
       privilege,
       admin_option
  FROM dba_sys_privs
 WHERE privilege LIKE '%ANY%'
    OR privilege LIKE 'GRANT ANY%'
 ORDER BY grantee, privilege;
~~~

Query for delegable object grants:

~~~sql
SELECT grantee,
       owner,
       table_name,
       privilege,
       grantable
  FROM dba_tab_privs
 WHERE grantable = 'YES'
 ORDER BY grantee, owner, table_name;
~~~

`GRANTABLE = YES` indicates the recipient can further grant that object privilege. `ADMIN_OPTION = YES` on roles or system privileges also permits delegating within the privilege's scope. These must be examined under authorization governance and separation of duties.

## 12. Detecting dormant accounts: investigation workflow

Never rely on a single criterion to conclude an account is abandoned. Combine account status, login history, sessions, jobs, applications, and owner confirmation.

### Step 1: build the candidate account list

~~~sql
SELECT username,
       account_status,
       created,
       lock_date,
       expiry_date,
       profile,
       authentication_type
  FROM dba_users
 WHERE oracle_maintained = 'N'
 ORDER BY account_status, username;
~~~

On releases without `ORACLE_MAINTAINED`, omit that filter and classify users using other inventory sources.

### Step 2: identify owners

Every account should document:

- Technical owner or responsible team.
- Consuming application/service.
- Environment and PDB.
- Login purpose.
- Privilege approver.
- Most recent review date.
- Planned expiration or next review date.

If no owner can be identified, flag the account for investigation rather than dropping it automatically.

### Step 3: check activity

Cross-check `LAST_LOGIN` if available, audit trails, `V$SESSION`, scheduler jobs, connection pools, DB links, and application logs. For monthly or quarterly batch accounts, observe at least one full business cycle before concluding inactivity.

### Step 4: classify

Possible categories:

| Category | Typical action |
|---|---|
| Individual account of departed employee | Lock or revoke per offboarding procedure |
| Active service account | Retain, confirm owner, and tighten privileges |
| Replaced legacy service account | Confirm zero traffic/jobs, then lock |
| Schema owner | Retain object ownership; lock login if direct connections are unneeded |
| Oracle-maintained account | Do not lock/drop arbitrarily; follow Oracle documentation |
| Account with unknown owner | Investigate, trace dependencies, and assign an owner |
| Standby or periodic batch account | Verify run schedules and failover procedures before locking |

### Step 5: lock before deleting

Once confirmed an account no longer needs to log in, lock it to block new connections:

~~~sql
ALTER USER old_service_user ACCOUNT LOCK;
~~~

Locking an account is reversible:

~~~sql
ALTER USER old_service_user ACCOUNT UNLOCK;
~~~

Locking an account does not terminate already open sessions. If active sessions must be ended, inspect sessions, transactions, and application impact before taking administrative action.

### Step 6: monitor before dropping

After locking, monitor login errors, job failures, application connectivity, and owner feedback over an appropriate business cycle. Only if no dependencies surface and approval is obtained should you consider dropping the account under change control.

`DROP USER ... CASCADE` deletes every object in the user's schema. This is a destructive data and object operation; perform it only after confirming ownership, backups/retention, dependencies, exports to keep, and recovery plans.

## 13. Locked, expired, and never-logged-in accounts

Account statuses carry distinct meanings:

- `OPEN`: account can log in if other conditions allow.
- `LOCKED`: account is locked.
- `EXPIRED`: password expired per profile.
- `EXPIRED & LOCKED` or combined statuses: account is both expired and locked.
- Other statuses may appear depending on version, authentication, and policy.

A `LOCKED` account can still own schemas and objects referenced by active applications. Never drop an account merely because it is locked.

An `EXPIRED` account might be a service account experiencing a rotation failure. Before resetting its password, verify the owner and secret manager pipeline.

An `OPEN` account lacking `LAST_LOGIN` might never have logged in via a tracked method, or the column may be unsupported/unpopulated. Check audits and operational schedules too.

## 14. Auditing privilege grants and account changes

Periodic reviews need evidence of who created users, modified accounts, granted privileges, or revoked privileges. Oracle Unified Auditing records these actions when appropriate audit policies are created and enabled.

Example creating an audit policy for user and privilege changes:

~~~sql
CREATE AUDIT POLICY security_account_changes
  ACTIONS CREATE USER, ALTER USER, DROP USER, GRANT, REVOKE;

AUDIT POLICY security_account_changes;
~~~

Action syntax and auditing capabilities depend on version, Unified Auditing mode, and execution privileges. Test policies in an appropriate environment and verify actual actions appear in the audit trail.

View recent events:

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       userhost,
       client_program_name
  FROM unified_audit_trail
 WHERE event_timestamp >= SYSTIMESTAMP - INTERVAL '90' DAY
   AND action_name IN (
         'CREATE USER',
         'ALTER USER',
         'DROP USER',
         'GRANT',
         'REVOKE'
       )
 ORDER BY event_timestamp DESC;
~~~

The 90-day window is an example only. Choose timeframes per retention policy and investigation needs. Columns, action types, and capture behavior depend on configuration. If the database uses traditional auditing or mixed mode, check the corresponding audit views and verify where records are stored.

### Auditing logins and account activity

Create a policy tracking logons if aligned with policy:

~~~sql
CREATE AUDIT POLICY user_logon_events
  ACTIONS LOGON;

AUDIT POLICY user_logon_events;
~~~

System-wide logon auditing can generate large data volumes. Evaluate user scope, audit conditions, capacity, retention, and operational impact. Some environments already have default or centrally managed policies; check existing configuration before adding duplicates.

### Protecting the audit trail

An audit trail has value only when audited parties cannot arbitrarily alter or delete it with ordinary privileges. Restrict read, export, purge, and policy modification privileges; retain per policy; synchronize clocks; and forward critical events to centralized monitoring per policy.

## 15. Reviewing PUBLIC in a controlled manner

A workflow for addressing `PUBLIC` grants may include:

1. Export system privileges with `grantee = 'PUBLIC'`.
2. Export object privileges and column privileges with `grantee = 'PUBLIC'`.
3. Classify objects by owner, object type, and sensitivity level.
4. Locate Oracle or application documentation explaining each grant.
5. Check dependencies across code, jobs, synonyms, and clients.
6. Determine whether a grant is truly needed by all users or only one role/service.
7. Test replacing `PUBLIC` with a dedicated role in a test environment.
8. Verify logins and business workflows after the change.
9. Revoke the `PUBLIC` grant once confirmed unnecessary.
10. Document results, owner, approver, and rollback plan.

For example, if a package is only needed by service `ORDER_RUNTIME`, replace `PUBLIC` access with a dedicated role:

~~~sql
CREATE ROLE order_api_role;

GRANT EXECUTE ON app_owner.order_api TO order_api_role;
GRANT order_api_role TO order_runtime;

REVOKE EXECUTE ON app_owner.order_api FROM PUBLIC;
~~~

Execute `REVOKE` only after verifying no other users depend on the `PUBLIC` grant and the new role has been granted to all legitimate services. If the package is Oracle-managed or a database component, follow Oracle guidance before modifying.

### Do not bulk-revoke PUBLIC

Never run automated scripts revoking every grant to `PUBLIC`. Many grants are required by database components or installed features. Blind revoking can cause subtle errors, break management tools, or disrupt application workflows.

Instead, classify first:

- Application-created grants.
- Oracle product or component-created grants.
- Third-party grants.
- Unknown-origin grants.

For unknown-origin grants, trace change history, deployment scripts, audit trails, and owners before deciding.

## 16. PUBLIC in a Multitenant environment

In Oracle Multitenant, distinguish the CDB root from individual PDBs. Grants can be common or local; effective scope and metadata appear in columns such as `COMMON`, `INHERITED`, and `CON_ID` in corresponding CDB views.

When reviewing an entire CDB:

- Inspect grants in CDB root and every PDB.
- Distinguish common grants from local grants.
- Check `CON_ID` to identify the relevant container.
- Distinguish common users from local users.
- Do not assume a grant visible in root has the same scope as a grant created inside a PDB.

Example inspecting object privileges granted to `PUBLIC` from a CDB view when authorized and in an appropriate container:

~~~sql
SELECT con_id,
       owner,
       table_name,
       privilege,
       grantable,
       common,
       inherited
  FROM cdb_tab_privs
 WHERE grantee = 'PUBLIC'
 ORDER BY con_id, owner, table_name, privilege;
~~~

Similarly, use `CDB_SYS_PRIVS` and `CDB_COL_PRIVS` to inspect system and column privileges. `CONTAINER_DATA` settings and CDB view privileges can limit visible containers. When reviewing inside a single PDB, `DBA_*` views typically reflect metadata for the current container per connection context.

Never use a query run inside one PDB to declare the entire CDB free of `PUBLIC` grants. Define the container scope of every review.

## 17. Checking privileges across applications and schema owners

Grant lists alone do not reveal the full picture of how applications exercise privileges. Cross-check:

- Connection strings and service names for each application.
- Users in connection pools.
- Secret managers or wallets.
- Stored procedures, packages, triggers, and jobs.
- Database links, directory objects, and external procedures if any.
- Public and private synonyms.
- Views accessing data across schemas.
- Definer-rights and invoker-rights PL/SQL.
- Proxy authentication or external authentication.

An application may share a single runtime account across multiple services. When it does, the database struggles to distinguish callers without module/action or proper context. Separating service accounts and tagging metadata simplifies reviews and audits.

### Checking owners not used at runtime

A schema owner may need to own objects without logging in regularly. You can lock the owner's login after deployment if the architecture permits:

~~~sql
ALTER USER app_owner ACCOUNT LOCK;
~~~

Before locking, verify deployment pipelines, jobs, management tools, and rotation workflows can operate under other identities. Locking an owner does not drop objects, yet tasks connecting as the owner will fail.

## 18. End-to-end periodic review workflow

An access review cycle can follow these steps:

### Step 1: define scope

Specify databases, CDBs/PDBs, schemas, environments, application groups, and review period. Identify sensitive data, privileged accounts, and connected integration systems.

### Step 2: collect inventory

Extract lists of users, statuses, profiles, roles, system privileges, object privileges, column privileges, `PUBLIC` grants, synonyms, and database links.

### Step 3: map effective privileges

Trace nested roles, system privileges, direct grants, and `PUBLIC`. For critical users, log in using the actual account in a test environment to inspect `SESSION_ROLES` and `SESSION_PRIVS`.

### Step 4: verify owners and purpose

Send account and privilege lists to technical/business owners for attestation. Every account needs a purpose, environment, owner, and review timestamp.

### Step 5: identify excess privileges and dormant accounts

Flag ownerless users, inactive accounts, overly broad roles, `ANY` privileges, delegable privileges, `PUBLIC` grants, and privileges no longer matching application functions.

### Step 6: assess impact

Inspect code, jobs, integrations, dependencies, and business cycles. Never rely on `LAST_LOGIN` alone to declare an account safe to lock.

### Step 7: plan changes

Prioritize replacing broad grants with narrow roles, locking unneeded accounts, revoking confirmed unnecessary `PUBLIC` grants, and separating accounts per service. Document approvers, schedule, rollback steps, and verification checks.

### Step 8: test

Test in development/staging or an equivalent environment. Verify logins, APIs, batch jobs, reports, scheduled jobs, failover, and period-end processes.

### Step 9: deploy and monitor

Execute inside a change window. Monitor for `ORA-01031`, `ORA-01017`, job failures, connection failures, and unusual audit events.

### Step 10: retain evidence

Archive before/after inventories, revoked grants, locked accounts, approvals, test outcomes, audit events, and accepted exceptions.

## 19. Access review tracking template

A privilege management tracking table can include:

| Field | Purpose |
|---|---|
| Database / PDB | Container scope |
| Username / Role | Identity or privilege group |
| Account type | Human, service, schema owner, deployment, monitor |
| Owner | Responsible team/person |
| Account status | `OPEN`, `LOCKED`, `EXPIRED`... |
| Last login / evidence | Activity data and verification source |
| Granted roles | Direct and nested roles |
| System privileges | System-level privileges |
| Object privileges | Object-level privileges |
| PUBLIC exposure | Whether grants or dependencies exist via `PUBLIC` |
| Sensitive privileges | `ANY`, `DBA`, `ADMIN_OPTION`, `GRANTABLE` |
| Decision | Keep, reduce, lock, revoke, investigate |
| Approver | Approval authority |
| Due date | Target completion date |
| Evidence | Ticket, audit record, test result |

Retained accounts still require justification and an owner. Exception privileges still require expiration dates and next review dates.

## 20. Responding to unexpected PUBLIC privileges

If a sensitive table or application package is found granted to `PUBLIC`:

1. Identify the exact object and privilege.
2. Determine what data or operations the privilege permits.
3. Find which users/services currently depend on that grant.
4. Identify a narrower role or replacement API.
5. Test revoking `PUBLIC` and granting the role in a test environment.
6. Confirm all legitimate applications continue operating.
7. Deploy the approved change.
8. Monitor access errors and audits after the change.
9. Document an exception if the grant must remain.

If the grant was exploited or unauthorized access is suspected, switch to incident response: preserve audit evidence, determine data scope, rotate credentials, close necessary access paths, and notify per organizational policy.

## 21. Common mistakes

**Locking users solely due to an old LAST_LOGIN:** can break period-end batches or standby services. Verify run schedules and owners first.

**Dropping users to tidy up lists:** `DROP USER ... CASCADE` can delete schema objects. Lock first, evaluate dependencies and backups, and only then consider dropping.

**Revoking all PUBLIC privileges:** can break Oracle features or applications. Classify origin and dependencies first.

**Checking only DBA_SYS_PRIVS:** misses object grants, column grants, nested roles, and `PUBLIC`.

**Checking only direct user grants:** misses role-inherited privileges and `ANY`-scoped system privileges.

**Confusing PUBLIC synonyms with PUBLIC privileges:** synonyms do not grant object privileges.

**Assuming OPEN accounts are active:** `OPEN` only permits login; it does not prove an owner or business need exists.

**Assuming LOCKED accounts can be dropped:** locking login does not remove objects and dependencies.

**Ignoring common/local scope in CDB:** can miss containers or mistakenly revoke grants with a different scope.

**Not auditing grants/revokes:** after an incident, no one knows who granted privileges or when changes occurred.

**Not tracking exceptions:** excess privileges kept without owners or expiration dates become long-term risks.

## 22. Review execution checklist

- [ ] Identify database, instance, CDB/PDB, and environment.
- [ ] Inventory users, roles, and account statuses.
- [ ] Identify the owner of every account and service.
- [ ] Check `LAST_LOGIN` if supported by release and cross-check audits/sessions/jobs.
- [ ] Inspect system privileges and `ANY` privileges.
- [ ] Trace nested roles and delegable privileges.
- [ ] Inspect object privileges and column privileges.
- [ ] Export system, object, and column grants with `grantee = 'PUBLIC'`.
- [ ] Inspect `PUBLIC` synonyms and `PUBLIC` database links.
- [ ] Distinguish application grants from Oracle-managed grants.
- [ ] Evaluate accounts no longer needing login; lock in phases.
- [ ] Test replacing `PUBLIC` with dedicated roles where appropriate.
- [ ] Inspect Unified Audit policies and audit trails.
- [ ] Test applications, batches, jobs, failover, and periodic workflows.
- [ ] Retain evidence, approvals, exceptions, and next review dates.

## 23. Conclusion

Periodic privilege reviews keep a database from accumulating dormant accounts, broad privileges, and unexplained access paths. Inspect users, nested roles, system privileges, object privileges, column privileges, delegable privileges, and active sessions. For inactive accounts, combine `LAST_LOGIN` where available, audits, sessions, jobs, secrets, and owner confirmation; lock accounts before considering dropping them.

`PUBLIC` requires dedicated review because privileges granted to `PUBLIC` can apply to every user. Query `DBA_SYS_PRIVS`, `DBA_TAB_PRIVS`, and `DBA_COL_PRIVS` for grantee `PUBLIC`; distinguish `PUBLIC` synonyms from access privileges and inspect `PUBLIC` database links. Never bulk-revoke Oracle-managed grants without verifying dependencies. In Multitenant environments, distinguish common and local grants per container.

A sustainable process requires inventories, owners, approvals, auditing, testing, controlled changes, and post-deployment evidence. When maintained, database privileges continuously reflect the genuine needs of applications and operators.
