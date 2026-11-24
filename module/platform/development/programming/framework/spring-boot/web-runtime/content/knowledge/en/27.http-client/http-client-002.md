# RestClient, RestTemplate, and WebClient by Application Style in Spring Boot

## 1. Scenario and Objectives

A Spring Boot application frequently needs to **make HTTP calls to other services**: fetching product prices from a catalog, calling a payment system, pulling partner data, connecting to internal APIs, or consuming an event stream. Spring Framework provides three well-known HTTP clients:

- **RestClient**: A **synchronous (blocking)** HTTP client with a modern **fluent** API, suited for imperative Java.
- **RestTemplate**: A **synchronous** HTTP client with a traditional template-method API. Useful when maintaining existing systems; for new code, consider RestClient.
- **WebClient**: A **non-blocking, reactive** HTTP client with a fluent API producing `Mono` or `Flux` streams. Suited for Spring WebFlux applications, high-concurrency I/O calls, and asynchronous data streams.

**The decision point is not "Which API is newest?" but "Which application style and execution model are required?".** A Spring MVC app using JDBC/JPA and imperative request handling typically benefits from RestClient. A WebFlux app running on an event loop should use WebClient and avoid calling RestClient/RestTemplate directly on the event loop. You can still use WebClient inside an MVC application, though using it does not automatically turn controllers, JPA, or blocking business code into reactive code.

This lesson provides an architecture selection matrix, execution mechanics, a standalone runnable **Java 17+ Spring Boot 3.5.16 Maven** example, error/timeout handling, pooling, JSON, security, tests, and a migration path. Separate fragments are explicitly labeled; the complete demo requires no Internet access to a third-party service because it uses a local simulated upstream.

**Version scope:** APIs and package names in the examples follow **Spring Boot 3.5.x / Spring Framework 6.2.x**. In newer Spring Framework generations, deprecation status and some packages or configuration properties may change; when upgrading a major version, consult the exact version's documentation rather than copying Boot 3.5 configuration verbatim.

## 2. Distinguishing the HTTP Server from the HTTP Client

During a request from a browser:

```text
Browser -> Spring Boot /api/orders/7
              |
              | app needs product #7
              v
          HTTP client
              |
              +--> GET http://catalog-service/products/7
              |          |
              |          v
              |      Catalog HTTP server
              |
              v
          Process result -> reply to browser
```

Spring Boot runs on Tomcat/Jetty/Undertow/Reactor Netty in the **server role**. RestClient, RestTemplate, or WebClient runs in the **client role** to issue requests to an upstream service. Server and client models are related choices, but **they do not have to match**:

- A **Spring MVC server on Tomcat** can call RestClient, RestTemplate, or WebClient.
- A **Spring WebFlux server on Reactor Netty** should use WebClient for non-blocking HTTP I/O.
- A batch/scheduled job with no inbound HTTP server can still use RestClient or WebClient depending on execution style.
- A Spring MVC server does not need to migrate to WebFlux just to use WebClient for aggregating multiple outbound calls.

Do not confuse **`spring-boot-starter-web`** with an "HTTP client starter". It primarily enables Spring MVC and a web server while also bringing in Spring Web and synchronous HTTP client APIs. `spring-boot-starter-webflux` brings in WebFlux APIs, including `WebClient` and typically Reactor Netty client/server.

## 3. Selection Matrix by Application Style

| Context | Preferred choice | Why | What to avoid |
| --- | --- | --- | --- |
| Spring MVC, standard controllers/services, JDBC/JPA | **RestClient** | Synchronous, readable, fluent API, fits thread-per-request | Using WebClient only to call `.block()` on every request with no gain |
| Stable legacy MVC project using `RestTemplate` | **Keep RestTemplate and migrate gradually if needed** | Avoids breaking battle-tested code | Forcing a big-bang rewrite with no measurable benefit |
| End-to-end reactive Spring WebFlux | **WebClient** | Non-blocking, composes `Mono/Flux`, cancellation/backpressure | Calling blocking RestClient/RestTemplate directly on the event loop |
| MVC calling two independent services in parallel | RestClient with managed concurrency **or** WebClient with `Mono.zip` | Avoids sequential waiting; choose based on manageability and existing code | Spawning hundreds of threads or calling `block()` sequentially on each WebClient request |
| Scheduled job processing records sequentially | **RestClient** | Simple imperative code, straightforward timing control | Overly complex reactive chains without need |
| Pipeline fetching paginated results/event streams | **WebClient** | `Flux`, streaming, non-blocking | Collecting unbounded streams with `collectList().block()` |
| Reactive API gateway/aggregator | **WebClient** | Combines multiple HTTP requests in a reactive pipeline | Inserting blocking JDBC/JPA or `Thread.sleep` on the event loop |
| Need compatibility with legacy layer and many `RestTemplate` interceptors | Existing RestTemplate, optionally creating **RestClient from RestTemplate** | Supports incremental migration | Changing the underlying HTTP transport without testing |
| Team does not use Reactor, simple synchronous needs | **RestClient** | Lower abstraction overhead | Using `Mono` just because it looks modern |
| Need a typed interface API contract | `@HttpExchange` + RestClient/WebClient adapter | Decouples the interface from client implementation | Assuming an interface automatically makes every method non-blocking |

These are guidelines, not rigid laws. If an MVC app downloads thousands of network resources concurrently, WebClient can make sense. If WebFlux must invoke a blocking library with no alternative, you must isolate the blocking work on an appropriate scheduler—but that is an **adaptation**, not proof that RestClient is non-blocking.

## 4. Actual Execution Mechanics

### 4.1. RestClient and RestTemplate: Synchronous Calls

```text
Servlet request thread
    |
    | controller
    |  -> restClient.get()...retrieve().body(...)
    |  -> wait for upstream HTTP response
    |  -> receive Product
    |  -> continue processing
    |
HTTP response sent to browser
```

When called on the current thread, the program **waits for the result** before executing the next statement. The JVM may use different underlying I/O mechanisms, but the application-level API remains **blocking synchronous**. With a servlet request thread pool, many concurrent requests waiting on upstream services can occupy many worker threads, so you must configure timeouts, pool sizes, bulkheads, and concurrency limits.

### 4.2. WebClient: Declaring a Pipeline, Executing on Subscription

```text
WebFlux request / MVC async handler
    |
    | webClient.get()...retrieve().bodyToMono(Product.class)
    |             |
    |             +-- creates operation description (Mono)
    |                      |
    |                   subscription
    |                      |
    |            non-blocking network I/O
    |                      |
    |              Product / error / cancel
    |                      |
    v                      v
  downstream operators -> HTTP response
```

`WebClient` is a non-blocking interface; **`Mono` is typically lazy/cold**. Calling `bodyToMono` only creates a Publisher; I/O usually starts upon subscription (the framework subscribes when a controller returns `Mono`). Never call `.subscribe()` manually inside a controller and return immediately: doing so detaches error handling and request cancellation from the HTTP lifecycle and makes concurrency hard to control.

**Non-blocking does not mean "zero threads".** Network connections still run on appropriate event loops/threads. The benefit is avoiding tying up a request thread waiting on I/O in the same synchronous way and coordinating multiple upstream calls with a reasonable number of threads. You still need to control connections, rates, backpressure, and other resources.

### 4.3. The Risk of `.block()`

```java
// Inside a reactive event-loop: DO NOT do this.
Product product = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .block();
```

