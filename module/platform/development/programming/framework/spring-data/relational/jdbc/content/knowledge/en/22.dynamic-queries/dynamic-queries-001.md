# Expressing Filters with Query and Criteria

In **Spring Data Relational JDBC**, a query may need to filter by multiple properties that a user selects per request. For example, a product search screen lets users filter by status, category, price range, keyword, and creation time. Writing a separate repository method for every combination causes the number of methods to grow rapidly. Concatenating SQL strings arbitrarily makes code hard to maintain and creates SQL injection risks.

Spring Data Relational provides **Query** and **Criteria** to express query conditions in Java. **Criteria** describes conditions on mapped properties; **Query** wraps those conditions along with query options such as sorting, limit, and offset. In Spring Data JDBC, these objects can be used with **JdbcAggregateTemplate** to find, count, check existence of, or delete aggregates matching the conditions.

This lesson focuses on building dynamic filters with Query and Criteria, combining AND/OR conditions, handling optional parameters and empty collections, sorting/pagination, executing queries on aggregates, and the limitations to be aware of when queries become more complex than the aggregate model.

## 1. Why Do We Need Query and Criteria?

Suppose an application manages products. A search request might send:

~~~text
status = ACTIVE
categoryId = 12
minimumPrice = 100000
maximumPrice = 500000
nameContains = "book"
sort = PRICE_ASC
page = 0
size = 20
~~~

Another request might only send status; a third might only send category and keyword. The conditions are not fixed across every call.

There are three common approaches:

1. Declare multiple derived query methods for each case.
2. Write a single SQL query with many optional condition branches.
3. Build conditions from the provided parameters and create a Query to execute.

Query and Criteria make the third approach clearer:

~~~text
SearchFilter
    |
    v
Create Criteria from filters with values
    |
    v
Combine conditions
    |
    v
Query(criteria)
    +-- sort
    +-- limit
    +-- offset
    |
    v
JdbcAggregateTemplate
    |
    v
SQL generated according to mapping and dialect
    |
    v
Resulting aggregates
~~~

Instead of manually concatenating SQL for every combination, the application describes conditions in terms of domain properties and lets Spring Data JDBC generate statements matching the mapping metadata.

## 2. Roles of Criteria and Query

The two commonly used classes reside in the package:

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
~~~

### 2.1. Criteria Expresses Conditions

Criteria describes one or more conditions on mapped properties. For example:

~~~java
Criteria.where("status").is("ACTIVE");
~~~

This condition means the status property equals ACTIVE.

Combining additional conditions:

~~~java
Criteria.where("status").is("ACTIVE")
        .and("priceMinorUnits").greaterThanOrEquals(100_000L);
~~~

This condition expresses:

~~~sql
status = 'ACTIVE'
AND price_minor_units >= 100000
~~~

This is a logical description; the actual SQL is generated and parameterized by the framework.

### 2.2. Query Wraps Query Conditions

Query combines Criteria with read options:

~~~java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
);
~~~

Query can also carry sort, limit, and offset:

~~~java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
).sort(Sort.by(Sort.Order.desc("createdAt")))
 .limit(20)
 .offset(0);
~~~

Import Sort:

~~~java
import org.springframework.data.domain.Sort;
~~~

Criteria answers **which rows to filter**; Query describes **how to query that dataset**, such as ordering and the number of results.

### 2.3. Query and Criteria Are Not SQL Strings

This is a Java DSL (domain-specific language) for relational queries. When using:

~~~java
Criteria.where("priceMinorUnits").greaterThan(100_000L)
~~~

we are describing a condition on a mapped Java property. Spring Data Relational uses metadata to translate the property into a column name matching the schema/naming strategy.

This differs from SQL in @Query, where the author uses database table and column names. Do not pass arbitrary SQL column names into Criteria if they are not the property names expected by the mapping.

## 3. Executing a Query with JdbcAggregateTemplate

Spring Data JDBC provides JdbcAggregateTemplate to operate on aggregates using Query/Criteria objects.

Example injecting the template:

