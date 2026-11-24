# HttpServiceProxyFactory and Adapters for RestClient or WebClient

## 1. Overview: What Is an HTTP Service Client?

In Spring Framework, an **HTTP Service Client** is a way to declare a remote HTTP API as a **Java interface**. Each interface method is annotated to describe the HTTP method, URL, headers, request body, and response type. **HttpServiceProxyFactory** creates a proxy implementing the interface; when the application calls a method, the proxy translates it into an actual request through an HTTP client wrapped by an **adapter**.

For example, an endpoint GET /api/books/7 returning JSON:

~~~json
{"id":7,"title":"Spring in Action"}
~~~

You can write the interface:

~~~java
@HttpExchange(url = "/api/books", accept = MediaType.APPLICATION_JSON_VALUE)
public interface BookApi {
    @GetExchange("/{id}")
    Book findById(@PathVariable("id") long id);
}
~~~

When calling **bookApi.findById(7L)**, Spring builds the corresponding GET request, decodes JSON into **Book**, and returns it to the caller. **Book** can be a Java record:

~~~java
public record Book(long id, String title) {}
~~~

This is a **caller-side** HTTP client. It does not generate server endpoints, nor does it replace authentication, timeouts, retries, or service discovery. The remote server must still expose an API matching the contract.

~~~text
Business code: bookApi.findById(7)
                  |
                  v
        Interface @HttpExchange
                  |
          HttpServiceProxyFactory
                  |
       Proxy reads method + argument
                  |
           HttpExchangeAdapter
            /             \
 RestClientAdapter   WebClientAdapter
       |                    |
   RestClient            WebClient
    sync                 reactive
       \                    /
         HTTP request to server
                  |
         JSON response -> Book
~~~

Three concepts to distinguish:

- **HTTP service interface:** describes the HTTP contract and provides a typed API for Java code to call.
- **HttpServiceProxyFactory:** analyzes annotations/method signatures and creates the proxy at runtime; it is not an HTTP transport.
- **Adapter:** the bridge from the proxy down to a specific client. **RestClientAdapter** uses synchronous RestClient; **WebClientAdapter** uses reactive WebClient.

This approach reduces repetitive URI handling, serialization boilerplate, and centralizes contract declarations. When unusual HTTP details must be handled, you can still call the RestClient/WebClient fluent API directly.

### API Versions

This lesson uses **Java 17+**, focusing on **Spring Framework 6.2.x**; the concepts and common calls also apply in Spring Framework 7.x. You can run the example with **Spring Boot 3.5.x** (based on Spring 6.2).

- HttpServiceProxyFactory and WebClientAdapter have been available since Spring 6.0.
- RestClient and RestClientAdapter were introduced in Spring 6.1.
- With Spring 6.1+, prefer **HttpServiceProxyFactory.builderFor(adapter)** and **WebClientAdapter.create(webClient)**.
- Older examples using **HttpServiceProxyFactory.builder(adapter)** or **WebClientAdapter.forClient(webClient)** belong to deprecated APIs; avoid them in new code.

## 2. Declaring the HTTP Interface Accurately

Suppose a catalog system has:

| HTTP request | Body/response | Business operation |
| --- | --- | --- |
| GET /api/books/{id} | JSON Book | Look up one book |
| GET /api/books?keyword=java | JSON array Book | Search books |
| POST /api/books | JSON CreateBook, returns HTTP 201 and Book | Create a book |
| DELETE /api/books/{id} | No response body needed | Delete a book |

Data types:

~~~java
public record Book(long id, String title) {}
public record CreateBook(String title) {}
~~~

Synchronous interface:

~~~java
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.DeleteExchange;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

@HttpExchange(url = "/api/books",
              accept = MediaType.APPLICATION_JSON_VALUE)
public interface BookService {
    @GetExchange("/{id}")
    Book findById(@PathVariable("id") long id);

    @GetExchange
    List<Book> search(@RequestParam("keyword") String keyword);

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Book> create(
        @RequestHeader("X-Request-Id") String requestId,
        @RequestBody CreateBook request);

    @DeleteExchange("/{id}")
    void delete(@PathVariable("id") long id);
}
~~~

This is a contract-illustration sample. Top-level **public** types must be placed in identically named Java files, or turned into nested types like in the complete example in section 8. The real API server determines paths, statuses, and JSON.

