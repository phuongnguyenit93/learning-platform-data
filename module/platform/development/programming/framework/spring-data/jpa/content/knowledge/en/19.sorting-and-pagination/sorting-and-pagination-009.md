# Stable Ordering, Tie-Breakers, and Data Changes Between Pages

## Objectives

When paginating data with Spring Data JPA, each page is a separate query. If the sort order is not uniquely deterministic, or if data changes between two calls, users can see duplicate records, skipped records, or shifted positions across pages.

Three principles must work together:

1. **Deterministic sorting:** use `ORDER BY` with enough properties to uniquely determine the order of every row.
2. **Unique tie-breaker:** append the primary key or a unique property at the end of the sort order to break ties when primary sort values are equal.
3. **Choose a pagination strategy matching data churn:** offset pagination is easy to use but sensitive to inserts/deletes before the offset; keyset pagination is more stable when continuing from the last item of the previous page, though it does not automatically create an immutable snapshot of the entire dataset.

This lesson explains how to design stable ordering, the page drift phenomenon, writing cursors across multiple sort keys, transaction effects, and a runnable Java 17+ example with Spring Boot and H2.

## 1. Why Does ORDER BY Need to Uniquely Determine Order?

SQL does not guarantee row order if a query has no `ORDER BY`. Even with `ORDER BY`, rows sharing identical values across all sort properties can still appear in any order.

Example:

```sql
select id, title, created_at
from articles
order by created_at desc;
```

If multiple articles share the same `created_at`, the database has no obligation to preserve a fixed order among those rows. One execution might return Article A before Article B; another might reverse them due to execution plans, indexes, vacuuming, data updates, or statistics changes.

During pagination, this is more dangerous than in a single-list query. The boundary between page 1 and page 2 can cut through a group of rows with the same sort key. If the order within that group shifts, a row can appear on both pages or on neither page during traversal.

## 2. Adding a Unique Tie-Breaker

Append a unique property at the end of `ORDER BY`. The primary key is a common choice:

```sql
select id, title, created_at
from articles
order by created_at desc, id desc;
```

The order means:

1. Newer articles come first by `created_at DESC`.
2. If two articles share the same timestamp, the one with the larger `id` comes first by `id DESC`.

Because `id` is the primary key, the tuple `(created_at, id)` uniquely determines the order of every row.

In Spring Data JPA, a derived query can be written as:

```java
List<Article> findByPublishedTrueOrderByCreatedAtDescIdDesc();
```

Or using `Sort`:

```java
Sort stableSort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
);

Pageable pageable = PageRequest.of(0, 20, stableSort);
Page<Article> page = repository.findByPublishedTrue(pageable);
```

`Sort` uses the entity's Java property names, not SQL column names. If the database column is `created_at`, the Java property can still be `createdAt`.

### What Characteristics Should a Tie-Breaker Have?

- **Unique:** guarantees no two rows share the entire sort key tuple.
- **Non-null:** the primary key satisfies this.
- **Stable:** its value should not change while users browse pages.
- **Consistently comparable:** the database must have deterministic comparison rules for that data type.

You do not have to use `id DESC`; `id ASC` works too. What matters is picking one fixed direction and using the same direction across queries, cursors, and every page.

## 3. Multi-Property Ordering and Tie-Breakers

Sorting can include multiple business fields before the primary key:

```sql
order by priority desc, created_at asc, id asc
```

The database compares from left to right:

- Higher priority comes first.
- If priority ties, older records come first.
- If both priority and created_at are equal, smaller ID comes first.

The primary key at the end makes the ordering unique. Using only `priority DESC, created_at ASC` still allows rows sharing both values to swap places.

For APIs allowing dynamic sorting, validate sort properties against a whitelist and always append a unique key if the caller did not already include it:

```java
Sort requested = Sort.by(Sort.Order.desc("createdAt"));
Sort stable = requested.and(Sort.by(Sort.Order.desc("id")));
Pageable pageable = PageRequest.of(pageNumber, pageSize, stable);
```

In a real application, if the client can sort by `id`, avoid appending `id` a second time. You can check `requested.getOrderFor("id")` before adding the tie-breaker. Do not allow clients to pass arbitrary property names or SQL expressions.