~~~java
import java.util.List;
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final JdbcAggregateTemplate template;

    public ProductSearchService(JdbcAggregateTemplate template) {
        this.template = template;
    }

    public List<Product> findActiveProducts() {
        Query query = Query.query(
                Criteria.where("status").is("ACTIVE")
        );
        return template.findAll(query, Product.class);
    }
}
~~~

Common template operations include:

| Operation | Purpose |
| --- | --- |
| findAll(query, type) | Find all matching aggregates |
| findOne(query, type) | Find one matching aggregate |
| count(query, type) | Count matching aggregates |
| exists(query, type) | Check whether any matching aggregate exists |
| delete(query, type) | Delete aggregates matching the condition |

Exact API names and signatures should be verified against the Spring Data JDBC version used by the application. The examples in this lesson use common JdbcAggregateTemplate APIs of Spring Data JDBC.

### 3.1. Why Use the Template Instead of Repository Methods?

Repository interfaces fit queries with fixed contracts, for example:

~~~java
Optional<Product> findBySku(String sku);
List<Product> findByStatus(String status);
~~~

When filters vary by request, a service can build a Query and call the template. This avoids declaring a method for every filter combination.

There is no need to replace every repository with JdbcAggregateTemplate. You can keep repositories for CRUD and derived queries, and use the template in a service or custom repository fragment only for dynamic search.

## 4. Common Criteria Operators

Criteria provides common comparison and check operations.

| Operator | Example | Meaning |
| --- | --- | --- |
| is | where("status").is("ACTIVE") | Equals value |
| not | where("status").not("DELETED") | Not equal to value |
| isNull | where("deletedAt").isNull() | Column is SQL NULL |
| isNotNull | where("deletedAt").isNotNull() | Column is not NULL |
| greaterThan | where("price").greaterThan(100) | Greater than |
| greaterThanOrEquals | where("price").greaterThanOrEquals(100) | Greater than or equal to |
| lessThan | where("price").lessThan(500) | Less than |
| lessThanOrEquals | where("price").lessThanOrEquals(500) | Less than or equal to |
| between | where("price").between(100, 500) | Within range |
| in | where("status").in(values) | In set of values |
| notIn | where("status").notIn(values) | Not in set of values |
| like | where("name").like("%book%") | Matches SQL LIKE pattern |

Specific operators may vary across releases. Check your project's dependency API if you need a less common operation.

### 4.1. Equality and Inequality Comparisons

~~~java
Criteria active = Criteria.where("status").is("ACTIVE");

Criteria notDeleted = Criteria.where("status").not("DELETED");
~~~

If the domain uses an enum value:

~~~java
Criteria criteria = Criteria.where("status").is(ProductStatus.ACTIVE);
~~~

How an enum is converted to its stored value depends on the entity's mapping/converter. Use the same representation type configured by Spring Data JDBC for that property.

### 4.2. Numeric and Date/Time Comparisons

~~~java
Criteria priceRange = Criteria.where("priceMinorUnits")
        .greaterThanOrEquals(100_000L)
        .and("priceMinorUnits")
        .lessThanOrEquals(500_000L);
~~~

For timestamps:

~~~java
Criteria createdAfter = Criteria.where("createdAt")
        .greaterThanOrEquals(fromTime);
~~~

The passed value type should be compatible with the property type. Avoid comparing a timestamp column against a custom-formatted date/time string, which can cause implicit conversions, timezone bugs, or prevent index usage.

### 4.3. IN and NOT IN

~~~java
Criteria statuses = Criteria.where("status")
        .in(List.of("ACTIVE", "PENDING"));
~~~

Equivalent condition:

~~~sql
status IN ('ACTIVE', 'PENDING')
~~~

For an exclusion list:

~~~java
Criteria excluded = Criteria.where("status")
        .notIn(List.of("DELETED", "ARCHIVED"));
~~~

Do not pass an empty collection without defining its meaning. SQL may reject an empty IN list, or the framework may handle it in a specific way. Handle that case at the application layer before creating Criteria.

### 4.4. BETWEEN

~~~java
Criteria price = Criteria.where("priceMinorUnits")
        .between(100_000L, 500_000L);