Notes:
- **@HttpExchange** on the interface declares the shared URL prefix; method annotations such as **@GetExchange("/{id}")** append paths and define the method.
- **@PathVariable("id")** takes the Java argument and inserts it into the URI template.
- **@RequestParam("keyword")** normally becomes a query parameter. For **application/x-www-form-urlencoded** requests, request parameters are placed in the form body.
- **@RequestBody** is the Java data to serialize into the request (e.g., JSON).
- **@RequestHeader** adds a per-call header, suitable for correlation IDs or tokens passed per request.
- **ResponseEntity<Book>** lets you read status, headers, and body. Only declare **Book** when you genuinely need only the body.
- **void** executes the request without returning a body. If the API returns content you need, do not discard it with void.
- Other shortcuts include **@PutExchange**, **@PatchExchange**, and **@DeleteExchange**.
- **@GetExchange** in an HTTP interface belongs to **org.springframework.web.service.annotation**, unlike controller annotation **@GetMapping**.

**Accept** is the response format the client expects to receive; **Content-Type** is the format of the outgoing request body. Setting **accept = application/json** does not mean every request must also have JSON Content-Type.

You can use **@HttpExchange** directly on a method (with method/url) if a more general declaration is needed, though method-specific annotations are usually shorter and clearer.

### Parameter Names and Generic Types

Using **@PathVariable("id")** and **@RequestParam("keyword")** with explicit names avoids relying completely on compiler parameter-name metadata. Interface methods declaring **List<Book>** retain element type information through the reflective signature; the message converter knows how to decode a list of Book, unlike using raw **List**.

**Do not treat an HTTP interface as a REST controller**. The same annotation family can be used on the server side in certain Spring configurations, but creating a proxy via HttpServiceProxyFactory is client-side work.

## 3. Using HttpServiceProxyFactory with RestClientAdapter

**RestClient** is Spring Framework's synchronous HTTP client. How to use it when creating a proxy:

~~~java
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

RestClient restClient = RestClient.builder()
    .baseUrl("https://catalog.example.org")
    .build();

RestClientAdapter adapter = RestClientAdapter.create(restClient);

HttpServiceProxyFactory factory =
    HttpServiceProxyFactory.builderFor(adapter).build();

BookService books = factory.createClient(BookService.class);

Book book = books.findById(7L);
~~~

**catalog.example.org** is only an illustrative hostname. Assuming a real server has matching endpoints, **findById(7L)** issues a GET to **https://catalog.example.org/api/books/7**, waits for the response, decodes JSON, and returns Book. If the server errors or does not exist, the call may throw an exception.

RestClientAdapter implements the **HttpExchangeAdapter** contract, fitting synchronous return types:
- **void**.
- **HttpHeaders**, **Book**, or a specific **T**.
- **List<Book>** or **ResponseEntity<Book>**, **ResponseEntity<List<Book>>**.
- **ResponseEntity<Void>** when status and headers are needed without a response body.

A practical usage snippet:

~~~java
Book found = books.findById(7);
List<Book> matches = books.search("java");
ResponseEntity<Book> created =
    books.create("req-123", new CreateBook("Spring Cookbook"));

System.out.println(found.title());
System.out.println(created.getStatusCode());
~~~

This is only a usage snippet assuming a catalog API already exists; **stdout depends on the server**, so do not assume a fixed output string.

### When to Choose RestClientAdapter?

RestClientAdapter fits synchronous business layers, traditional Spring MVC applications, sequential jobs/batches, CLI tools, and integrations with controlled HTTP call volume. The caller thread waits for I/O; therefore, configure connection pools, concurrency, and timeouts appropriately.

Do not declare **Mono<Book>** or **Flux<Book>** as return types and wrap the interface with RestClientAdapter. It does not provide a reactive exchange equivalent to WebClient. If asynchronous streams are needed, use WebClientAdapter and declare an interface reflecting those semantics.

## 4. Using HttpServiceProxyFactory with WebClientAdapter

**WebClient** supports non-blocking/reactive I/O. WebClientAdapter implements **ReactorHttpExchangeAdapter**, allowing HTTP service interfaces to return Reactor **Mono** or **Flux**.

Corresponding reactive interface:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

@HttpExchange(url = "/api/books",
              accept = MediaType.APPLICATION_JSON_VALUE)
public interface ReactiveBookService {
    @GetExchange("/{id}")
    Mono<Book> findById(@PathVariable("id") long id);

    @GetExchange
    Flux<Book> list();

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<Book>> create(@RequestBody CreateBook request);
}
~~~

Creating the client, adapter, factory, and proxy:

~~~java
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example.org")
    .build();

WebClientAdapter adapter = WebClientAdapter.create(webClient);

