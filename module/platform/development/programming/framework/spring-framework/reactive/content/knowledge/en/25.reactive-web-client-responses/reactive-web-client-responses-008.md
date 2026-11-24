# Coordinating multiple independent calls and limiting concurrency with Spring WebClient

## 1. The fan-out problem when calling multiple APIs

An aggregator endpoint often needs data from multiple services:

- Product details from the Catalog API.
- Stock quantity from the Inventory API.
- Current price from the Pricing API.
- Reviews or recommendations from another service.

If the calls are independent, waiting for each request to finish before sending the next increases total latency. With three requests taking 300 ms, 400 ms, and 250 ms respectively, sequential execution can take around 950 ms plus overhead. If sent concurrently and awaited together, total time is close to the slowest request, around 400 ms plus overhead.

However, firing hundreds of requests at once can overload downstream services, exhaust connection pools, grow queues, and trigger retry storms. Therefore, two separate decisions are required:

1. **Result coordination:** which calls are independent, and should we wait for all or just one result?
2. **Load limiting:** how many calls at most are allowed to run concurrently within a processing flow?

Spring WebClient combined with Reactor provides operators such as Mono.zip, Flux.flatMap, flatMapSequential, and concatMap to solve both problems.

## 2. WebClient and Publishers are lazy

WebClient returns a Mono or Flux. When creating the publisher, the request is usually not sent immediately. The publisher describes the work to perform; the request begins upon subscription.

~~~java
Mono<Product> product = webClient.get()
        .uri("/products/{id}", "p-1")
        .retrieve()
        .bodyToMono(Product.class);
~~~

The snippet above creates a Mono describing the request. Only when a subscriber subscribes to the Mono does WebClient execute the HTTP exchange.

This allows composing multiple requests into a single pipeline before subscribing:

~~~java
Mono<Product> product = fetchProduct(id);
Mono<Inventory> inventory = fetchInventory(id);
Mono<Price> price = fetchPrice(id);

return Mono.zip(product, inventory, price, Dashboard::new);
~~~

Mono.zip subscribes to the sources when the pipeline is subscribed to. Independent HTTP requests can await I/O simultaneously. No dedicated thread is needed per request; Reactor Netty handles I/O asynchronously.

Do not call subscribe() inside a service to launch each request manually. Nor call block() after each call. Return Mono/Flux to the controller or caller so the entire lifecycle, error handling, and cancellation are managed within one pipeline.

## 3. Mono.zip: coordinating independent calls returning one result

### 3.1. When to use zip?

Use Mono.zip when values from multiple independent sources are needed before building an aggregated result.

~~~java
Mono<Dashboard> dashboard(String id) {
    Mono<Product> product = fetchProduct(id);
    Mono<Inventory> inventory = fetchInventory(id);
    Mono<Price> price = fetchPrice(id);

    return Mono.zip(product, inventory, price, Dashboard::new);
}
~~~

Dashboard is created only when all three Monos emit a value. Dashboard::new receives the results in the exact order the sources were passed to zip.

If requests take 300 ms, 400 ms, and 250 ms respectively, total wait time is close to the slowest request rather than the sum of all three. Actual numbers still depend on network, connection pool, DNS, servers, and decoding overhead.

### 3.2. zip does not turn dependent calls into independent ones

Sources can only run concurrently when they do not depend on each other's results.

Valid example: fetching product, inventory, and price by the same product ID; all three APIs can be called immediately.

Dependent example: fetching the order first to learn customerId, and only then fetching the customer. Use flatMap:

~~~java
Mono<OrderSummary> summary(String orderId) {
    return fetchOrder(orderId)
            .flatMap(order ->
                    fetchCustomer(order.customerId())
                            .map(customer -> new OrderSummary(order, customer))
            );
}
~~~

You cannot call fetchCustomer before knowing customerId. Using zip in this case yields no useful parallelism.

### 3.3. zip and empty Monos

