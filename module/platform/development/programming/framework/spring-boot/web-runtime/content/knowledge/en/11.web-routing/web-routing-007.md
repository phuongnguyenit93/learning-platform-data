# Route Composition, Path Grouping, and Handler Selection Order in Spring Boot

In the Spring Boot web runtime, **routing** determines which HTTP request is dispatched to which handler. A route can depend on the URL path, HTTP method, query parameters, headers, Content-Type, and Accept. When a project has dozens of controllers or multiple functional routers, three things must be understood: **route composition**, **path grouping**, and **handler selection order**.

**Foundational distinction:**
- With **annotated controllers** (`@RequestMapping`, `@GetMapping`), Spring MVC/WebFlux compares matching mappings and prioritizes more specific conditions/patterns. Do not treat method declaration order in the source file as priority.
- With **functional routing** (`RouterFunction`), composed branches are typically evaluated **in order**; the first matching branch wins. Place literal/specific routes before variable/catch-all routes.
- At a higher level, `DispatcherServlet` (MVC) or `DispatcherHandler` (WebFlux) queries `HandlerMapping` beans according to their `order`. A HandlerMapping that finds a handler first can prevent subsequent mapping mechanisms from being evaluated.

## 1. Which conditions make up an HTTP route?

Example request:

~~~http
GET /api/v1/products/42?detail=true HTTP/1.1
Host: example.test
Accept: application/json
~~~

Components used during matching:

| Attribute | Example value | Purpose |
|---|---|---|
| Path | `/api/v1/products/42` | Selects group and endpoint |
| HTTP method | GET | Distinguishes GET/POST/PUT/DELETE on the same path |
| Query parameter | `detail=true` | Can participate in `params` predicates |
| Header | Accept: application/json | `produces` condition, content negotiation |
| Content-Type | e.g. application/json when body is present | `consumes` condition and body converter selection |

The query string is not part of the path pattern; `/products?sort=name` and `/products?sort=price` share the same path `/products` yet can be distinguished using `params` conditions.

The selected route is the result of a **combination of conditions**, not just matching a single path string.

## 2. Request flow to HandlerMapping

With the Spring MVC Servlet stack:

~~~text
Client
 -> Servlet container (Tomcat / Jetty / Undertow)
 -> Servlet FilterChain (may include Spring Security)
 -> DispatcherServlet
 -> HandlerMapping by order
 -> HandlerAdapter
 -> Controller or HandlerFunction
 -> HTTP response
~~~

With the Spring WebFlux reactive stack, the framework normally uses `DispatcherHandler` and reactive `HandlerMapping` / `HandlerAdapter` beans; on Reactor Netty, there is no Servlet FilterChain in the conventional Servlet sense.

Common mapping strategies in MVC:

- `RequestMappingHandlerMapping`: annotated controllers.
- `RouterFunctionMapping`: Spring MVC functional routes.
- Resource handler mappings: serve static resources per configuration.
- Other `HandlerMapping` instances provided by the framework or application.

Spring uses the first `HandlerMapping` that returns a handler according to the configured order. Therefore, **annotated route specificity is not a global comparison across all RouterFunctions and controllers**. Distinguish HandlerMapping ordering from branch ordering inside a single functional router.

## 3. URL composition: class-level and method-level @RequestMapping

Spring MVC lets you group endpoints using a prefix on the controller:

~~~java
@RestController
@RequestMapping("/api/v1/users")
class UserController {

    @GetMapping
    String listUsers() {
        return "list";
    }

    @GetMapping("/{id}")
    String byId(@PathVariable String id) {
        return "user:" + id;
    }

    @PostMapping
    String createUser() {
        return "created";
    }
}
~~~

This is a fragment requiring imports and a Spring MVC project. Resulting URLs:

| Request | Method |
|---|---|
| GET `/api/v1/users` | `listUsers()` |
| GET `/api/v1/users/9` | `byId("9")` |
| POST `/api/v1/users` | `createUser()` |

