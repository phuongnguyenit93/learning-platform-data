# Designing Pagination APIs, Cursors, and Access Limits

A search API must clearly specify how many results a user can retrieve, in what order, and how to continue from their current position. With Spring Data Elasticsearch, pagination choices directly affect cluster performance, result consistency, and API security. An endpoint that allows huge page numbers, unbounded page sizes, or tamperable cursors creates both system load risks and out-of-scope data access risks.

Good design starts from the API contract: use page numbers when jumping to pages within a small window; use cursors when users only need to move forward; use PIT combined with `search_after` when traversing a stable snapshot; and use dedicated batch processes for exports. Every option needs limits on page size, processing time, query complexity, and the data scope the principal is permitted to see.

This lesson explains how to design pagination and cursor APIs in Spring Data Elasticsearch, covering response contracts, offset pagination, `search_after`, Point in Time (PIT), secure cursor tokens, tenant/authorization binding, access limits, testing, and operations.

## 1. Start from API needs

Before choosing a technique, identify how users need to navigate results.

| Need | Typically suitable API style |
|---|---|
| Jump to a specific page number | Bounded page number with `from/size` |
| View first few pages of a list | Page number |
| Next or Load more button | Cursor pagination |
| Traverse large dataset requiring a snapshot | PIT + `search_after` |
| Export or process all results | Batch job with cursor/PIT or suitable mechanism |
| Only aggregate numbers needed | Aggregation without loading unnecessary hits |

Do not choose cursors simply because they seem modern. If the UI needs to jump from page 2 to page 30, page numbers may fit better within a small bound. Conversely, if users only scroll continuously through results, cursors avoid large offsets and eliminate calculating page numbers.

Also determine whether results can change while users paginate. Continuously updated lists may need snapshots; slowly changing lists can accept simpler semantics.

## 2. Defining request and response contracts

A page-number API might accept:

~~~http
GET /api/products?q=keyboard&page=0&size=20&sort=createdAt,desc
~~~

Example response:

~~~json
{
  "items": [
    {
      "id": "p-1001",
      "name": "Mechanical Keyboard"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 135,
  "totalPages": 7,
  "hasNext": true,
  "hasPrevious": false
}
~~~

A cursor API might accept an optional cursor:

~~~http
GET /api/products?q=keyboard&limit=20
~~~

Response:

~~~json
{
  "items": [
    {
      "id": "p-1001",
      "name": "Mechanical Keyboard"
    }
  ],
  "nextCursor": "opaque-token",
  "hasNext": true
}
~~~

Next request:

~~~http
GET /api/products?cursor=opaque-token&limit=20
~~~

Cursors should be treated as opaque tokens. Clients simply store and resend them without needing to know about internal sort values, PIT IDs, or query fingerprints.

The API contract must specify:

- Whether page numbers start at 0 or 1.
- Default and maximum size.
- Allowed sort fields.
- Default sort direction.
- How long cursors remain valid.
- Whether cursors are bound to filters and principal.
- What error the API returns when a cursor is expired or invalid.
- Whether total hit counts are exact or approximate.
- Whether data across pages provides snapshot consistency.

Do not force clients to guess semantics from Elasticsearch implementation details.

## 3. Bounding page size at the API layer

Never accept an arbitrary `size` from clients and pass it straight to Elasticsearch. A massive size request can produce heavy responses, consume heap, spike network traffic, and prolong processing time.

Example policy:

- Default page size: 20.
- Maximum page size: 100.
- Non-negative page number.
- Accept only allowlisted sort fields.
- Cap search keyword length.
- Limit filter count and query complexity.
- Configure timeouts at both the API and Elasticsearch client.

A validation helper:

~~~java
public Pageable validatePageRequest(
        int page,
        int size,
        Sort sort) {

    int defaultSize = 20;
    int maxSize = 100;

    if (page < 0) {
        throw new InvalidPageRequestException("Page must be non-negative");
    }

    int effectiveSize = size <= 0 ? defaultSize : size;

    if (effectiveSize > maxSize) {
        throw new InvalidPageRequestException("Page size is too large");
    }

    Sort safeSort = validateSort(sort);

    return PageRequest.of(page, effectiveSize, safeSort);
}
~~~

If the API prefers rejecting zero or negative `size` rather than substituting the default, specify and test that behavior explicitly. Avoid silently clamping an invalid request into a different request if clients need to know about limits.

## 4. Computing offsets safely

For page numbers, offset is computed as:

\[
from = page \times size
\]

Use a sufficiently wide numeric type when checking bounds to avoid integer overflow:

~~~java
long from = (long) page * size;
long window = from + size;

if (window > maxResultWindow) {
    throw new DeepPaginationNotSupportedException();
}
~~~

If two `int` values are multiplied before assigning to `long`, multiplication can overflow before widening. Always cast before multiplying.

Example with a max result window of 10,000 and size 20:

| Page (zero-based) | from | from + size | Result |
|---:|---:|---:|---|
| 0 | 0 | 20 | Allowed |
| 10 | 200 | 220 | Allowed |
| 100 | 2,000 | 2,020 | Allowed |
| 499 | 9,980 | 10,000 | Allowed |
| 500 | 10,000 | 10,020 | Rejected or switched to cursor |

API limits should be explicitly configured. Elasticsearch has an `index.max_result_window` setting, commonly defaulting to 10,000, though applications may pick a lower threshold.

## 5. Never let page numbers become an overload vector

A client might send `page=999999999` or `size=1000000`. If the API forwards the request straight to Elasticsearch, the application lets users control query cost.

You should:

- Validate page and size before building queries.
- Limit page depth per API contract.
- Enforce rate limits per principal or client.
- Set timeouts.
- Limit query complexity and filter count.
- Record requests rejected due to deep pagination.
- Never auto-retry when the error is result window exceeded.

If the API serves multiple indices with different `max_result_window` values, do not expose raw per-index settings to clients. Define a consistent API limit or select policies per endpoint type.

## 6. Offset pagination in Spring Data Elasticsearch

With repositories supporting `Pageable`:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("productId")
        )
);