~~~

BETWEEN is typically inclusive on both ends. If business rules require a half-open interval, such as an inclusive start date and an exclusive end date, use two conditions:

~~~java
Criteria period = Criteria.where("createdAt")
        .greaterThanOrEquals(startInclusive)
        .and("createdAt")
        .lessThan(endExclusive);
~~~

This approach typically fits [start, end) time ranges and avoids bugs when timestamps have differing fractional-second precision.

### 4.5. LIKE

~~~java
Criteria nameContains = Criteria.where("name").like("%book%");
~~~

LIKE uses SQL wildcards:

- % matches any sequence of characters, including empty.
- _ matches a single character.

If user input is placed into a LIKE pattern, decide whether wildcards are allowed. To search for literal text, escape wildcard characters according to the appropriate SQL/database rules.

Case-insensitivity of LIKE depends on the database/collation or transformations used. Do not assume a LIKE criterion automatically has the same semantics as IgnoreCase in a derived query across every dialect.

## 5. Combining AND and OR Conditions

### 5.1. Combining with AND

For example, a product must be ACTIVE and have a price of at least 100,000:

~~~java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .and("priceMinorUnits").greaterThanOrEquals(100_000L);
~~~

Logic:

~~~sql
WHERE status = 'ACTIVE'
  AND price_minor_units >= 100000
~~~

Each additional condition narrows the result set.

### 5.2. Combining with OR

For example, accepting two statuses:

~~~java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .or("status").is("PENDING");
~~~

Logic:

~~~sql
WHERE status = 'ACTIVE'
   OR status = 'PENDING'
~~~

When using OR, the result count can increase because only one branch needs to match.

### 5.3. Be Careful with Complex AND/OR Expressions

Consider the requirement:

~~~text
(status = ACTIVE OR status = PENDING)
AND price >= 100000
~~~

These are two distinct logical groups. Do not write a long chain of AND/OR and rely on memory for precedence. In SQL, AND normally has higher precedence than OR; without parentheses, the expression can be evaluated differently than intended.

For nested multi-group conditions:

- Separate logical groups into distinct Criteria instances using the composition API supported by your version.
- Inspect the generated SQL to confirm parentheses.
- Write integration tests with data that distinguishes each branch.
- If the expression becomes too complex or needs joins/subqueries, consider @Query or a custom repository.

Do not assume every way of chaining Criteria produces the exact parenthesized grouping you imagine. Check the specific API of your release.

### 5.4. Example Verifying Logic with Data

Given the condition:

~~~text
(ACTIVE OR PENDING) AND price >= 100
~~~

| Product | Status | Price | Matches? |
| --- | --- | ---: | --- |
| A | ACTIVE | 150 | Yes |
| B | PENDING | 100 | Yes |
| C | ACTIVE | 50 | No |
| D | ARCHIVED | 200 | No |

Tests should also cover cases where one OR branch is true but the final AND condition is false.

## 6. Building Criteria from Optional Filters

This is the most common use case for Query/Criteria. We do not know in advance which filters a request will include.

Define the filter:

~~~java
public record ProductFilter(
        String status,
        Long categoryId,
        Long minimumPrice,
        Long maximumPrice,
        String nameContains,
        List<String> statuses
) {
}
~~~

Build Criteria for each present value:

~~~java
Criteria criteria = Criteria.empty();

if (filter.status() != null) {
    criteria = criteria.and("status").is(filter.status());
}

if (filter.categoryId() != null) {
    criteria = criteria.and("categoryId").is(filter.categoryId());
}

if (filter.minimumPrice() != null) {
    criteria = criteria.and("priceMinorUnits")
            .greaterThanOrEquals(filter.minimumPrice());
}

if (filter.maximumPrice() != null) {
    criteria = criteria.and("priceMinorUnits")
            .lessThanOrEquals(filter.maximumPrice());
}

if (filter.nameContains() != null
        && !filter.nameContains().isBlank()) {
    criteria = criteria.and("name")
            .like("%" + filter.nameContains().trim() + "%");
}

