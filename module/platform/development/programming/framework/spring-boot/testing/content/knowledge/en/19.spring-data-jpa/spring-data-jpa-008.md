# Spring Data JPA: Testing Pagination, Sorting, Projections, and Totals

## 1. Goal: Prove the Exact Data Set, Ordering, and Totals

A product list endpoint can return 20 items and still violate its contract because of **missing records, unstable ordering, duplicated total counts, projections leaking extra fields, or aggregate totals mismatched with filters**.

When testing Spring Data JPA, separate four questions:

1. **Pagination:** does this page have the right elements, offset, size, and next-page metadata?
2. **Sorting:** which `ORDER BY` do results obey, including when multiple records share the same sort value?
3. **Projection:** does the repository return the exact data shape for the use case, instead of forcing the API to carry full JPA entities?
4. **Totals/aggregates:** do `totalElements`, `totalPages`, `COUNT`, `SUM`, and grouped totals match the filter criteria, numeric precision, and intended semantics?

Example dataset of six products with five active products:

| ID | SKU | Category | Price | Active |
| --- | --- | --- | --- | --- |
| 101 | BOOK-101 | BOOK | 100.00 | true |
| 102 | BOOK-102 | BOOK | 50.00 | true |
| 103 | BOOK-103 | BOOK | 50.00 | true |
| 104 | BOOK-104 | BOOK | 25.00 | false |
| 105 | TOOL-105 | TOOL | 200.00 | true |
| 106 | TOOL-106 | TOOL | 150.00 | true |

If a query selects only `active=true`, sorted by `price ASC, id ASC`, with page size 2, we expect:

~~~text
Page 0: BOOK-102 (50),  BOOK-103 (50)
Page 1: BOOK-101 (100), TOOL-106 (150)
Page 2: TOOL-105 (200)

totalElements = 5
totalPages    = 3
pageSize      = 2
~~~

When aggregating **active only**:

~~~text
BOOK: count = 3, sum(price) = 200.00
TOOL: count = 2, sum(price) = 350.00
ALL:  count = 5, sum(price) = 550.00
~~~

This hands-on lesson builds that exact dataset and uses `@DataJpaTest` to test a **real repository with JPA/Hibernate and an H2 test database**, without mocking the repository. To test PostgreSQL/MySQL-specific SQL behavior, add integration tests on the corresponding database.

### What Will You Be Able to Do?

- Distinguish `Page<T>`, `Slice<T>`, `List<T>`, and their metadata.
- Use `PageRequest.of(page,size,Sort)`, `Sort.Order`, and secondary sorting by ID.
- Understand when Spring Data generates or may skip a `count query`, and when a dedicated `countQuery` is required.
- Write closed interface projections, DTO record projections, and dynamic projections.
- Test `COUNT`, `SUM`, `GROUP BY`, empty groups, negative/nullable values, and `BigDecimal`.
- Handle 0-based page bugs, page size limits, sort fields, join-to-many multiplication, N+1, offset drift, and data changing between two queries.
- Run a complete Java 17+/Spring Boot 3.5.x example with 10 JUnit Jupiter test methods practicing all topics.

## 2. Mechanism: Pageable, Sort, Page, Slice, and List

Spring Data accepts **special parameters** like `Pageable` and `Sort` to apply pagination and sorting without declaring separate repository methods for each page number.

~~~java
Page<Product> findByActiveTrue(Pageable pageable);
Slice<Product> findByCategory(String category, Pageable pageable);
List<Product> findByCategory(String category, Sort sort);
~~~

These are **method signatures inside a repository interface**, not a standalone runnable file. Each return type serves a distinct purpose.

| Return Type | Returns Page Content? | Knows If Next Exists? | Knows Full Set Total? | Typical Cost |
| --- | --- | --- | --- | --- |
| `Page<T>` | Yes | Yes | **Yes:** `totalElements`, `totalPages` | May require an extra count query |
| `Slice<T>` | Yes | Yes | **No** | Usually fetches just enough rows to detect next |
| `List<T>` + `Pageable` | Yes, without Page metadata | Not provided automatically | No | Limits query results without issuing a Page count |
| `List<T>` + `Sort` | Yes, all matching results | Not paged | No | Can load huge row sets if unbounded |

**Never equate `Page` with “always one List plus one count” in every situation.** Spring Data JPA can infer the total on certain pages—such as a partial last page smaller than page size—without executing a separate SQL count. Tests should verify the **public API values**, not hardcode the number of `SELECT COUNT` invocations when the framework or configuration may optimize them away.

### 2.1 What Does Each Piece of Metadata Mean?

Given `Page<Product> page`:

| API | Meaning |
| --- | --- |
| `getContent()` | Actual list of elements in the page |
| `getNumber()` | Page index, **starting at 0** |
| `getSize()` | Requested page size |
| `getNumberOfElements()` | Actual number of elements on the current page |
| `getTotalElements()` | Total matching elements **across the entire filtered set** |
| `getTotalPages()` | Total page count from total elements and page size |
| `isFirst()`, `isLast()` | First/last page position per metadata |
| `hasNext()`, `hasPrevious()` | Whether a next/previous page exists per metadata |
| `getSort()` | Sort order attached to the page |
| `map(converter)` | Transforms elements while generally preserving page metadata |

For example, `totalElements=5` and `size=2` produces `totalPages=3`, not 2. `getNumberOfElements()` on the last page is 1, while `getSize()` remains 2.

When no data matches, normally `totalElements=0`, `totalPages=0`, and `getContent().isEmpty()==true`. **Never fabricate a dummy page containing a null row** to represent an empty set.

### 2.2 PageRequest.of(page,size)

~~~java
Pageable first = PageRequest.of(0, 20);
Pageable second = PageRequest.of(1, 20);
Pageable sorted = PageRequest.of(
        0, 20, Sort.by(Sort.Order.asc("price"),
                     Sort.Order.asc("id")));
~~~

`page` is **0-based**, and `size` must be positive. `PageRequest.of(-1,10)` or `PageRequest.of(0,0)` throws `IllegalArgumentException`.

An API accepting `page` from clients must validate inputs, cap page size, and return an appropriate error (usually 400) before issuing a query. Do not pass `PageRequest.of(1,20)` to fetch the first page unless your API intentionally uses a 1-based client convention and converts it.

### 2.3 Conceptual SQL Equivalent

For page 2, size 20:

~~~sql
SELECT ...
FROM catalog_product
WHERE active = TRUE
ORDER BY price ASC, id ASC
LIMIT 20 OFFSET 40;
~~~

This is **illustrative SQL** in H2/PostgreSQL style, not SQL Hibernate guarantees across every database; dialects may emit `FETCH FIRST` or other syntax. Key takeaways:

- `OFFSET = page * size`.
- `ORDER BY` must be deterministic for stable pages.
- `LIMIT` caps rows, **without guaranteeing accurate totals** if joins multiply rows.

## 3. Correct and Stable Sorting: Always Think About a Tie-Breaker

A very common bug: two products both have price `50.00`. The query:

~~~java
Sort.by(Sort.Order.asc("price"));
~~~

does not specify whether ID 102 or ID 103 comes first. The database **is free** to return them in different orders on ties, especially when execution plans, indexes, or concurrency change.

To make ordering deterministic:

~~~java
Sort stable = Sort.by(
        Sort.Order.asc("price"),
        Sort.Order.asc("id"));
~~~

The secondary key `id` must be **unique and stable** in the set; this reduces the risk of duplicated or skipped items across page boundaries when data is static.

### 3.1 Two Ways to Build Sort

~~~java
Sort bySkuDesc = Sort.by(Sort.Direction.DESC, "sku");

Sort byPriceThenId = Sort.by(
        Sort.Order.asc("price"),
        Sort.Order.asc("id"));
~~~

`Sort.by("price")` defaults to ascending; `Sort.unsorted()` passes no sort. If a project requires explicit nulls-first/nulls-last ordering, note that `nullsFirst()`/`nullsLast()` options can act only as **hints** whose behavior depends on the JPA provider/DB.

### 3.2 Java Property Names, Not SQL Columns

Spring Data JPA `Sort` normally references **entity property names**, such as `price` or `category`, rather than raw column names like `PRICE_CENTS_DB`, unless the query defines matching aliases.

Never take a raw sort string from HTTP and concatenate it directly into custom SQL. With `@Query`, Spring Data supports `JpaSort.unsafe` for function expressions not validated as property paths; use that strictly for **trusted application-defined expressions**, never arbitrary client input.

### 3.3 Whitelisting Sort Fields at the API Boundary

An **illustrative service/controller helper, not a standalone file**:

~~~java
static Sort safeSort(String requested, boolean descending) {
    String property = switch (requested) {
        case "price" -> "price";
        case "name" -> "name";
        case "sku" -> "sku";
        default -> throw new IllegalArgumentException(
                "Unsupported sort field");
    };

    Sort.Direction direction = descending
            ? Sort.Direction.DESC : Sort.Direction.ASC;

    return Sort.by(
            new Sort.Order(direction, property),
            Sort.Order.asc("id"));
}
~~~

In a real API, map `IllegalArgumentException` cleanly to HTTP 400 or accept only a validated enum. The tie-breaker ID is fixed to `ASC` even when the primary sort direction flips. Multi-column sorting is still only an **ordering contract**; it does not freeze data if concurrent writes occur.

### 3.4 Offset Paging and Mutating Data

Even with deterministic `ORDER BY price,id`, if someone inserts or deletes a record with a lower price between fetching page 0 and page 1, `OFFSET` can cause an item to repeat or be skipped.

For large or rapidly changing feeds, consider **keyset/cursor pagination** (`Window<T>`, `ScrollPosition` with matching APIs), advancing from the sort-key tuple of the last item. Keyset avoids deep `OFFSET` scans and reduces page drift, yet **does not automatically provide `totalElements`**; it requires cursor logic, unique/non-null sort keys per contract, and dedicated tests under mutating data.

## 4. When Should You Use Page, Slice, or List?

| Use Case | Recommendation | Why |
| --- | --- | --- |
| UI showing “Page 1 of 12” and total results | `Page<T>` | Needs `totalElements`/`totalPages` |
| Infinite scroll needing only to know if more items exist | `Slice<T>` | Avoids counting the full dataset |
| Dropdown with at most a few dozen items, just sorted | `List<T> + Sort` or explicit limit | No pagination metadata needed |
| Exporting millions of rows | Stream/scroll/batch instead of one giant List | Avoids memory/offset overhead |
| Group counts/monetary totals report | Dedicated aggregate query | Page total is row count, not monetary sum |
| Lean projection list for mobile | `Page<Summary>` or `Slice<Summary>` | Returns only required fields |
| Near-real-time metrics dashboard | Aggregate/materialized view/counters as required | Full-table `COUNT` can be expensive |

**Rule:** Use `Page` only when the user **genuinely needs the total count**. Otherwise, `Slice` can eliminate count overhead. Conversely, if the product requires “247 results found”, never take `slice.getContent().size()` and pretend it is the total.

## 5. Count Query and totalElements: Count the Whole Set, Not the Page

With the method:

~~~java
Page<Product> findByActiveTrue(Pageable pageable);
~~~

Spring Data JPA generates the content query and a mechanism to compute the total matching `active=true`. When needed, the framework runs the corresponding count query. Even with a small page size, `totalElements` must reflect **all** matching active records, not just the rows on the current page.

Compare:

~~~text
page = 0, size = 2, content.size = 2
totalElements = 5
numberOfElements = 2
totalPages = 3
~~~

Never write `assertEquals(2, page.getTotalElements())` just because `page.getContent().size()==2`.

### 5.1 Why a Separate `countQuery` Matters

With a JPQL projection:

~~~java
@Query(
  value = """
      select new example.catalog.ProductCard(p.id, p.sku, p.price)
      from Product p
      where p.category = :category
      """,
  countQuery = """
      select count(p)
      from Product p
      where p.category = :category
      """)
Page<ProductCard> findCardsByCategory(
        @Param("category") String category,
        Pageable pageable);
~~~

Here:

- The content query returns **DTO `ProductCard`**, not the full entity.
- The count query must use the **exact same `category = :category` predicate**.
- The count query needs neither `ORDER BY` nor the DTO constructor.
- `Page` receives both content and total without forcing the count to match one page's size.

For simple queries, Spring Data can derive the count automatically. For `JOIN`, `DISTINCT`, `GROUP BY`, native SQL, and complex queries, **declaring `countQuery` explicitly** keeps semantics clear and prevents miscounts.

### 5.2 Real-World Count Query Bugs

**Mismatched predicates:** content filters `active=true AND category=:category`, while count filters only `category` → total is inflated.

**Joins multiplying root entities:** an order has 3 lines, `JOIN order.lines` yields 3 SQL rows; `count(o)` may count 3 where the UI expects 1 order. When the contract is distinct orders, consider `count(distinct o.id)` and structure the content query accordingly.

**Collection fetch join with Pageable:** `JOIN FETCH` on a collection + LIMIT/OFFSET can produce duplicate rows, in-memory pagination, or exceptions depending on Hibernate config. Do not treat this as a default “optimization”; use two steps: page IDs first, then fetch details for those IDs.

