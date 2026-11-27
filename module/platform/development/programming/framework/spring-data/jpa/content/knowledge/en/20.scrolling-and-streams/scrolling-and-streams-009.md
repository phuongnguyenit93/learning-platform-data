# Limiting Results with Top, First, or Limit by Version

## 1. Objectives

Spring Data JPA offers several ways to limit the number of records returned from a Repository. The two keywords `Top` and `First` are placed in derived query method names; `Limit` is a special parameter that lets you pass the maximum count at method invocation time. Which option to pick depends on your Spring Data version and whether sorting, pagination, or dynamic limits are needed.

After this lesson, you will be able to:
- Use `Top` and `First` to limit results directly in method names.
- Understand the default count when no number follows `Top` or `First`.
- Use `Sort` to select the exact K newest, largest, or highest-priority records.
- Use `Limit.of(n)` and `Limit.unlimited()` when supported by the Spring Data version.
- Distinguish total result limits from offset pagination.
- Combine `Top`/`First` with `Pageable`, while recognizing invalid parameter combinations.
- Choose the appropriate return type: `List`, `Optional`, `Page`, or `Slice`.
- Test counts, ordering, and empty-result cases.

## 2. Why Limit Results?

Many use cases only need the first few records:

- Fetching the 5 latest articles to display on the home page.
- Finding the lowest-priced or highest-priced product.
- Fetching a customer's most recent order.
- Finding the first matching record by priority order.
- Displaying up to 10 search suggestions.

Limiting at the Repository layer allows the database to return only the required number of rows. However, limits must accompany a clear sort order. Without `ORDER BY`, the database does not guarantee which records are considered first.

## 3. Using Top and First in Derived Query Names

`Top` and `First` are equivalent keywords for limiting result counts in method names. An integer can be appended immediately after the keyword to specify the maximum count.

```java
List<Article> findTop5ByStatus(ArticleStatus status);

List<Article> findFirst10ByStatus(ArticleStatus status);

Optional<Article> findFirstBySlug(String slug);
```

Meaning:

| Method name | Limit |
| --- | ---: |
| `findTop5ByStatus(...)` | At most 5 results. |
| `findFirst10ByStatus(...)` | At most 10 results. |
| `findFirstBySlug(...)` | Defaults to at most 1 result. |
| `findTopByStatus(...)` | Defaults to at most 1 result. |

If no number follows `Top` or `First`, the default limit is 1. `Top` and `First` are interchangeable; there is no need to place both in the same method name.

### 3.1. Keyword Placement

Limiting keywords sit in the subject portion of the method name, i.e., before `By`:

```java
findTop5ByStatusAndCategory(ArticleStatus status, String category);
```

The `Top5` portion caps results at 5 rows; `StatusAndCategory` creates the filter predicates. They can be combined with other derived query predicates and keywords.

### 3.2. Returning a Single Result

When the limit is one record, you can return the Entity or `Optional<Entity>`. `Optional` clearly represents the not-found case:

```java
Optional<Article> findFirstBySlug(String slug);
```

If no article matches the slug, the Repository returns `Optional.empty()`. If multiple rows match, the method still returns at most one row.

For limits greater than 1, use `List`, `Slice`, or `Page` as needed. Never declare a method capable of returning multiple results as a single Entity unless it has a one-row limit.

## 4. Always Combine Limits with a Stable Order

`Top` or `First` only specifies the maximum count. They do not themselves determine which records come first. Use `OrderBy` in the method name or pass a `Sort`.

### 4.1. Static Sorting with OrderBy

```java
List<Article> findTop5ByStatusOrderByPublishedAtDescIdDesc(ArticleStatus status);

Optional<Article> findFirstByStatusOrderByPublishedAtDescIdDesc(ArticleStatus status);
```

The first query fetches up to 5 articles by status, sorted newest published first. Descending `id` acts as the secondary criterion to break ties when two articles share the same `publishedAt`.

### 4.2. Dynamic Sorting with Sort

If multiple screens need different orderings, accept `Sort` as a parameter:

```java
List<Article> findTop5ByStatus(ArticleStatus status, Sort sort);
```

Calling it:

```java
Sort newestFirst = Sort.by(
        Sort.Order.desc("publishedAt"),
        Sort.Order.desc("id"));

List<Article> newest = repository.findTop5ByStatus(
        ArticleStatus.PUBLISHED, newestFirst);
```

Sort uses the Entity's Java property names, such as `publishedAt`, not database column names like `published_at`.

### 4.3. Why Is a Secondary Criterion Needed?

Suppose 20 articles share the exact same publication timestamp. If sorting only by `publishedAt DESC`, the order among articles with equal timestamps is non-deterministic. When taking Top 5, the database may select different rows across executions.

Add a unique key as the final criterion, such as `id DESC`. This keeps results more stable when data does not change. If data is still being inserted or modified between calls, offset pagination can still shift; for large, rapidly changing streams, consider cursor/keyset scrolling.

## 5. Limit: Dynamic Limiting via Parameter

`org.springframework.data.domain.Limit` is a special parameter type for passing a limit when invoking a Repository instead of hardcoding the number in the method name.

`Limit` was introduced in **Spring Data Commons 3.2**. Therefore, only use this API when the actual Spring Data version in your dependencies supports it. Spring Boot projects should let the Spring Boot BOM manage Spring Data versions consistently; if a project uses Spring Data older than 3.2, use `Top`/`First` or upgrade dependencies according to plan.

Import:

```java
import org.springframework.data.domain.Limit;
```

Creating limits:

```java
Limit five = Limit.of(5);
Limit unlimited = Limit.unlimited();
```

- `Limit.of(5)` requests at most 5 results.
- `Limit.unlimited()` expresses no dynamic limit.
- Do not pass `null` instead of an unlimited Limit; use `Limit.unlimited()`.

### 5.1. Repository Using Limit

```java
List<Article> findByStatus(ArticleStatus status, Limit limit);

List<Article> findByStatus(ArticleStatus status, Sort sort, Limit limit);
```

The second method allows selecting both the order and the limit at call time:

```java
List<Article> recent = repository.findByStatus(
        ArticleStatus.PUBLISHED,
        Sort.by(
                Sort.Order.desc("publishedAt"),
                Sort.Order.desc("id")),
        Limit.of(5));
```

The same method can be invoked with `Limit.of(3)`, `Limit.of(10)`, or `Limit.unlimited()` depending on the use case. This is the key difference from `Top5`, which fixes the number 5 in the method name.

### 5.2. Capping Quantities at the Service Layer

Do not accept an arbitrary count from a client and pass it straight to the database. Enforce a maximum API cap:

```java
package com.example.articles;

import java.util.List;
import org.springframework.data.domain.Limit;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ArticleQueryService {
    private static final int MAX_RESULTS = 50;

    private final ArticleRepository repository;

    public ArticleQueryService(ArticleRepository repository) {
        this.repository = repository;
    }

    public List<Article> findRecent(ArticleStatus status, int requestedLimit) {
        if (requestedLimit < 1 || requestedLimit > MAX_RESULTS) {
            throw new IllegalArgumentException(
                    "Limit must be between 1 and " + MAX_RESULTS);
        }

        Sort sort = Sort.by(
                Sort.Order.desc("publishedAt"),
                Sort.Order.desc("id"));

        return repository.findByStatus(status, sort, Limit.of(requestedLimit));
    }
}
```

The service clearly defines the valid range. In a real API, `IllegalArgumentException` can be translated to an HTTP 400 error via an exception handler. The cap of 50 is purely an illustrative policy; choose a limit fitting your workload and product experience.

## 6. Choosing Top/First or Limit?

| Need | Prefer | Reason |
| --- | --- | --- |
| Always fetch at most 5 records for a fixed use case | `Top5` or `First5` | Intent is visible directly in the method name. |
| Always fetch the first record in a deterministic order | `First` or `Top` without a number | Defaults to limit 1; can return `Optional`. |
| Count varies by request or configuration | `Limit.of(n)` | Pass dynamic count when calling the method. |
| Need the same method with multiple sort orders | `Sort` combined with `Top` or `Limit` | Decouples ordering from filter conditions. |
| Need offset-based pages | `Pageable` | Provides page index, page size, and Sort. |
| Only need to know if more data follows | `Slice` with `Pageable` | Avoids total element count like `Page`. |

