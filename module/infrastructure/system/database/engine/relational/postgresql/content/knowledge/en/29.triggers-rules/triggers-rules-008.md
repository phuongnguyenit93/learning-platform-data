# Event Triggers for DDL Changes in PostgreSQL

## 1. When You Need to Track or Govern Database Schema Changes

In a PostgreSQL database where multiple teams deploy schema changes, administrators need to know:

- Who created a new table or index?
- When was a table renamed, a column added, or a data type changed?
- Which objects were cascaded away by `DROP TABLE ... CASCADE`?
- Which `ALTER TABLE` change forced a full physical **table rewrite**?
- Can dangerous DDL operations be blocked by operational policy?

**Regular table triggers** do not solve these questions directly. They bind to a table's data and fire on operations like `INSERT`, `UPDATE`, `DELETE`, or `TRUNCATE`.

**Event triggers** are a distinct PostgreSQL mechanism invoked when **supported DDL commands** occur in a database—such as creating, altering, or dropping objects.

```text
                       PostgreSQL session
                               |
                          DDL command
                               |
                      +--------+---------+
                      |                  |
              ddl_command_start      Validate/run DDL
                      |                  |
             Block or inspect            |
                      |                  |
                      +--------+---------+
                               |
                     Catalog objects change
                               |
               +---------------+---------------+
               |                               |
           sql_drop                       table_rewrite
       (if objects dropped)           (if table rewritten)
               |                               |
               +---------------+---------------+
                               |
                        ddl_command_end
                               |
                   Transaction COMMIT / ROLLBACK
```

This diagram illustrates **hook points**, not a mandatory sequence for every command. For example, `table_rewrite` fires **before the table is rewritten**, during DDL execution—not after everything finishes. `sql_drop` fires after PostgreSQL has removed objects from system catalogs within that transaction. A single DDL statement need not trigger all four event types.

> **Core takeaway:** event triggers are useful for monitoring, enforcing conventions, and capturing metadata about DDL changes, yet they execute **inside the DDL command's transaction**. Audit rows inserted by an event trigger roll back with the command when the transaction fails; they do not replace independent audit logs, access privileges, or migration workflows.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Distinguish event triggers from table triggers.
2. List the four event types: `ddl_command_start`, `ddl_command_end`, `sql_drop`, and `table_rewrite`.
3. Explain when each event is emitted.
4. Write a `RETURNS event_trigger` function in PL/pgSQL.
5. Use `TG_EVENT` and `TG_TAG` in the right context.
6. Create event triggers with `CREATE EVENT TRIGGER ... ON ... EXECUTE FUNCTION`.
7. Filter by command tag using `WHEN TAG IN (...)` where supported.
8. Use `pg_event_trigger_ddl_commands()` to collect objects affected by a DDL command.
9. Use `pg_event_trigger_dropped_objects()` to identify dropped objects, including `CASCADE` effects.
10. Use `pg_event_trigger_table_rewrite_oid()` and `pg_event_trigger_table_rewrite_reason()` when a table is rewritten.
11. Understand why `ddl_command_start` lacks complete "newly created" metadata.
12. Understand the database-level scope of event triggers and which DDL commands are not covered.
13. Design a DDL audit table and recognize limitations regarding rollbacks, actor identity, and durability.
14. Block specific DDL commands in a controlled environment.
15. Avoid recursion or operational locks caused by DDL inside event triggers.
16. Understand privileges required to create event triggers and permissions of handler functions.
17. Use `SECURITY INVOKER`, `SECURITY DEFINER`, and safe `search_path` settings.
18. Query the `pg_event_trigger` catalog to inventory enabled states, owners, and tag filters.
19. Enable/disable event triggers with `ALTER EVENT TRIGGER` using appropriate privileges.
20. Test migrations involving `CREATE`, `ALTER`, `DROP`, `CASCADE`, and rollback.
21. Distinguish structural DDL metadata capture from capturing exact raw SQL text.
22. Evaluate performance costs and risks when installing event triggers on production databases.
23. Build operational, testing, and recovery checklists for when a handler fails.

## 3. How Do Event Triggers Differ From Data Triggers?

| Criterion | Table trigger | Event trigger |
| --- | --- | --- |
| Primary purpose | React to data operations on a table | React to supported DDL commands |
| Attachment scope | A table, view, or supported relation | Current database |
| Creation statement | `CREATE TRIGGER` | `CREATE EVENT TRIGGER` |
| Function return type | `trigger` | `event_trigger` |
| Typical events | `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE` | `ddl_command_start`, `ddl_command_end`, `sql_drop`, `table_rewrite` |
| Context info | `NEW`, `OLD`, `TG_OP`, ... per type | `TG_EVENT`, `TG_TAG`, and event-trigger helper functions |
| Creation privilege | Per table/trigger privilege model | `CREATE EVENT TRIGGER` requires superuser in PostgreSQL |
| Blast radius | Attached table/view | Supported DDLs across the database |
| Used for auditing table changes? | Audits row changes | Audits schema changes |
| Can block operations? | Can raise an exception in valid contexts | Can raise an exception to reject DDL |

### 3.1. Example of a table trigger (not a DDL event trigger)

```sql
CREATE TRIGGER audit_order_updates
AFTER UPDATE ON some_schema.orders
FOR EACH ROW
EXECUTE FUNCTION some_schema.audit_row();
```

This observes data `UPDATE`s on `orders`, not `ALTER TABLE orders`.

### 3.2. Example of an event trigger

```sql
CREATE EVENT TRIGGER log_schema_changes
ON ddl_command_end
EXECUTE FUNCTION admin_schema.log_ddl();
```

It does not belong exclusively to `orders`. Inside the current database, the handler is invoked whenever a supported DDL command finishes.

### 3.3. Not every "admin-looking" command is a supported event

`VACUUM`, `ANALYZE`, DML transactions, and several other commands do not emit `ddl_command_end` merely because they have operational impact. Event triggers cover a PostgreSQL-defined set of command tags; check your version and supported tag list when designing.

## 4. The Four Key Event Types

| Event | General timing | Characteristic helper functions | Example use |
| --- | --- | --- | --- |
| `ddl_command_start` | Before executing supported DDL | `TG_TAG` | Inspect/block DDL command kinds |
| `ddl_command_end` | After DDL execution completes, before commit | `pg_event_trigger_ddl_commands()` | Audit created/altered objects |
| `sql_drop` | After objects are removed from system catalogs in transaction | `pg_event_trigger_dropped_objects()` | Audit DROP and CASCADE dependencies |
| `table_rewrite` | Immediately before a table rewrite required by DDL | `pg_event_trigger_table_rewrite_oid()`, `pg_event_trigger_table_rewrite_reason()` | Detect expensive I/O and locking table rewrites |

### 4.1. `ddl_command_start`

Fires before DDL execution begins. Well-suited for rejecting a **command tag** or checking preconditions known upfront.

Do not expect to query catalog metadata of newly created objects here; those objects do not exist yet.

### 4.2. `ddl_command_end`

Fires after the DDL command has executed inside the transaction, before final commit. Catalog changes made by the command are visible within this transaction.

If the handler throws an unhandled exception, the in-flight DDL rolls back.

### 4.3. `sql_drop`

Provides information about objects dropped during DDL. Because those objects have already been removed from catalogs at this point, querying `pg_class` alone will not find dropped objects. PostgreSQL supplies dedicated metadata via `pg_event_trigger_dropped_objects()`.

### 4.4. `table_rewrite`

Certain `ALTER TABLE` commands must physically rewrite the table's heap data. This event fires right before the rewrite and provides the table OID and a reason bitmask. Not **every** `ALTER TABLE` causes a rewrite.

## 5. Lab Environment Setup and Prerequisites

**Warning:** event triggers are database-wide hooks and can affect every migration in that database. Run this lab only in a **dedicated test database**, never install arbitrarily in production.

### 5.1. Privileges to create event triggers

PostgreSQL requires **superuser** privileges to create event triggers. Managed PostgreSQL services may restrict this or expose provider-specific roles/mechanisms; never assume an ordinary application role can run it.

The DDL examples below assume you are an administrator in a lab database with permissions to:

- `CREATE SCHEMA` / `CREATE TABLE` / `CREATE FUNCTION`.
- `CREATE EVENT TRIGGER`.
- Manage event triggers via `ENABLE` / `DISABLE` / `DROP`.
- Access the lab tables.

### 5.2. Audit schema and table

```sql
CREATE SCHEMA IF NOT EXISTS et_lab;

CREATE TABLE et_lab.ddl_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    happened_at timestamptz NOT NULL
        DEFAULT clock_timestamp(),
    transaction_id bigint NOT NULL
        DEFAULT txid_current(),
    event_name text NOT NULL,
    command_tag text NOT NULL,
    effective_role name NOT NULL
        DEFAULT current_user,
    session_login name NOT NULL
        DEFAULT session_user,
    object_type text,
    schema_name text,
    object_identity text,
    in_extension boolean,
    original_drop boolean,
    normal_drop boolean,
    is_temporary boolean,
    rewrite_reason integer,
    details text
);
```

Audit fields include:

- Observed timestamp.
- Transaction ID that wrote the record.
- Event name and command tag.
- Effective PostgreSQL role and session login role.
- Object type, schema, and identity string.
- Extension, drop, and rewrite metadata.

### 5.3. Why store both current_user and session_user?

`CURRENT_USER` reflects the effective role where the expression is evaluated. `SESSION_USER` reflects the connection's original DB login and does not automatically change with `SET ROLE`.

