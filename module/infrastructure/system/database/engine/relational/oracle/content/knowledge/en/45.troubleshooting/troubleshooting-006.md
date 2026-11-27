# ORA-01400, ORA-01438, ORA-12899, and Out-of-Domain Data Errors

When inserting or updating data in Oracle Database, input values must satisfy the column's data type, length, precision/scale, nullability, and business constraints. If data does not conform, Oracle rejects the operation and returns an error. Three common errors are:

- **ORA-01400: cannot insert NULL into (...)** — the operation attempts to put a NULL value into a column that disallows NULL.
- **ORA-01438: value larger than specified precision allowed for this column** — a numeric value exceeds the precision permitted by the `NUMBER` column.
- **ORA-12899: value too large for column (...)** — a character value exceeds the column length, evaluated under `BYTE` or `CHAR` semantics.

Beyond these three, data can violate a `CHECK` constraint (ORA-02290), foreign key (ORA-02291/ORA-02292), unique constraint (ORA-00001), or hit conversion errors such as ORA-01722 and ORA-01861. These errors have different root causes and therefore require different fixes.

The core principle is to identify the exact column and offending value, inspect the actual schema definition, examine source data and business boundaries, and then decide whether to fix the data or change the schema. Never blindly replace `NULL` with `0`, truncate strings, or round numbers just to make a statement succeed; those actions can silently alter data meaning.

## 1. The Value Domain of an Oracle Column

A column can restrict data across multiple layers:

| Layer | Example | Common Error |
|---|---|---|
| Nullability | `CUSTOMER_ID NOT NULL` | ORA-01400 |
| Data type | `NUMBER`, `DATE`, `VARCHAR2` | ORA-01722, ORA-01861, conversion errors |
| Precision/scale | `NUMBER(7,2)` | ORA-01438 |
| String length | `VARCHAR2(30 BYTE)` | ORA-12899 |
| Business domain | `CHECK (amount >= 0)` | ORA-02290 |
| Referential integrity | `FOREIGN KEY` to `CUSTOMER` | ORA-02291, ORA-02292 |
| Uniqueness | `UNIQUE (email)` | ORA-00001 |

A column's domain is more than just its data type. A `NUMBER` column accepts a vast range of numbers, but `NUMBER(7,2)` limits precision and decimal places. A `VARCHAR2` column stores strings, but only up to its declared length. A `CHECK` constraint can narrow the domain further, such as allowing status values only from `OPEN`, `PAID`, or `CANCELLED`.

Design example:

~~~sql
CREATE TABLE order_lines (
    order_line_id NUMBER(19) NOT NULL,
    order_id      NUMBER(19) NOT NULL,
    quantity      NUMBER(8, 3) NOT NULL,
    unit_price    NUMBER(12, 2) NOT NULL,
    status        VARCHAR2(20 CHAR) NOT NULL,
    note          VARCHAR2(500 CHAR),
    CONSTRAINT pk_order_lines
        PRIMARY KEY (order_line_id),
    CONSTRAINT ck_order_lines_quantity
        CHECK (quantity > 0),
    CONSTRAINT ck_order_lines_price
        CHECK (unit_price >= 0),
    CONSTRAINT ck_order_lines_status
        CHECK (status IN ('OPEN', 'FULFILLED', 'CANCELLED'))
);
~~~

In this example, `quantity` must be non-null and greater than 0; `unit_price` must be non-negative; `status` is mandatory and restricted to the listed values; `note` is nullable. Each rule guards against a distinct class of invalid data.

## 2. ORA-01400: Cannot Insert NULL into a NOT NULL Column

ORA-01400 occurs when an `INSERT` produces a `NULL` value for a column with a `NOT NULL` constraint. The error message typically identifies the violated schema, table, and column, helping isolate where to check.

Example:

~~~sql
CREATE TABLE customers (
    customer_id   NUMBER(19) NOT NULL,
    customer_name VARCHAR2(100 CHAR) NOT NULL,
    email         VARCHAR2(200 CHAR)
);
~~~

The following statement omits `customer_name`:

~~~sql
INSERT INTO customers (customer_id, email)
VALUES (1001, 'customer@example.com');
~~~

Because `customer_name` is omitted and has no default, Oracle supplies `NULL` for that column and rejects the `INSERT`.

Another example explicitly passes `NULL`:

~~~sql
INSERT INTO customers (
    customer_id,
    customer_name,
    email
)
VALUES (
    1002,
    NULL,
    'another@example.com'
);
~~~

The `customer_name` column receives `NULL`, so the operation fails as well.

### 2.1. Omitting a Column vs. Passing NULL Explicitly

This distinction matters when using `DEFAULT`:

~~~sql
CREATE TABLE payment_methods (
    method_id   NUMBER(19) NOT NULL,
    method_name VARCHAR2(50 CHAR)
        DEFAULT 'UNSPECIFIED' NOT NULL
);
~~~

If `method_name` is omitted:

~~~sql
INSERT INTO payment_methods (method_id)
VALUES (1);
~~~

Oracle applies the default `'UNSPECIFIED'`.

If `NULL` is passed explicitly:

~~~sql
INSERT INTO payment_methods (method_id, method_name)
VALUES (2, NULL);
~~~

