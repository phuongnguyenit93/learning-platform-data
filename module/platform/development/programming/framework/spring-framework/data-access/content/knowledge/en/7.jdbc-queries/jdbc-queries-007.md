# Distinguishing a Row Containing SQL NULL from No Rows

When querying a database with JDBC or Spring JDBC, the following two outcomes **differ in both meaning and handling**:

1. The query **returns one row**, but a column in that row has value **SQL `NULL`**.
2. The query **returns zero rows**.

In the first case, the entity/record is present in the result set, though the attribute in question has no value. In the second case, no row matched the query condition. Confusing the two can cause the application to report "not found" for an existing record, return wrong defaults, lose business state, or mishandle `JdbcTemplate` exceptions.

This lesson focuses on **JDBC query results**: distinguishing row count from column value, reading `ResultSet.next()`, using `wasNull()`, mapping into Java, and handling results in Spring JDBC.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why "one row with a NULL column" and "no rows" are two distinct states.
- Inspect SQL and `ResultSet` to check **row existence** before reading **column values**.
- Use `next()`, `getString()`, `getObject()`, `getInt()`, and `wasNull()` properly in Java 17+.
- Design Java return types that preserve both "no row" and "row exists with nullable field equal to null".
- Understand `JdbcTemplate.queryForObject()`, `query()`, and `queryForList()` when results have 0, 1, or multiple rows.
- Avoid pitfalls arising from `LEFT JOIN`, `COUNT(*)`, `COUNT(column)`, `COALESCE`, and API result handling.
- Verify all three cases with meaningful tests.

## 2. A SQL Example with Three States

Suppose the system stores customer notes. Each customer in the sample table can have a note, while the `note` column allows NULL.

~~~sql
CREATE TABLE customer_note (
    id BIGINT PRIMARY KEY,
    note VARCHAR(200) NULL
);

INSERT INTO customer_note (id, note) VALUES (1, NULL);
INSERT INTO customer_note (id, note) VALUES (2, 'Contacted');
~~~

Let us test the same SQL query with three IDs:

~~~sql
SELECT id, note
FROM customer_note
WHERE id = ?;
~~~

| Bound `id` value | Rows returned | Result content | Meaning |
| ---: | ---: | --- | --- |
| `1` | 1 | `id=1, note=NULL` | Record exists, but note is missing/unset |
| `2` | 1 | `id=2, note='Contacted'` | Record exists and note has a value |
| `3` | 0 | No rows | No matching record exists |

For ID 1, the row contains **two columns**: `id` is 1, `note` is SQL NULL. For ID 3, there is no row to read, so asking "what is the value of column `note` in that row?" makes no sense.

Visualize the results:

~~~text
id = 1:  +----+------+
         | id | note |
         +----+------+
         |  1 | NULL |     <-- one row present
         +----+------+

id = 3:  +----+------+
         | id | note |
         +----+------+
                           <-- no rows
~~~

Do not equate "blank display" with "no rows". Many SQL GUIs render NULL as an empty cell or the text `NULL`; how a tool displays it is not proof of row count.

### Two Independent Layers of Information

A lookup returning at most one record can be modeled with two questions:

1. **Does a row exist in the result?** Yes/no, checked first.
2. **If a row exists, is the column value SQL NULL?** Yes/no, checked after reading the column.

Logically, the states can be `NO_ROW`, `ROW_WITH_NULL`, or `ROW_WITH_VALUE`. If a table has multiple nullable columns, one row can also have many combinations of NULL and non-NULL values. Returning only a nullable `String` from the repository layer usually cannot express all of these states on its own.

## 3. JDBC ResultSet: next() Is About Rows, Getters Are About Columns

JDBC receives `SELECT` results through `java.sql.ResultSet`. The `ResultSet` cursor initially points **before the first row**. You must call `rs.next()` to advance to the next row:

- `rs.next() == true`: the cursor is positioned on a valid row; you may read columns of **the current row**.
- `rs.next() == false` on the first call: there are no result rows.
- A getter like `rs.getString("note")` returns Java `null` when **column `note` of the current row** is SQL NULL. It is not a way to check whether a row exists.
- Once `rs.next()` returns `false`, there is no current row; never call a getter to "test" whether it is NULL.

Conceptual snippet:

~~~java
try (ResultSet rs = statement.executeQuery()) {
    if (!rs.next()) {
        // Query returned 0 rows.
    } else {
        // Guaranteed at least 1 row exists.
        String note = rs.getString("note");
        if (note == null) {
            // Row exists, note column has SQL NULL value.
        } else {
            // Row exists, note column is non-NULL.
        }
    }
}
~~~

