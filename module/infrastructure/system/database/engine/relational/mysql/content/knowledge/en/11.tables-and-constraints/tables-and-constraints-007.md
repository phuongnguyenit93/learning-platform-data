# NULL in UNIQUE, CHECK, and Composite Keys

In MySQL, `NULL` represents an unknown or absent value. It is not zero, an empty string, or a default value. Because SQL uses three-valued logic (TRUE, FALSE, UNKNOWN), `NULL` directly affects filter conditions, unique indexes, check constraints, and composite keys.

Three rules to keep in mind:

1. **UNIQUE:** MySQL allows multiple rows with a `NULL` value in a column belonging to a unique index. With a multi-column unique key, if one or more key components are `NULL`, multiple combinations can coexist.
2. **CHECK:** MySQL only rejects a row when a CHECK expression evaluates to FALSE. Both TRUE and UNKNOWN results are accepted. Therefore, `CHECK (quantity > 0)` does not by itself prevent `quantity` from accepting NULL.
3. **Composite keys:** every column of a composite primary key must be NOT NULL. With a composite foreign key, if one foreign key component is NULL, InnoDB does not require finding a matching parent row for that key.

This lesson falls within the scope of `DATABASE_MYSQL`: designing tables, keys, and data constraints; controlling uniqueness, referential integrity, and business conditions; and knowing how to inspect metadata, queries, and migrations to prevent invalid data as a system evolves.

## 1. How Does NULL Differ from 0, Empty String, and DEFAULT?

The following values have distinct meanings:

| Value | Meaning |
|---|---|
| `NULL` | No value or unknown value |
| `0` | A numeric value equal to zero |
| `''` | A string of length zero |
| `'NULL'` | A four-character string consisting of N, U, L, L |
| `DEFAULT` | Requests using the default value declared for the column |

Example:

~~~sql
CREATE TABLE profile (
    profile_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    age INT NULL,
    nickname VARCHAR(80) NULL,
    note VARCHAR(100) NOT NULL DEFAULT 'No note'
);
~~~

The following rows are not equivalent:

~~~sql
INSERT INTO profile (profile_id, age, nickname)
VALUES
    (1, NULL, NULL),
    (2, 0, ''),
    (3, 25, 'An');
~~~

- Row 1 has no age and no nickname yet.
- Row 2 has an age of 0 and a nickname that is an empty string.
- Row 3 has concrete values.
- The `note` column receives its DEFAULT because it does not appear in the INSERT column list.

If a column is declared nullable, omitting it from an INSERT normally applies its declared default; if no explicit default exists, a nullable column defaults to NULL. Passing `NULL` explicitly causes MySQL to store NULL when the column allows it. On a NOT NULL column, passing NULL may be rejected or handled differently depending on SQL mode; use strict mode and do not rely on implicit value conversion.

Inspect the definition:

~~~sql
SHOW CREATE TABLE profile\G
~~~

### 1.1. NULL Does Not Equal NULL Under Ordinary Comparison

In SQL:

~~~sql
SELECT
    NULL = NULL AS ordinary_equal,
    NULL <> NULL AS ordinary_not_equal,
    NULL IS NULL AS is_null,
    NULL <=> NULL AS null_safe_equal;
~~~

The first two expressions return NULL (UNKNOWN), not TRUE or FALSE. `IS NULL` returns TRUE. The MySQL `<=>` operator is NULL-safe equality; it returns TRUE when both sides are NULL.

Therefore, do not write:

~~~sql
SELECT *
FROM profile
WHERE age = NULL;
~~~

Write instead:

~~~sql
SELECT *
FROM profile
WHERE age IS NULL;
~~~

And to find rows that have values:

~~~sql
SELECT *
FROM profile
WHERE age IS NOT NULL;
~~~

### 1.2. Three-Valued Logic

SQL uses three logical states:

| Expression | Result |
|---|---|
| TRUE AND TRUE | TRUE |
| TRUE AND FALSE | FALSE |
| TRUE AND UNKNOWN | UNKNOWN |
| FALSE AND UNKNOWN | FALSE |
| TRUE OR UNKNOWN | TRUE |
| FALSE OR UNKNOWN | UNKNOWN |
| NOT UNKNOWN | UNKNOWN |

In a `WHERE` clause, only rows where the condition evaluates to TRUE are retained. Rows yielding FALSE or UNKNOWN are filtered out.

This explains why:

~~~sql
SELECT *
FROM profile
WHERE age > 18;
~~~