Query query = Query.query(criteria);
List<Product> products = template.findAll(query, Product.class);
~~~

The idea behind this code:

1. Start from an empty Criteria.
2. Add a condition only when the filter has a value.
3. Combine conditions with AND.
4. Create a Query from the final Criteria.
5. Use JdbcAggregateTemplate to read aggregates.

Properties in Criteria are the mapped property names of Product, such as categoryId or priceMinorUnits. Spring Data Relational handles translating them into column names using the mapping context.

### 6.1. Null Means No Filter Applied

In the example, a null status means the caller did not request filtering by status. No status condition is added.

This is an API convention that should be explicitly documented. If null means "find records whose status is SQL NULL", build an isNull Criteria instead of skipping the filter.

### 6.2. Distinguishing Null, Empty Strings, and Whitespace-Only Strings

For text filters:

- null: do not apply filter.
- empty string: usually treated as no keyword.
- whitespace-only string: usually trimmed and then treated as no keyword.
- non-empty string: add search condition.

Example:

~~~java
if (filter.nameContains() != null
        && !filter.nameContains().isBlank()) {
    String term = filter.nameContains().trim();
    criteria = criteria.and("name").like("%" + term + "%");
}
~~~

If search rules require an empty string to be a meaningful value, do not skip it automatically.

### 6.3. Price Range Filters

Users may enter only a minimum price, only a maximum price, or both:

~~~java
if (filter.minimumPrice() != null) {
    criteria = criteria.and("priceMinorUnits")
            .greaterThanOrEquals(filter.minimumPrice());
}

if (filter.maximumPrice() != null) {
    criteria = criteria.and("priceMinorUnits")
            .lessThanOrEquals(filter.maximumPrice());
}
~~~

Before querying, validate that minimum is not greater than maximum:

~~~java
if (filter.minimumPrice() != null
        && filter.maximumPrice() != null
        && filter.minimumPrice() > filter.maximumPrice()) {
    throw new IllegalArgumentException(
            "Minimum price must not exceed maximum price"
    );
}
~~~

Input validation prevents meaningless queries and clarifies the API contract.

## 7. IN Filters and Empty Collection Conventions

An empty parameter collection requires an explicit decision because it can have two meanings:

1. The caller selected no values and wants to skip the filter.
2. The caller intentionally supplied an empty set, so no records are allowed to match.

Do not let semantics depend accidentally on how the framework or database handles an empty IN clause.

Example status filter:

~~~java
public record ProductFilter(List<String> statuses) {
}
~~~

Convention:

| statuses value | Chosen meaning in this example |
| --- | --- |
| null | Do not filter by status |
| Empty list | No statuses allowed; return empty result |
| Non-empty list | Only include statuses in the set |

Implementation:

~~~java
if (filter.statuses() != null) {
    if (filter.statuses().isEmpty()) {
        return List.of();
    }
    criteria = criteria.and("status").in(filter.statuses());
}
~~~

If the API convention treats an empty list as "skip filter", implement that deliberately and document it in the contract. Do not apply the same handling blindly across every endpoint without considering business meaning.

### 7.1. Filtering Out Null Elements

A status list such as:

~~~java
List.of("ACTIVE", null, "PENDING")
~~~

is invalid with List.of and should also not be used as a filter set. Check for null elements before building Criteria. If null represents a SQL NULL status, express that condition with isNull or a separate logic branch.

### 7.2. Limiting IN Set Size

A very large ID list can generate SQL with many placeholders, exceed database/driver limits, or slow down queries. You should:

- Limit the number of input elements.
- Batch requests if business logic permits.
- Use temporary tables/table-valued parameters or an appropriate database mechanism when sets are very large.
- Measure execution plans and bind overhead.

## 8. Building Queries with Sort, Limit, and Offset

Query carries not only Criteria but also sorting and result-limiting options.

Example:

~~~java
Query query = Query.query(criteria)
        .sort(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")
        ))
        .limit(20)
        .offset(0);
~~~

Meaning:

- Sort by createdAt descending.
- When createdAt values are equal, sort by id ascending for deterministic ordering.
- Return at most 20 results.
- Skip 0 preceding results.

