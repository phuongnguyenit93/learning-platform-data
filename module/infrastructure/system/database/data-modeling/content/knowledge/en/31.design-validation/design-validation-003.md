# Testing Invariants with Boundary Values, Missing Data, and Invalid States

## Learning Objectives and Scope

A data schema may look completely reasonable on an ERD yet still allow states the business **never accepts**: an order line with quantity 0, a discount exceeding the item amount, a confirmed order with zero product lines, a customer lacking any contact method, or two historical versions of a record simultaneously effective at one point in time. These flaws rarely appear in "clean" sample datasets because every row is complete and valid.

**Design validation** is the process of turning business statements into **observable, falsifiable invariants**. We intentionally feed boundary data, missing data, non-existent links, and illegal state transitions into a test system to verify whether the model **accepts valid data and rejects invalid data** strictly according to contract.

This lesson belongs to the **Design Validation** chapter of the **DATABASE_DATA_MODELING** module. The module's overall goal is to translate business requirements into clear data models—from entities, relationships, and constraints to normalization, keys, indexes, and physical schemas—while comparing relational, document, graph, and analytical models to achieve structures that fit, evolve cleanly, and can be verified. This lesson focuses on **testing invariants with boundary values, missing data, and invalid states**, rather than merely checking whether SQL runs.

After this lesson, you will be able to:

1. Distinguish **entity, relationship, dataset, state, and temporal invariants**, and identify where each should be enforced.
2. Construct test values **just below, right at, and just above thresholds**; distinguish valid from invalid cases per business domain.
3. Recognize the impact of **NULL, empty strings, unknown values, and SQL three-valued logic**, especially with `CHECK` and `UNIQUE`.
4. Design negative tests for **PK, FK, UNIQUE, NOT NULL, CHECK**, scoped uniqueness, and multi-row constraints.
5. Test **valid state transitions**, late-arriving data, non-overlapping time intervals, and invariants affected by concurrent transactions.
6. Write PostgreSQL examples with fixtures, violation-detection queries, and tests **expected to fail**.
7. Combine tests across **Java domain, application layer, database, and integration flows**, understanding each layer's limits.
8. Build a validation matrix and acceptance criteria so a model not only works on small sample data but withstands edge cases and change.

> **Scope note:** SQL examples use PostgreSQL in a test environment. They are not instructions for running intentionally failing commands in production. A statement rejected by a constraint is an **expected test outcome**, not a successful migration step. Invariants spanning multiple rows, transactions, or systems must be tested with appropriate mechanisms and cannot be proved by a single-row `CHECK` alone.

## 1. What Is an Invariant and Why Validate It?

### 1.1. Definition by Data Semantics

A **data invariant** is a condition that **must always hold at points where the system commits valid state**. Examples:

- Every sales order line has a **positive quantity**.
- Line discount amount lies within **[0, pre-discount gross amount]**.
- An order line's key points to an **existing order**.
- An account belonging to tenant A must not link to an object in tenant B when the business forbids it.
- A customer code has **at most one active SCD2 version at any point in time**.
- An order in `CONFIRMED` status must have **at least one valid order line**.

Not every rule has to be enforced by a single SQL statement. **The invariant defines what is true**, while `CHECK`, FK, transactions, triggers, API validation, and integration tests are **mechanisms that enforce or verify it at different boundaries**.

### 1.2. Distinguishing Invariant, Expectation, and Quality Threshold

| Statement type | Example | Interpretation |
| --- | --- | --- |
| **Hard invariant** | Order line has quantity > 0 | Any row with quantity = 0 is invalid |
| **Mandatory relationship** | `order_line.order_id` points to an existing order | Orphan lines are unacceptable in committed state |
| **State rule** | Only an eligible `DRAFT` order can be `CONFIRMED` | Must validate transition, not just status name |
| **Historical rule** | Two SCD2 effective intervals for the same customer do not overlap | Must check across rows and timestamps |
| **Business expectation** | 95% of orders ship within 2 days | This is a KPI; do not encode as `CHECK` "every order ships in 2 days" |
| **Data quality threshold** | Missing-address rate in legacy set < 1% | A measurement/acceptance policy criterion, not necessarily blocking individual rows |

Do not turn every statistical KPI into a hard constraint. Conversely, do not leave a critical invariant as a vague goal ("data should be good") when **bad state must be prevented at write time**.

### 1.3. Points in Time Where Invariants Must Hold

An invariant may be defined at:

- **Object/domain command creation**: cannot construct `Money` with an empty currency.
- **DB transaction completion**: `order_line` must have a matching order.
- **A business state transition step**: an order moving `DRAFT → CONFIRMED` must have valid lines.
- **Analytical data publication**: facts/dimensions must be complete enough so reports do not double-count.
- **Cross-system event processing**: projections may lag, yet must not show "settled" without accepted evidence.

Some models allow **intermediate states inside a transaction** before `COMMIT`, or inside a saga before completion. That never justifies publishing invalid data: **document which intermediate states are valid, who can observe them, and when the invariant must hold**.

## 2. Writing Invariants as Testable Conditions

### 2.1. From Vague Prose to Exact Statements

Sample requirement: "Disallow orders with abnormal discounts."

This statement is not testable yet. Break it down into:

1. Each line has an **integer positive quantity**, capped at 1,000 units per example policy.
2. Unit price locked on the line is **non-negative**, in VND.
3. **`discount_amount`** falls in `[0, quantity × unit_price]`.
4. **`net_amount`** equals `quantity × unit_price − discount_amount`.
5. If a valid free-item promotion exists, **`net_amount = 0` is permitted**.
6. If certain customers cannot receive a 100% discount, that is a **separate rule** tied to promotion type; do not invent it from the word "abnormal."

Testing **right at the boundary** must come from the specification, not from an intuition that "0 is always bad."

### 2.2. Invariant Specification Template

For each invariant, document:

~~~~text
INVARIANT ID: LINE-DISCOUNT-001

Subject: valid order line.
Scope: every persisted order_line.
Check timing: before/at COMMIT on insert or update.

Preconditions:
  quantity in [1,1000], integer.
  unit_price in VND, non-negative.

Predicate:
  0 <= discount_amount <= quantity * unit_price
  net_amount = quantity * unit_price - discount_amount

Allowed:
  discount_amount = 0
  discount_amount = quantity * unit_price

Disallowed:
  discount_amount < 0
  discount_amount > quantity * unit_price
  quantity = 0 or quantity > 1000

Enforcement:
  Domain/API validation + DB CHECK/NOT NULL
  net_amount is a generated column using the formula.

Verification:
  Test values at and adjacent to thresholds.
  Verify rejected SQL error codes.
  Reconcile formula over committed data.
~~~~

This template keeps QA, developers, data architects, and business owners aligned on **the exact same meaning**. A test only proves a rule once **inputs, timing, and expected outcomes** are specified.

### 2.3. Validation Flow from Requirements to Evidence

~~~~mermaid
flowchart TD
    A["Business requirements"] --> B["Invariant + scope + timing"]
    B --> C["Partition data: valid / boundary / missing / invalid"]
    C --> D["Model: types, keys, states, relationships"]
    D --> E["Safeguards: Java + SQL + transactions"]
    E --> F["Positive tests: valid data must pass"]
    E --> G["Negative tests: invalid data must be rejected"]
    F --> H["Reconciliation and evidence"]
    G --> H
    H --> I{"Matches contract?"}
    I -- "No" --> B
    I -- "Yes" --> J["Design accepted within tested scope"]
~~~~

Nowhere is there a step "draw a pretty ERD → assume data is right." **Evidence of accepting valid data and rejecting invalid data** is what confirms safeguards match the model.

## 3. Designing Boundary Data: Do Not Test Only Average Values

### 3.1. Equivalence Partitioning and Boundary Value Analysis

**Equivalence partitioning** divides the input domain into classes expected to behave identically. **Boundary value analysis** focuses on points **just below, right on, and just above** each class boundary.

For integer quantity in `[1,1000]`:

| Value | Partition | Expected outcome |
| ---: | --- | --- |
| -1 | Below allowed domain | Reject |
| 0 | Just below lower bound | Reject |
| **1** | **Valid lower bound** | Accept |
| 2 | Just above lower bound | Accept |
| 500 | Normal interior value | Accept |
| 999 | Just below upper bound | Accept |
| **1000** | **Valid upper bound** | Accept |
| 1001 | Just above upper bound | Reject |
| NULL | Missing data | Reject if quantity required |

If code checks `quantity > 1` instead of `>= 1`, testing the **lower boundary** catches it. If tests only try `quantity = 2` and `500`, the bug stays hidden.

### 3.2. Monetary and Unit Boundaries

With `unit_price NUMERIC(14,2)`, `discount_amount NUMERIC(14,2)`:

- **`0.00`** may be valid if the business permits free promotional items.
- **`-0.01`** must be rejected if prices are non-negative.
- A discount **equal** to gross amount may be valid by contract.
- A discount **0.01 above** gross amount must be rejected.
- Test **very large values, fractional digits, and `quantity × unit_price` products** to uncover overflow, truncation, or wrong rounding.
- Distinguish **VND, USD**, or minor currency units; the number `100` can have the right technical type yet carry the wrong business meaning.

Example with `quantity = 2`, `unit_price = 100000.00 VND`:

| discount_amount | Expected net_amount | Valid? |
| ---: | ---: | --- |
| -0.01 | N/A | No |
| 0.00 | 200000.00 | Yes |
| 199999.99 | 0.01 | Yes |
| 200000.00 | 0.00 | Yes per example rule |
| 200000.01 | N/A | No |

**Never store money in binary floating-point types when exact financial decimals are required.** Use decimal types with explicit rounding rules; test precision/scale limits in both Java and the database.

### 3.3. Temporal Boundaries

With half-open validity intervals **`[valid_from, valid_to)`** (inclusive start, exclusive end):

- **`valid_to = valid_from`**: empty interval; reject if every version must span a positive duration.
- **`valid_to` immediately after `valid_from`**: valid.
- **Timestamp equal to `valid_from`**: counts as effective.
- **Timestamp equal to `valid_to`**: **no longer** effective.
- **`valid_to` NULL**: may mean current version / open-ended, depending on contract.
- Two intervals for the same source and entity that **overlap** must be caught if the model forbids overlaps.

**Do not equate local calendar dates with UTC timestamps.** Test around midnight, time zones, year boundaries, and business calendar rules if they affect reporting.

### 3.4. Cardinality and Collection-Size Boundaries

For "a `CONFIRMED` order must have at least one line," test:

- **0 lines:** cannot `CONFIRM`.
- **1 line:** minimum valid line count.
- **Multiple lines:** valid if no other rule is broken.
- **Adding two lines with the same `line_no`:** violates `UNIQUE(order_id, line_no)`.
- **Deleting the last line of a `CONFIRMED` order:** must be blocked or trigger a valid state-transition workflow.

Major trap: an FK on `order_line.order_id` guarantees **the line has a parent**, yet **does not guarantee the parent has at least one line**. Those are opposite sides of the relationship.

## 4. Missing Data: NULL, Empty Strings, and "Unknown"

