# Pagination Contracts

A pagination contract defines how clients split a collection into pages and continue reading subsequent pages. In GraphQL, pagination is not prescribed by the schema language itself; applications must publish arguments, response shapes, data ordering, size limits, and metadata semantics.

A well-designed contract tells clients how to move forward or backward without guessing from element counts. It also lets the server change databases and query strategies without coupling clients to offsets, SQL, or repository internals.

In Spring for GraphQL, the contract is declared in SDL; resolvers bind arguments using `@Argument` and pass them to application services. Services execute pagination per the contract and return connection/page DTOs. Never return Spring Data's `Page<T>` directly as part of the public API, because it is a persistence abstraction that can change across framework versions and does not express full GraphQL semantics.

## 1. What problem does pagination solve?

A query returning an entire collection can scale in cost with data volume:

~~~graphql
query {
    products {
        id
        name
    }
}
~~~

When a catalog holds tens of thousands of products, large responses increase query duration, memory usage, network transfer, and client rendering overhead. Pagination bounds the number of items returned in a single request.

A pagination contract needs to answer:

- How many items does the client request?
- From what position does the client start?
- How is item ordering determined?
- Are filters and sorting preserved across pages?
- How does the client tell whether a next page exists?
- Is a total item count provided, and is that number exact?
- How does the server handle invalid inputs or concurrent data changes?

If these rules are left undefined, two clients may interpret the exact same response in two different ways.

## 2. Choosing the right pagination style

Two common contracts are offset/page pagination and cursor/connection pagination.

| Criterion | Offset/page | Cursor/connection |
| --- | --- | --- |
| Input | `page`, `size` or `offset`, `limit` | `first`, `after` or `last`, `before` |
| Response | content and page metadata | `edges`, cursors, and `PageInfo` |
| Jumping to an arbitrary page | Easy, given a page number | Not a primary goal |
| Deep pages | Can be slow as the database must skip many rows | Usually steadier with keyset indexes |
| Data changing between requests | Inserts/deletes before the offset can duplicate or skip items | Less susceptible to shifts from inserts/deletes before the cursor |
| Total pages | Easy to compute if a count exists | Usually does not require a count |
| Client contract | Simple for data tables | Well suited for infinite scroll and forward/backward traversal |

There is no single best pagination style for every collection. Offset fits small admin tables with infrequent writes and a need to jump to specific pages. Cursors fit large collections, feeds, transaction histories, or infinite scrolling.

Do not expose both `page`/`size` and `first`/`after` on the same field merely to please every client style. The two styles have different semantics; if both are truly needed, name the fields distinctly and document why each contract exists.

## 3. Offset/page pagination contracts

Offset pagination typically uses `page` and `size`. Specify clearly whether `page` is 0-based or 1-based. Spring Data `PageRequest` uses 0-based page indices; if your public API uses 1-based pages, the resolver must convert explicitly.

Example contract:

~~~graphql
type Query {
    productsPage(page: Int = 0, size: Int = 20): ProductPage!
}

type ProductPage {
    items: [Product!]!
    pageInfo: OffsetPageInfo!
}

type Product {
    id: ID!
    name: String!
}

type OffsetPageInfo {
    page: Int!
    size: Int!
    hasNextPage: Boolean!
    totalElements: Int
    totalPages: Int
}
~~~

Published semantics should state:

- Whether `page` is zero-based or one-based.
- `size` is the maximum number of items the server returns.
- `pageInfo.page` reflects the applied page after validation.
- `pageInfo.size` is the actual page size.
- `hasNextPage` indicates whether more data exists after the current page.
- `totalElements`/`totalPages` may be null if the server does not compute a count.

If `totalElements` can exceed GraphQL `Int`'s signed 32-bit limit, do not silently use `Int`. Define a custom `Long`/`BigInt` scalar with clear coercing or omit exact counts.

Some APIs use `offset` and `limit` instead of `page` and `size`. If choosing this style, define `offset` as the number of skipped items, `limit` as the maximum items returned, and cap the maximum offset to prevent excessively deep queries.

## 4. Cursor/connection pagination contracts

Cursor pagination commonly follows the Relay Connection pattern. A connection contains `edges` and `PageInfo`; each edge holds a `node` and a `cursor`.

~~~graphql
scalar DateTime

