# Mapping One-to-Many Relationships from JOIN Results in Spring JDBC

## 1. Objective and Problem to Solve

In relational databases, data is commonly normalized into multiple tables: **one order has many line items**, **one department has many employees**, **one post has many comments**. When using a SQL `JOIN` to fetch parents and children together, the result is no longer “one SQL row = one parent object”:

- A parent with 3 children normally appears in **3 result rows**, with the parent's columns repeated.
- A parent **with no children** still needs to appear when using `LEFT JOIN`, with SQL `NULL` in the child columns.
- If you simply use `RowMapper<Parent>` and add each result to `List<Parent>`, you can accidentally create multiple copies of the same parent.
- If you use `queryForObject(...)` to fetch one parent that has multiple children, multiple JOIN rows will cause a row-count error even though the parent table has a unique primary key.

This lesson explains how to **fold/aggregate** multiple JOIN rows into a Java structure like `Parent { List<Child> children; }` using Spring JDBC, preserving data and ordering, handling NULLs properly, testing independently, and avoiding performance pitfalls.

After this lesson, you can:

1. Calculate row counts for `INNER JOIN` and `LEFT JOIN` on a one-to-many relationship.
2. Distinguish `RowMapper` (one row → one object) from `ResultSetExtractor` (entire `ResultSet` → one result structure).
3. Use `LinkedHashMap<ParentId, Accumulator>` to create only one parent, append the right children, and construct immutable DTOs/records after reading.
4. Read potentially `NULL` child keys properly; parents without children must receive an empty list.
5. Prevent duplicate children when joining additional relationships, recognize row multiplication, and avoid paginating directly on JOINs.
6. Write a runnable Spring Boot + `JdbcTemplate` application with Java 17+, sample SQL, and JUnit tests verifying the 1–N relationship.

**Core principle:** a SQL JOIN result is a **flat set of rows**; a parent–child structure in Java is a **hierarchical model**. You need a deliberate mapping step between those two representations.

## 2. Sample Data: One Order with Multiple Line Items

Suppose there are two tables:

```text
purchase_orders
+----+--------------+
| id | order_number |
+----+--------------+
| 10 | ORD-A        |
| 20 | ORD-B        |
| 30 | ORD-C        |
+----+--------------+

purchase_order_lines
+-----+----------+---------+------+----------+
| id  | order_id | line_no | sku  | quantity |
+-----+----------+---------+------+----------+
| 101 | 10       | 1       | BOOK | 2        |
| 102 | 10       | 2       | PEN  | 5        |
| 201 | 20       | 1       | PAD  | 1        |
+-----+----------+---------+------+----------+
```

Business constraints:

- `purchase_orders.id` uniquely identifies each order.
- `purchase_order_lines.id` uniquely identifies each line item.
- `purchase_order_lines.order_id` is the foreign key to the order.
- An order has **0..N line items**; each line item belongs to only one order.
- `line_no` is unique within an order, defining display order of line items.

In Java, we want the result:

```text
Order(10, ORD-A)
  - Line(101, BOOK, quantity=2)
  - Line(102, PEN, quantity=5)

Order(20, ORD-B)
  - Line(201, PAD, quantity=1)

Order(30, ORD-C)
  - [] (no line items)
```

These are **3 parent objects** with a total of **3 child objects**. However, `LEFT JOIN` returns **4 rows**: 2 for ORD-A, 1 for ORD-B, and 1 row with NULL child columns for ORD-C.

### 2.1. Inspecting the Actual JOIN Result

```sql
SELECT
    o.id AS order_id,
    o.order_number,
    l.id AS line_id,
    l.line_no,
    l.sku AS line_sku,
    l.quantity AS line_quantity
FROM purchase_orders o
LEFT JOIN purchase_order_lines l ON l.order_id = o.id
ORDER BY o.id, l.line_no, l.id;
```

Logical result with the data above:

| order_id | order_number | line_id | line_no | line_sku | line_quantity |
| ---: | --- | ---: | ---: | --- | ---: |
| 10 | ORD-A | 101 | 1 | BOOK | 2 |
| 10 | ORD-A | 102 | 2 | PEN | 5 |
| 20 | ORD-B | 201 | 1 | PAD | 1 |
| 30 | ORD-C | NULL | NULL | NULL | NULL |

There are four SQL rows because a parent row is repeated for each joined child row. The last row is a **valid parent with no children**; do not construct a fake line item with `id = 0`, `sku = null`, or `quantity = 0`.

### 2.2. Row-Counting Rule

When joining exactly one child table without extra filters, each parent with `n` children produces:

- `INNER JOIN`: `n` rows; parents with `n=0` disappear.
- `LEFT JOIN`: `max(1, n)` rows; a parent with `n=0` still appears once with NULL child columns.

With three orders having 2, 1, and 0 children respectively: `LEFT JOIN` produces `2 + 1 + 1 = 4` rows; `INNER JOIN` produces `2 + 1 + 0 = 3` rows, excluding ORD-C.

The mapping goal is not “one row into one Order”, but **each parent key into one unique Order**, placing its corresponding children into that Order's collection.

## 3. Choosing the Right Spring JDBC Callback

### 3.1. RowMapper Operates on One Row at a Time

A `RowMapper<T>` maps the current row in `ResultSet` into one object `T`. `JdbcTemplate` is responsible for moving the cursor across rows; `RowMapper.mapRow(rs, rowNum)` **must not call `rs.next()` itself**.

The example below is a flat single-row mapping, **not yet** parent–child grouping:

```java
record FlatOrderLine(
        long orderId,
        String orderNumber,
        Long lineId,
        Integer lineNo,
        String sku,
        Integer quantity
) {}

RowMapper<FlatOrderLine> mapper = (rs, rowNum) ->
        new FlatOrderLine(
                rs.getLong("order_id"),
                rs.getString("order_number"),
                rs.getObject("line_id", Long.class),
                rs.getObject("line_no", Integer.class),
                rs.getString("line_sku"),
                rs.getObject("line_quantity", Integer.class)
        );
```

This is a Java fragment in code importing `org.springframework.jdbc.core.RowMapper` and `java.sql.ResultSet` as needed; it assumes the query in Section 2.1. Calling `jdbcTemplate.query(sql, mapper)` returns **4 FlatOrderLines**, where parent id=10 appears twice and the fourth row has `lineId == null`.

That is **not wrong** if the actual requirement is returning flat rows. It is **not enough** to produce a `List<OrderWithLines>` model with deduplicated parents and child collections.

### 3.2. ResultSetExtractor Processes the Entire Result Set

`ResultSetExtractor<T>` receives the entire `ResultSet` of a single query and iterates through the rows itself to build the result `T`:

```java
ResultSetExtractor<List<OrderView>> extractor = rs -> {
    // Call rs.next() yourself, group rows by parent ID,
    // and return the list of parents with their child lists.
};
```

This is an architectural illustration fragment; `OrderView` and the complete implementation appear in the runnable application section. Inside `ResultSetExtractor`, **you** advance `rs.next()`; `JdbcTemplate` still owns and closes the `ResultSet`/`Statement`/connection along the standard call path and translates `SQLException` into appropriate data access exceptions.

| Spring JDBC tool | Processing scope | Best suited for |
| --- | --- | --- |
| `RowMapper<T>` | One row at a time; JDBC template controls the cursor | Flat `List<T>`, one object per row |
| `ResultSetExtractor<T>` | Entire row set; extractor controls the cursor | Single aggregate, 1–N grouping, hierarchical structures |
| `RowCallbackHandler` | Callback invoked per row; template controls the cursor | Controlled sequential processing/side effects, can accumulate into external state |
| `queryForObject(...)` | Requires exactly one **result row** | Lookup by ID without multi-row JOINs, scalar/row object |
| `queryForList(...)` | Flat result set | List of scalars/maps matching per-row structure |

Do not confuse `queryForObject` with “fetching exactly one parent”: if order id=10 has two lines, the JOIN produces two rows; the query returns one order in the **business sense** yet **two SQL rows**, so `queryForObject` is unsuitable for folding a 1–N relationship.

### 3.3. Why Map by Identifying Key?

Wrong:

```text
for each JOIN row:
    result.add(new Order(row.orderId, row.number, [row.child]))
```

For ORD-A this creates two independent `Order`s rather than one order with two lines. Correct:

```text
map = LinkedHashMap<OrderId, MutableOrder>

for each JOIN row:
    id = row.order_id
    if id not in map:
        map[id] = new MutableOrder(id, row.order_number)

    if row.line_id is not NULL:
        map[id].lines.add(mappedLine)

return map.values().map(MutableOrder::toImmutableView)
```

`LinkedHashMap` has two benefits: average O(1) parent lookup by key and preserving the **first-seen order** of parents from `ORDER BY`. For a moderate number of orders, grouping time complexity is roughly O(R), where `R` is the SQL row count; result memory is O(P+C), where `P` is parent count and `C` is child count.

Grouping by **id** matters more than grouping by name or position: two orders with the same description are still two distinct orders; order/customer names can change, whereas the primary key uniquely identifies the record.

## 4. Prerequisites for Correct 1–N Mapping

Before writing the mapper, establish clearly:

1. **Parent key:** `order_id` is non-NULL and unique in the parent table. Each parent key produces at most one parent object in the map.
2. **Child key:** `line_id` indicates whether a child exists. `LEFT JOIN` yields `NULL` when the parent has no children.
3. **Columns and aliases:** use `AS order_id` and `AS line_id` to prevent multiple tables with `id` or `name` columns from making `rs.getLong("id")` ambiguous.
4. **Ordering:** include `ORDER BY o.id, l.line_no, l.id` to make parent and child order explicit; do not rely on physical storage order.
5. **Child invariants:** `id`, `order_id`, and `line_no` are required, with FK/UNIQUE enforced by the DB; if additional joins multiply rows, handle them separately.
6. **Parent data stays consistent across JOIN rows:** parent columns in a single SELECT come consistently from the same source row; if merging data from disparate sources manually, define an explicit merge policy.
7. **Data types:** use getters matching `BIGINT`, `INTEGER`, `VARCHAR`; check `NULL` on nullable columns.
8. **Data boundaries:** the repository completes mapping before returning; never pass an open `ResultSet` up to controllers/services.

In particular, `ResultSet.getLong("line_id")` returns `0` on SQL NULL; to know whether it was truly NULL, call `rs.wasNull()` right after the getter. A cleaner option when supported by the JDBC driver is `rs.getObject("line_id", Long.class)` to receive `Long null` when there is no child row. The runnable example below uses the second approach.

## 5. Runnable Spring Boot/JDBC Application with Java 17+

The self-contained example uses **Spring Boot 3.3.x, Spring JDBC, and in-memory H2** to run without installing PostgreSQL. The SQL in the example is standard relational SQL, keeping focus on mapping. In production you can use PostgreSQL/MySQL/SQL Server per your actual dialect; the parent–child folding algorithm remains the same.

Directory layout:

```text
one-to-many-join-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/joinmapping/
    │   │   ├── JoinMappingApplication.java
    │   │   ├── OrderView.java
    │   │   └── OrderJdbcRepository.java
    │   └── resources/
    │       ├── application.yml
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/demo/joinmapping/
        └── OrderJdbcRepositoryTest.java
```

### 5.1. Gradle and Dependencies

`settings.gradle`:

```groovy
rootProject.name = 'one-to-many-join-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot Starter JDBC provides `JdbcTemplate`, `DataSource` support, and connection pooling; H2 is used in the example. `spring-boot-starter-test` includes JUnit/AssertJ and Spring test utilities. The plugin versions here are one specific Spring Boot 3.3 / Java 17 set; if integrating into an existing repo, keep the repo's standard version management instead of introducing conflicting versions.

### 5.2. Schema with Proper PK, FK, and UNIQUE Constraints

File `src/main/resources/schema.sql`:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(30) NOT NULL UNIQUE
);

CREATE TABLE purchase_order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(60) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_purchase_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT uq_purchase_lines_position
        UNIQUE (order_id, line_no),
    CONSTRAINT ck_purchase_lines_quantity
        CHECK (quantity > 0)
);
```

The foreign key constraint enforces that a line item must belong to a valid order. `UNIQUE(order_id, line_no)` prevents two lines from sharing the same position within one order, while allowing different orders to each have line number 1. Separate primary keys on parent and child enable accurate grouping and identification.

File `src/main/resources/data.sql`:

```sql
INSERT INTO purchase_orders (id, order_number)
VALUES
    (10, 'ORD-A'),
    (20, 'ORD-B'),
    (30, 'ORD-C');

INSERT INTO purchase_order_lines
    (id, order_id, line_no, sku, quantity)
VALUES
    (101, 10, 1, 'BOOK', 2),
    (102, 10, 2, 'PEN', 5),
    (201, 20, 1, 'PAD', 1);
```

The data intentionally includes an order with two lines, one line, and zero lines to test all three cases. `schema.sql`/`data.sql` are learning fixtures; in production, manage schema changes with proper migrations and never let sample seeds run against real data.

### 5.3. H2 Configuration

File `src/main/resources/application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:join_mapping;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always
```

Spring Boot creates the in-memory datasource, then runs `schema.sql` and `data.sql` during startup. `DB_CLOSE_DELAY=-1` keeps the in-memory H2 database alive while the JVM runs even if connections close temporarily; when the JVM exits, the data disappears. The example requires no frontend, HTTP server, or external DB.

### 5.4. Record-Based Domain/Read Model

File `src/main/java/demo/joinmapping/OrderView.java`:

```java
package demo.joinmapping;

import java.util.List;

public record OrderView(
        long id,
        String orderNumber,
        List<OrderLine> lines
) {
    public OrderView {
        lines = List.copyOf(lines);
    }

    public record OrderLine(
            long id,
            int lineNumber,
            String sku,
            int quantity
    ) {}
}
```

`OrderView` is a read model representing the parent and child collection. `List.copyOf(lines)` creates an externally unmodifiable copy: the repository can use an `ArrayList` while grouping, yet callers cannot accidentally add/remove lines on the returned object.

`OrderLine` is a nested record inside `OrderView`, accessed as `OrderView.OrderLine`. Making the record immutable does not automatically turn relational data into a transactionally consistent domain aggregate: this is a read structure, whereas multi-table writes/updates require appropriate transactions and constraints.

### 5.5. Repository: ResultSetExtractor Folding the Entire JOIN

File `src/main/java/demo/joinmapping/OrderJdbcRepository.java`:

```java
package demo.joinmapping;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.stereotype.Repository;

@Repository
public class OrderJdbcRepository {

    private static final String JOIN_SELECT = """
            SELECT
                o.id AS order_id,
                o.order_number AS order_number,
                l.id AS line_id,
                l.line_no AS line_no,
                l.sku AS line_sku,
                l.quantity AS line_quantity
            FROM purchase_orders o
            LEFT JOIN purchase_order_lines l
                   ON l.order_id = o.id
            """;

    private static final String ORDERING = """
            ORDER BY o.id, l.line_no, l.id
            """;

    private static final ResultSetExtractor<List<OrderView>> EXTRACTOR =
            rs -> {
                LinkedHashMap<Long, Accumulator> orders =
                        new LinkedHashMap<>();

                while (rs.next()) {
                    long orderId = rs.getLong("order_id");

                    Accumulator order = orders.get(orderId);
                    if (order == null) {
                        order = new Accumulator(
                                orderId,
                                rs.getString("order_number")
                        );
                        orders.put(orderId, order);
                    }

                    Long lineId = rs.getObject("line_id", Long.class);
                    if (lineId != null) {
                        order.lines.add(new OrderView.OrderLine(
                                lineId,
                                rs.getInt("line_no"),
                                rs.getString("line_sku"),
                                rs.getInt("line_quantity")
                        ));
                    }
                }

                return orders.values().stream()
                        .map(Accumulator::toView)
                        .toList();
            };

    private final JdbcTemplate jdbc;

    public OrderJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderView> findAllWithLines() {
        return jdbc.query(JOIN_SELECT + ORDERING, EXTRACTOR);
    }

    public Optional<OrderView> findByIdWithLines(long id) {
        List<OrderView> orders = jdbc.query(
                JOIN_SELECT + " WHERE o.id = ? " + ORDERING,
                EXTRACTOR,
                id
        );
        return orders.stream().findFirst();
    }

    private static final class Accumulator {
        final long id;
        final String orderNumber;
        final List<OrderView.OrderLine> lines = new ArrayList<>();

        Accumulator(long id, String orderNumber) {
            this.id = id;
            this.orderNumber = orderNumber;
        }

        OrderView toView() {
            return new OrderView(id, orderNumber, lines);
        }
    }
}
```

**Step-by-step analysis:**

