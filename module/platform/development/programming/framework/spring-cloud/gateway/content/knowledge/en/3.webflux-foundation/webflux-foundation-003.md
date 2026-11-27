# ServerWebExchange, ServerHttpRequest, and ServerHttpResponse

## 1. Why Are These Three Types Important to Spring Cloud Gateway?

In **Spring WebFlux**, an incoming HTTP request entering the application is not handled through the Servlet API's `HttpServletRequest`/`HttpServletResponse` pair. WebFlux uses server-side HTTP types designed to compose with asynchronous and reactive processing flows:

- **`ServerHttpRequest`** represents the client's incoming request: method, URI, path, headers, cookies, query parameters, and body stream.
- **`ServerHttpResponse`** represents the response the server prepares to return: status, headers, cookies, and how the body is written.
- **`ServerWebExchange`** is the context for **a single HTTP exchange**, linking the request, response, and related processing metadata together.

In the **WebFlux Foundation** chapter of **SPRING_CLOUD_GATEWAY**, understanding these three types is a prerequisite for writing gateway filters properly. Spring Cloud Gateway uses route predicates to select a route, the filter chain to authenticate or enforce rate limits, rewrite paths/headers, discover service instances, and forward requests. All of those operations need to read or update data in the exchange; circuit breakers, retries, TLS, and request observability also hook into corresponding stages.

> **Scope:** This lesson covers **Spring Cloud Gateway Server WebFlux** (commonly using Reactor Netty). The Gateway Server MVC variant uses the Servlet/MVC model, so its APIs and filters are not identical.

### Learning Objectives

After completing this lesson, you will be able to explain the relationship between these three objects, know when to read or mutate request/response data, use `exchange.mutate()` and `request.mutate()` in a `GlobalFilter`, recognize when a response is **committed**, and avoid common pitfalls with reactive bodies and security headers.

## 2. How Does an Exchange Connect Request and Response?

When WebFlux receives a request, the framework provides a `ServerWebExchange` to processing components. The exchange lives for the scope of that handling pass, allowing filters to access the current request, response, and attributes used to share metadata.

~~~mermaid
flowchart TD
    C["Client"] -->|"HTTP request"| W["WebFlux WebFilter chain"]
    W --> E["ServerWebExchange"]
    E --> Q["ServerHttpRequest<br/>method, path, headers, body"]
    E --> R["ServerHttpResponse<br/>status, headers, body writer"]
    E --> A["Exchange attributes<br/>route, target URL, internal metadata"]
    E --> G["Gateway route matching<br/>and gateway filter chain"]
    G --> S["Backend microservice"]
    S -->|"HTTP response"| R
    R -->|"Commit and write response"| C
~~~

The diagram illustrates **data relationships**, not that the backend directly operates on the response object inside the gateway's JVM: the gateway receives an HTTP response from the backend and writes the corresponding data to its own `ServerHttpResponse`.

| Object | Answers the question | How to get from exchange | Characteristics |
| --- | --- | --- | --- |
| `ServerHttpRequest` | "What did the client just send?" | `exchange.getRequest()` | API for reading request info; to change path/headers, build a new request via builder/decorator. |
| `ServerHttpResponse` | "What will the server return?" | `exchange.getResponse()` | Allows setting status/headers, registering pre-commit hooks, and writing reactive bodies. |
| `ServerWebExchange` | "How is the entire exchange progressing?" | Passed into filter/handler | Holds request, response, attributes, session/principal info, and the ability to create a mutated exchange with replaced request/response. |

The request and response flows live inside **one exchange**, but the two directions typically execute at different times: pre-filters run before the downstream call; post-filters run after the downstream chain completes.

## 3. ServerHttpRequest: Reading the Incoming Request

`ServerHttpRequest` is the WebFlux interface representing the request received by the server. Common methods include:

| API | Value or meaning |
| --- | --- |
| `getMethod()` | HTTP method such as `GET`, `POST`, `PUT` |
| `getURI()` | Request URI in the current context |
| `getPath()` | `RequestPath`: the path parsed into structured components |
| `getHeaders()` | HTTP request headers as `HttpHeaders` |
| `getQueryParams()` | Query parameters as `MultiValueMap<String, String>` |
| `getCookies()` | Cookies sent by the client |
| `getRemoteAddress()` | Address of the connected peer (which may be a reverse proxy) |
| `getBody()` | `Flux<DataBuffer>` containing the streamed body data |
| `mutate()` | Creates a builder to transform the request without directly mutating the original object |

Example of reading information in a gateway filter:

~~~java
ServerHttpRequest request = exchange.getRequest();

HttpMethod method = request.getMethod();
String path = request.getPath().value();
String clientRequestId = request.getHeaders().getFirst("X-Request-Id");
String expand = request.getQueryParams().getFirst("expand");
~~~

The snippet above only **reads metadata**. It does not trigger body consumption and does not send any request to the backend.

### 3.1. Requests Are Treated as Immutable

You should not assume you can grab `request.getHeaders()` and arbitrarily mutate headers on the original request. To transform HTTP info, use the builder:

~~~java
ServerHttpRequest updatedRequest = exchange.getRequest()
        .mutate()
        .path("/orders/42")
        .headers(headers -> headers.set("X-Edge-Source", "gateway"))
        .build();

ServerWebExchange updatedExchange = exchange.mutate()
        .request(updatedRequest)
        .build();

return chain.filter(updatedExchange);
~~~

Filters downstream of `chain.filter(updatedExchange)` see the transformed request. Components that already executed earlier **do not re-run** and do not retroactively receive the new request. This is especially important for **route predicates**: Spring Cloud Gateway normally selects the route using the current request **before** running gateway filters such as `StripPrefix` or `RewritePath`.

In real applications, if you only need to change paths/headers, prefer built-in filters (`StripPrefix`, `RewritePath`, `SetRequestHeader`, etc.) for concise configuration and predictable ordering.

### 3.2. Path and URI Can Differ by Stage

Suppose a client calls:

~~~http
GET /api/orders/42?expand=items HTTP/1.1
Host: api.example.test
~~~

If the route applies `StripPrefix=1`, the forwarded path becomes `/orders/42`, while the query `expand=items` is preserved. A filter running **before** the transformation can read path `/api/orders/42`; a filter running **after** sees path `/orders/42`. The final target URI is stored by the gateway in an internal attribute and often also depends on service discovery/load balancing results.

You cannot infer the exact backend URL from `getURI()` at every point in time. When troubleshooting, distinguish the **client-requested URI**, the **filter-transformed request**, and the **actual URL received by the backend**.

### 3.3. The Body Is a Publisher, Not an In-Memory String

`getBody()` returns `Flux<DataBuffer>`. The body may arrive across multiple buffers, is consumed asynchronously, and usually **cannot be read arbitrarily multiple times** like an in-memory string. A filter that consumes the entire body without re-emitting it to the chain can cause the backend to receive an empty body or fail the request.

Therefore:

- For routing, logging, or auth that only needs method/path/headers, **do not read the body**.
- When you must transform a JSON body, prefer the `ModifyRequestBody` mechanism appropriate for your Spring Cloud Gateway version, or use a decorator/caching approach with proper `DataBuffer` handling.
- Avoid `block()` or ad-hoc `subscribe()` inside filters; the reactive chain must be **returned** to the framework to subscribe and execute.
- Do not concatenate a large body into a `String` just to log it; large payloads put pressure on memory, and sensitive contents may be leaked in logs.
- Whenever retaining, replacing, or releasing a `DataBuffer` manually, understand buffer ownership and release rules; misuse can leak memory, especially with Netty pooled buffers.

## 4. ServerHttpResponse: Preparing, Committing, and Writing Responses

`ServerHttpResponse` represents the HTTP response sent by the gateway to the client. Typical APIs:

| API | Purpose |
| --- | --- |
| `setStatusCode(HttpStatusCode)` | Sets HTTP status before the response is committed |
| `getStatusCode()` | Gets the currently configured status, which may not yet be explicitly set |
| `getHeaders()` | Reads/updates HTTP response headers before commit |
| `addCookie(...)` | Registers a response cookie |
| `beforeCommit(Supplier<Mono<Void>>)` | Registers an action to run before headers/status are written to the connection |
| `isCommitted()` | Checks whether the response has already been committed |
| `setComplete()` | Completes the response asynchronously; often used to short-circuit a request with an empty-body response |
| `writeWith(Publisher<? extends DataBuffer>)` | Writes the body from a reactive data stream |
| `bufferFactory()` | Provides a factory to allocate `DataBuffer` instances when writing data manually |

Example of rejecting a rate-limited request, inside a filter that **has definitively determined the rejection condition**:

~~~java
ServerHttpResponse response = exchange.getResponse();
response.setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
return response.setComplete();
~~~

Here the filter **does not call** `chain.filter(exchange)`, so the request does not continue through remaining gateway filters or reach the backend. This differs from the backend itself returning 429: where the status originates directly affects diagnostics.

### 4.1. What Does "Commit" Mean?

Before commit, the gateway can set status codes and headers. Once the response begins to be sent (or when an operation completes the response), the framework executes `beforeCommit` callbacks and writes HTTP metadata out to the connection. **After commit**, modifying status/headers generally has no effect or is disallowed.

Example of registering a header before the response is written:

~~~java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
            .set("X-Gateway", "spring-cloud-gateway");
    return Mono.empty();
});

return chain.filter(exchange);
~~~

Callbacks must be registered **before** the response commits; calling `beforeCommit(...)` itself does not mean the body has already been sent. You should also never call `setComplete()` after the backend has begun streaming the response.

### 4.2. The Response Body Is Still a Reactive Stream

When proxying large files or Server-Sent Events (SSE), the gateway can forward buffers incrementally instead of buffering the entire response in memory. Inspecting or transforming the response body usually requires a `ServerHttpResponseDecorator` or a dedicated filter that respects backpressure and properly releases buffers. Adding a header via `beforeCommit` is much simpler and safer than manually intercepting the body.

If the backend has already streamed part of the response and the connection drops, the gateway cannot always turn the response back into a JSON error with status 500, because the HTTP status may already have been sent. This is one reason to monitor both connection errors and commit state when operating a gateway.

## 5. ServerWebExchange: The Context Connecting Steps

`ServerWebExchange` is passed into `WebFilter`, `GlobalFilter`, `GatewayFilter`, and many other WebFlux APIs. Beyond `getRequest()`/`getResponse()`, the exchange provides:

| Member | Usage |
| --- | --- |
| `getAttributes()`, `getAttribute(name)` | Stores **internal per-request** metadata between filters, such as a correlation ID or selected route |
| `mutate()` | Creates an exchange decorator with replaced request/response |
| `getPrincipal()` | Returns `Mono<Principal>`, if an identity is provided by authentication |
| `getSession()` | Accesses `WebSession` asynchronously when needed |
| `getLocaleContext()` | Accesses locale information |
| `getFormData()`, `getMultipartData()` | APIs to parse form/multipart data when truly needed; affects body consumption |

Example of storing metadata for downstream filters:

~~~java
exchange.getAttributes().put("demo.startNanos", System.nanoTime());

Long started = exchange.getAttribute("demo.startNanos");
~~~

**An exchange attribute is not an HTTP header.** Attributes live inside the gateway's request processing scope; neither the backend nor the client automatically receives them. Conversely, headers are part of the HTTP message and can travel over the network. Never copy secrets from attributes into headers without an explicit requirement and proper protections.

Spring Cloud Gateway also stores routing metadata in the exchange, for example:

~~~java
import java.net.URI;
import org.springframework.cloud.gateway.route.Route;
import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR;
import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils.GATEWAY_REQUEST_URL_ATTR;

Route selectedRoute = exchange.getAttribute(GATEWAY_ROUTE_ATTR);
URI targetUri = exchange.getAttribute(GATEWAY_REQUEST_URL_ATTR);
~~~