A Mono can complete without emitting a value. Mono.zip requires every source to emit a value to invoke the combinator function. If one source completes empty, zip completes empty and cancels the remaining sources.

If a source represents optional data, convert empty into a sentinel value before zipping:

~~~java
Mono<Optional<Recommendation>> recommendation =
        fetchRecommendation(id)
                .map(Optional::of)
                .defaultIfEmpty(Optional.empty());

return Mono.zip(
        fetchProduct(id),
        recommendation,
        ProductPage::new
);
~~~

This clearly separates having no recommendation from a failed request.

### 3.4. zip and errors

By default, if one source emits an error, Mono.zip emits that error and cancels the remaining sources. This fail-fast behavior fits when the aggregated result cannot succeed if a required part is missing.

If you want to wait for remaining sources to finish before emitting the error, you can use Mono.zipDelayError:

~~~java
return Mono.zipDelayError(
        fetchProduct(id),
        fetchInventory(id),
        fetchPrice(id),
        Dashboard::new
);
~~~

zipDelayError defers errors until remaining sources have had a chance to complete. If multiple sources fail, exceptions may be combined as suppressed exceptions. If one source completes empty, the final result may still be an empty Mono once other sources finish.

Do not use zipDelayError just to mask errors. Choose fail-fast or delay-error based on whether the application needs to collect all results/errors.

## 4. Mono.when: waiting for multiple tasks without values

Mono.zip fits when combining values. When publishers only represent task completion—such as writing an audit log, updating metrics, or publishing an event—they typically have type Mono<Void>.

Mono<Void> completes without emitting a value. Therefore, do not use zip to await multiple Mono<Void>; zip will have no values to pass to the combinator.

Use Mono.when:

~~~java
Mono<Void> saveSideEffects(Event event) {
    return Mono.when(
            writeAudit(event),
            updateCounter(event),
            publishNotification(event)
    );
}
~~~

Mono.when completes when all tasks complete. If you need to return a result after the side effects:

~~~java
return Mono.when(writeAudit(event), publishNotification(event))
        .thenReturn(new Accepted(event.id()));
~~~

Mono.when coordinates completion signals; it does not collect values from sources. You can use Mono.whenDelayError when you want to defer errors so remaining tasks have a chance to finish.

## 5. Flux.flatMap: limiting concurrent in-flight calls

### 5.1. The multi-ID list problem

Suppose we need to call the Catalog API for 500 product IDs. The following creates a publisher per ID and lets all inner publishers be subscribed according to the operator's default scheduling:

~~~java
Flux<Product> products = Flux.fromIterable(ids)
        .flatMap(this::fetchProduct);
~~~

For large lists, unbounded fan-out can create too many in-flight requests, putting pressure on the connection pool and upstream. Set maxConcurrency:

~~~java
Flux<Product> products = Flux.fromIterable(ids)
        .flatMap(this::fetchProduct, 8);
~~~

The number 8 is the maximum number of inner Publishers subscribed and merged concurrently within this subscription. When one request completes, the operator can subscribe to the next request from the source.

### 5.2. Overload with both concurrency and prefetch

~~~java
Flux<Product> products = Flux.fromIterable(ids)
        .flatMap(this::fetchProduct, 8, 1);
~~~

The two parameters have different meanings:

| Parameter | Meaning |
| --- | --- |
| maxConcurrency = 8 | At most 8 inner Publishers processed concurrently |
| prefetch = 1 | Number of elements requested upfront from each inner Publisher |

With fetchProduct returning Mono<Product>, each inner publisher emits at most one element, so prefetch 1 is an intuitive choice. With an inner Flux emitting multiple elements, prefetch affects how many elements are requested upfront from each inner publisher and how much data can be queued.

**prefetch is not the concurrency limit.** The parameter controlling the number of active inner Publishers is maxConcurrency.

### 5.3. flatMap does not preserve input order

flatMap merges results as inner publishers emit data. Whichever request finishes first may emit first, even if its ID appeared later in the list.

Example input:

~~~text
p-1, p-2, p-3
~~~

Response times:

~~~text
p-1: 500 ms
p-2: 100 ms
p-3: 250 ms
~~~

Results may emit in the order:

~~~text
p-2, p-3, p-1
~~~

This is desirable when prioritizing throughput and results are independent. If input order must be preserved, use flatMapSequential.

## 6. Choosing flatMap, flatMapSequential, or concatMap

| Operator | Active inner publishers | Output order | When appropriate |
| --- | --- | --- | --- |
| flatMap(mapper, concurrency) | Multiple, up to concurrency | Completion order | Prioritize throughput; independent results |
| flatMapSequential(mapper, concurrency) | Multiple, up to concurrency | Preserves source order | Need parallelism while output must stay ordered |
| concatMap(mapper) | One inner at a time | Preserves source order | Order-dependent tasks or strict sequentiality needed |

### 6.1. flatMapSequential

~~~java
Flux<Product> ordered = Flux.fromIterable(ids)
        .flatMapSequential(this::fetchProduct, 8, 1);
~~~

flatMapSequential subscribes eagerly to inner publishers like flatMap, but keeps output in source order. If the first request is slow while the second finishes early, the second result must wait in a queue until the first result is emitted.

Consequently, flatMapSequential may use memory to buffer completed results waiting for their turn. Choose it when order genuinely matters.

### 6.2. concatMap

~~~java
Flux<Product> sequential = Flux.fromIterable(ids)
        .concatMap(this::fetchProduct);
~~~

concatMap waits for the current inner publisher to complete before subscribing to the next. It preserves order and runs only one request at a time in that pipeline.

Use when the API has a very low quota, operations have a strict order, or a later request depends on side effects of an earlier one. If requests are independent and the upstream tolerates concurrency, concatMap can unnecessarily hurt throughput.

### 6.3. Timing illustration

~~~text
flatMap, concurrency = 3
p-1: [------response------]
p-2: [--response--]
p-3: [----response----]
output: p-2, p-3, p-1

flatMapSequential, concurrency = 3
p-1: [------response------]
p-2: [--response--] (waiting to emit)
p-3: [----response----] (waiting to emit)
output: p-1, p-2, p-3

concatMap
p-1: [------response------]
p-2:                      [--response--]
p-3:                                    [----response----]
output: p-1, p-2, p-3
~~~

## 7. Concurrency limit is per subscription

maxConcurrency in flatMap applies to a single subscription of the pipeline.

For instance, each request to a local endpoint calls:

~~~java
client.findMany(ids, 4)
~~~

Each subscription can run up to 4 inner requests. If 20 local requests arrive concurrently, each with its own pipeline, total requests hitting the upstream can far exceed 4.

Therefore, distinguish:

- **Per-subscription limit:** limit within a single list-processing call; use flatMap maxConcurrency.
- **Global bulkhead:** limit on total active calls across multiple local requests; use a shared mechanism like semaphore/bulkhead or gateway-level limits.
- **Connection pool limit:** transport resource limit of the HTTP client; requests exceeding connection count may wait to acquire. This is a transport limit, not a substitute for business quotas.
- **Rate limit:** limit on requests per time window, e.g., 50 requests/second. It differs from limiting concurrent in-flight requests.

If each call takes 500 ms on average and the system needs to handle about 12 requests/second, Little's Law gives an initial estimate of around 6 in-flight requests. That is only a starting point; measure p95/p99 latency, upstream quotas, connection pool behavior, and real load before choosing limits.

Do not set concurrency sky-high just to saturate the connection pool. Excessive load can slow down the upstream, causing many requests to time out and retry together, triggering a retry storm.

## 8. Error handling in fan-out

### 8.1. Default error behavior of flatMap

By default, when an inner publisher emits an error, flatMap propagates the error downstream and cancels remaining inner publishers. This is fail-fast.

This behavior fits when the entire batch is only valid if every item succeeds. If one item fails while others still need results, recover from the error inside the mapper.

### 8.2. Per-item error recovery

