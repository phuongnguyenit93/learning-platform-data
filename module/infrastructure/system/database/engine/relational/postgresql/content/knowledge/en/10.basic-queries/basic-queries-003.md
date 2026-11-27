# WHERE, Comparison Operators, and Logical Operators in PostgreSQL

## 1. Why Is `WHERE` Fundamental to Querying Data?

When a table has a few rows, you can run `SELECT * FROM orders` and visually scan for the orders you need. But when a table holds millions of orders, the application must describe clear **filter conditions** so PostgreSQL returns only the required rows.

The **`WHERE`** clause keeps rows that satisfy a **conditional expression** (*predicate*). Conditions can be built from:

- **Comparison operators**: `=`, `<>`, `!=`, `<`, `<=`, `>`, `>=`.
- **Logical operators**: `AND`, `OR`, `NOT`.
- **NULL checks**: `IS NULL`, `IS NOT NULL`, `IS DISTINCT FROM`.
- **Value sets**: `IN`, `NOT IN`, `ANY`, `ALL`, `EXISTS`.
- **Value ranges**: `BETWEEN`, `NOT BETWEEN`.
- **Text patterns**: `LIKE`, `ILIKE`.
- **Other expressions**: functions, calculations, and conditions correlated with subqueries.

Example:

```sql
SELECT order_id, customer_name, total_amount
FROM where_lab.orders
WHERE status = 'PAID'
  AND total_amount >= 250000
ORDER BY order_id;
```

Meaning: "Retrieve orders that are **paid** and have a total amount of **250,000 or more**, ordered by ascending order ID."

Two key points:

1. `WHERE` is a **logical expression**, not a loop you write imperatively. PostgreSQL chooses the physical execution strategy via its query plan.
2. A condition in PostgreSQL can evaluate to **TRUE, FALSE, or UNKNOWN (NULL)**. In `WHERE`, **only rows evaluating to TRUE** are kept.

The second point explains many common bugs when filtering columns that contain `NULL`.

## 2. Preparing the Practice Dataset

This lesson uses **PostgreSQL** and a dedicated test schema. The statements below assume you have privileges to create schemas and tables in a practice database; do not run them arbitrarily on production.

### 2.1. Creating the Orders Table

```sql
CREATE SCHEMA IF NOT EXISTS where_lab;

CREATE TABLE where_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    status text NOT NULL CHECK (
        status IN ('NEW', 'PAID', 'SHIPPED', 'CANCELLED')
    ),
    total_amount numeric(12,2) NOT NULL
        CHECK (total_amount >= 0),
    priority smallint NOT NULL
        CHECK (priority BETWEEN 1 AND 5),
    placed_at timestamptz NOT NULL,
    shipped_at timestamptz,
    region text
);
```

Explanation:

| Column | Type | Meaning |
| --- | --- | --- |
| `order_id` | `bigint` | Unique order ID |
| `customer_name` | `text` | Customer name |
| `status` | `text` | Status from a fixed set of values |
| `total_amount` | `numeric(12,2)` | Order total amount |
| `priority` | `smallint` | Priority from 1 to 5 |
| `placed_at` | `timestamptz` | Timestamp when the order was placed |
| `shipped_at` | `timestamptz`, nullable | Timestamp when handed over to carrier, if any |
| `region` | `text`, nullable | Region, possibly not yet entered |

`status` and `total_amount` have `NOT NULL`. However, `region` and `shipped_at` allow `NULL`, which is very useful for practicing **three-valued logic**.

### 2.2. Loading Sample Data

```sql
INSERT INTO where_lab.orders
    (
        order_id,
        customer_name,
        status,
        total_amount,
        priority,
        placed_at,
        shipped_at,
        region
    )
VALUES
    (
        101, 'An', 'NEW', 120000.00, 3,
        TIMESTAMPTZ '2026-10-01 09:00:00+07',
        NULL, 'Hanoi'
    ),
    (
        102, 'Bình', 'PAID', 350000.00, 5,
        TIMESTAMPTZ '2026-10-02 10:30:00+07',
        NULL, 'Ho Chi Minh City'
    ),
    (
        103, 'Chi', 'SHIPPED', 250000.00, 4,
        TIMESTAMPTZ '2026-10-02 15:00:00+07',
        TIMESTAMPTZ '2026-10-04 11:00:00+07',
        'Da Nang'
    ),
    (
        104, 'Dung', 'CANCELLED', 95000.00, 2,
        TIMESTAMPTZ '2026-10-03 11:30:00+07',
        NULL, NULL
    ),
    (
        105, 'Em', 'PAID', 80000.00, 1,
        TIMESTAMPTZ '2026-10-03 20:00:00+07',
        NULL, 'Hanoi'
    ),
    (
        106, 'Phúc', 'SHIPPED', 550000.00, 5,
        TIMESTAMPTZ '2026-10-04 08:00:00+07',
        TIMESTAMPTZ '2026-10-05 12:00:00+07',
        'Ho Chi Minh City'
    ),
    (
        107, 'Giang', 'NEW', 250000.00, 2,
        TIMESTAMPTZ '2026-10-05 14:00:00+07',
        NULL, 'Da Nang'
    ),
    (
        108, 'Hà', 'PAID', 250000.00, 3,
        TIMESTAMPTZ '2026-10-06 09:00:00+07',
        NULL, NULL
    );
```

Timestamps are recorded with the `+07` offset so date-filtering examples have unambiguous meaning. Once you run the load script, re-running the exact `INSERT` will violate the primary key. Practice on a fresh database or manage reloads intentionally.

Summary of the eight rows:

| ID | Customer | Status | Total Amount | Priority | Region |
| ---: | --- | --- | ---: | ---: | --- |
| 101 | An | NEW | 120,000 | 3 | Hanoi |
| 102 | Bình | PAID | 350,000 | 5 | Ho Chi Minh City |
| 103 | Chi | SHIPPED | 250,000 | 4 | Da Nang |
| 104 | Dung | CANCELLED | 95,000 | 2 | NULL |
| 105 | Em | PAID | 80,000 | 1 | Hanoi |
| 106 | Phúc | SHIPPED | 550,000 | 5 | Ho Chi Minh City |
| 107 | Giang | NEW | 250,000 | 2 | Da Nang |
| 108 | Hà | PAID | 250,000 | 3 | NULL |

### 2.3. `SELECT ... WHERE` Syntax Template

```sql
SELECT <column_list>
FROM <table_name>
WHERE <condition>
ORDER BY <sort_column>;
```

Using the sample table:

```sql
SELECT order_id, customer_name, total_amount
FROM where_lab.orders
WHERE total_amount > 200000
ORDER BY order_id;
```

The result includes IDs `102, 103, 106, 107, 108` because their total amounts are greater than 200,000.

**Without `ORDER BY`, SQL does not guarantee the order of returned rows.** Avoid relying on `INSERT` order or physical table order.

## 3. Basic Comparison Operators

PostgreSQL supports these operators:

| Operator | Meaning | Example |
| --- | --- | --- |
| `=` | Equal | `status = 'PAID'` |
| `<>` | Not equal | `status <> 'CANCELLED'` |
| `!=` | Not equal (accepted by PostgreSQL) | `status != 'CANCELLED'` |
| `>` | Greater than | `total_amount > 100000` |
| `>=` | Greater than or equal | `total_amount >= 100000` |
| `<` | Less than | `priority < 3` |
| `<=` | Less than or equal | `priority <= 3` |

`<>` is the standard SQL **not equal** operator. PostgreSQL also accepts `!=`; both generally have the same meaning.

### 3.1. `=`: Matching an Exact Status

```sql
SELECT order_id, customer_name, status
FROM where_lab.orders
WHERE status = 'PAID'
ORDER BY order_id;
```

Result:

| order_id | customer_name | status |
| ---: | --- | --- |
| 102 | Bình | PAID |
| 105 | Em | PAID |
| 108 | Hà | PAID |

This condition is a value comparison, **not an assignment**. In `WHERE`, `=` does not mean "set status to PAID."

### 3.2. `<>` and `!=`: Not Equal

```sql
SELECT order_id, status
FROM where_lab.orders
WHERE status <> 'CANCELLED'
ORDER BY order_id;
```

The result includes all IDs **except 104**, since 104 is `CANCELLED`.

You can write:

```sql
WHERE status != 'CANCELLED'
```

but pick one convention across the project; `<>` is often easier to read for people familiar with standard SQL.

