# Response Headers Such as `Location`, `ETag`, and Pagination Metadata

An HTTP response has more than a status code and a body. Headers also carry metadata telling clients where a newly created resource lives, which version of a representation is current, whether content can be reused from cache, or where the next page of data is located. With Spring Boot, `ResponseEntity` is the common way to build responses with headers; with `springdoc-openapi`, `@ApiResponse(headers = ...)` documents those headers in the OpenAPI contract.

Three common header groups in APIs:

- `Location`: points to the URI of a newly created resource or a redirect target.
- `ETag`: identifies a representation version for caching and conditional update checks.
- `Link` along with pagination headers such as `X-Total-Count`: provides links to the first, previous, next, and last pages as well as the total record count.

Headers sent in the actual HTTP response must match what OpenAPI advertises. Annotations only describe the contract; controller code or filters actually produce the headers when requests are handled.

## 1. Building Responses with Headers Using `ResponseEntity`

`ResponseEntity<T>` lets the controller control status, headers, and body in a single return value:

```java
return ResponseEntity
    .status(HttpStatus.CREATED)
    .header("X-Request-Id", requestId)
    .body(result);
```

Commonly used builder methods:

| API | Purpose |
| --- | --- |
| `ResponseEntity.ok()` | Builds a `200 OK` response. |
| `ResponseEntity.created(uri)` | Builds a `201 Created` response and sets the `Location` header. |
| `.eTag(value)` | Sets the `ETag` header. |
| `.lastModified(value)` | Sets the `Last-Modified` header. |
| `.cacheControl(value)` | Sets the `Cache-Control` policy. |
| `.header(name, values...)` | Adds one or more header values for a given header name. |
| `.body(value)` | Attaches the response body. |

You can use `HttpHeaders` when preparing multiple headers or reusing the same header set across branches. Header names are case-insensitive in HTTP, but using standard capitalization such as `ETag`, `Location`, and `Link` keeps logs and documentation readable.

## 2. `Location` Identifies the Newly Created Resource

When a client sends a `POST` to create a resource, the server typically returns `201 Created`. The `Location` header provides the URI for accessing the new resource. This is a standard way for clients to learn the ID or path of the newly created object without assembling URLs themselves.

