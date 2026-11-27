# CREATE TABLE, DEFAULT Values, and Mandatory Columns

In Oracle Database, designing a table does not stop at naming columns and choosing `VARCHAR2`, `NUMBER`, or `DATE`. Right at `CREATE TABLE` time, the designer must answer: **which columns must have a value**, **which columns may be `NULL`**, **what Oracle fills in when the caller omits a column**, and **which boundaries are enforced by the database rather than checked only in the UI**.

This lesson focuses on three closely connected mechanisms:

- `CREATE TABLE` declares the table's structure and data types.
- `DEFAULT` provides a default value in supported insert scenarios.
- `NOT NULL` and constraints such as `PRIMARY KEY` protect mandatory columns, even when an application or SQL tool submits incomplete data.

The most common point of confusion is that **omitting a column from an `INSERT` statement is different from explicitly passing `NULL`**. This lesson uses a small orders table, tests these cases, and connects them to Java/JDBC. Table-creation and data-insertion commands should only be run in a **practice schema** with appropriate privileges, never in a production database.

## 1. Tables, Columns, and Constraints in Oracle

A table stores rows of data sharing a common structure. Each column has a **name**, **type**, **length/precision limit**, and optionally a **default** or **constraints**.

~~~mermaid
flowchart TD
    A["CREATE TABLE LAB_ORDERS"] --> B["Columns and data types"]
    A --> C["DEFAULT: value applied during INSERT"]
    A --> D["NOT NULL: forbids storing NULL"]
    A --> E["PRIMARY KEY: uniquely identifies each row"]
    A --> F["CHECK: minimal business rules"]
    B --> G["Data row stored by Oracle"]
    C --> G
    D --> G
    E --> G
    F --> G
~~~

| Feature | Purpose | Example |
|---|---|---|
| `NUMBER(12,2)` | Numeric type with precision/scale limits | Unit price |
| `VARCHAR2(30 CHAR)` | String, limited by character count subject to Oracle's byte ceiling | Customer code |
| `DATE` | Date and time down to seconds, without timezone | Creation date |
| `DEFAULT 1` | Provides a default when no input value is supplied in supported cases | Default quantity |
| `NOT NULL` | Prevents storing `NULL` in the column | Customer code |
| `PRIMARY KEY` | Uniquely identifies a row and cannot be `NULL` | `ORDER_ID` |
| `CHECK` | Blocks values violating a condition | `QUANTITY > 0` |

**`DEFAULT` does not replace `NOT NULL`.** Conversely, **`NOT NULL` does not generate values on its own**. If a mandatory column has no default and an `INSERT` does not supply a valid value, Oracle cannot insert the row.

## 2. Reading CREATE TABLE Syntax

Basic template:

~~~sql
CREATE TABLE table_name (
    column_1 data_type [DEFAULT expression] [constraint],
    column_2 data_type [DEFAULT expression] [constraint],
    ...
    [CONSTRAINT constraint_name PRIMARY KEY (column_1)]
);
~~~

Items inside square brackets are syntax notation, **not literal SQL to run as-is**. In a real statement, Oracle requires valid data types, commas separating columns, and a `;` terminator in the corresponding SQL tool.

In Oracle, certain constraints can be placed **immediately after the column** (*inline*) or declared at the **table level** (*out-of-line*). For example:

~~~sql
CREATE TABLE lab_customers (
    customer_id   NUMBER(10),
    customer_code VARCHAR2(30 CHAR)
                  CONSTRAINT nn_lab_customers_code NOT NULL,
    display_name  VARCHAR2(100 CHAR) NOT NULL,
    CONSTRAINT pk_lab_customers PRIMARY KEY (customer_id)
);
~~~

Here:

1. `CUSTOMER_ID` has a table-level primary key, so it must be non-`NULL` and unique.
2. `CUSTOMER_CODE` has a `NOT NULL` constraint named `NN_LAB_CUSTOMERS_CODE`.
3. `DISPLAY_NAME` is also mandatory, though Oracle will generate a constraint name if none is specified.
4. No column has a `DEFAULT`; the application must provide valid values to insert a row.

Giving constraints meaningful names makes error messages and metadata easier to read. For example, `PK_LAB_CUSTOMERS` or `NN_LAB_CUSTOMERS_CODE` is much easier to recognize than system-generated names like `SYS_C...`.

### 2.1 In Which Schema and PDB Is the Table Created?

Before running DDL, verify the connection context:

~~~sql
SELECT USER AS session_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV','CON_NAME') AS container_name
FROM dual;
~~~

An unqualified name `LAB_CUSTOMERS` is resolved according to the session context and privileges. In a CDB/PDB architecture, connecting to the right server but the wrong PDB can create the table in the wrong container. For practice exercises, connect directly to the **practice PDB service** using a user permitted to create tables in its own schema.

**Note on DDL:** In Oracle, many DDL statements such as `CREATE TABLE` perform an implicit commit under Oracle semantics. Do not run `ROLLBACK` expecting to delete a newly created table or undo a completed DDL statement. Only create sample tables in an authorized environment.

