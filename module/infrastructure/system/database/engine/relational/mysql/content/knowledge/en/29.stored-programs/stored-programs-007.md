# SQL SECURITY, DEFINER, and Executor Privileges

Stored programs in MySQL can run with the privileges of the account that defined the object or the privileges of the account invoking the object. This mechanism is controlled by the `DEFINER` attribute and the `SQL SECURITY` characteristic. Understanding both concepts helps you design secure procedures, functions, views, triggers, and events, while avoiding granting direct table privileges to every application.

With `SQL SECURITY DEFINER`, statements inside a routine or view have their privileges checked against the `DEFINER` account. The caller still needs permission to reference the object, such as `EXECUTE` for a procedure or `SELECT` for a view, but does not necessarily need direct privileges on the tables accessed by the object. With `SQL SECURITY INVOKER`, internal operations are checked against the caller's privileges. Triggers and events do not have an `SQL SECURITY` option; they always execute in the security context of their `DEFINER`.

This is a critical security boundary. A `DEFINER` procedure can expose a restricted data operation to an application, yet it can also become a privilege escalation path if the `DEFINER` is overly privileged, parameters are not validated, or dynamic SQL is concatenated from untrusted data. This lesson covers how MySQL determines security context, how to grant least privilege, how to deploy stable `DEFINER` accounts, and how to inspect objects at risk of becoming orphaned.

## Learning objectives

After this lesson, you will be able to:

- Distinguish `DEFINER` from the object creator account and the object caller account.
- Explain `SQL SECURITY DEFINER` and `SQL SECURITY INVOKER`.
- Know the default `SQL SECURITY` of stored routines and views.
- Identify the security context of triggers and events.
- Distinguish `USER()` and `CURRENT_USER()` when inspecting execution privileges.
- Design `DEFINER` procedures to provide controlled access.
- Design `INVOKER` routines when the caller must hold privileges on underlying data.
- Grant `CREATE ROUTINE`, `ALTER ROUTINE`, and `EXECUTE` with proper scope.
- Understand the privilege required to specify a `DEFINER` different from the current account.
- Manage roles and effective privileges of the `DEFINER` account.
- Avoid orphaned stored objects when renaming or dropping accounts.
- Inspect `DEFINER`, `SQL SECURITY`, and grants using `SHOW CREATE` and `INFORMATION_SCHEMA`.
- Apply least privilege, parameter validation, and SQL injection prevention.

## 1. Three identities to distinguish

When an application calls a stored procedure, there can be three distinct identities:

1. **Creator**: the account that executed the `CREATE` statement to create the procedure.
2. **DEFINER**: the account stored in the object definition and used as the security context when the object runs in `DEFINER` mode.
3. **Invoker**: the account that actually calls the procedure or references the view.

These three identities can overlap, though they do not have to. For example, a deployment pipeline may create a procedure with a dedicated service account as `DEFINER`; application users only hold `EXECUTE` on that procedure.

If a `CREATE` statement omits `DEFINER`, MySQL defaults to using the account executing the `CREATE` statement as `DEFINER`. Thus, running migrations with a deploy account while omitting `DEFINER` can accidentally make the deploy account the `DEFINER` of all new routines.

`DEFINER` is not a privilege group name nor a snapshot of privileges captured at `CREATE` time. When a routine runs under `DEFINER`, MySQL checks privileges against the `DEFINER` account at execution time. If a required privilege is revoked, the routine can start failing even though the routine definition did not change.

## 2. What is DEFINER?

`DEFINER` is an attribute identifying a MySQL account by a user and host pair. For example:

    DEFINER = 'orders_api_definer'@'localhost'

This account is the security principal referenced in the object's metadata. It is not necessarily the account that created the object.

When `DEFINER` is omitted:

    CREATE PROCEDURE app_db.list_orders()
    BEGIN
        SELECT order_id
        FROM app_db.orders;
    END;

MySQL assigns the account executing `CREATE PROCEDURE` as the `DEFINER`. To make intent explicit and reduce dependence on the migration account, you can specify:

    CREATE DEFINER = CURRENT_USER
    PROCEDURE app_db.list_orders()
    BEGIN
        SELECT order_id
        FROM app_db.orders;
    END;

`CURRENT_USER` in the `DEFINER` clause represents the current account authenticated with the server at the time the object is created.

### 2.1. DEFINER does not automatically grant privileges

Writing:

    DEFINER = 'orders_api_definer'@'localhost'

does not automatically grant `SELECT`, `INSERT`, `UPDATE`, or `DELETE` to that account. The `DEFINER` account must be created and granted the privileges required by the routine body.

If the routine reads `app_db.orders`, the `DEFINER` account needs appropriate `SELECT` privilege on that table. If the routine updates a table, the `DEFINER` needs `UPDATE` or corresponding write privileges. Privileges are checked under the execution context.

Do not use `root` or a DBA account as `DEFINER` merely to avoid privilege errors. Create a dedicated account holding only the privileges required by the object.

## 3. SQL SECURITY controls whose privileges are checked

For stored procedures, stored functions, and views, MySQL supports two values:

- `DEFINER`: checks internal operations using the privileges of the `DEFINER` account.
- `INVOKER`: checks internal operations using the privileges of the account calling or referencing the object.

If `SQL SECURITY` is omitted, the default is `DEFINER`.

| Characteristic | `SQL SECURITY DEFINER` | `SQL SECURITY INVOKER` |
|---|---|---|
| Base object access privileges | `DEFINER`'s privileges | Invoker's privileges |
| Caller needs privilege on routine | Yes, typically `EXECUTE` | Yes, typically `EXECUTE` |
| Caller needs direct privilege on base tables | Not necessarily | Yes, per operations performed by the routine |
| Used to encapsulate restricted access | Suitable | Not the primary goal |
| Risk if misdefined | Can create privilege escalation paths | Generally bounded by caller's privileges |

`SQL SECURITY` does not alter the SQL logic inside the routine. It changes the identity MySQL uses for privilege checks when internal statements execute.

Characteristics such as `READS SQL DATA`, `MODIFIES SQL DATA`, `CONTAINS SQL`, and `NO SQL` describe the routine's activity category to the server and schema readers. They do not replace `GRANT` and are not an automatic sandbox preventing the routine from running statements outside the declared label. Actual permissions are still checked against the `SQL SECURITY` context and the corresponding account's privileges.

### 3.1. SQL SECURITY DEFINER

Example:

    CREATE DEFINER = CURRENT_USER
    PROCEDURE app_db.get_order_summary(
        IN p_customer_id BIGINT UNSIGNED
    )
    SQL SECURITY DEFINER
    READS SQL DATA
    BEGIN
        SELECT
            order_id,
            order_date,
            total_amount
        FROM app_db.orders
        WHERE customer_id = p_customer_id;
    END;

Suppose the `DEFINER` has `SELECT` on `app_db.orders`, while the application account only has `EXECUTE` on the procedure. The application can invoke the procedure and receive results without being granted direct `SELECT` on the entire `orders` table.

This is a common way to encapsulate access privileges for a database API. The procedure must restrict returned data based on parameters and business rules. If the procedure allows reading any customer via an arbitrary parameter, it can expose data beyond its original intent.

The example above only illustrates the privilege boundary between caller and `DEFINER`; it does not implement tenant authorization. In multi-tenant systems, never treat a caller-supplied `p_customer_id` as proof that the caller owns that data. Production procedures must verify customer/tenant ownership using a trusted identity and validated business rules. If an application shares one database account across many end users, `USER()` also only identifies the shared connection account, not the end user.

### 3.2. SQL SECURITY INVOKER

Example:

    CREATE DEFINER = CURRENT_USER
    PROCEDURE app_db.get_my_order_rows(
        IN p_customer_id BIGINT UNSIGNED
    )
    SQL SECURITY INVOKER
    READS SQL DATA
    BEGIN
        SELECT
            order_id,
            order_date,
            total_amount
        FROM app_db.orders
        WHERE customer_id = p_customer_id;
    END;

With `INVOKER`, the caller must hold `EXECUTE` on the procedure and the required `SELECT` privilege on `app_db.orders`. If the caller only holds `EXECUTE` without `SELECT` on the table, the inner statement fails because the `DEFINER`'s privileges are not substituted for the caller's.

`INVOKER` fits when the routine merely organizes SQL or standardizes operations while authorization policy remains governed by the caller's privileges.

### 3.3. Do not confuse DEFINER with SQL SECURITY

`DEFINER` identifies which account is attached to the object. `SQL SECURITY` determines whether that account's privileges are used at execution time.

A routine can declare:

    CREATE DEFINER = 'admin'@'localhost'
    PROCEDURE app_db.read_sensitive_data()
    SQL SECURITY INVOKER
    BEGIN
        SELECT sensitive_value
        FROM app_db.sensitive_table;
    END;

In this example, `DEFINER` is still `admin@localhost`, yet the routine runs with the invoker's privileges because of `SQL SECURITY INVOKER`. Never infer that seeing `DEFINER` means the caller automatically receives the `DEFINER`'s privileges.

## 4. USER() and CURRENT_USER() help observe security context

These two functions serve different purposes:

- `USER()` returns the user/host identity the client used when connecting.
- `CURRENT_USER()` returns the MySQL account currently used for privilege checks in the active security context.

Running directly in a session:

    SELECT
        USER() AS connection_identity,
        CURRENT_USER() AS privilege_identity;

Inside an `SQL SECURITY DEFINER` routine, `CURRENT_USER()` returns the routine's `DEFINER` account. `USER()` still reflects the client's connection identity.

Example:

    CREATE DEFINER = CURRENT_USER
    PROCEDURE app_db.show_security_context()
    SQL SECURITY DEFINER
    BEGIN
        SELECT
            USER() AS connection_identity,
            CURRENT_USER() AS privilege_identity;
    END;

When an application account invokes the procedure, the output can show `USER()` as the application account while `CURRENT_USER()` is the `DEFINER` account.

Switching the procedure to `SQL SECURITY INVOKER` makes `CURRENT_USER()` reflect the invoker's security context.

This is a useful diagnostic check when investigating privilege errors. Do not use `USER()` instead of `CURRENT_USER()` to conclude which account MySQL uses when checking privileges of statements inside a routine.

