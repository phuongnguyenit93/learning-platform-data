# Choosing RestClient, RestTemplate, WebClient, or HTTP Service Client in Spring Framework

> **Context:** Synchronous HTTP clients, while also needing to understand reactive and interface-declarative options to choose the right architecture. This guide uses **Spring Framework 6.2.x, Spring Boot 3.5.x, and Java 17+** for runnable code. Spring Framework 7.x marked `RestTemplate` as deprecated to steer users toward `RestClient`; this does not mean `RestTemplate` stops working immediately, and Spring 7 APIs should **not** be applied verbatim to a Spring 6.2 project. All HTTP timeout, pool, auth, error handling, and tracing configurations must still be verified against the actual framework and transport library versions in use.

## 1. 30-Second Selection Summary

| Practical Need | Typically Suitable Choice | Reason |
| --- | --- | --- |
| New synchronous Java/Spring MVC code, typical JSON API calls | **`RestClient`** | Fluent synchronous API, concise, readable, uses `HttpMessageConverter` |
| Codebase already uses `RestTemplate` extensively and stably | Keep `RestTemplate` temporarily, plan migration to `RestClient` | No need to rewrite the whole system just because a newer API exists |
| Non-blocking HTTP calls, coordinating multiple remote calls, streams, WebFlux/Reactor | **`WebClient`** | Returns `Mono`/`Flux`, supports reactive composition, backpressure/streaming |
| Multiple endpoints of one remote service, wanting a readable/mockable interface | **HTTP Service Client** on `RestClient` or `WebClient` | Proxy generated from `@HttpExchange`/`@GetExchange` interface, **not a fourth transport** |
| Wanting a declarative interface while keeping synchronous call sites | HTTP Service Client + `RestClientAdapter` | Methods return DTO/`ResponseEntity<T>` synchronously |
| Wanting a declarative interface with methods returning `Mono<T>`/`Flux<T>` | HTTP Service Client + `WebClientAdapter` | Reactive signatures supported by the transport adapter |
| A scheduled task or MVC controller handling blocking I/O per request | `RestClient` or an interface proxy over it | No need to add Reactor just to GET a single DTO |
| SSE, NDJSON, or large/infinite response streams | `WebClient` or an interface proxy over it | Reactive streaming, avoids buffering everything into memory |

**Decision order:** (1) whether the calling model is **blocking or non-blocking**, (2) direct API or HTTP interface, (3) transport/pooling/timeouts/observability choices, (4) error contract and retry. Do not pick a client just because its name is newer or because “WebClient is always faster”.

## 2. Four Concepts at Different Layers

`RestClient`, `RestTemplate`, and `WebClient` directly build/send HTTP requests; **HTTP Service Client** defines a Java interface for which Spring creates a proxy to **delegate** requests to one of those underlying clients.

```text
                    Spring HTTP client usage
                              |
                  +-----------+------------+
                  |                        |
             Fluent/direct             Interface-first
                  |                        |
      +-----------+-----------+       @HttpExchange
      |           |           |       @GetExchange
   RestClient  RestTemplate  WebClient        |
      |           |           |       HttpServiceProxyFactory
      +-----------+-----------+             |
                  |                  Selected HTTP adapter
        Actual client request factory/connector
                  |
      TCP/TLS connection, HTTP exchange, codecs
                  |
             Remote HTTP API
```

- `RestClient`: synchronous fluent API, introduced in Spring Framework 6.1. When calling terminal `retrieve().body(...)` or `toEntity(...)`, the caller waits for the result.
- `RestTemplate`: long-standing synchronous template-method API, with methods such as `getForObject`, `postForEntity`, `exchange`. Still works on Spring 6.2; Spring 7 deprecates it to recommend `RestClient`.
- `WebClient`: reactive HTTP API, using Reactor's `Mono`/`Flux` and a non-blocking HTTP connector (typically Reactor Netty). The caller can compose async sources instead of holding a thread waiting on the network.
- HTTP Service Client: an interface with `@HttpExchange`, `@GetExchange`, `@PostExchange`, etc. implemented by `HttpServiceProxyFactory` through an adapter. With `RestClientAdapter`, methods can return DTOs synchronously; with `WebClientAdapter`, they can return `Mono<T>`/`Flux<T>`.

**Key point:** an interface proxy does not replace business logic, nor does it automatically add circuit breakers, retries, transactions, or async execution. Those properties come from the underlying client/config or an explicitly implemented application layer.

## 3. Detailed Comparison

| Property | RestClient | RestTemplate | WebClient | HTTP Service Client |
| --- | --- | --- | --- | --- |
| API style | Fluent | Template operations | Fluent reactive | Annotated interface + proxy |
| Nature | Synchronous/blocking caller | Synchronous/blocking caller | Non-blocking HTTP I/O when configured appropriately | **Depends on adapter** |
| Common return types | DTO, `ResponseEntity<T>` | DTO, `ResponseEntity<T>` | `Mono<T>`, `Flux<T>` | DTO or Mono/Flux depending on adapter/signature |
| JSON conversion | `HttpMessageConverter` | `HttpMessageConverter` | Reactive `HttpMessageReader/Writer` | Per underlying client |
| Default HTTP status errors | 4xx/5xx throws `RestClientException`/subtype with `retrieve()` | Default `ResponseErrorHandler` throws 4xx/5xx exceptions | `retrieve()` emits `WebClientResponseException` error signal on subscribe | Per underlying client and status policy |
| Custom error handling | `onStatus`, builder status handler, `exchange` | `ResponseErrorHandler`, `exchange` | `onStatus`, `exchangeToMono/Flux` | Configure underlying client |
| Streaming/backpressure | Not natively reactive | Not natively reactive | Native publisher/streaming | Native when using reactive adapter |
| Integration with Spring MVC blocking code | Very suitable | Suitable when legacy exists | Usable, but sync/async contract must be clear | Good with sync adapter |
| Integration with WebFlux event loop | **Should not call directly** because blocking | **Should not call directly** | Suitable | Choose WebClientAdapter |
| Connection pooling | Depends on `ClientHttpRequestFactory` | Depends on `ClientHttpRequestFactory` | Depends on `ClientHttpConnector`/Netty pool | Per underlying client |
| Suitability for new Spring 6.2 code | Preferred for synchronous | Mainly maintenance | Reactive/concurrent streaming | Interface-first when reducing boilerplate helps |

### 3.1. REST API and Transport Are Two Separate Layers

The same `RestClient` can run over different HTTP libraries/request factories. Likewise, `WebClient` can use the Reactor Netty connector or another suitable connector. The “RestClient vs WebClient” choice primarily describes the **programming model**; throughput/latency also depend on transport implementation, DNS, TLS, pool size, server availability, payload, and traffic volume.