## 3. End-to-End Example: Creating an Orders Table with DEFAULT and NOT NULL

Create the practice table:

~~~sql
CREATE TABLE lab_orders (
    order_id      NUMBER(10),
    customer_code VARCHAR2(30 CHAR)
                  CONSTRAINT nn_lab_orders_customer NOT NULL,
    status        VARCHAR2(12 CHAR) DEFAULT 'NEW'
                  CONSTRAINT nn_lab_orders_status NOT NULL,
    quantity      NUMBER(6) DEFAULT 1
                  CONSTRAINT nn_lab_orders_quantity NOT NULL,
    unit_price    NUMBER(12,2)
                  CONSTRAINT nn_lab_orders_price NOT NULL,
    created_at    DATE DEFAULT SYSDATE
                  CONSTRAINT nn_lab_orders_created NOT NULL,
    note          VARCHAR2(200 CHAR),

    CONSTRAINT pk_lab_orders PRIMARY KEY (order_id),
    CONSTRAINT ck_lab_orders_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    CONSTRAINT ck_lab_orders_quantity
        CHECK (quantity > 0),
    CONSTRAINT ck_lab_orders_price
        CHECK (unit_price >= 0)
);
~~~

This table illustrates a simplified **order with a single quantity and unit price**, not a full e-commerce model. The goal is to clearly see how the constraints interact.

| Column | Type | Has `DEFAULT`? | Allows `NULL`? | Meaning |
|---|---|---|---|---|
| `ORDER_ID` | `NUMBER(10)` | No | No, because `PRIMARY KEY` | Order identifier; must be unique |
| `CUSTOMER_CODE` | `VARCHAR2(30 CHAR)` | No | No | Customer code is required |
| `STATUS` | `VARCHAR2(12 CHAR)` | `'NEW'` | No | Defaults to `NEW` when omitted on insert |
| `QUANTITY` | `NUMBER(6)` | `1` | No | Defaults to one unit when omitted |
| `UNIT_PRICE` | `NUMBER(12,2)` | No | No | Unit price is required, non-negative |
| `CREATED_AT` | `DATE` | `SYSDATE` | No | Creation time per the database server clock |
| `NOTE` | `VARCHAR2(200 CHAR)` | No | **Yes** | Optional note |

`DEFAULT SYSDATE` is evaluated for supported insert operations, not stored as the literal text `'SYSDATE'`. A `DATE` column stores both date and hours/minutes/seconds, even though a client tool may display only the date portion due to `NLS_DATE_FORMAT`.

The `CHECK` constraints are simple data rules:

- `STATUS` must belong to `NEW`, `PAID`, `CANCELLED`.
- `QUANTITY` must be greater than 0.
- `UNIT_PRICE` must be non-negative.

Because `NOT NULL` is already declared on the corresponding columns, we do not rely on `CHECK` to forbid `NULL`. In Oracle's three-valued SQL logic, a `CHECK` condition evaluating to *UNKNOWN* (for example, due to `NULL`) is not treated the same as `FALSE`; when a column must always have a value, declare `NOT NULL` explicitly.

## 4. How Does DEFAULT Work During INSERT?

### 4.1 Omitting Columns with Defaults from the INSERT List

~~~sql
INSERT INTO lab_orders (
    order_id,
    customer_code,
    unit_price
)
VALUES (
    101,
    'CUS-001',
    120000
);

COMMIT;
~~~

In the statement above, four columns—`STATUS`, `QUANTITY`, `CREATED_AT`, and `NOTE`—are not passed:

- `STATUS` receives `'NEW'` from `DEFAULT`.
- `QUANTITY` receives `1` from `DEFAULT`.
- `CREATED_AT` receives the result of `SYSDATE` at insert time.
- `NOTE` has no default and no `NOT NULL`, so it receives `NULL`.

Query it back:

~~~sql
SELECT order_id,
       customer_code,
       status,
       quantity,
       unit_price,
       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_text,
       note
FROM lab_orders
WHERE order_id = 101;
~~~

Example output:

~~~text
ORDER_ID  CUSTOMER_CODE  STATUS  QUANTITY  UNIT_PRICE  CREATED_TEXT         NOTE
--------  -------------  ------  --------  ----------  -------------------  ----
101       CUS-001        NEW     1         120000      <insert-timestamp>   NULL
~~~

The actual `CREATED_TEXT` is the date and time provided by the server; do not copy a fixed timestamp from an example. `TO_CHAR` with an explicit format makes the time component readable regardless of each session's date display settings.

### 4.2 Explicitly Passing a Non-Default Value

~~~sql
INSERT INTO lab_orders (
    order_id, customer_code, status, quantity, unit_price, note
)
VALUES (
    102, 'CUS-002', 'PAID', 3, 89000, 'Paid'
);

COMMIT;
~~~

`STATUS` receives `PAID` and `QUANTITY` receives `3`; the default value **does not override a valid supplied value**. `CREATED_AT` still receives `SYSDATE` because it is omitted from the column list.

### 4.3 Using the DEFAULT Keyword in the VALUES List

