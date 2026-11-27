# Unified Auditing, audit policies, and querying audit trails in Oracle Database

Unified Auditing is Oracle Database's centralized auditing mechanism. Instead of enabling scattered audits statement by statement, a DBA can define an **audit policy** describing the actions, privileges, or objects to monitor, then enable that policy system-wide or for specific users. Events are recorded into the unified audit trail for security investigations, change tracking, and compliance verification.

An effective audit process must answer four questions:

1. **Who** performed the action? Which database user, proxy user, OS user, or client identity?
2. **What** was done? A login, table read, data update, configuration change, or system privilege usage?
3. **Where and when**? Which object, timestamp, client/host, and container?
4. **What was the outcome**? Success or failure, what return code, and which SQL statement executed?

This lesson uses Oracle Database 19c as the reference baseline. It covers Unified Auditing architecture, mixed/pure mode status, creating and enabling audit policies, predefined policies, querying `UNIFIED_AUDIT_TRAIL`, separating audit admin and viewer privileges, Fine-Grained Auditing, audit trail lifecycle management, and incident investigation workflows.

## 1. What is the goal of database auditing?

### 1.1. Auditing provides evidence of activity

The audit trail records configured events. It supports:

- Investigating unauthorized access or anomalous behavior.
- Tracking use of powerful privileges such as `CREATE ANY TABLE` or `ALTER SYSTEM`.
- Identifying who read or modified a sensitive table.
- Monitoring successful and failed logins.
- Reviewing changes to users, roles, privileges, and configurations.
- Supporting compliance requirements, internal audits, and incident response workflows.

The audit trail is technical evidence. It does not by itself prove user intent, nor does it replace application logs, OS logs, network logs, or identity management processes.

### 1.2. Auditing differs from application logging

Application logs typically describe business operations such as "user created an order" or "request completed." Database auditing records database-layer activity such as which user executed `SELECT`, `UPDATE`, DDL, or exercised a privilege.

The two sources complement each other:

| Source | Typically answers |
| --- | --- |
| Unified audit trail | Which database account performed what action on which database/object |
| Application log | Business user, request ID, and application workflow |
| OS/security log | Process, host, OS login, and server events |
| Network/security gateway | Connections, network source, and traffic |
| Identity provider | Authenticated identity, MFA, and account lifecycle |

For end-to-end traceability, applications should set an appropriate client identifier and module/action to correlate database activity with business requests.

### 1.3. Audit policies need a clear purpose

Do not audit every `SELECT` on every table just because it is possible. Overly broad auditing can:
- Rapidly inflate audit trail storage.
- Add I/O and processing overhead.
- Make investigative queries harder due to excessive noise.
- Record SQL or sensitive information that itself needs protection.
- Increase storage, archival, and retention burden.

Start from the risks that need control: privileged actions, sensitive data, failed logins, critical DDL, or account changes. Choose narrow policies, measure volume, and expand only with justification.

## 2. What is Unified Auditing?

### 2.1. Unified auditing model

Unified Auditing provides a single framework to define audit policies and store audit records in the unified audit trail. A policy can include:
- SQL actions, e.g., `SELECT` on an object.
- System privileges, e.g., `CREATE ANY TABLE`.
- Roles.
- Actions from database components supporting unified auditing.
- Success/failure recording conditions specified when enabling the policy.

Records are queried via `UNIFIED_AUDIT_TRAIL`. Oracle manages internal audit tables in the `AUDSYS` schema; applications and DBAs must use supported views/packages and never manipulate internal tables directly.

### 2.2. Mixed mode and pure unified auditing

In Oracle 19c, distinguish two deployment modes:

- **Mixed mode:** unified auditing and traditional auditing coexist. Unified audit policies operate while legacy traditional audit configurations may still write to traditional audit destinations.
- **Pure unified auditing:** the database runs exclusively on unified auditing; legacy traditional auditing mechanisms no longer act as independent audit pipelines as in mixed mode.

Check status depending on environment:

~~~sql
SELECT parameter,
       value
FROM   v$option
WHERE  parameter = 'Unified Auditing';
~~~

A value of `TRUE` indicates pure unified auditing is enabled in the corresponding Oracle home/database. `FALSE` does not mean unified audit policies cannot be used; mixed mode still supports Unified Auditing.

Switching to pure mode involves the Oracle home/binaries and database startup procedures. This is a DBA change following platform- and version-specific instructions; never relink or restart production just to test a policy.

### 2.3. Traditional auditing vs. Unified Auditing

Traditional auditing uses legacy `AUDIT` statements and corresponding audit destinations/parameters. Unified Auditing uses `CREATE AUDIT POLICY`, `AUDIT POLICY`, and `NOAUDIT POLICY`.

In mixed mode, both mechanisms can coexist, so when investigating legacy systems, do not inspect only one view and conclude all audit data has been captured. You may need to check:
- `UNIFIED_AUDIT_TRAIL` for unified audit records.
- `DBA_AUDIT_TRAIL` or corresponding traditional views if traditional auditing is still active.
- `DBA_FGA_AUDIT_TRAIL` or the unified trail for Fine-Grained Auditing, depending on configuration and compatibility settings.

