# Limitations of Applying Gateway Server Route and Filter Configurations

## 1. The Problem: Having ProxyExchange Yet Retry and RewritePath Configurations Do Not Run

In **SPRING_CLOUD_GATEWAY**, we typically build an API Gateway with route predicates, filter chains, path/header transformations, service discovery, authentication, rate limiting, circuit breakers, retries, TLS, and request observability. Those capabilities are thoroughly covered in the **Spring Cloud Gateway Server** documentation. However, Spring Cloud Gateway also offers another style: **Proxy Exchange**.

Consider a controller:

~~~java
@GetMapping("/edge/items/{id}")
public ResponseEntity<?> read(
        @PathVariable long id,
        ProxyExchange<byte[]> proxy) throws Exception {
    return proxy.uri("http://127.0.0.1:9091/items/" + id).get();
}
~~~

Suppose a developer adds:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          default-filters:
            - AddResponseHeader=X-Server-Filter,applied
          routes:
            - id: catalog
              uri: http://127.0.0.1:9091
              predicates:
                - Path=/edge/items/**
              filters:
                - RewritePath=/edge/items/(?<id>.*), /items/\${id}
                - name: Retry
                  args:
                    retries: 2
                    statuses:
                      - BAD_GATEWAY
~~~

Then they expect the `ProxyExchange` controller to automatically add headers, rewrite paths, and retry according to this filter list. **That is a false assumption about the boundary between the two products.**

The official Spring Cloud Gateway documentation explicitly states regarding **Proxy Exchange**: it is an alternative Gateway style, and **Gateway Server documentation does not apply to this style**. Specifically, an annotated controller using `ProxyExchange` **does not automatically become a Gateway Server `RouteDefinition`**, nor does it pass through `GatewayFilterFactory` or `HandlerFilterFunction` components simply because they are declared in Gateway Server routes.

This lesson belongs to the **Proxy Exchange** chapter, covering **“Limitations of Applying Gateway Server Route and Filter Configurations”**. The goal is not to criticize ProxyExchange as lacking capability, but to understand **its execution path, configuration scope, and self-implementation responsibilities** so you do not ship an entry point you think is protected when its filters are actually absent.

> **Early conclusion:** ProxyExchange fits when you need selective proxying directly inside a **`@Controller` / `@RestController`**. If you need an API gateway with hundreds of routes, standardized per-route policy filters, route refresh, discovery, and an actuator route inventory, **Gateway Server** is usually a better fit.

## 2. Two Flavors, Each With Two Web Stacks

Spring Cloud Gateway distinguishes two **flavors**:

1. **Gateway Server**: full-featured API Gateway handling routing/filtering via route configs or the Server Java Routes API.
2. **Proxy Exchange**: the `ProxyExchange` utility library injected into **annotated web handlers**, enabling controllers to perform downstream HTTP exchanges.

Each flavor can use **Web MVC** or **WebFlux**. Do not confuse:

- `Gateway Server Web MVC` vs. `Proxy Exchange Web MVC` — **same Servlet stack**, different route/filter types.
- `Gateway Server WebFlux` vs. `Proxy Exchange WebFlux` — **same reactive stack**, different `RouteDefinition`/`GatewayFilter` machinery.

| Option | Entry Point | Primary Routing | Specific Filters |
| --- | --- | --- | --- |
| Server WebFlux | `RoutePredicateHandlerMapping` and `RouteLocator` | `RouteDefinition`, predicate factories, Java routes | `GatewayFilter`, `GatewayFilterFactory`, `GlobalFilter` |
| Server Web MVC | WebMvc.fn `RouterFunction` with HTTP forwarding handler | Java Routes API or Gateway Server MVC YAML routes | `BeforeFilterFunctions`, `AfterFilterFunctions`, `HandlerFilterFunction` |
| Proxy Exchange WebFlux | `@GetMapping/@PostMapping` controller | Spring WebFlux annotated handler mapping + controller code | Spring WebFlux `WebFilter`/security, controller logic, `ProxyExchange` API |
| Proxy Exchange Web MVC | `@GetMapping/@PostMapping` controller | Spring MVC annotated handler mapping + controller code | Servlet `Filter`, Spring MVC interceptors/security, `ProxyExchange` API |

### 2.1. Path Diagram for the Same Public URI

~~~mermaid
flowchart TB
    C["Client GET /edge/items/42"]
    C --> D{"Chosen architecture?"}
    D -->|"Gateway Server WebFlux"| S1["RoutePredicateHandlerMapping"]
    S1 --> S2["RouteDefinition + Server GatewayFilter chain"]
    S2 --> P1["HTTP routing filter → backend"]
    D -->|"ProxyExchange WebFlux"| W1["Annotated @GetMapping handler"]
    W1 --> W2["ProxyExchange.uri(...).get()"]
    W2 --> P2["HTTP client → backend"]
    D -->|"ProxyExchange Web MVC"| M1["DispatcherServlet / @GetMapping"]
    M1 --> M2["ProxyExchange.uri(...).get()"]
    M2 --> P3["HTTP client → backend"]
~~~

The diagram illustrates three paths; it **does not** mean one application cannot contain multiple handler types simultaneously. When mixing modules, handler selection depends on separate HandlerMappings/route predicates; always verify **which handler actually served the request**.

### 2.2. What Can Still Be Reused?

Both flavors still build on Spring Boot, Spring Framework, and matching Spring Security/Micrometer/Spring Cloud libraries. For example:

- **Spring Security** can protect requests before reaching the controller.
- **Bean Validation** can validate controller paths/queries/bodies.
- **Micrometer/Observation** can record metrics and tracing.
- **Spring Cloud LoadBalancer or Resilience4j** can be used **when integrated explicitly**, rather than automatically inheriting all Server GatewayFilters.
- **TLS, timeouts, and HTTP client pooling** can still be configured at the appropriate HTTP client/infrastructure layer.

Crucially: **sharing the Spring ecosystem does not mean sharing Gateway Server's route/filter pipeline**.

## 3. Feature Map: Automatic or Must Be Written Separately?

| Required Feature | Gateway Server (Right Route/Filter) | Plain Annotated ProxyExchange |
| --- | --- | --- |
| Match path, method, header | Route predicate factories | `@GetMapping`/`@RequestMapping`, Spring MVC/WebFlux mapping |
| Define ID, URI, predicates, filters in Gateway routes YAML | Supported | **Does not auto-bind to controllers** |
| `RewritePath`, `StripPrefix`, `SetPath` | Per-route Gateway filters | Build/transform destination URI yourself in controller |
| `AddRequestHeader`/`AddResponseHeader` factories | Per route filter chain | Use ProxyExchange header API, `ResponseEntity` mapper, or Spring web layer |
| `RequestRateLimiter` + `KeyResolver` | Server WebFlux GatewayFilterFactory | Not enabled automatically; integrate limiter/security/quota policy yourself |
| `CircuitBreaker` and Retry GatewayFilter | Per Server route with matching config | Does not run automatically; apply resilience explicitly to downstream calls |
| Server `TokenRelay`/auth filters | Uses proper Server config and dependencies | Must authenticate and propagate credentials intentionally |
| `lb://service-id` and discovery route locator | Server Gateway integration | Does not apply route discovery to annotated controllers automatically |
| `Default-filters` for Server routes | Applies to Server routes per namespace/version | **Not a global filter for all controllers** |
| `RefreshRoutesEvent`, route definition repository | Refreshes Server route cache | Does not alter `@GetMapping` or destination code |
| `/actuator/gateway/routes` | Inspects Server routes when Actuator is enabled | Not a complete catalog of annotated `ProxyExchange` mappings |
| Servlet Filter / WebFlux WebFilter | Per web stack, independent of route filters | **Can still** apply to controllers |
| Spring Security on web stack | Can protect Gateway | Can protect ProxyExchange like any regular handler |

This is a **default scope map**, not a claim that these things are impossible with ProxyExchange. You can **write custom code/configuration** to achieve equivalent behavior. When doing so, verify the implementation, ordering, error behavior, and observability—do not set a Server property and expect magic.

### 3.1. Initial Diagnostic Tip

Ask one question before debugging:

> “Is this request handled by a Gateway Server `Route`, or by a `@RestController` accepting `ProxyExchange`?”

If it is the latter, do not start by tweaking `spring.cloud.gateway.server.webflux.routes[...].filters` to fix a controller issue. Look at **the controller mapping, the code calling `proxy.uri(...).get()`, the HTTP client, and the Spring filters/interceptors protecting the handler**.

## 4. Dependencies and Namespaces: Avoiding Installing the Wrong Gateway Flavor

### 4.1. Proxy Exchange MVC / WebFlux

Per Gateway 4.3/5.x documentation, the two artifacts:

~~~xml
<!-- For annotated Spring MVC controllers (Servlet) -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-gateway-proxyexchange-webmvc</artifactId>
</dependency>
~~~

~~~xml
<!-- For annotated Spring WebFlux controllers (reactive) -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-gateway-proxyexchange-webflux</artifactId>
</dependency>
~~~

A real project adds only **one** artifact matching its web stack, alongside the Spring Boot web starter, managing versions via a compatible **Spring Cloud BOM**. Do not add a Server starter as a prerequisite for obtaining `ProxyExchange`.

### 4.2. Old and New Artifact Names

Starting with the Spring Cloud 2025.0 release train, modules were renamed to clearly separate flavor and web stack:

| Goal | Old Name | Newly Published Name |
| --- | --- | --- |
| MVC Proxy Exchange | `spring-cloud-gateway-mvc` | `spring-cloud-gateway-proxyexchange-webmvc` |
| WebFlux Proxy Exchange | `spring-cloud-gateway-webflux` | `spring-cloud-gateway-proxyexchange-webflux` |
| MVC Gateway Server | `spring-cloud-starter-gateway-mvc` | `spring-cloud-starter-gateway-server-webmvc` |
| WebFlux Gateway Server | `spring-cloud-starter-gateway` | `spring-cloud-starter-gateway-server-webflux` |

Old names are deprecated per release notes; do not assume they are **four products sharing one filter pipeline**. Projects on Gateway 4.2.x may use legacy modules/prefixes; verify the exact BOM and deployment line, and never randomly mix 4.2 code with 5.x properties.

### 4.3. Proxy Exchange Configuration Prefixes Have Their Own Namespace

Spring Cloud 2025.0 release notes distinguish:

~~~properties
# Legacy prefix formerly used for ProxyExchange:
spring.cloud.gateway.proxy.*

# New prefixes separated by web stack:
spring.cloud.gateway.proxy-exchange.webmvc.*
spring.cloud.gateway.proxy-exchange.webflux.*
~~~

This is the **Proxy Exchange property group** (such as per-version header policies), **not** the namespace for Gateway Server routes or default-filters. When relying on a specific property, inspect the configuration metadata for your **running artifact/version**.

Conversely, modern route properties for Gateway Server WebFlux live under `spring.cloud.gateway.server.webflux.routes`, and Gateway Server Web MVC under `spring.cloud.gateway.server.webmvc.routes`; earlier releases used shorter prefixes such as `spring.cloud.gateway.routes` and `spring.cloud.gateway.mvc.routes`, respectively.

## 5. Anti-Pattern: Server Config Mistaken for Protecting ProxyExchange

Suppose an app has only **Proxy Exchange Web MVC**, with controller:

~~~java
@GetMapping("/edge/items/{id}")
public ResponseEntity<?> read(
        @PathVariable long id,
        ProxyExchange<byte[]> proxy) throws Exception {
    return proxy.uri("http://127.0.0.1:9091/items/" + id).get();
}
~~~

Someone adds configuration:

~~~yaml
# NOT how to enable Server GatewayFilters for the controller above
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-server
              uri: http://127.0.0.1:9091
              predicates:
                - Path=/edge/items/**
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Expected-Server-Filter,true
                - AddResponseHeader=X-Policy-From-Server,true
                - name: Retry
                  args:
                    retries: 2
~~~

If only Proxy Exchange MVC is installed (without Gateway Server MVC route machinery), **this Server route config creates no filter chain around `@GetMapping`**. Spring's binder may ignore properties without matching auto-configuration or behave differently depending on classpath/version; do not assume YAML will necessarily fail startup.

If **the same app also installs Gateway Server MVC**, that config may create a **separate Server route**. In that case:

- Requests matching the Server route may run through Server filters **owned by the Server route**.
- Requests entering the annotated ProxyExchange controller remain an **independent handler path**; `@GetMapping` never automatically inherits `StripPrefix`/`Retry` from the Server list.
- If a Server route and a controller **match the same URL**, HandlerMapping conflicts or precedence issues can arise. Verify which handler actually runs before concluding a filter took effect.

**Do not test “config does not apply” using two overlapping-path routes** while checking only HTTP 200. Use distinct paths, or disable the Server route completely while testing ProxyExchange to see the exact scope.

### 5.1. Why Are default-filters Not Global Filters for Controllers Either?

The property:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          default-filters:
            - AddResponseHeader=X-From-Server,yes
~~~

means “apply filters to **Gateway Server WebFlux routes** via Server machinery”, **not** “add headers to every HTTP endpoint served by Spring Boot”. A `ProxyExchange WebFlux` controller does not become a Server Route merely because both use WebFlux.

If you want a **global** policy across annotated handlers, use a `WebFilter` (WebFlux) or `Servlet Filter` (MVC) with explicit scope and order, or a Security chain. Those are **Spring web stack filters**, not `Gateway Server default-filters`.

## 6. MVC Lab: An Annotated Controller Deciding the Destination Itself

Let's stand up two separate apps in a lab environment:

| Application | Port | Role |
| --- | ---: | --- |
| Proxy Exchange MVC | 8080 | Holds `@GetMapping` accepting `ProxyExchange<byte[]>` |
| Catalog backend | 9091 | Receives `GET /items/{id}` and returns JSON echo |

This lab **does not add the Gateway Server starter** and creates no `RouteDefinition`. The goal is to observe routing logic coming directly from **annotations + controller code**.

### 6.1. Dependencies

With Spring Boot 3.x and a matching Spring Cloud BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-gateway-proxyexchange-webmvc</artifactId>
    </dependency>
</dependencies>
~~~

Do not pin a separate version on the Spring Cloud library when managed by the BOM. With Spring Boot 4.x, the web starter name may differ, so pick the Spring MVC/Servlet dependency per the BOM and Boot documentation.

### 6.2. application.yml

~~~yaml
server:
  port: 8080

spring:
  application:
    name: proxyexchange-mvc-lab

demo:
  proxy:
    backend-base-url: http://127.0.0.1:9091
~~~

`demo.proxy.backend-base-url` is a **custom property for this lab**, not `spring.cloud.gateway.server.webmvc.routes[0].uri`. Projects can bind properties with `@ConfigurationProperties` or `@Value`. The destination is centrally configured and fixed in the controller; never take URLs from client queries or headers.

### 6.3. Spring Boot Application and Controller

`src/main/java/demo/proxymvc/ProxyMvcApplication.java`:

~~~java
package demo.proxymvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProxyMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProxyMvcApplication.class, args);
    }
}
~~~

`src/main/java/demo/proxymvc/CatalogProxyController.java`:

~~~java
package demo.proxymvc;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class CatalogProxyController {

    private final String backendBaseUrl;

    public CatalogProxyController(
            @Value("${demo.proxy.backend-base-url}") String baseUrl) {
        this.backendBaseUrl = baseUrl.replaceAll("/+$", "");
    }

    @GetMapping("/edge/items/{id}")
    public ResponseEntity<?> read(
            @PathVariable long id,
            ProxyExchange<byte[]> proxy) throws Exception {

        if (id < 1 || id > 1000000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid item id");
        }

        String upstreamUri = backendBaseUrl + "/items/" + id;

        return proxy
                .uri(upstreamUri)
                .header("X-Proxy-Lab", "mvc-controller")
                .get();
    }
}
~~~

In the code above:

1. `@GetMapping` is a **Spring MVC annotated mapping**, not a Gateway Server `Path` predicate.
2. Spring Cloud Gateway Proxy Exchange's argument resolver creates/injects `ProxyExchange<byte[]>` for the handler method.
3. The controller builds the **upstream URI** itself and calls `proxy.uri(...).get()`. Neither `NettyRoutingFilter` nor `RouteDefinitionRouteLocator` is needed.
4. `proxy.header("X-Proxy-Lab", "...")` sets a header on the **downstream call** via ProxyExchange's Java API. It is not `AddRequestHeaderGatewayFilterFactory`.
5. The controller validates `id` as a number within a valid range to avoid concatenating arbitrary client paths. For free-form multi-segment paths, handle encoding and path traversal carefully.
6. Generic `byte[]` is the body representation for the downstream response; do not assume every endpoint is suitable for buffering huge bodies in RAM.

**API note:** package `org.springframework.cloud.gateway.mvc.ProxyExchange` is used in published MVC API lines. The new `proxyexchange-webmvc` artifact name does not mean every Java class moves to a `server.mvc` package. When upgrading versions, verify imports against the actual artifact/Javadoc.

### 6.4. Why Does the Example Intentionally Omit Retry and CircuitBreaker?

We want to verify the minimal structure. If the backend fails, this controller **has no Retry/CircuitBreaker policy configured**, even if another project in the organization applies Retry on a Server route. Adding a Server filter list to YAML does not turn `proxy.get()` into calls with a retry budget.

To add resilience, design it **outside or around the controller's downstream call** using stack-appropriate libraries/methods, with tests for timeouts, failure policies, and idempotency. Never write an infinite loop around `proxy.get()` just because you previously used Server's `Retry` filter.

## 7. WebFlux Lab: Same Idea, Reactive Return Type

If the application is Spring WebFlux/Reactive and wants to use **Proxy Exchange WebFlux**, dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-gateway-proxyexchange-webflux</artifactId>
    </dependency>
</dependencies>
~~~

Backend URL configuration matches Section 6.2. However, **the WebFlux controller does not return `ResponseEntity<?>` directly**; it returns `Mono<ResponseEntity<?>>` per the official example:

~~~java
package demo.proxyflux;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.webflux.ProxyExchange;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveCatalogProxyController {

    private final String backendBaseUrl;

    public ReactiveCatalogProxyController(
            @Value("${demo.proxy.backend-base-url}") String baseUrl) {
        this.backendBaseUrl = baseUrl.replaceAll("/+$", "");
    }

    @GetMapping("/edge/items/{id}")
    public Mono<ResponseEntity<?>> read(
            @PathVariable long id,
            ProxyExchange<byte[]> proxy) {

        if (id < 1 || id > 1000000) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid item id"));
        }

        return proxy
                .uri(backendBaseUrl + "/items/" + id)
                .header("X-Proxy-Lab", "webflux-controller")
                .get();
    }
}
~~~

This is a **separate alternative** to Web MVC; never run both controllers on the same path in one application to “auto-compare”. A WebFlux project must not accidentally boot Servlet Spring MVC by having both web starters present.

### 7.1. WebFlux ProxyExchange Is Not ServerWebExchange Gateway

`ProxyExchange` injected into an annotated controller is a helper for making downstream calls; it does not turn the callback into:

~~~java
GatewayFilter filter(ServerWebExchange exchange,
                     GatewayFilterChain chain)
~~~

Therefore:

- **Gateway Server WebFlux** `GlobalFilter`s do not run around annotated controllers by default.
- `RoutePredicateHandlerMapping` does not generate a route ID for this handler.
- `spring.cloud.gateway.server.webflux.default-filters` is not automatically applied to `Mono<ResponseEntity<?>>`.
- A standard `WebFilter` on the WebFlux web stack can protect the annotated handler **just like any other WebFlux handler**.

`Mono` does not imply automatic retries either: retry semantics exist only when code uses reactive operators or a controlled resilience library. For HTTP calls with side effects, analyze replay safety and duplicates.

### 7.2. MVC and WebFlux Differ in Threading but Share Configuration Limits

| Detail | ProxyExchange MVC | ProxyExchange WebFlux |
| --- | --- | --- |
| Handler | Annotated Spring MVC | Annotated Spring WebFlux |
| Common return type | `ResponseEntity<?>` | `Mono<ResponseEntity<?>>` |
| HTTP client | HTTP tech per MVC/Boot version, typically blocking | Reactive client per WebFlux version |
| Security filter | Servlet/Spring Security filter chain | WebFlux `SecurityWebFilterChain` |
| Controller binding | `@PathVariable`, `@RequestHeader`, `@RequestParam` | Same WebFlux annotation style |
| Server route/filter config auto-applied? | No | No |

Never call `block()` on the WebFlux event loop to turn `Mono<ResponseEntity<?>>` into `ResponseEntity<?>`. If you need a large streaming HTTP proxy, evaluate memory, backpressure, timeouts, and response semantics separately rather than defaulting to `ProxyExchange<byte[]>`.

## 8. Standalone Echo Backend to Observe What Actually Arrives

We create a small Spring Boot MVC backend on port 9091 to inspect real requests. The backend needs no knowledge of Gateway Server or ProxyExchange.

### 8.1. Configuration and Application

Backend dependency matching your Spring Boot MVC version; for example, Spring Boot 3.x:

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

spring:
  application:
    name: catalog-backend-proxyexchange-lab
~~~

`src/main/java/demo/catalog/CatalogApplication.java`:

~~~java
package demo.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### 8.2. Backend Controller

`src/main/java/demo/catalog/CatalogController.java`:

~~~java
package demo.catalog;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {

    private final AtomicLong totalCalls = new AtomicLong();

    @GetMapping("/items/{id}")
    public ResponseEntity<Map<String, Object>> read(
            @PathVariable long id,
            HttpServletRequest request) {

        long attempt = totalCalls.incrementAndGet();

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("backend", "catalog-backend");
        body.put("id", id);
        body.put("path", request.getRequestURI());
        body.put("proxyMarker",
                request.getHeader("X-Proxy-Lab"));
        body.put("hasAuthorization",
                request.getHeader("Authorization") != null);
        body.put("hasCookie",
                request.getHeader("Cookie") != null);
        body.put("backendCallsSinceStart", attempt);

        if (id == 503) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .header("X-Backend-State", "temporary-error")
                    .body(body);
        }

        return ResponseEntity.ok()
                .header("X-Backend-State", "healthy")
                .body(body);
    }
}
~~~

The backend deliberately returns only **booleans (present/absent)** for Authorization/Cookie, **never echoing raw token or cookie values** into responses. The `AtomicLong` counter is strictly for **single-process** lab observation, not a production metric or cluster-wide attempt count.

ID 503 always returns HTTP 503 so we can test the proxy's reaction. Whether the client receives 503 verbatim or a wrapped error depends on how your HTTP client/proxy handles errors in your version; the key goal is verifying **the backend call count** rather than guessing auto-retries occurred.

### 8.3. Running Both Applications

In two terminals respectively:

~~~bash
# Terminal 1: catalog-backend project
./mvnw spring-boot:run

# Terminal 2: proxyexchange-mvc (or proxyexchange-webflux) project
./mvnw spring-boot:run
~~~

On Windows use `mvnw.cmd spring-boot:run` or an installed Maven binary. This is practice code for learners to run themselves; **this lesson does not claim to have executed builds or tests in the repository**.

### 8.4. Testing the Backend Directly

~~~bash
curl -i "http://127.0.0.1:9091/items/42"
~~~

Expect HTTP 200 with `"id":42`, `"path":"/items/42"`. Because the proxy controller is bypassed, `proxyMarker` will be `null`.

Calling `/items/503` directly makes the backend return 503. Use this path to separate backend errors from route-selection or ProxyExchange controller errors.

## 9. Testing the Real Path Without Relying on Server YAML

### 9.1. Calling Through the ProxyExchange Controller

~~~bash
curl -i "http://127.0.0.1:8080/edge/items/42"
~~~

Illustrative response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Backend-State: healthy

{"backend":"catalog-backend","id":42,"path":"/items/42",
 "proxyMarker":"mvc-controller","hasAuthorization":false,
 "hasCookie":false,"backendCallsSinceStart":2}
~~~

`backendCallsSinceStart` may differ from 2 if you did not call directly first or sent extra traffic. **Do not assert a hardcoded count**; compare before-and-after deltas.

Two pieces of evidence stronger than status 200:

- `path=/items/42`: the controller constructed the downstream URI itself, without `StripPrefix`.
- `proxyMarker=mvc-controller`: the header was set via `proxy.header(...)`, not by `AddRequestHeaderGatewayFilterFactory`.

When using **WebFlux ProxyExchange**, the matching marker is `webflux-controller`.

### 9.2. Verifying Annotated Handler Mapping Limits

~~~bash
# No @PostMapping, so this is not an open POST proxy:
curl -i -X POST "http://127.0.0.1:8080/edge/items/42"

# ID cannot be parsed as a long:
curl -i "http://127.0.0.1:8080/edge/items/not-a-number"

# ID outside the range defined in the controller:
curl -i "http://127.0.0.1:8080/edge/items/0"
~~~

Expectation: requests with unmatched methods or invalid types/ranges are rejected by mapping/binding/controller logic. Exact codes may be 400/405/404 depending on version and other handlers. **They do not prove Gateway Server Path/Method predicates are running.**

### 9.3. Testing Against Auto-Filter Assumptions

In a **project with only the ProxyExchange module** like this lab, add Server `default-filters`:

~~~yaml
# Deliberately added to verify: NOT a policy for ProxyExchange controllers
spring:
  cloud:
    gateway:
      server:
        webflux:
          default-filters:
            - AddResponseHeader=X-Expected-Server-Filter,applied
~~~

Run again:

~~~bash
curl -i "http://127.0.0.1:8080/edge/items/42"
~~~

**Do not expect `X-Expected-Server-Filter` to appear** on the controller's response, because that is Server WebFlux config whereas the lab runs a ProxyExchange MVC/WebFlux controller. If the header still appears, check whether **another Server starter/route, another filter, or a reverse proxy added it**. Always verify the **source of a header**, not just its presence.

### 9.4. Testing “Default Retry” With a Failing Backend

~~~bash
curl -i "http://127.0.0.1:8080/edge/items/503"
~~~

The backend intentionally returns an error. Observe `backendCallsSinceStart` and backend logs. **There is no Retry in the controller code**, so writing `retries: 2` under Server route YAML is no promise this proxy will make three backend attempts.

If the proxy's response code differs from 503 due to your version's HTTP client/error handler, separate **error translation** from **retry**: translating an exception into HTTP 500/502 does not mean extra attempts occurred.

### 9.5. Query Parameters Are Not Automatic “RewritePath”

In the lab, the controller explicitly constructs the URL:

~~~java
String upstreamUri = backendBaseUrl + "/items/" + id;
~~~

If the client calls `/edge/items/42?lang=vi`, the code above **does not automatically append `lang=vi` to the URL**. Do not assume ProxyExchange forwards all queries/paths by default like a Gateway Server route with `PreserveHostHeader` or `RewritePath`.

To forward query parameters, design an explicit **allowlist**, URL encoding, default values, and limits. For example, use `UriComponentsBuilder` to attach a parameter declared via `@RequestParam`, rather than concatenating raw unchecked query strings. If downstream authorizes by query/resource, guard against parameter pollution and unexpected duplicate keys.

## 10. Request/Response Headers: ProxyExchange Differs From FilterFactory

A common source of security bugs is assuming `ProxyExchange` copies every HTTP header verbatim like a Gateway Server–configured reverse proxy.

Proxy Exchange docs list **specially handled header groups**:

| Group | Documented Defaults | Why |
| --- | --- | --- |
| **Sensitive** | `Cookie`, `Authorization` | Avoid accidentally forwarding client credentials/sessions to unintended backends |
| **Skipped** | `Content-Length`, `Host` | The backend HTTP client may change body length, transfer encoding, or authority |
| **Proxy headers** | `X-Forwarded-*` | Supports proxy metadata handling via its own mechanism |

This is the **default** behavior documented for Proxy Exchange downstream calls; whenever you customize `sensitive()`, `header()`, properties, or the HTTP client, re-verify concrete behavior.

### 10.1. Is `proxy.header(...)` Equivalent to AddRequestHeaderGatewayFilterFactory?

No. In ProxyExchange MVC, the Java API provides:

~~~java
proxy.header("X-Proxy-Lab", "mvc-controller");
~~~

This API sets a header for the **downstream call**. It is invoked **directly inside the controller**, needing neither a route ID nor `GatewayFilterChain`. The business concept resembles Gateway Server's “add request header”, but the **execution path differs**.

To modify the response sent to the client, ProxyExchange also provides HTTP method overloads accepting a **mapper**:

~~~java
// Illustrative pattern: responseMapper transforms the downstream response
// into the client response, useful when adjusting headers/status.
return proxy.uri("http://127.0.0.1:9091/items/42")
        .get(response -> ResponseEntity
                .status(response.getStatusCode())
                .headers(response.getHeaders())
                .header("X-Proxy-Response", "mapped")
                .body(response.getBody()));
~~~

This illustration uses the MVC ProxyExchange Java API and Spring `ResponseEntity`. If building against a version with different generic method signatures, check the matching Javadoc. When copying downstream headers, watch out for **hop-by-hop headers** and stale `Content-Length`/`Transfer-Encoding` if the body or encoding changed. Never copy conflicting headers blindly when changing status/body.

### 10.2. Never Relay Authorization Blindly

A client may send:

~~~http
Authorization: Bearer eyJ...
Cookie: SESSION=...
X-Forwarded-For: 203.0.113.77
~~~

If the frontend sends a token meant for accessing the Gateway, the backend may require **a different token** with its own audience and scopes. ProxyExchange's default stripping of `Authorization`/`Cookie` helps prevent accidental leaks, yet **does not build an authorization system**. Never replace `sensitive()` with an empty list just to “make the backend call work” without checking audience, scope, issuer, and trust boundaries.

Safer approach when downstream identity is needed:

1. Spring Security authenticates the client on the matching web stack.
2. Identify which backends need user identity or a delegated token.
3. Use an **intentional** token-exchange / client-credentials / authorized-client mechanism.
4. Keep raw tokens out of URLs, logs, responses, and metric labels.
5. Backends still verify permissions on critical resources.

**Do not assume Server's `TokenRelay` filter works** on ProxyExchange controllers: it is not attached automatically to annotated handlers. Integrate OAuth2/Spring Security explicitly, then test the actual headers arriving at the backend.

### 10.3. Host and Content-Length Must Not Be Copied Arbitrarily

The downstream HTTP call may have a different authority, port, or scheme than the frontend; forcing the client's raw `Host` header can break virtual-host routing or mislead the backend about origin. Likewise, if the body is re-serialized or sent chunked, the original `Content-Length` will be wrong.

Never write a custom controller like:

~~~java
// CONCEPTUALLY WRONG, not a recommended API:
// for (var header : incomingHeaders) proxy.header(header);
~~~

Copying every header verbatim can forward:

- Credentials with the wrong audience.
- `Connection` and hop-by-hop headers.
- Inconsistent `Content-Length`/`Transfer-Encoding`.
- Client-forged identity/tenant headers.
- Untrusted forwarding metadata.

Use an allowlist or an explicit denylist policy grounded in the backend contract and trust boundaries.

### 10.4. Forwarded/X-Forwarded-* Still Requires Checking Trusted Proxies

ProxyExchange supports `X-Forwarded-*`, but **never treat every `X-Forwarded-For` as a real IP**. If edge/ingress fails to strip client-sent values, an attacker can send:

~~~http
X-Forwarded-For: 10.0.0.1
X-Forwarded-Proto: https
X-Forwarded-Host: admin.internal
~~~

Therefore, when using IP, scheme, or host for auditing, rate limiting, or redirects:

- Isolate Gateway entry paths so clients cannot bypass ingress.
- Have a trusted reverse proxy clean/overwrite forwarding headers.
- Configure trusted proxies using the actual **WebFlux/MVC ProxyExchange and Spring Framework** mechanisms—never copy Server properties.
- Never use client-supplied `X-Forwarded-Host` to generate redirects or downstream URIs.
- Test forged external requests and inspect what the backend receives.

Spring Cloud also ships per-version security updates for forwarding headers. Default behavior can change after upgrades; do not rely on old examples to widen trust.

## 11. Replacing Server Route/Filter Policies Intentionally

Because ProxyExchange is an **in-controller** HTTP proxy utility, whenever cross-cutting behavior is needed, identify the actual layer handling it:

| Requirement | Approach for ProxyExchange | Why Not Just Put a Server Filter? |
| --- | --- | --- |
| Block unauthenticated callers | Spring Security `SecurityFilterChain` (MVC) or `SecurityWebFilterChain` (WebFlux) | Server auth filters do not wrap annotated handlers automatically |
| Tenant/item authorization | Controller/service + Security authorization | Resource permissions need business context |
| Client rate limiting | Servlet Filter, WebFilter, Bucket4j, or actively integrated service quota | Server's `RequestRateLimiter` does not run automatically |
| Downstream circuit breaker | Resilience4j/Spring Cloud CircuitBreaker around HTTP client call, with fallback | No Server CircuitBreaker filter chain on controllers |
| Controlled GET retries | Dedicated HTTP client retry with bounded attempts/deadlines | Server Retry filter is not invoked |
| Modify downstream path/headers | Controller + ProxyExchange API + safe URI builder | Server `RewritePath/SetPath` does not alter controller URIs |
| CORS | Spring MVC/WebFlux CORS + Security policy | Server CORS route config does not apply to controllers |
| Service discovery | Actively integrate LoadBalancer client / `DiscoveryClient` | `proxy.uri("lb://...")` does not become Server LB routing automatically |
| Observability | Micrometer/HTTP server metrics, HTTP client metrics, explicit tracing | No automatic Server route ID tags/counters |
| Route refresh | Custom config or deploy/controller strategy | `RefreshRoutesEvent` does not recompile `@GetMapping` |

### 11.1. Spring Security MVC Example Blocking Unauthenticated Requests

If the API must protect all `/edge/items/**` paths, one strategy is configuring Servlet Security:

~~~java
package demo.proxymvc.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/edge/items/**").authenticated()
                .anyRequest().denyAll());

        http.oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

This is an **illustrative Security example** that only runs once Spring Security resource-server dependencies are added and issuer/JWKs, audience validation, and keys are configured. Never use this snippet as-is without an IdP or test tokens. A Servlet-layer Security chain can guard annotated controllers **even without Gateway Server MVC installed**.

**Do not claim** Spring Security turns on every desired policy automatically: you must define matching rules—never set `anyRequest().permitAll()` expecting ProxyExchange to bring `TokenRelay` or Gateway Server auth filters.

### 11.2. Equivalent Example for Spring WebFlux

~~~java
package demo.proxyflux.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class ReactiveApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http.authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET,
                        "/edge/items/**").authenticated()
                .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

`SecurityWebFilterChain` protects annotated WebFlux handlers per Spring Security's matching rules. It is **not** a Gateway Server WebFlux `GlobalFilter`. The MVC and WebFlux examples differ in imports, lifecycles, and web stacks; use only the one matching your application type.

### 11.3. Adding Rate Limiting and Circuit Breakers Should Not Be “Faked With Booleans”

A snippet like:

~~~java
// PSEUDOCODE — the helpers below must have real implementations.
quotaPolicy.check(authenticatedPrincipal, "catalog-read");
return circuitBreaker.execute(
        () -> proxy.uri(fixedBackendUri).get());
~~~

only shows **logical placement**. It is not yet a working RateLimiter or circuit breaker, nor does it address 429/503 responses, key uniqueness, timeouts, thread safety, or cluster-wide state.

When integrating these yourself:

1. **Rate limit key:** derive from the authenticated principal/client/tenant or trusted-proxy IP; never trust self-reported headers.
2. **Distributed state:** use Redis or an appropriate adapter when running multiple ProxyExchange replicas. Standalone local limiters enforce only per-replica quotas.
3. **Quota exceeded** returns 429; **quota store unavailable** needs an explicit fail-open/closed/degraded policy rather than ambiguously returning 429.
4. Circuit-breaker fallbacks must honor downstream failure semantics, never turning real failures into HTTP 200 regardless of contract.
5. Retries on POST/PUT/PATCH require durable backend idempotency keys; retries can multiply downstream calls and retain bodies longer.
6. In WebFlux, never call a blocking HTTP client on the event loop; in MVC, never tie up Servlet request threads indefinitely.

If these requirements repeat across hundreds of APIs/routes, that is a strong signal to **move to Gateway Server** or build a thoroughly tested reusable abstraction rather than duplicating code in every controller.

## 12. Discovery, lb://, Path Rewriting, and Controller Routes

### 12.1. `lb://service-id` Is Not an Ordinary HTTP URI

In Server Gateway, `lb://orders-service` can be resolved by a **LoadBalancer filter/routing integration**. A ProxyExchange controller, however, works through an HTTP client; a call like:

~~~java
// Do NOT assume this gives you Server LB filtering automatically:
proxy.uri("lb://orders-service/items/42").get();
~~~

is **not guaranteed** to be handled like a Server `lb://` route, because annotated controllers lack the Server LoadBalancer filter chain. The result can be an unsupported URI scheme in the HTTP client unless you have configured **an explicit client/load-balancer integration**.

Options:

- Use a fixed HTTP(S) upstream from configuration, as in the lab.
- Inject `DiscoveryClient` / `ReactiveDiscoveryClient` and pick a service instance using a safe strategy if you genuinely want to manage discovery yourself.
- Use a `@LoadBalanced` HTTP client with proper load-balancer integration where supported by Spring Cloud docs.
- If routing by service ID and path/header conditions is central, use Gateway Server with its discovery locator and load-balancer filters.

Never pick `instances.get(0)` and call it production load balancing: account for health, zones, connection pools, retries, and instance churn.

### 12.2. Path Rewriting Differs From `proxy.path(...)`

Gateway Server has built-in `RewritePath`, `StripPrefix`, and `SetPath`. ProxyExchange offers helpers like `proxy.path(prefix)` to extract the path after a prefix; calling this helper **does not register a Server `RouteDefinition`** and does not apply all of Server's regex/route-template behavior.

Documentation example:

~~~java
@GetMapping("/proxy/path/**")
public ResponseEntity<?> proxyPath(ProxyExchange<byte[]> proxy)
        throws Exception {
    String suffix = proxy.path("/proxy/path/");
    return proxy.uri(
            "http://127.0.0.1:9091/items/" + suffix).get();
}
~~~

This example is only for understanding `proxy.path(prefix)`; if the suffix comes from clients:

- Guard against path traversal, percent-encoding, slashes/backslashes, and special Unicode characters.
- Never let a raw path alter host/scheme or inject out-of-policy queries/fragments.
- Use a URI builder/allowlist and test `%2F`, `..`, and repeated slashes.
- If the API only uses numeric IDs, prefer `@PathVariable long id` as in the lab.

### 12.3. Header Rewriting Is Not a Trust Boundary by Itself

A ProxyExchange controller can add:

~~~java
proxy.header("X-Route-Tag", "catalog");
~~~

However, if the backend trusts `X-Tenant-Id` or `X-Authenticated-User`, you must **strip forged client values and set values from the verified authentication context** rather than merely appending. Verifying backend-received headers in integration tests is mandatory for sensitive policies.

## 13. Actuator, Route Refresh, and Dynamic Configuration: Different Scopes

Gateway Server typically uses:

~~~text
RouteDefinitionRepository/Locator
  → RouteDefinitionRouteLocator
  → CachingRouteLocator
  → Gateway filter chain

RefreshRoutesEvent / POST /actuator/gateway/refresh
  → triggers rebuilding Server routes at runtime
~~~

Annotated ProxyExchange controllers typically use:

~~~text
Spring @RequestMapping metadata
  → Spring MVC/WebFlux handler mapping
  → controller method
  → proxy.uri(...).get()
~~~

**`RefreshRoutesEvent` is a Gateway Server event**; it does not alter `@GetMapping("/edge/items/{id}")` annotations, recompile controllers, or inject Server `default-filters` into `ProxyExchange`.

### 13.1. What Happens When `demo.proxy.backend-base-url` Changes?

The lab property:

~~~yaml
demo:
  proxy:
    backend-base-url: http://127.0.0.1:9091
~~~

is injected into the controller when Spring creates the bean. Editing `application.yml` on disk after startup **does not automatically update the field inside the bean**. You need a redeploy/restart or an explicitly designed configuration-refresh/application mechanism with validation and rollback. Firing `RefreshRoutesEvent` is not the default answer.

### 13.2. Does `/actuator/gateway/routes` Reflect Annotated Controllers?

That endpoint is primarily for inspecting **Gateway Server** routes when the Server Actuator endpoint is enabled. It is not a general catalog of all `@GetMapping` or `ProxyExchange` handlers.

For annotated Spring handlers, Actuator's **`/actuator/mappings`** (when exposed in a controlled way) is a better place to inspect mappings. Even so, the mappings endpoint **does not reveal dynamic destination URIs assembled in Java** or prove security rules and timeouts are right.

Never set `management.endpoints.web.exposure.include="*"` on the Internet to debug missing routes. Expose only needed endpoints on a dedicated management port protected by authentication and RBAC.

### 13.3. When Both Server and ProxyExchange Are Installed in One App

This is possible, though tricky to observe:

~~~text
Gateway Server route:     Path=/api/**
ProxyExchange controller: @GetMapping("/api/catalog/{id}")
~~~

A request may be claimed first by either the Server handler mapping or the controller depending on web stack, configuration, and ordering. When debugging:

1. Check the active Spring Boot web application type and auto-configurations.
2. Log the exact controller handler name or Server route ID that handled the request.
3. Use separate paths in integration tests to prove both pipelines.
4. Never assume Server filters ran before the controller simply because request paths look similar.
5. Once choosing one flavor for a service, remove unnecessary starters to eliminate confusion.

An application can simultaneously use a Servlet Filter / WebFlux WebFilter alongside a Server route filter—but **sharing the same web stack does not mean annotated controllers pass through Server route filters**.

## 14. When ProxyExchange Fails: Status, Timeouts, and Memory Have No “Gateway Server Defaults”

### 14.1. Quota Exhaustion Differs From Upstream 503

Suppose an API needs a limit of 20 requests/second per principal, while the backend occasionally returns 503. With Gateway Server WebFlux, a route can integrate `RequestRateLimiter` and `Retry` with explicit policies. With a ProxyExchange controller:

~~~text
Client
  ↓
Spring Security (authentication/authorization if configured)
  ↓
Controller (validate id, enforce quota if implemented in code)
  ↓
ProxyExchange downstream GET
  ↓
Backend returns 200 / 404 / 503
  ↓
Controller/HTTP client responds to client
~~~

Whatever has not been coded **does not happen just because a filter name exists in the Server docs**. Distinguish:

| Condition | Expected Response / Policy | Responsible Component |
| --- | --- | --- |
| Principal lacks permission | 401/403 | Spring Security, backend authorization |
| Caller exceeds quota | 429 | Explicitly integrated limiter |
| Quota store fails, quota unknown | 503 / controlled fail-open per policy | Application quota component |
| Backend returns 503 | Relay 503 or apply proper error mapping | HTTP client/ProxyExchange/controller/error handler |
| Backend unreachable, connect timeout | Categorized 5xx, logs/metrics, deadline | HTTP client config and exception handling |
| Backend wrote data, response dropped | Never retry blindly | Idempotency contract and retry policy |

Do not “convert” every exception into 429 or 200, as that misleads monitoring and clients about system health.

### 14.2. HTTP Client Timeouts Are Not Retry Filter Timeouts

Server Gateway has its own timeout properties and route-specific filters. ProxyExchange uses an underlying HTTP client per web stack and version. Therefore, snippets like:

~~~properties
# Do NOT assume this sets a timeout for a ProxyExchange controller:
spring.cloud.gateway.server.webflux.httpclient.connect-timeout=1000
~~~

do not automatically set a connect timeout on a ProxyExchange MVC HTTP client. For MVC, identify the corresponding client/request factory and configure connection/read timeouts; for WebFlux, configure the matching HTTP connector/response timeouts. Whenever swapping implementations, test DNS failures, connect timeouts, and response-body read timeouts.

### 14.3. Managing Large Bodies

`ProxyExchange<byte[]>` is convenient for modest response sizes, yet the byte array may have to hold the entire payload in memory. With 200 concurrent requests each receiving a 4 MiB response, the raw payload footprint alone is:

\[
M_{\mathrm{payload}}\approx 200\times 4\,\mathrm{MiB}
=800\,\mathrm{MiB}
\]

This is **not the real heap measurement**: you also have HTTP client overhead, headers, TLS buffers, copies, GC, and other objects. With ProxyExchange WebFlux, using a reactive `Mono` does not automatically guarantee unbuffered streaming for large file downloads; the `byte[]` body type and concrete implementation still dictate behavior.

If the API handles large uploads/downloads, SSE/WebSockets, or streaming requests/responses:

- Pick a streaming mechanism supported by your docs and version instead of holding large byte arrays.
- Configure request size and concurrency limits.
- Never retry requests whose bodies trigger side effects or cannot be replayed.
- Test request cancellation, downstream disconnects, and memory/direct buffers.
- When general-purpose streaming reverse proxying is required, evaluate Gateway Server or a dedicated reverse proxy.

### 14.4. Error Mapping and Response Headers

The HTTP client under ProxyExchange may treat 4xx/5xx responses and network exceptions differently across library versions. **Never assume every error is passed straight through as a `ResponseEntity` with the same status.**

A production system should test:

- Downstream returning 404 with a body.
- Downstream returning 429 with `Retry-After`.
- Downstream returning 503, then recovering.
- Connection refused / timeout / TLS handshake failure.
- Downstream returning redirects, 204 No Content, or malformed responses.
- Client canceling the request before the backend responds.

Verify that response mapping does not copy conflicting headers: hop-by-hop headers, stale `Content-Length` after body changes, or `Location` pointing to internal domains.

## 15. Negative Testing to Prove Server Policies Do *Not* Apply Automatically

A good test proves **which layer handled the request**, rather than merely observing HTTP 200.

### 15.1. Minimum Test Matrix

| Case | Input / Action | Observation to Verify |
| --- | --- | --- |
| P01 | Call backend `:9091/items/42` directly | Backend runs, no ProxyExchange marker |
| P02 | Call `:8080/edge/items/42` | Backend sees `/items/42` and controller-added marker |
| P03 | POST to a GET-only annotated handler | Does not act as an open POST proxy |
| P04 | Send non-numeric or non-positive ID | Annotated handler binding/validation rejects it |
| P05 | Add Server `default-filters` in a ProxyExchange-only app | No Server-filter response header appears by default |
| P06 | Add Server `Retry` config, call backend ID 503 | Do not assume extra backend attempts happen |
| P07 | Send query param not forwarded by controller | Not rewritten/forwarded automatically like a Server route |
| P08 | Send test `Authorization`/`Cookie` | Backend receives no credentials per default sensitive policy; verify for your version |
| P09 | Send fake `X-Forwarded-For` from client | Not trusted as the client IP |
| P10 | Enable stack-appropriate security, call anonymously | Blocked by the Security chain policy |
| P11 | Omit Gateway Server starter, call `/actuator/gateway/routes` | Do not use this endpoint to confirm controller presence |
| P12 | Edit Server YAML routes without changing controller | Annotated handler destination does not change |
| P13 | Same app has overlapping Server route and controller | Verify real handler via tracing/logs, never infer from status |
| P14 | Backend unreachable | Clean timeout and error mapping; request does not hang |
| P15 | Concurrent load with large response bodies | Memory and latency stay bounded |

Tests should distinguish **default behavior** from **custom integrations**: if an app has its own `Servlet Filter` or `WebFilter`, that filter can add headers or rate limits to controllers, but it is not coming from Gateway Server route filters.

### 15.2. cURL Check for Sensitive Headers (Dummy Data Only)

~~~bash
curl -i "http://127.0.0.1:8080/edge/items/42" \
  -H "Authorization: Bearer LAB_FAKE_TOKEN_NOT_REAL" \
  -H "Cookie: lab=session-placeholder" \
  -H "X-Forwarded-For: 203.0.113.55"
~~~

Under default ProxyExchange configuration per documentation, the backend echo expects:

~~~json
{
  "hasAuthorization": false,
  "hasCookie": false
}
~~~

This is an **expectation based on documented behavior**, not a guarantee if code customized the header policy or uses a different version/client. Never put real tokens in terminal history or logs. The sample backend echoes only booleans, never exposing credential contents.

### 15.3. Diagnosing by Mapping Instead of Route ID

In an annotated-handler app, you can:

1. Log controller entry using a sanitized correlation ID.
2. Inspect Spring MVC/WebFlux mappings (if Actuator mappings are enabled on a secured management plane).
3. Read HTTP client logs/metrics for downstream URLs **after redacting secrets**.
4. Compare paths/headers arriving at the backend.
5. Separate responses returned by the backend from responses generated by exception handlers.

Do not waste time debugging `/actuator/gateway/routes` if the project does not use Gateway Server routes.

## 16. Troubleshooting Errors Caused by Misapplying Server Docs

| Symptom | Likely Cause | Check Steps |
| --- | --- | --- |
| `AddResponseHeader` header missing | Calling a ProxyExchange controller, not a Server route | Check handler mapping; find where headers are built |
| `RewritePath` does not change backend path | Controller constructs URL manually | Inspect `proxy.uri(...)`; echo backend path |
| Retries don't fire despite `retries: 2` | Retry filter belongs to a Server route | Log backend call count; inspect retry wrapper around ProxyExchange |
| `RedisRateLimiter` properties set yet quota exceeded | No `RequestRateLimiter` pipeline | Inspect controller / Servlet Filter / WebFilter limiter |
| `lb://orders-service` fails with scheme/URI error | No Server LoadBalancer filter | Verify HTTP client / load-balancer integration |
| Spring Security works, Server `TokenRelay` does not | Security chain does not run Server token relay automatically | Design token propagation per backend audience |
| Editing `spring.cloud.gateway.server.webflux.routes` doesn't change controller | Annotated mapping and controller destination are independent | Inspect dependencies and source of truth |
| Sending `RefreshRoutesEvent` leaves controller URL unchanged | Event refreshes only Server route cache | Check config beans / controller refresh strategy |
| `/actuator/gateway/routes` empty while Proxy API still works | Controllers are not in Server Route inventory | Use Actuator mappings and endpoint smoke tests |
| Backend loses `Authorization` | Sensitive headers filtered by ProxyExchange | Review auth delegation contract; never enable pass-through blindly |
| Backend receives spoofed `X-Forwarded-For` | Edge did not sanitize forwarding metadata | Audit proxy trust boundaries |
| POST payload has altered `Content-Length` | HTTP client changed body/encoding | Never copy raw `Content-Length`/`Host` |
| Client gets 503 while backend logs only one call | No retries (or policy mismatch) | Separate status mapping from attempt count |
| Memory spikes on file downloads | `byte[]` bodies under concurrent load | Measure RSS/heap/direct memory and streaming strategy |
| Controller 404s while Server route exists | HandlerMapping precedence or route conflict | Separate paths and verify active handler |
| CORS preflight fails | MVC/WebFlux CORS and Security misconfigured | Check `OPTIONS` handling and allowed origins/methods |

**Systematic debugging order:** trace `flavor → web stack → handler mapping → downstream client → security/filter boundary` in sequence. Never hastily add the Server starter to “fix a missing header”; doing so can introduce a new routing path and complicate diagnosis.

## 17. When to Keep ProxyExchange vs. Migrate to Gateway Server

### 17.1. Deciding by Policy Scale

| Scenario | Option to Consider | Rationale |
| --- | --- | --- |
| Only 1–3 custom proxy endpoints inside an existing web app | **ProxyExchange** | Close to business code, minimal route-engine overhead |
| One endpoint aggregating data from multiple backends | Controller/service + HTTP client, optionally ProxyExchange for specific calls | Needs business orchestration rather than transparent reverse proxying |
| Hundreds of routes with path/header predicates and shared route filters | **Gateway Server** | Uses unified route definitions and filter factories |
| Dynamic route updates, live route inventory, route refresh | **Gateway Server** | Route repository/cache/actuator fit better |
| Per-tenant/route quotas, complex circuit breaker/retry/filter ordering | Usually **Gateway Server** or a clear abstraction | Reduces duplicated policy code |
| Very large uploads/downloads/streaming, long-lived connections | Evaluate Gateway Server or a dedicated proxy | Needs matching memory, timeout, and streaming semantics |
| App already has MVC Servlet Security filter chain and needs 1 custom proxy path | **ProxyExchange MVC** can fit | Reuses already-controlled authentication/authorization |
| App primarily uses WebFlux reactive annotated controllers | **ProxyExchange WebFlux** can fit for a small endpoint count | Keeps the reactive programming model |
| Need WebMvc.fn route-specific Before/After/`HandlerFilterFunction` | **Gateway Server Web MVC** | Not ProxyExchange MVC annotated handlers |

No single choice fits every system. What matters is **never advertising one flavor's features as if the other flavor owned that pipeline**.

### 17.2. Decision Flow

~~~mermaid
flowchart TD
    A["Need to forward HTTP requests?"] --> B{"Need route inventory,<br/>many predicates/filters, dynamic routes?"}
    B -->|"Yes"| S["Prefer matching Gateway Server WebFlux/MVC"]
    B -->|"No"| C{"Controller needs custom business logic?"}
    C -->|"Yes"| P["Consider ProxyExchange in annotated handler"]
    C -->|"No"| D["Consider Gateway Server or a simple reverse proxy"]
    P --> E["Design AuthN/AuthZ, rate limit,<br/>timeouts, resilience, header trust separately"]
    S --> F["Configure routes/filters per exact flavor and version"]
    E --> T["Integration tests proving policies"]
    F --> T
~~~

### 17.3. Migrating From ProxyExchange to Gateway Server: What Must Move

If a project grows from two controllers to hundreds of routes:

1. Inventory **all annotated mappings** being proxied, their methods/paths/queries, and custom controller logic.
2. Translate routes/URIs into **Server `RouteDefinition`/Java Routes API** for your web stack, avoiding path collisions with controllers during rollout.
3. Map each controller responsibility to matching predicates/filters; verify differences in **bodies, headers, statuses, and forwarded metadata**.
4. Specifically review sensitive header defaults: ProxyExchange strips `Authorization`/`Cookie` by default, whereas Server policies are not automatically identical. **Never leak credentials to backends during migration.**
5. Keep authentication and backend authorization on the same trust boundary.
6. Design retries, circuit breakers, rate limiters, and quota keys explicitly rather than copying defaults blindly.
7. Test with traffic mirroring/canaries, distinguishing which layer produced 4xx/5xx responses.
8. Verify service discovery, LoadBalancer, URI rewriting, and Host/Proto before rollout.
9. Retire legacy controllers only after contracts, metrics, and security match and rollback is proven.

**Do not equate “same HTTP status and body” with “same security posture”.** Two pipelines can return identical 200s while differing in whether Cookies/JWTs are forwarded, quotas are enforced, or Host/Forwarded headers are trusted.

## 18. Production Checklist Specifically for ProxyExchange

- [ ] Confirmed this is **Proxy Exchange**, not Gateway Server; artifact matches MVC/WebFlux.
- [ ] Compatible Spring Cloud BOM used; module/property names verified against the 2025.0 rename.
- [ ] Controllers define explicit HTTP method/path mappings, never an unchecked `/**` proxy.
- [ ] Destination URIs come from trusted allowlists/configs, never raw untrusted headers/queries.
- [ ] Query/path parameters are validated and encoded; guarded against traversal, open redirects, and SSRF.
- [ ] Do not assume `spring.cloud.gateway.server.*.routes/default-filters` apply to ProxyExchange.
- [ ] Do not assume Server `RequestRateLimiter`/`Retry`/`CircuitBreaker`/`TokenRelay` wrap controllers automatically.
- [ ] Appropriate Spring Security MVC/WebFlux configured and tested for anonymous and authorized cases.
- [ ] Sensitive headers, skipped headers, and `X-Forwarded` trust verified at both Gateway and backend.
- [ ] Raw `Cookie`, `Authorization`, `Host`, `Content-Length`, and hop-by-hop headers are not blindly forwarded.
- [ ] Connect/read/response timeouts configured for the actual HTTP client used by ProxyExchange.
- [ ] If rate limiting is needed, use a real integrated limiter, trusted quota key, and multi-replica state.
- [ ] Retries never duplicate unintended side effects; retryable POSTs have an idempotency contract.
- [ ] Response mappers never corrupt status, `Content-Length`, `Transfer-Encoding`, `Location`, or CORS.
- [ ] Large bodies are not buffered/downloaded into `byte[]` without memory and cancellation load tests.
- [ ] Metrics distinguish inbound requests, downstream attempts, backend errors, timeouts, and auth decisions.
- [ ] Do not treat `/actuator/gateway/routes` as an inventory of annotated controllers.
- [ ] If the project includes both Server and ProxyExchange, tests verify handler mapping/precedence with no unintended route overlaps.
- [ ] Changing backend URLs has a dedicated config-update mechanism, readiness checks, and rollback.
- [ ] Negative tests prove Server filter configs are not mistaken for active controller policies.

## 19. Self-Check Questions

**1. Does adding `spring.cloud.gateway.server.webflux.default-filters` automatically add a response header to a ProxyExchange WebFlux controller?**

No. `default-filters` belongs to **Gateway Server WebFlux** routes. A ProxyExchange controller is a separate annotated handler; to modify headers, use the ProxyExchange API, a response mapper, or a Spring WebFlux `WebFilter`.

**2. Gateway Server Web MVC and ProxyExchange Web MVC both run on Servlet. Do they share the same filter chain?**

Not by default. Server Web MVC uses WebMvc.fn routes/`HandlerFilterFunction`; ProxyExchange MVC uses `@Controller` and the ProxyExchange argument resolver. Both can share underlying Servlet/Spring Security filters, yet **they do not share Server route filters**.

**3. Why is `/actuator/gateway/routes` empty while `/edge/items/42` still calls the backend?**

Because an annotated `@GetMapping` is not a Server `RouteDefinition`. Inspect a secured `/actuator/mappings` endpoint and controller/downstream logs instead.

**4. If you change a Server route URI from A to B and fire `RefreshRoutesEvent`, does the controller automatically switch to B?**

No. The controller builds its URI from its own code/config. A Server route refresh event does not rewrite fields inside controllers.

**5. How does ProxyExchange handle `Authorization` and `Cookie` by default?**

The documentation describes them as **sensitive headers** stripped from downstream calls by default. Always test your specific version/customizations, and never enable credential relay blindly to “fix” a backend 401.

**6. If the backend returns 503, what effect does setting `retries: 3` in Server YAML have on a ProxyExchange controller?**

It does not make the controller retry requests. To retry, integrate a retry policy around the actual HTTP call/stack with a budget, deadline, and idempotency.

**7. When should you migrate to Gateway Server?**

When you need many routes, shared filters, built-in discovery/LoadBalancer, dynamic route refresh, or route-ID-level observability. Base the decision on policy scale/complexity and real operational requirements.

## 20. References

1. [Spring Cloud Gateway — Proxy Exchange Gateway with Spring Web MVC or WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-proxy-exchange.html): primary doc confirming Proxy Exchange is an alternative style separate from Gateway Server docs; artifacts, controllers, and header policies.
2. [Spring Cloud Gateway Proxy Exchange 4.3](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-proxy-exchange.html): reference for applications on the 4.3.x release.
3. [Spring Cloud Gateway 5.0 — Proxy Exchange](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-proxy-exchange.html): reference for 5.0.x.
4. [Spring Cloud Gateway — Project Introduction](https://docs.spring.io/spring-cloud-gateway/reference/intro.html): Server vs. Proxy Exchange, MVC vs. WebFlux.
5. [Spring Cloud 2025.0 Release Notes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes): artifact renames and configuration namespaces.
6. [Spring Cloud Gateway Server WebFlux — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/how-it-works.html): **Server** route predicates, Gateway filter chain, and Netty routing, for spotting differences.
7. [Spring Cloud Gateway Server Web MVC — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/how-it-works.html): **Server MVC** WebMvc.fn `RouterFunction`/`HandlerFilterFunction`.
8. [Spring Framework — Spring MVC annotated controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html): `@RequestMapping` and argument annotations in MVC.
9. [Spring Framework — Spring WebFlux annotated controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html): annotated handlers in reactive WebFlux.
10. [Spring Security — Servlet authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) and [Reactive authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): security mechanisms per stack.

**Remember:** `ProxyExchange` lets an annotated MVC/WebFlux controller make downstream HTTP calls conveniently, yet it is **not a Spring Cloud Gateway Server Route**. Consequently, Server's `routes`, `default-filters`, `RequestRateLimiter`, `Retry`, `CircuitBreaker`, `TokenRelay`, and `RefreshRoutesEvent` **do not apply automatically** to that controller. Verify **which handler** actually processes requests, use configuration matching your **flavor and web stack**, and intentionally wire authentication, header trust, timeouts, quotas, resilience, and observability. When route and policy counts grow large, choose Gateway Server to avoid rebuilding an entire filter pipeline inside controllers.