### 3.3. Inequality Comparisons and Boundaries

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount >= 250000
ORDER BY order_id;
```

Kept IDs: `102, 103, 106, 107, 108`.

Difference between `>` and `>=`:

- `total_amount > 250000` keeps `102` and `106`.
- `total_amount >= 250000` also keeps `103`, `107`, and `108`, because those three orders total exactly 250,000.

When filtering prices, quantities, or timestamps, an off-by-one equals sign causes business bugs at the **range boundary**.

### 3.4. Comparing Values with Compatible Data Types

The `total_amount` column is `numeric(12,2)`, so:

```sql
WHERE total_amount >= 250000.00
```

expresses an exact decimal monetary boundary. Avoid sending monetary values computed with binary floating-point `double` in the application and expecting PostgreSQL to recover the original precision.

For `timestamptz` timestamps, compare against timestamp literals with an explicit time zone rather than date-time strings with ambiguous time zone semantics.

## 4. `WHERE` Keeps TRUE, Not FALSE or UNKNOWN

Many SQL learners think conditions only have two outcomes: true or false. In reality, PostgreSQL uses **three-valued logic** for expressions involving `NULL`:

- **TRUE**: the condition holds.
- **FALSE**: the condition does not hold.
- **UNKNOWN** (represented as `NULL` in boolean results): whether it holds is unknown.

Summary table:

| `WHERE` Expression Outcome | Row Kept? |
| --- | --- |
| TRUE | **Yes** |
| FALSE | No |
| UNKNOWN / NULL | No |

Example:

```sql
SELECT
    order_id,
    region,
    region = 'Hanoi' AS is_ha_noi
FROM where_lab.orders
ORDER BY order_id;
```

For rows `104` and `108`, `region` is `NULL`; the expression `region = 'Hanoi'` returns **NULL/UNKNOWN**, not `false`.

Filtering:

```sql
SELECT order_id, region
FROM where_lab.orders
WHERE region = 'Hanoi'
ORDER BY order_id;
```

returns `101` and `105`. Rows with `NULL` region are not kept, because it cannot be determined whether they belong to Hanoi.

### 4.1. `NULL` Is Not Zero or an Empty String

`NULL` means missing/unknown/not applicable data, depending on the model. The following values are **not equivalent**:

```sql
SELECT
    0 IS NULL AS zero_is_null,
    '' IS NULL AS empty_string_is_null,
    NULL IS NULL AS null_is_null;
```

`0` is a number, `''` is an empty string, and `NULL` is SQL's special marker. Do not overload `NULL` to simultaneously represent "not entered", "not applicable", and "pending" if business logic needs to distinguish them.

## 5. Checking NULL with `IS NULL` and `IS NOT NULL`

### 5.1. Why Not Use `= NULL`?

Incorrect:

```sql
SELECT order_id
FROM where_lab.orders
WHERE region = NULL;
```

In standard SQL logic, `region = NULL` evaluates to UNKNOWN even when `region` itself is NULL. Thus the query fails to return rows with NULL region as beginners often expect.

Correct:

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE region IS NULL
ORDER BY order_id;
```

Result: `104` and `108`.

### 5.2. `IS NOT NULL`

```sql
SELECT order_id, region
FROM where_lab.orders
WHERE region IS NOT NULL
ORDER BY order_id;
```

The query returns rows that actually have a region value: `101, 102, 103, 105, 106, 107`.

Similarly, to find orders that have a shipping timestamp:

```sql
SELECT order_id, shipped_at
FROM where_lab.orders
WHERE shipped_at IS NOT NULL
ORDER BY order_id;
```

On the sample dataset: `103` and `106`.

**Business note:** `shipped_at IS NOT NULL` checks whether a shipping timestamp exists; it does not automatically guarantee the order status is still `SHIPPED`. Synchronization rules between those fields must be enforced by application logic or database constraints.

### 5.3. `NOT (=)` Does Not Replace `IS NULL`

```sql
-- Does not return rows where region is NULL:
SELECT order_id
FROM where_lab.orders
WHERE NOT (region = 'Hanoi')
ORDER BY order_id;
```

`NOT UNKNOWN` is still **UNKNOWN**, so rows 104 and 108 are still filtered out. To include NULL regions as well, write explicitly:

```sql
SELECT order_id
FROM where_lab.orders
WHERE region <> 'Hanoi'
   OR region IS NULL
ORDER BY order_id;
```

Another PostgreSQL option is introduced in the next section: `IS DISTINCT FROM`.

## 6. NULL-Aware Comparisons with `IS DISTINCT FROM`

PostgreSQL supports:

```sql
a IS DISTINCT FROM b
a IS NOT DISTINCT FROM b
```

These are **null-safe** comparisons: they return TRUE or FALSE instead of UNKNOWN when `NULL` is involved.

### 6.1. Comparison Table

| `a` | `b` | `a = b` | `a IS DISTINCT FROM b` | `a IS NOT DISTINCT FROM b` |
| --- | --- | --- | --- | --- |
| 1 | 1 | TRUE | FALSE | TRUE |
| 1 | 2 | FALSE | TRUE | FALSE |
| 1 | NULL | UNKNOWN | TRUE | FALSE |
| NULL | NULL | UNKNOWN | FALSE | TRUE |

Example:

```sql
SELECT
    NULL::integer = NULL::integer AS regular_equal,
    NULL::integer IS NOT DISTINCT FROM NULL::integer
        AS null_safe_equal,
    NULL::integer IS DISTINCT FROM 10
        AS null_safe_different;
```

`IS NOT DISTINCT FROM` is helpful when you intentionally want to treat **two NULL values** as equal in a comparison.

### 6.2. Finding Regions Other Than Hanoi, Including Unspecified

```sql
SELECT order_id, region
FROM where_lab.orders
WHERE region IS DISTINCT FROM 'Hanoi'
ORDER BY order_id;
```

IDs: `102, 103, 104, 106, 107, 108`.

Compared to `WHERE region <> 'Hanoi'`, this query **also includes 104 and 108**, because NULL is considered distinct from a concrete string value.

**The right choice depends on business meaning:**

- "Customer belongs to a **known** region other than Hanoi" → `region <> 'Hanoi'`.
- "Customer **does not have region equal to Hanoi**, including unentered regions" → `region IS DISTINCT FROM 'Hanoi'`.

Do not blindly replace every `<>` with `IS DISTINCT FROM`. The two conditions express different rules when NULLs exist.

## 7. Logical Operators: `AND`, `OR`, `NOT`

### 7.1. `AND`: All Conditions Must Hold

```sql
SELECT
    order_id,
    status,
    total_amount
FROM where_lab.orders
WHERE status = 'PAID'
  AND total_amount >= 250000
ORDER BY order_id;
```

Keeps `102` and `108`. Order `105` is paid but only 80,000, so it is excluded.

`AND` means "**and**": both conditions must evaluate to TRUE.

### 7.2. `OR`: At Least One Condition Holds

```sql
SELECT order_id, status, priority
FROM where_lab.orders
WHERE status = 'NEW'
   OR priority = 5
ORDER BY order_id;
```

Result: `101, 102, 106, 107`.

- `101` and `107` have status NEW.
- `102` and `106` have priority 5.

A row satisfying both conditions still appears **only once** from that row filter—it is not duplicated just because `OR` was used.

### 7.3. `NOT`: Negating a Condition

```sql
SELECT order_id, status
FROM where_lab.orders
WHERE NOT (status = 'CANCELLED')
ORDER BY order_id;
```

Since `status` in the sample table is always `NOT NULL`, this is equivalent to `status <> 'CANCELLED'` and returns the seven IDs other than 104.

However, when a column can be NULL, `NOT` does not turn UNKNOWN into TRUE—a crucial detail when writing exclusion filters.

### 7.4. Operator Precedence: `NOT`, `AND`, `OR`

In standard PostgreSQL logical expressions:

1. `NOT` has higher precedence than `AND`.
2. `AND` has higher precedence than `OR`.
3. Parentheses `(...)` let you group conditions explicitly.

Compare these two clauses:

```sql
-- Meaning: (NEW and priority 5) or PAID
WHERE status = 'NEW'
  AND priority = 5
   OR status = 'PAID'
```

and:

```sql
-- Meaning: NEW and (priority 5 or PAID)
WHERE status = 'NEW'
  AND (priority = 5 OR status = 'PAID')
```