The traditional auditing `AUDIT_TRAIL` parameter is not an on/off switch for unified audit policies. Inspect the audit mode and actual configuration separately.

### 2.4. Checking enabled policies

`AUDIT_UNIFIED_ENABLED_POLICIES` shows which policies are enabled, their user/entity scope, and success/failure conditions. Example:

~~~sql
SELECT user_name,
       policy_name,
       enabled_option,
       entity_name,
       success,
       failure
FROM   audit_unified_enabled_policies
ORDER  BY policy_name, user_name;
~~~

To check release-specific columns, use `DESC AUDIT_UNIFIED_ENABLED_POLICIES` or consult Oracle Database Reference. This view describes policy configuration; it is not a list of generated audit events.

## 3. Audit administration and viewing privileges

### 3.1. AUDIT_ADMIN

`AUDIT_ADMIN` is the role for administering supported audit operations, such as creating/managing audit policies and managing the audit trail via appropriate APIs.

Example DBA granting the role to a security admin account:

~~~sql
GRANT AUDIT_ADMIN TO audit_admin_user;
~~~

Grant this role only to accounts responsible for audit management. Never share audit admin accounts with applications.

### 3.2. AUDIT_VIEWER

`AUDIT_VIEWER` is for users who need to inspect audit data without full policy administration rights.

~~~sql
GRANT AUDIT_VIEWER TO security_reader;
~~~

Separating policy creators/enablers from audit readers enforces least privilege. Audit viewers can still see SQL text, user identities, object names, and sensitive details; audit read access must be protected.

### 3.3. Checking privileges

Inspect roles granted to users:

~~~sql
SELECT grantee,
       granted_role,
       default_role
FROM   dba_role_privs
WHERE  grantee IN ('AUDIT_ADMIN_USER', 'SECURITY_READER')
ORDER  BY grantee, granted_role;
~~~

View names and access depend on schema/DBA privileges. In learning environments, a DBA can grant the appropriate role; never grant `SELECT ANY TABLE` or other broad privileges just to read the audit trail.

### 3.4. Separation of duties principles

- Audit administrators create and maintain policies.
- Security auditors query, analyze, and generate reports.
- Application accounts hold only required business privileges.
- `SYS`/`DBA` accounts are controlled separately with break-glass procedures.
- Audit trails are stored with independent access control and retention.

## 4. Creating audit policies for objects

### 4.1. Auditing SELECT on a sensitive table

Suppose `HR.EMPLOYEES` contains personnel data. Create a policy:

~~~sql
CREATE AUDIT POLICY audit_employee_reads
    ACTIONS SELECT ON hr.employees;
~~~

Enable the policy:

~~~sql
AUDIT POLICY audit_employee_reads;
~~~

This policy records `SELECT` actions on the specified object. To scope it to a specific user, enable it for one database user:

~~~sql
AUDIT POLICY audit_employee_reads
    BY app_user;
~~~

Schema, table, and user names must exist in the actual environment. The executor needs appropriate audit policy management privileges.

### 4.2. Auditing both SELECT and UPDATE

~~~sql
CREATE AUDIT POLICY audit_employee_access
    ACTIONS SELECT ON hr.employees,
            UPDATE ON hr.employees;

AUDIT POLICY audit_employee_access BY app_user;
~~~

A single policy can group multiple actions on objects. Grouping policies by behavior keeps administration clearer, but avoid merging events with different retention or owners if security policy requires distinguishing them.

### 4.3. Auditing only successful or failed operations

You can restrict conditions when enabling a policy:

~~~sql
AUDIT POLICY audit_employee_access
    BY app_user
    WHENEVER SUCCESSFUL;
~~~

Or record only failures:

~~~sql
AUDIT POLICY audit_employee_access
    BY app_user
    WHENEVER NOT SUCCESSFUL;
~~~

If enabled without a `WHENEVER` clause, the default behavior audits both successes and failures. Define investigation goals before choosing conditions.

### 4.4. Auditing DDL

Create a policy to track critical DDL actions:

~~~sql
CREATE AUDIT POLICY audit_schema_ddl
    ACTIONS CREATE TABLE,
            ALTER TABLE,
            DROP TABLE,
            CREATE USER,
            ALTER USER,
            DROP USER;

AUDIT POLICY audit_schema_ddl;
~~~

DDL can affect structure, data, and access rights. In production, audit high-risk actions and verify which users/roles are authorized to execute them.

### 4.5. Auditing system privilege usage

To know when powerful privileges are exercised:

~~~sql
CREATE AUDIT POLICY audit_powerful_privileges
    PRIVILEGES CREATE ANY TABLE,
               DROP ANY TABLE,
               ALTER SYSTEM;

AUDIT POLICY audit_powerful_privileges;
~~~

Auditing privilege usage tracks exercise of those privileges even when an action does not target a specific object named in the policy. Check the supported privilege list and policy behavior in your running release.

### 4.6. Viewing policy definitions

~~~sql
SELECT policy_name,
       audit_option,
       object_schema,
       object_name,
       object_type
FROM   audit_unified_policies
WHERE  policy_name IN (
           'AUDIT_EMPLOYEE_READS',
           'AUDIT_EMPLOYEE_ACCESS',
           'AUDIT_SCHEMA_DDL',
           'AUDIT_POWERFUL_PRIVILEGES'
       )
