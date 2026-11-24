# HandlerResultHandler and Writing Results to the Response

In Spring WebFlux, finding a controller and invoking its method is only **half the journey of an HTTP request**. After the handler runs, the framework must interpret its return value—a DTO, `Mono<DTO>`, `Flux<DTO>`, `ResponseEntity<?>`, a view name, or a functional endpoint's `ServerResponse`—and turn that result into an **HTTP status, headers, and response body**.

The central component for this step is the **`org.springframework.web.reactive.HandlerResultHandler`** interface. It processes the `HandlerResult` created by `HandlerAdapter` and completes the response via `ServerWebExchange`. This lesson explains how result handlers are selected, the default implementations, reactive publishers, JSON/SSE/NDJSON payloads, response commit timing, write-time errors, and testing.

Scope: **Spring Boot 3.3.x + Spring Framework 6.1.x + Spring WebFlux**, Java 21. This covers the **reactive WebFlux stack**, not the Spring MVC Servlet stack. Examples use `spring-boot-starter-webflux` without adding `spring-boot-starter-web`, because when both starters are present Spring Boot normally prioritizes Servlet/MVC unless configured otherwise.

## 1. Where HandlerResultHandler Fits in the WebFlux Flow

High-level diagram of a WebFlux request with an annotated controller or functional route:

~~~text
HTTP client
   |
   v
Reactive HTTP server (Reactor Netty by default with starter-webflux)
   |
   v
HttpHandler / WebHttpHandlerBuilder
   |
   v
WebFilter chain -> WebHandler
   |
   v
DispatcherHandler
   |
   +-- HandlerMapping: finds matching handler
   |      +-- RequestMappingHandlerMapping (@Controller)
   |      +-- RouterFunctionMapping (functional endpoints)
   |
   +-- HandlerAdapter: invokes handler by type
   |      +-- RequestMappingHandlerAdapter
   |      +-- HandlerFunctionAdapter
   |
   +-- HandlerResult: holds return value + type + binding context...
   |
   +-- HandlerResultHandler: handles the returned result type
          +-- ResponseEntityResultHandler
          +-- ServerResponseResultHandler
          +-- ResponseBodyResultHandler
          +-- ViewResolutionResultHandler
                      |
                      v
          ServerWebExchange.getResponse()
                      |
             status / headers / codecs / views
                      |
               Mono<Void> completion
                      |
                      v
              HTTP response to client
~~~

Key distinctions:

- **`HandlerMapping`** decides which handler handles the request.
- **`HandlerAdapter`** knows how to execute that handler: resolve controller arguments, invoke the method or function, and package the result.
- **`HandlerResult`** describes the invocation result and required metadata.
- **`HandlerResultHandler`** knows how to turn a specific result kind into an actual response.
- **`ServerHttpResponse`** is the HTTP response abstraction; writing bytes over the network is ultimately handled by the runtime and codecs.

`DispatcherHandler` coordinates these pieces. It does not hard-code Jackson to serialize every DTO to JSON; writing the body is delegated to the appropriate result handlers and HTTP message writers.

## 2. The HandlerResultHandler Interface Has Two Methods

Conceptually, the contract is:

~~~java
package org.springframework.web.reactive;

import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public interface HandlerResultHandler {
    boolean supports(HandlerResult result);
    Mono<Void> handleResult(ServerWebExchange exchange, HandlerResult result);
}
~~~

This is an **illustrative API shape**, not code to copy into your project since the interface already ships in Spring WebFlux.

**`supports(HandlerResult)`** returns `true` when the implementation understands the result kind. For example, a handler for `ResponseEntity` checks the return type; a handler for `@ResponseBody` inspects annotations on the handler method as well.

**`handleResult(ServerWebExchange, HandlerResult)`** can set status/headers, select codecs or views, and write the response body. Its return value is **`Mono<Void>`**: an asynchronous completion or error signal, **not** the body sent to the client. A controller's return value and a result handler's return value live at two different layers.

Example:

~~~text
Controller returns: Mono<Message>
        |
        v
HandlerResult(returnValue = Mono<Message>, returnType = ...)
        |
        v
ResponseBodyResultHandler.handleResult(...)
        |
        v
Mono<Void>  <-- completes when the response-writing pipeline finishes
~~~

Never call `subscribe()` inside a controller just to get a response sent. The Spring WebFlux runtime subscribes and orchestrates the request/response pipeline. Subscribing manually detaches work from the response pipeline and can break error handling, cancellation, and backpressure along the request lifecycle.

## 3. What Information Does HandlerResult Carry?

`HandlerResult` is not just a plain Java object. It carries everything the framework needs to interpret the return value:

- The handler that was invoked (for example, the controller method).
- The actual return value (a DTO, `Mono`, `Flux`, `ResponseEntity`, `ServerResponse`, or `null`).
- Return type and generic type metadata, typically represented via `ResolvableType`.
- `BindingContext` and model/binding-related data.
- Where applicable, a `DispatchExceptionHandler` attached by the adapter to handle errors during the write phase.

For generic types in particular, `Flux<Message>` must be recognized as a stream of `Message` items to choose the right writer. Inspecting `Object.getClass()` alone would only reveal Reactor's publisher class, without inferring the element structure or media type.