## 5. Privileges for creating and calling stored routines

Fundamental privileges related to stored procedures and stored functions:

| Privilege | Purpose |
|---|---|
| `CREATE ROUTINE` | Create stored procedures or stored functions |
| `ALTER ROUTINE` | Alter or drop stored routines |
| `EXECUTE` | Invoke stored procedures or stored functions |
| `SET_ANY_DEFINER` / version-equivalent privilege | Specify a `DEFINER` other than the current account |
| `SHOW_ROUTINE` | View routine definitions within granted scope, on versions supporting this privilege |

`CREATE ROUTINE` is typically granted at the schema level. `ALTER ROUTINE` and `EXECUTE` can be granted at the specific routine level.

Example:

    GRANT CREATE ROUTINE
    ON app_db.*
    TO 'routine_deployer'@'localhost';

    GRANT EXECUTE
    ON PROCEDURE app_db.get_order_summary
    TO 'app_runtime'@'%';

To revoke:

    REVOKE EXECUTE
    ON PROCEDURE app_db.get_order_summary
    FROM 'app_runtime'@'%';

Account name and host must match an existing created account. Do not grant `CREATE ROUTINE` or privileges to set `DEFINER` to a runtime application account if the application only needs to invoke routines.

### 5.1. automatic_sp_privileges

MySQL has the `automatic_sp_privileges` system variable. When enabled (typically `1` by default), the server automatically grants `ALTER ROUTINE` and `EXECUTE` to the routine creator if needed; these auto-granted privileges are removed when the routine is dropped.

Check:

    SHOW VARIABLES LIKE 'automatic_sp_privileges';

If this variable is off, the creator does not automatically receive those privileges. The `DEFINER` account of an `SQL SECURITY DEFINER` routine also needs `EXECUTE` on the routine under MySQL's privilege check rules. When creator and `DEFINER` differ, do not assume privileges auto-granted to the creator were also granted to the `DEFINER`.

Inspect grants:

    SHOW GRANTS FOR 'routine_deployer'@'localhost';
    SHOW GRANTS FOR 'app_runtime'@'%';

For the `DEFINER` account, verify both base-table privileges and `EXECUTE` on the routine.

### 5.2. Invoker and definer privileges in a DEFINER routine

For an `SQL SECURITY DEFINER` routine:

- The invoker needs `EXECUTE` on the routine.
- The `DEFINER` needs privileges to execute the statements inside the routine.
- The `DEFINER` also needs `EXECUTE` on the routine under MySQL's privilege checks.
- The invoker does not need direct privileges on base tables if access is provided through the `DEFINER` routine.

For an `SQL SECURITY INVOKER` routine:

- The invoker needs `EXECUTE` on the routine.
- The invoker needs privileges on the tables, views, or objects accessed inside the routine.
- The `DEFINER`'s privileges do not substitute for missing invoker privileges.

Exact required privileges depend on statements and execution paths inside the routine. For example, an `IF` branch containing an `UPDATE` only triggers an `UPDATE` privilege check when that branch executes, yet privilege design must cover every permitted execution path.

## 6. Complete example: encapsulating order read privileges

Suppose the application is only allowed to call a procedure to read a single customer's orders. The application must not `SELECT` directly from the entire `orders` table.

### 6.1. Creating a dedicated DEFINER account

Run with an administrative account:

    CREATE USER 'orders_api_definer'@'localhost'
    IDENTIFIED BY 'replace-with-secret-from-secret-manager';

    GRANT CREATE ROUTINE
    ON app_db.*
    TO 'orders_api_definer'@'localhost';

    GRANT SELECT
    ON app_db.orders
    TO 'orders_api_definer'@'localhost';

In real systems, passwords must be managed via a secret manager and never stored in repositories or migration logs. If the deployment pipeline can connect directly using the `DEFINER` account, protect credentials and restrict login paths.

### 6.2. Creating the procedure with the DEFINER account

Connect as `orders_api_definer@localhost` and run:

    DELIMITER //

    CREATE DEFINER = CURRENT_USER
    PROCEDURE app_db.get_order_summary(
        IN p_customer_id BIGINT UNSIGNED
    )
    SQL SECURITY DEFINER
    READS SQL DATA
    BEGIN
        IF p_customer_id IS NULL OR p_customer_id = 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'customer_id is required';
        END IF;

        SELECT
            order_id,
            order_date,
            total_amount
        FROM app_db.orders
        WHERE customer_id = p_customer_id
        ORDER BY order_date DESC;
    END//

    DELIMITER ;

`DEFINER` is set to `CURRENT_USER` so the object binds to the account creating the routine. The body only reads `orders`. Parameters are used as SQL values and are not concatenated into dynamic SQL strings.

### 6.3. Granting only EXECUTE to the application

Run with an administrative account:

    GRANT EXECUTE
    ON PROCEDURE app_db.get_order_summary
    TO 'app_runtime'@'%';

Do not grant:

    -- Do not grant full-table read privilege to runtime if unnecessary:
    -- GRANT SELECT ON app_db.orders TO 'app_runtime'@'%';

