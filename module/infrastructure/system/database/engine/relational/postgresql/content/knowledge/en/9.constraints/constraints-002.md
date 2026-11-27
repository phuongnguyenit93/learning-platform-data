# CHECK Constraints and Validation Limits in PostgreSQL

An application receives data from APIs, CSV files, admin forms, or other services. Even when the application validates input, the database still needs to protect core data invariants: non-negative prices, quantities greater than 0, end dates after start dates, statuses within an allowed list, or discount amounts not exceeding the original price.

PostgreSQL provides **`CHECK` constraints** to express such conditions directly in the table definition. When an `INSERT` or `UPDATE` produces a row that fails the condition, PostgreSQL rejects the change. This is a valuable defense layer because it applies to every standard write path into the table—from applications, SQL scripts, and admin tools to bulk import pipelines.

However, `CHECK` has **clear limits**: it primarily evaluates expressions over the data of **a single row**, not an arbitrary query across multiple rows or tables; expressions evaluating to `NULL` are treated as non-violating; and PostgreSQL does not continuously re-evaluate all rows simply because time passes or a function changes behavior.

This lesson explains how to declare `CHECK` constraints, SQL's three-valued logic, multi-column constraints, validation limits, workflows for adding constraints to tables with existing data, and how to combine `CHECK` with other integrity mechanisms.

## 1. Learning Objectives

After this lesson, you will be able to:

- Write `CHECK` constraints at the column or table level with clear, meaningful constraint names.
- Understand why PostgreSQL treats **`TRUE` and `NULL`** as satisfying `CHECK`, while `FALSE` causes the operation to be rejected.
- Combine `CHECK` with `NOT NULL` to block missing values and avoid misinterpreting three-valued logic.
- Express valid conditions for numeric ranges, value sets, strings, timestamps, and relationships across multiple columns in the same row.
- Read `check_violation` errors with SQLSTATE `23514` and distinguish them from other constraint errors.
- Add constraints to tables with legacy data using `NOT VALID`, repair invalid rows, and run `VALIDATE CONSTRAINT`.
- Explain why `CHECK` is unsuitable for uniqueness, foreign keys, table-wide row counts, or invariants across two concurrent transactions.
- Understand expression stability requirements for `CHECK` and the risks of referencing current time or functions whose behavior changes.
- Coordinate constraints, transactions, locking, isolation levels, and application validation to keep data accurate.
- Design and run a PostgreSQL lab exercise with valid and invalid cases.

The SQL examples target modern PostgreSQL. Statements that create or drop tables should only be run in a **dedicated test database**—never copy them straight into production.

---

## 2. Where Does CHECK Fit in the Constraint System?

A PostgreSQL table can have several types of constraints:

| Type | Primary Purpose | Example |
| --- | --- | --- |
| `NOT NULL` | A column must not contain `NULL` | Product name is required |
| `CHECK` | Check expression must not evaluate to `FALSE` | `price >= 0` |
| `UNIQUE` | No duplicate values or value combinations per uniqueness rules | Distinct SKU code |
| `PRIMARY KEY` | Row identifier, both unique and non-NULL | `product_id` |
| `FOREIGN KEY` | Referenced value must match a relationship in another table | `customer_id` exists |
| `EXCLUDE` | Prevents two rows from having conflicting combinations under specified operators | No overlapping room bookings |

**`CHECK` is well suited for per-row invariants**: non-negative prices, discounts within allowed bounds, start times before end times.

**`UNIQUE`, `FOREIGN KEY`, and `EXCLUDE`** are better suited for rules that depend on data in other rows or tables. Rules spanning multiple rows or business workflow stages may also require transactions, locks, triggers, or application-level coordination.

Overview diagram:

```text
Application / psql / import tool
                |
                | INSERT or UPDATE
                v
       PostgreSQL table
    +----------------------+
    | Data types           |
    | NOT NULL             |
    | CHECK                |
    | UNIQUE / PRIMARY KEY |
    | FOREIGN KEY          |
    | Other rules          |
    +----------------------+
                |
         +------+------+
         |             |
       Valid       Violation
         |             |
         v             v
 Continue work     SQL Error
 in transaction    not written
         |
      COMMIT if
    everything valid
```

A constraint does not commit data by itself. It is one part of validating each SQL statement inside the active transaction.

---

## 3. Basic CHECK Syntax

Inline column-level declaration:

```sql
CREATE TABLE example_products (
    product_id BIGINT PRIMARY KEY,
    price NUMERIC(12,2) CHECK (price >= 0)
);
```

Named constraint declaration:

```sql
CREATE TABLE example_products_named (
    product_id BIGINT PRIMARY KEY,
    price NUMERIC(12,2)
        CONSTRAINT example_products_named_price_nonnegative
        CHECK (price >= 0)
);
```

Table-level constraint declaration:

```sql
CREATE TABLE example_discounts (
    product_id BIGINT PRIMARY KEY,
    list_price NUMERIC(12,2) NOT NULL,
    sale_price NUMERIC(12,2) NOT NULL,
    CONSTRAINT example_discounts_prices_valid
        CHECK (
            list_price >= 0
            AND sale_price >= 0
            AND sale_price <= list_price
        )
);
```

Both placements can create a `CHECK` constraint, though **table-level constraints** are usually easier to read when comparing multiple columns.

### 3.1. Name Constraints Explicitly

If no name is specified, PostgreSQL generates a default name. That works, but explicit names help you:

- Identify which condition failed when reading logs.
- Handle errors structurally in backend services.
- Run `ALTER TABLE ... DROP CONSTRAINT` or `VALIDATE CONSTRAINT` clearly.
- Distinguish multiple conditions on the same table.
- Write more consistent migrations.

Examples of clear names:

```text
products_price_nonnegative
products_discount_within_price
bookings_time_order
payments_amount_positive
orders_status_allowed
```

Do not use constraint names as a substitute for business documentation; a name is only a concise identifier, while the full rule still needs documentation.

### 3.2. What Expressions Can CHECK Evaluate?

Inside `CHECK (...)`, standard SQL expressions are typically used:

```sql
CHECK (quantity > 0)
CHECK (price >= 0 AND price <= 1000000000)
CHECK (status IN ('DRAFT', 'ACTIVE', 'ARCHIVED'))
CHECK (length(code) BETWEEN 3 AND 20)
CHECK (start_at < end_at)
```

For each new or updated row, PostgreSQL evaluates the condition. If it returns `FALSE`, the operation violates the constraint.

**A CHECK condition is not an arbitrary SELECT query capable of querying the entire database.** PostgreSQL does not allow direct subqueries inside `CHECK` expressions to count other rows or look up reference tables.

---

## 4. The Most Important Rule: CHECK Accepts TRUE or NULL

In SQL, logical conditions have **three values**:

- `TRUE`: true.
- `FALSE`: false.
- `NULL`, also known as unknown: truth value cannot be determined due to missing information.

For a PostgreSQL `CHECK` constraint, a row **satisfies the constraint if the expression evaluates to `TRUE` or `NULL`**. Only when the expression evaluates to `FALSE` does PostgreSQL reject the row for that constraint.

### 4.1. Simple CHECK Example