### 3.2. Do Not Confuse a Reactive Client with a Reactive Server

A Spring MVC/Servlet application **can use `WebClient`** to call downstream services, and can even return `Mono<T>` from an MVC controller via Servlet async support. This **does not turn `DispatcherServlet` into `DispatcherHandler`**. Conversely, a WebFlux server can still call a blocking library, but should not call it directly on the non-blocking event loop.

### 3.3. Versions to Remember

- `RestTemplate`: available since Spring 3.0, long-established.
- `WebClient`: available since Spring 5.0 (WebFlux).
- `@HttpExchange`/HTTP Interface: since Spring 6.0.
- `RestClient`: since Spring 6.1.
- With Spring 6.2, `HttpServiceProxyFactory.builderFor(adapter)` is the right API; avoid very old snippets using `builder(HttpClientAdapter)` which was deprecated/removed.
- From Spring 7, `RestTemplate` is marked deprecated to guide users toward `RestClient`; do not assume “every Spring 6.2 project immediately emits a deprecation compiler warning”.

## 4. RestClient: Good Default for New Synchronous HTTP

### 4.1. A Simple GET

```java
RestClient client = RestClient.builder()
        .baseUrl("https://catalog.example.test")
        .build();

Item item = client.get()
        .uri("/items/{id}", 7)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(Item.class);
```

**This is a snippet**: it requires an `Item` record/class, imports, and a real endpoint. `.retrieve()` returns a `ResponseSpec`; it is **not yet a terminal operation**. Calling `.body(Item.class)` executes the exchange and decodes the result. Because it is a synchronous API, the calling thread must wait for the network/exchange/response decoding to complete.

### 4.2. Wanting Status and Headers

```java
ResponseEntity<Item> response = client.get()
        .uri("/items/{id}", 7)
        .retrieve()
        .toEntity(Item.class);

HttpStatusCode status = response.getStatusCode();
HttpHeaders headers = response.getHeaders();
Item body = response.getBody();
```

If the server returns a successful 204 with no body, `body` can be null; a DTO return type does not mean a non-null value is always returned at runtime. If the status is 4xx/5xx, `retrieve()` usually throws an exception before you receive `ResponseEntity`, unless a custom handler is configured.

### 4.3. POST JSON

```java
record CreateItem(String name) {}

Item created = client.post()
        .uri("/items")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(new CreateItem("Java"))
        .retrieve()
        .body(Item.class);
```

This snippet illustrates the request body converter; a real API might return 201 + Location, so `toEntity(Item.class)` is suitable if you need to read the Location or ETag header.

### 4.4. Generic Lists

```java
List<Item> items = client.get()
        .uri("/items")
        .retrieve()
        .body(new ParameterizedTypeReference<List<Item>>() {});
```

Use `ParameterizedTypeReference` when the response is a generic list/map; `List.class` does not preserve the element type at runtime and easily causes JSON items to become `Map` instead of `Item`.

### 4.5. Explicit Status Checking

```java
Item item = client.get()
        .uri("/items/{id}", id)
        .retrieve()
        .onStatus(HttpStatusCode::is4xxClientError,
                (request, response) -> {
                    throw new IllegalStateException(
                            "Catalog returned " + response.getStatusCode());
                })
        .body(Item.class);
```

This snippet demonstrates syntax; it **does not recommend turning every 4xx into IllegalStateException** in production. Classify 404/resource missing, 401/403/auth, and 429/rate-limit properly; log safely. `RestClient` already throws by default for 4xx/5xx; custom `onStatus` is only needed when the contract differs.

### 4.6. retrieve vs exchange

`RestClient.retrieve()` performs high-level status handling/conversion. `RestClient.exchange((request,response) -> ...)` grants lower-level direct access to the response.

**Pitfall:** in RestClient, `exchange` bypasses status handlers attached for `retrieve`. Therefore, if you use `exchange` to access the raw response, you **must** handle status decisions, check 4xx/5xx, and close the body/resource properly. Do not choose exchange just because it looks “more flexible” when the task only needs a DTO.

## 5. RestTemplate: When to Keep and When to Migrate?

### 5.1. Usage in Existing Codebases

```java
RestTemplate template = new RestTemplate();

Item item = template.getForObject(
        "https://catalog.example.test/items/{id}",
        Item.class,
        7);
```

This API is still supported in Spring 6.2 and convenient for older systems. `RestTemplate` uses `HttpMessageConverter`, `ClientHttpRequestFactory`, and request interceptors, similar to the underlying infrastructure shared with `RestClient`. A RestTemplate bean can be used across multiple threads once configured, but you should **not** mutate its configuration concurrently while serving requests.

### 5.2. exchange and Generic Results

```java
ResponseEntity<List<Item>> result = template.exchange(
        "https://catalog.example.test/items",
        HttpMethod.GET,
        HttpEntity.EMPTY,
        new ParameterizedTypeReference<List<Item>>() {});
```

This snippet illustrates the signature (not a full program). When an authorization header is needed, create an `HttpEntity<?>` with appropriate HttpHeaders, or configure an interceptor that supplies a trusted token. Do not put raw tokens into query strings or stdout.

### 5.3. Distinguishing “Legacy” from “Needs Immediate Rewrite”

- There is no reason to halt a well-running service just because `RestTemplate` has an older API; replacing a client must be tested for exceptions, URI encoding, status handling, timeouts, pooling, and request interceptors.
- For **new** synchronous code, `RestClient` is generally clearer and recommended by Spring.
- Spring Framework 7 deprecates `RestTemplate`; therefore, avoid adding large amounts of new RestTemplate code where possible.
- Do not switch to WebClient just to “get away from RestTemplate” when call sites are synchronous and you plan to call `.block()` everywhere; the natural choice is RestClient.

### 5.4. Migrating RestTemplate to RestClient

| RestTemplate | RestClient Equivalent |
| --- | --- |
| `getForObject(url,Item.class,id)` | `get().uri(url,id).retrieve().body(Item.class)` |
| `getForEntity(url,Item.class,id)` | `get().uri(url,id).retrieve().toEntity(Item.class)` |
| `postForObject(url,request,Item.class)` | `post().uri(url).body(request).retrieve().body(Item.class)` |
| `delete(url,id)` | `delete().uri(url,id).retrieve().toBodilessEntity()` |
| `exchange(...,ParameterizedTypeReference)` | `method(...).uri(...).body(...).retrieve().toEntity(new ParameterizedTypeReference<...>() {})` |
| `setErrorHandler(...)` | `onStatus(...)` or builder defaultStatusHandler |
| `ClientHttpRequestFactory` | Choose appropriate requestFactory on RestClient.Builder |

