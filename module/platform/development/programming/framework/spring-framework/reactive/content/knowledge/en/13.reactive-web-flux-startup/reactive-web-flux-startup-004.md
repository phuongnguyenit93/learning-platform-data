# Connecting `HttpHandler` to a Non-Blocking Server in Spring WebFlux

## 1. Where does `HttpHandler` sit in the WebFlux architecture?

Spring WebFlux needs a common point of contact between **Spring's HTTP processing logic** and **the actual HTTP server**. `HttpHandler` is Spring's low-level abstraction for the lifecycle of a single request/response. The server receives connections and network data; an adapter converts the server's native request/response into Spring's abstractions; `HttpHandler` performs the reactive processing and returns a `Mono<Void>` that represents the completion of the response.

A typical architecture with Reactor Netty:

```text
HTTP client
    |
    | TCP / HTTP
    v
Reactor Netty HttpServer
    |
    | HttpServerRequest / HttpServerResponse
    v
ReactorHttpHandlerAdapter
    |
    | convert to ServerHttpRequest / ServerHttpResponse
    v
Spring HttpHandler
    |
    | if using the WebFlux stack
    v
HttpWebHandlerAdapter
    |
    | WebFilter, exception handling, WebHandler
    v
RouterFunction / annotated Controller / WebHandler
    |
    v
Mono<Void> completes the response
```

The components have different responsibilities:

- **`HttpServer`** is the Reactor Netty server: it binds the port, accepts connections, manages non-blocking I/O, and calls the handler for each request.
- **`ReactorHttpHandlerAdapter`** is the bridge between Reactor Netty's request/response API and Spring's `HttpHandler` interface.
- **`HttpHandler`** is Spring's HTTP processing contract; it does not open sockets or listen on ports by itself.
- **`HttpWebHandlerAdapter`** is the adapter at the WebFlux layer, converting `ServerHttpRequest`/`ServerHttpResponse` into a `ServerWebExchange` to call the `WebHandler`.
- **`WebHandler`** is the abstraction that handles a `ServerWebExchange`; WebFilters, exception handling, sessions, codecs, and controllers can be composed around this layer.

Therefore, connecting `HttpHandler` to a server means **plugging an implementation of `HttpHandler` into an adapter that the server understands**, so that the server calls it every time it receives a request. Business controllers do not need to know the details of sockets or Reactor Netty's own API.

## 2. The contract of `HttpHandler`

The interface `org.springframework.http.server.reactive.HttpHandler` has a core method:

```java
public interface HttpHandler {
    Mono<Void> handle(
            ServerHttpRequest request,
            ServerHttpResponse response
    );
}
```

This is the API signature for reference. `ServerHttpRequest` provides the method, URI, headers, and body; `ServerHttpResponse` lets you set the status/headers and write the body.

`Mono<Void>` has an important meaning:

- It completes (`onComplete`) when request processing and writing the response are done.
- It emits `onError` when processing fails.
- It can be cancelled (`cancel`) when the connection/request is no longer being consumed.
- It does not emit a `Void` value as a body; `Void` only signals completion.

A simple handler can return a fixed body:

```java
HttpHandler handler = (request, response) -> {
    response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
    byte[] bytes = "Hello from WebFlux".getBytes(StandardCharsets.UTF_8);

    DataBuffer buffer = response.bufferFactory().wrap(bytes);
    return response.writeWith(Mono.just(buffer));
};
```

This is an illustrative code snippet that requires importing the Spring and Reactor types. The handler does not call `.subscribe()` itself: it returns a `Mono<Void>` to the server adapter so the framework manages the lifecycle, errors, cancellation, and response writing.

## 3. The adapter connecting Spring to Reactor Netty

In Spring Framework, `ReactorHttpHandlerAdapter` implements a callback that Reactor Netty can invoke. In terms of usage, the connection involves three steps:

1. Create a Spring `HttpHandler`.
2. Wrap it in a `ReactorHttpHandlerAdapter`.
3. Register the adapter with `HttpServer.handle(...)`, then bind the server to an address/port.

```java
HttpHandler httpHandler = ...;

ReactorHttpHandlerAdapter adapter =
        new ReactorHttpHandlerAdapter(httpHandler);

DisposableServer server = HttpServer.create()
        .host("127.0.0.1")
        .port(8080)
        .handle(adapter)
        .bindNow();
```

`handle(adapter)` provides the request/response handling callback to Reactor Netty. When a request arrives, the adapter converts Netty's native objects into the corresponding Spring abstractions, calls `HttpHandler.handle(...)`, and returns the reactive result back to the server.