`Top`/`First` fits when the limit is a fixed part of the use case. `Limit` fits when the count is a parameter of the use case.

## 7. Combining Top/First with Pageable

`Top` or `First` can be combined with `Pageable`. In that case:

- `Top`/`First` establishes the overall maximum result cap of the query.
- `Pageable` selects a slice within that capped result set and can also provide Sort.

Repository example:

```java
Page<Article> findTop10ByStatus(ArticleStatus status, Pageable pageable);
```

Fetching the first page and next page:

```java
Sort sort = Sort.by(
        Sort.Order.desc("publishedAt"),
        Sort.Order.desc("id"));

Page<Article> firstPage = repository.findTop10ByStatus(
        ArticleStatus.PUBLISHED, PageRequest.of(0, 4, sort));

Page<Article> secondPage = repository.findTop10ByStatus(
        ArticleStatus.PUBLISHED, PageRequest.of(1, 4, sort));
```

The entire query is capped at 10 articles. With page size 4, the first page takes up to the first 4 of those 10, and the second page takes up to the next 4. A third page can fetch the final 2. `Page` metadata is calculated within the capped result scope.

Do not confuse this with `Limit`: `Pageable` already carries limit and offset information. Consequently, `Pageable` and `Limit` cannot be declared on the same method.

## 8. Valid and Invalid Parameter Combinations

Spring Data recognizes `Sort`, `Pageable`, and `Limit` as special parameters. Certain combinations are disallowed because they describe the same aspect of a query.

| Combination | Valid? | Explanation |
| --- | --- | --- |
| `Top`/`First` + `Sort` | Yes | Fixed limit, ordering varies at call time. |
| `Top`/`First` + `Pageable` | Yes | Top sets the total result ceiling; Pageable selects pages within that ceiling. |
| `Sort` + `Limit` | Yes | Chooses dynamic ordering and maximum row count. |
| `Pageable` + `Sort` | No | `Pageable` already includes Sort. |
| `Pageable` + `Limit` | No | `Pageable` already includes row limit and offset. |
| `Top`/`First` + `Limit` | No | Two mechanisms limiting the same query; pick one. |

Each special parameter type should appear at most once in a method signature. APIs accepting `Sort`, `Pageable`, or `Limit` require non-null objects; use `Sort.unsorted()`, `Pageable.unpaged()`, or `Limit.unlimited()` when you do not want to apply that aspect.

## 9. Page, Slice, List, and Optional When Limiting Results

Choose the return type based on what information the caller needs:

| Return type | When appropriate |
| --- | --- |
| `Optional<Article>` | At most one result and you want to express the not-found case. |
| `Article` | At most one result and the app has its own absence policy; watch out for null. |
| `List<Article>` | Need a group of K results without page metadata. |
| `Slice<Article>` | Need to know if a subsequent data chunk exists in a paginated query. |
| `Page<Article>` | Need total element count and total page count within the query scope. |

With `Page`, Spring Data may run a count query to compute metadata. If only the latest few results are needed, `List` is usually simpler and avoids counting. If paging through a result set without needing totals, consider `Slice`.

With `Top10` combined with `Pageable`, total elements and total pages are computed within the cap of 10, not across the entire table.

## 10. Complete Example with Article

The example uses Java 17+, Spring Boot 3.5.x, and Spring Data JPA 3.5.x. `Limit` has been available since Spring Data Commons 3.2, so 3.5.x supports this API.

### 10.1. Enum ArticleStatus

`src/main/java/com/example/articles/ArticleStatus.java`:

```java
package com.example.articles;

public enum ArticleStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}
```

### 10.2. Entity Article

`src/main/java/com/example/articles/Article.java`:

```java
package com.example.articles;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "articles")
public class Article {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 160)
    private String title;

    @Column(nullable = false, unique = true, length = 100)
    private String slug;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ArticleStatus status;

    @Column(name = "published_at")
    private Instant publishedAt;

    protected Article() {
        // JPA requires a no-arg constructor.
    }

    public Article(String title, String slug, ArticleStatus status, Instant publishedAt) {
        if (title == null || title.isBlank() || title.length() > 160) {
            throw new IllegalArgumentException("Title is required");
        }
        if (slug == null || slug.isBlank() || slug.length() > 100) {
            throw new IllegalArgumentException("Slug is required");
        }
        if (status == null) {
            throw new IllegalArgumentException("Status is required");
        }
        this.title = title.trim();
        this.slug = slug.trim();
        this.status = status;
        this.publishedAt = publishedAt;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public String getSlug() { return slug; }
    public ArticleStatus getStatus() { return status; }
    public Instant getPublishedAt() { return publishedAt; }
}
```