This is a **warning snippet** (variables `webClient` and `id` must exist). On a WebFlux/Reactor non-blocking thread, `block()` may be rejected by Reactor with an exception and/or destroy scalability. On an imperative worker thread outside the event loop, `block()` **can work**, but if the goal is simply synchronous HTTP, `RestClient` is usually clearer and simpler.

Spring Framework also supports synchronous use of WebClient for imperative apps, but when reactive composition is not needed, prefer the API suited to your style. Do not call `block()` sequentially on one Mono after another if you actually want requests to run in parallel.

## 5. RestClient: The Synchronous Fluent HTTP Client

`RestClient` was introduced in Spring Framework 6.1. In Spring Framework 6.2/Boot 3.5, it is typically the right choice for **new** HTTP calls in imperative applications.

### 5.1. Configuration and GET Calls

```java
RestClient client = RestClient.builder()
        .baseUrl("https://catalog.example.com")
        .build();

Product product = client.get()
        .uri("/products/{id}", 42)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(Product.class);
```

This is a **snippet** requiring `RestClient`, `Product`, and `MediaType` inside an appropriate class/method. At runtime, `body(Product.class)` is the terminal operation that sends the request, waits for the response, and deserializes it into a Java object. Calling `retrieve()` alone is not enough; it returns a `ResponseSpec` to continue declaring how to read the response.

`RestClient.Builder` supports `baseUrl`, `defaultHeader`, `requestInterceptor`, `requestFactory`, message converters, and more. In Spring Boot, you should **inject the auto-configured builder** rather than always calling `RestClient.create()`, because Boot prepares the builder with observability/customizers and the appropriate HTTP client factory.

### 5.2. POST JSON

```java
CreateOrderRequest request = new CreateOrderRequest(7, 3);

OrderDto created = client.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .body(request)
        .retrieve()
        .body(OrderDto.class);
```

This is a **snippet** assuming the DTOs and `client` already exist. Serialization/deserialization uses Spring HTTP message converters; in Boot's web starter, Jackson is usually present. Do not build JSON manually by string concatenation when typed DTOs exist, and never interpolate unvalidated user data into URL strings.

### 5.3. Headers, Status, and Entity

```java
ResponseEntity<Product> response = client.get()
        .uri("/products/{id}", 42)
        .header("X-Request-ID", requestId)
        .retrieve()
        .toEntity(Product.class);

HttpStatusCode status = response.getStatusCode();
String upstreamEtag = response.getHeaders().getETag();
Product body = response.getBody();
```

This snippet requires imports for `ResponseEntity`, `HttpStatusCode`, `Product`, and variable `requestId`. When you need status, headers, and body together, `toEntity` is better than reading only the body. For responses without a body, `toBodilessEntity()` is available.

### 5.4. Error Handling

With `retrieve()`, 4xx/5xx error statuses by default throw a Spring HTTP client exception rather than silently returning an empty `Product`. You can use `onStatus`:

```java
Product product = client.get()
        .uri("/products/{id}", 42)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                (request, response) -> {
                    throw new IllegalArgumentException(
                            "Product not found upstream");
                })
        .body(Product.class);
```

This is a custom-mapping snippet. In a real application, create a domain exception (for example `ProductNotFoundException`), preserve appropriate request context, and avoid leaking full error bodies containing sensitive data to public responses or logs.

### 5.5. Choosing the Underlying HTTP Transport

RestClient is an **API facade** over HTTP request factories. You can select JDK HttpClient or Apache HttpComponents when you need pooling, proxies, TLS, HTTP/2 support, or specific tuning. **Do not infer pool sizes or timeouts from the name RestClient alone**; they depend on the request factory and client library detected by Spring Boot.

A built RestClient can be reused safely across multiple threads. Do not create a new client with a new connection pool **on every request**; typically build a singleton bean per upstream service.

## 6. RestTemplate: The Traditional Synchronous Approach and Why You Still See It

`RestTemplate` existed long before RestClient. It offers methods such as:

```java
Product product = restTemplate.getForObject(
        "https://catalog.example.com/products/{id}",
        Product.class, 42);

ResponseEntity<Product> response = restTemplate.getForEntity(
        "https://catalog.example.com/products/{id}",
        Product.class, 42);
```

This is a snippet assuming `restTemplate` is already configured. Other methods include `postForObject`, `postForEntity`, `exchange`, `execute`, and PUT/DELETE operations.

### 6.1. Why RestTemplate Is Not "Wrong"

- Many long-running production systems rely on it with well-tested interceptors and error handlers.
- Spring's `HttpMessageConverter` and `ClientHttpRequestFactory` mechanisms still support synchronous HTTP requests.
- When legacy code is stable, migration must weigh regression risk.
- In Spring Framework 6.2, the documentation lists RestTemplate as a synchronous client while recommending RestClient for new code; in newer Spring Framework versions, API status may evolve.

The **mistake** is confusing RestTemplate with **reactive** just because Spring Framework also includes WebFlux. RestTemplate is synchronous; calling it directly on a Reactor event loop will block.

### 6.2. Inject RestTemplateBuilder Instead of Assuming a RestTemplate Bean Exists

Spring Boot normally **does not provide a single global `RestTemplate` bean**; Boot provides `RestTemplateBuilder` so you can construct `RestTemplate` instances configured for each consumer:

```java
@Bean
RestTemplate catalogRestTemplate(RestTemplateBuilder builder) {
    return builder
            .connectTimeout(Duration.ofSeconds(2))
            .readTimeout(Duration.ofSeconds(3))
            .build();
}
```

This is a `@Bean` snippet inside a `@Configuration` class, requiring imports for `RestTemplateBuilder` (in Boot 3.5, `org.springframework.boot.web.client.RestTemplateBuilder`), `RestTemplate`, and `Duration`. In Boot 3.5, use `connectTimeout`/`readTimeout`; the older `setConnectTimeout`/`setReadTimeout` methods were deprecated in recent Boot 3.x releases.

### 6.3. `exchange()` for Controlling HTTP Method and Headers

```java
HttpHeaders headers = new HttpHeaders();
headers.setBearerAuth(accessToken);
HttpEntity<Void> entity = new HttpEntity<>(headers);

ResponseEntity<Product> response = restTemplate.exchange(
        "https://catalog.example.com/products/{id}",
        HttpMethod.GET,
        entity,
        Product.class,
        42);
```

This snippet illustrates passing a bearer token. **Do not** hardcode real tokens in source code; tokens must be retrieved securely and redacted in logs/traces.

### 6.4. Migration Path to RestClient

In Spring Framework 6.2 you can create a RestClient from an existing RestTemplate to **reuse its configured infrastructure**:

```java
RestTemplate legacy = /* existing RestTemplate */ ;
RestClient modern = RestClient.create(legacy);

Product product = modern.get()
        .uri("/products/{id}", 42)
        .retrieve()
        .body(Product.class);
```

This is a migration snippet; **`legacy` must have an appropriate base URI or use absolute URIs**. If no base URL was configured on the old RestTemplate, pass absolute URLs or configure a RestClient builder explicitly. Do not assume switching APIs preserves every detail: test the request factory, interceptors, error mapping, URI encoding, redirects, authentication, and timeouts.

Incremental migration approach: pick one outbound call service, replace the old method, compare HTTP requests/responses and tests; only then decide whether to replace the underlying builder/transport. You do not have to rewrite every RestTemplate at once.

## 7. WebClient: Non-Blocking, Reactive, and Streaming Support

