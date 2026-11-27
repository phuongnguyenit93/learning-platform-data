# Looking Up Views, Routines, Triggers, Events, and Definers

In an operational MySQL system, table structure is only part of the schema. A database can also contain views, stored procedures, stored functions, triggers, and events. These objects may contain business logic, run automatically when data changes, or execute on a schedule. When investigating unexpected behavior, preparing a migration, performing a security review, or handing over a system, you need to know which objects exist, which schema they belong to, how they are defined, and under which account's privileges they execute.

MySQL provides two primary toolsets for inspection: metadata tables in `INFORMATION_SCHEMA` and `SHOW` commands. `INFORMATION_SCHEMA` is suited for filtering, aggregating, and comparing many objects with SQL; `SHOW CREATE` is suited for viewing the complete definition statement of a single object. Both are subject to the current user's privileges, so results do not necessarily list every object present on the server.

## Learning Objectives

After this lesson, you will be able to:

- List views, procedures, functions, triggers, and events in a schema or across a server.
- Query metadata using `INFORMATION_SCHEMA` and inspect definitions using `SHOW CREATE`.
- Read `DEFINER`, `SECURITY_TYPE`, `SQL_MODE`, timestamps, and status attributes of objects.
- Distinguish invoker privileges from object definer privileges.
- Recognize when an event has been created yet has not executed because Event Scheduler is disabled.
- Handle cases where metadata is incomplete due to missing privileges or a definer that no longer exists.

## 1. Lookup Scope and Metadata Visibility Privileges

The queries in this lesson use the current database as the default scope. Check the selected database:

```sql
SELECT DATABASE() AS current_schema;
```

If the result is `NULL`, select a database using `USE database_name;` or replace the `TABLE_SCHEMA = DATABASE()` condition with a specific schema name. When inventorying multiple schemas, you can omit the schema filter while keeping access privileges and result size in mind.

`INFORMATION_SCHEMA` is a system schema providing metadata as tables and views. You can query it with `SELECT`, filter by schema name, sort, or join with other metadata tables. Do not directly access internal tables in the `mysql` schema as a substitute for public metadata APIs; internal structures can change between versions and are not a stable lookup interface.

Metadata may be restricted by privileges. Users only see objects for which they hold appropriate privileges; certain columns containing definition bodies may return `NULL` without viewing privileges. Therefore:

- Not seeing an object in a metadata query does not prove that the object does not exist.
- Inventory results depend on the connected account. For full-schema audits, use an inventory account granted appropriate metadata viewing privileges.
- Privilege to view a definition differs from privilege to execute or alter an object.
- Specific privileges vary by object type and MySQL version. Common privileges include `SHOW VIEW`, `TRIGGER`, `EVENT`, `CREATE ROUTINE`, `ALTER ROUTINE`, `EXECUTE`, and the dynamic `SHOW_ROUTINE` privilege on supported versions.

## 2. Looking Up Views

A view is a schema object storing a `SELECT` query definition. When an application reads a view, MySQL processes that definition as a data-access layer. Views can encapsulate joins, standardize data reads, or restrict exposed columns.

### 2.1. Listing views in a schema

`INFORMATION_SCHEMA.VIEWS` provides the view name, schema, definer, security mode, and query definition:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME AS view_name,
    DEFINER,
    SECURITY_TYPE,
    CHECK_OPTION,
    IS_UPDATABLE,
    VIEW_DEFINITION
