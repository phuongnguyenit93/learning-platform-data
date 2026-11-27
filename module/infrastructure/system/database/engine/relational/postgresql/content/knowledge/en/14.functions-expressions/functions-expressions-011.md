# IMMUTABLE, STABLE, VOLATILE, and Their Impact on Query Optimization in PostgreSQL

When creating a user-defined function (UDF) in PostgreSQL, you can declare one of three **volatility** categories: `IMMUTABLE`, `STABLE`, or `VOLATILE`. This is not just a descriptive label. It is a **contract with the query optimizer (query planner)** stating how much a function's return value can vary, which directly shapes how PostgreSQL evaluates expressions, plans queries, and uses indexes.

Examples:

- Computing `price * (1 - discount_rate)` depends solely on two numeric arguments: a candidate for `IMMUTABLE`.
- Looking up a customer's tier from a table: the data can change between statements yet is read consistently within a single statement: typically suited for `STABLE`.
- Calling `random()`, `clock_timestamp()`, `nextval()`, or modifying data: requires `VOLATILE`.

An overly conservative declaration—for instance marking a pure mathematical calculation as `VOLATILE`—can cause PostgreSQL to miss optimization opportunities. Worse still, **overstating stability**—such as marking a function that reads a frequently updated table as `IMMUTABLE`—can cause the planner to reuse stale values, especially with prepared statements and cached plans.

This lesson moves from definitions and runnable PostgreSQL SQL examples to the effects of volatility on **constant folding**, index scan conditions, **expression indexes**, **partial indexes**, generated columns, snapshots inside functions, transactions, and plan caching.

## 1. Volatility Is a Promise About Result Variability

Imagine PostgreSQL encounters the expression:

~~~sql
SELECT my_function(10);
~~~

The planner needs to know:

- Can it **precompute the expression during planning**?
- If a query scans one million rows, can it **evaluate once and reuse** or must it keep the ability to evaluate per row?
- Can the function result be used in comparison conditions against a **B-tree index**?
- Can the function result be stored as part of an index key or a generated column?
- Can the function observe data changing while the outer statement executes?

The three volatility levels provide distinct guarantees.

| Category | Guarantee about results | Can modify database inside function? | Primary impact on the planner |
| --- | --- | --- | --- |
| **`IMMUTABLE`** | Identical arguments always yield the same result, independent of time and database/session state | No | Can be precomputed when arguments are constants; valid in expression indexes |
| **`STABLE`** | Identical arguments yield the same result within the scope of **a single statement** | No | Can be treated as constant within a statement; eligible for many index scan conditions |
| **`VOLATILE`** | Results can vary between calls, even within the same statement; function may have side effects | Yes, if privileges and language permit | Cannot assume an invariant value; restricts precomputation and call hoisting |

This is a **contractual classification of the function**, not something PostgreSQL infers automatically after observing a few calls. When declaring a function, the author is responsible for selecting a level matching every behavior the function performs.

### How important is "identical arguments"?

Suppose `f(10)` is called repeatedly:

- `IMMUTABLE`: the result must not depend on current time, table data, session settings, or any mutable external state.
- `STABLE`: may depend on data read or values fixed for the statement; subsequent statements may observe different results.
- `VOLATILE`: each evaluation may return a different value, or perform data writes.

If a zero-argument function returns the current wall-clock time, by nature it **cannot be IMMUTABLE** merely because its signature takes no parameters.

## 2. The Three Categories Are Not Three "Speed Tiers"

A common misconception is:

~~~text
IMMUTABLE = fast
STABLE    = medium
VOLATILE  = slow
~~~

In reality, volatility describes **which optimizations are legal**, not how fast the function itself executes.

An `IMMUTABLE` function can perform a very CPU-intensive scientific calculation. A `VOLATILE` function can simply return a pseudo-random number in microseconds. Actual runtime depends on call count, table access, expressions, execution plan, caching, indexes, and concurrency.

Crucially, **never trade correctness for optimization**. Marking a function incorrectly as `IMMUTABLE` can introduce subtle data bugs far harder to detect than saving a few milliseconds of runtime.

~~~mermaid
flowchart TD
    A["Analyze actual function behavior"] --> B{"Result depends only on arguments, invariant across time/state?"}
    B -->|"Yes"| C["IMMUTABLE"]
    B -->|"No"| D{"Reads without modifying data and stable within one statement?"}
    D -->|"Yes"| E["STABLE"]
    D -->|"No"| F["VOLATILE"]
    C --> G["Planner may constant-fold"]
    E --> H["Planner may treat as stable within the statement"]
    F --> I["Planner must preserve re-evaluation and side effects"]
~~~

This flowchart is an initial selection rule; for functions involving collations, time zones, snapshots, extensions, or external APIs, you must also inspect less obvious dependencies.

## 3. Which Volatility Category Do Familiar PostgreSQL Functions Have?

The table below clarifies the distinctions:

| Expression/function | Typical volatility | Reason |
| --- | --- | --- |
| `abs(-10)` | `IMMUTABLE` | Deterministic operation depending solely on its argument |
| `lower(text)` | `IMMUTABLE` | Text transformation using the environment's comparison/collation rules |
| `now()` / `current_timestamp` | `STABLE` | Transaction start timestamp; constant within a transaction |
| `transaction_timestamp()` | `STABLE` | Same semantics: transaction start timestamp |
| `statement_timestamp()` | `STABLE` | Start timestamp of the current statement |
| `current_setting('TimeZone')` | `STABLE` | Reads a setting that can change between executions |
| `clock_timestamp()` | `VOLATILE` | Reads the real wall clock; value can change within the same statement |
| `random()` | `VOLATILE` | Generates a pseudo-random value on each call |
| `nextval('some_seq')` | `VOLATILE` | Mutates sequence state |
| Function reading a customer table | Usually `STABLE` if read-only and stable per statement | Table rows change over time |
| Function performing `INSERT`/`UPDATE`/`DELETE` | `VOLATILE` | Produces write side effects |

The easiest point to get wrong is assuming **`now()` is VOLATILE** just because its name means "now." In PostgreSQL, `now()` equals the **transaction** start time, so it stays unchanged within a transaction; `clock_timestamp()` is the function that reads the real clock at evaluation time.

You cannot reliably guess volatility from a function name alone. When accuracy matters, inspect `pg_proc`, the documentation for your server version, and the actual UDF implementation.

## 4. Distinguishing Three Time Functions Inside a Transaction

Run this example in a lab PostgreSQL session:

~~~sql
BEGIN;

SELECT
    now() AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;

-- Sleep briefly just to observe clock progression in the lab.
SELECT pg_sleep(0.3);

SELECT
    now() AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;

ROLLBACK;
~~~

Expected behavior:

- Both `now()` values inside the same transaction are **equal**, because both reference the transaction start time.
- `statement_timestamp()` differs between the two `SELECT` statements because they are separate statements.
- `clock_timestamp()` reflects wall-clock time at invocation and advances with real elapsed time.

