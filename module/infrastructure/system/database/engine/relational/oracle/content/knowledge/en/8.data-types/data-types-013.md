# Distinguishing BOOLEAN in PL/SQL and SQL by Supported Version

In Oracle Database, the keyword **`BOOLEAN`** can appear in two contexts: **PL/SQL variables and expressions** and **SQL column data types and expressions**. These two contexts historically had different version support. That is why `DECLARE v_ok BOOLEAN := TRUE;` runs cleanly on Oracle 19c while creating a table with column `is_active BOOLEAN` fails on the exact same database.

The major change is that **Oracle Database 23c/23ai brings the `BOOLEAN` data type into SQL**. Prior releases, including Oracle 19c and 21c, supported `BOOLEAN` in **PL/SQL** but **had no native `BOOLEAN` column type in SQL**. When working across multiple versions, developers must choose flag storage patterns, write queries, and configure JDBC mappings based on the **actual database release**, while testing their driver/ORM.

## 1. First Distinguish Oracle's Two Languages

**SQL** defines and manipulates data: `CREATE TABLE`, `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `WHERE`, `JOIN`, `GROUP BY`, and query expressions. **PL/SQL** is Oracle's procedural extension to SQL, offering variables, data types, `IF`, loops, exceptions, procedures, functions, and packages.

```text
           APPLICATION / SQL CLIENT
                      |
           +----------+----------+
           |                     |
           v                     v
       ORACLE SQL             ORACLE PL/SQL
   CREATE TABLE, SELECT,      DECLARE, IF, LOOP,
   INSERT, WHERE, CASE        FUNCTION, PROCEDURE
           |                     |
           | SQL BOOLEAN from    | PL/SQL BOOLEAN available
           | Oracle 23c/23ai     | since older versions
           +----------+----------+
                      |
                ORACLE DATABASE
```

Even on Oracle 19c, `WHERE` conditions evaluate **TRUE, FALSE, UNKNOWN** logic. For example, `WHERE amount > 0` tests a true/false/unknown condition. However, **having Boolean conditions in SQL grammar does not mean having a SQL `BOOLEAN` data type to store in columns or return as values**. The distinction between a *logical condition* and a *first-class SQL data type* is central to this lesson.

### 1.1. Version Support Matrix

| Oracle Database Version | `BOOLEAN` Variables in PL/SQL | `BOOLEAN` Column in `CREATE TABLE` | Boolean Expressions as Standalone SQL Values | Common Flag Storage Pattern |
|---|---|---|---|---|
| 11g/12c/18c | Yes | No | No SQL `BOOLEAN` type | `NUMBER(1)`, `CHAR(1)`, `VARCHAR2` with constraint |
| **19c** | **Yes** | **No** | Cannot use Boolean as a SQL value type | `NUMBER(1)` or `CHAR(1)` with constraint |
| **21c** | **Yes** | **No** | No native SQL `BOOLEAN` data type | Still uses alternative storage types |
| **23c/23ai** | **Yes** | **Yes** | **Yes**, including `TRUE`/`FALSE` literals and Boolean expressions | Can use `BOOLEAN` directly if the whole ecosystem supports it |
| **26ai and later SQL BOOLEAN-supporting releases** | Yes | Yes | Yes | `BOOLEAN` supported; verify drivers, ORMs, and upgrade paths |

> **Note on release naming:** docs and examples may refer to the feature as "Oracle Database 23c SQL BOOLEAN" or "Oracle Database 23ai SQL BOOLEAN." Before running scripts, verify the **actual release you are connected to**. Never infer from SQL filenames, service names, SQL Developer version, or JDBC driver version.

**Direct consequence:** a schema migration using `CREATE TABLE ... (flag BOOLEAN)` cannot be treated as backward-compatible with Oracle 19c/21c. If an application must run on both 19c and 23ai, adopt an explicit conditional storage/migration strategy.

## 2. PL/SQL BOOLEAN: Available Before Oracle 23ai

PL/SQL `BOOLEAN` has three states:

- `TRUE`: condition holds.
- `FALSE`: condition does not hold.
- `NULL`: unknown or undefined; **distinct** from `FALSE`.

It is a logical type used in **PL/SQL variables, parameters, and function return types**. The following example uses PL/SQL syntax and runs on common Oracle versions before and after 23ai:

```sql
SET SERVEROUTPUT ON;

DECLARE
    v_paid     BOOLEAN := TRUE;
    v_verified BOOLEAN := NULL;
BEGIN
    IF v_paid THEN
        DBMS_OUTPUT.PUT_LINE('Order is paid');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Order payment not yet confirmed');
    END IF;

    IF v_verified IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Verification status unknown');
    END IF;
END;
/
```

This code passes **character strings** to `DBMS_OUTPUT.PUT_LINE`. On older versions, `DBMS_OUTPUT.PUT_LINE(v_paid)` with a `BOOLEAN` argument has no overload accepting Boolean like `VARCHAR2`; converting to text via `IF`/`CASE` is broadly portable.

### 2.1. `BOOLEAN` in Procedures and Functions

```sql
CREATE OR REPLACE PROCEDURE check_discount (
    p_is_vip IN BOOLEAN
) AS
BEGIN
    IF p_is_vip THEN
        DBMS_OUTPUT.PUT_LINE('Apply VIP privilege');
    ELSIF p_is_vip IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('VIP status undetermined');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Do not apply VIP privilege');
    END IF;
END;
/

BEGIN
    check_discount(TRUE);
    check_discount(FALSE);
    check_discount(NULL);
END;
/
```

These three calls occur **inside PL/SQL**. That does not prove every application or older SQL statement can bind/return `BOOLEAN` like a SQL column type. When invoking PL/SQL from JDBC, OCI, or external tools, bind support depends on the driver/API and version; verify what your driver supports rather than treating it like a SQL `BOOLEAN` column.

### 2.2. How Does `IF` Handle `NULL`?

In PL/SQL, the `THEN` branch of `IF expression THEN` executes **only when the expression evaluates to `TRUE`**. When it evaluates to `FALSE` or `NULL`, Oracle moves to `ELSIF`/`ELSE`.

```sql
DECLARE
    v_enabled BOOLEAN := NULL;