With a standard `DEFAULT`, an explicit `NULL` remains `NULL` and violates `NOT NULL`. On Oracle versions supporting it, `DEFAULT ON NULL` applies the default even when `INSERT` explicitly passes `NULL`:

~~~sql
CREATE TABLE payment_methods_v2 (
    method_id   NUMBER(19) NOT NULL,
    method_name VARCHAR2(50 CHAR)
        DEFAULT ON NULL 'UNSPECIFIED' NOT NULL
);
~~~

`DEFAULT ON NULL` is a business decision. Use it only when `NULL` genuinely means "use the default value." If `NULL` means required data is missing, let the database reject it rather than silently substituting a value.

### 2.2. Empty Strings in Oracle

Oracle treats zero-length strings in character types like `VARCHAR2`/`CHAR` as `NULL`. Therefore:

~~~sql
INSERT INTO customers (customer_id, customer_name)
VALUES (1003, '');
~~~

triggers ORA-01400 if `customer_name` is `NOT NULL`. A string containing only spaces, such as `'   '`, is not the same as an empty string; it remains a non-null character value unless normalized by the application or a constraint.

If business rules reject whitespace-only strings, enforce it with `CHECK`:

~~~sql
ALTER TABLE customers
  ADD CONSTRAINT ck_customers_name_not_blank
  CHECK (TRIM(customer_name) IS NOT NULL);
~~~

A `CHECK` constraint only validates the condition; for mandatory columns, still declare `NOT NULL` separately. Test the condition against real data and application normalization rules.

### 2.3. Common Causes

- `INSERT` omits a mandatory column that has no default.
- The application binds `NULL` due to a missing DTO field.
- ORM mapping fails to populate a field before persisting.
- ETL/import has blank cells or the source lacks the corresponding field.
- A `BEFORE INSERT` trigger sets the column to `NULL`.
- `INSERT INTO ... SELECT` pulls `NULL` from the source or a faulty `CASE`/`NVL` expression.
- A view with an `INSTEAD OF` trigger forwards data to the base table and produces `NULL` for a mandatory column.
- An empty string value is treated by Oracle as `NULL`.

Inspect both the base DML and any triggers. Never look only at the object the application calls, as the error can arise inside downstream triggers or procedures.

### 2.4. Resolving ORA-01400

Choose the fix based on business semantics:

1. If the field is mandatory and the source has a valid value, pass the proper value.
2. If the column has a valid default value, declare `DEFAULT` and decide whether `DEFAULT ON NULL` is appropriate.
3. If `NULL` is a valid business state, consider dropping `NOT NULL` after evaluating impact on applications, constraints, and queries.
4. If source data is missing, route records to a reject/quarantine area for completion or remediation.
5. If a trigger or expression generates `NULL` unexpectedly, fix the logic where the value is computed.

Never automatically replace all `NULL`s with `0`, `'UNKNOWN'`, or a dummy date. Those placeholder values can corrupt reports, calculations, and business logic.

## 3. ORA-01438: Value Larger Than Specified Precision for NUMBER

ORA-01438 occurs when a numeric value, after conversion/rounding to the column's scale, cannot fit within the column's declared precision.

Oracle `NUMBER` can be declared with precision and scale:

~~~sql
NUMBER(p, s)
~~~

- **p (precision)** is the maximum number of significant digits.
- **s (scale)** is the number of digits to the right of the decimal point when scale is positive.
- If scale is `0`, the column stores integers up to `p` digits.
- Negative scale rounds digits to the left of the decimal point.
- Unconstrained `NUMBER` without precision/scale has a much wider range, though still bounded by Oracle's `NUMBER` type limits.

For typical `NUMBER(p,s)` with positive scale, the maximum number of integer digits is `p - s`.

Example:

~~~sql
CREATE TABLE invoices (
    invoice_id NUMBER(19) NOT NULL,
    amount     NUMBER(5, 2) NOT NULL
);
~~~

`NUMBER(5,2)` allows up to 5 significant digits with 2 decimal places; the typical maximum positive value is `999.99`. Examples:

| Input Value | Result |
|---|---|
| `12.34` | Valid |
| `999.99` | Valid |
| `1000.00` | Exceeds precision |
| `12.345` | Oracle rounds to scale 2 before storing, provided the result still fits within precision |
| `999.995` | Rounding can push the value beyond `NUMBER(5,2)` |

Failing example:

~~~sql
INSERT INTO invoices (invoice_id, amount)
VALUES (1, 1234.56);
~~~

The value has 4 integer digits while `NUMBER(5,2)` allows only 3 integer digits. Oracle returns ORA-01438.

### 3.1. Precision vs. Scale

For `NUMBER(8,2)`:

- Maximum of 8 significant digits per precision.
- 2 decimal digits per scale.
- Fits up to 6 integer digits in typical cases.
- `123456.78` fits within range.
- `1234567.89` exceeds range.

Scale is not separate from precision. `NUMBER(8,2)` does not mean "8 digits before the decimal point and 2 digits after"; total precision is 8.

With `NUMBER(6,0)`, numbers are stored without fractional digits. With `NUMBER(6,3)`, the integer range is smaller because 3 digits of precision are allocated to decimal places. With negative scale, Oracle rounds to multiples of 10, 100, etc., depending on scale; check the column definition and test boundary data.

### 3.2. What Does Oracle Do with Extra Decimal Digits?

