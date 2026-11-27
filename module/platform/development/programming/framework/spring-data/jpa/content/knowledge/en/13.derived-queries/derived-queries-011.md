# Top, First, OrderBy, and Limiting Result Counts

## Objectives

Spring Data JPA lets you limit the number of results directly in a query method name using `Top` or `First`, sort using `OrderBy`, or pass dynamic sorting and pagination at runtime via `Sort` and `Pageable`.

- `Top` and `First` limit the number of returned records.
- `OrderBy` declares a fixed ordering in the method name.
- `Sort` lets the caller choose the order when invoking the repository.
- `Pageable` selects the page, page size, and optionally sorting.

Limiting results reduces data transferred to the application and the number of entities to hydrate. However, performance still depends on filter conditions, ordering, indexes, and the database execution plan.

## 1. Top and First in query method names

`Top` and `First` are result-limiting keywords placed in the subject part of a query method, before `By`.

```java
List<Article> findTop5ByCategory(String category);
List<Article> findFirst5ByCategory(String category);
Optional<Article> findFirstByCategory(String category);
```

`Top` and `First` have the same result-limiting meaning. A number can follow the keyword; if omitted, the default limit is one result.

| Method | Limit |
| --- | ---: |
| `findTopByCategory(...)` | 1 |
| `findFirstByCategory(...)` | 1 |
| `findTop3ByCategory(...)` | 3 |
| `findFirst10ByCategory(...)` | 10 |

The limit is applied in the database query, so the provider may emit `LIMIT`, `FETCH FIRST`, `TOP`, or equivalent syntax depending on the dialect. The application receives at most the requested number of rows.

### Choosing the return type

- `List<Article>` or a collection: receives at most N elements, may be empty.
- `Optional<Article>`: suitable with `First` without a number or a limit of one; no matching record yields `Optional.empty()`.
- `Article`: can be used when the API allows missing results to be represented as `null`, though `Optional` is usually clearer.

Example:

```java
Optional<Article> newest = repository
        .findFirstByCategoryOrderByPublishedAtDescIdDesc("BOOK");
```

If a method returns a single entity or `Optional` without a limit of one, and the query actually returns multiple rows, Spring Data may throw `IncorrectResultSizeDataAccessException`. Use `First`/`Top` when business logic genuinely wants to select a single result under a deterministic order.

## 2. OrderBy: fixed sorting in the method name

`OrderBy` lets you declare sorting directly in the method name. Following `OrderBy` is the entity's Java property and the direction `Asc` or `Desc`.

```java
List<Article> findTop3ByCategoryOrderByPublishedAtDesc(String category);
```

This method finds articles in a category, sorts `publishedAt` descending, and returns at most three articles.

### Sorting by multiple properties

When two records share the same value on the primary property, add a secondary property so the order is deterministic:

```java
List<Article> findTop3ByCategoryOrderByViewsDescIdDesc(String category);
```

The order is `views DESC`, then `id DESC`. If you sort only by `views`, two articles with the same view count may swap positions across runs because databases do not guarantee the order of rows with tied sort keys.

With pagination, deterministic sorting is especially important. If the ordering is non-unique, a record can appear on multiple pages or be skipped when data changes between page requests.

### Properties in OrderBy are Java names

Spring Data parses entity properties, not SQL column names. If an entity has `publishedAt` while the database column is `published_at`, the method still uses `OrderByPublishedAtDesc`.

## 3. Sort: dynamic sorting at call time

If the sort order depends on UI input or the caller, declare a `Sort` parameter:

```java
List<Article> findTop5ByCategory(String category, Sort sort);
```

The caller selects the order:

```java
Sort sort = Sort.by(
        Sort.Order.desc("publishedAt"),
        Sort.Order.desc("id")
);

List<Article> latest = repository.findTop5ByCategory("BOOK", sort);
```

`Sort.Order` uses entity property names. You can pass `Sort.unsorted()` when no dynamic sorting is needed. Restrict allowed sort fields in the API layer; do not pass arbitrary client-supplied strings directly as sort properties without validation.

`Sort` does not limit result counts. If you need both sorting and limiting, combine `Sort` with `Top`/`First` as shown above.

### Static OrderBy vs. dynamic Sort

`OrderBy` fits when ordering is a fixed part of business logic, such as always picking the newest record. `Sort` fits when the caller may choose the order. Using one clear source of sorting keeps APIs readable and avoids surprises from combining multiple sort rules.

## 4. Pageable: pagination with flexible page size

`Pageable` holds the page number, page size, and optionally `Sort`. A repository can declare:

```java
Page<Article> findByCategory(String category, Pageable pageable);
```

Caller:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("publishedAt"), Sort.Order.desc("id"))
);

