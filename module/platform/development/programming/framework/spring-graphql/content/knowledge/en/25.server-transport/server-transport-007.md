# GraphQL response content type

GraphQL over HTTP uses HTTP headers to describe request and response formats. The request `Content-Type` tells the server what format the body is sent in; `Accept` tells the server which response formats the client can receive. These two headers have different roles and must not be used interchangeably.

For standard HTTP requests in Spring for GraphQL, clients send a GraphQL request envelope as JSON, typically using `Content-Type: application/json`. On the return path, the dedicated media type `application/graphql-response+json` describes a GraphQL JSON response; `application/json` is still widely used for compatibility with older clients and servers. Choosing the right media type helps clients distinguish a GraphQL response from ordinary JSON and handle status codes more consistently.

After this lesson, you will be able to:

- Distinguish request `Content-Type`, response `Content-Type`, and request `Accept`.
- Understand `application/json` and `application/graphql-response+json`.
- Send GraphQL queries/mutations over HTTP with appropriate headers.
- Understand the relationship between media types and HTTP status codes.
- Recognize 406, 415 errors, and GraphQL errors in the response body.
- Test content negotiation in Spring for GraphQL.
- Distinguish HTTP response media types from WebSocket, SSE, and incremental delivery.

## 1. Content-Type and Accept serve different roles

HTTP has two important headers when exchanging content:

| Header | Direction | Meaning |
| --- | --- | --- |
| Request `Content-Type` | Client → Server | Format of the request body |
| Request `Accept` | Client → Server | Response formats the client accepts |
| Response `Content-Type` | Server → Client | Actual format of the response body |

Example of a client sending a JSON GraphQL request and preferring the GraphQL response media type:

```http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/graphql-response+json, application/json;q=0.9

{
  "query": "query Book($id: ID!) { book(id: $id) { id title } }",
  "operationName": "Book",
  "variables": {
    "id": "book-42"
  }
}
```

The server reads the request body according to `Content-Type: application/json`, then selects a response representation matching `Accept`. If the dedicated media type is chosen, the response may be:

```http
HTTP/1.1 200 OK
Content-Type: application/graphql-response+json; charset=UTF-8

{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL in Practice"
    }
  }
}
```

`Accept` does not describe the request body format. Conversely, the request `Content-Type` does not tell the server which format to return. If a client sends only `Content-Type` without `Accept`, the server falls back to the adapter/framework's default rules.

## 2. The GraphQL request envelope is JSON

A GraphQL HTTP request typically sends a JSON object with these properties:

```json
{
  "query": "query Books { books { id title } }",
  "operationName": "Books",
  "variables": {},
  "extensions": {}
}
```

- `query`: GraphQL document as a string.
- `operationName`: name of the operation to execute when the document contains multiple operations; can be omitted if there is only one operation.
- `variables`: map of input variables for the operation.
- `extensions`: extension metadata agreed upon between client and server.

This is a JSON envelope, so standard request bodies use `Content-Type: application/json`. Do not set `Content-Type: application/graphql-response+json` on the request envelope just because the server returns responses with that media type; that media type name is reserved for GraphQL responses.

Some legacy systems or extensions may support sending a raw GraphQL document with a separate media type, but that is not the standard JSON envelope used by Spring for GraphQL. Always use the format supported by your application's HTTP handler.

## 3. application/json and application/graphql-response+json

Two common media types for HTTP responses:

| Media type | Meaning | Scenario |
| --- | --- | --- |
| `application/json` | Generic JSON | Compatible with many existing clients and servers |
| `application/graphql-response+json` | JSON with GraphQL response structure | Dedicated media type recommended by GraphQL over HTTP |

`application/graphql-response+json` still contains a JSON body with fields such as `data`, `errors`, and optionally `extensions`. The difference is that the media type explicitly declares that the body conforms to the GraphQL response shape, telling clients this is the result of a GraphQL operation rather than an arbitrary JSON document.

This media type carries the `+json` suffix, allowing clients to recognize JSON syntax via the structured syntax suffix convention. However, clients should still check the full media type instead of guessing solely from the body content.

`application/json` remains important because many older clients, proxies, and servers only support it. During migration periods, clients typically send both values in `Accept`, prioritizing `application/graphql-response+json` with a higher quality value.

## 4. Response media type does not change based on whether errors occur

The media type describes the response format, not whether the operation succeeded or failed. A GraphQL response can be:

- Only `data` when all fields succeed.
- Both `data` and `errors` when some fields fail.
- Only `errors` when the request is invalid before execution.
- `data: null` together with `errors` when an execution error bubbles up to the root due to non-null propagation.

All of the cases above are still GraphQL responses. If the server has selected `application/graphql-response+json`, the response media type does not need to change merely because the `errors` array appears.

Partial data example:

```http
HTTP/1.1 200 OK
Content-Type: application/graphql-response+json

{
  "data": {
    "book": {
      "id": "book-42",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service is unavailable",
      "path": ["book", "author"],
      "extensions": {
        "code": "UPSTREAM_UNAVAILABLE"
      }
    }
  ]
}
```

Clients must inspect the GraphQL envelope rather than relying only on the media type name or status code to conclude that all fields succeeded.

## 5. Accept negotiation for GraphQL responses

Clients can declare multiple response media types in priority order:

```http
Accept: application/graphql-response+json, application/json;q=0.9
```

The quality value `q` indicates relative preference; the default value is `1`. In this example, the client prefers `application/graphql-response+json` but still accepts `application/json` if the server does not yet support the newer media type.

The server must pick a representation supported by both sides. If the client does not accept any response media type the server can produce, HTTP content negotiation may end with `406 Not Acceptable`.

When supporting multiple response media types, the server should return the exact chosen `Content-Type` and may need `Vary: Accept` so caches/proxies distinguish responses by the `Accept` header. Never hardcode `application/graphql-response+json` in a response filter if the handler actually serialized another representation or does not support the corresponding semantics.

## 6. HTTP status codes and GraphQL responses

HTTP status codes describe outcomes at the HTTP layer; GraphQL `data` and `errors` describe outcomes at the GraphQL layer. The two layers are related, not identical.

With the dedicated `application/graphql-response+json` media type, GraphQL over HTTP enables clearer separation between pre-execution request errors and execution results. Exact rules follow the specification version and implementation, though the direction is:

- Requests that cannot be executed due to syntax, validation, or variable coercion errors can be represented with HTTP 4xx.
- Once GraphQL execution produces an execution result—even a response with partial data and `errors`—the response typically uses HTTP 2xx.
- HTTP or server errors occurring before a GraphQL response can be built can use the corresponding 4xx/5xx status.

With the legacy `application/json` media type, many older clients expect to read the GraphQL envelope even when the status is not 2xx. For compatibility, implementations may preserve status 200 for valid GraphQL responses and let clients read `errors` from the body. Check the behavior of your Spring for GraphQL version and HTTP adapter instead of assuming status mappings.

Example illustrating the two layers:

| Scenario | HTTP layer | GraphQL layer |
| --- | --- | --- |
| Request body is not valid JSON | May be 400 | No GraphQL response yet |
| `Accept` has no matching representation | 406 | Operation not executed |
| Query calls a nonexistent field | Status depends on response media type/implementation | Request error in `errors` |
| Resolver fails on a nullable field | Usually 2xx when an execution result exists | May contain both `data` and `errors` |
| Server error before creating response | 5xx | May lack a GraphQL envelope |

Do not use HTTP 200 as sole proof of business success; likewise, do not use HTTP 4xx as a substitute for reading `errors` and `extensions.code`.

## 7. Distinguishing 400, 406, and 415

Common status codes encountered when configuring the endpoint:

| Status | Meaning | Example |
| --- | --- | --- |
| `400 Bad Request` | Request is invalid at HTTP or GraphQL request parsing/coercion per server mapping | Malformed JSON body or request envelope missing required fields |
| `406 Not Acceptable` | Server cannot produce any response representation requested by the client | `Accept: application/xml` when the endpoint only returns JSON |
| `415 Unsupported Media Type` | Server does not support the format of the sent request body | Sending a JSON body with `Content-Type: text/plain` |

Exact status codes can depend on the HTTP adapter, framework version, and failure stage. For example, a GraphQL query failing validation may be returned as a GraphQL request error rather than an HTTP parser error. Determine how far the request progressed before classifying it.

## 8. Sending requests with curl

Example sending a query via a JSON envelope and preferring the dedicated response media type:

```bash
curl -i https://localhost:8080/graphql \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/graphql-response+json, application/json;q=0.9' \
  --data '{"query":"query { books { id title } }"}'
```

Read both the status line and `Content-Type` in the response headers. Do not look only at the JSON body, because the exact same body can be returned with different media types or status codes.

To check legacy fallback:

```bash
curl -i https://localhost:8080/graphql \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"query":"query { books { id title } }"}'
```

Compare the response headers to confirm the server selects the media type according to `Accept`. If both requests always return the same media type, that may be the current adapter behavior; cross-check with your Spring for GraphQL version.

## 9. GET and POST in GraphQL over HTTP

GraphQL over HTTP typically supports POST with a JSON request envelope. GET can use URL-encoded query parameters such as `query`, `operationName`, `variables`, and `extensions`.

GET example:

```http
GET /graphql?query=%7Bbooks%7Bid%20title%7D%7D HTTP/1.1
Accept: application/graphql-response+json, application/json;q=0.9
```

