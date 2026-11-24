# Distinguishing WebFilter from HandlerFilterFunction in Spring WebFlux

Spring WebFlux has two filter contracts commonly used to insert logic before and after a handler: **WebFilter** and **HandlerFilterFunction**. Both run on the reactive model, can inspect the request, block the request, call the next processing step, and transform the response. However, they sit at two different layers:

- **WebFilter** belongs to Spring's WebHandler API. A WebFilter bean is applied on the application's HTTP exchange processing chain, before the target WebHandler. It can wrap annotated controllers, functional endpoints, and other WebHandlers in the same WebFlux application.
- **HandlerFilterFunction** belongs to WebFlux.fn. It wraps a HandlerFunction inside a RouterFunction, so its scope is the functional routes to which the router builder or RouterFunction has attached that filter.

Therefore, if you need an application-level common policy for requests such as correlation ID, CORS, logging, timeout, or an integrated security check step, consider WebFilter. If you need small middleware dedicated only to a group of routes declared with RouterFunction, HandlerFilterFunction is usually more suitable.

This lesson belongs to the **Filters and Sessions** group and focuses on how to distinguish the two filters, organize the chain, access WebSession, and choose the right scope of application.

## 1. Learning Objectives

After this lesson, you can:

- Describe the position of WebFilter in the WebHandler processing chain.
- Explain the filter(ServerWebExchange, WebFilterChain) contract and the Mono<Void> return value.
- Describe the HandlerFilterFunction<T, R> contract in WebFlux.fn.
- Distinguish the scope of an application-wide filter from a per-functional-route filter.
- Use a filter to continue, block, or transform a request/response.
- Distinguish before, after, and filter in RouterFunctions.Builder.
- Understand filter order and filter scope in nested routes.
- Access WebSession from ServerWebExchange or ServerRequest without accidentally creating a session.
- Write a Java 17+ example with WebFilter, HandlerFilterFunction, and WebTestClient.
- Avoid common mistakes with single-read bodies, manual subscribe, unnecessary sessions, and security.

## 2. Placing Both Filters in the Right Processing Layer

WebFlux provides a common HTTP processing chain. WebFilter sits at the WebHandler API layer, wrapping the remaining processing. After the request passes through the filter chain, the central WebHandler is usually DispatcherHandler. DispatcherHandler finds the handler through HandlerMappings and invokes the handler through the appropriate HandlerAdapter.

Functional endpoints also participate in the DispatcherHandler lifecycle. RouterFunctionMapping finds the route, HandlerFunctionAdapter invokes the HandlerFunction, and ServerResponseResultHandler writes the result. Therefore, functional routes still pass through WebFilters at the outer layer.

~~~text
HTTP server
    |
    v
WebExceptionHandler chain
    |
    v
WebFilter chain
    |
    v
WebHandler / DispatcherHandler
    |
    +-------------------------------+
    |                               |
    v                               v
Annotated controller          Functional endpoint
HandlerMapping                 RouterFunctionMapping
    |                               |
HandlerAdapter                 HandlerFunctionAdapter
    |                               |
Controller method              HandlerFunction
    |                               |
    v                               v
Result handling                ServerResponse
    |                               |
    +---------------+---------------+
                    |
                    v
              HTTP response
~~~

The diagram is a general model. An application can have many filters, exception handlers, security filters, and different HandlerMappings. The point to remember is that **WebFilter wraps the general handler layer**, whereas **HandlerFilterFunction sits inside the functional routing branch after a route is selected**.

A request to an annotated controller still passes through WebFilter. That request does not automatically pass through the HandlerFilterFunction of another RouterFunction.

## 3. What Is WebFilter?

WebFilter is a contract in the org.springframework.web.server package. It has one method:

~~~java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain)
~~~

The two parameters play different roles:

- **ServerWebExchange:** represents the current HTTP request-response exchange. It provides access to the request, response, request attributes, session, principal, and other information.
- **WebFilterChain:** provides a method to pass the request to the next filter or the target WebHandler.

The filter returns **Mono<Void>** to indicate that the entire request processing has completed or emitted an error. This Mono is part of the HTTP pipeline; there is no need to subscribe yourself.

A simple WebFilter adding a response header:

~~~java
@Component
public class ResponseHeaderWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse()
            .getHeaders()
            .add("X-Application-Filter", "applied");

        return chain.filter(exchange);
    }
}
~~~

This is a fragment that needs Spring WebFlux imports. The header is set before calling the next processing step, so the response can carry that header if the response has not yet committed. The filter returns the publisher from the chain so the framework manages the lifecycle.

### Continuing or Blocking a Request

Calling chain.filter(exchange) lets the request proceed. If the filter does not call the chain, it can create its own response and end the pipeline:

~~~java
@Component
public class SimpleGateWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String token = exchange.getRequest()
            .getHeaders()
            .getFirst("X-Demo-Token");

        if (!"allow".equals(token)) {
            exchange.getResponse()
                .setStatusCode(HttpStatus.FORBIDDEN);
            return exchange.getResponse().setComplete();
        }

        return chain.filter(exchange);
    }
}
~~~

This is an example illustrating a simple gate, not a production authentication mechanism. When rejecting a request, the filter sets the status and then returns Mono<Void> from setComplete. It does not call the chain, so the controller or functional handler is not run.

For real authentication and authorization, you should use Spring Security reactive. A custom WebFilter can join the security chain as configured, but you should not invent your own token checking, identity management, session fixation, and authorization if Spring Security already provides suitable mechanisms.

## 4. How Are WebFilter Beans Applied?

In an application using WebFlux Config or Spring Boot WebFlux, beans of type WebFilter are automatically put into the filter chain for HTTP exchanges. Thus, a filter does not need to be declared again in each controller or RouterFunction.

You can register it as a component:

~~~java
@Component
public class TraceWebFilter implements WebFilter {
    // ...
}
~~~

Or declare a bean:

~~~java
@Configuration
public class WebFilterConfiguration {

    @Bean
    WebFilter traceWebFilter() {
        return (exchange, chain) -> {
            exchange.getResponse().getHeaders()
                .add("X-Trace-Filter", "applied");
            return chain.filter(exchange);
        };
    }
}
~~~

Both approaches above create a WebFilter bean. Choose one approach that fits the configuration structure; do not register the same filter twice via both @Component and @Bean.

### Order of Multiple WebFilters

When order matters, a WebFilter can implement Ordered or use @Order:

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
WebFilter firstWebFilter() {
    return (exchange, chain) -> chain.filter(exchange);
}

@Bean
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
WebFilter secondWebFilter() {
    return (exchange, chain) -> chain.filter(exchange);
}
~~~

A lower order value takes precedence earlier in the chain. The filter that runs earlier is usually the outer wrapper: the code before chain.filter runs when the request comes in; the processing after chain.filter runs when the response goes back out, if the pipeline completes along that branch.

~~~text
Request coming in:
Filter A before
  Filter B before
    Handler
  Filter B after
Filter A after

Response going out:
Filter B finishes first
Filter A finishes after
~~~

In practice, check the order of framework filters and application filters. Spring Security uses WebFilterChainProxy; CORS, observation, and other filters can also have configured orders. Do not assume a custom filter always runs before or after Security unless you have set and checked the order explicitly.

## 5. What Is HandlerFilterFunction?

HandlerFilterFunction belongs to the org.springframework.web.reactive.function.server package of WebFlux.fn. It is a functional interface that wraps a HandlerFunction.

Main contract:

~~~java
Mono<R> filter(
    ServerRequest request,
    HandlerFunction<T> next
)
~~~

Where:

- **ServerRequest:** the request converted to the functional endpoint abstraction. It provides the method, URI, path variables, headers, query parameters, body, principal, session, and underlying exchange.
- **HandlerFunction<T>:** the next handler in the functional chain. It receives a ServerRequest and returns a publisher containing a ServerResponse.
- **T and R:** the response type of the handler and the response type the filter returns. Usually both are ServerResponse.

HandlerFilterFunction can call next.handle(request) to forward. It can also skip calling next and return a response itself to block the request.

Example:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> routeGuard =
    (request, next) -> {
        String token = request.headers()
            .firstHeader("X-Route-Token");

        if (!"allow".equals(token)) {
            return ServerResponse.status(HttpStatus.FORBIDDEN)
                .bodyValue("Blocked by route filter");
        }

        return next.handle(request);
    };
