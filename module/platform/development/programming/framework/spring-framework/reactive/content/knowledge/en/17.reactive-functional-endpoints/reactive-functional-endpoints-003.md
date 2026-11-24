# Combining Path, Method, Header, and Media Type Predicates in Spring WebFlux

## 1. What Is a Request Predicate in WebFlux.fn?

In Spring WebFlux's **functional endpoints** model, we route HTTP requests using `RouterFunction` instead of declaring `@RequestMapping` on a controller. A `RouterFunction` inspects the request and selects the corresponding `HandlerFunction`. The condition for a route to match is represented by a **`RequestPredicate`**.

A predicate takes a `ServerRequest` and returns a true/false result. Spring provides built-in predicates in `RequestPredicates`, allowing you to check:

- **Path:** is the request going to `/api/reports/42`, `/users/{id}`, or a matching pattern?
- **HTTP method:** GET, POST, PUT, PATCH, DELETE, OPTIONS...
- **Header:** does the request send `X-API-Version: v1`, `X-Client: partner`, or a matching header value?
- **Media type:** is the `Content-Type` of the request body JSON, or does `Accept` accept JSON?

A route often requires **multiple conditions to be true together**. For example: only accept `GET /api/reports/{id}` when the client sends the version header `X-API-Version: v1` and accepts a JSON response.

General model:

~~~text
HTTP request
    |
    v
RequestPredicate
    |
    +-- path matches?
    +-- method is right?
    +-- header meets condition?
    +-- media type is compatible?
    |
    +-- All conditions true --> HandlerFunction
    |
    +-- No match -------------> Router tries the next route
~~~

`RequestPredicate` only decides **which route is selected**. It is not a handler that reads the body, does not create a response on its own, and does not replace validation, authorization, or business processing.

## 2. Components in a Functional Endpoint

A functional endpoint has three main components:

| Component | Responsibility | Typical type |
| --- | --- | --- |
| `ServerRequest` | Represents the HTTP request: method, URI, path variables, headers, query params, and body | `ServerRequest` |
| `RequestPredicate` | Checks whether the request satisfies the routing condition | `RequestPredicate` |
| `HandlerFunction` | Handles the request selected by the route and creates a reactive response | `HandlerFunction<ServerResponse>` |

A handler function takes a `ServerRequest` and returns a `Mono<ServerResponse>`. The request and response have an immutable API; the body is represented using the reactive model. Example of reading a JSON body:

~~~java
Mono<CreateReportRequest> body =
    request.bodyToMono(CreateReportRequest.class);
~~~

A direct route can be created with:

~~~java
RouterFunction<ServerResponse> route =
    RouterFunctions.route(
        RequestPredicates.GET("/api/reports/{id}"),
        handler::getReport
    );
~~~

This is an illustrative snippet that requires `handler` and the `getReport` method in the application. With multiple routes, you typically use the `RouterFunctions.route()` builder or combine `RouterFunction` instances with `and`.

## 3. Path Predicate: path

`RequestPredicates.path(String)` creates a predicate that checks the request path against a pattern. Spring WebFlux uses a path pattern mechanism to support path variables and matching patterns.

Example:

~~~java
RequestPredicate reportPath = path("/api/reports/{id}");
RequestPredicate allReports = path("/api/reports/**");
RequestPredicate healthPath = path("/health");
~~~

The patterns above are examples of paths:

- `/api/reports/{id}` matches a dynamic segment, such as `/api/reports/42`.
- `/api/reports/**` is used to group sub-paths under the reports prefix.
- `/health` matches a specific health path.

When the route has matched, the handler gets the path variable with:

~~~java
public Mono<ServerResponse> getReport(ServerRequest request) {
    String id = request.pathVariable("id");

    return ServerResponse.ok()
        .bodyValue(Map.of("id", id));
}
~~~

If there are multiple path variables, you can read each variable by name or get a map via `request.pathVariables()`. A path variable is part of the URI path, unlike a query parameter such as `?page=2`.

You can combine a path predicate with another condition:

~~~java
RequestPredicate reportRead =
    path("/api/reports/{id}")
        .and(method(HttpMethod.GET));
~~~

The predicate only matches when **both path and method** are right. If the path is right but the method is wrong, the combined predicate still returns false.

## 4. HTTP Method Predicate

