# NULL in UNIQUE, CHECK, and Composite Key Constraints

## 1. Why Does `NULL` Change How Constraints Behave?

In an Oracle Database system, a customer table may have an undeclared email, an order may have an unknown completion date, or a partner identifier may arrive only after synchronization. Those missing values are typically represented with **`NULL`**.

SQL newcomers often predict two behaviors incorrectly:

- "A column with `UNIQUE` cannot hold two `NULL` rows."
- "A `CHECK (amount > 0)` constraint rejects `NULL`, because `NULL` is not greater than 0."

In Oracle, **neither statement is true under standard usage**. A single-column `UNIQUE` constraint allows multiple `NULL` rows, while `CHECK` rejects only expressions evaluating to **`FALSE`**; expressions evaluating to **`UNKNOWN`** due to `NULL` generally still pass the constraint.

With **composite keys** spanning multiple columns, the rules are even subtler: `UNIQUE (a, b)` does not follow a simplistic rule like "whenever any `NULL` is present, rows can repeat freely." Oracle behaves differently when **all components are NULL** versus when **only some components are NULL**.

This lesson belongs to the **Tables and Constraints** chapter and focuses on:

1. The meaning of `NULL` and three-valued logic in SQL expressions.
2. Differences among `UNIQUE`, `NOT NULL`, `CHECK`, and `PRIMARY KEY`.
3. How Oracle handles `NULL` in single-column `UNIQUE` and composite `UNIQUE` constraints.
4. `NULL` edge cases when using composite primary keys and composite foreign keys.
5. Writing constraints matching business rules accurately without letting invalid data slip through.
6. Inspecting metadata, diagnosing errors, and practicing with observable SQL.

> Examples below are meant for a **practice schema**, not tables serving live applications. `CREATE`, `INSERT`, `UPDATE`, `DELETE`, `ALTER`, and `DROP` statements modify the database; explanations describe expected behavior rather than output captured from a single fixed run.

## 2. `NULL` Is Neither 0, an Empty String, Nor an Ordinary Value

In Oracle, `NULL` represents the **absence of a known/recorded value** for a data field. It is distinct from:

| Value | Meaning |
|---|---|
| `0` | A concrete numeric value equal to zero |
| `'0'` | A string containing the digit character `0` |
| `' '` | A string containing a space character, not `NULL` |
| `DATE '2026-01-01'` | A concrete calendar date |
| `NULL` | No defined value for the expression/column |

Example:

```sql
SELECT CASE WHEN 0 IS NULL THEN 'YES' ELSE 'NO' END AS zero_is_null,
       CASE WHEN ' ' IS NULL THEN 'YES' ELSE 'NO' END AS space_is_null,
       CASE WHEN NULL IS NULL THEN 'YES' ELSE 'NO' END AS null_is_null
FROM dual;
```

Expected semantics: `0` and `' '` are not `NULL`, whereas `NULL IS NULL` is `TRUE`.

### 2.1. Empty-String Behavior in Oracle

In current Oracle Database releases, a zero-length string (`''`) in standard character types is treated by Oracle as `NULL`:

```sql
SELECT CASE
           WHEN '' IS NULL THEN 'IS NULL'
           ELSE 'IS NOT NULL'
       END AS empty_string_behavior
FROM dual;
```

Consequently, passing `''` into a `VARCHAR2` column behaves identically to passing `NULL`, including for `NOT NULL`, `UNIQUE`, and `CHECK`. However, a string containing one or more **spaces** is not an empty string. If an application treats `"   "` as "nothing entered," define explicit normalization and validation rather than expecting Oracle to treat it as `NULL`.

### 2.2. Do Not Compare `NULL` with `=`

These expressions are not equivalent:

```sql
-- Wrong way to find NULLs:
SELECT * FROM customers WHERE email = NULL;

-- Right way:
SELECT * FROM customers WHERE email IS NULL;
```

`email = NULL` evaluates to **`UNKNOWN`**, even when `email` is `NULL`. In a `WHERE` clause, only rows where the condition evaluates to **`TRUE`** are returned. Thus `WHERE email = NULL` fails to match the NULL rows the author expected.

Similarly:

```sql
-- Do not use to check for non-NULL:
WHERE email <> NULL

-- Use:
WHERE email IS NOT NULL
```

When comparing two values for business logic where `NULL` on both sides should count as matching, write an explicit **null-safe comparison** appropriate to your Oracle version and use case. That is distinct from how `UNIQUE` constraints evaluate keys.

## 3. Three-Valued Logic: TRUE, FALSE, UNKNOWN

When expressions can contain `NULL`, SQL is not two-valued (`TRUE`/`FALSE`); it has a third value, **`UNKNOWN`**. That explains why `CHECK` normally allows a NULL value through.

| Expression | Logical Result |
|---|---|
| `5 > 0` | `TRUE` |
| `-5 > 0` | `FALSE` |
| `NULL > 0` | `UNKNOWN` |
| `NULL = 5` | `UNKNOWN` |
| `NULL = NULL` | `UNKNOWN` |
| `NULL IS NULL` | `TRUE` |
| `NULL IS NOT NULL` | `FALSE` |

To observe this in Oracle SQL, you can use `CASE WHEN`:

```sql
SELECT CASE
           WHEN 5 > 0 THEN 'TRUE'
           ELSE 'NOT TRUE'
       END AS positive_number,
       CASE
           WHEN CAST(NULL AS NUMBER) > 0 THEN 'TRUE'
           ELSE 'NOT TRUE'
       END AS null_comparison
FROM dual;
```

`CASE WHEN` takes the `THEN` branch only when the condition is `TRUE`; the `ELSE` branch above groups both `FALSE` and `UNKNOWN`, illustrating that the NULL comparison is **not TRUE**.

### 3.1. AND, OR, and NOT with UNKNOWN

Core truth combinations:

| Expression | Result |
|---|---|
| `TRUE AND UNKNOWN` | `UNKNOWN` |
| `FALSE AND UNKNOWN` | `FALSE` |
| `TRUE OR UNKNOWN` | `TRUE` |
| `FALSE OR UNKNOWN` | `UNKNOWN` |
| `NOT UNKNOWN` | `UNKNOWN` |

These rules affect multi-condition constraints such as:

```sql
CHECK (start_date <= end_date AND status = 'ACTIVE')
```

If `start_date` is NULL, the first comparison evaluates to `UNKNOWN`. If the remaining condition is `TRUE`, the whole expression evaluates to `UNKNOWN` and `CHECK` **permits** the row. If the remaining condition is `FALSE`, `UNKNOWN AND FALSE` becomes `FALSE`, so the row is rejected.

To express business rules accurately, specify **which columns may be omitted**, which are mandatory, and which state combinations are valid.

## 4. How Does Oracle Apply Constraints?

