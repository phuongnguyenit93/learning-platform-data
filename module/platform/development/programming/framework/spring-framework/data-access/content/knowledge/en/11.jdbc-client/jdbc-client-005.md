# Choosing Result Type or RowMapper in Spring JdbcClient

## 1. The Question: When to Specify a Class vs. Writing a Custom RowMapper?

`JdbcClient` is a fluent API introduced in **Spring Framework 6.1**, in the `org.springframework.jdbc.core.simple` package. It helps write queries, bind parameters, and choose result shapes on top of Spring JDBC. After `sql(...)` and `param(...)` calls, you commonly encounter two mapping approaches:

```java
// Automatic mapping by class/record:
List<Product> products = jdbcClient.sql("""
        SELECT id, product_name, quantity
        FROM products
        ORDER BY id
        """)
    .query(Product.class)
    .list();

// Explicit mapping via a RowMapper callback:
List<Product> products2 = jdbcClient.sql("""
        SELECT id, product_name, quantity
        FROM products
        ORDER BY id
        """)
    .query((rs, rowNum) -> new Product(
        rs.getLong("id"),
        rs.getString("product_name"),
        rs.getInt("quantity")))
    .list();
```

The two snippets above are **illustrative snippets only**: they assume an existing `JdbcClient jdbcClient` and a matching Java record/class `Product`. The standalone runnable Java 17 program in section 9 provides complete filenames, imports, and structure.

**Main question of this lesson:** should you use `query(Class<T>)` for Spring to map automatically, or `query(RowMapper<T>)` to decide column by column yourself? The answer depends on **result shape**, **how closely column names match Java properties**, **value conversion rules**, and **testing responsibility**—not on which approach feels "newer" or "faster" by intuition.

After this lesson, you should be able to:

1. Explain the pipeline `sql(...).param(...).query(...).list()/single()/optional()`.
2. Distinguish `query(Integer.class)` for a single scalar column from `query(MyRecord.class)` for a multi-column row.
3. Use `query(MyClass.class)` for JavaBeans, records, and field holders with compatible names/types.
4. Use `query(RowMapper<T>)` when aliases differ from names, or when conversion logic, NULL handling, enums, JOINs, or custom result structures are needed.
5. Choose `list()`, `set()`, `single()`, `optional()`, or `stream()` with the right cardinality and lifecycle; recognize errors for 0 or multiple rows.
6. Distinguish mapper-less `query()` (Map, column, rowSet) from `query(Class)` and `query(RowMapper)`.
7. Run the Java 17 + Spring JDBC + H2 example, verify stdout, and complete the practice exercises.

**Scope:** result mapping in `JdbcClient`. Opening transactions, pool management, batching, and stored procedures are only mentioned where they help define API boundaries.

## 2. Visualizing the Three Processing Steps

```text
JdbcClient.sql(SQL)
       │
       ├─ .param(name, value), .param(value), .paramSource(...)
       │        → defines bound values
       ▼
 .query(Class<T>)            .query(RowMapper<T>)         .query()
       │                           │                        │
       │ auto-selects mapper       │ callback reads rs      │ no DTO type chosen
       │ for scalar / property     │ for each row           │ returns row map / column / rowSet
       ▼                           ▼                        ▼
 MappedQuerySpec<T>          MappedQuerySpec<T>           ResultQuerySpec
       │                           │                        │
       ├─ list()                   ├─ list()                 ├─ listOfRows()
       ├─ single()                 ├─ single()               ├─ singleRow()
       ├─ optional()               ├─ optional()             ├─ singleColumn()
       ├─ set()                    ├─ set()                  ├─ singleValue()
       └─ stream()                 └─ stream()               └─ rowSet()
```

Distinguish **two independent decisions**:

- **What type should each row map to?** Decided in `query(Class<T>)` or `query(RowMapper<T>)`.
- **How many rows should be returned and in what structure?** Decided in `list()`, `single()`, `optional()`, `set()`, or `stream()`.

Thus `query(Product.class).list()` and `query(Product.class).single()` use the same logic to convert one row into a `Product`, but differ in their **row-count contract**. `query(Product.class)` does not automatically pick the first row; the terminal method decides.

`JdbcClient` is not an ORM: it does not auto-generate `SELECT` for entities, does not track object state, does not lazy-load associations, and does not compute joins or persist objects automatically. You still write SQL and remain responsible for columns, aliases, WHERE, ORDER BY, and business boundaries.

## 3. query(Class<T>): Automatic Mapping by Target Class

### 3.1. Single Scalar Column

For SQL returning **one column and one row**:

```java
int total = jdbcClient.sql("SELECT COUNT(*) FROM products")
        .query(Integer.class)
        .single();
```

`Integer.class` is a **single-value type**. `JdbcClient` uses single-column mapping (corresponding to `SingleColumnRowMapper`) to convert the JDBC result into the requested type. You can also choose `Long.class`, `String.class`, `BigDecimal.class`, or any type appropriately supported by Spring/the driver, though you should not assume every Java type can convert from every SQL type.

Example of a string value:

```java
String sku = jdbcClient.sql("""
        SELECT sku
        FROM products
        WHERE id = :id
        """)
    .param("id", 11L)
    .query(String.class)
    .single();
```