~~~

This is a fragment for WebFlux.fn. The filter only takes effect when attached to a RouterFunction or router builder. It does not automatically become an application-wide filter just because a variable is declared in configuration.

### Attaching HandlerFilterFunction to a RouterFunction

You can attach a filter using the builder:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/fn/hello", request ->
            ServerResponse.ok().bodyValue("hello"))
        .filter(routeGuard)
        .build();
~~~

The filter is applied to the routes built in that builder. You can apply it to an existing RouterFunction:

~~~java
RouterFunction<ServerResponse> secured =
    existingRoutes.filter(routeGuard);
~~~

One RouterFunction can be composed with another RouterFunction. Attach the filter at the right route level to avoid accidentally protecting too broadly or too narrowly.

## 6. before, after, and filter in Functional Routing

RouterFunctions.Builder provides three ways to add logic around functional routes:

- **before(requestProcessor):** receives a ServerRequest and returns a transformed ServerRequest before the handler runs.
- **after(responseProcessor):** receives the request along with the ServerResponse and returns a response after the handler completes.
- **filter(handlerFilterFunction):** wraps the HandlerFunction; it can inspect the request, decide whether to call the handler, and observe or transform the response.

### before: Transforming the Request Before the Handler

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/fn/header", request ->
            ServerResponse.ok().bodyValue(
                request.headers().firstHeader("X-Route-Tag")))
        .before(request -> ServerRequest.from(request)
            .header("X-Route-Tag", "from-before")
            .build())
        .build();
~~~

ServerRequest is an immutable abstraction. ServerRequest.from(request) creates a builder based on the current request; the header is added to the new request and then passed to the handler. The original request is not modified directly.

### after: Observing the Response After the Handler

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/fn/hello", request ->
            ServerResponse.ok().bodyValue("hello"))
        .after((request, response) -> {
            log.info("Functional response status: {}",
                response.statusCode());
            return response;
        })
        .build();
~~~

The after callback receives the response already created by the handler. The example only logs and returns the same response, thereby preserving the body and headers. If you need to change the response, you must create a new response with an explicitly defined status, headers, and body; do not assume a builder that only copies status/headers will automatically keep the old body.

### filter: Wrapping the Entire Handler

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> loggingFilter =
    (request, next) ->
        next.handle(request)
            .doOnNext(response ->
                log.info("{} {} -> {}",
                    request.method(),
                    request.path(),
                    response.statusCode()));
~~~

The filter calls next.handle(request), then observes the ServerResponse when the publisher emits the result. Because doOnNext only observes and returns the original signal, the response body is preserved. If the filter does not call next, it can return a ServerResponse itself to block the request.

## 7. Scope of HandlerFilterFunction and Nested Routes

A filter added to a router builder applies to the routes belonging to that builder. With nested routes, the declaration position decides the scope:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .path("/people", people -> people
            .nest(accept(MediaType.APPLICATION_JSON), json -> json
                .GET("/{id}", handler::getPerson)
                .GET("", handler::listPeople)
                .before(request -> ServerRequest.from(request)
                    .header("X-Json-Route", "yes")
                    .build()))
            .POST(handler::createPerson))
        .after((request, response) -> {
            log.info("Completed {}", request.path());
            return response;
        })
        .build();
~~~

In the example:

- before is inside the nested branch with the Accept JSON condition, so it only affects the GET routes in that branch.
- after is on the outer builder, so it affects all routes composed in the builder, including the nested routes.
- A route outside this builder does not receive the filter just because it is in the same application.

This differs from a WebFilter bean, which is put into the common HTTP exchange chain. If you want an application-wide policy, you should not create a bunch of HandlerFilterFunctions and attach them manually to every RouterFunction.

## 8. Direct Comparison Table