ORDER  BY policy_name, audit_option;
~~~

`AUDIT_UNIFIED_POLICIES` describes the audit options declared inside policies. One policy can have multiple rows because each action/object option is stored as a metadata row.

## 5. Enabling, disabling, and dropping audit policies

### 5.1. Enabling a policy for all users

~~~sql
AUDIT POLICY audit_employee_reads;
~~~

When no user is specified, the policy is enabled under the statement's default scope. Before applying broadly, check which actions the policy audits and estimate volume.

### 5.2. Enabling a policy for a specific user

~~~sql
AUDIT POLICY audit_employee_reads BY app_user;
~~~

User scoping works when only one account or a small group of accounts needs monitoring. With many users, manage lists through provisioning workflows and periodic reviews.

### 5.3. Disabling a policy

~~~sql
NOAUDIT POLICY audit_employee_reads;
~~~

Disabling a policy stops recording new events generated by that policy after the change takes effect. Already recorded events remain in the audit trail per retention policy.

If the policy was enabled only for a single user, `NOAUDIT` can be scoped to that user:

~~~sql
NOAUDIT POLICY audit_employee_reads BY app_user;
~~~

### 5.4. Dropping a policy

Once a policy is no longer needed, disable it first and then drop its definition:

~~~sql
NOAUDIT POLICY audit_employee_reads;
DROP AUDIT POLICY audit_employee_reads;
~~~

Never drop a policy to conceal history. Policy changes or removals must be recorded under security change management.

### 5.5. Verifying status after changes

~~~sql
SELECT user_name,
       policy_name,
       enabled_option,
       entity_name,
       success,
       failure
FROM   audit_unified_enabled_policies
WHERE  policy_name = 'AUDIT_EMPLOYEE_READS';
~~~

If no rows appear, the policy may not be enabled or may not apply to the current container/user. Verify the target database, PDB, and query privileges.

## 6. Predefined unified audit policies

Oracle provides several predefined unified audit policies for common security activity groups. Policy names and default enabled states depend on release, database configuration, and database creation method; check before enabling or disabling.

Common names in Oracle 19c:

| Policy | General purpose |
| --- | --- |
| `ORA_SECURECONFIG` | Tracks critical security configuration actions |
| `ORA_LOGON_FAILURES` | Tracks failed logins |
| `ORA_ACCOUNT_MGMT` | Tracks account management operations |
| `ORA_DATABASE_PARAMETER` | Tracks database parameter changes |
| `ORA_CIS_RECOMMENDATIONS` | CIS-aligned audit recommendations |

Check definitions:

~~~sql
SELECT policy_name,
       audit_option,
       object_schema,
       object_name,
       object_type
FROM   audit_unified_policies
WHERE  policy_name LIKE 'ORA_%'
ORDER  BY policy_name, audit_option;
~~~

Check enabled policies:

~~~sql
SELECT policy_name,
       enabled_option,
       entity_name,
       success,
       failure
FROM   audit_unified_enabled_policies
WHERE  policy_name LIKE 'ORA_%'
ORDER  BY policy_name;
~~~

If a predefined policy is not yet enabled and matches your security baseline, enable it:

~~~sql
AUDIT POLICY ORA_LOGON_FAILURES;
~~~

Do not assume all `ORA_*` policies are already enabled or fit every environment. Review scope, volume, and internal policies before making changes.

## 7. Unified audit trail — querying the audit log

### 7.1. The UNIFIED_AUDIT_TRAIL view

`UNIFIED_AUDIT_TRAIL` is the primary view for querying unified audit records. Common columns include:
- `EVENT_TIMESTAMP`: timestamp of the event.
- `DBUSERNAME`: database user performing the action.
- `OS_USERNAME`: OS user recorded by client/database.
- `USERHOST`: source host.
- `CLIENT_PROGRAM_NAME`: client program.
- `CLIENT_IDENTIFIER`: client identifier if set by the application.
- `ACTION_NAME`: action name.
- `OBJECT_SCHEMA`, `OBJECT_NAME`: involved object.
- `RETURN_CODE`: outcome code.
- `UNIFIED_AUDIT_POLICIES`: policies that triggered the record.
- `SQL_TEXT`, `SQL_BINDS`: SQL statement and bind information when captured.
- `SYSTEM_PRIVILEGE_USED`: relevant system privilege if applicable.

Not every column is populated in every record. Login events, DDL, object `SELECT`s, and component events populate different fields.

### 7.2. Querying recent events

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       unified_audit_policies,
       userhost,
       client_program_name
FROM   unified_audit_trail
WHERE  event_timestamp >= SYSTIMESTAMP - INTERVAL '1' DAY
ORDER  BY event_timestamp DESC
FETCH FIRST 100 ROWS ONLY;
~~~

The time range is bounded to avoid scanning and displaying too many records. In high-volume audit systems, filter by time window, user, or specific object.

### 7.3. Querying by database user

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       unified_audit_policies,
       userhost,
       client_program_name
FROM   unified_audit_trail
WHERE  dbusername = 'APP_USER'
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '7' DAY
ORDER  BY event_timestamp DESC;
~~~

