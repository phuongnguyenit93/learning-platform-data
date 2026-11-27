# OrderBy and Dynamic Sorting

## 1. When Is Sorting Needed in Spring Data MongoDB?

In Spring Data MongoDB, repositories can derive queries automatically from **method names** (*derived queries*). When returning lists, applications typically need a specific order: newest books first, books A–Z, most viewed articles, or priority orders first.

For those needs, Spring Data provides two primary mechanisms:

- **`OrderBy` in the method name:** hardcodes sort keys and directions right in the repository interface, e.g., `findByStatusOrderByCreatedAtDescIdDesc(...)`.
- **`Sort` passed at call time:** chooses sort keys and directions dynamically at runtime, e.g., `findByStatus("PUBLISHED", Sort.by("title").ascending())`.

When paginating, you can embed `Sort` inside `Pageable` to sort and limit returned documents together.

The core principle is that **sorting must happen in MongoDB**, rather than loading a huge collection into Java and calling `List.sort(...)`. In real systems, result ordering also intersects with **indexes, pagination stability, BSON field mapping, and user-input validation**.

| Business need | Usually suitable option |
| --- | --- |
| A screen always shows newest books first | Derived query with `OrderByCreatedAtDescIdDesc` |
| Users pick sorting by title, views, or date | Derived query accepting a `Sort` parameter |
| API returns paginated books needing deterministic order | `Pageable` containing a `Sort` |
| Complex filters, projections, or aggregations needed | `MongoTemplate` or aggregation with `$sort` |
| Reactive application | Repository or `ReactiveMongoTemplate` with the same sorting principles |

## 2. Dataset and Entity Used Throughout This Lesson

Suppose a book catalog app has a `books` collection. Statuses can be `DRAFT` or `PUBLISHED`, while creation timestamp is stored under BSON field `created_at`.

Sample data in `mongosh`:

```javascript
use book_sort_demo

db.books.insertMany([
  {
    _id: "BK-001",
    title: "Java căn bản",
    status: "PUBLISHED",
    created_at: ISODate("2026-11-01T08:00:00Z"),
    view_count: 80,
    author_name: "An"
  },
  {
    _id: "BK-002",
    title: "MongoDB thực hành",
    status: "PUBLISHED",
    created_at: ISODate("2026-11-04T08:00:00Z"),
    view_count: 140,
    author_name: "Bình"
  },
  {
    _id: "BK-003",
    title: "Spring Data nhập môn",
    status: "PUBLISHED",
    created_at: ISODate("2026-11-10T08:00:00Z"),
    view_count: 120,
    author_name: "An"
  },
  {
    _id: "BK-004",
    title: "Query nâng cao",
    status: "PUBLISHED",
    created_at: ISODate("2026-11-10T08:00:00Z"),
    view_count: 260,
    author_name: "Chi"
  },
  {
    _id: "BK-005",
    title: "Bản thảo dữ liệu",
    status: "DRAFT",
    created_at: ISODate("2026-11-12T08:00:00Z"),
    view_count: 0,
    author_name: "Bình"
  }
])
```

Run `insertMany` only when the practice collection does not yet contain these IDs; re-running causes duplicate-key errors. On Spring Boot 3.x, a sample app might use `spring.data.mongodb.uri=mongodb://localhost:27017/book_sort_demo`. Production environments must configure authentication, authorization, and secure connections.

The Java entity is declared as:

```java
package com.example.library;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "books")
public class Book {

    @MongoId(FieldType.STRING)
    private String id;

    private String title;
    private String status;

    @Field("created_at")
    private Instant createdAt;

    @Field("view_count")
    private long viewCount;

    @Field("author_name")
    private String authorName;

    protected Book() {}

    public String getId() { return id; }
    public String getTitle() { return title; }
    public String getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public long getViewCount() { return viewCount; }
    public String getAuthorName() { return authorName; }
}
```

