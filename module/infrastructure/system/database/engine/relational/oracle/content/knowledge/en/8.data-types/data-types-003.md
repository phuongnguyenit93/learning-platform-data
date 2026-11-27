# BINARY_FLOAT, BINARY_DOUBLE, and Special Numeric Values in Oracle Database

When storing sensor readings, scientific calculations, or quantities spanning huge ranges, Oracle Database provides two binary floating-point data types: **`BINARY_FLOAT`** and **`BINARY_DOUBLE`**. They differ from `NUMBER` in **representation**, **precision**, **value range**, and **behavior when special values occur** such as *NaN* or positive/negative infinity.

A very practical question: *Why can a query filtering `reading > 100` also return a row containing NaN?* In Oracle SQL, **NaN is treated as greater than every other numeric value, including positive infinity, and equal to itself**. This differs from the NaN comparison semantics commonly seen in Java, Python, and pure IEEE 754 intuition. Therefore, using these numeric types requires clear data validation and sanitization rules.

This lesson belongs to the **Data Types** module of relational Oracle Database; the examples use standard SQL in Oracle Database 19c and later and can be executed in SQL*Plus, SQLcl, or other SQL tools with appropriate privileges. Exact numeric display formatting may vary depending on tool formatting, NLS settings, and client software.

## 1. Distinguishing NUMBER, BINARY_FLOAT, and BINARY_DOUBLE

### 1.1. Comparison Table

| Characteristic | `NUMBER` | `BINARY_FLOAT` | `BINARY_DOUBLE` |
| --- | --- | --- | --- |
| Representation | Oracle **decimal** precision number | 32-bit **binary** floating-point number | 64-bit **binary** floating-point number |
| Storage size | Variable length per Oracle storage format, up to ~22 bytes | **4 bytes** | **8 bytes** |
| Precision | Up to ~**38 significant decimal digits** | Roughly **6–9 decimal digits** on conversion/representation; commonly ~7 significant digits | Roughly **15–17 decimal digits** on conversion/representation; commonly ~15–16 significant digits |
| Largest finite number (approx.) | Less than `1E126` | `3.4028235E38` | `1.7976931348623157E308` |
| Smallest positive **normal** number (approx.) | Around `1E-130` per NUMBER range | `1.17549435E-38` | `2.2250738585072014E-308` |
| Special values supported | Does not contain NaN or ±Infinity as NUMBER values | Has **NaN**, **+Infinity**, **-Infinity** | Has **NaN**, **+Infinity**, **-Infinity** |
| Fractional arithmetic | Uses NUMBER decimal precision | Binary approximation; subject to rounding | Binary approximation; subject to rounding |
| Suitable use cases | Money, accounting, exact decimals, numeric identifiers | Measurements/simulations where single precision suffices | Scientific computing, statistics, measurements needing larger precision/range |

**Note:** The 6–9 and 15–17 digit precision ranges characterize IEEE 754 representation/conversion, not a guarantee that every decimal value with that many digits is stored exactly. When monetary calculations must be exact to decimal places, typically choose `NUMBER(p,s)`, such as `NUMBER(18,2)`.

### 1.2. `BINARY_FLOAT` and `BINARY_DOUBLE` Are Truly Separate Types

Oracle defines:

- `BINARY_FLOAT` uses 32 bits, corresponding to IEEE 754 *single precision*. Inside 32 bits there is **1 sign bit**, **8 exponent bits**, and **23 stored fraction bits** (24-bit effective significand precision).
- `BINARY_DOUBLE` uses 64 bits, corresponding to *double precision*. Inside 64 bits there is **1 sign bit**, **11 exponent bits**, and **52 stored fraction bits** (53-bit effective significand precision).

Conceptual layout:

```text
BINARY_FLOAT  (32-bit)
+------+--------------+--------------------------+
| sign | exponent (8b)| stored fraction (23-bit) |
+------+--------------+--------------------------+

BINARY_DOUBLE (64-bit)
+------+---------------+--------------------------------+
| sign | exponent (11b)| stored fraction (52-bit)       |
+------+---------------+--------------------------------+
```

More bits allow `BINARY_DOUBLE` to store **more significant digits** and represent a **larger value range**. However, both are **approximate** types; many familiar decimal numbers still have no finite binary representation.

### 1.3. Do Not Confuse Oracle FLOAT with BINARY_FLOAT

In Oracle SQL, **`FLOAT`** is a subtype of **`NUMBER`**, with precision declared in binary bits in SQL syntax, and is not synonymous with the 32-bit IEEE 754 type.

Example:

```sql
CREATE TABLE numeric_type_examples (
    exact_value  NUMBER(18, 4),
    legacy_float FLOAT(126),
    float32_val  BINARY_FLOAT,
    float64_val  BINARY_DOUBLE
);
```

Here `legacy_float` does **not** become a `BINARY_FLOAT` column. If you want IEEE 754 binary floating-point numbers, explicitly declare `BINARY_FLOAT` or `BINARY_DOUBLE`.

## 2. Why Is Decimal 0.1 Not Always Exact?

### 2.1. Binary Mechanics

In decimal:

```text
0.1 = 1 / 10
```

This number is represented exactly with one digit after the decimal point. In binary, however, `0.1` has an infinite expansion; a 32-bit/64-bit type can only store finitely many bits and must **round** to the nearest binary value.

Consequences:

- The stored value is an approximation of the decimal number entered.
- Two computations yielding the same mathematical result can produce different bit sequences.
- Testing with `=` may be inappropriate if the goal is "approximately equal" within an allowed tolerance.

