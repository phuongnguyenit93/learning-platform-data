# Building Query, Criteria, and Update

In Spring Data Relational R2DBC, `Query`, `Criteria`, and `Update` are the components that help build dynamic queries without manually concatenating SQL strings. They are commonly used with `R2dbcEntityTemplate` when search conditions vary per request, when pagination/sorting is needed, or when you want to update certain properties without loading the entire entity first.

`Criteria` describes filter conditions; `Query` combines conditions with query options such as sort, limit, and offset; `Update` describes the properties to be modified. `R2dbcEntityTemplate` translates these objects into R2DBC operations, binds values, and maps results according to entity metadata.

## 1. Position of Query, Criteria, and Update in the Architecture

These components belong to Spring Data Relational, sitting at a higher entity-operation layer than `DatabaseClient`:

```text
Application service
        |
        v
R2dbcEntityTemplate
        |
        +-------------------+
        |                   |
        v                   v
      Query              Update
        |                   |
        v                   v
     Criteria           values to write
        |                   |
        +---------+---------+
                  |
                  v
       Spring Data Relational mapping
                  |
                  v
              R2DBC SPI
                  |
                  v
             R2DBC driver
                  |
                  v
               Database
```

Each component has its own responsibility:

- **`Criteria`:** represents conditions such as equals, greater than, belonging to a set of values, pattern matching, or null.
- **`Query`:** holds conditions and read options such as sorting, row limit, and offset.
- **`Update`:** describes the columns/properties to set in an UPDATE operation.
- **`R2dbcEntityTemplate`:** executes select, update, or delete using `ConnectionFactory`, while utilizing entity mapping metadata.

Import example:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.data.relational.core.query.Update;
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
```

These APIs are useful when a query needs to be constructed from optional conditions. For specialized SQL, complex joins, or database-specific features, `DatabaseClient` and `@Query` may still be more appropriate.

## 2. Query: Describing a Query Request

`Query` is the object that describes a query. It is usually created from a `Criteria`:

```java
Query query = Query.query(
    Criteria.where("status").is("ACTIVE")
);
```

This query represents a request to find entities whose `status` equals `ACTIVE`. `Query` itself does not execute SQL; it is a descriptor passed to `R2dbcEntityTemplate`.

Example reading all matching customers:

```java
Flux<Customer> customers = template.select(
    Query.query(Criteria.where("status").is("ACTIVE")),
    Customer.class
);
```

`select(query, Customer.class)` returns a `Flux<Customer>`. The result rows are mapped to `Customer` entities according to Spring Data Relational metadata.

If only a single result is needed, `selectOne` can be used:

```java
Mono<Customer> customer = template.selectOne(
    Query.query(Criteria.where("email").is(email)),
    Customer.class
);
```

`selectOne` is suitable when the condition is expected to return at most one row. If the database returns multiple rows, the operation may throw an error instead of silently picking one row. If you only need the first row in a specific order, design the query with appropriate sort/limit and use the suitable template API.

## 3. Criteria: Building Filter Conditions

`Criteria` is the predicate descriptor. A simple condition can be created with `Criteria.where(property)` followed by choosing a comparison operator.

```java
Criteria criteria = Criteria.where("status").is("ACTIVE");
```

Some commonly used operators:

| Operator | Meaning | Example |
|---|---|---|
| `is(value)` | Equal to value | `where("status").is("ACTIVE")` |
| `not(value)` | Not equal to value | `where("status").not("DELETED")` |
| `in(values)` | In set of values | `where("status").in(statuses)` |
| `notIn(values)` | Not in set of values | `where("type").notIn(types)` |
| `greaterThan(value)` | Greater than | `where("price").greaterThan(min)` |
| `greaterThanOrEquals(value)` | Greater than or equal to | `where("createdAt").greaterThanOrEquals(from)` |
| `lessThan(value)` | Less than | `where("price").lessThan(max)` |
| `lessThanOrEquals(value)` | Less than or equal to | `where("createdAt").lessThanOrEquals(to)` |
| `between(from, to)` | Within range | `where("price").between(min, max)` |
| `like(pattern)` | Matches LIKE pattern | `where("name").like("A%")` |
| `isNull()` | Null value | `where("deletedAt").isNull()` |
| `isNotNull()` | Non-null value | `where("email").isNotNull()` |

Specific capabilities and method names should be checked against the Spring Data Relational version in use. These examples illustrate common ways of expressing the Criteria API.

### 3.1. Combining Multiple AND Conditions

Conditions can be chained using `and`:

```java
Criteria criteria = Criteria.where("status").is("ACTIVE")
    .and("age").greaterThanOrEquals(18)
    .and("country").is("VN");

