# Enums, Domains, and Composite Types in PostgreSQL

In an order management system, the `status` column should only accept certain states such as `pending`, `paid`, and `cancelled`; `quantity` must be a positive integer; and a shipping address may consist of multiple components such as street, city, and postal code. If you use `text`, `integer`, and separate unvalidated columns without consistent rules, the application has to repeat validation checks in multiple places and risks storing invalid data.

PostgreSQL lets you define **custom data types** to express those rules at the database level:

- **Enum (*enumerated type*)**: a named, finite, and ordered set of allowed values.
- **Domain**: a type built on top of an existing data type, optionally with `DEFAULT`, `NOT NULL`, and `CHECK` constraints to reuse value rules.
- **Composite type**: a type consisting of multiple named fields, each with its own type, similar to the structure of a table row.

This lesson explains their syntax, usage, differences from `CHECK` constraints and lookup tables, querying, altering types after data exists, as well as the limitations that affect PostgreSQL schema design. The examples are suitable for PostgreSQL 16 and modern versions; in production deployments, verify feature behavior against the running server version.

## 1. Why Do We Need User-Defined Data Types?

Consider three columns:

~~~sql
status text,
quantity integer,
shipping_address text
~~~

Declared like this alone, the database can store:

~~~text
status           = 'paidd'
quantity         = -10
shipping_address = 'Da Nang / 123 / unknown format'
~~~

Not every value above is wrong for every business case, but they **do not clearly express** the rules of a typical order.

You could add a separate `CHECK` constraint on each table. However, if 15 tables all have a positive-quantity column or a status code with the same meaning, repeating the rule in every `CREATE TABLE` makes maintenance and expansion difficult.

Custom-defined types allow:

~~~text
                       DATA RULES
                             |
             +---------------+----------------+
             |               |                |
             v               v                v
          ENUM             DOMAIN          COMPOSITE
     Named, ordered      Value domain      Group of fields
     set of states       of a scalar       into one value
             |               |                |
             v               v                v
       order_status     positive_quantity  shipping_address
             |               |                |
             +---------------+----------------+
                             |
                             v
                    SQL columns and functions
~~~

The shared advantage is that **the type carries business-domain semantics**, rather than only physical representation semantics. However, these three constructs do not completely replace primary keys, foreign keys, unique indexes, or multi-row constraints.

## 2. Quick Comparison Table

| Criterion | Enum | Domain | Composite |
| --- | --- | --- | --- |
| Purpose | Pick one value from a fixed list | Reuse validation on a base type | Group multiple fields into one structured value |
| Created with | `CREATE TYPE ... AS ENUM (...)` | `CREATE DOMAIN ... AS ...` | `CREATE TYPE ... AS (...)` |
| Structure | Named, ordered labels | A base type and constraints | A list of attributes and data types |
| Example | `'pending'`, `'paid'` | Quantity greater than 0 | `(street, city, postal_code)` |
| Supports `CHECK` directly in definition? | Not in the domain way | Yes | Not directly across the whole composite |
| Used in tables? | Yes | Yes | Yes |
| Used as function parameters/return values? | Yes | Yes | Yes |
| Changing later | Add/rename labels; removing labels is harder | Add/modify constraints and defaults | Add/alter attributes via supported syntax |
| Best suited when | Value set is small and relatively stable | A scalar rule is reused in many places | A value has parts that always belong together |

A design decision should evaluate both **how the application queries data** and **future changeability**, not just whether the syntax is shorter.

## 3. Preparing the Practice Database

The examples use a dedicated schema `types_lab` so they do not affect other tables:

~~~sql
CREATE SCHEMA types_lab;
~~~

You need an account with `CREATE` privilege in the database and permission to create objects in the appropriate schema. Do not run type creation or deletion examples directly on a production database.

If you are using `psql`, you can check:

~~~sql
SELECT current_database(), current_user, version();
~~~

You should write **schema-qualified** object names, such as `types_lab.order_status`, to avoid accidentally creating objects in another schema when `search_path` changes.

The practice goes through three steps:

1. Separately create an enum, several domains, and a composite type.
2. Use these types in an orders table.
3. Try queries and controlled DDL changes.

## 4. Enum: Representing a Finite Set of States

An enum in PostgreSQL is a type whose valid values must belong to a **defined set of labels**.

Create an order status type:

~~~sql
CREATE TYPE types_lab.order_status AS ENUM (
    'pending',
    'paid',
    'cancelled'
);
~~~

After this statement, `types_lab.order_status` is **a data type**, not a table.

Try converting strings into enum values:

~~~sql
SELECT 'pending'::types_lab.order_status AS status;

SELECT CAST('paid' AS types_lab.order_status) AS status;
~~~

The `::` notation is PostgreSQL's type cast syntax; `CAST(... AS ...)` is the equivalent standard SQL form.

### 4.1. Enums Reject Labels Outside the Set

~~~sql
-- Intentionally cause an error to observe:
SELECT 'finished'::types_lab.order_status;
~~~

PostgreSQL is expected to reject this because `finished` is not a label of `types_lab.order_status`.

Enum values are **case-sensitive** in their labels. `'Paid'` is not automatically treated as `'paid'`:

~~~sql
-- Intentionally cause an error:
SELECT 'Paid'::types_lab.order_status;
~~~

This helps prevent certain input errors, though the application still needs to decide how to normalize, display, and localize statuses.

> When testing SQL statements that intentionally fail inside `BEGIN`, the transaction enters an aborted state. Run `ROLLBACK` before continuing with other statements in the same session.

### 4.2. Enum Ordering Is Determined at Declaration Time

A distinctive feature of PostgreSQL enums is that values have a **comparison order** based on their position in `CREATE TYPE`, not alphabetical order:

~~~sql
SELECT status
FROM (
    VALUES
        ('cancelled'::types_lab.order_status),
        ('paid'::types_lab.order_status),
        ('pending'::types_lab.order_status)
) AS v(status)
ORDER BY status;
~~~

With the definition created above, the order is:

~~~text
pending
paid
cancelled
~~~

This order comes from the declaration:

~~~text
pending < paid < cancelled
~~~

That does not mean business logic will always want to sort orders in that sequence. If the UI needs to display `paid` before `pending`, explicitly specify the desired order in `ORDER BY` or store a separate column/set of ranking rules.

Enums support comparisons between values of the **same enum type**:

~~~sql
SELECT
    'pending'::types_lab.order_status
        < 'paid'::types_lab.order_status AS is_before;
~~~

However, two different enums, even with identical labels, are **two separate types**. Do not assume they can be directly compared or assigned to each other without explicit conversion handling.

### 4.3. Using an Enum in a Table

~~~sql
CREATE TABLE types_lab.enum_demo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status types_lab.order_status NOT NULL DEFAULT 'pending'
);

INSERT INTO types_lab.enum_demo (status)
VALUES ('pending'), ('paid');

INSERT INTO types_lab.enum_demo DEFAULT VALUES;

SELECT id, status
FROM types_lab.enum_demo
ORDER BY id;
~~~

Because the column has type `types_lab.order_status`, PostgreSQL knows how to cast untyped string literals in `VALUES` to the matching enum. However, an **expression that already has type `text`** is not always implicitly converted to an enum.