`GATEWAY_ROUTE_ATTR` can be present after a route is selected; `GATEWAY_REQUEST_URL_ATTR` is usually populated only after the gateway resolves the routing URL. Before those respective steps, values may be `null`. These are **internal metadata**; do not overwrite special gateway attributes unless you understand the impact on routing, load balancing, and retries.

### Mutation Does Not Mean Creating a New Network Request

The two mutations below play distinct roles:

~~~java
ServerHttpRequest newRequest = exchange.getRequest()
        .mutate()
        .headers(h -> h.set("X-Trace-Source", "edge"))
        .build();

ServerWebExchange newExchange = exchange.mutate()
        .request(newRequest)
        .build();
~~~

`newRequest` and `newExchange` are **new views** for the rest of the downstream chain, still belonging to the same HTTP exchange sent by the client. They do not call the backend by themselves; the gateway forwards only when execution reaches the routing filter. Therefore, after mutating, you still must pass `newExchange` into `chain.filter(newExchange)`.

## 6. Applying in Spring Cloud Gateway

Consider a gateway listening at `http://localhost:8080` and a catalog service at `http://localhost:9001`. Illustrative configuration:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-route
          uri: http://localhost:9001
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Gateway-Route, catalog-route
~~~

> The key `spring.cloud.gateway.routes` applies to many released Spring Cloud Gateway WebFlux versions; newer lines may use the prefix `spring.cloud.gateway.server.webflux.routes`. Choose the namespace matching your running version. A static URI is used here to focus on request/exchange; when switching to `lb://catalog-service`, the gateway needs discovery and LoadBalancer to locate instances.

Given the request:

~~~http
GET /api/catalog/items/42?locale=vi HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

The flow proceeds as follows:

1. WebFlux creates the exchange context via `ServerWebExchange`, attaching a `ServerHttpRequest` with the initial path `/api/catalog/items/42`.
2. `RoutePredicateHandlerMapping` selects `catalog-route` because `Path=/api/catalog/**` matches; the route is stored in an exchange attribute.
3. `FilteringWebHandler` orders `GlobalFilter` and `GatewayFilter` instances. `StripPrefix=1` produces a request with path `/catalog/items/42`; `AddRequestHeader` adds `X-Gateway-Route: catalog-route`.
4. The gateway resolves the target URI and the routing filter sends the corresponding HTTP request to `http://localhost:9001/catalog/items/42?locale=vi`.
5. The service returns status, headers, and body; the gateway writes that response to `ServerHttpResponse` for the client while running appropriate post-filters.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant W as WebFlux
    participant F as Gateway filters
    participant B as Catalog service
    C->>W: GET /api/catalog/items/42?locale=vi
    W->>F: ServerWebExchange(request, response)
    F->>F: Path predicate match
    F->>F: StripPrefix and AddRequestHeader
    F->>B: GET /catalog/items/42?locale=vi
    B-->>F: 200 + JSON
    F->>W: Post-filter, handle response
    W-->>C: HTTP 200 + JSON
~~~

In particular, `ServerWebExchange` belongs to HTTP processing **at the gateway**. The backend has its own request/response objects inside its application and does not share Java objects with the gateway.

## 7. Complete Example: GlobalFilter Attaching a Request ID

The following filter demonstrates all three objects in one flow: reading the request from the exchange, creating a request with a new header, registering a response update callback, and invoking the chain with the updated exchange. The request ID is generated **at the gateway** to correlate logs across steps rather than blindly trusting a client-supplied header.

