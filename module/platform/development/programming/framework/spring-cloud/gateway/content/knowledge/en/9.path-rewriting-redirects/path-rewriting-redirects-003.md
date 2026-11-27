# SetPath: Setting the Path with a URI Template

## 1. The Problem: External URLs Differ from Microservice URLs

In the **Path Rewriting and Redirects** chapter of **SPRING_CLOUD_GATEWAY**, we saw that the gateway can accept a public URL and forward the request to microservices. What happens when the path called by the client differs from the path the backend actually supports?

Suppose the client needs a stable API:

~~~http
GET /api/orders/42?include=items HTTP/1.1
Host: api.example.test
~~~

However, the order service only implements the `GET /internal/orders/42` endpoint. We want the gateway to rewrite **just the path** from `/api/orders/42` to `/internal/orders/42`, while preserving the `include=items` query and forwarding the request via proxying.

The **`SetPath` GatewayFilter Factory** does exactly this using a **URI template**:

~~~yaml
predicates:
  - Path=/api/{resource}/{id}
filters:
  - SetPath=/internal/{resource}/{id}
~~~

For the request `/api/orders/42`, the predicate extracts `resource=orders` and `id=42`; the filter builds the new path `/internal/orders/42`. Key point: this is an **internal path change before forwarding to the backend**, not an HTTP redirect instructing the browser to call a new URL.

In Spring Cloud Gateway, route predicates decide whether a request enters a route; the filter chain handles paths/headers, service discovery, authentication, and policies such as rate limiting, retries, or circuit breakers. Understanding `SetPath` helps you keep the external API contract stable even as internal microservice endpoint structures evolve.

> **Scope:** This lesson focuses on **Spring Cloud Gateway Server WebFlux**, using `SetPath` in route configuration. Property names vary across versions, but the filter semantics remain the same. Server MVC has its own integration mechanism and Java DSL style.

## 2. Where Does SetPath Run in the Routing Flow?

A route contains an `id`, target `uri`, `predicates`, and `filters`. In WebFlux, `RoutePredicateHandlerMapping` finds the matching route for the request, and then `FilteringWebHandler` runs the route's gateway filters and relevant global filters. `SetPath` is a **gateway filter**, so it is applied **after the route has matched** and before the routing filter sends the request to the backend.

~~~mermaid
flowchart TD
    C["Client<br/>GET /api/orders/42?include=items"] --> P{"Path predicate<br/>/api/{resource}/{id}"}
    P -->|"Matches"| V["Template variables:<br/>resource=orders, id=42"]
    P -->|"Does not match"| O["Gateway evaluates other routes"]
    V --> F["SetPath<br/>/internal/{resource}/{id}"]
    F --> R["New path:<br/>/internal/orders/42"]
    R --> U["Determine target URL<br/>from route uri"]
    U --> B["orders-service<br/>GET /internal/orders/42?include=items"]
    B --> S["Backend returns response"]
    S --> C
~~~

| Stage | Path value | Meaning |
| --- | --- | --- |
| Client sends request | `/api/orders/42` | Public API surface |
| `Path` predicate evaluates | `/api/orders/42` | Route matches and extracts `resource`, `id` variables |
| `SetPath` filter runs | `/internal/orders/42` | Sets the **entire new path** from the expanded template |
| Backend receives request | `/internal/orders/42` | Actual microservice endpoint |

The query string `?include=items` is not part of the path template and normally stays attached to the request after `SetPath` replaces the path. The HTTP method, body, and headers are also not actively changed by `SetPath`. However, other filters or HTTP proxies may further modify them; when testing, observe the request arriving at the backend rather than inferring from YAML alone.

### Why doesn't SetPath invalidate the Path predicate that just matched?

`Path=/api/{resource}/{id}` was already used to **select the route** before filters ran. Afterward, `SetPath` mutates the request for downstream processing. The Gateway does not re-evaluate all predicates because the path changed. Therefore:

- The route matches on `/api/orders/42` even though the backend will see `/internal/orders/42`.
- A route with only `Path=/internal/**` **will not match** an initial `/api/orders/42` request just because another route has `SetPath`.
- If no route matches, that route's `SetPath` never runs; the gateway may return 404 if no other handler applies.

