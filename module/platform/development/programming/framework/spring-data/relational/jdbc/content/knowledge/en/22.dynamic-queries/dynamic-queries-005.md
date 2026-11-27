# Column Selection, Sorting, Limiting, and Pagination in Query

In Spring Data JDBC, when a query must be built from conditions that vary at runtime, you can use **§org.springframework.data.relational.core.query.Query§** together with §Criteria§, §Sort§, and §Pageable§. This object describes the main parts of a SELECT statement: filter conditions, list of columns to fetch, sort order, maximum number of rows, and number of rows to skip.

The §Query§ object is executed via §JdbcAggregateTemplate§ or §JdbcAggregateOperations§. This approach fits when a service needs to construct queries from multiple optional filters, select a subset of columns, vary sorting, and limit results without manually concatenating SQL strings.

Four capabilities to master:

- **Column selection:** use §columns(...)§ to restrict the columns in SELECT.
- **Sorting:** use §sort(Sort)§ to specify result ordering.
- **Limiting:** use §limit(int)§ to cap the number of rows and §offset(long)§ to skip a number of rows.
- **Pagination:** use §with(Pageable)§ to apply offset, limit, and sort together from a page request.

This lesson focuses on the Spring Data JDBC §Query§ API, building dynamic queries, returning paginated results, and understanding the caveats of selecting only a subset of an aggregate's columns.

## 1. What Is Query in Spring Data JDBC?

§Query§ is a value object describing a relational query. It can hold:

| Component | API | Role |
| --- | --- | --- |
| Conditions | §Criteria§ / §CriteriaDefinition§ | Builds the WHERE clause. |
| Column list | §columns(...)§ | Selects which columns to read. |
| Sorting | §sort(Sort)§ | Builds ORDER BY. |
| Limit | §limit(int)§ | Caps the number of returned rows. |
| Offset | §offset(long)§ | Skips leading rows according to ordering. |
| Pagination | §with(Pageable)§ | Applies offset, limit, and sort together. |

Example querying a single person by name:

§§§java
Query query = Query.query(
        Criteria.where("name").is("Gandalf")
);

Optional<Person> person =
        jdbcAggregateTemplate.findOne(query, Person.class);
§§§

§Query.query(criteria)§ creates a query with a condition. §findOne§ executes the query and returns an §Optional§; if there is no match it returns §Optional.empty()§, and if there is more than one match it throws an incorrect result size error.

Unlike derived method names such as §findByStatusAndCategoryId§, §Query§ lets the service decide at runtime which filters to include.

### 1.1. The Query API Differs from the @Query Annotation

Two APIs are easy to confuse:

| API | Package | Purpose |
| --- | --- | --- |
| §Query§ class | §org.springframework.data.relational.core.query.Query§ | Builds queries via Java API. |
| §@Query§ annotation | §org.springframework.data.jdbc.repository.query.Query§ | Declares string-based SQL on repository methods. |

Example of the §Query§ class:

§§§java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
).limit(20);
§§§

Example of the §@Query§ annotation:

§§§java
@Query("SELECT * FROM products WHERE status = :status")
List<Product> findActiveProducts(String status);
§§§

This lesson covers the §Query§ object used with §JdbcAggregateTemplate§. With string-based SQL in §@Query§, the application writes the SQL itself and must manage limiting/sorting according to the rules supported by that API.

## 2. JdbcAggregateTemplate Executes Query

§JdbcAggregateTemplate§ is a lower-level API for reading and persisting aggregates. When configuring Spring Data JDBC, the framework provides it as a Spring bean, so it can be injected into services or custom repository fragments.

Example:

§§§java
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final JdbcAggregateTemplate jdbc;

    public ProductSearchService(JdbcAggregateTemplate jdbc) {
        this.jdbc = jdbc;
    }
}
§§§

Common read methods:

| Method | Result |
| --- | --- |
| §findOne(Query, Class<T>)§ | §Optional<T>§, expects at most one match. |
| §findAll(Query, Class<T>)§ | §List<T>§ of matching aggregates. |
| §streamAll(Query, Class<T>)§ | §Stream<T>§ for sequential reading. |
| §count(Query, Class<T>)§ | Number of aggregates matching the condition. |
| §exists(Query, Class<T>)§ | Checks whether any aggregate matches the condition. |

Example:

§§§java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
);

List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