~~~java
Flux<LookupResult> results = Flux.fromIterable(ids)
        .flatMap(id ->
                fetchProduct(id)
                        .map(LookupResult::success)
                        .onErrorResume(error ->
                                Mono.just(LookupResult.failure(
                                        id,
                                        classify(error)
                                ))
                        ),
                8,
                1
        );
~~~

onErrorResume sits inside the mapper, so a single item's failure becomes LookupResult.failure. Remaining items keep running.

If onErrorResume is placed outside flatMap, the first error can terminate the batch before remaining items finish; the fallback then only handles failure for the entire pipeline.

Never expose raw exception messages, internal URLs, tokens, or sensitive bodies in client responses. Translate errors into filtered business status codes.

### 8.3. Delay error

If you want remaining inner publishers to continue before emitting the error, Reactor provides delay-error variants such as flatMapDelayError. They are useful when collecting multiple errors across a batch.

Delay error does not mean ignoring errors. The final outcome can still be an error once the backlog completes. If the batch must always return a result per ID, per-item error recovery is usually clearer.

### 8.4. Do not retry the entire batch when one item fails

A common mistake is placing retry after the fan-out pipeline:

~~~java
Flux.fromIterable(ids)
        .flatMap(this::fetchProduct, 8)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200)));
~~~

When the batch fails, an outer retry can resubscribe to the source and re-invoke requests that already succeeded earlier. This creates unnecessary duplicate load.

Place timeouts and retries inside each request's publisher when the retry policy is per item:

~~~java
Mono<Product> fetchProduct(String id) {
    return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class)
            .timeout(Duration.ofSeconds(2))
            .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                    .filter(this::isRetryable));
}
~~~

This example allows up to two retries after the initial attempt. Retry only failures identified as transient; do not retry all 4xx responses by default. For POST or operations with side effects, retry only with an idempotency key or duplicate-prevention mechanism.

## 9. Timeout, cancellation, and backpressure

### 9.1. Timeouts for individual requests and the whole batch

Place a timeout inside fetchProduct to cap each individual HTTP request:

~~~java
Mono<Product> fetchProduct(String id) {
    return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class)
            .timeout(Duration.ofSeconds(2));
}
~~~

Place a timeout after flatMap to cap the whole batch:

~~~java
Flux<Product> products = Flux.fromIterable(ids)
        .flatMap(this::fetchProduct, 8, 1)
        .timeout(Duration.ofSeconds(10));
~~~

The two limits serve two different goals. If one request takes 5 seconds while others are fast, a per-request timeout and a batch timeout will behave differently.

### 9.2. Cancellation

When the local client cancels the subscription, cancellation propagates down the pipeline. Active inner publishers are cancelled per Reactor and WebClient connector contracts. This stops work whose results no longer have a receiver.

Never call nested subscribe() because an independent publisher is no longer governed by the main pipeline's cancellation.

### 9.3. Backpressure

Backpressure lets downstream control how many elements are requested from upstream. flatMap combines demand with concurrency and prefetch to regulate inner publishers.

However, backpressure cannot shrink an already materialized Java list. If the application loads one million IDs into a List before calling Flux.fromIterable, that List still occupies memory. For large datasets, read IDs in pages or stream from the data source rather than materializing everything.

Do not call collectList() on large responses unless an in-memory list is truly required. Process item by item and collect results only when the count is bounded.

## 10. Concurrency is not rate limiting

Two limits that are frequently confused:

| Limit type | Question | Example |
| --- | --- | --- |
| Concurrency | How many requests are running at the same time? | At most 8 in-flight requests |
| Rate limit | How many requests are started within a time interval? | At most 50 requests per second |

If each request takes 10 ms, a concurrency of 8 can still generate hundreds of requests per second. Conversely, a rate limit of 50 requests/second does not guarantee only 8 requests are running concurrently if latency spikes.

If the upstream enforces a per-second quota, a dedicated rate limiter is required. If the upstream limits active concurrent tasks, a bulkhead/concurrency limit is required. A system may need both.

