# Avoiding Full Table Scans, Over-Selecting Columns, and Unnecessary Counts

## 1. Objectives

In Spring Data JPA, a query can return a full Entity, a projection containing only a few attributes, a page of data, or just a single number. Choosing the right result type reduces data read from the database, lowers application memory usage, and avoids unnecessary count queries.

This lesson focuses on three issues:
- **Full table reads:** calling `findAll()` without bounds can load too many rows into memory.
- **Over-selecting columns:** returning full Entities even when the screen only needs ID, name, and price.
- **Unnecessary counts:** using `Page` when the UI only needs to know if more data exists, or loading a list just to check whether any records exist.

After this lesson, you will be able to:
- Limit row counts using filters, `Pageable`, `Slice`, `Top`, and `First`.
- Use interface projections and DTO projections to fetch only required columns.
- Use dynamic projections when a single query serves multiple display formats.
- Choose between `Page`, `Slice`, and `List` based on metadata needs.
- Use `existsBy...` instead of loading Entities or counting all rows when checking existence.
- Write an appropriate `countQuery` for complex paginated queries.
- Inspect generated SQL to verify the application actually reads only needed data.

## 2. Avoiding Full Table Reads

Suppose a screen displays only 20 active products. The following call is usually unsuitable for large tables:

```java
List<Product> products = productRepository.findAll();
```

`findAll()` loads every Entity into the persistence context and application memory. If the table has hundreds of thousands of rows, the application can consume excessive memory, spend time transferring data over the network, and put pressure on the database.

Place filtering conditions and limits directly in the query:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id")));

Slice<ProductSummary> products =
        productRepository.findSliceByStatus(ProductStatus.ACTIVE, pageable);
```

The query retrieves only a bounded subset of results. Sorting includes `id` as a tie-breaker so the order stays deterministic when multiple products share the same `createdAt`.

If the use case always needs a small fixed count, you can use `Top` or `First`:

```java
List<ProductSummary> latestTwenty =
        productRepository.findTop20ProjectedByStatusOrderByCreatedAtDescIdDesc(
                ProductStatus.ACTIVE);
```

Do not use pagination merely to mask an unfiltered query when the business logic actually requires a specific scope. Define search filters, tenant/access scopes, and appropriate data limits right inside the query.

## 3. Avoiding Over-Selecting Columns with Projections

Suppose the `Product` Entity has many attributes: name, SKU, long description, status, price, creation timestamp, and other details. A listing page only needs:

```text
id, name, price
```

If the Repository returns `Product`, the ORM typically has to hydrate the Entity with all persistent columns required by the mapping. For a read-only list, that can fetch far more data than the UI requires.

A projection defines a narrower view of an Entity. Spring Data JPA can query only the requested attributes and return the projection type instead of the full Entity.

### 3.1. Closed Interface Projection

Create an interface declaring only the getters you need:

`src/main/java/com/example/catalog/ProductSummary.java`:

```java
package com.example.catalog;

import java.math.BigDecimal;

public interface ProductSummary {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
```

Repository:

```java
List<ProductSummary> findProjectedByStatus(ProductStatus status);
```

Invocation example:

```java
List<ProductSummary> rows =
        productRepository.findProjectedByStatus(ProductStatus.ACTIVE);

for (ProductSummary row : rows) {
    System.out.println(row.getName() + ": " + row.getPrice());
}
```

Because the interface only contains accessors corresponding to Entity properties, this is a closed projection. Spring Data knows which properties are used and can optimize the fetched columns.

This projection is suited for read-only lists. It is not a managed Entity; modifying a projection will not be automatically persisted by JPA dirty checking like an Entity.

### 3.2. Using Projections with Pageable

Projections can be combined with `Pageable` and `Slice`:

```java
Slice<ProductSummary> findSliceByStatus(
        ProductStatus status, Pageable pageable);
```

Example:

```java
Slice<ProductSummary> slice = productRepository.findSliceByStatus(
        ProductStatus.ACTIVE,
        PageRequest.of(0, 20,
                Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))));
