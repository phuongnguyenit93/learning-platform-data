# Choosing REST for Browsers and the Broad HTTP Ecosystem

## Learning Objectives

After this lesson, you can:

- Identify when REST/HTTP is the right choice for browsers, mobile apps, and external partners.
- Explain the advantages of HTTP semantics, JSON, URLs, and widespread tooling.
- Distinguish REST APIs from native gRPC and gRPC-Web in browser environments.
- Design endpoints, methods, status codes, pagination, and caching according to HTTP semantics.
- Integrate a REST edge with Spring services and internal gRPC.
- Evaluate trade-offs in latency, payload, contracts, security, and operability.

## 1. Communicating with Browsers and the Broad HTTP Ecosystem

A system may serve many kinds of clients: JavaScript-running browsers, mobile applications, integration partners, automation scripts, and backend services. These clients usually already have an HTTP stack supporting request/response, JSON, TLS, cookies, OAuth/OIDC, proxies, and HTTP debugging tools.

When an API is called directly from a browser or needs broad integration, REST over HTTP usually reduces the barrier to entry. Browsers can use the Fetch API, HTTP libraries, or frontend frameworks without needing a specialized gRPC runtime. Partners can test endpoints using curl, Postman, or similar HTTP tools.

Within the scope of **SPRING_GRPC**, choosing REST for browsers and the broad HTTP ecosystem does not negate the role of gRPC. An architecture can use REST at the system edge, where clients are diverse, and use gRPC between internal services that need Protobuf contracts, typed stubs, deadlines, and streaming.

## 2. What Advantages Do REST and HTTP Bring?

REST is an architectural style based on resources and interaction constraints. REST APIs typically represent resources via URIs, use HTTP methods semantically, and return representations such as JSON.

Key advantages:

- **Ubiquity:** browsers, mobile devices, proxies, API gateways, and partners all have built-in HTTP clients.
- **Standard semantics:** methods, status codes, headers, conditional requests, and caching follow well-known rules.
- **Inspectability:** requests/responses are easy to inspect with devtools, curl, logs, and API gateways.
- **Ecosystem integration:** OpenAPI, OAuth/OIDC, CDNs, WAFs, rate limiting, and API management have broad support.
- **Contract evolution:** JSON often allows clients and servers to evolve independently if compatibility and clear field rules are maintained.

REST does not mean designing arbitrary URL-based APIs. APIs need proper method/status semantics, a contract, and a clear compatibility policy.

## 3. Why Do Browsers Usually Use REST Instead of Native gRPC?

Browsers support HTTP/2 and can send HTTP requests with the Fetch API, but browser APIs do not let JavaScript applications directly control all the transport details native gRPC requires, such as HTTP/2 framing and trailer semantics in the way standard gRPC clients use them.

Therefore, native gRPC clients typically do not run directly in a browser like an HTTP JSON client. There are two common approaches:

- **REST/JSON API:** the browser calls regular HTTP endpoints, receiving JSON and standard statuses/headers.
- **gRPC-Web:** the browser uses a gRPC-Web client/runtime and a server-side proxy or gateway forwards to the gRPC backend.

gRPC-Web is useful when you want to keep **Protocol Buffers (Protobuf)** contracts and part of RPC semantics in the browser. However, it requires tooling, proxies, and compatible configuration; streaming capabilities depend on the implementation. If the browser only needs standard CRUD/queries, REST is usually simpler.

Do not say that browsers do not support HTTP/2. The limitation lies in directly using the native gRPC protocol through browser APIs, not in a lack of HTTP/2 support in browsers.

## 4. Comparing REST, gRPC, and gRPC-Web