| Criterion | WebFilter | HandlerFilterFunction |
| --- | --- | --- |
| API | WebHandler API | WebFlux.fn |
| Package | org.springframework.web.server | org.springframework.web.reactive.function.server |
| Contract | ServerWebExchange + WebFilterChain | ServerRequest + HandlerFunction |
| Return value | Mono<Void> | Mono<R> |
| Scope | The application's HTTP processing chain | The RouterFunction/functional routes the filter is attached to |
| Annotated controller | Can wrap | Not applied automatically |
| Functional endpoint | Yes, at the outer layer | Yes, at the functional route layer |
| Accessing response | ServerWebExchange.getResponse() | Handles immutable ServerResponse |
| Transforming request | Use exchange/request wrapper or mutate | Use ServerRequest.from(request).build() |
| Blocking request | Do not call chain.filter; complete the response yourself | Do not call next.handle; return ServerResponse |
| Registration | Spring bean WebFilter | RouterFunction.filter or builder.filter |
| Order | Ordered / @Order | Composition and filter position in the router |
| Session | exchange.getSession() | request.session() |
| Use case | Application-wide cross-cutting | Middleware tied to functional routes |

Both are reactive, but the abstraction and scope are different. WebFilter operates on ServerWebExchange and completes the entire HTTP exchange. HandlerFilterFunction operates on ServerRequest and the response is represented by ServerResponse.

## 9. Choosing a Filter by Use Case

### Choose WebFilter When Logic Must Apply Broadly

Examples that usually fit WebFilter:

- Attach a correlation ID or request ID to every request.
- Record observation/logging at the HTTP boundary.
- Configure CORS at the WebFlux layer.
- Apply timeouts or request limits according to an application-wide policy.
- Read or update metadata/session shared across many endpoints.
- Integrate Spring Security's filter chain.
- Standardize certain response headers on every route.

A WebFilter can check the path and only do extra work for one group of endpoints, but the bean is still called in the chain of every exchange. If the logic truly belongs only to one functional route, using HandlerFilterFunction expresses the scope more clearly.

### Choose HandlerFilterFunction When Logic Belongs to Functional Routes

Suitable examples:

- Guard a group of functional routes with a dedicated policy.
- Add an internal request header before a HandlerFunction runs.
- Check metadata specific to a functional module.
- Attach a session attribute for a specific functional workflow.
- Log responses only for one RouterFunction.
- Create middleware that can be composed with a route builder.

HandlerFilterFunction is not attached to annotated controller methods. If you want similar behavior on annotated controllers, consider WebFilter, Spring Security, @ControllerAdvice, an appropriate hook, or logic in a service depending on the requirement.

### Do Not Use Filters in Place of Every Other Layer

A filter is an interception point at the HTTP layer. It is not the default place to put all business rules.

- Authentication and authorization should rely on Spring Security reactive.
- Business data validation should sit at the service/domain boundary.
- Converting business errors into responses can use an exception handler/advice.
- Recording business logs after an operation succeeds should be placed in the appropriate use case/service.
- Logic dedicated only to one functional route can be placed in HandlerFilterFunction.

## 10. Accessing WebSession in WebFlux

**WebSession** is Spring's abstraction for a server-side session, allowing attributes to be kept across multiple HTTP requests. The session ID is usually sent to the client with a cookie; the session contents are managed by WebSessionStore.

There are two access paths corresponding to the two filter types:

- In WebFilter: call **exchange.getSession()**, returning Mono<WebSession>.
- In HandlerFilterFunction: call **request.session()**, returning Mono<WebSession>.

Both methods return a publisher because the session may need to be retrieved from the session store. Calling getSession/session to get the instance **does not automatically initialize and save a new session**.

~~~java
// In WebFilter
return exchange.getSession()
    .flatMap(session -> {
        session.getAttributes().put(
            "lastPath",
            exchange.getRequest().getPath().value());
        return chain.filter(exchange);
    });
~~~

~~~java
// In HandlerFilterFunction
return request.session()
    .flatMap(session -> {
        session.getAttributes().put(
            "lastFunctionalPath",
            request.path());
        return next.handle(request);
    });
~~~

Adding an attribute causes the session to start. The application can call start() to start it explicitly. The session is saved automatically before the response is committed; normally there is no need to call save() manually.

### Some WebSession Operations

| API | Meaning |
| --- | --- |
| getAttribute(name) | Read an attribute if present |
| getAttributeOrDefault(name, fallback) | Read with a default value |
| getAttributes() | Access the attribute map |
| start() | Start the session explicitly |
| isStarted() | Check if the session has started |
| changeSessionId() | Change the session ID |
| invalidate() | Invalidate the session and clear storage |
| setMaxIdleTime(duration) | Set the maximum idle time |