This snippet is **illustrative code inside a method with an existing `PreparedStatement statement` and appropriate JDBC imports**; not a standalone runnable Java file. The decisive step is **checking `next()` first**, then checking the getter value.

### Behavior Table to Remember

| SQL Result | First `rs.next()` | `rs.getString("note")` after `next()==true` | Conclusion |
| --- | --- | --- | --- |
| 0 rows | `false` | Must not be read | `NO_ROW` |
| 1 row, `note IS NULL` | `true` | Java `null` | `ROW_WITH_NULL` |
| 1 row, `note='Contacted'` | `true` | String `"Contacted"` | `ROW_WITH_VALUE` |
| Multiple rows | `true`; subsequent calls may return `true` | Value depends on each row | Must loop or detect cardinality violation |

**Very common pitfall:** If you call `rs.next()` once in an `if` condition and call it a second time to "start reading", you have moved to the next row or past the end. A `ResultSet` with one row returns `false` on the second call; that is a cursor-control bug, not evidence that the first row was NULL.

## 4. SQL NULL Values When Reading with Different Getters

`ResultSet` methods have different rules when encountering SQL NULL. In particular, getters returning **Java primitives** cannot return Java `null`.

| Reading current column | When SQL NULL | How to preserve "NULL" information |
| --- | --- | --- |
| `rs.getString("note")` | Java `null` | Check `note == null` |
| `rs.getObject("note")` | Java `null` | Check `object == null` |
| `rs.getInt("score")` | Primitive `0` | Call `rs.wasNull()` immediately after getter |
| `rs.getLong("id")` | Primitive `0L` | Call `rs.wasNull()` if column is nullable |
| `rs.getBoolean("enabled")` | Primitive `false` | Call `rs.wasNull()` if column is nullable |
| `rs.getBigDecimal("amount")` | Java `null` | Check `amount == null` |

Example when `score INTEGER NULL` contains SQL NULL:

~~~java
int score = rs.getInt("score");
boolean scoreIsSqlNull = rs.wasNull();  // Must check right after the getter just read.
Integer nullableScore = scoreIsSqlNull ? null : score;
~~~

If the SQL value is an **actual number 0**, `getInt` also returns `0`, but `wasNull()` will be `false`. If it is SQL NULL, `getInt` returns `0` and `wasNull()` is `true`. Therefore, checking `score == 0` alone is wrong when the column is nullable.

`rs.wasNull()` reflects **the column read by the most recent getter**. Store its result immediately after the getter you want to inspect:

~~~java
int score = rs.getInt("score");
boolean isScoreNull = rs.wasNull();
String note = rs.getString("note");   // Reading another column afterward.
~~~

Do not read `note` and then call `wasNull()` expecting it to still reflect `score`. Nor does `wasNull()` mean anything for checking whether zero rows exist; it applies only after a getter has read a column of a valid row.

Some JDBC drivers support typed `rs.getObject("score", Integer.class)` to return `Integer` or `null`. Conversion support depends on the driver and SQL type; for primitives, the `getInt`/`wasNull` pair is the fundamental, explicit rule.

### SQL NULL Differs from Empty String, Zero, and false

`NULL` means missing/unknown value in SQL; `''` is a zero-length string; `0` is an integer with value zero; `false` is boolean false. Those three values are **not** SQL NULL under general JDBC rules, even though certain databases have quirks with empty strings. Never use `isBlank()` or `equals("")` as a SQL NULL check, because a getter can return Java `null`.

## 5. Standalone Java 17+ Example with CachedRowSet

The following example uses `javax.sql.rowset.CachedRowSet` from the JDK to construct three in-memory result sets; no JDBC driver, database, or Spring is needed. `CachedRowSet` implements `ResultSet`, letting you practice real `next()` and `getString()` calls. It does not replace testing queries on a concrete database, but is ideal for observing the distinction directly.

Save as **`NullVsNoRowDemo.java`**:

~~~java
import java.sql.Types;
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.RowSetMetaDataImpl;
import javax.sql.rowset.RowSetProvider;

public class NullVsNoRowDemo {
    static CachedRowSet prepare(boolean hasRow, String note) throws Exception {
        CachedRowSet rows = RowSetProvider.newFactory().createCachedRowSet();
        RowSetMetaDataImpl meta = new RowSetMetaDataImpl();
        meta.setColumnCount(2);
        meta.setColumnName(1, "id");
        meta.setColumnType(1, Types.INTEGER);
        meta.setColumnName(2, "note");
        meta.setColumnType(2, Types.VARCHAR);
        rows.setMetaData(meta);

        if (hasRow) {
            rows.moveToInsertRow();
            rows.updateInt("id", 1);
            if (note == null) {
                rows.updateNull("note");
            } else {
                rows.updateString("note", note);
            }
            rows.insertRow();
            rows.moveToCurrentRow();
        }
        rows.beforeFirst();
        return rows;
    }