`RequestPredicates.method(HttpMethod)` checks one HTTP method. `methods(HttpMethod...)` lets you accept one of multiple methods. Shortcuts like `GET(path)`, `POST(path)`, `PUT(path)` already combine the method condition with the path.

Example:

~~~java
RequestPredicate getOnly = method(HttpMethod.GET);
RequestPredicate writeMethods =
    methods(HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH);
~~~

Some equivalent ways of writing:

~~~java
// Shortcut: method GET + path /reports/{id}.
.GET("/reports/{id}", handler::getReport)

// Explicit form:
.route(
    path("/reports/{id}").and(method(HttpMethod.GET)),
    handler::getReport
)
~~~

Shortcuts in the router builder make code shorter, while explicit predicate composition is suitable when you need to add multiple conditions or reuse a predicate.

### Do not confuse route predicates with HTTP authorization

A method predicate only checks whether the request uses GET/POST/... or not. It does not verify that the caller has permission to perform the action. A matching POST route does not mean the user is allowed to create data; authentication/authorization checks must be performed with Spring Security or an appropriate security mechanism.

## 5. Header Predicate: headers(...)

`RequestPredicates.headers(Predicate<ServerRequest.Headers>)` lets you write custom conditions on request headers.

Example requiring the client to send the API version:

~~~java
RequestPredicate apiV1 =
    headers(headers ->
        "v1".equals(headers.firstHeader("X-API-Version"))
    );
~~~

`firstHeader(name)` returns the first header value or `null` if absent. Writing comparisons in the form `"expected".equals(actual)` helps avoid a `NullPointerException` when the client does not send the header.

Some other examples:

~~~java
RequestPredicate trustedClient =
    headers(headers ->
        "partner".equals(headers.firstHeader("X-Client"))
    );

RequestPredicate hasTraceId =
    headers(headers ->
        headers.firstHeader("X-Trace-Id") != null
    );

RequestPredicate internalChannel =
    headers(headers ->
        List.of("internal", "batch")
            .contains(headers.firstHeader("X-Channel"))
    );
~~~

A predicate can check multiple headers in the same lambda:

~~~java
RequestPredicate partnerV1 =
    headers(headers ->
        "partner".equals(headers.firstHeader("X-Client"))
            && "v1".equals(headers.firstHeader("X-API-Version"))
    );
~~~

HTTP header names are case-insensitive according to HTTP rules. Header values are compared according to the logic defined by the application; do not automatically assume every value must be converted to lowercase.

**Security warning:** custom headers such as `X-Client`, `X-Role`, or `X-API-Key` can be sent by the client itself. Use header predicates to select a route or classify requests, but **do not use a client-declared header as proof of authorization**. If you need to verify identity, use Spring Security, a verified token, or an equivalent trusted mechanism.

## 6. Media Type Predicates: Distinguishing Content-Type and Accept

The two media type headers have different purposes:

| Header | Meaning | Corresponding predicate |
| --- | --- | --- |
| `Content-Type` | The content type the client is sending in the request body | `contentType(MediaType...)` |
| `Accept` | The response type the client wants to receive | `accept(MediaType...)` |

### contentType(...)

`contentType(MediaType.APPLICATION_JSON)` checks whether the request body's media type matches one of the declared types.

~~~java
RequestPredicate jsonBody =
    contentType(MediaType.APPLICATION_JSON);

RequestPredicate jsonOrNdjson =
    contentType(
        MediaType.APPLICATION_JSON,
        MediaType.APPLICATION_NDJSON
    );
~~~

Use this predicate for routes that accept a JSON/NDJSON body, such as POST or PUT. Do not mechanically apply `contentType` to a GET request that has no body.

### accept(...)

`accept(MediaType.APPLICATION_JSON)` checks whether the client's `Accept` header is compatible with a JSON response.

~~~java
RequestPredicate wantsJson =
    accept(MediaType.APPLICATION_JSON);

RequestPredicate wantsJsonOrText =
    accept(
        MediaType.APPLICATION_JSON,
        MediaType.TEXT_PLAIN
    );
~~~

Example of a route that only serves JSON:

~~~java
.GET(
    "/reports/{id}",
    accept(MediaType.APPLICATION_JSON),
    handler::getReport
)
~~~

### Practical example: client sends JSON and wants JSON back

A POST request can carry at the same time:

~~~http
POST /api/reports
Content-Type: application/json
Accept: application/json
X-Client: partner
~~~