Usernames in the dictionary are typically stored in uppercase if created without quoted identifiers. Verify the exact casing of usernames in your environment.

### 7.4. Querying by object

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       unified_audit_policies,
       userhost
FROM   unified_audit_trail
WHERE  object_schema = 'HR'
AND    object_name = 'EMPLOYEES'
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '30' DAY
ORDER  BY event_timestamp DESC;
~~~

This helps when investigating access to a sensitive table. Some actions are not object-bound, so `object_schema`/`object_name` may be NULL.

### 7.5. Distinguishing success and failure

`RETURN_CODE` equal to 0 typically indicates a successful operation; a non-zero value is usually the Oracle error code of a failed operation.

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       userhost,
       client_program_name
FROM   unified_audit_trail
WHERE  return_code <> 0
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '24' HOUR
ORDER  BY event_timestamp DESC;
~~~

Do not assume every database error is audited. Only actions covered by enabled policies or corresponding audit sources appear.

### 7.6. Querying failed logins

~~~sql
SELECT event_timestamp,
       dbusername,
       os_username,
       userhost,
       client_program_name,
       action_name,
       return_code,
       unified_audit_policies
FROM   unified_audit_trail
WHERE  action_name = 'LOGON'
AND    return_code <> 0
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '7' DAY
ORDER  BY event_timestamp DESC;
~~~

The `ORA_LOGON_FAILURES` policy is commonly used to track logon failures. Verify the policy is enabled in the intended container and covers the investigation timeframe.

### 7.7. Querying account and privilege changes

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       system_privilege_used,
       return_code,
       unified_audit_policies,
       userhost
FROM   unified_audit_trail
WHERE  action_name IN (
           'CREATE USER',
           'ALTER USER',
           'DROP USER',
           'GRANT',
           'REVOKE'
       )
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '30' DAY
ORDER  BY event_timestamp DESC;
~~~

Action names depend on the exact `ACTION_NAME` value recorded. When investigating, query actions broadly around the incident window first, then refine filters using observed values.

### 7.8. Reading SQL_TEXT and SQL_BINDS

`SQL_TEXT` and `SQL_BINDS` can hold long strings. Use `DBMS_LOB.SUBSTR` to extract a snippet when clients do not display CLOBs conveniently:

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       DBMS_LOB.SUBSTR(sql_text, 1000, 1) AS sql_text_sample,
       DBMS_LOB.SUBSTR(sql_binds, 1000, 1) AS sql_binds_sample
FROM   unified_audit_trail
WHERE  sql_text IS NOT NULL
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '1' DAY
ORDER  BY event_timestamp DESC;
~~~

`SQL_TEXT`/`SQL_BINDS` may be NULL depending on record type, policy, and event source. Bind capture does not always include every bind value. These values may contain sensitive data; access only when authorized and redact sensitive fields before sharing reports.

### 7.9. Grouping audit events by user and action

~~~sql
SELECT dbusername,
       action_name,
       COUNT(*) AS event_count,
       MIN(event_timestamp) AS first_event,
       MAX(event_timestamp) AS last_event
FROM   unified_audit_trail
WHERE  event_timestamp >= SYSTIMESTAMP - INTERVAL '7' DAY
GROUP  BY dbusername, action_name
ORDER  BY event_count DESC;
~~~

Aggregation helps spot accounts or actions generating excessive audit records. High counts may reflect normal workloads; cross-check against application traffic and policy scope.

## 8. Querying policy and audit configurations

### 8.1. List of policies

~~~sql
SELECT DISTINCT policy_name
FROM   audit_unified_policies
ORDER  BY policy_name;
~~~

### 8.2. Actions/objects in a policy

~~~sql
SELECT policy_name,
       audit_option,
       object_schema,
       object_name,
       object_type
FROM   audit_unified_policies
WHERE  policy_name = 'AUDIT_EMPLOYEE_ACCESS'
ORDER  BY audit_option, object_schema, object_name;
~~~

### 8.3. Enabled policies and targets

~~~sql
SELECT user_name,
       policy_name,
       enabled_option,
       entity_name,
       success,
       failure
FROM   audit_unified_enabled_policies
ORDER  BY policy_name, entity_name;
~~~

Inspect both definitions and enabled states. A policy existing in `AUDIT_UNIFIED_POLICIES` is not necessarily enabled.

### 8.4. Checking audit trail record types

~~~sql
SELECT audit_type,
       COUNT(*) AS record_count,
       MIN(event_timestamp) AS oldest_event,
       MAX(event_timestamp) AS newest_event
FROM   unified_audit_trail
GROUP  BY audit_type
ORDER  BY record_count DESC;
~~~

`AUDIT_TYPE` distinguishes audit sources. Specific record types appear depending on components and configuration. Use this output to understand existing data rather than assuming all audit sources are active.

## 9. Fine-Grained Auditing and Unified Auditing

### 9.1. When is Fine-Grained Auditing needed?

Unified audit policies cover broad actions, privileges, and objects. Fine-Grained Auditing (FGA) is used when finer conditions are needed, such as auditing access only to a sensitive column or only when a data condition is met.

