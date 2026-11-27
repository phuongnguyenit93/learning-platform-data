# ForwardRoutingFilter and Internal Forwarding with `forward:`

## 1. What Problem Does Internal Forwarding Solve?

When building an API Gateway with **Spring Cloud Gateway**, a route normally receives a request and proxies it over HTTP to another microservice, such as `lb://catalog-service`. Yet there are cases where the gateway needs to hand a request off to a **handler inside the gateway application itself**, such as a fallback data endpoint, an internal health/test endpoint, or a handler enforcing special response rules.

In **Spring Cloud Gateway Server WebFlux**, a URI with the **`forward:`** scheme expresses a request to route into **Spring WebFlux's internal** handler-processing mechanism. The component responsible for this is **ForwardRoutingFilter**, a routing filter provided by the framework.

~~~mermaid
flowchart LR
    C[Client] --> G[Spring Cloud Gateway]
    G --> P{Route URI scheme}
    P -->|http / https / lb| U[Upstream HTTP service]
    P -->|forward| H[Local WebFlux handler]
    H --> R[HTTP response]
    U --> R
    R --> C
~~~

The key difference lies in the **processing target**: a `forward:` URI sends the request to a handler inside the same application, whereas `http:`, `https:`, and `lb:` target upstreams over a network connection (directly or via service resolution).

After this lesson, you will be able to:

1. Explain where **ForwardRoutingFilter** operates in the request processing chain.
2. Distinguish `forward:` from HTTP routing, load balancing, path rewriting, and redirects.
3. Configure a `forward:` route to a WebFlux controller in the same application.
4. Understand the roles of **GATEWAY_REQUEST_URL_ATTR**, **GATEWAY_ORIGINAL_REQUEST_URL_ATTR**, and **DispatcherHandler**.
5. Design local fallbacks, test routing behavior, and prevent routing loops, internal endpoint exposure, blocking I/O, and observability skew.

> **Scope:** This content covers **Spring Cloud Gateway Server WebFlux**, the variant built on Spring WebFlux and Reactor. Spring Cloud Gateway Server Web MVC and Servlet forwarding have different processing components; do not mechanically apply WebFlux's `ForwardRoutingFilter` class to those variants.

## 2. Position of ForwardRoutingFilter in the Gateway Architecture

To understand `forward:`, first look at the normal request flow in Spring Cloud Gateway:

~~~mermaid
flowchart TB
    A[Incoming HTTP request] --> B[Spring WebFlux handler mappings]
    B --> C[RoutePredicateHandlerMapping]
    C -->|Route matches| D[FilteringWebHandler]
    D --> E[Combined GatewayFilter chain]
    E --> F[RouteToRequestUrlFilter]
    F --> G{Target URL scheme}
    G -->|forward| H[ForwardRoutingFilter]
    H --> I[Spring WebFlux DispatcherHandler]
    I --> J[Local controller / handler]
    G -->|http / https| K[NettyRoutingFilter]
    K --> L[HTTP upstream]
    J --> M[Write response to client]
    L --> M
~~~

Responsibilities:

- **RoutePredicateHandlerMapping:** finds a route matching the request via predicates such as `Path`, `Method`, `Host`, or `Header`.
- **FilteringWebHandler:** builds and executes the chain composed of `GlobalFilter`s and the selected route's `GatewayFilter`s.
- **RouteToRequestUrlFilter:** prepares the route's target URL in the exchange attribute used for routing.
- **ForwardRoutingFilter:** recognizes the **`forward` scheme** in the target URL and hands processing over to WebFlux's **DispatcherHandler**.
- **NettyRoutingFilter:** handles the HTTP proxy path for applicable target URIs; it is not the component that makes a new HTTP request for `forward:`.
- **DispatcherHandler:** Spring WebFlux's handler dispatcher, which can pick an `@RequestMapping` controller or functional handler declared in the same application.

These components are not one fixed single chain for every request. The route, enabled filters, filter ordering, and infrastructure configuration determine the concrete processing path. The diagram intentionally simplifies steps such as security checks, metrics, errors, URL edits, and pre/post filters.

### ForwardRoutingFilter Is Not Added by Name in YAML

A route targeting `forward:` is normally specified in **`uri`**:

~~~yaml
uri: forward:///internal/ping
~~~

You do not need to add `ForwardRoutingFilter` under `filters:`. The framework recognizes the URL with scheme `forward` in the exchange and uses the corresponding routing filter. Filters declared under `filters:` such as `StripPrefix`, `RewritePath`, or custom filters can still affect the request before the routing step.

