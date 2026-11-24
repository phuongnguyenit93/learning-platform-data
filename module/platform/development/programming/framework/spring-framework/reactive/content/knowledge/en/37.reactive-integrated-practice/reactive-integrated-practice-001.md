# Designing a Data Aggregation Flow from Multiple HTTP Services

An aggregation API often has to call multiple backend services to produce a single response. For example, a dashboard screen needs customer information from Customer Service, order metrics from Order Service, and a list of recommendations from Recommendation Service. If each service is called sequentially, the total wait time can approach the sum of all downstream latencies. With Spring WebFlux and WebClient, we can launch independent requests reactively, wait for their results, and combine them into one response using the fan-out/fan-in pattern.

This lesson focuses on choosing the right operator for each dependency relationship: Mono.zip when combining multiple single results, flatMap when a subsequent request depends on a previous result, Flux.merge when receiving multiple streams in completion order, and concat when sequential ordering must be preserved. The implementation also handles timeouts, required/optional service failures, bounded retries, cancellation, backpressure, and testing with an HTTP mock server.

The goal is not to turn every downstream call into a complex pipeline. What matters is accurately modeling the relationships between data sources, identifying which sources are required and which can degrade gracefully, and then setting clear time and resource limits.

## 1. Learning Objectives

After this lesson, you can:

1. Describe the fan-out/fan-in pattern in an aggregation API.
2. Distinguish between sequential calls and concurrent calls to independent services.
3. Use Mono.zip to combine multiple single results.
4. Use flatMap when the next call depends on previous data.
5. Choose Flux.merge, concat, and flatMapSequential based on ordering requirements.
6. Understand why Mono<Void> cannot act as a regular data source in zip.
7. Classify downstreams into required and optional.
8. Handle 4xx/5xx, timeouts, network errors, and intentional empty responses.
9. Retry transient errors with backoff, bounded attempts, and an overall deadline.
10. Allow cancellation and backpressure to propagate through the pipeline.
11. Design partial responses without hiding critical errors.
12. Use the WebClient.Builder configured by Spring Boot and separate clients by base URL.
13. Write a runnable Java 17 application integrating with three downstream HTTP services.
14. Test the aggregation flow using WebTestClient and MockWebServer.

## 2. The Aggregation Problem: Fan-Out and Fan-In

Suppose the endpoint is:

~~~http
GET /api/dashboard/42
~~~

Three services need to be called:

| Service | Endpoint | Role | Policy |
| --- | --- | --- | --- |
| Customer | GET /customers/42 | Customer name and identity | Required |
| Orders | GET /orders/summary/42 | Order count and total spend | Optional |
| Recommendations | GET /recommendations/42 | List of recommendations | Optional |

Aggregated response:

~~~json
{
  "customerId": "42",
  "customerName": "An",
  "orderCount": 3,
  "totalSpend": 125.50,
  "recommendations": ["book", "keyboard"]
}
~~~

Customer is required data. If the customer cannot be identified, the dashboard is meaningless and should return an error. Orders and recommendations are supplementary data; if either service encounters a transient error, the API can return a degraded response with default values and record the error in logs/metrics.

### 2.1. Sequential Calls

~~~java
return loadCustomer(id)
    .flatMap(customer ->
        loadOrders(id)
            .flatMap(orders ->
                loadRecommendations(id)
                    .map(recommendations ->
                        combine(customer, orders, recommendations)
                    )
            )
    );
~~~

If three independent requests have latencies of 200 ms, 300 ms, and 250 ms respectively, the wait time is close to the sum of 750 ms (excluding overhead). Sequential calls are appropriate when a subsequent request needs the previous request's result, but suboptimal for independent sources.

### 2.2. Fan-Out/Fan-In

~~~text
                 API /dashboard/42
                         |
                         v
                    Fan-out
                  /     |      \
                 v      v       v
           Customer   Orders  Recommendations
              |         |          |
              +---------+----------+
                         |
                         v
                    Fan-in / zip
                         |
                         v
                 Dashboard response
~~~

If independent requests are launched nearly simultaneously, the group latency can approach that of the slowest request rather than the sum of latencies. For example, ideally with 200/300/250 ms it is about 300 ms plus overhead. This is only an estimation model; DNS, connection pool, network, server queue, and CPU still affect actual timing.

### 2.3. When Should You Not Fan-Out Concurrently?

Do not launch concurrently if:

- Input data for the next request is only available after the previous response.
- The downstream has a low quota and does not allow that concurrency level.
- Requests depend on ordering or have side effects.
- Concurrent reads produce an inconsistent snapshot that the business rules do not accept.
- A single request can fan-out thousands of times without bounds.

Concurrency is a decision about dependencies and capacity, not an end in itself.

## 3. Choosing Operators by Data Relationship