`WebClient` lives in `org.springframework.web.reactive.function.client.WebClient` and is best configured via the `WebClient.Builder` provided by Spring Boot when WebFlux is on the classpath.

### 7.1. GET Returning `Mono<T>`

```java
Mono<Product> result = webClient.get()
        .uri("/products/{id}", 42)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(Product.class);
```

This is a snippet; it **does not immediately start an HTTP request when creating the Mono**. The framework can subscribe when a WebFlux controller returns `Mono<Product>`; inside services you can compose `map`, `flatMap`, `timeout`, and `onErrorResume` to build the pipeline.

### 7.2. Asynchronous POST

```java
Mono<OrderDto> created = webClient.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateOrderRequest(7, 3))
        .retrieve()
        .bodyToMono(OrderDto.class);
```

This snippet needs the DTOs and a configured WebClient. `bodyValue` suits an already-materialized body; for streaming/Publisher bodies, `body(...)` overloads are available.

### 7.3. Combining Two Independent Requests

```java
Mono<Product> left = webClient.get()
        .uri("/products/{id}", 1)
        .retrieve().bodyToMono(Product.class);

Mono<Product> right = webClient.get()
        .uri("/products/{id}", 2)
        .retrieve().bodyToMono(Product.class);

Mono<List<Product>> both = Mono.zip(left, right)
        .map(pair -> List.of(pair.getT1(), pair.getT2()));
```

This is a snippet; when `both` is subscribed to, the two independent requests can run **concurrently** instead of waiting sequentially. It does not guarantee "twice as fast" because of upstream latency, connection pools, and network contention. `zip` waits for both Monos to emit a value; if either Mono errors, the pipeline errors; if either completes empty, the zipped result may emit no list either. Design fallback/optional semantics explicitly.

### 7.4. Handling Status and Body Per Case

```java
Mono<Product> found = webClient.get()
        .uri("/products/{id}", 42)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                response -> Mono.error(
                        new IllegalArgumentException("Product not found")))
        .bodyToMono(Product.class);
```

This snippet turns a 404 into a domain exception. With WebClient, when you need to decode different bodies by status, use `exchangeToMono`:

```java
Mono<Product> found = webClient.get()
        .uri("/products/{id}", 42)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class);
            }
            return response.createException().flatMap(Mono::error);
        });
```

This illustrates `exchangeToMono`. Do not use the older `exchange()` API and forget to consume/release the body, as that can cause connection/memory leaks. `exchangeToMono`/`exchangeToFlux` let the framework manage response body lifecycle when the callback completes.

### 7.5. Streaming Multiple Items with `Flux`

```java
Flux<Product> stream = webClient.get()
        .uri("/products/stream")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(Product.class);
```

This is a snippet; **there is no `/products/stream` endpoint in the demo below**. It illustrates a service supporting SSE/streaming and returning matching JSON events. When streaming, avoid unbounded `collectList()` or `block()` on the event loop; set realistic concurrency, timeout, and memory/buffer limits.

### 7.6. WebClient Does Not Force the Server to Be WebFlux

In a Spring MVC application, WebClient can act as an outbound HTTP client. MVC can handle controllers returning `Mono<T>` via asynchronous request processing if the necessary reactive libraries are present. However:

- The Servlet server remains Tomcat/Jetty/Undertow per config; it does not silently switch to Reactor Netty.
- A Spring MVC controller differs from a WebFlux reactive handler in its request processing model.
- If business logic invokes blocking JDBC/JPA inside `map`/`flatMap` on the event loop, it is still **blocking** and can degrade performance.
- Choosing WebClient should stem from non-blocking, composition, or streaming requirements, not merely "having the WebFlux dependency".

## 8. Spring Boot Auto-Configuration: Which Builder Should You Inject?

### 8.1. The Builders

| API | Boot-provided builder | When available | How to use |
| --- | --- | --- | --- |
| RestClient | `RestClient.Builder` | Spring Web client support on classpath and matching Boot auto-configuration | Inject builder, `baseUrl(...).build()` |
| RestTemplate | `RestTemplateBuilder` | Spring Web/RestTemplate support on classpath and Boot auto-configuration | Inject builder, `rootUri(...).build()` |
| WebClient | `WebClient.Builder` | Spring WebFlux/WebClient support on classpath and Boot auto-configuration | Inject builder, `baseUrl(...).build()` |

Builders can be **stateful**, whereas built clients are generally safe to reuse. When a builder is mutated, clients built afterward pick up the new configuration. Separate configuration per upstream (base URL, auth, timeout, pool) and use `builder.clone()` when creating independent variants.

### 8.2. Both Starters on the Classpath

The demo example uses both:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

In Spring Boot 3.5, if both MVC and WebFlux starters are present, Boot typically selects a **Servlet web application (Spring MVC)**; WebClient remains available for outbound calls. If you want a true reactive server, create the project **with only the WebFlux starter**, unless there is a specific configuration reason. Do not add the WebFlux starter just to "enable reactive" and assume JPA becomes reactive.

### 8.3. Spring Boot 3.5 Timeout Configuration

Spring Boot **3.5** provides HTTP client properties:

```properties
# Synchronous HTTP clients: RestClient and RestTemplate
spring.http.client.connect-timeout=2s
spring.http.client.read-timeout=3s

# Reactive HTTP client connector (WebClient)
spring.http.reactiveclient.connect-timeout=2s
spring.http.reactiveclient.read-timeout=3s
```

These properties are applied by Boot through HTTP client/request-factory auto-configuration when applicable. They are **not timeouts for inbound Tomcat requests**, nor do they replace a `WebClient` pipeline timeout like `.timeout(Duration)` when an overall operation limit is needed. **Property names differ across major versions**: do not substitute `spring.http.clients.*` from newer Boot docs and expect it to work on Boot 3.5.

### 8.4. One Client Bean Per Upstream

In a system with catalog, payments, identity, and search services, create **clearly named client beans** or dedicated service wrappers:

- Each client gets its own base URL, TLS/auth, and timeout/pool policy.
- Do not embed a per-request bearer token or user cookie into a singleton client if values vary by request without a safe propagation mechanism.
- Use environment configuration for upstream endpoints; never hardcode production hosts in classes.
- Separate connection pool and response buffer policies for reactive streaming when workloads differ.
- Preserve Boot instrumentation (metrics, tracing, interceptors) when customizing builders.

## 9. Runnable Example: Same API via RestClient, RestTemplate, and WebClient

This example uses **Java 17**, **Maven**, and **Spring Boot 3.5.16**. To stay completely self-contained, the app exposes an "upstream" endpoint at `http://localhost:8080/upstream/products/{id}`, and the three HTTP clients call it over **HTTP loopback** as if calling a separate microservice. This is an **educational simulation**, not recommended for production because calling your own server over HTTP adds overhead and can deadlock if worker threads are exhausted.

Endpoints:

- `GET /upstream/products/7`: acts as the catalog service, returning `Product` JSON.
- `GET /demo/rest-client/7`: RestClient outbound call returning JSON.
- `GET /demo/rest-template/7`: RestTemplate outbound call returning JSON.
- `GET /demo/web-client/7`: returns `Mono<Product>` from WebClient for Spring MVC async handling.
- `GET /demo/web-client-parallel`: WebClient fetches two products in parallel using `Mono.zip`.

No database, Docker, frontend, or API key is needed to run the example. Any production hostnames mentioned below are illustrative only and must not be used as real targets.