FGA is managed via `DBMS_FGA`. In Oracle versions supporting Unified Auditing, FGA audit records can be queried in the unified audit trail; legacy compatibility views may still exist depending on mode.

### 9.2. Creating a column- and condition-based FGA policy

Example auditing `SELECT` on the `SALARY` column only when values meet a condition:

~~~sql
BEGIN
    DBMS_FGA.ADD_POLICY(
        object_schema   => 'HR',
        object_name     => 'EMPLOYEES',
        policy_name     => 'FGA_HIGH_SALARY_READ',
        audit_condition => 'SALARY >= 10000',
        audit_column    => 'SALARY',
        statement_types => 'SELECT'
    );
END;
/
~~~

The audit condition must be a valid SQL expression within `DBMS_FGA` constraints; do not treat it as a place to run arbitrary subqueries. The executor needs appropriate privileges on the object and package.

### 9.3. Checking an FGA policy

~~~sql
SELECT object_schema,
       object_name,
       policy_name,
       enabled,
       sel,
       ins,
       upd,
       del,
       audit_column
FROM   dba_audit_policies
WHERE  policy_name = 'FGA_HIGH_SALARY_READ';
~~~

Displayed columns depend on view and release. You can use `ALL_AUDIT_POLICIES` or `USER_AUDIT_POLICIES` according to privileges.

### 9.4. Disabling or dropping an FGA policy

~~~sql
BEGIN
    DBMS_FGA.DISABLE_POLICY(
        object_schema => 'HR',
        object_name   => 'EMPLOYEES',
        policy_name   => 'FGA_HIGH_SALARY_READ'
    );
END;
/
~~~

Drop the policy when no longer needed:

~~~sql
BEGIN
    DBMS_FGA.DROP_POLICY(
        object_schema => 'HR',
        object_name   => 'EMPLOYEES',
        policy_name   => 'FGA_HIGH_SALARY_READ'
    );
END;
/
~~~

Unified audit policies and FGA policies are two distinct configuration mechanisms. Choose the mechanism suited to the audit requirement and avoid enabling overlapping policies unnecessarily.

## 10. Client identity and traceability

### 10.1. Database user is not always the business end user

In connection pools, hundreds of application users may share one database account like `APP_USER`. If you only audit `DBUSERNAME`, all activity appears under the same account.

Applications should set a client identifier after authenticating the user:

~~~sql
BEGIN
    DBMS_SESSION.SET_IDENTIFIER('user-7421');
END;
/
~~~

The client identifier is attached to the session and can appear in the audit context when records support that field. Use values without secrets and comply with personal data protection rules.

### 10.2. Setting module and action

Applications can set module/action:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'OrderService',
        action_name => 'ReadCustomerProfile'
    );
END;
/
~~~

Module/action assists session and SQL analysis through appropriate monitoring tools. The audit trail can capture certain client context fields depending on column support; for reliable correlation, rely on `CLIENT_IDENTIFIER` and application-managed correlation IDs.

### 10.3. Clearing context when returning connections to the pool

Connection pools reuse sessions. After finishing a request, the application must reset client identifier/module/action or set new values before the next request. Otherwise, audit records can carry stale identities from prior requests.

### 10.4. Do not treat client identifier as independent authentication proof

`CLIENT_IDENTIFIER` is set by the client/application. It is useful for request correlation, but does not by itself prove the user authenticated properly. Correlate with application authentication logs, proxy identities, or identity providers during investigations.

## 11. Unified auditing in CDB and PDB

### 11.1. Container context

In a multitenant database, policies and audit records can be scoped to the CDB root or a PDB. When investigating:
- Identify the connected container.
- Check whether policies are common or local.
- Check whether users are common users or local users.
- Distinguish root records from PDB records.
- Use appropriate CDB views if aggregating across multiple containers when authorized.

### 11.2. Checking the current container

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'CON_ID') AS con_id
FROM   dual;
~~~

When running `CREATE AUDIT POLICY` or `AUDIT POLICY`, execute in the intended container per administrative design. Do not assume a policy created in a PDB automatically applies to the whole CDB, or vice versa.

### 11.3. Multi-container audit trail

In a CDB, DBAs can use corresponding CDB-level audit views to inspect data across containers, subject to privileges and container visibility. When exporting reports, always retain `CON_ID`/container metadata so two PDBs with identical schema/object names are not conflated as a single event source.

### 11.4. Common and local policies

Common policies serve configurations managed from root across supported scopes; local policies apply only within their respective container. Designing common policies requires reviewing impact across all PDBs, audit volume, and administrative privileges.

`CONTAINER` syntax and common/local rules depend on policy type and release. Consult the 19c SQL Language Reference before deploying in a production CDB.

## 12. Storage, flushing, and audit trail capacity management

### 12.1. Audit trails are critical security data

The unified audit trail is stored in Oracle's internal `AUDSYS` management area. Never directly modify or delete internal tables. Use `UNIFIED_AUDIT_TRAIL` for reading and `DBMS_AUDIT_MGMT` for cleanup per Oracle guidelines.

Audit records can contain SQL text, object names, user identities, and context. Protect audit trails from:
- Unauthorized users.
- Out-of-process deletion or modification.
- Storage exhaustion.
- Retention shorter than required.
- Clock drift between the database and related systems.

