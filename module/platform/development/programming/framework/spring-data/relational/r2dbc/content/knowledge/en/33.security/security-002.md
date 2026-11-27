# Controlling Dynamic Table Names, Column Names, and Sort Directions

In Spring Data Relational R2DBC applications, a SQL query typically combines two kinds of information: statement structure and data values. Values such as email, status, or date ranges can be passed via bind parameters. Table names, column names, `ORDER BY` expressions, and `ASC`/`DESC` keywords are structural components of SQL; they cannot be safely replaced by ordinary bind parameters.

When an API lets clients choose a sort field, table, filter column, or schema, the application must translate that choice through a server-controlled allowlist. Only predefined identifiers and SQL fragments may be included in the statement. Data values continue to be bound separately.

This lesson explains how to control dynamic identifiers in R2DBC, how to build allowlists for tables, columns, and sort directions, how to use Spring Data's `Sort` and `Criteria`, how to assemble dynamic SQL with `DatabaseClient`, how to handle multi-sort, filters, pagination, and tenant routing, and how to test against SQL injection.

## 1. Distinguishing Identifiers from Values in SQL

SQL can contain several types of components:

| Component | Example | Safe handling |
| --- | --- | --- |
| Data value | email, status, date, amount | Bind parameter. |
| Table name | products, orders | Select from a server-side allowlist. |
| Schema name | app, reporting | Select from an allowlist; never accept raw input. |
| Column name | created_at, price | Map API key to a predefined identifier. |
| Sort direction | ASC, DESC | Convert to an enum or fixed choice. |
| Sort expression | lower(name), created_at | Select the entire expression from an allowlist. |
| Operator | =, LIKE, IN, >= | Map from an enum to a fixed operator. |
| Function/collation name | lower, unaccent, collation name | Select from an allowed list. |

Example SQL with bind parameters:

~~~sql
SELECT id, name, price
FROM products
WHERE category_id = :categoryId
  AND status = :status
ORDER BY created_at DESC
LIMIT :limit OFFSET :offset;
~~~

In this example:

- `categoryId` and `status` are data values so they can be bound.
- `limit` and `offset` are numeric values so they can be bound if the driver/database supports those positions.
- `products` is a fixed table name.
- `created_at` is a fixed column name.
- `DESC` is a fixed SQL keyword.

Bind parameters protect data values from being interpreted as SQL syntax. They do not turn a string into a table name or column name.

## 2. Why Can't Table Names or Column Names Be Bound?

Prepared statements parse the SQL structure first, then accept values for bind positions. A bind marker represents a literal/value in an expression, not an identifier or SQL keyword.

Incorrect example:

~~~java
databaseClient.sql("""
    SELECT id, name
    FROM :tableName
    WHERE status = :status
    ORDER BY :sortColumn :direction
    """)
    .bind("tableName", tableName)
    .bind("status", status)
    .bind("sortColumn", sortColumn)
    .bind("direction", direction);
~~~

Bind markers in table, column, and direction positions do not work as intended. The database may raise a syntax error, or treat a marker in `ORDER BY` as a constant value instead of a column name. It does not automatically turn a bound value into an identifier.

Some database engines allow `ORDER BY` on a literal or parameter expression. In that case, every row may be sorted by the same constant value rather than by the column the client selected.

### Rules to remember

- Bind data.
- Allowlist identifiers.
- Allowlist SQL fragments.
- Never concatenate raw input into SQL.
- Never use escaping instead of an allowlist.

Prepared statements and bind parameters remain the right choice for values; only the dynamic structure requires a separate control mechanism.

## 3. SQL Injection via ORDER BY

An endpoint might let clients send:

~~~text
GET /api/products?sort=createdAt&direction=DESC
~~~

If code concatenates parameters directly into SQL:

~~~java
String sql = "SELECT id, name FROM products ORDER BY "
    + request.sort()
    + " "
    + request.direction();
~~~

a client can send strings that are not valid column names or sort directions. Depending on how the SQL is built, that input can alter the statement structure, cause errors, or create a SQL injection vulnerability.

Do not try to solve this merely by stripping semicolons, spaces, or quote characters. SQL has many syntaxes and ways of representing identifiers; character blacklists are routinely incomplete. The safe approach is to prevent input from ever becoming a SQL fragment.

