# Testing Functions, Procedures, and Triggers with pgTAP or SQL Scripts in PostgreSQL

Functions, procedures, and triggers bring business logic inside PostgreSQL. They can compute values, modify multiple tables, enforce invariants, write audit records, or fire automatically when data changes. Because this logic sits close to the data, a small bug in a routine can affect multiple application paths simultaneously. Testing directly inside the database catches bugs in outputs, side effects, exceptions, privileges, trigger wiring, and schema contracts before changes are deployed.

PostgreSQL does not include a dedicated unit testing framework in core. You can write tests using plain SQL scripts, build custom assertions, or install **pgTAP** to write tests following the Test Anything Protocol (TAP). pgTAP provides assertions for values, query results, exceptions, and database object metadata. Plain SQL scripts have fewer dependencies and fit small integration tests or environments that prohibit installing extensions.

This lesson belongs to the **Testing** chapter and focuses on:

- Distinguishing unit tests, database integration tests, and migration/schema tests.
- Preparing test databases, roles, fixtures, and repeatable data.
- Installing and running pgTAP with `pg_prove` or `psql`.
- Using `plan`, `finish`, `ok`, `is`, `throws_ok`, `lives_ok`, and `results_eq`.
- Testing scalar functions, set-returning functions, NULLs, boundary values, and errors.
- Testing procedures via `CALL`, side effects, and transaction behavior.
- Testing trigger definitions, trigger functions, events, timing, and row-level effects.
- Verifying function/procedure metadata, security mode, volatility, and trigger wiring.
- Testing permissions, `SECURITY DEFINER`, RLS, and execution contexts using realistic runtime roles.
- Writing plain SQL test harnesses with `DO` blocks, assertions, and transaction rollbacks.
- Managing fixtures, test isolation, deterministic results, and parallel test execution.
- Integrating tests into CI, migration pipelines, and release verification.

> **Principle:** testing a routine must verify both its return values and the resulting data state afterward. For triggers, you must prove the right event fired the right function and produced the right side effects. For functions/procedures with special privileges, tests must run under a role representing the real caller; running everything as superuser can hide permission and RLS bugs.

## 1. Defining the Right Testing Scope

Functions, procedures, and triggers have different invocation models and impacts. Choosing the right test type catches bugs at the right boundary.

### 1.1. Function

A function is invoked in SQL expressions, `SELECT`, `FROM`, `WHERE`, `DEFAULT`, `CHECK`, index expressions, or from other routines. A function can:

- Return a scalar value.
- Return a set of rows via `SETOF` or `RETURNS TABLE`.
- Accept `IN`/`OUT`/`INOUT` arguments.
- Raise an exception.
- Have side effects if permitted and designed to do so.

Function tests should verify signature, return type, results, NULL semantics, boundary conditions, exceptions, and permitted side effects.

### 1.2. Procedure

A procedure is invoked with `CALL`. Unlike a function, a procedure cannot be used as an expression inside `SELECT` and can support transaction control under appropriate conditions.

Procedure tests should check:

- Whether `CALL` succeeds.
- Which rows/columns are modified.
- `OUT`/`INOUT` parameters if present.
- Behavior when inputs are invalid or target rows do not exist.
- Idempotency and retry behavior.
- Transaction boundaries if the procedure performs `COMMIT`/`ROLLBACK`.

A procedure that executes transaction control cannot be called inside a transaction block already opened by a test harness. Such cases require separate integration tests on a dedicated database.

### 1.3. Trigger

A trigger is invoked automatically by PostgreSQL when an event such as `INSERT`, `UPDATE`, `DELETE`, or `TRUNCATE` occurs. A trigger can execute:

- `BEFORE` or `AFTER`.
- `FOR EACH ROW` or `FOR EACH STATEMENT`.
- Under a `WHEN` condition.
- On a table, view, or DDL event depending on the trigger type.
- Before/after other triggers according to PostgreSQL ordering rules.

Trigger tests must verify both the trigger configuration and the post-event result. Calling the trigger function directly does not prove the trigger is attached properly or fires at the right time.

### 1.4. Distinguishing test layers

| Test layer | Goal | Example |
| --- | --- | --- |
| Routine unit test | Verify small behavior with clear inputs/outputs | `calculate_discount(1000)` returns `100` |
| Database integration test | Verify routine together with tables, constraints, triggers, and roles | `CALL` procedure updates order and audit row |
| Schema contract test | Verify function, procedure, and trigger exist with expected signature/config | Function is `SECURITY INVOKER`, trigger calls expected function |
| Migration test | Verify new schema after applying migrations | Routines and triggers remain intact after upgrade |
| Concurrency test | Verify race conditions, locks, and isolation | Two sessions process the same order concurrently |
| Performance test | Measure latency/throughput under workload | Function runs in a 10,000-row query |

A test suite can contain multiple layers, as long as it is clear what each test proves.

## 2. What Is pgTAP?

`pgTAP` is a testing extension for PostgreSQL. It provides assertion functions that emit results in TAP format so a test runner can parse them.

### 2.1. TAP output

TAP is a simple text format. A test suite might output:

```text
1..3
ok 1 - function exists
ok 2 - discount is calculated
not ok 3 - negative amount is rejected
```

Each `ok` or `not ok` line corresponds to one assertion. A runner can aggregate results, report failing test files, and fail CI.

### 2.2. pgTAP runs inside the database

`pgTAP` is installed as a database extension:

```sql
CREATE EXTENSION IF NOT EXISTS pgtap;
```

The `pgTAP` package/binary must be present on the PostgreSQL host/container before running `CREATE EXTENSION`. Installing the package on a developer's machine does not automatically install the extension on a remote server.

### 2.3. pgTAP does not replace a test runner

`pgTAP` provides assertions and TAP output. You can use:

- `pg_prove` to run multiple SQL test files and aggregate TAP output.
- `psql` to run scripts directly.
- Build/CI tooling with TAP support.
- `pgTAP`'s `runtests()` function for an xUnit style inside the database.

`pg_prove` is a separately distributed client-side test runner, not a PostgreSQL SQL command.

### 2.4. When to choose pgTAP?

`pgTAP` is useful when:

- Many assertions are needed for database objects.
- You want to verify function signatures and trigger wiring.
- You need to test exceptions with `SQLSTATE`.
- You want TAP output for CI parsing.
- You want to group many SQL files into one suite with reporting.

Plain SQL scripts fit better when:

- The environment does not allow installing extensions.
- Tests are simple and few in number.
- You want fewer dependencies beyond the PostgreSQL client.
- You need to test a transaction-control procedure that cannot run inside a `pgTAP` transaction wrapper.

## 3. Preparing the Test Environment

Never test routines with side effects on production data. Create a dedicated test database with reproducible schemas, roles, and fixtures.

### 3.1. Install the pgTAP package on the PostgreSQL host

On Debian/Ubuntu, the package is usually named `pgtap`; package versions and names can differ by PostgreSQL major version/distribution.

Example installing a server-compatible package:

```bash
sudo apt-get install postgresql-17-pgtap
```

This is just an example for one major version. Check your OS repository/package manager and actual PostgreSQL version. With Docker, extension files must be present inside the image/container running PostgreSQL.

### 3.2. Install the extension in the test database

Connect to the test database with an appropriate administrative role:

```sql
CREATE EXTENSION IF NOT EXISTS pgtap;
```

It can be installed in a separate schema if supported by the extension and policy:

```sql
CREATE SCHEMA IF NOT EXISTS test_support;
CREATE EXTENSION IF NOT EXISTS pgtap
    WITH SCHEMA test_support;
```

If installed in a separate schema, adjust `search_path` or schema-qualify `pgTAP` function calls. Do not add the test schema to the application runtime `search_path` merely for testing convenience.

### 3.3. Verify the extension

```sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema
FROM pg_extension
WHERE extname = 'pgtap';
```

Check the installed `pgTAP` version:

```sql
SELECT pgtap_version();
```

### 3.4. Create a dedicated test database

Example:

```sql
CREATE DATABASE app_test;
```

Install schema migrations and `pgTAP` into this database. If CI creates an ephemeral database per job, jobs can run in parallel without contending over fixtures.