§findAll(Query, Class)§ returns a list of mapped aggregates. If an aggregate has owned child entities, Spring Data JDBC still applies the corresponding aggregate-loading mechanism; Query does not turn a repository into an arbitrary flat-table API.

## 3. Creating Queries Without Conditions or with Criteria

There are two basic ways to create a query.

### 3.1. Query.empty()

Use when no WHERE condition is needed:

§§§java
Query query = Query.empty();
§§§

You can chain sort, limit, offset, or columns:

§§§java
Query query = Query.empty()
        .sort(Sort.by("name").ascending())
        .limit(20);
§§§

This query fetches at most 20 results sorted by name ascending.

### 3.2. Query.query(Criteria)

Use when there are conditions:

§§§java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
);
§§§

Equivalent condition:

§§§sql
WHERE status = ?
§§§

Values are bound through JDBC; there is no need to concatenate input values into SQL.

### 3.3. Combining Multiple Conditions

§Criteria§ supports comparisons such as §is§, §greaterThan§, §lessThan§, §between§, §in§, §like§, §isNull§, and §isNotNull§. Conditions can be combined with §and§ and §or§.

Example:

§§§java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .and("price").greaterThanOrEquals(new BigDecimal("100"))
        .and("stock_quantity").greaterThan(0);

Query query = Query.query(criteria);
§§§

SQL meaning:

§§§sql
WHERE status = 'ACTIVE'
  AND price >= 100
  AND stock_quantity > 0
§§§

Condition groups can be used:

§§§java
Criteria criteria = Criteria.from(
        Criteria.where("status").is("ACTIVE"),
        Criteria.where("price").greaterThanOrEquals(
                new BigDecimal("100")
        )
);
§§§

§Criteria§ is also an immutable API: each chained condition returns a new object. When building dynamic conditions, reassign the variable:

§§§java
Criteria criteria = Criteria.where("status").is("ACTIVE");

if (minimumPrice != null) {
    criteria = criteria.and("price").greaterThanOrEquals(minimumPrice);
}

if (maximumPrice != null) {
    criteria = criteria.and("price").lessThanOrEquals(maximumPrice);
}

Query query = Query.query(criteria);
§§§

If you forget to reassign the result of §and§ or §or§, the new condition will not be included in the original query variable.

## 4. Selecting Columns with columns(...)

§Query.columns(...)§ specifies which columns to select in the SELECT statement.

Example fetching only ID, name, and status:

§§§java
Query query = Query.empty()
        .columns("id", "name", "status");

List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

Conceptual SQL:

§§§sql
SELECT id, name, status
FROM products;
§§§

If §columns(...)§ is not called, the query selects the default column set from the aggregate mapping. When §columns(...)§ is called, the selected column list is restricted to the specified names.

### 4.1. Column Names Must Match the Mapping

Spring Data Relational uses a naming strategy to convert Java property names to column names. By default convention, a property §createdAt§ typically maps to column §created_at§. When §@Column§ is present, the declared column name is used explicitly.

Example:

§§§java
@Table("products")
public class Product {

    @Id
    private Long id;

    private String name;

    @Column("created_at")
    private LocalDateTime createdAt;
}
§§§

When selecting columns, use the SQL column names matching the mapping, such as §created_at§. If the schema uses custom names, pass the exact declared identifiers.

Since Spring Data Relational 4.1, §Query§ also provides §columnsOf(...)§ accepting §TypedPropertyPath§ values to select columns using typed property paths. This API helps reduce reliance on string column names where appropriate.

### 4.2. Selecting Columns Does Not Automatically Turn Results into a DTO

Important reminder: §findAll(query, Product.class)§ still requires mapping results into type §Product§. §columns(...)§ only alters the SELECT column list; it does not automatically create a new projection interface or DTO.

For example, if §Product§ has a required constructor:

§§§java
public record Product(
        Long id,
        String name,
        BigDecimal price,
        String status
) {
}
§§§

but the query selects only §id§ and §name§:

§§§java
Query query = Query.empty().columns("id", "name");
List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

the mapper lacks data to invoke the constructor that expects §price§ and §status§. With a mutable type having a no-arg constructor, unselected properties may remain unset with default/null values.

Therefore:

- Only select a column subset when the result type can be safely mapped from those columns.
- Never pass a partially loaded aggregate as input to §save§.
- If the goal is a read-only DTO, use a query/custom repository with an appropriate §RowMapper§ or supported projection mechanism.
- If you need to update an aggregate, load its full state before modifying and saving it.