Keep track of three name groups:

| Java property | BSON field | Used when writing derived queries or `Sort` on the entity |
| --- | --- | --- |
| `id` | `_id` | `id` |
| `createdAt` | `created_at` | `createdAt` |
| `viewCount` | `view_count` | `viewCount` |
| `authorName` | `author_name` | `authorName` |
| `title` | `title` | `title` |

`@MongoId(FieldType.STRING)` ensures IDs like `BK-001` are stored as BSON Strings. With `@Field`, Spring Data maps Java properties to BSON field names; in `mongosh`, you still write actual BSON field names.

## 3. Static `OrderBy` in Method Names

Repository declaration:

```java
package com.example.library;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface BookRepository extends MongoRepository<Book, String> {

    List<Book> findByStatusOrderByCreatedAtDescIdDesc(String status);

    List<Book> findByStatusOrderByTitleAscIdAsc(String status);

    List<Book> findTop3ByStatusOrderByViewCountDescIdAsc(String status);
}
```

Spring Data splits each method name into two parts:

1. **Filter section** `findByStatus`: matches documents whose `status` property equals the argument.
2. **Static sort section** starting with `OrderBy`: specifies one or more properties and directions `Asc`/`Desc`.

Examples:

```java
List<Book> newest =
    bookRepository.findByStatusOrderByCreatedAtDescIdDesc("PUBLISHED");

List<Book> alphabetical =
    bookRepository.findByStatusOrderByTitleAscIdAsc("PUBLISHED");

List<Book> mostViewed =
    bookRepository.findTop3ByStatusOrderByViewCountDescIdAsc("PUBLISHED");
```

On the sample dataset, each call means:

| Method | Criterion | Expected ID order |
| --- | --- | --- |
| `findByStatusOrderByCreatedAtDescIdDesc` | Newest first; ties broken by descending ID | `BK-004`, `BK-003`, `BK-002`, `BK-001` |
| `findByStatusOrderByTitleAscIdAsc` | Ascending by title; ties broken by ascending ID | Depends on MongoDB string/collation rules |
| `findTop3ByStatusOrderByViewCountDescIdAsc` | Top 3 most-viewed PUBLISHED books | `BK-004`, `BK-002`, `BK-003` |

In `mongosh`, the query for "newest first":

```javascript
db.books.find({ status: "PUBLISHED" })
  .sort({ created_at: -1, _id: -1 })
```

Sorting targets the expected fields because:

- `OrderByCreatedAt` resolves to **Java property** `createdAt`, not literal `created_at` in the method name.
- `Desc` means descending; `Asc` means ascending.
- Multiple keys chain sequentially in the method name: `CreatedAtDescIdDesc`.
- `findTop3By...` adds a limit of at most three sorted results.

### Common Method-Naming Mistakes

```java
// Correct: OrderBy uses the Java property name.
List<Book> findByStatusOrderByCreatedAtDesc(String status);

// Wrong intent: writing snake_case BSON field name in the method name.
// List<Book> findByStatusOrderByCreated_atDesc(String status);

// Wrong intent: referencing a property that does not exist on the entity.
// List<Book> findByStatusOrderByPublicationDateDesc(String status);
```

Spring Data must resolve every property path cleanly. If a property cannot be found, the application typically fails during repository initialization or query creation. Never conclude Spring Data can derive a valid MongoDB query merely because a method compiles in Java.

**Choose static `OrderBy` when every caller requires the exact same order.** If a UI lets users pick from several sort options, declaring a separate method for each leads to a bloated, hard-to-maintain interface.

## 4. Dynamic Sorting with a `Sort` Parameter

When requirements call for options like "Newest", "Title A–Z", or "Most Viewed", declare a method accepting `org.springframework.data.domain.Sort`:

```java
import java.util.List;
import org.springframework.data.domain.Sort;

public interface BookRepository extends MongoRepository<Book, String> {

    List<Book> findByStatus(String status, Sort sort);
}
```