Example order-creation controller:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    @Operation(summary = "Create an order")
    @ApiResponse(
        responseCode = "201",
        description = "Order created",
        headers = @Header(
            name = HttpHeaders.LOCATION,
            description = "URI of the newly created order",
            schema = @Schema(type = "string", format = "uri",
                example = "https://api.example.com/api/orders/8d3f")
        )
    )
    ResponseEntity<OrderResponse> create(@Valid @RequestBody CreateOrderRequest request) {
        OrderResponse created = orderService.create(request);
        URI location = ServletUriComponentsBuilder
            .fromCurrentRequest()
            .path("/{id}")
            .buildAndExpand(created.id())
            .toUri();

        return ResponseEntity.created(location).body(created);
    }
}
```

`ResponseEntity.created(location)` produces status `201` and sets `Location` to the supplied URI. `ServletUriComponentsBuilder.fromCurrentRequest()` captures the current request URI; `.path("/{id}")` appends the new resource path. This avoids hard-coding hosts or base paths in the controller.

In OpenAPI, response headers are declared inside the corresponding response—here, `201`. `schema` describes the header value as a URI; `description` explains how the client should use it. Headers are not part of the response body.

`Location` can also appear in redirect responses such as `301`, `302`, `303`, `307`, or `308`. For resource creation, pairing `201 Created` with `Location` helps clients distinguish resource creation from merely receiving a response with a body.

## 3. `ETag` Identifies a Representation Version

`ETag` (Entity Tag) is a validator sent by the server to identify a representation's version. Clients can store the ETag and send it back in subsequent requests to ask whether the data has changed.

Example response:

```http
HTTP/1.1 200 OK
ETag: "order-v42"
Cache-Control: private, max-age=60
Content-Type: application/json
```

ETags have two main forms:

- **Strong ETag:** e.g., `"order-v42"`; indicates a byte-for-byte equivalent representation according to strong validator rules.
- **Weak ETag:** e.g., `W/"order-v42"`; indicates semantically equivalent content per server criteria, without guaranteeing identical bytes.

Do not generate a strong ETag solely from a record ID if response content can change without the ID changing. Use a version number incremented on each update, a hash of the representation, or another identifier guaranteed to change whenever the representation changes. If the server does not guarantee byte-for-byte equivalence, consider a weak ETag.

### Using ETag with `If-None-Match` for Caching

The client sends the stored ETag in the `If-None-Match` request header. If the representation has not changed, the server can return `304 Not Modified` without resending the body. The client continues using its cached copy.

```http
GET /api/orders/8d3f HTTP/1.1
If-None-Match: "order-v42"
```

If the data still has the same validator:

```http
HTTP/1.1 304 Not Modified
ETag: "order-v42"
Cache-Control: private, max-age=60
```

In Spring MVC, `ServletWebRequest.checkNotModified(etag)` helps evaluate cache conditions and set the appropriate status:

```java
@GetMapping("/{id}")
@Operation(summary = "Get order by ID")
@ApiResponses({
    @ApiResponse(responseCode = "200", description = "Order returned",
        headers = @Header(name = "ETag", description = "Representation validator",
            schema = @Schema(type = "string", example = "\"order-v42\""))),
    @ApiResponse(responseCode = "304", description = "Representation unchanged",
        headers = @Header(name = "ETag", description = "Current validator",
            schema = @Schema(type = "string", example = "\"order-v42\"")))
})
ResponseEntity<OrderResponse> get(
    @PathVariable UUID id,
    ServletWebRequest webRequest
) {
    OrderResponse order = orderService.getById(id);
    String etag = "\"order-v" + order.version() + "\"";

    if (webRequest.checkNotModified(etag)) {
        return null; // Spring keeps the 304 response already set.
    }

    return ResponseEntity.ok()
        .header(HttpHeaders.ETAG, etag)
        .cacheControl(CacheControl.noCache())
        .body(order);
}
```

`checkNotModified` checks the request validator and can finalize a `304` response; in that case the controller does not need to send a body. The example uses the order version to build the ETag. In a real application, the version must increment whenever any data affecting the representation changes. `CacheControl.noCache()` allows caches to store the response while requiring revalidation before reuse; choose the cache policy based on data sensitivity and lifecycle.

### Using `If-Match` to Prevent Overwriting Updates

`If-Match` serves a different goal: the client sends the ETag it previously read when updating a resource. The server performs the update only if the current version still matches. If someone else updated it first, the server returns `412 Precondition Failed`.

```http
PUT /api/orders/8d3f HTTP/1.1
If-Match: "order-v42"
Content-Type: application/json
```

If the current version is already `order-v43`, the server rejects the update so the client can reload the latest data and resolve the conflict. You can declare both the request header and error response in OpenAPI:

```java
@PutMapping("/{id}")
@Operation(summary = "Update order with version check")
@ApiResponses({
    @ApiResponse(responseCode = "200", description = "Updated successfully",
        headers = @Header(name = "ETag", description = "New validator after update",
            schema = @Schema(type = "string", example = "\"order-v43\""))),
    @ApiResponse(responseCode = "412", description = "Resource version no longer matches")
})
ResponseEntity<OrderResponse> update(
    @PathVariable UUID id,
    @Parameter(name = "If-Match", in = ParameterIn.HEADER,
        description = "ETag received by the client on the previous read",
        schema = @Schema(type = "string", example = "\"order-v42\""))
    @RequestHeader(HttpHeaders.IF_MATCH) String ifMatch,
    @Valid @RequestBody UpdateOrderRequest request
) {
    OrderResponse updated = orderService.updateIfVersionMatches(id, ifMatch, request);
    String newEtag = "\"order-v" + updated.version() + "\"";
    return ResponseEntity.ok()
        .header(HttpHeaders.ETAG, newEtag)
        .body(updated);
}
```

Version comparison and raising the `412` error belong in the service or business layer. `@Parameter` only describes the request header; `@ApiResponse` describes the possible responses. With `If-Match`, the server also needs to handle missing headers if the contract requires the precondition, as well as valid ETag syntax and wildcard/list forms under HTTP.

## 4. Pagination Headers: `Link` and Total Record Counts

Paginated APIs often return a slice of items in the body and navigation metadata in headers. This lets clients know whether a next page exists without calculating URLs themselves.

Example response:

```http
HTTP/1.1 200 OK
X-Total-Count: 143
X-Total-Pages: 8
Link: <https://api.example.com/api/products?page=0&size=20>; rel="first",
      <https://api.example.com/api/products?page=2&size=20>; rel="next",
      <https://api.example.com/api/products?page=7&size=20>; rel="last"
