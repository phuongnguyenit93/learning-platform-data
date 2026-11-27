# Function Call Cost, Side-Effect Boundaries, and Criteria for Placing Logic in the Database

In PostgreSQL, **functions** and **procedures** bring business logic closer to data: computing values, normalizing records, executing multiple SQL statements, guarding updates, or providing a shared SQL interface. However, moving logic into the database **does not automatically make an application faster, safer, or easier to maintain**. That outcome depends on call frequency, implementation language, planner optimization opportunities, transaction semantics, side effects, privileges, and how new versions are deployed.

Consider two ways to count paid orders for 1,000 customers:

- Approach A: run `paid_order_count(customer_id)` once per customer row. If the function runs a `SELECT COUNT(*)` internally, the system may have to execute many internal queries.
- Approach B: use a **single set-based SQL query** with `JOIN`, `GROUP BY`, or an appropriate aggregate so the planner sees the entire problem and can optimize differently.

Both can return the exact same result, yet **their cost diverges sharply as row counts grow**. Conversely, a small SQL function eligible for **inlining** may introduce almost no meaningful optimization boundary. Therefore, the real question is not "are PostgreSQL functions slow?", but rather **where is the function called, how many times is it invoked, how much work does it do internally, and how much of that logic can the planner see?**

This lesson belongs to the **Functions and Procedures** chapter of the *Database Engine Relational PostgreSQL* module, focusing on the three themes in its title: **function call cost**, **side-effect boundaries**, and **criteria for placing logic in the database**.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish functions from procedures in PostgreSQL.
2. Explain fixed per-call overhead versus work performed inside a function.
3. Identify per-row function call patterns that introduce *row-by-row overhead* or hidden N+1 queries.
4. Understand when a `LANGUAGE SQL` function can be *inlined* by the planner and why PL/pgSQL usually establishes a separate execution boundary.
5. Rewrite appropriate loop-based logic into set-based SQL.
6. Distinguish `IMMUTABLE`, `STABLE`, and `VOLATILE` along with their usage restrictions.
7. Understand planner metadata such as `COST`, `ROWS`, `PARALLEL SAFE/RESTRICTED/UNSAFE`, and `STRICT`.
8. Distinguish transactional data modifications from sequence state and external side effects.
9. Recognize that functions cannot `COMMIT` the caller's transaction and identify the rules governing transaction control inside procedures.
10. Evaluate the benefits, risks, and operational cost of placing logic in the database versus Java/application services.
11. Use `EXPLAIN (ANALYZE, BUFFERS)` and statistics views to diagnose slow execution.
12. Design safe, versionable, and testable function/procedure APIs.

## 2. The Big Picture: Application, SQL, and In-Database Logic

~~~text
Java / HTTP service / batch job
            |
            | JDBC query / CALL
            v
       PostgreSQL server
            |
            +-- SQL parser / planner / executor
            |
            +-- SQL function
            |      +-- Can be inlined if eligible
            |      +-- Or executed across its own function boundary
            |
            +-- PL/pgSQL function
            |      +-- Variables, IF, LOOP, RETURN
            |      +-- SQL statements execute through the SQL engine
            |
            +-- Procedure
                   +-- CALL, SQL/procedural operations
                   +-- Transaction control under supported conditions
~~~

Three **separate cost components** must be evaluated independently:

- **Network round trips** between the application and the database.
- **Per-call overhead** of each function invocation and each SQL statement inside it.
- **Actual data processing cost**: index/heap reads, joins, sorts, aggregates, WAL generation, locking, and resource contention.

Moving many SQL queries from Java into a stored function can reduce network round trips, yet if that stored function executes thousands of row-by-row queries internally, you have merely pushed the N+1 pattern from the application tier into the database without fixing its root cause.

## 3. How Functions and Procedures Differ

| Aspect | Function | Procedure |
|---|---|---|
| Created with | `CREATE FUNCTION` | `CREATE PROCEDURE` |
| Typical invocation | `SELECT f(...)`, inside SQL expressions | `CALL p(...)` |
| Return values | Scalar, composite, `SETOF`/`TABLE`, `void`, etc. | `OUT`/`INOUT` per version support; not usable as scalar expression |
| Allowed in `SELECT`/`WHERE` | Yes, when type and semantics fit | No, not usable in expressions |
| Transaction control | Cannot `BEGIN`/`COMMIT`/`ROLLBACK` caller's transaction | Supported under specific `CALL`/`DO` conditions |
| Volatility labels | `IMMUTABLE`, `STABLE`, `VOLATILE` | Does not share expression volatility model |
| Planner inlining | Certain eligible SQL functions | Not applicable as inline expressions in `SELECT` |
| Common use cases | Computations, reusable queries, data-returning APIs, controlled DML | Multi-step workflows, admin/batch tasks invoked with `CALL` |

### 3.1. A Function Is Not Simply a "Procedure with Different Syntax"

A function can execute DML when declared and invoked appropriately, yet it still cannot commit independently mid-transaction on behalf of the caller. Procedures follow the `CALL` model and dedicated transaction-control rules.

### 3.2. Procedures Are Not Automatically Faster Than Functions

If a procedure and a function each execute 10,000 repeated `UPDATE` statements in a loop, most of the total cost remains those 10,000 SQL executions. Changing the invocation mechanism does not turn a row-by-row algorithm into a set-based one.

### 3.3. Choose the Object Type by Contract

- Need an expression inside `SELECT` or a computed result: **function**.
- Need an operational `CALL` API, possibly managing transactions under supported conditions: **procedure**.
- Only need a straightforward SQL statement executed by the application: no function or procedure is required.

## 4. A Mental Model for Estimating Function Call Cost

To diagnose bottlenecks, we can model total execution time roughly as:

\[
T_{\text{total}} \approx T_{\text{network}}+
N_{\text{calls}}\times T_{\text{call-overhead}}+
\sum_{i=1}^{N_{\text{calls}}} T_{\text{work},i}
+T_{\text{other}}
\]

Where:

- `T_network`: time spent sending requests across the network/protocol between client and PostgreSQL.
- `N_calls`: number of times the executor actually invokes the function.
- `T_call-overhead`: dispatch, context setup, argument evaluation, type handling, and interpreter/runtime overhead if any.
- `T_work,i`: cost of SQL statements, expressions, or writes executed during invocation *i*.
- `T_other`: planning, locking, serialization, result fetching, and miscellaneous overhead.

This is a **mental model**, not an exact formula PostgreSQL uses to compute execution time.

### 4.1. Small Overheads Multiply Quickly

Even when per-call overhead is tiny, evaluating a function in an expression across millions of rows turns that small overhead into a significant cost.

### 4.2. Do Not Blindly Multiply by Table Row Count

The executor may filter rows earlier, inline the expression, pick a different plan, or avoid evaluating the expression in some cases. Actual invocation count depends on the **execution plan**, not always the physical row count of the table.

### 4.3. Work Inside the Function Often Exceeds Dispatch Overhead

A PL/pgSQL function executing `SELECT COUNT(*) FROM orders WHERE ...` for each customer costs orders of magnitude more than simple arithmetic. The bottleneck is often not just interpreter overhead, but the **number of internal queries and repeated data reads**.

## 5. A Function in SELECT Can Be Invoked Many Times

Example:

~~~sql
SELECT
    order_id,
    amount,
    finance.apply_discount(amount, 0.10) AS after_discount
FROM sales.orders
WHERE status = 'paid';
~~~

If this query returns one million orders, the function may need to be evaluated across very many rows.

### 5.1. A Simple Function Still Has Evaluation Semantics

Even when the body only multiplies and calls `round`, PostgreSQL still handles expression evaluation, argument types, and result handling; the real runtime impact depends on whether it is inlined.

### 5.2. Functions Containing SQL Inside Are Higher Risk

~~~sql
SELECT customer_id,
       reporting.count_paid_orders(customer_id)
FROM core.customers;
~~~

If `count_paid_orders` runs an internal `SELECT` for every customer, you have **per-row correlated work**, potentially triggering thousands of executor invocations and nested SQL executions.

### 5.3. Not Every Function Call Is Slow

Simple SQL functions can be inlined. Even a small PL/pgSQL function may be completely acceptable if called only a few times per request. **Evaluate scale and query plans** rather than rejecting functions based on rumors that "stored functions are always slow".

## 6. SQL Functions and Inlining

A `LANGUAGE SQL` function contains SQL expressions or queries. Under certain conditions, PostgreSQL can **inline** the function body directly into the calling query as an expression or relational subquery.

Example:

~~~sql
CREATE FUNCTION finance.discounted_amount(
    p_amount NUMERIC,
    p_discount_rate NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT round(p_amount * (1 - p_discount_rate), 2);
$$;
~~~

In a calling query:

~~~sql
SELECT finance.discounted_amount(amount, 0.10)
FROM sales.orders;
~~~

The planner **may** rewrite the logic into an inline expression, removing most of the separate function-call boundary.

### 6.1. Inlining Is an Optimization Opportunity, Not a Guarantee

Not every SQL function is inlined. Eligibility depends on:

- Function structure (scalar vs. set-returning).
- Number and structure of statements and expressions in the body.
- Volatility, strictness, and declared attributes.
- Security attributes.
- `SET` clauses, execution environment, and planner constraints.
- How the function is invoked, operator/argument types, and PostgreSQL version.

### 6.2. SECURITY DEFINER and Inlining

A `SECURITY DEFINER` function carries special privilege semantics; the planner is not permitted to inline it arbitrarily if doing so would alter permission boundaries. Treat `SECURITY DEFINER` as a condition that can block inlining, and never enable it expecting "faster execution".

### 6.3. An SQL Function Is Not Always Better Than an Inline Expression

A complex SQL function ineligible for inlining still runs across a call boundary. For a single-use simple expression, writing it directly in SQL can be clearer. When a stable reusable contract is needed, a function can be well worth a minor boundary cost.

### 6.4. How to Spot Inlining

Use `EXPLAIN (VERBOSE)` and inspect the displayed target-list/filter expressions; you may see the expanded expression in the plan instead of an explicit function call. Keep in mind that plan output does not guarantee inlining in every situation, so combine metadata understanding with real measurement.

## 7. PL/pgSQL Functions: Power and Overhead

`PL/pgSQL` provides variables, conditionals, loops, error handling, `RETURN QUERY`, and execution of SQL statements.

~~~sql
CREATE FUNCTION finance.discounted_amount_pl(
    p_amount NUMERIC,
    p_discount_rate NUMERIC
)
RETURNS NUMERIC
LANGUAGE plpgsql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
BEGIN
    RETURN round(p_amount * (1 - p_discount_rate), 2);
END;
$$;
~~~

### 7.1. Not Inlined Like Simple SQL Expressions

PL/pgSQL functions execute through the PL/pgSQL procedural runtime rather than receiving the expression/query inlining applied to eligible `LANGUAGE SQL` functions. This creates an optimization boundary when invoked per row inside a query.

### 7.2. Internal SQL Still Runs Through the PostgreSQL SQL Engine

PL/pgSQL does not scan tables with a custom interpreter. Whenever a `SELECT` or `UPDATE` runs inside PL/pgSQL, it is parsed, planned, and executed by the regular SQL engine.

### 7.3. Plan Caching Does Not Eliminate Many Separate Calls

PL/pgSQL caches execution plans for eligible static SQL statements and chooses between custom and generic plans. That reduces repeated planning, but it does not turn 10,000 separate `SELECT` invocations into a single `JOIN`.

### 7.4. Dynamic EXECUTE Has Its Own Trade-Offs

In PL/pgSQL, dynamic `EXECUTE` generally re-plans the dynamic query string on every execution; this helps when SQL structure varies or parameter-specific plans are required, but it increases planning cost and risks SQL injection if strings are constructed carelessly.

### 7.5. When Does PL/pgSQL Fit Well?

- Multi-step workflows requiring consistent transaction scope.
- Conditional/procedural control flow that is awkward in a single SQL statement.
- Encapsulating validation and DML behind a controlled interface.
- Triggers or routines needing state inspection and exception handling.
- Administrative tasks with clear operational rules.

Do not pick PL/pgSQL merely because `IF`/`LOOP` syntax feels familiar from Java.

## 8. Set-Based SQL Is Usually the First Choice

PostgreSQL is built to operate on **sets of rows**. When logic can be expressed with joins, aggregates, window functions, `INSERT ... SELECT`, or `UPDATE ... FROM`, the planner can choose efficient access paths and execution strategies across the whole dataset.

### 8.1. Row-by-Row

~~~text
for customer in customers:
    count = SELECT COUNT(*)
            FROM orders
            WHERE orders.customer_id = customer.id
    save(customer, count)
~~~

This generates a separate query or function invocation per customer.

### 8.2. Set-Based

~~~sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS paid_count
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'paid'
GROUP BY c.customer_id;
~~~

The planner can optimize the join and aggregation across all customers in a single pass.

### 8.3. COUNT with LEFT JOIN

Use `COUNT(o.order_id)` or `COUNT(*) FILTER (WHERE ...)` carefully; `COUNT(*)` over a `LEFT JOIN` counts the null-extended row for customers with zero orders, producing `1` instead of `0`.

### 8.4. Not Every Correlated Subquery Is Bad

In pure SQL, the planner can decorrelate, memoize, or choose parameterized nested-loop plans for certain correlated patterns. The trickier case is correlation hidden inside a PL/pgSQL function whose internal SQL structure is opaque to the outer query planner.

## 9. When Does Database Logic Reduce Network Round Trips?

Suppose a Java service needs to:

1. Check that an order is currently `new`.
2. Transition it to `paid`.
3. Write an audit record.
4. Return the result.

Executing those steps via separate JDBC statements creates multiple network round trips and increases the risk of split transactions if application transaction management is misconfigured.

A function or procedure can execute these steps **close to the data** in a single `CALL` or `SELECT` from the application. Even so:

- Transaction semantics must remain clean.
- Concurrency must be handled properly.
- Non-rollbackable HTTP network calls must not be placed inside the transaction without an appropriate pattern.
- Sometimes a single `UPDATE ... RETURNING` statement paired with an audit trigger or outbox suffices without procedural code.

**Fewer round trips are a potential advantage**, not proof that every stored function outperforms Java.

## 10. Volatility: IMMUTABLE, STABLE, and VOLATILE

PostgreSQL uses **volatility** attributes to understand how stable a function's output is and how aggressively the optimizer may transform calls.

| Attribute | Contract Meaning | Appropriate Examples |
|---|---|---|
| `IMMUTABLE` | Returns the exact same result for the same arguments across all calls under valid semantics | Pure math, pure string normalization |
| `STABLE` | Within a single statement, returns consistent results for the same arguments; may depend on stable read state | Table lookups, transaction timestamp |
| `VOLATILE` | Output can vary across consecutive calls or function has side effects | `random()`, `clock_timestamp()`, sequences/DML |

### 10.1. Default Is VOLATILE

When omitted, user-defined PostgreSQL functions default to `VOLATILE`. This is conservative and can inhibit optimizations if the function is actually pure or stable.

### 10.2. Volatility Is a Developer Promise

Mislabeling volatility is a correctness bug, not merely a performance issue. The planner uses volatility to fold expressions, reuse evaluations, or select index/plan structures assuming result stability.

### 10.3. Do Not Mark a Function IMMUTABLE Just to Enable an Index

A function reading a pricing table or feature-flag table can return different values after `INSERT`/`UPDATE` activity, so it is not truly immutable. Forcing `IMMUTABLE` so PostgreSQL accepts an expression index or generated column can yield stale or wrong results after data changes.

## 11. IMMUTABLE: Pure Functions and Restrictions

Example:

~~~sql
CREATE FUNCTION finance.add_tax(
    p_amount NUMERIC,
    p_tax_rate NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT round(p_amount * (1 + p_tax_rate), 2);
$$;
~~~

This relies purely on its arguments and deterministic arithmetic under compatible data types and settings.

### 11.1. Uses of IMMUTABLE

- Eligible for use in expression indexes (subject to expression rules).
- Eligible for use in generated columns.
- Planner can constant-fold calls when arguments are constants.
- Enables broader optimizer rewrites when other conditions are satisfied.

### 11.2. Do Not Depend on Mutable Tables

If a function reads an exchange-rate table or a mutable product price table, declaring it `IMMUTABLE` is wrong because results depend on external state beyond the arguments.

### 11.3. Timezones and Session Settings Are Hidden Hazards

A function formatting or converting timestamps based on the session `TimeZone` or locale settings may not truly be `IMMUTABLE`. Never assume timestamp formatting is immutable simply because "an instant in time never changes".

### 11.4. Beware Constant Folding and Cached Plans

If mislabeled, an expression precomputed once and embedded into a cached plan can return stale results when environment settings or data change — bugs that often surface only in production under prepared statement plan reuse.

## 12. STABLE: Statement-Snapshot Consistency

Example reading a discount rate from a table:

~~~sql
CREATE FUNCTION pricing.current_discount(
    p_customer_id BIGINT
)
RETURNS NUMERIC
LANGUAGE SQL
STABLE
AS $$
    SELECT discount_rate
    FROM pricing.customer_discounts
    WHERE customer_id = p_customer_id;
$$;
~~~

This syntax is illustrative; the referenced schemas and tables must exist.

### 12.1. Why STABLE Fits Better Than IMMUTABLE

Discount rates may be updated later. Within a single running statement, snapshot semantics keep lookups consistent, yet results are never promised to stay invariant across future statements.

### 12.2. Side-Effect Restrictions

`STABLE` and `IMMUTABLE` functions must not perform database-modifying SQL according to PostgreSQL's language enforcement rules. Functions executing DML must be marked `VOLATILE`.

### 12.3. Time Examples

- `now()` / `CURRENT_TIMESTAMP` reflect the current transaction start time and carry `STABLE` semantics matching their contract.
- `clock_timestamp()` advances even within a single statement and is `VOLATILE`.

### 12.4. Snapshot Behavior

In SQL and standard procedural languages, `STABLE` and `IMMUTABLE` functions inherit the calling query's snapshot according to documented rules, whereas `VOLATILE` functions executing nested queries can obtain fresh snapshots seeing concurrent changes. This affects MVCC consistency and correctness, not just planner cost.

## 13. VOLATILE: Changing Values and Side Effects

Typical functions:

~~~sql
SELECT random();
SELECT clock_timestamp();
SELECT nextval('some_sequence');
~~~

`nextval` requires an existing sequence and demonstrates a stateful side effect.

### 13.1. DML Inside Functions

A workflow function performing `INSERT`, `UPDATE`, or `DELETE` must be marked with appropriate volatility, normally `VOLATILE`.

### 13.2. VOLATILE Does Not Allow Self-Commit

A `VOLATILE` function still executes inside the caller's statement/transaction and cannot arbitrarily `COMMIT` or `ROLLBACK`.

### 13.3. Multiple Invocations Cause Multiple Side Effects

An audit-inserting function placed inside a multi-row `SELECT` can insert many rows — possibly more than expected if query plans, joins, retries, or client consumption change. Never implement an exactly-once audit write by hiding an `INSERT` inside a `SELECT` expression.

### 13.4. Evaluation Order Should Not Be a Business Contract

SQL is declarative. Never rely on observed evaluation order of select-list expressions, `WHERE` filters, joins, or `LIMIT` to control how many times or in what order a side-effecting function runs unless explicitly guaranteed.

### 13.5. Side Effects Constrain Optimization

Planner transformations are restricted to respect `VOLATILE` semantics, though defensively labeling pure functions `VOLATILE` "just to be safe" unnecessarily blocks valid optimizations. Classify functions accurately rather than out of habit.

## 14. STRICT and NULL Semantics

A function declared `STRICT` (or `RETURNS NULL ON NULL INPUT`) skips executing its body whenever any argument is SQL `NULL` and returns `NULL` directly.

~~~sql
CREATE FUNCTION finance.multiply_amount(
    p_amount NUMERIC,
    p_factor NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
AS $$
    SELECT p_amount * p_factor;
$$;
~~~

### 14.1. Why Is It Helpful?

It avoids invoking the body when the result is guaranteed to be `NULL` and documents the `NULL` contract explicitly.

### 14.2. Do Not Mark STRICT If Business Logic Handles NULLs

If the function treats `NULL` as `0` or uses a default fallback, declaring `STRICT` prevents the body from executing on `NULL` input and yields `NULL` instead.

### 14.3. STRICT Is Not Domain Validation

`STRICT` does not validate that a discount lies in `[0, 1]`, that an amount is non-negative, or that an ID exists; use explicit constraints and validation logic for that.

## 15. Planner COST: An Estimate, Not Real Time

PostgreSQL allows specifying an estimated execution cost:

~~~sql
CREATE FUNCTION finance.expensive_score(
    p_amount NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
COST 200
AS $$
    SELECT sqrt(abs(p_amount)::double precision)::numeric;
$$;
~~~

### 15.1. What Is COST Used For?

`COST` is a **hint to the planner**, not a measurement in milliseconds. Its units follow PostgreSQL's cost model, typically scaled relative to `cpu_operator_cost`. For set-returning functions, cost is interpreted on a per-returned-row basis.

### 15.2. Default Values

PostgreSQL versions typically default to a low cost for internal/C functions (commonly `1`) and a higher cost for other languages (commonly `100`) unless overridden. These are **heuristic constants**, not benchmark measurements.

### 15.3. COST Does Not Force Fewer Invocations

Raising `COST` will not convert a PL/pgSQL loop into a `JOIN`. The planner may reposition filter evaluation or choose a different eligible plan, yet it cannot magically cure an $O(N^2)$ algorithm.

### 15.4. Inlining Changes How COST Applies

When an SQL function is inlined, the planner evaluates the expanded expression tree directly; do not assume `COST` behaves the same as on an opaque function call.

### 15.5. Tune Only After Measuring

If a genuinely expensive function keeps the low default cost, the planner might underprice it; inflating `COST` excessively can equally distort plans. Benchmark a representative workload and compare `EXPLAIN` output instead of picking arbitrary numbers.

## 16. ROWS: Cardinality Estimate for Set-Returning Functions

Functions returning sets of rows can declare `ROWS`:

~~~sql
CREATE FUNCTION reporting.paid_orders_for_customer(
    p_customer_id BIGINT
)
RETURNS TABLE (
    order_id BIGINT,
    amount NUMERIC
)
LANGUAGE SQL
STABLE
ROWS 100
AS $$
    SELECT order_id, amount
    FROM sales.orders
    WHERE customer_id = p_customer_id
      AND status = 'paid';
$$;
~~~

### 16.1. ROWS Does Not Truncate Results

`ROWS 100` is **not `LIMIT 100`**. It is purely the planner's cardinality estimate of how many rows the function is expected to emit.

### 16.2. Why Does It Matter?

If the planner estimates `1,000` rows when the function actually yields one million, join ordering, join algorithms, memory sizing, and downstream cardinality estimates can degrade sharply.

### 16.3. Typical Default

For set-returning functions, PostgreSQL commonly defaults to an estimate of `ROWS 1000` when unspecified (subject to inlining and version behavior). Never mistake `1000` for an actual row cap.

### 16.4. Adjusting via ALTER FUNCTION

~~~sql
ALTER FUNCTION reporting.paid_orders_for_customer(BIGINT)
ROWS 50 COST 100;
~~~

This requires the function to exist. It updates planner metadata without modifying data or guaranteeing faster plans.

## 17. PARALLEL SAFE, RESTRICTED, and UNSAFE

Function labels also govern parallel query execution:

| Label | Meaning |
|---|---|
| `PARALLEL SAFE` | Safe to execute inside parallel worker processes under documented conditions |
| `PARALLEL RESTRICTED` | Cannot run inside parallel workers; may execute only in the parallel leader |
| `PARALLEL UNSAFE` | Prevents the query from using parallelism under planner rules |

### 17.1. Conservative Default

User-defined functions normally default to `PARALLEL UNSAFE` if unspecified. Pure functions can be marked `PARALLEL SAFE` once verified.

### 17.2. Pure Computation Example

~~~sql
CREATE FUNCTION finance.square_number(
    p_input NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_input * p_input;
$$;
~~~

### 17.3. Operations Requiring Caution

Functions modifying database state, advancing sequences, touching temporary tables, or reading backend-local session state are generally unsafe inside parallel workers. Classification depends on exact runtime behavior, not merely SQL vs. PL/pgSQL syntax.

### 17.4. Mislabeling Can Break Correctness

Marking a side-effecting function `PARALLEL SAFE` to "force a faster parallel plan" can fail at runtime or produce wrong behavior. Never mark `SAFE` without auditing the function and everything it calls.

### 17.5. PARALLEL SAFE Does Not Guarantee a Parallel Plan

The planner also weighs table size, costs, configuration settings, operators, join shapes, and system load. `PARALLEL SAFE` merely **permits** parallelism; it never forces it.

## 18. Side Effects: Defining the Full Scope

"Side effects" extend well beyond DML. Classify all of them:

1. **Transactional table mutations**: `INSERT`, `UPDATE`, `DELETE`.
2. **Sequence state**: `nextval`, `setval` generally do not roll back like table rows.
3. **Locks**: row, table, and advisory locks with differing lifetimes.
4. **Session/backend state**: configuration GUCs, temporary objects, session variables.
5. **External I/O**: HTTP calls, filesystem writes, external systems via extensions or untrusted languages.
6. **Notifications/events**: `NOTIFY`, logical outbox tables, or extension integrations.
7. **Time/randomness**: clock or RNG calls change results even without modifying tables.

### 18.1. Side Effects Make Functions Harder to Reason About

A "price calculation" function that silently logs rows or calls external services is far harder to benchmark, retry, and unit-test than a pure function depending solely on its arguments.

### 18.2. Distinguish Observable State from Mutable Side Effects

A table-reading function marked `STABLE` can return different outputs across statements; that is a dependency on database state rather than a **DML side effect**, though it still disqualifies `IMMUTABLE`.

### 18.3. Transaction Boundaries Are Key

Not all side effects roll back with a PostgreSQL transaction. You must know precisely which actions stay atomic with primary table writes.

## 19. DML Inside a Function Still Runs in the Caller's Transaction

Example:

~~~sql
CREATE FUNCTION audit.record_event(
    p_type TEXT,
    p_detail TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_id BIGINT;
BEGIN
    INSERT INTO audit.events(event_type, detail)
    VALUES (p_type, p_detail)
    RETURNING event_id INTO v_id;

    RETURN v_id;
END;
$$;
~~~

### 19.1. No Independent Commit Inside a Function

When called inside a transaction, inserted rows commit or roll back together with that transaction under PostgreSQL's transaction rules.

### 19.2. Rollback Example

~~~sql
BEGIN;

SELECT audit.record_event(
    'demo',
    'this row belongs only to the test transaction'
);

ROLLBACK;
~~~

The row inserted into `audit.events` disappears after `ROLLBACK`.

### 19.3. Sequences Still Advance

If `event_id` is backed by an identity column or sequence, `nextval` allocations generally **do not roll back** with the row transaction. After `ROLLBACK`, the sequence remains incremented and subsequent IDs skip numbers.

### 19.4. Why Does This Matter?

Assuming "gapless sequential IDs" or treating sequence IDs as contiguous accounting document numbers is a design mistake. Sequences generate unique identifiers, not gap-free ledgers.

## 20. Functions Cannot Arbitrarily BEGIN/COMMIT/ROLLBACK Transactions

A PL/pgSQL **function** invoked within an SQL statement or expression cannot terminate the caller's transaction via `COMMIT` or `ROLLBACK`.

~~~sql
-- INVALID PATTERN FOR A FUNCTION
CREATE FUNCTION demo_wrong_transaction()
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    COMMIT;
END;
$$;
~~~

This snippet is **not a valid transaction-controlling function**. Do not copy it into production.

### 20.1. Why?

An SQL statement operates within a caller/session-level transaction boundary. A nested function must not silently commit half the work while the enclosing statement is still running.

### 20.2. Multi-Step Atomicity Pattern

Let the caller open a transaction and invoke the required SQL statements or functions:

~~~sql
BEGIN;
-- Steps that must commit or roll back atomically
COMMIT;
~~~

Or encapsulate non-committing DML inside a function or procedure so the outer transaction decides when to commit or roll back.

### 20.3. Batch Commits Across Multiple Transactions

Evaluate procedures/`DO` blocks under valid `CALL` rules, or orchestrate batched commits from the application tier with explicit transaction boundaries. Avoid uncontrolled autonomous-transaction hacks.

## 21. Procedures and Transaction Control

Since PostgreSQL 11, `CREATE PROCEDURE` combined with `CALL` allows transaction control under specific conditions.

### 21.1. Standard Transactional Procedure

~~~sql
CREATE PROCEDURE orders.mark_paid(
    p_order_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE orders.orders
    SET status = 'paid'
    WHERE order_id = p_order_id
      AND status = 'new';
END;
$$;
~~~

This procedure contains **no `COMMIT`**. The caller retains transaction ownership and the procedure runs inside that transaction context.

### 21.2. Procedure with Internal COMMIT

Under supported PostgreSQL conditions, a top-level `CALL` outside an explicit transaction block can perform transaction control inside the procedure:

~~~sql
CREATE PROCEDURE audit.commit_one_event(
    p_detail TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO audit.events(event_type, detail)
    VALUES ('procedure_demo', p_detail);

    COMMIT;
END;
$$;
~~~

This is a specialized pattern, **not a default recommendation**.

### 21.3. Critical Conditions

Transaction control inside procedures depends on:

- Top-level `CALL` or `DO` invocation context.
- Not being nested inside a prohibited explicit transaction block.
- Valid nested `CALL`/`DO` chains with no intervening incompatible frames.
- Restrictions around `SECURITY DEFINER` or function/procedure `SET` clauses.
- Not ending transactions inside an active `EXCEPTION` block subtransaction.
- Target PostgreSQL version support.

### 21.4. When Does CALL ... COMMIT Fail?

If the client executes:

~~~sql
BEGIN;
CALL audit.commit_one_event('abc');
COMMIT;
~~~

internal `COMMIT` is normally rejected because the procedure runs inside an explicit transaction block. In JDBC, `autoCommit = false` often places statements into a client-managed transaction with the same effect.

### 21.5. Do Not Turn Every Procedure Into a Commit Manager

Many business workflows require the caller to compose multiple atomic operations. A procedure that commits unexpectedly breaks the application service's transaction contract. Use internal transaction control only when genuinely required and documented explicitly in the API.

## 22. EXCEPTION Blocks and Subtransaction Overhead

In PL/pgSQL, an `EXCEPTION` block uses PostgreSQL's subtransaction machinery, introducing extra overhead.

~~~sql
CREATE FUNCTION orders.try_mark_paid(
    p_order_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
VOLATILE
AS $$
BEGIN
    BEGIN
        UPDATE orders.orders
        SET status = 'paid'
        WHERE order_id = p_order_id
          AND status = 'new';
        RETURN FOUND;
    EXCEPTION WHEN unique_violation THEN
        RETURN FALSE;
    END;
END;
$$;
~~~

This illustrates exception-block mechanics; `unique_violation` is not the natural error for this `UPDATE`. Never catch mismatched exceptions in production.

### 22.1. EXCEPTION Is Not Free

An exception-handling block incurs subtransaction setup and cleanup overhead even on the happy path when no error occurs. Avoid wrapping every row in `EXCEPTION` if SQL constraints or `ON CONFLICT` achieve the required semantics cleanly.

### 22.2. When an Exception Occurs

Database writes made inside the failing block roll back via the subtransaction; PL/pgSQL local variables and external non-transactional side effects do not necessarily revert to prior values.

### 22.3. Never Swallow All Errors with WHEN OTHERS

Catching `WHEN OTHERS` and silently returning `FALSE` hides data corruption, deadlocks, permission denials, and critical failures. Catch specific expected errors, record context, and decide explicitly whether to retry or propagate.

### 22.4. When Should EXCEPTION Be Used?

Use `EXCEPTION` when translating specific database errors into controlled business outcomes where set-based checks or `ON CONFLICT` cannot handle the case. For rare error paths the overhead is often fine; for hot per-row loops, measure carefully.

## 23. DML Side Effects in SELECT: An Easy-to-Miss Anti-Pattern

~~~sql
SELECT
    order_id,
    audit.record_event('read_order', order_id::text)
FROM orders.orders
WHERE status = 'paid'
LIMIT 100;
~~~

### 23.1. Consequences

A "read" query now inserts audit rows. Retrying the `SELECT` writes duplicate rows. If the planner or executor changes evaluation order or re-evaluates expressions, side-effect counts and ordering are not a reliable business guarantee unless explicitly documented.

### 23.2. Reads Should Not Silently Mutate Business State

A GET endpoint or reporting `SELECT` should maintain a clean side-effect contract. If read auditing is needed, use proper application telemetry or dedicated logging rather than embedding `INSERT` inside a `SELECT` expression.

### 23.3. When DML Functions Make Sense

A command-style function like `record_payment(...)` called deliberately as a write operation is reasonable when transactions, idempotency, and privileges are properly controlled. What matters is that **callers recognize it as a write operation**.

### 23.4. Do Not Rely on LIMIT as an Exact Side-Effect Counter

`LIMIT` constrains returned rows, not a standalone guarantee of how many times a side-effecting function runs across every plan. Model writes as explicit DML statements or procedures whenever exactly-once business effects are needed.

## 24. Transaction Rollback Does Not Undo Every Side Effect

### 24.1. Table DML

`INSERT`, `UPDATE`, and `DELETE` within the same transaction normally roll back together on `ROLLBACK`.

### 24.2. Sequences

`nextval` and sequence state adjustments do not roll back like table rows. Gaps are normal.

### 24.3. NOTIFY

`NOTIFY` inside a transaction delivers notifications only upon commit; it does not equate to firing irreversible external emails or webhooks mid-statement.

### 24.4. External I/O

If an extension or external helper executes an HTTP request, sends an email, or writes to an external service, rolling back the PostgreSQL transaction **cannot undo** that external effect.

### 24.5. Advisory Locks

Transaction-level and session-level advisory locks have distinct lifetimes. Session-level advisory locks survive transaction rollback; choose the right scope and ensure reliable release.

### 24.6. Architectural Takeaway

When external side effects must stay consistent with database commits, use a **transactional outbox** in PostgreSQL paired with a reliable out-of-band worker publishing after commit, rather than invoking external systems inside transactions.

## 25. Transactional Outbox: Pattern for Reliable Event Publishing

Suppose we mark an order paid and emit an `OrderPaid` event to another service using an outbox:

~~~text
PostgreSQL Transaction:
  UPDATE orders SET status='paid'
  INSERT INTO event_outbox(...)
  COMMIT
                |
                v
Out-of-process worker reads outbox
  -> sends message / HTTP request
  -> marks processed / schedules retry
~~~

### 25.1. Atomic In-Database Writes

The order update and outbox `INSERT` share the same transaction; on rollback, neither row commits.

### 25.2. Delivery Is Not Automatically Exactly-Once

A worker may dispatch the message and crash before marking it processed, then retry. Downstream consumers must handle idempotency and deduplication by event ID.

### 25.3. Why Is This Better Than HTTP Calls Inside Functions?

External network latency or failures do not hold PostgreSQL transactions open unnecessarily; rollback and retry behavior remain clean and observable.

### 25.4. Outboxes Have Operational Cost Too

You still need workers or CDC, polling, retention cleanup, monitoring, dead-letter retries, and consumer idempotency. It is a deliberate engineering trade-off for distributed side effects, not free magic.

## 26. Security Invoker and Security Definer

PostgreSQL functions default to **SECURITY INVOKER** unless specified otherwise. With `SECURITY DEFINER`, code executes under the privileges of the function owner according to PostgreSQL rules.

### 26.1. SECURITY INVOKER

The caller must hold privileges for the underlying operations. Appropriate when caller grants and RLS policies should govern execution directly.

### 26.2. SECURITY DEFINER

Exposes a tightly scoped capability without granting callers broad permissions on underlying tables.

~~~sql
CREATE FUNCTION api.safe_mark_paid(
    p_order_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app_private, pg_temp
AS $$
BEGIN
    UPDATE app_private.orders
    SET status = 'paid'
    WHERE order_id = p_order_id
      AND status = 'new';

    RETURN FOUND;
END;
$$;
~~~

This architectural example assumes matching schemas, tables, and roles; do not deploy without designing permissions carefully.

### 26.3. Safe search_path Configuration

For `SECURITY DEFINER`, include only **trusted schemas** in `search_path`, place `pg_temp` last per PostgreSQL security guidance, and schema-qualify all important tables and functions. Avoid schemas where untrusted users have `CREATE` privileges that could hijack name resolution.

### 26.4. Least-Privilege Owner

Never assign a superuser as owner of `SECURITY DEFINER` functions merely to skip configuring grants. Create a dedicated role holding only the required table privileges.

### 26.5. Explicit GRANT EXECUTE

By default, PostgreSQL grants `EXECUTE` on newly created functions to `PUBLIC` unless overridden. For sensitive functions, create the routine, `REVOKE` from `PUBLIC`, and `GRANT` to target roles inside the same transaction to eliminate exposure windows.

### 26.6. Test RLS Under Realistic Roles

Owners or roles with `BYPASSRLS` behave differently from standard users. `SECURITY DEFINER` alters how RLS policies evaluate. Always run integration tests under actual application roles rather than superusers.

## 27. EXECUTE Privileges as Part of the API

Standard pattern:

~~~sql
BEGIN;

CREATE FUNCTION app_private.log_action(
    p_action TEXT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app_private, pg_temp
AS $$
BEGIN
    INSERT INTO app_private.audit_events(action_name)
    VALUES (p_action);
END;
$$;

REVOKE ALL
ON FUNCTION app_private.log_action(TEXT)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION app_private.log_action(TEXT)
TO app_writer;

COMMIT;
~~~

This assumes `app_private.audit_events` and the `app_writer` role already exist.

### 27.1. Schema USAGE Is Still Required

Calling roles also need `USAGE` on the schema. `GRANT EXECUTE` on the function does not bypass schema access rules.

### 27.2. Write-Capable Functions Are Sensitive Interfaces

If callers only have `EXECUTE` on a DML function, validate inputs, tenant ownership, state transitions, and business rules inside the routine so users cannot tamper with rows belonging to another tenant.

### 27.3. Do Not Use Functions to Bypass Authorization Policy

`SECURITY DEFINER` is a specialized privilege mechanism, not an excuse to bypass authorization. Auditing, tests, and data-path reviews are mandatory.

## 28. Which Logic Belongs in Constraints Rather Than Functions?

Many **simple, universal integrity rules** belong in constraints:

~~~sql
CREATE TABLE example_items (
    item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    sku TEXT NOT NULL UNIQUE,
    customer_id BIGINT REFERENCES customers(customer_id)
);
~~~

### 28.1. Why Constraints Excel

- Invariants hold regardless of whether Java, ETL pipelines, BI tools, or manual scripts write data.
- Constraints use purpose-built concurrency and locking semantics.
- Planners and schema tools understand constraints far better than opaque checking functions.
- Eliminates the risk of an application path forgetting to call a validator.

### 28.2. Never Replace UNIQUE with a SELECT COUNT Function

A function checking "does SKU exist yet, then `INSERT`" suffers race conditions under concurrent transactions. Use a `UNIQUE` constraint and handle conflicts intentionally.

### 28.3. Never Replace Foreign Keys with Pre-Insert Exists Checks

Pre-checking before `INSERT` cannot prevent concurrent deletes or updates between the check and insert steps. Use `FOREIGN KEY` constraints wherever relational integrity applies.

### 28.4. CHECK Has Limits

`CHECK` fits row-local invariants and supported expressions. Never call functions querying other tables inside `CHECK` expecting PostgreSQL to enforce cross-table invariants across concurrent modifications.

## 29. Trigger Functions: When They Help and What They Cost

Triggers let PostgreSQL invoke a function automatically in response to table events.

### 29.1. Helpful Scenarios

- Maintaining audit columns.
- Recording transactional outbox rows atomically.
- Maintaining derived columns that applications must never skip.
- Blocking prohibited state transitions where appropriate.

### 29.2. Per-Row Trigger Cost

A `FOR EACH ROW` trigger on a one-million-row bulk `INSERT` fires one million times. If each invocation queries multiple tables, total overhead escalates dramatically.

### 29.3. Consider Statement-Level Triggers

When processing can be done set-wise, evaluate `FOR EACH STATEMENT` triggers with transition tables where supported instead of executing row-by-row trigger logic unnecessarily.

### 29.4. Never Hide External Side Effects Inside Triggers

Making HTTP calls, sending emails, or talking to external systems inside triggers ties database writes to network availability and produces side effects that cannot roll back. Prefer outboxes or asynchronous workers.

### 29.5. Avoid Hidden "Magic" Triggers

A seemingly simple `INSERT` can trigger dozens of cascading operations silently. Document all trigger side effects and benchmark them before accepting the design.

## 30. Lab: Preparing Data to Measure Function Call Cost

This lab uses a dedicated schema `fn_cost_lab` in a **test database** — never run it in production. If the schema name already exists, choose another name instead of dropping someone else's objects.

### 30.1. Create Schema

~~~sql
CREATE SCHEMA fn_cost_lab;
~~~

### 30.2. Customers Table

~~~sql
CREATE TABLE fn_cost_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    tier TEXT NOT NULL
        CHECK (tier IN ('regular', 'premium')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

### 30.3. Orders Table

~~~sql
CREATE TABLE fn_cost_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES fn_cost_lab.customers(customer_id),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('new', 'paid', 'cancelled', 'archived')),
    created_at TIMESTAMPTZ NOT NULL
);
~~~

### 30.4. Audit Table

~~~sql
CREATE TABLE fn_cost_lab.audit_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
~~~

### 30.5. Load 1,000 Customers

~~~sql
INSERT INTO fn_cost_lab.customers (
    customer_id, name, tier
)
SELECT
    n,
    'Customer ' || n::text,
    CASE
        WHEN n % 10 = 0 THEN 'premium'
        ELSE 'regular'
    END
FROM generate_series(1, 1000) AS gs(n);
~~~

### 30.6. Load 100,000 Orders

~~~sql
INSERT INTO fn_cost_lab.orders (
    order_id, customer_id, amount, status, created_at
)
SELECT
    n,
    ((n - 1) % 1000) + 1,
    ((n % 997) + 1)::numeric(12,2),
    CASE
        WHEN n % 13 = 0 THEN 'cancelled'
        WHEN n % 3  = 0 THEN 'paid'
        ELSE 'new'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
       + n * INTERVAL '1 minute'
FROM generate_series(1, 100000) AS gs(n);
~~~

### 30.7. Index and Statistics

~~~sql
CREATE INDEX orders_customer_status_idx
ON fn_cost_lab.orders(customer_id, status);

ANALYZE fn_cost_lab.customers;
ANALYZE fn_cost_lab.orders;
~~~

The modulo data generator makes results reproducible. It is not a representative production workload; measured timings apply only to this test environment and dataset.

## 31. Lab: Pure SQL Function for Calculation

Create a discount function:

~~~sql
CREATE FUNCTION fn_cost_lab.discounted_amount(
    p_amount NUMERIC,
    p_discount_rate NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT round(p_amount * (1 - p_discount_rate), 2);
$$;
~~~

### 31.1. Single Call Check

~~~sql
SELECT fn_cost_lab.discounted_amount(100.00, 0.10)
    AS after_discount;
~~~

Expected result is `90.00` as a matching numeric type.

### 31.2. Set-Query Usage

~~~sql
SELECT
    order_id,
    amount,
    fn_cost_lab.discounted_amount(amount, 0.10)
        AS after_discount
FROM fn_cost_lab.orders
WHERE status = 'paid'
ORDER BY order_id
LIMIT 20;
~~~

### 31.3. Measure Across Many Rows

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    SUM(fn_cost_lab.discounted_amount(amount, 0.10))
FROM fn_cost_lab.orders;
~~~

### 31.4. Compare Against Inline Expression

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT SUM(round(amount * (1 - 0.10::numeric), 2))
FROM fn_cost_lab.orders;
~~~

Both express the exact same calculation. Because simple SQL functions can be inlined, do not assume there is always a large fixed call overhead.

## 32. Lab: Same Calculation in PL/pgSQL

~~~sql
CREATE FUNCTION fn_cost_lab.discounted_amount_pl(
    p_amount NUMERIC,
    p_discount_rate NUMERIC
)
RETURNS NUMERIC
LANGUAGE plpgsql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
BEGIN
    RETURN round(p_amount * (1 - p_discount_rate), 2);
END;
$$;
~~~

### 32.1. Measure on the Same Dataset

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    SUM(fn_cost_lab.discounted_amount_pl(amount, 0.10))
FROM fn_cost_lab.orders;
~~~

### 32.2. Comparison Goal

Compare total execution time and plan shape over repeated runs on the same dataset; PL/pgSQL runs via its function runtime rather than being inlined like eligible SQL functions.

### 32.3. Beware Warm-Up Caching and JIT

Initial runs can include cache warm-up, planning/compilation, and differing I/O. If JIT is enabled, timings may also shift. Never use a single pair of runs to proclaim "PL/pgSQL is always X times slower" across all systems.

### 32.4. How to Choose

For trivial math called over millions of rows, inline SQL expressions or inlinable SQL functions are usually worth trying first. For multi-step business logic, PL/pgSQL can be easier to maintain despite slightly higher per-call overhead.

## 33. Lab: A PL/pgSQL Function Querying a Table Per Call

Create a function counting paid orders for a customer:

~~~sql
CREATE FUNCTION fn_cost_lab.paid_order_count_pl(
    p_customer_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_count BIGINT;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM fn_cost_lab.orders
    WHERE customer_id = p_customer_id
      AND status = 'paid';

    RETURN v_count;
END;
$$;
~~~

### 33.1. Calling for One Customer

~~~sql
SELECT fn_cost_lab.paid_order_count_pl(42);
~~~

This is completely acceptable when called infrequently.

### 33.2. Calling for 500 Customers

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    c.customer_id,
    fn_cost_lab.paid_order_count_pl(c.customer_id)
        AS paid_count
FROM fn_cost_lab.customers AS c
WHERE c.customer_id <= 500
ORDER BY c.customer_id;
~~~

### 33.3. Hidden N+1 Inside the Database

The outer query scans 500 customers, yet the function executes a separate SQL lookup per customer. The index on `orders(customer_id, status)` speeds up each internal query, yet it still does not collapse 500 queries into a single aggregate.

### 33.4. Outer EXPLAIN Can Hide Internal SQL

The outer `SELECT` plan does not automatically break out plans for SQL running inside PL/pgSQL. Never conclude a function is cheap merely because the outer `EXPLAIN` shows a fast Index Scan on `customers`.

### 33.5. Measuring Total Cost

Combine function statistics or nested-statement instrumentation to observe invocation count and internal SQL execution time, then compare against the set-based rewrite next.

## 34. Lab: Rewriting into a Set-Based Query

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    c.customer_id,
    COUNT(o.order_id) AS paid_count
FROM fn_cost_lab.customers AS c
LEFT JOIN fn_cost_lab.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'paid'
WHERE c.customer_id <= 500
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

### 34.1. Why Is This Usually Worth Testing?

The planner sees the full join, cardinalities, indexes, and aggregation together. It can pick hash, merge, or nested-loop joins with aggregation instead of executing an opaque query per row.

### 34.2. Customers With Zero Orders

`COUNT(o.order_id)` yields `0` when no paid orders exist because null-extended rows produced by `LEFT JOIN` have `NULL` for `o.order_id`.

### 34.3. Joins Are Not Universally Faster in Every Case

For a single customer lookup, an indexed query is cheap. Set-based rewrites shine when processing larger batches of customers, though real workloads should always be measured.

### 34.4. Pre-Aggregation Alternative

~~~sql
SELECT
    c.customer_id,
    COALESCE(p.paid_count, 0) AS paid_count
FROM fn_cost_lab.customers AS c
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS paid_count
    FROM fn_cost_lab.orders
    WHERE status = 'paid'
    GROUP BY customer_id
) AS p
  ON p.customer_id = c.customer_id
WHERE c.customer_id <= 500
ORDER BY c.customer_id;
~~~

Depending on statistics and planner transformations, the optimizer may filter early or aggregate differently. Compare `EXPLAIN` output against the direct `LEFT JOIN`.

## 35. Lab: Controlled DML Function

Create a command function transitioning an order from `new` to `paid`:

~~~sql
CREATE FUNCTION fn_cost_lab.mark_order_paid(
    p_order_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
BEGIN
    UPDATE fn_cost_lab.orders
    SET status = 'paid'
    WHERE order_id = p_order_id
      AND status = 'new';

    RETURN FOUND;
END;
$$;
~~~

### 35.1. Why Include status in the WHERE Clause?

This implements a **conditional state transition**. Two concurrent requests attempting to pay the same `new` order must not both believe they transitioned it. Combining the `UPDATE ... WHERE` filter with row locking/MVCC ensures only one transition succeeds under database semantics.

### 35.2. Test Inside a Transaction and Roll Back

~~~sql
BEGIN;

SELECT fn_cost_lab.mark_order_paid(10) AS changed;

SELECT order_id, status
FROM fn_cost_lab.orders
WHERE order_id = 10;

ROLLBACK;
~~~

Order 10 in the sample dataset initially has status `new`. After `ROLLBACK`, the state change is undone.

### 35.3. RETURN FOUND Applies Only to the Immediately Preceding Statement

Here `FOUND` reflects the `UPDATE` just executed. If additional SQL statements run before `RETURN`, capture `FOUND` or `GET DIAGNOSTICS ... ROW_COUNT` immediately after the target `UPDATE`.

### 35.4. Not a Substitute for Business Authorization

This `SECURITY INVOKER` function performs no tenant or ownership check. Production APIs must enforce scope and permissions (e.g., `tenant_id`, role checks, or RLS). Never deploy this snippet verbatim as a complete payment endpoint.

## 36. Lab: Side Effects and Rollback with an Audit Table

Create an audit logging function:

~~~sql
CREATE FUNCTION fn_cost_lab.record_event(
    p_event_type TEXT,
    p_detail TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_event_id BIGINT;
BEGIN
    INSERT INTO fn_cost_lab.audit_events(
        event_type, detail
    )
    VALUES (p_event_type, p_detail)
    RETURNING event_id INTO v_event_id;

    RETURN v_event_id;
END;
$$;
~~~

### 36.1. Insert and Roll Back

~~~sql
BEGIN;

SELECT fn_cost_lab.record_event(
    'lab_demo',
    'this row should roll back'
) AS generated_id;

SELECT COUNT(*)
FROM fn_cost_lab.audit_events
WHERE event_type = 'lab_demo';

ROLLBACK;
~~~

### 36.2. Verify After Rollback

~~~sql
SELECT COUNT(*)
FROM fn_cost_lab.audit_events
WHERE event_type = 'lab_demo';
~~~

Assuming no prior `lab_demo` rows existed, the count is `0`. However, the sequence generating `event_id` has still advanced despite the rollback.

### 36.3. Do Not Treat Sequence Gaps as Bugs

Sequences naturally develop gaps from rollbacks, caching, failovers, and concurrency. Legal gap-free numbering requires dedicated sequencing workflows and explicit transaction locking.

### 36.4. Name Side-Effecting Functions Clearly

`record_event` clearly communicates a write. Naming a logging function `get_customer_name` while silently inserting rows creates confusing contracts and unsafe retries.

## 37. Lab: Multi-Step Workflow Procedure

Create a procedure to mark an order paid and record an audit event in the same transaction:

~~~sql
CREATE PROCEDURE fn_cost_lab.confirm_order(
    p_order_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE fn_cost_lab.orders
    SET status = 'paid'
    WHERE order_id = p_order_id
      AND status = 'new';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Order % not found or not in new state',
            p_order_id;
    END IF;

    INSERT INTO fn_cost_lab.audit_events(
        event_type, detail
    )
    VALUES ('order_paid', p_order_id::text);
END;
$$;
~~~

### 37.1. Invoke via CALL

~~~sql
BEGIN;

CALL fn_cost_lab.confirm_order(10);

SELECT order_id, status
FROM fn_cost_lab.orders
WHERE order_id = 10;

ROLLBACK;
~~~

Because the procedure does not commit internally, both changes roll back with the caller's transaction.

### 37.2. Why Rely on an Outer Transaction?

In real applications, the service may also need to insert a payment record or update a ledger inside the same atomic transaction. A procedure committing halfway through would destroy that atomicity.

### 37.3. When Is UPDATE ... RETURNING Simpler?

If a workflow only runs a single `UPDATE` and needs to inspect changed columns:

~~~sql
UPDATE fn_cost_lab.orders
SET status = 'paid'
WHERE order_id = 10
  AND status = 'new'
RETURNING order_id, status;
~~~

a plain DML statement is cleaner. **Do not create a stored procedure if a clear DML statement already satisfies the entire contract.**

### 37.4. Design Idempotency Explicitly

If a payment request is retried, the procedure may raise "not in new state" instead of reporting success. Depending on API needs, use an explicit idempotency key and request/ledger table rather than masking already-processed transitions.

## 38. Transaction Control Inside Procedures: Advanced Lab

Run this section only on PostgreSQL 11+ after understanding `CALL` transaction rules.

~~~sql
CREATE PROCEDURE fn_cost_lab.commit_marker(
    p_detail TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO fn_cost_lab.audit_events(
        event_type, detail
    )
    VALUES ('commit_marker', p_detail);

    COMMIT;
END;
$$;
~~~

### 38.1. Top-Level CALL

When invoked outside an explicit transaction block and without violating transaction-control constraints:

~~~sql
CALL fn_cost_lab.commit_marker('top-level call');
~~~

allows the procedure to perform an internal `COMMIT`.

### 38.2. CALL Inside a Transaction Block

~~~sql
-- ERROR ILLUSTRATION: DO NOT EXPECT THIS TO COMMIT CLEANLY
BEGIN;
CALL fn_cost_lab.commit_marker('inside transaction');
COMMIT;
~~~

PostgreSQL normally rejects internal `COMMIT` here because an explicit caller transaction is active. Afterward, run `ROLLBACK` to clear the aborted transaction state.

### 38.3. JDBC autoCommit

When testing top-level `CALL` semantics from Java, check how the JDBC driver manages autocommit and transaction blocks. With `autoCommit = false`, `CALL` typically runs inside a client-opened transaction.

### 38.4. Do Not Combine with SECURITY DEFINER

`SECURITY DEFINER` procedures or those with certain `SET` configuration clauses have transaction-control restrictions. Never combine them without consulting PostgreSQL documentation for your version.

### 38.5. Contracts Must Clearly State Transaction Ownership

A procedure that executes `COMMIT` internally behaves fundamentally differently from one participating in the caller's transaction. Callers must know which contract applies before calling.

## 39. Reading EXPLAIN Properly When Functions Are Involved

Given a query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    c.customer_id,
    fn_cost_lab.paid_order_count_pl(c.customer_id)
FROM fn_cost_lab.customers AS c
WHERE c.customer_id <= 500;
~~~

### 39.1. The Outer Plan Hides Internal Function Work

PL/pgSQL SQL statements run via SPI and do not appear as child plan nodes in the outer `EXPLAIN` output. Additional instrumentation is required to observe nested SQL execution totals.

### 39.2. Estimated vs. Actual Rows

If the planner expects `10` rows yet actual execution produces one million, check statistics, selectivity, or `ROWS` annotations on set-returning functions rather than trusting raw cost numbers.

### 39.3. Buffers

`BUFFERS` reports shared hits/reads and buffer activity, though nested SQL executed inside procedural functions can obscure full resource attribution compared to a single set-based query.

### 39.4. Planning Time vs. Execution Time

Dynamic SQL, repeated invocations, and complex queries shift work across planning and execution phases. Do not confuse the outer query's `Planning Time` with total planning spent across nested internal statements.

### 39.5. EXPLAIN ANALYZE Executes DML

Running `EXPLAIN ANALYZE` on an `UPDATE` or a function/procedure wrapper with side effects actually executes those writes. Always wrap test runs in a rolled-back transaction or run in a sandbox; never treat `EXPLAIN ANALYZE` as a dry run.

## 40. Monitoring Functions Using PostgreSQL Statistics

### 40.1. pg_stat_user_functions

When `track_functions` is enabled for the relevant function types, `pg_stat_user_functions` reports `calls`, `total_time`, and `self_time` per user function.

~~~sql
SELECT
    schemaname,
    funcname,
    calls,
    total_time,
    self_time
FROM pg_stat_user_functions
WHERE schemaname = 'fn_cost_lab'
ORDER BY total_time DESC;
~~~

### 40.2. track_functions

Options typically include `none`, `pl`, and `all` depending on PostgreSQL configuration and privileges. Evaluate overhead and monitoring policies before enabling broad instrumentation in production.

### 40.3. Self Time vs. Total Time

`self_time` and `total_time` account differently for nested calls. Do not treat partial tracking (such as `pl` only) as complete CPU accounting for all functions in the database.

### 40.4. Inlined Functions May Not Appear as Discrete Calls

When an SQL function is inlined by the planner, per-function call counters will not increment as they would for non-inlined calls. Always interpret statistics alongside query plans.

### 40.5. pg_stat_statements

The `pg_stat_statements` extension, when installed and configured, tracks aggregate SQL execution counts and timings. Nested-statement visibility depends on settings such as `pg_stat_statements.track` and statement types.

### 40.6. auto_explain

`auto_explain` can log execution plans automatically, including nested statements when configured (`auto_explain.log_nested_statements`). Manage overhead and log volume carefully when enabling it.

## 41. Dynamic SQL in PL/pgSQL

PL/pgSQL supports dynamic execution:

~~~sql
EXECUTE dynamic_sql_text
USING parameter_value;
~~~

### 41.1. When Is It Useful?

- Table or schema names must be chosen dynamically against a strict whitelist.
- Query predicate/clause structure genuinely varies at runtime.
- Value-specific custom plans are needed where static cached plans perform poorly.

### 41.2. Cost

Dynamic `EXECUTE` generally bypasses static PL/pgSQL statement plan caching, requiring parsing and planning on every execution.

### 41.3. SQL Injection Prevention

Never concatenate raw user input into SQL strings. Use `format('%I', identifier)` after strict allowlist validation for identifiers, `USING` parameters for values, and explicit object allowlists.

### 41.4. Do Not Use EXECUTE for Fixed SQL

Static SQL inside PL/pgSQL is cleaner and benefits from plan caching. Wrapping an unchanging query inside `EXECUTE 'SELECT ...'` adds complexity and unnecessary planning overhead.

### 41.5. Privileges and search_path

Dynamic SQL inside `SECURITY DEFINER` routines is especially security-sensitive. Control identifiers, `search_path`, and caller inputs tightly; parameterizing values alone does not protect against arbitrary caller-supplied table names.

## 42. Comparing Database Logic vs. Java/Service Logic

| Criterion | Logic in PostgreSQL | Logic in Java / Service |
|---|---|---|
| Data locality | Co-located with tables/indexes; avoids shipping raw rows | May require fetching large datasets over the network |
| Set-based SQL | Planner optimizes directly over row sets | Must still send SQL to DB for set-based work |
| Transactions | Naturally integrated with single-cluster DML | Coordinates transactions across JDBC boundaries |
| Compute scaling | Consumes centralized, expensive primary DB CPU/RAM | Service instances scale horizontally with ease |
| Versioning | Schema migrations and DB privilege management | Application CI/CD and rolling deployments |
| Portability | Coupled to PostgreSQL / PL/pgSQL | Less coupled to specific database dialect |
| Observability | Requires SQL and function monitoring | Mature app tracing and CPU profiling |
| Security | `EXECUTE`, `DEFINER`/`INVOKER`, RLS | AuthN/AuthZ and service-layer boundaries |
| External APIs | Unsuitable inside open DB transactions | Handles network clients, timeouts, retries cleanly |
| Business consistency | Strong DB constraints and transactions | Must rely on DB constraints/transactions properly |
| Testability | Needs integration DB fixtures/migrations | Fast unit tests and mocks |
| Reusability | Shared SQL contract across diverse DB clients | Shared libraries and HTTP/gRPC APIs across services |

### 42.1. It Is Rarely an All-or-Nothing Choice

Clean architectures divide responsibilities thoughtfully:

- The database enforces core invariants and executes set-based data processing.
- Java handles orchestration, API/UI validation, external integrations, and cross-service workflows.
- Functions/procedures encapsulate reusable or atomic in-DB data operations.
- Outbox/workers handle external side effects asynchronously.

### 42.2. Avoid Duplicating Business Rules

Implementing tax calculation separately in both Java and PL/pgSQL invites silent drift. Designate a single **source of truth** for each rule and enforce alignment with contract tests.

## 43. Criteria for Placing Logic in the Database: Data Locality

Database placement works well when:

- Many rows must be processed without streaming them to the application tier.
- Logic maps cleanly to one or a few set-based SQL statements.
- Operations require atomic execution within a single PostgreSQL cluster.
- Multiple diverse clients share the same validation or transformation.
- A stable SQL contract can be maintained.
- Table access must be restricted behind narrow function APIs and grants.

### 43.1. Good Example: Aggregation via GROUP BY

Compute per-customer totals inside PostgreSQL; avoid fetching every order row into Java merely to sum amounts when SQL aggregates do it efficiently.

### 43.2. Good Example: Atomic State Transition

`UPDATE ... WHERE status = 'new' RETURNING ...` belongs in the database because concurrency and transactional atomicity matter.

### 43.3. Potentially Good Example: Bulk Normalization

An `UPDATE ... FROM` or `INSERT ... SELECT` normalizing thousands of rows runs cleanly in the database without round-tripping every row through Java.

### 43.4. Not All Validation Belongs in Stored Functions

Input-format checks, user-facing validation messages, and cross-service orchestration usually fit better in Java, while critical data invariants remain guarded by database constraints and transactions.

## 44. Criteria for Keeping Logic in Application Services

Logic generally belongs outside the database when it involves:

1. Calling external HTTP/gRPC third-party APIs.
2. Sending emails, webhooks, or push notifications.
3. Processing files, PDFs, media, or object storage.
4. CPU-intensive math independent of DB I/O that benefits from independent scaling.
5. Rapidly changing business rules requiring traffic-split A/B rollouts.
6. Distributed workflows across multiple systems needing sagas and idempotency.
7. Workloads requiring specialized Java libraries or GPU/ML runtimes.
8. Presentation logic, localization, or client-specific formatting.
9. Flows requiring external retries, timeouts, and rate limiting.
10. Computations that do not require PostgreSQL transaction atomicity.

### 44.1. Never Hold Database Transactions Open Over Network Calls

Holding a transaction open while waiting seconds for an HTTP response keeps locks, snapshots, and backend slots occupied, worsening contention and autovacuum bloat. Persist intent to an outbox table and call external services outside the transaction.

### 44.2. Scaling Out Compute

Application tiers scale horizontally by adding replicas, whereas a PostgreSQL primary is a centralized bottleneck. Offloading non-data-intensive CPU work preserves database capacity for core I/O queries.

### 44.3. Versioning and Rollbacks

Rules changing multiple times a day are far easier to roll out and roll back in Java services than via database function migrations, provided data invariants stay protected by schemas and constraints.

## 45. Criteria for Encapsulating Logic in a Function or Procedure

Choose a function or procedure when one or more clear benefits apply:

- **Reusability**: multiple queries or clients invoke identical logic.
- **Atomicity**: multiple DML statements on the same cluster must commit together.
- **Reduced round trips**: eliminates chatty sequences of small queries.
- **Data access control**: grants narrow capabilities instead of direct table access.
- **Data locality**: transforms or aggregates data right where it lives.
- **Set-oriented SQL**: pure SQL functions that stay concise and potentially inline.
- **Stable interface**: versioned DB contract with clear ownership.
- **Operational discipline**: existing migration, testing, and monitoring pipelines cover DB objects.

### 45.1. When to Skip Creating a Function

If a function merely wraps a trivial single-use `SELECT` with no security, reuse, or API benefit, the extra indirection rarely pays off.

### 45.2. Multi-Step Procedural Logic

PL/pgSQL helps when combining conditional checks, multi-table updates, and controlled exception handling. Even then, **write set-based DML inside** (`UPDATE ... FROM`) instead of `FOR row IN SELECT LOOP UPDATE ... END LOOP`.

### 45.3. Judge by Overall System Quality

Execution speed, correctness, security, observability, deployability, and team maintainability all matter — never optimize solely for raw microbenchmark time.

## 46. Example Decision Matrix

| Problem | First Option to Evaluate | Reason |
|---|---|---|
| Multiply `amount * 1.1` across 10M rows | Inline SQL expression or pure SQL function | Set-based, eligible for inlining |
| Count paid orders across 1,000 customers | `JOIN` / `GROUP BY` | Eliminates per-row SQL lookups |
| Enforce `quantity >= 0` | `CHECK` constraint | Universal row invariant |
| Enforce unique SKU | `UNIQUE` constraint | Concurrency-safe uniqueness |
| Transition order `new` -> `paid` | Conditional `UPDATE` (or function/procedure API) | Atomic conditional state change |
| Persist order + outbox atomically | Transaction / DML + outbox insert | Single-transaction atomicity |
| Send payment confirmation email | Outbox + external worker | External I/O and safe retries |
| Heavy ML scoring | Dedicated service or evaluated extension | Scales compute independently |
| Multi-transaction admin batch | Service orchestrator or controlled `CALL` procedure | Explicit transaction boundaries |
| Lookup configuration table in function | `STABLE` function | Cannot safely be marked `IMMUTABLE` |
| Random ID / sequence increment | `VOLATILE` semantics | Stateful / non-deterministic output |
| Validate JSON/UI request payload | Java / application service | Close to API layer, rapid iteration |
| Restricted write capability for callers | Hardened `SECURITY DEFINER` function | Least-privilege narrow capability |
| Cross-table summary reports | SQL query / view / materialized view by freshness | Planner optimization & data locality |

## 47. Versioning Stored Functions and API Contracts

A stored function signature is a public contract:

~~~sql
SELECT fn_cost_lab.discounted_amount(100, 0.10);
~~~

Callers may depend on:

- Schema and function name.
- Parameter count and parameter types.
- Default arguments and parameter names (for named notation).
- Return type and `RETURNS TABLE` column names.
- Volatility and side-effect behavior.
- Raised exceptions and `SQLSTATE` codes.
- Required `EXECUTE` grants.
- Transaction ownership expectations.
- Runtime latency and resource characteristics.

### 47.1. Limits of CREATE OR REPLACE FUNCTION

PostgreSQL forbids arbitrarily changing the return type of an existing function via `CREATE OR REPLACE FUNCTION`; introducing a new signature/version or `DROP` + `CREATE` (with dependency and privilege impact) is required.

### 47.2. Semantic Changes Without Signature Changes Can Still Break Clients

If `calculate_total` switches from pre-tax to post-tax while still returning `NUMERIC`, callers silently compute wrong totals. Maintain strict versioning and contract tests.

### 47.3. Overloading Can Trigger Ambiguous Resolution

Defining overloads differing subtly across `numeric`, `integer`, or `unknown` literals can make calls with `NULL` or uncast string literals fail or resolve unexpectedly. Use explicit casts and distinct versioned names when contracts diverge.

### 47.4. Signal Side Effects in Function Names

Names like `get_...` or `calculate_...` should promise no data mutations. Names like `record_...`, `mark_...`, or `confirm_...` clearly indicate command semantics requiring privilege and idempotency checks.

### 47.5. JDBC Return-Shape Verification

JDBC code mapping `RETURNS TABLE` or composite results depends on exact column names and types. Altering output shapes breaks client mappers even when SQL DDL executes cleanly.

## 48. Deploying and Rolling Back Functions and Procedures

### 48.1. Database Migrations Are Code Deployments

Store function and procedure sources under version control, require code review, test in staging, and validate against the exact target PostgreSQL version.

### 48.2. Expand–Contract for Database APIs

Standard rollout sequence:

1. Create function v2.
2. Keep v1 active for older application instances.
3. Roll out Java callers to v2 in stages.
4. Monitor v1 and v2 invocation metrics.
5. Confirm zero active callers remain on v1.
6. `REVOKE` and `DROP` v1 only when confirmed safe.

### 48.3. Never Use DROP CASCADE Recklessly

Views, triggers, other routines, or external applications may depend on a function. `CASCADE` can silently destroy database objects, while application SQL references do not even appear in catalog dependencies.

### 48.4. Re-Verify Privileges After Changes

`CREATE OR REPLACE FUNCTION` and `DROP`/`CREATE` treat object OIDs, ownership, and ACLs differently. Always verify effective grants after modifying routines rather than assuming only the body changed.

### 48.5. Locks and Transaction Disruption

DDL altering functions, ownership, or privileges can contend with active queries and cached plans. Always follow structured migration and rollback plans rather than running ad-hoc production scripts.

## 49. Meaningful Benchmarks: Measure Both Reads and Writes

A fair benchmark comparing SQL and PL/pgSQL implementations requires:

1. Identical dataset.
2. Identical query semantics.
3. Identical input row count.
4. Identical output columns and aggregations.
5. Consistent key PostgreSQL configuration settings.
6. Multiple warm runs to stabilize cache effects.
7. Observing both planning and execution times.
8. Inspecting `BUFFERS` counts.
9. Recording function call statistics when instrumented.
10. Measuring both throughput and p95/p99 latency.
11. Tracking CPU, I/O, WAL volume, and locks for DML workloads.
12. Separating pure CPU math from nested SQL lookups.
13. Avoiding hacks like `SET enable_seqscan = off` as production tuning.
14. Never treating `EXPLAIN` estimated cost units as milliseconds.
15. Never committing accidental test mutations during live DML benchmarks.

### 49.1. Benchmarks Without Identical Semantics Are Meaningless

If a PL/pgSQL tax calculation rounds differently from an SQL expression, functional bugs overshadow speed differences. Align precision and rounding rules first.

### 49.2. LIMIT Does Not Eliminate All Function Work

A query with `ORDER BY expensive_function(...) LIMIT 20` may still evaluate the function across huge numbers of candidate rows before selecting the top 20.

### 49.3. Account for Network Overhead

A Java loop issuing 1,000 sequential JDBC queries pays steep network latency; consolidating them into one set-based SQL query eliminates round trips and unlocks planner optimization.

### 49.4. Optimize the Real Bottleneck Tier

If 99% of request time is spent calling a remote third-party API, moving an arithmetic formula from Java into an SQL function achieves nothing. Profile end-to-end first.

## 50. Common Mistakes

### 50.1. "Stored functions are always faster than Java"

**False.** Database code gains data locality and single-transaction efficiency, yet adds invocation overhead and consumes primary database CPU.

### 50.2. "A function in SELECT executes only once"

**False in general.** It may be evaluated per row depending on the query plan and optimizer behavior.

### 50.3. "PL/pgSQL is just SQL, so it will inline"

**False.** Inlining applies to eligible `LANGUAGE SQL` functions, not PL/pgSQL procedural blocks.

### 50.4. "Every LANGUAGE SQL function gets inlined"

**False.** Planner rules and structural restrictions prevent inlining in many cases.

### 50.5. "Plan caching turns 1,000 internal SELECTs into a JOIN"

**False.** Reusing a single-row plan still executes 1,000 separate lookups rather than set-based execution.

### 50.6. "If an index exists, per-row function calls cannot be slow"

**False.** Thousands or millions of repeated index probes still add up to heavy cumulative work.

### 50.7. "Use LOOP because it is easier to write than GROUP BY"

Avoid as a default. Set-based SQL nearly always deserves to be tried first at scale.

### 50.8. "IMMUTABLE makes functions faster, so label everything IMMUTABLE"

**False and dangerous.** Mislabeling can yield stale results and broken index behavior.

### 50.9. "STABLE permits all DML because it reads a single snapshot"

**False.** `STABLE` and `IMMUTABLE` prohibit database-modifying statements.

### 50.10. "VOLATILE allows a function to COMMIT on its own"

**False.** Volatility never alters transaction boundaries.

### 50.11. "Rolling back a function rolls back sequences too"

**False.** Sequence state advances independently of transaction rollback.

### 50.12. "HTTP calls inside functions roll back with the transaction"

**False.** External side effects cannot be rolled back by PostgreSQL.

### 50.13. "COST 100 means 100 milliseconds"

**False.** `COST` is an abstract planner cost estimate, not wall-clock time.

### 50.14. "ROWS 50 caps the function output at 50 rows"

**False.** `ROWS` is a cardinality estimate, not a `LIMIT`.

### 50.15. "PARALLEL SAFE forces every query to run in parallel"

**False.** It merely allows parallelism when the planner determines it is beneficial and permitted.

### 50.16. "Marking sequence-calling functions PARALLEL SAFE makes them faster"

**False and unsafe.** Sequence mutations inside parallel workers violate safety restrictions.

### 50.17. "Catching WHEN OTHERS and returning FALSE is always safe"

**No.** It silently masks severe failures like deadlocks or permission errors.

### 50.18. "An EXCEPTION block costs nothing if no error happens"

**False by default.** Subtransaction entry/exit carries overhead even on clean execution.

### 50.19. "SELECT queries cannot write data"

**False if invoking a `VOLATILE` function executing DML** where permitted.

### 50.20. "LIMIT guarantees a logging function runs exactly N times"

**Do not rely on it** unless an execution contract specifically guarantees evaluation count.

### 50.21. "Procedures can COMMIT inside any CALL"

**False.** Transaction control inside procedures only works under supported invocation contexts.

### 50.22. "JDBC autoCommit=false still allows independent procedure COMMITs"

**Not by default.** The driver typically places `CALL` inside an active client transaction.

### 50.23. "SECURITY DEFINER is always safer than SECURITY INVOKER"

**False.** It elevates execution privileges and becomes an attack surface unless `search_path`, permissions, and inputs are properly hardened.

### 50.24. "Default EXECUTE granted to PUBLIC does not matter"

**False for write-capable or privileged functions.** Always lock down `EXECUTE` grants intentionally.

### 50.25. "RLS applies identically regardless of function owner"

**Not guaranteed.** Ownership, `SECURITY DEFINER`, and `BYPASSRLS` semantics alter policy enforcement.

### 50.26. "Check uniqueness with a SELECT COUNT function instead of UNIQUE"

**False.** Application/function pre-checks suffer race conditions under concurrency.

### 50.27. "An outbox automatically guarantees exactly-once delivery outside the DB"

**False.** Workers retry on failure, so consumers must implement idempotency.

### 50.28. "Using dynamic EXECUTE for every query is both more flexible and faster"

**Generally false.** Dynamic `EXECUTE` incurs per-call planning cost and SQL injection risk.

### 50.29. "Outer EXPLAIN prints every nested PL/pgSQL query"

**Not by default.** Nested queries require additional instrumentation such as `auto_explain`.

### 50.30. "One benchmark run settles performance forever"

**False.** Validate across representative data, warm caches, read/write mixes, and realistic concurrency.

## 51. Hands-On Exercises

### Exercise 1 — Function or Procedure?

You need to compute price after tax inside a `SELECT` list. Which PostgreSQL object fits better?

**Hint:** A scalar-returning function, ideally `LANGUAGE SQL` with accurate volatility.

### Exercise 2 — Per-Row Function Calls

A query returning 800,000 rows calls a PL/pgSQL function in its `SELECT` list. What should you measure?

**Hint:** Actual invocation count, call boundary overhead, and work executed inside each call.

### Exercise 3 — Round Trips

Java executes 1,000 sequential `SELECT` statements over JDBC. Why is a single set-based query often faster?

**Hint:** Eliminates network round trips and allows the planner to optimize across the entire set.

### Exercise 4 — SQL Inlining

Are all `LANGUAGE SQL` functions inlined?

**Answer:** No; eligibility depends on structure, attributes, and planner constraints.

### Exercise 5 — PL/pgSQL

Can a PL/pgSQL function be treated as an always-inlined SQL expression?

**Answer:** No.

### Exercise 6 — Hidden N+1

What can `SELECT c.id, count_orders(c.id) FROM customers c` hide?

**Hint:** An internal SQL query executing separately for each `c.id`.

### Exercise 7 — Set-Based Rewrite

Write a `GROUP BY` query counting paid orders per customer.

**Hint:** Use `LEFT JOIN` with `status = 'paid'` in the `ON` condition and `COUNT(order_id)`.

### Exercise 8 — COUNT with LEFT JOIN

Why can `COUNT(*)` return `1` for a customer with zero orders?

**Answer:** `LEFT JOIN` preserves one null-extended row for the unmatched customer.

### Exercise 9 — IMMUTABLE

What volatility applies to `square(numeric)` if it only multiplies its input by itself?

**Hint:** `IMMUTABLE`, as it depends on no external state.

### Exercise 10 — STABLE

Should a function reading an exchange-rate table be marked `IMMUTABLE`?

**Answer:** No, if rates can change; evaluate `STABLE` (or `VOLATILE`) based on required semantics.

### Exercise 11 — VOLATILE

What volatility does `random()` have?

**Answer:** `VOLATILE`.

### Exercise 12 — Time Functions

Do `clock_timestamp()` and `now()` share the same volatility?

**Answer:** No.

### Exercise 13 — INSERT Function

What volatility should a function inserting audit rows declare?

**Hint:** `VOLATILE`.

### Exercise 14 — Function COMMIT

Can a function called from `SELECT` run `COMMIT` independently?

**Answer:** No.

### Exercise 15 — Procedure COMMIT

Can a procedure invoked via `CALL` inside an explicit transaction block freely run internal `COMMIT`?

**Answer:** No; transaction control is restricted inside explicit caller transactions.

### Exercise 16 — JDBC

Why must you check `autoCommit` before calling a transaction-controlling procedure from JDBC?

**Hint:** The driver controls whether `CALL` starts inside an implicit or explicit transaction context.

### Exercise 17 — Sequence Rollback

Can an identity/sequence ID still skip numbers after a `ROLLBACK`?

**Answer:** Yes.

### Exercise 18 — External Side Effects

Does rolling back an `INSERT` automatically roll back an email sent via an external API inside the same function?

**Answer:** Not automatically.

### Exercise 19 — Outbox

What atomicity guarantee does the outbox pattern provide?

**Hint:** Updating business state and recording the event intent atomically inside one database transaction.

### Exercise 20 — Exactly-Once Delivery

Does a retrying outbox worker still require idempotent consumers?

**Answer:** Yes.

### Exercise 21 — COST

Does `COST 100` mean 100 ms per invocation?

**Answer:** No; it represents abstract planner cost units.

### Exercise 22 — ROWS

Does `ROWS 100` truncate a function's output at 100 rows?

**Answer:** No.

### Exercise 23 — PARALLEL SAFE

Should a function calling a sequence be labeled `PARALLEL SAFE` to speed up queries?

**Answer:** No.

### Exercise 24 — STRICT

Should a function that treats `NULL` input as `0` be declared `STRICT`?

**Hint:** No, if the body must inspect and handle `NULL` values explicitly.

### Exercise 25 — EXCEPTION

What overhead can a PL/pgSQL `EXCEPTION` block introduce?

**Hint:** Subtransaction management overhead.

### Exercise 26 — Constraints

Why prefer a `UNIQUE` constraint over checking `SELECT COUNT` before `INSERT`?

**Hint:** Prevents concurrency race conditions.

### Exercise 27 — Foreign Keys

Why cannot an application-level pre-check replace a `FOREIGN KEY`?

**Hint:** Concurrent deletes or updates can invalidate the check before the insert commits.

### Exercise 28 — Triggers

How many times can a `FOR EACH ROW` trigger execute on a one-million-row `INSERT`?

**Hint:** Approximately one million times under row-trigger firing semantics.

### Exercise 29 — SQL UPDATE

Should a one-million-row update always loop row-by-row with `FOR LOOP UPDATE`?

**Answer:** No; prefer a set-based `UPDATE`.

### Exercise 30 — SECURITY DEFINER

Why is a safe `SET search_path` critical on `SECURITY DEFINER` routines?

**Hint:** Prevents name resolution hijacking via untrusted schemas.

### Exercise 31 — Privileges

Because new functions normally default to granting `EXECUTE` to `PUBLIC`, what should you do for sensitive functions?

**Hint:** `REVOKE` from `PUBLIC` and `GRANT` intentionally, ideally in the same transaction that creates the function.

### Exercise 32 — RLS

Does passing tests as a superuser prove a function is safe under an application role?

**Answer:** No.

### Exercise 33 — EXPLAIN

Does an outer query's `EXPLAIN` always display every nested `SELECT` inside PL/pgSQL?

**Answer:** No.

### Exercise 34 — pg_stat_user_functions

Which setting must be configured to collect function call counts and timings?

**Hint:** Configure `track_functions` appropriately.

### Exercise 35 — Dynamic SQL

Why can `EXECUTE` on dynamic SQL cost more than static PL/pgSQL statements?

**Hint:** Repeated parsing/planning plus string construction and SQL-injection validation costs.

### Exercise 36 — pg_stat_statements

What configuration determines whether nested statements are tracked?

**Hint:** `pg_stat_statements.track` and related tracking scope settings.

### Exercise 37 — Java vs. Database

Should post-payment webhook delivery happen inside a database transaction function or outside the DB?

**Hint:** Outside the DB via an outbox and worker for cleaner retry and timeout handling.

### Exercise 38 — API Contract

Can changing a function return type from `numeric` to `text` break Java clients?

**Answer:** Yes; the return type is part of the API contract.

### Exercise 39 — Versioning

If older application instances still call v1, should you drop v1 immediately after creating v2?

**Answer:** No; migrate all consumers and verify first.

### Exercise 40 — Architecture Design

A SaaS platform handles 2 million orders/day, requiring `quantity >= 0` checks, payment state transitions, audit logging, and confirmation emails. Split responsibilities between DB and services.

**Hint:** `CHECK`/PK/FK constraints for invariants, atomic conditional `UPDATE` for state transitions, audit + outbox writes in the same transaction, asynchronous email worker after commit, and Java service orchestration with retry/idempotency.

### Exercise 41 — Benchmarking

Two implementations (SQL vs. PL/pgSQL) of a tax calculation show different plans and latencies. Name five variables that must remain constant in a valid benchmark.

**Hint:** Dataset, query semantics, row count, PostgreSQL configuration, cache warm-up state, and output shape.

### Exercise 42 — Planner

An SQL function has a high `COST` attribute but gets inlined. Should you assume the planner charges that full opaque `COST`?

**Answer:** No.

### Exercise 43 — DML Return Status

In `mark_order_paid`, what does `FOUND` indicate right after the `UPDATE`?

**Hint:** Whether the preceding `UPDATE` matched/affected at least one row per PL/pgSQL semantics.

### Exercise 44 — Transaction API

Is a procedure that commits internally suitable when the caller needs to combine it with three other steps in one atomic transaction?

**Answer:** Generally no; transaction ownership must be designed clearly.

### Exercise 45 — Complete Classification

Given a pure discount formula function, a discount-table lookup function, and a function calling an external recommendation API, classify their volatility and placement.

**Hint:** Pure math as `IMMUTABLE`; table lookup as `STABLE` when snapshot semantics fit; external API calls belong in application services/workers and must never be marked `IMMUTABLE`.

## 52. Pre-Database Logic Checklist

### 52.1. Algorithms and Performance

- Can the logic be expressed as set-based SQL?
- How many times per request will the function run?
- Does it execute nested `SELECT` queries per row?
- Can a `LANGUAGE SQL` function be inlined?
- Is PL/pgSQL genuinely required for branching or error handling?
- Does moving logic reduce network round trips without introducing row-by-row SQL overhead?
- Do representative benchmark results exist?
- Have p95/p99 latencies as well as write, lock, and WAL impact been measured?

### 52.2. Correctness

- Is `IMMUTABLE`/`STABLE`/`VOLATILE` classified accurately?
- Are `NULL` and `STRICT` semantics exact?
- Could declarative constraints replace procedural checks?
- Are race conditions handled via conditional updates, `UNIQUE`/FK constraints, or proper locks?
- Which side effects do not roll back?
- Are idempotency and retry semantics defined?
- Is transaction ownership (caller vs. procedure) explicit?
- Are any hidden side effects triggered by `SELECT` or triggers?

### 52.3. Planner

- Are `COST` and `ROWS` estimates realistic?
- Does `PARALLEL SAFE`/`RESTRICTED`/`UNSAFE` match actual behavior?
- Have execution plans been inspected with `EXPLAIN`?
- Does an opaque function hide joins or filters from the planner?
- Does dynamic SQL cause excessive re-parsing/re-planning?
- Are base table indexes and statistics up to date?

### 52.4. Security

- `SECURITY INVOKER` or `SECURITY DEFINER`?
- Does the function owner hold only least privileges?
- Is `search_path` pinned strictly to trusted schemas?
- Are important objects schema-qualified?
- Has `EXECUTE` been revoked from `PUBLIC` where needed?
- Have tenant isolation, RLS, and authorization been tested under the application role?
- Are inputs validated and dynamic SQL protected against injection?

### 52.5. Operations

- Are stored routines under migration and version control?
- Can v2 be deployed alongside v1?
- Is there a rollback plan if outputs or semantics change?
- Are callers, contracts, and side effects documented?
- Is monitoring tracking function calls, duration, locks, and errors?
- Can database CPU handle added computational load?
- Are external effects routed via outbox/workers rather than open DB transactions?
- Is long-term ownership assigned for maintaining functions and procedures?

## 53. Quick Reference

| Concept | Key Takeaway |
|---|---|
| `CREATE FUNCTION` | Routine usable inside SQL expressions |
| `CREATE PROCEDURE` | Routine invoked via `CALL` |
| `LANGUAGE SQL` | Eligible for planner inlining when conditions hold |
| `LANGUAGE plpgsql` | Procedural logic running in PL/pgSQL runtime |
| Per-row function call | High invocation counts across large result sets |
| Hidden N+1 in DB | Function executing repeated internal SQL per row |
| Set-based SQL | `JOIN`, `GROUP BY`, `UPDATE ... FROM`, `INSERT ... SELECT` |
| Inlining | Planner merges SQL function body into outer query when eligible |
| Static SQL in PL/pgSQL | Eligible for plan caching/reuse |
| Dynamic `EXECUTE` | Dynamic SQL, typically re-planned per execution |
| `IMMUTABLE` | Output invariant for identical arguments |
| `STABLE` | Consistent under statement snapshot semantics |
| `VOLATILE` | Can change across calls or perform DML/side effects |
| `STRICT` | `NULL` argument yields `NULL` without invoking body |
| `COST` | Planner heuristic unit, not wall-clock latency |
| `ROWS` | Estimated row cardinality for set-returning functions |
| `PARALLEL SAFE` | Eligible to run in parallel workers when genuinely safe |
| `PARALLEL RESTRICTED` | Restricted to parallel leader process |
| `PARALLEL UNSAFE` | Disallows parallel plan execution |
| Function transactions | Cannot `COMMIT`/`ROLLBACK` caller transaction |
| Procedure transactions | May `COMMIT` under valid top-level `CALL`/`DO` rules |
| `EXCEPTION` | Adds subtransaction overhead |
| Sequences | `nextval` does not roll back with table rows |
| DML side effect | Table mutation inside transaction |
| External side effect | Cannot roll back with PostgreSQL transaction |
| Transactional outbox | Records event intent atomically alongside business state |
| Idempotency | Safe retries without duplicate business effects |
| `SECURITY INVOKER` | Runs with caller's privileges |
| `SECURITY DEFINER` | Runs with owner's privileges; requires hardening |
| `search_path` | Exclude untrusted schemas in `SECURITY DEFINER` |
| `GRANT EXECUTE` | Governs permission to invoke routine |
| RLS | Enforces row-level visibility policies |
| Trigger function | Executes automatically on table DML events |
| `EXPLAIN (ANALYZE, BUFFERS)` | Inspects actual execution plan and buffer usage |
| `track_functions` | Enables function execution statistics collection |
| `pg_stat_user_functions` | Reports `calls`, `total_time`, and `self_time` |
| `pg_stat_statements` | Tracks aggregate query stats when configured |
| `auto_explain` | Logs slow plans automatically, including nested SQL if enabled |
| DB API versioning | Introduce v2, migrate callers, retire v1 afterward |
| Decision boundary | Correctness, locality, scale, observability, maintainability |

---

## Conclusion

**There is no universal rule that "placing logic in PostgreSQL is always faster" or "PostgreSQL functions are always slow".** Real cost depends on call frequency, internal work, implementation language, SQL inlining eligibility, the query planner, network round trips, and whether queries operate on sets. For simple calculations over millions of rows, inline SQL expressions or pure SQL functions work very well. For multi-step workflows requiring atomicity, PL/pgSQL functions or procedures can reduce round trips and centralize invariants. For counting orders per customer, a `JOIN`/`GROUP BY` query almost always deserves benchmarking before accepting nested per-row queries.

**Volatility and side effects are correctness contracts, not speed flags.** Mark functions `IMMUTABLE` only when outputs depend strictly on arguments; use `STABLE` for snapshot-consistent reads; and use `VOLATILE` for time-varying values or DML. `COST`, `ROWS`, and `PARALLEL` guide optimizer assumptions — mislabeling them produces bad plans or broken semantics. Functions cannot commit independently, procedures support transaction control only under restricted contexts, and PostgreSQL rollbacks never undo sequences or external network side effects.

**Place logic inside the database when it genuinely benefits from data locality, set-based execution, transactional atomicity, constraints, and controlled access.** Keep cross-system orchestration, HTTP/email/webhooks, UI formatting, and independently scalable CPU workloads in application services or workers; bridge PostgreSQL commits to external events via transactional outboxes and idempotency. Before deciding, establish the single source of truth for each business rule, measure with `EXPLAIN` and function statistics, test privileges/transactions/retries under real roles, and plan versioning and rollback for every database API.

A practical guiding principle: **prefer set-based SQL and declarative constraints for correctness; use functions and procedures to expose clean contracts and encapsulate atomic operations where truly needed; and never hide critical side effects inside unpredictable call sites.**
