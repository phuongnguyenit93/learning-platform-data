# HttpHandler and Server-Specific Adapters in Spring WebFlux

## 1. The problem: one WebFlux application running on many HTTP servers

Spring WebFlux provides a reactive HTTP processing model, but an application does not have to be tied to one specific server API. It can be deployed on **Reactor Netty**, **Tomcat**, **Jetty**, **Undertow**, or a suitable Servlet container. Each server has its own way of receiving requests, reading the body, writing the response, managing connections, and signaling that a client has disconnected.

If a controller had to know the Netty or Servlet API directly, business code would depend on the runtime and swapping servers would be very difficult. Spring places an intermediate contract called **HttpHandler** at the lowest level of the server-side reactive stack. **Server adapters** convert each server's own API into that common contract.

This lesson focuses on:

- The **HttpHandler** contract and the reactive request/response types.
- Distinguishing **HttpHandler**, **WebHandler**, **HttpWebHandlerAdapter**, and **DispatcherHandler**.
- The role of **WebHttpHandlerBuilder** in assembling filters, exception handlers, and the web handler.
- The adapters **ReactorHttpHandlerAdapter**, **ServletHttpHandlerAdapter**, **TomcatHttpHandlerAdapter**, **JettyHttpHandlerAdapter**, **JettyCoreHttpHandlerAdapter**, and **UndertowHttpHandlerAdapter**.
- The request/response flow, backpressure, cancellation, and DataBuffer.
- How Spring Boot auto-configures the adapter, and when manual server integration is needed.
- A runnable Java 17+ program that creates its own HttpHandler and attaches it to Reactor Netty.

## 2. Where HttpHandler sits in the WebFlux architecture

The architecture can be viewed as layers:

~~~text
Application:
  Annotated Controller / Functional Endpoint
                  |
                  v
  DispatcherHandler / WebHandler
                  |
          WebFilter chain
          WebExceptionHandler
                  |
                  v
  HttpWebHandlerAdapter
                  |
                  v
             HttpHandler
                  |
       Server-specific adapter
       /       |        |       \
 Reactor    Servlet   Tomcat   Jetty / Undertow
 Netty       API       API       native API
       \       |        |       /
                  |
                  v
             HTTP Server
                  |
                  v
               Client
~~~

The diagram above shows the layers; when a request is actually processed, the server-specific adapter calls into the HttpHandler, and then the web handler chain processes the request. The response and the completion signal flow back out to the server.

| Layer | Typical API | Responsibility |
| --- | --- | --- |
| Application model | Annotated Controller, Functional Endpoint | Describes routes and business logic |
| Web handler | **DispatcherHandler**, **WebHandler**, **WebFilter**, **WebExceptionHandler** | Handles requests at the web level: session, security/filters, and routing |
| HTTP abstraction | **HttpHandler**, **ServerHttpRequest**, **ServerHttpResponse** | Reactive request/response handling contract, independent of the server API |
| Adapter | **ReactorHttpHandlerAdapter**, **TomcatHttpHandlerAdapter**... | Converts between a specific server API and HttpHandler |
| Runtime | Reactor Netty, Tomcat, Jetty, Undertow | Manages sockets, connections, HTTP parsing, and I/O |

**HttpHandler is not a controller.** It does not map URLs to business methods and contains no application-level route logic. It only receives a request already represented by a Spring abstraction, writes the response, and returns a completion signal.

## 3. The HttpHandler contract

In Spring, the interface **org.springframework.http.server.reactive.HttpHandler** has one main method:

~~~java
Mono<Void> handle(
    ServerHttpRequest request,
    ServerHttpResponse response
);
~~~

Meaning:

- **ServerHttpRequest** represents the server-side request, including method, URI, headers, and body.
- **ServerHttpResponse** represents the response, allowing you to set the status, headers, and write the body.
- The return value **Mono<Void>** signals that response processing has completed or ended with an error.
- The request body can be read as a **Flux<DataBuffer>**.
- The response body is written using APIs that accept a Publisher, such as **writeWith(Publisher<? extends DataBuffer>)** or **writeAndFlushWith(...)** when flushing in batches is needed.