GET is only suitable for query operations. Mutations must not be sent over GET because GET has safe semantics and can be cached, prefetched, or re-executed by intermediaries. Use POST for mutations.

With GET, there is no request body so `Content-Type` is usually unnecessary; `Accept` still describes the response the client wants to receive. With JSON POST, `Content-Type: application/json` is required and `Accept` can be added to select the response representation.

## 10. Spring for GraphQL and HTTP content negotiation

Spring for GraphQL provides HTTP transport via `GraphQlHttpHandler` with adapters for Spring MVC or WebFlux. Spring Boot can auto-configure the endpoint based on starters and application properties. Requests are converted into `WebGraphQlRequest`, then pass through interceptors and the GraphQL execution service.

When working with content types, verify three points in your exact application version:

1. Which request `Content-Type` values the HTTP adapter accepts.
2. Whether the adapter/framework supports `Accept` negotiation between `application/graphql-response+json` and `application/json`.
3. Which `Content-Type` and status codes are actually written for request errors, execution results, and transport errors.

Do not set response headers manually in a filter without aligning content negotiation and status mapping. Headers must reflect the actual serialized representation. If the current adapter only supports `application/json`, keep that contract until you upgrade or configure an implementation supporting the full GraphQL response media type.

The `spring.graphql.path` property can change the endpoint path, but does not determine all media types supported by the adapter. Content negotiation also depends on the HTTP handler, message converters/codecs, and the Spring for GraphQL/Spring Framework version.

## 11. Example HTTP testing with WebTestClient

With WebFlux or a `WebTestClient`-based test client, you can verify request and response headers directly:

```java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(
                MediaType.parseMediaType("application/graphql-response+json"),
                MediaType.APPLICATION_JSON)
        .bodyValue(Map.of(
                "query", "query { books { id title } }"))
        .exchange()
        .expectStatus().is2xxSuccessful()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/graphql-response+json"));
```

This test assumes your project's endpoint and adapter already support `application/graphql-response+json`. If the application currently returns only `application/json`, assertions should reflect the configured contract; do not modify tests to force a header the server does not actually support.

In addition to media type, assert on the body envelope:

```java
.expectBody()
.jsonPath("$.data.books").exists();
```

For error requests, check both the status code and the response body according to the negotiated media type. In particular, verify that clients do not discard the GraphQL error body simply because the HTTP status is not 2xx.

## 12. Testing fallback and content negotiation errors

Consider dedicated tests for:

1. Client sends `Accept: application/graphql-response+json` and the server returns that media type if supported.
2. Client sends `Accept: application/json` and the server returns legacy JSON.
3. Client sends both media types with quality values and the server picks the preferred compatible representation.
4. Client sends an unsupported `Accept` and the server returns 406 as configured.
5. Client sends a JSON request body with `Content-Type: application/json` and the server parses the envelope.
6. Client sends an unsupported request media type and the server returns 415 per adapter behavior.
7. Query validation errors return the expected GraphQL error envelope and status mapping.
8. Execution errors with partial data are still read properly by clients.
9. Response headers match the actual representation, including charset if declared.
10. Proxies/gateways do not alter or strip media types and statuses unexpectedly.

If the project uses `MockMvc`, write equivalent checks with `MockMvc`. If using `HttpGraphQlTester`, remember that the tester focuses on GraphQL interactions; when you need to assert HTTP headers/status codes, use the tester or a web test client at the transport layer.

## 13. Subscriptions and transport content types

Not all GraphQL results are delivered as a standard HTTP JSON response.

| Exchange type | Common transport/media type or protocol |
| --- | --- |
| Query/mutation over HTTP | JSON request/response; response may be `application/graphql-response+json` or `application/json` |
| Subscription over WebSocket | WebSocket subprotocol, typically `graphql-transport-ws`; does not use HTTP JSON response `Content-Type` per event |
| Subscription over Server-Sent Events | `text/event-stream` |
| Incremental delivery | Can use `multipart/mixed` if supported by server, client, and implementation version |

A WebSocket handshake still begins over HTTP, but after upgrade, GraphQL messages travel over the WebSocket subprotocol. SSE uses an HTTP response stream with its own content type. Therefore, do not mechanically apply `application/graphql-response+json` to every subscription event.

Likewise, `multipart/mixed` must not be enabled merely by changing headers. The server must actually emit proper multipart boundaries and payload formatting that the client understands. Check support across your Spring for GraphQL version, GraphQL Java, and transport adapter before using incremental delivery.

## 14. Charset and JSON encoding

Modern JSON over HTTP is typically encoded in UTF-8. Response headers may appear as:

```http
Content-Type: application/graphql-response+json; charset=UTF-8
```

Clients must not assume the response is UTF-16 or uses the OS default encoding. The server must serialize JSON consistently and preserve Unicode characters, such as accented Vietnamese characters.

