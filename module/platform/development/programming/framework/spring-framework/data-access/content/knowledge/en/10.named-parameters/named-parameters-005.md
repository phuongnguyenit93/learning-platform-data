# Using Map and Type Inference Limits with Null Values

## Objectives and Context

In Spring JDBC, `NamedParameterJdbcTemplate` lets you write SQL with **named parameters** such as `:id`, `:nickname`, or `:minScore` instead of counting `?` markers. The simplest way to pass values is a `Map<String, ?>`:

```java
String sql = """
        SELECT id, display_name
        FROM contacts
        WHERE tenant_id = :tenantId AND score >= :minScore
        ORDER BY id
        """;

Map<String, Object> params = Map.of(
        "tenantId", 7L,
        "minScore", 50
);

List<Contact> contacts = namedJdbc.query(sql, params, CONTACT_MAPPER);
```

This snippet is **illustrative**, assuming `namedJdbc`, `CONTACT_MAPPER`, and `Contact` are declared elsewhere. For non-null values and simple data types, passing a `Map` is usually concise and sufficient.

However, there is an important distinction between:

- **Key present in the Map with a `null` value**;
- **Key missing from the Map**;
- **Having a `null` value while explicitly declaring which SQL type it belongs to**.

When a value is `null`, the Java `null` reference itself **carries no type information** for JDBC to infer reliably. That is the exact limitation this lesson explains.

After this lesson, you will be able to:

1. Use `Map<String, ?>` with `NamedParameterJdbcTemplate` for simple parameters.
2. Distinguish the behavior of `Map.of(...)`, `HashMap`, and `MapSqlParameterSource` with `null` values.
3. Understand why a plain `Map` usually **provides no explicit SQL type**, and why binding null can depend on metadata, the driver, or the DBMS.
4. Use `MapSqlParameterSource.addValue(name, value, sqlType)` to pass `null` with the proper type such as `Types.VARCHAR` or `Types.INTEGER`.
5. Distinguish **binding null** from **SQL `IS NULL` logic**; avoid misinterpreting `column = NULL`.
6. Write, run, and verify a Java 17+ example using Spring JDBC + H2, including a Map with null, a typed null parameter, and returned SQL data.
7. Choose appropriate strategies for optional filters, `IN` lists, and multi-parameter queries.

**Scope:** This lesson belongs to the *Named Parameters* group in Spring Framework data access. It focuses on passing parameter values—especially `null`—without going deep into full entity mapping, distributed transactions, or connection pool tuning.

## 1. From Question Marks `?` to Named Parameters

With `JdbcTemplate`, SQL typically uses positional placeholders:

```sql
SELECT id, display_name
FROM contacts
WHERE tenant_id = ? AND score >= ?;
```

When calling it, arguments must follow the **exact order**:

```java
jdbc.query(sql, CONTACT_MAPPER, tenantId, minScore);
```

With `NamedParameterJdbcTemplate`, the same intent can be written as:

```sql
SELECT id, display_name
FROM contacts
WHERE tenant_id = :tenantId AND score >= :minScore;
```

and supplying matching names:

```java
Map<String, Object> params = Map.of(
        "tenantId", tenantId,
        "minScore", minScore
);

namedJdbc.query(sql, params, CONTACT_MAPPER);
```

These snippets only illustrate API usage and assume the corresponding variables already exist.

Internally, Spring parses SQL containing `:tenantId` and `:minScore`, converts them into the appropriate JDBC parameter markers, and binds each value. Named parameters are **syntax handled by Spring**, not something the JDBC driver natively understands from `:tenantId`.

One name can appear in multiple places in SQL; Spring places the corresponding value at each position according to the parsed SQL. However, every parameter name must be supplied by the parameter source. Do not confuse `:name` with a dynamic column name: parameters still represent **values**, and cannot substitute query structure.

## 2. How Does Map<String, ?> Work?

### 2.1. Map as a List of Names and Values

Example overload:

```java
List<Contact> contacts =
        namedJdbc.query(sql, params, CONTACT_MAPPER);
```

With `params` as `Map<String, ?>`, Spring uses keys as parameter names and values as data. Suitable when:

- The number of parameters is small or moderate;
- Values have clear Java types, such as `Long`, `Integer`, or `String`;
- There is no need to declare a specific SQL type, scale, or vendor type name;
- You only need to pass a single-use group of names/values into `query`/`update`.

Update example:

```java
String updateSql = """
        UPDATE contacts
        SET score = :score
        WHERE id = :id AND tenant_id = :tenantId
        """;

int affected = namedJdbc.update(
        updateSql,
        Map.of("score", 80, "id", 12L, "tenantId", 7L));
```

`affected` is the affected row count reported by JDBC/DBMS, **not an auto-generated ID**. `Map.of(...)` does not guarantee entry iteration order, which **does not matter** for named parameters because Spring looks up values by **name**, not by Map entry order.

### 2.2. A Map Has String Keys and Object Values — Yet SQL Types Are Another Matter

`Map<String, Object>` is a Java data type. At runtime, a non-null value has a concrete class:

```java
Map<String, Object> params = new HashMap<>();
params.put("score", Integer.valueOf(80));

System.out.println(params.get("score").getClass().getSimpleName());
// Integer
```

The snippet above can run under Java 17 with imports for `java.util.Map` and `java.util.HashMap`.

However:

- Java `Integer.class` does not always map to a single SQL column type across all DBMSs.
- A driver may choose different conversions when the statement targets `DECIMAL`, `SMALLINT`, `BIGINT`, or a DB-specific type.
- **A `null` value has no runtime class to inspect via `getClass()`**. Calling `params.get("nickname").getClass()` when `nickname` is null throws `NullPointerException`.
- A generic type `Map<String, String>` does not automatically attach JDBC `Types.VARCHAR` metadata to each value either: Java generics are largely erased at runtime, and a null value does not "carry" the SQL column's generic type.

For most simple types and non-null values, inference/negotiation between Spring and the JDBC driver usually works smoothly. Yet **you should not equate one successful query with the Map always knowing the right SQL type**.

### 2.3. Missing Key in Map vs. Present Key with Null Value

These are two distinct states:

```java
Map<String, Object> params = new HashMap<>();
params.put("nickname", null);

System.out.println(params.containsKey("nickname")); // true
System.out.println(params.get("nickname") == null);   // true
System.out.println(params.containsKey("missing"));    // false
System.out.println(params.get("missing") == null);     // true
```

`Map.get(...) == null` is **not enough** to distinguish a missing key from present-but-null. `containsKey` is the proper check on null-permitting Maps.

For an SQL statement using `:nickname`:

- If the key `nickname` **is present** with value null: Spring has a supplied parameter carrying SQL NULL at bind time, even though the SQL type may still be unknown.
- If the key `nickname` **is missing**: there is no value for a required SQL parameter; Spring may throw `InvalidDataAccessApiUsageException` for the missing parameter before running the statement.

Do not treat a missing key as equivalent to SQL NULL; a missing key is a **query input bug**, whereas NULL is a **valid SQL value** depending on the column and context.

## 3. Map.of() Rejects Null

### 3.1. Why Can't You Write Map.of("nickname", null)?

Java's `Map.of(...)` and `Map.ofEntries(...)` create immutable Maps and **reject null keys and null values**. Example:

```java
Map<String, String> data = Map.of("nickname", null);
```

This line **compiles**, yet at runtime throws `NullPointerException` **immediately when creating the Map**, before SQL or `NamedParameterJdbcTemplate` is ever called. This is a constraint of **Java Collections Factory Methods**, not a Spring JDBC limitation.

When all values are non-null, `Map.of(...)` is very convenient:

```java
Map<String, Object> params =
        Map.of("id", 42L, "score", 75, "status", "ACTIVE");
```

However, if any value can be null, do not pick `Map.of` without handling null first.

### 3.2. Using HashMap When You Need a Key with Null

`HashMap` permits null values:

```java
Map<String, Object> params = new HashMap<>();
params.put("id", 42L);
params.put("nickname", null);

System.out.println(params.containsKey("nickname")); // true
```

This is **structurally valid as a Map** for named parameters, for example:

```java
namedJdbc.update(
        "UPDATE contacts SET nickname = :nickname WHERE id = :id",
        params);
```

However, this `UPDATE` still leaves the issue of the **null parameter's SQL type** (analyzed in the next section). `HashMap` solves **storing null in a Map**, not **declaring the SQL type for null**.

Besides `HashMap`, other Map implementations may allow nulls, but you must check each implementation's contract. **Never infer from the `Map` interface that every implementation permits null.**

### 3.3. Do Not Mutate an Existing Map.of

`Map.of` returns a Map that cannot be modified with `put` or `remove`:

```java
Map<String, Integer> values = Map.of("score", 100);
// values.put("score", 200); // UnsupportedOperationException
```