HttpHandler is a minimal abstraction for HTTP request handling with non-blocking I/O and Reactive Streams backpressure. It does not require the application to know whether the request came from Netty, Servlet, or another server API.

### 3.1. Low-level handler example

~~~java
HttpHandler handler = (request, response) -> {
    response.setStatusCode(HttpStatus.OK);
    response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

    String body = "Hello " + request.getURI().getPath();
    DataBuffer buffer = response.bufferFactory()
        .wrap(body.getBytes(StandardCharsets.UTF_8));

    return response.writeWith(Mono.just(buffer));
};
~~~

This is an illustrative snippet; the corresponding Spring and Reactor types need to be imported. The handler does the following:

1. Chooses the HTTP status.
2. Sets the Content-Type.
3. Creates a DataBuffer using the response's buffer factory.
4. Returns the Mono<Void> from writeWith so the framework knows when the response has finished being written.

In real code, you do not need to create an HttpHandler for each controller. Spring WebFlux already has a higher layer to manage routes and the request lifecycle. HttpHandler is usually the connection point between the whole WebFlux application and the server.

### 3.2. Why return Mono<Void>?

Mono<Void> represents a **completion signal**, not the response body. Response data is passed through ServerHttpResponse. When writeWith completes, the Mono<Void> completes; if the write fails, the Mono emits onError.

Do not call **block()** inside an HttpHandler to wait for the body to be written. That can block the event loop or the I/O-handling thread. Return the Publisher to the adapter and let the runtime coordinate the subscription.

## 4. Distinguishing HttpHandler from WebHandler

The two interfaces have similar names but sit at different layers:

~~~java
// Low-level HTTP layer
public interface HttpHandler {
    Mono<Void> handle(
        ServerHttpRequest request,
        ServerHttpResponse response
    );
}

// Higher-level Web layer
public interface WebHandler {
    Mono<Void> handle(ServerWebExchange exchange);
}
~~~

| Criterion | **HttpHandler** | **WebHandler** |
| --- | --- | --- |
| Package | org.springframework.http.server.reactive | org.springframework.web.server |
| Parameters | ServerHttpRequest, ServerHttpResponse | ServerWebExchange |
| Goal | Common contract for the HTTP server runtime | General-purpose API for web processing |
| Session / Principal / Locale | Not provided directly by this contract | Accessible via ServerWebExchange and related abstractions |
| Filter / exception chain | Not the place to declare these directly | Assembled by WebHttpHandlerBuilder |
| Controller / functional endpoint | Does not route directly | The foundation layer for the WebFlux programming model |

**ServerWebExchange** wraps the request and response, and also provides web capabilities such as attributes, session, principal, locale, and access to form/multipart data through the corresponding mechanisms.

HttpHandler can be seen as the very low-level boundary between Spring and the HTTP server; WebHandler is the convenient boundary for web applications.

## 5. HttpWebHandlerAdapter and WebHttpHandlerBuilder

### 5.1. What does HttpWebHandlerAdapter do?

**HttpWebHandlerAdapter** is an adapter on the Spring side that turns a **WebHandler** into an **HttpHandler**. It creates/prepares the ServerWebExchange from the ServerHttpRequest and ServerHttpResponse and then invokes the corresponding WebHandler chain.

This is why there are two kinds of adapters that are easy to confuse:

- **HttpWebHandlerAdapter:** converts from Spring's WebHandler API to Spring's HttpHandler contract.
- **ReactorHttpHandlerAdapter / ServletHttpHandlerAdapter / TomcatHttpHandlerAdapter...:** convert from the HttpHandler contract to the underlying server's API.

One adapter belongs to the **internal architecture of Spring WebFlux**, while the other belongs to the **runtime/server boundary**.

### 5.2. WebHttpHandlerBuilder assembles the web chain

**WebHttpHandlerBuilder** helps create a complete HttpHandler from a WebHandler and related components. The builder can receive an ApplicationContext to auto-detect beans, or be configured manually.

Conceptual example:

~~~java
HttpHandler httpHandler =
    WebHttpHandlerBuilder
        .applicationContext(applicationContext)
        .build();
~~~

When the ApplicationContext has a suitable WebFlux configuration, the builder can detect beans such as:

- The target **WebHandler**, usually DispatcherHandler.
- **WebFilter** for cross-cutting concerns.
- **WebExceptionHandler** for handling web errors.
- **WebSessionManager**.
- **ServerCodecConfigurer**.
- **LocaleContextResolver**.
- Observation components or decorators, supported depending on the version.

The processing chain, logically:

~~~text
HTTP request
    |
    v
WebExceptionHandler chain
    |
    v
WebFilter chain
    |
    v
WebHandler (usually DispatcherHandler)
    |
    v
Annotated Controller / Functional Handler
    |
    v
Mono<Void> completes the response
~~~

Exception handlers wrap around the outside of the filter chain so that they can handle errors that occur in the inner layers. The filter chain surrounds the WebHandler and can run logic before/after the handler.

### 5.3. When to use the builder manually?

In a typical Spring Boot WebFlux application, Boot auto-configures this chain. You do not need to create a WebHttpHandlerBuilder in every controller or service.

A manual builder is useful when:

- You integrate WebFlux yourself into an HTTP server that is embedded in a custom way.
- You create an HttpHandler from a standalone WebHandler.
- You write integration tests or a custom runtime environment.
- You need explicit control over filters, exception handlers, or decorators at the whole-application level.

Example using a hand-written WebHandler:

~~~java
WebHandler webHandler = exchange -> {
    exchange.getResponse().getHeaders()
        .setContentType(MediaType.TEXT_PLAIN);

    byte[] bytes = "Hello from WebHandler"
        .getBytes(StandardCharsets.UTF_8);

    DataBuffer buffer = exchange.getResponse()
        .bufferFactory()
        .wrap(bytes);

    return exchange.getResponse()
        .writeWith(Mono.just(buffer));
};

HttpHandler httpHandler =
    WebHttpHandlerBuilder.webHandler(webHandler).build();
~~~

This is an illustrative snippet. When using a hand-written WebHandler, it can be wrapped by HttpWebHandlerAdapter to become an HttpHandler. If you want controller mapping, you need to configure DispatcherHandler along with the related WebFlux components; a simple WebHandler does not create annotation controller routing on its own.

## 6. What is a server adapter?

Each HTTP server has its own API for receiving requests and writing responses. Spring's server adapter converts those events into a reactive abstraction:

- Receives the method, URI, headers, and body from the server.
- Provides ServerHttpRequest and ServerHttpResponse to the HttpHandler.
- Moves the byte/body stream between the native API and DataBuffer.
- Connects the request lifecycle to the Mono<Void>.
- Coordinates demand, asynchronous data writing, errors, and cancellation according to the runtime's capabilities.

The adapter **does not replace the HTTP server**. It also does not choose a controller or decide business routing. Its main job is to bridge two contracts.

### 6.1. Common adapters

| Server | Spring adapter | Target API | Notes |
| --- | --- | --- | --- |
| **Reactor Netty** | **ReactorHttpHandlerAdapter** | Reactor Netty HttpServer handling function | Fits the default runtime commonly used by Spring Boot WebFlux |
| **Servlet container** | **ServletHttpHandlerAdapter** | Servlet API, async and non-blocking I/O | Used when deploying WebFlux on a Servlet container |
| **Tomcat** | **TomcatHttpHandlerAdapter** | Tomcat-specific APIs | Optimizes the ByteBuffer read/write bridge using the Tomcat API |
| **Jetty** | **JettyHttpHandlerAdapter** | Jetty via Servlet integration | Available in the Spring Framework 6.1 line; deprecated in 6.2 in favor of JettyCoreHttpHandlerAdapter |
| **Jetty 12** | **JettyCoreHttpHandlerAdapter** | Jetty Core Handler API | Direct adapter, no intermediate Servlet layer needed |
| **Undertow** | **UndertowHttpHandlerAdapter** | Undertow HttpHandler | Bridge to Undertow's handler API |

Class names and the level of support depend on the Spring Framework version and the server version. Do not copy an adapter from one Spring version into a project that uses a different dependency version without first checking the corresponding Javadoc.

### 6.2. ReactorHttpHandlerAdapter

**ReactorHttpHandlerAdapter** converts a Spring HttpHandler into a handler function that Reactor Netty can register with HttpServer.

How to wire it:

~~~java
HttpHandler springHandler = ...;

ReactorHttpHandlerAdapter adapter =
    new ReactorHttpHandlerAdapter(springHandler);

HttpServer.create()
    .host("127.0.0.1")
    .port(8080)
    .handle(adapter)
    .bindNow();
~~~

Here Reactor Netty manages the server socket, connections, and the HTTP protocol. The adapter passes the request/response through the Spring abstraction, then returns a Mono<Void> so Reactor Netty can coordinate writing the response.

### 6.3. ServletHttpHandlerAdapter

**ServletHttpHandlerAdapter** is suitable when WebFlux runs on a Servlet container. The adapter uses **Servlet asynchronous processing** and **non-blocking I/O** support to connect the Servlet request/response with the HttpHandler contract.

The Servlet API is still present at the runtime layer, but the WebFlux application handler continues to use ServerHttpRequest, ServerHttpResponse, WebHandler, and Reactor.

### 6.4. TomcatHttpHandlerAdapter

**TomcatHttpHandlerAdapter** is a specialized adapter based on ServletHttpHandlerAdapter that uses Tomcat's own APIs to read/write data as **ByteBuffer**. When the application runs on Tomcat, Spring can use the corresponding bridge instead of having controllers depend directly on the Tomcat API.

### 6.5. JettyHttpHandlerAdapter and JettyCoreHttpHandlerAdapter

In Spring Framework 6.1 versions, **JettyHttpHandlerAdapter** integrates WebFlux through the Servlet layer and the Jetty API.

Since Spring Framework 6.2, **JettyHttpHandlerAdapter** has been deprecated in favor of **JettyCoreHttpHandlerAdapter**, an adapter that integrates directly with the Jetty 12 Core API without a Servlet layer. When upgrading Spring Framework/Jetty, you must choose the adapter that matches the version in use.

### 6.6. UndertowHttpHandlerAdapter

**UndertowHttpHandlerAdapter** converts a Spring HttpHandler into an **io.undertow.server.HttpHandler**. Undertow manages the server runtime; the adapter connects Undertow's request/response with Spring's reactive abstraction.

## 7. The flow of processing a request from server to controller

A GET request to a WebFlux endpoint can be pictured in these steps:

1. **The server receives the request:** Reactor Netty, Tomcat, Jetty, or Undertow accepts the connection and parses HTTP.
2. **The adapter creates the abstraction:** the server-specific adapter converts the native information into ServerHttpRequest/ServerHttpResponse.
3. **HttpHandler is invoked:** the adapter calls the handle method and receives a Mono<Void>.
4. **HttpWebHandlerAdapter creates the exchange:** the request/response are wrapped into a ServerWebExchange and passed into the web chain.
5. **WebExceptionHandler/WebFilter run:** handle exceptions, logging, security, CORS, or other common concerns.
6. **DispatcherHandler finds the handler:** maps the request to an annotated controller or functional endpoint.
7. **The controller returns a Publisher:** a Mono/Flux describes the data and when it completes.
8. **The codec writes the body:** Java data is encoded into DataBuffer/bytes according to the media type.
9. **The response is written:** the server adapter converts the DataBuffer to the native API and completes the response.
10. **Mono<Void> terminates:** notifies the runtime that response processing has completed; if there is an error, the error signal is handled through the appropriate exception chain.

~~~text
Client
  |
  v
HTTP Server (Netty / Tomcat / Jetty / Undertow)
  |
  v
Server Adapter
  |
  v
HttpHandler
  |
  v
HttpWebHandlerAdapter
  |
  v
WebExceptionHandler -> WebFilter -> DispatcherHandler
                                      |
                                      v
                         Controller / Functional Handler
                                      |
                                      v
                                  Mono / Flux
                                      |
                                      v
                              HTTP Message Codecs
                                      |
                                      v
                               ServerHttpResponse
                                      |
                                      v
                              Server Adapter -> Client
~~~

**Key takeaway:** a controller does not need to know whether the request was received by Netty or Tomcat. Changing the runtime is mainly a matter of dependencies and the adapter; the application programming model still uses Spring's abstractions.

## 8. DataBuffer, streaming, and backpressure at the HTTP boundary

### 8.1. Request body

