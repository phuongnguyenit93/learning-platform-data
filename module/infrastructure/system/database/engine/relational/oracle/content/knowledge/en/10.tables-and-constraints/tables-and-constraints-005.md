# CHECK, NOT NULL, and the Limits of Declarative Data Validation in Oracle Database

## 1. The Problem: Who Guarantees Data Remains Valid?

An ordering application might check `quantity > 0` in the UI, Java service layer, and PL/SQL procedures. Yet data can also be written via batch jobs, SQL scripts, other applications, imports, or maintenance tasks. Relying solely on application-side validation forces every write path to implement the exact same rule consistently. **Integrity constraints** in Oracle Database establish a data contract directly on the table: every DML operation within the constraint's enforcement scope must satisfy the declared rules.

Two fundamental yet critical constraint forms:

- **`NOT NULL`:** a column must hold a value other than `NULL`.
- **`CHECK (condition)`:** the values of **each row** must cause the check condition to evaluate to **`TRUE` or `UNKNOWN`**; only **`FALSE`** violates it.

Example:

```sql
CREATE TABLE order_items_demo (
    item_id    NUMBER PRIMARY KEY,
    sku        VARCHAR2(30 CHAR) NOT NULL,
    quantity   NUMBER NOT NULL,
    unit_price NUMBER(12,2) NOT NULL,
    discount   NUMBER(5,2),
    CONSTRAINT oi_quantity_ck CHECK (quantity > 0),
    CONSTRAINT oi_price_ck    CHECK (unit_price >= 0),
    CONSTRAINT oi_discount_ck CHECK (discount BETWEEN 0 AND 100)
);
```

This table blocks `quantity = 0`, `unit_price = -1`, and `quantity = NULL`, yet **permits `discount = NULL`**: the `CHECK` constraint on `discount` evaluates to UNKNOWN when the column is NULL, and the column does not have `NOT NULL`.

> This lesson uses standard Oracle Database 19c behavior. Syntax and additional features may vary in other releases. `CREATE TABLE`, `ALTER TABLE`, `INSERT`, and `DROP TABLE` statements perform real changes; run them only in a lab schema you own. Read-only metadata queries may be run in any environment where you have appropriate privileges.

## 2. Where Do CHECK and NOT NULL Fit in the Constraint System?

| Mechanism | Rule It Protects | Example | What It Does **Not** Do |
| --- | --- | --- | --- |
| `NOT NULL` | A column cannot be NULL | `email VARCHAR2(200) NOT NULL` | Does not prove the email is well-formed or active |
| `CHECK` | Valid expression **on the current row** | `CHECK (price >= 0)` | Does not aggregate across rows or query other tables |
| `PRIMARY KEY` | Unique identifier, non-NULL | `order_id PRIMARY KEY` | Does not validate business state |
| `UNIQUE` | Uniqueness per Oracle's NULL semantics | `CONSTRAINT uq_code UNIQUE(code)` | Does not ensure a string follows a valid format |
| `FOREIGN KEY` | Referenced value exists in a valid parent key | `customer_id REFERENCES customers(id)` | Does not enforce arbitrary conditional or aggregate rules |
| `DEFAULT` | Supplies a default value per column rules | `status DEFAULT 'NEW'` | Does not replace constraints; does not automatically block NULL |
| Trigger / procedure | Executes multi-step logic, can read additional data | Enforce specialized workflows | Must handle concurrency, errors, and privileges carefully |
| Application / API | UX, user-friendly messages, and business workflows | Validate input before sending SQL | Cannot block write paths bypassing that application |

A sound defensive architecture:

```text
Client/API validation        → catch early, explain errors clearly
        │
        ▼
Service / PL/SQL transaction → execute business logic and coordinate across rows
        │
        ▼
Oracle table constraints     → reject rows violating declared invariants
        │
        ▼
Committed database state     → data protected regardless of standard write path
```

An **invariant** is a property that must always hold for accepted data states—for example, "price is non-negative," "end date is not before start date," or "status belongs to the allowed set." Matching each constraint to the **scope** of its invariant is the first step in table design.

## 3. Syntax: Declaring at Table Creation and on Existing Tables

### 3.1. `NOT NULL` Is an Inline Column Constraint

```sql
CREATE TABLE customer_contact_demo (
    customer_id NUMBER,
    full_name   VARCHAR2(100 CHAR)
        CONSTRAINT ccd_name_nn NOT NULL,
    email       VARCHAR2(200 CHAR),
    CONSTRAINT ccd_pk PRIMARY KEY (customer_id)
);
```

`NOT NULL` is declared in the **column definition**. If unnamed, Oracle generates a name like `SYS_C...`; consistent naming makes error logs, migrations, and dashboards easier to interpret.

Adding `NOT NULL` to an existing column:

```sql
ALTER TABLE customer_contact_demo
  MODIFY (email CONSTRAINT ccd_email_nn NOT NULL);
```

This command checks existing data; if any row has `email IS NULL`, applying the constraint under default validation mode fails. Clean up or migrate existing rows first.

### 3.2. `CHECK` Can Be Inline or Out-of-Line

**Inline** when the expression involves only one column:

```sql
CREATE TABLE product_demo (
    product_id NUMBER PRIMARY KEY,
    price      NUMBER(12,2)
        CONSTRAINT product_price_ck CHECK (price >= 0)
);
```

**Out-of-line** at table level when the rule compares multiple columns:

```sql
CREATE TABLE booking_period_demo (
    booking_id NUMBER PRIMARY KEY,
    starts_at  DATE NOT NULL,
    ends_at    DATE NOT NULL,
    CONSTRAINT booking_period_ck CHECK (ends_at >= starts_at)
);
```

In a table-level CHECK expression, you may reference **multiple columns of the same row**. Examples: `CHECK (end_date >= start_date)`, `CHECK (discount <= amount)`, `CHECK (status <> 'CANCELLED' OR cancel_reason IS NOT NULL)`.

Adding a CHECK to an existing table:

```sql
ALTER TABLE product_demo
  ADD CONSTRAINT product_discount_ck
  CHECK (price <= 999999.99);
```

By default, a new CHECK must hold for existing data under `ENABLE VALIDATE` mode. An `ENABLE NOVALIDATE` transition path for legacy data is covered in the constraint lifecycle section.

### 3.3. A Column Can Have Multiple CHECK Constraints

```sql
CREATE TABLE item_validation_demo (
    item_id NUMBER PRIMARY KEY,
    code    VARCHAR2(30 CHAR) NOT NULL,
    amount  NUMBER(12,2),
    CONSTRAINT iv_amount_nonnegative_ck CHECK (amount >= 0),
    CONSTRAINT iv_amount_max_ck         CHECK (amount <= 1000000),
    CONSTRAINT iv_code_nonblank_ck      CHECK (TRIM(code) IS NOT NULL)
);
```

Several small constraints—each representing **one rule**—are usually easier to read and handle in errors than one giant expression. **Oracle does not guarantee the evaluation order of multiple CHECK constraints**; never write conditions whose behavior relies on constraint A running before constraint B.

## 4. The Most Important Rule: CHECK Accepts TRUE **and** UNKNOWN