## 3. How Does ForwardRoutingFilter Work?

Gateway components exchange data via **ServerWebExchange**. Once a route is selected, its target URL is stored in the attribute:

```java
ServerWebExchangeUtils.GATEWAY_REQUEST_URL_ATTR
```

**ForwardRoutingFilter** inspects this URL value. If the URL carries the `forward` scheme, the filter uses **DispatcherHandler** to handle the request within the current application. The request path is replaced with the path portion of the `forward:` URI; the original unmodified URL is added to the list stored at:

```java
ServerWebExchangeUtils.GATEWAY_ORIGINAL_REQUEST_URL_ATTR
```

Conceptual flow:

~~~mermaid
sequenceDiagram
    participant Client
    participant Mapping as RoutePredicateHandlerMapping
    participant Chain as Gateway filter chain
    participant Forward as ForwardRoutingFilter
    participant Dispatcher as DispatcherHandler
    participant Local as Local WebFlux controller

    Client->>Mapping: GET /api/ping
    Mapping->>Chain: Matched route: local-ping
    Chain->>Chain: Set target forward:///internal/ping
    Chain->>Forward: Continue routing
    Forward->>Forward: Change request path to /internal/ping
    Forward->>Dispatcher: Handle within same application
    Dispatcher->>Local: GET /internal/ping
    Local-->>Dispatcher: Mono response
    Dispatcher-->>Forward: Completion / error
    Forward-->>Chain: Completion / error
    Chain-->>Client: HTTP response
~~~

Key points to remember:

- **Does not make a new HTTP trip to localhost.** Calling the internal handler happens inside the current process. `forward:` is not a hostname and does not use DNS, service discovery, or Spring Cloud LoadBalancer to look up another application.
- **Still the same request being handled at the gateway.** Information such as method, headers, and the exchange travels through the internal path; the path is adjusted so the target handler matches. If the body was already consumed or modified by an earlier filter, the internal handler must work with the actual remaining body state.
- **Errors can occur normally.** A missing target handler can yield 404; a disallowed method can yield 405; exceptions in the handler can flow to WebFlux error handling.
- **Forward is not synonymous with redirect.** The client typically sees only one request/response and does not issue a new request to the internal path.
- **Some filters run both pre and post phases.** Filters with post-processing after `chain.filter(exchange)` can still observe completion status of internal processing, depending on ordering and how the filter is written.

### Three Common Exchange Attributes

| Attribute | Meaning |
| --- | --- |
| `GATEWAY_ROUTE_ATTR` | The Route selected by the Gateway for the request |
| `GATEWAY_REQUEST_URL_ATTR` | Current target URL, used by routing filters to decide where to dispatch |
| `GATEWAY_ORIGINAL_REQUEST_URL_ATTR` | List of URLs prior to URL modifications, for tracing the routing process |

These are internal attributes of `ServerWebExchange`, **not HTTP headers** sent by the client. When logging, select only needed data and avoid logging tokens, cookies, or query parameters containing sensitive information.

## 4. Complete Example: Route from /api/ping to an Internal Controller

Suppose the gateway application has a controller returning a short response to verify the path. Client calls:

```http
GET /api/ping HTTP/1.1
Host: localhost:8080
```

We want **Spring Cloud Gateway** to select route `local-ping`, and then **ForwardRoutingFilter** to dispatch to the local handler at **/internal/ping**.

### 4.1. Route Configuration

The example below uses the **Gateway Server WebFlux** configuration structure found in newer versions:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: local-ping
              uri: forward:///internal/ping
              predicates:
                - Path=/api/ping
                - Method=GET
~~~

In some earlier Spring Cloud Gateway Server WebFlux versions, the route list uses **`spring.cloud.gateway.routes`**:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: local-ping
          uri: forward:///internal/ping
          predicates:
            - Path=/api/ping
            - Method=GET
~~~

**Pick one namespace compatible with your actual version**; do not copy both blocks at once. The notation `forward:///internal/ping` expresses the `forward` scheme and target path `/internal/ping`. The form `forward:/internal/ping` may also appear in fallback examples; what matters is that the URI parses to the right scheme and path.

### 4.2. Creating the Local Handler

A WebFlux controller located **in the same application** as the Gateway:

~~~java
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class InternalPingController {

    @GetMapping("/internal/ping")
    Mono<Map<String, String>> ping() {
        return Mono.just(Map.of(
                "status", "ok",
                "handledBy", "gateway-local-handler"
        ));
    }
}
~~~

