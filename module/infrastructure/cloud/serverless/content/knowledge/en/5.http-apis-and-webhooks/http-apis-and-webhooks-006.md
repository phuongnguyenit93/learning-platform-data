# Designing Pagination, Filtering, and API Versioning

## Learning Objectives

After this lesson, you will be able to:

- Design HTTP endpoints that return large datasets in chunks.
- Choose between offset or cursor/keyset pagination based on data characteristics and client traversal patterns.
- Build safe, intuitive, bounded filtering and sorting.
- Design API versioning and controlled contract evolution.
- Apply these principles to HTTP-triggered Java functions in serverless environments.

## 1. Why List APIs Need Pagination

Suppose an order management application has an endpoint:

~~~http
GET /orders
~~~

When the system has only a few dozen orders, returning the entire list might still work. When the count grows to millions, that approach causes several problems:

- Large responses increase transfer time, memory usage, and processing cost.
- The function must read and serialize many records even if the client displays only a fraction.
- Heavy queries hold database connections longer and impact other requests.
- Clients struggle to find the right data without filtering by status, time, or customer.
- Changing the response structure can break existing API clients.

A list API usually needs three capabilities working together:

1. **Pagination:** splitting results into small chunks and allowing clients to fetch more.
2. **Filtering and sorting:** defining the subset of data and the return order.
3. **API versioning:** evolving the contract while controlling impact on existing clients.

In serverless architectures, these requirements tie directly to execution duration, concurrency, and cost. Each HTTP request may invoke a new Java function. Requests loading too many records consume memory, lengthen invocations, and increase database load.

The running example throughout this lesson is an order management API. Clients need to view lists, filter by status or creation time, sort by date, and advance to the next page of results.

## 2. Designing a List Endpoint Contract

An endpoint can start with a contract like:

~~~http
GET /v1/orders?limit=25&status=PAID&sort=-createdAt
Accept: application/json
~~~

Meaning:

- `/v1/orders`: order list belonging to API version 1.
- `limit=25`: request at most 25 items.
- `status=PAID`: retrieve only paid orders.
- `sort=-createdAt`: sort by creation date descending.
- `Accept`: response format the client can handle.

A request adding a time range:

~~~http
GET /v1/orders?limit=25&status=PAID&createdAfter=2026-01-01T00%3A00%3A00Z&createdBefore=2026-02-01T00%3A00%3A00Z&sort=-createdAt,id
~~~

Parameter names are part of the public contract. Use consistent names, and clearly document data types, defaults, bounds, and how multiple conditions combine. Avoid forcing clients to guess whether `size` is a record count, whether `page` is 0- or 1-indexed, or whether `date` is local date or a UTC timestamp.

### 2.1. Pagination Parameters

| Parameter | Meaning | Example |
|---|---|---|
| `limit` | Maximum records in a page | `limit=25` |
| `offset` | Number of records to skip before returning results | `offset=50` |
| `cursor` | Token to resume from the last read position | `cursor=eyJ...` |
| `page` | Page number per API convention | `page=3` |
| `pageSize` | Desired number of items in a page | `pageSize=25` |

You do not need to support every parameter. A contract should pick one primary pagination style so clients do not accidentally send both `offset` and `cursor` with conflicting meanings.

Set a sensible default `limit` and a server-side maximum, such as default 20 and maximum 100. Exact values should reflect record size, database performance, and platform limits. The server must validate and cap client-provided values; never let `limit=1000000` trigger an unbounded query.

### 2.2. Response Contract

A paginated response can be structured as:

~~~json
{
  "data": [
    {
      "id": "ord_1024",
      "status": "PAID",
      "total": 125000,
      "createdAt": "2026-01-15T10:20:30Z"
    }
  ],
  "page": {
    "limit": 25,
    "nextCursor": "eyJ2IjoxLCJrZXkiOi...",
    "hasMore": true
  },
  "links": {
    "next": "/v1/orders?limit=25&cursor=eyJ2IjoxLCJrZXkiOi..."
  }
}
~~~

`data` holds the records for the current page. `page` describes how to continue. `links.next` is a relative or absolute URL the client can request next. On the final page, `nextCursor` and `next` can be `null`, and `hasMore` is `false`.

Returning both `nextCursor` and `links.next` is not mandatory; pick a consistent contract. If providing links, the server should construct URLs from normalized parameters and preserve active filters and sorting so the next page queries the same result set.

