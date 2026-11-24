# Documenting Links or Cursors for Cursor Pagination

Cursor pagination splits a dataset into consecutive slices using a cursor value. Clients send the cursor received from the previous response to fetch the next slice. Unlike offset pagination, which uses page numbers or starting positions, a cursor typically represents the last read position under a stable sort order. This approach suits large lists, frequently changing data, or APIs that need to resume reading without re-scanning earlier records.

In an OpenAPI contract, a cursor can be documented as a query parameter; responses can return `nextCursor`, `previousCursor`, or navigation URLs `next`/`previous`. Springdoc-openapi helps publish these fields and parameters via schemas, annotations, and response headers. Distinguish between cursor tokens, navigation URLs in payloads, HTTP `Link` headers, and OpenAPI Link Objects, because each serves a different role.

## 1. How Does Cursor Pagination Work?

With offset pagination, clients typically send `page` and `size`, or `offset` and `limit`. The server skips a number of records and fetches the next slice. With cursor pagination, the server returns a cursor marking the continuation point, and the client sends that cursor in the next request.

Simple flow example:

```text
First request:
GET /api/orders?limit=20

First response:
{
  "items": [ ... 20 orders ... ],
  "nextCursor": "eyJjcmVhdGVkQXQiOi..."
}

Next request:
GET /api/orders?limit=20&cursor=eyJjcmVhdGVkQXQiOi...

Next response:
{
  "items": [ ... next 20 orders ... ],
  "nextCursor": "eyJjcmVhdGVkQXQiOi..."
}
```

Clients do not compute the next position themselves. The server issues a cursor after determining the current page and uses that cursor to resume the query.

A response may include:

- `items`: items of the current page.
- `nextCursor`: cursor to fetch the next page; may be null or omitted when no data remains.
- `previousCursor`: cursor to go back to the previous page if the API supports backward navigation.
- `hasNext` or `hasPrevious`: status flags if the API needs to provide them explicitly, even though they can be inferred from cursors.
- `next` and `previous`: full or relative URLs for the client to call next.

There is no need to return all of these fields if they duplicate information. Choose one clear structure and keep it consistent across the entire API.

## 2. How Cursors Differ from Offsets and Page Numbers

| Criterion | Offset/page | Cursor |
|---|---|---|
| Continuation parameter | `page`, `size`, `offset`, `limit` | `cursor`, usually paired with `limit` |
| How position is determined | Skips a count of preceding records | Resumes after a sort key or encoded position |
| When new data is inserted | Records can shift across pages | Less likely to shift if order and cursor are designed stably |
| Random page access | Easier with page number/offset | Usually requires sequential traversal from an existing cursor |
| Performance on large datasets | Large offsets can incur scan/skip costs | Keyset queries can leverage appropriate indexes |
| Backward navigation | Easy to compute by page number | Requires a previous cursor or reverse-query logic |
| Showing total page count | Easy if total count is available | Does not necessarily include total count |

Cursors do not automatically make queries fast. Performance depends on how the cursor is built, sort order, indexes, and the query itself. If the server decodes a cursor only to run a huge `OFFSET`, most benefits of keyset pagination will not materialize.

## 3. Designing Stable Cursors with Keyset Pagination

A cursor typically stores the sort values of the last record on the current page. For instance, an order list sorted by `createdAt DESC`; if multiple records share the same timestamp, add a unique key like `id DESC` so the order is unambiguous.

```sql
SELECT id, created_at, status, total
FROM orders
WHERE (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :limitPlusOne;
```

This illustrates syntax for databases supporting tuple comparison. For other database engines, write the equivalent predicate:

```sql
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id < :lastId)
```

The server typically queries `limit + 1` records to tell whether more data follows. If an extra record is returned, the server returns `limit` items and builds `nextCursor` from the sort keys of the last returned item.

A stable cursor requires:

- A deterministic sort order, ideally including a unique key as a tie-breaker.
- Storing all values needed to resume the query, not just a potentially duplicated timestamp.
- Reusing the same sort order and filter conditions across subsequent requests.
- Explicit rules for handling nulls, collation, and timestamp precision.
- Generating the cursor from the last item returned on the page, not from the extra lookahead record used to detect the next page.

If the sort order changes between requests, the old cursor may lose meaning. Fix the sort order in the contract or bind the sort inside the cursor.

## 4. Designing `cursor` and `limit` Request Parameters

