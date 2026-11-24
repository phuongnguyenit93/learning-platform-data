# @HttpExchange and Declaring HTTP Contracts with Interfaces

## 1. Objectives and Context

When a Java application calls another REST API, the calling code often has to repeat the URL, HTTP method, path variables, query parameters, headers, request body, and response type. Spring Framework's **HTTP Service Client** lets you express that information as **an annotated Java interface**, and Spring then creates a proxy that executes HTTP requests through a configured client. This mechanism has been available since Spring Framework 6.0; in Spring Framework 6.1+ you can use **RestClient**, while **WebClient** supports the reactive approach.

After this lesson, you will be able to:
- Define clear HTTP contracts using @HttpExchange, @GetExchange, @PostExchange, @PutExchange, @PatchExchange, and @DeleteExchange.
- Pass path variables, query parameters, headers, and JSON bodies properly; choose an appropriate return type.
- Use HttpServiceProxyFactory to create proxies backed by RestClientAdapter or WebClientAdapter.
- Understand the HTTP call flow, status/error handling, timeouts, authentication, and the limitations of interface-based contracts.
- Run a Java 17 + Spring Boot 3.3.x example calling a local HTTP server without needing an external server.

**Core idea:** the interface defines "which endpoints this application needs to call and what data it exchanges"; RestClient/WebClient is responsible for **executing the actual request**. The interface and proxy do not implement business logic on the remote server.

## 2. From Manual Calls to Interface Contracts

Direct RestClient call (integration snippet, assuming BookDto exists):

~~~java
BookDto book = restClient.get()
    .uri("/api/books/{id}", 42L)
    .header("Accept-Language", "vi")
    .retrieve()
    .body(BookDto.class);
~~~

As calls grow, repeating path strings, header names, and decoding logic easily introduces inconsistencies. An interface centralizes the contract:

~~~java
@HttpExchange(url = "/api/books", accept = MediaType.APPLICATION_JSON_VALUE)
public interface BookHttpClient {

    @GetExchange("/{id}")
    BookDto findById(@PathVariable("id") long id,
                     @RequestHeader("Accept-Language") String language);

    @GetExchange
    List<BookDto> search(@RequestParam("q") String keyword);

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    BookDto create(@RequestBody CreateBookRequest body);
}
~~~

BookDto and CreateBookRequest belong to the application. This is an **interface contract**, not yet a callable client: you must create the RestClient/WebClient, adapter, and proxy in the later sections. Compared to manual code, the caller simply calls:

~~~java
BookDto book = bookHttpClient.findById(42L, "vi");
~~~

The proxy reads the method annotations and arguments to construct the HTTP request. An interface contract provides compile-time type checking for the Java signature, but **does not guarantee that the remote endpoint actually exists or that the response always matches the DTO**. Those can only be verified through integration testing or at runtime.

### Distinguishing the Concepts

| Component | Responsibility |
| --- | --- |
| @HttpExchange / @GetExchange / @PostExchange | Declare HTTP method, URL, media types, and parameter mapping |
| Java interface | Client-facing API, input/output types, and method names |
| HttpServiceProxyFactory | Create the proxy object implementing the interface at runtime |
| RestClientAdapter | Connect the proxy to synchronous **RestClient** |
| WebClientAdapter | Connect the proxy to reactive-capable **WebClient** |
| RestClient / WebClient | Send requests, encode/decode data, handle transport, status, and filters/interceptors |
| Remote server | Execute logic, check permissions, and return responses |

Do not confuse @HttpExchange with an HTTP server launched by this interface itself. Spring MVC/WebFlux can also use an @HttpExchange interface on a @Controller implementing the contract, but that is **a different server mapping mechanism** and does not turn a client proxy into a controller.

## 3. Annotations and URL Construction Rules

### 3.1. @HttpExchange and Shortcut Annotations

