# BeforeFilterFunctions, AfterFilterFunctions, and HandlerFilterFunction

## 1. How Can an MVC Route Intercept Requests and Responses?

In **Spring Cloud Gateway Server Web MVC**, the API Gateway receives client requests, matches **route predicates**, runs filters before/after proxying to microservices, can rewrite paths and headers, uses service discovery to select backends, and integrates authentication, rate limiting, circuit breakers, retries, TLS, and observability. Unlike the **Server WebFlux** variant, Server Web MVC is built on the **Servlet stack** and **Spring WebMvc.fn**.

Consider a realistic requirement:

1. The client calls `GET /api/echo` on the Gateway.
2. The Gateway rewrites the path to `/echo` and adds `X-Route-Tag: mvc-demo` before calling the backend.
3. The backend returns data with status 200.
4. The Gateway attaches `X-Gateway-After: applied` to the response returned to the client.
5. If the request carries a test flag `X-Lab-Block: yes`, a custom filter must **reject before proxying**, without calling the backend.

With Gateway MVC's Java Routes API, the three main tools for this requirement are:

- **`BeforeFilterFunctions`**: functions that process the **request before the handler**; the Java Routes API uses `.before(...)`.
- **`AfterFilterFunctions`**: functions that process the **response after the handler**; the Java Routes API uses `.after(...)`.
- **`HandlerFilterFunction`**: a general filter **wrapping the handler**, able to act before and after `next.handle(request)`, short-circuit early, or coordinate other logic; uses `.filter(...)`.

This lesson belongs to the **Server Web MVC** chapter of the **SPRING_CLOUD_GATEWAY** module, focusing on using these three filter types according to their responsibilities rather than confusing them with Server WebFlux's `GlobalFilter`/`GatewayFilterFactory` or the Servlet container's `jakarta.servlet.Filter`.

Objectives:

1. Understand Gateway MVC's WebMvc.fn `RouterFunction → HandlerFunction → ServerResponse` flow.
2. Distinguish the contracts and positions of `before`, `after`, and `filter`.
3. Use built-in functions to modify request/response headers and paths.
4. Write custom `Function<ServerRequest, ServerRequest>`, `BiFunction<ServerRequest, ServerResponse, ServerResponse>`, and `HandlerFilterFunction<ServerResponse, ServerResponse>`.
5. Run a Gateway MVC → echo backend lab and test the short-circuit rejection branch.
6. Understand filter scope, error handling, execution order, Servlet Filters, body handling, and security/operational impacts.

> **Scope:** The Java code below targets Spring Cloud Gateway **Server Web MVC**, using synchronous WebMvc.fn on a Servlet runtime. When an actual application uses Server WebFlux, write the matching reactive APIs rather than mechanically swapping imports.

## 2. WebMvc.fn Foundations in Gateway Server Web MVC

Spring WebMvc.fn provides a functional way to declare routes alongside the `@Controller` model:

| Concept | Java type | Responsibility |
| --- | --- | --- |
| Route predicate | `RequestPredicate` | Determines whether a request matches a route |
| Request | `ServerRequest` | Accesses method, path, headers, params, body |
| Handler | `HandlerFunction<ServerResponse>` | Handles a request and returns `ServerResponse` |
| Response | `ServerResponse` | Holds status, headers, and body |
| Route | `RouterFunction<ServerResponse>` | Selects a handler when a request matches |
| General filter | `HandlerFilterFunction<T,R>` | Wraps a handler or the next filter |
| Route builder | `RouterFunctions.Builder` | Combines predicates, handlers, and before/after/filter |

In Gateway MVC, the HTTP proxy handler provided by Gateway is **`HandlerFunctions.http()`**. The backend address can be set using **`BeforeFilterFunctions.uri(...)`**, typically paired with **`GatewayRouterFunctions.route("route-id")`** to carry route ID metadata for advanced filters.

~~~mermaid
flowchart LR
    C["Client"] --> S["DispatcherServlet"]
    S --> P["RouterFunction<br/>match predicate"]
    P --> F["HandlerFilterFunction chain"]
    F --> B["Before request transformations"]
    B --> H["HandlerFunctions.http()"]
    H --> U["Backend microservice"]
    U --> A["After response transformations"]
    A --> C
~~~

This diagram is a conceptual model. A `HandlerFilterFunction` can run **both before and after** calling `next`; `before/after` functions are plugged into the chain via WebMvc.fn's adaptation mechanism. Exact ordering across multiple filters or nested routes must be verified with tests rather than inferred solely from diagram placement.

### 2.1. Comparing Web MVC and WebFlux

| Aspect | Gateway Server Web MVC | Gateway Server WebFlux |
| --- | --- | --- |
| Web stack | Spring MVC/WebMvc.fn, Servlet/Tomcat/Jetty | Spring WebFlux, reactive Netty |
| Request type | `org.springframework.web.servlet.function.ServerRequest` | `ServerWebExchange`, `ServerHttpRequest` |
| Java route | `RouterFunction<ServerResponse>` | `RouteLocator` or route config |
| Proxy handler | `HandlerFunctions.http()` | Netty routing filter in reactive chain |
| Custom filters | `HandlerFilterFunction`/`before`/`after` | `GatewayFilter`/`GlobalFilter` |
| Filter result | `ServerResponse` directly | Typically `Mono<Void>` |
| Threading | Servlet request threads, controlled blocking I/O | Non-blocking reactive event loop |
| Built-in filter classes | `BeforeFilterFunctions`, `AfterFilterFunctions` | `GatewayFilterFactory`, `GlobalFilter` |

**Do not write** `Mono<Void> filter(ServerWebExchange, GatewayFilterChain)` into a Web MVC route expecting `.before(...)` to accept it. Conversely, a `HandlerFilterFunction` calling `next.handle(...)` is a **Servlet/WebMvc.fn** API, not a WebFlux `WebFilter`.

### 2.2. Use the Starter Matching Your Version

Per Spring Cloud Gateway documentation:

| Gateway Server MVC line | Maven starter | YAML route namespace |
| --- | --- | --- |
| 4.2.x (named "Server MVC") | `spring-cloud-starter-gateway-mvc` | `spring.cloud.gateway.mvc.routes` |
| 4.3.x ("Server Web MVC") | `spring-cloud-starter-gateway-server-webmvc` | `spring.cloud.gateway.server.webmvc.routes` |
| 5.0.x/5.1.x ("Server Web MVC") | `spring-cloud-starter-gateway-server-webmvc` | `spring.cloud.gateway.server.webmvc.routes` |

Always use a **Spring Cloud BOM compatible with your Spring Boot** version. Do not mix releases arbitrarily. The Java Routes API examples below correspond to versions supporting `GatewayRouterFunctions`, `HandlerFunctions.http()`, and before/after/filter; verify the Java API of your exact patch when upgrading.

Example dependency for newer Gateway MVC lines:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>
~~~

Gateway MVC runs on a Servlet container. **Do not add the WebFlux starter "to enable `BeforeFilterFunctions`"**—that is a different filter system. For the lab's echo backend, Spring MVC/Servlet is also a straightforward choice.

