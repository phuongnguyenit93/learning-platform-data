# SQL Server: Pagination, Data Types, and Generated Results

When using Spring Data R2DBC with Microsoft SQL Server, you need to understand three engine-specific aspects: pagination syntax, how SQL Server represents data types, and how to retrieve database-generated values after write operations. These differences directly affect SQL queries, entity mappings, converters, and R2DBC driver behavior.

Spring Data R2DBC provides abstractions such as repositories, `R2dbcEntityTemplate`, and `DatabaseClient`, but the final SQL must still match SQL Server and the driver in use, typically the R2DBC SQL Server driver (`r2dbc-mssql`). Versions of Spring Data, Spring Framework, and the driver can differ in dialect support, bind markers, codecs, and generated-value handling. Always verify your actual dependencies and run integration tests against your target SQL Server version.

## 1. SQL Server Connection and Dialect

An R2DBC URL for SQL Server typically looks like:

```yaml
spring:
  r2dbc:
    url: r2dbc:mssql://sqlserver-host:1433/orders
    username: ${DB_USER}
    password: ${DB_PASSWORD}
```

Hostname, database, credentials, encryption, and TLS options must be configured according to your deployment environment and driver version. Never hard-code passwords in source code or committed configuration files.

In multi-database applications, create the `ConnectionFactory`, `DatabaseClient`, `R2dbcEntityTemplate`, and `R2dbcTransactionManager` specifically for SQL Server. Do not mistakenly reuse a PostgreSQL/MySQL template just because the Java entities look similar. The SQL Server dialect is responsible for generating the SQL Server-specific SQL fragments supported by Spring Data, such as result limits and bind markers.

`DatabaseClient` supports named parameters in the form `:name`; Spring translates them into markers the dialect/driver understands. When calling the R2DBC SPI directly via `Connection.createStatement`, use the marker syntax documented by the SQL Server driver. Do not copy PostgreSQL's `$1` markers to SQL Server or assume every driver uses `?`.

## 2. Pagination With OFFSET and FETCH NEXT

SQL Server supports offset pagination via `ORDER BY ... OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` starting with SQL Server 2012. The query must include `ORDER BY`; `OFFSET/FETCH` cannot be used as an arbitrary limit without specifying a row order.

Example fetching the first page of the 20 latest orders:

```sql
SELECT id, order_number, status, created_at
FROM dbo.purchase_order
WHERE tenant_id = @tenantId
ORDER BY created_at DESC, id DESC
OFFSET 0 ROWS
FETCH NEXT 20 ROWS ONLY;
```

`created_at DESC` sorts by newest first. `id DESC` acts as a tie-breaker so the ordering remains deterministic when multiple orders share the same timestamp. If you sort only by `created_at`, rows with identical timestamps can shift positions across executions.

Example for the third page of 20 rows each:

```sql
SELECT id, order_number, status, created_at
FROM dbo.purchase_order
WHERE tenant_id = @tenantId
ORDER BY created_at DESC, id DESC
OFFSET 40 ROWS
FETCH NEXT 20 ROWS ONLY;
```

`OFFSET` is the number of rows skipped before returning results. `FETCH NEXT` is the maximum number of rows for the page. Validate that page size is greater than 0 and offset is non-negative before execution.

### 2.1 Safe Offset Calculation

With a 0-based page number, the formula is:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

Do not compute it using `int` if data can span many pages. Use `long` and guard against overflow:

```java
long offset = Math.multiplyExact((long) pageNumber, pageSize);

if (pageNumber < 0 || pageSize <= 0) {
    throw new IllegalArgumentException("Invalid page request");
}
```

In production code, validate inputs before computing the offset to reject negative inputs; `Math.multiplyExact` catches multiplication exceeding `long` bounds.

### 2.2 Using R2dbcEntityTemplate

When querying entities and leveraging mapping metadata, you can build a `Query` with `Sort`, `offset`, and `limit`:

```java
public Flux<PurchaseOrder> findOrderPage(
        UUID tenantId, int pageNumber, int pageSize) {

    if (pageNumber < 0 || pageSize <= 0) {
        return Flux.error(new IllegalArgumentException("Invalid page request"));
    }

    long offset = Math.multiplyExact((long) pageNumber, pageSize);

    Query query = Query.query(
            Criteria.where("tenantId").is(tenantId))
        .sort(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")))
        .offset(offset)
        .limit(pageSize);

    return ordersTemplate.select(query, PurchaseOrder.class);
}
```