**The adapter is not a separate server.** It does not bind a port, manage sockets, or run the server lifecycle by itself. `HttpServer` is the component that listens for connections; the adapter only makes the two APIs compatible.

Besides Reactor Netty, Spring WebFlux can integrate with several other servers through corresponding adapters. The choice of server depends on the runtime/dependencies and how the application is deployed. Business logic at the `HttpHandler`/`WebHandler` layer should not depend on a particular server's own API unless truly necessary.

## 4. Composing a `WebHandler` into an `HttpHandler` with `WebHttpHandlerBuilder`

In a full WebFlux application, we usually do not write the entire HTTP layer ourselves. `WebHandler` handles a `ServerWebExchange`, while `WebHttpHandlerBuilder` assembles Spring's infrastructure components to create an `HttpHandler`.

A minimal `WebHandler`:

```java
WebHandler webHandler = exchange -> {
    exchange.getResponse().setStatusCode(HttpStatus.OK);
    exchange.getResponse().getHeaders()
            .setContentType(MediaType.TEXT_PLAIN);

    byte[] bytes = "Hello from WebHandler"
            .getBytes(StandardCharsets.UTF_8);

    DataBuffer buffer = exchange.getResponse()
            .bufferFactory()
            .wrap(bytes);

    return exchange.getResponse().writeWith(Mono.just(buffer));
};
```

You can build an `HttpHandler` from it:

```java
HttpHandler httpHandler =
        WebHttpHandlerBuilder.webHandler(webHandler).build();
```

Then pass `httpHandler` to `ReactorHttpHandlerAdapter` as in the previous section. In an application that uses an `ApplicationContext`, you can use the builder from the context to automatically find and assemble the suitable WebFlux infrastructure beans:

```java
HttpHandler httpHandler =
        WebHttpHandlerBuilder.applicationContext(applicationContext).build();
```

The builder can combine configured `WebFilter`s, `WebExceptionHandler`s, `WebSessionManager`, codecs, and other infrastructure components. Building from the `ApplicationContext` is usually more suitable for real Spring applications because it does not miss any WebFlux configuration.

Distinguishing three abstractions:

| Type | Input | Role |
|---|---|---|
| `HttpHandler` | `ServerHttpRequest`, `ServerHttpResponse` | Spring's low-level HTTP contract |
| `WebHandler` | `ServerWebExchange` | Handles request/response at the WebFlux layer |
| `ReactorHttpHandlerAdapter` | Reactor Netty's native request/response | Converts the server API into `HttpHandler` calls |

## 5. A runnable Java 17+ program: connecting `HttpHandler` to Reactor Netty yourself

The following example does not need Spring Boot. We use Spring's `HttpHandler`, the Reactor Netty adapter, and the `HttpServer` server directly to see the integration boundary clearly.

Directory structure:

```text
http-handler-reactor-netty/
├── pom.xml
└── src/main/java/demo/Main.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>http-handler-reactor-netty</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor.netty</groupId>
            <artifactId>reactor-netty-http</artifactId>
            <version>1.1.24</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/Main.java`:

```java
package demo;

import java.nio.charset.StandardCharsets;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.HttpHandler;
import org.springframework.http.server.reactive.ReactorHttpHandlerAdapter;

import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

public final class Main {
    public static void main(String[] args) {
        HttpHandler httpHandler = (request, response) -> {
            response.getHeaders().setContentType(
                    new MediaType("text", "plain", StandardCharsets.UTF_8)
            );

            String body = "Hello from HttpHandler\n";
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

            DataBuffer buffer = response.bufferFactory().wrap(bytes);
            return response.writeWith(Mono.just(buffer));
        };

        ReactorHttpHandlerAdapter adapter =
                new ReactorHttpHandlerAdapter(httpHandler);

        DisposableServer server = HttpServer.create()
                .host("127.0.0.1")
                .port(8080)
                .handle(adapter)
                .bindNow();

        System.out.println(
                "Listening on http://127.0.0.1:" + server.port()
        );

        // Wait for the server to stop on the main thread; do not block the event-loop thread.
        server.onDispose().block();
    }
}
```

From the directory containing `pom.xml`, you need JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

The server console shows:

```text
Listening on http://127.0.0.1:8080
```

Open another terminal and call:

```bash
curl -i http://127.0.0.1:8080/
```

Response body:

```text
Hello from HttpHandler
```

You may see the HTTP header `200 OK` and `Content-Type: text/plain;charset=UTF-8` (how headers are displayed may differ by client/server). Press `Ctrl+C` in the terminal running the server to stop the program.