1. `JOIN_SELECT` lists columns explicitly, with aliases `order_id` and `line_id` to prevent ambiguity. No `SELECT *`.
2. `LEFT JOIN` preserves order ORD-C even with no line items; `INNER JOIN` would drop it.
3. `ORDER BY o.id, l.line_no, l.id` gives deterministic ordering. `l.id` acts as a tie-breaker; the sample data already enforces `line_no` uniqueness per order.
4. `EXTRACTOR` is stored in a `static final` field yet **retains no result state across calls**. `LinkedHashMap` is instantiated **inside the lambda on every query execution**, so independent calls never mix results.
5. Each row visited via `rs.next()` reads `order_id` and looks up the map. Only on first encountering a parent ID does the code create an `Accumulator`.
6. `rs.getObject("line_id", Long.class)` returns `null` for SQL NULL from the `LEFT JOIN`. An `OrderLine` is added only when `lineId != null`.
7. After reading the whole `ResultSet`, each accumulator converts into a new `OrderView` with an immutable list. Exactly one parent object is returned per ID.
8. `findByIdWithLines` filters by **parent primary key** using `?` and reuses the same extractor. It may receive 0, 1, or many SQL rows for that parent; the result is still `Optional<OrderView>` for 0 or 1 parent.

Implicit assumption of this snippet: **each child row appears at most once in the JOIN**. When joining from orders to **one** line-item table as shown, this holds because `l.id` is a primary key. When joining additional collections, the same child can appear multiple times; Section 8 explains how to handle that.

### 5.6. Entry Point and Expected Output

File `src/main/java/demo/joinmapping/JoinMappingApplication.java`:

```java
package demo.joinmapping;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JoinMappingApplication {

    public static void main(String[] args) {
        SpringApplication.run(JoinMappingApplication.class, args);
    }

    @Bean
    CommandLineRunner showOrders(OrderJdbcRepository repository) {
        return args -> {
            var orders = repository.findAllWithLines();

            System.out.println("orders=" + orders.size());

            for (var order : orders) {
                var skus = order.lines().stream()
                        .map(OrderView.OrderLine::sku)
                        .toList();

                System.out.println(
                        order.orderNumber() + " -> " + skus
                );
            }

            System.out.println(
                    "found(999)="
                    + repository.findByIdWithLines(999L).isPresent()
            );
        };
    }
}
```

With a **Gradle wrapper already present** in the project or Gradle installed, run:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If you created the project manually from the files above without a Gradle wrapper, generate the wrapper with an installed Gradle or run `gradle bootRun`. The application class name and package must match the file paths in the example. Java 17 suffices for `record`, text blocks, and `Stream.toList()`.

After Spring Boot startup logs, the five lines printed by `CommandLineRunner` are:

```text
orders=3
ORD-A -> [BOOK, PEN]
ORD-B -> [PAD]
ORD-C -> []
found(999)=false
```

The line `ORD-C -> []` proves a childless parent is still present. `orders=3` proves four parent objects were not accidentally created from the four JOIN rows. `found(999)=false` proves a primary-key lookup with no match returns `Optional.empty()` rather than a fake object.

## 6. Comparing Two Mapping Approaches: Flatten-Then-Group vs. Direct Extract

### 6.1. Approach 1: RowMapper Produces FlatRow, Then Java Groups

First step: one row becomes a flat record like `FlatOrderLine` in Section 3.1. Then:

```java
List<FlatOrderLine> rows = jdbcTemplate.query(sql, flatMapper);

LinkedHashMap<Long, List<FlatOrderLine>> grouped =
        new LinkedHashMap<>();

for (FlatOrderLine row : rows) {
    grouped.computeIfAbsent(
            row.orderId(),
            ignored -> new ArrayList<>()
    ).add(row);
}
```

This is a fragment requiring `sql` and `flatMapper` to be declared; in a real project, import `java.util.ArrayList`, `java.util.LinkedHashMap`, and `java.util.List`. The result is a map holding **flat rows** by parent, not yet the final DTO. A subsequent step is needed to construct `Order`s, ignore rows with `lineId == null`, and avoid repeating parent fields.

Pros: easy to unit-test the single-row `RowMapper` and reuse flat projections. Cons: retains both a `List<FlatRow>` and the grouping map simultaneously, increasing memory allocations on large results. It is not wrong; it fits when code also needs flat data independently.

### 6.2. Approach 2: ResultSetExtractor Iterates and Groups Simultaneously

The `ResultSetExtractor` in Section 5.5 performs grouping as Spring streams the `ResultSet`, avoiding an intermediate list. It can return final DTOs immediately when the query finishes. For clear parent–child needs, this is direct and reduces intermediate allocations.

However, the extractor still holds the final parents/children in memory until returning; it **does not turn the entire result into an unbounded stream**. When row counts are very large, consider pagination, batch loading, narrower projections, or true streaming processing.

### 6.3. When to Use RowCallbackHandler?

`RowCallbackHandler` is invoked by Spring per row; you can accumulate into a `LinkedHashMap` outside the callback. However, the callback has no direct return value, so the repository must manage per-query state and convert it afterward after calling `jdbc.query(...)`. For “entire result set → one object structure”, `ResultSetExtractor` usually communicates intent more clearly.

A `RowCallbackHandler.processRow(rs)` **does not** call `rs.next()` itself; the template already advances the cursor. If switching from `ResultSetExtractor` to `RowCallbackHandler` and leaving `while (rs.next())` inside the callback, you will skip rows and introduce subtle bugs.

## 7. LEFT JOIN and SQL NULL: Data Pitfalls

### 7.1. Always Check the Child ID, Not an Optional Attribute

If the child has nullable fields (such as `description` or `discount_code`), do not use those fields to decide “whether a child exists”:

```java
// Wrong if sku/description can be NULL:
if (rs.getString("description") != null) {
    // add child
}

// Correct when line.id is a NOT NULL PK:
Long lineId = rs.getObject("line_id", Long.class);
if (lineId != null) {
    // add child
}
```