If a value has more fractional digits than the column's scale, Oracle typically rounds to the column's scale when storing rather than always failing. For example, `NUMBER(5,2)` can store `12.345` as `12.35`. However, if rounding increases the digit count beyond precision, the operation still fails.

Do not rely on implicit rounding when financial rules require explicit rounding. Decide the rounding mode in the business layer and validate range before writing.

### 3.3. Resolving ORA-01438

- Determine whether the input value is valid according to business rules.
- If the value is valid and the column definition is too narrow, consider increasing precision.
- If the value is wrong due to unit mistakes, bad conversions, or shifted decimal points, fix the source data.
- If the number of decimal places is invalid, apply the agreed rounding or rejection rule.
- For columns storing quantities, monetary amounts, rates, or codes, choose appropriate precision/scale at design time.

Example increasing precision:

~~~sql
ALTER TABLE invoices
  MODIFY (amount NUMBER(12, 2));
~~~

Before altering, inspect all applications, views, packages, triggers, ETL pipelines, indexes/function-based indexes, and data contracts using the column. Widening precision expands the storage domain, yet type changes still require compatibility review and coordinated deployment.

If business rules forbid negative numbers or overly large amounts, increasing precision does not enforce business boundaries. Use a `CHECK` constraint to define the valid domain:

~~~sql
ALTER TABLE invoices
  ADD CONSTRAINT ck_invoices_amount
  CHECK (amount BETWEEN 0 AND 9999999999.99);
~~~

A `CHECK` constraint returns ORA-02290 when a value falls outside the domain. Keep a separate `NOT NULL` if `NULL` is disallowed, because a `CHECK` expression evaluates to `UNKNOWN` when the value is `NULL`.

## 4. ORA-12899: String Exceeds Column Length

ORA-12899 occurs when a character value being written is longer than the column limit. The error message usually reports owner/table/column along with actual and maximum length. Length units depend on `BYTE` vs. `CHAR` semantics and Oracle version formatting in the message.

Example:

~~~sql
CREATE TABLE contacts (
    contact_id NUMBER(19) NOT NULL,
    full_name  VARCHAR2(20 BYTE) NOT NULL
);
~~~

The following value exceeds 20 bytes:

~~~sql
INSERT INTO contacts (contact_id, full_name)
VALUES (1, 'Nguyễn Văn An');
~~~

The name has fewer than 20 visible characters, but in a multi-byte character set such as `AL32UTF8`, a single accented character can occupy multiple bytes. Consequently, the byte length exceeds the character count.

### 4.1. BYTE Semantics vs. CHAR Semantics

Oracle lets you declare `VARCHAR2` length in bytes or characters:

~~~sql
CREATE TABLE byte_columns (
    code VARCHAR2(20 BYTE)
);

CREATE TABLE char_columns (
    display_name VARCHAR2(20 CHAR)
);
~~~

- **BYTE semantics** limits the number of bytes stored in the database character set.
- **CHAR semantics** limits the number of characters under Oracle's semantics, while remaining subject to the maximum byte limit allowed by the data type and database.

If the database uses `AL32UTF8`, accented letters or non-ASCII characters can take multiple bytes. A `VARCHAR2(20 BYTE)` column can therefore hold fewer than 20 Vietnamese characters. `VARCHAR2(20 CHAR)` is better suited when the business requirement is a maximum of 20 characters, while still respecting Oracle's maximum byte limit.

If `BYTE`/`CHAR` is omitted in DDL, default semantics are governed by `NLS_LENGTH_SEMANTICS` at column creation time. To keep schemas explicit and consistent across environments, specify it explicitly in DDL.

### 4.2. LENGTH and LENGTHB

Oracle provides functions to measure length:

~~~sql
SELECT LENGTH('Nguyễn Văn An')  AS char_length,
       LENGTHB('Nguyễn Văn An') AS byte_length
FROM dual;
~~~

- `LENGTH` returns the character count under Oracle's semantics.
- `LENGTHB` returns the byte count in the database character set.
- `LENGTHC` returns the count of Unicode complete characters.
- `LENGTH2` and `LENGTH4` measure UCS2 and UCS4 code points respectively when distinguishing Unicode supplementary characters.

When investigating a `BYTE` column, compare using `LENGTHB`. For `CHAR` columns, `LENGTH` or `LENGTHC` may be appropriate depending on Unicode requirements. Do not guess from visible characters on screen or from Java's `String.length()`.

Check the database character set:

~~~sql
SELECT parameter,
       value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
);
~~~

`AL32UTF8` is the most common Unicode character set. If a database uses a different character set, byte counts for the same string may differ.

### 4.3. Checking the Column Definition

Use the data dictionary to inspect length and semantics:

~~~sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       data_length,
       char_length,
       char_used,
       nullable
FROM all_tab_columns
WHERE owner = 'APP'
  AND table_name = 'CONTACTS'
ORDER BY column_id;
~~~

Key columns:

- `DATA_LENGTH`: maximum length in bytes.
- `CHAR_LENGTH`: declared length under character semantics.
- `CHAR_USED`: `B` for `BYTE`, `C` for `CHAR`, or `NULL` where inapplicable.
- `NULLABLE`: `Y` if the column allows `NULL`, `N` otherwise.

