# Numeric, String, Date/Time, and BOOLEAN Data Types in PL/SQL

PL/SQL is the procedural language of Oracle Database. A PL/SQL program declares variables, constants, parameters, and records using a data type system closely tied to SQL data types. Choosing the right type ensures accurate calculations, avoids implicit conversions, controls NULLs, and makes programs easier to maintain.

The four groups you need to master in basic PL/SQL are:

- **Numeric types:** NUMBER, PLS_INTEGER, BINARY_FLOAT, and BINARY_DOUBLE.
- **String types:** CHAR, VARCHAR2, NCHAR, NVARCHAR2, and LOB types.
- **Date/time types:** DATE, TIMESTAMP, time-zone types, and INTERVAL.
- **BOOLEAN:** the three-valued logic type TRUE, FALSE, and NULL in PL/SQL.

One key distinction to make is between the data type of a PL/SQL variable and the data type of a SQL column. For example, in Oracle Database 19c, PL/SQL has BOOLEAN, but SQL tables do not have a BOOLEAN column; support for the BOOLEAN type in SQL was added in Oracle Database 23c. This lesson highlights these differences and uses syntax broadly compatible with Oracle 19c, except where noted otherwise.

## 1. Declaring Variables and Data Types in PL/SQL

Variables are declared in the DECLARE section of a block, procedure, function, or package:

~~~sql
DECLARE
    l_count       PLS_INTEGER := 0;
    l_amount      NUMBER(14,2) := 125000.50;
    l_customer    VARCHAR2(100 CHAR);
    l_created_at  TIMESTAMP WITH TIME ZONE := SYSTIMESTAMP;
    l_is_active   BOOLEAN := TRUE;
BEGIN
    l_count := l_count + 1;
    DBMS_OUTPUT.PUT_LINE('Count = ' || l_count);
END;
/
~~~

A variable declaration typically has the form:

~~~sql
variable_name data_type [NOT NULL] [:= initial_value];
~~~

Points to remember:

- A PL/SQL variable that is not assigned a default value starts with a value of NULL.
- NOT NULL forces the variable to always have a non-NULL value; the variable must have an initial value.
- The := operator is used to assign values in PL/SQL.
- CONSTANT declares a constant and requires initialization.
- A variable is scoped only to the block or subprogram where it is declared, unless declared at package scope.

Example:

~~~sql
DECLARE
    c_tax_rate CONSTANT NUMBER(5,4) := 0.0850;
    l_net      NUMBER(14,2) := 100000;
    l_tax      NUMBER(14,2);
BEGIN
    l_tax := l_net * c_tax_rate;
    DBMS_OUTPUT.PUT_LINE('Tax = ' || TO_CHAR(l_tax, 'FM9999990D00'));
END;
/
~~~

## 2. Numeric Data Types

### 2.1 NUMBER

NUMBER is Oracle's general-purpose decimal numeric type. It is suitable for currency, quantities, rates, and calculations requiring decimal accuracy.

Common declaration forms:

~~~sql
DECLARE
    l_value       NUMBER;
    l_amount      NUMBER(12,2);
    l_percentage  NUMBER(7,4);
    l_whole       NUMBER(8,0);
BEGIN
    NULL;
END;
/
~~~

Meaning:

- NUMBER: no specific precision/scale declared; Oracle stores numeric values within the supported range.
- NUMBER(p): limits the number of significant digits to precision p, with scale defaulting to 0.
- NUMBER(p,s): p is precision, s is scale.

The precision of NUMBER can range from 1 to 38 digits. Scale specifies the number of digits to the right of the decimal point when positive; negative scale rounds to the left of the decimal point. Scale has a wider range than precision, so choose it according to business requirements.

Example:

~~~sql
DECLARE
    l_price    NUMBER(10,2) := 1234.567;
    l_quantity NUMBER(8,0) := 12;
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_price);
    DBMS_OUTPUT.PUT_LINE(l_quantity);
END;
/
~~~

When assigning a value with more decimal digits into NUMBER(10,2), Oracle rounds according to the variable's scale. If the number of digits to store exceeds the allowed precision, the assignment can raise a value/precision error such as VALUE_ERROR in PL/SQL.

Do not rely on automatic rounding by a column or variable as a substitute for currency rules. If business logic specifies a particular rounding rule, use ROUND with an explicit scale at the exact calculation step:

~~~sql
l_total := ROUND(l_unit_price * l_quantity, 2);
~~~

### 2.2 Precision and Scale

For NUMBER(7,2):

- At most 7 significant digits in total.
- Two digits are reserved for the fractional part.
- The integer part has at most 5 digits.

Examples of values representable within the limit:

| Value | Meaning |
|---:|---|
| 12345.67 | 5 integer digits and 2 fractional digits |
| 0.25 | Value less than 1 |
| -99999.99 | Negative boundary for the declared width |

A value such as 123456.78 exceeds the precision limit of NUMBER(7,2). A value with more than two fractional digits is rounded to the scale when stored/assigned; after rounding, if the integer part still exceeds the limit, an error is raised.

### 2.3 INTEGER, SMALLINT, DECIMAL, and NUMERIC

Oracle provides familiar numeric type names compatible with SQL syntax:

- INTEGER and SMALLINT are subtypes of NUMBER with a scale of 0.
- DECIMAL and NUMERIC are subtype names of NUMBER that can declare precision/scale.
- REAL and DOUBLE PRECISION in an Oracle SQL context are numeric type names mapped according to Oracle rules; they should not be confused with BINARY_FLOAT/BINARY_DOUBLE.

