# Handling Explicit `null` and Default Values with Special Data Types in Spring JDBC

## 1. Why Is This Problem Error-Prone?

When accessing a database through Spring JDBC, developers often need to express three distinct intentions:

1. **Supply no value** so the database applies `DEFAULT`.
2. **Explicitly store SQL `NULL`** (unknown, absent, or clearing an existing value per business rules).
3. **Store a real but empty value**, such as the string `""`, array `[]`, JSON object `{}`, or JSON value `null`.

These three intentions **are not equivalent**. Especially with `UUID`, `JSON/JSONB`, `ARRAY`, `ENUM`, LOBs, or custom types, passing Java `null` without describing the SQL type can prevent the driver from determining the parameter type. Moreover, passing `null` into a column with `DEFAULT` **does not trigger** the default value.

This lesson focuses on Spring JDBC (`JdbcTemplate`, `NamedParameterJdbcTemplate`, `MapSqlParameterSource`, and `PreparedStatement`) alongside SQL rules. Concrete examples use **PostgreSQL**, Java 17, and Spring Framework 6.x; the general principles apply across JDBC, though special types and binding differ in MySQL, Oracle, or SQL Server.

## 2. Separating Value States

| Desired State | Typical Value/SQL | Stored Data or Behavior |
| --- | --- | --- |
| Column **omitted** on `INSERT` | Omit column from `INSERT` column list | Uses `DEFAULT` if declared; otherwise typically SQL `NULL` |
| Request using default | `DEFAULT` keyword in SQL | DBMS evaluates the schema default value |
| Explicitly store SQL `NULL` | `SET column = NULL` or bind typed SQL null parameter | Stores SQL `NULL` (errors if column is `NOT NULL`) |
| Empty string | `''` (PostgreSQL) | Zero-length string, **not** SQL `NULL` |
| Empty PostgreSQL array | `ARRAY[]::text[]` | Zero-element array, distinct from SQL `NULL` |
| Empty JSON object | `'{}'::jsonb` | JSON value representing an empty object |
| JSON literal `null` | `'null'::jsonb` | **A JSON value**, not SQL `NULL` |
| Leave column unchanged in `UPDATE` | Omit column from `SET` clause | Keeps current value |

Example with a `payload jsonb` column:

```sql
-- SQL NULL value: the column has no SQL value.
SELECT NULL::jsonb IS NULL;           -- true

-- JSON null value is still a jsonb value.
SELECT 'null'::jsonb IS NULL;         -- false
SELECT jsonb_typeof('null'::jsonb);   -- string 'null'

-- Empty JSON object is also not SQL NULL.
SELECT '{}'::jsonb IS NULL;           -- false
SELECT jsonb_typeof('{}'::jsonb);     -- string 'object'
```

Thus, checking for JSON `null` with `column IS NULL` is insufficient. Conversely, if `payload` is SQL `NULL`, `jsonb_typeof(payload)` also yields SQL `NULL`, not the string `"null"`. At the Java layer, `String json = "null"` contains four characters, whereas `String json = null` points to no string at all.

### Java `null` Does Not Express Business Intent on Its Own

A DTO field `tags = null` could mean any of three things: not sent, delete/clear, or use default. Looking at `null` alone **cannot distinguish** them. An API contract should define clearly:

- **Absent**: field omitted from the request → keep unchanged on update; or let the database apply its default on creation.
- **Present with null**: field present with value null → store SQL `NULL` or perform a clear action per design.
- **Present with value**: field present with data, including `[]`/`{}` → store that exact value.

For PATCH requests, you can model the state with a `provided` flag plus value, or a wrapper type distinguishing "absent" from "present but null". Do not use `Optional.ofNullable(...)` **alone** for PATCH because `Optional.empty()` collapses the difference between an omitted field and one explicitly sent as null.

## 3. Declaring Defaults Properly in the Schema

Using a PostgreSQL table to illustrate multiple special types:

```sql
CREATE TABLE demo_null_defaults (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_ref  UUID NULL,
    payload       JSONB NULL,
    labels        TEXT[] DEFAULT ARRAY[]::TEXT[],
    status        VARCHAR(16) NOT NULL DEFAULT 'DRAFT',
    attempts      INTEGER NOT NULL DEFAULT 0,
    optional_limit INTEGER NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

`labels` defaults to an **empty array**, yet still permits SQL `NULL` because it has no `NOT NULL` constraint. `status` and `attempts` have both defaults and `NOT NULL`: passing SQL `NULL` directly into these two columns is rejected rather than replaced with the default.

The inserts below demonstrate four states:

```sql
-- A. No columns specified: use all defaults.
INSERT INTO demo_null_defaults DEFAULT VALUES;

