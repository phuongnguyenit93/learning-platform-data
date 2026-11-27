# DDL/Database Event Triggers and Administrative Privilege Boundaries in Oracle

In Oracle Database, triggers do not run only when a row is inserted, updated, or deleted. The database also supports triggers reacting to DDL events such as `CREATE`, `ALTER`, `DROP`, and `TRUNCATE`, as well as database/session-level events such as `LOGON`, `LOGOFF`, `STARTUP`, `SHUTDOWN`, and `SERVERERROR`. These triggers are commonly used to log schema changes, enforce governance rules, record session logins, or execute controlled operational actions.

Running at schema-wide or database-wide scope carries greater risk than normal DML triggers. A buggy DDL trigger can block deployments; a broken `LOGON` trigger can lock users out of signing in; an auditing trigger can add load or raise errors during administrative operations. Therefore, you must clearly understand **event scope**, **trigger creation privileges**, **execution privileges used by the trigger**, and **boundaries between custom triggers and Oracle's native security/auditing mechanisms**.

This lesson belongs to the **Exceptions and Triggers** group of Database Engine Relational Oracle. It focuses on schema/database-level DDL triggers, database event triggers, `ORA_*` event-context functions, `CREATE TRIGGER` and `ADMINISTER DATABASE TRIGGER` privileges, direct grants inside trigger bodies, auditing/blocking DDL, operational limits, and diagnostics.

After this lesson, you will be able to:

- Distinguish DML triggers, DDL triggers, and database event triggers.
- Choose `ON SCHEMA` versus `ON DATABASE` based on monitoring scope.
- Recognize `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `LOGON`, `LOGOFF`, `STARTUP`, `SHUTDOWN`, and `SERVERERROR` events.
- Use `ORA_SYSEVENT`, `ORA_DICT_OBJ_NAME`, `ORA_DICT_OBJ_OWNER`, `ORA_LOGIN_USER`, and appropriate event attributes.
- Write triggers to audit DDL or block specific schema operations by policy.
- Distinguish `CREATE TRIGGER`, `CREATE ANY TRIGGER`, and `ADMINISTER DATABASE TRIGGER`.
- Understand that triggers execute with owner privileges and require direct grants in stored code.
- Identify risks when triggers affect logins, DDL deployments, and transactions.
- Inspect triggers, status, dependencies, and compilation errors via the data dictionary.
- Distinguish custom trigger auditing from Oracle Unified Auditing.
- Establish safe workflows for deploying, testing, and disabling triggers.

> **Example scope:** Syntax follows Oracle Database 19c. Objects suffixed with `_LAB` are for practice schemas. `ON DATABASE` triggers have broad scope and require appropriate administrative privileges; test them only in lab databases or DBA-approved environments.

## 1. Trigger Types and Operational Scope

Oracle provides several trigger types distinguished by the events that fire them.

| Trigger Type | Firing Events | Scope |
| --- | --- | --- |
| DML trigger | `INSERT`, `UPDATE`, `DELETE` | Table or view |
| DDL trigger | `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, and supported DDL events | Schema or database |
| Database event trigger | `LOGON`, `LOGOFF`, `STARTUP`, `SHUTDOWN`, `SERVERERROR`, `SUSPEND`, and supported events | Database |
| `INSTEAD OF` trigger | DML on non-directly-updatable views | View |

### 1.1. DML Triggers

DML triggers react to data modifications:

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_dml_lab
BEFORE UPDATE OF monthly_salary
ON employee_data_lab
FOR EACH ROW
BEGIN
    IF :NEW.monthly_salary < 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Salary cannot be negative');
    END IF;
END;
/
~~~

This trigger attaches to a table and runs when matching DML occurs. `FOR EACH ROW` makes it execute once per affected row.

### 1.2. DDL Triggers

DDL triggers execute when DDL events occur within a schema or database scope:

~~~sql
CREATE OR REPLACE TRIGGER trg_ddl_audit_lab
AFTER DDL ON SCHEMA
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name,
        object_type,
        object_name,
        object_owner,
        login_user,
        event_time
    )
    VALUES (
        ORA_SYSEVENT,
        ORA_DICT_OBJ_TYPE,
        ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER,
        ORA_LOGIN_USER,
        SYSTIMESTAMP
    );
END;
/
~~~

This is a schema-level DDL trigger. It reacts to DDL occurring within the schema containing the trigger.

### 1.3. Database Event Triggers

Database event triggers execute on database or session events, for example:

~~~sql
CREATE OR REPLACE TRIGGER trg_logon_audit_lab
AFTER LOGON ON DATABASE
BEGIN
    NULL;
END;
/
~~~

`ON DATABASE` specifies database-wide scope. The trigger can fire when a session logs on rather than when a specific table changes.

### 1.4. DDL Triggers Are Not Row Triggers

DDL triggers run per DDL statement/event and do not have `:OLD` and `:NEW` like row-level DML triggers. Never declare `FOR EACH ROW` on a DDL trigger. An `ALTER TABLE` statement is a single DDL event; the trigger does not run once per row in the table.

## 2. DDL Triggers: ON SCHEMA vs. ON DATABASE

Two common scopes:

### 2.1. ON SCHEMA

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_owner_lab
AFTER DDL ON SCHEMA
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name,
        object_type,
        object_name,
        object_owner,
        login_user,
        event_time
    )
    VALUES (
        ORA_SYSEVENT,
        ORA_DICT_OBJ_TYPE,
        ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER,
        ORA_LOGIN_USER,
        SYSTIMESTAMP
    );
END;
/
~~~

This trigger monitors only DDL within the schema owning the trigger. It fits when an application schema wants to track its own object changes without monitoring the entire database.

### 2.2. ON DATABASE

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_database_lab
AFTER DDL ON DATABASE
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name,
        object_type,
        object_name,
        object_owner,
        login_user,
        event_time
    )
    VALUES (
        ORA_SYSEVENT,
        ORA_DICT_OBJ_TYPE,
        ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER,
        ORA_LOGIN_USER,
        SYSTIMESTAMP
    );
END;
/
~~~

A database-level DDL trigger observes DDL across a wider scope, spanning multiple schemas. This is a high-impact administrative trigger; only DBAs or appropriately authorized owners should create and manage it.

### 2.3. Comparing Scopes