This is a snippet inside a class that has `JdbcClient` and a `products` table. If the SQL returns **two columns**, `query(String.class)` is not how to read a row into a String; scalar mappers normally require exactly one column and fail when the shape is incompatible.

### 3.2. Multiple Columns into a Record

Suppose we have the record:

```java
public record Product(
        long id,
        String productName,
        int quantity) {}
```

SQL produces matching column labels:

```sql
SELECT id,
       product_name,
       quantity
FROM products
ORDER BY id;
```

When calling:

```java
List<Product> items = jdbcClient.sql("""
        SELECT id, product_name, quantity
        FROM products
        ORDER BY id
        """)
    .query(Product.class)
    .list();
```

Spring JDBC can use **`SimplePropertyRowMapper`** to map columns into records/classes. This mapper supports constructors with matching parameter names, bean setters, and corresponding fields—not only JavaBeans with setters. Spring supports matching `product_name` to `productName` by convention; however, you must **verify with integration tests against the actual SQL/driver/types** rather than assuming every alias is inferred.

Important requirements:

- Column labels must match parameter/property names according to mapper rules; aliases are the clearest way to align them.
- Constructor and field types must be compatible with the actual JDBC values.
- The mapped class should be a top-level or `static` nested class, not a non-static inner class requiring an enclosing instance.
- Records are immutable; the mapper creates a new object per row and does not update records when the database changes.
- There is no guarantee of automatically handling nested objects, collections, one-to-many relationships, or object graphs like an ORM.

### 3.3. JavaBeans and Field Holders

Records are not mandatory. JavaBean example:

```java
public static class ProductBean {
    private Long id;
    private String productName;

    public ProductBean() {}

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getProductName() { return productName; }
    public void setProductName(String productName) {
        this.productName = productName;
    }
}
```

The SQL `SELECT id, product_name FROM products` can map into `ProductBean.class`. `SimplePropertyRowMapper` also supports matching fields in a suitable field holder; that is one difference from plain `BeanPropertyRowMapper`, which typically relies on JavaBean setters.

**Precedence order** when the same target has matching constructor parameters, setters, and fields: constructor arguments take precedence, followed by setters, then field mapping. Do not rely on complex fallback paths to mask a class with an unclear contract; if a DTO has multiple ways to populate the same field, test it accurately.

### 3.4. Aliases Are a Contract, Not Magic

Given a SQL query:

```sql
SELECT p.id AS product_id,
       p.name AS display_name,
       p.stock_quantity AS quantity
FROM products p;
```

Expected record:

```java
record ProductView(long productId, String displayName, int quantity) {}
```

The aliases `product_id`, `display_name`, and `quantity` allow the mapper to match components `productId`, `displayName`, and `quantity` by convention. Conversely, if the SQL outputs `p.name AS title` while the record only has `displayName`, the mapper will not automatically guess that `title` means `displayName`.

**How to fix:** change the alias to a mappable name, update the DTO, or write a manual `RowMapper`. For JOINs or aggregate queries, always assign clear/unique aliases instead of `SELECT *`.

## 4. query(RowMapper<T>): Deciding How to Map Each Row Yourself

`RowMapper<T>` is a callback with the method `mapRow(ResultSet rs, int rowNum)`. Spring has already positioned the `ResultSet` cursor at the current row before calling the callback; the mapper just reads the columns and returns an object.

```java
RowMapper<ProductView> mapper = (rs, rowNum) -> {
    long id = rs.getLong("product_id");
    String title = rs.getString("display_name");
    int quantity = rs.getInt("quantity");
    return new ProductView(id, title, quantity);
};

List<ProductView> products = jdbcClient.sql("""
        SELECT p.id AS product_id,
               p.name AS display_name,
               p.stock_quantity AS quantity
        FROM products p
        ORDER BY p.id
        """)
    .query(mapper)
    .list();
```

This is a conceptually self-contained snippet requiring the `ProductView` record and corresponding table. When you need control over:

- Which columns to read (by label name or 1-based position).
- Java types: `getBigDecimal`, `getObject(..., LocalDate.class)`, or driver-specific mappings.
- Conversion logic such as `"A" → Status.ACTIVE`, cents → business currency units, or intentional formatting/parsing.
- Null values: `rs.wasNull()` or nullable object getters.
- Aliases/types that do not map 1-to-1 to Java properties.
- Complex per-row mapping while keeping the DTO immutable.

a `RowMapper` is usually easier to read, easier to test, and clearer in responsibility than a string of contrived aliases just to force automatic mapping.

### 4.1. What Not to Do Inside a RowMapper

**Do not** call `rs.next()`, `rs.close()`, or close connections/statements provided by Spring. `JdbcClient` uses `JdbcTemplate`/`NamedParameterJdbcTemplate` infrastructure to coordinate resources. `rowNum` starts at 0 and is the **row number**; `rs.getString(1)`, by contrast, uses a **column** index starting at 1.

```java
// WRONG: this illustrates an anti-pattern only, do not run.
(rs, rowNum) -> {
    rs.next();              // The template already advances the ResultSet.
    return rs.getString(rowNum); // rowNum=0 on the first row; column indices start at 1.
}
```