A valid child can have a NULL description. Use the child's `NOT NULL` primary key to determine existence. With composite keys, identify the right key columns and the JOIN's NULL semantics.

### 7.2. getLong/getInt with NULL Requires wasNull

With `rs.getLong("line_id")` and SQL NULL data, JDBC normally returns `0L`; `rs.wasNull()` reveals whether the true value was NULL:

```java
long lineId = rs.getLong("line_id");
if (!rs.wasNull()) {
    // This is genuinely a child row.
}
```

`wasNull()` reflects **the most recently read getter**. If another getter is called before `wasNull()`, the check will be wrong. Using `rs.getObject("line_id", Long.class)` is clearer when supported by the driver. Do not create a `Line(0,...)` for ORD-C.

### 7.3. Put Conditions in ON or WHERE?

The two queries below have **different semantics** when a parent has no matching child rows:

```sql
-- Keep every order; only join lines with quantity >= 2.
SELECT o.id, l.id
FROM purchase_orders o
LEFT JOIN purchase_order_lines l
  ON l.order_id = o.id AND l.quantity >= 2;

-- WHERE predicate drops rows where l.quantity is NULL.
SELECT o.id, l.id
FROM purchase_orders o
LEFT JOIN purchase_order_lines l
  ON l.order_id = o.id
WHERE l.quantity >= 2;
```

In the first query, a parent with no qualifying line still gets one row with `l.id = NULL`. In the second query, the NULL child row fails `WHERE l.quantity >= 2`, so the parent vanishes from the result. For “show all orders along with matching lines”, put the child predicate in `ON` (or use an equivalent filter/subquery).

If the opposite is required—“only return orders with at least one qualifying line”—use `WHERE`/`EXISTS` per that intent; do not pick `LEFT JOIN` out of habit.

### 7.4. COUNT(*) on a LEFT JOIN Can Mislead

```sql
SELECT
    o.id,
    COUNT(*) AS joined_rows,
    COUNT(l.id) AS actual_lines
FROM purchase_orders o
LEFT JOIN purchase_order_lines l ON l.order_id = o.id
GROUP BY o.id
ORDER BY o.id;
```

For childless ORD-C: `joined_rows = 1` whereas `actual_lines = 0`. `COUNT(*)` counts the “placeholder” row produced by `LEFT JOIN`; `COUNT(l.id)` ignores NULLs and gives the accurate line count when each child appears once. If joining another table duplicates children, consider `COUNT(DISTINCT l.id)` or a separate subquery count.

## 8. Joining Multiple Relationships: Row Multiplication and Key-Based Deduplication

Suppose an order has **2 line items** and **3 notes**, and both child sets are joined:

```sql
SELECT o.id, l.id AS line_id, n.id AS note_id
FROM purchase_orders o
LEFT JOIN purchase_order_lines l ON l.order_id = o.id
LEFT JOIN order_notes n ON n.order_id = o.id
WHERE o.id = 10;
```

`order_notes` is a hypothetical table with primary key `id` and FK `order_id` to the orders table. The result can contain **2 × 3 = 6 rows**, because every line item pairs with every note. Simply calling `order.lines.add(...)` on every row appends both lines three times each. That is **Cartesian multiplication** of independent collections, not six real line items.

### 8.1. Deduplicating by Child ID Inside the Accumulator

In a multi-collection JOIN that must be folded, you can store children by ID:

```java
// Illustrative snippet inside an accumulator.
LinkedHashMap<Long, OrderView.OrderLine> uniqueLines =
        new LinkedHashMap<>();

Long lineId = rs.getObject("line_id", Long.class);
if (lineId != null) {
    uniqueLines.putIfAbsent(
            lineId,
            new OrderView.OrderLine(
                    lineId,
                    rs.getInt("line_no"),
                    rs.getString("line_sku"),
                    rs.getInt("line_quantity")
            )
    );
}

// After iterating everything:
List<OrderView.OrderLine> lines =
        List.copyOf(uniqueLines.values());
```

Here `rs` is the `ResultSet` inside the extractor, with corresponding `Map`/`List` imports. `putIfAbsent` only makes sense when the child ID genuinely identifies a unique child and repeated rows refer to the exact same child. If data contains two distinct child records with the same description, never merge them by name or by `line_no` without parent context.

### 8.2. Deduplication Does Not Eliminate JOIN Cost

Deduplicating by ID keeps the object tree free of duplicates, yet the DB still transfers `N × M` rows. That increases data transfer, JDBC CPU, and memory. For two or more large collections, it is usually better to consider:

- Query parents first, then query **all lines for the selected parents in one batch** via `WHERE order_id IN (...)`; assemble in Java.
- Query independent collections in separate batches instead of joining everything at once.
- Use DBMS-specific SQL/JSON aggregation where appropriate, then verify mapping, ordering, NULLs, and payload sizes.
- Return projection DTOs tailored to the screen instead of “loading every relationship” by default.

Java-side deduplication does not replace UNIQUE/FK constraints in the DB and does not fix truly duplicated source data.

## 9. Correct Pagination with One-to-Many Data

### 9.1. Why LIMIT/OFFSET Directly on a JOIN Is Usually Wrong

Example:

```sql
SELECT o.id AS order_id, l.id AS line_id
FROM purchase_orders o
LEFT JOIN purchase_order_lines l ON l.order_id = o.id
ORDER BY o.id, l.line_no
LIMIT 1;
```

In the sample data, ORD-A has two lines. `LIMIT 1` keeps only the **first single JOIN row**, ORD-A with BOOK; once folded, you get ORD-A missing PEN. This is a **partial child collection** data bug. `LIMIT 2` might return ORD-A complete, yet fails to return two orders even though the screen requested “2 orders”.

