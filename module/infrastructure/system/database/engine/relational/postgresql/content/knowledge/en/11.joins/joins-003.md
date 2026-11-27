# CROSS JOIN and Cartesian Product in PostgreSQL

When writing SQL, most of us think about **pairing rows that are related to each other**: orders linked to customers by `customer_id`, products linked to order items by `product_id`. However, there is another combination operation: **pairing every row from the left set with every row from the right set**, regardless of whether they share a linking key. That operation is the **Cartesian product**, explicitly expressed in PostgreSQL with `CROSS JOIN`.

For example, a store has **2 colors** and **3 sizes** and needs to list every color–size variant. A Cartesian product produces **2 × 3 = 6** combinations. That is a proper use of `CROSS JOIN`. On the other hand, if you accidentally omit the join condition between **100,000 orders** and **50,000 customers**, the pair count can reach **5 billion rows** before any subsequent operations. It is the exact same operation, yet the intent and impact are vastly different.

This lesson belongs to the **Combining Data** chapter in PostgreSQL. You will understand the mathematical basis of `CROSS JOIN`, distinguish it from `INNER JOIN` and `LEFT JOIN`, practice generating combinations, build report scaffolds, use `generate_series` and `LATERAL`, spot row-multiplication bugs, and estimate execution cost before running large queries.

## 1. What Is a Cartesian Product?

Suppose there are two datasets:

~~~text
Color set A              Size set B
+----------+             +-----------+
| Red      |             | S         |
| Blue     |             | M         |
+----------+             | L         |
                         +-----------+
~~~

The Cartesian product `A × B` consists of every pair:

~~~text
+----------+-----------+
| Color    | Size      |
+----------+-----------+
| Red      | S         |
| Red      | M         |
| Red      | L         |
| Blue     | S         |
| Blue     | M         |
| Blue     | L         |
+----------+-----------+
~~~

Every row of A is paired with **every** row of B.

In SQL:

~~~sql
SELECT
    c.color_name,
    s.size_code
FROM colors AS c
CROSS JOIN sizes AS s;
~~~

This syntax **has no `ON` clause** because PostgreSQL is not asked to match row pairs against any condition.

### 1.1. Row Count Formula

If A has `m` rows and B has `n` rows, the Cartesian product contains:

\[
|A \times B| = m \times n
\]

Examples:

| Rows in A | Rows in B | CROSS JOIN Rows |
|---:|---:|---:|
| 2 | 3 | 6 |
| 5 | 10 | 50 |
| 100 | 1,000 | 100,000 |
| 1,000 | 1,000 | 1,000,000 |
| 100,000 | 50,000 | 5,000,000,000 |

This formula applies to the **raw CROSS JOIN result**, prior to any filters, aggregations, `DISTINCT`, or `LIMIT` appearing elsewhere in the query.

### 1.2. It Is Multiplication, Not Addition

Two tables with 10 and 20 rows do not produce 30 rows under a CROSS JOIN—they produce **200 rows**. Confusing these often leads to underestimating memory, CPU, or output size.

### 1.3. Result Column Count

If A has 2 columns and B has 3 columns, `SELECT *` from `A CROSS JOIN B` can output 5 columns. However, column names across both tables can collide; the result can be hard to read and cause trouble when clients map column names.

Select columns explicitly and use aliases:

~~~sql
SELECT
    a.id AS left_id,
    a.name AS left_name,
    b.id AS right_id,
    b.code AS right_code
FROM table_a AS a
CROSS JOIN table_b AS b;
~~~

The snippet above illustrates the structure and runs only if the corresponding tables exist.

## 2. How Does PostgreSQL Evaluate CROSS JOIN Semantically?

Consider the SQL query:

~~~sql
SELECT a.value AS a_value, b.value AS b_value
FROM (VALUES ('A'), ('B')) AS a(value)
CROSS JOIN (VALUES (1), (2), (3)) AS b(value)
ORDER BY a.value, b.value;
~~~

Result:

| a_value | b_value |
|---|---:|
| A | 1 |
| A | 2 |
| A | 3 |
| B | 1 |
| B | 2 |
| B | 3 |

Every row on the left is combined with every row on the right. The ordering in the result table above is dictated by `ORDER BY`, **not guaranteed by CROSS JOIN by default**.

### 2.1. CROSS JOIN Has No Matching Condition

With `INNER JOIN`, there is typically a condition:

~~~sql
FROM orders AS o
INNER JOIN customers AS c
    ON c.customer_id = o.customer_id
~~~

With `CROSS JOIN`:

~~~sql
FROM colors AS c
CROSS JOIN sizes AS s
~~~

no key is needed and no equality is required. Every pair is formed logically.

### 2.2. Cartesian Product Is a Set of Pairs; SQL Allows Duplicate Records

Relational algebra normally describes relations as **sets**. In practice, SQL uses **multiset semantics** (*bag semantics*): unless `DISTINCT` or an appropriate uniqueness mechanism is applied, duplicate rows are not automatically removed.

Example:

~~~sql
SELECT a.label, b.number_value
FROM (VALUES ('A'), ('A')) AS a(label)
CROSS JOIN (VALUES (1), (2)) AS b(number_value);
~~~

The result has four rows, containing two copies of `(A,1)` and two copies of `(A,2)`. PostgreSQL does not collapse two rows with identical values into one row just because a CROSS JOIN is running.

**Do not use `DISTINCT` to hide duplicate data bugs without understanding the business requirement.**

### 2.3. NULL Does Not Automatically Block a Pair

~~~sql
SELECT a.value AS left_value, b.value AS right_value
FROM (VALUES (NULL::INTEGER), (1)) AS a(value)
CROSS JOIN (VALUES ('x'::TEXT), ('y'::TEXT)) AS b(value);
~~~

There are **4 rows** even though one value on the left is `NULL`. CROSS JOIN requires no equality comparison, so it does not discard rows merely for containing NULL.

Only when a condition such as `WHERE a.value = b.value` is added does SQL's three-valued logic affect which rows are kept; in the example above, the two sides do not even share a compatible comparison type for such a condition.

## 3. What If One Table Is Empty?

Suppose A has 4 rows and B has 0 rows:

\[
|A \times B| = 4 \times 0 = 0
\]

You can verify this:

~~~sql
SELECT a.id, b.code
FROM (VALUES (1), (2), (3), (4)) AS a(id)
CROSS JOIN (
    SELECT code
    FROM (VALUES ('X')) AS x(code)
    WHERE FALSE
) AS b;
~~~

The result is **0 rows**.

This matters when one side is a configuration table or a value set from a subquery. If the subquery returns no rows, **the entire CROSS JOIN result vanishes**, even when the main table still has data.

### 3.1. Difference from LEFT JOIN

If you need to keep all rows from A even when B is empty, use an appropriate outer join:

~~~sql
SELECT a.id, b.code
FROM (VALUES (1), (2)) AS a(id)
LEFT JOIN (
    SELECT code
    FROM (VALUES ('X')) AS x(code)
    WHERE FALSE
) AS b ON TRUE;
~~~

The result has two rows, with `b.code` as `NULL`. This does **not have the same semantics** as CROSS JOIN.

### 3.2. Case Where One Table Has Exactly One Row

If A has 100 rows and B has exactly one row, the CROSS JOIN produces 100 rows. This is an intentional way to attach a **shared value** to every row of A, such as a configuration value, an aggregate, or a parameter.

However, you must be sure query B **truly returns exactly one row**; otherwise the entire calculation can multiply or vanish.

## 4. CROSS JOIN Syntax in PostgreSQL

Standard form:

~~~sql
SELECT ...
FROM table_a AS a
CROSS JOIN table_b AS b;
~~~

With multiple tables:

~~~sql
SELECT ...
FROM table_a AS a
CROSS JOIN table_b AS b
CROSS JOIN table_c AS c;
~~~

If they have `m`, `n`, and `p` rows respectively, the full product has `m × n × p` rows.

### 4.1. CROSS JOIN Has No ON or USING

Invalid:

~~~sql
-- Not valid CROSS JOIN syntax:
-- FROM orders o CROSS JOIN customers c
-- ON o.customer_id = c.customer_id
~~~

To join by a condition, use:

~~~sql
FROM orders AS o
JOIN customers AS c
    ON o.customer_id = c.customer_id
~~~

or use CROSS JOIN and filter in `WHERE` when there is a clear reason; however, `INNER JOIN ... ON ...` expresses data relationships much more clearly.

### 4.2. You Can CROSS JOIN with a Subquery