Page<Article> page = repository.findByCategory("BOOK", pageable);
```

`PageRequest.of(0, 20, ...)` retrieves the first page with up to 20 rows. Page numbers are zero-based.

### Page and Slice

| Return type | Information | Typical cost |
| --- | --- | --- |
| `Page<T>` | Page content, total row count, and total pages | May execute an extra count query to get exact totals |
| `Slice<T>` | Page content and `hasNext()` | Usually only fetches one extra row to check if more data exists, no total count needed |
| `List<T>` with `Pageable` | Page content only | Does not return totals; suitable when caller only needs a chunk of data |

Example using Slice:

```java
Slice<Article> findByCategoryAndActiveTrue(String category, Pageable pageable);
```

If the UI does not need to display total page counts, `Slice` avoids an expensive count query. `Page` fits when exact totals are needed for display or page navigation.

### Combining Top/First with Pageable

Spring Data supports result limiting and pagination together in eligible query methods. When combined, pagination is applied within the limited result set. This can be useful for a capped window of results, though you should verify total page/count query semantics on your Spring Data JPA version.

In typical APIs, choose `Top`/`First` when you need a fixed maximum count and choose `Pageable` when callers traverse results page by page. If both are needed, write integration tests verifying pages, totals, and generated SQL.

## 5. SQL and execution cost

Example query:

```java
List<Article> findTop3ByCategoryOrderByViewsDescIdDesc(String category);
```

Conceptual SQL might resemble:

```sql
select a.id, a.title, a.category, a.views
from articles a
where a.category = ?
order by a.views desc, a.id desc
fetch first 3 rows only;
```

Limit syntax depends on the database. SQL Server may use `TOP`, PostgreSQL/MySQL typically use `LIMIT`, while some databases use `FETCH FIRST` or other syntax. Hibernate chooses the syntax based on the dialect.

### Limiting results does not automatically make a query cheap

Top 3 only asks to return at most three rows. The database must still find matching rows and determine the top three according to the sort order. Without a suitable index, the database may have to scan many rows and sort them before returning three rows.

With filter `category` and sort `views DESC, id DESC`, a composite index on these columns can help:

```sql
create index ix_articles_category_views_id
    on articles(category, views desc, id desc);
```

Index syntax and support for DESC ordering depend on the database engine. Use `EXPLAIN` or execution plans to verify. Indexes speed up reads but increase storage and INSERT/UPDATE/DELETE overhead.

### Offset pagination can be expensive

For deep pages, the database may have to skip many rows before returning the requested page. For example, page 500 with page size 20 may need to process a large number of preceding rows depending on the execution plan.

When traversing large datasets in a stable order, consider keyset pagination or scrolling APIs supported in applicable Spring Data versions. Keyset pagination uses the last record's values from the previous page as the starting point for the next page instead of skipping a large offset.

## 6. Choosing a method based on requirements

| Need | Suitable method |
| --- | --- |
| Get the single latest article | `findFirstBy...OrderByPublishedAtDescIdDesc` |
| Get up to 5 popular articles | `findTop5By...OrderByViewsDescIdDesc` |
| Caller chooses sort order, limit 5 | `findTop5ByCategory(category, sort)` |
| Get an arbitrary page and need total count | `findByCategory(category, pageable)` returning `Page` |
| Get a page and only need to know if a next page exists | Query returning `Slice` |
| Get a small unpaginated list | `List` with `Top`/`First` |

## 7. Correctness notes

1. **Always sort when picking top or first has business significance.** Without `OrderBy` or `Sort`, databases do not guarantee which record comes first.
2. **Add a unique tie-breaker.** For instance, sort by `publishedAt DESC, id DESC` for stable ordering when timestamps collide.
3. **Mind nulls in sort properties.** Null ordering can differ between databases; if consistent results are needed, define explicit null rules or normalize data.
4. **Do not use Top as a substitute for filtering.** Limiting returned rows does not guarantee efficient filtering; proper indexes are still needed.
5. **Do not load everything and call `subList` in Java.** Push limits down to the repository so the database caps the results.
6. **Choose Page only when totals are needed.** Count queries can carry significant cost on large tables.
7. **Do not assume sorting uses SQL column names.** Method derivation and `Sort` use entity Java properties.
8. **Account for data changing between pages.** Offset pagination can skip or duplicate rows if records are inserted/deleted while a user pages through; stable sorting and appropriate snapshots/transactions help reduce risk.

## 8. Runnable example with Java 17+, Spring Boot, and H2

This example saves articles and retrieves the top 3 by view count, then fetches the first page. The project uses Spring Boot 3.4.5, Java 17, and an H2 in-memory database.

### Project structure

```text
top-first-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/topfirst/
        │   ├── TopFirstApplication.java
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
    <artifactId>top-first-demo</artifactId>
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
spring.datasource.url=jdbc:h2:mem:topfirst;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Article.java`

```java
package com.example.topfirst;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "articles")
public class Article {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 160)
    private String title;

    @Column(nullable = false, length = 40)
    private String category;

    @Column(nullable = false)
    private int views;

    protected Article() {
    }

    public Article(String title, String category, int views) {
        this.title = title;
        this.category = category;
        this.views = views;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public int getViews() {
        return views;
    }
}
```

### `ArticleRepository.java`

```java
package com.example.topfirst;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ArticleRepository extends JpaRepository<Article, Long> {
    List<Article> findTop3ByCategoryOrderByViewsDescIdDesc(String category);

    Optional<Article> findFirstByCategoryOrderByViewsDescIdDesc(String category);

    List<Article> findTop3ByCategory(String category, Sort sort);

    Page<Article> findByCategory(String category, Pageable pageable);
}
```

### `TopFirstApplication.java`

```java
package com.example.topfirst;

