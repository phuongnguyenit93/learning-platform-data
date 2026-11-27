# Distinguishing List, Slice, and Page

Spring Data JPA supports multiple result types for repository queries. When querying a list of data, you can return **List**, **Slice**, or **Page**. All three contain results, but the amount of metadata and query cost differ.

- **List** returns only the elements. When combined with **Pageable**, results are limited to the page, but there is no information about the next page or total record count.
- **Slice** returns a slice of data along with navigation information such as **hasNext()** and **hasPrevious()**, without calculating the total record count.
- **Page** provides the content along with the total element count and total page count. To obtain totals, Spring Data typically needs to execute an additional count query.

Choosing the right return type avoids unnecessary count queries, reduces database load, and provides exactly the information the API needs. This lesson uses a shared Book model to compare all three return types, passing Pageable, stable sorting, and handling large datasets.

**Example prerequisites:** the code snippets use Spring Boot 3.x, Java 17 or later, and Spring Data JPA. The application requires **spring-boot-starter-data-jpa**, a JDBC driver, DataSource, and matching schema. These are parts of a Spring Boot application, not standalone programs that can be run with just **javac**.

## 1. Quick Comparison of List, Slice, and Page

| Criterion | List | Slice | Page |
|---|---|---|---|
| Result content | Yes | Yes | Yes |
| Limited by Pageable | Yes, if Pageable is passed | Yes | Yes |
| Knows if next page exists | No | Yes, via **hasNext()** | Yes, via **hasNext()** |
| Knows total elements | No | No | Yes, via **getTotalElements()** |
| Knows total pages | No | No | Yes, via **getTotalPages()** |
| Count query | Not needed for List with Pageable | Not needed | Usually needed, unless inferred by framework |
| Cost | Low metadata overhead | Generally lower than Page | Can be higher due to count |
| Best suited for | Fetching a simple list or a bounded chunk | Iterating slice by slice, only needing to know if more data exists | UIs needing total records/pages and full pagination controls |

Both **Slice** and **Page** extend Spring Data's **Slice** abstraction; Page adds total counts. A Page can provide all the basic navigation information of a Slice, at the cost of computing total results.

Choose based on actual needs:

- If you only need a bounded list, use List with Pageable.
- If you need a “Next” button without knowing the total number of pages, use Slice.
- If the UI must display “page 2 of 15” or “1,245 results”, use Page.

## 2. Pageable Controls Page and Size

**Pageable** describes which page to retrieve, the page size, and sorting details.

Example creating a page request:

~~~java
Pageable pageable = PageRequest.of(0, 20);
~~~

Meaning:

- **0** is the first page index (zero-based).
- **20** is the maximum number of elements per page.

Next page:

~~~java
Pageable nextPage = PageRequest.of(1, 20);
~~~

In Spring Data, page index starts at 0:

| page value | User-facing page number |
|---:|---:|
| 0 | 1 |
| 1 | 2 |
| 2 | 3 |
| 3 | 4 |

Do not confuse page index with the page number typically displayed in the UI. If an API receives 1-based page numbers, convert to zero-based index before creating PageRequest.

Page size must be positive. APIs should also cap the maximum size so a client cannot request hundreds of thousands of records in a single call.

## 3. Sample Repository Using All Three Return Types

Suppose the Book entity has properties **id**, **title**, **status**, **createdAt**, and **authorId** or an appropriate author association.

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Book;
import com.example.catalog.domain.BookStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface BookRepository extends JpaRepository<Book, Long> {

    Page<Book> findByStatus(
        BookStatus status,
        Pageable pageable
    );

    Slice<Book> findByAuthorId(
        Long authorId,
        Pageable pageable
    );

    List<Book> findByTitleContainingIgnoreCase(
        String keyword,
        Pageable pageable
    );
}
~~~

The methods use similar query conditions but different return types:

- **findByStatus** returns Page because the use case needs the total count of books by status.
- **findByAuthorId** returns Slice because the UI only needs to load more if additional books exist.
- **findByTitleContainingIgnoreCase** returns List because the caller only needs a bounded chunk of results without navigation metadata.

Property names in derived queries must match the actual entity model. For instance, **findByAuthorId** works when the property path resolves to the author relationship and ID; if the entity uses a different field name, update the method accordingly or declare an explicit query.

## 4. List with Pageable: Fetch Only What Is Needed

When a repository method returns List and accepts Pageable:

~~~java
List<Book> books =
    bookRepository.findByTitleContainingIgnoreCase(
        "spring",
        PageRequest.of(0, 20)
    );
~~~

Spring Data applies the limit and offset corresponding to Pageable. The result contains at most 20 elements for the requested page.

List does not provide:

- Total number of matching elements.
- Total number of pages.
- hasNext() or hasPrevious().
- Page number and page size as result metadata.

Because totals are not needed, List with Pageable does not require a count query to calculate totals. It is a lean choice when a task only needs one slice of results.

If a method returns List without taking Pageable, the repository may return all matching results. On large tables, avoid unbounded queries when the caller only needs a limited number of records.

### Limitations of List with Pageable

The caller cannot know for sure whether a next page exists from a List alone. If a full page size is returned, more data may exist, or that could happen to be the exact final page. Receiving fewer elements than page size generally implies no further results in that query, but such checks do not replace Slice metadata when clear navigation is needed.

If a workflow must loop over multiple pages and know whether more data remains, Slice is generally a better fit.

## 5. Slice: Know Whether More Data Exists Without Counting Totals

Slice holds page content and navigation metadata. Commonly used methods:

| Method | Meaning |
|---|---|
| **getContent()** | List of elements in the current slice |
| **getNumber()** | Current page index, starting from 0 |
| **getSize()** | Requested page size |
| **getNumberOfElements()** | Actual number of elements in the slice |
| **hasNext()** | Whether a next slice exists |
| **hasPrevious()** | Whether a previous slice exists |
| **nextPageable()** | Pageable for the next slice |
| **previousPageable()** | Pageable for the previous slice |

Example:

~~~java
Slice<Book> slice =
    bookRepository.findByAuthorId(
        authorId,
        PageRequest.of(0, 20)
    );

for (Book book : slice.getContent()) {
    System.out.println(book.getTitle());
}

if (slice.hasNext()) {
    Pageable next = slice.nextPageable();
    // Can use next to load the next slice.
}
~~~

To determine whether more data exists, Spring Data typically requests one extra element beyond the page size. For example, with page size 20, the query may fetch up to 21 rows. If the 21st row exists, **hasNext()** is true; the extra row is omitted from the current slice's content.

This avoids running a count query just to check for more data. Cost can still scale with the main query, but it is typically lower than counting the entire result set.

### Iterating Through All Slices

~~~java
Pageable pageable = PageRequest.of(0, 100);
Slice<Book> slice;

do {
    slice = bookRepository.findByAuthorId(authorId, pageable);

    process(slice.getContent());

    pageable = slice.nextPageable();
} while (slice.hasNext());
~~~

In production code, ensure the loop terminates when no data remains and handle query errors appropriately. If data changes while iterating, results between slices may shift depending on transaction isolation and sorting.

## 6. Page: Includes Total Elements and Total Pages

Page extends Slice information with total result counts:

~~~java
Page<Book> page =
    bookRepository.findByStatus(
        BookStatus.PUBLISHED,
        PageRequest.of(0, 20)
    );
~~~

Commonly used methods:

| Method | Meaning |
|---|---|
| **getContent()** | Page content |
| **getNumber()** | Current page index |
| **getSize()** | Requested page size |
| **getNumberOfElements()** | Number of elements on the current page |
| **getTotalElements()** | Total elements matching the query conditions |
| **getTotalPages()** | Total pages |
| **hasNext()** | Whether there is a next page |
| **isFirst()** / **isLast()** | Whether it is the first or last page |

Example output:

~~~text
number        = 0
size          = 20
numberOfElements = 20
totalElements = 245
totalPages    = 13
hasNext       = true
~~~

If page size is 20 and total elements is 245, total pages is 13. The last page can contain fewer than 20 elements.

If no records match, Page has empty content, **getTotalElements()** is 0, and **getTotalPages()** is 0.

If a page index beyond the last page is requested, Page typically returns empty content while still potentially containing the total count computed from the count query.

## 7. Why Does Page Usually Need a Count Query?

To return **getTotalElements()**, the framework must know the total number of matching records, not only the records on the current page. Spring Data typically executes:

1. A content query with limit/offset.
2. A count query to count total results.

Conceptual SQL example:

~~~sql
SELECT id, title, status, created_at
FROM books
WHERE status = 'PUBLISHED'
ORDER BY created_at DESC
LIMIT 20 OFFSET 0;