**ServerHttpRequest.getBody()** provides a Flux<DataBuffer>. Instead of being forced to read the entire request body into a byte array, the handler can process data buffer by buffer. This is useful for streaming and large payloads.

~~~java
Flux<DataBuffer> body = request.getBody();
~~~

When consuming a DataBuffer, pay attention to buffer ownership and lifecycle, especially with Netty's pooled buffers. If the application retains a buffer or manages the reference count itself, it must follow the correct retain/release rules and use utilities such as DataBufferUtils where appropriate. Do not release a buffer that downstream still needs to read, and do not hold a buffer indefinitely beyond the request lifecycle.

### 8.2. Response body

**ServerHttpResponse.writeWith(...)** accepts a Publisher<DataBuffer>. Because the response data is a Publisher, writing can proceed according to demand and supports streaming instead of gathering all the data into RAM first.

~~~java
return response.writeWith(
    Flux.just(buffer1, buffer2, buffer3)
);
~~~

This is an illustrative snippet. In real code, buffers must be created at the right time, in the right order, and with a valid lifecycle. If you need to write multiple groups of buffers and flush each group, the **writeAndFlushWith(...)** API may be appropriate.

### 8.3. Backpressure at the server adapter

Reactive Streams backpressure lets a consumer signal its demand. At the HTTP boundary, the adapter and the server runtime need to coordinate reading/writing the body according to the capabilities of the underlying API.

Not every HTTP server has the same internal mechanism, but the goal of the abstraction is to keep a consistent reactive contract for the application. This does not mean no layer has any buffer. The server, network stack, codecs, and operators may have their own buffers; appropriate limits need to be configured.

### 8.4. Client disconnect and cancellation

If the client disconnects while the response Flux is still emitting, the runtime may trigger cancellation to the pipeline that is writing the response. Reactive work that is still active is asked to cancel. However, cancellation does not guarantee rollback of a side effect already committed to a database, or of an HTTP request already sent to another service.

Do not treat a client disconnect as evidence that the business operation was not performed. For write operations, you need a transaction, idempotency, or a compensation mechanism according to business requirements.

## 9. Manual integration with Reactor Netty: a runnable Java program

The following example creates a standalone HttpHandler, wraps it with ReactorHttpHandlerAdapter, and registers it with Reactor Netty. It does not use annotation controllers, because the goal is to see the boundary between HttpHandler and the adapter clearly.

It uses Spring Boot 3.3.5 (Spring Framework 6.1.x) and Java 17.

Structure:

~~~text
http-handler-adapter-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/adapter/
                └── HttpHandlerAdapterDemo.java
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>http-handler-adapter-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File **src/main/java/com/example/adapter/HttpHandlerAdapterDemo.java**:

~~~java
package com.example.adapter;

import java.nio.charset.StandardCharsets;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.HttpHandler;
import org.springframework.http.server.reactive.ReactorHttpHandlerAdapter;

import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

public class HttpHandlerAdapterDemo {

    public static void main(String[] args) {
        HttpHandler handler = (request, response) -> {
            response.setStatusCode(HttpStatus.OK);
            response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

            String message =
                "Handled by HttpHandler: " + request.getURI().getPath();

            DataBuffer buffer = response.bufferFactory()
                .wrap(message.getBytes(StandardCharsets.UTF_8));

            return response.writeWith(Mono.just(buffer));
        };

        ReactorHttpHandlerAdapter adapter =
            new ReactorHttpHandlerAdapter(handler);

        DisposableServer server = HttpServer.create()
            .host("127.0.0.1")
            .port(8080)
            .handle(adapter)
            .bindNow();

        System.out.println(
            "Listening on http://127.0.0.1:" + server.port()
        );

        server.onDispose().block();
    }
}
~~~

Run it in the directory containing pom.xml, with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.adapter.HttpHandlerAdapterDemo
~~~

Console:

~~~text
Listening on http://127.0.0.1:8080
~~~

Open another terminal and send a request:

~~~bash
curl -i http://127.0.0.1:8080/demo
~~~

Response body:

~~~text
Handled by HttpHandler: /demo
~~~

The response has status **200 OK** and Content-Type **text/plain**. You can change the path to /orders or /health to see that the handler uses the request's URI. Stop the server with Ctrl+C in the terminal running Maven.

