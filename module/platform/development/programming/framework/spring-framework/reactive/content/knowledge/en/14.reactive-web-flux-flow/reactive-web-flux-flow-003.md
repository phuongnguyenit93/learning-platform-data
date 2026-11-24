# ServerHttpRequest, ServerHttpResponse, and ServerWebExchange

**Module:** Spring Framework – reactive  
**Parent topic:** WebFlux processing flow

## Learning objectives

After this lesson, you can:

1. Distinguish the roles of `ServerHttpRequest`, `ServerHttpResponse`, and `ServerWebExchange` in one Spring WebFlux HTTP processing pass.
2. Read the method, URI, path, query parameters, headers, cookies, remote address, and request body using the appropriate reactive APIs.
3. Set the status, headers, and cookies and write the response body using `ServerHttpResponse`; understand when the response is committed.
4. Use `ServerWebExchange` to access the request/response, request attributes, session, principal, form/multipart data, and information that supports request processing.
5. Use these three abstractions in controllers and `WebFilter`, and know when to let message converters/codecs handle the body instead of manipulating `DataBuffer` manually.
6. Avoid reading the request body multiple times, changing headers after commit, blocking the event loop, or breaking the relationship between the reactive request and response.

## 1. Three abstractions in one HTTP exchange

In Spring WebFlux, an HTTP request enters the server and is passed through the reactive processing components. At the low level of Spring Web, three interfaces commonly appear together:

- `ServerHttpRequest` represents the **request the server received**: method, URI, path, headers, cookies, query parameters, connection address, and body.
- `ServerHttpResponse` represents the **response the server will send**: status, headers, cookies, and the operations that write the body/complete the response.
- `ServerWebExchange` represents the **entire request-response interaction**: it contains the request and response, and also provides request attributes, session, principal, locale, form/multipart data, log prefix, and some HTTP utilities.

```text
                 HTTP client
                     |
              request enters server
                     |
                     v
          +------------------------+
          |    ServerWebExchange   |
          |                        |
          |  +------------------+  |
          |  | ServerHttpRequest|  |
          |  | method, URI      |  |
          |  | headers, cookies |  |
          |  | body             |  |
          |  +------------------+  |
          |                        |
          |  +------------------+  |
          |  |ServerHttpResponse|  |
          |  | status, headers  |  |
          |  | cookies, body    |  |
          |  +------------------+  |
          |                        |
          | attributes, session,   |
          | principal, locale, ... |
          +------------------------+
                     |
              response goes out to client
```

You can picture `ServerWebExchange` as the "envelope" of one HTTP pass; the request and response are the two parts inside. A `WebFilter` receives the exchange to intervene before/after the handler. An annotated controller can receive `ServerHttpRequest`, `ServerHttpResponse`, or the whole `ServerWebExchange` directly as a method argument.

These three interfaces belong to the reactive server API. They are not Servlet classes such as `HttpServletRequest`/`HttpServletResponse`. Do not use the Servlet API in a purely reactive WebFlux handler.

## 2. ServerHttpRequest: reading the request on the server side

The full type:

```java
org.springframework.http.server.reactive.ServerHttpRequest
```

`ServerHttpRequest` provides HTTP information and the body in the form of a publisher. Commonly used APIs:

| API | Meaning |
| --- | --- |
| `getMethod()` / `getMethodValue()` | The method, for example GET, POST, PUT, DELETE. |
| `getURI()` | The request URI, which may include the query string. |
| `getPath()` | The path as a `RequestPath`, with context path information and the path within the application. |
| `getHeaders()` | Headers as `HttpHeaders`; read from the request. |
| `getQueryParams()` | Query parameters already parsed/decoded into a `MultiValueMap<String, String>`. |
| `getCookies()` | Cookies received from the client. |
| `getBody()` | The body as a `Flux<DataBuffer>`, i.e. a stream of byte buffers. |
| `getRemoteAddress()` | The address of the connecting peer, if the server provides it. |
| `getId()` | An ID for correlating connection/request, if available. |
| `mutate()` | Creates a builder to produce a request decorator with adjusted properties. |

### 2.1. Method, URI, path, and query parameters

An example request:

```http
GET /api/orders/42?includeItems=true&lang=vi HTTP/1.1
Host: localhost:8080
Accept: application/json
X-Client-Version: 2.1
```

