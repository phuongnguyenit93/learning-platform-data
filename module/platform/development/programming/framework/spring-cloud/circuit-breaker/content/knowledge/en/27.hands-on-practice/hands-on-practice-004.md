# Protecting Blocking Calls and WebClient Flows with the Same Business Goal

## Practice Objectives

A Spring Cloud application needs to fetch product information from `catalog-service`. There are two common ways to implement this: synchronous HTTP calls with `RestTemplate`, or building a reactive pipeline with `WebClient`. Both approaches must achieve the same business goal: retrieve product data when the dependency is healthy, respond meaningfully when the dependency fails, and prevent new requests from continuing to pile onto a degrading service.

In this practice, we build two independent call paths for the same product lookup use case. The blocking path uses `CircuitBreakerFactory`; the reactive path uses `ReactiveCircuitBreakerFactory`. Each path has timeouts tailored to its HTTP client, a fallback with identical semantics, and its own metrics.

Upon completion, you should be able to distinguish:

- How to wrap a Circuit Breaker around a synchronous supplier versus a `Mono` publisher.
- Why `CircuitBreakerFactory` and `ReactiveCircuitBreakerFactory` are two separate APIs.
- How to place timeouts on the HTTP client or within the reactive pipeline.
- How to preserve the same response contract whether the implementation is blocking or reactive.
- How to test `CLOSED`, `OPEN`, and `HALF_OPEN` states and verify that the fallback does not hide dependency errors.

## Business Model and Contract

Both implementations query the same endpoint `GET /products/{id}` on `catalog-service`:

```text
                    Product API
                         |
              Choose one implementation
                    /          \
                   /            \
           Blocking path      Reactive path
           RestTemplate       WebClient
                |                 |
       CircuitBreakerFactory  ReactiveCircuitBreakerFactory
                |                 |
                +--------+--------+
                         |
                   catalog-service
```

The return contract shares a single `ProductView` type with three states:

| State | Meaning |
| --- | --- |
| `CURRENT` | Current data was retrieved from catalog. |
| `UNAVAILABLE` | Data could not be retrieved due to dependency failure or Circuit Breaker rejection. |
| `NOT_FOUND` | Catalog confirmed the product does not exist, if the API models this case in the business contract. |

Do not return quantity 0, price 0, or an empty object when the call fails. Those values can be mistaken for real data. The `UNAVAILABLE` fallback must be clearly distinct from `NOT_FOUND`.

The two implementations are alternatives for the same use case. Within a single business request, invoke only the one path appropriate for the application's stack. Do not call both blocking and reactive just to "try both," as doing so creates two requests to the dependency and can multiply load during an outage.

## 1. Declare Dependencies and Choose the Stack

Manage Spring Boot and Spring Cloud versions using compatible BOMs. With Resilience4j, an application using the blocking path needs the imperative Spring Cloud Circuit Breaker provider; a WebFlux path needs the Reactor provider:

```xml
<dependencies>
    <!-- Choose the dependency based on the application's stack. -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

    <!-- Add only when the application actually uses a WebFlux/Reactor pipeline. -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>
</dependencies>
```

If a project only uses MVC and `RestTemplate`, only the imperative provider is needed. If a project only uses WebFlux and `WebClient`, use the reactive provider. If an application genuinely needs both APIs, check the runtime dependency graph and auto-configuration for the exact release train to confirm both factories are created without conflicts. Do not add both starters mechanically.

Gateway/starter artifact names and auto-configuration conditions can vary by release train. Let the Spring Cloud BOM manage starter versions; do not override Spring Cloud Circuit Breaker or Resilience4j individually without verifying the compatibility matrix.

## 2. Create Shared Data Types

Both call paths share the response domain types. The example uses records; if the application runs on an older Java version, you can substitute standard immutable classes:

```java
public record Product(String id, String name, long priceInCents) {}

public enum ProductState {
    CURRENT,
    UNAVAILABLE,
    NOT_FOUND
}

public record ProductView(
    String id,
    String name,
    Long priceInCents,
    ProductState state
) {
    public static ProductView current(Product product) {
        return new ProductView(
            product.id(), product.name(), product.priceInCents(),
            ProductState.CURRENT
        );
    }

    public static ProductView unavailable(String id) {
        return new ProductView(id, null, null, ProductState.UNAVAILABLE);
    }

    public static ProductView notFound(String id) {
        return new ProductView(id, null, null, ProductState.NOT_FOUND);
    }
}
```

`priceInCents` is a `Long` so the unavailable state is not represented as price 0. In a real API, a separate response DTO can be used, while keeping the same semantics across both implementations so clients do not have to interpret two different error models.

Input validation should happen before the Circuit Breaker boundary. For example, if `productId` is blank, return a validation error immediately; do not record that local error as a `catalog-service` failure.

## 3. Configure the Circuit Breaker with Two IDs

Use two stable IDs to track each execution path:

- `catalogBlocking` for the synchronous call.
- `catalogReactive` for the WebClient publisher.

Example `application.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogBlocking:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 2

      catalogReactive:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 2
```

Both configurations use the same thresholds to compare behavior. Separate names help dashboards distinguish the two execution paths. However, these two IDs create two independent Circuit Breaker states; they do not share a sliding window or state just because they point to the same backend. If both paths run in the same application and send load to catalog concurrently, account for their combined traffic when budgeting concurrency.

If you want both paths to share a single breaker state, you need a design/provider that explicitly supports the same registry and the same instance. Do not assume the imperative and reactive factories automatically share state. In this practice, separate IDs are used for observability and to avoid mixing the two call paths.

## 4. Blocking Path with RestTemplate

### Configure HTTP Client Timeouts

For blocking calls, timeouts should be configured directly on the HTTP client. Example using `RestTemplateBuilder`:

```java
import java.time.Duration;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
public class BlockingHttpConfiguration {

    @Bean
    RestTemplate catalogRestTemplate(RestTemplateBuilder builder) {
        return builder
            .setConnectTimeout(Duration.ofMillis(300))
            .setReadTimeout(Duration.ofSeconds(2))
            .build();
    }
}
```

Connect timeout bounds connection establishment time; read timeout bounds waiting for response data according to the semantics of the request factory in use. This is not necessarily the overall business operation deadline. If an overall deadline is needed, manage it additionally at the calling layer and make sure it aligns with the client timeouts.

### Wrap the Call with CircuitBreakerFactory

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestTemplate;