For PL/SQL variables, you can use NUMBER(p,0) or PLS_INTEGER depending on the value range and requirements. For table columns, check the data type defined in the DDL rather than guessing from standard SQL type names.

### 2.4 PLS_INTEGER and BINARY_INTEGER

PLS_INTEGER is a 32-bit signed integer type with the value range:

~~~text
-2,147,483,648 to 2,147,483,647
~~~

It is commonly suitable for:

- Loop counters.
- Collection indices.
- Retry counts.
- Small integer calculations within PL/SQL logic.

Example:

~~~sql
DECLARE
    l_counter PLS_INTEGER := 0;
BEGIN
    FOR i IN 1 .. 5 LOOP
        l_counter := l_counter + 1;
    END LOOP;

    DBMS_OUTPUT.PUT_LINE(l_counter);
END;
/
~~~

BINARY_INTEGER is a legacy type name that is essentially equivalent to PLS_INTEGER in modern PL/SQL. New code typically uses PLS_INTEGER to express intent clearly.

If a PLS_INTEGER calculation exceeds its representable range, NUMERIC_OVERFLOW/VALUE_ERROR may be raised. Do not use PLS_INTEGER for large monetary totals or integers that could exceed 32 bits.

### 2.5 SIMPLE_INTEGER

SIMPLE_INTEGER is a subtype of PLS_INTEGER with a NOT NULL constraint. It is designed for integer calculations in PL/SQL where high performance is needed and the value is always non-NULL.

~~~sql
DECLARE
    l_counter SIMPLE_INTEGER := 0;
BEGIN
    l_counter := l_counter + 1;
END;
/
~~~

Only use SIMPLE_INTEGER when the value range, NULL rules, and arithmetic behavior are clearly understood. Its performance optimization depends on how PL/SQL is compiled and the execution environment; do not mechanically replace PLS_INTEGER with SIMPLE_INTEGER.

### 2.6 Built-in Integer Subtypes

PL/SQL provides several subtypes based on PLS_INTEGER:

| Subtype | Value Range / Characteristics |
|---|---|
| NATURAL | Integers from 0 upward within the PLS_INTEGER range |
| NATURALN | Like NATURAL and disallows NULL |
| POSITIVE | Positive integers within the PLS_INTEGER range |
| POSITIVEN | Like POSITIVE and disallows NULL |
| SIGNTYPE | Only accepts -1, 0, or 1 |
| SIMPLE_INTEGER | PLS_INTEGER with a NOT NULL constraint |

These subtypes help express data semantics, but they do not replace business validation. For example, POSITIVE does not by itself prove that an inventory quantity is valid under application rules.

### 2.7 BINARY_FLOAT and BINARY_DOUBLE

These are binary floating-point types following the IEEE standard:

- BINARY_FLOAT: single precision, 32-bit.
- BINARY_DOUBLE: double precision, 64-bit.

They are suited for scientific calculations, measurements, or approximate data where floating-point performance matters.

~~~sql
DECLARE
    l_measure  BINARY_FLOAT := 12.5;
    l_distance BINARY_DOUBLE := 123456.789;
BEGIN
    l_measure := l_measure * 1.1;
    l_distance := l_distance / 3;
END;
/
~~~

Decimal numbers like 0.1 may not be represented exactly in finite binary form. Therefore, floating-point calculation results can have small rounding errors.

For currency or figures requiring exact decimal reconciliation, prefer NUMBER over BINARY_FLOAT/BINARY_DOUBLE.

### 2.8 Choosing NUMBER or PLS_INTEGER?

| Requirement | Usually Suitable Type |
|---|---|
| Monetary amounts, taxes, decimal rates | NUMBER(p,s) |
| Large row counts or wide-range integers | NUMBER(p,0) |
| Counters, collection indices within 32-bit range | PLS_INTEGER |
| Approximate measurement calculations | BINARY_FLOAT or BINARY_DOUBLE |
| Always non-NULL values and controlled integer optimization | Consider SIMPLE_INTEGER |

Do not choose a type just because its name is shorter. Consider the value range, precision, operations, and how the data is stored in SQL.

## 3. String Data Types

### 3.1 CHAR and VARCHAR2

CHAR is a fixed-length character type. Values shorter than the declared length are padded with trailing spaces.

VARCHAR2 is a variable-length character type. It stores only the actual data plus internal overhead.

Variable declaration example:

~~~sql
DECLARE
    l_country_code CHAR(2) := 'VN';
    l_customer_name VARCHAR2(100 CHAR) := 'Nguyen An';
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_country_code);
    DBMS_OUTPUT.PUT_LINE(l_customer_name);
END;
/
~~~

CHAR is generally suitable for fixed-length codes, such as 2-character country codes. VARCHAR2 is suitable for names, addresses, descriptions, or variable-length values.

Avoid using CHAR for variable-length strings if trailing-space padding causes issues in comparisons or display.

### 3.2 BYTE and CHAR Length Semantics

A VARCHAR2 declaration can specify length in bytes or in characters:

~~~sql
VARCHAR2(100 BYTE)
VARCHAR2(100 CHAR)
~~~

- BYTE limits the number of stored bytes.
- CHAR limits the number of characters according to Oracle semantics.

In a multibyte character set such as AL32UTF8, a single character can take multiple bytes. Thus, VARCHAR2(100 BYTE) will not necessarily hold 100 Vietnamese or Unicode characters.

In PL/SQL, CHAR/VARCHAR2 variables have a maximum limit of 32,767 bytes. SQL types in tables have their own limits depending on the MAX_STRING_SIZE configuration and version; do not infer SQL column limits from PL/SQL variable limits.