```

The Repository returns only the projection attributes for at most one slice of data. `Slice` also indicates whether a next page exists without needing the total row count.

### 3.3. Open Projections and Optimization Limits

An open projection can use SpEL to access any property of the target Entity:

```java
public interface ProductDisplay {
    @Value("#{target.name + ' (' + target.sku + ')'}")
    String getDisplayName();
}
```

Because the expression can access arbitrary properties, Spring Data cannot always determine the minimal set of columns to fetch. Open projections can forfeit column-selection optimizations.

For large list queries, prefer closed projections or DTO projections with an explicit property list. Nested projections across associations can also cause the provider to join and materialize extra data; inspect the SQL instead of assuming only a single column is fetched.

## 4. DTO Projections via Constructor Expressions

If you want a concrete return type, use a DTO or Java record. A DTO is not an Entity and is not managed in the persistence context.

`src/main/java/com/example/catalog/ProductCard.java`:

```java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductCard(Long id, String name, BigDecimal price) {
}
```

JPQL constructor expression:

```java
@Query("""
       select new com.example.catalog.ProductCard(
           p.id, p.name, p.price)
       from Product p
       where p.status = :status
       order by p.createdAt desc, p.id desc
       """)
List<ProductCard> findCardsByStatus(
        @Param("status") ProductStatus status);
```

JPQL must use the fully qualified class name in the constructor expression. Parameter order and types must match the record's canonical constructor.

DTO projections are useful when:
- The API only needs a fixed set of fields.
- You want responses decoupled from Entity mappings.
- You need to return aggregated data or fields computed in the query.
- You want to separate the read model from the Entity used for updates.

Do not use a DTO projection and expect field changes to be saved via `save()` like an Entity. If updates are needed, load the appropriate Entity, mutate it within a transaction, or use an explicit update statement.

## 5. Dynamic Projections

Sometimes the same filter criteria need to return different data shapes. Dynamic projections let the caller choose the result type via a `Class<T>` parameter:

```java
<T> List<T> findByStatus(ProductStatus status, Class<T> projectionType);
```

Calling with an interface projection:

```java
List<ProductSummary> summaries = productRepository.findByStatus(
        ProductStatus.ACTIVE, ProductSummary.class);
```

Calling with a DTO:

```java
List<ProductCard> cards = productRepository.findByStatus(
        ProductStatus.ACTIVE, ProductCard.class);
```

Spring Data recognizes a `Class<T>` matching the generic return type as a dynamic projection parameter. The DTO's constructor must match the properties Spring Data uses to instantiate the projection.

Dynamic projections help reuse filter conditions, though you should avoid creating too many arbitrary return types. Each projection should represent a specific, stable read requirement.

## 6. When Should You Return an Entity?

Projections do not replace Entities in every scenario. Return an Entity when the use case needs to:

- Mutate data and rely on dirty checking.
- Execute business logic via Entity domain methods.
- Use Entity associations or lifecycle callbacks.
- Have a managed Entity inside a transaction.

Example status update:

```java
@Transactional
public void deactivate(Long id) {
    Product product = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Product not found"));
    product.deactivate();
}
```

Here an Entity is the right choice because the Service invokes a domain method and relies on JPA persisting changes upon transaction flush.

For read-only listing screens, using a projection is generally better than loading full Entities and mapping each object to a DTO afterward:

```java
// Loads the full Entity only to discard unneeded fields afterward.
List<ProductCard> cards = repository.findByStatus(ProductStatus.ACTIVE)
        .stream()
        .map(p -> new ProductCard(p.getId(), p.getName(), p.getPrice()))
        .toList();
```

The code above constructs DTOs after Entities have already been loaded. If the goal is to reduce columns read from the database, push the projection down into the Repository.

## 7. Page, Slice, and List: Avoiding Unnecessary Count Queries

The three common return types when a Repository accepts `Pageable` differ in cost and metadata:

| Return type | Metadata | Count query | When to use |
| --- | --- | --- | --- |
| `Page<T>` | Current page, total rows, and total pages. | May need a count query to compute totals; the framework can optimize in certain cases. | The UI genuinely needs to display total results/pages. |
| `Slice<T>` | Current page and `hasNext()`/`hasPrevious()`. | No full count needed; typically fetches one extra row to check if a next page exists. | "Load more" buttons, infinite scroll, or only needing to know if more data exists. |
| `List<T>` + `Pageable` | Only the page's content list. | No count query needed to build page metadata. | The caller only needs the rows within a data window. |

### 7.1. Page When Exact Totals Are Needed

```java
Page<ProductSummary> findPageByStatus(
        ProductStatus status, Pageable pageable);