-- B. Explicit SQL NULL: labels' default is NOT applied.
INSERT INTO demo_null_defaults (payload, labels)
VALUES (NULL, NULL);

-- C. JSON null; labels uses DEFAULT via the SQL keyword.
INSERT INTO demo_null_defaults (payload, labels)
VALUES ('null'::jsonb, DEFAULT);

-- D. JSON object and empty array are real values.
INSERT INTO demo_null_defaults (payload, labels)
VALUES ('{}'::jsonb, ARRAY[]::text[]);
```

To inspect the different states:

```sql
SELECT id,
       status,
       attempts,
       labels IS NULL AS labels_sql_null,
       cardinality(labels) AS label_count,
       payload IS NULL AS payload_sql_null,
       jsonb_typeof(payload) AS payload_json_type
FROM demo_null_defaults
ORDER BY id;
```

If the table was just created and those exact four inserts ran, the observable attributes are (specific IDs depend on the sequence):

| Row | `status` | `attempts` | `labels_sql_null` | `label_count` | `payload_sql_null` | `payload_json_type` |
| --- | --- | ---: | --- | ---: | --- | --- |
| A | `DRAFT` | 0 | `false` | 0 | `true` | SQL `NULL` |
| B | `DRAFT` | 0 | `true` | SQL `NULL` | `true` | SQL `NULL` |
| C | `DRAFT` | 0 | `false` | 0 | `false` | `null` (JSON type string) |
| D | `DRAFT` | 0 | `false` | 0 | `false` | `object` |

**Rule:** When you want a column's default on `INSERT`, **omit the column** from the insert list or write `DEFAULT` in SQL. You cannot use `?` or `:parameter` to pass the SQL keyword `DEFAULT` as if it were data. `PreparedStatement` binds *values*; it does not alter SQL statement structure.

## 4. Binding Explicit SQL `NULL` via Spring JDBC

### 4.1. `JdbcTemplate` with an `int[]` Type Array

Spring usually infers SQL type from the Java value. Java `null` has no runtime type, so the safe approach is **declaring the type matching the target column**. Example updating `JSONB` in PostgreSQL combined with a SQL cast:

```java
// Fragment in a repository with JdbcTemplate jdbc and long id.
String sql = """
        UPDATE demo_null_defaults
        SET payload = CAST(? AS jsonb)
        WHERE id = ?
        """;

int changed = jdbc.update(
        sql,
        new Object[] {null, id},
        new int[] {Types.VARCHAR, Types.BIGINT}
);
```

Here:

- Parameter 1 is **SQL `NULL`** with JDBC type `VARCHAR`, and PostgreSQL then receives the explicit target type from `CAST(? AS jsonb)`.
- Parameter 2 is `BIGINT` for column `id`.
- `changed` is the number of updated rows, not the ID; if row `id` does not exist, it may be 0.
- To store **JSON literal null**, replace the first input with the string `"null"`; to store an empty object, pass `"{}"`.

`Types.VARCHAR` + `CAST(... AS jsonb)` is a **PostgreSQL-specific strategy** for valid JSON strings, not a universal mapping rule for all DBMSs. When binding a driver-specific PostgreSQL `jsonb` object directly, `Types.OTHER` or `PGobject` may be required.

### 4.2. `NamedParameterJdbcTemplate` and `MapSqlParameterSource`

Named parameters help avoid positional mix-ups:

```java
// Fragment: assumes NamedParameterJdbcTemplate namedJdbc already exists.
String sql = """
        UPDATE demo_null_defaults
        SET payload = CAST(:payload AS jsonb),
            external_ref = :ref
        WHERE id = :id
        """;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("payload", null, Types.VARCHAR)
        .addValue("ref", null, Types.OTHER)
        .addValue("id", 42L, Types.BIGINT);