Table and column names in the dictionary are typically stored in uppercase unless created with quoted identifiers. Use the right owner and verify access privileges.

### 4.4. Resolving ORA-12899

There are three options:

1. If the source value is invalid, fix the source or reject the record.
2. If the schema was declared too short for business requirements, increase the length or switch to `CHAR` semantics after impact assessment.
3. If business rules strictly require the limit, ask the user to shorten the text or store extended content in a separate field.

Example increasing length:

~~~sql
ALTER TABLE contacts
  MODIFY (full_name VARCHAR2(100 CHAR));
~~~

Never blindly use `SUBSTR` to truncate data before inserting. Truncation can corrupt names, identifiers, addresses, or audit data. If business rules allow truncation, define exact truncation rules, notify the user, and retain the original value if required.

## 5. Out-of-Domain Business Values and CHECK Constraints

A value can match the column's data type and length yet still be invalid under business rules. Examples:

- Quantity must be greater than 0.
- Payment amount must be non-negative.
- Status must belong to a fixed set of values.
- End date must not precede start date.
- Percentage must be between 0 and 100.

Use `CHECK` constraints to enforce business domains in the database:

~~~sql
CREATE TABLE promotions (
    promotion_id NUMBER(19) NOT NULL,
    discount_pct NUMBER(5, 2) NOT NULL,
    start_date   DATE NOT NULL,
    end_date     DATE NOT NULL,
    status       VARCHAR2(20 CHAR) NOT NULL,

    CONSTRAINT ck_promo_discount
        CHECK (discount_pct BETWEEN 0 AND 100),

    CONSTRAINT ck_promo_dates
        CHECK (end_date >= start_date),

    CONSTRAINT ck_promo_status
        CHECK (status IN ('DRAFT', 'ACTIVE', 'EXPIRED'))
);
~~~

A `discount_pct` of `150` does not cause ORA-01438 since `NUMBER(5,2)` can store it, yet it violates the `CHECK` constraint and raises ORA-02290. This shows that data-type limits and business-domain limits are separate layers.

### 5.1. CHECK and NULL

A `CHECK` constraint does not replace `NOT NULL`. In SQL, a `CHECK` condition rejects a row only when the expression evaluates to `FALSE`; an `UNKNOWN` result caused by `NULL` is accepted.

Example:

~~~sql
CREATE TABLE products (
    product_id NUMBER NOT NULL,
    price      NUMBER CHECK (price >= 0)
);
~~~

`price = -1` is rejected, but `price = NULL` is accepted. If `price` is mandatory, declare:

~~~sql
price NUMBER NOT NULL CHECK (price >= 0)
~~~

### 5.2. Constraints vs. Triggers

`CHECK` constraints are ideal for single-row conditions using Oracle-supported expressions. If a rule must look up another table or inspect complex state, consider foreign keys, unique constraints, triggers, or transactional business logic. Avoid using triggers for simple domain checks because triggers are harder to inspect and can raise errors separate from the caller's statement logic.

Never place a `CHECK` constraint calling a user-defined function whose output changes over time or depends on other tables; that makes consistency difficult to guarantee.

## 6. Related Data Errors to Distinguish

| Error Code | Common Meaning | Investigation Focus |
|---|---|---|
| ORA-01400 | NULL into a NOT NULL column | Bind values, defaults, triggers, source data |
| ORA-01438 | NUMBER exceeds precision | `DATA_PRECISION`, `DATA_SCALE`, numeric value |
| ORA-12899 | String exceeds column length | `DATA_LENGTH`, `CHAR_LENGTH`, `CHAR_USED`, `LENGTHB` |
| ORA-02290 | CHECK constraint violated | CHECK condition and input value |
| ORA-02291 | Parent key not found for foreign key | Parent key, data load order |
| ORA-02292 | Cannot delete/update parent due to child rows | Referential relationships and delete rules |
| ORA-00001 | Duplicate unique/primary key | Duplicate key, sequence, retries |
| ORA-01722 | Invalid string-to-NUMBER conversion | Format, NLS, bind type, source data |
| ORA-01861 | Literal does not match date/time format | Format mask and date value |
| ORA-01843 | Not a valid month | Date format and `NLS_DATE_LANGUAGE` |

Do not handle every error by widening columns or dropping constraints. ORA-02291 is a referential error, not a precision error; ORA-01722 is a conversion error, not an undersized `NUMBER` column.

### 6.1. Numeric Conversion Errors

If an application passes a string into a `NUMBER` column, Oracle performs implicit conversion. Strings such as `'12,50'` depend on `NLS_NUMERIC_CHARACTERS`; non-numeric strings raise ORA-01722.

Bind numeric values as `NUMBER` from the application instead of concatenating SQL strings. If parsing text inside SQL is unavoidable, specify an explicit format model and NLS parameter:

~~~sql
SELECT TO_NUMBER(
         :amount_text,
         '999999D99',
         'NLS_NUMERIC_CHARACTERS=''.,'''
       )
FROM dual;
~~~

This works only when inputs match the declared mask. When source data arrives in multiple formats, normalize it during staging and reject unparseable values.

### 6.2. Date Conversion Errors

Never rely on default session date formats. Bind `DATE`/`TIMESTAMP` types from JDBC; if accepting strings, parse with an explicit format mask:

~~~sql
INSERT INTO events (event_id, event_date)
VALUES (
    :event_id,
    TO_DATE(:date_text, 'YYYY-MM-DD')
);
~~~

If data includes timezones or time components, consider `TIMESTAMP WITH TIME ZONE` and the matching JDBC API. Avoid date strings dependent on `NLS_DATE_FORMAT` in migrations or ETL.

## 7. Step-by-Step Diagnostic Procedure

When an error occurs in an application, SQL script, or import job, capture the full statement, bind values, error stack, and transaction context before making changes.

### Step 1: Read the Exact Error Message

Record:

- ORA error code.
- Owner, table, and column named in the message.
- SQL statement or procedure being executed.
- Bind values and bind types.
- Phase when the error occurred: execute, flush, commit, or batch.
- Any intermediate triggers, views, or procedures.

When using Hibernate, the error may surface at flush or transaction commit rather than on the `persist` call. Enable SQL and bind parameter logging in a test environment to find the exact DML statement.

### Step 2: Inspect the Column Definition

Example checking table `CONTACTS`:

~~~sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       data_length,
       char_length,
       char_used,
       data_precision,
       data_scale,
       nullable,
       data_default
FROM all_tab_columns
WHERE owner = 'APP'
  AND table_name = 'CONTACTS'
ORDER BY column_id;
~~~

For `NUMBER`, inspect `DATA_PRECISION` and `DATA_SCALE`. For `VARCHAR2`/`CHAR`, inspect `DATA_LENGTH`, `CHAR_LENGTH`, and `CHAR_USED`. For mandatory columns, inspect `NULLABLE`. `DATA_DEFAULT` may be exposed as a special dictionary type (`LONG`) depending on version; handle view column limitations when querying.

### Step 3: Inspect Constraints

~~~sql
SELECT c.owner,
       c.table_name,
       c.constraint_name,
       c.constraint_type,
       c.status,
       c.validated,
       cc.column_name,
       c.search_condition
FROM all_constraints c
LEFT JOIN all_cons_columns cc
  ON cc.owner = c.owner
 AND cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.owner = 'APP'
  AND c.table_name = 'CONTACTS'
ORDER BY c.constraint_name, cc.position;
~~~

For `CHECK` constraints, inspect `SEARCH_CONDITION` or `SEARCH_CONDITION_VC` depending on version and view. If the dictionary truncates or restricts display due to `LONG`, use `DBMS_METADATA` or DDL extraction tools to read the full definition.

### Step 4: Inspect Triggers and Intermediate Objects

~~~sql
SELECT owner,
       trigger_name,
       triggering_event,
       trigger_type,
       status
FROM all_triggers
WHERE table_owner = 'APP'
  AND table_name = 'CONTACTS'
ORDER BY trigger_name;
~~~

If DML runs through a view, package, or procedure, inspect `INSTEAD OF` triggers, variable assignments, and internal `INSERT`/`UPDATE` statements. A column may receive a different value than what the application sent because of a trigger or transformation expression.

### Step 5: Inspect Source Data

For ORA-12899, check both character and byte lengths:

~~~sql
SELECT customer_id,
       full_name,
       LENGTH(full_name)  AS char_length,
       LENGTHB(full_name) AS byte_length
FROM app.customer_import_stage
WHERE LENGTHB(full_name) > 20;
~~~

This example uses 20 bytes only when the target is `VARCHAR2(20 BYTE)`. If the target uses `CHAR` semantics, compare by character count and verify Unicode rules.

For ORA-01438, check maximum values and digit counts:

~~~sql
SELECT MAX(ABS(amount)) AS max_abs_amount,
       MAX(LENGTH(TO_CHAR(ABS(amount)))) AS max_rendered_length
FROM app.invoice_stage;
~~~

`TO_CHAR` length depends on format and NLS, so use it only as a rough indicator; the accurate check is comparing each value against target precision/scale and business rounding rules.

For ORA-01400:

~~~sql
SELECT COUNT(*) AS missing_customer_name
FROM app.customer_import_stage
WHERE customer_name IS NULL;
~~~

If empty strings were normalized to `NULL` by Oracle when stored in `VARCHAR2`, `IS NULL` detects those too. If data still resides outside the database, inspect source files or APIs prior to loading.

### Step 6: Reproduce with a Single Record

Use one representative record in a test environment to confirm the cause. Never run repeated tests directly in production where unintended data could be created. Test both valid and invalid boundary cases.

### Step 7: Choose Remediation and Verify

Once the root cause is identified, fix it at the data source, mapping, PL/SQL logic, or DDL. Re-run controlled tests, verify accepted/rejected record counts, and confirm constraints still guard the domain properly.

## 8. Data Validation in Java/JDBC Applications

The database is the last line of defense, but the application should validate data early to return clear error messages. Never wait for ORA-01400 or ORA-12899 and return a raw stack trace to end users.

### 8.1. NUMBER and BigDecimal

Use `BigDecimal` for currency, rates, or `NUMBER` columns requiring decimal precision. Avoid `double` for money because binary floating-point introduces representation inaccuracies.

Example validating `amount` for `NUMBER(12,2)`:

~~~java
public static BigDecimal validateAmount(BigDecimal value) {
    if (value == null) {
        throw new IllegalArgumentException("Amount is required");
    }

    BigDecimal normalized = value.setScale(
        2,
        RoundingMode.UNNECESSARY
    );

    BigDecimal max = new BigDecimal("9999999999.99");

    if (normalized.signum() < 0 || normalized.compareTo(max) > 0) {
        throw new IllegalArgumentException("Amount is outside the allowed range");
    }

    return normalized;
}
~~~

`RoundingMode.UNNECESSARY` rejects values that would require rounding to fit 2 decimal places. If business rules allow rounding, pick an explicit rounding mode such as `HALF_UP` or `HALF_EVEN`, then check range after rounding. Never let application layers and the database round independently under inconsistent rules.

Bind with `BigDecimal`:

~~~java
preparedStatement.setBigDecimal(1, amount);
~~~

If `NULL` is allowed:

~~~java
preparedStatement.setNull(1, Types.NUMERIC);
~~~

If disallowed, validate before calling JDBC while keeping `NOT NULL` in the schema.

### 8.2. VARCHAR2 and Unicode

For `VARCHAR2(20 CHAR)` columns, check character counts according to the Unicode rules chosen by the application. For `VARCHAR2(20 BYTE)`, check byte length in the database character set.

Java's `String.length()` counts UTF-16 code units, not bytes in the Oracle database character set and not always Unicode code points. For example, a supplementary character outside the BMP occupies two code units in Java.

If the database character set is `AL32UTF8` and the column uses `BYTE` semantics, you can pre-check UTF-8 byte count:

~~~java
int utf8Bytes = value.getBytes(StandardCharsets.UTF_8).length;
~~~

Use this measurement only when the database character set is genuinely UTF-8 compatible such as `AL32UTF8`. If the database uses another character set, byte counts may differ. Final checking in Oracle via `LENGTHB` is definitive.

For `CHAR` semantics, you can count code points:

~~~java
int codePoints = value.codePointCount(0, value.length());
~~~

However, this count can still differ from user-perceived grapheme clusters, such as a base letter combined with diacritical marks. Align length definitions with business requirements and verify against the database.

Bind strings in JDBC with `setString`:

~~~java
preparedStatement.setString(1, fullName);
~~~

For `NVARCHAR2`/`NCHAR` columns, use the appropriate national character set binding API such as `setNString` when supported by the driver. Do not rely on implicit conversion between `VARCHAR2` and `NVARCHAR2` without checking character sets.

### 8.3. Bean Validation Does Not Replace Database Constraints

Bean Validation can catch invalid input early:

~~~java
public record CustomerRequest(
    @NotNull
    Long customerId,

    @NotBlank
    @Size(max = 100)
    String customerName,

    @DecimalMin("0.00")
    @Digits(integer = 10, fraction = 2)
    BigDecimal creditLimit
) {}
~~~

Annotations like `@Size` and `@Digits` validate at the Java layer but do not replace schema constraints. `@Size` on a `String` measures Java `CharSequence` length, not bytes under `BYTE` semantics. `@Digits` checks precision/scale per Bean Validation rules and must be kept aligned with the actual `NUMBER(p,s)` definition.

Database constraints remain essential because data can also arrive from batch jobs, DBA scripts, integration services, or other applications.

## 9. Error Handling in JDBC and Batch Inserts

Errors can occur during `executeUpdate`, `executeBatch`, flush, or commit. Preserve the vendor error code and message in logs for investigation while returning a standardized business error to the client.

Example:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO customers(customer_id, customer_name) VALUES (?, ?)")) {

    ps.setLong(1, customerId);
    ps.setString(2, customerName);

    ps.executeUpdate();
} catch (SQLException e) {
    log.error(
        "Insert customer failed. SQLState={}, vendorCode={}, message={}",
        e.getSQLState(),
        e.getErrorCode(),
        e.getMessage(),
        e
    );
    throw e;
}
~~~

Do not log passwords, tokens, or sensitive personal data. For business records, log only reference keys and enough context for troubleshooting per security policy.

### 9.1. BatchUpdateException

When a batch contains failing records, the driver may throw `BatchUpdateException`. `getUpdateCounts()` indicates execution status for statements in the batch according to driver behavior; do not assume statements after the error did or did not run without checking driver documentation.

~~~java
try {
    ps.executeBatch();
} catch (BatchUpdateException e) {
    int[] counts = e.getUpdateCounts();

    log.error(
        "Batch failed; processed statement count={}, vendorCode={}",
        counts.length,
        e.getErrorCode()
    );

    connection.rollback();
    throw e;
}
~~~

If valid records must be kept while isolating failed ones, design an explicit rejection mechanism. Never commit partially simply because the driver returned positive update counts; verify transaction semantics and batch behavior against driver, auto-commit, and database settings.

### 9.2. Transactions and Rollback

When multiple DML statements must succeed together, set `autoCommit=false` and roll back when any operation violates a constraint:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        insertCustomer(connection, customer);
        insertOrders(connection, orders);
        connection.commit();
    } catch (SQLException e) {
        connection.rollback();
        throw e;
    }
}
~~~

In Oracle, DDL issues an implicit commit. Never mix DDL and DML in an application transaction expecting rollback to undo both. With JPA/Hibernate, constraint errors may be thrown at flush or commit; roll back the transaction and discard the failed persistence context.