### 12.2. Flushing the unified audit trail

In some configurations, audit records can be queued before being written to audit tables. You can force a flush using the management package:

~~~sql
BEGIN
    DBMS_AUDIT_MGMT.FLUSH_UNIFIED_AUDIT_TRAIL;
END;
/
~~~

This helps ensure pending records are persisted before reconciliation. It does not replace verifying that policies are enabled or confirming events fall within audit scope.

### 12.3. Checking tablespace space usage

Check related segments and tablespaces with DBA privileges:

~~~sql
SELECT owner,
       segment_name,
       segment_type,
       tablespace_name,
       bytes / 1024 / 1024 AS size_mb
FROM   dba_segments
WHERE  owner = 'AUDSYS'
ORDER  BY bytes DESC;
~~~

`AUDSYS` is an internal schema. Only observe metadata; never `DROP`, `MOVE`, or modify internal audit segments with unsupported operations.

### 12.4. Archive before purging

A retention policy should define:
- Online retention duration for quick queries.
- Long-term archive destination.
- Archive access controls.
- Encryption and integrity verification.
- Legal hold or investigation hold procedures.
- Who approves cleanup.
- How archive readability is verified.

Only set the last archive timestamp after records up to that point have actually been safely archived per procedure.

### 12.5. Initializing cleanup management

Example DBA initializing cleanup management for the unified audit trail:

~~~sql
BEGIN
    DBMS_AUDIT_MGMT.INIT_CLEANUP(
        audit_trail_type        => DBMS_AUDIT_MGMT.AUDIT_TRAIL_UNIFIED,
        default_cleanup_interval => 24
    );
END;
/
~~~

Constant names and privilege requirements should be verified against your release's package reference. This operation initializes cleanup scheduling; it does not immediately delete records.

### 12.6. Marking the archived timestamp

After old records have been exported/archived and archive success confirmed, the DBA can update the last archive timestamp:

~~~sql
BEGIN
    DBMS_AUDIT_MGMT.SET_LAST_ARCHIVE_TIMESTAMP(
        audit_trail_type => DBMS_AUDIT_MGMT.AUDIT_TRAIL_UNIFIED,
        last_archive_time => SYSTIMESTAMP - INTERVAL '90' DAY
    );
END;
/
~~~

The 90-day mark is illustrative only. In production, the timestamp must accurately reflect data already archived, not merely desired retention on paper.

### 12.7. Cleaning up archived records

~~~sql
BEGIN
    DBMS_AUDIT_MGMT.CLEAN_AUDIT_TRAIL(
        audit_trail_type         => DBMS_AUDIT_MGMT.AUDIT_TRAIL_UNIFIED,
        use_last_arch_timestamp  => TRUE
    );
END;
/
~~~

The statement above demonstrates cleanup using the last archive timestamp. Run it only after verifying retention, archive status, privileges, legal holds, and approvals. Never use cleanup to erase traces of an incident under active investigation.

### 12.8. Monitoring audit volume

~~~sql
SELECT TRUNC(event_timestamp) AS audit_day,
       audit_type,
       COUNT(*) AS record_count
FROM   unified_audit_trail
WHERE  event_timestamp >= SYSTIMESTAMP - INTERVAL '30' DAY
GROUP  BY TRUNC(event_timestamp), audit_type
ORDER  BY audit_day DESC, audit_type;
~~~

Daily volume helps spot overly broad policies or sudden spikes in audit records. Correlate with request volume, batch jobs, and configuration changes to identify root causes.

## 13. Protecting the audit trail and safe operations

### 13.1. Least privilege

Only `AUDIT_ADMIN` or authorized administrative accounts may create/disable policies and manage cleanup. Only required audit personnel should hold `AUDIT_VIEWER`. Application users must never read the audit trail.

### 13.2. Audit trails must be protected independently

- Restrict `SYSDBA` and `AUDSYS` administrative access.
- Monitor policy changes.
- Archive to access-controlled storage.
- Protect archives against unauthorized modification/deletion.
- Apply encryption and checksums per policy.
- Synchronize clocks across database, OS, application, and identity providers.
- Log who exported, purged, or changed retention.

### 13.3. Do not over-audit sensitive data

`SQL_TEXT`/`SQL_BINDS` and application context can contain sensitive data. Decide whether SQL binds must be captured, who may view them, and how long they are kept. Never place passwords, tokens, or secrets in client identifiers, module/action fields, or SQL comments.

### 13.4. Audit administrative actions themselves

Creating, enabling, disabling, and modifying audit policies are critical security actions. Use policies to protect configuration changes and periodically review enabled policies to detect unauthorized scope reductions.

### 13.5. Time synchronization

Timestamps are useful only if comparable with application logs and OS logs. Use NTP/time synchronization on database hosts, app hosts, and related systems. During analysis, pay attention to `EVENT_TIMESTAMP`, timezones, and how query tools render timestamps.

## 14. Security event investigation workflow

### Step 1 — Define the question

Examples:
- Who read `HR.EMPLOYEES` yesterday?
- Which user had repeated failed logins?
- Who granted `CREATE ANY TABLE`?
- When was a policy disabled?
- Which client executed an `UPDATE` on sensitive data?