```

`Page` provides:

- `getContent()`: page content.
- `getNumber()`: current page index.
- `getSize()`: requested page size.
- `getNumberOfElements()`: actual number of rows in the page.
- `getTotalElements()`: total rows matching the filter.
- `getTotalPages()`: total number of pages.

To populate `getTotalElements()` and `getTotalPages()`, Spring Data usually needs to execute a count query. In certain cases the framework can deduce the total from the page content and skip the count; therefore, do not assume every `Page` call always issues exactly two SQL statements.

### 7.2. Slice When Only Checking for More Data

```java
Slice<ProductSummary> findSliceByStatus(
        ProductStatus status, Pageable pageable);
```

Suppose the page size is 20. Spring Data typically requests one extra row to determine `hasNext()`. The caller receives at most 20 rows and a flag indicating whether more data exists. There is no total row count or total page count.

If the UI does not display totals, `Slice` usually avoids unnecessary count overhead.

### 7.3. List with Pageable When Only Content Is Needed

```java
List<ProductSummary> findPageContentByStatus(
        ProductStatus status, Pageable pageable);
```

This method returns the requested page's list without total metadata. Use it when the Service already manages navigation or the client only needs the page contents.

Do not confuse `List` without metadata with an unbounded query. When `Pageable` is passed, the query is still bounded by page size and offset.

## 8. Using exists Instead of Loading or Counting

If the business question is simply "does a product with this SKU exist?", there is no need to load an Entity:

```java
boolean existsBySku(String sku);
```

If you write:

```java
boolean exists = !repository.findBySku(sku).isEmpty();
```

The Repository may have to load matching Entities into memory just to check if the list is empty. `existsBySku` clearly expresses intent and lets Spring Data generate an appropriate existence query.

Do not use `countBySku(sku) > 0` when you only need existence. `countBySku` is appropriate when the business logic actually needs the number:

```java
long activeCount = repository.countByStatus(ProductStatus.ACTIVE);
```

Distinguish them:

| Question | Repository method |
| --- | --- |
| Does this SKU exist? | `existsBySku(sku)` |
| How many ACTIVE products are there? | `countByStatus(ACTIVE)` |
| Fetch the first matching product? | `findFirstBySkuOrderByCreatedAtDescIdDesc(sku)` |
| Fetch at most 20 newest products? | `findTop20ProjectedByStatusOrderByCreatedAtDescIdDesc(status)` |

Avoid loading an entire list and calling `.size()` to get the row count. Use `countBy...` when you need a total, and `existsBy...` when you only need a boolean.

## 9. Optimizing Count Queries for Page

For simple queries, Spring Data can derive the count query automatically. For complex queries, especially those with joins or `distinct`, declare a separate `countQuery` to count root Entities accurately.

Example query joining a tag collection:

```java
@Query(
    value = """
        select distinct new com.example.catalog.ProductCard(
            p.id, p.name, p.price)
        from Product p
        join p.tags t
        where p.status = :status
          and t.name = :tagName
        """,
    countQuery = """
        select count(distinct p.id)
        from Product p
        join p.tags t
        where p.status = :status
          and t.name = :tagName
        """
)
Page<ProductCard> findCardsByStatusAndTag(
        @Param("status") ProductStatus status,
        @Param("tagName") String tagName,
        Pageable pageable);
```

A one-to-many join can produce multiple rows for the same Product. `count(p)` may double-count roots; `count(distinct p.id)` reflects the unique Products in this example.

The count query should keep the same filtering conditions as the data query. Do not include `order by` in the count query. If the count query remains very expensive and the UI does not need the total, switch the return type to `Slice` or `List` with `Pageable` instead of trying to optimize an unused number.

## 10. Complete Entity and Repository Example

This example uses Java 17+, Spring Boot 3.x, Spring Data JPA, and an application-managed database. The Entity has enough attributes to demonstrate projections.

`src/main/java/com/example/catalog/ProductStatus.java`:

```java
package com.example.catalog;