Page<Product> result =
        productRepository.findByStatus("ACTIVE", pageable);
~~~

With `ElasticsearchOperations` and `NativeQuery`:

~~~java
Query query = NativeQuery.builder()
        .withQuery(q -> q.term(t -> t
                .field("status")
                .value("ACTIVE")
        ))
        .withPageable(PageRequest.of(0, 20))
        .build();

SearchHits<Product> hits =
        operations.search(query, Product.class);
~~~

`Pageable` translates into offset and size in the search request. Consequently, large page numbers can still exceed `max_result_window`.

Repository signatures and `NativeQuery` builders vary by Spring Data Elasticsearch version. Verify actual APIs in your project dependencies, especially when combining custom queries, sorts, and `Pageable`.

## 7. Sorting must be server-controlled

Never accept an arbitrary field name from clients and pass it straight into sorting. Allow only fields designed for sorting with compatible mappings.

Example allowlist:

~~~java
private static final Map<String, String> ALLOWED_SORT_FIELDS = Map.of(
        "createdAt", "createdAt",
        "price", "price",
        "name", "name.keyword"
);
~~~

Validation:

~~~java
public Sort validateSort(String field, String direction) {
    String mappedField = ALLOWED_SORT_FIELDS.get(field);

    if (mappedField == null) {
        throw new InvalidSortException("Unsupported sort field");
    }

    Sort.Direction sortDirection =
            Sort.Direction.fromString(direction);

    return Sort.by(new Sort.Order(sortDirection, mappedField));
}
~~~

An allowlist prevents errors from sorting on `text` fields, fields without doc values, or sensitive fields that should not be exposed. It also blocks clients from issuing expensive queries by sorting on fields never meant for that use case.

For multi-field sorting, the server should define complete sort orders rather than letting clients submit an unbounded arbitrary list.

## 8. Use a tie-breaker for deterministic ordering

If multiple documents share the same sort value, ordering among them is not guaranteed to be stable. This matters especially during pagination.

For example, sorting only by `createdAt`:

~~~json
"sort": [
  { "createdAt": "desc" }
]
~~~

If multiple documents share the same timestamp, a hit may shift positions between searches. Add a unique tie-breaker:

~~~json
"sort": [
  { "createdAt": "desc" },
  { "productId": "asc" }
]
~~~

`productId` should have a `keyword` mapping and be unique within the result scope. When searching across multiple tenants, ensure the tie-breaker is globally unique across results or include `tenantId`.

Do not rely on Elasticsearch's default ordering when sort values tie. With PIT, Elasticsearch may append an internal tie-breaker like `_shard_doc` in certain flows, yet the API must still preserve exact sort values from responses.

## 9. Why do cursors fit next-page APIs?

Offset pagination says "skip the first N results". Cursor pagination says "continue after the last result I received".

With `from/size`, page 1,000 may require Elasticsearch to process 20,000 intermediate hits even though the client receives only 20. With `search_after`, the client sends the sort values of the last hit to resume from that position.

Cursors fit when:

- The UI uses Next or Load more.
- Results can exceed `max_result_window`.
- Arbitrary random page jumping is unnecessary.
- Sorting is deterministic and stable.
- Clients can store the cursor for the next request.