```sql
CREATE TABLE example_scores (
    score_id INTEGER PRIMARY KEY,
    score INTEGER CHECK (score >= 0)
);
```

Try each statement individually in `psql` autocommit mode:

```sql
-- Valid: CHECK returns TRUE.
INSERT INTO example_scores VALUES (1, 10);

-- Rejected: CHECK returns FALSE.
INSERT INTO example_scores VALUES (2, -3);

-- Valid under CHECK: score >= 0 evaluates to NULL.
INSERT INTO example_scores VALUES (3, NULL);
```

The third line often surprises beginners: **`CHECK (score >= 0)` does not mean `score` must have a value**.

| `score` Value | `score >= 0` | Result for CHECK |
| --- | --- | --- |
| 10 | `TRUE` | Allowed |
| 0 | `TRUE` | Allowed |
| -3 | `FALSE` | Rejected |
| `NULL` | `NULL` | Allowed, unless another constraint forbids it |

To make `score` both required and non-negative:

```sql
CREATE TABLE example_scores_required (
    score_id INTEGER PRIMARY KEY,
    score INTEGER NOT NULL CHECK (score >= 0)
);
```

### 4.2. Why Does PostgreSQL Allow NULL in CHECK?

SQL distinguishes between “a known value that violates the rule” and “an unknown/missing value”. `CHECK` does not automatically treat missing data as invalid; `NOT NULL` exists specifically to express that data must be present.

This behavior is consistent with SQL expressions:

```sql
SELECT
    NULL::INTEGER >= 0 AS unknown_comparison,
    (NULL::INTEGER >= 0) IS TRUE AS explicitly_true,
    (NULL::INTEGER >= 0) IS NOT FALSE AS not_false;
```

Semantic result:

- `NULL >= 0` is unknown.
- `(...) IS TRUE` is `FALSE` when the expression is unknown.
- `(...) IS NOT FALSE` is `TRUE` when the expression is unknown.

You could write `CHECK (score IS NOT NULL AND score >= 0)` to reject `NULL`, but **`score INTEGER NOT NULL CHECK (score >= 0)` is clearer**: presence is enforced by `NOT NULL`, and the value domain is enforced by `CHECK`.

### 4.3. Compound Conditions Can Still Evaluate to NULL

Example:

```sql
CHECK (discount_amount >= 0 AND discount_amount <= list_price)
```

If `discount_amount = NULL` and `list_price = 100`, the overall expression can evaluate to unknown. If `list_price` is missing, the discount bound check can also become unknown.

Therefore, when both columns are required:

```sql
list_price NUMERIC(12,2) NOT NULL,
discount_amount NUMERIC(12,2) NOT NULL,
CHECK (
    list_price >= 0
    AND discount_amount >= 0
    AND discount_amount <= list_price
)
```

**Design rule:** domain validation and value presence are two independent requirements. Do not omit `NOT NULL` just because `CHECK` contains multiple conditions.

---

## 5. Preparing the Practice Database

This section builds a products table with common constraints. For clarity, the data is purely illustrative and contains no real business records.

> **Warning:** The `DROP TABLE IF EXISTS` statements below delete any data in existing lab tables of those names. Run them only on a practice database you are allowed to reset—never run this block verbatim in production.

```sql
CREATE SCHEMA IF NOT EXISTS check_lab;

DROP TABLE IF EXISTS check_lab.products;
DROP TABLE IF EXISTS check_lab.legacy_prices;

CREATE TABLE check_lab.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,

    list_price NUMERIC(12,2) NOT NULL
        CONSTRAINT products_list_price_nonnegative
        CHECK (list_price >= 0),

    discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    stock_quantity INTEGER NOT NULL DEFAULT 0,

    status TEXT NOT NULL DEFAULT 'DRAFT',

    CONSTRAINT products_sku_not_blank
        CHECK (btrim(sku) <> ''),

    CONSTRAINT products_name_not_blank
        CHECK (btrim(product_name) <> ''),

    CONSTRAINT products_discount_valid
        CHECK (
            discount_amount >= 0
            AND discount_amount <= list_price
        ),

    CONSTRAINT products_stock_nonnegative
        CHECK (stock_quantity >= 0),

    CONSTRAINT products_status_allowed
        CHECK (status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')),

    CONSTRAINT products_active_price_positive
        CHECK (
            status <> 'ACTIVE'
            OR list_price > 0
        )
);
```

These constraints enforce **per-product rules**:

| Constraint | Requirement |
| --- | --- |
| `products_list_price_nonnegative` | List price is non-negative |
| `products_sku_not_blank` | SKU after trimming leading/trailing spaces is not empty |
| `products_name_not_blank` | Product name cannot contain only ordinary whitespace |
| `products_discount_valid` | Discount is between 0 and list price |
| `products_stock_nonnegative` | Stock quantity is non-negative |
| `products_status_allowed` | Status belongs to the allowed set |
| `products_active_price_positive` | ACTIVE products must have a list price greater than 0 |

Required columns all have `NOT NULL`. Without `NOT NULL`, several of the `CHECK` expressions above could evaluate to unknown and fail to block rows with missing values.

### 5.1. Inserting Valid Data

```sql
INSERT INTO check_lab.products (
    sku, product_name, list_price,
    discount_amount, stock_quantity, status
)
VALUES
    ('BOOK-001', 'PostgreSQL Book', 125000.00, 5000.00, 10, 'ACTIVE'),
    ('PEN-002',  'Blue Pen',         15000.00,    0.00, 50, 'ACTIVE'),
    ('GIFT-003', 'Gift',                 0.00,    0.00,  0, 'DRAFT')
RETURNING
    product_id, sku, list_price,
    discount_amount, stock_quantity, status;
```

All three rows are valid under the declared rules.

Specifically, `GIFT-003` has a price of 0 because it is in `DRAFT` status. If switched to `ACTIVE` while keeping price 0, `products_active_price_positive` will block it.

### 5.2. Testing Violating Operations

Run each statement **independently to observe the error**:

```sql
-- Error: negative price.
INSERT INTO check_lab.products (
    sku, product_name, list_price
)
VALUES ('BAD-PRICE', 'Invalid item', -1.00);

-- Error: SKU contains only whitespace.
INSERT INTO check_lab.products (
    sku, product_name, list_price
)
VALUES ('   ', 'Invalid item', 100.00);

-- Error: discount exceeds list price.
INSERT INTO check_lab.products (
    sku, product_name, list_price, discount_amount
)
VALUES ('BAD-DISCOUNT', 'Invalid item', 100.00, 200.00);

-- Error: status not in allowed set.
INSERT INTO check_lab.products (
    sku, product_name, list_price, status
)
VALUES ('BAD-STATUS', 'Invalid item', 100.00, 'PUBLISHED');

-- Error: ACTIVE but list price is 0.
INSERT INTO check_lab.products (
    sku, product_name, list_price, status
)
VALUES ('BAD-ACTIVE', 'Invalid item', 0.00, 'ACTIVE');
```

All of the statements above are expected to raise constraint errors. Do not run a whole group of failing statements inside one transaction and then continue normal `INSERT`s, because in PostgreSQL an error inside a transaction puts it into an aborted state until rolled back or reverted to an appropriate savepoint.

---

## 6. Multi-Column CHECK: Rules Within a Single Row