    static void inspect(String label, CachedRowSet rows) throws Exception {
        try (rows) {
            if (!rows.next()) {
                System.out.println(label + ": NO_ROW");
                return;
            }
            String note = rows.getString("note");
            System.out.println(label + (note == null
                    ? ": ROW_WITH_SQL_NULL"
                    : ": ROW_WITH_VALUE(" + note + ")"));
        }
    }

    public static void main(String[] args) throws Exception {
        inspect("missing", prepare(false, null));
        inspect("null", prepare(true, null));
        inspect("filled", prepare(true, "hello"));
    }
}
~~~

Compile and run with JDK 17 or higher:

~~~bash
javac --release 17 NullVsNoRowDemo.java
java NullVsNoRowDemo
~~~

**Exact stdout:**

~~~text
missing: NO_ROW
null: ROW_WITH_SQL_NULL
filled: ROW_WITH_VALUE(hello)
~~~

Explanation: `prepare(false, null)` inserts no row; `rows.next()` returns `false` on the first call. `prepare(true, null)` inserts **one** row whose `note` column is set via `updateNull`; `rows.next()` is `true` and `getString("note")` returns Java `null`. `prepare(true, "hello")` creates a row with a non-NULL string. `rows.beforeFirst()` resets the cursor before the first row after populating data; `try (rows)` closes the row set after inspection.

**Demo limitation:** It only simulates results and does not test SQL `SELECT`, isolation, or real JDBC driver behavior. `ResultSet`-reading code in later sections must be tested in an application against a real database.

## 6. A Real JDBC Method: Optional of the Row, Not Optional of the Column

Assuming a `DataSource` bean is available, we want to look up `customer_note` by primary key `id`. The contract must distinguish:

- No row: `Optional.empty()`.
- Row `id=1, note=NULL`: `Optional.of(new CustomerNote(1, null))`.
- Row `id=2, note="Contacted"`: `Optional.of(new CustomerNote(2, "Contacted"))`.

Use an **object representing the row**, allowing its nullable field to be Java `null`. Because `Optional` wraps the non-null `CustomerNote` object, it preserves row existence even when `note` is null.

Example `CustomerNoteDao.java` using plain JDBC, Java 17+:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class CustomerNoteDao {
    public record CustomerNote(long id, String note) {}

    private final DataSource dataSource;

    public CustomerNoteDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<CustomerNote> findById(long id) throws SQLException {
        String sql = "SELECT id, note FROM customer_note WHERE id = ?";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();     // No row.
                }

                CustomerNote row = new CustomerNote(
                        rs.getLong("id"),
                        rs.getString("note")     // Java null allowed.
                );

                if (rs.next()) {
                    throw new SQLException("Expected at most one row");
                }
                return Optional.of(row);         // Row exists, even if note == null.
            }
        }
    }
}
~~~

This is an **integration class**: it compiles with JDK 17+ but needs a configured `DataSource`/JDBC driver, schema, and data to run. It has no `main` and is not presented as a standalone program. `try-with-resources` ensures JDBC resources are released even on exception. `?` is a prepared statement parameter, avoiding concatenating `id` directly into SQL.

Since `id` is a primary key, a valid schema returns at most one row. The second `rs.next()` check catches bugs if the query contract is ever changed into a multi-row query. You do not need `wasNull()` for `note` when using `getString`; `id` is `PRIMARY KEY` and thus non-nullable.

### Why Does Optional<String> Easily Lose Information?

Compare:

~~~java
// Wrong if business needs to distinguish "no row" from "row with NULL note".
Optional<String> result = Optional.ofNullable(note);
~~~

`Optional.ofNullable(null)` evaluates to `Optional.empty()`, even though `note == null` may come from **an existing row**. If code also uses `Optional.empty()` for a zero-row query, two distinct states have been collapsed into one.

**Recommended:** `Optional<CustomerNote>`, where `CustomerNote.note()` may be `null`. If a stricter domain contract is needed, use a *sealed result type* with dedicated cases like `NotFound`, `FoundNull`, and `FoundValue`; that helps when API/logic relies on pattern matching without inferring from null. Do not add extra abstractions automatically if a row-wrapping record is already clear.

## 7. Spring JdbcTemplate and the 0 / 1 / Multiple-Row Cases