BEGIN
    IF v_enabled THEN
        DBMS_OUTPUT.PUT_LINE('TRUE');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not TRUE');
    END IF;

    IF NOT v_enabled THEN
        DBMS_OUTPUT.PUT_LINE('FALSE');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not FALSE');
    END IF;
END;
/
```

With `v_enabled = NULL`, both `IF` statements take `ELSE`: `v_enabled` is `NULL`, and `NOT NULL` is also `NULL`. Therefore, `IF NOT v_enabled` cannot be used to test definitively for `FALSE` when the variable is nullable.

To distinguish all three states in PL/SQL, check in this order:

```sql
IF v_enabled IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('UNKNOWN');
ELSIF v_enabled THEN
    DBMS_OUTPUT.PUT_LINE('TRUE');
ELSE
    DBMS_OUTPUT.PUT_LINE('FALSE');
END IF;
```

`NULL` can be a genuine business state—such as an unreviewed request, unsynchronized record, or unanswered prompt. Never convert every `NULL` into `FALSE` if doing so changes business meaning.

### 2.3. Three-Valued Truth Tables

| A | `NOT A` | Notes |
|---|---|---|
| `TRUE` | `FALSE` | Negating true yields false |
| `FALSE` | `TRUE` | Negating false yields true |
| `NULL` | `NULL` | Unknown remains unknown |

| A | B | `A AND B` | `A OR B` |
|---|---|---|---|
| `TRUE` | `TRUE` | `TRUE` | `TRUE` |
| `TRUE` | `FALSE` | `FALSE` | `TRUE` |
| `TRUE` | `NULL` | `NULL` | `TRUE` |
| `FALSE` | `FALSE` | `FALSE` | `FALSE` |
| `FALSE` | `NULL` | `FALSE` | `NULL` |
| `NULL` | `NULL` | `NULL` | `NULL` |

Three-valued logic applies in both SQL conditions (even before 23ai) and PL/SQL `BOOLEAN`. The version difference lies in **whether Boolean can be used as a SQL data value**.

## 3. Oracle 19c/21c: Why Doesn't SQL Have `BOOLEAN` Columns?

On Oracle 19c or 21c, the following statement is not supported:

```sql
-- CANNOT run on Oracle 19c/21c:
CREATE TABLE lab_feature_flags (
    feature_id NUMBER PRIMARY KEY,
    enabled    BOOLEAN
);
```

This is **SQL DDL**. Although PL/SQL in the same release allows `DECLARE v_enabled BOOLEAN;`, the SQL column type system does not yet include `BOOLEAN`. On older releases, you encounter an invalid-datatype error such as `ORA-00902` depending on statement and version; do not assume every case produces the exact same error code.

Likewise, `SELECT TRUE FROM dual` or `SELECT (amount > 0) FROM orders` **cannot work in SQL 19c/21c as returning a Boolean column**. On those releases, *conditional* syntax appears in `WHERE`, `CASE WHEN`, and `HAVING`, yet selecting a condition expression as a standalone returned value lacks 23ai's SQL `BOOLEAN` support.

### 3.1. True/False Conditions Still Work in `WHERE` and `CASE`

```sql
-- Compatible with versions prior to SQL BOOLEAN:
SELECT order_id, amount
FROM orders
WHERE amount > 0;

SELECT order_id,
       CASE WHEN amount > 0 THEN 1 ELSE 0 END AS has_positive_amount
FROM orders;
```

Here `amount > 0` is a **SQL condition**; the `CASE` expression produces type `NUMBER`, not SQL `BOOLEAN`. Naming an alias `has_positive_amount` does not mean the database has a Boolean column.

### 3.2. Pattern Using `NUMBER(1)` with `CHECK`

A common solution for two-state flags in Oracle 19c/21c schemas:

```sql
CREATE TABLE lab_flags_number (
    feature_id NUMBER PRIMARY KEY,
    enabled    NUMBER(1) DEFAULT 0 NOT NULL,
    CONSTRAINT ck_lab_flags_number_enabled CHECK (enabled IN (0, 1))
);

INSERT INTO lab_flags_number (feature_id, enabled) VALUES (1, 1);
INSERT INTO lab_flags_number (feature_id, enabled) VALUES (2, 0);
COMMIT;

SELECT feature_id, enabled
FROM lab_flags_number
WHERE enabled = 1;
```

Make the convention explicit: `1 = TRUE`, `0 = FALSE`. `NUMBER(1)` **does not restrict values to 0 and 1 on its own**; the `CHECK` constraint rejects out-of-domain numbers. `NOT NULL` narrows the column to two states. If the business needs "unknown", drop `NOT NULL` and allow `NULL`, while defining behavior from API to SQL.

If nullable, `CHECK (enabled IN (0,1))` **does not forbid `NULL`**; in Oracle, check constraints allow `UNKNOWN` unless paired with another constraint. That is why `NOT NULL` must be declared explicitly for strictly two-state data.

### 3.3. Pattern Using `CHAR(1)` with `Y/N`

```sql
CREATE TABLE lab_flags_char (
    feature_id NUMBER PRIMARY KEY,
    enabled    CHAR(1) DEFAULT 'N' NOT NULL,
    CONSTRAINT ck_lab_flags_char_enabled CHECK (enabled IN ('Y', 'N'))
);

INSERT INTO lab_flags_char (feature_id, enabled) VALUES (1, 'Y');
INSERT INTO lab_flags_char (feature_id, enabled) VALUES (2, 'N');
COMMIT;
```

`Y/N` is easy to read in manual SQL queries, though it requires an explicit mapping to `Boolean` in Java. Other apps using `'T'/'F'` or `'TRUE'/'FALSE'` are also **data conventions**, not true SQL Booleans. Never mix multiple conventions in the same schema without a clear justification and compatibility plan.

### 3.4. Comparing the Two Traditional Options

| Criterion | `NUMBER(1)` + `CHECK (IN (0,1))` | `CHAR(1)` + `CHECK (IN ('Y','N'))` |
|---|---|---|
| Stored values | `1`, `0` | `'Y'`, `'N'` |
| Native SQL `BOOLEAN` type? | No | No |
| Readability in manual queries | Requires knowing 1/0 convention | Fairly intuitive if knowing Y/N |
| JDBC/ORM mapping | Maps numbers to Java Boolean via converter/dialect | Commonly uses an explicit converter |
| Constraint needed? | Yes, to prevent digits other than 0/1 | Yes, to prevent letters other than Y/N |
| Can store `NULL`? | Yes, if not `NOT NULL` | Yes, if not `NOT NULL` |
| Moving to SQL BOOLEAN on upgrade | Requires migration and mapping updates | Requires migration and mapping updates |

In production systems, prefer **keeping one consistent convention**, changing column types only after reviewing schemas, existing data, clients, stored procedures, and rollback/forward-fix paths.

## 4. PL/SQL vs. SQL Boundary on Older Versions

A PL/SQL procedure accepting `BOOLEAN` does not mean SQL on Oracle 19c/21c can **directly store or return** Booleans the way SQL columns do.

```sql
-- PL/SQL pre-23ai: function can return BOOLEAN to a PL/SQL caller.
CREATE OR REPLACE FUNCTION lab_is_even (p_value IN NUMBER)
RETURN BOOLEAN
IS
BEGIN
    RETURN MOD(p_value, 2) = 0;