`@RequestMapping` on the class acts as a shared prefix/condition; `@GetMapping` and `@PostMapping` on methods add subpaths and HTTP methods. A method can also declare multiple paths using a path array; ensure those aliases share the same semantics.

### 3.1. Context path is not a controller prefix

If `application.yml` has:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /shop
~~~

then clients call `GET /shop/api/v1/users`, while the controller still declares `@RequestMapping("/api/v1/users")`. Do not copy `/shop` into the annotation, because that is the context path at the Servlet container layer.

`spring.mvc.servlet.path`, if configured, is the DispatcherServlet path mapping and differs from the context path. A reverse proxy/ingress can also rewrite URLs; inspect the actual path forwarded to the application, not only the client-visible URL.

## 4. Method, params, headers, consumes, and produces conditions

Multiple mappings can share a URL while differing in conditions:

~~~java
@GetMapping(path = "/reports", params = "mode=short",
            produces = "text/plain")
String shortReport() {
    return "short";
}

@GetMapping(path = "/reports", params = "mode=full",
            produces = "text/plain")
String fullReport() {
    return "full";
}
~~~

This is a fragment inside a controller; the two endpoints share URL path `/reports` but differ in `params`. Request `GET /reports?mode=short` picks the first handler; `GET /reports?mode=full` picks the second.

With a request body:

~~~java
@PostMapping(path = "/reports",
             consumes = "application/json",
             produces = "application/json")
ResponseEntity<ReportDto> create(
        @RequestBody CreateReportDto input) {
    // Service logic and return response ...
}
~~~

This is an illustrative fragment missing domain types/services, so it is not a standalone runnable class. `consumes` checks the request body's Content-Type; `produces` checks response capability and the client's Accept header.

**Note:** class-level and method-level annotations have specific condition-combining rules; `consumes`/`produces` on a method can override class-level media type conditions. Do not assume every attribute concatenates or intersects like path strings.

When handler selection fails, the response can be 404, 405, 406, or 415 depending on which condition failed and other mappings/exception handlers. Do not diagnose everything as "wrong URL".

## 5. Annotated controllers pick more specific routes

Suppose two mappings exist:

~~~java
@GetMapping("/products/new")
String newProduct() {
    return "new";
}

@GetMapping("/products/{id}")
String product(@PathVariable String id) {
    return "id:" + id;
}
~~~

Request `GET /products/new` matches both the literal route and the variable pattern. Spring annotated mapping prioritizes `/products/new` because it is more specific than `/products/{id}`. Request `GET /products/42` picks the handler with `{id}`.

**Declaration order of the two methods does not determine priority.** Spring uses a comparison algorithm for request mappings based on path specificity and other conditions. With `PathPatternParser`, literal patterns are generally more specific than variables, while catch-all `/**` is much broader.

One way to constrain a path variable:

~~~java
@GetMapping("/orders/{id:[0-9]+}")
String order(@PathVariable String id) {
    return "order:" + id;
}
~~~

The pattern accepts `/orders/123` and rejects `/orders/new`. If IDs are UUIDs or alphanumeric codes, do not use a digits-only regex. With `PathPatternParser`, catch-alls like `/**` or `/{*path}` have placement rules and generally must appear at the end of the pattern.

### 5.1. Ambiguous mappings cannot be fixed by reordering

Example to avoid declaring in the same controller:

~~~java
@GetMapping("/items/{id}")
String byId(@PathVariable String id) {
    return "id";
}

@GetMapping("/items/{code}")
String byCode(@PathVariable String code) {
    return "code";
}
~~~

Variable names `id` and `code` do not create two structurally distinct matching routes; they are structurally equivalent. Depending on remaining mappings, the framework may detect a conflict at registration or runtime. The fix is to change the design:

~~~text
GET /items/by-id/{id}
GET /items/by-code/{code}
~~~

Routes with clearly distinct conditions are far easier to reason about than hoping whichever method appears first in the file wins.

## 6. Functional routing and RequestPredicate