## 4. Creating an Allowlist for Sort Columns

Suppose an API supports sorting products by name, price, or creation time. Use an enum to represent the allowed choices:

~~~java
public enum ProductSortKey {
    NAME,
    PRICE,
    CREATED_AT
}
~~~

Map the enum to a server-controlled Java property or SQL expression:

~~~java
public enum ProductSortKey {
    NAME("name"),
    PRICE("price"),
    CREATED_AT("createdAt");

    private final String property;

    ProductSortKey(String property) {
        this.property = property;
    }

    public String property() {
        return property;
    }
}
~~~

When using Spring Data `Sort` with an entity `ProductEntity`, the property is typically the mapped Java property name, such as `createdAt`, rather than the physical column name `created_at`:

~~~java
Sort.Direction direction = Sort.Direction.DESC;

Sort sort = Sort.by(direction, ProductSortKey.CREATED_AT.property());
~~~

Spring Data mapping translates the property into the corresponding column using entity metadata. This preserves the separation between Java property names and database column names.

Never pass a client-sent sort key directly into `Sort.by` if the request contains arbitrary input. Instead, parse the choice against an allowlist and reject unsupported values.

### Parsing input into an enum

If the request uses a string:

~~~java
public ProductSortKey parseSortKey(String raw) {
    if (raw == null || raw.isBlank()) {
        return ProductSortKey.CREATED_AT;
    }

    try {
        return ProductSortKey.valueOf(
            raw.trim().toUpperCase(Locale.ROOT)
        );
    } catch (IllegalArgumentException exception) {
        throw new InvalidSortFieldException(raw);
    }
}
~~~

This snippet accepts only exact enum names. If the API wants public names like `createdAt` instead of `CREATED_AT`, create an explicit `Map` from the public key to the enum. Do not use reflection to turn arbitrary strings into property paths.

If you use the enum directly in a request DTO or `@RequestParam`, Jackson/Spring conversion can reject invalid values before the service is invoked. Whichever approach you choose, error responses must be consistent and must never fall back to concatenating raw input.

## 5. Allowlists for Sort Directions

Sort direction usually has only two values:

~~~java
public enum SortDirection {
    ASC,
    DESC
}
~~~

Convert to Spring Data:

~~~java
Sort.Direction toSpringDirection(SortDirection direction) {
    return direction == SortDirection.ASC
        ? Sort.Direction.ASC
        : Sort.Direction.DESC;
}
~~~

If the API accepts a string, parse it via an enum or fixed `Map`. Never concatenate an arbitrary direction into SQL.

When constructing a manual SQL fragment, use a `switch`:

~~~java
String directionSql = switch (direction) {
    case ASC -> "ASC";
    case DESC -> "DESC";
};
~~~

The value of `directionSql` can only be one of the two literals defined in source code. Never use the request string directly, even after trimming or uppercasing.

### Null ordering

Some databases support `NULLS FIRST` or `NULLS LAST`. This is also SQL structure, so if the API lets clients choose it, represent it with an enum:

~~~java
public enum NullPlacement {
    DEFAULT,
    FIRST,
    LAST
}
~~~

Map each value to a fixed fragment and enable the feature only when the database dialect supports it. Never concatenate raw input after `ORDER BY`.

## 6. Using `Sort` with Spring Data R2DBC Repositories

If a repository method supports `Sort`, you can pass a `Sort` built from the allowlist:

~~~java
public interface ProductRepository
        extends ReactiveCrudRepository<ProductEntity, UUID> {

    Flux<ProductEntity> findByStatus(String status, Sort sort);
}
~~~

Service:

~~~java
public Flux<ProductEntity> findProducts(
        String status,
        ProductSortKey sortKey,
        SortDirection direction) {

    Sort.Direction springDirection =
        direction == SortDirection.ASC
            ? Sort.Direction.ASC
            : Sort.Direction.DESC;

    Sort sort = Sort.by(
        springDirection,
        sortKey.property()
    );

    return repository.findByStatus(status, sort);
}
~~~

The property is chosen from the enum; `status` is a data value bound by Spring Data. The repository generates the query from entity metadata.

If the entity declares:

~~~java
@Table("products")
public record ProductEntity(
    @Id UUID id,
    String name,
    BigDecimal price,
    @Column("created_at") Instant createdAt,
    String status
) {}
~~~

