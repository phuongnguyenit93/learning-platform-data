# Pageable, PageRequest, and the Zero-Based Page Index Convention

## 1. Objectives

Spring Data uses `Pageable` to describe a pagination request: which page to retrieve, how many elements per page, and the sort order. `PageRequest` is the standard implementation used to create a specific pagination request. The most important point when using `PageRequest` is that **the page index starts at 0**.

After this lesson, you will be able to:
- Explain the roles of `Pageable`, `PageRequest`, `Sort`, `Page`, and `Slice`.
- Create pagination requests using `PageRequest.of(page, size)`.
- Calculate offsets accurately and distinguish the first page from the page number displayed in the UI.
- Combine pagination with ascending, descending, and multi-criteria sorting.
- Read `Page` metadata and choose between `Page` and `Slice` according to requirements.
- Validate page/size from HTTP requests to avoid invalid values or overly large queries.
- Test page ordering, content, and metadata.

## 2. What Is Pageable?

`Pageable` is an interface describing a pagination request. It does not hold Entity data; it carries the information the Repository needs to know which slice of data to retrieve.

Key information:

| Member | Meaning |
| --- | --- |
| `getPageNumber()` | Current page index, starting from 0. |
| `getPageSize()` | Maximum number of elements requested in one page. |
| `getOffset()` | Starting position across the entire result set, zero-based. |
| `getSort()` | Sorting rules for the results. |
| `isPaged()` | Indicates whether the request is paged. |
| `next()` / `previousOrFirst()` | Creates a request for the next or previous page; does not mutate the current instance. |

`Pageable` is the abstraction that a Repository accepts. As a result, repository methods do not depend directly on a specific implementation.

## 3. PageRequest and Zero-Based Page Indexing

`PageRequest` is the implementation of `Pageable`, created via static factory methods. The most common usage:

```java
PageRequest firstPage = PageRequest.of(0, 10);
PageRequest secondPage = PageRequest.of(1, 10);
PageRequest thirdPage = PageRequest.of(2, 10);
```

The first parameter is the page index, starting at 0. The second parameter is the page size.

With `size = 10`, the pages have the following positions:

| Passed page index | User-facing page label | Offset | Result positions |
| ---: | ---: | ---: | --- |
| `0` | Page 1 | `0` | 0 to 9 |
| `1` | Page 2 | `10` | 10 to 19 |
| `2` | Page 3 | `20` | 20 to 29 |

Formula:

\[
\text{offset} = \text{page index} \times \text{page size}
\]

For example, `PageRequest.of(2, 10)` requests page index 2, which is the third page in human counting; the offset is 20.

**Convention to remember:** `PageRequest.of(1, 10)` is the second page, not the first page. The first page always has index `0`.

### 3.1. Why Does Spring Data Use Zero-Based Indexing?

Index 0 aligns with indexing in many data structures and APIs in Java. Offsets also start at 0: the first element is at position 0. Therefore, the formula `page * size` directly computes the offset.

### 3.2. When the UI Numbers Pages Starting from 1

Some interfaces display Page 1, Page 2, Page 3 to users. If your API also accepts 1-based page numbers, convert them before creating `PageRequest`:

```java
int pageNumberFromUi = 1;
int pageIndex = pageNumberFromUi - 1;
Pageable pageable = PageRequest.of(pageIndex, 10);
```

In this case, the UI sends `1` to indicate the first page, while Spring Data receives `0`. Define the API contract clearly: whether the `page` parameter starts at 0 or 1. Do not subtract 1 twice, and do not convert if the client already sends a zero-based index.

## 4. Creating a PageRequest

### 4.1. Specifying Page and Size

```java
Pageable pageable = PageRequest.of(0, 20);
```

This request fetches up to the first 20 elements. By default there is no specific sort order (`Sort.unsorted()`). If stable results are needed, specify `Sort` explicitly.

### 4.2. With Sort

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by("title").ascending());
```

Example sorting by title descending:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by("title").descending());
```

### 4.3. Sorting by Multiple Properties

```java
Sort sort = Sort.by(
        Sort.Order.asc("title"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id"));

Pageable pageable = PageRequest.of(0, 20, sort);
```

The database will sort by `title` ascending first. If multiple records share the same title, `createdAt` descending is used next; if still tied, `id` ascending breaks the tie.

