# Priority Order When Multiple Routes Match

## 1. The Problem: A Single Request Can Satisfy Multiple Routes

In **Spring Cloud Gateway**, a route typically consists of an `id`, a `uri`, a list of **predicates**, and optional **filters**. Predicates evaluate requests by path (`Path`), HTTP method (`Method`), host, headers, query parameters, or other conditions. When a microservices system has many APIs, these conditions can easily overlap:

~~~text
GET /api/orders/42
  ├─ Path=/api/orders/**  → matches
  └─ Path=/api/**         → also matches
~~~

If both routes can accept the request, **which route does Spring Cloud Gateway choose?** The answer lies in the route's **`order` property**: in **Spring Cloud Gateway Server WebFlux**, routes with a **lower `order` value** are evaluated **first**. The Gateway selects **the first route whose predicates all match** in that order.

This lesson belongs to the **Route Configuration** chapter of the **SPRING_CLOUD_GATEWAY** module. Understanding route priority helps avoid sending requests to the wrong service, explains why path/header-rewriting filters fail to execute, and keeps boundaries clear when later adding service discovery, authentication, rate limiting, circuit breakers, retries, TLS, and request observability.

> **Key takeaway:** `Path` specificity (e.g., `/api/orders/**` vs. `/api/**`) **does not automatically determine** the winning route. Configure `order` explicitly whenever routes can match the same requests.

## 2. In What Order Does the Gateway Select a Route?

In WebFlux Gateway, `RoutePredicateHandlerMapping` searches for a matching route from the list supplied by `RouteLocator`. Routes are sorted by priority; the Gateway evaluates predicates sequentially and picks the first matching route. Only after a route is selected does `FilteringWebHandler` assemble the `GlobalFilter` and `GatewayFilter` instances to process the request.

~~~mermaid
flowchart TD
    C["Request arrives at Gateway"] --> S["Retrieve routes in priority order"]
    S --> P1{"Does lowest-order route<br/>match all predicates?"}
    P1 -->|"Yes"| R["Select that route"]
    P1 -->|"No"| P2{"Evaluate next route"}
    P2 -->|"Matches"| R
    P2 -->|"No match, more routes"| P2
    P2 -->|"No routes left"| N["No route found"]
    R --> F["Run filter chain<br/>of selected route"]
    F --> U["Resolve target URI / select instance"]
    U --> B["Send request to backend"]
    N --> E["Typically 404 if no other<br/>WebFlux handler matches"]
~~~

In route configuration:

- `order: -20`: higher priority than `order: -10`.
- `order: -10`: higher priority than `order: 0`.
- `order: 0`: higher priority than `order: 100`.
- **Omitting `order`:** the default value is typically **`0`**.

Because lower numbers are evaluated first, a broad route with `order: -100` can "swallow" requests intended for a specific route with `order: 0`. Conversely, a high-priority route **whose predicates do not match** is skipped, and the Gateway moves on to the next route.

### 2.1. Conditions Within a Single Route Must All Hold

Consider this route:

~~~yaml
predicates:
  - Path=/api/orders/special/**
  - Method=GET
~~~

Both predicates are combined with **AND**: `GET /api/orders/special/42` matches, whereas `POST /api/orders/special/42` does not match this route even though the path is identical. If a general route with `Path=/api/orders/**` and no method restriction sits behind it, the POST request can fall into that general route.

**High priority does not force a request to match predicates.** `order` only controls the evaluation order among candidate routes.

### 2.2. Only One Route Is Selected Per Routing Pass

When two routes both satisfy `Path`:

1. The Gateway picks the route with the appropriate priority.
2. The **selected route's own gateway filters** execute alongside applicable shared filters.
3. The Gateway constructs the target URL and forwards the request to that route's `uri`.
4. Filters declared on the **unselected route(s)** do not run and are never "merged" into the winning route.

This matters especially for `StripPrefix`, `RewritePath`, `SetRequestHeader`, or `CircuitBreaker`: if a filter is declared on a losing route, do not expect it to affect the request.

## 3. Illustrative Configuration with Three Overlapping Routes

Suppose a test backend is running at `http://localhost:9001`. To observe **only which route is selected**, the three routes below all point to that backend and each adds a distinct header. In a real system, they could point to independent microservices or `lb://orders-service` URIs.

Example for **Spring Cloud Gateway Server WebFlux** using the new configuration namespace:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: route-priority-lab
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: special-get
              order: -20
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/special/**
                - Method=GET
              filters:
                - SetRequestHeader=X-Lab-Route, special-get
                - AddResponseHeader=X-Lab-Route, special-get

            - id: orders-general
              order: -10
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/**
              filters:
                - SetRequestHeader=X-Lab-Route, orders-general
                - AddResponseHeader=X-Lab-Route, orders-general

            - id: api-fallback
              order: 100
              uri: http://localhost:9001
              predicates:
                - Path=/api/**
              filters:
                - SetRequestHeader=X-Lab-Route, api-fallback
                - AddResponseHeader=X-Lab-Route, api-fallback
~~~

> **Configuration version:** Older Spring Cloud Gateway WebFlux versions use `spring.cloud.gateway.routes`. In that case, place the entire `routes` list under `spring.cloud.gateway.routes` instead of `spring.cloud.gateway.server.webflux.routes`. Choose the structure matching your Spring Boot/Spring Cloud version; do not define the same route in both namespaces.

| Route | `order` | Predicates | Role |
| --- | ---: | --- | --- |
| `special-get` | **-20** | `Path=/api/orders/special/**` **and** `Method=GET` | Special GET case, evaluated first |
| `orders-general` | **-10** | `Path=/api/orders/**` | Handles remaining orders requests |
| `api-fallback` | **100** | `Path=/api/**` | Catches API requests not matched by the two routes above |

The `order` property sits **at the same level** as the route's `id`, `uri`, `predicates`, and `filters`, not inside `predicates` or `filters`.

### Why Do Two Filters Add Headers?

`SetRequestHeader=X-Lab-Route, ...` sets the header **on the request** sent downstream to the backend; the backend can read it to confirm the winning route. `AddResponseHeader=X-Lab-Route, ...` sets the header **on the response** returned to the client, making results immediately visible via `curl -i`. These are lab markers, not an authentication mechanism.

The example intentionally leaves the path unchanged so route priority is easy to observe. When you need to turn `/api/orders/42` into `/orders/42`, you can add `StripPrefix=1` to the appropriate route; that behavior belongs to the **filter phase**, after the route has been selected.

## 4. Table Predicting Which Route Will Be Selected

Applying the configuration above:

| Request | Routes whose predicates match | Selected route | Reason |
| --- | --- | --- | --- |
| `GET /api/orders/special/42` | `special-get`, `orders-general`, `api-fallback` | **`special-get`** | All three match; `-20` is lowest |
| `POST /api/orders/special/42` | `orders-general`, `api-fallback` | **`orders-general`** | `special-get` fails `Method=GET` |
| `GET /api/orders/42` | `orders-general`, `api-fallback` | **`orders-general`** | `-10` takes precedence over `100` |
| `DELETE /api/orders/42` | `orders-general`, `api-fallback` | **`orders-general`** | The orders route has no `Method` predicate |
| `GET /api/customers/42` | `api-fallback` | **`api-fallback`** | Both orders routes fail `Path` |
| `GET /health-check` | None | **No route selected** | No path matches `/api/**` |

The last case typically returns `404 Not Found` if the gateway has no other WebFlux handler or route for `/health-check`. **It is not mandatory in every setup for an unmatched request to return 404**: the application may define another endpoint to handle it.

Similarly, a `Method=GET` route predicate does not automatically produce `405 Method Not Allowed` on a POST request. If another route still matches, POST is evaluated against that route; if no route or handler handles it, the result is usually 404. A backend may still return 405 once a request reaches an endpoint that allows only other methods.

## 5. Hands-On: Seeing the Winning Route Firsthand

To keep the experiment independent of multiple microservices, run a minimal echo backend that accepts any path and method and echoes the `X-Lab-Route` header received from the gateway.

### 5.1. Create a Simple WebFlux Backend

Create a Spring Boot application with the `spring-boot-starter-webflux` dependency, set `server.port=9001` in `application.properties`, and add the following code. Both classes belong to the `demo.echo` package.

~~~java
package demo.echo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EchoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EchoApplication.class, args);
    }
}
~~~

~~~java
package demo.echo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EchoController {

    @RequestMapping("/**")
    public Map<String, Object> inspect(ServerHttpRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("method", request.getMethod().name());
        result.put("path", request.getPath().value());
        result.put("query", request.getURI().getRawQuery());
        result.put("routeSeenByBackend",
                   request.getHeaders().getFirst("X-Lab-Route"));
        return result;
    }
}
~~~

The echo backend does not set the `X-Lab-Route` response header itself, so that header in responses through the gateway comes from `AddResponseHeader`. When calling `localhost:9001` directly, `routeSeenByBackend` will be `null` because no gateway filter added the header.

### 5.2. Start the WebFlux Gateway

The gateway application needs the **Spring Cloud Gateway Server WebFlux** starter and a Spring Cloud BOM compatible with Spring Boot. In newer versions, the starter is usually named `spring-cloud-starter-gateway-server-webflux`; in some older versions it is `spring-cloud-starter-gateway`. Do not mix in the Servlet MVC starter if your goal is WebFlux Gateway.

Save the YAML from section 3 into the gateway's `application.yml` and start both applications in **two separate terminals**:

~~~bash
# Inside the echo backend project directory:
./mvnw spring-boot:run

# Inside the gateway project directory:
./mvnw spring-boot:run
~~~

On Windows, you can use `mvnw.cmd spring-boot:run`. These commands are hands-on instructions; the outputs in the following sections are **expected results**, not measurements taken on the reader's machine.

### 5.3. Send Requests and Verify Headers

~~~bash
# All three routes match; special-get wins:
curl -i "http://localhost:8080/api/orders/special/42"

# special-get does not match POST; orders-general wins:
curl -i -X POST "http://localhost:8080/api/orders/special/42"

# orders-general beats api-fallback:
curl -i "http://localhost:8080/api/orders/42"

# Only api-fallback matches:
curl -i "http://localhost:8080/api/customers/42"
~~~

Expected result for the first request:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Lab-Route: special-get

{"method":"GET","path":"/api/orders/special/42","query":null,"routeSeenByBackend":"special-get"}
~~~

The remaining three requests should return `X-Lab-Route: orders-general`, `X-Lab-Route: orders-general`, and `X-Lab-Route: api-fallback`, respectively. In the JSON body, `routeSeenByBackend` matches the selected route. For the POST request, the sample controller accepts all methods and does not read a body, so it can still return 200.

**Spoofed header check:** send `-H "X-Lab-Route: chosen-by-client"`; the gateway uses `SetRequestHeader` to overwrite the value per route. The backend must see the value chosen by the gateway rather than the spoofed client value. Even so, do not use this marker header as user authentication evidence.

### 5.4. Flip Order to Observe the Change

In the lab, change **only** `order` of `orders-general` from `-10` to `-30`, then reload configuration as supported by your version/application (for static YAML, the simplest way is to restart the gateway):

~~~yaml
- id: orders-general
  order: -30
  uri: http://localhost:9001
  predicates:
    - Path=/api/orders/**
  filters:
    - SetRequestHeader=X-Lab-Route, orders-general
    - AddResponseHeader=X-Lab-Route, orders-general
~~~

Now `GET /api/orders/special/42` will select **`orders-general`** because `-30 < -20`, even though `Path=/api/orders/special/**` looks "more specific." This is a direct proof that path specificity does not automatically override route order.

Change `order` back to `-10` afterward to restore the original scenario.

## 6. Duplicate `order` Values and Multiple Route Sources

When `order` is omitted, most routes default to `0`. For example:

~~~yaml
routes:
  - id: orders-route
    uri: http://localhost:9001
    predicates:
      - Path=/api/orders/**

  - id: catch-all
    uri: http://localhost:9001
    predicates:
      - Path=/api/**
~~~

Both routes can match `GET /api/orders/42` and share priority `0`. A specific setup may exhibit stable ordering during a single run, but **you should never rely on YAML declaration order to guarantee business rules** when routes have equal `order`. Results can be affected by route sources, merging/sorting mechanisms, version changes, or route refreshes.

Common sources include:

- Routes declared in application configuration.
- Routes created via the Java DSL (such as `RouteLocatorBuilder`).
- Routes generated by a discovery locator or dynamic sources if configured.

When multiple sources contribute routes, **set `order` consistently**, keep every `id` unique, and avoid unintended predicate overlaps. If precedence is critical for business logic or security, design routes so predicates are as mutually exclusive as possible.

For example, instead of letting both `GET /api/reports/public/**` and a catch-all match the same path and hoping a security filter runs as expected, combine explicit predicates with independent authorization policies per endpoint/resource.

## 7. Distinguishing Route `order` from Filter `order`

These are two **separate layers** in Spring Cloud Gateway:

| Concept | Phase | What gets ordered | Effect |
| --- | --- | --- | --- |
| **Route `order`** | **Before** gateway filters run | Candidate routes | Which route is evaluated first when predicates overlap |
| **Filter `order`** | **After** a route is chosen | `GlobalFilter` and `GatewayFilter` in the combined chain | Which filter runs pre-logic earlier and post-logic later |
| **`WebFilter` / handler mapping order** | WebFlux layer wrapping or preceding the gateway handler | WebFlux framework filters/handlers | Coordinates overall HTTP handling; does not replace route order |

Example of a global filter:

~~~java
@Component
public class RequestTimingFilter implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             GatewayFilterChain chain) {
        long start = System.nanoTime();
        return chain.filter(exchange)
                .doFinally(signal ->
                        log.info("elapsedNanos={}",
                                System.nanoTime() - start));
    }
}
~~~

This is an **illustrative filter body snippet**: you must add the corresponding imports and a logger field in the class to compile it. Returning `-100` from `getOrder()` only affects filter ordering once a route is selected; **it does not give the route containing this filter a route priority of `-100`**. Inside the filter chain, lower-order filters typically run their **pre** phase earlier and their **post** phase later.

When you need to change which route is selected, adjust **predicates** and **route `order`**; when you need to change when timing logs run, headers are modified, or chain logic executes, inspect **filter order**.

## 8. Common Errors and How to Diagnose Them

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| Catch-all route captures specialized API | Catch-all has a lower `order` than the specific route | Compare `order` across all matching routes |
| High-priority route is not selected | Another predicate (`Method`, `Host`, `Header`...) does not match | Check **all** predicates, not just `Path` |
| Route-specific filter does not run | Request was matched to a different route | Tag each route with a marker header or inspect route ID |
| Config looks right but always returns 404 | Wrong YAML namespace or route failed to load | Check runtime routes and startup logs |
| Edited YAML but new priority has no effect | App has not reloaded config / route cache | Restart or refresh via supported mechanism |
| Backend returns 404 even though route matched | URI/path after `StripPrefix`, `RewritePath` misses backend endpoint | Compare gateway input path with path received by backend |
| Results vary across runs | Equal route priorities, multiple route sources, or refresh reordered them | Set explicit `order` and inspect active routes |

### Distinguishing 404 Before and After Routing

If a client calls `/not-api/orders/42`, no route in section 3 matches; the gateway typically returns 404. If a client calls `/api/orders/does-not-exist`, `orders-general` still matches and the gateway forwards the request so the backend returns 404. Both cases share the same HTTP status code but fail at different stages. When investigating, compare **route ID, path received by the backend, status, and trace ID**.

### Inspecting the Active Route List

In development, you can enable Spring Boot Actuator and the Gateway management endpoint for your running version to inspect route IDs, predicates, filters, URIs, and `order`. Management endpoints must be **access-restricted and secured**, never exposed publicly on the Internet. Metrics (when gateway metrics and Micrometer are enabled) can carry a `routeId` tag, helping track which route handled each request.

In systems using discovery/`lb://`, record both the **service ID** and the selected target instance. Keep in mind: **route selection** and **instance selection** are two different decisions. `order` decides *which route wins*; LoadBalancer decides *which instance receives requests* for that route.

## 9. Important Notes for Production Use

### Route Priority Is Not an Authorization Mechanism

In section 4's example, `POST /api/orders/special/42` does **not** match `special-get` yet can still flow through `orders-general`. If a special route has an authentication filter that the general route lacks, clients could take an unintended branch. Design authorization at the proper layer (such as Spring Security and backend authorization), verify every method/path/host that needs protection, and avoid relying solely on "the special route will win."

### Avoid Overly Broad Catch-All Routes

`Path=/**` or `Path=/api/**` with high priority can swallow requests meant for other services or management endpoints. Assign clear priorities to specialized routes, low priority to fallbacks, and restrict fallbacks by host/method where appropriate. Also remember that a fallback can forward an "unknown" path to a backend instead of failing fast with 404.

### Combining with Retries, Circuit Breakers, and Rate Limiting

Retry, circuit breaker, rate-limiting, or header-transformation policies live in the filter chain or corresponding security layer. They apply strictly as configured. If a request matches the wrong route, it may hit **a different resilience or rate-limit policy**. When testing `order` changes, verify HTTP codes, how many times the backend receives a request, headers, latency, and traces—especially for non-idempotent write operations.

### TLS, Forwarded Headers, and Observability

TLS for client → gateway and gateway → backend connections is configured per hop; `order` does not replace TLS controls. If a reverse proxy sits in front of the gateway, handle `Host`, `Forwarded`, and `X-Forwarded-*` under a clear trust policy: changing the host can alter `Host` predicate results. In operations, log the **selected route ID**, original method/path, status, trace ID, and processing duration while avoiding logging access tokens or sensitive data.

## 10. Self-Practice: Predict Before Running

Using the three routes declared in section 3, answer first and then verify with `curl -i`:

1. If you change `api-fallback`'s `order` from `100` to `-50`, which route will `GET /api/orders/42` take? **Answer:** `api-fallback`, because both fallback and orders match, and `-50` is evaluated first.
2. If you keep the initial `order` values but call `PUT /api/orders/special/42`, which route is chosen? **Answer:** `orders-general`; `special-get`'s `Method=GET` is not satisfied.
3. If you remove `api-fallback` and call `GET /api/customers/42`, what will the gateway do? **Answer:** no route matches; typically 404 if no other handler exists.
4. If two routes both have `order: 0`, should you rely on YAML declaration order to guarantee the right route is chosen? **Answer:** no; set explicit order values or adjust predicates so routes do not compete for the same requests.

**Remember:** In Spring Cloud Gateway WebFlux, **lower route `order` takes precedence; the first route satisfying all predicates is selected**. Only then does the gateway execute that route's filter chain and resolve the target service. Assign explicit priorities to overlapping routes, verify with real requests and route IDs, and enforce security independently of route-selection rules.