A cursor-paginated endpoint typically accepts an optional cursor and an item limit. The first request omits the cursor; subsequent requests pass the cursor from the previous response.

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping
    CursorPage<OrderResponse> list(
            @RequestParam(required = false) String cursor,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit) {
        return orderService.list(cursor, limit);
    }
}
```

In this example:

- `cursor` is an optional query parameter; omitting it starts from the beginning.
- `limit` is the maximum number of items requested in a response.
- `@Min` and `@Max` enforce page size limits at runtime when validation is enabled.
- `defaultValue` lets Spring apply a default when the query parameter is omitted.

Unbounded `limit` should not be allowed. A maximum cap controls database load, memory usage, and response size. If a cursor is malformed, expired, or incompatible with current filters, the API must return a clear error response such as `400 Bad Request`.

## 5. Documenting the Cursor Parameter with springdoc-openapi

Springdoc can infer query parameters from `@RequestParam`. Use `@Parameter` to clarify that the cursor is an opaque token, not a page number or client-crafted value.

```java
@GetMapping
CursorPage<OrderResponse> list(
        @Parameter(
            description = "Cursor returned by the server in the previous page. Omit to fetch the first page.",
            example = "eyJjcmVhdGVkQXQiOiIyMDI2LTExLTIwVDEwOjAwOjAwWiIsImlkIjoiLi4uIn0"
        )
        @RequestParam(required = false) String cursor,
        @Parameter(
            description = "Maximum number of items per page",
            example = "20"
        )
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit) {
    return orderService.list(cursor, limit);
}
```

In OpenAPI, `cursor` usually has schema `type: string`, `required: false`; `limit` is an integer with appropriate default and bounds. Do not document cursor as `format: uuid` if the actual token is an opaque string carrying encoded data or a signature.

Condensed YAML example:

```yaml
paths:
  /api/orders:
    get:
      parameters:
        - name: cursor
          in: query
          required: false
          description: Server-issued cursor from the previous response
          schema:
            type: string
        - name: limit
          in: query
          required: false
          description: Maximum number of items per page
          schema:
            type: integer
            format: int32
            minimum: 1
            maximum: 100
            default: 20
      responses:
        '200':
          description: Page of orders
```

If the endpoint permits filtering or sorting, parameters like `status`, `fromDate`, and `sort` also need documentation. The server must define whether those can be altered when a client sends an existing cursor.

## 6. Documenting `nextCursor` and `previousCursor` in the Response Schema

The response should clearly describe which cursors can be used to move forward or backward. Example DTO:

```java
public class CursorPage<T> {
    private List<T> items;
    private String nextCursor;
    private String previousCursor;

    // getters and setters
}
```

Illustrative OpenAPI schema:

```yaml
CursorPageOrderResponse:
  type: object
  required:
    - items
  properties:
    items:
      type: array
      items:
        $ref: '#/components/schemas/OrderResponse'
    nextCursor:
      type: string
      nullable: true
      description: Cursor for fetching the next page; null when no more pages remain
    previousCursor:
      type: string
      nullable: true
      description: Cursor for returning to the previous page if supported by the API
```

`nullable: true` is standard in OpenAPI 3.0. If the spec uses OpenAPI 3.1, express nullability using the JSON Schema syntax supported by your springdoc version.

Returning `hasNext` is not strictly necessary if a null `nextCursor` already clearly signals the end of results. If both are returned, keep them strictly consistent: `hasNext: true` must always accompany a usable cursor.

You can use `@Schema` to document the fields:

```java
public class CursorPage<T> {
    @Schema(description = "Items on the current page")
    private List<T> items;

    @Schema(
        description = "Opaque cursor for fetching the next page; null when no more data remains",
        nullable = true,
        example = "eyJjcmVhdGVkQXQiOi..."
    )
    private String nextCursor;

    @Schema(
        description = "Opaque cursor for returning to the previous page; null if unavailable",
        nullable = true
    )
    private String previousCursor;

    // getters and setters
}
```

A generic `CursorPage<T>` schema may be named by springdoc based on the concrete element type. If schema names must remain stable in a public contract, define concrete DTOs such as `OrderCursorPageResponse` or configure schema naming per library version.

## 7. Returning `next` and `previous` URLs Instead of Cursor Tokens

An API can return full or relative URLs directly so clients simply follow them:

```json
{
  "items": [
    { "id": "ord-101", "status": "PAID" }
  ],
  "links": {
    "next": "/api/orders?limit=20&cursor=eyJpZCI6...",
    "previous": null
  }
}
```

With this approach, the server builds the URLs and preserves necessary filters, sort, and limit. Clients do not assemble query strings manually. Corresponding DTOs:

```java
public class PageLinks {
    private URI next;
    private URI previous;

