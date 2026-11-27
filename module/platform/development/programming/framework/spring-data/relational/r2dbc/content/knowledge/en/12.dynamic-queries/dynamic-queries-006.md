# Selecting Columns, Sorting, and Limiting Results

Dynamic queries in Spring Data R2DBC often need to vary three parts based on the caller's request: the set of columns read, the sort order, and the number of rows returned. A list API might only need an ID and name to display a table, sort by creation date or name, and return at most 20 results per request. Always reading the full entity, always using a fixed order, and loading every row into Java wastes I/O, memory, and processing time.

Spring Data R2DBC provides `Query`, `Criteria`, and `Sort` to build queries against entity metadata. For custom SQL or dedicated projections, `DatabaseClient` allows specifying columns, `ORDER BY`, `LIMIT`, and `OFFSET` directly. Regardless of the API used, client-supplied inputs must be validated: values can be bound as parameters, while column names and sort directions must be selected from an allow-list.

## 1. Why Select Specific Columns and Limit Results?

Suppose the `person` table has columns `id`, `firstname`, `lastname`, `email`, `phone`, `address`, `created_at`, `updated_at`, `profile_json`, and `notes`. A list screen only displays ID, full name, and email. If the application runs `SELECT *`, the database must read and transfer unnecessary columns, which may include large payloads such as JSON or notes.

Three decisions make the query leaner:

- **Projection (column selection):** read only the fields required by the use case.
- **Sort:** define a deterministic order suited to how users view the data.
- **Limit:** retrieve only the slice of data needed for display or processing in one pass.

SQL example:

```sql
SELECT id, firstname, lastname, email
FROM person
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
```

This query avoids loading `profile_json`, `address`, or `notes`; results are ordered by newest creation timestamp and capped by page size. `id` is added as a secondary key so rows sharing the same `created_at` still have a deterministic order.

Selecting fewer columns does not automatically make every query faster: the database still has to locate matching rows and may need to read the required data pages. However, projections typically reduce network payload size, mapping overhead, and avoid loading large unused fields.

## 2. Selecting Columns with SQL Projections

With `DatabaseClient`, the `SELECT` clause specifies directly which columns to read. For example, create a DTO dedicated to the list screen:

```java
public record PersonSummary(
    Long id,
    String firstname,
    String lastname,
    String email
) {}
```

A custom repository can map results into the DTO:

```java
@Repository
public class PersonQueryRepository {

    private final DatabaseClient databaseClient;

    public PersonQueryRepository(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<PersonSummary> findSummaries(String status, int pageSize) {
        return databaseClient.sql("""
                SELECT id, firstname, lastname, email
                FROM person
                WHERE status = :status
                ORDER BY created_at DESC, id DESC
                LIMIT :pageSize
                """)
            .bind("status", status)
            .bind("pageSize", pageSize)
            .map((row, metadata) -> new PersonSummary(
                row.get("id", Long.class),
                row.get("firstname", String.class),
                row.get("lastname", String.class),
                row.get("email", String.class)
            ))
            .all();
    }
}
```

The DTO clarifies the data needed by the use case and avoids turning a full entity into a one-size-fits-all object across every screen. If `PersonSummary` is read-only, do not use it to write back to the table as though it were a complete entity.

### Selecting Columns by API Need

If an API has a few fixed projection shapes, creating dedicated methods or DTOs is usually best. For example:

- `PersonListItem`: ID, full name, and email for lists.
- `PersonContact`: ID, email, and phone number for contact features.
- `PersonDetail`: fields needed for the detail screen.

This keeps SQL statements and return types clearly structured and easy to verify when schemas change. There is no need to build an arbitrary-column selection API if the product only has a handful of well-defined screens.

### When Dynamic Column Selection Is Truly Needed

Some APIs let clients specify a list of fields to receive. SQL column names cannot be passed via bind parameters like regular values. Therefore, public field names must be mapped to fixed column expressions in code:

```java
private static final Map<String, String> SELECTABLE_COLUMNS = Map.of(
    "id", "p.id AS id",
    "firstName", "p.firstname AS first_name",
    "lastName", "p.lastname AS last_name",
    "email", "p.email AS email"
);

private List<String> resolveColumns(List<String> requestedFields) {
    if (requestedFields == null || requestedFields.isEmpty()) {
        return List.of(
            SELECTABLE_COLUMNS.get("id"),
            SELECTABLE_COLUMNS.get("firstName"),
            SELECTABLE_COLUMNS.get("lastName")
        );
    }

    return requestedFields.stream()
        .map(field -> {
            String column = SELECTABLE_COLUMNS.get(field);
            if (column == null) {
                throw new IllegalArgumentException("Unsupported field: " + field);
            }
            return column;
        })
        .distinct()
        .toList();
}
```

After resolving, concatenate only pre-defined expressions into the `SELECT` clause. All filter values must still use bind parameters. With dynamic projections of varying shape, the return type can be a map or flexible structure; keep column aliases stable for straightforward mapping.

Never accept raw `fields` strings from a request to concatenate into SQL. A string like `id, (SELECT ...)` or a malicious SQL expression can alter query semantics. An allow-list must validate both column names and allowed expressions.

## 3. Selecting Columns with R2dbcEntityTemplate

When queries still operate on entities and want to leverage mapping metadata, `Query` can be combined with `Columns` to specify columns to fetch:

```java
public Flux<Person> findBasicPeople(String status) {
    Query query = Query.query(Criteria.where("status").is(status))
        .columns(Columns.include("id", "firstname", "lastname"));

    return template.select(Person.class)
        .matching(query)
        .all();
}
```

`Columns.include(...)` specifies which properties/columns are included in the result. Spring Data uses mapping metadata to translate entity property names to column names per mapping configuration.

When reading only a subset of columns into an entity, unselected properties may lack values in the mapped object. Treat such results as partial read data. Do not fetch a partially populated entity and then call `save()` as if it were a complete record, because unloaded fields may lack values required for writes. For read-only projections, a dedicated DTO via `DatabaseClient` usually communicates intent better.

The `Columns` API and `Query` overloads must be checked against your Spring Data Relational version. If your version or query style does not support the desired projection, use `DatabaseClient` for explicit SQL.

## 4. Sorting with Sort

Sorting determines the order of returned rows. In Spring Data Relational, `Sort` describes properties and sort directions; `Query` combines `Sort` with `Criteria` conditions.

Example sorting people by last name ascending:

```java
public Flux<Person> findByStatus(String status) {
    Query query = Query.query(Criteria.where("status").is(status))
        .sort(Sort.by(Sort.Order.asc("lastname")));

    return template.select(Person.class)
        .matching(query)
        .all();
}
```

Multiple sort fields can be combined:

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("lastname"),
    Sort.Order.asc("id")
);
```

Order is applied sequentially: first by `createdAt` descending; if two rows share the same timestamp, compare `lastname`; if still tied, compare `id`. Adding a unique secondary key like ID keeps ordering deterministic during pagination.

Property names in `Sort` are typically the entity's Java property names. Spring Data translates them to physical column names via the mapping context. When using `DatabaseClient`, SQL uses actual database column names.

## 5. Safely Selecting Sort Fields and Directions from Requests

List APIs may accept `sortBy` and `direction` query parameters. Never place those strings directly into `ORDER BY`:

```java
// Unsafe: sortBy and direction come from the request.
String sql = "SELECT id, firstname FROM person ORDER BY "
    + sortBy + " " + direction;
```

Bind parameters are only for values. Column names and `ASC`/`DESC` keywords are part of SQL structure and must be controlled separately.

### Allow-List for Sort Properties

With `R2dbcEntityTemplate`, map API field names to entity property names:

```java
private String resolveSortProperty(String sortBy) {
    return switch (sortBy == null ? "" : sortBy) {
        case "firstName" -> "firstname";
        case "lastName" -> "lastname";
        case "createdAt" -> "createdAt";
        case "email" -> "email";
        default -> "id";
    };
}

private Sort.Direction resolveDirection(String direction) {
    return "asc".equalsIgnoreCase(direction)
        ? Sort.Direction.ASC
        : Sort.Direction.DESC;
}
```

Then construct `Sort` from the controlled values:

```java
String property = resolveSortProperty(sortBy);
Sort.Direction direction = resolveDirection(directionParam);