END;
/

-- Calling from PL/SQL on older versions:
BEGIN
    IF lab_is_even(10) THEN
        DBMS_OUTPUT.PUT_LINE('10 is an even number');
    END IF;
END;
/
```

On versions lacking SQL BOOLEAN, you cannot use a function's `BOOLEAN` return value as a **returned column expression in `SELECT`** like this:

```sql
-- Not a valid SQL query on Oracle 19c/21c:
SELECT lab_is_even(10) AS is_even
FROM dual;
```

A broadly compatible approach is providing a **wrapper returning a classic SQL type**, such as `NUMBER` or `VARCHAR2`. The wrapper must map `NULL` faithfully so "unknown" is not accidentally turned into `FALSE`.

```sql
CREATE OR REPLACE FUNCTION lab_is_even_num (p_value IN NUMBER)
RETURN NUMBER
IS
    v_result BOOLEAN;
BEGIN
    v_result := lab_is_even(p_value);

    IF v_result IS NULL THEN
        RETURN NULL;
    ELSIF v_result THEN
        RETURN 1;
    ELSE
        RETURN 0;
    END IF;
END;
/

-- Using NUMBER result in legacy SQL:
SELECT lab_is_even_num(10) AS is_even_number
FROM dual;
```

In certain versions and contexts, SQL can invoke a PL/SQL function with Boolean **parameters** through supported bind mechanisms. That **does not make Boolean a full SQL datatype**: never assume every literal, column, return value, or bind API works identically. When strict 19c/21c compatibility is needed, APIs using traditional SQL parameter/return types are simpler and less error-prone.

## 5. Oracle 23c/23ai: SQL BOOLEAN Becomes a Native Data Type

Oracle Database 23c/23ai supports `BOOLEAN` directly in SQL, including columns, expressions, and conditions. The SQL `BOOLEAN` type has three logical values—`TRUE`, `FALSE`, and `NULL` (unknown); a `NOT NULL` column restricts values to `TRUE` and `FALSE`.

```sql
-- ONLY run on Oracle Database supporting SQL BOOLEAN (23c/23ai+).
CREATE TABLE lab_flags_boolean (
    feature_id NUMBER PRIMARY KEY,
    feature_name VARCHAR2(100 CHAR) NOT NULL,
    enabled BOOLEAN DEFAULT FALSE NOT NULL
);

INSERT INTO lab_flags_boolean (feature_id, feature_name, enabled)
VALUES (1, 'new-checkout', TRUE);

INSERT INTO lab_flags_boolean (feature_id, feature_name, enabled)
VALUES (2, 'old-report', FALSE);

COMMIT;

SELECT feature_id, feature_name, enabled
FROM lab_flags_boolean;
```

`enabled` is now **genuinely SQL `BOOLEAN`**. In some Oracle docs, **`BOOL`** is also accepted as an alias for this type. Even so, use `BOOLEAN` consistently so documentation and migrations stay clear.

### 5.1. `TRUE` and `FALSE` Are SQL Literals

In SQL 23ai, `TRUE` and `FALSE` are logical literals, not column names or strings `'TRUE'`, `'FALSE'`:

```sql
-- Direct SQL BOOLEAN:
SELECT TRUE AS always_true,
       FALSE AS always_false
FROM dual;

SELECT feature_name
FROM lab_flags_boolean
WHERE enabled IS TRUE;

SELECT feature_name
FROM lab_flags_boolean
WHERE enabled IS FALSE;
```

`IS TRUE` and `IS FALSE` express state checks cleanly. For nullable columns, also use `IS NULL` when distinguishing "unknown". Boolean expressions can also appear in `SELECT` to return a Boolean value:

```sql
SELECT feature_id,
       (feature_id > 1) AS has_large_id
FROM lab_flags_boolean;
```

This is a major departure from SQL 19c/21c, where conditions like `feature_id > 1` could appear in `WHERE` yet were not **SQL `BOOLEAN` values** returnable in a select list.

### 5.2. Writing Conditions with SQL Boolean

```sql
-- Ways to check for TRUE flag:
SELECT feature_name
FROM lab_flags_boolean
WHERE enabled;

SELECT feature_name
FROM lab_flags_boolean
WHERE enabled IS TRUE;

-- Ways to check for FALSE flag:
SELECT feature_name
FROM lab_flags_boolean
WHERE NOT enabled;

SELECT feature_name
FROM lab_flags_boolean
WHERE enabled IS FALSE;
```

In the example table where `enabled` is `NOT NULL`, the pairs behave identically for two states. When a column **can be `NULL`**, however, there is a critical difference: `WHERE NOT enabled` selects only rows where `enabled` is `FALSE`; it **excludes `NULL` rows** because `NOT NULL` stays `NULL`, and `WHERE` keeps only `TRUE`.

### 5.3. Nullable Booleans and `IS NOT TRUE`

Create another example for three-valued states:

```sql
-- Oracle 23ai+; column allows NULL.
CREATE TABLE lab_flags_nullable (
    id NUMBER PRIMARY KEY,
    approved BOOLEAN
);