@Service
public class BlockingProductService {
    private final RestTemplate catalogRestTemplate;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public BlockingProductService(
            RestTemplate catalogRestTemplate,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.catalogRestTemplate = catalogRestTemplate;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public ProductView find(String productId) {
        validate(productId);

        return circuitBreakerFactory.create("catalogBlocking").run(
            () -> {
                try {
                    Product product = catalogRestTemplate.getForObject(
                        "http://catalog-service/products/{id}",
                        Product.class,
                        productId
                    );
                    if (product == null) {
                        throw new IllegalStateException("Catalog returned an empty body");
                    }
                    return ProductView.current(product);
                } catch (HttpClientErrorException.NotFound notFound) {
                    return ProductView.notFound(productId);
                }
            },
            error -> ProductView.unavailable(productId)
        );
    }

    private void validate(String productId) {
        if (productId == null || productId.isBlank()) {
            throw new IllegalArgumentException("productId is required");
        }
    }
}
```

In this example, HTTP 404 is translated into the business result `NOT_FOUND`, not the unavailable fallback. Connection errors, timeouts, and 5xx server errors propagate out of the supplier so the Circuit Breaker can classify them. The fallback only produces the `UNAVAILABLE` state.

`RestTemplate` converts 4xx/5xx responses into exceptions by default. If you swap the error handler or HTTP client, re-verify status mapping to avoid accidentally turning a 503 into a normal response. For real systems, the base URL should come from configuration or service discovery rather than being hard-coded.

## 5. Reactive Path with WebClient

### Configure WebClient

WebClient typically uses Reactor Netty. Configure connect/response timeouts on the HTTP client and add a timeout in the pipeline if you need to bound total publisher completion time:

```java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class ReactiveHttpConfiguration {

    @Bean
    WebClient catalogWebClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
            .responseTimeout(Duration.ofSeconds(2));

        return builder
            .baseUrl("http://catalog-service")
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
```

Reactor Netty timeouts bound network phases according to client configuration. You can add `Mono.timeout(...)` to impose a time limit on the composite pipeline. Both timeout layers must be coordinated; do not configure conflicting values that cancel requests prematurely or wait longer than the business deadline.

### Wrap the Publisher with ReactiveCircuitBreakerFactory

```java
import java.time.Duration;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

@Service
public class ReactiveProductService {
    private final WebClient catalogWebClient;
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public ReactiveProductService(
            WebClient catalogWebClient,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.catalogWebClient = catalogWebClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public Mono<ProductView> find(String productId) {
        if (productId == null || productId.isBlank()) {
            return Mono.error(new IllegalArgumentException("productId is required"));
        }

        Mono<ProductView> primary = Mono.defer(() ->
            catalogWebClient.get()
                .uri("/products/{id}", productId)
                .retrieve()
                .onStatus(
                    status -> status.value() == 404,
                    response -> response.createException()
                )
                .bodyToMono(Product.class)
                .timeout(Duration.ofSeconds(2))
                .map(ProductView::current)
                .onErrorResume(
                    WebClientResponseException.NotFound.class,
                    error -> Mono.just(ProductView.notFound(productId))
                )
        );

        return circuitBreakerFactory.create("catalogReactive").run(
            primary,
            error -> Mono.just(ProductView.unavailable(productId))
        );
    }
}
```

`Mono.defer` defers request creation until subscription. `ReactiveCircuitBreakerFactory` wraps the publisher and accepts a fallback publisher. When the HTTP client emits a connection error, timeout, or server error, the integration can record it according to the Circuit Breaker policy and switch to the fallback.

In this example, 404 is mapped to `NOT_FOUND`; remaining errors can route to the `UNAVAILABLE` fallback. Verify the exact exception type and how `onStatus` behaves in the Spring WebFlux version you are using. If you need the Circuit Breaker to record 404 as a failure, do not convert it into a domain result inside the publisher before the breaker observes it.

Do not call `block()` or `subscribe()` manually inside this service. Return the `Mono` to the controller so WebFlux manages subscription, cancellation, and error handling across the request lifecycle.

## 6. Comparing the Protection Boundaries

| Aspect | Blocking | Reactive |
| --- | --- | --- |
| HTTP client | `RestTemplate` | `WebClient` |
| Factory | `CircuitBreakerFactory` | `ReactiveCircuitBreakerFactory` |
| Return type | `ProductView` | `Mono<ProductView>` |
| Supplier | Synchronous `Supplier<T>` | `Mono<T>` subscribed later |
| Primary timeout | HTTP client connect/read timeout | Reactor Netty timeout and/or `Mono.timeout` |
| Fallback | Function returning `ProductView` | Function returning `Mono<ProductView>` |
| Threading | Calling thread waits for HTTP result | Non-blocking pipeline, does not block event loop |

The commonality is that the Circuit Breaker wraps the dependency call and the fallback preserves the same business semantics. The difference is that a blocking call executes immediately inside the supplier when invoked; a reactive call executes when the publisher is subscribed to. Therefore, with reactive calls you must control subscriptions to avoid sending duplicate requests.

## 7. Configuring Error Classification

Not every exception signals dependency degradation. Invalid input validation is a caller error; 404 can be a valid business outcome; timeouts, connection failures, and 5xx responses are usually signals that should be recorded.

With Resilience4j, you can configure an instance to ignore specific business errors. The example below only illustrates classification for a dependency; verify the actual HTTP client exception types:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogBlocking:
        ignoreExceptions:
          - com.example.catalog.InvalidProductRequestException
      catalogReactive:
        ignoreExceptions:
          - com.example.catalog.InvalidProductRequestException
```

Do not ignore broad types such as `RuntimeException`, `RestClientException`, or `WebClientResponseException`; these wide hierarchies can include connection errors and server errors that must be recorded. Likewise, do not treat every HTTP 4xx as an infrastructure failure. If 429 indicates the dependency is overloaded, consider classifying it as a failure; if 404 means the product does not exist, map it to `NOT_FOUND` per the API contract.

If an error is wrapped inside a `CompletionException` or a client wrapper, inspect the cause before defining predicates. Exception configuration for imperative and reactive factories may need to be applied through their respective provider mechanisms; verify instance names and runtime behavior instead of assuming a single customizer applies to both factories.

## 8. Do Not Let Fallbacks Hide Outages

Fallbacks preserve user experience, but they can make the final response look successful. Therefore, measure separately:

- Number of blocking and reactive calls.
- Number of times the primary supplier/publisher started executing.
- Number of timeouts, connection failures, HTTP 5xx responses, and ignored errors.
- Number of Circuit Breaker rejections while `OPEN`.
- Number of fallback invocations and number of times the fallback itself failed.
- Latency of the primary path and latency of the fallback.

Use the breaker ID as a bounded tag, such as `catalogBlocking` and `catalogReactive`. Do not put product IDs, user IDs, full URLs, or exception messages into metric tags. High-cardinality values belong in logs or distributed traces.

The two breakers in the example maintain separate states. If `catalogBlocking` opens while `catalogReactive` stays closed, that is not necessarily a bug; the two paths may have different traffic or error histories. Dashboards should display each ID separately while also aggregating actual backend requests to assess total load.

## 9. Testing the Blocking Path

Use a mock HTTP server or WireMock to control catalog responses. For the blocking service, verify:

| Scenario | Expected result |
| --- | --- |
| Catalog returns 200 | Returns `ProductView` with `CURRENT` state. |
| Catalog returns 404 | Returns `NOT_FOUND` state per business mapping. |
| Catalog returns 503 | Circuit Breaker records failure and fallback returns `UNAVAILABLE`. |
| Connection refused | HTTP client throws transport error; fallback is invoked. |
| Read timeout | Supplier ends within timeout limit; breaker records according to config. |
| Breaker `OPEN` | Supplier does not invoke HTTP client; fallback returns `UNAVAILABLE`. |
| Probe in `HALF_OPEN` succeeds | Breaker can return to `CLOSED` after enough trial outcomes. |

To verify that the breaker opens, generate enough outcomes according to `minimumNumberOfCalls` and `slidingWindowSize`. Do not make a single call and expect `OPEN` if the configuration requires multiple samples.

## 10. Testing the Reactive Path

With `WebClient`, use a mock server and `StepVerifier` to verify publisher signals:

```java
StepVerifier.create(reactiveProductService.find("p-100"))
    .expectNextMatches(view -> view.state() == ProductState.CURRENT)
    .verifyComplete();
```

Also verify these cases:

- A 404 response is mapped to `NOT_FOUND`.
- A 503 response or connection error routes to the `UNAVAILABLE` fallback.
- A timeout emitted inside the publisher is observed by the Circuit Breaker as configured.
- When the breaker is `OPEN`, no new HTTP requests reach the mock server and the fallback is emitted.
- A single subscription produces exactly one request; `subscribe()` is not called inside the service.
- Cancelling a subscription releases resources according to WebClient and operator semantics.

If using `Mono.defer`, each subscription can create a new request. Do not subscribe to the same publisher multiple times when the business flow only intends one call. Count requests at the mock server to catch duplicate calls; Java method call counts alone are not enough to prove network request counts.

## 11. Testing the Same Business Goal

Write contract tests using the same set of cases for both implementations. You can create a shared test interface or test suite to confirm that both blocking and reactive paths return identical semantics:

| Input from catalog | Blocking result | Reactive result |
| --- | --- | --- |
| HTTP 200 with valid product | `CURRENT` | `CURRENT` |
| HTTP 404 | `NOT_FOUND` | `NOT_FOUND` |
| HTTP 503 | `UNAVAILABLE` after fallback | `UNAVAILABLE` after fallback |
| Connection timeout | `UNAVAILABLE` after fallback | `UNAVAILABLE` after fallback |
| Circuit Breaker `OPEN` | `UNAVAILABLE`, backend not called | `UNAVAILABLE`, backend request not subscribed |

The two paths must align on the domain response, though they do not have to share Circuit Breaker state. If tests compare breaker states, check `catalogBlocking` and `catalogReactive` separately. If comparing total request counts, reset the mock server and metrics between tests so earlier test outcomes do not affect subsequent tests.

## 12. Choosing the Appropriate Execution Model

Blocking calls suit synchronous MVC services or legacy libraries without reactive APIs. They are easy to read and integrate with synchronous code, though each waiting request typically holds a thread. Thread pools, connection pools, and timeouts must be bounded.

WebClient suits WebFlux or scenarios requiring a non-blocking pipeline. It does not automatically grant infinite concurrency; you still need to bound connections, concurrency, queues, and processing time. Do not migrate a blocking API to WebClient by calling `block()` and assume it has become reactive.

Do not use both implementations simultaneously for a single request as backups for each other. If you want to shift traffic between the two execution models, decide at the routing or deployment layer and monitor total load. Likewise, never have a single request execute a blocking call first and then a reactive call on failure; that multiplies latency and dependency load.

## 13. Complete Practice Workflow

1. Create a shared `ProductView` DTO/domain model with `CURRENT`, `NOT_FOUND`, and `UNAVAILABLE` states.
2. Configure timeouts for `RestTemplate` and `WebClient` according to business deadlines.
3. Configure two separate Circuit Breaker IDs and test thresholds in Resilience4j.
4. Implement the blocking path using `CircuitBreakerFactory.create("catalogBlocking").run(...)`.
5. Implement the reactive path using `ReactiveCircuitBreakerFactory.create("catalogReactive").run(...)`.
6. Keep validation outside the protected boundary and place only the dependency call inside the supplier/publisher.
7. Map 404 to `NOT_FOUND`; let timeouts, connection errors, and 5xx be classified by policy; have fallback return `UNAVAILABLE`.
8. Test success, not found, 5xx, connection failure, timeout, `OPEN`, and `HALF_OPEN` for both paths.
9. Count actual requests reaching the mock server to confirm the reactive publisher is not subscribed multiple times.
10. Cross-check metrics by breaker ID and verify that fallback does not mask dependency failures.

## Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using imperative factory to wrap a `Mono` | Publisher is not protected with reactive semantics. | Use `ReactiveCircuitBreakerFactory`. |
| Using reactive factory for a blocking supplier | May block the event loop or violate the execution model. | Use the imperative factory for synchronous calls. |
| Not setting HTTP client timeouts | Threads or subscriptions hold resources for too long. | Set connect/read/response timeouts and an overall deadline. |
| Placing fallback before the Circuit Breaker | Breaker may see a success result and fail to increase failure rate. | Place fallback outside the operator or use the factory's fallback function. |
| Treating 404 as an infrastructure error | Circuit Breaker opens because products do not exist. | Map 404 according to the domain contract. |
| Subscribing multiple times to a cold publisher | One business action generates multiple HTTP requests. | Keep a single subscription per request lifecycle and verify with a mock server. |
| Calling both blocking and reactive for one request | Doubles load and latency. | Choose one execution path per request. |
| Assuming both factories share state automatically | Metrics and state are misinterpreted. | Use separate IDs and inspect each factory/instance. |
| Checking only the final response | Fallback hides dependency incidents. | Measure primary, fallback, and state transitions separately. |

## Expected Outcome

Both implementations must serve the same business contract while preserving the characteristics of their respective execution models. The blocking path uses `CircuitBreakerFactory` and synchronous HTTP client timeouts; the reactive path uses `ReactiveCircuitBreakerFactory`, a `Mono` publisher, and pipeline/client timeouts. Both classify errors consistently, return a meaningful `UNAVAILABLE` fallback, and are observed under separate IDs. Once you have tested success, not found, timeout, fallback, and `OPEN`/`HALF_OPEN` states, you can demonstrate that the dependency is protected without distorting response semantics or accidentally sending duplicate requests.
