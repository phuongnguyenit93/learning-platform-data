# Reading by Column Name, Alias, or Position

## 1. Objectives and Context

This lesson belongs to the **Result Mapping** group of Spring Framework Data Access. After executing a `SELECT`, JDBC returns a `ResultSet`; in Spring JDBC, `JdbcTemplate` typically passes each row into a `RowMapper<T>`. The core issue is: **retrieving the right column in each row** by column name, SQL alias, or position. Doing it wrong can lead to reading the wrong primary key on a JOIN, mapping the wrong type, or bugs that only surface after someone changes the `SELECT` order.

You will learn:

1. The two JDBC overloads `getXxx(String columnLabel)` and `getXxx(int columnIndex)` and the difference between physical column name and **column label**.
2. Using `AS` to define unique aliases and establish a clear contract between the SQL query and Java DTO/record.
3. The **1-based column index** rule, distinct from `RowMapper`'s 0-based `rowNum`.
4. When to read by name/alias, when position is a reasonable choice, and the risks of `SELECT *`.
5. How to inspect `ResultSetMetaData.getColumnLabel`, `getColumnName`, `getColumnCount`; handling SQL `NULL` and data types.
6. The relationship with `RowMapper`, `BeanPropertyRowMapper`, `DataClassRowMapper`, `queryForList`, and `Map`-based mapping.
7. A **standalone runnable Java 17 + Spring Framework + H2** example to verify how columns are read and their results.

This lesson focuses on **column selection and result mapping**, without diving deeply into query optimization, pool lifecycles, or transaction boundaries.

## 2. JDBC Actually Provides Two Ways to Locate Columns

Suppose the SQL outputs three columns:

```sql
SELECT id, full_name, age
FROM customers
WHERE id = ?;
```

In a `ResultSet` already positioned on a valid row:

```java
long id1 = rs.getLong("id");
String name1 = rs.getString("full_name");
int age1 = rs.getInt("age");

long id2 = rs.getLong(1);
String name2 = rs.getString(2);
int age2 = rs.getInt(3);
```

This is a **snippet inside a callback/JDBC code that already has `rs`**, not a standalone Java file. The two getter groups correspond to:

- **By string** `getXxx(String columnLabel)`: JDBC looks up a column by **result label**. This label comes from the alias when SQL uses `AS`; otherwise, it is normally the column name.
- **By integer** `getXxx(int columnIndex)`: JDBC looks up the column by **position in the select-list**. The first index is **1**, not 0.

What people call “reading by column name” and “reading by alias” actually **both use the `String columnLabel` getter**, not two different kinds of API. An alias is a way of setting the **label** for a query column.

### Quick Example Table

| SQL Select-list | Label at column 1 | Label at column 2 | Correct read call |
| --- | --- | --- | --- |
| `SELECT id, name` | `id` | `name` | `getLong("id")` or `getLong(1)` |
| `SELECT name, id` | `name` | `id` | `getLong(2)` |
| `SELECT id AS user_id, name AS display_name` | `user_id` | `display_name` | `getString("display_name")` |
| `SELECT COUNT(*) AS total` | `total` | None | `getLong("total")` or `getLong(1)` |

This table writes label names following the SQL phrasing; the exact casing returned by metadata depends on the database/driver and how the alias is quoted. Do not design code relying on every driver exposing labels in the exact uppercase/lowercase typed in SQL.

## 3. Distinguishing Column Name, SQL Alias, and JDBC Column Label

Three concepts:

1. **Physical column name:** the column name defined in the schema, e.g., `customers.full_name`.
2. **SQL alias:** the name set in `SELECT` with `AS`, e.g., `full_name AS display_name`.
3. **Column label:** the name exposed by JDBC for each column in the result set and accepted by `getXxx(String columnLabel)`.

Example:

```sql
SELECT c.id AS customer_id,
       c.full_name AS display_name
FROM customers c
WHERE c.id = ?;
```

Correct mapper:

```java
CustomerView customer = new CustomerView(
        rs.getLong("customer_id"),
        rs.getString("display_name"));
```