### 9.1. Directory Structure

```text
http-clients-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/httpclients/
    │   │   ├── HttpClientsDemoApplication.java
    │   │   ├── Product.java
    │   │   ├── UpstreamController.java
    │   │   ├── OutboundClientsConfig.java
    │   │   ├── OutboundProductService.java
    │   │   └── DemoController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/httpclients/
            └── ClientsSmokeTest.java
```

### 9.2. Complete Maven POM

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>http-clients-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
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
```

**Why both starters?** `starter-web` runs **Servlet MVC/Tomcat** and brings in RestClient/RestTemplate and JSON converters. `starter-webflux` provides `WebClient`, `Mono`, and the HTTP client connector. When both are present, the demo app remains MVC per Boot 3.5 auto-configuration rules. In an MVC app that only uses RestClient, omit the WebFlux dependency altogether; in a pure WebFlux app, omit `starter-web`.

### 9.3. Main Class

File `src/main/java/com/example/httpclients/HttpClientsDemoApplication.java`:

```java
package com.example.httpclients;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpClientsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpClientsDemoApplication.class, args);
    }
}
```

`@SpringBootApplication` scans classes in package `com.example.httpclients` and subpackages. Do not place controllers/configs outside the scan scope unless configured.

### 9.4. DTO `Product.java`

```java
package com.example.httpclients;

public record Product(long id, String name, long price) {
}
```

`record` is a built-in Java 17 language feature, deserialized from JSON by Jackson when the web starter provides the appropriate module. The price here is a demo integer, **not a production monetary design**; real monetary values need currency, minor units, rounding, and validation.

### 9.5. Simulated Upstream `UpstreamController.java`

```java
package com.example.httpclients;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/upstream/products")
public class UpstreamController {

    @GetMapping("/{id}")
    public Product get(@PathVariable long id) {
        if (id <= 0) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Product not found");
        }
        return new Product(id, "Product-" + id, id * 1000L);
    }
}
```

Calling `GET /upstream/products/7` returns a JSON body with the content:

```json
{"id":7,"name":"Product-7","price":7000}
```

JSON property order is not part of the API contract, but **the values** must match. For `id=0`, upstream returns HTTP **404**. For valid IDs, the controller builds the DTO directly without calling a DB or external service.

### 9.6. Client Bean Config `OutboundClientsConfig.java`

```java
package com.example.httpclients;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OutboundClientsConfig {

    @Bean
    RestClient productRestClient(
            RestClient.Builder builder,
            @Value("${demo.upstream.base-url}") String baseUrl) {
        return builder
                .baseUrl(baseUrl)
                .build();
    }

    @Bean
    RestTemplate productRestTemplate(
            RestTemplateBuilder builder,
            @Value("${demo.upstream.base-url}") String baseUrl) {
        return builder
                .rootUri(baseUrl)
                .connectTimeout(Duration.ofSeconds(2))
                .readTimeout(Duration.ofSeconds(3))
                .build();
    }

    @Bean
    WebClient productWebClient(
            WebClient.Builder builder,
            @Value("${demo.upstream.base-url}") String baseUrl) {
        return builder
                .baseUrl(baseUrl)
                .build();
    }
}
```

**Key points:**

- `RestClient.Builder`, `RestTemplateBuilder`, and `WebClient.Builder` are all auto-configured by Spring Boot; the code **injects the builder** and registers each client as a bean rather than rebuilding inside controllers.
- `baseUrl` applies to relative URIs on RestClient/WebClient.
- `RestTemplateBuilder.rootUri(baseUrl)` applies to String URIs starting with `/`, as used in `getForObject` in the next example.
- `RestTemplateBuilder.connectTimeout`/`readTimeout` simply illustrate per-client configuration; timeouts for RestClient/WebClient are set in `application.properties` per Boot 3.5.
- `Duration` is a standard Java type. `@Value` reads from environment config. When changing `baseUrl` to a real service, test HTTPS, DNS, auth, and pooling.

### 9.7. Service Using All Three Clients `OutboundProductService.java`

```java
package com.example.httpclients;