This is a critical boundary between **optimizing read payloads** and **stateful objects intended for writes**.

### 4.3. Example Dedicated Read Model for a Query

If only a product summary list is needed, use a JDBC mapper for a DTO:

§§§java
public record ProductSummary(
        Long id,
        String name,
        String status
) {
}
§§§

With §NamedParameterJdbcTemplate§ or §JdbcTemplate§, you can write SQL selecting the exact columns and map directly into the DTO:

§§§java
String sql = """
        SELECT id, name, status
        FROM products
        WHERE status = :status
        ORDER BY name ASC, id ASC
        LIMIT :limit OFFSET :offset
        """;

MapSqlParameterSource parameters = new MapSqlParameterSource()
        .addValue("status", "ACTIVE")
        .addValue("limit", 20)
        .addValue("offset", 0);

List<ProductSummary> summaries =
        namedParameterJdbcTemplate.query(
                sql,
                parameters,
                (rs, rowNum) -> new ProductSummary(
                        rs.getLong("id"),
                        rs.getString("name"),
                        rs.getString("status")
                )
        );
§§§

This is a custom JDBC query, not a call to §JdbcAggregateTemplate.findAll(Query, Product.class)§. Use it when you need a read model/DTO or explicit SQL projection.

## 5. Sorting with Sort

§Query.sort(Sort)§ adds sort ordering to the query.

Example sorting by name ascending:

§§§java
Query query = Query.empty()
        .sort(Sort.by("name").ascending());
§§§

Equivalent:

§§§sql
ORDER BY name ASC
§§§

Sorting by price descending:

§§§java
Sort sort = Sort.by(Sort.Direction.DESC, "price");

Query query = Query.empty().sort(sort);
§§§

### 5.1. Sorting by Multiple Properties

§Sort§ can contain multiple sort orders:

§§§java
Sort sort = Sort.by(
        Sort.Order.asc("status"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
);

Query query = Query.empty().sort(sort);
§§§

The database sorts by:

1. Status ascending.
2. Within the same status, creation date descending.
3. If status and creation date are equal, ID ascending.

Appending a unique key like §id§ at the end keeps results deterministically ordered when primary sort values tie.

### 5.2. Why Stable Sorting Matters

If paginating by §createdAt DESC§ when multiple rows share the same timestamp, the database does not guarantee ordering among tied rows without a secondary key. When fetching the next page, rows can appear duplicated or skipped due to nondeterministic ordering.

A good sort for pagination typically includes:

§§§java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
);
§§§

This order uses the unique ID as a tie-breaker. That makes ordering deterministic when data does not change while reading.

### 5.3. Sort from Requests Must Use an Allowlist

Do not accept arbitrary column names from clients and pass them directly into §Sort.by(...)§. Restrict to properties permitted by the API:

§§§java
private Sort resolveSort(String requestedSort) {
    return switch (requestedSort) {
        case "name" ->
                Sort.by("name").ascending()
                        .and(Sort.by("id").ascending());
        case "price" ->
                Sort.by(Sort.Order.desc("price"))
                        .and(Sort.Order.asc("id"));
        case "created" ->
                Sort.by(Sort.Order.desc("createdAt"))
                        .and(Sort.Order.asc("id"));
        default ->
                Sort.by(Sort.Order.asc("id"));
    };
}
§§§

Sort is not a bind parameter like a WHERE value. Sort property names affect SQL structure and therefore must be controlled.

### 5.4. Sort.unsorted()

When sorting is not needed:

§§§java
Query query = Query.empty().sort(Sort.unsorted());
§§§

However, if paginating, specify an explicit order instead of relying on database default ordering.

## 6. Limiting Rows with limit(...)

§limit(int)§ caps the maximum number of rows returned.

Example fetching 10 products:

§§§java
Query query = Query.empty().limit(10);

List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

Conceptual SQL:

§§§sql
SELECT ...
FROM products
LIMIT 10;
§§§

Actual SQL syntax is determined by the database dialect. Not every RDBMS uses the exact §LIMIT§ syntax of PostgreSQL.

### 6.1. Combining Conditions and Limit

§§§java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
).limit(10);

List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

The query returns at most 10 ACTIVE products.

### 6.2. Limits Must Be Validated