SQL does not have only `TRUE` and `FALSE`. When an expression compares a `NULL` value, the result is typically **`UNKNOWN`**. Oracle considers a CHECK constraint violated **only when the condition evaluates to FALSE**.

| `score` Value | `score >= 0` | Does CHECK Allow It? |
| --- | --- | --- |
| `15` | TRUE | Yes |
| `0` | TRUE | Yes |
| `-3` | FALSE | **No** |
| `NULL` | UNKNOWN | **Yes** |

Therefore:

```sql
CREATE TABLE score_demo (
    score NUMBER
        CONSTRAINT score_nonnegative_ck CHECK (score >= 0)
);

INSERT INTO score_demo(score) VALUES (10);   -- Valid.
INSERT INTO score_demo(score) VALUES (NULL); -- Also valid!
```

If the rule requires **both a non-null score and a non-negative value**, declare both conditions:

```sql
CREATE TABLE score_required_demo (
    score NUMBER NOT NULL,
    CONSTRAINT score_required_ck CHECK (score >= 0)
);
```

### 4.1. Three-Valued SQL Truth Table

| A | B | `A AND B` | `A OR B` |
| --- | --- | --- | --- |
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

With `NOT`: `NOT TRUE = FALSE`, `NOT FALSE = TRUE`, and `NOT UNKNOWN = UNKNOWN`.

Important consequence: `CHECK (salary > 0 OR commission >= 0)` **accepts** `salary = NULL` and `commission = -100`, because `UNKNOWN OR FALSE = UNKNOWN`. If the rule requires both columns to be present, add `NOT NULL` or explicit null checks.

### 4.2. `= NULL` Is Not a NULL Check

```sql
-- SEMANTICALLY WRONG: col <> NULL evaluates to UNKNOWN for all values.
CHECK (status <> NULL)

-- RIGHT: use IS NOT NULL.
CHECK (status IS NOT NULL)
```

For normal columns, **declare `NOT NULL`** rather than a separate CHECK containing only `IS NOT NULL`, as column intent and metadata are clearer. A CHECK using `IS NOT NULL` is useful inside compound conditional expressions or special cases.

## 5. NOT NULL: A Value Must Exist, Not Necessarily Be Meaningful

### 5.1. Three Cases Often Confused

| Case | Value | With `NOT NULL` | Business-Valid? |
| --- | --- | --- | --- |
| Not provided | `NULL` | **Blocked** | Depends on requirement |
| Empty string for `VARCHAR2` | `''` | Current Oracle treats as `NULL` → **blocked** | Usually no |
| Whitespace-only string | `'   '` | **Accepted** because not NULL | Usually no if real name/code is needed |
| String `'0'` | Non-NULL | Accepted | Might be out of domain |
| String `'UNKNOWN'` | Non-NULL | Accepted | Depends on business rules |

In Oracle Database, zero-length character strings **are currently treated as NULL** in standard `VARCHAR2` usage; **do not** rely on distinguishing `''` from `NULL` in Oracle tables. However, a string containing one or more spaces **is not** NULL. For blank-padded `CHAR` columns, also consider column type semantics.

To reject whitespace-only codes:

```sql
CREATE TABLE customer_code_demo (
    code VARCHAR2(30 CHAR)
        CONSTRAINT customer_code_nn NOT NULL,
    CONSTRAINT customer_code_nonblank_ck
      CHECK (TRIM(code) IS NOT NULL)
);
```

**Why not use `CHECK (LENGTH(TRIM(code)) > 0)` alone?** When `TRIM(code)` becomes an empty string (treated by Oracle as NULL), `LENGTH(NULL) > 0` evaluates to **UNKNOWN**, so CHECK **accepts** it. `TRIM(code) IS NOT NULL` catches the exact case you want to reject.

### 5.2. `DEFAULT` Does Not Replace `NOT NULL`

```sql
CREATE TABLE status_default_demo (
    id     NUMBER PRIMARY KEY,
    status VARCHAR2(20 CHAR) DEFAULT 'NEW' NOT NULL
);

INSERT INTO status_default_demo(id) VALUES (1);
-- STATUS gets 'NEW' when the column is omitted in INSERT.

-- The following DML is blocked by NOT NULL:
INSERT INTO status_default_demo(id, status) VALUES (2, NULL);
```

Standard `DEFAULT` applies when a value is omitted per statement semantics; an **explicit NULL** is not automatically replaced by DEFAULT. Oracle offers `DEFAULT ON NULL` with its own rules, yet even when using it, you must still define CHECK rules and UPDATE semantics clearly. Defaulting is a **value-population policy**, not a substitute for enforcing invariants.

### 5.3. PRIMARY KEY Already Implies NOT NULL

`PRIMARY KEY` guarantees **uniqueness and non-NULL**. Thus, with `order_id NUMBER PRIMARY KEY`, you do not need an extra `CHECK (order_id IS NOT NULL)` just for the same rule. Giving the PK a **deliberate constraint name** is still essential.

### 5.4. NOT NULL Is Recorded in Constraint Metadata

In `USER_CONSTRAINTS` / `DBA_CONSTRAINTS`, both `NOT NULL` and regular `CHECK` constraints appear with `CONSTRAINT_TYPE = 'C'`. A `NOT NULL` constraint is identifiable by a condition such as `"COL_NAME" IS NOT NULL` and column metadata; do not treat every `CONSTRAINT_TYPE='C'` row blindly as a business CHECK constraint.

Oracle requires `NOT NULL` to be **declared inline on the column** (e.g., `MODIFY (col CONSTRAINT col_nn NOT NULL)`); for multi-column conditions, use an out-of-line table-level CHECK.

## 6. Practical CHECK Patterns for Real Schemas

### 6.1. Fixed Value Set: `IN`

```sql
status VARCHAR2(12 CHAR)
    CONSTRAINT orders_status_nn NOT NULL,

CONSTRAINT orders_status_ck
    CHECK (status IN ('NEW', 'PAID', 'SHIPPED', 'CANCELLED'))
```

Benefit: only approved statuses can be stored. Considerations:

- `NULL` still passes an `IN` CHECK **without** `NOT NULL`.
- `'paid'` differs from `'PAID'` under standard comparison/collation rules; if uppercase is required, normalize and validate explicitly.
- If the status list changes frequently or carries metadata like `display_name` and `is_active`, consider a **lookup table + foreign key** instead of altering a CHECK every time a code is added.

### 6.2. Numeric Ranges: `BETWEEN`, `>=`, `<=`

```sql
CONSTRAINT price_nonnegative_ck CHECK (unit_price >= 0),
CONSTRAINT discount_pct_ck     CHECK (discount_pct BETWEEN 0 AND 100)
```

`NUMBER(5,2)` only bounds **precision/scale**, not whether `discount_pct` stays between 0 and 100. Add a CHECK constraint for the business range, and `NOT NULL` if discount is mandatory.

### 6.3. Relationship Between Two Columns **in the Same Row**

```sql
CONSTRAINT validity_dates_ck
  CHECK (valid_to IS NULL
         OR (valid_from IS NOT NULL AND valid_to >= valid_from))
```

Meaning: the end date may be open/unknown, yet **if an end date is present, a start date must also exist and end date cannot precede start date**.

If both are always required, it is simpler:

```sql
valid_from DATE NOT NULL,
valid_to   DATE NOT NULL,
CONSTRAINT validity_dates_ck CHECK (valid_to >= valid_from)
```

### 6.4. Conditional Rule: Status Requires Another Field

```sql
CONSTRAINT cancelled_reason_ck
  CHECK (status <> 'CANCELLED'
         OR TRIM(cancel_reason) IS NOT NULL)
```

If `status = 'CANCELLED'`, the left side is FALSE, forcing `cancel_reason` to be non-NULL/non-empty/non-blank. If status differs from `'CANCELLED'`, the left side is TRUE so no reason is required. **Pair this with `status NOT NULL`** so UNKNOWN never lets rows with missing status slip past.

Some rules also require the converse: "when not CANCELLED, `cancel_reason` must be NULL." That requires an explicit additional expression; do not assume the CHECK above forbids a reason for other statuses.

### 6.5. Format Validation: Limits of `LIKE` and `REGEXP_LIKE`

```sql
-- Illustrative code policy only, not universal validation across countries.
CONSTRAINT customer_code_pattern_ck
  CHECK (REGEXP_LIKE(customer_code, '^[A-Z0-9-]+$', 'c'))
```

When `customer_code IS NULL`, the expression does not replace `NOT NULL`. Regular expressions check only **string shape**, not whether a code is real, issued, non-duplicate, or business-valid. For emails, phone numbers, tax IDs, and addresses, checking "real/active" lies outside declarative CHECK constraints.

### 6.6. Avoid Implicit Type Conversions in CHECK

Never write `CHECK (varchar_price > '100')` expecting numeric comparison: string comparison semantics and NLS/implicit conversions can behave unexpectedly. **Store numbers in NUMBER columns**, dates/times in DATE/TIMESTAMP columns, and compare using matching literals and types. When date/time expressions are needed, use explicit DATE/TIMESTAMP literals instead of relying on session date formats.

## 7. Complete Example: Orders Table with CHECK and NOT NULL

Suppose an application schema manages orders with these rules:

1. Every order has `order_id`, `order_code`, `status`, `quantity`, and `unit_price`.
2. `order_code` cannot be empty or whitespace-only.
3. `status` belongs to a controlled set.
4. `quantity > 0` and `unit_price >= 0`.
5. `discount_pct` may be NULL; if supplied, it must be between 0 and 100.
6. `valid_to` may be NULL; if non-NULL, `valid_from` must exist and `valid_to >= valid_from`.
7. When `status = 'CANCELLED'`, a non-blank reason is required.

```sql
CREATE TABLE orders_check_lab (
    order_id       NUMBER
        CONSTRAINT orders_lab_pk PRIMARY KEY,

    order_code     VARCHAR2(40 CHAR)
        CONSTRAINT orders_lab_code_nn NOT NULL,

    status         VARCHAR2(12 CHAR) DEFAULT 'NEW'
        CONSTRAINT orders_lab_status_nn NOT NULL,

    quantity       NUMBER(8)
        CONSTRAINT orders_lab_quantity_nn NOT NULL,

    unit_price     NUMBER(12,2)
        CONSTRAINT orders_lab_price_nn NOT NULL,

    discount_pct   NUMBER(5,2),
    valid_from     DATE,
    valid_to       DATE,
    cancel_reason  VARCHAR2(200 CHAR),

    CONSTRAINT orders_lab_code_ck
      CHECK (TRIM(order_code) IS NOT NULL),

    CONSTRAINT orders_lab_status_ck
      CHECK (status IN ('NEW', 'PAID', 'SHIPPED', 'CANCELLED')),

    CONSTRAINT orders_lab_quantity_ck
      CHECK (quantity > 0),

    CONSTRAINT orders_lab_price_ck
      CHECK (unit_price >= 0),

    CONSTRAINT orders_lab_discount_ck
      CHECK (discount_pct BETWEEN 0 AND 100),

    CONSTRAINT orders_lab_period_ck
      CHECK (valid_to IS NULL
             OR (valid_from IS NOT NULL AND valid_to >= valid_from)),

    CONSTRAINT orders_lab_cancel_ck
      CHECK (status <> 'CANCELLED'
             OR TRIM(cancel_reason) IS NOT NULL)
);
```

**Note:** This is a lab schema for learning constraints, not a full e-commerce model. Pricing/discounts also involve currency, tax, units, precision, foreign keys, inventory checks, payment transactions, and concurrency handled separately.

### 7.1. Valid Row Without `discount_pct`

```sql
INSERT INTO orders_check_lab (
    order_id, order_code, quantity, unit_price, valid_from
) VALUES (
    1, 'ORD-001', 2, 125000,
    DATE '2026-01-01'
);

-- STATUS uses DEFAULT 'NEW'.
-- DISCOUNT_PCT and VALID_TO are allowed to be NULL.
SELECT order_id, status, quantity, unit_price, discount_pct
FROM   orders_check_lab
WHERE  order_id = 1;
```

### 7.2. Invalid Rows: Cases Expected to Fail

**Each INSERT below is an independent test; run them one by one.** They illustrate errors, not a migration script meant to run cleanly end-to-end.

```sql
-- quantity = 0: CHECK (quantity > 0) → FALSE.
INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price)
VALUES (2, 'ORD-002', 'NEW', 0, 100);
-- Expected: ORA-02290, constraint ORDERS_LAB_QUANTITY_CK.

-- quantity NULL: NOT NULL violated.
INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price)
VALUES (3, 'ORD-003', 'NEW', NULL, 100);
-- Expected: ORA-01400, cannot insert NULL.

-- Status outside allowed set.
INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price)
VALUES (4, 'ORD-004', 'UNKNOWN', 1, 100);
-- Expected: ORA-02290, constraint ORDERS_LAB_STATUS_CK.

-- CANCELLED with whitespace-only reason.
INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price, cancel_reason)
VALUES (5, 'ORD-005', 'CANCELLED', 1, 100, '   ');
-- Expected: ORA-02290, constraint ORDERS_LAB_CANCEL_CK.

-- valid_to provided without valid_from.
INSERT INTO orders_check_lab
    (order_id, order_code, quantity, unit_price, valid_to)
VALUES (6, 'ORD-006', 1, 100, DATE '2026-02-01');
-- Expected: ORA-02290, constraint ORDERS_LAB_PERIOD_CK.
```

When an `INSERT` violates a standard **NOT DEFERRABLE** constraint, **that statement** rolls back—it does not automatically roll back earlier statements that succeeded in the same transaction. When deferring a constraint to commit, rollback semantics differ, as covered later.

### 7.3. Valid Row When CANCELLED Has a Reason

```sql
INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price, cancel_reason)
VALUES (7, 'ORD-007', 'CANCELLED', 1, 100, 'Customer requested cancellation');

SELECT order_id, status, cancel_reason
FROM   orders_check_lab
WHERE  order_id = 7;
```

To roll back test rows within the same transaction, run `ROLLBACK` before ending the lab. `CREATE TABLE` is DDL with an implicit commit; `ROLLBACK` does not drop created tables.

## 8. How Far Can CHECK Go? Limits of Declarative SQL