## 3. Nature of the Three Filter APIs

### 3.1. `BeforeFilterFunctions` — Request Transformation Only

Input type of `RouterFunctions.Builder.before(...)`:

~~~java
java.util.function.Function<ServerRequest, ServerRequest>
~~~

A before function receives the initial request and returns the request for subsequent processing:

~~~java
Function<ServerRequest, ServerRequest> before =
        request -> ServerRequest.from(request)
                .header("X-Lab-Before", "added")
                .build();
~~~

Here, `ServerRequest.from(request)` builds a new request with an extra header. You **do not** call `next.handle(...)` because a before processor focuses solely on the request. Gateway docs recommend preferring specialized functions in `BeforeFilterFunctions` when they meet your goal, such as:

~~~java
BeforeFilterFunctions.uri("http://127.0.0.1:9091")
BeforeFilterFunctions.stripPrefix(1)
BeforeFilterFunctions.addRequestHeader("X-Route-Tag", "mvc-demo")
~~~

**Watch out for duplicate headers:** `addRequestHeader` means "append"; when protecting identity/authorization headers, do not assume adding will remove a value already sent by the client. Use set/remove header functions as needed and verify what the backend receives.

### 3.2. `AfterFilterFunctions` — Adjusting the Response After the Handler

Input type of `RouterFunctions.Builder.after(...)`:

~~~java
java.util.function.BiFunction<ServerRequest, ServerResponse, ServerResponse>
~~~

An after function sees both the request and the response returned by the inner handler/filters:

~~~java
BiFunction<ServerRequest, ServerResponse, ServerResponse> after =
        (request, response) -> {
            response.headers().add("X-Lab-After", "added");
            return response;
        };
~~~

Built-in examples:

~~~java
AfterFilterFunctions.addResponseHeader("X-Gateway-After", "applied")
AfterFilterFunctions.setResponseHeader("X-Response-Policy", "v2")
~~~

`addResponseHeader` appends a value; `setResponseHeader` replaces values of the same name per Gateway semantics. For single-valued security headers on responses, **appending duplicates** can cause clients/proxies to interpret them inconsistently. In an API Gateway, decide explicitly whether to *set*, *add*, or *remove*.

Spring WebMvc.fn describes `ServerRequest` and `ServerResponse` as mostly immutable interfaces, though Spring Cloud Gateway MVC includes implementations that permit header modifications for proxying. Using `response.headers().add(...)` is the main pattern shown in Gateway docs for custom after filters. **Do not infer from this that every `ServerResponse` created by any library can be mutated indefinitely, even after the response has been committed.**

### 3.3. `HandlerFilterFunction` — Wrapping the Entire Handler

General contract:

~~~java
@FunctionalInterface
public interface HandlerFilterFunction<T extends ServerResponse,
        R extends ServerResponse> {
    R filter(ServerRequest request, HandlerFunction<T> next)
            throws Exception;
}
~~~

Note that this is the **illustrative contract signature**, not a request to redeclare Spring's interface. With the common type:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse>
~~~

you can:

- Inspect the request **before** calling `next.handle(request)`.
- Construct a new request and pass it into `next.handle(modifiedRequest)`.
- **Short-circuit the chain** by returning a different `ServerResponse` without calling `next`.
- Inspect the response after `next` returns, adjust headers, or record metrics.
- Wrap in `try/finally` to measure duration even when downstream fails.

Example:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> audit =
        (request, next) -> {
            long started = System.nanoTime();
            try {
                ServerResponse response = next.handle(request);
                response.headers().add("X-Lab-HandlerFilter", "passed");
                return response;
            } finally {
                long elapsed = System.nanoTime() - started;
                // Send elapsed to controlled metrics/logs.
            }
        };
~~~

**You do not need `HandlerFilterFunction` for everything.** If you only add a request header, `.before(...)` expresses the intent more clearly; if you only add a response header, `.after(...)` is clearer. Use `.filter(...)` when you genuinely need **before/after/short-circuit/error-handling** control.

### 3.4. Quick Comparison

| Characteristic | `.before(...)` | `.after(...)` | `.filter(...)` |
| --- | --- | --- | --- |
| Primary contract | `Function<ServerRequest,ServerRequest>` | `BiFunction<ServerRequest,ServerResponse,ServerResponse>` | `HandlerFilterFunction<T,R>` |
| Access to request? | Yes | Yes | Yes |
| Access to handler response? | Not yet | Yes | Yes, if `next` is called |
| Can skip calling handler? | No, per processor contract | No | Yes |
| Typical use | Inbound path/header/URI | Response headers/appropriate status policy | Auth gate, audit timing, coordinating logic |
| Java DSL syntax | `.before(fn)` | `.after(fn)` | `.filter(fn)` |
| Complexity | Low | Low | Higher; manages `next`/errors |

In all three cases, filters **run only for routes scoped to that router builder after the predicate matches**, not automatically for every request in the Servlet container.

## 4. One Java Route Using `before`, `after`, and `filter` Together

The example below uses **one Gateway MVC app** and **one echo backend**. Gateway listens on `localhost:8080`, backend on `localhost:9091`.

### 4.1. Gateway Entry Class

In a project with `spring-cloud-starter-gateway-server-webmvc` (4.3+/5.x) and a compatible Spring Cloud BOM:

`src/main/java/demo/mvcgateway/MvcGatewayApplication.java`:

~~~java
package demo.mvcgateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcGatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcGatewayApplication.class, args);
    }
}
~~~

Gateway's `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: mvc-filter-lab-gateway
~~~

In the **Java Routes API** approach below, there is no need to declare the same route ID again in YAML.

### 4.2. Writing Custom Filter Functions with Explicit Types

`src/main/java/demo/mvcgateway/DemoMvcFilters.java`:

~~~java
package demo.mvcgateway;

import java.util.function.BiFunction;
import java.util.function.Function;

import org.springframework.http.HttpStatus;
import org.springframework.web.servlet.function.HandlerFilterFunction;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

public final class DemoMvcFilters {

    private DemoMvcFilters() {
    }

    // BEFORE: create a new ServerRequest with an extra header.
    public static Function<ServerRequest, ServerRequest> beforeMarker() {
        return request -> ServerRequest.from(request)
                .header("X-Mvc-Before", "custom-before")
                .build();
    }

    // AFTER: operate on the response returned by the handler/filter.
    public static BiFunction<ServerRequest, ServerResponse, ServerResponse>
            afterMarker() {
        return (request, response) -> {
            response.headers().add(
                    "X-Mvc-After-Custom", "custom-after");
            return response;
        };
    }