| Constraint | Purpose | When Encountering `NULL` |
|---|---|---|
| `NOT NULL` | Column must have a non-`NULL` value | **Rejects** `NULL` |
| `UNIQUE (c)` | No two non-NULL values match in column `c` | Allows multiple `NULL`s in the single-column case |
| `UNIQUE (a,b)` | Ensures uniqueness of the composite key per Oracle semantics | Allows multiple all-NULL rows; partial-NULL has specific rules |
| `CHECK (expression)` | Row-level business condition | Rejects `FALSE`; accepts `TRUE` or `UNKNOWN` |
| `PRIMARY KEY` | Unique row identifier | **Every key component must be non-NULL**, and the key tuple must be unique |
| `FOREIGN KEY` | References a parent table key | NULL components in composite FKs carry special semantics |

Both `UNIQUE` and `PRIMARY KEY` enforce uniqueness, yet **`PRIMARY KEY` implies non-NULL**. A table can have only one primary key, whereas multiple `UNIQUE` constraints can protect different candidate keys.

Do not conflate three separate questions:

1. **Must data be present?** → `NOT NULL`.
2. **Must it not duplicate another row?** → `UNIQUE`.
3. **Must values or cross-column relationships be valid?** → `CHECK` or an appropriate constraint mechanism.

A single column may need `NOT NULL`, `UNIQUE`, and `CHECK` together depending on business rules.

## 5. Single-Column `UNIQUE`: Multiple `NULL`s Are Typically Allowed

### 5.1. The Undeclared Email Scenario

Suppose every provided email may belong to only one account, while some users have not supplied an email yet:

```sql
CREATE TABLE demo_unique_email (
    customer_id NUMBER CONSTRAINT pk_due PRIMARY KEY,
    email       VARCHAR2(120),
    CONSTRAINT uq_due_email UNIQUE (email)
);
```

The following statements illustrate behavior:

```sql
-- Succeeds: two customers both lack an email.
INSERT INTO demo_unique_email (customer_id, email)
VALUES (1, NULL);

INSERT INTO demo_unique_email (customer_id, email)
VALUES (2, NULL);

-- Succeeds: concrete email value.
INSERT INTO demo_unique_email (customer_id, email)
VALUES (3, 'lan@example.test');

-- Fails: duplicate non-NULL email.
-- INSERT INTO demo_unique_email (customer_id, email)
-- VALUES (4, 'lan@example.test');
```

Uncommenting and running the final insert while the constraint is active raises:

```text
ORA-00001: unique constraint (...) violated
```

In this example, **two `NULL` rows do not violate `UNIQUE (email)`**, while two identical `'lan@example.test'` rows are rejected.

### 5.2. Why Is This Not a Contradiction?

`NULL` is not a concrete value compared equal via `=` against another value. Oracle's rule for single-column `UNIQUE` does not treat repeated NULLs as duplicate defined key values. Do not infer that Oracle evaluates `NULL = NULL` and gets `TRUE`.

Additionally, a **standard Oracle B-tree index** does not store an index entry when **all indexed key components are NULL**. That gives a helpful implementation perspective on why multiple NULL rows can coexist on a single-column constraint, though `UNIQUE` should always be understood at the **constraint level**, not solely via index mechanics.

### 5.3. Requiring Email to Be Both Mandatory and Unique

Declare:

```sql
CREATE TABLE demo_required_email (
    customer_id NUMBER PRIMARY KEY,
    email       VARCHAR2(120) NOT NULL,
    CONSTRAINT uq_dre_email UNIQUE (email)
);
```

Now:

- `NULL` is rejected by **`NOT NULL`**.
- Duplicate concrete emails are rejected by **`UNIQUE`**.
- Distinct emails are allowed unless another constraint rejects them.

**`UNIQUE` alone does not replace `NOT NULL`**; add `NOT NULL` whenever the business rule states "every account must have an email."

### 5.4. Duplicates After Normalization

A unique constraint on `email` does not automatically guarantee that variants like `Lan@Example.test` and `lan@example.test` are treated as the same email. String comparison depends on collation and schema design.

If the business requires emails to be unique **after normalizing to a canonical form**, define a consistent normalization method. Where appropriate, a function-based unique index can help:

```sql
-- Illustration: unique on UPPER(email) when present.
CREATE UNIQUE INDEX ux_dre_email_upper
ON demo_required_email (UPPER(email));
```

However, if the table already has `UNIQUE(email)`, a second index may be redundant or conflict with design policy. `UPPER` is only an example; real email rules can be subtler, and case-folding depends on data and collation. Do not assume `UPPER()` is universally correct for all emails or locales.

## 6. Composite `UNIQUE`: All-NULL vs. Partial-NULL Cases

### 6.1. What Is a Composite Key?

A **composite key** consists of **two or more columns**. For example, employee codes need only be unique **within each company**:

```sql
CREATE TABLE demo_company_employee (
    company_id    NUMBER,
    employee_code VARCHAR2(20),
    full_name     VARCHAR2(100),
    CONSTRAINT uq_dce_company_code UNIQUE (company_id, employee_code)
);
```

The constraint protects the **combination** `(company_id, employee_code)` without requiring each column to be globally unique on its own.

Example:

```text
company_id  employee_code
----------  -------------
10          E001
10          E002
20          E001
```

These three rows have distinct **key pairs**, even though `company_id = 10` and `employee_code = E001` each appear multiple times.

### 6.2. Oracle's Crucial Composite NULL Rule

For `UNIQUE (company_id, employee_code)`:

- If **both columns are `NULL`**, the row satisfies uniqueness and multiple `(NULL, NULL)` rows are allowed.
- If the composite key has **at least one non-NULL component**, Oracle checks uniqueness under composite unique key semantics; repeating the same combination of non-NULL values and NULL positions **violates** the constraint.
- Therefore, there is **no** rule saying "if any single component is NULL, Oracle skips UNIQUE."

Walk through each case:

```sql
-- Both rows are all-NULL: allowed.
INSERT INTO demo_company_employee (company_id, employee_code)
VALUES (NULL, NULL);

INSERT INTO demo_company_employee (company_id, employee_code)
VALUES (NULL, NULL);

-- Partial NULL: first row allowed.
INSERT INTO demo_company_employee (company_id, employee_code)
VALUES (10, NULL);

-- Repeats non-NULL portion and same NULL position: violates UNIQUE.
-- INSERT INTO demo_company_employee (company_id, employee_code)
-- VALUES (10, NULL);

-- Same behavior when first column is NULL.
INSERT INTO demo_company_employee (company_id, employee_code)
VALUES (NULL, 'E100');

-- Violates against existing combination.
-- INSERT INTO demo_company_employee (company_id, employee_code)
-- VALUES (NULL, 'E100');

-- Distinct combinations: allowed.
INSERT INTO demo_company_employee (company_id, employee_code)
VALUES (20, NULL);

INSERT INTO demo_company_employee (company_id, employee_code)
VALUES (10, 'E100');
```

Because Oracle treats **all-NULL keys** differently from **partial-NULL keys**, test both scenarios when designing tables. This is especially important when one column defines scope (such as company, tenant, or project) and the other holds a code unique within that scope.