The application calls:

    CALL app_db.get_order_summary(1001);

Results are read under the `DEFINER`'s privileges. The `app_runtime` account only holds permission to invoke the procedure per its grants.

### 6.4. Verifying privilege behavior

Connect as `app_runtime` and test:

    CALL app_db.get_order_summary(1001);

If `EXECUTE` was granted and `DEFINER` has sufficient privileges, the procedure succeeds.

Test direct access:

    SELECT *
    FROM app_db.orders;

If `app_runtime` has no `SELECT` on the table, the direct statement must be denied. This verifies the designed privilege boundary.

Note: this example assumes the `DEFINER` account already holds `EXECUTE` on the procedure. If `automatic_sp_privileges` is off or the creator differs from `DEFINER`, an administrator must grant `EXECUTE` to `DEFINER` per server policy.

## 7. SQL SECURITY INVOKER example

If the routine should succeed only when the caller holds table read privileges, declare `INVOKER`:

    DELIMITER //

    CREATE DEFINER = CURRENT_USER
    PROCEDURE app_db.list_orders_as_invoker(
        IN p_customer_id BIGINT UNSIGNED
    )
    SQL SECURITY INVOKER
    READS SQL DATA
    BEGIN
        SELECT
            order_id,
            order_date,
            total_amount
        FROM app_db.orders
        WHERE customer_id = p_customer_id;
    END//

    DELIMITER ;

Grant `EXECUTE` to the application:

    GRANT EXECUTE
    ON PROCEDURE app_db.list_orders_as_invoker
    TO 'app_runtime'@'%';

If `app_runtime` does not yet have `SELECT` on `app_db.orders`, `CALL` fails at the inner `SELECT` statement. Only after granting `SELECT` can the routine read the table:

    GRANT SELECT
    ON app_db.orders
    TO 'app_runtime'@'%';

This is the core difference between `DEFINER` and `INVOKER`. Do not pick `INVOKER` just because the name sounds safer; choose according to the authorization policy the application needs to enforce.

## 8. SQL SECURITY and VIEWs

Views also have `DEFINER` and `SQL SECURITY`. By default, views use `SQL SECURITY DEFINER`.

Example `DEFINER` view:

    CREATE DEFINER = CURRENT_USER
    SQL SECURITY DEFINER
    VIEW app_db.v_public_order_summary AS
    SELECT
        order_id,
        customer_id,
        order_date,
        total_amount
    FROM app_db.orders
    WHERE order_status = 'PAID';

Users referencing the view need `SELECT` on the view. Base-table access privileges are checked against the view's `DEFINER`. This exposes a restricted set of columns/rows without granting direct `SELECT` on the underlying table.

`INVOKER` view:

    CREATE DEFINER = CURRENT_USER
    SQL SECURITY INVOKER
    VIEW app_db.v_order_rows_invoker AS
    SELECT
        order_id,
        customer_id,
        order_date,
        total_amount
    FROM app_db.orders;

With an `INVOKER` view, the account referencing the view must hold appropriate privileges on the underlying objects. Having `SELECT` on the view does not replace `SELECT` on the base table under the `INVOKER` security context.

### 8.1. Views calling stored functions

A view can call a stored function. In that case, security contexts can chain across objects:

- An `SQL SECURITY DEFINER` view uses the view `DEFINER`'s privileges when accessing base tables.
- If the view calls an `SQL SECURITY DEFINER` function, the function uses the function `DEFINER`'s privileges.
- If the view calls an `SQL SECURITY INVOKER` function, the function uses the privileges determined by the view's `SQL SECURITY` context. With a `DEFINER` view, an `INVOKER` function runs under the view `DEFINER`'s privileges; with an `INVOKER` view, the function uses the privileges of whoever referenced the view.

Therefore, never assume the end user is always the context of every indirectly called function. When combining views and routines, inspect each object's definition and test with an account holding realistic privileges.

## 9. Triggers always run in DEFINER context

Triggers have no `SQL SECURITY DEFINER` or `INVOKER` clause. Triggers always execute using the privileges of their `DEFINER` account.

Example:

    DELIMITER //

    CREATE DEFINER = CURRENT_USER
    TRIGGER app_db.orders_before_insert
    BEFORE INSERT ON app_db.orders
    FOR EACH ROW
    BEGIN
        IF NEW.total_amount < 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'total_amount cannot be negative';
        END IF;
    END//

    DELIMITER ;

Users performing an `INSERT` on the table trigger it automatically. Triggers do not require the user to invoke a routine via `EXECUTE`. Thus, the trigger `DEFINER`'s privileges are especially sensitive: users can fire the trigger via table operations without directly referencing the trigger.

The `DEFINER` account must hold the privileges used inside the trigger body. If the trigger writes to an audit table, the `DEFINER` needs `INSERT` on the audit table. The user inserting into `orders` does not necessarily need direct `INSERT` on the audit table if the trigger performs that write in the `DEFINER` context.

When creating a trigger, the account running `CREATE` needs the `TRIGGER` privilege on the target table. Manage trigger creation privileges separately from trigger execution privileges.

Do not create triggers with an overly powerful `DEFINER`. An abused trigger can turn `INSERT`/`UPDATE` privilege on one table into the ability to perform additional sensitive operations.