Do not return `ResultSet`, a cursor-backed `InputStream`, or `PreparedStatement` out of a mapper. If you need data after calling `list()` or `single()`, materialize it into an independent Java object **inside the callback**.

### 4.2. Avoid Side Effects and N+1 Queries Inside a Mapper

You should avoid:

- Issuing another query per row just to populate an extra property (N+1 queries).
- Writing to the database or making HTTP calls inside a mapper.
- Using mutable state shared across threads/requests.
- Swallowing `SQLException` and returning a half-populated object.
- Running heavy business rules that hold JDBC resources open for a long time inside the callback.

If a DTO needs data from two tables, consider an appropriate JOIN/projection and map each row cleanly; if you need to group multiple rows into a complex structure, `ResultSetExtractor` may fit better than `RowMapper`.

## 5. Decision Table: Class or RowMapper?

| Scenario | Start with | Reason |
| --- | --- | --- |
| `SELECT COUNT(*)`, single numeric value | `query(Integer.class).single()` | Single-column scalar mapping |
| `SELECT name ...`, single String | `query(String.class)` | No separate DTO/mapper needed |
| Record with names/types matching column labels | `query(MyRecord.class)` | Less boilerplate, constructor mapping |
| Simple JavaBean with setters | `query(MyBean.class)` | Leverages property mapping |
| Class with matching fields only | `query(MyClass.class)` if valid constructor/fields supported | SimplePropertyRowMapper handles simple structures |
| JOIN with stable aliases and matching DTO | `query(MyDto.class)` | Automatic mapping when contract matches |
| JOIN with duplicate `id` columns, inconsistent aliases | `query(RowMapper<T>)` after aliasing SQL | Explicit control over columns read |
| SQL NULL must be distinguished from 0/false | `query(RowMapper<T>)` or suitable wrapper DTO | Controls semantics |
| Monetary decimal / enum / business conversion | `query(RowMapper<T>)` | Explicit type conversion |
| Single row combining multiple fields into a new value | `query(RowMapper<T>)` | Separates SQL projection from transformation |
| Multiple rows aggregated into one complex structure | `query(ResultSetExtractor<T>)` | Controls the entire ResultSet |
| Only need Maps/rowsets for flexible inspection | `query().listOfRows()` / `rowSet()` | No fixed DTO needed |

The speed of an approach depends on the query, driver, row count, DTO structure, conversions, and environment. **Do not conclude that a manual mapper is always faster** or that an automatic mapper is always safer. Benchmark if throughput is a requirement; by default prioritize clarity, stability, and test coverage.

## 6. Choosing Result Cardinality: list, single, optional, set, stream

After `query(Class<T>)` or `query(RowMapper<T>)`, you obtain a `JdbcClient.MappedQuerySpec<T>`. It provides these key terminal methods:

### 6.1. list(): 0..N Rows

```java
List<Product> products = jdbcClient.sql("""
        SELECT id, product_name, quantity
        FROM products
        ORDER BY id
        """)
    .query(Product.class)
    .list();
```

- Returns a mapped `List<T>`; returns an empty list if there are no rows.
- Rows preserve the order returned by the database. If order matters, **the SQL must include `ORDER BY`**.
- `list()` materializes all rows in memory; do not read huge tables unbounded when only a few pages are needed.

### 6.2. single(): Exactly One Object, Non-Null in Spring 6.2

```java
Product product = jdbcClient.sql("""
        SELECT id, product_name, quantity
        FROM products
        WHERE id = :id
        """)
    .param("id", 10L)
    .query(Product.class)
    .single();
```

Contract to remember:

- **Exactly one** object is required.
- **Zero rows** normally throws `EmptyResultDataAccessException`.
- **More than one row** throws `IncorrectResultSizeDataAccessException` (or an appropriate subtype).
- Starting in Spring **6.2**, `single()` requires the mapped value to be **non-null**; if a callback returns null, do not treat this as a way to accept an optional nullable value. Design your mapper/DTO accordingly.

`WHERE id = :id` only guarantees at most one row if the `id` column is a unique/primary key. Do not call `single()` on a non-unique query expecting Spring to silently pick the first row.

### 6.3. optional(): 0 or 1 Object

```java
Optional<Product> found = jdbcClient.sql("""
        SELECT id, product_name, quantity
        FROM products
        WHERE id = :id
        """)
    .param("id", 999L)
    .query(Product.class)
    .optional();
```

- Zero results → `Optional.empty()`.
- Exactly one non-null object → `Optional.of(object)`.
- Multiple results → **error**, does not silently pick one row.
- If the mapper returns null, `Optional` cannot clearly distinguish "row exists with null value" from "no row"; for nullable scalar queries, pick a clear wrapper or data contract.

**When to choose?** In a repository lookup by unique key where "not found" is a normal state: use `Optional<T>`. When absence is a business/contract violation, use `single()` and handle the appropriate exception.

### 6.4. set(): Deduplicated Collection

```java
Set<String> categories = jdbcClient.sql("""
        SELECT category
        FROM products
        ORDER BY category
        """)
    .query(String.class)
    .set();
```