| Criterion | ON SCHEMA | ON DATABASE |
| --- | --- | --- |
| Scope | Schema containing the trigger | Entire database for registered events |
| Creation privilege | `CREATE TRIGGER` in own schema, per object rules | `ADMINISTER DATABASE TRIGGER` and related conditions |
| Purpose | Application change control/auditing | Database-wide governance policies/auditing |
| Risk | Affects one schema | Can affect multiple schemas and database operations |
| Operations | Usually managed by app owner with DBA | Requires DBA processes and strict privilege review |

### 2.4. ON SCHEMA Does Not Catch DDL in Other Schemas

If a trigger belongs to `APP_OWNER`, DDL executed by `DATA_OWNER` in `DATA_OWNER` falls outside `APP_OWNER`'s `ON SCHEMA` scope. If the requirement is monitoring multiple schemas, consider a database-level DDL trigger or an appropriate auditing mechanism.

Never create a trigger in an application schema and assume it provides database-wide auditing.

## 3. Common DDL Events

A DDL trigger can subscribe to one or more Oracle-supported events.

| Event | Example Operations |
| --- | --- |
| `CREATE` | `CREATE TABLE`, `CREATE VIEW`, `CREATE PROCEDURE` |
| `ALTER` | `ALTER TABLE`, `ALTER INDEX`, `ALTER PACKAGE` |
| `DROP` | `DROP TABLE`, `DROP VIEW`, `DROP PROCEDURE` |
| `TRUNCATE` | `TRUNCATE TABLE` or partition |
| `RENAME` | `RENAME` object |
| `COMMENT` | `COMMENT ON TABLE`/`COLUMN` |
| `GRANT` | `GRANT` privilege or role |
| `REVOKE` | `REVOKE` privilege or role |
| `ANALYZE` | `ANALYZE` object per supported syntax |

Always verify the exact event list and registration syntax against your release's SQL Language Reference. A trigger can catch a single event:

~~~sql
CREATE OR REPLACE TRIGGER audit_drop_lab
AFTER DROP ON SCHEMA
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name, object_type, object_name,
        object_owner, login_user, event_time
    )
    VALUES (
        ORA_SYSEVENT, ORA_DICT_OBJ_TYPE, ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER, ORA_LOGIN_USER, SYSTIMESTAMP
    );
END;
/
~~~

Or multiple events:

~~~sql
CREATE OR REPLACE TRIGGER audit_schema_ddl_lab
AFTER CREATE OR ALTER OR DROP OR TRUNCATE ON SCHEMA
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name, object_type, object_name,
        object_owner, login_user, event_time
    )
    VALUES (
        ORA_SYSEVENT, ORA_DICT_OBJ_TYPE, ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER, ORA_LOGIN_USER, SYSTIMESTAMP
    );
END;
/
~~~

Some multi-step DDL operations or special objects can fire events with specific semantics. If a policy depends strictly on a given operation, test on your exact release and verify which events the trigger receives.

## 4. BEFORE DDL and AFTER DDL

### 4.1. BEFORE DDL

A `BEFORE DDL` trigger runs before the database executes the DDL event. It is useful for checking policies and rejecting unauthorized operations:

~~~sql
CREATE OR REPLACE TRIGGER protect_table_drop_lab
BEFORE DROP ON SCHEMA
BEGIN
    IF ORA_DICT_OBJ_TYPE = 'TABLE'
       AND ORA_DICT_OBJ_NAME IN ('CUSTOMER', 'ORDERS')
    THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Dropping protected tables is not allowed'
        );
    END IF;
END;
/
~~~

If the `DROP` matches the blocked condition, the trigger raises an error and the DDL does not proceed normally.

### 4.2. AFTER DDL

An `AFTER DDL` trigger executes after the DDL event has been performed under Oracle semantics. It is typically used to log events or run post-event actions:

~~~sql
CREATE OR REPLACE TRIGGER record_table_create_lab
AFTER CREATE ON SCHEMA
WHEN (ORA_DICT_OBJ_TYPE = 'TABLE')
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name, object_type, object_name,
        object_owner, login_user, event_time
    )
    VALUES (
        ORA_SYSEVENT, ORA_DICT_OBJ_TYPE, ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER, ORA_LOGIN_USER, SYSTIMESTAMP
    );
END;
/
~~~

`WHEN` in a DDL trigger is a trigger-level filter; supported event attributes can be used in the condition. If the condition is complex or needs multiple branches, place the logic in the trigger body.

### 4.3. Choosing BEFORE vs. AFTER

| Requirement | Choice |
| --- | --- |
| Block disallowed `DROP`/`ALTER` | `BEFORE DDL` |
| Record DDL that occurred | `AFTER DDL` |
| Inspect metadata before the operation | `BEFORE DDL` |
| Record outcome/event after the operation | `AFTER DDL` |

Do not use an `AFTER` trigger to block an operation that has already executed. Conversely, a `BEFORE` trigger should not log a message saying "DDL succeeded" since the operation can still fail afterward.

## 5. Event Attributes: Reading Event Context

Oracle provides functions/attributes prefixed with `ORA_` so triggers know which event occurred and which object is involved.

### 5.1. Common DDL Attributes

| Attribute | Meaning |
| --- | --- |
| `ORA_SYSEVENT` | Event name, e.g., `CREATE`, `ALTER`, `DROP` |
| `ORA_DICT_OBJ_TYPE` | Affected object type, e.g., `TABLE`, `VIEW`, `PROCEDURE` |
| `ORA_DICT_OBJ_NAME` | Object name |
| `ORA_DICT_OBJ_OWNER` | Object owner |
| `ORA_LOGIN_USER` | Logged-in user executing the event |
| `ORA_DATABASE_NAME` | Database name |
| `ORA_INSTANCE_NUM` | Current instance number |
| `ORA_CLIENT_IP_ADDRESS` | Client IP address, if available |
| `ORA_IS_ALTER_COLUMN` | Information related to `ALTER COLUMN` in supported contexts |

Not every attribute is meaningful for every event. In a `LOGON` trigger, DDL object attributes like `ORA_DICT_OBJ_NAME` are not the focus; use attributes relevant to the event type.

### 5.2. ORA_SYSEVENT

`ORA_SYSEVENT` returns the current event:

~~~sql
IF ORA_SYSEVENT = 'DROP' THEN
    ...
END IF;
~~~

It lets one trigger handle multiple events via separate branches. However, if each event has substantially different logic, splitting triggers by event can be easier to review.

### 5.3. ORA_DICT_OBJ_NAME and ORA_DICT_OBJ_OWNER

These two attributes identify the affected object:

~~~sql
DBMS_OUTPUT.PUT_LINE(
    ORA_DICT_OBJ_OWNER || '.' ||
    ORA_DICT_OBJ_NAME || ' (' ||
    ORA_DICT_OBJ_TYPE || ')'
);
~~~

