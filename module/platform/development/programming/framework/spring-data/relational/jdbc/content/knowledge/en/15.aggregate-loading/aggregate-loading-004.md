# Single Query Loading: Purpose and Activation

**Single Query Loading** is a Spring Data JDBC aggregate-loading mechanism that uses a single SELECT statement instead of loading the aggregate root first and then issuing separate queries for owned child entity collections. Its primary goal is to reduce round-trips between the application and the database, especially when a query returns multiple aggregates that have owned collections.

This feature was introduced in Spring Data JDBC 3.2. To enable it, call §setSingleQueryLoadingEnabled(true)§ on §JdbcMappingContext§. However, enabling the flag only permits the framework to attempt using this mechanism; the aggregate, repository method, and database dialect must still satisfy the supported conditions. If they do not, Spring Data JDBC automatically falls back to the default aggregate loading strategy.

This lesson explains the problem Single Query Loading targets, the SQL idea behind it, how to configure the mapping context, the limitations to know, and how to observe its effectiveness in an application.

## 1. The aggregate loading problem in Spring Data JDBC

Spring Data JDBC works with **aggregates**: an aggregate root and the entities owned inside it. When an application reads an aggregate, the domain-level goal is to receive the root together with the components belonging to the aggregate according to the model.

Example of an order with multiple order lines:

§§§text
PurchaseOrder aggregate
┌──────────────────────────────┐
│ PurchaseOrder                │
│ id = 501                     │
│ status = "CONFIRMED"         │
│                              │
│ lines                        │
│   ├── OrderLine A            │
│   ├── OrderLine B            │
│   └── OrderLine C            │
└──────────────────────────────┘
§§§

Business code might call:

§§§java
PurchaseOrder order = orderRepository.findById(501L)
        .orElseThrow();
§§§

At that point, the application expects a complete object ready to access its order lines. However, **one repository call does not necessarily correspond to one SQL statement**. With traditional loading, Spring Data JDBC may query the root first and then query child entities using separate statements.

For an aggregate with a collection:

§§§sql
SELECT id, status
FROM purchase_orders
WHERE id = ?;

SELECT order_id, line_position, sku, quantity
FROM order_lines
WHERE order_id = ?;
§§§

For a single aggregate, two queries like those above may be completely acceptable. The problem becomes more pronounced when the application loads many aggregates at once.

## 2. How does the N+1 query pattern appear?

Suppose an admin screen needs to load 100 orders, each with a §lines§ collection. Traditional loading may follow this pattern:

1. Run one §SELECT§ to fetch 100 §purchase_orders§ rows.
2. For each order, run another §SELECT§ to fetch the order lines belonging to that order.

Number of queries:

§§§text
1 query fetching 100 aggregate roots
+
100 queries fetching each root's collection
=
101 queries
§§§

This is the **N+1 query problem**: one initial query plus N follow-up queries proportional to the number of roots.

If an aggregate has multiple collections at the same level, each root may need separate queries for each collection. For example, a §Minion§ has lists of §toys§ and §hobbies§:

§§§text
SELECT * FROM minions;

For each Minion:
    SELECT * FROM toys WHERE minion_id = ?;
    SELECT * FROM hobbies WHERE minion_id = ?;
§§§

If N minions are loaded with two collections, the number of queries this way can be §1 + 2N§. As N grows, the number of exchanges between the application and the database grows accordingly.

### 2.1. Why is N+1 expensive?

The cost is not only in database SQL execution time:

- Every query must be sent over the JDBC connection and its result received.
- Every round-trip incurs network/driver latency.
- The database has to prepare, execute, and return results many times.
- The connection pool and application threads may be held longer.
- When loading many aggregates, cost grows with the number of roots rather than only the amount of data returned.

Even if each individual query runs quickly, the cumulative time of hundreds of round-trips can be significant.

### 2.2. One repository call does not mean one SQL statement

Two levels must be distinguished:

| Level | Meaning |
| --- | --- |
| **Repository call** | A Java call such as §findAll()§ or §findById(id)§. |
| **SQL statement** | An actual command sent to the database. |

Traditional loading can execute multiple SQL statements inside a single repository call. Single Query Loading changes how the framework generates read statements to load eligible aggregates in a single SELECT.

## 3. Goal of Single Query Loading

Single Query Loading aims to load **multiple complete aggregates in one SQL statement**, including the root and supported child entities, reducing round-trips.

Example loading 100 orders:

§§§text
Traditional loading:
    SELECT purchase_orders ...          (once)
    SELECT order_lines WHERE order_id=? (repeated per order)
    SELECT order_lines WHERE order_id=?
    ...
    SELECT order_lines WHERE order_id=?

Single Query Loading:
    SELECT ... root + child collections ...  (once)
§§§

This is especially useful when:

- A repository method loads many aggregates.
- Each aggregate has owned entity collections.
- The number of aggregates is large enough that round-trips become a noticeable cost.
- The database supports the required analytic/window functions.
- The aggregate model and query method fall within the feature's supported scope.

Single Query Loading focuses on **reading data**. It does not change how aggregates are inserted, updated, or deleted, nor does it turn an aggregate into an arbitrary business query.

### 3.1. Not every case needs Single Query Loading

If the application only loads a single aggregate with a small collection, the default loading mechanism may be fast and simple enough. If a query only fetches roots with no collections needed, the benefit of combined collection loading is negligible.

The goal is not to reduce SQL count at all costs. The goal is to reduce data access overhead in aggregate-loading flows where N+1 genuinely impacts performance.

## 4. Why not just JOIN all collections?

A natural idea is to use one SQL query with multiple §JOIN§ clauses:

§§§sql
SELECT *
FROM minions m
LEFT JOIN toys t ON t.minion_id = m.id
LEFT JOIN hobbies h ON h.minion_id = m.id;
§§§

This approach can create a **Cartesian product between collections** of the same root.

Suppose one minion has:

- 2 toys.
- 3 hobbies.

When joining both collections simultaneously, the result can have §2 × 3 = 6§ rows for the same minion:

§§§text
Minion  Toy          Hobby
------  -----------  ----------------
1       Teddy        Hold Teddy
1       Blue Light   Hold Teddy
1       Teddy        Look Cute
1       Blue Light   Look Cute
1       Teddy        Follow Kevin
1       Blue Light   Follow Kevin
§§§

As collections grow larger, duplicate rows explode quickly. With 5 collections of 10 elements each, a naive join can produce §10 × 10 × 10 × 10 × 10 = 100,000§ combinations for one root, even though the actual data contains only 50 child elements.

This increases:

- The number of rows the database must produce and return.
- Duplicate root and child data over the wire.
- Mapping and deduplication work in the application.
- Memory and time spent processing results.

Single Query Loading uses a different technique to combine collections without generating this full Cartesian product.

## 5. Technical idea: window functions and row numbers

Single Query Loading uses **analytic functions**, also called **window functions**, supported by databases. A key example is §ROW_NUMBER() OVER (PARTITION BY ...)§.

A window function computes over a group of rows while keeping each individual row in the result. For child collections, the framework can number each element's position within its owning root.

Example §toys§ table:

§§§sql
SELECT
    minion_id,
    name,
    ROW_NUMBER() OVER (
        PARTITION BY minion_id
        ORDER BY id
    ) AS toy_row
FROM toys;
§§§

Conceptual result:

§§§text
minion_id | name       | toy_row
----------+------------+--------
1         | Teddy      | 1
1         | Blue Light | 2
2         | ...        | 1
§§§

Similarly for §hobbies§:

§§§sql
SELECT
    minion_id,
    name,
    ROW_NUMBER() OVER (
        PARTITION BY minion_id
        ORDER BY id
    ) AS hobby_row
FROM hobbies;
§§§

Result:

§§§text
minion_id | name        | hobby_row
----------+-------------+----------
1         | Hold Teddy  | 1
1         | Look Cute   | 2
1         | Follow Kevin| 3
2         | ...         | 1
§§§