In Spring Framework, `JdbcTemplate` manages query execution, mapping, closing JDBC resources, and translating errors via the `DataAccessException` hierarchy. However, **each query method has a different row-cardinality contract**. Read the Javadoc and choose the API matching the business states you need to preserve.

### 7.1. queryForObject: Requires Exactly One Row

Example in a Spring application with a `JdbcTemplate jdbc` bean:

~~~java
String note = jdbc.queryForObject(
        "SELECT note FROM customer_note WHERE id = ?",
        String.class,
        id
);
~~~

Assuming `id` is a primary key with the schema/data from section 2:

| `id` | Scenario | `queryForObject(..., String.class, id)` Behavior |
| ---: | --- | --- |
| 1 | One row, `note` column is SQL NULL | Returns Java `null` |
| 2 | One row, `note` has a string | Returns corresponding string |
| 3 | No row | Throws `EmptyResultDataAccessException` |
| Broken query returning multiple rows | More than one row | Throws `IncorrectResultSizeDataAccessException` |

Therefore, **returning `null` and throwing `EmptyResultDataAccessException` mean different things**. `EmptyResultDataAccessException` is a subtype of `IncorrectResultSizeDataAccessException`, not a raw `SQLException`. If a repository wants to return `Optional` instead of an exception when not found, catch **only** the "empty result" exception; do not catch every `DataAccessException` and treat it as "not found", which masks connection errors, SQL syntax bugs, or permission denials.

Also distinguish the case where `RowMapper` returns Java `null` for a valid row: `queryForObject(sql, rowMapper, args...)` can return `null` when the mapper returns null. API usage should thus clearly document **0 rows vs. 1 row mapped to null vs. multiple rows**.

### 7.2. Preserving Three States with ResultSetExtractor

A clearer approach in Spring JDBC is `JdbcTemplate.query(sql, ResultSetExtractor, args...)` to check `rs.next()`, then wrap **the entire row** in `Optional`.

~~~java
import java.sql.SQLException;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerNoteRepository {
    public record CustomerNote(long id, String note) {}

    private final JdbcTemplate jdbc;

    public CustomerNoteRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<CustomerNote> findById(long id) {
        return jdbc.query(
                "SELECT id, note FROM customer_note WHERE id = ?",
                rs -> {
                    if (!rs.next()) {
                        return Optional.empty();
                    }

                    CustomerNote row = new CustomerNote(
                            rs.getLong("id"),
                            rs.getString("note")
                    );

                    if (rs.next()) {
                        throw new SQLException("Expected at most one row");
                    }
                    return Optional.of(row);
                },
                id
        );
    }
}
~~~

This is **a class snippet for integration into a Spring application**, requiring `spring-jdbc`, `spring-context`, `DataSource`/`JdbcTemplate`, and the matching schema. It is not a standalone Java CLI.

The distinction logic matches plain JDBC:

- No row → `Optional.empty()`.
- One row with `note IS NULL` → `Optional.of(CustomerNote)` where `note() == null`.
- One row with a non-null note → `Optional.of(CustomerNote)` with content.
- Multiple rows violating contract → error, instead of silently taking the first row.

`ResultSetExtractor` lets you inspect the entire `ResultSet`, so it can verify cardinality. Do not use `RowMapper` directly to detect "no rows" inside the mapper: the mapper is normally invoked **only when there is a row to map**.

### 7.3. queryForList and queryForMap

`jdbc.queryForList(sql, String.class, args...)` normally yields a `List<String>`:

- 0 rows → empty list `[]`.
- 1 row with SQL NULL column → **one-element** list `[null]`.
- 1 row with value → e.g., `["Contacted"]`.

Importantly, **`list.isEmpty()` differs from `list.get(0) == null`**. A Java list built by Spring's mapper can contain null elements; do not replace it with `List.of(null)` because `List.of` forbids null elements. When a SQL query expects at most one row, prefer a DTO/record or check `size()` for cardinality.

`jdbc.queryForMap(sql, args...)` expects one row and maps columns to `Map<String,Object>`. If the row exists and `note` is SQL NULL, the map can hold key `note` with Java value `null`. `map.get("note") == null` **does not prove the key is absent**: use `map.containsKey("note")` if you truly need to distinguish a missing key from an existing key with a null value. Meanwhile, **row** existence in `queryForMap` is still enforced by the exactly-one-row contract; a 0-row query throws the corresponding exception.

### 7.4. Do Not Turn Every Error into "Not Found"

Anti-example:

~~~java
try {
    return jdbc.queryForObject(sql, String.class, id);
} catch (Exception ex) {
    return null; // Swallows DB, SQL, network, and empty-result errors alike.
}
~~~