    // HANDLER FILTER: can short-circuit or wrap next.
    public static HandlerFilterFunction<ServerResponse, ServerResponse>
            blockLabRequest() {

        return (request, next) -> {
            String labFlag =
                    request.headers().firstHeader("X-Lab-Block");

            if ("yes".equalsIgnoreCase(labFlag)) {
                // Lab flag only; NOT real security/auth.
                return ServerResponse.status(HttpStatus.FORBIDDEN)
                        .header("X-Mvc-Decision", "blocked")
                        .body("Blocked by the demo filter");
            }

            long start = System.nanoTime();
            try {
                ServerResponse response = next.handle(request);
                response.headers().add(
                        "X-Mvc-Decision", "forwarded");
                return response;
            } finally {
                long elapsedNanos = System.nanoTime() - start;
                // Lab: replace with a low-cardinality histogram metric.
                // Do not log request body, Cookie, or Authorization.
            }
        };
    }
}
~~~

Notes:

- `beforeMarker()` is a **Function**, never calls `next`, and receives no response.
- `afterMarker()` is a **BiFunction**, operating on an existing response; method name is arbitrary, while the return type must satisfy `.after(...)`.
- `blockLabRequest()` returns a **HandlerFilterFunction**, inspects the lab flag, and can return `403` **without calling `next`**.
- When `next.handle(request)` returns, the filter attaches `X-Mvc-Decision: forwarded`. `finally` is useful for timing even on errors, though it does not turn exceptions into 200 responses.
- The code neither copies request bodies nor stores per-request state in shared fields. These filter factory functions are safe across concurrent requests.
- `elapsedNanos` is kept intentionally just to show where metrics plug in; this lesson does not add a full monitoring stack.

**Important:** `X-Lab-Block` is client-supplied, so it is purely a **testing tool for the short-circuit branch**, never production authorization. Clients can omit it or pass any value.

### 4.3. Wiring Filters into a Java `RouterFunction`

`src/main/java/demo/mvcgateway/MvcRouteConfig.java`:

~~~java
package demo.mvcgateway;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static demo.mvcgateway.DemoMvcFilters.afterMarker;
import static demo.mvcgateway.DemoMvcFilters.beforeMarker;
import static demo.mvcgateway.DemoMvcFilters.blockLabRequest;
import static org.springframework.cloud.gateway.server.mvc.filter.AfterFilterFunctions.addResponseHeader;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.addRequestHeader;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.stripPrefix;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;

@Configuration(proxyBeanMethods = false)
public class MvcRouteConfig {

    @Bean
    RouterFunction<ServerResponse> mvcFilterLabRoute() {
        return route("mvc-filter-lab")
                .GET("/proxy/echo", http())
                .before(uri("http://127.0.0.1:9091"))
                .before(stripPrefix(1))
                .before(addRequestHeader(
                        "X-Route-Tag", "mvc-route"))
                .before(beforeMarker())
                .filter(blockLabRequest())
                .after(addResponseHeader(
                        "X-Gateway-After", "applied"))
                .after(afterMarker())
                .build();
    }
}
~~~

**Key lines:**

1. `route("mvc-filter-lab")` creates a builder with a route ID, useful for Gateway filter metadata.
2. `.GET("/proxy/echo", http())` matches GET requests on that path using the HTTP proxy handler.
3. `.before(uri(...))` supplies the destination URI for `HandlerFunctions.http()`. Legacy `http(String)`/`http(URI)` overloads have been **deprecated since Gateway 4.1.7**; prefer `http()` with `uri()`.
4. `.before(stripPrefix(1))` strips the `proxy` segment so the backend receives `/echo`. This happens pre-routing and does not alter the response.
5. `.before(addRequestHeader(...))` attaches a Gateway-controlled header to the request going to the backend.
6. `.before(beforeMarker())` uses our **custom Function**, not a built-in name.
7. `.filter(blockLabRequest())` registers a **HandlerFilterFunction** that can reject requests and wrap the handler.
8. `.after(addResponseHeader(...))` applies built-in **`AfterFilterFunctions`** to attach a header returned to the client.
9. `.after(afterMarker())` applies our **custom BiFunction** to the response.

Chaining `.before(...).after(...).filter(...)` follows WebMvc.fn's Java Routes API. Filters execute through function wrapping/composition rather than simply running top-to-bottom as a flat list and reversing; when reordering or adding nested routes, **verify actual conditions with tests**, especially around short-circuiting and retries.

### 4.4. Use `GatewayRouterFunctions.route()` or `RouterFunctions.route()`?

Spring Framework provides:

~~~java
org.springframework.web.servlet.function.RouterFunctions.route()
~~~

Gateway MVC also provides:

~~~java
org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route(
        "mvc-filter-lab")
~~~

Gateway docs explain that Gateway's builder attaches **route ID metadata** to request attributes, letting advanced filters identify the route. For proxy routes using advanced filters, prefer `GatewayRouterFunctions.route("...")`. For ordinary WebMvc.fn handlers, `RouterFunctions.route()` remains a valid API.

## 5. Echo Backend to Verify Request and Response Sides

The echo backend is a **standalone Spring Boot MVC application** on port 9091. It receives requests and reflects back headers sent by the Gateway.

### 5.1. Backend Setup

Maven dependency for the backend:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 9091
~~~

`src/main/java/demo/mvcbackend/EchoBackendApplication.java`:

~~~java
package demo.mvcbackend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EchoBackendApplication {
    public static void main(String[] args) {
        SpringApplication.run(EchoBackendApplication.class, args);
    }
}
~~~

`src/main/java/demo/mvcbackend/EchoController.java`:

~~~java
package demo.mvcbackend;

import java.util.LinkedHashMap;
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EchoController {

    @GetMapping("/echo")
    public Map<String, Object> echo(HttpServletRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("source", "mvc-backend");
        result.put("path", request.getRequestURI());
        result.put("routeTag",
                request.getHeader("X-Route-Tag"));
        result.put("beforeMarker",
                request.getHeader("X-Mvc-Before"));
        result.put("clientHeader",
                request.getHeader("X-Client-Note"));
        return result;
    }
}
~~~

The backend knows nothing about Gateway's `DemoMvcFilters` or `RouterFunction`; it only sees the proxied HTTP request. Notably, **response** headers such as `X-Gateway-After` will not appear in the backend's **echo body**, because they are added on the response path after the backend finishes.

### 5.2. Running the Lab

Open two terminals in the respective project directories:

~~~bash
# Backend terminal: mvc-backend project
./mvnw spring-boot:run

# Gateway terminal: mvc-gateway project
./mvnw spring-boot:run
~~~

On Windows, run `mvnw.cmd spring-boot:run`. This document provides **hands-on self-study instructions** and does not claim a build/test was executed inside the repository.

Test the backend directly:

~~~bash
curl -i "http://127.0.0.1:9091/echo"
~~~

The backend response is expected to show `"path":"/echo"` with Gateway-added headers `null`, since the request bypassed the Gateway.

### 5.3. Sending Requests Through the Gateway

~~~bash
curl -i "http://127.0.0.1:8080/proxy/echo" \
  -H "X-Client-Note: sent-by-curl"
~~~

When routing, proxying, and filters work as intended, the body looks like:

~~~json
{
  "source": "mvc-backend",
  "path": "/echo",
  "routeTag": "mvc-route",
  "beforeMarker": "custom-before",
  "clientHeader": "sent-by-curl"
}
~~~

And response headers (actual ordering/formatting may vary):