Example:

```sql
SELECT
    0.1 + 0.2                    AS decimal_expression,
    0.1d + 0.2d                  AS double_expression,
    TO_BINARY_FLOAT(0.1)        AS float_expression,
    TO_BINARY_DOUBLE(0.1)       AS converted_double
FROM dual;
```

Expressions containing the `d` suffix or `TO_BINARY_DOUBLE` conversion use binary floating-point types. Tools may round numbers on **display**, so two columns looking identical does not prove they share the same internal representation.

### 2.2. Precision Differs from Range Magnitude

`BINARY_DOUBLE` has a much larger representation range than `NUMBER` in terms of **exponent**, yet it only has roughly 15–17 decimal digits of binary precision.

Example with large integers:

```sql
SELECT
    CASE
      WHEN TO_BINARY_DOUBLE(9007199254740992) =
           TO_BINARY_DOUBLE(9007199254740993)
      THEN 'EQUAL AFTER CONVERSION'
      ELSE 'DIFFERENT'
    END AS double_comparison
FROM dual;
```

The numbers 9,007,199,254,740,992 and 9,007,199,254,740,993 are strictly distinct as `NUMBER`. In this magnitude region, however, 53-bit double resolution cannot represent every consecutive integer, so both can round to the same binary value. This is why `BINARY_DOUBLE` should not be used to store very large integer identifiers requiring exact matching.

### 2.3. Normal, Subnormal, Underflow

Alongside *normal* numbers, IEEE 754 also has **subnormal** numbers very close to 0, with lower relative precision. For `BINARY_FLOAT`, the smallest positive subnormal is roughly `1.40129846E-45`; for `BINARY_DOUBLE`, roughly `4.9406564584124654E-324`.

A result too small to represent in the target format can **underflow to 0**. Conversely, a result too large to represent finitely can become **Infinity** in binary floating-point arithmetic.

Therefore, do not interpret "very large representation range" as "every operation keeps enough digits". Numeric range and precision are two separate limits.

## 3. Column Declarations, Literals, and Type Conversions

### 3.1. Creating a Table with Both Binary Numeric Types

```sql
CREATE TABLE sensor_readings (
    reading_id   NUMBER(12) PRIMARY KEY,
    sensor_code  VARCHAR2(30) NOT NULL,
    raw_value    BINARY_FLOAT,
    refined_value BINARY_DOUBLE,
    recorded_at  TIMESTAMP DEFAULT SYSTIMESTAMP
);
```

In this example:

- `raw_value` holds a 32-bit binary floating-point number.
- `refined_value` holds a 64-bit binary floating-point number.
- Both columns can store finite numbers, NaN, ±Infinity, or `NULL` if no `NOT NULL`/`CHECK` constraint restricts them.
- `recorded_at` uses `TIMESTAMP` to record the event time and is unrelated to floating-point range.

This table only illustrates schema syntax. Real designs must also consider data sources, unit standardization, outlier validation rules, and business requirements.

### 3.2. `f/F` and `d/D` Literals

Oracle supports direct suffixes in numeric literals:

| Syntax | Numeric Type |
| --- | --- |
| `25`, `0.5`, `1.25e3` | `NUMBER` per standard numeric literal syntax |
| `25f`, `0.5F`, `1.25e3f` | `BINARY_FLOAT` |
| `25d`, `0.5D`, `1.25e3d` | `BINARY_DOUBLE` |

Example:

```sql
SELECT
    12.5       AS number_value,
    12.5f      AS binary_float_value,
    12.5d      AS binary_double_value
FROM dual;
```

**Do not put quotes around the suffix.** `12.5d` is a binary numeric literal; `'12.5d'` is a character string and does not mean the same thing.

For numeric literals written directly in SQL, a period is normally used as the decimal separator according to SQL syntax. When converting from **strings** to numbers, NLS rules can apply. For external inputs, use appropriate bind variables/drivers instead of concatenating numbers or strings into SQL.

### 3.3. Conversion Functions

Common functions:

- `TO_BINARY_FLOAT(expr)`: converts an expression to `BINARY_FLOAT`.
- `TO_BINARY_DOUBLE(expr)`: converts an expression to `BINARY_DOUBLE`.
- `TO_NUMBER(expr)`: converts to `NUMBER` when the value is convertible and supported.
- `CAST(expr AS BINARY_FLOAT)` or `CAST(expr AS BINARY_DOUBLE)`: explicitly specifies the target type.

Example:

```sql
SELECT
    TO_BINARY_FLOAT(3.125)        AS as_float32,
    TO_BINARY_DOUBLE(3.125)       AS as_float64,
    CAST(3.125 AS BINARY_DOUBLE)  AS cast_float64
FROM dual;
```

The number `3.125 = 25/8` has a finite binary representation, so it is preserved exactly in both types within this range. Numbers like `0.1`, by contrast, must be rounded.

**Conversions do not restore lost precision.** If an exact number is rounded when written to `BINARY_FLOAT`, later converting it to `BINARY_DOUBLE` only represents the **already rounded value** more accurately—it does not recover the original decimal digits.

### 3.4. Numeric Precedence When Mixing Numeric Types

Oracle applies *numeric precedence*:

```text
BINARY_DOUBLE
      >
BINARY_FLOAT
      >
NUMBER
```

For operations/functions supporting these numeric types:

- If any operand is `BINARY_DOUBLE`, Oracle generally converts the other operand to `BINARY_DOUBLE` before computing.
- If there is no `BINARY_DOUBLE` but an operand is `BINARY_FLOAT`, Oracle generally converts to `BINARY_FLOAT`.
- If all operands are `NUMBER`, the operation uses `NUMBER` semantics.