The controller must be discovered by Spring via component scanning or explicit bean configuration. The `@GetMapping` path must match the **forwarded path**, rather than the public path `/api/ping`.

### 4.3. Sending a Test Request

~~~bash
curl -i http://localhost:8080/api/ping
~~~

Expected response when the application works properly:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"ok","handledBy":"gateway-local-handler"}
~~~

This is an **illustrative response**, not output captured from running in this article. Actual headers and JSON formatting may vary depending on configuration.

### 4.4. What Happens at Each Hop?

| Step | Actor | Outcome |
| --- | --- | --- |
| 1 | Client | Sends `GET /api/ping` |
| 2 | Route predicate | `Path=/api/ping` and `Method=GET` match route `local-ping` |
| 3 | Route URL | Target has scheme `forward` and path `/internal/ping` |
| 4 | ForwardRoutingFilter | Adjusts path for DispatcherHandler to handle |
| 5 | DispatcherHandler | Looks up local handler at `/internal/ping` |
| 6 | InternalPingController | Produces reactive response `Mono<Map<...>>` |
| 7 | HTTP response | Client receives result from the original request |

In this model, the local controller can return JSON, text, SSE, or other reactive content supported by WebFlux and codecs. ForwardRoutingFilter itself neither requires the body to be JSON nor assembles data into a new response on its own.

## 5. Comparing Forward, HTTP Proxy, Path Rewrite, and Redirect

These mechanisms are easily confused because all of them can make an external URL lead to another resource.

| Mechanism | Processing Target | Does Client Send a New Request? | Primary Effect |
| --- | --- | --- | --- |
| `uri: forward:///internal/ping` | WebFlux handler in the same Gateway app | No | DispatcherHandler handles internally at the forwarded path |
| `uri: http://localhost:9000` | HTTP server at target address | Not for this proxy hop | Gateway calls backend over HTTP |
| `uri: lb://catalog-service` | Service instance resolved via load balancing | Not for this proxy hop | Gateway picks instance and calls service |
| `RewritePath` / `StripPrefix` | Depends on route `uri` | No | Changes the path used when the route forwards |
| `RedirectTo` | Target URL visited by client after redirect | **Yes**, if client follows redirect | Returns HTTP 3xx and `Location` |

Example:

~~~yaml
# Forward path to local handler in the same app:
uri: forward:///internal/ping

# HTTP proxy to a service listening on another port:
uri: http://localhost:9000

# Proxy via service name and load balancer:
uri: lb://catalog-service
~~~

**`RewritePath` does not define a processing target by itself**. It transforms the request path; the Gateway still needs a route `uri` to know where to send it. **`RedirectTo`** returns an instruction to the client, so the client may see the new URL and initiate a new network trip.

**`forward:` is also not a way to "fast-call" another microservice by bypassing HTTP.** To forward to a handler, that handler must live in the same WebFlux application. If business logic resides in another process/container, use a real inter-service communication mechanism such as HTTP, gRPC, or messaging.

### Should StripPrefix Be Used with Forward?

It can be, provided the final path is clearly understood. In the example above, the URI explicitly specifies `/internal/ping`, so there is no need to add `StripPrefix` just to drop `/api`. If path-transforming filters are also present, the outcome depends on filter ordering and how the target URL is constructed. Explicitly note the **incoming path**, **post-filter path**, and **path received at the handler**, then verify with a real request.

## 6. Practical Application: CircuitBreaker Fallback to a Local Handler

A common use case for `forward:` is **fallback**. Suppose a request needs the Pricing service, yet the service is temporarily unavailable. You can use the **CircuitBreaker** filter and, only when fallback conditions trigger, handle the request in a controller inside the Gateway:

~~~mermaid
flowchart TB
    Client[GET /api/prices/P42] --> Edge[Gateway route: pricing]
    Edge --> CB{CircuitBreaker}
    CB -->|Upstream healthy| Service[Pricing service]
    Service --> Result[Actual price response]
    CB -->|Failure / open circuit| Forward[forward:/internal/fallback/pricing]
    Forward --> Local[Local fallback handler]
    Local --> Error[Controlled error response]
~~~