~~~http
HTTP/1.1 200 OK
X-Gateway-After: applied
X-Mvc-After-Custom: custom-after
X-Mvc-Decision: forwarded
Content-Type: application/json
~~~

Points to observe:

| Evidence | Where observed | Producing filter/feature |
| --- | --- | --- |
| `path=/echo` | Backend echo JSON | `BeforeFilterFunctions.stripPrefix(1)` |
| `routeTag=mvc-route` | Backend echo JSON | `BeforeFilterFunctions.addRequestHeader` |
| `beforeMarker=custom-before` | Backend echo JSON | Custom `Function<ServerRequest,ServerRequest>` |
| `X-Gateway-After: applied` | HTTP response to client | `AfterFilterFunctions.addResponseHeader` |
| `X-Mvc-After-Custom` | HTTP response to client | Custom `BiFunction<ServerRequest,ServerResponse,ServerResponse>` |
| `X-Mvc-Decision` | HTTP response to client | Custom `HandlerFilterFunction` |

If the backend sees the before header yet the client misses the after header, check whether the route really uses `.after(...)`, whether the response committed early, or whether an error handler/Servlet Filter replaced it. Conversely, if the client sees response headers while the backend misses request markers, check before functions and the route path.

### 5.4. Verifying the Short-Circuit Branch

~~~bash
curl -i "http://127.0.0.1:8080/proxy/echo" \
  -H "X-Lab-Block: yes"
~~~

Per `blockLabRequest()`, the expected baseline result is:

~~~http
HTTP/1.1 403 Forbidden
X-Mvc-Decision: blocked

Blocked by the demo filter
~~~

**The backend must not receive a new request** from this command, because the filter returns a response before invoking `next.handle(request)`. As for after filters on the same builder, whether they run on a short-circuited response depends on **how filters are composed in the chain**; do not rely on the presence of `X-Gateway-After` as a universal rule across all orderings. Test against your exact version and declaration order.

To verify the backend was skipped, add a backend counter/log recording only the route ID and endpoint hit count, then compare before/after the test. Never enable raw HTTP wiretaps containing secrets in production.

### 5.5. Negative Tests for Route Predicates

~~~bash
# Route is declared as GET, not POST:
curl -i -X POST "http://127.0.0.1:8080/proxy/echo"

# Different path:
curl -i "http://127.0.0.1:8080/proxy/other"
~~~

With no other route/handler, Gateway usually returns 404/405 depending on Servlet/WebMvc.fn mappings. **Do not assume a custom filter malfunctioned** when the request never matched the predicate so the filter was never invoked.

### 5.6. Never Ship Lab Flags to Production

The `X-Lab-Block` flag only demonstrates `HandlerFilterFunction` returning early. If used for security decisions, clients can simply omit the header to bypass policy. Production must use **Spring Security on the Servlet stack**, verifying JWTs/sessions/authorization alongside backend access controls. Never accept self-asserted headers as proof of identity.

## 6. Configuring Built-in Filters via YAML Instead of Java Routes API

Built-in filters like `AddRequestHeader`, `StripPrefix`, and `AddResponseHeader` are also supported by Gateway Server MVC in external route configuration. Filter names in YAML rely on **factory/DSL discovery**, unlike calling a static Java method directly.

### 6.1. Gateway Server Web MVC 4.3.x / 5.x

`application.yml`:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: mvc-header-yaml
              uri: http://127.0.0.1:9091
              predicates:
                - Path=/proxy/echo
                - Method=GET
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Route-Tag,yaml-route
                - AddResponseHeader=X-Gateway-After,applied
~~~

With this route, `GET /proxy/echo` forwards to `http://127.0.0.1:9091/echo`. The echo backend receives `X-Route-Tag: yaml-route`, and the client receives `X-Gateway-After: applied`. `DemoMvcFilters.beforeMarker()/afterMarker()/blockLabRequest()` **are not present** in this config, because they are **custom** functions from the Java example rather than auto-discovered from method names.

**Do not define the same route ID/path simultaneously with the Java bean in Section 4** and try to infer which ran from the output. Enable **one style at a time** per test, or put routes on distinct paths and verify route IDs via logs/Actuator.

### 6.2. Gateway Server MVC 4.2.x

Older lines use `spring.cloud.gateway.mvc.routes`:

~~~yaml
spring:
  cloud:
    gateway:
      mvc:
        routes:
          - id: mvc-header-yaml
            uri: http://127.0.0.1:9091
            predicates:
              - Path=/proxy/echo
              - Method=GET
            filters:
              - StripPrefix=1
              - AddRequestHeader=X-Route-Tag,yaml-route
              - AddResponseHeader=X-Gateway-After,applied
~~~

**Do not swap namespaces by guesswork:** Gateway 4.2.x/4.3.x changed both starter names and configuration prefixes. Choose the right BOM, starter, and namespace for your release, then verify the route actually loads.

### 6.3. Java and YAML Offer Different Levels of Customization

| Need | Java Routes API | YAML route |
| --- | --- | --- |
| Built-in static before/after filters | Call `.before(addRequestHeader(...))` | Declare `AddRequestHeader=...` |
| Route ID, predicate, URI | `route("id").GET(...).before(uri(...))` | `id`/`uri`/`predicates` |
| Custom filter with application lambda | Call `.before(customFn)`, `.after(customFn)`, `.filter(customFn)` | **Requires registering discovery/supplier** to reference from YAML |
| Large payloads, retries, circuit breakers | Pick corresponding specialized filters | Pick corresponding factory/config |
| Compile-time checks | Java compiler catches contract mismatches | Binding/argument conversion can fail when loading routes |
| Runtime updates | Deploy Java code or supported route loader | Can come from Config Server/repository if supported |

### 6.4. Registering a Custom `HandlerFilterFunction` for External Configuration

Per Gateway Server MVC's **Writing Custom Predicates and Filters** documentation, using a **custom filter** in configuration files requires registering a **Supplier bean** so the filter can be discovered. `SimpleFilterSupplier` is a convenient option when static methods in a class return `HandlerFilterFunction`.

In our example, `DemoMvcFilters.blockLabRequest()` is a static method returning `HandlerFilterFunction<ServerResponse,ServerResponse>`. You can declare:

~~~java
package demo.mvcgateway;

import org.springframework.cloud.gateway.server.mvc.filter.SimpleFilterSupplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

class DemoMvcFilterSupplier extends SimpleFilterSupplier {
    DemoMvcFilterSupplier() {
        super(DemoMvcFilters.class);
    }
}

@Configuration(proxyBeanMethods = false)
class CustomFilterSupplierConfiguration {
    @Bean
    DemoMvcFilterSupplier demoMvcFilterSupplier() {
        return new DemoMvcFilterSupplier();
    }
}
~~~

`FilterDiscoverer` can then discover matching static methods. **Do not assume every static `Function`/`BiFunction` in the class becomes a configurable filter automatically**: `SimpleFilterSupplier` documentation specifies it targets methods returning `HandlerFilterFunction`. To expose custom before/after logic in YAML, wrap them with `HandlerFilterFunction` adapters or structure an appropriate supplier/factory.