HttpServiceProxyFactory factory =
    HttpServiceProxyFactory.builderFor(adapter).build();

ReactiveBookService books =
    factory.createClient(ReactiveBookService.class);

Mono<Book> result = books.findById(7L);
~~~

**result** here is a publisher describing the HTTP operation. The request executes upon subscription. In a Spring WebFlux controller, **return result** so the framework manages subscription/cancellation/errors; do not call **subscribe()** arbitrarily. Only call **result.block()** at a controlled synchronous boundary (e.g., main/tests), never call block() inside an event loop.

### Flux, Streaming, and Return Types

An HTTP service method can declare:

~~~java
@GetExchange(url = "/events",
             accept = MediaType.APPLICATION_NDJSON_VALUE)
Flux<Book> streamBooks();
~~~

This method illustrates when a remote server returns **application/x-ndjson**, with one JSON record per line. Flux emits Books as the decoder receives complete records. If the actual server returns **text/event-stream**, use the matching Content-Type and consider **Flux<ServerSentEvent<Book>>** if id/event/retry metadata is needed.

Do not assume an API is real-time merely because the return type is Flux. Whether items arrive incrementally also depends on framing, codec, server/proxy flushing, and subscription. Avoid calling **collectList()** on unbounded streams.

### Can Synchronous Return Types Be Used with WebClientAdapter?

Spring also supports synchronous return types such as **Book** or **ResponseEntity<Book>** when using WebClientAdapter, but to return Book directly the proxy must wait for the response. Therefore choose **Mono/Flux** if the entire call chain needs to be non-blocking.

There is no need to force sharing one Java interface between sync and reactive clients when usage APIs differ. A pair of interfaces makes the contracts explicit:

~~~text
BookService.findById(id)          -> Book
ReactiveBookService.findById(id)  -> Mono<Book>
~~~

They can target the same endpoint while their result types reflect different execution models.

## 5. Adapter Comparison Table

| Criterion | RestClientAdapter | WebClientAdapter |
| --- | --- | --- |
| Wrapped client | RestClient | WebClient |
| Adapter type | HttpExchangeAdapter | ReactorHttpExchangeAdapter |
| Typical usage | Synchronous (blocking caller) | Reactive, non-blocking |
| Natural return types | Book, List<Book>, ResponseEntity<Book>, void | Mono<Book>, Flux<Book>, Mono<ResponseEntity<Book>> |
| Can sync types be used? | Yes | Yes, but must wait for response |
| Long-lived streams | Not primary target | Better suited with Flux |
| Error/status policy | RestClient Builder/request factory | WebClient Builder/connector |
| Suitable scenarios | MVC, batch, and synchronous integration layers | WebFlux, high concurrent I/O, streams |

**HttpServiceProxyFactory does not turn a synchronous method into a reactive one on its own.** The adapter and return type determine how the request operates. Switching adapters while keeping the entire interface unchanged can mismatch the desired response model.

## 6. Registering Proxies as Beans in Spring Boot

Place client/proxy configuration in **@Configuration**, then inject the interface into services. This supports reusing HTTP clients, per-environment configuration, and easier testing. In Spring Boot applications, both **RestClient.Builder** and **WebClient.Builder** may be available:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration
public class RemoteClientConfig {

    @Bean
    BookService bookService(RestClient.Builder builder) {
        RestClient http = builder
            .baseUrl("https://catalog.example.org")
            .build();
        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(http))
            .build()
            .createClient(BookService.class);
    }

    @Bean
    ReactiveBookService reactiveBookService(WebClient.Builder builder) {
        WebClient http = builder
            .baseUrl("https://catalog.example.org")
            .build();
        return HttpServiceProxyFactory
            .builderFor(WebClientAdapter.create(http))
            .build()
            .createClient(ReactiveBookService.class);
    }
}
~~~

Interfaces/records must belong to compatible packages with the configuration (or have proper imports). The URL in the example is an illustrative host. Real configurations should pull from **application.properties** or **@ConfigurationProperties**, for example:

~~~properties
catalog.base-url=https://catalog.example.org
~~~

With **@Value** or type-safe configuration properties, inject those values into the bean factory method instead of hardcoding hostnames. Create separate clients when hosts, credentials, base URLs, timeouts, or trust policies differ; if multiple interfaces share the same host and policy, one factory can call **createClient** for multiple interfaces.

**Important:** Spring Boot only auto-provides a WebClient.Builder bean when the appropriate WebFlux dependency is on the classpath; in applications without WebFlux, add the matching dependency/client configuration. Using WebClient to call APIs **does not require the whole application to be a WebFlux server**.