The route can require all of `contentType(APPLICATION_JSON)`, `accept(APPLICATION_JSON)`, and the matching client header. If one condition is missing, the route does not match.

**Do not confuse a predicate with a codec:** a predicate only checks metadata to select a handler. Actually decoding JSON into a Java object is still handled by `ServerRequest.bodyToMono(...)` and the message reader/codec inside the handler. A Content-Type accepted by the route does not guarantee a valid JSON body; a malformed body can still emit a decode error.

## 7. Combining Conditions with and, or, and negate

`RequestPredicate` supports logical operations:

| Method | Meaning | Example |
| --- | --- | --- |
| `and(other)` | Both the current predicate and the other predicate must be true | Path AND GET AND header |
| `or(other)` | At least one of the two predicates is true | Internal header OR partner header |
| `negate()` | Inverts the predicate result | Not under the internal path |

### Using and when every condition is required

~~~java
RequestPredicate readJsonReport =
    path("/api/reports/{id}")
        .and(method(HttpMethod.GET))
        .and(headers(h ->
            "v1".equals(h.firstHeader("X-API-Version"))))
        .and(accept(MediaType.APPLICATION_JSON));
~~~

Equivalent condition:

~~~text
path matches
AND method = GET
AND X-API-Version = v1
AND Accept is compatible with application/json
------------------------------------------
                 MATCH
~~~

If even one condition is false, the route is not selected.

### Using or when multiple options are valid

~~~java
RequestPredicate allowedChannel =
    headers(h -> "internal".equals(h.firstHeader("X-Channel")))
        .or(headers(h ->
            "partner".equals(h.firstHeader("X-Channel"))));
~~~

The predicate above allows either channel. When combining with other conditions, use parentheses or create an intermediate variable so the code clearly expresses the OR group:

~~~java
RequestPredicate statusRoute =
    path("/api/status")
        .and(method(HttpMethod.GET))
        .and(allowedChannel)
        .and(accept(MediaType.TEXT_PLAIN));
~~~

### Using negate to exclude

~~~java
RequestPredicate notInternal =
    path("/internal/**").negate();

RequestPredicate publicGet =
    method(HttpMethod.GET).and(notInternal);
~~~

This example is only a routing condition. It does not replace security rules; "not under /internal" should not be treated as sufficient to grant access.

## 8. Combining Multiple Predicates and Registering Routes

There are two common approaches.

### Approach 1: RouterFunctions.route(predicate, handler)

This approach is suitable when you have already built a complete predicate:

~~~java
RequestPredicate predicate =
    path("/api/reports/{id}")
        .and(method(HttpMethod.GET))
        .and(accept(MediaType.APPLICATION_JSON));

RouterFunction<ServerResponse> route =
    RouterFunctions.route(predicate, handler::getReport);
~~~

### Approach 2: RouterFunctions.route() builder

The builder has shortcuts by HTTP method and path, and also accepts additional predicates:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET(
            "/api/reports/{id}",
            accept(MediaType.APPLICATION_JSON),
            handler::getReport
        )
        .POST(
            "/api/reports",
            contentType(MediaType.APPLICATION_JSON),
            handler::createReport
        )
        .build();
~~~

In the GET route, the builder combines the path and the GET method with the Accept JSON predicate. In the POST route, the builder combines the path and the POST method with the Content-Type JSON predicate.

### Nesting routes with shared conditions

If multiple routes share a prefix or a header condition, you can use nested routes to avoid repetition:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .path("/api/reports", reports -> reports
            .nest(
                headers(h ->
                    "v1".equals(h.firstHeader("X-API-Version"))),
                versioned -> versioned
                    .GET("/{id}", handler::getReport)
                    .GET("", handler::listReports)
            )
            .POST(
                contentType(MediaType.APPLICATION_JSON),
                handler::createReport
            )
        )
        .build();
~~~

In the example above, the `/api/reports` path prefix is shared. The two GET routes are in the group requiring the v1 version header; POST has its own Content-Type predicate. Nested routes help group shared conditions, but you must clearly understand the scope: an outer predicate applies to all child routes; a predicate on one nested branch applies only to that branch.

## 9. Route Declaration Order and Handling When No Route Matches

A `RouterFunction` is evaluated **in declaration/composition order**. When a route does not match, the router can try the next route. Therefore, place specific routes before general routes.