does not return rows with `age IS NULL`: the expression `NULL > 18` evaluates to UNKNOWN.

## 2. NULL in Single-Column UNIQUE

A unique constraint ensures non-NULL values in the key are unique according to the data type/collation comparison rules. In MySQL, NULL is treated as unknown, so a unique index can contain multiple NULLs.

Example:

~~~sql
CREATE TABLE employee (
    employee_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    tax_code VARCHAR(30) NULL,
    UNIQUE KEY uq_employee_tax_code (tax_code)
);
~~~

The following rows can be inserted:

~~~sql
INSERT INTO employee (employee_id, tax_code)
VALUES
    (1, 'TX-001'),
    (2, NULL),
    (3, NULL);
~~~

The two rows with a NULL `tax_code` are not considered duplicates violating the unique key. However, the following fourth row is rejected:

~~~sql
INSERT INTO employee (employee_id, tax_code)
VALUES (4, 'TX-001');
~~~

Because `TX-001` already exists.

### 2.1. When Is This Behavior Useful?

Allowing multiple NULLs in a unique column fits when an attribute only exists for certain records:

- Tax codes not yet issued to every entity.
- Reference codes from an external system present only for certain transactions.
- Optional license numbers.
- Secondary emails or optional identifiers.
- Partner transaction codes that only appear when a transaction routes through that partner.

For example, a customer may not have supplied a tax code yet. The system still needs to ensure two customers never share the same tax code once a code is provided. A nullable unique column expresses this exact rule.

### 2.2. When Do You Need NOT NULL UNIQUE?

If business rules require every row to have a value and forbid duplicates, combine NOT NULL with UNIQUE:

~~~sql
CREATE TABLE login_account (
    account_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    username VARCHAR(80) NOT NULL,
    UNIQUE KEY uq_login_username (username)
);
~~~

Declaring UNIQUE alone is not enough to enforce providing a value. If `username` can be NULL, multiple rows can still lack a username.

## 3. NULL in Composite UNIQUE Keys

A composite unique key contains multiple columns. In MySQL, if one or more key components are NULL, rows can repeat the remaining combination without violating the unique constraint.

Example:

~~~sql
CREATE TABLE external_reference (
    reference_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    tenant_id BIGINT UNSIGNED NOT NULL,
    external_code VARCHAR(80) NULL,
    UNIQUE KEY uq_tenant_external_code (tenant_id, external_code)
);
~~~

You can insert:

~~~sql
INSERT INTO external_reference
    (reference_id, tenant_id, external_code)
VALUES
    (1, 10, 'A-100'),
    (2, 10, NULL),
    (3, 10, NULL),
    (4, 20, NULL);
~~~

Rows 2 and 3 share the same `tenant_id` while both have `external_code` as NULL. They are still accepted. Row 4 is also accepted because `external_code` is NULL.

Conversely, two rows with the same `tenant_id` and the same non-NULL `external_code` will violate the constraint:

~~~sql
INSERT INTO external_reference
    (reference_id, tenant_id, external_code)
VALUES (5, 10, 'A-100');
~~~

### 3.1. Case-by-Case Rules

For the unique key `(tenant_id, external_code)`:

| tenant_id | external_code | Outcome |
|---:|---|---|
| 10 | `A-100` | Allowed if it does not exist yet |
| 10 | `A-100` again | Violates UNIQUE |
| 10 | NULL | Allowed |
| 10 | NULL again | Still allowed |
| 20 | NULL | Allowed |
| NULL | `A-100` | Allowed if columns allow NULL; rows with NULL components can repeat |

Therefore, if `tenant_id` is a mandatory component of the uniqueness scope, declare it `NOT NULL`. If `external_code` is optional, verify whether allowing multiple records without codes within the same tenant matches business requirements.

### 3.2. UNIQUE Does Not Mean Every Combination Differs When NULL Is Present

A common misconception is that a composite UNIQUE key prevents two rows from sharing the same known values regardless of the remaining parts. In MySQL, NULL causes the uniqueness condition not to apply like ordinary equality comparison.

If the business wants:

- Multiple rows without an external code: keep `external_code` nullable and use unique as shown.
- Every row required to have a code: add NOT NULL.
- At most one row without a code per tenant: design an additional rule turning the missing-code case into a controllable non-NULL key; a standard unique key will not do this automatically.

Do not arbitrarily substitute empty strings for NULL. An empty string is a concrete value and will be constrained by UNIQUE just like any other value.