`CHECK` is not limited to single columns. A table-level constraint can enforce **relationships across multiple columns in the same row**.

### 6.1. Valid Time Intervals

```sql
CREATE TABLE check_lab.booking_periods (
    booking_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT booking_periods_time_order
        CHECK (starts_at < ends_at)
);
```

Valid example:

```sql
INSERT INTO check_lab.booking_periods (starts_at, ends_at)
VALUES (
    '2026-11-15 09:00:00+07',
    '2026-11-15 10:00:00+07'
);
```

Valid because the start time is earlier than the end time.

Invalid example:

```sql
INSERT INTO check_lab.booking_periods (starts_at, ends_at)
VALUES (
    '2026-11-15 11:00:00+07',
    '2026-11-15 10:00:00+07'
);
```

Here `starts_at < ends_at` evaluates to `FALSE`.

**Limit:** this constraint does not prevent two **different rows** from booking the same room for overlapping intervals. It only checks time ordering **within each individual row**. To forbid overlapping schedules per room key, you typically need an `EXCLUDE` constraint with a range type or an equivalent concurrency design.

### 6.2. State-Dependent Conditions

A business rule:

> A delivered order must have a delivery timestamp; an undelivered order does not need one yet.

This can be written as:

```sql
CREATE TABLE check_lab.deliveries (
    delivery_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'IN_TRANSIT', 'DELIVERED')),
    delivered_at TIMESTAMPTZ,
    CONSTRAINT deliveries_delivered_time_required
        CHECK (
            status <> 'DELIVERED'
            OR delivered_at IS NOT NULL
        )
);
```

Or expressed using `CASE`:

```sql
CHECK (
    CASE
        WHEN status = 'DELIVERED'
            THEN delivered_at IS NOT NULL
        ELSE TRUE
    END
)
```

In practice, prefer the simplest form that is easiest to verify. If the business also requires that `delivered_at` may only be non-NULL when status is `DELIVERED`, add the symmetric condition; the constraint above does not forbid a `NEW` row from having a timestamp.

### 6.3. Checking Optional Column Combinations

For example, an account can have **either an email or a phone number**, but must have at least one:

```sql
CREATE TABLE check_lab.contacts (
    contact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    phone TEXT,
    CONSTRAINT contacts_at_least_one_method
        CHECK (
            email IS NOT NULL
            OR phone IS NOT NULL
        )
);
```

If **exactly one** of the two fields must have a value:

```sql
CREATE TABLE check_lab.exclusive_contacts (
    contact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    phone TEXT,
    CONSTRAINT exclusive_contacts_exactly_one
        CHECK (num_nonnulls(email, phone) = 1)
);
```

`num_nonnulls` counts the number of non-NULL arguments. Columns containing empty strings are still considered **non-NULL**; if empty strings are disallowed, add checks for that as well.

---

## 7. String Validation: Length, Whitespace, Regex, and Limits

`CHECK` can use PostgreSQL string functions for basic format validation.

### 7.1. Length and Whitespace

```sql
CREATE TABLE check_lab.tags (
    tag_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tag_code TEXT NOT NULL,
    CONSTRAINT tags_length_valid
        CHECK (char_length(tag_code) BETWEEN 3 AND 20),
    CONSTRAINT tags_not_blank
        CHECK (btrim(tag_code) <> '')
);
```

`char_length(text)` measures the number of characters in text; `octet_length(text)` measures the number of bytes. For Unicode strings such as Vietnamese with diacritics, the UTF-8 byte count can differ from the character count.

Therefore:

- If the business limit is **character count**, consider `char_length`.
- If a protocol or file limit is **byte count**, use `octet_length` or a byte-based rule.
- If you need display character count (*grapheme clusters*), that is more complex than SQL character count; `char_length` does not automatically match how users perceive accented letters or emojis.

`btrim` by default strips certain whitespace characters according to its definition and is not a full Unicode whitespace validator for all scripts. Strings with control characters or special whitespace may still need normalization at another layer.

### 7.2. Format Validation with Regex

A currency code with exactly three uppercase Latin letters:

```sql
CREATE TABLE check_lab.currency_codes (
    code TEXT PRIMARY KEY,
    CONSTRAINT currency_codes_format
        CHECK (code ~ '^[A-Z]{3}$')
);
```

The `~` operator performs a PostgreSQL regular expression match.

Examples:

- `USD` → matches.
- `usd` → does not match under a case-sensitive regex.
- `US` → does not match.
- `USDD` → does not match.

However, **`AAA` matching the regex does not prove it is a recognized currency code**. Regex checks syntax, not reference validity or active status. To restrict codes to a managed list, use a **currency reference table + foreign key**.

### 7.3. Is Regex Email Validation Enough?

An expression like:

```sql
CHECK (email ~ '^[^@]+@[^@]+\.[^@]+$')
```

only checks a basic syntactic shape; it does not prove:

- The mailbox exists.
- The domain accepts mail.
- The user owns the email address.
- The format covers every valid case in email standards.
- The address has been verified through a business flow.

For login emails, applications usually need policy-based normalization, ownership verification, appropriate uniqueness rules, and handling of address changes over time. `CHECK` can serve as a limited syntax guard, **not a replacement for email verification**.

### 7.4. Correctness Depends on Collation and Normalization

String comparison rules, case sensitivity, sort order, and matching can be affected by collation and data normalization. Do not rely on a simple regex to claim product codes or usernames are fully normalized.

If SKUs must be unique after lowercasing, one option is a **unique expression index**:

```sql
CREATE UNIQUE INDEX products_sku_lower_unique
ON check_lab.products (lower(sku));
```

Run this example only on a lab table with non-conflicting data. This index addresses **uniqueness**; it cannot be replaced by `CHECK (lower(sku) = sku)` if the goal is to prevent duplicates across **multiple rows**.

---

## 8. What CHECK Cannot Check Directly

Fundamental limitation: `CHECK` is designed to validate a single row when inserted or updated. Do not treat it as a general-purpose query mechanism over other rows or tables.

### 8.1. Cannot Write Table-Wide COUNT(*) Inside CHECK

Suppose a system allows at most 10 active members in a group. A flawed idea is:

```sql
-- INVALID idea for direct CHECK:
CHECK (
    (SELECT COUNT(*)
     FROM group_members
     WHERE group_id = ...) <= 10
)
```

PostgreSQL **does not allow direct subqueries in CHECK**. Even if you wrap the count inside a function to bypass the syntax restriction, concurrency and future data mutations mean it is not a safe single-row invariant.

Solutions depend on the problem:

- Design a summary/counter row updated conditionally inside a transaction.
- Lock the group row while allocating slots.
- Use an appropriate isolation level with retry when needed.
- Model constraints for elements representable as unique keys.
- Use triggers with carefully designed locking/concurrency if required.

### 8.2. Cannot Use CHECK Instead of FOREIGN KEY

Suppose `orders.customer_id` must reference an existing customer.

Wrong idea:

```sql
-- CHECK is not for checking existence in another table:
CHECK (customer_id IN (SELECT customer_id FROM customers))
```

Instead use:

```sql
customer_id BIGINT REFERENCES customers(customer_id)
```