Before exposing a custom filter in external configuration:

1. Check the exact filter name registered by the discoverer in your version.
2. Verify argument binding, data types, defaults, and constraints.
3. Run integration tests for YAML configs, not just unit tests on lambdas.
4. Ensure the filter is placed on the intended route and in the right order.
5. Never expose lab endpoints/flags like `X-Lab-Block` to production.

**Do not write `BlockLabRequest` in YAML assuming the framework derives that exact name** without verifying your library version's naming/discovery behavior. Spring docs also note that legacy `FilterSupplier` registration via `META-INF/spring.factories` is deprecated; prefer Spring beans as documented for current lines.

## 7. Adaptation: Why Are `before` and `after` Also Filters?

WebMvc.fn provides mechanisms to adapt the two specialized functions into a `HandlerFilterFunction`:

~~~java
HandlerFilterFunction.ofRequestProcessor(beforeFunction)
HandlerFilterFunction.ofResponseProcessor(afterFunction)
~~~

Java example:

~~~java
package demo.mvcgateway;

import org.springframework.web.servlet.function.HandlerFilterFunction;
import org.springframework.web.servlet.function.ServerResponse;

class FilterAdapters {
    static HandlerFilterFunction<ServerResponse, ServerResponse>
            asBeforeFilter() {
        return HandlerFilterFunction.ofRequestProcessor(
                DemoMvcFilters.beforeMarker());
    }

    static HandlerFilterFunction<ServerResponse, ServerResponse>
            asAfterFilter() {
        return HandlerFilterFunction.ofResponseProcessor(
                DemoMvcFilters.afterMarker());
    }
}
~~~

Thus, all three forms participate in WebMvc.fn's **`HandlerFilterFunction` chain**. Even so, **prefer `.before(...)`/`.after(...)` when appropriate**: readers immediately see whether a filter touches only the request or response, avoiding unnecessary `next` boilerplate.

### 7.1. Three Ways to Express the Same Simple Intent

Adding a header to a request:

~~~java
// Option A: WebMvc.fn before processor (preferred when only changing request)
.before(request -> ServerRequest.from(request)
        .header("X-Lab-Before", "added")
        .build())

// Option B: Gateway built-in BeforeFilterFunctions
.before(BeforeFilterFunctions.addRequestHeader(
        "X-Lab-Before", "added"))

// Option C: adapted form under HandlerFilterFunction
.filter(HandlerFilterFunction.ofRequestProcessor(
        DemoMvcFilters.beforeMarker()))
~~~

These are three **independent** variants; do not apply all three at once expecting a single header. Calling "add" multiple times can produce duplicate values.

### 7.2. When to Use `FilterFunctions` vs. `Before`/`AfterFilterFunctions`?

Gateway Server MVC provides `org.springframework.cloud.gateway.server.mvc.filter.FilterFunctions` holding `HandlerFilterFunction` equivalents adapted from before/after operations. Documentation recommends preferring **specialized `BeforeFilterFunctions` and `AfterFilterFunctions`** when possible, because they express intent more clearly.

For example, to set the backend URI before the handler runs, `BeforeFilterFunctions.uri(...)` is more natural than a general wrapper inspecting both request and response. To add a response header, `AfterFilterFunctions.addResponseHeader(...)` is easier to audit than a filter touching both request and response without reason.

### 7.3. Advanced Filters Are More Than Just "Before" or "After"

Some capabilities need control both before and after proxying, or even retrying the handler:

| MVC filter group | Common responsibilities |
| --- | --- |
| `BodyFilterFunctions` | Reads or transforms bodies; requires understanding buffering costs |
| `Bucket4jFilterFunctions` | Rate limiting with an appropriate bucket-storage policy |
| `CircuitBreakerFilterFunctions` | Wraps backend calls and returns fallbacks when needed |
| `RetryFilterFunctions` | Retries permitted errors under idempotency/replay constraints |
| `LoadBalancerFilterFunctions` | Picks downstream instances from service discovery |
| `TokenRelayFilterFunctions` | Forwards tokens per security context and policy |

Gateway docs categorize these as **Advanced Filter Functions**, not simple pre/post header edits. **Never replace retries/circuit breakers with an ad-hoc `next.handle(...)` loop**: you must account for request body preservation, connection failures, downstream state, timeouts, and side effects.

## 8. Filter Ordering and Scope in WebMvc.fn

### 8.1. Filters Apply to the Router Builder Where Declared

Per Spring Framework, `before`, `after`, and `filter` attach to a **`RouterFunctions.Builder`**. They apply to routes **within that builder**, not automatically to every controller in the Servlet application.

Structural example:

~~~text
Router A:
  GET /public/catalog
  before(add X-Catalog)   -> only routes belonging to Router A

Router B:
  GET /internal/health
  no filter above          -> does not automatically receive X-Catalog

Servlet Filter:
  runs at the Servlet filter chain level by URL/mapping/order
  can wrap Router A, Router B, and @Controller
~~~

With nested routes, filters declared on a nested builder apply to that nested group and **do not automatically apply to top-level siblings**. Spring WebMvc.fn docs show `.path("/person", nestedBuilder -> ... .before(...))` as well as a parent `.after(...)` applying to all routes in that parent builder.

### 8.2. Before and After Do Not Mean "Strict Line-by-Line Top-to-Bottom"

With multiple filters:

~~~java
.before(beforeA())
.before(beforeB())
.filter(aroundC())
.after(afterD())
~~~

The underlying model is **function composition** wrapping the inner handler. Pre-`next` logic runs in one direction, while post-`next` logic unwinds in reverse; how the builder and nested routes compose filters determines the exact sequence. Never claim that every version always runs `A → B → C → Handler → D` in strict textual order.

Verify ordering with a **per-request trace list** or an echo backend logging distinct headers. Never store per-request trace logs in a shared singleton mutable list on a bean across concurrent requests; use per-request structures or test-specific recording.

### 8.3. Route Predicates Must Match First

A route's filters have no say if the request matched a different route. If `POST /proxy/echo` arrives when only `.GET("/proxy/echo", http())` is defined, the GET route's filters do not run.

When testing, always distinguish:

- 404/405 from unmatched predicate/method.
- 403 from `HandlerFilterFunction` short-circuit.
- 502/503 from backend proxy/transport failure.
- 401/403 from Spring Security Servlet chain.
- 429 from a dedicated rate limiter.

Identical HTTP status codes can originate from **different layers**. You need route IDs, trace spans, and sanitized logs to tell them apart.

### 8.4. Servlet Filters and `HandlerFilterFunction` Have Different Scopes

| `jakarta.servlet.Filter` | WebMvc.fn `HandlerFilterFunction` |
| --- | --- |
| Invoked by Servlet container / Servlet filter chain | Runs inside a matched functional handler/route |
| Receives `ServletRequest`/`ServletResponse` and `FilterChain` | Receives `ServerRequest` and `HandlerFunction<T> next` |
| Can wrap `DispatcherServlet`, annotated controllers, and WebMvc.fn | Bound to a specific router builder |
| Suited for Servlet-layer security and cross-cutting concerns | Suited for route-specific proxy requests/responses |
| Ordered via filter registration/`Ordered` | Ordered via WebMvc.fn builder composition |