## 4. UNIQUE and String Collation

A unique index on a string column follows the column's collation. If the collation is case-insensitive or accent-insensitive, two differently written strings can be treated as the same value.

Example:

~~~sql
CREATE TABLE member_name (
    member_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    username VARCHAR(80)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL,
    UNIQUE KEY uq_member_username (username)
);
~~~

Under an accent-insensitive and case-insensitive collation, `'Admin'` and `'admin'` will collide. Accent variants can also be treated as equivalent.

This operates independently of NULL rules: a unique key applies both NULL handling and the collation's comparison rules for present string values.

Before changing a collation, search for values that will become duplicates under the target collation:

~~~sql
SELECT
    username COLLATE utf8mb4_0900_ai_ci AS normalized_compare,
    COUNT(*) AS total
FROM member_name
GROUP BY username COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
~~~

This is a pre-migration data audit. Resolve duplicates per business rules before rebuilding the unique index.

## 5. NULL in CHECK Constraints

A CHECK constraint validates a row's expression. In MySQL, a CHECK expression passes if it evaluates to TRUE or UNKNOWN; only FALSE causes the row to be rejected.

This is the most critical detail when combining CHECK with nullable columns.

### 5.1. CHECK May Not Block NULL

Example:

~~~sql
CREATE TABLE product (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    quantity INT NULL,
    CONSTRAINT chk_product_quantity
        CHECK (quantity > 0)
);
~~~

You can insert:

~~~sql
INSERT INTO product (product_id, quantity)
VALUES
    (1, 5),
    (2, 1),
    (3, NULL);
~~~

Row 3 is accepted because `NULL > 0` evaluates to UNKNOWN, not FALSE.

If business rules require `quantity` to have a positive value, declare both conditions:

~~~sql
CREATE TABLE product_required (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    quantity INT NOT NULL,
    CONSTRAINT chk_product_required_quantity
        CHECK (quantity > 0)
);
~~~

`NOT NULL` ensures a value exists; `CHECK` ensures that value is greater than 0. The two constraints solve two distinct problems.

### 5.2. CHECK with Optional Columns

If `quantity` may be unspecified, yet whenever present must be greater than 0, a nullable design combined with CHECK is appropriate:

~~~sql
CREATE TABLE product_optional (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    estimated_quantity INT NULL,
    CONSTRAINT chk_estimated_quantity
        CHECK (estimated_quantity IS NULL OR estimated_quantity > 0)
);
~~~

The expression clearly states the intent: accept NULL or a positive number.

In this case, the condition still evaluates to true when the value is NULL because the `IS NULL` branch is TRUE.

### 5.3. CHECK for Value Ranges

If the value is mandatory:

~~~sql
CREATE TABLE rating (
    rating_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    score DECIMAL(3, 1) NOT NULL,
    CONSTRAINT chk_rating_score
        CHECK (score >= 0 AND score <= 10)
);
~~~

If the value is optional:

~~~sql
CREATE TABLE optional_rating (
    rating_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    score DECIMAL(3, 1) NULL,
    CONSTRAINT chk_optional_rating_score
        CHECK (score IS NULL OR (score >= 0 AND score <= 10))
);
~~~

Do not assume `CHECK (score BETWEEN 0 AND 10)` automatically forbids NULL. When `score` is NULL, `BETWEEN` also yields UNKNOWN and is accepted.

### 5.4. CHECK Does Not Replace UNIQUE

CHECK only evaluates the expression for the row being inserted or updated. It cannot guarantee a value does not duplicate another row. To enforce uniqueness across rows, use UNIQUE or PRIMARY KEY.

For example, the following CHECK does not ensure `username` is unique:

~~~sql
CHECK (username <> '')
~~~

It only checks that the current row's `username` is not an empty string. To prevent duplicates, create a unique index:

~~~sql
UNIQUE KEY uq_username (username)
~~~

If `username` is mandatory, add NOT NULL.

### 5.5. CHECK Does Not Validate Relationships Across Multiple Rows or Tables

CHECK constraints are not the tool for rules requiring reads from other rows or other tables. Do not use CHECK to enforce:

- Each customer has at most one open order.
- The sum of order line items does not exceed a budget in another table.
- A parent ID must exist in another table.
- Total quantity across multiple lines must stay below a limit.

Use UNIQUE, FOREIGN KEY, transactions, triggers, or appropriate business logic depending on the rule. For referential integrity, prefer FOREIGN KEY whenever the model and engine support it.

