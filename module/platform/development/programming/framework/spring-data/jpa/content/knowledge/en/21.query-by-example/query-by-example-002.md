# Configuring Included or Ignored Properties

## Objective

When scrolling large datasets in Spring Data JPA, especially with **keyset scrolling**, the result type (projection) must provide enough properties for the framework to determine the next position. You can still select only the fields needed for the screen or processing, but you must not omit properties involved in sorting and cursor construction.

Practical rules:

- **Include** all properties used in `Sort` or `OrderBy` in the returned projection.
- **Include the primary key** (or the remaining parts of a composite primary key), because keyset scrolling requires a unique order and Spring Data appends the primary key to the ordering when needed.
- **May omit** filter-only properties, as well as large or unnecessary fields for the task, if the caller does not need to read them.
- Keep keyset properties non-null and choose indexes that match the filter conditions and sort order.

Example: a query filters by `status`, sorts by `createdAt DESC, id DESC`, and displays only `title`. A suitable projection needs `title`, `createdAt`, and `id`. `status` is only used for filtering so it does not have to appear in the projection; `body` is long content so it can also be omitted.

## 1. Why does keyset scrolling need sort properties?

The Scroll API splits large results into `Window<T>` chunks. Each window holds a batch of results and can provide a `ScrollPosition` to fetch the next batch.

With keyset scrolling, the next position is determined from the sort values of the last row in the current window. Spring Data uses those values to build the continuation condition in the subsequent query.

Suppose the order is:

```sql
order by created_at desc, id desc
```

To continue after the last row having `created_at = :lastCreatedAt` and `id = :lastId`, the query needs to compare these values against subsequent rows. Therefore, the result must expose `createdAt` and `id` so the framework can extract the cursor.

If the projection returns only `title`, the framework lacks sufficient data to construct the keyset position. Scrolling may fail during keyset extraction, even though the database can still sort by those columns.

## 2. Which properties must be included?

For a keyset-based `Window<T>`, review the following categories:

| Property type | Needed in projection? | Reason |
| --- | --- | --- |
| Property used in `OrderBy` or `Sort` | **Yes** | Values are used to build the continuation position. |
| Primary key | **Yes** | Spring Data appends the primary key or remaining parts of a composite key to guarantee unique ordering; the cursor needs to read this value. |
| Property used only in `WHERE`/predicate | Not required | The database uses it for filtering; the projection only needs it if calling code needs to read it. |
| Display or processing property | Yes if caller needs it | Select the fields required for work after fetching the window. |
| Unused large fields, e.g., `body`, `blob`, or long descriptions | Can be omitted | Avoids loading unnecessary data. |

Example entity:

```java
@Entity
public class Article {
    @Id
    private Long id;

    private String status;
    private Instant createdAt;
    private String title;
    private String body;
}
```

Query filters by `status`, sorts `createdAt DESC, id DESC`, and displays `title`. The projection should declare:

```java
public interface ArticleScrollRow {
    Long getId();
    Instant getCreatedAt();
    String getTitle();
}
```

`getId()` and `getCreatedAt()` are the cursor fields. `getTitle()` is the business field to display. `status` and `body` are omitted from the projection because they are filter-only or do not need to be read.

## 3. Configuring included properties with a projection

With an interface projection, the getters determine which properties are read:

```java
public interface ArticleScrollRow {
    Long getId();
    Instant getCreatedAt();
    String getTitle();
}
```

Spring Data generates the projection for repository results. With a closed interface projection, the framework knows the declared properties and can optimize the retrieved data.

The key point to remember is that the projection must include both groups:

1. Application properties needed for display or processing, such as `title`.
2. Technical properties needed to continue keyset scrolling, such as `createdAt` and `id`.

You can keep this projection in the repository/service layer, then map it to a public DTO containing only the display fields:

```java
public record ArticleCard(String title) {
}

ArticleCard card = new ArticleCard(scrollRow.getTitle());
```

That way, external APIs receive only `title`, while the internal projection still carries the cursor keys for proper scrolling.

### DTO projection

DTO projections also work if the constructor or record components include all required sort keys:

```java
public record ArticleScrollDto(
        Long id,
        Instant createdAt,
        String title
) {
}
```

Do not create a keyset DTO with only `title` if the query sorts by `createdAt` and `id`. The DTO must retain enough data for keyset extraction, even when those fields are not exposed in the final response.

### Nested projections and property paths