~~~sql
SELECT a.product_code, b.discount_rate
FROM (VALUES ('P01'), ('P02')) AS a(product_code)
CROSS JOIN (
    SELECT 0.10::NUMERIC AS discount_rate
) AS b;
~~~

The result has two products, each paired with the single value 0.10.

### 4.3. You Can CROSS JOIN with VALUES

~~~sql
SELECT d.day_code, s.slot_time
FROM (VALUES ('MON'), ('TUE')) AS d(day_code)
CROSS JOIN (
    VALUES (TIME '09:00'), (TIME '14:00')
) AS s(slot_time)
ORDER BY d.day_code, s.slot_time;
~~~

This is a concise way to build a small value set, commonly used in demos, reports, or parameter models.

### 4.4. Use Aliases to Avoid Ambiguous Columns

~~~sql
SELECT
    a.id AS source_id,
    b.id AS target_id
FROM source_table AS a
CROSS JOIN target_table AS b;
~~~

Do not write an unqualified `SELECT id` when both tables contain an `id` column, because PostgreSQL will report an ambiguous column reference.

## 5. CROSS JOIN vs. Comma-Separated Tables in FROM

PostgreSQL supports:

~~~sql
SELECT a.value, b.value
FROM (VALUES (1), (2)) AS a(value),
     (VALUES ('x'), ('y')) AS b(value);
~~~

In this example with two unconditional sources, it produces a Cartesian product equivalent to:

~~~sql
SELECT a.value, b.value
FROM (VALUES (1), (2)) AS a(value)
CROSS JOIN (VALUES ('x'), ('y')) AS b(value);
~~~

### 5.1. Why Prefer Explicit CROSS JOIN?

- Readers know the **intent is to generate every combination**, not an accidentally omitted JOIN condition.
- Easy to distinguish from key-based relational joins.
- Easier to control join grouping and avoid misreading `ON` binding precedence.
- Aids code review in catching unexpected row growth.

### 5.2. Different Precedence When Mixed with JOIN

In SQL syntax, explicit `JOIN` has higher binding precedence than commas in `FROM`. A clause like:

~~~sql
-- Illustrating syntax that can cause a reference error:
-- FROM a, b JOIN c ON c.key = a.key
~~~

can fail because the `ON` condition of `b JOIN c` cannot see `a` in the way the author assumed.

A clearer approach is to group relationships explicitly using `JOIN` syntax with conditions attached to the proper join:

~~~sql
FROM a
JOIN c ON c.key = a.key
CROSS JOIN b
~~~

This is a structural example and runs only if the tables and columns exist.

### 5.3. Do Not Equate NATURAL JOIN with CROSS JOIN

`NATURAL JOIN` is a join based on matching column names, **not a synonym** for CROSS JOIN. Because schemas can evolve and accidentally introduce shared column names, NATURAL JOIN is often hard to read and can silently alter query meaning. For business relationships, write explicit `ON` or `USING` clauses.

## 6. CROSS JOIN vs. INNER JOIN ON TRUE

For two independent sources, the following forms produce equivalent result rows:

~~~sql
SELECT a.id, b.code
FROM (VALUES (1), (2)) AS a(id)
CROSS JOIN (VALUES ('X'), ('Y')) AS b(code);
~~~

~~~sql
SELECT a.id, b.code
FROM (VALUES (1), (2)) AS a(id)
INNER JOIN (VALUES ('X'), ('Y')) AS b(code)
    ON TRUE;
~~~

The `ON TRUE` condition holds for **every pair**, so INNER JOIN discards no pairs.

### 6.1. Syntax Choice Communicates Intent

- `CROSS JOIN`: intentionally generates all pairs.
- `INNER JOIN ... ON TRUE`: join condition always true; sometimes used in generated SQL or specialized patterns.
- `INNER JOIN ... ON condition`: keeps only pairs meeting the condition, typically a data relationship.

Prefer `CROSS JOIN` when you want the full product.

### 6.2. LEFT JOIN ON TRUE Is Not Always the Same

If the right table has at least one row, `LEFT JOIN ... ON TRUE` produces all pairs like CROSS JOIN. However, if the right table is empty, LEFT JOIN still retains the left rows with NULL right columns, whereas CROSS JOIN returns 0 rows.

Therefore, the two cannot be substituted for each other in general.

## 7. CROSS JOIN Combined with WHERE: Multiply Then Filter

Consider:

~~~sql
SELECT a.id, b.id
FROM (VALUES (1), (2)) AS a(id)
CROSS JOIN (VALUES (1), (3)) AS b(id)
WHERE a.id = b.id;
~~~

The initial product has four pairs:

~~~text
(1,1)
(1,3)
(2,1)
(2,3)
~~~

After `WHERE a.id = b.id`, one pair `(1,1)` remains.

Another way to write it:

~~~sql
SELECT a.id, b.id
FROM (VALUES (1), (2)) AS a(id)
JOIN (VALUES (1), (3)) AS b(id)
    ON a.id = b.id;
~~~

Both queries return the same result for a standard INNER JOIN case.

### 7.1. Logically, SELECT Passes Through Stages

A conceptual model:

~~~text
FROM / JOIN
    |
    v
WHERE
    |
    v
GROUP BY / HAVING
    |
    v
SELECT
    |
    v
ORDER BY / LIMIT
~~~

However, this is a **semantic model**, not a mandatory description of the physical order in which PostgreSQL materializes and stores every row. The planner can push filters down, reorder joins, and pick different algorithms as long as semantics are preserved.

### 7.2. Why Does JOIN ON Express Intent Better?

When two tables have a real relationship:

~~~sql
SELECT
    o.order_id,
    c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id;
~~~

is easier to read than:

~~~sql
SELECT
    o.order_id,
    c.customer_name
FROM orders AS o
CROSS JOIN customers AS c
WHERE c.customer_id = o.customer_id;
~~~

PostgreSQL can optimize both forms similarly in many cases, yet the first syntax accurately expresses **key-based relationship intent** and lowers the risk of someone accidentally deleting the WHERE condition.

### 7.3. Conditions in WHERE Can Shrink the Pair Set

If each table has its own filter:

~~~sql
SELECT a.id, b.code
FROM table_a AS a
CROSS JOIN table_b AS b
WHERE a.active = TRUE
  AND b.enabled = TRUE;
~~~

The logical result is the Cartesian product of **active** rows with **enabled** rows. The planner can usually apply each filter before physically joining.

Do not assume PostgreSQL necessarily builds all `|A| × |B|` rows in RAM before filtering; check the execution plan.

## 8. Lab: Creating Sample Color and Size Data

The commands in this section are for a **test PostgreSQL database** with CREATE SCHEMA privileges. Do not run on production. If the `cross_join_lab` schema already exists from a previous session, use another database or schema name; do not delete real data.

### 8.1. Create the Schema

~~~sql
CREATE SCHEMA cross_join_lab;
~~~

### 8.2. Create Two Dimension Tables

~~~sql
CREATE TABLE cross_join_lab.colors (
    color_id INTEGER PRIMARY KEY,
    color_name TEXT NOT NULL UNIQUE
);

CREATE TABLE cross_join_lab.sizes (
    size_code TEXT PRIMARY KEY,
    sort_rank INTEGER NOT NULL UNIQUE
);
~~~

### 8.3. Insert Data

~~~sql
INSERT INTO cross_join_lab.colors (color_id, color_name)
VALUES
    (1, 'Red'),
    (2, 'Blue');

INSERT INTO cross_join_lab.sizes (size_code, sort_rank)
VALUES
    ('S', 1),
    ('M', 2),
    ('L', 3);
~~~

Row counts:

~~~sql
SELECT COUNT(*) AS color_count
FROM cross_join_lab.colors;

SELECT COUNT(*) AS size_count
FROM cross_join_lab.sizes;
~~~

Expected results are 2 and 3, respectively.

### 8.4. Generate All Combinations

~~~sql
SELECT
    c.color_id,
    c.color_name,
    s.size_code
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s
ORDER BY c.color_id, s.sort_rank;
~~~

Result:

| color_id | color_name | size_code |
|---:|---|---|
| 1 | Red | S |
| 1 | Red | M |
| 1 | Red | L |
| 2 | Blue | S |
| 2 | Blue | M |
| 2 | Blue | L |

### 8.5. Verify the Product Row Count

~~~sql
SELECT COUNT(*) AS combination_count
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s;
~~~

Expected: `6`.

You can also compare:

~~~sql
SELECT
    (SELECT COUNT(*) FROM cross_join_lab.colors)
    *
    (SELECT COUNT(*) FROM cross_join_lab.sizes)
    AS expected_combinations;
~~~

Both results must match when evaluating a pure CROSS JOIN and data does not change between reads under the corresponding snapshot semantics.

### 8.6. Do Not Assume Order Without ORDER BY

~~~sql
SELECT c.color_name, s.size_code
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s;
~~~

PostgreSQL may return rows in a particular order during one run, but **SQL guarantees no output order** without `ORDER BY`. Never write tests relying on incidental ordering.

## 9. CROSS JOIN in Business: Generating Product Variants

The "color × size" problem is a natural use case, though you must distinguish:

- **Possible variant set**: all theoretical combinations.
- **Actually sold variant set**: a rule-governed subset.
- **Registered SKUs**: variants that exist and are managed as independent entities.
- **Inventory**: stock quantity at a specific location and time.

### 9.1. Generate a List of Potential Variants

~~~sql
SELECT
    c.color_name,
    s.size_code
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s
ORDER BY c.color_id, s.sort_rank;
~~~

This SQL generates **every combination**; it does not confirm they can be manufactured or already have a price.

### 9.2. Exclude Invalid Combinations

Suppose size L is available only in Red:

~~~sql
SELECT
    c.color_name,
    s.size_code
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s
WHERE s.size_code <> 'L'
   OR c.color_name = 'Red'
ORDER BY c.color_id, s.sort_rank;
~~~

The result has 5 combinations: three sizes in Red and two sizes (S/M) in Blue.

In real systems, avoid hardcoding every exception in `WHERE`. A configuration table of allowed variants or a `product_variants` table with proper keys and constraints may be needed.

### 9.3. Do Not Use CROSS JOIN to Pretend an Entity Exists

If the application needs a SKU, barcode, stock count, or per-variant price, merely displaying a Cartesian product does not create that data. You need a proper variant table model and registration workflow.

CROSS JOIN solves **combination generation**, not the lifecycle of business entities.

## 10. Building a Report Scaffold: Days × Stores

An important scenario: reporting **every store, every day** within a range, even when no transactions occurred.

If you only group the transaction table, days without transactions **disappear**. You can use CROSS JOIN to build a complete scaffold and then LEFT JOIN the actual data.

### 10.1. Create Stores and Daily Sales Tables

~~~sql
CREATE TABLE cross_join_lab.stores (
    store_id INTEGER PRIMARY KEY,
    store_name TEXT NOT NULL
);

CREATE TABLE cross_join_lab.daily_sales (
    store_id INTEGER NOT NULL
        REFERENCES cross_join_lab.stores(store_id),
    sale_day DATE NOT NULL,
    revenue NUMERIC(14, 2) NOT NULL
        CHECK (revenue >= 0),
    PRIMARY KEY (store_id, sale_day)
);

INSERT INTO cross_join_lab.stores (store_id, store_name)
VALUES
    (1, 'Hanoi'),
    (2, 'Da Nang');

INSERT INTO cross_join_lab.daily_sales (
    store_id, sale_day, revenue
)
VALUES
    (1, DATE '2026-11-14', 1000000.00),
    (2, DATE '2026-11-15', 1500000.00);
~~~

The data has two stores and two days:

~~~text
Hanoi:   Nov 14 has revenue, Nov 15 has no record
Da Nang: Nov 14 has no record, Nov 15 has revenue
~~~

### 10.2. Create a Date Set Using VALUES

~~~sql
SELECT d.sale_day
FROM (
    VALUES
        (DATE '2026-11-14'),
        (DATE '2026-11-15')
) AS d(sale_day);
~~~

### 10.3. CROSS JOIN to Generate Every Store–Day Pair

~~~sql
SELECT
    s.store_id,
    s.store_name,
    d.sale_day
FROM cross_join_lab.stores AS s
CROSS JOIN (
    VALUES
        (DATE '2026-11-14'),
        (DATE '2026-11-15')
) AS d(sale_day)
ORDER BY s.store_id, d.sale_day;
~~~

The scaffold has **2 × 2 = 4** rows, including the two cells with no revenue yet.

### 10.4. LEFT JOIN and COALESCE to Fill Data

~~~sql
SELECT
    s.store_name,
    d.sale_day,
    COALESCE(ds.revenue, 0::NUMERIC) AS revenue
FROM cross_join_lab.stores AS s
CROSS JOIN (
    VALUES
        (DATE '2026-11-14'),
        (DATE '2026-11-15')
) AS d(sale_day)
LEFT JOIN cross_join_lab.daily_sales AS ds
    ON ds.store_id = s.store_id
   AND ds.sale_day = d.sale_day
ORDER BY s.store_id, d.sale_day;
~~~

Result:

| store_name | sale_day | revenue |
|---|---|---:|
| Hanoi | 2026-11-14 | 1,000,000 |
| Hanoi | 2026-11-15 | 0 |
| Da Nang | 2026-11-14 | 0 |
| Da Nang | 2026-11-15 | 1,500,000 |

This is the **data scaffolding / densification** pattern commonly used in dashboards and reports.

### 10.5. Is COALESCE to 0 Always Right?

No. **No record** can mean "zero revenue" or "data not yet received." If data is missing due to a failed ETL job, turning NULL into 0 can hide the outage.

Verify the business meaning:

- If no transaction certainly equals 0, `COALESCE` is appropriate.
- If a missing record may mean data is not ready yet, keep NULL or add a `data_available` flag.

CROSS JOIN creates the missing cells; **what an empty cell means** is a separate business decision.

## 11. The WHERE Trap After LEFT JOIN

Once you build a scaffold with CROSS JOIN and LEFT JOIN, a misplaced filter condition can drop rows that should be kept.

Example:

~~~sql
SELECT
    s.store_name,
    d.sale_day,
    ds.revenue
FROM cross_join_lab.stores AS s
CROSS JOIN (
    VALUES
        (DATE '2026-11-14'),
        (DATE '2026-11-15')
) AS d(sale_day)
LEFT JOIN cross_join_lab.daily_sales AS ds
    ON ds.store_id = s.store_id
   AND ds.sale_day = d.sale_day
WHERE ds.revenue > 0;
~~~

Unmatched rows have `ds.revenue IS NULL`, so `WHERE ds.revenue > 0` discards them. The result no longer covers every store–day pair.

### 11.1. If You Only Want to Join Positive-Revenue Records

Move the condition to `ON`:

~~~sql
LEFT JOIN cross_join_lab.daily_sales AS ds
    ON ds.store_id = s.store_id
   AND ds.sale_day = d.sale_day
   AND ds.revenue > 0
~~~

Now all scaffold rows remain preserved, while unmatched revenue columns stay NULL.

**Never move conditions mechanically between WHERE and ON**: with an outer join, the result semantics can differ.

### 11.2. Combining CROSS JOIN and LEFT JOIN Intentionally

In a reporting query:

~~~text
CROSS JOIN:
    Defines which combinations MUST appear.

LEFT JOIN:
    Attaches actual data that MAY exist.

WHERE / ON:
    Defines entity filters and which data records qualify.
~~~

Separating these roles makes queries much easier to read.

## 12. generate_series() and CROSS JOIN

PostgreSQL provides `generate_series` to produce numeric or timestamp sequences. It pairs naturally with CROSS JOIN when building calendars or value matrices.

### 12.1. Generating a Number Sequence

~~~sql
SELECT g.n
FROM generate_series(1, 5) AS g(n);
~~~

The result contains 1, 2, 3, 4, 5.

### 12.2. Pairing Each Color with Sequence Numbers

~~~sql
SELECT
    c.color_name,
    g.n
FROM cross_join_lab.colors AS c
CROSS JOIN generate_series(1, 3) AS g(n)
ORDER BY c.color_id, g.n;
~~~

Two colors and three numbers yield **6 rows**.

### 12.3. Generating Days Combined with Time Slots

~~~sql
SELECT
    g.day_start::DATE AS schedule_day,
    slot.slot_time
FROM generate_series(
    TIMESTAMP '2026-11-14 00:00:00',
    TIMESTAMP '2026-11-16 00:00:00',
    INTERVAL '1 day'
) AS g(day_start)
CROSS JOIN (
    VALUES
        (TIME '09:00:00'),
        (TIME '14:00:00')
) AS slot(slot_time)
ORDER BY schedule_day, slot.slot_time;
~~~

The day set consists of Nov 14, 15, and 16. Each day has two slots (09:00 and 14:00), so the result has **3 × 2 = 6 rows**.