@HttpExchange is used on a **type** to set shared configuration; on a **method** to declare a specific endpoint. Typical attributes:
- **url** or alias **value**: URI template or path, e.g. "/api/books/{id}".
- **method**: HTTP method (GET, POST, PUT, PATCH, DELETE, ...).
- **accept**: the Accept value that the client expects to receive.
- **contentType**: the Content-Type of the outgoing request body.

Specialized annotations make code easier to read:

| Annotation | Outgoing method | Example purpose |
| --- | --- | --- |
| @GetExchange | GET | Fetch a resource, query a list |
| @PostExchange | POST | Create a resource or execute a command |
| @PutExchange | PUT | Replace resource state |
| @PatchExchange | PATCH | Partial update per contract |
| @DeleteExchange | DELETE | Delete a resource |

The following example illustrates several signature forms; request/response types are application-defined:

~~~java
@HttpExchange(url = "/api/books", accept = MediaType.APPLICATION_JSON_VALUE)
interface BookClient {
    @GetExchange("/{id}")
    BookDto get(@PathVariable("id") long id);

    @PutExchange(url = "/{id}", contentType = MediaType.APPLICATION_JSON_VALUE)
    BookDto replace(@PathVariable("id") long id,
                    @RequestBody ReplaceBookRequest body);

    @PatchExchange(url = "/{id}", contentType = MediaType.APPLICATION_JSON_VALUE)
    BookDto patch(@PathVariable("id") long id,
                  @RequestBody PatchBookRequest body);

    @DeleteExchange("/{id}")
    void delete(@PathVariable("id") long id);
}
~~~

These paths are relative to the HTTP client's baseUrl. For instance, if RestClient has baseUrl "https://catalog.example" and the interface declares "/api/books": GET "/{id}" with id=42 sends GET to "https://catalog.example/api/books/42". **Do not concatenate URL strings manually in business code** when URI templates and resolvers are available.

A method can also use @HttpExchange(method = "OPTIONS", url = "/api/books") when an HTTP method has no shortcut annotation. The accept/contentType values on a method can refine or override shared settings. For requests without a body, do not set Content-Type just because the response is JSON: Content-Type describes the **request** content, whereas Accept describes the desired response.

### 3.2. Passing Arguments

| Parameter type | Effect | Example |
| --- | --- | --- |
| @PathVariable("id") | Replace "{id}" in URI template | /books/42 |
| @RequestParam("page") | Query parameter or form parameter depending on Content-Type | ?page=2 |
| @RequestHeader("Authorization") | Add header | Bearer token |
| @RequestBody | Encode object into body | JSON when supported by converter/encoder |
| @CookieValue | Add cookie | locale=vi |
| @RequestPart | A part of a multipart request | File or metadata |
| URI | Allow passing a dynamic URI, replacing annotation URL | Runtime-computed endpoint |
| HttpMethod | Allow choosing HTTP method at runtime | GET/HEAD per caller |

Example:

~~~java
@GetExchange("/search")
List<BookDto> search(
    @RequestParam("keyword") String keyword,
    @RequestParam("page") int page,
    @RequestHeader("X-Correlation-Id") String correlationId);
~~~

A call to search("spring web", 2, "trace-9") builds a request with encoded query parameters for keyword and page, plus the corresponding header. **Do not pre-encode query strings before passing them to @RequestParam** if the URI builder/client already does that; double encoding corrupts data.

Optional parameters must be declared appropriately for Spring's mechanism, such as @RequestParam(required = false) or Optional<T> when accepted by the resolver. For null values, do not assume Spring will silently drop them arbitrarily: resolvers have rules for required/optional parameters, and a null required parameter can fail.

**@RequestBody on the client** instructs how to serialize the HTTP request body; it does not automatically validate server-side business constraints. Validation, Content-Type, and JSON mapping must align with the remote API.

## 4. Creating Proxies from RestClient or WebClient

### 4.1. RestClient: Synchronous Calls

Spring Framework 6.1+:

~~~java
RestClient restClient = RestClient.builder()
    .baseUrl("https://catalog.example")
    .defaultHeader("Accept", "application/json")
    .build();