then the `Sort` property should be `createdAt`. You do not necessarily use `created_at` because `Sort` in the mapping API targets entity properties.

Do not pass client-sent physical column names into `Sort`. If you want the public API to use `created_at`, map the key `created_at` to the property `createdAt` on the server.

## 7. Using `Criteria` and `R2dbcEntityTemplate`

For dynamic queries with multiple conditions, you can build `Criteria` and `Query`. Property paths passed into `Criteria` must also be selected from an allowlist if they come from requests.

Example:

~~~java
Criteria criteria = Criteria.where("status").is(status);

Query query = Query.query(criteria)
    .sort(Sort.by(
        Sort.Direction.DESC,
        ProductSortKey.CREATED_AT.property()
    ))
    .limit(50);

return template.select(ProductEntity.class)
    .matching(query)
    .all();
~~~

`Criteria` expresses conditions by property and lets Spring Data handle mapping. Even so, if the application lets clients pick field names, you must still map field keys to allowed properties before constructing `Criteria`.

Example filter keys:

~~~java
public enum ProductFilterField {
    STATUS("status"),
    CATEGORY_ID("categoryId"),
    PRICE("price");

    private final String property;

    ProductFilterField(String property) {
        this.property = property;
    }

    public String property() {
        return property;
    }
}
~~~

The service can use a `switch` or `Map` to build `Criteria` matching each field's data type. Avoid building `Criteria` from an arbitrary property string in the request.

## 8. Allowlists for Dynamic Table Names

In most applications, table names should be fixed in entity mappings or repositories. Dynamic table selection is only necessary in special cases such as:

- Separate archive tables.
- Period-managed partitioned tables.
- Sharding by tenant or region.
- Multiple identically structured tables chosen by a routing registry.

Do not write:

~~~java
String sql = "SELECT * FROM " + request.tableName();
~~~

This allows input to control SQL structure.

Instead, translate a public key into a server-registered identifier:

~~~java
public enum DataSet {
    CURRENT,
    ARCHIVE
}

private static final Map<DataSet, String> TABLES = Map.of(
    DataSet.CURRENT, "products",
    DataSet.ARCHIVE, "products_archive"
);

String tableName = TABLES.get(dataSet);
~~~

Here `dataSet` must first be parsed into a valid enum. The table name comes solely from the fixed `Map`.

Then, if raw SQL is truly needed:

~~~java
String sql = "SELECT id, name FROM " + tableName
    + " WHERE status = :status";
~~~

`tableName` is a literal selected from the allowlist; `status` remains bound. Never use `request.tableName()` directly.

### Avoid dynamic tables when possible

If you only need to separate current and historical data, two fixed repositories/queries may suffice. If tenants are only a logical partition condition, a shared table with `tenant_id` is usually simpler than creating a table per tenant.

Dynamic tables complicate migrations, indexes, observability, query planning, access permissions, and transactions. Use them only when there is a clear architectural reason.

## 9. Schema-Qualified Identifiers and Quoting

A table name can consist of a schema and a table:

~~~sql
SELECT id FROM reporting.monthly_sales
~~~

If the database requires quoted identifiers, quote each component according to the dialect's rules:

~~~sql
SELECT id FROM "reporting"."monthly_sales"
~~~

Do not quote the entire string as a single identifier:

~~~sql
SELECT id FROM "reporting.monthly_sales"
~~~

The latter may be interpreted as a single table name containing a dot, rather than schema `reporting` and table `monthly_sales`.

### Quoting does not replace an allowlist

Quoting helps the database parse identifiers accurately, especially when names contain uppercase letters, reserved keywords, or special characters. It does not make raw input safe. If clients can choose identifiers, you must still select from an allowlist before quoting.

When writing manual SQL, use identifier processing/quoting appropriate for the database's R2DBC dialect. Do not assume every database uses double quotes; some dialects have different rules. When names are fixed in source code, you can use pre-quoted fragments tailored to the supported vendor.

### Do not write custom quoting by replacing characters

Do not create a quoting helper by merely wrapping raw input in quote characters. Each database has its own identifier escaping rules. The right approach is to obtain the identifier from metadata/an allowlist, then use the dialect's identifier processing API or a vendor-verified helper.