### 6.3. Quick Reference Table for `UNIQUE (a,b)`

Assume an initially empty table with immediate constraint checking:

| Inserted Row | `(a,b)` | Illustrated Outcome | Reason |
|---|---|---|---|
| 1 | `(NULL,NULL)` | Allowed | All-NULL key |
| 2 | `(NULL,NULL)` | Allowed | All-NULL keys may repeat |
| 3 | `(10,NULL)` | Allowed | Combination has not appeared yet |
| 4 | `(10,NULL)` | **Rejected** | Repeats existing non-NULL + NULL combination |
| 5 | `(20,NULL)` | Allowed | Non-NULL value differs from row 3 |
| 6 | `(NULL,'X')` | Allowed | New combination |
| 7 | `(NULL,'X')` | **Rejected** | Duplicates row 6's combination |
| 8 | `(10,'X')` | Allowed | Distinct from existing combinations |
| 9 | `(10,'X')` | **Rejected** | Exact duplicate of row 8 |

This highlights the difference between single-column and multi-column `UNIQUE`. A single `NULL` inside a tuple is not enough to assume the row can repeat.

### 6.4. For "Unique per Company," Should `company_id` Be Nullable?

If the true rule is "every employee always belongs to a company," declare it explicitly:

```sql
CREATE TABLE demo_employee_strict (
    employee_id   NUMBER PRIMARY KEY,
    company_id    NUMBER NOT NULL,
    employee_code VARCHAR2(20) NOT NULL,
    CONSTRAINT uq_des_company_code UNIQUE (company_id, employee_code)
);
```

This model is clean and predictable:

- Every row must have `company_id`.
- Every row must have `employee_code`.
- Each `(company_id, employee_code)` pair appears at most once.

If an employee code **is not assigned at profile creation**, while company is mandatory, you might leave `employee_code` nullable with `UNIQUE(company_id, employee_code)`. However, Oracle will allow only one `(10, NULL)` row per company under composite unique key semantics. If the business allows **multiple employees in the same company awaiting codes**, choose another constraint design (see the conditional uniqueness section).

## 7. Composite `PRIMARY KEY`: No Component May Be NULL

A primary key uniquely identifies each row. With a composite primary key:

```sql
CREATE TABLE demo_order_line (
    order_id   NUMBER,
    line_no    NUMBER,
    product_id NUMBER NOT NULL,
    quantity   NUMBER NOT NULL,
    CONSTRAINT pk_dol PRIMARY KEY (order_id, line_no)
);
```

Oracle requires:

1. `order_id` is non-`NULL`.
2. `line_no` is non-`NULL`.
3. The pair `(order_id, line_no)` does not repeat.

Even without writing `NOT NULL` directly on both columns in the DDL, `PRIMARY KEY (order_id, line_no)` **enforces `NOT NULL` on every primary key component**.

Example:

```sql
-- Valid: same order_id, different line_no.
INSERT INTO demo_order_line (order_id, line_no, product_id, quantity)
VALUES (1001, 1, 501, 2);

INSERT INTO demo_order_line (order_id, line_no, product_id, quantity)
VALUES (1001, 2, 502, 1);

-- Error: line_no is NULL; primary key cannot be incomplete.
-- INSERT INTO demo_order_line (order_id, line_no, product_id, quantity)
-- VALUES (1001, NULL, 503, 3);

-- Error: primary key already exists.
-- INSERT INTO demo_order_line (order_id, line_no, product_id, quantity)
-- VALUES (1001, 1, 504, 1);
```

Typical errors:

- `ORA-01400: cannot insert NULL into ...` when inserting NULL into a NOT NULL/PK column.
- `ORA-00001: unique constraint ... violated` when duplicating the key tuple.

### Is `PRIMARY KEY (a,b)` Equivalent to `UNIQUE(a,b)`?

**No**, with respect to nullability:

| Property | `PRIMARY KEY(a,b)` | `UNIQUE(a,b)` |
|---|---|---|
| Tuple cannot duplicate | Yes | Yes, per composite unique rules |
| Can `a` be NULL? | No | Possibly |
| Can `b` be NULL? | No | Possibly |
| Can `(NULL,NULL)` repeat? | No, row is invalid | Yes |
| Limit per table | At most one PK | Multiple UNIQUEs allowed |
| Role | Primary row identifier of the table | Additional unique key |

If you want a pair to behave identically ("non-NULL and unique") without making it the primary key, declare **both columns `NOT NULL` plus `UNIQUE`**. Still, **primary key** conveys clearer modeling intent for row identity and referential targets.

## 8. Composite Foreign Keys and `NULL`: An Additional Perspective

A **composite foreign key** references a matching key in a parent table. In Oracle, when one or more components of a **composite foreign key** are `NULL`, the remaining non-NULL components do not necessarily have to match a parent row. This differs from composite unique key checking.

Example:

```sql
CREATE TABLE demo_department_parent (
    company_id    NUMBER NOT NULL,
    department_id NUMBER NOT NULL,
    department_name VARCHAR2(100),
    CONSTRAINT pk_ddp PRIMARY KEY (company_id, department_id)
);

CREATE TABLE demo_employee_child (
    employee_id   NUMBER PRIMARY KEY,
    company_id    NUMBER,
    department_id NUMBER,
    CONSTRAINT fk_dec_department
        FOREIGN KEY (company_id, department_id)
        REFERENCES demo_department_parent (company_id, department_id)
);
```

Suppose the parent table has no departments yet. Oracle accepts:

```sql
-- Both foreign key columns are NULL.
INSERT INTO demo_employee_child
    (employee_id, company_id, department_id)
VALUES (1, NULL, NULL);

-- Composite foreign key is partially NULL.
INSERT INTO demo_employee_child
    (employee_id, company_id, department_id)
VALUES (2, 10, NULL);
```

With a complete key `(10,100)`, Oracle requires that pair to exist in the parent table:

```sql
-- If parent lacks (10,100), this violates the foreign key.
-- INSERT INTO demo_employee_child
--     (employee_id, company_id, department_id)
-- VALUES (3, 10, 100);
```

Key takeaway: the **business may forbid half-populated foreign references**. In that case, `FOREIGN KEY` alone is not enough to express the rule.

### 8.1. Allowing Either Both NULL or Both Non-NULL

You can add a `CHECK` constraint:

```sql
ALTER TABLE demo_employee_child
ADD CONSTRAINT ck_dec_pair_complete
CHECK (
       (company_id IS NULL     AND department_id IS NULL)
    OR (company_id IS NOT NULL AND department_id IS NOT NULL)
);
```

This rule allows:

- `(NULL,NULL)`: employee not assigned to a department yet.
- `(10,100)`: complete key pair, which must also satisfy the foreign key.

It forbids:

- `(10,NULL)`.
- `(NULL,100)`.

**Because the practice example above already inserted `(10,NULL)`**, `ALTER TABLE ... ADD CONSTRAINT` will fail until that row is cleaned up. This is an important consequence of adding constraints to populated tables: inspect and remediate non-conforming rows before enabling the constraint.