## 10. Events always run in DEFINER context

The Event Scheduler runs events on a schedule. Events do not have `SQL SECURITY INVOKER`; an event body always uses its `DEFINER`'s security context.

Example:

    CREATE DEFINER = CURRENT_USER
    EVENT app_db.expire_old_sessions
    ON SCHEDULE EVERY 1 DAY
    DO
        DELETE FROM app_db.user_session
        WHERE expires_at < CURRENT_TIMESTAMP;

The `DEFINER` account needs `DELETE` privilege on the `user_session` table. Application users do not call events directly; the server runs the event automatically when the Event Scheduler is active.

Check:

    SHOW VARIABLES LIKE 'event_scheduler';

The Event Scheduler must be enabled for scheduled events to run. The account creating the event needs the appropriate `EVENT` privilege on the schema. The `DEFINER` account must hold privileges for the operations in the event body.

Because events run automatically, there is no invoker `EXECUTE` privilege acting as a gate like with procedures. Restrict event creation/modification privileges and periodically audit event `DEFINER`s.

## 11. Comparing security contexts across object types

| Object | Has `SQL SECURITY`? | Default / behavior | Referencer privileges |
|---|---|---|---|
| Procedure | Yes | Default `DEFINER` | Needs `EXECUTE`; body privileges follow `DEFINER` or `INVOKER` |
| Function | Yes | Default `DEFINER` | Needs privilege to invoke function; body privileges follow `DEFINER` or `INVOKER` |
| View | Yes | Default `DEFINER` | Needs privilege on view; base-table privileges follow `DEFINER` or `INVOKER` |
| Trigger | No | Always `DEFINER` | Fired via table operations; body runs under `DEFINER` |
| Event | No | Always `DEFINER` | Server runs on schedule; body runs under `DEFINER` |

Only procedures, functions, and views allow choosing `SQL SECURITY INVOKER`. Do not try to add an `SQL SECURITY` clause to `CREATE TRIGGER` or `CREATE EVENT`.

## 12. What privileges must the DEFINER account hold?

The `DEFINER` account needs exact privileges for the statements that may execute inside the object:

| Statement in object | Privileges to review |
|---|---|
| `SELECT` from table | `SELECT` on appropriate table or columns |
| `INSERT` into table | `INSERT` |
| `UPDATE` columns | `UPDATE` on appropriate table/columns |
| `DELETE` rows | `DELETE` |
| Call another procedure/function | `EXECUTE` on the called routine |
| Create or alter objects | Corresponding DDL privileges if body/logic is permitted to do so |
| Read view | `SELECT` on the view plus privileges required per the view's security context |

Never grant `ALL PRIVILEGES` just to make a routine run. Read the body, list the actual operations, and grant least privilege.

If a routine has multiple branches, evaluate all reachable branches. A rarely taken branch performing `UPDATE` or `DELETE` still requires the corresponding privilege when executed.

### 12.1. Privileges on nested routine calls

A procedure can call another procedure. Each routine has its own security context based on its own `SQL SECURITY`. Therefore, trace the call chain:

    app_runtime
       |
       v
    app_db.api_procedure
       |
       v
    app_db.internal_procedure
       |
       v
    app_db.orders

If `api_procedure` is `DEFINER` but calls `internal_procedure` which is `INVOKER`, the second routine uses the caller's context for that call (which is `api_procedure`'s `DEFINER`). If `internal_procedure` is `DEFINER`, it switches to its own `DEFINER`'s privileges. Context transitions must be traced per object, not assumed from the outermost routine.

When investigating privilege errors, run `SHOW CREATE` for all involved routines/views and test with the actual runtime account.

## 13. Roles and effective privileges of DEFINER

MySQL supports roles for grouping privileges. However, do not assume every role `GRANT`ed to a `DEFINER` is automatically active inside a `DEFINER` stored routine.

For `SQL SECURITY DEFINER` stored routines, MySQL by default activates the `DEFINER` account's default roles; non-default roles are not automatically active. If `activate_all_roles_on_login` is enabled, the server may activate all granted roles according to that variable's rules. Stored programs can also execute `SET ROLE` to activate needed roles, but this must be controlled carefully since role privileges can change after the routine is deployed.

Check:

    SHOW VARIABLES LIKE 'activate_all_roles_on_login';

    SHOW GRANTS FOR 'orders_api_definer'@'localhost';

For a predictable security context, you can grant the minimal required privileges directly to the `DEFINER` account rather than relying on a role set that varies by session. If using roles, verify default roles, active roles, and behavior in your exact MySQL version.

Do not use broad administrative roles as the privilege foundation for `DEFINER` routines. Effective routine privileges should be stable and auditable.

## 14. Privileges to set a DEFINER other than the current account

Normally, when creating a stored object, the creating account can set `DEFINER` to itself or `CURRENT_USER`. Specifying another account requires the corresponding administrative privilege for your MySQL version.

| Version / rule | Privilege to note |
|---|---|
| MySQL 8.0 releases prior to privilege model changes | `SET_USER_ID` or `SUPER` per release rules |
| MySQL 8.4 | `SET_ANY_DEFINER` to specify another account; `ALLOW_NONEXISTENT_DEFINER` bypasses certain orphan-object safeguards |

