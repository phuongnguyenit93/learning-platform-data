# Implementing Dynamic Filtering, Sorting, and Stable Pagination

In Spring Data Relational R2DBC, a search screen typically lets users combine multiple filters, choose a sort order, and page through results. Because these criteria vary per request, you cannot always write a single static SQL query for every combination.

Spring Data R2DBC provides `Criteria`, `Query`, `Sort`, and `R2dbcEntityTemplate` to build conditional entity queries. For complex SQL or tighter control, you can use `DatabaseClient` with bind parameters. Both approaches must uphold the same principles:

- Add a predicate only when its corresponding filter is actually provided.
- Distinguish an omitted filter from a filter requesting `NULL` values.
- Bind values instead of concatenating user input into SQL.
- Never allow clients to supply arbitrary column names, SQL expressions, or sort keywords.
- Apply tenant/ownership scope from an authenticated source to every query.
- Cap page sizes and bound offsets.
- Use a deterministic sort order with a unique key as a tie-breaker.
- Consider keyset pagination when datasets are large or change concurrently.

## 1. Dynamic filtering, sorting, and pagination are three distinct concerns

A search query can be divided into three parts:

| Part | Responsibility | Example |
|---|---|---|
| Filter | Determines which rows are selected | `status = OPEN`, `createdAt` within a time range |
| Sort | Determines row ordering | `createdAt` descending, `id` descending |
| Pagination | Limits the slice of results returned | page size 20, offset 40, or cursor |

Example request:

~~~http
GET /orders?status=OPEN&from=2026-01-01&sort=createdAt,desc&page=0&size=20
~~~

Conceptually equivalent query:

~~~sql
SELECT id, tenant_id, status, created_at, total_amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at >= :from
ORDER BY created_at DESC, id DESC
LIMIT :limit
OFFSET :offset;
~~~

This is only an illustrative SQL shape. Placeholder names and `LIMIT`/`OFFSET` syntax vary by driver and database. With `R2dbcEntityTemplate`, Spring Data generates SQL using the database dialect.

## 2. Designing the search request DTO

Never accept an entity object directly as a search request. Create a DTO containing only the permitted filters and options:

~~~java
public record OrderSearchRequest(
    String status,
    Instant createdFrom,
    Instant createdTo,
    BigDecimal minAmount,
    BigDecimal maxAmount,
    String keyword,
    String sortBy,
    String sortDirection,
    Integer page,
    Integer size
) {
}
~~~

This DTO describes search criteria and does not hold a trusted tenant ID. The tenant must come from the authenticated security principal or context.

Some validation rules:

- `status` accepts only valid business values.
- `createdFrom` must not be after `createdTo`.
- `minAmount` must not exceed `maxAmount`.
- `keyword` has a maximum length.
- `sortBy` must belong to the allowed field list.
- `sortDirection` accepts only `ASC` or `DESC`.
- `page` is non-negative.
- `size` is greater than 0 and within the system maximum.

Validate at the HTTP boundary before calling the service or repository. The repository must still ensure queries are built safely, as it may be invoked from callers other than the controller.

## 3. Distinguishing absent filters, NULL filters, and concrete values

A common mistake is treating an omitted filter and a filter requesting `NULL` as the same state.

Three distinct cases exist:

| Request | Meaning |
|---|---|
| `assignedTo` omitted | Do not filter by `assignedTo` |
| `assignedTo=null` per API contract | Find rows where `assigned_to IS NULL` |
| `assignedTo=alice` | Find rows where `assigned_to = 'alice'` |

In a plain Java DTO, a `null` field can mean either "not sent" or "explicitly requesting NULL". If both must be supported, represent the state explicitly, for example with a filter wrapper carrying a `specified` flag or a dedicated request type.

Example:

~~~java
public record OptionalFilter<T>(
    boolean specified,
    T value
) {
}
~~~

When `specified` is `false`, omit the predicate. When `specified` is `true` and `value` is `null`, emit an `IS NULL` predicate. When `value` is non-null, emit an equality predicate.

Never automatically turn every `null` filter into `IS NULL`. Doing so can cause an unfiltered request to unexpectedly return only rows with `NULL` columns.

## 4. Building dynamic Criteria with R2dbcEntityTemplate

`Criteria` represents filter conditions on entity properties. Start with mandatory predicates, then append optional ones:

~~~java
private Criteria buildCriteria(
        Long tenantId,
        OrderSearchRequest request) {

    Criteria criteria = Criteria.where("tenantId").is(tenantId);

    if (request.status() != null) {
        criteria = criteria.and("status").is(request.status());
    }

    if (request.createdFrom() != null) {
        criteria = criteria.and("createdAt")
            .greaterThanOrEquals(request.createdFrom());
    }

    if (request.createdTo() != null) {
        criteria = criteria.and("createdAt")
            .lessThan(request.createdTo());
    }

    if (request.minAmount() != null) {
        criteria = criteria.and("totalAmount")
            .greaterThanOrEquals(request.minAmount());
    }

    if (request.maxAmount() != null) {
        criteria = criteria.and("totalAmount")
            .lessThanOrEquals(request.maxAmount());
    }

    return criteria;
}
~~~

Names passed to `Criteria.where(...)` are persistent entity property names mapped by Spring Data. Never pass arbitrary column names directly from the request.

The tenant predicate is added at the very start and is always mandatory. It is a data-scope guardrail, not an optional client-controlled filter.

### Querying entities

After building the criteria, construct a `Query`:

~~~java
public Flux<Order> search(
        Long tenantId,
        OrderSearchRequest request) {

    Criteria criteria = buildCriteria(tenantId, request);
    Sort sort = buildSort(request.sortBy(), request.sortDirection());

    int page = normalizePage(request.page());
    int size = normalizePageSize(request.size());
    long offset = Math.multiplyExact((long) page, size);

    Query query = Query.query(criteria)
        .sort(sort)
        .limit(size)
        .offset(offset);

    return template.select(query, Order.class).all();
}
~~~

Here `template` is an `R2dbcEntityTemplate` or a bean of type `R2dbcEntityOperations`. Verify the exact API against your Spring Data Relational version.

`limit` bounds the number of rows fetched; `offset` skips preceding rows. Never use a client-supplied offset directly without validation and upper bounds.

## 5. Combining AND conditions

Independent filters are typically combined with `AND`:

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at >= :from
  AND total_amount <= :maxAmount
~~~

When adding conditions conditionally, only append the active predicates:

~~~java
Criteria criteria = Criteria.where("tenantId").is(tenantId);

if (status != null) {
    criteria = criteria.and("status").is(status);
}

if (from != null) {
    criteria = criteria.and("createdAt").greaterThanOrEquals(from);
}
~~~

Avoid writing a catch-all predicate such as:

~~~sql
(:status IS NULL OR status = :status)
~~~

for every filter purely for convenience. That pattern can make query plans harder to optimize, especially with many optional filters and skewed data. Building queries with only the predicates actually in use usually gives the optimizer clearer information.

## 6. Combining OR conditions and grouping parentheses

Some searches require `OR` within a subgroup:

~~~sql
WHERE tenant_id = :tenantId
  AND (status = 'OPEN' OR status = 'PENDING')
~~~

With `Criteria`:

~~~java
Criteria statusCriteria =
    Criteria.where("status").is("OPEN")
        .or("status").is("PENDING");

Criteria criteria =
    Criteria.where("tenantId").is(tenantId)
        .and(statusCriteria);
~~~

The critical requirement is that the `OR` group stays parenthesized under the tenant condition. Never accidentally produce logic equivalent to:

~~~sql
WHERE (tenant_id = :tenantId AND status = 'OPEN')
   OR status = 'PENDING'
~~~

That broken query allows `PENDING` rows from other tenants to leak into the results.

For complex `OR` conditions, name each predicate group and review the boolean structure before executing. Writing dedicated helpers for `Criteria` groups helps prevent precedence bugs.

## 7. Common comparison operators

Spring Data Relational `Criteria` supports common comparisons:

| Need | Equivalent SQL predicate |
|---|---|
| Equals | `column = value` |
| Not equals | `column <> value` |
| Greater than | `column > value` |
| Greater than or equal | `column >= value` |
| Less than | `column < value` |
| Less than or equal | `column <= value` |
| In value set | `column IN (...)` |
| Within range | `column BETWEEN a AND b` |
| NULL | `column IS NULL` |
| Not NULL | `column IS NOT NULL` |
| Pattern match | `column LIKE pattern` |

Example:

~~~java
Criteria.where("totalAmount").between(
    request.minAmount(),
    request.maxAmount()
);
~~~

Only use `between` when both bounds are provided and inclusive semantics match the business rule. If either bound can be omitted, use `greaterThan`/`lessThan` variants accordingly.

## 8. List filtering with IN

Filtering by multiple statuses:

~~~java
Criteria.where("status").in(
    List.of("OPEN", "PENDING", "PAID")
);
~~~

Never let clients send unbounded lists. Cap the list size and validate every element.

### Empty IN lists

An empty list needs explicit semantics:

- If the filter was not provided, omit the predicate.
- If the filter was provided with an empty list, either return no rows or return a validation error.
- Never generate `SQL IN ()`, as syntax and behavior can fail or vary across databases.

Do not silently treat an empty list as "ignore filter", because that can return far more rows than the caller intended.

## 9. String filtering and LIKE

Prefix search:

~~~java
Criteria.where("customerName").like(prefix + "%");
~~~

Contains search:

~~~java
Criteria.where("customerName").like("%" + keyword + "%");
~~~

Values are bound as parameters by Spring Data. However, `%` and `_` are `LIKE` wildcards. If users want to match literal `%` or `_` characters, escape them per database syntax and specify the appropriate escape character.

Illustrative SQL example:

~~~sql
WHERE customer_name LIKE :pattern ESCAPE '\'
~~~

The escape character itself must be escaped first, followed by `%` and `_`, and only then should application-controlled wildcards be added. Verify `ESCAPE` syntax and collation behavior on your target database.

### Case-insensitive search

There is no single universally portable approach:

- PostgreSQL offers `ILIKE` and matching expression indexes.
- MySQL typically depends on column collation.
- SQL Server depends on collation.
- Oracle and SQLite have their own rules.

You can normalize data on write, choose an appropriate collation, or maintain a normalized column. If using `LOWER(column)`, consider an expression/functional index so the predicate can still use an index.

## 10. Time-range filtering

For time ranges, prefer half-open intervals:

~~~sql
created_at >= :from
AND created_at < :to
~~~

Example:

~~~java
if (request.createdFrom() != null) {
    criteria = criteria.and("createdAt")
        .greaterThanOrEquals(request.createdFrom());
}

if (request.createdTo() != null) {
    criteria = criteria.and("createdAt")
        .lessThan(request.createdTo());
}
~~~

Half-open intervals avoid inventing end-of-day timestamps like `23:59:59.999999` and behave consistently across varying timestamp precisions.

If the API accepts local dates, convert them to the start instant and next-day instant in the business timezone before calling the repository. Never assume every day is 24 hours long, because some timezones change offsets seasonally.

## 11. Numeric filtering and range validation

For min/max bounds:

- Only min: `amount >= min`.
- Only max: `amount <= max`.
- Both: `amount >= min AND amount <= max`.
- `min` greater than `max`: return a validation error.

Never convert monetary amounts through `double` when decimal precision is required. Use `BigDecimal` and matching column types.

For integer pagination or numeric ranges, check for overflow before multiplying or casting. For instance, compute offsets with `Math.multiplyExact((long) page, pageSize)` after bounding `page` and `size`.

## 12. Sorting must use an allowlist

Column names or identifiers cannot be protected by bind parameters the way values are. Never do this:

~~~java
String sql = "SELECT * FROM orders ORDER BY " + request.sortBy();
~~~

If a client passes `created_at DESC; DROP TABLE orders`, direct concatenation turns it into dangerous SQL.

Instead, map public sort names to allowed properties:

~~~java
private static final Map<String, String> SORT_FIELDS = Map.of(
    "createdAt", "createdAt",
    "status", "status",
    "amount", "totalAmount",
    "orderId", "id"
);
~~~

Building `Sort`:

~~~java
private Sort buildSort(String requestedField, String direction) {
    String property = SORT_FIELDS.get(requestedField);

    if (property == null) {
        throw new IllegalArgumentException("Unsupported sort field");
    }

    boolean descending = "desc".equalsIgnoreCase(direction);

    Sort.Order primary = descending
        ? Sort.Order.desc(property)
        : Sort.Order.asc(property);

    Sort.Order tieBreaker = descending
        ? Sort.Order.desc("id")
        : Sort.Order.asc("id");

    return Sort.by(primary, tieBreaker);
}
~~~

In practice, if `requestedField` already maps to `id`, do not append `id` a second time. If multiple sort fields are allowed, cap the number of fields, validate each one, and deduplicate them.

### Never use raw column names from the request

`Sort.by(request.getSortBy())` is safe only after the value passes an allowlist check. Even when Spring Data maps properties, clients should not arbitrarily choose internal fields to sort by, as this can leak data or trigger expensive queries.

Sort properties are typically entity property names under Spring Data mapping, not necessarily SQL column names. Map API fields to properties explicitly.

## 13. Default sort and deterministic ordering

If the client omits sort parameters, the application should apply a default order:

~~~java
Sort defaultSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
~~~

Ordering solely by `createdAt` is non-deterministic when multiple rows share the same timestamp. The database may return tied rows in different orders across runs.

Add a unique key:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

This establishes a total order when `id` is unique. A tie-breaker prevents pagination from duplicating or skipping rows when primary sort values collide.