## 6. CHECK When Multiple Columns Can Be NULL

When an expression involves multiple nullable columns, UNKNOWN can surface in unexpected ways. The best practice is to write conditions explicitly enumerating valid NULL states.

### 6.1. Two Columns Must Either Both Be Present or Both Be Absent

Suppose a record has a start and end time window. Business rules allow both to be unspecified, or both must have values with start not after end.

~~~sql
CREATE TABLE booking_window (
    window_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    starts_at DATETIME NULL,
    ends_at DATETIME NULL,
    CONSTRAINT chk_window_pair
        CHECK (
            (starts_at IS NULL AND ends_at IS NULL)
            OR
            (
                starts_at IS NOT NULL
                AND ends_at IS NOT NULL
                AND starts_at <= ends_at
            )
        )
);
~~~

This expression clearly handles all cases:

| starts_at | ends_at | Result |
|---|---|---|
| NULL | NULL | Valid |
| Has value | Has value, starts_at <= ends_at | Valid |
| Has value | NULL | Invalid |
| NULL | Has value | Invalid |
| Has value | Has value, starts_at > ends_at | Invalid |

Using `IS NULL` and `IS NOT NULL` prevents the pair-check logic from evaluating to UNKNOWN.

### 6.2. At Least One of Two Columns Must Have a Value

For example, a contact must have either an email or a phone number:

~~~sql
CREATE TABLE contact (
    contact_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    email VARCHAR(254) NULL,
    phone VARCHAR(30) NULL,
    CONSTRAINT chk_contact_method
        CHECK (email IS NOT NULL OR phone IS NOT NULL)
);
~~~

The expression only rejects rows where both are NULL. If at least one has a value, the condition passes.

Note: `NOT NULL` does not mean non-empty string. If `email` or `phone` must not be empty strings, add conditions:

~~~sql
CHECK (
    (email IS NULL OR email <> '')
    AND
    (phone IS NULL OR phone <> '')
)
~~~

And keep the CHECK requiring at least one of the two fields to be populated. In real systems, also validate email/phone format at the appropriate layer.

### 6.3. Exactly One of Two Columns Must Have a Value

If only one contact method is allowed to be present:

~~~sql
CHECK (
    (email IS NOT NULL AND phone IS NULL)
    OR
    (email IS NULL AND phone IS NOT NULL)
)
~~~

Do not write `CHECK (email <> phone)` to express this. If one side is NULL, the comparison yields UNKNOWN and fails to enforce the intended rule.

## 7. NULL in Composite PRIMARY KEYs

A primary key uniquely identifies each row and does not allow NULL. With a composite primary key, every column forming the key must be NOT NULL.

Example:

~~~sql
CREATE TABLE order_item (
    order_id BIGINT UNSIGNED NOT NULL,
    line_number INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id, line_number),
    CONSTRAINT chk_order_item_quantity CHECK (quantity > 0)
);
~~~

The primary key is the combination `(order_id, line_number)`. Every column must have a value. No two rows can share the same `order_id` and `line_number`.

If you omit NOT NULL when declaring a primary key column, MySQL still enforces non-nullability on primary key columns. However, declare it explicitly so readers understand the model and avoid confusing it with a regular unique key.

### 7.1. PRIMARY KEY vs. Nullable UNIQUE

| Property | PRIMARY KEY | UNIQUE |
|---|---|---|
| Allows NULL | No | Yes, depending on column nullability rules |
| Count per table | One | Can have multiple |
| Purpose | Row identification | Enforcing uniqueness of one or more attributes |
| InnoDB | Clustered index | Usually a secondary unique index unless chosen as clustered index |
| Composite columns | All components NOT NULL | Can contain nullable components |

Do not use a nullable UNIQUE key as a row's primary identifier if the business requires a mandatory identifier. Use a stable primary key, typically a surrogate key or a genuinely non-NULL business key.

## 8. NULL in Composite FOREIGN KEYs

A foreign key ensures child table values reference a valid key in the parent table. In InnoDB, if one or more columns in a composite foreign key are NULL, the child row is not required to match a parent row for that key.

Example:

~~~sql
CREATE TABLE region (
    country_code CHAR(2) NOT NULL,
    region_code VARCHAR(10) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (country_code, region_code)
) ENGINE = InnoDB;

CREATE TABLE customer_location (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    country_code CHAR(2) NULL,
    region_code VARCHAR(10) NULL,
    CONSTRAINT fk_customer_region
        FOREIGN KEY (country_code, region_code)
        REFERENCES region (country_code, region_code)
) ENGINE = InnoDB;
~~~