## 11. WebClient I/O does not need parallel() to run concurrently

WebClient is a non-blocking HTTP client. For independent I/O requests, flatMap or Mono.zip already allows requests waiting on I/O to progress concurrently.

There is no need to write:

~~~java
Flux.fromIterable(ids)
        .parallel()
        .runOn(Schedulers.parallel())
        .flatMap(this::fetchProduct);
~~~

parallel() splits a sequence into rails for scheduler-based parallel CPU work; it is not a tool for limiting HTTP request concurrency. Using it mechanically can complicate code without improving I/O.

If you must call a legacy blocking library, wrap the blocking operation and offload it to boundedElastic:

~~~java
Mono<Result> legacyCall(String id) {
    return Mono.fromCallable(() -> blockingClient.fetch(id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Afterward, you can still use flatMap with maxConcurrency to limit how many blocking tasks run concurrently.

## 12. Runnable Java 17+ example: Dashboard and batch lookup

This example uses Spring Boot 3.5.5, Java 17+, and WebFlux. The application showcases coordination patterns:

- dashboard(id): calls Product, Inventory, and Price independently and combines them with Mono.zip.
- findMany(ids, maxConcurrent): calls the Product API for a list of IDs with a concurrency limit.
- findManyOrdered(...): preserves ID order via flatMapSequential.
- findManySequential(...): calls one by one via concatMap.

### 12.1. Project structure

~~~text
webclient-fanout/
├── pom.xml
└── src/
    ├── main/java/example/fanout/
    │   ├── DemoApplication.java
    │   ├── CatalogProperties.java
    │   ├── CatalogClientConfiguration.java
    │   ├── CatalogClient.java
    │   ├── CatalogController.java
    │   ├── Product.java
    │   ├── Inventory.java
    │   ├── Price.java
    │   └── Dashboard.java
    └── test/java/example/fanout/
        └── CatalogClientTest.java
~~~

### 12.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webclient-fanout</artifactId>
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
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
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

### 12.3. Product.java

~~~java
package example.fanout;

public record Product(String id, String name) {
}
~~~

### 12.4. Inventory.java

~~~java
package example.fanout;

public record Inventory(int available) {
}
~~~

### 12.5. Price.java

~~~java
package example.fanout;

import java.math.BigDecimal;

public record Price(BigDecimal amount, String currency) {
}
~~~

### 12.6. Dashboard.java

~~~java
package example.fanout;

public record Dashboard(
        Product product,
        Inventory inventory,
        Price price
) {
}
~~~

### 12.7. CatalogProperties.java

~~~java
package example.fanout;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(String baseUrl) {
}
~~~

### 12.8. CatalogClientConfiguration.java

~~~java
package example.fanout;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogClientConfiguration {

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            CatalogProperties properties
    ) {
        return builder.baseUrl(properties.baseUrl()).build();
    }

    @Bean
    CatalogClient catalogClient(WebClient catalogWebClient) {
        return new CatalogClient(catalogWebClient);
    }
}
~~~

### 12.9. CatalogClient.java

~~~java
package example.fanout;

import java.time.Duration;
import java.util.function.Function;

import org.reactivestreams.Publisher;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<Dashboard> dashboard(String id) {
        Mono<Product> product = get("/products/{id}", id, Product.class);
        Mono<Inventory> inventory = get(
                "/inventory/{id}", id, Inventory.class);
        Mono<Price> price = get("/prices/{id}", id, Price.class);

        return Mono.zip(product, inventory, price, Dashboard::new)
                .timeout(Duration.ofSeconds(3));
    }

    public Mono<Product> findProduct(String id) {
        return get("/products/{id}", id, Product.class)
                .retryWhen(Retry.backoff(
                                2,
                                Duration.ofMillis(100))
                        .filter(this::isRetryable));
    }

    public Flux<Product> findMany(
            Iterable<String> ids,
            int maxConcurrent
    ) {
        return boundedMap(ids, this::findProduct, maxConcurrent);
    }

    public Flux<Product> findManyOrdered(
            Iterable<String> ids,
            int maxConcurrent
    ) {
        requirePositive(maxConcurrent);

        return Flux.fromIterable(ids)
                .flatMapSequential(this::findProduct, maxConcurrent, 1);
    }

    public Flux<Product> findManySequential(Iterable<String> ids) {
        return Flux.fromIterable(ids)
                .concatMap(this::findProduct, 1);
    }

    private <T> Mono<T> get(String path, String id, Class<T> type) {
        return webClient.get()
                .uri(path, id)
                .retrieve()
                .bodyToMono(type)
                .timeout(Duration.ofSeconds(2));
    }

    private boolean isRetryable(Throwable error) {
        return error instanceof WebClientResponseException response
                && response.getStatusCode().is5xxServerError();
    }

    static <I, O> Flux<O> boundedMap(
            Iterable<I> inputs,
            Function<? super I, ? extends Publisher<? extends O>> mapper,
            int maxConcurrent
    ) {
        requirePositive(maxConcurrent);

        return Flux.fromIterable(inputs)
                .flatMap(mapper, maxConcurrent, 1);
    }

    private static void requirePositive(int maxConcurrent) {
        if (maxConcurrent < 1) {
            throw new IllegalArgumentException(
                    "maxConcurrent must be greater than zero");
        }
    }
}
~~~

Analysis:

- dashboard creates three independent Monos. When Mono.zip is subscribed, all three requests can run concurrently.
- Dashboard::new is invoked only after Product, Inventory, and Price have all emitted values.
- findProduct applies a per-request timeout and retries up to two times on HTTP 5xx errors.
- findMany uses flatMap with maxConcurrent to limit in-flight requests within the current subscription.
- findManyOrdered still runs requests concurrently while emitting results in input ID order.
- findManySequential runs only one request at a time.
- boundedMap validates concurrency is greater than 0; prefetch of 1 fits inner publishers returning Mono.

Retries in the example apply only to 5xx errors. 4xx errors, timeouts, and connection errors are not automatically retried. This is an illustrative policy; production must clearly define transient errors and idempotency for each API.

### 12.10. CatalogController.java

~~~java
package example.fanout;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/catalog")
public class CatalogController {

    private final CatalogClient client;

    public CatalogController(CatalogClient client) {
        this.client = client;
    }

    @GetMapping("/dashboard/{id}")
    public Mono<Dashboard> dashboard(@PathVariable String id) {
        return client.dashboard(id);
    }

    @GetMapping("/products")
    public Flux<Product> products(
            @RequestParam("ids") List<String> ids,
            @RequestParam(defaultValue = "4") int maxConcurrent
    ) {
        if (maxConcurrent < 1 || maxConcurrent > 16) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "maxConcurrent must be between 1 and 16"
            );
        }

        return client.findMany(ids, maxConcurrent);
    }
}
~~~