In other words, SQL `LIMIT/OFFSET` operates on **post-JOIN result rows**, unaware of a Java Order aggregate concept. Spring/JDBC pagination does not fix this automatically.

### 9.2. Two-Step Strategy: Select Parent IDs Then Batch-Load Children

Step 1, paginate **parents** in a deterministic order:

```sql
SELECT o.id
FROM purchase_orders o
ORDER BY o.id
LIMIT ? OFFSET ?;
```

Step 2, fetch full rows for **the parents on that page**, e.g. for ID list `[10, 20]`:

```sql
SELECT
    o.id AS order_id,
    o.order_number,
    l.id AS line_id,
    l.line_no,
    l.sku AS line_sku,
    l.quantity AS line_quantity
FROM purchase_orders o
LEFT JOIN purchase_order_lines l ON l.order_id = o.id
WHERE o.id IN (10, 20)
ORDER BY o.id, l.line_no, l.id;
```

Query 2 must bind IDs via parameters (such as `NamedParameterJdbcTemplate` with `IN (:ids)`), never concatenating raw user input into SQL. In this example, a two-parent page of ORD-A and ORD-B gets all 2+1 children completely, totaling 3 JOIN rows.

Conceptual implementation in Spring JDBC:

```java
List<Long> ids = jdbc.query(
        """
        SELECT id FROM purchase_orders
        ORDER BY id
        LIMIT ? OFFSET ?
        """,
        (rs, rowNum) -> rs.getLong(1),
        pageSize,
        offset
);

if (ids.isEmpty()) {
    return List.of();
}

return namedJdbc.query(
        JOIN_SELECT
            + " WHERE o.id IN (:ids) "
            + ORDERING,
        new MapSqlParameterSource("ids", ids),
        EXTRACTOR
);
```

This is a **repository fragment** assuming `jdbc`, `namedJdbc` (`NamedParameterJdbcTemplate`), `JOIN_SELECT`, `ORDERING`, `EXTRACTOR`, and importing `MapSqlParameterSource`; it is not a standalone complete Java method. Input `pageSize` needs a reasonable cap and `offset` must be non-negative. `IN (:ids)` requires a non-empty list, hence the `ids.isEmpty()` check before querying.

**Concurrency note:** two separate SQL statements may observe two different snapshots when concurrent requests update data; a `readOnly` transaction under default isolation does not necessarily create a stable snapshot across two statements, depending on the DBMS. If strict cross-query page consistency is required, consider isolation/snapshot settings, keyset pagination, or an appropriate read model. Do not keep a read transaction open across slow network processing just to hold a snapshot.

### 9.3. Avoiding N+1 When Loading Children

Poor approach:

```text
SELECT * FROM purchase_orders ... LIMIT 20
for each order:
    SELECT * FROM purchase_order_lines WHERE order_id = ?
```

That is 1 parent query + 20 child queries, causing the **N+1 queries** problem. The `WHERE order_id IN (...)` batch approach usually uses two SQL queries total per page, reducing round-trips while keeping collections complete.

Place an index on `purchase_order_lines(order_id, line_no)` if queries frequently fetch and sort lines by order. `UNIQUE(order_id, line_no)` in the sample schema already creates a suitable index on many DBMSs; check the real DB's execution plan rather than creating redundant duplicate indexes.

## 10. Invariants, Ordering, and Data Reliability

### 10.1. Parent Identity Must Be Stable

In `LinkedHashMap<Long, Accumulator>`, the key is the parent ID. If the model requires tenant isolation, you may need a composite key `(tenantId, orderId)` or guarantee `orderId` is globally unique and queries filter by tenant. Do not use `orderNumber` if it is only unique per tenant; never use display names as identity.

### 10.2. Child Identity Must Be Stable

When joining only one child table with a unique child PK, each child row appears once; appending to a `List` suffices. With multi-table joins, use `Map<ChildId, Child>` per parent to deduplicate. **Do not** deduplicate via `equals` if equality does not reflect the PK; two line items with the same SKU can still be two distinct records.

### 10.3. ORDER BY Determines List Order

Without `ORDER BY`, SQL guarantees no row order. `LinkedHashMap` only preserves **encounter** order, so if input row order shifts, parent and child order shifts too. On screens requiring sorting, choose explicit order keys: `ORDER BY o.created_at DESC, o.id DESC, l.line_no, l.id`; if the backend does not support that expression, adapt to the DBMS.

A memory-saving streaming algorithm sometimes keeps only **the current parent** and emits it when `order_id` changes. That requires JOIN rows to arrive contiguously grouped by parent; without `ORDER BY`, if rows of the same parent are interleaved, it can emit duplicate parents. Using a map is generally safer and easier to understand for moderate record counts.

### 10.4. Do Not Mix Data Validation Rules with Mapping

`ResultSetExtractor` only translates DB results to Java; it should not silently patch corrupt data such as orphaned children, negative quantities, or truly duplicate records. Use PK, FK, UNIQUE, and CHECK constraints in the DB to protect invariants, and transactions when writing aggregates. The mapper should fail loudly on unexpected schemas rather than fabricating dummy data.

### 10.5. Notes on Null and Optional

`Optional<OrderView>` represents “order found / order not found” when looking up by ID. An order that **exists with no lines** should be `Optional.of(new OrderView(..., List.of()))`, not `Optional.empty()`. That differs from an empty child collection.

A line item with a nullable field, such as `discount_code`, is still a valid child if `line_id` is non-null. Never treat a child as “nonexistent” simply because an optional attribute is null.

## 11. Testing Mapping with JUnit 5