SELECT COUNT(*)
FROM books
WHERE status = 'PUBLISHED';
~~~

The count query can be expensive if filter conditions are complex, join many tables, use DISTINCT, or query large datasets.

Spring Data can infer the total count from content in some situations, such as when the first page has fewer elements than page size. Thus not every Page call necessarily runs a count query. Still, when designing for performance, assume Page may require a count query and inspect the actual SQL.

If the UI does not need totals, using Slice avoids this cost.

## 8. Declaring countQuery for Complex JPQL

For simple query methods, Spring Data usually generates the count query automatically. For JPQL with joins, distinct, or complex structures, declare an explicit count query.

Example:

~~~java
@Query(
    value = """
        select b
        from Book b
        join b.author a
        where b.status = :status
          and a.active = true
        """,
    countQuery = """
        select count(b)
        from Book b
        join b.author a
        where b.status = :status
          and a.active = true
        """
)
Page<Book> findActiveAuthorBooks(
    @Param("status") BookStatus status,
    Pageable pageable
);
~~~

The count query must count the exact logical number of entities returned by the content query. If joining a collection causes a Book to appear multiple times, you may need:

~~~sql
select count(distinct b.id)
~~~

In JPQL, use **count(distinct b.id)** when appropriate for the query structure. Do not simply copy the content query and swap SELECT for COUNT without checking join cardinality.

## 9. Paginating Native Queries

Native queries can return Page, but for complex queries declare a separate **countQuery**:

~~~java
@Query(
    value = """
        SELECT b.id, b.title, b.status, b.created_at
        FROM books b
        WHERE b.status = :status
        ORDER BY b.created_at DESC, b.id DESC
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM books b
        WHERE b.status = :status
        """,
    nativeQuery = true
)
Page<Book> findNativePageByStatus(
    @Param("status") String status,
    Pageable pageable
);
~~~

The content query must return all columns required by the Book mapping. Column names in SQL are physical database names; verify mappings and aliases if names differ.

For native queries with GROUP BY, the count query needs to count the number of returned groups, not the total source rows. For joins that can multiply rows, use COUNT DISTINCT on the entity ID or a count query matching the actual logic.

Do not assume Spring Data can always infer a correct count query for arbitrary native SQL. Test both the content query and count query on the target database.

## 10. Sorting with Pageable

Pageable can carry a Sort:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by(Sort.Direction.DESC, "id"))
);
~~~

The query sorts by creation time descending, then by ID descending.

Add a unique property such as **id** as a tie-breaker so ordering stays stable when multiple rows share the same createdAt. Without stable ordering, pages can duplicate or miss elements even when data has not changed, depending on the database and execution plan.

Property names in Sort are normally entity property paths, e.g. **createdAt**, not physical column names like **created_at**. With native queries, dynamic sort support depends on how Spring Data processes the query and the version; declare ORDER BY in SQL when explicit control is needed.

Do not pass arbitrary sort strings from clients directly into native SQL. Restrict allowed sort fields in the API to prevent errors and keep queries predictable.

## 11. Using Page.map() to Convert to DTOs

You do not need to construct a new Page manually just to convert entities to DTOs. **Page.map()** preserves pagination metadata and transforms each element.

DTO:

~~~java
public record BookSummary(
    Long id,
    String title,
    BookStatus status
) {
    public static BookSummary from(Book book) {
        return new BookSummary(
            book.getId(),
            book.getTitle(),
            book.getStatus()
        );
    }
}
~~~

Service:

~~~java
@Transactional(readOnly = true)
public Page<BookSummary> findPublishedBooks(Pageable pageable) {
    return bookRepository
        .findByStatus(BookStatus.PUBLISHED, pageable)
        .map(BookSummary::from);
}
~~~

The result still retains **getTotalElements()**, **getTotalPages()**, **hasNext()**, and other metadata. Only the content is converted from Book to BookSummary.

If the DTO needs data from LAZY associations, load the proper fetch plan in the query or use a DTO projection directly. Do not call association getters inside the mapper uncontrolled, as that can cause N+1 queries.

## 12. Example API Accepting Pageable

Spring MVC can bind standard query parameters into Pageable when Spring Data web support is configured.

Controller:

~~~java
@RestController
@RequestMapping("/books")
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @GetMapping
    public Page<BookSummary> search(
            @RequestParam(required = false) String keyword,
            @PageableDefault(
                size = 20,
                sort = "createdAt",
                direction = Sort.Direction.DESC
            ) Pageable pageable) {

        return bookService.search(keyword, pageable);
    }
}
~~~

