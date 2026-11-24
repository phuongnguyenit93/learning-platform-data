# Pagination, Sorting, Filtering, and List Result Contracts in Spring MVC

## 1. Problem: What Must a List Endpoint Guarantee?

Suppose a client calls a book listing API:

~~~http
GET /api/books?page=0&size=2&sort=createdAt,desc&category=spring&available=true HTTP/1.1
Accept: application/json
~~~

A sound design must simultaneously answer:
- **Filtering:** which records qualify to appear, how matching works, and how absent or blank parameters are interpreted?
- **Sorting:** which records come first, is there a default order, and is there a final tie-breaker key so the order is deterministic?
- **Pagination:** which page index the client requests, maximum items per page, whether the first page is 0- or 1-based, and whether a next page exists?
- **List response contract:** what JSON shape do data, metadata, total elements, navigation hints, and errors take, and does it remain stable across versions?
- **Resource bounds:** what is the maximum size; what limits deep offsets, empty lists, and total-count costs?
- **Consistency:** at what point in time are the total count and page contents observed; how do data changes between requests shift pages?

In Spring MVC, `@RestController` and `@RequestParam` handle **receiving HTTP input and producing the HTTP response**; Spring Data (when present) supports `Pageable`/`Sort`/`Page` and repository queries. **Plain Spring MVC does not automatically query a database or define the entire list JSON structure.** The contract is an API decision that must be defined and tested.

Lesson examples use Java 17+, Spring Boot 3.x / Spring Framework 6.x. There is a runnable **database-independent** application to clearly isolate the HTTP contract; later sections show how to wire Spring Data JPA and address issues at very large data volumes.

## 2. Designing the URL Before Writing the Controller

### 2.1. A Transparent Query Contract

Chosen endpoint:

~~~text
GET /api/books
  ?page=0
  &size=20
  &sort=createdAt,desc
  &category=spring
  &available=true
  &q=security
~~~

Formal definition for the example:

| Parameter | Type | Default/meaning | Bounds or rules |
| --- | --- | --- | --- |
| `page` | integer | `0`, **zero-based** | Non-negative |
| `size` | integer | `20` | From 1 to 50 |
| `sort` | string `field,direction` | `createdAt,desc` | `field ∈ {id,title,createdAt}`, `direction ∈ {asc,desc}` |
| `category` | optional string | No filter | Case-insensitive, full-value match |
| `available` | optional boolean | No filter | `true` or `false` per converter |
| `q` | optional string | No filter | Substring in `title`, case-insensitive |

This is an **application-defined contract**. Do not blindly assume "default size 20" or the sort format above applies to every Spring application: Spring Data web configuration and `@PageableDefault` annotations may differ.

In a URL, peer parameters typically combine using **AND** logic: e.g., `category=spring&available=true` fetches only books that are both in `spring` and currently `available`. For search `q`, explicitly document which attributes are searched; do not let clients assume `q` searches every field if the server only searches titles.

Input parameters belong in the **query string**, not a JSON request body. Listing does not need `POST` just for simple filters; for very complex filters and large payloads, a dedicated search endpoint can be defined, but it requires a clear HTTP/cache contract.

### 2.2. Avoiding Ambiguity: 0-Based or 1-Based Index?

With zero-based:
- `page=0` is the first page.
- `page=1` is the second page.
- `size=2` is at most two items per page.
- In offset pagination, the starting position is `page × size`, e.g., `page=2&size=10` starts at offset 20.

Some APIs use one-based (`page=1` is the first page). Either works if **explicitly documented** and the response returns the matching index; never change the convention in an existing API without versioning/migration. Spring Data's `PageRequest.of(page,size)` uses **zero-based**, though the web resolver can be configured to accept one-based at the HTTP boundary.

### 2.3. Bounding Size and Preventing Arbitrary Requests from Exhausting Resources

`size=1000000` must not be allowed simply because the client can pass a large integer. Enforce:
- Minimum size 1; avoid division by 0.
- Published maximum size, 50 in the example.
- Non-negative page; compute `page × size` using `long` to avoid `int` overflow.
- Rate-limit and authorize requests via an API gateway/rate limiting where needed.
- Consider capping query length, filter count, sort column count, and offset depth; avoid unbounded wildcards/filters.

**Error policy of this lesson:** parsed parameters that violate the contract (size=0, sort field outside the allowlist) → HTTP `400 Bad Request` with a meaningful error code. Type conversion failures like `page=abc` to `int` are also typically returned as 400 by Spring MVC before reaching the method.

## 3. Offset Pagination: Algorithm, Metadata, and Limitations

### 3.1. Pagination Must Apply After Filtering and Sorting

Semantic processing order:

~~~text
Data source
   │
   ▼
Filter by category, available, q
   │
   ▼
Sort by allowed keys
   │
   ▼
Add stable tie-breaker key (e.g. id)
   │
   ▼
Compute totalElements / totalPages if contract requires
   │
   ▼
Take window offset..offset+size
   │
   ▼
Map entity/domain → response DTO
   │
   ▼
Return items + page metadata + sort + filters
~~~

If you paginate **before filtering**, a page may receive very few results even when other pages still hold matching records. Without an explicit order, the database can return two overlapping pages or drop records when the execution plan changes.

In SQL, the concept (not SQL meant verbatim for every dialect) is:

~~~sql
SELECT id, title, category, created_at, available
FROM books
WHERE (:category IS NULL OR category = :category)
  AND (:available IS NULL OR available = :available)
ORDER BY created_at DESC, id ASC
LIMIT :size OFFSET :offset;
~~~

This SQL snippet only illustrates filtering/sorting/offsetting. In production, build dynamic conditional SQL or use a query builder to leverage indexes; multiple `OR :param IS NULL` predicates can hinder the query planner. **Never concatenate client input directly into `ORDER BY`**: map sort names from an allowlist to valid properties/columns.

### 3.2. Page Formulas

If the number of matching records is `totalElements` and `size > 0`:

~~~text
offset      = page * size
totalPages  = totalElements == 0 ? 0 : ceil(totalElements / size)
hasNext     = page + 1 < totalPages
hasPrevious = page > 0 (policy may also check totalElements)
~~~