Spring also supports declaring routes as functions. Key components:

- `RequestPredicate`: determines whether a request matches a condition.
- `HandlerFunction<ServerResponse>`: handles a request and produces a response.
- `RouterFunction<ServerResponse>`: pairs a predicate with a handler.
- `RouterFunctions.route(...)` or the `route()` builder: defines routes.
- `RouterFunctions.nest(...)` or builder `path(...)`: creates nested route groups.
- `and(...)` / `andRoute(...)`: composes routers or branches.

**Use the right package:** Servlet MVC uses `org.springframework.web.servlet.function.*`; reactive WebFlux uses `org.springframework.web.reactive.function.server.*`. The models look alike, yet types from the two stacks are not interchangeable.

Spring MVC functional routing fragment:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/api/status", request ->
                        ServerResponse.ok().body("up"))
                .GET("/api/version", request ->
                        ServerResponse.ok().body("v1"))
                .build();
~~~

The handlers here return `ServerResponse` from the Servlet functional API, not `Mono<ServerResponse>`.

## 7. Grouping paths with path or nest

A catalog API group has URLs:

~~~text
GET /api/v1/catalog/featured
GET /api/v1/catalog/{sku}
~~~

Instead of repeating the prefix in every route:

~~~java
RouterFunction<ServerResponse> catalogRoutes =
        RouterFunctions.route()
                .path("/api/v1/catalog", catalog -> {
                    catalog.GET("/featured", request ->
                            ServerResponse.ok().body("featured"));
                    catalog.GET("/{sku}", request ->
                            ServerResponse.ok().body(
                                    "sku:" + request.pathVariable("sku")));
                })
                .build();
~~~

This is a Spring MVC functional route fragment. Builder `path(...)` applies a shared prefix to the group; child routes declare only the remaining subpath. `RouterFunctions.nest(...)` is also used to group different RequestPredicates and routers; nesting is not mere string concatenation and can combine predicates cleanly.

Route grouping is especially valuable when:

- Separating APIs by module: users, orders, catalog.
- Splitting versions: `/api/v1`, `/api/v2`.
- Grouping admin endpoints: `/internal` with separate security rules.
- Reusing router structures composed via `and`.
- Applying a shared path/header condition to one group.

Nesting does not automatically provide authentication/authorization. Grouped paths are an organizational cue; security must be configured with Spring Security appropriately.

## 8. Ordering in functional routes: first match

This is a crucial difference from annotated mappings. In a functional router, branches are evaluated in composition order. If a broad branch comes first, requests can be captured by it before reaching a specific branch.

**Wrong example:**

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/products/{id}", req ->
                        ServerResponse.ok().body("id:" + req.pathVariable("id")))
                .GET("/products/new", req ->
                        ServerResponse.ok().body("new-product"))
                .build();
~~~

`GET /products/new` matches `/{id}` in the first branch and returns `id:new`. To avoid this:

**Right example:**

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/products/new", req ->
                        ServerResponse.ok().body("new-product"))
                .GET("/products/{id}", req ->
                        ServerResponse.ok().body("id:" + req.pathVariable("id")))
                .build();
~~~

Practical rules:

1. Place exact/literal routes before variable patterns.
2. Place narrow predicates for headers, params, and media types before broad predicates when they intersect.
3. Place catch-all `/**` last and only within the scope actually needed.
4. When composing multiple routers with `and`, verify the order of the combined components.
5. If you need priority across different handler types, inspect `HandlerMapping order` at the higher level; do not confuse first-match **inside a router** with global ordering across all of Spring MVC.

## 9. Runnable Java 17+ example: Spring MVC controller and functional route

This example uses Spring Boot 3.x, `spring-boot-starter-web`, and the default embedded Tomcat. The controller and functional routes use **two separate namespaces** to avoid conflicts.

In the `build.gradle` of a project with the Spring Boot plugin and dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

File **src/main/java/demo/routing/RoutingApplication.java**:

~~~java
package demo.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@SpringBootApplication
public class RoutingApplication {

    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/v1/users")
class UserController {