A 1–N mapper must be tested **by its resulting object graph**, not only by JOIN row count. Use `@SpringBootTest` for the H2 example in Section 5; Spring SQL initialization loads the fixture data without needing an HTTP service.

File `src/test/java/demo/joinmapping/OrderJdbcRepositoryTest.java`:

```java
package demo.joinmapping;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class OrderJdbcRepositoryTest {

    @Autowired
    OrderJdbcRepository repository;

    @Test
    void createsOneParentForEachOrderId() {
        List<OrderView> orders = repository.findAllWithLines();

        assertEquals(3, orders.size());
        assertEquals(
                List.of(10L, 20L, 30L),
                orders.stream().map(OrderView::id).toList()
        );
    }

    @Test
    void groupsTwoLinesUnderSingleParentInOrder() {
        OrderView order = repository.findByIdWithLines(10L)
                .orElseThrow();

        assertEquals("ORD-A", order.orderNumber());
        assertEquals(
                List.of(101L, 102L),
                order.lines().stream().map(
                        OrderView.OrderLine::id
                ).toList()
        );
        assertEquals(
                List.of("BOOK", "PEN"),
                order.lines().stream().map(
                        OrderView.OrderLine::sku
                ).toList()
        );
        assertEquals(2, order.lines().get(0).quantity());
    }

    @Test
    void preservesParentWithoutChildren() {
        OrderView emptyOrder = repository.findByIdWithLines(30L)
                .orElseThrow();

        assertEquals("ORD-C", emptyOrder.orderNumber());
        assertTrue(emptyOrder.lines().isEmpty());
    }

    @Test
    void missingParentIsDifferentFromEmptyChildList() {
        assertTrue(repository.findByIdWithLines(999L).isEmpty());
        assertTrue(repository.findByIdWithLines(30L).isPresent());
    }

    @Test
    void returnedChildCollectionIsNotMutable() {
        OrderView order = repository.findByIdWithLines(10L)
                .orElseThrow();

        assertThrows(
                UnsupportedOperationException.class,
                () -> order.lines().clear()
        );
    }
}
```

Run tests:

```bash
./gradlew test
```

With the sample code and data intact, all five tests are designed to pass. They protect key requirements: 3 distinct parents, two properly ordered lines in ORD-A, empty order ORD-C present, missing ID distinguished from empty child list, and returned lists unmodifiable externally.

This is an **integration test with H2**, not yet testing performance or production PostgreSQL/MySQL JOIN semantics. If the real application uses a specific dialect, add integration tests with that DBMS (e.g., Testcontainers PostgreSQL) and test large datasets, pagination, and concurrent updates.

### 11.1. Additional Test Cases Needed for Real Data

| Case | Expectation |
| --- | --- |
| 0 parents | Returns `List.of()`, no fake objects |
| 1 parent, 0 children | One parent with `lines=[]` |
| 1 parent, 1 child | One parent and one child |
| 1 parent, 100 children | One parent, 100 children in order |
| 100 parents, some childless | No dropped parents; exact total child count |
| Two parents with same `orderNumber` if model permits | Do not merge two parents just because names match |
| JOIN with extra table multiplying each child | Deduplicate by child ID or change query to avoid multiplication |
| Child optional field NULL | Child still exists if child PK is non-NULL |
| JOIN capped by row `LIMIT` | Test must catch truncated child lists |
| Two-query pagination under concurrent writes | Evaluate consistency contract and appropriate isolation |

Do not assert only the total number of `OrderView`s: parent count could be right while lines are missing, duplicated, or attached to the wrong parent. Check **parent IDs, child IDs, counts, ordering, and field values** to catch mapping bugs reliably.

## 12. Performance and Resource Safety

A JOIN query can eliminate N+1 yet is not automatically faster than every other loading strategy:

- **Transferred rows:** a parent with 1,000 lines repeats parent columns 1,000 times over the JDBC network. If the parent has many wide columns, transfer cost grows.
- **Memory:** the extractor keeps aggregates in RAM; do not return millions of children to an unpaginated request by default.
- **Projections:** select only needed columns, avoiding `SELECT *` and large payloads like BLOBs in list queries.
- **Indexes:** child FK `order_id` and sort column `line_no` need indexes matching the workload; verify with `EXPLAIN` rather than guessing.
- **JDBC resources:** `JdbcTemplate` manages opening/closing statements/result sets per lifecycle. Never return a `ResultSet` outside and let slow service/web serialization hold the borrowed connection.
- **Transactions:** a short read-only query may not need a long service transaction. If a consistent snapshot across multiple queries is needed, pick reasonable isolation/scope and avoid slow HTTP calls inside transactions.
- **Bounding load:** paginate by parent, batch-load children, enforce a max page size. Multi-collection results often work better with multiple queries than one giant JOIN.
- **Observability:** measure query time, DB row count, post-mapping parent/child counts, memory, p95/p99, and pool wait count.

A useful measurement per page: **returned SQL rows**, **distinct parent IDs**, **distinct child IDs**, **time to map**, and **response size**. If SQL returns 100,000 rows just to build 100 parents and 200 children, you likely have a JOIN explosion or over-fetching.