If the rule states "every employee must belong to a department," simply declare **both foreign key components `NOT NULL`** from the start alongside the foreign key.

### 8.2. Unique Keys and Foreign Keys Have Different Goals

- `UNIQUE(a,b)` verifies **no duplicate key tuples exist** within the constrained table.
- `FOREIGN KEY(a,b) REFERENCES parent(a,b)` verifies **referential matching** when components are supplied per Oracle rules.
- `CHECK` enforces valid **NULL/non-NULL combinations**.
- `NOT NULL` specifies which components are **always mandatory**.

A multi-tenant or project-scoped schema often needs **multiple constraints working together**, not just a single composite key.

## 9. `CHECK` and `NULL`: FALSE Is Blocked, UNKNOWN Is Accepted

### 9.1. Positive Quantity Example

```sql
CREATE TABLE demo_check_quantity (
    item_id  NUMBER PRIMARY KEY,
    quantity NUMBER,
    CONSTRAINT ck_dcq_positive CHECK (quantity > 0)
);
```

Cases:

| `quantity` | `quantity > 0` | `CHECK` Outcome |
|---|---|---|
| `5` | `TRUE` | Allowed |
| `0` | `FALSE` | Rejected |
| `-2` | `FALSE` | Rejected |
| `NULL` | `UNKNOWN` | **Allowed** |

This is the single easiest mistake when writing check constraints. If the business requires **quantity to exist and exceed 0**, add `NOT NULL`:

```sql
CREATE TABLE demo_check_quantity_required (
    item_id  NUMBER PRIMARY KEY,
    quantity NUMBER NOT NULL,
    CONSTRAINT ck_dcqr_positive CHECK (quantity > 0)
);
```

Now `NULL` is rejected by `NOT NULL`, while `0` and negatives are rejected by `CHECK`.

### 9.2. Why Does Oracle Accept UNKNOWN in CHECK?

`CHECK` guarantees that **no row is proven to violate the expression**. When a component is unknown (`NULL`), the expression may be neither true nor false. Following the SQL standard, Oracle admits rows when the result is **`TRUE` or `UNKNOWN`**, rejecting only **`FALSE`**.

This differs from `WHERE`:

```sql
-- WHERE returns rows only when the condition is TRUE:
SELECT * FROM demo_check_quantity
WHERE quantity > 0;
```

Rows with `quantity IS NULL` are excluded by `WHERE quantity > 0`, yet can still exist in a table with `CHECK (quantity > 0)`. **Being permitted for storage and being selected by WHERE are two different questions.**

### 9.3. `CHECK` with a Value List

```sql
CREATE TABLE demo_order_status (
    order_id NUMBER PRIMARY KEY,
    status  VARCHAR2(20),
    CONSTRAINT ck_dos_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);
```

This blocks `'UNKNOWN_STATUS'`, yet **does not block `NULL`**. If every order must have a status:

```sql
status VARCHAR2(20) NOT NULL
```

Then `NOT NULL` guarantees presence and `CHECK` guarantees the allowed domain.

A common mistake is writing `CHECK (status IN (...))` and assuming `NOT NULL` is unnecessary because `NULL` is not in the list. That misunderstands three-valued logic.

## 10. Multi-Column `CHECK` Constraints and UNKNOWN Traps

### 10.1. End Date Must Follow Start Date

```sql
CREATE TABLE demo_booking (
    booking_id NUMBER PRIMARY KEY,
    start_at   DATE,
    end_at     DATE,
    CONSTRAINT ck_db_time_order CHECK (end_at > start_at)
);
```

When both dates have values, Oracle checks their order:

| `start_at` | `end_at` | Result |
|---|---|---|
| 10:00 | 11:00 | Allowed |
| 11:00 | 10:00 | Rejected |
| `NULL` | 11:00 | **Allowed** (`UNKNOWN`) |
| 10:00 | `NULL` | **Allowed** (`UNKNOWN`) |
| `NULL` | `NULL` | **Allowed** (`UNKNOWN`) |

If both dates are always mandatory:

```sql
start_at DATE NOT NULL,
end_at   DATE NOT NULL,
CHECK (end_at > start_at)
```

If an end date is required only once the booking is confirmed, express that conditional requirement using status in `CHECK` instead of forcing every state into one rule.

### 10.2. Requiring at Least One of Two Contact Methods

```sql
CREATE TABLE demo_contact (
    contact_id NUMBER PRIMARY KEY,
    email      VARCHAR2(100),
    phone      VARCHAR2(30),
    CONSTRAINT ck_dc_one_contact
        CHECK (email IS NOT NULL OR phone IS NOT NULL)
);
```

Here, `IS NULL` and `IS NOT NULL` always yield a definite `TRUE` or `FALSE`, making the rule unambiguous:

| Email | Phone | Result |
|---|---|---|
| Present | Missing | Allowed |
| Missing | Present | Allowed |
| Present | Present | Allowed |
| Missing | Missing | Rejected |

Remember that `''` is treated by Oracle as `NULL` for character types. Passing `"   "` (three spaces), however, produces a non-NULL string that passes the check above. If the business requires at least one **valid** contact method, add formatting/normalization rules beyond `IS NOT NULL`.

### 10.3. Requiring Exactly One of Two Columns

```sql
CREATE TABLE demo_payment_reference (
    payment_id     NUMBER PRIMARY KEY,
    card_ref       VARCHAR2(50),
    bank_ref       VARCHAR2(50),
    CONSTRAINT ck_dpr_exclusive
    CHECK (
        (card_ref IS NOT NULL AND bank_ref IS NULL)
        OR
        (card_ref IS NULL AND bank_ref IS NOT NULL)
    )
);
```

This expresses **exclusive OR**: exactly one reference type must be present. Both populated or both NULL are rejected.

This shows why writing `IS NULL` / `IS NOT NULL` directly is far safer and clearer when handling potentially missing data than attempting `= NULL`.

### 10.4. Status-Dependent Conditional Constraints

Suppose an order's `status` is `NEW`, `PAID`, or `CANCELLED`, and every `PAID` order must have `paid_at`:

```sql
CREATE TABLE demo_order_paid (
    order_id NUMBER PRIMARY KEY,
    status   VARCHAR2(20) NOT NULL,
    paid_at  DATE,
    CONSTRAINT ck_dop_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    CONSTRAINT ck_dop_paid_date
        CHECK (status <> 'PAID' OR paid_at IS NOT NULL)
);
```

If `status='PAID'` and `paid_at IS NULL`, both sides are FALSE so the row is rejected. If status differs from `PAID`, the first side is TRUE so `paid_at` is optional per the written rule. Because `status` is `NOT NULL`, the second expression cannot slip into UNKNOWN via a missing status.

If the business also requires **unpaid orders not to have `paid_at`**, express the bidirectional condition explicitly—combining `status='PAID'`/`status<>'PAID'` branches with `IS NULL`/`IS NOT NULL`.

## 11. Not Every Rule Can Be Written with CHECK