| Operator | Use When | Characteristics |
| --- | --- | --- |
| Mono.zip | Combining one value from multiple sources | Produces a result only when every source emits an item |
| flatMap | Creating a new publisher based on a previous item | Branches can run asynchronously |
| Flux.merge | Combining multiple independent streams | Items are emitted in arrival order |
| Flux.concat | Combining streams in order | Waits for the previous stream to complete before subscribing to the next |
| flatMapSequential | Running multiple branches concurrently while keeping source order | May buffer results that arrive early |
| Mono.when | Waiting for multiple tasks that only need completion | Does not combine result values |

### 3.1. Mono.zip for Multiple Single Results

~~~java
Mono<Customer> customer = loadCustomer(id);
Mono<OrderSummary> orders = loadOrders(id);
Mono<Recommendations> recommendations = loadRecommendations(id);

return Mono.zip(customer, orders, recommendations)
    .map(tuple -> combine(
        tuple.getT1(),
        tuple.getT2(),
        tuple.getT3()
    ));
~~~

Mono.zip subscribes to the sources and combines their values into a tuple when each source emits an item. With WebClient, each source is an asynchronous HTTP request, so independent requests can wait on the network simultaneously.

If one source emits an error, the zip result typically errors and the remaining sources are cancelled. If one source completes without emitting an item, zip can complete empty without invoking the combine function. Therefore, you must explicitly decide how to handle empty response bodies before combining.

### 3.2. Mono.zip and Empty Publishers

This is a common mistake:

~~~java
Mono<Void> saveAudit = saveAuditEvent(event);
Mono<Customer> customer = loadCustomer(id);

return Mono.zip(saveAudit, customer, (ignored, value) -> value);
~~~

Mono<Void> represents completion without an item. zip needs one item from each source, so the combine function is not called as expected.

If you only need to wait for a group of side effects to complete, use:

~~~java
return Mono.when(saveAudit, publishEvent);
~~~

If you need both data results and side effects, combine the data first and then use then/thenReturn for side effects in the proper business order; do not turn Mono<Void> into a fake zip source.

### 3.3. zipDelayError

Mono.zipDelayError can wait for the other sources to finish before emitting the combined error. Use it when you need to collect multiple errors or allow independent operations to finish before reporting failure. It does not automatically turn errors into partial responses and does not replace a fallback policy.

### 3.4. flatMap for Conditional Dependencies

For example, needing to fetch the profile first to learn the tenant before calling the pricing service:

~~~java
return customerClient.get()
    .uri("/customers/{id}", id)
    .retrieve()
    .bodyToMono(CustomerProfile.class)
    .flatMap(customer ->
        priceClient.get()
            .uri("/prices/{tenant}/{sku}",
                customer.tenantId(), sku)
            .retrieve()
            .bodyToMono(PriceView.class)
            .map(price -> combine(customer, price))
    );
~~~

The price request depends on the tenant in the customer profile, so this is a true dependency chain. Using zip here does not help because the URL/input for the second request is not yet known.

### 3.5. Flux.merge When Arrival Order Matters

~~~java
Flux<Event> events = Flux.merge(
    customerEvents(),
    orderEvents(),
    inventoryEvents()
);
~~~

Events are emitted as each source produces an item. An event from inventory can arrive before a customer event even though the customer source was declared first.

### 3.6. concat When Order Must Be Preserved

~~~java
Flux<Event> events = Flux.concat(
    initialSnapshot(),
    liveUpdates()
);
~~~

concat subscribes to the first source, waits for completion, and only then moves to the next source. It preserves order, but there is no concurrent fan-out across sources.

### 3.7. flatMap and Concurrency Limits

~~~java
Flux<ProductView> products = Flux.fromIterable(productIds)
    .flatMap(this::loadProduct, 8);
~~~

The parameter 8 limits the number of inner publishers subscribed concurrently. Do not use unbounded flatMap(this::loadProduct) for a list that could contain millions of IDs. If you need to emit results in the original ID order while still calling concurrently, consider flatMapSequential and evaluate the buffering cost.

## 4. Designing Required and Optional Downstreams

Not every backend service has the same level of criticality.

### 4.1. Required Dependency

Required data is a prerequisite for building a valid response. For example, Customer Service must return a profile. If the service is down, times out, or returns an unrecoverable error, the API should return a meaningful error, typically 502/503 depending on semantics.

Do not replace the customer with an empty object just so the response is always 200. That hides business errors and can cause the client to display incorrect data.

### 4.2. Optional Dependency

An optional dependency can use a fallback if the error belongs to a degradable category:

- Network/connect error.
- Timeout.
- Transient downstream 5xx.
- Empty response if the contract allows treating it as no data.

Do not automatically fall back for all 4xx responses. 400 could be an invalid request; 401/403 could be a credential configuration issue; 404 could carry specific business meaning. Define the policy per service.

Example:

~~~java
Mono<OrderSummary> orders = loadOrders(id)
    .onErrorResume(
        WebClientRequestException.class,
        error -> Mono.just(OrderSummary.empty())
    );
~~~

This only illustrates one error type. Production should have logs/metrics recording fallbacks and restrict which exceptions are handled.

### 4.3. Partial Responses Must Have a Clear Contract

If an optional service is unavailable, the response can include a status:

~~~json
{
  "orderCount": 0,
  "totalSpend": 0,
  "degraded": ["orders"]
}
~~~

The degraded list lets the client know data is missing due to a downstream error, distinguishing it from genuinely having no orders. If the API cannot change its schema, at a minimum record metrics/logs and document the fallback semantics.

### 4.4. Empty Mono Is Different from Error

- Mono.just(value): has one result.
- Mono.empty(): completes without a result.
- Mono.error(error): terminates with an error.
- Mono<Void>: represents completion without a data item.

For required sources, you can convert empty to an error:

~~~java
bodyToMono(CustomerProfile.class)
    .switchIfEmpty(Mono.error(
        new RequiredDependencyFailure("customer")
    ));
~~~

For optional sources, you can convert empty to a default value if the contract allows:

~~~java
bodyToMono(RecommendationResponse.class)
    .defaultIfEmpty(RecommendationResponse.empty());
~~~

## 5. WebClient: Calling HTTP Services Reactively

WebClient is the reactive HTTP client of Spring WebFlux. It supports asynchronous request/response, streaming response bodies, and Reactor integration.

Example:

~~~java
Mono<CustomerProfile> customer = webClient.get()
    .uri("/customers/{id}", customerId)
    .retrieve()
    .bodyToMono(CustomerProfile.class);
~~~

### 5.1. retrieve and exchangeToMono

retrieve() is the simple choice for normal responses. By default, 4xx/5xx responses produce a WebClientResponseException. You can customize this with onStatus:

~~~java
Mono<CustomerProfile> customer = webClient.get()
    .uri("/customers/{id}", customerId)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        response -> Mono.error(
            new CustomerNotFoundException(customerId)
        )
    )
    .bodyToMono(CustomerProfile.class);
~~~

Use exchangeToMono when you need more complex decoding decisions based on status/headers/body. When using the exchange API, you must consume or release the response body per contract so connections are properly freed.

### 5.2. Creating Separate Clients by Base URL

You can use a Boot-managed builder and clone it to configure multiple services:

~~~java
WebClient customerClient = builder.clone()
    .baseUrl(customerBaseUrl)
    .build();

WebClient orderClient = builder.clone()
    .baseUrl(orderBaseUrl)
    .build();

WebClient recommendationClient = builder.clone()
    .baseUrl(recommendationBaseUrl)
    .build();
~~~

Using the builder provided by Spring Boot preserves auto-configured customizers, codecs, and observation configuration. Do not instantiate your own WebClient and assume it has all of Boot's configuration.

### 5.3. URI Templates and Encoding

Use:

~~~java
.uri("/customers/{id}", customerId)
~~~

instead of manually concatenating URL strings from input. URI templates provide consistent encoding and help observability recognize stable endpoint patterns. You still need to validate the ID according to business rules.

## 6. Timeouts, Deadlines, and Latency Budgets

Each downstream can hang or respond too slowly. You need a timeout for each individual request and a deadline for the entire aggregation.

Example:

~~~java
private static final Duration DEPENDENCY_TIMEOUT =
    Duration.ofSeconds(2);

private static final Duration TOTAL_TIMEOUT =
    Duration.ofSeconds(4);
~~~

Individual call:

~~~java
Mono<CustomerProfile> customer = loadCustomer(id)
    .timeout(DEPENDENCY_TIMEOUT);
~~~

Entire fan-in:

~~~java
return Mono.zip(customer, orders, recommendations)
    .map(this::combine)
    .timeout(TOTAL_TIMEOUT);
~~~

If three sources run concurrently, the total time is not the sum of the three timeouts. Still, an overall deadline is needed to protect the caller and resources. Set the overall timeout to fit the latency budget of the API gateway/frontend.

### 6.1. A Timeout Does Not Mean the Server Stopped Processing

When the client times out, Reactor emits an error and cancellation is sent upstream. WebClient/transport can cancel the request if still possible. However, the downstream may have already received and continued processing the request, especially for operations with side effects. A timeout on the aggregator side does not guarantee the transaction on the other service rolled back.

### 6.2. Do Not Set Timeouts Too Low

Timeouts must be based on p95/p99 metrics, network conditions, and downstream SLAs. Values that are too low cause false timeouts and retry storms; values that are too high hold connections/request contexts for too long.

### 6.3. Overall Deadline and Per-Dependency Budgets

A sample policy:

| Component | Illustrative Budget |
| --- | ---: |
| Customer required | 1.5 s |
| Orders optional | 1.2 s |
| Recommendations optional | 1.0 s |
| Total API | 2.5 s |

Branches running concurrently should have an overall deadline shorter than the sum of sequential times. These numbers are only illustrative; measure production and set them according to actual SLAs.

## 7. Bounded Retries and Transient Errors

Retries are only useful when errors are likely to recover on their own. Some principles:

- Only retry transient error categories such as connect failures, timeouts, or identified 5xx responses.
- Limit the number of attempts.
- Use exponential backoff and jitter to avoid many instances retrying in lockstep.
- Set an overall deadline that encompasses retries.
- Only retry idempotent requests or requests with an idempotency key.
- Do not retry 400/401/403 as if they were network errors.