## 10. Dynamic SQL with `DatabaseClient`

`DatabaseClient` is useful when a query has dynamic structure that repository methods cannot express. The rule is to assemble only server-controlled SQL fragments; all data values still use bind parameters.

Example querying by status and sort key:

~~~java
public Flux<ProductRow> search(
        String status,
        ProductSortKey sortKey,
        SortDirection direction) {

    String column = switch (sortKey) {
        case NAME -> "name";
        case PRICE -> "price";
        case CREATED_AT -> "created_at";
    };

    String order = switch (direction) {
        case ASC -> "ASC";
        case DESC -> "DESC";
    };

    String sql = """
        SELECT id, name, price, created_at
        FROM products
        WHERE status = :status
        ORDER BY %s %s, id ASC
        """.formatted(column, order);

    return databaseClient.sql(sql)
        .bind("status", status)
        .map((row, metadata) -> new ProductRow(
            row.get("id", UUID.class),
            row.get("name", String.class),
            row.get("price", BigDecimal.class),
            row.get("created_at", Instant.class)
        ))
        .all();
}
~~~

Both `column` and `order` fragments come from fixed `switch` expressions. `status` is data so it is bound. `id ASC` is a fixed tie-breaker so results have deterministic order when multiple rows share the same sort value.

The example assumes the driver maps UUID, NUMERIC, and timestamp types to the Java types shown. Converters may need adjustment depending on the database.

### Avoid concatenating uncontrolled fragments

Do not replace the `switch` by concatenating `request.sort()` or `request.direction()` directly into SQL. Do not use a simple regex to "clean" the sort string. Reject any choice outside the allowlist.

## 11. Multi-Column Sort

An API may allow clients to send:

~~~text
GET /api/products?sort=name,ASC&sort=price,DESC
~~~

Limit the number of criteria, eliminate duplicate fields if the contract disallows them, and map each key through the allowlist.

DTO:

~~~java
public record SortRequest(
    String field,
    String direction
) {}
~~~

A parser can return `Sort.Order`:

~~~java
Sort.Order toOrder(SortRequest request) {
    ProductSortKey key = parseSortKey(request.field());
    SortDirection direction = parseDirection(request.direction());

    Sort.Direction springDirection =
        direction == SortDirection.ASC
            ? Sort.Direction.ASC
            : Sort.Direction.DESC;

    return new Sort.Order(
        springDirection,
        key.property()
    );
}
~~~

Assemble `Sort`:

~~~java
List<Sort.Order> orders = requests.stream()
    .limit(3)
    .map(this::toOrder)
    .toList();

Sort sort = orders.isEmpty()
    ? Sort.by(Sort.Direction.DESC, "createdAt")
    : Sort.by(orders);
~~~

In production code, reject requests whose sort field count exceeds the limit instead of silently truncating with `limit`. The limit of 3 in the example only illustrates policy. If the list contains duplicate fields, specify clearly whether to keep the first, keep the last, or return an error.

With raw SQL, each `Order` must be translated into a fragment from the allowlist. Never use unvalidated property or direction strings.

## 12. Dynamic Filters and Operators

Dynamic filters can also create injection if the application concatenates client-sent fields or operators.

A request might ask for:

~~~text
filterField=price
operator=gte
value=100
~~~

Only supported fields and operators may be turned into SQL:

~~~java
enum FilterField {
    STATUS,
    PRICE,
    CATEGORY_ID
}

enum FilterOperator {
    EQ,
    GTE,
    LTE,
    IN
}
~~~

Map the operator:

~~~java
String operatorSql(FilterOperator operator) {
    return switch (operator) {
        case EQ -> "=";
        case GTE -> ">=";
        case LTE -> "<=";
        case IN -> "IN";
    };
}
~~~

Column names must also be mapped independently:

~~~java
String columnSql(FilterField field) {
    return switch (field) {
        case STATUS -> "status";
        case PRICE -> "price";
        case CATEGORY_ID -> "category_id";
    };
}
~~~

Then bind the value according to the field's type. Never let clients send arbitrary operator strings and concatenate them into SQL.

### Type checking per field

Not every filter accepts a `String`. `PRICE` needs `BigDecimal`; `CATEGORY_ID` needs `UUID`; `STATUS` may be an enum or string code. Parse and validate types before binding.