This table is a **migration guide**, not a mechanical overload-by-overload replacement. Verify status handling, encoding, and especially the REST methods invoked after conversion. If the application uses interceptors, SSL client certificates, OAuth2, proxies, or compression, migrate the corresponding configuration as well.

## 6. WebClient: When Reactive, Async Fan-Out, or Streaming Is Needed

### 6.1. Non-Blocking GET

```java
WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example.test")
        .build();

Mono<Item> pending = client.get()
        .uri("/items/{id}", 7)
        .retrieve()
        .bodyToMono(Item.class);
```

Unlike RestClient:
- `pending` describes a **reactive HTTP operation**, typically cold/lazy.
- No actual request is sent just by creating the Mono variable; it starts upon **subscribe**.
- In a WebFlux controller, return Mono/Flux for the framework to subscribe to.
- In a Spring MVC controller, you can return Mono for the MVC async adapter to handle, while the server remains MVC.
- Do not call `pending.subscribe()` and then return `null`, because detached work is no longer tied to response/error/cancellation.

### 6.2. Multiple Independent Requests

```java
Mono<Item> item = client.get()
        .uri("/items/{id}", 7)
        .retrieve()
        .bodyToMono(Item.class);

Mono<Stock> stock = client.get()
        .uri("/stock/{id}", 7)
        .retrieve()
        .bodyToMono(Stock.class);

Mono<ItemPage> page = Mono.zip(
        item, stock,
        (i, s) -> new ItemPage(i, s));
```

Snippets require `Stock`/`ItemPage` DTOs. With two independent upstream calls, `Mono.zip` can overlap I/O so total latency is typically close to the max latency plus overhead rather than the sum of two sequential latencies. However, if one Mono completes empty, zip can complete empty. For 404, explicitly model `switchIfEmpty` or error mapping.

### 6.3. Bounded List Fan-Out

```java
Flux<Item> items = Flux.fromIterable(ids)
        .flatMap(id -> client.get()
                .uri("/items/{id}", id)
                .retrieve()
                .bodyToMono(Item.class),
                5);
```

`flatMap(...,5)` limits inner publishers per **single pipeline/subscription**, not a maximum of five connections across the entire application. 100 inbound requests each with concurrency=5 can create up to roughly 500 active operations. You need connection pool limits, global rate-limit/bulkhead, timeouts, and backpressure.

If output order matching the IDs must be preserved, consider `flatMapSequential`; if side effects must execute sequentially, `concatMap`. Increasing concurrency does not always increase throughput when downstream is already saturated.

### 6.4. Reactive HTTP Errors

```java
Mono<Item> item = client.get()
        .uri("/items/{id}", id)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                response -> Mono.error(
                        new ItemNotFoundException(id)))
        .bodyToMono(Item.class);
```

The snippet requires `ItemNotFoundException`. With `retrieve()`, 4xx/5xx by default become a `WebClientResponseException` error signal. `exchangeToMono`/`exchangeToFlux` allow controlling response status/body per outcome, but you must consume/release the body according to contract before exiting the callback. Do not buffer entire large error bodies or log PII/raw upstream errors as client-facing details.

### 6.5. Can You Use WebClient and Then Block in MVC?

The Spring reference documents using `WebClient...bodyToMono(...).block()` in a synchronous environment, however:
- Doing so **still blocks the calling thread**; it does not automatically provide end-to-end non-blocking behavior.
- Avoid doing this on the WebFlux event loop, where blocking terminal operations may be disallowed or cause stalls.
- If the rest of the application is synchronous, `RestClient` is usually simpler.
- If you need to wait on **multiple** requests without changing the call site, you can compose them first with `Mono.zip` and then block **once at a boundary where blocking is actually permitted**; do not block each request sequentially.

### 6.6. Streaming Responses

```java
Flux<EventDto> events = client.get()
        .uri("/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(EventDto.class);
```

This is a snippet, requiring a server and codec supporting event streams and an EventDto class. With SSE/NDJSON, avoid `collectList()` on infinite streams: it never completes and can retain unbounded data. You need cancellation, reconnect policy, backpressure, authentication expiry, memory limits, and protocol-specific event ID/duplicate semantics handling.

## 7. HTTP Service Client: Interface + Proxy, Not a Fourth HTTP Library

### 7.1. Interface with @HttpExchange

```java
@HttpExchange("/items")
interface ItemApi {

    @GetExchange("/{id}")
    Item find(@PathVariable("id") long id);

    @GetExchange
    List<Item> list();
}
```

This is a sync interface used with `RestClientAdapter` or `RestTemplateAdapter`. `@HttpExchange` describes the common base path, `@GetExchange` describes the GET endpoint; similarly there are `@PostExchange`, `@PutExchange`, `@PatchExchange`, `@DeleteExchange`. A dynamically generated proxy implements the interface, so there is **no** need to write an HTTP-sending implementation manually.

**Note:** a Spring HTTP Service Client interface is a **client contract** executed by a proxy, very different from how a server dispatches an annotated controller. The interface does not hold transport, connection pool, or authentication policies; those are configured on the underlying client.

### 7.2. Synchronous Proxy on RestClient

```java
RestClient restClient = RestClient.builder()
        .baseUrl("https://catalog.example.test")
        .build();

RestClientAdapter adapter = RestClientAdapter.create(restClient);

HttpServiceProxyFactory proxyFactory =
        HttpServiceProxyFactory.builderFor(adapter).build();

ItemApi itemApi = proxyFactory.createClient(ItemApi.class);

Item item = itemApi.find(7);  // Synchronous call.
```

This is a snippet; it requires the right imports:
- `org.springframework.web.client.RestClient`;
- `org.springframework.web.client.support.RestClientAdapter`;
- `org.springframework.web.service.invoker.HttpServiceProxyFactory`;
- `org.springframework.web.service.annotation.HttpExchange` and `GetExchange`;
- `org.springframework.web.bind.annotation.PathVariable`.

Method `find` returns Item because the adapter is synchronous. If the remote service is slow, the thread calling the proxy still waits just as when calling RestClient directly.

### 7.3. Reactive Proxy on WebClient

```java
@HttpExchange("/items")
interface ReactiveItemApi {
    @GetExchange("/{id}")
    Mono<Item> find(@PathVariable("id") long id);

    @GetExchange
    Flux<Item> stream();
}

WebClient webClient = WebClient.builder()
        .baseUrl("https://catalog.example.test")
        .build();

ReactiveItemApi reactiveApi = HttpServiceProxyFactory
        .builderFor(WebClientAdapter.create(webClient))
        .build()
        .createClient(ReactiveItemApi.class);

Mono<Item> future = reactiveApi.find(7);
```

The above is a snippet requiring imports; `Flux<Item>` is only appropriate when the remote response/codec supports multiple values, not to automatically turn a single JSON object into a stream. Use `org.springframework.web.reactive.function.client.support.WebClientAdapter`. With reactive signatures, do not use the sync `RestClientAdapter` and expect the proxy to return non-blocking Mono/Flux.