Per the Javadoc, `set()` returns an ordered set preserving result encounter order, typically backed by `LinkedHashSet`. **Do not** confuse this with SQL `SELECT DISTINCT`:

- SQL may still return duplicate rows; `Set` deduplicates by Java `equals()/hashCode()` **after mapping**.
- Two records differing in a single field are two distinct elements.
- If you need distinctness at the database for performance, use `SELECT DISTINCT` or `GROUP BY` appropriately.
- Even though the set preserves read order, without `ORDER BY` the source order itself is not guaranteed.

### 6.5. stream(): Lazy, Must Be Closed

```java
try (Stream<Product> stream = jdbcClient.sql("""
        SELECT id, product_name, quantity
        FROM products
        ORDER BY id
        """)
    .query(Product.class)
    .stream()) {

    long lowStock = stream.filter(p -> p.quantity() < 5).count();
    System.out.println(lowStock);
}
```

`Stream<T>` from Spring JDBC can hold open JDBC `ResultSet`, `Statement`, and `Connection` resources until closed. Callers **must use `try-with-resources` or close explicitly**, even after calling terminal operations like `count()`, `findFirst()`, or short-circuiting pipelines.

**Do not return a JDBC stream across service/request boundaries and lose track of closing responsibility.** For large workloads, combine paging/cursors and appropriate transactions as supported by the driver; `stream()` does not automatically solve all memory or locking issues.

### Cardinality Matrix

| Actual SQL result | `list()` | `single()` | `optional()` | `set()` |
| --- | --- | --- | --- | --- |
| 0 rows | Empty list | Not-found error | `Optional.empty()` | Empty set |
| 1 row, non-null object | 1-element list | Returns object | `Optional.of(object)` | 1-element set |
| Multiple rows | Multi-element list | Incorrect size error | Incorrect size error | Set, deduplicated by Java equality |
| 1 row, mapped object null | Depends on mapper contract and nullability | Not accepted as required value (6.2) | Optional cannot distinguish row-null vs. no row | Avoid or define clear null semantics |

The table describes the general contract and does not mean you should intentionally map rows to null. In business code, row mappers should return meaningful objects; for nullable SQL scalars, choose a wrapper/`optionalValue()` or explicit handling after defining semantics.

## 7. query() Without a Mapper: Other Result Forms

`jdbcClient.sql(...).query()` returns `ResultQuerySpec`, not `MappedQuerySpec<T>`. It offers different methods:

```java
// Separate snippets, assuming jdbcClient variable and products table exist.
List<Map<String, Object>> rows = jdbcClient.sql("""
        SELECT id AS product_id, product_name
        FROM products
        ORDER BY id
        """)
    .query()
    .listOfRows();

Map<String, Object> row = jdbcClient.sql("""
        SELECT id AS product_id, product_name
        FROM products
        WHERE id = :id
        """)
    .param("id", 10L)
    .query()
    .singleRow();

Object count = jdbcClient.sql("SELECT COUNT(*) FROM products")
    .query()
    .singleValue();
```

**Options from `ResultQuerySpec`:**

| API | Result | Best for |
| --- | --- | --- |
| `listOfRows()` | `List<Map<String,Object>>` | Dynamic data / quick inspection, no DTO needed |
| `singleRow()` | `Map<String,Object>` | Single row, multiple columns |
| `singleColumn()` | `List<Object>` | Single column, multiple rows |
| `singleValue()` | `Object` | Single row, single column, required value |
| `optionalValue()` (Spring 6.2+) | `Optional<Object>` | Single value that may be absent |
| `rowSet()` | Detached `SqlRowSet` | Rowset-style access without holding a JDBC ResultSet directly |

**Note:** Map results key by column label, typically supporting case-insensitive lookup, though you should avoid duplicate aliases and avoid guessing the Java runtime type of `Object`. When a public API needs strong typing, a class or `RowMapper` is usually clearer.

Do not confuse `query().singleValue()` with `query(Integer.class).single()`: the former returns an `Object` requiring type inspection, while the latter uses a typed scalar mapper. Also do not confuse `singleRow()` (a Map for one row) with `single()` (an object of type `T`). The methods in this section **do not all exist on the same spec**; follow the right call path.

## 8. Cases for query(RowCallbackHandler) or query(ResultSetExtractor)

`JdbcClient.StatementSpec` also provides overloads taking callbacks:

```java
// Process one row at a time rather than mapping to List<T>.
jdbcClient.sql("SELECT id, sku FROM products ORDER BY id")
    .query((RowCallbackHandler) rs ->
        System.out.println(rs.getString("sku")));

// Aggregate the entire ResultSet into a single custom result.
Long sum = jdbcClient.sql("SELECT quantity FROM products")
    .query((ResultSetExtractor<Long>) rs -> {
        long total = 0;
        while (rs.next()) {
            total += rs.getLong("quantity");
        }
        return total;
    });
```

These are illustrative snippets requiring the corresponding `RowCallbackHandler` and `ResultSetExtractor` imports.