Example of an explicit cast:

~~~sql
SELECT 'paid'::text::types_lab.order_status AS status;
~~~

With JDBC drivers, parameter types and binding modes affect whether PostgreSQL accepts the passed value. You should not assume an enum column and a `text` column are interchangeable without a cast in every context.

## 5. Modifying an Enum After It Is Already in Use

In practice, business states can evolve. PostgreSQL supports adding labels:

~~~sql
ALTER TYPE types_lab.order_status
ADD VALUE IF NOT EXISTS 'refunded' AFTER 'paid';
~~~

Comparison order after the change:

~~~text
pending < paid < refunded < cancelled
~~~

`IF NOT EXISTS` helps avoid errors when the label already exists. `BEFORE` and `AFTER` allow specifying the relative position of the new value.

### 5.1. Transaction Caveat When Adding Enum Values

In modern PostgreSQL versions, adding an enum value can be executed inside a transaction block, but **the new value cannot be used in the same transaction until that transaction commits**.

Example that needs to be split:

~~~sql
BEGIN;

ALTER TYPE types_lab.order_status
ADD VALUE IF NOT EXISTS 'reviewing' BEFORE 'paid';

COMMIT;

-- Use the new value after the transaction has committed.
INSERT INTO types_lab.enum_demo (status)
VALUES ('reviewing');
~~~

When writing migrations, do not combine `ADD VALUE` and data updates using the new value into the same transaction without checking PostgreSQL's version limits and enum rules.

### 5.2. Renaming a Label

~~~sql
ALTER TYPE types_lab.order_status
RENAME VALUE 'cancelled' TO 'voided';
~~~

Renaming a label changes **the displayed/referenced value under the old name** for existing rows using this enum. Queries or application code still sending the string `'cancelled'` may fail after the change. This is a *data contract* change, not just editing a label in a lookup table.

If you continue with the lab and want to keep the name `cancelled` for later examples, **do not run the `RENAME VALUE` statement above**, or use a separate test environment and proactively adjust data and application code.

### 5.3. Is Removing an Enum Label Simple?

PostgreSQL **does not provide a standard `ALTER TYPE ... DROP VALUE` operation** to safely remove an already defined label. If you want to retire an old status, the usual workflow is:

1. Inventory all columns, views, functions, and SQL statements using the enum.
2. Migrate data away from the value to be removed.
3. Create a **new enum** with the desired set of labels.
4. Alter columns to the new enum using a controlled conversion.
5. Update defaults, indexes, constraints, functions, and related dependencies.
6. Drop the old enum only when no objects depend on it.

Example illustrating the type-conversion principle:

~~~sql
-- A new enum with a different set of labels:
CREATE TYPE types_lab.order_status_v2 AS ENUM (
    'pending',
    'paid',
    'cancelled',
    'refunded'
);

-- Illustrates a migration step on the enum_demo table.
-- ONLY perform this when all existing values have a matching label
-- in order_status_v2 and other dependencies have been checked.

ALTER TABLE types_lab.enum_demo
ALTER COLUMN status DROP DEFAULT;

ALTER TABLE types_lab.enum_demo
ALTER COLUMN status TYPE types_lab.order_status_v2
USING status::text::types_lab.order_status_v2;

ALTER TABLE types_lab.enum_demo
ALTER COLUMN status SET DEFAULT 'pending'::types_lab.order_status_v2;
~~~

If you renamed `cancelled` to `voided` in the previous section, casting to `order_status_v2` in this example **will fail for rows holding `voided`**, unless you plan a value mapping. That illustrates why enum migrations must inspect **existing data**, not just the target type.

This is a design-explanation example, **not a required cleanup command** for the upcoming lab steps. It is best to keep the original `order_status` when creating the combined table in later sections.

## 6. Domain: Creating a Type with Reusable Constraints

If an enum describes a **list of labels**, a domain describes the **valid bounds of a value of a base type**.

For example, every product quantity must be an integer greater than 0:

~~~sql
CREATE DOMAIN types_lab.positive_quantity
AS integer
NOT NULL
CHECK (VALUE > 0);
~~~

In the domain definition:

- `integer` is the **base type**.
- `NOT NULL` specifies that the value cannot be null in contexts where the constraint applies.
- `VALUE` is a special keyword representing **the value being checked**.
- `CHECK (VALUE > 0)` is the domain condition applied when a value is cast/assigned into the domain.

Try:

~~~sql
SELECT 5::types_lab.positive_quantity AS valid_quantity;
~~~

Invalid cases:

~~~sql
-- Intentionally fail: not greater than 0.
SELECT 0::types_lab.positive_quantity;

-- Intentionally fail: negative number.
SELECT (-3)::types_lab.positive_quantity;

-- Intentionally fail: domain declares NOT NULL.
SELECT NULL::types_lab.positive_quantity;
~~~

### 6.1. How Does a Domain Differ from a Per-Table CHECK?

If you only define:

~~~sql
CREATE TABLE example_a (
    quantity integer NOT NULL CHECK (quantity > 0)
);

CREATE TABLE example_b (
    quantity integer NOT NULL CHECK (quantity > 0)
);
~~~

then the same rule is duplicated in two places.

With a domain:

~~~sql
CREATE TABLE example_domain_a (
    quantity types_lab.positive_quantity
);

CREATE TABLE example_domain_b (
    quantity types_lab.positive_quantity
);
~~~

both columns share the same type describing a positive quantity. A domain can also be used as a function parameter type or return type when needed.

However, **a domain does not eliminate the need for table-level constraints** when a table-specific rule is stricter or spans multiple columns.

### 6.2. Domain for Monetary Amounts

~~~sql
CREATE DOMAIN types_lab.nonnegative_money
AS numeric(14, 2)
NOT NULL
CONSTRAINT ck_nonnegative_money
CHECK (VALUE >= 0);
~~~

Example:

~~~sql
SELECT 125000.50::types_lab.nonnegative_money
       AS accepted_amount;

-- Intentionally fail:
SELECT (-0.01)::types_lab.nonnegative_money;
~~~

`numeric(14,2)` represents a decimal number with precision 14 and scale 2, suitable for monetary values that need to avoid floating-point rounding errors in many situations. Even so, choosing scale 2 **does not automatically solve** all currency issues such as currency units, currency-specific decimal places, tax rules, or rounding policies.

If an amount **cannot be 0**, create a positive domain with `VALUE > 0` instead of a nonnegative domain. Domain names should accurately reflect the business rule.

### 6.3. Domain for Order Codes

~~~sql
CREATE DOMAIN types_lab.order_code
AS text
CONSTRAINT ck_order_code_format
CHECK (VALUE ~ '^[A-Z0-9-]{3,20}$');
~~~

`~` is PostgreSQL's regular expression match operator; the pattern above illustrates a code of 3–20 characters consisting only of uppercase Latin letters, digits, and hyphens.

~~~sql
SELECT 'ORD-2026-001'::types_lab.order_code;

-- Intentionally fail because it contains lowercase letters:
SELECT 'ord-001'::types_lab.order_code;
~~~