However, inside a `SECURITY DEFINER` function, `CURRENT_USER` is the **function owner**, not the role that issued the DDL. And if an application shares one DB login across all users, `SESSION_USER` cannot distinguish individual web users either.

**These two columns assist investigation**; they do not by themselves prove end-user application identity.

### 5.4. Why must the audit table exist before the event trigger?

Once an event trigger is active, creating another table can invoke the handler. If the handler tries to INSERT into an audit table **that does not exist yet**, DDL statements fail.

Creating the schema, audit table, and functions **before** creating the event trigger is the clean deployment order.

## 6. Writing a `ddl_command_end` Handler Function

An event trigger handler is a function:

- With no declared parameters.
- With return type `event_trigger`.
- Invoked by PostgreSQL in the corresponding event context.
- Able to read `TG_EVENT` and `TG_TAG` in PL/pgSQL.

### 6.1. Function recording DDL metadata

```sql
CREATE OR REPLACE FUNCTION et_lab.capture_ddl_end()
RETURNS event_trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, et_lab, pg_temp
AS $fn$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT *
        FROM pg_catalog.pg_event_trigger_ddl_commands()
    LOOP
        INSERT INTO et_lab.ddl_audit (
            event_name,
            command_tag,
            object_type,
            schema_name,
            object_identity,
            in_extension,
            details
        )
        VALUES (
            TG_EVENT,
            r.command_tag,
            r.object_type,
            r.schema_name,
            r.object_identity,
            r.in_extension,
            'ddl_command_end'
        );
    END LOOP;
END;
$fn$;
```

Explanation:

1. `RETURNS event_trigger` declares the proper handler type.
2. `TG_EVENT` holds the active event name, here `ddl_command_end`.
3. `TG_TAG` is also available holding the command tag; the example uses `r.command_tag` per record because a command can yield multiple metadata rows.
4. `pg_event_trigger_ddl_commands()` returns the DDL commands/objects recorded by PostgreSQL for the current event.
5. Each row is inserted into the audit table.
6. `SECURITY INVOKER` uses the DDL caller's privileges in the lab example.
7. `SET search_path` and fully qualified table/function names govern object resolution.

### 6.2. Why use a FOR loop instead of SELECT INTO one row?

A single DDL statement can produce **multiple command records or objects**. Assuming "one statement always equals one metadata row" risks silently dropping audit records.

### 6.3. `pg_event_trigger_ddl_commands()` works only in its event context

This system function is strictly for `ddl_command_end` handlers. Do not call it as a general query API:

```sql
-- Not a standalone call to fetch DDL history:
SELECT * FROM pg_event_trigger_ddl_commands();
```

It reads metadata of **the event currently executing**, not a database-wide history table.

### 6.4. Why doesn't the handler use SECURITY DEFINER yet?

The lab assumes the administrator creating and testing DDL has `INSERT` permission on `et_lab.ddl_audit`.

If different roles run DDL without direct INSERT permissions on the audit table, a `SECURITY INVOKER` handler fails on permissions. We will design a production pattern with a dedicated low-privilege owner role in the security section; never jump straight to a superuser `SECURITY DEFINER`.

## 7. Creating an Event Trigger Filtered by Command Tag

```sql
CREATE EVENT TRIGGER et_lab_on_ddl_end
ON ddl_command_end
WHEN TAG IN (
    'CREATE TABLE',
    'ALTER TABLE',
    'CREATE INDEX',
    'CREATE VIEW'
)
EXECUTE FUNCTION et_lab.capture_ddl_end();
```

### 7.1. Event trigger names

`et_lab_on_ddl_end` is a database-level event trigger name—**not schema-qualified** like `et_lab.et_lab_on_ddl_end`.

Only the handler function resides inside schema `et_lab`.

### 7.2. `WHEN TAG IN (...)`

Only the declared and PostgreSQL-supported command tags invoke the trigger. This filters by **command type**, not by specific table name.

For instance, `CREATE TABLE et_lab.samples` matches `'CREATE TABLE'`, whereas `CREATE FUNCTION ...` is outside the list.

### 7.3. Auditing all supported DDLs

You can omit `WHEN TAG IN`:

```sql
CREATE EVENT TRIGGER et_lab_on_ddl_end_all
ON ddl_command_end
EXECUTE FUNCTION et_lab.capture_ddl_end();
```

**This is an alternative definition—do not create it alongside the existing trigger unless you want duplicate logs.** Also note that omitting the filter still only covers command tags supported by PostgreSQL event triggers.

### 7.4. Command tags are exact values

`'CREATE TABLE'` is distinct from `'ALTER TABLE'`. If code watches `'CREATE TABLE'`, `CREATE TABLE AS` has its own command tag depending on syntax/version. Verify exact tags and supported coverage when precision matters.

## 8. Practice Recording CREATE and ALTER

After creating the handler and event trigger:

```sql
CREATE TABLE et_lab.samples (
    sample_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL
);

ALTER TABLE et_lab.samples
ADD COLUMN notes text;

CREATE INDEX samples_title_idx
ON et_lab.samples (title);
```

All three should be captured by the `ddl_command_end` trigger above.

### 8.1. Reading the audit table

```sql
SELECT
    audit_id,
    happened_at,
    event_name,
    command_tag,
    object_type,
    schema_name,
    object_identity,
    in_extension
FROM et_lab.ddl_audit
ORDER BY audit_id;
```

Exact output varies slightly by version and command, yet you should see records for table `et_lab.samples` and index `samples_title_idx`.

### 8.2. Do not equate audit rows with DDL statement counts

One DDL statement can emit multiple objects or command records; conversely, some DDL behaviors are handled differently or unsupported by event triggers.

Therefore:

```sql
SELECT COUNT(*)
FROM et_lab.ddl_audit;
```

does not necessarily equal the number of `CREATE`/`ALTER` statements a user typed.

### 8.3. `object_identity` is descriptive text

This value is great for human-readable audit reports. Never treat it as a safe raw SQL identifier to concatenate directly into dynamic SQL later.

### 8.4. `in_extension`

The `in_extension` flag indicates whether the command executed inside an extension script context per PostgreSQL metadata. It helps distinguish objects created by direct migrations from objects created during extension installation or upgrades.

## 9. Metadata From `pg_event_trigger_ddl_commands()`

The function provides key columns:

| Field | Meaning |
| --- | --- |
| `classid` | OID of catalog containing the object |
| `objid` | Object OID |
| `objsubid` | Sub-object ID, e.g., column attribute in certain cases |
| `command_tag` | DDL command tag |
| `object_type` | Object kind |
| `schema_name` | Schema if applicable; may be NULL |
| `object_identity` | Descriptive identity text of the object |
| `in_extension` | Whether executed inside an extension script context |
| `command` | Internal `pg_ddl_command` representation |

### 9.1. Do not try printing `command` as raw SQL

The `command` column is an internal `pg_ddl_command` representation, **not a text column containing the user's verbatim SQL string**.

To log exact raw SQL text, look to PostgreSQL server logs, pgAudit, or migration tooling. Event triggers do not automatically provide raw SQL copies for every statement.

### 9.2. Catalog OIDs are not permanent durable identifiers

`objid`/`classid` identify the object/catalog at event time. Once an object is dropped/recreated or moved to another database, OIDs no longer refer to the same object.

For durable history, store `object_identity` alongside permitted business attributes.

### 9.3. schema_name can be NULL

Not every recorded object belongs to a schema like a table or view. Never put `NOT NULL` on the audit table's `schema_name` column.

### 9.4. Recorded DDL does not mean committed

The handler runs inside the transaction. If the transaction later rolls back, both the catalog changes and the audit rows inserted by the handler roll back.

## 10. Recording DROPs With the `sql_drop` Event

`ddl_command_end` captures metadata for created/altered objects. When objects are dropped, metadata for some objects is already gone from system catalogs by the time hooks run.

PostgreSQL provides `pg_event_trigger_dropped_objects()` to list objects dropped during supported DDL commands.

### 10.1. DROP handler function

```sql
CREATE OR REPLACE FUNCTION et_lab.capture_sql_drop()
RETURNS event_trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, et_lab, pg_temp
AS $fn$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT *
        FROM pg_catalog.pg_event_trigger_dropped_objects()
    LOOP
        INSERT INTO et_lab.ddl_audit (
            event_name,
            command_tag,
            object_type,
            schema_name,
            object_identity,
            original_drop,
            normal_drop,
            is_temporary,
            details
        )
        VALUES (
            TG_EVENT,
            TG_TAG,
            r.object_type,
            r.schema_name,
            r.object_identity,
            r.original,
            r.normal,
            r.is_temporary,
            'sql_drop'
        );
    END LOOP;
END;
$fn$;
```

### 10.2. Create the event trigger

```sql
CREATE EVENT TRIGGER et_lab_on_sql_drop
ON sql_drop
EXECUTE FUNCTION et_lab.capture_sql_drop();
```

### 10.3. Why can't `pg_event_trigger_dropped_objects()` be called anywhere?

This function is meaningful only inside the event trigger context of `sql_drop`. It is not a historical table of past DROPs.

### 10.4. Why is a loop needed?

`DROP ... CASCADE` can remove many dependent objects, not just the object named in the command. One drop command can yield many related records.

## 11. Practice With DROP and CASCADE

Following the CREATE/ALTER steps above:

```sql
CREATE VIEW et_lab.samples_view AS
SELECT sample_id, title
FROM et_lab.samples;
```

View `samples_view` depends on table `samples`.

Running:

```sql
DROP TABLE et_lab.samples;
```

without `CASCADE` is normally rejected by PostgreSQL because the dependent view still exists.

### 11.1. DROP with CASCADE

In the lab database:

```sql
DROP TABLE et_lab.samples CASCADE;
```

This removes:

- Table `et_lab.samples`.
- View `et_lab.samples_view`.
- Indexes and constraints attached to the table per dependency semantics.
- Any other dependent objects if present.

### 11.2. Reading DROP history

```sql
SELECT
    audit_id,
    command_tag,
    object_type,
    object_identity,
    original_drop,
    normal_drop,
    is_temporary
FROM et_lab.ddl_audit
WHERE event_name = 'sql_drop'
ORDER BY audit_id;
```

### 11.3. `original` and `normal`

`pg_event_trigger_dropped_objects()` exposes flags distinguishing objects named directly in the command from objects removed via internal PostgreSQL dependency processing.

Never rely on a single flag to claim "the user deliberately typed all of these objects"; with `CASCADE`, many objects are dropped indirectly via dependencies.

### 11.4. Temporary objects

`is_temporary` identifies temporary objects in drop metadata when captured. Do not assume temporary-object lifecycle churn should be audited identically to permanent production schema changes.

### 11.5. Counting dropped object identities

```sql
SELECT
    object_type,
    COUNT(*) AS dropped_objects
FROM et_lab.ddl_audit
WHERE event_name = 'sql_drop'
GROUP BY object_type
ORDER BY dropped_objects DESC, object_type;
```

This counts recorded entries, not proof that every DROP in the database was captured.

## 12. Why Does `DROP TABLE IF EXISTS` Still Need Consideration?

`ddl_command_start` can fire for a command tag even before PostgreSQL checks whether the named object exists.

Example:

```sql
DROP TABLE IF EXISTS et_lab.table_that_does_not_exist;
```

A guard blocking `DROP TABLE` at `ddl_command_start` will reject this statement purely by **command kind**, even though no table existed to drop.

Conversely, `sql_drop` receives metadata only for objects actually processed for removal inside the event context.

### 12.1. Do not infer from command tag alone that an object was dropped

`TG_TAG = 'DROP TABLE'` identifies the statement kind, not proof that a table actually vanished.

### 12.2. With CASCADE, read detailed metadata

The command tag stays `DROP TABLE`, yet the impact can include views, constraints, indexes, and other objects. Use `pg_event_trigger_dropped_objects()` for full inventory.

### 12.3. Do not extrapolate simple examples to complex schemas

Partitioned tables, views, sequences, and extensions can have intricate dependency trees. Test against realistic DDL for your actual database.

## 13. Blocking a DDL Kind With `ddl_command_start`

An organization might want to forbid `DROP TABLE` in a shared multi-team staging database.

### 13.1. Simple handler

```sql
CREATE OR REPLACE FUNCTION et_lab.block_drop_table()
RETURNS event_trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, et_lab, pg_temp
AS $fn$
BEGIN
    RAISE EXCEPTION
        'DROP TABLE is blocked by et_lab policy'
        USING ERRCODE = '42501';
END;
$fn$;
```

### 13.2. Enable for the right command tag

```sql
CREATE EVENT TRIGGER et_lab_guard_drop_table
ON ddl_command_start
WHEN TAG IN ('DROP TABLE')
EXECUTE FUNCTION et_lab.block_drop_table();
```

**Important:** this is a **very broad illustrative policy** blocking every supported `DROP TABLE` in the database, including maintenance and lab cleanup. Install it only when prepared to manage disabling privileges and error handling.

### 13.3. Test in the lab

```sql
CREATE TABLE et_lab.guard_demo (id integer);

-- The command below is expected to raise an error:
DROP TABLE et_lab.guard_demo;
```

If executed inside an explicit transaction, the error puts the transaction into an aborted state. Run `ROLLBACK` before subsequent tests.

### 13.4. Temporarily disable to clean up the lab

With event-trigger management privileges:

```sql
ALTER EVENT TRIGGER et_lab_guard_drop_table DISABLE;

DROP TABLE et_lab.guard_demo;

ALTER EVENT TRIGGER et_lab_guard_drop_table ENABLE;
```

Never let application roles toggle guards freely. This is a controlled administrative action.

### 13.5. Guards cannot stop superusers

A superuser can alter or disable event triggers or modify the database. Never treat `block_drop_table` as security protection against administrators who hold override privileges.

### 13.6. Guards do not cover every destructive alternative

Destructive changes can occur under many different command tags. A trigger filtering only `DROP TABLE` is **not** a complete DDL governance model.

## 14. `ddl_command_start` Lacks Final Object Metadata

A guard trying to block `DROP TABLE` in schema `finance` while permitting schema `scratch` faces a limitation:

`TG_TAG` primarily gives the command tag; it **does not automatically provide a structured record containing target schemas and tables**.

At `ddl_command_start`, objects have not been processed yet and many objects may not exist yet. Therefore, per-schema or per-object checks at start time are harder than checking `TG_TAG`.

### 14.1. Do not parse `current_query()` like a security SQL parser

A fragile anti-pattern:

```sql
IF current_query() LIKE '%finance.%' THEN ...
```

SQL supports comments, quoting, whitespace, multi-statement strings, and varied syntax. Raw substring matching is not a trustworthy SQL parser or authorization engine.

### 14.2. Better alternatives

- Enforce `CREATE`/`ALTER`/`DROP` privileges and ownership at the root.
- Separate migration roles per environment.
- Validate migrations in CI/CD before execution.
- Use event triggers for policies that can be verified reliably.
- Audit object metadata at `ddl_command_end`/`sql_drop` and alert on unexpected changes.

### 14.3. What about blocking at `ddl_command_end`?

If a `ddl_command_end` handler detects a forbidden condition and raises an exception, the DDL transaction rolls back. However, the DDL already executed its work beforehand, potentially consuming significant locks, CPU, and I/O.

To prevent expensive operations **before they run**, rely on proper privileges, ownership, and pre-execution validation rather than post-hoc checks alone.

## 15. `table_rewrite`: Detecting Expensive ALTER TABLE Operations

Not every `ALTER TABLE` rewrites table data. Some metadata-only changes are instant, while changing a column's type or similar operations can require rebuilding the physical table storage.

The `table_rewrite` event fires **right before the rewrite**, providing:

- The OID of the relation about to be rewritten.
- A bitmask describing the rewrite reason per PostgreSQL semantics.

### 15.1. Handler

```sql
CREATE OR REPLACE FUNCTION et_lab.capture_table_rewrite()
RETURNS event_trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, et_lab, pg_temp
AS $fn$
DECLARE
    v_relation_oid oid;
    v_reason integer;
BEGIN
    v_relation_oid :=
        pg_catalog.pg_event_trigger_table_rewrite_oid();

    v_reason :=
        pg_catalog.pg_event_trigger_table_rewrite_reason();

    INSERT INTO et_lab.ddl_audit (
        event_name,
        command_tag,
        object_type,
        object_identity,
        rewrite_reason,
        details
    )
    VALUES (
        TG_EVENT,
        TG_TAG,
        'table',
        v_relation_oid::regclass::text,
        v_reason,
        'before physical table rewrite'
    );
END;
$fn$;
```

### 15.2. Create the trigger

```sql
CREATE EVENT TRIGGER et_lab_on_table_rewrite
ON table_rewrite
EXECUTE FUNCTION et_lab.capture_table_rewrite();
```

### 15.3. Create a test table

```sql
CREATE TABLE et_lab.rewrite_demo (
    id integer PRIMARY KEY,
    payload integer NOT NULL
);

INSERT INTO et_lab.rewrite_demo (id, payload)
SELECT g, g * 10
FROM generate_series(1, 1000) AS s(g);
```

### 15.4. Change likely to force a rewrite

```sql
ALTER TABLE et_lab.rewrite_demo
ALTER COLUMN payload TYPE text
USING payload::text;
```

Converting `integer` to `text` typically changes physical storage representation and triggers `table_rewrite`. Query `ddl_audit` on your PostgreSQL version to observe actual events; never assume all `ALTER TYPE` operations behave identically.

### 15.5. View rewrite history

```sql
SELECT
    audit_id,
    command_tag,
    object_identity,
    rewrite_reason,
    happened_at
FROM et_lab.ddl_audit
WHERE event_name = 'table_rewrite'
ORDER BY audit_id;
```

## 16. Understanding `pg_event_trigger_table_rewrite_reason()`

This function returns an **integer bitmask**, not human-readable prose.

Depending on version, bits can indicate one or more causes such as:

- Changing relation persistence.
- Changing a default expression requiring a rewrite.
- Changing a column type.
- Changing table access method or other version-supported changes.

Do not hardcode business policies on unverified integer constants. To decode individual bits, consult **the exact documentation for your running PostgreSQL version** and test.

### 16.1. One rewrite can have multiple reasons

Because it is a bitmask, a single integer can combine multiple flags simultaneously.

### 16.2. Store the raw reason for analysis

`et_lab.ddl_audit.rewrite_reason` stores the raw integer. Decode bits in your reporting layer according to your exact PostgreSQL version's definitions.

### 16.3. The event does not mean the rewrite succeeded/committed

`table_rewrite` fires before the rewrite. If the command fails or rolls back, the audit row inserted in the same transaction rolls back too.

### 16.4. Operational impact of rewrites

An `ALTER TABLE` rewrite on a large table can consume heavy:

- I/O.
- WAL.
- Temporary disk / extra storage.
- Lock hold duration.
- Replication lag depending on setup.
- Migration time.

Event triggers detect or guard rewrites; they do not make rewrites online or lock-free.

## 17. Which Events Can a DDL Command Fire?

This is a **typical pattern**, not a guarantee that every command tag fires every event:

| Command | start | end | sql_drop | table_rewrite |
| --- | --- | --- | --- | --- |
| `CREATE TABLE` | Possible | Possible | Usually no | Usually no |
| `ALTER TABLE ADD COLUMN` | Possible | Possible | Depends on impact | Not necessarily |
| `ALTER TABLE ALTER TYPE` | Possible | Possible | Possible depending on change | Possible |
| `DROP TABLE` | Possible | Possible | Usually yes if actually dropped | No |
| `DROP VIEW` | Possible | Possible | Usually yes if actually dropped | No |
| `CREATE INDEX` | Possible | Possible | Usually no | No |
| `INSERT` | Not a DDL event | Not a DDL event | No | No |

"Possible" is used because event triggers cover a supported subset of command tags and remain subject to `WHEN` filters, `ENABLE`/`DISABLE` state, and transaction/error conditions.

### 17.1. Relative event order

- `ddl_command_start` runs before DDL execution.
- `table_rewrite`, if applicable, runs right before the physical rewrite.
- `sql_drop` runs as dropped objects are processed.
- `ddl_command_end` runs after DDL completes inside the transaction.

Never build workflows assuming **every command** emits exactly one row at every stage.

### 17.2. Multiple event triggers on the same event

Multiple event triggers can share an event. PostgreSQL executes them according to system-defined ordering rules (such as alphabetical name order for the same event). Never build critical business logic relying on unmanaged or untested ordering.

### 17.3. Different triggers can have different WHEN filters

Two `ddl_command_end` triggers can list different tags; a command fires only the triggers whose filters match.

## 18. Scope: Per-Database, Not Cluster-Wide

An event trigger is created inside the **current database**. It is not a cluster-wide object applying automatically across every database in the PostgreSQL instance.

```text
PostgreSQL instance / cluster
  |
  +-- database A
  |     +-- event trigger A1
  |     +-- event trigger A2
  |
  +-- database B
        +-- event trigger B1
```

### 18.1. With multiple databases

To monitor DDL across both database A and database B, deploy and monitor in each database or use centralized logging/tooling.

### 18.2. Do not use event triggers to audit roles, databases, or tablespaces

In PostgreSQL, event triggers do not fire for DDL operating on certain **shared objects**, including:

- Roles.
- Databases.
- Tablespaces.

Therefore, to audit `CREATE ROLE`, `ALTER ROLE`, or `CREATE DATABASE`, you cannot rely on an in-database event trigger alone.

### 18.3. Event-trigger management commands

DDL targeting event triggers themselves is not observed by event triggers the same way ordinary object DDLs are. This prevents recursion and matters when designing monitoring around changes to the audit machinery itself.

### 18.4. Special operational modes

Event triggers have operational exceptions, such as not firing in **single-user mode** per PostgreSQL rules. Never treat event triggers as an absolute boundary against superusers or system-level recovery operations.

### 18.5. Check the supported command tag list

PostgreSQL expands and updates DDL support across versions. Test `WHEN TAG IN` filters in migrations against real command tags rather than claiming "covers all DDL" from the event name alone.

## 19. What Event Triggers Do Not Provide Automatically

Event triggers are **not** an all-in-one tool for every DDL auditing need:

1. They do not automatically capture the raw SQL text of every statement.
2. They do not guarantee audit rows survive failed or rolled-back transactions.
3. They do not cover DDL on shared objects.
4. They do not directly monitor DML operations.
5. They do not replace schema/object authorization.
6. They cannot stop a superuser who chooses to disable them.
7. They cannot distinguish web end-users when a connection pool shares one DB login.
8. They do not automatically evaluate whether an `ALTER TABLE` is runtime-safe.
9. They do not guarantee historical audit object names stay valid after repeated schema renames.
10. They do not replace migration reviews and backups.

### 19.1. What if raw SQL text is needed?

Consider PostgreSQL server logs, pgAudit (where supported), or deployment/migration pipelines that record statement text and actors.

Event triggers provide **structured object metadata** at specific hooks—a valuable complement, not a replacement for all those sources.

### 19.2. What if you need to know who changed a data row?

Use table row/statement triggers, application auditing, WAL/logical decoding, or logs as appropriate—never DDL event triggers.

## 20. Transactional Behavior: Do Audit Rows Survive If DDL Rolls Back?

Suppose:

```sql
BEGIN;

CREATE TABLE et_lab.rollback_demo (
    id integer
);

-- The ddl_command_end function has inserted an audit record.
ROLLBACK;
```

After `ROLLBACK`:

- Table `et_lab.rollback_demo` no longer exists.
- The audit row inserted by the handler inside this transaction **also rolls back**.
- Do not expect an "attempted CREATE TABLE" record inside the internal audit table.

### 20.1. Auditing is not an attempt log

A trigger-based DDL audit table primarily records **committed changes**, not failed or rolled-back attempts.

### 20.2. If CREATE succeeds before transaction commit

`ddl_command_end` has already run, yet other sessions cannot see the new table or its audit row until the transaction commits.

### 20.3. If the handler raises an exception

```sql
RAISE EXCEPTION 'DDL rejected';
```

An unhandled exception fails the DDL statement and rolls back the corresponding transaction.

### 20.4. If failed DDL attempts must be logged

Use a channel **outside the DDL transaction** (such as properly governed database/server logs), not just an INSERT inside the same transaction.

### 20.5. Savepoints

When DDL after a `SAVEPOINT` rolls back to that savepoint, audit rows inserted within that rolled-back scope are also reverted. Test recovery semantics in your migration tools.

## 21. Design Pitfall: Writing Audits and Dropping the Audit Table Itself

Suppose a `sql_drop` event trigger always inserts into `et_lab.ddl_audit`. If a migration attempts to drop the audit table itself, the handler fails to log as expected and breaks the DDL.

### 21.1. Do not trap the audit table in a hazardous dependency

Strictly control who has permission to DROP or ALTER audit objects. Never treat an event trigger as the audit table's only self-defense.

### 21.2. Use a dedicated schema and restricted privileges

Permissions on schema `et_lab` should belong strictly to the audit module owner, never granting `CREATE`/`DROP` loosely to application roles.

### 21.3. Clean up the lab in order

Before running `DROP SCHEMA et_lab CASCADE`, drop event triggers referencing functions and tables in that schema. Otherwise dropping the schema containing the audit function/table interferes with active hooks.

### 21.4. Audit tables are not WORM storage

Ordinary PostgreSQL tables are not immutable. Privileged roles can edit or delete records or disable triggers. If compliance requires tamper-evident logs, stream logs to an independent external system with integrity controls.

## 22. Preventing Recursion and Dangerous Operations in Handlers

Event triggers run **while DDL is executing**. If a handler executes DDL itself, it can fire another event trigger (or itself) under matching conditions.

### 22.1. Pattern to avoid

```sql
-- Dangerous idea inside an event handler:
EXECUTE 'CREATE TABLE et_lab.new_log_table (...)';
```

If that DDL fires `ddl_command_end`, the handler can invoke itself recursively or produce hard-to-control side effects.

### 22.2. Safer pattern

- Only `INSERT` into an existing audit table.
- Minimize SQL statements inside the handler.
- Avoid issuing DDL inside handlers.
- Never open network requests or depend on external services without dedicated design.
- Set a safe `search_path`.
- Maintain clear transaction and error semantics.

### 22.3. Watch out for temporary objects

Temporary objects must not be treated as trusted schema objects in privileged handlers. `pg_temp` has special resolution semantics; always use fully qualified names and trusted search paths.

### 22.4. Do not commit inside an event trigger function

Event triggers run inside the command's transaction. PL/pgSQL trigger functions cannot arbitrarily `COMMIT` or `ROLLBACK` transactions like a top-level session manager.

### 22.5. Beware of locks

DDL commands often hold strong locks. A handler running heavy queries or waiting on contended resources prolongs lock hold times and blocks other sessions.

## 23. Performance: One DDL Can Emit Many Metadata Rows

An event trigger using:

```sql
FOR r IN
    SELECT *
    FROM pg_event_trigger_ddl_commands()
LOOP
    INSERT INTO et_lab.ddl_audit (...);
END LOOP;
```

can insert multiple audit rows for a single DDL statement.

### 23.1. Metadata volume

A migration creating many tables, indexes, constraints, and views emits many records. Never assume one insert per statement.

### 23.2. Avoid heavy work in event triggers

Never run:

- Full-database reporting scans.
- Network calls with unpredictable latency.
- DDL depending on newly created objects in untested ways.
- Nested migrations.
- Queries waiting on long locks unnecessarily.

### 23.3. Keep audit tables append-oriented

In production, configure retention, partitioning if logs grow huge, and only essential indexes for reporting. Avoid over-indexing the audit table so DDL writes stay fast.

### 23.4. Measure migration overhead

Benchmark migration runtimes with and without handlers in staging, tracking record counts, lock durations, and WAL. Never compare an empty `CREATE TABLE` with a multi-tens-of-GB `ALTER TABLE` rewrite when estimating event-trigger overhead.

### 23.5. Error handling determines schema-change availability

If the audit table runs out of disk or lacks `INSERT` privileges, an unhandled error in the handler blocks DDL. That may be an **intentional fail-closed policy** or an operational outage; make the choice explicit.

## 24. Security: Who Creates Event Triggers and Who Writes Logs?

Under PostgreSQL's standard security model, only a **superuser** can create event triggers. However, the **handler function** has its own security mode and owner.

### 24.1. SECURITY INVOKER in the lab

`et_lab.capture_ddl_end()` defaults to caller privileges. In the lab, an administrator runs DDL and holds `INSERT` privileges on the audit table, so it works.