If sorting by an association property, such as `publisher.name`, the projection needs to expose that property path according to a mapping Spring Data can read. Nested projections can trigger joins or additional data loading. For keyset scrolling, prefer simple, stable, easily mapped sort keys; test the SQL and cursor extraction when using nested projections.

## 4. Which properties can be ignored?

You do not need to include every entity field in the projection. Distinguish properties used for filtering from properties used to build the cursor.

Example:

```java
Window<ArticleScrollRow> findFirst20ByStatusOrderByCreatedAtDescIdDesc(
        String status,
        KeysetScrollPosition position
);
```

- `status` is used as a filter condition rather than a sort key, so no getter is needed in `ArticleScrollRow` if the caller does not use it.
- `body` does not participate in filtering, sorting, or display, so it can be omitted.
- `createdAt` and `id` must not be omitted because they define the order and cursor.
- `title` is kept because the application needs to process or display the title.

Omitting a field from the projection does not remove it from the entity or database. It only restricts the data that the query result/projection provides to the caller. If a repository returns the full entity (`Window<Article>`), the entity may carry more properties than needed; a projection is a better fit when you want to limit read data.

### No separate exclude annotation for keyset

You typically configure inclusion/exclusion through the shape of the projection: declare getters or DTO components for needed fields and omit unnecessary ones. There is no safe way to tell keyset scrolling to ignore a sort property while expecting the framework to reconstruct a cursor from that property.

If you want to exclude a field from the public response while still needing it for the cursor, keep it in an internal projection and map it to a smaller response DTO.

## 5. Primary key and unique ordering

Keyset scrolling needs a stable order so each row has a distinct position. If sorting only by `createdAt`, multiple rows can share the same timestamp. Spring Data appends the primary key (or the remaining parts of a composite primary key) to the ordering to ensure uniqueness.

Example sort:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
);
```

Here `id` is explicitly declared as a tie-breaker. Even though the framework can append the primary key when needed, declaring the order explicitly helps readers understand the sorting rules and makes the projection easier to verify.

With a composite primary key, every required component of the primary key must be mapped and extractable to build the cursor. Do not include only part of a composite key in the projection.

## 6. Keyset properties must be non-null

Keyset filtering uses comparison operators to find rows after the cursor. How databases handle `NULL` in comparisons differs from regular values; therefore, Spring Data requires properties used for keyset/sorting to be non-null. Keyset scrolling with nullable sort properties can produce unexpected results.

Configure the schema and entity so sort keys are non-null:

```java
@Column(nullable = false, updatable = false)
private Instant createdAt;
```

Primary keys are inherently non-null. For business fields that may be null, consider:

- Using another non-null sort key.
- Normalizing the value before saving, if business rules allow.
- Using offset scrolling if keyset constraints cannot be met and nullable data is required.

Do not substitute `NULL` with a dummy value in the cursor without ensuring the `ORDER BY` query and predicates use the exact same rule.

## 7. Offset scrolling differs from keyset scrolling in projection requirements

Spring Data supports offset-based and keyset-based scrolling, both returning `Window<T>`:

| Characteristic | Offset scrolling | Keyset scrolling |
| --- | --- | --- |
| Continuation position | Number of skipped rows | Sort key values of the last row |
| Must projection expose sort keys? | Not required for keyset extraction | **Yes**, must expose all sort keys and primary key needed for the cursor |
| Deep pages | Can be expensive as the database must skip many rows | Usually more efficient with suitable indexes |
| Null in sort key | No equivalent keyset constraint | Sort/keyset properties must be non-null |
| Indexes | Helpful | Critical for taking advantage of keyset |

Offset scrolling should still have a stable sort for predictable ordering. However, the projection rule requiring cursor fields is specific to keyset scrolling.

### Starting and continuing scroll

With offset, you can start with `ScrollPosition.offset()`. With keyset, start with `ScrollPosition.keyset()`. The position returned by `Window.positionAt(index)` is the position of that element; the next query continues after the selected element.

Do not confuse `ScrollPosition.offset()` with `ScrollPosition.offset(0L)`: one represents the starting point before the first element, while the other identifies the element at offset 0. Because scroll positions have exclusive semantics, using the wrong initial position can skip the first element.

## 8. Window and Stream serve two data consumption patterns

`Window<T>` fits when an application needs to process data in batches and resume via scroll positions. Keyset projections must contain cursor keys as covered in previous sections.

`Stream<T>` fits when you want to iterate results as a stream. A Stream does not itself provide a keyset cursor to request the next window. It can hold JDBC resources or cursors, so it must be closed and consumed inside an appropriate transaction:

```java
@Transactional(readOnly = true)
public void processPublished(String status) {
    try (Stream<ArticleTitleView> stream = repository.streamByStatus(status)) {
        stream.forEach(this::process);
    }
}
```

Do not return an open Stream out of a transaction to process it in the caller. With Stream, the projection can still declare only the fields needed; the rule requiring exposed sort keys for keyset cursor construction applies to keyset `Window`, not to every Stream.

Fetch size and batch reading capabilities also depend on the JPA provider, JDBC driver, and database configuration. A `Stream<T>` return type does not by itself guarantee every driver loads row-by-row.

## 9. Indexes and query cost

Keyset filtering performs well when the database has an index matching the filter conditions and sort order. For a query filtering by `status` and sorting by `created_at DESC, id DESC`, a composite index can help:

```sql
create index ix_articles_status_created_id
    on articles(status, created_at desc, id desc);