Query query = Query.query(criteria);
Flux<Customer> customers = template.select(query, Customer.class);
```

The condition above simultaneously requires:

- `status` equals `ACTIVE`.
- `age` is greater than or equal to 18.
- `country` equals `VN`.

Logically, the condition is equivalent to `status = 'ACTIVE' AND age >= 18 AND country = 'VN'`.

### 3.2. Combining OR Conditions

When business logic allows multiple alternatives, branches can be combined with `or`:

```java
Criteria criteria = Criteria.where("status").is("NEW")
    .or("status").is("PROCESSING");

Query query = Query.query(criteria);
Flux<Order> orders = template.select(query, Order.class);
```

The condition means the status is either `NEW` or `PROCESSING`. When combining multiple AND/OR groups, check the grouping order and logical parentheses in the generated SQL. If an expression is complex, split it into clear Criteria groups and verify the SQL via integration tests or SQL logging in the development environment.

### 3.3. Date Range Conditions

Example filtering orders created within a time period:

```java
Criteria criteria = Criteria.where("createdAt")
    .greaterThanOrEquals(from)
    .and("createdAt")
    .lessThan(to);
```

For time ranges, standardize on timezone and Java/database types. If the column stores UTC, the service should convert input times to the same convention before creating the Criteria. You should clearly define whether the interval is closed or open, such as `[from, to)`, so that two adjacent time pages do not overlap or miss data.

## 4. Building Dynamic Criteria from Optional Filters

In a search API, users often submit only a subset of conditions. For example, a request might have status, name, minimum price, and start creation date. You should not create a separate SQL statement for every filter combination. Add Criteria only when a parameter actually has a value.

Suppose the filter is:

```java
public record ProductFilter(
    String status,
    String name,
    BigDecimal minPrice,
    Instant createdAfter
) {}
```

The condition can be constructed as follows:

```java
Criteria criteria = Criteria.empty();

if (filter.status() != null && !filter.status().isBlank()) {
    criteria = criteria.and("status").is(filter.status());
}

if (filter.name() != null && !filter.name().isBlank()) {
    criteria = criteria.and("name").like("%" + filter.name() + "%");
}

if (filter.minPrice() != null) {
    criteria = criteria.and("price").greaterThanOrEquals(filter.minPrice());
}

if (filter.createdAfter() != null) {
    criteria = criteria.and("createdAt").greaterThanOrEquals(filter.createdAfter());
}

Query query = Query.query(criteria);
Flux<Product> products = template.select(query, Product.class);
```

When a filter is not provided, the corresponding predicate is not added. As a result, the query only contains the conditions the user actually requested.

`Criteria.empty()` is a convenient starting point for composing optional conditions. Check the API of the Spring Data Relational version in your project if an older version lacks this method; you can start from the first condition and then chain subsequent ones.

### 4.1. Distinguishing Omitted Filters from Null-Valued Filters

In a PATCH API or advanced search, `null` can carry multiple meanings:

- Client omits the field: do not add a filter condition.
- Client sends the field as null: may want to find rows where the column is null.
- Client sends an empty value: may want to ignore it or search for an empty string, depending on the API contract.

A simple DTO using `String status` may not be able to distinguish an omitted field from an explicitly sent null after deserialization. If you need to distinguish them, use a type that represents field presence, a request wrapper, or a filter structure with a separate `provided` flag.

For example, if you want to filter rows where `deletedAt IS NULL`, you must explicitly add `Criteria.where("deletedAt").isNull()`. Do not skip a predicate just because the filter value is null if null itself is the business condition.

### 4.2. Guarding Queries When No Filter Is Provided

If all filters are empty, `Criteria.empty()` can produce a query without conditions. For a SELECT operation, that could mean reading the entire table. For an UPDATE or DELETE, this can be a severe bug.

The service should explicitly decide whether unfiltered searches are allowed:

```java
boolean hasFilter =
    filter.status() != null ||
    filter.name() != null ||
    filter.minPrice() != null ||
    filter.createdAfter() != null;