When accepting limit from an API, establish a default and a maximum:

§§§java
int normalizedLimit = Math.min(
        Math.max(requestedLimit, 1),
        100
);
§§§

The example above clamps values between 1 and 100. Real policies may reject invalid inputs instead of silently clamping; the key is preventing clients from requesting arbitrarily huge row counts.

§Query.limit§ takes an integer. Validate input before building the Query and avoid negative or invalid values.

## 7. Skipping Rows with offset(...)

§offset(long)§ specifies how many rows to skip before returning results.

Example skipping the first 40 rows:

§§§java
Query query = Query.empty()
        .sort(Sort.by("id").ascending())
        .offset(40)
        .limit(20);
§§§

Meaning:

- Sort by ID ascending.
- Skip the first 40 rows.
- Return at most the next 20 rows.

Conceptual SQL:

§§§sql
SELECT ...
FROM products
ORDER BY id ASC
LIMIT 20 OFFSET 40;
§§§

Logical ordering must be defined before applying offset. Without ORDER BY, the database does not guarantee row order and offset results are unstable.

### 7.1. Offset Formula

With zero-based pages:

\[
offset = pageNumber \times pageSize
\]

For example, page 3 with size 25:

\[
offset = 3 \times 25 = 75
\]

A Query can be constructed manually:

§§§java
int pageNumber = 3;
int pageSize = 25;

long offset = (long) pageNumber * pageSize;

Query query = Query.empty()
        .sort(Sort.by("id").ascending())
        .limit(pageSize)
        .offset(offset);
§§§

Multiply using long to prevent integer overflow when page number and page size are large.

### 7.2. Deep Offsets Can Be Expensive

As offset grows very large, the database still has to process ordering and skip many rows before returning the requested slice. For instance, offset 500,000 with limit 20 can be expensive even though the application receives only 20 rows.

For large datasets and continuous browsing, consider keyset/cursor pagination based on the last read sort values, or a dedicated query model. Offset pagination is convenient for numbered page UIs, but not optimal for every workload.

## 8. Pagination with Query.with(Pageable)

If you already have a §Pageable§, there is no need to compute offset and limit manually. §Query.with(pageable)§ applies:

- Offset from §pageable.getOffset()§.
- Limit from §pageable.getPageSize()§.
- Sort from §pageable.getSort()§.

Example:

§§§java
Pageable pageable = PageRequest.of(
        2,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")
        )
);

Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
).with(pageable);

List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

This fetches page 2, up to 20 ACTIVE products per page, sorted by creation date descending then ID ascending.

### 8.1. Query.with(Pageable) Does Not Return a Page Directly

§JdbcAggregateTemplate.findAll(Query, Class)§ returns §List<T>§. When using §with(pageable)§, the query only restricts the slice of data read; it does not automatically compute total element or total page metadata.

If you only need the page's content list, §List§ is sufficient.

If you need the total count as well, call §count(Query, Class)§ separately and construct a §Page<T>§.

### 8.2. Creating a Page with count and PageImpl

Example:

§§§java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

public Page<Product> findActiveProducts(
        int pageNumber,
        int pageSize
) {
    Pageable pageable = PageRequest.of(
            pageNumber,
            pageSize,
            Sort.by(
                    Sort.Order.desc("createdAt"),
                    Sort.Order.asc("id")
            )
    );

    Query filter = Query.query(
            Criteria.where("status").is("ACTIVE")
    );

    long total = jdbcAggregateTemplate.count(
            filter,
            Product.class
    );

    Query pageQuery = filter.with(pageable);

    List<Product> content = jdbcAggregateTemplate.findAll(
            pageQuery,
            Product.class
    );

    return new PageImpl<>(content, pageable, total);
}
§§§

Processing flow:

1. Create a §Pageable§ holding page number, page size, and sort.
2. Create a Query containing only the filter conditions.
3. Count total matching aggregates using §count§.
4. Apply §with(pageable)§ to build the page query.
5. Construct §PageImpl§ from content, pageable, and total.

**Note:** the query used for counting should retain filter conditions but have no limit/offset. In the example, §filter§ contains only Criteria, so count is not restricted to one page.

### 8.3. The findAll(Query, Class, Pageable) API Is Deprecated

In Spring Data Relational 4.1.2, the overload:

§§§java
findAll(Query query, Class<T> domainType, Pageable pageable)
§§§