### 7.4. Proxy on RestTemplate

In Spring 6.2, `RestTemplateAdapter` is also available:

```java
RestTemplate template = new RestTemplate();

RestTemplateAdapter adapter =
        RestTemplateAdapter.create(template);

ItemApi api = HttpServiceProxyFactory
        .builderFor(adapter)
        .build()
        .createClient(ItemApi.class);
```

This is a snippet; to use relative paths in the interface, configure `DefaultUriBuilderFactory(baseUrl)` on RestTemplate beforehand. Without a base URL, a relative `/items/{id}` is insufficient to open a connection. This is a convenient bridge for older projects, not a reason to start new code on RestTemplate.

### 7.5. Annotated Method Parameters

An HTTP interface can accept:
- `@PathVariable`: inserts URI template variables and encodes properly;
- `@RequestParam`: query/form params depending on method/content type;
- `@RequestHeader`: request headers;
- `@RequestBody`: request object;
- `URI` or `UriBuilderFactory` for dynamic targets as supported by the framework API.

Example:

```java
@HttpExchange("/orders")
interface OrderApi {

    @GetExchange("/{id}")
    OrderView find(@PathVariable("id") long id,
                   @RequestHeader("X-Correlation-Id") String traceId);

    @PostExchange(contentType = "application/json")
    OrderView create(@RequestBody CreateOrder command);
}
```

This is an interface snippet; `OrderView` and `CreateOrder` must be declared. A trace ID header does not replace Authorization. A POST resource creation event may need `ResponseEntity<OrderView>` to read Location/ETag if the API contract requires it.

### 7.6. Return Types by Adapter

| HTTP Interface Return Type | RestClientAdapter / RestTemplateAdapter | WebClientAdapter |
| --- | --- | --- |
| `T` | Yes, synchronous | Can block via adapter; consider avoiding in reactive code |
| `ResponseEntity<T>` | Yes, synchronous | Can have synchronous form, but still blocks |
| `void` | Yes | Yes |
| `Mono<T>` | **Do not use with sync adapter** | Yes |
| `Flux<T>` | **Do not use with sync adapter** | Yes |
| `Mono<ResponseEntity<T>>` | No | Yes |
| `Flux<ServerSentEvent<T>>` | Not natively reactive | Yes if media type/codec supports it |

When an API interface returns a DTO synchronously while using WebClientAdapter, the proxy has to wait to provide a synchronous value; that does not make the method non-blocking. For true reactivity, declare a reactive return type and compose publishers.

### 7.7. Pros and Cons of Interface-First

**Pros:** clean service code, a single place describing the contract of multiple endpoints, easy to swap implementations via mock/stub interfaces, reusable API shape, less boilerplate repetition. **Cons:** highly dynamic requests, complex streaming logic, per-status branching, or per-call request signing/customization may be easier to read with direct RestClient/WebClient. API interface stability requires versioning and testing when upstream changes.

**Do not confuse with OpenFeign:** Spring HTTP Service Client is a framework-native feature and does not automatically provide features of other declarative client ecosystems (service discovery, load balancing, circuit breaker, retry) unless you configure them.

## 8. Java 17 + Spring Boot 3.5: Runnable Example of All Four Options

Goal: a project with a **mock HTTP supplier endpoint** running in-process, and four call paths:
- `/compare/rest-client/7` — calls synchronously using RestClient;
- `/compare/rest-template/7` — calls synchronously using RestTemplate;
- `/compare/http-interface/7` — calls using HTTP Service Client over RestClient;
- `/compare/web-client/7` — returns `Mono<Item>` from WebClient.

This application uses a **Spring MVC server** to show that WebClient can still be used in an MVC project. Because the demo supplier and caller run in the same process on localhost:8080, no real remote service is needed; **this is not a production microservice architecture**. Caution: synchronous requests calling back into the same server can contribute to exhausting the servlet thread pool under high load; use this self-call pattern only for learning.

### 8.1. Dependencies and Structure

Create a Maven Spring Boot **3.5.x**, Java 17+ project with dependencies:
- **Spring Web**: MVC server, RestClient, RestTemplate;
- **Spring Reactive Web**: WebClient, Reactor.

In the POM generated by Spring Initializr, there is a fragment:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
</dependencies>
```

This is **only a dependency fragment**, not a complete POM; Initializr's parent/BOM/plugins manage versions. When **both starters** are present on Boot 3.5, the default web application type is **Servlet MVC**, not a WebFlux server. `WebClient.Builder` is still auto-configured for making reactive downstream HTTP calls.

Structure:

```text
src/main/java/com/example/demo/DemoApplication.java
src/test/java/com/example/demo/RestClientExampleTest.java
```

### 8.2. Complete Source (Single File)

Save the entire code into `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    // All clients call the local supplier for demonstration only.
    @Bean
    RestClient restClient(RestClient.Builder builder) {
        return builder.baseUrl("http://localhost:8080").build();
    }

    @Bean
    RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder.rootUri("http://localhost:8080").build();
    }

    @Bean
    WebClient webClient(WebClient.Builder builder) {
        return builder.baseUrl("http://localhost:8080").build();
    }

    @Bean
    SupplierApi supplierApi(RestClient restClient) {
        return HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(restClient))
                .build()
                .createClient(SupplierApi.class);
    }
}

record Item(long id, String name, int stock) {}

record ErrorView(String code, int upstreamStatus) {}

// Client-side declarative HTTP service interface.
@HttpExchange("/supplier/items")
interface SupplierApi {
    @GetExchange("/{id}")
    Item find(@PathVariable("id") long id);
}

// Server-side stub (for demo only; not a real upstream).
@RestController
@RequestMapping("/supplier/items")
class SupplierController {

    @GetMapping("/{id}")
    ResponseEntity<Item> find(@PathVariable("id") long id) {
        if (id != 7L) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(
                new Item(7L, "Spring Web", 12));
    }

    @GetMapping
    List<Item> list() {
        return List.of(new Item(7L, "Spring Web", 12));
    }
}

// Four client styles calling the same supplier endpoint.
@RestController
@RequestMapping("/compare")
class ComparisonController {

    private final RestClient restClient;
    private final RestTemplate restTemplate;
    private final WebClient webClient;
    private final SupplierApi supplierApi;

    ComparisonController(
            RestClient restClient,
            RestTemplate restTemplate,
            WebClient webClient,
            SupplierApi supplierApi) {
        this.restClient = restClient;
        this.restTemplate = restTemplate;
        this.webClient = webClient;
        this.supplierApi = supplierApi;
    }