When sorting by multiple columns, append the unique key last. The tie-breaker's sort direction must be defined consistently.

## 14. Null ordering and collation

`NULL` values may sort first or last depending on the database and direction. Spring Data `Sort` can represent null handling at the abstraction level, though drivers and dialects vary in support or SQL emulation.

If `NULL` ordering is a business requirement:

- Decide explicitly between `NULLS FIRST` and `NULLS LAST`.
- Verify database support.
- Test both `ASC` and `DESC`.
- Ensure keyset cursors encode `NULL` state properly.

String sorting also depends on collation: uppercase/lowercase order, Vietnamese diacritics, Unicode characters, and locales can differ. If the API requires a specific linguistic order, define collation/normalization in the database and test with real data.

## 15. Bounding page size and offset

Never trust client-supplied `page` and `size` values:

~~~java
private int normalizePage(Integer requestedPage) {
    if (requestedPage == null) {
        return 0;
    }
    if (requestedPage < 0) {
        throw new IllegalArgumentException("page must be >= 0");
    }
    return requestedPage;
}

private int normalizePageSize(Integer requestedSize) {
    int size = requestedSize == null ? 20 : requestedSize;

    if (size < 1 || size > 100) {
        throw new IllegalArgumentException(
            "size must be between 1 and 100"
        );
    }

    return size;
}
~~~

Capping `size` prevents a single request from loading hundreds of thousands of rows into memory or holding a connection for too long.

Offset:

~~~java
long offset = Math.multiplyExact((long) page, size);
~~~

Compute in `long` to avoid `int` overflow. You should still enforce a maximum `page` or maximum `offset` policy in the API, because very large offsets consume significant resources.

## 16. Offset pagination with Query

Offset pagination works well when:

- Users need to jump to arbitrary page numbers.
- Datasets are moderate in size.
- Data changes infrequently while users browse.
- Queries have indexes matching the filters and sort order.

Example:

~~~java
public Flux<Order> findPage(
        Criteria criteria,
        Sort sort,
        int page,
        int size) {

    long offset = Math.multiplyExact((long) page, size);

    Query query = Query.query(criteria)
        .sort(sort)
        .limit(size)
        .offset(offset);

    return template.select(query, Order.class).all();
}
~~~

With page 0 and size 20, the database returns at most the first 20 rows. With page 1000 and size 20, the database must walk past 20,000 rows before returning the slice. Sort-supporting indexes reduce the cost, but do not eliminate skipping many rows.

## 17. Why is offset pagination unstable when data changes?

Suppose page size is 3 and results are sorted by `createdAt` descending:

~~~text
Initially:
A, B, C | D, E, F
Page 1    Page 2
~~~

A user reads Page 1. Then a new row `X` is inserted at the top:

~~~text
After X arrives:
X, A, B | C, D, E | F
~~~

A Page 2 request with `OFFSET 3` returns `C, D, E`. Row `C` is duplicated because it already appeared on Page 1 before the data changed.

If an earlier row is deleted, Page 2 can skip a row instead. Deterministic sorting prevents instability from ties, but it cannot make offset pagination immune to concurrent inserts and deletes.

## 18. What is keyset pagination?

Keyset pagination (seek pagination) uses the values of the last row on the previous page as an anchor to fetch the next page. Instead of skipping N rows, the query asks for rows strictly after the cursor in sort order.

Example sort:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Cursor from the previous page:

~~~text
lastCreatedAt = 2026-01-10T10:30:00Z
lastId = 900
~~~

Next query:

~~~sql
WHERE tenant_id = :tenantId
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :size;
~~~

This condition expresses lexicographic ordering over the two descending sort keys.

Keyset pagination usually maintains steadier performance deep into a dataset because the database can seek directly from the cursor using a matching index. It also prevents duplicates when new rows are inserted ahead of the cursor.

## 19. Building Criteria for a keyset cursor

For sort `createdAt DESC, id DESC`:

~~~java
Criteria afterCursor =
    Criteria.where("createdAt")
        .lessThan(cursor.createdAt())
        .or(
            Criteria.where("createdAt")
                .is(cursor.createdAt())
                .and("id")
                .lessThan(cursor.id())
        );

Criteria criteria =
    Criteria.where("tenantId").is(tenantId)
        .and(afterCursor);
~~~

Combine this with other business filters and build the query:

~~~java
Query query = Query.query(criteria)
    .sort(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    ))
    .limit(pageSize + 1);
~~~

Fetch `pageSize + 1` rows to detect whether a next page exists:

~~~java
return template.select(query, Order.class)
    .all()
    .collectList()
    .map(rows -> {
        boolean hasNext = rows.size() > pageSize;

        List<Order> content = hasNext
            ? rows.subList(0, pageSize)
            : rows;

        return new CursorPage<>(
            content,
            hasNext,
            content.isEmpty()
                ? null
                : toCursor(content.get(content.size() - 1))
        );
    });
~~~

This is a skeleton example. Make sure the cursor is derived from the last row actually returned to the client, not the extra `pageSize + 1` lookahead row.

## 20. Keyset pagination with multiple sort columns

For ordering:

~~~sql
ORDER BY status ASC, created_at DESC, id DESC
~~~

The cursor must contain all three values. The "after cursor" predicate takes the form:

~~~sql
status > :lastStatus
OR (
    status = :lastStatus
    AND created_at < :lastCreatedAt
)
OR (
    status = :lastStatus
    AND created_at = :lastCreatedAt
    AND id < :lastId
)
~~~

Comparison operators must match each column's direction:

- `ASC`: subsequent values are greater than the cursor.
- `DESC`: subsequent values are less than the cursor.

With `NULL`s, collations, expression sorts, or complex types, model the exact comparison semantics used by your database. Never apply a naive formula blindly across arbitrary sorts.

If supporting dynamic multi-column sorts, the cursor builder must rely on the same allowlisted and normalized sort list. A simpler alternative is restricting the cursor API to a few predefined sort profiles.

## 21. Indexes for pagination

Given the query:

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT 50
~~~

A suitable index might be:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

This index can help:

1. Narrow down to the tenant range.
2. Filter by `status`.
3. Read rows in `createdAt` and `id` order.
4. Seek directly to the cursor in keyset pagination.

If `status` is an optional filter, an index starting with `(tenant_id, status)` does not always serve queries filtering only by `tenant_id` and sorting by `created_at` well. Another index `(tenant_id, created_at, id)` may be needed if workload measurements prove it worthwhile.

Do not create every possible index combination. Measure common search profiles and balance write overhead.

## 22. Total record counts and count queries

A `Page`-style API often returns:

- List of rows.
- Page number and page size.
- Total matching rows.
- Total pages.

The count query must use the exact same predicates as the data query:

~~~java
Mono<Long> count = template.count(
    Query.query(criteria),
    Order.class
);
~~~

Never run a count without the tenant filter or omit a business condition, as that can leak out-of-scope record counts.

### Counting can be expensive

`COUNT(*)` on a large dataset still needs to scan matching rows or consult database-specific structures. A query fetching the first 20 rows may be fast while counting all matches is considerably slower.

API options:

- `Page`: returns total count when genuinely required by the business.
- `Slice`: returns content and `hasNext`, typically via `limit + 1`, avoiding a total count.
- `Cursor page`: returns the next cursor and `hasNext`.

If the UI only needs a "Load more" button, skip counting total rows. Using cursor/slice pagination reduces database work.

### Keeping filters identical

Build `criteria` once and reuse it for both `select` and `count`. Never copy and paste filter logic in two places, as divergence causes total counts to mismatch the returned content.

If both queries must observe the same snapshot, run them sequentially inside a transaction with an isolation level appropriate for your database. Under `READ COMMITTED`, separate statements can see different snapshots in some RDBMS engines. Never assume every database shares identical isolation semantics.

## 23. Reactive pagination and memory limits

R2DBC emits results via reactive publishers. With a bounded page size, collecting a small page into a `List` to build a DTO is fine:

~~~java
template.select(query, Order.class)
    .all()
    .collectList();
~~~

Never collect the entire table and paginate in Java:

~~~java
// Unsuitable for large datasets
repository.findAll()
    .collectList()
    .map(all -> all.subList(start, end));
~~~

That pulls every row over the network, consumes heap memory, and holds resources longer. Filtering, sorting, and pagination belong in the database.

If exporting large datasets, use controlled streaming with appropriate fetch/chunk sizes and backpressure handling. Never turn an export into a gigantic page size.

## 24. Combining multiple filters in a search service

You can structure a service in clear steps:

~~~java
public Flux<Order> search(
        OrderSearchRequest request,
        CurrentUser currentUser) {

    Long tenantId = currentUser.tenantId();

    Criteria criteria = buildCriteria(tenantId, request);
    Sort sort = buildValidatedSort(request);
    int page = normalizePage(request.page());
    int size = normalizePageSize(request.size());

    Query query = Query.query(criteria)
        .sort(sort)
        .limit(size)
        .offset(Math.multiplyExact((long) page, size));

    return template.select(query, Order.class).all();
}
~~~