- **`RowMapper`**: template invokes once **per row**, mapper reads the current row and returns one `T`.
- **`RowCallbackHandler`**: template invokes once per row, callback performs controlled side effects; template manages `rs.next()`.
- **`ResultSetExtractor<T>`**: callback processes the **entire ResultSet**, calls `rs.next()` itself, and returns a single aggregated result.
- **Do not** manually close the `ResultSet` passed by the template into standard callbacks.

If you only need per-row DTOs, do not pick `ResultSetExtractor` just because it seems "more flexible": it adds manual iteration responsibility. Choose the callback matching the **shape of returned data**, not simply the shortest syntax.

## 9. Standalone Java 17 Practice with H2

This example uses **Java 17+**, **Spring Framework 6.2.14**, **H2 2.3.232**, and Gradle. The program uses plain Spring Framework, **without Spring Boot** or an external database installation. Versions are pinned so learners know which version's contract is being demonstrated.

### 9.1. Structure

```text
jdbc-client-result-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/JdbcClientResultDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'jdbc-client-result-demo'
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
    mainClass = 'demo.JdbcClientResultDemo'
}
```

`src/main/java/demo/JdbcClientResultDemo.java`:

```java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Stream;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class JdbcClientResultDemo {

    record InventoryItem(long id, String sku, int quantity) {}

    record InventoryBadge(String sku, String status) {}

    @Configuration
    static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:client_result;DB_CLOSE_DELAY=-1", "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        JdbcClient jdbcClient(JdbcTemplate jdbcTemplate) {
            // Reuse configuration from the existing JdbcTemplate.
            return JdbcClient.create(jdbcTemplate);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            JdbcClient client = context.getBean(JdbcClient.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE inventory (
                        id BIGINT PRIMARY KEY,
                        sku VARCHAR(40) NOT NULL,
                        quantity INTEGER NOT NULL
                    )
                    """);

            client.sql("""
                    INSERT INTO inventory(id, sku, quantity)
                    VALUES (:id, :sku, :quantity)
                    """)
                .param("id", 1L)
                .param("sku", "PEN")
                .param("quantity", 12)
                .update();

            client.sql("""
                    INSERT INTO inventory(id, sku, quantity)
                    VALUES (:id, :sku, :quantity)
                    """)
                .param("id", 2L)
                .param("sku", "NOTE")
                .param("quantity", 0)
                .update();

            client.sql("""
                    INSERT INTO inventory(id, sku, quantity)
                    VALUES (:id, :sku, :quantity)
                    """)
                .param("id", 3L)
                .param("sku", "BAG")
                .param("quantity", 5)
                .update();

            // 1) Auto-map columns into a Java record.
            List<InventoryItem> typed = client.sql("""
                    SELECT id, sku, quantity
                    FROM inventory
                    ORDER BY id
                    """)
                .query(InventoryItem.class)
                .list();
            System.out.println("typed=" +
                    typed.stream().map(InventoryItem::sku).toList());

            // 2) Manual RowMapper producing the same model.
            RowMapper<InventoryItem> explicit = (rs, rowNum) ->
                    new InventoryItem(
                            rs.getLong("id"),
                            rs.getString("sku"),
                            rs.getInt("quantity"));
            List<InventoryItem> manual = client.sql("""
                    SELECT id, sku, quantity
                    FROM inventory
                    ORDER BY id
                    """)
                .query(explicit)
                .list();
            System.out.println("manualEqual=" + typed.equals(manual));

            // 3) Manual mapper converting quantity into a status.
            List<InventoryBadge> badges = client.sql("""
                    SELECT sku, quantity
                    FROM inventory
                    ORDER BY id
                    """)
                .query((rs, rowNum) -> new InventoryBadge(
                        rs.getString("sku"),
                        rs.getInt("quantity") > 0
                                ? "READY" : "EMPTY"))
                .list();
            System.out.println("badges=" +
                    badges.stream()
                          .map(x -> x.sku() + ":" + x.status())
                          .toList());

            // 4) Scalar result: one row, one column.
            Integer total = client.sql("SELECT COUNT(*) FROM inventory")
                    .query(Integer.class)
                    .single();
            System.out.println("total=" + total);

            String firstSku = client.sql("""
                    SELECT sku FROM inventory WHERE id = ?
                    """)
                .param(1L)
                .query(String.class)
                .single();
            System.out.println("firstSku=" + firstSku);

            // 5) Required single vs. Optional: differs when no row exists.
            InventoryItem required = client.sql("""
                    SELECT id, sku, quantity
                    FROM inventory
                    WHERE id = :id
                    """)
                .param("id", 2L)
                .query(InventoryItem.class)
                .single();
            System.out.println("required=" + required.sku());

            Optional<InventoryItem> missing = client.sql("""
                    SELECT id, sku, quantity
                    FROM inventory
                    WHERE id = :id
                    """)
                .param("id", 999L)
                .query(InventoryItem.class)
                .optional();
            System.out.println("missingPresent=" + missing.isPresent());

            // 6) list() for 0..N rows with a named parameter.
            List<InventoryItem> lowStock = client.sql("""
                    SELECT id, sku, quantity
                    FROM inventory
                    WHERE quantity <= :maxQty
                    ORDER BY id
                    """)
                .param("maxQty", 3)
                .query(InventoryItem.class)
                .list();
            System.out.println("lowStock=" +
                    lowStock.stream().map(InventoryItem::sku).toList());

            // 7) No mapper passed: receive maps of SQL columns.
            List<Map<String, Object>> rows = client.sql("""
                    SELECT id AS item_id, sku AS item_sku
                    FROM inventory
                    WHERE id = :id
                    """)
                .param("id", 1L)
                .query()
                .listOfRows();
            System.out.println("rowMaps=" + rows.size());

            // 8) Stream holds JDBC resources, so it must be closed.
            long inStock;
            try (Stream<InventoryItem> stream = client.sql("""
                    SELECT id, sku, quantity
                    FROM inventory
                    ORDER BY id
                    """)
                .query(InventoryItem.class)
                .stream()) {
                inStock = stream.filter(item -> item.quantity() > 0).count();
            }
            System.out.println("streamAvailable=" + inStock);
        }
    }
}
```