FROM information_schema.views
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;
```

Columns to note:

| Column | Meaning |
|---|---|
| `TABLE_SCHEMA`, `TABLE_NAME` | Schema and view name |
| `DEFINER` | Account recorded as the definer |
| `SECURITY_TYPE` | `DEFINER` or `INVOKER`, determining privilege context when accessing the view |
| `CHECK_OPTION` | Validation rule when writing through an updatable view: `LOCAL`, `CASCADED`, or `NONE` |
| `IS_UPDATABLE` | Indicates whether MySQL considers the view updatable |
| `VIEW_DEFINITION` | Query portion defining the view; may be hidden if privileges are lacking |

To retrieve only the list of view names, you can use `TABLES`:

```sql
SELECT TABLE_SCHEMA, TABLE_NAME
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'VIEW'
ORDER BY TABLE_NAME;
```

`TABLES` contains both base tables and views; the condition `TABLE_TYPE = 'VIEW'` filters to the exact object type.

### 2.2. Viewing the full definition

After identifying the view name, use `SHOW CREATE VIEW`:

```sql
SHOW CREATE VIEW view_name;
```

If the view resides in a schema other than the current database, specify the schema:

```sql
SHOW CREATE VIEW schema_name.view_name;
```

The output shows the statement that creates the view, typically including `ALGORITHM`, `DEFINER`, `SQL SECURITY`, and the `SELECT` query. This is a convenient way to capture definitions when reviewing migrations or comparing two environments.

To quickly list views the current account is permitted to see:

```sql
SHOW FULL TABLES FROM schema_name
WHERE Table_type = 'VIEW';
```

`SHOW CREATE VIEW` requires privileges to view the view definition, typically `SHOW VIEW` along with appropriate object privileges. If the command reports insufficient privileges, request inspection privileges according to policy; do not guess the definition from the view name.

## 3. Looking Up Stored Procedures and Stored Functions

Stored procedures and stored functions are routines stored in a schema. Procedures are invoked with `CALL`; functions return a value and can be used inside SQL expressions according to MySQL rules.

### 3.1. Listing routines

`INFORMATION_SCHEMA.ROUTINES` contains metadata for both procedures and functions:

```sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DEFINER,
    SECURITY_TYPE,
    SQL_DATA_ACCESS,
    IS_DETERMINISTIC,
    CREATED,
    LAST_ALTERED,
    ROUTINE_DEFINITION
FROM information_schema.routines
WHERE ROUTINE_SCHEMA = DATABASE()
ORDER BY ROUTINE_TYPE, ROUTINE_NAME;
```

Meaning of key columns:

| Column | Meaning |
|---|---|
| `ROUTINE_SCHEMA`, `ROUTINE_NAME` | Schema and routine name |
| `ROUTINE_TYPE` | `PROCEDURE` or `FUNCTION` |
| `DEFINER` | Account that defined the routine |
| `SECURITY_TYPE` | Privilege context `DEFINER` or `INVOKER` |
| `SQL_DATA_ACCESS` | Declared characteristic regarding whether the routine accesses or modifies SQL data |
| `IS_DETERMINISTIC` | Whether the routine is declared deterministic |
| `CREATED`, `LAST_ALTERED` | Creation and most recent modification timestamps recorded in metadata |
| `ROUTINE_DEFINITION` | Routine body, which may be hidden due to privileges or metadata restrictions |

`SQL_DATA_ACCESS` commonly has values such as `NO SQL`, `CONTAINS SQL`, `READS SQL DATA`, and `MODIFIES SQL DATA`. This is a characteristic declared when creating the routine; do not treat it as a complete guarantee that the routine performs only the declared category of operations.

### 3.2. Looking up routine parameters

`INFORMATION_SCHEMA.PARAMETERS` shows the name, order, mode, and data type of each parameter:

```sql
SELECT
    SPECIFIC_SCHEMA,
    SPECIFIC_NAME,
    ROUTINE_TYPE,
    ORDINAL_POSITION,
    PARAMETER_MODE,
    PARAMETER_NAME,
    DATA_TYPE,
    DTD_IDENTIFIER