Here `null` could mean "row with SQL NULL", "no row", or "database failure". The code loses both **business information** and **operational signals**. If you need to handle `EmptyResultDataAccessException`, catch that exact type and represent absence explicitly; let infrastructure errors flow through proper error handling.

## 8. How SQL Returns One Row: SELECT, COUNT, and Aggregates

A common mistake is inferring **row count** from a column's **value**. In SQL, aggregate expressions can produce a row even when there are no input rows.

With the sample table:

~~~sql
-- ID 3 does not exist: direct query returns 0 rows.
SELECT note FROM customer_note WHERE id = 3;

-- ID 3 does not exist: aggregate without GROUP BY returns one row, value 0.
SELECT COUNT(*) AS total FROM customer_note WHERE id = 3;

-- ID 1 exists with NULL note: COUNT(*) = 1, COUNT(note) = 0.
SELECT COUNT(*) AS all_rows, COUNT(note) AS non_null_notes
FROM customer_note
WHERE id = 1;

-- ID 3 does not exist: MIN(note) returns one row with SQL NULL.
SELECT MIN(note) AS minimum_note
FROM customer_note
WHERE id = 3;
~~~

| Query | Result row count | Value |
| --- | ---: | --- |
| `SELECT note ... WHERE id=3` | 0 | No columns to read |
| `SELECT COUNT(*) ... WHERE id=3` | 1 | `0` |
| `SELECT COUNT(*) ... WHERE id=1` | 1 | `1` |
| `SELECT COUNT(note) ... WHERE id=1` | 1 | `0` |
| `SELECT MIN(note) ... WHERE id=3` | 1 | SQL `NULL` |

**Why?** `COUNT(*)` counts **rows**; `COUNT(note)` counts **non-NULL note values**. Aggregates without `GROUP BY` summarize the entire input into **one row** even when there are zero input rows; `COUNT` yields 0, while many other aggregates like `MIN` or `SUM` normally return NULL. With `GROUP BY`, having no matching groups can produce **0 result rows**, so do not apply "aggregates always return one row" mechanically to every SQL query.

For example:

~~~sql
SELECT id, COUNT(*)
FROM customer_note
WHERE id = 3
GROUP BY id;
~~~

This returns **0 rows** because there is no `id=3` group. When the application needs to check whether a record exists, `COUNT(*)` or `EXISTS` can be useful, provided you understand the returned value. If you already run a query returning the full row, checking `rs.next()` directly is usually clearest.

## 9. LEFT JOIN Can Produce Rows with NULL Right-Side Columns

With `LEFT JOIN`, if the left table has a row and the right table has no matching row, SQL **still returns a result row** and selected columns from the right side are typically NULL. This is another source of confusion, especially when the application selects only one nullable column.

Suppose:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL
);

CREATE TABLE customer_profile (
    customer_id BIGINT PRIMARY KEY,
    nickname VARCHAR(100) NULL,
    FOREIGN KEY (customer_id) REFERENCES customer(id)
);

INSERT INTO customer (id, full_name)
VALUES (10, 'An'), (11, 'Binh');

INSERT INTO customer_profile (customer_id, nickname)
VALUES (10, NULL);
~~~

Query:

~~~sql
SELECT c.id, p.customer_id AS profile_customer_id, p.nickname
FROM customer AS c
LEFT JOIN customer_profile AS p
  ON p.customer_id = c.id
WHERE c.id IN (10, 11)
ORDER BY c.id;
~~~

Result:

| `c.id` | `profile_customer_id` | `nickname` | Reality |
| ---: | ---: | --- | --- |
| 10 | 10 | NULL | Profile **exists**, nickname is NULL |
| 11 | NULL | NULL | Profile **does not exist**; result row produced by LEFT JOIN |

**If you only SELECT `p.nickname`**, both rows give NULL. You cannot distinguish having a profile from not having one using only that nullable column. Also select **a right-side key that is NOT NULL whenever the row exists**, such as `p.customer_id`, or use `EXISTS` / two controlled queries.

To read accurately when joining:

~~~java
long id = rs.getLong("id");
long profileId = rs.getLong("profile_customer_id");
boolean hasProfile = !rs.wasNull();
String nickname = rs.getString("nickname");
// hasProfile=true, nickname=null: profile exists, but nickname is NULL.
// hasProfile=false, nickname=null: profile does not exist.
~~~

When the join key is read as a primitive, call `wasNull()` immediately after reading `profile_customer_id`. If you use `rs.getObject("profile_customer_id")`, checking for Java null can also distinguish them. In other SQL queries, choose a column guaranteed by schema to be **NOT NULL on matched rows**; never use a nullable column as the indicator of a "join match".