**Spring Security MVC** normally operates via the Servlet Filter chain. Never assume a custom `HandlerFilterFunction` replaces the full authentication, authorization, CSRF, and cookie policies of `SecurityFilterChain`.

### 8.5. Note on `FormFilter` for `form-urlencoded`

Gateway MVC uses a Servlet container; for `application/x-www-form-urlencoded`, the container may merge form fields with query parameters whenever anything reads request parameters. Gateway provides `FormFilter` to help reconstruct the form body for downstream calls.

**Working with Servlets and Servlet Filters** documentation warns that a **custom Servlet Filter** reading request parameters ahead of the chain may need explicit ordering relative to `FormFilter.FORM_FILTER_ORDER`. Otherwise, proxied form requests can be altered unexpectedly.

Never write a before processor that reads and parses form bodies and rebuilds them manually without checking framework rules. For large/multipart/streaming bodies, account for buffering, disk usage, request size limits, and timeouts.

## 9. Designing Error-Safe `HandlerFilterFunction` Implementations

### 9.1. Three Ways a Request Can End

A general filter can:

1. **Proceed:** call `next.handle(request)` exactly once and return the response.
2. **Reject early:** return a `ServerResponse` directly without calling `next`.
3. **Fail:** handler/transport throws an exception; the filter can let it propagate to standard error handling or handle it deliberately.

Pattern:

~~~java
return (request, next) -> {
    if (reject(request)) {
        return ServerResponse.status(403)
                .body("Not allowed");
    }
    return next.handle(request);
};
~~~

This snippet illustrates structure only and **contains no `reject(...)` implementation or real security**.

Never call `next.handle(request)` twice just to "retry briefly," because for POST/PUT/PATCH the backend may have already executed side effects on the first attempt. Retries require a dedicated mechanism with timeouts, budgets, allowed methods/statuses/exceptions, and idempotency contracts.

### 9.2. Exceptions Can Prevent After Processors from Running

A custom after function is invoked when the inner handler returns a `ServerResponse` for it to process. If the handler **throws an exception before returning a response**, you cannot assume `.after(...)` will still run and add headers to the error response.

For metrics:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> timed =
        (request, next) -> {
            long startNanos = System.nanoTime();
            try {
                return next.handle(request);
            } finally {
                long durationNanos =
                        System.nanoTime() - startNanos;
                // Record duration metric, even when next throws an exception.
            }
        };
~~~

For application-wide error standardization, use Spring MVC exception handling, Servlet error dispatches, or tested built-in mechanisms. Never catch all exceptions and turn them into `200 OK` or expose raw exception messages to clients.

### 9.3. The Response May Already Be Committed

A proxy response may begin streaming its body to the client; once headers are committed, changing status or headers may no longer be valid. Built-in `AfterFilterFunctions` are designed for proper Gateway response flows, yet custom code must still:

- Modify only headers that remain safe to change.
- Never attach a stale `Content-Length` after altering a body.
- Avoid sending conflicting duplicate CORS/cache/security headers.
- Never assume a body write can be rolled back once partially sent.
- Test behavior when the backend returns redirects, `204 No Content`, 4xx/5xx errors, or streaming responses.

If you need to **transform response bodies**, use dedicated body-filter mechanisms and understand buffering/content-encoding, rather than writing directly to the response in a simple after function.

### 9.4. Status Decisions Do Not Depend on One Filter Alone

| HTTP result | Possible origin | What to verify |
| --- | --- | --- |
| 200 | Backend or local handler | Right backend, right route ID? |
| 301/302 | Backend or redirect filter | `Location`, Host/Proto, open redirect |
| 401 | Spring Security, backend OAuth2 | Token/issuer/audience, security chain |
| 403 | Spring Security, custom short-circuit | Log decision source without leaking details |
| 404/405 | Unmatched predicate, missing handler | Method, path, route order |
| 429 | Rate limiting | KeyResolver/tenant quota, `Retry-After` |
| 502/503 | Proxy, service discovery, backend outage | URI, TLS, DNS, LB, timeouts |
| 500 | Exception in custom filter or framework | Sanitized logs/traces, input validation |

Never coerce every exception into `403` "to be safe": that hides system failures and misleads clients and monitoring.

## 10. Security: Custom MVC Filters Do Not Replace API Protection

### 10.1. Never Trust Client-Declared Identity Headers

In the lab, `X-Route-Tag` and `X-Mvc-Before` are **technical markers**. In real systems:

~~~http
X-User-Id: admin
X-Tenant-Id: enterprise
Authorization: Bearer ...
Forwarded: for=...
~~~

are all HTTP inputs requiring evaluation at the **trust boundary**. A client can send `X-User-Id`, `X-Tenant-Id`, or `X-Forwarded-For` on its own. Never use `before(request -> ...)` to treat those values as verified identity.

Your system must:

1. Validate access tokens/sessions/API keys via Spring Security on the Servlet stack (or the designated component).
2. Authorize by principal/tenant/resource from a trusted source.
3. Strip/overwrite identity headers clients are not permitted to control.
4. Protect Gateway → backend links via network policy/TLS/mTLS or an equivalent trusted mechanism.
5. Let the backend independently verify permissions on sensitive resources rather than trusting markers alone.

### 10.2. Prevent SSRF/Open Proxy on Destination URIs

`BeforeFilterFunctions.uri(...)` routes traffic upstream. A URI from trusted administrative config is safe, but if built **directly from client headers/queries**, attackers can target:

~~~text
http://127.0.0.1:...
http://169.254.169.254/...
http://internal-admin-service/...
~~~

That is an SSRF/open-proxy vulnerability. For dynamic routes, enforce scheme/host/port allowlists, check DNS resolution/redirects, and restrict route update permissions rather than letting a custom before filter proxy arbitrary client-specified targets.

### 10.3. After Filters and Security Response Headers

When setting `Content-Security-Policy`, `Strict-Transport-Security`, `Access-Control-Allow-Origin`, or `Cache-Control`, know **which layer sets the header** (backend, Gateway MVC, public Ingress). Two layers both calling `add` on the same header does not mean browsers interpret it as intended; CORS credentials and HSTS especially demand consistent configuration.

Never add `Access-Control-Allow-Origin: *` for credentialed requests assuming the issue is solved. CORS is a browser rule, **not authentication or CSRF protection**.

### 10.4. CSRF, Cookies, and the Servlet Stack

If Gateway MVC uses session-cookie authentication, browsers attach cookies automatically. Analyze **CSRF** for POST/PUT/PATCH/DELETE in Spring Security Servlet stack alongside `SameSite`/`Secure`/`HttpOnly` and HTTPS. A custom `HandlerFilterFunction` processing route requests/responses **does not itself provide full session-fixation protection, CSRF token repositories, or authorization rules**.

### 10.5. Sensitive Data in Logs