To avoid floating point math and overflow, Java can compute `totalPages = (totalElements == 0 ? 0 : 1 + (totalElements - 1) / size)` with `long`. The API must stay consistent on what `totalPages` means for an empty list: in this example **it equals 0**, `items=[]`, and `totalElements=0`.

Suppose there are 21 matches and size is 10: `totalPages=3`, page 0 has 10, page 1 has 10, page 2 has 1. Page `page=3` is out of range. You can choose **200 with `items=[]`** or **404/400** depending on product contract; this example chooses **200 and an empty page**, keeping the total count and requested index so the client can navigate back to an earlier page.

### 3.3. Returned Items Differ from Requested Size

- `size`: **maximum** number of items the client requested per page.
- `numberOfElements`: **actual** number of items in the current response; may be 0 or smaller than size.
- `totalElements`: total items **matching the filters** (not total rows in the table).
- `totalPages`: number of pages in the **filtered** set at the requested size.

Do not use `items.length` instead of `totalElements` when the UI needs the total count. Conversely, if the API only needs a Next button and the dataset is huge, computing `totalElements` may not be worth the cost.

## 4. Proper Sorting: Allowlists, Multi-Key, and Deterministic Order

### 4.1. Which Columns Are Allowed for Sorting?

An API should not let clients sort arbitrarily on any entity property. For instance, the public contract permits:
- `id`: incrementing identifier in the demo system.
- `title`: display title.
- `createdAt`: creation date/time.

Internal properties such as `passwordHash`, `internalScore`, `tenantId`, or expensive joins must not automatically become sort options. In Spring Data, `Sort.Order` carries property names, yet **the resolver is not an application security/allowlist mechanism**; validate the client's choice before passing it to the repository.

If you need to decouple API field names from entity field names, use an explicit mapping:

~~~text
API "createdAt" → entity property "createdAt"
API "title"     → entity property "title"
API "id"        → entity property "id"
Other than these three → 400 BAD_QUERY
~~~

### 4.2. Why Is a Secondary Tie-Breaker Key Required?

Suppose `ORDER BY created_at DESC` and three books share the exact same timestamp. The database is free to return those three equal-key records in any order. With `LIMIT/OFFSET`, two consecutive requests can paginate inconsistently. Use:

~~~sql
ORDER BY created_at DESC, id ASC
~~~

Unique `id` establishes a **total order** for a given data snapshot. Note: a stable secondary key resolves ties within a dataset; it **does not eliminate** items shifting when records are inserted/deleted between two offset page requests.

When a client sorts by `title,asc`, the example keeps `id ASC` as the secondary default. When supporting multiple client sort fields, document precedence clearly: `sort=createdAt,desc&sort=id,asc` in Spring Data web typically denotes primary then secondary key. **The runnable example below intentionally supports one primary sort field** and automatically appends `id ASC` to keep testing simple.

### 4.3. Letter Case, Vietnamese Diacritics, NULL, and Time Zones

String sort order depends on database collation and case sensitivity; Java's `String.CASE_INSENSITIVE_ORDER` does not match every SQL collation. If the API requires Vietnamese ordering rules, decide locale/collation at the storage layer and test with accented data. Do not promise identical ordering across in-memory Java, PostgreSQL/MySQL, and JavaScript clients.

For timestamps, store `Instant`/UTC at the data layer when representing absolute instants, use ISO-8601 with offset/UTC in the HTTP contract, and specify comparison rules. For nullable sort keys, document NULLS FIRST/LAST if clients require stability; add a unique tie-breaker and matching indexes.

## 5. Filters: Semantics, Null, Search, and Security

### 5.1. Distinguishing Omitted, Empty, and Populated Values

Three requests:

~~~text
GET /api/books
GET /api/books?category=
GET /api/books?category=spring
~~~

These can carry three meanings depending on the contract. In this example, null or whitespace-only `category` are normalized to "no filter"; `category=spring` matches the category string exactly, case-insensitively.

For `available`: `null` = no filter, `true` = available only, `false` = unavailable only. Do not use a primitive `boolean` with default `false` if you need to distinguish **absent** from **explicitly false**.

For `q`: after trimming, performs a case-insensitive substring check on `title`. This is a simple demo search, **not automatically full-text search**, fuzzy search, tokenization, or Vietnamese diacritic stripping.

### 5.2. Which Filters Combine with AND, Which with OR?

If supporting `category=java&category=spring`, document the semantics clearly: e.g., OR between the two category values, but AND with `available=true`. The runnable example accepts only **one category**, because by default repeated parameters with the same name in HTTP can be aggregated unexpectedly by resolvers when bound to a `String`.

UI display rules must match the backend: total count, page count, and sorting are all calculated **on the dataset after applying all filters**. When the user changes a filter, the UI should usually reset to page 0 rather than staying on a page beyond the new range.

### 5.3. Preventing Query Abuse and Unauthorized Data Exposure

Client-supplied input is untrusted: validate allowed values, filter lengths, condition counts, sort allowlists, and configure timeouts/indexes. **Access control / tenant filters** must be determined by the server from the principal/context and always applied in the repository query—never trust client parameters like `tenantId=...` to decide authorization.

When querying the database, use parameter binding in JPA/PreparedStatement/DSL instead of interpolating filter values into SQL. Never concatenate `ORDER BY ` + raw client sort field. SQL injection is not the only risk: sorting by internal columns or triggering expensive joins also hurts performance and leaks schema details.

## 6. Defining the List Result JSON Contract

A well-defined JSON envelope keeps the frontend from guessing framework internals:

~~~json
{
  "items": [
    {"id": 106, "title": "Testing Spring", "category": "spring", "createdAt": "2025-02-15", "available": false},
    {"id": 105, "title": "Spring Security", "category": "spring", "createdAt": "2024-06-01", "available": true}
  ],
  "page": {
    "number": 0,
    "size": 2,
    "numberOfElements": 2,
    "totalElements": 4,
    "totalPages": 2,
    "first": true,
    "last": false,
    "hasNext": true,
    "hasPrevious": false
  },
  "sort": {"field": "createdAt", "direction": "desc"},
  "filters": {"q": null, "category": "spring", "available": null}
}
~~~

