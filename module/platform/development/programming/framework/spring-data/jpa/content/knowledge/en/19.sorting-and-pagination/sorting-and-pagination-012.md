# Mapping Page<Entity> to Page<DTO> and Response Contracts

In Spring Data JPA, repositories commonly return **Page<Entity>** when a query needs pagination. However, an entity is a persistence model: it may contain LAZY associations, internal fields, and database mapping details. An API typically needs only a subset of data and requires a stable JSON structure for clients to read page metadata.

The standard approach is converting **Page<Entity>** to **Page<DTO>** using the **Page.map()** method, and then converting the result into an application-defined response contract. This preserves pagination metadata while exposing only the required fields.

This lesson covers writing DTOs, mapping content without losing metadata, handling LAZY associations, when to query DTOs directly, designing stable JSON responses, controlling sort/page size, and testing the API contract.

**Example prerequisites:** the code snippets use Java 17 or later, Spring Boot 3.x, Spring Data JPA, and Spring MVC. The application requires **spring-boot-starter-data-jpa**, **spring-boot-starter-web**, a JDBC driver, DataSource, and matching schema. These are parts of a Spring Boot application, not standalone programs that can be run with just **javac**.

## 1. Why Not Return Entities Directly from an API?

An entity models data managed by the persistence context. For example, Book may have fields like:

~~~java
@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    @Enumerated(EnumType.STRING)
    private BookStatus status;

    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    private Author author;

    // constructor, getters, and other mappings
}
~~~

A list endpoint might need only ID, title, status, and creation timestamp. Returning the entity directly causes several issues:

- The API can accidentally expose internal fields when attributes are added to the entity.
- The serializer may access LAZY associations and trigger unexpected SQL queries.
- Bidirectional relationships can cause serialization cycles.
- Entities/proxies depend on the persistence provider and are not a clean JSON contract.
- Database mapping changes can unintentionally alter the API response.

A DTO (Data Transfer Object) defines the exact data sent outward. DTOs decouple the API contract from entities and allow the persistence model to evolve without forcing clients to change.

## 2. Creating a DTO for Each Element

With Java 17+, a record is a concise choice for an immutable DTO:

~~~java
package com.example.catalog.dto;

import com.example.catalog.domain.BookStatus;
import java.time.Instant;

public record BookSummary(
    Long id,
    String title,
    BookStatus status,
    Instant createdAt
) {
}
~~~

The DTO contains only the four fields needed by the list screen. It has no JPA annotations, is not a managed entity, and is not persisted via a repository.

Conversion logic can be placed in a static factory:

~~~java
package com.example.catalog.dto;

import com.example.catalog.domain.Book;

public record BookSummary(
    Long id,
    String title,
    BookStatus status,
    Instant createdAt
) {
    public static BookSummary from(Book book) {
        return new BookSummary(
            book.getId(),
            book.getTitle(),
            book.getStatus(),
            book.getCreatedAt()
        );
    }
}
~~~

The example assumes Book has corresponding getters and BookStatus is a domain enum. If the DTO requires special formatting, use a dedicated mapper such as MapStruct or a mapper class; avoid stuffing complex business logic into DTOs.

## 3. Page.map(): Converting Page<Entity> to Page<DTO>

Spring Data provides **Page.map(Function)** to convert each page element to another type:

~~~java
Page<Book> entityPage = bookRepository.findByStatus(status, pageable);

Page<BookSummary> dtoPage =
    entityPage.map(BookSummary::from);
~~~

The result is **Page<BookSummary>**. The map method transforms only the content while keeping the original page metadata, including:

- Current page number.
- Page size.
- Total elements.
- Total pages.
- First/last page and navigation flags.
- Sort information.

There is no need to build a new Page manually just to change the element type. **Page.map()** preserves accurate metadata from the original Page and does not rerun the count query.

Service example:

~~~java
package com.example.catalog.service;

import com.example.catalog.domain.Book;
import com.example.catalog.domain.BookStatus;
import com.example.catalog.dto.BookSummary;
import com.example.catalog.repository.BookRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional(readOnly = true)
    public Page<BookSummary> findByStatus(
            BookStatus status,
            Pageable pageable) {

        Page<Book> books =
            bookRepository.findByStatus(status, pageable);

        return books.map(BookSummary::from);
    }
}
~~~

Mapping runs over entities already in the Page's content. No extra queries run just from calling **map()**, provided the mapper only reads already-loaded fields and does not trigger lazy associations.

## 4. Repository Returning Page<Entity>

The repository can use a derived query:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Book;
import com.example.catalog.domain.BookStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {

    Page<Book> findByStatus(
        BookStatus status,
        Pageable pageable
    );
}
~~~