Oracle supports the `DEFAULT` keyword in the appropriate value position:

~~~sql
INSERT INTO lab_orders (
    order_id, customer_code, status, quantity, unit_price
)
VALUES (
    103, 'CUS-003', DEFAULT, DEFAULT, 150000
);

COMMIT;
~~~

`DEFAULT` in the `STATUS` and `QUANTITY` positions instructs Oracle to use the declared default expression for each column, similar to omitting those columns from the `INSERT` list. This is a SQL keyword, **not the string `'DEFAULT'`**.

If a column has no `DEFAULT`, specifying `DEFAULT` typically evaluates to `NULL`; if that column has `NOT NULL`, the insert is rejected. Never assume every column produces a valid value when typing `DEFAULT`.

### 4.4 Does DEFAULT Apply When Explicitly Passing NULL?

With standard `DEFAULT` syntax, **no**. For example:

~~~sql
-- Illustrative statement that will fail; do not run with a batch of valid INSERTs:
INSERT INTO lab_orders (
    order_id, customer_code, status, unit_price
)
VALUES (
    104, 'CUS-004', NULL, 70000
);
~~~

In our table, `STATUS` has `DEFAULT 'NEW'` **and** `NOT NULL`. Because the `INSERT` **explicitly passed `NULL`**, Oracle does not substitute `NEW` under standard `DEFAULT` rules; `NOT NULL` is violated and the typical error is:

~~~text
ORA-01400: cannot insert NULL into ...
~~~

This is the essential difference between **"not sending a value"** and **"sending a null value"**. Standard `DEFAULT` alone does not cover both cases.

### 4.5 DEFAULT Does Not Re-Run Automatically on UPDATE

Suppose `ORDER_ID = 101` has `STATUS = NEW`; then:

~~~sql
UPDATE lab_orders
SET status = 'PAID'
WHERE order_id = 101;
~~~

Oracle does not automatically "re-apply `DEFAULT 'NEW'`" when another column is updated or after every `UPDATE`. A `DEFAULT` definition primarily governs default values during inserts and contexts where `DEFAULT` is explicitly specified. Where supported, you can write:

~~~sql
UPDATE lab_orders
SET status = DEFAULT
WHERE order_id = 101;

COMMIT;
~~~

In that case, `STATUS` is reset to its declared default. These two `UPDATE` statements are shown to explain behavior: run them on the practice table if you want to observe it, not on real order data.

## 5. NOT NULL: A Mandatory Column Does Not Auto-Generate Values

`NOT NULL` ensures a column **cannot accept null** when Oracle writes or updates a row. In `LAB_ORDERS`:

~~~sql
-- Fails because CUSTOMER_CODE is mandatory and has no DEFAULT.
INSERT INTO lab_orders (order_id, unit_price)
VALUES (105, 100000);
~~~

Explanation:

- `ORDER_ID` is provided.
- `UNIT_PRICE` is provided.
- `STATUS`, `QUANTITY`, and `CREATED_AT` have defaults, so they can receive valid values.
- `CUSTOMER_CODE` is omitted and has no default, so its implicit value is `NULL`; because of `NOT NULL`, the `INSERT` fails.

Declaring `NOT NULL` does not fabricate a dummy customer code; the database requires the application to supply a valid value.

### 5.1 DEFAULT and NOT NULL Are Two Independent Dimensions

| Column Declaration | When Column Is Omitted in INSERT | When `NULL` Is Passed Explicitly | Conclusion |
|---|---|---|---|
| `note VARCHAR2(100)` | Receives `NULL` | Receives `NULL` | Optional column |
| `note VARCHAR2(100) DEFAULT 'N/A'` | Receives `N/A` | **Receives `NULL`** | Has a default, yet still nullable |
| `note VARCHAR2(100) NOT NULL` | Fails (no value) | Fails | Application must supply value |
| `note VARCHAR2(100) DEFAULT 'N/A' NOT NULL` | Receives `N/A` | Fails | Omitting works; passing null fails |
| `note VARCHAR2(100) DEFAULT ON NULL 'N/A'` | Receives `N/A` | Receives `N/A` on INSERT | Special case, requires supporting version |

The distinctions across these rows govern how an application designs requests, validation, and parameter binding.

### 5.2 NULL Is Neither an Empty String Nor Zero

`NULL` means no value is recorded, not the number 0 or the text `"NULL"`.

~~~sql
-- The string 'NULL' is four characters, not SQL NULL:
SELECT 'NULL' AS literal_text
FROM dual;

-- Correct way to check for NULL:
SELECT order_id
FROM lab_orders
WHERE note IS NULL;
~~~

In Oracle, a **zero-length character string** in standard character types such as `VARCHAR2` is currently treated as `NULL`. Consequently, an application sending an empty string `''` to `CUSTOMER_CODE NOT NULL` can trigger a `NOT NULL` violation. However, a whitespace string such as `' '` **is not `NULL`**; if the business rejects whitespace-only codes, additional validation is needed in the data or application layer.

Do not use:

~~~sql
WHERE note = NULL
~~~