Property names in `Criteria` and `Sort` are typically mapped by Spring Data to column names based on entity metadata. For example, `createdAt` maps to `created_at` when configured by the naming strategy or `@Column`. Inspect the SQL generated on your Spring Data version and confirm the SQL Server dialect produces valid limit/offset syntax.

`R2dbcEntityTemplate.select(...)` returns a `Flux`, even when a page limits row count. If you need a container holding both page items and total record count, the service can execute an additional count query and combine the results into a dedicated DTO.

### 2.3 Using DatabaseClient With Explicit SQL

When SQL Server-specific queries or projections are needed, `DatabaseClient` allows writing SQL directly:

```java
Flux<OrderSummary> findPage(
        UUID tenantId, long offset, int pageSize) {

    return databaseClient.sql("""
            SELECT id, order_number, status, created_at
            FROM dbo.purchase_order
            WHERE tenant_id = :tenantId
            ORDER BY created_at DESC, id DESC
            OFFSET :offset ROWS
            FETCH NEXT :pageSize ROWS ONLY
            """)
        .bind("tenantId", tenantId)
        .bind("offset", offset)
        .bind("pageSize", pageSize)
        .map((row, metadata) -> new OrderSummary(
            row.get("id", Long.class),
            row.get("order_number", String.class),
            row.get("status", String.class),
            row.get("created_at", LocalDateTime.class)))
        .all();
}
```

This snippet demonstrates Spring `DatabaseClient` named parameters. `offset` and `pageSize` are bound as values, while table names, column names, and sort direction are fixed in SQL. Before executing, the service must still validate that `offset >= 0` and `pageSize` stays within application-allowed bounds.

If constructing `DatabaseClient` manually from a `ConnectionFactory`, ensure the dialect is configured for SQL Server. When binding numeric or temporal types, the Java type must be compatible with the driver codec and column type.

## 3. Why Must ORDER BY Be Deterministic?

Offset pagination depends on row positions within an ordered result set. If the sort order is not unique, the database is free to return tied rows in different orders on consecutive runs.

Unstable example:

```sql
SELECT id, created_at
FROM dbo.purchase_order
ORDER BY created_at DESC
OFFSET 20 ROWS FETCH NEXT 20 ROWS ONLY;
```

If multiple rows share the same `created_at`, a row can appear on an earlier page during the first request and on a later page during the next request. Add a unique key as a tie-breaker:

```sql
ORDER BY created_at DESC, id DESC
```

A deterministic sort makes pagination repeatable when data is static. It does not prevent rows from being inserted or deleted between requests. When data changes, offsets of subsequent pages can shift, resulting in duplicate or skipped rows.

## 4. TOP and ROW_NUMBER in SQL Server

`TOP` is well-suited when you only need the first N rows in a given order:

```sql
SELECT TOP (20) id, order_number, created_at
FROM dbo.purchase_order
WHERE tenant_id = @tenantId
ORDER BY created_at DESC, id DESC;
```

`TOP` does not natively handle multi-page offsets. For the first page, `TOP` is simple. For subsequent pages, use `OFFSET/FETCH` or keyset pagination.

On older systems or when computing ranks inside a CTE, you can use `ROW_NUMBER()`:

```sql
WITH ranked_orders AS (
    SELECT
        id,
        order_number,
        created_at,
        ROW_NUMBER() OVER (
            ORDER BY created_at DESC, id DESC
        ) AS row_number
    FROM dbo.purchase_order
    WHERE tenant_id = @tenantId
)
SELECT id, order_number, created_at
FROM ranked_orders
WHERE row_number BETWEEN @firstRow AND @lastRow
ORDER BY row_number;
```

`ROW_NUMBER()` numbers rows according to the `OVER` clause. Use the same deterministic ordering in the window and the outer query. A CTE does not guarantee final output order if the outer `SELECT` lacks an `ORDER BY`.

## 5. Keyset Pagination for Large Datasets

Offset pagination must skip preceding rows. When offsets grow large, the database may scan and sort a substantial number of rows before returning a page, even if the caller only wants a few dozen rows. Keyset pagination (seek pagination) uses values from the last row of the previous page to seek directly to the next slice, which is typically much more efficient on large tables with a matching index.

Suppose results are sorted descending by `created_at` and `id`. The next page uses the pair of values from the previous page's final row:

```sql
SELECT TOP (@pageSize)
    id, order_number, created_at
FROM dbo.purchase_order
WHERE tenant_id = @tenantId
  AND (
       created_at < @lastCreatedAt
       OR (created_at = @lastCreatedAt AND id < @lastId)
  )
ORDER BY created_at DESC, id DESC;
```