The commented line illustrates a runtime failure. If you want to build parameters conditionally, you can use `HashMap`, but create a **new Map per repository call** to avoid sharing mutable state across requests. For nullable parameters requiring types, `MapSqlParameterSource` is usually clearer.

## 4. Why Does Null Make SQL Type Inference Harder?

### 4.1. Non-Null Values Hint at a Java Type

Consider this SQL:

```sql
UPDATE contacts SET score = :score WHERE id = :id;
```

With:

```java
Map<String, Object> params =
        Map.of("score", 80, "id", 7L);
```

`score` has an `Integer` value and `id` has a `Long` value. Spring and the JDBC driver get extra hints when choosing bind types, and the database can also infer from the SQL column/expression.

When `nickname = null`, there is no `String` object for Spring to inspect. The SQL statement might let the database infer the type because it assigns to a `VARCHAR` column, **yet not every null position and not every driver infers reliably**.

### 4.2. Plain Maps Lack SQL Type Metadata

Example:

```java
Map<String, Object> params = new HashMap<>();
params.put("nickname", null);
params.put("id", 7L);
```

The Map holds keys and values, with **no separate entry stating that `nickname` is JDBC `Types.VARCHAR`**. When Spring passes a Map into `NamedParameterJdbcTemplate`, it may wrap it in a `MapSqlParameterSource`, but without registering an SQL type, the parameter type remains unknown under the `SqlParameterSource` contract.

When binding an unknown-type null, Spring uses fallback strategies such as querying `PreparedStatement.getParameterMetaData()`, calling `setNull` with a fallback SQL type, or taking driver/database-specific paths. Exact behavior can differ across Spring versions, DBMSs, drivers, and configurations. Consequently:

- On H2, a simple query may run fine with an untyped `null`;
- On PostgreSQL, Oracle, SQL Server, or an expression like `:value IS NULL`, behavior and cost can differ;
- Succeeding in tests does not guarantee null types will be inferred identically in production;
- When you **already know the SQL column type**, supply that metadata directly whenever null is a normal business branch.

Do not conclude either "Map + null always fails" or "Map + null is always safe". Both are overstatements.

### 4.3. Preferred Solution: MapSqlParameterSource with SQL Types

Spring provides `org.springframework.jdbc.core.namedparam.MapSqlParameterSource`. Besides values, it lets you declare **SQL types by parameter name**:

```java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("nickname", null, Types.VARCHAR)
        .addValue("id", 7L, Types.BIGINT);

int changed = namedJdbc.update(
        "UPDATE contacts SET nickname = :nickname WHERE id = :id",
        params);
```

This is an illustrative snippet with a valid `namedJdbc`.

The key difference is `addValue("nickname", null, Types.VARCHAR)`:

- Parameter name: `nickname`;
- Value: `null` (SQL NULL);
- SQL type: `java.sql.Types.VARCHAR` (matching the target column type).

`Types.VARCHAR` **does not mean binding the string literal `"null"`**. It instructs binding an **SQL NULL of type VARCHAR**. If the column is `INTEGER`, use `Types.INTEGER`; if `BIGINT`, use `Types.BIGINT`; if `TIMESTAMP`, use `Types.TIMESTAMP`, etc. When the DB uses vendor-specific types (e.g., PostgreSQL enum/UUID), you may need a type name/`Types.OTHER` or driver-specific configuration, backed by integration tests on the real database.

### 4.4. addValue Overloads and registerSqlType

Common forms:

```java
var params = new MapSqlParameterSource()
        .addValue("id", 7L)                      // type not explicitly specified
        .addValue("nickname", null, Types.VARCHAR)
        .addValue("score", 80, Types.INTEGER);
```

`addValue(String, Object)` stores the value. `addValue(String, Object, int)` stores both the value and SQL type. Another overload accepts `typeName` for cases where the driver/DBMS requires a vendor type name.

You can also initialize from a Map and **register types afterward**:

```java
Map<String, Object> values = new HashMap<>();
values.put("id", 7L);
values.put("nickname", null);

MapSqlParameterSource params = new MapSqlParameterSource(values);
params.registerSqlType("nickname", Types.VARCHAR);
params.registerSqlType("id", Types.BIGINT);
```

Key point: `MapSqlParameterSource` implements `SqlParameterSource`, exposing `getValue(name)` and `getSqlType(name)` to Spring, whereas a plain `Map<String, ?>` primarily supplies names and values.

You can also write a helper factory method to bind nullable parameters consistently across a group of related queries, making them easier to test.