This is a **lesson-defined contract**, not the default JSON of `Page<T>`. That is why the controller should map data into dedicated DTOs/envelopes.

Points to standardize:
- `items` is **always an array**, even when empty. Avoid `null` or missing the field without reason.
- `page.number` is zero-based like the query.
- `totalElements` is the count over the filtered set, not the entire catalog.
- `totalPages` equals 0 when `totalElements=0` in this contract.
- `first` / `last` follow the API convention. Both may be `true` for an empty dataset at page 0 if that choice is documented.
- `sort` echoes back the **validated and normalized** sort; `filters` echoes the effective criteria.
- With `available=false`, preserve boolean `false`; do not confuse it with an omitted filter (`null`).

An out-of-range page response still returns HTTP **200** and:

~~~json
{
  "items": [],
  "page": {
    "number": 10, "size": 2, "numberOfElements": 0,
    "totalElements": 4, "totalPages": 2,
    "first": false, "last": true,
    "hasNext": false, "hasPrevious": true
  },
  "sort": {"field": "createdAt", "direction": "desc"},
  "filters": {"q": null, "category": "spring", "available": null}
}
~~~

`last=true` on an out-of-range page means "there is no next page", **not that page 10 is the last valid page**. The frontend should therefore also inspect `totalPages` when rendering page links. Some applications choose 404 for out-of-range pages; define the policy and test it rather than changing it accidentally during refactoring.

### 6.1. Should You Return `Page<Entity>` Directly?

Spring Data's `Page<T>` is useful **inside the Java application/service/repository layers**, yet serializing `PageImpl` directly to JSON couples the frontend to library implementation details. Spring Data warns about the stability of this format; since Spring Data 3.3, `org.springframework.data.web.PagedModel` and `PageSerializationMode.VIA_DTO` offer a more stable representation option.

Sensible options:
1. **Design your own DTO envelope** as in the example, maintaining complete control over field names/compatibility.
2. Use `PagedModel` / `VIA_DTO` when Spring Data's standard format fits the contract, verifying actual version and field shape.
3. Use Spring HATEOAS when hypermedia navigation links are desired instead of hand-rolling URLs and guessing links.

Do not assume `Page<T>` always emits the same `content` or `pageable` fields across all Spring Data releases. Snapshot/test public API JSON before upgrading dependencies.

### 6.2. Include Navigation Links or Just Metadata?

For REST list contracts, you can add:

~~~json
{
  "links": {
    "self": "/api/books?page=0&size=2&sort=createdAt%2Cdesc&category=spring",
    "next": "/api/books?page=1&size=2&sort=createdAt%2Cdesc&category=spring"
  }
}
~~~

The snippet above is an **illustrative fragment adding a `links` field**; it is not the runnable response below. When generating links, preserve all filters, sort, and size; URL-encode properly, and never trust raw user-supplied Host headers when generating absolute links behind a reverse proxy. If `hasNext=false`, omit `next` instead of emitting a broken link.

## 7. Runnable Example: In-Memory Spring Boot REST Catalog

To verify HTTP semantics independently of a database, the following example uses six fixed records and runs filter → sort → page. In a real environment, push filtering/sorting/paging down to the database (avoid loading the entire table and sorting in the heap).

Structure:

~~~text
catalog-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/catalog/
    │   ├── CatalogApplication.java
    │   └── web/
    │       ├── BookController.java
    │       ├── BookCatalogService.java
    │       └── CatalogErrorHandler.java
    └── test/java/com/example/catalog/web/
        └── BookControllerTest.java
~~~

### 7.1. Gradle and Spring Boot

`settings.gradle`:

~~~groovy
rootProject.name = 'catalog-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-data-jpa` is not needed in this example; pagination is an in-memory service algorithm. This demonstrates `@RequestParam` and JSON DTOs working purely with Spring MVC. The Gradle project needs an appropriate wrapper, e.g., Gradle 8.x running on Java 17.

`src/main/java/com/example/catalog/CatalogApplication.java`:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### 7.2. Controller: Defining the Contract at the HTTP Boundary

`src/main/java/com/example/catalog/web/BookController.java`:

~~~java
package com.example.catalog.web;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookCatalogService service;

    public BookController(BookCatalogService service) {
        this.service = service;
    }

    @GetMapping
    public PageResponse<BookItem> list(
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "20") int size,
            @RequestParam(name = "sort", defaultValue = "createdAt,desc") String sort,
            @RequestParam(name = "category", required = false) String category,
            @RequestParam(name = "available", required = false) Boolean available,
            @RequestParam(name = "q", required = false) String q) {

        return service.find(page, size, sort, category, available, q);
    }

    public record BookItem(
            long id, String title, String category,
            String createdAt, boolean available) {
    }

    public record PageMeta(
            int number, int size, int numberOfElements,
            long totalElements, long totalPages,
            boolean first, boolean last, boolean hasNext, boolean hasPrevious) {
    }

    public record SortMeta(String field, String direction) {
    }

    public record FilterMeta(String q, String category, Boolean available) {
    }

    public record PageResponse<T>(
            List<T> items, PageMeta page,
            SortMeta sort, FilterMeta filters) {
    }
}
~~~

Here:
- `@RestController` serializes `PageResponse` to JSON via Jackson.
- `@RequestParam` receives HTTP inputs and converts `page`/`size` to `int` and `available` to `Boolean`.
- The controller only coordinates. The service validates page/size/sort policy, normalizes filters, selects data, and builds metadata.
- The records define the specific **JSON response contract** without exposing repository entities or framework internals.
- `PageMeta.totalElements`/`totalPages` use `long` to fit large datasets in JSON; the in-memory demo is naturally small.

### 7.3. Service: Filter → Sort → Paginate → DTO

`src/main/java/com/example/catalog/web/BookCatalogService.java`:

~~~java
package com.example.catalog.web;