Example request:

~~~text
GET /books?keyword=spring&page=0&size=20&sort=createdAt,desc
~~~

Common parameters:

- **page**: zero-based page index.
- **size**: maximum number of elements per page.
- **sort**: property and sort direction; multiple sort parameters may be passed.

**@PageableDefault** sets default values when the client omits page/size/sort. Cap maximum page size and allow only the sort properties supported by the API. If the API displays 1-based page numbers, convert explicitly at the boundary layer instead of implicitly altering Pageable semantics.

## 13. Choosing List, Slice, or Page by Use Case

| Use case | Typically suitable choice | Reason |
|---|---|---|
| Small dropdown, always-bounded list | List | Only content is needed |
| Incremental “load more” API | Slice | Knows if more data exists, no total needed |
| UI with page numbers / total results | Page | Needs totalElements and totalPages |
| Batch reading chunks for processing | Slice or List with Pageable | No need to count the entire set |
| Report requiring total record count | Page | Provides total metadata |
| Large search where count query is very expensive | Slice | Avoids count if UI does not need total |
| Fetching a small, business-bounded set of records | List | Simple, though size must be controlled |

There is no single best return type for every situation. Ask what information the caller needs before selecting the result type.

## 14. Offset Pagination and Large Datasets

PageRequest normally uses offset pagination. The deeper the page, the more rows the database may have to skip before returning results. For example, page 5,000 with page size 20 has an offset of 99,980.

Offset pagination is convenient for UIs that jump to arbitrary pages, but it has two drawbacks:

- Large offsets can be slow because the database must process/skip many rows.
- If records are inserted or deleted between two calls, row positions shift; users may see duplicate or skipped records across pages.

Mitigate the risk by:

- Using stable ordering with a unique key as a tie-breaker.
- Keeping page sizes reasonable.
- Using Slice when total counts are unnecessary.
- For unidirectional traversal over large datasets, considering keyset/scroll pagination if supported by the Spring Data version and query.

Keyset pagination resumes from the last sort key values instead of jumping to a large offset. It works well for “load more” or sequential batches, though it does not easily support jumping directly to arbitrary pages. Choose sort keys that are stable and properly indexed.

## 15. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| First page skipped | Using 1-based page index instead of 0-based | Convert API page numbers to zero-based |
| Page query is slow | Complex count query or counting over multiple joins | Use Slice if total is unneeded; optimize countQuery |
| Wrong total element count | Count query counts join rows instead of unique entities | Use count distinct or an accurate count query |
| List returns too much data | Missing Pageable or unbounded query | Use Pageable and cap page size |
| Cannot tell if next page exists with List | List has no navigation metadata | Use Slice |
| Sort does not work | Sort name uses column name instead of property or native query lacks expected support | Check property path and declare appropriate ORDER BY |
| Duplicate/missing results across pages | Unstable order or data changing between requests | Add a unique tie-breaker; consider keyset |
| Client requests huge page size | Unvalidated Pageable input | Enforce maximum page size at the API |
| Wrong total pages with GROUP BY | Count query does not count groups | Write a countQuery that counts groups accurately |

## 16. Selection and Implementation Checklist

- [ ] Determine whether the caller needs total record and total page counts.
- [ ] Use List if only bounded content is needed.
- [ ] Use Slice if knowing whether a next page exists is needed without total counts.
- [ ] Use Page if the UI needs totalElements/totalPages.
- [ ] Remember Spring Data page indexes start at 0.
- [ ] Cap page size and validate sort parameters.
- [ ] Add a unique tie-breaker for stable ordering.
- [ ] Declare countQuery for complex JPQL/native queries.
- [ ] Check whether JOINs multiply row counts.
- [ ] Use Page.map() when converting entities to DTOs.
- [ ] Measure SQL and count query latency on realistic data.
- [ ] Consider keyset/scroll for large offsets and sequential reads.

## 17. Conclusion

**List** returns only content; when used with Pageable, it limits results without providing navigation metadata. **Slice** adds whether a next page exists without counting total records. **Page** provides total elements and total pages, usually requiring a count query to obtain those values.

Use Slice for load-more flows, Page for UIs requiring totals, and List when only a bounded result set is needed. Pair Pageable with stable sorting, accurate countQuery definitions, and sensible page sizes to keep queries understandable and performance predictable.