The predicate performs a lexicographical comparison on `(created_at, id)`. For descending order, the next page contains rows with an earlier timestamp, or the same timestamp and a smaller ID.

The first page has no cursor and uses a query without `lastCreatedAt/lastId` predicates. You can package the cursor in the response, such as `nextCreatedAt` and `nextId`, and have the client pass it back on the next request.

### 5.1 Requirements for Keyset Pagination to Work Properly

- The sort order must be deterministic and end with a unique column or column group.
- Cursor values must come from the actual last row returned.
- Seek predicates must match each column's `ASC`/`DESC` direction.
- Nullable columns must be handled explicitly because comparisons with `NULL` do not evaluate to standard true/false.
- Indexes should support filter and sort columns, e.g., `(tenant_id, created_at DESC, id DESC)` if suited to the workload.
- Cursors should be validated and optionally signed/encoded if clients must not alter query boundaries.

Keyset pagination is unsuitable if users need to jump directly to arbitrary page numbers without a cursor. It excels for feeds, activity histories, latest-items lists, and infinite scrolling.

### 5.2 Handling Nullable Sort Columns

If `created_at` can be null, `created_at < :lastCreatedAt` excludes null rows. Choose one of these strategies:

- Make the sort column `NOT NULL` if business rules permit.
- Add a secondary sort key indicating null/non-null grouping and include it in the cursor.
- Normalize the sort expression using `CASE` or a sentinel value, using the identical expression in both `ORDER BY` and the seek predicate.

Do not ignore null behavior, as doing so can cause some rows to never appear on subsequent pages.

## 6. Total Row Counts and Page Objects

A paginated view often needs both the current page's data and the total matching row count. SQL Server provides `COUNT_BIG(*)` to count totals exceeding `int` limits:

```sql
SELECT COUNT_BIG(*)
FROM dbo.purchase_order
WHERE tenant_id = @tenantId
  AND status = @status;
```

`COUNT(*)` returns `int` in SQL Server; `COUNT_BIG(*)` returns `bigint`. For large tables or totals that may exceed `int` range, prefer `COUNT_BIG` and map to `Long`.

A straightforward pattern runs two queries:

1. Page query with `ORDER BY/OFFSET/FETCH`.
2. Count query with the same `WHERE` clause.

Then combine the results into a dedicated DTO such as `PageResult<T>` containing `items`, `pageSize`, `offset`, and `totalElements`. Reactive repositories return `Flux`/`Mono`; do not force a reactive API to return Spring's blocking-style `Page<T>` if doing so tempts code to block for the count.

You can combine the two publishers with `Mono.zip` when each query produces a single aggregated result:

```java
Mono<PageResult<OrderSummary>> loadPage(
        UUID tenantId, long offset, int pageSize) {

    Mono<List<OrderSummary>> items = findPage(tenantId, offset, pageSize)
        .collectList();

    Mono<Long> total = countOrders(tenantId);

    return Mono.zip(items, total)
        .map(tuple -> new PageResult<>(
            tuple.getT1(), offset, pageSize, tuple.getT2()));
}
```

`PageResult` and `countOrders` are application abstractions. If the two queries execute independently under `READ_COMMITTED`, data may change between fetching items and fetching the count, causing `items` and `totalElements` to reflect different snapshots. If snapshot consistency is required, configure appropriate transaction isolation and database settings, or accept approximate/separately updated counts.

A single query can use `COUNT_BIG(*) OVER()` to return the total alongside each page row. However, if the page is empty there are no rows to carry `total_count`; therefore handle out-of-range pages carefully. Window counts also do not replace deterministic ordering.

## 7. Numeric Types in SQL Server

SQL Server offers several numeric types with different ranges and precisions. The table below summarizes common Java pairings; specific codecs must be confirmed against your R2DBC driver version:

| SQL Server Type | Common Java Type | Notes |
|---|---|---|
| `bit` | `Boolean` | Can hold `NULL` if nullable; use wrapper instead of primitive when nulls are possible. |
| `tinyint` | `Short` or `Integer` | SQL Server `tinyint` is unsigned 0–255; signed Java `byte` cannot represent the full range. Check driver codec. |
| `smallint` | `Short` | Signed 16-bit integer. |
| `int` | `Integer` | Signed 32-bit integer. |
| `bigint` | `Long` | Signed 64-bit integer. |
| `decimal(p,s)` / `numeric(p,s)` | `BigDecimal` | SQL Server supports up to precision 38; choose scale per business rules. |
| `smallmoney` / `money` | `BigDecimal` | Fixed scale; for business currency, `decimal` is usually preferred. |
| `real` | `Float` | Single-precision floating point. |
| `float` | `Double` | Precision depends on definition; do not use for currency requiring exact decimal arithmetic. |