The framework can pair subsets by root ID and row number rather than pairing every toy element with every hobby element. The actual algorithm also handles empty collections and columns without matching values to reconstruct the exact aggregate structure.

The desired result looks like:

§§§text
Minion id | Toy          | Hobby
----------+--------------+----------------
1         | Teddy        | Hold Teddy
1         | Blue Light   | Look Cute
1         |              | Follow Kevin
2         | ...          | ...
§§§

Instead of the 6 Cartesian-product rows from the previous example, the result can represent elements at their corresponding positions without cross-multiplying entire collections.

### 5.1. Why are row numbers needed?

Databases return a flat table, whereas Java needs an object graph with roots and collections. Row numbers identify which element belongs at which position in each collection.

Conceptually:

- A root has representative rows.
- Each collection has its own row numbering within the root's scope.
- Collections are aligned by row number to form one flat result set.
- The mapper reads the result set and reconstructs aggregate objects along with their collections.

This is how relational data is transformed into an aggregate structure in a single result read.

**Note:** the SQL statements above only illustrate the window-function concept. Spring Data JDBC generates the Single Query Loading SQL itself; applications do not need to hand-write these subqueries, row numbers, or complex joins.

## 6. Support conditions and limitations

Enabling Single Query Loading does not mean every aggregate and every repository method automatically uses a single query. According to the Spring Data Relational 4.1.2 documentation, pay attention to the following conditions:

| Condition | Currently documented support scope |
| --- | --- |
| Version | Available since Spring Data JDBC 3.2. |
| Aggregate shape | No nested collections; this limitation also includes nested §Map§. |
| Embedded entities | The aggregate does not use embedded entities. |
| AggregateReference | The aggregate does not use §AggregateReference§. |
| Database dialect | The dialect must support the required analytic/window functions. |
| H2 and HSQL | These dialects do not support Single Query Loading according to current Spring Data JDBC documentation. |
| Repository methods | Only §CrudRepository§ find methods. |
| Derived queries | Not yet within the scope of Single Query Loading. |
| Annotated queries | Methods using §@Query§ are not yet within the scope of Single Query Loading. |
| Configuration | Must be enabled on §JdbcMappingContext§ via §setSingleQueryLoadingEnabled(true)§. |

The documentation also makes clear: if any of the conditions are not satisfied, Spring Data JDBC **falls back to the default aggregate loading mechanism**. Thus, the fact that the application still runs does not prove Single Query Loading was used.

### 6.1. Nested collections vs. multiple collections at the same level

Example with two direct collections under the root:

§§§text
Order
  ├── lines[]
  └── notes[]
§§§

These are sibling (same-level) collections.

Example with a collection nested inside a child element:

§§§text
Order
  └── lines[]
        └── adjustments[]
§§§

This is a nested collection. Current documentation lists nested collections as a limitation of Single Query Loading. Do not assume that having multiple collections automatically disqualifies an aggregate; examine the specific aggregate structure and published limitations.

### 6.2. AggregateReference and embedded entities

Example of an aggregate with another reference:

§§§java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        AggregateReference<Customer, Long> customer,
        String status
) {
}
§§§

Or an embedded entity:

§§§java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        @Embedded(prefix = "delivery_")
        DeliveryAddress deliveryAddress
) {
}
§§§

These aggregate shapes fall outside the Single Query Loading conditions stated in the 4.1.2 documentation. When using them, expect the default loading mechanism to be used.

### 6.3. Database dialect must support it

Spring Data JDBC uses a dialect to know how to generate SQL appropriate for the database. Single Query Loading requires analytic/window functions; not every dialect supports this mechanism in Spring Data JDBC.

Spring Data Relational 4.1.2 documentation states that all provided dialects are supported except H2 and HSQL. Therefore, if tests run on H2 while production uses PostgreSQL, observed SQL counts in tests may differ from production.