### 8.1. Whitelisting Sort Properties

If users send a sort field from the API, do not pass an arbitrary string directly into Sort. Allow only supported properties:

~~~java
Sort sort = switch (requestedSort) {
    case NEWEST -> Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("id")
    );
    case PRICE_LOW_TO_HIGH -> Sort.by(
            Sort.Order.asc("priceMinorUnits"),
            Sort.Order.asc("id")
    );
    case NAME -> Sort.by(
            Sort.Order.asc("name"),
            Sort.Order.asc("id")
    );
};
~~~

Whitelisting prevents requests from sorting by nonexistent properties or properties that must not be exposed.

### 8.2. Capping Page Size

Do not let callers request an unbounded page size:

~~~java
int pageSize = Math.min(Math.max(requestedSize, 1), 100);
long offset = (long) page * pageSize;
~~~

Using long for offset reduces overflow risk when multiplying page and pageSize. Also validate that page is non-negative and cap total pages/offset according to application needs.

### 8.3. Offset Pagination and Keyset Pagination

Offset pagination is straightforward:

~~~java
Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Order.asc("id")))
        .limit(pageSize)
        .offset((long) page * pageSize);
~~~

When offset is very large, the database may have to scan/skip many rows before returning the page. Keyset pagination is often more efficient when there is a stable sort key:

~~~java
Criteria afterLastSeen = Criteria.where("id").greaterThan(lastSeenId);
Query query = Query.query(afterLastSeen)
        .sort(Sort.by(Sort.Order.asc("id")))
        .limit(pageSize);
~~~

Keyset pagination needs to combine the initial filters with the condition after the last seen key. The example above only illustrates the simple case of sorting by ascending ID. If sorting by multiple columns, the cursor must carry enough values to construct the exact continuation condition.

## 9. Using Query for find, count, exists, and delete

A single Criteria can be reused across operations with different purposes.

~~~java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .and("categoryId").is(categoryId);

Query query = Query.query(criteria);

List<Product> products = template.findAll(query, Product.class);
long count = template.count(query, Product.class);
boolean exists = template.exists(query, Product.class);
~~~

Operations:

- findAll: returns a list of matching aggregates.
- count: returns the number of matching aggregates.
- exists: returns true if at least one match exists.
- delete: deletes matching aggregates.

### 9.1. Caution with delete(Query)

Deleting by Criteria can affect many aggregates. Before calling it:

- Verify the condition is sufficiently narrow.
- Check the count first if the use case requires confirmation.
- Configure an appropriate transaction.
- Review foreign keys and child relationships.
- Check history-retention/soft-delete policies.

Do not pass a Query whose optional filters are all null into delete. An empty Criteria can result in a very broad scope depending on the API and mapping. For destructive operations, require explicit mandatory conditions and verify before execution.

### 9.2. count and findAll Have Different Costs

If you only need the total result count, use count instead of loading all aggregates and calling size. If you only need to know whether at least one result exists, use exists instead of findAll.

These operations let the database perform more appropriate work and avoid materializing unnecessary object graphs.

## 10. Separating Request Filters from Criteria

Do not let controllers construct Criteria directly from requests. Use an application filter/criteria object to establish semantics before translating to the persistence DSL.

Example:

~~~java
public record ProductSearchRequest(
        String status,
        Long categoryId,
        Long minPrice,
        Long maxPrice,
        String keyword,
        Integer page,
        Integer size
) {
}
~~~

The service converts the request into a validated filter:

~~~java
public record ProductSearchFilter(
        String status,
        Long categoryId,
        Long minPrice,
        Long maxPrice,
        String keyword
) {
}
~~~

Benefits:

- The API does not depend directly on Spring Data classes.
- Validation and null/empty semantics live at the application boundary.
- Query implementations can change without breaking the HTTP contract.
- Filter logic can be unit tested without a database.
- The same filter can be used across multiple query implementations.

### 10.1. Validation Before Creating Criteria

Example:

~~~java
private ProductSearchFilter validate(ProductSearchRequest request) {
    if (request.minPrice() != null
            && request.maxPrice() != null
            && request.minPrice() > request.maxPrice()) {
        throw new IllegalArgumentException("Invalid price range");
    }

    if (request.page() != null && request.page() < 0) {
        throw new IllegalArgumentException("page must not be negative");
    }

    if (request.size() != null
            && (request.size() < 1 || request.size() > 100)) {
        throw new IllegalArgumentException("size must be between 1 and 100");
    }

    String keyword = request.keyword();
    if (keyword != null) {
        keyword = keyword.trim();
        if (keyword.isEmpty()) {
            keyword = null;
        }
    }

    return new ProductSearchFilter(
            request.status(),
            request.categoryId(),
            request.minPrice(),
            request.maxPrice(),
            keyword
    );
}
~~~

After validation, Criteria construction code is simpler because it no longer has to handle invalid data or inconsistent states.

## 11. Extracting Query Building into a Separate Component

If a service has multiple search use cases, Query-building logic can be extracted:

~~~java
public class ProductQueryFactory {

    public Query create(ProductSearchFilter filter, Sort sort,
                        int limit, long offset) {

        Criteria criteria = Criteria.empty();

        if (filter.status() != null) {
            criteria = criteria.and("status").is(filter.status());
        }

        if (filter.categoryId() != null) {
            criteria = criteria.and("categoryId").is(filter.categoryId());
        }

        if (filter.minPrice() != null) {
            criteria = criteria.and("priceMinorUnits")
                    .greaterThanOrEquals(filter.minPrice());
        }

        if (filter.maxPrice() != null) {
            criteria = criteria.and("priceMinorUnits")
                    .lessThanOrEquals(filter.maxPrice());
        }

        if (filter.keyword() != null) {
            criteria = criteria.and("name")
                    .like("%" + filter.keyword() + "%");
        }

        return Query.query(criteria)
                .sort(sort)
                .limit(limit)
                .offset(offset);
    }
}
~~~

The factory does not execute SQL. It only converts a validated filter into a Query. The service or custom repository is responsible for calling JdbcAggregateTemplate.

### 11.1. Unit Testing the Query Factory

Validation and filter selection can be tested independently of the database. However, inspecting internal Criteria objects may depend on the framework's equals/toString APIs. A reliable approach is integration testing query results against a database with representative fixtures.

## 12. How Criteria Works with Mapped Properties

When writing:

~~~java
Criteria.where("priceMinorUnits").greaterThan(100_000L);
~~~

the argument is typically the property name in the domain entity model. Spring Data Relational uses the mapping context to resolve that property to the column name in the schema.

Example:

~~~java
@Table("products")
public class Product {

    @Id
    private Long id;

    @Column("price_minor_units")
    private long priceMinorUnits;
}
~~~

Criteria uses:

~~~java
Criteria.where("priceMinorUnits").greaterThan(100_000L);
~~~

rather than necessarily using the string price_minor_units. When property mapping is customized with @Column, the framework can translate the property to the declared column.

### 12.1. Unmapped Properties

A @Transient field is not a persistent property. You cannot use Criteria to filter in SQL by a value that exists only in memory:

~~~java
@Transient
private String displayLabel;
~~~

If filtering by displayLabel is needed, identify the underlying database source or an appropriate SQL expression. Criteria cannot query an attribute that has no persistence mapping.

### 12.2. Embedded Value Objects

For value objects embedded with @Embedded, how sub-properties are referenced depends on the mapping path and the Spring Data Relational version. Verify how the DSL supports property paths for embedded objects in your release. If a path is unsupported or the condition is complex, consider an explicit SQL query.

## 13. Limitations of Criteria and Query

Query/Criteria is not a replacement for every SQL statement.

Typically suitable for:

- Filtering aggregate roots by mapped properties.
- Comparisons, ranges, null checks, IN, and LIKE.
- Combining conditions.
- Sorting and limiting results.
- Counting, checking existence, and deleting by condition.

Do not assume the DSL can express every SQL feature:

- Arbitrary joins across multiple aggregate roots.
- Complex CTEs.
- Window functions.
- Deeply nested subqueries.
- Vendor-specific expressions.
- Complex multi-table aggregate projections.
- Dynamic table/column identifiers.

When those capabilities are needed, use @Query or a custom repository with JdbcClient/NamedParameterJdbcTemplate. Choose based on the shape of the problem instead of forcing every query into Criteria.

### 13.1. Aggregate Queries Differ from Reporting Queries

JdbcAggregateTemplate operates on aggregate mappings. A Query for Product returns Product aggregates according to the mapping. If you need a joined result across Product, Category, and Supplier in a DTO, that is a read projection; use an appropriate SQL/projection approach instead of expecting Query/Criteria to construct arbitrary joins.

### 13.2. Do Not Use Criteria as a Substitute for Database Protections

Criteria only describes conditions sent by the application to the database. It does not replace:

- Primary keys and unique constraints.
- Foreign keys.
- Check constraints.
- Access authorization.
- Business validation.
- Transactions and optimistic locking.

For example, checking whether an SKU exists before inserting does not replace a unique constraint on SKU. Two concurrent requests can still both pass the check.

## 14. Combining Query/Criteria with Transactions

A simple read query can be called from a read-only service method:

~~~java
@Transactional(readOnly = true)
public List<Product> search(ProductSearchFilter filter) {
    Criteria criteria = buildCriteria(filter);
    Query query = Query.query(criteria);
    return template.findAll(query, Product.class);
}
~~~

For multi-step operations, place the transaction at the service boundary so commands sharing the same datasource participate in a transaction according to configuration.

When using Query to delete:

~~~java
@Transactional
public void deleteDiscontinuedProducts() {
    Criteria criteria = Criteria.where("status").is("DISCONTINUED");
    Query query = Query.query(criteria);
    template.delete(query, Product.class);
}
~~~

Only use deletion when the condition is clearly defined and data policy permits deleting rows. If history must be retained, use soft delete or an archival workflow.

### 14.1. Read-Only Does Not Guarantee an Absolute Snapshot

@Transactional(readOnly = true) expresses read intent. Consistency across multiple SQL statements depends on transaction isolation and the database. If a use case requires a consistent snapshot, choose an appropriate isolation level and test on the target database.

## 15. Handling Sort and Filters Safely

Criteria binds condition values using the framework's mechanisms. Still, the API must validate inputs:

- Do not let requests sort by arbitrary properties.
- Validate limits on filter count and IN list size.
- Validate min/max bounds.
- Define null/empty semantics explicitly.
- Normalize strings according to domain rules.
- Never accept raw SQL from clients.

Sorting should be mapped from an enum:

~~~java
public enum ProductSort {
    NEWEST,
    NAME,
    PRICE_LOW_TO_HIGH
}
~~~

~~~java
private Sort toSort(ProductSort sort) {
    return switch (sort) {
        case NEWEST -> Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
        );
        case NAME -> Sort.by(
                Sort.Order.asc("name"),
                Sort.Order.asc("id")
        );
        case PRICE_LOW_TO_HIGH -> Sort.by(
                Sort.Order.asc("priceMinorUnits"),
                Sort.Order.asc("id")
        );
    };
}
~~~

Only properties explicitly permitted by developers can be used as sort fields. Adding a secondary key like id keeps ordering stable when primary sort values tie.

## 16. Testing Dynamic Filters

An integration test should prepare products with different statuses, categories, and prices, then verify each filter combination.

Example data:

| SKU | Status | Category | Price |
| --- | --- | ---: | ---: |
| BOOK-A | ACTIVE | 10 | 150000 |
| BOOK-B | ACTIVE | 10 | 300000 |
| PEN-A | ACTIVE | 20 | 20000 |
| BOOK-C | PENDING | 10 | 180000 |
| BOOK-D | ARCHIVED | 10 | 250000 |

Filter:

~~~java
ProductSearchFilter filter = new ProductSearchFilter(
        "ACTIVE",
        10L,
        100_000L,
        250_000L,
        "BOOK"
);
~~~