Example:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/api/reports/summary", handler::summary)
        .GET("/api/reports/{id}", handler::getReport)
        .GET("/api/reports/**", handler::fallback)
        .build();
~~~

If a general route is placed first, it can catch the request before the specific route is checked. This differs from the annotation-based controller model, where Spring chooses the matching mapping according to its own specificity rules.

When a predicate does not match, that route does not invoke the handler. If none of the routers match, the request continues through the application's dispatch mechanism; the final outcome is usually 404 if no other handler/resource matches. **Do not assume a predicate mismatch automatically produces HTTP 405, 406, or 415.** If you need specific statuses for wrong method/media type, design an appropriate fallback route or exception/handler and test it clearly.

## 10. Predicate Routing vs. Handler Filter

A predicate answers the question **does this request belong to this route?** A filter processes the request/response inside or around the already selected handler.

WebFlux.fn provides several mechanisms:

- `before(...)`: transforms the request before the handler runs.
- `after(...)`: transforms the response after the handler.
- `filter(...)`: wraps the handler to perform before/after logic, such as permission checks, logging, or timing.

Example filter:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/api/reports/{id}", handler::getReport)
        .filter((request, next) -> {
            if ("allowed".equals(
                    request.headers().firstHeader("X-Demo-Access"))) {
                return next.handle(request);
            }
            return ServerResponse.status(HttpStatus.FORBIDDEN).build();
        })
        .build();
~~~

This is an example illustrating the filter mechanism, not a production security solution. A filter can inspect request information and then decide whether to call `next.handle(request)` or return another response. For real authentication/authorization, use Spring Security instead of trusting a demo header.

Filter scope is also important: a filter attached to a builder applies to the routes created by that builder; a filter inside a nested builder does not automatically apply to other top-level routes.

## 11. A Complete Java 17+ Example with Spring Boot WebFlux

The example below creates three functional endpoints:

- `GET /api/reports/{id}`: path + GET method + version header + Accept JSON.
- `POST /api/reports`: path + POST method + client header + Content-Type JSON.
- `GET /api/status`: path + GET method + one of two channel headers + Accept text/plain.

Create the structure:

~~~text
predicate-routing-demo/
├── pom.xml
└── src/main/java/com/example/routing/
    ├── RoutingApplication.java
    ├── ReportHandler.java
    └── ReportRoutes.java
~~~

File `pom.xml` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>predicate-routing-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

File `src/main/java/com/example/routing/RoutingApplication.java`:

~~~java
package com.example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/routing/ReportHandler.java`:

~~~java
package com.example.routing;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@Component
public class ReportHandler {

    public record ReportView(String id, String status) {}
    public record CreateReportRequest(String title) {}
    public record CreateReportResponse(boolean accepted, String title) {}

    public Mono<ServerResponse> getReport(ServerRequest request) {
        String id = request.pathVariable("id");

        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ReportView(id, "ready"));
    }

    public Mono<ServerResponse> createReport(ServerRequest request) {
        return request.bodyToMono(CreateReportRequest.class)
            .flatMap(body ->
                ServerResponse.accepted()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(
                        new CreateReportResponse(true, body.title())
                    )
            );
    }

    public Mono<ServerResponse> status(ServerRequest request) {
        return ServerResponse.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("ready");
    }
}
~~~

File `src/main/java/com/example/routing/ReportRoutes.java`:

~~~java
package com.example.routing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicate;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.accept;
import static org.springframework.web.reactive.function.server.RequestPredicates.contentType;
import static org.springframework.web.reactive.function.server.RequestPredicates.headers;
import static org.springframework.web.reactive.function.server.RequestPredicates.method;
import static org.springframework.web.reactive.function.server.RequestPredicates.path;

@Configuration(proxyBeanMethods = false)
public class ReportRoutes {

    @Bean
    RouterFunction<ServerResponse> reportRoutes(ReportHandler handler) {

        RequestPredicate readReport =
            path("/api/reports/{id}")
                .and(method(HttpMethod.GET))
                .and(headers(h ->
                    "v1".equals(h.firstHeader("X-API-Version"))))
                .and(accept(MediaType.APPLICATION_JSON));

        RequestPredicate createReport =
            path("/api/reports")
                .and(method(HttpMethod.POST))
                .and(headers(h ->
                    "trusted".equals(h.firstHeader("X-Client"))))
                .and(contentType(MediaType.APPLICATION_JSON));

        RequestPredicate allowedChannel =
            headers(h ->
                "internal".equals(h.firstHeader("X-Channel")))
            .or(headers(h ->
                "partner".equals(h.firstHeader("X-Channel"))));

        RequestPredicate status =
            path("/api/status")
                .and(method(HttpMethod.GET))
                .and(allowedChannel)
                .and(accept(MediaType.TEXT_PLAIN));

        return RouterFunctions.route(readReport, handler::getReport)
            .and(RouterFunctions.route(createReport, handler::createReport))
            .and(RouterFunctions.route(status, handler::status));
    }
}
~~~

Run inside the `predicate-routing-demo` directory with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

### Try GET: path + method + header + Accept

~~~bash
curl -i "http://localhost:8080/api/reports/42" ^
  -H "Accept: application/json" ^
  -H "X-API-Version: v1"
~~~

Expected JSON response:

~~~json
{"id":"42","status":"ready"}
~~~

If `X-API-Version: v1` is missing, or Accept does not match, the predicate does not match and the `getReport` handler is not invoked.

### Try POST: path + method + header + Content-Type

~~~bash
curl -i -X POST "http://localhost:8080/api/reports" ^
  -H "Content-Type: application/json" ^
  -H "X-Client: trusted" ^
  -d "{"title":"Q2 report"}"
~~~

The expected response is HTTP 202 with JSON:

~~~json
{"accepted":true,"title":"Q2 report"}
~~~

If the Content-Type is not suitable or the client header is wrong, the route does not match. Only when the route has matched but the JSON body is syntactically invalid does the handler/codec process it and potentially emit a decode error; these two cases are different.

### Try OR: one of the two allowed channels

~~~bash
curl -i "http://localhost:8080/api/status" ^
  -H "Accept: text/plain" ^
  -H "X-Channel: partner"
~~~

Expected response:

~~~text
ready
~~~

You can replace `partner` with `internal`. The `allowedChannel` predicate uses `or`, so either header value is sufficient; the path, method, and Accept conditions must still be met.

The cURL commands above use Windows CMD's `^` line-continuation character. In PowerShell or Bash, you can write the command on one line or use the corresponding line-continuation character.

## 12. Testing Routes with WebTestClient

You can test a functional route without starting a real server using `WebTestClient.bindToRouterFunction(...)`. This approach is useful for testing both predicate match and mismatch cases.

Illustrative test snippet:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class ReportRoutesTest {

    private final ReportHandler handler = new ReportHandler();

    private final RouterFunction<ServerResponse> routes =
        new ReportRoutes().reportRoutes(handler);

    private final WebTestClient client =
        WebTestClient.bindToRouterFunction(routes).build();

    @Test
    void matchesGetWhenAllPredicatesPass() {
        client.get()
            .uri("/api/reports/42")
            .header("X-API-Version", "v1")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("{"id":"42","status":"ready"}");
    }

    @Test
    void doesNotMatchWhenVersionHeaderIsMissing() {
        client.get()
            .uri("/api/reports/42")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isNotFound();
    }
}
~~~

This is a test snippet that needs the `spring-boot-starter-test` dependency or the corresponding test dependencies, and the `RouterFunction` and `ServerResponse` imports. If run in an application that has other routes/controllers, the result of an unmatched request may differ because another router continues handling it; binding directly to this router isolates the exact behavior of the tested route.

You should have tests for:

- Right path, method, header, and media type → the handler is called.
- Right path but wrong method → the route does not match.
- Missing required header → the route does not match.
- Unsuitable Content-Type → the handler is not selected.
- Incompatible Accept → the route does not match.
- OR: each valid branch individually matches.
- Multiple routes with overlapping paths → the specific route is declared first.
- Malformed body after the route matches → the decode error is handled separately from routing errors.

## 13. Common Mistakes and How to Avoid Them

1. **Confusing Content-Type with Accept:** Content-Type is the request body type; Accept is the response type the client wants. Use `contentType(...)` for the incoming body and `accept(...)` for the response.
2. **Using a header predicate while forgetting the header can be absent:** `firstHeader` can return `null`. Compare in a null-safe way such as `"v1".equals(value)`.
3. **Using `and` when you actually want one of several options:** all conditions must be true so the route may never match. Use `or` and group predicates clearly.
4. **Using `or` without grouping conditions:** the logical expression becomes hard to read or accidentally loosens a required condition. Create a predicate variable for the OR group and then combine with AND outside.
5. **Thinking the path predicate checks query parameters:** path only checks the URI path. If you need a query param, use the corresponding query predicate or check `ServerRequest.queryParam(...)` in the handler.
6. **Using a Content-Type predicate for a GET with no body:** the header may not exist. Only check Content-Type on routes that actually receive a body.
7. **Reading the body inside a predicate:** predicates are for selecting a route based on metadata; the body is a stream with its own lifecycle. Read the body in the handler after the route is selected.
8. **Assuming a predicate mismatch automatically returns 405/406/415:** a predicate only causes the route not to match. If you want a specific status, you need fallback/exception handling and tests.
9. **Placing a general route before a specific route:** the general route can catch the request first. Declare specific routes first.
10. **Using custom headers for authentication:** the client can send headers itself. Use Spring Security or real token/credential verification.
11. **Confusing a predicate with a filter:** a predicate decides the route; a filter wraps the selected handler. Use the right abstraction for the purpose.
12. **Repeating a path prefix across many routes:** nested routes with `path(...)` help group the shared prefix and conditions.
13. **Not testing route mismatches:** a route working on the happy path is not enough. Test each missing header, wrong method, and media type.
14. **Confusing media type compatibility with exact string equality:** `accept`/`contentType` perform matching according to Spring's MediaType rules, not simply comparing header strings.
15. **Using a header predicate to check for a valid JSON body:** predicates only check headers. Syntactically invalid JSON is detected at the decode step in the handler.
16. **Ignoring RouterFunction composition order:** `and(...)` chains routes in order; the first matching route will be selected.

## 14. Route Design Checklist

Before registering a route, determine:

- What is the exact path pattern? Are there path variables or a shared prefix?
- Which HTTP methods are allowed?
- Are any headers required? If missing, should the route not match?
- What media type does the request body have? Is `contentType` needed?
- What response media type must the client accept? Is `accept` needed?
- Is the condition AND or OR? Are predicate groups clear?
- Is there any general route that could catch the request before a specific route?
- If no route matches, does the application need 404, 405, 406, or 415 according to the contract?
- Are you confusing route selection with authentication/authorization?
- Is the body read exactly once in the handler?
- Are there tests for both route match and mismatch?

## 15. Self-Check Questions

**1.** What job does `RequestPredicate` perform? Checks whether a request satisfies the conditions to select a route.

**2.** Which part of the request does `path("/reports/{id}")` check? The URI path, not the query string.

**3.** Does `method(HttpMethod.GET)` check headers? No; it only checks the HTTP method.

**4.** What does `headers(h -> ...)` allow you to do? Write a custom predicate on the request headers.

**5.** Which header does `contentType(APPLICATION_JSON)` check? The Content-Type of the request body.

**6.** Which header does `accept(APPLICATION_JSON)` check? Accept, meaning the media type the client accepts in the response.

**7.** How does `and` differ from `or`? AND requires both predicates to be true; OR requires at least one predicate to be true.

**8.** What is `negate()` used for? Inverts the result of a predicate.

**9.** Why should specific routes be placed before general routes? A RouterFunction is evaluated in order; a general route may match first.

**10.** Does a header predicate replace Spring Security? No; it only selects a route, and does not authenticate identity or permissions.

**11.** When a predicate does not match, is the handler called? No; the router tries another route or lets the dispatch mechanism handle a request with no matching handler.

**12.** Should you read the request body inside a predicate? No; the body should be read in the handler via `bodyToMono` or `bodyToFlux`.

**Key takeaway:** In WebFlux.fn, `RequestPredicate` lets you combine **path + HTTP method + headers + media type** conditions to select the right `HandlerFunction`. Use `and` when every condition is required, `or` when there are alternative options, and `negate` when exclusion is needed. `contentType` checks the body sent by the client; `accept` checks the response accepted by the client. Place specific routes before general routes, handle the body in the handler, and use Spring Security for authorization.

**Official documentation:** [Spring Framework 6.2 — Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html); [RequestPredicates Javadoc — WebFlux](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/server/RequestPredicates.html); [RequestPredicate Javadoc — WebFlux](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/server/RequestPredicate.html).