```

Index syntax depends on the database. Use `EXPLAIN` or execution plans to verify whether the database uses the index for both predicates and sorting.

Projections avoid reading unnecessary fields, especially large text/blob fields. However, projections do not replace indexes and do not make a keyset query efficient if the sort keys are not properly indexed.

## 10. Runnable example with Java 17+, Spring Boot, and H2

This example creates five articles. The repository scrolls two articles per window using keyset scrolling, filtering by `status` and sorting by `createdAt DESC, id DESC`. The projection returns only `id`, `createdAt`, and `title`; it omits `status` and `body`.

### Project structure

```text
keyset-projection-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/keyset/
        │   ├── KeysetProjectionApplication.java
        │   ├── Article.java
        │   ├── ArticleScrollRow.java
        │   ├── ArticleRepository.java
        │   └── ArticleReader.java
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
    <artifactId>keyset-projection-demo</artifactId>
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
spring.datasource.url=jdbc:h2:mem:keysetprojection;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Article.java`

```java
package com.example.keyset;

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

    @Column(nullable = false, length = 30)
    private String status;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @Column(nullable = false, length = 120)
    private String title;

    @Column(length = 4000)
    private String body;

    protected Article() {
    }

    public Article(String status, Instant createdAt, String title, String body) {
        this.status = status;
        this.createdAt = createdAt;
        this.title = title;
        this.body = body;
    }
}
```

### `ArticleScrollRow.java`

```java
package com.example.keyset;

import java.time.Instant;

public interface ArticleScrollRow {
    Long getId();

    Instant getCreatedAt();

    String getTitle();
}
```

`id` and `createdAt` are the cursor fields. `title` is the field needed by the application. The projection does not declare `getStatus()` or `getBody()`, so the caller does not receive those fields.

### `ArticleRepository.java`

```java
package com.example.keyset;

import org.springframework.data.domain.KeysetScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ArticleRepository extends JpaRepository<Article, Long> {
    Window<ArticleScrollRow> findFirst2ByStatusOrderByCreatedAtDescIdDesc(
            String status,
            KeysetScrollPosition position
    );
}
```

This is a derived query method. Spring Data JPA's Scroll API currently does not support scrolling for string-based query methods; therefore, the example uses query derivation instead of `@Query`.

### `ArticleReader.java`

```java
package com.example.keyset;