Prefer a strongly typed internal model rather than an uncontrolled `Map<String, Object>`:

~~~java
sealed interface ProductFilter
    permits StatusFilter, PriceRangeFilter, CategoryFilter {}

record StatusFilter(String status) implements ProductFilter {}
record PriceRangeFilter(BigDecimal min, BigDecimal max)
    implements ProductFilter {}
record CategoryFilter(UUID categoryId) implements ProductFilter {}
~~~

Each filter type has its own builder that produces `Criteria` or fixed SQL fragments. This reduces casting errors and restricts how input can affect syntax.

## 13. `IN` Clauses and Lists of Values

Lists of values must have each element bound. Do not concatenate CSV strings into SQL:

~~~java
// Unsafe and also error-prone when values contain commas/quotes.
String sql = "WHERE id IN (" + String.join(",", rawIds) + ")";
~~~

With `DatabaseClient`, you can generate indexed bind marker names:

~~~java
String placeholders = IntStream.range(0, ids.size())
    .mapToObj(index -> ":id" + index)
    .collect(Collectors.joining(", "));

String sql = "SELECT id, name FROM products WHERE id IN ("
    + placeholders
    + ")";

DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(sql);

for (int index = 0; index < ids.size(); index++) {
    spec = spec.bind("id" + index, ids.get(index));
}

return spec.map((row, metadata) ->
        new ProductRow(
            row.get("id", UUID.class),
            row.get("name", String.class)
        ))
    .all();
~~~

Placeholder names are generated solely from server-created numeric indices. Each UUID is still bound as a value.

### Handling empty lists

Do not generate SQL `IN ()` if the database does not support it. Define clear semantics:

- If an empty list means no filter, omit the `IN` condition.
- If an empty list means no results, return `Flux.empty()` or add an always-false condition.
- Never interpret an empty list as "all" if doing so could widen access permissions.

### Limiting the number of bind parameters

Large lists can exceed bind parameter limits. Split the list into chunks, use a temporary table, or use a database-appropriate bulk mechanism. Never fall back to concatenating raw values into SQL to work around parameter limits.

## 14. `LIKE`, Wildcards, and String Search

Bind parameters prevent data from becoming SQL syntax, but `%` and `_` in `LIKE` still carry wildcard meaning. If the API requires literal string matching, escape wildcards according to database rules.

Example SQL:

~~~sql
WHERE name LIKE :pattern ESCAPE '\'
~~~

Pattern-building code must escape:

~~~java
String escapeLike(String value) {
    return value
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_");
}

String pattern = "%" + escapeLike(searchText) + "%";
~~~

Escape syntax and string literals can differ across databases; test on the production dialect. Binding is still required to prevent SQL injection. Wildcard escaping only adjusts search semantics; it does not replace bind parameters.

Never concatenate `searchText` directly into SQL, even after escaping wildcards.

## 15. Pagination and Deterministic Ordering

`LIMIT`/`OFFSET` are usually values and can be bound:

~~~sql
SELECT id, name, created_at
FROM products
ORDER BY created_at DESC, id ASC
LIMIT :limit OFFSET :offset;
~~~

Validate:

- `page` is non-negative.
- `size` is greater than 0.
- `size` does not exceed the cap.
- `offset` does not exceed integer limits or API policy.
- Sort keys and directions come from the allowlist.

Never let clients pass a full SQL string into the `sort` query parameter.

### Always include a tie-breaker

When sorting by `created_at`, multiple rows can share the same timestamp. Add `id` as a tie-breaker:

~~~sql
ORDER BY created_at DESC, id ASC
~~~

Deterministic ordering makes pagination less likely to duplicate or skip rows when primary sort values are equal. If data changes continuously between pages, `OFFSET` pagination can still shift results; consider keyset pagination.

### Keyset pagination

With sorting `created_at DESC, id ASC`, a cursor can hold the `createdAt` and `id` of the last row on the page. The next page query uses the corresponding comparison predicate. Column structure and sort directions must still be selected from an allowlist; cursor values must be bound.

Keyset pagination suits large datasets because it avoids skipping deep offsets. However, each sort combination may require a dedicated predicate. Support only predefined combinations and test comparison/null semantics thoroughly.

## 16. Dynamic Tables in Multi-Tenant Systems