| Criterion | REST/JSON | Native gRPC | gRPC-Web |
| --- | --- | --- | --- |
| Browser client | Directly supported via Fetch/XHR | Typically requires client runtime and transport unavailable in browser APIs | Has browser-specific client/runtime |
| Contract | OpenAPI, JSON Schema, or equivalent docs | Protobuf service/message | Usually uses Protobuf |
| Transport | HTTP semantics, HTTP/1.1 or HTTP/2 | HTTP/2 with gRPC framing | HTTP via proxy/gateway using gRPC-Web protocol |
| Debugging | DevTools, curl, Postman | gRPC tools such as grpcurl/specialized GUIs | Tools and runtimes supporting gRPC-Web |
| Payload | Text JSON, easy to read | Binary Protobuf, often compact | Protobuf per gRPC-Web protocol |
| Streaming | SSE/WebSocket or suitable HTTP mechanisms | Unary and all gRPC streaming types | Support depends on client/proxy/implementation |
| HTTP caching | Can use standard cache semantics | Not a typical HTTP resource caching model | More limited than REST resource caching |
| Partner integration | Broad and familiar | Partners need gRPC/Protobuf support | Partners need gRPC-Web support |

Choose based on clients and required semantics. If browsers and HTTP partners are the primary client groups, REST reduces friction. If the browser needs Protobuf contracts or streaming RPC, evaluate gRPC-Web rather than trying to use native gRPC directly.

## 5. Designing Resources and HTTP Methods

A REST API should model resources rather than turning every action into an RPC name in the URL. Example for orders:

| Need | Suggested Method and URI | Meaning |
| --- | --- | --- |
| List orders | GET /api/v1/orders | Read collection, usually supporting filtering/pagination. |
| Read one order | GET /api/v1/orders/{orderId} | Read a specific resource. |
| Create order | POST /api/v1/orders | Create a resource or initiate an operation. |
| Replace entire representation | PUT /api/v1/orders/{orderId} | Perform replacement according to PUT semantics. |
| Partial update | PATCH /api/v1/orders/{orderId} | Modify part of a resource using a published patch format. |
| Delete order | DELETE /api/v1/orders/{orderId} | Request resource deletion per policy. |

Do not use GET to cause side effects. GET is expected to be safe and may be cached or prefetched. PUT and DELETE have idempotent semantics per HTTP; POST is not inherently idempotent. If clients need to retry creation operations, the API can support an idempotency key and clearly specify how the server handles duplicate requests.

## 6. Example REST Controller in Spring

A Spring MVC/WebFlux endpoint can return a JSON representation for the browser:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
final class OrderController {
    private final OrderApplicationService orders;