Never log raw `Authorization`, session cookies, request bodies containing personal data, refresh tokens, payment details, or full proxy URIs with credentials. If a filter needs a correlation ID, generate a safe ID, normalize client-sent headers, and bound length/charset. Metric labels should hold only low-cardinality fields like route ID/status/error category—never individual user IDs or tokens.

## 11. Performance: Servlet Threads, Bodies, and Retries

### 11.1. Web MVC Is Not Reactor Netty

Server MVC runs on a **Servlet runtime** (Tomcat/Jetty as configured), unlike WebFlux's reactive architecture. A `HandlerFilterFunction` takes and returns `ServerRequest`/`ServerResponse` directly. Placing slow HTTP/DB calls or `Thread.sleep(...)` inside a filter can hold Servlet request threads for long periods, causing queueing and dropping throughput.

Perform only strictly necessary I/O in filters, enforce timeouts and concurrency limits, and keep rate limiting/circuit breakers/retries controlled. Never copy WebFlux `Mono.defer()/flatMap()` into MVC filters expecting identical contracts.

### 11.2. Bodies Are Not Free Just Because You Used a Before Function

A before function should normally only alter paths/headers/URIs. Reading the body for HMAC signing, JSON transformation, or debugging introduces costs:

- Body streams may be readable only once without proper wrappers/caching.
- Materializing `byte[]`/`String` holds entire payloads on the heap, spiking memory under concurrency.
- Multipart/form-urlencoded adds parsing overhead, temporary files, and `FormFilter` interactions.
- `Content-Length`, `Content-Type`, charset, and compression must stay consistent after transformation.
- Retrying large bodies holds them longer and amplifies memory usage.

Prefer **`BodyFilterFunctions`** or version-appropriate official filters, enforce payload limits at ingress/server, and test chunked bodies, file uploads, UTF-8, empty bodies, and client disconnects.

### 11.3. Retries Repeat Calls and Can Repeat Side Effects

A `HandlerFilterFunction` wrapping `next` may sit outside or inside a Retry filter depending on chain composition. When one client request triggers three backend attempts, distinguish:

- **logical client request count**;
- **downstream attempt count**;
- which filters run once vs. per attempt;
- whether the body is replayable;
- whether the backend enforces idempotency keys/transactions against duplicates.

Never trigger charges, emails, or business state changes inside a route filter without proper exactly-once/idempotency guarantees. Circuit breakers must also be ordered deliberately: whether a breaker tracks overall logical requests or individual attempts changes failure metrics.

### 11.4. Service Discovery and Path Modification Order

When using `lb://service-id` or `LoadBalancerFilterFunctions`, the order of URL rewrite/`StripPrefix` relative to instance resolution matters. Gateway MVC's `StripPrefix` docs emphasize that with `lb()`, it should be placed **after `stripPrefix()`** to avoid malformed final URLs; config-based `lb:` handlers can apply ordering priorities of their own.

Do not infer from `uri("http://127.0.0.1:9091")` that changing it to `uri("lb://orders-service")` works identically in every release. Verify load-balancing dependencies, service registry, URL attributes, and related filters in your exact Gateway MVC version.

## 12. Troubleshooting and Root-Cause Isolation

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| Java build cannot find `HandlerFilterFunction` | Imported WebFlux by mistake, missing Spring MVC starter | Use `org.springframework.web.servlet.function.*` |
| Cannot find `BeforeFilterFunctions` | Wrong starter or mixing Gateway 4.2 with 5.x prefixes/docs | Check `spring-cloud-starter-gateway-server-webmvc` or matching legacy starter |
| Route is not selected | GET/path predicate mismatch, another route has higher priority | Send matching method/path, inspect route IDs |
| 404 through Gateway, 200 directly at backend | Wrong `stripPrefix`/uri path | Echo `getRequestURI()` at backend |
| Request header never reaches backend | Before function didn't run, wrong route, proxy stripped header | Compare backend echo response and route selection |
| Response lacks after header | After filter missing, handler threw before returning, response committed | Test 200 case and error case separately |
| Header has two values | Called `add` repeatedly, or client already sent header | Check set/replace policy |
| Lab flag returns 403 yet backend logs a hit | Different/concurrent request, filter chain assembled differently than intended | Correlation ID/trace, count requests with same ID |
| Backend does not receive `/echo` | Wrong `StripPrefix` segment count or misunderstood route URI path | Inspect actual downstream URL, test raw path |
| YAML route config has no effect | Wrong MVC 4.2 vs. 4.3+/5.x namespace | Check configuration properties / startup logs |
| Custom Java filter runs, YAML cannot find it | Missing `FilterSupplier` bean / discovery | Test registration/naming/binding |
| Wrong response status on backend failure | Exception vs. status handling, Retry/CircuitBreaker behavior | Trace root cause layer by layer |
| Throughput drops sharply after adding filter | Blocking I/O, reading large bodies, heavy serialization/logging | Check thread pools, p95/p99 latency, heap |
| POST form body missing data | Servlet Filter reading parameters or `FormFilter` order | Check filter registration and `FormFilter` |
| Security filter "skips" new route | Route filter is not the Servlet/Spring Security chain | Inspect `SecurityFilterChain`/URL matchers |
| Browser hits CORS errors | Preflight misses route/security, duplicate headers | Check `OPTIONS`, origins, credentials |

### 12.1. Layer-by-Layer Testing

1. **Backend directly:** `GET http://127.0.0.1:9091/echo` must work.
2. **Gateway route:** `GET http://127.0.0.1:8080/proxy/echo` must match.
3. **Before markers:** backend sees expected path and headers.
4. **After markers:** client sees expected response headers.
5. **Handler short-circuit:** request with `X-Lab-Block: yes` never calls backend.
6. **Method mismatch:** POST does not slip into a GET-only route.
7. **Security/proxy behavior:** test requests with and without credentials against real policies, never lab flags.
8. **Performance:** measure p95/p99, thread utilization, and memory as concurrency rises.

During debugging, never disable TLS, rate limiting, or auth, or open Actuator write access just "to make the lab pass." Isolating the test environment lets you pinpoint causes without weakening production.

## 13. Extended Practice Exercises

### Exercise 1 — Replace `add` with `set`

Update the marker policy so that even when a client sends `X-Route-Tag: client-value`, the backend sees only **one** Gateway-generated value. Pick an appropriate built-in such as `setRequestHeader` (if supported in your version), write a duplicate-header test, and explain why `add` is unsafe for identity headers.

### Exercise 2 — Combining Pre- and Post-Handler Logic for Latency

Write a `HandlerFilterFunction` that records start time, calls `next.handle(request)` once, and records a **latency histogram** by route/status. Ensure `finally` records latency even if the handler throws an exception. Never include request IDs or user IDs in metric labels.

### Exercise 3 — Independent Short-Circuit Verification

Add a backend endpoint counter for the lab. Send 10 normal requests and 10 requests with `X-Lab-Block: yes`. Verify the backend count rises only for unblocked requests; compare statuses/headers and note whether after processors run on short-circuited responses in your chosen filter structure.

