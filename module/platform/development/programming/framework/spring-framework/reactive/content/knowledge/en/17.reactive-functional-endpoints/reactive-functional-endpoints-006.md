# Grouping Routes with nest and Managing Matching Order in Spring WebFlux.fn

## 1. Why Are Nested Routes Needed?

In Spring WebFlux.fn, **RouterFunction** maps requests to **HandlerFunction**. Many endpoints often share conditions such as the path prefix \`/api/v1/users\`, the \`Accept: application/json\` header, the \`Content-Type: application/json\` body type, a tenant, or an API version. Repeating those conditions on every route makes the configuration long and easy to drift out of sync.

**Nested routes** group routes together, place the shared predicate on the outside, and declare child routes inside:

~~~text
/api/v1
   |
   +-- Accept: application/json
   |      +-- GET /users/search
   |      +-- GET /users/{id}
   |      +-- POST /users
   |
   +-- GET /health
~~~

The \`/api/v1\` prefix applies to all routes in the group. The Accept JSON predicate applies only to the users group. The health route still belongs to the API prefix but is not constrained by the JSON predicate.

You need to understand two things at once: **nest** groups routes with shared predicates; **route order** decides which route is chosen first when multiple patterns can match the same request.

## 2. RouterFunction and RequestPredicate

### 2.1. What is a RouterFunction?

In WebFlux.fn:

- **ServerRequest** represents the HTTP request at the functional layer.
- **HandlerFunction<T extends ServerResponse>** receives a ServerRequest and returns a Mono of ServerResponse.
- **RouterFunction<T>** receives a ServerRequest and returns a Mono containing a HandlerFunction if the route matches; if it does not match, it completes empty.

~~~text
ServerRequest
     |
     v
RouterFunction
     |
     +-- match -------> Mono<HandlerFunction>
     |
     +-- no match ----> Mono.empty()
~~~

RouterFunction selects the handler; HandlerFunction executes the business logic and creates the ServerResponse. RouterFunction should not query the database or perform I/O.

### 2.2. RequestPredicate

**RequestPredicate** is the condition that checks whether a request fits a route. Common predicates in \`RequestPredicates\`:

| Predicate | Meaning |
| --- | --- |
| \`GET(path)\`, \`POST(path)\`, \`PUT(path)\`, \`DELETE(path)\` | Checks HTTP method and path |
| \`method(HttpMethod)\` | Checks HTTP method |
| \`path(pattern)\` | Checks path against pattern |
| \`accept(mediaType)\` | Checks the client's Accept header |
| \`contentType(mediaType)\` | Checks the request's Content-Type |
| \`queryParam(name, predicate)\` | Checks a query parameter |
| \`headers(predicate)\` | Checks a condition on headers |

Example:

~~~java
RouterFunctions.route()
        .GET("/products/{id}",
                RequestPredicates.accept(MediaType.APPLICATION_JSON),
                handler::find)
        .build();
~~~

The route must satisfy the GET method, a matching path, and the Accept JSON predicate. The builder's GET overload automatically combines method/path with the additional predicate.

### 2.3. Combining predicates

RequestPredicate supports:

- **\`RequestPredicate.and(RequestPredicate)\`**: both predicates must be true.
- **\`RequestPredicate.or(RequestPredicate)\`**: at least one predicate is true.
- **\`RequestPredicate.negate()\`**: inverts the predicate result.

~~~java
RequestPredicate apiJson =
        RequestPredicates.path("/api/**")
                .and(RequestPredicates.accept(MediaType.APPLICATION_JSON));

RequestPredicate notHealth =
        RequestPredicates.path("/health").negate();
~~~

When using \`nest(apiJson, ...)\`, child routes are only considered if both the API path and Accept JSON match.

Distinguish the two headers: **Accept** indicates the media type the client wants to receive; **Content-Type** indicates the media type of the request body being sent. For a JSON POST, you may need to check both.

## 3. path(...) — Grouping by Path Prefix

### 3.1. Basic example

~~~java
RouterFunction<ServerResponse> userRoutes = RouterFunctions.route()
        .path("/users", users -> users
                .GET("/{id}", handler::find)
                .GET("", handler::list)
                .POST(handler::create))
        .build();
~~~

This is an illustrative snippet with an existing handler. The child routes are joined onto the shared prefix:

| Inner route | Actual URL |
| --- | --- |
| \`GET("/{id}")\` | \`GET /users/{id}\` |
| \`GET("")\` | \`GET /users\` |
| \`POST(handler::create)\` | \`POST /users\` |

**\`path(String, Consumer<RouterFunctions.Builder>)\`** is a convenient way to create a group of routes sharing a prefix. The Consumer receives a builder to declare child routes.

### 3.2. Multi-level prefixes

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .path("/api", api -> api
                .path("/v1", v1 -> v1
                        .path("/users", users -> users
                                .GET("/{id}", handler::find)
                                .GET("", handler::list))))
        .build();
~~~

The final URLs are \`GET /api/v1/users\` and \`GET /api/v1/users/{id}\`. Nesting should reflect domain structure; avoid nesting too many levels if it only makes the code harder to read.

### 3.3. path is a specialized form of nest

\`path("/users", builder -> ...)\` is convenient syntax for a group of routes with a shared path predicate. When you need to group by a condition other than path, use \`nest(RequestPredicate, Consumer<RouterFunctions.Builder>)\`.

## 4. nest(...) — Grouping by Any Predicate

### 4.1. Grouping by Accept header

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .nest(RequestPredicates.accept(MediaType.APPLICATION_JSON), json -> json
                .GET("/users", handler::list)
                .GET("/users/{id}", handler::find)
                .POST("/users", handler::create))
        .build();
~~~

The routes in the group are only evaluated when the Accept JSON predicate matches. This avoids repeating the predicate on every route.

### 4.2. Combining path and header

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .path("/api/v1", api -> api
                .nest(RequestPredicates.accept(MediaType.APPLICATION_JSON), json -> json
                        .GET("/users", handler::list)
                        .GET("/users/{id}", handler::find)))
        .build();
~~~

For a child route to be selected, the request must satisfy the \`/api/v1\` prefix, Accept JSON, method, and child path. Logically, the predicates are combined with an AND relationship.

### 4.3. Grouping by a custom predicate

~~~java
RequestPredicate internalClient = request ->
        request.headers().header("X-Client-Type").contains("internal");

RouterFunction<ServerResponse> internalRoutes =
        RouterFunctions.route()
                .nest(internalClient, internal -> internal
                        .GET("/reports", handler::listInternal))
                .build();
~~~

This is an illustrative snippet with an existing handler. Custom predicates should be **fast, deterministic, and side-effect-free**. Do not query a database or make blocking HTTP calls during route matching.

You can use the static \`RouterFunctions.nest(predicate, routerFunction)\` to nest an already created router; or use the builder's \`nest(predicate, consumer)\` to build the child router inline. The builder approach is usually easier to read when declaring application routes.

## 5. Managing Matching Order: First Match

### 5.1. Routes are evaluated in composition order

In WebFlux.fn:

1. Check the first route.
2. If the route does not match, move to the next route.
3. Stop at the first route that finds a HandlerFunction.
4. If no route matches, RouterFunction does not supply a handler.

Therefore, declare **specific routes before general routes**.

This differs from annotated controllers. With annotation-based mapping, Spring picks the best-fitting mapping based on matching conditions and specificity. With WebFlux.fn, do not rely on automatic selection of the most specific route; composition order is what you need to manage.

### 5.2. Static routes and path-variable routes

Wrong example:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .GET("/users/{id}", handler::find)
        .GET("/users/search", handler::search)
        .build();
~~~

A \`GET /users/search\` request can also match the \`/users/{id}\` pattern with \`id = "search"\`. Because the variable route is declared first, the find handler can be selected and the search route after it is not evaluated.

Correct approach:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .GET("/users/search", handler::search)
        .GET("/users/{id}", handler::find)
        .build();
~~~

The static \`/users/search\` route is evaluated first; the variable route receives the remaining matching paths.

### 5.3. Specific routes and wildcards

Suppose there are \`GET /files/latest\`, \`GET /files/{name}\`, and \`GET /files/**\`. You should declare:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .GET("/files/latest", handler::latest)
        .GET("/files/{name}", handler::byName)
        .GET("/files/**", handler::underDirectory)
        .build();
~~~

The most specific route goes first, and the broadest route goes last. If the wildcard comes first, it can catch requests that a specialized handler should process.

### 5.4. Combining multiple RouterFunctions

~~~java
RouterFunction<ServerResponse> publicRoutes = RouterFunctions.route()
        .GET("/public/status", handler::status)
        .build();

RouterFunction<ServerResponse> adminRoutes = RouterFunctions.route()
        .GET("/admin/status", handler::adminStatus)
        .build();

RouterFunction<ServerResponse> allRoutes =
        publicRoutes.and(adminRoutes);
~~~

If publicRoutes cannot find a handler, the next router is evaluated. If publicRoutes has already matched, adminRoutes does not replace that handler. The builder also supports \`add\` and \`andRoute\`. Internally in Spring, RouterFunctionMapping combines router beans in order via **\`RouterFunction.andOther(...)\`**.

## 6. Order Within Nested Routes

### 6.1. Child routes still preserve declaration order

~~~java
.path("/api/v1", api -> api
        .path("/users", users -> users
                .GET("/search", handler::search)
                .GET("/{id}", handler::find)
                .GET("/**", handler::fallback)))
~~~

The order in the users group is \`/search\`, \`/{id}\`, then \`/**\`. The prefix only adds a shared condition; it does not automatically sort child routes by specificity.

### 6.2. Routes outside the group and routes inside the group

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .path("/api/v1", api -> api
                .GET("/health", handler::health)
                .path("/users", users -> users
                        .GET("/search", handler::search)
                        .GET("/{id}", handler::find)))
        .GET("/health", handler::rootHealth)
        .build();
~~~

The \`/api/v1/health\` and \`/health\` routes have different paths so they do not conflict. If groups have overlapping predicates, read the composition order and test representative requests. Do not assume nested routes always take precedence over top-level routes or vice versa in every structure.

### 6.3. When the group predicate does not match

If the outer predicate of nest does not match, the child routes are not evaluated. For example, an Accept JSON group is not selected when the Accept header does not satisfy the predicate. If the application needs an explicit response for an unsupported media type, design a suitable fallback route or error-handling mechanism; do not assume every predicate mismatch automatically produces HTTP 406.

## 7. Order Between Multiple RouterFunction Beans

In Spring WebFlux configuration, **RouterFunctionMapping** detects RouterFunction beans, sorts them, and combines them into a composite RouterFunction. When splitting routes into multiple beans, the order between beans can also affect which route is chosen first.

~~~java
@Configuration
class RouteConfiguration {

    @Bean
    @Order(0)
    RouterFunction<ServerResponse> specificRoutes(SpecificHandler handler) {
        return RouterFunctions.route()
                .GET("/reports/latest", handler::latest)
                .build();
    }

    @Bean
    @Order(10)
    RouterFunction<ServerResponse> generalRoutes(GeneralHandler handler) {
        return RouterFunctions.route()
                .GET("/reports/{id}", handler::find)
                .build();
    }
}
~~~

This is an illustrative configuration snippet. \`@Order(0)\` is ordered before \`@Order(10)\`; specific routes are composed before general routes.

Recommendations:

- Related routes that can easily overlap should live in one builder so the order is visible in one place.
- If splitting into multiple beans by module, set \`@Order\` explicitly when order matters.
- Do not rely on bean initialization order or method names to infer precedence.
- Avoid leaving two beans with the same order containing overlapping routes if the order between them is not explicitly designed.
- Use integration tests for routes that may overlap.

## 8. Nested Routes and Filters: Scope of Application

The router builder provides three ways to process across routes:

| API | Role |
| --- | --- |
| \`before(...)\` | Transforms ServerRequest before calling the handler |
| \`after(...)\` | Transforms or observes ServerResponse after the handler creates the response |
| \`filter(...)\` | Wraps the next HandlerFunction; can allow or block calling the handler |

### 8.1. before: handling the request before the handler

ServerRequest has an immutable contract. If you want to add a header to the request passed to the handler, create a new request:

~~~java
.before(request -> ServerRequest.from(request)
        .header("X-Route-Scope", "users")
        .build())
~~~

This is an illustrative snippet. When \`before\` is placed in a nested route's builder, it only applies to routes created within that builder. Other sibling or top-level routes do not automatically receive this transformation.

### 8.2. after: handling the response after the handler

~~~java
.after((request, response) -> {
    logResponse(request.path(), response.statusCode());
    return response;
})
~~~

This is an illustrative snippet with the application's logResponse function. \`after\` takes the request and response, then returns the processed response. When placed on the outermost builder, the filter applies to all routes created by that builder, including nested routes inside.

### 8.3. filter and HandlerFilterFunction

The \`filter(...)\` API takes a **HandlerFilterFunction**. The filter function receives the ServerRequest and the next HandlerFunction, and returns a Publisher of ServerResponse:

~~~java
.filter((request, next) -> {
    if (accessPolicy.allow(request)) {
        return next.handle(request);
    }
    return ServerResponse.status(HttpStatus.UNAUTHORIZED).build();
})
~~~

This is an illustrative snippet with an application-supplied accessPolicy. If the condition is not met, the filter returns a response without calling \`next.handle(request)\`. If the condition is met, it forwards the request to the next filter/handler.

Route-level filters are useful for logic that applies only to a group of functional routes. For overall application security, consider Spring Security and the WebFilter chain; do not use a demo header as a production security solution.

### 8.4. Filters in nested builders and outer builders

~~~java
RouterFunctions.route()
        .path("/api/v1", api -> api
                .path("/users", users -> users
                        .GET("/{id}", handler::find)
                        .before(this::addUserHeader))
                .GET("/health", handler::health))
        .after(this::logAllResponses)
        .build();
~~~

- \`before(addUserHeader)\` is placed in the users group so it only applies to routes created in the users group.
- \`after(logAllResponses)\` is placed on the outer builder so it applies to all routes created by the builder, including users and health.

Filter scope is determined by where it is placed in the builder. When moving a filter into or out of a nested group, re-check which routes are affected.

## 9. Predicate Mismatch, 404, and Content Errors

A predicate mismatch means that route was not selected. It does not mean the handler ran and returned an error response.

| Scenario | Meaning |
| --- | --- |
| Path does not match nest prefix | The route group is not evaluated |
| Method does not match | The route is not selected |
| Accept predicate does not match | The route requiring that media type is not selected |
| Content-Type predicate does not match | The route requiring that body type is not selected |
| Handler is called and returns ServerResponse.notFound() | The handler deliberately creates HTTP 404 |
| No route matches after evaluating all RouterFunctions | No matching functional handler; the framework/application's not-found handling determines the final response |

If the API needs to distinguish **404 Not Found** from **405 Method Not Allowed**, or **406 Not Acceptable** from **415 Unsupported Media Type**, design clear fallback/error handling and test against the HTTP contract. Do not rely on simply adding a predicate for the framework to guarantee returning the right business status in every configuration.

## 10. Runnable Java 17+ Example: Nested Routes and Route Order

The example builds a Spring Boot WebFlux app with a shared prefix \`/api/v1\`, a users group that only accepts Accept JSON, a static search route before the dynamic id route, and a health route outside the nested Accept predicate.

### 10.1. Project structure

~~~text
webflux-nested-routes/
├── pom.xml
└── src/
    ├── main/java/example/routes/
    │   ├── DemoApplication.java
    │   └── ApiRoutes.java
    └── test/java/example/routes/
        └── ApiRoutesTest.java
~~~

### 10.2. pom.xml

The example uses Spring Boot **3.5.5** and Java 17+:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-nested-routes</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 10.3. DemoApplication.java

~~~java
package example.routes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.4. ApiRoutes.java

~~~java
package example.routes;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.reactive.function.server.RequestPredicates;

import reactor.core.publisher.Mono;

@Configuration
public class ApiRoutes {

    @Bean
    RouterFunction<ServerResponse> apiRoutes() {
        return RouterFunctions.route()
                .path("/api/v1", api -> api
                        .nest(RequestPredicates.accept(MediaType.APPLICATION_JSON),
                                json -> json
                                        .GET("/users/search", this::searchUsers)
                                        .GET("/users/{id}", this::findUser))
                        .GET("/health", this::health))
                .build();
    }

    private Mono<ServerResponse> searchUsers(ServerRequest request) {
        String query = request.queryParam("q").orElse("");

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("route", "search", "query", query));
    }

    private Mono<ServerResponse> findUser(ServerRequest request) {
        String id = request.pathVariable("id");

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("route", "user", "id", id));
    }

    private Mono<ServerResponse> health(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("UP");
    }
}
~~~

Points to observe:

- \`path("/api/v1", ...)\` creates a shared prefix.
- \`nest(accept(APPLICATION_JSON), ...)\` applies Accept JSON to the users routes.
- \`GET("/users/search")\` comes before \`GET("/users/{id}")\`, so the search keyword is not interpreted as an id.
- \`GET("/health")\` sits outside the nested Accept predicate but still inside the /api/v1 prefix.
- Handlers return Mono<ServerResponse>; do not call subscribe() or block() in routes.

### 10.5. Running the application

In the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Search users:

~~~bash
curl -i -H "Accept: application/json" "http://localhost:8080/api/v1/users/search?q=reactor"
~~~

The response has status **200 OK** and JSON containing:

~~~json
{
  "route": "search",
  "query": "reactor"
}
~~~

Get user by id:

~~~bash
curl -i -H "Accept: application/json" "http://localhost:8080/api/v1/users/42"
~~~

The response has status **200 OK** and JSON containing:

~~~json
{
  "route": "user",
  "id": "42"
}
~~~

Health endpoint:

~~~bash
curl -i http://localhost:8080/api/v1/health
~~~

Body:

~~~text
UP
~~~

The order of keys in JSON is not a routing contract.

### 10.6. Testing route order with WebTestClient

File **ApiRoutesTest.java**:

~~~java
package example.routes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ApiRoutesTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void staticSearchRouteWinsBeforePathVariableRoute() {
        webTestClient.get()
                .uri("/api/v1/users/search?q=reactor")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.route").isEqualTo("search")
                .jsonPath("$.query").isEqualTo("reactor");
    }

    @Test
    void pathVariableRouteReceivesUserId() {
        webTestClient.get()
                .uri("/api/v1/users/42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.route").isEqualTo("user")
                .jsonPath("$.id").isEqualTo("42");
    }

    @Test
    void healthRouteIsOutsideJsonNestedPredicate() {
        webTestClient.get()
                .uri("/api/v1/health")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("UP");
    }
}
~~~

Run tests:

~~~bash
mvn test
~~~

The three tests confirm that the static search route is selected instead of the id variable route, the variable route handles normal user URLs, and health shares the prefix without being constrained by nested Accept JSON.

## 11. Common Mistakes and How to Fix Them

### 11.1. General route placed before specific route

**Wrong:**

~~~java
RouterFunctions.route()
        .GET("/orders/{id}", handler::find)
        .GET("/orders/search", handler::search)
        .build();
~~~

**Correct:**

~~~java
RouterFunctions.route()
        .GET("/orders/search", handler::search)
        .GET("/orders/{id}", handler::find)
        .build();
~~~

If the order is not fixed, the search keyword may be treated as an id.

### 11.2. Repeating prefixes and predicates

**Hard to maintain:**

~~~java
RouterFunctions.route()
        .GET("/api/v1/users", acceptJson, handler::list)
        .GET("/api/v1/users/{id}", acceptJson, handler::find)
        .POST("/api/v1/users", acceptJson, handler::create)
        .build();
~~~

**Easier to read:**

~~~java
RouterFunctions.route()
        .path("/api/v1", api -> api
                .nest(acceptJson, json -> json
                        .GET("/users", handler::list)
                        .GET("/users/{id}", handler::find)
                        .POST("/users", handler::create)))
        .build();
~~~

Nesting reduces duplication and lets you change the prefix/predicate in one place.

### 11.3. Placing a predicate at the wrong level

If you put Accept JSON on the outermost builder, every route created in that builder may have the JSON condition applied, including health or routes returning text/plain. Place predicates at the right scope: the JSON group inside nest, text health on a sibling route outside the JSON group, and upload groups by appropriate Content-Type.

### 11.4. Confusing Accept and Content-Type

A JSON body POST usually needs to check the request's Content-Type; a JSON response needs to check the Accept sent by the client. The two predicates can be combined, but they do not replace each other.

### 11.5. Multiple RouterFunction beans without setting order

If two beans have overlapping routes, RouterFunctionMapping combines them in bean order. Use \`@Order\` or group related routes into one builder and test precedence; do not rely on unclear initialization order.

### 11.6. Custom predicate performing I/O or having side effects

Predicates are used during route lookup. Do not call a database, remote service, or blocking operations inside a predicate. Let the handler execute business logic after the route is selected.

## 12. Route Order Debugging and Design Checklist

A readable route order is typically:

1. Special static routes: \`/search\`, \`/summary\`, \`/latest\`, \`/health\`.
2. Routes with path variables: \`/{id}\`, \`/{id}/history\`.
3. Wildcard/catch-all routes: \`/**\` or resource fallback.
4. Fallback route if the application explicitly needs a custom response.

When a route goes wrong, check:

- Path, context path, prefix, slashes, and path variables.
- HTTP method.
- Outer nest and inner predicates.
- Accept, Content-Type, query parameters, and custom conditions.
- Whether variable/wildcard routes come before static routes.
- RouterFunction composition and add/and order.
- @Order when there are multiple RouterFunction beans.
- Filter scope: which builder level before/filter/after is placed at.
- Response status, content type, body, and deferred errors.
- Boundary test requests: static, variable, unmatched path, wrong method, and unsuitable headers.

You can enable selective logging for WebFlux packages in the development environment. Do not turn on broad DEBUG in production if logs may contain sensitive request information.

## 13. Quick Comparison with Annotated Controllers

| Topic | WebFlux.fn | Annotated controller |
| --- | --- | --- |
| Route declaration | RouterFunction builder | @RequestMapping, @GetMapping... |
| Prefix grouping | path(...) or nest(path(...)) | @RequestMapping on class |
| Predicate grouping | nest(RequestPredicate, ...) | Mapping conditions/annotations |
| Handler | HandlerFunction | Controller method |
| Order | Route composition first-match | Spring selects the best-fitting mapping by conditions |
| Per-route filter | before/after/filter on builder | WebFilter, ControllerAdvice and corresponding mechanisms |
| Style | Functional, routes and handlers clearly separated | Annotation-driven |

Both belong to Spring WebFlux and can coexist. You should not convert all controllers to functional just to use nest; annotated controllers already have a way to group prefixes with class-level @RequestMapping.

## 14. Key Takeaways

- **path(prefix, builder)** groups routes that share a path prefix.
- **nest(predicate, builder)** groups routes that share any RequestPredicate, not just path.
- **RequestPredicate.and/or/negate** helps combine route conditions.
- Nested routes are only evaluated when the group predicate matches; child routes still preserve declaration order.
- **RouterFunction routes are evaluated in composition order**. Place static/specific routes before path-variable and wildcard routes.
- Multiple RouterFunction beans are sorted and combined by RouterFunctionMapping via RouterFunction.andOther; set @Order when order between beans matters.
- Filters placed inside a nested builder apply only to the corresponding route scope; filters on an outer builder can apply to nested routes as well.
- Do not perform I/O or business logic inside a RequestPredicate.
- Test route precedence with WebTestClient to prevent regressions when adding endpoints.

**Official documentation:**
- [Spring Framework — Functional Endpoints (WebFlux.fn): predicates, route order, nested routes, and filters](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework Javadoc — RouterFunctions.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.Builder.html)
- [Spring Framework Javadoc — RouterFunctionMapping](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/support/RouterFunctionMapping.html)
- [Spring Framework Javadoc — RequestPredicates](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/RequestPredicates.html)
- [Spring Framework Reference — DispatcherHandler and WebFlux infrastructure](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)