Consider two different cases:

~~~java
Mono<Message>                  // body is produced asynchronously
Mono<ResponseEntity<Message>>  // status + headers + body are also resolved asynchronously
~~~

In the first case, the response body infrastructure uses reactive adapters, codecs, and content negotiation to write the DTO. In the second case, the emitted `ResponseEntity` must be unwrapped first to apply status and headers before writing the body.

`HandlerResult` is an internal WebFlux request-handling abstraction; applications rarely construct it directly when writing ordinary controllers.

## 4. How Does WebFlux Choose a Result Handler?

WebFlux collects all `HandlerResultHandler` beans from the application context, sorts them by order (`Ordered` / `@Order`), and picks the **first result handler whose `supports(result)` returns `true`**.

Default implementations in standard WebFlux configuration:

| Implementation | Result kinds typically handled | Default order |
| --- | --- | ---: |
| `ResponseEntityResultHandler` | `ResponseEntity` and reactive variants from annotated controllers | `0` |
| `ServerResponseResultHandler` | `ServerResponse` from functional endpoints | `0` |
| `ResponseBodyResultHandler` | `@ResponseBody` methods or `@RestController` classes, including reactive values | `100` |
| `ViewResolutionResultHandler` | View names, `View`, `Rendering`, models, and MVC-style view values | `Integer.MAX_VALUE` |

**Two result handlers sharing order `0` does not mean both write the response.** Their `supports` implementations differ, so normally only one handler is chosen for a given `HandlerResult`.

Why does `ResponseEntityResultHandler` come before `ResponseBodyResultHandler`? Because a method inside `@RestController` can still return `ResponseEntity<Message>`. The framework must treat it as a full HTTP response (status/headers/body) rather than serializing the `ResponseEntity` wrapper itself as a plain JSON DTO.

Why does `ViewResolutionResultHandler` come last? It supports a broad set of return shapes and needs to yield to more specific handlers ahead of it.

**This is not a sequential pipeline running through all four result handlers.** `DispatcherHandler` picks the first matching handler and lets it complete the result. Never assume "`ResponseBodyResultHandler` runs and then `ViewResolutionResultHandler` runs too."

## 5. ResponseBodyResultHandler: DTOs and @RestController

When a method carries `@ResponseBody` or lives inside `@RestController`:

~~~java
@RestController
class GreetingController {
    @GetMapping("/api/greeting")
    Mono<Greeting> greeting() {
        return Mono.just(new Greeting("Hello"));
    }
}

record Greeting(String message) {}
~~~

This snippet illustrates annotations and return types, not a full project. `ResponseBodyResultHandler` receives the result from the annotated controller and uses configured message writers to convert `Greeting` into JSON when content negotiation selects `application/json`.

High-level sequence:

~~~text
Mono<Greeting>
   |
   +-- ReactiveAdapterRegistry recognizes reactive type
   |
   +-- ResolvableType: element type is Greeting
   |
   +-- RequestedContentTypeResolver: negotiates media type
   |
   +-- Matching HttpMessageWriter (e.g., JSON encoder)
   |
   +-- ServerHttpResponse writes DataBuffers / bytes
   |
   +-- Mono<Void> completes or emits error
~~~

In WebFlux, the component writing response bodies is **`HttpMessageWriter`**, not `HttpMessageConverter` as in Spring MVC Servlet. Codecs that read and write can use Jackson, other encoders/decoders, or writers for text, binary, resources, and specific media types.

### 5.1. Mono, Flux, and Plain Value Types

| Controller return | Common meaning | Handling |
| --- | --- | --- |
| `Greeting` | DTO already available | Encoded into body per media type |
| `Mono<Greeting>` | 0 or 1 DTO produced asynchronously | Awaits publisher and encodes DTO |
| `Flux<Greeting>` | Multiple DTOs | Encodes multiple elements; framing depends on media type |
| `Mono<Void>` | Async work returning no payload | Completes response per endpoint contract |
| `ResponseEntity<Greeting>` | Direct status/headers/body | Dedicated `ResponseEntity` handler |
| `Mono<ResponseEntity<Greeting>>` | Status/headers/body known after publisher emits | `ResponseEntity` handler awaits result |
| `ResponseEntity<Flux<Greeting>>` | Status/headers known upfront, body is a stream | Writes streamed body with upfront status/headers |

**`Mono.empty()` does not automatically mean 404.** For an endpoint returning `Mono<DTO>`, without an explicit policy, an empty publisher does not automatically imply "resource not found." When you want 404, use `switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)))` or return `Mono<ResponseEntity<...>>` with a 404 branch.

### 5.2. Content Negotiation: Accept and produces

If the client sends `Accept: application/json` and the endpoint returns a DTO, WebFlux searches for a writer capable of producing that representation. If no acceptable representation exists, the server can return **406 Not Acceptable**. `@GetMapping(produces=...)` constrains the media types supported by the mapping.

`Content-Type` describes the format of the body being sent; `Accept` describes the format the client is willing to receive. Confusing those two headers frequently leads to 406/415 during testing.

### 5.3. Streaming Is More Than Changing the Return Type to Flux