    @GetMapping("/rest-client/{id}")
    Item viaRestClient(@PathVariable("id") long id) {
        return restClient.get()
                .uri("/supplier/items/{id}", id)
                .retrieve()
                .body(Item.class);
    }

    @GetMapping("/rest-template/{id}")
    Item viaRestTemplate(@PathVariable("id") long id) {
        return restTemplate.getForObject(
                "/supplier/items/{id}", Item.class, id);
    }

    @GetMapping("/http-interface/{id}")
    Item viaHttpInterface(@PathVariable("id") long id) {
        return supplierApi.find(id);
    }

    @GetMapping("/web-client/{id}")
    Mono<Item> viaWebClient(@PathVariable("id") long id) {
        return webClient.get()
                .uri("/supplier/items/{id}", id)
                .retrieve()
                .bodyToMono(Item.class);
    }
}

// Keep error messages safe instead of exposing the raw upstream body.
@RestControllerAdvice
class DemoClientErrors {

    @ExceptionHandler(RestClientResponseException.class)
    ResponseEntity<ErrorView> syncError(
            RestClientResponseException exception) {
        return ResponseEntity.status(exception.getStatusCode())
                .body(new ErrorView(
                        "UPSTREAM_HTTP_ERROR",
                        exception.getStatusCode().value()));
    }

    @ExceptionHandler(WebClientResponseException.class)
    ResponseEntity<ErrorView> reactiveError(
            WebClientResponseException exception) {
        return ResponseEntity.status(exception.getStatusCode())
                .body(new ErrorView(
                        "UPSTREAM_HTTP_ERROR",
                        exception.getStatusCode().value()));
    }
}
```

### 8.3. Why Is This Code Valid on Boot 3.5?

- Java 17 allows `record`; a file has one public top-level class `DemoApplication`, and the remaining classes/interfaces/records are package-private.
- `@SpringBootApplication` component-scanning finds `SupplierController`, `ComparisonController`, `DemoClientErrors` in the same package; beans in the main class are discovered.
- `RestClient.Builder`, `RestTemplateBuilder`, `WebClient.Builder` are provided by Boot when the relevant starters are present; beans are built once and reused, rather than creating an HTTP client per request.
- `SupplierApi` is an HTTP Service Client proxy backed by `RestClientAdapter`; it is synchronous matching the `Item find(long)` signature.
- `viaWebClient` returns Mono, so the MVC controller uses async support; **the server is still Servlet MVC**. No `.block()` is needed to obtain the Item in the controller.
- `DemoClientErrors` illustrates mapping errors from both client families to a status and a sanitized error body. In production APIs, you need distinct policies for rate limits, 502/503 upstream failures, permissions, and return-timeouts; do not simply forward every upstream status.
- The local supplier and caller both use port 8080; if you change `server.port`, you must also update `baseUrl`/`rootUri` in the three corresponding beans. These are hardcoded local demo URLs, not deployment configuration.
- Network timeouts, circuit breakers, retries, auth, observability, or connection limits are omitted because the example focuses on **API selection**. They must be added before production.

### 8.4. Running

In the directory containing the Maven wrapper generated by Spring Initializr:

```bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell / CMD
mvnw.cmd spring-boot:run
```

Keep port 8080 as in the code and ensure no other service is using that port.

### 8.5. Comparing HTTP Results

Call all four options:

```bash
curl -i 'http://localhost:8080/compare/rest-client/7'
curl -i 'http://localhost:8080/compare/rest-template/7'
curl -i 'http://localhost:8080/compare/http-interface/7'
curl -i 'http://localhost:8080/compare/web-client/7'
```

Each successful request returns status 200 and a JSON object with value:

```json
{"id":7,"name":"Spring Web","stock":12}
```

The difference lies in **call mechanics**, not different data or HTTP business contract:
- RestClient: blocks the thread executing the MVC handler while waiting for the local supplier.
- RestTemplate: also blocking, with a template-method API.
- HTTP interface: method invocation looks like a Java interface, backed underneath by synchronous RestClient.
- WebClient: the method returns Mono without blocking in controller code; Spring MVC uses Servlet async support while awaiting Mono completion. Client-side HTTP I/O is reactive.

### 8.6. Not Found Case

```bash
curl -i 'http://localhost:8080/compare/rest-client/99'
curl -i 'http://localhost:8080/compare/rest-template/99'
curl -i 'http://localhost:8080/compare/http-interface/99'
curl -i 'http://localhost:8080/compare/web-client/99'
```

The supplier returns 404. Clients by default turn 4xx into exceptions/reactive errors; the advice demonstrates mapping to a 404 JSON response:

```json
{"code":"UPSTREAM_HTTP_ERROR","upstreamStatus":404}
```

This is a **deliberate demo policy**, not something to copy blindly as “forward raw upstream 404/500 to the browser” in production. Sometimes a frontend resource is genuinely missing so 404 makes sense; other times a third-party upstream 404 indicates an integration misconfiguration and should be handled internally as 502. An API gateway needs a domain-designed policy.

### 8.7. PowerShell

```powershell
curl.exe -i "http://localhost:8080/compare/rest-client/7"
curl.exe -i "http://localhost:8080/compare/rest-template/7"
curl.exe -i "http://localhost:8080/compare/http-interface/7"
curl.exe -i "http://localhost:8080/compare/web-client/7"
```

Run `curl.exe` to avoid the `curl` alias in some PowerShell versions. If JSON is pretty-printed, do not compare whitespace or object field order as business data.

## 9. Testing RestClient and HTTP Interface Without a Remote Server

Spring Test provides `MockRestServiceServer` supporting binding to `RestClient.Builder` and intercepting mock HTTP requests. Suitable for verifying URL, HTTP method, JSON conversion, and default exception mapping without depending on an external service.

Add the test dependency with Spring Boot 3.5:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

### 9.1. Complete Test File

Create `src/test/java/com/example/demo/RestClientExampleTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class RestClientExampleTest {

    @Test
    void restClientDecodesJson() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.example.test");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder.build();

        server.expect(requestTo(
                        "https://catalog.example.test/supplier/items/7"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"id\":7,\"name\":\"Spring Web\",\"stock\":12}",
                        MediaType.APPLICATION_JSON));

        Item item = client.get()
                .uri("/supplier/items/{id}", 7)
                .retrieve()
                .body(Item.class);

        assertNotNull(item);
        assertEquals(7L, item.id());
        assertEquals("Spring Web", item.name());
        assertEquals(12, item.stock());
        server.verify();
    }

    @Test
    void annotatedProxyUsesUnderlyingRestClient() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.example.test");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder.build();
        SupplierApi api = HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(client))
                .build()
                .createClient(SupplierApi.class);

        server.expect(requestTo(
                        "https://catalog.example.test/supplier/items/7"))
                .andRespond(withSuccess(
                        "{\"id\":7,\"name\":\"Spring Web\",\"stock\":12}",
                        MediaType.APPLICATION_JSON));

        Item item = api.find(7L);
        assertEquals(7L, item.id());
        server.verify();
    }

    @Test
    void status404IsRaisedByRetrieve() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.example.test");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder.build();

        server.expect(requestTo(
                        "https://catalog.example.test/supplier/items/99"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        RestClientResponseException exception = assertThrows(
                RestClientResponseException.class,
                () -> client.get()
                        .uri("/supplier/items/{id}", 99)
                        .retrieve()
                        .body(Item.class));

        assertEquals(404, exception.getStatusCode().value());
        server.verify();
    }
}
```

These tests use the package-private `Item` and `SupplierApi` from the main file in the same package. To run, Spring Initializr needs Maven/Java 17 and `spring-boot-starter-test`. The test binds `RestClient.Builder` to the mock server before calling `build()`; no real socket is opened.

### 9.2. Mocking RestTemplate

For RestTemplate, Spring Test supports:

```java
RestTemplate template = new RestTemplate();
MockRestServiceServer server = MockRestServiceServer.createServer(template);

