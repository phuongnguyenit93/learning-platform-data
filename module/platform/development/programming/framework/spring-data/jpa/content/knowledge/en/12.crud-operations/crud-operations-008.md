# existsById, count, and Query Cost

## Objectives

Spring Data JPA provides operations for checking existence and counting records, such as `existsById`, `existsBy...`, `count`, and `countBy...`. They all return compact results (`boolean` or `long`), but they have different purposes and costs.

- `existsById(id)` answers whether an entity exists by primary key.
- `existsBy...` is an application-declared query method using conditions on entity properties to check whether any matching record exists.
- `count()` counts the number of entities in the repository domain.
- `countBy...` counts records matching conditions.

Choosing the right operation helps avoid loading unnecessary entities, avoids counting data just to check presence, and limits repeated queries in loops or pagination.

## 1. existsById(): Checking by Primary Key

`JpaRepository` extends `CrudRepository`, which defines:

```java
boolean existsById(ID id);
```

Example:

```java
boolean exists = productRepository.existsById(42L);
if (!exists) {
    throw new EntityNotFoundException("Product not found");
}
```

The method returns `true` if an entity with that primary key exists and `false` otherwise. It does not return the entity.

### SQL Typically Executed

In modern versions of Spring Data JPA, `SimpleJpaRepository.existsById` typically issues a count query by ID rather than hydrating the entire entity:

```sql
select count(p)
from Product p
where p.id = ?
```

This is conceptual JPQL. Hibernate translates it into dialect-specific SQL, which may use different aliases and column names. With an indexed primary key, the database can usually check quickly via the index without reading the whole entity.

This is a common implementation detail, not a guarantee that every version/provider emits the exact same SQL statement. For composite IDs, some code paths may fall back to `findById` due to parameter binding differences. When specific optimization is needed, enable SQL logging and measure on the actual version.

### When Should existsById Be Used?

- When only a yes/no answer by primary key is needed.
- When no other entity properties are needed.
- When you want to avoid hydrating the entity and related associations.

If you need to update the entity right afterward, usually use `findById` or `EntityManager.find` to load the managed entity in a transaction and then perform the operation. Calling `existsById` followed by `findById` usually produces two round-trips.

## 2. existsBy...: Query Methods Checking by Properties

Spring Data JPA can derive existence-check queries from method names:

```java
boolean existsBySku(String sku);
boolean existsByCategoryAndActiveTrue(String category);
```

Spring Data parses the `existsBy` prefix and subsequent predicates based on the entity's Java properties. The query may fetch just enough information to determine whether a match exists rather than returning full entities. The exact SQL depends on the Spring Data JPA version and JPA provider; query derivation typically limits results so it does not have to fetch every matching row.

Usage example:

```java
if (productRepository.existsBySku(sku)) {
    throw new DuplicateSkuException(sku);
}
```

This method checks by `sku`; it does not require `sku` to be the primary key. Property names must match properties on the entity; if the Java field is `sku` while the database column is `product_code`, the method name is still `existsBySku`.

### existsBy and countBy Differ

- `existsBySku(sku)` answers whether at least one row satisfies the condition.
- `countBySku(sku)` counts the exact number of rows satisfying the condition.

If business logic only needs a boolean, avoid `countBySku(sku) > 0`, because requiring an exact count can force the database to do more work than necessary. Using `existsBySku` expresses intent clearly and lets the framework/provider select an appropriate checking strategy.

## 3. count(): Counting All Entities

`JpaRepository` provides:

```java
long count();
```

Example:

```java
long totalProducts = productRepository.count();
```

`count()` returns the number of entities in the repository domain. For a simple entity, the SQL usually resembles:

```sql
select count(*)
from products
```

Spring Data JPA typically constructs a JPQL count query and lets the provider translate it to SQL. The query can be more complex when the entity uses inheritance, filters, special mappings, or customized queries.

The return type is `long` because record counts can exceed the limit of `int`. Do not cast to `int` without range checking.

## 4. countBy...: Counting by Condition

Query derivation supports counting by properties:

```java
long countByActiveTrue();
long countByCategory(String category);
long countByCategoryAndActiveTrue(String category);
```

Example:

```java
long activeBooks = productRepository.countByCategoryAndActiveTrue("BOOK");
```

Conceptual SQL:

```sql
select count(*)
from products
where category = ?
  and active = true
```

Conditions are parsed from the method name and entity properties. Predicates such as `And`, `Or`, `IsNull`, `In`, `Between`, or conditions across relationships can be combined as long as query derivation syntax supports them.