public enum ProductStatus {
    DRAFT,
    ACTIVE,
    DISCONTINUED
}
```

`src/main/java/com/example/catalog/Product.java`:

```java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 160)
    private String name;

    @Column(nullable = false, unique = true, length = 40)
    private String sku;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ProductStatus status;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(length = 2000)
    private String description;

    protected Product() {
        // JPA requires a no-arg constructor.
    }

    public Product(String name, String sku, BigDecimal price,
            ProductStatus status, LocalDateTime createdAt, String description) {
        if (name == null || name.isBlank() || name.length() > 160) {
            throw new IllegalArgumentException("Name is required");
        }
        if (sku == null || sku.isBlank() || sku.length() > 40) {
            throw new IllegalArgumentException("SKU is required");
        }
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("Price cannot be negative");
        }
        if (status == null || createdAt == null) {
            throw new IllegalArgumentException("Status and createdAt are required");
        }
        this.name = name.trim();
        this.sku = sku.trim();
        this.price = price;
        this.status = status;
        this.createdAt = createdAt;
        this.description = description;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public String getSku() { return sku; }
    public BigDecimal getPrice() { return price; }
    public ProductStatus getStatus() { return status; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public String getDescription() { return description; }
}
```

`src/main/java/com/example/catalog/ProductSummary.java`:

```java
package com.example.catalog;

import java.math.BigDecimal;

public interface ProductSummary {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
```

`src/main/java/com/example/catalog/ProductCard.java`:

```java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductCard(Long id, String name, BigDecimal price) {
}
```

`src/main/java/com/example/catalog/ProductRepository.java`:

```java
package com.example.catalog;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends JpaRepository<Product, Long> {
    List<ProductSummary> findProjectedByStatus(ProductStatus status);

    List<ProductSummary> findTop20ProjectedByStatusOrderByCreatedAtDescIdDesc(
            ProductStatus status);

    <T> List<T> findByStatus(ProductStatus status, Class<T> projectionType);

    Slice<ProductSummary> findSliceByStatus(
            ProductStatus status, Pageable pageable);

    List<ProductSummary> findPageContentByStatus(
            ProductStatus status, Pageable pageable);

    @Query("""
           select new com.example.catalog.ProductCard(p.id, p.name, p.price)
           from Product p
           where p.status = :status
           """)
    Page<ProductCard> findCardPageByStatus(
            @Param("status") ProductStatus status, Pageable pageable);

    boolean existsBySku(String sku);

    long countByStatus(ProductStatus status);

    Optional<Product> findFirstBySkuOrderByCreatedAtDescIdDesc(String sku);
}
```

The Repository above illustrates different result types:

- `findProjectedByStatus`: interface projection.
- `findTop20ProjectedByStatus...`: fixed-limit list with deterministic ordering.
- `findByStatus(status, ProductCard.class)`: dynamic DTO projection.
- `findSliceByStatus`: pagination without needing a total count.
- `findPageContentByStatus`: page content as a List.
- `findCardPageByStatus`: DTO projection with Page metadata and an auto-derived count query for a simple query.
- `existsBySku` and `countByStatus`: returning only a boolean or count.

## 11. Service Choosing Query Types by Use Case

The Service should make clear whether the caller needs content, metadata, or a scalar value:

```java
package com.example.catalog;

import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ProductReadService {
    private static final int MAX_PAGE_SIZE = 100;

    private final ProductRepository repository;

    public ProductReadService(ProductRepository repository) {
        this.repository = repository;
    }

    public Slice<ProductSummary> browseActive(int page, int size) {
        Pageable pageable = validatedPageable(page, size);
        return repository.findSliceByStatus(ProductStatus.ACTIVE, pageable);
    }

    public List<ProductSummary> latestActive() {
        return repository.findTop20ProjectedByStatusOrderByCreatedAtDescIdDesc(
                ProductStatus.ACTIVE);
    }

    public boolean skuExists(String sku) {
        if (sku == null || sku.isBlank()) {
            return false;
        }
        return repository.existsBySku(sku.trim());
    }

    private Pageable validatedPageable(int page, int size) {
        if (page < 0) {
            throw new IllegalArgumentException("Page index must be zero or greater");
        }
        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("Page size must be between 1 and 100");
        }
        return PageRequest.of(page, size,
                Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id")));
    }
}
```

The Service caps page size so clients cannot request an excessively large page. For sequential browsing screens, `Slice` avoids the count query. For a widget needing only the 20 latest products, `Top20` suffices. For SKU checks, `existsBySku` returns a boolean without loading Entity lists.

## 12. Checking Actual SQL

Do not look solely at return types and assume a query is optimized. Inspect the SQL emitted by Hibernate to confirm:

- Projections select only needed columns, e.g., `id`, `name`, `price`.
- Queries include a `WHERE` clause matching the filter.
- Queries apply row limits and offsets when using Pageable.
- `Slice` does not emit a count query for the total row count.
- `Page` may emit a count query when totals are needed.
- `existsBy...` does not load full Entity lists.

In development or test environments, you can enable:

```properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
```

Do not enable bind parameter logging broadly in production if queries may contain sensitive data. SQL logging should be controlled per environment.

Expected SQL for a closed projection might look like:

```sql
select p.id, p.name, p.price
from products p
where p.status = ?
order by p.created_at desc, p.id desc
```

Exact SQL depends on dialect, naming strategy, and provider. What matters is verifying the selected column list, filter conditions, and result limits—not the exact aliases or formatting.

## 13. Testing with H2

This example uses `spring-boot-starter-data-jpa`, H2, and `spring-boot-starter-test`. `@DataJpaTest` tests the Repository in a test slice.

`src/test/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:projectiondb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/catalog/ProductProjectionTest.java`:

```java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

@DataJpaTest
class ProductProjectionTest {
    @Autowired
    private ProductRepository repository;