server.expect(requestTo("https://catalog.example.test/items/7"))
        .andRespond(withSuccess(
                "{\"id\":7,\"name\":\"Spring Web\",\"stock\":12}",
                MediaType.APPLICATION_JSON));

Item item = template.getForObject(
        "https://catalog.example.test/items/{id}",
        Item.class,
        7);

server.verify();
```

This is a fragment inside a test method, requiring imports. Do not use WebClient just to mock a RestTemplate call.

### 9.3. Testing WebClient

You can use a local HTTP mock server (e.g., OkHttp MockWebServer or WireMock), or `WebTestClient` to test a WebFlux handler/server, or provide an `ExchangeFunction` test double when testing only the client. **`MockRestServiceServer` is not the tool to use directly for WebClient**, because WebClient relies on a reactive connector/ExchangeFunction. When testing WebClient, verify:
- request URI/method/headers and JSON body;
- 2xx decoding into Mono/Flux;
- 404/429/500 becoming error signals according to policy;
- timeouts/retries/cancellation;
- streaming/backpressure and response body release when using `exchangeToMono`;
- trace/auth/tenant header propagation (without logging tokens).

### 9.4. HTTP Service Interface Unit Tests

With interface-first, the business layer calling `SupplierApi` can mock the interface directly (Mockito) without opening HTTP. However, dedicated proxy/adapter tests still need an HTTP mock to ensure `@HttpExchange`/`@GetExchange`/`@PathVariable` annotations produce the right paths, headers, and bodies.

## 10. Timeouts and Connection Pools: More Important Than Syntax

### 10.1. Every Request Must Have Deadlines

Distinguish between:
- DNS lookup timeout;
- connect timeout (opening the TCP connection);
- TLS handshake timeout;
- pending connection acquisition/pool wait timeout;
- response/read timeout;
- write timeout;
- overall request deadline;
- retry/backoff duration within the overall SLA.

There is no single universal option like `timeout=2s` covering all these limits across every HTTP transport. `RestClient`/`RestTemplate` use `ClientHttpRequestFactory`; `WebClient` uses `ClientHttpConnector`. Timeouts/connection pools may reside on Apache HttpComponents, JDK HttpClient, Reactor Netty, or another chosen transport.

### 10.2. Timeouts on RestClient Using Request Factory

Principle example:

```java
// Snippet: configure on the HTTP request factory you actually use.
ClientHttpRequestFactory factory = configuredFactory;

RestClient client = RestClient.builder()
        .requestFactory(factory)
        .baseUrl("https://catalog.example.test")
        .build();
```

`configuredFactory` must be created/configured with connect/read/pool timeouts according to its concrete class. This is not standalone runnable code; do **not** assume simply creating `RestClient.Builder` provides production-safe timeouts. In Spring Boot, inspect request factory selection and RestClient customization/builder beans before manually creating a new HttpClient that bypasses Boot's configuration.

### 10.3. WebClient/Reactor Netty Example

```java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
        .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .baseUrl("https://catalog.example.test")
        .build();
```

This is a snippet for the Reactor Netty connector, requiring imports:
- `reactor.netty.http.client.HttpClient`;
- `io.netty.channel.ChannelOption`;
- `org.springframework.http.client.reactive.ReactorClientHttpConnector`;
- `java.time.Duration`.

`responseTimeout` is not automatically an overall end-to-end deadline and does not yet configure pending acquire timeout/pool max size. If your organization uses proxy/TLS connection reuse, add TLS/HTTP2/proxy/pool settings and test slow responses.

### 10.4. Connection Limits and Total Concurrency

Suppose 60 inbound requests each fan out 10 HTTP calls:
- This can create **600 in-flight operations** even though a single `flatMap(mapper, 10)` looks small.
- Downstream pool max connections, max pending acquire, and rate limits must be sufficient or protected by a bulkhead.
- With RestClient/RestTemplate, each caller typically occupies a thread waiting for the response; thread pool saturation can increase tail latency.
- With WebClient, fewer threads are held waiting on I/O, but it **does not eliminate** bottlenecks at remote services or the need for backpressure/limits.

### 10.5. Singleton/Shared Client Beans

Configure clients once as beans or reuse configured builders. Do not create a new RestClient/WebClient for every HTTP request; pool/TLS/config costs and resource lifecycles will be wasted. Builders are mutable during configuration; built clients are designed to be shared across the application. With RestTemplate, configure before sharing and do not mutate concurrently at runtime.

## 11. Error Handling: HTTP Status, Transport, and Parsing Must Be Separated

| Situation | RestClient/RestTemplate | WebClient |
| --- | --- | --- |
| 404/4xx from server | Default status handling throws RestClientResponseException subtype | `retrieve()` converts into WebClientResponseException error signal |
| 500/5xx from server | Exception contains status/body/headers when available | Error signal with status/headers/body when available |
| DNS/connect timeout | I/O exception wrapped in RestClientException family | `WebClientRequestException` or cause/timeout signal |
| Malformed JSON schema/decoder | Message conversion/RestClientException family | Reactive codec/decoding error |
| 204 Response | DTO body may be null | `Mono<T>` typically completes empty |
| Consumer cancel | Blocking caller has interruption/transport-specific mechanism | Publisher cancellation can propagate to connector |
| Retry | Explicit policy must be implemented in service/client resilience layer | `retryWhen` + filter/backoff in reactive pipeline |

Actual exception types can vary by `retrieve/exchange` method, custom status handlers, codecs, transport, and Spring version. Never do `catch(Exception.class) -> HTTP 200`.

### 11.1. Do Not Map All Upstream 404/500 One Way

If the client GETs an exact resource and upstream returns 404, your API might return 404. But if downstream is an **identity provider** or payment gateway, an upstream 404 might mean route misconfiguration rather than a nonexistent customer. Status mapping must carry business meaning.

### 11.2. Retries Are Not Free or Automatic

Only retry transient recoverable errors: connection reset/timeout under idempotent conditions, 502/503/504/429 if the API contract and Retry-After allow. Do **not** blindly retry payment-creating POSTs, 400 validation errors, 401/403, or operations with committed side effects without an idempotency key.

With WebClient:

```java
Mono<Item> item = client.get()
        .uri("/items/{id}", id)
        .retrieve()
        .bodyToMono(Item.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(150))
                .filter(ex -> isTransient(ex)));