FROM information_schema.parameters
WHERE SPECIFIC_SCHEMA = DATABASE()
ORDER BY SPECIFIC_NAME, ORDINAL_POSITION;
```

For functions, metadata may include a row describing the return value at `ORDINAL_POSITION = 0`; input parameters follow. For procedures, `PARAMETER_MODE` can be `IN`, `OUT`, or `INOUT`. Cross-check parameter order against call statements to avoid passing the wrong type or position.

### 3.3. Viewing procedure and function definitions

```sql
SHOW CREATE PROCEDURE procedure_name;
SHOW CREATE FUNCTION function_name;
```

You can specify the schema if the routine does not belong to the current database:

```sql
SHOW CREATE PROCEDURE schema_name.procedure_name;
SHOW CREATE FUNCTION schema_name.function_name;
```

The output displays the definition statement, parameters, return type for functions, `DEFINER`, `SQL SECURITY`, `SQL_MODE`, and routine attributes. `SQL_MODE` is recorded when the routine is created or altered; the routine can execute with the mode saved alongside its definition rather than simply picking up subsequent session changes.

To list routines by type using `SHOW`:

```sql
SHOW PROCEDURE STATUS WHERE Db = DATABASE();
SHOW FUNCTION STATUS WHERE Db = DATABASE();
```

`SHOW ... STATUS` commands are handy for quick inventories; when filtering, joining, or exporting reports is needed, `INFORMATION_SCHEMA.ROUTINES` is more flexible. Viewing routine bodies may require privileges such as `SHOW_ROUTINE` or appropriate management/execution privileges depending on version.

## 4. Looking Up Triggers

A trigger is a routine attached to a table that runs automatically when an `INSERT`, `UPDATE`, or `DELETE` event occurs on that table. Triggers in MySQL are row-level triggers: they execute for each affected row, with `OLD` and `NEW` references depending on the event.

### 4.1. Listing triggers

```sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    EVENT_MANIPULATION,
    ACTION_ORIENTATION,
    ACTION_ORDER,
    DEFINER,
    SQL_MODE,
    CREATED,
    ACTION_STATEMENT
FROM information_schema.triggers
WHERE TRIGGER_SCHEMA = DATABASE()
ORDER BY EVENT_OBJECT_TABLE, ACTION_TIMING, EVENT_MANIPULATION, ACTION_ORDER;
```

Important columns:

- `EVENT_OBJECT_TABLE`: the table to which the trigger is attached.
- `ACTION_TIMING`: `BEFORE` or `AFTER`.
- `EVENT_MANIPULATION`: `INSERT`, `UPDATE`, or `DELETE`.
- `ACTION_ORDER`: execution order when multiple triggers share the same timing and event on a table.
- `DEFINER`: account that defined the trigger.
- `ACTION_STATEMENT`: trigger body.

MySQL allows multiple triggers with the same timing and event on a single table; execution order can be controlled with `FOLLOWS` or `PRECEDES` when creating triggers in supported versions. When investigating automatic update logic, inspect all triggers on the table and their order, not just the first one found.

### 4.2. Viewing trigger definitions

```sql
SHOW CREATE TRIGGER trigger_name;
```

Or specify the schema:

```sql
SHOW CREATE TRIGGER schema_name.trigger_name;
```

The output provides the trigger creation statement, associated table, timing, event, `DEFINER`, and `SQL_MODE`. To list triggers quickly:

```sql
SHOW TRIGGERS FROM schema_name;
```

`SHOW TRIGGERS` and `INFORMATION_SCHEMA.TRIGGERS` only display metadata that the account has privilege to view. Inspectors typically need the `TRIGGER` privilege on the table or version-appropriate privileges. If privileges are lacking, note that the inventory scope is limited.

### 4.3. Evaluating trigger impact

Triggers can modify secondary data, write audit logs, or validate a condition before writes. When reviewing an `UPDATE` statement that appears to touch only one table, check triggers because a trigger can induce operations on other tables, lengthen execution time, or fail the original statement.

Notably, triggers run in the transaction context of the triggering statement if the involved tables support transactions. With non-transactional tables such as MyISAM, you cannot rely on `ROLLBACK` to undo written changes. When evaluating triggers, inspect the storage engine of both the source table and any tables the trigger writes to.

## 5. Looking Up Events and Execution Schedules

An event is an object executed by the MySQL Event Scheduler at a specific time or on a recurring interval. Events suit periodic tasks such as purging expired data, aggregating metrics, or running minor maintenance jobs. Events differ from triggers in that they are triggered by schedule, not by row operations.

### 5.1. Checking the Event Scheduler

First, check the scheduler status at the server level:

```sql
SELECT @@GLOBAL.event_scheduler AS event_scheduler_status;
```

Common values:

| Value | Meaning |
|---|---|
| `ON` | Event Scheduler is active and can execute enabled events |
| `OFF` | Scheduler is off; events are stored but do not run on schedule |
| `DISABLED` | Scheduler is disabled at startup; cannot be turned on solely via `SET GLOBAL` in the current instance |

An event having `STATUS = ENABLED` does not mean it has definitely been running. The scheduler must be `ON`, start/end times must be valid, and the definer must hold required privileges. Check both the event's status and the scheduler's status.

### 5.2. Listing events

`INFORMATION_SCHEMA.EVENTS` provides schedule, time zone, definer, status, and event body information:

```sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    TIME_ZONE,
    EVENT_TYPE,
    EXECUTE_AT,
    INTERVAL_VALUE,
    INTERVAL_FIELD,
    STARTS,
    ENDS,
    STATUS,
    ON_COMPLETION,
    LAST_EXECUTED,
    EVENT_DEFINITION,
    SQL_MODE