### 4.1. Absent Data Is Not Always NULL

| Representation | Possible meaning | Caveat |
| --- | --- | --- |
| **SQL NULL** | Unknown, not provided, or N/A if unsplit | A single SQL marker does not state **the reason** |
| **Empty string `''`** | Sender included field with zero characters | Distinct from `NULL` in PostgreSQL; may be invalid input |
| **Whitespace-only string** | Input contains only whitespace characters | Trim first, then validate per business rules |
| **Number `0`** | A concrete numeric value | Does not mean missing; inventory of 0 may be real |
| **`UNKNOWN` enum/member** | Named undetermined state | Distinguish from `NULL` and "not applicable" |
| **N/A / not applicable** | Attribute has no meaning for this entity | Do not mix with "not yet collected" |
| **Sentinel (`-1`, `9999-12-31`)** | Conventional placeholder value | Easily breaks `SUM`, `JOIN`, or comparisons if unmanaged |

For example, if a customer registers with phone only, `email = NULL` may be **valid**. Yet `email = '   '` is not a meaningful email address. Thus you can neither enforce `CHECK(email IS NOT NULL)` on all customers nor accept any arbitrary string just because the column is non-null.

### 4.2. Three-Valued Logic in SQL

SQL evaluates three logical outcomes: **TRUE**, **FALSE**, **UNKNOWN**. Comparisons involving `NULL` typically yield **UNKNOWN**, not `FALSE`.

~~~~sql
SELECT
    (NULL::INTEGER > 0) AS compare_null,
    (NULL::INTEGER = NULL::INTEGER) AS null_equals_null,
    (NULL::INTEGER IS NULL) AS null_check,
    (NULL::INTEGER IS NOT DISTINCT FROM NULL::INTEGER)
        AS null_safe_equal;
-- compare_null = NULL (UNKNOWN)
-- null_equals_null = NULL (UNKNOWN)
-- null_check = TRUE
-- null_safe_equal = TRUE
~~~~

This directly impacts **`CHECK`** constraints. In PostgreSQL, a `CHECK` **rejects a row only when it evaluates to FALSE**. If an expression evaluates to `UNKNOWN` due to `NULL`, `CHECK` **lets the row pass**.

~~~~sql
CREATE TABLE check_null_demo (
    quantity INTEGER CHECK (quantity > 0)
);

INSERT INTO check_null_demo(quantity)
VALUES (NULL); -- ACCEPTED: CHECK does not replace NOT NULL.
~~~~

If `quantity` is required, write:

~~~~sql
CREATE TABLE check_null_strict_demo (
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~~

**Rule of thumb:** Whenever you read a `CHECK` containing a comparison, ask **which columns can be NULL and whether UNKNOWN is allowed to slip through?** A strict-looking `CHECK` does not prove the constraint is tight.

### 4.3. NULL in UNIQUE and Foreign Keys

In PostgreSQL, a standard `UNIQUE` constraint **allows multiple rows containing `NULL`** in the compared column because `NULL`s are not considered equal under default `UNIQUE` semantics. For an optional email, this makes sense: many phone-only customers share `email = NULL`.

~~~~sql
CREATE TABLE email_unique_demo (
    person_id BIGINT PRIMARY KEY,
    email TEXT UNIQUE
);

INSERT INTO email_unique_demo(person_id, email)
VALUES (1, NULL), (2, NULL);
-- Two rows with NULL email are accepted under default UNIQUE.
~~~~

If the business genuinely wants **to treat NULL as a duplicate**, modern PostgreSQL offers `UNIQUE NULLS NOT DISTINCT`, though you must check engine version and apply it only in the right scope. **Never forbid multiple NULL emails just to "make UNIQUE stronger"** when the business permits users without email.

For a nullable FK, a row with `child_fk = NULL` is normally not flagged as an orphan: **there is no reference to check**. If the relationship is mandatory, combine **`NOT NULL` + `FK`**. For composite FKs, decide how partially-NULL components behave (default `MATCH SIMPLE` skips checks when any component is NULL); if the whole composite key must be populated, mark the columns `NOT NULL` or add an appropriate rule.

### 4.4. Testing Missing Data Across Distinct Cases

For an API accepting email and phone:

~~~~text
{ "email": "a@example.org", "phone": null }
{ "email": null, "phone": "0900000000" }
{ "email": null, "phone": null }
{ "email": "", "phone": "" }
{ "email": "   ", "phone": null }
{ "email": "a@example.org" }  (phone omitted)
{ }  (both fields omitted)
~~~~

**JSON omission**, **JSON `null`**, and **SQL `NULL`** may be mapped differently by frameworks, especially on `PATCH`: an omitted field often means **no change**, whereas `null` means **clear the value**. Test the API contract and mapping directly rather than guessing from DDL.

In the next example, the business rule is **a customer must have at least one non-empty contact method after trimming**, while strict syntax/ownership verification of emails and phone numbers is handled further at the boundary and dedicated checks.

## 5. Building a PostgreSQL Schema to Validate Invariants

### 5.1. Test Dataset Context

A small sales system has:

- **Customer:** at least one non-empty contact method; email is optional, yet if present cannot be blank.
- **Product:** unique SKU and non-negative list price.
- **SalesOrder:** belongs to one real customer, status in `{DRAFT, CONFIRMED, CANCELLED}`, valid `confirmed_at`.
- **OrderLine:** belongs to one order, references a real product; `line_no` unique within the order; `quantity` from 1 to 1,000; valid price and discount.
- **Additional business target:** A `CONFIRMED` order must have at least one valid line. This is a **multi-row invariant**, requiring enforcement beyond a single-row `CHECK`.

These rules are **lesson assumptions**. Real systems may need fractional quantities by unit of measure, negative prices for adjustment entries, multiple currencies, or anonymous guests. Before altering constraints, establish **business meaning** instead of blindly copying the example.

### 5.2. Tables and Constraints

Run in a dedicated test database with schema/table creation privileges:

~~~~sql
CREATE SCHEMA validation_lab;

CREATE TABLE validation_lab.customer (
    customer_id BIGINT PRIMARY KEY,
    email TEXT,
    phone TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_email_not_blank
        CHECK (email IS NULL OR BTRIM(email) <> ''),
    CONSTRAINT ck_phone_not_blank
        CHECK (phone IS NULL OR BTRIM(phone) <> ''),
    CONSTRAINT ck_contact_required
        CHECK (
            NULLIF(BTRIM(email), '') IS NOT NULL
            OR NULLIF(BTRIM(phone), '') IS NOT NULL
        )
);

-- Email is treated as case-insensitive per this
-- illustrative rule; verify actual policy.
CREATE UNIQUE INDEX uq_customer_email_normalized
    ON validation_lab.customer (LOWER(BTRIM(email)))
    WHERE email IS NOT NULL;

CREATE TABLE validation_lab.product (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL
        CHECK (BTRIM(product_name) <> ''),
    list_price NUMERIC(14, 2) NOT NULL
        CHECK (list_price >= 0)
);

CREATE TABLE validation_lab.sales_order (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES validation_lab.customer(customer_id),
    status TEXT NOT NULL DEFAULT 'DRAFT',
    created_at TIMESTAMPTZ NOT NULL,
    confirmed_at TIMESTAMPTZ,
    CONSTRAINT ck_order_status
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    CONSTRAINT ck_confirm_time
        CHECK (confirmed_at IS NULL OR confirmed_at >= created_at),
    CONSTRAINT ck_confirm_requires_time
        CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL)
);