### 3.5. Separate roles

You can use dedicated roles:

| Role | Purpose |
| --- | --- |
| migration_owner | Creates/alters schema objects |
| app_runtime | Executes functions/procedures as the application |
| test_runner | Connects and runs the test suite |
| test_admin | Creates databases/roles/extensions in the test environment |

Do not use superuser for all permission assertions. You can use an admin role to set up fixtures, then run test groups under the runtime role under test.

## 4. Preparing an Illustrative Schema

The following examples use schemas `app` and `audit`. Create them in a test or lab database:

```sql
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE app.orders (
    id bigint PRIMARY KEY,
    status text NOT NULL,
    total_amount numeric(12, 2) NOT NULL,
    review_required boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE audit.order_status_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    old_status text NOT NULL,
    new_status text NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
```

The audit table in the example has no foreign key to `orders` so history is retained even if an order is archived or deleted. Real designs must select appropriate retention and referential behavior.

### 4.1. Function to test

```sql
CREATE OR REPLACE FUNCTION app.calculate_discount(p_amount numeric)
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $function$
BEGIN
    IF p_amount < 0 THEN
        RAISE EXCEPTION
            USING ERRCODE = '22003',
                  MESSAGE = 'amount must be nonnegative';
    END IF;

    IF p_amount >= 1000 THEN
        RETURN round(p_amount * 0.10, 2);
    END IF;

    RETURN 0;
END;
$function$;
```

The function contract:

- `NULL` input returns `NULL` because of `STRICT`.
- Negative amount raises exception SQLSTATE `22003`.
- Amounts below 1000 receive no discount.
- Amounts 1000 and above receive 10%.

### 4.2. Set-returning function

```sql
CREATE OR REPLACE FUNCTION app.open_order_ids()
RETURNS TABLE(order_id bigint)
LANGUAGE sql
STABLE
AS $function$
    SELECT o.id
    FROM app.orders AS o
    WHERE o.status = 'pending'
    ORDER BY o.id;
$function$;
```

### 4.3. Procedure to test

```sql
CREATE OR REPLACE PROCEDURE app.mark_order_reviewed(p_order_id bigint)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    UPDATE app.orders
    SET review_required = true,
        updated_at = clock_timestamp()
    WHERE id = p_order_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            USING ERRCODE = 'P0002',
                  MESSAGE = 'order not found';
    END IF;
END;
$procedure$;
```

The procedure does not `COMMIT` on its own; it participates in the caller's transaction. Thus it can be tested inside a transaction that issues `ROLLBACK` at the end of the script to clean up fixtures.

### 4.4. Trigger function and trigger

```sql
CREATE OR REPLACE FUNCTION audit.capture_order_status()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    INSERT INTO audit.order_status_events (
        order_id,
        old_status,
        new_status
    )
    VALUES (
        NEW.id,
        OLD.status,
        NEW.status
    );

    RETURN NEW;
END;
$function$;

CREATE TRIGGER orders_status_audit_trg
AFTER UPDATE OF status ON app.orders
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION audit.capture_order_status();
```

The trigger writes an audit record only when the `status` column is in the `UPDATE` target list and the value actually changes. The trigger function uses `OLD`/`NEW`, so it is designed for an `UPDATE` row-level trigger.

## 5. Structure of a pgTAP Test File

A test file typically has three parts:

1. Open a transaction and prepare fixtures.
2. Declare the number of assertions using `plan()`.
3. Run assertions, call `finish()`, and roll back.

Example:

```sql
BEGIN;

SELECT plan(3);

SELECT ok(true, 'basic assertion works');
SELECT is(1 + 1, 2, 'addition returns two');
SELECT isnt('pending', 'paid', 'statuses differ');

SELECT * FROM finish();

ROLLBACK;
```

### 5.1. plan()

`plan(n)` declares the expected number of assertions. If the script runs fewer or more tests, `pgTAP` reports a mismatch.

```sql
SELECT plan(5);
```

Prefer a fixed plan when the test count is known. It helps detect unexecuted test branches or early script termination.

### 5.2. no_plan()

`no_plan()` lets you avoid declaring the test count upfront:

```sql
SELECT * FROM no_plan();
```

Use it when the assertion count is genuinely unknown beforehand. Limit its use because it can mask a skipped test branch.

### 5.3. finish()

At the end of the suite, call:

```sql
SELECT * FROM finish();
```

`finish()` summarizes results and detects plan/assertion count mismatches. You can pass `finish(true)` to raise an exception when tests fail, which is useful when running via `psql` with `ON_ERROR_STOP`.

### 5.4. Transaction rollback

Test suites typically use:

```sql
BEGIN;
-- setup and assertions
SELECT * FROM finish();
ROLLBACK;
```

`ROLLBACK` cleans up test data as well as transactional DDL created within the suite. Do not place transaction-control procedure calls inside this wrapper.

### 5.5. Test setup does not count toward plan

`CREATE TABLE`, fixture `INSERT`s, and `SET LOCAL` are not assertions. Count only calls to test functions in `plan(n)`. Count carefully around branches with `skip()` or dynamic test loops.

## 6. Basic Assertions

### 6.1. ok()

Checks a boolean expression:

```sql
SELECT ok(
    app.calculate_discount(1000) = 100,
    'discount for amount 1000 is 100'
);
```

If the expression returns `NULL`, the test is not considered passing. When testing nullable values, use `is()` or an `IS NULL` predicate.

### 6.2. is() and isnt()

Compares two values:

```sql
SELECT is(
    app.calculate_discount(500),
    0::numeric,
    'amount below threshold has no discount'
);

SELECT isnt(
    app.calculate_discount(1200),
    0::numeric,
    'eligible amount has a discount'
);
```

Cast expected values to the exact type to avoid ambiguity among overloaded assertion functions.

### 6.3. cmp_ok()

Compares using an operator:

```sql
SELECT cmp_ok(
    app.calculate_discount(1500),
    '>',
    0::numeric,
    'discount is positive'
);
```

Use this when expressing a greater-than, less-than, or equality condition without building a manual boolean expression.

### 6.4. isa_ok()

Checks the type of a value:

```sql
SELECT isa_ok(
    app.calculate_discount(1000),
    'numeric',
    'discount result'
);
```

### 6.5. diag()

Prints diagnostic text without disrupting TAP results:

```sql
SELECT diag(
    'server version: ' || current_setting('server_version')
);
```

Diagnostics should provide helpful context on failure without logging secrets or sensitive data.

## 7. Testing Functions with pgTAP

A function test should verify both behavior and the object contract.

### 7.1. Verify function existence

```sql
SELECT has_function(
    'app',
    'calculate_discount',
    ARRAY['numeric'],
    'calculate_discount(numeric) exists'
);
```

The signature matters because PostgreSQL supports function overloading. Checking only the name can miss an incorrect overload or a missing signature.

### 7.2. Verify return type

```sql
SELECT function_returns(
    'app',
    'calculate_discount',
    ARRAY['numeric'],
    'numeric',
    'calculate_discount returns numeric'
);
```

For a set-returning function, the type argument uses the `setof ...` form per `pgTAP` syntax.

### 7.3. Verify language and volatility

```sql
SELECT function_lang_is(
    'app',
    'calculate_discount',
    ARRAY['numeric'],
    'plpgsql',
    'discount function uses PL/pgSQL'
);

SELECT volatility_is(
    'app',
    'calculate_discount',
    ARRAY['numeric'],
    'immutable',
    'discount function is immutable'
);
```

Volatility is a contract with the planner. Assert `IMMUTABLE` only if the implementation truly depends on no database state, clock, sequence, or mutable external state.

### 7.4. Verify results and boundary values

```sql
SELECT is(
    app.calculate_discount(0),
    0::numeric,
    'zero amount has zero discount'
);

SELECT is(
    app.calculate_discount(999.99),
    0::numeric,
    'amount just below threshold has no discount'
);

SELECT is(
    app.calculate_discount(1000),
    100::numeric,
    'threshold amount receives ten percent'
);

SELECT is(
    app.calculate_discount(1250),
    125::numeric,
    'larger amount receives ten percent'
);

SELECT is(
    app.calculate_discount(NULL::numeric),
    NULL::numeric,
    'strict function returns null for null input'
);
```