`FOREIGN KEY` also coordinates with transactions, updates, and deletes on the referenced table through integrity mechanisms that an ad-hoc read query inside `CHECK` cannot safely replicate.

### 8.3. Cannot Use CHECK Instead of UNIQUE

A table with two rows sharing `sku = 'ABC'` still satisfies `CHECK (sku <> '')`. To forbid duplicates, use:

```sql
CONSTRAINT products_sku_unique UNIQUE (sku)
```

or an appropriate unique index supporting normalization or partial predicates.

Do not write a `CHECK` function that scans the entire table counting duplicate SKUs; that lacks the concurrency guarantees and global enforcement of a unique constraint/index.

### 8.4. Cannot Use CHECK to Prevent Overlapping Bookings Across Rows

`CHECK (starts_at < ends_at)` validates time ordering within **one** booking.

To prevent two bookings for the same room from having overlapping time ranges, PostgreSQL provides **range types** such as `tstzrange` and `EXCLUDE` constraints with matching operators. Some designs require an extension such as `btree_gist` to support equality on the room key inside GiST.

That design differs from `CHECK` because it enforces **conflicts across rows**. Installing extensions and defining exclusion constraints requires privileges, migration planning, and understanding interval boundary semantics (for example, `[)` allows adjacent back-to-back bookings).

### 8.5. Cannot Use CHECK to Conserve Total Balance Across Rows

A wallet table has:

```sql
balance_minor BIGINT NOT NULL
CHECK (balance_minor >= 0)
```

This prevents a negative balance on any single wallet. However, when transferring 1000 cents from A to B, `CHECK` does not guarantee that **subtracting from A also adds the exact amount to B**.

Protecting that invariant requires a transaction, identifying both wallets correctly, checking currency units, conditional updates, checking affected row counts, and recording appropriate ledger/idempotency entries.

---

## 9. CHECK Does Not Track the Passage of Time

A tempting but usually flawed modeling rule is:

```sql
-- Design example NOT RECOMMENDED for enforcing long-term "not expired" validity.
CHECK (expires_at > now())
```

Suppose at `INSERT` time, `expires_at` is tomorrow so the condition holds. Two days later, the row has expired, yet no `INSERT` or `UPDATE` touched it. PostgreSQL does not run a background task to continuously re-evaluate `CHECK` constraints.

Therefore, a constraint referencing **current time** is unsuitable for defining a permanently true invariant like “only store unexpired rows”.

A better approach:

- Store `expires_at` as data.
- Check “currently valid” in queries or business logic at point of use:
  `WHERE expires_at > now()`.
- Use a job/scheduler to transition statuses or clean up expired rows if needed.
- If you only need to validate a static relationship within the row, use `CHECK (expires_at > created_at)` with deterministic, non-NULL columns as needed.

Static relationship example:

```sql
CREATE TABLE check_lab.tokens (
    token_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT tokens_expiry_after_creation
        CHECK (expires_at > created_at)
);
```

As time passes, `expires_at > created_at` remains true because neither column of the row changed. Whether a token is “expired yet” is evaluated when needed, not as a permanent `CHECK` invariant.

---

## 10. Functions in CHECK: Stability Requirements and Behavior-Change Risks

PostgreSQL allows many functions and expressions inside `CHECK`, but by design it **assumes the check outcome is stable for the same row data**. This is generally understood as requiring semantic **immutability**.

A sensible example:

```sql
CHECK (btrim(sku) <> '')
```

For the same `sku` value and unchanged function behavior, the result is stable.

A risky example:

```sql
-- Do NOT use volatile/non-deterministic functions in CHECK:
CHECK (random() > 0.5)
```

`random()` can return different results even though the row's data has not changed. The same row might be accepted once and rejected later regardless of its stored values.

Similarly, calling a function inside `CHECK` that depends on another table, session configuration, or external resources is a design smell that should be reviewed.

### 10.1. Changing a Function Definition Can Invalidate Existing Rows

Suppose a constraint calls a custom function `is_valid_code(code)`. After the table has data, an operator modifies the function body so that a previously valid code now returns `FALSE`.

**PostgreSQL does not automatically re-scan the entire table when a function definition changes.** Existing rows may now violate the function's new meaning. During a dump/restore or a later row update, new errors can surface.

If validation logic must change:

1. Identify stored rows that would become invalid.
2. Design a migration to clean up or transform existing data.
3. Replace or recreate the constraint in a controlled workflow.
4. Validate and verify results; never silently alter the body of a function used in `CHECK` without managing historical data.

Marking a function `IMMUTABLE` in DDL is a **promise about its behavior**, not a way to make a function that actually depends on time or another table safe.

### 10.2. CHECK Is Not a Place for Side Effects

Do not write `CHECK` functions intended to:

- Send emails or HTTP requests.
- Insert rows into other tables.
- Call external services.
- Mutate application state.
- Generate keys or cause side-effecting data mutations.

`CHECK` is for **validity checking**, not workflows. Use application code, transactions, appropriate triggers, or an outbox pattern when business side effects are required.

---

## 11. CHECK, NOT NULL, DEFAULT, and Data Types

These four mechanisms complement one another and cannot be swapped arbitrarily.

### 11.1. Data Types Constrain Value Form

Example:

```sql
quantity INTEGER
price NUMERIC(12,2)
created_at TIMESTAMPTZ
```

PostgreSQL only accepts values convertible to the target type. A string like `'abc'` cannot normally be inserted into an `INTEGER` column.

However, `INTEGER` does not forbid `-5`; `NUMERIC(12,2)` does not forbid negative prices; and `TIMESTAMPTZ` does not know an end date must follow a start date.

### 11.2. NOT NULL Guarantees Presence of Data

```sql
quantity INTEGER NOT NULL
```

If the caller supplies no value and there is no applicable default, `INSERT` is rejected with `not_null_violation`, typically SQLSTATE `23502`.

### 11.3. DEFAULT Supplies a Value When Omitted

```sql
stock_quantity INTEGER NOT NULL DEFAULT 0
    CHECK (stock_quantity >= 0)
```

When `INSERT` omits `stock_quantity`, default 0 is used. If you **explicitly pass NULL** for the column, `DEFAULT 0` does not overwrite NULL; `NOT NULL` rejects it.

`DEFAULT` also does not fix invalid explicit values such as `-3`. `CHECK` will reject the negative number in this example.

### 11.4. CHECK Enforces Value Domains and Relationships

```sql
price NUMERIC(12,2) NOT NULL
    CHECK (price >= 0)
```

The schema combines three layers:

1. `NUMERIC(12,2)`: decimal type with declared precision and scale.
2. `NOT NULL`: value must be present.
3. `CHECK (price >= 0)`: negative prices are disallowed.

Note that `NUMERIC(12,2)` can **round** input to scale 2 before the final value is checked. If an API must reject inputs with more than two fractional digits, validate before casting, such as in the application or a staging text column.

---

## 12. What Does a CHECK Error Look Like?

Using `check_lab.products`, try:

```sql
INSERT INTO check_lab.products (
    sku, product_name, list_price
)
VALUES ('BAD-001', 'Invalid product', -100);
```

PostgreSQL may return a message like:

```text
ERROR: new row for relation "products"
violates check constraint "products_list_price_nonnegative"
```