    @GetMapping("/me")
    String me() {
        return "current-user";
    }

    @GetMapping("/{id}")
    String byId(@PathVariable String id) {
        return "user:" + id;
    }
}

@Configuration(proxyBeanMethods = false)
class CatalogConfiguration {

    @Bean
    RouterFunction<ServerResponse> catalogRoutes() {
        return RouterFunctions.route()
                .path("/api/v1/catalog", catalog -> {
                    catalog.GET("/featured", request ->
                            ServerResponse.ok().body("featured"));
                    catalog.GET("/{sku}", request ->
                            ServerResponse.ok().body(
                                    "sku:" + request.pathVariable("sku")));
                })
                .build();
    }
}
~~~

The public class matches the filename. The other two classes are package-private in the same package, so they are scanned by `@SpringBootApplication`.

Run the project via the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows you can use `gradlew.bat bootRun`. When the application runs on the default port 8080, with no Spring Security or blocking filter, test:

~~~bash
curl -s http://localhost:8080/api/v1/users/me
curl -s http://localhost:8080/api/v1/users/42
curl -s http://localhost:8080/api/v1/catalog/featured
curl -s http://localhost:8080/api/v1/catalog/A7
~~~

Response body of **each command**:

~~~text
current-user
user:42
featured
sku:A7
~~~

The four lines above are shown separately for readability; response bodies do not necessarily contain trailing newlines.

**Why are the results right?** In the controller, literal path `/me` beats variable `/{id}` via annotated mapping specificity. In the functional router, `/featured` appears before `/{sku}`, so the featured catalog request hits the specific handler while an arbitrary SKU falls through to the subsequent handler.

## 10. Testing handler selection order with MockMvc

Verifying only that the router bean was created is not enough. Directly test URLs at risk of overlapping. Add to `build.gradle`:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

File **src/test/java/demo/routing/RoutingApplicationTest.java**:

~~~java
package demo.routing;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class RoutingApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void annotationPicksLiteralRoute() throws Exception {
        mvc.perform(get("/api/v1/users/me"))
                .andExpect(status().isOk())
                .andExpect(content().string("current-user"));

        mvc.perform(get("/api/v1/users/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("user:42"));
    }

    @Test
    void functionalRouterPicksFirstMatchingBranch() throws Exception {
        mvc.perform(get("/api/v1/catalog/featured"))
                .andExpect(status().isOk())
                .andExpect(content().string("featured"));

        mvc.perform(get("/api/v1/catalog/A7"))
                .andExpect(status().isOk())
                .andExpect(content().string("sku:A7"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

`MockMvc` tests the MVC stack without opening a real HTTP socket. With the dependencies and configuration above, the tests verify both literal/variable routing and functional ordering. When you need to test context paths, reverse proxies, or Servlet container network behavior, add `@SpringBootTest(webEnvironment = RANDOM_PORT)` integration tests with an HTTP client.

## 11. HandlerMapping order and overlapping routes across styles

An application can combine annotated controllers, functional routes, and static resources. In that case there are **two levels of decision**:

**Level 1:** DispatcherServlet iterates through HandlerMapping beans by `order` and uses the first handler found.

**Level 2:** Within each strategy, the framework evaluates routes:
- Annotated mapping selects by conditions and specificity.
- Functional router uses composition/nesting and branch order.
- Static resource handlers follow their own URL and resource resolution rules.

Suppose a functional router defines a `/**` fallback, and the application also has an annotated `/api/users` controller. If RouterFunctionMapping is consulted first and the fallback matches, the controller handler may never be reached. Actual behavior depends on the effective HandlerMapping order; do not assume fixed order numbers across every version/configuration.

**Do not use `@Order` on a controller as a substitute for `@GetMapping` specificity.** When you want route priority, write clear patterns/conditions; when using a functional router, organize branch order and avoid overly broad paths.

## 12. WebFlux also has annotated and functional routing

WebFlux annotated controllers have semantics close to MVC for request mapping conditions and specificity:

~~~java
@RestController
@RequestMapping("/api/items")
class ReactiveItemController {

    @GetMapping("/featured")
    Mono<String> featured() {
        return Mono.just("featured");
    }

    @GetMapping("/{id}")
    Mono<String> item(@PathVariable String id) {
        return Mono.just("item:" + id);
    }
}
~~~

This is a fragment requiring imports from Spring WebFlux and Project Reactor. The reactive controller returns `Mono` and is dispatched by `DispatcherHandler`, not Servlet DispatcherServlet when WebFlux runs on Reactor Netty.

### Functional WebFlux example

In a **separate** project using only the WebFlux starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

File **src/main/java/demo/reactive/ReactiveRoutingApplication.java**:

~~~java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@SpringBootApplication
public class ReactiveRoutingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveRoutingApplication.class, args);
    }

    @Bean
    RouterFunction<ServerResponse> catalogRoutes() {
        return RouterFunctions.route()
                .path("/api/v1/catalog", b -> {
                    b.GET("/featured", request ->
                            ServerResponse.ok().bodyValue("featured"));
                    b.GET("/{sku}", request ->
                            ServerResponse.ok().bodyValue(
                                    "sku:" + request.pathVariable("sku")));
                })
                .build();
    }
}
~~~

In WebFlux, `ServerResponse.ok().bodyValue(...)` is a reactive response builder returning `Mono<ServerResponse>` per its API. There is no need to call `block()` to turn it into a Servlet response.

When the app runs, `GET /api/v1/catalog/featured` returns `featured`, and `GET /api/v1/catalog/X9` returns `sku:X9`. The literal route is placed before the variable route to preserve first-match behavior.

**Do not combine MVC and WebFlux examples in the same module assuming both routers register together.** If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath, Spring Boot normally prefers Servlet MVC by default. Verify the actual web application type and server runtime.

## 13. Error statuses that are easily misunderstood

| HTTP status | Common cause |
|---|---|
| 404 | No matching path/handler found or resource does not exist |
| 405 | Path has a mapping, yet the HTTP method is unsupported |
| 406 | `Accept` is incompatible with response `produces` |
| 415 | `Content-Type` is incompatible with `consumes` or body media type |
| 400 | Invalid parameters, binding/validation/body error |
| 401/403 | Authentication/authorization (usually happens before the handler) |
| 500 | Unhandled error or faulty handler/configuration |

These are **typical** outcomes, not absolute guarantees when custom exception handlers, filters, and security are present.

Diagnostic questions in order: what was the actual client request? Was there a proxy/context-path rewrite? Was the request blocked by a filter/security before MVC? Which HandlerMapping picked up the request? Inside a RouterFunction, which branch matched first? Are the media types and HTTP method right?

## 14. PathPatternParser, slashes, and catch-alls

Modern Spring Framework versions generally use `PathPatternParser` for annotated mappings. Compared with legacy Ant matching rules in older projects, there are differences in valid patterns, encoded paths, trailing slashes, and wildcards.

Example:

- `/users/me` is a specific literal path.
- `/users/{id}` matches one path segment.
- `/users/{id:[0-9]+}` accepts a segment matching the numeric regex.
- `/assets/**` is a catch-all for the remaining path under the corresponding configuration.

Do not assume `/users` and `/users/` always match identically, especially when upgrading Spring versions. Depending on configuration, optional trailing slash matching may be disabled. Test both forms with and without slashes if real clients send both.

Certain wildcards/catch-alls in PathPattern are only valid at the end of a pattern. If a route fails to register or matching changes after a Spring upgrade, inspect the matching strategy and pattern syntax rather than only tweaking order.

## 15. Security and route groups

A `/internal/**` path group does not make endpoints secure on its own. Spring Security has its own filter chain and authorization matchers, which can process requests **before** DispatcherServlet or reactive DispatcherHandler. Therefore:

- Do not treat "this route is more specific" as an authorization policy.
- Security matchers and route matchers may use different path mechanisms.
- Behind a reverse proxy or Servlet context path, verify the path that security filters actually see.
- A functional catch-all is not a workaround for handling requests blocked by security.
- Test sensitive routes with both authorized and unauthorized requests.

Place authorization in the proper security mechanism; do not wait for controllers to protect endpoints when filters already should or do run first.

## 16. Inspecting registered routes

If the application includes Actuator, `/actuator/mappings` helps inspect mappings recognized by Spring Boot. Add the dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Expose the endpoint in a test environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,mappings
~~~

After running with the management endpoint on the application port:

~~~bash
curl -s http://localhost:8080/actuator/mappings
~~~

The response may include handler mappings, controllers, and request predicates depending on Boot version. Do not assume a fixed JSON structure. Because this endpoint exposes internal structure, **restrict access** in production.

You can enable Spring MVC/WebFlux logging to see which handler a request maps to. Never log tokens, Authorization headers, cookies, or sensitive content just to debug routing.

## 17. Common mistakes

**Mistake 1 — Applying a prefix twice:** `server.servlet.context-path=/shop` is already set, yet the controller also declares `/shop/api`. The client-visible path duplicates the prefix. Fix it at the right layer.

**Mistake 2 — Assuming controller method order picks the handler:** annotated mappings use a comparison algorithm regardless of source position. Write clear patterns and conditions.

**Mistake 3 — Functional variable route before literal:** `/{id}` swallows `/new` or `/featured`. Place literals first.

**Mistake 4 — Functional catch-all at the top:** `/**` can shadow specific branches and even affect other handlers depending on HandlerMapping order. Put fallbacks last and narrow their prefixes.

**Mistake 5 — Two mappings with different path variable names yet identical structure:** `/{id}` and `/{code}` can cause ambiguity. Separate URLs meaningfully or add distinct conditions.

**Mistake 6 — Confusing 405/406/415 with 404:** inspect the HTTP method, consumes, produces, and client headers, not just the URL.

**Mistake 7 — Confusing MVC functional with WebFlux functional:** identical `RouterFunction` names have different packages and response types. Verify stack/runtime.

**Mistake 8 — Adding both starter-web and starter-webflux and thinking the server is reactive:** Spring Boot normally picks MVC when both are present. Verify the web runtime type.

**Mistake 9 — Relying on route order for security:** requests can be intercepted before handlers; auth policies must be independent and tested.

**Mistake 10 — Testing only one URL:** fails to catch overlapping literal/variable routes. Test intersecting paths along with methods, media types, and fallbacks.

## 18. Implementation checklist

1. Identify whether the application runs Spring MVC/Servlet or Spring WebFlux/Reactive.
2. Identify the exact URL the application receives after ingress, context path, servlet path, or base path.
3. Group controllers cleanly with class-level `@RequestMapping` and method-level mappings.
4. With functional APIs, group paths with `path`/`nest` and compose routers with `and` in intentional order.
5. Place literal routes and specific predicates before variable/catch-all routes in functional routing.
6. Do not rely on source method ordering for annotated mappings.
7. Check `/{id}`, `/me`, regex, and wildcard paths to prevent ambiguity.
8. Clearly distinguish **single-mapping specificity** from **HandlerMapping order**.
9. Test valid URLs, non-existent URLs, wrong methods, unacceptable media types, and denied authentication.
10. Use Actuator mappings/logging safely to diagnose which handler is chosen.
11. Do not mix MVC and WebFlux functional routes without confirming the stack.
12. Run regression tests after any change to modules, version prefixes, or fallback routers.

**Conclusion:** Path grouping helps organize routes by module and version; route composition reduces repeated conditions. Yet when multiple endpoints could match, you must distinguish **annotated mapping specificity**, **functional router first-match**, and **HandlerMapping order**. Designing clear namespaces, keeping specific routes ahead of general ones in functional routers, and testing overlapping paths ensure handler selection stays accurate, predictable, and easy to maintain.