**Always add a unique criterion such as `id` as the final criterion** when paginating. If you sort only by an attribute with many duplicate values, the order among tied records is not guaranteed. That can cause records to appear twice or be skipped between page reads, especially when data changes.

### 4.4. Creating Sort First and Passing It to PageRequest

You can reuse a `Sort`:

```java
Sort newestFirst = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"));

Pageable firstPage = PageRequest.of(0, 25, newestFirst);
Pageable nextPage = PageRequest.of(1, 25, newestFirst);
```

`PageRequest` is immutable. Operations such as `next()`, `previousOrFirst()`, `first()`, or `withPage(...)` return a new request; they do not modify the current object.

## 5. Sorting Rules with Sort

`Sort` describes ordering by Entity properties, not physical column names in the database.

Suppose an Entity has:

```java
@Column(name = "created_at")
private Instant createdAt;
```

The property to use in Sort is `createdAt`, even though the database column name is `created_at`:

```java
Sort.by(Sort.Order.desc("createdAt"));
```

Common sorting styles:

```java
Sort ascending = Sort.by("title").ascending();
Sort descending = Sort.by("title").descending();

Sort combined = Sort.by("status").ascending()
        .and(Sort.by("createdAt").descending());
```

### 5.1. Controlling Sort Properties from Requests

Do not pass property names sent by a client directly into `Sort` without validation. Whitelist the fields that the API allows sorting by:

```java
private static final Set<String> ALLOWED_SORT_FIELDS = Set.of(
        "title", "createdAt", "id");

Sort toSort(String requestedField, boolean descending) {
    String field = ALLOWED_SORT_FIELDS.contains(requestedField)
            ? requestedField
            : "createdAt";

    Sort.Order order = descending
            ? Sort.Order.desc(field)
            : Sort.Order.asc(field);

    return Sort.by(order).and(Sort.by(Sort.Order.desc("id")));
}
```

This is an illustrative example; in a real application, place the helper in an appropriate class and handle invalid field names according to the API contract. Whitelisting prevents errors from nonexistent properties and stops clients from requesting sorts on unexposed attributes.

`Sort.NullHandling` can express a preference for where null values appear, but it is a hint to the datastore/provider. If null placement directly affects business logic, verify the behavior on the database in use.

## 6. Page, Slice, and List

A Repository can return different result types when accepting `Pageable`.

| Return Type | Content | Total element/page counts? |
| --- | --- | --- |
| `Page<T>` | Page content and pagination metadata. | Has `getTotalElements()` and `getTotalPages()`. |
| `Slice<T>` | Page content and whether previous/next pages exist. | No total element count or total page count. |
| `List<T>` | Only the list of elements for the requested page. | No pagination metadata. |

### 6.1. Page<T>

`Page<T>` is suitable when the UI needs to show the total result count or total pages, e.g. “1–20 of 243 products”.

Useful methods:

| Method | Meaning |
| --- | --- |
| `getContent()` | List of elements on the current page. |
| `getNumber()` | Current page index, starting from 0. |
| `getSize()` | Requested page size. |
| `getNumberOfElements()` | Actual number of elements on the current page. |
| `getTotalElements()` | Total number of matching elements. |
| `getTotalPages()` | Total number of pages. |
| `hasNext()` | Whether there is a next page. |
| `hasPrevious()` | Whether there is a previous page. |
| `isFirst()` / `isLast()` | Whether the current page is the first/last page. |

For example, if there are 43 results and size is 20, total pages is 3. Page index 2 is the last page, containing only 3 elements.

### 6.2. Slice<T>

`Slice<T>` is suitable when the UI only needs a “Load more” or “Next page” button without knowing the total result count.

```java
Slice<Article> findByPublishedTrue(Pageable pageable);
```

The provider typically fetches one extra element to determine whether a next page exists. `Slice` avoids needing to count total rows like `Page`, so it can save cost on large tables or complex filter conditions.

### 6.3. List<T> with Pageable

```java
List<Article> findByPublishedTrue(Pageable pageable);
```

The result is just the list for the requested page. If the Service needs the page number, total result count, or the `hasNext` flag, choose `Page` or `Slice`.

## 7. Repository Using Pageable

The example below uses an `Article` Entity with title, published status, and creation time.

`src/main/java/com/example/articles/Article.java`:

```java
package com.example.articles;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
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

    @Column(nullable = false)
    private boolean published;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Article() {
        // JPA requires a no-argument constructor.
    }

    public Article(String title, boolean published, Instant createdAt) {
        if (title == null || title.isBlank() || title.length() > 160) {
            throw new IllegalArgumentException("Title is required");
        }
        if (createdAt == null) {
            throw new IllegalArgumentException("Created time is required");
        }
        this.title = title.trim();
        this.published = published;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public boolean isPublished() { return published; }
    public Instant getCreatedAt() { return createdAt; }
}
```

`src/main/java/com/example/articles/ArticleRepository.java`:

```java
package com.example.articles;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ArticleRepository extends JpaRepository<Article, Long> {
    Page<Article> findByPublishedTrue(Pageable pageable);

    Slice<Article> findByTitleContainingIgnoreCase(String keyword, Pageable pageable);
}
```

Spring Data generates the implementation for these methods. `Pageable` carries the page index, size, and Sort; the derived query `findByPublishedTrue` filters published articles.

## 8. Using PageRequest in a Service

A Service can construct `PageRequest`, call the repository, and return the Page:

```java
package com.example.articles;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ArticleQueryService {
    private static final int MAX_PAGE_SIZE = 100;

    private final ArticleRepository repository;

    public ArticleQueryService(ArticleRepository repository) {
        this.repository = repository;
    }

    public Page<Article> findPublished(int page, int size) {
        if (page < 0) {
            throw new IllegalArgumentException("Page index must be zero or greater");
        }
        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("Page size must be between 1 and 100");
        }

        Sort sort = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"));
        Pageable pageable = PageRequest.of(page, size, sort);
        return repository.findByPublishedTrue(pageable);
    }
}
```

The Service validates that the page index is non-negative and caps the size to prevent a single request from asking for hundreds of thousands of records. `PageRequest.of` also validates page index and size; validating in the Service lets you return clear business errors and enforce API limits.

## 9. API Examples: Zero-Based Page and One-Based Page

### 9.1. API Accepting Zero-Based Page

This passes API parameters directly into Spring Data:

```java
package com.example.articles;

import org.springframework.data.domain.Page;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/articles")
public class ArticleController {
    private final ArticleQueryService service;

    public ArticleController(ArticleQueryService service) {
        this.service = service;
    }

    @GetMapping
    public Page<Article> list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return service.findPublished(page, size);
    }
}
```

First request:

```http
GET /api/articles?page=0&size=20
```

Second page request:

```http
GET /api/articles?page=1&size=20
```

### 9.2. API Accepting 1-Based Page Numbers

If the API exposes standard 1-based page numbers, it can accept `pageNumber` starting from 1 and convert it:

```java
public Page<Article> findPublishedByPageNumber(int pageNumber, int size) {
    if (pageNumber < 1) {
        throw new IllegalArgumentException("Page number must be at least 1");
    }
    int pageIndex = pageNumber - 1;
    return findPublished(pageIndex, size);
}
```

For example, `pageNumber = 1` is converted to `pageIndex = 0`. Do not do this if the client already sends a zero-based page index.

In real APIs, name parameters clearly (`page` or `pageNumber`) and document the convention in OpenAPI/API docs. This avoids confusion between page index and display page number.

## 10. PageRequest and Page Navigation

`PageRequest` provides operations to create requests for the next or previous page:

```java
PageRequest current = PageRequest.of(2, 20);

Pageable next = current.next();
Pageable previous = current.previousOrFirst();
Pageable first = current.first();
Pageable samePageWithNewSort = current.withSort(Sort.by("title").ascending());
```

With `current` at page index 2:
- `next()` creates page index 3.
- `previousOrFirst()` creates page index 1.
- `first()` creates page index 0.
- `withSort(...)` keeps page index and size while changing the sort rule.

You can also use `withPage(0)` to create a request for the first page. These methods return a new object; retain the returned value if you want to use it.

## 11. Offset Pagination and Its Limitations

Standard PageRequest uses offset pagination. Given a page index and size, the database fetches data starting at the corresponding offset, typically via `LIMIT` and `OFFSET` or the dialect's equivalent syntax.

For example, `PageRequest.of(3, 25)` has an offset of 75. As the page index grows very large, the database may have to skip many rows before returning the requested page. Thus, offset pagination can become slow on deep pages.

Key points to remember:
- Keep page size bounded.
- Always specify a stable sort and add a unique criterion.
- For screens needing random page jumps and total page counts, offset pagination is usually appropriate.
- For very large data streams that only need sequential loading, consider keyset/scrolling pagination or cursor-based APIs.