**Group by:** each content row represents **a group**, not an entity. When paging a list of groups, the total must be the **number of groups** satisfying filters/HAVING, not total entities. The count query may need `count(distinct key)` or a DB-appropriate subquery/native strategy.

**Optimization:** certain pages (especially a partial final page) can deduce total without running a count query. Tests should not assert “COUNT ran exactly once” when only public metadata accuracy is required.

### 5.3 PageableExecutionUtils Is Not a SQL Contract

Spring Data Commons uses a count-supplier optimization when constructing a `Page`, invoking it only when necessary. This explains why inspecting SQL logs sometimes shows no count query on certain pages. Do not mistake “no COUNT logged” for “`totalElements` must be wrong”, nor skip verifying totals because of this optimization.

A solid repository test verifies **content**, **predicates**, **totalElements**, and **totalPages** across multiple pages and empty cases. To test performance, measure SQL counts in dedicated benchmarks/integration tests on realistic data.

## 6. Projections: Returning Only the Shape Needed for the Use Case

Returning full `Product` entities from an API causes problems: lazy relationships, internal fields, fragile serialization, and persistence coupling. **Projections** let repositories return purpose-built views.

Spring Data supports **interface-based projections**, **DTO/class/record projections**, and **dynamic projections**. They are not 100% identical mechanisms: column selection, proxies, constructors, nested joins, and performance depend on the implementation.

### 6.1 Closed Interface Projection

Example:

~~~java
public interface ProductBrief {
    Long getId();
    String getSku();
    String getName();
    BigDecimal getPrice();
}
~~~

This is a **Java interface** whose getters match entity property names. With:

~~~java
Page<ProductBrief> findByCategoryAndActiveTrue(
        String category, Pageable pageable);
~~~

Spring Data JPA can generate a projection proxy and select only the required top-level attributes. Do not claim “every SQL projection always selects only four columns” without inspecting the query/provider, especially when nested projections or custom JPQL are involved.

**Tests should prove:**

1. The record set matches the predicate.
2. Each getter returns a value of the right type.
3. `Page<ProductBrief>` retains accurate pagination metadata.
4. API serialization or service mapping does not accidentally expose other entity fields.

A projection interface is a **read view**, not an entity to mutate and pass back to `save`.

### 6.2 Open Projection Using SpEL

Illustrative example:

~~~java
public interface ProductLabelView {
    String getSku();

    @Value("#{target.sku + ' - ' + target.name}")
    String getLabel();
}
~~~

`@Value` here is `org.springframework.beans.factory.annotation.Value`; `target` points to the underlying projection target object. This is an **open projection** because SpEL can touch arbitrary properties, making column-selection optimization difficult for the framework.

If you are just concatenating two already-exposed getters, a Java interface `default String getLabel() { return getSku()+" - "+getName(); }` is usually cleaner. Never mistake an open projection for an optimized “materialized computed SQL column”.

### 6.3 DTO/Record Projection

Java 17 record:

~~~java
public record ProductCard(
        Long id,
        String sku,
        BigDecimal price) {
}
~~~

In a JPQL `@Query` with a constructor expression:

~~~jpql
select new example.catalog.ProductCard(p.id, p.sku, p.price)
from Product p
where p.category = :category
~~~

The DTO name **must be fully qualified** inside the JPQL constructor expression. It must have a constructor matching the argument order and types. Records provide a canonical constructor suited for DTO projections and value-based `equals`.

Do not add `as id`/`as price` **inside the constructor expression**; aliases there are invalid per JPQL rules highlighted in the Spring Data JPA documentation.

### 6.4 Dynamic Projection

~~~java
<T> List<T> findByCategory(
        String category, Class<T> type);
~~~

Can be called as:

~~~java
List<ProductBrief> briefs =
        repository.findByCategory("BOOK", ProductBrief.class);

List<Product> entities =
        repository.findByCategory("BOOK", Product.class);
~~~

This is a **usage pattern assuming `ProductRepository`**. `Class<T>` picks the projection type at runtime. If another overload takes `Sort`/`Pageable`, Java resolves overloads by **parameter types**, not return type.

Use dynamic projections when multiple views genuinely share the same predicate; if all callers use one DTO, an explicit static method is simpler and easier to audit.

### 6.5 Nested Projections and Join Cost

A projection reading `order.customer.address.city` can generate joins and load more of the association graph than expected. “Projections fetch only declared fields” optimizes best for **top-level properties**; nested properties do not behave identically to selecting a single flat SQL column.

Never treat projections as an automatic cure for N+1, fetch joins, or transaction boundaries. For high-volume aggregate endpoints, inspect SQL logs, query counts, row multiplicity, and database execution plans.

## 7. Totals: Count, Sum, Group By, and Numeric Types

“Totals” carry at least three distinct meanings:

1. **Page totals:** `totalElements` and `totalPages` of the filtered query result.
2. **Domain counts:** `countByCategoryAndActiveTrue("BOOK")`, the count matching a dedicated predicate.
3. **Business aggregates:** `SUM(price)`, `AVG`, `MIN`, `MAX`, `COUNT` grouped by category, time window, tenant, or status.

They may relate, yet **never substitute for one another**. `getTotalElements()` is the number of **logical result rows** in a paged query—not revenue or total entities across the entire database.

### 7.1 Aggregate JPQL Constructor Projection

~~~java
@Query("""
    select new example.catalog.CategoryTotals(
        p.category, count(p), sum(p.price))
    from Product p
    where p.active = true
    group by p.category
    order by p.category
    """)
List<CategoryTotals> activeTotalsByCategory();
~~~

DTO:

~~~java
public record CategoryTotals(
        String category,
        Long productCount,
        BigDecimal totalPrice) {
}
~~~

Tests will verify BOOK has 3 products totaling 200.00 and TOOL has 2 products totaling 350.00. We use `Long` for `COUNT` and `BigDecimal` for `SUM(BigDecimal)`, avoiding `double` for monetary sums.

**COUNT(p)** counts matching entities; **COUNT(p.someNullableField)** counts only non-null values of that field. **COUNT(DISTINCT ...)** is needed when deduplicating. **SUM** over an empty set normally returns **null** in SQL/JPQL, whereas `COUNT` returns 0. With `GROUP BY`, if no groups match, the result is normally an **empty list**, not a group with count 0.

### 7.2 Group Totals Do Not Automatically Add Up to a System-Wide Total

To sum cleanly into a system-wide total, groups must be **non-overlapping**, share the **exact same filter**, use the same currency/unit, and exclude no rows via joins or `HAVING`.

For example, if active BOOK is 200.00 and active TOOL is 350.00, the active grand total is 550.00. If a `Page<Product>` query filters only category BOOK, metadata `totalElements` is **3**, not 5; never pull a total from another endpoint with a broader filter and attach it to a page as though they shared semantics.