if (!hasFilter) {
    return Flux.error(new IllegalArgumentException(
        "At least one search condition must be provided"));
}
```

If an endpoint allows reading all data, you should still limit the number of rows, apply pagination, and enforce access control.

## 5. Query with Sort, Limit, and Offset

`Query` does not just hold Criteria. It can also describe how to sort and limit results.

```java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE"))
    .sort(Sort.by(Sort.Order.desc("createdAt")))
    .limit(50)
    .offset(0);

Flux<Customer> page = template.select(query, Customer.class);
```

In the example:

- `sort(...)` sorts by creation time descending.
- `limit(50)` limits to at most 50 rows.
- `offset(0)` starts from the first row.

You should add a unique key at the end of the sort order to achieve a deterministic order, especially when multiple rows share the same timestamp:

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
```

When using dynamic sorting from a request, never pass arbitrary column names directly into the API. Map the user-submitted value to an allowed list of properties:

```java
String sortProperty = switch (requestedSort) {
    case "name" -> "name";
    case "price" -> "price";
    case "createdAt" -> "createdAt";
    default -> "createdAt";
};

Sort.Direction direction = descending
    ? Sort.Direction.DESC
    : Sort.Direction.ASC;

Sort sort = Sort.by(direction, sortProperty);
```

Filter values are bound as data; sort property names are identifiers. Identifiers cannot be protected by binding them like regular values, so a whitelist is required.

### 5.1. Computing Offset Safely

If the API accepts `page` and `size`, validate them before building the Query:

```java
int safePage = Math.max(0, page);
int safeSize = Math.max(1, Math.min(size, 100));
long offset = (long) safePage * safeSize;

Query query = Query.query(criteria)
    .sort(Sort.by(Sort.Order.desc("createdAt"),
                  Sort.Order.desc("id")))
    .limit(safeSize)
    .offset(offset);
```

Casting to `long` before multiplication helps prevent integer overflow when the page number is large. Capping `safeSize` prevents clients from requesting an overly large page and consuming excessive resources.

### 5.2. OFFSET and Keyset Pagination

Offset pagination is convenient when the UI needs specific page numbers, but querying deep pages can be costly because the database has to skip many rows. For large datasets read sequentially, keyset pagination may be more suitable:

```java
Criteria criteria = Criteria.where("id").greaterThan(lastSeenId);

Query query = Query.query(criteria)
    .sort(Sort.by(Sort.Order.asc("id")))
    .limit(batchSize);
```

After each batch, take the last ID as `lastSeenId` for the next round. The cursor column should be indexed and the order must be deterministic. If sorting by multiple columns, the cursor condition must fully reflect that sort order.

## 6. Counting Results with the Same Criteria

When the UI needs the total number of matching records, `count` can be used with the same Query:

```java
Query query = Query.query(criteria);

Mono<Long> total = template.count(query, Product.class);
Flux<Product> products = template.select(
    query.limit(pageSize).offset(offset),
    Product.class
);
```

Count and select are two separate database operations. If data changes between the two operations, the total count and page content may not reflect the same snapshot, unless they run within an appropriate transaction/isolation level. Avoid running exact counts on every endpoint if the query cost is high and the UI does not strictly need it.

## 7. Update: Updating a Partial Entity

`Update` describes the values to write to the database. It is commonly used together with `Query` to identify which rows to update.

Example changing the status of an order:

```java
Query query = Query.query(Criteria.where("id").is(orderId));

Update update = Update.update("status", "PAID")
    .set("updatedAt", Instant.now());

Mono<Long> affected = template.update(query, update, Order.class);
```

`template.update(...)` returns a `Mono<Long>` representing the number of affected rows as reported by the driver. There is no need to load the entity and call `save` if only a few properties need to change and business logic does not require the entire current object.

### 7.1. Updating Multiple Properties

Multiple `set` calls can be chained:

```java
Update update = Update.update("status", "SHIPPED")
    .set("shippedAt", Instant.now())
    .set("trackingCode", trackingCode)
    .set("updatedAt", Instant.now());

Mono<Long> affected = template.update(
    Query.query(Criteria.where("id").is(orderId)),
    update,
    Order.class
);
```

Only the properties listed in `Update` are updated by this operation. Other columns keep their current values in the database.

### 7.2. Dynamic Update Based on Request

Suppose a request can only change a product's name and description:

```java
Update update = Update.empty();

if (request.name() != null && !request.name().isBlank()) {
    update = update.set("name", request.name());
}

if (request.description() != null) {
    update = update.set("description", request.description());
}

if (!update.hasAssignments()) {
    return Mono.error(new IllegalArgumentException(
        "No properties to update"));
}

Query query = Query.query(Criteria.where("id").is(productId));
return template.update(query, update, Product.class);
```

This code snippet illustrates how to conditionally add assignments. Depending on the Spring Data Relational version, the API to initialize `Update.empty()` and check assignments may differ or not be public. You can construct `Update` from a map or initialize from the first assignment before chaining `set`; use the API provided by your project's version.

It is important to clearly define what null means. In the example above, `description == null` is treated as not updating. If a request wants to clear content by setting the column to SQL NULL, field presence must be represented separately and a null assignment added using a supported binding API. Never merge "field omitted" and "null sent to clear value" into the same case.

### 7.3. Conditional Update to Avoid Overwriting Newer Data

You can include the current state in the Query so the update only applies if the condition still holds:

```java
Query query = Query.query(
    Criteria.where("id").is(orderId)
        .and("status").is("PAID")
);

Update update = Update.update("status", "SHIPPED");

Mono<Long> affected = template.update(query, update, Order.class);
```

This is a compare-and-set pattern: transition the status only if the order is still `PAID`. If the number of affected rows is 0, either the order does not exist or its status has already changed. The service needs to decide how to distinguish those cases, possibly re-reading the entity when needed.

## 8. Update and Optimistic Locking

If an entity has `@Version`, Spring Data can use the version to control concurrent updates when operating on the entity through supported mechanisms. With custom `Update` statements, do not assume all version rules are automatically applied the same way as `save` on an entity.

When manual compare-and-set is needed, include the current version in Criteria and increment the version in Update in a way supported by the database/driver:

```java
Query query = Query.query(
    Criteria.where("id").is(id)
        .and("version").is(expectedVersion)
);

Update update = Update.update("status", newStatus)
    .set("version", expectedVersion + 1);

Mono<Long> affected = template.update(query, update, Order.class);
```

If `affected` equals 0, the version no longer matches or the row does not exist. This illustrates optimistic compare-and-set at the SQL layer; verify the version type, increment rules, and transaction behavior with your target database. Do not both increment the version manually in `Update` and expect the framework to increment it again.

## 9. Delete Using Query and Criteria

`Query` and `Criteria` can also specify rows to delete:

```java
Query query = Query.query(
    Criteria.where("status").is("EXPIRED")
        .and("expiresAt").lessThan(Instant.now())
);

Mono<Long> deleted = template.delete(query, Session.class);
```

The operation returns the number of deleted rows. For critical data, inspect predicates carefully and consider soft delete instead of physical deletion.

Do not use an empty Criteria for UPDATE or DELETE unless business logic genuinely requires modifying the entire table and has dedicated safeguards. A skipped filter due to a deserialization error can turn a scoped operation into a table-wide mutation.

## 10. Property Names, Column Names, and Mapping Metadata

`Criteria` and `Update` are used in the context of an entity class, so property names must align with Spring Data Relational's mapping metadata. If an entity uses `@Column`, a naming strategy, or column names differing from field names, verify the conversion rules applied by your framework version.