CREATE TABLE validation_lab.order_line (
    line_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES validation_lab.sales_order(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL
        REFERENCES validation_lab.product(product_id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    discount_amount NUMERIC(18, 2) NOT NULL,
    currency_code CHAR(3) NOT NULL DEFAULT 'VND',
    net_amount NUMERIC(18, 2) GENERATED ALWAYS AS
        (quantity * unit_price - discount_amount) STORED,
    CONSTRAINT uq_order_line_no UNIQUE (order_id, line_no),
    CONSTRAINT ck_line_quantity CHECK (quantity BETWEEN 1 AND 1000),
    CONSTRAINT ck_line_unit_price CHECK (unit_price >= 0),
    CONSTRAINT ck_line_discount
        CHECK (
            discount_amount >= 0
            AND discount_amount <= quantity * unit_price
        ),
    CONSTRAINT ck_line_currency CHECK (currency_code = 'VND')
);
~~~~

**Guarantees inferred from this DDL:**

- `customer_id`, `product_id`, `order_id`, and `line_id` are unique non-NULL keys.
- `(order_id, line_no)` is unique per order, yet **`line_no` may repeat across different orders**.
- Every order line points to one order and one product **existing in the same database**.
- `quantity`, `unit_price`, and `discount_amount` obey stated bounds, and since input columns are `NOT NULL`, `UNKNOWN` cannot slip past `CHECK` via `NULL`.
- `net_amount` is computed via a `GENERATED` column, preventing mismatched stored monetary columns on the same row.
- `email` **may be NULL** if `phone` is supplied, while a whitespace-only string is rejected.
- Status name is one of the three declared values; if `status = CONFIRMED`, `confirmed_at` is non-NULL and not earlier than `created_at`.

**What the DDL does NOT guarantee:**

- That a `CONFIRMED` order **has at least one line**.
- That an order transitions strictly along **`DRAFT → CONFIRMED → CANCELLED`**, because `CHECK` sees only **the new status**, not transition history.
- That nobody edits lines of a `CONFIRMED` order if policy requires locked prices.
- Whether a deactivated customer is still allowed to place orders.
- Whether an email actually belongs to the registrant; basic syntax checks do not verify ownership.
- Whether ordered quantities fit within another warehouse's allocation capacity.

These require **additional rules and validation checks** — never declare "all invariants protected" right after `CREATE TABLE`.

### 5.3. Valid Test Data

~~~~sql
INSERT INTO validation_lab.customer
    (customer_id, email, phone)
VALUES
    (1, 'an@example.org', NULL),
    (2, NULL, '0900000002'),
    (3, 'binh@example.org', '0900000003');

INSERT INTO validation_lab.product
    (product_id, sku, product_name, list_price)
VALUES
    (101, 'NOTE-A5', 'A5 Notebook', 100000.00),
    (102, 'PEN-BLUE', 'Blue Ink Pen', 20000.00);

INSERT INTO validation_lab.sales_order
    (order_id, customer_id, status, created_at, confirmed_at)
VALUES
    (1001, 1, 'DRAFT',
     TIMESTAMPTZ '2026-10-01 08:00:00+07', NULL),
    (1002, 2, 'DRAFT',
     TIMESTAMPTZ '2026-10-01 09:00:00+07', NULL);

INSERT INTO validation_lab.order_line
    (line_id, order_id, line_no, product_id, quantity,
     unit_price, discount_amount)
VALUES
    (201, 1001, 1, 101, 2, 100000.00, 10000.00),
    (202, 1001, 2, 102, 1, 20000.00, 0.00),
    (203, 1002, 1, 101, 1, 100000.00, 100000.00);

UPDATE validation_lab.sales_order
SET status = 'CONFIRMED',
    confirmed_at = TIMESTAMPTZ '2026-10-01 08:05:00+07'
WHERE order_id = 1001;
~~~~

Line monetary results:

| line_id | order_id | quantity | unit_price | discount_amount | net_amount |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 201 | 1001 | 2 | 100000.00 | 10000.00 | 190000.00 |
| 202 | 1001 | 1 | 20000.00 | 0.00 | 20000.00 |
| 203 | 1002 | 1 | 100000.00 | 100000.00 | 0.00 |

**Order 1001 totals 210000.00 VND**, while order 1002 is `DRAFT` with a 100%-discounted line. Line 203 having net `0` is **valid under the assumed discount policy**. If the business forbids 100% discounts on certain products, that is a separate invariant not yet included here.

### 5.4. Verifying Valid Data After Persistence

~~~~sql
SELECT
    o.order_id,
    o.status,
    COUNT(l.line_id) AS line_count,
    COALESCE(SUM(l.net_amount), 0) AS total_vnd
FROM validation_lab.sales_order AS o
LEFT JOIN validation_lab.order_line AS l
    ON l.order_id = o.order_id
GROUP BY o.order_id, o.status
ORDER BY o.order_id;
-- 1001: CONFIRMED, 2 lines, 210000.00
-- 1002: DRAFT,     1 line,       0.00
~~~~

This is a **positive test**: data obeying invariants must be accepted and monetary totals must compute accurately. Running only negative tests without positive tests at **valid boundaries** can make an overly strict `CHECK` appear to "work" simply because it rejects everything.

## 6. Negative Testing: Expecting the Database to Reject Invalid Data

### 6.1. Why Verify the Error Code?

A negative test checking only "did `INSERT` error?" can mislead testers: a statement might fail **due to a misspelled column name or lost connection** rather than the intended invariant.

Common PostgreSQL **SQLSTATE** codes:

| SQLSTATE | Common meaning |
| --- | --- |
| **23502** | NOT NULL violation |
| **23503** | FOREIGN KEY violation |
| **23505** | UNIQUE violation |
| **23514** | CHECK violation |

To verify a specific constraint, check the **constraint name** when catching the error. Negative tests should assert **a specific meaningful failure**, never accept arbitrary exceptions.

### 6.2. Failure-Testing Helper in a Learning Environment

The function below accepts a **trusted SQL statement supplied by the test author**, runs it inside a PL/pgSQL exception block (subtransaction), and confirms the observed `SQLSTATE` matches expectations. If the statement **unexpectedly succeeds**, the function intentionally raises an exception. If it fails for another reason, the function also raises an exception.

~~~~sql
CREATE OR REPLACE FUNCTION validation_lab.expect_failure(
    p_statement TEXT,
    p_expected_sqlstate TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_actual_sqlstate TEXT;
BEGIN
    BEGIN
        EXECUTE p_statement;
        RAISE EXCEPTION 'Expected statement to fail but it succeeded';
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            v_actual_sqlstate = RETURNED_SQLSTATE;

        IF v_actual_sqlstate IS DISTINCT FROM p_expected_sqlstate THEN
            RAISE EXCEPTION
                'Expected SQLSTATE %, observed %',
                p_expected_sqlstate, v_actual_sqlstate;
        END IF;
    END;

    RETURN 'PASS';
END;
$$;
~~~~

**Safety and scope note:** This helper uses dynamic **`EXECUTE`**, so use it strictly in test databases with fixed SQL controlled by the test author. **Never** pass SQL from HTTP/APIs or untrusted users. It checks **`SQLSTATE`** without verifying constraint name; strict test suites should also assert constraint names or inspect persisted data afterward.

When an `INSERT` fails inside the exception block, its changes are rolled back inside the subtransaction without dirtying fixtures. If it **unexpectedly succeeds**, the exception raised by the helper also rolls back the block's changes and fails the test with a non-matching code.

### 6.3. Invalid Cases by Constraint Type

**Quantity = 0 — CHECK must reject (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.order_line
        (line_id, order_id, line_no, product_id, quantity,
         unit_price, discount_amount)
     VALUES (901, 1001, 9, 101, 0, 100000, 0)',
    '23514'
);
~~~~

**Quantity = 1001 — exceeds upper bound (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.order_line
        (line_id, order_id, line_no, product_id, quantity,
         unit_price, discount_amount)
     VALUES (902, 1001, 9, 101, 1001, 100000, 0)',
    '23514'
);
~~~~

**Quantity NULL — NOT NULL must reject (23502):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.order_line
        (line_id, order_id, line_no, product_id, quantity,
         unit_price, discount_amount)
     VALUES (903, 1001, 9, 101, NULL, 100000, 0)',
    '23502'
);
~~~~

**Negative discount — CHECK (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.order_line
        (line_id, order_id, line_no, product_id, quantity,
         unit_price, discount_amount)
     VALUES (904, 1001, 9, 101, 2, 100000, -0.01)',
    '23514'
);
~~~~

**Discount exceeding gross by 0.01 — CHECK (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.order_line
        (line_id, order_id, line_no, product_id, quantity,
         unit_price, discount_amount)
     VALUES (905, 1001, 9, 101, 2, 100000, 200000.01)',
    '23514'
);
~~~~

**Non-existent `order_id` — FOREIGN KEY (23503):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.order_line
        (line_id, order_id, line_no, product_id, quantity,
         unit_price, discount_amount)
     VALUES (906, 9999, 1, 101, 1, 100000, 0)',
    '23503'
);
~~~~

**Duplicate `line_no` within the same order — UNIQUE (23505):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.order_line
        (line_id, order_id, line_no, product_id, quantity,
         unit_price, discount_amount)
     VALUES (907, 1001, 1, 101, 1, 100000, 0)',
    '23505'
);
~~~~

**Customer with no contact method — CHECK (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.customer
        (customer_id, email, phone)
     VALUES (901, NULL, NULL)',
    '23514'
);
~~~~

**Whitespace-only email — CHECK (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.customer
        (customer_id, email, phone)
     VALUES (902, ''   '', ''0900000000'')',
    '23514'
);
~~~~

**Case-insensitive duplicate email — UNIQUE index (23505):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.customer
        (customer_id, email, phone)
     VALUES (903, ''AN@example.org'', NULL)',
    '23505'
);
~~~~

**Out-of-domain status — CHECK (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'UPDATE validation_lab.sales_order
     SET status = ''PAID''
     WHERE order_id = 1002',
    '23514'
);
~~~~

**`CONFIRMED` status missing timestamp — CHECK (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'UPDATE validation_lab.sales_order
     SET status = ''CONFIRMED'', confirmed_at = NULL
     WHERE order_id = 1002',
    '23514'
);
~~~~

**`CONFIRMED` timestamp earlier than order creation — CHECK (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'UPDATE validation_lab.sales_order
     SET status = ''CONFIRMED'',
         confirmed_at = TIMESTAMPTZ ''2026-09-30 10:00:00+07''
     WHERE order_id = 1002',
    '23514'
);
~~~~

All of these negative tests must return **`PASS`**. If a test fails because of a wrong table/column name or an unrelated constraint, never mark the check passed just because an exception occurred.

### 6.4. Positive Test at Valid Boundaries

Test upper quantity boundary and maximum discount, then `ROLLBACK` to preserve fixtures:

~~~~sql
BEGIN;

INSERT INTO validation_lab.order_line
    (line_id, order_id, line_no, product_id, quantity,
     unit_price, discount_amount)
VALUES
    (950, 1002, 2, 101, 1000, 100000.00, 100000000.00);

SELECT line_id, quantity, discount_amount, net_amount
FROM validation_lab.order_line
WHERE line_id = 950;
-- quantity=1000, discount_amount=100000000.00, net_amount=0.00

ROLLBACK;
~~~~

An overly tight check—such as `quantity < 1000` or `discount_amount < quantity × unit_price`—will **be caught by positive boundary tests**. Do not measure only rejection power; prove valid boundary values are accepted too.

### 6.5. Test Datasets Must Not Self-Contradict

If a test aims to check an orphan FK while also passing `quantity = 0`, the `INSERT` may fail on `CHECK` first, or evaluation order may be unguaranteed. In that case the test **proves nothing about the FK**.

Rules for crafting negative test data:

1. Keep **every other condition valid**.
2. Violate **only the one target rule**.
3. Verify the **matching SQLSTATE/constraint**.
4. When multiple invariants matter, write **dedicated tests per target** plus integration suites.
5. Inspect data afterward to confirm no unintended side effects.

## 7. Invariant Validation Matrix: From Tables to Behavior

| Invariant | Valid case | Boundary/invalid case | Safeguard |
| --- | --- | --- | --- |
| `quantity` `[1,1000]` | 1, 1000 | 0, 1001, NULL | NOT NULL + CHECK |
| `unit_price >= 0` | 0.00 | -0.01, NULL | NOT NULL + CHECK |
| Discount within gross | 0, equal to gross | negative, gross + 0.01 | CHECK on NOT NULL columns |
| One contact method | email or phone | both NULL, empty, or whitespace | CHECK + validation |
| Normalized unique email | distinct emails | different case for same email | Normalized UNIQUE index |
| Line has order and product | existing keys | missing keys, NULL | NOT NULL + FK |
| `line_no` unique per order | line 1 in two orders | two line 1s in same order | `UNIQUE(order_id,line_no)` |
| Status in allowed set | DRAFT, CONFIRMED, CANCELLED | PAID, empty string, NULL | NOT NULL + CHECK |
| `confirmed_at >= created_at` | equal or later | earlier than `created_at` | CHECK |
| CONFIRMED must have ≥1 line | order with 1+ lines | order with 0 lines | Transaction rule + multi-row guard |
| Forbid editing finalized lines | edit DRAFT order | edit line of CONFIRMED | Domain transition + DB write control/trigger if needed |
| No overselling stock | `available >= request` | `available < request`, concurrent requests | Atomic transaction / conditional update |
| Non-overlapping history | adjacent intervals | overlapping intervals on same business key | Exclusion/appropriate constraint + temporal tests |

**The matrix does not replace actual tests.** It is the map from **business definition → counterexample → mechanism and evidence**. Each row must be implemented as a concrete test or check with a clear name, fixture setup, and observable expectation.

## 8. Invalid States: Check Transitions, Not Just Current Values

### 8.1. Allowed State Set Differs from Allowed State Transitions

In our example, `order.status` belongs to three values:

~~~~text
DRAFT
CONFIRMED
CANCELLED
~~~~

Yet that **does not prove** every transition among those three values is valid. An illustrative business policy:

~~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> CONFIRMED: At least one valid line
    DRAFT --> CANCELLED: Cancel draft order
    CONFIRMED --> CANCELLED: Approved cancellation flow
    CONFIRMED --> CONFIRMED: Idempotent retry, no data change
    CANCELLED --> [*]
~~~~

Under this policy:

- **`DRAFT → CONFIRMED`:** valid when confirmation preconditions pass.
- **`DRAFT → CANCELLED`:** valid.
- **`CONFIRMED → CANCELLED`:** only via an approved cancellation workflow.
- **`CONFIRMED → DRAFT`:** invalid.
- **`CANCELLED → CONFIRMED`:** invalid once terminally cancelled.
- **`CANCELLED → DRAFT`:** invalid.