Cases:

- `('VN', 'HN')`: the matching pair must exist in the `region` table.
- `(NULL, NULL)`: no parent row reference is required.
- `('VN', NULL)`: the NULL component causes referential validation not to be performed as a complete pair.
- `(NULL, 'HN')`: likewise, because a component is NULL, no matching parent row is required.

This is useful when the relationship is optional. However, if business rules require either selecting no region at all or selecting both country and region, add a CHECK:

~~~sql
ALTER TABLE customer_location
ADD CONSTRAINT chk_customer_region_pair
CHECK (
    (country_code IS NULL AND region_code IS NULL)
    OR
    (country_code IS NOT NULL AND region_code IS NOT NULL)
);
~~~

CHECK prevents partially populated foreign keys. FOREIGN KEY continues to ensure any populated pair exists in the parent table.

### 8.1. When the Relationship Is Mandatory

If every customer must belong to a region, the simplest approach is declaring both columns NOT NULL:

~~~sql
country_code CHAR(2) NOT NULL,
region_code VARCHAR(10) NOT NULL,
FOREIGN KEY (country_code, region_code)
    REFERENCES region (country_code, region_code)
~~~

This makes it impossible to bypass the relationship using NULL.

### 8.2. When the Relationship Is Optional but Must Be Complete

Use two nullable columns, an all-or-none CHECK, and a composite FOREIGN KEY as shown above. Do not rely on the foreign key alone to prevent partially populated reference keys.

## 9. NULL in Composite Keys and Indexes

NULL does not prevent indexing. MySQL can store and look up NULL in a B-tree index. `IS NULL` queries can use an index when the execution plan deems it appropriate.

Example:

~~~sql
CREATE INDEX idx_external_code
ON external_reference (external_code);

EXPLAIN
SELECT reference_id
FROM external_reference
WHERE external_code IS NULL;
~~~

With a composite index:

~~~sql
CREATE INDEX idx_tenant_external
ON external_reference (tenant_id, external_code);
~~~

Queries filtering by the first column or both columns can use the index's leftmost prefix:

~~~sql
EXPLAIN
SELECT reference_id
FROM external_reference
WHERE tenant_id = 10
  AND external_code IS NULL;
~~~

Do not create an index solely because a column contains NULL. Consider selectivity, row count, query patterns, and write overhead. If most rows have a NULL `external_code`, an index may have low selectivity for `IS NULL`.

### 9.1. NULL and Sort Order

In MySQL, during `ORDER BY`:

- ASC: NULLs sort before non-NULL values.
- DESC: NULLs sort after non-NULL values.

You can test:

~~~sql
SELECT employee_id, tax_code
FROM employee
ORDER BY tax_code ASC;

SELECT employee_id, tax_code
FROM employee
ORDER BY tax_code DESC;
~~~

If you want a custom placement, express it explicitly:

~~~sql
SELECT employee_id, tax_code
FROM employee
ORDER BY tax_code IS NULL DESC, tax_code;
~~~

The first expression puts NULL rows first, then sorts the remaining values. Choose the ordering that fits your UI and business requirements.

## 10. NULL in Aggregate Functions and Queries

### 10.1. COUNT(*) and COUNT(column)

`COUNT(*)` counts all rows. `COUNT(column)` only counts non-NULL values.

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(tax_code) AS rows_with_tax_code,
    COUNT(*) - COUNT(tax_code) AS rows_without_tax_code
FROM employee;
~~~

This is useful for measuring data completeness.

### 10.2. SUM, AVG, MIN, and MAX

Aggregate functions such as `SUM()`, `AVG()`, `MIN()`, and `MAX()` ignore NULL values. If all input values are NULL or no rows match, the result can be NULL.

~~~sql
SELECT
    AVG(score) AS average_score,
    COUNT(score) AS scored_rows,
    COUNT(*) AS total_rows
FROM optional_rating;
~~~

If using `COALESCE(AVG(score), 0)`, verify whether the business genuinely treats "no data" as 0. An average of 0 and having no scores at all are two different states.

### 10.3. GROUP BY

In `GROUP BY`, NULL values are grouped together into a single group:

~~~sql
SELECT
    tax_code,
    COUNT(*) AS employee_count
FROM employee
GROUP BY tax_code;
~~~