Reactor supports:

~~~java
.retryWhen(
    Retry.backoff(2, Duration.ofMillis(100))
        .filter(this::isTransientFailure)
)
~~~

Retry.backoff(2, ...) allows at most two retries after the initial attempt. If all three attempts fail, the final error is emitted according to the Retry policy. Operator ordering matters: a per-attempt timeout can be placed before retry; the overall timeout is placed after fan-in.

### 7.1. Retries and Fallbacks

An optional branch can:

1. Call the downstream.
2. Retry certain transient errors within limits.
3. If it still fails, fall back.
4. Record that the dependency is degraded.

Do not place fallback before retry because once the first error is converted into a default value, retry no longer receives an error signal.

### 7.2. Avoiding Unsafe Side-Effect Retries

GET data reads are usually idempotent, but POST creating an order or payment is not automatically safe to retry. If the client does not know whether the previous request was processed, retrying can create duplicate records. Use an idempotency key or deduplication mechanism.

### 7.3. Circuit Breakers and Bulkheads

For high-load systems, consider Resilience4j or an equivalent mechanism:

- Circuit breaker: temporarily stops calling a downstream that is failing continuously.
- Bulkhead: limits the number of concurrent requests to a dependency.
- Rate limiter: limits the call rate.
- Retry: retries transient errors within budget.

Do not configure infinite retries or circuit breakers for all services with the same unexamined threshold. Each downstream has its own SLA, quota, and failure modes.

## 8. Error Handling in Aggregation Flows

### 8.1. WebClientResponseException

By default, retrieve() emits WebClientResponseException for 4xx/5xx responses. You can classify by status:

~~~java
private boolean isTransientFailure(Throwable error) {
    if (error instanceof WebClientRequestException) {
        return true;
    }

    if (error instanceof TimeoutException) {
        return true;
    }

    return error instanceof WebClientResponseException response
        && response.getStatusCode().is5xxServerError();
}
~~~

This is a sample policy. Depending on the service, some 429 responses can be retried after honoring Retry-After; 404 is usually not retried.

### 8.2. Required Dependency Failure

If customer service is required, map downstream errors into a gateway error with clear semantics:

~~~java
.onErrorMap(error ->
    new RequiredDependencyFailure("customer", error)
)
~~~

Controller advice can return HTTP 502 and an application error code. Do not send raw stack traces or internal downstream details to the client.

### 8.3. Optional Dependency Failure

~~~java
.onErrorResume(error -> {
    if (isTransientFailure(error)) {
        return Mono.just(OrderSummary.empty());
    }
    return Mono.error(error);
});
~~~

Do not use onErrorResume(error -> Mono.just(defaultValue)) for every exception type without a clear definition. A decode error from a mismatched schema or a 401 from wrong credentials may need to fail explicitly instead of faking empty data.

### 8.4. Zip Fail-Fast and zipDelayError

By default, zip can fail as soon as one branch errors and cancel the other branches. This is useful behavior to avoid continuing unnecessary work. If you need to wait for all branches to finish to collect multiple errors, look into zipDelayError; in exchange, the request may have to wait longer.

### 8.5. Do Not Catch and Swallow Cancellation

Cancellation is not a business error. Do not use doOnError or onErrorResume in a way that assumes every request finishes successfully. Ensure cleanup happens in doFinally/appropriate resource operators and do not continue background work after the caller has left unless explicitly required.

## 9. Backpressure, Concurrency, and Resource Limits

Reactive does not mean unbounded.

### 9.1. Limiting Fan-Out

If a dashboard calls three fixed services, concurrency is relatively small. However, if an endpoint accepts a list of 10,000 IDs and calls a service for each ID, you must bound it:

~~~java
Flux<ProductView> products = Flux.fromIterable(ids)
    .flatMap(this::loadProduct, 16);
~~~

The parameter 16 is an example. Choose the value based on downstream capacity, connection pool, and latency.

### 9.2. Connection Pool

WebClient typically uses a connector with a connection pool. If concurrency exceeds available connections, requests must wait to acquire one. Monitor pending acquires, pool saturation, and timeouts. Do not increase the pool indefinitely to mask excessive fan-out.

### 9.3. Backpressure in Flux

Flux propagates demand back upstream. Operators can prefetch/buffer, so check the semantics of each operator and bound queues. flatMap has concurrency and prefetch; merge also has buffering. For large data, stream incrementally rather than collecting everything into a list.

### 9.4. Cancellation When the Caller Disconnects

If the frontend closes the connection before the dashboard completes, cancellation should propagate to the in-flight WebClient requests. Do not call subscribe() yourself inside a service and return a different Mono, because doing so detaches the lifecycle from the HTTP request and can leave the downstream running pointlessly.

### 9.5. CPU-Bound Transforms

Lightweight JSON mapping usually fits well on the current pipeline. Heavy CPU work can block the event loop; consider an appropriate scheduler and bound concurrency. Do not move every operator to boundedElastic out of habit.