This is an **illustrative rule**, not the universal standard for order codes. Whether an order code is unique still requires `UNIQUE` or an equivalent identifier design. **A domain `CHECK` only validates each individual value; it does not guarantee that two rows do not share the same code.**

## 7. Domains, NULL, and CHECK Expressions

PostgreSQL evaluates `CHECK` using SQL three-valued logic: a `CHECK` expression passes when it returns **true or null/unknown**; it rejects only when it returns **false**.

For example, if a domain only declares:

~~~sql
CREATE DOMAIN types_lab.quantity_check_only
AS integer
CHECK (VALUE > 0);
~~~

then:

~~~sql
SELECT NULL::types_lab.quantity_check_only;
~~~

can be accepted, because `NULL > 0` yields unknown rather than false.

To block null in the domain constraint, add `NOT NULL` or write a `CHECK` expression that explicitly rejects null, depending on the requirement.

### 7.1. If the Domain Has NOT NULL, Does the Column Still Need NOT NULL?

A domain with `NOT NULL` means the type does not accept null during normal casts and storage. However, PostgreSQL notes **cases where SQL expressions can produce NULL without always passing through domain validation**, such as the unmatched side of an outer join or a scalar subquery returning no rows.

Therefore, when a **table column must never be null**, express that rule at the **column level**:

~~~sql
CREATE TABLE types_lab.quantity_example (
    quantity types_lab.positive_quantity NOT NULL
);
~~~

Repeating `NOT NULL` at the column level does not diminish the value of the domain: the domain still reuses the positive check, while the column-level constraint clearly states the row's integrity requirement.

### 7.2. Limits of CHECK in Domains

Domains are suitable for conditions that depend solely on **the value being checked**, such as:

~~~text
quantity > 0
amount >= 0
code matches a regular expression
date falls within a fixed valid range
~~~

Do not use domains as a substitute for foreign keys:

~~~text
customer_id must exist in the customers table
order.total_amount = SUM(order_items...)
start_date <= end_date of the same row
two different rows must not use the same code
~~~

Those rules require **FOREIGN KEY, table-level CHECK, UNIQUE/EXCLUDE**, triggers, transactions, or an appropriate data model—they cannot be solved with a scalar-validating domain alone.

A domain `CHECK` should use expressions with **stable/immutable semantics** for the same input value. If it relies on a function whose behavior changes over time or based on external configuration, already stored values may cease to satisfy the new rule without PostgreSQL automatically re-scanning them at all times. Modifying a function used by a CHECK constraint must be managed as a data migration.

## 8. Evolving a Domain as Business Rules Grow

A domain is an independent object, so its constraints can be updated without modifying the DDL of every column referencing it.

Example of adding an upper bound on monetary amounts:

~~~sql
ALTER DOMAIN types_lab.nonnegative_money
ADD CONSTRAINT ck_money_upper_limit
CHECK (VALUE <= 999999999999.99)
NOT VALID;
~~~

Meaning:

- `ADD CONSTRAINT` adds a new rule.
- `NOT VALID` defers verifying all existing data holding that domain type across related objects.
- New values or updates where the constraint is enforced must still comply with the new check.
- After reviewing historical data, you can ask PostgreSQL to validate it.

~~~sql
ALTER DOMAIN types_lab.nonnegative_money
VALIDATE CONSTRAINT ck_money_upper_limit;
~~~

If old data violates the rule, the validation step can fail; you need to fix the data or design before treating the new constraint as valid.

To drop a domain constraint that is no longer appropriate:

~~~sql
ALTER DOMAIN types_lab.nonnegative_money
DROP CONSTRAINT ck_money_upper_limit;
~~~

**Do not add or drop constraints on a shared domain in production without inventorying all tables using it.** A change to one domain can affect many columns, functions, and applications at once.

### 8.1. How Can a Domain DEFAULT Help?

A domain can have a default:

~~~sql
CREATE DOMAIN types_lab.default_priority
AS integer
DEFAULT 1
CHECK (VALUE BETWEEN 1 AND 5);
~~~

When a column uses the domain without its own specific default, PostgreSQL can use the domain's default in appropriate contexts. **A column-level default overrides the domain's default**, so a domain default should not be relied upon to completely replace table-level default policies.

Setting a default is not equivalent to `NOT NULL`: the default value only takes effect when defaults are used; it does not automatically turn every explicit null into 1.

### 8.2. Domains Can Be Based on Types Other Than integer

Domains can be built on `text`, `numeric`, `date`, and many compatible base types. In PostgreSQL, you can also create a domain over an enum type or a composite type when you need to combine appropriate rules.

Example of a status domain for a narrower workflow:

~~~sql
CREATE DOMAIN types_lab.open_order_status
AS types_lab.order_status
CHECK (VALUE IN ('pending', 'paid'));
~~~

However, if you repeatedly have to create many domains just to pick subsets of an enum for constantly changing states, consider a lookup/status table model with explicit relationships instead.

## 9. Composite Type: One Value with Multiple Attributes

A composite type describes a **multi-field structure**:

~~~sql
CREATE TYPE types_lab.shipping_address AS (
    line1 text,
    city text,
    postal_code text
);
~~~

The `shipping_address` type has three fields:

~~~text
shipping_address
├── line1        text
├── city         text
└── postal_code  text
~~~

This is **a data type**, not a table. It does not store rows on its own and has no primary key or indexes of its own.

### 9.1. Constructing a Composite Value with ROW

~~~sql
SELECT ROW(
    '12 Nguyen Hue',
    'Ho Chi Minh City',
    '700000'
)::types_lab.shipping_address AS destination;
~~~

`ROW(...)` is a *row constructor*. The result is cast to `types_lab.shipping_address`, where value positions must match the order of the type's attributes.

You can use string representation syntax for composites, but with data containing commas, quotes, and nulls, literal formatting becomes complex and error-prone. In queries where you have control, `ROW(...)::type` is usually much easier to read.

### 9.2. Accessing Fields of a Composite

Place a value in a CTE:

~~~sql
WITH sample AS (
    SELECT ROW(
        '12 Nguyen Hue',
        'Ho Chi Minh City',
        '700000'
    )::types_lab.shipping_address AS address
)
SELECT
    (address).line1 AS line1,
    (address).city AS city,
    (address).postal_code AS postal_code
FROM sample;
~~~

Notice the parentheses in `(address).city`. PostgreSQL generally requires parentheses when referencing a field of a **composite expression**, to avoid ambiguity with `table.column` syntax.

You can expand the fields of a composite into multiple columns:

~~~sql
WITH sample AS (
    SELECT ROW('A', 'Da Nang', '550000')
           ::types_lab.shipping_address AS address
)
SELECT (address).*
FROM sample;
~~~

In real queries, if the expression inside the parentheses is an **expensive function**, expanding `(function_call(...)).*` can cause the function to be evaluated multiple times depending on the plan. Use a subquery, `LATERAL`, or a clear structure to avoid repeated evaluation when necessary.

## 10. Using a Composite Type in a Table

Example table storing a structured address value:

~~~sql
CREATE TABLE types_lab.address_demo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recipient text NOT NULL,
    destination types_lab.shipping_address NOT NULL,
    CONSTRAINT ck_address_city_present
        CHECK (
            (destination).city IS NOT NULL
            AND length(btrim((destination).city)) > 0
        )
);
~~~