Oracle 19c restricts CHECK expressions to conditions evaluable on **the row currently being INSERTed or UPDATEd**. Standard CHECK constraints cannot arbitrarily read other rows or other tables.

| Requirement | Directly Possible with CHECK? | Alternative or Complementary Design |
| --- | --- | --- |
| `amount >= 0` on a row | **Yes** | CHECK + NOT NULL if mandatory |
| `end_date >= start_date` on same row | **Yes** | Table-level CHECK |
| `status IN (...)` | **Yes** | CHECK or lookup table + FK |
| Forbid NULL in a column | **Yes**, using `NOT NULL` | Avoid standalone CHECK if only non-nullability is needed |
| `email LIKE ...` basic format | **Yes**, within expression limits | Does not prove email exists |
| `orders.customer_id` must exist in `customers` | **No** with CHECK | **FOREIGN KEY** |
| Product code unique across rows | **No** with CHECK | **UNIQUE** or PK |
| Total ordered quantity of a product ≤ stock | **No** with single-row CHECK | Transactions, row locks, conditional updates; proper ledger/counter design |
| No overlapping booking intervals for the same room | **No** with plain CHECK | Concurrency design, locking/serialization, and overlap queries |
| Group allocation percentages sum to 100 | **No** with per-row CHECK | Transactional aggregation logic or alternative data model |
| `created_at <= SYSDATE` | **No** in Oracle 19c CHECK | Validate at write time via supported logic; enforce timestamp via workflow |
| Validate country name via user-defined function | **No** in 19c CHECK | Lookup table + FK or business logic |

### 8.1. Expressions Forbidden in Oracle 19c CHECK Constraints

Per the **SQL Language Reference** and **Database Development Guide**:

- **Subqueries** or scalar subqueries; you cannot `SELECT` from other tables inside the condition.
- **Sequences** and pseudocolumns `CURRVAL`, `NEXTVAL`; you cannot base a rule on the next sequence value.
- Non-deterministic context/time functions such as `SYSDATE`, `SYSTIMESTAMP`, `CURRENT_DATE`, `CURRENT_TIMESTAMP`, `UID`, `USER`, and `USERENV`, along with other functions listed in release restrictions.
- **User-defined functions** (even when marked `DETERMINISTIC`).
- Pseudocolumns `ROWNUM`, `LEVEL`, and the `PRIOR` operator.
- Certain specialized object/`REF`/nested-table attribute references, as well as under-specified date constant expressions.
- Table CHECK constraints cannot be placed on regular **views**; `WITH CHECK OPTION` on a view is a different mechanism. Specialized table types such as external tables have their own restrictions.

**Invalid** examples:

```sql
-- Invalid: CHECK cannot query another table.
CONSTRAINT fk_by_check_bad
CHECK (customer_id IN (SELECT id FROM customers))

-- Invalid: SYSDATE changes over time.
CONSTRAINT created_before_now_bad
CHECK (created_at <= SYSDATE)

-- Invalid: user-defined function in CHECK (Oracle 19c).
CONSTRAINT valid_code_fn_bad
CHECK (my_package.is_valid_code(code) = 1)
```

**Why do these restrictions exist?** A CHECK constraint is a contract requiring a stable result evaluable immediately from a single row; allowing arbitrary dependencies on other tables, current wall-clock time, or side-effecting functions would break consistency, independent row evaluation, and concurrency.

### 8.2. "Must Not Exceed Stock" Is a Scope-Mismatch Example

Suppose `inventory.stock = 10` and there are multiple `order_items.qty` rows. `CHECK (qty <= 10)` on each row does not stop **two orders of 8 items each**, totaling 16. The desired condition is an invariant **spanning multiple rows and inventory state**.

An inventory protection pattern might:

1. Execute a **conditional** stock update in a transaction: `UPDATE inventory SET available = available - :qty WHERE sku = :sku AND available >= :qty`.
2. Check the updated row count to determine success/failure.
3. In the same transaction, create the order item; commit or roll back together.
4. Keep `CHECK (available >= 0)` on inventory **as a row-level safety net**, without mistaking it for the entire allocation mechanism.

Conditional SQL updates with row locks prevent common race conditions, while full inventory correctness depends on returns, cancellations, reservations, and idempotency workflows.

### 8.3. Multi-Row or Multi-Table Rules Are Not Easily Patched with Triggers

Triggers can run more complex checks than CHECK, but you must watch out for:

- **Mutating table** errors (`ORA-04091`) when certain triggers query the table currently being modified.
- **Concurrency/race conditions**: two sessions can simultaneously read a valid state and both write a logical violation without locking/serialization.
- Row triggers, statement triggers, and compound triggers differ in execution timing and constraints.
- Privileges, error handling, recursive DML, and operational cost.

Prefer PK, UNIQUE, FK, CHECK, and NOT NULL whenever logic can be expressed declaratively. If you must use triggers or stored procedures, prove correctness **under concurrency**, not only in single-session tests.

## 9. Behavior When DML Violates a Constraint

### 9.1. Default Constraints Check at Statement End

In Oracle 19c, **`NOT DEFERRABLE`** is the default; constraints are checked during statement execution under Oracle semantics, reporting errors at the statement boundary. An `INSERT`/`UPDATE` causing a violating row causes **that statement to roll back** and raises an error.

```text
Transaction T
  │
  ├─ INSERT valid row A          → succeeds, still uncommitted
  │
  ├─ INSERT row B quantity = -5 → ORA-02290
  │                               statement B rolls back
  │
  ├─ SELECT checks row A        → A is still in the transaction
  │
  └─ COMMIT                     → persists row A if no other error occurs
```

Never write applications assuming a constraint error "automatically cancels all prior work in the transaction." Rollback scope is **statement-level** vs. **transaction-level** (especially with deferred constraints or other errors). The application must explicitly roll back the transaction in error handling according to business atomicity requirements.

### 9.2. Common Errors

| Error Code | Typical Scenario | Example |
| --- | --- | --- |
| `ORA-02290` | Check constraint violated | `CHECK (quantity > 0)` receives 0 or negative |
| `ORA-01400` | Cannot INSERT NULL into NOT NULL column | `INSERT ... email = NULL` |
| `ORA-01407` | Cannot UPDATE NOT NULL column to NULL | `UPDATE ... SET email = NULL` |
| `ORA-02293` | Cannot validate constraint because existing rows violate it | `ENABLE VALIDATE` with invalid rows present |
| `ORA-02296` | Cannot enable NOT NULL because NULLs exist | `ALTER TABLE ... MODIFY ... NOT NULL` |
| `ORA-02291` | Foreign key missing parent row | **FK**, not CHECK |
| `ORA-00001` | Unique constraint/index violated | **UNIQUE/PK**, not CHECK |

Exact error text may vary by release and context; rely on the **error code, constraint name**, and database metadata rather than guessing from application-translated messages.

### 9.3. When Multiple CHECK Constraints Are Violated Together

Oracle makes no guarantee about evaluation order across CHECK constraints. A single row might violate `quantity`, `discount`, and `status` simultaneously, yet the returned error reports only **one** constraint for that DML call. Never rely on constraint order to drive business error messages; applications can pre-validate all fields to return a friendly error list while the database enforces invariants underneath.

## 10. DEFERRABLE: Check at Statement End or at COMMIT?