FROM information_schema.events
WHERE EVENT_SCHEMA = DATABASE()
ORDER BY EVENT_NAME;
```

Meaning of key columns:

- `EVENT_TYPE`: one-time (`ONE TIME`) or repeating (`RECURRING`).
- `EXECUTE_AT`: execution timestamp for a one-time event.
- `INTERVAL_VALUE`, `INTERVAL_FIELD`: repeat interval and interval unit.
- `STARTS`, `ENDS`: start and end timestamps of the schedule.
- `TIME_ZONE`: time zone used to schedule and interpret event times.
- `STATUS`: whether the event is `ENABLED`, `DISABLED`, or a related version-dependent status.
- `LAST_EXECUTED`: most recent recorded execution timestamp; `NULL` may mean the event has never run.
- `DEFINER`: account under which the event executes.

### 5.3. Viewing event definitions

```sql
SHOW EVENTS FROM schema_name;
SHOW CREATE EVENT event_name;
```

If the event belongs to a schema other than the current database, specify the schema using syntax supported by your MySQL version:

```sql
SHOW CREATE EVENT schema_name.event_name;
```

`SHOW CREATE EVENT` shows the schedule, statement definition, time zone, `DEFINER`, `SQL_MODE`, and status. The `EVENT` privilege on the schema/object and appropriate definition-viewing privileges are needed to manage or inspect events.

### 5.4. Diagnosing why an event is not running

When an event does not run as expected, check in order:

1. Is `@@GLOBAL.event_scheduler` set to `ON`?
2. Is `INFORMATION_SCHEMA.EVENTS.STATUS` set to `ENABLED`?
3. Do `STARTS`, `ENDS`, `EXECUTE_AT`, and `TIME_ZONE` match the expected execution window?
4. Has `LAST_EXECUTED` updated after the expected run time?
5. Does the `DEFINER` account still exist and have sufficient privileges for the event statements?
6. Does the event body contain SQL errors, depend on renamed/dropped objects, or encounter runtime errors?

Do not enable the Event Scheduler on a shared server just to test a single event. Changing the scheduler is a server-level change that must follow operational procedures and administrative authorization.

## 6. Understanding `DEFINER` and `SQL SECURITY`

`DEFINER` is the MySQL account recorded when a view, routine, trigger, or event is created. The account is typically stored in the form `user_name`@`host_name`. It determines the privilege context of many objects at execution time—it is not a password and not necessarily the account currently connected to query metadata.

`SQL SECURITY` determines how MySQL checks privileges when accessing certain objects:

| Object | Security mode | Meaning |
|---|---|---|
| View | `DEFINER` | Querying the view uses the defining account's privileges |
| View | `INVOKER` | Querying the view uses the calling account's privileges |
| Procedure/function | `DEFINER` | Routine executes in the definer's privilege context |
| Procedure/function | `INVOKER` | Routine executes in the caller's privilege context |
| Trigger | Always definer | Trigger executes in the definer's context; does not declare `SQL SECURITY INVOKER` like views/routines |
| Event | Definer | Event executes using the privileges of the account that defined the event |

For views and routines, if omitted, `SQL SECURITY DEFINER` is typically the default. When `DEFINER` is used, a caller can access data through the object without directly holding every privilege on the underlying tables, subject to the object definition and MySQL privilege checks. This is a useful mechanism, yet requires strict control because objects can widen data access.

### 6.1. Comparing the connected account and the executing account

In a normal session:

```sql
SELECT USER() AS connection_identity,
       CURRENT_USER() AS privilege_account;