### What to Configure on the Underlying HTTP Client

- **baseUrl**, default headers, and how authorization is attached per request.
- Connection pool, TLS, HTTP proxy, and connect/read/response timeouts.
- Jackson converters or WebFlux codecs, buffer sizes, and media types.
- Interceptors/filters for logging with sensitive-data redaction, tracing, and metrics.
- HTTP status handlers, 404/5xx mapping, retry policies, and circuit breakers per business needs.

These settings belong to **RestClient.Builder**, **WebClient.Builder**, or the connector/request factory; **HttpServiceProxyFactory** handles translating interface invocations into HTTP exchanges.

## 7. Return Types, Error Handling, and Advanced Customizations

### 7.1 Return Types Are Determined by the Adapter

With RestClientAdapter, common return types include:

~~~java
void delete(long id);
Book findById(long id);
ResponseEntity<Book> getWithHeaders(long id);
List<Book> findAll();
~~~

With WebClientAdapter:

~~~java
Mono<Void> deleteReactive(long id);
Mono<Book> findByIdReactive(long id);
Flux<Book> stream();
Mono<ResponseEntity<Book>> getWithHeadersReactive(long id);
~~~

Spring also supports **Mono<ResponseEntity<Flux<T>>>** when both status and streaming body are needed on the reactive adapter. Declaring accurate generic types on methods helps decoders construct the right DTOs. **Mono<List<Book>>** emits one list once decoding completes; **Flux<Book>** emits each Book. **ResponseEntity** provides status and headers, whereas a plain DTO is just the body.

### 7.2 HTTP Error Mapping

By default, RestClient turns HTTP error statuses into **RestClientException** types (e.g., **RestClientResponseException** with status/body), while WebClient typically emits **WebClientResponseException** in the reactive pipeline. Do not treat network errors, JSON decoding errors, and HTTP 4xx/5xx as a single error category.

Example 404 handler configuration for RestClient:

~~~java
RestClient rest = RestClient.builder()
    .baseUrl("https://catalog.example.org")
    .defaultStatusHandler(
        status -> status.value() == 404,
        (request, response) -> {
            throw new IllegalStateException("Book not found");
        })
    .build();
~~~

Corresponding example for WebClient:

~~~java
WebClient web = WebClient.builder()
    .baseUrl("https://catalog.example.org")
    .defaultStatusHandler(
        status -> status.value() == 404,
        response -> Mono.just(
            new IllegalStateException("Book not found")))
    .build();
~~~

Both code snippets are **configuration fragments**, not standalone runnable programs; imports for RestClient/WebClient/Mono are required. RestClient's status handler has a synchronous handler signature taking request and response; WebClient's handler takes response and returns a Publisher emitting a Throwable. Do not copy lambdas verbatim from one client to the other.

Errors should be designed around business semantics: 404 may map to Optional/empty data, 409 requires conflict handling, and 429 can be retried per Retry-After. Do not swallow all 4xx responses to return null DTOs; doing so can mask configuration or security errors.

### 7.3 Timeouts, Retries, and Lifecycle

- Synchronous: set timeouts on the HTTP client/request factory. Do not let threads wait indefinitely when downstream fails.
- Reactive: set network timeouts on the connector and business timeouts in Reactor when needed; note that inter-element timeouts can break valid streams.
- **WebClientAdapter** can support a block timeout for methods returning synchronous types, though configuring timeouts on the underlying HTTP client is usually clearer.
- Retrying resource-creating POSTs can cause duplicates; only retry safely with an idempotency mechanism or clear contract.
- Reactive Mono/Flux requires subscription; WebFlux controllers should return publishers. Do not call **block()** on the event loop.
- For long-lived streams, manage cancellation, buffering, error signals, backpressure, and server flushing behavior.

### 7.4 Customizing Resolvers for Parameter Objects

When an API requires three query parameters but Java wants a **SearchFilter** object, you can create an **HttpServiceArgumentResolver**:

~~~java
public record SearchFilter(String owner, String language, String term) {}

public class SearchFilterResolver
        implements HttpServiceArgumentResolver {

    @Override
    public boolean resolve(
            Object argument,
            MethodParameter parameter,
            HttpRequestValues.Builder values) {
        if (!SearchFilter.class.equals(parameter.getParameterType())) {
            return false;
        }

        SearchFilter filter = (SearchFilter) argument;
        values.addRequestParameter("owner", filter.owner());
        values.addRequestParameter("language", filter.language());
        values.addRequestParameter("term", filter.term());
        return true;
    }
}
~~~