## 10. Validating Data Before Bulk Loads

When importing from CSV, Excel, external systems, or staging tables, separate data ingestion from loading target business tables.

Processing flow:

~~~text
File / API / External source
            |
            v
     Staging table
            |
            v
  Validate type, null, length,
  precision, scale, domain
        /         \
       /           \
      v             v
 Valid rows      Reject rows
      |             |
      v             v
 Target tables   Error detail,
                 source row,
                 reason
~~~

Staging tables should retain enough source data for investigation—potentially storing raw fields as `VARCHAR2`/`CLOB` during initial parsing depending on design. After validation, cast valid rows to target types with explicit conversions.

### 10.1. Isolating Invalid Records with SQL

Example checking name strings exceeding 100 characters:

~~~sql
SELECT source_row_id,
       customer_name,
       LENGTH(customer_name) AS char_length
FROM customer_stage
WHERE customer_name IS NULL
   OR LENGTH(customer_name) > 100;
~~~

If the target column uses `BYTE` semantics, check `LENGTHB` instead of `LENGTH` using the matching character set.

Example validating monetary amounts:

~~~sql
SELECT source_row_id,
       amount_text
FROM payment_stage
WHERE amount_text IS NULL
   OR VALIDATE_CONVERSION(
        amount_text AS NUMBER,
        '9999999999D99',
        'NLS_NUMERIC_CHARACTERS=''.,'''
      ) = 0;
~~~

`VALIDATE_CONVERSION` is available on supported Oracle versions; confirm your database version before using it. After parsing, verify range and scale against the target column domain.

### 10.2. Using DML Error Logging

Oracle supports DML error logging for certain `INSERT`/`UPDATE`/`MERGE` operations to write per-row errors into an error table instead of aborting the entire statement on the first error.

Create the error table:

~~~sql
BEGIN
  DBMS_ERRLOG.CREATE_ERROR_LOG(
    dml_table_name => 'CUSTOMERS',
    err_log_table_name => 'ERR$_CUSTOMERS'
  );
END;
/
~~~

Execute the insert:

~~~sql
INSERT INTO customers (
    customer_id,
    customer_name
)
SELECT customer_id,
       customer_name
FROM customer_stage
LOG ERRORS INTO err$_customers ('CUSTOMER_LOAD')
REJECT LIMIT UNLIMITED;
~~~

The error table records error details and row values within `DBMS_ERRLOG` limits. Some data types/objects and operations are unsupported or restricted; consult Oracle documentation for your exact release. DML error logging does not replace business validation, and not all statement errors can be logged as per-row errors.

After loading, reconcile source row count, successfully inserted rows, and error table rows. Maintain a controlled process to review rejects, fix source data, and reprocess.

## 11. Updating the Schema When Column Limits No Longer Fit

If errors reveal that the schema is too narrow for evolving business requirements, create a migration to widen the column. Before changing it, review all schema consumers and backward compatibility.

### 11.1. Increasing String Length

~~~sql
ALTER TABLE customers
  MODIFY (customer_name VARCHAR2(200 CHAR));
~~~

Switching from `BYTE` to `CHAR` can change semantics and byte limits. Check Oracle version, `MAX_STRING_SIZE`, character set, index key length limits, views, packages, and applications.

### 11.2. Increasing NUMBER Precision

~~~sql
ALTER TABLE invoices
  MODIFY (amount NUMBER(14, 2));
~~~

Inspect existing data, check constraints, function-based indexes, views, and code mappings. If the column is used in calculations, check precision of intermediate expressions and `OUT` parameters.

### 11.3. Safely Adding NOT NULL

If a column currently allows `NULL` but business rules now require it, do not add `NOT NULL` directly while `NULL` rows exist.

First check existing data:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE customer_name IS NULL;
~~~

Determine backfill values from an authoritative source. After backfilling and verifying:

~~~sql
ALTER TABLE customers
  MODIFY (customer_name NOT NULL);
~~~

If missing values cannot be recovered, explicitly decide which records to reject, fix manually, or keep nullable per business rules. Never insert dummy strings just to pass the constraint if applications treat that column as real names.

### 11.4. Changing Schema Through Migrations

All schema changes should be captured as versioned migrations, reviewed, and tested before production. Because Oracle DDL issues implicit commits, migrations must support safe recovery after partial failure. For rolling deployments, use expand-and-contract patterns so old and new code work together during the transition window.

## 12. Errors Originating from ORMs or PL/SQL

### Hibernate/JPA

With JPA, values are not always written immediately at `save`. Hibernate often defers SQL until flush. As a result, ORA-01400, ORA-01438, or ORA-12899 can surface at:

- `entityManager.flush()`
- `repository.flush()`
- before a query requiring persistence context synchronization
- transaction commit

To pinpoint the offending record, enable SQL and bind logging in a test environment, reduce batch size, or split chunks to isolate. When batching is active, a single error can roll back the entire transaction depending on configuration and driver.

Mappings must match the schema:

~~~java
@Column(name = "CUSTOMER_NAME", nullable = false, length = 100)
private String customerName;

@Column(name = "AMOUNT", precision = 12, scale = 2)
private BigDecimal amount;
~~~

Attributes like `length`, `precision`, and `scale` describe the mapping/DDL generation. When a migration tool is the source of truth, mappings should match the schema, and you should never use Hibernate `ddl-auto=update` to mutate production automatically.