```

`USER()` shows the username and host supplied by the client when connecting. `CURRENT_USER()` shows the MySQL account used for privilege checks in the current context. Inside an object running with `SQL SECURITY DEFINER`, `CURRENT_USER()` may reflect the definer account. Therefore, when investigating privileges, distinguish the login identity from the effective account in the execution context.

### 6.2. Risk of a definer no longer existing

An object can retain `DEFINER` metadata after that account has been dropped or renamed. Such an object is often referred to as having an orphaned definer. When the object needs to run under the definer's privileges but the account no longer exists or lacks privileges, access can fail.

Inventory view definers:

```sql
SELECT TABLE_SCHEMA, TABLE_NAME, DEFINER, SECURITY_TYPE
FROM information_schema.views
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY DEFINER, TABLE_NAME;
```

Inventory routine definers:

```sql
SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE, DEFINER, SECURITY_TYPE
FROM information_schema.routines
WHERE ROUTINE_SCHEMA = DATABASE()
ORDER BY DEFINER, ROUTINE_NAME;
```

Inventory trigger and event definers:

```sql
SELECT TRIGGER_SCHEMA AS object_schema,
       TRIGGER_NAME AS object_name,
       'TRIGGER' AS object_type,
       DEFINER
FROM information_schema.triggers
WHERE TRIGGER_SCHEMA = DATABASE()
UNION ALL
SELECT EVENT_SCHEMA,
       EVENT_NAME,
       'EVENT',
       DEFINER
FROM information_schema.events
WHERE EVENT_SCHEMA = DATABASE()
ORDER BY DEFINER, object_type, object_name;
```

You can cross-check definer accounts against the account list in `mysql.user` if the auditing account is granted appropriate read privileges. However, do not grant broad read access to system tables just to run routine reports. A DBA can perform this cross-check during a controlled audit process.

Do not automatically replace `DEFINER` with a general administrative account. Before modifying it, determine the logical owner of the object, the minimum privileges the object needs, its `SQL SECURITY` mode, the accessed tables, and the impact on applications. Only then select an appropriate service account, update the definition through a migration workflow, and test using the actual calling account.

## 7. Full Schema Object Inventory Workflow

When taking over a system or preparing a migration, you can run the following queries in a session with appropriate metadata viewing privileges.

**Step 1: list views.**

```sql
SELECT TABLE_NAME, DEFINER, SECURITY_TYPE, IS_UPDATABLE
FROM information_schema.views
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;
```

**Step 2: list procedures and functions.**

```sql
SELECT ROUTINE_NAME, ROUTINE_TYPE, DEFINER, SECURITY_TYPE,
       CREATED, LAST_ALTERED