Required imports are **org.springframework.core.MethodParameter**, **org.springframework.web.service.invoker.HttpServiceArgumentResolver**, and **org.springframework.web.service.invoker.HttpRequestValues**. This resolver example is a fragment extracted from a system with an interface; it shows how to map an object to query parameters, not a standalone main.

Attaching the resolver:

~~~java
HttpServiceProxyFactory factory = HttpServiceProxyFactory
    .builderFor(RestClientAdapter.create(restClient))
    .customArgumentResolver(new SearchFilterResolver())
    .build();
~~~

Spring invokes custom resolvers before default resolvers; if a resolver does not support the parameter type, it must return **false** so other resolvers can continue. The Builder also supports **conversionService(...)** to convert values to Strings and **embeddedValueResolver(...)** for values embedded in HTTP service metadata.

### 7.5 Headers, URI, and Multipart

Interfaces also support **@CookieValue**, **@RequestPart**, **URI** parameters (overriding the declared URL), and other arguments. Multipart request example:

~~~java
@PostExchange(
    url = "/files",
    contentType = MediaType.MULTIPART_FORM_DATA_VALUE)
ResponseEntity<Void> upload(
    @RequestPart("description") String description,
    @RequestPart("file") Resource file);
~~~

Import **org.springframework.core.io.Resource**. The caller passes a **FileSystemResource** for an existing file; part names and media types must match the server contract. Multipart upload does not automatically mean the response is also multipart: if the server returns JSON, declare the JSON response DTO as usual.

## 8. Complete Java 17 Example: One API, Two Adapters

The demo below starts a minimal loopback HTTP server using the JDK, then calls the same endpoint through **RestClientAdapter** and **WebClientAdapter**. No internet server is needed; Maven downloads the required Spring dependencies on first run.

Structure:

~~~text
http-interface-demo/
  pom.xml
  src/main/java/demo/HttpInterfaceDemo.java
~~~

**pom.xml** uses Spring Boot 3.5.0 to manage Spring 6.2.x versions:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>http-interface-demo</artifactId>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/HttpInterfaceDemo.java**:

~~~java
package demo;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import com.sun.net.httpserver.HttpServer;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;
import reactor.core.publisher.Mono;

public class HttpInterfaceDemo {

    public record Book(long id, String title) {}

    @HttpExchange(url = "/api/books",
                  accept = MediaType.APPLICATION_JSON_VALUE)
    public interface BlockingBooks {
        @GetExchange("/{id}")
        Book find(@PathVariable("id") long id);
    }

    @HttpExchange(url = "/api/books",
                  accept = MediaType.APPLICATION_JSON_VALUE)
    public interface ReactiveBooks {
        @GetExchange("/{id}")
        Mono<Book> find(@PathVariable("id") long id);
    }

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/books/1", HttpInterfaceDemo::respond);
        server.start();

        try {
            String baseUrl =
                "http://127.0.0.1:" + server.getAddress().getPort();

            RestClient rest = RestClient.builder()
                .baseUrl(baseUrl)
                .build();

            BlockingBooks blocking = HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(rest))
                .build()
                .createClient(BlockingBooks.class);

            WebClient web = WebClient.builder()
                .baseUrl(baseUrl)
                .build();

            ReactiveBooks reactive = HttpServiceProxyFactory
                .builderFor(WebClientAdapter.create(web))
                .build()
                .createClient(ReactiveBooks.class);

            System.out.println("RestClient -> " +
                blocking.find(1).title());
            System.out.println("WebClient -> " +
                reactive.find(1).block().title());
        } finally {
            server.stop(0);
        }
    }

    private static void respond(com.sun.net.httpserver.HttpExchange exchange)
            throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            exchange.sendResponseHeaders(405, -1);
            exchange.close();
            return;
        }

        byte[] body = "{\"id\":1,\"title\":\"Spring\"}"
            .getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", "application/json");
        exchange.sendResponseHeaders(200, body.length);

        try (OutputStream output = exchange.getResponseBody()) {
            output.write(body);
        }
    }
}
~~~

**Run** in the **http-interface-demo** directory, requiring JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.HttpInterfaceDemo
~~~

**Output printed to stdout by the program** on a successful run:

~~~text
RestClient -> Spring
WebClient -> Spring
~~~