Example:

```sql
SELECT
    1 + 0.5d         AS result_using_double,
    1 + 0.5f         AS result_using_float,
    1 + 0.5          AS result_using_number
FROM dual;
```

This rule means **a single double operand can cause a NUMBER expression to switch to binary representation**, introducing rounding the SQL author did not intend.

In addition, each SQL function has its own data type rules; always check the function documentation when results depend on return types.

## 4. Special Numeric Values: NaN and Infinity

### 4.1. What Is NaN?

**NaN** stands for *Not a Number*. It is a **valid floating-point value**, typically representing the result of an indeterminate operation, such as a floating-point `0.0 / 0.0` under IEEE 754 semantics.

NaN:

- Is a **value** stored in `BINARY_FLOAT`/`BINARY_DOUBLE`, not `NULL`.
- Is not a finite number for ordinary measurement.
- Can propagate through subsequent calculations.
- Has its own **comparison and sorting rules** in Oracle SQL.

In Oracle, NaN bit patterns are normalized by data type; Oracle does not expose separate signaling/quiet NaN exception-handling modes in ordinary SQL calculations.

### 4.2. What Is Infinity?

**Infinity** has two directions:

- **`+Infinity`**, written `+INF`: positive infinity.
- **`-Infinity`**, written `-INF`: negative infinity.

In binary floating-point arithmetic, results can become Infinity upon overflowing the finite range or dividing by zero in defined scenarios. Infinity is greater than all positive finite values or less than all negative finite values respectively, yet **NaN ranks higher than +Infinity** in Oracle SQL comparisons.

**Infinity is not simply a very large decimal number.** If "infinity" data appears in a business application, determine what business meaning it carries and whether it should be accepted or flagged as an error state.

### 4.3. Four Special Constants Provided by Oracle

| Oracle Constant | Type | Meaning |
| --- | --- | --- |
| `BINARY_FLOAT_NAN` | `BINARY_FLOAT` | Single-precision NaN |
| `BINARY_FLOAT_INFINITY` | `BINARY_FLOAT` | Single-precision positive infinity |
| `BINARY_DOUBLE_NAN` | `BINARY_DOUBLE` | Double-precision NaN |
| `BINARY_DOUBLE_INFINITY` | `BINARY_DOUBLE` | Double-precision positive infinity |

To represent negative infinity, apply the unary minus operator to the constant:

```sql
SELECT
    BINARY_FLOAT_INFINITY    AS positive_float_infinity,
   -BINARY_FLOAT_INFINITY    AS negative_float_infinity,
    BINARY_DOUBLE_NAN        AS double_nan,
   -BINARY_DOUBLE_INFINITY   AS negative_double_infinity
FROM dual;
```

There is no need for a separate "negative NaN" name: the sign of NaN has no numeric meaning under Oracle's provided semantics.

### 4.4. Zero and Negative Zero

IEEE 754 can represent `+0` and `-0` at the bit level. In Oracle floating-point types, **`-0` is normalized to `+0`**, and comparisons ignore the sign of zero.

Therefore, do not use the sign of zero to encode distinct business states in a `BINARY_FLOAT` or `BINARY_DOUBLE` column. If the application needs to distinguish two states, use a dedicated status column or an explicitly descriptive data type.

### 4.5. How Do NaN and Infinity Arise from Operations?

In binary floating-point operations under Oracle semantics, certain situations commonly produce:

| Situation | Typical Result |
| --- | --- |
| Exceeding the finite numeric range (*overflow*) | `+INF` or `-INF` |
| Result too small to represent (*underflow*) | Subnormal value or `0` depending on magnitude and rounding |
| Indeterminate operation (*invalid operation*) | `NaN` |
| Floating-point division by 0 | `+INF`, `-INF`, or `NaN` depending on operands |
| Result cannot be represented exactly (*inexact*) | A rounded finite number |

Oracle uses a default floating-point exception handling mode and does not raise custom **IEEE 754 floating-point exceptions** like some numeric computing environments. However, this **does not mean no SQL expression can fail**: `NUMBER` arithmetic, type conversions, data constraints, or syntax errors can still raise Oracle errors.

For instance, a pure `NUMBER` division by 0 can raise `ORA-01476: divisor is equal to zero`; this does not follow the same semantics as native floating-point division.

## 5. Distinguishing NaN, Infinity, and NULL

These three states are **completely different**:

| State | Nature | `IS NULL` | Can Appear in `BINARY_DOUBLE`? |
| --- | --- | --- | --- |
| Finite value | Approximate real number usable in math | FALSE | Yes |
| `NaN` | Floating-point Not-a-Number value | FALSE | Yes |
| `+INF` or `-INF` | Floating-point infinity value | FALSE | Yes |
| `NULL` | No SQL value | TRUE | Yes, if the column allows NULL |

A `NOT NULL` column **can still contain NaN or Infinity** unless another constraint prevents it. Likewise, `COUNT(column)` ignores `NULL` but counts both NaN and Infinity because they are non-null values.

### 5.1. Specialized Conditions

Oracle provides these conditions:

- `expression IS NAN`: value is NaN.
- `expression IS NOT NAN`: value is not NaN.
- `expression IS INFINITE`: value is positive or negative infinity.
- `expression IS NOT INFINITE`: value is neither positive nor negative infinity.

Examples:

```sql
SELECT reading_id, refined_value
FROM   sensor_readings
WHERE  refined_value IS NAN;

SELECT reading_id, refined_value
FROM   sensor_readings
WHERE  refined_value IS INFINITE;

SELECT reading_id, refined_value
FROM   sensor_readings
WHERE  refined_value IS NOT NULL
AND    refined_value IS NOT NAN
AND    refined_value IS NOT INFINITE;
```

The last query selects **finite, non-null** values, suitable as input for many statistical formulas.

**Syntax note:** `IS NAN` and `IS INFINITE` are Oracle SQL conditions, not function names like `IS_NAN(value)`. In SQL, use the syntax supported by the database; Java or Python have different function names and rules.

### 5.2. Using CASE to Classify Data

```sql
SELECT
    reading_id,
    CASE
      WHEN refined_value IS NULL THEN 'NULL'
      WHEN refined_value IS NAN THEN 'NaN'
      WHEN refined_value = BINARY_DOUBLE_INFINITY THEN '+Infinity'
      WHEN refined_value = -BINARY_DOUBLE_INFINITY THEN '-Infinity'
      ELSE 'FINITE'
    END AS value_class
FROM sensor_readings
ORDER BY reading_id;
```

The `IS NULL` condition is checked separately. The final `ELSE 'FINITE'` branch contains only finite cases once earlier branches have excluded NaN and ±Infinity.

In real applications, you can classify using `IS INFINITE` first and then check the sign, or use an equivalent `CASE` structure for readability.

## 6. How Oracle's NaN Comparison Rules Differ from Standard IEEE 754

### 6.1. Comparison Order Applied by Oracle

In Oracle Database SQL, the ordering of **non-null values** is:

```text
-Infinity  <  negative finite numbers  <  0  <  positive finite numbers  <  +Infinity  <  NaN
```

Specifically:

- `BINARY_DOUBLE_NAN > BINARY_DOUBLE_INFINITY` is **TRUE** in Oracle.
- `BINARY_DOUBLE_NAN = BINARY_DOUBLE_NAN` is **TRUE** in Oracle.
- NaN values are treated as equal to one another under Oracle's comparison semantics.

Verification example with `CASE`:

```sql
SELECT
    CASE
      WHEN BINARY_DOUBLE_NAN = BINARY_DOUBLE_NAN
      THEN 'TRUE' ELSE 'FALSE'
    END AS nan_equals_nan,
    CASE
      WHEN BINARY_DOUBLE_NAN > BINARY_DOUBLE_INFINITY
      THEN 'TRUE' ELSE 'FALSE'
    END AS nan_above_infinity
FROM dual;
```

This is a critical point when porting logic between SQL and Java/Python. In standard IEEE 754 comparisons in Java, `Double.NaN == Double.NaN` is **false**, whereas Oracle SQL defines an ordering where NaN is greatest and equals itself.

**Never apply application-language rules to infer comparison outcomes in Oracle SQL.**

### 6.2. Filtering with >, >= Can Accidentally Include NaN

Consider the SQL query:

```sql
SELECT reading_id, refined_value
FROM   sensor_readings
WHERE  refined_value > 100d;
```

If the data contains NaN, Oracle can include it in the result because **NaN is greater than every finite number**, including 100. This SQL statement is insufficient to express "valid readings greater than 100".

Safer version when the business only accepts finite numbers:

```sql
SELECT reading_id, refined_value
FROM   sensor_readings
WHERE  refined_value IS NOT NULL
AND    refined_value IS NOT NAN
AND    refined_value IS NOT INFINITE
AND    refined_value > 100d;
```

Similarly, when computing `MAX` or top-N reports, NaN can distort the interpretation of results if not filtered out beforehand.

### 6.3. ORDER BY and NULL

Example:

```sql
SELECT reading_id, refined_value
FROM   sensor_readings
ORDER BY refined_value ASC NULLS LAST;
```

Among non-null values, Oracle sorts **NaN after +Infinity**. `NULL` has its own sorting behavior and can be placed last or first with `NULLS LAST`/`NULLS FIRST`.

When sorting sensor data, decide explicitly:

1. Should NaN/Infinity be excluded?
2. Should outlier/special values be displayed as a separate group?
3. Does `NULL` mean "no measurement recorded" or "not applicable"?

Do not rely solely on `ORDER BY reading DESC` to determine valid top-N rows if the column can contain special values.

### 6.4. NaN Is Not NULL in Three-Valued Logic

SQL uses **TRUE**, **FALSE**, and **UNKNOWN** condition outcomes in contexts involving `NULL`. Example:

```sql
SELECT CASE
         WHEN CAST(NULL AS BINARY_DOUBLE) =
              CAST(NULL AS BINARY_DOUBLE)
         THEN 'TRUE'
         ELSE 'NOT TRUE'
       END AS null_comparison
FROM dual;
```

Comparing `NULL = NULL` does not return TRUE; thus `CASE` takes the `ELSE` branch. By contrast, comparing two NaNs in Oracle SQL can return TRUE.

Therefore, do not use `NVL` or `COALESCE` hoping to automatically replace NaN/Infinity; those functions handle **NULL**, and do not automatically convert special floating-point values into null.

## 7. Arithmetic, Rounding, and Approximate Equality Checks

### 7.1. Rounding Error and Non-Associative Addition

In pure mathematics:

```text
(a + b) + c = a + (b + c)
```

When storing and computing in finite binary floating-point, however, step-by-step rounding errors can cause the two expressions to differ in their trailing bits. This is especially noticeable when adding very large numbers to very small numbers.

Main causes:

- Significant digits exceeding representation capacity.
- Changing the order of operations.
- Converting between `BINARY_FLOAT` and `BINARY_DOUBLE`.
- Aggregate functions or parallel execution changing accumulation order.
- Round-tripping between decimal, driver, and binary floating-point.

Do not write business logic requiring **bit-exact matching** if computations rely on approximate floating-point without controlling these factors.

### 7.2. Approximate Equality with an Error Tolerance

For example, to check whether two finite measurements are within an absolute tolerance of `1E-9`:

```sql
SELECT reading_id, refined_value
FROM   sensor_readings
WHERE  refined_value IS NOT NULL
AND    refined_value IS NOT NAN
AND    refined_value IS NOT INFINITE
AND    ABS(refined_value - 12.5d) <= 1e-9d;
```

This is an **absolute tolerance**, suitable when the measured quantity and its scale are known. For data spanning many orders of magnitude, you can combine relative and absolute tolerances:

```sql
-- Illustrative pattern when parameter expected_value is known to be a finite number.
SELECT reading_id, refined_value
FROM   sensor_readings
WHERE  refined_value IS NOT NULL
AND    refined_value IS NOT NAN
AND    refined_value IS NOT INFINITE
AND    ABS(refined_value - 12.5d)
         <= 1e-9d * GREATEST(1d, ABS(refined_value), ABS(12.5d));
```

This is **not a universal formula for every business case**: tolerances must be chosen based on measurement units, source data accuracy, and risk tolerance. In particular, do not pass NaN/Infinity into `GREATEST` without filtering them out first.

### 7.3. ROUND, TRUNC, and TO_CHAR Do Not Restore the Original Number

Functions such as `ROUND`, `TRUNC`, or `TO_CHAR` can help control display values or the number of digits after the decimal point, but they cannot recreate exact decimal data lost when entering a binary type.

For instance, when a `NUMBER` is converted down to `BINARY_FLOAT` and rounded, a subsequent `CAST` back to `NUMBER` has no knowledge of the truncated digits. To preserve original data, store it in an appropriately typed column from the start, or store both raw and transformed values according to query requirements.

### 7.4. Special Values Can Affect Aggregations

When floating-point data contains NaN/Infinity:

- `COUNT(value)` counts non-null values, including NaN and Infinity.
- `MIN`, `MAX`, `SUM`, and `AVG` can yield unexpected results if special values are included in the calculation.
- `ORDER BY` can place NaN at the highest position among non-null values.
- Grouping or joining on floating-point keys can be affected by representation error and Oracle comparison rules.

Best practice is to **define what constitutes a "valid sample"** before computing statistics. Example:

```sql
SELECT COUNT(*) AS valid_sample_count,
       AVG(refined_value) AS average_valid_reading,
       MIN(refined_value) AS minimum_valid_reading,
       MAX(refined_value) AS maximum_valid_reading
FROM   sensor_readings
WHERE  refined_value IS NOT NULL
AND    refined_value IS NOT NAN
AND    refined_value IS NOT INFINITE;
```

If Infinity/NaN genuinely carry business meaning, store and handle them under an explicit policy rather than silently discarding them.

## 8. Table Design and Input Validation

### 8.1. Should NaN and Infinity Be Allowed?

The answer depends on the business domain:

- **Scientific or machine-learning problems** may need to store special results to represent failed calculations, non-convergence, or overflow.
- **Sensors/telemetry** may treat NaN/Infinity as erroneous data to route into an inspection queue with a recorded cause.
- **Currency, inventory, and credit limits** should generally not be stored as floating-point; `NUMBER` and appropriate constraints make more sense.

If special values are permitted, explicitly define the behavior of APIs, SQL reports, batch jobs, and BI tools. Never let a `BINARY_DOUBLE` field accept arbitrary values while the rest of the system assumes its values are always finite.

### 8.2. Example CHECK Constraint Accepting Only Finite Numbers

If a measurement is required to be valid and non-negative:

```sql
CREATE TABLE quality_measurements (
    measurement_id NUMBER(12) PRIMARY KEY,
    measured_value BINARY_DOUBLE NOT NULL,
    CONSTRAINT chk_quality_value
      CHECK (
        measured_value IS NOT NAN
        AND measured_value IS NOT INFINITE
        AND measured_value >= 0d
      )
);
```

This constraint expresses three rules clearly: **not NULL**, **not NaN/Infinity**, and **non-negative**. Using only `CHECK (measured_value >= 0d)` may **fail to block NaN**, because Oracle ranks NaN above all numeric values in comparisons.

If data can be missing, choose `NULL` intentionally, documenting clearly that `NULL` differs from "NaN from arithmetic". SQL `CHECK` constraints also obey three-valued logic; do not assume a CHECK replaces `NOT NULL`.

### 8.3. When to Store a Separate Status Instead of Putting NaN in the Column

Another design stores the measurement and measurement status separately:

```sql
CREATE TABLE sensor_samples (
    sample_id        NUMBER(12) PRIMARY KEY,
    measured_value   BINARY_DOUBLE,
    measure_status   VARCHAR2(20) NOT NULL,
    CONSTRAINT chk_sensor_status
      CHECK (measure_status IN ('OK', 'MISSING', 'INVALID', 'OVERFLOW'))
);
```

Example:

- `OK`: valid finite value.
- `MISSING`: sample not received; `measured_value` may be `NULL`.
- `INVALID`: measurement failed.
- `OVERFLOW`: result exceeded the measurement range.

This design needs cross-column constraints if full consistency must be enforced, but it clarifies business semantics and keeps SQL reports from overloading a single special value with multiple meanings.

## 9. Working with Java/JDBC

