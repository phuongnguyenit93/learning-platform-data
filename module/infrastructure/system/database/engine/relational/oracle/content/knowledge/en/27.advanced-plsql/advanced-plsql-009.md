# DETERMINISTIC and the Responsibility for Ensuring Determinism

In PL/SQL, the **DETERMINISTIC** keyword is a promise made by the function author to Oracle Database: given the same input values, the function always returns the same result and produces no side effects. Oracle relies on this promise in contexts that optimize or store expression outputs, such as function-based indexes and certain types of materialized views.

Most importantly, Oracle **does not prove that a function is truly deterministic**. When declaring DETERMINISTIC, the developer is responsible for ensuring determinism across all valid invocations. If the function reads time-varying state, depends on session settings, queries mutable tables, or creates side effects, the promise can be broken. When that happens, query results or values stored in an index may no longer reflect current logic.

Example function computing a fee from two parameters:

~~~sql
CREATE OR REPLACE FUNCTION calculate_fee (
    p_amount IN NUMBER,
    p_rate   IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN ROUND(p_amount * p_rate, 2);
END calculate_fee;
/
~~~

The output depends solely on `P_AMOUNT` and `P_RATE`. Given the same two input values, the function returns the same result and modifies no external state, so declaring `DETERMINISTIC` is appropriate.

Conversely, a function using `SYSDATE`, `DBMS_RANDOM`, sequence `NEXTVAL`, mutable package variables, session context, or updatable configuration tables should not be declared `DETERMINISTIC` unless those factors are fully represented in the inputs.

This lesson presents the meaning of `DETERMINISTIC`, the boundary between determinism and environmental state, function declaration syntax, usage with function-based indexes, risks of stale index data when changing a function, differences from `RESULT_CACHE`, and how to verify the promise.

## 1. What Is a Deterministic Function?

A deterministic function must satisfy two core requirements:

1. **Same inputs, same output**: if the function is called with the same parameter values, the returned result must be identical.
2. **No side effects**: invoking the function must not alter external state in a way that affects subsequent calls or modifies business data.

Determinism must be evaluated across the entire execution context, not just the declared parameter list. If a function quietly reads system time, package variables, configuration tables, NLS settings, or session context, those values affect the outcome even though they do not appear in the parameter list.

### 1.1. Purely Input-Driven Functions

Example:

~~~sql
CREATE OR REPLACE FUNCTION normalize_amount (
    p_amount IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN ROUND(p_amount, 2);
END normalize_amount;
/
~~~

For the same `P_AMOUNT`, `ROUND` produces the same result. The function reads no tables, reads no session variables, and writes no data.

Another example:

~~~sql
CREATE OR REPLACE FUNCTION amount_bucket (
    p_amount IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN TRUNC(p_amount / 1000);
END amount_bucket;
/
~~~

If 2500 is passed, the result is always 2. If 3999 is passed, the result is always 3. The logic depends purely on the input NUMBER value.

### 1.2. DETERMINISTIC Does Not Ask Oracle to Auto-Verify

The declaration:

~~~sql
RETURN NUMBER DETERMINISTIC
~~~

is a developer assertion. Oracle does not analyze the entire function body to prove that every branch returns the same result for identical inputs.

A function can compile even if the author declared `DETERMINISTIC` while the body reads `SYSDATE` or a mutable table. Successful compilation does not prove the promise holds.

If misdeclared, Oracle may apply assumptions that no longer hold. Results can become non-deterministic or inconsistent; function-based indexes and dependent objects may store values that do not reflect current logic.

### 1.3. Determinism Does Not Mean One-Time Execution

`DETERMINISTIC` is not a guarantee that:
- Oracle will invoke the function exactly once.
- Oracle will always cache the result.
- Each parameter set is evaluated only once within a SELECT statement.
- Two different SQL statements will definitely share results.
- The function will run faster in every situation.

Oracle may leverage the declaration to choose execution optimizations, yet the actual invocation count is not an application contract. Never write business logic depending on how many times a function executes.

## 2. Syntax for Declaring DETERMINISTIC

`DETERMINISTIC` is declared in the function heading, after the return type.

### 2.1. Standalone Function

~~~sql
CREATE OR REPLACE FUNCTION calculate_fee (
    p_amount IN NUMBER,
    p_rate   IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN ROUND(p_amount * p_rate, 2);
END calculate_fee;
/
~~~

Callers can use the function in PL/SQL:

~~~sql
DECLARE
    l_fee NUMBER;
BEGIN
    l_fee := calculate_fee(100000, 0.05);
    DBMS_OUTPUT.PUT_LINE(l_fee);
END;
/
~~~

And in SQL when the function meets SQL-invocable function rules:

~~~sql
SELECT calculate_fee(100000, 0.05) AS fee
FROM dual;
~~~

### 2.2. Function in a Package

You can publish a deterministic function in a package specification:

~~~sql
CREATE OR REPLACE PACKAGE pricing_api AS
    FUNCTION calculate_fee (
        p_amount IN NUMBER,
        p_rate   IN NUMBER
    ) RETURN NUMBER DETERMINISTIC;
END pricing_api;
/
~~~

Package body implementation:

~~~sql
CREATE OR REPLACE PACKAGE BODY pricing_api AS

    FUNCTION calculate_fee (
        p_amount IN NUMBER,
        p_rate   IN NUMBER
    ) RETURN NUMBER DETERMINISTIC
    IS
    BEGIN
        RETURN ROUND(p_amount * p_rate, 2);
    END calculate_fee;

END pricing_api;
/
~~~

`DETERMINISTIC` must be declared consistently in the function declaration. When the function is part of a package's public API, callers and Oracle must see this attribute via the package specification.

### 2.3. DETERMINISTIC Is Only for Functions

`DETERMINISTIC` is a function property, not a procedure property. Procedures do not return a value under the same model for Oracle to treat as a deterministic expression.

Do not use this keyword to describe a side-effect-free procedure. Ensuring a procedural operation does not mutate state is a different design contract.

### 2.4. Modifying the Function Body Does Not Automatically Re-Verify Determinism

When editing a function, the maintainer must re-evaluate:
- Does output still depend solely on parameters?
- Were calls to non-deterministic functions added?
- Were table queries or session-state reads added?
- Were new side effects introduced?
- Are there dependent function-based indexes, materialized views, or other objects?

Leaving the `DETERMINISTIC` keyword intact while editing code does not mean the function still honors its promise.

## 3. Dependency Sources That Break Determinism

The most useful question when reviewing a function is: **If called again with the same parameters, could anything outside the function have changed and altered the result?**

If the answer is yes, the function cannot yet be considered deterministic unless that state is fixed or fully passed in as input.

### 3.1. System Time

The following function is not deterministic:

~~~sql
CREATE OR REPLACE FUNCTION current_year
RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN EXTRACT(YEAR FROM SYSDATE);
END current_year;
/
~~~

Calling it with no parameters can return different values when the calendar year changes. `SYSDATE` is temporal state external to the inputs.

If business logic needs the year of a caller-supplied date, pass the date as a parameter:

~~~sql
CREATE OR REPLACE FUNCTION year_of_date (
    p_date IN DATE
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN EXTRACT(YEAR FROM p_date);
END year_of_date;
/
~~~

For the same `P_DATE`, the resulting year does not depend on the server's current date.

### 3.2. Random Numbers

Functions using `DBMS_RANDOM` are not deterministic:

~~~sql
CREATE OR REPLACE FUNCTION random_token
RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN DBMS_RANDOM.VALUE;
END random_token;
/
~~~

With the same empty parameter list, each call can yield a different value. Never declare `DETERMINISTIC` on functions generating random numbers, random tokens, or results depending on random seeds/session state.

### 3.3. Sequences

Functions reading sequence `NEXTVAL` are not deterministic:

~~~sql
CREATE OR REPLACE FUNCTION next_business_id
RETURN NUMBER DETERMINISTIC
IS
    l_id NUMBER;
BEGIN
    SELECT business_seq.NEXTVAL
    INTO l_id
    FROM dual;

    RETURN l_id;
END next_business_id;
/
~~~

Each call retrieves a new sequence value. The function also has a database-level side effect because `NEXTVAL` advances the sequence.

Never use a deterministic function to generate unique IDs. Use sequences directly or an appropriate key-generation mechanism.

### 3.4. Package Variables and Global State

~~~sql
CREATE OR REPLACE PACKAGE runtime_state AS
    g_multiplier NUMBER := 1;
END runtime_state;
/
~~~

~~~sql
CREATE OR REPLACE FUNCTION multiply_by_runtime_setting (
    p_value IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN p_value * runtime_state.g_multiplier;
END multiply_by_runtime_setting;
/
~~~

If `G_MULTIPLIER` changes in the session or package state is re-initialized, the same `P_VALUE` can produce different results. Visible function parameters do not represent all data determining the output.

If the factor is part of the calculation, pass it as a parameter:

~~~sql
CREATE OR REPLACE FUNCTION multiply_value (
    p_value      IN NUMBER,
    p_multiplier IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN p_value * p_multiplier;
END multiply_value;
/
~~~

### 3.5. Session Context and Current User

Values like `USER`, `SYS_CONTEXT`, client identifier, application context, or session metadata can differ across sessions. If a function uses them to compute output, identical explicit parameters may not produce identical results.

Example:

~~~sql
CREATE OR REPLACE FUNCTION current_user_label (
    p_suffix IN VARCHAR2
) RETURN VARCHAR2 DETERMINISTIC
IS
BEGIN
    RETURN SYS_CONTEXT('USERENV', 'SESSION_USER') || p_suffix;
END current_user_label;
/
~~~

Two different sessions can get different results for the same `P_SUFFIX`. This function should not be declared deterministic.

If output must depend on user identity, pass an explicit user identifier into the function only when the calculation is genuinely pure over that identifier; if current privileges must be checked, perform authorization checks in the appropriate layer instead of turning a session check into a deterministic function.

### 3.6. NLS, Timezone, and Implicit Formatting

A function formatting dates or numbers can depend on NLS settings unless formats and conversion rules are specified explicitly.

For example, `TO_CHAR(date)` without a format model can depend on `NLS_DATE_FORMAT`. Converting a string to a date without an explicit format can depend on the session's `NLS_DATE_FORMAT`.

To reduce hidden dependencies, use:
- Explicit format models.
- Explicit NLS parameters when functions require them.
- `DATE`/`TIMESTAMP` datatypes instead of session-formatted strings.
- Explicit timezone rules when handling timezone-aware timestamps.

However, adding a format model alone is insufficient if the function still reads other session state.

### 3.7. Reading Mutable Tables

A function looking up a discount rate from a table:

~~~sql
CREATE OR REPLACE FUNCTION customer_discount (
    p_customer_id IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
    l_discount NUMBER;
BEGIN
    SELECT discount_rate
    INTO l_discount
    FROM customer_discount_config
    WHERE customer_id = p_customer_id;

    RETURN l_discount;
END customer_discount;
/
~~~

If `CUSTOMER_DISCOUNT_CONFIG` is updated, the same `P_CUSTOMER_ID` can return a different discount rate. The function depends on database state not captured in parameters.

Do not declare such a function deterministic merely because the configuration table changes rarely. "Rarely changes" does not mean "immutable."

If you need current configuration lookups, use SQL directly or consider `RESULT_CACHE` when conditions are met and cache invalidation semantics are acceptable. Never attach `DETERMINISTIC` to hide a table dependency.

### 3.8. Functions Calling Other Functions

A function is deterministic only if its entire call chain honors the same contract. If `FUNCTION_A` calls `FUNCTION_B`, and `B` reads `SYSDATE`, a package variable, or a mutable table, `A` is not deterministic either—even if `A`'s body is a single line `RETURN FUNCTION_B(...)`.

When evaluating, trace the dependency graph:
- Functions called directly.
- Package variables read by called functions.
- SQL statements executed by called functions.
- Built-ins with session or environmental dependencies.
- External procedures/services invoked indirectly.

Do not inspect only the few top-level lines of the outermost function.

## 4. Side Effects and Deterministic Functions

A side effect is a state change outside the return value. A function declared `DETERMINISTIC` must not perform side effects.

Examples of side effects:
- `INSERT`, `UPDATE`, or `DELETE` on business data.
- Modifying package variables or global state.
- Writing files or calling stateful external services.
- Sending notifications.
- Advancing sequences.
- Altering session state.
- Running an autonomous transaction to write logs.

Never declare deterministic on a function that both returns a value and mutates state.

### 4.1. Do Not Use a Deterministic Function for Auditing

A function such as:

~~~sql
CREATE OR REPLACE FUNCTION audit_and_return (
    p_value IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    INSERT INTO audit_log(value_logged)
    VALUES (p_value);

    RETURN p_value;
END audit_and_return;
/
~~~

violates the deterministic contract because it writes data. Even if the return value matches, the side effects across calls do not match a pure computation.

Separate responsibilities:
- The calculation function only returns a result.
- A separate procedure or DML statement handles auditing.
- The caller coordinates transactions and logging.

### 4.2. Do Not Rely on Function Execution Counts

If a function has side effects, Oracle optimizing, eliminating, or reusing a computation can cause program behavior to diverge from expectations. A deterministic function must be independent of how many times it is invoked.

Never use a function inside a SQL expression to send emails, write logs, or increment counters expecting Oracle to call it once per row.

## 5. DETERMINISTIC and Function-Based Indexes

A major use case for deterministic functions is **function-based indexes**. Oracle stores the index expression's computed value for efficient data access. If the expression uses a user-defined function, that function must be declared deterministic and genuinely honor that contract.

Example function normalizing an amount into buckets:

~~~sql
CREATE OR REPLACE FUNCTION amount_bucket (
    p_amount IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN TRUNC(p_amount / 1000);
END amount_bucket;
/
~~~

Create the index:

~~~sql
CREATE INDEX ix_orders_amount_bucket
ON orders (amount_bucket(amount));
~~~

Query using the same expression:

~~~sql
SELECT order_id, amount
FROM orders
WHERE amount_bucket(amount) = 2;
~~~

The optimizer can consider the function-based index when the expression, predicate, statistics, and cost align.

### 5.1. Indexes Store Values Computed at DML Time

When creating a function-based index, Oracle evaluates the expression for existing rows and stores the keys in the index. On `INSERT` or `UPDATE` of the referenced columns, Oracle recomputes the index value for affected rows.

This means the index stores outputs of the function logic used when keys were computed. If the function depends on mutable data outside the row, changing that external data does not automatically cause Oracle to recompute all index keys.

### 5.2. Risk When a Function Is Declared Deterministic but Is Not

Suppose `amount_bucket` does not merely divide `amount`, but also reads a configuration table holding the bucket size. The index was built when bucket size was 1000. Later, the configuration table changes to 500.

Keys stored in the index may still reflect the old logic/config while direct calls to the function return new values. Queries relying on the index risk returning inconsistent data.

This is why `DETERMINISTIC` must never be applied to functions depending on mutable state outside their parameters.

### 5.3. Changing Function Code Requires Reviewing Dependent Indexes

If you modify logic in a function used by a function-based index, stored index values may no longer match the new code. Identify all dependent indexes and objects, then rebuild or refresh them according to object type and deployment procedures.

Example rebuilding an index:

~~~sql
ALTER INDEX ix_orders_amount_bucket REBUILD;
~~~

Do not assume `CREATE OR REPLACE FUNCTION` alone updates all values stored in indexes. Check index status and deployment plans after changing functions.

### 5.4. Predicates Must Match the Index Expression

If an index is created on:

~~~sql
amount_bucket(amount)
~~~

a query using the exact same expression:

~~~sql
WHERE amount_bucket(amount) = :bucket
~~~

gives the optimizer a clear pattern to consider the index.

If the query uses a different formula or wraps it in non-equivalent functions, the index may not be used as expected. Check the execution plan rather than guessing from the function name alone.

### 5.5. Privileges and Dependencies

A function-based index depends on the function and execute privileges on that function. When deploying in real schemas, you must:
- Verify owners of the table, index, and function.
- Grant required privileges per Oracle rules.
- Manage dependencies when the function is modified or invalidated.
- Check index status after compile/recompile.
- Test `INSERT`/`UPDATE` and queries using the expression.

Never treat `DETERMINISTIC` as a privilege or data-protection mechanism.

## 6. DETERMINISTIC and Materialized Views

Some materialized view definitions can reference user-defined functions. Oracle enforces specific rules and restrictions on functions used in materialized views, query rewrite, and refresh. Function determinism is crucial because materialized data is persisted for later reuse.

When a function or dependency changes, review:
- Which refresh methods the materialized view supports.
- Whether a full refresh is required instead of fast refresh.
- Whether query rewrite remains valid.
- Whether materialized data must be recomputed under the new logic.
- Restrictions of your Oracle version and expression types.

Do not infer that adding `DETERMINISTIC` automatically enables fast refresh for every materialized view. Refresh capability depends on MV definitions, expressions, logs, joins, aggregates, and Oracle's specific rules.

### 6.1. Deterministic Does Not Replace Refresh

If a materialized view stores results computed by a function, modifying the function can make materialized results stale. `DETERMINISTIC` does not run refreshes or update old data automatically.

When changing a function:
1. Identify dependent MVs.
2. Check definitions and status.
3. Choose a valid refresh method.
4. Refresh or recreate according to plan.
5. Verify data and query rewrite post-deployment.

## 7. DETERMINISTIC vs. RESULT_CACHE

These two features both relate to reusing results, but they are not synonymous.

### 7.1. DETERMINISTIC

`DETERMINISTIC`:
- Is a developer promise.
- States that identical parameters always return the same result.
- Does not create a managed cache on its own.
- Does not guarantee the function executes only once.
- Is used by Oracle in specific optimizations/contexts requiring deterministic functions.
- Places responsibility on the author if the promise is violated.

### 7.2. RESULT_CACHE

A function can declare `RESULT_CACHE`:

~~~sql
CREATE OR REPLACE FUNCTION get_tax_rate (
    p_region_code IN VARCHAR2
) RETURN NUMBER RESULT_CACHE
IS
    l_rate NUMBER;
BEGIN
    SELECT tax_rate
    INTO l_rate
    FROM tax_region
    WHERE region_code = p_region_code;

    RETURN l_rate;
END get_tax_rate;
/
~~~

`RESULT_CACHE` instructs Oracle to store function results in the result cache keyed by parameters and managed dependencies. Oracle can invalidate cached entries when tables read by the function change, under result cache rules.

This is a genuine caching mechanism, distinct from `DETERMINISTIC`. However, `RESULT_CACHE` also has restrictions and prerequisites; not every function or workload is suitable.

### 7.3. Comparison

| Criterion | DETERMINISTIC | RESULT_CACHE |
| --- | --- | --- |
| Nature | Promise of determinism | Mechanism storing results in result cache |
| Author guarantees same input, same output | Yes | Function still needs compatible semantics |
| Creates an SGA cache automatically | No | Yes |
| Tracks table dependencies for cache invalidation | Not a DETERMINISTIC mechanism | Yes, per result cache rules |
| Used for function-based indexes | Essential declaration for user-defined functions | Does not replace deterministic requirement |
| Guarantees function executes only once | No | No; cache hit/miss and invalidation decide |
| Fully interchangeable | No | No |

### 7.4. Do Not Mark DETERMINISTIC Hoping for Result Caching

If your goal is reusing lookups from a configuration table, `DETERMINISTIC` is not a caching solution. If the function depends on mutable tables, marking it deterministic can cause wrong results wherever Oracle relies on that promise.

Evaluate `RESULT_CACHE` if dependencies and workload fit, or use direct `JOIN`/subqueries so the optimizer manages data inside SQL.

## 8. Turning External State into Parameters

One design pattern to keep a function deterministic is passing every value that determines output as a parameter.

Example function computing a discounted price:

~~~sql
CREATE OR REPLACE FUNCTION discounted_price (
    p_base_price IN NUMBER,
    p_discount_rate IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN ROUND(
        p_base_price * (1 - p_discount_rate),
        2
    );
END discounted_price;
/
~~~

Both base price and discount rate are passed in. Given the same two values, the function yields the same result.

### 8.1. Do Not Let the Function Look Up Current Rates

Another version:

~~~sql
CREATE OR REPLACE FUNCTION discounted_price_current (
    p_product_id IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
    l_price NUMBER;
    l_rate  NUMBER;
BEGIN
    SELECT price, discount_rate
    INTO l_price, l_rate
    FROM product_pricing
    WHERE product_id = p_product_id;

    RETURN ROUND(l_price * (1 - l_rate), 2);
END discounted_price_current;
/
~~~

This function depends on the `PRODUCT_PRICING` table. If price or discount rate changes, the same `PRODUCT_ID` can return a different result. Never declare `DETERMINISTIC` on this function merely because the table updates infrequently.

If a pure function is needed, the caller reads the data and passes both price and rate in. If dynamic lookup is needed, use SQL or a cache with proper invalidation.

### 8.2. Pass Version/Config Keys Only When Versions Are Immutable

You can pass a `CONFIG_VERSION` so the function determines calculation rules. However, this makes sense only if the same version always maps to the exact same configuration content and old versions are never edited.

If an administrator updates data for an existing version, adding version as a parameter still does not guarantee determinism. Determinism must be protected by immutable data rules, such as freezing versions upon release.

## 9. Verifying Determinism

Because Oracle does not prove determinism automatically, the engineering team must verify this contract through design and testing.

### 9.1. Test the Same Inputs Multiple Times

~~~sql
SELECT calculate_fee(100000, 0.05) AS result_1
FROM dual;

SELECT calculate_fee(100000, 0.05) AS result_2
FROM dual;
~~~

Both outputs must match. This is only a basic check; it does not prove independence from session or database state.

### 9.2. Test Across Multiple Sessions

If a function could be affected by:
- `NLS_DATE_FORMAT`.
- `NLS_NUMERIC_CHARACTERS`.
- `SESSIONTIMEZONE`.
- `CURRENT_SCHEMA`.
- Application context.
- User/session identity.

test calling it across sessions with differing configurations. If identical parameters produce different outputs, the function is not deterministic under the declared contract.

### 9.3. Test After Changing Database State

If a function contains any table queries, test:
1. Call the function with a parameter set.
2. Modify the rows the function reads.
3. Call again with the same parameters.
4. Compare outputs.

If output changes, the function depends on table state. Do not declare `DETERMINISTIC`.

### 9.4. Check for Side Effects

Inspect source and dependencies for:
- DML.
- Sequence `NEXTVAL`.
- Assignments to package variables.
- `DBMS_RANDOM`.
- `DBMS_OUTPUT` or loggers with observable side effects.
- External procedures or network calls.
- Autonomous transactions.
- Session state modifications.

A test comparing only return values cannot detect every side effect. Inspect function behavior as well.

### 9.5. Check Recursive Dependencies

If a function calls other packages or functions, inspect those dependencies too. An outer function that looks pure may call a helper reading tables or session state.

Document critical dependencies in code comments so future maintainers understand the scope of the promise.

## 10. Hands-on Examples: Deterministic vs. Non-Deterministic Functions

### 10.1. Deterministic Function

~~~sql
CREATE OR REPLACE FUNCTION tax_amount (
    p_net_amount IN NUMBER,
    p_tax_rate   IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN ROUND(p_net_amount * p_tax_rate, 2);
END tax_amount;
/
~~~

Test:

~~~sql
SELECT tax_amount(1000, 0.1) AS tax
FROM dual;
~~~

The result is always 100 for the same two NUMBER parameters.

### 10.2. Non-Deterministic Function Because of Current Time

~~~sql
CREATE OR REPLACE FUNCTION is_current_year (
    p_year IN NUMBER
) RETURN NUMBER
IS
BEGIN
    IF p_year = EXTRACT(YEAR FROM SYSDATE) THEN
        RETURN 1;
    END IF;

    RETURN 0;
END is_current_year;
/
~~~

The function omits `DETERMINISTIC` because the result for the same `P_YEAR` can change when the current year changes.

If a pure function is desired, pass the comparison year as well:

~~~sql
CREATE OR REPLACE FUNCTION is_year_equal (
    p_year_a IN NUMBER,
    p_year_b IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    IF p_year_a = p_year_b THEN
        RETURN 1;
    END IF;

    RETURN 0;
END is_year_equal;
/
~~~

### 10.3. Function-Based Index with a Deterministic Function

Create a sandbox table:

~~~sql
CREATE TABLE deterministic_demo (
    item_id NUMBER PRIMARY KEY,
    amount  NUMBER NOT NULL
);
~~~

Insert data:

~~~sql
INSERT INTO deterministic_demo VALUES (1, 1200);
INSERT INTO deterministic_demo VALUES (2, 2400);
INSERT INTO deterministic_demo VALUES (3, 3900);
COMMIT;
~~~

Create the function:

~~~sql
CREATE OR REPLACE FUNCTION demo_amount_bucket (
    p_amount IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN TRUNC(p_amount / 1000);
END demo_amount_bucket;
/
~~~

Create the index:

~~~sql
CREATE INDEX ix_deterministic_demo_bucket
ON deterministic_demo (demo_amount_bucket(amount));
~~~

Query:

~~~sql
SELECT item_id, amount
FROM deterministic_demo
WHERE demo_amount_bucket(amount) = 2;
~~~

The optimizer can consider this function-based index. A tiny table may cause the optimizer to pick a full table scan due to lower cost; that is not proof the function-based index does not work.

### 10.4. Testing a Function Change

If you change `DEMO_AMOUNT_BUCKET` from dividing by 1000 to dividing by 500, values stored in the function-based index may no longer match the new logic. Rebuild the index:

~~~sql
ALTER INDEX ix_deterministic_demo_bucket REBUILD;
~~~

In real systems, before changing a function, list dependencies and plan rebuilds/refreshes for all related objects.

### 10.5. Clean Up Sandbox

~~~sql
DROP INDEX ix_deterministic_demo_bucket;
DROP FUNCTION demo_amount_bucket;
DROP TABLE deterministic_demo PURGE;
~~~

Drop the lesson's sandbox objects only when you are certain the data is no longer needed. `DROP` is DDL and issues an implicit commit; perform cleanup separately.

## 11. DETERMINISTIC in Application Design

A well-designed deterministic function typically has these traits:
- Parameters fully describe all data determining the result.
- Does not read session state or current time.
- Does not query mutable tables.
- Does not mutate package/global state.
- Does not write to the database or trigger external side effects.
- Called helper functions honor the same contract.
- Calculation rules remain stable across releases or have a defined process for updating dependent objects.

### 11.1. Use for Pure Data Transformations

Common suitable use cases:
- Rounding numbers according to a fixed rule.
- Unit conversions with an explicit conversion factor passed in.
- Computing buckets from an input value.
- Normalizing strings via a fixed, session-independent rule.
- Computing checksums/hashes from inputs with a fixed algorithm and no hidden random salt.
- Computing outputs from a complete, immutable set of parameters.

### 11.2. Do Not Use for Current-State Lookups

Common unsuitable use cases:
- Fetching current exchange rates from a table.
- Fetching active tax rates from a configuration table.
- Checking account status.
- Fetching current user privileges.
- Determining the current date or remaining time.
- Generating random codes or IDs.
- Writing audit logs or sending notifications.

These operations depend on mutable state or create side effects. Use SQL, procedures, or result caching with appropriate semantics instead.

### 11.3. Do Not Confuse Immutable Data with Infrequently Changing Data

A configuration table updated only once a month is still mutable. If a function depends on that table, identical parameters can return different results at two points in time.

Only when data is guaranteed immutable across the entire lifecycle of the function, with no hidden dependencies, can it be treated as a fixed part of the contract. In many cases, passing the value explicitly as a parameter is far easier to control.

## 12. DETERMINISTIC and Business Rule Versioning

A deterministic function can be used in indexes or materialized data. Hence, editing function logic is not just a PL/SQL code change; it can alter the meaning of precomputed data.

Example order classification function:

~~~sql
CREATE OR REPLACE FUNCTION order_priority (
    p_amount IN NUMBER
) RETURN VARCHAR2 DETERMINISTIC
IS
BEGIN
    IF p_amount >= 10000000 THEN
        RETURN 'HIGH';
    ELSIF p_amount >= 1000000 THEN
        RETURN 'MEDIUM';
    ELSE
        RETURN 'LOW';
    END IF;
END order_priority;
/
~~~

If a new policy raises the HIGH threshold to 20,000,000, results already computed and stored in a function-based index may no longer match. During deployment:
1. Identify dependent indexes, MVs, views, or code.
2. Agree on the cutover timing for the logic change.
3. Update the function.
4. Rebuild/refresh objects storing precomputed results as needed.
5. Verify query plans and outputs.
6. Monitor compilation errors and object validity.

Never leave new code running alongside stale index data in an uncontrolled window.

### 12.1. Versioning Calculation Rules

If multiple versions of a rule must coexist, pass the version as an input:

~~~sql
CREATE OR REPLACE FUNCTION priority_for_version (
    p_amount IN NUMBER,
    p_rule_version IN PLS_INTEGER
) RETURN VARCHAR2 DETERMINISTIC
IS
BEGIN
    IF p_rule_version = 1 THEN
        IF p_amount >= 10000000 THEN
            RETURN 'HIGH';
        END IF;
    ELSIF p_rule_version = 2 THEN
        IF p_amount >= 20000000 THEN
            RETURN 'HIGH';
        END IF;
    ELSE
        RETURN 'UNKNOWN';
    END IF;

    RETURN 'NORMAL';
END priority_for_version;
/
~~~

Identical `P_AMOUNT` and `P_RULE_VERSION` yield the same result, provided function logic and dependencies do not change. When policies evolve, adding a new version instead of altering an old version's meaning helps keep historical outputs stable.

Versioning alone does not make a function deterministic if it still reads mutable state or causes side effects.

## 13. Common Errors and Risks

| Issue | Cause | Resolution |
| --- | --- | --- |
| Marking a function reading SYSDATE as deterministic | Output depends on invocation time | Pass date as a parameter or remove DETERMINISTIC |
| Reading a config table inside a deterministic function | Table data can change | Use direct SQL or a cache with invalidation |
| Using package variables | Output depends on session/package state | Pass value as a parameter |
| Using DBMS_RANDOM | Same input can yield different outputs | Do not declare deterministic |
| Using sequence NEXTVAL | Value changes and sequence has a side effect | Use the sequence directly |
| Using SYS_CONTEXT/USER | Output depends on session/user | Omit deterministic or pass explicit context if appropriate |
| Writing logs inside function | Has side effects | Separate logging from the function |
| Editing body of an indexed function | Old index values may become wrong | Rebuild index and refresh dependent objects |
| Confusing DETERMINISTIC with RESULT_CACHE | Assuming declaration creates a cache | Use RESULT_CACHE when appropriate |
| Assuming Oracle auto-verifies | Successful compilation mistaken for verification | Review dependencies and test contract |
| Function calls a non-deterministic helper | Indirect dependency alters results | Inspect entire call graph |
| Hidden NLS/timezone dependency | Same input across sessions yields different results | Specify format/NLS/timezone explicitly or omit DETERMINISTIC |

## 14. Decision Process Before Declaring DETERMINISTIC

Before adding the keyword, answer each question in order:

1. Does the function return the exact same value for identical parameters?
2. Do any package, global, or session-state variables affect the result?
3. Does the function read `SYSDATE`, `SYSTIMESTAMP`, `DBMS_RANDOM`, or sequences?
4. Does the function read any mutable table?
5. Does the function use `USER`, `SYS_CONTEXT`, NLS, or current timezone?
6. Does the function call other functions? Are all those dependencies deterministic?
7. Does the function perform DML, logging, session changes, or external service calls?
8. If configuration data changes, could identical parameters return a different result?
9. Is the function used in a function-based index, materialized view, or object storing precomputed results?
10. If function logic changes, what is the rebuild/refresh plan for dependencies?
11. Is `RESULT_CACHE` needed instead of `DETERMINISTIC`?
12. Can hidden state be converted into explicit parameters?

If you cannot guarantee identical output for identical inputs with zero side effects, do not declare `DETERMINISTIC`.

## 15. Common Misconceptions

**DETERMINISTIC makes Oracle verify the function automatically.** False. It is a developer promise; Oracle does not prove the entire function logic.

**DETERMINISTIC automatically caches results.** False. It is not a caching mechanism like `RESULT_CACHE` and does not guarantee how many times the function is invoked.

**A function reading a config table is still deterministic if the table rarely changes.** False. Mutable data can still change; low frequency does not make it immutable.

**Identical parameters mean identical results even across different sessions.** False if the function depends on NLS, timezone, user, application context, or session state.

**A function using SYSDATE can be deterministic if it only returns the year.** False. The current year changes over time; identical inputs can still yield different outputs.

**A function using DBMS_RANDOM can be deterministic if the seed is usually the same.** Never rely on seed/session state; random outputs violate the same-input, same-output contract.

**DETERMINISTIC is purely a performance hint.** False. It is a semantic contract affecting correctness whenever Oracle uses the function in objects or optimizations built on that promise.

**Function-based indexes auto-update every row when the function body changes.** False. Stored keys may require rebuilding; inspect dependent objects.

**Adding DETERMINISTIC automatically enables fast refresh for materialized views.** False. MVs have many other requirements and restrictions; determinism does not guarantee fast refresh.

**RESULT_CACHE and DETERMINISTIC are interchangeable.** False. One is a determinism promise; the other is a caching mechanism with dependency invalidation.

**A function with no DML is definitely deterministic.** False. It can still read time, random numbers, session context, package state, or mutable tables.

**A function calling just one helper function is definitely deterministic.** False. You must examine all dependencies of the called function.

**Changing a business threshold inside a function does not affect existing indexes.** False. Precomputed index values can reflect old logic; dependent objects must be rebuilt/refreshed.

## 16. Practice Exercises

1. Write a function taking two NUMBERs and returning their sum. Explain why it can be declared `DETERMINISTIC`.
2. Write a function computing a fee from a passed amount and rate.
3. Write a function using `SYSDATE` and explain why it is not deterministic.
4. Modify the function in exercise 3 so the current date becomes a parameter.
5. Write a function using `DBMS_RANDOM` and identify what contract violation occurs.
6. Why is a function reading sequence `NEXTVAL` not deterministic?
7. Write a function reading a package variable. Analyze outputs when the variable changes.
8. Write a function reading a discount configuration table and explain why it should not be declared `DETERMINISTIC`.
9. Analyze how `SYS_CONTEXT` affects determinism.
10. Why can `NLS_DATE_FORMAT` be a hidden dependency?
11. Create a standalone function with `DETERMINISTIC` after the return type.
12. Create a package specification declaring a deterministic function and implement it in the body.
13. Explain why Oracle does not prove the deterministic promise.
14. Create a function-based index on a pure function computing buckets from `AMOUNT`.
15. Write a query using the same expression so the optimizer can consider the index.
16. Explain why a configuration table change can make a function-based index stale.
17. Modify a function used in a function-based index. List the required deployment steps.
18. Distinguish `DETERMINISTIC` from `RESULT_CACHE`.
19. A `RESULT_CACHE` function reads a configuration table. How does dependency-managed caching differ from `DETERMINISTIC`?
20. Why doesn't `DETERMINISTIC` guarantee a function runs only once per input value?
21. A function has no DML but calls a helper reading `SYSDATE`. Is the outer function deterministic?
22. Design a data-normalization function independent of session NLS.
23. Design an order-priority function taking rule version as a parameter.
24. Why isn't versioning sufficient if an old version's data can still be edited?
25. Write a dependency checklist to verify before declaring `DETERMINISTIC`.
26. Give an example of a side effect prohibited in a deterministic function.
27. Analyze how changing a function affects dependent materialized views.
28. Design a release procedure when changing a function used in a function-based index.
29. Write a test calling identical inputs in two sessions with different NLS/timezone settings.
30. An exchange-rate lookup function needs optimization. Why shouldn't it be marked `DETERMINISTIC`, and what are the alternatives?

**DETERMINISTIC is a promise that identical inputs always yield identical outputs and the function has no side effects.** Oracle relies on that promise in specific optimizations and objects storing precomputed values, without verifying correctness automatically. Inspect all direct and indirect dependencies, pass determining state as parameters when appropriate, distinguish `DETERMINISTIC` from `RESULT_CACHE`, and rebuild/refresh dependent objects whenever function logic changes.