Some APIs also return `totalItems` or `totalPages`. This is useful for UI elements like "page 2 of 14", though exact counting can be expensive on large datasets. Provide it only when genuinely needed and when query costs are acceptable. With cursor pagination, `hasMore` is usually enough for a "Load more" button.

## 3. Offset Pagination

Offset pagination uses a starting position and the number of records to fetch. Example:

~~~http
GET /v1/orders?limit=20&offset=40
~~~

The server can run an equivalent query:

~~~sql
SELECT id, status, total, created_at
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, id DESC
LIMIT :limit
OFFSET :offset;
~~~

This request skips the first 40 records and returns up to the next 20 records.

### 3.1. Advantages and Limitations

Offset is easy to understand and implement. Clients can jump to any position, compute pages from a page number, and display total page counts if the server supplies total record counts. It works well for moderate datasets, internal admin tables, or screens needing direct jumps to specific pages.

However, offset positions can shift as records are inserted or deleted. Suppose a client reads the first page, and then 3 new orders are inserted at the top of the list ordered by descending creation time. When the client requests the next page with `offset=20`, some records may reappear because their positions shifted. If a record is deleted before the offset position, the client may skip an unread record.

Deep offsets can also be expensive. The database may have to scan and discard many rows before returning the needed slice. `OFFSET 500000 LIMIT 20` is typically far more costly than fetching the first 20 records, especially without a suitable index.

If choosing offset:

- Always use an explicit `ORDER BY` with a unique tie-breaker key for deterministic results.
- Bound `limit` and `offset`; reject negative values or values exceeding published limits.
- Create indexes matching common filter conditions and sort orders.
- Define how data changes between requests are handled and document it in the API docs.
- Avoid promising that pages form an immutable snapshot unless the system actually maintains a snapshot.

For example, `ORDER BY created_at DESC, id DESC` is more stable than `ORDER BY created_at DESC` because multiple records can share the same creation timestamp. `id` serves as a tie-breaker to determine order among records with identical `created_at`.

If business requirements demand exporting a point-in-time consistent dataset, ordinary offset pagination is insufficient. Consider snapshots, appropriate transaction isolation, asynchronous export jobs, or a fixed data watermark.

## 4. Cursor and Keyset Pagination

Cursor pagination uses a token indicating where to continue. Clients do not need to compute offsets. Example:

~~~http
GET /v1/orders?limit=20&cursor=eyJ2IjoxLCJjcmVhdGVkQXQiOi...
~~~

Suppose the sort order is `created_at DESC, id DESC`. After returning the first page, the server creates a cursor from the key pair of the last record. The next page queries records appearing after that anchor:

~~~sql
SELECT id, status, total, created_at
FROM orders
WHERE tenant_id = :tenant_id
  AND (created_at, id) < (:last_created_at, :last_id)
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;
~~~

Tuple comparison syntax may vary across database engines. It can be written equivalently as `created_at < :last_created_at OR (created_at = :last_created_at AND id < :last_id)`.

The server fetches `limit + 1` records to know whether more data exists. If more than `limit` rows return, the server returns the first `limit` records and constructs a cursor from the last returned record. This avoids running a separate count query just to check for a next page.

### 4.1. Why Cursors Are More Stable

Because a cursor relies on the sort values of the last record, new records inserted ahead of the anchor generally do not shift the continuation position like offset does. Keyset queries can also leverage indexes to seek directly from the anchor instead of skipping huge numbers of rows.

Nevertheless, cursors do not automatically create a snapshot. If records are deleted, change their sort field, or change status so they no longer match a filter, the result set across requests can still change. If strict snapshots are required, design an explicit watermark or snapshot mechanism.

Cursor pagination fits feeds, transaction histories, activity logs, and large sequentially traversed datasets. It is less convenient when clients need to jump straight to page 50 or require exact page numbers.

### 4.2. Cursors Should Be Opaque Tokens

Clients should treat cursors strictly as strings to pass back to the server, without inspecting or fabricating their contents. A token can URL-safe Base64-encode a payload containing:

- Cursor format version.
- Sort values of the page's last record.
- Sort order and associated filters.
- Data watermark or expiration timestamp if needed.
- Binding information tying the cursor to the tenant or query scope.

Base64 is only encoding, not cryptographic protection. If the payload holds sensitive data, encrypt it with an appropriate mechanism. To prevent cursor tampering, sign the payload with HMAC or a digital signature. The server verifies the signature before using cursor values in a query.