### 4.5. When Do Even Non-Null Values Need Explicit Types?

Although `null` is the main motivation, a non-null parameter may also need an explicit SQL type when:

- A Java type can map to multiple SQL types;
- A DB column is `DECIMAL/NUMERIC` needing business precision/scale;
- A driver handles `UUID`, arrays, JSON, LOBs, enums, or temporal types specially;
- Consistent behavior across environments/drivers is required;
- Query plans or binding depend on matching types.

For example, `addValue("amount", amount, Types.DECIMAL)` can help when the column is decimal and `amount` is `BigDecimal`. Still, **declaring an SQL type does not replace picking the right Java model and SQL column**; never pass `Types.VARCHAR` for everything just to bypass type inference.

### 4.6. Why Not Use Types.NULL for Every Parameter?

`java.sql.Types.NULL` represents a generic SQL NULL, **not the exact column type needed**. When you know `nickname` is VARCHAR, `Types.VARCHAR` states the intent more accurately. Some drivers require the concrete type to evaluate expressions, convert values, inspect parameter metadata, or plan statements.

`Types.NULL` can be a valid fallback in certain scenarios, but it is not a universally better choice than the actual SQL type. If an SQL parameter targets a specialized column or an expression prone to type conversion, pick the right `Types.*` constant or vendor type name when needed.

## 5. Binding Null Is Not Equivalent to WHERE ... IS NULL

This is the most critical point about **SQL semantics**, independent of whether `Map`/`MapSqlParameterSource` binds cleanly.

### 5.1. `= NULL` Never Matches NULL Rows

Suppose table `contacts` has a nullable `nickname`:

| id | display_name | nickname |
| ---: | --- | --- |
| 1 | Alice | NULL |
| 2 | Bob | NULL |
| 3 | Carol | Caz |

SQL query:

```sql
SELECT id
FROM contacts
WHERE nickname = :nickname
ORDER BY id;
```

Even if `nickname` is bound as SQL NULL **with type VARCHAR**, the expression `nickname = NULL` evaluates to **UNKNOWN** under SQL's three-valued logic. In a `WHERE` clause, UNKNOWN is not treated as TRUE. Hence, this query **returns neither Alice nor Bob**.

To filter rows where `nickname` is truly NULL, write:

```sql
SELECT id
FROM contacts
WHERE nickname IS NULL
ORDER BY id;
```

The second statement needs no `nickname` binding, because `IS NULL` is an **SQL construct** with its own semantics.

### 5.2. Distinguishing Three Business Intents for Nullable Input

A value `nickname = null` can carry multiple API meanings:

1. **Do not update nickname**: the caller omitted the field, so the SQL `UPDATE` should leave that column untouched.
2. **Clear nickname**: the caller explicitly asked to set the column to SQL NULL.
3. **Find rows with NULL nickname**: the query must use `WHERE nickname IS NULL`.

These three cases cannot be deduced from a single `map.get("nickname") == null` check, since that also returns null when the **key is absent**. In PATCH APIs, you typically need to distinguish an **absent field** from an **explicit `null` field** at the request layer before constructing the query. That is a business/API contract decision, not a `PreparedStatement` detail.

For "ignore filter if null" semantics, you can branch the query:

```java
String sql;
MapSqlParameterSource params = new MapSqlParameterSource();

if (nicknameFilter == null) {
    sql = "SELECT id FROM contacts ORDER BY id";
} else {
    sql = """
            SELECT id FROM contacts
            WHERE nickname = :nickname
            ORDER BY id
            """;
    params.addValue("nickname", nicknameFilter, Types.VARCHAR);
}
```

This snippet illustrates selecting SQL structure; `nicknameFilter` is assumed to exist and execution is omitted. With many filters, using a controlled SQL builder or predefined branches is easier to maintain.

If null input **means search for `nickname IS NULL`**, you must take a `WHERE nickname IS NULL` SQL branch, not the "omit filter" branch.

### 5.3. Do Not Casually Write `:value IS NULL OR column = :value`

You may encounter expressions like:

```sql
WHERE (:nickname IS NULL OR nickname = :nickname)
```

This tries to express "skip filter when `nicknameFilter` is null." However, at `:nickname IS NULL`, the DBMS may struggle with **type inference** on a null parameter. Furthermore, `OR` expressions can hinder index usage depending on the optimizer.

When queries and types grow complex, prefer controlled branching for conditions, or ensure SQL types are declared and tested directly on the real DBMS. Never assume the `OR`-with-null pattern is always portable or produces the best query plan.