This is a snippet inside a `RowMapper`; the `CustomerView` class/record must be defined by the application.

**Do not write a mapper that relies on `rs.getString("full_name")` still finding the column after SQL has changed the label to `display_name`.** Some drivers support looking up by physical name after an alias, but that is not a portable contract to rely on. Always use the actual label output by `SELECT`.

### Aliases Do Not Change the Schema

`AS display_name` only changes the **presentation name in the result set**; it does not rename `full_name` in the table. Thanks to that, the application can keep a stable mapping interface when the schema is altered and the query can preserve the alias:

```sql
-- Before migration:
SELECT full_name AS display_name FROM customers;

-- After migration renaming the column:
SELECT legal_name AS display_name FROM customers;
```

If the business meaning or data type changes, the mapper still needs to be re-evaluated; aliases only solve the **naming** problem.

## 4. RowMapper in Spring JdbcTemplate

`JdbcTemplate.query(...)` can accept a `RowMapper<T>`:

```java
List<Customer> customers = jdbcTemplate.query(
        "SELECT id, name FROM customers ORDER BY id",
        (rs, rowNum) -> new Customer(
                rs.getLong("id"),
                rs.getString("name")));
```

Spring opens/closes the `ResultSet` itself, moves the cursor to each row, and calls `mapRow(rs, rowNum)`. The mapper only reads data **on the current row** and returns a Java object.

Rules:

- **Do not call `rs.next()`** inside `RowMapper`: the template already controls row iteration.
- **Do not call `rs.close()`** inside the mapper: resources are managed by the template.
- `rowNum` is the **row** index starting from **0**, whereas `getLong(1)` uses the **column** position starting from **1**.
- The mapper must return a DTO/record or data detached from the result set; do not return the raw `ResultSet` to use after the query completes.
- Getters can throw `SQLException`; let Spring JDBC handle/translate exceptions instead of swallowing errors and returning wrong results.

**Wrong example:**

```java
// WRONG: do not use this snippet in an application.
(rs, rowNum) -> {
    rs.next();                       // Skips the row controlled by JdbcTemplate.
    return rs.getString(rowNum);     // rowNum=0 on the first row, but column index starts at 1.
}
```

Do not mix up **which column to read** with **who manages the cursor**.

## 5. Reading by Column Name: Clear and Less Order-Dependent

If the SQL is:

```sql
SELECT id, name, reward_points
FROM customers
WHERE id = ?;
```

then a name-based mapper can be:

```java
RowMapper<CustomerDetails> mapper = (rs, rowNum) ->
        new CustomerDetails(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getInt("reward_points"));
```

Pros:

- Easy to cross-reference SQL with Java.
- Reordering `SELECT` while keeping labels usually keeps the mapper valid.
- Code reviewers can see the meaning of the fields being read.
- Reduces column mix-ups after adding new fields.

Cons:

- When SQL changes an alias, the mapper must also be updated or the alias contract preserved.
- A JOIN with two columns both named `id` makes `getLong("id")` ambiguous.
- These are still strings in Java: the compiler does not know whether a label exists. Integration tests running real queries are needed.

For queries using a reusable mapper, you can define label-name constants; however, constants do not verify on their own that the SQL emits the right labels. Do not design a default mapper assuming every query returns `id`/`name` if some queries have changed them to `customer_id`/`display_name`.

## 6. Using AS to Avoid Name Collisions After JOIN

Suppose:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(80) NOT NULL
);

CREATE TABLE purchases (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL
);
```

Dangerous query:

```sql
SELECT c.id, p.id, c.name, p.amount_cents
FROM purchases p
JOIN customers c ON c.id = p.customer_id;
```

The result set has **two `id` labels**. Calling `rs.getLong("id")` typically fetches **the first matching column**, without automatically knowing whether you want `p.id` or `c.id`. If the `SELECT` order changes, the code can read a different value with no compile error.

Fix with distinct aliases:

```sql
SELECT p.id AS purchase_id,
       c.id AS customer_id,
       c.name AS buyer_name,
       p.amount_cents AS total_cents