~~~java
package example.gateway;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class RequestIdFilter implements GlobalFilter, Ordered {
    private static final Logger log =
            LoggerFactory.getLogger(RequestIdFilter.class);

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             GatewayFilterChain chain) {
        String requestId = UUID.randomUUID().toString();
        long started = System.nanoTime();

        // Attribute: for internal processing only.
        exchange.getAttributes().put("demo.requestId", requestId);

        // Request: create a mutated copy so downstream sees the new header.
        ServerHttpRequest changedRequest = exchange.getRequest()
                .mutate()
                .headers(headers -> {
                    // Prevent clients from spoofing trusted identity headers.
                    headers.remove("X-Trusted-User");
                    headers.set("X-Request-Id", requestId);
                })
                .build();

        // Response: set header before response commits.
        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders()
                    .set("X-Request-Id", requestId);
            return Mono.empty();
        });

        ServerWebExchange changedExchange = exchange.mutate()
                .request(changedRequest)
                .build();

        // Return Mono; do not subscribe/block manually.
        return chain.filter(changedExchange)
                .doFinally(signal -> {
                    long durationMs =
                            (System.nanoTime() - started) / 1_000_000;
                    log.info("requestId={} method={} path={} status={} " +
                                    "durationMs={} signal={}",
                            requestId,
                            exchange.getRequest().getMethod(),
                            exchange.getRequest().getPath().value(),
                            exchange.getResponse().getStatusCode(),
                            durationMs,
                            signal);
                });
    }
}
~~~

Key points to note:

- **`getOrder() = -100`** is just an ordering example. Filters with lower order values generally execute **pre** logic earlier and post-chain logic later than filters with higher order values; actual execution also depends on other configured filters.
- `exchange.getRequest()` in the log reads the original request, whereas `changedExchange.getRequest()` going down the chain carries `X-Request-Id`. This separates what the client originally sent from what the gateway added.
- `beforeCommit` sets the header right before the response commits, even when the backend returns an error; if a component completes the request **before this filter is invoked**, the callback is not registered.
- `doFinally` runs when the publisher completes, errors, or is cancelled, making it suitable for recording observation duration. It does not guarantee the backend always returned a full response.
- This illustrative filter only **removes the client-supplied `X-Trusted-User` header**; it does not populate a verified identity. Real authentication/authorization requires Spring Security and explicit policies.
- The request ID in this example differs from a distributed trace ID. In multi-service systems, also use Micrometer Tracing and the W3C `traceparent` standard to link all hops end to end.

### Why Not Mutate the Request Directly?

In WebFlux, a request may be wrapped in decorators; using the builder and passing a new exchange is the framework-supported mechanism for downstream steps to observe changes. Meanwhile, `ServerHttpResponse` has methods to write status, headers, cookies, and body before commit, so updating a response follows a different model from mutating a request. **Do not conflate request immutability with response commit state.**

## 8. Common Pitfalls When Writing Filters

| Pitfall | Correct understanding / how to handle |
| --- | --- |
| Mutating request headers via `request.getHeaders().set(...)` | May encounter read-only headers or produce changes outside the expected contract. Use `request.mutate().headers(...)` and pass the new exchange into the chain. |
| Creating a new request but calling `chain.filter(exchange)` | The chain still receives the old exchange so changes never reach downstream. Call `chain.filter(updatedExchange)`. |
| Reading the body to log it, then forwarding the body "as-is" | The body may already be consumed, resulting in an empty/failed downstream request. Use a caching/decorator mechanism or built-in filter if truly needed. |
| Calling `subscribe()` inside a filter | Creates a detached subscription outside the gateway lifecycle, causing races, unhandled errors, or broken responses. Return the chain's `Mono<Void>`. |
| Calling `block()` to get principal, body, or service response | Can block the Netty event loop and degrade throughput. Compose with `flatMap`, `then`, `map`, or appropriate reactive operators. |
| Modifying status/headers in a post-filter after response commit | Changes may be ignored or rejected. Set them early or register `beforeCommit` at the right time. |
| Reading `getAttribute(GATEWAY_REQUEST_URL_ATTR)` in a very early filter | The attribute may not be set yet. Check for `null` and understand router/load-balancer ordering. |
| Treating `getRemoteAddress()` as the absolute client IP | It may just be the nearest proxy in front of the gateway. Handle `Forwarded`/`X-Forwarded-*` according to a trusted proxy list. |
| Assuming `GlobalFilter` runs on every HTTP request entering the server | It runs inside the gateway filter chain of a matched route. Requests rejected by a WebFlux `WebFilter` or matching no route may never reach `GlobalFilter`. |