    OrderController(OrderApplicationService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    ResponseEntity<OrderResponse> getOrder(
            @PathVariable String orderId) {
        return orders.find(orderId)
            .map(order -> ResponseEntity.ok(
                OrderResponse.from(order)))
            .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping
    ResponseEntity<OrderResponse> createOrder(
            @RequestBody CreateOrderRequest request) {
        Order created = orders.create(request);
        URI location = URI.create(
            "/api/v1/orders/" + created.id());

        return ResponseEntity
            .created(location)
            .body(OrderResponse.from(created));
    }
}
~~~

OrderApplicationService contains the business use cases. The controller is responsible for translating HTTP requests/responses to the application API. In an architecture with internal gRPC, the application service or an adapter behind the controller can call generated gRPC clients to communicate with other services.

Illustrative examples require corresponding DTOs and services in the project. Do not expose Protobuf generated messages directly as a public JSON contract if doing so couples the browser API to internal details of the gRPC schema.

## 7. HTTP Status Codes Are Part of the Contract

Status codes tell the client the outcome at the HTTP level:

| Status | Common Meaning |
| --- | --- |
| 200 OK | Request succeeded with a response representation. |
| 201 Created | New resource created; usually includes Location. |
| 202 Accepted | Request accepted but asynchronous processing is not yet complete. |
| 204 No Content | Succeeded with no response body. |
| 400 Bad Request | Request is syntactically malformed or invalid at input level. |
| 401 Unauthorized | Missing or invalid credentials; authentication required. |
| 403 Forbidden | Authenticated but insufficient permissions. |
| 404 Not Found | Resource/route does not exist or is not exposed. |
| 409 Conflict | Conflict with the current state of the resource. |
| 422 Unprocessable Content | Content is understood but fails processing/business rules per API policy. |
| 429 Too Many Requests | Rate limit or quota exceeded. |
| 500 Internal Server Error | Unclassified server error. |
| 502/503/504 | Gateway/upstream error, service temporarily unavailable, or timeout. |

Do not return 200 OK for every outcome and embed custom error codes inside JSON unless there is a clear compatibility reason. Clients, proxies, caches, and monitoring rely on HTTP statuses to behave properly.

## 8. JSON Contracts and API Evolution

JSON is easy to read and widely supported, but its flexibility can also create loose contracts if the server arbitrarily changes field types or meanings.

Rules to apply:

- Publish OpenAPI or an equivalent contract for endpoints, requests, responses, and error models.
- Add new fields in a backward-compatible way; older clients should ignore unknown fields.
- Do not change types or repurpose the meaning of published fields.
- Clearly specify required/optional fields and default semantics.
- Standardize timestamp, decimal, enum, and identifier formats.
- Use a version in the URI or an agreed versioning mechanism when making breaking changes.

JSON numbers can lose precision with large integers when passing through JavaScript Number. For identifiers or integers exceeding the safe integer range, consider representing them as strings and documenting this in the contract.

Do not assume JSON is self-compatible. Compatibility must be verified with contract tests and overlapping client/server rollout versions.

## 9. Pagination, Filtering, and Caching

Browsers often need to load collections page by page instead of fetching all data:

~~~http
GET /api/v1/orders?status=OPEN&pageSize=25&pageToken=eyJvZmZzZXQiOjI1fQ
Accept: application/json
~~~

The response can include items and nextPageToken. Cursor tokens should be server-managed or signed so clients cannot arbitrarily alter query positions. Avoid offset pagination for rapidly changing collections if it causes duplicate/missing items between pages.

HTTP supports cache semantics:

- Cache-Control controls cacheability and lifetime.
- ETag represents a version of the representation.
- If-None-Match allows clients to ask whether the representation has changed.
- 304 Not Modified lets clients reuse their existing cached copy.

Only cache responses when data policy allows it. Personalized responses or responses containing sensitive data need an appropriate cache policy, such as private or no-store. Do not set public caching for identity-dependent responses.

## 10. CORS and Browser Authentication

Browsers enforce the same-origin policy. When a frontend calls an API on a different origin, the server needs appropriate Cross-Origin Resource Sharing (CORS) configuration:

- Allow only necessary origins rather than arbitrary wildcards.
- Allow only HTTP methods and headers that the frontend actually uses.
- Allow credentials only when needed and with specific origins configured.
- Handle OPTIONS preflight requests.
- Do not treat CORS as an authentication or authorization mechanism.

With OAuth 2.0/OIDC, browsers typically obtain an access token through an appropriate flow and send a bearer token in the Authorization header. If session cookies are used, consider CSRF protection and cookie attributes (Secure, HttpOnly, SameSite) based on the deployment model.

TLS protects credentials in transit. The backend must still verify the token, issuer, audience, expiry, and access permissions. Do not trust user IDs or tenant IDs sent by the frontend without checking them against the authenticated principal.

## 11. Streaming and Live Updates for Browsers

REST request/response fits short operations and resource representations. When browsers need continuous updates, you can use:

- **Server-Sent Events (SSE):** the server pushes one-way events over HTTP; browsers have the EventSource API.
- **WebSocket:** a two-way connection for real-time interaction.
- **Polling/long polling:** a simple option when update frequency is low or infrastructure does not support long-lived streams.
- **gRPC-Web:** when you need to preserve Protobuf contracts and the RPC model in the browser, with compatible proxies/runtimes.

Choose based on data direction, reconnect semantics, proxy timeouts, auth, and browser support. SSE does not replace bidirectional streams; WebSocket does not inherently provide Protobuf contracts or gRPC's status/deadline semantics.

## 12. REST Edge Combined with Internal gRPC

A practical architecture can have browsers call a REST API at the edge. The controller authenticates the request, validates input, and calls the application service; the application service uses a gRPC client to call internal backends.

~~~mermaid
flowchart LR
  B["Browser / Mobile / Partner"] -->|"HTTPS + JSON"| A["Spring REST API / Edge"]
  A -->|"gRPC + Protobuf"| O["Order Service"]
  O -->|"gRPC + Protobuf"| I["Inventory Service"]
  O -->|"gRPC + Protobuf"| P["Payment Service"]
  O -->|"Event"| Q["Message Broker"]
~~~

Benefits:

- External clients use accessible HTTP/JSON.
- Internal backends keep typed Protobuf contracts and RPC semantics.
- The edge can enforce API versioning, rate limiting, CORS, and public auth policies.
- Backends can use channel reuse, deadlines, and load balancing.

The risk is that the gateway/controller can become overloaded with orchestration. Keep business use cases in the application/service layer, propagate deadline/correlation context down to gRPC calls, and map backend errors to meaningful HTTP statuses.

## 13. Mapping gRPC Errors to HTTP

When a REST edge calls a gRPC backend, do not return raw internal status text or stack traces to the browser. Map them intentionally:

| gRPC status | Common HTTP mapping | Notes |
| --- | --- | --- |
| INVALID_ARGUMENT | 400 Bad Request | Input validation. |
| UNAUTHENTICATED | 401 Unauthorized | Client needs valid credentials. |
| PERMISSION_DENIED | 403 Forbidden | Authenticated but lacks permission. |
| NOT_FOUND | 404 Not Found | Resource does not exist. |
| ALREADY_EXISTS | 409 Conflict | Duplicate resource/key. |
| FAILED_PRECONDITION | 409 or 422 | Choose according to public contract. |
| RESOURCE_EXHAUSTED | 429 or 503 | Distinguish caller quota from server overload. |
| UNAVAILABLE | 503 Service Unavailable | May be transient; do not expose internal topology. |
| DEADLINE_EXCEEDED | 504 Gateway Timeout | Backend exceeded time budget. |
| INTERNAL / UNKNOWN | 500 Internal Server Error | Return a generic error and correlation ID. |

This mapping is not a mandatory conversion table for every system. Public APIs must define stable semantics, avoiding accidentally turning backend implementation statuses into the external contract.

## 14. Protecting Latency Across the REST Edge

When a REST controller calls gRPC backends, total latency includes HTTP/JSON parsing, edge logic, gRPC network, backend processing, and response mapping. Set gRPC deadlines based on the remaining HTTP request budget, rather than giving each backend the caller's full timeout.

If a request calls multiple backends sequentially, divide the latency budget intentionally. If calling in parallel, limit concurrency and cancel unneeded calls when the overall request times out. Avoid unbounded retries because they can amplify load when a backend is failing.

Propagate correlation/trace context via HTTP headers and gRPC metadata to observe the full path. Do not write bearer tokens or personal data into logs/traces.

## 15. When Is REST Not the Best Choice?

REST may not be the best fit when:

- Internal services have very high RPC frequency and need type-safe Protobuf contracts between JVMs.
- Client/server/bidirectional streaming with flow control and gRPC semantics is required.
- Payloads are large, repetitive structures where binary serialization gains have been confirmed by benchmarks.
- Callers consistently need RPC-level deadlines, cancellation, and status semantics.
- All clients control their gRPC runtime and infrastructure supports end-to-end HTTP/2.

Even in these cases, REST can still serve as the public edge. The decision does not have to be uniform between external APIs and inter-backend communication.

## 16. Common Mistakes When Choosing REST for Browsers

| Mistake | Consequence | Mitigation |
| --- | --- | --- |
| Calling native gRPC directly from Fetch like HTTP JSON | Browsers do not implement gRPC framing/trailer semantics like native clients | Use REST or gRPC-Web/proxy. |
| Assuming browsers do not support HTTP/2 | Misunderstands protocol limitations | Distinguish HTTP/2 support from native gRPC client APIs. |
| Using POST for every operation | Loses HTTP method/cache/idempotency semantics | Model resources and appropriate methods. |
| Returning 200 for all errors | Clients/proxies/monitoring struggle to classify failures | Use contract-accurate status codes. |
| Lacking OpenAPI/schema | Integrating clients rely on guesswork | Publish and test contracts. |
| Returning unpaginated collections | Large payloads, rising latency and memory | Use cursor/page tokens and limit page size. |
| Caching personal data as public | Data leakage across users | Use private/no-store per policy. |
| Treating CORS as API security | Clients not blocked by CORS can still call from elsewhere | Enforce authentication and authorization on the server. |
| Uncontrolled exposure of internal Protobuf as public JSON | Public API gets locked to backend schema | Create independent DTOs/public contracts when needed. |
| REST edge not propagating deadlines to backends | HTTP request times out while RPC still consumes resources | Propagate time budgets and cancellation. |

## 17. Decision Matrix

| Question | If the answer is "yes" | Direction to consider |
| --- | --- | --- |
| Do browsers/partners need to call directly via standard HTTP clients? | Yes | REST/JSON is usually suitable. |
| Is resource caching via HTTP semantics needed? | Yes | REST has a clear advantage. |
| Does the API need to be easy to test with DevTools, curl, and Postman? | Yes | REST reduces friction. |
| Do browser clients need Protobuf/RPC semantics? | Yes | Evaluate gRPC-Web and proxies. |
| Does backend-to-backend need typed contracts, latency, and streaming? | Yes | Native gRPC is a strong candidate. |
| Are durable events and independent consumer processing needed? | Yes | A message broker is a better fit. |
| Does the system need a stable public API while backends use gRPC? | Yes | Use a REST edge and internal gRPC. |

Evaluate the client ecosystem, latency, contracts, caching, security, observability, and operational capability together. Do not pick a protocol based on a single serialization metric.

## 18. Hands-on Exercise

Design an API for an ordering application with a browser frontend and Spring backends:

1. Define REST endpoints for the browser to create orders, read an order, and list orders with pagination.
2. Choose HTTP methods/status codes and idempotency rules for creation.
3. Write an OpenAPI contract and JSON DTOs independent of internal Protobuf.
4. Design a Spring controller calling OrderService via a gRPC client.
5. Set deadlines based on the HTTP request budget and map gRPC statuses to HTTP statuses.
6. Configure CORS, TLS, OAuth/OIDC, and cache policies for personal data.
7. Add trace/correlation propagation from HTTP headers to gRPC metadata.
8. Evaluate the case where the browser needs real-time updates: choose SSE, WebSocket, or gRPC-Web and explain why.
9. Measure p50/p95/p99, payload size, and throughput for the REST edge with the gRPC backend.

**Completion criteria:** the browser uses an easy-to-integrate HTTP API, backends keep gRPC contracts where appropriate, the public contract is stable, and latency/security budgets are propagated across hops.

## 19. Takeaways

- REST/HTTP fits browsers and broad integration ecosystems thanks to Fetch, JSON, statuses/headers, caching, and ubiquitous tooling.
- Browsers support HTTP/2 but do not provide native gRPC client APIs equivalent to a gRPC runtime; use REST or gRPC-Web as needed.
- Design resources, HTTP methods, status codes, pagination, and caching according to standard semantics.
- Publish OpenAPI/JSON contracts and manage compatibility; JSON does not automatically guarantee backward compatibility.
- CORS does not replace authentication/authorization; TLS and token verification remain mandatory per the threat model.
- A REST edge can call internal gRPC to preserve typed Protobuf contracts and deadlines.
- Map gRPC errors to HTTP according to public API semantics without exposing backend details.
- Choose SSE, WebSocket, or gRPC-Web when browsers need live updates/streaming, depending on data direction and infrastructure.
- Measure end-to-end latency and tail latency before concluding whether REST or gRPC fits better.

Choose REST for browsers and the broad HTTP ecosystem when accessibility, caching, tooling, and client compatibility are priorities; you can still use gRPC internally to optimize service-to-service communication.
