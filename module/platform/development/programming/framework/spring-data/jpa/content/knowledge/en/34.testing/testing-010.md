# Testing Page, Count Queries, Projections, and Empty Result Cases

## 1. Goals of Paginated Query Testing

Spring Data JPA provides several return types for repository queries. When a method accepts `Pageable`, the application can request paged data, limit row counts, sort results, and sometimes fetch total counts.

A good pagination test simultaneously verifies:

- Page content matches filter conditions and sort order.
- Page number, page size, and actual number of elements on the page are accurate.
- `totalElements` and `totalPages` accurately reflect matching rows.
- The count query counts the exact dataset represented by the content query.
- Projections map fields and data types properly.
- Zero-match cases and out-of-range page requests are clearly distinguished.

Checking only `page.getContent()` is insufficient. A page can contain the right two records while `totalElements` is wrong due to a buggy count query; conversely, the count can be right while unstable sorting makes tests flaky.

Examples below use Spring Data JPA with Hibernate, JUnit 5, and AssertJ. Package names are illustrative; in your project, substitute your actual entity and DTO packages.

## 2. How Do Page, Pageable, and Slice Differ?

Three common return shapes:

| Type | Content | Total Count Metadata | How Next Page Is Determined |
|---|---|---|---|
| `Page<T>` | Elements of the current page | Includes `totalElements` and `totalPages` | Derived from total result count |
| `Slice<T>` | Elements of the current slice | No total count across all pages | Typically fetches one extra element to check for a next slice |
| `List<T>` with `Pageable` | List bounded by `Pageable` | No page metadata | Application decides |

`Page<T>` is useful when the UI needs to show “page 2 of 8” or total match counts. To supply this metadata, Spring Data often needs an additional count query. However, Spring Data can infer the total from page content in certain cases and skip calling the count supplier—for example, when the first page has fewer elements than the page size. Therefore, not every `Page` call guarantees executing a `COUNT` SQL statement.

`Slice<T>` fits cases where you only need to know if more data can be loaded. It avoids computing total counts, often reducing cost on large datasets. `List<T>` paired with `Pageable` can also limit results without total metadata.

Page numbers in `PageRequest` are zero-based. For instance, `PageRequest.of(0, 10)` requests the first 10 items; `PageRequest.of(1, 10)` requests the second page.

## 3. Preparing the Sample Entity and Repository

Suppose an application manages `Product` with name, category, SKU, and price:

~~~java
package com.example.catalog;