Boundary tests are usually far more valuable than repeating multiple tests on ordinary inputs.

### 7.5. Verify exceptions by SQLSTATE

```sql
SELECT throws_ok(
    'SELECT app.calculate_discount(-1)',
    '22003',
    'amount must be nonnegative',
    'negative amount is rejected'
);
```

`SQLSTATE` is more stable across locales than error text. For PostgreSQL core errors with localized messages, you can pass `NULL` for the expected message and check only the error code.

### 7.6. Verify a query raises no error

```sql
SELECT lives_ok(
    'SELECT app.calculate_discount(250)',
    'normal amount does not raise an exception'
);
```

`lives_ok()` only confirms the statement ran without raising an exception. It does not prove the result is correct; combine it with `is()` or `results_eq()`.

### 7.7. Verify set-returning functions

Create fixtures:

```sql
INSERT INTO app.orders (
    id, status, total_amount
)
VALUES
    (91001, 'pending', 100),
    (91002, 'paid', 200),
    (91003, 'pending', 300);
```

Compare query results with expected rows:

```sql
SELECT results_eq(
    'SELECT order_id FROM app.open_order_ids()',
    $$VALUES (91001::bigint), (91003::bigint)$$,
    'open_order_ids returns pending orders in id order'
);
```

`results_eq()` compares the results of two queries including row order. If order is not part of the contract, use `set_eq()` for order-independent set comparison. If duplicates matter, consider `bag_eq()`.

### 7.8. Verify empty results

```sql
SELECT is_empty(
    'SELECT order_id FROM app.open_order_ids() WHERE order_id = 999999',
    'unknown order is absent from result'
);
```

`is_empty()` fits when the contract expects zero rows. When results must contain rows, use `isnt_empty()`.

## 8. Testing Function Overloads and NULL Semantics

### 8.1. Function overloads

Suppose we have:

```sql
CREATE FUNCTION app.format_code(p_value integer)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $function$
    SELECT 'I-' || p_value::text;
$function$;

CREATE FUNCTION app.format_code(p_value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $function$
    SELECT 'T-' || p_value;
$function$;
```

Test each signature:

```sql
SELECT has_function('app', 'format_code', ARRAY['integer']);
SELECT has_function('app', 'format_code', ARRAY['text']);

SELECT is(
    app.format_code(7),
    'I-7',
    'integer overload is selected'
);

SELECT is(
    app.format_code('7'::text),
    'T-7',
    'text overload is selected'
);
```

### 8.2. NULL input

Distinguish:

- `STRICT` function: PostgreSQL does not invoke the function when an argument is `NULL` and returns `NULL`.
- Non-`STRICT` function: the function body receives `NULL` and decides its own behavior.

Explicitly test the contract:

```sql
SELECT is(
    app.calculate_discount(NULL::numeric),
    NULL::numeric,
    'NULL input is propagated'
);
```

### 8.3. Empty strings and whitespace

`NULL`, empty strings, and whitespace are not equivalent. If a function normalizes text, test each separately:

```sql
SELECT is(app.normalize_code(NULL), NULL::text, 'NULL stays NULL');
SELECT is(app.normalize_code(''), '', 'empty string behavior is explicit');
SELECT is(app.normalize_code('  A-1  '), 'A-1', 'surrounding spaces are trimmed');
```

Expected values must follow the business contract. Do not treat empty strings as `NULL` if the application distinguishes the two.

## 9. Testing Procedures

Procedures are invoked with `CALL`. `pgTAP` can verify existence, procedure kind, exceptions, and side effects.

### 9.1. Verify the object is a procedure

```sql
SELECT has_function(
    'app',
    'mark_order_reviewed',
    ARRAY['bigint'],
    'mark_order_reviewed(bigint) exists'
);

SELECT is_procedure(
    'app',
    'mark_order_reviewed',
    ARRAY['bigint'],
    'mark_order_reviewed is a procedure'
);
```

`pgTAP` uses `has_function()` for both functions and procedures in the catalog; `is_procedure()` verifies the object kind.

### 9.2. Fixture for the procedure

```sql
INSERT INTO app.orders (
    id, status, total_amount, review_required
)
VALUES (
    92001, 'pending', 250, false
);
```

### 9.3. CALL and verifying side effects

```sql
SELECT lives_ok(
    'CALL app.mark_order_reviewed(92001)',
    'existing order can be marked for review'
);

SELECT is(
    (SELECT review_required FROM app.orders WHERE id = 92001),
    true,
    'procedure updates review_required'
);
```

`lives_ok()` only confirms `CALL` did not error. The subsequent assertion confirms the data actually changed as expected.

### 9.4. Test error paths

```sql
SELECT throws_ok(
    'CALL app.mark_order_reviewed(999999)',
    'P0002',
    'order not found',
    'procedure rejects missing order'
);
```

Also test cases where the target row does not exist, status forbids updating, the caller lacks privileges, and inputs are invalid.

### 9.5. OUT and INOUT parameters

Procedures can declare `OUT`/`INOUT` arguments. Use `CALL` with variables in PL/pgSQL or an appropriate client to capture outputs. Test outputs alongside side effects; do not check only row updates if output parameters are part of the API contract.

### 9.6. Procedures with transaction control

A procedure can execute `COMMIT`/`ROLLBACK` when invoked under permitted conditions. A procedure performing transaction control cannot be called inside a `pgTAP` test transaction or a `DO` block inside a transaction wrapper.

To test this behavior:

1. Create a dedicated test database.
2. Run `CALL` at the top level without an outer `BEGIN`.
3. Use fixtures that can be deleted/recreated.
4. Verify commit boundaries from another connection.
5. Clean up the database or fixtures after the test.

Do not assume a `ROLLBACK` at the end of a test will undo transactions the procedure already committed.

## 10. Testing Triggers: Configuration and Behavior

Triggers have two parts to verify: the trigger object on the table and the trigger function it invokes.

### 10.1. Verify trigger existence

```sql
SELECT has_trigger(
    'app',
    'orders',
    'orders_status_audit_trg',
    'orders table has status audit trigger'
);
```

### 10.2. Verify the trigger calls the right function

```sql
SELECT trigger_is(
    'app',
    'orders',
    'orders_status_audit_trg',
    'audit',
    'capture_order_status',
    'status trigger calls audit function'
);
```

This test checks wiring. It does not prove the trigger function handles `OLD`/`NEW` properly; a separate behavioral test is needed.

### 10.3. Verify the trigger list

```sql
SELECT triggers_are(
    'app',
    'orders',
    ARRAY['orders_status_audit_trg'],
    'orders table has only the expected user trigger'
);
```

`triggers_are()` checks the set of trigger names on a table. Use it to catch both extra and missing triggers. On tables with multiple triggers, list all triggers belonging to the test's contract.

### 10.4. Create fixtures and fire the trigger

```sql
INSERT INTO app.orders (
    id, status, total_amount
)
VALUES (
    93001, 'pending', 500
);

UPDATE app.orders
SET status = 'paid'
WHERE id = 93001;
```

Check the audit row:

```sql
SELECT is(
    (
        SELECT count(*)
        FROM audit.order_status_events
        WHERE order_id = 93001
    ),
    1::bigint,
    'status change creates one audit event'
);

SELECT results_eq(
    $query$
        SELECT old_status, new_status
        FROM audit.order_status_events
        WHERE order_id = 93001
    $query$,
    $$VALUES ('pending'::text, 'paid'::text)$$,
    'audit event records OLD and NEW status'
);
```

### 10.5. Verify the WHEN condition

The example trigger only logs an audit row when `status` actually changes. Test an `UPDATE` that leaves `status` unchanged:

```sql
UPDATE app.orders
SET status = 'paid'
WHERE id = 93001;

SELECT is(
    (
        SELECT count(*)
        FROM audit.order_status_events
        WHERE order_id = 93001
    ),
    1::bigint,
    'same status does not create another audit event'
);
```

### 10.6. Verify other events do not fire the trigger

The trigger is declared `AFTER UPDATE OF status`, so updating another column should not create an audit event:

```sql
UPDATE app.orders
SET total_amount = 600
WHERE id = 93001;

SELECT is(
    (
        SELECT count(*)
        FROM audit.order_status_events
        WHERE order_id = 93001
    ),
    1::bigint,
    'updating amount does not fire status audit trigger'
);
```

Note that `UPDATE OF status` checks whether the column appears in the `SET` target list. The `WHEN` clause determines whether `OLD.status` and `NEW.status` actually differ.

## 11. Testing Different Trigger Types

### 11.1. BEFORE ROW trigger

A `BEFORE ROW` trigger can modify `NEW` before the row is written.

Code normalization example:

```sql
CREATE OR REPLACE FUNCTION app.normalize_customer_code()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.customer_code := upper(trim(NEW.customer_code));
    RETURN NEW;
END;
$function$;

CREATE TRIGGER customers_normalize_code_biu
BEFORE INSERT OR UPDATE OF customer_code
ON app.customers
FOR EACH ROW
EXECUTE FUNCTION app.normalize_customer_code();
```

Tests must insert/update through the table, then `SELECT` the stored value. Calling `normalize_customer_code()` directly does not simulate the full trigger context because the function needs `NEW`/`TG_OP` supplied by PostgreSQL.

### 11.2. AFTER ROW trigger

`AFTER ROW` triggers typically fit audits, outboxes, or transactional side effects. Tests verify that the row was written and the corresponding side effect was created in the same transaction.

### 11.3. Statement-level trigger

A statement-level trigger runs once per statement regardless of how many rows the statement affects. Test with:

- A statement affecting zero rows.
- A statement affecting one row.
- A statement affecting multiple rows.

Do not assume a statement-level trigger fires only when rows actually change; verify the semantics of the event and trigger definition.

### 11.4. Transition tables

Some `AFTER` statement triggers can use transition relations to inspect the set of changed rows. Test bulk `UPDATE`/`DELETE` to ensure all changed rows are processed properly rather than just one row.

### 11.5. DELETE trigger

A `DELETE` trigger uses `OLD` and has no `NEW` row like `INSERT`/`UPDATE`. Create a fixture, `DELETE`, and verify the audit snapshot stores the pre-delete values.

### 11.6. TRUNCATE trigger

`TRUNCATE` has its own trigger event and statement-level behavior. If the application can `TRUNCATE` a table, test it separately because `DELETE` triggers do not substitute for a `TRUNCATE` trigger.

### 11.7. Trigger ordering

When multiple triggers share the same event/timing on the same relation, PostgreSQL orders execution by trigger name. Do not rely on accidental ordering in test fixtures; if ordering is part of the design, name triggers intentionally and test the final outcome.

## 12. Testing Function Metadata and Security Properties

`pgTAP` provides assertions for object contracts, helping migration tests catch unintended changes.

### 12.1. SECURITY DEFINER

```sql
SELECT is_definer(
    'app_private',
    'expire_one_order',
    ARRAY['bigint'],
    'maintenance function is SECURITY DEFINER'
);
```

If the function must run under caller privileges, use `isnt_definer()`.

### 12.2. Language

```sql
SELECT function_lang_is(
    'app',
    'calculate_discount',
    ARRAY['numeric'],
    'plpgsql',
    'discount function uses expected language'
);
```

### 12.3. Volatility

```sql
SELECT volatility_is(
    'app',
    'calculate_discount',
    ARRAY['numeric'],
    'immutable',
    'discount function volatility is immutable'
);
```

### 12.4. Procedure kind and return type

```sql
SELECT is_procedure(
    'app',
    'mark_order_reviewed',
    ARRAY['bigint'],
    'routine remains a procedure'
);

SELECT function_returns(
    'app',
    'mark_order_reviewed',
    ARRAY['bigint'],
    'void',
    'procedure has void return type'
);
```

### 12.5. Privileges

You can use PostgreSQL privilege helper functions in `pgTAP` assertions:

```sql
SELECT ok(
    has_function_privilege(
        'app_runtime',
        'app.calculate_discount(numeric)',
        'EXECUTE'
    ),
    'runtime role can execute discount function'
);

SELECT ok(
    NOT has_function_privilege(
        'app_runtime',
        'app_private.expire_one_order(bigint)',
        'EXECUTE'
    ),
    'runtime role cannot execute maintenance function'
);
```

This test checks effective privileges at runtime. Run it using a role able to inspect catalog/privilege metadata and confirm exact role/object names.

### 12.6. Testing with real roles

To verify real behavior:

- Connect as `app_runtime`.
- Call permitted functions/procedures.
- Confirm functions are denied without `EXECUTE`.
- Confirm schema `USAGE` and underlying table privileges.
- Verify `SECURITY DEFINER` grants only the intended capability.
- Test RLS using a non-superuser, non-table-owner role whenever policies should apply.

Superusers bypass many security checks. Never use results from a superuser session to conclude runtime authorization is correct.

## 13. Testing Trigger Functions with Security Context

A trigger function can be `SECURITY INVOKER` or `SECURITY DEFINER`. Tests must verify effective privileges and RLS behavior.

### 13.1. Verify function owner and mode

Use `pgTAP` `is_definer()` or a catalog query to confirm the mode. If a trigger function is `SECURITY DEFINER`, the owner should be a dedicated least-privilege role.

### 13.2. Run DML with the runtime role

Connect with a role matching the application and execute `INSERT`/`UPDATE`/`DELETE`. Verify:

- The caller has DML privileges on the source table.
- The trigger performs the designed side effect.
- The caller cannot directly modify the audit table unless permitted.
- The trigger does not create unintended access.
- RLS policies behave properly in the effective user context.

### 13.3. Do not test only as owner

A table owner can bypass RLS under PostgreSQL rules unless `FORCE ROW LEVEL SECURITY` is enabled. Testing as the owner can yield different results from the application runtime role.

### 13.4. Testing errors in triggers

If a trigger function raises an exception, the DML statement normally fails along with the transaction. Test the `SQLSTATE`, application-defined exception message, and confirm the source row was not partially written.

```sql
SELECT throws_ok(
    $$INSERT INTO app.orders (id, status, total_amount)
      VALUES (93002, 'invalid', 100)$$,
    '23514',
    NULL,
    'invalid order is rejected by constraint or trigger'
);
```

If you need to distinguish a constraint error from a trigger error, use a distinct `SQLSTATE` and message explicitly raised by the routine.

## 14. A Complete pgTAP Suite

The example below tests a function, procedure, and trigger in one transaction. It assumes the schema, routines, and trigger from the setup section are already installed in the test database.

```sql
BEGIN;

SELECT plan(18);

-- Function contract.
SELECT has_function(
    'app', 'calculate_discount', ARRAY['numeric'],
    'discount function exists'
);
SELECT function_returns(
    'app', 'calculate_discount', ARRAY['numeric'], 'numeric',
    'discount function returns numeric'
);
SELECT function_lang_is(
    'app', 'calculate_discount', ARRAY['numeric'], 'plpgsql',
    'discount function uses PL/pgSQL'
);
SELECT volatility_is(
    'app', 'calculate_discount', ARRAY['numeric'], 'immutable',
    'discount function is immutable'
);

-- Function behavior.
SELECT is(app.calculate_discount(0), 0::numeric, 'zero has no discount');
SELECT is(app.calculate_discount(999.99), 0::numeric, 'below threshold');
SELECT is(app.calculate_discount(1000), 100::numeric, 'threshold discount');
SELECT is(app.calculate_discount(1250), 125::numeric, 'larger discount');
SELECT is(
    app.calculate_discount(NULL::numeric),
    NULL::numeric,
    'NULL propagates through STRICT function'
);
SELECT throws_ok(
    'SELECT app.calculate_discount(-1)',
    '22003',
    'amount must be nonnegative',
    'negative input is rejected'
);

-- Procedure contract and behavior.
SELECT is_procedure(
    'app', 'mark_order_reviewed', ARRAY['bigint'],
    'review routine is a procedure'
);
INSERT INTO app.orders (id, status, total_amount)
VALUES (92001, 'pending', 250);

SELECT lives_ok(
    'CALL app.mark_order_reviewed(92001)',
    'procedure accepts existing order'
);
SELECT is(
    (SELECT review_required FROM app.orders WHERE id = 92001),
    true,
    'procedure updates the order'
);
SELECT throws_ok(
    'CALL app.mark_order_reviewed(999999)',
    'P0002',
    'order not found',
    'procedure rejects missing order'
);

-- Trigger contract and behavior.
SELECT has_trigger(
    'app', 'orders', 'orders_status_audit_trg',
    'status audit trigger exists'
);
SELECT trigger_is(
    'app', 'orders', 'orders_status_audit_trg',
    'audit', 'capture_order_status',
    'status trigger calls expected function'
);

INSERT INTO app.orders (id, status, total_amount)
VALUES (93001, 'pending', 500);

UPDATE app.orders
SET status = 'paid'
WHERE id = 93001;

SELECT is(
    (SELECT count(*) FROM audit.order_status_events WHERE order_id = 93001),
    1::bigint,
    'status change writes one audit event'
);
SELECT results_eq(
    'SELECT old_status, new_status FROM audit.order_status_events WHERE order_id = 93001',
    $$VALUES ('pending'::text, 'paid'::text)$$,
    'audit event contains expected old and new values'
);

SELECT * FROM finish();
ROLLBACK;
```