The service obtains the tenant from the authenticated principal. Never let a request switch tenants via a query parameter unless the domain explicitly supports a separately authorized cross-tenant permission.

In larger systems, you can separate:

- `OrderFilterBuilder`: builds `Criteria`.
- `OrderSortPolicy`: validates and builds `Sort`.
- `PageRequestValidator`: normalizes page/size.
- `OrderSearchRepository`: executes queries.

Only split classes when doing so improves reuse or clarity of responsibilities. Avoid over-engineering a generic framework for a simple search endpoint.

## 25. Using DatabaseClient for dynamic SQL

When complex SQL is required, build the `WHERE` clause from allowlisted predicates while still binding values:

~~~java
DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(
    "SELECT id, status, created_at " +
    "FROM orders WHERE tenant_id = :tenantId"
).bind("tenantId", tenantId);

if (status != null) {
    spec = spec.bind("status", status);
}
~~~

The snippet above only illustrates binding and is incomplete because the SQL itself must include the corresponding predicate before calling `sql()`. A safe builder constructs SQL fragments from fixed code branches alongside a binding map of values.

Conceptual example:

~~~java
StringBuilder sql = new StringBuilder(
    "SELECT id, status, created_at FROM orders WHERE tenant_id = :tenantId"
);

Map<String, Object> bindings = new HashMap<>();
bindings.put("tenantId", tenantId);

if (status != null) {
    sql.append(" AND status = :status");
    bindings.put("status", status);
}

if (createdFrom != null) {
    sql.append(" AND created_at >= :createdFrom");
    bindings.put("createdFrom", createdFrom);
}
~~~

In a complete implementation:

1. Build SQL only from fixed fragments owned by the application.
2. Append fragments strictly based on validated booleans/enums.
3. Bind every value through `DatabaseClient`.
4. Pull sort fields from an allowlist mapped to fixed identifiers.
5. Ensure `limit`/`offset` are bounded integers.

Never concatenate `status`, `keyword`, `tenantId`, or date values directly into SQL.

### Binding lists

Binding collections into `IN` clauses depends on the named-parameter expander API and driver. Verify support in your Spring Framework/Spring Data R2DBC version. For large lists, consider chunking, temporary tables, or database-specific strategies instead of generating thousands of placeholders.

## 26. Dynamic SQL and column names

Bind parameters cannot substitute for identifiers:

~~~sql
ORDER BY :columnName
~~~

Normally that sorts by a constant parameter value rather than a dynamic column name.

When using `DatabaseClient`:

- Use column names only from an allowlist.
- Never accept raw SQL expressions from clients.
- Never let clients pass `ASC`/`DESC` as raw SQL text; parse into an enum.
- Quote identifiers per dialect if needed.
- Never concatenate a sort string from the URL directly into the statement.

Even with Spring Data `Criteria`/`Sort`, still enforce an allowlist so clients cannot sort by sensitive columns, wide columns, or unindexed expressions that trigger costly queries.

## 27. Paginating with dynamic sorts requires matching cursors

If the API supports multiple sort profiles, the cursor must accurately reflect the active sort:

~~~json
{
  "sort": [
    {"field": "createdAt", "direction": "DESC"},
    {"field": "id", "direction": "DESC"}
  ],
  "lastValues": [
    "2026-01-10T10:30:00Z",
    900
  ]
}
~~~

This is a conceptual structure only. An API can issue an opaque cursor instead of raw JSON so clients do not depend on its internals.

Cursors should be:

- Validated for structure and data types.
- Bound to the appropriate tenant or principal.
- Bound to the active filter and sort profile.
- Versioned so formats can evolve.
- Signed or integrity-protected if clients can tamper with them.

Base64 only encodes representation; it provides neither confidentiality nor tamper protection. If a cursor carries sensitive data, sign or encrypt it as needed.

Never trust a cursor from a client merely because the server issued it previously. Verify it still matches the current request.

## 28. Stability when data is updated

Keyset pagination is more stable than offset pagination when new rows are inserted ahead of the cursor, yet it does not create an immutable snapshot across an entire browsing session:

- Already-read rows can be deleted.
- Sort values on unread rows can change, moving them across the cursor boundary.
- Filter membership can change when status or tenant metadata updates.
- Newly inserted rows after the cursor can appear on subsequent pages depending on sort values.

If the business requires a strictly consistent dataset throughout a browsing session, consider:

- A snapshot transaction with appropriate isolation and bounded lifetime.
- A high-water mark such as `createdAt <= snapshotTime`.
- An export job producing a fixed dataset.
- Dataset versioning/watermarks.