### Nulls and Collation Also Affect Ordering

Sort properties can be nullable or compared using a case-insensitive collation. Two values such as `"alpha"` and `"ALPHA"` may be treated as equal by the collation. Hence, a unique tie-breaker is still necessary.

Default NULL ordering differs across databases. If business rules require nulls always last or always first, define the ordering explicitly via database/dialect features or a `CASE` expression in the query. When using keyset pagination on nullable sort keys, the cursor predicate must mirror the exact same null rules; a simpler alternative is using non-null cursor fields or maintaining a normalized sort key.

## 4. Offset Pagination and Page Drift

`Pageable` normally implements offset pagination. With a page size of 3:

```java
PageRequest.of(0, 3); // rows 0-2
PageRequest.of(1, 3); // rows 3-5
PageRequest.of(2, 3); // rows 6-8
```

Databases typically use `OFFSET` and `LIMIT`, or the dialect's equivalent syntax.

Suppose the initial order is:

| Position | Record |
| ---: | --- |
| 1 | Article-10 |
| 2 | Article-09 |
| 3 | Article-08 |
| 4 | Article-07 |
| 5 | Article-06 |
| 6 | Article-05 |

The first page with page size 3 returns `Article-10`, `Article-09`, `Article-08`. Before the user requests the second page, a newer article `Article-11` is inserted at the top of the list:

| New position | Record |
| ---: | --- |
| 1 | Article-11 |
| 2 | Article-10 |
| 3 | Article-09 |
| 4 | Article-08 |
| 5 | Article-07 |
| 6 | Article-06 |
| 7 | Article-05 |

The second page still runs `OFFSET 3 LIMIT 3`, returning `Article-08`, `Article-07`, `Article-06`. `Article-08` is duplicated because it appeared on the first page before the data changed.

### Deletes Before the Offset Also Cause Skips

If a row located before the offset position is deleted after the first page is read, subsequent rows shift upward. The page-two query still skips the same number of rows, so it can skip over a record the user never saw.

### Updating a Sort Key Can Cause Duplicates or Skips

If a record's `createdAt`, `priority`, or other sorted property is updated, it can move from behind the cursor to ahead of it, or vice versa. Both offset pagination and keyset pagination can be affected by this movement.

Thus, a uniquely deterministic `ORDER BY` is a necessary condition for stable ordering within each query, but **it does not guarantee that pages fetched at different times observe the exact same dataset**.

## 5. Keyset Pagination: Continuing from the Last Row's Keys

Keyset pagination (also called seek pagination) does not skip N rows using an offset. Instead, the next page's query fetches only rows that come after the sort keys of the previous page's last record.

With the ordering:

```sql
order by created_at desc, id desc
```

Suppose the last row of the previous page has `created_at = :lastCreatedAt` and `id = :lastId`. Subsequent rows must have a sort tuple smaller than the cursor in descending order:

```sql
where created_at < :lastCreatedAt
   or (created_at = :lastCreatedAt and id < :lastId)
order by created_at desc, id desc
fetch first :pageSize rows only;
```

This is a lexicographic comparison: compare the first field first; only when equal compare the next field.

### Example with Multiple Sort Keys

With ordering `priority DESC, created_at ASC, id ASC`, the next cursor must satisfy one of the cases:

```sql
where priority < :lastPriority
   or (priority = :lastPriority and created_at > :lastCreatedAt)
   or (priority = :lastPriority
       and created_at = :lastCreatedAt
       and id > :lastId)
```

Each branch represents the first field that differs at that position and falls after the cursor in the chosen sort direction. With mixed ASC/DESC sorting, comparison operators must change accordingly for each field.

### Why Is Keyset Less Affected by Inserts Before the Cursor?

In the `createdAt DESC, id DESC` example, the cursor is at `Article-08`. If `Article-11` is inserted at the top of the list, its sort key is greater than the cursor, so it does not satisfy `createdAt < lastCreatedAt`. Articles `Article-07`, `Article-06`, and `Article-05` remain after the cursor and are returned.

Keyset prevents new rows inserted ahead of the cursor from pushing the offset and duplicating previously read items. It also avoids forcing the database to count or skip through all rows from prior pages.

## 6. Keyset Is Not a Data Snapshot