### 5.4. NULL Is a Value; the String `"null"` Is Not SQL NULL

Distinguish clearly:

```java
params.addValue("nickname", null, Types.VARCHAR);    // SQL NULL
params.addValue("nickname", "null", Types.VARCHAR);  // 4 characters
params.addValue("nickname", "", Types.VARCHAR);      // empty string
```

In most DBMSs, an empty string and NULL have distinct semantics; some DBMSs, such as Oracle for certain string types, have special rules. Never replace nullable text with `""` or `"null"` merely to avoid binding null—doing so alters data and business semantics.

## 6. Runnable Example with Java 17 + Spring JDBC + H2

This program directly demonstrates the differences among:

- `HashMap` containing a `null` value;
- `Map.of(...)` rejecting `null`;
- `MapSqlParameterSource` registering an SQL type for `null`;
- `nickname = :nickname` vs. `nickname IS NULL`;
- A plain Map passing non-null values to `NamedParameterJdbcTemplate`;
- A null value returned from a nullable SQL column (not the same as zero rows returned).

Uses **Java 17+**, Spring Framework **6.2.12**, H2 **2.3.232**, and a Java 17–compatible Gradle. No Spring Boot or separate database server required.

### 6.1. Project Structure

```text
named-parameter-null-demo/
├── build.gradle
└── src/main/java/example/NamedParameterNullDemo.java
```

### 6.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.NamedParameterNullDemo'
}
```

`spring-jdbc` provides `NamedParameterJdbcTemplate`, `JdbcTemplate`, and `DriverManagerDataSource`. H2 is used at runtime to create an in-memory H2 database without importing H2 driver classes directly in Java source.

### 6.3. Complete Java Source

Create `src/main/java/example/NamedParameterNullDemo.java`:

```java
package example;