import java.math.BigDecimal;

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

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private String category;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Product() {
    }

    public Product(String name, String category, String sku, BigDecimal price) {
        this.name = name;
        this.category = category;
        this.sku = sku;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public String getSku() {
        return sku;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

An interface projection selecting a subset of properties:

~~~java
package com.example.catalog;

import java.math.BigDecimal;

public interface ProductSummary {
    String getName();

    String getSku();

    BigDecimal getPrice();
}
~~~

A record DTO for constructor projection:

~~~java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductRow(String name, String sku, BigDecimal price) {
}
~~~

The repository provides entity queries, queries with explicit `countQuery`, and projections:

~~~java
package com.example.catalog;

import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends JpaRepository<Product, Long> {
    Page<Product> findByCategory(String category, Pageable pageable);

    @Query(
        value = """
            select p
            from Product p
            where p.category = :category
            """,
        countQuery = """
            select count(p)
            from Product p
            where p.category = :category
            """
    )
    Page<Product> searchByCategory(
        @Param("category") String category,
        Pageable pageable
    );

    Page<ProductSummary> findProjectedByCategory(
        String category,
        Pageable pageable
    );

    @Query(
        value = """
            select new com.example.catalog.ProductRow(
                p.name, p.sku, p.price
            )
            from Product p
            where p.category = :category
            """,
        countQuery = """
            select count(p)
            from Product p
            where p.category = :category
            """
    )
    Page<ProductRow> findRowsByCategory(
        @Param("category") String category,
        Pageable pageable
    );

    List<Product> findAllByCategory(String category);
}
~~~

The example assumes all classes live in the declared packages and the database schema has matching columns. For JPQL constructor expressions, the DTO class name must be fully qualified and constructor parameter order and types must match the `SELECT` expressions.

## 4. Testing Page Content and Metadata

A `@DataJpaTest` test can inject `ProductRepository` and `TestEntityManager`. `TestEntityManager` prepares entities, flushes SQL, and clears the persistence context.

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@DataJpaTest
class ProductRepositoryPageTest {
    @Autowired
    private ProductRepository products;

    @Autowired
    private TestEntityManager entityManager;

    private void insertProducts() {
        entityManager.persist(new Product(
            "A Book", "BOOK", "B-01", new BigDecimal("10.00")
        ));
        entityManager.persist(new Product(
            "B Book", "BOOK", "B-02", new BigDecimal("20.00")
        ));
        entityManager.persist(new Product(
            "C Book", "BOOK", "B-03", new BigDecimal("30.00")
        ));
        entityManager.persist(new Product(
            "D Book", "BOOK", "B-04", new BigDecimal("40.00")
        ));
        entityManager.persist(new Product(
            "E Book", "BOOK", "B-05", new BigDecimal("50.00")
        ));
        entityManager.persist(new Product(
            "Pen", "STATIONERY", "P-01", new BigDecimal("2.00")
        ));

        entityManager.flush();
        entityManager.clear();
    }

    @Test
    void returnsExpectedContentAndPageMetadata() {
        insertProducts();

        Sort sort = Sort.by("name").ascending()
            .and(Sort.by("id").ascending());
        Page<Product> page = products.searchByCategory(
            "BOOK",
            PageRequest.of(0, 2, sort)
        );

        assertThat(page.getContent())
            .extracting(Product::getName)
            .containsExactly("A Book", "B Book");

        assertThat(page.getNumber()).isZero();
        assertThat(page.getSize()).isEqualTo(2);
        assertThat(page.getNumberOfElements()).isEqualTo(2);
        assertThat(page.getTotalElements()).isEqualTo(5);
        assertThat(page.getTotalPages()).isEqualTo(3);
        assertThat(page.isFirst()).isTrue();
        assertThat(page.hasNext()).isTrue();
        assertThat(page.hasPrevious()).isFalse();
    }
}
~~~

In this example, page size is 2 and there are 5 `BOOK` products. The first page holds two elements, total elements is 5, and total pages is 3.

The assertions verify different aspects:

- `getContent()` checks the exact entities on the page.
- `getNumber()` checks the zero-based page index.
- `getSize()` is the requested page size.
- `getNumberOfElements()` is the actual count on the current page; the last page may have fewer than page size.
- `getTotalElements()` is the total matching rows across all pages.
- `getTotalPages()` is the total number of pages computed from total rows and page size.
- `hasNext()`, `hasPrevious()`, and `isFirst()` check navigation flags.

Use deterministic ordering when paginating. If sorting only by `name` and multiple rows share a name, ordering among ties can shift. Adding a unique key like `id` as a tie-breaker stabilizes tests and prevents items from appearing on two pages or being skipped across requests.

## 5. Testing Count Queries

### 5.1. What Does the Count Query Do?

With `Page<T>`, besides the query fetching page content, Spring Data can execute a count query to calculate `totalElements`. Example:

~~~sql
select p
from Product p
where p.category = :category
order by p.name
~~~

Corresponding count query:

~~~sql
select count(p)
from Product p
where p.category = :category
~~~

The count query must count the exact set of rows represented by the content query. Filter predicates must match; the count query does not need `ORDER BY` since ordering does not affect totals.

When using `@Query` for paginated queries, an explicit `countQuery` can be declared. This keeps intent clear when the main query is complex or Spring Data cannot safely derive a count query automatically.

### 5.2. Common Count Query Bugs

1. **Missing filter predicates:** content query filters by category and active status, while the count query filters only by category. `totalElements` ends up higher than reality.
2. **JOIN multiplying rows:** one `Product` has multiple related child rows. `COUNT(p)` after a join can count the same `Product` repeatedly. When counting root entities, `count(distinct p.id)` may be needed.
3. **Wrong count granularity with DISTINCT or GROUP BY:** the main query returns grouped or distinct results, while the count query counts source rows. Define the exact unit being counted.
4. **Using FETCH JOIN in count queries:** count queries generally must not contain fetch joins because their only purpose is counting. Write a separate count query.
5. **Complex native SQL:** Spring Data cannot always parse complex SQL to generate an accurate count query. Declare `countQuery` explicitly.
6. **Count query returning wrong totals due to secondary filters:** if queries enforce tenant, soft-delete, authorization, or specification filters, the count must apply the exact same business filters.

Example when a join query can produce multiple rows for the same `Product`:

~~~java
@Query(
    value = """
        select distinct p
        from Product p
        join p.tags t
        where t.name in :tagNames
        """,
    countQuery = """
        select count(distinct p.id)
        from Product p
        join p.tags t
        where t.name in :tagNames
        """
)
Page<Product> findByAnyTag(
    @Param("tagNames") List<String> tagNames,
    Pageable pageable
);
~~~

This example assumes `Product` has a `tags` relationship and `Tag` has a `name` property. If business rules require products having *all* tags rather than *any* tag, both content and count queries must be redesigned with matching semantics.

### 5.3. Testing Totals With a Custom countQuery

In the earlier test, the first page had two items and page size was two. Spring Data needs to determine whether more data exists on subsequent pages and can invoke the count supplier to complete metadata. Asserting `totalElements` equals 5 verifies the total provided by `Page`.

You can also test the second page:

~~~java
@Test
void returnsSecondPageWithCorrectTotal() {
    insertProducts();

    Page<Product> page = products.searchByCategory(
        "BOOK",
        PageRequest.of(
            1,
            2,
            Sort.by("name").ascending().and(Sort.by("id").ascending())
        )
    );

    assertThat(page.getContent())
        .extracting(Product::getName)
        .containsExactly("C Book", "D Book");

    assertThat(page.getNumber()).isEqualTo(1);
    assertThat(page.getNumberOfElements()).isEqualTo(2);
    assertThat(page.getTotalElements()).isEqualTo(5);
    assertThat(page.getTotalPages()).isEqualTo(3);
    assertThat(page.hasPrevious()).isTrue();
    assertThat(page.hasNext()).isTrue();
}
~~~

If you need to prove the exact `COUNT` SQL statement executed, asserting `totalElements` alone may not suffice in every case because Spring Data can infer totals from page content. Use SQL logging, Hibernate Statistics, or a datasource proxy to observe executed SQL and statement counts. On full pages like the example, the count supplier typically needs to run; however, framework optimizations still depend on page shape and version.

### 5.4. Native Queries and countQuery

With native SQL, declaring an explicit `countQuery` is particularly helpful:

~~~java
@Query(
    value = """
        select p.*
        from products p
        where p.category = :category
        order by p.name
        """,
    countQuery = """
        select count(*)
        from products p
        where p.category = :category
        """,
    nativeQuery = true
)
Page<Product> findNativePage(
    @Param("category") String category,
    Pageable pageable
);
~~~

Table and column names must match the real schema. Applying `Sort` from `Pageable` onto native queries has limitations depending on the Spring Data version and SQL parsing support. For complex native queries, write an explicit `ORDER BY` or test carefully how the framework appends pagination and sorting.

## 6. Testing Interface Projections

Projections allow repositories to return only needed attributes rather than loading entire entities. Interface projections typically declare getters matching entity property names.

Example `ProductSummary`:

~~~java
public interface ProductSummary {
    String getName();

    String getSku();

    BigDecimal getPrice();
}
~~~

Repository method:

~~~java
Page<ProductSummary> findProjectedByCategory(
    String category,
    Pageable pageable
);
~~~

Test:

~~~java
@Test
void returnsInterfaceProjectionForRequestedPage() {
    insertProducts();

    Page<ProductSummary> page = products.findProjectedByCategory(
        "BOOK",
        PageRequest.of(0, 2, Sort.by("name").ascending())
    );

    assertThat(page.getContent()).hasSize(2);
    assertThat(page.getContent())
        .extracting(ProductSummary::getName)
        .containsExactly("A Book", "B Book");
    assertThat(page.getContent())
        .extracting(ProductSummary::getSku)
        .containsExactly("B-01", "B-02");
    assertThat(page.getTotalElements()).isEqualTo(5);
}
~~~

Things to verify:

- Getters match the property names the projection needs to read.
- Return types are compatible with entity property types.
- The projection includes only fields needed by the use case.
- `Page` metadata stays accurate; projections do not eliminate count query requirements.
- Sorting uses valid properties and yields a stable order.

Interface projections can be backed by Spring Data proxies. With nested projections or open projections using SpEL, actual SQL may fetch additional columns or map differently. Do not assume a projection always selects only the getter columns without observing the real SQL.

## 7. Testing DTO/Class-Based Projections

DTO projections return a concrete data type instead of a proxy interface. With JPQL, constructor expressions can be used:

~~~java
select new com.example.catalog.ProductRow(
    p.name, p.sku, p.price
)
from Product p
where p.category = :category
~~~

The constructor or record canonical constructor must match the `SELECT` expressions in parameter order and types. If the class name or constructor signature is wrong, query execution fails.

Test:

~~~java
@Test
void returnsDtoProjectionAndCorrectCount() {
    insertProducts();

    Page<ProductRow> page = products.findRowsByCategory(
        "BOOK",
        PageRequest.of(0, 2, Sort.by("name").ascending())
    );

    assertThat(page.getContent()).hasSize(2);
    assertThat(page.getContent())
        .extracting(ProductRow::name)
        .containsExactly("A Book", "B Book");
    assertThat(page.getContent())
        .extracting(ProductRow::sku)
        .containsExactly("B-01", "B-02");
    assertThat(page.getTotalElements()).isEqualTo(5);
}
~~~

DTO tests must verify both per-field values and page metadata. A DTO could receive the right names yet swap `price`/`sku` if constructor expressions mismatch; per-field assertions catch that bug.

For native queries, DTO mapping may require constructor result mappings or interface projections with matching column aliases. Do not assume JPQL constructor expressions work verbatim in every native query.

## 8. Testing Empty Result Cases

Two scenarios are easily confused:

1. No records satisfy the filter condition.
2. Matching records exist, but the requested page falls beyond the available range.

Both return empty content, yet `totalElements` differs.

~~~java
@Test
void distinguishesNoMatchesFromOutOfRangePage() {
    insertProducts();

    Page<Product> noMatches = products.searchByCategory(
        "TOY",
        PageRequest.of(0, 2)
    );

    assertThat(noMatches.getContent()).isEmpty();
    assertThat(noMatches.getTotalElements()).isZero();
    assertThat(noMatches.getTotalPages()).isZero();
    assertThat(noMatches.hasNext()).isFalse();

    Page<Product> outOfRange = products.searchByCategory(
        "BOOK",
        PageRequest.of(3, 2)
    );

    assertThat(outOfRange.getContent()).isEmpty();
    assertThat(outOfRange.getTotalElements()).isEqualTo(5);
    assertThat(outOfRange.getTotalPages()).isEqualTo(3);
    assertThat(outOfRange.hasNext()).isFalse();
}
~~~

In the example, 5 `BOOK` products with page size 2 yield 3 valid pages with indexes 0, 1, and 2. Requesting page 3 is out of range. Content is empty, yet `totalElements` remains 5 when the count query is accurate.

When no records match, a `Page` normally has empty content, `totalElements` equal to 0, and `totalPages` equal to 0. That is normal behavior, not a repository error.

### 8.1. List, Optional, and Projections When No Rows Match

Other return types have distinct semantics:

- Repository methods returning `List<T>` usually return an empty list when no rows match, not `null`.
- Methods returning `Optional<T>` explicitly model presence or absence of a single result.
- Methods returning a single entity directly may return `null` when not found, depending on method kind.
- Projected `Page` or `Slice` results can likewise have empty content and corresponding metadata.
- DTO projections must also be tested for zero-match inputs, not only populated cases.

Example testing `List` and `Optional`:

~~~java
@Test
void returnsEmptyCollectionAndOptionalWhenNoProductMatches() {
    insertProducts();

    assertThat(products.findAllByCategory("TOY")).isEmpty();
    assertThat(products.findBySku("UNKNOWN")).isEmpty();
}
~~~

This test assumes the repository declares `findBySku(String sku)` returning `Optional<Product>`. You can add the following declaration to `ProductRepository`:

~~~java
import java.util.Optional;

Optional<Product> findBySku(String sku);
~~~

Avoid single assertions like checking only that a result is non-null. For collections, assert empty; for `Optional`, assert `isEmpty`; for `Page`, assert both content and metadata.

### 8.2. Out-of-Range Case: Requesting a Page Beyond Bounds

An `out-of-range` request occurs when matching data exists, yet `PageRequest` asks for a page past the final page. For instance, with 5 matching products and page size 2, `totalPages` is 3 with valid page indexes 0, 1, and 2. Calling `PageRequest.of(3, 2)` must return an empty `Page.getContent()`, while `totalElements` stays 5, `totalPages` stays 3, and `hasNext()` is `false`. This differs from zero-match queries where both `totalElements` and `totalPages` equal 0.

You can add this assertion to the repository test seeded with 5 `BOOK` products:

~~~java
Page<Product> beyondLastPage = products.searchByCategory(
    "BOOK",
    PageRequest.of(3, 2, Sort.by("name").ascending().and(Sort.by("id").ascending()))
);

assertThat(beyondLastPage.getContent()).isEmpty();
assertThat(beyondLastPage.getTotalElements()).isEqualTo(5);
assertThat(beyondLastPage.getTotalPages()).isEqualTo(3);
assertThat(beyondLastPage.getNumber()).isEqualTo(3);
assertThat(beyondLastPage.hasNext()).isFalse();
~~~

When total metadata is needed for an empty out-of-range page, Spring Data may have to call the count supplier to determine total rows. Inspect the count query alongside the assertions above to accurately distinguish `out-of-range` from zero matches.

### 8.3. Using Testcontainers to Verify Production Database Semantics

`Testcontainers` is an optional integration testing choice when embedded databases like H2 do not fully capture production database behavior. You can run the exact same repository tests on a real engine such as PostgreSQL or MySQL to verify native SQL, data types, pagination, custom `countQuery`, interface projections, and DTO projections.

With Spring Boot 3.1+, containers can be declared with `@Container` and `@ServiceConnection`; on older versions, use `@DynamicPropertySource` to provide the JDBC URL, username, and password. To preserve the container-provided `DataSource`, configure `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)`. Re-running `Page`, count query, and projection tests against a container reveals dialect/driver differences that embedded databases can miss. Testcontainers is a complementary path for production parity, not mandatory for every repository slice test.

## 9. Testing Sort and Cross-Page Stability

Offset/page-number pagination can yield unpredictable results when ordering is non-deterministic. When multiple rows share the same sort value, databases do not guarantee ordering among them without a unique secondary key.

Example:

~~~java
PageRequest.of(
    0,
    2,
    Sort.by("name").ascending()
        .and(Sort.by("id").ascending())
);
~~~

When testing:

- Choose distinct sort values if testing basic ordering only.
- Or add `id` as a tie-breaker when names can collide.
- Check both the first page and the next page to catch duplicate or skipped items.
- Use Java entity property names in `Sort`, not SQL column names when `@Column` renames them.
- Test both `ASC`/`DESC` directions and multi-property sorting if supported by the repository.

Example verifying consecutive pages do not repeat products:

~~~java
@Test
void consecutivePagesContainDifferentProductsInStableOrder() {
    insertProducts();

    Sort sort = Sort.by("name").ascending()
        .and(Sort.by("id").ascending());

    Page<Product> first = products.findByCategory(
        "BOOK", PageRequest.of(0, 2, sort)
    );
    Page<Product> second = products.findByCategory(
        "BOOK", PageRequest.of(1, 2, sort)
    );

    assertThat(first.getContent())
        .extracting(Product::getSku)
        .containsExactly("B-01", "B-02");

    assertThat(second.getContent())
        .extracting(Product::getSku)
        .containsExactly("B-03", "B-04");
}
~~~

Offset pagination can still shift rows if records are inserted or deleted between user requests. For large or rapidly changing datasets, consider keyset/scrolling pagination supported by your Spring Data version. Keyset tests must verify cursors, unique ordering, and page boundaries; `Page.totalElements` assertions cannot substitute because keyset pagination targets a different read model.

## 10. Flush, Clear, and Transactions in Repository Tests

`@DataJpaTest` normally runs each test method inside a transaction that rolls back at the end. This provides a convenient environment to seed data and run queries without polluting the test database.

However, the persistence context contains a first-level cache. If a test persists entities and queries immediately, Hibernate may return managed instances or defer SQL differently than expected. To verify real database queries, flush and clear:

- `flush()`: forces pending changes to synchronize down to the database.
- `clear()`: detaches all managed entities, avoiding returning cached instances from L1.
- Subsequent repository queries execute reads under real transaction and cache semantics.

Example:

~~~java
entityManager.persist(new Product(
    "A Book", "BOOK", "B-01", new BigDecimal("10.00")
));
entityManager.flush();
entityManager.clear();

Page<Product> page = products.findByCategory(
    "BOOK", PageRequest.of(0, 10)
);
~~~

Flush does not commit. The test transaction still rolls back when finished unless `@Commit` or `@Rollback(false)` overrides it.

To inspect count queries, observe SQL via Hibernate SQL logging, Statistics, or a datasource proxy. Do not infer SQL query counts from the number of repository method calls.

## 11. Inspecting Real SQL and Count Queries

You can enable Hibernate statistics in test configuration:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Or set properties on the test annotation:

~~~java
@DataJpaTest(properties = {
    "spring.jpa.properties.hibernate.generate_statistics=true"
})
class ProductRepositoryPageTest {
}
~~~

To observe queries, enable SQL logging compatible with your Hibernate version:

~~~properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
~~~

If viewing bind parameters, logger names and packages differ between Hibernate 5 and Hibernate 6; verify against your version. Do not enable bind parameter logging in environments handling sensitive data.

When verifying `Page` queries, look for two SQL patterns:

1. `SELECT` fetching page content with `LIMIT`/`OFFSET` or the database's pagination syntax.
2. `SELECT COUNT(...)` computing total rows matching the filter.

In some cases, the framework may skip `COUNT` by deriving the total from page content. When testing a custom `countQuery`, design data and page requests that trigger counting, then inspect logs/metrics. Keep `totalElements` assertions in the test to validate metadata as well.

## 12. Common Pitfalls Testing Page, Count, and Projections

| Symptom | Common Cause | Resolution |
|---|---|---|
| Content is right but `totalElements` is wrong | Count query misses filters or double-counts via `JOIN` | Write a matching `countQuery`; consider `count(distinct p.id)` |
| Last page has fewer items than page size | Not a bug; expected behavior | Assert `numberOfElements` based on data, not necessarily equal to `size` |
| Out-of-range page has empty content | Page index exceeds total pages | Inspect `totalElements` and `totalPages` to distinguish from no matches |
| Results reorder across runs | Sort lacks a unique tie-breaker | Add `id` or another unique key as tie-breaker |
| Projection getter returns null | Getter name mismatches property or native alias is wrong | Verify mappings, aliases, and data types |
| DTO query fails constructor lookup | Fully qualified class name or parameter order/types mismatch | Align constructor expression with record/class signature |
| Native `Page` query errors or miscounts | Framework cannot parse complex SQL for count | Declare an explicit `countQuery` |
| No `COUNT` SQL observed | Spring Data optimizes and infers total from content | Use page requests/data requiring count; inspect SQL/metrics |
| Test does not emit expected `SELECT` SQL | Entities remain in persistence context or cache | Flush/clear and control caching |
| Test passes on H2 but fails in production | Dialect, native SQL, data type, or pagination differences | Run integration tests on the production database engine |

## 13. Checklist for Reliable Paginated Repository Tests

Before finalizing tests, confirm:

1. Seeded data has enough rows and distinct values to span multiple pages.
2. `Pageable` has explicit page index, page size, and sort criteria.
3. Sort order is deterministic, ideally with a unique key tie-breaker.
4. Assertions check `content`, `number`, `size`, `numberOfElements`, `totalElements`, and `totalPages`.
5. Custom `@Query` declarations include matching `countQuery` where needed; counts do not duplicate across joins.
6. Projection tests check every required field alongside `Page` metadata.
7. Zero-match cases are distinguished from out-of-range pages.
8. Data is flushed/cleared when confirming database query execution.
9. `COUNT` SQL is observed when the test specifically verifies count execution.
10. Native queries and engine-specific behavior are tested on a production-compatible database.

Testing `Page`, count queries, projections, and empty results requires verifying both returned rows and Spring Data's constructed metadata. By thoroughly testing count semantics, projection mappings, deterministic sorting, and edge cases, repository tests catch defects that asserting content lists alone can never expose.