import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@SpringBootApplication
public class TopFirstApplication {
    public static void main(String[] args) {
        SpringApplication.run(TopFirstApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ArticleRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                    new Article("Intro to JPA", "BOOK", 120),
                    new Article("Spring Data", "BOOK", 250),
                    new Article("Hibernate", "BOOK", 180),
                    new Article("JPA in Practice", "BOOK", 250),
                    new Article("Java basics", "TOOL", 90)
            ));
            repository.flush();

            List<Article> top = repository
                    .findTop3ByCategoryOrderByViewsDescIdDesc("BOOK");
            System.out.println("Top 3: " + titles(top));

            Article first = repository
                    .findFirstByCategoryOrderByViewsDescIdDesc("BOOK")
                    .orElseThrow();
            System.out.println("First: " + first.getTitle());

            Sort sort = Sort.by(
                    Sort.Order.desc("views"),
                    Sort.Order.desc("id")
            );
            System.out.println("Dynamic top 3: "
                    + titles(repository.findTop3ByCategory("BOOK", sort)));

            Page<Article> page = repository.findByCategory(
                    "BOOK",
                    PageRequest.of(0, 2, sort)
            );
            System.out.println("Page 0: " + titles(page.getContent()));
            System.out.println("Total BOOK: " + page.getTotalElements());
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

### Running the application

```bash
mvn spring-boot:run
```

Output printed by the application:

```text
Top 3: JPA in Practice, Spring Data, Hibernate
First: JPA in Practice
Dynamic top 3: JPA in Practice, Spring Data, Hibernate
Page 0: JPA in Practice, Spring Data
Total BOOK: 4
```

Two articles share `views = 250`; `id DESC` places `JPA in Practice` ahead of `Spring Data` because it was saved later and received a higher ID. The results show `Top3` limiting to three rows, `First` picking one row per sort order, `Sort` supplying order at call time, and `Page` returning page content plus total record count.

SQL generated by Hibernate may vary in aliases and limit syntax by dialect. For the Top 3 query, the core SQL includes `category = ?`, `ORDER BY views DESC, id DESC`, and a three-row limit. For Page, there is typically a page query and a count query to calculate the total.

## 9. Verifying and optimizing in projects

1. Enable `logging.level.org.hibernate.SQL=DEBUG` in development to inspect generated SQL.
2. Use realistic data volumes and `EXPLAIN` to verify whether the database uses indexes for filtering and ordering.
3. Verify sorting includes a unique tie-breaker, especially when paginating.
4. Compare `Page` and `Slice` if the count query causes slowdowns.
5. Test behavior when sort properties are null and when records are inserted/deleted while a client paginates.
6. Benchmark on the same database engine as production; H2 results do not accurately represent PostgreSQL, MySQL, SQL Server, or Oracle.

## 10. Common mistakes

1. **Using `First` without sorting:** the first result is non-deterministic. Add `OrderBy` or pass `Sort`.
2. **Sorting by a single field that can have duplicates:** add a unique key such as `id` as a tie-breaker.
3. **Writing SQL column names in method names:** use Java properties, e.g. `publishedAt` instead of `published_at`.
4. **Limiting after loading everything:** do not fetch all rows and slice with `subList`; use `Top`/`First` or `Pageable` so the database applies the limit.
5. **Using Page even when total count is unnecessary:** consider `Slice` to avoid the count query.
6. **Assuming Top is always fast:** lacking a proper index can still force scanning and sorting many rows.
7. **Assuming Sort limits results:** Sort only orders results; Top/First or Pageable is required to limit counts.
8. **Ignoring data mutations between pages:** use stable sorting and consider keyset pagination when browsing large datasets.

## 11. Practical guidelines

- Use `Top`/`First` for fixed limits and specify the count explicitly when greater than one.
- Use `OrderBy` when ordering is a fixed business rule.
- Use `Sort` when the caller chooses ordering, while whitelisting allowed sort properties.
- Use `Page` when exact totals are needed; use `Slice` when only knowing whether a next page exists is enough.
- Always include a unique tie-breaker for top results and pagination.
- Create indexes matching actual filter and sort conditions, and confirm with execution plans.
- Test SQL and semantics when combining limits with pagination.

Core takeaway: **Top/First limits row counts; OrderBy and Sort determine order; Pageable splits results into pages. For deterministic and efficient results, sort explicitly, add a unique tie-breaker, and inspect indexes and count queries on a real database.**