Insert data:

~~~sql
INSERT INTO types_lab.address_demo
    (recipient, destination)
VALUES
    (
        'Lan',
        ROW('12 Nguyen Hue', 'Ho Chi Minh City', '700000')
            ::types_lab.shipping_address
    ),
    (
        'Minh',
        ROW('8 Bach Dang', 'Da Nang', '550000')
            ::types_lab.shipping_address
    );
~~~

Read individual fields:

~~~sql
SELECT
    id,
    recipient,
    (destination).line1 AS line1,
    (destination).city AS city
FROM types_lab.address_demo
ORDER BY id;
~~~

Filter by a composite attribute:

~~~sql
SELECT id, recipient
FROM types_lab.address_demo
WHERE (destination).city = 'Da Nang';
~~~

### 10.1. Updating One Field of a Composite

~~~sql
UPDATE types_lab.address_demo
SET destination.city = 'Hue'
WHERE recipient = 'Minh';
~~~

In the `SET` clause, PostgreSQL supports assigning to a single field of a composite column like `destination.city`. In read expressions in `SELECT` or `WHERE`, writing `(destination).city` disambiguates it clearly.

You can also replace **the entire composite value**:

~~~sql
UPDATE types_lab.address_demo
SET destination = ROW(
    '22 Le Loi',
    'Da Nang',
    '550000'
)::types_lab.shipping_address
WHERE recipient = 'Minh';
~~~

Each `UPDATE` above actually modifies the test data. If you only want to observe and then revert, run it inside a transaction:

~~~sql
BEGIN;

UPDATE types_lab.address_demo
SET destination.city = 'Can Tho'
WHERE recipient = 'Lan';

SELECT (destination).city
FROM types_lab.address_demo
WHERE recipient = 'Lan';

ROLLBACK;
~~~

### 10.2. Composites Do Not Automatically Enforce Per-Attribute Constraints

In the syntax:

~~~sql
CREATE TYPE types_lab.shipping_address AS (
    line1 text,
    city text,
    postal_code text
);
~~~

you cannot declare `city text NOT NULL` or `CHECK (length(city) > 0)` directly inside `CREATE TYPE ... AS (...)` in the same way as in `CREATE TABLE`.

If a table needs to require a city:

~~~sql
CHECK (
    (destination).city IS NOT NULL
    AND btrim((destination).city) <> ''
)
~~~

then place the constraint on the **table** or use domains for the relevant fields.

Example using a domain to constrain an attribute:

~~~sql
CREATE DOMAIN types_lab.nonblank_text AS text
NOT NULL
CHECK (length(btrim(VALUE)) > 0);

CREATE TYPE types_lab.strong_address AS (
    line1 types_lab.nonblank_text,
    city types_lab.nonblank_text,
    postal_code text
);
~~~

Domains on `line1` and `city` reject empty/blank values during checked assignments, but **the entire composite value itself can still be null in expression contexts**. If a column requires an address, keep `NOT NULL` at the column level and consider appropriate table-level constraints.

### 10.3. Composites Can Contain NULL in Some Fields

~~~sql
SELECT ROW(
    '12 Nguyen Hue',
    'Ho Chi Minh City',
    NULL
)::types_lab.shipping_address AS address;
~~~

The value above can be valid because `postal_code` is declared as `text` with no not-null constraint. That differs from a row where **the entire composite** is null.

PostgreSQL has special rules for `IS NULL` / `IS NOT NULL` when applied to row/composite values: a row where all fields are null may evaluate to `IS NULL`; a row where only some fields are null may **fail both checks compared to naive intuition**. Therefore, when you want to check a required field, check **that field directly** instead of inferring from `destination IS NOT NULL`.

## 11. Composites Can Serve as Function Parameter and Return Types

Beyond table columns, composites are very useful in function signatures.

~~~sql
CREATE FUNCTION types_lab.format_shipping_city(
    p_address types_lab.shipping_address
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT ($1).city || ' - ' || ($1).line1
$$;
~~~

Call the function:

~~~sql
SELECT types_lab.format_shipping_city(
    ROW(
        '12 Nguyen Hue',
        'Ho Chi Minh City',
        '700000'
    )::types_lab.shipping_address
) AS formatted_address;
~~~

The function accepts **a single address value** instead of three separate parameters `line1`, `city`, and `postal_code`. This ties the function signature to a structured domain concept.

In return, changing the composite structure can affect every function, table, and query using that type. The benefit of reuse comes with **DDL dependencies**.

### 11.1. Functions Returning a Composite

~~~sql
CREATE FUNCTION types_lab.make_shipping_address(
    p_line1 text,
    p_city text,
    p_postal_code text
)
RETURNS types_lab.shipping_address
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT ROW(
        p_line1, p_city, p_postal_code
    )::types_lab.shipping_address
$$;
~~~

Example:

~~~sql
SELECT (
    types_lab.make_shipping_address(
        '18 Tran Phu', 'Hue', '530000'
    )
).city AS city_name;
~~~

This style is useful for SQL APIs with a fixed structure. But if the result is **a set of multiple rows** with relationships and frequent filtering/joining, a relational table or `RETURNS TABLE (...)` can be more appropriate than packing everything into a composite.

## 12. Tables Automatically Have a Row Type

One common point of confusion: PostgreSQL **automatically creates a composite row type** when you create a table:

~~~sql
CREATE TABLE types_lab.warehouses (
    warehouse_id bigint PRIMARY KEY,
    name text NOT NULL
);
~~~

The table `types_lab.warehouses` is both a **relation** and has a **row type** describing its columns. Thus, PostgreSQL functions can return values of the table's row type, and row expressions can use the corresponding type.

However, a table's row type and the **table's constraints** do not have an "enforced everywhere" relationship like inserting into the table:

- `PRIMARY KEY` and `UNIQUE` are constraints tied to data **within the table**.
- If an expression constructs a composite value with the table's row type, do not assume table constraints automatically run on every standalone expression of that type.
- Scalar rules that need reuse outside the table may be better suited to a **domain**.

This is also why you should avoid creating a `CREATE TYPE` with the same name as the row type PostgreSQL generates for a table in the same schema.

## 13. Composite Types, Arrays, and JSONB: Which Should You Choose?

If an order has one address with three fixed attributes, a composite can be neat. But if an order has **many items**, each with price, quantity, SKU, and update history, storing a single array of composites inside the order usually makes querying and relationship enforcement harder.

| Need | Usually Sensible Design Direction |
| --- | --- |
| A single value with a few fixed fields, usually read/written together | Composite |
| A scalar value needing reusable validation rules | Domain |
| A fixed list of statuses that rarely changes | Enum |
| Multiple child rows needing foreign keys, indexes, and independent queries | Relational table |
| Metadata whose structure changes frequently | `jsonb` when appropriate |
| A list of same-typed elements with simple structure | Array, after weighing query limitations |

### 13.1. Composite vs. JSONB

Composite:

~~~sql
ROW('12 Nguyen Hue', 'Da Nang', '550000')
    ::types_lab.shipping_address
~~~

JSONB:

~~~sql
'{
  "line1": "12 Nguyen Hue",
  "city": "Da Nang",
  "postal_code": "550000"
}'::jsonb
~~~