**Do not assert that consecutive `clock_timestamp()` calls always return distinct numbers**: if two calls happen closer together than clock resolution, they can match numerically. The distinction is that PostgreSQL **does not promise invariance within a statement**.

### Is it safe to filter with NOW()?

Completely appropriate:

~~~sql
SELECT order_id
FROM orders
WHERE expires_at < now();
~~~

`now()` is `STABLE`, making it a well-behaved comparison threshold within a statement. If a very long-running query truly needs a moving wall-clock timestamp mid-execution, specify that requirement carefully and evaluate `clock_timestamp()` along with its execution-plan and consistency trade-offs.

## 5. Preparing the Practice Schema

Use a **dedicated practice** PostgreSQL database. This script drops `volatility_lab` if it already exists; **never run it against real data or a shared schema**.

~~~sql
-- RUN ONLY IN YOUR LAB DATABASE.
DROP SCHEMA IF EXISTS volatility_lab CASCADE;
CREATE SCHEMA volatility_lab;

CREATE TABLE volatility_lab.customers (
    customer_id bigint PRIMARY KEY,
    email text NOT NULL UNIQUE,
    full_name text NOT NULL,
    segment text NOT NULL
        CHECK (segment IN ('standard', 'silver', 'gold'))
);

CREATE TABLE volatility_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES volatility_lab.customers(customer_id),
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE INDEX idx_orders_customer
    ON volatility_lab.orders(customer_id);

CREATE INDEX idx_orders_expires
    ON volatility_lab.orders(expires_at);
~~~

Seed data:

~~~sql
INSERT INTO volatility_lab.customers
    (customer_id, email, full_name, segment)
VALUES
    (1, 'an@example.test', 'An', 'gold'),
    (2, 'binh@example.test', 'Binh', 'silver'),
    (3, 'chi@example.test', 'Chi', 'standard');

INSERT INTO volatility_lab.orders
    (order_id, customer_id, status, amount, expires_at)
VALUES
    (101, 1, 'paid',      120.00, now() - interval '1 day'),
    (102, 1, 'pending',    80.00, now() + interval '2 days'),
    (103, 2, 'pending',   200.00, now() - interval '2 hours'),
    (104, 3, 'cancelled',  40.00, now() + interval '1 day');
~~~

The table holds three customers and four orders:

| order_id | customer_id | status | amount | expires_at |
| ---: | ---: | --- | ---: | --- |
| 101 | 1 | paid | 120.00 | One day before seeding |
| 102 | 1 | pending | 80.00 | Two days after seeding |
| 103 | 2 | pending | 200.00 | Two hours before seeding |
| 104 | 3 | cancelled | 40.00 | One day after seeding |

Exact timestamps are not hardcoded because the lesson demonstrates **time-dependent** behavior; values are anchored relative to seeding time. Results of queries comparing against `now()` will shift as days pass if you leave the lab sitting. You can reset the lab using the safe cleanup snippet above to restore initial time relationships.

## 6. Creating an IMMUTABLE Function: A Pure Calculation

Example computing net amount after discount when both amount and discount percentage are passed explicitly:

~~~sql
CREATE FUNCTION volatility_lab.net_amount(
    p_amount numeric,
    p_discount_percent numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT p_amount * (1 - p_discount_percent / 100)
$$;
~~~

Declaration highlights:

- `LANGUAGE sql`: body is a SQL expression.
- `IMMUTABLE`: result depends solely on `p_amount` and `p_discount_percent`.
- `STRICT`: if either argument is NULL, return NULL without executing the body.
- The function reads no tables and depends on no clock, session configuration, or external state.

Test it:

~~~sql
SELECT volatility_lab.net_amount(100.00, 10.00) AS result;
~~~

Result: `90.0000` or an equivalent numeric format depending on client rendering.

Applied to orders:

~~~sql
SELECT
    order_id,
    amount,
    volatility_lab.net_amount(amount, 10) AS discounted_amount
FROM volatility_lab.orders
ORDER BY order_id;
~~~

With the 10% discount passed as an explicit argument, the result obeys the formula for each order's `amount`.

**This demo function does not enforce percentages in 0–100.** In production applications, validate at an appropriate layer or design the function to reject invalid inputs. `IMMUTABLE` does not mean "business-valid for all possible inputs."

## 7. Why Is This Calculation Called IMMUTABLE?

If you run:

~~~sql
SELECT
    volatility_lab.net_amount(100, 10) AS a,
    volatility_lab.net_amount(100, 10) AS b;
~~~

`a` and `b` have the exact same value.

Changing the time zone, inserting new orders, updating a customer's segment, or calling it again tomorrow **cannot alter the output** for those two arguments. That is the promise `IMMUTABLE` makes.

Looking deeper: PostgreSQL can **precompute** the result when all arguments are constants during planning:

~~~sql
SELECT volatility_lab.net_amount(100, 10);
~~~

The function call can be collapsed directly into the equivalent of `90` in the plan without invoking the function per row. This optimization is called **constant folding**.

Not every call to an immutable function runs just once: if an argument is a column varying per row, PostgreSQL still evaluates the function for each value unless another optimization applies. Volatility **permits** transformations; it does not mandate a fixed execution schedule.

## 8. Creating a STABLE Function: Reading Table Data

Suppose we want to fetch a customer's current segment by ID:

~~~sql
CREATE FUNCTION volatility_lab.customer_segment(
    p_customer_id bigint
)
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT c.segment
    FROM volatility_lab.customers AS c
    WHERE c.customer_id = p_customer_id
$$;
~~~

Usage:

~~~sql
SELECT
    customer_id,
    volatility_lab.customer_segment(customer_id) AS segment
FROM volatility_lab.customers
ORDER BY customer_id;
~~~

Result:

| customer_id | segment |
| ---: | --- |
| 1 | gold |
| 2 | silver |
| 3 | standard |

Why is it not `IMMUTABLE`?

Because the result depends on **table rows**. For the same `p_customer_id = 1`, the customer might be `gold` today, yet next month be updated to `standard`:

~~~sql
BEGIN;

UPDATE volatility_lab.customers
SET segment = 'standard'
WHERE customer_id = 1;

SELECT volatility_lab.customer_segment(1) AS segment_after_update;

ROLLBACK;
~~~

The separate `SELECT` following the `UPDATE` within the same transaction observes the updated segment under PostgreSQL's own-transaction visibility rules. After `ROLLBACK`, the lab returns to its original state.

The function qualifies as `STABLE` because it is **read-only** and PostgreSQL can use the statement snapshot to maintain a consistent view.

### STABLE does not mean the underlying data never changes

`STABLE` guarantees stability only **within a single statement** for identical arguments under appropriate snapshot semantics. It does not guarantee that the same customer ID retains the same segment across days, transactions, or repeated prepared-statement executions.

## 9. Creating a VOLATILE Function: Output Can Vary Between Calls

Example returning a random number:

~~~sql
CREATE FUNCTION volatility_lab.sample_random()
RETURNS double precision
LANGUAGE sql
VOLATILE
AS $$
    SELECT random()
$$;
~~~

Called per row:

~~~sql
SELECT
    n,
    volatility_lab.sample_random() AS random_value
FROM generate_series(1, 5) AS g(n);
~~~

Values can differ across rows and across executions.

Another `VOLATILE` function returning the real wall clock:

~~~sql
CREATE FUNCTION volatility_lab.wall_clock()
RETURNS timestamptz
LANGUAGE sql
VOLATILE
AS $$
    SELECT clock_timestamp()
$$;
~~~

`VOLATILE` informs PostgreSQL that **the result must not be treated as constant** wherever re-evaluation is required. It is also mandatory when a function writes to the database or calls side-effecting functions such as `nextval()`.

**Do not assume every call to a VOLATILE function must yield a distinct value.** `random()` can happen to draw two equal numbers; `clock_timestamp()` can match when called back-to-back within clock resolution. The contract states **it can change**, not **it must differ**.

## 10. VOLATILE Is the Default in CREATE FUNCTION

If volatility is omitted:

~~~sql
CREATE FUNCTION volatility_lab.double_amount(
    p_amount numeric
)
RETURNS numeric
LANGUAGE sql
AS $$
    SELECT p_amount * 2
$$;
~~~

PostgreSQL defaults the function to **`VOLATILE`**, even though its body is a pure arithmetic expression.

Usually that **does not produce mathematically wrong answers**, yet it prevents certain planner optimizations and disqualifies the function where immutability is required.

When a function is genuinely pure and properly implemented, declare it accurately:

~~~sql
CREATE OR REPLACE FUNCTION volatility_lab.double_amount(
    p_amount numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT p_amount * 2
$$;
~~~

Thus the lesson is not "PostgreSQL guesses automatically," but rather **the function author supplies the appropriate contract**.

### IMMUTABLE is stronger than STABLE, and STABLE is stronger than VOLATILE

Think of the three levels as an optimization permission hierarchy:

~~~text
IMMUTABLE  → permanently invariant for given arguments
   ↓
STABLE     → invariant within a single statement
   ↓
VOLATILE   → may change even within a single statement
~~~

A truly immutable function can conservatively be labeled stable or volatile, sacrificing some optimization. Conversely, **you must never promote a volatile function to immutable** if its real behavior breaks that promise.

## 11. Constant Folding: Planner Precomputation

Compare these two calls:

~~~sql
SELECT volatility_lab.net_amount(100, 10);

SELECT volatility_lab.sample_random();
~~~

In the first call, the arguments are constants and the function is `IMMUTABLE`. PostgreSQL **may** evaluate it during planning and embed the result in the execution plan.

In the second call, `sample_random()` is `VOLATILE`. The planner must not replace the call with a frozen constant merely because it takes no arguments.

### STABLE and constant folding

A `STABLE` function must not be folded into a constant **permanently across cached plan executions**, because the table data or configuration it reads can change between statements.

For example:

~~~sql
SELECT volatility_lab.customer_segment(1);
~~~

Today it returns `gold`; after an `UPDATE` from another transaction, a later statement may return `silver`. If the planner froze `gold` permanently because the function was mislabeled `IMMUTABLE`, the application would receive stale data.

Keep the distinction clear:

- **The planner can treat STABLE as constant for the duration of executing one statement**, especially in index scan conditions.
- Yet **STABLE is not permanently constant** for folding into a cached plan reused across executions.

## 12. Prepared Statements and the Risk of "Stale Values" from Mislabeling

Prepared statements and cached plans let applications avoid re-planning work. That makes accurate volatility critical.

Consider a bad function:

~~~sql
-- BAD EXAMPLE, DO NOT CREATE THIS FUNCTION:
-- CREATE FUNCTION bad_customer_segment(customer_id bigint)
-- RETURNS text
-- IMMUTABLE
-- AS $$ SELECT segment FROM customers WHERE id = customer_id $$;
~~~

If a table-reading function is **wrongly marked `IMMUTABLE`**, PostgreSQL may evaluate it at planning time when passed constant arguments. When the cached plan is reused later, the underlying table may already have changed.

Risk flow:

~~~mermaid
flowchart TD
    A["Table-reading function wrongly declared IMMUTABLE"] --> B["Planner sees constant arguments"]
    B --> C["May constant-fold value during planning"]
    C --> D["Plan is cached / reused"]
    D --> E["Underlying table data changes"]
    E --> F["Plan returns stale or incorrect results"]
~~~

**There is no guarantee the bug surfaces in a quick ad-hoc query.** Simple runs may happen to return the current value, hiding the mislabeling until the application runs prepared statements, plan caches, PL/pgSQL loops, or differently optimized queries.

### Selection rules

- Function reading mutable tables → **`STABLE`** if read-only and statement-snapshot consistent.
- Function reading session configuration settings → typically **`STABLE`**, not `IMMUTABLE`.
- Function calling `random()`, `clock_timestamp()`, sequences, or writing data → **`VOLATILE`**.
- Pure deterministic computation from arguments with no mutable state dependency → **`IMMUTABLE`**.

If a function returns stale data after table or configuration changes, do not simply "flush caches" to mask the symptom; check whether the **volatility contract** was misdeclared.

## 13. STABLE Enables Index Scan Conditions

Suppose `orders` has a B-tree index:

~~~sql
CREATE INDEX idx_orders_expires
ON volatility_lab.orders(expires_at);
~~~

For the query:

~~~sql
SELECT order_id, expires_at
FROM volatility_lab.orders
WHERE expires_at < now()
ORDER BY expires_at;
~~~

`now()` is `STABLE`. PostgreSQL can treat the threshold as constant within the statement, allowing `expires_at < now()` **to qualify as an index scan condition** on `expires_at`.

That does not force PostgreSQL to always pick the index. On a four-row table, a sequential `Seq Scan` is usually cheaper.

### Comparison with a VOLATILE expression

~~~sql
SELECT order_id
FROM volatility_lab.orders
WHERE expires_at < clock_timestamp();
~~~

`clock_timestamp()` can change across evaluations. If the planner assumed it was a fixed boundary computed once up front for an index scan without re-evaluating per check, behavior could violate `VOLATILE` semantics.

Hence **index scan conditions** require the comparison expression to offer sufficient stability; `VOLATILE` expressions generally cannot serve as **invariant runtime index keys across a scan** the way `STABLE` expressions can.

**Never claim absolutely that a query containing VOLATILE can never use any index.** If the query contains other indexable predicates, PostgreSQL can still scan an index on those predicates and apply the `VOLATILE` predicate as a filter afterward. Always inspect the actual execution plan.

## 14. Expression Indexes Require IMMUTABLE Functions

An **expression index** persists the output of an expression computed from table columns. PostgreSQL must rely on the fact that if the row's column values **do not change**, the expression always yields **the same result**. Therefore, functions used inside index expressions must satisfy the required volatility—in practice **`IMMUTABLE`**.

Example index supporting case-insensitive email lookups via `lower`:

~~~sql
CREATE INDEX idx_customers_email_lower
ON volatility_lab.customers (lower(email));
~~~

Query:

~~~sql
SELECT customer_id, full_name
FROM volatility_lab.customers
WHERE lower(email) = lower('AN@EXAMPLE.TEST');
~~~

Because `lower(email)` can be indexed, PostgreSQL gains an efficient access path once row counts and statistics justify it.

### Expression index on a user-defined function

~~~sql
CREATE INDEX idx_orders_net_amount
ON volatility_lab.orders (
    volatility_lab.net_amount(amount, 10::numeric)
);
~~~

`net_amount` is declared `IMMUTABLE` and depends solely on `amount` and constant `10`, making it a valid candidate.

Key detail: the index stores values of the **exact expression defined**, not every roughly similar calculation. The planner checks whether the query expression matches the index definition, data types, statistics, and cost.

### Invalid example: putting now() in an index expression

~~~sql
-- DO NOT RUN: PostgreSQL rejects this because now() is not IMMUTABLE.
CREATE INDEX idx_bad_expiry_boolean
ON volatility_lab.orders ((expires_at < now()));
~~~

The expression `expires_at < now()` can flip from false to true purely as time passes **without any UPDATE to the row**. A stored boolean index key would become out of date.

Therefore, you cannot solve "find expired orders" by baking `now()` into an expression index.

### The right approach

Index the column value that remains **invariant between row updates**:

~~~sql
CREATE INDEX idx_orders_expires_at
ON volatility_lab.orders(expires_at);
~~~

Then compare dynamically at query time:

~~~sql
SELECT order_id
FROM volatility_lab.orders
WHERE expires_at < now();
~~~

The index on `expires_at` supports range comparison against the `STABLE` timestamp computed when the query runs. Note that our lab table already created an equivalent `idx_orders_expires`, so do not keep redundant duplicate indexes in real systems.

## 15. Partial Indexes: Predicates Also Require IMMUTABLE

A **partial index** includes only rows matching a fixed `WHERE` predicate evaluated during index maintenance.

Example indexing only pending orders:

~~~sql
CREATE INDEX idx_orders_pending_expiry
ON volatility_lab.orders(expires_at)
WHERE status = 'pending';
~~~

Here `status = 'pending'` depends purely on the row's own column value. Whenever `status` is updated, PostgreSQL updates index membership accordingly.

Matching query:

~~~sql
SELECT order_id
FROM volatility_lab.orders
WHERE status = 'pending'
  AND expires_at < now();
~~~

This query can leverage the partial index under favorable plans and statistics.

### Mistake: a partial index for "not yet expired as of now"

~~~sql
-- DO NOT RUN: now() is STABLE, not IMMUTABLE.
CREATE INDEX idx_bad_not_expired
ON volatility_lab.orders(order_id)
WHERE expires_at > now();
~~~

The predicate `expires_at > now()` changes value as time passes even when zero rows are modified. Thus it cannot serve as an invariant membership predicate for a partial index.

**Solution:** index `expires_at`, or build a partial index on an application-maintained status column combined with a dynamic time filter in the query.

Never try to "cheat" by wrapping `now()` inside a function falsely marked `IMMUTABLE`. That is **breaking the contract**, not a legitimate optimization.

## 16. Generated Columns and Volatility

Expression-generated columns (*generated columns*) in PostgreSQL enforce strict computation requirements. For **stored generated columns**, the generation expression must use **`IMMUTABLE`** functions satisfying generated-expression rules.

Example:

~~~sql
CREATE TABLE volatility_lab.price_examples (
    price_id bigint PRIMARY KEY,
    base_price numeric(12,2) NOT NULL
        CHECK (base_price >= 0),
    tax_rate numeric(5,4) NOT NULL
        CHECK (tax_rate BETWEEN 0 AND 1),
    final_price numeric
        GENERATED ALWAYS AS (
            base_price * (1 + tax_rate)
        ) STORED
);
~~~

The table stores price and tax rate as **per-row inputs**. Whenever either column changes, PostgreSQL recomputes `final_price`. Because the expression depends only on row values, immutability is satisfied.

### Do not use now() in a generated column expression

~~~sql
-- DO NOT RUN: now() is not IMMUTABLE and is unsuitable
-- for a generated expression representing time-varying state.
CREATE TABLE volatility_lab.bad_generated (
    expires_at timestamptz NOT NULL,
    is_expired boolean
        GENERATED ALWAYS AS (expires_at < now()) STORED
);
~~~

If `is_expired` were persisted at insert time without future updates, it would grow stale as time advances.

### DEFAULT differs from generated expressions

Do not confuse generated-column requirements with **DEFAULT** values.

~~~sql
CREATE TABLE volatility_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_time timestamptz NOT NULL DEFAULT now(),
    captured_clock timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

`DEFAULT` is evaluated when inserting a row without specifying that column, so it may legally call **`STABLE`** or **`VOLATILE`** functions. Using `clock_timestamp()` in a `DEFAULT` never requires mislabeling it `IMMUTABLE`.

## 17. CHECK Constraints and Invariance Assumptions

A `CHECK` constraint expresses a validity rule over **a row's own values**. PostgreSQL assumes the check predicate continues to mean the same thing as long as the row's stored data does not change.

Sensible example:

~~~sql
CREATE TABLE volatility_lab.accounts (
    account_id bigint PRIMARY KEY,
    balance numeric(12,2) NOT NULL
        CHECK (balance >= 0)
);
~~~

As long as `balance` is untouched, whether `balance >= 0` holds cannot change simply because time passes.

### Anti-pattern: CHECK depending on now()

~~~sql
-- NOT RECOMMENDED: condition changes purely as time passes.
CREATE TABLE volatility_lab.bad_check (
    item_id bigint PRIMARY KEY,
    expires_at timestamptz NOT NULL,
    CHECK (expires_at > now())
);
~~~

A row valid at `INSERT` time becomes "invalid" a day later simply because the clock moved forward, yet PostgreSQL **does not re-scan every row to re-evaluate CHECK constraints as time passes**.

PostgreSQL does not forbid non-immutable functions in `CHECK` as strictly as in expression indexes; that very permissiveness allows definitions with **dangerous semantics**. Risks include time-dependent validity drift and failures during dump/restore or subsequent unrelated updates.

If your business rule says "reject creating an already-expired record," validate **at operation time** appropriately; to query active records, use `WHERE expires_at > now()` backed by an index on `expires_at`. Never treat a time-based `CHECK` as a timer.

## 18. Snapshots Inside STABLE/IMMUTABLE vs. VOLATILE Functions

PostgreSQL exhibits a subtle but crucial behavioral difference when a function **executes SQL queries internally**:

- Functions declared **`STABLE`** or **`IMMUTABLE`** inherit the snapshot established at the start of the calling query for the queries they run.
- Functions declared **`VOLATILE`** can take a fresh snapshot at the start of each internal SQL query, allowing them to observe changes made while the outer query is running under PostgreSQL semantics.

This is tied directly to MVCC (*multi-version concurrency control*), not merely "caching function results."

### Why does STABLE fit reading configuration or lookup tables?

For example, `customer_segment(customer_id)` queries `customers`. Inside a long-running statement, you want every lookup to see a consistent statement snapshot rather than reading the old segment at the start of the statement and a newly committed segment halfway through.

`STABLE` gives both planner and executor the foundation for statement-consistent reads.

### Why does VOLATILE need flexible snapshots?

A `VOLATILE` function may write rows, invoke side-effecting operations, or execute multiple statements that need to observe evolving state. Not being pinned to the outer statement's snapshot is part of supporting those behaviors.

**Note:** exact visibility still depends on isolation level, SQL statement type, locks, and execution plan. Do not design workflows assuming "a VOLATILE function immediately sees every concurrent transaction's change"—that misstates MVCC.

## 19. STABLE Functions Cannot Modify the Database

In `LANGUAGE sql` or `LANGUAGE plpgsql`, **`STABLE`** and **`IMMUTABLE`** functions are restricted from executing data-modifying statements the way a `VOLATILE` function can.

Example of a write function with accurate volatility:

~~~sql
CREATE FUNCTION volatility_lab.mark_order_paid(
    p_order_id bigint
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_rows integer;
BEGIN
    UPDATE volatility_lab.orders
    SET status = 'paid'
    WHERE order_id = p_order_id
      AND status = 'pending';

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RETURN v_rows = 1;
END;
$$;
~~~

Test inside a transaction:

~~~sql
BEGIN;

SELECT volatility_lab.mark_order_paid(102) AS changed;
SELECT order_id, status
FROM volatility_lab.orders
WHERE order_id = 102;

ROLLBACK;
~~~

With our seed data, order 102 starts as `pending`; the function returns true and updates it temporarily to `paid`. After rollback, the original data is restored.

Changing its declaration to `STABLE` or `IMMUTABLE` while keeping the `UPDATE` violates the read-only contract. Never alter the label just to coax the planner into "running faster."

### Remember permissions

`VOLATILE` only states that the function **may** modify data or vary. It **grants zero extra privileges** to callers. Effective permissions still depend on ownership, object grants, `SECURITY INVOKER`/`SECURITY DEFINER`, and security policies.

## 20. Can a STABLE Function Call a VOLATILE Function Internally?

Under the **contract**, if an outer function invokes a component whose output can vary within the same statement or cause side effects, the outer wrapper **must not promise stronger stability than its underlying behavior**.

Example of what not to do:

~~~sql
-- DESIGN ANTI-PATTERN, DO NOT CREATE:
-- CREATE FUNCTION bad_random()
-- RETURNS double precision
-- LANGUAGE sql
-- STABLE
-- AS $$ SELECT random() $$;
~~~

`random()` is `VOLATILE`; wrapping it in a function labeled `STABLE` does not make the output stable.

Likewise, wrapping `clock_timestamp()` cannot yield `IMMUTABLE` or `STABLE` if you intend to preserve "clock at invocation time" semantics.

In certain cases PostgreSQL cannot statically inspect every behavior across all languages or extensions to reject every bad declaration. **Successful CREATE FUNCTION execution does not prove the volatility label is right.**

## 21. Session Settings and Time Zones Can Break Immutability

A function may appear to transform only its input argument while actually depending on **`TimeZone`**, `DateStyle`, collation, or another session setting.

Example converting `timestamptz` to a date under the session time zone:

~~~sql
SELECT
    timestamptz '2026-11-14 00:30:00+00'::date;
~~~

The resulting date varies with the session's `TimeZone`:

- In UTC, this instant falls on November 14.
- In time zones west of UTC, it can still be November 13.

A wrapper converting timestamps according to the **current session time zone** cannot be declared `IMMUTABLE` merely because its `timestamptz` argument stays the same.

### Date_trunc and timestamp types

These two expressions differ semantically:

~~~sql
-- timestamp WITHOUT time zone: operates purely on the local timestamp passed in.
SELECT date_trunc(
    'day',
    timestamp '2026-11-14 12:30:00'
);

-- timestamptz: the day boundary depends on the interpreting time zone.
SELECT date_trunc(
    'day',
    timestamptz '2026-11-14 12:30:00+00'
);
~~~

Overloads of the same function name can have different volatilities. In modern PostgreSQL, `date_trunc(text, timestamp)` is `IMMUTABLE`, whereas `date_trunc(text, timestamptz)` is `STABLE` because it depends on the session time zone.

Do not look only at the name `date_trunc` and assume every overload shares one volatility. Always check the **exact function signature and parameter types**.

### Designing time-based index expressions

If you need an index grouped by calendar day, determine:

1. Whether the column is `timestamp` or `timestamptz`.
2. Whether "day" means UTC day or a fixed business time zone.
3. Whether the expression genuinely satisfies `IMMUTABLE`.
4. Whether indexes require rebuilding if tzdata/collation rules ever change.

**Never wrap a session-dependent `date_trunc` inside a mislabeled IMMUTABLE UDF** solely to satisfy an index creation check.

## 22. Functions Depending on External Data

A function can read:

- Environment variables or external configuration files.
- Network/API responses.
- State from an external system.
- Clocks, random generators, or sequences.
- Rows from mutable tables.

Any of those can change **even when the function arguments remain identical**. Therefore, never assume a function is `IMMUTABLE` merely because its SQL body contains no `UPDATE`.

For instance, a function fetching exchange rates from a web endpoint does not become `IMMUTABLE` if rates change every minute. In many cases external data sources are not protected by PostgreSQL's MVCC snapshot either, so even `STABLE` requires verifying true stability within a statement.

When in doubt, defaulting to `VOLATILE` is the safe choice for optimizer correctness. Only strengthen the promise when you can **prove the stronger guarantee holds**.

## 23. Volatility Is Orthogonal to STRICT, PARALLEL, and COST

`CREATE FUNCTION` carries several independent attributes alongside volatility:

| Attribute | Question it answers |
| --- | --- |
| `IMMUTABLE` / `STABLE` / `VOLATILE` | How much can the function's output vary? |
| `STRICT` / `RETURNS NULL ON NULL INPUT` | If any argument is NULL, can PostgreSQL return NULL without executing the body? |
| `PARALLEL SAFE/RESTRICTED/UNSAFE` | Can the function run inside parallel workers, and under what restrictions? |
| `COST` | Relative estimated CPU cost per invocation |
| `ROWS` | Estimated row count returned by a set-returning function |
| `SECURITY INVOKER/DEFINER` | Under whose privileges does the function run? |
| `LEAKPROOF` | A strict security property that must only be declared when rigorously verified |

These attributes **do not substitute for one another**.

An `IMMUTABLE` function is not automatically safe for parallel workers if it performs operations incompatible with parallel execution. Conversely, a `VOLATILE` function does not mean every query referencing it follows a simplistic all-or-nothing rule—always inspect parallel safety declarations and the query plan directly.

In PostgreSQL, user-defined functions typically default to **`VOLATILE`** and **`PARALLEL UNSAFE`** unless declared otherwise. Never mark `PARALLEL SAFE` just because you marked `IMMUTABLE`; evaluate parallelism independently.

### STRICT example

~~~sql
SELECT
    volatility_lab.net_amount(NULL::numeric, 10::numeric)
        AS null_result;
~~~

`net_amount` is declared `STRICT`, so it returns NULL when given a NULL input. That null-handling behavior is separate from whether output varies over time.

## 24. Inspecting Actual Volatility in pg_proc

PostgreSQL stores function metadata in `pg_proc`. The `provolatile` column uses these codes:

| Code | Volatility |
| --- | --- |
| `i` | `IMMUTABLE` |
| `s` | `STABLE` |
| `v` | `VOLATILE` |

Query the functions created in the lab:

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    pg_get_function_identity_arguments(p.oid) AS arguments,
    CASE p.provolatile
        WHEN 'i' THEN 'IMMUTABLE'
        WHEN 's' THEN 'STABLE'
        WHEN 'v' THEN 'VOLATILE'
    END AS volatility
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'volatility_lab'
ORDER BY p.proname, arguments;
~~~

Sample expected results include:

- `net_amount(numeric, numeric)` → `IMMUTABLE`.
- `customer_segment(bigint)` → `STABLE`.
- `sample_random()` → `VOLATILE`.
- `wall_clock()` → `VOLATILE`.
- `mark_order_paid(bigint)` → `VOLATILE`.
- `double_amount(numeric)` → `IMMUTABLE` after replacing via `CREATE OR REPLACE`.

### Inspecting built-in functions by exact signature

~~~sql
SELECT
    p.oid::regprocedure AS function_signature,
    p.provolatile,
    CASE p.provolatile
        WHEN 'i' THEN 'IMMUTABLE'
        WHEN 's' THEN 'STABLE'
        WHEN 'v' THEN 'VOLATILE'
    END AS volatility
FROM pg_proc AS p
WHERE p.oid IN (
    'pg_catalog.now()'::regprocedure,
    'pg_catalog.statement_timestamp()'::regprocedure,
    'pg_catalog.clock_timestamp()'::regprocedure,
    'pg_catalog.random()'::regprocedure,
    'pg_catalog.nextval(regclass)'::regprocedure,
    'pg_catalog.current_setting(text)'::regprocedure
)
ORDER BY function_signature::text;
~~~

Using `regprocedure` identifies the exact **signature**, avoiding confusion across overloads sharing a name with different parameter types.

In `psql`, you can also use `\df+ volatility_lab.*` to view function attributes or `\sf volatility_lab.net_amount` to view source definitions. Those are `psql` meta-commands, not standard SQL statements sent over JDBC.

## 25. EXPLAIN: Observing the Effect on Query Plans

`EXPLAIN` shows how the planner intends to execute a query.

Example with a `STABLE` condition:

~~~sql
EXPLAIN
SELECT order_id, expires_at
FROM volatility_lab.orders
WHERE expires_at < now();
~~~

Compared with a `VOLATILE` condition:

~~~sql
EXPLAIN
SELECT order_id, expires_at
FROM volatility_lab.orders
WHERE expires_at < clock_timestamp();
~~~

With an index on `expires_at` and a sufficiently large table, you can observe the difference between an `Index Cond` and a row `Filter` in applicable plans. The key takeaway is that the planner treats the two differently because **`now()` is stable**, whereas `clock_timestamp()` can change mid-execution.

**Do not expect a four-row lab table to always choose an Index Scan.** The planner decides by cost, and a sequential scan is typically cheaper on tiny tables.

### EXPLAIN ANALYZE actually executes the query

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM volatility_lab.orders
WHERE expires_at < now();
~~~

For a read-only `SELECT`, this is great for inspecting actual row counts and buffer hits.

However:

~~~sql
-- DO NOT run against production data just to inspect a plan:
EXPLAIN (ANALYZE)
UPDATE volatility_lab.orders
SET status = 'paid'
WHERE order_id = 102;
~~~

`EXPLAIN ANALYZE` **actually runs the UPDATE**. When testing data-modifying statements in a lab, wrap them in `BEGIN ... ROLLBACK`; never mistake `EXPLAIN ANALYZE` for a dry-run simulation.

## 26. Performance Depends on More Than Volatility

When a query invokes a UDF across many rows, total cost also depends on:

1. Whether the SQL function gets inlined.
2. Whether the function executes table queries or pure arithmetic.
3. Whether supporting indexes exist on predicates/expressions.
4. Cardinality statistics and filter selectivity.
5. Whether cheaper predicates filter out rows before evaluating the function.
6. Whether the planner reuses expressions, folds constants, or reorders evaluation.
7. How many times the function actually executes in the **real execution plan**, not just how often it appears in SQL text.
8. Parallel safety attributes, `COST`, and call context.

Example:

~~~sql
SELECT
    o.order_id,
    volatility_lab.customer_segment(o.customer_id)
FROM volatility_lab.orders AS o;
~~~

A `STABLE` function that queries a table per `customer_id` can still be expensive if invoked repeatedly. Often an **explicit JOIN** is clearer and faster:

~~~sql
SELECT
    o.order_id,
    c.segment
FROM volatility_lab.orders AS o
JOIN volatility_lab.customers AS c
    ON c.customer_id = o.customer_id;
~~~

Both queries express equivalent intent over valid rows, while an explicit `JOIN` gives the planner full visibility into table relationships.

**Do not hide an important JOIN inside a UDF expecting a STABLE label alone to produce optimal plans.** Compare actual plans on realistic data volumes.

## 27. Expression Evaluation and Side Effects: Never Rely on Call Counts

Beginners sometimes place a side-effecting `VOLATILE` function inside `WHERE` or `SELECT`, assuming it will be called **exactly once per row of the source table**.

Example:

~~~sql
SELECT
    order_id,
    random() AS sample_value
FROM volatility_lab.orders
WHERE status = 'pending';
~~~

`random()` is evaluated as needed for output rows. Yet query planning—expression pushdown, sorting, filtering, short-circuiting, or valid plan rewrites—can affect when and how often expressions run in complex queries.

### Practical rules

- Never embed critical business side effects inside functions called from `WHERE`.
- Never deduce exact invocation counts solely from base-table row counts.
- When audit logs or state transitions are required, use explicit `INSERT`/`UPDATE` statements, transactions, and `RETURNING`.
- If a single random value must be reused across multiple steps, **generate and bind it explicitly as data** rather than expecting separate `random()` calls to agree.

Volatility informs the planner **which transformations are allowed**, not a business guarantee over side effects or exact call frequency.

## 28. IMMUTABLE Does Not Protect Against Library or Environment Upgrades

Some deterministic functions rely on rules outside the immediate SQL expression, such as:

- OS or ICU collations.
- Text/Unicode extension versions.
- Timezone/`tzdata` rules.
- Algorithm changes deployed in custom extensions or code.

A function considered immutable under the current environment may require **index maintenance/rebuilding** if comparison semantics or logic change after an upgrade.

For example, `lower(email)` in an expression index relies on case-folding/collation rules. After OS collation/ICU upgrades or function definition edits, you may need **`REINDEX`** or a rebuild strategy so stored index keys match the new semantics.

**Never alter the body of an IMMUTABLE function used in an expression index assuming existing keys automatically recompute.** Index maintenance is separate from evaluating new rows correctly.

## 29. Function Volatility and Intra-Transaction Consistency

One transaction can span multiple statements:

~~~sql
BEGIN;

SELECT volatility_lab.customer_segment(1);

UPDATE volatility_lab.customers
SET segment = 'silver'
WHERE customer_id = 1;

SELECT volatility_lab.customer_segment(1);

ROLLBACK;
~~~

The two `SELECT` statements return different values: `gold` before the `UPDATE`, `silver` afterward. That **does not violate STABLE**, because the promise spans **one statement**, not an entire transaction.

By contrast:

~~~sql
BEGIN;

SELECT now();
SELECT pg_sleep(0.2);
SELECT now();

ROLLBACK;
~~~

both `now()` calls return the exact transaction start time. That is a **specific property of `now()`**, stronger than the bare minimum required of `STABLE`.

If a function needs statement start time rather than transaction start time, PostgreSQL provides `statement_timestamp()`. If it needs wall-clock time advancing during execution, use `clock_timestamp()`. Pick the exact **time semantics**, not whichever name sounds appealing.

## 30. Common Mistakes

### 30.1. Marking table-reading functions IMMUTABLE "for speed"

Table rows can change, so results can vary across statements. False `IMMUTABLE` labels cause cached plans to serve stale results.

### 30.2. Thinking now() is VOLATILE because its name says "now"

`now()` is `STABLE` in PostgreSQL and returns transaction start time. `clock_timestamp()` is the `VOLATILE` wall-clock function.

### 30.3. Putting now() in an expression index

`expires_at < now()` flips as time passes, violating the `IMMUTABLE` requirement for expression indexes.

### 30.4. Putting now() in a partial index predicate

`WHERE expires_at > now()` is not an invariant row-level membership rule. Index `expires_at` instead and filter dynamically in queries.

### 30.5. Using a time-based CHECK constraint expecting rows to expire automatically

`CHECK (expires_at > now())` may hold at `INSERT`, yet PostgreSQL does not re-evaluate it on a schedule. `CHECK` is not a scheduler.

### 30.6. Forgetting CREATE FUNCTION defaults to VOLATILE

Omitting volatility on a pure function leaves it at the most restrictive level, missing constant folding and expression-index eligibility.

### 30.7. Labeling a wrapper around random() as STABLE

The outer function can still vary within a single statement and must keep the corresponding `VOLATILE` contract.

### 30.8. Confusing STABLE with "constant across an entire transaction"

`STABLE` guarantees stability within one statement; a table-reading function can return different results on the next statement in the same transaction after an update.

### 30.9. Confusing IMMUTABLE with "takes zero arguments"

A parameterless function can still read the clock, tables, or settings, so zero parameters never implies immutability.

### 30.10. Assuming IMMUTABLE automatically makes any function fast

Immutability permits optimizations, yet the function body may still be CPU- or I/O-heavy; planner choices still depend on `COST`, indexes, data distribution, and plans.

### 30.11. Assuming all overloads share the same volatility

`date_trunc` differs between `timestamp` and `timestamptz` due to time-zone sensitivity. Verify exact signatures in `pg_proc`.

### 30.12. Relying on VOLATILE to force exactly one call per base row

Expression evaluation rules in complex plans cannot be reduced to that assumption. Use explicit DML/transactions when guaranteed side effects are required.

### 30.13. Abusing IMMUTABLE to bypass generated-column rules

Wrapping `now()` or table reads inside a falsely marked `IMMUTABLE` function may pass DDL checks while corrupting generated columns or index consistency.

### 30.14. Editing an immutable function without addressing existing index keys

If a function backing an expression index changes behavior, existing stored index entries do not refresh automatically. Plan an update/reindex strategy.

### 30.15. Confusing volatility with parallel safety or security attributes

An `IMMUTABLE` function is not automatically `PARALLEL SAFE` or safe under `SECURITY DEFINER`. They are separate contracts.

### 30.16. Ignoring MVCC and snapshot rules

`STABLE` table-reading functions read under the statement snapshot; do not expect them to observe concurrent mid-statement updates from other sessions. Complex read/write workflows require understanding isolation levels and transactions.

## 31. Practice Exercises with Answers

These exercises use the `volatility_lab` schema created in Section 5, except conceptual questions.

### Exercise 1. Choose volatility for a two-number addition function

~~~sql
CREATE FUNCTION volatility_lab.add_numbers(
    a numeric, b numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT a + b
$$;
~~~

**Answer:** `IMMUTABLE`, because it depends solely on its two inputs, reads no mutable state, and produces no side effects.

### Exercise 2. Choose volatility for a customer-tier lookup function

The function reads `segment` from `customers` by `customer_id`.

**Answer:** `STABLE`, as it is read-only and needs a consistent view within each statement. Never use `IMMUTABLE` because table rows can change between statements.

### Exercise 3. Identify volatility of random()

~~~sql
SELECT random() FROM generate_series(1, 3);
~~~

**Answer:** `VOLATILE`. PostgreSQL must not treat `random()` as constant simply because it has no parameters.

### Exercise 4. now() vs. clock_timestamp() for real elapsed time?

A function must return the live wall clock on each invocation, even within the same transaction.

**Answer:** `clock_timestamp()`, which is `VOLATILE`. `now()` returns transaction start time.

### Exercise 5. Why is this expression index invalid?

~~~sql
CREATE INDEX bad_idx
ON volatility_lab.orders ((expires_at < now()));
~~~

**Answer:** `now()` is `STABLE`, not `IMMUTABLE`; elapsed time changes the expression outcome without updating rows. Index `expires_at` instead.

### Exercise 6. Partial index on pending status

Write an index covering only `pending` orders sorted by expiration time:

~~~sql
CREATE INDEX idx_exercise_pending_expiry
ON volatility_lab.orders(expires_at)
WHERE status = 'pending';
~~~

**Answer:** The predicate depends solely on the row's `status` column and is valid; the time condition `expires_at < now()` belongs in the query.

### Exercise 7. What happens if volatility is omitted in CREATE FUNCTION?

**Answer:** PostgreSQL defaults to `VOLATILE`. For a pure calculation, declare `IMMUTABLE` explicitly to enable planner optimizations.

### Exercise 8. Why isn't reading TimeZone immutable?

~~~sql
SELECT current_setting('TimeZone');
~~~

**Answer:** The result changes whenever session configuration changes, even with identical function arguments. Thus it cannot guarantee "same arguments → same result forever."

### Exercise 9. Inspect the actual volatility of now()

~~~sql
SELECT
    proname,
    provolatile
FROM pg_proc
WHERE oid = 'pg_catalog.now()'::regprocedure;
~~~

**Answer:** `provolatile = 's'`, meaning `STABLE`.

### Exercise 10. What should an UPDATE-status function be declared as?

Function body:

~~~sql
UPDATE volatility_lab.orders
SET status = 'paid'
WHERE order_id = p_order_id;
~~~

**Answer:** `VOLATILE`, because it mutates database rows; declaring `STABLE` or `IMMUTABLE` violates the contract.

### Exercise 11. Why can cached plans become dangerous under mislabeling?

A price-lookup function is marked `IMMUTABLE`. First call returns 100; price changes to 120; a prepared statement may keep returning 100.

**Answer:** The planner may constant-fold an `IMMUTABLE` function with constant inputs at planning time and reuse that folded result inside cached plans. Functions reading mutable tables require an appropriate category, typically `STABLE`.

### Exercise 12. Generated column for taxed total

~~~sql
CREATE TABLE volatility_lab.invoice_lines (
    line_id bigint PRIMARY KEY,
    amount numeric(12,2) NOT NULL,
    tax_rate numeric(5,4) NOT NULL,
    total numeric
        GENERATED ALWAYS AS (amount * (1 + tax_rate)) STORED
);
~~~

**Answer:** Valid, because the expression uses same-row columns and immutable arithmetic. Do not inject `now()` into generated columns just to stamp current time.

### Exercise 13. Do two statements in one transaction share STABLE snapshots?

**Answer:** Do not assume so. `STABLE` guarantees consistency within **each statement**; later statements' snapshot and visibility depend on isolation level and transaction rules. `now()` staying fixed across a transaction is a special property of `now()` itself.

### Exercise 14. Why shouldn't a local-date wrapper be marked IMMUTABLE?

The function accepts `timestamptz` and returns `::date` in the session's `TimeZone`.

**Answer:** The same instant can yield different calendar dates if `TimeZone` changes. Make business time zones explicit and classify functions according to their true behavior.

### Exercise 15. Can a STABLE function return a newer value in a later statement?

~~~sql
BEGIN;
SELECT volatility_lab.customer_segment(1);
UPDATE volatility_lab.customers
SET segment = 'silver'
WHERE customer_id = 1;
SELECT volatility_lab.customer_segment(1);
ROLLBACK;
~~~

**Answer:** Yes. Subsequent statements in the same transaction observe their own updates; `STABLE` does not promise invariance across statements.

### Exercise 16. Is the planner forced to use an index if WHERE compares against STABLE now()?

**Answer:** No. `STABLE` makes the predicate eligible for index scans, yet the planner still evaluates cost; small tables often use sequential scans.

## 32. Practical Workflow for Classifying Functions in Real Projects

When creating or modifying a PostgreSQL function, follow this checklist:

1. **List all dependencies:** arguments, tables, sequences, clocks, randomness, settings, files/network, extensions, collations.
2. **Check for side effects:** does it run `INSERT`/`UPDATE`/`DELETE` or invoke write helpers?
3. **Test long-term invariance:** will identical arguments always return identical outputs regardless of data, config, or clock changes?
4. **If yes, choose IMMUTABLE**—and only when you can genuinely prove it.
5. **If not, check intra-statement stability:** is it read-only, statement-snapshot consistent, and invariant within a single statement?
6. **If yes, choose STABLE**; otherwise choose `VOLATILE`.
7. **Inspect inner calls:** a wrapper must never promise stronger stability than its internal dependencies allow.
8. **Check overloads and parameter types:** functions sharing a name can differ in volatility.
9. **Check usage context:** plain `SELECT`, index predicates, expression/partial indexes, generated columns, `DEFAULT`, `CHECK`, or cached prepared plans.
10. **Evaluate orthogonal attributes separately:** `STRICT`, `PARALLEL`, `COST`, privileges, and `SECURITY DEFINER`.
11. **Inspect catalog and plans:** `pg_proc.provolatile`, `EXPLAIN`, and `Index Cond` vs. `Filter`.
12. **Test boundary cases:** table updates between statements, changing `TimeZone`, concurrency, prepared statements, `NULL`s, extension/collation upgrades.
13. **Plan ahead when changing function logic:** expression indexes or stored generated columns may need recomputation/reindexing and coordinated migrations.
14. **Never test risky DML against production:** experiment inside rolled-back lab transactions.

This workflow separates two distinct questions: **what does the function truthfully guarantee**, and **what optimizations can the planner safely apply using that guarantee**.

## 33. Official PostgreSQL Documentation

For production systems, consult the documentation matching your exact **PostgreSQL major version**:

- [Function Volatility Categories](https://www.postgresql.org/docs/current/xfunc-volatility.html): definitions of `IMMUTABLE`, `STABLE`, `VOLATILE`, and snapshot rules.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): syntax for volatility, `STRICT`, `PARALLEL`, and `COST`.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): expression indexes.
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html): conditional partial indexes.
- [Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html): rules for generated expressions.
- [Date/Time Functions](https://www.postgresql.org/docs/current/functions-datetime.html): `now`, `statement_timestamp`, `clock_timestamp`, and `date_trunc`.
- [System Catalog pg_proc](https://www.postgresql.org/docs/current/catalog-pg-proc.html): `provolatile` and function metadata.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): query execution plan analysis.

Documentation under `/current/` points to the latest release. When writing migrations or troubleshooting older servers, replace `current` with your target version number to avoid assuming newer features or behaviors.

## 34. Summary

The three volatility levels form a **contract between the function author and the PostgreSQL planner**:

| Category | Short takeaway | Typical uses |
| --- | --- | --- |
| **`IMMUTABLE`** | Same arguments, permanently same result | Pure calculations; expression indexes; generated expressions |
| **`STABLE`** | Same arguments, stable within one statement | `now()`, table lookups, reading settings; index scan predicates |
| **`VOLATILE`** | Result or side effects can vary per call | `random()`, `clock_timestamp()`, `nextval()`, data-modifying functions |

**Key takeaways for optimization:**

- `IMMUTABLE` allows the planner to **constant-fold literal calls** and is required for invariant structures such as expression index keys.
- `STABLE` treats an expression as constant within a single statement, making it eligible for index scan bounds.
- `VOLATILE` forces PostgreSQL to respect potential variability and side effects without prematurely freezing results.
- Mislabeling volatility can cause **stale or incorrect query results**, particularly across cached plans, indexes, and generated columns.

Always choose the **strongest category your function's real behavior truly guarantees**—never the strongest category merely in hopes of faster queries. When volatility contracts are accurate, the planner unlocks safe optimizations while preserving data consistency and business semantics.