Keyset pagination uses the values of the last record on the previous page as a bookmark for the next page, such as `createdAt < lastCreatedAt` or the pair `(createdAt, id)`. This avoids large offsets, though it cannot easily jump directly to an arbitrary page like page 500. Choose based on API experience and data ordering.

## 12. Page, Metadata, and Mapping to DTOs

`Page<T>` can transform content to a DTO type via `map()` while preserving pagination metadata:

```java
public record ArticleSummary(Long id, String title) {
    public static ArticleSummary from(Article article) {
        return new ArticleSummary(article.getId(), article.getTitle());
    }
}

Page<ArticleSummary> summaries = articleRepository
        .findByPublishedTrue(pageable)
        .map(ArticleSummary::from);
```

This lets the API return only the required fields while keeping `getNumber()`, `getSize()`, `getTotalElements()`, and `getTotalPages()`.

Do not rely on the full internal JSON structure of `PageImpl` as a long-term API contract. When a stable response format is needed, create a dedicated DTO:

```java
import java.util.List;

public record PageResponse<T>(
        List<T> content,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean first,
        boolean last) {

    public static <T> PageResponse<T> from(Page<T> page) {
        return new PageResponse<>(
                page.getContent(),
                page.getNumber(),
                page.getSize(),
                page.getTotalElements(),
                page.getTotalPages(),
                page.isFirst(),
                page.isLast());
    }
}
```

## 13. Page and Count Query Cost

When returning `Page<T>`, Spring Data needs the total result count to compute `getTotalElements()` and `getTotalPages()`. For many queries, that requires an additional count query. The framework can optimize and infer the total in certain cases, so do not assume every Page query executes strictly one SQL statement.

On large tables, complex count queries or multi-table joins can be expensive. When the UI only needs to know whether more data exists, use `Slice<T>`:

```java
Slice<Article> findByPublishedTrue(Pageable pageable);
```

`Slice` does not provide the total result count. The provider typically reads one extra row beyond page size to determine `hasNext()`. This is a good choice for “Load more” buttons or infinite scroll.

## 14. Handling Pages Beyond Available Data

Suppose there are 23 articles and page size is 10:

| Page index | Content | `getNumberOfElements()` | `hasNext()` |
| ---: | --- | ---: | --- |
| 0 | Articles 1–10 | 10 | true |
| 1 | Articles 11–20 | 10 | true |
| 2 | Articles 21–23 | 3 | false |
| 3 | No articles | 0 | false |

A page beyond available data normally returns an empty Page rather than automatically snapping back to the last page. An API can choose to return an empty page, return a 404/400 error, or clamp the page to the end; define consistent behavior in the API contract.

Do not use `getSize()` to infer the actual number of elements on the last page. Use `getNumberOfElements()` or `getContent().size()`.

## 15. Testing with H2

The example uses Java 17+, Spring Boot 3.5.0, `spring-boot-starter-data-jpa`, H2, and `spring-boot-starter-test`.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:pagingdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/articles/ArticleRepositoryPagingTest.java`:

```java
package com.example.articles;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

@DataJpaTest
class ArticleRepositoryPagingTest {
    @Autowired
    private ArticleRepository repository;

    @Test
    void pageIndexStartsAtZeroAndReturnsCorrectMetadata() {
        repository.saveAll(List.of(
                new Article("Gamma", true, Instant.parse("2026-01-03T00:00:00Z")),
                new Article("Alpha", true, Instant.parse("2026-01-01T00:00:00Z")),
                new Article("Beta", true, Instant.parse("2026-01-02T00:00:00Z")),
                new Article("Hidden", false, Instant.parse("2026-01-04T00:00:00Z"))));
        repository.flush();

        Page<Article> first = repository.findByPublishedTrue(
                PageRequest.of(0, 2, Sort.by("title").ascending().and(Sort.by("id").ascending())));

        assertThat(first.getNumber()).isZero();
        assertThat(first.getSize()).isEqualTo(2);
        assertThat(first.getNumberOfElements()).isEqualTo(2);
        assertThat(first.getContent()).extracting(Article::getTitle)
                .containsExactly("Alpha", "Beta");
        assertThat(first.getTotalElements()).isEqualTo(3);
        assertThat(first.getTotalPages()).isEqualTo(2);
        assertThat(first.hasNext()).isTrue();

        Page<Article> second = repository.findByPublishedTrue(
                PageRequest.of(1, 2, Sort.by("title").ascending().and(Sort.by("id").ascending())));

        assertThat(second.getNumber()).isEqualTo(1);
        assertThat(second.getNumberOfElements()).isEqualTo(1);
        assertThat(second.getContent()).extracting(Article::getTitle)
                .containsExactly("Gamma");
        assertThat(second.isLast()).isTrue();
        assertThat(second.hasNext()).isFalse();
    }