import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class OutboundProductService {

    private final RestClient restClient;
    private final RestTemplate restTemplate;
    private final WebClient webClient;

    public OutboundProductService(
            RestClient productRestClient,
            RestTemplate productRestTemplate,
            WebClient productWebClient) {
        this.restClient = productRestClient;
        this.restTemplate = productRestTemplate;
        this.webClient = productWebClient;
    }

    public Product viaRestClient(long id) {
        return restClient.get()
                .uri("/upstream/products/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(Product.class);
    }

    public Product viaRestTemplate(long id) {
        return restTemplate.getForObject(
                "/upstream/products/{id}",
                Product.class,
                id);
    }

    public Mono<Product> viaWebClient(long id) {
        return webClient.get()
                .uri("/upstream/products/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(Product.class);
    }

    public Mono<List<Product>> viaWebClientParallel() {
        Mono<Product> first = viaWebClient(1);
        Mono<Product> second = viaWebClient(2);

        return Mono.zip(first, second)
                .map(pair -> List.of(pair.getT1(), pair.getT2()));
    }
}
```

Distinguish the **return types**:

- `viaRestClient` and `viaRestTemplate` return `Product` directly, because they wait for the HTTP call to finish.
- `viaWebClient` returns `Mono<Product>`, **without calling `block()`**.
- `viaWebClientParallel` returns a `Mono<List<Product>>` composed from **two independent requests**. They are only sent upon subscription.
- There is no automatic retry logic in these methods; a 404 turns into a client error/exception.

With multiple beans of the same RestClient/WebClient type in a real project, use `@Qualifier` explicitly instead of relying on parameter names. The demo has only one bean per type, so Spring injects unambiguously.

### 9.8. Controller `DemoController.java`

```java
package com.example.httpclients;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    private final OutboundProductService products;

    public DemoController(OutboundProductService products) {
        this.products = products;
    }

    @GetMapping("/demo/rest-client/{id}")
    public Product restClient(@PathVariable long id) {
        return products.viaRestClient(id);
    }

    @GetMapping("/demo/rest-template/{id}")
    public Product restTemplate(@PathVariable long id) {
        return products.viaRestTemplate(id);
    }

    @GetMapping("/demo/web-client/{id}")
    public Mono<Product> webClient(@PathVariable long id) {
        return products.viaWebClient(id);
    }

    @GetMapping("/demo/web-client-parallel")
    public Mono<List<Product>> parallel() {
        return products.viaWebClientParallel();
    }
}
```

Spring MVC supports reactive return types like `Mono` via async integration when reactive libraries are present in the app. **RestClient and RestTemplate still run synchronously on the Servlet request thread**; only the WebClient endpoints return `Mono` for MVC to subscribe and complete the response asynchronously. This difference is easy to observe when combining both starters.

### 9.9. `application.properties`

```properties
server.port=8080
spring.application.name=http-clients-demo

# Local run; replace with the actual service host in deployment.
demo.upstream.base-url=http://localhost:8080

# Spring Boot 3.5: timeouts for synchronous HTTP clients.
spring.http.client.connect-timeout=2s
spring.http.client.read-timeout=3s

# Spring Boot 3.5: timeouts for WebClient connector.
spring.http.reactiveclient.connect-timeout=2s
spring.http.reactiveclient.read-timeout=3s
```

This is a **standalone configuration file**. In production deployments, supply the base URL via environment variables or a config server; never place usernames, passwords, or tokens in source files. If you change `server.port`, remember to update `demo.upstream.base-url` as well for the local self-call demo. Inside containers, `localhost` does not automatically point to another service.

### 9.10. Build, Run, and Verify with curl

Prerequisites: **JDK 17+** and Maven installed, port 8080 available.

```bash
mvn clean package
java -jar target/http-clients-demo-1.0.0.jar
```

From a second terminal:

```bash
curl -s http://localhost:8080/upstream/products/7
curl -s http://localhost:8080/demo/rest-client/7
curl -s http://localhost:8080/demo/rest-template/7
curl -s http://localhost:8080/demo/web-client/7
```

All four successful calls return equivalent content:

```json
{"id":7,"name":"Product-7","price":7000}
```

JSON key ordering may vary by serializer; what matters is `id=7`, `name="Product-7"`, and `price=7000`.

Test parallel WebClient composition:

```bash
curl -s http://localhost:8080/demo/web-client-parallel
```

Expected JSON response **data**:

```json
[
  {"id":1,"name":"Product-1","price":1000},
  {"id":2,"name":"Product-2","price":2000}
]
```

There is no artificial delay in the example source, so **there is no guarantee** that the parallel endpoint is noticeably faster locally. What is tested is that both remote Monos are combined and result ordering follows `zip(first,second)`.

Try a non-existent upstream item:

```bash
curl -i http://localhost:8080/upstream/products/0
curl -i http://localhost:8080/demo/rest-client/0
curl -i http://localhost:8080/demo/rest-template/0
curl -i http://localhost:8080/demo/web-client/0
```

Upstream returns **404**. The clients encounter 404 and by default raise an exception/reactive error; **the external status of `/demo/...` may become 500** if you have not added a `@ControllerAdvice` mapping domain exceptions. This is intentional to illustrate that **an upstream client error does not automatically become the same status on the frontend API**. In real applications, design error mapping (Section 11).

In PowerShell, use `curl.exe` instead of the `curl` alias if needed. With a port other than 8080, change both the server port and upstream base URL in config, then update the test URLs.

## 10. Integration Testing Without External Services

To test all three clients against a real HTTP server on a **random port**, add `src/test/java/com/example/httpclients/ClientsSmokeTest.java`:

```java
package com.example.httpclients;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ClientsSmokeTest {

    @LocalServerPort
    int port;

    @Test
    void threeClientsReadSameData() {
        String baseUrl = "http://localhost:" + port;

        Product a = RestClient.create(baseUrl).get()
                .uri("/upstream/products/{id}", 3)
                .retrieve()
                .body(Product.class);

        Product b = new RestTemplate().getForObject(
                baseUrl + "/upstream/products/{id}",
                Product.class,
                3);

        Product c = WebClient.create(baseUrl).get()
                .uri("/upstream/products/{id}", 3)
                .retrieve()
                .bodyToMono(Product.class)
                .block(Duration.ofSeconds(5));

        assertNotNull(a);
        assertEquals(new Product(3, "Product-3", 3000), a);
        assertEquals(a, b);
        assertEquals(a, c);
    }
}
```

This test **makes real HTTP calls on an actual port** rather than mocking the entire network. `@LocalServerPort` gives the port chosen by Spring Boot test, avoiding port 8080 conflicts. It builds clients directly with the random-port base URL to verify **client API functionality and serialization**; the demo's singleton beans remain configured from `application.properties`, so this test **does not** isolate every custom timeout/bean setting in `OutboundClientsConfig`.

Inside a **normal JUnit test thread**, `.block(Duration)` can be used as above to obtain and assert the result; **do not** copy this blocking call into a Spring WebFlux event loop. For real WebFlux service tests, use `StepVerifier` or `WebTestClient` appropriately.

Run:

```bash
mvn test
```

On success, Maven reports all tests passing (counts/summary vary by plugin). You do not need to override `server.port` in the environment to test with a random port.

### Common Testing Strategies

- **Unit**: mock the wrapper/service interface without real HTTP requests.
- **MockRestServiceServer**: supports testing `RestTemplate` and `RestClient.Builder` with expected requests/responses without opening sockets.
- **WebClient with mock ExchangeFunction/MockWebServer/WireMock**: simulates HTTP error responses, timeouts, headers, malformed JSON, and retries without calling third-party services.
- **Integration**: `@SpringBootTest(RANDOM_PORT)`, Testcontainers/WireMock, or a real stub service on a random port.
- **Contract**: verifies request schemas, headers, auth, and error mapping against real upstream API versions.
- **Performance**: measures connection pools, p95 latency, concurrency, cancellation, and retry storms.

Never rely on an uncontrolled public API for stable CI tests. For HTTP network failure cases, offline tests catch regressions faster and more reliably.

## 11. Status Codes, Exceptions, and Error Mapping

### 11.1. Distinguishing "Server Returned Error" from "Could Not Connect"

| Case | HTTP response present? | RestClient / RestTemplate | WebClient |
| --- | --- | --- | --- |
| Upstream 200 + valid JSON | Yes | DTO/value | `Mono<DTO>` emits value |
| Upstream 204 No Content | Yes, no body | Possibly `null`/bodyless entity | `Mono.empty()` for body |
| Upstream 404 | Yes | `RestClientResponseException` and subclasses per API | `WebClientResponseException.NotFound` |
| Upstream 503 | Yes | 5xx exception with status/body | `WebClientResponseException.ServiceUnavailable` |
| DNS/connect refused | No valid HTTP response | `ResourceAccessException` or wrapped I/O exception | `WebClientRequestException` |
| Read timeout | Complete HTTP response may not arrive | I/O/timeout exception | Timeout/network error in pipeline |
| JSON incompatible with DTO | Response received, decode failed | HTTP message conversion error | Codec/decoding error |

Exact exception types depend on versions and underlying transports. Do not lump everything into "upstream 500" and never expose stack traces or raw sensitive responses to the browser.

### 11.2. Returning Controlled Domain Errors

At the application layer, distinguish:

- **Upstream 404**: resource may genuinely not exist; map to domain `NotFound` or an appropriate response.
- **Upstream 401/403**: service-to-service auth is wrong/expired; do not turn this into "end user lacks permission" unless equivalent.
- **Upstream 429**: rate limited; respect `Retry-After`, backoff, and retry limits.
- **Upstream 500/502/503/504**: transient or server-side failure; may warrant fallback/circuit breaker.
- **Timeout/connect refused**: downstream unavailable; usually mapped to `503`/`504` per gateway contract, with correlation logging.
- **Invalid JSON**: upstream contract/schema mismatch; emit metrics and alerts rather than pretending it is a 404.

In Spring MVC, `@RestControllerAdvice` + `@ExceptionHandler` can return a standardized error response. In Spring Boot 3.5, `ProblemDetail` represents errors per RFC 9457, though you must explicitly design the mapping; Boot does not auto-map every WebClient/RestClient exception into the right business `ProblemDetail`.

### 11.3. Custom Mapping Example in RestClient

```java
try {
    return restClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .body(Product.class);
}
catch (HttpClientErrorException.NotFound ex) {
    throw new ProductMissingException(id);
}
catch (RestClientResponseException ex) {
    throw new UpstreamUnavailableException(
            ex.getStatusCode().value(), ex);
}
```

This is an **illustrative snippet**; domain exceptions are application-defined. RestClient versions/underlying factories may use other subtypes; test real 404/429/5xx paths. Avoid catching overly broad exceptions that swallow programming or request-mapping bugs.

### 11.4. WebClient and `onErrorResume`

```java
Mono<Product> product = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .onErrorResume(WebClientResponseException.NotFound.class,
                ex -> Mono.empty());
```

This snippet intentionally turns 404 into **no product** (`Mono.empty()`). That is only valid if business logic treats 404 as optional; for endpoints requiring a Product, translate to a domain error. Never attach `onErrorResume(ex -> Mono.empty())` to **all errors**, as that hides downtime and connectivity failures.

### 11.5. Which Errors Can Be Retried?

Retries are not safe by default:

- Idempotent GETs may retry on transient connection errors/503/429 (per policy).
- A POST creating a transaction can create **duplicate records** if upstream finished processing before the connection dropped.
- Retrying state-changing operations requires an idempotency key, clear transaction semantics, and upstream agreement.
- Retries must have **attempt limits + backoff + jitter**, respecting `Retry-After` when present.
- Do not blindly retry 401, 403, 400, 404, or schema errors.
- Maintain an overall deadline, circuit breaker, bulkhead, and metrics. Excessive retries can overload an already struggling upstream.

Reactor provides `retryWhen(Retry.backoff(2, Duration.ofMillis(200)))`, but **do not copy it directly** without filtering exceptions/statuses and verifying request idempotency. `Retry` **resubscribes** to the pipeline: it does not just "reprocess the result"; it can re-send the HTTP request.

## 12. Timeouts, Connection Pooling, and Concurrency

### 12.1. Timeouts Are a Set of Distinct Limits

| Type | Purpose | Guidance |
| --- | --- | --- |
| Connection timeout | Avoid waiting indefinitely for TCP/TLS connect | Usually short, based on network |
| Response/read timeout | Avoid waiting indefinitely for response/reads | Per upstream SLA |
| Total operation deadline | Bound the whole call including retries/backoff | Not just socket read timeout |
| Pool acquire timeout | Avoid waiting indefinitely for an idle connection | Crucial when connection pool saturates |
| Idle/keep-alive timeout | Release idle connections appropriately | Align with proxy/upstream idle timeouts |
| Request-level timeout (Reactor) | Terminate pipeline after a duration | E.g., `.timeout(Duration)` |
| Circuit breaker timeout | Prevent cascading downstream hangs | Coordinate with all other timeouts |

**Budget example:** upstream target is 300 ms, API gateway deadline is 2 s. If the client sets a 30 s read timeout and retries 5 times, the gateway will time out long before business code notices. Timeouts and retry budgets must align across the entire service chain.

### 12.2. WebClient `timeout` and Cancellation

```java
Mono<Product> result = webClient.get()
        .uri("/products/{id}", 42)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(2));