In drivers, a `CHECK` constraint error typically has SQLSTATE:

```text
23514  check_violation
```

Comparison:

| SQLSTATE | Common Name | Meaning |
| --- | --- | --- |
| `23514` | `check_violation` | A CHECK expression was violated |
| `23502` | `not_null_violation` | A required column received NULL |
| `23505` | `unique_violation` | Duplicate unique/primary key |
| `23503` | `foreign_key_violation` | Foreign key relationship violation |

Applications should classify errors using **SQLSTATE and structured metadata** provided by the driver rather than parsing message strings that can vary by locale or version.

### 12.1. Do Not Expose Sensitive Data Details Through APIs

Raw PostgreSQL error messages can include table names, constraint names, and sometimes row value details. When returning errors to clients:

- Translate into an appropriate business message, e.g., “List price must be non-negative”.
- Do not leak internal schema structure, private data, or full SQL queries.
- Log errors in a controlled manner for diagnostics.
- Do not turn every `CHECK` error into HTTP 500 when it is a known input error; conversely, do not assume every `23514` error was directly caused by end-user input.

### 12.2. An Error Inside a Transaction

```sql
BEGIN;

INSERT INTO check_lab.products (
    sku, product_name, list_price
)
VALUES ('BAD-002', 'Error', -10);

-- After a statement fails, the transaction enters an aborted state.
ROLLBACK;
```

If you want to test several failing statements in one `psql` session, the simplest approach is running each statement in autocommit mode. Inside an explicit transaction, use `ROLLBACK` or `SAVEPOINT` appropriately.

---

## 13. Updates Must Also Satisfy CHECK

Constraints do not apply only on `INSERT`. An `UPDATE` producing a row where a `CHECK` expression evaluates to `FALSE` is rejected.

Example on `products`:

```sql
UPDATE check_lab.products
SET discount_amount = 999999.00
WHERE sku = 'BOOK-001';
```

Because `BOOK-001` has `list_price` 125000, `discount_amount <= list_price` becomes `FALSE`, so the `UPDATE` violates the constraint.

Or:

```sql
UPDATE check_lab.products
SET status = 'ACTIVE'
WHERE sku = 'GIFT-003';
```

Row `GIFT-003` has `list_price` 0, so changing it to `ACTIVE` is blocked by `products_active_price_positive`.

### 13.1. Validating the Final Row State of a Statement

`CHECK` expresses valid row state as PostgreSQL validates each DML statement, not multi-step workflows outside a statement. When changing multiple related columns, update them **in the same UPDATE statement** when needed to reach a valid final state:

```sql
UPDATE check_lab.products
SET
    list_price = 20000.00,
    status = 'ACTIVE'
WHERE sku = 'GIFT-003'
RETURNING sku, list_price, status;
```

This succeeds because the resulting row after `UPDATE` has `ACTIVE` status and a positive price.

Do not change `status` to `ACTIVE` in one `UPDATE` and update `list_price` in a second statement if the intermediate row violates `CHECK`. With `CHECK`, you cannot tell PostgreSQL to ignore the failure and “wait to fix it at the end of the transaction”.

---

## 14. CHECK Does Not Support DEFERRABLE

PostgreSQL allows deferring validation for certain constraints such as `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY`, and `EXCLUDE` when declared appropriately. However, **`CHECK` is not among the constraint types that can be declared `DEFERRABLE`** in PostgreSQL.

Thus, there is no standard way to write:

```sql
-- Invalid for CHECK in PostgreSQL:
CHECK (quantity >= 0) DEFERRABLE INITIALLY DEFERRED
```

and:

```sql
SET CONSTRAINTS ALL DEFERRED;
```

does not defer an ordinary `CHECK` constraint until `COMMIT`.

### 14.1. Why Does This Matter?

Suppose a table has `CHECK (balance >= 0)`. If an `UPDATE` temporarily makes `balance` negative and you intend to add funds back in the next statement, PostgreSQL will not accept the violating intermediate value just because the transaction might fix it later.

You must structure operations so that **each DML result checked is valid**.

For multi-row invariants that can only be evaluated at transaction end, `CHECK` is usually not the right tool; consider data model changes, other constraint types, or a well-designed trigger/transaction mechanism.

---

## 15. Adding CHECK to a Table with Existing Data

A practical issue: a legacy table already has 10 million rows, and some rows have negative prices. Adding a `CHECK` immediately across the whole table forces PostgreSQL to scan existing rows and reject the DDL if any violation exists.

### 15.1. Standard Addition

```sql
ALTER TABLE check_lab.products
ADD CONSTRAINT products_discount_cap
CHECK (discount_amount <= 1000000);
```

When adding a constraint normally, PostgreSQL must verify that all existing data satisfies the rule. On large tables, the required scan and locks can impact operations, so migration planning is necessary.

### 15.2. NOT VALID: Enforcing New Rules Before Checking All Legacy Data

For `CHECK`, PostgreSQL supports:

```sql
ALTER TABLE some_table
ADD CONSTRAINT some_table_rule
CHECK (some_column >= 0) NOT VALID;
```

This means:

- The constraint is added **without requiring immediate validation of all existing rows**.
- Subsequent `INSERT` and `UPDATE` operations **still must satisfy the constraint**.
- The constraint is not yet marked validated across the whole table, because old violating rows may remain.
- After cleaning up the data, an administrator can run `VALIDATE CONSTRAINT`.

**`NOT VALID` does not mean “the constraint is disabled for new writes”.** That is a very common misconception.

### 15.3. Lab: Adding CHECK When Violating Legacy Rows Exist

Create a legacy table:

```sql
CREATE TABLE check_lab.legacy_prices (
    legacy_id INTEGER PRIMARY KEY,
    price NUMERIC(12,2)
);

INSERT INTO check_lab.legacy_prices (legacy_id, price)
VALUES
    (1, 100.00),
    (2, -5.00),
    (3,  20.00),
    (4, NULL);
```

Add the constraint **without validating legacy data**:

```sql
ALTER TABLE check_lab.legacy_prices
ADD CONSTRAINT legacy_prices_nonnegative
CHECK (price >= 0) NOT VALID;
```

Inspect the constraint:

```sql
SELECT
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'check_lab.legacy_prices'::regclass
ORDER BY conname;
```

`convalidated` for `legacy_prices_nonnegative` is initially `false`.

At this point, the row with `price = -5` still exists because old data has not been validated.

If you attempt a new `INSERT` with a negative price:

```sql
-- Expected to raise check_violation even while constraint is NOT VALID.
INSERT INTO check_lab.legacy_prices (legacy_id, price)
VALUES (5, -2.00);
```

PostgreSQL rejects it. That confirms the constraint already protects new write operations.

### 15.4. Finding and Fixing Violating Legacy Rows

With `price >= 0`, rows with negative prices violate the rule. In the lab:

```sql
SELECT legacy_id, price
FROM check_lab.legacy_prices
WHERE price < 0;
```

The result includes `legacy_id = 2`.

To fix data, follow business truth. This lab resets it to 0:

```sql
UPDATE check_lab.legacy_prices
SET price = 0
WHERE legacy_id = 2;
```

In production, **do not blindly turn every negative price into 0** if there may be refunds, credits, or corrupted records needing investigation. That choice is only for this lab example.