For events not tied to a specific object, object attributes may hold no useful value. Never assume they are always non-`NULL`.

### 5.4. ORA_LOGIN_USER

`ORA_LOGIN_USER` indicates the logged-in database user associated with the event. This is useful audit metadata, but it does not equal the final human identity in all applications. Many applications share a single database service account across numerous end users; if end-user identity is required, the application must pass/record a trusted context via a managed mechanism.

### 5.5. ORA_CLIENT_IP_ADDRESS

Records the client IP address when supplied by the environment. Do not treat the IP as complete authentication identity. NAT, proxies, connection pools, and middle tiers often cause the IP to be only the application server's address.

### 5.6. ORA_SQL_TXT

Inside a DDL trigger, `ORA_SQL_TXT` can return text fragments of the SQL statement that fired the event. This is useful for investigation, though fragments must be concatenated properly while respecting length and data-type limits. Never re-execute captured SQL text.

Conceptual example:

~~~sql
DECLARE
    l_sql_parts ORA_NAME_LIST_T;
    l_part_count PLS_INTEGER;
    l_sql_text CLOB;
BEGIN
    l_part_count := ORA_SQL_TXT(l_sql_parts);

    FOR i IN 1 .. l_part_count LOOP
        l_sql_text := l_sql_text || l_sql_parts(i);
    END LOOP;

    -- Write l_sql_text to audit table if policy permits.
END;
/
~~~

Verify data types and limits of `ORA_NAME_LIST_T`/`ORA_SQL_TXT` in documentation for your release. SQL statements can contain sensitive literals; consider masking and audit-log access control before storing full text.

## 6. Creating an Audit Table and DDL Trigger

The following example illustrates DDL auditing in a lab schema.

### 6.1. Creating the Audit Table

~~~sql
CREATE TABLE ddl_audit_lab (
    audit_id       NUMBER GENERATED BY DEFAULT AS IDENTITY,
    event_name     VARCHAR2(30),
    object_type    VARCHAR2(30),
    object_name    VARCHAR2(128),
    object_owner   VARCHAR2(128),
    login_user     VARCHAR2(128),
    database_name  VARCHAR2(128),
    client_ip      VARCHAR2(64),
    event_time     TIMESTAMP WITH TIME ZONE,
    CONSTRAINT pk_ddl_audit_lab PRIMARY KEY (audit_id)
);
~~~

Identity columns are supported in modern releases; if targeting an older database, use a sequence and corresponding key-generation mechanism.

### 6.2. Creating a Schema-Level DDL Audit Trigger

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_schema_lab
AFTER DDL ON SCHEMA
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name,
        object_type,
        object_name,
        object_owner,
        login_user,
        database_name,
        client_ip,
        event_time
    )
    VALUES (
        ORA_SYSEVENT,
        ORA_DICT_OBJ_TYPE,
        ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER,
        ORA_LOGIN_USER,
        ORA_DATABASE_NAME,
        ORA_CLIENT_IP_ADDRESS,
        SYSTIMESTAMP
    );
END;
/
~~~

The trigger belongs to the schema owning the audit table. When the owner runs DDL in that schema, the trigger logs the event and object metadata.

### 6.3. Testing

~~~sql
CREATE TABLE ddl_probe_lab (
    id NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);

ALTER TABLE ddl_probe_lab ADD created_at TIMESTAMP;

CREATE INDEX ix_ddl_probe_lab ON ddl_probe_lab(id);

SELECT
    audit_id,
    event_name,
    object_type,
    object_name,
    object_owner,
    login_user,
    event_time
FROM ddl_audit_lab
ORDER BY audit_id;
~~~

You will see the corresponding `CREATE`/`ALTER` events. The exact events recorded depend on the DDL statements actually executed and the trigger event registration.

### 6.4. Self-Auditing DDL Triggers Are Also Dependencies

The trigger depends on `DDL_AUDIT_LAB`. If the audit table is dropped/altered incompatibly or `INSERT` privilege is revoked, the trigger can become `INVALID` or fail at runtime. Subsequent DDL in the schema can then be impacted by the broken audit trigger.

Protect the audit table, monitor trigger status, and maintain a plan to disable/restore triggers during migrations when needed.

## 7. Database-Level DDL Triggers

When monitoring DDL across multiple schemas is needed, a database-level trigger can be an option:

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_database_lab
AFTER DDL ON DATABASE
BEGIN
    INSERT INTO audit_owner.ddl_audit_lab (
        event_name,
        object_type,
        object_name,
        object_owner,
        login_user,
        database_name,
        client_ip,
        event_time
    )
    VALUES (
        ORA_SYSEVENT,
        ORA_DICT_OBJ_TYPE,
        ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER,
        ORA_LOGIN_USER,
        ORA_DATABASE_NAME,
        ORA_CLIENT_IP_ADDRESS,
        SYSTIMESTAMP
    );
END;
/
~~~

This example assumes the trigger owner has been granted direct `INSERT` privilege on `AUDIT_OWNER.DDL_AUDIT_LAB`. Schema names and privileges must match your real environment.

### 7.1. Separating Trigger Owner and Audit Owner

~~~text
SECURITY_ADMIN
  - owns database DDL trigger
  - receives ADMINISTER DATABASE TRIGGER
  - receives direct INSERT on AUDIT_OWNER.DDL_AUDIT

AUDIT_OWNER
  - owns audit table
  - controls retention and read access

APPLICATION_OWNER
  - owns application objects
  - does not need database-wide trigger privilege
~~~

This model separates trigger administration, audit data ownership, and application development. Grant least privilege; never make `SYS` or a `DBA` account the application owner merely to create triggers.

### 7.2. Controlling Database-Level Scope

A database-level DDL trigger can run for operations from many schemas. Therefore:

- Log only genuinely needed metadata.
- Avoid calling complex business packages inside the trigger.
- Never perform heavy processing or deep dictionary queries per DDL.
- Plan for failures when the audit table or audit tablespace hits an error.
- Test administrative, deployment, patching, and maintenance workflows.

### 7.3. Database-Wide Triggers Can Become a Single Point of Failure

If a database-wide trigger fails for every DDL, multiple application teams may be blocked from deploying objects. If a `LOGON` trigger fails, many users may be unable to log in. This is why privileges to create and manage database-level triggers must be strictly limited and paired with a recovery runbook.

## 8. Database Event Triggers

Database event triggers react to database-level or session-level events. General syntax:

~~~sql
CREATE OR REPLACE TRIGGER trigger_name
{BEFORE | AFTER} event_name
ON DATABASE
BEGIN
    ...
END;
/
~~~

Common events include:

| Event | Common Timing | Illustrative Purpose |
| --- | --- | --- |
| `LOGON` | `AFTER LOGON` | Log session sign-in, initialize context |
| `LOGOFF` | `BEFORE LOGOFF` | Log session ending |
| `STARTUP` | `AFTER STARTUP` | Log database open/startup event |
| `SHUTDOWN` | `BEFORE SHUTDOWN` | Log activity before database shutdown |
| `SERVERERROR` | `AFTER SERVERERROR` | Track specific server errors |
| `SUSPEND` | `AFTER SUSPEND` | Handle details when a resumable statement suspends |

Verify event availability and supported timing against the SQL Language Reference. Do not assume one timing applies to all events.

## 9. LOGON Triggers

### 9.1. Auditing Logins

Create a session audit table:

~~~sql
CREATE TABLE logon_audit_lab (
    audit_id NUMBER GENERATED BY DEFAULT AS IDENTITY,
    login_user VARCHAR2(128),
    event_time TIMESTAMP WITH TIME ZONE,
    client_ip VARCHAR2(64),
    database_name VARCHAR2(128)
);
~~~

Trigger:

~~~sql
CREATE OR REPLACE TRIGGER audit_logon_lab
AFTER LOGON ON DATABASE
BEGIN
    INSERT INTO logon_audit_lab (
        login_user,
        event_time,
        client_ip,
        database_name
    )
    VALUES (
        ORA_LOGIN_USER,
        SYSTIMESTAMP,
        ORA_CLIENT_IP_ADDRESS,
        ORA_DATABASE_NAME
    );
END;
/
~~~

This is a conceptual example. The trigger owner must hold direct `INSERT` privilege on the audit table if it resides in another schema.

### 9.2. Risks of LOGON Triggers

A `LOGON` trigger sits directly in the login path. If it:

- Calls an `INVALID` object.
- Inserts into an inaccessible table.
- Calls a timing-out network service.
- Hits quota/tablespace errors.
- Raises an unhandled exception.

then logins can fail. Never put heavy queries, remote calls, or complex business logic inside a `LOGON` trigger.

### 9.3. LOGON Triggers and Application Users

A single database user can serve thousands of end users through a connection pool. `ORA_LOGIN_USER` identifies only the database account. If end-user identity is needed, use an application context set securely after authentication; never trust arbitrary client-supplied values.

### 9.4. Setting Session Context

`LOGON` triggers are sometimes used to configure session-level defaults or contexts. Ensure that:

- Configured values do not depend on untrusted data.
- Context from a prior pooled session never leaks to a new request.
- Context is reset when returning connections to the pool.
- Triggers are never used to grant privileges bypassing application authorization.

## 10. LOGOFF Triggers

A `LOGOFF` trigger can log session termination:

~~~sql
CREATE OR REPLACE TRIGGER audit_logoff_lab
BEFORE LOGOFF ON DATABASE
BEGIN
    NULL;
END;
/
~~~

In practice, `LOGOFF` triggers require great caution:

- Sessions can terminate abruptly due to errors or dropped network connections.
- Never depend on the trigger always executing to record every disconnect.
- Never perform long-running work on the logoff path.
- Use dedicated session monitoring/auditing if high operational coverage is required.

`LOGOFF` triggers do not replace session monitoring, client-disconnect tracking, or Unified Auditing.

## 11. STARTUP and SHUTDOWN Triggers

### 11.1. AFTER STARTUP

Example:

~~~sql
CREATE OR REPLACE TRIGGER record_startup_lab
AFTER STARTUP ON DATABASE
BEGIN
    INSERT INTO database_event_audit_lab (
        event_name,
        event_time,
        login_user
    )
    VALUES (
        'STARTUP',
        SYSTIMESTAMP,
        ORA_LOGIN_USER
    );
END;
/
~~~

`AFTER STARTUP` fires on startup events at Oracle-supported timing. The trigger should do minimal work and depend as little as possible on objects that may not be ready.

### 11.2. BEFORE SHUTDOWN

~~~sql
CREATE OR REPLACE TRIGGER record_shutdown_lab
BEFORE SHUTDOWN ON DATABASE
BEGIN
    NULL;
END;
/
~~~

Never use a `SHUTDOWN` trigger to perform large backups, call remote services, or run multi-minute procedures. Shutdown operations must remain predictable; complex triggers make operational procedures hard to control.

### 11.3. Startup/Shutdown Triggers Are Not Schedulers

Startup/shutdown triggers should not serve as general job schedulers. For periodic batch work, use Oracle Scheduler or an appropriate orchestration system. Event triggers should perform only brief actions directly tied to the lifecycle event.

## 12. SERVERERROR Triggers

### 12.1. Tracking a Group of Errors

~~~sql
CREATE OR REPLACE TRIGGER audit_server_error_lab
AFTER SERVERERROR ON DATABASE
BEGIN
    IF ORA_IS_SERVERERROR(942) THEN
        INSERT INTO database_error_audit_lab (
            login_user,
            error_code,
            event_time
        )
        VALUES (
            ORA_LOGIN_USER,
            ORA_SERVER_ERROR(1),
            SYSTIMESTAMP
        );
    END IF;
END;
/
~~~

This example filters for `ORA-00942` (table or view does not exist). `ORA_IS_SERVERERROR` checks whether the error code appears in the current stack; `ORA_SERVER_ERROR(n)` reads the error code at position `n` per Oracle's API.

### 12.2. Do Not Log Every Error Indiscriminately

A `SERVERERROR` trigger can be fired by errors caused by the trigger or audit logic itself, causing loops or secondary failures. Make sure to:

- Filter for a meaningful set of error codes.
- Avoid complex queries.
- Avoid referencing objects likely to trigger the same error.
- Avoid letting the audit table become an unstable dependency.
- Test what happens when the audit table is unavailable.

### 12.3. SERVERERROR Does Not Replace Application Error Handling

This trigger does not provide full application request context and does not replace exception handling at the API/service layer. Handle errors where business context exists, while using auditing/monitoring for database-wide investigation.

## 13. SUSPEND Events and Resumable Space Allocation

Oracle supports `AFTER SUSPEND` event triggers for situations where a resumable statement is suspended, typically due to space or resource limits required for the operation. This is a specialized administrative feature, not a general trigger for ordinary SQL errors.