to find rows without a note. In SQL, comparing with `NULL` yields unknown (*UNKNOWN*); to check for missing values, you must use `IS NULL` or `IS NOT NULL`.

## 6. DEFAULT ON NULL: Handling Applications That Send NULL

In Oracle versions supporting `DEFAULT ON NULL` (introduced in the Oracle Database 12c family), a column can be declared so Oracle applies the default **both when the column is omitted and when an `INSERT` passes `NULL`**.

In the practice schema:

~~~sql
CREATE TABLE lab_default_compare (
    id                   NUMBER PRIMARY KEY,
    standard_default     VARCHAR2(12 CHAR) DEFAULT 'NEW',
    default_when_null    VARCHAR2(12 CHAR) DEFAULT ON NULL 'NEW'
);
~~~

Test three insert patterns:

~~~sql
-- 1) Omit both columns: both use the default
INSERT INTO lab_default_compare (id)
VALUES (1);

-- 2) Pass NULL into both columns
INSERT INTO lab_default_compare (
    id, standard_default, default_when_null
)
VALUES (
    2, NULL, NULL
);

-- 3) Pass explicit valid values
INSERT INTO lab_default_compare (
    id, standard_default, default_when_null
)
VALUES (
    3, 'PAID', 'PAID'
);

COMMIT;

SELECT id, standard_default, default_when_null
FROM lab_default_compare
ORDER BY id;
~~~

Expected result:

| ID | `STANDARD_DEFAULT` | `DEFAULT_WHEN_NULL` |
|---:|---|---|
| 1 | `NEW` | `NEW` |
| 2 | `NULL` | `NEW` |
| 3 | `PAID` | `PAID` |

`DEFAULT ON NULL` interacts with the column's **non-nullable** constraint semantics in Oracle; it is not just a display substitution. For instance, attempting to update a column of this kind to `NULL` in the standard way is not treated as a valid null assignment. To check version-specific behavior for update variants, consult the documentation for your exact release; the example here focuses on **INSERT**.

### 6.1 When Should You Use DEFAULT ON NULL?

It is a good fit when **every row creation needs a default status**, even if a legacy client sends `NULL`. However, there are also cases where sending `NULL` is **a business error that must be caught**, such as a required customer code, a mandatory email, or a user-selected deadline.

If sending `NULL` is invalid, let `NOT NULL` raise an error rather than silently replacing it with a fake value. Do not slap `DEFAULT ON NULL 'UNKNOWN'` onto every column just to hide data errors.

### 6.2 Difference Between DEFAULT ON NULL and NVL

`NVL` is a SQL function commonly used when **reading or evaluating expressions**:

~~~sql
SELECT id, NVL(standard_default, 'NOT_SET') AS displayed_status
FROM lab_default_compare;
~~~

It returns a substitute expression when the stored value is `NULL`, but **does not modify the stored value** in the table. By contrast, `DEFAULT ON NULL` affects the value placed into the column under `INSERT` rules. Do not confuse display logic at `SELECT` time with storage policy.

## 7. PRIMARY KEY, CHECK, and Related Constraints

Understanding "mandatory columns" requires distinguishing `NOT NULL` from complementary rules:

### 7.1 PRIMARY KEY Is More Than NOT NULL

~~~sql
CONSTRAINT pk_lab_orders PRIMARY KEY (order_id)
~~~

A primary key requires **every key value to be present and unique**. Primary key columns cannot be `NULL`. If you try to insert two rows with the same `ORDER_ID`, Oracle raises a uniqueness error, typically `ORA-00001`. Putting only `ORDER_ID NOT NULL` without `PRIMARY KEY` or `UNIQUE` still allows multiple rows with the same ID; thus the two constraints are not equivalent.

For a composite primary key, all participating key columns must be non-`NULL`. In typical designs, prefer a clear, stable identifying key for the table.

### 7.2 CHECK Protects a Value Set or Range

~~~sql
CONSTRAINT ck_lab_orders_status
CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
~~~

`CHECK` only allows data matching the allowed status set. If you send `'REFUNDED'` without adding it to the rule, Oracle raises `ORA-02290: check constraint violated`. Yet a `CHECK` does not generate status values by itself, nor does it replace a `NULL` policy unless non-nullability is explicitly declared.

A complete design combines:

- The right data types.
- Reasonable `DEFAULT` values for creation-time state.
- `NOT NULL` for columns that must hold a value.
- `CHECK` for value domains; `PRIMARY KEY` / `FOREIGN KEY` / `UNIQUE` for relationships and uniqueness that must be protected.

### 7.3 FOREIGN KEY Does Not Auto-Generate Parent Keys

Suppose a system has `CUSTOMERS(CUSTOMER_ID)` and wants `LAB_ORDERS.CUSTOMER_ID` to reference it:

~~~sql
-- Standalone syntax example, not added directly to the sample table above:
CREATE TABLE lab_order_refs (
    order_id    NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    CONSTRAINT fk_lab_order_refs_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_customers (customer_id)
);
~~~