type Query {
    products(
        first: Int = 20
        after: String
        filter: ProductFilter
        sort: ProductSort = CREATED_AT_DESC
    ): ProductConnection!
}

type Product {
    id: ID!
    name: String!
    createdAt: DateTime!
    availability: ProductAvailability!
}

type ProductConnection {
    edges: [ProductEdge!]!
    pageInfo: PageInfo!
    totalCount: Int
}

type ProductEdge {
    cursor: String!
    node: Product!
}

type PageInfo {
    hasNextPage: Boolean!
    hasPreviousPage: Boolean!
    startCursor: String
    endCursor: String
}

input ProductFilter {
    keyword: String
    categoryId: ID
    availability: ProductAvailability
}

enum ProductSort {
    CREATED_AT_DESC
    CREATED_AT_ASC
    NAME_ASC
}

enum ProductAvailability {
    IN_STOCK
    OUT_OF_STOCK
    PREORDER
}
~~~

In this contract, clients pass `first` to request a maximum number of edges and `after` to resume after a cursor returned from the previous page. `sort` is an enum so the server restricts ordering to supported options. `filter` describes the subset the client wants to traverse.

`Connection`/`Edge`/`PageInfo` fields are the public contract. Clients do not need to know whether the server uses SQL keyset predicates, Spring Data scrolling, or a search engine to fetch pages.

## 5. Choosing Relay Connection vs. a simpler response

Relay Connection is a widespread convention, especially when clients use Relay or need per-edge cursors. However, not every API must adopt the full Relay shape.

A simpler response could be:

~~~graphql
type ProductSlice {
    items: [Product!]!
    nextCursor: String
    hasNext: Boolean!
}
~~~

A simpler shape is convenient for APIs that only support forward pagination. On the other hand, it lacks per-edge cursors, does not express backward pagination by convention, and makes sharing generic pagination components harder.

Pick a shape matching your client ecosystem and apply it consistently across similar collections. Do not add `edges`/`pageInfo`/`totalCount` if clients do not need them, yet do not invent a different response shape for every collection field either.

## 6. Defining page sizes and server limits

Clients must never be allowed to request an unbounded number of items. The contract should define:

- Default value when the client omits page size.
- Minimum value.
- Maximum value.
- Behavior when page size is negative, zero, or exceeds the limit.
- Whether the server clamps the value or returns an error.

Example policy:

| Input | Behavior |
| --- | --- |
| `first` omitted | Use default 20 |
| `first = 1` | Return at most 1 edge |
| `first = 100` | Accepted if max is 100 |
| `first = 101` | Return `BAD_REQUEST` |
| `first = 0` | Reject or support per published contract |
| Negative `first` | Reject |

Both clamping and rejecting are viable, but never choose inconsistently across resolvers. Rejecting makes client errors explicit; clamping is friendlier, though clients need to know the server adjusted the page size. When clamping, metadata should report the effective page size so clients do not make false assumptions.

Capping page sizes is part of query cost protection. Combine it with query complexity limits, timeouts, rate limits, and caps on nested collections.

## 7. Rules for combining arguments

Cursor contracts must state which argument combinations are permitted:

| Arguments | Suggested rule |
| --- | --- |
| `first` without `after` | First page per sort/filter |
| `first` with `after` | Next page |
| `last` with `before` | Previous page if backward pagination is supported |
| `first` with `last` | Reject |
| `after` with `before` | Reject unless defined by contract |
| Cursor without page size | Use default or require page size per contract |

If full Relay-style forward/backward pagination is supported, clearly define the semantics of `first`/`after` and `last`/`before`. Do not accept `first` and `last` together without a clear reason.

For offset contracts, do not mix `page` with `offset` or `page` with cursors on the same field. If the API uses `page` and `size`, both need clear defaults and validation. If using `offset` and `limit`, specify offset units and maximum bounds.

## 8. Data ordering is part of the contract

Pagination makes no sense if item ordering is unstable. Every collection needs a deterministic sort order:

~~~graphql
enum ProductSort {
    CREATED_AT_DESC
    CREATED_AT_ASC
    NAME_ASC
}
~~~

Enum names describe the public ordering. The server must map each enum to a stable database ordering. For example, `CREATED_AT_DESC` can execute:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

`id` serves as a tie-breaker so records sharing the same `created_at` still have a deterministic order. The tie-breaker does not need to be exposed as a separate sort option in the schema.