### 7.3 Why Avoid `double` for Money?

~~~java
BigDecimal a = new BigDecimal("100.00");
BigDecimal b = new BigDecimal("50.00");

BigDecimal sum = a.add(b);
assertEquals(0, sum.compareTo(new BigDecimal("150.00")));
~~~

This is an **illustrative JUnit snippet**, requiring `BigDecimal` and `assertEquals` imports. `BigDecimal.equals` checks scale as well: `150.0` and `150.00` are not `equals`; `compareTo` compares numeric value. When serialization/money contracts require exact scale, test scale or formatting per policy separately.

When a system handles multiple currencies, **never add USD and EUR into a single total**; group by currency or convert with explicit exchange rates/rules.

### 7.4 Aggregates Under Changing Datasets

A pagination query and an aggregate query may execute at slightly different instants. Under `READ COMMITTED` isolation, another transaction can insert a row between the two reads; `totalElements=100` while `SUM` covers 101 rows is **not necessarily a math bug**, but a snapshot-consistency issue.

When an API requires strict point-in-time consistency, choose appropriate transaction isolation, snapshots, or reporting architecture, noting that a read-only transaction does not guarantee strong snapshots on every database. Test consistency with integration tests on a production-like DB rather than extrapolating from H2.

## 8. Runnable Example: Java 17+ / Spring Boot 3.5.x / Spring Data JPA

This section provides **a real mini-application** with a repository and `@DataJpaTest` suite; no HTTP server, Docker, cloud environment, or credentials needed. It uses in-memory H2 for CI repeatability while explicitly noting differences from PostgreSQL/MySQL.

### 8.1 File Structure

~~~text
src/
  main/
    java/example/catalog/
      CatalogApplication.java
      Product.java
      ProductBrief.java
      ProductCard.java
      CategoryTotals.java
      ProductRepository.java
  test/
    java/example/catalog/
      ProductRepositoryTest.java
~~~

All files use `package example.catalog;`. Tests reside under the same package hierarchy as the root `@SpringBootApplication` so Boot locates the root configuration for the test slice.

### 8.2 CatalogApplication.java

~~~java
package example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

This class provides the primary Boot configuration. `@DataJpaTest` loads only the **JPA test slice**, without starting a TCP server.

### 8.3 Product.java — Entity with Fixed IDs for Fixtures

~~~java
package example.catalog;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "catalog_product")
public class Product {

    @Id
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private String category;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
        // JPA requires a no-arg constructor.
    }

    public Product(
            Long id,
            String sku,
            String name,
            String category,
            BigDecimal price,
            boolean active) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.category = category;
        this.price = price;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

**Test-assigned IDs** (101–106) ensure ID tie-breaking does not depend on sequences or insert order. Production apps normally use `@GeneratedValue` or UUIDs per design. The entity has a `protected` no-arg constructor for JPA; tests use the public constructor to build fixtures.

Do not let a JPA entity automatically become the JSON response of every endpoint. `Product` here acts solely as domain/persistence; projection records or API DTOs are better suited for output.

### 8.4 ProductBrief.java — Closed Interface Projection

~~~java
package example.catalog;

import java.math.BigDecimal;

public interface ProductBrief {
    Long getId();
    String getSku();
    String getName();
    BigDecimal getPrice();
}
~~~

Getter names match the top-level attributes `id`, `sku`, `name`, `price`. Do not declare a hypothetical `getSecretToken()` when the entity has no matching property.

### 8.5 ProductCard.java — DTO Record Projection

~~~java
package example.catalog;

import java.math.BigDecimal;

public record ProductCard(
        Long id,
        String sku,
        BigDecimal price) {
}
~~~

### 8.6 CategoryTotals.java — Aggregate DTO

~~~java
package example.catalog;

import java.math.BigDecimal;

public record CategoryTotals(
        String category,
        Long productCount,
        BigDecimal totalPrice) {
}
~~~

These are **real DTOs**, not Mockito mocks. JPQL uses fully qualified type names inside constructor expressions.

### 8.7 ProductRepository.java — Page, Slice, Projections, Totals

~~~java
package example.catalog;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Page<Product> findByActiveTrue(Pageable pageable);

    Slice<Product> findByCategory(
            String category, Pageable pageable);

    List<Product> findByCategory(
            String category, Sort sort);

    Page<ProductBrief> findByCategoryAndActiveTrue(
            String category, Pageable pageable);

    <T> List<T> findByCategory(
            String category, Class<T> type);

    long countByActiveTrue();

    long countByCategoryAndActiveTrue(String category);

    @Query(
      value = """
          select new example.catalog.ProductCard(
              p.id, p.sku, p.price)
          from Product p
          where p.category = :category
          """,
      countQuery = """
          select count(p)
          from Product p
          where p.category = :category
          """)
    Page<ProductCard> findCardsByCategory(
            @Param("category") String category,
            Pageable pageable);

    @Query("""
        select new example.catalog.CategoryTotals(
            p.category, count(p), sum(p.price))
        from Product p
        where p.active = true
        group by p.category
        order by p.category
        """)
    List<CategoryTotals> activeTotalsByCategory();

    @Query("""
        select sum(p.price)
        from Product p
        where p.active = true
        """)
    BigDecimal sumActivePrices();
}
~~~

**Important notes:**

- `findByActiveTrue` is a derived query using boolean property `active`.
- `findByCategory(String,Pageable)` returns `Slice`; overload `findByCategory(String,Sort)` sorts without paging.
- `findByCategoryAndActiveTrue` returns an interface projection wrapped in `Page` with both category and active filters.
- Generic method `findByCategory(String,Class<T>)` is a **dynamic projection**, requiring no separate overloads per return type.
- `findCardsByCategory` uses a **JPQL constructor expression** and explicit count query with the same category filter. Because this query does not filter active, an inactive BOOK product is included.
- `activeTotalsByCategory` uses `COUNT`/`SUM` for **active products**, grouped by category; returns a List without Page metadata.
- `sumActivePrices()` returns `BigDecimal` for datasets with active rows; if a predicate matches zero rows, handle `null` or `COALESCE` per policy.
- Do not pass a `Sort` into a `GROUP BY` aggregate query in a way that distorts grouping; `ORDER BY category` here merely ensures deterministic output order.

## 9. `@DataJpaTest` with 10 JUnit Jupiter Tests

File `src/test/java/example/catalog/ProductRepositoryTest.java`:

~~~java
package example.catalog;

import java.math.BigDecimal;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=create-drop")
@DisplayName("Spring Data JPA: paging, sorting, projection, totals")
class ProductRepositoryTest {