The 1 to 16 bound is a demo API policy. Real applications should choose maximum values based on upstream quotas and system capacity.

### 12.11. DemoApplication.java

~~~java
package example.fanout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 12.12. application.yml

~~~yaml
catalog:
  base-url: http://localhost:8081
~~~

In real environments, place the upstream URL in deployment configuration. Never hardcode credentials or tokens in source code.

## 13. Testing with MockWebServer and StepVerifier

MockWebServer lets you test WebClient over real local HTTP. You can configure responses by path and verify how the pipeline coordinates requests.

CatalogClientTest.java:

~~~java
package example.fanout;

import java.io.IOException;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogClientTest {

    private MockWebServer server;
    private CatalogClient client;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        WebClient webClient = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .build();

        client = new CatalogClient(webClient);
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void combinesIndependentRequestsIntoDashboard() {
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                return switch (request.getPath()) {
                    case "/products/p-1" -> json(
                            "{\"id\":\"p-1\",\"name\":\"Keyboard\"}");
                    case "/inventory/p-1" -> json(
                            "{\"available\":8}");
                    case "/prices/p-1" -> json(
                            "{\"amount\":49.90,\"currency\":\"USD\"}");
                    default -> new MockResponse().setResponseCode(404);
                };
            }
        });

        StepVerifier.create(client.dashboard("p-1"))
                .assertNext(dashboard -> {
                    assertThat(dashboard.product().name())
                            .isEqualTo("Keyboard");
                    assertThat(dashboard.inventory().available())
                            .isEqualTo(8);
                    assertThat(dashboard.price().currency())
                            .isEqualTo("USD");
                    assertThat(dashboard.price().amount())
                            .isEqualByComparingTo("49.90");
                })
                .verifyComplete();
    }

    @Test
    void boundedMapNeverExceedsConfiguredConcurrency() {
        AtomicInteger inFlight = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();

        List<Integer> ids = IntStream.range(0, 12)
                .boxed()
                .toList();

        Flux<Integer> result = CatalogClient.boundedMap(
                ids,
                id -> Mono.delay(Duration.ofMillis(50))
                        .doOnSubscribe(subscription -> {
                            int current = inFlight.incrementAndGet();
                            maximum.accumulateAndGet(current, Math::max);
                        })
                        .doFinally(signal -> inFlight.decrementAndGet())
                        .thenReturn(id),
                3
        );

        StepVerifier.create(result)
                .expectNextCount(12)
                .verifyComplete();

        assertThat(maximum.get()).isEqualTo(3);
        assertThat(inFlight.get()).isZero();
    }

    private MockResponse json(String body) {
        return new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody(body);
    }
}
~~~