### 12.4. generate_series Usually Includes the Upper Endpoint

In the example above, `2026-11-16 00:00` appears because `generate_series` steps forward and includes the endpoint if reached exactly.

If a report expects the half-open interval `[2026-11-14, 2026-11-16)`, calculate the ending boundary accordingly or filter out the unintended Nov 16 row.

### 12.5. Calendars with Timezones and DST

When generating daily **instants** in a region with daylight saving time, check whether a one-day step applies in local calendar time or as an absolute duration, and whether your PostgreSQL version supports the timezone-accepting overload.

The example above uses `timestamp without time zone` to generate local date labels for the lab, **not a cross-timezone instant schedule**. For DST-aware schedules, model timezones and date boundary conversions explicitly.

## 13. Multi-Dimensional CROSS JOIN

Suppose a report has:

- 2 stores.
- 3 product categories.
- 7 days.

Number of cells:

\[
2 \times 3 \times 7 = 42
\]

Illustrative query:

~~~sql
SELECT
    s.store_name,
    p.category_code,
    d.day_start::DATE AS report_day
FROM cross_join_lab.stores AS s
CROSS JOIN (
    VALUES ('BOOK'), ('TOY'), ('GIFT')
) AS p(category_code)
CROSS JOIN generate_series(
    TIMESTAMP '2026-11-14 00:00:00',
    TIMESTAMP '2026-11-20 00:00:00',
    INTERVAL '1 day'
) AS d(day_start)
ORDER BY s.store_id, p.category_code, report_day;
~~~

The result has 42 rows when the stores table contains exactly 2 rows.

### 13.1. Row Count Grows as the Product of Dimensions

With multiple dimensions:

\[
N = n_1 \times n_2 \times \cdots \times n_k
\]

A dimension with 0 rows reduces the entire product to 0 rows. Doubling one dimension doubles the total output, holding everything else constant.

### 13.2. Example of Combination Explosion

~~~text
100 stores
× 10,000 products
× 365 days
= 365,000,000 combinations
~~~

365 million rows likely far exceeds what a dashboard needs. Generate only business-relevant combinations: for example, only products carried at each store, only days in the reporting window, and only permitted pairs.

### 13.3. Do Not Equate Every Combination with Valid Combinations

The product `stores × products` can generate products that a given store does not carry. If a report needs all **permitted** pairs, use a `store_products` mapping table or a properly maintained filter.

A sensible pattern uses `stores JOIN store_products` to identify valid pairs, then `CROSS JOIN dates` to expand each valid pair across all days.

## 14. Filtering Early to Control Input Sets

Suppose you only need active stores and enabled products:

~~~sql
SELECT
    s.store_id,
    p.product_id
FROM (
    SELECT store_id
    FROM stores
    WHERE active = TRUE
) AS s
CROSS JOIN (
    SELECT product_id
    FROM products
    WHERE enabled = TRUE
) AS p;
~~~

This is a structural example and runs only if the tables and columns exist.

### 14.1. Why Filter Dimensions Before Combining?

If the stores table has 1,000 rows with only 50 active, and the products table has 100,000 rows with only 200 enabled:

~~~text
Unfiltered: 1,000 × 100,000 = 100,000,000 rows

Needed set: 50 × 200 = 10,000 rows
~~~

Logically shrinking input sets before generating combinations drastically reduces the workload.

### 14.2. The Planner Can Push WHERE Predicates Down

The following two queries usually mean the same thing:

~~~sql
SELECT s.store_id, p.product_id
FROM stores AS s
CROSS JOIN products AS p
WHERE s.active = TRUE
  AND p.enabled = TRUE;
~~~

~~~sql
SELECT s.store_id, p.product_id
FROM (
    SELECT store_id
    FROM stores
    WHERE active = TRUE
) AS s
CROSS JOIN (
    SELECT product_id
    FROM products
    WHERE enabled = TRUE
) AS p;
~~~

The PostgreSQL planner can recognize single-source filters and apply them early. The second form highlights the intended subset, though it does not force every subquery to be materialized.

To see what the server actually executes, inspect `EXPLAIN`.

### 14.3. CTEs Are Not Physical Barriers by Default

~~~sql
WITH active_stores AS (
    SELECT store_id
    FROM stores
    WHERE active
),
enabled_products AS (
    SELECT product_id
    FROM products
    WHERE enabled
)
SELECT s.store_id, p.product_id
FROM active_stores AS s
CROSS JOIN enabled_products AS p;
~~~

CTEs organize SQL cleanly, yet PostgreSQL may inline or materialize them depending on context, version, and hints. Do not assume writing `WITH` always creates a temp table or blocks optimizations.

## 15. CROSS JOIN and the Missing JOIN Condition Bug

This is the most important real-world hazard.

Suppose you have:

~~~text
customers: 5,000 rows
orders:   80,000 rows
~~~

The goal is to pair each order with its owning customer.

**Correct:**

~~~sql
SELECT
    o.order_id,
    c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id;
~~~

If each order points to one customer, the result is close to **80,000 rows**.

**Wrong due to missing condition:**

~~~sql
SELECT
    o.order_id,
    c.customer_name
FROM orders AS o
CROSS JOIN customers AS c;
~~~

The pair count is:

\[
80{,}000 \times 5{,}000 = 400{,}000{,}000
\]

If the author used comma syntax:

~~~sql
SELECT
    o.order_id,
    c.customer_name
FROM orders AS o,
     customers AS c;
~~~

and forgot `WHERE o.customer_id = c.customer_id`, the bug still produces a Cartesian product.

### 15.1. Symptoms of an Accidental Cartesian Product

- One order appears alongside many unrelated customers.
- Row counts jump from thousands to millions.
- Total revenue is multiplied many times over.
- The query returns very slowly or consumes abnormal resources.
- `EXPLAIN` predicts a huge cardinality jump at the join node.
- A report looks fine under a very narrow filter yet breaks over broader ranges.

### 15.2. GROUP BY Can Mask Row Multiplication

Example:

~~~sql
SELECT SUM(o.amount)
FROM orders AS o
CROSS JOIN customers AS c;
~~~

If `customers` has 5,000 rows, each order is repeated 5,000 times, multiplying the sum by 5,000 assuming nothing else changes.

Adding `DISTINCT` inside the amount sum is not a valid fix: different orders can have the same `amount`, in which case `DISTINCT` breaks the result in a different way.

**Fix the JOIN relationship**, rather than patching over it with `DISTINCT` or `GROUP BY`.

## 16. Self CROSS JOIN: Every Pair of Items in One Table

Sometimes you need all pairs among rows of the **same table**.

~~~sql
SELECT
    a.color_name AS color_a,
    b.color_name AS color_b
FROM cross_join_lab.colors AS a
CROSS JOIN cross_join_lab.colors AS b
ORDER BY a.color_id, b.color_id;
~~~

With 2 colors, the result includes:

~~~text
Red  - Red
Red  - Blue
Blue - Red
Blue - Blue
~~~

### 16.1. Excluding Self-Pairs

~~~sql
SELECT
    a.color_name AS color_a,
    b.color_name AS color_b
FROM cross_join_lab.colors AS a
CROSS JOIN cross_join_lab.colors AS b
WHERE a.color_id <> b.color_id;
~~~

With 2 colors, two ordered pairs remain: Red–Blue and Blue–Red.

With `n` rows having distinct keys, the number of non-self ordered pairs is:

\[
n(n-1)
\]

### 16.2. Generating Unordered Pairs

~~~sql
SELECT
    a.color_name AS first_color,
    b.color_name AS second_color
FROM cross_join_lab.colors AS a
CROSS JOIN cross_join_lab.colors AS b
WHERE a.color_id < b.color_id;
~~~

The condition `a.color_id < b.color_id` removes self-pairs and eliminates one of each symmetric pair. The pair count is:

\[
\frac{n(n-1)}{2}
\]

This pattern is useful when listing product pairs for comparison, room pairs for proximity checks, or user pairs for recommendations. On very large sets, pair generation can quickly become expensive.

### 16.3. Do Not Pair Everyone When Only Known Relationships Matter

If a system has millions of users but you only need pairs who are already friends, CROSS JOINing everyone with everyone is far too large. Use a `friendships` relationship table or query directly against existing link records.

## 17. CROSS JOIN with Set-Returning Functions

PostgreSQL allows **set-returning functions** in `FROM`, such as `generate_series` or `unnest`.