Do not manually append `charset` to headers if the message converter/codec already manages encoding. Avoid situations where the header claims UTF-8 while the actual body is encoded in another charset.

## 15. Caching, proxies, and Vary: Accept

HTTP caches and reverse proxies can store responses based on URL, method, and certain request headers. If the same endpoint returns two representations depending on `Accept`, caches need to know the response depends on that header.

The header:

```http
Vary: Accept
```

tells caches that the representation can vary based on `Accept`. Without `Vary: Accept`, a misconfigured proxy could serve an `application/json` representation to a client that only accepts `application/graphql-response+json`, or vice versa.

GraphQL POST requests are typically not cached like GET by default. If you allow caching GET queries, carefully consider variables in URLs, authorization, tenants, cookies, and cache keys. Never cache responses containing private data in shared caches without proper partitioning policies.

## 16. CORS and browser clients

Browser clients can send `Accept` and `Content-Type` via CORS. `Content-Type: application/json` usually triggers a preflight for cross-origin requests because it is not a CORS-safelisted content type in many cases. The server must allow the appropriate origins, methods, and headers.

If the client sends an `Authorization` header or custom headers, CORS configuration must allow those headers. Response `Content-Type` is exposed to browsers by default as a basic response header; if clients need to read non-default headers, configure `Access-Control-Expose-Headers` accordingly.

Do not use CORS instead of authentication or authorization. CORS is a browser policy controlling whether JavaScript on another origin can read responses; it does not prevent direct HTTP clients from calling the endpoint.

## 17. Common errors

- **Confusing `Accept` with request `Content-Type`:** one header describes the desired response, while the other describes the request body.
- **Sending `application/graphql-response+json` for the JSON request envelope:** that media type describes GraphQL responses.
- **Sending only `Accept: application/json` while expecting the server to automatically pick the dedicated media type:** the server chooses based on negotiation and actual support.
- **Always hardcoding response `Content-Type`:** headers may mismatch the serialized representation.
- **Assuming the presence of `errors` requires a 4xx response:** execution results with partial data are still typically 2xx responses.
- **Relying on HTTP 200 to conclude business success:** you must inspect `data`, `errors`, and `extensions`.
- **Using GET for mutations:** GET can be cached or prefetched and is unsuitable for state-changing operations.
- **Confusing HTTP JSON responses with WebSocket/SSE subscriptions:** each transport has its own protocol and content type.
- **Changing the header to `multipart/mixed` when the body is not multipart:** the media type must match the actual format.
- **Omitting `Vary: Accept`:** caches/proxies may serve the wrong representation.
- **Not testing through the real HTTP adapter:** `GraphQlTester` at the execution layer does not fully verify HTTP headers and status codes.
- **Treating CORS as an API security mechanism:** Spring Security and server-side authorization are still required.

## 18. Workflow for designing GraphQL response content types

When configuring HTTP transport for Spring for GraphQL, follow these steps:

1. Choose the JSON request envelope and verify the request `Content-Type` is supported by the adapter.
2. Determine which response media types the server supports: `application/graphql-response+json`, `application/json`, or both.
3. Configure clients to send `Accept` in the appropriate priority and fallback order.
4. Ensure response `Content-Type` reflects the actual serialized JSON representation.
5. Define status mappings for request errors, execution results, and HTTP errors based on media type/implementation.
6. Return 406 when no acceptable representation exists and 415 when the request media type is unsupported, per the adapter contract.
7. Test successful queries, partial data, request errors, and invalid content negotiation over HTTP.
8. Check `Vary: Accept`, proxies, caches, and CORS if the endpoint is called from browsers.
9. Handle WebSocket, SSE, and multipart incremental delivery as separate transports/representations.
10. Document media types, status codes, and fallback behavior clearly in API documentation.

`Content-Type` and `Accept` are part of the HTTP contract between clients and the GraphQL server. JSON request envelopes typically use `application/json`; responses can use the dedicated `application/graphql-response+json` media type or legacy `application/json` depending on capabilities and compatibility policies. In Spring for GraphQL, verify your HTTP adapter and framework version behavior with integration tests, ensuring headers match bodies and status mappings. By cleanly separating HTTP transport from GraphQL execution and subscription transports, clients can handle responses, errors, and partial data consistently.

## References

- [GraphQL over HTTP Specification](https://graphql.github.io/graphql-over-http/draft/)
- [Spring for GraphQL — HTTP Transport](https://docs.spring.io/spring-graphql/reference/transports.html#transports.http)
- [Spring for GraphQL — GraphQlHttpHandler API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/GraphQlHttpHandler.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [MDN — Content-Type](https://developer.mozilla.org/docs/Web/HTTP/Headers/Content-Type)
- [MDN — Accept](https://developer.mozilla.org/docs/Web/HTTP/Headers/Accept)