Some systems create separate tables per tenant. This is a special case requiring strict control.

Never construct table names directly from headers or query parameters:

~~~java
String table = "orders_" + request.tenant();
~~~

Even if tenant names are strictly alphanumeric, building table names from input creates risks of wrong-tenant routing, cross-tenant data access, or injection when naming rules evolve.

Prefer:

1. Obtain the tenant identity from the authenticated security context.
2. Look up the tenant in a server-side registry.
3. Have the registry return a provisioned schema/table identifier.
4. Verify the tenant is authorized to access that database/shard.
5. Select SQL fragments from trusted metadata.
6. Bind all filter values, including the tenant key if schemas are shared.

Where the model allows, a shared table with `tenant_id` and row-level access conditions is usually easier to manage than many separate tables.

### A table allowlist does not replace authorization

Even when a table name is valid, the user may still lack permission to access that tenant. The allowlist protects SQL structure; authorization protects data access. Both must be enforced.

Never treat a tenant ID from the request as proof of access rights. Use the authenticated principal and include tenant conditions in queries to avoid querying the wrong data.

## 17. Identifiers in R2DBC and Spring Data Mapping

Spring Data Relational uses entity metadata to map Java properties to column/table names. Annotations such as `@Table`, `@Id`, and `@Column` describe static mapping:

~~~java
@Table("products")
public record ProductEntity(
    @Id UUID id,
    String name,
    @Column("created_at") Instant createdAt
) {}
~~~

When using repositories or `R2dbcEntityTemplate`, Spring Data knows that the `createdAt` property maps to the `created_at` column.

`SqlIdentifier` is Spring Data Relational's abstraction for representing identifiers and quoting metadata. It is useful in mapping APIs and custom persistence implementations that support identifiers. It is not a SQL bind parameter and does not automatically make raw request strings safe.

With raw `DatabaseClient` SQL, the application is responsible for constructing the SQL text. Map external keys to trusted identifiers before assembling. When quoting is needed, use dialect-appropriate identifier processing.

### Differences between repositories and custom SQL

- Repository derived queries typically take properties and values per Spring Data metadata.
- `Sort` in repositories uses mapped property paths.
- `Criteria`/`Query` use entity properties.
- `DatabaseClient` takes SQL text and bound values; dynamic identifiers in SQL text must be controlled manually.
- Custom `Statement` at the R2DBC SPI level is responsible for SQL, markers, and connection lifecycle.

Choose the appropriate API to minimize the number of SQL fragments you have to manage manually.

## 18. Testing Allowlists and SQL Injection

Security tests should prove that inputs outside the allowlist are rejected before a query is executed.

### Unit testing the parser

~~~java
@Test
void acceptsOnlySupportedSortKeys() {
    assertEquals(
        ProductSortKey.CREATED_AT,
        parser.parseSortKey("created_at")
    );
}

@Test
void rejectsUnknownSortKey() {
    assertThrows(
        InvalidSortFieldException.class,
        () -> parser.parseSortKey("name; DROP TABLE products")
    );
}
~~~

The first example only holds if the parser maps the public key `created_at` to `CREATED_AT`. Parsing rules must be defined explicitly rather than accepting arbitrary variations automatically.

### Testing sort directions

Verify `ASC` and `DESC` convert to the right enum or fixed fragment. Sending values such as `DESC NULLS FIRST`, `ASC` with extra syntax, or arbitrary strings must be rejected if the API only supports `ASC`/`DESC`.

### Testing that SQL-looking values remain data

A string such as:

~~~text
x' OR '1'='1
~~~

submitted in `name` or `searchText` must be stored/searched as a literal value when bound. It must not alter SQL conditions.

An integration test can insert that string using a bind parameter, then read it back and verify it matches verbatim.

### Testing table routing

- Key `CURRENT` selects the `products` table.
- Key `ARCHIVE` selects the `products_archive` table.
- Keys outside the enum are rejected.
- An unauthorized tenant cannot select another tenant's table.
- Input containing SQL characters cannot become an identifier.

### Testing schema integrity

In an integration test against a dedicated database, send sort/table injection attempts and verify the query returns a validation error and the tables still exist. Never run destructive tests against a shared database.

## 19. Standardizing Errors for Invalid Identifiers

An unsupported sort key or table key is a request error. You can return `400 Bad Request` with a stable error code:

~~~java
public record ApiError(
    String code,
    String message
) {}
~~~

Example:

~~~java
@ExceptionHandler(InvalidSortFieldException.class)
public ResponseEntity<ApiError> handleInvalidSort(
        InvalidSortFieldException exception) {

    return ResponseEntity.badRequest().body(
        new ApiError(
            "INVALID_SORT_FIELD",
            "Requested sort field is not supported"
        )
    );
}
~~~

In WebFlux, exception handlers can return reactive types if needed; these examples use `ResponseEntity` directly for synchronous responses after an exception is thrown.

Do not return raw SQL fragments or internal details of the allowlist unless necessary. You may log a masked key or length-limited value to aid investigation.

Distinguish validation errors from database errors:

- Invalid sort key: `400`.
- Disallowed table key: `400` or `403` depending on API semantics.
- Unauthorized tenant: `403` or `404` per resource-enumeration prevention policy.
- SQL grammar error caused by a bug in a fixed fragment: `500` and operational alert.
- Database temporarily unavailable: handle as an infrastructure error.

## 20. Common Mistakes

| Mistake | Why it is wrong | Remedy |
| --- | --- | --- |
| Binding table names with `:table` | Bind markers are values, not identifiers. | Select tables from an allowlist. |
| Binding columns in `ORDER BY` | May sort by a literal instead of a column. | Map keys to trusted properties/fragments. |
| Binding `ASC`/`DESC` | Direction is SQL syntax. | Use an enum and fixed `switch`. |
| Concatenating sort requests into SQL | Input controls query structure. | Parse against an allowlist before building SQL. |
| Using a regex blacklist to sanitize identifiers | SQL and identifiers have many representations. | Use an allowlist. |
| Only quoting raw identifiers | Quoting does not replace authorization/allowlists. | Allowlist first, then quote per dialect. |
| Using physical column names in `Sort` mismatched with mapping | Spring Data usually expects Java properties. | Map public keys to entity properties. |
| Using raw tenant names to form table names | Risks misrouting tenants or injection. | Server-side tenant registry and authorization. |
| Allowing arbitrary filter operators | Operators are SQL structure. | Fixed operator enum/map. |
| Concatenating `IN` lists as CSV | Quotes/commas can break syntax and cause injection. | Bind each element or use an appropriate collection API. |
| Sorting without a tie-breaker | Pagination can become unstable. | Add a unique column like `id`. |
| Letting clients pass `ORDER BY` expressions | Arbitrary functions/identifiers widen the injection surface. | Allowlist entire expressions. |
| Using client-sent alias names | Aliases are also identifiers. | Use fixed aliases from source code. |

## 21. Workflow for Building Safe Dynamic Queries

When an endpoint needs dynamic filtering, sorting, or table selection, follow this order:

1. **Identify which parts are values:** user data, dates, numbers, and IDs must be bound.
2. **Enumerate allowed structures:** tables, schemas, columns, aliases, expressions, operators, and directions.
3. **Create an enum/registry:** map public keys to properties or fixed SQL fragments.
4. **Parse and validate requests:** reject unsupported choices before calling the database.
5. **Use mapping APIs when suitable:** repository `Sort`, `Criteria`, and `Query` let Spring Data map properties.
6. **Assemble minimal SQL:** concatenate only allowlisted fragments.
7. **Bind all values:** never concatenate values into SQL text.
8. **Control collections:** handle empty `IN` lists and limit bind parameter counts.
9. **Limit pagination:** page size, offset, sort field count, and filter complexity.
10. **Check authorization:** especially for tenant-scoped schemas/tables.
11. **Test malicious inputs:** sort keys, directions, table keys, filter operators, and SQL-looking values.
12. **Observe queries:** log query names/fingerprints and duration; do not log sensitive data.

Controlling dynamic identifiers is the responsibility of the query-building layer. Bind parameters protect data values, but they cannot replace allowlists for table names, column names, sort expressions, or sort directions. In Spring Data R2DBC, prefer `Sort`/`Criteria` based on validated properties; when `DatabaseClient` or custom SQL is required, assemble only server-defined fragments and bind all values. Combining allowlists with authorization, dialect-aware quoting, and integration tests keeps dynamic queries flexible while keeping SQL structure firmly under control.