### 9.2. Running

In the directory containing `build.gradle`, run using Gradle with a Java 17 toolchain:

```bash
gradle run
```

If Gradle Wrapper is set up: on Linux/macOS run `./gradlew run`, and on Windows run `gradlew.bat run`. The lines **printed by the program itself via `System.out`** (excluding Gradle/Spring logs) are expected to be:

```text
typed=[PEN, NOTE, BAG]
manualEqual=true
badges=[PEN:READY, NOTE:EMPTY, BAG:READY]
total=3
firstSku=PEN
required=NOTE
missingPresent=false
lowStock=[NOTE]
rowMaps=1
streamAvailable=2
```

### 9.3. Why Are the Results Like This?

- Three `INSERT`s create `PEN(12)`, `NOTE(0)`, and `BAG(5)`, and `ORDER BY id` preserves read order. `typed=[PEN, NOTE, BAG]` shows the records were mapped via `InventoryItem.class`.
- `manualEqual=true` proves that for this projection, manually reading the three columns via `RowMapper` produces equal records (Java records have value equality across components).
- `badges` demonstrates why a manual mapper is needed: SQL has no `status` column, so the callback **computes** `READY` or `EMPTY` from `quantity`.
- `COUNT(*)` returns a scalar, so `query(Integer.class).single()` suffices; `total=3`.
- `firstSku=PEN` uses `?` positional binding, unlike `:id` named binding elsewhere. Both binding styles are supported by `JdbcClient`.
- The query `WHERE id=2` matches one row so `single()` returns `NOTE`; the query `id=999` matches no row so `optional().isPresent()` is false.
- `lowStock` filters `quantity <= 3`, leaving only `NOTE`.
- `query().listOfRows()` for `id=1` returns one row map, so `rowMaps=1`.
- The stream reads three rows, filters those with quantity greater than 0 to get two rows, and is **closed inside `try-with-resources`**.

### 9.4. Limitations of This Demo

The example uses `DriverManagerDataSource` **without pooling** to minimize dependencies; this is not the default choice for production under load. In-memory H2 is quick to run, though type conversion, precision, SQL dialect, and naming can differ from PostgreSQL/MySQL/Oracle. For real services, use a properly managed connection pool, externalize secrets outside source code, and run integration tests against a production-compatible database.

This demo is a **console application** without `@Transactional`. `JdbcClient` reuses Spring JDBC's connection/exception infrastructure, but does not turn multiple `update()` calls into a business transaction on its own.

## 10. Common Mistakes When Choosing Class<T>

### 10.1. Scalar Mapping When SQL Has Multiple Columns

```java
// WRONG: result has 2 columns, cannot be read wholly into a String.
String value = jdbcClient.sql(
        "SELECT sku, quantity FROM inventory WHERE id = 1")
    .query(String.class)
    .single();
```

Fix by selecting only `SELECT sku`, using an `InventoryItem`/`InventoryBadge` DTO, or writing an appropriate `RowMapper`.

### 10.2. Class Properties Not Matching Column Names

```java
record ProductCard(long productId, String displayName) {}
```

The SQL `SELECT id, sku FROM inventory` does not produce labels `product_id` or `display_name`. The mapper cannot guess that `id` is `productId` and `sku` is `displayName`. Fix with aliases:

```sql
SELECT id AS product_id, sku AS display_name
FROM inventory;
```

Or write a `RowMapper` specifying the exact position/label of each column. **Do not rely on accidental naming guesses by the driver.**

### 10.3. SQL NULL into a Primitive

`int quantity` cannot represent "unknown quantity" distinctly from 0. If `quantity` allows NULL, choose `Integer` with appropriate mapping or handle it inside a `RowMapper`:

```java
int raw = rs.getInt("quantity");
Integer quantity = rs.wasNull() ? null : raw;
```

Check `wasNull()` **immediately after** the primitive getter, as it reflects the most recent column read. Avoid defaulting to 0 if business logic distinguishes SQL NULL from an actual 0.

### 10.4. Enums, JSON, and Uncommon Types

Do not assume `query(MyRecord.class)` automatically deserializes JSON strings into complex classes, resolves custom enum codes, or converts monetary `BigDecimal` values into custom domain types. For conversions requiring business rules, write a dedicated `RowMapper` (or configure a conversion service properly per the API and version in use).