Do not conclude that the feature fails on all databases just because H2 tests fall back to default loading.

### 6.4. Repository method must be within the supported scope

Example find operations from §CrudRepository§:

§§§java
public interface MinionRepository
        extends CrudRepository<Minion, Long> {
}
§§§

Methods such as §findById§, §findAll§, and §findAllById§ belong to §CrudRepository§'s find methods.

A derived query:

§§§java
List<Minion> findByName(String name);
§§§

or a query annotated with §@Query§:

§§§java
@Query("SELECT * FROM minions WHERE name = :name")
List<Minion> findNamed(@Param("name") String name);
§§§

is outside the Single Query Loading scope described in current documentation. These methods still load aggregates using the default approach, even when the flag is enabled on the mapping context.

## 7. How to enable Single Query Loading

Single Query Loading is enabled via §JdbcMappingContext§ using the method:

§§§java
mappingContext.setSingleQueryLoadingEnabled(true);
§§§

§JdbcMappingContext§ extends §RelationalMappingContext§. This method sets the flag so Spring Data JDBC attempts to use Single Query Loading when the dialect and aggregate support it.

This is not a datasource configuration property like §spring.datasource.url§. Documentation instructs enabling the feature via the mapping context API, so the bean must be configured properly.

### 7.1. Configuring via AbstractJdbcConfiguration

One way to customize the infrastructure is to extend §AbstractJdbcConfiguration§ and override the §jdbcMappingContext§ bean. The example below follows the Spring Data Relational 3.3.x/4.x API with the three-parameter configuration method:

§§§java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.data.jdbc.core.convert.JdbcCustomConversions;
import org.springframework.data.jdbc.core.mapping.JdbcMappingContext;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;
import org.springframework.data.relational.RelationalManagedTypes;
import org.springframework.data.relational.core.mapping.NamingStrategy;

@Configuration
public class SingleQueryLoadingJdbcConfiguration
        extends AbstractJdbcConfiguration {

    @Override
    @Bean
    public JdbcMappingContext jdbcMappingContext(
            Optional<NamingStrategy> namingStrategy,
            JdbcCustomConversions customConversions,
            RelationalManagedTypes jdbcManagedTypes
    ) {
        JdbcMappingContext context = super.jdbcMappingContext(
                namingStrategy,
                customConversions,
                jdbcManagedTypes
        );

        context.setSingleQueryLoadingEnabled(true);

        return context;
    }
}
§§§

Explanation:

1. §AbstractJdbcConfiguration§ provides the core infrastructure beans needed by Spring Data JDBC.
2. The §jdbcMappingContext§ method creates the mapping context along with the naming strategy, custom conversions, and managed types.
3. Call §super.jdbcMappingContext(...)§ to retain Spring Data JDBC's default configuration.
4. Call §setSingleQueryLoadingEnabled(true)§ on that exact context.
5. Return the context with the flag enabled so converters and repositories share it.

**Key point:** you must customize the §JdbcMappingContext§ actually used by the JDBC infrastructure. Do not instantiate a separate standalone mapping context and call the setter on it, because repositories may still be using a different context bean.

If the application already has a class extending §AbstractJdbcConfiguration§, add the override to that existing configuration class. Avoid declaring two competing §JdbcMappingContext§ beans. With Spring Boot configuration, ensure repository infrastructure and converters share the same customized mapping context. If using Spring Data JDBC without Spring Boot, still configure repository activation as your application expects, such as §@EnableJdbcRepositories§.

### 7.2. Why call super before enabling the flag?

The superclass configuration method constructs the mapping context based on dependencies managed by Spring Data JDBC:

- §NamingStrategy§ to determine table/column names.
- §JdbcCustomConversions§ to register type conversions.
- §RelationalManagedTypes§ to supply managed/discovered types.

If you arbitrarily instantiate §new JdbcMappingContext()§, you risk bypassing those configurations. Calling §super.jdbcMappingContext(...)§ preserves the standard initialization and only changes the Single Query Loading flag.