You can read the fields with:

```java
HttpMethod method = request.getMethod();
URI uri = request.getURI();
String path = request.getPath().value();
MultiValueMap<String, String> query = request.getQueryParams();

String includeItems = query.getFirst("includeItems");
String language = query.getFirst("lang");
String clientVersion = request.getHeaders().getFirst("X-Client-Version");
```

This is an **illustrative snippet** inside a controller or WebFilter; the corresponding Spring types need to be imported. Query parameters are a multi-value map because the same name can appear multiple times, for example `?tag=java&tag=reactive`. Use `getFirst` when you only need the first value; use `get` to get the whole list.

`getPath().value()` returns the path as represented by `RequestPath`. If you need to process path segments, use the `RequestPath` API instead of cutting the URI string yourself, especially when there are encoded characters, a context path, or path parameters.

### 2.2. Headers and cookies

`getHeaders()` lets you read information such as:

```java
String contentType = request.getHeaders().getFirst(HttpHeaders.CONTENT_TYPE);
String authorization = request.getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
List<String> accepted = request.getHeaders().get(HttpHeaders.ACCEPT);

HttpCookie sessionCookie = request.getCookies()
        .getFirst("SESSION");
```

This is an illustrative snippet. Request headers/cookies are data sent by the client; do not treat them as trustworthy just because they have familiar names. For example, do not grant permissions based solely on an `X-User-Id` or `X-Role` that the client sends itself. Use Spring Security and `exchange.getPrincipal()` or a verified authentication mechanism.

### 2.3. Remote address and forwarded headers

`getRemoteAddress()` usually reflects the peer directly connected to the server. If the application sits behind a reverse proxy or load balancer, this address may be the proxy, not the end user's device.

The `Forwarded` and `X-Forwarded-*` headers should only be interpreted when the proxy at the trust boundary is configured to overwrite/remove values the client sends itself and the application has enabled the appropriate forwarded-headers handling. Do not simply take the first `X-Forwarded-For` as an identity or a basis for authorization without determining the trusted proxy chain.

### 2.4. The request body is a Flux<DataBuffer>

`ServerHttpRequest` inherits the reactive input message API; `getBody()` returns a `Flux<DataBuffer>`. A large body can be received as many buffers, and there is no guarantee that one `DataBuffer` corresponds to one HTTP packet or to the whole body.

```java
Flux<DataBuffer> rawBody = request.getBody();
```

The snippet above only obtains the publisher that describes the body; the data is consumed when the chain has a subscriber. **The body is a stream that must be managed**, not a string on which you can call `getBody()` multiple times to read again from the start. If a filter consumes the body itself, the downstream handler may no longer have data. To read and forward the body, you need a cache/replay mechanism and a correct decorator; this must manage memory, backpressure, and the `DataBuffer` lifecycle.

In a controller, you should usually let Spring WebFlux decode the body via `@RequestBody`:

```java
@PostMapping("/orders")
public Mono<OrderResult> create(@RequestBody Mono<CreateOrderRequest> body) {
    return body.flatMap(orderService::create);
}
```

This is an **illustrative snippet**; `CreateOrderRequest`, `OrderResult`, and `orderService` are defined by the application. This approach uses message readers/codecs to convert the body into a Java type. Only manipulate `DataBuffer` directly when there is a low-level requirement such as proxying, streaming, or special byte processing.

### 2.5. Form and multipart

`ServerWebExchange` provides `getFormData()` and `getMultipartData()` in reactive form. These APIs use message readers to parse the body into a suitable structure. URL-encoded form data is returned as `Mono<MultiValueMap<String, String>>`; multipart data is returned as `Mono<MultiValueMap<String, Part>>`.

Parsing form/multipart may read the entire body, and the parsed result is cached so that calling the corresponding methods is safer. Even so, do not consume the raw body yourself at the same time and then ask the framework to parse it again. For large multipart content that needs streaming, consider `Flux<PartEvent>` instead of gathering all the parts into a map.

## 3. ServerHttpResponse: building the response

The full type:

```java
org.springframework.http.server.reactive.ServerHttpResponse
```

`ServerHttpResponse` lets the application set the response's state and metadata, then write the body as a publisher. Commonly encountered APIs:

| API | Meaning |
| --- | --- |
| `setStatusCode(HttpStatusCode)` | Sets the HTTP status, for example 201, 204, 404, or 503. |
| `getStatusCode()` | Reads the current status; it may not have been set explicitly. |
| `getHeaders()` | The response headers. |
| `getCookies()` | Cookies that will be sent to the client. |
| `isCommitted()` | Checks whether the response has been committed. |
| `beforeCommit(Supplier<Mono<Void>>)` | Registers a reactive action that runs right before the commit. |
| `writeWith(Publisher<DataBuffer>)` | Writes the body from a DataBuffer publisher. |
| `writeAndFlushWith(Publisher<Publisher<DataBuffer>>)` | Writes groups of buffers and flushes after each group's publisher. |
| `setComplete()` | Completes the response without a body written by the application. |

### 3.1. Set the status and headers before the response commits

Example:

```java
response.setStatusCode(HttpStatus.CREATED);
response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
response.getHeaders().set("X-Request-Source", "webflux");
```

This is an **illustrative snippet**. Headers and status must be set before the response is committed (usually when the body starts being written or when the server completes the response). After the commit, you cannot freely change the status or headers already sent to the client; late changes may be ignored or no longer take effect.

`beforeCommit` is for operations that need to run exactly before the commit:

```java
response.beforeCommit(() ->
        Mono.fromRunnable(() ->
                response.getHeaders().set("X-Processed", "true")));
```

This is an **illustrative snippet**. The Supplier must return a publisher so that the action is performed properly within the commit chain; do not call `subscribe()` inside the callback. `beforeCommit` is not the place to run blocking tasks or long-running work.

### 3.2. Writing the body with writeWith

A small response can be written directly:

```java
byte[] bytes = "Hello from WebFlux".getBytes(StandardCharsets.UTF_8);
DataBuffer buffer = response.bufferFactory().wrap(bytes);

response.setStatusCode(HttpStatus.OK);
response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
return response.writeWith(Mono.just(buffer));
```

This is an **illustrative snippet in a handler that returns `Mono<Void>`**; it needs imports for `DataBuffer`, `Mono`, and `StandardCharsets`. `writeWith` accepts a publisher of buffers and returns a `Mono<Void>` representing the write completing or failing. You must **return this publisher** so that WebFlux/the server can track the response-writing lifecycle.

Do not both call `writeWith` manually and return a different body for the framework to write again. If you want to use manual writing, the method usually returns `Mono<Void>` and that chain is the result of response processing.

When working with `DataBuffer`, you need to understand ownership and release on the error/cancel/discard paths. Spring's codecs usually manage the buffers they create; when you create or hold pooled buffers yourself, use `DataBufferUtils` and the API guidance to release them at the right time, avoiding leaks or double release.

### 3.3. writeAndFlushWith for streaming

`writeAndFlushWith` accepts a nested publisher: each inner publisher contains a group of `DataBuffer`s. The server flushes after each group. This is useful for content that needs to be sent in batches, but it is not the default way to write every JSON response.

An illustrative example of the structure:

```java
Publisher<Publisher<DataBuffer>> chunks = ...;
return response.writeAndFlushWith(chunks);
```

This is an **illustrative snippet**; you need to build a buffer publisher appropriate to the response protocol. For SSE, you usually use `Flux<T>` and `MediaType.TEXT_EVENT_STREAM` so that the Spring codec encodes each event; there is no need to create buffers/flush yourself unless there is a specific low-level reason.

### 3.4. setComplete when there is no body

```java
response.setStatusCode(HttpStatus.NO_CONTENT);
return response.setComplete();
```

This is an illustrative snippet in a handler. `204 No Content` is a successful response without a body. `setComplete()` returns a `Mono<Void>`, so you must still return/compose that publisher so the completion is managed.

### 3.5. Cookies

`getCookies()` on the response returns a cookie map to which you can add or configure response cookies. In real code, prefer `ResponseCookie` to set attributes such as `Path`, `Max-Age`, `Secure`, `HttpOnly`, and `SameSite` in line with the security policy.

```java
ResponseCookie cookie = ResponseCookie.from("theme", "dark")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .build();

response.addCookie(cookie);
```