INSERT INTO lab_flags_nullable VALUES (1, TRUE);
INSERT INTO lab_flags_nullable VALUES (2, FALSE);
INSERT INTO lab_flags_nullable VALUES (3, NULL);
COMMIT;
```

| SQL Condition | Rows Selected | Meaning |
|---|---|---|
| `approved IS TRUE` | `id = 1` | Only `TRUE` |
| `approved IS FALSE` | `id = 2` | Only `FALSE` |
| `approved IS NULL` | `id = 3` | Only unknown |
| `NOT approved` | `id = 2` | `NOT NULL` stays `NULL`, does not pick `id = 3` |
| `approved IS NOT TRUE` | `id = 2, 3` | Includes `FALSE` **and** `NULL` |
| `approved IS NOT FALSE` | `id = 1, 3` | Includes `TRUE` **and** `NULL` |

`IS NOT TRUE` **differs** from `IS FALSE`. A business query for "not yet confirmed approved" may want both `FALSE` and `NULL`; a query for "explicitly rejected" should normally select only `FALSE`. That is a business decision, not just syntax preference.

### 5.4. What Types Can `CASE` Return?

In SQL 23ai, `BOOLEAN` can be returned by compatible SQL expressions:

```sql
-- Return Boolean directly:
SELECT feature_id,
       CASE
           WHEN feature_id = 1 THEN TRUE
           ELSE FALSE
       END AS is_first_feature
FROM lab_flags_boolean;

-- If a legacy API expects NUMBER(1), keep the numeric contract:
SELECT feature_id,
       CASE WHEN enabled IS TRUE THEN 1 ELSE 0 END AS enabled_num
FROM lab_flags_boolean;
```

In the second example, `enabled` is `NOT NULL`, so mapping to `1/0` loses no unknown state. If the source can be `NULL` and the API preserves three states, map `NULL` explicitly, for example:

```sql
SELECT id,
       CASE
           WHEN approved IS TRUE THEN 1
           WHEN approved IS FALSE THEN 0
           ELSE NULL
       END AS approved_num
FROM lab_flags_nullable;
```

Avoid `ELSE 0` for both `FALSE` and `NULL` unless business rules explicitly define them as equivalent.

## 6. SQL BOOLEAN and PL/SQL BOOLEAN from 23ai: Seamless Interaction

Once SQL has a `BOOLEAN` datatype, exchanging values between PL/SQL and SQL becomes direct. A PL/SQL function returning Boolean can be used as a SQL value expression where supported:

```sql
-- PL/SQL function similar to earlier example:
CREATE OR REPLACE FUNCTION lab_is_positive (p_value IN NUMBER)
RETURN BOOLEAN
IS
BEGIN
    IF p_value IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN p_value > 0;
END;
/

-- Oracle 23ai+: SQL receives returned BOOLEAN value.
SELECT lab_is_positive(10) AS positive_check
FROM dual;
```

On older versions, a function with `RETURN BOOLEAN` works inside PL/SQL yet **cannot be used as a SQL column expression in `SELECT`**. The 23ai feature simplifies SQL/PLSQL contracts for systems running on newer releases.

PL/SQL still retains its own role: `BOOLEAN` in a PL/SQL expression drives `IF`, `LOOP`, and procedures; SQL `BOOLEAN` is a persistent schema type queryable through drivers. Both supporting Boolean does not erase differences in **scope, transactions, SQL syntax, and privileges**.

### 6.1. Not Every Older Component Automatically Understands the New Type

An application connecting to 23ai may use an older driver or ORM configured to map `Boolean` to `NUMBER(1)` or `CHAR(1)`. Even when the database has SQL BOOLEAN, verify:

- Does your JDBC/OCI/ODP.NET or client driver support the server's `BOOLEAN` type?
- Does your Hibernate/JPA dialect pick the right SQL type for `Boolean` on the **target Oracle version**?
- Does code reading `NULL` into primitive `boolean` silently erase the unknown state?
- Do native queries, stored procedures, schema migrations, serializers, and reports/exports understand the new type?
- If using multiple datasources, do any 19c/21c environments still run the older schema?

**Database version and client version are two independent compatibility axes.** Never change storage design solely because the app upgraded its JDK or Spring Boot version.

## 7. Converting Between BOOLEAN, NUMBER, and Strings

On SQL 23ai+, Oracle supports logical type conversions and explicit functions such as `TO_BOOLEAN`, `TO_CHAR`, or `CAST` in supported contexts.

### 7.1. Explicit Conversion in Modern SQL

```sql
-- Use only on versions supporting SQL BOOLEAN:
SELECT TO_BOOLEAN(1) AS bool_from_one,
       TO_BOOLEAN(0) AS bool_from_zero,
       TO_BOOLEAN('true') AS bool_from_text
FROM dual;

SELECT TO_CHAR(TRUE) AS true_as_text,
       TO_CHAR(FALSE) AS false_as_text
FROM dual;
```

`TO_BOOLEAN` accepts valid numeric/string inputs per version rules; for numeric inputs, **0 becomes `FALSE` and any nonzero number becomes `TRUE`**. Consequently, if legacy data accidentally contains `2` or `-1`, converting numbers straight to Boolean turns them into `TRUE` instead of raising an error for a `0/1` domain. **Cleanse and constrain data before migrating**.

Accepted string values depend on Oracle conversion rules and include representations such as `'true'`/`'false'`. In production migrations, **define explicit mappings** instead of relying on every string variant Oracle might coerce.

Example safely converting a `NUMBER(1)` flag to a Boolean expression:

```sql
-- SQL BOOLEAN on Oracle 23ai+; column legacy_enabled holds 0/1/NULL.
SELECT feature_id,
       CASE
           WHEN legacy_enabled = 1 THEN TRUE
           WHEN legacy_enabled = 0 THEN FALSE
           ELSE NULL
       END AS enabled_bool
FROM legacy_flags;
```

This illustrates mapping over an existing `legacy_flags` table; prepare actual schema/migration scripts before running. Compared to `TO_BOOLEAN(legacy_enabled)`, `CASE` documents the accepted domain and out-of-domain behavior clearly. If values outside `0/1/NULL` appear, investigate or error per procedure instead of silently folding them into one branch.

### 7.2. Converting Boolean to String for Display

With SQL Boolean 23ai+, you can produce display labels while handling unknown states:

```sql
SELECT id,
       CASE
           WHEN approved IS TRUE THEN 'APPROVED'
           WHEN approved IS FALSE THEN 'REJECTED'
           ELSE 'PENDING'
       END AS approval_label