    // getters and setters
}

public class LinkedCursorPage<T> {
    private List<T> items;
    private PageLinks links;

    // getters and setters
}
```

Schema:

```yaml
PageLinks:
  type: object
  properties:
    next:
      type: string
      format: uri-reference
      nullable: true
    previous:
      type: string
      format: uri-reference
      nullable: true
```

Relative URLs work well when the API sits behind a reverse proxy or runs across multiple environments. Absolute URLs are convenient for clients but must construct the right scheme, host, and base path according to deployment configuration. Never build URLs from untrusted `Host` or forwarded headers unless proxy trust is properly configured in the application.

`next` and `previous` in JSON are application-generated response data. They differ from OpenAPI Link Objects: one is an actual runtime URL, while the other is documentation metadata describing how to invoke an operation.

## 8. Documenting the HTTP `Link` Header

Another option is placing pagination URLs in the HTTP `Link` response header, typically following Web Linking syntax:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Link: </api/orders?limit=20&cursor=abc123>; rel="next"
```

If a previous page exists:

```http
Link: </api/orders?limit=20&cursor=prev456>; rel="prev",
      </api/orders?limit=20&cursor=next789>; rel="next"
```

`rel="next"` and `rel="prev"` define the URL relationship. Query parameters must follow URI encoding rules; never append a raw cursor into the header if it contains characters needing percent-encoding.

In Spring, you can add the header to `ResponseEntity`:

```java
return ResponseEntity.ok()
        .header(HttpHeaders.LINK,
                "</api/orders?limit=20&cursor=" + encodedCursor + ">; rel=\"next\"")
        .body(page);
```

This snippet illustrates the header structure; in real implementations, build URIs using `UriComponentsBuilder` or an equivalent URI builder, encode query parameters, and assemble each link safely. Avoid raw string concatenation when cursors might contain special characters.

With springdoc, declare the response header using `@ApiResponse(headers = @Header(...))`:

```java
@ApiResponse(
    responseCode = "200",
    description = "Page of orders",
    headers = @Header(
        name = "Link",
        description = "Links to the previous or next page",
        schema = @Schema(type = "string")
    )
)
```

If a frontend calls the API cross-origin and needs to read `Link` from JavaScript, configure CORS `Access-Control-Expose-Headers: Link`. Presence of a header on the response does not automatically allow browser JavaScript to read it.

## 9. Documenting Next-Page Links with OpenAPI Link Objects

An OpenAPI Link Object can describe the next pagination call by taking `nextCursor` from the current response and passing it to the `cursor` query parameter of the same operation.

```yaml
paths:
  /api/orders:
    get:
      operationId: listOrders
      parameters:
        - name: cursor
          in: query
          required: false
          schema:
            type: string
        - name: limit
          in: query
          required: false
          schema:
            type: integer
            default: 20
      responses:
        '200':
          description: Page of orders
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderCursorPage'
          links:
            nextPage:
              operationId: listOrders
              parameters:
                cursor: '$response.body#/nextCursor'
                limit: '$request.query.limit'
```

The `nextPage` link indicates the target operation is still `listOrders`; `cursor` is taken from `nextCursor` in the current response and `limit` is carried over from the source request.

Note one caveat: the Link Object sits statically in the documentation under response `200`, whereas the last page may return `nextCursor: null`. Clients or consuming tools must inspect the cursor value before following the link. The link describes how to construct the next request; it does not guarantee the current response always has a next page.

If other filters like `status` or `fromDate` must be preserved, map them from the source request:

```yaml
links:
  nextPage:
    operationId: listOrders
    parameters:
      cursor: '$response.body#/nextCursor'
      limit: '$request.query.limit'
      status: '$request.query.status'
      fromDate: '$request.query.fromDate'
```

The target operation must declare those corresponding parameters. If filters change while an old cursor is reused, results may be wrong or the cursor invalid.

## 10. Declaring OpenAPI Links with springdoc Annotations

You can use `@Link` and `@LinkParameter` on a response to describe the next page:

```java
@Operation(operationId = "listOrders", summary = "List orders with cursor pagination")
@ApiResponse(
    responseCode = "200",
    description = "Page of orders",
    links = @Link(
        name = "nextPage",
        operationId = "listOrders",
        description = "Use the cursor from the response to fetch the next page",
        parameters = {
            @LinkParameter(
                name = "cursor",
                expression = "$response.body#/nextCursor"
            ),
            @LinkParameter(
                name = "limit",
                expression = "$request.query.limit"
            )
        }
    )
)
@GetMapping("/api/orders")
CursorPage<OrderResponse> list(
        @RequestParam(required = false) String cursor,
        @RequestParam(defaultValue = "20") int limit) {
    return orderService.list(cursor, limit);
}
```

`CursorPage`, `OrderResponse`, and `orderService` are illustrative components. After starting the application, inspect `/v3/api-docs` or `/v3/api-docs.yaml` to verify the link appears under response `200` and the expressions are preserved intact.

When `nextCursor` is null on the last page, tools should not issue another request with a null cursor. This is a business condition clients must handle; annotations do not hide links dynamically per runtime response.

## 11. Designing Secure and Resilient Cursor Tokens

Cursors are usually opaque tokens: clients store and send them back without decoding or modifying them. A token can carry keyset values like timestamp and ID, or serve as a reference ID to server-side state.

A token-style cursor can be built from a JSON payload, URL-safe Base64 encoded, and digitally signed:

```json
{
  "v": 1,
  "createdAt": "2026-11-20T10:00:00Z",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "sort": "createdAt:desc,id:desc",
  "filterHash": "...",
  "expiresAt": "2026-11-20T12:00:00Z"
}
```

This is an illustrative payload; production tokens can be signed with HMAC or use random identifiers pointing to server state. Base64 is encoding, not encryption. If a token contains sensitive data, encrypt it or exclude that data from the token.

Key principles:

- Verify signatures or integrity so clients cannot tamper with IDs, sort keys, or query scope.
- Bind the cursor to filters, sort order, tenant, or access context to prevent cross-scope reuse.
- Enforce authorization on every request; a cursor is not an access token and grants no permissions.
- Version the token (`v`) so cursor structure can evolve cleanly.
- Consider expiration and how to respond when a cursor expires.
- Avoid embedding PII or secrets in tokens visible in URLs, logs, and browser history.
- Cap token length and handle malformed tokens consistently.

Cursors in query strings can appear in access logs, analytics, browser history, or Referer headers depending on the environment. Never use cursors to carry authentication credentials.

## 12. Preserving Filters and Sort Across Pages

A cursor is meaningful only within the query context that produced it. For example, a cursor issued for `status=PAID` and `sort=createdAt,desc` should not be used with `status=CANCELLED` or another sort order unless explicitly designed for it.

Two common strategies:

1. Include a hash of the filter/sort inside the cursor and validate it on the next request.
2. Store filter/sort in server-side cursor state and return only a reference token.

When generating a `next` URL, preserve all relevant parameters:

```text
/api/orders?status=PAID&sort=createdAt%2Cdesc&limit=20&cursor=...
```

If the client changes filters, start a new pagination stream by dropping the old cursor. The API can return `400 Bad Request` when detecting a cursor incompatible with the current query.

## 13. Backward Navigation and `previousCursor`

Not every system supports moving backward. With keyset pagination, forward and backward cursors can require different query logic.

To support `previousCursor`, the server must store or derive the starting point of the previous page. Common designs:

- Return a previous cursor derived from the first item's keys on the current page, reversing the comparison predicate and sort order when querying backward.
- Maintain visited page cursors on the client or server.
- Support forward-only (`next`) traversal to keep the contract simple when backward navigation is unnecessary.

For example, when sorting `createdAt DESC, id DESC`, forward queries compare less than the page's last key; backward queries compare greater than the page's first key, fetch in reverse order, and flip the results before returning. Details depend on the database engine and sort direction.

Never fabricate a fake `previousCursor` by stepping back a fixed record count if data can mutate. Verify cursor stability and returned ordering.

## 14. Cursor-Related Error Responses

Cursor pagination can produce specific error cases:

| Status | Scenario |
|---|---|
| `400 Bad Request` | Malformed cursor, invalid signature, or filter/sort mismatch |
| `401 Unauthorized` | Unauthenticated request |
| `403 Forbidden` | User lacks permission to access the data scope |
| `410 Gone` | Cursor or snapshot expired and the API chooses this semantics |
| `422 Unprocessable Content` | Syntactically valid token that cannot be processed per business rules, if the API uses this status |
| `429 Too Many Requests` | Client paginates too rapidly or exceeds quota |

Not every API needs `410` or `422`; choose status codes consistent with your system's error conventions. Error responses should have a stable schema, machine-readable error codes, and messages that do not leak internal token details.