Content-Type: application/json
```

`Link` uses the Web Linking format. Each link contains a URI in angle brackets and a relation such as:

| Relation | Meaning |
| --- | --- |
| `first` | First page. |
| `prev` | Page immediately before the current page. |
| `self` | Current page. |
| `next` | Next page. |
| `last` | Last page. |

These relations are common pagination values; the server can omit `prev` on the first page or `next` on the last page. `X-Total-Count` and `X-Total-Pages` are custom API headers, not universal standard HTTP headers across all systems. Clearly document their meaning, unit, and calculation in the docs.

Example using Spring Data `Page<T>`:

```java
@GetMapping
@Operation(summary = "List products by page")
@ApiResponse(
    responseCode = "200",
    description = "List of products for the current page",
    headers = {
        @Header(name = "Link", description = "Navigation links across pages",
            schema = @Schema(type = "string",
                example = "<https://api.example.com/api/products?page=2&size=20>; rel=\"next\"")),
        @Header(name = "X-Total-Count", description = "Total products matching the filter",
            schema = @Schema(type = "integer", format = "int64", example = "143")),
        @Header(name = "X-Total-Pages", description = "Total number of pages",
            schema = @Schema(type = "integer", format = "int32", example = "8"))
    }
)
ResponseEntity<List<ProductResponse>> list(
    @RequestParam(defaultValue = "0") int page,
    @RequestParam(defaultValue = "20") int size
) {
    Page<ProductResponse> result = productService.findAll(PageRequest.of(page, size));
    UriComponentsBuilder base = ServletUriComponentsBuilder.fromCurrentRequest();
    List<String> links = new ArrayList<>();

    if (result.getTotalPages() > 0) {
        links.add(pageLink(base, 0, result.getSize(), "first"));
        if (result.hasPrevious()) {
            links.add(pageLink(base, result.getNumber() - 1, result.getSize(), "prev"));
        }
        links.add(pageLink(base, result.getNumber(), result.getSize(), "self"));
        if (result.hasNext()) {
            links.add(pageLink(base, result.getNumber() + 1, result.getSize(), "next"));
        }
        links.add(pageLink(base, result.getTotalPages() - 1, result.getSize(), "last"));
    }

    return ResponseEntity.ok()
        .header("X-Total-Count", Long.toString(result.getTotalElements()))
        .header("X-Total-Pages", Integer.toString(result.getTotalPages()))
        .header(HttpHeaders.LINK, String.join(", ", links))
        .body(result.getContent());
}