**Deferrability** is orthogonal to `ENABLE/NOVALIDATE`:

- **`NOT DEFERRABLE` (default):** checking cannot be postponed to COMMIT; validated at statement time.
- **`DEFERRABLE INITIALLY IMMEDIATE`:** defaults to checking after each statement, but a transaction can run `SET CONSTRAINTS ... DEFERRED`.
- **`DEFERRABLE INITIALLY DEFERRED`:** defaults to checking at COMMIT, though a transaction can switch to `IMMEDIATE` via `SET CONSTRAINTS`.

Oracle 19c **supports deferrable NOT NULL constraints** when declared as such, alongside CHECK and certain other constraint types. Do not conclude that NOT NULL can never be deferred just because typical examples check immediately.

### 10.1. Lab Illustrating Deferred CHECK Evaluation

```sql
CREATE TABLE defer_check_lab (
    id     NUMBER PRIMARY KEY,
    amount NUMBER,
    CONSTRAINT defer_amount_ck
      CHECK (amount >= 0)
      DEFERRABLE INITIALLY DEFERRED
);

-- First statement in transaction temporarily creates a row violating CHECK:
INSERT INTO defer_check_lab (id, amount) VALUES (1, -10);

-- Fix before COMMIT so the final transaction state is valid:
UPDATE defer_check_lab
SET    amount = 10
WHERE  id = 1;

COMMIT; -- Succeeds because the final state satisfies CHECK.
```

If you leave `amount = -10` and call `COMMIT`, Oracle detects the violation at commit time and **the transaction is not committed**; under deferred constraint behavior, the transaction rolls back when commit fails due to the constraint. Thus, **temporary DML success does not mean the transaction was accepted**.

Within a transaction using deferrable constraints:

```sql
-- Set all deferrable constraints to deferred for this transaction.
SET CONSTRAINTS ALL DEFERRED;

-- Check all deferrable constraints right now,
-- before actually calling COMMIT.
SET CONSTRAINTS ALL IMMEDIATE;
```

`SET CONSTRAINTS` affects checking mode **only for the current transaction**; it does not permanently alter the `INITIALLY` definition. Do not call `SET CONSTRAINTS` casually inside triggers; Oracle restricts that statement there.

### 10.2. Deferrability Is a Design-Time Property

Oracle does not let you convert a constraint from `NOT DEFERRABLE` to `DEFERRABLE` via `MODIFY` after creation; normally you must **drop and re-create** the constraint under controlled change management. Decide this at table-design time. Most rules like `quantity > 0` and `status IN (...)` should remain `NOT DEFERRABLE`; use deferred checking only when legitimate workflows require temporary intermediate states within a transaction.

**Never use deferred constraints to legitimize invalid data at the end of a transaction.** They only permit **temporary intermediate violations**, never committed violations.

## 11. ENABLE/DISABLE and VALIDATE/NOVALIDATE States

Constraints in Oracle also have two key dimensions:

1. **`ENABLED` vs. `DISABLED`:** does it check future DML?
2. **`VALIDATED` vs. `NOT VALIDATED`:** to what extent has Oracle verified existing rows against the constraint?

| State | DML After Setting State | Existing Data | Purpose & Notes |
| --- | --- | --- | --- |
| **`ENABLE VALIDATE`** | Must comply | Verified compliant | Strongest normal integrity state |
| **`ENABLE NOVALIDATE`** | New DML and modified rows must comply | May still contain older violating rows | Useful when phasing constraints onto legacy data |
| **`DISABLE NOVALIDATE`** | Constraint not enforced | Not guaranteed compliant | Accepts risk of invalid new data; requires strict operational control |
| **`DISABLE VALIDATE`** | Constraint disabled; restricts DML on constrained columns | Marked validated | Specialized admin/data-warehouse mode, not a "normal disable" |

**Most common pitfall:** `ENABLE NOVALIDATE` **does not mean the database passively watches without blocking new DML**. It actively checks rows touched after enabling, even though older rows may remain uncleaned.

### 11.1. What Happens to Existing Violating Rows?

Suppose `legacy_orders` already holds a row with `quantity = -3`. The DBA adds:

```sql
ALTER TABLE legacy_orders
  ADD CONSTRAINT legacy_qty_ck
  CHECK (quantity > 0)
  ENABLE NOVALIDATE;
```

The constraint enforces rules on subsequent DML, yet **the existing `-3` row stays in the table**. To reach `ENABLE VALIDATE`, the DBA must fix/remove violating rows or execute data remediation; never claim all table rows are clean merely because the constraint is `ENABLED`.

### 11.2. `RELY` Does Not Prove Real Data Compliance

`RELY`/`NORELY` controls whether the optimizer/query rewrite **trusts certain constraints in NOVALIDATE state** under supported integrity modes. It **does not clean violating rows** and **does not mean the constraint was enforced across all historical rows**.

If you mark a false assumption as reliable and allow query rewrite to depend on it, query results can become logically wrong. Only enable `RELY` under policies with verified data, semantics, and environment controls.

## 12. Adding CHECK to a Legacy Table Without Blocking Rollout

Suppose an existing table has millions of rows and some historical `amount < 0` rows. The goal is "block new bad writes immediately" while "remediating historical rows in batches."

### Step A — Audit Data Before Changing DDL

```sql
-- Read-only; if amount must be NOT NULL, count NULLs separately.
SELECT COUNT(*) AS negative_amount_rows
FROM   legacy_orders
WHERE  amount < 0;

SELECT COUNT(*) AS null_amount_rows
FROM   legacy_orders
WHERE  amount IS NULL;

SELECT order_id, amount
FROM   legacy_orders
WHERE  amount < 0
ORDER BY order_id
FETCH FIRST 50 ROWS ONLY;
```

**Do not use `WHERE NOT (amount >= 0)` to find all violating rows if you also want to catch NULLs**: `NOT (NULL >= 0)` is still UNKNOWN, and `WHERE` only returns TRUE rows. Check NULLs separately if non-nullability is part of the requirement.

### Step B — Enable the Constraint for New Data

```sql
-- Run only after change approval; this is real DDL.
ALTER TABLE legacy_orders
  ADD CONSTRAINT legacy_amount_ck
  CHECK (amount >= 0)
  ENABLE NOVALIDATE;
```

From this point forward, new DML cannot introduce `amount < 0` on checked rows. However, if `amount` remains nullable, CHECK **does not block NULL**. Do not claim "all new rows have valid amounts" until the full rule set is enforced.

### Step C — Remediate Legacy Data According to Business Rules

Handling options:

- Classify whether negative rows are valid refunds or input errors; if valid refunds, **update the business model** instead of forcing values to 0.
- If rows are genuinely wrong, determine corrected values from verified source records.
- Run controlled batch updates with proper transactions, logging, privileges, and row-count checks.
- If an existing violating row is updated, Oracle will require the updated row to satisfy CHECK; do not assume you can modify an unrelated column while leaving the violating value untouched.

Once violations drop to 0:

```sql
SELECT COUNT(*) AS remaining_invalid_rows
FROM   legacy_orders
WHERE  amount < 0;

-- After checking impact and dependencies:
ALTER TABLE legacy_orders
  MODIFY CONSTRAINT legacy_amount_ck ENABLE VALIDATE;
```