Explanation:
1. JDK HttpServer serves GET /api/books/1 and returns **{"id":1,"title":"Spring"}**. A random port is chosen when binding port **0**.
2. RestClient and WebClient share the same base URL but use separate adapters and interfaces.
3. Calling **blocking.find(1)** sends a synchronous request and returns Book.
4. **reactive.find(1)** returns Mono; **block()** is used solely for illustration in synchronous main, causing the publisher to subscribe and read JSON.
5. **server.stop(0)** in finally stops the server even if an HTTP call fails.

No other fixed HTTP output should be assumed. When running with Maven, tool logs/warnings may appear depending on the environment; the two lines above are the ones emitted directly by the program's **System.out.println**.

## 9. Contract Testing and Common Errors

### Two Test Layers Should Be Separated

**Proxy + HTTP contract testing**: use a mock server such as WireMock, MockWebServer, or JDK HttpServer to verify request method, path, query, headers, request JSON, status, and response deserialization. The Java main example in section 8 tests one successful GET for both adapters.

**Business logic testing**: mock the Java interface **BookService**/**ReactiveBookService** itself in service unit tests; there is no need to create an HTTP proxy when a test only verifies orchestration. Both test types complement each other.

Additional scenarios for contract tests: server returns 404/500, malformed body schema, unexpected content type, missing token, slow server, subscription cancellation, and retrying side-effecting operations.

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Cannot find builder(adapter), forClient(...) | Mixing Spring 6.0 and 6.1+/6.2 examples | Use builderFor and create matching your version |
| Mono/Flux unsupported | Reactive interface paired with RestClientAdapter | Use WebClientAdapter |
| Hang or block() error in WebFlux handler | Method returns synchronously or blocks on event loop | Keep Mono/Flux pipeline and return publisher |
| 404 despite correct host | baseUrl and @HttpExchange/@GetExchange concatenate wrong path | Verify actual path and path variables |
| Path variable not resolved | Parameter name does not match placeholder | Explicitly specify @PathVariable("id") |
| JSON error / ClassCastException | Return type mismatches JSON, raw types used | Declare exact DTO/generics |
| Flux receives no data | Not subscribed, server does not flush, wrong media type | Verify NDJSON/SSE, subscriber, and flushing |
| 401 or leaked token in logs | Wrong auth header setup or unredacted logging | Apply proper auth policy, redact tokens from logs |
| POST duplicated after retry | Missing idempotency key | Design safe retries |
| HTTP 4xx/5xx hard to handle | No status handler configured | Configure on RestClient/WebClient |
| Unexplained timeouts | Timeout not set on HTTP connector | Explicitly set connect/read/response timeouts |

**Limitations to keep in mind:** HTTP interfaces do not automatically handle every protocol variant. Special requests may require a **customArgumentResolver** or going directly to the fluent client API. **RequestEntity** is generally not supported as an HTTP service method parameter because it already carries the entire HTTP request; use specific annotated parameters instead.

## 10. Project Adoption Checklist

1. Write the Java interface contract with the right method, URL, parameters, and request/response types.
2. Choose RestClientAdapter if callers are synchronous, or WebClientAdapter if results need Mono/Flux and the application runs reactively.
3. Build RestClient/WebClient with proper base URL, auth, timeouts, converters/codecs, and error policy.
4. Create the proxy via **HttpServiceProxyFactory.builderFor(adapter).build().createClient(Interface.class)**.
5. Register the interface as a bean and inject it where used.
6. Verify actual HTTP behavior via contract tests, not merely Java compilation.
7. For reactive code, preserve subscription, cancellation, retry, and backpressure in the right context. Avoid blocking on the event loop.

### Review Questions

- Why does an **@HttpExchange** interface still need **HttpServiceProxyFactory** and an **adapter**?
- Can you swap RestClientAdapter for WebClientAdapter while keeping an interface returning **Mono<Book>**?
- When should you use **Book**, **ResponseEntity<Book>**, **Mono<Book>**, and **Flux<Book>**?
- If a remote API returns a JSON array, why is **List<Book>** better than raw **List**?
- Should authentication, timeouts, and status handlers be placed on the factory or the underlying client?
- When an HTTP service method receives a custom **SearchFilter**, should you use built-in annotations or **HttpServiceArgumentResolver**?

## Official Documentation

- [Spring Framework 6.2 – REST Clients, HTTP Interface](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html)
- [Spring Framework – Current REST Clients documentation](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [HttpServiceProxyFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html)
- [RestClientAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/support/RestClientAdapter.html)
- [WebClientAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/client/support/WebClientAdapter.html)