Counting across relationships can generate joins. For example, `countByCategoryName("Books")` may require joining product and category. In that case, inspect the SQL and execution plan to understand the actual cost.

## 5. COUNT and EXISTS Have Different Costs

`COUNT` must return an exact quantity. `EXISTS` only needs to determine whether at least one matching row exists. This difference matters when result sets are large.

| Need | Suitable approach | Reason |
| --- | --- | --- |
| Check if an ID exists | `existsById(id)` | Only need a boolean by primary key. |
| Check if a record exists by SKU/email | `existsBySku(value)` | Query method clearly expresses existence intent. |
| Count total records | `count()` | Exact count is required. |
| Count records by status | `countByStatus(status)` | Exact count within a group is required. |
| Fetch data for display or update | `findById` / query returning entity | Need entity contents, not just a boolean. |

### Does COUNT(*) Always Scan the Full Table?

You cannot conclude that from the SQL statement alone. The database may use indexes, index-only scans, statistics, partition pruning, or other strategies. Still, to return an exact count, the database must process enough information about the set of qualifying rows. On large tables, `count()` can consume considerable I/O and CPU, even though the query returns very little data to the application.

`EXISTS` often has an advantage because the database can stop as soon as it finds a matching row. However, the optimizer, indexes, predicates, joins, and database engine determine the actual execution plan. There is no universal rule that every exists query is always faster than every count query.

### How Do Indexes Affect It?

For instance, `existsBySku` or `countByCategory` generally benefits from suitable indexes:

```sql
create unique index ux_products_sku on products(sku);
create index ix_products_category on products(category);
```

- A unique index on `sku` both speeds up lookups and ensures no two products share the same SKU.
- An index on `category` can help filter or count by category, depending on selectivity and the execution plan.
- For queries with multiple conditions, a composite index may be better, with column order determined by workload.

Indexes add overhead to INSERT/UPDATE/DELETE operations and consume storage. Do not index every field; check execution plans and real metrics first.

## 6. Can existsById Followed by save Prevent Duplicate Data?

No. The following pattern has a race condition:

```java
if (!repository.existsById(id)) {
    repository.save(entity);
}
```

Two concurrent transactions can both check `false` and then both attempt to insert. Checking existence beforehand does not lock the gap between SELECT and INSERT.

For uniqueness conditions such as email or SKU, place a unique constraint/index in the database. The application can check beforehand to present a friendly message, but it must still handle unique constraint errors on write.

```sql
alter table products
add constraint uk_products_sku unique (sku);
```

For updates by ID, optimistic locking (`@Version`) can be used to detect concurrent overwrites. Choose transaction isolation or locking when business logic needs stronger guarantees; do not use an exists check as a locking mechanism.

## 7. Avoiding N+1 Existence-Check Queries

A common performance mistake is looping over a list of IDs and calling `existsById` per item:

```java
for (Long id : ids) {
    if (repository.existsById(id)) {
        // process
    }
}
```

With N IDs, this can create N queries. For large counts, consider a single query over the ID set or a query fetching only the needed data:

```java
List<Product> products = repository.findAllById(ids);
Set<Long> foundIds = products.stream()
        .map(Product::getId)
        .collect(Collectors.toSet());
```

Compare `foundIds` against the input list to identify missing IDs. If you only need to check an ID set without needing entities, you can write a repository query returning a list of IDs or use an appropriate native/JPQL query. Split into batches if the list exceeds the database's bind parameter limit.

`findAllById` does not guarantee preserving input order and does not create placeholders for nonexistent IDs. If order matters, reconstruct the result according to the initial ID list.

## 8. count and Pagination

`Page<T>` typically needs the total element count to provide `getTotalElements()` and `getTotalPages()`. Thus, a paginated query may issue:

1. A query fetching the page of data with limit/offset or equivalent syntax.
2. A count query to determine the total number of rows matching the criteria.

With large tables or complex predicates, the count query can be the most expensive part of pagination.

If the UI only needs to know whether there is a next page, using `Slice<T>` or `Window<T>` as appropriate can avoid requesting an exact total count. Keyset/scroll pagination can be more suitable than offset pagination when data is large and has a stable sort key.

Do not manually call `count()` and then also use `Page` if `Page` already performs the count query; that could count twice.

## 9. Runnable Example with Java 17+, Spring Boot, and H2

This example creates a repository with `existsById`, `existsBySku`, `count`, and `countBy...` query methods. The project uses Spring Boot 3.4.5, Java 17, and an H2 in-memory database.

### Project Structure