### 7.3. If a custom JdbcMappingContext bean already exists

If the application defines a §JdbcMappingContext§ bean elsewhere, add the setter call to that existing bean:

§§§java
JdbcMappingContext context = ...; // properly configured context
context.setSingleQueryLoadingEnabled(true);
return context;
§§§

The principle remains **configure only the context actually being used**. Do not create two beans of the same type and hope Spring Data picks the right one.

## 8. An eligible aggregate example for testing

To observe Single Query Loading, use a simple aggregate with a root and one direct collection, without nested collections, embedded entities, or AggregateReference.

Example minion and hobby tables:

§§§sql
CREATE TABLE minions (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE hobbies (
    minion_id BIGINT NOT NULL REFERENCES minions(id),
    hobby_position INTEGER NOT NULL,
    name VARCHAR(150) NOT NULL,
    PRIMARY KEY (minion_id, hobby_position)
);
§§§

Aggregate root:

§§§java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("minions")
public record Minion(
        @Id Long id,
        String name,

        @MappedCollection(
                idColumn = "minion_id",
                keyColumn = "hobby_position"
        )
        List<Hobby> hobbies
) {
}
§§§

Child entity:

§§§java
import org.springframework.data.relational.core.mapping.Table;

@Table("hobbies")
public record Hobby(String name) {
}
§§§

Repository:

§§§java
import org.springframework.data.repository.CrudRepository;

public interface MinionRepository
        extends CrudRepository<Minion, Long> {
}
§§§

Try loading multiple aggregates:

§§§java
List<Minion> minions = StreamSupport
        .stream(minionRepository.findAll().spliterator(), false)
        .toList();
§§§

Or loading by ID:

§§§java
Minion minion = minionRepository.findById(1L)
        .orElseThrow();
§§§

When Single Query Loading is enabled and conditions are satisfied, Spring Data JDBC can use a single SELECT to load the root along with its collection. When conditions are not met, the framework automatically falls back to default loading.

This example only illustrates an eligible model; to confirm the mechanism is active, observe the actual SQL rather than only checking the Java result.

## 9. Observing whether Single Query Loading is actually used

After enabling the configuration, test with data containing many aggregates and multiple child entities. With only a single root or empty collections, statement counts may not clearly show the difference.

### 9.1. Preparing test data

For example:

- 50 minions.
- 5 hobbies per minion.
- Call §findAll()§ to load all aggregates.

With traditional loading, you can observe one root query plus many per-root collection queries. With Single Query Loading, the goal is to load the eligible aggregates in one SELECT statement.

### 9.2. Checking the number of queries

You can use SQL monitoring tools such as datasource-proxy, P6Spy, or JDBC logging in development environments to count statements.

When inspecting, distinguish between:

- Root-reading SQL statements.
- Collection-reading SQL statements.
- Queries emitted by another service in the same request.
- Migration, health check, or transaction metadata SQL.

Compare only statements belonging to the aggregate loading operation under test.

### 9.3. Comparing under identical conditions

A meaningful measurement should hold constant:

- The same database and version.
- The same data.
- The same repository method.
- The same number of aggregates.
- The same collection sizes.
- The same cache and connection pool state.
- The same timing methodology.

Track at least:

| Metric | Meaning |
| --- | --- |
| Number of SQL statements | Did round-trips decrease? |
| Total duration | Is overall operation speed better? |
| Result row count | Does the query return too many rows? |
| Transferred data | Are many columns or large payloads repeated? |
| Database CPU | Does the new query incur extra window-function processing? |
| Application CPU and heap | Does mapping the result set create extra memory pressure? |

### 9.4. Do not draw conclusions from SQL count alone

A single complex SQL query can take longer than several small queries under certain workloads. Single Query Loading reduces round-trips, but does not guarantee every application will be faster in every case.

Inspect execution plans, data volume, result row counts, and actual timing. If an aggregate is very large or the query loads too much unnecessary data, reducing the statement count may not be enough to improve overall performance.

## 10. How does fallback work?

A helpful aspect of this mechanism is that the framework can automatically revert to default loading when Single Query Loading cannot be used.

For example:

| Scenario | Expected outcome |
| --- | --- |
| Flag not enabled | Uses default aggregate loading. |
| Flag enabled, supported dialect, eligible aggregate, and using a CrudRepository find method | Attempts Single Query Loading. |
| Flag enabled, but database dialect not supported | Falls back to default loading. |
| Aggregate has a nested collection | Falls back to default loading. |
| Aggregate uses AggregateReference or embedded entity | Falls back to default loading. |
| Using a derived query | Does not use Single Query Loading; loads via default approach. |
| Using a `@Query` method | Does not use Single Query Loading; loads via default approach. |

Fallback ensures the application can still load aggregates via the traditional mechanism. However, it also means **a successfully running application cannot be used as proof that Single Query Loading actually took effect**.

## 11. Common misconceptions

**"One findAll call always generates only one SQL statement."** Incorrect. A repository call can issue multiple SQL statements to load roots and collections. Single Query Loading is the mechanism that helps reduce these statements within its supported scope.

**"Enabling setSingleQueryLoadingEnabled(true) makes every query run in one statement."** Incorrect. The dialect, aggregate structure, and repository method type must all qualify.

**"Single Query Loading is a database feature."** Not quite. The database provides window functions; Spring Data JDBC generates the SQL and maps the result according to Single Query Loading.

**"Just JOIN every collection onto the root."** Incorrect. Joining multiple collections can create a Cartesian product and multiply row counts. Single Query Loading uses window functions to align collections.

**"Single Query Loading replaces @Query."** Incorrect. It is an automatic aggregate-loading mechanism for supported find methods; custom queries remain a separate concern.

**"Testing on H2 is enough to evaluate the feature fully."** Incorrect under current dialect support in Spring Data JDBC documentation. H2/HSQL are not in the list of dialects supporting Single Query Loading; test on a database compatible with production.

**"This feature affects save and delete."** Incorrect. Single Query Loading focuses on loading/reading aggregates; write operations have their own mechanisms.

**"An aggregate with two direct collections is definitely a nested collection."** Incorrect. A nested collection is a collection inside a child collection/entity. Two collections that are direct properties of the root do not constitute nested collections; however, other limitations still need to be checked.

**"Not seeing query count drop means the setter doesn't work."** Not yet conclusive. The method used may not be supported, the aggregate shape may be incompatible, the dialect may be falling back, or logging may be counting unrelated queries.

**"One query is always faster than multiple queries."** Incorrect. You must measure duration, execution plans, row counts, and returned data volume in real workloads.

## 12. Process for enabling and evaluating in a project

You can roll this out using the following steps:

1. **Check Spring Data JDBC version:** available from 3.2; the version must expose the §setSingleQueryLoadingEnabled§ API.
2. **Identify the database dialect:** check whether the actual database dialect supports window functions per Spring Data JDBC.
3. **Choose an eligible aggregate:** avoid nested collections, embedded entities, and AggregateReference in the tested aggregate.
4. **Choose a repository method:** start with §CrudRepository.findAll()§, §findById()§, or a documented supported find method.
5. **Enable the flag on JdbcMappingContext:** override the bean in §AbstractJdbcConfiguration§ or customize the existing context bean.
6. **Prepare sufficiently large data:** multiple aggregates and populated collections so the difference in statement count is visible.
7. **Observe SQL:** count statements and inspect the generated SELECT.
8. **Measure performance:** compare duration, execution plans, row counts, and transferred data.
9. **Verify fallback:** test an out-of-scope method or aggregate to understand default behavior.
10. **Decide based on results:** keep the configuration only if real workloads benefit and the operations team understands the feature's limits.

§§§mermaid
flowchart TD
    A["Need to reduce round-trips when loading aggregates"] --> B{"Spring Data JDBC >= 3.2?"}
    B -->|No| C["No Single Query Loading"]
    B -->|Yes| D{"Dialect supports window functions?"}
    D -->|No| E["Use default loading"]
    D -->|Yes| F{"Aggregate has no nested collections,<br/>AggregateReference, or embedded entities?"}
    F -->|No| E
    F -->|Yes| G{"Using CrudRepository find method?"}
    G -->|No| E
    G -->|Yes| H["Enable on JdbcMappingContext"]
    H --> I["Observe SQL and measure workload"]
    I --> J{"Effective in practice?"}
    J -->|Yes| K["Keep config and monitor"]
    J -->|No| L["Re-evaluate query/model/indexes"]
§§§

## 13. Self-check questions

1. Why can a single §findAll()§ call generate multiple SQL statements in Spring Data JDBC?
2. How does the N+1 query problem occur when loading N aggregates that each have one collection?
3. Why can joining two collections simultaneously produce a Cartesian product?
4. How does the §ROW_NUMBER() OVER (PARTITION BY ...)§ window function help Single Query Loading align collections?
5. Which Spring Data JDBC version introduced Single Query Loading?
6. Which method on §JdbcMappingContext§ must be called to activate it?
7. Why must you configure the exact mapping context bean used by converters and repositories?
8. Which aggregate cases are currently incompatible according to the Spring Data Relational 4.1.2 documentation?
9. Why are H2/HSQL unsuitable environments for verifying this feature under current dialect support?
10. Why does a repository method annotated with §@Query§ not automatically use Single Query Loading?
11. If the flag is enabled but the aggregate is ineligible, what does the framework do?
12. Is a single SQL query always faster than multiple small SQL queries? Which metrics should be measured?

### Practice exercise

Create a §Minion§ aggregate with a §hobbies§ collection as in the example:

1. Create 50 minions, each with 5 hobbies.
2. Run §findAll()§ with Single Query Loading disabled and count SQL statements.
3. Enable §setSingleQueryLoadingEnabled(true)§ in the mapping context.
4. Run the same repository method again with the same data and a supported database.
5. Compare statement count, duration, and result row count.
6. Add a nested collection to the test model or switch to a method using §@Query§.
7. Observe the fallback behavior and explain why Single Query Loading is no longer used.
8. Re-run on the database used in production to avoid drawing conclusions from an unsupported dialect.

## 14. Key takeaways

- Single Query Loading was introduced in Spring Data JDBC 3.2 to load multiple aggregates in a single SELECT, reducing round-trips and mitigating N+1 when loading collections.
- The mechanism uses analytic/window functions, particularly row numbering, to combine collections into a flat result without the Cartesian product of naive JOINs.
- Enabled via §JdbcMappingContext.setSingleQueryLoadingEnabled(true)§.
- When customizing, configure the exact §JdbcMappingContext§ actually used by Spring Data JDBC; do not create a secondary context.
- According to Spring Data Relational 4.1.2 documentation, aggregates must not have nested collections (including Map), AggregateReference, or embedded entities; the dialect must be supported; and the method must be a §CrudRepository§ find method.
- Derived queries and annotated queries are not within the currently documented scope.
- H2 and HSQL dialects do not support Single Query Loading according to current Spring Data JDBC documentation.
- If a condition is not met, the framework falls back to default aggregate loading.
- Single Query Loading is marked experimental in the documentation; measure real workloads before deciding to adopt it.
- This feature affects data loading and does not change insert, update, or delete mechanisms.

When you understand Single Query Loading well, you can recognize when a repository call is causing N+1, know how to enable it on the right mapping context, and verify whether the database is actually using single-query loading. **The goal is to reduce aggregate-reading cost in suitable workloads while respecting mapping and dialect limits.**

## References

- [Spring Data Relational — Persisting Entities / Loading Aggregates](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Relational — RelationalMappingContext API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/RelationalMappingContext.html)
- [Spring Blog — Introducing Single Query Loading](https://spring.io/blog/2023/08/31/this-is-the-beginning-of-the-end-of-the-n-1-problem-introducing-single-query/)