To avoid ambiguity, declare CHAR/BYTE explicitly when application requirements depend on length. Commonly used functions:

~~~sql
LENGTH(value)   -- Length in characters
LENGTHB(value)  -- Length in bytes
~~~

Example:

~~~sql
DECLARE
    l_text VARCHAR2(20 CHAR) := 'Việt Nam';
BEGIN
    DBMS_OUTPUT.PUT_LINE('Characters=' || LENGTH(l_text));
    DBMS_OUTPUT.PUT_LINE('Bytes=' || LENGTHB(l_text));
END;
/
~~~

The byte count depends on the database character set; do not assume a fixed result across all environments.

### 3.3 NCHAR and NVARCHAR2

NCHAR and NVARCHAR2 use the national character set:

- NCHAR: fixed length.
- NVARCHAR2: variable length.

They may be necessary in systems with specific national character set requirements. In many modern systems that use AL32UTF8 as the database character set, VARCHAR2 already supports full Unicode; you do not need to choose NVARCHAR2 just because strings contain Vietnamese diacritics.

When mixing VARCHAR2 with NVARCHAR2 or CHAR with NCHAR, Oracle may have to perform character set conversion. Keep data types consistent across your schema and bind variables.

### 3.4 CLOB and NCLOB

CLOB stores large amounts of text; NCLOB stores large text in the national character set. They are suitable for long content such as documents, article bodies, or text payloads.

Column example:

~~~sql
CREATE TABLE documents (
    document_id NUMBER PRIMARY KEY,
    title       VARCHAR2(300 CHAR),
    body        CLOB
);
~~~

In PL/SQL, a CLOB variable can hold much larger content than VARCHAR2. Concatenating, slicing, reading, and writing LOBs have APIs such as DBMS_LOB; do not assume every short-string operation applies directly to LOBs without limits.

### 3.5 Empty Strings and NULL in Oracle

In current Oracle versions, a zero-length character string such as a literal with two single quotes is treated as NULL for CHAR/VARCHAR2. This is an important difference compared to some other database management systems.

Example:

~~~sql
DECLARE
    l_text VARCHAR2(10) := '';
BEGIN
    IF l_text IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Value is NULL');
    END IF;
END;
/
~~~

A string containing only spaces, such as three space characters, is not NULL. It is a string containing space characters.

Consequences:

- You cannot normally use an empty string to distinguish an "empty string" state from "no value" in VARCHAR2.
- LENGTH of an empty string returns NULL.
- Comparing a column to an empty string is not a way to find an independent empty value; in Oracle it is equivalent to comparing with NULL and does not return TRUE.
- Use IS NULL to check for NULL.

Oracle has maintained this rule for a long time, but Oracle documentation notes that applications should not rely on empty strings always being identical to NULL in all future releases.

### 3.6 Strings with Quotes and q-quoting

String literals are normally enclosed in single quotes. To include a single quote, write two single quotes:

~~~sql
DECLARE
    l_message VARCHAR2(100) := 'User''s account is active';
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_message);
END;
/
~~~

For content with many quotes, PL/SQL supports alternative quoting:

~~~sql
DECLARE
    l_message VARCHAR2(200) := q'[It is Oracle PL/SQL]';
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_message);
END;
/
~~~

The opening and closing delimiters in q-quoting can be chosen to suit the content, helping avoid having to escape many single quotes.

## 4. Date and Time Data Types

### 4.1 DATE

DATE stores year, month, day, hour, minute, and second. Oracle's DATE does not store only a calendar date; it includes a time component down to the second, though it does not store fractional seconds or a time zone.

Example:

~~~sql
DECLARE
    l_created_at DATE := DATE '2026-11-14';
BEGIN
    DBMS_OUTPUT.PUT_LINE(TO_CHAR(
        l_created_at,
        'YYYY-MM-DD HH24:MI:SS'
    ));
END;
/
~~~

The date literal DATE '2026-11-14' defaults to a time of 00:00:00. If you need a specific time of day, use TO_DATE with a format mask:

~~~sql
DECLARE
    l_meeting_at DATE;
BEGIN
    l_meeting_at := TO_DATE(
        '14-11-2026 09:30:00',
        'DD-MM-YYYY HH24:MI:SS'
    );
END;
/
~~~

### 4.2 TIMESTAMP

TIMESTAMP extends DATE with fractional seconds. Fractional seconds precision can be declared from 0 to 9 digits; the default is typically 6.

~~~sql
DECLARE
    l_event_time TIMESTAMP(6);
BEGIN
    l_event_time := TIMESTAMP '2026-11-14 09:30:15.123456';
END;
/
~~~

TIMESTAMP is suitable when sub-second time precision is needed. It still does not contain a time zone on its own unless you use a time-zone variant.

### 4.3 TIMESTAMP WITH TIME ZONE

TIMESTAMP WITH TIME ZONE stores a point in time along with time zone/offset information. Example:

~~~sql
DECLARE
    l_event_time TIMESTAMP WITH TIME ZONE;
BEGIN
    l_event_time := TO_TIMESTAMP_TZ(
        '2026-11-14 09:30:15 Asia/Ho_Chi_Minh',
        'YYYY-MM-DD HH24:MI:SS TZR'
    );
END;
/
~~~

You can use an offset like +07:00 or a region name like Asia/Ho_Chi_Minh. Use region names when daylight saving time rules and time zone history matter.

### 4.4 TIMESTAMP WITH LOCAL TIME ZONE