They are **not equivalent**. On the sample dataset, the first expression returns the PAID orders because of the `OR status = 'PAID'` branch; the second returns no rows because a single status column cannot be both NEW and PAID.

**Recommendation:** whenever `WHERE` combines both `AND` and `OR`, **always use parentheses to express business intent**, even if you know the precedence rules by heart.

## 8. Three-Valued Logic and Truth Tables

When a condition can evaluate to UNKNOWN, the outcomes of `AND`, `OR`, and `NOT` follow three-valued logic.

### 8.1. Truth Tables for `AND` and `OR`

Using notation:

- **T** = TRUE.
- **F** = FALSE.
- **U** = UNKNOWN/NULL.

| A | B | A AND B | A OR B |
| --- | --- | --- | --- |
| T | T | T | T |
| T | F | F | T |
| T | U | U | T |
| F | T | F | T |
| F | F | F | F |
| F | U | F | U |
| U | T | U | T |
| U | F | F | U |
| U | U | U | U |

For `NOT`:

| A | NOT A |
| --- | --- |
| T | F |
| F | T |
| U | U |

Two intuitive rules:

- `FALSE AND UNKNOWN = FALSE` because the whole expression is already guaranteed false.
- `TRUE OR UNKNOWN = TRUE` because the whole expression is already guaranteed true.

However:

- `TRUE AND UNKNOWN = UNKNOWN`.
- `FALSE OR UNKNOWN = UNKNOWN`.
- `NOT UNKNOWN = UNKNOWN`.

### 8.2. Test It Directly in PostgreSQL

```sql
SELECT
    TRUE AND NULL::boolean AS true_and_unknown,
    FALSE AND NULL::boolean AS false_and_unknown,
    TRUE OR NULL::boolean AS true_or_unknown,
    FALSE OR NULL::boolean AS false_or_unknown,
    NOT NULL::boolean AS not_unknown;
```

Result:

| Expression | Value |
| --- | --- |
| `TRUE AND NULL` | NULL |
| `FALSE AND NULL` | FALSE |
| `TRUE OR NULL` | TRUE |
| `FALSE OR NULL` | NULL |
| `NOT NULL` | NULL |

When displayed in `psql`, a NULL cell may appear blank or formatted per display settings. Do not confuse a blank NULL cell with an empty string.

### 8.3. Combining `OR` with a Nullable Column

```sql
SELECT order_id, region, status
FROM where_lab.orders
WHERE region = 'Hanoi'
   OR status = 'CANCELLED'
ORDER BY order_id;
```

Result: `101, 104, 105`.

Order 104 has `region = NULL`, but `status = 'CANCELLED'` is TRUE. `UNKNOWN OR TRUE` yields TRUE, so order 104 is still kept.

Conversely:

```sql
SELECT order_id, region, status
FROM where_lab.orders
WHERE region = 'Hanoi'
  AND status = 'CANCELLED'
ORDER BY order_id;
```

No rows returned: Hanoi orders are not CANCELLED, and the CANCELLED order has NULL region, making `UNKNOWN AND TRUE` evaluate to UNKNOWN.

### 8.4. `IS TRUE`, `IS FALSE`, and `IS UNKNOWN`

To test the **state of a boolean expression**, use:

```sql
SELECT
    NULL::boolean IS TRUE AS is_true,
    NULL::boolean IS FALSE AS is_false,
    NULL::boolean IS UNKNOWN AS is_unknown;
```

Result: `false`, `false`, `true`.

An expression:

```sql
WHERE (region = 'Hanoi') IS NOT TRUE
```

keeps rows where `region = 'Hanoi'` is **not TRUE**, including both FALSE and UNKNOWN. The result matches `region IS DISTINCT FROM 'Hanoi'` in this specific comparison; however, `IS DISTINCT FROM` usually communicates null-safe comparison semantics more clearly.

## 9. `BETWEEN` and `NOT BETWEEN`: Range Filtering

### 9.1. `BETWEEN` Is Inclusive of Both Endpoints

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount BETWEEN 250000 AND 350000
ORDER BY order_id;
```

Result: `102, 103, 107, 108`.

`BETWEEN 250000 AND 350000` is logically equivalent to:

```sql
WHERE total_amount >= 250000
  AND total_amount <= 350000
```

Both **250000** and **350000** are included.

### 9.2. `NOT BETWEEN`

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount NOT BETWEEN 250000 AND 350000
ORDER BY order_id;
```

Returns `101, 104, 105, 106` because their total amounts lie outside [250000, 350000].

If the column or either bound is NULL, the expression can return UNKNOWN; `NOT BETWEEN` does not automatically pass all NULL rows through.

### 9.3. The Lower Bound Must Come Before the Upper Bound

Normally:

```sql
WHERE total_amount BETWEEN 350000 AND 250000
```

does not mean "from 250000 to 350000 in reverse." For non-NULL numbers, zero rows satisfy this condition.

PostgreSQL offers `BETWEEN SYMMETRIC` if you need to accept bounds in either order:

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount BETWEEN SYMMETRIC 350000 AND 250000
ORDER BY order_id;
```

On the sample set, the result matches the range 250000 to 350000.

Even so, application code should usually **validate/order the two input bounds** beforehand rather than relying on special syntax to mask invalid user input.

### 9.4. Date/Time Ranges: Avoiding End-Date Mistakes

With `placed_at timestamptz`, writing:

```sql
WHERE placed_at BETWEEN
    TIMESTAMPTZ '2026-10-02 00:00:00+07'
    AND TIMESTAMPTZ '2026-10-04 00:00:00+07'
```

does **not** cover the entire day of Oct 4: it only includes up to exact midnight 00:00 of that day.

To include **all of Oct 2, Oct 3, and Oct 4 in timezone +07**, use a **half-open interval**:

```sql
SELECT order_id, placed_at
FROM where_lab.orders
WHERE placed_at >= TIMESTAMPTZ '2026-10-02 00:00:00+07'
  AND placed_at <  TIMESTAMPTZ '2026-10-05 00:00:00+07'
ORDER BY order_id;
```

Result: `102, 103, 104, 105, 106`.

Using `>= start AND < next_day` avoids missing timestamps with fractional seconds late in the day. In multi-timezone systems, **"day" must be defined in the business timezone**; do not blindly hard-code `+07` for global data.

## 10. `IN` and `NOT IN`: Comparing Against a Set of Values

### 10.1. `IN` Is Equivalent to Multiple `OR` Branches

```sql
SELECT order_id, status
FROM where_lab.orders
WHERE status IN ('PAID', 'SHIPPED')
ORDER BY order_id;
```

Result: `102, 103, 105, 106, 108`.

For non-NULL values, this condition is equivalent to:

```sql
WHERE status = 'PAID'
   OR status = 'SHIPPED'
```

`IN` keeps SQL compact and readable when a column must belong to an allowed set of values.

### 10.2. Combining `IN` with `AND`

```sql
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE status IN ('PAID', 'SHIPPED')
  AND total_amount >= 250000
ORDER BY order_id;
```

Result: `102, 103, 106, 108`.

Order `105` is PAID, yet totals only 80000 and is filtered out.

### 10.3. `NOT IN`: Watch Out for NULL

The condition:

```sql
WHERE status NOT IN ('CANCELLED', 'SHIPPED')
```

returns statuses other than those two values; since `status` is NOT NULL in the sample table, the result is `101, 102, 105, 107, 108`.

However, if the list contains **NULL**, the semantics are counterintuitive:

```sql
SELECT
    1 NOT IN (2, NULL) AS result_one,
    2 NOT IN (2, NULL) AS result_two,
    1 IN (2, NULL) AS result_three;