RestClientAdapter adapter = RestClientAdapter.create(restClient);

HttpServiceProxyFactory factory = HttpServiceProxyFactory
    .builderFor(adapter)
    .build();

BookHttpClient books = factory.createClient(BookHttpClient.class);
BookDto book = books.findById(42L, "vi");
~~~

This is an integration snippet: BookHttpClient and BookDto must have corresponding definitions. **Calling books.findById(...) executes a synchronous HTTP request on the calling thread**. RestClient should be created/configured once and reused via the proxy, such as by registering it as a Spring bean. Do not create a new client/factory for every business request without a clear reason.

Example Spring @Configuration using the application's BookHttpClient interface:

~~~java
@Configuration
class CatalogClientConfig {

    @Bean
    BookHttpClient bookHttpClient(RestClient.Builder builder) {
        RestClient client = builder
            .baseUrl("https://catalog.example")
            .build();

        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(client))
            .build()
            .createClient(BookHttpClient.class);
    }
}
~~~

RestClient.Builder can be provided by Spring Boot when the appropriate configuration/dependencies are present. If the application does not use Spring Boot, you can call RestClient.builder() directly. In Spring Boot 3.3, **declaring an annotated interface does not automatically turn it into a bean**: you still need to create the proxy or configure a separate registration mechanism.

### 4.2. WebClient: Reactive Types

If the application uses Reactor and needs non-blocking I/O, create a WebClientAdapter:

~~~java
WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example")
    .build();

HttpServiceProxyFactory factory = HttpServiceProxyFactory
    .builderFor(WebClientAdapter.create(webClient))
    .build();

ReactiveBookClient books = factory.createClient(ReactiveBookClient.class);
Mono<BookDto> response = books.findById(42L);
~~~

Corresponding interface:

~~~java
@HttpExchange("/api/books")
interface ReactiveBookClient {
    @GetExchange("/{id}")
    Mono<BookDto> findById(@PathVariable("id") long id);

    @GetExchange
    Flux<BookDto> streamBooks();
}
~~~

These are illustrative integration snippets: BookDto and variables belong to the application; required imports are in org.springframework.web.reactive.function.client.* and reactor.core.publisher.*.

With WebClient, Mono/Flux represent reactive pipelines; the HTTP request is typically executed **when subscribed to**. In a WebFlux controller, return Mono/Flux to the framework instead of calling block() on the event loop. Flux is only suitable when the API/protocol and decoder actually support item streaming (e.g., NDJSON or appropriate SSE); do not assume every endpoint returning JSON is streaming.

**The chosen return type must match the adapter.** RestClientAdapter is meant for synchronous results such as BookDto, ResponseEntity<BookDto>, HttpHeaders, or void; do not use Mono/Flux return types with an adapter that only supports synchronous execution. WebClientAdapter supports reactive types such as Mono<T>, Flux<T>, and ResponseEntity variants, and can also handle some synchronous types depending on the adapter, though calling synchronously on a reactive stack can cause unwanted blocking.

## 5. Choosing Return Types by Contract

| Return type | When to use |
| --- | --- |
| BookDto | Only need the decoded body; suitable for synchronous clients |
| List<BookDto> | Endpoint returns a JSON array and the decoder supports generics |
| ResponseEntity<BookDto> | Need status, headers, and body |
| ResponseEntity<Void> | Need status/headers of a response with no body |
| HttpHeaders | Only need headers |
| void | Response body is not used |
| Mono<BookDto> | A single asynchronous result on WebClientAdapter |
| Flux<BookDto> | A stream of elements when server and codec support it |
| Mono<ResponseEntity<BookDto>> | Reactive response with status, headers, and body |

Example accepting 204 No Content from DELETE:

~~~java
@DeleteExchange("/{id}")
ResponseEntity<Void> delete(@PathVariable("id") long id);
~~~

The caller can inspect the status. However, for 4xx/5xx statuses, **the client throws an exception by default**, so do not assume ResponseEntity will automatically return every error code. To handle error statuses per contract, configure the underlying RestClient/WebClient.