### PL/SQL Procedures

A procedure may assign values into variables or columns of different types. Errors can occur on an `INSERT`/`UPDATE` inside the procedure rather than on the caller's binds.

Preserve the stack trace using:

~~~sql
EXCEPTION
  WHEN OTHERS THEN
    DBMS_OUTPUT.PUT_LINE(SQLERRM);
    DBMS_OUTPUT.PUT_LINE(DBMS_UTILITY.FORMAT_ERROR_BACKTRACE);
    RAISE;
END;
~~~

In production, write errors to proper logging/audit tables rather than relying solely on `DBMS_OUTPUT`. Crucially, re-`RAISE` the exception if the caller needs to know the transaction failed; never catch and silently ignore exceptions.

## 13. Consolidated Diagnostic Examples

### ORA-01400

Suppose the error message reports cannot insert NULL into `APP.CUSTOMERS.CUSTOMER_NAME`.

Check:

~~~sql
SELECT column_name,
       nullable,
       data_default,
       data_type,
       data_length
FROM all_tab_columns
WHERE owner = 'APP'
  AND table_name = 'CUSTOMERS'
  AND column_name = 'CUSTOMER_NAME';
~~~

Then inspect the `INSERT` statement, bind values, triggers, and source data. If customer name is mandatory, fix the producer/import to send valid names. If business rules allow unknown names, evaluate changing the constraint and all dependent consumers.

### ORA-01438

Suppose the error message points to `APP.INVOICES.AMOUNT`.

Check:

~~~sql
SELECT data_type,
       data_precision,
       data_scale
FROM all_tab_columns
WHERE owner = 'APP'
  AND table_name = 'INVOICES'
  AND column_name = 'AMOUNT';
~~~

If it is `NUMBER(5,2)`, check for values over `999.99` or post-rounding results. If the value is valid under business rules, create a migration to increase precision; if invalid, reject or fix source data.

### ORA-12899

Suppose the error message reports `APP.CONTACTS.FULL_NAME`, actual length 28, maximum 20.

Check:

~~~sql
SELECT data_length,
       char_length,
       char_used
FROM all_tab_columns
WHERE owner = 'APP'
  AND table_name = 'CONTACTS'
  AND column_name = 'FULL_NAME';
~~~

Measure source data using `LENGTH` and `LENGTHB`. If the column uses `BYTE` semantics, multi-byte characters can exceed the byte limit. If business rules allow 20 characters, consider `CHAR` semantics or increasing the limit; otherwise reject overly long values with a clear message.

### ORA-02290

Suppose constraint `CK_PROMO_DISCOUNT` raises an error:

~~~sql
SELECT constraint_name,
       search_condition
FROM all_constraints
WHERE owner = 'APP'
  AND table_name = 'PROMOTIONS'
  AND constraint_type = 'C';
~~~

Inspect the condition and input value. If `discount_pct` must be between 0 and 100, a value of `150` is a business error even though `NUMBER(5,2)` can store it. Do not increase precision to "fix" this error.

## 14. Designing User-Facing Error Messages

Never expose raw ORA errors or internal table names to end users. Map technical errors to validation messages:

| Database Error | Suggested Business Message |
|---|---|
| ORA-01400 | Required field was not provided |
| ORA-01438 | Numeric value exceeds allowed range |
| ORA-12899 | Field value exceeds maximum length |
| ORA-02290 | Value does not satisfy business rules |
| ORA-02291 | Referenced record does not exist |
| ORA-00001 | Value already exists or is duplicated |

Validate early in the service layer to return field-specific errors. If the database still rejects the write, log the vendor error code and correlation/request ID and return a generic actionable error. Never leak SQL, schema names, sensitive data, or stack traces to clients.

## 15. Safe Handling Principles

- Read the exact ORA code and owner/table/column before making fixes.
- Check the real definition in the data dictionary rather than relying on entities or outdated documentation.
- Distinguish `NULL`, empty strings, and whitespace-only strings.
- Distinguish precision from scale; inspect values both before and after rounding rules.
- For ORA-12899, inspect `BYTE`/`CHAR` semantics and database character set; use `LENGTHB` when needed.
- Use `BigDecimal` for Oracle `NUMBER` values requiring precision and bind with the proper JDBC type.
- Use explicit format masks/NLS parameters when converting strings to numbers or dates in SQL.
- Keep `NOT NULL`, `CHECK`, `UNIQUE`, and `FOREIGN KEY` constraints active in the database.
- Never silently truncate strings, replace `NULL` with dummy values, or round outside business rules.
- For bulk imports, use staging and reject tables to preserve bad rows for investigation.
- When updating schemas, use versioned migrations, test thoroughly, and assess all dependent applications.
- For Oracle DDL, plan for implicit commits and partial failures.
- Log enough technical detail for investigation without exposing sensitive data.
- After fixing, verify success counts, reject counts, constraints, and boundary values.

ORA-01400, ORA-01438, and ORA-12899 all indicate data incompatible with a column's definition, yet each reflects a distinct constraint: nullability, numeric precision, or character/byte length. Combining schema inspection, source data analysis, business rules, and proper application binding identifies the real cause, preserves data meaning, and prevents recurring write failures.