Keyset pagination reduces page drift from inserts/deletes before the current read position, but it does not freeze the dataset:

- **Inserts after the cursor:** new records can appear on the next page even though they did not exist when the first page was read.
- **Deletes after the cursor:** deleted records will no longer appear on subsequent pages.
- **Sort key updates:** a record can cross over the cursor, leading to duplicates or skips.
- **Updates to non-sort attributes:** ordering does not change, though displayed content may reflect newer versions than earlier pages.

If you need to traverse an exact dataset as of a point in time, you need a consistent snapshot mechanism, such as an appropriate transaction/snapshot isolation level within a short processing session, versioned data, or explicitly designed snapshot queries. Keeping a database transaction open across multiple HTTP requests is rarely a good option because it holds connections and snapshots open for too long.

### As-Of Timestamp Boundary

A simple approach for append-only data is fixing an `asOf` boundary on the first page:

```sql
where created_at <= :asOf
  and (
      created_at < :lastCreatedAt
      or (created_at = :lastCreatedAt and id < :lastId)
  )
order by created_at desc, id desc
```

The `created_at <= :asOf` condition excludes records created after the starting point. However, it does not prevent an older row from being deleted or having its sort key updated; thus it is only an approximate snapshot for append-only workloads, not a full database snapshot.

### When Should You Use Immutable Sort Keys?

For feeds or lists requiring stable browsing, prefer fields assigned at creation that never change, such as an immutable `createdAt` paired with the primary key. If sorting by `updatedAt`, status, or scores that change continuously, either accept live-data semantics or use snapshots/versioning when business rules require it.

## 7. Page, Slice, and Keyset

| Type | Retrieval Mechanism | Metadata | Notes |
| --- | --- | --- | --- |
| `Page<T>` | Usually offset pagination | Content, total row count, total pages | May require a count query; separate page requests can still observe different data. |
| `Slice<T>` | Usually offset pagination | Content and `hasNext()` | Avoids total count, but still has offset page drift. |
| Keyset/cursor | Filters by values of the last row | Next cursor | Avoids deep offsets and reduces shifts from inserts ahead of cursor; requires stable sort keys. |

`Slice` does not automatically turn offset pagination into keyset pagination. If an API needs cursors, pass the last row's sort key values and use the corresponding keyset predicate.

With Spring Data, you can use `Pageable` for offset pagination or implement cursor queries with JPQL/Criteria. Some Spring Data versions support scrolling/keyset APIs for specific query types; check the documentation for your exact version and query limitations before selecting an API.

## 8. Designing a Cursor API

A cursor should contain all sort values needed to continue after the last row, not only the ID if the primary order depends on other fields.

Example logical payload:

```json
{
  "createdAt": "2025-01-08T00:00:00Z",
  "id": 3
}
```

The API can encode the cursor into an opaque token so clients do not construct predicates themselves. Best practices:

- Bind the cursor to the filter and sort used on the first page; do not allow clients to change sorting mid-stream.
- Validate and verify incoming cursors; do not trust client-tampered ID or timestamp values.
- Include all sort keys and tie-breakers in the cursor.
- Ensure timestamps preserve the exact precision stored in the database; avoid generating cursors from rounded values that differ from comparison values.
- Normalize timezones, typically using UTC/Instant.
- Consider signing or encrypting tokens to prevent tampering if the cursor contains sensitive data or query constraints.

Do not place sensitive data inside plain Base64 cursors; Base64 is encoding, not encryption or a signature.

## 9. Nulls, Timestamp Precision, and Complex Sort Keys

The keyset predicate must follow the exact same comparison rules as `ORDER BY`:

- If a sort key is nullable, represent null rank in the cursor and predicate, or normalize to a non-null value.
- If using a case-insensitive collation, cursor comparisons must follow that same collation.
- If using an expression such as `lower(title)`, the cursor must carry the sorted expression value or the query must recompute the same expression.
- When using timestamps, build the cursor from the value read back from the database. The database may store microsecond or millisecond precision even though Java `Instant` has nanoseconds.
- When sorting in mixed directions, construct the lexicographic predicate with the proper `<` or `>` operator for each field.

This lesson's example picks non-null `createdAt` and `id`, both in descending order, keeping the predicate simple and clear.