FROM purchases p
JOIN customers c ON c.id = p.customer_id;
```

Reading:

```java
PurchaseView purchase = new PurchaseView(
        rs.getLong("purchase_id"),
        rs.getLong("customer_id"),
        rs.getString("buyer_name"),
        rs.getLong("total_cents"));
```

**Rule:** every column mapped to a distinct meaning must have a **distinct label**. Do not merely switch `getLong("id")` to `getLong(2)` to mask the issue: index 2 is unambiguous today, but easily shifts when the select-list is edited.

### Expressions and Aggregates

Computed results should also have explicit aliases:

```sql
SELECT COUNT(*) AS purchase_count,
       COALESCE(SUM(amount_cents), 0) AS total_cents
FROM purchases
WHERE customer_id = ?;
```

The mapper can read:

```java
long count = rs.getLong("purchase_count");
long cents = rs.getLong("total_cents");
```

Without aliases, metadata for expressions like `COUNT(*)`, `SUM(...)`, or complex calculations can carry unpredictable/non-portable labels. Aliases are the public part of the **SQL result contract**.

## 7. Reading by Position: Only Correct When the Exact Select-List Is Known

Here is the SQL:

```sql
SELECT id, name FROM customers;
```

Since `id` is in the first column and `name` is in the second:

```java
(rs, rowNum) -> new Customer(
        rs.getLong(1),
        rs.getString(2))
```

If the SQL changes to:

```sql
SELECT name, id FROM customers;
```

the mapper must change to:

```java
(rs, rowNum) -> new Customer(
        rs.getLong(2),
        rs.getString(1))