A composite has **predefined** field structure and types, checked by PostgreSQL on cast. JSONB is more flexible when keys vary across records, but ensuring a key is present, has the right type, and satisfies business rules typically requires extra mechanisms.

If the application constantly filters by `city`, you need to evaluate appropriate indexes, statistics, and write costs for **both** representations. Composites do not automatically create per-field indexes.

### 13.2. Composite vs. Separate Columns in a Table

Separate columns design:

~~~sql
CREATE TABLE types_lab.address_columns_demo (
    id bigint PRIMARY KEY,
    line1 text,
    city text,
    postal_code text
);
~~~

This approach allows:

- Simple indexes directly on `city`.
- Per-column constraints, foreign keys, or multi-column combinations.
- Querying, statistics, and column migrations using the standard table model.

A composite fits when you want to pass **an address value as a single unit** in columns/functions, not because it is always faster or safer than three separate columns.

## 14. Combined Practice Using All Three Type Kinds

Create an `orders` table using an enum for status, domains for quantity/unit price/order code, and a composite for the address.

> If you ran the `RENAME VALUE` or `order_status_v2` migration statements in section 5, make sure `types_lab.order_status` still contains the labels used below. This section assumes you kept the original enum with `pending`, `paid`, and `cancelled`.

~~~sql
CREATE TABLE types_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_code types_lab.order_code NOT NULL UNIQUE,
    status types_lab.order_status NOT NULL DEFAULT 'pending',
    quantity types_lab.positive_quantity NOT NULL,
    unit_price types_lab.nonnegative_money NOT NULL,
    shipping_address types_lab.shipping_address NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_order_shipping_city
        CHECK (
            (shipping_address).city IS NOT NULL
            AND btrim((shipping_address).city) <> ''
        )
);
~~~

This is a **simplified table for the data types lesson**, not modeling a full real-world multi-line order or refund workflow.

### 14.1. Inserting Valid Values

~~~sql
INSERT INTO types_lab.orders (
    order_code,
    status,
    quantity,
    unit_price,
    shipping_address
)
VALUES
    (
        'ORD-001',
        'paid',
        2,
        75000.00,
        ROW(
            '12 Nguyen Hue',
            'Ho Chi Minh City',
            '700000'
        )::types_lab.shipping_address
    ),
    (
        'ORD-002',
        'pending',
        1,
        125000.00,
        ROW(
            '8 Bach Dang',
            'Da Nang',
            '550000'
        )::types_lab.shipping_address
    );
~~~

The strings `'paid'` and `'pending'` are inferred as the enum according to the target column type; quantity and price are validated by their domains.

### 14.2. Reading and Computing Values

~~~sql
SELECT
    order_id,
    order_code,
    status,
    quantity,
    unit_price,
    quantity * unit_price AS estimated_total,
    (shipping_address).city AS shipping_city
FROM types_lab.orders
ORDER BY order_id;
~~~

Since `quantity` is a domain over `integer` and `unit_price` is a domain over `numeric`, arithmetic operations are supported according to PostgreSQL's type resolution rules. The expression `quantity * unit_price` has a result type deduced from its operands/base types and **does not automatically become `types_lab.nonnegative_money` merely because one operand uses that domain**.

If a computed result needs to obey a specific domain, you can cast it explicitly:

~~~sql
SELECT
    (quantity * unit_price)
        ::types_lab.nonnegative_money AS total_amount
FROM types_lab.orders;
~~~

### 14.3. Testing Errors to See Each Type's Role

Run **each statement separately**:

~~~sql
-- Non-existent enum label:
INSERT INTO types_lab.orders (
    order_code, status, quantity, unit_price, shipping_address
)
VALUES (
    'ORD-003',
    'in_delivery',
    1,
    15000.00,
    ROW('A', 'Da Nang', '550000')
        ::types_lab.shipping_address
);
~~~

~~~sql
-- Quantity domain violation:
INSERT INTO types_lab.orders (
    order_code, status, quantity, unit_price, shipping_address
)
VALUES (
    'ORD-004',
    'pending',
    -2,
    15000.00,
    ROW('A', 'Da Nang', '550000')
        ::types_lab.shipping_address
);
~~~

~~~sql
-- Table-level CHECK violation because city is empty:
INSERT INTO types_lab.orders (
    order_code, status, quantity, unit_price, shipping_address
)
VALUES (
    'ORD-005',
    'pending',
    2,
    15000.00,
    ROW('A', '', '550000')
        ::types_lab.shipping_address
);
~~~

These three errors occur at **three different validation layers**:

| Case | Protection Layer |
| --- | --- |
| `status = 'in_delivery'` | Enum does not contain that label |
| `quantity = -2` | `positive_quantity` domain |
| `shipping_address.city = ''` | `CHECK` constraint on the `orders` table |

This shows that data types and table constraints **complement each other**; not all rules can be folded into a single type kind.

### 14.4. Filtering by Enum and Composite Field

~~~sql
SELECT
    order_code,
    status,
    (shipping_address).city AS city
FROM types_lab.orders
WHERE status = 'paid'::types_lab.order_status
ORDER BY created_at DESC;
~~~

~~~sql
SELECT order_code
FROM types_lab.orders
WHERE (shipping_address).city = 'Da Nang';
~~~

If filtering by status or city happens frequently on a large table, you can consider indexes.

~~~sql
CREATE INDEX idx_orders_status_created
ON types_lab.orders (status, created_at DESC);

CREATE INDEX idx_orders_shipping_city
ON types_lab.orders (((shipping_address).city));
~~~

`idx_orders_shipping_city` is an **expression index** on a field of the composite. The extra parentheses are needed for PostgreSQL to parse the expression properly. Indexes should only be created when workload and `EXPLAIN` show meaningful benefit; every index carries storage and write-maintenance overhead.

## 15. Enum vs. Status Lookup Table: Design Choice

An alternative design to an enum is a status lookup table:

~~~sql
CREATE TABLE types_lab.order_status_lookup (
    status_code text PRIMARY KEY,
    display_name text NOT NULL,
    sort_rank integer NOT NULL UNIQUE,
    is_active boolean NOT NULL DEFAULT true
);

INSERT INTO types_lab.order_status_lookup
    (status_code, display_name, sort_rank)
VALUES
    ('pending', 'Pending', 10),
    ('paid', 'Paid', 20),
    ('cancelled', 'Cancelled', 30);
~~~

A business table can then use:

~~~sql
status_code text NOT NULL
    REFERENCES types_lab.order_status_lookup(status_code)
~~~

This **illustrates an alternative design**, not a direct modification to the `orders.status` column in the current lab.

| Criterion | Enum | Lookup Table + FK |
| --- | --- | --- |
| Small, rarely changing value set | Very suitable | Also suitable |
| Adding a label | `ALTER TYPE ... ADD VALUE` | `INSERT` a new lookup row |
| Removing or retiring a status | Hard to cleanly drop a label | Can mark `is_active` or migrate data before deleting |
| Multilingual display labels | Usually managed in app or separate table | Can add translation tables or metadata |
| Flexible display ordering | Enum order is fixed by declaration | Can use `sort_rank` |
| Needs status metadata | Cannot hold arbitrary metadata inside enum | Easy to add columns |
| Enforcing valid values | Enforced by the type itself | Enforced by foreign key |