~~~sql
CREATE OR REPLACE TRIGGER audit_suspend_lab
AFTER SUSPEND ON DATABASE
BEGIN
    NULL;
END;
/
~~~

When using this event, study resumable space allocation, timeouts, and the functions providing error/segment details in Oracle's release documentation. Never embed logic that grants unlimited storage automatically or alters system configuration inside a trigger.

## 14. Trigger Creation Privileges: CREATE TRIGGER, ANY, and ADMINISTER DATABASE TRIGGER

This is the most critical privilege boundary in this lesson.

### 14.1. CREATE TRIGGER

`CREATE TRIGGER` allows a user to create triggers in their own schema according to Oracle rules. For example, `APP_OWNER` can create DML triggers on its own tables or schema-level DDL triggers:

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_lab
AFTER DDL ON SCHEMA
BEGIN
    NULL;
END;
/
~~~

This privilege does not grant permission to create triggers in another user's schema or database-wide triggers.

### 14.2. CREATE ANY TRIGGER

`CREATE ANY TRIGGER` is a broader system privilege allowing trigger creation in another user's schema under Oracle rules. It is a powerful privilege because a trigger can execute inside the target schema's DML/DDL flows.

Never grant `CREATE ANY TRIGGER` to ordinary developers just for convenience when deploying triggers into an application schema. Let the schema owner create its own objects or use a managed deployment identity.

### 14.3. ADMINISTER DATABASE TRIGGER

`ADMINISTER DATABASE TRIGGER` is the system privilege governing creation and administration of database-level triggers. It permits creating database-scoped triggers for supported DDL/database events.

This privilege has broad impact: a grantee can create triggers affecting multiple schemas or all sessions. Grant it only to trusted DBAs/security administrators under change management controls.

### 14.4. Do Not Confuse the Three Privileges

| Privilege | Primary Scope | Impact Level |
| --- | --- | --- |
| `CREATE TRIGGER` | Create triggers in own schema | Schema owner |
| `CREATE ANY TRIGGER` | Create triggers in other schemas | Broad; impacts other schemas |
| `ADMINISTER DATABASE TRIGGER` | Create/administer database-level triggers | Entire database |

Verify exact privilege names and conditions in your release's SQL Language Reference / Administrator's Guide. Never grant privileges based on guessing from their names.

### 14.5. ALTER ANY TRIGGER and DROP ANY TRIGGER

Administering triggers in another schema may require corresponding system privileges such as `ALTER ANY TRIGGER` or `DROP ANY TRIGGER`, depending on the operation. `ANY` privileges have broad scope and must be restricted.

Trigger owners normally manage their own triggers; DBAs use appropriate administrative privileges. Separate create, alter, enable/disable, and drop privileges following least privilege if organizational processes require it.

## 15. Execution Privileges: Definer Rights and Direct Grants

The privilege to create a trigger and the privileges the trigger uses at runtime are two separate concerns.

### 15.1. Triggers Execute with Owner Privileges

PL/SQL triggers run under the privileges of the schema owning the trigger following the definer-rights model; triggers do not have an `AUTHID CURRENT_USER` clause like procedures or packages. Therefore, objects referenced inside the trigger body require appropriate privileges for the trigger owner.

### 15.2. Direct Grants for Cross-Schema Objects

Suppose `AUDIT_OWNER` owns the table:

~~~sql
CREATE TABLE ddl_audit_lab (
    event_name VARCHAR2(30),
    object_name VARCHAR2(128),
    event_time TIMESTAMP
);
~~~

`SECURITY_ADMIN` owns the database trigger and needs to write to the audit table:

~~~sql
GRANT INSERT ON audit_owner.ddl_audit_lab TO security_admin;
~~~

Trigger body:

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_db_lab
AFTER DDL ON DATABASE
BEGIN
    INSERT INTO audit_owner.ddl_audit_lab (
        event_name,
        object_name,
        event_time
    )
    VALUES (
        ORA_SYSEVENT,
        ORA_DICT_OBJ_NAME,
        SYSTIMESTAMP
    );
END;
/
~~~

`INSERT` privilege is granted directly to `SECURITY_ADMIN`. A role holding `INSERT` privilege does not substitute for a direct object grant when compiling static SQL in stored definer-rights code.

### 15.3. Triggers Do Not Automatically Gain SYS Privileges

Creating a database-level trigger does not turn the trigger owner into `SYS` and does not grant all database administrative privileges to the trigger body. The trigger executes with its owner's privileges and legitimately granted privileges. Never use `ADMINISTER DATABASE TRIGGER` as an excuse to also grant `DBA`/`SYSDBA` to the owner.

### 15.4. Least Privilege for the Trigger Owner

A dedicated schema may need only:

- The privilege to create/administer database triggers as required.
- Direct `INSERT` on the audit table.
- `EXECUTE` on truly necessary utility packages.
- `SELECT` on required metadata/objects if permitted.

Avoid granting `DBA`, `SELECT ANY TABLE`, `EXECUTE ANY PROCEDURE`, or other broad privileges when the trigger only needs to insert a few audit columns.

## 16. Administrative Boundaries: Triggers Do Not Replace Object Privileges

### 16.1. Trigger Policies Are Not the Sole Authorization Layer

A `BEFORE DROP` trigger can block certain operations by object name, but it does not replace:

- Object privileges.
- System privileges.
- Role design.
- Schema ownership.
- Separation of duties.
- Oracle auditing.
- Change management procedures.

A trigger can be disabled or dropped by an owner or sufficiently privileged administrator. Users with high administrative privileges may have operational paths outside trigger policies. Thus, triggers serve only as an additional control layer.

### 16.2. Protect Objects with Privileges First

If developers are not allowed to `DROP` a production table, do not grant unnecessary `DROP`/`ALTER` privileges and hope a DDL trigger will stop them. Enforce object/schema privileges properly and use deployment accounts with approved scopes.

### 16.3. Database-Level Triggers Are Sensitive Privileges

A `LOGON` trigger can affect every sign-in; a DDL trigger can affect multiple schemas. Privileges to create database triggers must be governed as system administration privileges, with approvals, code reviews, testing, and rollback plans.

## 17. DDL Transaction Semantics and Trigger Side Effects

### 17.1. DDL Performs Implicit Commits

Oracle DDL typically performs an implicit commit before executing and commits after the DDL succeeds under Oracle's transaction rules. Therefore, never treat DDL like an `UPDATE` statement that can be rolled back within the same transaction.

If an application runs:

~~~sql
UPDATE business_table SET status = 'READY';
CREATE TABLE new_table (...);
ROLLBACK;
~~~