Clear questions select the right audit trail filters.

### Step 2 — Verify policy coverage

Check `AUDIT_UNIFIED_POLICIES` and `AUDIT_UNIFIED_ENABLED_POLICIES`. Confirm whether the policy existed and was enabled for the relevant user/container, and whether it captured successes/failures as expected.

If the policy was not enabled at the time of the event, the audit trail may have no records. Unrecorded historical events cannot be retroactively captured by enabling the policy later.

### Step 3 — Choose the time window

Use timezone-aware timestamps and widen the search window if clock skew is possible. Start narrow, then expand based on evidence.

### Step 4 — Filter by user, action, and object

Filter using `DBUSERNAME`, `ACTION_NAME`, `OBJECT_SCHEMA`, `OBJECT_NAME`, `RETURN_CODE`, and `UNIFIED_AUDIT_POLICIES`. Keep `USERHOST`, `CLIENT_PROGRAM_NAME`, and `CLIENT_IDENTIFIER` to correlate sources.

### Step 5 — Inspect SQL and context

When `SQL_TEXT`/`SQL_BINDS` are available, inspect only what is necessary and protect sensitive details. Correlate with application request IDs, client identifiers, sessions, and application logs.

### Step 6 — Distinguish successful and failed actions

`RETURN_CODE` and action type show database outcomes. A failed login may reflect a wrong password, nonexistent user, or connection error; cross-check error codes and identity logs.

### Step 7 — Preserve evidence

Export records following approved procedures, preserving timestamps/timezones, SQL_ID or transaction context where available, query source, exporter identity, and checksum/archive metadata. Avoid altering retention or policies while an investigation is open.

### Step 8 — Report findings with boundaries

Reports should distinguish:
- What the audit trail directly proves.
- What is inferred from client/application context.
- Data that was not audited or is absent from records.
- Timeframe, container, and policy coverage.
- Other log sources requiring correlation.

Never conclude "no action occurred" merely from missing records if policies did not cover the action or the audit trail was purged.

## 15. Sample queries for common scenarios

### 15.1. Who read a sensitive table?

~~~sql
SELECT event_timestamp,
       dbusername,
       userhost,
       client_program_name,
       client_identifier,
       action_name,
       return_code,
       unified_audit_policies
FROM   unified_audit_trail
WHERE  object_schema = 'HR'
AND    object_name = 'EMPLOYEES'
AND    action_name = 'SELECT'
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '1' DAY
ORDER  BY event_timestamp DESC;
~~~

### 15.2. Who modified a table?

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       userhost,
       client_program_name
FROM   unified_audit_trail
WHERE  object_schema = 'HR'
AND    object_name = 'EMPLOYEES'
AND    action_name IN ('INSERT', 'UPDATE', 'DELETE')
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '7' DAY
ORDER  BY event_timestamp DESC;
~~~

`ACTION_NAME` values may need adjustment based on how records appear in your environment. Query broadly first to verify how Oracle represents the action.

### 15.3. Finding privilege changes

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       system_privilege_used,
       object_schema,
       object_name,
       return_code,
       unified_audit_policies
FROM   unified_audit_trail
WHERE  action_name IN ('GRANT', 'REVOKE')
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '30' DAY
ORDER  BY event_timestamp DESC;
~~~

For deeper analysis, inspect `SQL_TEXT` and related records within the same transaction/time window.

### 15.4. Finding activity from a host

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       client_program_name
FROM   unified_audit_trail
WHERE  userhost = 'APPHOST01'
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '24' HOUR
ORDER  BY event_timestamp DESC;
~~~

`USERHOST` is connection/client-supplied metadata per Oracle mechanisms; corroborate with network/host logs if stronger source attribution is required.

### 15.5. Finding events generated by a specific policy

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       unified_audit_policies
FROM   unified_audit_trail
WHERE  unified_audit_policies LIKE '%AUDIT_EMPLOYEE_ACCESS%'
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '7' DAY
ORDER  BY event_timestamp DESC;
~~~

`UNIFIED_AUDIT_POLICIES` can contain multiple policy names. In systems with many policies, filter by time range and inspect actual column values before relying on `LIKE`.

## 16. Common pitfalls and misconceptions

**"Having Unified Auditing means everything is recorded."** No. Only actions covered by enabled audit policies or configured audit sources are recorded.

**"UNIFIED_AUDIT_TRAIL always contains all traditional audit records."** Do not assume this in mixed mode. Check traditional audit views/destinations if legacy mechanisms are still in use.

**"A policy existing means it is enabled."** No. Check `AUDIT_UNIFIED_ENABLED_POLICIES` to confirm active status.

**"AUDIT_TRAIL=DB enables Unified Auditing."** No. That parameter belongs to traditional auditing; unified policies are managed with `AUDIT POLICY`.

**"No records prove no action happened."** No. The policy might not have been enabled, the action may fall outside scope, records may not yet be flushed, or records may have been purged.

**"Non-zero RETURN_CODE always means failed login."** No. It can be an error from any audited action.

**"DBUSERNAME is always the end user."** No. Connection pools often share one database account. Use `CLIENT_IDENTIFIER` and application logs to identify the business user.