**Choose an enum when the label set is stable and carries clear type semantics.** If the product requires operations teams to self-serve new statuses, rename labels, attach rich metadata, or continuously manage status lifecycles, a lookup table is usually more flexible.

Status is not always just a list of values. Whether an order **can transition from pending to paid** is a *state transition rule*, which may require transactions, business logic, or triggers. An enum only guarantees the value belongs to the defined set; **it does not automatically restrict state transitions**.

## 16. Domain vs. Table-Level CHECK?

Two options:

~~~sql
-- Rule attached directly to a single table column.
quantity integer NOT NULL CHECK (quantity > 0)

-- Rule defined as a shared type.
quantity types_lab.positive_quantity NOT NULL
~~~

A domain is useful when:

- Multiple tables or functions share the same meaning of positive quantity, region code, or nonnegative money.
- You want to encapsulate scalar conversion/validation rules into a well-named object.
- Changes to the shared rule must be centrally managed with a testing process.

A table-level `CHECK` is useful when:

- The rule applies to only one table.
- The condition depends on **multiple columns in the same row**, such as `end_at >= start_at`.
- You want to keep the business rule close to the specific table structure.

Example:

~~~sql
CREATE TABLE types_lab.booking_demo (
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    CONSTRAINT ck_booking_period
        CHECK (ends_at > starts_at)
);
~~~

No scalar domain on `ends_at` alone knows the `starts_at` value of **the same row**. This is a natural case for a table-level `CHECK`.

### When Over-Sharing a Domain Can Become a Drawback

Suppose the domain `nonnegative_money` is used for **base price**, **refund amount**, and **credit limit**. One day business requirements change: one kind of amount needs to allow negative values for adjustment entries, while another does not.

If every column shares the exact same domain, changing the shared constraint could weaken protection on unrelated tables. In that case, you should have **distinct domains by semantic meaning**, or use a base type with separate table-level constraints. Reuse is only beneficial when **the rules are genuinely identical**, not merely because the columns are all `numeric`.

## 17. Changing Composite Structure and Dependency Impact

PostgreSQL provides syntax to alter composite attributes:

~~~sql
ALTER TYPE types_lab.shipping_address
ADD ATTRIBUTE country_code text;
~~~

After adding the attribute, the type has an extra field:

~~~text
shipping_address
├── line1
├── city
├── postal_code
└── country_code
~~~

However, this affects any place constructing the composite value **positionally**:

~~~sql
ROW('A', 'Da Nang', '550000')::types_lab.shipping_address
~~~

which has three fields and may no longer cast cleanly to the new four-attribute type. Functions, import scripts, prepared statements, or drivers mapping by field count/order also need review.

Adding an attribute to a composite **does not automatically populate a valid `country_code` value for all existing rows**. You need a plan to update data and applications, handle nulls/defaults, and maintain compatibility across versions.

### 17.1. Other ALTER TYPE Operations for Composites

PostgreSQL supports operations such as:

~~~sql
-- Syntax illustrations; do not run all at once on a type in use.
ALTER TYPE types_lab.shipping_address
RENAME ATTRIBUTE postal_code TO zip_code;

ALTER TYPE types_lab.shipping_address
ALTER ATTRIBUTE postal_code TYPE varchar(20);

ALTER TYPE types_lab.shipping_address
DROP ATTRIBUTE postal_code;
~~~

These statements are **separate change options**; if you already ran `RENAME ATTRIBUTE`, the name `postal_code` no longer exists for the next two statements. Do not run them as a mandatory sequence. Dependent objects may cause PostgreSQL to reject a change or require additional handling.

### 17.2. When Should You Avoid Composites in Stable APIs?

If many external applications depend on a composite type with numerous fields and its schema changes frequently, adding or renaming fields can become a **breaking change**.

Possible strategies include:

- Keep the composite type stable as a function interface.
- Create a `shipping_address_v2` type when the data contract changes substantially.
- Use explicit migrations to switch columns/functions to the new type.
- For variable payloads or flexible exchange documents, consider JSONB with appropriate validation.

Do not modify a composite used system-wide just to add one field for a single screen.

## 18. Inspecting Metadata for Enums, Domains, and Composites

After creating the types, you can inspect them directly via the system catalogs.

### 18.1. Listing User-Defined Types

~~~sql
SELECT
    n.nspname AS schema_name,
    t.typname AS type_name,
    t.typtype,
    CASE t.typtype
        WHEN 'e' THEN 'enum'
        WHEN 'd' THEN 'domain'
        WHEN 'c' THEN 'composite'
        ELSE 'other'
    END AS type_kind
FROM pg_type AS t
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE n.nspname = 'types_lab'
  AND t.typtype IN ('e', 'd', 'c')
ORDER BY type_kind, type_name;
~~~

`typtype = 'c'` also includes **row types automatically created for tables**, not just composites explicitly declared with `CREATE TYPE ... AS (...)`. When listing them, expect the output to include `orders`, `address_demo`, or other practice tables.

### 18.2. Viewing Enum Labels and Order

~~~sql
SELECT
    t.typname AS enum_name,
    e.enumlabel AS label,
    e.enumsortorder AS sort_order
FROM pg_type AS t
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
JOIN pg_enum AS e
    ON e.enumtypid = t.oid
WHERE n.nspname = 'types_lab'
  AND t.typname = 'order_status'
ORDER BY e.enumsortorder;
~~~

`pg_enum.enumsortorder` stores ordering information; you should not treat each label's OID or alphabetical order as a reliable substitute for `ORDER BY` on an enum.

### 18.3. Viewing Domains and Base Types

~~~sql
SELECT
    t.typname AS domain_name,
    format_type(t.typbasetype, t.typtypmod) AS base_type,
    t.typnotnull AS domain_not_null,
    t.typdefault AS domain_default
FROM pg_type AS t
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE n.nspname = 'types_lab'
  AND t.typtype = 'd'
ORDER BY t.typname;
~~~

To view domain CHECK constraints:

~~~sql
SELECT
    t.typname AS domain_name,
    c.conname AS constraint_name,
    pg_get_constraintdef(c.oid) AS definition,
    c.convalidated AS is_validated
FROM pg_constraint AS c
JOIN pg_type AS t
    ON t.oid = c.contypid
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE n.nspname = 'types_lab'
  AND t.typtype = 'd'
ORDER BY t.typname, c.conname;
~~~

### 18.4. Viewing Fields of Explicitly Declared Composites

~~~sql
SELECT
    t.typname AS composite_name,
    a.attnum AS attribute_position,
    a.attname AS attribute_name,
    format_type(a.atttypid, a.atttypmod) AS attribute_type
FROM pg_type AS t
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
JOIN pg_class AS cl
    ON cl.oid = t.typrelid
   AND cl.relkind = 'c'
JOIN pg_attribute AS a
    ON a.attrelid = cl.oid
WHERE n.nspname = 'types_lab'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY t.typname, a.attnum;
~~~