Never accept arbitrary column names or SQL expressions from clients. Sorting must use an allowlist to prevent SQL injection and avoid unindexed query shapes.

If a sort field is nullable, specify `NULLS FIRST`/`NULLS LAST` and ensure keyset predicates/cursors follow that exact rule. For `NAME_ASC`, define collation/case sensitivity if clients rely on exact display ordering.

## 9. Filters must remain consistent across pages

When clients traverse a collection, every page must apply the same filter and authorization scope. If a client fetches page 1 with `categoryId = "c-1"`, then changes `categoryId` while reusing the old cursor, the cursor boundary may no longer be valid for the new dataset.

The contract should specify one of two rules:

1. Cursors are bound to the canonical filter and sort; changing filter/sort invalidates the cursor.
2. Cursors represent only the sort key and are applied to the new filter; these semantics are explicitly published.

The first approach is more predictable for clients. The server can store or encode a fingerprint of the filter/sort inside the cursor to detect out-of-scope cursor reuse. Page size may vary between requests if allowed by the contract; it is usually not part of the cursor identity.

Filters with default values must also canonicalize identically. For example, omitted `availability` and `availability = ALL` may carry identical or distinct semantics; decide before computing fingerprints.

## 10. Cursors as opaque contract tokens

Clients should treat cursors as opaque strings: take them from an edge and pass them back unchanged in `after`/`before`. Do not parse cursors, increment them, or synthesize them from IDs if the API does not publish a format.

Cursors usually contain enough information to pinpoint a position in the sort order, such as `createdAt` and `id`. They can carry a version so the server can change formats later. If cursors need tamper resistance, the server can sign the payload; Base64 is merely encoding, not encryption.

A cursor is not a credential and grants no access permissions. Even with a signed cursor, the server must enforce authorization and tenant scope on every request. Do not embed tokens, secrets, or unnecessary personal data inside cursors.

If a cursor is bound to a filter/sort, the server must verify the fingerprint and return an error with a stable code when a client sends a mismatched or unsupported-version cursor.

## 11. Meaning of PageInfo

`PageInfo` enables clients to navigate without inferring state from edge counts:

| Field | Semantics to publish |
| --- | --- |
| `hasNextPage` | At least one edge exists after the current page's last edge |
| `hasPreviousPage` | At least one edge exists before the current page's first edge |
| `startCursor` | Cursor of the first edge; null when there are no edges |
| `endCursor` | Cursor of the last edge; null when there are no edges |

Do not set `hasNextPage = edges.size() == first`. A page containing exactly `first` edges can still be the final page. Servers typically fetch one extra item (`n + 1`) or run an `EXISTS` check to determine whether more data remains.

If only forward pagination is supported, define how `hasPreviousPage` is computed. You can check with `EXISTS` under the filter/sort before the first position; do not blindly set it to `true` simply because `after` was passed if prior rows were deleted or scope changed.

For an empty connection, `edges` is an empty list and `startCursor`/`endCursor` are null. Never fabricate dummy cursors.

## 12. totalCount is not always necessary

`totalCount` is often added so the UI can show "N results." However, an exact count can be costlier than fetching a page—especially with complex filters, multi-table joins, or authorization predicates narrowing the dataset.

If `totalCount` is provided, define:

- Whether the count is exact or estimated.
- Whether the count reflects the current filter.
- Whether the count applies tenant/authorization scope.
- Whether the count can be null when the server skips computing it.
- Whether the count and `edges` share the same snapshot or may reflect slightly different timestamps.

Do not leave `totalCount` semantics ambiguous. A nullable field might mean "not computed" or "not authorized to view count"; distinguish those cases via contract/errors if clients care.

Never execute `COUNT(*)` just to compute `hasNextPage`. Fetching `n + 1` items is usually sufficient for forward navigation.

## 13. Data changing between requests

Pagination typically spans multiple HTTP requests, so database state can change between pages. The contract must clarify the consistency level clients can expect.

With offset pagination, inserts/deletes near the start of the list shift item positions and cause duplicates or skipped items. With cursor/keyset pagination, inserts before the cursor usually cause less disruption, though updating a sort key can move an item across page boundaries.

If business workflows require traversing a stable snapshot, you can use a watermark/snapshot token or a fixed dataset version. This incurs state-storage cost and requires token expiration. Do not promise snapshot consistency unless the backend actually provides it.