    @Autowired
    ProductRepository repository;

    @Autowired
    EntityManager entityManager;

    @BeforeEach
    void seed() {
        List<Product> rows = List.of(
                product(101, "BOOK-101", "Java 17", "BOOK", "100.00", true),
                product(102, "BOOK-102", "JPA A", "BOOK", "50.00", true),
                product(103, "BOOK-103", "JPA B", "BOOK", "50.00", true),
                product(104, "BOOK-104", "Draft", "BOOK", "25.00", false),
                product(105, "TOOL-105", "IDE", "TOOL", "200.00", true),
                product(106, "TOOL-106", "Build", "TOOL", "150.00", true));

        rows.forEach(entityManager::persist);
        entityManager.flush();
        entityManager.clear();
    }

    private static Product product(
            long id, String sku, String name,
            String category, String price, boolean active) {
        return new Product(
                id, sku, name, category,
                new BigDecimal(price), active);
    }

    private static Sort priceThenId() {
        return Sort.by(
                Sort.Order.asc("price"),
                Sort.Order.asc("id"));
    }

    @Test
    @DisplayName("Page 0: exact two records, totalElements=5, totalPages=3")
    void pageMetadataUsesAllMatchingRows() {
        Page<Product> page = repository.findByActiveTrue(
                PageRequest.of(0, 2, priceThenId()));

        assertEquals(0, page.getNumber());
        assertEquals(2, page.getSize());
        assertEquals(2, page.getNumberOfElements());
        assertEquals(5L, page.getTotalElements());
        assertEquals(3, page.getTotalPages());
        assertEquals(List.of(102L, 103L),
                page.getContent().stream()
                        .map(Product::getId).toList());
        assertTrue(page.isFirst());
        assertTrue(page.hasNext());
        assertFalse(page.isLast());
    }

    @Test
    @DisplayName("ID tie-breaker gives deterministic ordering across 3 pages")
    void sortingHasDeterministicTieBreaker() {
        Page<Product> first = repository.findByActiveTrue(
                PageRequest.of(0, 2, priceThenId()));
        Page<Product> second = repository.findByActiveTrue(
                PageRequest.of(1, 2, priceThenId()));
        Page<Product> third = repository.findByActiveTrue(
                PageRequest.of(2, 2, priceThenId()));

        List<Long> orderedIds = Stream.of(first, second, third)
                .flatMap(p -> p.getContent().stream())
                .map(Product::getId)
                .toList();

        assertEquals(
                List.of(102L, 103L, 101L, 106L, 105L),
                orderedIds);
        assertEquals(1, third.getNumberOfElements());
        assertTrue(third.isLast());
        assertFalse(third.hasNext());
    }

    @Test
    @DisplayName("Slice knows hasNext without needing totalElements")
    void sliceReportsHasNext() {
        Slice<Product> first = repository.findByCategory(
                "BOOK", PageRequest.of(0, 2, priceThenId()));
        Slice<Product> second = repository.findByCategory(
                "BOOK", PageRequest.of(1, 2, priceThenId()));

        assertEquals(List.of(104L, 102L),
                first.getContent().stream()
                        .map(Product::getId).toList());
        assertEquals(List.of(103L, 101L),
                second.getContent().stream()
                        .map(Product::getId).toList());
        assertTrue(first.hasNext());
        assertFalse(second.hasNext());
        assertTrue(second.isLast());
    }

    @Test
    @DisplayName("List + Sort returns exact order without Page metadata")
    void listCanSortWithoutPaging() {
        List<Product> rows = repository.findByCategory(
                "BOOK", Sort.by(Sort.Direction.DESC, "sku"));

        assertEquals(
                List.of("BOOK-104", "BOOK-103",
                        "BOOK-102", "BOOK-101"),
                rows.stream().map(Product::getSku).toList());
    }

    @Test
    @DisplayName("Closed interface projection preserves Page totals")
    void interfaceProjectionKeepsPagingMetadata() {
        Page<ProductBrief> result =
                repository.findByCategoryAndActiveTrue(
                        "BOOK",
                        PageRequest.of(0, 2, priceThenId()));

        assertEquals(3L, result.getTotalElements());
        assertEquals(2, result.getTotalPages());
        assertEquals(List.of("BOOK-102", "BOOK-103"),
                result.getContent().stream()
                        .map(ProductBrief::getSku).toList());
        assertEquals(0,
                result.getContent().get(0).getPrice()
                        .compareTo(new BigDecimal("50.00")));
    }

    @Test
    @DisplayName("DTO JPQL projection uses countQuery with same predicate")
    void dtoProjectionHasCorrectCountQuery() {
        Page<ProductCard> result =
                repository.findCardsByCategory(
                        "BOOK",
                        PageRequest.of(0, 2, priceThenId()));

        // This query does NOT filter active: BOOK has 4 rows.
        assertEquals(4L, result.getTotalElements());
        assertEquals(2, result.getTotalPages());
        assertEquals(List.of(104L, 102L),
                result.getContent().stream()
                        .map(ProductCard::id).toList());
        assertEquals("BOOK-104",
                result.getContent().get(0).sku());
    }

    @Test
    @DisplayName("Dynamic projection chooses interface at call site")
    void dynamicProjectionReturnsExpectedFields() {
        List<ProductBrief> rows = repository.findByCategory(
                "TOOL", ProductBrief.class);

        Set<String> skus = rows.stream()
                .map(ProductBrief::getSku)
                .collect(Collectors.toSet());

        assertEquals(
                Set.of("TOOL-105", "TOOL-106"), skus);
        assertEquals(2, rows.size());
    }

    @Test
    @DisplayName("COUNT/SUM/GROUP BY match active rows")
    void aggregatesMatchFilteredRows() {
        List<CategoryTotals> totals =
                repository.activeTotalsByCategory();

        assertEquals(2, totals.size());
        assertEquals("BOOK", totals.get(0).category());
        assertEquals(3L, totals.get(0).productCount());
        assertEquals(0, totals.get(0).totalPrice()
                .compareTo(new BigDecimal("200.00")));

        assertEquals("TOOL", totals.get(1).category());
        assertEquals(2L, totals.get(1).productCount());
        assertEquals(0, totals.get(1).totalPrice()
                .compareTo(new BigDecimal("350.00")));

        assertEquals(5L, repository.countByActiveTrue());
        assertEquals(3L,
                repository.countByCategoryAndActiveTrue("BOOK"));
        assertEquals(0, repository.sumActivePrices()
                .compareTo(new BigDecimal("550.00")));
    }