The NULL group represents rows without a `tax_code`. This differs from `NULL = NULL` comparison, which evaluates to UNKNOWN.

### 10.4. NOT IN and NULL

A common bug is using `NOT IN` with a list or subquery containing NULL:

~~~sql
SELECT employee_id
FROM employee
WHERE employee_id NOT IN (
    SELECT employee_id
    FROM blocked_employee
);
~~~

If the subquery returns NULL, the comparison yields UNKNOWN for non-matching values and causes the query to return no rows at all.

You can use `NOT EXISTS` to express an anti-join cleanly:

~~~sql
SELECT e.employee_id
FROM employee AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_employee AS b
    WHERE b.employee_id = e.employee_id
);
~~~

If the join key inside can be NULL and you want NULL-safe comparison, consider the `<=>` operator or define a clear data policy.

## 11. Designing Schemas from Business Rules

Before choosing NULL/NOT NULL and UNIQUE/CHECK, describe the rule in plain sentences. For example:

| Business Rule | MySQL Design |
|---|---|
| Every account must have a unique username | `NOT NULL` + `UNIQUE` |
| Tax code is optional, but if present must be unique | Nullable + `UNIQUE` |
| Quantity must be greater than 0 | `NOT NULL` + `CHECK (quantity > 0)` |
| Rating score is optional; if present must be 0 to 10 | Nullable + CHECK allowing NULL or valid range |
| Two timestamp columns must both be present or both absent | Nullable + all-or-none CHECK |
| Composite foreign key is optional, but all parts must be filled | Nullable + all-or-none CHECK + FOREIGN KEY |
| Identifying key consists of two mandatory components | Composite PRIMARY KEY, all NOT NULL |
| Combination of tenant and external code is unique when code exists | `UNIQUE (tenant_id, external_code)`, `tenant_id` NOT NULL |

### 11.1. Table Template Combining Multiple Constraints

~~~sql
CREATE TABLE subscription (
    subscription_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    external_code VARCHAR(80) NULL,
    starts_at DATETIME NULL,
    ends_at DATETIME NULL,
    seat_count INT NOT NULL,
    PRIMARY KEY (subscription_id),
    UNIQUE KEY uq_subscription_external (tenant_id, external_code),
    CONSTRAINT chk_subscription_seats
        CHECK (seat_count > 0),
    CONSTRAINT chk_subscription_dates
        CHECK (
            (starts_at IS NULL AND ends_at IS NULL)
            OR
            (
                starts_at IS NOT NULL
                AND ends_at IS NOT NULL
                AND starts_at <= ends_at
            )
        )
) ENGINE = InnoDB;
~~~

This design expresses:

- Each subscription has a non-NULL primary key.
- `tenant_id` always has a value.
- `external_code` is optional; multiple subscriptions in the same tenant can lack a code.
- If a start time is specified, an end time must also be specified, and start is not after end.
- `seat_count` is always positive and non-NULL.

If business rules require `external_code` to be mandatory, change the column to NOT NULL. If rules require at most one subscription per tenant to lack an `external_code`, the current unique key is insufficient; a dedicated design is needed for that rule.

## 12. Allowing Only One NULL in a Unique Key: When and How to Design It

MySQL allows multiple NULLs in a unique index by default. If a business requirement truly states that at most one row may lack a value, you must map the NULL case into a controllable key value.

One approach uses a generated column with a reserved sentinel value, paired with a CHECK prohibiting real data from matching the sentinel. The following example reserves the empty string for the NULL case:

~~~sql
CREATE TABLE optional_email (
    contact_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    email VARCHAR(254) NULL,
    email_unique_key VARCHAR(254)
        GENERATED ALWAYS AS (COALESCE(email, '')) STORED,
    CONSTRAINT chk_email_not_empty
        CHECK (email IS NULL OR email <> ''),
    UNIQUE KEY uq_optional_email (email_unique_key)
) ENGINE = InnoDB;
~~~

How it works:

- If `email` is NULL, the generated column becomes the empty string.
- If `email` has a value, the generated column holds the email value.
- CHECK forbids real emails from being empty strings, so the sentinel cannot be used by business data.
- UNIQUE on the generated column allows only one empty string—meaning at most one NULL email; all other emails remain unique per the column's collation.

This technique requires CHECK to actually be enforced (MySQL 8.0.16 or later). Test collation, length, generated column expression, and migrations on the target version. If the empty string has valid meaning or no safe sentinel can be reserved, use a separate status-management table or redesign the model. Do not apply the sentinel trick unless business rules genuinely require at most one NULL.