`SET_USER_ID` was deprecated in newer MySQL lines and removed in MySQL 8.4. Check documentation for your exact version before writing migrations or `GRANT`s.

`SET_ANY_DEFINER` is a sensitive privilege because its holder can create objects that run with another account's privileges. Do not grant it to application accounts or ordinary deployment accounts without strict controls.

If the target `DEFINER` holds `SYSTEM_USER`, the object creator also needs `SYSTEM_USER` under MySQL's system-account protection rules.

`ALLOW_NONEXISTENT_DEFINER` allows bypassing orphan-object protection checks in special cases. On MySQL 8.4, intentionally creating a new stored object with a nonexistent `DEFINER` requires both `SET_ANY_DEFINER` and `ALLOW_NONEXISTENT_DEFINER`. Do not grant these privileges just to make migrations stop failing; create the `DEFINER` account first and deploy the object afterward.

### 14.1. Deploy under the DEFINER account or specify from a deployment account?

Two common approaches:

**Approach A: create objects while logged in as the DEFINER account**

- The `DEFINER` account holds `CREATE ROUTINE` and required data privileges.
- `CREATE` does not specify another user as `DEFINER`; use `CURRENT_USER`.
- After creation, grant `EXECUTE` to the runtime account.

**Approach B: deployment account specifies a dedicated DEFINER**

- The deployment account needs the privilege to set a `DEFINER` other than the current account.
- The `DEFINER` account must exist on the target server.
- `DEFINER` privileges must be granted beforehand or managed in clearly ordered migrations.
- Verify `DEFINER` after deployment.

Approach A generally avoids granting `SET_ANY_DEFINER` to pipelines. Approach B is convenient for centralized migrations but requires strict protection of the privilege to assign `DEFINER`.

## 15. What is an orphaned stored object?

An orphaned stored object is an object whose `DEFINER` points to an account that no longer exists. This can happen when:

- The `DEFINER` account is dropped.
- The `DEFINER` account is renamed.
- Objects are dumped/restored into an environment where the `DEFINER` account has not yet been created.
- A migration creates an object referencing an unprovisioned account.
- An administrative operation bypasses orphan-object safeguards.

Consequences depend on object type and security context:

- An `SQL SECURITY DEFINER` routine may fail at execution time because the `DEFINER` account does not exist.
- An `SQL SECURITY DEFINER` view may fail when referenced.
- An event may fail when its schedule fires.
- A trigger with a nonexistent `DEFINER` can exhibit undefined behavior under privilege check rules; never leave triggers in this state.
- `SQL SECURITY INVOKER` routines/views still require metadata and governance checks even though runtime privileges follow the invoker.

Do not intentionally create orphaned objects. Recreating an account later with the same user/host can unexpectedly bind old objects to the new account, creating a security risk.

### 15.1. Checking routine DEFINERs

    SELECT
        ROUTINE_SCHEMA,
        ROUTINE_NAME,
        ROUTINE_TYPE,
        DEFINER,
        SECURITY_TYPE
    FROM information_schema.ROUTINES
    WHERE ROUTINE_SCHEMA = 'app_db'
    ORDER BY ROUTINE_TYPE, ROUTINE_NAME;

### 15.2. Checking view DEFINERs

    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        DEFINER,
        SECURITY_TYPE
    FROM information_schema.VIEWS
    WHERE TABLE_SCHEMA = 'app_db'
    ORDER BY TABLE_NAME;

### 15.3. Checking trigger DEFINERs

    SELECT
        TRIGGER_SCHEMA,
        TRIGGER_NAME,
        EVENT_OBJECT_TABLE,
        DEFINER
    FROM information_schema.TRIGGERS
    WHERE TRIGGER_SCHEMA = 'app_db'
    ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME;

### 15.4. Checking event DEFINERs

    SELECT
        EVENT_SCHEMA,
        EVENT_NAME,
        DEFINER,
        STATUS
    FROM information_schema.EVENTS
    WHERE EVENT_SCHEMA = 'app_db'
    ORDER BY EVENT_NAME;

These queries require appropriate metadata privileges. Not every account can view all routine definitions or objects in other schemas.

## 16. Do not drop or rename a DEFINER carelessly

Before running `DROP USER` or `RENAME USER`, locate any stored objects referencing that account. If any exist, plan to update their `DEFINER` or drop/recreate the objects properly.

In MySQL 8.4, the server enforces orphan-object safeguards. `DROP USER` or `RENAME USER` may be rejected if the account is actively used as a `DEFINER`. `CREATE USER` may also be rejected if the new account would adopt existing orphaned objects. Special administrative privileges such as `ALLOW_NONEXISTENT_DEFINER` can bypass some checks; do not use them as an everyday workaround.