The first test confirms three independent endpoints are combined into one Dashboard with the expected data. The second test creates 12 asynchronous publishers and measures active publishers; the maximum must equal 3 when maxConcurrent is 3.

StepVerifier verifies Mono/Flux signals without blocking in application code. The concurrency test uses Mono.delay to simulate asynchronous I/O and tests the exact helper used by findMany.

### 13.1. Running tests

From the directory containing pom.xml:

~~~bash
mvn test
~~~

### 13.2. Running the application

~~~bash
mvn spring-boot:run
~~~

Assuming Catalog API, Inventory API, and Pricing API are running on localhost:8081:

~~~bash
curl http://localhost:8080/catalog/dashboard/p-1
curl "http://localhost:8080/catalog/products?ids=p-1&ids=p-2&ids=p-3&maxConcurrent=2"
~~~

Dashboard calls three independent APIs and returns an aggregated object. The products endpoint calls multiple product IDs with at most two concurrent inner requests within that subscription.

## 14. Configuring the connection pool and transport limits

WebClient typically uses Reactor Netty as the HTTP connector in Spring Boot WebFlux applications. The connection pool can limit the number of connections and pending requests waiting to acquire a connection.

Illustrative configuration:

~~~java
ConnectionProvider provider = ConnectionProvider.builder("catalog")
        .maxConnections(32)
        .pendingAcquireMaxCount(64)
        .build();

HttpClient httpClient = HttpClient.create(provider);

WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .baseUrl("http://localhost:8081")
        .build();
~~~

Requires the Reactor Netty HTTP dependency and corresponding imports:

~~~java
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;
~~~

maxConnections limits connections in the pool; pendingAcquireMaxCount limits requests waiting to acquire a connection. This is transport resource control. It does not replace business-level fan-out limits.

With HTTP/2, one connection can multiplex multiple streams, so do not simply assume one connection equals one request. Combine application limits, connection pool limits, and upstream quotas.