Never trust `tenantId`, access permissions, or security conditions merely because they are inside a cursor. The server must still derive identity from the request's authentication context and enforce authorization on every page. Cursors should be bound to the current user/tenant scope so tokens from another tenant cannot be reused.

If a cursor is invalid, mismatched in version, or incompatible with the current filters/sort, return a clear client error—typically `400 Bad Request`. If the token expired per policy, inform the client that it must restart from the first page. Never include SQL, index names, or internal details in error responses.

### 4.3. Choosing Offset or Cursor?

| Criterion | Offset | Cursor/Keyset |
|---|---|---|
| Ease of implementation and explanation | High | Requires designing tokens and anchors |
| Jumping to an arbitrary page | Convenient | Inconvenient |
| Very large datasets | Deep offsets can be slow | Typically more efficient with proper indexes |
| Continuously changing data | May duplicate or skip rows across pages | Less affected by new rows inserted before the anchor |
| Total page count | Can pair with `COUNT` | Usually does not provide total pages |
| Sequential traversal | Good | Well suited |
| Feeds or transaction history | Usable at small scale | Often the better choice |

There is no mandatory rule that every API must use cursors. Choose based on how clients traverse data and actual query characteristics. One system might use offset for small admin tables and cursors for large feeds, as long as each endpoint publishes a clear contract.

## 5. Controlled Filtering

Filters let clients narrow the result set. Example:

~~~http
GET /v1/orders?status=PAID&customerId=cus_42&createdAfter=2026-01-01T00%3A00%3A00Z
~~~

The server returns only orders matching the defined conditions. Explicitly document supported filters, data types, comparison operators, and how multiple conditions combine.

### 5.1. Designing Filter Names and Semantics

| Parameter | Type | Meaning |
|---|---|---|
| `status` | Enum or repeated value | Order status |
| `customerId` | Identifier string | Customer's orders |
| `createdAfter` | ISO 8601 timestamp | Created after this point in time |
| `createdBefore` | ISO 8601 timestamp | Created before this point in time |
| `minTotal` | Decimal number | Minimum total amount |
| `maxTotal` | Decimal number | Maximum total amount |
| `q` | String | Search according to published rules |

Clearly define time boundaries. For instance, `createdAfter` can mean `created_at >= value`, while `createdBefore` means `created_at < value`. Using half-open intervals `[from, to)` prevents adjacent ranges from overlapping. Document this rule explicitly.

Timestamps should use a timezone-aware format, typically ISO 8601 with `Z` for UTC or an explicit offset. Do not silently interpret `2026-01-01T09:00:00` as UTC if the string omits a timezone.

If multiple values are allowed for the same filter, adopt a clear convention:

~~~http
GET /v1/orders?status=PAID&status=SHIPPED
~~~

Here, the two `status` values can be interpreted as OR within the same field, while different fields combine with AND. For example: `(status = PAID OR status = SHIPPED) AND customerId = cus_42`. Another API might choose `status=PAID,SHIPPED`; what matters is documenting and parsing consistently.

### 5.2. Allow Only Supported Filters

Never take arbitrary field names from a query string and concatenate them into SQL. The following example is very dangerous:

~~~java
String sql = "SELECT * FROM orders WHERE " + request.getParameter("field")
        + " = ?";
~~~

Bind parameters protect values, but they do not protect column names or SQL expressions concatenated from input. Callers could supply unintended column names, operators, or expressions.

Instead, use an allowlist for fields and operators:

~~~java
enum OrderFilterField {
    STATUS,
    CUSTOMER_ID,
    CREATED_AT,
    TOTAL
}
~~~

After parsing, translate each valid field into a predicate built from controlled code. Always use prepared statements or parameterized query APIs for values. If supporting dynamic sorting, column names and sort directions must likewise go through a dedicated allowlist.

### 5.3. Validating Filters

The server should check:

- Whether enum values belong to the supported set.
- Whether `minTotal` is less than or equal to `maxTotal`.
- Whether `createdAfter` precedes `createdBefore`.
- Whether search strings stay within length limits.
- Whether the number of filters, repeated values, and query complexity stay within bounds.
- Whether the filters align with the caller's access permissions.

If a query is invalid, return `400 Bad Request` detailing which field is invalid and what values are accepted. Do not silently ignore invalid filters, because clients might assume data was filtered properly while the server returns more records than expected.

### 5.4. Security and Data Scope

