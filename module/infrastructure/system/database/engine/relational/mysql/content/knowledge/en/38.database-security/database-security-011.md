# DEFINER/INVOKER and Privilege Escalation Risks via Stored Objects

In MySQL, an account can be allowed to call a view or stored procedure without holding direct privileges on the underlying tables. This mechanism is useful for exposing a narrow data interface, yet it also introduces a risk: a stored object can perform operations using the privileges of an account more powerful than the caller.

Two concepts to distinguish are **DEFINER** and **INVOKER**. `DEFINER` identifies the account used as the basis for privilege checks when an object runs in the definer context. `INVOKER` uses the privileges of the account invoking the object. This choice determines which tables and data a SQL call can reach, so it must be treated as part of MySQL security design.

## 1. What Are DEFINER and SQL SECURITY?

A stored object stores metadata about the account that defines it. This account is recorded as a `user` and `host` pair, such as `'report_owner'@'localhost'`; comparing usernames alone is not enough to identify the exact account. Nor is the account in the `DEFINER` clause necessarily the person who created the object.

For views, stored procedures, and stored functions, the `SQL SECURITY` clause selects the execution privilege context:

| Mode | Privilege Check Context on Referenced Objects | Meaning |
|---|---|---|
| `SQL SECURITY DEFINER` | Account recorded in `DEFINER` | Callers can exercise privileges granted to the definer through the object, even if they lack direct privileges on the underlying tables. |
| `SQL SECURITY INVOKER` | Account invoking the object | Callers must hold the required privileges on the objects accessed by the statements. |

If `SQL SECURITY` is omitted, views and stored routines default to `DEFINER`. Declare it explicitly so readers of DDL and migration reviewers see the security decision right in the object definition.

Triggers and events also have a `DEFINER`, yet they always execute in the definer context; their syntax offers no `SQL SECURITY INVOKER` option. This is critical when evaluating automated actions: an application's `INSERT`, `UPDATE`, or `DELETE` can fire a trigger that executes with another account's privileges.

## 2. How Are Privileges Checked?

Consider an application account querying `reporting.open_orders`:

1. MySQL authenticates the connection and identifies the calling account.
2. MySQL checks whether the caller has privileges to use the object, such as `SELECT` on a view or `EXECUTE` on a procedure.
3. MySQL determines the security context based on `SQL SECURITY`.
4. When statements inside the object access tables or other objects, MySQL checks privileges against the selected context.

With `SQL SECURITY DEFINER`, the caller still needs privileges on the view or routine itself. However, privileges to read or modify referenced tables come from the definer. This enables encapsulating a controlled operation: the application is granted access only to a specific routine rather than direct `UPDATE` privileges on the entire table.

With `SQL SECURITY INVOKER`, the definer's privileges are not used to elevate the call. The caller must possess appropriate privileges on the accessed tables and objects in addition to the privilege required to access the view or routine.

Triggers and events follow different flows: a trigger runs when a table operation fires it; an event runs on schedule when the Event Scheduler executes it. Both use the definer's privileges. Therefore, when granting write privileges on a table that has triggers, you must also evaluate the trigger body and the tables the trigger can read or write.

## 3. Intentionally Using DEFINER for Views

Suppose order data resides in the `sales` schema. A reporting account only needs to view open orders; it does not need read access to the entire orders table.

Create a dedicated definer account and grant only the required read privilege:

```sql
CREATE USER 'report_owner'@'localhost' IDENTIFIED BY 'replace-with-a-managed-secret';

GRANT SELECT ON sales.orders
TO 'report_owner'@'localhost';
```

Create the view using that account's privileges:

```sql
CREATE DEFINER = 'report_owner'@'localhost'
SQL SECURITY DEFINER
VIEW reporting.open_orders AS
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM sales.orders
WHERE status = 'OPEN';
```

Then grant read access only on the view to the reporting account:

```sql
GRANT SELECT ON reporting.open_orders
TO 'report_reader'@'%';
```

If `report_reader` has no other privileges on `sales.orders`, it can query the view without being able to query the base table directly. This creates a smaller access surface. However, the view is only safe if its query actually restricts to the intended columns and rows and the user's other privileges do not allow bypassing the view.

If the view is switched to `SQL SECURITY INVOKER`, the caller must have the required privileges on `sales.orders` for the query inside the view to run. Choose `INVOKER` when the goal is to preserve the caller's privileges; choose `DEFINER` when exposing a narrow interface backed by the least privilege of a dedicated account.

`WITH CHECK OPTION` can constrain writes through an updatable view so written rows still satisfy the view's condition. It does not replace authorization design, nor does it automatically create a row-level access policy across all access paths to the table.

## 4. Stored Procedures as High-Privilege Operation Gateways

A `SQL SECURITY DEFINER` stored procedure can execute an operation that the caller is not permitted to perform directly. For example, an internal procedure reading a payroll table:

```sql
CREATE DEFINER = 'payroll_owner'@'localhost'
PROCEDURE hr.read_payroll()
SQL SECURITY DEFINER
BEGIN
    SELECT employee_id, salary
    FROM hr.payroll;
END;
```

An application account can be granted execution access to the procedure:

```sql
GRANT EXECUTE ON PROCEDURE hr.read_payroll
TO 'hr_report_user'@'10.%';
```

The caller does not need direct `SELECT` privileges on `hr.payroll`, yet still receives all results returned by the procedure. Therefore, `GRANT EXECUTE` is effectively a data-access grant. If a procedure does not filter by the caller's authorized scope, granting `EXECUTE` too broadly can expose sensitive data.

A `DEFINER` procedure must enforce business checks internally: which records the caller may view or modify, which state transitions are permitted, and whether parameter counts and ranges are valid. Never trust a client-supplied `actor_id`, `tenant_id`, or `role` as proof of identity or authorization. In applications sharing a single database connection account across many end users, MySQL only sees the shared connection account; end-user authentication and authorization must be bound through a trusted application mechanism.

## 5. How Privilege Escalation Occurs

| Scenario | Risk Mechanism | Potential Impact |
|---|---|---|
| Over-privileged definer | View or routine runs as an account with privileges across many schemas, or even an admin account | Anyone granted access to invoke the object may indirectly read or modify more data than intended. |
| Overly broad `EXECUTE` grant | A `DEFINER` procedure exposes sensitive operations to too many accounts or roles | Callers can use the procedure as a gateway to privileged data or actions. |
| Unsafe dynamic SQL | Routine concatenates input strings into SQL and executes in the definer context | SQL injection turns input into statements that read or alter data with the definer's privileges. |
| Triggers or events missed during review | Triggers/events automatically execute with definer privileges | An operation seemingly targeting one table can trigger writes to other tables or run privileged scheduled tasks. |
| Identity confusion inside routines | Using `CURRENT_USER()` as if it were always the connecting user | In a `DEFINER` context, `CURRENT_USER()` can return the definer account; caller-based checks may break. |
| Definer deleted or privileges altered | Object still stores a reference to the definer account | Object may fail at runtime if the account is gone; changing the account's privileges alters what the object can execute. |
| Arbitrary definer assignment | Object creator holds special admin privileges allowing another account to be named as definer | An object can be created to leverage the privileges of an account stronger than the creator. |

### Dynamic SQL Inside DEFINER Routines

Never concatenate input directly into a SQL string:

```sql
-- Dangerous pattern: input can alter statement structure.
SET @sql = CONCAT(
    'SELECT * FROM sales.orders WHERE customer_name = ''',
    p_customer_name,
    ''''
);
```

When dynamic SQL is needed inside a stored procedure, use parameter markers for values and pass values via `EXECUTE ... USING`. Table names, column names, or sort directions cannot be bound as values; if they must vary, map input through a fixed allow-list before assembling the statement. Always validate parameter length, value domain, and business meaning. Parameterization prevents data from being interpreted as SQL syntax, but by itself does not prove the caller is authorized to act on that record.

### CURRENT_USER() and USER() Are Not Synonymous

`CURRENT_USER()` reflects the MySQL account used for privilege checking in the current context. Inside a routine or view running with `SQL SECURITY DEFINER`, this value may be the definer account. `USER()` reflects the connection identity supplied by the client when connecting. The two values can differ; connections through proxies or applications sharing one account further complicate inferring the end user.

If a view uses `CURRENT_USER()` to filter rows, verify that condition under the exact `SQL SECURITY` mode deployed. A filter written assuming `CURRENT_USER()` is always the viewer can inadvertently use the definer's identity and return out-of-scope data.

## 6. Auditing DEFINER and SQL SECURITY

Do not review only views and procedures. Inventory triggers and events as well because they also execute with definer privileges.

List views and stored routines with their security modes:

```sql
SELECT
    'VIEW' AS object_type,
    TABLE_SCHEMA AS object_schema,
    TABLE_NAME AS object_name,
    DEFINER,
    SECURITY_TYPE
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema')

UNION ALL

SELECT
    ROUTINE_TYPE AS object_type,
    ROUTINE_SCHEMA AS object_schema,
    ROUTINE_NAME AS object_name,
    DEFINER,
    SECURITY_TYPE
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema')
ORDER BY object_schema, object_type, object_name;
```

List triggers and events separately:

```sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_OBJECT_TABLE,
    DEFINER
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema');

SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    STATUS
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema');
```

Views in `INFORMATION_SCHEMA` display only metadata the current account is allowed to see. An empty result does not prove the system has no objects; run audits using an audit account with appropriate read scope.

For suspicious objects, inspect the full definition and the definer's privileges:

```sql
SHOW CREATE VIEW reporting.open_orders;
SHOW CREATE PROCEDURE hr.read_payroll;
SHOW CREATE TRIGGER sales.orders_after_update;
SHOW CREATE EVENT maintenance.daily_cleanup;

SHOW GRANTS FOR 'report_owner'@'localhost';
SHOW GRANTS FOR 'hr_report_user'@'10.%';
```

Read the object body to inspect accessed tables, dynamic SQL, identity-checking functions, write operations, and nested calls. Compare the definer's privileges against those exact operations, and also inspect the caller's direct and role-based privileges to spot bypass paths.

## 7. Secure Design Principles

1. **Prefer INVOKER when privilege elevation is unnecessary.** For views and routines serving only operations allowed by the caller's own privileges, declare `SQL SECURITY INVOKER` explicitly.
2. **Use dedicated definer accounts per purpose.** Never use `root` or administrative accounts as definers for applications. Grant only the privileges needed on the exact schemas, tables, and operations; avoid global privileges without clear justification.
3. **Treat EXECUTE as a data-access privilege.** Grant privileges per procedure only to the roles or accounts that need it. Review both the results a procedure returns and the modifications it can perform.
4. **Enforce authorization logic inside the object.** Validate tenant scope, record ownership, state transitions, and business limits on the trusted side. Never treat client-supplied parameters as sole proof of identity.
5. **Use parameter markers and allow-lists.** Never concatenate input directly into SQL. When table or column selection is required, map choices to a fixed list and reject out-of-list values.
6. **Review triggers and events as privileged code.** Document the source table, target table, firing timing, execution condition, and definer account. Ensure side effects align with privileges users are permitted to trigger.
7. **Manage definer account lifecycles.** Before dropping or modifying an account's privileges, check which objects reference it. A missing definer account can cause runtime errors when objects are invoked; if recreating an account with the same `user`/`host` pair, re-review its new privileges and all referencing objects.
8. **Control DEFINER assignment.** Grant deployment accounts only necessary administrative privileges. The ability to specify a definer other than the current account is governed by a special privilege; its exact name and requirements vary by MySQL version.
9. **Verify privileges after deployment.** Cross-check DDL, `SHOW GRANTS`, assigned roles, and test runs using the actual account. Do not rely solely on migrations succeeding.

When deploying to a new environment or restoring from a dump, create definer accounts and grant appropriate privileges before verifying dependent objects. A dump file may preserve `DEFINER` clauses; if that account does not exist on the target server or lacks required privileges, views, routines, triggers, or events may not behave as in the source environment. Re-check the definer list and privileges after every restore or environment migration.

## 8. Pre-Release Testing Procedure

For each view or routine using `DEFINER`, build a minimal test matrix:

| Test Account | Expected Access | What to Confirm |
|---|---|---|
| Account granted access on the object | Can perform only the exposed functionality | Results do not exceed row/column scope; writes alter only permitted data. |
| Account not granted access on the object | Denied | Cannot invoke the view or routine merely by knowing its name. |
| Account with direct table privileges | Matches that account's own grants | Do not confuse outcomes from direct privileges with privileges via the stored object. |
| Definer account | Holds only minimum necessary privileges | The object does not rely on unnecessary administrative privileges. |

In testing, verify both direct and indirect access paths. Test boundary parameters, invalid inputs, records belonging to other tenants, and disallowed business states. For objects containing dynamic SQL, test input strings containing quotes and syntax characters; statements must handle them as data or reject the input. For triggers, verify both primary changes and side effects. For events, verify the definer account, event status, and privileges on tables touched by the job.

If an object is found to run with overly broad privileges, first identify dependent applications and accounts. Then narrow the definer's privileges, fix the logic or switch to `INVOKER` where appropriate, adjust caller grants, and re-run the test matrix. Do not abruptly drop a definer account before inventorying dependent objects, as doing so can break live operational jobs.

## 9. Review Questions to Answer

- Does the object truly need to run with `DEFINER` rights? If yes, why does `INVOKER` not suffice?
- Which `user`/`host` account is the definer, what privileges does it hold, and which privileges does the object actually use?
- Who holds `SELECT` on the view or `EXECUTE` on the routine? Are privileges granted directly or via roles?
- Which columns and rows does the object return? Can a caller pass parameters to widen the scope?
- Does it contain dynamic SQL, write operations, triggers, events, or calls to other stored objects?
- Does the logic use `CURRENT_USER()` or `USER()`, and does that value match the execution context?
- If the definer is locked, has privileges changed, is dropped, or is recreated, how is the object affected?
- Have tests been run using actual application accounts in a production-like environment?

A solid design uses `DEFINER` as a bounded delegation mechanism: the object exposes a small operation, the definer holds only necessary privileges, and callers receive access only to that exact object. When that delegation is unnecessary, `INVOKER` keeps privilege checks tied to the invoking account and is generally easier to reason about.