The assertion count in `plan(18)` must match the exact number of test calls. Update the plan simultaneously whenever adding or removing assertions. Fixtures and procedure side effects are rolled back at the end because the example procedure performs no transaction control.

## 15. Plain SQL Scripts Without pgTAP

You can build a small test harness in PL/pgSQL. This does not produce standard TAP output, but it suffices to fail fast when an assertion does not hold.

### 15.1. Create a temporary assertion helper

```sql
CREATE FUNCTION pg_temp.assert_true(
    p_condition boolean,
    p_description text
)
RETURNS text
LANGUAGE plpgsql
AS $function$
BEGIN
    IF p_condition IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'ASSERTION FAILED: %', p_description;
    END IF;

    RETURN 'ok - ' || p_description;
END;
$function$;
```

The helper returns an `ok` line when true and raises an exception when false or `NULL`.

### 15.2. Run tests with psql

Save as `tests/routines.sql`:

```sql
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
\pset pager off

BEGIN;

CREATE FUNCTION pg_temp.assert_true(
    p_condition boolean,
    p_description text
)
RETURNS text
LANGUAGE plpgsql
AS $function$
BEGIN
    IF p_condition IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'ASSERTION FAILED: %', p_description;
    END IF;

    RETURN 'ok - ' || p_description;
END;
$function$;

SELECT pg_temp.assert_true(
    app.calculate_discount(1000) = 100,
    'discount threshold'
);

SELECT pg_temp.assert_true(
    app.calculate_discount(NULL::numeric) IS NULL,
    'strict function propagates NULL'
);

INSERT INTO app.orders (id, status, total_amount)
VALUES (94001, 'pending', 100);

CALL app.mark_order_reviewed(94001);

SELECT pg_temp.assert_true(
    (SELECT review_required FROM app.orders WHERE id = 94001),
    'procedure updates order'
);

UPDATE app.orders
SET status = 'paid'
WHERE id = 94001;

SELECT pg_temp.assert_true(
    (SELECT count(*) = 1
     FROM audit.order_status_events
     WHERE order_id = 94001),
    'trigger writes audit event'
);

ROLLBACK;
```

Run:

```bash
psql -X -v ON_ERROR_STOP=1 -d app_test -f tests/routines.sql
```

`-X` ignores `psqlrc` so output and behavior are consistent. `ON_ERROR_STOP=1` makes `psql` stop on SQL errors. When the script fails inside a transaction, the connection closes and PostgreSQL rolls back the uncommitted transaction.

### 15.3. Checking exceptions with a DO block

Without `pgTAP`, you can catch the expected `SQLSTATE`:

```sql
DO $test$
BEGIN
    PERFORM app.calculate_discount(-1);

    RAISE EXCEPTION
        'expected calculate_discount to reject a negative amount';
EXCEPTION
    WHEN SQLSTATE '22003' THEN
        -- Expected exception.
        NULL;
END;
$test$;
```

If the function fails to raise an exception, the `RAISE` generated by the test has a different `SQLSTATE` and is not caught by the handler, causing the script to fail.

### 15.4. Limitations of custom assertions

Custom helpers must be maintained and lack full diagnostics and the TAP ecosystem. As a test suite grows, `pgTAP` typically reduces boilerplate and improves CI integration.

## 16. xUnit-Style Tests in pgTAP

`pgTAP` supports organizing tests into functions returning `SETOF TEXT`, then executing them with `runtests()`.

### 16.1. Test function

```sql
CREATE SCHEMA IF NOT EXISTS tests;

CREATE OR REPLACE FUNCTION tests.test_calculate_discount()
RETURNS SETOF text
LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN NEXT is(
        app.calculate_discount(1000),
        100::numeric,
        'threshold discount'
    );

    RETURN NEXT throws_ok(
        'SELECT app.calculate_discount(-1)',
        '22003',
        'amount must be nonnegative',
        'negative input is rejected'
    );
END;
$function$;
```

### 16.2. Run tests

```sql
SELECT * FROM runtests('tests');
```

Syntax and test function discovery follow the `pgTAP` version in use. `pgTAP` defines conventions for setup/teardown and test routine discovery; read the documentation for your installed version before standardizing function names.

### 16.3. When to use xUnit style?

Suitable when:

- You want to group tests by module/schema.
- You want shared setup/teardown.
- Each test function contains multiple assertions.
- You want to run the suite with a single command.

SQL test files are often easier to review when tests are long SQL workflows or need explicit transaction setups.

## 17. Fixtures and Test Data

Reliable tests require deterministic and reproducible fixtures.

### 17.1. Independent data

Each test should own its fixture IDs or use a separate data namespace. Avoid using IDs that could collide with data created by another developer.

### 17.2. Setup and teardown

Options include:

- Creating fixtures inside a transaction and issuing `ROLLBACK`.
- Using a dedicated test schema and running `DROP SCHEMA` after the suite.
- Using an ephemeral database per CI job.
- Using ordered setup/teardown helpers.

Transaction rollback is a good choice for tests that do not commit inside procedures and have no external side effects.

### 17.3. Avoid relying on sequence state

Sequence increments do not roll back like ordinary table rows. If a test depends on an exact generated ID, use explicit fixture IDs or capture the ID with `RETURNING` instead of assuming a sequence always starts from a fixed number.

### 17.4. Clock and timezone

If a routine depends on the clock:

- Use a clock injection parameter when designing for testability.
- Compare time intervals with an appropriate tolerance.
- Set timezone explicitly with `SET LOCAL` if behavior depends on timezone.
- Avoid asserting exact timestamp equality when a function uses `clock_timestamp()`.

### 17.5. Randomness

If a function uses random UUIDs or random numbers, test the contract rather than hardcoding outputs. You can assert format, uniqueness, or range. For algorithms requiring deterministic tests, inject an appropriate seed/source of randomness.

### 17.6. Order-independent tests

If a query has no `ORDER BY`, result ordering is not guaranteed. Use `set_eq()` or add `ORDER BY` in the query when order is part of the contract.

## 18. Testing Triggers Without False Positives

A trigger test can pass due to flawed fixture data or overly weak assertions.

### 18.1. Prove the trigger actually ran

Do not just check that the audit table has some row. Filter by the fixture key and assert the exact old/new values.

### 18.2. Prove the trigger does not fire on the wrong event

If a trigger applies only to `UPDATE OF status`, test updating `total_amount` and assert no new event is created.

### 18.3. Test multi-row DML

`UPDATE` multiple rows in a single statement and verify a row-level trigger creates the exact matching number of audit rows. Test a statement-level trigger with a statement affecting multiple rows and verify only one statement event is created.

### 18.4. Test rollback atomicity

Within the same transaction:

1. `UPDATE` the source row.
2. Trigger creates the audit row.
3. `ROLLBACK`.
4. Verify neither the source update nor the audit insert exists.

This proves database side effects within the same transaction. It does not apply to HTTP calls, emails, or external queues invoked externally by a trigger/function.

