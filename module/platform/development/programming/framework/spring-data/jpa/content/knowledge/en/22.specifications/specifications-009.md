# Pagination, Sorting, and Fluent Queries with Spring Data JPA Specifications

## 1. Objective: Flexible Querying Without Over-Fetching Data

In real applications, a search screen often lets users combine multiple conditions—status, name, date range, price tier—and pick a page and sort order. Spring Data JPA `Specification` lets you assemble dynamic conditions into a reusable predicate. `Pageable` and `Sort` add pagination and result ordering. In Spring Data JPA versions supporting Fluent Queries, you can further specify the return type, projection, row limit, and fetch behavior directly at the query call site.

The three concepts each have a distinct role:

- **Specification:** describes filter criteria using the Criteria API.
- **Pageable / Sort:** describes which page to retrieve and the sort order.
- **Fluent Query:** controls how the Specification executes and what result type is returned via chained intermediate and terminal operations.

Combining these APIs properly allows a single search filter to serve multiple use cases: returning entities, DTOs, a page, a slice, a count, or an existence check.

## 2. Preparing a Specification-Capable Repository

The repository must extend `JpaSpecificationExecutor` in addition to `JpaRepository`:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
~~~

`JpaRepository` provides standard CRUD, pagination, and sorting operations. `JpaSpecificationExecutor` provides `Specification` execution methods, such as:

- `findAll(spec)` returns all matching entities.
- `findAll(spec, sort)` returns a sorted list of entities.
- `findAll(spec, pageable)` returns a `Page<T>`.
- `findOne(spec)` returns an `Optional<T>` and throws an error if more than one result matches.
- `count(spec)` counts matching entities.
- `exists(spec)` checks whether any matching result exists.

The basic `findAll` methods accepting Specification and Pageable/Sort existed in Spring Data JPA versions prior to the Fluent API. Therefore, older projects can still paginate and sort with Specifications without using the Fluent API.

## 3. Specification Represents Filter Criteria

`Specification<T>` is a predicate built using the JPA Criteria API. A Specification receives `Root<T>`, `CriteriaQuery<?>`, and `CriteriaBuilder`, and returns a `Predicate`.

Simple entity example:

~~~java
@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fullName;
    private String email;

    @Enumerated(EnumType.STRING)
    private CustomerStatus status;

    private LocalDate createdDate;

    protected Customer() {
    }

    // Constructor, getters and domain methods omitted.
}
~~~

Creating a Specification by status:

~~~java
public final class CustomerSpecifications {

    private CustomerSpecifications() {
    }

    public static Specification<Customer> hasStatus(
            CustomerStatus status) {

        return (root, query, cb) ->
            status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }
}
~~~

`cb.conjunction()` builds an always-true condition. Thus, when no status is passed, this condition filters out no records.

Creating a case-insensitive keyword-contains Specification on name:

~~~java
public static Specification<Customer> nameContains(String keyword) {
    return (root, query, cb) -> {
        if (keyword == null || keyword.isBlank()) {
            return cb.conjunction();
        }

        String pattern =
            "%" + keyword.trim().toLowerCase(Locale.ROOT) + "%";

        return cb.like(
            cb.lower(root.<String>get("fullName")),
            pattern
        );
    };
}
~~~

Creating a date range condition:

~~~java
public static Specification<Customer> createdBetween(
        LocalDate from,
        LocalDate to) {

    return (root, query, cb) -> {
        if (from == null && to == null) {
            return cb.conjunction();
        }
        if (from == null) {
            return cb.lessThanOrEqualTo(root.get("createdDate"), to);
        }
        if (to == null) {
            return cb.greaterThanOrEqualTo(root.get("createdDate"), from);
        }
        return cb.between(root.get("createdDate"), from, to);
    };
}
~~~

These methods are code snippets for a Spring Data JPA application; matching enums, entity mappings, imports, and dependencies are required. Breaking each condition into a small Specification makes testing and composition easier.

## 4. Combining Specifications with AND and OR

Specifications can be combined using `and()`, `or()`, and `not()`.

Example finding active customers with a matching name created within a date range:

~~~java
Specification<Customer> spec =
    CustomerSpecifications.hasStatus(CustomerStatus.ACTIVE)
        .and(CustomerSpecifications.nameContains("an"))
        .and(CustomerSpecifications.createdBetween(
            LocalDate.of(2025, 1, 1),
            LocalDate.of(2025, 12, 31)
        ));