### 7.1 Decimal and Currency

`decimal(p,s)`/`numeric(p,s)` fits values needing exact decimal precision. SQL Server allows precision up to 38 digits. Example:

```sql
amount DECIMAL(19, 4) NOT NULL
```

Here `19` is total digits and `4` is digits after the decimal point. Java `BigDecimal` preserves decimal values, though the application still needs consistent scale, rounding modes, and business limits before writing.

Do not use `float`/`double` for currency or balances. Nor should you pick `money` solely because of its name; `decimal(p,s)` generally provides clearer control over precision/scale and aligns better across database engines.

### 7.2 NULL and Java Primitives

If a `bit`, `int`, `bigint`, or `decimal` column allows `NULL`, use `Boolean`, `Integer`, `Long`, `BigDecimal`, or the corresponding reference type. Java primitives cannot represent null. Never silently turn null into 0 or false if business logic distinguishes "unknown" from zero.

## 8. Unicode Strings and Text Types

SQL Server distinguishes non-Unicode and Unicode string types:

| SQL Type | Meaning | Guidance |
|---|---|---|
| `char(n)` | Fixed-length, non-Unicode string | Short codes of fixed length when appropriate. |
| `varchar(n)` | Variable-length, non-Unicode per code page/collation | Use when data and collation allow. |
| `nchar(n)` | Fixed-length Unicode string | Fixed-length Unicode data. |
| `nvarchar(n)` | Variable-length Unicode string | Generally suitable for names, addresses, and multilingual text. |
| `varchar(max)` | Long non-Unicode text | Use for long content when small limits do not apply. |
| `nvarchar(max)` | Long Unicode text | Use for large Unicode content. |

In Java, these map to `String`. For Vietnamese or multilingual text, `nvarchar`/`nvarchar(max)` is usually the safe choice unless there is a clear reason to use `varchar` with a matching UTF-8/appropriate collation and code page.

SQL Server collations affect comparison, sorting, case sensitivity, and accent sensitivity. A string comparison query can return different results if databases or columns use different collations. Do not assume Java `String.equals()` and SQL comparisons share identical semantics.

For `nvarchar(n)`, `n` specifies the number of byte pairs/code units under SQL Server rules, not strictly display character count for supplementary Unicode characters. Choose column lengths from business limits and test real data. For `varchar(max)`/`nvarchar(max)`, consider payload size, memory footprint, and indexing impacts.

## 9. UUID and Binary Data

SQL Server uses `uniqueidentifier` to store GUIDs. In Java, `UUID` is the natural representation:

```sql
id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY
```

The R2DBC driver must provide a codec between `uniqueidentifier` and `UUID`. If using a driver/version without direct support, use a converter or consistent string representation. Do not manually reorder UUID bytes unless you understand the exact byte format used by the driver and database.

`binary(n)`, `varbinary(n)`, and `varbinary(max)` typically map to `byte[]` or a driver-provided binary type. Large binary payloads may require streaming or external storage rather than materializing into a single byte array.

SQL Server `rowversion` is an 8-byte binary value automatically generated on every insert or update of a row. Its legacy alias `timestamp` is a synonym for `rowversion`; it is **not a date or time**. You can read it as binary data (`byte[]` or a driver-supported type) and use it as a concurrency token if code respects its semantics.

## 10. Date and Time: date, time, datetime2, and datetimeoffset

SQL Server provides multiple temporal types; choosing the wrong one can lose precision or timezone information:

| SQL Server Type | Meaning | Common Java Type |
|---|---|---|
| `date` | Calendar date without time | `LocalDate` |
| `time(p)` | Time of day, precision 0–7 | `LocalTime` |
| `datetime2(p)` | Date and time without offset | `LocalDateTime` |
| `datetimeoffset(p)` | Date and time with UTC offset | `OffsetDateTime` |
| `datetime` | Legacy date/time type, lower precision | `LocalDateTime` |
| `smalldatetime` | Date/time with 1-minute precision | `LocalDateTime` |

`datetime2` is generally preferred over `datetime` for new temporal columns due to its wider date range and higher precision. `datetime` rounds to increments of approximately 1/300 second, meaning values can be rounded to nearest millisecond fractions. `datetime2(7)` supports precision up to 100 nanoseconds per SQL Server specification.