This is a **variation of `BookRepository` from the previous section**. In a real project, keep all methods inside one interface rather than creating two interfaces with the same name.

Invocation:

```java
import org.springframework.data.domain.Sort;

Sort newestSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Sort titleSort = Sort.by(
    Sort.Order.asc("title"),
    Sort.Order.asc("id")
);

Sort popularSort = Sort.by(
    Sort.Order.desc("viewCount"),
    Sort.Order.asc("id")
);

List<Book> newest =
    bookRepository.findByStatus("PUBLISHED", newestSort);

List<Book> byTitle =
    bookRepository.findByStatus("PUBLISHED", titleSort);

List<Book> popular =
    bookRepository.findByStatus("PUBLISHED", popularSort);
```

**The same repository method** produces multiple sort orders. Keys and directions live in the `Sort` object passed at runtime.

Several handy ways to construct `Sort`:

```java
Sort descendingByTime = Sort.by("createdAt").descending();

Sort ascendingByTitle = Sort.by("title").ascending();

Sort multiKey = Sort.by(Sort.Order.desc("viewCount"))
    .and(Sort.by(Sort.Order.asc("id")));

Sort unspecified = Sort.unsorted();
```

`Sort.unsorted()` requests no specific order. It **does not mean** MongoDB will return documents in insertion or `_id` order. Whenever results are paginated or require stable presentation order, pass an explicit `Sort`.

### Comparing `OrderBy` and `Sort`

| Criterion | `OrderBy` in method name | Dynamic `Sort` |
| --- | --- | --- |
| Where order is defined | In the Java method name | In the argument at call time |
| Flexibility across requests | Low, requires extra methods | High, built from validated requests |
| Quick readability of method intent | Clear for a few keys | Clear if builder/variable names are descriptive |
| Risk of invalid property name | Caught during method parsing | Requires validating and testing sort fields |
| When to use | Screens with fixed ordering | List APIs supporting user-selected sorting |

**Avoid mixing static `OrderBy` with dynamic `Sort` unless you have verified precedence and combination rules in your framework version.** When callers control sorting, declare a method accepting `Sort` without `OrderBy` in its name to prevent confusion.

## 5. Combining `Sort` with `Pageable` to Bound Results

`Sort` alone **does not limit the number** of returned documents. In a list API, bound returned records on the database side. Spring Data supports `Pageable`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import java.util.List;

public interface BookRepository extends MongoRepository<Book, String> {

    List<Book> findByStatus(String status, Sort sort);

    Page<Book> findByStatus(String status, Pageable pageable);
}
```

Requesting the first page of size two, sorted newest first:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Pageable firstPage = PageRequest.of(0, 2, sort);

Page<Book> result =
    bookRepository.findByStatus("PUBLISHED", firstPage);

List<Book> content = result.getContent();
long total = result.getTotalElements();
boolean hasNext = result.hasNext();
```

With the demo data in Section 2, `PUBLISHED` books sorted by `createdAt DESC, id DESC` are:

| Sorted position | ID | Timestamp |
| --- | --- | --- |
| 1 | `BK-004` | `2026-11-10T08:00:00Z` |
| 2 | `BK-003` | `2026-11-10T08:00:00Z` |
| 3 | `BK-002` | `2026-11-04T08:00:00Z` |
| 4 | `BK-001` | `2026-11-01T08:00:00Z` |

Therefore:

- Page `0`, size `2`: `BK-004` and `BK-003`.
- Page `1`, size `2`: `BK-002` and `BK-001`.
- `totalElements` is `4` when the database contains only the sample dataset with no new writes.

Semantically equivalent in MongoDB:

```javascript
db.books.find({ status: "PUBLISHED" })
  .sort({ created_at: -1, _id: -1 })
  .skip(0)
  .limit(2)
```