    @Test
    void sliceExposesWhetherAnotherPageExists() {
        repository.saveAll(List.of(
                new Article("Alpha", true, Instant.parse("2026-01-01T00:00:00Z")),
                new Article("Beta", true, Instant.parse("2026-01-02T00:00:00Z")),
                new Article("Gamma", true, Instant.parse("2026-01-03T00:00:00Z"))));
        repository.flush();

        Slice<Article> slice = repository.findByTitleContainingIgnoreCase(
                "a", PageRequest.of(0, 2, Sort.by("title").ascending()));

        assertThat(slice.getContent()).hasSize(2);
        assertThat(slice.hasNext()).isTrue();
    }
}
```

Run tests from the directory containing `pom.xml`:

```bash
mvn test
```

The expected result is Maven finishing with `BUILD SUCCESS`. The first test confirms index 0 is the first page, index 1 is the second page, Sort is applied, and total metadata is calculated accurately. The second test checks `Slice.hasNext()`. This is the expected outcome of the example; no actual build log is shown.

## 16. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| First page is skipped | Passing `page=1` directly to `PageRequest.of` while client numbers from 1. | Subtract `pageNumber - 1` exactly once or standardize on a zero-based API. |
| `PageRequest` throws `IllegalArgumentException` | Negative page index or non-positive page size. | Validate input before creating the request. |
| Pages have duplicate or missing results between reads | Unstable sort or data changes during pagination. | Add a unique criterion such as `id`; consider snapshots/cursors for volatile data. |
| Incorrect sort order | Using database column name instead of Entity property name. | Use Java property like `createdAt`, not `created_at`. |
| API returns too much data | Client can request a huge page size. | Enforce a maximum limit in Controller/Service. |
| `Page` is slower than expected | Count query can be expensive. | Use `Slice` if total count is not needed; optimize query/count query. |
| Last page has fewer elements than page size | Total results are not evenly divisible by page size. | Use `getNumberOfElements()` to read the actual element count. |
| Page beyond data returns empty | Page index is greater than the last page. | Define clearly whether the API returns empty, an error, or clamps to the last page. |
| Sort field causes error | Client sends nonexistent or disallowed property. | Whitelist sort fields and provide a default sort. |

## 17. Project Usage Principles

1. Remember `PageRequest.of(page, size)` uses a zero-based page index; index `0` is the first page.
2. Document whether page starts at 0 or 1 in the API contract and convert only once.
3. Validate that page is non-negative and size is within reasonable bounds before creating PageRequest.
4. Always specify a stable sort; add ID as a secondary criterion when primary attributes may tie.
5. Use Entity Java property names when creating `Sort`, not physical column names.
6. Use `Page` when total counts are needed; `Slice` when only checking if more data exists; `List` when metadata is unnecessary.
7. Do not rely on `getSize()` to determine the actual element count on the last page.
8. Consider keyset/cursor pagination when offsets are large or data changes continuously.
9. Do not expose `PageImpl`'s internal structure directly as a long-term API contract; use a response DTO when a stable format is needed.
10. Test the first page, next page, last page, empty page, Sort, and metadata.

## 18. Completion Checklist

- [ ] Can explain `Pageable` and `PageRequest`.
- [ ] Can create `PageRequest.of(0, size)` for the first page.
- [ ] Can calculate offset as `page index * page size`.
- [ ] Can convert accurately between 1-based page numbers and 0-based page indexes.
- [ ] Can combine `PageRequest` with single- or multi-property `Sort`.
- [ ] Understand why a unique secondary sort criterion is needed.
- [ ] Can read metadata from `Page` and `Slice`.
- [ ] Can choose the right type among `Page`, `Slice`, or `List` for each need.
- [ ] Enforce page size limits and whitelist sort fields from APIs.
- [ ] Can run integration tests for page content, ordering, and metadata.

Once complete, you can build Spring Data JPA pagination APIs with proper zero-based indexing, stable sorting, and metadata tailored to the user experience.