### 10.5. Multiple Tables with Duplicate Column Names

`SELECT a.id, b.id` produces duplicate column labels; name/alias-based mappers can read the wrong column. Assign aliases `a.id AS account_id`, `b.id AS owner_id` and map explicitly. If you still use `query(Class)`, the aliases must match the DTO; if the logic is complex, a `RowMapper` is usually clearer.

### 10.6. Merely Changing .list to .single

`single()` is not `limit(1)`. If the query returns multiple rows, this method must raise a cardinality error rather than picking a row arbitrarily. When business logic wants one "latest" row, SQL must specify `ORDER BY ... LIMIT 1` (or the database's equivalent syntax) and handle missing rows.

## 11. Common Mistakes When Writing a Custom RowMapper

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ResultSet closed` / missing rows | Mapper calls `rs.next()` or `rs.close()` | Only read the current row, let Spring manage the cursor |
| Reading the wrong `id` in a JOIN | Columns share the label `id` | Use distinct aliases and read by alias |
| `Column not found` | SQL alias changed without updating mapper | Verify select-list and `ResultSetMetaData.getColumnLabel` |
| Lost distinction for NULL | `getInt` returns 0 for SQL NULL | Use `wasNull()` or wrapper type |
| Wrong DTO values despite query running | Getter reads wrong index (JDBC is 1-based) | Prefer column labels or align ordinals |
| Slow with many rows | Subquery executed inside each `mapRow` | Use JOIN/batching/paging instead of N+1 |
| Resource leak | Returning `ResultSet`/cursor-backed stream | Materialize DTO in callback; close terminal stream |
| Wrong data returned | Ignoring `SQLException` and returning defaults | Let Spring translate exceptions, test on real DB |

If a mapper needs to combine multiple rows into one object, `ResultSetExtractor` may fit better: it iterates `rs.next()` inside its callback. `RowMapper` is for when **each row corresponds to one object**.

## 12. Testing Result Selection Against Contracts

Do not only test that a query "throws no exception". Verify both **shape** and **semantics**:

| Test case | Setup | Expectation |
| --- | --- | --- |
| 1-column scalar | `SELECT COUNT(*)` | `query(Integer.class).single()` returns exact count |
| Multi-column scalar | `SELECT sku, quantity` with `query(String.class)` | Detects incompatible shape |
| Matching record | `SELECT id, sku, quantity` | `query(InventoryItem.class).list()` populates all three fields |
| Different record alias | `SELECT sku AS item_code` | Mapper/record must be aligned or use RowMapper |
| Equivalence of two mappers | Same select-list query | Auto and custom produce equal objects |
| Custom transform | Quantity 0 and >0 | `EMPTY`/`READY` status is accurate |
| No rows | `WHERE id=999` | `optional()` is empty, `single()` throws |
| Multiple rows | Non-unique query | Both `single()` and `optional()` throw |
| NULL | Nullable column + wrapper | Distinguishes null from default values |
| Many rows | Query with paging/streaming | Does not consume excessive memory, stream closes |
| JOIN | Two tables with `id` columns | Distinct aliases, no key confusion |
| Real database | Run with production driver | Verifies aliases/casing/types/NULL |

### Cardinality Test Snippet

```java
// Snippet for use in a test with JdbcClient and inventory table.
// Intended for JUnit/AssertJ assertions, not for running in main demo.
Optional<InventoryItem> missing = client.sql("""
        SELECT id, sku, quantity
        FROM inventory WHERE id = :id
        """)
    .param("id", -1L)
    .query(InventoryItem.class)
    .optional();

// Assert: missing.isEmpty() == true.
// Calling .single() on the same query throws EmptyResultDataAccessException.
```

In integration tests, use `assertThatThrownBy` or `assertThrows` from your test framework with the expected exception type. Do not use Java `assert` for production validation, as JVM assertions are typically disabled by default.

## 13. Organizing Repository Code for Long-Term Use

Example of a repository with constructor-injected `JdbcClient`:

```java
@Repository
public class InventoryRepository {
    private final JdbcClient client;

    public InventoryRepository(JdbcClient client) {
        this.client = client;
    }

    public Optional<InventoryItem> findById(long id) {
        return client.sql("""
                SELECT id, sku, quantity
                FROM inventory
                WHERE id = :id
                """)
            .param("id", id)
            .query(InventoryItem.class)
            .optional();
    }

    public List<InventoryBadge> findBadges() {
        return client.sql("""
                SELECT sku, quantity
                FROM inventory
                ORDER BY id
                """)
            .query((rs, rowNum) -> new InventoryBadge(
                    rs.getString("sku"),
                    rs.getInt("quantity") > 0 ? "READY" : "EMPTY"))
            .list();
    }
}
```

This is an **illustrative snippet** and does not compile standalone yet: it needs the `@Repository` import, matching DTOs/records, component scanning or bean registration, and a `JdbcClient` bean. The full program is in section 9.

**Design tip:** if the SQL has a simple DTO contract, keep `query(Class)` close to the SQL. If mapping requires transformation, extract a dedicated `RowMapper` when logic is reused across places or needs dedicated unit tests. Avoid cramming complex business logic into a long lambda.

### Do You Need a New JdbcClient for Every Call?

No. You can define a shared singleton `JdbcClient` bean, as in the demo. The client is a facade over Spring's JDBC operations; it does not hold a single shared `Connection` across requests. `JdbcClient.create(jdbcTemplate)` reuses the existing `JdbcTemplate` configuration. With Spring Boot, auto-configuration may be available when conditions and versions match; never assume every project already has the bean without checking the context.

### Transactions and Errors

- `JdbcClient` uses Spring JDBC infrastructure to acquire/release connections and handle `DataAccessException`; it can join Spring transactions when configured.
- `query(Class)` or `query(RowMapper)` only determines mapping, **not** when a transaction starts.
- `RowMapper` should let `SQLException` be handled by Spring; never swallow errors to return dummy DTOs.
- For service transactions and multiple writes, use `@Transactional` or `TransactionTemplate` with your configured infrastructure.
- If you do not need `JdbcClient`'s fluent features or need advanced callbacks/batching/stored procedures, `JdbcTemplate`/`NamedParameterJdbcTemplate` and `SimpleJdbcInsert`/`SimpleJdbcCall` remain the right tools.

## 14. Guided Practice Exercises

**Exercise 1 — Choose a mapper without redundant code.** From table `inventory(id,sku,quantity)`, fetch all skus ordered by id. Use `query(String.class).list()` and explain why no record is needed.

```java
List<String> skus = client.sql("""
        SELECT sku FROM inventory ORDER BY id
        """).query(String.class).list();
```

**Exercise 2 — Map to a DTO by class.** Define `record InventoryItem(long id, String sku, int quantity)`, query the three columns `id, sku, quantity`, and call `query(InventoryItem.class).list()`. Try changing `sku AS product_code`, observe the contract mismatch, and fix it with alias `sku` or an explicit `RowMapper`.

**Exercise 3 — Status logic.** Return `OUT` for `quantity=0`, `LOW` for 1 to 4, and `OK` for 5 or more. Write a `RowMapper<InventoryBadge>` and test the boundary values 0/1/4/5. Do not try to use `query(InventoryBadge.class)` when the SQL lacks a matching status column.

**Exercise 4 — Cardinality.** Call `single()` on a query returning zero rows and then on a query returning three rows; record the exceptions. Switch to `optional()` for zero-or-one and `list()` for zero-or-many.

**Exercise 5 — SQL NULL.** Add `discount_percent INTEGER NULL` to the projection; write a record using `Integer` and a row mapper handling `rs.getInt` + `wasNull()`. If using automatic `query(Class)`, verify output/null behavior on the target driver.

**Exercise 6 — Stream lifecycle.** Obtain a `stream()` and call `findFirst()`. Explain why the stream must still be closed even though the pipeline short-circuits early. Fix the code using `try-with-resources`.

**Exercise 7 — Map or DTO?** For an admin query with a dynamic column set, consider `query().listOfRows()`; for a public API with a fixed schema, choose a record/`RowMapper` and explain type and alias control.

## 15. Pre-Merge Code Review Checklist

1. Does the query return **one column** or **multiple columns**? Is a scalar class accidentally used for multiple columns?
2. Do class/record property/constructor names match column labels? Is `snake_case`/`camelCase` conversion tested?
3. If the SQL uses JOIN/aggregates, are aliases unique and unambiguous?
4. Does the query satisfy the cardinality expected by `single()`/`optional()`?
5. When 0..N results are needed, are `list()`/`set()` used along with `ORDER BY` if ordering matters?
6. If using `stream()`, does the caller close the stream even on exceptions or short-circuiting?
7. If using `RowMapper`, does the callback avoid `next()`/`close()`/side effects?
8. Are SQL NULLs and Java primitive/wrapper types compatible?
9. Are SQL params bound via `param(...)` rather than concatenating untrusted strings?
10. Do Map results avoid duplicate aliases or unchecked Java runtime types?
11. Are there tests **running real SQL** covering 0/1/many rows, nullability, aliases, and conversions?
12. If code becomes complex with a heavy mapper, should it be extracted to a dedicated class/function or should the projection change?

## 16. Official Documentation

- Spring Framework 6.2 — Unified JDBC Query/Update Operations (`JdbcClient`): https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html
- Spring Framework 6.2 — `JdbcClient` API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html
- Spring Framework 6.2 — `JdbcClient.MappedQuerySpec` API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.MappedQuerySpec.html
- Spring Framework 6.2 — `JdbcClient.ResultQuerySpec` API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.ResultQuerySpec.html
- Spring Framework 6.2 — `RowMapper` API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/RowMapper.html
- Spring Framework 6.2 — `SimplePropertyRowMapper` API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/SimplePropertyRowMapper.html

**Conclusion:** `query(Class<T>)` fits when the data structure is simple and column names align with the target type. `query(RowMapper<T>)` fits when you need direct control over columns, NULLs, or value conversions. Choose `list()`, `single()`, `optional()`, `set()`, or `stream()` according to row count and data lifecycle; that is a **separate** decision from choosing the mapper.