**Reading the program by responsibility:**

1. The `HttpHandler` lambda receives Spring's request and response abstractions.
2. The handler sets the `Content-Type`, creates a `DataBuffer` from UTF-8 bytes, and returns `response.writeWith(...)`.
3. `ReactorHttpHandlerAdapter` turns Spring's handler into a callback that Reactor Netty understands.
4. `HttpServer.create()` configures the host/port; `.handle(adapter)` registers the callback; `.bindNow()` starts listening.
5. `server.onDispose().block()` keeps `main` waiting for the server to stop. This is a lifecycle wait on the **main thread of the console program**, not a `block()` call inside a handler or the event loop.

This example uses Spring Framework 6.1.14 and Reactor Netty 1.1.24 as an illustrative version set compatible with Java 17. In a real project, prefer managing versions in sync using the Spring Boot BOM or the project's dependency management, and avoid upgrading foundation libraries individually without checking compatibility.

## 6. The lifecycle of bind, request handling, and shutdown

A manually integrated server usually has this lifecycle:

```text
Create HttpHandler
     |
     v
Create ReactorHttpHandlerAdapter
     |
     v
HttpServer.create()
     |
     | handle(adapter)
     v
bindNow()
     |
     v
Server is listening
     |
     +---- request A -> adapter -> HttpHandler -> Mono<Void>
     |
     +---- request B -> adapter -> HttpHandler -> Mono<Void>
     |
     v
dispose / process shutdown
```

Common lifecycle methods:

- **`bind()`**: starts binding using the reactive API and returns the server's Publisher when the bind completes.
- **`bindNow()`**: waits for the bind to complete and returns a `DisposableServer`; convenient for simple bootstrap programs.
- **`onDispose()`**: a Publisher that completes when the server is disposed.
- **`dispose()`**: requests the server to stop.
- **`disposeNow()`**: requests a stop and waits, using the synchronous API.

Example of a controlled shutdown:

```java
server.dispose();
server.onDispose().block();
```

Use synchronous wait operations only on a suitable bootstrap/lifecycle thread, and do not call them in a request handler. A real application should integrate shutdown with the framework's lifecycle to close the server and related resources in the correct order.

When `bindNow()` fails (for example, the port is already used by another process), the application needs to report a startup error and not pretend the server is ready. In a deployment environment, the readiness probe should only succeed once the server has bound and the application can serve requests.

## 7. A non-blocking server does not mean all code is non-blocking

Reactor Netty uses an event loop and non-blocking I/O to serve many connections with a relatively small number of threads. However, a handler can still block the event loop if it calls a synchronous API:

```java
// COUNTER-EXAMPLE: a synchronous call runs right on the request-handling thread.
HttpHandler handler = (request, response) -> {
    LegacyDao dao = ...;
    Customer customer = dao.loadCustomer(); // may block I/O
    return writeCustomer(response, customer);
};
```

A non-blocking server **does not by itself turn** `dao.loadCustomer()` into asynchronous. When an event-loop thread is blocked, other connections sharing that event loop may slow down too.

Prefer truly reactive APIs for I/O, for example WebClient or R2DBC. If you must integrate a synchronous library, isolate that very call:

```java
Mono<Customer> customer = Mono.fromCallable(
        () -> legacyDao.loadCustomer()
).subscribeOn(Schedulers.boundedElastic());
```

`fromCallable` defers the call; `subscribeOn(boundedElastic)` moves the execution of the source to a scheduler suited to tasks that may block. Then compose the `Mono<Customer>` into the response pipeline. Do not call `.block()` to get the Customer in the handler; continue with `map`, `flatMap`, and return the final `Mono<Void>`.

Also, do not treat `Schedulers.boundedElastic()` as infinite capacity. You need timeouts for the client/DAO, concurrency limits, and monitoring of the load on the external system.

## 8. `DataBuffer` and writing the response correctly

Spring uses `DataBuffer` to represent byte data in the request/response. `ServerHttpResponse.writeWith(Publisher<? extends DataBuffer>)` lets you write a reactive sequence of buffers:

```java
Flux<DataBuffer> body = Flux.just("first\n", "second\n")
        .map(text -> response.bufferFactory().wrap(
                text.getBytes(StandardCharsets.UTF_8)
        ));

return response.writeWith(body);
```

This is an illustrative snippet that needs a `response` variable and the import of `Flux`. Using `Flux<DataBuffer>` is suitable when the response is produced gradually in pieces, such as streaming content or events.

Some points to note:

- **Do not gather an entire large body into one `byte[]` or `List<DataBuffer>`** if the goal is streaming; emit buffers one at a time as appropriate.
- `writeWith` returns a `Mono<Void>` representing the writing process, so you must return that Publisher from the handler.
- Do not call `.subscribe()` on the body yourself and then return `Mono.empty()`; that detaches the writing from the response lifecycle, easily causing the response to end too early or errors that the framework does not manage.
- Buffers may use a reference-counting mechanism depending on the implementation. When you allocate, retain, discard, or handle buffers yourself outside the standard flow, you must follow the implementation's retain/release rules; avoid releasing a buffer twice or releasing it before the server has finished writing.
- If you handle a streaming body, design error/cancel handling and cleanup appropriately; a client disconnect can cause the write to be cancelled.

## 9. Error handling at the `HttpHandler` layer

Because `HttpHandler` returns `Mono<Void>`, errors can be represented reactively:

```java
HttpHandler handler = (request, response) ->
        Mono.error(new IllegalStateException("Cannot serve request"));
```

This is an example that deliberately emits an error, not a complete handler. In a WebFlux stack assembled with `WebHttpHandlerBuilder`, `WebExceptionHandler` and other error handling components can take part in handling exceptions. If you implement `HttpHandler` directly yourself, clearly determine how to map errors to a status/body and make sure the response has not been committed before trying to write an error response.

Example of deliberate recovery for a business error:

```java
return service.load()
        .flatMap(value -> writeOkResponse(response, value))
        .onErrorResume(NotFoundException.class, error -> {
            response.setStatusCode(HttpStatus.NOT_FOUND);
            return response.setComplete();
        });
```

This is illustrative code that depends on `service`, `writeOkResponse`, and `NotFoundException`. When the response has been partially committed, it is not always possible to change the status or write a new error body. Avoid catching every error and returning `200 OK` with an empty body; keep the HTTP semantics correct and log/trace errors at an appropriate boundary.

## 10. Integrating with Spring Boot WebFlux: when do you need to create the adapter yourself?