## 10. Indexes for Stable Ordering and Keyset

For a query filtering `published = true` and sorting `created_at DESC, id DESC`, a composite index can help:

```sql
create index ix_articles_published_created_id
    on articles(published, created_at desc, id desc);
```

A suitable index can help the database filter by published and read in cursor order. However, index utilization depends on the database engine, data distribution, predicates, and execution plan. DESC syntax in index definitions also varies by dialect.

Use `EXPLAIN`/execution plans with representative data to check:

- Does the database use the index for both filter and order?
- Is there a large in-memory sort or temporary file write?
- How many rows are read to return one page?
- Does the keyset query seek into the right index range?

Indexes increase storage size and write overhead. Only create indexes matching actual workloads.

## 11. Runnable Example with Java 17+, Spring Boot, and H2

The example creates articles in chronological order, where two articles share the same `createdAt`. The query sorts `createdAt DESC, id DESC`, so the larger ID comes first when timestamps match. After fetching the first page, the program inserts a new article at the top of the list and compares page two using offset against the next page using keyset.

### Project Structure

```text
stable-pagination/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/pagination/
        │   ├── StablePaginationApplication.java
        │   ├── Article.java
        │   └── ArticleRepository.java
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
    <artifactId>stable-pagination</artifactId>
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
spring.datasource.url=jdbc:h2:mem:stablepagination;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Article.java`

```java
package com.example.pagination;

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

    @Column(nullable = false, length = 120)
    private String title;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private boolean published;

    protected Article() {
    }

    public Article(String title, Instant createdAt, boolean published) {
        this.title = title;
        this.createdAt = createdAt;
        this.published = published;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

### `ArticleRepository.java`

```java
package com.example.pagination;

import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ArticleRepository extends JpaRepository<Article, Long> {
    @Query("select a from Article a "
         + "where a.published = true "
         + "order by a.createdAt desc, a.id desc")
    List<Article> findFirstPage(Pageable pageable);

    @Query("select a from Article a "
         + "where a.published = true "
         + "and (a.createdAt < :lastCreatedAt "
         + "or (a.createdAt = :lastCreatedAt and a.id < :lastId)) "
         + "order by a.createdAt desc, a.id desc")
    List<Article> findNextPage(
            @Param("lastCreatedAt") Instant lastCreatedAt,
            @Param("lastId") Long lastId,
            Pageable limit
    );
}
```

The first query uses `Pageable` to apply limit/offset with a fixed sort order. The second query uses a cursor predicate and `PageRequest.of(0, pageSize)` to limit row count without skipping an offset.

### `StablePaginationApplication.java`

```java
package com.example.pagination;

import java.time.Instant;
import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.PageRequest;

@SpringBootApplication
public class StablePaginationApplication {
    public static void main(String[] args) {
        SpringApplication.run(StablePaginationApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ArticleRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                    new Article("Article-10-A", Instant.parse("2025-01-10T00:00:00Z"), true),
                    new Article("Article-10-B", Instant.parse("2025-01-10T00:00:00Z"), true),
                    new Article("Article-09", Instant.parse("2025-01-09T00:00:00Z"), true),
                    new Article("Article-08", Instant.parse("2025-01-08T00:00:00Z"), true),
                    new Article("Article-07", Instant.parse("2025-01-07T00:00:00Z"), true),
                    new Article("Article-06", Instant.parse("2025-01-06T00:00:00Z"), true),
                    new Article("Article-05", Instant.parse("2025-01-05T00:00:00Z"), true)
            ));
            repository.flush();

            int pageSize = 3;
            List<Article> firstPage = repository.findFirstPage(PageRequest.of(0, pageSize));
            System.out.println("First page: " + titles(firstPage));

            Article cursor = firstPage.get(firstPage.size() - 1);

            // A new row is inserted before the old page boundary.
            repository.save(new Article(
                    "Article-11", Instant.parse("2025-01-11T00:00:00Z"), true));
            repository.flush();

            List<Article> offsetPageTwo = repository.findFirstPage(
                    PageRequest.of(1, pageSize));
            System.out.println("Offset page 2 after insert: " + titles(offsetPageTwo));