    private void insertProducts() {
        repository.saveAll(List.of(
                new Product("Keyboard", "KB-100", new BigDecimal("120.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-01T10:00:00"),
                        "Long description that the list does not need"),
                new Product("Mouse", "MS-200", new BigDecimal("35.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-02T10:00:00"),
                        "Another long description"),
                new Product("Monitor", "MN-300", new BigDecimal("250.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-03T10:00:00"),
                        "Panel details"),
                new Product("Draft keyboard", "KB-400", new BigDecimal("90.00"),
                        ProductStatus.DRAFT, LocalDateTime.parse("2026-01-04T10:00:00"),
                        "Not published")));
        repository.flush();
    }

    @Test
    void returnsOnlyTheRequestedProjectionProperties() {
        insertProducts();

        List<ProductSummary> result =
                repository.findProjectedByStatus(ProductStatus.ACTIVE);

        assertThat(result).hasSize(3);
        assertThat(result).extracting(ProductSummary::getName)
                .containsExactlyInAnyOrder("Keyboard", "Mouse", "Monitor");
        assertThat(result).allSatisfy(row -> {
            assertThat(row.getId()).isNotNull();
            assertThat(row.getPrice()).isNotNull();
        });
    }

    @Test
    void dynamicProjectionCanReturnDtoRecords() {
        insertProducts();

        List<ProductCard> result = repository.findByStatus(
                ProductStatus.ACTIVE, ProductCard.class);

        assertThat(result).hasSize(3);
        assertThat(result).extracting(ProductCard::name)
                .containsExactlyInAnyOrder("Keyboard", "Mouse", "Monitor");
    }

    @Test
    void sliceProvidesNextFlagWithoutTotalCountMetadata() {
        insertProducts();

        Slice<ProductSummary> slice = repository.findSliceByStatus(
                ProductStatus.ACTIVE,
                PageRequest.of(0, 2, Sort.by("id").ascending()));

        assertThat(slice.getContent()).hasSize(2);
        assertThat(slice.hasNext()).isTrue();
        assertThat(slice.getNumber()).isZero();
    }

    @Test
    void pageDtoReturnsTotalWhenTheCallerNeedsIt() {
        insertProducts();

        Page<ProductCard> page = repository.findCardPageByStatus(
                ProductStatus.ACTIVE,
                PageRequest.of(0, 2, Sort.by("name").ascending()));

        assertThat(page.getContent()).hasSize(2);
        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }

    @Test
    void existenceAndCountMethodsReturnOnlyScalarResults() {
        insertProducts();

        assertThat(repository.existsBySku("KB-100")).isTrue();
        assertThat(repository.existsBySku("UNKNOWN")).isFalse();
        assertThat(repository.countByStatus(ProductStatus.ACTIVE)).isEqualTo(3);
    }
}
```

Run tests from the directory containing `pom.xml`:

```bash
mvn test
```

The expected result is Maven finishing with `BUILD SUCCESS`. The tests verify interface projections, dynamic DTO projections, Slice, Page metadata, existence, and count. This is the expected outcome of the example; no actual build log is attached.

Data tests verify return types and contents. To confirm exact SQL column counts and the absence of count queries, inspect SQL logs or use SQL measurement tools in integration tests; assertions on Java results alone do not prove the SQL shape.

## 14. Common Pitfalls

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Projection getter returns null | Getter name does not match Entity property or projection alias. | Use exact property names and inspect SQL/aliases. |
| Projection still selects many columns | Using open SpEL projections or nested projections needing multiple associations. | Prefer flat closed projections or DTO constructor expressions. |
| Loading Entities then converting to DTO | Projection happens in Java after the query already hydrated Entities. | Push projection down to Repository/JPQL to reduce columns from the database. |
| `Page` slower than expected | Count query is expensive, especially with joins or complex filters. | Use Slice/List if total is not needed; write a dedicated `countQuery` if Page is required. |
| Count double-counts records | Collection joins produce multiple rows per root Entity. | Use `count(distinct root.id)` and keep matching filter conditions. |
| `findAll().size()` loads massive data | Application fetches all Entities just to know the count. | Use `countBy...` if you need a count, `existsBy...` if you only need a boolean. |
| `exists` implemented by fetching a list | Caller only needs existence, but Repository returns an Entity collection. | Use derived query `existsBy...`. |
| Deep pages run slowly | Large offsets force the database to skip many rows. | Limit page size; consider keyset/scrolling pagination when browsing large datasets. |
| Using projection for updates fails to save | DTO/interface projections are not managed Entities. | Load the Entity for use cases that modify data. |
| Fetch join makes query heavy or duplicates roots | Collection joins expand returned rows and columns. | Use projections, batch fetching, or an appropriate two-step query. |

## 15. Design Principles

1. Do not call unbounded `findAll()` for listing screens or APIs returning large datasets.
2. Put appropriate filters and limits directly in the Repository query.
3. Use closed interface projections or DTO projections when only a subset of attributes is needed.
4. Use Entities when you need domain behavior, dirty checking, or lifecycle callbacks; use DTOs for read models.
5. Use `Slice` when you only need to know if a next page exists; use `Page` when total counts are a real requirement; use `List` with Pageable when only page content is needed.
6. Use `existsBy...` for yes/no existence questions and `countBy...` when you genuinely need a count.
7. Never load a list and call `.size()` just to count rows.
8. For complex Page queries, declare an accurate `countQuery` and use `count(distinct id)` if joins multiply rows.
9. Keep sorting deterministic with a unique tie-breaker like ID; enforce page size limits in the Service/API.
10. Inspect actual SQL to verify selected columns, filters, limits, and count queries.
11. Measure performance on a production-like database; H2 does not fully represent execution plans of every engine.
12. Only optimize data and counts that the use case actually needs; avoid adding complex queries or projections without measurable benefit.

## 16. Completion Checklist

- [ ] Can explain why unbounded `findAll()` can trigger full table loads.
- [ ] Can create a closed interface projection containing only needed fields.
- [ ] Can create a DTO/record projection using a JPQL constructor expression.
- [ ] Can use dynamic projections with `Class<T>`.
- [ ] Can distinguish projections from managed Entities.
- [ ] Can choose between `Page`, `Slice`, or `List` with `Pageable`.
- [ ] Understand when `Page` requires a count query and when `Slice` avoids counting.
- [ ] Use `existsBy...` instead of loading Entities when checking existence.
- [ ] Use `countBy...` when business logic genuinely needs the total count.
- [ ] Write a proper `countQuery` for queries with joins.
- [ ] Inspect SQL to confirm no extra columns or unnecessary counts are executed.
- [ ] Test projections, pagination, existence, and counts with `@DataJpaTest`.

Once complete, you can design leaner Spring Data JPA read queries: fetching only the exact rows, columns, and metadata the use case needs.