## 10. Consistency and Snapshot Data

Calling multiple services concurrently does not guarantee the responses reflect the exact same point in time.

For example:

- Customer profile is read at 10:00:00.100.
- Order summary is read at 10:00:00.250.
- Recommendations are computed from a snapshot at 09:59:59.800.

The dashboard may display slightly skewed states. This is usually acceptable eventual consistency, but must be decided according to business rules.

Ways to handle it:

- Return each source's timestamp/version if transparency is needed.
- Use a shared snapshot token or version if the services support it.
- Move aggregation into a dedicated service/query model when strong consistency is required.
- Cache infrequently changing data and clearly state freshness.
- Do not assume Mono.zip creates a distributed transaction or a consistent snapshot.

## 11. Tracing and Observing Downstreams

An aggregation API needs to monitor each dependency separately:

- Latency of customer/order/recommendation.
- Rate of timeouts, 4xx, 5xx, and network errors.
- Retry counts.
- Number of fallback/degraded responses.
- Total latency of the aggregation endpoint.
- Connection pool usage and pending acquires.
- Cancellations and requests still running past the deadline.

Use Micrometer Observation/Tracing with a properly configured WebClient to generate client observations/spans. Do not record tokens or personal data in URLs, logs, or metric tags. Metric tags should have low cardinality; dependency names like customer/orders/recommendations are appropriate, whereas customerId/orderId should not be metric tags.

## 12. Complete Java 17 Example with Spring Boot WebFlux

The example uses Java 17 and Spring Boot 3.5.16. The application has a dashboard endpoint calling three HTTP services:

- Customer is required.
- Orders and recommendations are optional.
- Each downstream has its own timeout.
- The entire aggregation has an overall deadline.
- Transient errors on optional services are converted into fallbacks.
- Errors on the required service return HTTP 502.
- Tests use three independent MockWebServer instances without calling external services.

### 12.1. Project Structure

~~~text
http-aggregation-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/AggregationApplication.java
    │   ├── java/demo/ServiceUrls.java
    │   ├── java/demo/DashboardModels.java
    │   ├── java/demo/DashboardService.java
    │   ├── java/demo/DashboardController.java
    │   └── java/demo/DownstreamErrorHandler.java
    └── test/java/demo/DashboardIntegrationTest.java
~~~

### 12.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 12.3. application.properties

~~~properties
spring.application.name=http-aggregation-demo

services.customer-base-url=http://localhost:8081
services.order-base-url=http://localhost:8082
services.recommendation-base-url=http://localhost:8083
~~~

The localhost URLs are demo configuration. In production, retrieve addresses from service discovery, environment variables, or deployment configuration; do not hard-code internal endpoints in source code.

### 12.4. AggregationApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ServiceUrls.class)
public class AggregationApplication {

    public static void main(String[] args) {
        SpringApplication.run(AggregationApplication.class, args);
    }
}
~~~

### 12.5. ServiceUrls.java

~~~java
package demo;

import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "services")
public record ServiceUrls(
    URI customerBaseUrl,
    URI orderBaseUrl,
    URI recommendationBaseUrl
) {}
~~~

Spring Boot binds the properties services.customer-base-url, services.order-base-url, and services.recommendation-base-url into the record.

### 12.6. DashboardModels.java

~~~java
package demo;

import java.math.BigDecimal;
import java.util.List;

record CustomerProfile(
    String id,
    String name
) {}

record OrderSummary(
    int orderCount,
    BigDecimal totalSpend
) {
    static OrderSummary empty() {
        return new OrderSummary(0, BigDecimal.ZERO);
    }
}

record RecommendationResponse(
    List<String> items
) {
    static RecommendationResponse empty() {
        return new RecommendationResponse(List.of());
    }
}

record DashboardView(
    String customerId,
    String customerName,
    int orderCount,
    BigDecimal totalSpend,
    List<String> recommendations
) {}

record ApiError(
    String code,
    String dependency
) {}
~~~

The package-private records live in the same demo package to keep the example concise. In a real project, each DTO can be placed in its own file.

### 12.7. DashboardService.java

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Mono;

@Service
class DashboardService {

    private static final Logger log =
        LoggerFactory.getLogger(DashboardService.class);

    private static final Duration DEPENDENCY_TIMEOUT =
        Duration.ofSeconds(2);

    private static final Duration TOTAL_TIMEOUT =
        Duration.ofSeconds(4);

    private final WebClient customerClient;
    private final WebClient orderClient;
    private final WebClient recommendationClient;

    DashboardService(
            WebClient.Builder builder,
            ServiceUrls urls) {

        this.customerClient = builder.clone()
            .baseUrl(urls.customerBaseUrl().toString())
            .build();

        this.orderClient = builder.clone()
            .baseUrl(urls.orderBaseUrl().toString())
            .build();

        this.recommendationClient = builder.clone()
            .baseUrl(urls.recommendationBaseUrl().toString())
            .build();
    }