Sort sort = Sort.by(
    new Sort.Order(direction, property),
    Sort.Order.asc("id")
);
```

Here, any unrecognized value falls back to the default order. Another API might return HTTP 400 when `sortBy` is invalid; the key rule is never turning unvalidated strings into column names.

### Allow-List for SQL with DatabaseClient

When writing SQL manually, map to physical column names:

```java
String orderColumn = switch (sortBy == null ? "" : sortBy) {
    case "firstName" -> "firstname";
    case "lastName" -> "lastname";
    case "createdAt" -> "created_at";
    case "email" -> "email";
    default -> "id";
};

String orderDirection = "asc".equalsIgnoreCase(directionParam)
    ? "ASC"
    : "DESC";
```

Both variables take values exclusively from fixed code branches, so they can be placed into the `ORDER BY` clause. Values such as status, ID, or search keywords must still be bound via `.bind(...)`.

Do not pass client data directly into `Sort.Direction.valueOf(directionParam)` without catching and handling invalid inputs. Also avoid using Java property names in raw SQL if physical column names differ.

## 6. Limiting Results with Query.limit

When using `R2dbcEntityTemplate`, row limits can be set directly on `Query`:

```java
public Flux<Person> findFirstPeople(String status, int pageSize) {
    int safePageSize = Math.max(1, Math.min(pageSize, 100));

    Query query = Query.query(Criteria.where("status").is(status))
        .sort(Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("id")))
        .limit(safePageSize);

    return template.select(Person.class)
        .matching(query)
        .all();
}
```

`limit(...)` instructs the database to return at most the specified number of rows. Enforcing a server-side maximum prevents a request with a huge `pageSize` from inflating memory usage, query latency, and connection hold times.

`Flux` emits rows reactively; that does not mean the database automatically caps row counts if SQL or Query lacks a limit. Do not fetch hundreds of thousands of rows and apply Reactor's `take(20)` if your goal is reducing the volume of data the database returns. Place the limit inside the database query.

## 7. Combining Conditions, Columns, Sort, and Limit

A dynamic query can combine status filtering, projection, sorting, and limits:

```java
public Flux<Person> searchPeople(
        String status,
        String sortBy,
        String direction,
        int pageSize) {

    int safePageSize = Math.max(1, Math.min(pageSize, 100));
    String property = resolveSortProperty(sortBy);
    Sort.Direction sortDirection = resolveDirection(direction);

    Criteria criteria = Criteria.where("status").is(status);

    Query query = Query.query(criteria)
        .columns(Columns.include("id", "firstname", "lastname", "email"))
        .sort(Sort.by(
            new Sort.Order(sortDirection, property),
            Sort.Order.asc("id")
        ))
        .limit(safePageSize);

    return template.select(Person.class)
        .matching(query)
        .all();
}
```

This code illustrates combining query APIs; corresponding imports typically include `Criteria`, `Query`, `Columns`, and `Sort` from Spring Data Relational. Verify specific overloads in your application's release train.

If the query only needs a DTO, use `DatabaseClient` to define projections and mapping explicitly. If a full entity is needed for update logic, consider whether partial column selection is appropriate; incomplete entities are better suited to reads than writes.

## 8. Limiting Results with LIMIT in DatabaseClient

With custom SQL, `LIMIT` caps row count. PostgreSQL example:

```java
public Flux<PersonSummary> findPage(
        String status,
        int pageSize,
        long offset) {

    int safePageSize = Math.max(1, Math.min(pageSize, 100));
    long safeOffset = Math.max(0, offset);

    return databaseClient.sql("""
            SELECT id, firstname, lastname, email
            FROM person
            WHERE status = :status
            ORDER BY created_at DESC, id DESC
            LIMIT :pageSize OFFSET :offset
            """)
        .bind("status", status)
        .bind("pageSize", safePageSize)
        .bind("offset", safeOffset)
        .map((row, metadata) -> new PersonSummary(
            row.get("id", Long.class),
            row.get("firstname", String.class),
            row.get("lastname", String.class),
            row.get("email", String.class)
        ))
        .all();
}
```

In this example, `pageSize` and `offset` are bounds-checked in Java and then bound as values. PostgreSQL supports parameters in `LIMIT` and `OFFSET`; pagination syntax may differ on SQL Server or other database engines. Adjust according to your dialect and driver capabilities.

Limiting returned rows does not mean limiting the total rows the database must examine. Without indexes matching the filter and sort, the database may still scan or sort a large dataset before returning `LIMIT` rows. Therefore, inspect execution plans and design indexes for your queries.

## 9. Offset Pagination

Offset pagination splits results into fixed-size pages. For the first page, offset is typically 0; the second page has offset equal to page size; the general formula is:

\[
\text{offset} = (\text{pageNumber} - 1) \times \text{pageSize}
\]

Example:

| Page | Page size | Offset |
|---:|---:|---:|
| 1 | 20 | 0 |
| 2 | 20 | 20 |
| 3 | 20 | 40 |
| 4 | 20 | 60 |

Advantages of offset pagination:

- Easy to understand and implement.
- Fits UIs with page numbers and jump-to-page navigation.
- Can be paired with total record count to show page counts.

Limitations:

- Large offsets can force the database to scan and discard many rows.
- If rows are inserted or deleted between requests, items can shift across pages, causing duplicates or omissions.
- Counting total rows to display page totals can be expensive on large datasets.

When using offset, always specify a deterministic `ORDER BY`. Sorting solely by `created_at` leaves order undefined among rows with identical timestamps. Add ID or a unique key as a tie-breaker.

## 10. Keyset Pagination (Cursor Pagination)

For large datasets or infinite-scroll feeds, keyset pagination is often more efficient than offset pagination. Instead of asking to skip N rows, the client sends the last row's values from the previous page as a cursor.

Assuming sorting by `created_at DESC, id DESC`, the next-page query can be:

```sql
SELECT id, firstname, lastname, created_at
FROM person
WHERE status = :status
  AND (
      created_at < :cursorCreatedAt
      OR (created_at = :cursorCreatedAt AND id < :cursorId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
```

The cursor includes both `created_at` and `id` because both fields define the ordering. Using only `created_at` could duplicate or skip rows sharing the same timestamp across pages.

A suitable index might be:

```sql
CREATE INDEX idx_person_status_created_id
    ON person (status, created_at DESC, id DESC);
```

This index is a starting point to test; verify with execution plans and real data. Keyset pagination is especially useful when users advance sequentially from the current page, though it is inconvenient for jumping directly to page 100.

### Cursor Implementation Example with DatabaseClient

The cursor query DTO contains both display fields and the timestamp field needed to build the cursor for the next page:

```java
public record PersonCursorItem(
    Long id,
    String firstname,
    String lastname,
    Instant createdAt
) {}
```

```java
public Flux<PersonCursorItem> findNextPage(
        String status,
        Instant cursorCreatedAt,
        Long cursorId,
        int pageSize) {

    int safePageSize = Math.max(1, Math.min(pageSize, 100));

    return databaseClient.sql("""
            SELECT id, firstname, lastname, created_at
            FROM person
            WHERE status = :status
              AND (
                  created_at < :cursorCreatedAt
                  OR (created_at = :cursorCreatedAt AND id < :cursorId)
              )
            ORDER BY created_at DESC, id DESC
            LIMIT :pageSize
            """)
        .bind("status", status)
        .bind("cursorCreatedAt", cursorCreatedAt)
        .bind("cursorId", cursorId)
        .bind("pageSize", safePageSize)
        .map((row, metadata) -> new PersonCursorItem(
            row.get("id", Long.class),
            row.get("firstname", String.class),
            row.get("lastname", String.class),
            row.get("created_at", Instant.class)
        ))
        .all();
}
```

This example illustrates the case where a cursor is already present. For the first page, use a query branch without the cursor condition or construct the query accordingly; never bind `null` into comparisons expecting it to act as unfiltered. Actual DTOs should match selected columns exactly.

If sort columns allow `NULL`, define `NULLS FIRST`/`NULLS LAST` rules and incorporate that rule into the cursor. The simplest approach is choosing `NOT NULL` cursor columns or normalizing null values into a deterministic expression.

## 11. Consistency of Ordering and Pagination

Deterministic sorting is critical when combined with limit and offset. A query without `ORDER BY` guarantees no row order. The database may return rows in different orders depending on execution plans, indexes, or data changes.

Even with `ORDER BY` on a non-unique column, rows sharing the same value can appear in different orders across queries. Append a unique column at the end of the sort list.

With frequently changing data, offset pagination can still shift page contents between calls. If users require browsing a consistent snapshot, consider transaction isolation, snapshot tokens, or storing a query timestamp. Avoid keeping a database transaction open across the entire time a user reads multiple pages; that holds connections and snapshots open for too long. Cursors based on immutable or rarely changing columns are usually more suitable.

## 12. Handling Nulls in Sorting and Data Types

Database engines can differ in default ordering for `NULL` values. If a sort field is nullable, results may vary across databases or sort directions.

Some engines support `NULLS FIRST` or `NULLS LAST` syntax. If using `Sort`, verify your Spring Data version's null handling API and dialect translation support. For exact control, use database-specific SQL.

Avoid sorting by expensive expressions like `LOWER(name)` or `CAST(...)` on large datasets without inspecting the execution plan. If a use case frequently sorts case-insensitively, a functional index or normalized column may be needed depending on the database.

Data types also affect ordering: strings compare by collation, numbers by numeric value, timestamps by instant. Storing dates as strings can cause lexicographical order to diverge from chronological order. Use proper column types and clear timezone conventions.

## 13. Capping Page Size and Protecting Resources

Never let clients request an arbitrary page size. A request could send `pageSize=1000000` and force the application to generate an enormous data stream. Set server-side default and maximum limits:

```java
private int normalizePageSize(Integer requested) {
    if (requested == null) {
        return 20;
    }
    return Math.max(1, Math.min(requested, 100));
}
```

Maximum size should be based on projection size, query latency, database load, and consumer capacity. If clients need bulk data exports, build a dedicated export endpoint or streaming job with quotas, timeouts, and concurrency controls; do not raise regular API page sizes indefinitely.

With `Flux`, backpressure lets consumers regulate item consumption rate, but it does not replace `LIMIT`. An unbounded query can still trigger heavy database work and hold a connection open while the publisher is consumed.

## 14. Optimizing Indexes for Filter, Sort, and Limit

Queries frequently combine `WHERE`, `ORDER BY`, and `LIMIT`. Indexes must support both filtering and ordering to avoid scanning or sorting many rows.

For example:

```sql
SELECT id, firstname, lastname, created_at
FROM person
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

A candidate index:

```sql
CREATE INDEX idx_person_status_created_id
    ON person (status, created_at DESC, id DESC);
```

`status` leads because it is filtered with equality; trailing columns serve the sort order. However, effectiveness depends on `status` selectivity, row count, database engine, and other queries. A separate index may be needed if many queries filter only by `created_at` or sort by another field.

If the projection is small, some databases support covering indexes or `INCLUDE` clauses to satisfy queries without reading the heap/table for every column. This is a database-specific optimization that increases index size; apply it only after measuring.

Verify queries with `EXPLAIN` or equivalent tools. In PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` shows the execution plan, timing, and buffer reads; statements with `ANALYZE` actually execute the query.

## 15. Total Pages and COUNT Queries

UIs may want to know total matching rows to display "1–20 of 540". In that case, an additional `COUNT(*)` query can run with the same conditions:

```sql
SELECT COUNT(*)
FROM person
WHERE status = :status;
```

Total pages can be computed as:

\[
\text{totalPages} = \left\lceil
\frac{\text{totalElements}}{\text{pageSize}}
\right\rceil
\]

Count queries can be costly on large tables, complex filters, or multi-table joins. They can also observe data at a different moment than the page query unless both statements run in the same snapshot transaction. If the UI only needs a "Load more" button, fetch `pageSize + 1` rows to detect whether more data exists without counting everything.

In reactive applications, compose the two publishers intentionally when both data and total count are required. Never call `block()` to wait for the count inside a WebFlux flow. If the count is unnecessary for the use case, omitting that query saves resources.

## 16. A Complete Search API Design

A list request can accept filters, sort, page size, and cursor/offset. Request DTOs should constrain supported options:

```java
public record PersonSearchRequest(
    String status,
    String sortBy,
    String direction,
    Integer pageSize,
    Long offset
) {}
```

The service normalizes inputs before invoking the data access layer:

```java
public Flux<PersonSummary> search(PersonSearchRequest request) {
    int size = normalizePageSize(request.pageSize());
    long offset = request.offset() == null
        ? 0
        : Math.max(0, request.offset());

    String sortColumn = switch (request.sortBy() == null ? "" : request.sortBy()) {
        case "firstName" -> "firstname";
        case "lastName" -> "lastname";
        case "createdAt" -> "created_at";
        default -> "id";
    };

    String direction = "asc".equalsIgnoreCase(request.direction())
        ? "ASC"
        : "DESC";

    String sql = """
        SELECT id, firstname, lastname, email
        FROM person
        WHERE status = :status
        ORDER BY %s %s, id ASC
        LIMIT :pageSize OFFSET :offset
        """.formatted(sortColumn, direction);

    return databaseClient.sql(sql)
        .bind("status", request.status())
        .bind("pageSize", size)
        .bind("offset", offset)
        .map((row, metadata) -> new PersonSummary(
            row.get("id", Long.class),
            row.get("firstname", String.class),
            row.get("lastname", String.class),
            row.get("email", String.class)
        ))
        .all();
}
```

In this example, `sortColumn` and `direction` take only allow-listed literals; filter and pagination values are bound. If `status` is optional, construct the condition accordingly and define behavior when no filter is supplied. Never omit tenant conditions or authorization scopes just because a request omits values.

If the application supports multiple database engines, separate pagination syntax and sort expressions by dialect. For simple entity queries, `R2dbcEntityTemplate` typically reduces manual SQL assembly.

## 17. Testing Dynamic Queries

Test the following cases:

- Projections return only needed columns and map aliases accurately.
- Disallowed columns are rejected.
- Unknown `sortBy` cannot inject SQL and is handled per API policy.
- Sort direction accepts only `ASC` or `DESC` per allow-list.
- Default and maximum page sizes are enforced.
- Page size 0, negative, or very large is handled properly.
- Ordering has a unique tie-breaker, avoiding arbitrary duplicates when rows share sort values.
- Large offsets perform acceptably or the API switches to cursors.
- Cursors return the exact next page, even when multiple rows share timestamps.
- Filters and user values are always bound as parameters.
- Indexes and execution plans are verified against realistic data.

Tests should run on the same database engine and driver intended for deployment, especially when relying on `LIMIT`, `OFFSET`, null ordering, or specific temporal types.

## 18. Workflow for Selecting Columns, Sorting, and Limiting

When implementing a dynamic query API, follow this sequence:

**Step 1 — Identify data to return.** List fields actually used by the screen or business logic and create the corresponding DTO/projection.

**Step 2 — Define allowed sort fields.** Create an allow-list mapping API names to entity properties or SQL column names.

**Step 3 — Normalize sort direction.** Accept only `ASC` or `DESC`; define a default direction and handle invalid values.

**Step 4 — Cap page size.** Set server-side default and maximum limits; validate offset or cursor.

**Step 5 — Choose pagination strategy.** Use offset for moderate datasets and jump-to-page needs; consider keyset for large datasets or continuous scrolling.

**Step 6 — Add deterministic ordering.** Append a unique key as a tie-breaker and define null rules.

**Step 7 — Design indexes.** Consider filter columns, sort columns, and index ordering; verify with execution plans.

**Step 8 — Test safety and performance.** Verify malicious inputs, projections, pagination, concurrent load, and behavior on a real database.

Column selection reduces unnecessary data; `Sort` or `ORDER BY` establishes ordering; `limit` or `LIMIT` keeps row counts bounded. Combining these three elements with allow-lists, bind parameters, deterministic ordering, and proper indexes makes dynamic queries in Spring Data R2DBC controllable, safe, and performance-predictable.