Spring Data generates the paginated content query and typically generates a count query to determine the total number of elements. For simple queries, the framework usually infers the count query automatically.

If a query has complex joins, DISTINCT, GROUP BY, or special conditions, inspect the count query. You can declare an explicit **countQuery** on **@Query** to ensure totalElements reflects the exact logical results.

Having the service receive Page<Entity> and map to DTO keeps the repository focused on the persistence model. This fits well when DTO mapping is straightforward and accessed associations are controlled.

## 5. Defining a Dedicated Response Contract for the API

Even when the service returns **Page<DTO>**, you do not have to serialize Spring Data's Page implementation directly. Page's default JSON structure can depend on the Spring Data version and Jackson serialization behavior. If clients depend on that structure, framework upgrades can alter responses unexpectedly.

An explicit response contract:

~~~java
package com.example.api.dto;

import java.util.List;
import org.springframework.data.domain.Page;

public record PageResponse<T>(
    List<T> content,
    int page,
    int size,
    int numberOfElements,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last,
    boolean hasNext,
    boolean hasPrevious,
    List<SortField> sort
) {

    public static <T> PageResponse<T> from(Page<T> source) {
        List<SortField> sortFields = source.getSort()
            .stream()
            .map(order -> new SortField(
                order.getProperty(),
                order.getDirection().name()
            ))
            .toList();

        return new PageResponse<>(
            source.getContent(),
            source.getNumber(),
            source.getSize(),
            source.getNumberOfElements(),
            source.getTotalElements(),
            source.getTotalPages(),
            source.isFirst(),
            source.isLast(),
            source.hasNext(),
            source.hasPrevious(),
            sortFields
        );
    }

    public record SortField(
        String property,
        String direction
    ) {
    }
}
~~~

Field meanings:

| Field | Meaning |
|---|---|
| **content** | List of DTOs on the current page |
| **page** | Page index, starting from 0 |
| **size** | Requested page size |
| **numberOfElements** | Actual number of elements in content |
| **totalElements** | Total elements matching the query conditions |
| **totalPages** | Total number of pages |
| **first** / **last** | Whether the current page is the first/last page |
| **hasNext** / **hasPrevious** | Whether a next/previous page exists |
| **sort** | Applied sort properties and directions |

**size** and **numberOfElements** differ: size is the page limit, whereas numberOfElements is the actual count of returned elements. The last page can have fewer elements than size.

For a query with no results, content is empty, totalElements is 0, and totalPages is 0. The page index remains the requested value, so clients should rely on metadata to handle out-of-range pages.

## 6. Converting Page<DTO> into a Response in the Controller

The controller can return the response contract instead of Page directly:

~~~java
package com.example.catalog.api;

import com.example.api.dto.PageResponse;
import com.example.catalog.domain.BookStatus;
import com.example.catalog.dto.BookSummary;
import com.example.catalog.service.BookService;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/books")
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @GetMapping
    public PageResponse<BookSummary> findBooks(
            @RequestParam BookStatus status,
            @PageableDefault(
                size = 20,
                sort = "createdAt",
                direction = Sort.Direction.DESC
            ) Pageable pageable) {

        return PageResponse.from(
            bookService.findByStatus(status, pageable)
        );
    }
}
~~~

Example request:

~~~http
GET /books?status=PUBLISHED&page=0&size=20&sort=createdAt,desc
~~~

Spring MVC can bind page, size, and sort parameters into Pageable when Spring Data web support is configured. **@PageableDefault** sets defaults when clients omit these parameters.

The controller converts Page to PageResponse using the factory method. As a result, the public JSON structure is controlled by the application rather than tied directly to the Page implementation.

## 7. Example JSON Response

A response can look like:

~~~json
{
  "content": [
    {
      "id": 101,
      "title": "Spring Data JPA",
      "status": "PUBLISHED",
      "createdAt": "2026-11-09T08:30:00Z"
    },
    {
      "id": 102,
      "title": "Hibernate Basics",
      "status": "PUBLISHED",
      "createdAt": "2026-11-08T10:15:00Z"
    }
  ],
  "page": 0,
  "size": 20,
  "numberOfElements": 2,
  "totalElements": 42,
  "totalPages": 3,
  "first": true,
  "last": false,
  "hasNext": true,
  "hasPrevious": false,
  "sort": [
    {
      "property": "createdAt",
      "direction": "DESC"
    }
  ]
}
~~~

This is an illustrative JSON response for a page with two actual elements. In this example, size is 20 while numberOfElements is 2; totalElements is 42 and totalPages is 3 only when page size and total results match the underlying data.

The contract should be documented: field names, data types, zero-based page index meaning, sort representation, and empty-result behavior. When structural changes are needed, add fields in a backward-compatible way or create an appropriate API version.