```

**The index is the position in the result, not the ordinal in the table definition.** Index 0 is invalid. If the SQL has only two columns, index 3 is also invalid. This mismatch can produce hard-to-spot bugs when a getter accepts convertible types: for example, the new column is numeric while the mapper still calls `getString(2)` and throws no error, even though the value is business-wrong.

### When Using an Index Is Reasonable

- Single-column queries: `SELECT COUNT(*) ...`, `getLong(1)` is very clear.
- Projections of just one or two columns under complete control, where mapper code sits right next to the SQL.
- Code that needs to avoid label lookups in a hot path proven important by profiling; **do not automatically assume index lookup is dramatically faster**, since performance depends on the driver and SQL/network cost is usually the dominant factor.

For multi-column queries, JOINs, or mappers reused across multiple SQL statements, aliases/names are generally easier to maintain.

## 8. Comparing the Three Approaches at a Design Level

| Criterion | Reading by unaliased name | Reading by alias | Reading by position |
| --- | --- | --- | --- |
| Java | `getString("name")` | `getString("buyer_name")` | `getString(2)` |
| Matching SQL | `SELECT name` | `SELECT name AS buyer_name` | `SELECT id, name` |
| Reordering select-list | Minimal impact | Minimal impact | **Easily misaligned** |
| Renaming physical column | Mapper may need changes | Alias can stay stable | Index remains valid if position/type stay |
| JOIN with duplicate `id` | Ambiguous | **Should have unique aliases** | Readable but hard to review |
| Aggregate expressions | Hard to rely on default name | Should alias | Read first column if position known |
| Use for DTOs | Fine if names are stable | Clearest contract | Tightly coupled to SQL order |
| Risk | Missing/changed labels, duplicate labels | SQL alias and Java out of sync | Order changed without updating code |

There is no single solution for every case; choose based on **the complexity and stability of the projection**. For business applications with many JOINs/DTOs, explicit aliases are a more reliable default.

## 9. JDBC Metadata: Seeing the Actual Contract

`ResultSetMetaData` tells you:

- `getColumnCount()`: number of returned columns.
- `getColumnLabel(i)`: display name/label, prioritizing the `AS` alias when present.
- `getColumnName(i)`: column name according to JDBC metadata; usually the schema name for real columns, though driver/query-dependent and may not be useful for expressions.
- `getColumnType(i)` / `getColumnTypeName(i)`: SQL data type.
- `getTableName(i)`: source table name if the driver can provide it; not always populated.

Illustrative snippet inside a `ResultSetExtractor`:

```java
int columnCount = rs.getMetaData().getColumnCount();
for (int i = 1; i <= columnCount; i++) {
    System.out.println(
            "index=" + i
            + ", label=" + rs.getMetaData().getColumnLabel(i)
            + ", name=" + rs.getMetaData().getColumnName(i));
}
```

**Loop bounds:** the index loop runs from 1 to `columnCount`, not from 0. If the SQL has `SELECT name AS "display_name"`, metadata labels on H2 can preserve the lowercase string `display_name` due to the quoted identifier. With unquoted aliases, H2 normally normalizes to uppercase; PostgreSQL normally normalizes to lowercase. Do not infer from the H2 example that every driver preserves casing verbatim.

If a label is missing, do not fix the code by “guessing another name” without first verifying the select-list and metadata. Record the exact label/type and update the query or mapper deliberately.

## 10. Casing Rules and Quoted Aliases

In the statement:

```sql
SELECT name AS display_name FROM customers;
```

the database may change the identifier's case when unquoted. JDBC column-label lookup is normally case-insensitive, but the **display string** in `getColumnLabel` may not match how you typed it.

Standard SQL for a quoted alias:

```sql
SELECT name AS "display_name" FROM customers;
```

Some database systems have different quoting rules (`backticks`, `[brackets]`, or SQL modes). Prefer simple aliases like `customer_id`, `buyer_name`, and verify against the actual database in use.

**Avoid designing two aliases that differ only by case** such as `id` and `ID`; many drivers perform case-insensitive lookups and therefore do not guarantee they can be accessed distinctly via `getXxx(String)`. If you need two distinct fields, give them semantically distinct labels.

## 11. SQL NULL and Primitive Getters

Fetching the right column is still not enough if the column contains `NULL`. Primitive JDBC getters return a default value when the SQL value is NULL:

- `getInt` / `getLong` → 0;
- `getDouble` → 0.0;
- `getBoolean` → false.

To distinguish `NULL` from a valid 0/false value, call `rs.wasNull()` **immediately after the getter being checked**:

```java
int points = rs.getInt("reward_points");
Integer nullablePoints = rs.wasNull() ? null : points;
```

If you call `rs.getString("name")` and only then call `wasNull()`, the result reflects the **most recent** getter, no longer `reward_points`.

Object-style getters can normally return `null`, for example `getString(...)` or `getObject("reward_points", Integer.class)` on supporting drivers. When creating a DTO record, choose `Integer`/`Long` if it means **no data yet**, instead of `int`/`long`; if business rules allow defaulting to 0, establish an explicit conversion rule.

Data types also matter:

- `BIGINT` → `long/Long` if within range;
- `VARCHAR` → `String`;
- `DECIMAL` → `BigDecimal` for currency/exact decimals;
- `DATE/TIMESTAMP` → Java time API matching the driver and timezone;
- `SUM(...)` can return a wider type than the input column: verify on the real DB.

Adding an alias does not automatically cast types or eliminate `NULL`.

## 12. Complete Example: Java 17 + Spring JdbcTemplate + H2

The application below uses **Spring Framework 6.2.14**, **H2 2.3.232**, and **Java 17+**, run with Gradle. It runs as a standalone Java application without needing Spring Boot or an external database. `DriverManagerDataSource` in the example has no pooling and is used solely for illustration.

### 12.1. Structure

```text
column-lookup-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ColumnLookupDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'column-lookup-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}
repositories {
    mavenCentral()
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
    implementation 'org.springframework:spring-jdbc:6.2.14'
    runtimeOnly 'com.h2database:h2:2.3.232'
}
application {
    mainClass = 'demo.ColumnLookupDemo'
}
```

`src/main/java/demo/ColumnLookupDemo.java`:

```java
package demo;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class ColumnLookupDemo {

    record Customer(long id, String name) {}
    record Purchase(long id, String buyer, long cents) {}

    @Configuration
    static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:lookup_demo;DB_CLOSE_DELAY=-1",
                    "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE customers (
                        id BIGINT PRIMARY KEY,
                        name VARCHAR(80) NOT NULL,
                        reward_points INT
                    )
                    """);
            jdbc.execute("""
                    CREATE TABLE purchases (
                        id BIGINT PRIMARY KEY,
                        customer_id BIGINT NOT NULL,
                        amount_cents BIGINT NOT NULL
                    )
                    """);

            jdbc.update("INSERT INTO customers (id, name) VALUES (?, ?)",
                    1L, "Lan");
            jdbc.update("INSERT INTO customers (id, name) VALUES (?, ?)",
                    2L, "Minh");
            jdbc.update("""
                    INSERT INTO purchases (id, customer_id, amount_cents)
                    VALUES (?, ?, ?)
                    """, 101L, 1L, 25_000L);
            jdbc.update("""
                    INSERT INTO purchases (id, customer_id, amount_cents)
                    VALUES (?, ?, ?)
                    """, 102L, 1L, 40_000L);

            // A: By column name when SQL has no AS.
            Customer byName = jdbc.queryForObject(
                    "SELECT id, name FROM customers WHERE id = ?",
                    (rs, rowNum) -> new Customer(
                            rs.getLong("id"),
                            rs.getString("name")),
                    1L);
            System.out.println("byName=" +
                    byName.id() + ":" + byName.name());

            // B: By 1-based position.
            Customer byIndex = jdbc.queryForObject(
                    "SELECT id, name FROM customers WHERE id = ?",
                    (rs, rowNum) -> new Customer(
                            rs.getLong(1),
                            rs.getString(2)),
                    1L);
            System.out.println("byIndex=" +
                    byIndex.id() + ":" + byIndex.name());

            // C: When SELECT changes to name, id, update the getter positions.
            Customer reordered = jdbc.queryForObject(
                    "SELECT name, id FROM customers WHERE id = ?",
                    (rs, rowNum) -> new Customer(
                            rs.getLong(2),
                            rs.getString(1)),
                    1L);
            System.out.println("reordered=" +
                    reordered.id() + ":" + reordered.name());

            // D: JOIN with distinct aliases to avoid mixing up ids across tables.
            Purchase joined = jdbc.queryForObject("""
                    SELECT p.id AS purchase_id,
                           c.name AS buyer_name,
                           p.amount_cents AS total_cents
                    FROM purchases p
                    JOIN customers c ON c.id = p.customer_id
                    WHERE p.id = ?
                    """,
                    (rs, rowNum) -> new Purchase(
                            rs.getLong("purchase_id"),
                            rs.getString("buyer_name"),
                            rs.getLong("total_cents")),
                    101L);
            System.out.println("joined=" + joined.id() +
                    ":" + joined.buyer() + ":" + joined.cents());

            // E: SQL aggregate with an explicit alias.
            Long total = jdbc.queryForObject("""
                    SELECT COALESCE(SUM(amount_cents), 0) AS total_cents
                    FROM purchases
                    WHERE customer_id = ?
                    """,
                    (rs, rowNum) -> rs.getLong("total_cents"),
                    1L);
            System.out.println("sumCents=" + total);

            // F: Read the alias instead of the physical column name.
            List<String> names = jdbc.query(
                    "SELECT name AS display_name FROM customers ORDER BY id",
                    (rs, rowNum) -> rs.getString("display_name"));
            System.out.println("names=" + names);

            // G: getColumnLabel reflects the quoted alias on H2.
            Boolean labelMatch = jdbc.queryForObject(
                    "SELECT name AS \"public_name\" FROM customers WHERE id = ?",
                    (rs, rowNum) ->
                            "public_name".equals(
                                    rs.getMetaData().getColumnLabel(1)),
                    1L);
            System.out.println("metadataLabel=" + labelMatch);

            // H: reward_points is SQL NULL; primitive int is not enough.
            Boolean pointsNull = jdbc.queryForObject(
                    "SELECT reward_points FROM customers WHERE id = ?",
                    (rs, rowNum) -> {
                        rs.getInt("reward_points");
                        return rs.wasNull();
                    },
                    1L);
            System.out.println("pointsWasNull=" + pointsNull);
        }
    }
}
```

In the directory containing `build.gradle`, run:

```bash
gradle run
```

With the project's Gradle Wrapper, use `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows). The stdout produced by the program's `System.out.println` statements is:

```text
byName=1:Lan
byIndex=1:Lan
reordered=1:Lan
joined=101:Lan:25000
sumCents=65000
names=[Lan, Minh]
metadataLabel=true
pointsWasNull=true
```

Gradle/Spring logs may also appear. **Explanation:**

1. `byName` and `byIndex` fetch the same customer `id=1` using the two overloads.
2. `reordered` stays correct because the indexes were updated when `SELECT` changed order.
3. `joined` reads `purchase_id`/`buyer_name`/`total_cents`, avoiding primary-key confusion across tables.
4. Lan's two purchases are 25,000 and 40,000 cents, so `sumCents=65000`.
5. `names` reads the `display_name` alias and preserves `ORDER BY id`.
6. `metadataLabel=true` because H2 preserves the double-quoted alias `"public_name"` in exact lowercase.
7. `pointsWasNull=true` because customer id 1 has no SQL value for `reward_points` yet; `getInt` returns 0, while `wasNull` distinguishes it.

In each `RowMapper`, `JdbcTemplate` invokes the callback on the positioned row and manages closing the result set/statement/connection afterward.

### 12.2. Modify the SQL Yourself to See the Risks

- Change `SELECT id, name` in case B to `SELECT name, id` without updating the mapper: `getLong(1)` will receive the `name` column and may throw a type conversion error.
- Change `p.id AS purchase_id` in case D to `p.id AS order_id` while keeping `getLong("purchase_id")`: the label no longer exists; the test must fail.
- Change `name AS display_name` in case F to `name AS buyer_name`: update the corresponding getter or keep the old alias if you want to preserve the contract.
- Set `reward_points=0` for customer id 1: case H must become `pointsWasNull=false`, distinguishing a real 0 from NULL.
- In case G, try an unquoted alias to observe the difference between SQL phrasing and metadata casing on H2.

**Do not** run broken variants against a production database; these are experiments to understand the contract.

## 13. Property-Based Mapping: BeanPropertyRowMapper

Spring provides `BeanPropertyRowMapper` to bind columns to JavaBean properties by name. If a DTO has fields `customerId` and `displayName` (with matching setters), the SQL should emit appropriate labels:

```sql
SELECT id AS customer_id,
       name AS display_name
FROM customers;
```

Illustrative example, not part of the runnable file in Section 12:

```java
public class CustomerDto {
    private Long customerId;
    private String displayName;

    public Long getCustomerId() { return customerId; }
    public void setCustomerId(Long customerId) {
        this.customerId = customerId;
    }
    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

```java
List<CustomerDto> values = jdbcTemplate.query("""
        SELECT id AS customer_id,
               name AS display_name
        FROM customers
        """, new BeanPropertyRowMapper<>(CustomerDto.class));
```

`BeanPropertyRowMapper` supports the `snake_case` → `camelCase` naming convention. **It does not automatically infer** that the physical column `id` corresponds to property `customerId` without an appropriate alias. When mapping fails, check the actual labels before suspecting getters/setters.

### DataClassRowMapper and Records

`DataClassRowMapper` supports mapping data into constructors / Java records when parameter/record component names and labels match according to Spring's rules.

```java
record PurchaseDto(long purchaseId, String buyerName) {}
```

SQL:

```sql
SELECT p.id AS purchase_id,
       c.name AS buyer_name
FROM purchases p
JOIN customers c ON c.id = p.customer_id;
```

Snippet:

```java
List<PurchaseDto> purchases = jdbcTemplate.query(
        sql,
        new DataClassRowMapper<>(PurchaseDto.class));
```

`sql` in this snippet represents the query string shown above, not yet a variable defined in the runnable file. With automatic mappers, the rule remains that **SQL labels must match properties/constructor parameters**. When type conversions, combining multiple fields, or business calculations are needed, a manual mapper is usually clearer.

## 14. Map, ColumnMapRowMapper, and Duplicate Labels

`JdbcTemplate.queryForList` can return `List<Map<String,Object>>`:

```java
List<Map<String, Object>> rows = jdbcTemplate.queryForList("""
        SELECT id AS customer_id,
               name AS display_name
        FROM customers
        ORDER BY id
        """);
```

The map uses the **column label** as the key per the mapper's mechanism, though display casing and value types depend on the driver/Spring. When two columns share the same label (for example two `ID`s), a single Map cannot represent two separate values under the same key; one value risks being overwritten or inaccessible as expected.

Therefore:

- Use **unique labels** for distinct fields, especially in JOINs.
- Do not rely on casing (`id` vs `ID`) to distinguish columns.
- If an external API requires exact JSON keys, map deliberately to a DTO or create explicit keys.
- For type-sensitive data, `Object` values in the Map may need conversion; do not assume every `BIGINT` is always returned as the same Java class by every driver when using `getObject`.

When reading a single value, use the scalar overload to avoid writing a mapper:

```java
Long count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM customers",
        Long.class);
```

This overload expects a single-row, single-column result; if the result set size does not match, Spring may throw an exception such as `EmptyResultDataAccessException` or `IncorrectResultSizeDataAccessException`. Do not treat it as a way to read multiple rows.

## 15. Avoid SELECT * for Long-Term Mapping

```sql
SELECT *
FROM customers c
JOIN purchases p ON p.customer_id = c.id;
```

Problems:

1. There may be two `id` columns with duplicate labels.
2. When the schema changes, the number of columns in `SELECT *` changes too.
3. Index-based mappers can read the wrong column after a migration.
4. The query pulls unnecessary data, easily increasing transfer/processing cost.
5. Automatic mapping and Maps struggle to distinguish fields with identical labels.

Make the projection explicit:

```sql
SELECT p.id AS purchase_id,
       c.id AS customer_id,
       c.name AS buyer_name,
       p.amount_cents AS amount_cents
FROM purchases p
JOIN customers c ON c.id = p.customer_id;
```

When changing the output, update SQL and Java together, along with tests. If a shared API needs to return multiple projections, do not reuse the same default mapper across all of them when the labels differ.

## 16. Staying Safe with Dynamic Column/Alias Names

JDBC/`JdbcTemplate` `?` placeholders are for binding **data values**:

```sql
SELECT id AS customer_id, name AS display_name
FROM customers
WHERE id = ?;
```

Calling code:

```java
Customer result = jdbcTemplate.queryForObject(
        "SELECT id AS customer_id, name AS display_name "
        + "FROM customers WHERE id = ?",
        (rs, rowNum) -> new Customer(
                rs.getLong("customer_id"),
                rs.getString("display_name")),
        selectedId);
```

You cannot use `?` to bind **identifiers** such as table names, column names, aliases, or `ASC/DESC` keywords. If dynamic column selection or `ORDER BY` is needed, build an allowlist of permitted identifiers and only interpolate values from that allowlist into the SQL. Never concatenate unvalidated free-form input into SQL just because the getter ultimately reads by label.

## 17. Common Errors and Diagnostic Workflow

| Symptom | Common cause | Solution |
| --- | --- | --- |
| `Column not found: id` | SQL uses `id AS customer_id`, mapper still calls `getLong("id")` | Update getter to use the label or preserve the SQL label |
| Result has wrong ID | JOIN has two duplicate `id` labels | Distinct aliases `purchase_id`, `customer_id` |
| `getLong(1)` conversion error | Changed `SELECT id,name` to `name,id` | Update index or read by label |
| `getString(0)` error | JDBC index is 1-based | Start from 1 |
| Mapper missing field | Alias does not match JavaBean/constructor property | Check metadata labels and mapping rules |
| Value 0 instead of null | `getInt`/`getLong` on SQL NULL | `wasNull()` or nullable wrapper |
| Scalar query throws exception | Not exactly 1 row / 1 column | Choose the right overload and handle empty/multiple |
| Metadata label uppercase | Database normalizes unquoted identifiers | Check quoting/driver rules; do not change labels arbitrarily |
| Map loses field on JOIN | Duplicate column labels | Define unique aliases |
| `ResultSet closed` | Returned raw result set out of callback | Materialize DTO/record inside the mapper |

**Debug workflow:** inspect the SQL select-list → list expected labels in order → check result set metadata on the real driver → cross-check each getter/type/nullability → run integration tests for alias, JOIN, NULL, and reordering cases.

## 18. Pull Request Review Checklist

1. Are all columns used by the mapper present in the select-list?
2. If `AS` is used, does the mapper read by **alias** rather than guessing the physical name?
3. Do JOINs have unique labels for ID/NAME/TOTAL columns from multiple tables?
4. When using indexes, do they start from 1 and remain valid after reordering?
5. Does every `RowMapper` only read the current row, without calling `next()`/`close()`?
6. Is `NULL` kept distinct from 0/false where business logic requires it?
7. Do getters have matching data types, without arbitrarily converting `VARCHAR` to numbers?
8. Do `BeanPropertyRowMapper`/`DataClassRowMapper` have SQL label names matching Java properties/constructors?
9. Has `SELECT *` been replaced with explicit projections on critical paths?
10. Are dynamic aliases, if any, validated against an allowlist?
11. Are there tests against real SQL covering labels/types/NULL, not just unit tests with mocked mappers?
12. Are missing-column errors surfaced rather than swallowed into fake data?

## 19. Practice Exercises

**Exercise 1 — Reading by alias and position.** Given SQL `SELECT name AS display_name, id AS customer_id FROM customers`. Write a mapper returning record `Customer(long id, String name)` by **alias**; then rewrite it by **index**. Answer:

```java
// By alias
(rs, rowNum) -> new Customer(
        rs.getLong("customer_id"),
        rs.getString("display_name"))

// By index (name at column 1, id at column 2)
(rs, rowNum) -> new Customer(
        rs.getLong(2),
        rs.getString(1))
```

**Exercise 2 — JOIN with two IDs.** From tables `purchases` and `customers`, output `purchase_id`, `customer_id`, `buyer_name` and map to record `PurchaseCustomer(long purchaseId, long customerId, String buyerName)`. Do not use `getLong("id")`.

**Exercise 3 — Aggregate.** Write `SELECT COUNT(*) AS purchase_count, COALESCE(SUM(amount_cents),0) AS total_cents FROM purchases WHERE customer_id=?`. The mapper must return both the transaction count and total amount, independent of column order.

**Exercise 4 — SQL NULL.** Add a customer with `reward_points=0` and a customer with `reward_points=NULL`. Use `rs.getInt` and `rs.wasNull` to confirm the two cases differ. Try `rs.getObject("reward_points", Integer.class)` on H2 and compare.

**Exercise 5 — Metadata and real database.** On H2, query `SELECT name AS "public_name" ...` and print `getColumnLabel(1)` and `getColumnName(1)`. Try an unquoted alias; if you have PostgreSQL/MySQL tests, run again and note the differences. Do not write code dependent on unverified casing/metadata behavior.

## 20. References

- Java SE 17, `ResultSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html
- Java SE 17, `ResultSetMetaData`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSetMetaData.html
- Spring Framework 6.2, `RowMapper`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/RowMapper.html
- Spring Framework 6.2, `JdbcTemplate`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework, JDBC query APIs: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework 6.2, `BeanPropertyRowMapper`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html
- Spring Framework 6.2, `DataClassRowMapper`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html

**Summary:** Reading by column name and by alias are both reading by **column label**; reading by position is reading by **1-based select-list index**. For JOINs, expressions, and long-lived DTOs, define explicit and unique aliases. Verify SQL together with mappers against a real driver/database to avoid silent bugs.