Expected result includes BOOK-A. Tests should verify:

- Each condition applies when it has a value.
- Conditions are omitted when filters are null according to the contract.
- Min/max include boundaries properly.
- Search strings handle wildcards as intended.
- Sorting produces a deterministic order.
- Limit/offset return the expected page.
- Empty IN collections follow the defined semantics.
- Missing matches return an empty list.

### 16.1. Testing Against a Real Database

Query/Criteria is translated into SQL according to the dialect. Even though the DSL reduces syntax coupling, behavior can still be affected by:

- Data types and collation.
- Null semantics.
- LIKE escaping.
- Boolean representation.
- Limit/offset.
- Indexes and optimizer behavior.

For critical queries, run integration tests against the production database engine or corresponding Testcontainers. H2 is useful for fast checks, but it does not replace real dialect testing when differences exist.

### 16.2. Inspecting Generated SQL

In test/dev environments, enable appropriate logging or use a datasource proxy to observe:

- Columns and WHERE conditions.
- Parameter binding.
- ORDER BY.
- Limit/offset.
- Number of queries executed.
- Query plans and indexes when needed.

Do not log sensitive data in production without proper protection policies.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using SQL column names instead of mapped properties | Criteria cannot find property or maps incorrectly | Use Java property names and verify @Column/naming strategy |
| Adding a null filter as an equality-to-null condition | SQL semantics do not match expectations | Skip the filter or use isNull per contract |
| Passing an empty IN collection | Unclear SQL or semantics | Handle empty sets before building Criteria |
| Chaining many AND/OR without checking grouping | Logical condition differs from requirements | Split groups, inspect SQL, and write integration tests |
| Sorting by a raw property from the request | Invalid properties or expanded attack surface | Use an enum/whitelist |
| Using Criteria to join another aggregate | DSL does not support arbitrary joins | Use @Query or custom JDBC |
| Using Query to return complex reporting DTOs | Confuses aggregate mapping with read projection | Write dedicated SQL/projections |
| Calling delete(Query) with an empty filter | Can delete an overly broad scope | Require safe mandatory conditions and check beforehand |
| Loading everything and filtering in Java | Wastes memory and database round trips | Push conditions down into Query/Criteria |
| Using very large offsets | Slow queries | Consider keyset pagination |
| Not validating filter types | Implicit driver/DB conversions or errors | Use types compatible with properties |
| Assuming Criteria replaces unique constraints | Duplicate data can still appear concurrently | Enforce invariants in the database |

## 18. Workflow for Building Dynamic Filters

When implementing a search screen:

1. **Define the filter contract.** Specify null, empty string, empty collection, and default value behavior.
2. **Validate input.** Check numeric/date ranges, IN set sizes, page size, and sort options.
3. **Build Criteria.** Start from an empty Criteria and add conditions for validated filters.
4. **Combine logic.** Use AND/OR intentionally; verify grouping for complex expressions.
5. **Create Query.** Attach sort, limit, and offset.
6. **Choose the operation.** findAll for aggregates, count for totals, exists when only a boolean is needed.
7. **Keep boundaries clear.** Use Query/Criteria for aggregate mapping; use SQL/projections for complex joins and reports.
8. **Manage transactions.** Set service-level boundaries when a use case spans multiple operations.
9. **Test semantics.** Cover matching rows, empty results, null, empty sets, boundaries, and multiple logical groups.
10. **Measure performance.** Observe SQL, indexes, execution plans, and result sizes.

## Key Takeaways

**Criteria** describes filter conditions on mapped properties; **Query** combines Criteria with sort, limit, and offset; **JdbcAggregateTemplate** executes find, count, exists, or delete operations on aggregates using a Query.

When building dynamic filters, add conditions only when a filter is meaningful, define null and empty collection semantics explicitly, whitelist sort fields, and verify AND/OR grouping. Query/Criteria fits mapped aggregate queries. When arbitrary joins, CTEs, window functions, or complex reporting projections are required, use custom SQL or a custom repository. This separation keeps filters flexible while preserving aggregate boundaries, type safety, and clear layer responsibilities.