## 8. Avoiding N+1 When the Mapper Accesses LAZY Associations

A simple mapper like **BookSummary.from(book)** only reads basic fields. But if the DTO needs the author's name:

~~~java
public record BookDetails(
    Long id,
    String title,
    String authorName
) {
    public static BookDetails from(Book book) {
        return new BookDetails(
            book.getId(),
            book.getTitle(),
            book.getAuthor().getName()
        );
    }
}
~~~

If **Book.author** is LAZY, calling **getAuthor().getName()** can trigger an additional query for each Book. For a page of N books, this can turn into N+1 queries.

Three common solutions:

1. Use **@EntityGraph** to load required to-one associations alongside the content query.
2. Use a JPQL DTO projection so the database returns only the fields the DTO needs.
3. Use an appropriate query/fetch plan and inspect SQL to confirm the query count.

Example using EntityGraph for a to-one association:

~~~java
@EntityGraph(attributePaths = "author")
Page<Book> findByStatus(
    BookStatus status,
    Pageable pageable
);
~~~

The mapper can then read the author's name without issuing a separate query per book if the provider executes the fetch plan as expected. Inspect actual SQL. Be careful with collection fetches in paginated queries because collection joins can multiply rows and make pagination unpredictable.

## 9. When Should You Query DTOs Directly?

If a use case is read-only and the DTO has a clear shape, the repository can return **Page<DTO>** directly using a JPQL constructor expression.

DTO:

~~~java
package com.example.catalog.dto;

import com.example.catalog.domain.BookStatus;
import java.time.Instant;

public record BookSummary(
    Long id,
    String title,
    BookStatus status,
    Instant createdAt
) {
}
~~~

Repository:

~~~java
@Query(
    value = """
        select new com.example.catalog.dto.BookSummary(
            b.id,
            b.title,
            b.status,
            b.createdAt
        )
        from Book b
        where b.status = :status
        """,
    countQuery = """
        select count(b)
        from Book b
        where b.status = :status
        """
)
Page<BookSummary> findSummariesByStatus(
    @Param("status") BookStatus status,
    Pageable pageable
);
~~~

In this approach, the database returns only the values needed for the DTO. There is no need to load full entities and map them in Java.

Comparison of the two approaches:

| Criterion | Page<Entity>.map(...) | Direct Page<DTO> Query |
|---|---|---|
| Mapping | Performed in Java | Performed in the query |
| Entity materialization | Yes | No full entity needed |
| Reusing entity logic | Convenient | Less convenient |
| Exact column selection | Depends on projection/fetch plan | Explicit via SELECT constructor |
| Associations | Can trigger lazy queries if mapper accesses them | Can join and select only needed fields |
| Count query | Entity Page query | Requires matching count query if framework cannot infer accurately |

Use **Page.map()** when entities are already needed or mapping is simple. Use direct DTO queries when optimizing read payloads, joining multiple tables, or avoiding entity materialization.

## 10. Count Queries and Metadata After Mapping

**Page.map()** does not alter total element counts. If Page<Entity> has totalElements equal to 245, the mapped Page<DTO> still has totalElements equal to 245.

Mapping does not rerun the count query. The count query (if needed) already ran when Spring Data constructed the initial Page<Entity>.

With direct DTO queries, the count query must count the exact number of logical results. If the content query joins a collection causing an entity to appear multiple times, counting may require **count(distinct b.id)**. If the query has GROUP BY, the count query must count groups instead of total source rows.

Do not manually instantiate a Page via constructor with only content and a page request unless you have an accurate total. Doing so can lose or corrupt metadata clients rely on.

## 11. Stable Sorting and Controlling Pageable

Pagination requires a stable sort order. If you sort only by createdAt and multiple records share the same timestamp, the database can return tied rows in an indeterminate order.

Add ID as a tie-breaker:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by(Sort.Direction.DESC, "id"))
);
~~~

Sort names are normally entity properties, such as **createdAt**, not physical column names like **created_at**.

The API should enforce:

- Whether page index starts at 0 or 1.
- Maximum page size.
- List of permitted sort properties.
- Valid sort directions.
- Default ordering and a unique tie-breaker.

Do not pass arbitrary client sort strings into dynamic SQL. With native queries, dynamic sort support depends on the query and Spring Data version; declare explicit ORDER BY clauses when SQL control is needed.

## 12. Can PagedModel Replace a Custom Response Wrapper?

Spring Data provides **PagedModel** in the **org.springframework.data.web** package in supporting Spring Data versions. It is a wrapper designed to represent a Page as a more stable web DTO.

Example in versions providing this API:

~~~java
@GetMapping
public PagedModel<BookSummary> findBooks(Pageable pageable) {
    Page<BookSummary> page = bookService.findByStatus(
        BookStatus.PUBLISHED,
        pageable
    );

    return new PagedModel<>(page);
}
~~~

Another option is configuring page serialization mode **VIA_DTO** via **@EnableSpringDataWebSupport** if supported by your Spring Data version.

PagedModel is convenient when you want Spring Data's standard structure. A custom response wrapper fits when an API needs system-specific fields, metadata naming, or compatibility rules. Check the Spring Data version managed by Spring Boot before using this API; do not upgrade individual dependencies arbitrarily.

## 13. Testing Mapping and the Response Contract

You can test the service/repository to verify content and metadata preservation:

~~~java
@DataJpaTest
class BookPageMappingTest {

    @Autowired
    private BookRepository bookRepository;

    @Test
    void mapsPageContentAndKeepsMetadata() {
        Pageable pageable = PageRequest.of(0, 2);

        Page<Book> entityPage =
            bookRepository.findByStatus(
                BookStatus.PUBLISHED,
                pageable
            );

        Page<BookSummary> dtoPage =
            entityPage.map(BookSummary::from);

        assertThat(dtoPage.getContent())
            .allSatisfy(item -> assertThat(item.id()).isNotNull());

        assertThat(dtoPage.getNumber())
            .isEqualTo(entityPage.getNumber());

        assertThat(dtoPage.getSize())
            .isEqualTo(entityPage.getSize());

        assertThat(dtoPage.getTotalElements())
            .isEqualTo(entityPage.getTotalElements());

        assertThat(dtoPage.getTotalPages())
            .isEqualTo(entityPage.getTotalPages());
    }
}
~~~

To test the response contract, use **@WebMvcTest** or integration tests with MockMvc and assert JSON fields:

- content is an array of DTOs with no internal entity fields.
- page and size use the expected convention.
- totalElements and totalPages reflect results accurately.
- sort contains expected property/direction pairs.
- an empty page has empty content and zero totals.
- out-of-range pages return empty content per the chosen contract.

If the mapper accesses associations, inspect SQL counts or use Hibernate Statistics / a datasource proxy to detect N+1 queries. Checking valid JSON alone is not enough to conclude queries are efficient.

## 14. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Page<DTO> loses totalElements | Manually creating a new Page without keeping total from original Page | Use **Page.map()** |
| API leaks entity fields | Returning entities directly | Use DTOs with explicitly selected fields |
| Page JSON changes after upgrade | Serializing Page implementation directly | Use a response DTO or version-appropriate PagedModel |
| DTO mapping triggers N+1 | Mapper accesses LAZY associations | EntityGraph, DTO query, or explicit fetch plan |
| DTO contains null values | Incorrect getter/alias or mapping | Verify entity fields, constructors, and query |
| Incorrect totalElements | Count query counts join rows instead of entities | Use count distinct or accurate countQuery |
| Pages have duplicate/missing records | Unstable sort | Add a unique tie-breaker such as ID |
| Page size too large | Unbounded client parameter | Enforce maximum page size at the API |
| Sort fails at runtime | Client sends nonexistent or disallowed property | Use a sort property allowlist |
| DTO query fails constructor match | Mismatched order or types in SELECT expressions | Synchronize constructor and JPQL types |

## 15. Implementation Checklist

- [ ] Identify exact fields the API needs and create a dedicated DTO.
- [ ] Use **Page.map()** to convert Page<Entity> to Page<DTO> when Java-side mapping is appropriate.
- [ ] Do not manually reconstruct a Page if metadata can be preserved via map().
- [ ] Ensure mappers do not access unintended LAZY associations.
- [ ] Use EntityGraph or direct DTO queries when association data is needed.
- [ ] Verify count queries and totalElements with joins/grouping.
- [ ] Do not serialize entities or Page implementations directly as a long-term contract.
- [ ] Define a response contract containing page, size, content, and required metadata.
- [ ] Document zero-based page indexing and field meanings.
- [ ] Cap page size and allowlist sort properties.
- [ ] Use stable ordering with a tie-breaker.
- [ ] Test JSON contracts, empty pages, last pages, and SQL performance.

## 16. Conclusion

**Page<Entity>.map()** is a simple way to transform each entity into a DTO while preserving pagination metadata. Mappers should read only necessary data; if LAZY associations are accessed, choose a suitable fetch plan or query DTOs directly to prevent N+1 queries.

At the API boundary, define an explicit response contract instead of relying on how a Page implementation serializes. Having a DTO for content and a wrapper for metadata gives clients a stable structure that is easy to document and resilient when entities or framework versions change.