### 10.3. ArticleRepository

`src/main/java/com/example/articles/ArticleRepository.java`:

```java
package com.example.articles;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Limit;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ArticleRepository extends JpaRepository<Article, Long> {
    List<Article> findTop5ByStatusOrderByPublishedAtDescIdDesc(ArticleStatus status);

    Optional<Article> findFirstBySlug(String slug);

    List<Article> findTop5ByStatus(ArticleStatus status, Sort sort);

    List<Article> findByStatus(ArticleStatus status, Sort sort, Limit limit);

    Page<Article> findTop10ByStatus(ArticleStatus status, Pageable pageable);
}
```

The first method applies a fixed limit of 5 articles with static sorting. The second returns at most one article by slug. The third accepts dynamic Sort while retaining a cap of 5. The fourth accepts a dynamic Limit. The final method combines a Top 10 cap with pagination.

## 11. Testing Limits and Ordering with H2

The example uses `spring-boot-starter-data-jpa`, H2, and `spring-boot-starter-test`. H2 works for verifying basic derived queries; if your application depends on database-specific syntax or behavior, run additional tests against your production engine.

`src/test/java/com/example/articles/ArticleRepositoryLimitTest.java`:

```java
package com.example.articles;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Limit;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@DataJpaTest
class ArticleRepositoryLimitTest {
    @Autowired
    private ArticleRepository repository;

    private void insertArticles() {
        repository.saveAll(List.of(
                new Article("Article 1", "article-1", ArticleStatus.PUBLISHED, Instant.parse("2026-01-01T00:00:00Z")),
                new Article("Article 2", "article-2", ArticleStatus.PUBLISHED, Instant.parse("2026-01-02T00:00:00Z")),
                new Article("Article 3", "article-3", ArticleStatus.PUBLISHED, Instant.parse("2026-01-03T00:00:00Z")),
                new Article("Article 4", "article-4", ArticleStatus.PUBLISHED, Instant.parse("2026-01-04T00:00:00Z")),
                new Article("Article 5", "article-5", ArticleStatus.PUBLISHED, Instant.parse("2026-01-05T00:00:00Z")),
                new Article("Article 6", "article-6", ArticleStatus.PUBLISHED, Instant.parse("2026-01-06T00:00:00Z")),
                new Article("Draft", "draft", ArticleStatus.DRAFT, null)));
        repository.flush();
    }

    private Sort newestFirst() {
        return Sort.by(
                Sort.Order.desc("publishedAt"),
                Sort.Order.desc("id"));
    }

    @Test
    void topKeywordReturnsOnlyFiveNewestRows() {
        insertArticles();

        List<Article> result = repository.findTop5ByStatusOrderByPublishedAtDescIdDesc(
                ArticleStatus.PUBLISHED);

        assertThat(result).hasSize(5);
        assertThat(result).extracting(Article::getTitle)
                .containsExactly("Article 6", "Article 5", "Article 4", "Article 3", "Article 2");
    }

    @Test
    void limitParameterAppliesDynamicMaximumAndSort() {
        insertArticles();

        List<Article> result = repository.findByStatus(
                ArticleStatus.PUBLISHED, newestFirst(), Limit.of(3));

        assertThat(result).hasSize(3);
        assertThat(result).extracting(Article::getTitle)
                .containsExactly("Article 6", "Article 5", "Article 4");
    }

    @Test
    void firstQueryReturnsOptionalEmptyWhenNoRowMatches() {
        insertArticles();

        Optional<Article> result = repository.findFirstBySlug("missing-slug");

        assertThat(result).isEmpty();
    }

    @Test
    void pageableSelectsAWindowInsideTheTopTenCap() {
        insertArticles();

        Page<Article> page = repository.findTop10ByStatus(
                ArticleStatus.PUBLISHED,
                PageRequest.of(1, 2, newestFirst()));

        assertThat(page.getTotalElements()).isEqualTo(6);
        assertThat(page.getTotalPages()).isEqualTo(3);
        assertThat(page.getNumber()).isEqualTo(1);
        assertThat(page.getContent()).extracting(Article::getTitle)
                .containsExactly("Article 4", "Article 3");
    }
}
```