If another role creates a table without `INSERT` privileges on `et_lab.ddl_audit`, the DDL fails due to a handler permission error.

### 24.2. SECURITY DEFINER in production

You can create a **dedicated `NOLOGIN` audit writer role** with strictly scoped `INSERT` privileges on the audit table, and give the handler:

```sql
SECURITY DEFINER
SET search_path = pg_catalog, et_lab, pg_temp
```

This lets the handler log audits across diverse DDL caller roles without granting direct `INSERT` on the audit table to every DDL role.

**Never make a superuser own this function just to silence permission errors.** If the handler has a SQL injection or object-hijacking flaw, an over-privileged owner magnifies the blast radius.

### 24.3. Owner must have least privilege

The writer role likely needs only:

- `USAGE` on the audit schema.
- `INSERT` on the audit table.
- Privileges on objects referenced in the `INSERT`.
- Appropriate catalog/helper read access.

It does not need `CREATEROLE`, `BYPASSRLS`, superuser, or permissions to touch application data.

### 24.4. SECURITY DEFINER changes current_user

Inside a `SECURITY DEFINER` handler, `effective_role DEFAULT current_user` records the **function owner**, not the DDL invoker.

Actor attribution design must distinguish:

- DB session login: `session_user`.
- Effective context inside the routine.
- `SET ROLE` context and active privileges.
- End user in the application or migration pipeline.

If many web users share one DB login, correlate identity via a trusted app/migration source—never blindly trust client-modifiable parameters or custom GUCs.

### 24.5. Safe schema search_path

`et_lab` must be a trusted schema where untrusted roles cannot `CREATE`/`ALTER` objects. Put `pg_catalog` first and `pg_temp` last, and explicitly qualify `et_lab.ddl_audit`.

### 24.6. Event triggers do not grant DDL privileges

A role lacking `ALTER TABLE` rights does not gain permission just because an event trigger is watching. PostgreSQL still enforces standard DDL privileges.

## 25. `TG_EVENT` and `TG_TAG` Differ

Inside a PL/pgSQL event trigger function:

- `TG_EVENT` is the event name, such as `ddl_command_start` or `ddl_command_end`.
- `TG_TAG` is the command tag, such as `CREATE TABLE`, `ALTER TABLE`, or `DROP TABLE`.

### 25.1. Illustration

```sql
CREATE OR REPLACE FUNCTION et_lab.print_ddl_context()
RETURNS event_trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, et_lab, pg_temp
AS $fn$
BEGIN
    RAISE NOTICE
        'event=%, tag=%',
        TG_EVENT,
        TG_TAG;
END;
$fn$;
```

This is purely an observer handler; it **is not active** until attached with `CREATE EVENT TRIGGER`.

### 25.2. Do not use `TG_OP` from table triggers

`TG_OP` belongs to table triggers (`INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`) and does not replace `TG_TAG` for DDL event triggers.

### 25.3. TG_TAG does not list CASCADE dependencies

`TG_TAG` may be `DROP TABLE`, yet it contains no list of dropped objects. Use `pg_event_trigger_dropped_objects()` inside `sql_drop`.

### 25.4. One command can affect multiple objects

`TG_TAG` describes the command level, while helper functions return multiple object-level rows.

## 26. Event Triggers and Extension Scripts

When `CREATE EXTENSION` or `ALTER EXTENSION ... UPDATE` runs scripts creating or altering objects, inner DDLs can trigger event triggers under PostgreSQL-supported conditions.

The `in_extension` column from `pg_event_trigger_ddl_commands()` identifies commands executed inside an extension script context.

### 26.1. Why can one migration record many objects?

An extension can create dozens of functions, types, operators, casts, tables, or views. Handlers see all those command records; counting `CREATE EXTENSION` statements alone misses the detail.

### 26.2. Do not blindly block all DDLs inside extensions

A policy blocking `CREATE FUNCTION` or `CREATE TYPE` can break extension installation and upgrades. Test all migration and extension workflows before enabling guards in production.

### 26.3. `in_extension` does not replace authorization

Seeing "command ran inside an extension script" does not automatically mean every action is safe or exempt from checks. Define explicit policies.

### 26.4. Never alter extension objects inside an audit handler

Extension objects have their own dependency and ownership lifecycle. Altering them inside an event handler causes upgrade failures and maintenance headaches.

## 27. Tracking Event Triggers via System Catalogs

Event triggers are stored in `pg_event_trigger`.

```sql
SELECT
    e.evtname AS event_trigger_name,
    e.evtevent AS event_name,
    e.evtenabled AS enabled_mode,
    e.evttags AS command_tags,
    e.evtfoid::regprocedure AS handler_function,
    pg_catalog.pg_get_userbyid(e.evtowner) AS owner_name
FROM pg_catalog.pg_event_trigger AS e
ORDER BY e.evtname;
```

### 27.1. `evtname`

Name of the event trigger in the database.

### 27.2. `evtevent`

Event type, such as `ddl_command_end` or `sql_drop`.

### 27.3. `evtenabled`

Enabled mode relative to replication modes; internal codes typically include:

- `O`: enabled in origin/normal mode.
- `D`: disabled.
- `R`: replica.
- `A`: always.

Interpret status alongside `session_replication_role` and operational policies; never assume an enabled trigger fires in every execution mode.

### 27.4. `evttags`

Array of command tags specified in `WHEN TAG IN (...)`, or NULL when unfiltered.

### 27.5. `evtfoid` and `evtowner`

`evtfoid` references the handler function, while `evtowner` is the event trigger's owner. Event trigger owner and handler function owner are **two distinct concepts** and need not be identical.

## 28. Enabling and Disabling Event Triggers

You can run:

```sql
ALTER EVENT TRIGGER et_lab_on_ddl_end DISABLE;

ALTER EVENT TRIGGER et_lab_on_ddl_end ENABLE;
```

These commands require appropriate privileges.

### 28.1. Other modes

PostgreSQL supports:

```sql
ALTER EVENT TRIGGER et_lab_on_ddl_end
ENABLE ALWAYS;

ALTER EVENT TRIGGER et_lab_on_ddl_end
ENABLE REPLICA;
```

These modes interact with `session_replication_role`. Never change modes in production without understanding replicas, logical replication, apply workers, and related privileges.

### 28.2. DISABLE does not drop the trigger

The trigger remains in the catalog, simply inactive while disabled.

### 28.3. DROP deletes the definition

```sql
DROP EVENT TRIGGER et_lab_on_ddl_end;
```

Once committed, the hook is gone from the database.

### 28.4. Updating the handler function

`CREATE OR REPLACE FUNCTION et_lab.capture_ddl_end()` alters the body invoked by the event trigger. Consequently, permission to modify the handler function is a critical part of securing the audit system.

### 28.5. Emergency recovery

If a buggy event trigger breaks all migrations, a DBA must be able to disable or drop it quickly. Always maintain a reliable administrative recovery path, rather than letting the broken handler block its own repair.

## 29. Testing a Migration Inside a Transaction

In staging, you can test:

```sql
BEGIN;

CREATE TABLE et_lab.migration_probe (
    id integer PRIMARY KEY,
    label text
);

ALTER TABLE et_lab.migration_probe
ADD COLUMN created_at timestamptz;

SELECT
    event_name,
    command_tag,
    object_identity
FROM et_lab.ddl_audit
WHERE object_identity LIKE '%migration_probe%'
ORDER BY audit_id;

ROLLBACK;
```

### 29.1. Observing within your own transaction

Your current session sees the audit rows it just inserted before committing (MVCC read-your-writes).

### 29.2. After ROLLBACK

Both `migration_probe` and the test transaction's audit rows vanish.

### 29.3. Not a way to audit all DDL attempts

Running a transaction and rolling back is great for testing semantics, not for building a persistent log of attempted DDLs.

### 29.4. Migration tools

Some migration tools wrap multiple statements in one transaction; others include non-transactional steps or commands like `CREATE INDEX CONCURRENTLY` requiring separate execution contexts.

Event triggers do not eliminate the need to understand each migration's transaction boundaries.

## 30. Multi-Level Dependency DROPs

Example with a dependency chain:

```sql
CREATE TABLE et_lab.parent_doc (
    id integer PRIMARY KEY,
    title text
);

CREATE VIEW et_lab.doc_view AS
SELECT id, title
FROM et_lab.parent_doc;

CREATE VIEW et_lab.doc_titles AS
SELECT title
FROM et_lab.doc_view;
```

When running:

```sql
DROP TABLE et_lab.parent_doc CASCADE;
```

multiple dependent objects are dropped. `pg_event_trigger_dropped_objects()` is essential because those view relations are already gone from catalogs at `sql_drop` time.

### 30.1. Why not just SELECT pg_class after DROP?

Objects already removed from catalogs cannot be looked up normally. The event-context helper returns specialized metadata before it disappears from normal access paths.

### 30.2. Why the original flag is not the whole story

An object removed by dependency cascade can carry more business impact than the directly named object. For impact analysis, retain **all dropped objects** and dependency metadata when required.

### 30.3. How does DROP EXTENSION affect objects?

Extensions own dependent components and can bundle many objects. Dropping an extension removes components per the dependency model; verify actual `sql_drop` records for extensions in your audit environment.

### 30.4. Do not assume all dropped rows are "tables"

`object_type` can be view, index, constraint, type, or other object kinds recorded by PostgreSQL.

## 31. DDL in Long Transactions and Lock Impact

A migration running:

```sql
BEGIN;

ALTER TABLE large_table
ALTER COLUMN ...;

-- Other operations...
COMMIT;
```