    Mono<DashboardView> getDashboard(String customerId) {

        Mono<CustomerProfile> customer =
            customerClient.get()
                .uri("/customers/{id}", customerId)
                .retrieve()
                .bodyToMono(CustomerProfile.class)
                .timeout(DEPENDENCY_TIMEOUT)
                .switchIfEmpty(Mono.error(
                    new IllegalStateException(
                        "Customer service returned an empty body"
                    )
                ))
                .onErrorMap(error ->
                    new RequiredDependencyFailure("customer", error)
                );

        Mono<OrderSummary> orders = optional(
            orderClient.get()
                .uri("/orders/summary/{id}", customerId)
                .retrieve()
                .bodyToMono(OrderSummary.class),
            OrderSummary::empty,
            "orders"
        );

        Mono<RecommendationResponse> recommendations = optional(
            recommendationClient.get()
                .uri("/recommendations/{id}", customerId)
                .retrieve()
                .bodyToMono(RecommendationResponse.class),
            RecommendationResponse::empty,
            "recommendations"
        );

        return Mono.zip(customer, orders, recommendations)
            .map(tuple -> new DashboardView(
                tuple.getT1().id(),
                tuple.getT1().name(),
                tuple.getT2().orderCount(),
                tuple.getT2().totalSpend(),
                tuple.getT3().items()
            ))
            .timeout(TOTAL_TIMEOUT);
    }

    private <T> Mono<T> optional(
            Mono<T> source,
            Supplier<T> fallback,
            String dependency) {

        return source
            .timeout(DEPENDENCY_TIMEOUT)
            .switchIfEmpty(Mono.fromSupplier(fallback))
            .onErrorResume(
                this::isRecoverable,
                error -> {
                    log.warn(
                        "Optional dependency {} failed; using fallback",
                        dependency,
                        error
                    );
                    return Mono.fromSupplier(fallback);
                }
            );
    }

    private boolean isRecoverable(Throwable error) {
        if (error instanceof TimeoutException
                || error instanceof WebClientRequestException) {
            return true;
        }

        return error instanceof WebClientResponseException response
            && response.getStatusCode().is5xxServerError();
    }
}
~~~

Key points:

1. Three WebClients are configured from the same Boot-managed builder but with separate base URLs.
2. Three requests are created as three independent Monos before calling zip.
3. Customer has no fallback because it is a required dependency.
4. Orders and recommendations use the optional helper to handle timeouts, network errors, and 5xx responses.
5. 4xx responses are not in the recoverable list so they emit errors.
6. An empty response body from an optional service is replaced with a default value.
7. An empty response body from customer is converted into an error.
8. The overall timeout protects the API even if individual branches gain retries/fallbacks in the future.

Automatic retry is not enabled in this example to keep test behavior simple. Section 7 presents how to add bounded retries when the downstream and business rules allow.

### 12.8. RequiredDependencyFailure.java

~~~java
package demo;

final class RequiredDependencyFailure extends RuntimeException {

    private final String dependency;

    RequiredDependencyFailure(
            String dependency,
            Throwable cause) {
        super("Required dependency failed: " + dependency, cause);
        this.dependency = dependency;
    }

    String dependency() {
        return dependency;
    }
}
~~~

### 12.9. DashboardController.java

~~~java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/dashboard")
class DashboardController {

    private final DashboardService service;

    DashboardController(DashboardService service) {
        this.service = service;
    }

    @GetMapping("/{customerId}")
    Mono<DashboardView> getDashboard(
            @PathVariable String customerId) {

        return service.getDashboard(customerId);
    }
}
~~~

The controller returns the Mono directly to WebFlux. Do not call block() or subscribe() inside the controller/service; the framework manages subscription according to the HTTP request lifecycle.

### 12.10. DownstreamErrorHandler.java

~~~java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class DownstreamErrorHandler {

    @ExceptionHandler(RequiredDependencyFailure.class)
    ResponseEntity<ApiError> handleRequiredDependency(
            RequiredDependencyFailure error) {

        ApiError body = new ApiError(
            "REQUIRED_DEPENDENCY_UNAVAILABLE",
            error.dependency()
        );

        return ResponseEntity
            .status(HttpStatus.BAD_GATEWAY)
            .body(body);
    }
}
~~~

The API returns 502 when a required data source fails. Do not return raw exception messages or stack traces to the client.

### 12.11. DashboardIntegrationTest.java

~~~java
package demo;