`relkind = 'c'` focuses on explicitly declared composite types rather than including the row types of regular tables.

In `psql`, meta-commands such as `\dT+` help inspect user-defined data types. When you need to find **actual dependencies**, query `pg_depend` along with related catalogs, because a type may be referenced across multiple tables and functions.

## 19. Permissions, Schemas, and Type Lifecycle

Enums, domains, and composites are all PostgreSQL **schema objects**.

An account needs appropriate privileges:

- To create a type in a schema, the role needs permission to create objects in that schema.
- To use a type in an object or expression, `USAGE` privilege on the schema and on the type may be required according to the applicable rules.
- To alter or drop a type, ownership or corresponding administrative privileges are required.

Illustrative privilege grants:

~~~sql
GRANT USAGE ON SCHEMA types_lab TO app_role;

GRANT USAGE ON TYPE
    types_lab.order_status,
    types_lab.positive_quantity,
    types_lab.shipping_address
TO app_role;
~~~

The statements above are illustrative; `app_role` must exist. They **do not grant `SELECT`, `INSERT`, or `UPDATE` privileges on tables**. Type usage privileges and table data-manipulation privileges are separate control layers.

### 19.1. DROP TYPE RESTRICT and CASCADE

~~~sql
-- Conservative default when dependent objects exist:
DROP TYPE types_lab.order_status RESTRICT;

-- More dangerous: may cascade to dependent objects.
DROP TYPE types_lab.order_status CASCADE;
~~~

When a type is used by a table column, `RESTRICT` normally refuses to drop it. `CASCADE` can cause PostgreSQL to **drop essential dependent objects**, including columns or schema components using the type, depending on the dependency graph.

Therefore, **never run `DROP TYPE ... CASCADE` just to clear a duplicate-name error in an environment with real data**. Inventory all affected columns, views, functions, and constraints first.

### 19.2. Type Changes Impact Many Places

In a large schema, a `positive_quantity` domain might be used across 12 tables, several functions, and views. Editing a domain constraint changes **the shared rule**, while changing a composite field or enum label can alter the data contract across many clients.

You should have:

1. A list of all places using the type.
2. A plan to update code and schema in coordination.
3. Migration testing in staging with representative data.
4. A backfill/reconciliation plan.
5. Appropriate backups and rollback procedures.

Reuse reduces duplicate definitions, but it also gives type changes a **broader blast radius**.

## 20. Choosing Types When Integrating with Java/JDBC

When working from Java, custom PostgreSQL types may require more explicit handling than basic types like `integer` and `varchar`.

### Enums and Bound Parameters

A clear way to write SQL with string parameters:

~~~sql
SELECT order_id, order_code
FROM types_lab.orders
WHERE status = CAST(? AS types_lab.order_status);
~~~

With PostgreSQL JDBC, the `?` placeholder is handled by the driver as a prepared statement parameter. How values are bound depends on the driver and application mapping. Wrappers such as `PGobject` or an appropriate mapping framework can be used; do not assume a PostgreSQL enum **automatically turns into** a `java.lang.Enum` in every environment.

### Domains on the Java Side

A domain has a base type, so values read via the driver can generally be handled as the corresponding base type (e.g., `integer` or `BigDecimal`) depending on the API and mapping. However, domain constraints are enforced by PostgreSQL upon receiving values—they do not auto-generate a Java validation layer.

The application still needs input validation to return friendly error messages, but **application-side validation should not be treated as the sole protection layer**.

### Composites on the Java Side

Composites have a wire format over the PostgreSQL protocol; automatic mapping to a Java record/POJO is not always provided out of the box by a basic JDBC driver. Options include:

- Writing SQL that extracts fields: `(shipping_address).city AS city` to map individual columns.
- Using custom driver/ORM mapping APIs where supported.
- Using regular columns or JSONB when API and structural-evolution requirements make composites awkward.

Do not pick a composite merely because it "looks like a Java object". Prioritize a structure that makes sense for **queries, constraints, and migrations in PostgreSQL**.

## 21. Common Mistakes

### Mistake 1: Using an enum for a catalog updated every day

Enums suit stable label sets. For dynamic administrative catalogs, a lookup table makes adding metadata, deactivating entries, or deleting items by policy much easier.

### Mistake 2: Assuming enum order is alphabetical

`ORDER BY status` sorts by the declaration order of enum values, not alphabetically. If a different business order is required, write the corresponding sorting logic.

### Mistake 3: Thinking you can remove an enum label with a single DROP VALUE

Changing a label set by removing a value usually requires migrating to a new enum along with handling existing data and dependencies.

### Mistake 4: Using a domain to enforce multi-table relationships

A domain `CHECK (VALUE > 0)` protects a scalar. It does not replace foreign keys, unique constraints, or transactions needed for multi-row conditions.

### Mistake 5: Writing CHECK and forgetting NULL

`CHECK (VALUE > 0)` does not block null by itself, because unknown is not false. Use `NOT NULL` on the domain/column when business rules require it.

### Mistake 6: Assuming composites inherently support NOT NULL, UNIQUE, and FK per field

`CREATE TYPE ... AS (...)` defines field structure; it does not provide the full constraint system of `CREATE TABLE`. Use domains for fields or table-level constraints when needed.

### Mistake 7: Using a composite array instead of a one-to-many detail table

An array of composites in a column does not provide per-element foreign keys, relational indexing, or independent row-level updates like a relational child table.

### Mistake 8: Altering a composite structure without checking ROW constructors

Adding a field breaks positional `ROW(...)::type` calls written for the old field count. Inventory functions, applications, and data beforehand.

### Mistake 9: Adding indexes for custom types without looking at the workload

Enums, domains, and composites **do not automatically guarantee fast queries**. Indexes should be chosen based on `WHERE`, `JOIN`, `ORDER BY`, and data distribution, while weighing write overhead.

### Mistake 10: Validating values only in the application

An application may have other write paths such as imports, operational scripts, or new services. PostgreSQL data types and constraints maintain consistency right where data is stored.

## 22. Practice Exercises

These exercises are based on the `types_lab` schema; you can predict the outcome first and then test on a PostgreSQL lab instance. Do not run drop/structural commands on a database containing data you need to keep.

### Exercise 1. Choose the Appropriate Construct

Choose enum, domain, composite, or relational table for each case:

1. Article status: `draft`, `published`, `archived`, very rarely added to.
2. An order quantity that must be greater than 0, applied across multiple tables.
3. A coordinate consisting of longitude and latitude, passed into several functions.
4. An order containing multiple product line items, each needing its own foreign key and indexes.

### Exercise 2. Create a New Enum

Write a statement to create `types_lab.review_state` with labels `new`, `approved`, `rejected` in that order. Then construct an `'approved'` value with an explicit cast.

### Exercise 3. Predict ORDER BY

Given:

~~~sql
CREATE TYPE types_lab.level_code AS ENUM (
    'medium', 'low', 'high'
);
~~~

Will `ORDER BY level_code` put `low` before `medium`? Why or why not?

### Exercise 4. Domain and NULL

Given:

~~~sql
CREATE DOMAIN types_lab.score AS integer
CHECK (VALUE >= 0 AND VALUE <= 100);
~~~