FROM lab_flags_nullable;
```

Converting to labels is a **presentation concern**. Do not store localized display labels as canonical database values when the app must filter, sort, or synchronize business state. When a status has more than two distinct meaningful states like `PENDING`, `APPROVED`, `REJECTED`, use a **status code / enum** rather than forcing it into a Boolean.

### 7.3. PL/SQL Conversion on Older Releases

In PL/SQL 19c/21c, an explicit `IF` or `CASE` wrapper is clear and unambiguous:

```sql
DECLARE
    v_flag BOOLEAN := NULL;
    v_number NUMBER(1);
BEGIN
    IF v_flag IS NULL THEN
        v_number := NULL;
    ELSIF v_flag THEN
        v_number := 1;
    ELSE
        v_number := 0;
    END IF;

    DBMS_OUTPUT.PUT_LINE('Mapped flag: ' || NVL(TO_CHAR(v_number), 'NULL'));
END;
/
```

Oracle 23ai+ adds richer SQL conversions, yet never introduce new functions into scripts that must still run on 19c. When maintaining shared libraries, branch by baseline version or keep legacy-compatible mappings for un-upgraded environments.

## 8. Java/JDBC Compatibility: `boolean` vs. `Boolean`

In Java:

- `boolean` is a primitive type with only `true` or `false`.
- `java.lang.Boolean` is a wrapper type holding `true`, `false`, or `null`.

When a SQL column is nullable, reading into primitive `boolean` can **erase the unknown state**. JDBC `ResultSet.getBoolean(...)` returns primitive Java `boolean`; when the SQL column is `NULL`, standard JDBC returns `false`, so you must call **`ResultSet.wasNull()`** to check whether the original value was `NULL`.

### 8.1. Reading SQL BOOLEAN on Oracle 23ai+ via Supported JDBC

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class BooleanFlagReader {
    public static Boolean readFlag(Connection connection, long featureId)
            throws SQLException {
        String sql = "SELECT enabled FROM lab_flags_boolean WHERE feature_id = ?";

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, featureId);

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return null; // Record not found; caller must distinguish if needed.
                }

                boolean value = result.getBoolean("enabled");
                return result.wasNull() ? null : Boolean.valueOf(value);
            }
        }
    }
}
```

In the `lab_flags_boolean` example table, `enabled` is `NOT NULL`, yet this code illustrates how JDBC handles `NULL` in general. A production business API should **distinguish "no record found" from "record found with `NULL` flag"**, such as returning an `Optional`, a result record, or a clear exception.

With JDBC drivers supporting native SQL `BOOLEAN`, `PreparedStatement.setBoolean(...)` and `ResultSet.getBoolean(...)` are familiar APIs. Some drivers also support `getObject(..., Boolean.class)` or direct SQL type bindings; exact capabilities must be **verified against your Oracle JDBC driver and server versions**. Never assume every driver supports the new type just because Java has `Boolean`.

### 8.2. Inserting SQL BOOLEAN via `PreparedStatement`

```java
String sql = "INSERT INTO lab_flags_boolean (feature_id, feature_name, enabled)"
           + " VALUES (?, ?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 100L);
    statement.setString(2, "feature-java");
    statement.setBoolean(3, true);
    statement.executeUpdate();
}
```

This example targets a **SQL BOOLEAN database and compatible driver**. It will not give Oracle 19c/21c a `BOOLEAN` column. To write `NULL` into a nullable Boolean column, use `setNull` with a JDBC/driver-supported SQL type such as `java.sql.Types.BOOLEAN` after verifying with integration tests.

### 8.3. For Oracle 19c/21c: Bind According to Actual Storage Type

If the schema stores flags as `NUMBER(1)`, the explicit approach is:

```java
// Column enabled is NUMBER(1), 1 = true, 0 = false.
try (PreparedStatement statement = connection.prepareStatement(
        "UPDATE lab_flags_number SET enabled = ? WHERE feature_id = ?")) {
    statement.setInt(1, true ? 1 : 0);
    statement.setLong(2, 1L);
    statement.executeUpdate();
}
```

In real applications, the Boolean value comes from a business variable. If nullable, map `null` to SQL `NULL` when permitted by the contract rather than coercing silently to `0`. For `CHAR(1)` columns, pass `'Y'`/`'N'` via `setString`; you can use an `AttributeConverter<Boolean, String>` or ORM equivalent to centralize mapping.

### 8.4. ORM/JPA/Hibernate May Generate Different DDL

Example Java entity:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class FeatureFlag {
    @Id
    private Long id;

    @Column(nullable = false)
    private Boolean enabled;

    // Constructors / getters / setters omitted for brevity.
}
```

This entity **does not determine by itself** whether the database gets `BOOLEAN`, `NUMBER(1)`, or another column type. Generated DDL and parameter binding depend on the dialect, ORM version, JDBC driver, schema generation mode, and explicit mapping configuration. For an application supporting both **19c and 23ai**, never rely solely on ORM auto-generated DDL; manage versioned SQL migrations and run integration tests against **real Oracle** for every supported baseline.

### 8.5. Note on Bind Changes in Newer Driver Releases

When upgrading the database or Oracle JDBC driver, how **Java `boolean`** is transmitted to the server may change to use native SQL type support. This can affect older applications expecting a `NUMBER` or `VARCHAR` bind rather than SQL `BOOLEAN`. Newer Oracle JDBC documentation covers options controlling native Boolean binding in certain cases; use such options only after evaluating your real driver and server combination.

Before upgrading, test at minimum `INSERT`, `UPDATE`, `SELECT`, `TRUE/FALSE/NULL` binds, stored procedures, and native queries. In particular, never rely on implicit coercion when the database contract requires exact `0/1` or `Y/N`.

## 9. Migrating from `NUMBER(1)`/`CHAR(1)` to SQL BOOLEAN

Once Oracle is upgraded to 23ai or a newer release supporting SQL BOOLEAN, native `BOOLEAN` columns **become an option**. However, changing a column actively used by applications can impact SQL queries, stored procedures, reports, indexes, ETL pipelines, ORMs, caches, and older clients. It is a **schema contract change**, not just swapping a keyword in DDL.

### 9.1. Inspect Existing Data

Suppose a legacy table uses `NUMBER(1)` with `1/0`:

```sql
-- Run on existing legacy_flags table in a test environment.
SELECT legacy_enabled, COUNT(*) AS row_count
FROM legacy_flags
GROUP BY legacy_enabled
ORDER BY legacy_enabled;
```

Check whether `NULL`, `2`, `-1`, or invalid values exist. A `NUMBER(1)` column does not guarantee only 0/1 if no prior constraint existed; audit data quality before converting.

```sql
SELECT COUNT(*) AS invalid_rows
FROM legacy_flags
WHERE legacy_enabled NOT IN (0, 1)
   OR legacy_enabled IS NULL;