```

This is a snippet. Reactor's `timeout` signals an error if the publisher does not emit in time; timeout can trigger cancellation of the subscription and HTTP request when supported by the connector. **There is no guarantee** that upstream processing is aborted: the remote server may still complete the operation.

### 12.3. Connection Pools Are Bounded

Whether using RestClient or WebClient, the **HTTP transport pool** is distinct from the thread pool. With 500 concurrent requests, you do not always have 500 TCP connections: the client can reuse connections, queue requests, or use HTTP/2 multiplexing. Monitor:

- active/idle/pending connections;
- pool max connections, pool acquire timeout;
- HTTP/1.1 keep-alive vs HTTP/2 multiplexing;
- DNS/TLS handshakes, idle evictions;
- timeouts at reverse proxies and load balancers;
- memory buffering, max response size, and streaming pressure.

Do not create a new `HttpClient`/`WebClient`/`RestClient` with its own pool per incoming request. Doing so increases sockets, TLS handshakes, GC, and harms observability. Build reusable client beans and configure pooling deliberately.

### 12.4. Bounding Request Queues and Upstream Concurrency

Non-blocking WebClient can still overwhelm an upstream if `flatMap` spawns too many concurrent requests. You can cap concurrency:

```java
Flux<Product> products = Flux.range(1, 100)
        .flatMap(this::fetchProduct, 8);
```

This snippet assumes a method `Mono<Product> fetchProduct(int id)`; `8` is the maximum concurrency coordinated by `flatMap`, not a system-wide socket limit guarantee. Results may arrive out of input order; use `flatMapSequential` if ordering is needed at appropriate cost.

In MVC with RestClient, you can use bounded executors/bulkheads/virtual threads matching your Java runtime, though adding threads alone never increases DB or upstream capacity.

### 12.5. Reactive Code Containing Blocking I/O

When a blocking library cannot be avoided in WebFlux:

```java
Mono<Product> adapted = Mono.fromCallable(
                () -> legacyRestClient.getProduct(42))
        .subscribeOn(Schedulers.boundedElastic());
```

This is a **reluctant adaptation snippet**, not recommended as a replacement for WebClient. `legacyRestClient` is an existing synchronous abstraction; Reactor's `Schedulers` must be imported. `boundedElastic` is designed for bounded blocking work with queueing; it does not "make I/O non-blocking" or scale infinitely. Prefer genuinely reactive clients first when end-to-end reactivity is needed.

## 13. JSON, Generics, Encoding, and Large Response Bodies

### 13.1. Reading Typed Lists

For `List<Product>`, do not pass `List.class` expecting generic types to be preserved. Use `ParameterizedTypeReference`:

```java
List<Product> products = restClient.get()
        .uri("/products")
        .retrieve()
        .body(new ParameterizedTypeReference<List<Product>>() {});
```

```java
Mono<List<Product>> products = webClient.get()
        .uri("/products")
        .retrieve()
        .bodyToMono(
                new ParameterizedTypeReference<List<Product>>() {});
```

Both examples are **snippets only**; `/products` does not exist in the Section 9 demo. With RestTemplate, `exchange` has an overload accepting `ParameterizedTypeReference<List<Product>>`.

### 13.2. Setting `Content-Type` and `Accept` Properly

`Content-Type` describes the **format of the outbound request body**; `Accept` declares the **expected response type**. JSON POST example:

```java
client.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(order)
        .retrieve()
        .toBodilessEntity();
```

This tells the server the request body is JSON and that no response body needs to be decoded. Do not use `toBodilessEntity()` if business code needs an ID or order status from the response body.

### 13.3. Large Responses and Streaming

- RestClient/RestTemplate can stream via appropriate APIs, but you must manage the body stream and close resources properly.
- WebClient `bodyToFlux` suits streaming, though default codecs cap in-memory buffering for certain decode types.
- If an endpoint returns a 100 MB payload, avoid `bodyToMono(byte[].class)` if memory budget does not allow it.
- For downloads, use streaming/body-extraction APIs and ensure resources are closed.
- With WebClient, never call `collectList()` on an infinite Flux or unbounded source.

When hitting `DataBufferLimitException`, do not instinctively raise `maxInMemorySize` to gigabytes. Inspect the response schema and switch to streaming/size caps. For sensitive data, protect logs and avoid printing full request/response bodies at debug level.

## 14. TLS, Proxies, Credentials, and Outbound HTTP Security

### 14.1. SSL/TLS

An HTTP client calling `https://...` must verify the **certificate chain, hostname, and TLS policy**. When upstreams use an internal CA or mTLS, use a managed truststore/keystore; Spring Boot supports SSL bundles and HTTP client customizations. Never use "trust all certificates", disable hostname verification, or rely on `curl -k` behavior in production.