## 3. URI Template Syntax and Variables from Predicates

A URI template is a string containing **placeholders inside curly braces**. In this lesson:

~~~text
Matched path:  /api/{resource}/{id}
New path:      /internal/{resource}/{id}

GET /api/orders/42
       resource = orders
                     id = 42

SetPath → /internal/orders/42
~~~

The variables `resource` and `id` come from match information produced by predicates such as `Path`. WebFlux Gateway stores URI template variables in `ServerWebExchange` so filters like `SetPath` can consume them. You can also use multiple template segments in one route; **variable names in `SetPath` must correspond to variables available from the predicate**.

| Input request | `Path` predicate | `SetPath` | Backend path |
| --- | --- | --- | --- |
| `/api/orders/42` | `/api/{resource}/{id}` | `/internal/{resource}/{id}` | `/internal/orders/42` |
| `/api/products/SKU-7` | `/api/{resource}/{id}` | `/internal/{resource}/{id}` | `/internal/products/SKU-7` |
| `/v1/users/17/profile` | `/v1/{domain}/{id}/profile` | `/private/{domain}/{id}/profile` | `/private/users/17/profile` |
| `/public/report/daily` | `/public/{kind}/{name}` | `/documents/{kind}/{name}` | `/documents/report/daily` |

### 3.1. Variables are not auto-generated from placeholder names

If you configure:

~~~yaml
predicates:
  - Path=/api/orders/**
filters:
  - SetPath=/internal/orders/{id}
~~~

then `**` is a wildcard used for path matching, and it **does not automatically create a variable named `id`**. The filter lacks a bound `id` value to expand the template; depending on the version and error-handling path, the request may fail when the filter runs. The fix is to declare a predicate that actually extracts the ID:

~~~yaml
predicates:
  - Path=/api/orders/{id}
filters:
  - SetPath=/internal/orders/{id}
~~~

If you need to accept several different path structures, design multiple routes, or use `RewritePath` when a regular expression fits the requirement. Avoid assuming `SetPath` can infer IDs from wildcards.

### 3.2. Preserving, reordering, or dropping variables

The target template does not have to mirror the original path structure:

~~~yaml
# Client: /legacy/orders/42
# Backend: /v2/42/orders
predicates:
  - Path=/legacy/{type}/{id}
filters:
  - SetPath=/v2/{id}/{type}
~~~

`SetPath` can insert fixed path segments (`/v2`), reorder variables (`{id}` before `{type}`), or omit an unneeded variable. It **sets the path to the expanded template result**, rather than merely stripping a prefix. Detailed behavior for special characters, path encoding/decoding, and slashes should be verified against your exact Spring Framework, gateway, upstream proxy, and backend versions.

### 3.3. A template is not JSON, regex, or an arbitrary string

- `{id}` is a URI template variable; `SetPath` does not parse a JSON body to find `id`.
- `SetPath=/internal/{id}` is **not a regex** with named capture group `(?<id>...)`.
- `SetPath` only targets the **request path**; it does not set scheme/host/port like `uri: http://localhost:9091` and does not create a redirect response.
- If you also need to modify query parameters, use the corresponding query manipulation filters. Do not append `?foo=bar` inside the path assuming it is part of the path template.
- For paths containing spaces, `%2F`, Unicode, or `;`, test end-to-end; never concatenate strings from untrusted input for routing or sensitive authorization decisions.

## 4. Complete Route Configuration with SetPath

Suppose the gateway listens on `localhost:8080` and the microservice on `localhost:9091`. To observe the filter clearly, we add request/response marker headers; those two headers are for testing only.

### 4.1. Configuration for Gateway Server WebFlux 5.x

~~~yaml
server:
  port: 8080

spring:
  application:
    name: gateway-setpath-lab
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: setpath-demo
              order: -10
              uri: http://localhost:9091
              predicates:
                - Path=/api/{resource}/{id}
                - Method=GET,POST
              filters:
                - SetPath=/internal/{resource}/{id}
                - SetRequestHeader=X-Gateway-Route, setpath-demo
                - AddResponseHeader=X-Path-Rule, setpath-demo
~~~

With path `/api/orders/42?include=items`, the gateway selects route `setpath-demo`, builds path `/internal/orders/42`, adds the `X-Gateway-Route` header, and forwards to the declared backend URI. When the backend responds, the gateway adds the `X-Path-Rule` response header.

**Filter declaration order:** In this lab, `SetPath` does not conflict with the two header-setting filters. When multiple filters modify the path—such as `StripPrefix`, `PrefixPath`, `RewritePath`, and `SetPath`—the outcome depends on actual execution order. Keep one clear path transformation rule per route and verify with real requests.

### 4.2. Configuration for Gateway Server WebFlux 4.2.x and 4.3.x

Official documentation for WebFlux Gateway **4.2.x and 4.3.x** uses `spring.cloud.gateway.routes`:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      routes:
        - id: setpath-demo
          order: -10
          uri: http://localhost:9091
          predicates:
            - Path=/api/{resource}/{id}
            - Method=GET,POST
          filters:
            - SetPath=/internal/{resource}/{id}
            - SetRequestHeader=X-Gateway-Route, setpath-demo
            - AddResponseHeader=X-Path-Rule, setpath-demo
~~~

Pick **one namespace** matching your project dependencies/version. Using the wrong namespace can allow the app to start without loading routes, causing 404s even though the YAML looks valid.

### 4.3. Full argument syntax for SetPath

Beyond the shortcut `SetPath=/internal/{resource}/{id}`, you can specify the filter name and parameter explicitly:

~~~yaml
filters:
  - name: SetPath
    args:
      template: /internal/{resource}/{id}
~~~

Both forms define the same filter with one `template` argument. The full form is suitable when you want explicit config structure or generate YAML programmatically. By default, the template is expanded using the URI variables already stored in the exchange.

## 5. Practice: Echo Backend to Observe the Path After SetPath

A good test is having the backend return the **method, path, query, headers, and body** it received. That lets you verify `SetPath` at the actual destination rather than relying solely on the final gateway response.

Create a standalone Spring Boot application with the `spring-boot-starter-webflux` dependency and package `demo.echo`. Configure `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: echo-service

server:
  port: 9091
~~~

Main class `EchoApplication.java`:

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

Test controller `EchoController.java`:

~~~java
package demo.echo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class EchoController {

    private Map<String, Object> describe(ServerHttpRequest request,
                                          String resource,
                                          String id) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("method", request.getMethod().name());
        result.put("path", request.getPath().value());
        result.put("query", request.getURI().getRawQuery());
        result.put("resource", resource);
        result.put("id", id);
        result.put("gatewayRoute",
                request.getHeaders().getFirst("X-Gateway-Route"));
        return result;
    }

    @GetMapping("/internal/{resource}/{id}")
    public Map<String, Object> inspectGet(
            @PathVariable String resource,
            @PathVariable String id,
            ServerHttpRequest request) {
        return describe(request, resource, id);
    }

    @PostMapping("/internal/{resource}/{id}")
    public Mono<Map<String, Object>> inspectPost(
            @PathVariable String resource,
            @PathVariable String id,
            @RequestBody Mono<Map<String, Object>> payload,
            ServerHttpRequest request) {
        return payload.map(body -> {
            Map<String, Object> result = describe(request, resource, id);
            result.put("body", body);
            return result;
        });
    }
}
~~~

This backend application accepts `GET` and `POST` at `/internal/{resource}/{id}`. The gateway route extracts the two variables from the **external** path, while the Spring controller extracts variables from the **rewritten** path. They may hold the same values, yet they exist in two separate processes and request contexts.

In the gateway project using the Spring Cloud Gateway **Server WebFlux starter** and a Spring Cloud BOM compatible with Spring Boot, add the configuration from Section 4 to `application.yml`. Newer releases usually name the starter `spring-cloud-starter-gateway-server-webflux`; earlier ones use `spring-cloud-starter-gateway`. Avoid adding the Servlet MVC starter to an application intended to run Gateway WebFlux.

Start both applications in separate terminals:

~~~bash
# Terminal 1: inside the echo backend project directory
./mvnw spring-boot:run

# Terminal 2: inside the gateway project directory
./mvnw spring-boot:run
~~~

On Windows you can run `mvnw.cmd spring-boot:run` or an installed Maven via `mvn spring-boot:run`. These commands only work after creating both Maven projects with the proper dependencies.

### 5.1. Verifying GET through the gateway

~~~bash
curl -i "http://localhost:8080/api/orders/42?include=items"
~~~

**Illustrative** result, not a response captured from a live system:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Path-Rule: setpath-demo

{"method":"GET","path":"/internal/orders/42","query":"include=items","resource":"orders","id":"42","gatewayRoute":"setpath-demo"}
~~~

Seeing path `/internal/orders/42` and header `gatewayRoute=setpath-demo` gives two independent signals: the route was selected and the transformed path reached the backend. The `query` field confirms `SetPath` does not drop the query string.

### 5.2. Verifying that the POST body is forwarded

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/42" \
  -H "Content-Type: application/json" \
  --data-binary '{"operation":"confirm","quantity":2}'
~~~

Expected response payload:

~~~json
{
  "method": "POST",
  "path": "/internal/orders/42",
  "query": null,
  "resource": "orders",
  "id": "42",
  "gatewayRoute": "setpath-demo",
  "body": {
    "operation": "confirm",
    "quantity": 2
  }
}
~~~

In this lab, the `SetPath` filter only changes the path; it does not read or rewrite the body itself. JSON re-serialized by the backend after decoding may differ in whitespace or field ordering from the original payload. To compare **byte-for-byte**, use a separate backend checksum or raw-byte echo endpoint.

If using Windows PowerShell, prefer `curl.exe`; for large JSON payloads, save to a UTF-8 file and pass `--data-binary "@payload.json"` to avoid quoting issues.

### 5.3. Comparing with direct backend calls

~~~bash
# Path the backend actually supports
curl -i "http://localhost:9091/internal/orders/42?include=items"

# Public path that does not exist on the lab backend
curl -i "http://localhost:9091/api/orders/42?include=items"
~~~

The first command typically returns 200; the second typically returns 404. Through the gateway, the client still calls `/api/orders/42` while the backend receives `/internal/orders/42`. That behavior is the essence of **path rewriting**.

### 5.4. Smoke test table

| Request to gateway | Matches route? | Forwarded path | Expected outcome |
| --- | --- | --- | --- |
| `GET /api/orders/42` | Yes | `/internal/orders/42` | 200, JSON resource `orders`, id `42` |
| `GET /api/products/SKU-7?lang=vi` | Yes | `/internal/products/SKU-7` | 200, query keeps `lang=vi` |
| `POST /api/orders/42` with valid JSON | Yes | `/internal/orders/42` | 200 and JSON echoed body |
| `GET /api/orders/42/extra` | No, extra segment | Not forwarded via lab route | Usually 404 if no other route matches |
| `GET /api/orders` | No, missing `{id}` | Not forwarded via lab route | Usually 404 if no other route matches |
| `DELETE /api/orders/42` | No, due to `Method=GET,POST` | Not forwarded via lab route | Usually 404 if no other handler matches |

Do not assume the `DELETE` request in the last row returns **405** from the gateway: the Method predicate does not match, so this route is not selected. An HTTP 405 may come from the **backend** or from a different handler that matched but does not support the method.

## 6. Comparing SetPath, StripPrefix, RewritePath, and Redirects

| Mechanism | How it works | Example | When to use |
| --- | --- | --- | --- |
| **`SetPath`** | Replaces the entire path with a **URI template** expanded from variables | `/api/{resource}/{id} → /internal/{resource}/{id}` | New path has a clear structure using predicate variables |
| **`StripPrefix`** | Removes a number of leading path segments | `/api/orders/42 → /orders/42` with `StripPrefix=1` | Only need to remove a fixed prefix |
| **`PrefixPath`** | Prepends a prefix to the path | `/orders/42 → /internal/orders/42` | Only need to prepend a fixed prefix |
| **`RewritePath`** | Transforms the path using a **regular expression** and replacement | Capture regex groups for flexible substitution | Rules too complex for simple URI templates |
| **`RedirectTo`** | Gateway returns a **3xx** response and `Location` to the client | Sends client to another URL | Client must make a new request, e.g., public URL migration |

**Distinguishing example:** if a client calls `GET /api/orders/42`:

- `SetPath=/internal/orders/42`: the gateway calls the backend at the new path itself. The client sees the backend response and normally **does not see HTTP 3xx** just because of SetPath.
- `RedirectTo=302, https://new.example.test/orders/42`: the gateway returns **302** with `Location`; the client decides whether to follow the redirect. Plain `curl -i` shows the 302 response, whereas `curl -L` attempts to follow it.

Thus, **SetPath is not a redirect mechanism** even though it belongs to the same topic of path transformation and redirects.

### When is SetPath not the right fit?

- You only want to strip `/api` from any URL without knowing the remaining segment count ahead of time: `StripPrefix=1` is usually simpler.
- You need regex-based path replacement with complex capture groups: use `RewritePath` and check YAML escaping rules.
- You want to send users to a new public domain or page: use an appropriate HTTP redirect.
- You want to change host, scheme, query, or body: configure dedicated mechanisms for those parts.

## 7. Common Errors and How to Diagnose Them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Client always gets 404, no backend logs | No route matches or route config not loaded | Check `Path`, `Method`, and configuration namespace |
| `SetPath` fails on placeholder | Variable missing from URI template variables, e.g. `{id}` used when predicate only has `**` | Ensure variable names in `SetPath` match capturing predicates like `Path` |
| Backend receives original path | Filter did not run or a different route was selected | Verify route ID, `X-Path-Rule` header, and backend request |
| Backend receives doubly-modified path | Combined with `StripPrefix`, `PrefixPath`, `RewritePath`, or custom filter | Audit filter chain and order; simplify path transformations |
| Client gets 404 but backend logs request | Route matched, `SetPath` produced a path backend does not support | Compare URI after SetPath against controller mappings |
| Query missing or changed | Another filter or upstream reverse proxy altered query | Compare incoming request, routed URL, and backend request |
| Empty POST body after path change | Custom filter or other body processor consumed `Flux<DataBuffer>` | Check body modifiers/decorators; SetPath itself does not read the body |
| Response is 401/403/429 | Security or rate limiter blocked the request | Inspect policy and filter position; not a default SetPath status |
| `lb://service-id` config returns 503 | LoadBalancer cannot find instances for service | Check registry, discovery, service ID, and instances |

### 7.1. Be careful with path variables and security

Never assume URI template variables are pre-validated data. Clients control the incoming path; if the backend has administrative endpoints or privileged routes, an overly broad template substitution can route requests to unintended places.

For instance, checking only `Path=/api/{resource}/{id}` while allowing any `resource` lets clients supply arbitrary values. In real systems, constrain the valid `resource` set, split routes by specific API when needed, and enforce **authorization at both gateway and backend** on the actual target resource. Do not let a broad catch-all route accidentally bypass a specific route's security filters.

For paths containing `%2F` (encoded slash), `..`, Unicode, or special characters, test decoding/normalization behavior across **ingress, WebFlux/Gateway, and backend**. Discrepancies between layers can cause authorization checks to evaluate a different path from the one the backend ultimately handles. SetPath is no substitute for safe validation and normalization.

### 7.2. Route order and filter order are two separate concepts

When two routes both match, the route with the **smaller** `order` is usually evaluated first and the first match wins. `SetPath` only runs if the route containing it is selected. Then, filter order governs execution sequence within that route.

For example, `GET /api/orders/42` matches both a specific route `Path=/api/orders/{id}` and a broad route `Path=/api/**`. If the broad route wins, `SetPath` on the specific route never runs. Use route IDs, metrics, or marker headers in a lab environment to verify which route actually ran.

### 7.3. The path changes, but what about queries, headers, and bodies?

With **`SetPath` alone**, the filter's job is to set the request path. However, Spring Cloud Gateway acts as an HTTP proxy with many other filters; therefore:

- Headers such as `Host`, `Connection`, and `Transfer-Encoding` may be handled hop-by-hop; do not assume all client headers pass through byte-for-byte.
- `Forwarded` and `X-Forwarded-*` should be verified at trusted proxies, especially when TLS terminates before the gateway.
- `Query parameters` can still be modified by query rewrite/add/remove filters.
- The `Body` may be touched by body-modifying filters or retries; account for idempotency, payload size, backpressure, and body buffering.

These behaviors are not caused by SetPath by default, but they frequently occur alongside it in microservices deployments.

## 8. Using SetPath with Discovery and Operations

To replace a static URI with service discovery:

~~~yaml
routes:
  - id: orders-service-api
    uri: lb://orders-service
    predicates:
      - Path=/api/orders/{id}
    filters:
      - SetPath=/internal/orders/{id}
~~~

The snippet above is a **partial `routes` list entry**; place it under the correct namespace for your Gateway WebFlux version. The `lb://orders-service` URI requires Spring Cloud LoadBalancer and an appropriate instance-list provider. `SetPath` still updates the request path; LoadBalancer selects the target backend instance, and the routing filter sends the HTTP request.

In production, pair path transformations with:

1. **Authentication and authorization:** audit public routes, internal endpoints, and resource permissions. SetPath does not validate tokens or grant permissions.
2. **Rate limiting:** verify rate-limit keys by user/API key/trusted IP, and avoid overlapping routes applying the wrong policy.
3. **Circuit breaker, retry, and timeout:** monitor how many times the backend receives a request; retries on POST endpoints that create orders or payments require idempotency and body replayability.
4. **TLS:** verify HTTPS connections for client → gateway and gateway → service by design; SetPath does not enable HTTPS or verify certificates.
5. **Observability:** logs/metrics/traces should distinguish the **client-called path**, **route ID**, **transformed path/URL**, **target instance**, status, and latency. Avoid logging access tokens or bodies with sensitive data.

### Quick deployment verification commands

~~~bash
# Expected route with query preserved
curl -i "http://localhost:8080/api/orders/42?include=items"

# Another resource sharing the same URI template
curl -i "http://localhost:8080/api/products/SKU-7?lang=vi"

# Path missing variable: should not match route
curl -i "http://localhost:8080/api/orders"

# Method not allowed by route
curl -i -X DELETE "http://localhost:8080/api/orders/42"
~~~

With the test setup in Sections 4–5, the first two requests reach the backend under `/internal/...`; the last two do not match the lab route. In a deployment with additional routes, the final status and target depend on those other routes/handlers.

## 9. Self-Check Questions

**1. A client calls `/api/customers/7`, with `Path=/api/{resource}/{id}` and `SetPath=/v2/{id}/{resource}`. Which path does the backend receive?**

Answer: `/v2/7/customers`. Placeholder order in the target template determines the new structure.

**2. If the predicate is `Path=/api/orders/**`, can `SetPath=/orders/{id}` obtain `id`?**

You cannot rely on the `**` wildcard to produce a variable named `id`. You need a predicate that captures `{id}` or an alternative filter design.

**3. Why doesn't SetPath itself cause the client to receive 301/302?**

Because SetPath modifies the request forwarded by the gateway to the backend within the same HTTP exchange. A redirect is a 3xx response with `Location` returned by the gateway or backend so the client can decide whether to issue a new request.

**4. If the backend returns 404 after SetPath, is that definitely a route-selection error?**

No. The route may have matched, while the new path has no matching controller on the backend. Inspect backend logs, route ID, and the transformed path to pinpoint the fault.

**5. When switching from a static URI to `lb://orders-service`, does SetPath still apply?**

Yes. SetPath still determines the path sent to the service; discovery/LoadBalancer handles selecting the target instance. They solve two independent problems.

## 10. Version Reference Documentation

- [Spring Cloud Gateway Server WebFlux — SetPath GatewayFilter Factory (5.x)](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/setpath-factory.html)
- [Spring Cloud Gateway Server WebFlux — SetPath GatewayFilter Factory (4.3.x)](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/setpath-factory.html)
- [Spring Cloud Gateway — SetPath GatewayFilter Factory (4.2.x)](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/gatewayfilter-factories/setpath-factory.html)

**Key takeaway:** `SetPath` sets the **entire request path** using a URI template after a route predicate matches. Template variables must be supplied by predicates; queries, methods, headers, and bodies are not the filter's direct target. When deploying Spring Cloud Gateway, verify the **actual path at the backend**, maintain security boundaries at both the gateway and service layers, and clearly distinguish internal path rewriting from HTTP redirects.