can hold locks for extended periods.

### 31.1. Event triggers lengthen critical sections

If a handler runs slow queries, stalls on audit-table I/O, or waits for locks on the audit table, the DDL command and its locks remain held longer.

### 31.2. Handlers do not make migrations online

For instance, `table_rewrite` only notifies before a rewrite happens. It does not automatically batch rewrites or eliminate locks.

### 31.3. Never make external network calls without timeouts

A handler calling external network APIs can hang DDLs or fail migrations whenever an external audit service is down. Evaluate synchronous vs. asynchronous designs separately; keep handlers simple by default.

### 31.4. Use timeouts in migrations appropriately

`lock_timeout` and `statement_timeout` protect waiting windows in managed deployments, keeping in mind that aborting a statement also rolls back the DDL and its in-transaction audit logs.

### 31.5. Test on large tables

An `ALTER TABLE` changing a column type can trigger a very costly rewrite. Plan maintenance windows and estimate storage and lock impact before deploying.

## 32. Audit Strategy: Block, Record, or Monitor?

| Goal | Usually appropriate choice |
| --- | --- |
| Block a clear list of command tags | `ddl_command_start` + exception |
| Audit created/modified objects | `ddl_command_end` + `pg_event_trigger_ddl_commands()` |
| Audit dropped objects | `sql_drop` + `pg_event_trigger_dropped_objects()` |
| Detect expensive rewrites | `table_rewrite` + OID/reason |
| Log failed or rolled-back attempts | PostgreSQL logs / out-of-transaction solution |
| Capture exact raw SQL text | Logs / pgAudit / migration history per need |
| Stop app role from dropping tables | Ownership and privileges |
| Audit DML row changes | Table triggers / CDC / logical decoding per need |
| Audit cluster roles/databases | Cluster/system logs and admin tooling |
| Analyze schema drift | Catalog snapshots, migration checksums, diff tools |

### 32.1. Why use event triggers if logs already exist?

Event triggers deliver structured object-level metadata—especially dropped dependencies and rewrite reasons. Server logs supply statement text, timing, and actor details per configuration.

Both sources complement rather than replace each other.

### 32.2. Why not replace privileges with event triggers?

A policy that "nobody may DROP production tables" must start with **withholding DROP privileges and unauthorized ownership**, paired with change management. Event triggers are an extra guardrail, never the primary access-control boundary.

## 33. Operating Safely With Multiple Roles

In multi-team environments, separate roles cleanly:

- **Migration role:** DDL privileges in approved schemas.
- **App runtime role:** only required DML, no ALTER/DROP.
- **Audit writer owner:** used to insert metadata into the audit table.
- **Read-only audit reviewer:** `SELECT` on audit logs.
- **DBA/incident role:** manages event triggers and recovery when needed.

### 33.1. Least privilege

Never grant superuser to an application just because it needs to trigger DDL. Creating event triggers belongs to an approved administrative step.

### 33.2. Trigger function ownership

A `SECURITY DEFINER` function owned by a superuser is a serious attack surface. Restrict ownership and `search_path`, and never execute arbitrary caller-supplied SQL.

### 33.3. SQL injection in handlers

Metadata like `object_identity` should be stored as **data values**, never concatenated into dynamic SQL to query tables.

If dynamic identifiers are unavoidable, quote properly with `format('%I')`, validate against allowlists, and verify permissions. Better yet, avoid dynamic DDL in handlers altogether.

### 33.4. Forbid untrusted CREATE in the audit schema

If callers can create or alter helpers inside `et_lab`, a privileged handler's object resolution can be hijacked. Use a trusted schema, schema-qualify tables/functions, and set `SET search_path = pg_catalog, et_lab, pg_temp`.

### 33.5. Do not trust caller RLS inside a definer context

When a handler is `SECURITY DEFINER`, owner privileges affect RLS. Separate privileged log writing from reading sensitive data.

## 34. Using Catalogs and Reports to Detect Unexpected Changes

Once auditing is active:

```sql
SELECT
    date_trunc('day', happened_at) AS audit_day,
    command_tag,
    COUNT(*) AS event_records
FROM et_lab.ddl_audit
GROUP BY
    date_trunc('day', happened_at),
    command_tag
ORDER BY audit_day DESC, event_records DESC;
```

### 34.1. Statistics by object type

```sql
SELECT
    event_name,
    object_type,
    COUNT(*) AS n
FROM et_lab.ddl_audit
GROUP BY event_name, object_type
ORDER BY event_name, n DESC;
```

### 34.2. Grouping objects by transaction

```sql
SELECT
    transaction_id,
    COUNT(*) AS audit_rows,
    array_agg(command_tag ORDER BY audit_id)
        AS command_tags
FROM et_lab.ddl_audit
GROUP BY transaction_id
ORDER BY transaction_id DESC
LIMIT 20;
```

One transaction can contain multiple statements; `transaction_id` groups records by transaction, not necessarily uniquely per SQL statement.

### 34.3. Dedicated rewrite report

```sql
SELECT
    happened_at,
    object_identity,
    rewrite_reason
FROM et_lab.ddl_audit
WHERE event_name = 'table_rewrite'
ORDER BY happened_at DESC;
```

### 34.4. Be careful with actor attribution

`session_login` may be a shared migration login; `effective_role` can reflect `SET ROLE` or `SECURITY DEFINER`. Never blame an individual solely from those two columns without cross-checking logs and deployment records.

### 34.5. Metrics are not raw statement counts

Because audits store object-level records, total rows may exceed statement counts; conversely, due to filters and supported events, counts may be lower.

## 35. Installing Event Triggers as Part of a Migration

A minimal rollout sequence:

1. Verify target database and confirm you are not accidentally touching production.
2. Create the audit schema and table first.
3. Configure appropriate owner and permissions for the handler.
4. Write `RETURNS event_trigger` functions with a trusted `search_path`.
5. Review logic, scope, and command tags.
6. Create event triggers using an authorized superuser/admin role.
7. Verify `pg_event_trigger` and handler ownership.
8. Run rollbackable test DDL.
9. Verify audit metadata and rollback behavior.
10. Test multi-role permissions.
11. Test guard/cleanup behavior on exceptions.
12. Enable monitoring, retention, and a documented incident runbook.

### 35.1. Do not create triggers before the audit table

If the handler writes to a table that does not exist yet, the very next DDL fails.

### 35.2. Do not enable blocking guards too early

Enabling a `DROP TABLE` guard prematurely can block migrations that clean up temp/staging tables—including lab cleanup.

### 35.3. Keep a recovery path independent of the handler

DBAs must know trigger names and hold `ALTER EVENT TRIGGER ... DISABLE` / `DROP EVENT TRIGGER` privileges when a handler misbehaves.

### 35.4. Test extension upgrades in staging

Tag-based policies can interfere with `CREATE EXTENSION`/`ALTER EXTENSION`. Test with all extensions your database uses.

### 35.5. Include a rollback migration

Dropping a handler function while an event trigger still depends on it fails due to dependencies. Drop/disable event triggers in order before dropping functions or schemas.

## 36. Cleaning Up the Lab in Safe Order

Once you finish practicing and want to remove the lesson objects:

```sql
-- Requires appropriate event-trigger administration privileges.
DROP EVENT TRIGGER IF EXISTS et_lab_guard_drop_table;
DROP EVENT TRIGGER IF EXISTS et_lab_on_table_rewrite;
DROP EVENT TRIGGER IF EXISTS et_lab_on_sql_drop;
DROP EVENT TRIGGER IF EXISTS et_lab_on_ddl_end;

-- Run only in a lab database.
DROP SCHEMA IF EXISTS et_lab CASCADE;
```

### 36.1. Why drop event triggers first?

The event triggers depend on functions and the audit table inside `et_lab`. Dropping them first prevents active hooks from pointing at removed objects during schema teardown.

### 36.2. Why not leave the DROP TABLE guard behind?

Event triggers apply database-wide. Leaving a guard active in a shared lab database can block other users' work afterwards.

### 36.3. `DROP SCHEMA ... CASCADE` is destructive

Run this only when `et_lab` is strictly your lab schema containing no unrelated data. Never copy this command to production.

### 36.4. Do not clean up before exporting audit results

Cleanup deletes `et_lab.ddl_audit`. Export data or save reports before dropping the schema if you need to keep results.

## 37. Common Misconceptions