~~~sql
SELECT
    c.color_name,
    series.n
FROM cross_join_lab.colors AS c
CROSS JOIN generate_series(1, 3) AS series(n);
~~~

When the function does not depend on the left row, it acts as an independent row source and the row count equals `colors_count × 3`.

### 17.1. unnest with a Fixed Array

~~~sql
SELECT
    c.color_name,
    u.tag
FROM cross_join_lab.colors AS c
CROSS JOIN unnest(
    ARRAY['featured', 'clearance']::TEXT[]
) AS u(tag)
ORDER BY c.color_id, u.tag;
~~~

Each color pairs with two tags, producing 4 rows.

### 17.2. A Function Returning Zero Rows Also Empties the Result

~~~sql
SELECT
    c.color_name,
    u.tag
FROM cross_join_lab.colors AS c
CROSS JOIN unnest(ARRAY[]::TEXT[]) AS u(tag);
~~~

Because `unnest` on an empty array returns zero rows, the entire CROSS JOIN produces zero rows. That is a direct consequence of multiplying by 0.

## 18. CROSS JOIN LATERAL: Right Source Depends on Each Left Row

A regular CROSS JOIN between two independent sets has `m × n` rows. Sometimes, however, the right source needs **values from each left row** to generate a varying number of rows.

PostgreSQL supports `LATERAL`:

~~~sql
SELECT
    c.color_id,
    c.color_name,
    g.n
FROM cross_join_lab.colors AS c
CROSS JOIN LATERAL generate_series(
    1,
    c.color_id
) AS g(n)
ORDER BY c.color_id, g.n;
~~~

With the sample data:

~~~text
color_id = 1 (Red)  -> generate_series(1,1): 1 row
color_id = 2 (Blue) -> generate_series(1,2): 2 rows
~~~

The result has **3 rows** rather than `2 × some constant n`.

### 18.1. Why Is LATERAL Needed?

In a subquery or function in `FROM`, `LATERAL` allows the right source to reference columns from preceding left sources.

Conceptual pattern:

~~~text
For each row LEFT:
    evaluate RIGHT using values from LEFT
    emit every row returned by RIGHT
~~~

The total row count is:

\[
N = \sum_{\text{each row }a \in A} |\text{right}(a)|
\]

This is the sum of right-side rows generated per left row, not necessarily a product of two fixed cardinalities.

### 18.2. For Functions in FROM, LATERAL Can Be Implicit

In PostgreSQL, certain functions in `FROM` can reference columns from earlier sources without explicitly writing the `LATERAL` keyword.

Still, writing `CROSS JOIN LATERAL` explicitly highlights the dependency and prevents confusing an independent source with a per-row evaluated source.

## 19. CROSS JOIN LATERAL with Per-Row Arrays

Create an orders table with a tag list:

~~~sql
CREATE TABLE cross_join_lab.order_tags (
    order_id INTEGER PRIMARY KEY,
    tags TEXT[]
);

INSERT INTO cross_join_lab.order_tags (order_id, tags)
VALUES
    (101, ARRAY['new', 'priority']),
    (102, ARRAY['gift']),
    (103, ARRAY[]::TEXT[]);
~~~

Expand each tag into its own row:

~~~sql
SELECT
    o.order_id,
    t.tag
FROM cross_join_lab.order_tags AS o
CROSS JOIN LATERAL unnest(o.tags) AS t(tag)
ORDER BY o.order_id, t.tag;
~~~

Result:

| order_id | tag |
|---:|---|
| 101 | new |
| 101 | priority |
| 102 | gift |

Order 103 has an empty array and does not appear.

### 19.1. Preserving Orders with Empty Arrays

Use `LEFT JOIN LATERAL ... ON TRUE`:

~~~sql
SELECT
    o.order_id,
    t.tag
FROM cross_join_lab.order_tags AS o
LEFT JOIN LATERAL unnest(o.tags) AS t(tag)
    ON TRUE
ORDER BY o.order_id, t.tag NULLS LAST;
~~~

The result now includes order 103 with `tag IS NULL`. This is a key difference between **CROSS JOIN LATERAL** and **LEFT JOIN LATERAL** when the right source can return 0 rows.

### 19.2. Avoiding Unintended Multiplication When Unnesting

If a row has a 100-element array and the query CROSS JOINs another 50-element array, you produce 5,000 pairs for a single parent row. If the goal is to pair elements **by matching index positions** across two arrays, CROSS JOINing two unnests is wrong; use position-preserving techniques like `WITH ORDINALITY` or multi-argument unnest according to the right semantics.

## 20. CROSS JOIN or LATERAL Subquery for Related Data?

Suppose you want the **two most recent orders per customer**. That question does not ask for every customer–order pair; it asks for a subset dependent on the current customer.

A PostgreSQL approach:

~~~sql
SELECT
    c.customer_id,
    latest.order_id,
    latest.created_at