```

Result:

| Expression | Value |
| --- | --- |
| `1 NOT IN (2, NULL)` | UNKNOWN/NULL |
| `2 NOT IN (2, NULL)` | FALSE |
| `1 IN (2, NULL)` | UNKNOWN/NULL |

Because `1` does not equal `2` yet it is unknown whether `1` equals the NULL element, `NOT IN` returns UNKNOWN. In `WHERE`, UNKNOWN is dropped.

**Very common bug:** writing `NOT IN (SELECT nullable_column FROM ...)` when the subquery can emit NULL, causing the outer query to return fewer rows than expected—or zero rows altogether.

### 10.4. Empty Lists and Dynamic Parameters

Syntax:

```sql
-- Invalid:
WHERE status IN ()
```

is not valid SQL in PostgreSQL. If the application receives a status list that may be empty, explicitly decide what it means:

- Empty list means **return no rows**.
- Empty list means **apply no filter**.
- Empty list is **invalid input that should raise an error**.

Do not construct `IN ()` in SQL strings. You can use `= ANY($1::text[])` with a properly bound array parameter, or build dynamic predicates safely via a structured API, depending on requirements.

## 11. `ANY`, `ALL`, and Array Comparison Operators

PostgreSQL lets you compare a single value against multiple elements:

```sql
expression operator ANY (array_expression)
expression operator ALL (array_expression)
```

### 11.1. `= ANY` with an Array

```sql
SELECT order_id, status
FROM where_lab.orders
WHERE status = ANY (ARRAY['PAID', 'SHIPPED']::text[])
ORDER BY order_id;
```

The result matches `status IN ('PAID', 'SHIPPED')` on this set of values.

This form is handy when the application binds **a single array parameter** through the driver rather than splicing `'PAID','SHIPPED'` into SQL.

### 11.2. `> ALL`

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount > ALL (ARRAY[100000, 200000]::numeric[])
ORDER BY order_id;
```

The row's total amount must exceed **both 100000 and 200000**, i.e., greater than 200000. Result: `102, 103, 106, 107, 108`.

`ALL` corresponds to "**every element**", while `ANY` corresponds to "**at least one element**" under the chosen operator.

### 11.3. Empty Sets and NULL

Some results can surprise beginners:

```sql
SELECT
    'PAID' = ANY (ARRAY[]::text[]) AS any_empty,
    10 > ALL (ARRAY[]::integer[]) AS all_empty,
    10 = ANY (ARRAY[NULL]::integer[]) AS any_null;
```

| Expression | Result |
| --- | --- |
| `x = ANY(empty_array)` | FALSE |
| `x > ALL(empty_array)` | TRUE |
| `10 = ANY(ARRAY[NULL])` | UNKNOWN/NULL |

This follows logically from "there exists at least one element satisfying the condition" and "every element satisfies the condition." When working with arrays containing NULLs, the result depends on the operator and elements; never assume every NULL behaves like FALSE.

**Distinction:** `ANY (subquery)` also exists with different syntax; when passing an array parameter, make sure you write `ANY(array_expression)`.

## 12. `EXISTS` and `NOT EXISTS`: Filtering by Related Row Existence

When you want to know whether matching rows exist in another table, `EXISTS` usually expresses intent more clearly than building a list and trying `IN` or `NOT IN`.

### 12.1. Creating an Illustrative Payments Table

```sql
CREATE TABLE where_lab.payments (
    payment_id bigint PRIMARY KEY,
    order_id bigint NOT NULL
        REFERENCES where_lab.orders(order_id),
    paid_amount numeric(12,2) NOT NULL
        CHECK (paid_amount >= 0),
    state text NOT NULL
        CHECK (state IN ('PENDING', 'CONFIRMED'))
);

INSERT INTO where_lab.payments
    (payment_id, order_id, paid_amount, state)
VALUES
    (1001, 102, 350000, 'CONFIRMED'),
    (1002, 103, 250000, 'CONFIRMED'),
    (1003, 106, 550000, 'CONFIRMED'),
    (1004, 108, 250000, 'PENDING');
```

This dataset is solely for practicing queries. `orders.status` and `payments.state` do not necessarily model full real-world payment workflows (such as sync delays or split/multiple payments).

### 12.2. Finding Orders with a Confirmed Payment

```sql
SELECT o.order_id, o.customer_name
FROM where_lab.orders AS o
WHERE EXISTS (
    SELECT 1
    FROM where_lab.payments AS p
    WHERE p.order_id = o.order_id
      AND p.state = 'CONFIRMED'
)
ORDER BY o.order_id;
```

Result: `102, 103, 106`.

`EXISTS` returns TRUE if the subquery finds **at least one** matching row; the specific expression inside `SELECT 1` does not matter for the existence check.

The subquery uses `p.order_id = o.order_id` to link to each outer row, making it a **correlated subquery**.

### 12.3. Finding Orders with No Payments Yet

```sql
SELECT o.order_id, o.customer_name
FROM where_lab.orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM where_lab.payments AS p
    WHERE p.order_id = o.order_id
)
ORDER BY o.order_id;
```

Result: `101, 104, 105, 107`.

Order 108 has a `PENDING` payment, so it is **not** in the "no payments at all" group. If you want "no CONFIRMED payment yet", add `AND p.state = 'CONFIRMED'` inside `NOT EXISTS`; order 108 will then be returned.

### 12.4. Why Is `NOT EXISTS` Often Safer Than `NOT IN` with NULLs?

`NOT EXISTS` tests **whether any matching row exists**; it does not suffer from "one NULL in the list turning the entire `NOT IN` into UNKNOWN" as happens with nullable subqueries.

That does not mean every `NOT EXISTS` is always faster than `NOT IN`. PostgreSQL's optimizer chooses among multiple execution strategies; pick the syntax that **matches the intended semantics first**, then inspect `EXPLAIN` against real data when needed.

## 13. Text Filtering with `LIKE` and `ILIKE`

### 13.1. `LIKE`: Pattern Matching

`LIKE` supports two wildcards:

| Wildcard | Meaning |
| --- | --- |
| `%` | Zero or more characters |
| `_` | Exactly one character per pattern-matching rules |

Example matching names starting with A:

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE customer_name LIKE 'A%'
ORDER BY order_id;
```

Result: `101, An`.

Names ending in `n`:

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE customer_name LIKE '%n'
ORDER BY order_id;
```

This matches `An`. The leading `%` permits zero or more characters before `n`.

### 13.2. `ILIKE`: Case-Insensitive Matching

`ILIKE` is a PostgreSQL extension:

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE customer_name ILIKE 'a%'
ORDER BY order_id;
```

The query finds `An` even though the pattern uses lowercase `a`.

**Do not confuse `ILIKE` with automatic accent/diacritic stripping.** It performs case-insensitive pattern matching according to the applicable locale; it does not guarantee `'nguyen'` will match `'Nguyễn'`. If business rules require accent-insensitive search, design a dedicated normalization/search strategy.

### 13.3. Matching Literal `%` or `_` Characters

Because `%` and `_` are wildcards, escape them when searching for literal characters. Example:

```sql
SELECT
    'A_B' LIKE 'A!_B' ESCAPE '!' AS match_literal_underscore,
    'A%B' LIKE 'A!%B' ESCAPE '!' AS match_literal_percent;
```

Both return TRUE. `ESCAPE '!'` states that `!` escapes the following pattern character. In application code, wildcard escaping must be handled separately from **SQL parameter binding**: binding safely passes values, yet does not automatically turn `%` into a literal character for `LIKE`.

### 13.4. `NOT LIKE`, `NOT ILIKE`, and NULL

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE customer_name NOT ILIKE 'a%'
ORDER BY order_id;
```

Because `customer_name` is `NOT NULL`, the query returns names not starting with `A` under `ILIKE` rules.

If a string column allows NULL, `NULL NOT LIKE 'A%'` evaluates to UNKNOWN, so that row **is not kept automatically**. To include NULLs in an exclusion result, add `IS NULL` or use an appropriate rule.

### 13.5. Collation Affects Text Comparisons

`=`, `<`, `>`, `ORDER BY`, and several text operations depend on collation rules. Particularly with ICU nondeterministic collations, equality between byte-different strings can be defined differently from `"C"` collation.

Example requiring code-point ordering:

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE customer_name COLLATE "C" > 'B' COLLATE "C"
ORDER BY customer_name COLLATE "C", order_id;
```

This does not give natural language-specific sorting. Choose a collation matching data semantics, and note that `LIKE`/`ILIKE` support on certain nondeterministic collations also depends on PostgreSQL version.

## 14. Common Combined Conditions

### 14.1. Using Parentheses to Express Requirements

Requirement: "Fetch orders that are **PAID or SHIPPED**, but only if **total amount is at least 250,000**."

Correct:

```sql
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE (status = 'PAID' OR status = 'SHIPPED')
  AND total_amount >= 250000
ORDER BY order_id;
```

Result: `102, 103, 106, 108`.

Shorter form:

```sql
WHERE status IN ('PAID', 'SHIPPED')
  AND total_amount >= 250000
```

Wrong if you omit parentheses like this:

```sql
WHERE status = 'PAID'
   OR status = 'SHIPPED'
  AND total_amount >= 250000