**"FGA completely replaces Unified Auditing."** No. FGA adds fine-grained conditions on objects/columns; unified policies remain essential for actions, privileges, and broader events.

**"Increasing retention is enough."** No. Archival, storage capacity, access controls, legal holds, and cleanup procedures are all required.

**"Records can be deleted using DELETE from AUDSYS."** No. Use `DBMS_AUDIT_MGMT` and supported procedures.

**"Auditing all SELECTs is always better."** No. Broad auditing generates huge volumes, impacts operations, and expands sensitive data requiring protection.

**"AUDIT_ADMIN should be granted to applications."** No. It is an audit administration role; applications do not need it.

## 17. Hands-on exercises

Run exercises in a test database or authorized PDB. Never create broad policies in production just for testing.

### Exercise 1 — Check Unified Auditing mode

Query `V$OPTION` and determine whether the database runs in pure or mixed mode. Explain why `FALSE` does not mean unified policies cannot be used.

### Exercise 2 — Inspect predefined policies

Query `AUDIT_UNIFIED_POLICIES` and `AUDIT_UNIFIED_ENABLED_POLICIES`. Record which `ORA_*` policies exist and which are currently enabled.

### Exercise 3 — Audit SELECT on an object

Create a test table with non-sensitive data. Create a `SELECT` policy, enable it for a test user, run queries, and locate the records in `UNIFIED_AUDIT_TRAIL`.

### Exercise 4 — Audit successes/failures

Enable a policy with `WHENEVER SUCCESSFUL`, then run valid and invalid operations in the test environment. Compare `RETURN_CODE` and audit records.

### Exercise 5 — Audit DDL

Create a policy tracking `CREATE TABLE`, `ALTER TABLE`, and `DROP TABLE`. Execute each action with a test user and inspect `ACTION_NAME`.

### Exercise 6 — Audit system privileges

Create a policy for a system privilege granted in the test schema. Exercise that privilege and inspect the resulting records.

### Exercise 7 — Enable/disable policy per user

Enable a policy for one specific user, run actions as two different users, and compare the records. Disable the policy afterward.

### Exercise 8 — Query by object and time window

Write a query retrieving `SELECT`/`UPDATE` history on a test table over 24 hours. Include `userhost`, `client_program_name`, and `return_code`.

### Exercise 9 — Read SQL_TEXT

Trigger an audited SQL statement and read `SQL_TEXT` using `DBMS_LOB.SUBSTR`. Verify access controls and sensitive data handling.

### Exercise 10 — Column-level FGA

Create an FGA policy on a test column, run `SELECT` queries both accessing and omitting the audited column. Compare records and disable the policy.

### Exercise 11 — Client identifier

Use `DBMS_SESSION.SET_IDENTIFIER` to attach a request identity. Generate an audit record and verify `CLIENT_IDENTIFIER` when populated.

### Exercise 12 — Multitenant

Create or inspect a policy in a test PDB. Identify the container of the session and records; compare local/common scope per granted privileges.

### Exercise 13 — Audit volume

Aggregate records by day, policy, and action. Identify which policy produces the largest volume and propose a tighter scope.

### Exercise 14 — Archive and cleanup

In a test environment, run an approved export/archive process, set the last archive timestamp, and run cleanup with `DBMS_AUDIT_MGMT`. Verify newer records remain and older archives are readable.

## 18. Oracle reference documentation

- [Oracle Database 19c Security Guide — Auditing Database Activity](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/introduction-to-auditing.html): auditing concepts, unified auditing, and policy design.
- [Oracle Database 19c Security Guide — Configuring and Administering Unified Auditing](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/configuring-audit-policies.html): creating, enabling, disabling, and managing unified audit policies.
- [Oracle Database 19c SQL Language Reference — CREATE AUDIT POLICY](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-AUDIT-POLICY.html): policy definition syntax.
- [Oracle Database 19c SQL Language Reference — AUDIT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/AUDIT.html): enabling audit policies.
- [Oracle Database 19c SQL Language Reference — NOAUDIT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/NOAUDIT.html): disabling audit policies.
- [Oracle Database Reference — UNIFIED_AUDIT_TRAIL](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/UNIFIED_AUDIT_TRAIL.html): columns and records in the unified audit trail.
- [Oracle Database Reference — AUDIT_UNIFIED_ENABLED_POLICIES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/AUDIT_UNIFIED_ENABLED_POLICIES.html): enabled policy status.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_AUDIT_MGMT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_AUDIT_MGMT.html): flushing, archive timestamps, and audit trail cleanup.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_FGA](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_FGA.html): Fine-Grained Auditing.
- [Oracle Database Reference — AUDIT_UNIFIED_POLICIES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/AUDIT_UNIFIED_POLICIES.html): unified audit policy metadata.

Unified Auditing provides a centralized way to manage auditing through policies and the unified audit trail. Clearly define the actions, objects, users, and success/failure conditions to monitor; enable policies with proper scope; query records by time, user, action, and object; and correlate database identities with client/application context. Audit trails must be properly authorized, archived, retained per policy, and cleaned up under approved procedures. **A good audit system records the right events for investigation, protects the evidence, and enables traceability without generating unmanageable operational volume.**