Asynchronous operations such as changeSessionId() and invalidate() return Mono<Void>; you must compose them into the pipeline. Do not call subscribe() separately.

### A Session Is Not the Same as a Request Attribute

- **Request attribute** exists only within one current HTTP exchange.
- **WebSession attribute** exists across multiple requests carrying the same session ID, according to the storage policy and session expiration.
- **Reactor Context** is tied to a subscription, and does not automatically persist across the next request.
- **Cookie** usually carries the session ID, not the entire session data.

Do not store large data, objects that cannot be serialized by the store in use, or unnecessary sensitive information in the session. For multi-instance applications, you need a shared session store such as Spring Session Redis or a suitable storage mechanism; a session kept only in the memory of one instance is not automatically shared between nodes.

## 11. Complete Java 17+ Example with Spring Boot WebFlux

This example uses both filter types in the same application:

- A **WebFilter** adds a request ID to the response for every exchange, including annotated controllers and functional routes.
- Another **WebFilter** updates the session only on the /api/session/visits endpoint.
- A **HandlerFilterFunction** protects the functional route /fn/hello, blocks requests missing the token, and adds a header to the ServerRequest copy passed to the handler.
- Another **HandlerFilterFunction** updates the session for the functional route /fn/session/visits.
- One annotated controller and two functional routes help compare the active scopes.

### Project Structure

~~~text
webflux-filter-demo/
├── pom.xml
└── src
    ├── main/java/com/example/filters
    │   ├── FilterDemoApplication.java
    │   ├── ApiController.java
    │   └── FilterConfiguration.java
    └── test/java/com/example/filters
        └── FilterComparisonTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>webflux-filter-demo</artifactId>
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

The Spring Boot parent manages compatible Spring Framework and Reactor versions. The example uses Java 17 and the WebFlux starter.

### FilterDemoApplication.java

~~~java
package com.example.filters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }
}
~~~

### ApiController.java

~~~java
package com.example.filters;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/hello")
    public Mono<String> hello() {
        return Mono.just("annotated");
    }

    @GetMapping("/session/visits")
    public Mono<String> sessionVisits(ServerWebExchange exchange) {
        return exchange.getSession()
            .map(session -> "visits=" +
                session.getAttributeOrDefault("webFilterVisits", 0));
    }
}
~~~

The /api/hello endpoint simply returns content to test the global WebFilter. The /api/session/visits endpoint reads the session updated earlier by the WebFilter.

### FilterConfiguration.java

~~~java
package com.example.filters;

import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.server.HandlerFilterFunction;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;

@Configuration
public class FilterConfiguration {

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    WebFilter requestIdWebFilter() {
        return (exchange, chain) -> {
            String requestId = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Request-Id");

            if (requestId == null ||
                    !requestId.matches("[A-Za-z0-9._-]{1,64}")) {
                requestId = UUID.randomUUID().toString();
            }

            exchange.getResponse()
                .getHeaders()
                .set("X-Request-Id", requestId);

            return chain.filter(exchange);
        };
    }

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE + 10)
    WebFilter webFilterSessionCounter() {
        return (exchange, chain) -> {
            String path = exchange.getRequest()
                .getPath()
                .value();

            if (!"/api/session/visits".equals(path)) {
                return chain.filter(exchange);
            }

            return exchange.getSession()
                .flatMap(session -> {
                    Integer current =
                        session.getAttribute("webFilterVisits");

                    session.getAttributes().put(
                        "webFilterVisits",
                        current == null ? 1 : current + 1);

                    return chain.filter(exchange);
                });
        };
    }

    @Bean
    RouterFunction<ServerResponse> functionalRoutes() {
        HandlerFilterFunction<ServerResponse, ServerResponse> routeGuard =
            (request, next) -> {
                String token = request.headers()
                    .firstHeader("X-Route-Token");

                if (!"allow".equals(token)) {
                    return ServerResponse.status(HttpStatus.FORBIDDEN)
                        .bodyValue("Blocked by functional route filter");
                }

                ServerRequest decorated = ServerRequest.from(request)
                    .header("X-Route-Filter", "applied")
                    .build();

                return next.handle(decorated);
            };

        RouterFunction<ServerResponse> helloRoute =
            RouterFunctions.route()
                .GET("/fn/hello", request ->
                    ServerResponse.ok().bodyValue(
                        "functional:" +
                        request.headers().firstHeader("X-Route-Filter")))
                .filter(routeGuard)
                .build();

        HandlerFilterFunction<ServerResponse, ServerResponse> sessionCounter =
            (request, next) -> request.session()
                .flatMap(session -> {
                    Integer current =
                        session.getAttribute("functionalVisits");

                    session.getAttributes().put(
                        "functionalVisits",
                        current == null ? 1 : current + 1);

                    return next.handle(request);
                });

        RouterFunction<ServerResponse> sessionRoute =
            RouterFunctions.route()
                .GET("/fn/session/visits", request ->
                    request.session()
                        .flatMap(session ->
                            ServerResponse.ok().bodyValue(
                                "visits=" + session.getAttributeOrDefault(
                                    "functionalVisits", 0))))
                .filter(sessionCounter)
                .build();

        return helloRoute.andOther(sessionRoute);
    }
}
~~~