```

That condition treats `NULL` as "invalid" **only if** the business requires a two-state `NOT NULL` flag. If `NULL` is valid, adjust the check query and migration plan accordingly.

### 9.2. Add a New Boolean Column Instead of Modifying In-Place Blindly

A suitable strategy for systems needing compatibility is **expand → backfill → switch → contract**:

```text
Old schema: legacy_enabled NUMBER(1)
       |
       v
EXPAND: add nullable enabled_bool BOOLEAN
       |
       v
BACKFILL: convert 1 -> TRUE, 0 -> FALSE, NULL -> NULL
       |
       v
VERIFY: compare row counts, check mismatches, test apps and clients
       |
       v
SWITCH: applications gradually migrate to the new column per plan
       |
       v
CONTRACT: drop old column once no consumers depend on it
```

Example **for Oracle 23ai+ only in an authorized environment**:

```sql
-- Existing legacy_flags table has column legacy_enabled NUMBER(1).
ALTER TABLE legacy_flags ADD (enabled_bool BOOLEAN);

UPDATE legacy_flags
SET enabled_bool = CASE
    WHEN legacy_enabled = 1 THEN TRUE
    WHEN legacy_enabled = 0 THEN FALSE
    ELSE NULL
END;

COMMIT;
```

This snippet illustrates the mapping; it is **not a complete production migration for a large table**. Before running in production, plan out-of-domain cleanup, batched backfills, locking, undo/redo volume, application rollback, dual-column synchronization during transition, when to enforce `NOT NULL`, and criteria for dropping the legacy column.

### 9.3. Verify After Backfill

```sql
-- Oracle 23ai+, example verifying 0/1/NULL mapping.
SELECT COUNT(*) AS mismatch_rows
FROM legacy_flags
WHERE (legacy_enabled = 1 AND enabled_bool IS NOT TRUE)
   OR (legacy_enabled = 0 AND enabled_bool IS NOT FALSE)
   OR (legacy_enabled IS NULL AND enabled_bool IS NOT NULL);
```

This query verifies only **part** of the mapping; values outside 0/1/NULL must have been caught during data profiling. On large tables, key-range verification, statistics, and batched checks are safer than a full-table scan during peak load.

Oracle DDL usually issues an **implicit commit**, so `ALTER TABLE ... ADD` is not undone by rolling back a subsequent DML transaction. Application rollback and schema rollback are separate concerns; plan transition safety when multiple app versions run concurrently.

### 9.4. When Not to Rush Switching to BOOLEAN

- The system must still support Oracle 19c/21c or has standby/fallback environments not yet upgraded.
- ETL, BI/reporting tools, integrations, or drivers lack native SQL BOOLEAN support.
- External contracts expose `0/1`, `Y/N`, or status codes consumed by multiple partners.
- The field actually has more than two states and `NULL` carries distinct business meaning.
- Changing the schema requires touching many untested stored procedures, indexes, materialized views, jobs, or APIs.

In those cases, keeping the existing representation with clear constraints and mappings reduces risk. Using SQL BOOLEAN is a design choice, **not a mandatory refactor the instant a database is upgraded**.

## 10. Verifying Version and Actual Support

A landscape with multiple PDBs, environments, or drivers may not be uniform. Before executing SQL Boolean syntax, verify the target:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
```

Depending on privileges and environment, DBAs can check the database release from Oracle's instance/version views; authorized accounts can run:

```sql
-- Version/view data may require appropriate privileges.
SELECT banner_full
FROM v$version;
```

Do not grant broad catalog privileges to application accounts just to check version; in restricted environments, ask the DBA or read verified deployment configuration. You can inspect column type metadata after creation on a supported environment:

```sql
SELECT column_name, data_type, nullable
FROM user_tab_columns
WHERE table_name = 'LAB_FLAGS_BOOLEAN'
ORDER BY column_id;
```

On Oracle 23ai+, `ENABLED` in the sample table appears with datatype `BOOLEAN`. On 19c/21c, migrations using SQL Boolean fail during schema creation; **never cite a table existing on another database as proof that the target environment supports the feature**.

### 10.1. Separate Server, Driver, and Framework Verification

| Layer | What to Confirm |
|---|---|
| Oracle Database | Exact release, PDB/service, and whether SQL BOOLEAN is supported |
| Oracle JDBC/OCI client | Whether native Boolean binds/reads work, and how `NULL` behaves |
| ORM/dialect | Which SQL type `Boolean` maps to, and whether generated DDL matches the version |
| Migration tool | Whether scripts have version guards, migration ordering, and fallback paths |
| API/ETL/reporting | Whether numeric/char contracts or standard JSON Booleans are required |
| Runtime tests | Whether integration tests run directly against the target Oracle version, including nulls/edge cases |

Do not treat "unit tests pass on H2" as sufficient proof for Oracle SQL Boolean syntax, because test engines may support Boolean in ways older Oracle versions do not.

## 11. Practice Exercises for Both Version Groups

The exercises below use synthetic data in an **authorized DEV/TEST environment**. No `SYSDBA` account is needed. Learners need table-creation privileges in a lab schema and must verify the right PDB before running DDL.

### Lab A — Oracle 19c/21c: Boolean in PL/SQL, Numeric Flags in Tables

**Step 1.** Run three-valued PL/SQL:

```sql
SET SERVEROUTPUT ON;

DECLARE
    v_flag BOOLEAN := NULL;
BEGIN
    IF v_flag IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('PL/SQL BOOLEAN = UNKNOWN');
    ELSIF v_flag THEN
        DBMS_OUTPUT.PUT_LINE('PL/SQL BOOLEAN = TRUE');
    ELSE
        DBMS_OUTPUT.PUT_LINE('PL/SQL BOOLEAN = FALSE');
    END IF;
END;
/
```