has been marked deprecated since version 4.0 and scheduled for removal. The current API direction uses §findAll(Query, Class)§ with §Query.with(pageable)§, combined with §count(Query, Class)§ when a §Page§ result is needed.

Therefore, implement pagination explicitly using the two clear operations shown above instead of relying on the deprecated overload.

## 9. Distinguishing List, Page, and Slice in Dynamic Queries

§Query§ does not decide the returned metadata type on its own; the execution method and how the service assembles results determine it.

| Return Type | How to Obtain | Metadata |
| --- | --- | --- |
| §List<T>§ | §findAll(query, Type.class)§ | Content only. |
| §Page<T>§ | §count(filter, Type.class)§ + §findAll(filter.with(pageable), Type.class)§ + §PageImpl§ | Total elements, total pages, current page. |
| §Slice<T>§ | Fetch §pageSize + 1§ with limit, then trim the extra element | Whether a next page exists. |

If you want to construct a §Slice§ manually:

§§§java
int pageSize = 20;

Pageable pageable = PageRequest.of(
        0,
        pageSize,
        Sort.by("id").ascending()
);

Query query = Query.empty()
        .with(PageRequest.of(
                pageable.getPageNumber(),
                pageSize + 1,
                pageable.getSort()
        ));

List<Product> rows =
        jdbcAggregateTemplate.findAll(query, Product.class);

boolean hasNext = rows.size() > pageSize;

List<Product> content = hasNext
        ? rows.subList(0, pageSize)
        : rows;

Slice<Product> slice = new SliceImpl<>(
        content,
        pageable,
        hasNext
);
§§§

This demonstrates the technique. In an application, validate page size, sorting, and next-page handling. When a total count is not needed, fetching one extra row avoids a separate count query.

## 10. Building Dynamic Queries from Optional Filters

A major advantage of §Query§ is that services can add conditions based on parameters the user actually sends.

Suppose a product search screen has filters:

- Status may or may not be present.
- Minimum price may or may not be present.
- Maximum price may or may not be present.
- Name keyword may or may not be present.
- Sort, page, and size come from the request.

Example building Criteria:

§§§java
private Criteria buildCriteria(
        String status,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        String keyword
) {
    Criteria criteria = Criteria.empty();

    if (status != null && !status.isBlank()) {
        criteria = criteria.and(
                Criteria.where("status").is(status)
        );
    }

    if (minPrice != null) {
        criteria = criteria.and(
                Criteria.where("price").greaterThanOrEquals(minPrice)
        );
    }

    if (maxPrice != null) {
        criteria = criteria.and(
                Criteria.where("price").lessThanOrEquals(maxPrice)
        );
    }

    if (keyword != null && !keyword.isBlank()) {
        criteria = criteria.and(
                Criteria.where("name").like("%" + keyword.trim() + "%")
        );
    }

    return criteria;
}
§§§

Then construct the query:

§§§java
Criteria criteria = buildCriteria(
        request.status(),
        request.minPrice(),
        request.maxPrice(),
        request.keyword()
);

Query query = Query.query(criteria)
        .sort(resolveSort(request.sort()))
        .limit(request.limit())
        .offset(request.offset());

List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

This illustrates assembling a query from input. In production code, normalize and validate values, cap page size, whitelist sort properties, and handle the case where no filters are active.

### 10.1. Handling OR Conditions

You can group OR conditions and combine them with AND:

§§§java
Criteria nameMatches = Criteria.where("name")
        .like("%keyboard%");

Criteria skuMatches = Criteria.where("sku")
        .like("%keyboard%");

Criteria search = nameMatches.or(skuMatches);

Criteria activeProducts = Criteria.where("status").is("ACTIVE")
        .and(search);
§§§

Meaning:

§§§sql
WHERE status = 'ACTIVE'
  AND (
       name LIKE '%keyboard%'
       OR sku LIKE '%keyboard%'
  )
§§§

When conditions get complex, use explicit §Criteria§ groups to prevent AND/OR precedence from changing the intended meaning.

## 11. Combining columns, Sort, limit, and offset

Settings can be chained onto the same Query:

§§§java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
)
.columns("id", "name", "price", "created_at")
.sort(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
))
.limit(20)
.offset(40);

List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

The query above expresses:

- Filter ACTIVE products.
- Select the specified columns.
- Sort by createdAt descending, id ascending.
- Skip the first 40 rows.
- Return at most 20 rows.