import java.io.IOException;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class DashboardIntegrationTest {

    private static final MockWebServer CUSTOMER = startServer();
    private static final MockWebServer ORDERS = startServer();
    private static final MockWebServer RECOMMENDATIONS = startServer();

    @Autowired
    WebTestClient client;

    private static MockWebServer startServer() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        }
        catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    @DynamicPropertySource
    static void registerServiceUrls(DynamicPropertyRegistry registry) {
        registry.add(
            "services.customer-base-url",
            () -> CUSTOMER.url("/").toString()
        );
        registry.add(
            "services.order-base-url",
            () -> ORDERS.url("/").toString()
        );
        registry.add(
            "services.recommendation-base-url",
            () -> RECOMMENDATIONS.url("/").toString()
        );
    }

    @AfterAll
    static void stopServers() throws IOException {
        CUSTOMER.shutdown();
        ORDERS.shutdown();
        RECOMMENDATIONS.shutdown();
    }

    private MockResponse json(String body) {
        return new MockResponse()
            .setHeader("Content-Type", "application/json")
            .setBody(body);
    }

    @Test
    void combinesAllThreeServices() throws Exception {
        CUSTOMER.enqueue(json(
            "{\"id\":\"42\",\"name\":\"An\"}"
        ));
        ORDERS.enqueue(json(
            "{\"orderCount\":3,\"totalSpend\":125.50}"
        ));
        RECOMMENDATIONS.enqueue(json(
            "{\"items\":[\"book\",\"keyboard\"]}"
        ));

        client.get()
            .uri("/api/dashboard/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.customerId").isEqualTo("42")
            .jsonPath("$.customerName").isEqualTo("An")
            .jsonPath("$.orderCount").isEqualTo(3)
            .jsonPath("$.recommendations[0]").isEqualTo("book")
            .jsonPath("$.recommendations[1]").isEqualTo("keyboard");

        assertEquals(
            "/customers/42",
            CUSTOMER.takeRequest().getPath()
        );
        assertEquals(
            "/orders/summary/42",
            ORDERS.takeRequest().getPath()
        );
        assertEquals(
            "/recommendations/42",
            RECOMMENDATIONS.takeRequest().getPath()
        );
    }

    @Test
    void optionalOrdersFailureReturnsDegradedDashboard()
            throws Exception {

        CUSTOMER.enqueue(json(
            "{\"id\":\"42\",\"name\":\"An\"}"
        ));
        ORDERS.enqueue(
            new MockResponse().setResponseCode(503)
        );
        RECOMMENDATIONS.enqueue(json(
            "{\"items\":[\"book\"]}"
        ));

        client.get()
            .uri("/api/dashboard/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.customerName").isEqualTo("An")
            .jsonPath("$.orderCount").isEqualTo(0)
            .jsonPath("$.recommendations[0]").isEqualTo("book");

        assertEquals(
            "/customers/42",
            CUSTOMER.takeRequest().getPath()
        );
        assertEquals(
            "/orders/summary/42",
            ORDERS.takeRequest().getPath()
        );
        assertEquals(
            "/recommendations/42",
            RECOMMENDATIONS.takeRequest().getPath()
        );
    }

    @Test
    void requiredCustomerFailureReturnsBadGateway()
            throws Exception {

        CUSTOMER.enqueue(
            new MockResponse().setResponseCode(503)
        );
        ORDERS.enqueue(json(
            "{\"orderCount\":3,\"totalSpend\":125.50}"
        ));
        RECOMMENDATIONS.enqueue(json(
            "{\"items\":[\"book\"]}"
        ));

        client.get()
            .uri("/api/dashboard/42")
            .exchange()
            .expectStatus().isBadGateway()
            .expectBody()
            .jsonPath("$.code")
            .isEqualTo("REQUIRED_DEPENDENCY_UNAVAILABLE")
            .jsonPath("$.dependency")
            .isEqualTo("customer");
    }
}
~~~

The tests use three separate MockWebServer instances so each dependency has an independent response queue. They verify:

- All three services return data: the API combines them into a complete dashboard.
- Orders returns 503: the API uses the fallback for the optional branch and still returns customer and recommendations.
- Customer returns 503: the API returns 502 because the required branch failed.

WebTestClient calls the real WebFlux server on a random port; MockWebServer only plays the role of downstreams. No Internet access or installation of three separate business services is needed.

### 12.12. Running Tests and the Application

Run tests using the Gradle wrapper:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

If there is no wrapper yet and a compatible Gradle version is installed:

~~~bash
gradle test
~~~

Run the application:

~~~bash
./gradlew bootRun
~~~

Main endpoint:

~~~http
GET http://localhost:8080/api/dashboard/42
~~~

The downstream URLs are configured in application.properties. To run the demo manually, start three compatible HTTP services on ports 8081, 8082, and 8083, or change the base URLs to your mock/staging environment.

## 13. Design Variations

### 13.1. All Downstreams Required

If all sources are required, with no fallbacks:

~~~java
return Mono.zip(
    loadCustomer(id),
    loadOrders(id),
    loadRecommendations(id)
).map(this::combine);
~~~

A failure in any source causes the aggregation to fail. Map errors into consistent API statuses and error codes.

### 13.2. All Downstreams Optional

If the response can exist with empty data, each source should have an explicit default:

~~~java
Mono<OrderSummary> orders =
    loadOrders(id).defaultIfEmpty(OrderSummary.empty());

Mono<RecommendationResponse> recommendations =
    loadRecommendations(id)
        .defaultIfEmpty(RecommendationResponse.empty());
~~~

defaultIfEmpty only handles empty completion; it does not handle errors. To fall back on errors, add onErrorResume with a specific policy.

### 13.3. Returning Partial Results with Degraded Status