### WHERE on the Right Table Can Accidentally Turn LEFT JOIN into Filtering Out Rows

~~~sql
SELECT c.id, p.nickname
FROM customer c
LEFT JOIN customer_profile p ON p.customer_id = c.id
WHERE p.nickname = 'An';
~~~

The `p.nickname = 'An'` condition in `WHERE` eliminates rows with no profile and rows with a NULL nickname, because comparing against NULL does not evaluate to TRUE. If the goal is to keep all customers while only joining profiles with a specific nickname, place the condition appropriately in `ON`:

~~~sql
SELECT c.id, p.nickname
FROM customer c
LEFT JOIN customer_profile p
  ON p.customer_id = c.id AND p.nickname = 'An';
~~~

The two queries have different semantics; do not move conditions mechanically if business logic actually wants to exclude customers. Always analyze where conditions live and how many rows are returned.

## 10. SQL NULL and Filter Conditions: = NULL Does Not Mean IS NULL

In standard SQL, `NULL` represents an unknown/absent value, and comparisons use three-valued logic (`TRUE`, `FALSE`, `UNKNOWN`):

~~~sql
-- Correct: find rows where note column is SQL NULL.
SELECT id FROM customer_note WHERE note IS NULL;

-- Wrong intent: note = NULL is not a NULL check.
SELECT id FROM customer_note WHERE note = NULL;

-- Correct: find rows where note is not NULL.
SELECT id FROM customer_note WHERE note IS NOT NULL;
~~~

When `WHERE` evaluates to `UNKNOWN`, the row is not selected. Hence `WHERE note = NULL` normally returns **0 rows**, which does not prove the table has no `note=NULL` rows. Use `IS NULL`/`IS NOT NULL` or dialect-appropriate NULL-safe comparison operators when truly needed.

Another common trap:

~~~sql
SELECT COALESCE(note, 'No note yet') AS note
FROM customer_note
WHERE id = 1;
~~~

`COALESCE` replaces SQL NULL with a fallback string **within a present row**. It does not fabricate a row when an ID lookup yields no results. However, wrapping `COALESCE` around an aggregate changes the semantics:

~~~sql
SELECT COALESCE(MIN(note), 'No note yet') AS note
FROM customer_note
WHERE id = 3;
~~~

This returns **one row** containing the fallback string even though no source record matches `id=3`. Do not use an aggregate fallback to infer that a source row exists.

## 11. Defining Result Contracts in Repository/Service Layers

The data-access layer should explicitly advertise **cardinality contracts** (0..1, exactly 1, 0..N) and **nullability** of each field, rather than returning an unexplained nullable value.

| Business need | Suggested contract | Why |
| --- | --- | --- |
| Find record by ID, may not exist | `Optional<CustomerNote>` | Optional wraps **the row**; note field may be null |
| Query list of records | `List<CustomerNote>` | 0 rows is an empty list; each object is one row |
| Fetch scalar requiring exactly one row | `queryForObject` + contract exception handling | Expresses "exactly one row" |
| Check existence only | `EXISTS` or `COUNT(*)` query with right condition | Needs boolean/count, no need to read nullable fields |
| Need three distinct states at API/domain | Sealed result type or discriminated DTO | Clearly separates NotFound, FoundNull, FoundValue |
| Numeric column that may be SQL NULL | `Integer`/`Long`/`BigDecimal` and `wasNull()` when needed | Primitives cannot hold null |

Java 17 example using a sealed result type **describing the contract**, independent of ORM or framework:

~~~java
sealed interface NoteLookup
        permits NoteLookup.NotFound, NoteLookup.Found {
    record NotFound() implements NoteLookup {}
    record Found(String note) implements NoteLookup {}
}
~~~

In Java 17, `record Found(String note)` allows `note == null`; `new NotFound()` represents not found. If business rules want no nulls even on Java fields, split into `FoundWithNull` and `FoundWithValue(String)`, with constructor validation ensuring `FoundWithValue` rejects null.

**Do not convert "not found" into default values like an empty string or 0** if those are valid business values. If a business rule says "if there is no note, display an empty string", perform that conversion intentionally at the presentation/domain layer after row existence has been established.

### API Example with Different Semantics

A hypothetical `GET /customer-notes/{id}` API could define:

~~~text
GET /customer-notes/1  -> 200 {"id":1,"note":null}
GET /customer-notes/2  -> 200 {"id":2,"note":"Contacted"}
GET /customer-notes/3  -> 404
~~~

This is an **illustrative API design convention**, not a mandatory standard. The lesson: SQL NULL in column `note` is **not automatically equivalent** to HTTP 404. In JSON, having a serializer omit null fields differs from emitting a field with value `null`; the API contract must specify this. With DTOs/JSON, avoid turning an existing record into "not found" merely because a nullable property is null.