A standard `CHECK` evaluates expressions solely on **the row currently being changed**, within Oracle syntax limits. It is not the tool for invariants spanning multiple rows or other tables.

For example:

> "Two accounts cannot share the same email within the same company."

A `CHECK` such as:

```sql
-- Invalid idea: CHECK cannot use subqueries to count other rows.
-- CHECK ((SELECT COUNT(*) FROM accounts WHERE email = ...) <= 1)
```

is not supported by Oracle for cross-row uniqueness. Use **`UNIQUE`**, a suitable expression-based unique index, or another data design.

Similarly:

> "Department code must exist in DEPARTMENTS."

Use **`FOREIGN KEY`**, not `CHECK` with a `SELECT` against another table.

For complex multi-row invariants, you may need transactions, redesigned tables, locking/serialization, complementary constraints, or application logic; never assume triggers automatically replace constraints safely under high concurrency.

## 12. When UNIQUE Permits NULL Yet the Business Needs a Different Rule

The scenarios below show why design must begin from **data semantics**, rather than dropping in a `UNIQUE` clause and hoping it fits.

### 12.1. Case A: Email Optional, Unique When Provided

Rule:

```text
email = NULL                -> Multiple accounts allowed
email = 'a@example.test'    -> At most one account
```

Using `UNIQUE(email)` on a nullable column fits naturally.

### 12.2. Case B: Email Mandatory and Unique

Rule:

```text
email = NULL                -> Disallowed
existing email              -> Duplicates disallowed
```

Use `email NOT NULL` plus `UNIQUE(email)`.

### 12.3. Case C: Unique per Tenant, Allowing Multiple Rows Without a Code

Suppose you need:

```text
tenant_id = 10, code = NULL -> Multiple rows allowed
tenant_id = 10, code = 'A'  -> Only one row
tenant_id = 20, code = 'A'  -> Allowed
```

Plain `UNIQUE(tenant_id, code)` **does not match** allowing multiple `(10,NULL)` rows in Oracle. One deliberate design uses a **conditional unique index** over expressions that produce values only when `code IS NOT NULL`:

```sql
CREATE TABLE demo_tenant_item (
    item_id   NUMBER PRIMARY KEY,
    tenant_id NUMBER NOT NULL,
    code      VARCHAR2(30)
);

-- When code is NULL, both index key expressions evaluate to NULL.
-- When code has a value, uniqueness is enforced on (tenant_id, code).
CREATE UNIQUE INDEX ux_dti_tenant_code_present
ON demo_tenant_item (
    CASE WHEN code IS NOT NULL THEN tenant_id END,
    CASE WHEN code IS NOT NULL THEN code END
);
```

Explanation:

- Row `(10,NULL)` yields key `(NULL,NULL)`, which **creates no non-NULL B-tree entry** and can repeat.
- Row `(10,'A')` yields key `(10,'A')`, blocking a second row for the same tenant and code.
- Row `(20,'A')` yields a distinct key from `(10,'A')` and is allowed.

With this approach, `tenant_id NOT NULL` matters because every item must belong to a tenant, while `code` may be absent. This illustrates a **function-based unique index**, subject to appropriate privileges and features. Evaluate real constraints carefully, keeping in mind that an expression index differs from a direct `UNIQUE` constraint.

### 12.4. Case D: Unique Only Among ACTIVE Records

Suppose a company retains multiple `INACTIVE` records with the same code, while allowing only one **`ACTIVE`** record per code within each tenant:

```sql
CREATE TABLE demo_tenant_account (
    account_id NUMBER PRIMARY KEY,
    tenant_id  NUMBER NOT NULL,
    code       VARCHAR2(30) NOT NULL,
    status     VARCHAR2(10) NOT NULL,
    CONSTRAINT ck_dta_status CHECK (status IN ('ACTIVE', 'INACTIVE'))
);

CREATE UNIQUE INDEX ux_dta_active
ON demo_tenant_account (
    CASE WHEN status = 'ACTIVE' THEN tenant_id END,
    CASE WHEN status = 'ACTIVE' THEN code END
);
```

For `INACTIVE` rows, both index expressions evaluate to NULL, so multiple inactive rows coexist. For `ACTIVE` rows, the `(tenant_id, code)` pair is enforced unique. If `status` were nullable, review the `CASE` expression and missing-status rules so unexpected rows cannot slip past.

### 12.5. Case E: Allowing at Most One NULL Value

This is a rare requirement—**not the default semantics of single-column `UNIQUE`**. If the business truly treats NULL as a "value" allowed at most once, an expression-based unique index can model it:

```sql
CREATE TABLE demo_one_missing_code (
    row_id NUMBER PRIMARY KEY,
    code   VARCHAR2(30),
    CONSTRAINT ck_domc_reserved
        CHECK (code IS NULL OR code <> '#MISSING#')
);

CREATE UNIQUE INDEX ux_domc_null_as_value
ON demo_one_missing_code (NVL(code, '#MISSING#'));
```

The index maps `NULL` to sentinel string `'#MISSING#'`. Two rows with `code=NULL` evaluate to the same key, so the unique index rejects the second row. The `CHECK` constraint forbids using the sentinel string as real data to prevent collisions.

**Design warning:** treating "missing code" as a singleton value should be scrutinized carefully. Any sentinel must not collide with real data, must fit column type/length, and must not leave loopholes under normalization. Treat this as a technical illustration rather than general advice to add `NVL` indexes on nullable columns.

## 13. `UNIQUE` Constraints and Unique Indexes: Related, Not Identical

Oracle typically uses an index to assist uniqueness checking. Still, the logical constraint and physical access structure play distinct roles:

| Component | Primary Role | Key Properties |
|---|---|---|
| `UNIQUE` constraint | Declares a schema-level data rule | Managed in constraint metadata; has name, status, checking mode |
| Unique index | Prevents duplicate index keys per index columns/expressions | Can use expressions or `CASE`; not every unique index corresponds to a declared constraint |
| `PRIMARY KEY` constraint | Identifies each row with a unique non-NULL key | Backed by an appropriate index in Oracle |

In cases such as **deferrable constraints**, Oracle can use a **nonunique index** to maintain a constraint checked at the appropriate boundary. Therefore, never assume index uniqueness alone defines the entire semantics of `UNIQUE` or `PRIMARY KEY`.

### 13.1. Status and Checking Timing

Constraints default to **`NOT DEFERRABLE`** (checked per statement rules), while constraints declared `DEFERRABLE` allow checking to be postponed until an appropriate boundary, such as `COMMIT` when in `DEFERRED` mode.

Illustrative example:

```sql
CREATE TABLE demo_deferred_codes (
    row_id NUMBER PRIMARY KEY,
    code   VARCHAR2(30),
    CONSTRAINT uq_ddc_code
        UNIQUE (code) DEFERRABLE INITIALLY DEFERRED
);
```

With this configuration, a transaction can pass through an intermediate state that violates uniqueness and fix it before `COMMIT`, per Oracle enforcement rules. If the violation remains at check time, the transaction cannot commit validly.