`datetime2` does not store a timezone. If your application uses `Instant`, standardize on storing UTC and convert explicitly via `OffsetDateTime`/`LocalDateTime` as required by the driver. `datetimeoffset` stores date/time plus an offset, fitting cases where preserving the original offset at write time matters; it does not store IANA zone IDs such as `Asia/Ho_Chi_Minh` or regional DST rules.

Schema example:

```sql
CREATE TABLE dbo.audit_entry (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    occurred_at DATETIMEOFFSET(7) NOT NULL,
    business_date DATE NOT NULL,
    local_time TIME(7) NULL
);
```

The Java entity can use `OffsetDateTime`, `LocalDate`, and `LocalTime` respectively. Exact codec support should still be verified with your R2DBC SQL Server driver. Do not rely on implicit conversions among `Instant`, `LocalDateTime`, and `OffsetDateTime` without an explicit timezone convention.

## 11. SQL Server-Specific Types

Other types to be aware of:

| Type | Purpose | Mapping Notes |
|---|---|---|
| `xml` | Store XML documents | May require `String`, `Clob`, or a custom codec depending on driver. |
| `sql_variant` | Store values of varied SQL types | Hard to map to a fixed Java type; avoid in domain models if possible. |
| `geometry` / `geography` | Spatial data | Typically requires corresponding spatial libraries/codecs. |
| `hierarchyid` | Hierarchical paths | Vendor-specific type requiring custom mapping. |
| `table`-valued parameter | Pass tabular sets as procedure parameters | Support depends on driver and API; not equivalent to binding a regular `List`. |
| `rowversion` | Auto-generated binary version token | Not a wall-clock timestamp; never write values into it manually. |

For specialized types, check whether the driver provides a Java type or codec. If not, consider converting to simpler types, using SQL projections, or isolating vendor-specific types in a persistence adapter rather than coupling your domain model directly to driver classes.

## 12. IDENTITY: Auto-Incrementing Keys in SQL Server

SQL Server typically creates auto-incrementing numeric keys with `IDENTITY(seed, increment)`:

```sql
CREATE TABLE dbo.customer (
    id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    email NVARCHAR(320) NOT NULL,
    display_name NVARCHAR(200) NOT NULL
);
```

On insert, the application omits the `id` column and the database generates the value:

```sql
INSERT INTO dbo.customer (email, display_name)
VALUES (N'an@example.com', N'An');
```

In Spring Data R2DBC, the entity can be declared as:

```java
@Table("customer")
public class Customer {
    @Id
    private Long id;

    private String email;
    private String displayName;
}
```

When an entity is detected as new and `id` has no value, the insert can request that the database generate the ID. Always use the entity emitted by `save`:

```java
return customerRepository.save(customer)
    .map(saved -> saved.getId());
```

This is especially critical for immutable entities: `save` may return a brand-new instance carrying the generated ID. Never assume the input object is mutated in place.

`IDENTITY` IDs are not guaranteed to be gapless. Rollbacks, failed inserts, identity caching, or concurrent operations can create gaps. Never use auto-incrementing IDs to infer exact record counts or strict chronological ordering.

## 13. Retrieving Generated Values With OUTPUT INSERTED

SQL Server supports `OUTPUT INSERTED.<column>` to return row values after an `INSERT` or `UPDATE`:

```sql
INSERT INTO dbo.customer (email, display_name)
OUTPUT INSERTED.id, INSERTED.created_at
VALUES (@P0, @P1);
```

`OUTPUT INSERTED.id` returns the `IDENTITY`-generated ID. You can also request columns populated by default constraints or computed columns if the database and driver support returning them.

With `DatabaseClient`, write explicit SQL and map the returned row:

```java
Mono<CreatedCustomer> insertCustomer(String email, String name) {
    return databaseClient.sql("""
            INSERT INTO dbo.customer (email, display_name)
            OUTPUT INSERTED.id, INSERTED.created_at
            VALUES (:email, :displayName)
            """)
        .bind("email", email)
        .bind("displayName", name)
        .map((row, metadata) -> new CreatedCustomer(
            row.get("id", Long.class),
            row.get("created_at", LocalDateTime.class)))
        .one();
}
```

This example shows Spring `DatabaseClient` named parameters; do not hard-code `@P0`/`@P1` when using named parameters. The framework/dialect translates placeholders into the form needed by the driver. When writing SQL directly at the SPI layer, use markers matching your R2DBC SQL Server driver version.

### 13.1 OUTPUT With Triggers

SQL Server has an important restriction: `OUTPUT` without `INTO` cannot be used on a table that has an enabled trigger for the corresponding DML action. When a table has a trigger, you may need to capture `OUTPUT` into a table variable and select from it afterward:

```sql
DECLARE @inserted TABLE (
    id BIGINT,
    created_at DATETIME2(7)
);

INSERT INTO dbo.customer (email, display_name)
OUTPUT INSERTED.id, INSERTED.created_at
INTO @inserted (id, created_at)
VALUES (@P0, @P1);

SELECT id, created_at FROM @inserted;
```

Additionally, values in `OUTPUT INSERTED` reflect the row state after DML but before AFTER triggers run. If a trigger further modifies the row and the application needs the final post-trigger values, re-query the row within the same transaction or design around the trigger behavior.

### 13.2 Generated Values via Spring Data and the Driver

`R2dbcEntityTemplate` and repositories can use the dialect/driver's generated-value capability to retrieve IDs on insert. Which columns are returned automatically and how it is implemented depend on the Spring Data R2DBC and SQL Server driver versions.

When you need generated columns beyond the ID, or when the driver/dialect does not return the expected columns, check `Statement.returnGeneratedValues(...)` support and explicit SQL Server `OUTPUT`. Do not assume the generated-values API behaves identically to PostgreSQL `RETURNING`; the underlying syntax differs.

## 14. SCOPE_IDENTITY and Other ID Retrieval Approaches

A legacy approach to retrieving an identity value within the same SQL scope is:

```sql
INSERT INTO dbo.customer (email, display_name)
VALUES (@P0, @P1);

SELECT CAST(SCOPE_IDENTITY() AS BIGINT) AS id;
```

`SCOPE_IDENTITY()` returns the last identity generated within the same scope. It is safer than `@@IDENTITY` when triggers insert into other identity tables, because `@@IDENTITY` can return a trigger-generated value. `IDENT_CURRENT('table')` is not scoped to the current session and can return IDs generated by other sessions, so never use it to obtain the ID of a just-executed insert.

With R2DBC, if using `SCOPE_IDENTITY()`, both statements must execute on the exact same connection and scope. Use a statement batch or an explicitly managed transaction/connection; never dispatch two independent queries that acquire separate pooled connections and expect them to share scope.

`OUTPUT INSERTED.id` usually expresses intent more clearly because it returns the generated value directly from the DML statement. However, triggers and driver support affect usage as noted above.

## 15. SEQUENCE and Default Constraints

SQL Server also supports table-independent sequences:

```sql
CREATE SEQUENCE dbo.order_number_seq
    AS BIGINT
    START WITH 1000
    INCREMENT BY 1;

CREATE TABLE dbo.purchase_order (
    id BIGINT NOT NULL PRIMARY KEY
        DEFAULT NEXT VALUE FOR dbo.order_number_seq,
    order_number NVARCHAR(40) NOT NULL
);
```

The application can omit `id` on insert so the default constraint pulls the next value from the sequence. Alternatively, it can call `NEXT VALUE FOR` beforehand if business logic needs the number prior to inserting the row.

Sequences do not roll back issued values on transaction rollback. If a transaction rolls back, already-drawn sequence values remain consumed, creating gaps. Just as with identity, never assume gapless sequences.

Sequences fit scenarios where multiple tables share one numbering sequence or when you want to decouple number generation from a specific table. `IDENTITY` is simpler when each table maintains its own auto-incrementing key.

## 16. DEFAULT, Computed Columns, and Database-Generated Values

Beyond identity, SQL Server can compute values via default constraints, computed columns, or triggers:

```sql
CREATE TABLE dbo.purchase_order (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    order_number NVARCHAR(40) NOT NULL,
    created_at DATETIME2(7) NOT NULL
        CONSTRAINT DF_purchase_order_created_at
        DEFAULT SYSUTCDATETIME(),
    normalized_number AS UPPER(order_number) PERSISTED
);
```

- `created_at` is assigned by the default constraint when an insert omits the column.
- `normalized_number` is a computed column calculated by the database from `order_number`.
- `id` is generated from identity.

If the application must return these values immediately after insert, use generated values/`OUTPUT` where supported by the driver and dialect. Otherwise, re-query by the returned key within the same transaction. Do not recompute `normalized_number` in Java assuming it always matches SQL Server's collation and string functions.

`SYSUTCDATETIME()` returns UTC time as `datetime2`; if storing offsets, design the schema and conversions explicitly. `GETDATE()` returns the SQL Server host's local time as `datetime`; never mix both functions if the system needs a consistent time convention.

## 17. rowversion and Optimistic Concurrency