Filters do not replace authorization. A client may send someone else's `customerId`; the server must determine whether the caller is permitted to read that data. In multi-tenant systems, tenant constraints must come from the server-side authentication context, independent of client-sent query parameters.

Likewise, pagination is not a security boundary. The server must enforce access permissions before computing pages, counting records, or generating cursors. Counting totals before applying permission filters can leak record counts belonging to other tenants.

Free-text search filters also require cost bounds. Full-text searches, leading wildcards, arbitrary regexes, or multi-table joins can impose heavy load. Publish supported search modes and enforce timeouts, length limits, rate limits, or dedicated search engines when needed.

## 6. Stable Sorting and Pagination Compatibility

Filters determine which records are selected; sorting determines return order. Both directly affect pagination. A cursor is meaningful only when the server knows the exact order it is continuing.

### 6.1. Allow Only Published Sort Fields

Example:

~~~http
GET /v1/orders?sort=-createdAt,id
~~~

Conventions in the example:

- A leading `-` before a field means descending.
- A field without `-` means ascending.
- Multiple fields are comma-separated.
- The server accepts only published fields, such as `createdAt`, `total`, and `id`.

Never concatenate client sort strings directly into SQL. Use an allowlist mapping API names to database columns:

| API Name | Internal Column | Sort Allowed? |
|---|---|---|
| `createdAt` | `created_at` | Yes |
| `total` | `total_amount` | Yes |
| `id` | `id` | Yes |
| `customerEmail` | `customer_email` | No, if not published |

Internal column names may differ from public field names. Mapping through an enum or fixed configuration prevents SQL injection and avoids accidentally exposing database schema internals.

### 6.2. Ordering Must Be Uniquely Deterministic

A query sorting only by `created_at DESC` can return records with identical timestamps in an indeterminate order. During pagination, a record can be duplicated or skipped if the database picks a different tie order across queries.

Append a unique key as a tie-breaker:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

If the client requests `sort=-createdAt`, the server can automatically append `id DESC` to the internal ordering. Document that this tie-breaker is applied to guarantee deterministic ordering.

Cursors must include values for the entire sort key. If sorting by `created_at DESC, id DESC`, storing only `created_at` in the cursor is insufficient; it also needs `id` to pinpoint the continuation point when multiple records share the same timestamp.

### 6.3. Nulls and Indexes

If a field allows `NULL`, define whether nulls sort first or last in ascending/descending order. Default database behavior can vary. If a cursor relies on a nullable field, comparison expressions must handle nulls explicitly; in some cases, prefer non-nullable sort keys.

Indexes should align with common queries. For instance, queries by tenant, status, and creation date may benefit from a composite index like `(tenant_id, status, created_at, id)`. Do not create indexes for every conceivable filter combination; that inflates write and storage costs. Base index decisions on query plans and real metrics.

If supporting many sort/filter combinations, restrict the supported combinations or identify critical query patterns. An overly flexible API can leave the database without usable indexes for common requests.

## 7. Implementation Example in Java

In serverless architectures, an HTTP adapter receives requests from API Gateway, an HTTP trigger, or an equivalent platform. The adapter reads query parameters, validates inputs, calls the service, and converts results into an HTTP response. Pagination logic should reside in the service/repository layer so it can be tested independently of the cloud provider.

### 7.1. Request and Response Data Types

The code below illustrates Java data types for cursor pagination. This is a skeleton example; add parsers, serializers, and adapters matching your framework or platform.

~~~java
import java.time.Instant;
import java.util.List;

public record OrderFilter(
    String status,
    String customerId,
    Instant createdAfter,
    Instant createdBefore
) {}

public enum OrderSortField {
    CREATED_AT,
    TOTAL,
    ID
}

public enum SortDirection {
    ASC,
    DESC
}

public record SortTerm(
    OrderSortField field,
    SortDirection direction
) {}

public record CursorPageRequest(
    int limit,
    String cursor,
    List<SortTerm> sort
) {}

public record PageMetadata(
    int limit,
    String nextCursor,
    boolean hasMore
) {}

public record PageResponse<T>(
    List<T> data,
    PageMetadata page
) {}
~~~

Using enums for sort fields and directions ensures the query layer works only with validated values. Query parameters are converted into enums only after matching the allowlist. Never let arbitrary column names flow straight from the HTTP request to the repository.

### 7.2. Query Orchestration Service

Service example:

~~~java
public final class OrderQueryService {
    private static final int DEFAULT_LIMIT = 20;
    private static final int MAX_LIMIT = 100;