the `UPDATE` may already be committed before the DDL runs. The subsequent `ROLLBACK` will not undo what was committed by the implicit commit.

### 17.2. Trigger Bodies Are Not for Transaction Management

Do not arbitrarily call `COMMIT` or `ROLLBACK` inside a trigger. Normal triggers run within the transaction context of the triggering statement; trigger errors can impact the statement. If auditing must persist independently of the main transaction, intentionally design an autonomous transaction and understand that audit records can remain even if the business/DDL operation fails to complete.

### 17.3. Use Autonomous Transactions Only with Clear Requirements

Conceptual example:

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_autonomous_lab
AFTER DDL ON SCHEMA
DECLARE
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name, object_type, object_name,
        object_owner, login_user, event_time
    )
    VALUES (
        ORA_SYSEVENT, ORA_DICT_OBJ_TYPE, ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER, ORA_LOGIN_USER, SYSTIMESTAMP
    );

    COMMIT;
END;
/
~~~

This is a technical pattern, not a default recommendation. An autonomous transaction can write an audit record even if the outer DDL fails or is aborted. That can be useful for recording attempts, but you must clearly distinguish `ATTEMPTED` from `SUCCEEDED`; never log an entry implying the DDL definitely succeeded merely because the trigger ran.

### 17.4. Avoid Nested DDL Inside DDL Triggers

Do not design DDL triggers to automatically create, drop, or alter multiple objects whenever another DDL occurs. That easily leads to recursion, hard-to-manage dependencies, unpredictable implicit commits, and system-trigger restrictions. Use deployment tools or controlled Oracle Scheduler jobs for migrations instead of turning a DDL trigger into a self-modifying schema engine.

## 18. Blocking DDL by Policy

One use case for `BEFORE DDL` is preventing `DROP` on critical tables in a schema:

~~~sql
CREATE OR REPLACE TRIGGER protect_core_tables_lab
BEFORE DROP ON SCHEMA
BEGIN
    IF ORA_DICT_OBJ_TYPE = 'TABLE'
       AND ORA_DICT_OBJ_NAME IN (
           'CUSTOMER',
           'ORDERS',
           'PAYMENT'
       )
    THEN
        RAISE_APPLICATION_ERROR(
            -20030,
            'Core table cannot be dropped by this schema policy'
        );
    END IF;
END;
/
~~~

### 18.1. Using Controlled Allowlists/Denylists

A policy can evaluate:

- `CREATE`/`ALTER`/`DROP` events.
- Object type.
- Object name/owner.
- Login user.
- Timestamp or change window.

Avoid hard-coding excessive rules inside the trigger if policies change frequently. Policies can live in a protected configuration table, provided reading it is fast and there is a plan if the table becomes inaccessible.

### 18.2. Do Not Use Unqualified Object Names as Security Boundaries

Object names can collide across schemas. For database-level triggers, inspect both `ORA_DICT_OBJ_OWNER` and `ORA_DICT_OBJ_NAME`. Object names follow Oracle identifier rules; quoted identifiers behave differently from default uppercase identifiers.

### 18.3. Policy Triggers Need a Break-Glass Mechanism

If a trigger mistakenly blocks a required DDL operation, DBAs need a recovery workflow:

1. Identify the trigger and error.
2. Use an approved administrative account.
3. Temporarily disable the trigger if policy permits.
4. Execute the approved DDL.
5. Re-enable the trigger.
6. Verify status and record an audit/change log.

Never create a policy trigger without an operational plan for when the trigger itself breaks.

## 19. Audit Data, Unified Auditing, and Trigger Limitations

### 19.1. Trigger Auditing Is a Custom Mechanism

DDL triggers can capture metadata in application-specific formats, such as batch ID, module, owner, object type, or deployment tags. This helps internal workflows, but has limitations:

- Triggers can be disabled or dropped by sufficiently privileged users.
- Triggers can become `INVALID` or fail due to dependencies.
- Triggers can cause DDL failures if the audit insert fails.
- Triggers record only events and context their code was written to handle.
- Dynamic SQL or application-level identities may not be captured completely.

### 19.2. Unified Auditing

Oracle Unified Auditing is the database's built-in auditing architecture with dedicated policies and audit trails. For security and compliance requirements, evaluate Unified Auditing and appropriate audit policies instead of building custom triggers for every audit need.

Example audit policy statement to be tailored to tracked actions/objects and release:

~~~sql
CREATE AUDIT POLICY audit_ddl_policy_lab
    ACTIONS CREATE TABLE, ALTER TABLE, DROP TABLE;

AUDIT POLICY audit_ddl_policy_lab;
~~~

Check exact syntax and supported actions in your release's SQL Language Reference, Licensing, and Administrator's Guide. Unified Auditing maintains dedicated configuration, retention, and audit-trail access controls.

### 19.3. Do Not Store Unnecessary Sensitive Data

`ORA_SQL_TXT` can contain literals from DDL statements. Logon/servererror metadata can also be sensitive. Follow these practices:

- Record only necessary fields.
- Mask literals/secrets when present.
- Restrict `SELECT` access on audit tables.
- Define retention and archiving policies.
- Protect audit tablespaces and backups.
- Avoid writing passwords, tokens, or credentials to logs.

### 19.4. Audit Triggers Are Not the Sole Authoritative Evidence

When investigating who ran DDL, when, with what outcome, and from where, combine Unified Auditing, database logs, deployment pipelines, application identities, and change-management records. Trigger audits can serve as a supplementary source.

## 20. Enabling, Disabling, and Managing Triggers

### 20.1. Viewing Triggers

~~~sql
SELECT
    trigger_name,
    trigger_type,
    triggering_event,
    base_object_type,
    table_name,
    status
FROM user_triggers
ORDER BY trigger_name;
~~~

`USER_TRIGGERS` displays triggers in the current schema. `ALL_TRIGGERS` and `DBA_TRIGGERS` expand scope based on privileges.

### 20.2. Viewing Database-Level Triggers

In the appropriate view, inspect `BASE_OBJECT_TYPE` and `TRIGGERING_EVENT` to distinguish table, schema, and database triggers. For database-level triggers, `TABLE_NAME` may not apply the way it does for table triggers.

### 20.3. Enable/Disable

~~~sql
ALTER TRIGGER audit_ddl_schema_lab DISABLE;

ALTER TRIGGER audit_ddl_schema_lab ENABLE;
~~~

Disabling a trigger is an important operational change. While disabled, events are neither audited nor blocked by that trigger. Audit enable/disable actions themselves through an appropriate mechanism.