int changed = namedJdbc.update(sql, params);
```

- `Types.OTHER` is commonly used with PostgreSQL `UUID` and many special types; verify driver behavior for the actual type.
- `MapSqlParameterSource.addValue(name, value, sqlType)` stores **value + JDBC type metadata**. `value = null` still needs an explicit type when the driver requires it.
- For non-null `UUID`, pgJDBC can bind `java.util.UUID` via `PreparedStatement.setObject(...)`. Do not blindly coerce all special types to `VARCHAR`.
- `:payload` and `:ref` are *named parameters*, whereas `DEFAULT` is SQL syntax. If you need `SET status = DEFAULT`, write `DEFAULT` directly in the static SQL.

In SQL using named parameters, prefer `CAST(:payload AS jsonb)` over `:payload::jsonb` to avoid ambiguity with parameter parser syntax.

### 4.3. `SqlParameterValue` When Only One Parameter Needs a Specific Type

```java
// Fragment: requires imports and repository variables jdbc/id.
int changed = jdbc.update(
        "UPDATE demo_null_defaults SET payload = CAST(? AS jsonb) WHERE id = ?",
        new SqlParameterValue(Types.VARCHAR, null),
        id
);
```

`SqlParameterValue` carries the SQL type and value for **one** placeholder. When several nullable values appear together, an `int[]` array or `MapSqlParameterSource` is usually easier to manage.

### 4.4. `PreparedStatement.setNull` for `ARRAY` and Driver-Specific Types

For a PostgreSQL `TEXT[]` column, use `java.sql.Array` for populated arrays and bind null with an explicit type:

```java
// Fragment inside a PreparedStatementSetter/ConnectionCallback.
// ps points to an INSERT or UPDATE whose 1st placeholder is type text[].
String[] values = {"java", "spring"};
java.sql.Array array = ps.getConnection().createArrayOf("text", values);
try {
    ps.setArray(1, array);              // array with two elements
} finally {
    array.free();                        // free the SQL Array object
}