    @Test
    @DisplayName("No matching rows: empty content, total=0")
    void emptyResultIsNotAOneRowPage() {
        Page<ProductBrief> none =
                repository.findByCategoryAndActiveTrue(
                        "MISSING",
                        PageRequest.of(0, 2, priceThenId()));

        assertTrue(none.getContent().isEmpty());
        assertEquals(0L, none.getTotalElements());
        assertEquals(0, none.getTotalPages());
        assertFalse(none.hasNext());
        assertEquals(0L,
                repository.countByCategoryAndActiveTrue("MISSING"));
    }

    @Test
    @DisplayName("Negative page and zero size are rejected")
    void invalidPageArgumentsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> PageRequest.of(-1, 2));
        assertThrows(IllegalArgumentException.class,
                () -> PageRequest.of(0, 0));
    }
}
~~~

**There are 10 `@Test` methods.** The tests use `@BeforeEach` to seed a **fresh dataset per test**, since `@DataJpaTest` rolls back transactions after each method by default. `EntityManager.persist/flush/clear` forces subsequent queries to actually read from the database rather than relying on objects still sitting in the persistence context.

### 9.1 What Each Test Actually Proves

| Test | Key Assertion | Bugs It Can Catch |
| --- | --- | --- |
| `pageMetadataUsesAllMatchingRows` | content 102,103, total 5 / pages 3 | Confusing count with page size, wrong predicate, wrong page index |
| `sortingHasDeterministicTieBreaker` | 3 pages yield exact 5 IDs, stable order | Sort missing ID tie-breaker, wrong boundary/offset |
| `sliceReportsHasNext` | BOOK Slice 4 rows, `hasNext` per page | Fabricating page totals instead of `hasNext` |
| `listCanSortWithoutPaging` | SKU DESC order accurate | Wrong sort direction/property |
| `interfaceProjectionKeepsPagingMetadata` | Active BOOK projection page total 3 | Wrong projection field or filter |
| `dtoProjectionHasCorrectCountQuery` | BOOK DTO includes inactive, total 4 | Count query predicate drift, broken DTO mapping |
| `dynamicProjectionReturnsExpectedFields` | Dynamic interface projection returns exact two TOOL rows | Wrong projection type or derived query |
| `aggregatesMatchFilteredRows` | BOOK 200, TOOL 350, all 550 | `COUNT`/`SUM`/`GROUP BY` wrong filter or data |
| `emptyResultIsNotAOneRowPage` | No match → total 0, empty content | Dummy fallback row, wrong count |
| `invalidPageArgumentsAreRejected` | Negative page / zero size throw | Accepting invalid paging inputs |

**Note:** `sortingHasDeterministicTieBreaker` on a static snapshot cannot prove pagination will not duplicate or skip items during **concurrent writes**. To test mutating data, add concurrency tests or keyset/transaction isolation semantics on a real database.

### 9.2 Exact COUNT Invocations Are Not What This Example Asserts

This lesson intentionally avoids spying on SQL logs to count `SELECT count(...)` calls. Spring Data optimizations may skip the count query on certain pages. What needs proof are **`totalElements = 5`, `totalPages = 3`, and accurate content**; inspect SQL count executions separately using SQL metrics/integration benchmarks when performance itself is the goal.

### 9.3 Why Use `BigDecimal.compareTo`?

On H2, `DECIMAL(12,2)` formatting typically returns two decimal places, yet providers and aggregate functions can return different scales. `compareTo` checks exact numeric value (200.00/350.00/550.00), whereas `equals` checks scale too. If an API contract requires `scale=2`, add scale/serialization assertions at the appropriate layer.

## 10. Gradle Configuration and How to Run

In a Spring Boot **3.5.x** project already configured with the Gradle plugin, dependency management, and Java 17 toolchain, add the following `dependencies` section to `build.gradle` (this snippet **is not a complete build file**):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

If a real production app needs to run standalone, add a production datasource/config; **H2 here is `testRuntimeOnly`** since only `@DataJpaTest` runs. The Java 17 toolchain and Spring Boot plugin must be configured in the rest of the build file.

Run command:

~~~bash
./gradlew test --tests example.catalog.ProductRepositoryTest
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.catalog.ProductRepositoryTest
~~~

**Expected result:** JUnit Jupiter discovers **10 test methods** and they PASS in a project containing all listed files and dependencies. The tests do not call `System.out.println`; console output shows Hibernate/Spring startup logs and Gradle `BUILD SUCCESSFUL`. This is an **expectation from code review**, not a confirmation log of an executed build.

### 10.1 Why Not Use `@SpringBootTest` for All of These Tests?

`@DataJpaTest` loads JPA repositories, entity manager, transaction support, and an appropriate test datasource instead of the full MVC/server/service graph. It is both faster and tightly scoped for testing real queries.

Do not create `@Mock ProductRepository` and assert `getTotalElements() == 5`, because a mock returns whatever you stub; such a test **checks neither the JPA query nor the `countQuery`**.

## 11. Testing Totals at the API Layer

Totals are often exposed in JSON APIs. When a controller returns `Page<ProductCard>` directly, JSON includes metadata serialized from Spring Data, yet `PageImpl`'s serialized structure can change across versions/configurations. When an API requires a long-lived contract, define a **stable response DTO**.

Example:

~~~java
public record PageEnvelope<T>(
        List<T> items,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean hasNext) {

    public static <T> PageEnvelope<T> from(Page<T> result) {
        return new PageEnvelope<>(
                result.getContent(),
                result.getNumber(),
                result.getSize(),
                result.getTotalElements(),
                result.getTotalPages(),
                result.hasNext());
    }
}
~~~

This is an **illustrative record class**, requiring `java.util.List` and `org.springframework.data.domain.Page` imports, placed in `PageEnvelope.java` when applied. It keeps JSON fields under application control instead of serializing entities or framework-internal types.

### 11.1 Filters Must Match Totals

`GET /products?category=BOOK&active=true&page=0&size=2` might return:

~~~json
{
  "items": [
    {"id": 102, "sku": "BOOK-102", "price": 50.00},
    {"id": 103, "sku": "BOOK-103", "price": 50.00}
  ],
  "page": 0,
  "size": 2,
  "totalElements": 3,
  "totalPages": 2,
  "hasNext": true
}
~~~

**Illustrative JSON matching an application contract**, not direct output from `ProductRepositoryTest`. Note that `Page<ProductCard> findCardsByCategory` in the repository example does not filter `active=true`; to produce this response, call a method/filter that matches (`findByCategoryAndActiveTrue` or a DTO query filtering active). **Never combine a total from a query without the active filter with content filtered by active.**

### 11.2 Testing the API with MockMvc/WebTestClient

When testing the HTTP layer:

- Send `page=0`, `size=2`, valid `sort`; assert 200, ordered items, `totalElements`/`totalPages`.
- Send negative page, `size=0`, or oversized page; assert 400 per validation policy.
- Send a disallowed sort field; assert 400 rather than turning raw input into a JPQL expression.
- Send a filter with no matches; assert `items=[]` and `totalElements=0`, not 404 unless the API explicitly specifies otherwise.
- With auth/tenancy, results and totals must include **only authorized records**; counts must never leak how many records another tenant owns.
- For projections, assert JSON omits internal entity fields even if present on the entity.

**Do not replace `@DataJpaTest` with HTTP tests.** HTTP tests mocking the repository test only controller mapping; repository tests need real queries.

## 12. Tricky Cases Requiring Dedicated Tests in Real Products

### 12.1 Pagination Over One-to-Many Relationships

Suppose each Order has many OrderLines. Joining Order with `lines` and paginating SQL rows causes an Order to appear multiple times and inflates counts.

~~~jpql
select distinct o
from Order o
join o.lines l
where l.status = :status
~~~

This is **illustrative JPQL**, without an `Order` entity in the mini-project. `DISTINCT` helps define the logical root set, yet combining collection fetch joins with pagination can force Hibernate into in-memory paging or fail depending on configuration.

A more reliable pattern:

1. Query **root IDs** by filter, sort, and `Pageable`.
2. Count `distinct root ID` for totals, if the API needs counts.
3. Fetch root/relationship details for the selected IDs.
4. Restore the exact paged ID order, since `IN (...)` does not guarantee ordering.

Seed a fixture with **one order having 3 lines and another having 1 line**; assert total roots = 2, not 4. Never use a fixture where every order has only one line, because such a test never catches row multiplication bugs.

### 12.2 Group By and HAVING

If a UI pages “categories whose total price exceeds 100”, the content query may use `GROUP BY category HAVING SUM(price) > 100`. The total must be the count of **matching category groups**, not total products.

Conceptual SQL example:

~~~sql
SELECT category, COUNT(*) AS product_count, SUM(price) AS total_price
FROM catalog_product
WHERE active = TRUE
GROUP BY category
HAVING SUM(price) > 100
ORDER BY category
LIMIT 20 OFFSET 0;
~~~

The group count query may need a subquery:

~~~sql
SELECT COUNT(*)
FROM (
  SELECT category
  FROM catalog_product
  WHERE active = TRUE
  GROUP BY category
  HAVING SUM(price) > 100
) grouped;
~~~

This is **illustrative SQL**, not valid JPQL across all providers; some JPQL dialects reject subqueries in `FROM`. When choosing native SQL, verify syntax/`countQuery` and aggregate DTO mapping on the real database.

### 12.3 Null/Consistent Sorting Across Databases

PostgreSQL, MySQL, and H2 can differ on `NULL` sorting, text collations, case folding, diacritics, and timezones. A passing H2 test **does not prove** Vietnamese name sorting on production PostgreSQL behaves identically.

If the UI requires locale-aware name sorting, verify exact DB/collation rules or normalize intentionally. `Sort.Order.ignoreCase()` is not magic guaranteeing identical results across dialects.

### 12.4 Count Distinct and Soft Deletes

With soft deletes:

~~~text
active = true
deleted_at IS NULL
tenant_id = currentTenant
~~~

Content queries, count queries, and aggregate queries must all enforce the **exact same visibility rules**. A missing predicate in the count query can leak deleted or cross-tenant record counts. Seed fixtures spanning at least two tenants plus a soft-deleted row; assert both page metadata and grouped totals.

### 12.5 Aggregates with Negative Values and Empty Sets

In transactional systems with negative refunds, discounts, or null/unknown prices:

- Use `BigDecimal` with precision/scale supporting negative amounts.
- `SUM` returns null when no rows match; decide whether the API expects null or 0 and handle via `COALESCE` or service mapping.
- `COUNT(field)` differs from `COUNT(*)` when fields are nullable.
- If cancelled/voided transactions must be excluded, enforce that filter across **every** count/sum query.
- When no groups match, `GROUP BY` returns an empty list; do not invent a “category=UNKNOWN, total=0” group unless the contract requires it.

### 12.6 Projections Are Not a Complete Security Mechanism

Interface projections trim returned fields, yet do not enforce authorization. If a predicate omits `tenantId` or sensitive columns are included in custom JPQL, the projection still returns unauthorized records. Test security filters and DB row-level rules separately.

### 12.7 Large Offsets and Database Cost

`OFFSET 1_000_000` forces the database to walk past many rows to reach deep pages, especially without a matching index for the sort. Run `EXPLAIN ANALYZE` on a production-like DB and consider keyset/cursor paging. Never blame `Page` slowness on “Java DTO construction” when the real bottleneck is sorting and deep offset scans.

## 13. Measuring Performance Without Confusing It with Correctness

A repository test with 6 rows proves **logic correctness**, saying nothing about performance at 10 million rows. Separate three types of evidence:

| Type | Goal | Tooling |
| --- | --- | --- |
| Correctness | Accurate content/sort/totals | `@DataJpaTest` with boundary data and clear assertions |
| SQL semantics | Accurate queries/counts/joins/dialects on target DB | Testcontainers PostgreSQL/MySQL, SQL logging, execution plans |
| Performance | Latency, memory, count cost, index tuning | Load/performance tests, query plans, metrics/JMH where appropriate |

Especially for aggregate reports, the count query can cost more than the content query. Still, optimize by measuring real workloads—considering pre-aggregated tables, invalidated caches, async reports, or UX designs without totals—**never** by replacing `totalElements` with `content.size()` while keeping the same contract.

### Limitations of `@DataJpaTest` with H2

By default `@DataJpaTest` can replace the datasource with an embedded DB when H2/HSQL/Derby is available. H2 does not fully replicate PostgreSQL/MySQL behavior (JSON columns, arrays, native CTE/window functions, collations, locking).

When a production-like database is needed, use Testcontainers and configure `@ServiceConnection`/`@DynamicPropertySource` for your Boot version, or `@AutoConfigureTestDatabase(replace = NONE)` to prevent test database replacement. **Never point tests at a production database.**

## 14. Common Mistakes

**1. Using page number 1 for the first page out of UI habit.**  
`PageRequest` is 0-based. If the UI is 1-based, convert and validate at the API boundary.

**2. Leaving page size uncapped.**  
`size=10000000` causes memory pressure. Enforce limits/whitelists and return 400 when exceeded.

**3. Sorting only by price when prices can tie.**  
Page boundaries become unstable. Add a unique secondary key like `id`.

**4. Confusing `getNumberOfElements()` with `getTotalElements()`.**  
One is items on the current page; the other is total matching rows.