**Deferring checks does not alter `NULL` rules:** a nullable column keeps its `UNIQUE` null semantics, and a primary key still rejects NULL. Never enable `DEFERRABLE` expecting to solve a multiple-`NULL` requirement; those are separate concerns.

### 13.2. Why Declare Constraints Directly in the Schema?

If duplicate checking relies solely on application code:

```text
1. SELECT to see if the code already exists
2. If not found, INSERT
```

two concurrent requests can both observe "absent" and both attempt `INSERT`. A `UNIQUE` constraint (or appropriate unique index) gives the database concurrency-safe uniqueness protection, instead of relying on pre-insert query checks.

Applications should still catch and classify constraint errors into clean business responses, without treating Java-side pre-checks as a replacement for database constraints.

## 14. Inspecting Constraint and Nullability Metadata in Oracle

Data dictionary views reveal **which constraints are actually declared**, especially on existing schemas where original DDL scripts are unavailable.

### 14.1. Finding Constraints on a Table in the Current Schema

```sql
SELECT constraint_name,
       constraint_type,
       status,
       deferrable,
       deferred,
       validated
FROM user_constraints
WHERE table_name = 'DEMO_COMPANY_EMPLOYEE'
ORDER BY constraint_name;
```

Common `CONSTRAINT_TYPE` codes:

| Code | Meaning |
|---|---|
| `P` | Primary key |
| `U` | Unique |
| `R` | Referential / foreign key |
| `C` | Check, which can also include metadata representations of `NOT NULL` |

`STATUS`, `VALIDATED`, `DEFERRABLE`, and `DEFERRED` show whether a constraint is enabled, how existing data was validated, and whether deferred checking is permitted. On legacy systems, **seeing a constraint name in metadata is not enough to assume all DML is actively enforced**; check its status.

### 14.2. Viewing Column Order in Composite Keys

```sql
SELECT c.constraint_name,
       c.constraint_type,
       cc.position,
       cc.column_name
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.table_name = 'DEMO_COMPANY_EMPLOYEE'
  AND c.constraint_type IN ('P', 'U', 'R')
ORDER BY c.constraint_name, cc.position;
```

`POSITION` shows each column's position in the composite key—for example, `COMPANY_ID` at position 1 and `EMPLOYEE_CODE` at position 2. When running metadata checks across multiple schemas or special constraint names, adjust owner filters accordingly.

### 14.3. Checking Column `NULLABLE` Metadata

```sql
SELECT column_name,
       data_type,
       nullable
FROM user_tab_columns
WHERE table_name = 'DEMO_COMPANY_EMPLOYEE'
ORDER BY column_id;
```

`NULLABLE='N'` indicates Oracle records the column as non-nullable in metadata. Cross-check `USER_CONSTRAINTS` to see why the column is mandatory; never assume `CHECK (col > 0)` flips `NULLABLE` to `'N'`.

### 14.4. Viewing CHECK Conditions

Depending on release/client, check condition text resides in metadata columns like `SEARCH_CONDITION` / `SEARCH_CONDITION_VC` (support varies). Example on releases with `SEARCH_CONDITION_VC`:

```sql
SELECT constraint_name,
       constraint_type,
       search_condition_vc
FROM user_constraints
WHERE table_name = 'DEMO_CHECK_QUANTITY'
  AND constraint_type = 'C';
```

Before running this query on older databases, verify whether `SEARCH_CONDITION_VC` exists on the view; older releases only provide `SEARCH_CONDITION` with a data type harder to manipulate directly in SQL.

### 14.5. Viewing Expression-Based Unique Indexes

```sql
SELECT index_name,
       uniqueness,
       table_name
FROM user_indexes
WHERE table_name = 'DEMO_TENANT_ITEM'
ORDER BY index_name;
```

For function-based indexes:

```sql
SELECT index_name,
       column_position,
       column_expression
FROM user_ind_expressions
WHERE index_name = 'UX_DTI_TENANT_CODE_PRESENT'
ORDER BY column_position;
```

Index metadata shows the exact expressions enforcing uniqueness. Checking only `USER_CONSTRAINTS` and ignoring standalone unique indexes can miss database-level uniqueness rules.

### 14.6. Differences Among USER_, ALL_, and DBA_ Views

- `USER_...`: objects owned by the currently logged-in schema.
- `ALL_...`: objects visible to the current session per privileges.
- `DBA_...`: broader administrative scope; requires appropriate privileges.

In CDB/PDB architectures, connect to the right PDB or administrative context. Two schemas with identical table names across two PDBs may enforce entirely different constraints.

## 15. Step-by-Step Lab: Observing NULL with UNIQUE and CHECK

Run these steps in a schema with `CREATE TABLE` privileges and sufficient quota, never on production tables. Deliberately failing statements are **commented out** so you can run them one at a time and observe responses cleanly without halting an entire batch.

### Step 1. Create a Table with Single-Column UNIQUE

```sql
CREATE TABLE lab_null_unique (
    id    NUMBER PRIMARY KEY,
    code  VARCHAR2(20),
    CONSTRAINT uq_lnu_code UNIQUE (code)
);
```

Insert rows:

```sql
INSERT INTO lab_null_unique (id, code) VALUES (1, NULL);
INSERT INTO lab_null_unique (id, code) VALUES (2, NULL);
INSERT INTO lab_null_unique (id, code) VALUES (3, 'A');
INSERT INTO lab_null_unique (id, code) VALUES (4, 'B');

COMMIT;
```

Query data:

```sql
SELECT id, code
FROM lab_null_unique
ORDER BY id;
```

The first two rows have `CODE IS NULL` and coexist cleanly.

### Step 2. Try Inserting a Duplicate Non-NULL Value

```sql
-- Uncomment to test in a practice schema:
-- INSERT INTO lab_null_unique (id, code) VALUES (5, 'A');
```

Oracle rejects it via `UQ_LNU_CODE`; the earlier valid rows remain intact. Applications should handle `ORA-00001` to return a clear "code already exists" message or equivalent logic.

### Step 3. Create a Composite Key Table

```sql
CREATE TABLE lab_null_composite (
    id NUMBER PRIMARY KEY,
    a  NUMBER,
    b  VARCHAR2(20),
    CONSTRAINT uq_lnc_pair UNIQUE (a, b)
);
```

Insert:

```sql
INSERT INTO lab_null_composite VALUES (1, NULL, NULL);
INSERT INTO lab_null_composite VALUES (2, NULL, NULL);
INSERT INTO lab_null_composite VALUES (3, 10,   NULL);
INSERT INTO lab_null_composite VALUES (4, 20,   NULL);
INSERT INTO lab_null_composite VALUES (5, NULL, 'X');
INSERT INTO lab_null_composite VALUES (6, 10,   'X');

COMMIT;
```

Test duplicate combinations:

```sql
-- Each statement below violates composite UNIQUE against existing data:
-- INSERT INTO lab_null_composite VALUES (7, 10, NULL);
-- INSERT INTO lab_null_composite VALUES (8, NULL, 'X');
-- INSERT INTO lab_null_composite VALUES (9, 10, 'X');
```

Observe: two `(NULL,NULL)` rows coexist, while repeating `(10,NULL)` or `(NULL,'X')` is blocked. **Never conclude from `NULL = NULL` that Oracle allows every composite key containing NULL to repeat.**

### Step 4. Test CHECK with UNKNOWN

```sql
CREATE TABLE lab_null_check (
    id     NUMBER PRIMARY KEY,
    amount NUMBER,
    CONSTRAINT ck_lnc_amount CHECK (amount > 0)
);

INSERT INTO lab_null_check VALUES (1, 10);
INSERT INTO lab_null_check VALUES (2, NULL);

-- This statement violates CHECK:
-- INSERT INTO lab_null_check VALUES (3, -1);

COMMIT;
```

Row `amount=NULL` is allowed because `amount > 0` evaluates to UNKNOWN. To disallow missing amounts, add `NOT NULL` or an equivalent business constraint.

### Step 5. Inspect Metadata

```sql
SELECT table_name,
       constraint_name,
       constraint_type,
       status
FROM user_constraints
WHERE table_name IN (
    'LAB_NULL_UNIQUE',
    'LAB_NULL_COMPOSITE',
    'LAB_NULL_CHECK'
)
ORDER BY table_name, constraint_name;

SELECT table_name,
       column_name,
       nullable
FROM user_tab_columns
WHERE table_name IN (
    'LAB_NULL_UNIQUE',
    'LAB_NULL_COMPOSITE',
    'LAB_NULL_CHECK'
)
ORDER BY table_name, column_id;
```

Notice that `CODE` in `LAB_NULL_UNIQUE` and `AMOUNT` in `LAB_NULL_CHECK` remain nullable despite having constraints on them.

### Step 6. Compare WHERE, GROUP BY, and UNIQUE

```sql
SELECT COUNT(*) AS all_rows,
       COUNT(code) AS rows_with_code
FROM lab_null_unique;
```

`COUNT(*)` counts every row, whereas `COUNT(code)` counts only non-NULL `CODE` values—so the two counts differ.

```sql
SELECT code, COUNT(*) AS row_count
FROM lab_null_unique
GROUP BY code
ORDER BY code;
```

`GROUP BY` groups rows with `CODE IS NULL` into one bucket for aggregation, even though `UNIQUE(code)` permits multiple NULLs. **NULL grouping semantics in aggregation are not the same as single-column UNIQUE semantics.**

### Step 7. Clean Up Practice Tables

Only after confirming these are tables you created and no data needs to be kept:

```sql
DROP TABLE lab_null_check PURGE;
DROP TABLE lab_null_composite PURGE;
DROP TABLE lab_null_unique PURGE;
```

`DROP TABLE ... PURGE` permanently drops objects and data without using the recycle bin, and performs an implicit commit. Never run cleanup commands on shared tables.

## 16. Common Errors and Symptoms in Java Applications

### 16.1. `ORA-00001` Is Not Always Caused by PRIMARY KEY

`ORA-00001` can originate from:

- A duplicate primary key.
- A violated unique constraint.
- A unique index, including an expression-based unique index.

When handling errors, inspect the **constraint/index name** in the exception and metadata to pinpoint which rule failed; never assume a duplicate ID when the error comes from `UNIQUE(email)`.

Interaction flow:

```text
Java API: POST /customers
    |
    v
INSERT INTO customers (id, email)
    |
    +-- Email not duplicate -> DB permits
    |
    +-- Duplicate email     -> ORA-00001
                                 |
                                 v
                           Application maps
                           to appropriate business error
```

Pre-checking duplicates in Java before `INSERT` improves UX, yet **cannot replace database constraints** when concurrent requests arrive.

### 16.2. `ORA-02290` When CHECK Fails

When a row causes a `CHECK` expression to evaluate to `FALSE`, Oracle raises:

```text
ORA-02290: check constraint (...) violated
```

If you expected `CHECK (amount > 0)` to block NULL and it did not, that is a **constraint specification bug**, not Oracle skipping validation.

### 16.3. `ORA-01400` When NOT NULL Fails

Attempting to `INSERT NULL` into a mandatory column raises:

```text
ORA-01400: cannot insert NULL into (...)
```

Attempting to `UPDATE` a NOT NULL column to NULL raises a related error such as `ORA-01407`. Error codes vary by operation, yet the rule is uniform: `NULL` cannot be stored in a `NOT NULL` column.

### 16.4. Java `null` Is Not the String `"null"`

JDBC example:

```java
String sql = "INSERT INTO customers (customer_id, email) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);

    if (email == null) {
        ps.setNull(2, java.sql.Types.VARCHAR);
    } else {
        ps.setString(2, email);
    }

    ps.executeUpdate();
}
```

`setNull(...)` passes SQL `NULL`. Passing `"null"` via `setString` sends a four-character string (`n`, `u`, `l`, `l`), not a missing value. In Oracle, empty string `""` is treated as NULL in standard character types; do not rely implicitly on that conversion instead of explicit application normalization.

This Java snippet assumes `Connection`, `customerId`, `email`, and transactions are configured. To prevent SQL injection, always **bind parameters** rather than concatenating input strings into SQL.

### 16.5. ORMs/Hibernate Do Not Automatically Fix NULL Design

An application annotation may declare nullability or uniqueness, yet you must verify the **actual DDL applied to the Oracle schema** and active constraint states. More importantly, `@Column(unique=true)` on a nullable column does not make it NOT NULL, and a unique constraint across two nullable columns follows Oracle's composite rules described above.

When using migrations or Hibernate, verify all of:

- Actual table and constraint DDL.
- Single vs. composite keys, and nullability of every component.
- Nullability validation rules at the API boundary.
- Expression-based unique indexes when conditional uniqueness is needed.
- How the application classifies Oracle exceptions.

## 17. Common Design Patterns and How to Express Them

| Business Requirement | Reference Constraint Design | NULL Notes |
|---|---|---|
| Email optional, unique when present | `email VARCHAR2(...), UNIQUE(email)` | Multiple NULL emails allowed |
| Email mandatory and unique | `email ... NOT NULL, UNIQUE(email)` | `NOT NULL` handles missing values |
| Quantity mandatory and positive | `quantity NUMBER NOT NULL CHECK (quantity > 0)` | CHECK alone permits UNKNOWN |
| End date optional, must follow start if present | `start_at NOT NULL`, `CHECK (end_at IS NULL OR end_at > start_at)` | Explicitly models absent end date |
| `(order_id,line_no)` identifies row | `PRIMARY KEY(order_id,line_no)` | All components non-NULL |
| Code unique per company, both mandatory | `company_id NOT NULL`, `code NOT NULL`, `UNIQUE(company_id,code)` | Avoids partial-NULLs |
| Code unique per tenant when assigned; multiple unassigned allowed | Unique index with `CASE WHEN code IS NOT NULL THEN ... END` | Produces all-NULL key when code is missing |
| Two FK components must be both present or both absent | `FOREIGN KEY(a,b)` + `CHECK ((a IS NULL AND b IS NULL) OR ...)` | FK alone allows partial NULL |
| At least one of email or phone | `CHECK (email IS NOT NULL OR phone IS NOT NULL)` | Also account for whitespace and formatting |
| Exactly one of two payment references | `CHECK ((a IS NOT NULL AND b IS NULL) OR (a IS NULL AND b IS NOT NULL))` | Rejects both NULL |
| Unique among ACTIVE rows only | Function-based unique index via `CASE` | Non-applicable branches must yield all-NULL |