### Exercise 4 — Comparing Java DSL and YAML

Run the same header logic on two routes with **different paths/route IDs**: one via Java API and one via built-in YAML. Compare before and after headers. Explain why custom Java methods do not automatically become named filters in external configuration without a filter supplier.

### Exercise 5 — 502 Errors and Retries

Configure the backend to return 502 on the first attempt and 200 on the next. Enable Gateway MVC's dedicated Retry for **GET** with a bounded budget, then observe backend attempts, final response, and latency. Explain why an idempotency contract is mandatory before applying the same idea to order-creation POSTs.

## 14. Checklist for Shipping Custom MVC Filters to Production

- [ ] Project genuinely uses **Gateway Server Web MVC**, with no WebFlux API mixup.
- [ ] Starter and Spring Cloud BOM match the 4.2, 4.3, or 5.x line; YAML namespace matches version.
- [ ] Java proxies use `HandlerFunctions.http()` paired with `BeforeFilterFunctions.uri()`.
- [ ] When modifying requests only, prefer `.before(...)`; when modifying responses only, prefer `.after(...)`.
- [ ] Use `.filter(...)` when wrapping the handler or intentionally short-circuiting.
- [ ] Call `next.handle(request)` the right number of times; never retry non-idempotent requests blindly.
- [ ] Scope of router builders/nested routes and composition order are understood.
- [ ] Tests cover route matching, Before headers/paths, After headers, and `HandlerFilterFunction` short-circuiting.
- [ ] Client-supplied markers/headers are never treated as authentication or access proof.
- [ ] Servlet Security Filter chain, CSRF, cookies, and OAuth2/JWT are configured independently.
- [ ] Destination URIs are constrained to prevent SSRF/open proxy.
- [ ] Sensitive headers like `Authorization`, `Host`, CORS, HSTS, and `Content-Length` are not accidentally duplicated.
- [ ] Timeouts/concurrency limits exist; blocking calls and large body buffering are avoided in filters.
- [ ] For `form-urlencoded`/multipart, Servlet Filter and `FormFilter` ordering are verified.
- [ ] Retry/CircuitBreaker/LoadBalancer ordering and failure policies are explicit, with metrics separating attempts.
- [ ] Raw tokens/cookies/sensitive bodies and high-cardinality metric labels are never logged/emitted.
- [ ] When custom filters are used in YAML, suppliers are registered and names/args/binding are tested.
- [ ] Smoke tests run before/after Gateway upgrades, especially migrating from 4.2 to 4.3+/5.x.

## 15. Knowledge Self-Check

**1. Why does `BeforeFilterFunctions` use `Function<ServerRequest, ServerRequest>`?**

Because it transforms the request **before the handler runs**, without needing a response or calling the handler itself. The result is a new or transformed request per the contract.

**2. Can `AfterFilterFunctions` stop the handler from running?**

Not under the normal after-processor contract: it operates on the request and the **already created** response. To short-circuit before reaching the backend, use a `HandlerFilterFunction` (or appropriate security/rate-limiting policy).

**3. What is the core difference between `HandlerFilterFunction` and before/after?**

It receives `HandlerFunction<T> next`, decides whether to invoke `next`, and can run logic both before and after `next`; this adds flexibility while requiring careful control over errors, side effects, and ordering.

**4. Why doesn't Gateway MVC use WebFlux-style `GatewayFilterFactory<Config>` for Java routes?**

Because Web MVC builds on WebMvc.fn/Servlet with `ServerRequest`/`ServerResponse`/`HandlerFilterFunction`, whereas WebFlux uses `ServerWebExchange`/`Mono<Void>`/`GatewayFilter` and reactive routing.

**5. Why doesn't the backend see `X-Gateway-After` in the echo request?**

Because after filters add headers to the **response returning to the client**, not the request sent to the backend. To make a header visible to the backend, use a before filter.

**6. Is a custom static method returning `HandlerFilterFunction` automatically referenceable from YAML?**

Not by default. Gateway docs require registering a **`FilterSupplier`/`SimpleFilterSupplier`** so the framework discovers custom filters for external configuration.

**7. Can one `HandlerFilterFunction` attached to one route apply to all requests, including annotated controllers?**

No. Filters attached to a `RouterFunction` builder are **scoped to routes in that builder**, whereas Servlet Filters/Spring Security chains operate at a broader mapping layer.

**8. Why should `stripPrefix()` be checked together with `lb()`?**

Because constructing the backend URL depends on the transformed path and the order of service instance resolution. If the load-balancer filter runs before the URL/path is in the intended state, the backend may receive the wrong URI.

## 16. Official Documentation

1. [Spring Cloud Gateway Server Web MVC — Gateway Handler Filter Functions](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/gateway-handler-filter-functions.html): before/after contract, placement of `BeforeFilterFunctions`, `AfterFilterFunctions`, `FilterFunctions`, and advanced filters.
2. [Gateway Server MVC — Writing Custom Predicates and Filters](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/writing-custom-predicates-and-filters.html): Java examples using `Function`, `BiFunction`, `HandlerFilterFunction`, and `FilterSupplier`.
3. [Gateway Server Web MVC — Java Routes API](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/java-routes-api.html): `RouterFunctions.Builder`, `GatewayRouterFunctions.route(...)`, `HandlerFunctions.http()`, and `BeforeFilterFunctions.uri()`.
4. [Gateway Server Web MVC — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/how-it-works.html): `RouterFunction` structure, HTTP handlers, and filters.
5. [Gateway Server Web MVC — AddRequestHeader](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/filters/addrequestheader.html): built-in request header function/YAML.
6. [Gateway Server Web MVC — AddResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/filters/addresponseheader.html): built-in after function/YAML.
7. [Gateway Server Web MVC — StripPrefix](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/filters/stripprefix.html): path rewriting and ordering warning with `lb()`.
8. [Spring Framework — WebMvc.fn Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webmvc-functional.html): `RouterFunction`, `HandlerFunction`, `ServerRequest`/`ServerResponse`, `before`/`after`/`filter`, and nested scope.
9. [Gateway Server Web MVC — Working with Servlets and Servlet Filters](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/working-with-servlets-and-filters.html): Servlet Filter ordering and `FormFilter`.
10. [Gateway Server MVC 4.2 — Starter](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway-server-mvc/starter.html): 4.2 starter name and Servlet architecture.
11. [Gateway Server Web MVC 4.3 — Starter](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webmvc/starter.html): 4.3 starter name and enabling/disabling MVC gateway.

**Takeaway:** In **Spring Cloud Gateway Server Web MVC**, `BeforeFilterFunctions` processes the **request before the handler**, `AfterFilterFunctions` processes the **response after the handler**, and `HandlerFilterFunction` **wraps the handler** with control over calling or skipping `next.handle(request)`. All three build on **WebMvc.fn/Servlet**, not WebFlux's reactive `GatewayFilter`. Pick the simplest tool for the job, verify with live requests/responses, guard filters against untrusted input, and validate ordering, error handling, retries, memory, and security before shipping routes to production.