**`PageRequest` numbers pages starting at 0**, and page size must be greater than 0. `Page<Book>` includes total element counts, so Spring Data may run an extra count query. When the UI only needs "is there a next page?" without totals, consider `Slice` or fetching one extra element depending on repository support.

`findAll(Pageable)` can also be called directly on `MongoRepository`, without a `status` filter. When business rules allow viewing only published books, **use `findByStatus(..., pageable)`** instead of loading everything and filtering in Java.

## 6. Why Add a Tie-Breaker Key for Deterministic Ordering?

Both `BK-003` and `BK-004` share the same `created_at`. Querying only:

```javascript
db.books.find({ status: "PUBLISHED" })
  .sort({ created_at: -1 })
```

**leaves the order between documents with equal timestamps undefined**. Their relative order can shift depending on execution plans, indexes, or data updates.

Add a unique tie-breaker key, usually `_id`:

```javascript
db.books.find({ status: "PUBLISHED" })
  .sort({ created_at: -1, _id: -1 })
```

and express it in Java:

```java
Sort stableNewest = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
```

Now, **for an unchanging dataset**, ordering is completely deterministic. Since `_id` is unique within a collection, it makes a convenient tie-breaker.

Important caveat: a tie-breaker makes ordering deterministic, yet **does not turn multi-request pagination into an immutable snapshot**. If new books are inserted between page 1 and page 2, `skip`-based pagination can still duplicate or skip items. For infinite scroll feeds, consider cursor/keyset pagination.

Example of fetching the next page after a last item's `created_at` and `_id`:

```javascript
const lastCreatedAt = ISODate("2026-11-10T08:00:00Z");
const lastId = "BK-003";

db.books.find({
  status: "PUBLISHED",
  $or: [
    { created_at: { $lt: lastCreatedAt } },
    {
      created_at: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
})
.sort({ created_at: -1, _id: -1 })
.limit(2)
```

The cursor must come from the **last document of the previous page**, carry every sort key, and keep filters like `status` consistent across pages. The pattern above applies when both `created_at` and `_id` sort descending. With dynamic sorting, the cursor comparison must adapt to each sort direction; a single expression cannot serve every sort direction.

## 7. Guarding Dynamic `Sort` from Untrusted User Input

A real API might receive parameters like:

```text
GET /books?status=PUBLISHED&sort=newest&page=0&size=20
GET /books?status=PUBLISHED&sort=title&page=0&size=20
GET /books?status=PUBLISHED&sort=popular&page=0&size=20
```

Never take a user-supplied string and pass it straight into `Sort.by(userValue)`. Not every property should be sortable: large fields, sensitive fields, unindexed paths, or typos can cause errors, slow scans, or unintended data exposure.

A simple safeguard is **allowing only predefined business sort options**:

```java
package com.example.library;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class BookListingService {

    private final BookRepository books;

    public BookListingService(BookRepository books) {
        this.books = books;
    }

    public Page<Book> list(
            String status,
            String sortKey,
            int page,
            int size) {
        if (status == null || status.isBlank()) {
            throw new IllegalArgumentException("Missing status");
        }
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Invalid page request");
        }

        String selected = sortKey == null ? "newest" : sortKey;

        Sort sort = switch (selected) {
            case "newest" -> Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
            );
            case "title" -> Sort.by(
                Sort.Order.asc("title"),
                Sort.Order.asc("id")
            );
            case "popular" -> Sort.by(
                Sort.Order.desc("viewCount"),
                Sort.Order.asc("id")
            );
            default -> throw new IllegalArgumentException(
                "Unsupported sort option: " + selected
            );
        };

        return books.findByStatus(
            status,
            PageRequest.of(page, size, sort)
        );
    }
}
```

This service uses Java 17+ `switch` expressions. It caps page size at 100, prevents clients from specifying arbitrary MongoDB paths, and always appends ID as a tie-breaker.