Points to observe:

1. **requestIdWebFilter** is a WebFilter bean. It is called on both /api/hello and /fn/hello, and adds X-Request-Id to the response.
2. **webFilterSessionCounter** is also a WebFilter, but only runs session logic when the path matches /api/session/visits. Other requests continue without creating a session.
3. **routeGuard** is attached only to helloRoute. It rejects requests if X-Route-Token=allow is missing. When allowed, it creates a new ServerRequest with X-Route-Filter and passes that request to the handler.
4. **sessionCounter** is attached only to sessionRoute. It accesses WebSession via request.session(), updates the count, and calls the next handler.
5. The two RouterFunctions are composed with andOther. helloRoute's filter does not automatically apply to sessionRoute; the application-wide WebFilter still wraps both.

### FilterComparisonTests.java

~~~java
package com.example.filters;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FilterComparisonTests {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void webFilterWrapsAnnotatedController() {
        webTestClient.get()
            .uri("/api/hello")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Request-Id")
            .expectHeader().doesNotExist("X-Route-Filter")
            .expectBody(String.class)
            .isEqualTo("annotated");
    }

    @Test
    void handlerFilterFunctionCanShortCircuitFunctionalRoute() {
        webTestClient.get()
            .uri("/fn/hello")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().exists("X-Request-Id")
            .expectBody(String.class)
            .isEqualTo("Blocked by functional route filter");
    }

    @Test
    void handlerFilterFunctionCanDecorateFunctionalRequest() {
        webTestClient.get()
            .uri("/fn/hello")
            .header("X-Route-Token", "allow")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Request-Id")
            .expectBody(String.class)
            .isEqualTo("functional:applied");
    }

    @Test
    void webFilterCanUpdateWebSession() {
        webTestClient.get()
            .uri("/api/session/visits")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("Set-Cookie")
            .expectBody(String.class)
            .isEqualTo("visits=1");
    }

    @Test
    void handlerFilterFunctionCanUpdateWebSession() {
        webTestClient.get()
            .uri("/fn/session/visits")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("Set-Cookie")
            .expectBody(String.class)
            .isEqualTo("visits=1");
    }
}
~~~

Run all tests:

~~~bash
mvn -q test
~~~

If the five tests pass, Maven exits with exit code 0. The tests check three core things:

- WebFilter also runs on the annotated controller.
- HandlerFilterFunction only protects the functional route it is attached to and can block the request or pass a transformed request to the handler.
- Both filter types can access WebSession and update the session in their own scope.

### Running the Application and Trying Requests

Start:

~~~bash
mvn spring-boot:run
~~~

The annotated controller always has a request ID from WebFilter:

~~~bash
curl -i http://localhost:8080/api/hello
~~~

The functional route is blocked if the token is missing:

~~~bash
curl -i http://localhost:8080/fn/hello
~~~

Send the token so the functional route can proceed:

~~~bash
curl -i -H "X-Route-Token: allow" http://localhost:8080/fn/hello
~~~