`ENABLE VALIDATE` gives a stronger guarantee because Oracle verifies all relevant rows satisfy the constraint. On large tables, validation consumes I/O and CPU and affects deployment duration, so schedule it within an appropriate change window.

### Step D — Enforce NULLs Separately If Required by the New Rule

```sql
-- Inspect missing values:
SELECT COUNT(*) FROM legacy_orders WHERE amount IS NULL;

-- After handling NULLs and approving the change:
ALTER TABLE legacy_orders
  MODIFY (amount CONSTRAINT legacy_amount_nn NOT NULL);
```

Do not add `NOT NULL` while unresolved NULL rows remain if you expect VALIDATE to succeed. Also, adding a default will not automatically backfill existing NULL rows without an appropriate data step.

**The statements in this section assume `LEGACY_ORDERS` and the corresponding column names exist in your schema.** They are workflow templates, not production change scripts pre-tested against a specific schema.

## 13. Metadata: Auditing CHECK, NOT NULL, and Enforcement States

Oracle records constraint details in the data dictionary. For the current schema:

```sql
SELECT constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred,
       rely,
       search_condition_vc
FROM   user_constraints
WHERE  table_name = 'ORDERS_CHECK_LAB'
ORDER BY constraint_name;
```

**Column reference:**

| Column | Meaning |
| --- | --- |
| `CONSTRAINT_NAME` | Explicit name like `ORDERS_LAB_STATUS_CK` or Oracle-generated `SYS_C...` |
| `CONSTRAINT_TYPE` | `C` for CHECK and NOT NULL; `P` for PK; `U` for UNIQUE; `R` for FK |
| `STATUS` | `ENABLED` / `DISABLED` |
| `VALIDATED` | `VALIDATED` / `NOT VALIDATED` |
| `DEFERRABLE` | `DEFERRABLE` / `NOT DEFERRABLE` |
| `DEFERRED` | Default checking mode `IMMEDIATE` / `DEFERRED` |
| `RELY` | Metadata for query rewrite / integrity assumptions |
| `SEARCH_CONDITION_VC` | CHECK expression as VARCHAR2 for quick inspection |

In Oracle 19c, `SEARCH_CONDITION_VC` is convenient in SQL clients, yet can be **truncated** for long expressions; `SEARCH_CONDITION` is a `LONG` column with SQL manipulation limits. When you need the complete, untruncated definition, use `DBMS_METADATA` or metadata tooling rather than relying on a truncated preview column.

### 13.1. Which Columns Participate in a Constraint?

```sql
SELECT c.constraint_name,
       c.constraint_type,
       cc.position,
       cc.column_name
FROM   user_constraints c
JOIN   user_cons_columns cc
       ON cc.constraint_name = c.constraint_name
      AND cc.table_name      = c.table_name
WHERE  c.table_name = 'ORDERS_CHECK_LAB'
ORDER BY c.constraint_name, cc.position;
```

Not every constraint binds to a **single column**. An out-of-line CHECK like `valid_to >= valid_from` references multiple columns; when writing audit scripts, do not grab only the first row in `USER_CONS_COLUMNS` and assume it represents the entire expression.

### 13.2. `USER_TAB_COLUMNS.NULLABLE` vs. CHECK Metadata

```sql
SELECT column_name,
       data_type,
       nullable,
       data_default
FROM   user_tab_columns
WHERE  table_name = 'ORDERS_CHECK_LAB'
ORDER BY column_id;
```

`NULLABLE = 'N'` generally indicates Oracle has active nullability metadata enforced for the column, though exact interpretation depends on constraint state and column type. For compliance audits, inspect **both `USER_TAB_COLUMNS` and `USER_CONSTRAINTS`** instead of checking `NULLABLE` alone and assuming `ENABLE VALIDATE`.

### 13.3. Viewing Normalized DDL via `DBMS_METADATA`

```sql
-- SQL*Plus / SQLcl: configure CLOB display length.
SET LONG 200000
SET PAGESIZE 0

SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS_CHECK_LAB')
FROM   dual;
```

The DDL displays `NOT NULL`/`CHECK` declarations and constraint states per transform settings; physical storage clauses may also appear. If your tool only shows the beginning of the CLOB, do not conclude constraints are missing. Reading metadata from another schema requires appropriate privileges.

### 13.4. CDB/PDB: Verify the Container Before Reading

In Oracle Multitenant, the same table name `ORDERS_CHECK_LAB` can exist in two different PDBs. Check:

```sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS service_name
FROM   dual;
```

`USER_CONSTRAINTS` and `DBMS_METADATA.GET_DDL` operate within the **current PDB/session** and privilege scope. Never mix constraint DDL from `PDB_A` with data/metadata from `PDB_B` when auditing two tenants.

## 14. Using Constraints Effectively and Maintainably

### 14.1. Constraint Names Should Reflect a Rule

Use consistent naming, such as:

- `orders_quantity_nn`: quantity is mandatory.
- `orders_quantity_pos_ck`: quantity > 0.
- `orders_status_domain_ck`: status within allowed domain.
- `orders_dates_order_ck`: date ordering.
- `orders_cancel_reason_ck`: cancelled requires a reason.

Names like `CHECK1` or `SYS_C012345` give operations teams no clue about the failing rule. Oracle enforces identifier length limits per release/compatibility; keep names clear, concise, and free of sensitive data.

### 14.2. Matching Constraints to the Right Defense Layer

```text
Rule: "quantity must be positive"
  └─ CHECK(quantity > 0) + NOT NULL

Rule: "customer_id must exist in customers"
  └─ FOREIGN KEY, not a CHECK subquery

Rule: "email must be unique"
  └─ UNIQUE (plus NOT NULL if required by business)

Rule: "total ordered quantity <= stock"
  └─ Transaction/locking + row invariants

Rule: "created timestamp must not be in the future at insertion"
  └─ Application/DB procedure/trigger at write time;
     SYSDATE is invalid in 19c CHECK

Rule: "percentage valid only if supplied"
  └─ CHECK(pct BETWEEN 0 AND 100), allowing NULL by design
```

A constraint is only good if it expresses the **exact rule**, not merely enough to make `CREATE TABLE` run.

### 14.3. Concurrency and Transaction Consistency

Oracle enforces CHECK on modified rows alongside its transaction and locking mechanisms. If two sessions update **the same row**, row locks and atomic updates prevent certain race conditions. Yet CHECK cannot know row counts across a group, overlapping bookings, or external system state.

For example, `CHECK (balance >= 0)` on each account prevents negative balances after an update, but **does not** replace a two-account transfer transaction design that preserves total funds, handles uncertain commit timeouts, or prevents double-spending at the transaction level.

### 14.4. Performance and Query Optimizer

- Simple CHECK constraints have negligible cost relative to business logic, though millions of DMLs with heavy expressions still create measurable overhead.
- CHECK **does not create indexes automatically**. Indexing is a separate query-access decision, and indexes back other constraints (PK/UNIQUE) per Oracle rules.
- Validated constraint metadata can help the optimizer reason in supported scenarios. Never mark `RELY` when data integrity is unverified.
- DML blocked by CHECK triggers a statement error/rollback, without automatically guaranteeing the application rolled back the whole transaction.
- `DISABLE` or `NOVALIDATE` can assist maintenance windows, provided a concrete plan exists to re-verify data quality afterward.