For example:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("display_name")
    private String displayName;
}
```

When creating Criteria/Update, use property names as required by the API and mapping context of your project's version; do not assume Java names always match physical column names. With `DatabaseClient`, on the other hand, SQL is written directly, so actual column names must be used in the statement.

This is one reason to write integration tests against a real schema or inspect the generated SQL whenever changing `@Column` or naming strategies.

## 11. Are Criteria and Update Safe Against SQL Injection?

When using the Criteria/Update API properly, condition values and update values are bound by the framework as parameters instead of being concatenated directly into SQL. For example:

```java
Criteria criteria = Criteria.where("email").is(request.email());
Query query = Query.query(criteria);
```

The `request.email()` value is treated as data. However, that does not mean every dynamic component is automatically safe.

Identifiers such as sort property names, column names passed into Criteria/Update, or table names are not ordinary bind values. Never allow clients to send arbitrary strings to select identifiers. Use a whitelist:

```java
String property = switch (request.sortBy()) {
    case "name" -> "name";
    case "createdAt" -> "createdAt";
    case "price" -> "price";
    default -> "createdAt";
};
```

With `LIKE`, `%` and `_` characters act as wildcards. If business logic requires searching for a literal string, escape wildcard characters according to database/dialect rules and declare an appropriate escape clause if supported by the API. Do not let users accidentally or intentionally turn an exact search into an overly broad match pattern.

## 12. Handling Empty Collections in IN Conditions

The `IN` condition is useful when filtering by a set of IDs or statuses:

```java
Criteria criteria = Criteria.where("status").in(statuses);
```

However, behavior when `statuses` is empty must be defined. Some databases or SQL generation approaches do not accept `IN ()`; even when the framework handles it, the business meaning may be ambiguous.

Handle it upfront:

```java
if (statuses == null || statuses.isEmpty()) {
    return Flux.empty();
}

Criteria criteria = Criteria.where("status").in(statuses);
return template.select(Query.query(criteria), Order.class);
```

If an empty collection means "do not apply this filter", you can omit the predicate. If it means "no results are permitted", returning `Flux.empty()` is usually clearer. Do not let an empty set inadvertently become an unfiltered query.

## 13. Transactions When Combining Multiple Operations

A use case may need to read, update, and write an audit record within the same transaction. You can compose publishers from the template and use reactive transaction management.

For example:

```java
@Service
public class OrderService {

    private final R2dbcEntityTemplate template;

    public OrderService(R2dbcEntityTemplate template) {
        this.template = template;
    }

    @Transactional
    public Mono<Long> markShipped(Long orderId) {
        Query query = Query.query(
            Criteria.where("id").is(orderId)
                .and("status").is("PAID")
        );

        Update update = Update.update("status", "SHIPPED")
            .set("updatedAt", Instant.now());

        return template.update(query, update, Order.class);
    }
}
```

The method returns a `Mono` so Spring can manage reactive transaction boundaries. Do not call `block()` inside the method. The transaction manager and template must use the same `ConnectionFactory` for operations to participate in the same transaction.

If a use case needs to update multiple tables, define rollback conditions and affected row expectations. An operation returning 0 rows might be a normal business outcome or a sign that data changed; decide clearly whether to continue the transaction or emit an error.

## 14. Comparing Query/Criteria/Update with Other Options

| Approach | When Suitable | Considerations |
|---|---|---|
| Derived query in repository | Stable conditions, clear method names | Inconvenient when filters vary across many combinations |
| `@Query` in repository | Fixed SQL, need statement control | SQL is tied to repository method; complex dynamic SQL is hard to organize |
| `Query` + `Criteria` | Dynamic entity queries, optional filters, sort/page | Requires managing predicates, identifiers, and empty cases |
| `Update` with `R2dbcEntityTemplate` | Conditional partial property updates | Requires checking affected row count and concurrency |
| `DatabaseClient` | Specialized SQL, custom joins/projections, or dialect-specific | Application writes SQL and mappers manually |

These approaches can coexist. Repositories fit common CRUD/query contracts; the template fits dynamic entity operations; DatabaseClient fits when direct SQL control is needed.

## 15. Testing Dynamic Queries

Tests should verify both how conditions are composed and the resulting SQL behavior against a compatible database.

Cases to include:

- No filters and empty filters.
- Single condition; multiple AND conditions; OR branches.
- Null values, empty strings, and whitespace-only strings.
- `IN` with a populated set and an empty set.
- `LIKE` with `%`, `_`, and escape characters.
- Sorting by each whitelisted property and ascending/descending directions.
- First page, deep page, size 0, negative size, and oversized page.
- Updating one field, multiple fields, and no assignments.
- Update matching no rows or when predicate no longer holds.
- Delete with narrow conditions and when no rows match.
- Transaction rollback when a subsequent operation emits an error.
- Optimistic locking or compare-and-set under concurrent updates.

`StepVerifier` can verify reactive results:

```java
StepVerifier.create(productService.search(filter))
    .expectNextMatches(product -> product.getStatus().equals("ACTIVE"))
    .verifyComplete();