A `Flux<T>` can be rendered as a JSON array, newline-delimited JSON, or Server-Sent Events depending on media type and encoder. Network streaming, per-item flushing, and client-observed latency depend on codecs, transport, proxies, and media types—not on the `Flux` type alone.

To transmit multiple JSON objects record by record, use `application/x-ndjson`. To push events over HTTP to browsers, use `text/event-stream`. Avoid returning `application/json` and assuming clients receive each object individually as soon as the server emits an element.

## 6. ResponseEntityResultHandler: Status, Headers, and Body

`ResponseEntity` describes a response containing status, headers, and body. WebFlux supports several async combinations:

~~~java
ResponseEntity<MyDto>
ResponseEntity<Mono<MyDto>>
ResponseEntity<Flux<MyDto>>
Mono<ResponseEntity<MyDto>>
Mono<ResponseEntity<Flux<MyDto>>>
~~~

Distinguish when metadata becomes known:

- **`ResponseEntity<Flux<T>>`**: the handler knows status and headers immediately when the method returns `ResponseEntity`; the body is still published/encoded later.
- **`Mono<ResponseEntity<T>>`**: status and headers are unknown until the publisher emits a `ResponseEntity`. Ideal when a query outcome decides 200 vs. 404.
- **`ResponseEntity<Mono<T>>`**: metadata is known upfront, while the body awaits a single value.
- **`Mono<ResponseEntity<Flux<T>>>`**: metadata is resolved asynchronously, and the body is then streamed.

Example when a resource might be absent:

~~~java
@GetMapping("/api/users/{id}")
Mono<ResponseEntity<UserView>> find(@PathVariable long id) {
    return userService.find(id)
        .map(user -> ResponseEntity.ok(new UserView(user.name())))
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

This is an **illustrative controller snippet**; it assumes `userService.find(id)` returns `Mono<User>` and `UserView` is declared. The idea is 200 when found and 404 when missing; it is not standalone code for `javac` without the service and model.

For an intentionally empty body, `ResponseEntity.noContent().build()` expresses **204 No Content** far more clearly than returning a `null` DTO and hoping the framework infers 204.

### 6.1. Cannot Change Status After Commit

Before the response is committed, the result handler can still set status and headers. Once headers have been sent/committed, changing status from 200 to 500 typically has no effect on that response. That is why an error mid-stream must be handled differently from an error before any body is written.

## 7. ServerResponseResultHandler: Functional Endpoints

In addition to annotated controllers, Spring WebFlux supports router functions:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route(
    RequestPredicates.GET("/fn/hello"),
    request -> ServerResponse.ok().bodyValue(Map.of("kind", "functional"))
);
~~~

The snippet above shows the API structure; in the complete project below the router is registered as a `@Bean`.

`RouterFunctionMapping` selects the handler function, `HandlerFunctionAdapter` executes the function and feeds the result into dispatch. `ServerResponseResultHandler` accepts the `ServerResponse` and lets it write status, headers, and body using the required message writers or view resolvers.

In functional endpoints, `ServerResponse` is the response abstraction of the **WebFlux functional API**. Do not confuse it with `WebClient`'s `org.springframework.web.reactive.function.client.ClientResponse`, or Spring MVC's `ServerResponse` in a different package.

Contrast example:

~~~java
// Annotated controller:
@GetMapping("/api/hello")
Mono<Map<String, String>> hello() { ... }

// Functional handler function:
request -> ServerResponse.ok().bodyValue(Map.of("hello", "webflux"))
~~~

They can produce identical HTTP JSON while being dispatched to **different result handlers**.

## 8. ViewResolutionResultHandler: Returning HTML/Views Instead of a JSON Body

A `@Controller` using an MVC-style view name:

~~~java
@Controller
class PageController {
    @GetMapping("/page")
    String page(Model model) {
        model.addAttribute("title", "Reactive page");
        return "home";
    }
}
~~~

With a configured view technology and matching `ViewResolver`, `ViewResolutionResultHandler` treats `"home"` as a **logical view name**, resolves a `View`, passes the model into the view, and renders the response (such as HTML).

However, if you use `@RestController` and return `String`:

~~~java
@RestController
class TextController {
    @GetMapping("/text")
    String text() {
        return "home";
    }
}
~~~

`"home"` is the **response body**, not a view name; `ResponseBodyResultHandler` takes precedence.

Note: `spring-boot-starter-webflux` alone does not include a template engine or a `home.html` template. To render HTML, add and configure an appropriate view technology (such as reactive Thymeleaf integration) and templates. Without a matching resolver or template, a view endpoint will error rather than silently returning `"home"` as plain text.

WebFlux does not support Servlet `forward:` dispatches as Spring MVC Servlet does. Use redirects or view mechanisms supported by WebFlux when navigation is needed.

## 9. From a Publisher to Bytes on the HTTP Response

Even though different result handlers handle different return types, writing the response passes through shared abstractions:

| Component | Meaning |
| --- | --- |
| `ServerWebExchange` | WebFlux request/response context, containing `ServerHttpRequest`, `ServerHttpResponse`, and exchange attributes |
| `ServerHttpResponse` | Sets status, headers, cookies, and writes the response body |
| `HttpMessageWriter<T>` | Encodes objects into an appropriate representation (JSON, text, binary, SSE...) |
| `Encoder` | Converts objects into `DataBuffer`s / byte streams for encoder-backed writers |
| `DataBuffer` | Buffer holding data written along the reactive pipeline |
| `Mono<Void>` | Represents completion/error of the HTTP write operation |
| `MediaType` | Representation format and framing negotiated between client and server |

Low-level operations on `ServerHttpResponse` include:

~~~java
response.setStatusCode(HttpStatus.OK);
response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
return response.writeWith(publisherOfDataBuffers);
~~~

This is only **illustrative code inside a `WebHandler` or custom result handler**, assuming valid `response` and `publisherOfDataBuffers`. In ordinary controllers, return DTOs or `ResponseEntity` so WebFlux selects writers for you rather than creating `DataBuffer`s manually.

An `HttpMessageWriter` selects how to encode based on type, generic type, media type, hints, and codec configuration. Do not assume every Java object turns into JSON automatically; Jackson/the appropriate codec must be on the classpath and the request must match an acceptable media type.

### 9.1. setComplete vs. writeWith

- `response.setComplete()` returns a completion publisher, suited when response metadata is set and no body is needed.
- `response.writeWith(Publisher<? extends DataBuffer>)` writes a publisher of data buffers.
- `response.writeAndFlushWith(Publisher<? extends Publisher<? extends DataBuffer>>)` expresses grouped buffers that should be flushed (when supported by transport).
- `response.beforeCommit(Supplier<? extends Mono<Void>>)` registers a callback before commit; the callback must return a publisher and suits pre-commit updates.

Do not call `writeWith` and then `setComplete` as a "required extra step" in business controllers. Operations must coordinate properly within the reactive pipeline; committing and completing the response are managed by the result handler's lifecycle.

### 9.2. When Is the Response Committed?

A response becomes committed when the infrastructure starts writing data to the client or completes the response; at that point status and headers can no longer be changed arbitrarily. `ServerHttpResponse.isCommitted()` is useful when writing error-handling infrastructure.

Do not use the moment a controller method `return`s to infer that the HTTP response has committed. With `Mono<ResponseEntity<T>>`, the method may return the publisher long before the publisher emits its value and determines the status.

### 9.3. Backpressure and Cancellation

WebFlux uses Reactive Streams to move data according to demand across layers. When a client reads slowly, the pipeline can emit fewer chunks or slow down; however, that **does not guarantee** every data source is automatically backpressure-aware or buffer-free.

When a client disconnects, response writing can receive cancellation or an error. Avoid uncancellable work inside publishers, and manage resources with operators like `usingWhen` and `doFinally` when needed.

## 10. Runnable Example: Spring Boot WebFlux With Four Result Shapes

The example below demonstrates one application containing:

- A REST controller returning `Mono<DTO>` → `ResponseBodyResultHandler`.
- A REST controller returning `Mono<ResponseEntity<DTO>>` or `ResponseEntity<Void>` → `ResponseEntityResultHandler`.
- A REST controller returning `Flux<DTO>` as NDJSON or `Flux<ServerSentEvent<String>>` → streaming response body.
- A functional route returning `Mono<ServerResponse>` → `ServerResponseResultHandler`.

Do not add a Servlet starter so the app does not default to Spring MVC. This example requires JDK 21 and a compatible Gradle wrapper.

~~~text
webflux-result-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/resultdemo/
    │   ├── ResultDemoApplication.java
    │   ├── ResultController.java
    │   └── FunctionalRoutes.java
    └── test/java/com/example/resultdemo/
        └── ResultControllerTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'webflux-result-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-webflux` typically pulls in Reactor Netty as the default web server. `reactor-test` is included explicitly in case `StepVerifier` is needed later; the tests here use `WebTestClient`. Dependency versions are managed by Spring Boot dependency management.

### 10.1. Main Application

**src/main/java/com/example/resultdemo/ResultDemoApplication.java**

~~~java
package com.example.resultdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResultDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResultDemoApplication.class, args);
    }
}
~~~

### 10.2. Controller With Multiple Return Types

**src/main/java/com/example/resultdemo/ResultController.java**