Can `NULL::types_lab.score` be accepted? If a table's `score` column must require a value, write the appropriate column declaration.

### Exercise 5. Domain and UNIQUE

The `types_lab.order_code` domain only has a format constraint. Can two rows both have `order_code = 'ORD-001'`? Which constraint should be added at the table level to prevent duplicates?

### Exercise 6. Accessing Composite Fields

Given column `destination types_lab.shipping_address`, write a query returning `line1` and `city` for each row in `types_lab.address_demo`.

### Exercise 7. Designing Constraints for a Composite

Why is `CREATE TYPE shipping_address AS (city text)` not enough to require `city` to always be non-null and non-empty in every table row? Explain how to add the constraint.

### Exercise 8. Enum and Migration

Why does completely removing the `cancelled` label from `types_lab.order_status` usually require a separate migration? List the main steps before dropping the old type.

### Exercise 9. Composite Instead of JSONB?

An event receives metadata from many partners, each with different sets of fields that change constantly. Should you create a single composite with hundreds of optional fields? Explain.

### Exercise 10. Querying Metadata

Write a query listing the labels of enum `types_lab.order_status` in comparison order, using `pg_type` and `pg_enum`.

### Exercise 11. Combined Error Prediction

Suppose table `types_lab.orders` has domain `quantity > 0` and enum `status`. Identify the validation layer that rejects each value:

~~~text
quantity = -1
status = 'unknown'
shipping_address.city = ''
order_code duplicates an existing order
~~~

### Exercise 12. Performance Evaluation

A table uses a composite column `shipping_address` and frequently filters by `(shipping_address).city = 'Da Nang'`. Can an index be created on this expression? Should it be created solely because the syntax allows it?

### Suggested Answers

**Exercise 1:** (1) enum; (2) domain; (3) composite; (4) relational child table because it needs to manage multiple rows with separate constraints and indexes.

**Exercise 2:**

~~~sql
CREATE TYPE types_lab.review_state AS ENUM (
    'new',
    'approved',
    'rejected'
);

SELECT 'approved'::types_lab.review_state;
~~~

**Exercise 3:** No. The enum order is `medium < low < high` because it was defined in that order, not alphabetically.

**Exercise 4:** Null can be accepted because the `CHECK` expression returns unknown. Declare `score types_lab.score NOT NULL` on the column to enforce non-null; consider putting `NOT NULL` in the domain when the shared rule also requires it.

**Exercise 5:** A format domain does not guarantee uniqueness across rows; add `UNIQUE (order_code)` or an appropriate unique index on the table.

**Exercise 6:**

~~~sql
SELECT
    (destination).line1 AS line1,
    (destination).city AS city
FROM types_lab.address_demo;
~~~

**Exercise 7:** A composite only defines fields and types; you need `CHECK`/`NOT NULL` on the table or domains for attributes that have corresponding scalar rules.

**Exercise 8:** There is no standard `ALTER TYPE ... DROP VALUE`; you must migrate data away from the old value, create a new type, handle defaults, cast columns, check dependencies, and drop the old type only when safe.

**Exercise 9:** Usually no if fields change continuously. JSONB or an appropriate event model can be more flexible, paired with targeted validation and indexing.

**Exercise 10:**

~~~sql
SELECT
    e.enumlabel,
    e.enumsortorder
FROM pg_enum AS e
JOIN pg_type AS t
    ON t.oid = e.enumtypid
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE n.nspname = 'types_lab'
  AND t.typname = 'order_status'
ORDER BY e.enumsortorder;
~~~

**Exercise 11:** Negative quantity is rejected by the `positive_quantity` domain; `unknown` is rejected by the enum; empty city is rejected by the table-level `CHECK`; duplicate code is rejected by the unique constraint on `orders.order_code`.

**Exercise 12:** You can create an expression index on `((shipping_address).city)`; you should only do so after measuring workload, selectivity, and index maintenance cost.

## 23. Checklist Before Introducing a Custom Type to Production

| Question | Enum | Domain | Composite |
| --- | --- | --- | --- |
| Is the value set / rule stable long-term? | Very important | Important if reused across many tables | Important if used by many functions/clients |
| Do you need metadata and a lookup table? | If yes, consider a lookup table | Not its primary purpose | Does not replace a relational table |
| Are there reusable scalar constraints? | Label set | `CHECK`, `NOT NULL` | Domains can be used for individual fields |
| Are there multiple child rows needing own keys? | Does not solve | Does not solve | Does not replace a relational table |
| What does altering the type affect? | Labels, comparisons, casts, and app SQL | Columns/functions using the domain | Fields, ROW constructors, mappings, and functions |
| Are indexes needed? | According to enum queries | According to actual columns/expressions | Indexes can target individual fields |
| Can it be migrated and rolled back? | Requires careful planning if removing/renaming labels | Check existing data before validating | Check signature and field compatibility |

## 24. Quick Syntax Reference Table

| Task | Syntax |
| --- | --- |
| Create enum | `CREATE TYPE schema.name AS ENUM ('a', 'b');` |
| Add enum label | `ALTER TYPE schema.name ADD VALUE 'c' AFTER 'b';` |
| Rename enum label | `ALTER TYPE schema.name RENAME VALUE 'a' TO 'x';` |
| Cast value to enum | `'a'::schema.name` |
| Create domain | `CREATE DOMAIN schema.name AS integer CHECK (VALUE > 0);` |
| Non-null domain | `CREATE DOMAIN schema.name AS integer NOT NULL CHECK (...);` |
| Add domain constraint | `ALTER DOMAIN schema.name ADD CONSTRAINT ... CHECK (...);` |
| Validate domain constraint | `ALTER DOMAIN schema.name VALIDATE CONSTRAINT constraint_name;` |
| Create composite | `CREATE TYPE schema.name AS (field1 text, field2 integer);` |
| Construct composite value | `ROW('abc', 123)::schema.name` |
| Read composite field | `(composite_value).field1` |
| Expand all fields | `(composite_value).*` |
| Add composite field | `ALTER TYPE schema.name ADD ATTRIBUTE field3 text;` |
| List enum labels | `pg_enum` + `pg_type` |
| View domain constraints | `pg_constraint` with `contypid` |
| View composite attributes | `pg_attribute` + `pg_type.typrelid` |

## 25. Summary

**Enums** make it clear that a value belongs to a **finite, ordered set of labels**. They fit stable statuses well, though removing labels or changing the data contract later is not as simple as updating a row in a lookup table.

**Domains** wrap a base type together with **validity rules for a single value**. They help reuse scalar checks such as positive quantities, nonnegative monetary amounts, or formatted codes; however, they do not replace foreign keys, cross-row uniqueness, or multi-column constraints.

**Composites** represent **a single value with multiple named fields**, useful in columns and function signatures. However, they do not carry the full constraint system of a relational table, and structural changes can affect `ROW` constructors, functions, mappings, and queries.

When choosing among the three, ask: **is this a set of states, a constrained scalar value, or a multi-attribute structure?** Then consider how fast business rules change, query/indexing needs, missing constraints, dependencies, and migration plans. A clearly named custom data type makes a schema easier to understand, but it is only truly helpful when it **protects the right data without creating hard-to-manage dependencies**.