TIMESTAMP WITH LOCAL TIME ZONE is normalized to the database time zone when stored and displayed in the session time zone when read. This type does not preserve the client's original time zone as part of the returned value.

It is useful when the application wants to store normalized instants while displaying them in the session's time zone. The database time zone and session time zone must be configured deliberately.

### 4.5 Comparing Date/Time Types

| Type | Has Time Component? | Fractional Seconds? | Has Time Zone? |
|---|---|---|---|
| DATE | Yes, to the second | No | No |
| TIMESTAMP | Yes | Yes | No |
| TIMESTAMP WITH TIME ZONE | Yes | Yes | Has offset/region |
| TIMESTAMP WITH LOCAL TIME ZONE | Yes | Yes | Normalized on store, displayed per session |

Choose the type based on data semantics:

- Business dates without time zone needs: DATE may suffice.
- Instants requiring high precision: TIMESTAMP.
- Instants originating from multiple time zones: TIMESTAMP WITH TIME ZONE.
- Instants stored normalized and displayed per session time zone: consider TIMESTAMP WITH LOCAL TIME ZONE.

### 4.6 SYSDATE, SYSTIMESTAMP, CURRENT_DATE, and CURRENT_TIMESTAMP

Common time functions:

| Function | Return Type | Semantics |
|---|---|---|
| SYSDATE | DATE | Date and time from the database server's OS clock |
| SYSTIMESTAMP | TIMESTAMP WITH TIME ZONE | Timestamp from the database server's system clock, with time zone/offset |
| CURRENT_DATE | DATE | Current date and time in the session time zone |
| CURRENT_TIMESTAMP | TIMESTAMP WITH TIME ZONE | Current timestamp in the session time zone |
| LOCALTIMESTAMP | TIMESTAMP | Current timestamp in the session time zone without retaining time zone in the result |

Do not substitute these functions for one another if the application depends on time zones. A session in a different time zone can receive different CURRENT_DATE/CURRENT_TIMESTAMP values compared to SYSDATE/SYSTIMESTAMP.

### 4.7 DATE Arithmetic

With DATE, adding or subtracting a NUMBER is interpreted as a number of days:

~~~sql
DECLARE
    l_start DATE := DATE '2026-11-14';
    l_next  DATE;
BEGIN
    l_next := l_start + 1;
    DBMS_OUTPUT.PUT_LINE(TO_CHAR(l_next, 'YYYY-MM-DD'));
END;
/
~~~

Examples:

- date_value + 1: adds one day.
- date_value + 1/24: adds one hour.
- date_value - 7: goes back seven days.
- date_value_2 - date_value_1: returns the number of days as a NUMBER, which may include a fractional part.

For time-zone-aware data and local calendar requirements, do not assume "one calendar day" always equals exactly 24 hours across all DST transitions. Determine whether business logic needs an absolute duration or a calendar day in a specific region.

### 4.8 INTERVAL YEAR TO MONTH

INTERVAL YEAR TO MONTH represents a duration in years and months:

~~~sql
DECLARE
    l_contract_period INTERVAL YEAR TO MONTH;
BEGIN
    l_contract_period := INTERVAL '2-6' YEAR TO MONTH;
END;
/
~~~

The example value represents 2 years and 6 months. Use it for contract terms, periods, or calendar calculations by months/years.

### 4.9 INTERVAL DAY TO SECOND

INTERVAL DAY TO SECOND represents days, hours, minutes, seconds, and fractional seconds:

~~~sql
DECLARE
    l_timeout INTERVAL DAY TO SECOND;
BEGIN
    l_timeout := INTERVAL '0 00:05:30' DAY TO SECOND;
END;
/
~~~

The value above represents 5 minutes and 30 seconds. This type is suitable for durations, timeouts, processing times, and the difference between two timestamps.

### 4.10 DATE and TIMESTAMP Subtraction

Subtracting two DATE values:

~~~sql
SELECT DATE '2026-11-14' - DATE '2026-11-10' AS days_between
FROM dual;
~~~

returns a number of days.

Subtracting two TIMESTAMP values:

~~~sql
SELECT TIMESTAMP '2026-11-14 10:00:00'
     - TIMESTAMP '2026-11-14 09:30:00' AS elapsed_time
FROM dual;
~~~

returns an INTERVAL DAY TO SECOND.

### 4.11 NUMTOYMINTERVAL and NUMTODSINTERVAL

These two functions convert numbers to intervals:

~~~sql
SELECT NUMTOYMINTERVAL(3, 'MONTH') AS three_months,
       NUMTODSINTERVAL(90, 'MINUTE') AS ninety_minutes
FROM dual;
~~~

They are useful when representing dynamic durations in SQL/PLSQL. Clearly define the business unit, especially when calculating due dates by months, month-ends, or calendar days.

## 5. Date/Time Conversion and Formatting

### 5.1 Using Standard Literals

DATE literal:

~~~sql
DATE '2026-11-14'
~~~

TIMESTAMP literal:

~~~sql
TIMESTAMP '2026-11-14 09:30:15.123456'
~~~

Standard literals avoid dependency on NLS_DATE_FORMAT or session language date formatting.

### 5.2 TO_DATE

Converts a string to a DATE:

~~~sql
DECLARE
    l_date DATE;
BEGIN
    l_date := TO_DATE('14/11/2026', 'DD/MM/YYYY');
END;
/
~~~

Always specify the format mask explicitly when converting strings to dates. If you omit the format mask, the result depends on the session's NLS_DATE_FORMAT.

### 5.3 TO_TIMESTAMP and TO_TIMESTAMP_TZ