    private final OrderRepository repository;
    private final CursorCodec cursorCodec;

    public OrderQueryService(
            OrderRepository repository,
            CursorCodec cursorCodec) {
        this.repository = repository;
        this.cursorCodec = cursorCodec;
    }

    public PageResponse<OrderView> search(
            OrderFilter filter,
            Integer requestedLimit,
            String cursorToken,
            List<SortTerm> requestedSort,
            RequestIdentity identity) {

        int limit = requestedLimit == null
                ? DEFAULT_LIMIT
                : requestedLimit;

        if (limit < 1 || limit > MAX_LIMIT) {
            throw new InvalidQueryException(
                    "limit must be between 1 and " + MAX_LIMIT);
        }

        validateFilter(filter);
        List<SortTerm> sort = normalizeSort(requestedSort);

        CursorPosition position = cursorToken == null
                ? null
                : cursorCodec.decodeAndVerify(
                        cursorToken, filter, sort, identity);

        List<OrderView> rows = repository.findPage(
                identity.tenantId(),
                filter,
                sort,
                position,
                limit + 1);

        boolean hasMore = rows.size() > limit;
        List<OrderView> data = hasMore
                ? rows.subList(0, limit)
                : rows;

        String nextCursor = null;
        if (hasMore && !data.isEmpty()) {
            OrderView last = data.get(data.size() - 1);
            nextCursor = cursorCodec.encode(
                    last, filter, sort, identity);
        }

        return new PageResponse<>(
                data,
                new PageMetadata(limit, nextCursor, hasMore));
    }

    private void validateFilter(OrderFilter filter) {
        if (filter.createdAfter() != null
                && filter.createdBefore() != null
                && !filter.createdAfter().isBefore(filter.createdBefore())) {
            throw new InvalidQueryException(
                    "createdAfter must be earlier than createdBefore");
        }
    }

    private List<SortTerm> normalizeSort(List<SortTerm> requested) {
        // Parse allowlist, apply default sort, and append ID as tie-breaker.
        return OrderSortPolicy.normalize(requested);
    }
}
~~~

`OrderRepository`, `CursorCodec`, `CursorPosition`, `OrderView`, `RequestIdentity`, `InvalidQueryException`, and `OrderSortPolicy` are illustrative components. In production implementations:

- `CursorCodec` must verify signature, version, filter/sort binding, and identity scope before decoding the position.
- `RequestIdentity` extracts tenant and user from a verified authentication context.
- `OrderRepository` must enforce tenant and access conditions in the query.
- `findPage` must use parameterized queries and deterministic ordering.
- `OrderSortPolicy` maps enums strictly to allowlisted columns.
- The repository fetches only `limit + 1` rows to determine `hasMore`, never loading the entire result set.

One important detail: `rows.subList(0, limit)` in the example is safe only after confirming `rows.size() > limit`. When the repository returns fewer than or equal to `limit` rows, the service uses the full list. For large datasets, the repository must return a bounded collection; never materialize the entire result set and slice afterward.

### 7.3. HTTP Adapter and Status Codes

The adapter can translate the request into a service call and return `200 OK` with `PageResponse`. Common error scenarios:

| Scenario | HTTP Status | Response Behavior |
|---|---:|---|
| Valid query, with or without data | `200 OK` | Return `data` and pagination metadata |
| Invalid parameter, corrupted cursor, unsupported sort | `400 Bad Request` | Indicate invalid parameter and valid rules |
| Unauthenticated | `401 Unauthorized` | Require authentication |
| Authenticated but lacking permission | `403 Forbidden` | Do not disclose restricted data |
| Specific resource does not exist | `404 Not Found` | Used for single-resource endpoints |
| Rate limit exceeded | `429 Too Many Requests` | May include `Retry-After` |
| Downstream service temporarily unavailable | `503 Service Unavailable` | May include retry guidance |

An empty list is usually a successful response with `data: []`, not `404`. `404` applies when a specifically requested resource does not exist or cannot be disclosed to the caller under security policy.

For validation errors, you can use `application/problem+json` per HTTP Problem Details. Example:

~~~json
{
  "type": "https://api.example.com/problems/invalid-query",
  "title": "Invalid query parameter",
  "status": 400,
  "detail": "The requested sort field is not supported.",
  "errors": [
    {
      "field": "sort",
      "message": "Allowed fields: createdAt, total, id."
    }
  ]
}
~~~