```

Because `AND` binds tighter than `OR`, this is equivalent to:

```sql
WHERE status = 'PAID'
   OR (
       status = 'SHIPPED'
       AND total_amount >= 250000
   )
```

It returns **every PAID order**, including order `105` with only 80,000—violating the original requirement.

### 14.2. Combining `NOT` with Compound Expressions

Requirement: "Find orders that are **not PAID** and **do not have priority 4 or higher**."

```sql
SELECT order_id, status, priority
FROM where_lab.orders
WHERE NOT (
    status = 'PAID'
    OR priority >= 4
)
ORDER BY order_id;
```

Result: `101, 104, 107`.

By De Morgan's laws in SQL's three-valued logic, this can be written as:

```sql
WHERE status <> 'PAID'
  AND priority < 4
```

Since `status` and `priority` are non-NULL in the sample table, both forms match here. When adding predicates on nullable columns, inspect the impact of UNKNOWN carefully; never automatically swap `NOT (column = value)` for `IS DISTINCT FROM` without checking NULL requirements.

### 14.3. Filtering Paid Orders Not Yet Shipped

```sql
SELECT order_id, status, shipped_at
FROM where_lab.orders
WHERE status = 'PAID'
  AND shipped_at IS NULL
ORDER BY order_id;
```

Result: `102, 105, 108`.

This is a very common filter pattern: combining a status check with an optional timestamp column. Writing `shipped_at = NULL` would fail.

### 14.4. Using `COALESCE` to Supply a Fallback for NULL

```sql
SELECT order_id, region
FROM where_lab.orders
WHERE COALESCE(region, 'UNSPECIFIED') = 'UNSPECIFIED'
ORDER BY order_id;
```

Result: `104` and `108`.

However, if a row literally stores the string `'UNSPECIFIED'`, this query keeps it too; thus its semantics **differ** from `region IS NULL`.

`COALESCE` produces a fallback value at evaluation time; it does not store that string in the table. When you specifically want rows with no region, `IS NULL` is clearer and can more easily leverage an appropriate index.

## 15. Time, Time Zones, and Boundary Conditions

### 15.1. Comparing `date`, `timestamp`, and `timestamptz`

In PostgreSQL:

- `date`: calendar date with no time-of-day component.
- `timestamp without time zone`: date and time without time zone metadata.
- `timestamp with time zone` / `timestamptz`: instant interpreted with time zone semantics; displayed according to the session's time zone.

With `placed_at timestamptz`, the expression:

```sql
WHERE placed_at >= TIMESTAMPTZ '2026-10-03 00:00:00+07'
```

sets an unambiguous point in time. Avoid passing a bare string `'2026-10-03'` without knowing how PostgreSQL casts and interprets its time zone in that context.

### 15.2. Selecting One Day in Vietnam Time

Example selecting the entire day of 2026-10-03 in `+07`:

```sql
SELECT order_id, placed_at
FROM where_lab.orders
WHERE placed_at >= TIMESTAMPTZ '2026-10-03 00:00:00+07'
  AND placed_at <  TIMESTAMPTZ '2026-10-04 00:00:00+07'