## 13. MySQL Versions and CHECK Verification

MySQL only began enforcing CHECK constraints in MySQL 8.0.16. In earlier MySQL versions, CHECK syntax is accepted, but the constraint is not enforced. Therefore, never assume CHECK protects data simply because the table creation DDL ran without errors.

Verify the version:

~~~sql
SELECT VERSION();
~~~

Inspect the definition:

~~~sql
SHOW CREATE TABLE product_required\G
~~~

On supported versions, you can check constraint metadata in INFORMATION_SCHEMA:

~~~sql
SELECT
    CONSTRAINT_SCHEMA,
    TABLE_NAME,
    CONSTRAINT_NAME,
    CHECK_CLAUSE,
    ENFORCED
FROM information_schema.check_constraints
WHERE CONSTRAINT_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
~~~

If using MySQL 5.7 or a compatible product with different behavior, verify actual runtime support. You may need to enforce rules with NOT NULL, triggers, or application logic until upgrading. Do not treat an unenforced CHECK as a data safeguard.

## 14. Migrations Changing NULL and UNIQUE

Changing a column from nullable to NOT NULL or modifying a unique key can fail if existing data violates the new rule.

### 14.1. Check for NULLs Before Setting NOT NULL

~~~sql
SELECT COUNT(*) AS null_rows
FROM employee
WHERE tax_code IS NULL;
~~~

If the count is greater than 0, decide how to handle them:

- Populate valid values from a trusted data source.
- Keep it nullable if the business genuinely allows missing values.
- Remove records according to business rules if permitted.
- Transition to a model that explicitly records missing states.

Do not blindly replace all NULLs with empty strings or 0 just to make DDL pass.

### 14.2. Check for Duplicates Before Adding UNIQUE

~~~sql
SELECT tax_code, COUNT(*) AS total
FROM employee
WHERE tax_code IS NOT NULL
GROUP BY tax_code
HAVING COUNT(*) > 1;
~~~

If the column has a case-insensitive or accent-insensitive collation, the `GROUP BY` query applies the column's collation. Audit duplicates using the exact comparison rules the new unique index will enforce.

For composite keys:

~~~sql
SELECT
    tenant_id,
    external_code,
    COUNT(*) AS total
FROM external_reference
WHERE external_code IS NOT NULL
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
~~~

The `external_code IS NOT NULL` condition focuses on combinations where the unique key actually enforces uniqueness. If other components are also nullable, analyze each NULL combination per MySQL's rules.

### 14.3. Add CHECK After Auditing Data

For example, requiring `quantity` to be positive and non-NULL:

~~~sql
SELECT COUNT(*) AS invalid_rows
FROM product
WHERE quantity IS NULL OR quantity <= 0;
~~~

After resolving invalid rows:

~~~sql
ALTER TABLE product
    MODIFY quantity INT NOT NULL,
    ADD CONSTRAINT chk_product_quantity_positive
        CHECK (quantity > 0);
~~~

Change ordering and online capability depend on MySQL version, storage engine, and table structure. Test in a staging environment, take a backup beforehand, and evaluate lock/rebuild duration.

## 15. Common Mistakes

| Mistake or Misconception | Cause | Fix |
|---|---|---|
| UNIQUE is present, yet multiple rows lack a code | UNIQUE permits multiple NULLs | Add NOT NULL only if business requires a code |
| Composite UNIQUE still accepts two rows in the same tenant with NULL code | One key component is NULL | Clarify whether multiple unknown codes are allowed |
| `CHECK (quantity > 0)` still accepts NULL | CHECK accepts UNKNOWN | Combine with NOT NULL or an explicit NULL-handling expression |
| Start/end date CHECK fails to block one side being NULL | Comparison evaluates to UNKNOWN | Write an all-or-none CHECK using `IS NULL`/`IS NOT NULL` |
| Composite FK raises no error when one column is NULL | A foreign key component is NULL | Use NOT NULL or an all-or-none CHECK |
| `WHERE column = NULL` returns no rows | Comparison returns UNKNOWN | Use `IS NULL` |
| `NOT IN` returns unexpected results | List/subquery contains NULL | Use `NOT EXISTS` or intentionally filter NULLs |
| `COUNT(column)` is lower than `COUNT(*)` | `COUNT(column)` skips NULLs | Use both to measure completeness |
| DDL adding UNIQUE reports duplicate | Duplicate data under collation rules | Run `GROUP BY` check before migration |
| CHECK is created, yet invalid data still gets in | Older MySQL version does not enforce CHECK | Verify version and `ENFORCED` status |