`RestClientSsl` in Spring Boot 3.5 helps apply an SSL bundle to `RestClient.Builder` in dedicated configurations. WebClient with Reactor Netty uses its connector/TLS setup; do not copy Servlet server SSL config into an outbound client expecting it to automatically trust new CAs.

### 14.2. Service-to-Service Auth

Depending on architecture, use `Authorization: Bearer <token>`, mTLS, or OAuth2 client credentials. Tokens must be:

- Fetched/refreshed on schedule, never hardcoded in POM/properties.
- Kept out of URLs/query strings, exception messages, and HTTP client debug logs.
- Distinguished between **user** tokens and **service account** tokens; do not blindly forward incoming request tokens to every upstream.
- Propagated with trace/request IDs and security identity according to policy.
- On 401/403, do not retry infinitely and do not translate upstream failures into misleading end-user permission errors.

### 14.3. SSRF: Never Let Users Choose Arbitrary URLs

**Server-Side Request Forgery** occurs when a backend is tricked into sending HTTP requests to unauthorized destinations such as cloud metadata services, loopback, admin networks, or internal files. You must:

- Prefer **statically configured** base URLs per service.
- Validate allowed schemes/hostnames/paths; do not accept arbitrary absolute URLs from clients.
- Restrict redirects and validate DNS/IP ranges as required by your threat model.
- Prevent requests from jumping from public hosts to private/internal IPs via redirects or DNS rebinding.
- Apply egress firewall/network policies and HTTP client IP filtering where appropriate.
- Never allow users to submit `http://169.254.169.254/...` or `http://127.0.0.1:...` as an "API URL" fetched with server privileges.

In the local demo, calling `localhost:8080` is intentional to remain self-contained; in production, user input **must never** override `demo.upstream.base-url`.

### 14.4. CORS Does Not Apply to Java Server-to-Server Clients

Spring CORS policy primarily governs JavaScript running in browsers. A Spring RestClient/WebClient calling another service from the backend **is not blocked by browser CORS policy**. If an outbound backend HTTP call fails, inspect DNS/TLS/proxy/firewall, auth, path, and status—do not "fix CORS" on the upstream unless there is a separate browser requirement.

### 14.5. Environment Proxies and DNS

- Corporate HTTP proxies may require authentication, allowlists, and per-client configuration.
- Apps in containers/Kubernetes must call proper service DNS/ports; `localhost` inside a pod usually refers only to that pod/container, not another service.
- Reverse proxies/load balancers between services maintain their own connect/read/idle timeouts.
- DNS caching and TLS connection reuse affect latency under heavy load.
- With an mTLS service mesh, know where TLS terminates, which certificate identities apply, and mesh retry policies to avoid "retries on top of retries".

## 15. Observability, Tracing, and Production Debugging

### 15.1. Metrics and Tracing

Use Boot's auto-configured builders to keep customizers and observability integrations when Micrometer/Actuator/Tracing are enabled. Track:

- outbound request counts by client/service, method, and status class;
- p50/p95/p99 latency, timeouts, and error rates;
- connection pool active/pending/idle counts and pending acquire latency;
- DNS/TLS handshake errors, 429/503 rates, retry counts, and circuit breaker state;
- correlation/trace IDs across hops.

Avoid putting raw URLs containing customer IDs or tokens into metric tags (cardinality explosion and data leakage). Use URL templates/route names and bounded tags.

### 15.2. Debugging a Failing Request

1. Identify **which client type** and underlying request factory/connector are used.
2. Record method, host, path template, status, latency, and correlation ID; mask credentials.
3. Run `curl -i` against the upstream **from the same network environment** to verify DNS/TLS/routing.
4. Separate HTTP error responses (4xx/5xx) from connection/timeout failures.
5. Check timeouts across client, gateway, and upstream; check whether retries are multiplying requests.
6. For WebClient, verify there is an actual subscription; do not mistake constructing a `Mono` for sending a request.
7. Inspect connection pools, event loops, and blocking operations.
8. For JSON decode errors, capture schema/status/body samples **with sensitive data redacted**.

### 15.3. Never Log Full Bodies Unconditionally

Logging entire payloads of payments, auth, or user profiles can violate security policies. When debugging is required, log approved fields using sampling, masking, correlation IDs, and retention policies. Partner error responses can contain PII, secrets, or untrusted content.

## 16. Migration Paths: RestTemplate to RestClient, and MVC to Reactive

### 16.1. Migrating RestTemplate → RestClient

A risk-controlled path:

1. Inventory all uses of `RestTemplate` and `RestTemplateBuilder`; catalog custom interceptors, converters, error handlers, and request factories.
2. Pick a simple GET call and confirm request method/URL/headers, timeout, auth, and response semantics.
3. Write integration/mock-server tests comparing responses; do not stop at "code compiles".
4. Use `RestClient.create(existingTemplate)` where helpful or inject `RestClient.Builder` to leverage Boot configuration.
5. Incrementally convert to `get().uri().retrieve().body()`, mapping errors carefully.
6. Monitor performance, redirects, pooling, content negotiation, and retry behavior.
7. Do not swap transport/mTLS/proxy at the same time as the API refactor unless necessary.
8. Once all calls are migrated, remove unused legacy beans/dependencies/configs.

### 16.2. Spring MVC → WebFlux Is More Than Changing the Client

Changing a REST controller return type from `Product` to `Mono<Product>` **is not enough** to become a reactive architecture:

- Server/routing/web stack must run on WebFlux runtime.
- Repositories and downstream operations should also be non-blocking; use R2DBC/reactive drivers where appropriate.
- Blocking libraries must be replaced or isolated on bounded schedulers.
- Error handling, transactions, context propagation, security, and testing must be updated.
- The team needs to understand reactive stream semantics: laziness, subscription, backpressure, cancellation.

If most of the system uses JPA/JDBC with moderate concurrency, Spring MVC + RestClient can still be the right choice. Do not treat "reactive" as a goal independent of performance needs and team capability.

### 16.3. HTTP Service Clients (`@HttpExchange`)

When many calls to a downstream need typed interfaces, Spring Framework supports declarative HTTP interfaces backed by **RestClient** (blocking) or **WebClient** (reactive). Interface example:

```java
@HttpExchange("/products")
interface CatalogApi {
    @GetExchange("/{id}")
    Product get(@PathVariable long id);
}
```

This is an **illustrative snippet**, not a standalone program; it needs Spring Web annotation imports, `HttpServiceProxyFactory`, and `RestClientAdapter` configuration. With a WebClient adapter, use reactive return types (such as `Mono<Product>`). HTTP interfaces separate the contract from call execution, but **do not alter the blocking semantics** of the underlying adapter.