### 14.5. Never Remove Constraints Just Because the Application Validates

Applications can miss batch loads, SQL consoles, ETL pipelines, or legacy client versions; DB constraints are the "last line of defense" for declaratively expressible invariants. If dirty data must be ingested for further processing, use a **dedicated staging table** or controlled intermediate state rather than disabling constraints on core business tables.

## 15. DDL and Migrations: Watch Out for Implicit COMMIT

`CREATE TABLE`, `ALTER TABLE`, and `DROP TABLE` are DDL in Oracle and carry **implicit commit** semantics. Therefore:

1. Never bundle DML remediation with `ALTER TABLE` expecting `ROLLBACK` to undo the `ALTER TABLE`.
2. Back up/snapshot metadata and prepare forward-fix or DDL/DML rollback plans rather than relying on `ROLLBACK`.
3. Test `ENABLE VALIDATE` against staging data volumes matching production scale and peak traffic.
4. Applications should catch constraint errors with friendly messaging without swallowing ORA error details in logs.
5. Schema migration frameworks must specify intentional constraint and column names; never hard-code assumptions about `SYS_C...` names.

Deploying "add NOT NULL to a new column" sometimes requires **expand–backfill–constrain**:

```text
1. Add nullable column (expand schema)
2. Deploy application capable of writing the new column
3. Backfill valid values for existing rows
4. Audit remaining NULLs and violations
5. Enforce NOT NULL / CHECK with proper validation
6. Remove backward-compatibility code once safe
```

Exact steps depend on zero-downtime needs, Oracle release, DDL locking behavior, partitioning, and data volume. Never promise an `ALTER TABLE` is lock-free or "online" merely because the constraint looks simple.

## 16. Safe Session-by-Session Practice Lab

> Run only in a lab schema with appropriate privileges. Deliberately invalid DML statements return ORA errors for demonstration. If SQL*Plus uses `WHENEVER SQLERROR EXIT`, run failing test statements individually; never bundle failing statements into deployment scripts.

### Part A — Inspect Created Constraint States

```sql
SELECT constraint_name,
       constraint_type,
       status,
       validated,
       search_condition_vc
FROM   user_constraints
WHERE  table_name = 'ORDERS_CHECK_LAB'
ORDER BY constraint_name;
```

Expected: several `C` constraints and one PK `P`; `NOT NULL` constraints also appear under `C`.

### Part B — Use SAVEPOINT to Test DML

```sql
SAVEPOINT before_constraint_lab;

INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price)
VALUES (101, 'LAB-101', 'NEW', 1, 1000);

-- Deliberately invalid, run separately:
INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price)
VALUES (102, 'LAB-102', 'NEW', -1, 1000);
-- Expected ORA-02290.

SELECT order_id, quantity
FROM   orders_check_lab
WHERE  order_id IN (101, 102)
ORDER BY order_id;

ROLLBACK TO before_constraint_lab;
```

After row 102 fails, row 101 remains in the transaction until rolling back to the savepoint. This demonstrates **statement-level** rollback for non-deferrable constraints, rather than whole-transaction rollback.

### Part C — Observe Whether NULL Passes CHECK

```sql
-- DISCOUNT_PCT lacks NOT NULL, so NULL is allowed.
SAVEPOINT before_null_lab;

INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price, discount_pct)
VALUES (103, 'LAB-103', 'NEW', 1, 1000, NULL);

SELECT order_id, discount_pct
FROM   orders_check_lab
WHERE  order_id = 103;

ROLLBACK TO before_null_lab;
```

Do not explain this as "CHECK `BETWEEN 0 AND 100` validated discount 0–100 for row 103": in truth, **UNKNOWN was accepted**, and the design intentionally allowed the field to be optional.

### Part D — Observe Errors on Non-NULL Whitespace-Only Values

```sql
-- Run separately; expected to violate ORDERS_LAB_CODE_CK.
INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price)
VALUES (104, '   ', 'NEW', 1, 1000);
```

`NOT NULL` on `ORDER_CODE` alone does not reject whitespace-only strings; `CHECK (TRIM(order_code) IS NOT NULL)` enforces the "meaningful content" rule.

### Part E — Observe Deferred Errors Only at COMMIT (Optional)

Run after understanding transaction effects and **on the separate lab table `DEFER_CHECK_LAB`** from Section 10. This is the easiest step to misunderstand:

```sql
-- Constraint is DEFERRABLE INITIALLY DEFERRED.
INSERT INTO defer_check_lab (id, amount) VALUES (2, -100);

-- Temporarily update so the final transaction state is valid.
UPDATE defer_check_lab SET amount = 100 WHERE id = 2;
COMMIT;
```

Without the `UPDATE`, `COMMIT` fails and the associated transaction rolls back. Never use deferred constraints to hide invalid data or "soften" post-commit integrity.

### Part F — Clean Up Lab Objects

The commands below **drop tables and perform an implicit commit**; run them only once you are certain these are newly created lab tables with no data worth keeping:

```sql
DROP TABLE orders_check_lab PURGE;
DROP TABLE defer_check_lab PURGE;
```

If demo tables such as `score_demo`, `score_required_demo`, `product_demo`, `customer_contact_demo`, etc., were also created in your lab schema, clean up each named object individually after confirming ownership; **never** run an unchecked bulk DROP script.

## 17. Real-World Scenarios and Root-Cause Analysis

### Scenario 1 — Column Has CHECK Yet Still Contains NULL

**Symptom:** A DBA sees `CHECK (score BETWEEN 0 AND 100)` alongside rows with `score IS NULL`.

**Explanation:** CHECK permits UNKNOWN. Verify whether `NOT NULL` exists and whether the application intentionally permits "not entered yet." If mandatory, clean existing NULLs before validating and adding `NOT NULL`.

### Scenario 2 — Column Has NOT NULL Yet Customer Name Is All Spaces

**Symptom:** `NAME = '   '` is not blocked.

**Explanation:** NOT NULL only forbids NULL. Add `CHECK (TRIM(name) IS NOT NULL)` for VARCHAR2 columns, while defining normalization and policies for Unicode whitespace and external input formatting. Default `TRIM` does not strip all Unicode whitespace characters; if stricter rules are required, validate according to character set and requirements.

### Scenario 3 — New Order Status Appears Missing from CHECK

**Symptom:** Application deploys status `REFUNDED`, and inserts fail with `ORA-02290`.

**Explanation:** The domain CHECK was not migrated alongside the application. Coordinate releases: update the constraint via migration, or move to a lookup table if the domain changes frequently and carries metadata. Never permanently disable the constraint just to let the app "get through."

### Scenario 4 — SELECT Finding Invalid Rows Returns Empty, Yet VALIDATE Fails

**Symptom:** A DBA runs `WHERE NOT (col > 0)`, sees zero rows, yet adding `col > 0` combined with a NOT NULL requirement fails.

**Explanation:** `NULL` was skipped because `NOT UNKNOWN = UNKNOWN`, so `WHERE` excluded those rows. Query `col IS NULL` separately. Also verify exact expressions, type conversions, collations, concurrent writes, and constraint state.