## 13. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Direct `RowMapper<Order>` for 1–N JOIN | Creates multiple duplicate `Order`s per ID | Use `ResultSetExtractor`/grouping by parent ID |
| `queryForObject` on JOIN for a multi-child parent | Throws `IncorrectResultSizeDataAccessException` | Use `query` with an extractor returning the aggregate |
| `INNER JOIN` when childless parents are needed | Loses parents with empty collections | `LEFT JOIN` |
| Not checking `line_id IS NULL` | Creates fake child from LEFT JOIN placeholder row | Check nullable child PK properly |
| Calling `getLong` without `wasNull` | SQL NULL treated as ID 0 | `getObject(..., Long.class)` or `wasNull()` right after getter |
| Grouping parents by `name` or non-unique `orderNumber` | Accidentally merges two distinct parents | Group by true primary/composite key |
| Relying on DB order without `ORDER BY` | Child list order shifts unpredictably | Sort by parent ID and child position/ID |
| JOINing two independent collections | Each child repeats by the product of both collections | Deduplicate by ID, or use separate batch queries |
| Deduplicating by SKU/text | Wrongly merges two valid lines sharing a SKU | Deduplicate by child PK |
| `LIMIT/OFFSET` directly on joined rows | Truncates child collections | Paginate parent IDs first, batch-load children |
| Querying children per parent in a loop | N+1 database round-trips | Single query over parent ID set |
| `WHERE child.condition` on LEFT JOIN | Can drop parents without matching children | Review `ON`/`WHERE` per business logic |
| `COUNT(*)` to count children on LEFT JOIN | Childless parent counted as 1 | `COUNT(child.id)` when model fits |
| Not aliasing `id` columns from two tables | Reads wrong/ambiguous column | `AS order_id`, `AS line_id` |
| Storing ResultSetExtractor map in a shared field | Cross-request state mixing, race conditions | Create a local accumulator per query |
| Returning mutable lists directly to callers | Callers accidentally corrupt read aggregates | `List.copyOf` in the final DTO |
| Returning `ResultSet`/`Connection` out of repository | Resource leaks, JDBC coupling | Map completely inside repository and return DTOs |
| Too many rows/columns from JOIN | Wastes RAM and bandwidth | Projections, paging, batch loading, indexes |

## 14. Practice Exercises

**Exercise 1 — Predicting row counts.** Given 4 orders having 0, 1, 3, and 5 line items respectively. How many rows do `INNER JOIN` and `LEFT JOIN` produce? Why does the `LEFT JOIN` row count not match the number of `Order` objects to return?

**Exercise 2 — Spotting the bug.** A mapper runs:

```java
List<OrderView> result = new ArrayList<>();
while (rs.next()) {
    result.add(new OrderView(
            rs.getLong("order_id"),
            rs.getString("order_number"),
            List.of()
    ));
}
```

This is a `ResultSet`-processing fragment ignoring children. For ORD-A with two lines, how many parents does it create? Replace it with a map by ID, detect `line_id == null`, and add children in the right place.

**Exercise 3 — LEFT JOIN.** Write a query selecting only lines with `quantity >= 2` while still keeping all orders, including childless ORD-C. Put the condition in `ON` or `WHERE`? Explain using the NULL child row.

**Exercise 4 — Multiple collections.** An Order has 3 lines and 4 notes. Joining both produces at most how many rows? Without deduplication, how many times is each line added? Choose between deduplicating by child ID or running separate batch queries.

**Exercise 5 — Pagination.** A screen wants to display 10 orders, each with all its lines. Why does `LIMIT 10` on the JOIN easily return incomplete data? Propose a SQL query selecting 10 parent IDs and a SQL query loading lines for those 10 IDs with bind parameters.

**Exercise 6 — Testing.** Seed an Order with 10 lines inserted out of `line_no` order and verify `ORDER BY` produces the right list. Add a test verifying that when the same child ID appears across multiple rows after joining an extra table, no duplicate children are produced.

**Hints:** Exercise 1 gives `INNER JOIN = 0+1+3+5 = 9` and `LEFT JOIN = 1+1+3+5 = 10`, yet both represent at most 4 parents and `INNER JOIN` drops the childless parent. Exercise 3 puts the child filter in `ON` to keep parents with no qualifying lines. Exercise 4 has `3×4=12` rows and each line repeats 4 times; deduplication does not remove the cost of transferring 12 rows. Exercise 5 must paginate by **parents**, not by JOIN rows.

## 15. Checklist When Designing a 1–N Mapper

- Have you identified the exact **parent primary key** and **child primary key**?
- Does the SQL JOIN return the required set of parents, including childless parents?
- Do parent/child columns have clear aliases avoiding ambiguous `id`?
- Are you using `ResultSetExtractor` or an explicit grouping step to fold multiple rows into one parent?
- Do you check `NULL` on the **child PK** before creating child objects?
- If joining additional tables, have you accounted for **row multiplication** and a deduplication/split-query strategy?
- Is there an `ORDER BY` for the parent/child ordering the UI expects?
- If paginating, are you paginating **parent IDs** rather than raw joined rows?
- Have you avoided N+1 by loading children in one query over the parent ID list?
- Is the JDBC lifecycle closed inside the repository without passing `ResultSet`/connections to controllers?
- Do tests cover 0, 1, many children; childless parents; nulls; ordering; multi-collection joins; pagination; and performance?

**Conclusion:** Mapping one-to-many relationships from SQL JOINs requires understanding the difference between **SQL row count** and **business object count**. In Spring JDBC, `ResultSetExtractor` paired with `LinkedHashMap` keyed by parent ID is a clear pattern: iterate once, create one parent per ID, add children when the child PK is non-NULL, preserve deliberate ordering, and return immutable object trees. For multiple collections or pagination, reshape the queries to avoid row multiplication and truncated data before micro-optimizing the mapper.

## References

- Spring Framework — JDBC Core and querying/result mapping: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — `ResultSetExtractor` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/ResultSetExtractor.html
- Spring Framework — `RowMapper` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/RowMapper.html
- Spring Framework — `JdbcTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework — `NamedParameterJdbcTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- PostgreSQL — Combining Queries/Joined Tables: https://www.postgresql.org/docs/current/queries-table-expressions.html#QUERIES-JOIN
- PostgreSQL — `SELECT` and `ORDER BY`/`LIMIT`: https://www.postgresql.org/docs/current/sql-select.html