A model can include:

~~~java
record DashboardView(
    String customerName,
    OrderSummary orders,
    RecommendationResponse recommendations,
    List<String> degradedDependencies
) {}
~~~

Each optional branch can return a wrapper containing data and source status. This helps the client distinguish "no orders" from "Order Service did not respond".

### 13.4. A Source Returning Flux

If a service returns an event stream, do not coerce it into a Mono by arbitrarily taking the first element. Choose:

- collectList if the list is small and bounded.
- take(n) if only the first n elements are needed.
- Stream the response directly if the client also consumes streaming.
- Bounded window/buffer if grouping data is needed.

### 13.5. Dynamic Fan-Out by List

~~~java
Flux<ProductView> result = Flux.fromIterable(productIds)
    .flatMap(this::loadProduct, 12);
~~~

The limit 12 is an example. If the list comes from the client, validate the maximum number of items before fanning out. Do not let a single request open thousands of downstream connections.

## 14. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling independent sources in a flatMap chain | Latency near the sum of downstream times | Use Mono.zip when there is no dependency |
| Using zip for Mono<Void> | Combine function never runs because there is no item | Use Mono.when for completion |
| Not handling Mono.empty | Zip completes empty, no dashboard produced | switchIfEmpty/defaultIfEmpty per contract |
| Falling back on every exception | Hides schema errors, auth issues, or bugs | Only fall back on classified error groups |
| Treating all downstreams as optional | API may return wrong/fabricated data | Classify required and optional |
| Not setting timeouts | Requests can hold resources for too long | Per-dependency timeout and overall deadline |
| Unbounded retries | Retry storms and downstream overload | Backoff, jitter, attempt limit, deadline |
| Retrying non-idempotent POST | Creates duplicate side effects | Idempotency key or do not retry |
| Using unbounded flatMap | Excessive fan-out, pool exhaustion | Bound concurrency |
| Using concat for independent sources | Fails to take advantage of parallel wait time | Merge/zip per contract |
| Using merge while assuming order | Unstable response/event ordering | Use concat or flatMapSequential when needed |
| Calling subscribe manually inside a service | Loses request lifecycle and cancellation | Return Mono/Flux to the caller |
| Calling block in a controller | Blocks the event loop | Keep the pipeline reactive |
| Not propagating cancellation | Downstreams keep running after caller leaves | Do not detach subscription; clean up by lifecycle |
| Increasing connection pool indefinitely | Increases sockets/memory and downstream pressure | Capacity plan and bound concurrency |
| Merging multiple snapshots without evaluating | Response contains data skewed across points in time | Snapshot/version or clear eventual consistency |
| Not observing each dependency | Hard to tell which service slows aggregation down | Separate metrics/spans per downstream |
| Putting IDs/tokens in metric tags | High cardinality and data leakage | Use stable tags, mask sensitive data |

## 15. Aggregation Flow Review Checklist

1. **Dependency graph:** which downstreams are independent, and which branches depend on prior results?
2. **Required/optional:** which services are required to produce a valid response?
3. **Operator:** are zip, flatMap, merge, concat, or when used with the right semantics?
4. **Empty:** can each Mono be empty and what is the policy?
5. **Error:** are 4xx, 5xx, network errors, and decode errors classified?
6. **Fallback:** is it applied only to optional branches and allowed error categories?
7. **Timeout:** are there per-dependency timeouts and an overall deadline?
8. **Retry:** are attempt counts, backoff, filter, and idempotency clear?
9. **Concurrency:** is dynamic fan-out bounded?
10. **Backpressure:** are stream/buffer/prefetch bounded?
11. **Cancellation:** does caller disconnect stop unnecessary requests?
12. **Consistency:** do the sources need a shared snapshot?
13. **Observability:** are there per-dependency latency/error/fallback metrics?
14. **Security:** are outbound credentials, TLS, and secrets properly managed?
15. **Tests:** are success, optional failure, required failure, timeout, and empty response covered?
16. **Contract:** does a partial response clearly represent degraded state to the client?

**Remember:** Use Mono.zip for multiple independent sources returning a single value; use flatMap when a subsequent request needs the previous result; use merge when combining streams in arrival order and concat when sequential order must be preserved. Classify required/optional before writing fallbacks. Set individual timeouts and an overall deadline, retry only transient retryable errors, bound fan-out, and let cancellation/backpressure flow all the way through. A good aggregation API is both fast when all sources are healthy and deliberate when returning errors or partial responses if a downstream fails.

## References

- Spring Framework — WebClient retrieve(), bodyToMono(), bodyToFlux() and onStatus: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework — WebClient configuration and builder: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Reactor Core — Mono.zip and zipDelayError API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Core — Reference Guide, error handling, timeout and retry: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Reactor Core — Reference Guide, flatMap, merge, concat and backpressure: https://projectreactor.io/docs/core/release/reference/
- Spring Boot 3.5 — WebFlux and WebClient configuration: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- OkHttp MockWebServer — API and usage: https://github.com/square/okhttp/tree/master/mockwebserver