The foreign key constraint ensures `CUSTOMER_ID` references a valid parent key in Oracle. `NOT NULL` ensures the customer ID cannot be omitted. These two roles are distinct: a foreign key allows `NULL` if the column lacks `NOT NULL`, whereas `NOT NULL` does not prove that the customer ID exists in the parent table.

## 8. Defaults for DATE, TIMESTAMP, and NUMBER

### 8.1 DEFAULT Is an Expression Evaluated When Appropriate

~~~sql
CREATE TABLE lab_event_log (
    event_id    NUMBER PRIMARY KEY,
    event_code  VARCHAR2(30 CHAR) NOT NULL,
    event_time  TIMESTAMP DEFAULT LOCALTIMESTAMP NOT NULL,
    retry_count NUMBER(4) DEFAULT 0 NOT NULL
);
~~~

`LOCALTIMESTAMP` produces the current timestamp in the session timezone context, returning a `TIMESTAMP` without timezone. `SYSDATE` returns the database server system time as a `DATE`. If a system must record an **exact instant with timezone semantics**, choose the appropriate column type and time API; do not rely on `DATE DEFAULT SYSDATE` as a guarantee that timezone information is stored.

For numbers:

~~~sql
retry_count NUMBER(4) DEFAULT 0 NOT NULL
~~~

the default `0` is a **NUMBER value**, not the string `'0'`. Applications should bind numeric values with matching numeric types. If the business needs to distinguish "retry count not recorded yet" from "recorded as 0 retries", adding `DEFAULT 0` erases that distinction; design must follow the data contract.

### 8.2 A Default Is Not an "Always-Updated Value"

Suppose you add:

~~~sql
created_at DATE DEFAULT SYSDATE NOT NULL
~~~

This is useful for knowing when the row was created, but **it does not automatically update whenever the row changes**. For `updated_at`, you need separate update logic—for instance, setting the timestamp in the application's `UPDATE` or using a trigger according to system policy. Never assume column names like `CREATED_AT` and `UPDATED_AT` carry special behavior merely from their names.

### 8.3 Avoiding NLS-Dependent Defaults

Do not treat an arbitrary string as a date default:

~~~sql
-- Avoid depending on session/database NLS format settings:
-- some_date DATE DEFAULT '14/11/2026'
~~~

When a fixed date is needed, prefer a date literal:

~~~sql
CREATE TABLE lab_campaigns (
    campaign_id NUMBER PRIMARY KEY,
    start_date  DATE DEFAULT DATE '2026-11-14' NOT NULL
);
~~~

`DATE 'YYYY-MM-DD'` has fixed syntax and does not depend on `NLS_DATE_FORMAT`. For user-supplied dates from Java, bind date/time types rather than concatenating strings into SQL. Locale and timezone formatting during string conversion is a separate concern from column mandatory constraints.

## 9. DEFAULT, IDENTITY, and Generating Primary Keys

Putting `DEFAULT` on an ID column does not mean Oracle will auto-increment the ID per row. If you write:

~~~sql
order_id NUMBER DEFAULT 1 PRIMARY KEY
~~~

multiple rows omitting `ORDER_ID` will all try to receive `1`, causing primary key violations. When Oracle needs to generate key values, use an **identity column** or a sequence appropriate for your version.

Starting from the Oracle Database 12c family, you can use:

~~~sql
CREATE TABLE lab_identity_orders (
    order_id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY,
    note     VARCHAR2(100 CHAR),
    CONSTRAINT pk_lab_identity_orders PRIMARY KEY (order_id)
);
~~~

In this example, `ORDER_ID` uses an identity mechanism, **which is different from `DEFAULT ON NULL 'NEW'` on a text column**. Oracle generates the key value when `INSERT` omits the ID or passes `NULL` under the `BY DEFAULT ON NULL` option. Identity options also include `GENERATED ALWAYS` and `GENERATED BY DEFAULT`, each with different rules for whether clients may supply values directly.

Example:

~~~sql
INSERT INTO lab_identity_orders (note)
VALUES ('Auto-generated ID order');

COMMIT;

SELECT order_id, note
FROM lab_identity_orders;
~~~

Auto-generated IDs **are not guaranteed to be strictly gap-free**: sequences/identities can have gaps due to rollbacks, caching, concurrency, or other operations. Therefore, do not use sequential identity values for business document numbers requiring gapless numbering without a dedicated business mechanism.

On older Oracle versions without identity support, use a sequence with appropriate DML or triggers; **do not copy 12c+ identity syntax verbatim to Oracle 11g**. Most importantly, keep the distinction clear: the primary key enforces uniqueness, while the key-generation mechanism handles producing values.

## 10. Inspecting Structure, DEFAULT, and NOT NULL in the Data Dictionary

After creating tables, do not trust old DDL files alone. Query the metadata of the **existing table** to verify its actual state.

### 10.1 Columns, Nullability, and Default Values

For tables owned by the current user:

~~~sql
SELECT column_id,
       column_name,
       data_type,
       data_length,
       nullable,
       data_default