### Program analysis

1. **HttpHandler** is the request-handling logic at Spring's common HTTP layer. The lambda does not use the Netty API.
2. **ServerHttpRequest** provides the URI; **ServerHttpResponse** provides the status, headers, and buffer factory.
3. **DataBuffer** holds the response content encoded in UTF-8.
4. **writeWith(Mono.just(buffer))** returns a Mono<Void>, signaling completion of the write operation.
5. **ReactorHttpHandlerAdapter** converts the HttpHandler into the handler type that Reactor Netty accepts.
6. **HttpServer.handle(adapter)** attaches the adapter to the server runtime.
7. **bindNow()** starts the server synchronously at the boundary of the CLI program; **server.onDispose().block()** keeps the main thread waiting until the server is disposed.

In a real WebFlux application, you should not create a second HttpServer yourself if Spring Boot already manages the server. This example deliberately creates the runtime itself to make the adapter clear.

## 10. Using other adapters when integrating manually

### 10.1. Servlet container

With a Servlet container, you can register **ServletHttpHandlerAdapter** as a Servlet:

~~~java
HttpHandler handler = ...;

Servlet servlet = new ServletHttpHandlerAdapter(handler);
~~~

The container manages the Servlet lifecycle, while the adapter connects the Servlet request/response with the HttpHandler. For applications deployed as a WAR, Spring provides mechanisms for initializing a reactive web application, such as **AbstractReactiveWebInitializer**, to register the adapter correctly.

### 10.2. Tomcat

In a Tomcat environment, Spring has a specialized adapter:

~~~java
Servlet servlet = new TomcatHttpHandlerAdapter(handler);
~~~

When setting up embedded Tomcat manually, you need to create a Context, register the Servlet, and map a URL for that Servlet. The server initialization depends on the Tomcat configuration and is unnecessary if Spring Boot already manages the embedded server.

### 10.3. Jetty

With Spring Framework 6.1, you may encounter:

~~~java
JettyHttpHandlerAdapter adapter =
    new JettyHttpHandlerAdapter(handler);
~~~

With Spring Framework 6.2 and Jetty 12, prefer the direct adapter:

~~~java
JettyCoreHttpHandlerAdapter adapter =
    new JettyCoreHttpHandlerAdapter(handler);
~~~

The newer adapter works with the Jetty Core Handler API. Do not use both adapters at the same time for the same request pipeline.

### 10.4. Undertow

With Undertow:

~~~java
UndertowHttpHandlerAdapter adapter =
    new UndertowHttpHandlerAdapter(handler);

Undertow server = Undertow.builder()
    .addHttpListener(8080, "127.0.0.1")
    .setHandler(adapter)
    .build();

server.start();
~~~

This is a snippet for a project that already has a compatible Undertow dependency and the corresponding Spring adapter. When stopping the server, you need to call **server.stop()** according to the application lifecycle.

The examples above illustrate where the adapter plugs in; TLS configuration, thread pools, port, context path, and shutdown for each server should follow the corresponding runtime's documentation.

## 11. How does Spring Boot auto-configure the adapter?

For a typical Spring Boot WebFlux application:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Boot detects the reactive web stack and configures WebFlux and the embedded server according to the dependencies/runtime on the classpath. With the common configuration, **Reactor Netty** is the default server. Spring Boot builds the HttpHandler chain and connects it to the corresponding adapter/server.

This means the application only needs to:

- Create a Spring Boot main class.
- Declare controllers or functional routes.
- Configure WebFilter, WebFluxConfigurer, or other required beans.
- Return Mono/Flux so the framework manages the subscription and response.

You do not need to write:

~~~java
new ReactorHttpHandlerAdapter(...);
HttpServer.create()...
~~~

in every ordinary Boot application. Only integrate manually when you deliberately manage the server runtime yourself or have a special embedding requirement.

### 11.1. Choosing the runtime via dependencies

The runtime options require compatible dependencies:

- Reactor Netty: usually pulled in by the default WebFlux starter.
- Tomcat or Jetty: requires the corresponding dependency/server configuration depending on the Spring Boot and Spring Framework versions.
- Undertow: requires a dependency and an adapter supported in the version in use.