```text
crud-query-cost/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/querycost/
        │   ├── QueryCostApplication.java
        │   ├── Product.java
        │   └── ProductRepository.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>crud-query-cost</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:querycost;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Product.java`

```java
package com.example.querycost;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 40)
    private String sku;

    @Column(nullable = false, length = 40)
    private String category;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
    }

    public Product(String sku, String category, boolean active) {
        this.sku = sku;
        this.category = category;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }
}
```

### `ProductRepository.java`

```java
package com.example.querycost;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
    boolean existsBySku(String sku);

    boolean existsByCategoryAndActiveTrue(String category);

    long countByActiveTrue();

    long countByCategory(String category);
}
```

### `QueryCostApplication.java`

```java
package com.example.querycost;

import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class QueryCostApplication {
    public static void main(String[] args) {
        SpringApplication.run(QueryCostApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ProductRepository repository) {
        return args -> {
            List<Product> saved = repository.saveAll(List.of(
                    new Product("SKU-100", "BOOK", true),
                    new Product("SKU-200", "BOOK", true),
                    new Product("SKU-300", "TOOL", false)
            ));
            repository.flush();

            System.out.println("existsById: "
                    + repository.existsById(saved.get(0).getId()));
            System.out.println("missing id: " + repository.existsById(-1L));
            System.out.println("existsBySku: " + repository.existsBySku("SKU-200"));
            System.out.println("existsByCategoryAndActiveTrue: "
                    + repository.existsByCategoryAndActiveTrue("BOOK"));
            System.out.println("count: " + repository.count());
            System.out.println("active count: " + repository.countByActiveTrue());
            System.out.println("BOOK count: " + repository.countByCategory("BOOK"));
        };
    }
}
```

### Running the Application

```bash
mvn spring-boot:run
```

Output printed by the application:

```text
existsById: true
missing id: false
existsBySku: true
existsByCategoryAndActiveTrue: true
count: 3
active count: 2
BOOK count: 2
```

SQL logs may show different count/existence queries and SELECT statements depending on the Spring Data JPA, Hibernate, and H2 versions. Use these logs to verify the execution strategy in a real project.

## 10. How to Measure Query Cost

To evaluate an existence or count operation, do not look only at the timing of a single run. Instead:

1. Use data sized close to production.
2. Enable SQL logging in test environments to inspect query count and shape.
3. Use `EXPLAIN` or the database's execution plan to inspect indexes, scans, joins, and estimated rows.
4. Measure latency and database load under concurrency, after warm-up.
5. Test both matching cases, non-matching cases, and low-selectivity predicates.
6. Compare indexed vs. unindexed queries on a suitable data copy.

Avoid drawing production database conclusions from H2 in-memory. Query plans and costs depend on the database engine, statistics, indexes, data distribution, concurrency, and configuration.

## 11. Common Pitfalls

1. **Using count to check existence:** `countBy... > 0` asks for an exact count. Use `existsBy...` when only a boolean is needed.
2. **Loading an entity just to check presence:** `findById` may hydrate the entity and relationships; `existsById` is more appropriate when only a boolean is needed.
3. **Calling existsById then findById:** usually creates two queries. If the entity is needed, load it directly with `findById`.
4. **Calling exists in a loop:** generates N queries for N IDs. Consider querying by ID set or batching.
5. **Using exists checks to guarantee uniqueness:** suffers from race conditions. Use unique constraints/indexes and handle write errors.
6. **Counting large datasets without needing an exact total:** consider Slice or keyset pagination instead of Page if total count is unnecessary.
7. **Ignoring indexes:** predicates on unindexed columns can scan many rows; add indexes based on workload and verify with execution plans.
8. **Believing COUNT(*) always full-scans or EXISTS is always faster:** the optimizer can choose different strategies; measure on the real database.

## 12. Practical Guidelines

- Use `existsById` for boolean checks by primary key.
- Use `existsBy...` for property conditions when you only need to know whether a matching record exists.
- Use `count()` or `countBy...` when an exact quantity is needed.
- Use `findById` or entity-returning queries when data is needed for reading/updating.
- For unique business keys, use database unique constraints; pre-checking existence is only to improve user-facing messages.
- Check the count query generated by `Page`; use `Slice` if the total count is not needed.
- Measure execution plans, indexes, and latency on the actual database engine.

Key takeaway: **exists answers yes or no; count returns an exact quantity. Choose the API matching your actual need, avoid repeated queries, leverage proper indexes, and use database constraints to guarantee uniqueness in concurrent environments.**