import com.example.catalog.web.BookController.BookItem;
import com.example.catalog.web.BookController.FilterMeta;
import com.example.catalog.web.BookController.PageMeta;
import com.example.catalog.web.BookController.PageResponse;
import com.example.catalog.web.BookController.SortMeta;
import java.time.LocalDate;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.springframework.stereotype.Service;

@Service
public class BookCatalogService {

    private record Book(
            long id, String title, String category,
            LocalDate createdAt, boolean available) {
    }

    private static final List<Book> BOOKS = List.of(
            new Book(101, "Java Basics", "java",
                    LocalDate.parse("2023-05-01"), true),
            new Book(102, "Spring MVC", "spring",
                    LocalDate.parse("2024-01-10"), true),
            new Book(103, "Spring Data", "spring",
                    LocalDate.parse("2024-03-12"), false),
            new Book(104, "Java Concurrency", "java",
                    LocalDate.parse("2024-05-20"), true),
            new Book(105, "Spring Security", "spring",
                    LocalDate.parse("2024-06-01"), true),
            new Book(106, "Testing Spring", "spring",
                    LocalDate.parse("2025-02-15"), false)
    );

    private record SortSelection(String field, String direction) {
    }

    public PageResponse<BookItem> find(
            int page, int size, String rawSort,
            String category, Boolean available, String q) {

        if (page < 0) {
            throw new IllegalArgumentException("page must be >= 0");
        }
        if (size < 1 || size > 50) {
            throw new IllegalArgumentException("size must be between 1 and 50");
        }

        SortSelection sort = parseSort(rawSort);
        String categoryFilter = normalize(category);
        String qFilter = normalize(q);

        Comparator<Book> primary = switch (sort.field()) {
            case "id" -> Comparator.comparingLong(Book::id);
            case "title" ->
                    Comparator.comparing(Book::title, String.CASE_INSENSITIVE_ORDER);
            case "createdAt" -> Comparator.comparing(Book::createdAt);
            default -> throw new IllegalStateException("Unexpected sort field");
        };

        if ("desc".equals(sort.direction())) {
            primary = primary.reversed();
        }

        // Unique ID is the tie-breaker so the order is deterministic.
        Comparator<Book> order = primary.thenComparingLong(Book::id);

        List<Book> matched = BOOKS.stream()
                .filter(book -> categoryFilter == null
                        || book.category().equalsIgnoreCase(categoryFilter))
                .filter(book -> available == null
                        || book.available() == available)
                .filter(book -> qFilter == null
                        || book.title().toLowerCase(Locale.ROOT)
                                .contains(qFilter.toLowerCase(Locale.ROOT)))
                .sorted(order)
                .toList();

        long totalElements = matched.size();
        long totalPages = totalElements == 0
                ? 0 : 1 + (totalElements - 1) / size;
        long start = (long) page * size;

        List<BookItem> items;
        if (start >= totalElements) {
            items = List.of();
        } else {
            int from = (int) start;
            int to = (int) Math.min(totalElements, start + size);
            items = matched.subList(from, to).stream()
                    .map(book -> new BookItem(
                            book.id(), book.title(), book.category(),
                            book.createdAt().toString(), book.available()))
                    .toList();
        }

        boolean hasNext = (long) page + 1 < totalPages;
        boolean hasPrevious = page > 0 && totalElements > 0;
        PageMeta pageMeta = new PageMeta(
                page, size, items.size(),
                totalElements, totalPages,
                page == 0,
                !hasNext,
                hasNext,
                hasPrevious);

        return new PageResponse<>(
                items,
                pageMeta,
                new SortMeta(sort.field(), sort.direction()),
                new FilterMeta(qFilter, categoryFilter, available));
    }

    private static String normalize(String text) {
        if (text == null || text.isBlank()) {
            return null;
        }
        return text.trim();
    }

    private static SortSelection parseSort(String raw) {
        String[] parts = raw.split(",", -1);
        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "sort must have format field,direction");
        }

        String field = parts[0].trim();
        String direction = parts[1].trim().toLowerCase(Locale.ROOT);
        if (!Set.of("id", "title", "createdAt").contains(field)
                || !Set.of("asc", "desc").contains(direction)) {
            throw new IllegalArgumentException(
                    "sort field or direction is not supported");
        }
        return new SortSelection(field, direction);
    }
}
~~~

**Explanation of intentional choices:**
1. `BOOKS` is an immutable fixture: easy to reproduce results. Production must filter/sort/page **in the database** instead of pulling the entire table into the JVM.
2. `Boolean available` distinguishes `null` (no filter) from `false`.
3. `normalize` turns blank and whitespace into no filter, without forcing `category` in metadata to lowercase; data matching uses `equalsIgnoreCase`.
4. `parseSort` checks field/direction against an allowlist. An automatic secondary sort `id ASC` ensures deterministic results when primary sort values tie.
5. `start` uses `long` to avoid `int` multiplication overflow. It only casts to `int` when `start < matched.size()`, safe for a JVM `List`.
6. When there is no data, `totalPages=0`, `first=true` when page=0, and `last=true` because there is no next page.
7. `hasPrevious` is metadata for client behavior in the example; on an out-of-range page when data exists, navigating back to an earlier page is still valid.

`String.CASE_INSENSITIVE_ORDER` serves the Java demo; a production database must use collation/sort keys compatible with the API contract. When multiple records share the same timestamp, a unique ID tie-breaker resolves ordering ties.

### 7.4. Returning Clear Input Errors

`src/main/java/com/example/catalog/web/CatalogErrorHandler.java`:

~~~java
package com.example.catalog.web;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class CatalogErrorHandler {

    public record ErrorBody(String code, String message) {
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ErrorBody> badQuery(IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body(new ErrorBody("BAD_QUERY", ex.getMessage()));
    }
}
~~~

This handler targets **`IllegalArgumentException` thrown by the service**; production apps should use a dedicated domain exception (such as `InvalidListQueryException`) to avoid turning every `IllegalArgumentException` from internal logic bugs into 400.

An error like `page=xyz` before entering the service is a Spring MVC type conversion failure; it typically returns **400** via the default exception mechanism rather than the `ErrorBody` JSON produced by the method above. If all errors must share one schema, override `ResponseEntityExceptionHandler` hooks or use dedicated conversion/binding advice and test it.

**Security note:** do not always return raw exception messages if exceptions might contain SQL, internal identifiers, or secrets. In the example, messages come from allowlist/validation checks and contain no sensitive payload; production should use safe message codes and correlation IDs.

## 8. Calling the API and Interpreting Results

Run in a project with the Gradle wrapper and Java 17:

~~~bash
./gradlew bootRun
~~~

On Windows you can run `.\gradlew.bat bootRun`. Because this is a Spring Boot app, it cannot be run standalone via `javac BookController.java` without the Spring classpath.

### 8.1. First Page for Category `spring`

~~~bash
curl -s 'http://localhost:8080/api/books?page=0&size=2&category=spring'
~~~

Default sort is `createdAt,desc`. The four `spring` books in order are:
1. ID `106` — Testing Spring (2025-02-15).
2. ID `105` — Spring Security (2024-06-01).
3. ID `103` — Spring Data (2024-03-12).
4. ID `102` — Spring MVC (2024-01-10).

With size=2, the first page contains **106, 105**; `totalElements=4`, `totalPages=2`, `hasNext=true`, `numberOfElements=2`.

~~~json
{
  "items": [
    {"id":106,"title":"Testing Spring","category":"spring","createdAt":"2025-02-15","available":false},
    {"id":105,"title":"Spring Security","category":"spring","createdAt":"2024-06-01","available":true}
  ],
  "page": {
    "number":0,"size":2,"numberOfElements":2,
    "totalElements":4,"totalPages":2,
    "first":true,"last":false,"hasNext":true,"hasPrevious":false
  },
  "sort":{"field":"createdAt","direction":"desc"},
  "filters":{"q":null,"category":"spring","available":null}
}
~~~

### 8.2. Page Two and Filtering by `available`

~~~bash
curl -s 'http://localhost:8080/api/books?page=1&size=2&category=spring'
curl -s 'http://localhost:8080/api/books?page=0&size=2&category=spring&available=true'
~~~

The first request returns IDs `103`, `102`, `hasNext=false`, `hasPrevious=true`. The second request keeps only IDs `105`, `102`; `totalElements=2` and `totalPages=1`. **Do not keep total=4 after adding the `available` filter**.

### 8.3. Changing Sort Does Not Change Filtered Count

~~~bash
curl -s 'http://localhost:8080/api/books?page=0&size=2&category=spring&sort=title,asc'
~~~

Title order in the Java demo sort:
- `Spring Data` (103).
- `Spring MVC` (102).
- `Spring Security` (105).
- `Testing Spring` (106).

Page 0 receives `103,102`. `totalElements` remains 4: sorting **changes order**, not the number of matching records.

### 8.4. Out-of-Range Page and Filter with No Matches

~~~bash
curl -s 'http://localhost:8080/api/books?page=10&size=2&category=spring'
curl -s 'http://localhost:8080/api/books?q=NoSuchBook'
~~~

The first returns HTTP **200**, `items=[]`, `number=10`, `totalElements=4`, `totalPages=2`. The second returns HTTP **200**, `items=[]`, `totalElements=0`, `totalPages=0`, because no book title contains NoSuchBook.

This is a valid state for a list query. Returning 404 for "single record not found" (`GET /api/books/{id}`) is a separate concern from an empty list.

### 8.5. Contract-Violating Values

~~~bash
curl -i 'http://localhost:8080/api/books?page=-1'
curl -i 'http://localhost:8080/api/books?size=0'
curl -i 'http://localhost:8080/api/books?size=1000'
curl -i 'http://localhost:8080/api/books?sort=secret,asc'
curl -i 'http://localhost:8080/api/books?page=abc'
~~~

The first four requests trigger `IllegalArgumentException` from the service and advice returns **400** with code `BAD_QUERY`. The last request fails `int` conversion, so Spring MVC also typically returns **400**, though the body may differ because it goes through the default exception handler.

**Do not silently clamp `size=1000` to 50 if the contract requires returning 400.** Another product may intentionally clamp; what matters is that clients know the policy and the response reports the enforced size.

## 9. MockMvc Tests for the Full List Contract

`src/test/java/com/example/catalog/web/BookControllerTest.java`:

~~~java
package com.example.catalog.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void filtersBeforePagingAndReturnsTotalForFilteredSet() throws Exception {
        mvc.perform(get("/api/books")
                        .param("page", "0")
                        .param("size", "2")
                        .param("category", "spring"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(2))
                .andExpect(jsonPath("$.items[0].id").value(106))
                .andExpect(jsonPath("$.items[1].id").value(105))
                .andExpect(jsonPath("$.page.totalElements").value(4))
                .andExpect(jsonPath("$.page.totalPages").value(2))
                .andExpect(jsonPath("$.page.hasNext").value(true))
                .andExpect(jsonPath("$.sort.field").value("createdAt"));
    }

    @Test
    void nextPageKeepsStableOrder() throws Exception {
        mvc.perform(get("/api/books")
                        .param("page", "1")
                        .param("size", "2")
                        .param("category", "spring"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].id").value(103))
                .andExpect(jsonPath("$.items[1].id").value(102))
                .andExpect(jsonPath("$.page.hasNext").value(false))
                .andExpect(jsonPath("$.page.hasPrevious").value(true));
    }

    @Test
    void availableFalseIsARealFilter() throws Exception {
        mvc.perform(get("/api/books")
                        .param("category", "spring")
                        .param("available", "false"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page.totalElements").value(2))
                .andExpect(jsonPath("$.items[0].id").value(106))
                .andExpect(jsonPath("$.items[1].id").value(103))
                .andExpect(jsonPath("$.filters.available").value(false));
    }

    @Test
    void sortingByTitleChangesOrderNotTotal() throws Exception {
        mvc.perform(get("/api/books")
                        .param("category", "spring")
                        .param("size", "2")
                        .param("sort", "title,asc"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].id").value(103))
                .andExpect(jsonPath("$.items[1].id").value(102))
                .andExpect(jsonPath("$.page.totalElements").value(4))
                .andExpect(jsonPath("$.sort.direction").value("asc"));
    }

    @Test
    void outOfRangePageReturnsEmptyArrayAndOriginalTotal() throws Exception {
        mvc.perform(get("/api/books")
                        .param("page", "10")
                        .param("size", "2")
                        .param("category", "spring"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(0))
                .andExpect(jsonPath("$.page.totalElements").value(4))
                .andExpect(jsonPath("$.page.number").value(10))
                .andExpect(jsonPath("$.page.hasNext").value(false));
    }

    @Test
    void noMatchesReturnsZeroTotals() throws Exception {
        mvc.perform(get("/api/books").param("q", "NoSuchBook"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(0))
                .andExpect(jsonPath("$.page.totalElements").value(0))
                .andExpect(jsonPath("$.page.totalPages").value(0));
    }

    @Test
    void invalidPaginationAndSortReturn400() throws Exception {
        mvc.perform(get("/api/books").param("page", "-1"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("BAD_QUERY"));

        mvc.perform(get("/api/books").param("size", "0"))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/api/books").param("size", "51"))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/api/books").param("sort", "privateField,asc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void parameterConversionFailureIs400() throws Exception {
        mvc.perform(get("/api/books").param("page", "abc"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Run all tests:

~~~bash
./gradlew test
~~~

These tests intentionally check **item order**, **post-filter totals**, **out-of-range pages**, **boolean false**, and **error statuses**. Only asserting item count without checking order misses sorting bugs. Only asserting total on unfiltered requests misses "count before filter" bugs.

Verification scope note: the test code is presented for the demo app. Security filters or custom MVC configuration in a real project may require additional MockMvc setup. In-memory tests **do not prove SQL correctness, index usage, or consistency under concurrent transactions**.

## 10. With Spring Data: `Pageable`, `Sort`, `Page`, and `Slice`

### 10.1. Spring MVC Accepts `Pageable` via Spring Data Web Support

In an application with Spring Data web configured (typically via the corresponding Spring Data/Boot starter auto-configuration), a controller can accept directly:

~~~java
@GetMapping("/api/books")
public Page<BookEntity> find(
        @PageableDefault(size = 20, sort = "createdAt",
                         direction = Sort.Direction.DESC)
        Pageable pageable) {
    return repository.findAll(pageable);
}
~~~

**This is a non-standalone fragment:** it requires imports for `Page`, `Pageable`, `PageableDefault`, `Sort`, entity/repository declarations, and Data/JPA config; it is also **not a recommendation to return `Page<Entity>` directly in a public API**. Map `Page<BookEntity>` into a DTO and envelope as shown in section 6.

Spring Data's web resolver typically interprets:
- `page`: zero-based index, default 0.
- `size`: page size, usually defaulting to 20 in the resolver (customizable).
- `sort=title,asc`: sort field/direction.
- `sort=createdAt,desc&sort=id,asc`: multiple directives.

`@PageableDefault` overrides defaults for the controller parameter; `@SortDefault` can configure multiple default sorts. The resolver also supports `setMaxPageSize` and `setOneIndexedParameters` when configured. Do not assume `@PageableDefault(size=20)` creates a sort allowlist or satisfies every security policy by itself.

### 10.2. Repository Queries with `Pageable`

A typical Spring Data JPA repository may declare:

~~~java
// Fragment, only valid when BookEntity and JPA repository setup exist.
interface BookRepository extends JpaRepository<BookEntity, Long> {
    Page<BookEntity> findByCategoryIgnoreCase(
            String category, Pageable pageable);
}
~~~

A real project must combine optional filters `q`, `available`, and authorization into the same query before paging. You can use `Specification`, Criteria API, Querydsl, or appropriate repository methods. **Never** do:
1. `repository.findAll()` loading the entire table.
2. `stream().filter(...)` in the JVM.
3. `subList(...)` returning a single page.

That approach is acceptable for a six-record fixture teaching the contract, but wrong in scale and cost for a production database.

### 10.3. How Does `Page` Differ from `Slice`?

| Return type | Knows totalElements/totalPages? | Knows if next page exists? | Typical cost |
| --- | --- | --- | --- |
| `Page<T>` | Yes, via total query when needed | Yes | May require an expensive `COUNT(...)` |
| `Slice<T>` | Not needed | Yes (`hasNext`) | Typically queries `size + 1` to check for more |
| `List<T>` with `Pageable` | No page metadata | Not directly | Fetches only the limit/offset window |
| `Window<T>` with scrolling | Not focused on total count | Yes | Supports offset/keyset scrolling depending on store |

`Page` is useful for UIs showing "Page 2 of 37" or needing the filtered total count. `Slice` fits "Load more" flows that only need to know whether more data exists. Do not add a COUNT query merely because an HTML page has a Next button; check what the UX contract actually requires.

Depending on repository and query, Spring Data can optimize or infer the total count in certain cases, so do not claim **every** `Page` always executes exactly two SQL statements.

### 10.4. Creating Stable JSON from `Page`

Conceptual example in a service:

~~~java
// Fragment requiring the application's DTO and repository types.
Page<BookEntity> entityPage = repository.findAll(validatedPageable);

List<BookDto> items = entityPage.getContent().stream()
        .map(BookDto::fromEntity)
        .toList();

// Build the application-managed response DTO:
// items, page number/size, numberOfElements,
// entityPage.getTotalElements(), entityPage.getTotalPages(),
// entityPage.hasNext(), applied sort, effective filters.
~~~

If using `org.springframework.data.web.PagedModel` (Spring Data 3.3+) or `@EnableSpringDataWebSupport(pageSerializationMode = VIA_DTO)`, verify the actual representation with integration tests and versioned docs. The name `PagedModel` also exists in Spring HATEOAS; **they are not the same class**.

## 11. Offset Pagination Does Not Preserve a Snapshot When Data Changes

### 11.1. The Problem When New Records Arrive

Suppose sorting newest-first:

~~~text
At time T1:  [A, B, C, D, E, F]
page=0,size=2 -> [A, B]
~~~

Before the client fetches the next page, a new record `X` appears at the top of the list:

~~~text
At time T2:  [X, A, B, C, D, E, F]
page=1,size=2 -> [B, C]
~~~

The client saw `B` on both pages. When records are deleted or filter values change, **skipped items** can occur. The secondary key `id` makes ordering deterministic at a given moment, yet **it does not freeze a snapshot across requests**.

Handling strategies depending on needs:
- Normal lookup UIs: accept changing data and offer a Refresh action.
- Exports/reports requiring a consistent set: use a snapshot/cursor token or an appropriate transaction/snapshot strategy without holding HTTP transactions open indefinitely.
- Infinite feeds, large datasets, chronological order: consider cursor/keyset pagination.

### 11.2. Keyset/Cursor Pagination

Instead of `OFFSET 100000`, a cursor records the key of the last returned item:

~~~text
GET /api/events?limit=20&after=opaqueCursor
~~~

For data ordered `createdAt DESC, id DESC`, the next request fetches only records **coming after the last tuple** in that order. Conceptual SQL:

~~~sql
SELECT id, created_at, payload
FROM events
WHERE (created_at < :last_created_at)
   OR (created_at = :last_created_at AND id < :last_id)
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;
~~~

This SQL illustrates keyset pagination for two non-null keys on a database with matching comparison semantics. A composite index matching the filter/order and proper NULL/collation handling are required. Never use raw client query strings in place of a trusted token.

A public API cursor should be:
- Opaque (e.g., base64url-encoded versioned token with keyset values, sort, filter fingerprint, expiry); if the cursor affects authorization, protect it against tampering.
- Bound to the **exact filters and sort**; a cursor must not be reused across a different query.
- Subject to a clear `limit` cap and expiry/restart behavior.
- Returning `items`, `nextCursor`, `hasNext`; **never promise `totalPages`** without counting the entire set.

Cursors do not magically create an immutable snapshot. They keep traversal position stable when inserts happen ahead of the cursor, though updates/deletes affecting sort/filter columns can still affect traversal.

### 11.3. Choosing Between Them

| Product requirement | Offset (`page,size`) | Cursor/keyset |
| --- | --- | --- |
| Jump straight to page 19 | Convenient | Usually inconvenient |
| Display "total 1,239 results" | `Page`/COUNT fits | Needs a separate count if desired |
| Continuous "Load more" feed | Works, but shifts on writes | Usually better with stable sort/keyset |
| Very deep offsets on large tables | Can be expensive | Can be faster with proper indexes |
| Client needs shareable fixed page URLs | Easy to express | Needs tokens and expiry policy |
| Data changes between requests | Does not guarantee a snapshot | Also does not guarantee an absolute snapshot |

Do not switch to cursors just because you have a list API: choose based on volume, UX needs, query cost, and real consistency requirements.

## 12. Performance, Indexes, and Total Reliability

### 12.1. Count Queries Can Be Heavy

A `Page<Book>` request in Spring Data usually queries page items and may need a count for `totalElements`. COUNT over large joins/filters can be expensive, especially with multiple joins, authorization checks, distinct, or full-text queries. Use `Slice` if totals are unnecessary, or design the API to include totals only when requested (e.g., `includeTotal=true`) if appropriate.

Never return `totalElements=items.size()` to dodge counting while keeping the field name: that changes semantics and breaks frontend pagination math. If an exact total cannot be provided, omit the field, use a clearly named `totalApproximate` with explicit guarantees, or switch to a slice/cursor contract.

### 12.2. Indexes Should Serve Filters and Sorts

If you frequently filter by `category` and sort by `createdAt DESC,id DESC`, consider a composite index starting with selective filter columns followed by sort keys (depending on database/cardinality/query workload). Verify with `EXPLAIN` and production-like data. Creating indexes for every filter/sort combination slows writes and increases storage; measure the workload instead of guessing.

A query without `ORDER BY` has no guaranteed order, even if it happens to follow primary key order today. If sorting on expressions or joined fields, check cost and enforce bounds.

### 12.3. Consistency Between Total and Items

When data changes between the items query and the count query, the two results can reflect two different points in time. Isolation levels, transaction snapshots, and persistence logic govern consistency; `Page<T>` does not guarantee an absolute snapshot across HTTP requests.

The frontend should handle:
- `items=[]` while `totalElements>0` if the user went past the last page.
- Total shrinking when filters change.
- A record being deleted before the user clicks Next.
- Previous/next pages shifting under concurrent writes.

Product documentation should state that **total is an as-of-query-time count** and can change, unless the API explicitly provides snapshot semantics.

## 13. Error Contracts, HTTP Caching, and API Evolution

### 13.1. A Consistent Status Set

| Request or condition | Suggested status for example | Meaning |
| --- | --- | --- |
| List with data | `200 OK` | `items` and metadata |
| Valid filter with no matches | `200 OK` | `items=[]`, `totalElements=0` |
| Page beyond page count with valid input | `200 OK` | Returns `items=[]` per published policy |
| `page=-1`, `size=0`, unknown sort | `400 Bad Request` | Violates query contract |
| `page=abc` | `400 Bad Request` | Type conversion/binding error |
| Unauthenticated / insufficient permissions | `401`/`403` | Per auth/authorization mechanism |
| Real server-side query/DB error | Appropriate `5xx` | Never disguise as an empty list |

This table reflects the **example app's policy**, not a mandate for every API. What matters is machine-readable error codes and tests so the frontend never interprets `[]` as service failure.

### 13.2. Filters Are Part of the Cache Key

If using HTTP/CDN caching for GET, the cache key must vary on query params affecting output (`page`, `size`, `sort`, all filters, tenant/visibility if any). Never cache user-specific responses in shared caches without appropriate authorization/cache headers.

`ETag` or `Last-Modified` can support conditional GET when a suitable resource version exists. However, computing an `ETag` by serializing the entire dataset on every request defeats caching; design around the data lifecycle.

### 13.3. Backward Compatibility

Changes that can break clients:
- Switching `page` from zero-based to one-based.
- Changing default size/sort, shifting item positions.
- Renaming/removing fields or changing `totalElements` from number to string.
- Replacing public sort fields with new entity field names.
- Changing `q` filter semantics from contains to exact match.
- Replacing a custom JSON envelope with Jackson serialization of `PageImpl`.

Changes that are generally safer when tested:
- Adding optional metadata fields when clients ignore unknown properties.
- Adding optional filters defaulting to "no filter".
- Adding allowlisted sort options while preserving old ones.

For APIs with multiple consumers, publish OpenAPI response schemas, standardize error schemas, and run contract tests in CI. Never let a Spring Data upgrade silently alter your public response shape.

## 14. Common Bugs and How to Diagnose Them

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Items repeat across two pages | Sort lacks a unique tie-breaker or data changed | Add a secondary sort key, consider cursor/snapshot |
| Returns 20 items when size=5 requested | Limit/`Pageable` not passed down to query | Assert size and inspect actual query |
| Wrong total when filtering | COUNT ran on whole table or count conditions differ from data query | Apply identical filters/tenant scope to count |
| Arbitrary sort accesses internal properties | Missing allowlist | Map public field names to valid properties |
| `size=0` causes division by zero | Size not validated | Enforce 1..MAX before computing metadata |
| `page × size` is negative/wrong | `int` overflow | Validate page/size and multiply as `long` |
| Last page empty even though UI thinks more exist | Data changed or stale total | Refresh, handle out-of-range, and track versions |
| `PageImpl` JSON shape changed after Spring Data upgrade | Exposed internal framework representation | Use a stable envelope or tested PagedModel |
| COUNT query too slow | Returning `Page` when UI only needs Next | Consider `Slice` or cursor |
| `q` does not match accented characters as expected | Inconsistent string matching/collation | Define search/collation contract |
| Works in-memory, paginates wrong in DB | Filtered/sorted in JVM after limit, or missing ORDER BY | Push filter/sort/page into query, run integration tests |
| 200 with `items=[]` masks server errors | Catching exceptions and returning empty list | Distinguish empty dataset from infrastructure failures |
| Client sent `sort=title,desc` but metadata says asc | Used default when building response | Echo normalized effective sort and test it |

When debugging, capture **one concrete URL** with its filters, sort, index, size, user permissions, and data snapshot to reproduce. Inspect the executed SQL (`WHERE`/`ORDER BY`/`LIMIT OFFSET`), Java mapping, and JSON envelope rather than looking only at the response array.

## 15. Design Checklist and Self-Assessment

Before publishing a list API:
1. Document query names, page base, default size, max size, and invalid-parameter behavior.
2. Define filter criteria, case sensitivity, blank/null semantics, AND/OR, timezone, and access control.
3. Choose a sort allowlist with default ordering and a **unique tie-breaker**.
4. Paginate only after filtering/sorting at the **data source**, preferring the database for large datasets.
5. Choose among `Page` (with totals), `Slice` (hasNext), and cursor (load-more/large feeds).
6. Define a self-owned JSON envelope; `items=[]` when empty, metadata scoped to the **filtered set**.
7. Standardize out-of-range page handling and `totalPages=0`, 400 conversion/validation, and system error statuses.
8. Test multiple pages, sort ties, `available=false`, blank filters, out-of-range, empty datasets, boundary sizes, and auth/tenant rules.
9. With a DB, measure counts/deep offsets, EXPLAIN indexes, and test queries under changing data.
10. Maintain backward compatibility for field names, metadata, and defaults; snapshot-test public JSON when upgrading frameworks.

### Self-Check Questions

**1.** A client sends `page=2&size=10` to a zero-based API. What is the offset?

**Answer:** 20; this is the third page when the first page is 0.

**2.** Why does `totalElements` not equal `items.length`?

**Answer:** `items.length` only counts elements on the currently returned page; `totalElements` counts all records matching the filters when the API provides a total.

**3.** Is sorting by `createdAt DESC` stable enough when multiple records share the same timestamp?

**Answer:** No. Add a unique key, such as `id ASC`, to establish a total order within a snapshot.

**4.** Should a feed with only a "Load more" button use `Page<T>` or `Slice<T>`?

**Answer:** `Slice<T>` is usually more suitable when total count is unneeded; cursor/keyset pagination is worth considering if offsets grow deep or data changes frequently.

**5.** What is the risk of returning `PageImpl<Entity>` directly to the frontend?

**Answer:** JSON easily becomes coupled to Spring Data's serialization structure, which can change across versions; entities may also leak fields. Use a stable DTO/envelope or a supported and tested representation mechanism.

**6.** Why must `available=null` be distinguished from `available=false`?

**Answer:** `null` means no filter; `false` means fetch only unavailable records. Merging the two causes wrong filtering and wrong totals.

## 16. Official Documentation

- [Spring Framework — `@RequestParam` in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html): query/form parameters and conversion.
- [Spring Framework — `@ResponseBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html): serializing return values via HTTP message converters.
- [Spring Data Commons — Web support, Pageable, and Sort](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html): `page`, `size`, `sort`, resolvers, customizers, and `@PageableDefault`.
- [Spring Data JPA — Paging/Sorting, `Page`, `Slice`, and Scrolling](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): count queries, offset/keyset, and trade-offs.
- [Spring Data — `PageableDefault` Javadoc](https://docs.spring.io/spring-data/commons/docs/3.3.5/api/org/springframework/data/web/PageableDefault.html): default page/size/sort for method parameters.
- [Spring Data — `PageSerializationMode` Javadoc](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/web/config/EnableSpringDataWebSupport.PageSerializationMode.html): `DIRECT` and `VIA_DTO`.
- [Spring Data — `PagedModel` Javadoc](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/web/PagedModel.html): stable DTO representation of `Page`.
- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): note this is a separate REST repository exposure mechanism and does not automatically apply to `@RestController` classes you write.

**Key takeaway:** a reliable REST list endpoint requires **clear filter semantics, deterministic ordering, bounded pagination, and a stable response contract**. Spring MVC parses parameters and writes responses; Spring Data assists with querying/paging when repositories are used, while public API semantics, consistency, and error policies must always be decided and tested by the application.