import org.springframework.data.domain.KeysetScrollPosition;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ArticleReader {
    private final ArticleRepository repository;

    public ArticleReader(ArticleRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public void printPublishedArticles() {
        KeysetScrollPosition position = ScrollPosition.keyset();

        while (true) {
            Window<ArticleScrollRow> window =
                    repository.findFirst2ByStatusOrderByCreatedAtDescIdDesc(
                            "PUBLISHED", position);

            for (ArticleScrollRow article : window) {
                System.out.println(article.getTitle()
                        + " | " + article.getCreatedAt()
                        + " | id=" + article.getId());
            }

            if (!window.hasNext()) {
                break;
            }

            position = (KeysetScrollPosition)
                    window.positionAt(window.size() - 1);
        }
    }
}
```

`positionAt(window.size() - 1)` gets the position of the last element in the window. The next query uses that position with exclusive semantics to fetch subsequent rows. The loop runs in a read-only transaction so the persistence context and query resources are managed throughout processing.

### `KeysetProjectionApplication.java`

```java
package com.example.keyset;

import java.time.Instant;
import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class KeysetProjectionApplication {
    public static void main(String[] args) {
        SpringApplication.run(KeysetProjectionApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ArticleRepository repository, ArticleReader reader) {
        return args -> {
            repository.saveAll(List.of(
                    new Article("PUBLISHED", Instant.parse("2025-01-10T00:00:00Z"),
                            "Article-10-A", "Long body A"),
                    new Article("PUBLISHED", Instant.parse("2025-01-10T00:00:00Z"),
                            "Article-10-B", "Long body B"),
                    new Article("PUBLISHED", Instant.parse("2025-01-09T00:00:00Z"),
                            "Article-09", "Long body C"),
                    new Article("PUBLISHED", Instant.parse("2025-01-08T00:00:00Z"),
                            "Article-08", "Long body D"),
                    new Article("DRAFT", Instant.parse("2025-01-11T00:00:00Z"),
                            "Draft-11", "Not included")
            ));
            repository.flush();

            reader.printPublishedArticles();
        };
    }
}
```

### Running the program

```bash
mvn spring-boot:run
```

Stdout:

```text
Article-10-B | 2025-01-10T00:00:00Z | id=2
Article-10-A | 2025-01-10T00:00:00Z | id=1
Article-09 | 2025-01-09T00:00:00Z | id=3
Article-08 | 2025-01-08T00:00:00Z | id=4
```

The output ordering uses `createdAt DESC, id DESC`. Two articles with the same timestamp are distinguished by ID. The `Draft-11` record does not appear because it is filtered by `status`; the projection does not need to return `status`. `body` is also not returned because the caller did not declare a getter for that field.

## 11. Common mistakes

1. **Projection only has display fields:** if sort keys are missing, keyset extraction can fail. Include all sort properties and the primary key in the projection.
2. **Omitting `id` because the framework adds the tie-breaker automatically:** the framework can add the primary key to the ordering; the projection still needs to expose the values needed for the cursor.
3. **Mechanically including filter-only fields in the projection:** fields used only in predicates can be omitted if the caller does not need to read them.
4. **Using nullable sort keys:** keyset comparisons can skip rows or return unexpected results. Use non-null sort keys.
5. **Sort keys changing while scrolling:** a row can move across the cursor. Prefer stable, immutable sort keys.
6. **Projection omits fields needed for business logic:** omitted fields cannot be accessed from the projection. Keep necessary display or processing fields.
7. **Confusing offset scroll with keyset scroll:** offset uses the number of skipped rows; keyset uses sort key values and requires exposing them.
8. **Using string-based `@Query` for Scroll API:** scrolling with string-based query methods is not yet supported by Spring Data JPA; use derived queries, Query by Example, Querydsl, or an appropriate custom repository.
9. **Using Stream without closing:** streams can hold cursors/connections open. Use try-with-resources and a transaction.
10. **Selecting too many fields:** projections do not need the entire entity; omit unused large fields to reduce read data.
11. **Forgetting indexes for filters and sorts:** keyset scrolling needs matching indexes for good performance.
12. **Unclear separation between internal projection and public DTO:** keep cursor keys in the internal projection, then map to a response containing only fields allowed for display.

## 12. Checklist when designing a projection for keyset scroll

- [ ] Identify the exact properties in `OrderBy` or `Sort`.
- [ ] Include all sort properties in the projection.
- [ ] Include the primary key or all remaining parts of the composite key in the projection.
- [ ] Verify that sort keys are non-null in both schema and data.
- [ ] Keep only necessary display/processing fields; omit filter-only fields or large payloads if not needed for reading.
- [ ] Use a stable sort that does not change during scrolling when possible.
- [ ] Create indexes matching the filter and ordering, then inspect the execution plan.
- [ ] Test multiple windows, duplicate sort key cases, and cursors at the end of the dataset.
- [ ] Map the internal projection to a public DTO if you do not want to expose cursor fields.
- [ ] Close Streams and keep stream consumption inside a transaction.

## 13. References

- Spring Data JPA Reference — JPA Query Methods, Scrolling Large Query Results section: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data Commons Reference — Scrolling: https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html
- Spring Data Commons API — `Window` and `ScrollPosition`: https://docs.spring.io/spring-data/commons/docs/3.4.x/api/

Key takeaway: **A projection for keyset scrolling must retain all sort keys and the primary key required for the cursor, even if the caller does not display them. Filter-only fields or large payloads can be omitted if they do not need to be read. Keep cursor fields in an internal projection, map to a smaller DTO when returning externally, and ensure non-null sort keys with appropriate indexes.**