The two session endpoints illustrate the two filter positions:

~~~bash
curl -i -c cookies.txt http://localhost:8080/api/session/visits
curl -i -b cookies.txt -c cookies.txt http://localhost:8080/api/session/visits
curl -i -c functional-cookies.txt http://localhost:8080/fn/session/visits
curl -i -b functional-cookies.txt -c functional-cookies.txt http://localhost:8080/fn/session/visits
~~~

The client must send back the session cookie on the next request to continue the same WebSession. The two cookie jars in the example are separated so as not to mix the state of the two endpoints.

## 12. Common Mistakes and How to Fix Them

1. **Using HandlerFilterFunction and expecting it to apply to @RestController.** It only wraps the functional routes the filter is attached to. Use WebFilter if you need a general HTTP exchange scope.
2. **Using WebFilter for a single functional route that does not need global scope.** The filter still gets called for every exchange and then has to check the path itself. Consider HandlerFilterFunction.
3. **Forgetting to return the chain's publisher.** WebFilter must compose and return chain.filter(exchange); HandlerFilterFunction must compose next.handle(request) when allowing continuation.
4. **Calling subscribe() inside a filter.** This detaches the work from the HTTP lifecycle, breaking the connection with errors, cancellation, and response.
5. **Calling block() to get the session or body.** Session/body APIs are reactive; use flatMap/map and return the publisher.
6. **Not calling next/chain but expecting the handler to run.** If it does not delegate, the filter is short-circuiting and must create an appropriate response itself.
7. **Reading the request body in a filter and leaving the handler to read it again.** The body is a stream that may only be read once. If you need to inspect the body, you must design suitable caching/wrapping and preserve backpressure.
8. **Directly modifying ServerRequest or ServerResponse.** These are immutable abstractions. Use a builder/wrapper or return a new response with an explicitly built body.
9. **Assuming ServerResponse.from(response) keeps the body.** This builder is used to start from status and headers; if recreating a response, you must handle the body intentionally.
10. **Creating a session unnecessarily for every request.** Simply getting the session does not start the session; adding an attribute or calling start() starts the session. Only access the session when business logic requires it.
11. **Calling WebSession.save() manually on every request.** The framework saves automatically before the response commits. Let the pipeline manage it, unless there is a special documented requirement.
12. **Not composing invalidate() or changeSessionId().** These are Mono<Void>; if the publisher is ignored, the asynchronous operation may not execute.
13. **Assuming an in-memory session is shared across multiple instances.** You need a shared store when deploying multiple nodes.
14. **Writing authentication yourself with a demo header.** The token example in the lesson only illustrates short-circuiting; production needs Spring Security reactive, credential verification, and authorization.
15. **Setting @Order without considering framework filters.** Security, CORS, observation, and application filters may depend on order. Check the actual chain.
16. **Placing a route filter on a builder that is too broad.** The filter may apply to every route composed in that builder. Split routers or use nested scope when you need to restrict it.
17. **Swallowing errors in a filter.** Do not turn every error into a 200 response or Mono.empty(); let an appropriate exception handler process the error.
18. **Not testing both annotated and functional routes.** A functional route test does not prove WebFilter wrapped the annotated controller and vice versa.

## 13. Design Checklist

Before implementing a filter, determine:

- **Scope:** does the policy need to run on every HTTP exchange, or only one functional route?
- **Contract:** is the code working with ServerWebExchange/WebFilterChain or ServerRequest/HandlerFunction?
- **Delegate:** when should chain.filter or next.handle be called, and when should it short-circuit?
- **Reactive lifecycle:** are all publishers completely composed and returned?
- **Request body:** does the filter read the body? If so, can the later handler still read it?
- **Request mutation:** are you using a wrapper/builder instead of mutating an immutable object?
- **Response mutation:** are status, headers, and body preserved properly when creating a new response?
- **Ordering:** do WebFilters and Spring Security have an appropriate order?
- **Nested routes:** does the builder's filter cover the intended route scope?
- **Session:** is WebSession really needed? Is a session accidentally started for stateless requests?
- **Storage:** does the session store meet single-node or multi-node requirements?
- **Security:** are you using Spring Security reactive for authentication/authorization?
- **Errors:** are errors propagated to WebExceptionHandler or the appropriate handler?
- **Tests:** have you tested annotated controllers, functional routes, short-circuiting, request mutation, and sessions?