The row with `price = NULL` **does not violate** `CHECK (price >= 0)` because the expression returns unknown. If price must be required, add `NOT NULL` after handling NULLs per a separate plan.

### 15.5. Validating After Cleanup

```sql
ALTER TABLE check_lab.legacy_prices
VALIDATE CONSTRAINT legacy_prices_nonnegative;
```

Once all rows pass verification, `convalidated` becomes `true`:

```sql
SELECT
    conname, convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'check_lab.legacy_prices'::regclass;
```

If any violating legacy rows remain, validation fails and the constraint is not yet fully verified. Never treat `ADD CONSTRAINT ... NOT VALID` as a completed migration until validation succeeds.

### 15.6. Does NOT VALID Eliminate All Locks?

No. `ADD CONSTRAINT ... NOT VALID` avoids scanning the entire table right away, and `VALIDATE CONSTRAINT` has locking characteristics suited for managing large tables, but **that does not mean zero locks or zero workload impact**.

In production, evaluate the PostgreSQL version, table size, active transactions, maintenance window, and rollback plan. Never run DDL on hot tables solely assuming “`NOT VALID` is always instantaneous and lock-free”.

---

## 16. Inspecting Existing Constraints in the Catalog

PostgreSQL stores constraint metadata in system catalogs, with `pg_constraint` being a key source.

Example:

```sql
SELECT
    conname AS constraint_name,
    contype AS constraint_type,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'check_lab.products'::regclass
ORDER BY conname;
```

Common `contype` values:

| Value | Type |
| --- | --- |
| `c` | CHECK |
| `p` | PRIMARY KEY |
| `u` | UNIQUE |
| `f` | FOREIGN KEY |
| `x` | EXCLUDE |

To list only `CHECK` constraints:

```sql
SELECT
    conname,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'check_lab.products'::regclass
  AND contype = 'c'
ORDER BY conname;
```

If you are using `psql`, the command:

```text
\d+ check_lab.products
```

displays columns and constraints. This is a `psql` meta-command, not raw SQL accepted verbatim by every GUI client.

### 16.1. Changing or Dropping a CHECK Constraint

When business rules change, you may need to update a constraint definition. PostgreSQL typically uses drop/add operations rather than editing the expression in place:

```sql
-- Illustrative example; execute only under an approved migration.
ALTER TABLE check_lab.products
DROP CONSTRAINT products_discount_cap;
```

Then you can add the new definition with an appropriate name.

**Do not drop a constraint just to temporarily work around data entry errors in production.** Removing the safeguard lets other writers insert invalid data during the gap.

In safer workflows, you can add the new constraint first, clean up data, validate, and then remove the old rule in a controlled sequence, depending on requirements and compatibility between the two conditions.

---

## 17. CHECK and Imported File Data

When using `COPY FROM` or `\copy` to load data into a table, PostgreSQL still enforces supported constraints, including `CHECK`.

Suppose a CSV contains:

```csv
sku,product_name,list_price,discount_amount,stock_quantity,status
BOOK-100,CSV Imported Book,100000,0,20,ACTIVE
BAD-100,Invalid Product,-1000,0,10,ACTIVE
```

Importing into `check_lab.products` with a column list:

```text
\copy check_lab.products (sku, product_name, list_price, discount_amount, stock_quantity, status) FROM 'products.csv' WITH (FORMAT csv, HEADER true)
```

will be rejected because one row has `list_price = -1000`, violating `products_list_price_nonnegative`. Simply having a readable file does not mean every row is allowed into the table.

**Note:** `\copy` is a `psql` meta-command. `products.csv` is read on the machine running `psql`, not from the PostgreSQL server's filesystem.

### 17.1. Using a Staging Table When Source Data Is Untrusted

For data that may contain many errors, load raw text into a staging table first:

```sql
CREATE TABLE check_lab.product_import_stage (
    source_line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku_text TEXT,
    name_text TEXT,
    price_text TEXT,
    discount_text TEXT,
    stock_text TEXT,
    status_text TEXT
);
```

Staging lets you:

1. Preserve raw input for investigation.
2. Separate format/type errors from constraint errors.
3. Check missing data before casting.
4. Normalize whitespace and number formats.
5. Handle duplicate keys per policy.
6. Promote only valid rows into the target table inside a managed transaction.

Example preliminary check:

```sql
SELECT *
FROM check_lab.product_import_stage
WHERE sku_text IS NULL
   OR btrim(sku_text) = ''
   OR price_text IS NULL
   OR price_text !~ '^[0-9]+(\.[0-9]{1,2})?$'
   OR status_text IS NULL
   OR status_text NOT IN ('DRAFT', 'ACTIVE', 'ARCHIVED');
```

This is only a **simple syntactic check**: the regex does not prevent numbers too large for `NUMERIC(12,2)`, nor does it catch currency errors, negative-value business rules, duplicate SKUs, unusual Unicode characters, or other conflicts.

**Do not turn every blank cell into 0** and do not silently discard bad rows just to make an import succeed.

### 17.2. CHECK and Rounded Values

With:

```sql
list_price NUMERIC(12,2) NOT NULL CHECK (list_price >= 0)
```

PostgreSQL can round an input like `12.345` to `12.35` per the column's scale before storing it. `CHECK` only verifies that the final number is non-negative; it **does not prove the source file had at most two decimal places**.

If the requirement is “reject prices with more than two fractional digits”, validate the **raw input** before casting, such as in a text staging column or the application.

---

## 18. CHECK and Concurrency: What Is Guaranteed?

When multiple transactions write to a table concurrently, PostgreSQL still checks `CHECK` on the written rows. However, a per-row expression **does not automatically enforce** invariants spanning multiple rows or concurrent reads.

### 18.1. Non-Negative Inventory Example

Suppose a product has `stock_quantity = 3`, and two clients concurrently try to sell 2 units each.

Conditional update pattern:

```sql
UPDATE check_lab.products
SET stock_quantity = stock_quantity - 2
WHERE sku = 'BOOK-001'
  AND stock_quantity >= 2
RETURNING product_id, stock_quantity;
```

This `UPDATE` both deducts stock and checks available inventory under PostgreSQL's row-locking and isolation rules. After one transaction sells 2, the other request may update 0 rows if insufficient stock remains.

**The application must inspect the rows returned by `RETURNING`**: updating 0 rows is not a SQL error, but it represents the business outcome “insufficient stock / product not found”.

`CHECK (stock_quantity >= 0)` acts as an extra safeguard against other code paths accidentally driving inventory negative.

### 18.2. Why Is SELECT-Then-UPDATE Risky?

A flow without concurrency protection:

```text
Client A: SELECT stock = 3
Client B: SELECT stock = 3
Client A: computes 3 - 2 = 1
Client B: computes 3 - 2 = 1
Client A: UPDATE stock = 1
Client B: UPDATE stock = 1
```

This can let two orders think they both succeeded while stock was only deducted once. `CHECK (stock >= 0)` still passes for the final value 1, so it **does not catch lost updates or stale reads**.

Coordinated approaches include:

- `UPDATE ... SET stock = stock - qty WHERE stock >= qty RETURNING ...`.
- Transactions with `SELECT ... FOR UPDATE` where appropriate.
- Appropriate isolation levels and retry logic for the business model.
- Recording order/stock movements in the same transaction and verifying affected row counts.
- Idempotency keys when clients may retry requests.

### 18.3. CHECK Does Not Replace Isolation Levels

Two transactions can observe different rows and update them in a way that violates a table-wide invariant (*write skew*), while each individual row still satisfies `CHECK`.

If an invariant can only be expressed globally, consider:

- Redesigning the schema to enable a stronger constraint.
- `SERIALIZABLE` isolation where appropriate, retrying the whole transaction on `serialization_failure`.
- Locking a representative parent/resource row.
- Triggers or constraint triggers with a strict locking strategy.

Never add `CHECK (some_custom_function())` and assume concurrency is solved.

---

## 19. CHECK vs. Triggers: Which One Should You Use?

**CHECK** is usually best when:

- The rule depends entirely on columns within a single row.
- The expression is relatively simple and deterministic/stable.
- No side effects are needed.
- You want the rule visible in the schema and automatically enforced by the database.

**Triggers** may be needed when:

- Complex logic must execute on `INSERT`/`UPDATE`/`DELETE`.
- Audit tables or outbox tables must be updated in a designed workflow.
- Multiple tables must be coordinated with explicit understanding of transactions and concurrency.

However, triggers do not automatically provide global guarantees: a trigger that merely runs `SELECT COUNT(*)` under concurrent transactions can still suffer race conditions without proper locking or isolation.

### 19.1. Practical Comparison

| Requirement | Typical Appropriate Tool |
| --- | --- |
| `quantity >= 0` | CHECK |
| `discount <= price` within the same row | CHECK |
| `email IS NOT NULL` | NOT NULL |
| Each SKU appears at most once | UNIQUE or unique index |
| `customer_id` must exist | FOREIGN KEY |
| Two bookings for the same room cannot overlap | EXCLUDE with appropriate range type and operators |
| Active members in a group must not exceed N | Counter design / transaction / locking or other coordination |
| Write an audit record when an order is updated | Trigger or application/outbox, depending on architecture |
| An order can only transition along valid workflow edges | Application logic or trigger/transaction; CHECK only validates allowed states at a point in time |
| Data is only valid up to the current date | Check in queries/business logic against current time, not dynamic CHECK |
| Send an email after a transaction | External workflow/outbox, not CHECK |

Start by asking: **does this rule depend only on the state of a single row at write time?** If yes, `CHECK` is likely a good fit. If not, evaluate another tool.

---

## 20. CHECK in Domains for Reusable Rules

Beyond table-level `CHECK` constraints, PostgreSQL supports **domains**: user-defined data types based on an underlying type that can include constraints.

Example domain for percentages:

```sql
CREATE DOMAIN check_lab.percentage AS NUMERIC(5,2)
    CHECK (VALUE >= 0 AND VALUE <= 100);
```

Usage:

```sql
CREATE TABLE check_lab.campaigns (
    campaign_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    campaign_name TEXT NOT NULL,
    discount_percent check_lab.percentage NOT NULL
);
```

Domains let multiple tables or columns share value rules, reducing duplicate definitions.

However:

- A domain's `CHECK` also follows SQL's NULL logic; if a column must be required, evaluate `NOT NULL` at the column level as in the example.
- A domain cannot enforce rules across **two columns of a row**, such as discount amount not exceeding list price; that remains a table `CHECK`.
- When altering a domain shared across many tables, evaluate existing data and the impact on all consumers.

Do not put every business rule into a domain solely for reuse; domains work best for **value domains that genuinely share identical semantics** across tables.

---

## 21. CHECK with Partitioning and Table Inheritance

In larger systems, tables may use partitioning or inheritance. `CHECK` constraints can help express data ranges or be inherited according to PostgreSQL rules.

Key points to remember:

- A parent table's `CHECK` constraint can have inheritance relationships with child tables depending on table structure and definition.
- PostgreSQL offers `NO INHERIT` syntax for certain `CHECK` constraints in inheritance hierarchies; do not use it without understanding the implications.
- With declarative partitioning, each partition's bounds are managed by partition bounds; additional `CHECK` constraints can enforce business rules but do not replace partition key bounds.
- When adding or validating constraints across large table/partition trees, assess object scope and lock impact.

For an introductory foundation, get `CHECK` design right on standalone tables first, then expand to partitioning/inheritance once you understand the specific data model.

---

## 22. Common Misconceptions

| Misconception | More Accurate Reality |
| --- | --- |
| “`CHECK(price > 0)` blocks all missing values.” | `CHECK` permits `NULL` when the expression is unknown; use `NOT NULL` when required. |
| “`CHECK` only runs on `INSERT`.” | `CHECK` also runs whenever `UPDATE` produces a row to validate. |
| “`CHECK` guarantees data stays valid forever as time passes.” | It does not continuously re-evaluate rows as dates advance or functions change. |
| “You can run `SELECT COUNT(*)` inside `CHECK`.” | PostgreSQL forbids direct subqueries in `CHECK`; table-wide invariants need other mechanisms. |
| “You can use `CHECK` to enforce FKs.” | Use `FOREIGN KEY`, which also protects changes and deletes in the referenced table. |
| “You can use `CHECK` to forbid duplicate SKUs.” | Use `UNIQUE` or a unique index. |
| “`CHECK(amount >= 0)` guarantees money transfers are accurate.” | It only constrains a single row, not two balanced entries in a transaction. |
| “`CHECK` can be `DEFERRABLE` until `COMMIT`.” | PostgreSQL does not support `DEFERRABLE` for `CHECK` constraints. |
| “`CHECK` requires the whole expression to return `TRUE`.” | Under SQL `CHECK`, both `TRUE` and `NULL` are non-violating. |
| “`DEFAULT 0` turns every `NULL` into 0.” | `DEFAULT` applies when a column is omitted or `DEFAULT` is passed, not when `NULL` is explicitly supplied. |
| “`NOT VALID` means new rows are not checked.” | `NOT VALID` skips verifying existing rows on add; new writes are still checked. |
| “`VALIDATE CONSTRAINT` is just a metadata change.” | It must scan existing data and fails if any violation remains. |
| “Changing a custom function causes PostgreSQL to recheck all rows.” | It does not re-scan automatically; old rows can silently contradict the new logic. |
| “Matching an email regex means the email works.” | A simple regex only checks shape, not mailbox existence or ownership. |
| “`CHECK` constraints handle all concurrency cases.” | They do not guarantee multi-row invariants or prevent all lost updates/write skew. |
| “`CHECK` prevents SQL injection.” | `CHECK` does not replace prepared statements, parameter binding, and privileges. |
| “With `CHECK`, the application does not need to validate.” | Applications still need user-friendly messages, business rules, and pre-submission checks. |
| “Disable constraints during imports for speed and convenience.” | Dropping safeguards risks letting bad data in; use staging or controlled migrations. |

---

## 23. Practice Exercises

### Exercise 1 — Three-Valued Logic

Given:

```sql
CREATE TABLE check_lab.test_nulls (
    id INTEGER PRIMARY KEY,
    amount NUMERIC CHECK (amount > 0)
);
```

Predict the result of three statements:

```sql
INSERT INTO check_lab.test_nulls VALUES (1, 10);
INSERT INTO check_lab.test_nulls VALUES (2, -1);
INSERT INTO check_lab.test_nulls VALUES (3, NULL);
```

Explain why the third statement does not raise an error. Modify the DDL to forbid `NULL`.

### Exercise 2 — Multi-Column Validation

Create an `invoice_items` table with:

- `quantity INTEGER NOT NULL CHECK(quantity > 0)`.
- `unit_price NUMERIC(12,2) NOT NULL CHECK(unit_price >= 0)`.
- `discount NUMERIC(12,2) NOT NULL DEFAULT 0`.
- A `CHECK` ensuring `discount <= quantity * unit_price`.

Write three `INSERT` examples: valid, discount exceeding line total, and quantity equal to 0.

### Exercise 3 — State-Dependent Condition

A ticket has `status` in `NEW, PAID, CANCELED`. When status is `PAID`, `paid_at` must have a value.

Create the table and write a `CHECK` using `OR` or `CASE`. Test the case where `status = 'PAID'` and `paid_at IS NULL`.

### Exercise 4 — Time Ordering

Create a table where `starts_at` and `ends_at` are both `NOT NULL`, with `CHECK (starts_at < ends_at)`.

Then explain why two rows with overlapping intervals can still be inserted if only this `CHECK` is used.

### Exercise 5 — NOT VALID and VALIDATE

In `check_lab.legacy_prices`:

1. Insert rows with a negative price and `NULL` before adding the constraint.
2. Add `CHECK(price >= 0) NOT VALID`.
3. Try inserting a new negative price.
4. Find the legacy row with a negative price and fix it.
5. Run `VALIDATE CONSTRAINT`.
6. Check `convalidated` in `pg_constraint`.

Explain why the `NULL` row can still remain accepted.

### Exercise 6 — Choosing the Right Constraint

For these requirements:

- Non-negative balance.
- Unique product code.
- Customer in an order must exist.
- A room cannot have two overlapping bookings.
- Email must have a value.
- Sale price cannot exceed original price.

Choose `CHECK`, `NOT NULL`, `UNIQUE`, `FOREIGN KEY`, `EXCLUDE`, or an appropriate combination and explain why.

### Exercise 7 — Business Bug Even When CHECK Passes

Suppose `CHECK(stock >= 0)` is active. Two concurrent requests both read `stock = 3`, then both write `stock = 1` and both record selling 2 units.

Why didn't `CHECK` detect the mistake? Write the pattern `UPDATE ... SET stock = stock - 2 WHERE stock >= 2 RETURNING ...` and describe how the application handles returning 0 rows.

### Exercise 8 — Time-Sensitive Rule

Suppose a system wants “every stored token row is unexpired” using `CHECK(expires_at > now())`.

Why can a row that is valid today become expired tomorrow without PostgreSQL deleting it? Propose a query pattern `WHERE expires_at > now()` or an appropriate status workflow.

### Exercise 9 — Regex vs. Reference Source

A table validates currency codes with `CHECK(code ~ '^[A-Z]{3}$')`. Does `'AAA'` pass the regex? Does that prove it is a valid currency code? Design a reference table and `FOREIGN KEY` to manage the valid list.

### Exercise 10 — Distinguishing Errors in an API

PostgreSQL returns SQLSTATE:

```text
23514
23502
23505
23503
```

Distinguish `CHECK`, `NOT NULL`, `UNIQUE`, and `FOREIGN KEY`. In an application, what message should be returned to users and what details should be kept hidden?

### Exercise 11 — Rounding Before CHECK

Column `price NUMERIC(12,2) NOT NULL CHECK(price >= 0)` receives string `19.999` from a file.

What number will PostgreSQL store? Can `CHECK` detect that the input had 3 fractional digits? If the business must reject such inputs, design a text-level check before casting.

### Exercise 12 — Complex Business Rule

A group allows at most 10 `ACTIVE` members. Explain why `CHECK((SELECT COUNT(*) ... ) <= 10)` is invalid and why a trigger simply reading `COUNT` is unsafe when two sessions add members concurrently.

Propose locking the group row and conditionally updating a counter inside a transaction, or an appropriate isolation level with retry.

---

## 24. Checklist Before Adding CHECK to a Production System

| Question | Decision to Make |
| --- | --- |
| Does the rule depend strictly on one row? | If not, consider another constraint or transaction/locking. |
| Which columns may be NULL? | Place `NOT NULL` appropriately to avoid `UNKNOWN` in `CHECK`. |
| Is the expression stable? | Avoid `now()`, `random()`, functions reading other tables, or functions with side effects. |
| Does the data type coerce or round inputs? | Validate raw input beforehand if needed. |
| Is the exact rule shared across tables? | Consider a domain for shared value types. |
| Do you need to prevent duplicate values? | Use `UNIQUE` or a unique index instead of `CHECK`. |
| Is there a foreign key relationship? | Use `FOREIGN KEY`, do not emulate it with a `CHECK` function. |
| Is concurrency control needed? | Use transactions, conditional `UPDATE`, locking/isolation, and retries. |
| Does the table already have legacy data? | Audit violations before adding the constraint; consider `NOT VALID`. |
| Has legacy data been validated? | Run `VALIDATE CONSTRAINT` and inspect `pg_constraint`. |
| Is the constraint clearly named? | Helps migrations and application error handling. |
| Are there DDL table-lock risks? | Plan operations and rollback accordingly. |
| Are there writers/imports outside the main app? | DB constraints protect all paths; use staging where needed. |
| Does the API handle SQLSTATE codes? | Classify `23514`/`23502`/`23505`/`23503` without exposing sensitive details. |
| Were edge cases tested? | `NULL`, `0`, negatives, max values, empty strings, equal timestamps. |
| Is there a time-based expiration rule? | Use queries or background jobs rather than expecting `CHECK` to re-evaluate. |

## Conclusion

**`CHECK` is a core tool for protecting per-row data validity in PostgreSQL.** It expresses rules such as non-negative prices, discounts not exceeding original prices, end times after start times, or statuses within an allowed set. When new or updated data violates a condition, PostgreSQL rejects the write rather than trusting every application to validate consistently.

However, you must understand **`CHECK`'s limits**:

- Expressions returning `TRUE` **or `NULL`** do not violate `CHECK`; add `NOT NULL` when values are required.
- `CHECK` primarily validates data **within a single row**; it does not replace `UNIQUE`, `FOREIGN KEY`, `EXCLUDE`, or multi-row invariants.
- `CHECK` does not automatically re-evaluate existing rows as **time passes** or when functions change.
- `CHECK` is **not `DEFERRABLE`** in PostgreSQL.
- `NOT VALID` lets you add `CHECK` to tables with legacy data in phases while still enforcing it on new writes; `VALIDATE CONSTRAINT` is required to verify all existing data.
- `CHECK` does not replace transactions, locks, isolation levels, idempotency, application validation, or access controls.

Good design **places stable, clearly expressible single-row invariants into `CHECK`**, while choosing the right constraint types and transactional mechanisms for everything else. When each layer guards its proper scope, PostgreSQL helps keep data consistent even with multiple write paths and multiple client applications sharing the database.