import java.sql.Types;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class NamedParameterNullDemo {

    private static final String INSERT = """
            INSERT INTO contacts (id, display_name, nickname, score)
            VALUES (:id, :name, :nickname, :score)
            """;

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:named_null_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(ds);
        NamedParameterJdbcTemplate named = new NamedParameterJdbcTemplate(ds);

        jdbc.execute("""
                CREATE TABLE contacts (
                    id BIGINT PRIMARY KEY,
                    display_name VARCHAR(80) NOT NULL,
                    nickname VARCHAR(80),
                    score INTEGER NOT NULL
                )
                """);

        // HashMap allows a key to be present even with a null value.
        Map<String, Object> alice = new HashMap<>();
        alice.put("id", 1L);
        alice.put("name", "Alice");
        alice.put("nickname", null);
        alice.put("score", 10);

        System.out.println(
                "keyPresent=" + alice.containsKey("nickname")
                        + ",isNull=" + (alice.get("nickname") == null));

        // For null, declare an explicit type rather than relying on
        // driver inference.
        MapSqlParameterSource aliceTyped =
                new MapSqlParameterSource(alice);
        aliceTyped.registerSqlType("nickname", Types.VARCHAR);
        int a = named.update(INSERT, aliceTyped);

        MapSqlParameterSource bob = new MapSqlParameterSource()
                .addValue("id", 2L, Types.BIGINT)
                .addValue("name", "Bob", Types.VARCHAR)
                .addValue("nickname", null, Types.VARCHAR)
                .addValue("score", 20, Types.INTEGER);
        int b = named.update(INSERT, bob);

        // Map.of is convenient for non-null values.
        int c = named.update(
                INSERT,
                Map.of("id", 3L,
                       "name", "Carol",
                       "nickname", "Caz",
                       "score", 30));
        System.out.println("inserted=" + (a + b + c));

        // Map.of rejects null when creating the Map, before SQL is called.
        boolean mapOfRejectedNull;
        try {
            Map.of("nickname", (String) null);
            mapOfRejectedNull = false;
        } catch (NullPointerException ex) {
            mapOfRejectedNull = true;
        }
        System.out.println("mapOfRejectedNull=" + mapOfRejectedNull);

        // SQL three-valued logic: = NULL matches no rows.
        MapSqlParameterSource nullNickname =
                new MapSqlParameterSource()
                        .addValue("nickname", null, Types.VARCHAR);
        Integer equalsNull = named.queryForObject(
                "SELECT COUNT(*) FROM contacts WHERE nickname = :nickname",
                nullNickname,
                Integer.class);
        System.out.println("equalsNullCount=" + equalsNull);

        // IS NULL checks for rows that actually hold SQL NULL.
        Integer isNull = named.queryForObject(
                "SELECT COUNT(*) FROM contacts WHERE nickname IS NULL",
                Map.of(),
                Integer.class);
        System.out.println("isNullCount=" + isNull);

        // A row exists, yet its nickname column value can be null.
        String bobNickname = named.queryForObject(
                "SELECT nickname FROM contacts WHERE id = :id",
                Map.of("id", 2L),
                String.class);
        System.out.println("bobNicknameBefore=" + bobNickname);

        // Updating from null to a string; type can still be declared.
        int changed = named.update(
                """
                UPDATE contacts
                SET nickname = :nickname
                WHERE id = :id
                """,
                new MapSqlParameterSource()
                        .addValue("nickname", "Bobby", Types.VARCHAR)
                        .addValue("id", 2L, Types.BIGINT));
        System.out.println("updated=" + changed);

        Integer remainingNull = named.queryForObject(
                "SELECT COUNT(*) FROM contacts WHERE nickname IS NULL",
                Map.of(),
                Integer.class);
        System.out.println("remainingNull=" + remainingNull);

        // Plain Map passes non-null values concisely.
        List<String> selected = named.query(
                """
                SELECT display_name
                FROM contacts
                WHERE score >= :minScore
                ORDER BY id
                """,
                Map.of("minScore", 20),
                (rs, rowNum) -> rs.getString("display_name"));
        System.out.println("scoreAtLeast20=" + selected);
    }
}
```

**Notable points:**

1. `alice` is a `HashMap` with key `nickname` and null value, wrapped in `MapSqlParameterSource`. Registering `Types.VARCHAR` for this key specifies the SQL type at bind time instead of relying on a classless null.
2. `bob` directly uses `addValue(name, value, sqlType)`, so the source holds both values and JDBC metadata.
3. `Carol` has a non-null nickname, so `Map.of(...)` is concise.
4. `Map.of("nickname", (String) null)` throws `NullPointerException` right in Java; the `catch` turns that behavior into a verification output rather than silently swallowing errors.
5. `nickname = :nickname` with null evaluates to UNKNOWN, so the count is 0 despite two rows having NULL nicknames.
6. `nickname IS NULL` returns 2 before updating Bob and 1 after updating Bob.
7. `queryForObject(..., String.class)` can return `null` for **an existing row** whose `nickname` column is SQL NULL. This differs from **zero rows**, which throws `EmptyResultDataAccessException`.
8. `DriverManagerDataSource` suits demos but is not a production pool; in-memory H2 with `DB_CLOSE_DELAY=-1` persists across connections within the same JVM process.

### 6.4. Running the Demo and Expected Stdout

From the directory containing `build.gradle`, run:

```bash
gradle run
```

If the project has a Gradle Wrapper, use `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows. Gradle may print its own logs; the **Java program** prints these lines in order:

```text
keyPresent=true,isNull=true
inserted=3
mapOfRejectedNull=true
equalsNullCount=0
isNullCount=2
bobNicknameBefore=null
updated=1
remainingNull=1
scoreAtLeast20=[Bob, Carol]
```

Result explanation:

- Initially, Alice and Bob both have NULL nicknames; Carol has `Caz`.
- Three valid inserts add 3 rows, so `inserted=3`.
- `Map.of` rejects null in Java, so `mapOfRejectedNull=true`.
- `WHERE nickname = NULL` does not select the two NULL-nickname rows, so the count is 0.
- `WHERE nickname IS NULL` selects Alice and Bob, so the count is 2.
- Querying the nickname for ID 2 returns **one row**, whose value is NULL, so the Java variable is `null`.
- Updating Bob's nickname to `Bobby` affects one row; afterward only Alice has a NULL nickname.
- `score >= 20` selects Bob (20) and Carol (30); `ORDER BY id` guarantees output order.

This is a small runnable project, not a complete production configuration. When an application targets PostgreSQL/Oracle/SQL Server, write integration tests with the real driver and column types, especially for nullable parameters.

## 7. Should You Choose Map or MapSqlParameterSource?

| Criterion | `Map<String, ?>` | `MapSqlParameterSource` |
| --- | --- | --- |
| Passing values by name | Yes | Yes |
| Concise for non-null values | Very good | Good |
| Can hold null values | Depends on implementation: `HashMap` yes, `Map.of` no | Yes |
| Register JDBC SQL type per param | No separate metadata in a plain Map | Yes, via `addValue(..., sqlType)` or `registerSqlType` |
| Register vendor type name | Not via plain Map | Yes, via `addValue(..., sqlType, typeName)` |
| Reusing a param multiple times in one SQL | Yes | Yes |
| Optional filter parameters | Code must decide whether to add key/SQL predicate | Code must still decide SQL predicate; source does not interpret null meaning |
| Readability with many nullable params | Easy to omit SQL types; hard to see null intent | Clearly expresses value and type in one place |