### 20.4. Checking Compilation Errors

~~~sql
SELECT name, type, line, position, text
FROM user_errors
WHERE type = 'TRIGGER'
ORDER BY name, sequence;
~~~

An `INVALID` trigger can cause event processing errors when fired. Always compile and test before enabling in production.

### 20.5. Dropping a Trigger

~~~sql
DROP TRIGGER audit_ddl_schema_lab;
~~~

Only the owner or an appropriately authorized user can drop a trigger. For database-level triggers, follow database trigger administration privileges and change processes.

## 21. Checking Privileges and Dependencies

### 21.1. Current User System Privileges

~~~sql
SELECT privilege
FROM user_sys_privs
ORDER BY privilege;
~~~

`SESSION_PRIVS` shows active system privileges in the current session:

~~~sql
SELECT privilege
FROM session_privs
ORDER BY privilege;
~~~

To inspect other users' privileges, DBAs can query `DBA_SYS_PRIVS`/`DBA_ROLE_PRIVS` according to granted privileges.

### 21.2. Direct Object Grants

~~~sql
SELECT
    owner,
    table_name,
    grantee,
    privilege,
    grantable
FROM all_tab_privs
WHERE grantee = USER
ORDER BY owner, table_name, privilege;
~~~

This checks object privileges visible to the session. For stored triggers, verify direct privileges for the trigger owner rather than checking only role memberships.

### 21.3. Trigger Dependencies

~~~sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM user_dependencies
WHERE type = 'TRIGGER'
ORDER BY name, referenced_owner, referenced_name;
~~~

Dependencies reveal tables, packages, and types referenced by triggers. Dynamic SQL may not be fully represented.

### 21.4. Object Status

~~~sql
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_type = 'TRIGGER'
ORDER BY object_name;
~~~

Before enabling a trigger, confirm its status is `VALID` and no errors remain in `USER_ERRORS`.

## 22. Operational Risks and Mitigations

### 22.1. Triggers Causing DDL Deployments to Fail

An auditing DDL trigger depends on its audit table. If the tablespace fills up, the audit table becomes unavailable, or `INSERT` privilege is revoked, DDL in the trigger's scope can fail. Define a clear policy:

- Fail closed: block DDL if the audit cannot be written.
- Fail open: allow DDL while reporting audit failures through another channel.

This is a governance/security decision. Never arbitrarily pick fail-open for mandatory auditing or fail-closed for all DDL without impact assessment.

### 22.2. LOGON Triggers Blocking Logins

Keep logic minimal, avoid remote calls, and avoid complex dependencies. Always maintain a DBA recovery path to disable the trigger if an error locks normal users out of logging in.

### 22.3. SERVERERROR Triggers Creating Error Loops

If an audit trigger encounters an error and that error re-fires the `SERVERERROR` trigger, an error loop can occur. Filter events, avoid dependent queries, and test scenarios where the audit table is unavailable.

### 22.4. Database-Level Triggers Increasing Coupling

A database-wide trigger can couple many schemas to a shared audit table or package. If the audit owner alters table structure or a package turns `INVALID`, wide database operations can break. Decouple dependencies, test thoroughly, and manage versions carefully.

### 22.5. Use Scheduler for Long-Running Tasks

Triggers should react quickly. If you need to send emails, call external services, process files, or run long reports, enqueue an event/job into a queue or coordination table and let Oracle Scheduler or an application worker process it asynchronously. Never prolong DDL or login execution with asynchronous work.

## 23. Comprehensive Lab

This lab uses a dedicated schema and creates only schema-level DDL triggers so no database-wide privileges are needed.

### Step 1 — Create the Audit Table

~~~sql
CREATE TABLE ddl_audit_lab (
    audit_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_name VARCHAR2(30),
    object_type VARCHAR2(30),
    object_name VARCHAR2(128),
    object_owner VARCHAR2(128),
    login_user VARCHAR2(128),
    event_time TIMESTAMP WITH TIME ZONE
);
~~~

### Step 2 — Create the DDL Trigger

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_lab
AFTER DDL ON SCHEMA
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name,
        object_type,
        object_name,
        object_owner,
        login_user,
        event_time
    )
    VALUES (
        ORA_SYSEVENT,
        ORA_DICT_OBJ_TYPE,
        ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER,
        ORA_LOGIN_USER,
        SYSTIMESTAMP
    );
END;
/
~~~

### Step 3 — Create and Alter Test Objects

~~~sql
CREATE TABLE ddl_probe_lab (
    id NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);

ALTER TABLE ddl_probe_lab ADD created_at TIMESTAMP;

CREATE INDEX ix_ddl_probe_lab ON ddl_probe_lab(id);
~~~

### Step 4 — Inspect the Audit Table

~~~sql
SELECT
    audit_id,
    event_name,
    object_type,
    object_name,
    object_owner,
    login_user,
    event_time
FROM ddl_audit_lab
ORDER BY audit_id;
~~~

### Step 5 — Create a Trigger Blocking DROP on Protected Tables

~~~sql
CREATE OR REPLACE TRIGGER protect_ddl_probe_lab
BEFORE DROP ON SCHEMA
BEGIN
    IF ORA_DICT_OBJ_TYPE = 'TABLE'
       AND ORA_DICT_OBJ_NAME = 'DDL_PROBE_LAB'
    THEN
        RAISE_APPLICATION_ERROR(
            -20031,
            'DDL_PROBE_LAB is protected'
        );
    END IF;
END;
/
~~~

Test:

~~~sql
DROP TABLE ddl_probe_lab;
~~~

The `DROP` command will be blocked by the policy trigger. Afterward, disable the trigger in the lab to clean up:

~~~sql
ALTER TRIGGER protect_ddl_probe_lab DISABLE;
DROP TABLE ddl_probe_lab PURGE;
~~~

### Step 6 — Inspect Triggers and Dependencies

~~~sql
SELECT trigger_name, triggering_event, base_object_type, status
FROM user_triggers
ORDER BY trigger_name;

SELECT name, type, referenced_name, referenced_type
FROM user_dependencies
WHERE type = 'TRIGGER'
ORDER BY name, referenced_name;

SELECT name, type, line, position, text
FROM user_errors
WHERE type = 'TRIGGER'
ORDER BY name, sequence;
~~~

### Step 7 — Clean Up Lab Objects

~~~sql
DROP TRIGGER audit_ddl_lab;
DROP TRIGGER protect_ddl_probe_lab;
DROP TABLE ddl_audit_lab PURGE;
~~~