FROM user_tab_columns
WHERE table_name = 'LAB_ORDERS'
ORDER BY column_id;
~~~

In `USER_TAB_COLUMNS`:

- `COLUMN_NAME`: column name.
- `DATA_TYPE`, `DATA_LENGTH`: data type and byte length in type metadata.
- `NULLABLE = 'N'`: metadata records that the column cannot be `NULL`; `Y` means `NULL` is allowed per the active constraint state.
- `DATA_DEFAULT`: the stored default expression, if any.

`DATA_DEFAULT` is a `LONG` metadata column in many Oracle versions; some tools may truncate its output if display length is small. In SQL*Plus, you can run:

~~~sql
SET LONG 10000
~~~

before selecting `DATA_DEFAULT`. To inspect another schema you have permission to view, use `ALL_TAB_COLUMNS` and filter by `OWNER`:

~~~sql
SELECT owner, table_name, column_name, nullable, data_default
FROM all_tab_columns
WHERE owner = 'APP_OWNER'
  AND table_name = 'LAB_ORDERS';
~~~

Replace `APP_OWNER` with the actual schema name; `ALL_TAB_COLUMNS` does not mean a regular user can see every table in the database.

### 10.2 Viewing DEFAULT ON NULL on Supported Versions

On releases that include the metadata column, you can inspect:

~~~sql
SELECT column_name,
       nullable,
       default_on_null
FROM user_tab_columns
WHERE table_name = 'LAB_DEFAULT_COMPARE'
ORDER BY column_id;
~~~

`DEFAULT_ON_NULL` helps identify special default declarations. If your database/version lacks this column, the query will raise `ORA-00904`; check the data dictionary definition for your release instead of assuming the table has no `DEFAULT`. Combine it with `DATA_DEFAULT` to see the applied **expression**.

### 10.3 Viewing Constraints and Associated Columns

~~~sql
SELECT c.constraint_name,
       c.constraint_type,
       c.status,
       c.validated,
       cc.column_name,
       cc.position
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.table_name = 'LAB_ORDERS'
ORDER BY c.constraint_name, cc.position;
~~~

| `CONSTRAINT_TYPE` | Common Type |
|---|---|
| `P` | Primary key |
| `U` | Unique |
| `R` | Referential integrity / foreign key |
| `C` | Check constraint; `NOT NULL` constraints are also typically reflected in this group |

`STATUS` and `VALIDATED` show whether the constraint is enabled and validated. A constraint present in metadata yet disabled or unvalidated does not provide the same guarantee as one actively protecting every row in normal mode. In a learning environment, create constraints enabled and let Oracle validate data from the start.

To inspect `CHECK` conditions, supported Oracle versions provide `SEARCH_CONDITION_VC` in `USER_CONSTRAINTS`; some versions also expose `SEARCH_CONDITION` as `LONG`. For broad compatibility, you can inspect DDL via your client tool or `DBMS_METADATA.GET_DDL` (with appropriate privileges) to verify the exact definition.

## 11. Changing DEFAULT or NOT NULL on an Existing Table

Designs evolve, but you must evaluate existing data before applying new constraints.

### 11.1 Changing DEFAULT for Future INSERTs

On the practice table:

~~~sql
ALTER TABLE lab_orders
MODIFY (quantity DEFAULT 2);
~~~

After this statement, subsequent `INSERT`s that omit `QUANTITY` will use the new default `2`. Modifying a default expression **does not automatically update existing rows** from `1` to `2`. If historical rows must change, plan a separate `UPDATE` while controlling business impact and transactions.

### 11.2 Check Existing NULLs Before Adding NOT NULL

Suppose the `NOTE` column is currently optional:

~~~sql
SELECT COUNT(*) AS null_note_rows
FROM lab_orders
WHERE note IS NULL;
~~~

If any rows have `NOTE IS NULL`, trying to enforce a mandatory constraint with:

~~~sql
-- Run only after handling null data and confirming with the business:
ALTER TABLE lab_orders
MODIFY (note NOT NULL);
~~~

will fail because existing rows violate the new constraint. Oracle raises an error such as `ORA-02296: cannot enable ... null values found`. **Do not** blindly replace all `NULL`s with `'N/A'` if "no note recorded" means something different from "note is N/A".

A safe change workflow includes: inspecting actual data, determining the business meaning of `NULL`, normalizing data once approved by the business, applying the constraint at an appropriate time, and testing application impact.

### 11.3 Adding a Mandatory Column to a Table That Already Has Data

If a table already contains rows, adding a `NOT NULL` column without a default fails because existing rows have no value for the new column:

~~~sql
-- Risky change example; do not run on production tables:
ALTER TABLE lab_orders
ADD (source_system VARCHAR2(20 CHAR) NOT NULL);
~~~

When business policy allows a sensible default, consider:

~~~sql
ALTER TABLE lab_orders
ADD (source_system VARCHAR2(20 CHAR)
     DEFAULT 'MANUAL' NOT NULL);
~~~

Depending on column type, Oracle version, and table conditions, Oracle applies different optimizations when adding a column with a default. Do not assume every case is metadata-only or generates zero I/O. On large tables, assess locking, migration strategy, backfilling, and maintenance windows.