| Misconception or error | Reality |
| --- | --- |
| Event triggers are like AFTER INSERT triggers | No; they observe supported DDL commands |
| Event triggers attach to a single table | No; they belong to the database |
| Anyone can run CREATE EVENT TRIGGER | PostgreSQL requires superuser privileges |
| `ddl_command_start` fires after DDL | It fires before DDL execution |
| `ddl_command_end` means the transaction committed | Not yet; it can still roll back |
| A DROP TABLE command always emits a `sql_drop` object | `IF EXISTS` on a missing object drops nothing |
| `sql_drop` can query `pg_class` for all dropped objects | Objects are already removed from catalogs in the transaction |
| `pg_event_trigger_dropped_objects()` is a history table | Holds metadata only for the active event |
| `pg_event_trigger_ddl_commands()` works anytime | Valid only inside `ddl_command_end` context |
| One DDL equals one audit row | A single command can affect many objects |
| `TG_TAG` holds the object list | Only the command tag string |
| `TG_EVENT` is the command tag | It is the event name |
| `table_rewrite` fires after the rewrite finishes | Fires right before the rewrite |
| Every `ALTER TABLE` rewrites the table | No |
| `rewrite_reason` is descriptive text | It is an integer bitmask |
| Audit INSERTs survive rollbacks | Same-transaction writes roll back together |
| Event triggers catch every cluster DDL | Shared objects and special commands are excluded |
| `CREATE ROLE` fires `ddl_command_end` | Not via standard in-database DDL event triggers |
| Event triggers always capture raw SQL | They provide metadata, not every raw statement text |
| Superusers cannot bypass guards | Superusers hold administrative override privileges |
| Any `SECURITY DEFINER` owner is fine | Use least privilege; superuser owners are dangerous |
| Actor is `current_user` inside a definer handler | That may be the function owner |
| `session_user` is always the web end-user | Shared connection pools reuse one DB login |
| Handlers can COMMIT independently | They are not transaction managers |
| Running extra DDL inside handlers is always safe | Risks recursion, locks, and unexpected side effects |
| `WHEN TAG IN` filters by table | Filters by command tag, not relation |
| Writing to an audit table makes it immutable | Privileged roles can edit or delete rows |
| Heavy handlers for deep audits are harmless | Overhead increases lock durations and latency |
| `DROP EVENT TRIGGER` is always audited by other event triggers | Event-trigger DDL has exceptions |
| `ALTER EVENT TRIGGER DISABLE` deletes the trigger | Only changes its enabled mode |
| `evttags IS NULL` means the trigger is broken | It simply has no `WHEN` tag filter |
| `evtenabled='D'` means the trigger was dropped | It still exists, just disabled |
| Audit logs alone suffice for DDL governance | Combine with `GRANT`, ownership, and migration reviews |
| Testing `CREATE TABLE` alone is enough | Test `DROP CASCADE`, `ALTER`, rollback, rewrite, and roles |

## 38. Practice Exercises With Answers

Exercises assume lab schema `et_lab` is set up and you have required privileges. Never run anti-pattern examples in production.

### Exercise 1. What are event triggers used to observe?

**Answer:** PostgreSQL-supported DDL command tags and events within the current database, such as `CREATE TABLE`, `ALTER TABLE`, and `DROP TABLE`.

### Exercise 2. How do event triggers differ from table triggers?

**Answer:** Table triggers observe DML/`TRUNCATE` on a specific object; event triggers observe database-level DDL by event and tag.

### Exercise 3. Name the four events

**Answer:** `ddl_command_start`, `ddl_command_end`, `sql_drop`, `table_rewrite`.

### Exercise 4. Which event runs before DDL?

**Answer:** `ddl_command_start`.

### Exercise 5. Which event fits auditing metadata after CREATE TABLE?

**Answer:** `ddl_command_end` paired with `pg_event_trigger_ddl_commands()`.

### Exercise 6. Which event fits auditing DROP CASCADE?

**Answer:** `sql_drop` paired with `pg_event_trigger_dropped_objects()`.

### Exercise 7. Which event detects an ALTER TABLE requiring a rewrite?

**Answer:** `table_rewrite`.

### Exercise 8. What return type must the handler function have?

**Answer:** `event_trigger`.

### Exercise 9. Syntax for a minimal handler function?

```sql
CREATE FUNCTION et_lab.notice_event()
RETURNS event_trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    RAISE NOTICE 'event=%, tag=%', TG_EVENT, TG_TAG;
END;
$fn$;
```

**Answer:** No function parameters, `RETURNS event_trigger`, and valid use of event context.

### Exercise 10. Create a trigger watching ALTER TABLE?

```sql
CREATE EVENT TRIGGER et_lab_alter_notice
ON ddl_command_end
WHEN TAG IN ('ALTER TABLE')
EXECUTE FUNCTION et_lab.notice_event();
```

**Answer:** Event trigger using `ON ddl_command_end` and a command tag filter. Do not recreate with a duplicate name if it already exists.

### Exercise 11. How do TG_EVENT and TG_TAG differ?

**Answer:** `TG_EVENT` is the event name; `TG_TAG` is the DDL command type.

### Exercise 12. Can you use TG_OP from row triggers for DDL?

**Answer:** No. Event triggers have their own context; `TG_OP` does not replace `TG_TAG`.

### Exercise 13. Does CREATE EVENT TRIGGER fire ddl_command_end like CREATE TABLE?

**Answer:** Commands targeting event triggers have exceptions and do not fire event triggers like ordinary object DDLs.

### Exercise 14. Can a non-superuser create an event trigger?

**Answer:** `CREATE EVENT TRIGGER` requires superuser privileges in PostgreSQL. Managed services may disallow it even for broad application roles.

### Exercise 15. Does `WHEN TAG IN` filter by table column or name?

**Answer:** No. It filters command tags such as `'CREATE TABLE'` or `'ALTER TABLE'`.

### Exercise 16. Can one DDL generate multiple metadata rows?

**Answer:** Yes. `pg_event_trigger_ddl_commands()` can return multiple records/objects.

### Exercise 17. Why not assume one statement = one audit row?

**Answer:** A DDL statement can create or alter multiple objects, dependencies, and command records.

### Exercise 18. When is `pg_event_trigger_ddl_commands()` called?

**Answer:** Inside a `ddl_command_end` event handler.

### Exercise 19. When is `pg_event_trigger_dropped_objects()` called?

**Answer:** Inside a `sql_drop` event handler.

### Exercise 20. Why is the sql_drop helper vital when objects are dropped?

**Answer:** Objects are already gone from system catalogs at hook time; the helper supplies dropped-object metadata.

### Exercise 21. Is `object_identity` a raw SQL statement?

**Answer:** No. It is a textual identity description of the object.

### Exercise 22. Can `command` of type pg_ddl_command be printed directly as original SQL?

**Answer:** Do not treat it as original SQL text; it is an internal representation.

### Exercise 23. What does `in_extension` indicate?

**Answer:** That the DDL command executed within an extension script context per PostgreSQL metadata.

### Exercise 24. What can `DROP TABLE ... CASCADE` affect?

**Answer:** Beyond the target table, it can remove dependent objects such as views, constraints, and indexes per dependency semantics.

### Exercise 25. Does `original_drop` mean the user typed every object in the command?

**Answer:** The flag helps distinguish directly targeted objects, whereas `CASCADE` removes additional indirectly dependent objects.

### Exercise 26. What is `is_temporary` for?

**Answer:** Identifies temporary objects in dropped-object metadata when recorded.

### Exercise 27. Can `DROP TABLE IF EXISTS missing` trigger a start guard?

**Answer:** Yes, because the command tag is known before checking object existence.

### Exercise 28. Can `ddl_command_start` inspect metadata of newly created objects?

**Answer:** No, because the event runs before DDL execution.

### Exercise 29. Should you parse `current_query()` with `LIKE` to protect schema `finance`?

**Answer:** No; that is not a reliable SQL parser. Use proper privileges, ownership, and designed policies.

### Exercise 30. Why can an exception in an event trigger roll back DDL?

**Answer:** The handler executes inside the DDL transaction; an unhandled exception fails the statement.

### Exercise 31. Do audit INSERTs survive a DDL ROLLBACK?

**Answer:** Normally no. Audit rows in the same transaction roll back with the DDL.

### Exercise 32. What is needed to log failed DDL attempts?

**Answer:** Server logs, an out-of-transaction solution, or an independent auditing mechanism—not just an INSERT inside the same transaction.

### Exercise 33. Does `table_rewrite` fire before or after the rewrite?

**Answer:** Before the rewrite.

### Exercise 34. Which function retrieves the OID of the table about to be rewritten?

**Answer:** `pg_event_trigger_table_rewrite_oid()`.

### Exercise 35. Which function retrieves the rewrite reason?

**Answer:** `pg_event_trigger_table_rewrite_reason()`, returning an integer bitmask.

### Exercise 36. Does every `ALTER TABLE ADD COLUMN` rewrite the table?

**Answer:** No. It depends on the specific change, PostgreSQL version, and column/DDL attributes.

### Exercise 37. Are event triggers cluster-wide?

**Answer:** No. They belong to the current database.

### Exercise 38. Can an in-database event trigger capture `CREATE ROLE`?

**Answer:** No, shared objects are excluded from standard event triggers; use server logs or external auditing.

### Exercise 39. Where does a `SECURITY INVOKER` handler get its privileges?

**Answer:** From the effective caller role; if the role executing DDL lacks `INSERT` on the audit table, the handler fails.

### Exercise 40. Why avoid `SECURITY DEFINER` owned by a superuser?

**Answer:** Any bug in code or name resolution executes with unrestricted privileges. Use a dedicated low-privilege owner.

### Exercise 41. Is `CURRENT_USER` in a definer handler the DDL invoker?

**Answer:** Not necessarily; it normally reflects the definer function's owner in that context.

### Exercise 42. Why is `SESSION_USER` insufficient to identify web users?

**Answer:** Many web users typically share a single database login via a connection pool.

### Exercise 43. What should a safe `search_path` look like?

**Suggested answer:** `pg_catalog, et_lab, pg_temp` with `et_lab` as a trusted schema and sensitive tables/functions fully schema-qualified.

### Exercise 44. Why avoid running DDL inside event handlers?

**Answer:** Risk of recursion, extra locks/overhead, and hard-to-control side effects.

### Exercise 45. Does `ALTER EVENT TRIGGER ... DISABLE` drop the object?

**Answer:** No. It changes the enabled mode; the trigger remains in the catalog.

### Exercise 46. Which catalog inventories event triggers?

**Answer:** `pg_event_trigger`, via columns `evtname`, `evtevent`, `evtenabled`, `evttags`, `evtfoid`, and `evtowner`.

### Exercise 47. Does `evttags IS NULL` indicate an error?

**Answer:** Not necessarily; the trigger may simply have no `WHEN TAG IN` filter.