Accepting `status` from requests must also obey **business authorization rules**: if callers may only view published books, the service or authorization layer must enforce that status rather than trusting the request blindly. In multi-tenant apps, filter by `tenantId` and enforce permissions in the query. `Sort` is an ordering tool, **not an authorization mechanism**.

### If the API Accepts Separate Field Name and Direction

Some APIs accept `sortField=createdAt&direction=desc`. Map external names (such as `created`, `title`, `views`) to an **allowlist of Java properties**, and verify `direction` is strictly `asc` or `desc`. Then construct:

```java
Sort.Direction direction =
    Sort.Direction.fromString("desc");

Sort sort = Sort.by(
    new Sort.Order(direction, "createdAt"),
    Sort.Order.desc("id")
);
```

This illustrates building from a validated `"desc"` value. If sorting by `createdAt` ascending, pick a tie-breaker order aligned with product rules; what matters is establishing **complete, consistent ordering**.

## 8. String Sorting, Casing, and Collation

Sorting by `title` does not automatically follow "Vietnamese A–Z" across all environments. MongoDB uses binary/default string comparison unless configured with **collation** to apply locale rules, case sensitivity, and diacritic strength.

For example, to sort titles in Vietnamese, a `mongosh` query can specify a collation:

```javascript
db.books.find({ status: "PUBLISHED" })
  .collation({ locale: "vi", strength: 2 })
  .sort({ title: 1, _id: 1 })
```

`locale: "vi"` selects Vietnamese rules; `strength` tunes comparison sensitivity. Always verify exact ordering on fixtures containing uppercase, lowercase, and accented characters. Never assume `OrderByTitleAsc` automatically uses Vietnamese rules; it uses **the active collation**, so you may need to set collation at the query or collection level.

With `MongoTemplate`, collation can be set explicitly:

```java
import org.springframework.data.mongodb.core.query.Collation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.domain.Sort;

Query query = Query.query(
    Criteria.where("status").is("PUBLISHED")
);
query.with(Sort.by(
    Sort.Order.asc("title"),
    Sort.Order.asc("id")
));
query.collation(Collation.of("vi"));
query.limit(20);
```

Query collation and index collation must **match** for an index to serve the sort as expected. If Vietnamese sorting is frequent, build an index with matching collation and inspect `explain`. Do not assume an ordinary default-collation index optimizes queries using a custom collation.

### Null, Missing Fields, and Mixed BSON Types

If some documents lack `title` or `created_at`, MongoDB still places them according to BSON comparison order. Missing fields and `null` fields must be accounted for in business rules; `Sort` does not fill in fallback values.

In particular, mixing BSON Date and String in `created_at` breaks "newest" ordering. Enforce schema consistency, migrate legacy records, and test against actual BSON documents.

## 9. Designing Indexes So Sorting Does Not Become a Bottleneck

Queries with `sort` can **require extra work in MongoDB**. Depending on filters, document count, and available indexes, MongoDB either reads in index order or performs an extra in-memory sort. On large datasets, unindexed sorts consume heavy memory or run slowly.

Suppose the primary query is:

```javascript
db.books.find({ status: "PUBLISHED" })
  .sort({ created_at: -1, _id: -1 })
  .limit(20)
```

A candidate index:

```javascript
db.books.createIndex(
  { status: 1, created_at: -1, _id: -1 },
  { name: "books_status_created_id_desc" }
)
```

In this setup:

- `status` is an **equality** filter, typically placed before sort keys.
- `created_at` and `_id` match the requested sort directions.
- MongoDB can scan `PUBLISHED` books in order without sorting a large set in memory.

If the workload also commonly uses "most viewed", another index may be considered:

```javascript
db.books.createIndex(
  { status: 1, view_count: -1, _id: 1 },
  { name: "books_status_views_id" }
)
```

For `title` sorting, a dedicated index may fit, especially matching the string collation used by the query. **Do not create every possible index just because the UI offers many sort options**: each index uses memory and disk while slowing inserts, updates, and deletes.