**Practical guidelines:**

- Use `Map.of(...)` when all values are known non-null and no special metadata is needed.
- Use `HashMap` when building dynamically with possible nulls, **yet do not forget the SQL type issue**.
- Use `MapSqlParameterSource` when parameters are nullable, when explicit types improve clarity, or when specialized values need JDBC type/type names.
- Ensure SQL expresses the right `NULL` semantics; even with the right type, `column = :param` will not find NULL columns.

## 8. When a Map Is Built from a Request DTO

Suppose an API receives an update request:

```json
{
  "id": 2,
  "nickname": null
}
```

Define the contract: does `nickname = null` mean "clear nickname" or "leave unchanged"? Some JSON serializers/deserializers or DTOs turn both an **omitted field** and an **explicit null field** into the same Java `null`, unless you design a model or flag to distinguish them.

If sending null means "clear nickname", the repository can do:

```java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("id", request.id(), Types.BIGINT)
        .addValue("nickname", request.nickname(), Types.VARCHAR);

int changed = namedJdbc.update(
        "UPDATE contacts SET nickname = :nickname WHERE id = :id",
        params);
```

This is an **excerpt**, assuming `request` is defined, `namedJdbc` exists, and the user is authorized to update that record. `changed` is normally 1 when the ID exists and 0 when no row matches. Handle according to your business contract.

If "not sending nickname" means no change, do not blindly include a null `nickname` key in every `UPDATE`. Represent absent vs. explicit-null explicitly in the DTO and construct the query accordingly. You cannot rely solely on `Map.get("nickname") == null`, since it also returns null for a missing key.

Also, never trust a `tenantId` from the request without authorization checks; Map/parameter binding protects **SQL syntax**, not **authorization**.

## 9. Map, SQL Types, and Collection-Parameterized Queries

`NamedParameterJdbcTemplate` can expand a collection parameter for `IN (:ids)` in supported cases.

```java
List<Long> ids = List.of(1L, 2L, 3L);

List<String> names = namedJdbc.query(
        """
        SELECT display_name
        FROM contacts
        WHERE id IN (:ids)
        ORDER BY id
        """,
        Map.of("ids", ids),
        (rs, rowNum) -> rs.getString("display_name"));
```

This snippet is illustrative; it assumes `namedJdbc` and the table exist. When preparing the JDBC statement, Spring expands the list into the matching number of `?` markers. This is fundamentally different from concatenating SQL values with string building.

**Limits to keep in mind:**

1. Never assume a collection works as **one** JDBC `?` across databases; expansion is a named-parameter utility feature.
2. Empty lists must be handled deliberately; `IN ()` may be invalid or behave differently across dialects. When there are no IDs to search for, returning an empty list in the application layer is a reasonable choice.
3. Very large lists can hit driver/DBMS bind-parameter or SQL-length limits; split into batches or change strategy (temporary tables, joins, etc.) when appropriate.
4. `List.of(...)` also rejects null elements. If a list can contain null, rethink the SQL logic rather than merely switching to `ArrayList`.
5. `IN (NULL)` does not find `id IS NULL` rows (and primary key IDs are non-NULL anyway). Finding NULL requires an explicit `IS NULL` condition when valid for the business case.

Similarly, with `LIKE :pattern`, safe binding **does not automatically escape `LIKE` wildcards** `%` and `_`. They retain wildcard semantics; escape them appropriately if the user expects a literal substring search.

## 10. Errors and Scenarios to Distinguish