### 18.5. Test trigger exceptions

When a trigger raises an exception, verify the source DML rolls back. If the trigger writes multiple audit rows before failing at the last step, verify all transactional changes within the statement/transaction obey expected atomicity.

### 18.6. Test trigger recursion

A trigger can update the same table that fired it. Test recursion guards, `pg_trigger_depth()` if used, and termination behavior. Do not test only a single-row happy path.

### 18.7. Test disabled triggers and replication roles

Triggers can be disabled or affected by `session_replication_role`. If deployment/replication workflows alter this setting, test under the corresponding configuration and verify data integrity does not rely on a trigger that gets unexpectedly bypassed.

## 19. Testing Privileges, SECURITY DEFINER, and RLS

Security tests must simulate realistic roles.

### 19.1. Function EXECUTE grants

Use `pgTAP` `function_privs_are()` when ACL assertions are needed. `pgTAP`'s schema name depends on where the extension is installed; if `pgTAP` is in `public`, call functions without a prefix. You can use `has_function_privilege()` as a direct assertion to avoid depending on ACL assertion signatures.

### 19.2. Using privilege helpers

```sql
SELECT ok(
    has_function_privilege(
        'app_runtime',
        'app.calculate_discount(numeric)',
        'EXECUTE'
    ),
    'runtime role has EXECUTE'
);
```

Check both allowed roles and denied roles.

### 19.3. Testing SECURITY DEFINER

Check `is_definer()` and the owner. Then invoke the routine as the runtime role to prove the function permits only the defined operation.

### 19.4. Search path

For `SECURITY DEFINER`, test the function-local `search_path` and ensure schemas on the path do not allow `CREATE` by untrusted roles. Test temporary objects with colliding names if the routine resolves unqualified identifiers.

### 19.5. RLS

Test with a non-superuser, non-table-owner role to confirm policies apply. Verify:

- `SELECT` sees only permitted rows.
- `UPDATE`/`DELETE` affect only permitted rows.
- Whether `SECURITY DEFINER` alters the effective user.
- Whether `FORCE ROW LEVEL SECURITY` is enabled where needed.

### 19.6. Do not rely on SET ROLE as the sole proof

`SET ROLE` can be useful inside a test transaction, but results do not always match connecting directly as the login role—especially regarding session authorization, role memberships, connection settings, or authentication context. For security-sensitive flows, open a dedicated connection as the actual role.

## 20. Testing Migrations and Schema Contracts

Routine tests should run after migrations create or update functions, procedures, and triggers.

### 20.1. Test from an empty database

CI should create a fresh database, apply all migrations in order, and run tests. This catches missing dependencies or migrations that fail to reconstruct the schema.

### 20.2. Test upgrades from a prior version

A migration might run cleanly on an empty database yet fail when upgrading an older database with existing data/indexes/triggers. Use a snapshot or fixture database from a previous version to test the upgrade path.

### 20.3. Contract assertions

Verify:

- Function/procedure signatures.
- Return type.
- Language and volatility.
- `SECURITY DEFINER`/`INVOKER`.
- Trigger existence and attached function.
- Dependent constraints/indexes.
- Owner and `EXECUTE` grants.
- Function-local settings/`search_path`.

### 20.4. Migrations must not check object existence alone

A function can exist with the right signature while its body behavior changed. Combine catalog assertions with behavioral tests.

### 20.5. Test after CREATE OR REPLACE

`CREATE OR REPLACE FUNCTION` can alter body or properties. After migration, re-verify owner, ACL, `SECURITY` mode, volatility, and `SET` clauses. Do not assume pre-migration tests still represent the new state.

## 21. Testing Concurrency and Transaction Behavior

Sequential unit tests do not uncover all race conditions.

### 21.1. Two sessions processing one row

Use two connections to test procedures that claim/lock rows. Verify that only one worker succeeds if the contract requires a single claimant.

### 21.2. FOR UPDATE SKIP LOCKED

If a routine uses `SKIP LOCKED`, test two concurrent sessions and confirm each session receives distinct rows. Avoid fixed-timing tests; use barriers or coordination tables in the test harness.

### 21.3. Deadlocks and retries

Test routines that lock multiple tables. Check lock ordering, deadlock `SQLSTATE`, and application retry policies. Do not write deadlock tests using random sleeps while expecting fixed ordering.

### 21.4. Isolation levels

Behavior can differ across `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE`. Test at the application's actual isolation level, especially for functions that check state before updating data.

### 21.5. Advisory locks

If a procedure uses advisory locks, test release/cleanup on exceptions, transaction rollbacks, and session disconnects. Distinguish transaction-level from session-level advisory locks.

### 21.6. Test transaction-control procedures separately

Procedures containing `COMMIT`/`ROLLBACK` must be invoked at top level. Use an integration script opening multiple connections to test visibility and commit boundaries; do not wrap inside a `pgTAP` transaction.

## 22. Meaningful Performance Tests

`pgTAP` includes `performs_ok()` to check that a query does not exceed a time threshold. Use it cautiously in CI.

### 22.1. performs_ok()

Example:

```sql
SELECT performs_ok(
    'SELECT app.open_order_ids()',
    250,
    'open order query completes within 250 ms'
);
```

This is a point-in-time runtime assertion. It does not replace benchmarking and fluctuates with CPU, cache, I/O, shared runners, or concurrency.

### 22.2. Do not set overly tight thresholds

If baseline p95 is 100 ms, a test should not fail at 101 ms on a shared CI runner. Set generous thresholds to catch major regressions; use dedicated benchmarks for strict performance acceptance.

### 22.3. Representative data

A function querying 10 rows on an empty table proves nothing about performance on tens of millions of rows. Performance tests require datasets, indexes, statistics, and concurrency similar to production.

### 22.4. EXPLAIN

You can use `EXPLAIN (ANALYZE, BUFFERS)` on test workloads to inspect execution time, buffers, and plans. `EXPLAIN ANALYZE` actually executes the statement; for DML, use transaction rollback and watch for external side effects.

### 22.5. Separate correctness and performance

A function returning correct results slowly is still a correctness pass and a performance failure. Separate suites so behavioral tests do not become flaky due to resource contention.

## 23. Testing Bad Data and Property-Based Cases

A few examples do not cover the entire input space.

### 23.1. Boundary matrix

For numeric inputs, test:

- `NULL`.
- Negative values.
- Zero.
- Just below threshold.
- Exact threshold.
- Just above threshold.
- Very large values.
- Values involving scale/rounding.
- Values causing overflow.

### 23.2. String inputs

Test:

- Empty string.
- Leading/trailing whitespace.
- Unicode.
- Mixed case.
- Quotes and delimiters.
- Invalid characters.
- Maximum-length/overlong strings.
- Collation-sensitive values.

### 23.3. Date/time

Test leap days, daylight saving transitions, timezone boundaries, `NULL`, future/past timestamps, and inclusive/exclusive range endpoints.

### 23.4. Property-based testing

You can generate many inputs with SQL `generate_series` or client-side property testing. Example checking the non-negative discount invariant:

```sql
SELECT ok(
    bool_and(app.calculate_discount(x) >= 0),
    'discount is nonnegative for all generated amounts'
)
FROM generate_series(0, 5000, 25) AS values(x);
```

Property tests must control random seeds and inputs so failures can be reproduced.

### 23.5. Fuzzing dynamic SQL

If a function accepts identifiers or text inputs, fuzz quote characters, Unicode, long identifiers, case folding, and reserved words. Confirm inputs are rejected or safely handled without becoming unintended SQL syntax.

## 24. Failure Diagnostics and TAP Output

A useful suite helps developers understand why a test failed.

### 24.1. Specific assertion descriptions

Good:

```sql
SELECT is(
    app.calculate_discount(1000),
    100::numeric,
    'amount at discount threshold returns 10 percent'
);
```

Avoid vague descriptions like `function works`.

### 24.2. Expected vs. actual values

Use `is()`, `results_eq()`, and `throws_ok()` so `pgTAP` outputs diagnostics. In custom `DO` blocks, exceptions should mention the relevant input/cohort without exposing secrets.

### 24.3. SQLSTATE over error messages