For collections or generic types like List<BookDto>, the proxy obtains the generic return type from the interface signature. When calling manually with the fluent client, you may need ParameterizedTypeReference where generics cannot be inferred from Class. A DTO record/class requires Jackson or a compatible codec for JSON mapping. Not every case of unexpected data, missing fields, or mismatched types is guaranteed to deserialize successfully just because the interface compiles.

## 6. Runnable Java 17 Demo: GET, POST, Path, Query, Header, and JSON

This example embeds a small HTTP server right inside the JVM, so it can run offline against the target API once Maven has downloaded dependencies. Uses **Java 17+**, **Maven**, and **Spring Boot 3.3.13** (including Spring Framework 6.1.x). For new active projects, choose a supported Spring Boot version per your team's policy; this version is pinned solely to demonstrate Spring 6.1 APIs.

Structure:

~~~text
http-exchange-demo/
├── pom.xml
└── src/main/java/demo/HttpExchangeDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>http-exchange-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/HttpExchangeDemo.java**:

~~~java
package demo;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

public class HttpExchangeDemo {

    public record Item(long id, String name) {}
    public record NewItem(String name) {}

    @HttpExchange(url = "/api/items", accept = MediaType.APPLICATION_JSON_VALUE)
    public interface ItemHttpClient {

        @GetExchange("/{id}")
        Item findById(@PathVariable("id") long id,
                      @RequestParam("lang") String lang);

        @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
        Item create(@RequestBody NewItem body,
                    @RequestHeader("X-Request-Id") String requestId);
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger received = new AtomicInteger();
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/api/items", exchange -> {
            received.incrementAndGet();
            String method = exchange.getRequestMethod();
            String path = exchange.getRequestURI().getPath();
            String query = exchange.getRequestURI().getRawQuery();
            String json;
            int status;

            if ("GET".equals(method)
                    && "/api/items/42".equals(path)
                    && "lang=vi".equals(query)) {
                status = 200;
                json = "{\"id\":42,\"name\":\"Notebook\"}";
            } else if ("POST".equals(method)
                    && "/api/items".equals(path)
                    && "op-001".equals(
                        exchange.getRequestHeaders().getFirst("X-Request-Id"))
                    && !new String(exchange.getRequestBody().readAllBytes(),
                                  StandardCharsets.UTF_8).isBlank()) {
                status = 201;
                json = "{\"id\":99,\"name\":\"Notebook\"}";
            } else {
                status = 404;
                json = "{\"error\":\"Not found\"}";
            }

            byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                "Content-Type", "application/json; charset=UTF-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });
        server.start();

        try {
            RestClient restClient = RestClient.builder()
                .baseUrl("http://127.0.0.1:" + server.getAddress().getPort())
                .build();

            ItemHttpClient api = HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(restClient))
                .build()
                .createClient(ItemHttpClient.class);

            Item found = api.findById(42L, "vi");
            Item created = api.create(new NewItem("Notebook"), "op-001");