### How Do WebFilter and GlobalFilter Differ?

`WebFilter` is a **WebFlux** component running around handler selection; Spring Security checks typically occur here. `GlobalFilter` is a **Spring Cloud Gateway** component executed once the request is mapped to the gateway handler/filter chain. If a token is rejected inside a security `WebFilter`, a logging `GlobalFilter` may not observe that request. To get complete ingress metrics, instrument at the appropriate layer and combine reverse-proxy/HTTP-server logs if needed.

## 9. Verifying with an HTTP Client and Logs

Run the gateway on `localhost:8080` with the catalog route from Section 6 and a backend returning JSON on `GET /catalog/items/42` at `localhost:9001`. With `RequestIdFilter` from Section 7 active, run:

~~~bash
curl -i "http://localhost:8080/api/catalog/items/42?locale=vi"
~~~

Observe:

1. The backend receives path `/catalog/items/42`, query `locale=vi`, and header `X-Gateway-Route: catalog-route` added by the route filter.
2. The backend also receives `X-Request-Id` added by `RequestIdFilter`. The response sent to the client includes `X-Request-Id` with the same value when the filter runs and the response commits normally.
3. Filter logs record method, original path, status, and processing time. The logged path in this example is `/api/catalog/items/42` because it comes from the initial exchange.

Try further:

~~~bash
# Client attempts to send its own request ID and a spoofed header:
curl -i "http://localhost:8080/api/catalog/items/42" \
  -H "X-Request-Id: fake-from-client" \
  -H "X-Trusted-User: admin"

# Unless another route exists, this path will not match the catalog route:
curl -i "http://localhost:8080/api/orders/42"
~~~

In the first request, the gateway replaces the request ID with a freshly generated one and strips `X-Trusted-User` before forwarding to the backend. In the second request, if no other route/handler exists, the client typically receives `404` and `GlobalFilter` may not execute. When replacing the static backend with `lb://catalog-service`, processing adds an instance-selection step via service discovery/load balancing.

To practice diagnostic thinking, compare three cases:

- **404 from gateway:** no route predicate matched; no request reached the backend.
- **404 from backend:** route matched and forwarded, but the path after `StripPrefix`/`RewritePath` did not match a backend endpoint.
- **503 when using `lb://`:** the gateway could not find an available instance for the service ID (503 is the default with WebFlux LoadBalancer, configurable to return 404); the backend may never have received the request.

Every one of these distinctions starts with knowing **which request the exchange holds**, **when the request is mutated**, and **where the response is produced**.

## 10. Practical Checklist

Before deploying a gateway filter into a microservices system, check:

1. Does the filter need to **read** the request, **mutate** the request, or **modify** the response? Choose the right API and execution stage.
2. If mutating the request, did you pass the **new exchange** downstream? Do route predicates run before the mutation?
3. Does it read or cache the body? Have streaming, large payloads, backpressure, and `DataBuffer` lifecycles been accounted for?
4. Could the response already be **committed** before setting status/headers? Are you using `beforeCommit` where appropriate?
5. If the filter short-circuits a request, does it complete the response and stop the chain properly?
6. Should shared metadata live in **internal exchange attributes** or **HTTP headers** sent to services? Could a client spoof that header?
7. In production, requests can be stopped by TLS, WebFlux security, rate limiters, circuit breakers, timeouts, or discovery before the backend processes them. Do you have sufficient logs/metrics/traces to distinguish those points?

**Key takeaway:** `ServerHttpRequest` tells you what request is being processed; `ServerHttpResponse` manages the response and commit timing; `ServerWebExchange` ties them together with the data and lifecycle of a request. Writing filters in line with these three concepts makes routing, authentication, rate limiting, retries, circuit breaking, TLS, and observability in **Spring Cloud Gateway** much easier to reason about and control.