`CHECK(status IN (...))` sees only **the final value** and knows nothing of the prior transition path. An `UPDATE` from `CONFIRMED` back to `DRAFT` still satisfies `CHECK` if `confirmed_at` and other columns are also adjusted to fit.

### 8.2. Counterexample: CHECK Still Allows an Illegal Transition

Test inside a transaction and `ROLLBACK`:

~~~~sql
BEGIN;

-- Order 1001 is CONFIRMED from the fixture.
UPDATE validation_lab.sales_order
SET status = 'DRAFT',
    confirmed_at = NULL
WHERE order_id = 1001;

SELECT order_id, status, confirmed_at
FROM validation_lab.sales_order
WHERE order_id = 1001;
-- DRAFT, NULL: accepted by DDL yet violates state transition policy.

ROLLBACK;
~~~~

This outcome does not say PostgreSQL is buggy. It proves **the current constraint model does not fully encode transition invariants**. The design needs controlled write paths (domain service/transaction), version checks, or triggers/constraints if every DB writer must be blocked.

### 8.3. Counterexample: A CONFIRMED Order Without Lines

We can create a line-less order and mark it `CONFIRMED`:

~~~~sql
BEGIN;

INSERT INTO validation_lab.sales_order
    (order_id, customer_id, status, created_at, confirmed_at)
VALUES
    (1099, 1, 'DRAFT',
     TIMESTAMPTZ '2026-10-02 10:00:00+07', NULL);

UPDATE validation_lab.sales_order
SET status = 'CONFIRMED',
    confirmed_at = TIMESTAMPTZ '2026-10-02 10:01:00+07'
WHERE order_id = 1099;

SELECT
    o.order_id,
    o.status,
    COUNT(l.line_id) AS line_count
FROM validation_lab.sales_order AS o
LEFT JOIN validation_lab.order_line AS l
    ON l.order_id = o.order_id
WHERE o.order_id = 1099
GROUP BY o.order_id, o.status;
-- CONFIRMED, line_count = 0: violates business invariant.

ROLLBACK;
~~~~

**Why didn't the FK block it?** The FK on `order_line.order_id` answers "if a line exists, does the parent order exist?" It **does not** answer "does the parent order have at least one line?" Guarding the inverse cardinality requires transaction boundaries or multi-row rules.

### 8.4. Validating Confirmation Through API/Transaction

A transition path may execute:

~~~~text
ConfirmOrder(orderId):
  1. Authenticate permissions and orderId.
  2. Lock/coordinate access to the same order.
  3. Require current status is DRAFT.
  4. Verify at least one valid line exists.
  5. Check other preconditions (locked prices, currency, business rules).
  6. Write CONFIRMED and confirmed_at inside the transaction.
  7. Commit or roll back everything.
~~~~

SQL illustrating **part** of the condition:

~~~~sql
-- Run inside a transaction coordinated with all order_line writers.
UPDATE validation_lab.sales_order AS o
SET status = 'CONFIRMED',
    confirmed_at = CURRENT_TIMESTAMP
WHERE o.order_id = 1002
  AND o.status = 'DRAFT'
  AND EXISTS (
      SELECT 1
      FROM validation_lab.order_line AS l
      WHERE l.order_id = o.order_id
  )
RETURNING o.order_id, o.status;
~~~~

**This alone does not prevent every race condition.** In multi-transaction systems, another flow could delete the last line or alter prices right after the check. For lasting protection, all **line add/edit/delete paths and status transitions** must coordinate through the same locking and state protocol, or use DB mechanisms like parent-checking triggers, row locks, or constraint triggers designed for concurrency. An `EXISTS` inside one statement **does not permanently lock line existence**.

Before actually running the `UPDATE` above, wrap fixture tests in a transaction with `ROLLBACK` or run against a resettable test DB so order 1002's state isn't mutated for subsequent tests.

### 8.5. State Cases to Test

| Prior status | Action | Condition | Expected outcome |
| --- | --- | --- | --- |
| DRAFT | Confirm | No lines | Reject |
| DRAFT | Confirm | Valid lines present | Allow |
| DRAFT | Cancel | Authorized | Allow |
| CONFIRMED | Repeat Confirm | Same idempotency key | No duplicate confirmation |
| CONFIRMED | Revert to DRAFT | Any | Reject |
| CONFIRMED | Edit locked price | No adjustment workflow | Reject |
| CONFIRMED | Cancel | Per cancel policy | Conditional accept |
| CANCELLED | Confirm | Order restoration disallowed | Reject |
| No order | Confirm | Non-existent ID | Never silently create order |
| DRAFT | Concurrent Confirm from two requests | Same order | At most one transition effect |

## 9. Temporal Invariants and Uniqueness Across Versions

### 9.1. SCD2 Example: One Customer Across Multiple Segments Over Time

Suppose reporting needs the customer's segment **at sale time**. A customer can transition from `Retail` to `Business`; the model retains versions using **`[valid_from, valid_to)`** intervals.

~~~~sql
CREATE TABLE validation_lab.customer_segment_history (
    segment_key BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES validation_lab.customer(customer_id),
    segment_code TEXT NOT NULL
        CHECK (segment_code IN ('RETAIL', 'BUSINESS')),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    CONSTRAINT ck_segment_valid_interval
        CHECK (valid_to IS NULL OR valid_to > valid_from),
    CONSTRAINT uq_segment_start UNIQUE (customer_id, valid_from)
);

INSERT INTO validation_lab.customer_segment_history
    (segment_key, customer_id, segment_code, valid_from, valid_to)
VALUES
    (501, 1, 'RETAIL',
     TIMESTAMPTZ '2026-01-01 00:00:00+07',
     TIMESTAMPTZ '2026-10-02 00:00:00+07'),
    (502, 1, 'BUSINESS',
     TIMESTAMPTZ '2026-10-02 00:00:00+07',
     NULL);
~~~~

The two intervals are **adjacent** without overlapping. Record 501 is effective until **just before 00:00 on Oct 02**, while record 502 begins **at exactly 00:00 on Oct 02**.

### 9.2. Testing Right on the Temporal Boundary

~~~~sql
-- Immediately before the segment switch:
SELECT segment_key, segment_code
FROM validation_lab.customer_segment_history
WHERE customer_id = 1
  AND valid_from <= TIMESTAMPTZ '2026-10-01 23:59:59+07'
  AND (
      valid_to > TIMESTAMPTZ '2026-10-01 23:59:59+07'
      OR valid_to IS NULL
  );
-- Expected: 501, RETAIL.

-- Right at the exact segment switch timestamp:
SELECT segment_key, segment_code
FROM validation_lab.customer_segment_history
WHERE customer_id = 1
  AND valid_from <= TIMESTAMPTZ '2026-10-02 00:00:00+07'
  AND (
      valid_to > TIMESTAMPTZ '2026-10-02 00:00:00+07'
      OR valid_to IS NULL
  );
-- Expected: 502, BUSINESS, exactly one row.
~~~~

Using **`valid_to >= event_time`** instead of **`>`** can **match both versions** at the transition boundary and duplicate a fact row on JOIN. This is a **temporal-boundary** bug that midday tests will never spot.

### 9.3. UNIQUE(customer_id, valid_from) Does Not Prevent Overlaps

Two versions can have **different `valid_from` values** while still overlapping:

~~~~text
R1 = [2026-01-01, 2026-10-05)
R2 = [2026-10-02, 2026-11-01)
~~~~

`UNIQUE(customer_id, valid_from)` accepts both rows because their start timestamps differ. Check with:

~~~~sql
SELECT
    a.customer_id,
    a.segment_key AS version_a,
    b.segment_key AS version_b
FROM validation_lab.customer_segment_history AS a
JOIN validation_lab.customer_segment_history AS b
    ON a.customer_id = b.customer_id
   AND a.segment_key < b.segment_key
   AND a.valid_from <
       COALESCE(b.valid_to, 'infinity'::TIMESTAMPTZ)
   AND b.valid_from <
       COALESCE(a.valid_to, 'infinity'::TIMESTAMPTZ);
-- Expected: 0 overlapping pairs.
~~~~

**The current dataset has no overlap.** However, if two transactions concurrently insert differing intervals guarded only by a pre-insert `SELECT`, both can **read "no overlap" and commit** under weaker isolation levels unless write races are prevented.

### 9.4. Enforcing Interval Constraints at the Database

PostgreSQL supports **exclusion constraints** to reject overlaps using appropriate operators. **Supplementary** example for the history table above:

~~~~sql
-- Requires privilege/ability to enable the extension in the test DB.
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE validation_lab.customer_segment_history
ADD CONSTRAINT ex_customer_segment_no_overlap
EXCLUDE USING gist (
    customer_id WITH =,
    tstzrange(valid_from, valid_to, '[)') WITH &&
);
~~~~

Meaning:

- Two rows with the **same `customer_id`** cannot have **intersecting** time ranges.
- The range is **start-inclusive, end-exclusive**.
- `valid_to = NULL` in the range constructor denotes an **unbounded upper end**.
- On an overlapping insert, PostgreSQL rejects with an **exclusion violation** (`SQLSTATE 23P01`).

This is a PostgreSQL-specific option depending on type/operator support and extension permissions. In other engines, triggers, serialization, or specialized checks may be needed to enforce no-overlap. **A post-load SELECT audit only detects bugs; an exclusion constraint blocks them at write time.**

### 9.5. No Overlap Does Not Mean No Gaps

Two intervals:

~~~~text
[2026-01-01, 2026-10-01)
[2026-10-03, unbounded)
~~~~

do not overlap, yet leave **a two-day gap**. If the business requires exactly one segment at every moment, validate **coverage/gaps** in addition to no-overlap. If a segment can be undetermined during a period, gaps may be **valid**; decide upfront.

Other temporal rules to test:

- `valid_to = valid_from` (empty interval) — rejected by `CHECK`.
- `valid_to < valid_from` — rejected by `CHECK`.
- Two versions sharing a boundary timestamp — allowed under `[from, to)`.
- Two versions starting at the same timestamp — rejected by `UNIQUE`.
- Two current rows with `valid_to NULL` — rejected by exclusion if enabled above.
- Late-arriving events must join the **version effective at `event_time`**, not blindly the current version.

### 9.6. Validating Point-in-Time Joins in Analytics

Suppose a sale occurs at 23:00 on Oct 01, while the warehouse receives the event at 03:00 on Oct 02. Under "segment at sale time":

- **`event_time`:** Oct 01 ⇒ `RETAIL`.
- **`ingestion_time`:** Oct 02 ⇒ must not be used as segment date when the contract specifies sale time.

The checkpoint is not just non-overlapping ranges, but also **that ingestion picks the right lookup timestamp**. A database with a valid FK to `segment_key` can still attach **the wrong version** if ETL uses ingestion time instead of event time.

## 10. Concurrent Data: An Invariant Valid in One Thread May Break Across Two

### 10.1. Inventory Reservation Example

A warehouse has 5 units on hand, 0 reserved. Two requests simultaneously try to reserve 4 units:

~~~~text
T1 reads available = 5 → thinks 4 can be reserved.
T2 reads available = 5 → also thinks 4 can be reserved.
T1 adds reserved_qty += 4.
T2 adds reserved_qty += 4.
Wrong outcome can become reserved_qty = 8 if uncoordinated.
~~~~

Checking **availability in the application before writing** without an atomic/transactional re-check can oversell inventory.

### 10.2. Constraints and Conditional Updates at the Owner

~~~~sql
CREATE TABLE validation_lab.stock (
    product_id BIGINT PRIMARY KEY
        REFERENCES validation_lab.product(product_id),
    on_hand_qty INTEGER NOT NULL CHECK (on_hand_qty >= 0),
    reserved_qty INTEGER NOT NULL CHECK (reserved_qty >= 0),
    CONSTRAINT ck_stock_not_oversold
        CHECK (reserved_qty <= on_hand_qty)
);

INSERT INTO validation_lab.stock
    (product_id, on_hand_qty, reserved_qty)
VALUES (101, 5, 0);
~~~~

Operation for **one** 4-unit reservation request:

~~~~sql
BEGIN;

UPDATE validation_lab.stock
SET reserved_qty = reserved_qty + 4
WHERE product_id = 101
  AND on_hand_qty - reserved_qty >= 4
RETURNING product_id, on_hand_qty, reserved_qty;

-- Success if 1 row returns, meaning 4 more were reserved.
-- 0 rows: insufficient stock or product_id does not exist.

ROLLBACK; -- Keep fixture intact for repeated runs.
~~~~

When updating the same row in PostgreSQL, transactions coordinate via row locks and re-evaluate conditions per isolation level. A **conditional `UPDATE` against current values** combined with a DB `CHECK` beats disconnected "blind SELECT then UPDATE."

**Warning:** One succeeding `UPDATE` is not a full reservation workflow; you also need reservation IDs, idempotency keys, retry handling, release/expiry, and separation between reserved and shipped stock. If inventory lives in another context/database, a `CHECK` in Sales cannot protect Inventory stock.

### 10.3. Two-Session Concurrency Test

Goal: starting from `stock (on_hand=5, reserved=0)`, **two +4 reservation requests** arrive together:

| Request | Action | Expected outcome |
| --- | --- | --- |
| T1 | Conditional `UPDATE +4` | One request succeeds |
| T2 | Conditional `UPDATE +4` | The other fails when condition is evaluated against updated state |
| Post-COMMIT check | Read `stock` | `reserved_qty <= 5`; never two successful +4 reservations |

**Which specific request wins depends on scheduling.** The invariant is **never commit `reserved = 8`**. A sequential test running T1 then T2 proves nothing about race behavior.

Also test:

- Two requests with the **same idempotency key** retried.
- Two requests with different keys yet for the same order sent twice.
- A release concurrent with a reserve.
- Decreasing `on_hand_qty` concurrent with a reserve.
- Transaction timeout or rollback after acquiring locks.

These require integration tests with two real DB connections and concurrency orchestration, not a single `SELECT`.

### 10.4. Write Skew and Multi-Row Invariants

Rules like "always keep at least one on-call doctor" or "every `CONFIRMED` order has at least one line" span **sets of multiple rows** and can break if two transactions decide based on an older snapshot.

For example, a `CONFIRMED` order has two lines. T1 sees line B remains and deletes A; T2 sees line A remains and deletes B. Without order-level write coordination, the order ends up with zero lines.

To guard against this:

- Route line edits and state transitions through **one aggregate/transaction protocol** with proper locking.
- Or use **constraint triggers and serialization/locking** designed for correctness under concurrency.
- Test with **two real connections**, not isolated single requests.
- Track conflicts/retries properly rather than swallowing serialization errors and reporting success.

**Never claim simply enabling `SERIALIZABLE` solves everything:** the application must handle **serialization failures and safe transaction retries**, while external exceptions and emitted side effects must also stay coordinated.

## 11. Tenant-Scoped Constraints and Composite Relationships

### 11.1. Right-Typed FK Does Not Mean Right-Scoped FK

An employee in tenant A must reference a department also in tenant A. The design below **risks** cross-tenant leaks if using global `department_id`:

~~~~text
EMPLOYEE(tenant_id, employee_id, department_id)
DEPARTMENT(tenant_id, department_id)
~~~~

An FK on `department_id` alone (with suitable index/`UNIQUE`) proves **the department exists somewhere**, not that it belongs to the same tenant.

### 11.2. Using Composite FKs to Enforce Context Match

~~~~sql
CREATE TABLE validation_lab.department (
    tenant_id BIGINT NOT NULL,
    department_id BIGINT NOT NULL,
    department_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, department_id)
);

CREATE TABLE validation_lab.employee (
    tenant_id BIGINT NOT NULL,
    employee_id BIGINT NOT NULL,
    department_id BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, employee_id),
    FOREIGN KEY (tenant_id, department_id)
        REFERENCES validation_lab.department(tenant_id, department_id)
);

INSERT INTO validation_lab.department
    (tenant_id, department_id, department_name)
VALUES
    (10, 7, 'Accounting A'),
    (20, 8, 'Accounting B');

INSERT INTO validation_lab.employee
    (tenant_id, employee_id, department_id)
VALUES (10, 100, 7);
~~~~

Negative test:

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.employee
        (tenant_id, employee_id, department_id)
     VALUES (10, 101, 8)',
    '23503'
);
~~~~

Department `(tenant 20, department 8)` **exists**, yet does not belong to tenant 10; the composite FK rejects it. This tests a **scoped relationship invariant**, not just key existence.

### 11.3. Checking Partial-NULL Components of Composite Keys

If `department_id` or `tenant_id` is nullable, default composite FKs may skip checks whenever one component is NULL. In the example, both are `NOT NULL` to enforce full references.

If department is **optional**:

- Decide when an employee may have no department.
- When assigned, **both `tenant_id` and `department_id`** must be present.
- Distinguish "unassigned" from "assigned to another tenant's department."

A syntactically valid FK does not replace defining business keys and linkage scope. **Matching names or numbers across tenants are not the same business object.**

## 12. Validating in Java and the Database: Two Complementary Layers

### 12.1. Invariants in Value Objects / Domain Models

A Java object can reject bad values **at construction time**, before calling the DB. Java 17+ example:

~~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record OrderLineInput(
    int quantity,
    BigDecimal unitPrice,
    BigDecimal discountAmount
) {
    public OrderLineInput {
        Objects.requireNonNull(unitPrice, "unitPrice");
        Objects.requireNonNull(discountAmount, "discountAmount");

        if (quantity < 1 || quantity > 1000) {
            throw new IllegalArgumentException(
                "quantity must be between 1 and 1000"
            );
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("negative unitPrice");
        }

        BigDecimal gross = unitPrice.multiply(
            BigDecimal.valueOf(quantity)
        );
        if (discountAmount.signum() < 0
                || discountAmount.compareTo(gross) > 0) {
            throw new IllegalArgumentException("invalid discountAmount");
        }
    }

    public BigDecimal netAmount() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity))
            .subtract(discountAmount);
    }
}
~~~~

This object guards rules **computable from its own fields**, such as `quantity`, `unitPrice`, and `discountAmount`. Java validates at construction and produces clearer errors than raw DB exceptions.

However:

- Data from **SQL scripts, ETL, admin tools, or another app** can bypass Java constructors.
- A valid Java object may still hold an **FK pointing to a non-existent row**.
- An in-memory object cannot see another order concurrently reserving stock in the database.
- `BigDecimal` does not automatically enforce `NUMERIC(14,2)` precision/scale; if the contract mandates two decimal places, enforce consistent checks/rounding at boundaries and in the DB.
- An object valid at construction time may still violate the system's **current state** by `COMMIT`.

Thus, **domain validation and SQL constraints do not replace each other**. Domain code catches errors early, the DB protects state across all authorized write paths, and transaction boundaries protect concurrency-sensitive invariants.

### 12.2. Boundary Tests in Java

JUnit 5 example:

~~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;

class OrderLineInputTest {

    @Test
    void acceptsLowerAndUpperQuantityBoundaries() {
        assertDoesNotThrow(() -> new OrderLineInput(
            1, new BigDecimal("0.00"), new BigDecimal("0.00")
        ));
        assertDoesNotThrow(() -> new OrderLineInput(
            1000, new BigDecimal("100.00"),
            new BigDecimal("100000.00")
        ));
    }

    @Test
    void rejectsQuantityImmediatelyOutsideBoundaries() {
        assertThrows(IllegalArgumentException.class, () ->
            new OrderLineInput(0, BigDecimal.ONE, BigDecimal.ZERO));
        assertThrows(IllegalArgumentException.class, () ->
            new OrderLineInput(1001, BigDecimal.ONE, BigDecimal.ZERO));
    }

    @Test
    void rejectsNegativeAndExcessiveDiscount() {
        assertThrows(IllegalArgumentException.class, () ->
            new OrderLineInput(2, new BigDecimal("100.00"),
                new BigDecimal("-0.01")));
        assertThrows(IllegalArgumentException.class, () ->
            new OrderLineInput(2, new BigDecimal("100.00"),
                new BigDecimal("200.01")));
    }

    @Test
    void calculatesExpectedNetAmount() {
        var line = new OrderLineInput(
            2, new BigDecimal("100000.00"),
            new BigDecimal("10000.00")
        );
        assertEquals(0, new BigDecimal("190000.00")
            .compareTo(line.netAmount()));
    }
}
~~~~

**Why `compareTo` instead of `equals` on `BigDecimal`?** `BigDecimal.equals` compares scale too: `1.0` and `1.00` are not equal despite equal numeric value. When comparing **monetary value**, `compareTo` is usually appropriate; if scale itself is part of the invariant, test **scale separately**.

### 12.3. Domain and DB Tests Must Reflect the Same Contract

A common trap:

~~~~text
Java: quantity 1 to 999
Database: quantity 1 to 1000
Business: quantity 1 to 1000
~~~~

The DB accepts `quantity = 1000` yet the Java API rejects it: users hit errors on business-valid input. That is **drift between validation layers**, not a benefit of "validating twice."

Conversely, Java accepting `1001` while the DB rejects it surfaces errors late and may roll back an entire transaction.

Maintain a shared **set of contract examples** run against both domain and DB:

| Data | Java | DB |
| --- | --- | --- |
| `quantity = 1` | Accept | Accept |
| `quantity = 1000` | Accept | Accept |
| `quantity = 0` | Reject | Reject |
| `quantity = 1001` | Reject | Reject |
| `discount` equals gross | Accept | Accept |
| `discount` exceeds gross | Reject | Reject |

Java and SQL need not mirror line-for-line code; they must match on **invariant semantics** per contract. Database-level rules like FKs and concurrency need dedicated DB/integration tests rather than forcing them into record constructors.

### 12.4. PATCH: Omitted Field vs. Explicit Deletion Request

For a contact-update endpoint, payloads carry distinct meanings:

~~~~json
{}
~~~~

Normally means **no change**. Whereas:

~~~~json
{"email": null}
~~~~