Methods on §Query§ are immutable: each call returns a new object. Chaining as above keeps all settings. If written step by step, reassign the variable:

§§§java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
);

query = query.columns("id", "name", "price");
query = query.sort(Sort.by("name").ascending());
query = query.limit(20);
query = query.offset(40);
§§§

If you simply call §query.limit(20);§ without assigning the result, the original §query§ variable does not receive the new setting.

## 12. Query Limitations and Differences from @Query on Repositories

The dynamic §Query§ class and string-based §@Query§ have different capabilities.

| Need | Dynamic Query + JdbcAggregateTemplate | String-based @Query |
| --- | --- | --- |
| Build Criteria in Java | Yes | No; write SQL. |
| Column selection | §columns(...)§ | Write select list in SQL. |
| Dynamic sorting | §sort(Sort)§ | Write ORDER BY in SQL manually. |
| Limit/offset | §limit§ / §offset§ / §with(Pageable)§ | Write SQL and bind values manually. |
| Return mapped aggregates | Yes | Yes if SQL matches RowMapper mapping. |
| Return custom DTOs | Not automatic from columns; requires suitable mapper/read model | Can use projections/RowMapper as supported. |

Spring Data JDBC documentation notes that string-based queries do not support automatic pagination and do not accept §Sort§, §PageRequest§, or §Limit§ parameters for query rewriting by the framework. When using §@Query§, express limit/sort directly in SQL and bind parameters safely.

The §Query§ class fits when conditions and sorting are built dynamically at runtime. §@Query§ fits when the SQL structure is fixed or requires specialized SQL.

## 13. Protecting Queries When Receiving Client Input

A dynamic query typically receives filters, sort, limit, and page from an API. Validate them before constructing Query.

### 13.1. Never Concatenate Values Directly into SQL

With Criteria:

§§§java
Criteria.where("status").is(request.status())
§§§

values are bound via JDBC. Never concatenate strings like:

§§§java
String sql = "SELECT * FROM products WHERE status = '" +
        request.status() + "'";
§§§

String concatenation creates SQL injection risks and escaping bugs.

### 13.2. Allowlist Sort Columns

Sorting is query structure, not a bound value. Map the client's choice to a predefined set of sorts:

§§§java
Sort sort = switch (request.sortBy()) {
    case "price" -> Sort.by("price").ascending()
            .and(Sort.by("id").ascending());
    case "createdAt" -> Sort.by("createdAt").descending()
            .and(Sort.by("id").ascending());
    default -> Sort.by("id").ascending();
};
§§§

Never pass arbitrary client strings directly into §Sort.by§.

### 13.3. Validate limit and offset

Example:

§§§java
if (request.limit() < 1 || request.limit() > 100) {
    throw new IllegalArgumentException("Invalid limit");
}

if (request.offset() < 0) {
    throw new IllegalArgumentException("Offset must not be negative");
}
§§§

Large offsets can slow down queries. If the API needs deep traversal, evaluate keyset pagination.

### 13.4. Do Not Omit Sort When Paginating

If a query uses offset without a stable sort, the database can return rows in different orders across runs. Always append a unique criterion like ID at the end of the sort when appropriate.

## 14. Performance: Column Selection, Indexes, and Deep Offsets

Selecting fewer columns can reduce transferred payload, though the benefit depends on row size, column types, and execution plans. If a query needs many attributes to materialize an aggregate or related collections, trimming columns may not help as much as expected.

Some guidelines:

- Select only columns needed for the read use case.
- Use a projection/DTO or JDBC RowMapper for read models instead of constructing partial aggregates.
- Create indexes supporting frequently used filter conditions and sort orders.
- Inspect execution plans on a real database.
- Limit rows in the database rather than fetching everything and slicing in Java.
- Add a unique tie-breaker sort when paginating.
- Avoid deep offsets on very large datasets.

Example query:

§§§sql
SELECT id, name, price, created_at
FROM products
WHERE status = 'ACTIVE'
ORDER BY created_at DESC, id ASC
LIMIT 20 OFFSET 1000;
§§§

An index to consider on PostgreSQL:

§§§sql
CREATE INDEX idx_products_status_created_id
ON products (status, created_at DESC, id ASC);
§§§

Index choices must be driven by workload and execution plans. Indexes speed up certain reads while increasing insert/update overhead and storage usage.