Never return stack traces, SQL, table names, or internal data in client error responses. Record technical details in controlled logs and use a correlation ID to link requests to logs.

## 8. What Is API Versioning?

An API contract encompasses endpoints, methods, request parameters, headers, response schemas, status codes, and processing semantics. Changing part of the contract can impact integrated clients.

For example, v1 of an API returns:

~~~json
{
  "id": "ord_1024",
  "total": 125000
}
~~~

A new version might want to replace `total` with a currency object:

~~~json
{
  "id": "ord_1024",
  "amount": {
    "value": 125000,
    "currency": "VND"
  }
}
~~~

Removing `total` immediately on the endpoint older clients call can break clients parsing the response. API versioning creates a boundary allowing clients to choose the contract they integrated against.

Not every change warrants a new version. Adding an optional response field is often compatible with clients designed to ignore unknown fields. However, some clients deserialize JSON against strict schemas or use exhaustive switches on enums, so even seemingly additive changes can break them. Evaluate how clients consume contracts before classifying a change.

## 9. Choosing How to Express API Versions

There are three common ways for clients to select a version.

### 9.1. Version in the URL Path

~~~http
GET /v1/orders
GET /v2/orders
~~~

This approach is easy to observe, log, and route on API Gateway. Two versions can run side by side for a transition window. Clients clearly see which version they are calling directly in the URL.

On the flip side, the version becomes part of the resource URL. When running multiple versions, teams must manage routes, documentation, and support windows per version. For public APIs, this approach is usually straightforward to understand and operate.

### 9.2. Version in an HTTP Header

~~~http
GET /orders
X-API-Version: 2
~~~

The URL remains unchanged; the server selects the contract based on the header. This keeps URLs clean, though the version is less visible in logs and manual debugging. Caches or CDNs must vary responses by this header; otherwise, clients may receive responses from a different version. When caching by header, configure `Vary: X-API-Version`.

Header names like `X-API-Version` are API-specific conventions. Clearly define the default value and behavior when the header is missing or specifies an unsupported version.

### 9.3. Version via Media Type

Clients can select a representation via `Accept`:

~~~http
GET /orders
Accept: application/vnd.example.orders.v2+json
~~~

This binds the version to the resource representation and fits systems needing content negotiation. However, clients, gateways, documentation, and caches must all understand the custom media type. It can be unnecessarily complex for a straightforward API.

### 9.4. Which Approach Should You Choose?

| Approach | Strengths | Management Considerations |
|---|---|---|
| URL path (`/v1`) | Explicit, easy to debug, easy-to-find routes and docs | Versioned URLs, requires managing multiple routes |
| Header | Stable URLs, separates version from resource path | Caches, gateways, and logs must inspect the header |
| Media type | Expresses representation and content negotiation | Clients and tooling must support custom media types |
| Query parameter (`?version=2`) | Quick to test | Easily overlooked, generally a poor fit for long-term contracts |

Pick one primary approach and use it consistently across the entire API. For public APIs or internal APIs with many consumers, path versioning is usually the clearest choice. Avoid having one endpoint in the same API select versions by path and another by header without strong justification.

Do not create a new version on every deployment. A version signifies a contract change affecting clients, not a build number, internal release number, or function runtime version.

## 10. Backward-Compatible vs. Breaking Changes

### 10.1. Changes That Are Generally Compatible

The following changes usually have minimal impact when clients are built to ignore unknown data:

- Adding an optional response field.
- Adding a new endpoint.
- Adding an optional query parameter with a sensible default.
- Adding response links or metadata that clients are not required to understand.

Still, do not assume every client is tolerant. A client using strict JSON schema deserialization may fail on a new field. A client using an exhaustive enum switch may fail when the server adds an enum value. Verify how real clients handle responses.

### 10.2. Changes That Usually Require a New Version

The following changes carry high risk of breaking clients:

- Removing or renaming an actively used response field.
- Changing a field's data type, unit, or meaning.
- Adding a required request field that older clients do not send.
- Changing how filters, sorting, pagination, or default values are interpreted.
- Changing the response envelope structure or error format.
- Changing access permissions or business rules so existing requests produce different outcomes.
- Removing an enum value or altering the meaning of an existing value.

For example, changing `total` from VND currency units to minor units without renaming the field is a semantic change even though the JSON type remains a number. Clients may keep running while displaying wrong monetary amounts. Semantic changes are sometimes more dangerous than type changes because errors do not fail loudly right away.