## 17. Very Common Practical Pitfalls

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: RestTemplate` | Boot auto-configures the builder, not a ready-made RestTemplate bean | Define `@Bean RestTemplate` using `RestTemplateBuilder` |
| `NoSuchBeanDefinitionException: WebClient.Builder` | Missing `spring-webflux`/starter or inactive auto-config | Check dependencies and application context |
| Cannot inject `RestClient.Builder` | Spring Web/Boot version too old or auto-config overridden | Verify Boot 3.5 and starter/classpath |
| `WebClient` returns Mono but HTTP request never runs | Publisher was never subscribed/returned | Return Mono from controller or compose via subscription |
| `block() is not supported` | Blocking operation called on a Reactor non-blocking thread | Return Mono/Flux, remove `block()` |
| Low WebFlux throughput despite WebClient | Blocking JDBC/RestTemplate inside pipeline | Use non-blocking drivers or boundedElastic with limits |
| RestClient POST sends no request | Called `retrieve()` without terminal `body/toEntity` | Call the appropriate terminal operation |
| Upstream 404 turns into frontend 500 | HTTP client exception not mapped to domain error | Use `onStatus`/`@ControllerAdvice` |
| Requests hang too long | Missing timeouts or wrong client config | Set connect/read/total deadlines and inspect connector |
| Duplicate POST after retry | Non-idempotent retry | Idempotency key and conditional retry policy |
| Connection pool exhausted | Unbounded concurrency, leaked body/response, creating clients per call | Reuse singleton clients, consume/release bodies, add bulkhead |
| 200 but DTO is null/empty | HTTP 204/empty body, schema mismatch | Verify status/content-type, design Optional/Mono.empty |
| `DataBufferLimitException` | Large response exceeding codec buffer limit | Stream, bound payloads, tune codec sensibly |
| Mixed Spring starters make server MVC | Boot normally prefers MVC when both MVC+WebFlux exist | Set the intended web application type |
| Random-port test still calls 8080 | Demo app base URL hardcoded to 8080 | Inject dynamic base URL in tests or test clients directly |
| 401 when calling service | Missing/expired token or wrong audience | Check service-to-service auth, do not open CORS |
| SSLHandshakeException | Trust/cert/hostname/TLS mismatch | Use trusted CA/SSL bundle, never trust-all |
| Timeouts only in Kubernetes | DNS/service port/network policy/mesh retries | Test in same network, inspect mesh/gateway |
| Creating RestClient per request | Loses pooling/customizations, adds overhead | Build one bean per upstream |
| Metrics have millions of URL tags | Raw URLs with IDs used in tags | Use route templates to keep cardinality low |

## 18. Self-Check Questions

1. **When should you pick RestClient?** For imperative apps (MVC/JPA/batch) needing synchronous HTTP calls with a clear fluent API.
2. **Does RestTemplate become non-blocking if the server uses WebFlux?** No. The RestTemplate API remains synchronous.
3. **Can WebClient run inside MVC?** Yes. Adding WebFlux client APIs does not necessarily switch the server to WebFlux.
4. **Does `bodyToMono(Product.class)` immediately fire an HTTP call?** Normally no; Mono is lazy and requires a subscription.
5. **Is RestClient's `retrieve().body(Product.class)` blocking?** Yes, it is a synchronous operation waiting for the response.
6. **Does Spring Boot automatically register an injectable RestTemplate bean?** Normally no; Boot auto-configures `RestTemplateBuilder` so you can create beans.
7. **Why avoid WebClient `.block()` in a WebFlux controller?** It blocks the event loop, may throw an error, and hurts concurrency.
8. **Why can a WebClient 404 cause an MVC endpoint to return 500?** Outbound exceptions do not auto-map to domain responses; an explicit error handler is needed.
9. **Does `flatMap(...,8)` mean at most 8 sockets?** No. That bounds publisher concurrency in the operator; pool/network limits live at a lower layer.
10. **Should you retry a payment POST on timeout?** Only when idempotency and semantics are well-defined; otherwise it risks duplicate transactions.
11. **Why is a singleton RestClient bean usually better than creating one in a controller?** It preserves configuration, pooling, TLS, tracing, and cuts overhead.
12. **Why doesn't WebClient make every blocking library in the app non-blocking?** It only makes outbound HTTP non-blocking; DB/CPU/other SDKs can still block.
13. **What is the biggest difference between RestClient and RestTemplate?** Both are synchronous, differing in API style and extensibility; RestClient offers a modern fluent API.
14. **Distinguish connect timeout from total pipeline timeout?** Connect timeout bounds establishing the connection; total deadline covers connect, response, and retries/backoff.
15. **Does `localhost` inside a container point to another service?** No, it usually points to that container/pod's own network namespace.
16. **Is a Java backend calling a cross-origin API blocked by browser CORS?** No; browser CORS policy does not apply to server-to-server HTTP clients.
17. **Does adding both starter-web and starter-webflux force the server to use Netty?** No; Boot 3.5 normally picks MVC/Servlet when both are present.
18. **Does switching RestTemplate to RestClient automatically fix timeouts and redirects?** No. You must verify the underlying HTTP client transport.
19. **Are an HTTP error status and a connection error the same?** No. One received an HTTP response; the other may not have connected or received a response.
20. **What is the benefit of `Mono.zip` on two requests?** It combines independent publishers to await both results, typically executing concurrently upon subscription.

## 19. Production Readiness Checklist for HTTP Clients

- [ ] Determine whether the service is **imperative MVC/JPA** or **reactive WebFlux**.
- [ ] Prefer RestClient for new synchronous code; keep RestTemplate controlled in legacy code; use WebClient for non-blocking/reactive/streaming.
- [ ] Create reusable client beans per upstream by injecting Boot's auto-configured builders.
- [ ] Load base URLs, ports, proxies, and credentials from config/secrets—never hardcode production values.
- [ ] Configure **connect/read/total timeouts** aligned with gateway and upstream SLAs.
- [ ] Control connection pools, max concurrency, backpressure, and bulkheads.
- [ ] Distinguish HTTP 4xx/5xx from network/timeout/decode failures; map clearly to domain errors.
- [ ] Retry with bounded attempts/backoff/jitter; only retry idempotent requests or those with proper idempotency keys.
- [ ] Return `Mono/Flux` in WebFlux; avoid `block()` or ad-hoc `subscribe()` in controllers.
- [ ] With MVC + WebClient, measure real benefits; do not claim the whole app is reactive.
- [ ] Verify TLS/CA/hostnames; use secret managers/SSL bundles for mTLS when needed.
- [ ] Restrict SSRF, redirects, and egress; never let user input dictate arbitrary absolute URLs.
- [ ] Write tests for success, 404, 429, 503, timeouts, connection refused, and invalid JSON.
- [ ] Provide metrics/traces, request IDs, and log redaction; never log access tokens or PII.
- [ ] Measure p95/p99 latency, connection pool utilization, and retry rates under realistic load.
- [ ] When upgrading major Boot/Spring Framework versions, check RestTemplate status and version-specific HTTP client property names.

## 20. Official References

- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): RestClient, RestTemplate, WebClient, builders, client detection, timeouts, and SSL bundles.
- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): RestClient/RestTemplate, response handling, and HTTP Interfaces.
- [Spring Framework 6.2 — WebClient](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html): reactive HTTP client, lifecycle, and configuration.
- [Spring Framework — WebClient retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): error handling and body extraction.
- [Spring Framework — WebClient exchange](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): `exchangeToMono` and `exchangeToFlux`.
- [Spring Framework — WebClient synchronous use](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html): why `block()` can be used in synchronous contexts but is unsuitable for the event loop.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, random ports, and integration tests.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): `Mono`, `Flux`, laziness, threading, and error handling.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): service-to-service OAuth2 and token lifecycle.

**Conclusion:** Choose your HTTP client based on **the application's execution model**, not merely the library name. **RestClient** is the clear option for new synchronous code; **RestTemplate** helps maintain legacy synchronous systems and migrate gradually; **WebClient** is built for reactive/non-blocking, streaming, and composing multiple HTTP calls. Regardless of the client chosen, production reliability still depends on **timeouts, pooling, concurrency limits, error mapping, retry idempotency, TLS, and observability**.