            List<Article> keysetPageTwo = repository.findNextPage(
                    cursor.getCreatedAt(),
                    cursor.getId(),
                    PageRequest.of(0, pageSize)
            );
            System.out.println("Keyset page 2 after insert: " + titles(keysetPageTwo));
        };
    }

    private static String titles(List<Article> articles) {
        return articles.stream()
                .map(Article::getTitle)
                .reduce((left, right) -> left + ", " + right)
                .orElse("");
    }
}
```

### Running the Program

```bash
mvn spring-boot:run
```

Stdout:

```text
First page: Article-10-B, Article-10-A, Article-09
Offset page 2 after insert: Article-09, Article-08, Article-07
Keyset page 2 after insert: Article-08, Article-07, Article-06
```

Two articles share the same `createdAt`; `id DESC` puts `Article-10-B` before `Article-10-A` because it was inserted later and has a larger ID. After `Article-11` is inserted at the top of the list, offset page 2 duplicates `Article-09`, while keyset continues after cursor `Article-09` and returns `Article-08`, `Article-07`, `Article-06`.

The example illustrates an insert before the cursor. If a row after the cursor is deleted or its sort key is modified, keyset results can still change; immutable sort keys or snapshot semantics are needed when business rules demand a fixed result set.

## 12. Testing Pagination

Integration tests should verify both ordering and behavior when data changes:

- Create multiple rows sharing the same primary sort value and confirm the tie-breaker determines order.
- Fetch the first page, insert a row ahead of the boundary, and compare the next offset page with the next keyset page.
- Delete a row before the offset and confirm the shift behavior.
- Update a row's sort key from after the cursor to before it to understand duplicate/skip risks.
- Test cursors on boundary values with matching timestamps and IDs.
- Test nullable sort keys, collation, and timestamp precision if those factors participate in ordering.
- Verify queries include full `ORDER BY` clauses and execution plans leverage the intended indexes.

Do not test only with data where every `createdAt` is distinct; tie-breakers only reveal their effect when multiple rows share the primary sort key.

## 13. Common Pitfalls

1. **Sorting only by a non-unique field:** append the primary key or a unique tie-breaker at the end.
2. **Assuming ORDER BY freezes a snapshot:** it only fixes ordering within each query; data can still change between requests.
3. **Using deep offsets on large tables:** the database may have to skip many rows; consider keyset.
4. **Using Slice and thinking page drift is gone:** Slice usually still uses offset; it only avoids the total count.
5. **Building a cursor solely from ID when sorting by multiple fields:** the cursor must contain all sort keys in exact order.
6. **Using the wrong comparison operator in the cursor predicate:** `<`/`>` direction must match ASC/DESC for each field.
7. **Sort key changes during traversal:** rows can jump across the cursor. Prefer immutable sort keys or use snapshots.
8. **Not specifying null ordering:** results and cursor predicates may differ across databases.
9. **Rounding timestamps when creating cursors:** use the value read from the database at actual precision.
10. **Assuming an asOf boundary creates a complete snapshot:** it only blocks inserts after the timestamp in suitable models; it does not prevent deletes or updates.
11. **Forgetting the tie-breaker with dynamic sorting:** append a unique key after whitelisting client sort criteria.
12. **Not checking Page count queries:** total counts can be expensive and may be read from a different snapshot than page content.

## 14. Practical Guidelines

- Every paginated query must have a uniquely deterministic `ORDER BY`.
- Append the primary key or a unique attribute as the final tie-breaker.
- Keep the exact same sort order across the first-page query, subsequent queries, and cursor.
- Use offset pagination when datasets are moderate and page numbers are an important requirement.
- Use keyset pagination for forward-scrolling flows on large datasets or frequent inserts ahead of the read position.
- Prefer non-null and immutable sort keys to minimize duplicates/skips.
- Use snapshots/versioning when you need to view the exact same dataset across multiple pages.
- Create indexes matching actual filters and sorts; verify with execution plans.
- Test with duplicate sort keys and concurrent changes.

Core takeaway: **Stable ordering requires a uniquely deterministic ORDER BY, typically achieved by adding the primary key as a tie-breaker. Offset pagination can duplicate or skip rows when data changes before the offset; keyset continues from the last row's keys and reduces page drift, though an immutable snapshot still requires a dedicated data consistency strategy.**