~~~

Use `or()` when satisfying any one of multiple conditions suffices:

~~~java
Specification<Customer> nameOrEmail =
    CustomerSpecifications.nameContains("an")
        .or((root, query, cb) ->
            cb.like(
                cb.lower(root.<String>get("email")),
                "%an%"
            )
        );
~~~

Use `not()` to negate a Specification:

~~~java
Specification<Customer> notActive =
    Specification.not(
        CustomerSpecifications.hasStatus(CustomerStatus.ACTIVE)
    );
~~~

Clearly design what a condition means when parameters may be null or blank. When a condition should be skipped, returning an always-true predicate is a common pattern. If null means finding records whose column is NULL, write `isNull()` instead of skipping the condition.

## 5. Pageable and PageRequest

`Pageable` is an abstraction describing page number, page size, and optionally sort order. `PageRequest` is the standard implementation used to build pagination requests.

Example fetching the first page of 20 records:

~~~java
Pageable pageable = PageRequest.of(0, 20);
~~~

Page numbers are zero-based:

- `PageRequest.of(0, 20)` is the first page.
- `PageRequest.of(1, 20)` is the second page.
- `PageRequest.of(2, 20)` is the third page.

The second parameter is page size, which must be positive. Avoid large page sizes when results contain full entities or heavy associations.

Sorting can be attached directly to `PageRequest`:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdDate"),
    Sort.Order.asc("id")
);

Pageable pageable = PageRequest.of(0, 20, sort);
~~~

Here, results are sorted by creation date descending, then ID ascending. Because ID is a unique key, it keeps the order deterministic when multiple customers share the same creation date.

## 6. Page, Slice, and List in Pagination

Spring Data JPA can return `Page<T>`, `Slice<T>`, or `List<T>` when a method accepts `Pageable`.

| Return Type | Metadata | Count Query | When to Use |
|---|---|---|---|
| `Page<T>` | Total elements, total pages, current page | Usually needed to determine totals | UI needs total pages or total record count |
| `Slice<T>` | Whether a next page exists | No total count needed | Infinite scroll or step-by-step navigation |
| `List<T>` | Only the content within the page window | No total metadata generated | Only a slice of results is needed |

Repository example:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {

    Page<Customer> findByStatus(
        CustomerStatus status,
        Pageable pageable
    );

    Slice<Customer> findByEmailContaining(
        String keyword,
        Pageable pageable
    );

    List<Customer> findByFullNameContaining(
        String keyword,
        Pageable pageable
    );
}
~~~

Using Specification to fetch a Page:

~~~java
Page<Customer> page =
    customerRepository.findAll(spec, PageRequest.of(0, 20));
~~~

Reading metadata:

~~~java
int currentPage = page.getNumber();
int pageSize = page.getSize();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
boolean hasPrevious = page.hasPrevious();
~~~

`Page<T>` is useful for UIs displaying "page 2 of 8" or total result counts. To compute totals, Spring Data usually runs a count query; on complex queries, counting can be expensive. The framework may optimize away the count query in certain cases where the total can be inferred from the current results.

`Slice<T>` only needs to know whether a next element exists. The typical mechanism fetches one extra row to determine `hasNext()`, avoiding a full result count.

`List<T>` combined with `Pageable` retrieves only the requested data window without producing Page metadata. Use this when callers need a paged subset and do not need total counts.

## 7. Using Specification Together with Pageable

Example service receiving request filters:

~~~java
@Service
public class CustomerSearchService {

    private final CustomerRepository repository;

    public CustomerSearchService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Page<Customer> search(
            CustomerStatus status,
            String keyword,
            LocalDate from,
            LocalDate to,
            int page,
            int size) {

        Specification<Customer> spec =
            CustomerSpecifications.hasStatus(status)
                .and(CustomerSpecifications.nameContains(keyword))
                .and(CustomerSpecifications.createdBetween(from, to));

        Pageable pageable = PageRequest.of(
            page,
            size,
            Sort.by(
                Sort.Order.desc("createdDate"),
                Sort.Order.asc("id")
            )
        );

        return repository.findAll(spec, pageable);
    }
}
~~~

The service constructs a Specification from the filters and then constructs a Pageable. The repository executes the query and returns a Page.

In real APIs, validate that `page` is non-negative and `size` stays within permitted limits. Never let clients request hundreds of thousands of records in one page. Configure default and maximum page sizes at the API/service layer.