private String pageLink(UriComponentsBuilder base, int page, int size, String rel) {
    String uri = base.cloneBuilder()
        .replaceQueryParam("page", page)
        .replaceQueryParam("size", size)
        .build()
        .encode()
        .toUriString();
    return "<" + uri + ">; rel=\"" + rel + "\"";
}
```

The `pageLink` helper preserves existing filter query parameters and replaces only `page` and `size`, so subsequent pages still apply the same search criteria. The example assumes `PageRequest` uses 0-based page indexing. On an empty page, the code avoids generating `first` or `last` links pointing to negative pages; total pages is still returned as `0`.

If the API does not use Spring Data, you can construct similar URIs and headers from your application's pagination metadata. What matters is that `Link` points to callable URLs and preserves the filters and sorting sent by the client.

## 5. Describing Response Headers with `@ApiResponse`

In OpenAPI, response headers belong in the `headers` section of each response code. Springdoc supports declaring them using `@Header` annotations nested inside `@ApiResponse`:

```java
@ApiResponse(
    responseCode = "201",
    description = "Resource created",
    headers = {
        @Header(
            name = "Location",
            description = "URI of the new resource",
            schema = @Schema(type = "string", format = "uri")
        ),
        @Header(
            name = "ETag",
            description = "Representation validator",
            schema = @Schema(type = "string", example = "\"v42\"")
        )
    }
)
```

Each header should have:

- A header name matching the actual response.
- `description` explaining its purpose, format, or how clients use it.
- `schema` reflecting its value type: string, integer, URI, or appropriate type.
- `example`, which is helpful for headers with special syntax such as ETag or Link.

Do not declare a response header as `@Parameter(in = HEADER)`, because `@Parameter` describes data sent by the client. Request headers such as `If-None-Match` and `If-Match` can use `@Parameter` or `@RequestHeader`; response headers such as `ETag`, `Location`, and `Link` belong in `@ApiResponse(headers = ...)`.

An endpoint can return different headers per status code. For example, `201` returns `Location`, `200` returns `ETag`, `304` returns `ETag` without a body, and `412` indicates precondition failure. Declare each header under the exact response where clients will receive it.

## 6. CORS and Header Readability from Browsers

If a frontend calls the API from a different origin, browsers do not allow JavaScript to read arbitrary response headers. Safelisted headers are exposed per CORS rules; headers such as `ETag`, `Link`, `X-Total-Count`, or `X-Total-Pages` usually must be exposed via `Access-Control-Expose-Headers`.

Spring MVC configuration example:

```java
@Configuration
class WebCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "DELETE")
            .exposedHeaders("Location", "ETag", "Link",
                "X-Total-Count", "X-Total-Pages");
    }
}
```

`exposedHeaders` allows JavaScript to read the listed headers after a successful CORS request. If the application configures CORS in Spring Security, place the corresponding rules in the Security configuration and ensure the CORS filter is applied. CORS only controls whether browsers allow cross-origin frontends to read responses; it does not replace API authentication or authorization.

## 7. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `201` response lacks `Location` | Code sets only the status without building the URI | Use `ResponseEntity.created(uri)` or set the header explicitly. |
| `Location` has the wrong host | Hard-coded host or running behind a reverse proxy | Use a request-based URI builder and configure trusted forwarded headers on proxy/server. |
| ETag does not change after updates | Validator is based on an immutable ID or version is not incremented | Use a version/hash reflecting every representation change. |
| Client always receives `200` instead of `304` | `If-None-Match` is not handled or submitted ETag does not match | Use `checkNotModified` or implement compliant conditional request handling. |
| Updates overwrite someone else's changes | `If-Match` or version not checked on write | Compare current validator and return `412` when the precondition fails. |
| No `next` link even though more data exists | Wrong calculation of `hasNext`, page number, or query parameters | Use pagination metadata from the data source and verify generated URLs. |
| JavaScript cannot read `ETag` or `X-Total-Count` | Header is not exposed via CORS | Add the headers to `exposedHeaders`/`Access-Control-Expose-Headers`. |
| Swagger UI does not display response headers | Missing `@ApiResponse(headers = ...)` or mistakenly declared as a request parameter | Place `@Header` inside the corresponding response code. |

## 8. Header Verification Workflow

After implementation, verify both the HTTP responses and the OpenAPI document:

1. Call the resource-creation endpoint and confirm `201` with `Location` pointing to the new resource.
2. Call the resource-read endpoint and save the returned `ETag` value.
3. Resend the request with `If-None-Match` matching that value; confirm the server returns `304` when data has not changed.
4. Update with the stale `If-Match` after the version has changed; confirm the server returns `412` without overwriting newer data.
5. Call the paginated endpoint on the first, middle, and last pages; confirm `Link` has the appropriate relations and accurate total counts.
6. Call from a cross-origin frontend and confirm JavaScript can read the exposed headers.
7. Open `/v3/api-docs` and verify each response code lists `headers` with the right names, schemas, and descriptions.

Quick curl verification examples:

```bash
# Create a resource and inspect Location.
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customerId":"c-123"}'

# Send the received ETag to verify caching.
curl -i http://localhost:8080/api/orders/8d3f \
  -H 'If-None-Match: "order-v42"'

# Inspect pagination navigation headers.
curl -i 'http://localhost:8080/api/products?page=1&size=20'
```

When testing conditional requests, use the actual ETag returned by the server rather than assuming an example value matches. Curl shows response headers independently of Swagger UI, making it useful for separating runtime issues from documentation issues.

## 9. Guiding Principles

- Return `201 Created` with `Location` when creating a new resource that has a URI for access.
- Use an ETag that reflects the representation version; choose strong or weak validators consistent with your comparison logic.
- Use `If-None-Match` for cache validation and `If-Match` to prevent lost updates.
- Return `Link` for page navigation; clearly document the semantics of custom headers such as `X-Total-Count`.
- Use `@ApiResponse(headers = ...)` to publish response headers per status code.
- Expose headers needed by JavaScript when the API is called cross-origin.
- Verify actual HTTP responses and `/v3/api-docs` after every change.

Response headers supply essential context for clients: `Location` points to newly created resources, `ETag` supports caching and optimistic concurrency control, and `Link` with pagination metadata enables dataset navigation. When Spring code produces the right headers and springdoc documents them on the matching responses, clients can integrate consistently without guessing from the response body.

## References

- [RFC 9110 – HTTP Semantics: Location, ETag, and Conditional Requests](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 8288 – Web Linking: Link header](https://www.rfc-editor.org/rfc/rfc8288)
- [Spring Framework – `ResponseEntity`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html)
- [Spring Framework – `ServletWebRequest.checkNotModified`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/context/request/ServletWebRequest.html)
- [Springdoc OpenAPI – official documentation](https://springdoc.org/)