### 9.1. Corresponding Types in Java

In Java:

- `float` / `Float` has 32-bit precision matching `BINARY_FLOAT` in representation.
- `double` / `Double` has 64-bit precision matching `BINARY_DOUBLE`.
- `Double.NaN`, `Double.POSITIVE_INFINITY`, and `Double.NEGATIVE_INFINITY` are built-in special values.
- `Double.isNaN(value)` and `Double.isInfinite(value)` check state; Java 8+ provides `Double.isFinite(value)`.

However, **NaN comparison rules in Java differ from Oracle SQL**:

```java
double x = Double.NaN;

System.out.println(x == x);               // false in Java
System.out.println(Double.isNaN(x));       // true
System.out.println(Double.isInfinite(x));  // false
System.out.println(Double.isFinite(x));    // false
```

Consequently, if a Java application filters for NaN using `==` while Oracle filters using SQL `=`, behavior can diverge.

### 9.2. Reading NULL and NaN Separately in ResultSet

When calling `ResultSet.getDouble(...)`, SQL `NULL` is mapped to `0.0` if using the primitive getter; you must call `wasNull()` immediately after that read to distinguish them.

Example:

```java
try (java.sql.PreparedStatement stmt = connection.prepareStatement(
         "SELECT reading_id, refined_value FROM sensor_readings WHERE reading_id = ?")) {
    stmt.setLong(1, 1001L);

    try (java.sql.ResultSet rs = stmt.executeQuery()) {
        if (rs.next()) {
            double value = rs.getDouble("refined_value");
            boolean sqlNull = rs.wasNull();

            if (sqlNull) {
                System.out.println("Missing (SQL NULL)");
            } else if (Double.isNaN(value)) {
                System.out.println("Not a Number");
            } else if (Double.isInfinite(value)) {
                System.out.println("Infinity");
            } else {
                System.out.println("Finite: " + value);
            }
        }
    }
}
```

This snippet illustrates usage inside an application that already has a valid JDBC `connection`. Support for binding/returning special values also depends on the Oracle JDBC driver version and application fetch mechanisms; test on your exact deployment version.

### 9.3. Do Not Use double for Currency Just Because JDBC Supports It

If an Oracle column is `NUMBER(18,2)` and requires exact monetary amounts, the Java application should use an appropriate type such as `BigDecimal` to preserve decimal semantics and control scale/rounding. Converting `NUMBER` to `double` can inject binary floating-point error into accounting calculations.

Conversely, for scientific measurements that are already floating-point, `double` is the natural choice if precision and range are sufficient. Decide based on **data requirements**, not merely whether a type takes fewer bytes.

## 10. SQL Lab: Creating and Querying Special Values

Table creation and data modification operations are intended only for a **practice schema** with appropriate privileges. If you are learning on a PDB, connect to the right PDB and avoid running in production root.

### 10.1. Create the Table

```sql
CREATE TABLE lab_floating_values (
    sample_id    NUMBER(3) PRIMARY KEY,
    sample_label VARCHAR2(30) NOT NULL,
    value_f      BINARY_FLOAT,
    value_d      BINARY_DOUBLE
);
```

### 10.2. Insert Finite Numbers, ±Infinity, NaN, and NULL

```sql
INSERT INTO lab_floating_values
    (sample_id, sample_label, value_f, value_d)
VALUES
    (1, 'finite', 0.1f, 0.1d);

INSERT INTO lab_floating_values
    (sample_id, sample_label, value_f, value_d)
VALUES
    (2, 'positive infinity',
     BINARY_FLOAT_INFINITY, BINARY_DOUBLE_INFINITY);

INSERT INTO lab_floating_values
    (sample_id, sample_label, value_f, value_d)
VALUES
    (3, 'negative infinity',
     -BINARY_FLOAT_INFINITY, -BINARY_DOUBLE_INFINITY);

INSERT INTO lab_floating_values
    (sample_id, sample_label, value_f, value_d)
VALUES
    (4, 'NaN', BINARY_FLOAT_NAN, BINARY_DOUBLE_NAN);

INSERT INTO lab_floating_values
    (sample_id, sample_label, value_f, value_d)
VALUES
    (5, 'SQL NULL', NULL, NULL);

INSERT INTO lab_floating_values
    (sample_id, sample_label, value_f, value_d)
VALUES
    (6, 'zero', 0f, 0d);

COMMIT;
```

Explicitly typing the literals avoids confusing `NUMBER` arithmetic with floating-point arithmetic.

### 10.3. Classify Each Row

```sql
SELECT
    sample_id,
    sample_label,
    CASE
      WHEN value_d IS NULL THEN 'NULL'
      WHEN value_d IS NAN THEN 'NaN'
      WHEN value_d = BINARY_DOUBLE_INFINITY THEN '+Infinity'
      WHEN value_d = -BINARY_DOUBLE_INFINITY THEN '-Infinity'
      ELSE 'FINITE'
    END AS classification
FROM lab_floating_values
ORDER BY sample_id;
```

Expected classification output:

| SAMPLE_ID | SAMPLE_LABEL | CLASSIFICATION |
| ---: | --- | --- |
| 1 | finite | FINITE |
| 2 | positive infinity | +Infinity |
| 3 | negative infinity | -Infinity |
| 4 | NaN | NaN |
| 5 | SQL NULL | NULL |
| 6 | zero | FINITE |

### 10.4. Find NaN and Infinity