These examples represent standard technical patterns, not a substitute for defining explicit **business rules**. Before finalizing constraints, enumerate valid and invalid input cases—including **each column NULL, all NULL, duplicates, and whitespace/empty strings**.

## 18. Key Misconceptions to Avoid

| Claim | True or False? | Explanation |
|---|---|---|
| "`NULL = NULL` is TRUE." | False | In standard SQL, the result is UNKNOWN |
| "`WHERE x = NULL` finds NULL rows." | False | Use `WHERE x IS NULL` |
| "`UNIQUE(x)` forbids two NULLs." | False in Oracle | Multiple NULLs are allowed on single-column constraints |
| "If `UNIQUE(a,b)` has one NULL column, rows can always repeat." | False | Partial-NULL composite keys violate uniqueness if the non-NULL part matches |
| "Two `(NULL,NULL)` rows violate `UNIQUE(a,b)`." | False | All-NULL composite keys may repeat |
| "`PRIMARY KEY(a,b)` allows one component to be NULL." | False | Every PK component must be NOT NULL |
| "`CHECK(x > 0)` rejects NULL." | False | NULL produces UNKNOWN, which CHECK does not reject |
| "`CHECK` and `WHERE` reject UNKNOWN identically." | False | CHECK accepts UNKNOWN; WHERE selects only TRUE |
| "`CHECK(x IS NOT NULL)` rejects NULL." | True | `IS NOT NULL` evaluates to FALSE when x is NULL |
| "A composite FK with one NULL component still requires matching a parent." | False under standard Oracle semantics | Add `CHECK`/`NOT NULL` when half-populated pairs are disallowed |
| "`''` and `' '` are identical in Oracle." | False | Empty string is treated as NULL in current character types; space is a value |
| "`COUNT(col)` and `COUNT(*)` are always equal." | False | `COUNT(col)` skips NULLs |
| "Checking duplicates with SELECT before INSERT removes the need for UNIQUE." | False | Race conditions occur under concurrent transactions |
| "An expression-based unique index always implies a declared UNIQUE constraint." | False | Related mechanisms, yet distinct metadata and management semantics |

## 19. Self-Check Questions

**Question 1.** Table `CUSTOMERS` has `UNIQUE(email)` on a nullable `email` column. Are two rows with `email=NULL` valid?

**Answer:** Yes. Single-column `UNIQUE` in Oracle permits multiple NULLs.

**Question 2.** What changes if `NOT NULL` is added to `email`?

**Answer:** Rows missing an email are rejected. `UNIQUE` continues rejecting duplicate non-NULL values.

**Question 3.** A table has `UNIQUE(tenant_id, code)` with both columns nullable. Are two `(NULL,NULL)` rows valid?

**Answer:** Yes, Oracle permits multiple rows where **all** components of a composite unique key are NULL.

**Question 4.** Can two `(10,NULL)` rows coexist under `UNIQUE(tenant_id,code)`?

**Answer:** No under standard Oracle composite unique key semantics: repeating the same non-NULL component with matching NULL positions violates the constraint.

**Question 5.** Why is `CHECK (price > 0)` insufficient if every product must have a price?

**Answer:** `price=NULL` makes the expression UNKNOWN, which CHECK accepts. Add `price NOT NULL`.

**Question 6.** If `start_date=NULL`, what does `CHECK(end_date >= start_date)` return and what happens?

**Answer:** The comparison yields UNKNOWN, so CHECK allows the row. If `start_date` is mandatory, add `NOT NULL` or an equivalent explicit check.

**Question 7.** Does `PRIMARY KEY(order_id,line_no)` permit `line_no=NULL`?

**Answer:** No. Every component of a composite primary key must be non-NULL.

**Question 8.** A composite foreign key `(company_id,department_id)` has a row `(10,NULL)`. What constraint might be needed if partial references are forbidden?

**Answer:** Add a `CHECK` requiring both components to be NULL or both non-NULL, or mark both `NOT NULL` if the relationship is mandatory.

**Question 9.** What does `CHECK (email IS NOT NULL OR phone IS NOT NULL)` block?

**Answer:** Rows where both email and phone are NULL. It does not validate length, whitespace, or contact format by itself.

**Question 10.** A system wants multiple `(tenant_id=10,code=NULL)` rows, while requiring non-NULL codes to be unique per tenant. Does `UNIQUE(tenant_id,code)` fit?

**Answer:** Not cleanly in Oracle. Use an expression-based unique index producing non-NULL keys only when `code` is present, or another table/constraint design matching the rule.

**Question 11.** Why do `SELECT COUNT(*)` and `SELECT COUNT(email)` differ when many emails are NULL?

**Answer:** `COUNT(*)` counts all rows; `COUNT(email)` ignores rows where `email` is NULL.

**Question 12.** When encountering `ORA-00001`, how do you tell whether a primary key or a unique constraint was violated?

**Answer:** Inspect the constraint/index name reported by Oracle and cross-reference `USER_CONSTRAINTS`, `USER_CONS_COLUMNS`, and index metadata in the right schema—never guess from `ORA-00001` alone.

## 20. Conclusion

In Oracle, `NULL` represents the **absence of a defined value**, not a number or string comparable via `=`. When expressions contain `NULL`, SQL operates under **three-valued logic**: `TRUE`, `FALSE`, `UNKNOWN`. Thus, **`WHERE` returns only TRUE**, whereas **`CHECK` admits both TRUE and UNKNOWN**; whenever a column must hold a value, declare `NOT NULL` explicitly.

With `UNIQUE`, a **single nullable column** allows multiple NULL rows. With **composite unique keys**, Oracle allows multiple rows whose **components are all NULL**, yet **never assume a single NULL disables uniqueness checks**: partial-NULL tuples sharing the same non-NULL portion are rejected. **Composite primary keys** are completely different: every component must always be non-NULL. **Composite foreign keys** follow distinct rules when reference components are missing, often requiring `CHECK` or `NOT NULL` to prevent half-populated references.

Good constraint design **expresses business rules directly in the database**: which columns may be omitted, which value combinations must be unique, which states are valid, and which NULL combinations are permitted. Use expression-based unique indexes for conditional uniqueness, and combine `CHECK` with `NOT NULL` for multi-column validation. That allows Oracle to protect data even under concurrent Java writes, rather than relying solely on application-layer checks.