### Scenario 5 — ENABLE NOVALIDATE Still Shows Negative Numbers

**Symptom:** After enabling, queries still find `amount=-3`.

**Explanation:** The row existed prior to enabling. `ENABLE NOVALIDATE` validates subsequent DML, not historical rows. Upgrade to `ENABLE VALIDATE` only after remediation finishes.

### Scenario 6 — Trigger Checks Group Sum Yet Fails Under Load

**Symptom:** Sequential tests pass, while two concurrent transactions push a group's sum past the limit.

**Explanation:** Read-then-write sum checks without proper locking/serialization suffer from race conditions. CHECK cannot enforce multi-row invariants, and triggers do not automatically ensure concurrency correctness. Redesign transactions and data access patterns.

### Scenario 7 — DML Succeeds Yet COMMIT Fails

**Symptom:** Code uses a `DEFERRABLE INITIALLY DEFERRED` constraint; multiple INSERTs succeed, then COMMIT rolls back due to CHECK.

**Explanation:** Deferred constraints are evaluated at COMMIT. The application must handle errors at the **commit boundary**, not only catch ORA codes on individual INSERTs.

## 18. Self-Check Questions

**Question 1.** A table has `CHECK (age >= 18)` without NOT NULL. Is `age = NULL` accepted?

**Question 2.** Why might `CHECK (LENGTH(TRIM(code)) > 0)` fail to block whitespace-only strings in Oracle?

**Question 3.** An order requires `cancel_reason` to have content whenever `status = 'CANCELLED'`. How should the expression be written, and which column needs NOT NULL?

**Question 4.** Can you write `CHECK (customer_id IN (SELECT id FROM customers))` instead of a FOREIGN KEY?

**Question 5.** How does `ENABLE NOVALIDATE` differ from `ENABLE VALIDATE` for existing data?

**Question 6.** With `DEFERRABLE INITIALLY DEFERRED`, why can an INSERT violating CHECK temporarily succeed while COMMIT fails?

**Question 7.** Does `CONSTRAINT_TYPE='C'` in `USER_CONSTRAINTS` mean every row is a business CHECK constraint?

**Question 8.** Why is `CHECK (balance >= 0)` alone insufficient to implement safe transfers between two accounts?

**Question 9.** A table has `NOT NULL` on a `VARCHAR2` column. Are `''` and `'   '` handled identically?

**Question 10.** When adding a constraint to a table with legacy data, what phases ensure existing violations are not overlooked?

<details>
<summary>Answer Key</summary>

1. **Yes.** `NULL >= 18` evaluates to UNKNOWN, and CHECK only rejects FALSE. Add NOT NULL to make input mandatory.
2. `TRIM('   ')` becomes an empty string, which Oracle treats as NULL; `LENGTH(NULL) > 0` returns UNKNOWN, so CHECK accepts it. Use `TRIM(code) IS NOT NULL` and add NOT NULL on the column.
3. `CHECK (status <> 'CANCELLED' OR TRIM(cancel_reason) IS NOT NULL)`, paired with `status NOT NULL` and a status-domain constraint.
4. **No.** CHECK forbids subqueries and querying other tables. Use a FOREIGN KEY.
5. `ENABLE NOVALIDATE` blocks invalid new DML and updated rows while allowing existing legacy violations to remain; `ENABLE VALIDATE` verifies and guarantees all existing rows comply.
6. Oracle postpones validation until transaction end. The final state must be valid; otherwise COMMIT fails and the transaction rolls back.
7. **No.** Oracle represents NOT NULL constraints under type `C` as well; check `SEARCH_CONDITION` and column metadata.
8. You still need atomicity across both UPDATEs, conservation of total balance, network/commit error handling, double-spend prevention, concurrency control, and proper ledger design.
9. No. `''` is typically treated as NULL by Oracle and blocked by NOT NULL; `'   '` is non-NULL and can be stored.
10. Audit/define rules → enable `ENABLE NOVALIDATE` if appropriate to block new bad data → clean/reconcile old rows → switch to `ENABLE VALIDATE` → verify dictionary state.

</details>

## 19. Concluding Principles

- **CHECK protects single-row conditions**, not database-wide conditions.
- **Only `FALSE` fails CHECK; `UNKNOWN` from NULL still passes.** When a value is mandatory, use `NOT NULL` and define NULL semantics explicitly.
- **NOT NULL does not mean "meaningful content"**; whitespace and placeholder strings may need an additional CHECK.
- **You can compare multiple columns in the same row**, but cannot reference other tables, subqueries, user-defined functions, or current time in Oracle 19c CHECK constraints.
- **Constraints have enforcement states and checking timing**: `ENABLE/DISABLE`, `VALIDATE/NOVALIDATE`, and `DEFERRABLE` are distinct dimensions.
- **Legacy data under NOVALIDATE is not proven clean.** Full guarantees require cleaning backlog violations and switching to VALIDATE.
- **Use PK/UNIQUE/FK for key and cross-table invariants**, and controlled transactions for aggregate/concurrency invariants.
- **Inspect live metadata** via `USER_CONSTRAINTS`, `USER_CONS_COLUMNS`, `USER_TAB_COLUMNS`, and `DBMS_METADATA` instead of trusting only old DDL scripts in Git.

## 20. Official Oracle Documentation

1. [Oracle Database 19c SQL Language Reference — `constraint`](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/constraint.html): syntax for `NOT NULL`, `CHECK`, prohibited conditions, `DEFERRABLE`, `ENABLE`/`VALIDATE`/`RELY`, and examples.
2. [Oracle Database 19c Database Development Guide — Maintaining Data Integrity in Database Applications](https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/data-integrity.html): CHECK design, three-valued logic (TRUE/FALSE/UNKNOWN), and row-level limits.
3. [Oracle Database 19c Concepts — Data Integrity](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-integrity.html): constraint types, enforcement/validation states, and immediate/deferred handling.
4. [Oracle Database 19c Administrator's Guide — Managing Schema Objects](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-schema-objects.html): adding, modifying, enabling, disabling, validating, and handling exceptions on existing data.
5. [Oracle Database 19c SQL Language Reference — `CREATE TABLE`](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html), [`ALTER TABLE`](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): creating and altering constraints in DDL.
6. [Oracle Database 19c SQL Language Reference — `SET CONSTRAINTS`](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SET-CONSTRAINTS.html): switching deferrable constraint checking mode within a transaction.
7. [Oracle Database 19c Database Reference — `USER_CONSTRAINTS`](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_CONSTRAINTS.html), [`ALL_CONSTRAINTS`](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_CONSTRAINTS.html), [`USER_CONS_COLUMNS`](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_CONS_COLUMNS.html): reading constraint metadata.
8. [Oracle Database 19c PL/SQL Packages and Types Reference — `DBMS_METADATA`](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_METADATA.html): exporting DDL to verify constraints against the live schema.

**Decision chain to remember:** state the invariant precisely → choose scope (single column / single row / key / multi-row) → handle NULL and three-valued logic → select NOT NULL/CHECK/PK/UNIQUE/FK or transaction logic → choose enforcement timing and validation state → verify metadata and data before deployment.