            System.out.println("GET: " + found);
            System.out.println("POST: " + created);
            System.out.println("HTTP requests: " + received.get());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Run from the directory containing pom.xml:

~~~bash
mvn -q compile
mvn -q exec:java -Dexec.mainClass=demo.HttpExchangeDemo
~~~

**Stdout lines printed by the program:**

~~~text
GET: Item[id=42, name=Notebook]
POST: Item[id=99, name=Notebook]
HTTP requests: 2
~~~

Maven or libraries may output extra logs depending on the environment. The demo explicitly defines two responses on the local HTTP server so business outcomes are deterministic. The port is dynamically allocated by the OS to avoid port conflicts. There is no Spring Boot application context in this example: this is a **Spring HTTP client running from a Java main**. The first request uses URI template /api/items/{id} and query param lang=vi; the second sends a POST JSON body and X-Request-Id. The proxy uses RestClientAdapter and Jackson (via starter-web) to encode/decode records.

One caveat: in the demo, the X-Request-Id header **is only a marker allowing the demo server to accept the request**; it does not provide duplicate-POST protection on a real server. Preventing duplicate side effects requires implementing an idempotency contract with state persistence and concurrency control, not merely sending a header.

### Observing the Execution Flow

~~~mermaid
sequenceDiagram
    participant App as Java caller
    participant Proxy as ItemHttpClient proxy
    participant Client as RestClientAdapter + RestClient
    participant Server as HTTP Server
    App->>Proxy: findById(42, "vi")
    Proxy->>Client: GET /api/items/42?lang=vi
    Client->>Server: HTTP GET
    Server-->>Client: 200 + JSON Item
    Client-->>Proxy: decode Item
    Proxy-->>App: Item(42, "Notebook")
    App->>Proxy: create(NewItem, "op-001")
    Proxy->>Client: POST /api/items + JSON + header
    Client->>Server: HTTP POST
    Server-->>Client: 201 + JSON Item
    Client-->>App: Item(99, "Notebook")
~~~

The **Proxy → Client** part in the diagram is an internal call within the same JVM; only the **Client → Server** arrows go over HTTP. Annotations are not code running on the server; the server only sees ordinary HTTP requests.

## 7. Errors, Statuses, Timeouts, and Security

### 7.1. Do Not Hide Error Statuses

When using RestClientAdapter, status handling follows **RestClient**. By default, 4xx/5xx usually results in a RestClientResponseException or a corresponding subclass (such as HttpClientErrorException). With WebClientAdapter, WebClient produces WebClientResponseException on HTTP errors (under the default mechanism). Network/timeout errors and JSON mapping errors belong to different exception groups.

Proactively configure a handler on RestClient if you want to map statuses to business errors. Example **integration snippet**:

~~~java
RestClient client = RestClient.builder()
    .baseUrl("https://catalog.example")
    .defaultStatusHandler(
        status -> status.value() == 404,
        (request, response) -> {
            throw new CatalogItemNotFoundException(request.getURI().toString());
        })
    .build();
~~~

CatalogItemNotFoundException is an application custom runtime exception. This snippet is not a standalone program. With WebClient, you can use WebClient.Builder.defaultStatusHandler(...). The key point is configuring the underlying client used by the proxy; an @HttpExchange interface **does not automatically come with built-in retry, fallback, or separate status mapping**.

### 7.2. Operational Responsibilities to Configure

- **Timeout:** set appropriate transport/HTTP client timeouts, balanced against maximum business operation duration. Avoid unbounded requests on synchronous call paths.
- **Retry:** only retry transient errors and operations that are safe to repeat. GET is usually a candidate, whereas POST creating orders/payments can cause duplicate side effects if the response is lost.
- **Idempotency:** if a POST must be retried, the server needs deduplication mechanisms such as Idempotency-Key + unique constraint/transaction/deduplication; a header alone does not guarantee exactly-once execution.
- **Authentication:** provide tokens/API keys via filter/interceptor, @RequestHeader, or configured security mechanisms. Never hardcode secrets into interfaces, source code, or logs.
- **Observability:** record HTTP method, host/service, status, latency, correlation ID, and retry count; mask sensitive information.
- **URI/baseUrl:** control the target host. Dynamic URI parameters coming from untrusted input must be validated to avoid calling unauthorized internal addresses.
- **Connection pool and limits:** clients should reuse connections and bound concurrent requests, timeouts, and retry budgets according to actual load.
- **Serialization:** appropriate converters/codecs must be present (commonly Jackson for JSON), with naming/date formats aligned with the server.

Do not apply retry to every call on an interface just because they share the same annotation: retry policies depend on the specific method and business contract.

## 8. Designing Interfaces for Real-World APIs

A good HTTP interface typically represents one **remote service or group of related endpoints** with method names clearly expressing outcomes. Place baseUrl/host in configuration, keep paths and contracts in the interface; DTOs represent the wire format, separated from JPA entities and internal models when lifecycles evolve independently.

Example organization:

~~~text
client/catalog/
├── CatalogHttpClient.java   # @HttpExchange contract
├── CatalogClientConfig.java # proxy, baseUrl, auth, timeout
├── dto/
│   ├── BookDto.java
│   └── CreateBookRequest.java
└── CatalogFacade.java       # remote-call business logic, error mapping
~~~

Calling code in CatalogFacade depends on **CatalogHttpClient**, so it can be tested with a fake/mock interface or by testing the proxy against a mock HTTP server. Simply mocking the interface alone **does not prove that the URL, HTTP method, query, headers, and actual JSON are correct**; integration tests are needed to verify the requests generated by the client.

Design choices:
1. **RestClient + synchronous return types**: fits MVC applications, batch jobs, and synchronous services with accounted-for blocking call flows.
2. **WebClient + Mono/Flux**: fits WebFlux pipelines, concurrent tasks, or end-to-end reactive streaming.
3. **Direct fluent RestClient/WebClient**: fits when dynamic requests do not map naturally to an interface (highly variable method/URI/body), or when there are few calls.
4. **@HttpExchange interface**: fits remote APIs with relatively stable contracts, many endpoints, and a need for a clear, consistent Java API.

Do not turn every URL into a generic method accepting Object and lose type safety. Conversely, the interface should not contain retry logic, cache policies, database access, or business orchestration; keep those in client configuration/service layers.

## 9. Common Mistakes and Self-Checks

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Declaring the interface without creating a proxy | No bean to inject or cannot actually call | Create adapter + factory + createClient or configure official registration |
| Using Mono<T> with RestClientAdapter | Return type incompatible with synchronous adapter | Switch to WebClientAdapter or use T/ResponseEntity<T> |
| Missing @PathVariable for "{id}" | URI template is not expanded properly | Declare @PathVariable("id") explicitly |
| Mixing up Accept and Content-Type | Server may decode the body incorrectly | Accept for desired response; Content-Type for request body |
| Using @RequestParam for JSON object body | Body does not match contract | Use @RequestBody and JSON converter |
| Assuming ResponseEntity<T> captures every 404/500 | Client throws an exception on error | Configure status handling per contract |
| Enabling auto-retry on write POSTs | May create duplicate orders or transactions | Apply server-enforced idempotency |
| Calling block() in a reactive request handler | Blocks event loop, degrading throughput | Return Mono/Flux |
| Sharing DB entity DTOs as wire models | Internal schema changes break remote contract | Create DTOs per HTTP API version |
| Writing only unit tests mocking the interface | Misses wrong URI/header/body mapping | Test the real proxy against a mock HTTP server |
| Assuming @HttpExchange creates a remote endpoint | Server does not actually exist | Distinguish client proxy from @Controller implementation |

**Minimum test checklist:** verify HTTP method and URL; paths/queries containing special characters; headers/auth; serialization and response mapping; 2xx/204; 400/401/404/429/5xx; transport timeouts; malformed response body schemas; request retries with/without idempotency; proxy/bean creation on application startup. With WebClient, test subscriber/cancellation and ensure the event loop is not blocked where appropriate.

## 10. Knowledge Summary

@HttpExchange turns a remote HTTP contract into **a readable, easy-to-use Java interface**; HttpServiceProxyFactory generates a proxy to execute that contract over **RestClient** or **WebClient**. Annotations describe the request, the adapter determines the invocation mechanism, DTOs describe the data, while the server and client configuration determine authentication, error handling, timeouts, retries, and side-effect safety. Thus, type-safe interfaces make calling code concise and consistent, yet still require real HTTP tests and reliable business contracts.

## Official Documentation

- Spring Framework Reference, HTTP Service Clients: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-http-interface
- Spring Framework 6.1 API, @HttpExchange: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/service/annotation/HttpExchange.html
- Spring Framework 6.1 API, HttpServiceProxyFactory: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html
- Spring Framework 6.1 API, RestClientAdapter: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/support/RestClientAdapter.html
- Spring Framework Reference, WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