| Scenario | Observable Symptom | Diagnosis / Action |
| --- | --- | --- |
| `Map.of("x", null)` | `NullPointerException` before calling JDBC | Factory Map rejects null; use `MapSqlParameterSource` or null-permitting Map |
| `HashMap.put("x", null)` | Map created successfully | Java Map allows null, yet SQL type may still be unknown |
| SQL requires `:id` but Map lacks `id` | Spring error for missing parameter value | Use `containsKey`/verify query params; never equate missing with null |
| SQL uses null `:nickname` and driver cannot infer type | `SQLException` or `DataAccessException`, depending on DB/driver | Use `addValue("nickname", null, Types.VARCHAR)` or matching vendor type |
| `WHERE nickname = :nickname` with NULL | Misses rows with NULL nickname | To match NULL, write `IS NULL` |
| Query returns one row whose column is SQL NULL | Mapped scalar value may be Java null | Do not confuse with a 0-row result |
| Query returns 0 rows with `queryForObject` | `EmptyResultDataAccessException` | Choose appropriate API/cardinality |
| Client omits field but backend writes null | Can accidentally erase existing data | Distinguish absent from explicit-null in API contract |
| Using `Types.NULL` for every null | Type does not specify column type | Use the column's actual JDBC type; test with driver |
| Query `:name IS NULL` with untyped null | Some DBMSs cannot infer parameter type | Declare type or use explicit predicate branches |
| Calling `put` on a `Map.of` | `UnsupportedOperationException` | Use a mutable Map or build a new Map |
| `IN (:ids)` parameter is an empty list | SQL may be invalid | Define empty-list behavior before calling DB |
| Passing request column name as a value | `ORDER BY :field` does not sort by identifier | Pick columns/directions via an SQL structure allowlist |
| Works on H2, fails on nullable types in production | Different driver, SQL dialect, metadata, and schema | Integration-test with target DBMS/driver and typed parameters |

## 11. Minimum Recommended Tests

**Java Collections tests:** verify `Map.of("key", null)` throws `NullPointerException`; verify `HashMap` reports `containsKey("key") == true` when the value is null.

**Binding tests:** execute an SQL update on a nullable `VARCHAR` column using `MapSqlParameterSource(..., Types.VARCHAR)`; verify the DB stores SQL NULL rather than the string `"null"`.

**Cardinality tests:** `SELECT nickname WHERE id=:id` for an existing ID may return Java null; a non-existent ID with `queryForObject` is a separate case and must follow the contract.

**SQL NULL semantics tests:** `nickname = :nickname` with typed null returns zero null rows; `nickname IS NULL` returns the exact count of NULL rows.

**Missing key tests:** SQL using `:id` when the parameter source lacks `id` must fail explicitly, never silently substitute null.

**Optional patch tests:** distinguish a request omitting `nickname` from a request sending explicit `nickname: null`; verify existing data is not unintentionally cleared.

**Real DB tests:** nullable parameters in `WHERE :value IS NULL`, enums, UUIDs, arrays, or JSON must be tested against the production driver/DBMS rather than extrapolated from H2. Inspect query plans/performance when SQL has complex nullable filters.

## 12. Self-Check Questions

1. Why can `Map.of("nickname", null)` fail before Spring even builds a statement?
2. Is `Map.get("nickname") == null` enough to prove the `nickname` key exists? What else should you call?
3. Given a `HashMap` containing key `nickname` with value null, does Spring know for certain that `nickname`'s SQL type is VARCHAR?
4. Why does `MapSqlParameterSource.addValue("nickname", null, Types.VARCHAR)` express intent more clearly than a plain Map?
5. Do `Types.NULL` and `Types.VARCHAR` mean the exact same thing?
6. Why does binding `null` to `WHERE nickname = :nickname` still return no rows with SQL NULL nicknames?
7. If the requirement is to find NULL nicknames, should the SQL use `= :nickname` or `IS NULL`?
8. In a PATCH request, should an omitted `nickname` field and an explicit-null `nickname` field be treated identically?
9. When an SQL parameter holds an `Integer` value, does the value's Java class guarantee the JDBC type will always be `Types.INTEGER`?
10. What problem arises with SQL using `IN (:ids)` if `ids` is an empty list?
11. When is `Map.of` more appropriate than `MapSqlParameterSource`?
12. Why does using named parameters not allow concatenating column names or `ORDER BY` directly from a request?

**Key takeaway:** `Map<String, ?>` is very handy for passing **non-null** named parameters. Whenever values may be null, separate three questions: **Can the Map store null?**; **What SQL type does JDBC need to bind null?**; **Does the SQL interpret null according to business intent?**. Use `MapSqlParameterSource` to describe values with JDBC types; use `IS NULL` and proper SQL structure for nullable conditions.

### References

- Spring Framework — [Named Parameters in JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html).
- Spring Framework — [NamedParameterJdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html).
- Spring Framework — [MapSqlParameterSource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html).
- Spring Framework — [SqlParameterSource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/namedparam/SqlParameterSource.html).
- Java SE 17 — [Map.of API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#of()).
- Java SE 17 — [java.sql.Types API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Types.html).