## 12. Check Cardinality Instead of Silently Taking the First Row

Sometimes code does:

~~~java
if (!rs.next()) {
    return Optional.empty();
}
return Optional.of(new CustomerNote(
        rs.getLong("id"),
        rs.getString("note")
));
~~~

This is valid when **the schema/query guarantees at most one row**, such as a primary-key lookup. If a query accidentally returns two rows, this code takes the first and ignores the rest. When the contract demands exactly one or at most one row, call `rs.next()` a second time **after reading the first row** to detect multiple rows. When multiple rows are expected by design, use a loop:

~~~java
while (rs.next()) {
    String note = rs.getString("note");
    // Each iteration corresponds to one row, even if note is Java null.
}
~~~

A `while` loop executes only when rows exist. **An empty list** represents 0 rows; **a list with one nullable record** represents 1 row. Avoid `LIMIT 1` just to hide a duplicate bug or broken query when business rules actually demand uniqueness; fix the constraint or query properly.

### Two Separate Queries for Existence Checking Can Race

Example:

~~~sql
SELECT COUNT(*) FROM customer_note WHERE id = ?;
SELECT note FROM customer_note WHERE id = ?;
~~~

Between the two statements, another transaction can insert, delete, or update the row depending on isolation and concurrency. When the application needs state **from a single consistent read**, prefer a single query returning the row, or use appropriate transactions/isolation. Do not assume a prior `COUNT(*)` check is needed to distinguish NULL from no row: `ResultSet.next()` in one query already solves it.

## 13. Common Mistakes and Fixes

**Mistake 1 — Calling a getter before `next()`.** The ResultSet is not positioned on a valid row; reading columns violates the JDBC contract and typically raises a SQLException.  
**Fix:** Advance the cursor with `if (rs.next())` or `while (rs.next())` first.

**Mistake 2 — Seeing `rs.getString("note") == null` and concluding "record not found".** The getter only reads a column **of an existing row**.  
**Fix:** Separate the `!rs.next()` branch from the `note == null` branch.

**Mistake 3 — Using `getInt() == 0` to detect SQL NULL.** SQL number 0 is a valid value.  
**Fix:** Call `rs.wasNull()` immediately after the getter and use wrapper `Integer` if null must be represented.

**Mistake 4 — Calling `wasNull()` after a different getter.** The previous column's null state has been overwritten.  
**Fix:** Call `wasNull()` right after the target getter and save the boolean result.

**Mistake 5 — Collapsing `Optional.empty()` from both "no row" and "row with null scalar".** Loses existence information.  
**Fix:** Wrap a record/DTO representing **the row**, e.g., `Optional<CustomerNote>`, or use a result type distinguishing states.

**Mistake 6 — Catching all `DataAccessException` and returning null.** Network, query, or database failures get disguised as business state.  
**Fix:** Handle 0 rows specifically when expected; let infrastructure errors be logged/propagated properly.

**Mistake 7 — Using `COUNT(note) == 0` to conclude the table has no records.** `COUNT(note)` skips rows where `note` is NULL.  
**Fix:** Use `COUNT(*)` to count rows if asking "how many rows exist?", or query directly by ID.

**Mistake 8 — Using a nullable column from LEFT JOIN to infer whether the right side exists.** Both "matched with NULL column" and "no match" return NULL.  
**Fix:** Also select a non-nullable right-side key; check existence on that key or use `EXISTS`.

**Mistake 9 — Treating `SELECT MIN(column)` returning NULL as proof of a source row containing NULL.** An aggregate without GROUP BY can return one NULL row when there are zero input rows.  
**Fix:** Review the query structure and check count/existence separately when needed.

**Mistake 10 — Converting null to empty string too early.** Using `COALESCE` or Java defaults erases the difference between empty and missing data.  
**Fix:** Apply fallbacks intentionally at the presentation layer, preserving row presence for business logic.

**Mistake 11 — Concluding "a row exists" because `JdbcTemplate.queryForObject` returned `0`.** For `COUNT(*)`, `0` is **the value of an aggregate row**, not a source data row.  
**Fix:** Distinguish the aggregate query's result set from the source records it counts.

## 14. Testing Checklist for JDBC/Spring JDBC Code

For a repository looking up by `id` with a nullable `note` column, include at least these tests against an appropriate test database:

| Test | Prepared data | Expected outcome |
| --- | --- | --- |
| No row | No `id=3` | `Optional.empty()` or 0-row exception per contract |
| One row, NULL value | `id=1, note=NULL` | `Optional.of(row)`; `row.note()==null` |
| One row, non-NULL value | `id=2, note='Contacted'` | `Optional.of(row)` with string |
| Actual numeric zero | `score=0` | `getInt=0`, `wasNull=false` |
| Numeric SQL NULL | `score=NULL` | `getInt=0`, `wasNull=true` |
| Query accidentally returning multiple rows | Omit key filter or use non-unique filter | Cardinality error if contract is at most one row |
| LEFT JOIN matches row with nullable NULL | Profile exists, nickname NULL | Detected via non-NULL right-side PK/FK |
| LEFT JOIN has no match | No profile | Do not infer from nickname; right-side key is NULL |
| Aggregate with no source rows | `COUNT(*)` for missing ID | One row with value 0 |
| Aggregate over NULL column | `COUNT(note)` on one NULL row | One row with value 0; do not infer no row |

When testing `JdbcTemplate.queryForObject`, explicitly assert `EmptyResultDataAccessException` for 0 rows, Java null for 1 row/1 column SQL NULL, and `IncorrectResultSizeDataAccessException` for multiple rows. When using `Optional<Row>`, assert `isEmpty()`/`isPresent()` and the row contents.

If you only test cases where the column has a non-null value, the bug conflating "no row" with "row containing NULL" can survive even when all tests pass.

## 15. Self-Check Exercises

**Question 1.** Query `SELECT note FROM customer_note WHERE id=1` returns one row with `note=NULL`. What do `rs.next()` and `rs.getString("note")` return?  
**Answer:** `rs.next() == true`; the getter returns Java `null`.

**Question 2.** If `id=3` does not exist, should you call `rs.getString("note")` to check for NULL?  
**Answer:** No. The first `rs.next()` returns `false`, so there is no current row.

**Question 3.** A `score INTEGER NULL` column is read with `getInt` and returns 0. Is that enough to know whether SQL had 0 or NULL?  
**Answer:** No. You must call `wasNull()` right after `getInt`.

**Question 4.** How many result rows and what value does `SELECT COUNT(*) FROM customer_note WHERE id=3` produce?  
**Answer:** One row containing 0 (for an aggregate without GROUP BY), even though no record with ID 3 exists in the source table.

**Question 5.** Does `Optional.ofNullable(rs.getString("note"))` preserve the difference between 0 rows and one row containing NULL?  
**Answer:** No, if both branches lead to `Optional.empty()`. Use `next()` to detect row presence and wrap a row-representing DTO/record in `Optional`.

**Question 6.** A `LEFT JOIN` returns `profile_id=NULL, nickname=NULL`, while another row returns `profile_id=10, nickname=NULL`. How do their meanings differ?  
**Answer:** In the first case, no profile row matched the join (assuming `profile_id` is a non-NULL key of profile); in the second, a profile exists, with a NULL nickname.

**Question 7.** Why does `queryForObject(..., String.class)` returning `null` not mean `EmptyResultDataAccessException`?  
**Answer:** Null is the mapped value of one row with one SQL NULL column; the exception occurs when the row count violates the contract (specifically 0 rows).

**Question 8.** If you want a REST endpoint to return 404 when there is no row but 200 when a row exists with `note=NULL`, what return type should the repository use?  
**Answer:** For example `Optional<CustomerNote>`, where `CustomerNote` is always a non-null object when the row exists, while `note` may be null.

## 16. Summary of Rules

**Row presence must be determined by cardinality, not by the value of a nullable column.** In JDBC, `ResultSet.next()` determines whether a row exists; getters and `wasNull()` decode each value of that row. In Spring JDBC, `queryForObject` requires one row and distinguishes 0 rows with an exception, whereas `query`/`queryForList` can express row counts more explicitly per contract. For ID-lookup repositories, `Optional<RowDto>` is usually enough to preserve both layers of information.

When working with `JOIN`, aggregates, or `COALESCE`, inspect **the SQL output row set** first, and only then interpret NULL in individual columns. That prevents most "data exists yet reported as not found" bugs.

### Official References

- [Java SE 21 — ResultSet API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html): cursor position, `next()`, getters, `wasNull()`, and SQL NULL.
- [Java SE 21 — CachedRowSet API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql.rowset/javax/sql/rowset/CachedRowSet.html): disconnected rowset used with `ResultSet`.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): querying with `JdbcTemplate`.
- [Spring Framework — JdbcOperations API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html): `queryForObject`, `query`, `queryForList`, and cardinality contracts.
- [Spring Framework — EmptyResultDataAccessException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/EmptyResultDataAccessException.html): exception thrown when a result is expected but 0 rows are returned.