If you add both **spring-boot-starter-web** and **spring-boot-starter-webflux**, Spring Boot usually prefers MVC when choosing the application type. So you should not infer that having Mono/Flux in a controller means the application is definitely running on WebFlux. Check the dependency tree and the actual server type at startup.

### 11.2. Do not enable @EnableWebFlux just to change the adapter

**@EnableWebFlux** is not a switch for choosing Reactor Netty/Tomcat/Jetty. It enables manual WebFlux configuration and can change how Boot auto-configuration behaves. The choice of server adapter belongs to the runtime/server layer, not to the function of the controller annotation.

## 12. HttpHandlerDecorator and cross-cutting concerns at the HTTP layer

Spring provides extension points around HttpHandler. **HttpHandlerDecorator** and **HttpHandlerDecoratorFactory** can be used to wrap a handler, for example to measure processing time at the HTTP boundary or to add instrumentation.

The decorator idea:

~~~java
HttpHandler decorated = (request, response) -> {
    long started = System.nanoTime();

    return delegate.handle(request, response)
        .doFinally(signal -> {
            long elapsedNanos = System.nanoTime() - started;
            metrics.record(elapsedNanos, signal);
        });
};
~~~

This is a snippet that assumes **delegate** and **metrics** are provided. The decorator wraps a single request-handling pass; **doFinally** runs when the stream ends with complete, error, or cancel.

It is important to distinguish:
- **WebFilter** is suited to processing at the web layer, with ServerWebExchange and WebFlux abstractions.
- **HttpHandlerDecorator** sits lower, wrapping the HttpHandler contract.
- **Server adapter** is the bridge to the server API and should not be used to write business logic.

If you only need a correlation ID, CORS, security, or request handling using the WebFlux API, WebFilter is usually the easier layer to use. Only choose the lower-level decorator when you need to observe or intervene across the whole HttpHandler chain.

## 13. Common errors and how to diagnose them

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| A Boot application starts but runs MVC | spring-boot-starter-web is present or the servlet stack is selected | Check the dependency tree and the application type log |
| Controller is not called | Handler mapping is not registered or the request does not match | Check DispatcherHandler, the mapping, method, and path |
| HttpHandler runs but the response does not finish | The handler's Mono<Void> does not complete or writeWith hangs | Check the body Publisher, errors, and cancellation |
| Response body is missing | DataBuffer lifecycle issue or the Publisher ends too early | Check buffer ownership, writeWith, and demand |
| Incompatible adapter | Spring Framework and server versions are mismatched | Check the Javadoc, dependency management, and server API |
| Jetty adapter class not found | Using a Spring version different from the example | Check whether it is Spring 6.1 or 6.2+ and the corresponding Jetty adapter |
| Two servers bind the same port | Boot creates a server itself but the code also creates an HttpServer manually | Let only one component own the port |
| Client disconnect causes an error | Cancellation or write failure in the response | Distinguish cancellation from business errors and complete |
| Memory grows when streaming a large body | The body is gathered in memory or buffers are unbounded | Stream DataBuffer, set codec/queue limits |
| Blocking reduces throughput | Calling block or a blocking API on the event loop | Use a reactive client or isolate blocking with an appropriate scheduler |
| Adapter runs but WebFilter does not work | Using a hand-written HttpHandler instead of a chain configured by the builder | Check WebHttpHandlerBuilder and the ApplicationContext |
| Errors are not converted into a suitable response | The WebExceptionHandler chain is not assembled into the handler | Check the builder/application context and exception handlers |

### 13.1. Investigation checklist

1. What is the actual server runtime?
2. Which dependency brings the server onto the classpath?
3. Which adapter is being used?
4. Was the HttpHandler created directly or via WebHttpHandlerBuilder?
5. Does HttpWebHandlerAdapter wrap the WebHandler chain?
6. Is DispatcherHandler configured and detected?
7. Are WebFilter and WebExceptionHandler in the ApplicationContext/chain?
8. Does the handler's Mono<Void> complete or error?
9. Do the request body and response body respect the DataBuffer lifecycle?
10. Is there blocking or a manual subscribe that detaches the request lifecycle?

## 14. Boundaries and design principles