**Step 2.** In your lab schema, store flags using `NUMBER(1)`:

```sql
CREATE TABLE lab_legacy_bool (
    id NUMBER PRIMARY KEY,
    is_valid NUMBER(1),
    CONSTRAINT ck_lab_legacy_bool CHECK (is_valid IN (0, 1))
);

INSERT INTO lab_legacy_bool VALUES (1, 1);
INSERT INTO lab_legacy_bool VALUES (2, 0);
INSERT INTO lab_legacy_bool VALUES (3, NULL);
COMMIT;
```

**Step 3.** Query data and convert to labels:

```sql
SELECT id,
       CASE
           WHEN is_valid = 1 THEN 'TRUE'
           WHEN is_valid = 0 THEN 'FALSE'
           ELSE 'UNKNOWN'
       END AS validity
FROM lab_legacy_bool
ORDER BY id;
```

Expected output for `id = 1, 2, 3` is `TRUE`, `FALSE`, `UNKNOWN`. These are **display strings**, not a native SQL `BOOLEAN` column. To understand version differences, **read the theory** on `BOOLEAN` DDL earlier; there is no need to run unsupported DDL on a shared environment just to provoke an error.

### Lab B — Oracle 23ai+: Store and Filter Booleans Directly

**Step 1.** Create a nullable lab table:

```sql
-- Use only when the database supports SQL BOOLEAN.
CREATE TABLE lab_native_bool (
    id NUMBER PRIMARY KEY,
    is_valid BOOLEAN
);

INSERT INTO lab_native_bool VALUES (1, TRUE);
INSERT INTO lab_native_bool VALUES (2, FALSE);
INSERT INTO lab_native_bool VALUES (3, NULL);
COMMIT;
```

**Step 2.** Query all three state groups:

```sql
SELECT id FROM lab_native_bool WHERE is_valid IS TRUE;
SELECT id FROM lab_native_bool WHERE is_valid IS FALSE;
SELECT id FROM lab_native_bool WHERE is_valid IS NULL;

SELECT id FROM lab_native_bool WHERE is_valid IS NOT TRUE;
```

The first three queries return `id = 1`, `id = 2`, and `id = 3` respectively. The last query returns `id = 2` and `id = 3`, because **"not TRUE"** includes both FALSE and NULL.

**Step 3.** Query the data dictionary to confirm the data type:

```sql
SELECT table_name, column_name, data_type, nullable
FROM user_tab_columns
WHERE table_name = 'LAB_NATIVE_BOOL'
ORDER BY column_id;
```

**Step 4.** Use SQL Boolean inside expressions:

```sql
SELECT id,
       (id > 1) AS id_greater_than_one,
       CASE
           WHEN is_valid IS TRUE THEN 'TRUE'
           WHEN is_valid IS FALSE THEN 'FALSE'
           ELSE 'UNKNOWN'
       END AS readable_status
FROM lab_native_bool
ORDER BY id;
```

Compare `id_greater_than_one` (SQL Boolean) against `readable_status` (`VARCHAR2` from `CASE`).

**Step 5.** Clean up only the lab objects you created, if permitted:

```sql
DROP TABLE lab_native_bool PURGE;
```

For Lab A, clean up `lab_legacy_bool` similarly within your privileges and scope. `DROP TABLE ... PURGE` deletes objects/data and issues an implicit DDL commit; **never run it on tables outside the lab**.

## 12. Common Errors and Misconceptions

| Misconception | Why It Is Wrong | How to Handle |
|---|---|---|
| "Oracle 19c supports Boolean because `DECLARE x BOOLEAN` works." | PL/SQL and SQL had separate type sets prior to 23ai. | Use PL/SQL Boolean only inside PL/SQL; store table flags as `NUMBER(1)`/`CHAR(1)` with constraints. |
| "SQL `WHERE amount > 0` proves SQL 19c has BOOLEAN." | Logical conditions in `WHERE` differ from standalone SQL Boolean column/expression types. | Distinguish *condition* from *datatype*. |
| "Java's driver has `setBoolean()`, so Oracle 19c can create a BOOLEAN column." | JDBC APIs and server-side SQL column storage are separate layers. | Verify DDL and mapping against the actual server. |
| "`NUMBER(1)` holds only 0 or 1." | NUMBER can store other digits without a domain constraint. | Add `CHECK (IN (0,1))`. |
| "`CHECK (flag IN (0,1))` automatically forbids NULL." | Check constraints do not replace `NOT NULL`. | Declare `NOT NULL` if the business has only two states. |
| "In PL/SQL, `NOT NULL` is TRUE." | Negating Boolean NULL still yields NULL. | Use `IS NULL` to detect unknown. |
| "`IS NOT TRUE` means the same as `IS FALSE`." | For nullable columns, `IS NOT TRUE` also includes NULL. | Pick the predicate matching business semantics. |
| "`getBoolean()` returning `false` guarantees the column holds FALSE." | JDBC can return `false` when SQL value is NULL. | Check `wasNull()` or use nullable `Boolean` wrapper APIs. |
| "Just alter `NUMBER(1)` to `BOOLEAN` right after server upgrade." | Clients, ORMs, reports, and migrations may still rely on 0/1. | Run expand/backfill/switch/contract and test end-to-end. |
| "`TO_BOOLEAN(2)` must error because 2 is not 1." | Oracle converts nonzero numbers to TRUE in SQL Boolean conversion. | Cleanse data and verify the 0/1 domain before converting. |
| "Enabling a JDBC flag makes SQL Boolean exist on Oracle 19c." | SQL column types are a server/database release capability. | Choose compatible baselines; never assume driver flags emulate column types. |
| "`NULL` and `FALSE` behave identically in WHERE." | Under 3VL, `NOT NULL` remains UNKNOWN. | Write `IS FALSE`, `IS NULL`, or `IS NOT TRUE` as required. |

### 12.1. Common Symptoms During Upgrades