In a typical Spring Boot application, the `spring-boot-starter-webflux` dependency provides WebFlux and a default reactive server (usually Reactor Netty if you don't choose another server). Spring Boot automatically configures the server, creates the adapter, and manages the lifecycle.

A controller can simply return a `Mono`:

```java
@RestController
class HelloController {
    @GetMapping("/hello")
    Mono<String> hello() {
        return Mono.just("Hello from WebFlux");
    }
}
```

In this flow, the developer does not need to create an `HttpServer` or `ReactorHttpHandlerAdapter` or call `bindNow()` themselves. The framework assembles the controller into a handler chain and a server adapter underneath.

Connecting `HttpHandler` yourself is useful when:

- Writing a small server application that does not use all of Boot's auto-configuration.
- Integrating Spring HTTP handling with a Reactor Netty server that is managed externally.
- Writing integration tests or a custom adapter at the server boundary.
- Learning how a request travels from the native server into Spring WebFlux.

Do not create a second Reactor Netty server yourself inside a Boot application just to handle one endpoint. That can open a port unintentionally, split the TLS/port/metrics configuration, make shutdown hard to manage, and create two server lifecycles in the same application.

If you need to customize Spring Boot's server, prefer Boot's official extension points and configuration. Manage `HttpServer` yourself only when the application truly needs to own that lifecycle.

## 11. Testing `HttpHandler` without opening a real port

With Spring WebFlux, you can test a handler through `WebTestClient` without binding a real server. `WebTestClient` supports binding directly to an `HttpHandler`:

```java
WebTestClient client = WebTestClient.bindToHttpHandler(httpHandler).build();

client.get()
        .uri("/")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("Hello from HttpHandler");
```

This is an illustrative test snippet. You need the suitable `spring-test` dependency and the import of `org.springframework.test.web.reactive.server.WebTestClient`. This approach checks the status and body at the `HttpHandler` boundary without occupying a TCP port. If you need to verify the Reactor Netty adapter, the real server configuration, TLS, timeouts, or network behavior, add an integration test on a suitable test port.

Testing should include:

1. A valid request returns the expected status/header/body.
2. An unsupported path or method returns a suitable status.
3. The body Publisher completes correctly, without nested subscribing or ending the response early.
4. Errors in the handler are mapped to the correct status/exception handler.
5. A client cancel/disconnect does not leak resources.
6. The server binds/shuts down in the correct lifecycle when running integration tests.

## 12. Common implementation mistakes

| Mistake | Consequence | How to handle |
|---|---|---|
| Treating `HttpHandler` as an HTTP server | There is no component that binds a port or receives sockets | Use a server such as Reactor Netty and the corresponding adapter |
| Putting Netty APIs directly into every service/controller | Business code gets locked to one server | Keep the logic at the `HttpHandler`/`WebHandler` or higher layer |
| Forgetting to wrap `HttpHandler` with an adapter before `HttpServer.handle` | Wrong callback type or missing bridge between the two APIs | Use `new ReactorHttpHandlerAdapter(httpHandler)` |
| The handler calls `.subscribe()` itself and returns `Mono.empty()` | The response-writing lifecycle is detached; errors/cancel are hard to manage | Return the `Mono<Void>` from `writeWith` or the final pipeline directly |
| Calling `block()` in a handler | Blocks the event-loop thread | Compose Publishers with `map`/`flatMap`; isolate blocking with `fromCallable` + `boundedElastic` |
| Creating a `DataBuffer` but not returning a Publisher that writes it | The response may be empty or end incorrectly | Return `response.writeWith(Mono.just(buffer))` or a Flux of buffers |
| Using `Mono.just(legacyDao.read())` | The blocking call runs eagerly on the current thread | `Mono.fromCallable(...).subscribeOn(boundedElastic())` |
| Creating a separate server in Spring Boot without managing shutdown | Port, TLS, metrics, and lifecycle are out of sync | Prefer Boot's auto-configuration/extension points |
| Thinking a non-blocking server automatically protects against blocking code | The event loop can still be stalled | Use reactive I/O, timeouts, and suitable schedulers |
| Handling errors after the response has been committed | Cannot safely change the status/body | Design the error boundary before commit, handle/log according to the response state |

## 13. Self-check exercises

**Question 1.** Does `HttpHandler` open port 8080 and accept TCP connections by itself?

**Answer:** No. It is only Spring's request/response processing contract. `HttpServer` or another server is what listens on the port.

**Question 2.** What is the job of `ReactorHttpHandlerAdapter`?

**Answer:** It converts Reactor Netty's native request/response into Spring abstractions and calls `HttpHandler`, then passes the reactive result back to the server.

**Question 3.** Why does `HttpHandler.handle(...)` return `Mono<Void>`?

**Answer:** To represent the processing and the completion of the response asynchronously; it emits complete/error/cancel rather than emitting a body value of type `Void`.

**Question 4.** How does `WebHandler` differ from `HttpHandler`?

**Answer:** `WebHandler` receives a `ServerWebExchange`; `HttpHandler` receives `ServerHttpRequest` and `ServerHttpResponse` directly. `HttpWebHandlerAdapter` joins the WebFlux layer to the low-level HTTP contract.

**Question 5.** Why not call `.block()` in `HttpHandler`?

**Answer:** The handler may run on an event-loop thread; block holds that thread while waiting and reduces the ability to serve other requests. Return a Publisher so the server manages it.

**Question 6.** Is `server.onDispose().block()` in `main()` the same as blocking in a request handler?

**Answer:** No. In the bootstrap example, the main thread waits for the server lifecycle; the request handler is still reactive. Do not move that way of waiting into an event-loop thread.

**Question 7.** When should you create a `ReactorHttpHandlerAdapter` yourself in Spring Boot?

**Answer:** Only when the application truly owns/integrates the server lifecycle itself or needs a custom adapter. For a normal Boot WebFlux application, the framework has already configured the server and adapter.

## 14. Rules to apply

- Keep the boundary clear: **the server receives the network → the adapter converts the API → `HttpHandler` handles it reactively**.
- Use `ReactorHttpHandlerAdapter` to connect `HttpHandler` to the Reactor Netty `HttpServer`.
- Use `WebHttpHandlerBuilder` when you need to assemble a `WebHandler` with WebFlux infrastructure components into an `HttpHandler`.
- Return the final `Mono<Void>` from the response write; do not subscribe inside the handler.
- Keep the event loop free of blocking; prefer reactive clients/drivers, or isolate legacy blocking with `fromCallable` + `boundedElastic`.
- Manage bind, shutdown, timeouts, DataBuffer, and errors according to the server's lifecycle.
- In Spring Boot, prefer auto-configuration; only create the server adapter yourself when you need to manage the integration at a low level.

**Remember:** `HttpHandler` is Spring's reactive HTTP contract, and `ReactorHttpHandlerAdapter` is the bridge that lets Reactor Netty call that contract. The server actually receives connections and manages I/O; the handler returns a `Mono<Void>` so that the whole process of writing the response, errors, and cancellation is coordinated according to the reactive lifecycle.