Example finding objects using an account:

    SELECT
        ROUTINE_SCHEMA,
        ROUTINE_NAME,
        ROUTINE_TYPE
    FROM information_schema.ROUTINES
    WHERE DEFINER = 'orders_api_definer@localhost';

    SELECT
        TABLE_SCHEMA,
        TABLE_NAME
    FROM information_schema.VIEWS
    WHERE DEFINER = 'orders_api_definer@localhost';

    SELECT
        TRIGGER_SCHEMA,
        TRIGGER_NAME
    FROM information_schema.TRIGGERS
    WHERE DEFINER = 'orders_api_definer@localhost';

    SELECT
        EVENT_SCHEMA,
        EVENT_NAME
    FROM information_schema.EVENTS
    WHERE DEFINER = 'orders_api_definer@localhost';

To change the `DEFINER` of a procedure or function, you normally must drop and recreate the routine with the new `DEFINER`. For views or events, `ALTER VIEW` or `ALTER EVENT` can be used per supported syntax. For triggers, you must drop and recreate the trigger. Before making changes, save full definitions via `SHOW CREATE`.

## 17. Inspecting object definitions and privileges

Useful commands:

    SHOW CREATE PROCEDURE app_db.get_order_summary;

    SHOW CREATE FUNCTION app_db.calculate_tax;

    SHOW CREATE VIEW app_db.v_public_order_summary;

    SHOW TRIGGERS FROM app_db;

    SHOW EVENTS FROM app_db;

Check account privileges:

    SHOW GRANTS FOR 'orders_api_definer'@'localhost';
    SHOW GRANTS FOR 'app_runtime'@'%';

Inspect definitions in `INFORMATION_SCHEMA`:

    SELECT
        ROUTINE_NAME,
        ROUTINE_TYPE,
        DEFINER,
        SECURITY_TYPE,
        SQL_DATA_ACCESS
    FROM information_schema.ROUTINES
    WHERE ROUTINE_SCHEMA = 'app_db';

`SHOW CREATE` is a reliable source for saving complete object DDL before migrations. `INFORMATION_SCHEMA` is helpful for bulk audits and spotting anomalous `DEFINER` accounts.

## 18. Security risks of SQL SECURITY DEFINER

`DEFINER` is a powerful mechanism. It lets a lower-privileged user trigger an action running under another account's privileges. If a routine is poorly designed, this can become a privilege escalation path.

Common risks:

- Using `root` or a DBA account as `DEFINER`.
- Granting `EXECUTE` to too many accounts.
- Procedures taking an arbitrary `customer_id` and returning any customer's data.
- Procedures taking table/column/sort expressions and concatenating them directly into dynamic SQL.
- Triggers holding write/delete privileges on sensitive data that callers can fire indirectly.
- Events holding overly broad administrative privileges running on a schedule.
- Dropping, renaming, or altering grants of a `DEFINER` account without auditing dependent objects.
- Deployment pipelines unintentionally creating objects under a high-privilege account.

### 18.1. Least privilege principle

- Create a dedicated `DEFINER` account per responsibility group or object group with similar privileges.
- Grant privileges only on the schemas, tables, or columns actually needed.
- Never use `root`, `SUPER`, or global administrative privileges as routine execution privileges.
- Grant `EXECUTE` only to roles/users that need to call the routine.
- Do not grant `CREATE ROUTINE`, `TRIGGER`, or `EVENT` to runtime accounts unless necessary.
- Review grants periodically and after every business logic change.
- Monitor objects whose `DEFINER` differs from the deployment account.

### 18.2. Input validation and dynamic SQL

`SQL SECURITY DEFINER` does not automatically protect a routine against SQL injection. If a procedure builds dynamic SQL with `CONCAT`, untrusted data can become SQL syntax.

Do not do:

    -- Dangerous example, do not use:
    -- SET @sql_text = CONCAT(
    --     'SELECT * FROM app_db.orders ORDER BY ',
    --     p_sort_column
    -- );

Data values should be passed via prepared statement parameter markers when using dynamic SQL. Identifiers such as table names, column names, or sort directions cannot be bound like ordinary values; map them through a fixed allowlist before inserting into SQL.

Example allowlist logic:

    BEGIN
        DECLARE v_order_expression VARCHAR(64);

        IF p_sort_mode = 'newest' THEN
            SET v_order_expression = 'order_date DESC';
        ELSEIF p_sort_mode = 'largest' THEN
            SET v_order_expression = 'total_amount DESC';
        ELSE
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Unsupported sort mode';
        END IF;
    END;

Only fixed strings defined by the program may be placed in the identifier/expression portion of dynamic SQL. Never concatenate raw user input.

### 18.3. Restricting returned data

A `DEFINER` procedure reading a wide table can accidentally expose data. You should:

- Limit which columns are `SELECT`ed.
- Enforce appropriate tenant/customer ownership checks.
- Verify the caller's business-level authorization, not just parameter data-type validity.
- Bound row counts and date ranges.
- Avoid returning unnecessary sensitive fields.
- Audit sensitive operations if system requirements call for tracking.

Never treat the fact that a caller lacks `SELECT` on a table as sufficient data protection if that caller has `EXECUTE` on a procedure returning all that data.

## 19. Safe stored object deployment process

A migration deploying routines/views/triggers/events should follow a clear order:

1. Create the `DEFINER` account in the target environment.
2. Grant minimal privileges to the `DEFINER`.
3. Verify the account and grants using `SHOW GRANTS`.
4. Create objects with an explicit `DEFINER` or run `CREATE` under the `DEFINER` account itself.
5. Choose `SQL SECURITY` matching the authorization model.
6. Grant `EXECUTE` or object reference privileges to runtime roles/users.
7. Run `SHOW CREATE` to confirm `DEFINER` and `SQL SECURITY`.
8. Test with a runtime account holding exact production privileges.
9. Test missing-privilege cases to ensure proper failure behavior.
10. Verify Event Scheduler or trigger paths if objects fire automatically.
11. Record which objects depend on the `DEFINER` account to avoid accidental drops/renames.

### 19.1. When restoring or deploying to a new environment

Database dumps may contain `DEFINER` clauses in DDL. If objects are restored before creating `DEFINER` accounts, imports may fail or create orphans depending on server version and execution privileges.

Recommended order:

- Provision accounts and privileges.
- Restore/create stored objects.
- Grant runtime privileges.
- Inspect `DEFINER` and security types.
- Run smoke tests with the application account.

Do not replace every `DEFINER` with `root` in a dump just to make an import succeed. Map them to dedicated target-environment accounts and uphold least privilege.

## 20. Common mistakes

- Thinking `DEFINER` is always the account that created the object.
- Thinking `DEFINER` automatically possesses all required privileges.
- Thinking `SQL SECURITY INVOKER` still uses `DEFINER` privileges when reading tables.
- Thinking omitting `SQL SECURITY` defaults to `INVOKER`.
- Adding `SQL SECURITY` to triggers or events even though both always run under `DEFINER`.
- Granting `SELECT` on tables to app runtime when it only needs `EXECUTE` on a `DEFINER` procedure.
- Forgetting that `DEFINER` also needs `EXECUTE` on the routine per MySQL rules.
- Forgetting that `automatic_sp_privileges` may be turned off.
- Confusing `USER()` with `CURRENT_USER()` when investigating security context.
- Using the `root` account as `DEFINER`.
- Granting `SET_ANY_DEFINER` or equivalent privileges to application accounts.
- Using `ALLOW_NONEXISTENT_DEFINER` to ignore missing-account errors.
- Using roles without verifying default/active roles of `DEFINER`.
- Dropping or renaming an account still referenced by routines, views, triggers, or events.
- Restoring stored objects before provisioning `DEFINER` accounts.
- Concatenating user input directly into dynamic SQL inside a `DEFINER` routine.
- Assuming `SQL SECURITY DEFINER` automatically scopes data to the caller.
- Testing routines only with an admin account instead of the real runtime account.

## 21. Pre-deployment security checklist

- Identified creator, `DEFINER`, and invoker.
- Chose `DEFINER` or `INVOKER` according to authorization policy.
- Understood the default `SQL SECURITY` of the object type.
- Confirmed triggers/events always use the `DEFINER` context.
- Created the `DEFINER` account across all environments.
- Avoided using `root` or broad admin accounts as `DEFINER`.
- Granted least privilege to `DEFINER`.
- Granted minimal `EXECUTE` or object reference privileges to callers.
- Verified `DEFINER`'s `EXECUTE` privilege where required.
- Checked `automatic_sp_privileges` and auto-granted privileges.
- Verified effective roles of `DEFINER`.
- Verified `DEFINER`-assignment privileges for the exact MySQL version.
- Checked `USER()` and `CURRENT_USER()` in a test environment.
- Audited dynamic SQL, identifier allowlists, and bound values.
- Restricted returned data by business tenant/ownership rules.
- Audited `DEFINER` of routines, views, triggers, and events.
- Established a procedure to update `DEFINER` before dropping or renaming accounts.
- Tested using the real runtime account, not solely an admin account.
- Verified DDL after restore/deploy and saved `SHOW CREATE` output.

## 22. References

- MySQL 8.4 Reference Manual — Stored Object Access Control: https://dev.mysql.com/doc/refman/8.4/en/stored-objects-security.html
- MySQL 8.4 Reference Manual — CREATE PROCEDURE and CREATE FUNCTION: https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html
- MySQL 8.4 Reference Manual — Stored Routines and MySQL Privileges: https://dev.mysql.com/doc/refman/8.4/en/stored-routines-privileges.html
- MySQL 8.4 Reference Manual — CREATE VIEW: https://dev.mysql.com/doc/refman/8.4/en/create-view.html
- MySQL 8.4 Reference Manual — Privileges Provided by MySQL: https://dev.mysql.com/doc/refman/8.4/en/privileges-provided.html

`DEFINER` specifies the account attached to a stored object; `SQL SECURITY` determines whether the `DEFINER`'s or the invoker's privileges are used when the routine or view executes. Procedures, functions, and views default to `DEFINER` but can choose `INVOKER`; triggers and events always execute with their `DEFINER`'s privileges. Secure design requires dedicated `DEFINER` accounts, least privilege, properly scoped `EXECUTE` grants, verifying security context via `CURRENT_USER()`, role governance, and avoiding orphaned objects. Never treat `DEFINER` as a way to bypass authorization: it is a privilege boundary that must be carefully designed, deployed, tested, and audited.