Messages can change by locale or version. Prefer `SQLSTATE` for PostgreSQL errors. For application-defined errors, you can check messages when the message is part of the contract.

### 24.4. Plan mismatch

If a plan declares 10 tests but only 9 execute, inspect `IF`/`CASE` branches, skip counts, and test loops. Plan mismatches are test harness errors to fix, never ignore.

### 24.5. TODO and SKIP

`pgTAP` has `todo()`/`skip()` for intentional cases. Use them with deadlines and specific reasons. Never turn a regression into an indefinite `TODO` to keep CI artificially green.

## 25. Organizing Test Files and CI

A simple structure:

```text
project/
├── migrations/
├── tests/
│   ├── functions/
│   │   ├── calculate_discount.sql
│   │   └── open_order_ids.sql
│   ├── procedures/
│   │   └── mark_order_reviewed.sql
│   ├── triggers/
│   │   └── orders_status_audit.sql
│   ├── security/
│   │   └── routine_privileges.sql
│   └── integration/
│       └── transaction_boundaries.sql
└── scripts/
    └── create_test_database.sql
```

### 25.1. Running a pgTAP suite

Example:

```bash
pg_prove -d app_test -U test_runner tests/functions/*.sql tests/procedures/*.sql tests/triggers/*.sql
```

You can run an entire directory:

```bash
pg_prove -d app_test -U test_runner tests/
```

Glob/path syntax depends on the shell and `pg_prove` version; verify in the CI image.

### 25.2. Verbose output

When debugging:

```bash
pg_prove --verbose -d app_test -U test_runner tests/
```

Verbose mode helps pinpoint failing assertions and the corresponding files.

### 25.3. psql script runner

For plain SQL scripts:

```bash
psql -X -v ON_ERROR_STOP=1 -d app_test -f tests/routines.sql
```

Do not let CI check only the exit code of a shell pipeline while accidentally ignoring `psql`'s exit code. Configure the pipeline to fail whenever the test process fails.

### 25.4. CI sequence

A typical pipeline includes:

1. Provision a PostgreSQL test instance.
2. Install required extension packages.
3. Create the test database and roles.
4. Apply migrations.
5. Create the `pgTAP` extension.
6. Run catalog/behavior tests.
7. Run security tests as runtime roles.
8. Run integration/concurrency tests.
9. Export a TAP/JUnit-compatible report if tooling supports it.
10. Destroy the ephemeral database.

### 25.5. Parallel test execution

Do not run two test suites in parallel against the same fixed fixtures if both modify the same rows/tables. Use a separate database/schema per worker or non-overlapping fixture IDs.

### 25.6. CI credentials

Use a secret manager/environment variables. Never commit database passwords into test SQL files or command lines where they can leak into process listings/logs. The test runner role should hold only the privileges needed in the test database.

## 26. Limitations to Understand

### 26.1. pgTAP does not replace an external test runner

`pgTAP` assertions run inside PostgreSQL, but provisioning, package installation, environment orchestration, and CI lifecycle still require external tooling.

### 26.2. Transaction rollback does not undo external side effects

If a routine sends an HTTP request, email, or broker message, database `ROLLBACK` does not retract that side effect. Use mock adapters, test endpoints, transactional outboxes, or isolated external services.

### 26.3. Superuser tests can hide security bugs

Superusers bypass RLS and privilege checks. Run permission tests using runtime roles.

### 26.4. Trigger functions cannot be fully tested by direct invocation

Trigger context includes `NEW`, `OLD`, `TG_OP`, `TG_WHEN`, `TG_LEVEL`, and transition relations. Test with actual `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE` so PostgreSQL fires the trigger.

### 26.5. Schema metadata tests do not prove behavior

`has_function()` or `trigger_is()` only verify object existence/wiring. Behavioral tests are still required for outputs and side effects.

### 26.6. Local tests do not prove all PostgreSQL versions behave identically

If your module supports multiple major versions, run a compatibility matrix. Some catalog fields, syntax, and `pgTAP` assertions can differ by version.

### 26.7. Performance tests can be flaky

Timings depend on shared resources, cache, background work, and data distribution. Use a dedicated benchmark environment for strict performance gates.

## 27. Common Errors

| Symptom/assumption | Cause | Resolution |
| --- | --- | --- |
| plan mismatch | Wrong assertion count or unexecuted test branch | Update plan and check conditional branches |
| pgTAP function does not exist | Extension not installed in database or wrong schema | Check `pg_extension`/`search_path` |
| CREATE EXTENSION pgtap fails | Package/control files missing on server | Install package matching PostgreSQL major version |
| Test function passes but app fails | Test ran as owner/superuser | Run as runtime role and check grants/RLS |
| Trigger exists but writes no audit row | Wrong event/timing/WHEN or trigger disabled | Test actual DML and inspect trigger definition |
| Trigger test passes falsely | Assertion counts all audit rows without filtering by fixture key | Assert using fixture primary key |
| Procedure CALL fails in test | Procedure executes COMMIT inside a transaction wrapper | Test at top level in a dedicated integration script |
| Test depends on row order | Query lacks ORDER BY | Use `set_eq` or `ORDER BY` |
| NULL assertion gives unclear result | Boolean comparison returning NULL | Use `is(value, NULL::type)` or `IS NULL` |
| Exception test is flaky | Comparing localized/versioned message text | Prefer `SQLSTATE` |
| Sequence ID differs from expected | Sequence state does not roll back like table data | Use explicit IDs or `RETURNING` |
| CI tests collide | Shared fixture IDs/database | Separate database/schema or unique IDs |
| Tests run slowly | Small dev dataset vs. large CI dataset or missing indexes | Standardize fixtures and workload |
| RLS test sees all rows | Running as superuser/table owner | Use runtime role that does not bypass RLS |
| Function security test is wrong | Checked only body without checking owner/ACL/search_path | Test execution context and catalog metadata |
| SQL script reports pass and CI stays green on error | Runner lacks ON_ERROR_STOP or ignores exit code | Use `psql -v ON_ERROR_STOP=1` and fail pipeline |

## 28. Building a Test Suite from Scratch

**Step 1 — List routines and triggers.** Record function/procedure signatures, return types, owners, security modes, trigger events, and expected side effects.

**Step 2 — Write the contract.** For each object, define inputs, outputs, `SQLSTATE`, invariants, permissions, and performance expectations.

**Step 3 — Create the test database.** Use a compatible PostgreSQL version, install extensions, and create roles matching production where needed.

**Step 4 — Create fixtures.** Keep data small, deterministic, with explicit keys and no external state dependencies.

**Step 5 — Write behavioral tests.** Test happy paths, boundaries, `NULL`, exceptions, modified rows, and side effects.

**Step 6 — Write trigger tests.** Verify catalog wiring, events, timing, row/statement level, `WHEN` conditions, and rollback atomicity.

**Step 7 — Write security tests.** Run as runtime roles, verifying `EXECUTE`, RLS, `SECURITY DEFINER`, and `search_path`.

**Step 8 — Write schema contract tests.** Verify signatures, return types, volatility, trigger functions, and object counts.

**Step 9 — Run across migrations.** Test both an empty database and upgrading from a prior version.

**Step 10 — Integrate into CI.** Run `pg_prove`/`psql` fail-fast, save outputs, and classify failures.

**Step 11 — Add concurrency/performance.** Add tests needing multiple sessions or large datasets to the appropriate suites.

**Step 12 — Maintain tests alongside code.** Whenever a contract changes, update the routine, migration, and tests in the same change set.

## 29. Hands-On Exercises

Perform these in a dedicated lab database. Never run test data mutations, trigger side effects, or privilege experiments in production.

### Exercise 1 — Install pgTAP

Install the `pgTAP` package compatible with your PostgreSQL server, run `CREATE EXTENSION` in the lab database, and verify via `pg_extension`.

### Exercise 2 — TAP plan

Write a test file with `plan(3)`, three assertions, and `finish()`. Run it with `pg_prove` and inspect the output.

### Exercise 3 — Basic assertions

Use `ok()`, `is()`, `isnt()`, and `cmp_ok()` to verify results of a simple function.

### Exercise 4 — Function existence