This is an **illustrative snippet**; you need to import `ResponseCookie`. `Secure` only sends the cookie over HTTPS. `HttpOnly` prevents browser-side JavaScript from reading the cookie, but does not by itself prevent CSRF; you need a SameSite policy, CSRF protection, and appropriate domain/path configuration.

## 4. ServerWebExchange: the context of the entire request

The full type:

```java
org.springframework.web.server.ServerWebExchange
```

An exchange wraps the current request-response and the data that supports server-side processing. Important methods:

| API | Meaning |
| --- | --- |
| `getRequest()` | Gets the current `ServerHttpRequest`. |
| `getResponse()` | Gets the current `ServerHttpResponse`. |
| `getAttributes()` | A mutable map holding the exchange/request's own attributes. |
| `getAttribute(name)` / `getAttributeOrDefault` | Reads a request attribute. |
| `getRequiredAttribute(name)` | Gets a required attribute; reports an error if missing. |
| `getSession()` | Gets the request's `Mono<WebSession>`. |
| `getPrincipal()` | Gets a `Mono<Principal>` if the request is authenticated. |
| `getLocaleContext()` | Gets the configured locale context. |
| `getFormData()` | Parses URL-encoded form data via a reactive API. |
| `getMultipartData()` | Parses the multipart body via a reactive API. |
| `checkNotModified(...)` | Supports ETag/Last-Modified conditions and the 304 response. |
| `getLogPrefix()` | A prefix for correlating logs per request. |
| `mutate()` | Creates a builder to wrap the exchange with an adjusted request/response/principal. |

### 4.1. Request attributes are only for the current exchange

Attributes are suitable for passing data between a WebFilter and a handler within the **same request**, for example a correlation ID, the start time, the result of an internal check, or verified data.

```java
exchange.getAttributes().put("traceId", traceId);

String value = exchange.getAttributeOrDefault(
        "traceId", "missing");
```

This is an **illustrative snippet**. Attributes are not a global application cache, not a session, and are not automatically saved to the next request. Do not use a static map or a mutable field in a singleton in place of request attributes, because many requests can run concurrently.

### 4.2. Session and principal are reactive

`getSession()` returns a `Mono<WebSession>`, while `getPrincipal()` returns a publisher containing the principal if present. Do not call `block()` to obtain them in a WebFlux handler.

```java
return exchange.getPrincipal()
        .map(Principal::getName)
        .defaultIfEmpty("anonymous");
```

This is an illustrative snippet that returns a `Mono<String>`. The result can be empty when there is no principal; `defaultIfEmpty` only handles the empty case, not an authentication error. Actual authentication/authorization should be performed through Spring Security and the corresponding policies.

### 4.3. checkNotModified for ETag and Last-Modified

When there is a cacheable representation, the server can use an `ETag` or a modification time to avoid resending an unchanged body. `exchange.checkNotModified(etag)` or the overload with an additional `Instant lastModified` can prepare the appropriate status/headers for a conditional request and return `true` when no further processing is needed.

This is an HTTP utility with specific semantics, not an arbitrary string comparison. The ETag must represent the actual version of the content; if the data has changed but the old ETag is still used, the client may keep a wrong cache.

### 4.4. Mutating the exchange and request

The request/response/exchange APIs are mostly abstractions that can be wrapped/decorated. When you need to modify request properties for downstream filters/handlers, use the builder instead of trying to modify the original object:

```java
ServerWebExchange updated = exchange.mutate()
        .request(builder ->
                builder.headers(headers ->
                        headers.set("X-Internal-Check", "passed")))
        .build();

return chain.filter(updated);
```

This is an **illustrative snippet in a WebFilter**. `mutate()` creates an exchange decorator; `request(builder -> ...)` creates a request decorator with the changed header. Downstream components receive the new exchange via `chain.filter(updated)`. The original request is not modified in place.

Only add internal headers that the server controls; do not use this approach to trust an authentication header the client sends itself. If you want to change response behavior at a low level, you can use `ServerHttpResponseDecorator` and place it in a new exchange, but you need to understand the write/commit mechanics and DataBuffer ownership thoroughly.

## 5. Using the three abstractions in a WebFilter

`WebFilter` is the right place to handle concerns that cut across many endpoints: trace ID, audit metadata, header checks, processing time, or common request policies. The signature:

```java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain)
```

`WebFilterChain.filter(exchange)` passes the request to the next filter and the final handler. A filter should **compose and return** the chain's publisher; do not `subscribe()` to it yourself. You can attach operators to observe before/after:

```java
return chain.filter(exchange)
        .doOnError(error -> logFailure(exchange, error))
        .doFinally(signal -> recordCompletion(exchange, signal));
```

This is an **illustrative snippet**. `doFinally` can receive `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`; an upstream cancellation does not necessarily mean the client closed the connection, because another operator can also cancel. Place hooks close to the right boundary and use the request correlation ID to read logs.

### 5.1. A complete filter: attaching a trace ID and measuring time

This example creates a trace ID, stores it in the exchange attributes, adds a response header, and records the result when the request ends:

```java
@Component
public class RequestTraceFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String traceId = UUID.randomUUID().toString();
        exchange.getAttributes().put("demo.traceId", traceId);

        ServerHttpRequest request = exchange.getRequest();
        ServerHttpResponse response = exchange.getResponse();
        response.getHeaders().set("X-Trace-Id", traceId);

        long started = System.nanoTime();

        return chain.filter(exchange)
                .doFinally(signal -> {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started);

                    System.out.printf(
                            "%s %s -> %s [%s] %dms%n",
                            request.getMethodValue(),
                            request.getURI().getPath(),
                            response.getStatusCode(),
                            signal,
                            elapsedMs);
                });
    }
}
```

This is **an illustrative class** that needs the imports `UUID`, `TimeUnit`, `Component`, `ServerWebExchange`, `ServerHttpRequest`, `ServerHttpResponse`, `WebFilter`, `WebFilterChain`, and `Mono`. The header is set before the chain writes the response, so it can still be sent. The attribute lets the controller read the same trace ID without having to re-parse the header.

`doFinally` runs for complete/error/cancel of the publisher at that position. The measured time includes the time the chain takes to process up to the terminating signal that the filter can observe; this is not necessarily the time the client finishes receiving all bytes over the network on every server/transport.

### 5.2. When a filter does not call the chain

A filter can deliberately end early, for example rejecting a request that does not meet a condition. In that case the filter must set an appropriate response and return a publisher that completes:

```java
if (!allowed) {
    response.setStatusCode(HttpStatus.FORBIDDEN);
    return response.setComplete();
}
return chain.filter(exchange);
```

This is an **illustrative snippet** in a `WebFilter`; the variable `allowed` is a verified check result. If the response needs an error body, you can use a codec or write a DataBuffer publisher. Do not call the chain and also write a different response yourself in the same branch unless there is a clear design.

## 6. A runnable Spring Boot 3.3.5 example

The following complete example uses **Java 17+**, **Maven**, **Spring Boot 3.3.5**, and the `spring-boot-starter-webflux` dependency. The version is pinned for easy reproducibility; in a real project, follow the version/BOM that the project manages.

Structure:

```text
webflux-exchange-demo/
├── pom.xml
└── src/main/java/demo/
    ├── WebFluxExchangeApplication.java
    ├── RequestTraceFilter.java
    └── ExchangeController.java
```

### 6.1. pom.xml

```xml
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

    <groupId>demo</groupId>
    <artifactId>webflux-exchange-demo</artifactId>
    <version>1.0.0</version>

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
```

### 6.2. WebFluxExchangeApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxExchangeApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxExchangeApplication.class, args);
    }
}
```

### 6.3. RequestTraceFilter.java

```java
package demo;

import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class RequestTraceFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String traceId = UUID.randomUUID().toString();
        exchange.getAttributes().put("demo.traceId", traceId);

        ServerHttpRequest request = exchange.getRequest();
        ServerHttpResponse response = exchange.getResponse();
        response.getHeaders().set("X-Trace-Id", traceId);

        long started = System.nanoTime();

        return chain.filter(exchange)
                .doFinally(signal -> {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started);

                    System.out.printf(
                            "%s %s -> %s [%s] %dms%n",
                            request.getMethodValue(),
                            request.getURI().getPath(),
                            response.getStatusCode(),
                            signal,
                            elapsedMs);
                });
    }
}
```

### 6.4. ExchangeController.java

```java
package demo;