**Keep business code at the WebHandler/controller layer, and keep server integration at the adapter layer.**

- Controllers should not depend on the Reactor Netty request/response.
- WebHandler should use ServerWebExchange when it needs the general-purpose web API.
- HttpHandler should only handle what belongs to the low-level HTTP contract.
- Adapters only convert server APIs and contain no business rules.
- When switching runtimes, check dependencies and server configuration; do not rewrite controllers just because the server changed.
- If Spring Boot is managing the server, do not create a second server on the same port.
- For large bodies, prefer streaming DataBuffer instead of gathering everything into a byte[].
- When a client disconnects, treat cancellation as part of the request lifecycle; do not roll back side effects by default.
- Choose the correct adapter version for the Spring Framework and server in use.
- Use WebFilter for cross-cutting concerns at the WebFlux layer; use HttpHandlerDecorator only when you truly need to wrap the entire HTTP handling contract.

## 15. Practice exercises

**Exercise 1 — Read the contract:** Rewrite the HttpHandler signature and explain why the method returns Mono<Void> even though the response has a body.

**Exercise 2 — Plain handler:** Change the response content in the Java program to JSON and set the Content-Type to application/json. Send a request with curl and check the body.

**Exercise 3 — Request body:** Extend the handler to accept a POST and read request.getBody(). Process the DataBuffer appropriately, without subscribing to the body twice and without retaining the buffer beyond its lifecycle.

**Exercise 4 — Builder:** Write a simple WebHandler and then use WebHttpHandlerBuilder.webHandler(...).build() to create an HttpHandler. Compare it with the direct lambda HttpHandler.

**Exercise 5 — Adapter:** Keep the HttpHandler unchanged and try wiring it into the Reactor Netty adapter. Identify which parts of the code would change if you switched to Servlet/Tomcat.

**Exercise 6 — Filter:** Add a WebFilter to the ApplicationContext and create the HttpHandler with WebHttpHandlerBuilder.applicationContext(...).build(). Verify that the filter runs before the WebHandler.

**Exercise 7 — Exception:** Create a WebExceptionHandler that handles errors emitted by the WebHandler. Observe the difference between an error that is converted into a response and an error that still propagates out of the HttpHandler.

**Exercise 8 — Cancellation:** Send a long response Flux, interrupt curl midway, and observe the cancellation. Identify which side effects had already completed before the client disconnected.

**Exercise 9 — Jetty versions:** Read the dependency tree of projects using Spring Framework 6.1 and 6.2. Find the corresponding Jetty adapter and the reason the API changed.

## 16. Key takeaways

**HttpHandler is Spring's lowest-level reactive HTTP contract, which keeps WebFlux from depending directly on the API of a specific server.** WebHandler provides the web API at a higher layer; WebHttpHandlerBuilder assembles the WebHandler, WebFilter, and WebExceptionHandler and then creates the HttpHandler via HttpWebHandlerAdapter. After that, a server-specific adapter such as ReactorHttpHandlerAdapter or the Servlet/Tomcat/Jetty/Undertow adapters connects the HttpHandler to the runtime.

Thanks to this boundary, controllers and functional endpoints continue to use Mono/Flux and Spring's abstractions when the server changes. When debugging, identify the right layer: route, WebHandler chain, HttpHandler contract, adapter, or server runtime.

## 17. References

- Spring Framework Reference — Reactive Core / HttpHandler: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework API — HttpHandler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/HttpHandler.html
- Spring Framework API — WebHttpHandlerBuilder: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/adapter/WebHttpHandlerBuilder.html
- Spring Framework API — ReactorHttpHandlerAdapter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ReactorHttpHandlerAdapter.html
- Spring Framework API — ServletHttpHandlerAdapter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServletHttpHandlerAdapter.html
- Spring Framework API — TomcatHttpHandlerAdapter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/TomcatHttpHandlerAdapter.html
- Spring Framework API — JettyCoreHttpHandlerAdapter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/JettyCoreHttpHandlerAdapter.html
- Spring Framework API — UndertowHttpHandlerAdapter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/UndertowHttpHandlerAdapter.html
- Reactor Netty Reference Guide: https://projectreactor.io/docs/netty/release/reference/
- Spring Boot Reference — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