Example error responses:

```yaml
responses:
  '400':
    description: Invalid cursor or incompatible with filters
    content:
      application/problem+json:
        schema:
          $ref: '#/components/schemas/ApiProblem'
  '410':
    description: Cursor has expired
    content:
      application/problem+json:
        schema:
          $ref: '#/components/schemas/ApiProblem'
```

## 15. Verifying the Contract and Pagination Behavior

After declaring cursor parameters, response schemas, and links, verify both documentation and request flows:

1. Download `/v3/api-docs` or `/v3/api-docs.yaml`.
2. Confirm `cursor` is an optional query parameter and `limit` has accurate bounds and defaults.
3. Confirm `nextCursor`/`previousCursor` or link URLs document the right type, nullability, and meaning.
4. Check OpenAPI Link Objects if used; target parameter names must match the pagination operation.
5. Call the first request without a cursor and confirm the server returns the first page.
6. Pass the returned `nextCursor` to fetch the next page.
7. Confirm no items are duplicated or skipped on a static dataset.
8. Insert or update records between requests to check behavior under mutating data.
9. Test malformed, expired, tampered cursors, and cursors from different filters/sorts.
10. Verify `limit` caps, authorization, tenant isolation, and error responses.
11. If using URLs or `Link` headers, confirm URLs preserve filters/sort and are properly encoded.
12. Run an OpenAPI validator and check Swagger UI/client generators.

A critical check is ensuring zero duplicates when multiple records share the same sort key. If sorting only by `createdAt` and multiple orders share the same timestamp, the cursor may skip or duplicate items. Adding a unique key like `id` as a tie-breaker makes ordering deterministic.

## 16. Common Issues

| Symptom | Possible cause | Fix |
|---|---|---|
| Next page duplicates records | Sort lacks a unique tie-breaker or cursor derived from wrong item | Use deterministic ordering and build cursor from the last returned item |
| Records are skipped | Keyset predicate mismatches sort order or mishandles nulls | Check predicate and sort direction |
| Old cursor returns wrong filtered data | Cursor not bound to query context | Store or sign filter/sort with the cursor and validate |
| Clients decode or tamper with cursor | Contract does not clarify cursor is opaque | Document cursor as server-issued token, do not modify |
| `nextCursor` is null yet link is still followed | Static Link Object in docs | Client checks cursor before fetching next page |
| `next` URL drops filters | Server builds URL with only cursor and limit | Preserve applied filters and sort |
| Cursor is too long | Too much state stuffed into token | Trim payload or use a server-side reference token |
| Cursor leaks internal details | Base64 token holds plaintext data | Sign against tampering; encrypt or use opaque IDs if confidential |
| Swagger UI does not auto-navigate | UI does not execute OpenAPI Links or only displays metadata | Call manually or use a link-aware client |
| Frontend cannot read `Link` header | CORS does not expose the header | Add `Link` to `Access-Control-Expose-Headers` |

## 17. Design Principles

- Use cursors for sequential streams or large datasets; use offset/page when random page access is needed and cost is acceptable.
- Use deterministic sorting with a unique key as a tie-breaker.
- Document cursors as opaque server-issued strings; clients only store and resend them.
- Cap `limit` and clearly document default and maximum values.
- Return `nextCursor` when a next page exists; `hasNext` is optional if already clear.
- Keep filters and sort consistent across requests; bind cursors to query context when needed.
- Choose response body links, HTTP `Link` headers, or OpenAPI Link Objects as appropriate; do not confuse their roles.
- When using OpenAPI Links, map the cursor via runtime expressions and instruct clients to check for null on the last page.
- Sign or protect cursors against tampering; encrypt if tokens hold confidential data.
- Validate authorization independently; a cursor is not an authentication token.
- Test mutating data, duplicate sort keys, expired cursors, and error cases.
- Verify schemas and links in the JSON/YAML generated by springdoc.

## Conclusion

Cursor pagination uses a server-issued token to resume querying from the last read position. The OpenAPI contract should document the `cursor` query parameter, `limit` bounds, `nextCursor`/`previousCursor` fields or navigation URLs, and optionally add OpenAPI Link Objects to map a response's cursor into the next request. Springdoc-openapi supports publishing these elements via `@Parameter`, `@Schema`, response headers, and `@Link`/`@LinkParameter`. Keep query ordering deterministic, bind cursors to appropriate filters and sorts, protect tokens, and test real pagination flows so clients never encounter duplicates, gaps, or unauthorized data access.