Run cleanup commands only when sure the objects belong to the lab. `DROP` is DDL and performs an implicit commit.

## 24. Design and Deployment Checklist

**Scope**

- Is this a DDL event or a database event?
- Is `ON SCHEMA` sufficient, or is `ON DATABASE` genuinely needed?
- Which events need to be captured?
- Should the trigger run `BEFORE` or `AFTER`?
- Which event attributes are valid and necessary?

**Privileges**

- Who owns the trigger?
- Does the user hold the appropriate `CREATE TRIGGER`, `CREATE ANY TRIGGER`, or `ADMINISTER DATABASE TRIGGER` privilege?
- Does the trigger need broad `ALTER`/`DROP` privileges?
- Do cross-schema objects have direct grants?
- Are `DBA`/`SYSDBA` privileges being over-granted?

**Logic**

- Does the trigger perform the minimal amount of work possible?
- Is there any risk of recursion or re-invoking failing objects?
- Is exception handling appropriate?
- Do DDL policies include allowlists/denylists and owner qualification?
- Does full SQL text need to be saved, or only metadata?

**Operations**

- Has it been tested on a database of the same release/edition?
- What is the impact if the `LOGON`/`DDL`/`ERROR` trigger fails?
- Is there a break-glass procedure to disable/repair it?
- Are `INVALID` triggers and audit table health monitored?
- Have long-running tasks been moved to Scheduler/queues?
- Are custom triggers being misused in place of Unified Auditing?

## 25. Self-Check Questions

1. How do DDL triggers differ from DML triggers in firing events?
2. Can a DDL trigger use `FOR EACH ROW`?
3. How does `ON SCHEMA` differ from `ON DATABASE`?
4. Why cannot `ON SCHEMA` audit DDL in another schema?
5. How do `BEFORE DDL` and `AFTER DDL` differ in execution timing?
6. What does `ORA_SYSEVENT` return?
7. What are `ORA_DICT_OBJ_NAME` and `ORA_DICT_OBJ_OWNER` used for?
8. Does `ORA_LOGIN_USER` always identify the application's end user?
9. What can `ORA_SQL_TXT` be used for, and what are its risks?
10. Which database events are commonly used?
11. Why must a `LOGON` trigger keep its logic minimal?
12. What risk does a `SERVERERROR` trigger pose if audit code itself raises an error?
13. How do `CREATE TRIGGER` and `CREATE ANY TRIGGER` differ?
14. What scope does `ADMINISTER DATABASE TRIGGER` govern?
15. Why should database trigger privileges not be granted to ordinary developers?
16. Under whose privileges does a trigger execute?
17. Why are direct grants critical for stored triggers?
18. Does trigger auditing replace object privileges?
19. How does DDL's implicit commit affect triggers?
20. When should an autonomous transaction be considered for auditing?
21. Why should nested DDL inside a DDL trigger be avoided?
22. How does Unified Auditing differ in role from trigger auditing?
23. What are `USER_TRIGGERS` and `USER_ERRORS` used to inspect?
24. When should Oracle Scheduler be used instead of a trigger?
25. What procedure is needed if a `LOGON` trigger prevents users from signing in?

**Answer Key:**

1. DDL triggers fire on `CREATE`/`ALTER`/`DROP`...; DML triggers fire on `INSERT`/`UPDATE`/`DELETE`.
2. No; DDL triggers are statement/event-level, not row-level.
3. `ON SCHEMA` limits scope to the owning schema; `ON DATABASE` applies database-wide.
4. Because the trigger only receives DDL belonging to the schema that contains it.
5. `BEFORE` runs before the DDL; `AFTER` runs after the event per Oracle semantics.
6. The name of the current event.
7. Identifying the affected object and the schema owning that object.
8. No; applications may use a shared service account.
9. Capturing SQL text for investigation; requires handling length limits and sensitive data.
10. `LOGON`, `LOGOFF`, `STARTUP`, `SHUTDOWN`, `SERVERERROR`, `SUSPEND`.
11. Because trigger failures can block logins.
12. Recursive error loops and amplifying incidents.
13. `CREATE TRIGGER` creates in own schema; `CREATE ANY TRIGGER` creates in other schemas.
14. Creating/administering database-level triggers per Oracle rules.
15. Because triggers can impact multiple schemas and database-wide operations.
16. The trigger owner under the definer-rights model.
17. Stored code cannot rely on role grants when compiling static SQL; proper direct grants are required.
18. No; trigger policies are an extra layer, not a replacement for the privilege model.
19. DDL triggers an implicit commit; do not treat trigger DML as a rollbackable part of an application transaction.
20. When independent auditing is required, understanding that records may persist even if the DDL fails.
21. High risk of recursion, hard-to-manage dependencies, and unpredictable transaction behavior.
22. Unified Auditing is a native database auditing mechanism; trigger auditing is custom logic.
23. `USER_TRIGGERS` shows definitions/status; `USER_ERRORS` shows compilation errors.
24. When long-running, periodic, or asynchronous work is needed instead of synchronous trigger reactions.
25. A DBA recovery path to identify and disable/repair the trigger using an approved account.

## Oracle Reference Documentation

- [Oracle Database PL/SQL Language Reference — DDL Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/ddl-triggers.html): DDL triggers, schema/database scope, and event attributes.
- [Oracle Database PL/SQL Language Reference — System Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/system-triggers.html): database event triggers and timing.
- [Oracle Database SQL Language Reference — CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TRIGGER.html): trigger creation syntax and related privileges.
- [Oracle Database SQL Language Reference — ALTER TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TRIGGER.html): enabling, disabling, and compiling triggers.
- [Oracle Database Reference — USER_TRIGGERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TRIGGERS.html): trigger metadata in a schema.
- [Oracle Database Reference — USER_ERRORS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_ERRORS.html): compilation errors for triggers and stored objects.
- [Oracle Database Security Guide — Configuring Auditing](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/configuring-audit-policies.html): audit policies and Unified Auditing.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): database administration and system privileges.

**Key takeaway:** DDL triggers and database event triggers can impact a schema or the entire database, so trigger creation privileges must match that scope. `CREATE TRIGGER` is for schema owners; `CREATE ANY TRIGGER` extends to other schemas; `ADMINISTER DATABASE TRIGGER` permits administering database-level triggers under Oracle rules. Triggers execute with owner privileges and require direct grants for dependencies. Keep logic minimal, maintain recovery paths, rely on the privilege model and Unified Auditing as the governance foundation, and treat custom triggers as a controlled supporting layer.