`Pageable.unpaged()` indicates no pagination. If a method takes Sort, pass `Sort.unsorted()` when no sorting is needed. APIs accepting Pageable/Sort normally expect non-null arguments; never pass null to mean "unpaged" or "unsorted".

## 8. Sorting with Sort

`Sort` describes one or more sort orders. Each `Sort.Order` specifies a property, ascending/descending direction, and optional settings.

Example:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("status"),
    Sort.Order.desc("createdDate"),
    Sort.Order.asc("id")
);
~~~

Shorthand:

~~~java
Sort sort = Sort.by("createdDate").descending()
    .and(Sort.by("id").ascending());
~~~

Common operations:

- `Sort.by("name")`: sorts ascending by name.
- `Sort.by("name").descending()`: sorts descending.
- `Sort.Order.asc("name")`: a single ascending order.
- `Sort.Order.desc("createdDate")`: a single descending order.
- `Sort.unsorted()`: applies no sorting.
- `Sort.Order.asc("name").ignoreCase()`: requests case-insensitive sorting when supported.
- `Sort.Order.asc("name").nullsLast()`: specifies null handling preference; actual database behavior can vary.

Properties in Sort must resolve to entity properties or aliases declared in the query. For instance, if the entity defines `createdDate`, use `Sort.by("createdDate")`; do not use SQL column names like `created_date` unless that is a valid query alias.

## 9. Static Sorting via Method Names

When ordering is always fixed, `OrderBy` can be declared directly in the repository method name:

~~~java
List<Customer> findByStatusOrderByCreatedDateDescIdAsc(
    CustomerStatus status
);
~~~

This method filters by status, then sorts by creation date descending and ID ascending.

Static sorting fits when business rules specify one fixed order. If users can choose the sort column or direction, accept `Sort` or `Pageable` for dynamic control.

Avoid hardcoding a fixed order in the method name while also passing a dynamic sort unless there is a clear reason. Establish one source of truth for sorting to avoid unpredictable behavior.

## 10. Dynamic Sorting with @Query

Methods annotated with `@Query` can also accept `Sort` or `Pageable`:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select c
        from Customer c
        where c.status = :status
    """)
    List<Customer> findByStatus(
        @Param("status") CustomerStatus status,
        Sort sort
    );
}
~~~

Invocation:

~~~java
List<Customer> customers = repository.findByStatus(
    CustomerStatus.ACTIVE,
    Sort.by("fullName").ascending()
);
~~~

Spring Data appends the appropriate `ORDER BY` clause to the query. Sort expressions must be valid property paths or aliases referenceable in the query.

Example query selecting an aliased expression:

~~~java
@Query("""
    select c.id as id, length(c.fullName) as nameLength
    from Customer c
    where c.status = :status