~~~java
package com.example.resultdemo;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ResultController {

    public record Message(String text) {
    }

    @GetMapping("/message")
    public Mono<Message> message() {
        return Mono.just(new Message("hello"));
    }

    @GetMapping("/accepted")
    public Mono<ResponseEntity<Message>> accepted() {
        return Mono.just(
            ResponseEntity.status(HttpStatus.ACCEPTED)
                .header("X-Result", "async")
                .body(new Message("queued"))
        );
    }

    @GetMapping("/empty")
    public ResponseEntity<Void> empty() {
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/lookup/{id}")
    public Mono<ResponseEntity<Message>> lookup(@PathVariable long id) {
        // Stub data to illustrate dynamic status without a database call.
        return Mono.justOrEmpty(id == 1L ? new Message("found") : null)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping(value = "/stream",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Message> stream() {
        return Flux.fromIterable(List.of(
            new Message("first"), new Message("second")));
    }

    @GetMapping(value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.just("alpha", "beta")
            .map(value -> ServerSentEvent.<String>builder()
                .event("item")
                .data(value)
                .build());
    }
}
~~~

Characteristics of these endpoints:

| URL | Return type | Expected result |
| --- | --- | --- |
| `GET /api/message` | `Mono<Message>` | 200 JSON with `text="hello"` |
| `GET /api/accepted` | `Mono<ResponseEntity<Message>>` | 202 Accepted, header `X-Result: async`, JSON |
| `GET /api/empty` | `ResponseEntity<Void>` | 204 No Content, no body |
| `GET /api/lookup/1` | `Mono<ResponseEntity<Message>>` | 200 JSON |
| `GET /api/lookup/2` | `Mono<ResponseEntity<Message>>` | 404 Not Found |
| `GET /api/stream` | `Flux<Message>` + NDJSON | 200, each object as one JSON record |
| `GET /api/events` | `Flux<ServerSentEvent<String>>` | 200 SSE, two events |

`lookup` uses stub data to illustrate sync/async results; in a real service, a `Mono` from a reactive database or client determines the outcome. `Flux.just(...)` and `Flux.fromIterable(...)` terminate finitely so `curl` exits cleanly; a real SSE stream may stay open indefinitely.

### 10.3. Functional Router

**src/main/java/com/example/resultdemo/FunctionalRoutes.java**

~~~java
package com.example.resultdemo;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Configuration
public class FunctionalRoutes {

    @Bean
    public RouterFunction<ServerResponse> exampleRoutes() {
        return route(GET("/fn/hello"),
            request -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("kind", "functional")));
    }
}
~~~

The functional handler builds `Mono<ServerResponse>` via `ServerResponse.ok().bodyValue(...)`. WebFlux selects the result handler matching `ServerResponse` rather than treating the function like a `@RestController`.

### 10.4. Running the Application

If a Gradle wrapper already exists:

~~~bash
./gradlew bootRun
~~~

If you created the project manually and have a compatible Gradle installation:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

On Windows PowerShell, use `.\gradlew.bat bootRun`. Without overrides, Spring Boot WebFlux usually opens port 8080; if the port is busy or configured differently, check the startup log.

Test endpoints with `curl`:

~~~bash
curl -i http://localhost:8080/api/message
curl -i http://localhost:8080/api/accepted
curl -i http://localhost:8080/api/empty
curl -i http://localhost:8080/api/lookup/1
curl -i http://localhost:8080/api/lookup/2
curl -i http://localhost:8080/fn/hello
~~~

Expected:

- `/api/message`: HTTP **200**, JSON `{"text":"hello"}`.
- `/api/accepted`: HTTP **202**, header `X-Result: async`, JSON `{"text":"queued"}`.
- `/api/empty`: HTTP **204**, no response body.
- `/api/lookup/1`: HTTP **200**, JSON `{"text":"found"}`.
- `/api/lookup/2`: HTTP **404**; the error body format can vary under default error handling.
- `/fn/hello`: HTTP **200**, JSON `{"kind":"functional"}`.

Header ordering, `Server` headers, and error-body formatting are not guaranteed to match across every environment. These results are **derived expectations from the source code**, not a transcript of an actual execution run.

### 10.5. NDJSON and SSE

NDJSON:

~~~bash
curl -i -N -H "Accept: application/x-ndjson" \
  http://localhost:8080/api/stream
~~~

Expected body:

~~~text
{"text":"first"}
{"text":"second"}
~~~

Each line is a complete JSON object; proxies and networks can affect when each chunk arrives. Do not interpret these two lines as a single JSON array.

SSE:

~~~bash
curl -i -N -H "Accept: text/event-stream" \
  http://localhost:8080/api/events
~~~

Expected events look like:

~~~text
event:item
data:alpha

event:item
data:beta

~~~

Event/data structure follows the SSE spec; metadata ordering and flush behavior depend on writer and transport. For long-lived SSE endpoints, connections can remain open for a long time; account for cancellation, resource cleanup, and proxy timeouts.

## 11. Testing Response Status, Headers, and JSON With WebTestClient

**src/test/java/com/example/resultdemo/ResultControllerTest.java**

~~~java
package com.example.resultdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(controllers = ResultController.class)
class ResultControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void bodyResultHandlerWritesJson() {
        client.get().uri("/api/message")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.text").isEqualTo("hello");
    }

    @Test
    void responseEntityResultHandlerWritesStatusAndHeader() {
        client.get().uri("/api/accepted")
            .exchange()
            .expectStatus().isAccepted()
            .expectHeader().valueEquals("X-Result", "async")
            .expectBody()
            .jsonPath("$.text").isEqualTo("queued");
    }

    @Test
    void noContentHasNoBody() {
        client.get().uri("/api/empty")
            .exchange()
            .expectStatus().isNoContent()
            .expectBody().isEmpty();
    }

    @Test
    void missingResourceBecomes404() {
        client.get().uri("/api/lookup/2")
            .exchange()
            .expectStatus().isNotFound();
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

`@WebFluxTest` creates a WebFlux test slice for the controller; `WebTestClient` sends requests into the WebFlux test chain without necessarily starting a socket-listening server. This test does not attempt to verify the functional router because `@WebFluxTest` only loads beans belonging to the slice, typically excluding general `@Configuration` or route beans.

To test **functional routes** in isolation, bind `WebTestClient` directly to a `RouterFunction` in a unit/slice test, or use `@SpringBootTest(webEnvironment = RANDOM_PORT)` and an HTTP client to test both the full application context and live server runtime.

The tests above prove the controller returns the expected responses. They do not prove Netty flushes chunks at specific timestamps or that the app handles real production load. Streaming and backpressure need separate tests using `StepVerifier`, multi-chunk client assertions, and cancellation tests.

## 12. Writing Status, Headers, and Response Body: Valid Ordering

In a reactive HTTP server, status and headers must be determined **before the response commits**. Conceptual safe sequence:

~~~text
HandlerResult
    |
    v
Select HandlerResultHandler
    |
    v
Determine status, headers, content type
    |
    v
Select HttpMessageWriter or View
    |
    v
Subscribe / produce body buffers
    |
    v
Commit response, write chunks, flush per media type
    |
    v
Complete or error/cancel
~~~

Do not assume every response only commits after the entire body has been generated. With streaming, status may already be sent before the last item is published.

### 12.1. Does ResponseBodyResultHandler Set Status Automatically?

It serializes the body and applies related response details. Status can come from annotations such as `@ResponseStatus`, exception handling, or other custom logic; without an override, HTTP 200 is the usual status for a successful response with a body.

For explicit and consistent statuses, return `ResponseEntity` or use appropriate status mechanisms. Do not rely on `Mono.empty()` implying HTTP 404.

### 12.2. HEAD and 204 Do Not Write Normal Bodies

HTTP **HEAD** requires the server not to send a representation body, even though representation headers may be present. With **204 No Content**, the response carries no message body; choose `ResponseEntity.noContent().build()` rather than encoding an ambiguous empty string.

### 12.3. Do Not Write the Response Twice

A common bug in custom `WebFilter`s or `WebExceptionHandler`s is writing a body and still letting downstream write more data into the same response. After commit, attempts to alter status/headers or write additional bytes can fail.

When intervening in the pipeline, be clear about who **owns** completion. In normal controllers, returning a `Publisher` and letting the framework's result handler write is the most maintainable approach.

## 13. Errors When the Return Value Is a Reactive Publisher

Errors can occur:

1. Immediately while the handler method is executing.
2. When the publisher is subscribed and emits an error signal before the first item.
3. While an encoder/codec serializes data.
4. After a streaming response has started and several items have already been written.
5. When the client disconnects or transport encounters an error.

What can still be changed in the response varies:

| Error timing | What can usually still be done |
| --- | --- |
| Before status/headers commit | Map error to a different status/body via exception handling |
| During codec selection / content negotiation | Usually still possible to return an error if uncommitted |
| After body has started streaming | Cannot change the already-sent HTTP status; typically must terminate/error the stream |
| After client has disconnected | Cannot send a new response to the client; clean up resources and log appropriately |

Spring WebFlux supports exception handling via annotated `@ExceptionHandler`, `@ControllerAdvice`/`@RestControllerAdvice`, `DispatchExceptionHandler`, and the `WebExceptionHandler` layer. They **cannot undo** a committed response. A late-stream error cannot turn an already-sent HTTP 200 into a 500.

Example when an app wants to return 404 if a `Mono` has no value:

~~~java
return service.find(id)
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(HttpStatus.NOT_FOUND)));
~~~

This is a code fragment assuming `service` and `id` exist. If `service.find(id)` yields no data, the error is emitted before any body; WebFlux has the opportunity to respond with 404. If a body stream is already underway and has sent data, the error handler cannot rewrite the earlier headers.

### 13.1. The onErrorResume Operator and Response Commit

`onErrorResume` switches errors to a fallback publisher within the **reactive chain**. Placing a fallback before the write phase gives the app explicit control over output. However, during stream serialization, items already sent to the client cannot be retracted; a fallback might become extra items in the stream rather than a brand-new HTTP response with a different status.

### 13.2. Do Not Manually Subscribe or Block on the Event Loop

In a reactive controller:

~~~java
// Wrong approach:
var value = remoteCall.block();

// Also avoid fire-and-forget to produce the body:
remoteCall.subscribe();
return Mono.empty();
~~~

This is an anti-pattern example, not a complete program. `block()` on an event loop can throw an error or degrade service throughput. An uncoordinated `subscribe()` detaches work from the request lifecycle, losing cancellation and error propagation.

Compose instead:

~~~java
return remoteCall.map(this::toResponse);
~~~

When legacy blocking I/O must be integrated, use an appropriate scheduler/adapter and cap concurrency, or choose Servlet/MVC when the workload is predominantly blocking. Do not treat `publishOn`/`subscribeOn` as an automatic fix for every bottleneck.

## 14. SSE, NDJSON, JSON Array, and Byte Stream: Choosing a Response Format

| Format | Common Content-Type | Payload shape | Recommendation |
| --- | --- | --- | --- |
| Single JSON | `application/json` | One JSON object | `Mono<DTO>` |
| JSON array | `application/json` | JSON array of multiple items | `Flux<DTO>` can be encoded as an array |
| NDJSON | `application/x-ndjson` | One JSON object per line | `Flux<DTO>` with `produces` NDJSON |
| SSE | `text/event-stream` | `event:`/`data:` events | `Flux<ServerSentEvent<T>>` |
| Text | `text/plain` | Character string | `Mono<String>` or string body |
| Binary | `application/octet-stream` | Byte/buffer stream | `DataBuffer`/`Resource` per endpoint |

The HTTP client must know how to read the chosen format. For instance, browser JavaScript `EventSource` understands SSE, but cannot parse NDJSON as an SSE stream. Conversely, a standard JSON parser does not treat multiple independent JSON-object lines as **a single JSON document**.

### 14.1. Streaming Has Real Overhead

A long-lived stream holds open a client connection and requires managing heartbeats, proxy idle timeouts, cancellation, and subscriber counts. Do not use SSE for every endpoint just to appear "reactive."

### 14.2. Response Encoding and Memory

Even when `Flux` emits item by item, a codec may require buffering/framing depending on content type. If an endpoint calls `collectList()` to wait for the entire `Flux` before returning, streaming benefits disappear and memory grows with item count. Design APIs for expected payload sizes and client consumption patterns.

### 14.3. Charsets and Binary

For text, writers need the right charset; UTF-8 is commonly used. For binary/streaming, manage `DataBuffer`s and resources carefully to avoid memory leaks, especially when manipulating buffers directly outside framework abstractions. When simply returning JSON or plain text, rely on default codecs rather than managing raw byte arrays manually.

## 15. Comparison With the Spring MVC Servlet Stack

| Criterion | Spring WebFlux | Spring MVC |
| --- | --- | --- |
| Front controller | `DispatcherHandler` | `DispatcherServlet` |
| Result after invoking handler | `HandlerResult` | MVC return-value handling |
| Response writing step | `HandlerResultHandler` + `HttpMessageWriter`/view | `HandlerMethodReturnValueHandler` + `HttpMessageConverter`/view |
| Server API | `ServerWebExchange` / `ServerHttpResponse` | Servlet `HttpServletRequest`/`HttpServletResponse` |
| Reactive types | First-class across the entire WebFlux pipeline | Supports reactive return types in some controller methods |
| I/O model | Reactive/non-blocking when dependencies and runtime support it | Default Servlet stack and synchronous APIs |
| Streaming | `Flux`, SSE/NDJSON, Reactive Streams | Servlet async/streaming depending on mechanism |
| Default Boot starter runtime | Reactor Netty (`starter-webflux`) | Tomcat (`starter-web`) |

**Do not use `HttpMessageConverter` as a generic name for every Spring web response writer.** In WebFlux, `HttpMessageWriter` is the characteristic reactive write-phase abstraction.

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Boot usually builds a Servlet application, routing requests through `DispatcherServlet` rather than `DispatcherHandler`. Inspect the classpath and startup logs before debugging "why `HandlerResultHandler` isn't called."

## 16. When Do You Need a Custom HandlerResultHandler?

The framework already handles almost all common return types. Only consider writing a custom `HandlerResultHandler` when the application genuinely needs a **specialized return type** supported uniformly across the system—for instance, a custom response wrapper or format that codec configuration or `ResponseEntity` cannot handle cleanly.

Skeleton example (illustrates the contract only, not a complete implementation):

~~~java
import org.springframework.web.reactive.HandlerResult;
import org.springframework.web.reactive.HandlerResultHandler;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class CustomResultHandler implements HandlerResultHandler {
    @Override
    public boolean supports(HandlerResult result) {
        // Only claim the specialized return type you actually own.
        return false;
    }

    @Override
    public Mono<Void> handleResult(
            ServerWebExchange exchange, HandlerResult result) {
        // When writing responses manually, manage status, headers,
        // codecs / DataBuffers, errors, commit, and cancellation.
        return exchange.getResponse().setComplete();
    }
}
~~~

This is an **API skeleton for learning role separation**; it is not registered as a bean and intentionally claims no results (`supports=false`). Do not copy this code into a project expecting it to write controller responses.

A real custom handler must:

1. Match only its own return type; avoid hijacking normal `@RestController` results.
2. Specify an appropriate `Ordered`/`@Order` so it does not unintentionally override built-in handlers.
3. Respect negotiated content types and codec/buffer ownership.
4. Handle async completion, cancellation, and pre-/post-commit errors.
5. Be tested across multiple return types alongside the default WebFlux config.

If you only need to change JSON formatting or add a codec, **configuring HTTP message codecs** is usually better than writing a result handler. If you only need different statuses or headers, **`ResponseEntity`** is simpler.

## 17. Common Mistakes and Misconceptions

### 17.1. "HandlerResultHandler Is the Same as HandlerAdapter"

False. The adapter **executes the handler**; the result handler **processes the result** packaged by the adapter. A controller method may be invoked properly and the client still get an error due to a missing codec or unsupported return type.

### 17.2. "All Four Result Handlers Write the Response in Sequence"

False. The dispatcher picks the **first handler that supports** the result according to order; it does not chain all four writers sequentially for the same value.

### 17.3. "Mono<Void> Means Every Endpoint Has an Empty HTTP Body"

False. `Mono<Void>` is the completion signal type of `HandlerResultHandler.handleResult`. Controllers can also return `Mono<Void>` in specific cases, yet the two contracts exist at different layers.

### 17.4. "Mono.empty() Automatically Returns 404"

Not automatically. Specify 404 explicitly with `ResponseEntity.notFound()` or `ResponseStatusException` in the chain.

### 17.5. "Returning String Is Always Plain Text"

False. In a `@Controller` without `@ResponseBody`, a `String` can be a **view name**. In a `@RestController`, a `String` is the **body**.

### 17.6. "Using Flux Means Clients Receive Every Object Immediately"

Not guaranteed. Media type, codecs, batching, flush behavior, proxies, and client buffering all play a role. Use NDJSON/SSE when explicit streaming framing is needed.

### 17.7. "Status 200 Can Be Changed to 500 After Partial Streaming"

No. Committed status/headers cannot be altered retroactively. Mid-stream errors need protocol-level handling and resource cleanup.

### 17.8. "Without @RequestBody, the Response Cannot Be JSON"

`@RequestBody` concerns **reading the request body**, whereas `@ResponseBody`/`@RestController` concerns **writing the response body**. Mixing up input decoding and output encoding sends debugging in the wrong direction.

### 17.9. "Spring WebFlux Also Uses HttpMessageConverter Like MVC"

False for native WebFlux: it uses `HttpMessageWriter`/`HttpMessageReader` and reactive codecs.

### 17.10. "Functional ServerResponse Is Identical to ResponseEntity"

Both express an HTTP response, yet belong to different APIs with different result handlers. WebFlux functional `ServerResponse` is handled by `ServerResponseResultHandler`; annotated-controller `ResponseEntity` is handled by `ResponseEntityResultHandler`.

### 17.11. "You Must Call subscribe() on Every Mono Returned From a Controller"

No. WebFlux infrastructure subscribes and tracks the HTTP response lifecycle. Fire-and-forget manual subscriptions lose cancellation, tracing, and error handling.

### 17.12. "WebFlux Is Always Faster Than MVC"

There is no such guarantee. If data sources block, `block()` is called on the event loop, or blocking database drivers are mishandled, throughput and latency can be worse. Choose the stack based on workload and end-to-end non-blocking capability.

### 17.13. "Checking HTTP 200 Alone Is Enough to Test Response Writers"

Insufficient. Also verify `Content-Type`, JSON schema, statuses on empty/error paths, headers, cancellation, streaming framing, and pre-/post-commit behavior.

## 18. WebFlux Result Self-Review Checklist

1. Is the app genuinely running **WebFlux REACTIVE**, or MVC SERVLET because both starters are present?
2. Which `HandlerMapping` matched the request: annotated controller or functional route?
3. Did `HandlerAdapter` produce a `HandlerResult` with the expected return value and type?
4. Which result handler returned `true` for `supports(result)`: `ResponseEntity`, `ServerResponse`, `ResponseBody`, or `View`?
5. Does the return type wrap `Mono`, `Flux`, or `ResponseEntity` outside or inside the reactive publisher?
6. Are status and headers determined before or after the publisher emits a value?
7. Which media type was negotiated from `Accept`, `produces`, and available writers?
8. Do JSON, NDJSON, SSE, or HTML views have the expected format and framing?
9. Are there any unnecessary manual `subscribe()` or `block()` calls in the request pipeline?
10. Are errors emitted before response commit or after data has already been sent?
11. Is any error handler trying to modify the response when `isCommitted()` is already `true`?
12. Could `DataBuffer` leaks or unbounded buffering occur, especially in large streams?
13. When a client disconnects, does the reactive pipeline clean up resources?
14. Do tests cover status, headers, body, empty cases, and error cases?
15. Do streaming tests verify content type, flushing, and client consumption?
16. Before writing a custom result handler, did you check whether codecs or `ResponseEntity` already solve the need?

**Conclusion:** In Spring WebFlux, `HandlerResultHandler` is the link that turns a handler's return value into an HTTP response. `ResponseBodyResultHandler` writes DTO/reactive bodies; `ResponseEntityResultHandler` handles `ResponseEntity` status, headers, and body; `ServerResponseResultHandler` serves functional endpoints; and `ViewResolutionResultHandler` renders views/models. Handler selection relies on return-type support and ordering, while response encoding and writing rely on message writers, media types, and the reactive pipeline. Understanding the boundary **mapping → adaptation → result handling → response write/commit** explains why a controller can execute cleanly yet produce the wrong response, and helps you design testable error handling and streaming.

## References

- [Spring Framework — DispatcherHandler, Result Handling](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): `HandlerResultHandler` implementations, ordering, and exception handling.
- [Spring Framework 6.1 — HandlerResultHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/HandlerResultHandler.html): `supports`, `handleResult`, `Mono<Void>`.
- [Spring Framework — WebFlux @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html): body encoding via `HttpMessageWriter`.
- [Spring Framework — WebFlux ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html): nested `Mono`/`Flux` and status/headers.
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): `RouterFunction`, `HandlerFunction`, `ServerResponse`.
- [Spring Framework — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): configuring and extending HTTP codecs.