SQL Server `rowversion` is a database-wide auto-incrementing binary token updated whenever a row is inserted or modified. It detects whether data changed since it was last read:

```sql
CREATE TABLE dbo.inventory (
    product_id BIGINT PRIMARY KEY,
    available INT NOT NULL,
    row_version ROWVERSION NOT NULL
);
```

On read, the application retains `row_version`. On update, include it in the predicate:

```sql
UPDATE dbo.inventory
SET available = :available
OUTPUT INSERTED.row_version
WHERE product_id = :productId
  AND row_version = :expectedVersion;
```

If zero rows are updated, the version changed or the row no longer matched. The service can return a conflict, reload current state, or retry per business rules.

`rowversion` is not a wall-clock time and cannot display "when something was updated." Nor is it a per-row version counter starting at 1; it is a binary value managed at the database level. Never assign a value to a `rowversion` column on insert or update.

Spring Data `@Version` is typically used with properties that Spring Data can increment and compare according to supported mappings. Do not assume mapping `byte[]` directly to SQL Server `rowversion` works out-of-the-box as `@Version` across all versions. If you want native `rowversion`, verify driver/mapping support or write explicit SQL with `row_version = :expectedVersion` and check `rowsUpdated()`.

## 18. Entity Mapping and Generated IDs in Spring Data R2DBC

Example entity using `IDENTITY`:

```java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    @Column("created_at")
    private LocalDateTime createdAt;
}
```

When creating a new entity, keep `id` in a new state per Spring Data's newness rules. After saving, read the ID from the returned entity:

```java
return orderRepository.save(newOrder)
    .flatMap(saved -> orderLineRepository.saveAll(
            createLines(saved.getId(), request.lines()))
        .thenReturn(saved));
```

Do not discard the entity returned by `save`, especially for immutable entities or database-generated IDs. Spring Data may instantiate a new object holding the ID, version, or mapped fields.

If using application-assigned IDs, newness detection rules differ. You may need `Persistable` or a suitable newness strategy so Spring Data chooses insert rather than update. Verify the entity newness rules of your Spring Data Relational version.

## 19. SQL Server Identifiers, Schemas, and Keywords

SQL Server defaults to the `dbo` schema unless another schema is specified. You can qualify table names explicitly:

```sql
SELECT id, order_number
FROM dbo.purchase_order;
```

Table or column names matching keywords or containing special characters may require `[...]` delimiters:

```sql
SELECT [order], [status]
FROM dbo.[order];
```

However, avoid naming tables or columns after keywords like `order`, `user`, or `key` whenever possible. Clear domain names like `purchase_order` minimize quoting needs.

With Spring Data, `@Table` and `@Column` along with the dialect handle identifier mapping. With hand-written SQL in `DatabaseClient`, specify the proper schema and delimiters yourself. Never concatenate client-supplied identifiers into SQL; for dynamic sort fields, use an allowlist of permitted columns.

## 20. SQL Server R2DBC Bind Markers and Parameter Types

With Spring `DatabaseClient`, write named parameters:

```java
databaseClient.sql("SELECT id FROM dbo.customer WHERE email = :email")
    .bind("email", email)
    .map((row, metadata) -> row.get("id", Long.class))
    .one();
```

Spring translates named parameters into markers matching the dialect/driver. When invoking the R2DBC SPI directly, the SQL Server driver has its own marker conventions; follow your driver version's documentation. Do not copy `$1` from PostgreSQL or `?` from other drivers.

Java types passed to `bind` must match driver codecs—for example, `UUID` for `uniqueidentifier`, `BigDecimal` for `decimal`, `OffsetDateTime` for `datetimeoffset`, and `LocalDateTime` for `datetime2` when supported by the driver. For nulls, call `bindNull(name, JavaType.class)` to provide an explicit type.

Table and column names cannot be bound as parameter values. If a query needs dynamic `ORDER BY`, map the column from an allowlist:

```java
String orderColumn = switch (sortField) {
    case "createdAt" -> "created_at";
    case "orderNumber" -> "order_number";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};
```

Then interpolate only the code-selected `orderColumn` into fixed SQL. Filter values, offsets, and page sizes must still be bound.

## 21. Indexes Supporting Pagination

A paginated query can be slow if the database must sort many rows or skip a large offset. Indexes should align with filter predicates and sort order:

```sql
CREATE INDEX IX_purchase_order_tenant_created_id
ON dbo.purchase_order (tenant_id, created_at DESC, id DESC)
INCLUDE (order_number, status);
```