FROM customers AS c
CROSS JOIN LATERAL (
    SELECT o.order_id, o.created_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS latest;
~~~

This example assumes the `customers` and `orders` tables exist.

Each customer yields at most 2 rows. Customers with no orders do not appear because of **CROSS JOIN LATERAL**.

To keep customers without orders:

~~~sql
SELECT
    c.customer_id,
    latest.order_id,
    latest.created_at
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.created_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS latest
    ON TRUE;
~~~

### 20.1. Why Not CROSS JOIN All Orders?

Computing `customers × orders` and then filtering/ranking to find the two newest orders creates unnecessary intermediate pairs. A LATERAL subquery filtered by customer expresses the requirement far more directly.

With an appropriate index like `orders(customer_id, created_at DESC, order_id DESC)`, top-N per customer queries can be efficient; always verify with `EXPLAIN` on real data.

### 20.2. Watch the Execution Frequency of Dependent Sources

If the outer relation has 1 million customers, the LATERAL source might be evaluated per row or handled via a different plan chosen by the planner. Do not assume LATERAL is always fast just because each subquery returns few rows; check the plan and actual loop counts.

## 21. Using CROSS JOIN to Attach a Single Summary Row

An aggregate without `GROUP BY` normally returns **one row**, even on an empty input set (functions like `MAX` return NULL). Hence you can use CROSS JOIN to attach a summary value to every row.

Example with the lab data:

~~~sql
SELECT
    c.color_name,
    totals.size_count
FROM cross_join_lab.colors AS c
CROSS JOIN (
    SELECT COUNT(*) AS size_count
    FROM cross_join_lab.sizes
) AS totals
ORDER BY c.color_id;
~~~

The `totals` table has one row with `size_count = 3`, so the output has two rows.

### 21.1. Distinguishing a Scalar Aggregate from a Zero-Row Query

~~~sql
SELECT COUNT(*)
FROM cross_join_lab.sizes
WHERE FALSE;
~~~

Returns one row with value 0.

Whereas:

~~~sql
SELECT size_code
FROM cross_join_lab.sizes
WHERE FALSE;
~~~

Returns 0 rows.

If you CROSS JOIN the second case, **the entire result becomes empty**. Before using CROSS JOIN to attach "one configuration row," verify whether that query is guaranteed to return exactly one row.

### 21.2. Window Functions May Be a Better Fit

If the goal is to attach the total row count of the result itself to each row, you can use:

~~~sql
SELECT
    c.color_name,
    COUNT(*) OVER () AS total_colors
FROM cross_join_lab.colors AS c
ORDER BY c.color_id;
~~~

There is no need to CROSS JOIN an aggregated subquery for this case. Choose the construct that best expresses the intent and check actual cost.

## 22. CROSS JOIN with Multiple Relational Data Sources

Not every dimension should be CROSS JOINed directly with every other dimension. Distinguish **independent dimensions** from **dependent relationships**.

Suppose:

~~~text
stores
store_products (only products sold at each store)
products
calendar_days
~~~

If you need daily revenue/visibility for valid store–product pairs, the typical logic is:

~~~sql
SELECT
    sp.store_id,
    sp.product_id,
    d.day_start::DATE AS report_day
FROM store_products AS sp
CROSS JOIN generate_series(
    TIMESTAMP '2026-11-14',
    TIMESTAMP '2026-11-20',
    INTERVAL '1 day'
) AS d(day_start);
~~~

This example assumes `store_products` holds valid pairs.

Do not blindly write:

~~~sql
FROM stores CROSS JOIN products CROSS JOIN calendar_days
~~~

when not every store sells every product. That multiplication produces **business-meaningless rows** and causes row explosion.

### 22.1. Step-by-Step Cardinality Analysis

~~~text
1. stores JOIN store_products:
   2,500 valid store-product pairs

2. CROSS JOIN 7 days:
   2,500 × 7 = 17,500 rows

Compared to:
   100 stores × 10,000 products × 7 days
   = 7,000,000 rows
~~~

Constructing input sources according to true relationships can shrink the working set by orders of magnitude.

## 23. EXPLAIN: Inspecting Cost Instead of Guessing

PostgreSQL lets you inspect plans with:

~~~sql
EXPLAIN
SELECT
    c.color_name,
    s.size_code
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s;
~~~

`EXPLAIN` shows the estimated plan, including costs and row estimates. It does not execute the full SELECT like `EXPLAIN ANALYZE`.

### 23.1. EXPLAIN ANALYZE on the Small Lab Set

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.color_name,
    s.size_code
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s
ORDER BY c.color_id, s.sort_rank;
~~~

Look at:

- **Plan node** (Nested Loop, Sort, or other nodes).
- Estimated vs. actual **rows**.
- **loops** (how many times a child node executed).
- **Execution Time**.
- **Buffers** used within instrumented nodes.

Do not assume every CROSS JOIN always uses a single fixed physical algorithm. Plans vary with data size, indexes, predicates, and PostgreSQL version.

### 23.2. Nested Loop Is Easy to Visualize

One possible execution pattern:

~~~text
For each row c in colors:
    For each row s in sizes:
        emit (c, s)
~~~

This resembles a Nested Loop without a join condition. However, the planner can insert Materialize, Sort, or choose another execution strategy; **SQL specifies the logical result**, not every physical detail.

### 23.3. EXPLAIN ANALYZE Actually Runs the Query

When using:

~~~sql
EXPLAIN (ANALYZE, BUFFERS) SELECT ...;
~~~

PostgreSQL actually executes the SELECT to measure real timings and row counts. With `INSERT`, `UPDATE`, or `DELETE`, `EXPLAIN ANALYZE` also mutates data unless rolled back properly.

Never run a CROSS JOIN expected to produce billions of pairs just to see "how slow it is." Use **EXPLAIN without ANALYZE** first to inspect the estimated plan.

## 24. The Planner Can Reorder JOINs

Algebraically, for eligible INNER JOIN / CROSS JOIN combinations, the optimizer can rearrange join order to lower cost while preserving the exact same logical result.

Example:

~~~sql
SELECT ...
FROM a
CROSS JOIN b
JOIN c ON c.id = a.c_id;
~~~

PostgreSQL does not necessarily materialize all of `a × b` first before joining with `c`. The planner can push conditions down and choose an optimal join order.

### 24.1. Do Not Infer Physical Order from FROM Order

Writing SQL as:

~~~sql
FROM a CROSS JOIN b CROSS JOIN c
~~~

does not guarantee the execution loops always run in `a → b → c` order.

### 24.2. Planning Limits

PostgreSQL has parameters affecting join collapsing and reordering, such as `join_collapse_limit` and `from_collapse_limit`. Queries with very many tables can affect optimization cost.

This lesson does not require tuning those parameters. For queries with many joins, first verify correct relationships, clear filters, and fresh statistics before examining planner settings.

### 24.3. Cardinality Estimates Matter

If the planner misestimates row counts after filters or joins, it can pick a suboptimal plan. You may need:

- `ANALYZE` to refresh statistics.
- Appropriate indexes for filters or other relationships in the query.
- Shrinking input datasets per business logic.
- Rewriting the query to avoid unnecessary combinations.
- Checking correlations / extended statistics when appropriate.

However, **no magic index** can turn genuinely outputting 500 million combinations into a lightweight task like returning a few thousand rows.

## 25. Cardinality Explosion: A Real-World Risk

Suppose two tables have:

~~~text
A: 100,000 rows
B: 100,000 rows
~~~

The Cartesian product has **10,000,000,000** pairs.

If each result row carries many columns, simply streaming rows to the application consumes massive time and bandwidth. Adding `ORDER BY`, `DISTINCT`, or aggregations can require heavy CPU, work memory, and temporary disk files.

### 25.1. LIMIT Is Not a Safe Explosion Guard

~~~sql
SELECT ...
FROM big_table_a
CROSS JOIN big_table_b
LIMIT 100;
~~~

For certain simple plans, PostgreSQL can stop early after 100 rows. However, if there is an `ORDER BY` needing to inspect many rows, `DISTINCT`, aggregates, or other blocking operations, `LIMIT` **does not guarantee** the query only does 100 pairs' worth of work.

Furthermore, `LIMIT` never fixes broken logic when the query actually needed a key-based JOIN.

### 25.2. COUNT(*) Does Not Make Every Huge Product Cheap

~~~sql
SELECT COUNT(*)
FROM big_table_a
CROSS JOIN big_table_b;
~~~

The logical result is a single row, yet the server may still have to process huge volumes depending on the plan. Do not assume "just taking COUNT" is always cheap.

If you only want to **predict the count of independent combinations**, multiply the row counts of each source; even then, running `COUNT(*)` on massive tables carries its own cost.

### 25.3. Estimate Ahead of Time

An out-of-band calculation:

~~~text
Expected combinations =
    count_of_filtered_left
    × count_of_filtered_right
~~~

With multiple dimensions:

~~~text
Expected combinations =
    n1 × n2 × n3 × ... × nk
~~~

Set sensible thresholds for reports/jobs and confirm whether **users truly need every combination** before running.

## 26. How to Safely Forecast Row Counts in SQL

On the small lab set:

~~~sql
SELECT
    c.n_colors,
    s.n_sizes,
    c.n_colors * s.n_sizes AS expected_pairs
FROM (
    SELECT COUNT(*)::NUMERIC AS n_colors
    FROM cross_join_lab.colors
) AS c
CROSS JOIN (
    SELECT COUNT(*)::NUMERIC AS n_sizes
    FROM cross_join_lab.sizes
) AS s;
~~~

Each aggregate subquery returns one row; the CROSS JOIN here produces just **one row** containing the forecast.

Casting to `NUMERIC` before multiplying prevents integer overflow on huge forecasts. Note that this calculation still scans/counts each source; for massive tables, rely on estimated statistics or other monitoring tools as appropriate.

### 26.1. Post-WHERE Counts Are the Real Inputs

If you only need active products:

~~~sql
SELECT COUNT(*)
FROM products
WHERE active = TRUE;
~~~

Forecast using **business-filtered subsets**, rather than blindly using full table counts when the actual query targets a small subset.

### 26.2. With LATERAL, Multiplying Two Fixed Counts Is Not Enough

With:

~~~sql
SELECT c.color_id, g.n
FROM cross_join_lab.colors AS c
CROSS JOIN LATERAL generate_series(1, c.color_id) AS g(n);
~~~

each row produces a different number of right-side rows. The total row count is the **sum of per-row output sizes**, not simply the color count times a constant row count from `generate_series`.

## 27. CROSS JOIN and Memory, CPU, and I/O

When results grow large, costs surface across multiple layers:

| Layer | Risk |
|---|---|
| CPU | Processing many pairs, expressions, and filter predicates |
| Memory | Sorts, hashes, aggregates, and query state |
| Temporary files | Sorts/aggregates spilling beyond working memory |
| Disk I/O | Scanning many input pages or writing temp files |
| Network | Transferring massive result sets to the client |
| Application | Parsing millions of records, OOM on client |
| Database concurrency | Resource-heavy query slowing down other workloads |

Not every case can be solved by bumping `work_mem`. If the query is generating unnecessary rows, **reducing combinations** is the top priority.

### 27.1. Is Pulling Data to the Application and Multiplying There Worse?

There is no absolute rule. Generating combinations in the database enables efficient filtering and joining with real data, whereas streaming billions of pairs to an API still causes major problems.

A system may need to:

- Partition reports by day/location.
- Paginate with stable keys.
- Process in batches.
- Generate only qualifying combinations.
- Aggregate early where appropriate.
- Persist a normalized table of allowed combinations instead of regenerating everything every run.

The right choice depends on business requirements, workload, and measurements.

## 28. CROSS JOIN with Potentially Duplicate Data

Suppose a dimension contains two rows with the same label:

~~~sql
SELECT a.label, b.slot
FROM (VALUES ('A'), ('A')) AS a(label)
CROSS JOIN (VALUES (1), (2)) AS b(slot);
~~~

The result has 4 rows, even though there are only 2 distinct value pairs.

### 28.1. UNIQUE on Dimensions Clarifies the Model

If colors must be a unique catalog, a `color_name UNIQUE` constraint or proper business key prevents duplicates. In our lab, `cross_join_lab.colors` already enforces `UNIQUE(color_name)`.

### 28.2. Use DISTINCT Only When the Problem Demands a Distinct Set

~~~sql
SELECT DISTINCT a.label, b.slot
FROM (VALUES ('A'), ('A')) AS a(label)
CROSS JOIN (VALUES (1), (2)) AS b(slot);
~~~

The result drops to 2 rows, yet PostgreSQL still has to execute deduplication semantics, which adds cost. If the real intent is a unique dimension list, cleaning the source data or querying an explicit distinct dimension is usually preferable.

## 29. Interaction with Aggregates and KPI Calculations

An accidental CROSS JOIN can turn an accurate KPI into a wrong number.

Suppose orders have revenue:

~~~text
Order 1: 100
Order 2: 200
True total: 300
~~~

If accidentally CROSS JOINed with 3 regions:

~~~text
Order 1 × 3 regions -> 100 appears 3 times
Order 2 × 3 regions -> 200 appears 3 times
Total after CROSS JOIN: 900
~~~

Even though `SUM(amount)` returns a single row, the figure has been tripled.

### 29.1. Ask "What Does One Row Represent?"

Before every JOIN in a report, establish:

- What does one row of each table represent?
- Is the expected relationship 1:1, 1:N, or N:M?
- Should row counts be allowed to increase after the JOIN?
- Do we need deduplication by a specific key?
- Does a CROSS JOIN genuinely require every combination?

This prevents "fan-out" bugs in BI when joining tables without checking cardinality.

### 29.2. COUNT(*) and COUNT(DISTINCT key) Differ

After a CROSS JOIN, `COUNT(*)` counts **pairs**. `COUNT(DISTINCT order_id)` counts distinct order IDs if the key is present, yet that does not fix other aggregates.

Do not apply `COUNT(DISTINCT ...)` as a universal patch for a broken JOIN model.

## 30. CROSS JOIN Can Fit Combinatorial Testing

Some problems are not transactional business data:

- Generating parameter sets to test multiple configurations.
- Generating an OS × browser × viewport matrix.
- Generating number/day/time-slot combinations.
- Generating a hypothetical "every policy × every segment" matrix.
- Listing candidate pairs to evaluate before filtering.

Example generating a test environment matrix:

~~~sql
SELECT
    os.os_name,
    browser.browser_name,
    viewport.viewport_name
FROM (VALUES ('Windows'), ('Linux')) AS os(os_name)
CROSS JOIN (
    VALUES ('Chrome'), ('Firefox')
) AS browser(browser_name)
CROSS JOIN (
    VALUES ('Desktop'), ('Mobile')
) AS viewport(viewport_name)
ORDER BY os.os_name, browser.browser_name, viewport.viewport_name;
~~~

Combination count: `2 × 2 × 2 = 8`.

As dimensions grow, apply rules to exclude unsupported combinations (e.g., a browser unavailable on a given OS) before turning them into actual test cases.

## 31. CROSS JOIN Does Not Mean "Everything Exists"

When generating a `product × color × size` matrix, do not label every pair an "existing SKU" if no SKU record exists yet.

Similarly, a `store × day` matrix does not prove daily revenue records exist; it simply defines **the report cells you want displayed**.

Distinguish:

~~~text
Mathematically possible combinations
            |
            v
Business-valid combinations
            |
            v
Combinations registered in data
            |
            v
Combinations with actual state/values
~~~

CROSS JOIN directly solves only the first layer; subsequent layers require constraints, JOINs, or real relational data.

## 32. Tenants and Security When Generating All Combinations

In a multi-tenant system, pairing all users with all stores or all products can produce pairs **disallowed** by authorization policies.

~~~sql
-- Business-invalid if not every user can access every store:
-- SELECT *
-- FROM users CROSS JOIN stores;
~~~

Even if PostgreSQL protects tables with RLS, generating combinations from rows a user is allowed to read still does not prove **every cross-pair among those rows** is permitted by business policy.

Determine valid relationships using mapping tables, owner/tenant keys, and authorization rules.

### 32.1. CROSS JOIN Does Not Replace Joining by tenant_id

If a customer belongs to tenant A and an order belongs to tenant B, simply CROSS JOINing both tables with a filter missing the tenant check can produce cross-tenant pairs.

Use proper tenant-aware join conditions and keys:

~~~sql
SELECT
    o.order_id,
    c.customer_id
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
   AND c.tenant_id = o.tenant_id;
~~~

This is an illustrative structure; inspect your system's actual key and permission model. Never use CROSS JOIN to avoid writing relational join conditions.

## 33. Workflow for Designing a Safe CROSS JOIN

Before running on large datasets:

1. **State why every pair is needed.** If you want key-based matching, use INNER/LEFT JOIN instead of CROSS JOIN.
2. **Define the granularity** of each source: what is one row?
3. **Count or estimate the post-filter size of each source**.
4. **Multiply dimension row counts** to forecast the output.
5. **Check whether a source can be empty or unexpectedly return multiple rows**.
6. **Separate mathematical combinations from business-valid combinations**.
7. **Filter dimensions and valid relationships early before generating huge matrices**.
8. **To fill missing cells**, CROSS JOIN the scaffold, then LEFT JOIN actual data.
9. **If the right source depends on each left row**, consider CROSS JOIN LATERAL or LEFT JOIN LATERAL.
10. **Run EXPLAIN first** if scale poses any risk.
11. **Audit aggregates and fan-out**, especially SUM/COUNT after JOINs.
12. **Control CPU, I/O, memory, and response size**; never treat LIMIT as a cure-all.
13. **Add ORDER BY** when consumers need deterministic order.
14. **Verify permissions/tenants** before generating or returning combinations.
15. **Write cardinality tests** for critical queries.

A good JOIN both returns **meaningful rows** and runs at a cost suited to the workload.

## 34. Common Mistakes

### 34.1. "CROSS JOIN automatically finds common keys"

No. It generates every pair regardless of keys.

### 34.2. "100 rows and 200 rows give 300 rows in a CROSS JOIN"

No. The result has 20,000 pairs.

### 34.3. "CROSS JOIN always returns at least as many rows as the left table"

No. If the right table is empty, the result is 0.

### 34.4. "NULL removes rows from CROSS JOIN"

No. NULL never drops pairs by itself; only a filter condition can do that.

### 34.5. "CROSS JOIN can take an ON clause like INNER JOIN"

No. `CROSS JOIN` does not accept `ON`/`USING` directly.

### 34.6. "INNER JOIN ON TRUE and LEFT JOIN ON TRUE are always identical to CROSS JOIN"

`INNER JOIN ON TRUE` is equivalent when no other factors intervene. `LEFT JOIN ON TRUE` differs when the right side is empty.

### 34.7. "Comma syntax in FROM is always easier to read"

No. Explicit syntax distinguishes intentional full pairing from a forgotten join condition.

### 34.8. "WHERE after CROSS JOIN forces the DB to materialize all pairs in RAM"

Not necessarily. The planner can push filters down and adjust the plan.

### 34.9. "LIMIT 10 guarantees only 10 pairs are processed"

No. ORDER BY, DISTINCT, aggregates, or other plans may process far more rows.

### 34.10. "DISTINCT fixes a missing JOIN condition"

No. DISTINCT may hide duplicate rows, but it does not restore the true relationship.

### 34.11. "If a day has no transactions, the report must omit that day"

Not always true. CROSS JOIN builds a `day × entity` scaffold, then LEFT JOIN preserves missing days.

### 34.12. "COALESCE NULL to 0 is always accurate"

No. A missing record might mean data has not arrived yet, not a value of 0.

### 34.13. "CROSS JOIN LATERAL always has m × n rows"

No. The right source can return a different number of rows for each left row.

### 34.14. "If the right side is empty, CROSS JOIN LATERAL still keeps the left row"

No. You need `LEFT JOIN LATERAL ... ON TRUE` to keep left rows when the function returns 0 rows.

### 34.15. "Adding an index makes CROSS JOINing billions of pairs cheap"

No. If you actually have to emit that volume of combinations, processing and transferring the data remains very expensive.

### 34.16. "ORDER BY is unnecessary because PostgreSQL always starts from the first left row"

No. Result order is never guaranteed without `ORDER BY`.

### 34.17. "The store × product product equals products actually sold"

No, unless business rules permit every pair. You need a junction table or proper filter.

## 35. Practice Exercises

### Exercise 1 — Predict the Output

A has 4 rows and B has 7 rows. How many rows does `A CROSS JOIN B` have?

**Hint:** 4 × 7 = 28.

### Exercise 2 — Empty Right Side

A has 10 rows and B has 0 rows. What does CROSS JOIN return?

**Answer:** 0 rows, not 10 rows with NULLs.

### Exercise 3 — Generate Color × Size Combinations

Use `cross_join_lab.colors` and `cross_join_lab.sizes` to display all 6 variants.

~~~sql
SELECT
    c.color_name,
    s.size_code
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s
ORDER BY c.color_id, s.sort_rank;
~~~

### Exercise 4 — Without ORDER BY

If you remove `ORDER BY` from exercise 3, can you guarantee the "Red–S" row appears first?

**Hint:** No.

### Exercise 5 — NULL

The left side has one `NULL` row and one `1` row; the right side has two rows. How many rows does CROSS JOIN produce?

**Hint:** 2 × 2 = 4.

### Exercise 6 — Rewrite Using a Key JOIN

A broken query:

~~~sql
SELECT o.order_id, c.customer_name
FROM orders AS o
CROSS JOIN customers AS c;
~~~

Rewrite it using `o.customer_id = c.customer_id`.

**Suggested solution:**

~~~sql
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id;
~~~

### Exercise 7 — INNER JOIN ON TRUE

When is `INNER JOIN b ON TRUE` equivalent to `CROSS JOIN b`?

**Hint:** When considering two sources and an always-true condition, in terms of the resulting pair multiset.

### Exercise 8 — Report Scaffold

There are 5 stores and 7 days. How many rows does the scaffold have before LEFT JOINing sales?

**Hint:** 35.

### Exercise 9 — Days Without Revenue

Why can `GROUP BY sale_day` alone on the transactions table not show days with no records?

**Hint:** There are no source rows for those days; you need a separate date set and a LEFT JOIN.

### Exercise 10 — WHERE on LEFT JOIN

In the `stores × days` query, what does adding `WHERE ds.revenue > 0` do to rows without transactions?

**Hint:** Rows where `ds.revenue` is NULL get dropped.

### Exercise 11 — generate_series

Generate three days Nov 14–16, 2026 and two times 09:00, 14:00. How many rows are in the result?

**Answer:** 3 × 2 = 6.

### Exercise 12 — Three Dimensions

20 stores, 500 products, 30 days. How many combinations?

**Hint:** 20 × 500 × 30 = 300,000.

### Exercise 13 — Invalid Combinations

If each store sells only 10 out of 500 available products, should you CROSS JOIN `20 × 500` directly or use `store_products` first?

**Hint:** Start with valid `store_products` pairs, then expand across days.

### Exercise 14 — Self CROSS JOIN

With 5 people, how many distinct ordered pairs are produced using `a.id <> b.id`?

**Hint:** 5 × 4 = 20.

### Exercise 15 — Unordered Pairs

With 5 people, how many pairs does `a.id < b.id` generate?

**Hint:** 5 × 4 / 2 = 10.

### Exercise 16 — Per-Row LATERAL

Colors have `color_id` 1 and 2; how many rows does `CROSS JOIN LATERAL generate_series(1,color_id)` return?

**Hint:** 1 + 2 = 3.

### Exercise 17 — LATERAL with Empty Array

An order has an empty `tags` array. Does it appear with `CROSS JOIN LATERAL unnest(tags)`?

**Hint:** No; use `LEFT JOIN LATERAL ... ON TRUE` if you need to keep the order.

### Exercise 18 — Calculate Before Running

Two tables have 80,000 and 50,000 rows. How many pairs does the Cartesian product have?

**Hint:** 4,000,000,000; this is a scale requiring very careful thought before executing.

### Exercise 19 — LIMIT

Why can `ORDER BY ... LIMIT 20` on a huge CROSS JOIN still be expensive?

**Hint:** The server may have to evaluate huge numbers of pairs to find the top 20 rows under the sort order.

### Exercise 20 — Wrong Sum

You compute `SUM(order.amount)` after CROSS JOINing `orders` with 3 category rows. How can the total amount go wrong?

**Hint:** Each order is repeated three times, tripling the SUM unless further filtered or constrained.

### Exercise 21 — DISTINCT

Why is `SUM(DISTINCT amount)` not a proper fix for exercise 20?

**Hint:** Two different orders can share the exact same `amount`, causing DISTINCT to wrongly discard valid data.

### Exercise 22 — EXPLAIN

You are about to run a CROSS JOIN on two large tables. Should you run `EXPLAIN` or `EXPLAIN ANALYZE` first to avoid accidentally triggering massive execution work?

**Hint:** `EXPLAIN` without ANALYZE first; only execute to measure once confirmed safe.

### Exercise 23 — Aliasing

Write a query CROSS JOINing two tables that both have `id`, returning distinct names to avoid ambiguity.

**Hint:** `SELECT a.id AS left_id, b.id AS right_id ...`.

### Exercise 24 — Data Scaffolding

If there is no revenue record, should you always `COALESCE(revenue,0)`?

**Hint:** Only when business rules guarantee no record means 0; missing ETL feeds may need to stay NULL.

### Exercise 25 — Multi-Tenant Safety

Why can CROSS JOINing all users with all stores create invalid pairs even when each user and store exists?

**Hint:** Allowed user–store relationships are not necessarily all-to-all; mapping/authorization is required.

## 36. Quick Reference Table

| Question | Answer |
|---|---|
| What does CROSS JOIN produce? | Every pair between two sources |
| Row count formula? | `m × n` |
| Three sources? | `m × n × p` |
| One side empty? | Empty result |
| Does NULL block pairs? | No |
| Are duplicate rows removed automatically? | No |
| Does CROSS JOIN have ON? | No |
| Is INNER JOIN ON TRUE equivalent? | Yes, in terms of row pairs |
| Can commas in FROM create a product? | Yes, without a linking condition |
| Is LEFT JOIN ON TRUE always equivalent? | No, differs when the right side is empty |
| Does CROSS JOIN guarantee order? | No |
| Want deterministic order? | Use ORDER BY |
| Want key-based pairing? | Appropriate INNER/LEFT JOIN ON |
| Want every day × store? | CROSS JOIN date dimension |
| Want to fill potentially missing data? | LEFT JOIN real data onto the scaffold |
| Want to generate dates/numbers? | generate_series |
| Want right source dependent on left row? | CROSS JOIN LATERAL |
| Want to keep left row if LATERAL returns 0? | LEFT JOIN LATERAL ON TRUE |
| Want unordered pairs? | Self CROSS JOIN with `a.id < b.id` |
| What risks do large CROSS JOINs carry? | Cardinality explosion, CPU/I/O/memory/network |
| Does LIMIT guarantee processing few pairs? | No |
| Does WHERE always run after materializing the product? | No, the planner can optimize |
| Does EXPLAIN run the full SELECT? | No |
| Does EXPLAIN ANALYZE run it? | Yes |
| Does DISTINCT fix a forgotten ON clause? | No |
| Can a dimension row count be 0/1/n? | Yes, understand input sources |
| Are generated combinations always business-valid? | No |
| What to check before a large CROSS JOIN? | Sizes, goal, filters, EXPLAIN, and load |

---

## Conclusion

**`CROSS JOIN` is the explicit way to write a Cartesian product in PostgreSQL**: every row on the left combines with every row on the right. With two sources of `m` and `n` rows, the result has `m × n` rows before subsequent filters or aggregations. It is a valuable tool for generating **all independent combinations**, such as color × size, day × time slot, test configurations, or day × store scaffolds for reporting.

However, **the exact same row multiplication can be a severe bug** when tables actually need to be joined by keys. CROSS JOIN does not infer relationships, does not drop NULLs or duplicate records, and does not guarantee output order. When source counts grow large, cardinality can explode, dragging down CPU, memory, I/O, network, and corrupting KPI aggregations. Neither `LIMIT` nor `DISTINCT` is a cure for a missing JOIN condition.

Use `INNER JOIN ... ON ...` when you need key-based relationships; use **CROSS JOIN** when you truly need every pair; use **LEFT JOIN** to preserve scaffolds with missing data; and use **LATERAL** when the right source depends on each left row. Before running large queries, forecast the combination count, isolate valid input sets, and inspect `EXPLAIN`. Mastering Cartesian products lets you harness PostgreSQL's combinatorial power while avoiding queries that emit millions of wrong rows or overload the server.