~~~sql
DECLARE
    l_ts    TIMESTAMP(6);
    l_ts_tz TIMESTAMP WITH TIME ZONE;
BEGIN
    l_ts := TO_TIMESTAMP(
        '2026-11-14 09:30:15.123456',
        'YYYY-MM-DD HH24:MI:SS.FF6'
    );

    l_ts_tz := TO_TIMESTAMP_TZ(
        '2026-11-14 09:30:15 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    );
END;
/
~~~

The format mask must match the input data. FF represents fractional seconds; TZH:TZM represents hour/minute offset; TZR uses a time zone region.

### 5.4 TO_CHAR

Converts a date/time to a display string:

~~~sql
SELECT TO_CHAR(
           SYSTIMESTAMP,
           'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM'
       ) AS formatted_time
FROM dual;
~~~

Output formatting is only for presentation. Do not store dates/times as VARCHAR2 just to preserve a display format; store them as DATE/TIMESTAMP so they can be properly compared, calculated, and indexed.

### 5.5 Avoiding Implicit Conversion

Avoid writing:

~~~sql
WHERE order_date = '14/11/2026'
~~~

because Oracle must convert the string to a date according to NLS settings. Instead, use:

~~~sql
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
~~~

or bind a properly typed DATE variable from the application.

Do not call TO_DATE on a column that is already a DATE. TO_DATE takes a string and returns a DATE. When passing a DATE to TO_DATE, Oracle may first have to implicitly convert the DATE to a string depending on NLS, which is both unnecessary and can corrupt data or affect index access.

### 5.6 NLS and Display Language

Month names, day names, and numeric separators can depend on NLS settings. If consistent formatting is required:

- Specify the format mask explicitly.
- Specify NLS_DATE_LANGUAGE when the format contains month/day names.
- Specify NLS_NUMERIC_CHARACTERS when converting numbers to/from strings.
- Use properly typed bind variables instead of concatenating SQL strings.

Example:

~~~sql
SELECT TO_DATE(
           '14-NOV-2026',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=ENGLISH'
       )
FROM dual;
~~~

## 6. The BOOLEAN Type in PL/SQL

BOOLEAN is a logical type used in PL/SQL. It has three states:

- TRUE.
- FALSE.
- NULL (undetermined/unknown).

Example:

~~~sql
DECLARE
    l_is_valid BOOLEAN := TRUE;
    l_is_paid  BOOLEAN := FALSE;
    l_is_ready BOOLEAN;
BEGIN
    IF l_is_valid THEN
        DBMS_OUTPUT.PUT_LINE('Valid');
    END IF;

    IF l_is_paid = FALSE THEN
        DBMS_OUTPUT.PUT_LINE('Not paid');
    END IF;

    IF l_is_ready IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Ready state is unknown');
    END IF;
END;
/
~~~

An uninitialized BOOLEAN variable has the value NULL, not FALSE.

### 6.1 BOOLEAN vs. NUMBER(1) or CHAR(1)

Some systems use NUMBER(1) or CHAR(1) to represent flags:

| Type | Commonly Used Values |
|---|---|
| BOOLEAN in PL/SQL | TRUE, FALSE, NULL |
| NUMBER(1) | 1, 0, NULL |
| CHAR(1) | 'Y', 'N', NULL |

BOOLEAN directly expresses logical intent in code. NUMBER(1)/CHAR(1) is a way to model flags in SQL columns in versions without SQL BOOLEAN support or when a schema follows its own convention.

Do not assume every non-zero NUMBER value means TRUE if the application only allows 0 and 1. Use a CHECK constraint to enforce the valid value domain:

~~~sql
CREATE TABLE feature_flags (
    flag_name VARCHAR2(100) PRIMARY KEY,
    is_enabled NUMBER(1) NOT NULL,
    CONSTRAINT ck_feature_flag_enabled
        CHECK (is_enabled IN (0, 1))
);
~~~

### 6.2 TRUE, FALSE, and NULL in IF Conditions

In PL/SQL, an IF branch executes only when the expression evaluates to TRUE. If the expression is FALSE or NULL, the THEN branch does not execute.

~~~sql
DECLARE
    l_approved BOOLEAN;
BEGIN
    IF l_approved THEN
        DBMS_OUTPUT.PUT_LINE('Approved');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not approved or unknown');
    END IF;
END;
/
~~~

Because l_approved is NULL, the program executes the ELSE branch. If you need to distinguish FALSE from NULL, check for NULL separately:

~~~sql
IF l_approved IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('Not decided');
ELSIF l_approved THEN
    DBMS_OUTPUT.PUT_LINE('Approved');
ELSE
    DBMS_OUTPUT.PUT_LINE('Rejected');
END IF;
~~~

### 6.3 Three-Valued Logic

BOOLEAN in PL/SQL follows three-valued logic. Some results:

| A | B | A AND B | A OR B |
|---|---|---|---|
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | NULL | NULL | TRUE |
| FALSE | NULL | FALSE | NULL |
| NULL | NULL | NULL | NULL |

The NOT operation:

| A | NOT A |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |
| NULL | NULL |

Example:

~~~sql
DECLARE
    l_has_stock BOOLEAN := NULL;
BEGIN
    IF NOT l_has_stock THEN
        DBMS_OUTPUT.PUT_LINE('No stock');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Stock exists or state is unknown');
    END IF;
END;
/
~~~

NOT NULL is still NULL. Therefore, the condition IF NOT l_has_stock does not execute when the variable is NULL. If business logic must distinguish out-of-stock from unknown stock, handle the NULL state separately.

### 6.4 BOOLEAN and Comparison Operators

Comparing against NULL with equals or not-equals does not produce TRUE/FALSE as expected:

~~~sql
-- Do not use to check for NULL:
IF l_flag = NULL THEN
    NULL;
END IF;
~~~

You must use:

~~~sql
IF l_flag IS NULL THEN
    NULL;
END IF;
~~~

Similarly for numeric/string/date expressions, use IS NULL or IS NOT NULL instead of = NULL.

### 6.5 BOOLEAN in SQL Before and From Oracle Database 23c

In Oracle Database 19c:

- BOOLEAN is a PL/SQL type.
- A BOOLEAN column cannot be declared in a SQL table.
- A BOOLEAN variable cannot be used like a regular SQL column.
- A function returning BOOLEAN cannot be called directly from a SQL statement in the same way as a function returning a regular SQL type.

Starting in Oracle Database 23c, SQL has the BOOLEAN data type, which can be used in SQL tables, expressions, and PL/SQL with version support.

If an application must be compatible with Oracle 19c, use a storage convention such as NUMBER(1) or CHAR(1) and convert to BOOLEAN in the PL/SQL layer. If deploying on 23c or later, check drivers, tools, and compatibility settings before changing schemas/APIs.

### 6.6 Example of Converting a SQL Flag to BOOLEAN in PL/SQL

For a schema using NUMBER(1):

~~~sql
DECLARE
    l_flag_value NUMBER(1);
    l_is_enabled BOOLEAN;
BEGIN
    SELECT is_enabled
    INTO l_flag_value
    FROM feature_flags
    WHERE flag_name = 'NEW_CHECKOUT';

    l_is_enabled := (l_flag_value = 1);

    IF l_is_enabled THEN
        DBMS_OUTPUT.PUT_LINE('Feature enabled');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Feature disabled');
    END IF;
END;
/
~~~

The example assumes IS_ENABLED is NOT NULL and only contains 0/1. If the column allows NULL, the comparison l_flag_value = 1 can produce a BOOLEAN NULL; the application must decide what NULL means.

## 7. Converting Between Data Types

Oracle can perform implicit conversion, but clear code should use explicit conversion when data types differ.

### 7.1 Converting Numbers

~~~sql
DECLARE
    l_text   VARCHAR2(30) := '12345.67';
    l_amount NUMBER(12,2);
BEGIN
    l_amount := TO_NUMBER(
        l_text,
        '999999999D99',
        'NLS_NUMERIC_CHARACTERS=''.,'''
    );
END;
/
~~~

TO_NUMBER converts a string to a number. The format mask and NLS_NUMERIC_CHARACTERS explicitly define the decimal point/grouping separators instead of relying on session settings.

### 7.2 Converting Numbers to Strings

~~~sql
DECLARE
    l_amount NUMBER(12,2) := 12345.6;
    l_text   VARCHAR2(40);
BEGIN
    l_text := TO_CHAR(
        l_amount,
        'FM999G999G990D00',
        'NLS_NUMERIC_CHARACTERS='',.'''
    );
END;
/
~~~

TO_CHAR is for display. Do not store formatted strings and reuse them as numeric values when you can keep NUMBER throughout the calculation.

### 7.3 CAST

CAST converts an expression to a target type:

~~~sql
SELECT CAST('2026-11-14' AS DATE)
FROM dual;
~~~

This example can depend on how Oracle interprets date strings according to NLS. For input strings with a known format, TO_DATE with a format mask is usually clearer.

### 7.4 Avoiding Implicit Conversion in Predicates

Suppose EMPLOYEE_ID is NUMBER. A query binding a string may force Oracle to convert types:

~~~sql
WHERE employee_id = '1001'
~~~

Bind a number instead:

~~~sql
WHERE employee_id = :employee_id
~~~

with a bind variable of type NUMBER from the driver. Proper bind types prevent unintended conversions and can better support index access.

## 8. NULL in PL/SQL Variables

NULL means no value or unknown; it is not the same as 0, a space string, or FALSE.

Example:

~~~sql
DECLARE
    l_amount NUMBER;
    l_name   VARCHAR2(100);
    l_flag   BOOLEAN;
BEGIN
    IF l_amount IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Amount is unknown');
    END IF;

    IF l_name IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Name is missing');
    END IF;

    IF l_flag IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Flag is unknown');
    END IF;
END;
/
~~~

### 8.1 Operations with NULL

Most arithmetic operations with NULL return NULL:

~~~sql
DECLARE
    l_amount NUMBER := NULL;
    l_total  NUMBER;
BEGIN
    l_total := l_amount + 100;
    DBMS_OUTPUT.PUT_LINE(l_total);
END;
/
~~~

The result remains NULL. If you want to treat NULL as 0, make the rule explicit and use NVL/COALESCE:

~~~sql
l_total := NVL(l_amount, 0) + 100;
~~~

Do not automatically replace every NULL with 0. In financial data, NULL may mean unknown, whereas 0 is a known value of zero.

### 8.2 COALESCE, NVL, and NULLIF

- NVL(expr1, expr2): returns expr2 when expr1 is NULL.
- COALESCE(expr1, expr2, ...): returns the first non-NULL expression.
- NULLIF(expr1, expr2): returns NULL if the two expressions are equal, otherwise returns expr1.

Example:

~~~sql
DECLARE
    l_input  NUMBER := NULL;
    l_amount NUMBER;
BEGIN
    l_amount := COALESCE(l_input, 0);
    DBMS_OUTPUT.PUT_LINE(l_amount);
END;
/
~~~

In a division expression:

~~~sql
l_ratio := l_numerator / NULLIF(l_denominator, 0);
~~~

NULLIF helps prevent division by zero by turning a denominator of 0 into NULL. The result when the denominator is 0 is NULL, not 0; handle it according to business semantics.

### 8.3 NOT NULL and Initial Values

~~~sql
DECLARE
    l_count PLS_INTEGER NOT NULL := 0;
    l_name  VARCHAR2(100) NOT NULL := 'Unknown';
BEGIN
    l_count := l_count + 1;
END;
/
~~~

A NOT NULL variable cannot be assigned NULL. Attempting to assign NULL raises a value error in PL/SQL. Initializing variables explicitly helps avoid logic depending on unassigned states.

## 9. Using %TYPE and %ROWTYPE

### 9.1 %TYPE

%TYPE declares a variable based on the data type of a column or another variable:

~~~sql
DECLARE
    l_employee_id employees.employee_id%TYPE;
    l_salary      employees.salary%TYPE;
BEGIN
    SELECT employee_id, salary
    INTO l_employee_id, l_salary
    FROM employees
    WHERE employee_id = 1001;
END;
/
~~~

Benefits:

- Reduces duplication of data type definitions.
- When the column type changes, dependent declarations can automatically stay in sync upon recompilation.
- Reduces mismatches between variables and columns.

%TYPE does not automatically inherit all column constraints or defaults. In particular, do not assume a %TYPE variable will have the same NOT NULL constraint as the source column; if the variable requires NOT NULL, declare that constraint explicitly.

### 9.2 %ROWTYPE

%ROWTYPE declares a record whose fields correspond to the columns of a table, view, or cursor:

~~~sql
DECLARE
    l_employee employees%ROWTYPE;
BEGIN
    SELECT *
    INTO l_employee
    FROM employees
    WHERE employee_id = 1001;

    DBMS_OUTPUT.PUT_LINE(l_employee.employee_name);
    DBMS_OUTPUT.PUT_LINE(l_employee.salary);
END;
/
~~~

Each field of the record has the corresponding column's data type. %ROWTYPE is useful when retrieving a full row; if only a few columns are needed, declaring individual variables makes it clearer which data is actually used.

### 9.3 %TYPE Does Not Replace NULL Checks

A variable declared with employees.salary%TYPE can receive NULL if the type or logic allows it, even when the source column has NOT NULL. Verify the schema and business constraints where the variable is used.

## 10. Combining Types in a Practical Block

Example of a block that calculates an order total and determines its status:

~~~sql
DECLARE
    l_order_id      orders.order_id%TYPE := 1001;
    l_quantity      PLS_INTEGER := 3;
    l_unit_price    NUMBER(12,2) := 125000.50;
    l_discount_rate NUMBER(5,4) := 0.10;
    l_order_total   NUMBER(14,2);
    l_order_date    DATE := SYSDATE;
    l_confirmed     BOOLEAN := FALSE;
    l_description   VARCHAR2(200 CHAR);
BEGIN
    l_order_total := ROUND(
        l_quantity * l_unit_price * (1 - l_discount_rate),
        2
    );

    l_description := 'Order ' || l_order_id ||
                     ' created at ' ||
                     TO_CHAR(l_order_date, 'YYYY-MM-DD HH24:MI:SS');

    IF l_order_total > 0 THEN
        l_confirmed := TRUE;
    END IF;

    IF l_confirmed IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Confirmation is unknown');
    ELSIF l_confirmed THEN
        DBMS_OUTPUT.PUT_LINE('Confirmed: ' || l_description);
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not confirmed');
    END IF;

    DBMS_OUTPUT.PUT_LINE(
        'Total = ' || TO_CHAR(l_order_total, 'FM9999999990D00')
    );
END;
/
~~~

This example demonstrates multiple data type groups within the same block. In a real application, price, quantity, creation date, and status should come from data/bind parameters and be validated against business constraints.

## 11. Choosing Data Types by Business Domain

| Business Data | Commonly Considered Type | Notes |
|---|---|---|
| Currency | NUMBER(p,2) or scale per currency | Define rounding rules |
| Percentages / rates | NUMBER(p,s) | Choose sufficient scale and value range |
| Counters | PLS_INTEGER or NUMBER | Consider 32-bit limit |
| Scientific measurements | BINARY_DOUBLE/BINARY_FLOAT | Binary approximation error acceptable |
| Fixed codes | CHAR(n) | Watch out for padding |
| Names / addresses | VARCHAR2(n CHAR) | Consider Unicode and byte limits |
| Long content | CLOB/NCLOB | Use LOB APIs when needed |
| Business dates | DATE | Includes hour/minute/second |
| High-precision instants | TIMESTAMP | Includes fractional seconds |
| Multi-timezone instants | TIMESTAMP WITH TIME ZONE | Retains time zone/offset |
| Session-normalized instants | TIMESTAMP WITH LOCAL TIME ZONE | Displayed per session time zone |
| Year/month intervals | INTERVAL YEAR TO MONTH | Not equivalent to a fixed number of days |
| Duration intervals | INTERVAL DAY TO SECOND | Used for durations |
| Logic flags in PL/SQL | BOOLEAN | Has TRUE/FALSE/NULL |
| Flags stored in SQL 19c | NUMBER(1) or CHAR(1) | Use CHECK constraints |

## 12. Common Errors When Working with Data Types

| Error or Symptom | Cause | Resolution |
|---|---|---|
| VALUE_ERROR when assigning a number | Value exceeds precision/scale or type range | Choose a wide enough type, check calculations |
| Small monetary discrepancy | Using binary floating-point | Use NUMBER and explicit ROUND rules |
| PLS_INTEGER overflow | Exceeds 32-bit range | Use NUMBER or validate bounds |
| String truncated/errors | Variable length too small or incorrect BYTE/CHAR semantics | Specify length and semantics clearly |
| Vietnamese string exceeds byte limit | One character takes multiple bytes | Check LENGTHB and charset |
| Empty string treated as NULL | Oracle rule for zero-length strings | Use a separate convention if a distinct state is needed |
| DATE wrong day/month | Implicit conversion depending on NLS | Use DATE literals or TO_DATE with a format |
| Time portion lost | Using DATE literal or format without time | Check format mask and data type |
| Displayed time shifted by time zone | Confusing SYSDATE with CURRENT_TIMESTAMP or using a non-timezone type | Choose function/type per business time zone |
| IF does not execute despite expecting FALSE | BOOLEAN is actually NULL; NOT NULL is still NULL | Check NULL state explicitly |
| Cannot declare BOOLEAN column on 19c | BOOLEAN was PL/SQL-only at that time | Use NUMBER(1)/CHAR(1) or upgrade version |
| Date index not used | Function/implicit conversion applied to column | Use properly typed binds and range predicates |

## 13. Self-Check Practice Exercises

These practice exercises should be run in a test schema.

### Exercise 1 — NUMBER Precision and Scale

Declare NUMBER(7,2), assign values with two, three, and six fractional digits. Observe how rounding behaves and try assigning a value exceeding precision. Explain VALUE_ERROR.

### Exercise 2 — PLS_INTEGER and NUMBER

Write a PLS_INTEGER counter and a NUMBER(14,2) total amount variable. Try incrementing the counter near the 32-bit boundary and explain why PLS_INTEGER should not be used for all integer calculations.

### Exercise 3 — Floating-Point

Declare BINARY_DOUBLE and NUMBER, and add the value 0.1 multiple times. Compare the results and explain the difference between approximate binary representation and decimal NUMBER.

### Exercise 4 — CHAR and VARCHAR2

Assign a short string to CHAR(5) and VARCHAR2(5). Compare LENGTH, LENGTHB, and how trailing space padding is displayed.

### Exercise 5 — BYTE and CHAR Semantics

Create VARCHAR2(10 BYTE) and VARCHAR2(10 CHAR) variables. Assign a Vietnamese string with diacritics. Observe the length in bytes and in characters in the current database character set.

### Exercise 6 — Empty String and NULL

Assign an empty string and a string with a single space to two VARCHAR2 variables. Check IS NULL, LENGTH, and LENGTHB. Explain why the two values differ.

### Exercise 7 — DATE and TIMESTAMP

Create a DATE and a TIMESTAMP with fractional seconds. Perform subtraction and compare the result types. Try formatting with TO_CHAR.

### Exercise 8 — Time Zones

Compare SYSDATE, CURRENT_DATE, SYSTIMESTAMP, and CURRENT_TIMESTAMP in sessions with different time zones. Explain the difference between server time and session time.

### Exercise 9 — Three-Valued BOOLEAN

Declare three variables as TRUE, FALSE, and NULL. Test AND, OR, NOT, and IF. Write branches that distinguish FALSE from NULL.

### Exercise 10 — %TYPE and %ROWTYPE

Declare a variable using employees.salary%TYPE and a record using employees%ROWTYPE. Try SELECT INTO. Check what happens when SELECT returns no rows or more than one row.

### Exercise 11 — Explicit Conversion

Convert date strings using two different format masks. Try changing the session's NLS_DATE_FORMAT and explain why implicit conversion is unsafe.

### Exercise 12 — Flag Modeling in SQL 19c

Create a NUMBER(1) NOT NULL column with CHECK (value IN (0,1)). Write a PL/SQL block that converts the value to BOOLEAN and handles the case where the column allows NULL.

## 14. Key Takeaways

| Topic | Key Point |
|---|---|
| NUMBER | Decimal numeric type suited for money and data requiring accuracy |
| NUMBER(p,s) | Precision and scale bound the value range |
| PLS_INTEGER | 32-bit integer, suited for counters/indices |
| BINARY_FLOAT/DOUBLE | Approximate floating-point |
| CHAR/VARCHAR2 | Fixed-length and variable-length strings |
| BYTE/CHAR semantics | Bytes do not equal characters in multibyte charsets |
| CLOB/NCLOB | Stores large text |
| Empty string | Zero-length VARCHAR2/CHAR is treated as NULL by Oracle |
| DATE | Has time down to seconds, no time zone |
| TIMESTAMP | Has fractional seconds |
| TIMESTAMP WITH TIME ZONE | Carries time zone/offset |
| INTERVAL | Represents year-month or day-second durations |
| TO_DATE/TO_TIMESTAMP | Converts strings using an explicit format mask |
| BOOLEAN | TRUE, FALSE, NULL in PL/SQL |
| SQL BOOLEAN | Available from Oracle Database 23c; no SQL BOOLEAN column before then |
| %TYPE/%ROWTYPE | Anchors variable/record types to a column or row |
| NULL | Different from 0, FALSE, and space strings |

Choose data types based on value range and business semantics, not just convenience when declaring them. NUMBER protects decimal accuracy; PLS_INTEGER fits counters; VARCHAR2 and CHAR require distinguishing length semantics; DATE/TIMESTAMP must go hand in hand with time zone and formatting rules; BOOLEAN requires handling the NULL state. Using clear types, explicit conversions, and input validation makes PL/SQL easier to understand and avoids many subtle bugs.