## 15. Complete Service Example

Suppose the aggregate is:

§§§java
@Table("products")
public class Product {

    @Id
    private Long id;

    private String name;
    private BigDecimal price;
    private String status;

    @Column("created_at")
    private LocalDateTime createdAt;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public String getStatus() {
        return status;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
§§§

Service building dynamic queries:

§§§java
@Service
public class ProductSearchService {

    private final JdbcAggregateTemplate jdbc;

    public ProductSearchService(JdbcAggregateTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Product> search(
            String status,
            BigDecimal minPrice,
            int page,
            int size
    ) {
        Criteria criteria = Criteria.empty();

        if (status != null && !status.isBlank()) {
            criteria = criteria.and(
                    Criteria.where("status").is(status)
            );
        }

        if (minPrice != null) {
            criteria = criteria.and(
                    Criteria.where("price").greaterThanOrEquals(minPrice)
            );
        }

        int pageSize = Math.min(Math.max(size, 1), 100);
        int pageNumber = Math.max(page, 0);

        Sort sort = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")
        );

        Pageable pageable = PageRequest.of(
                pageNumber,
                pageSize,
                sort
        );

        Query query = Query.query(criteria).with(pageable);

        return jdbc.findAll(query, Product.class);
    }
}
§§§

This example returns a §List<Product>§ for the current page. If the UI needs the total result count, add §jdbc.count(filter, Product.class)§ and wrap it in §PageImpl§ as shown in section 8.

In a real application, also handle negative pages, invalid sizes, a sort allowlist, and data access authorization.

## 16. Common Misconceptions

**"Query is the @Query annotation."** Incorrect. §Query§ is a value object class for building queries in Java; §@Query§ is an annotation declaring string-based SQL.

**"Query.columns(...) creates a DTO."** Incorrect. It restricts selected columns, but the result type is still mapped to the class passed to §findAll§.

**"You can select partial columns and then save the aggregate."** Unsafe. Unselected properties may be null/default or uninitialized; save does not treat missing fields as "leave unchanged".

**"Query is a mutable builder."** Incorrect. Methods return a new Query; you must capture the return value or chain calls.

**"limit automatically sorts data."** No. If deterministic results are needed, add §Sort§.

**"offset can be used without ORDER BY."** It may run, but ordering is not guaranteed; pagination can duplicate or skip rows.

**"with(Pageable) returns a Page."** No. It applies offset, limit, and sort to Query; §findAll(Query, Class)§ still returns a List.

**"findAll(Query, Class, Pageable) is the preferred API for Page."** That overload has been deprecated since Spring Data Relational 4.0; use Query.with(Pageable), count, and PageImpl.

**"count must include the same limit/offset."** Not when you want the total matching rows for the filter. The count query should keep the filter criteria without page limits.

**"String-based @Query also accepts Pageable and Sort automatically."** No. In Spring Data JDBC, string-based queries are not rewritten by the framework to apply pagination or sorting; write the corresponding SQL yourself.

**"Larger offsets are just as fast as the first page."** Not necessarily. The database may have to scan/skip many rows before returning the requested slice.

**"Sort names from clients can be passed straight into queries."** Avoid this. Whitelist allowed properties.

## 17. Workflow for Column Selection, Sorting, Limiting, and Pagination

When creating a dynamic query, follow this sequence:

1. **Determine the result type:** full aggregate or read model/DTO.
2. **Build Criteria:** add only conditions with valid values.
3. **Select columns:** use a subset only when the result type can be safely mapped and is read-only.
4. **Create Sort:** use allowlisted properties and append a unique tie-breaker.
5. **Validate limit:** enforce defaults and maximum caps.
6. **Choose offset or Pageable:** use manual limit/offset for simple queries, Pageable when page number/size/sort are needed.
7. **Execute:** use findOne, findAll, streamAll, or count on JdbcAggregateTemplate.
8. **Build a Page if needed:** separate count query on the filter and PageImpl for content.
9. **Check performance:** inspect indexes, execution plans, row counts, and deep offsets.
10. **Separate reads and writes:** never save an aggregate object constructed from a subset of columns.

§§§mermaid
flowchart TD
    A["Receive filter, sort, limit, or page"] --> B["Build Criteria from valid filters"]
    B --> C{"What result is needed?"}
    C -->|Full aggregate| D["Keep all columns needed for mapping"]
    C -->|Partial read model| E["Select columns or use DTO RowMapper"]
    D --> F["Create Sort with allowlist + tie-breaker"]
    E --> F
    F --> G{"Paginated?"}
    G -->|No| H["Query.limit / Query.sort"]
    G -->|Yes| I["Query.with(Pageable)"]
    H --> J["JdbcAggregateTemplate.findAll"]
    I --> J
    J --> K{"Need total count?"}
    K -->|Yes| L["count(filter) + PageImpl"]
    K -->|No| M["Use List"]
    L --> N["Verify SQL, indexes, and offset"]
    M --> N
§§§

## 18. Practice Exercises

Create a §products§ table with columns §id§, §name§, §price§, §status§, and §created_at§. Create a §Product§ aggregate mapped to this table.

### Exercise 1: Basic Query

1. Use §Query.empty()§ to retrieve the product list.
2. Use §Query.query(Criteria.where("status").is("ACTIVE"))§ to filter products.
3. Execute with §JdbcAggregateTemplate.findAll§.
4. Observe the generated SQL.

### Exercise 2: Selecting Columns

1. Create a query selecting §id§, §name§, and §status§.
2. Try mapping into a mutable class with a no-arg constructor.
3. Observe the unselected properties.
4. Try with a record having a full constructor and explain why all constructor columns are needed.
5. Do not pass partially loaded objects to save.

### Exercise 3: Sorting

1. Sort by price ascending.
2. Sort by creation date descending.
3. Combine creation date descending and ID ascending.
4. Insert multiple products with the same timestamp to observe the tie-breaker.

### Exercise 4: Limit and Offset

1. Use limit 10.
2. Use offset 20 and limit 10.
3. Add sorting by ID.
4. Observe returned row counts and ordering.
5. Test a large offset to inspect the execution plan.

### Exercise 5: Pageable

1. Create §PageRequest.of(0, 20, sort)§.
2. Apply §Query.with(pageable)§.
3. Fetch the list using §findAll(Query, Product.class)§.
4. Construct a Page using count and PageImpl.
5. Compare List and Page metadata.

### Exercise 6: Dynamic Filters

1. Accept optional status, minPrice, and maxPrice.
2. Build Criteria with conditional if branches.
3. Validate limit and sort.
4. Create a Query with Criteria, Sort, and Pageable.
5. Verify results when some filters are omitted.

## 19. Key Takeaways

- §Query§ in §org.springframework.data.relational.core.query§ is a value object for building dynamic queries, distinct from the §@Query§ annotation.
- §Criteria§ expresses WHERE conditions and can combine AND/OR.
- §columns(...)§ limits SELECT columns; §columnsOf(...)§ based on typed property paths was added in Spring Data Relational 4.1.
- Selecting columns does not automatically produce a DTO. The class passed to §findAll(Query, Class)§ remains the target mapped by the mapper.
- Never save aggregates loaded with missing columns; missing properties may be null/default and do not mean "preserve existing data".
- §sort(Sort)§ defines result ordering; when paginating, append a unique key as a tie-breaker.
- §limit(int)§ caps row counts; §offset(long)§ skips rows according to the chosen order.
- §with(Pageable)§ applies offset, limit, and sort to Query.
- §findAll(Query, Class)§ returns a List; to return a Page, run a separate count and wrap with §PageImpl§.
- The §findAll(Query, Class, Pageable)§ overload has been deprecated since Spring Data Relational 4.0; prefer §Query.with(Pageable)§.
- String-based §@Query§ does not automatically support pagination/sorting via Pageable or Sort parameters in Spring Data JDBC; write the corresponding SQL explicitly.
- Validate client-supplied sort, limit, and offset; check execution plans and avoid deep offsets.
- Keep partial read models separate from full aggregates used for writes.

Once you master §Query§, you can construct queries from runtime filters, select the right columns, sort deterministically, and limit rows right at the database. **Treat Query as a specification of an intentional read operation**: decide the result type first, then choose the appropriate columns, sort, limit, and pagination.

## References

- [Spring Data Relational 4.1.2 — Persisting Entities and Querying](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Relational 4.1.2 — Query API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Query.html)
- [Spring Data Relational 4.1.2 — Criteria API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Criteria.html)
- [Spring Data JDBC 4.1.2 — JdbcAggregateOperations API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateOperations.html)
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