**5. Using `Slice` while displaying “Page 1 of 120”.**  
Slice lacks `totalPages`. You need `Page` or a different UX.

**6. Using unbounded `List<T>` on multi-million-row tables.**  
Risks OOM/timeouts. Use paging, scrolling, or streaming exports.

**7. Count query missing a filter predicate.**  
For instance, content filters active while count does not; fixtures must include inactive rows to catch this.

**8. Miscounting due to join-to-many.**  
Distinguish SQL row counts from distinct logical entity counts.

**9. Mechanically combining collection fetch join + Pageable.**  
Triggers in-memory paging, row multiplication, or Hibernate errors. Page root IDs first, then fetch details.

**10. Fixtures where every sort key is distinct.**  
Never exposes a missing tie-breaker. Include at least two rows sharing the same price/name/sort key.

**11. Testing only page 0.**  
Misses off-by-one and last-page bugs. Test first, middle, last, and empty pages.

**12. Returning JPA entities directly assuming projections hide sensitive fields.**  
Entities carry lazy relations/proxies; API contracts must explicitly use safe DTOs/projections.

**13. Assuming every interface projection produces optimal SQL.**  
Open projections/SpEL, nested projections, and custom joins can fetch extra fields. Inspect real SQL when performance matters.

**14. Wrong package/constructor in JPQL constructor expressions.**  
Use fully qualified DTO names with matching argument order and types; never put aliases inside constructor arguments.

**15. Writing complex native queries without defining `countQuery`.**  
Automatic count parsing fails on complex SQL; test both totals and dialect behavior.

**16. Summing money with `double`.**  
Introduces binary rounding error; use `BigDecimal` with explicit scale and currency handling.

**17. Expecting `SUM` on an empty set to always return 0.**  
SQL/JPQL typically returns null. Define the contract, handle null explicitly, and test it.

**18. Confusing `COUNT(row)` with `SUM(amount)`.**  
`totalElements=5` does not mean total amount = 5 or group count = 5.

**19. Asserting COUNT SQL runs literally once per call.**  
The framework can optimize counts away. Assert public metadata first; measure SQL in performance tests.

**20. Using H2 to assume sorting/collation/native SQL matches PostgreSQL.**  
Test on a container DB with the target dialect when that behavior matters.

**21. Ignoring mutating data across pages.**  
Offsets can duplicate or skip rows during inserts/deletes; use cursors/snapshots when the contract requires stability.

**22. Overlooking total leakage across visibility/security boundaries.**  
Every count/aggregate must apply the same tenant/auth/soft-delete predicates as the content query.

## 15. Workflow for Designing Pagination/Sort/Projection/Total Tests

1. **Craft fixtures** with sort ties, inactive/soft-deleted rows, multiple categories, and empty cases.
2. **Define the exact predicate** for content queries, e.g., `active=true AND category=:category`.
3. **Choose Page/Slice/List** based on whether the UX needs totals.
4. **Design sorting** with primary order plus a unique tie-breaker.
5. **Define projections** containing only fields required by the contract; use DTO records with JPQL constructors when appropriate.
6. **Define totals**: total matching rows, distinct logical roots, group count, or monetary sum?
7. **Test page 0 and subsequent pages**; assert `getContent`, `getTotalElements`, `getTotalPages`, and `hasNext`/`isLast`.
8. **Test Slice** without relying on total metadata; assert `hasNext` and content.
9. **Test projections** for exact getters/record fields and mapping/serialization over HTTP.
10. **Test aggregates** with finite numeric fixtures, identical predicates, and clear distinction between group counts and sums.
11. **Test empty/invalid inputs**: total 0, empty pages, negative pages, size 0/exceeding max, invalid sort fields.
12. **Test DB-specific cases**: join duplicates, collations, native SQL, transaction isolation, and concurrent writes.
13. **Measure SQL/performance** separately from correctness assertions.
14. **Run CI with rollback/cleanup** so tests never depend on order or leftover state.
15. **Preserve API contracts** without leaking entity internals, cross-tenant data, or mismatched totals.

### Pre-Commit Checklist

- [ ] Query has explicit predicates and the count query preserves the exact same predicates.
- [ ] `PageRequest` uses 0-based page numbers and positive/bounded sizes.
- [ ] Sorting uses valid property/alias names and includes a unique secondary key when stability is required.
- [ ] Tested rows with identical sort keys.
- [ ] Tested first, middle, last, empty pages, and invalid arguments.
- [ ] Distinguished `Page.getTotalElements` from `getNumberOfElements`.
- [ ] `Slice` is not used to claim `totalPages`.
- [ ] Interface projection getters match entity properties and return accurate values.
- [ ] DTO projection constructor expressions/return types align and `countQuery` is accurate.
- [ ] Nested/open projections are not assumed SQL-optimal without verification.
- [ ] Distinct counts are accurate across joins/relationships and grouped results.
- [ ] Totals use `BigDecimal` with clear null/zero/currency conventions.
- [ ] Aggregate filters match business visibility and count filters.
- [ ] `@DataJpaTest` uses intentional fixtures, flush/clear, and proper rollback/cleanup.
- [ ] Critical SQL/native/locale/collation/concurrency behaviors have production-like database tests.
- [ ] HTTP layer returns stable DTO contracts, validates size/sort, and hides private fields.

**Conclusion:** Correct pagination is more than calling `PageRequest.of(...)`. You must verify **accurate content, deterministic ordering, totals matching the exact filters, and consistent boundaries**. Use `Page` for total metadata, `Slice` for next-page navigation, projections for lean data shapes, and `COUNT/SUM/GROUP BY` for business totals. A `@DataJpaTest` suite with ties, inactive rows, multiple groups, and empty pages catches most implementation bugs before they reach the API.

### Official References

- [Spring Data JPA 3.5 — Defining Query Methods: paging, sorting, limiting](https://docs.spring.io/spring-data/jpa/reference/3.5/repositories/query-methods-details.html): `Page`, `Slice`, `List`, `Pageable`, `Sort`, `ScrollPosition`.
- [Spring Data JPA 3.5 — Projections](https://docs.spring.io/spring-data/jpa/reference/3.5/repositories/projections.html): closed/open interface projections, DTO records, dynamic projections, nested join considerations.
- [Spring Data JPA 3.5 — JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/3.5/jpa/query-methods.html): `@Query`, JPQL constructor expressions, custom count queries, native queries, Sort rules.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataJpaTest` slice and test datasources.
- [Spring Data Commons API — Page](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html): `totalElements`, `totalPages`, and Page methods.
- [Spring Data Commons API — Slice](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Slice.html): navigation metadata without total count.
- [Spring Data Commons API — PageRequest](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/PageRequest.html): page index, size, and Sort.