// If explicitly storing SQL NULL:
ps.setNull(1, Types.ARRAY);
```

The two assignments in this fragment show **two mutually exclusive alternatives**, not a sequence to run back-to-back on a single statement. Keep the `Array` object alive until the driver has finished using it to execute; in practice you normally free it **after `execute`**, not right after `setArray` before execution. The complete example later uses only `setNull`.

`ps.setNull(index, Types.ARRAY)` differs from `ps.setArray(index, emptyArray)`. Depending on the driver, the array element type may need to be inferred from SQL (`CAST(? AS text[])`) or registered via a vendor type name. Do not treat `Types.NULL` as a universal answer for all SQL types; and never confuse `null` with an empty array.

### Choosing Explicit SQL Types

| Target Column | Common Java Value | Null-Binding Approach |
| --- | --- | --- |
| `VARCHAR/TEXT` | `String` | `Types.VARCHAR` |
| Nullable `INTEGER` | `Integer` | `Types.INTEGER` |
| Nullable `BIGINT` | `Long` | `Types.BIGINT` |
| `NUMERIC/DECIMAL` | `BigDecimal` | `Types.NUMERIC` or `Types.DECIMAL` |
| PostgreSQL `UUID` | `UUID` | Usually `Types.OTHER` or typed SQL cast |
| PostgreSQL `JSONB` | Valid JSON string or `PGobject` | Cast from `VARCHAR` string or handle `OTHER` per driver |
| PostgreSQL `TEXT[]` | `java.sql.Array` | `Types.ARRAY`; specify element type when needed |
| `TIMESTAMPTZ` | `OffsetDateTime` | Check `Types.TIMESTAMP_WITH_TIMEZONE` and driver support |
| `BLOB/CLOB` | Bytes/stream/reader | `Types.BLOB`/`Types.CLOB` and appropriate LOB APIs |

The table above is **guidance**, not a guarantee that every database uses the same SQL type codes. For `ENUM`, `STRUCT`, `ARRAY`, `JSON`, spatial types, or user-defined types, read the official documentation of your driver and test both **populated** and **SQL NULL** cases.

## 5. Runnable Java 17+ Program: Distinguishing DEFAULT, SQL NULL, and JSON null

This example uses PostgreSQL (with `JSONB` and `TEXT[]` types) and Spring JDBC. It inserts four separate rows and prints their states; it does not modify or delete existing data. Before running, execute the `CREATE TABLE` from Section 3 on a test database.

### 5.1. Maven (`pom.xml`)

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>explicit-null-defaults</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <version>42.7.8</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

These are illustrative dependency versions. In a Spring Boot project, follow the synchronized BOM version management. Requires JDK 17+, Maven, and an accessible PostgreSQL instance.

### 5.2. File `src/main/java/ExplicitNullDefaultDemo.java`

```java
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class ExplicitNullDefaultDemo {

    private ExplicitNullDefaultDemo() {}

    // Returns a state snapshot without losing SQL NULL from cardinality().
    private record State(
            String status,
            int attempts,
            boolean labelsSqlNull,
            Integer labelCount,
            boolean payloadSqlNull,
            String jsonType
    ) {}

    public static void main(String[] args) {
        var ds = new DriverManagerDataSource(
                requireEnv("DB_URL"),
                requireEnv("DB_USER"),
                requireEnv("DB_PASSWORD")
        );
        var jdbc = new JdbcTemplate(ds);

        long defaultsId = insertUsingDefaults(jdbc);
        long sqlNullId = insertTypedSqlNull(jdbc);
        long jsonNullId = insertJsonValue(jdbc, "'null'::jsonb");
        long emptyObjectId = insertJsonValue(jdbc, "'{}'::jsonb");

        print("DEFAULT", read(jdbc, defaultsId));
        print("SQL NULL", read(jdbc, sqlNullId));
        print("JSON null", read(jdbc, jsonNullId));
        print("JSON object", read(jdbc, emptyObjectId));
    }

    private static long insertUsingDefaults(JdbcTemplate jdbc) {
        Long id = jdbc.queryForObject(
                "INSERT INTO demo_null_defaults DEFAULT VALUES RETURNING id",
                Long.class);
        return Objects.requireNonNull(id);
    }

    private static long insertTypedSqlNull(JdbcTemplate jdbc) {
        // Plain JDBC fragment inside Spring's ConnectionCallback.
        // For special columns, CAST in SQL helps establish target types.
        Long id = jdbc.execute((ConnectionCallback<Long>) connection -> {
            String sql = """
                    INSERT INTO demo_null_defaults
                        (external_ref, payload, labels)
                    VALUES (?, CAST(? AS jsonb), CAST(? AS text[]))
                    RETURNING id
                    """;
            try (PreparedStatement ps = connection.prepareStatement(sql)) {
                ps.setNull(1, Types.OTHER);    // PostgreSQL UUID
                ps.setNull(2, Types.VARCHAR);  // SQL NULL -> jsonb
                ps.setNull(3, Types.ARRAY);    // SQL NULL -> text[]

                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("INSERT did not return id");
                    }
                    return rs.getLong(1);
                }
            }
        });
        return Objects.requireNonNull(id);
    }

    private static long insertJsonValue(JdbcTemplate jdbc, String literal) {
        // Only accepts the two fixed SQL expressions of this example; never
        // pass SQL strings from user input into this method.
        if (!literal.equals("'null'::jsonb")
                && !literal.equals("'{}'::jsonb")) {
            throw new IllegalArgumentException("Invalid demo literal");
        }
        String sql = "INSERT INTO demo_null_defaults (payload) VALUES ("
                + literal + ") RETURNING id";
        Long id = jdbc.queryForObject(sql, Long.class);
        return Objects.requireNonNull(id);
    }

    private static State read(JdbcTemplate jdbc, long id) {
        String sql = """
                SELECT status, attempts,
                       labels IS NULL AS labels_sql_null,
                       cardinality(labels) AS label_count,
                       payload IS NULL AS payload_sql_null,
                       jsonb_typeof(payload) AS json_type
                  FROM demo_null_defaults
                 WHERE id = ?
                """;
        return Objects.requireNonNull(jdbc.queryForObject(
                sql,
                (rs, rowNum) -> new State(
                        rs.getString("status"),
                        rs.getInt("attempts"),
                        rs.getBoolean("labels_sql_null"),
                        rs.getObject("label_count", Integer.class),
                        rs.getBoolean("payload_sql_null"),
                        rs.getString("json_type")),
                id));
    }

    private static void print(String label, State value) {
        String type = value.jsonType() == null
                ? "(SQL NULL)" : value.jsonType();

        System.out.printf(
                "%s: status=%s; attempts=%d; labelsSQLNull=%s; "
                + "labelCount=%s; payloadSQLNull=%s; jsonType=%s%n",
                label,
                value.status(),
                value.attempts(),
                value.labelsSqlNull(),
                value.labelCount(),
                value.payloadSqlNull(),
                type
        );
    }

    private static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing environment variable: " + key);
        }
        return value;
    }
}
```

**Why does this code match the lesson's intent?**

- `insertUsingDefaults` supplies no values for any column; PostgreSQL applies `DEFAULT` for `labels`, `status`, `attempts`, and `created_at`.
- `insertTypedSqlNull` intentionally binds `NULL` for three columns, including `labels` which has a default. `labels`'s default is **not used**.
- `insertJsonValue(..., "'null'::jsonb")` stores **JSON null** as a `jsonb` value. `insertJsonValue(..., "'{}'::jsonb")` stores an empty JSON object.
- `read(...)` reads `label_count` with `getObject(..., Integer.class)` to preserve Java `null` when `cardinality(labels)` returns SQL `NULL`. `getInt(...)` would return `0` for SQL `NULL` and would require `wasNull()` on nullable columns.
- The SQL constructed from `literal` in the example permits only **two fixed literals checked against an allowlist**. In real apps, use bind parameters (`?` or `:name`), never concatenate user data into SQL.

### 5.3. Running the Program

Create the table using the SQL in Section 3, then in a Bash terminal configure connection details to your test database:

```bash
export DB_URL="jdbc:postgresql://localhost:5432/demo"
export DB_USER="demo_user"
export DB_PASSWORD="your_password"