```sql
-- NaN rows only.
SELECT sample_id, sample_label
FROM   lab_floating_values
WHERE  value_d IS NAN;

-- Both positive and negative infinity.
SELECT sample_id, sample_label
FROM   lab_floating_values
WHERE  value_d IS INFINITE;

-- Finite numbers only, excluding NULL.
SELECT sample_id, sample_label, value_d
FROM   lab_floating_values
WHERE  value_d IS NOT NULL
AND    value_d IS NOT NAN
AND    value_d IS NOT INFINITE
ORDER BY sample_id;
```

The queries above are expected to return row `4`, rows `2` and `3`, and rows `1` and `6` respectively.

### 10.5. Observe Comparison and Sorting

```sql
SELECT sample_id, sample_label, value_d
FROM   lab_floating_values
ORDER BY value_d ASC NULLS LAST;
```

Under Oracle SQL ordering, the conceptual order is:

```text
-Infinity
0
0.1
+Infinity
NaN
NULL
```

Now consider:

```sql
SELECT sample_id, sample_label
FROM   lab_floating_values
WHERE  value_d > 100d
ORDER  BY sample_id;
```

A surprising result: the query can return **both positive infinity and NaN**, because both are greater than `100` under Oracle comparisons.

If you only want finite measurements greater than `100`:

```sql
SELECT sample_id, sample_label
FROM   lab_floating_values
WHERE  value_d > 100d
AND    value_d IS NOT NAN
AND    value_d IS NOT INFINITE;
```

This practice dataset contains no finite number greater than 100, so the second query returns no rows.

### 10.6. COUNT(*) vs. COUNT on a Column

```sql
SELECT
    COUNT(*)       AS total_rows,
    COUNT(value_d) AS non_null_values,
    COUNT(CASE
            WHEN value_d IS NOT NULL
             AND value_d IS NOT NAN
             AND value_d IS NOT INFINITE
            THEN 1
          END)     AS finite_values
FROM lab_floating_values;
```

With the sample data:

- `TOTAL_ROWS = 6`: all 6 rows.
- `NON_NULL_VALUES = 5`: excludes the SQL `NULL` row, but **still counts NaN and Infinity**.
- `FINITE_VALUES = 2`: only the `finite` and `zero` rows.

This demonstrates that "non-null" does not mean "valid finite number".

### 10.7. Drop the Practice Table When Done

```sql
-- ONLY run on the LAB_FLOATING_VALUES table you created for practice.
DROP TABLE lab_floating_values PURGE;
```

This operation **destroys the table object and its data**; perform it only after confirming the table belongs to your learning schema and contains no data you need to keep.

## 11. Common Issues When Migrating Data or Writing Reports

### 11.1. "I see 0.1, yet equality comparison fails"

Tools may display only a few decimal digits, hiding binary approximation error. Understand whether the source data is `NUMBER` or `BINARY_FLOAT/DOUBLE`, track conversions, and define a tolerance if business rules allow approximate comparison.

Do not fix this by blindly putting `ROUND(value, 2)` in every query; rounding to a fixed number of digits can mask real errors and lose measurement detail.

### 11.2. "ORDER BY DESC puts NaN at the top"

Because Oracle ranks NaN above +Infinity, `ORDER BY value DESC` can put NaN first. If the business wants the largest finite value, filter `IS NOT NAN` and `IS NOT INFINITE` before sorting.

### 11.3. "The column is NOT NULL, yet the data is still not a number"

`NOT NULL` only prevents SQL `NULL`. It does not block NaN/Infinity in a floating-point column. Add finite checks in queries or an appropriate `CHECK` constraint.

### 11.4. "Java says NaN != NaN, while Oracle SQL says NaN = NaN"

Both can be right in their own contexts: Java semantics for `double` follow standard IEEE 754 comparison rules, which differ from the SQL ordering and comparison rules Oracle uses for NaN. On the application layer use `Double.isNaN`; in Oracle SQL use `IS NAN` when detecting that state.

### 11.5. "Numbers from NUMBER get rounded when converted to double"

If a `NUMBER` has many significant digits or exceeds double's resolution, type conversion loses precision. For decimal numbers requiring exactness, keep using `NUMBER`/`BigDecimal` and avoid unnecessary conversions through `double`.

### 11.6. "BINARY_FLOAT is faster than NUMBER so we should always switch"

Do not decide based solely on speed assumptions. Native floating-point can fit numeric-heavy workloads, yet performance depends on queries, hardware, data volume, indexes, data access patterns, and conversions. If changing the type sacrifices required precision or violates business rules, potential gains do not offset the cost of corrupted data.

### 11.7. "Using BINARY_DOUBLE means we don't need overflow checks"

`BINARY_DOUBLE` has a huge range, but it is still finite. Overflow can still produce Infinity; indeterminate operations can still produce NaN. Maintain detection workflows for special values even in double-based pipelines.

## 12. Operational Troubleshooting Checklist

When floating-point data looks suspicious, you can run these read-only checks:

1. **Verify column types**:

   ```sql
   SELECT table_name, column_name, data_type
   FROM   user_tab_columns
   WHERE  table_name = 'SENSOR_READINGS'
   ORDER  BY column_id;
   ```

2. **Count NaN/Infinity/NULL separately**:

   ```sql
   SELECT
       COUNT(*) AS total_count,
       COUNT(CASE WHEN refined_value IS NULL THEN 1 END) AS null_count,
       COUNT(CASE WHEN refined_value IS NAN THEN 1 END) AS nan_count,
       COUNT(CASE WHEN refined_value IS INFINITE THEN 1 END) AS infinity_count
   FROM sensor_readings;
   ```