can mean **clear email** under PATCH semantics. If `phone` is also `NULL`, clearing email must be rejected by **`ck_contact_required`** or caught early by the application. And:

~~~~json
{"email": ""}
~~~~

should not be silently treated like JSON `null` without an explicit rule; the app can reject empty strings at the boundary. **A deserializer that maps missing fields to `null`** without preserving user intent can break invariants or wipe data unintentionally.

## 13. Generative, Property-Based, and Metamorphic Testing

### 13.1. Why Fixed Examples Are Not Enough

A table spans many domains: quantity, price, discount, status, customer, product, timestamps, tenant. Hand-written examples prove core rules, yet struggle to cover **boundary combinations**.

**Property-based testing** generates controlled inputs and verifies **properties that must always hold**. It complements hand-crafted examples; it never replaces clearly stated invariants.

### 13.2. Mathematical Properties of a Sales Line

For every valid line with quantity $q$, unit price $p$, and discount $d$:

\[
1 \le q \le 1000,\qquad p\ge0,\qquad 0\le d\le q\times p
\]

we must have:

\[
\text{net}=q\times p-d
\]

and:

\[
0\le\text{net}\le q\times p.
\]

A generator can:

1. Generate $q$ from 1 to 1000.
2. Generate $p$ as a non-negative decimal bounded by schema precision/scale.
3. Compute $\text{gross} = q \times p$.
4. Generate $d$ from 0 to $\text{gross}$ at the same unit/scale.
5. Verify the Java object accepts it and $\text{net} = \text{gross} - d$.
6. Insert into a test DB and verify `net_amount`, FKs, and reconciliation.

**Note:** Generators must use exact decimal types, consistent currencies, and numbers within `NUMERIC` limits. Generating $d$ as a `double` with arbitrary rounding creates generator bugs rather than design bugs.

### 13.3. Generating Negative Cases by Mutating One Invariant

Instead of purely blind randomness, start from a valid line and **mutate exactly one condition**:

~~~~text
VALID:
  q = 2, p = 100.00, d = 50.00

MUTATION A:
  q = 0
  → expect rejection on quantity.

MUTATION B:
  d = -0.01
  → expect rejection on negative discount.

MUTATION C:
  d = 200.01
  → expect rejection on discount exceeding gross.

MUTATION D:
  order_id = non-existent ID
  → expect FK rejection.

MUTATION E:
  duplicate line_no in same order
  → expect UNIQUE rejection.
~~~~

Each mutation isolates **one specific failure cause**, making failures explainable and preventing unrelated constraints from masking the target check.

### 13.4. Metamorphic Testing: Checking Relationships Across Outputs

Sometimes it is hard to compute **exact expected outputs** for complex inputs, yet you can assert **invariant relationships under controlled input transformations**:

- **Increasing discount by $\Delta$** within valid bounds must reduce net by exactly $\Delta$.
- **Adding one valid line** increases the order net total by that exact line's net, holding other lines fixed.
- **Reordering lines** leaves order monetary `SUM` unchanged.
- **Renaming a product's display name** leaves historical revenue unchanged when prices are snapshotted.
- **Joining a valid 1:1 descriptive dimension** never doubles aggregated measures.
- **Replaying the same `eventId`** against an idempotent consumer leaves reservation counts unchanged.

For `net_amount`:

\[
\operatorname{net}(q,p,d+\Delta)
=\operatorname{net}(q,p,d)-\Delta
\]

provided $0\le d+\Delta\le q\times p$ and no additional rounding rules apply. This checks a stronger general property than testing one hardcoded constant.

### 13.5. Model-Based Testing for State Machines

A state model can generate action sequences:

~~~~text
CreateDraft
AddLine
Confirm
Cancel
ConfirmAgain
EditConfirmedLine
~~~~

For each action, the test engine consults a **reference state machine** to check:

- What is the expected next status?
- Should the action be rejected?
- Should side effects occur?
- On retry of the same request, is the outcome idempotent?

The key is **not merely generating isolated status strings**. Transition invariants must test **sequences of historical actions**, such as forbidding `CONFIRMED → DRAFT` or `CONFIRM` after `CANCELLED`.

### 13.6. Shrinking and Failure Reproduction

When a property test finds a long failing sequence, a framework can **shrink** the input to a minimal counterexample. For instance, out of 100 add/remove/edit steps, the failure shrinks to:

~~~~text
1. CreateOrder(DRAFT)
2. AddLine(A)
3. AddLine(B)
4. Confirm
5. Transaction T1 deletes A
6. Transaction T2 deletes B
7. Order is still CONFIRMED, no lines remain
~~~~

Save the **random seed**, schema version, isolation level, and fixture data so failures are reproducible. If a concurrency test depends on scheduler timing, writing "flaky test" helps nobody; log interleavings or use deterministic concurrency test harnesses.

## 14. Testing Missing Data and Invalid States Across System Boundaries

### 14.1. A Schema-Valid JSON Event Can Still Be Business-Invalid

Suppose Sales receives:

~~~~json
{
  "eventId": "e-1001",
  "eventType": "StockReserved",
  "orderId": "1001",
  "productId": "101",
  "quantity": 2
}
~~~~

The JSON has all fields and `quantity > 0`, yet crucial questions remain:

- Did the event come from an **authoritative Inventory service** or an unauthorized source?
- Does `productId` match the **right tenant and order line**?
- Is this a new reservation or a **replay** of the same `eventId`?
- Is it a **stale** event arriving after the order was cancelled?
- Does `quantity = 2` match the **requested reservation quantity**?
- Is there a `reservationId` and corresponding expiration state?

**Schema validation** checks shape and types. **Business validation** checks semantics, ownership, state, and time. Both layers must work together — never equate "valid JSON schema" with "valid event."

### 14.2. Missing Fields and Evolution Contracts

An older consumer knows only `customerId`. A new producer adds `tenantId` to scope customers per tenant. If the consumer drops `tenantId` and keeps looking up by `customerId` alone, it can **misattribute data across tenants** without any parse error.

Tests must cover:

- v1 payload **missing `tenantId`**: is it still permitted under the legacy scope?
- v2 payload **with valid `tenantId`**: mapping must stay within tenant.
- v2 payload **with NULL/empty `tenantId`**: reject per contract if tenant is mandatory.
- Late v1 events arriving after cutover: handle via adapter or controlled rejection.
- Consumer receiving a new enum value: never treat an unknown status as success.

Whenever semantics shift significantly, add **versioning and compatibility tests**, not just a SQL schema version bump.

### 14.3. Analytical Data: Complete and Without Double-Counting

A sales fact has grain **one row per sales line**, linked to `DIM_PRODUCT` to roll up by category. Analytical invariants:

- Every valid sales line appears **exactly once** per chosen business key.
- No fact row is dropped due to a missing or mismatched dimension version.
- No fact row fans out into two rows due to overlapping SCD2 dimension intervals.
- Every measure has appropriate **units, timing, and additivity**.

Tests should verify:

~~~~text
Sum of fact after filtering valid sources
   = Sum across dimension groups (if hierarchy is strict and complete)
   = Reported revenue over the same dataset and period
~~~~

If a dimension belongs to multiple groups or amounts span multiple currencies, this equality requires **allocation/conversion rules**; never claim `SUM` always reconciles while semantics are undecided.

**Analytical design validation differs from pipeline implementation:** We define grain, keys, invariants, and reconciliation checks. Schedulers, CDC, backfills, retries, and alerts are operational implementation, yet must obey those rules.

### 14.4. Data Migrated Across Schema Changes

When renaming/migrating `customer_email` to `buyer_email`:

- **Positive test:** valid legacy emails remain readable in the new field.
- **Negative test:** corrupt or unresolvable legacy data is never filled with fabricated values.
- **Missing-data test:** unbackfilled rows are clearly tracked and not marked "migrated" if the contract requires completeness.
- **Dual-path test:** old/new writers do not cause the two fields to diverge.
- **Final-state test:** drop the old column only after consumers stop reading it and new values are reconciled.

A migration returning exit code 0 does not prove the target data model is right if invalid rows remain or legacy writers keep writing bad data. Therefore, **testing boundary cases and transitional states belongs in the evolution plan**, not just in new-table creation.

## 15. Reproducible Process for Building a Design Validation Suite

### 15.1. Step 1 — Gather Requirements and Write Falsifiable Conditions

Do not start with "write lots of SQL tests." Start with:

1. Define **the entity and exact meaning of one row**.
2. Record data types, bounds, units, nullability, and temporal semantics.
3. Record relationships/keys, valid transitions, and historical rules.
4. State **one minimal counterexample** that would violate the rule.
5. State **when** the rule must hold: at object creation, at `COMMIT`, or at analytics publication.
6. Identify rule ownership across bounded contexts.

For example, "Customer must have contact info" must clarify **whether email OR phone suffices**, whether whitespace-only strings are rejected, whether contact info must be verified, and how legacy customers lacking contacts are handled.

### 15.2. Step 2 — Partition Values and Combinations

For every field:

- Normal valid value.
- Valid lower/upper boundaries.
- Values immediately outside bounds.
- `NULL`, empty string, whitespace-only.
- Wrong type or format at API/JSON boundary.
- Syntactically valid yet **semantically wrong** value (such as another tenant's ID).
- Duplicate, stale, or expired values.

For every relationship:

- Existing parent, missing parent, parent in another tenant.
- Parent with 0, 1, or many children.
- Key collisions within the same scope vs. across distinct scopes.
- Dimension member in multiple groups or no group.

For state:

- Every allowed transition and every forbidden transition.
- Retries and repeated identical commands.
- Two concurrent operations.
- Late or out-of-order events.

### 15.3. Step 3 — Choose Enforcement Layers and Safeguards

| Check layer | Good for | Limitations |
| --- | --- | --- |
| **DTO/API boundary** | Input types, required fields, formats, authorization | Other DB write paths may bypass |
| **Value object/domain** | Single-value or single-aggregate invariants | Unaware of live state in other contexts |
| **DB CHECK/NOT NULL** | Value domains and single-row expressions | Cannot directly enforce multi-row rules |
| **DB UNIQUE/PK** | Scoped key uniqueness | Does not prove business identity is accurate |
| **DB FK** | Referential existence inside the same DB | Does not enforce tenant scope if key omits it; ignores external systems |
| **Exclusion/temporal constraints** | Non-overlapping validity intervals | Requires DBMS support; still check gaps and historical rules |
| **Transaction/locking** | Multi-row or concurrency-sensitive invariants | All writers must follow protocol; test races and retries |
| **Contract/consumer tests** | Cross-system API/event semantics | Valid JSON schema does not prove valid business event |
| **Data quality/reconciliation** | Completeness, dedup, accurate post-transform totals | Detects post-load; does not block at write time |

Critical invariants can be guarded **across multiple layers** because each layer catches different failure modes. Never duplicate rules with **conflicting meanings**: if Java caps at 1000 while the DB caps at 999, the system has two contradictory contracts.

### 15.4. Step 4 — Prepare Clean, Independent Fixtures

A test dataset should have:

- **Deterministic, readable identifiers** that do not collide across fixtures.
- **Valid parent–child setups** before testing negative FKs.
- **Explicit status and timestamps** independent of wall-clock time unless needed.
- A dataset that is **small yet representative of key partitions**.
- Reliable **state reset** per test or isolated resettable schemas.
- Explicit **tenant-scoped events/IDs** in multi-tenant setups.
- **Synthetic placeholder PII** — never copy real customer emails, addresses, or phones.

Never let one negative test corrupt fixtures and cause later tests to fail randomly. In PostgreSQL, use transactions with `ROLLBACK` or a fixture runner ensuring cleanup; expected-failure tests should use **deterministic error trapping** instead of letting an aborted transaction run further statements.

### 15.5. Step 5 — Verify Both Directions: Valid Passes, Invalid Fails

Look for both:

- **False acceptance:** invalid data slips through, e.g., `quantity = 0`.
- **False rejection:** valid data gets blocked, e.g., `discount = gross` when free promos are valid.

Optimizing only for "block all bad data" produces overly rigid constraints that break valid business cases. Optimizing only for "everything saves" produces weak constraints.

### 15.6. Step 6 — Test Under Concurrency and Change

After single-row tests:

- Run two transactions inserting colliding keys.
- Run two requests reserving the same stock.
- Run two operations editing lines on the same order.
- Run old and new writers concurrently during a migration.
- Test duplicate, late, and cross-tenant events.
- Test SCD2 changes right at boundary timestamps.
- Test legacy records lacking sufficient data for backfill.

An invariant can pass **100% of sequential tests** and still break under two concurrent transactions.

### 15.7. Step 7 — Post-Change Verification and Acceptance Evidence

After updating a model:

1. Re-run boundary test suites.
2. Verify **migrations affected the right scope and target data**.
3. Check queries/reports for row multiplication from key or hierarchy changes.
4. Evaluate locking overhead, conflict rates, and new constraint costs.
5. Record results tied to **schema version, build version, fixture version, and DB isolation level**.
6. Label which invariants are **DB-enforced**, **application-only**, or **post-load detective** — never lump all of them into "DB PASS."

If a known gap is temporarily accepted, record **risk, scope, deadline, and remediation owner**. Never sign off "fully validated" while a core invariant remains unprotected.

## 16. Design Validation Acceptance Checklist

### 16.1. Requirements and Model Checks

- [ ] Every entity/relationship defines **what one row represents** and its business key identity.
- [ ] Invariants are written as statements **accepting or falsifying** concrete data.
- [ ] Numeric domains state **lower/upper bounds**, inclusive/exclusive policy, and units.
- [ ] `NULL`, empty, `Unknown`, and `Not applicable` have clear, unmixed meanings.
- [ ] Mandatory columns use **`NOT NULL`** where `CHECK` alone could let `UNKNOWN` pass.
- [ ] `UNIQUE`/FK keys include **tenant, source, time, or scope** where required.
- [ ] **Inverse cardinality** is enforced or checked when a parent requires children.
- [ ] State machines specify allowed and forbidden transitions, not just an enum list.
- [ ] Historical timestamps use clear interval conventions (e.g., `[from, to)`) with gap/overlap rules.
- [ ] Monetary and quantity fields have approved **units, precision/scale, and rounding rules**.

### 16.2. Data and Transaction Checks

- [ ] Positive tests exist **at boundaries** and negative tests **just outside boundaries**.
- [ ] Missing data is tested across **SQL NULL, JSON null, omitted fields, empty strings, and whitespace**.
- [ ] PK/FK/UNIQUE/CHECK tests assert **the exact expected error type**, not any arbitrary exception.
- [ ] FK tests cover tenant scope and cross-tenant identity collisions.
- [ ] Tests cover **0, 1, and many child rows** plus aggregate confirmation rules.
- [ ] Tests cover state transitions, cancellation, retries, and stale/late processing.
- [ ] Concurrency tests cover invariants spanning multiple rows or shared resources.
- [ ] Temporal interval tests cover exact start/end boundaries, overlaps, and gaps.
- [ ] Reconciliation verifies **formulas and measures** against sources and semantics.
- [ ] Preventive **write-time blocks** are distinguished from detective **post-write audits**.

### 16.3. Operations and Evolution Checks

- [ ] Fixtures are resettable, repeatable, and free of real customer PII.
- [ ] Test suites record schema/app/contract versions and required isolation levels.
- [ ] Mixed old/new writer/reader tests exist when evolving schemas.
- [ ] Replay/duplicate and late-arriving event tests exist at integration boundaries.
- [ ] Metrics/logs exist for constraint violations, conflicts, deadlocks, missing data, and reconciliation mismatches.
- [ ] Each invariant has an owner and an exception-resolution policy.
- [ ] Intentionally invalid `INSERT`/`UPDATE` tests are never run on production databases.
- [ ] "Concurrency tested" is never claimed from single-connection sequential runs.
- [ ] "Migration finished" is never equated with "all data now satisfies business semantics."

### 16.4. Minimum Acceptance Matrix

| Scope | Minimum evidence | If missing |
| --- | --- | --- |
| **Single-row invariants** | Positive/negative boundary tests, SQLSTATEs, committed rows | Value domains unverified |
| **Referential integrity** | Scoped FKs, orphan and cross-tenant tests | Risk of invalid cross-links |
| **State machine** | Allowed/forbidden action-sequence tests | Valid enum may hide illegal transitions |
| **Temporal integrity** | Adjacent, overlap, gap, and event-time tests | Risk of joining wrong historical versions |
| **Concurrent invariants** | Two real connections, post-commit assertions | Risk of races / write skew |
| **Integration validity** | Contract tests, replay/late/missing-field tests | Valid JSON may carry wrong semantics |
| **Analytics consistency** | Fact/grain/dimension/measure reconciliation | Risk of doubled or dropped revenue |
| **Schema evolution** | Mixed-version tests, backfill/reconciliation | Unsafe transitional states |

**Validation claims must be scoped:** "Quantity and discount `CHECK`s passed 12 tests" is a narrow, evidence-backed claim. It **does not** mean "ConfirmOrder is race-free" without dedicated tests and safeguards for that rule.

## 17. Practice Exercises with Answers

### Exercise 1 — Quantity Boundary Values

An order line has integer `quantity` in **`[1,1000]`**.

**Question:** Classify `-1, 0, 1, 2, 999, 1000, 1001`, and `NULL` as valid or invalid.

**Answer:** **`1, 2, 999, 1000` are valid**; `-1, 0`, and `1001` are out of bounds; `NULL` is invalid if quantity is mandatory. Test at **`1` and `1000`**, not just interior values. Both endpoints are inclusive under `[1,1000]`.

### Exercise 2 — Does CHECK Alone Guard Against NULL?

A table has `quantity INTEGER CHECK (quantity > 0)` without `NOT NULL`.

**Question:** Will `INSERT` with `quantity = NULL` be rejected by `CHECK`? Why?

**Answer:** **No**, because `NULL > 0` evaluates to **`UNKNOWN`**, and PostgreSQL `CHECK` rejects only `FALSE`. To require a present, positive quantity, use **`quantity INTEGER NOT NULL CHECK(quantity > 0)`**.

### Exercise 3 — Discount Right on the Boundary

A line has `quantity = 2`, `unit_price = 100.00 VND`, and `discount` in `[0, 200.00]`.

**Question:** Are `-0.01, 0, 199.99, 200.00, 200.01` valid? What is net when `discount = 200`?

**Answer:** **`0, 199.99`, and `200.00` are valid**; `-0.01` and `200.01` are invalid. When `discount = 200.00`, `net_amount = 0.00 VND`. Do not forbid 100% discounts when free promotions are permitted by contract.

### Exercise 4 — Missing Contact Information

Customers must have at least one non-empty email or phone after trimming.

**Question:** Classify four cases:

~~~~text
A: email=NULL, phone='0900000000'
B: email='a@example.org', phone=NULL
C: email=NULL, phone=NULL
D: email='   ', phone='0900000000'
~~~~

**Answer:** **A and B are valid.** **C** has no contact method. **D** is rejected in the example model because `email` is provided yet contains only whitespace, violating **`ck_email_not_blank`**; having a valid phone does not make a blank email valid. If the business decides to trim and normalize empty strings to `NULL` at the API, document and test that rule explicitly.

### Exercise 5 — UNIQUE and Multiple NULLs

A table has `email TEXT UNIQUE` allowing `NULL`. Two users without email both store `NULL`.

**Question:** Are both rows accepted in default PostgreSQL? Is it a data bug?

**Answer:** **Accepted** under default `UNIQUE`. It is not a bug if the business allows multiple users without email. To disallow `NULL`, use `NOT NULL`; to treat `NULL` as duplicate, choose the appropriate engine mechanism **and confirm semantics** rather than tightening constraints arbitrarily.

### Exercise 6 — Case-Insensitive Email Uniqueness

A table has a unique index on `LOWER(BTRIM(email))` and already stores `an@example.org`.

**Question:** Is inserting `AN@example.org` accepted? Why isn't plain `UNIQUE(email)` enough?

**Answer:** The normalized index rejects it because **`LOWER('AN@example.org')`** collides with the stored email. Plain `UNIQUE` on raw strings distinguishes letter case. However, email normalization rules are **a business/technical policy to confirm**, not an excuse to assume arbitrary complex normalizations.

### Exercise 7 — One-Way Nature of Foreign Keys

`ORDER_LINE.order_id` has an FK to `SALES_ORDER.order_id`. A `DRAFT` order has zero lines.

**Question:** Does that violate the FK? If transitioned to `CONFIRMED`, will the FK block it?

**Answer:** **No FK violation** while the order has zero lines. A child-to-parent FK guarantees only **if a child exists, its parent exists**. It does not guarantee a parent has at least one child. Blocking line-less `CONFIRMED` orders requires checking **a multi-row invariant** in the transition path or extra DB safeguards.

### Exercise 8 — Error Codes in Negative Tests

A test expects an FK to reject `order_id = 9999`, yet SQL fails because column `order_ids` does not exist.

**Question:** Should it be marked PASS because the `INSERT` errored?

**Answer:** **No.** The error proves nothing about the FK. Assert **`SQLSTATE 23503`** (and constraint name when needed) instead of accepting any exception. Keep all other conditions valid so only the target rule fails.

### Exercise 9 — Valid State Values but Invalid Transition

An order is `CONFIRMED`. SQL sets `status = 'DRAFT'` and `confirmed_at = NULL`. Both satisfy the row `CHECK`.

**Question:** Why can this still be a business bug?

**Answer:** Because the example state machine **forbids `CONFIRMED → DRAFT`**. A status `CHECK` inspects only **the target value**, not the transition path. You need transition services, triggers, or controlled write paths to protect transition history.

### Exercise 10 — Two Concurrent Requests Confirming One Order

Two `ConfirmOrder` requests run concurrently for a `DRAFT` order with one line.

**Question:** Besides ending in `status = CONFIRMED`, what else must be verified?

**Answer:** Ensure **no duplicate side effects** such as charging twice or issuing two non-idempotent stock reservations. Verify transition/version checks, concurrent transactions, idempotency keys, the second request's response, and emitted events. A correct final `status` field **does not prove the workflow avoided duplicate side effects**.

### Exercise 11 — SCD2 Interval Boundaries

Customer versions:

~~~~text
R1: [2026-01-01 00:00, 2026-10-02 00:00)
R2: [2026-10-02 00:00, unbounded)
~~~~

**Question:** Which version owns an event at exactly `00:00` on Oct 02? What risk arises if querying `valid_to >= event_time`?

**Answer:** **R2**, because the start is inclusive and the end is exclusive. Using `valid_to >= event_time` can make R1 match right at its end boundary too, causing **two joined rows** for one event.

### Exercise 12 — UNIQUE Does Not Block Overlaps

Two versions of the same customer start on Oct 01 and Oct 03, while the first expires on Oct 05.

**Question:** Does `UNIQUE(customer_id, valid_from)` catch the overlap? What else is needed?

**Answer:** **No**, because `valid_from` differs. You need a **non-overlapping validity invariant**, such as a PostgreSQL range exclusion constraint or proper locking/triggers, backed by concurrent insert tests. Also decide whether **gaps** are permitted, as no-overlap does not guarantee continuous coverage.

### Exercise 13 — Event Time vs. Ingestion Time

A customer changes segment at `00:00` on Oct 02. An order is sold at `23:00` on Oct 01, yet reaches the warehouse at `03:00` on Oct 02.

**Question:** If a KPI asks for segment at sale time, which version applies?

**Answer:** The version effective **at 23:00 on Oct 01**, not when the event was ingested. Look up intervals by **`event_time`**. An FK to a valid version does not guarantee it is the right version for the transaction timestamp.

### Exercise 14 — Two Transactions Reserving Stock Simultaneously

Stock has `on_hand_qty = 5` and `reserved_qty = 0`. Two requests both try to reserve 4.

**Question:** Can both reservations commit? What check is safer than blind `SELECT` then `UPDATE`?

**Answer:** **No**, if both need 4 units concurrently without intervening releases or restocks. Use a **conditional `UPDATE` against available stock** inside a transaction plus `CHECK (reserved_qty <= on_hand_qty)`; test with **two concurrent connections**. At most one 4-unit reservation may succeed absent other stock changes.

### Exercise 15 — Write Skew Across Order Lines

A `CONFIRMED` order has two lines A and B. Transaction T1 sees B and deletes A; transaction T2 sees A and deletes B.

**Question:** If both commit, which invariant breaks? Is an FK alone enough?

**Answer:** The `CONFIRMED` order can end up with **0 lines**, breaking the minimum-one-line rule. A child → parent FK never blocks deleting the last line. Coordinate edits/deletes and transitions via **one locking/transaction protocol** or DB safeguards, run concurrency tests, and handle serialization conflicts if using strict isolation.

### Exercise 16 — Right Entity Type, Wrong Tenant

`Department(tenant=20, id=8)` exists; `Employee(tenant=10, id=101)` references `department_id=8`.

**Question:** Why is an FK on `department_id` alone insufficient? What design blocks it?

**Answer:** It proves only that `department_id=8` **exists in some tenant**. When cross-tenant links are forbidden, use a scoped FK: **`FOREIGN KEY(tenant_id, department_id) REFERENCES department(tenant_id, department_id)`** with `NOT NULL` on mandatory components.

### Exercise 17 — PATCH API and Intent to Clear Data

A customer has only email (`phone` is `NULL`). A `PATCH` API receives `{"email": null}` to clear email.

**Question:** What must be checked? Does `{}` mean the same thing?

**Answer:** Removing email leaves the customer **with zero contact methods**, violating the rule. The API should reject early or the DB `CHECK` rejects at write time. Payload **`{}`** usually means **no change**, distinct from clearing email; if a framework deserializes both to `null`, preserve user intent explicitly.

### Exercise 18 — Metamorphic Test for Revenue

A valid line has `q=2, p=100.00, d=30.00, net=170.00`. Increase discount by `20.00` within valid bounds.

**Question:** How must `net` change? What kind of test is this?

**Answer:** New `net = 150.00`, dropping by **exactly `20.00`**. This is a **metamorphic/property test**, verifying a relationship across two results rather than comparing one output to a constant; it assumes no extra rounding rule alters the arithmetic.

### Exercise 19 — Analytical Measures Multiplied by JOIN

Fact sales has one row with `100,000 VND` for `P01`. `DIM_PRODUCT` SCD2 has two versions with `product_id=P01`. A report joins on `product_id` ignoring time.

**Question:** What risk threatens total revenue? What check catches it?

**Answer:** One fact row can join into **two rows**, inflating the total to **`200,000 VND`**. Join via the **selected version's `product_key`** or valid interval; assert post-JOIN row counts and **reconcile fact totals against report totals** under shared grain and additivity assumptions.

### Exercise 20 — Adding NOT NULL Means Legacy Data Is Accurate?

A migration converts an unstructured address field into `province_code NOT NULL` by setting every unknown row to `"01"`. Migration succeeds with zero NULLs.

**Question:** Is the new model validated?

**Answer:** **No.** `NOT NULL` ensures a value is present, not that **`"01"` is the right province**. Reconcile against authoritative sources, distinguish unknown/unresolved states, and apply defaults only when business-meaningful. Tests must verify **semantics and provenance**, not just shape.

### Exercise 21 — Negative Test Accidentally Breaks Two Rules

An `INSERT` testing an orphan FK passes `order_id=9999` along with `quantity=0`. The DB throws a `CHECK` violation.

**Question:** Did the FK test pass?

**Answer:** **Not yet.** The SQL failed on invalid `quantity` before proving the FK works. Use a valid `quantity` and valid remaining fields, changing only **`order_id` to a non-existent ID**, and assert `SQLSTATE 23503` or the expected FK name.

### Exercise 22 — Duplicate Record in an Event Stream

A consumer receives `StockReserved(eventId=e1)` again on retry and increments `reserved_qty` a second time.

**Question:** Is this a data-type bug or which invariant?

**Answer:** It is an **idempotency / event-identity** bug, not a SQL type error. Consumers must record processed events and tie resource updates to an appropriate transaction; besides `eventId`, a **business request ID** may also be needed to deduplicate distinct messages carrying the same business intent.

### Exercise 23 — Should Boundary Values Always Be Rejected?

A product costs `0.00 VND` under a free-gift campaign; quantity sold is `1`. A default test rejects every `unit_price=0` assuming sales always cost money.

**Question:** Is this test right or wrong?

**Answer:** **Wrong under this lesson's contract**, because `unit_price >= 0` makes **`0` a valid boundary**. A negative test is valid only when the business genuinely forbids zero prices. If a specific order type requires positive prices, enforce a conditional invariant by order type rather than blocking all lines.

### Exercise 24 — DB and Domain Tests Can Contradict

Java checks `quantity < 1000`, whereas SQL checks `quantity BETWEEN 1 AND 1000`. Business spec is `[1,1000]`.

**Question:** What happens for `quantity=1000` and how do you fix it?

**Answer:** Java rejects what the DB accepts — a **false rejection** in the application layer. Align Java to `quantity <= 1000` and run a shared **boundary contract test suite** across both layers.

### Exercise 25 — Can CHECKs Alone Prevent All Drift?

A team verifies `quantity`, `discount`, and `status` `CHECK`s and concludes no transaction, FK, event, or historical tests are needed.

**Question:** Where is that conclusion wrong?

**Answer:** A single-row `CHECK` protects **a narrow class of conditions** — never FKs, multi-row relationships, transition sequences, concurrency, SCD2 versions, or cross-system event accuracy. Match **each safeguard to its invariant scope** and test with counterexamples instead of judging the entire model by one constraint type.

### Exercise 26 — Writing a Comprehensive Validation Plan

A project adds `CONFIRMED` status, SCD2 customer segments, and stock reservations. The lead asks for "a test plan proving the design is solid."

**Question:** List at least six required test categories with key expected outcomes.

**Sample answer:**

1. **Boundary values:** `quantity=1/1000` accepted, `0/1001` rejected; negative/excessive discounts rejected.
2. **NULL/missing:** customer missing both email and phone rejected; NULL email with valid phone accepted.
3. **Keys/relationships:** line pointing to missing order/product rejected by FK; duplicate `line_no` in same order rejected by `UNIQUE`.
4. **State:** `ConfirmOrder` with zero lines rejected; `Confirm` from eligible `DRAFT` accepted; `CONFIRMED → DRAFT` rejected.
5. **SCD2:** adjacent intervals accepted; same-customer overlap rejected; event at `valid_to` matches only the new version.
6. **Concurrency:** two over-stock reservations cannot both commit; confirmed order cannot lose its last line.
7. **Integration:** duplicate events handled idempotently; late events never regress status or attach wrong segments.
8. **Analytics reconciliation:** grain-matched fact totals equal report totals after joining conformed dimensions within additive scope.
9. **Evolution:** old/new writers and unbackfilled rows follow contract; new constraints tighten only once data qualifies.

A trustworthy validation report logs **which tests ran, sample inputs, expected outcomes, version identifiers, and remaining risks**.

## 18. Summary

| Concept | Key takeaway |
| --- | --- |
| **Invariant** | Data condition that must hold at defined business/transaction boundaries |
| **Boundary value analysis** | Test just below, right on, and just above thresholds — not just normal values |
| **Positive test** | Valid data, especially right on boundaries, must be accepted |
| **Negative test** | Invalid data must be rejected for **the right reason**, not just any exception |
| **NULL / UNKNOWN** | `CHECK` can let `UNKNOWN` pass; `NOT NULL` is a separate constraint |
| **Empty / whitespace** | Empty and whitespace-only strings are not SQL `NULL` |
| **UNIQUE** | Enforces scoped key uniqueness; `NULL` has specific semantics |
| **FK** | Guards child → parent references; does not prove parent has children or same tenant without scope |
| **State machine** | Must validate **transition paths**, not just status values |
| **Temporal invariant** | Interval boundaries, overlaps/gaps, event time, and effective versions |
| **Concurrency** | Multi-row invariants need transactions/locking or proper DB mechanisms |
| **Business key** | Requires right identity and tenant/source/time scope, not just matching ID types |
| **Domain validation** | Rejects bad values early, yet does not replace DB constraints |
| **Property-based testing** | Generates broad inputs to verify general invariants |
| **Metamorphic testing** | Checks relationships across outputs under controlled input shifts |
| **Model-based testing** | Validates action sequences and state-transition rules |
| **Data quality / reconciliation** | Catches missing, duplicate, or semantically wrong data post-load/integration |
| **Design acceptance** | States scope, evidence, and any unguarded invariants explicitly |

**Conclusion:** A validated data model is not merely one that creates tables and stores clean examples. You must **actively try to break invariants** using just-out-of-bounds values, `NULL` and omitted fields, non-existent keys, illegal transitions, overlapping intervals, and concurrent transactions. Every counterexample must pair with **expected outcomes and specific safeguards**, while positive boundary tests prove valid data still passes. Combining **Java validation, SQL constraints, transactions, contract tests, and data reconciliation** yields designs that can be explained, evolved, and defended under real conditions harder than sample datasets.