ORDER BY order_id;
```

Result: `104` and `105`.

Using a half-open interval avoids writing `23:59:59.999999` at day's end, which breaks if microsecond precision varies or day boundaries shift.

### 15.3. Why `placed_at::date = ...` Is Not Always Ideal

```sql
SELECT order_id
FROM where_lab.orders
WHERE (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
      = DATE '2026-10-03';
```

This makes sense when converting each timestamp into a **local calendar date**. However, it applies an **expression to the column**, preventing a standard B-tree index on `placed_at` from matching directly as a time-range predicate.

When exact start/end instants can be computed, `placed_at >= start AND placed_at < end` usually utilizes an index on `placed_at` much more readily. If an expression index is needed, evaluate the expression's properties and planner behavior separately.

### 15.4. Intervals Involving DST

The `+07` offset has no DST transitions in Vietnam today, but other time zones observe daylight saving time. To filter "one local day" in a DST-observing time zone, never assume every day is 24 hours long. Determine the **start of that day and start of the next day in the business time zone**, then filter timestamps with a half-open range.

## 16. `WHERE` with `JOIN` and Predicate Placement

`WHERE` can appear in multi-table queries. With `INNER JOIN`, filter conditions on a joined table can often live in either `ON` or `WHERE` and yield the same row set. With **`LEFT JOIN`**, however, placement changes the semantics.

### 16.1. `INNER JOIN`

```sql
SELECT
    o.order_id,
    o.status,
    p.payment_id,
    p.state
FROM where_lab.orders AS o
JOIN where_lab.payments AS p
    ON p.order_id = o.order_id
WHERE p.state = 'CONFIRMED'
ORDER BY o.order_id;
```

Result includes orders `102, 103, 106` with confirmed payments.

`ON` defines how tables relate; `WHERE` defines which resulting rows to keep.

### 16.2. `LEFT JOIN` with a Condition in `WHERE`

```sql
SELECT
    o.order_id,
    p.payment_id,
    p.state
FROM where_lab.orders AS o
LEFT JOIN where_lab.payments AS p
    ON p.order_id = o.order_id
WHERE p.state = 'CONFIRMED'
ORDER BY o.order_id;
```

Even with `LEFT JOIN`, `WHERE p.state = 'CONFIRMED'` drops rows without payments because `p.state` is NULL on the right. Once again, the result has only `102, 103, 106`.

### 16.3. Placing the Condition Inside `ON` Preserves Left Rows

To get **all orders**, matching only CONFIRMED payments if present:

```sql
SELECT
    o.order_id,
    o.status,
    p.payment_id,
    p.state
FROM where_lab.orders AS o
LEFT JOIN where_lab.payments AS p
    ON p.order_id = o.order_id
   AND p.state = 'CONFIRMED'
ORDER BY o.order_id;
```

Now all 8 orders are preserved; orders lacking a CONFIRMED payment receive NULL in columns from `p`.

**Rule:** with outer joins, never casually move a predicate between `ON` and `WHERE`. The difference can drop the very unmatched rows `LEFT JOIN` was meant to preserve.

### 16.4. Finding Rows with No Related Record

```sql
SELECT o.order_id
FROM where_lab.orders AS o
LEFT JOIN where_lab.payments AS p
    ON p.order_id = o.order_id
WHERE p.payment_id IS NULL
ORDER BY o.order_id;
```

Result: `101, 104, 105, 107`.

Equivalent in intent to `NOT EXISTS` earlier because `payment_id` is a `NOT NULL` primary key. If an order can have multiple payments, explicitly decide whether you mean "no payment at all" or "no payment in a specific state."

## 17. How Does `WHERE` Differ from `HAVING`?

An aggregate query typically uses:

- **`WHERE`** to filter **input rows** before grouping.
- **`GROUP BY`** to form groups.
- **`HAVING`** to filter **groups** based on aggregate conditions.

### 17.1. Filtering Individual Rows Only

```sql
SELECT
    status,
    COUNT(*) AS order_count
FROM where_lab.orders
WHERE total_amount >= 250000
GROUP BY status
ORDER BY status;
```

Rows with total amount at least 250000 are `102, 103, 106, 107, 108`. After grouping:

| status | order_count |
| --- | ---: |
| NEW | 1 |
| PAID | 2 |
| SHIPPED | 2 |

CANCELLED has no matching orders, so it does not appear.

### 17.2. Filtering Groups with `HAVING`

```sql
SELECT
    status,
    COUNT(*) AS order_count
FROM where_lab.orders
GROUP BY status
HAVING COUNT(*) >= 2
ORDER BY status;
```

Result:

| status | order_count |
| --- | ---: |
| NEW | 2 |
| PAID | 3 |
| SHIPPED | 2 |

CANCELLED has only one row, so its group is excluded.

### 17.3. `WHERE COUNT(*) >= 2` Is in the Wrong Place

You cannot use an aggregate like `COUNT(*)` directly in `WHERE` at the same query level to filter groups. Use `HAVING`, or compute the aggregation in a subquery/CTE and filter outside.

Example:

```sql
WITH counts AS (
    SELECT status, COUNT(*) AS order_count
    FROM where_lab.orders
    GROUP BY status
)
SELECT status, order_count
FROM counts
WHERE order_count >= 2
ORDER BY status;
```

In the outer query, `order_count` is already an output column of the CTE, so `WHERE order_count >= 2` is valid.

### 17.4. Tip for Remembering Logical Processing Order

A useful conceptual order:

```text
FROM / JOIN
     |
     v
WHERE           (filter rows)
     |
     v
GROUP BY        (form groups)
     |
     v
HAVING          (filter groups)
     |
     v
SELECT          (project output expressions)
     |
     v
ORDER BY        (sort results)
     |
     v
LIMIT / OFFSET  (limit results)
```

This is the **logical order for understanding SQL**, not necessarily the physical execution order chosen by the optimizer.

## 18. `WHERE` in `UPDATE` and `DELETE`

`WHERE` is not just for `SELECT`. It also decides **which rows are modified or deleted**.

### 18.1. `UPDATE ... WHERE`

```sql
BEGIN;

UPDATE where_lab.orders
SET priority = 4
WHERE order_id = 107
  AND status = 'NEW'
RETURNING order_id, status, priority;

ROLLBACK;
```

This example runs inside a transaction and rolls back so it does not permanently alter the exercise data.

Here `WHERE` also checks the order status before updating priority. If the order is no longer NEW, the statement may update 0 rows.

**Do not assume "0 rows updated" means business success** when the application requires updating exactly one order. Inspect `RETURNING` or the affected row count, and handle concurrency between transactions.

### 18.2. `DELETE ... WHERE`

```sql
BEGIN;

DELETE FROM where_lab.orders
WHERE status = 'CANCELLED'
  AND total_amount < 100000
RETURNING order_id, status;

ROLLBACK;
```

On the sample data, this selects order 104. Because of `ROLLBACK`, the row is not permanently deleted when the transaction ends.

**Warning:** omitting `WHERE` in `DELETE FROM where_lab.orders` deletes **every row** permitted by privileges and constraints. Before running destructive statements, run a `SELECT` with the same predicate in a controlled environment to verify the target row set. In production, also ensure clear backup and rollback procedures.

### 18.3. A Correct Condition Does Not Replace Transactions

For example, "deduct inventory only if enough stock is available":

```sql
UPDATE where_lab.inventory
SET available = available - 1
WHERE product_id = 1001
  AND available >= 1
RETURNING product_id, available;
```

This is a syntax illustration (`inventory` has not been created in this lesson), showing that check and update should be combined into a single atomic statement whenever possible.

For multi-step workflows, you still need proper transaction boundaries, locking, and isolation levels to preserve data integrity.

## 19. Are `WHERE` Conditions Evaluated Left-to-Right?

**Never rely on PostgreSQL always evaluating predicates in the order you wrote them.** The optimizer may transform, push down, or reorder expressions to build an efficient execution plan.

Example:

```sql
WHERE status = 'PAID'
  AND total_amount > 100000
```

Do not assume `status = 'PAID'` always runs first before checking `total_amount`. For these two pure comparisons, evaluation order does not affect the result; however, if an expression can throw an error or cause side effects, assuming **left-to-right short-circuiting** can fail.

### 19.1. Do Not Rely on `AND` Alone to Guard Unsafe Casts

Suppose a CSV import table has a text column `raw_quantity`. You want to keep only positive integers before casting:

```sql
-- Do not treat AND order as an absolute guard:
WHERE raw_quantity ~ '^[0-9]+$'
  AND raw_quantity::integer > 0
```

The optimizer may evaluate expressions in a different order than written. Furthermore, an all-digit string can still overflow `integer`.

Proper approaches depending on requirements: validate/normalize in staging, create a typed column in a controlled step, or use a `CASE` expression to guard the conversion:

```sql
SELECT raw_quantity
FROM (
    VALUES ('3'), ('-1'), ('abc'), ('0')
) AS input(raw_quantity)
WHERE CASE
    WHEN raw_quantity ~ '^[0-9]{1,9}$'
    THEN raw_quantity::integer > 0
    ELSE FALSE
END;
```

By capping at 9 non-negative digits, the value fits safely inside a 32-bit integer; the query returns `'3'`. This is only an example guarding a cast over a simple input domain, not a general-purpose numeric validator.

**Never place functions with side effects in `WHERE` expecting `AND`/`OR` branches to control call order like procedural code.**

### 19.2. `WHERE` Declares the Result Set

Instead of thinking:

```text
1. Check status.
2. Then check amount.
3. If true, check date.
```

think:

```text
Select rows satisfying:
status = 'PAID'
AND amount >= 250000
AND placed_at within the requested date range.
```

Then inspect how PostgreSQL actually executes it via indexes, scans, joins, and filters using `EXPLAIN` when performance matters.

## 20. Writing Conditions That Can Use Indexes

Not all `WHERE` predicates use indexes equally. For example:

```sql
CREATE INDEX idx_orders_status_amount
ON where_lab.orders (status, total_amount);

CREATE INDEX idx_orders_placed_at
ON where_lab.orders (placed_at);
```

These indexes are illustrative examples, not a mandatory production index list.

### 20.1. B-Tree Indexes and Basic Comparisons

A standard B-tree index supports many comparison patterns:

```sql
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE status = 'PAID'
  AND total_amount >= 250000
ORDER BY total_amount, order_id;
```

With an index on `(status, total_amount)`, an **equality predicate on the leading column** and a **range predicate on the second column** is a favorable pattern for a B-tree.

With an 8-row table, PostgreSQL will likely choose a sequential scan because it is cheaper than using an index. Do not benchmark index effectiveness on tiny sample datasets.

### 20.2. Conditions Wrapping Columns in Expressions

```sql
SELECT order_id
FROM where_lab.orders
WHERE placed_at::date = DATE '2026-10-03';
```

Wrapping a column in an expression can prevent a plain B-tree index on `placed_at` from being used directly like a timestamp range.

The half-open range form:

```sql
SELECT order_id
FROM where_lab.orders
WHERE placed_at >= TIMESTAMPTZ '2026-10-03 00:00:00+07'
  AND placed_at <  TIMESTAMPTZ '2026-10-04 00:00:00+07';
```

is much more friendly to an index on `placed_at` for point-in-time range filtering.

**Time zone note:** both forms match by date only if the session/cast uses the same business time zone. `placed_at::date` depends on the session's time zone, whereas the `+07` boundaries fix the range to that offset.

### 20.3. `LIKE 'prefix%'` vs. `LIKE '%contains%'`

`LIKE 'An%'` has a fixed prefix, which can leverage an appropriate index depending on collation and operator class.

`LIKE '%An%'` has a leading wildcard, so a plain B-tree cannot easily use it like a prefix search. For substring search on large tables, PostgreSQL can use the `pg_trgm` extension with GIN/GiST indexes, though benefit depends on pattern length, selectivity, and data volume.

Do not create an index for every text condition before understanding the actual workload.

### 20.4. `OR` Can Use Multiple Indexes or Scans

```sql
SELECT order_id, status, priority
FROM where_lab.orders
WHERE status = 'PAID'
   OR priority = 5;
```

PostgreSQL can pick various strategies such as combined bitmap index scans (if suitable indexes exist), sequential scans, or rewrites based on statistics and cost. The presence of `OR` does not automatically mean indexes cannot be used.

### 20.5. NULL Conditions and Partial Indexes

If queries frequently look for unshipped paid orders:

```sql
SELECT order_id, status
FROM where_lab.orders
WHERE shipped_at IS NULL
  AND status = 'PAID';
```

A **partial index** can fit well when the table is very large and the target subset is small:

```sql
CREATE INDEX idx_orders_unshipped_paid
ON where_lab.orders (order_id)
WHERE shipped_at IS NULL
  AND status = 'PAID';
```

This index includes only rows matching the index's `WHERE` predicate. It carries write maintenance overhead and will not help unrelated queries. Measure with `EXPLAIN`, update frequency, and data size before adopting it.

### 20.6. Reading `EXPLAIN`

```sql
EXPLAIN
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE status = 'PAID'
  AND total_amount >= 250000;
```

You may see nodes such as:

- `Seq Scan`: sequential table scan.
- `Index Scan` or `Index Only Scan`: reading through an index using matching conditions.
- `Bitmap Index Scan` and `Bitmap Heap Scan`: combining index lookups before reading heap pages.
- `Filter`: condition applied to discard non-matching rows.
- `Index Cond`: condition pushed into the index lookup itself.

`EXPLAIN (ANALYZE, BUFFERS)` actually executes the query to measure real timings and row counts. With read-only `SELECT`s it is relatively safe in testing; with `UPDATE`, `DELETE`, or queries with side effects, **`EXPLAIN ANALYZE` still performs those modifications**, so wrap it in a transaction with rollback or run in a test environment.

## 21. Parameterizing `WHERE` in Applications

Never build queries by concatenating user input directly into SQL:

```java
// Unsafe and error-prone for data types:
String sql = "SELECT * FROM where_lab.orders WHERE status = '"
           + userInput + "'";
```

This introduces SQL injection risks and quoting bugs.

### 21.1. PreparedStatement in Java/JDBC

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class OrderRepository {

    public void findLargePaidOrders(Connection connection)
            throws Exception {

        String sql =
            "SELECT order_id, total_amount " +
            "FROM where_lab.orders " +
            "WHERE status = ? AND total_amount >= ? " +
            "ORDER BY order_id";

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setString(1, "PAID");
            statement.setBigDecimal(
                2, new BigDecimal("250000.00")
            );

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("order_id");
                    BigDecimal amount =
                        rs.getBigDecimal("total_amount");
                    System.out.println(id + " " + amount);
                }
            }
        }
    }
}
```

`?` in JDBC is a driver-bound placeholder, **not** raw text substitution into SQL. Using `BigDecimal` for `numeric` columns preserves decimal monetary precision.

### 21.2. `PREPARE` in PostgreSQL

You can test prepared statements directly in `psql`:

```sql
PREPARE find_orders (text, numeric) AS
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE status = $1
  AND total_amount >= $2
ORDER BY order_id;

EXECUTE find_orders('PAID', 250000);

DEALLOCATE find_orders;
```

Result: `102` and `108`.

This is PostgreSQL's SQL `PREPARE`. Drivers may use protocol-level prepare/bind messages; both separate **statement structure** from **parameter values**.

### 21.3. Optional Filters with NULL Parameters

Suppose a status parameter can be NULL to indicate "do not filter by status":

```sql
PREPARE search_optional_status(text) AS
SELECT order_id, status
FROM where_lab.orders
WHERE $1 IS NULL OR status = $1
ORDER BY order_id;

EXECUTE search_optional_status(NULL);
EXECUTE search_optional_status('PAID');

DEALLOCATE search_optional_status;
```

The NULL call returns all 8 orders; `'PAID'` returns 102, 105, and 108.

This pattern is convenient, though it can affect how the optimizer picks plans—especially on very large tables when parameter selectivity varies widely. When performance is critical, consider specialized queries per filter shape while still binding parameters safely.

**Important:** `$1 IS NULL OR status = $1` expresses **NULL parameter means skip filter**, which is different from "find rows where `status IS NULL`."

## 22. Common Mistakes When Writing `WHERE`

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `= NULL` | Evaluates to UNKNOWN; fails to match NULL rows | Use `IS NULL` |
| Using `<> NULL` | Fails to match expected rows | Use `IS NOT NULL` |
| Using `NOT (col = x)` expecting NULLs | `NOT UNKNOWN` stays UNKNOWN | Add `IS NULL` or use `IS DISTINCT FROM` if appropriate |
| Mixing `AND` and `OR` without parentheses | Wrong filter logic due to precedence | Add parentheses matching requirements |
| Confusing `>` and `>=` | Off-by-one boundary bugs | Clarify inclusive vs. exclusive bounds |
| Thinking `BETWEEN` is open | Includes both endpoints | Use `>`/`<` for open ranges |
| Using `BETWEEN` up to 00:00 on end date | Misses most of the final day | Use `>= start AND < next_day` |
| `NOT IN` with subquery returning NULL | Whole filter can evaluate to UNKNOWN | Guard against NULL or use `NOT EXISTS` |
| Concatenating input into SQL strings | SQL injection, quoting bugs | Bind parameters |
| Using `ILIKE` to "ignore accents" | Fails to match accented names | Design dedicated search normalization |
| Writing `col = 'a' OR 'b'` | `'b'` is not a valid boolean predicate | Write `col IN ('a','b')` or two comparisons |
| Writing `10 < amount < 100` | Invalid chained comparison in SQL | Write `amount > 10 AND amount < 100` |
| Using `WHERE COUNT(*) > ...` | Aggregates cannot be used directly in same-level WHERE | Use `HAVING COUNT(*) > ...` |
| Putting right-side `LEFT JOIN` filter in WHERE | Drops unmatched left rows | Decide whether predicate belongs in `ON` or `WHERE` |
| Omitting `WHERE` in `UPDATE/DELETE` | Modifies/deletes entire table | Verify beforehand and use transactions |
| Assuming left-to-right condition execution | Unsafe casts/functions may still error | Use `CASE` or input validation |
| Wrapping indexed columns in functions | Regular indexes may not be usable | Consider range predicates or expression indexes |
| Expecting fixed order without `ORDER BY` | Result order can shift | Add `ORDER BY` with tie-breaker |
| Using a `SELECT` alias in same-level `WHERE` | Alias is not yet in scope in WHERE | Repeat expression or use CTE/subquery |

### 22.1. Wrong: `status = 'PAID' OR 'SHIPPED'`

Incorrect:

```sql
-- Invalid syntax/boolean type:
SELECT *
FROM where_lab.orders
WHERE status = 'PAID' OR 'SHIPPED';
```

Correct:

```sql
SELECT *
FROM where_lab.orders
WHERE status = 'PAID'
   OR status = 'SHIPPED';
```

Or:

```sql
SELECT *
FROM where_lab.orders
WHERE status IN ('PAID', 'SHIPPED');
```

Each `OR` branch must be a valid boolean expression.

### 22.2. Wrong: Mathematical Chained Comparisons

Do not write:

```sql
-- Does not express a range in SQL syntax:
WHERE 100000 < total_amount < 500000
```

Correct:

```sql
WHERE total_amount > 100000
  AND total_amount < 500000
```

This is an **open** interval on both ends; if you want to include 100000 or 500000, switch the corresponding operator to `>=` or `<=`.

### 22.3. Confusing Text Comparison with Numeric Comparison

```sql
SELECT '10'::text < '2'::text AS text_comparison,
       10::integer < 2::integer AS number_comparison;
```

In `"C"` collation or similar lexicographical ordering, `'10'` sorts before `'2'` because the first character `'1'` precedes `'2'`, even though 10 is greater than 2.

If a value represents a **quantity** or **monetary amount**, store it in an appropriate numeric type instead of text and relying on string comparison.

### 22.4. Confusing `NULL` with a Default Value

If NULL region means "not yet assigned", do not write:

```sql
WHERE COALESCE(region, 'Hanoi') = 'Hanoi'
```

unless the business genuinely defines "unassigned region counts as Hanoi." That rule **transforms data semantics** rather than merely checking NULL.

## 23. Practice Exercises with Answers

Use the `where_lab.orders` and `where_lab.payments` tables created at the start of the lesson.

### Exercise 1. Retrieve All Orders with Total Amount of 250,000 or More

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount >= 250000
ORDER BY order_id;
```

**Answer:** IDs `102, 103, 106, 107, 108`.

### Exercise 2. Retrieve PAID Orders with Total Amount Greater Than 100,000

```sql
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE status = 'PAID'
  AND total_amount > 100000
ORDER BY order_id;
```

**Answer:** `102` and `108`. Order 105 has 80,000 and is excluded.

### Exercise 3. Retrieve Orders That Are NEW or Priority 5

```sql
SELECT order_id, status, priority
FROM where_lab.orders
WHERE status = 'NEW'
   OR priority = 5
ORDER BY order_id;
```

**Answer:** `101, 102, 106, 107`.

### Exercise 4. Retrieve Orders That Are Not PAID and Have Priority Below 4

```sql
SELECT order_id, status, priority
FROM where_lab.orders
WHERE status <> 'PAID'
  AND priority < 4
ORDER BY order_id;
```

**Answer:** `101, 104, 107`.

### Exercise 5. Retrieve Orders with Unspecified Region

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE region IS NULL
ORDER BY order_id;
```

**Answer:** `104` and `108`. Do not use `region = NULL`.

### Exercise 6. Retrieve All Orders Whose Region Is Not Hanoi, Including NULL Regions

```sql
SELECT order_id, region
FROM where_lab.orders
WHERE region IS DISTINCT FROM 'Hanoi'
ORDER BY order_id;
```

**Answer:** `102, 103, 104, 106, 107, 108`.

Explanation: `IS DISTINCT FROM` treats NULL as distinct from any non-NULL value.

### Exercise 7. Total Amount from 250,000 to 350,000, Inclusive

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount BETWEEN 250000 AND 350000
ORDER BY order_id;
```

**Answer:** `102, 103, 107, 108`.

### Exercise 8. PAID or SHIPPED Orders with Total Amount at Least 250,000

```sql
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE status IN ('PAID', 'SHIPPED')
  AND total_amount >= 250000
ORDER BY order_id;
```

**Answer:** `102, 103, 106, 108`.

### Exercise 9. Retrieve Orders from Oct 2 Through End of Oct 4, 2026 (+07)

```sql
SELECT order_id, placed_at
FROM where_lab.orders
WHERE placed_at >= TIMESTAMPTZ '2026-10-02 00:00:00+07'
  AND placed_at < TIMESTAMPTZ '2026-10-05 00:00:00+07'
ORDER BY order_id;
```

**Answer:** `102, 103, 104, 105, 106`.

### Exercise 10. Retrieve Unshipped Orders with Status PAID

```sql
SELECT order_id, status
FROM where_lab.orders
WHERE shipped_at IS NULL
  AND status = 'PAID'
ORDER BY order_id;
```

**Answer:** `102, 105, 108`.

### Exercise 11. Find Customer Names Starting with `a`, Case-Insensitive

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE customer_name ILIKE 'a%'
ORDER BY order_id;
```

**Answer:** `101 - An`.

### Exercise 12. Find Orders with a Confirmed Payment

```sql
SELECT o.order_id
FROM where_lab.orders AS o
WHERE EXISTS (
    SELECT 1
    FROM where_lab.payments AS p
    WHERE p.order_id = o.order_id
      AND p.state = 'CONFIRMED'
)
ORDER BY o.order_id;
```

**Answer:** `102, 103, 106`.

### Exercise 13. Find Orders with No Payments at All

```sql
SELECT o.order_id
FROM where_lab.orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM where_lab.payments AS p
    WHERE p.order_id = o.order_id
)
ORDER BY o.order_id;
```

**Answer:** `101, 104, 105, 107`.

### Exercise 14. Which Query Returns Zero Rows?

```sql
SELECT order_id
FROM where_lab.orders
WHERE region = NULL;
```

**Answer:** the query fails to return rows with NULL region because `= NULL` evaluates to UNKNOWN, not TRUE. You must use `IS NULL`.

### Exercise 15. Why Is `1 NOT IN (2, NULL)` Not TRUE?

**Answer:** comparing against NULL yields UNKNOWN. `1 <> 2` is true, yet `1 <> NULL` is unknown; evaluating the entire `NOT IN` cannot conclude TRUE, so it returns UNKNOWN.

### Exercise 16. Distinguishing `WHERE` and `HAVING`

Requirement: retrieve only statuses with at least 2 orders.

```sql
SELECT status, COUNT(*) AS order_count
FROM where_lab.orders
GROUP BY status
HAVING COUNT(*) >= 2
ORDER BY status;
```

**Answer:** `NEW (2), PAID (3), SHIPPED (2)`. Do not place `COUNT(*) >= 2` in `WHERE` at the same query level.

### Exercise 17. Retrieve All Orders and Their CONFIRMED Payment if Any

```sql
SELECT o.order_id, p.payment_id
FROM where_lab.orders AS o
LEFT JOIN where_lab.payments AS p
  ON p.order_id = o.order_id
 AND p.state = 'CONFIRMED'
ORDER BY o.order_id;
```

**Answer:** all 8 orders appear in the output; orders without a CONFIRMED payment get `payment_id NULL`. Moving `p.state = 'CONFIRMED'` into `WHERE` drops the unmatched orders.

### Exercise 18. Write a Safe Condition for an Amount Passed from the Application

**Suggested answer:** use a bind parameter in JDBC:

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount >= ?
ORDER BY order_id;
```

In Java, use `PreparedStatement` with `setBigDecimal` for monetary amounts; never concatenate user input directly into SQL strings.

### Exercise 19. Find Rows Where `region = 'Hanoi'` Is Not TRUE

```sql
SELECT order_id
FROM where_lab.orders
WHERE (region = 'Hanoi') IS NOT TRUE
ORDER BY order_id;
```

**Answer:** `102, 103, 104, 106, 107, 108`. The result includes rows with NULL region because an UNKNOWN expression is "not TRUE."

### Exercise 20. Filter Orders with Total Amount >= 250,000 and Status Not CANCELLED

```sql
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE total_amount >= 250000
  AND status <> 'CANCELLED'
ORDER BY order_id;
```

**Answer:** `102, 103, 106, 107, 108`. The sample table has no CANCELLED orders reaching 250,000, yet the status filter explicitly enforces the rule.

## 24. Checklist When Designing a `WHERE` Expression

Before putting a filter into an application, check:

| Question | Appropriate Action |
| --- | --- |
| Are any columns nullable? | Check three-valued logic; use `IS NULL` or `IS DISTINCT FROM` where semantically right |
| Does the condition mix `AND` and `OR`? | Add parentheses to enforce exact precedence |
| Are range endpoints inclusive? | Choose `>`/`>=`/`<`/`<=` or `BETWEEN` explicitly |
| Does date filtering include the entire end day? | Use `>= start AND < next_day` |
| Are inputs strings/numerics/timestamps? | Match data types and bind parameters |
| Is there a user-supplied `IN` list? | Handle empty lists/NULLs and parameterize |
| Is there a `NOT IN` subquery that could yield NULL? | Re-examine semantics and consider `NOT EXISTS` |
| Is there a filter on the right side of `LEFT JOIN`? | Check whether it belongs in `ON` or `WHERE` |
| Are there error-prone casts like text-to-number? | Do not rely on `AND` evaluation order; validate or use `CASE` |
| Is an indexed column wrapped in a function/cast? | Inspect `EXPLAIN`; consider ranges or expression indexes |
| Are you searching text with `LIKE`/`ILIKE`? | Understand wildcards, collations, case/accents, and indexes |
| Does the query use aggregation? | Use `WHERE` for rows and `HAVING` for groups |
| Does the query use `LIMIT`/pagination? | Add a deterministic `ORDER BY` |
| Is the filter for `UPDATE`/`DELETE`? | Verify the target rows first and wrap in transactions/rollback |
| Is the predicate overly complex? | Restate it in plain language and clarify with parentheses/subqueries |

## 25. Summary

**`WHERE`** is the primary tool for specifying which rows to fetch or modify in PostgreSQL. Mastering comparison and logical operators ensures queries produce **accurate results before optimizing for speed**.

Key takeaways:

1. **`=`, `<>`, `<`, `<=`, `>`, `>=`** compare values; always verify boundary conditions.
2. **`AND`, `OR`, `NOT`** combine predicates. When mixing operators, use parentheses to make intent explicit rather than relying on precedence.
3. PostgreSQL uses **three-valued logic**: TRUE, FALSE, UNKNOWN. `WHERE` keeps only TRUE rows.
4. **Never compare NULL with `= NULL`**. Use `IS NULL`, `IS NOT NULL`, and where appropriate `IS [NOT] DISTINCT FROM`.
5. **`BETWEEN` is inclusive of both endpoints**. For date/time ranges, prefer half-open intervals `>= start AND < end` to capture full days.
6. **`IN`** simplifies multiple OR checks; **`NOT IN` with NULL** produces surprising UNKNOWN results. `EXISTS`/`NOT EXISTS` fit well when checking for related rows.
7. **`LIKE`** matches patterns; **`ILIKE`** matches case-insensitively in PostgreSQL. Neither strips accents automatically, and not all patterns can use B-tree indexes efficiently.
8. With **`LEFT JOIN`**, placing a predicate in `ON` versus `WHERE` determines whether unmatched rows are preserved.
9. **`WHERE` filters rows before aggregation; `HAVING` filters groups** after `GROUP BY`.
10. In **`UPDATE` and `DELETE`**, `WHERE` defines the scope of mutation. Double-check conditions and control transactions.
11. **Do not rely on left-to-right predicate evaluation** or procedural short-circuiting.
12. **Use bind parameters** to pass inputs into SQL and inspect `EXPLAIN` for index/scan plans when tuning.

A great habit when writing SQL is to read your `WHERE` clause aloud as a clear natural-language sentence—for example: "Paid orders **and** amount at least 250,000, **or** high-priority orders without a shipping timestamp." Then place parentheses to match that exact sentence, decide how NULLs behave, and test against both typical and edge-case rows.