import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ExchangeController {
    @GetMapping("/inspect")
    public Map<String, Object> inspect(
            ServerHttpRequest request,
            ServerWebExchange exchange) {

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("method", request.getMethodValue());
        result.put("path", request.getPath().value());
        result.put("query", request.getQueryParams());
        result.put("traceId",
                exchange.getAttributeOrDefault("demo.traceId", "missing"));
        return result;
    }

    @PostMapping(
            value = "/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> echo(
            ServerHttpRequest request,
            @RequestBody Mono<String> body) {

        return body.map(value ->
                request.getHeaders().getContentType() + " | " + value);
    }

    @GetMapping("/direct")
    public Mono<Void> direct(ServerHttpResponse response) {
        response.setStatusCode(HttpStatus.ACCEPTED);
        response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

        byte[] bytes = "written by ServerHttpResponse\n"
                .getBytes(StandardCharsets.UTF_8);
        DataBuffer buffer = response.bufferFactory().wrap(bytes);

        return response.writeWith(Mono.just(buffer));
    }
}
```

### 6.5. Running and sending requests

In the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

On Windows PowerShell, use `curl.exe` to avoid the `curl` alias; on Linux/macOS you can use `curl`:

```powershell
curl.exe -i "http://localhost:8080/inspect?source=demo"
curl.exe -i -X POST -H "Content-Type: text/plain" --data "hello" http://localhost:8080/echo
curl.exe -i http://localhost:8080/direct
```

**Main observed results:**

1. `GET /inspect?source=demo` returns HTTP 200 and JSON containing the method `GET`, the path `/inspect`, the query `source=demo`, and the `traceId` created by the filter. The response has an `X-Trace-Id` header with the same value as the attribute the controller read.
2. `POST /echo` with the body `hello` returns the body `text/plain | hello`. The controller reads the header from `ServerHttpRequest` and lets `@RequestBody Mono<String>` together with the message reader decode the body.
3. `GET /direct` returns HTTP 202 Accepted, Content-Type `text/plain`, and the body `written by ServerHttpResponse`. The controller wrote the body itself, so the method returns `Mono<Void>`.

An example of the filter log looks like this (the time and trace ID change with each run):

```text
GET /inspect -> 200 OK [onComplete] 18ms
POST /echo -> 200 OK [onComplete] 4ms
GET /direct -> 202 ACCEPTED [onComplete] 2ms
```

This is illustrative output in the shape of the log; the millisecond numbers depend on the machine and environment. `doFinally` may print `onError` or `cancel` if the request ends in the corresponding way.

## 7. When to use request, response, or exchange?

| Need | API to use | Why |
| --- | --- | --- |
| Only need the method, path, header, or query | `ServerHttpRequest` | Reads exactly the part of the request needed. |
| Need to decode the body into a DTO | `@RequestBody Mono<T>`/`Flux<T>` | Lets the codec manage decoding and backpressure. |
| Need the raw byte stream or to proxy the body | `ServerHttpRequest.getBody()` | Low-level; you must manage DataBuffer and ownership yourself. |
| Need to set status/header/cookie or write the response manually | `ServerHttpResponse` | The direct API of the reactive response. |
| Need trace ID, session, principal, attributes, or both the request and response | `ServerWebExchange` | One unified context for the current request. |
| Need logic that cuts across many endpoints | `WebFilter` with `ServerWebExchange` | Intervenes before/after the handler while keeping the reactive chain. |
| Only returning ordinary JSON/text | Return a DTO, `Mono<T>`, or `Flux<T>` from the controller | The Spring codec encodes automatically; less code and safer. |

Just because you can use `ServerWebExchange` does not mean you should use it in every controller. If a method only needs one query parameter, `@RequestParam` is clearer. If it only needs one header, `@RequestHeader` is more readable. Use the exchange when you truly need the broader HTTP context.

## 8. Boundaries to distinguish

### 8.1. ServerHttpRequest differs from ServerRequest

In functional endpoints, Spring provides `org.springframework.web.reactive.function.server.ServerRequest`. This is a high-level abstraction for `HandlerFunction`, with its own APIs such as `headers()`, `bodyToMono`/`body`, and `exchange()`. It is not `org.springframework.http.server.reactive.ServerHttpRequest`.

Similarly, the functional endpoint's `ServerResponse` is a builder abstraction for describing a response, while `ServerHttpResponse` is the low-level HTTP server API for writing the response directly. Do not confuse the two pairs of similar names.

### 8.2. A committed response cannot have its status changed arbitrarily

If the body has started being written, the headers/status are usually already committed. When an error occurs in the middle of a streaming response, the server cannot go back and replace HTTP 200 with 500 if the headers have been sent. Decide the response contract and error strategy before streaming; if the client needs to know about an error mid-stream, the body/SSE protocol must have an appropriate way to represent errors.

### 8.3. Do not subscribe to the request body or response yourself

Do not write:

```java
request.getBody().subscribe(buffer -> process(buffer));
return chain.filter(exchange);
```

This is an **illustrative anti-pattern**: the body is consumed in a separate subscription, which can compete with the downstream decoder/handler; errors and cancellation are no longer composed into the HTTP lifecycle. Use `flatMap`/`map` on the publisher and return the result, or use a controller argument/codec.

Similarly, do not call `response.writeWith(...).subscribe()` and then return `Mono.empty()`. You must return `writeWith(...)` so that the server tracks the write and errors.

### 8.4. DataBuffer is not an ordinary byte[]

A `DataBuffer` may use pooled/native memory. Reading a buffer and then retaining or discarding it requires clear ownership. When using low-level APIs:

- Do not hold a DataBuffer after it has been released.
- Do not release it twice.
- When copying bytes out into your own structure, make sure to release the buffer using the correct API.
- Handle the cancel/error/discard paths, especially for buffers that have not reached downstream.
- Prefer Spring's codecs if you do not need to intervene in the byte stream.

### 8.5. Attributes are not a security context

A request attribute is just a data map in the current exchange. Do not turn an attribute value controlled by the client into access rights. Authentication data must be created by a trustworthy component; use `Principal` and Spring Security to check identity/authority.

### 8.6. Do not trust forwarded headers from every client

`Forwarded` and `X-Forwarded-*` can be forged if the proxy does not remove and rewrite the incoming values. The forwarded-header handling configuration must match the topology and trust boundary. Do not use these headers as a basis for granting permissions or IP-based rate limiting unless you control the proxy.

## 9. Common mistakes and how to handle them

| Mistake | Consequence | The right approach |
| --- | --- | --- |
| Confusing `ServerWebExchange` with the request body | Using the wrong abstraction | The exchange contains the request and response along with server-side metadata. |
| Confusing `ServerHttpRequest` with the functional `ServerRequest` | Calling the wrong API/package | Check the package and programming model. |
| Reading `getBody()` in a filter and then letting the handler read it again | The handler may receive an empty body or an already-consumed stream | Compose the body into the pipeline or build a request decorator with correct replay. |
| Gathering a large body into unbounded memory | Increases memory and reduces streaming capability | Use a streaming publisher, limit the size, and use an appropriate codec. |
| Modifying request headers directly | Request headers are usually a read-only view | Use `request.mutate()` or `exchange.mutate()` to create a decorator. |
| Changing status/header after the response is committed | The change is no longer sent | Set metadata before writing the body or use `beforeCommit` correctly. |
| Calling `writeWith` but not returning the publisher | The server does not track the write lifecycle correctly | Return/compose the `Mono<Void>` from writeWith. |
| Both writing the response manually and returning a DTO | May write the response twice or cause a commit conflict | Choose one way of owning the body for each handler. |
| Calling `subscribe()` in a WebFilter | Creates a branch detached from the request | Return the composed `chain.filter(exchange)`. |
| Using `block()` to get the principal/session/body | Blocks the event loop or breaks the reactive lifecycle | Compose publishers with map/flatMap. |
| Using a request attribute like a session | Data is lost after the current exchange | Use WebSession or appropriate persistence if it must span multiple requests. |
| Trusting `X-Forwarded-For` from the Internet | The client IP can be forged | Only process forwarded headers behind a trusted proxy. |
| Not releasing a pooled DataBuffer | Memory leak | Manage ownership/release according to the DataBuffer API. |
| Calling getStatusCode and assuming it is always non-null | The status may not have been set explicitly | Handle the unset state or use a default depending on context. |
| Treating cancel as always a client disconnect | Metrics/logs show the wrong cause | An upstream operator can also cancel; place hooks at the right boundary and use a correlation ID. |

## 10. Self-check questions

**Question 1.** How do `ServerHttpRequest` and `ServerHttpResponse` differ?  
**Answer:** The request represents the information and body the client sends to the server; the response represents the status, headers, cookies, and body the server sends back.

**Question 2.** What does `ServerWebExchange` add beyond the request/response?  
**Answer:** It provides context for the HTTP pass such as request attributes, session, principal, locale, form/multipart data, log prefix, and HTTP utilities like conditional requests.

**Question 3.** Why should you not call `request.getBody().subscribe(...)` in a WebFilter and then call `chain.filter(exchange)`?  
**Answer:** It is a detached subscription that can consume the body before the decoder/handler, and errors/cancellation are not managed together. Compose the body into the returned publisher.

**Question 4.** When can the HTTP status no longer be changed?  
**Answer:** After the response is committed, usually when headers/body start being written. The status and headers must be decided before the commit.

**Question 5.** What does `response.writeWith(...)` return and what must you do with it?  
**Answer:** It returns a `Mono<Void>` representing the body write completing or failing; you must return/compose this publisher.

**Question 6.** What data is suitable for `exchange.getAttributes()`?  
**Answer:** Metadata specific to the current request such as a trace ID or an internal processing result. Do not use it as a global cache or a session across multiple requests.

**Question 7.** Why might `getRemoteAddress()` not be the user's real IP?  
**Answer:** The direct connection may come from a reverse proxy/load balancer. Forwarded headers are only trustworthy when the proxy at the trust boundary rewrites them and the handling is configured correctly.

**Question 8.** Should you use `ServerHttpResponse` to write every JSON response yourself?  
**Answer:** No need. Usually return a DTO/Mono/Flux and let the Spring codecs encode. Direct writing is useful for low-level cases, byte streaming, or special response control.

**Question 9.** Is `ServerRequest` in a functional endpoint a `ServerHttpRequest`?  
**Answer:** No. They belong to different packages and abstraction levels. `ServerRequest` provides a high-level API for `HandlerFunction`; `ServerHttpRequest` is the low-level HTTP server message.

## Key takeaways

- **`ServerHttpRequest`:** reads the method, URI/path, headers, cookies, query params, and the raw body as a `Flux<DataBuffer>`.
- **`ServerHttpResponse`:** sets status/headers/cookies, tracks the commit, and writes the body via `writeWith`/`writeAndFlushWith` or completes with `setComplete`.
- **`ServerWebExchange`:** gathers the request, response, and context of one request; use attributes, session, principal, locale, form/multipart, log prefix, and the mutate builder.
- In controllers, prefer argument resolvers and codecs such as `@RequestBody Mono<T>`; use raw DataBuffer only when you truly need the low level.
- The request body is a stream with ownership/lifecycle; the response can only change status/headers before the commit. Always compose and return the publisher; do not subscribe/block yourself.
- For proxies, forwarded headers, and security metadata, only trust data after verifying the trust boundary.

### References

1. [Spring Framework – Reactive Core / WebHandler API](https://docs.spring.io/spring-framework/reference/7.1/web/webflux/reactive-spring.html): `ServerWebExchange`, `WebFilter`, session, attributes, form, and multipart.
2. [Spring Framework – Annotated Controller Method Arguments](https://docs.spring.io/spring-framework/reference/7.1/web/webflux/controller/ann-methods/arguments.html): injecting `ServerWebExchange`, `ServerHttpRequest`, and `ServerHttpResponse`.
3. [ServerWebExchange Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html): request/response, attributes, principal, session, mutate, and conditional requests.
4. [ServerHttpRequest Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html): request metadata, body, and builder.
5. [ServerHttpResponse Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html): response status, headers, cookies, and writing the body.
6. [ReactiveHttpOutputMessage Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ReactiveHttpOutputMessage.html): `beforeCommit`, `writeWith`, `writeAndFlushWith`, and `setComplete`.
7. [Spring Framework – WebFlux Testing](https://docs.spring.io/spring-framework/reference/7.1/testing/webtestclient.html): testing reactive HTTP with `WebTestClient`.