FROM information_schema.routines
WHERE ROUTINE_SCHEMA = DATABASE()
ORDER BY ROUTINE_TYPE, ROUTINE_NAME;
```

**Step 3: list triggers.**

```sql
SELECT TRIGGER_NAME, EVENT_OBJECT_TABLE, ACTION_TIMING,
       EVENT_MANIPULATION, ACTION_ORDER, DEFINER
FROM information_schema.triggers
WHERE TRIGGER_SCHEMA = DATABASE()
ORDER BY EVENT_OBJECT_TABLE, ACTION_TIMING, EVENT_MANIPULATION, ACTION_ORDER;
```

**Step 4: list events and scheduler status.**

```sql
SELECT @@GLOBAL.event_scheduler AS event_scheduler_status;

SELECT EVENT_NAME, DEFINER, EVENT_TYPE, TIME_ZONE,
       STARTS, ENDS, STATUS, LAST_EXECUTED
FROM information_schema.events
WHERE EVENT_SCHEMA = DATABASE()
ORDER BY EVENT_NAME;
```

**Step 5: inspect definitions of key objects.** Use `SHOW CREATE VIEW`, `SHOW CREATE PROCEDURE`, `SHOW CREATE FUNCTION`, `SHOW CREATE TRIGGER`, or `SHOW CREATE EVENT` according to the object type. Store the results in migration records or version control following your team's workflow.

**Step 6: review privileges and definers.** Record the definer account, `SQL SECURITY`, required caller privileges, dependencies on other tables/views/routines, and how to test execution with the application account.

Do not record only object names. A useful inventory captures definitions, privilege context, dependencies, event status, and the timestamp when metadata was collected.

## 8. Common Pitfalls When Looking Up Metadata

- Querying `TABLES` without filtering `TABLE_TYPE`, leading to confusing views with base tables.
- Querying only `ROUTINES` and skipping `PARAMETERS`, missing parameter types and ordering.
- Checking only `STATUS = ENABLED` on an event without checking `@@GLOBAL.event_scheduler`.
- Seeing `VIEW_DEFINITION`, `ROUTINE_DEFINITION`, or `ACTION_STATEMENT` as `NULL` and concluding the object has no body; the cause may be missing metadata viewing privileges.
- Assuming `DEFINER` is the currently connected user or a password; it is an account identity used for the object's privilege context.
- Checking only routines and views while overlooking triggers that fire automatically when data changes.
- Replacing a definer with a broadly privileged account without assessing privilege-escalation risk.
- Running metadata queries with a low-privilege application account and treating the output as a complete inventory of the entire schema.
- Assuming every object supports `SQL SECURITY`; triggers and events follow definer-based execution rules.

## 9. Checklist for Auditing Views, Routines, Triggers, Events, and Definers

- Selected the right schema and confirmed `DATABASE()` does not return `NULL` when using current scope.
- Inventoried views, procedures, functions, triggers, and events using `INFORMATION_SCHEMA`.
- Inspected key definitions using `SHOW CREATE`.
- Checked routine parameters, routine types, and data-access attributes.
- Checked trigger timing, events, execution order, and body.
- Checked both event status and `event_scheduler` status, time zone, and schedule.
- Recorded `DEFINER`, `SECURITY_TYPE`, `SQL_MODE`, and privileges required for execution.
- Verified that definer accounts still exist, hold appropriate least privileges, and have clear ownership.
- Confirmed the application account can actually invoke the object in the intended privilege context.
- Documented any visibility limitations from missing privileges before declaring the object list complete.

Views, routines, triggers, and events are crucial parts of a MySQL schema because they contain logic and can execute under dedicated privilege contexts. `INFORMATION_SCHEMA` supports systematic inventorying; `SHOW CREATE` reveals full definitions; and `DEFINER` and `SQL SECURITY` show who supplies privileges when logic runs. Combining all three perspectives helps you understand database behavior, uncover hidden dependencies, and manage schema changes safely.