## 12. INSERT from Java Applications and Missing Values

With JDBC, the distinction between **omitting a column from SQL** and **binding `NULL` to a parameter** is especially important.

### 12.1 Omitting Columns So Oracle Applies DEFAULT

Assuming the application has a `Connection connection`, you do not need to supply `STATUS`, `QUANTITY`, or `CREATED_AT` if you want their defaults:

~~~java
String sql = """
    INSERT INTO lab_orders (order_id, customer_code, unit_price)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 201L);
    ps.setString(2, "CUS-JAVA");
    ps.setBigDecimal(3, new java.math.BigDecimal("250000.00"));
    ps.executeUpdate();
}
~~~

In this SQL, **the three defaulted columns are absent from the column list**, so Oracle fills in their defaults. This snippet assumes `java.sql.*` imports and application-controlled transactions/`COMMIT`; `executeUpdate` does not mean the transaction is committed if autocommit is disabled.

### 12.2 Binding NULL Does Not Mean "Leave Blank for DEFAULT"

Another example:

~~~java
String sql = """
    INSERT INTO lab_orders (order_id, customer_code, status, unit_price)
    VALUES (?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 202L);
    ps.setString(2, "CUS-JAVA");
    ps.setNull(3, java.sql.Types.VARCHAR);
    ps.setBigDecimal(4, new java.math.BigDecimal("250000.00"));
    ps.executeUpdate();
}
~~~

This example **will fail** on the original `LAB_ORDERS` table: `STATUS` is `DEFAULT 'NEW' NOT NULL`, while JDBC explicitly passed `NULL`. Oracle must enforce `NOT NULL` rather than replacing it with a standard default. If the business wants `NULL` to also become `NEW`, consider `DEFAULT ON NULL` where appropriate rather than changing how `setNull` is interpreted.

### 12.3 JSON, ORMs, and PATCH Need Deliberate Design

In an API, three input states for a field usually need to be distinguished:

| Client Input | Possible Business Meaning | How SQL Can Handle It |
|---|---|---|
| Key `status` omitted | Use the default status | Omit `STATUS` from `INSERT` or use the `DEFAULT` keyword |
| Key `status` is `null` | Client supplied no valid value or requested clearing the value | Reject in validation, or bind `NULL` if nullable; `DEFAULT ON NULL` only if design allows it |
| Key `status` is `"PAID"` | Set a specific status | Bind `'PAID'`, validated by `CHECK` |

An ORM may generate an `INSERT` containing every column and bind `NULL` for unset fields. In that case, a default only applies to columns **omitted from the SQL** or configured with `DEFAULT ON NULL`. Never assume a Java annotation or field initializer always stays in sync with the database `DEFAULT`.

For update endpoints (`PATCH`), an "omitted field" usually means **keep the existing value**, unlike inserting a new row. Do not let `INSERT` `DEFAULT` semantics accidentally overwrite data during an `UPDATE`.

## 13. Common Errors and Troubleshooting Guide

| Message / Symptom | Likely Cause | How to Check |
|---|---|---|
| `ORA-01400: cannot insert NULL into ...` | Omitted a `NOT NULL` column with no default, or explicitly sent `NULL` to a mandatory column | Check `INSERT` column list, bound values, `NULLABLE`, and `DATA_DEFAULT` |
| `ORA-00001: unique constraint violated` | Duplicate primary or unique key | Inspect constraint name and key value; review ID generation |
| `ORA-02290: check constraint violated` | Value outside `CHECK` domain | Query `USER_CONSTRAINTS` and inspect actual value |
| `ORA-12899: value too large for column` | String exceeds column byte/character limit | Check DDL, `DATA_LENGTH`, `CHAR_USED`, measure `LENGTHB` |
| `ORA-01438` | Number exceeds `NUMBER(p,s)` precision | Verify precision/scale and input number |
| `ORA-00947: not enough values` | `VALUES` list does not match target column count | Use explicit `INSERT INTO t (col1, col2) VALUES (...)` |
| `ORA-02296` when adding `NOT NULL` | Table already contains `NULL` rows in that column | Count violating rows; plan backfill |
| `ORA-00904` when querying metadata | Metadata column/view absent in your version or misspelled | Check data dictionary for your release instead of assuming the table is corrupt |
| `DEFAULT 'NEW'` exists yet insert still fails `NOT NULL` | Client explicitly passed `NULL` | Distinguish omitting a column, `DEFAULT`, and `NULL`; consider `DEFAULT ON NULL` |
| Creation date shows only the date | `NLS_DATE_FORMAT` hides time component | `TO_CHAR(created_at,'YYYY-MM-DD HH24:MI:SS')` |
| Old rows unchanged after `ALTER TABLE MODIFY DEFAULT` | New default applies to future operations, not retroactively to old data | Distinguish DDL default from an `UPDATE` plan |
| Inserting empty string into mandatory column fails | Oracle treats empty string as `NULL` in standard character types | Validate input strings; distinguish from whitespace-only strings |