""")
List<Object[]> findNameLengths(
    @Param("status") CustomerStatus status,
    Sort sort
);
~~~

You can sort by the alias `nameLength` when that alias is exposed by the query and referenceable.

## 11. JpaSort.unsafe and Sort Expressions

By default, Spring Data JPA validates Sort expressions to disallow functions or expressions that are not valid property paths. In some situations, you need to sort by a JPQL expression such as name length or a calculation.

`JpaSort.unsafe()` can be used:

~~~java
List<Customer> customers = repository.findByStatus(
    CustomerStatus.ACTIVE,
    JpaSort.unsafe("LENGTH(fullName)")
);
~~~

`JpaSort.unsafe()` lets expressions pass into the ORDER BY clause without standard property-path validation. This is risky if expressions are constructed from user input.

Safety rules:

- Only use fixed expressions controlled by developers.
- Never concatenate arbitrary sort strings from requests into `JpaSort.unsafe()`.
- Map client-provided sort names to an allowlist of properties or expressions.
- Verify JPQL syntax and provider/database support.
- Prefer query aliases or standard property paths whenever they meet requirements.

Whitelist example:

~~~java
public Sort resolveSort(String requestedSort) {
    return switch (requestedSort) {
        case "name" -> Sort.by("fullName").ascending();
        case "newest" -> Sort.by(
            Sort.Order.desc("createdDate"),
            Sort.Order.asc("id")
        );
        case "oldest" -> Sort.by(
            Sort.Order.asc("createdDate"),
            Sort.Order.asc("id")
        );
        default -> Sort.by("id").ascending();
    };
}
~~~

Clients only pick an approved key; clients must never send raw JPQL/SQL expressions.

## 12. Sort Stability During Pagination

Pagination relies on an ordered result set. Without an explicit sort, the database does not guarantee consistent row order across queries.

Suppose multiple customers share the same `createdDate` and the query sorts only by date. Rows with equal values may appear in different order across two queries. When moving from page to page, records can be duplicated or skipped.

Add a unique key as a tie-breaker:

~~~java
Sort stableSort = Sort.by(
    Sort.Order.desc("createdDate"),
    Sort.Order.asc("id")
);
~~~

This establishes a total order if ID is unique and non-null.

However, a stable sort does not guarantee a consistent snapshot when data changes between requests. If records are inserted, deleted, or have their sort keys modified while a user paginates, offset positions can shift.

For very large datasets or background jobs traversing sequentially, consider the Scroll API with `Window<T>` and keyset positioning where appropriate. Keyset pagination uses the last record's sort values instead of skipping huge row offsets. It requires non-null sort keys, deterministic ordering, and supporting indexes.

## 13. Count Queries and Page Performance

A Page needs the total element count to compute `totalElements` and `totalPages`. Spring Data can derive a count query from the content query or Specification. For complex queries, counting may involve JOINs or DISTINCT and become costly.

Example using Specification:

~~~java
Page<Customer> page = repository.findAll(spec, pageable);
~~~

If the Specification joins a collection, verify how entities are counted. A one-to-many JOIN can multiply SQL rows. In that case, the count query must count unique root entities, typically requiring distinct ID counting or an appropriate query structure.

### Dedicated Count Specification

Starting in Spring Data JPA 3.5, `JpaSpecificationExecutor` provides an overload accepting a separate Specification for counting:

~~~java
Page<Customer> page = repository.findAll(
    contentSpec,
    countSpec,
    pageable
);
~~~

`contentSpec` can include JOINs/fetches or clauses needed for page content. `countSpec` describes the exact same entity set to count, while omitting unnecessary fetch joins to keep the count query lightweight.

Both Specifications must express the exact same logical result set. If `countSpec` omits a filter condition, `totalElements` will be wrong even though page content is right.

When using `@Query`, you can declare an explicit `countQuery` if the main query is complex or Spring Data cannot infer an accurate count.

## 14. What Is a Fluent Query?

Fluent Query lets you specify how a query executes directly inside a callback function. For Specifications, `JpaSpecificationExecutor` provides `findBy(spec, queryFunction)`.

The flow is:

1. Pass a Specification to identify matching records.
2. Receive the fluent query builder inside the callback.
3. Call intermediate operations such as `sortBy`, `limit`, `as`, or `project`.
4. Call a terminal operation such as `all`, `page`, `slice`, `first`, `count`, or `exists`.
5. Return the executed result from the callback.

General example:

~~~java
List<Customer> customers = repository.findBy(
    spec,
    query -> query
        .sortBy(Sort.by("fullName").ascending())
        .limit(100)
        .all()
);
~~~

This method applies the Specification, sorts by name, caps results at 100, and returns a List.

Fluent Query is not mandatory for every query. For straightforward queries, `findAll(spec, pageable)` or `findAll(spec, sort)` is often shorter and more readable. Fluent Query shines when you need projection, sorting, limiting, and result typing in one call.

## 15. Pagination with Fluent Query

Example fetching a Page with Specification and projection:

~~~java
Page<CustomerSummary> page = repository.findBy(
    spec,
    query -> query
        .as(CustomerSummary.class)
        .page(PageRequest.of(
            0,
            20,
            Sort.by("fullName").ascending()
        ))
);
~~~

`as(CustomerSummary.class)` specifies the return type. `page(Pageable)` runs the paginated query and returns `Page<CustomerSummary>`.

You can use `slice(Pageable)` when total counts are not needed:

~~~java
Slice<CustomerSummary> slice = repository.findBy(
    spec,
    query -> query
        .as(CustomerSummary.class)
        .slice(PageRequest.of(
            0,
            50,
            Sort.by("id").ascending()
        ))
);
~~~

`Pageable` can carry a Sort. If the supplied Pageable is sorted, its sort overrides any sort previously set via `sortBy()`. Avoid specifying two conflicting orders; pick one single place to define the final sort order.

## 16. Projections with Fluent Query

Fluent Query allows transforming entity results into a projection tailored to the use case.

Record DTO example:

~~~java
public record CustomerSummary(
    Long id,
    String fullName,
    String email
) {}
~~~

The repository can fetch the DTO directly:

~~~java
List<CustomerSummary> summaries = repository.findBy(
    spec,
    query -> query
        .as(CustomerSummary.class)
        .sortBy(Sort.by("fullName").ascending())
        .all()
);
~~~

Projections fetch only needed columns and avoid passing full entities across service/API layers. However, projection constructors and properties must match the entity and Spring Data JPA's projection rules.

`as(Class<R>)` selects the desired result/projection type. `project("fieldA", "fieldB")` restricts which properties are read where supported. These two operations are related but not identical: `as` chooses the projection type, whereas `project` restricts the property list.

For class/record DTOs, ensure a compatible constructor. For interface projections, getters must align with exposed properties. Verify projections with integration tests rather than relying solely on compile-time checks.

## 17. Common Fluent Query Operations

Fluent Query has two groups of operations:

### Intermediate Operations

| Method | Meaning |
|---|---|
| `sortBy(Sort)` | Adds sort ordering |
| `limit(int)` | Limits the number of results |
| `as(Class<R>)` | Selects projection/result type |
| `project(String...)` | Selects only the specified properties |

### Terminal Operations

| Method | Return Type | Meaning |
|---|---|---|
| `all()` | `List<T>` | Retrieves all matching results in query scope |
| `first()` | `Optional<T>` | Retrieves the first element or empty |
| `firstValue()` | `T` or null | Nullable variant of first |
| `one()` | `Optional<T>` | Requires at most one result; more than one throws |
| `oneValue()` | `T` or null | Nullable variant of one |
| `page(Pageable)` | `Page<T>` | Retrieves a page with total count |
| `slice(Pageable)` | `Slice<T>` | Retrieves a slice without total count |
| `scroll(ScrollPosition)` | `Window<T>` | Scrolls by offset or keyset position |
| `stream()` | `Stream<T>` | Consumes results via stream; must be closed |
| `count()` | `long` | Counts matching entities |
| `exists()` | `boolean` | Checks whether any match exists |

`first()` fits when you want any single element under a defined order. Without Sort, "first element" has no business-guaranteed order. `one()` fits when business rules allow at most one match; if the query finds more than one, Spring Data throws `IncorrectResultSizeDataAccessException`.

Intermediate and terminal operations must be invoked inside the `findBy` callback. Never store the intermediate query object for use outside the callback.

## 18. Fluent Query: first, count, and exists

Fetching the newest customer:

~~~java
Optional<Customer> newest = repository.findBy(
    spec,
    query -> query
        .sortBy(Sort.by(
            Sort.Order.desc("createdDate"),
            Sort.Order.asc("id")
        ))
        .first()
);
~~~

Counting results:

~~~java
long total = repository.findBy(
    spec,
    query -> query.count()
);
~~~

Checking existence:

~~~java
boolean hasMatch = repository.findBy(
    spec,
    query -> query.exists()
);
~~~

When you only need to know whether matching data exists, `exists()` communicates intent far better than loading an entire list and checking `isEmpty()`.

## 19. Fluent Query with a Custom Count Specification

Starting in Spring Data JPA 3.5, `SpecificationFluentQuery` supports `page(Pageable, countSpec)`. You can pass one Specification for the content query and another for counting:

~~~java
Page<CustomerSummary> page = repository.findBy(
    contentSpec,
    query -> query
        .as(CustomerSummary.class)
        .page(pageable, countSpec)
);
~~~

This helps when the content query needs JOINs or fetches that the count query does not need. `countSpec` must preserve the exact filter semantics of the result set, omitting only joins/fetches unnecessary for counting.

If a project runs Spring Data JPA prior to 3.5, this custom count specification overload is unavailable. Use `findAll(spec, pageable)` or declare a suitable count query where supported. Never copy newer API examples into older projects without checking dependency versions.

## 20. Fluent Query Combined with Scrolling

In supported versions, Fluent Query can terminate with `scroll(ScrollPosition)` to return a `Window<T>`:

~~~java
Window<Customer> window = repository.findBy(
    spec,
    query -> query
        .sortBy(Sort.by("id").ascending())
        .scroll(ScrollPosition.offset())
);
~~~

Keyset scrolling can be used when sort keys are suitable:

~~~java
Window<Customer> window = repository.findBy(
    spec,
    query -> query
        .sortBy(Sort.by(
            Sort.Order.asc("createdDate"),
            Sort.Order.asc("id")
        ))
        .scroll(ScrollPosition.keyset())
);
~~~

Scrolling helps when processing large datasets window by window without needing total record counts. Keyset scrolling requires deterministic ordering, non-null sort keys, and projections that include the sort fields.

According to current documentation, the Scroll API supports derived query methods, Query by Example, and Querydsl; string-based query methods such as `@Query` and stored `@Procedure` queries do not support scrolling. Fluent Query over Specifications provides a way to use scrolling with dynamic predicates.

## 21. The Fluent Query Object Is Only Valid Inside the Callback

A common design mistake is trying to save the intermediate query object:

~~~java
// Do not do this.
var fluentQuery = repository.findBy(spec, query -> query);
~~~

`findBy` requires the callback to return an executed result—such as a List, Page, Optional, count, or boolean. The fluent query object is valid only during the `findBy` invocation; never return the query object itself for later use.

Correct approach:

~~~java
List<Customer> customers = repository.findBy(
    spec,
    query -> query
        .sortBy(Sort.by("id").ascending())
        .all()
);
~~~

The callback must invoke a terminal operation and return the corresponding result. This ensures the query executes within Spring Data's managed scope.

## 22. Version Boundaries and Choosing an API

Fluent Query and Specification types have evolved across Spring Data JPA releases. Do not assume every project provides the exact same APIs.

| API | Version Milestone | Notes |
|---|---|---|
| `findAll(spec, pageable)` and `findAll(spec, sort)` | Available in Spring Data JPA lines before Fluent API | Broadly compatible choice |
| `findBy(spec, queryFunction)` | Spring Data JPA 3.0 | Provides basic fluent query for Specifications |
| `SpecificationFluentQuery` and custom count specification | Spring Data JPA 3.5 | Adds `page` with a separate count Specification |
| `PredicateSpecification` | Spring Data JPA 4.0 | Query-type-independent predicate API alongside traditional Specification |
| `findBy(PredicateSpecification, queryFunction)` | Spring Data JPA 4.0 | New fluent entry point for PredicateSpecification |

When a project does not yet support the `findBy` fluent query, use:

~~~java
Page<Customer> page = repository.findAll(spec, pageable);

List<Customer> sorted = repository.findAll(
    spec,
    Sort.by("fullName").ascending()
);
~~~

Before adopting Fluent API examples, check the Spring Data JPA version managed by your Spring Boot BOM and its matching Javadocs. Do not bump a single Spring Data module off the BOM just to grab one method without verifying cross-module compatibility.

## 23. Common Errors and Fixes

### 23.1. Using Database Column Names in Sort

Wrong if the entity property is `createdDate` while the column is `created_date`:

~~~java
Sort.by("created_date")
~~~

Correct:

~~~java
Sort.by("createdDate")
~~~

`Sort` normally references domain model property paths or query aliases, not arbitrary SQL column names.

### 23.2. Page Has Incorrect totalElements

Common causes are a count query using different business filters than the content query, or a collection JOIN multiplying rows. Verify `countSpec`/`countQuery` and ensure root entities are counted accurately.

### 23.3. Page Results Repeat or Skip Rows

Unstable sorting, missing unique tie-breakers, or data mutations between requests can shift rows. Add a unique key to the sort; for large datasets needing stable traversal, consider keyset scrolling or an appropriate snapshot strategy.

### 23.4. Using Page When Total Count Is Unnecessary

Page can incur extra count query overhead. If you only need to know whether another page exists, use Slice. If you only need items within a window, use List with Pageable. For sequential processing of large datasets, consider Window/Scroll API.

### 23.5. Unvalidated Dynamic Sort from Requests

Never pass arbitrary client strings into sort expressions or `JpaSort.unsafe()`. Map them to an allowlist of approved properties.

### 23.6. Calling Fluent Terminal Methods in the Wrong Place

Never return the fluent query object from the callback or save it for later. Call `all()`, `page()`, `first()`, `count()`, or the appropriate terminal method right inside the callback.

### 23.7. Calling an API Missing from the Current Dependency

Compile errors where `findBy`, `SpecificationFluentQuery`, or `PredicateSpecification` cannot be found usually mean your Spring Data JPA version lacks that API. Check your dependency tree and BOM before writing code.

## 24. Testing Pagination, Sorting, and Fluent Queries

Verify both result content and metadata.

Repository test example:

~~~java
@DataJpaTest
class CustomerSpecificationPagingTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void returnsSecondPageInStableOrder() {
        repository.save(new Customer("An", CustomerStatus.ACTIVE));
        repository.save(new Customer("Binh", CustomerStatus.ACTIVE));
        repository.save(new Customer("Chi", CustomerStatus.ACTIVE));
        repository.flush();

        Specification<Customer> spec =
            CustomerSpecifications.hasStatus(CustomerStatus.ACTIVE);

        Page<Customer> page = repository.findAll(
            spec,
            PageRequest.of(
                1,
                2,
                Sort.by("fullName").ascending()
                    .and(Sort.by("id").ascending())
            )
        );

        assertThat(page.getContent()).hasSize(1);
        assertThat(page.getContent().get(0).getFullName())
            .isEqualTo("Chi");
        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }
}
~~~

This example illustrates test structure; constructors, getters, enums, imports, and entity mappings must match your project. If tests run against a real database, ensure deterministic seeded fixtures and sort order.

Cases to test:

1. First page, middle page, and last page.
2. Page index beyond total available pages.
3. Page content and totalElements.
4. `Slice.hasNext()` accuracy when more data exists vs. at the end.
5. Multi-property sorting, ascending/descending directions, and tie-breakers.
6. Null and blank filter parameters.
7. AND/OR Specifications producing the exact matching record set.
8. Count specifications preserving filter conditions.
9. Projections returning exact types and fields.
10. Fluent `first`, `one`, `count`, and `exists` handling 0, 1, and multiple results.
11. Invalid sort requests rejected or mapped to a default.
12. Inspecting SQL and execution plans if queries involve JOINs or slow counts.

## 25. Workflow for Selecting a Query Approach

When building search features, choose based on requirements:

1. Use `Specification` to assemble dynamic filters.
2. Use `Sort` when only sorting is needed; use `Pageable` when a page window is also needed.
3. Use `Page<T>` when UI needs total counts; use `Slice<T>` when only next-page existence is needed; use `List<T>` with Pageable when only page content is needed.
4. Use `findAll(spec, pageable)` when standard execution suffices.
5. Use `findBy(spec, query -> ...)` when projection, limit, sort, and terminal execution need to be combined at one site.
6. From Spring Data JPA 3.5 onward, consider a custom count specification when counting requires separate logic.
7. From Spring Data JPA 4.0 onward, consider `PredicateSpecification` for query-type-independent predicates if running that version.
8. Use deterministic ordering with a unique key as a tie-breaker.
9. Test content, metadata, counts, and performance on the target database.

## 26. Key Takeaways

- `Pageable` describes page index, page size, and optionally Sort; page indices start at 0.
- `Page<T>` supplies total elements/pages and typically runs a count query.
- `Slice<T>` only checks whether a next page exists; `List<T>` with Pageable skips total metadata.
- `Sort` uses entity property paths or query aliases, not arbitrary SQL column names.
- Append a unique key at the end of a sort for deterministic pagination order.
- `JpaSort.unsafe()` should only be used with fixed, trusted expressions; never pass raw client input.
- `JpaSpecificationExecutor` supports `findAll(spec, pageable)` and `findAll(spec, sort)` even without Fluent Query.
- Fluent `findBy(spec, queryFunction)` arrived in Spring Data JPA 3.0; `SpecificationFluentQuery` with custom count specification in 3.5; `PredicateSpecification` in 4.0.
- Fluent Query provides intermediate operations `sortBy`, `limit`, `as`, `project` and terminal operations such as `all`, `first`, `one`, `page`, `slice`, `scroll`, `stream`, `count`, `exists`.
- The query object is only valid inside the callback; the callback must return an executed result.
- Count specifications must preserve the exact same filtering semantics as the content query.
- For large datasets, evaluate scrolling/keyset pagination instead of deep offset pagination.

Combining Specification, Pageable, and Sort enables clear paginated dynamic search. Where supported, Fluent Query lets you control projections, sorting, limits, and return types within a single callback. Choose APIs matching your project's Spring Data JPA version, maintain deterministic ordering, and verify both content and count queries.

## References

- [Spring Data JPA — Specifications and Fluent API](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring Data JPA — Query Methods, Sorting and Pagination](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [JpaSpecificationExecutor API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaSpecificationExecutor.html)
- [SpecificationFluentQuery API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaSpecificationExecutor.SpecificationFluentQuery.html)