For continuously updated feeds, the contract can accept eventual traversal: new items appearing at the top of the feed become visible when the client refreshes from the start, while an active traversal continues from its existing cursor.

## 14. Pagination in nested fields

A single query can paginate both a root collection and multiple nested collections:

~~~graphql
query {
    customers(first: 10) {
        edges {
            node {
                id
                orders(first: 5) {
                    edges {
                        node {
                            id
                            items(first: 10) {
                                edges {
                                    node {
                                        productName
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
~~~

Each collection has its own cursors and `PageInfo`. A `customers` cursor cannot be used for `orders` or `items`. The contract should clarify per-collection page size caps, total items permitted in one operation, and query complexity limits.

Do not load an entire nested collection and slice it in Java. Resolvers should pass arguments down to query services/repositories so the database or downstream API performs pagination.

If a nested resolver queries the database/service once per parent, pagination still causes N+1 queries. Use batch loading over parent keys and ensure the batch API understands the corresponding filter, sort, and page arguments. Never merge pages from multiple parents under a cache key lacking parent identity.

## 15. Authorization and tenant scope

Every page must enforce the same access policy as an unpaginated query. Never allow a cursor or page number to bypass tenant, ownership, or visibility checks.

For example, `myOrders` should not accept an arbitrary `customerId` if the endpoint may only return orders of the current principal. The service must derive the customer/tenant from the security context and apply it to the query:

~~~java
@QueryMapping
public OrderConnection myOrders(
        @Argument Integer first,
        @Argument String after,
        Principal principal) {

    return orderQueryService.findVisibleOrders(
        principal, first, after);
}
~~~

If the API has an admin search allowing filtering by `customerId`, that is a separate use case from `myOrders` and needs separate authorization. A cursor generated by one user must never be usable to bypass the current user's scope.

If cursors contain filter fingerprints, do not put tenant secrets or access privileges into the payload. The server must still extract the tenant from the principal and verify permissions.

## 16. Validation and error contracts

Pagination arguments are public inputs and must be validated before querying:

- `first`/`last`/`size` are non-negative and within the maximum cap.
- `page`/`offset` stay within integer bounds and operational limits.
- Forbidden argument combinations are rejected.
- Cursors must decode cleanly, match supported versions, and contain required sort keys.
- Filters and sorts belong to the schema/allowlist.
- Cursors match the current filter/sort if required by the contract.

Errors can be standardized:

| Case | Suggested error code |
| --- | --- |
| Negative page size | `INVALID_PAGE_SIZE` |
| Page size exceeds max | `PAGE_SIZE_EXCEEDED` |
| Malformed cursor | `INVALID_CURSOR` |
| Unsupported cursor version | `UNSUPPORTED_CURSOR_VERSION` |
| Cursor does not match filter/sort | `CURSOR_SCOPE_MISMATCH` |
| Invalid sort option | `INVALID_SORT` |

When arguments are typed as enums/ints in SDL, GraphQL validation and input coercion catch some errors before the resolver. Cross-argument rules such as `first` with `last`, maximum page sizes, or cursor/filter fingerprints still require application validation.

Never return stack traces or decoded cursor contents to clients. Error codes must be stable so clients can handle them reliably.

## 17. Nullability and empty pages

The schema should be consistent for collections:

~~~graphql
type ProductConnection {
    edges: [ProductEdge!]!
    pageInfo: PageInfo!
    totalCount: Int
}

type ProductEdge {
    cursor: String!
    node: Product!
}
~~~

With this contract:

- The connection is always present.
- `edges` is always a list, possibly empty.
- Every edge must have a `cursor` and a `node`.
- `pageInfo` is always present.
- `totalCount` may be null if uncomputed per published semantics.

If a node is deleted between querying and serialization, the service must decide whether to exclude that edge or return an error per contract. Do not return an edge with a null node if the schema declares `Product!` and clients are unprepared for it.

An empty page is not an error. If a cursor points to the end of the dataset, the server can return empty `edges`, an appropriate `PageInfo`, and no GraphQL errors. Malformed or out-of-scope cursors are input errors.

## 18. Mapping contracts to Spring for GraphQL

SDL publishes arguments and response shapes. Example resolver:

~~~java
@Controller
public class ProductQueryController {

    private final ProductQueryService productQueryService;

    public ProductQueryController(ProductQueryService productQueryService) {
        this.productQueryService = productQueryService;
    }

    @QueryMapping
    public ProductConnection products(
            @Argument Integer first,
            @Argument String after,
            @Argument ProductFilter filter,
            @Argument ProductSort sort,
            Principal principal) {

        return productQueryService.findProducts(
            first, after, filter, sort, principal);
    }
}
~~~

The controller only binds arguments and delegates to the service. The service handles defaults, validation, authorization, cursor decoding, repository queries, and building `PageInfo`.

Arguments can be grouped into a Java record when the input contract uses an input object:

~~~graphql
input ProductPageRequest {
    first: Int = 20
    after: String
    filter: ProductFilter
    sort: ProductSort = CREATED_AT_DESC
}
~~~

~~~graphql
type Query {
    products(input: ProductPageRequest): ProductConnection!
}
~~~

This is an alternative variant to `products(first, after, filter, sort)` from the earlier example; do not declare both fields with the same name in one schema. An input object is convenient when there are many pagination/filter arguments that need reuse. Individual arguments fit simpler queries and align with Relay conventions. Do not wrap just two fields in a nested input if it makes client queries wordier without clear benefit.

## 19. DTOs for Page and Connection

Do not expose framework `Page` or `Slice` directly if the contract should not depend on Spring Data. Create dedicated DTOs:

~~~java
public record ProductEdge(String cursor, ProductView node) {
}

public record PageInfo(
        boolean hasNextPage,
        boolean hasPreviousPage,
        String startCursor,
        String endCursor) {
}

public record ProductConnection(
        List<ProductEdge> edges,
        PageInfo pageInfo,
        Integer totalCount) {
}
~~~

Offset contracts can use:

~~~java
public record OffsetPageInfo(
        int page,
        int size,
        boolean hasNextPage,
        Integer totalElements,
        Integer totalPages) {
}

public record ProductPage(
        List<ProductView> items,
        OffsetPageInfo pageInfo) {
}
~~~

DTOs keep the schema contract decoupled from persistence implementations. Later, the service can switch from Spring Data `Page` to a keyset query or search backend without changing the response shape.

## 20. Do not let Spring Data Page become the public contract

Spring Data `Page` exposes `content`, `number`, `size`, `totalElements`, `totalPages`, and convenience methods. It fits well at the repository/application boundary, whereas the public GraphQL contract should define fields and semantics needed by clients.

Example mapping:

~~~java
Page<ProductEntity> page = repository.findAll(specification, pageable);

return new ProductPage(
    page.getContent().stream()
        .map(productMapper::toView)
        .toList(),
    new OffsetPageInfo(
        page.getNumber(),
        page.getSize(),
        page.hasNext(),
        Math.toIntExact(page.getTotalElements()),
        page.getTotalPages()));
~~~

This mapping must account for `totalElements` overflow; `Math.toIntExact` throws if the count exceeds `Int`. If datasets can exceed that limit, use an appropriate scalar or omit the count.

With `Slice`, the server knows `hasNext` without computing a total count. If the public contract only requires `hasNextPage`, `Slice` can be a better fit than `Page`, while still mapping to dedicated DTOs.

## 21. Client navigation contracts

Clients should rely on metadata returned by the server:

- First page: omit `after`.
- Next page: pass the current page's `endCursor` into `after`.
- Previous page: use `startCursor` and `before` if backward pagination is supported.
- Never increment or decode cursors client-side.
- Reset the cursor whenever filter or sort changes.
- Keep filter/sort stable across a single traversal.
- Change page size between requests if permitted by the contract.
- Use `hasNextPage`/`hasPreviousPage` to enable/disable navigation controls.

For infinite scroll, clients typically append edges and deduplicate by node ID if refreshes or live updates can return overlapping items. Deduplication is a UI strategy; the server must still uphold ordering and cursor semantics.

With offset pagination, clients can store page numbers and jump directly to arbitrary pages. However, if the dataset changes, a page number does not guarantee the same items appear as in a prior read.

## 22. Backward pagination

When backward traversal is supported, the contract can use `last` and `before`:

This is an alternative version replacing the forward-only `Query` declaration in the Connection section, not a second root type in the same schema:

~~~graphql
type Query {
    products(
        first: Int
        after: String
        last: Int
        before: String
        filter: ProductFilter
        sort: ProductSort = CREATED_AT_DESC
    ): ProductConnection!
}
~~~

Clearly define:

- `first`/`after` move forward in the published order.
- `last`/`before` fetch edges preceding the cursor.
- Never accept both `first` and `last` in a single request.
- `startCursor`/`endCursor` always reflect the connection's published order.
- `hasNextPage`/`hasPreviousPage` are computed within the same sort/filter scope.

The server can invert sorting internally when querying backward and then reverse the results before returning the response. Clients should never see reversed ordering merely because they used `last`/`before`.

If the product only needs a "Load more" button, a forward-only contract is simpler and often sufficient. Do not implement backward pagination just because Relay defines the convention if there is no use case.

## 23. Pagination and caching

A page's cache key must include every element affecting its result:

- Field/root collection.
- Canonicalized filter.
- Sort order.
- Cursor or page/offset.
- Page size if the response shape depends on it.
- Tenant/user scope when data is access-controlled.

Do not cache by cursor alone if cursors do not bind filter/sort or authorization scope. Never share authorized responses across users simply because the query text matches.

Cursors are typically opaque and may expire if the contract uses snapshot tokens. Clients should handle invalid/expired cursors by returning to the first page or refreshing the collection per published semantics.

Cache invalidation must consider mutations that create, delete, or update items affecting sorting/filtering. Never promise immediate pagination cache consistency if the system relies on eventual consistency.

## 24. Performance and query planning

A pagination contract bounds response size, but does not automatically make queries fast. The server needs an appropriate query plan:

- Large offsets may have to scan and discard many rows.
- Cursor/keyset queries need predicates matching sort keys.
- Composite indexes should support equality filters and sort columns.
- Projections should select only columns needed for edges/nodes.
- Avoid unnecessary counts.
- Batch nested fields to prevent N+1 queries.
- Cap total page sizes across nested collections.

If a collection is queried via a search engine, cursors can wrap backend search-after tokens or continuation tokens. Clients still see only an opaque `String`; the resolver translates it to the backend token per contract.

Never expose internal database or search-engine cursor formats for clients to construct themselves. Keep an adapter between the public cursor and the backend paging mechanism so the backend can change.

## 25. Testing contracts with GraphQlTester

Tests should verify both response shape and multi-page traversal behavior:

~~~java
@Test
void returnsNextPageUsingEndCursor() {
    var firstResponse = graphQlTester.document("""
            query {
                products(first: 2, sort: CREATED_AT_DESC) {
                    edges {
                        cursor
                        node {
                            id
                        }
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                }
            }
            """)
        .execute();

    firstResponse.errors().verify();
    firstResponse.path("products.edges")
        .entityList(ProductEdgeView.class)
        .hasSize(2);

    String endCursor = firstResponse.path("products.pageInfo.endCursor")
        .entity(String.class)
        .get();

    var nextResponse = graphQlTester.document("""
            query NextProducts($after: String) {
                products(first: 2, after: $after, sort: CREATED_AT_DESC) {
                    edges {
                        node {
                            id
                        }
                    }
                    pageInfo {
                        hasNextPage
                    }
                }
            }
            """)
        .variable("after", endCursor)
        .execute();

    nextResponse.errors().verify();
    nextResponse.path("products.edges")
        .entityList(ProductEdgeIdView.class)
        .hasSize(2);
}
~~~

The fixture needs enough records for at least two pages. View DTOs used in tests must match the selection set. Tests should also compare IDs across pages to confirm there are no duplicates in a stable fixture.

## 26. Essential test suite for pagination contracts

| Category | Cases to test |
| --- | --- |
| Defaults | Omitting page size uses the published default |
| Boundaries | Size = 1, max size, max + 1, 0, and negative values |
| First page | No cursor, correct sort/filter |
| Next page | Uses `endCursor` from the previous page |
| Last page | `hasNextPage = false` |
| Empty collection | Empty `edges`, null cursors |
| Sort | Deterministic order when multiple items share the same sort value |
| Filter | Filter preserved across pages and out-of-scope cursor rejected |
| Cursor | Malformed format, old version, missing keys, or expired |
| Backward | `last`/`before` returns items in published order |
| Count | `totalCount` matches semantics or is null per contract |
| Authorization | Cursors cannot be used to read another tenant's data |
| Concurrent changes | Inserts/deletes/updates behave per consistency contract |
| Nested collections | Each parent maintains independent cursors/`pageInfo` |
| Performance | Query count does not grow linearly from nested resolvers |

Test the GraphQL contract with `GraphQlTester`. Test repositories/query plans separately against an appropriate database when verifying keyset predicates, indexes, and performance. Test client integration if responses are cached or transformed by a gateway.

## 27. Evolving pagination contracts

A pagination contract is public API and must evolve compatibly:

- Adding nullable metadata fields is usually safer than changing the meaning of existing fields.
- Never change page indexing from zero-based to one-based on the same field.
- Never change default sorting if clients depend on the current order without notice.
- Never alter cursor formats in ways that invalidate cursors held by active clients without a policy.
- Never swap `page`/`size` for `first`/`after` on the same field.
- Never change the semantics of `hasNextPage` or `totalCount`.

If migrating from offset to cursor:

1. Add a new connection field, such as `productsConnection`.
2. Keep the old page field during the transition window.
3. Mark the old field `@deprecated` with specific guidance.
4. Track client usage.
5. Update clients and test both contracts.
6. Remove the old field only after confirming consumers have migrated.

Do not return cursors in an internal format and force clients to migrate whenever the backend changes. Public cursors should be server-managed, versionable tokens.

## 28. Common mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Not specifying 0-based vs. 1-based pages | Clients request the wrong page | Publish indexing conventions |
| Unbounded page size | Oversized responses and high query cost | Clear default and maximum caps |
| Unstable sort order | Items can repeat or be skipped | Unique tie-breaker |
| Inferring `hasNextPage` from `edges.size()` | Final page may report incorrectly | Fetch one extra item or use `EXISTS` |
| Always running `totalCount` even when unselected | Expensive count queries | Compute counts on demand per semantics |
| Reusing a cursor with a different filter | Page boundaries lose meaning | Bind cursors to filter/sort |
| Treating cursors as credentials | Replay attacks can bypass access control | Enforce authorization on every request |
| Mixing page and cursor styles | Clients cannot follow navigation | Choose one clear contract per field |
| Returning Spring Data `Page` directly | API coupled to framework | Map to GraphQL DTOs |
| Unpaginated nested lists | Queries can return huge payloads | Dedicated connections per collection |
| Batch loaders ignoring parent/filter scope | Leaking wrong data across parents | Full batch keys and authorization scope |
| Silently changing default sort | Client item order shifts unexpectedly | Controlled versioning/evolution |
| Removing offset field immediately after adding cursor field | Existing clients break | Deprecate and migrate by usage |

## 29. Pagination contract design workflow

A workflow applicable to each collection:

1. Identify the client use case: numbered data table, infinite scroll, or feed.
2. Choose offset/page or cursor/connection.
3. Define arguments, defaults, and bounds.
4. Publish sort options and deterministic ordering.
5. Define filter scope and cursor-reuse rules.
6. Define response shape, `PageInfo`, and `totalCount` semantics.
7. Choose nullability and error codes.
8. Apply authorization/tenant scope to every page.
9. Design resolver/service DTOs decoupled from repository types.
10. Test navigation, boundaries, concurrent changes, and schema compatibility.
11. Measure query plans, indexes, nested query counts, and response sizes.

## 30. Principles for pagination contract design

A pagination contract must describe behaviors clients can depend on: navigation style, page sizes, sort ordering, filter scope, metadata, empty pages, and input errors. Choose offset when jumping to page numbers over moderately sized collections; choose cursor connections when traversing large collections and resuming from stable positions.

Keep sort orders deterministic, bind cursors to filters/sorts where needed, enforce authorization on every request, and never let cursors act as credentials. Explicitly publish the semantics of `hasNextPage`, `hasPreviousPage`, and `totalCount`; cap page sizes and nested collections to control query cost.

In Spring for GraphQL, declare contracts in SDL, bind arguments via `@Argument`, and return dedicated `Page`/`Connection` DTOs. Application services own validation, querying, and metadata; resolvers must not couple clients to Spring Data `Page` or backend continuation tokens. Test contracts with `GraphQlTester` and inspect query plans at the repository layer.

A strong pagination API lets clients keep traversing data under stable rules while freeing the server to evolve querying and storage behind the contract.

## References

- [Relay Cursor Connections Specification](https://relay.dev/graphql/connections.htm)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution and Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Data Commons — Paging and Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html)
- [GraphQL Specification — Type System](https://spec.graphql.org/)