Cursors do not automatically guarantee snapshot consistency. If data changes between requests, either use PIT or accept semantics where new data may appear or shift positions.

## 10. search_after in Elasticsearch

First page:

~~~http
POST /products/_search
{
  "size": 20,
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Suppose the last hit on the page has sort values:

~~~json
[
  "2026-11-13T08:30:00Z",
  "p-020"
]
~~~

Next page:

~~~http
POST /products/_search
{
  "size": 20,
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "search_after": [
    "2026-11-13T08:30:00Z",
    "p-020"
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Subsequent requests must preserve the exact same query and sort semantics. The cursor taken from the last hit must retain all sort values in the exact order and data types.

Do not fabricate a cursor from `productId` alone when the sort includes both `createdAt` and `productId`. Do not flip sort directions between requests. Do not substitute client-computed values for the sort values returned by Elasticsearch.

## 11. PIT when a consistent snapshot is required

When an index changes while a user paginates, `search_after` alone does not guarantee every page comes from the same snapshot. **Point in Time (PIT)** preserves a consistent view for a specified duration.

Flow:

~~~text
Client                  API                    Elasticsearch
  |                      |                           |
  | GET first page       |                           |
  |--------------------->| Open PIT                  |
  |                      |-------------------------->|
  |                      |<--------------------------|
  |                      | Search with PIT           |
  |                      |-------------------------->|
  |                      |<--------------------------|
  |<---------------------| items + nextCursor        |
  |                      |                           |
  | GET next page        |                           |
  |--------------------->| Search with PIT + after   |
  |                      |-------------------------->|
  |                      |<--------------------------|
  |<---------------------| items + nextCursor        |
  |                      |                           |
  | Close / expiry       | Close PIT                 |
  |                      |-------------------------->|
~~~

Open PIT:

~~~http
POST /products/_pit?keep_alive=1m
~~~

Search with PIT:

~~~http
POST /_search
{
  "size": 20,
  "pit": {
    "id": "PIT_ID",
    "keep_alive": "1m"
  },
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

The next page uses the latest PIT ID if the response returns a refreshed ID and passes `search_after` from the last hit. When finished, close the PIT:

~~~http
DELETE /_pit
{
  "id": "PIT_ID"
}
~~~

PIT retains search contexts and consumes resources. `keep_alive` should be just long enough for users to reasonably continue; close PIT upon completion and ensure expiration handles abandoned sessions.

## 12. Designing opaque cursor tokens

Do not make clients submit raw JSON containing PIT IDs, sort values, indices, and queries. Instead, return an opaque token.

A cursor can represent an internal payload:

~~~json
{
  "version": 1,
  "pitId": "PIT_ID",
  "searchAfter": [
    "2026-11-13T08:30:00Z",
    "p-020"
  ],
  "queryHash": "sha256-of-normalized-query",
  "sort": [
    "createdAt:desc",
    "productId:asc"
  ],
  "tenantId": "tenant-a",
  "subject": "alice",
  "expiresAt": "2026-11-13T09:00:00Z"
}
~~~

This illustrates an internal structure, not a mandatory format. The API can:

- Encode and sign the payload with HMAC or digital signatures.
- Encrypt the payload if its contents must remain confidential.
- Use a random token pointing to server-side stored state.
- Combine random tokens with state in Redis or a database.

Signing detects tampering but does not hide contents. If tokens contain PIT IDs or internal details, use authenticated encryption or server-side state. Never treat Base64 as encryption or protection.

## 13. Binding cursors to queries and filters

A cursor is valid only for the query that produced it. If a user gets a cursor for keyword `keyboard` and sends it back with keyword `monitor`, the backend must not reuse the old cursor for the new query.

Build a query fingerprint from normalized components:

- Search text after validation/normalization.
- Business filters.
- Sort field and direction.
- Tenant scope.
- Parameters affecting results.
- Query/API version.

Do not hash an unnormalized raw query string if filter ordering can change without altering semantics. Serialize a canonical structure instead.

When receiving a cursor, the backend reconstructs the query from the validated request, computes the fingerprint, and compares it against the cursor's fingerprint. If they mismatch, return an invalid-cursor error or require starting a new search session.

Never trust a client-supplied query hash. Fingerprints must be computed server-side.

## 14. Binding cursors to principals and tenants

In multi-tenant systems, a cursor must remain scoped to the data its creator is permitted to see.

For example, Alice in `tenant-a` gets a cursor. Bob in `tenant-b` must not be able to use Alice's cursor to continue reading `tenant-a` results.

Cursor state should bind to:

- Authenticated subject or user ID.
- Tenant ID from the principal or authorized context.
- Role/permission scope if permissions affect the result set.
- Query fingerprint.
- Expiration timestamp.
- Policy version if needed.

Every continuation request must still authenticate and authorize the current principal. A cursor is not an access token and does not replace JWTs/sessions.

If user permissions change while a cursor is still valid, the application may need to check a permission version or re-authorize each request. Never rely on permissions captured at cursor creation if policy requires immediate revocation.

## 15. Never let cursors pick arbitrary indices or tenants

Never put client-controlled index names, aliases, or tenant IDs into Elasticsearch requests without validation. A modified cursor could become a vector for accessing another index or tenant.

The server should:

1. Verify the cursor signature/state.
2. Check expiration.
3. Authenticate the current principal.
4. Obtain tenant scope from the security context.
5. Verify the cursor matches the subject/tenant.
6. Reconstruct queries and filters from server policies.
7. Select the index/alias from server configuration.
8. Use `search_after` values and PIT ID only after the token is verified.

Even when a cursor is signed, the query must still include the server-side tenant filter. Never treat a valid token as an excuse to skip authorization.

## 16. Expiration, cancellation, and cursor lifecycle management

Cursors/PITs should not live forever. Define:

- Cursor TTL.
- PIT `keep_alive`.
- Maximum active cursors/PITs per user or tenant.
- How PIT is closed when the user finishes.
- State cleanup when cursors expire.
- Handling when PIT has already expired in Elasticsearch.
- Handling when an index alias switches to a new index.

Server-side cursor state should have TTLs and cleanup jobs. If clients create many cursors without using them, enforce caps to avoid holding excessive PIT contexts.

You can close PIT when the API knows the user is done, though in stateless HTTP flows the server rarely knows when a client abandons paging. TTLs are essential guardrails; an optional close endpoint supports early release.

## 17. Cursor responses do not need exact total counts

A cursor API typically only needs to know whether another page exists. You can request `size + 1` hits:

1. Request Elasticsearch `size = pageSize + 1`.
2. If more than `pageSize` hits arrive, set `hasNext = true`.
3. Return only the first `pageSize` items.
4. Build the next cursor from the last hit actually returned.
5. If no extra item arrives, set `hasNext = false`.

For example, with page size 20, request 21 hits. If 21 arrive, return 20 and report `hasNext = true`.

Take the cursor from the 20th hit, not the 21st lookahead hit. Using the 21st hit would skip that document on the next request.

The `size + 1` pattern avoids exact total counts in many use cases. However, with PIT and `search_after`, maintain proper snapshot and sort semantics for the lookahead as well.

## 18. track_total_hits and total count policies

Exact total hits can be expensive, especially for complex queries or large datasets. Elasticsearch supports `track_total_hits` to control counting.

~~~http
POST /products/_search
{
  "track_total_hits": false,
  "size": 20,
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

Or cap the counted threshold:

~~~json
"track_total_hits": 10000
~~~

When exact totals are not requested, responses can return a `gte` relation instead of `eq`. The API should represent this explicitly:

~~~json
{
  "total": {
    "value": 10000,
    "relation": "gte"
  }
}
~~~

Do not label this total as exact when the relation is `gte`. If the UI only needs `hasNext`, `size + 1` usually suffices.

Page-number APIs may need `totalPages`, whereas cursor APIs usually do not. Choose based on real UX needs instead of computing exact totals by default on every endpoint.

## 19. Access limits go beyond page size

A safe pagination API controls multiple dimensions:

| Limit | Goal |
|---|---|
| page size | Bound returned hits |
| max offset | Prevent deep pagination |
| query timeout | Bound processing time |
| rate limit | Limit request frequency |
| concurrent search limit | Prevent one principal from opening too many searches |
| filter complexity | Bound number/types of conditions |
| sort allowlist | Sort only on supported fields |
| aggregation limit | Bound buckets and complexity |
| cursor TTL | Limit state retention duration |
| PIT quota | Limit search contexts |
| response byte limit | Prevent oversized payloads |
| export quota | Control long jobs and large datasets |

A small page size is insufficient if a client can fire thousands of concurrent requests or request aggregations with millions of buckets.

## 20. Rate limits and concurrency limits

Rate limits control request volume over time; concurrency limits control simultaneously executing requests.

They can be applied per:

- User/principal.
- Tenant.
- API key/client application.
- Endpoint or query type.
- Global cluster capacity.

Example policy:

- Standard search: 60 requests/minute/user.
- Cursor continuation: 120 requests/minute/user.
- Export: 2 concurrent jobs/tenant.
- Open PITs: capped at a small number per user.

These numbers are purely illustrative. Real values must match load and SLOs.

When rate limits are exceeded, APIs can return HTTP 429 Too Many Requests with `Retry-After` if appropriate. When concurrency limits are exceeded, return 429 or 503 per semantics. Clients should not immediately retry without honoring backoff.

## 21. Limiting aggregations and query complexity

Even a `size=20` request can be very expensive if aggregations have many branches, high-cardinality `terms`, or deep nested aggregations.

The API should control:

- Number of allowed aggregations.
- Maximum `terms` size.
- Composite page size.
- Nested aggregation depth.
- Number of queryable fields.
- Bounded wildcard/regexp/fuzzy queries.
- Script queries restricted strictly to controlled use cases.
- Timeouts and circuit breaker behavior.

Never accept raw Query DSL from clients on a public API unless backed by strict validation/authorization. Exposing well-defined business schema parameters and building queries on the backend is safer.

## 22. Limiting response payloads

Page size alone does not capture full response size. A hit might contain long descriptions, large nested objects, or many highlight fragments.

You can bound:

- Returned fields via DTOs/source filtering.
- Text field sizes.
- Highlight fragment counts.
- Fragment sizes.
- Aggregation bucket counts.
- Total response bytes.
- Offloading exports to files/jobs instead of synchronous responses.

Never return full Elasticsearch `_source` when the API only needs a few fields. DTOs stabilize contracts and prevent leaking internal metadata.

## 23. Page-number controller example with WebFlux

A controller can validate page/size and return a DTO:

~~~java
@GetMapping("/products")
public Mono<ProductPageResponse> search(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam String q,
        @AuthenticationPrincipal Jwt jwt) {

    String tenantId = jwt.getClaimAsString("tenant_id");

    Pageable pageable =
            paginationPolicy.validate(page, size, "createdAt", "desc");

    return productSearchService.searchPage(tenantId, q, pageable)
            .map(ProductPageResponse::from);
}
~~~

The service must always attach the tenant filter:

~~~java
public Mono<ProductPageResponse> searchPage(
        String tenantId,
        String text,
        Pageable pageable) {

    Query query = buildTenantScopedQuery(tenantId, text, pageable);

    return operations.searchForPage(query, Product.class)
            .map(ProductPageResponse::from);
}
~~~

Method names like `searchForPage` and converting `SearchHits` to `Page` depend on API/version; the example illustrates architecture. The essential point is that `tenantId` comes from the principal, `Pageable` is validated, and the query is constructed server-side.

## 24. Response DTO example for page-number APIs

~~~java
public record ProductPageResponse(
        List<ProductView> items,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean hasNext,
        boolean hasPrevious
) {
    static ProductPageResponse from(Page<Product> page) {
        return new ProductPageResponse(
                page.getContent().stream()
                        .map(ProductView::from)
                        .toList(),
                page.getNumber(),
                page.getSize(),
                page.getTotalElements(),
                page.getTotalPages(),
                page.hasNext(),
                page.hasPrevious()
        );
    }
}
~~~

DTOs should use explicit data types and omit full entities when entities carry internal fields. With reactive repositories, `Page` may be wrapped in `Mono`; mapping works similarly while preserving the reactive publisher end-to-end.

## 25. Cursor service example

A cursor service can break work into clear steps:

~~~java
public Mono<ProductCursorPage> searchNext(
        SearchRequest request,
        Authentication authentication) {

    return cursorService.resolveAndValidate(
                    request.cursor(),
                    request.filters(),
                    authentication
            )
            .flatMap(state ->
                    elasticsearchSearch.search(
                            state.query(),
                            state.pitId(),
                            state.searchAfter(),
                            request.limit() + 1
                    )
                    .map(response ->
                            cursorService.toPage(
                                    response,
                                    state,
                                    request.limit()
                            )
                    )
            );
}
~~~

This illustrates structure only. The cursor service must verify signature/state lookup, principal, tenant, query fingerprint, sort, and expiration before calling Elasticsearch.

Do not let controllers parse tokens and assemble queries themselves. Separating responsibilities allows security and pagination to be tested independently.

## 26. Packaging cursors and signing tokens

If state is stored inside the token, a common pattern serializes canonical payload and signs with HMAC:

~~~text
payloadBytes = UTF8(canonicalJson(cursorState))
signature = HMAC_SHA256(secretKey, payloadBytes)
token = base64url(payloadBytes) + "." + base64url(signature)
~~~

Upon receiving a token:

1. Split payload and signature.
2. Recompute HMAC from payload.
3. Compare signatures using constant-time comparison.
4. Parse payload only after signature verification passes.
5. Check version and expiration.
6. Check subject/tenant/query binding.
7. Execute continuation search.

HMAC provides integrity/authenticity, not confidentiality. Token holders can still read the payload if only Base64URL encoded. If the payload contains PIT IDs or internal metadata, use authenticated encryption or server-side state.

Secret keys must be managed via a secret manager/secure configuration, with rotation plans and key IDs if multiple keys must be supported during transitions.

## 27. Server-side opaque cursors

Another approach generates a high-entropy random token and stores state in Redis or a database:

~~~text
cursor token -> server-side state
                 - PIT ID
                 - search_after
                 - query fingerprint
                 - subject / tenant
                 - expiresAt
~~~

Advantages:

- Clients never see PIT IDs or sort values.
- Cursors can be revoked.
- Open cursor counts can be controlled.
- PITs can be closed when state is deleted or expires.

Drawbacks:

- Requires storage and cleanup.
- Every continuation request needs a state lookup.
- State store availability must be handled.
- Race conditions must be avoided if the same cursor is used concurrently.

Tokens should be random, non-sequential, and never contain user IDs directly. The state store needs TTLs and record caps to defend against cursor-creation abuse.

## 28. Handling invalid, expired, and missing-PIT cursors

The API should distinguish failure cases:

| Situation | Recommended API behavior |
|---|---|
| Malformed token / bad signature | 400 Invalid cursor |
| Expired cursor | 410 Gone or 400 per contract |
| Cursor belongs to another user/tenant | 403 or 404 per policy |
| Query/filter mismatch | 400 Cursor does not match request |
| Expired PIT | 410 Restart search |
| Incompatible index/alias switch | Require starting a new search |
| State store unavailable | 503 Service Unavailable |

Never return raw PIT IDs, index names, Query DSL, or stack traces in error bodies.

When a PIT expires, never silently open a new PIT and resume with old `search_after` values. A new PIT sees a different snapshot; results can duplicate or skip. Require clients to start a new search session or follow an explicit recovery strategy.

## 29. Access control and tenant isolation on every page

Tenant filters must be enforced on every search request, including cursor continuations. Never assume that a valid cursor bypasses re-authorization on subsequent requests.

On every continuation:

- Authenticate the access token/session.
- Obtain tenant from the current principal.
- Verify cursor ownership matches subject/tenant.
- Check current roles/permissions.
- Reconstruct the query with the tenant filter.
- Use verified PIT/`search_after`.
- Return only permitted DTOs.

If a user loses permissions between pages, policy must dictate whether continuation proceeds. For sensitive permissions, re-authorize every request and consider embedding a permission version in cursors to invalidate stale ones.

## 30. Do not let clients control sort values or Query DSL

Clients should only send allowlisted business parameters:

~~~http
GET /products?q=keyboard&sort=price,asc&limit=20
~~~

The backend maps `sort=price` to the controlled `price` field. The cursor holds sort values returned by Elasticsearch.

Never take raw sort JSON or raw Query DSL from clients and forward it straight to the cluster. If internal users need flexible query builders, enforce strict parsers/allowlists and complexity bounds.

Fields such as `tenantId`, `ownerId`, `internalCost`, `permissions`, or index routing must never be client-selectable to alter query scope.

## 31. Protecting cursors from replay and unintended sharing

A valid cursor could be copied to another device or user. Binding cursors to subject/tenant and expiration limits sharing.

Depending on use case, you can:

- Allow reuse by the same user.
- Enforce single-use tokens when stateful continuation is required.
- Bind tokens to session/device if policy dictates.
- Limit continuation count.
- Revoke cursors on logout or permission changes.
- Avoid logging full cursor tokens in logs/analytics.

Do not over-constrain tokens if the product must support users opening multiple tabs or retrying network requests. Pick appropriate semantics and test concurrent continuations.

If the same cursor is submitted concurrently, stateful cursors may need optimistic locking or versioning to avoid closing PIT prematurely or corrupting state updates.

## 32. Caching and cursors

If search responses are cached, cache keys must include every factor affecting results:

- Query fingerprint.
- Tenant.
- Principal/permission scope if field visibility differs.
- Sort.
- Cursor or `search_after` position.
- Page size.
- Snapshot/PIT context when consistency is required.

Never cache a response by keyword alone when different tenants see different datasets.

Cursor state should likewise never be shared across requests just because query strings match. Two users searching `keyboard` may still hold different permissions.

## 33. Exports should not be a gigantic page size

A "download all products" requirement must never be implemented by letting clients send `size=1000000` or `page=50000`.

Build an export job instead:

1. Verify export permission.
2. Obtain tenant and filters from principal/policy.
3. Create a job bounded by record count and duration.
4. Traverse data via PIT + `search_after` or suitable batch mechanisms.
5. Write output via streaming/batching.
6. Track status and progress.
7. Issue a time-limited download link.
8. Verify permissions upon file download.
9. Clean up PIT, temporary files, and job state after retention.

Exports can have separate quotas per tenant and role. Never hold an HTTP connection open for hours generating large files.

## 34. Error handling and HTTP semantics

Common status codes:

| Status | Meaning |
|---|---|
| 400 | Invalid page/size/sort/cursor format |
| 401 | Unauthenticated |
| 403 | Unauthorized |
| 404 | Resource/cursor state missing or hidden per policy |
| 410 | Cursor/PIT expired |
| 422 | Syntactically valid parameters violating policy, if API uses this semantic |
| 429 | Rate limit or quota exceeded |
| 503 | Elasticsearch/state store temporarily unavailable |
| 504 | Gateway/API timeout |

Choose status codes consistently with your contract and framework. Never return 200 with an empty list when a request was actually rejected for deep pagination; clients would misinterpret it as zero results.

Error bodies should carry a stable error code, safe message, and correlation ID:

~~~json
{
  "code": "CURSOR_EXPIRED",
  "message": "Search session has expired. Start a new search.",
  "requestId": "req-123"
}
~~~

Never include raw Elasticsearch exceptions or tokens in responses.

## 35. Observing and operating pagination

Monitor:

- Search request counts and p50/p95/p99 latency.
- Page size distribution.
- Offset depth distribution.
- Requests rejected for max window.
- Cursor created/continued/expired/invalid counts.
- Open PIT count and PIT age.
- Rate limit and concurrency rejections.
- Search timeouts and 429s.
- Response byte sizes.
- Exact total hits request rate.
- Aggregation bucket counts.
- Cursor state store hits/misses/errors.

Metric tags should keep low cardinality. Never put cursor tokens, document IDs, or user IDs directly into metric labels. Use masked structured logs/traces for investigating specific requests.

Alert when PIT counts spike abnormally, cursor state fails to clean up, deep-page requests surge, or p95 search latency breaches SLOs.

## 36. Testing page-number limits

Unit-test validation:

~~~java
@Test
void rejectsPageBeyondResultWindow() {
    assertThatThrownBy(() ->
            policy.validate(page(500), size(20))
    ).isInstanceOf(DeepPaginationNotSupportedException.class);
}
~~~

Integration tests against Elasticsearch should create a test index with a small `max_result_window`, e.g., 100:

- `from=80, size=20` must succeed.
- `from=81, size=20` must be rejected.
- `from=0, size=101` must be rejected.
- The API must return the expected error contract.
- Do not retry the same out-of-bounds request.

Do not test only the helper; verify the real query is sent with validated offset/size.

## 37. Testing cursor tamper resistance

For HMAC-signed cursors, tests must verify:

- Valid tokens are accepted.
- Modifying a single payload byte is rejected.
- Modifying the signature is rejected.
- Malformed tokens are rejected.
- Unsupported token versions are rejected.
- Expired tokens are rejected.
- Payloads are not parsed before signature verification succeeds.
- Error responses do not leak secrets or internal payloads.

For stateful cursors, also test nonexistent random tokens, expired TTL state, revoked state, and state store failures.

## 38. Testing cursor binding to users and tenants

Create Alice in `tenant-a` and Bob in `tenant-b`:

1. Alice starts a search and receives a cursor.
2. Alice continues with the cursor: succeeds.
3. Bob sends Alice's cursor: rejected.
4. Alice changes query/filters while reusing the old cursor: rejected.
5. Alice changes sort while reusing the old cursor: rejected.
6. Alice loses permissions and continues: behaves per revocation policy.
7. Cursor expires: API instructs starting a new search.

Tests must verify responses never leak another tenant's data, including via error details or metadata.

## 39. Testing PIT lifecycle

Integration tests should verify:

- The first page creates or uses PIT properly.
- The cursor references the right PIT state.
- Subsequent pages use the latest PIT ID if the response rotates IDs.
- PIT preserves the snapshot when new documents are indexed.
- Cursors fail once PIT expires.
- The close endpoint closes PIT.
- TTL cleanup releases state.
- A user cannot close another user's PIT with a forged cursor.
- Elasticsearch errors on expired PIT map to the proper error contract.

PIT is a cluster resource. Lifecycle tests must cover both success paths and cancellation/abandonment.

## 40. Testing pagination without duplicates or omissions

Build a fixed fixture with many documents sharing sort values, e.g., 257 products, page size 50.

For the cursor flow:

1. Fetch first page.
2. Record IDs.
3. Read `nextCursor`.
4. Continue until finished.
5. Verify total ID count equals fixture count.
6. Verify every ID is unique.
7. Verify the ID set equals the fixture set.
8. Verify global sort order.
9. Verify the last page has `hasNext=false` and null cursor per contract.

If using PIT, index a new document between pages and verify the active snapshot remains unchanged while a new search session sees the new document.

## 41. Testing rate limits and query complexity

Tests must prove limits are enforced:

- Exceeding request quotas returns 429.
- Responses include `Retry-After` if policy provides it.
- Quotas are tracked properly per user/tenant/client.
- One user cannot exhaust the entire tenant quota if quotas are isolated.
- Exports have separate quotas.
- Oversized aggregations are rejected.
- Non-allowlisted sort fields are rejected.
- Overly long or complex queries are rejected.
- Concurrent PITs beyond the limit do not open extra search contexts.

Concurrency tests should run under controlled conditions to avoid flakiness. Use fake clocks or test-mode rate limiters instead of real sleeps.

## 42. Common mistakes

| Symptom | Cause | Fix |
|---|---|---|
| API slow on deep pages | Large offset | Cap page depth or use cursors |
| Huge page sizes cause OOM | Unvalidated size | Default and max size |
| Unstable sort across pages | Missing tie-breaker | Add unique keyword field |
| Cursor works with different queries | No query fingerprint bound | Canonicalize and match query |
| Tenant A cursor works in tenant B | Missing principal/tenant binding | Bind subject/tenant and re-authorize |
| Cursors can be forged | Plain Base64 tokens | HMAC/AEAD or server-side state |
| Long-lived PITs accumulate | Missing TTL/close | Quotas, `keep_alive`, and cleanup |
| Next page skips an item | Taking cursor from lookahead hit | Take sort values from last returned hit |
| Old cursor resumes on new PIT | Silently opening replacement PIT | Require restarting search |
| Slow counts | Always requesting exact total | `track_total_hits` policy or `size+1` |
| Exports overload cluster | Using giant page size | Background batch jobs |
| Rate limits bypassed via multiple tokens | Limiting per token only | Limit by principal/tenant/client policy |
| Errors leak PIT/queries | Returning raw exceptions | Safe error DTOs |

## 43. Pagination API design process

1. Determine whether the UI needs page jumping or forward-only paging.
2. Choose `from/size` or cursors based on need.
3. Define default and maximum page sizes.
4. Compute offsets with overflow-safe arithmetic.
5. Allowlist sort fields and directions.
6. Add a unique tie-breaker.
7. Decide whether snapshot consistency is required.
8. If snapshots are needed, use PIT + `search_after`.
9. Design opaque cursors with signatures or server-side state.
10. Bind cursors to query, sort, principal, tenant, and expiration.
11. Re-authorize on every continuation request.
12. Set rate, concurrency, aggregation, and response limits.
13. Request exact totals only when needed.
14. Extract exports into background jobs/batches.
15. Write integration tests for limits, cursors, PIT, and tenant boundaries.
16. Monitor latency, cursor/PIT lifecycles, and rejected requests.

## 44. Design principles

- Page-number APIs suit small result windows and page jumping.
- Cursor APIs suit Next/Load more flows and large result sets.
- Never allow arbitrary page sizes or offsets.
- Compute `from` using `long` to avoid overflow.
- Use sort allowlists and deterministic tie-breakers.
- Use `search_after` to resume from the last hit's sort values.
- Use PIT when consistent snapshots are required.
- Cursors must be opaque, integrity-protected, or backed by server-side state.
- Bind cursors to query fingerprints, principals, tenants, and expirations.
- Re-authorize every request; never treat cursors as credentials.
- Manage PIT quotas, `keep_alive`, closing, and cleanup.
- Cap rates, concurrency, aggregation complexity, and response sizes.
- Do not request exact totals if UX does not need them.
- Offload exports to background jobs.
- Test both pagination boundaries and security boundaries.
- Never let error responses leak PIT IDs, internal queries, or sensitive data.

Designing pagination APIs for Spring Data Elasticsearch involves balancing UX, performance, and security. `from/size` fits moderate lists when bounded by offset and page size; `search_after` fits sequential navigation; and PIT preserves snapshots as data changes. Cursors must be tamper-resistant, bound to queries and principals, time-limited, and authorized on every request. Combining deterministic sorting, rate/concurrency/aggregation limits, response DTOs, and integration tests lets APIs serve large datasets without generating expensive queries or widening data access unintentionally.