Long-lived snapshot transactions hold connections, snapshots, or database resources. Never keep a reactive transaction open across multiple user HTTP page requests if session duration is unbounded.

## 29. Pagination and isolation levels

Offset or keyset pagination across separate HTTP requests usually executes in separate transactions, so each request can observe a different database state.

If a count and content query within the same request must see the same snapshot:

1. Run both queries inside a single transaction.
2. Choose an isolation level whose snapshot semantics match your database.
3. Execute them sequentially if the driver/connection does not support concurrent statements.
4. End the transaction immediately after building the response.

Never assume `READ COMMITTED`, `REPEATABLE READ`, and `SNAPSHOT` behave identically across PostgreSQL, MySQL, SQL Server, and Oracle.

## 30. Sorting on relationships and nested properties

Some screens need to sort by a related attribute, such as an order's customer name. Spring Data Relational does not provide JPA-style lazy relationship loading; sorting by nested properties does not automatically guarantee the expected join is generated.

When sorting by columns from a related table:

- Write an explicit `JOIN` query using `DatabaseClient` or a custom repository.
- Use a view or materialized view if appropriate.
- Denormalize the sort value if business rules and consistency permit.
- Define indexes on join keys and sort keys.

Never pass `customer.name` blindly into `Sort` assuming Spring Data R2DBC will generate a `JOIN`.

## 31. Controlling filter and sort costs

Not all filters are cheap. The following can be expensive:

- `%keyword%` on large tables.
- `OR` across multiple columns without supporting indexes.
- Very long `IN` lists.
- Functions or casts wrapped around columns.
- Sorting by low-cardinality columns across large row sets.
- Filtering on unindexed JSON expressions.

The API should cap:

- Maximum number of filters.
- Keyword length.
- Number of elements in `IN` lists.
- Number of sort fields.
- Page size and offset.
- Maximum search time range when domain rules allow.
- Supported sort/filter combinations.

Check query plans on representative data. Providing a few pre-tuned search profiles is often better than allowing arbitrary, unbounded combinations.

## 32. Indexes for common search profiles

Suppose there are three frequent queries:

**Find orders by tenant and status, newest first**

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC, id DESC
~~~

Candidate index to test:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

**Find all orders for a tenant, newest first**

~~~sql
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
~~~

A separate index may be needed:

~~~sql
CREATE INDEX idx_orders_tenant_created
ON orders (tenant_id, created_at DESC, id DESC);
~~~

**Find by time range within a tenant**

~~~sql
WHERE tenant_id = :tenantId
  AND created_at >= :from
  AND created_at < :to
~~~

An index on `(tenant_id, created_at)` may help.

These are candidates to verify with `EXPLAIN`. Do not create all three indexes if one already satisfies the workload or if write amplification is unacceptable.

## 33. Testing dynamic filters

Cover every filter state in tests:

- Omitted filter.
- Valid value.
- Invalid value.
- Explicitly requested `NULL` value.
- Single-sided min/max range.
- `min` greater than `max`.
- Empty `IN` list.
- Single-element and multi-element `IN` lists.
- Keywords containing `%`, `_`, and escape characters.
- Tenant A cannot read Tenant B's rows.
- `OR` groups cannot bypass the tenant predicate.

Also test queries with no optional filters to verify the tenant predicate is always enforced.

## 34. Testing sorting and pagination

Test sorting:

- Allowlisted fields succeed.
- Unsupported fields are rejected.
- `ASC` and `DESC` return expected orderings.
- Multiple rows with identical `createdAt` are tie-broken by `id`.
- `NULL` ordering matches requirements.
- String sorting respects the chosen collation.

Test offset pagination:

- First page.
- Middle page.
- Empty page.
- Negative page.
- Size 0 and oversized requests.
- Offset overflow or limit exceeded.
- Concurrent inserts/deletes between calls, documenting acceptable semantics.

Test keyset pagination:

- Initial fetch with no cursor input.
- Subsequent cursor fetches do not duplicate rows.
- Multiple rows sharing primary sort values.
- Malformed or tampered cursor.
- Cursor belonging to another tenant.
- Cursor used with different filters/sort than the current request.
- Rows deleted or re-sorted during traversal.

Use integration tests against the real R2DBC driver and database to verify mapping, `NULL` handling, collation, ordering, and cursor predicates.

## 35. Example response for offset pagination

A response can include:

~~~json
{
  "content": [
    {
      "id": 900,
      "status": "OPEN"
    },
    {
      "id": 899,
      "status": "OPEN"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 135,
  "totalPages": 7
}
~~~

This structure suits clients needing page numbers. Total counts can increase query cost.

## 36. Example response for cursor pagination

A cursor response:

~~~json
{
  "content": [
    {
      "id": 900,
      "status": "OPEN"
    },
    {
      "id": 899,
      "status": "OPEN"
    }
  ],
  "hasNext": true,
  "nextCursor": "opaque-signed-cursor"
}
~~~

The client simply sends the cursor back on the next request. It does not need to know about `createdAt` or `id` inside an opaque token.

## 37. Common pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Concatenating filter values into SQL | SQL injection | Use Criteria or bind parameters |
| Using raw sort fields from the request | Identifier injection or unexpected queries | Allowlist and map to entity properties |
| Making the tenant filter optional | Can leak rows from other tenants | Derive tenant from principal and always include predicate |
| Misgrouping OR predicates | OR branch can bypass tenant scope | Wrap OR branches in their own Criteria group |
| Treating null filters as IS NULL | Unfiltered requests return wrong rows | Distinguish absent, explicit null, and concrete values |
| Skipping empty IN list validation | SQL syntax errors or unintended filter omission | Define explicit semantics |
| Not escaping LIKE wildcards | Broader matches than intended | Escape %, _, and the escape character |
| Sorting without a tie-breaker | Rows shift across pages | Append a unique key at the end of the sort |
| Allowing unbounded page sizes | Exhausts memory, connections, and DB CPU | Enforce a maximum size |
| Using very large offsets | Queries slow down at deep pages | Consider keyset pagination |
| Using keyset with missing cursor sort values | Skipped or duplicated rows | Include all sort keys and unique tie-breaker in cursor |
| Not binding cursors to filters/tenants | Cursors can be replayed out of scope | Validate/sign cursors against request context |
| Count query diverges from filter query | totalElements mismatches content | Share a single Criteria builder |
| Assuming count and content share a snapshot | Metadata and rows skew under concurrent writes | Use an appropriate transaction and isolation level |
| Collecting repository.findAll() in memory | Wastes heap and network bandwidth | Filter and paginate in the database |
| Sorting by nested relations as in JPA | Does not auto-generate JOINs as expected | Write explicit JOINs or custom queries |
| Guessing indexes without query profiles | Redundant or poorly ordered indexes | Inspect EXPLAIN and measure workload |

## 38. Implementation workflow for a search endpoint

You can implement a search endpoint in this order:

1. Define the search DTO with supported filters.
2. Validate types, ranges, lengths, and filter counts.
3. Obtain tenant/ownership scope from the security context.
4. Build `Criteria` starting with mandatory predicates.
5. Append optional filters using explicit semantics.
6. Group `AND`/`OR` predicates with proper parentheses.
7. Validate sort fields and direction against an allowlist.
8. Append a unique tie-breaker to the sort order.
9. Normalize page/size and bound offsets.
10. Choose offset or keyset pagination based on the use case.
11. Build the `Query` and execute via `R2dbcEntityTemplate`.
12. Add a count query only if the API truly needs totals.
13. Ensure count and content share identical filter logic.
14. Inspect execution plans and design indexes for the workload.
15. Write integration tests for filters, sorting, tenant scope, and concurrent data changes.

## 39. Key takeaways

- Use Spring Data R2DBC `Criteria`/`Query` to construct dynamic filters over entity properties.
- Use `DatabaseClient` when custom SQL is needed, always binding values.
- Distinguish omitted filters, explicit `NULL` filters, and concrete values.
- Group `AND`/`OR` logic carefully; always apply tenant scope from an authenticated source.
- Handle empty `IN` lists and `LIKE` wildcards with explicit semantics.
- Never accept raw sort identifiers; map API fields through an allowlist.
- Default sorts must be deterministic and should include a unique tie-breaker such as `id`.
- Validate page, size, and offset, and cap maximum page size.
- Offset pagination supports random page access but degrades at deep offsets and shifts under concurrent inserts/deletes.
- Keyset pagination anchors on the last row's values, fits large datasets, and avoids offset costs.
- Cursors must include all sort values, bind to active filters/tenants, and be integrity-protected if client-modifiable.
- Count queries must reuse the same filters; `Page` with total counts costs more than `Slice` or cursor pages.
- Reactive pagination belongs in the database; never collect entire tables in application memory.
- Isolation levels and snapshot semantics vary across databases; never hold transactions across multiple HTTP requests.
- Relationship sorting requires explicit `JOIN`s or custom queries in Spring Data Relational.
- Design indexes around actual search profiles, predicates, sort orders, and execution plans.
- Test against your target database and R2DBC driver, covering `NULL`s, collations, tie-breakers, cursors, and concurrent modifications.