Each error code narrows down the cause, but does not replace inspecting the **actual SQL**, **bound values**, **metadata**, and **container/schema**. For instance, `ORA-01400` may be triggered by a completely different column than the one the developer is currently looking at.

### Troubleshooting Flowchart for Failed INSERTs

~~~mermaid
flowchart TD
    A["INSERT into table fails"] --> B["Verify correct PDB and schema"]
    B --> C["Query USER_TAB_COLUMNS / ALL_TAB_COLUMNS"]
    C --> D{"Does failing column have NOT NULL?"}
    D -->|Yes| E{"Did client omit column or pass NULL?"}
    E -->|Omitted column| F["Check DATA_DEFAULT; if none, a value must be supplied"]
    E -->|Passed NULL| G["Standard DEFAULT does not replace NULL; consider validation / ON NULL"]
    D -->|No| H["Check CHECK, PK/UNIQUE, length, precision"]
    F --> I["Fix SQL/DDL per data contract"]
    G --> I
    H --> I
~~~

## 14. Self-Check Practice Lab

**Step 1 — Create the table.** In a practice PDB/schema, run `CREATE TABLE LAB_ORDERS` from Section 3. Note all column names and identify which ones are mandatory due to `NOT NULL` or `PRIMARY KEY`.

**Step 2 — Omit defaulted columns.** Insert `ORDER_ID = 301`, `CUSTOMER_CODE = 'CUS-301'`, `UNIT_PRICE = 100000` without passing `STATUS`, `QUANTITY`, `CREATED_AT`, or `NOTE`. Predict and then query the resulting values; why is `NOTE` `NULL` while `STATUS` is `NEW`?

**Step 3 — Pass NULL.** In a new insert with `ORDER_ID = 302`, pass `STATUS = NULL`. Write down why the statement will fail on `LAB_ORDERS` even though the column has a default. There is no need to include intentionally failing statements in deployment scripts.

**Step 4 — Compare the two DEFAULT styles.** Create `LAB_DEFAULT_COMPARE`, insert IDs 1, 2, and 3, and compare `STANDARD_DEFAULT` with `DEFAULT_WHEN_NULL`. Explain why `DEFAULT ON NULL` should only be used when the business accepts substituting null with a default.

**Step 5 — Read metadata.** Query `USER_TAB_COLUMNS` and `USER_CONSTRAINTS`. Identify default expressions, nullable columns, the primary key, and `CHECK` constraints. Cross-check with the DDL you ran and note that constraint names can be auto-generated by Oracle.

**Step 6 — Protect data with CHECK.** Predict the outcome of inserting `QUANTITY = 0` or `STATUS = 'DONE'`. Why doesn't `DEFAULT` fix explicit values that violate `CHECK`?

**Step 7 — Change DEFAULT.** On the test table, change `QUANTITY DEFAULT 2`. Before inserting a new row, predict whether `ORDER_ID = 301` will automatically change `QUANTITY` to 2. Insert a new row omitting quantity and compare.

**Step 8 — Java/JDBC.** Compare two `INSERT` statements: one sending only `ORDER_ID`, `CUSTOMER_CODE`, `UNIT_PRICE`; the other including `STATUS` with `setNull`. Predict which succeeds and explain using database constraints.

**Step 9 — New design.** An account registration table has a mandatory `EMAIL`, `STATUS` defaulting to `PENDING`, and `CREATED_AT` defaulting to the current timestamp. Write the DDL and answer: should `EMAIL` have `DEFAULT 'UNKNOWN'` just so every insert succeeds? Should `STATUS` use `DEFAULT` or `DEFAULT ON NULL` in an API where clients might send `null`? Base your choice on the business contract.

## 15. Takeaways for Oracle Table Design

| Goal | Appropriate Mechanism | Do Not Confuse With |
|---|---|---|
| Declare columns and data types | `CREATE TABLE` | Automatically enforcing all business rules |
| Supply a value when column is omitted | `DEFAULT` | Replacing every explicit `NULL` |
| Supply a value even when INSERT passes `NULL` | `DEFAULT ON NULL` on supported versions | Display function `NVL` |
| Require a column to have a value | `NOT NULL` | Generating values on the client's behalf |
| Uniquely identify each row | `PRIMARY KEY` | Automatic key generation |
| Auto-generate numeric keys | Appropriate `IDENTITY` / sequence | `DEFAULT 1` |
| Restrict value domain | `CHECK` | Auto-generating values within the domain |
| Verify active design | `USER_TAB_COLUMNS`, `USER_CONSTRAINTS` | Relying solely on DDL stored in docs |
| Insert data from Java | `PreparedStatement` with proper types | Assuming binding `NULL` triggers `DEFAULT` |

A solid design cleanly separates **values the application must supply**, **values Oracle may default**, and **values the database must never permit**. Good practice is to write clear DDL, test both column-omission and explicit-`NULL` cases, verify metadata, and keep API/JDBC behavior aligned with database constraints. That way, data remains protected even when multiple tools, services, or programs write to Oracle concurrently.