This index illustrates filtering by `tenant_id` and sorting by `created_at DESC, id DESC`. `INCLUDE` can let the query fetch extra columns without table lookups per row, at the cost of larger index size and higher write overhead. Add included columns only when execution plans and workloads justify them.

With keyset pagination, an index ordered like the seek columns lets the database locate the starting point efficiently. With offset pagination, indexes still assist filtering and sorting, though the engine may still read through skipped rows.

Inspect execution plans, logical reads, and query durations on realistic data. Do not create indexes from a single SQL example without considering write workloads and other queries.

## 22. Version and Driver Support Checklist

When deploying SQL Server with Spring Data R2DBC, verify the following on actual versions:

- Spring Data Relational provides the SQL Server dialect and supports the operations used.
- The R2DBC SQL Server driver supports required Java types, including `UUID`, `BigDecimal`, temporal types, and binaries.
- `R2dbcEntityTemplate` generates `OFFSET/FETCH` pagination compatible with your SQL Server version.
- `DatabaseClient` translates named parameters into appropriate bind markers.
- The driver supports generated values as expected by Spring Data, or the application explicitly uses `OUTPUT INSERTED`.
- Tables with triggers do not break `OUTPUT` usage.
- `rowversion` mapping and optimistic concurrency work as expected or use explicit SQL.
- `datetime2`/`datetimeoffset` read and write with expected precision and timezone semantics.

Do not treat a test passing on H2 as proof that SQL Server behaves the same way. SQL Server has its own syntax, data types, and generated-value behavior; integration tests must run on SQL Server or an environment matching production.

## 23. Testing Pagination and Generated Values

Verify these scenarios:

| Scenario | What to Confirm |
|---|---|
| First page | Returns exact row count, right order, and no rows outside tenant/filter. |
| Subsequent pages | No duplicate rows when data is unchanged. |
| Multiple rows with identical timestamps | ID tie-breaker yields deterministic order. |
| Large offset | Measure performance and compare against keyset pagination. |
| Invalid page size/offset | Service rejects inputs before running SQL. |
| Large total row counts | `COUNT_BIG(*)` maps properly to `Long`. |
| Identity insert | Returned entity carries the generated ID. |
| Default/computed columns | Values are returned or re-queried accurately. |
| Tables with triggers | `OUTPUT` does not fail; post-trigger values are handled properly if needed. |
| rowversion | Updates with stale versions fail or conflict as expected. |
| Unicode | Vietnamese names and supplementary characters round-trip without data loss. |
| datetimeoffset | Offsets are preserved according to application conventions. |
| decimal | Precision, scale, and rounding match business rules. |

For generated values, test both committed inserts and rolled-back inserts. Identity and sequences can leave gaps after rollbacks; tests must not assert contiguous IDs.

## 24. Process for Choosing Pagination and Generated Value Strategies

When building SQL Server queries, decide in this order:

1. Does the feature require jumping to arbitrary page numbers, or only advancing from the previous page?
2. For arbitrary pages, use deterministic `ORDER BY` with `OFFSET/FETCH`; for large sequential datasets, consider keyset pagination.
3. Enforce a maximum page size and calculate offset using `long` with overflow checks.
4. Choose `R2dbcEntityTemplate` when entity mapping fits; choose `DatabaseClient` for custom SQL or projections.
5. Select column types based on value range, precision, Unicode needs, nullability, and temporal semantics.
6. For auto-incrementing IDs, use `IDENTITY` or `SEQUENCE` as needed; never assume gapless ID sequences.
7. Use dialect/driver generated-value support or `OUTPUT INSERTED` to retrieve IDs, defaults, and computed values.
8. Handle `OUTPUT` restrictions on tables with triggers and remember output reflects state prior to AFTER triggers.
9. For optimistic concurrency, distinguish numeric Spring Data `@Version` from binary SQL Server `rowversion`.
10. Test against the real SQL Server and R2DBC driver, covering data types, paging, triggers, and transactions.

SQL Server provides `OFFSET/FETCH`, `TOP`, and `ROW_NUMBER` for pagination; for large datasets, keyset pagination avoids the cost of skipping rows. `datetime2`, `datetimeoffset`, `nvarchar`, `uniqueidentifier`, `decimal`, and `rowversion` must be mapped according to their true semantics rather than Java type names alone. For generated values, `IDENTITY`, `SEQUENCE`, default constraints, and `OUTPUT INSERTED` are key mechanisms; Spring Data R2DBC integrates generated values via the dialect and driver, which must be verified per version. Writing deterministic queries, choosing clear column types, and testing against real SQL Server keeps pagination and persistence predictable.