```

For update operations, check the affected row count:

```java
StepVerifier.create(productService.changeStatus(id, "ARCHIVED"))
    .expectNext(1L)
    .verifyComplete();
```

The example assumes only one row matches. Real tests should seed deterministic data, checking both 0-row and multi-row cases if business logic allows them.

## 16. Common Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Concatenating SQL strings to build filters | Hard to maintain and SQL injection risk | Use Criteria to bind values |
| Not checking for empty filters | Can read the whole table or update/delete too broadly | Add guards based on business rules |
| Using client-sent sort names directly | Dynamic identifiers are not protected like bind values | Whitelist allowed properties |
| Not capping page size | Query may return too many rows | Validate page/size and set a maximum |
| Using deep offset to scan large datasets | Query cost may escalate | Consider keyset pagination |
| Using `IN` with an empty collection unhandled | Invalid SQL or unclear filter semantics | Return empty or omit filter per API contract |
| Treating null as always meaning skip filter | Cannot find rows with null columns | Represent explicit-null filters and use `isNull()` |
| Updating the whole entity when only one field is needed | Wasted work and risk of overwriting other data | Use `Update` for partial updates |
| Not checking update/delete row count | Unknown whether row existed or predicate matched | Handle the returned `Mono<Long>` |
| Assuming Update automatically applies optimistic locking | Lost updates under concurrent transactions | Include version in predicate or use entity mechanisms |
| Confusing property names and physical column names | Criteria/Update may not map as expected | Check `@Column`, naming strategy, and actual SQL |
| Using Criteria API from a different version | Compile errors or unexpected behavior | Check Javadoc of your Spring Data Relational version |

## 17. Workflow for Building Dynamic Queries

When implementing a search or update endpoint, follow this sequence:

1. **Define the filter contract:** which fields are optional, which allow explicit null, what an empty collection means.
2. **Validate inputs:** string lengths, numeric/date ranges, page size, and sort properties.
3. **Build Criteria:** add each predicate according to the filter's value and presence state.
4. **Create Query:** add deterministic sort, limit, and offset/cursor.
5. **Execute with template:** use `select`, `selectOne`, `count`, `update`, or `delete` as appropriate.
6. **Check cardinality:** handle 0, 1, or multiple rows per business contract.
7. **Manage transactions:** wrap operations requiring atomicity in a reactive transaction.
8. **Test real SQL:** run against a compatible database, including empty-filter and concurrent-update cases.

## 18. Key Principles to Remember

- `Criteria` describes filter conditions; `Query` combines conditions with sort and result limits; `Update` describes values to change.
- Use `R2dbcEntityTemplate` to execute Query/Criteria/Update objects within the Spring Data Relational model.
- Add predicates according to actual filter state and distinguish omitted fields from explicit null.
- Guard empty queries before SELECT, UPDATE, and DELETE.
- Cap page size, use deterministic sorting, and consider keyset pagination for large datasets.
- Whitelist dynamic identifiers like sort properties; bind input values.
- Handle empty collections before using `IN`.
- Use `Update` for partial updates and check the affected row count.
- Do not assume custom Update operations automatically apply optimistic locking; put version in the condition if compare-and-set is needed.
- Verify property/column name mapping, `@Column`, and naming strategy.
- Use reactive transactions when multiple operations must be atomic and never call `block()` in the pipeline.
- Test against the target database and driver to verify SQL, mapping, and concurrency behavior.

`Query`, `Criteria`, and `Update` enable structured dynamic query building in Spring Data Relational R2DBC. By separating conditions, query options, and update assignments, services can support many filter combinations while remaining readable. Validating empty filters, whitelisting identifiers, bounding pagination, and checking affected row counts keep these operations safe and predictable in production.