mvn -q compile exec:java -Dexec.mainClass=ExplicitNullDefaultDemo
```

Replace `demo` and credentials with your existing database. With a freshly created schema and working driver, stdout from **the Java program** (excluding Maven logs) is:

```text
DEFAULT: status=DRAFT; attempts=0; labelsSQLNull=false; labelCount=0; payloadSQLNull=true; jsonType=(SQL NULL)
SQL NULL: status=DRAFT; attempts=0; labelsSQLNull=true; labelCount=null; payloadSQLNull=true; jsonType=(SQL NULL)
JSON null: status=DRAFT; attempts=0; labelsSQLNull=false; labelCount=0; payloadSQLNull=false; jsonType=null
JSON object: status=DRAFT; attempts=0; labelsSQLNull=false; labelCount=0; payloadSQLNull=false; jsonType=object
```

Results follow directly from the `INSERT ... RETURNING` statements and SQL checks; the program requires a real PostgreSQL instance to run. If the table already holds rows, the program still inserts four new rows and reads only the newly returned IDs, so expected values for the four lines remain unchanged. It does not drop or `TRUNCATE` existing data.

## 6. Default Values Across Layers and During Updates

A system typically has at least four layers where defaults may be defined:

1. **Database schema:** `DEFAULT 'DRAFT'`, `DEFAULT CURRENT_TIMESTAMP`, `DEFAULT ARRAY[]::text[]`; DBMS applies these when values are omitted or `DEFAULT` is written.
2. **Repository SQL:** `COALESCE(:x, value)`, `CASE ...`, `UPDATE ... SET column = DEFAULT`; rules written into SQL statements.
3. **Java service:** computes fallbacks via `Objects.requireNonNullElse(...)` or null checks before calling the repository.
4. **API contract/DTO:** default values for fields omitted from requests.

Each layer has different semantics and execution timing. **Generating a Java fallback value and binding it** means the DBMS receives **an explicit value**, rather than applying DEFAULT itself. Expression defaults (`CURRENT_TIMESTAMP`, sequences, custom functions) should be left to the DBMS when write-time consistency matters.

### UPDATE: Keep Unchanged, Clear, or Reset to DEFAULT?

```sql
-- Keep labels unchanged: omit the column.
UPDATE demo_null_defaults
SET status = 'READY'
WHERE id = 10;

-- Clear labels to SQL NULL.
UPDATE demo_null_defaults
SET labels = NULL
WHERE id = 10;

-- Reset labels to its default (empty array).
UPDATE demo_null_defaults
SET labels = DEFAULT
WHERE id = 10;

-- Clear JSONB value, distinct from JSON literal null.
UPDATE demo_null_defaults
SET payload = NULL
WHERE id = 10;