### Inspecting the Query Plan

In `mongosh`:

```javascript
db.books.find({ status: "PUBLISHED" })
  .sort({ created_at: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Check these indicators:

| Component | Question to answer |
| --- | --- |
| `winningPlan` | Which plan did MongoDB choose? |
| `IXSCAN` vs. `COLLSCAN` | Did it use an index or scan the collection? |
| Sort stage such as `SORT` | Was an extra non-indexed sort stage needed? |
| `totalKeysExamined` | How many index keys were scanned? |
| `totalDocsExamined` | How many documents were read? |
| `nReturned` | How many documents were returned after filter/limit? |
| `executionTimeMillis` | How long did this run take? |

Never declare an index good merely because `IXSCAN` appears. If a query scans a huge number of keys to return 20 documents, efficiency can still be poor. Conversely, `COLLSCAN` on a five-document demo collection says nothing about performance at millions of documents. Measure with representative volume and load, plus end-to-end application latency.

### Index Field Names Differ from Java Property Names

In the repository:

```java
Sort.by(Sort.Order.desc("createdAt"));
```

In `mongosh`:

```javascript
db.books.createIndex({ created_at: -1 })
```

Do not accidentally index `{ createdAt: -1 }` if documents actually store `created_at`. Even when declaring index annotations on entities, verify actual indexes in MongoDB and your Spring Data/Spring Boot auto-index configuration: entity annotations alone do not guarantee indexes are created in every environment.

## 10. `MongoTemplate` and Sorting in Aggregations

When filters cannot be expressed cleanly as derived method names or involve multiple optional criteria, use `MongoTemplate`:

```java
package com.example.library;

import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class BookQueryService {

    private final MongoTemplate template;

    public BookQueryService(MongoTemplate template) {
        this.template = template;
    }

    public List<Book> recentPublished(int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Invalid limit");
        }

        Query query = Query.query(
            Criteria.where("status").is("PUBLISHED")
        );
        query.with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        ));
        query.limit(limit);

        return template.find(query, Book.class);
    }
}
```

When `find(query, Book.class)` receives entity mapping metadata, Spring Data translates property names: `createdAt` maps to `created_at` and `id` maps to `_id`. With raw driver calls or `mongosh`, use actual BSON field names.

In aggregations, use `$sort` and `$limit` stages:

```javascript
db.books.aggregate([
  { $match: { status: "PUBLISHED" } },
  { $sort: { view_count: -1, _id: 1 } },
  { $limit: 3 },
  {
    $project: {
      _id: 1,
      title: 1,
      view_count: 1
    }
  }
])
```

This is a MongoDB aggregation pipeline, not a derived method name. Ordering `$match`, `$sort`, and `$limit` filters first and then retrieves a few top sorted items. The aggregation optimizer can reorder stages where safe, yet never assume every aggregation automatically uses your preferred index; verify with `explain` and real data.

### Nested Fields and References

If `Book` embeds an `author` object with a `name` property, you can sort by nested property paths such as `Sort.by("author.name")` when mapping supports it. However, **sorting by fields on documents in another collection does not auto-join** via derived methods or `Sort`. When the sort key lives in a referenced collection, evaluate `$lookup`, two-step queries, or denormalized sort fields with an explicit sync policy.

## 11. Sorting in Reactive MongoDB

In reactive applications, `ReactiveMongoRepository` and `ReactiveMongoTemplate` also accept `Sort`, while returning `Flux<T>`/`Mono<T>` instead of `List<T>` or `Optional<T>`.

Example:

```java
package com.example.library;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveBookRepository
        extends ReactiveMongoRepository<Book, String> {

    Flux<Book> findByStatusOrderByCreatedAtDescIdDesc(String status);

    Flux<Book> findByStatus(String status, Sort sort);

    Flux<Book> findByStatus(String status, Pageable pageable);
}
```

Fetching a sorted page of published books on the server:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import reactor.core.publisher.Flux;

Flux<Book> firstTwenty = reactiveBookRepository.findByStatus(
    "PUBLISHED",
    PageRequest.of(
        0, 20,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        )
    )
);
```