### 10.3. Keeping Contracts Independent

If both `/v1/orders` and `/v2/orders` exist, each route must have a well-defined schema and behavior. Never let `/v1` return v2 responses just because the backend was refactored. You can share a common domain service or repository, while each version's adapter/mapper translates the domain model to its corresponding contract.

Example:

~~~text
HTTP /v1/orders
    -> V1 request mapper
    -> OrderQueryService
    -> V1 response mapper

HTTP /v2/orders
    -> V2 request mapper
    -> OrderQueryService
    -> V2 response mapper
~~~

This structure lets the team evolve internal models without forcing all clients to upgrade simultaneously. Avoid duplicating core business logic when two versions differ only in representation; keep shared business rules in the service/domain layer.

## 11. Deprecation and Version Lifecycle

When releasing v2, v1 clients do not necessarily stop working immediately. A clear migration process should include:

1. Announcing the new version and the reasons for change.
2. Providing migration guides with before/after request and response examples.
3. Announcing the planned end-of-support date and transition window.
4. Tracking requests by API version and client/application ID to see who still uses the old version.
5. Helping clients migrate and verifying behavior in staging/test environments.
6. Retiring the old version per published policy after impact assessment.

HTTP can use the `Deprecation` and `Sunset` headers to signal lifecycle status. `Deprecation` indicates the API is marked deprecated; `Sunset` can indicate when the resource is expected to become unavailable. Headers are only signals to clients; they do not replace announcements, documentation, and support plans.

Do not silently redirect v1 to v2 when semantics or schemas differ. Redirects can cause clients to receive incompatible responses or alter the HTTP method in certain cases. Once an old version is retired, respond according to published policy and direct clients to upgrade documentation.

## 12. Caching, Links, and Client Experience

### 12.1. Caching GET Responses

GET generally pairs well with HTTP caching when data and access permissions allow. The server can return an `ETag` derived from the page representation. Clients send `If-None-Match`; if the representation has not changed, the server returns `304 Not Modified` without resending the body.

Cache keys must account for factors that alter the response: path, query parameters, version header or media type, and user identity if responses are cached per user. With header versioning, consider `Vary: X-API-Version`. With content negotiation, consider `Vary: Accept`.

Never publicly cache responses containing private or tenant-specific data. Use `Cache-Control: private` or `no-store` per policy. Never let a CDN share a cache entry across two tenants simply because the URL and query string match.

### 12.2. Next-Page Links

If a response provides `links.next`, clients should follow that URL directly rather than manually assembling cursors and filters. This lets the server change cursor encoding or add parameters without forcing all clients to update.

A link must preserve the active version, filters, sort, and limit. Query parameters must be properly percent-encoded. Never put secret tokens or unnecessary personal data in URLs, as URLs appear in access logs, browser history, and analytics systems.

### 12.3. Never Assume a Next Page Always Exists

Clients must handle:

- `nextCursor` missing or `null`.
- Expired or invalidated cursors.
- A page returning `data: []` due to underlying data changes.
- Network errors or `429`/`503` while loading the next page.
- Users changing filters or sorting mid-traversal.

When filters or sorting change, clients should restart from the first page. Never reuse an old cursor for a new query unless the API explicitly defines that cursors work across that condition set.

## 13. Designing APIs for Serverless Environments

HTTP-triggered Java functions typically have short invocation lifecycles and can run concurrently across many instances. API design must account for platform constraints:

- **Page size limits:** enforce default and maximum limits so a single request cannot read excessive records.
- **Query timeouts:** set database/query timeouts; never let requests hang on unbounded counts or searches.
- **Connection pools:** function concurrency can scale faster than database connection capacity. Cap concurrency, reuse clients appropriately, and size pools within system limits.
- **Memory:** project only needed columns; avoid loading full entity graphs or serializing unnecessary relationships.
- **Cold starts:** keep initialization lightweight; avoid repeatedly creating database connections or loading expensive metadata if the platform allows safe reuse across invocations.
- **Rate limits and backpressure:** protect the database when many clients paginate concurrently or repeatedly request maximum page sizes.
- **Cost:** each page is an invocation and potentially one or more queries. Balance page size against invocation counts, execution duration, and data transfer.

If users need to download hundreds of thousands or millions of records, interactive pagination is often the wrong tool. Consider an asynchronous export job endpoint: the request initiates a job, a function/worker writes the file in batches, stores it in object storage, and notifies on completion. Clients download the generated file instead of holding an HTTP invocation open too long.