-- Store JSON null; payload remains IS NOT NULL.
UPDATE demo_null_defaults
SET payload = 'null'::jsonb
WHERE id = 10;
```

IDs are illustrative: if no row has `id = 10`, `UPDATE` modifies zero rows. `DEFAULT` in `UPDATE` is PostgreSQL-supported column syntax, not a bindable parameter.

### `COALESCE` Can Mask "Clear Data" Intent

```sql
-- If :payload receives SQL NULL, this KEEPS the old payload.
UPDATE demo_null_defaults
SET payload = COALESCE(CAST(:payload AS jsonb), payload)
WHERE id = :id;
```

This expression is appropriate **only when** business rules state "null means keep existing". It **cannot be used** to represent "null means clear". When building PATCH APIs, distinguish:

| Request State | Appropriate SQL |
| --- | --- |
| `payload` field absent | Do not include `payload` in `SET` |
| `payload: null` present, meaning clear | `SET payload = NULL` |
| `payload: {}` present | `SET payload = CAST(? AS jsonb)`, bind `"{}"` |
| Reset `labels` to default | `SET labels = DEFAULT` |

When SQL must vary with the list of updated columns, **only assemble column names predefined in code** and bind values via `PreparedStatement`. Never accept arbitrary column names or SQL expressions from requests to prevent SQL injection.

## 7. Reading Null Safely in the Java Layer

### Nullable Numeric Values

`ResultSet.getInt(...)` returns `0` when the SQL value is `NULL`. You must check `wasNull()` **immediately after reading** to distinguish SQL `NULL` from 0:

```java
// Fragment inside RowMapper, assuming ResultSet rs has optional_limit.
int raw = rs.getInt("optional_limit");
Integer limit = rs.wasNull() ? null : raw;
```

When the driver supports JDBC 4.1 conversions, the shorter form is:

```java
// Preserves Java null if optional_limit is SQL NULL.
Integer limit = rs.getObject("optional_limit", Integer.class);
```

`getInt`, `getLong`, and `getBoolean` are primitive-returning getters, so watch out for the same confusion. In Spring JDBC, `RowMapper` should return DTOs with wrapper fields `Integer`/`Long`/`Boolean` when data can be SQL NULL; never default null to `0` or `false` unless business rules demand it.

### JSON Strings, SQL Arrays, and Vendor Objects

- `rs.getString("payload")` on PostgreSQL may return JSON text; SQL `NULL` is normally returned as Java `null`, whereas JSON literal `null` may be the string `"null"`. To decide reliably, also select `payload IS NULL` or use dedicated JSON type/parsing.
- `rs.getArray("labels")` returns `java.sql.Array` or Java `null`. Only call `getArray()` on the SQL Array object when non-null; a 0-element array is entirely different from SQL NULL.
- `rs.getObject("external_ref", java.util.UUID.class)` works on drivers supporting PostgreSQL UUID mapping. Test vendor-specific types; returned objects are not guaranteed to be the same Java class across all DBMSs.
- You can use `COALESCE` in read queries, e.g., `COALESCE(optional_limit, 5)`, when you **genuinely want** a read-time fallback. That discards whether the DB stored null or 5; unsuitable when the original state carries meaning.

## 8. Special Cases: LOB, ARRAY, UUID, and JSON

### BLOB/CLOB

An empty binary field (`byte[0]`) differs from SQL `NULL`. An empty string for CLOB can follow DBMS-specific rules (Oracle has well-known quirks with empty strings). For large data, use JDBC APIs (`setBinaryStream`/`setCharacterStream`) or Spring's `LobHandler` per driver support. Never treat `new byte[0]` as "default null" if the DB/schema distinguishes the two.

### ARRAY

`createArrayOf("text", elements)` produces a populated `text[]`, while `ARRAY[]::text[]` is an empty array **with an explicit type**. In PostgreSQL, an empty array must have an element type; not every context can infer the type from an uncast `ARRAY[]`. `cardinality(NULL::text[])` is SQL `NULL`, whereas `cardinality(ARRAY[]::text[])` is 0.

### UUID

`java.util.UUID` carries a specific value-domain type; never substitute `""` when SQL NULL is intended. With pgJDBC, `Types.OTHER`/`setObject(UUID)` usually fits, yet when nullable ensure SQL provides `UUID` context or an explicit cast. Ambiguous queries like `WHERE ? IS NULL` can fail with "could not determine data type of parameter"; use an explicit SQL type such as `CAST(? AS uuid) IS NULL` when needed.

### JSON/JSONB

JSON object `{}`, array `[]`, empty string `""`, and literal `null` are **four distinct JSON values**, and all four differ from SQL `NULL`. Do not use a single `payload IS NULL` check to classify all of them. When updating a sub-field inside JSON, PostgreSQL provides dedicated JSON functions/operators; treat "remove key", "set key to JSON null", and "clear entire column" as three separate actions.

## 9. Common Errors, Testing, and Design Principles

| Error | Consequence | Resolution |
| --- | --- | --- |
| Thinking Java `null` triggers `DEFAULT` | Stores SQL NULL or raises `NOT NULL` error | Omit column on INSERT or write `DEFAULT` |
| Using `Types.NULL`/`Types.OTHER` indiscriminately | Driver may fail to determine type | Choose type per schema, cast where appropriate, test driver |
| Coercing `null` to `""`, `[]`, `{}` by default | Loses distinction between "absent" and "empty" | Convert only when business rules require |
| Confusing JSON `null` with SQL `NULL` | Broken IS NULL checks and wrong branches | Use `IS NULL` and `jsonb_typeof` appropriately |
| Reading nullable numbers with `getInt` without `wasNull` | NULL silently becomes 0 | Use `getObject(..., Integer.class)` or `wasNull` |
| Using `COALESCE` in PATCH meant to clear fields | Cannot turn an existing value into null | Distinguish absent request fields from explicit nulls |
| Passing `DEFAULT` as a string parameter | Stores a literal string or causes type error | `DEFAULT` must be controlled SQL syntax |
| Building SQL by concatenating JSON from requests | SQL injection, escaping bugs | Use bind parameters; apply SQL casts |
| Treating Java defaults as DB defaults | Time/value drift across write paths | Pick one authoritative default layer and document clearly |
| Passing SQL NULL to a `NOT NULL` column | Constraint violation | Validate upfront, let DB guard bad data |
| Assuming all DBs support `JSONB` and `TEXT[]` | SQL fails on other DBMSs | Choose SQL, JDBC types, and mappers per DBMS |

### Practical Testing Checklist

1. Inspect **actual schema**: `NULL/NOT NULL`, `DEFAULT`, `UUID/JSON/ARRAY` types, numeric and temporal scale.
2. Test all four cases: omitted field, explicit null, empty value, and normal value; add JSON literal `null` when using JSONB.
3. After `INSERT/UPDATE`, run `SELECT` to verify stored values directly (not just affected row counts); for JSON also check `jsonb_typeof` and `IS NULL`.
4. Test PATCH DTOs for **absent/present-null/present-value** and align API contracts with persistence policies.
5. Measure performance when binding many nulls in large batches if the driver frequently queries `ParameterMetaData` to infer types. In some Spring versions/configs, explicit SQL types avoid errors or metadata overhead; verify actual gains on the real driver.
6. Test rollback/transactions for critical multi-step updates; SQL defaults and null binding do not automatically make a batch atomic.
7. For PostgreSQL arrays/JSON/UUID, test exact driver versions, SQL casts, mappers, and real null values before deploying to production.

### Key Rule to Remember

**Supplying no value, explicitly storing SQL NULL, and using a default value are three separate choices.** Define the intent at the API/service layer, pick SQL that reflects that intent, declare explicit JDBC types for special null parameters, and preserve the distinction between SQL NULL and empty strings/arrays/JSON when reading back.

## Official References

- [Spring Framework – Providing SQL Type Information for Parameters](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): `int[] argTypes`, `SqlParameterValue`, `MapSqlParameterSource`, and special types.
- [Spring Framework – JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `update`, `queryForObject`, `execute`, and `RowMapper`.
- [PostgreSQL – Default Values](https://www.postgresql.org/docs/current/ddl-default.html): omitted columns on insert, schema defaults, and default expressions.
- [PostgreSQL – INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `DEFAULT VALUES`, `DEFAULT` in values lists, `RETURNING`.
- [PostgreSQL – JSON Types](https://www.postgresql.org/docs/current/datatype-json.html): distinguishing JSON `null` from SQL `NULL`.
- [PostgreSQL – Arrays](https://www.postgresql.org/docs/current/arrays.html): `ARRAY` syntax and empty arrays.
- [pgJDBC – JDBC driver documentation](https://jdbc.postgresql.org/documentation/): binding `UUID`, `ARRAY`, and vendor-specific data.