## 14. Self-Check Exercises

**Exercise 1.** A WebFilter bean is registered in a WebFlux application. Can it wrap both annotated controllers and functional routes?  
**Answer:** Yes. WebFilter sits in the general WebHandler chain, outside the target WebHandler.

**Exercise 2.** Does HandlerFilterFunction run automatically for a @RestController?  
**Answer:** No. It only runs when attached to the corresponding RouterFunction/functional route.

**Exercise 3.** Why does WebFilter return Mono<Void> while HandlerFilterFunction returns Mono<ServerResponse> in the typical case?  
**Answer:** WebFilter wraps the entire HTTP exchange and signals completion of the response; HandlerFilterFunction wraps a HandlerFunction and returns the created response.

**Exercise 4.** If HandlerFilterFunction does not call next.handle(request), what happens?  
**Answer:** The next handler does not run. The filter must return a replacement ServerResponse, for example 401 or 403.

**Exercise 5.** To add a header to a request before a functional handler, which approach do you use?  
**Answer:** Create a new ServerRequest with ServerRequest.from(request), add the header, then build and pass the new request to next.handle.

**Exercise 6.** What do before and after in a router builder do?  
**Answer:** before transforms the request before the handler; after processes the response after the handler. filter wraps the handler and can block or delegate.

**Exercise 7.** With which API can WebFilter access WebSession?  
**Answer:** ServerWebExchange.getSession(), returning Mono<WebSession>.

**Exercise 8.** With which API can HandlerFilterFunction access WebSession?  
**Answer:** ServerRequest.session(), returning Mono<WebSession>.

**Exercise 9.** Does merely calling getSession() cause a new session to be saved and a cookie sent right away?  
**Answer:** No. Getting the instance does not automatically start the session. Adding an attribute or calling start() starts the session; the session is saved before the response commits.

**Exercise 10.** Why shouldn't you call subscribe() inside a filter?  
**Answer:** It creates a subscription detached from the HTTP lifecycle, making errors, cancellation, and response completion hard to coordinate properly.

**Exercise 11.** Does a filter attached on a nested router affect routes outside the nested scope?  
**Answer:** No. Filter scope depends on the builder and composition position; a filter on an outer builder can cover nested routes as well.

**Exercise 12.** You need to protect all endpoints with authentication. Should you write a HandlerFilterFunction yourself for every RouterFunction?  
**Answer:** No. Use Spring Security reactive and configure the appropriate WebFilter chain for a consistent security policy.

## 15. Key Takeaways

**WebFilter** is an interceptor at the WebHandler API layer. WebFilter beans are placed into the HTTP exchange processing chain and can wrap both annotated controllers and functional endpoints. It works with ServerWebExchange and WebFilterChain, returns Mono<Void>, can delegate or complete the response itself, and can be ordered with Ordered/@Order.

**HandlerFilterFunction** is middleware of WebFlux.fn. It works with ServerRequest and HandlerFunction, returns Mono<ServerResponse>, and applies only to the RouterFunction/functional routes to which the filter is attached. It can short-circuit, transform the request before the handler runs, or observe the response after the handler.

Both can access WebSession via their own APIs: exchange.getSession() or request.session(). Merely getting the session does not start the session; adding an attribute or calling start() starts it. Choose WebFilter for policies at the general HTTP boundary, HandlerFilterFunction for middleware per functional route, compose all publishers, and let Spring manage session save/cancellation/response lifecycle.

### References

- Spring Framework, [Reactive Core – WebHandler API and Filters](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Spring Framework, [Functional Endpoints – Filtering Handler Functions](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- Spring Framework Javadoc, [WebFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html).
- Spring Framework Javadoc, [HandlerFilterFunction](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/HandlerFilterFunction.html).
- Spring Framework Javadoc, [ServerWebExchange](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html).
- Spring Framework Javadoc, [ServerRequest](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html).
- Spring Framework Javadoc, [WebSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html).
- Spring Boot, [Reactive Web Applications and Web Filters](https://docs.spring.io/spring-boot/reference/web/reactive.html).