Configuration example for **Gateway Server WebFlux**:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: pricing
              uri: lb://pricing-service
              predicates:
                - Path=/api/prices/**
                - Method=GET
              filters:
                - name: CircuitBreaker
                  args:
                    name: pricingCircuitBreaker
                    fallbackUri: forward:/internal/fallback/pricing
~~~

To use the CircuitBreaker filter, the project needs Spring Cloud CircuitBreaker dependencies/integrations matching your running version, such as the Reactor Resilience4j variant, along with required breaker configuration. The example config **only illustrates the fallback path** and omits full production policies on timeouts, failure thresholds, or concurrency limits.

Local handler:

~~~java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class PricingFallbackController {

    @GetMapping("/internal/fallback/pricing")
    Mono<ResponseEntity<Map<String, String>>> fallback() {
        return Mono.just(
                ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                        .body(Map.of(
                                "code", "PRICE_SERVICE_UNAVAILABLE",
                                "message", "Unable to retrieve price at this time"
                        ))
        );
    }
}
~~~

**Why return 503?** Price may be essential information for making a purchase decision. Returning an untrustworthy "fallback price" or a 200 status can mislead clients. For auxiliary data such as product recommendations, returning an empty result or appropriately labeled cached data may be acceptable **if the business contract permits it**.

Common misconception: **the CircuitBreaker filter does not forward every request immediately**. Normally, requests are still sent to Pricing service. `fallbackUri` is the alternate path when the filter triggers fallback based on its conditions and observed failures. A 4xx/5xx response from the backend does not automatically trigger fallback unless the required conditions are configured. Other filters such as rate limiters can return 429 independently of CircuitBreaker.

### Errors Occurring Before vs. After the Response Is Sent

If upstream fails **before the response is committed**, the Gateway can usually still return an appropriate fallback response. If upstream is streaming and fails **after headers and part of the body have already been sent to the client**, you cannot assume the gateway will replace the entire response with a different HTTP code. Therefore, fallback for SSE, NDJSON, or large downloads requires application-appropriate reconnect/retry/range contracts.

### Do Not Use Local Fallbacks to Hide Failures That Need Detection

Observe separately:

- Total requests entering route `pricing`.
- CircuitBreaker open rate and fallback invocation count.
- Response times at upstream and local handler.
- HTTP status codes returned to clients and error categorization.

A fallback that always returns 200 can make gateway-level HTTP dashboards look like everything is healthy even while Pricing service is unresponsive. Degraded states must be reflected in metrics and tracing by design.

## 7. Security and Trust Boundaries of Internal Handlers

This is a major risk when using `forward:`: **a "/internal/..." path does not become private just because it is named internal**.

If a controller has `@GetMapping("/internal/ping")` on the same HTTP server and is not blocked, an external client can try accessing it directly:

~~~bash
curl -i http://localhost:8080/internal/ping
~~~

This request may be handled directly by the WebFlux controller, depending on route mapping, security, and infrastructure. Do not secure only `/api/ping` and assume `/internal/ping` does not exist to external users.

**Protection principles:**

1. **Protect both original paths and handler paths:** configure Spring Security WebFlux, network policies, or appropriate access controls so clients cannot directly call sensitive internal endpoints.
2. **Do not assume authentication runs a second time for the forwarded path.** Dispatching a handler through DispatcherHandler does not mean every WebFilter/security filter of the inbound HTTP request will run again as a brand-new request. If a Spring Security rule only matches `/internal/**`, verify how it behaves when a client calls the public `/api/**` path.
3. **Services or handlers must still check business permissions.** The Gateway validating a token does not prove the user is authorized to access every resource.
4. **Never trust internal headers supplied by clients.** Headers such as `X-User-Id`, `X-Role`, or propagated identity must come from trusted context, not directly from incoming request headers.
5. **Do not let fallbacks leak sensitive data:** internal hostnames, stack traces, real service URLs, or error messages containing tokens.
6. **Keep memory and processing time bounded:** local handlers run inside the gateway application itself, so heavy CPU work or blocking I/O can affect every request passing through the gateway.

For instance, WebFlux Security protections must be designed around application policy; a matcher that only blocks `/internal/**` on the initial HTTP pass may be **insufficient** to protect a flow forwarded from `/api/**`. Test both direct requests and forwarded requests with unauthenticated and unauthorized users.

## 8. When Can Forwarding Lead to a Loop?

Consider an overly broad route:

~~~yaml
predicates:
  - Path=/**
uri: forward:///internal/ping
~~~

If `/internal/ping` is picked up again by a Gateway route or a handler whose logic forwards back to the Gateway, the system risks a **processing loop**. Depending on handler mapping configuration, this can result in the wrong handler running, deep recursion, 5xx errors, or overload. The lesson is never to use catch-all routes without accounting for internal paths and handler priority ordering.

**Preventive measures:**

- Pick internal paths with a clear namespace that will not collide with public paths or paths the Gateway will match and re-forward.
- Write precise predicates and audit the coverage of `Path=/**`, regex, or Host routes.
- Avoid having a fallback route call back into the failing endpoint without a termination condition.
- Write tests for cases where the target path is re-matched, no handler exists, wrong method is used, and fallback itself fails.
- Do not let client request headers dictate arbitrary `forward:` targets without validation/allowlisting; avoid turning the Gateway into an uncontrolled internal router.

Note: whether a loop occurs depends on how the application configures handler mappings and filters; a `Path=/**` route **does not automatically prove** every forward loops. What must be verified is which handler is actually selected **after the path changes**.

## 9. Forward and the Reactive Request/Response Lifecycle

Because `forward:` operates through **Spring WebFlux**, Reactor principles still apply:

- **Never call `block()` on the event loop** inside controllers/fallbacks. A seemingly tiny fallback using a blocking JDBC query can stall the gateway right when upstream failures happen concurrently.
- **Do not manually `subscribe()` to the body to log or inspect it**, because a reactive request body can usually be consumed only once. The forwarded handler might have no data left to read.
- **Do not assume forward copies the body.** If a filter needs to read the body and let the controller read it afterward, use an appropriate body caching/decorating mechanism with size limits and accurate `DataBuffer` lifecycles.
- **Respect cancellation and timeouts.** If a client disconnects while a local handler is running, publishers may receive cancel signals; non-Reactor work does not automatically stop unless integrated properly.
- **Do not let fallback errors spin infinitely.** If the fallback itself fails, an error handler must produce a safe response or record the inability to complete the response.

### Non-Blocking Reactive Handler Example

~~~java
import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
class LocalEventController {

    @GetMapping(value = "/internal/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<String> events() {
        return Flux.interval(Duration.ofSeconds(1))
                .take(3)
                .map(i -> "event-" + i);
    }
}
~~~

With a route `uri: forward:///internal/events`, the local handler can return SSE over the same open HTTP connection. However, **forward does not automatically guarantee end-to-end streaming**: codecs, gateway filters, upstream proxies, and clients can affect buffering and flushing. When an application needs guaranteed delivery or replay after disconnect, design explicit event IDs and suitable storage/brokers.

## 10. Logging, Metrics, and Tracing

When a request is forwarded, looking only at the external URL or only at the handler path can be confusing. Useful logs should capture fields such as:

| Field | Example | Purpose |
| --- | --- | --- |
| Public path | `/api/ping` | Know what the client called |
| Route ID | `local-ping` | Identify which route was selected |
| Forward target | `/internal/ping` | Identify which internal handler received the request |
| Method and status | `GET`, `200` | Evaluate outcome |
| Trace/correlation ID | Valid generated or propagated ID | Correlate logs across steps |
| Duration | 12 ms | Analyze latency |

In real applications, logs can be produced from Spring Cloud Gateway metrics, tracing, and supported hooks. If writing a custom filter, read exchange attributes per the framework contract; never log bodies, passwords, tokens, or sensitive cookies.

One key distinction for reading traces: **forwarding to a controller in the same process is not an outbound HTTP client call to an upstream**, so it does not by default emit a new outbound HTTP span like the `NettyRoutingFilter` path. To separate Gateway routing time from local handler time, instrument the respective processing regions properly. For CircuitBreaker fallbacks, separating **requests served via fallback** from successful upstream requests is critical.

### Following Up When Troubleshooting

If `GET /api/ping` returns 404, check sequentially:

1. Do predicates match the actual method/path/host?
2. Is the route loaded under the right configuration namespace for your Gateway version?
3. Does `uri` have the `forward` scheme and right target path?
4. Was the internal controller component-scanned with the matching `@GetMapping`?
5. Did any filter change the path or request body before reaching ForwardRoutingFilter?
6. Did Spring Security, handler mapping, or an error handler block/alter the result?

If `GET /api/ping` returns 500 or times out, check exceptions in the local handler, routing loops, blocking I/O, and timeout limits. If it returns 200 with wrong content, check the selected route and the handler that actually received the request.

## 11. Hands-On Exercise: Designing a Controlled Local Fallback

**Problem:** The Gateway has a route to the Inventory service. When the service is failing, the system must report that inventory availability cannot be checked right now. It must never claim a product is in stock.

### Step 1 — Design the Route

Create a route for `GET /api/inventory/**` to `lb://inventory-service`. Use `CircuitBreaker` with `fallbackUri: forward:/internal/fallback/inventory` and configure breaker conditions suited to a test environment.

### Step 2 — Create the Handler

Create a WebFlux controller handling `GET /internal/fallback/inventory`, returning `503 Service Unavailable` with JSON:

~~~json
{
  "code": "INVENTORY_UNAVAILABLE",
  "message": "Unable to confirm inventory at this time",
  "retryable": true
}
~~~

`retryable` is only a hint to clients if the API contract clearly defines retry semantics; it does not replace client-side backoff, idempotency, and deadlines. For read `GET` requests, retries can be more appropriate than for non-idempotent `POST` operations, though frequency must still be controlled during outages.

### Step 3 — Verify Both Processing Paths

| Test Case | Expected Outcome |
| --- | --- |
| Inventory service healthy | Gateway returns real Inventory data without hitting fallback |
| Inventory service fails per breaker conditions | Request reaches local handler, returning 503 and defined error code |
| Direct external call to `/internal/fallback/inventory` | Blocked/controlled according to security policy |
| Calling `POST /api/inventory/... ` if only GET is allowed | Does not pass through the GET route or cause unintended side effects |
| Fallback handler missing | Fallback path fails; detected via logs/metrics and tests |
| Many concurrent requests during upstream outage | Gateway remains responsive; handler does not block or grow load unboundedly |
| Fallback errors or client disconnects | Errors/cancellations observed; no loops or resource leaks |

### Step 4 — Observe

Record route ID, original URL, forward target, fallback count, HTTP status, and latency. Check the case where `CircuitBreaker` is open: calls rejected or routed to fallback must be distinguished from 503 errors returned by the backend itself.

### Step 5 — Ask Architectural Questions

- Is this fallback simple enough to run inside the Gateway process itself?
- Can fallback data be trusted, or must a clear error be returned?
- If the Gateway had to connect to a database and run complex business logic to produce a fallback, should that move to a separate service/facade?
- Could a `Path=/**` route or security rule accidentally match or expose `/internal/fallback/**` externally?
- Do timeouts and tracing reveal whether an error response came from upstream, CircuitBreaker, or the local handler?

## 12. Misconceptions to Avoid

**"ForwardRoutingFilter is a way to call another service without network cost."** False. It sends requests to handlers **within the same WebFlux application**. A service in another process still requires an appropriate communication channel.

**"`forward:` is the same as `redirect:`."** False. Forward is internal processing, whereas redirect normally sends a 3xx response so the client fetches the new URL itself.

**"Just using `RewritePath` turns it into a forward."** False. Rewrite modifies the path; route URI determines the routing target. Forward uses the `forward` scheme.

**"A controller with `/internal/**` path is automatically private."** False. A path is just a name; security comes from authentication, authorization configuration, and network boundaries, and both direct and forwarded access must be tested.

**"All filters and Spring Security run again in full on forward."** Do not assume that. ForwardRoutingFilter dispatches via DispatcherHandler rather than creating a brand-new HTTP request.

**"A fallback that always returns 200 makes the system stable."** It can mask outages and violate data correctness. Choose status codes, payloads, observability, and recovery strategies based on business semantics.

**"Because the Gateway uses WebFlux, local handlers can call blocking functions freely."** False. Blocking work on the event loop degrades latency for many requests. Use reactive APIs or isolate blocking tasks under control.

## 13. Summary

- **ForwardRoutingFilter** belongs to the routing pipeline of **Spring Cloud Gateway Server WebFlux** and recognizes target URIs with the **`forward`** scheme.
- With `forward:`, the Gateway hands the request to **DispatcherHandler** to locate and invoke a WebFlux handler **within the same application**, adjusting the path and recording pre-change URL info in the exchange.
- `forward:` is suited for selected local endpoints and **CircuitBreaker fallbacks**, not a replacement for HTTP routing, load balancing, or inter-service communication.
- **Forward, rewrite, and redirect are three distinct operations.** Identify route predicates, target URI, final path, and actual handler clearly to avoid misconfiguration.
- **Internal handlers are not automatically safe because of their path name.** Block unauthorized direct access and verify authentication/authorization policies across both public and local paths.
- Monitor **route ID, original URL, forward target, status, latency, and fallback counts**; prevent loops, blocking I/O, and improper body handling so the Gateway maintains its role as a secure, stable microservices entry point.