Use `has_function()` with schema, name, and argument types. Create an overload to prove signatures matter.

### Exercise 5 — Return types

Use `function_returns()` to verify a scalar function and a set-returning function.

### Exercise 6 — Language and volatility

Use `function_lang_is()` and `volatility_is()` to verify a function's contract.

### Exercise 7 — STRICT/NULL

Create a `STRICT` function and a non-`STRICT` function. Test `NULL` inputs and document the semantics.

### Exercise 8 — Boundary values

Write tests for a numeric function at zero, negative values, thresholds, maximums, and rounding boundaries.

### Exercise 9 — Exception SQLSTATE

Create a function that raises an exception with a custom `SQLSTATE`. Use `throws_ok()` to verify the code/message.

### Exercise 10 — Exception localization

Try checking the error message of a PostgreSQL core error. Switch to asserting `SQLSTATE` to avoid locale dependence.

### Exercise 11 — Set-returning function

Create a function returning multiple rows. Use `results_eq()` to verify values and ordering.

### Exercise 12 — Set equality

Write a query without `ORDER BY` and use `set_eq()` to compare results regardless of order.

### Exercise 13 — Empty results

Use `is_empty()` and `isnt_empty()` to test queries with and without rows.

### Exercise 14 — Procedure kind

Create a procedure and use `is_procedure()` together with `function_returns(..., 'void')` to verify metadata.

### Exercise 15 — Procedure side effects

Invoke a procedure with `lives_ok()`, then inspect table state with `is()`/`results_eq()`.

### Exercise 16 — Procedure error path

Create a procedure that raises an exception when a row does not exist. Test `SQLSTATE` and confirm no data was modified.

### Exercise 17 — OUT/INOUT

Create a procedure with `OUT` or `INOUT` parameters. Invoke it with `CALL` in PL/pgSQL/client and verify outputs.

### Exercise 18 — Transaction-control procedure

Create a procedure containing `COMMIT` in the lab. Demonstrate that it cannot run inside a transaction wrapper and write a top-level integration test.

### Exercise 19 — Trigger exists

Use `has_trigger()` to verify a trigger is attached to a table.

### Exercise 20 — Trigger wiring

Use `trigger_is()` to verify the trigger invokes the right trigger function.

### Exercise 21 — Trigger set

Use `triggers_are()` to check the expected trigger list and try adding an extra trigger to observe diagnostics.

### Exercise 22 — AFTER UPDATE audit

Create a trigger auditing `OLD`/`NEW` status. Update a row and verify the exact audit record.

### Exercise 23 — WHEN condition

Create a trigger that fires only when `OLD`/`NEW` differ. Update with the same value and confirm no new audit event is created.

### Exercise 24 — UPDATE OF column

Create an `UPDATE OF status` trigger. Update another column and confirm the trigger writes no event.

### Exercise 25 — BEFORE trigger

Create a trigger normalizing text. Insert/update through the table and verify the stored value after the trigger runs.

### Exercise 26 — DELETE trigger

Create an audit trigger using `OLD`. Delete a row and verify the before-image is saved.

### Exercise 27 — Statement-level trigger

Create a statement-level trigger and run DML affecting zero, one, and multiple rows. Compare trigger invocation counts against the expected contract.

### Exercise 28 — Multi-row trigger

Create a row-level trigger, update 100 rows, and verify exactly 100 audit events are written.

### Exercise 29 — Trigger rollback

Update a source row and then `ROLLBACK`. Confirm both the source change and the audit row are rolled back.

### Exercise 30 — Trigger exception

Create a trigger that can raise an exception. Confirm DML fails and leaves no partial database state.

### Exercise 31 — SECURITY DEFINER

Create a `SECURITY DEFINER` function owned by a `NOLOGIN` role. Use `is_definer()` and invoke it as the runtime role.

### Exercise 32 — Privilege test

Use `has_function_privilege()` to verify allowed and denied `EXECUTE` roles. Run tests using the respective connection roles.

### Exercise 33 — RLS

Create an RLS-enabled table and role-based policies. Test `SELECT`/`UPDATE` as the runtime role, not as superuser.

### Exercise 34 — SQL-only harness

Write `pg_temp.assert_true()`, run tests via `psql` with `ON_ERROR_STOP`, and roll back fixtures.

### Exercise 35 — CI suite

Create a pipeline that provisions a database, applies migrations, installs `pgTAP`, runs `pg_prove`, saves TAP output, and fails the job when an assertion fails.

## 30. Summary

Core takeaways for **testing functions, procedures, and triggers with pgTAP or SQL scripts**:

1. Functions, procedures, and triggers have different invocation models and side effects; pick the right testing approach.
2. `pgTAP` provides assertions and TAP output; `pg_prove` runs multiple SQL test files in CI.
3. `plan()`/`finish()` track assertion counts and confirm the suite completed.
4. `has_function()`, `function_returns()`, `function_lang_is()`, `volatility_is()`, and `is_definer()` verify function/procedure contracts.
5. `throws_ok()` verifies exceptions by `SQLSTATE`; `lives_ok()` only confirms the statement did not error.
6. `results_eq()`, `set_eq()`, and `is_empty()` verify query results.
7. `has_trigger()`, `trigger_is()`, and `triggers_are()` verify trigger existence/wiring; real DML proves behavior.
8. Procedure side effects must be verified after `CALL`; transaction-control procedures require separate top-level integration tests.
9. Deterministic fixtures, transaction rollbacks, and dedicated test databases keep suites repeatable.
10. Security tests must use runtime roles to verify `EXECUTE`, `SECURITY DEFINER`, and RLS.
11. Concurrency, performance, and external side effects require dedicated test strategies.
12. Plain SQL scripts can use a `pg_temp` assertion helper and `psql` `ON_ERROR_STOP` when `pgTAP` cannot be installed.
13. CI must run migrations before tests, save diagnostics, and exit non-zero when assertions fail.
14. Metadata tests do not replace behavioral tests; calling a function directly does not replace trigger integration tests.
15. A strong suite protects outputs, data invariants, privileges, trigger side effects, and migration compatibility.

When testing logic inside PostgreSQL, treat each routine as an API with an explicit contract: which callers are permitted, which inputs are valid, which outputs/side effects are produced, and which errors must be raised. `pgTAP` expresses that contract as assertions with diagnostics; plain SQL scripts offer a lighter alternative in constrained environments. Combining both with reproducible fixtures, runtime roles, and migration tests catches bugs before routines touch production data.

## 31. References

- [pgTAP Documentation](https://pgtap.org/documentation.html) — installation, TAP plans, assertions, query tests, schema tests, and function/trigger assertions.
- [pgTAP on PGXN](https://pgxn.org/dist/pgtap/) — package, releases, and distribution docs.
- [Supabase: pgTAP Unit Testing](https://supabase.com/docs/guides/database/extensions/pgtap) — examples of organizing test functions and query assertions.
- [PostgreSQL: CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html) — function definition, volatility, security mode, and attributes.
- [PostgreSQL: CREATE PROCEDURE](https://www.postgresql.org/docs/current/sql-createprocedure.html) — procedure definition and transaction control.
- [PostgreSQL: CALL](https://www.postgresql.org/docs/current/sql-call.html) — calling procedures and transaction restrictions.
- [PostgreSQL: Trigger Definition](https://www.postgresql.org/docs/current/trigger-definition.html) — trigger events, timing, and execution behavior.
- [PostgreSQL: CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html) — trigger syntax, row/statement level, and `WHEN`.
- [PostgreSQL: PL/pgSQL Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html) — `RAISE`, `SQLSTATE`, and exception handling.
- [PostgreSQL: Transaction Management](https://www.postgresql.org/docs/current/tutorial-transactions.html) — `BEGIN`, `COMMIT`, and `ROLLBACK`.
- [PostgreSQL: Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS behavior and policy evaluation.
- [PostgreSQL: Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html) — `SQLSTATE` catalog.

`/current/` URLs point to the current PostgreSQL documentation. `pgTAP` APIs, extension packaging, and some trigger/procedure features can vary by version. Before standardizing a test suite, verify the PostgreSQL major version, `pgTAP` version, extension installation schema, and command-line runner available in the CI image.