```

This is a snippet; `isTransient` must be defined and `reactor.util.retry.Retry` imported. There are 2 additional retries after the first attempt when the filter matches. Set an overall deadline and backoff/jitter to avoid a retry storm.

For synchronous callers, use a resilience wrapper like Spring Retry/Resilience4j as needed (adding dependencies/config); do not write an unbounded `while(true)` retry loop.

### 11.3. Avoid Logging Leaked Secrets

Do not log:
- `Authorization: Bearer ...`, cookies/session tokens;
- query strings containing PII or signed URLs;
- entire raw HTTP error responses containing customer data;
- credentials in URIs or proxy settings.

Log the upstream service logical name, safe status class, latency, requestId/traceId, and internal error code, with appropriate retention/sampling.

## 12. Headers, URIs, Auth, and Request Signing

### 12.1. URI Variables and Encoding

Instead of concatenating URLs with user input:

```java
String unsafe = baseUrl + "/items/" + userInput;
```

Use URI templates:

```java
client.get()
        .uri("/items/{id}", itemId)
        .retrieve()
        .body(Item.class);
```

URI template expansion reduces encoding bugs and path injection; you still must validate that `itemId` conforms to the business contract. If a client allows dynamic absolute URLs from users, there is an **SSRF** risk even if the URI is encoded: allowlist hosts/protocols/ports, deny private/internal targets per policy, and control redirects/DNS rebinding.

### 12.2. Auth Propagation

RestClient:
```java
client.get()
        .uri("/items/{id}", id)
        .headers(headers -> headers.setBearerAuth(accessToken))
        .retrieve()
        .body(Item.class);
```

WebClient:
```java
client.get()
        .uri("/items/{id}", id)
        .headers(headers -> headers.setBearerAuth(accessToken))
        .retrieve()
        .bodyToMono(Item.class);