- **`ORA-00902: invalid datatype`** when creating a `BOOLEAN` column on an unsupported release: first verify database version/service/PDB instead of renaming columns or escalating privileges.
- **SQL error when selecting literal `TRUE` on an older release:** using modern SQL Boolean syntax; replace with compatible expressions or plan an upgrade.
- **JDBC bind/conversion errors:** inspect driver version, target column type, how `BOOLEAN`/`NUMBER` is bound, and `NULL` handling; never assume Java `Boolean` automatically fits every SQL type.
- **App runs yet reports wrong flags:** verify `1/0`, `Y/N`, `TRUE/FALSE/NULL` mappings, converters, and `IS NOT TRUE` logic. Silent business bugs are more dangerous than syntax errors.
- **Migration fails only in production:** compare Oracle Database version, schema version, service/PDB, and migration path; TEST environments must mirror baselines closely enough to catch mismatches early.

## 13. Design Guide for Oracle Projects

**Case A — Application still runs on Oracle 19c LTS or 21c:** use `BOOLEAN` for PL/SQL logic, while storing table flags in `NUMBER(1)`/`CHAR(1)` with constraints. Centralize mapping in one contract so one module does not use `1/0` while another uses `'Y'/'N'`.

**Case B — New project targeting only Oracle 23ai/26ai with verified compatible drivers:** use native `BOOLEAN` columns when the business concept genuinely has two states or three states including `NULL`. Write `IS TRUE`/`IS FALSE`/`IS NULL` explicitly and test JDBC/ORM, APIs, and reports.

**Case C — Project supporting both Oracle 19c and 23ai simultaneously:** keep a shared storage representation supported by both versions, or separate and test version-specific migrations/dialects. Never ship a native `BOOLEAN` script to all environments if older databases remain in service.

**Case D — Data with multiple business statuses:** use an explicit status code with a clear domain (`PENDING`, `APPROVED`, `REJECTED`, ...), constraints, and a lookup table if appropriate. A Boolean cannot naturally represent four or five states; never overload `NULL` to hide extra meanings.

**Case E — Java API accepting/returning `Boolean`:** distinguish `boolean` from `Boolean`, handle `NULL`/missing fields in the API contract, and verify converters and actual SQL types. Never let a property name like `isActive` dictate database datatype or default value implicitly.

## 14. Self-Check Questions

**Question 1.** On Oracle 19c, `DECLARE v_ok BOOLEAN := TRUE; BEGIN NULL; END;` runs cleanly. Can you create a column `is_ok BOOLEAN`?

**Answer:** No. That is PL/SQL `BOOLEAN`; Oracle 19c lacks a native SQL `BOOLEAN` column type.

**Question 2.** An `enabled NUMBER(1)` column is assigned `2`. Why can that still happen if only `NUMBER(1)` is declared?

**Answer:** Because the numeric type alone does not restrict values to 0/1; add `CHECK (enabled IN (0,1))` to enforce the Boolean convention and `NOT NULL` if UNKNOWN is disallowed.

**Question 3.** In PL/SQL, a `BOOLEAN` variable is `NULL`. Does `IF NOT v_flag THEN` enter the THEN branch?

**Answer:** No. `NOT NULL` remains `NULL`, and `IF` enters THEN only when the expression evaluates to `TRUE`.

**Question 4.** In Oracle 23ai SQL, `flag` can hold `TRUE`, `FALSE`, or `NULL`. Which states does `WHERE flag IS NOT TRUE` select?

**Answer:** `FALSE` and `NULL`. It differs from `WHERE flag IS FALSE`.

**Question 5.** Java calls `ResultSet.getBoolean()` and receives `false`. Can you conclude the column holds SQL FALSE?

**Answer:** Not yet. Call `wasNull()` or use a nullable `Boolean` API to check whether the database value was `NULL`.

**Question 6.** Oracle 23ai supports SQL BOOLEAN. Should you convert every existing `'Y'/'N'` column to `BOOLEAN` in a single release?

**Answer:** No. Evaluate clients/drivers, ORMs, stored procedures, reports, data quality, and compatibility paths, then execute a tested migration.

**Question 7.** Does `SELECT CASE WHEN amount > 0 THEN 1 ELSE 0 END AS positive FROM orders` mean SQL 19c returns a Boolean?

**Answer:** No. The expression returns `NUMBER` per `THEN`/`ELSE`, even though the `WHEN` condition evaluates true/false logic.

**Question 8.** Legacy data contains `0`, `1`, `2`, `NULL`. Can you call `TO_BOOLEAN` on the column and guarantee the original 0/1 convention is preserved?

**Answer:** No. On Oracle releases with SQL BOOLEAN, nonzero numbers can convert to `TRUE`; detect `2`, decide a cleansing policy first, and only then convert.

## Conclusion

**Prior to Oracle 23c/23ai, `BOOLEAN` was supported in PL/SQL but was not a SQL datatype for storing columns. Starting in Oracle 23c/23ai, SQL natively supports `BOOLEAN`**, allowing Boolean columns, `TRUE`/`FALSE` literals, Boolean expressions, and smoother SQL/PLSQL interoperability. **`NULL` remains a third state**, requiring explicit handling in SQL filters, PL/SQL branches, and Java/JDBC mappings.

When designing Oracle systems, decide flag representation from the **actual database release, verified drivers/ORMs, and business data meaning**. On 19c/21c, use `NUMBER(1)` or `CHAR(1)` with clear constraints and converters; on 23ai+, you can adopt SQL `BOOLEAN` once the entire ecosystem is ready. That approach prevents migration failures, silent `NULL`/`FALSE` bugs, and behavior drift across DEV, TEST, and production.

## Oracle Documentation by Version

- [Oracle Database 19c — PL/SQL `BOOLEAN` Data Type](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/boolean-data-type.html): PL/SQL Boolean mechanics and SQL interoperability limits prior to 23ai.
- [Oracle Database 23ai — Explore SQL Features](https://docs.oracle.com/en/learn/db23ai-sql-features/): examples of `BOOLEAN` as a SQL data type.
- [Oracle Database 23ai — SQL Boolean Expressions](https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/boolean-expressions.html): Boolean expressions and conditions in SQL.
- [Oracle AI Database 26ai — SQL Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Data-Types.html): SQL Boolean values, logical operations, and conversion rules.
- [Oracle JDBC — Accessing and Manipulating Oracle Data](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/accessing-and-manipulating-Oracle-data.html): JDBC mapping and notes for native Boolean in newer driver/database releases.