## 15. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling block() after each request | Requests run sequentially and block threads | Combine Monos with zip or flatMap |
| Calling subscribe() separately for each request | Loses shared error and cancellation management | Return a single Mono/Flux |
| Using zip for dependent requests | Cannot build the later request without prior output | Use flatMap for dependent steps |
| Using zip with Mono<Void> | Zip receives no values to combine | Use Mono.when |
| Forgetting to handle empty Mono in zip | The whole zip may complete empty | defaultIfEmpty or switchIfEmpty |
| Using unbounded flatMap on large lists | Too many concurrent requests | Set maxConcurrency |
| Confusing prefetch with concurrency | Load limiting behaves unexpectedly | Adjust the maxConcurrency parameter |
| Using flatMap when order must be preserved | Results may emit in completion order | Use flatMapSequential |
| Using concatMap for everything | Only one request runs at a time | Use flatMap when calls can run independently |
| Placing onErrorResume outside the whole batch | One failure loses results of other items | Recover errors inside the mapper |
| Retrying the entire fan-out | Already succeeded requests get re-invoked | Retry each inner publisher |
| Retrying all 4xx/5xx | Repeats unrecoverable requests or triggers retry storms | Retry only transient errors with bounds |
| Assuming per-subscription concurrency is global | Multiple local requests can exceed total quota | Use a shared bulkhead or limiter |
| Confusing concurrency with rate limit | Can exceed requests-per-second quota | Use a dedicated rate limiter |
| Calling collectList() on large datasets | Holds all results in heap | Process streaming or paginate |
| Using parallel() to speed up HTTP I/O | Adds unnecessary scheduler overhead | Use flatMap with appropriate concurrency |
| Not setting timeouts | One slow inner request holds a slot too long | Set per-request and batch timeouts |

## 16. Checklist for choosing a coordination pattern

Before implementing fan-out, answer:

1. Are the requests truly independent, or does a later request need data from an earlier one?
2. Do you need a single aggregated value, multiple values, or only to await side effects?
3. If one source is empty, what should the aggregated result be?
4. If one source fails, fail fast or wait for other sources to finish?
5. Must input order be preserved?
6. How many concurrent requests may run within a single subscription?
7. Do multiple concurrent local requests require a global bulkhead?
8. Does the upstream limit concurrency, requests/second, or both?
9. Do timeouts and retries apply per request or to the entire batch?
10. Should one failing item fail the entire batch?
11. Does cancellation propagate to active in-flight requests?
12. Are the input list and results small enough to fit in memory?
13. Do the connection pool and pending acquire queue match concurrency?
14. Are tests measuring max active inner publishers and verifying error/cancel cases?

## 17. Key takeaways

- Mono.zip coordinates multiple independent Monos and builds one result when all sources emit values.
- Mono.zip is fail-fast; empty or failing sources can cancel remaining sources.
- Use defaultIfEmpty for optional sources; use zipDelayError when errors genuinely need deferral.
- Mono.when fits awaiting multiple Mono<Void> tasks.
- Flux.flatMap(mapper, maxConcurrency, prefetch) limits active inner publishers within a subscription.
- maxConcurrency caps concurrent requests; prefetch controls element demand from each inner publisher.
- flatMap does not preserve order; flatMapSequential runs concurrently while preserving order; concatMap runs sequentially.
- Per-subscription concurrency is not global concurrency across multiple local requests.
- Rate limits, bulkheads, and connection pools address different limiting layers.
- Place timeouts and retries on individual requests; do not retry the entire batch when one item fails.
- Recover errors inside the mapper if other items should continue.
- WebClient I/O does not need parallel() or block(); compose Mono/Flux and preserve backpressure.
- Test fan-out with MockWebServer and StepVerifier, measuring max in-flight publishers and verifying cancellation/errors.

**Official documentation:**
- [Spring Framework — WebClient: Synchronous Use and composing multiple calls](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html)
- [Spring Framework — WebClient retrieve()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html)
- [Project Reactor 3.5 — Flux Javadoc: flatMap, flatMapSequential, concatMap](https://docs.spring.io/projectreactor/reactor-core/docs/3.5.x/api/reactor/core/publisher/Flux.html)
- [Project Reactor — Mono Javadoc: zip and zipDelayError](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Spring Framework — Testing WebClient with MockWebServer](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html)
- [Reactor Netty — Connection Provider](https://projectreactor.io/docs/netty/release/reference/http-client.html)