The first test confirms `Top5` limits and sorts accurately. The second confirms `Limit.of(3)` changes the maximum count at call time. The third confirms `First` returns `Optional.empty()` when no row matches. The last confirms `Pageable` selects the second page within the capped result set.

Run tests from the directory containing `pom.xml`:

```bash
mvn test
```

The expected result is `BUILD SUCCESS` with all four tests passing. This is the expected outcome of the example, not an actual build log.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Wrong first record returned | Using `First`/`Top` without Sort or OrderBy. | Declare explicit ordering and add ID as a secondary criterion. |
| Cannot compile `Limit` import | Spring Data Commons older than 3.2 or dependency overridden. | Inspect dependency tree; use Top/First or upgrade Spring Data consistently. |
| Method reports invalid special parameter | Combining `Pageable` with `Limit`, `Pageable` with `Sort`, or `Top`/`First` with `Limit`. | Pick one limiting mechanism; Pageable already includes Sort and page size. |
| Results exceed expected count | Confusing `Pageable` with total limit or using a method lacking Top/First/Limit. | Check method signature and semantics of each parameter. |
| `Optional` mismatches result type | Method can return more than one result. | Only use Optional when the query is capped at most to one row. |
| API allows fetching too many rows | Client controls unbounded Limit or page size. | Validate quantities and enforce a cap at the Service/API layer. |
| Duplicate or missing records across fetches | Unstable sort or data changing between calls. | Add a unique sort criterion; consider snapshots or keyset scrolling. |
| Null `Limit` passed | Caller fails to pass a valid special parameter. | Use `Limit.of(n)` or `Limit.unlimited()`, never null. |
| Using column name in Sort causes error | Sort resolves against Entity properties. | Use `publishedAt`, not `published_at`. |

## 13. Usage Guidelines

1. Use `Top` or `First` when a fixed limit is a clear part of the use case.
2. Use `Limit.of(n)` when the maximum count must vary by request or configuration and Spring Data Commons is 3.2 or newer.
3. Never combine `Top`/`First` with `Limit`, or `Pageable` with `Limit`.
4. You can combine `Top`/`First` with `Pageable`; Top sets the total cap, Pageable selects a page within that cap.
5. Always specify ordering via `OrderBy` or `Sort`; add ID as the final tie-breaker.
6. Use `Optional` for at-most-one queries, `List` for bounded groups, `Slice` when checking for a next page, and `Page` when totals are needed.
7. Validate client-supplied limits and enforce a reasonable maximum.
8. Use Java property names in Sort, not SQL column names.
9. Test counts, ordering, empty results, and Pageable/Top combinations against your project's actual Spring Data version.

## 14. Completion Checklist

- [ ] Can write `findTop5By...` and `findFirstBy...`.
- [ ] Understand that omitting a number after Top/First defaults to at most one result.
- [ ] Combine Top/First with `OrderBy` and `Sort` for deterministic ordering.
- [ ] Know that `Limit` resides in `org.springframework.data.domain` and was introduced in Spring Data Commons 3.2.
- [ ] Can use `Limit.of(n)` and `Limit.unlimited()`.
- [ ] Distinguish dynamic `Limit` from `Pageable` page index/offset.
- [ ] Recognize invalid parameter combinations.
- [ ] Combine `Top` with `Pageable` when paginating within a capped result set.
- [ ] Choose `Optional`, `List`, `Slice`, or `Page` appropriately.
- [ ] Test result counts and ordering with `@DataJpaTest`.

## 15. References

- [Spring Data Commons — Defining Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Spring Data Commons 3.2 — Limit API](https://docs.spring.io/spring-data/commons/docs/3.2.3/api/org/springframework/data/domain/Limit.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)

Upon completion, you can limit result counts in ways suited to your Spring Data version, establish stable ordering, and choose among fixed limits, dynamic limits, or pagination according to your application's needs.