## 14. Documenting the Contract

OpenAPI specifications should clearly document:

- Methods, paths, and versions.
- Query parameters, data types, defaults, and bounds.
- Supported filters/sorts and how conditions combine.
- Response schemas for populated pages and final pages.
- That cursors are opaque tokens, how clients pass them back, and errors when invalid.
- HTTP statuses and error schemas.
- Supported, deprecated, and sunset dates for versions.
- Request/response examples for every common flow.

Do not just write `cursor: string`. Documentation must state that clients must not decode or alter the token, must send it alongside the exact server-issued filters/sort, and must restart if the query changes.

A strong contract example shows clients precisely what they can send, what they will receive, and how to handle error cases. This reduces reliance on ad-hoc coordination between the API team and each integrator.

## 15. Testing Pagination, Filtering, and Versioning

Testing only the happy path is insufficient. Cover the following cases:

- First page, middle page, final page, and empty result sets.
- Default `limit`, max `limit`, negative values, 0, and out-of-bounds values.
- Multiple records sharing the same sort key; verify tie-breakers produce deterministic order.
- Records inserted or deleted between offset/cursor requests.
- Tampered, expired, wrong-version cursors, or cursors paired with mismatched filters/sorts.
- Invalid filter enums, inverted date ranges, and repeated filter values.
- Non-allowlisted sort names and inputs containing special characters.
- Callers lacking permission for the requested tenant or customer.
- V1 and v2 returning their distinct schemas, errors, and semantics.
- V1 clients continuing to function after v2 is released.
- Caches not leaking responses across versions or tenants.
- Query plans and execution times remaining acceptable at deep offsets or large data volumes.

For cursor pagination, test records with identical timestamps to confirm no records are skipped or duplicated due to missing tie-breakers. For filters, test cases where filters narrow results to 0 rows. For versioning, contract tests catch unintended response regressions.

## 16. Self-Check

**Question 1.** Why should a list API not return all records at once?

**Answer hint:** Large responses increase memory usage, processing time, data transfer cost, and database load. Pagination bounds work per request and lets clients fetch data on demand.

**Question 2.** How do offset and cursor differ when new data is continuously inserted?

**Answer hint:** Offset is position-based, so newly inserted rows ahead of the current position shift pages and cause duplicates/skips. Cursors rely on the sort key of the last record, making them far less affected by new rows inserted ahead of the anchor, though they still do not create a true snapshot.

**Question 3.** Why must a cursor contain all sort keys and be signed?

**Answer hint:** All sort keys uniquely pinpoint the continuation boundary even when multiple records share identical values. Signing detects tampered tokens before their values are used in queries.

**Question 4.** Why must sort fields from query strings never be concatenated directly into SQL?

**Answer hint:** Bind parameters protect values, not column names or expressions concatenated into SQL statements. Field/direction allowlists and parameterized queries for values are both required.

**Question 5.** When does an API change require a new version?

**Answer hint:** When the change can break clients—such as removing/renaming fields, changing types or semantics, adding required request fields, or changing response structure or pagination/filter semantics. Adding optional fields may be compatible, though strict clients must still be verified.

**Scenario exercise:** An order API currently uses `/v1/orders`, returns `total` as a number, and paginates with offset. Record counts have grown to tens of millions; mobile clients want feed-style "load more" traversal; the product team also wants to return money as `{value, currency}`. Propose the v2 contract, pagination style, sorting rules, client migration strategy, and required tests.

**Hint:** V2 can use cursor/keyset pagination with deterministic ordering `createdAt DESC, id DESC`, returning `nextCursor` and `hasMore`, while representing money as an object. V1 retains its old semantics and responses during the transition period. V2 should cap limits, sign cursors bound to filters/sort/tenant, document errors, monitor v1 usage, and announce a sunset date. Test cursors with duplicate timestamps, mutations between pages, tenant authorization, per-version schemas, and client behavior on expired cursors.

## Conclusion

Pagination bounds the work performed per request; filtering and sorting define the dataset and deterministic order; API versioning enables controlled contract evolution. Offset is simple and suits moderate datasets or arbitrary page jumps. Cursor/keyset pagination is usually better suited for large sequentially traversed datasets, provided sort keys are deterministic and tokens are verified. In Java serverless applications, enforce query limits, protect databases against concurrency spikes, authorize every page, and maintain clear contracts for each API version.