## 16. NULL and Key Design Checklist

- [ ] Distinguished NULL, 0, empty string, and DEFAULT.
- [ ] Identified which columns are genuinely allowed to lack values.
- [ ] Used NOT NULL for mandatory attributes.
- [ ] Understood that nullable UNIQUE allows multiple NULLs.
- [ ] Checked NULL behavior on each component of a composite UNIQUE key.
- [ ] Declared all columns of composite PRIMARY KEYs as NOT NULL.
- [ ] Determined whether composite FOREIGN KEYs are allowed to be partially missing.
- [ ] Added an all-or-none CHECK when foreign key components must all be present or all absent.
- [ ] Understood that CHECK accepts TRUE and UNKNOWN, rejecting only FALSE.
- [ ] Combined CHECK with NOT NULL when data is mandatory.
- [ ] Verified whether the MySQL version enforces CHECK.
- [ ] Used `IS NULL`/`IS NOT NULL` or `<=>` instead of `= NULL`.
- [ ] Checked how NULL affects `COUNT`, `GROUP BY`, `NOT IN`, and `ORDER BY`.
- [ ] Audited duplicates and NULLs before migrations.
- [ ] Tested rules on a data copy before deploying.

## 17. Hands-on Exercises

### Exercise 1: Nullable UNIQUE

Create an employee table with `tax_code VARCHAR(30) NULL UNIQUE`. Insert three NULL rows and two rows with distinct codes. Try inserting an existing code again. Explain why only the duplicate code is rejected.

### Exercise 2: Composite UNIQUE

Create a unique key `(tenant_id, external_code)`. Insert two rows with the same `tenant_id` and NULL `external_code`. Then insert two rows with the same `tenant_id` and identical `external_code`. Document which cases are allowed and which are rejected.

### Exercise 3: CHECK with NULL

Create a column `score DECIMAL(3,1) NULL` and `CHECK (score BETWEEN 0 AND 10)`. Try inserting NULL, -1, 5, and 11. Then add NOT NULL and retry. Explain the outcomes using three-valued logic.

### Exercise 4: Composite Foreign Key

Create a parent table with primary key `(country_code, region_code)` and a child table with a foreign key on those same two columns. Test inserting a valid pair, a non-existent pair, both NULL, and only one column NULL. Add an all-or-none CHECK and compare.

### Exercise 5: Nullable to NOT NULL Migration

Take a table containing some NULL rows. Write an inspection query, decide how to remediate the data, and migrate the column to NOT NULL. Verify both DDL and data after the migration.

## 18. Conclusion

NULL is a distinct data state and causes SQL to operate under three-valued logic. In MySQL, UNIQUE allows multiple NULLs; this also holds for composite unique keys whenever at least one component is NULL. CHECK only rejects expressions evaluating to FALSE, while UNKNOWN is accepted. Composite primary keys disallow NULL, whereas composite foreign keys skip referential validation if a foreign key component is NULL.

When designing schemas, translate business rules into explicit constraints: NOT NULL for mandatory values, UNIQUE for uniqueness, CHECK for per-row conditions, and FOREIGN KEY for referential relationships. For composite keys with optional components, write an all-or-none CHECK if business rules require components to be present or absent together. Before migrating, check for NULLs and duplicates under the exact comparison rules of the target collation.

## Official References

- [MySQL 8.4 Reference Manual – NULL Values](https://dev.mysql.com/doc/refman/8.4/en/working-with-null.html)
- [MySQL 8.4 Reference Manual – UNIQUE Indexes](https://dev.mysql.com/doc/refman/8.4/en/create-index.html)
- [MySQL 8.4 Reference Manual – CREATE TABLE and UNIQUE Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table.html)
- [MySQL 8.4 Reference Manual – CHECK Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html)
- [MySQL 8.4 Reference Manual – Foreign Key Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table-foreign-keys.html)
- [MySQL 8.4 Reference Manual – Primary Key Optimization](https://dev.mysql.com/doc/refman/8.4/en/primary-key-optimization.html)
- [MySQL 8.4 Reference Manual – Working with NULL Values](https://dev.mysql.com/doc/refman/8.4/en/working-with-null.html)
- [MySQL 8.4 Reference Manual – Aggregate Functions](https://dev.mysql.com/doc/refman/8.4/en/aggregate-functions.html)