```

These are snippets: `accessToken` must be validly issued per OAuth2/service credentials flow; do not copy a user token to every downstream service. When using Spring Security OAuth2 client, consider dedicated interceptors/filters/AuthorizedClientManager. Avoid sending tokens to hosts outside the trust boundary; redirects must be handled per policy.

### 12.3. Content-Type and Accept

- Request `Content-Type` states whether the sent body is JSON, form, binary, etc.
- `Accept` states what response media type the client wants.
- RestClient/RestTemplate use `HttpMessageConverter`; WebClient uses reactive codec writers/readers.
- If the server returns an unsupported Content-Type, the client may emit a decoding error; this is not caused by an HTTP 500 status on the server.

## 13. Observability, Tracing, Cancellation, and Testing

### 13.1. Metrics

With Spring Boot Actuator/Micrometer configured, you can instrument HTTP client calls to observe:
- outgoing request count/status;
- average/p95/p99 latency;
- timeouts, connection pool waits, DNS/TLS errors;
- retry rates and downstream 429/503;
- active requests/connection counts;
- slow consumer/stream cancellations (WebClient).

Do not use raw URL paths with individual IDs, requestIds, or email addresses as high-cardinality metrics tags; prefer URI templates and logical service names.

### 13.2. Testing Considerations by Client

| Client | Valuable Tests |
| --- | --- |
| RestClient | `MockRestServiceServer.bindTo(RestClient.Builder)`, verify URI/method/body/status |
| RestTemplate | `MockRestServiceServer.createServer(template)`, verify request/response |
| WebClient | HTTP mock server/ExchangeFunction stub, Reactor `StepVerifier` for Mono/Flux |
| HTTP Service Client | Mockito mock interface for business tests + HTTP mock for proxy/annotations |
| All | Real integration tests with TLS/proxy/pool/timeouts, 4xx/5xx, large payloads |

Tests must not only assert a 200 DTO: include malformed JSON, bad statuses, 204 empty, timeouts, cancellation, header/auth security, retry/no-retry, and wrong Content-Type.

### 13.3. HTTP Clients Do Not Decide Transactions

A POST call to a remote service may commit successfully even if the local client times out before receiving the response. Retries cannot know the final status reliably if the API lacks an idempotency key/reconciliation. Neither `RestClient`, `WebClient`, nor an interface proxy **creates a distributed transaction**. When multiple downstream writes exist, consider saga/outbox/compensation and business-level idempotency.

### 13.4. Real Tests and Mocks Are Not Identical

`MockRestServiceServer` mocks the HTTP boundary, so it is fast and deterministic, but does not prove real DNS/TLS/client connection pooling works. For proxy certificates, keepalive, and slow downstream bugs, test against an embedded/local upstream server or staging. A passing MockRestServiceServer test does not prove a production client has proper timeouts.

## 14. Common Anti-Patterns

| Anti-Pattern / Symptom | Cause | Fix |
| --- | --- | --- |
| Using WebClient + `block()` for all new sync calls | Reactive overhead without benefit | RestClient |
| Using RestTemplate in WebFlux event-loop handler | Blocking I/O | WebClient or boundedElastic bridge with quota |
| Using RestClient and expecting reactive Mono/Flux | Sync client | WebClient |
| Using `Mono.just(restClient.get()...)` | Synchronous call already executes before Mono | Choose WebClient or controlled bridge |
| HTTP interface returning Mono with RestClientAdapter | Sync adapter does not support reactive signatures | WebClientAdapter |
| Thinking HTTP interface is a new protocol | Interface is just a proxy | Configure underlying client |
| `retrieve()` without a terminal operation in RestClient | Request not sent yet | Add `body/toEntity/toBodilessEntity` |
| `WebClient.retrieve()` without subscribing | Lazy publisher | Return Mono/Flux for framework to subscribe |
| Creating a new WebClient per request | Wasted pools/resources/config | Reuse configured bean |
| Mutating RestTemplate.config during concurrent requests | Not thread-safe on runtime mutation | Configure once at startup |
| Using `exchange` and forgetting status checks | Bypasses default status mapping | Handle 4xx/5xx proactively |
| `body(List.class)` turning items into Maps | Generic type erasure | ParameterizedTypeReference |
| Treating 204 body as non-null | Empty response | Explicit Optional/empty semantics |
| Returning raw upstream exception body to client | Leaks implementation/PII | Domain-safe error DTO |
| Excessive WebClient flatMap concurrency | Downstream/pool saturation | Per-request and global limits |
| Calling `collectList()` on an infinite stream | Memory/never completes | SSE/NDJSON streaming, termination |
| Retrying non-idempotent POST | Duplicated side effects | Idempotency key/reconciliation |
| Unconfigured timeouts | Threads/connections hang indefinitely | Factory/connector timeouts + deadline |
| 200 result but invalid JSON response | Mismatched codec/Content-Type | Test media types and conversion |
| Letting client supply arbitrary absolute URL | SSRF | URL allowlist/network egress controls |
| Sending bearer token to unfamiliar redirect host | Credential leak | Redirect/auth policies |
| Only mock testing without load testing | Fails to measure pool/DNS/TLS/resource pressure | Integration/load tests |
| Using Spring 7 APIs in Boot 3.5 | Version/API mismatch | Pin exact framework version when copying code |

## 15. Client Selection and Implementation Checklist

1. [ ] Does my module use synchronous thread-per-request, MVC, or WebFlux reactive event-loop?
2. [ ] For new sync code: prefer RestClient; legacy RestTemplate still works in Spring 6.2 but have a migration plan.
3. [ ] If choosing WebClient, can callers **compose Publishers** without inserting `block()` on the event loop?
4. [ ] If choosing HTTP interface, do the backend adapter and method return types match (sync vs reactive)?
5. [ ] Is the base URL from trusted configuration; are dynamic targets validated against SSRF?
6. [ ] Are URI templates/encoding, Content-Type/Accept, and generic DTOs correct?
7. [ ] Are connection/read/response/pool wait timeouts and overall deadlines bounded?
8. [ ] Are retry filters/backoff/jitter/idempotency/Retry-After aligned with business rules?
9. [ ] Are pool size, max pending acquire, per-request concurrency, and global rate limits measured?
10. [ ] Are 404/401/403/429/5xx statuses mapped per domain contract without leaking upstream bodies?
11. [ ] Is there an auth propagation/OAuth2 policy and redaction of tokens/cookies?
12. [ ] Are client beans reused without mutating shared config at runtime?
13. [ ] Has the HTTP Service Client interface avoided becoming a complex overload list harder to read than a direct client?
14. [ ] Are 204/empty responses and codecs handled?
15. [ ] For streaming, are cancellation, backpressure, and resource release implemented?
16. [ ] Do tests cover URI, method, JSON, errors, timeouts, auth, retries, and proxy integration?
17. [ ] Has the solution been benchmarked against real workloads rather than guessed from library names?

## 16. Self-Check Questions

**Question 1.** In new synchronous Spring MVC code, should you choose RestClient or WebClient for a simple JSON GET?

**Answer:** Usually RestClient because of its clear synchronous contract and fluent API. WebClient makes sense when non-blocking composition/streaming is needed.

**Question 2.** Is HTTP Service Client a fourth HTTP transport?

**Answer:** No. It is a Java interface + proxy over RestClient, RestTemplate, or WebClient via an adapter.

**Question 3.** Has `RestClient.get().retrieve()` sent the request yet?

**Answer:** Per the Spring RestClient API, `retrieve()` only returns a ResponseSpec; terminal `body/toEntity/toBodilessEntity` executes the exchange.

**Question 4.** Does WebClient returning Mono mean the request is sent immediately when the Mono is created?

**Answer:** No, Publishers are typically lazy; a subscription is required, and the framework can subscribe when a controller returns Mono.

**Question 5.** When an HTTP interface method returns `Mono<Item>`, which adapter should be chosen?

**Answer:** `WebClientAdapter`; sync adapters do not provide a reactive return contract.

**Question 6.** Does `RestTemplate` stop working on Spring Framework 6.2?

**Answer:** No. It still works; starting in Spring 7 the API is marked deprecated to guide migration toward RestClient.

**Question 7.** Is `WebClient.bodyToMono(...).block()` safe inside the WebFlux event loop?

**Answer:** No; avoid blocking terminal methods in the WebFlux event loop. Compose non-blocking Mono/Flux instead.

**Question 8.** Why are timeouts needed even when using WebClient?

**Answer:** Non-blocking still consumes connection/pool/server resources and can stay in-flight indefinitely without deadlines; high concurrency cannot fix a slow downstream.

**Question 9.** When a POST times out but upstream already committed, what is the risk of blind retries?

**Answer:** Duplicate transactions/resources can be created; idempotency keys and reconciliation are required.

**Question 10.** Does a passing MockRestServiceServer test mean production TLS/proxy/pooling is verified?

**Answer:** No. It mocks the HTTP boundary; separate integration/load tests are required.

## 17. Official Documentation

- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): choosing between RestClient, RestTemplate, WebClient, and HTTP interfaces, method signatures, status/headers.
- [Spring Framework — REST Clients (current)](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): migration updates and RestTemplate status in Spring 7.
- [Spring Framework 6.2 — RestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/client/RestClient.html): retrieve, exchange, requestFactory, default status handlers.
- [Spring Framework 6.2 — RestTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/client/RestTemplate.html): synchronous template methods and request factory.
- [Spring Framework 6.2 — WebClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/client/WebClient.html): reactive HTTP API.
- [Spring Framework 6.2 — WebClient Synchronous Use](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-synchronous.html): blocking contract at sync boundaries and composing multiple calls.
- [Spring Framework 6.2 — HttpServiceProxyFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html): `builderFor(adapter)` and `createClient`.
- [Spring Framework 6.2 — HTTP Interface Client](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-http-interface-client.html): @HttpExchange/@GetExchange, adapters, and return values.
- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): RestClient.Builder, RestTemplateBuilder, WebClient.Builder auto-configuration.
- [Spring Framework — WebClient retrieve()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): status/error handling.
- [Spring Framework — WebClient Exchange](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): exchangeToMono/Flux and response release rules.
- [Spring Boot 3.5 — Testing Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): Spring Test/client testing practices.

**Conclusion:** For the “Synchronous HTTP Clients” module, **RestClient** is the sensible default choice for new Spring code. **RestTemplate** continues to support existing code and can be migrated gradually, especially when upgrading to Spring 7. **WebClient** is suitable when non-blocking composition, fan-out, or streaming is needed while avoiding blocking the event loop. **HTTP Service Client** is not another transport: it places an annotated interface over RestClient/WebClient (or RestTemplate), so the **synchronous vs reactive choice still lives in the adapter and return types**. Regardless of which API is chosen, production quality depends on timeouts, pooling, errors, auth, retries, backpressure, observability, and integration tests.