3. **Check filtering/sorting logic**: determine whether `WHERE value > threshold` accidentally picks up NaN; check `ORDER BY` and aggregations.
4. **Inspect type conversions**: `NUMBER → BINARY_FLOAT → BINARY_DOUBLE` can lose precision right at the first step.
5. **Cross-check the application**: verify whether Java/JDBC uses `isNaN`, `isInfinite`, and `wasNull` properly.
6. **Confirm data policy**: should NaN/Infinity be discarded, stored separately, alerted on, or mapped to an explainable business status?

When anomalous rows are detected, do not delete them or convert them to `NULL` in bulk before understanding why the special values appeared. They can be key evidence of measurement faults, division errors, overflow, or upstream source issues.

## 13. Self-Check Questions

### Question 1: Data Types

A system needs to store monetary amounts with two digits after the decimal point and requires exact totals when summing many transactions. Should it choose `NUMBER(18,2)` or `BINARY_DOUBLE`? Why?

**Hint:** Typically choose `NUMBER(18,2)` because decimal arithmetic and scale apply directly to currency; `BINARY_DOUBLE` is approximate binary floating-point.

### Question 2: Range

Between `BINARY_FLOAT` and `BINARY_DOUBLE`, which has greater precision and value range? Can both store NaN?

**Hint:** `BINARY_DOUBLE` is higher in both characteristics; both support NaN/Infinity.

### Question 3: Comparing NaN

In Oracle SQL, does `BINARY_DOUBLE_NAN = BINARY_DOUBLE_NAN` evaluate to TRUE? Is this comparison the same as `Double.NaN == Double.NaN` in Java?

**Hint:** Oracle SQL returns TRUE; in Java, `==` with NaN returns false.

### Question 4: Large-Value Filter

A `BINARY_DOUBLE` column `READING` contains 50, 200, NaN, and +Infinity. Which rows can `WHERE reading > 100d` return?

**Hint:** 200, +Infinity, and NaN under Oracle's comparison rules. To retrieve only finite numbers greater than 100, add `IS NOT NAN` and `IS NOT INFINITE`, plus `NULL` handling as needed.

### Question 5: NULL

Does `COUNT(reading)` ignore NaN? If a measurement was never collected, how should it be understood differently from NaN?

**Hint:** `COUNT(column)` only excludes `NULL` values; it does not automatically exclude NaN. `NULL` usually means no value; NaN is a special floating-point value produced by an arithmetic operation/state.

### Question 6: Numeric Precedence

Adding a `NUMBER` and a `BINARY_DOUBLE` is normally evaluated under which type? What is the risk?

**Hint:** `BINARY_DOUBLE` has higher precedence, which can cause the `NUMBER` value to be converted and rounded.

### Question 7: CHECK Constraint

Is `CHECK (reading >= 0d)` enough to guarantee every row stores a **finite** non-negative number?

**Hint:** Not yet, because NaN compares greater than every number; you must block `IS NAN` and `IS INFINITE`, and decide whether `NULL` is allowed.

### Question 8: Java JDBC

After `double reading = rs.getDouble("reading")`, the returned value is 0.0. How do you tell whether the database actually stored 0 or SQL `NULL`?

**Hint:** Call `rs.wasNull()` immediately after reading the column with a primitive getter.

### Question 9: Arithmetic

Why might converting `NUMBER → BINARY_FLOAT → BINARY_DOUBLE` fail to recover the original NUMBER value?

**Hint:** `BINARY_FLOAT` already rounded the value; `BINARY_DOUBLE` only represents the rounded result more precisely without reconstructing the previously lost data.

### Question 10: Quality Monitoring

Write a query returning `COUNT(*)` of rows in `SENSOR_READINGS` where `REFINED_VALUE` is a non-null finite number.

**Hint:**

```sql
SELECT COUNT(*) AS finite_count
FROM   sensor_readings
WHERE  refined_value IS NOT NULL
AND    refined_value IS NOT NAN
AND    refined_value IS NOT INFINITE;
```

## 14. Official Oracle Documentation

- [Oracle Database SQL Language Reference — Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html): `NUMBER`, `BINARY_FLOAT`, `BINARY_DOUBLE`, range, precision, and numeric precedence.
- [Oracle Database SQL Language Reference — Literals](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Literals.html): `f`/`d` suffixes and `BINARY_*_NAN`, `BINARY_*_INFINITY` constants.
- [Oracle Database SQL Language Reference — Floating-Point Conditions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Floating-Point-Conditions.html): `IS NAN`, `IS NOT NAN`, `IS INFINITE`, and `IS NOT INFINITE` conditions.
- [Oracle Database SQL Language Reference — Data Type Comparison Rules](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Type-Comparison-Rules.html): comparison ordering and Oracle rules for NaN.
- [Oracle Database Development Guide — Using SQL Data Types in Database Applications](https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/sql-data-types.html): IEEE 754, subnormals, special values, rounding, and comparison.
- [Oracle Database SQL Language Reference — TO_BINARY_FLOAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_BINARY_FLOAT.html): converting to the 32-bit type.
- [Oracle Database SQL Language Reference — TO_BINARY_DOUBLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_BINARY_DOUBLE.html): converting to the 64-bit type.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): working with numeric data via JDBC.

When using `BINARY_FLOAT` and `BINARY_DOUBLE`, remember four principles: **these are approximate binary numbers**, **data types determine precision and conversions**, **NaN/Infinity are real values rather than NULL**, and **Oracle SQL has its own NaN comparison rules**. Choose data types based on business requirements and build checks for special values from schema design through SQL processing to the Java/JDBC layer.