Once subscribed, the stream executes the paged, sorted MongoDB query. `Flux` does not carry total element counts like `Page`; if totals are required, pair it with an appropriate count query. Never run `findAll().collectList()` to load an entire collection just to pick 20 items in Java.

**Reactive does not eliminate database work.** Without supporting indexes or bounded result sets, MongoDB still bears the sorting and scanning cost. Also never call `block()` on request-handling event-loop threads.

## 12. Testing Actual Ordering

To verify a derived method with `OrderBy` works properly, use **real MongoDB in integration tests**, such as a test MongoDB instance or Testcontainers. Test both distinct sort keys and tied sort keys.

To simplify fixture creation, add this constructor to `Book` in Section 2:

```java
public Book(
        String id, String title, String status,
        Instant createdAt, long viewCount, String authorName) {
    this.id = id;
    this.title = title;
    this.status = status;
    this.createdAt = createdAt;
    this.viewCount = viewCount;
    this.authorName = authorName;
}
```

The test example below runs on an **isolated test-only database**. Calling `deleteAll()` is destructive and must never run against shared or production databases.

```java
package com.example.library;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class BookSortingRepositoryTest {

    @Autowired
    BookRepository books;

    @BeforeEach
    void insertIntoIsolatedTestDatabase() {
        books.deleteAll();
        Instant sameTime = Instant.parse("2026-11-10T08:00:00Z");
        books.insert(List.of(
            new Book("BK-001", "A", "PUBLISHED",
                Instant.parse("2026-11-01T08:00:00Z"), 80, "An"),
            new Book("BK-002", "B", "PUBLISHED",
                Instant.parse("2026-11-04T08:00:00Z"), 140, "Bình"),
            new Book("BK-003", "C", "PUBLISHED",
                sameTime, 120, "An"),
            new Book("BK-004", "D", "PUBLISHED",
                sameTime, 260, "Chi"),
            new Book("BK-005", "E", "DRAFT",
                Instant.parse("2026-11-12T08:00:00Z"), 0, "Bình")
        ));
    }

    @Test
    void staticOrderByUsesCreatedAtThenId() {
        assertThat(books
            .findByStatusOrderByCreatedAtDescIdDesc("PUBLISHED"))
            .extracting(Book::getId)
            .containsExactly("BK-004", "BK-003", "BK-002", "BK-001");
    }

    @Test
    void dynamicSortByViewsCanUseDifferentOrder() {
        Sort sort = Sort.by(
            Sort.Order.desc("viewCount"),
            Sort.Order.asc("id")
        );

        assertThat(books.findByStatus("PUBLISHED", sort))
            .extracting(Book::getId)
            .containsExactly("BK-004", "BK-002", "BK-003", "BK-001");
    }

    @Test
    void pagedSortKeepsStableOrder() {
        Page<Book> page = books.findByStatus(
            "PUBLISHED",
            PageRequest.of(0, 2, Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
            ))
        );

        assertThat(page.getContent())
            .extracting(Book::getId)
            .containsExactly("BK-004", "BK-003");

        assertThat(page.getTotalElements()).isEqualTo(4);
        assertThat(page.hasNext()).isTrue();
    }
}
```

`findByStatusOrderByCreatedAtDescIdDesc` and `findByStatus` must both be declared in `BookRepository` as shown earlier. `@DataMongoTest` configures data-layer test slicing, but **does not automatically ensure a safe test MongoDB is running**; configure appropriate test infrastructure for your project.

Additional cases worth testing:

1. Multiple books sharing `createdAt` to verify the `id` tie-breaker.
2. Missing, null, or wrong-BSON-type `created_at` fields in legacy documents.
3. Rejected sort parameters outside the allowlist and out-of-bounds page sizes.
4. Sorting Vietnamese titles with vs. without target collation.
5. Comparing query plans with and without matching indexes on representative datasets.
6. Inserting records between consecutive page requests to verify the API's pagination behavior.

## 13. Common Errors

| Symptom | Common cause | Solution |
| --- | --- | --- |
| `OrderBy` method fails to initialize | Property name in derived method does not exist | Use the exact Java property name; check query parsing stack trace |
| Sorting by `createdAt` while MongoDB stores `created_at` | Mixing Java and BSON names in raw queries | Use `createdAt` in repositories; use `created_at` in `mongosh` |
| Order fluctuates on equal timestamps | Sorted only by `createdAt` with no tie-breaker | Append `id` or another unique field |
| `findByStatus(..., Sort)` returns too many books | `Sort` does not limit counts | Use `Pageable`, `Top`, or query limits |
| User-supplied sort causes unwanted queries | Unvalidated property name or direction | Whitelist business sort options and validate page size |
| `findAll(Pageable)` leaks DRAFT books | Missing status/permission filter | Query by `status` and enforce authorization conditions |
| Deep pages are very slow | Offset/skip pagination at large offsets | Evaluate cursor/keyset pagination and run `explain` |
| Title sort ignores Vietnamese ordering | Missing collation or mismatched index collation | Set matching collation on query and index |
| Sort is slow despite an index | Index key order mismatches filter/sort | Check `winningPlan`, `totalKeysExamined`, `SORT` stage, and real workload |
| Aggregation pipeline sorts wrong field | Wrote Java property name in raw BSON | Use BSON field names in `mongosh`/raw pipelines |
| Sorting by referenced document's name fails | Derived queries do not auto-join other collections | Use `$lookup`, snapshot fields, or explicit multi-step queries |

## 14. Self-Check Exercises

**Exercise 1.** Write a derived query finding books with a given `status`, sorted descending by `createdAt` then descending by `id`.

**Solution:**

```java
List<Book> findByStatusOrderByCreatedAtDescIdDesc(String status);
```

**Exercise 2.** How can one method sort by title in one call and by view count in another?

**Solution:** Declare `findByStatus(String status, Sort sort)` and pass `Sort.by("title").ascending()` or `Sort.by("viewCount").descending()`; include tie-breaker `id` when deterministic ordering is required.

**Exercise 3.** Given 4 `PUBLISHED` books, how do you fetch the first page of the 2 newest books?

**Solution:** `findByStatus("PUBLISHED", PageRequest.of(0, 2, Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))))`.

**Exercise 4.** If two books share `created_at`, does `sort({ created_at: -1 })` guarantee which comes first?

**Solution:** No. Add `_id` as a secondary sort key whenever deterministic ordering is needed.

**Exercise 5.** The entity uses `@Field("view_count")` on `viewCount`. Which name belongs in the method name and `Sort`?

**Solution:** Use `ViewCount` in `OrderByViewCountDesc` and `"viewCount"` in `Sort`. Use `view_count` in `mongosh` or raw BSON indexes.

**Exercise 6.** Why should you never pass an arbitrary `sortField` string from an HTTP request directly into `Sort.by(sortField)`?

**Solution:** It can trigger invalid-property errors, expensive unindexed scans, or expose unintended fields. Always map through an allowlist of supported business sort options.

**Conclusion:** In Spring Data MongoDB, **`OrderBy` in method names** fits fixed ordering, whereas **dynamic `Sort`** changes keys and directions at runtime. `Pageable` pairs sorting with result limits; tie-breaker keys like `id` make ordering deterministic when primary keys match. In production, verify Java-to-BSON field mapping, validate inputs, design indexes matching filters and sorts, and test ordering against real MongoDB.