### Exercise 48. Why don't event triggers replace PostgreSQL logging?

**Answer:** Event triggers record transactional object-level metadata, whereas logs capture raw statements and failed/rolled-back attempts outside audit-table transaction semantics.

### Exercise 49. Why test `DROP CASCADE` and extension upgrades?

**Answer:** Dependent objects and extension scripts emit command tags that can trip handlers and break migrations if policies are too broad.

### Exercise 50. Build a production rollout checklist

**Suggested answer:**

1. Clarify goals: blocking, auditing created/altered objects, auditing dropped objects, or detecting table rewrites.
2. Pick the right events and matching helper functions.
3. Create the audit schema and table before enabling triggers.
4. Use a least-privilege owner role and trusted `search_path`.
5. Evaluate `INVOKER` vs. `DEFINER` and audit `INSERT` permissions.
6. Prevent untrusted roles from altering audit code or schemas.
7. Restrict tags only when needed, and verify coverage against real DDL.
8. Never write recursive DDL inside handlers.
9. Test `CREATE`, `ALTER`, `DROP CASCADE`, rewrites, and rollbacks.
10. Test permission errors, unavailable audit tables, and recovery.
11. Monitor `pg_event_trigger`, performance, WAL, and lock durations.
12. Prepare a DBA runbook for `DISABLE`/`DROP` and ordered cleanup.

## 39. Project Testing Matrix

| Scenario | Event / condition to observe | Expected |
| --- | --- | --- |
| New `CREATE TABLE` | `ddl_command_end` | Object metadata recorded |
| `ALTER TABLE ADD COLUMN` | `ddl_command_end` | Change metadata recorded |
| `CREATE INDEX` | `ddl_command_end` with matching tag | Command record present |
| `DROP TABLE` without dependents | `sql_drop` | Dropped object metadata present |
| `DROP TABLE CASCADE` | `sql_drop` | Lists all dependent objects |
| `DROP TABLE IF EXISTS missing` | `ddl_command_start` may run | Do not assume an object was dropped |
| `ALTER TABLE` rewriting type | `table_rewrite` | OID and reason logged on real rewrite |
| Metadata-only `ALTER TABLE` | `table_rewrite` | Should not emit rewrite event |
| `CREATE FUNCTION` | `ddl_command_end` if unfiltered | Not accidentally dropped by wrong filter |
| `CREATE EXTENSION` | Extension scripts | Verify `in_extension` |
| `CREATE ROLE` | Shared-object DDL | Do not expect event trigger capture |
| `CREATE EVENT TRIGGER` | Event-trigger DDL | Excluded by event-trigger machinery |
| `ROLLBACK` after `CREATE TABLE` | Transaction semantics | Both table and audit row roll back |
| Handler raises exception | DDL command | DDL rejected/rolled back per scope |
| DDL caller lacks audit INSERT | `INVOKER` handler | Permission error unless grants are set |
| `DEFINER` handler with wide owner | Security review | Reject over-privileged owner |
| Handler with dynamic DDL | Recursion review | Avoid loops and uncontrolled behavior |
| Audit table dropped | Recovery | Admin runbook and permissions ready |
| `DISABLE` event trigger | `pg_event_trigger` | Catalog mode updated |
| Multiple statements in one transaction | Audit grouping | Multiple rows share `transaction_id` |
| Connection pool / shared login | Attribution | Do not confuse DB login with end user |
| Migration on large table | Performance | Measure actual locks, latency, and WAL |

## 40. Operations and Security Checklist

| Question | What to ensure |
| --- | --- |
| Is the event trigger's goal clear? | Clear audit, block, or monitor objective |
| Using a dedicated test database? | Never impact production accidentally |
| Superuser privileges available to create? | Verify provider and permissions |
| Aware of per-database scope? | Do not mistake for cluster-wide |
| Audit table created before enabling hooks? | Avoid failing the very first DDL |
| Handler declares `RETURNS event_trigger`? | Correct return type |
| Helper functions match the event? | `ddl_commands`/end; `dropped_objects`/drop |
| Distinguished `TG_EVENT` and `TG_TAG`? | Event name vs. command tag |
| `WHEN TAG IN` chosen carefully? | No important DDL missed |
| Tested `CREATE TABLE AS`? | Verify command tag coverage per version |
| Capturing `CASCADE` dependencies? | Use `sql_drop` helper |
| Storing `object_identity`/`object_type`/`schema`? | Sufficient metadata |
| Aware audit disappears on rollback? | Understood and accepted |
| Source for failed attempt logs exists? | Out-of-transaction channel if needed |
| Raw SQL text required? | Do not expect `pg_ddl_command` as raw text |
| Handling `table_rewrite`? | OID/reason and lock/cost awareness |
| Hardcoding reason bitmask? | Only after verifying against exact version |
| Any recursive DDL in handler? | Avoid |
| Heavy queries or logs in handler? | Minimize overhead |
| Handler missing audit INSERT privilege? | Test across multiple roles |
| Handler `SECURITY DEFINER`? | Least-privilege owner |
| Trusted `search_path` configured? | `pg_catalog, trusted, pg_temp` |
| Objects schema-qualified? | Sensitive objects qualified |
| Need end-user web attribution? | Trusted identity, not just `session_user` |
| Broad `CREATE` rights on audit schema? | No |
| Audit table protected from edits/deletes? | Grants, ownership, and retention |
| Tracking event-trigger state? | `pg_event_trigger` |
| `DISABLE`/`DROP` runbook ready? | Admin access available during incidents |
| Tested migrations and extensions? | No unintended blocking |
| Tested failed DDL? | Verify rollback and exceptions |
| Tested long transactions? | Locks, WAL, and duration |
| Measured migration overhead? | Before/after in staging |
| Backup and rollback plan ready? | Never treat event triggers as backups |
| Lab cleanup procedure ready? | Drop event triggers before schema |
| Verified shared-object exclusion? | Use logs/external tools separately |
| Policy documented? | Migration team informed |
| Periodic review scheduled? | Monitor owner, tags, and path changes |

## 41. Summary

Event triggers are PostgreSQL's mechanism for observing and intervening in DDL changes **right inside the database**.

Key principles:

1. **Event triggers differ from table triggers.** They do not watch individual rows; they watch supported DDL commands and events.
2. **`ddl_command_start`** runs before DDL execution, suited for command-tag guards, though final object metadata is not yet available.
3. **`ddl_command_end`** runs after DDL completes inside the transaction, before commit; use `pg_event_trigger_ddl_commands()` to capture object-level metadata.
4. **`sql_drop`** supplies metadata on dropped objects, including `CASCADE` dependencies, via `pg_event_trigger_dropped_objects()`.
5. **`table_rewrite`** fires immediately before a physical table rewrite, providing OID and bitmask reason.
6. **Handler functions must declare `RETURNS event_trigger`**, using `TG_EVENT` and `TG_TAG` in context.
7. **`WHEN TAG IN (...)` filters by command tag**, not by table or schema name.
8. **One DDL statement can emit many audit records**, and not every DDL statement is supported by event triggers.
9. **Event triggers are database-scoped**, not cluster-wide by default.
10. **Shared objects (roles, databases, tablespaces) and event-trigger DDLs have exclusions**; comprehensive auditing requires additional sources.
11. **In-transaction audit INSERTs roll back with the DDL.** Event triggers are not an immutable log of every failed DDL attempt.
12. **`pg_ddl_command` is not raw SQL text**; use server logs or migration history when exact SQL text is required.
13. **Never put dynamic DDL or heavy work in handlers**, to avoid recursion, lock contention, and migration failures.
14. **`SECURITY DEFINER` requires a least-privilege owner and safe `search_path`**; never let application roles edit audit functions.
15. **Actor attribution requires understanding effective vs. session roles**, especially with shared connection pools and definer contexts.
16. **DDL privileges are the primary barrier**; event-trigger guards supplement rather than replace `GRANT` and ownership.
17. **Monitor catalogs and `ENABLE`/`DISABLE` state**, backed by monitoring and an incident runbook.
18. **Deploy in order:** audit table -> handler functions -> event triggers -> integration tests -> monitoring.
19. **Test rollbacks, `DROP CASCADE`, table rewrites, extension upgrades, and multiple roles**, not just a simple `CREATE TABLE`.
20. **Deploy to production only after benchmarking and establishing a recovery path**, since a broken handler can block all schema migrations.

Easy-to-remember pattern:

```sql
-- Function created first, returning event_trigger.
CREATE OR REPLACE FUNCTION et_lab.short_ddl_notice()
RETURNS event_trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, et_lab, pg_temp
AS $fn$
BEGIN
    RAISE NOTICE
        'DDL event: %, command tag: %',
        TG_EVENT,
        TG_TAG;
END;
$fn$;

-- Administrator creates the event trigger in the lab database.
CREATE EVENT TRIGGER et_lab_short_notice
ON ddl_command_end
WHEN TAG IN ('CREATE TABLE', 'ALTER TABLE')
EXECUTE FUNCTION et_lab.short_ddl_notice();
```

To capture detailed object metadata, switch to `pg_event_trigger_ddl_commands()` in a `ddl_command_end` handler; to audit DROPs, use `sql_drop` with `pg_event_trigger_dropped_objects()`; and to detect rewrites, use `table_rewrite` and its two helper functions.

**Final rule:** before installing an event trigger, clearly answer: **"Which DDL types must I observe, what metadata actually exists at that hook point, must the audit survive rollback, under whose privileges does the handler run, and if the handler fails, who can recover the database?"** Once you have clear answers to all five questions, event triggers become a reliable governance tool rather than an operational hazard.
