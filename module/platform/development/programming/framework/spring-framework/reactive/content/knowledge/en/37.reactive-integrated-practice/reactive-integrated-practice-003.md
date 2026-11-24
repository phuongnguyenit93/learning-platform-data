# Handling Empty Results, Per-Service Errors, and Fallbacks in Reactor

An aggregation API often calls multiple sources: catalog, inventory, pricing, recommendations, profile, or other microservices. Each source can return data, find nothing, emit an error, or miss its deadline. In a reactive pipeline, these situations have distinct semantics. Treating an empty result as an error, or catching all errors and returning default data, can cause the API to mask outages and produce responses that look successful while conveying the wrong meaning.

Reactor distinguishes three states: a publisher that emits a value and completes, a publisher that completes without emitting a value, and a publisher that terminates with an error. Operators such as defaultIfEmpty, switchIfEmpty, onErrorResume, timeout, retryWhen, and zip help define a policy for each source. What matters is choosing the right scope: a supporting service can be replaced with fallback data while a required service must still cause the request to fail.

This lesson belongs to the **Integrated Practice** group of the Spring Framework - reactive module. It progresses from Mono/Flux semantics to multi-service aggregation strategies, partial responses, timeout/retry/fallback, a complete Spring Boot WebFlux example, and testing with StepVerifier and WebTestClient.

## 1. Learning Objectives

After this lesson, you can:

- Distinguish a Mono with a value, Mono.empty(), and Mono.error().
- Understand Flux.empty(), next(), single(), and collectList() when a source emits no elements.
- Use defaultIfEmpty() for simple default values.
- Use switchIfEmpty() to switch to a fallback publisher.
- Use Mono.defer() to defer fallback creation.
- Distinguish empty handling from error handling.
- Use onErrorReturn(), onErrorResume(), onErrorMap(), and doOnError() for their intended purposes.
- Understand why Mono.zip() emits no result if one source is empty.
- Know that zipDelayError() delays errors but does not turn empty into a value.
- Normalize required and optional sources before calling zip.
- Design partial results with AVAILABLE, EMPTY, or FALLBACK status.
- Place timeouts and retries before fallbacks according to policy.
- Fall back only on recoverable errors.
- Control cancellation and concurrent calls when one source fails.
- Integrate multiple downstreams with WebClient while preserving reactive composition.
- Write an aggregation service and test success, empty, error, timeout, and not-found cases.

## 2. Three Fundamental States of a Publisher

A Mono<T> can terminate in three ways:

| State | Signal | Meaning |
| --- | --- | --- |
| With value | onNext(value), onComplete | Data is present |
| Empty | onComplete, no onNext | No result |
| Error | onError(error) | Did not complete successfully |

~~~java
Mono<String> found = Mono.just("product-1");
Mono<String> missing = Mono.empty();
Mono<String> failed = Mono.error(
    new IllegalStateException("catalog unavailable"));
~~~

The three publishers are not equivalent:

- found emits one String.
- missing completes normally without emitting a String.
- failed terminates with an error.

Empty is not necessarily an error. Looking up a nonexistent product can be a normal outcome at the repository layer; the business service then decides whether to translate it into a 404. Conversely, a catalog timeout is usually an infrastructure error and needs its own policy.

Suppose a product page aggregates catalog, inventory, and recommendation data. Catalog not finding the product means the page does not exist. Inventory having no record may mean quantities have not been synced yet and the UI should show "unknown." A recommendation failure may not affect viewing the product; the page can still render with an empty recommendation list and a fallback status.

## 3. Empty in Mono and Flux

### Mono.empty()

Mono.empty() emits onComplete without onNext:

~~~java
Mono<String> result = Mono.empty();

Mono<Integer> length = Mono.<String>empty()
    .map(String::length);
~~~

length also completes empty. map and flatMap require a value to invoke the mapper; with no element, the mapper does not run.

### Flux.empty()

Flux.empty() also completes without emitting any elements:

~~~java
Flux<String> names = Flux.empty();
~~~

Per-element operators such as map, filter, and flatMap are not invoked because there are no input elements.

### next() and single()

Flux.next() takes the first element as a Mono. If the Flux is empty, the resulting Mono is also empty:

~~~java
Mono<String> first = Flux.<String>empty().next();
~~~

single() requires exactly one element; if the source is empty or has more than one element, it emits an error. singleOrEmpty() allows zero or one element, but still errors if there is more than one.

### collectList() Has Different Semantics

~~~java
Mono<List<String>> list = Flux.<String>empty()
    .collectList();
~~~

The result is a Mono emitting an empty List and completing, not Mono.empty(). Therefore, Mono<Recommendation> can be empty when there is no recommendation, whereas Flux<Recommendation>.collectList() typically emits List.of() when there are no recommendations.

## 4. defaultIfEmpty(): Replacing Empty with a Value

defaultIfEmpty(T) emits a fallback value if the upstream completes empty:

~~~java
Mono<String> name = repository.findName("p-404")
    .defaultIfEmpty("Unknown product");
~~~

If the repository emits "Notebook", the result remains "Notebook". If the repository is empty, the result is "Unknown product".

Use defaultIfEmpty when the fallback is a known, cheap value that does not require invoking another publisher:

~~~java
Mono<Integer> stock = inventory.findAvailable("p-1")
    .defaultIfEmpty(0);
~~~

Be careful, however: 0 can mean "confirmed out of stock," whereas empty can mean "no inventory record exists." If the two meanings differ, use a stateful model instead of blindly replacing empty with 0.

defaultIfEmpty does not handle errors:

~~~java
Mono<String> result = Mono.<String>error(
        new IllegalStateException("network failed"))
    .defaultIfEmpty("fallback");
~~~

The publisher still emits an error. defaultIfEmpty handles only onComplete without onNext, not onError. Reactor also disallows Mono.just(null) or defaultIfEmpty(null); if the domain needs to represent the absence of a value, use Optional or a status record.

## 5. switchIfEmpty(): Switching to a Fallback Publisher

switchIfEmpty(Publisher<T>) subscribes to an alternative publisher if the original source completes empty:

~~~java
Mono<Product> product = cache.findById(id)
    .switchIfEmpty(database.findById(id));
~~~

Flow:

~~~text
cache.findById(id)
      |
      +-- has product --------> emit product
      |
      +-- empty --------------> subscribe database.findById(id)
                                   |
                                   +-- has product -> emit product
                                   +-- empty -> empty
                                   +-- error -> error
~~~

This is the cache-aside pattern: a cache miss falls back to the database. If the cache emits an error, switchIfEmpty does not run; you must decide separately whether cache errors should fall back to the database.

~~~java
Mono<Product> product = cache.findById(id)
    .onErrorResume(
        CacheUnavailableException.class,
        error -> Mono.empty())
    .switchIfEmpty(
        Mono.defer(() -> database.findById(id)));
~~~

This snippet intentionally treats a cache outage as a cache miss. That policy only makes sense if the database is the source of truth and the cache is merely an optimization. Log/record metrics for cache errors so outages are not hidden.

### Using Mono.defer() to Defer Fallback Creation

If database.findById(id) has synchronous side effects as soon as the method is called, the publisher could be constructed even when the cache has data. To ensure the fallback is only created when needed:

~~~java
Mono<Product> product = cache.findById(id)
    .switchIfEmpty(
        Mono.defer(() -> database.findById(id)));
~~~

Mono.defer invokes the supplier when the fallback is subscribed. It also turns synchronous exceptions thrown during method invocation into onError inside the reactive chain.

Defer does not defer an already-constructed publisher:

~~~java
Mono<Product> alreadyBuilt = database.findById(id);

Mono<Product> wrong = cache.findById(id)
    .switchIfEmpty(Mono.defer(() -> alreadyBuilt));
~~~

Here the supplier still returns a pre-built publisher. Place the gateway call inside the supplier.

## 6. Turning Empty into an Error for Required Sources

Some sources are required. For example, catalog must have a product before a detail page can be built. The repository can return Mono.empty(), but the service should turn it into a domain error:

~~~java
Mono<Product> requiredProduct =
    catalog.findById(id)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(id)));
~~~

This makes semantics clear:

- Catalog has the product: continue.
- Catalog is empty: ProductNotFoundException.
- Catalog errors: the error is preserved or mapped per policy.

Do not use defaultIfEmpty(new Product(...)) if a missing product must return 404. Fake data causes the API to render a nonexistent resource.

The controller can map the domain error:

~~~java
@ExceptionHandler(ProductNotFoundException.class)
public ResponseEntity<ApiError> notFound(
        ProductNotFoundException error) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND)
        .body(new ApiError("PRODUCT_NOT_FOUND", error.getMessage()));
}
~~~

This is a controller fragment; the complete sample section below has full code and HTTP tests.

## 7. onErrorReturn(): Falling Back to a Fixed Value

onErrorReturn(T) replaces an error with a static value:

~~~java
Mono<ExchangeRate> rate = exchangeGateway.getRate("USD", "VND")
    .onErrorReturn(ExchangeRate.unavailable());
~~~

It is simple, but has a drawback: it does not distinguish timeouts, authentication, validation, or programming errors if you use the overload that catches every Throwable. Use the typed overload when you only want to handle a specific category:

~~~java
Mono<ExchangeRate> rate = exchangeGateway.getRate("USD", "VND")
    .onErrorReturn(
        DownstreamUnavailableException.class,
        ExchangeRate.unavailable());
~~~

Do not fall back all errors to a default value if a 401, 403, or mapping error needs separate handling.

## 8. onErrorResume(): Switching Errors to Another Publisher

onErrorResume allows choosing an alternative publisher based on the exception:

~~~java
Mono<Profile> profile = profileClient.find(userId)
    .onErrorResume(
        ProfileServiceUnavailableException.class,
        error -> profileCache.find(userId));
~~~

The fallback can call a cache, database, or another service.

~~~java
// Fallback for all errors.
source.onErrorResume(error -> fallback());

// Fallback only for one error type.
source.onErrorResume(
    TimeoutException.class,
    error -> cachedValue());

// Fallback by predicate.
source.onErrorResume(
    this::isRecoverable,
    error -> fallback());
~~~

Select only recoverable errors. For example, a recommendation timeout may allow returning an empty list; an IllegalArgumentException caused by buggy caller code should not be turned into "no recommendations."

onErrorResume does not handle empty:

~~~java
Mono<String> value = Mono.<String>empty()
    .onErrorResume(error -> Mono.just("fallback"));
~~~

value remains empty. To handle empty, add switchIfEmpty or defaultIfEmpty.

### Recording Before Falling Back

~~~java
Mono<Profile> profile = profileClient.find(userId)
    .onErrorResume(
        ProfileServiceUnavailableException.class,
        error -> {
            log.warn("Profile service unavailable; using cache");
            return profileCache.find(userId);
        });
~~~

Do not log raw tokens or sensitive payloads. Log the service name, error category, and controlled trace ID.

## 9. doOnError, onErrorMap, and onErrorComplete

### doOnError(): Observing Errors as a Side Effect

~~~java
Mono<Product> product = catalog.findById(id)
    .doOnError(error ->
        log.error("Catalog lookup failed", error));
~~~

doOnError does not recover. The error still flows downstream.

### onErrorMap(): Translating Error Types

~~~java
Mono<Product> product = catalog.findById(id)
    .onErrorMap(
        WebClientRequestException.class,
        error -> new CatalogUnavailableException(error));
~~~

Use when you need to translate technical errors into domain errors or unified application errors. Preserve the cause for investigation.

### onErrorComplete(): Swallowing Errors into Empty

~~~java
Mono<Recommendation> recommendations =
    recommendationClient.find(id)
        .onErrorComplete();
~~~

It turns an error into an empty completion. This can make the pipeline appear successful and lose cause information. If used, clear logging/metrics are required and it should only apply to truly optional sources. Usually a FALLBACK status record is easier to observe than complete emptiness.

onErrorContinue is not a general-purpose fallback: its semantics depend on upstream operators and can make error flow confusing. For multi-service aggregation, prefer handling errors directly on each publisher with onErrorResume.

## 10. Mono.zip(): Combining Multiple Valued Sources

Mono.zip waits for each source to emit an element, then calls the combinator:

~~~java
Mono<ProductView> view = Mono.zip(
    catalog.findById(id),
    inventory.findByProductId(id),
    recommendations.findByProductId(id),
    ProductView::new);
~~~

If all three sources emit data, ProductView is created. If one source emits an error, zip terminates with that error and can cancel the remaining sources. If one source completes empty, zip completes empty because a full tuple cannot be formed. The combinator is not invoked.

### Dangerous Example

~~~java
Mono<String> name = Mono.just("Notebook");
Mono<Integer> stock = Mono.empty();

Mono<ProductSummary> summary =
    Mono.zip(name, stock, ProductSummary::new);
~~~

summary does not emit ProductSummary; it completes empty.

### Normalizing Sources Before zip

If inventory is optional, convert empty into a section with status:

~~~java
Mono<InventorySection> stock = inventory.findByProductId(id)
    .map(InventorySection::available)
    .switchIfEmpty(Mono.just(
        InventorySection.unknown()));

Mono<ProductSummary> summary =
    Mono.zip(
        catalog.findById(id),
        stock,
        ProductSummary::new);
~~~

If inventory errors are also recoverable:

~~~java
Mono<InventorySection> stock = inventory.findByProductId(id)
    .map(InventorySection::available)
    .switchIfEmpty(Mono.just(InventorySection.unknown()))
    .onErrorResume(
        InventoryUnavailableException.class,
        error -> Mono.just(InventorySection.unavailable()));
~~~

Now stock always emits an InventorySection in one of three states: success, empty, or fallback. ProductSummary can be built whenever the required catalog emits a product.

## 11. zipDelayError(): Delaying Errors Does Not Mean Fallback

Mono.zipDelayError differs from Mono.zip in how it handles errors:

- Mono.zip typically terminates early when one source errors or is empty.
- Mono.zipDelayError delays errors so the remaining sources have a chance to complete.
- If one source is empty, the final result is still empty after the remaining sources finish.
- If multiple sources error, Reactor can combine exceptions as suppressed exceptions.

~~~java
Mono.zipDelayError(
    catalog.findById(id),
    inventory.findByProductId(id),
    ProductView::new);
~~~

zipDelayError does not replace empty with a default value. Nor does it automatically turn an inventory error into a partial result. Use zipDelayError when you need to wait for other sources to finish to observe concurrent errors; use onErrorResume/defaultIfEmpty/switchIfEmpty to define fallbacks.

## 12. Mono<Void> Is Unsuitable as a zip Element

Mono<Void> represents a completion-only operation with no value. Therefore it is always empty to an operator that expects an element:

~~~java
Mono<Void> audit = auditService.record(event);

Mono<Result> wrong = Mono.zip(
    catalog.findById(id),
    audit,
    Result::new);
~~~

The combinator cannot receive a value from audit. Compose the side effect first and then return the needed value:

~~~java
Mono<Product> product = catalog.findById(id)
    .flatMap(found ->
        auditService.record(found)
            .thenReturn(found));
~~~

Or if two independent tasks must run before continuing:

~~~java
Mono<Product> product = catalog.findById(id);
Mono<Void> audit = auditService.recordRequest(id);

Mono<Product> result = product
    .delayUntil(ignored -> audit);
~~~

If you only need to wait for multiple side effects to complete, use Mono.when:

~~~java
Mono<Void> completed = Mono.when(
    auditService.record(event),
    eventBus.publish(event));
~~~

If you need to preserve the business value after side effects:

~~~java
Mono<Order> result = repository.save(order)
    .flatMap(saved ->
        Mono.when(
            auditService.record(saved),
            eventBus.publish(saved))
        .thenReturn(saved));
~~~

## 13. Partial Result Model: Distinguishing EMPTY and FALLBACK

On an aggregation page, some data is required and some is optional.

| Source | Empty | Error | Sample policy |
| --- | --- | --- | --- |
| Catalog | No product | Catalog failure | Empty becomes 404; error propagates or maps to 503 |
| Inventory | No record yet | Timeout/service failure | Return EMPTY or FALLBACK status |
| Recommendations | No recommendations | Service failure | Return empty list with corresponding status |
| Pricing | No price | Pricing failure | Per business rules: block purchase or use verified cached price |
| Reviews | No reviews | Service failure | Can display empty list and fallback status |

A clear model:

~~~java
public enum SectionStatus {
    AVAILABLE,
    EMPTY,
    FALLBACK
}

public record Section<T>(
    SectionStatus status,
    T value,
    String reason) {
}
~~~

Example response:

~~~json
{
  "product": {
    "id": "p-1",
    "name": "Notebook"
  },
  "inventory": {
    "status": "EMPTY",
    "value": {
      "available": 0,
      "known": false
    },
    "reason": null
  },
  "recommendations": {
    "status": "FALLBACK",
    "value": [],
    "reason": "recommendations_unavailable"
  }
}
~~~

The consumer understands that inventory has not been determined, whereas the recommendations list is empty due to a service error. If only 0 and [] were returned without status, the consumer could misinterpret that stock is depleted and no recommendations exist.

Optional<T> can express the presence or absence of a simple value, but it cannot distinguish "no record" from "downstream timed out." If status and reason are needed, use a wrapper record like Section<T>.

## 14. Handling Fallbacks Per Service

A good aggregation places policy directly on each downstream's publisher.

~~~java
Mono<Section<Inventory>> inventorySection =
    inventoryGateway.findByProductId(id)
        .timeout(Duration.ofMillis(300))
        .map(Section::available)
        .switchIfEmpty(Mono.just(
            Section.empty(Inventory.unknown())))
        .onErrorResume(
            this::isRecoverable,
            error -> Mono.just(
                Section.fallback(
                    Inventory.unknown(),
                    safeReason(error))));
~~~

The order matters:

1. Call downstream.
2. timeout limits wait duration.
3. map data into an AVAILABLE section.
4. switchIfEmpty handles empty completion.
5. onErrorResume handles timeouts or recoverable errors.

An error is not handled by switchIfEmpty. An empty is not handled by onErrorResume. Clear policy for both states.

Do not catch all errors:

~~~java
.onErrorResume(error ->
    Mono.just(Section.fallback(defaultValue, "failed")))
~~~

This can hide NullPointerException, mapping errors, or code bugs. It is better to check error instanceof TimeoutException or a specific domain exception, and fall back only for the recoverable category.

## 15. Timeout, Retry, and Fallback: Order Matters

A downstream request can be slow, transiently fail, or complete empty. A typical policy combines timeout, bounded retry, and then fallback.

~~~java
Mono<Inventory> inventory =
    Mono.defer(() -> inventoryGateway.findByProductId(id))
        .timeout(Duration.ofMillis(250))
        .retryWhen(
            Retry.backoff(1, Duration.ofMillis(30))
                .filter(this::isTransient))
        .onErrorResume(
            this::isRecoverable,
            error -> Mono.just(Inventory.unknown()));
~~~

### Why Retry Before Fallback?

If fallback is applied before retry:

~~~java
source
    .onErrorResume(error -> Mono.just(defaultValue))
    .retryWhen(Retry.max(2));
~~~

The error has already been converted into onNext(defaultValue), so retry no longer sees an error to act upon.

Common ordering:

~~~text
Downstream call
      |
      v
Timeout
      |
      v
Retry transient error (bounded)
      |
      v
Fallback recoverable error
      |
      v
Aggregate result
~~~

### Should Empty Be Retried?

Usually no. Empty is a successful completion without a value, not a transient error. retryWhen only handles error signals; it does not retry when a source completes empty.

If empty is a condition that warrants retrying—for example, data may appear after eventual consistency sync—model it with repeatWhenEmpty or a polling policy with a deadline and backoff. Do not use retryWhen because it does not address empty.

### Per-Attempt Timeout vs. Overall Operation Timeout

~~~java
// Each upstream subscription is limited to 250 ms.
source.timeout(Duration.ofMillis(250))
    .retryWhen(retrySpec);
~~~

~~~java
// The entire operation, including retries, is limited to 1 second.
source.retryWhen(retrySpec)
    .timeout(Duration.ofSeconds(1));
~~~

Both can be used together: a per-attempt timeout and an overall deadline. Budget the total time across all downstreams to prevent the aggregate response from exceeding its SLA.

## 16. Fallbacks Must Be Marked and Observed

Fallbacks should not masquerade as successful data.

Misleading example:

~~~java
Mono<Integer> stock = inventory.find(id)
    .onErrorReturn(0);
~~~

If 0 is interpreted as out of stock, an outage could make the system reject orders as if stock were confirmed to be zero.

Better approach:

~~~java
Mono<Section<Inventory>> stock = inventory.find(id)
    .map(Section::available)
    .switchIfEmpty(Mono.just(
        Section.empty(Inventory.unknown())))
    .onErrorResume(
        this::isRecoverable,
        error -> Mono.just(
            Section.fallback(
                Inventory.unknown(),
                "inventory_unavailable")));
~~~

Record metrics/logs for fallbacks:

~~~java
.onErrorResume(
    this::isRecoverable,
    error -> {
        meterRegistry.counter(
            "aggregation.fallback",
            "service", "inventory",
            "reason", safeReason(error))
            .increment();

        return Mono.just(
            Section.fallback(
                Inventory.unknown(),
                safeReason(error)));
    })
~~~

The reason tag must have a small bounded value domain such as timeout, unavailable, or rejected. Do not use error.getMessage() as a tag because the message may contain IDs, URLs, or dynamic data. Do not expose internal exception messages in the response.

## 17. Parallel or Sequential Aggregation?

If downstreams are independent, Mono.zip lets you coordinate them:

~~~java
Mono.zip(
    catalog.findById(id),
    inventory.findByProductId(id),
    recommendation.findByProductId(id),
    ProductView::new);
~~~

Completion time is typically dominated by the slowest source plus overhead, rather than the sum of each source's time if called sequentially.

If source B needs an ID or data from source A, use flatMap/zipWhen:

~~~java
catalog.findById(id)
    .flatMap(product ->
        pricing.findPrice(product.sku())
            .map(price -> new ProductPrice(product, price)));
~~~

Do not write sequential flatMap chains for independent sources merely for readability; it increases latency. Conversely, do not use zip if the second source needs a value from the first source.

When Mono.zip terminates early because one source errors or is empty, the remaining sources may be cancelled. Downstream HTTP clients or reactive databases must honor cancellation and release resources. Do not assume that cancelling a source guarantees the remote server did not execute side effects.

## 18. Aggregation with WebClient

WebClient is Spring WebFlux's reactive HTTP client. A gateway can return Mono<T>:

~~~java
public Mono<Inventory> findInventory(String productId) {
    return webClient.get()
        .uri("/inventory/{id}", productId)
        .retrieve()
        .bodyToMono(Inventory.class);
}
~~~

With retrieve(), HTTP error statuses are typically converted into WebClientResponseException. If a downstream uses 404 to represent "no record," map that status to empty explicitly.

One clear way is exchangeToMono:

~~~java
public Mono<Inventory> findInventory(String productId) {
    return webClient.get()
        .uri("/inventory/{id}", productId)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Inventory.class);
            }
            if (response.statusCode().value() == 404) {
                return Mono.empty();
            }
            return response.createException()
                .flatMap(Mono::error);
        });
}
~~~

This is an explicit way to turn 404 into empty while other statuses become errors. If a 2xx body is empty, bodyToMono can also complete empty.

In ResponseSpec, onStatus requires Function<ClientResponse, Mono<? extends Throwable>>. Returning Mono.empty() from the exception function means that status is not turned into an error; the body is still processed by the decoder. If 404 has a body or complex semantics, exchangeToMono is often easier to express clearly.

Timeouts can be placed at the gateway so every caller shares the same limit, or in the aggregation service so policy varies by use case. Avoid applying timeouts twice without understanding the overall deadline. Gateways should translate HTTP/network errors into classifiable domain error types; aggregation decides fallbacks per business rules.

## 19. Complete Java 17+ Spring Boot 3.3.5 Example

The project below builds a product aggregation page from three gateways:

- Catalog is a required source. Product not found returns 404.
- Inventory is an optional source. Empty returns an EMPTY section; recoverable downstream errors return FALLBACK.
- Recommendations is an optional source. Empty returns an empty list with EMPTY status; recoverable errors return FALLBACK.
- In-memory gateways simulate success, empty, and error so the demo has no external service dependencies.
- Aggregation uses Mono.zip after normalizing optional sources into Section<T> values that always emit.

### Project Structure

~~~text
reactive-aggregation-demo/
├── pom.xml
└── src
    ├── main/java/com/example/aggregation
    │   ├── AggregationApplication.java
    │   ├── AggregationModels.java
    │   ├── GatewayPorts.java
    │   ├── AggregationExceptions.java
    │   ├── DemoGatewayConfiguration.java
    │   ├── ProductAggregationService.java
    │   └── ProductController.java
    └── test/java/com/example/aggregation
        ├── ProductAggregationServiceTest.java
        └── ProductAggregationHttpTest.java
~~~

### pom.xml

~~~xml
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

  <groupId>com.example</groupId>
  <artifactId>reactive-aggregation-demo</artifactId>
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
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
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

### AggregationApplication.java

~~~java
package com.example.aggregation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AggregationApplication {

    public static void main(String[] args) {
        SpringApplication.run(AggregationApplication.class, args);
    }
}
~~~

### AggregationModels.java

~~~java
package com.example.aggregation;

import java.util.List;

public final class AggregationModels {

    private AggregationModels() {
    }

    public enum SectionStatus {
        AVAILABLE,
        EMPTY,
        FALLBACK
    }

    public record Product(String id, String name) {
    }

    public record Inventory(int available, boolean known) {

        public static Inventory unknown() {
            return new Inventory(0, false);
        }
    }

    public record Recommendation(String id, String title) {
    }

    public record Section<T>(
            SectionStatus status,
            T value,
            String reason) {

        public static <T> Section<T> available(T value) {
            return new Section<>(
                SectionStatus.AVAILABLE, value, null);
        }

        public static <T> Section<T> empty(T value) {
            return new Section<>(
                SectionStatus.EMPTY, value, null);
        }

        public static <T> Section<T> fallback(
                T value, String reason) {
            return new Section<>(
                SectionStatus.FALLBACK, value, reason);
        }
    }

    public record ProductView(
        Product product,
        Section<Inventory> inventory,
        Section<List<Recommendation>> recommendations) {
    }

    public record ApiError(String code, String message) {
    }
}
~~~

Section<T> holds both the value and the source status. reason is a safe code containing no exception message or sensitive data.

### GatewayPorts.java

~~~java
package com.example.aggregation;

import java.util.List;

import reactor.core.publisher.Mono;

public final class GatewayPorts {

    private GatewayPorts() {
    }

    public interface CatalogGateway {
        Mono<AggregationModels.Product> findById(String id);
    }

    public interface InventoryGateway {
        Mono<AggregationModels.Inventory> findByProductId(String id);
    }

    public interface RecommendationGateway {
        Mono<List<AggregationModels.Recommendation>>
            findByProductId(String id);
    }
}
~~~

The three gateways return publishers. Gateways do not subscribe manually and do not call block().

### AggregationExceptions.java

~~~java
package com.example.aggregation;

public final class AggregationExceptions {

    private AggregationExceptions() {
    }

    public static final class ProductNotFoundException
            extends RuntimeException {

        public ProductNotFoundException(String id) {
            super("Product not found: " + id);
        }
    }

    public static final class DownstreamUnavailableException
            extends RuntimeException {

        public DownstreamUnavailableException(String service) {
            super(service + " service unavailable");
        }
    }
}
~~~

### DemoGatewayConfiguration.java

~~~java
package com.example.aggregation;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static com.example.aggregation.AggregationModels.*;
import static com.example.aggregation.AggregationExceptions.*;
import static com.example.aggregation.GatewayPorts.*;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
public class DemoGatewayConfiguration {

    @Bean
    CatalogGateway catalogGateway() {
        return id -> {
            if ("missing".equals(id)) {
                return Mono.empty();
            }
            return Mono.just(
                new Product(id, "Notebook " + id));
        };
    }

    @Bean
    InventoryGateway inventoryGateway() {
        return id -> {
            if ("no-stock".equals(id)) {
                return Mono.empty();
            }
            if ("inventory-error".equals(id)) {
                return Mono.error(
                    new DownstreamUnavailableException("inventory"));
            }
            return Mono.just(new Inventory(8, true));
        };
    }

    @Bean
    RecommendationGateway recommendationGateway() {
        return id -> {
            if ("no-recommendations".equals(id)) {
                return Mono.empty();
            }
            if ("recommendation-error".equals(id)) {
                return Mono.error(
                    new DownstreamUnavailableException(
                        "recommendations"));
            }
            return Mono.just(List.of(
                new Recommendation("r-1", "Desk lamp"),
                new Recommendation("r-2", "Notebook stand")));
        };
    }
}
~~~

The in-memory gateways simulate three scenarios by ID so the demo does not require external microservices. In a real system, replace these beans with WebClient gateways; do not leave simulation logic in the production profile.

### ProductAggregationService.java

~~~java
package com.example.aggregation;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeoutException;

import org.springframework.stereotype.Service;

import static com.example.aggregation.AggregationModels.*;
import static com.example.aggregation.AggregationExceptions.*;
import static com.example.aggregation.GatewayPorts.*;

import reactor.core.publisher.Mono;

@Service
public class ProductAggregationService {

    private static final Duration DOWNSTREAM_TIMEOUT =
        Duration.ofMillis(300);

    private final CatalogGateway catalog;
    private final InventoryGateway inventory;
    private final RecommendationGateway recommendations;

    public ProductAggregationService(
            CatalogGateway catalog,
            InventoryGateway inventory,
            RecommendationGateway recommendations) {
        this.catalog = catalog;
        this.inventory = inventory;
        this.recommendations = recommendations;
    }

    public Mono<ProductView> getView(String id) {
        Mono<Product> requiredProduct =
            Mono.defer(() -> catalog.findById(id))
                .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)));

        Mono<Section<Inventory>> inventorySection =
            Mono.defer(() -> inventory.findByProductId(id))
                .timeout(DOWNSTREAM_TIMEOUT)
                .map(Section::available)
                .switchIfEmpty(Mono.fromSupplier(
                    () -> Section.empty(Inventory.unknown())))
                .onErrorResume(
                    this::isRecoverable,
                    error -> Mono.just(
                        Section.fallback(
                            Inventory.unknown(),
                            safeReason(error))));

        Mono<Section<List<Recommendation>>> recommendationSection =
            Mono.defer(() ->
                    recommendations.findByProductId(id))
                .timeout(DOWNSTREAM_TIMEOUT)
                .map(Section::available)
                .switchIfEmpty(Mono.just(
                    Section.empty(List.of())))
                .onErrorResume(
                    this::isRecoverable,
                    error -> Mono.just(
                        Section.fallback(
                            List.of(),
                            safeReason(error))));

        return Mono.zip(
            requiredProduct,
            inventorySection,
            recommendationSection,
            ProductView::new);
    }

    private boolean isRecoverable(Throwable error) {
        return error instanceof TimeoutException
            || error instanceof DownstreamUnavailableException;
    }

    private String safeReason(Throwable error) {
        if (error instanceof TimeoutException) {
            return "timeout";
        }
        return "downstream_unavailable";
    }
}
~~~

Service explanation:

1. Product is a required source. An empty catalog result is converted into ProductNotFoundException.
2. Inventory is called inside Mono.defer so the gateway call only happens when a subscription needs it.
3. Inventory times out after 300 ms. If empty, the EMPTY section carries Inventory.unknown().
4. An inventory timeout or DownstreamUnavailableException is converted into a FALLBACK section.
5. Recommendations applies a similar policy; empty creates an empty list with EMPTY status.
6. Errors not in the recoverable list continue propagating.
7. Once both optional sources are normalized into publishers that always emit a Section, Mono.zip has all values needed to build ProductView if catalog succeeds.
8. No exception messages are included in the response reason.

### ProductController.java

~~~java
package com.example.aggregation;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static com.example.aggregation.AggregationModels.*;
import static com.example.aggregation.AggregationExceptions.*;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductAggregationService service;

    public ProductController(ProductAggregationService service) {
        this.service = service;
    }

    @GetMapping("/{id}/view")
    public Mono<ProductView> view(@PathVariable String id) {
        return service.getView(id);
    }

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ApiError> notFound(
            ProductNotFoundException error) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError(
                "PRODUCT_NOT_FOUND",
                "Requested product does not exist"));
    }
}
~~~

The exception handler does not expose internal exception messages externally. ProductNotFoundException is translated into HTTP 404 and a stable error code.

## 20. Testing the Service with StepVerifier

StepVerifier verifies publisher signals and partial states without starting an HTTP server.

### ProductAggregationServiceTest.java

~~~java
package com.example.aggregation;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static com.example.aggregation.AggregationModels.*;
import static com.example.aggregation.AggregationExceptions.*;
import static com.example.aggregation.GatewayPorts.*;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ProductAggregationServiceTest {

    private CatalogGateway catalog;
    private InventoryGateway inventory;
    private RecommendationGateway recommendations;
    private ProductAggregationService service;

    @BeforeEach
    void setUp() {
        catalog = mock(CatalogGateway.class);
        inventory = mock(InventoryGateway.class);
        recommendations = mock(RecommendationGateway.class);
        service = new ProductAggregationService(
            catalog, inventory, recommendations);
    }

    @Test
    void allSourcesAvailableProducesCompleteView() {
        when(catalog.findById("p1"))
            .thenReturn(Mono.just(new Product("p1", "Notebook")));
        when(inventory.findByProductId("p1"))
            .thenReturn(Mono.just(new Inventory(5, true)));
        when(recommendations.findByProductId("p1"))
            .thenReturn(Mono.just(List.of(
                new Recommendation("r1", "Lamp"))));

        StepVerifier.create(service.getView("p1"))
            .assertNext(view -> {
                assertEquals("p1", view.product().id());
                assertEquals(
                    SectionStatus.AVAILABLE,
                    view.inventory().status());
                assertEquals(
                    5,
                    view.inventory().value().available());
                assertEquals(
                    SectionStatus.AVAILABLE,
                    view.recommendations().status());
                assertEquals(
                    1,
                    view.recommendations().value().size());
            })
            .verifyComplete();
    }

    @Test
    void emptyInventoryBecomesEmptySection() {
        when(catalog.findById("p1"))
            .thenReturn(Mono.just(new Product("p1", "Notebook")));
        when(inventory.findByProductId("p1"))
            .thenReturn(Mono.empty());
        when(recommendations.findByProductId("p1"))
            .thenReturn(Mono.just(List.of()));

        StepVerifier.create(service.getView("p1"))
            .assertNext(view -> {
                assertEquals(
                    SectionStatus.EMPTY,
                    view.inventory().status());
                assertFalse(view.inventory().value().known());
                assertEquals(
                    SectionStatus.AVAILABLE,
                    view.recommendations().status());
            })
            .verifyComplete();
    }

    @Test
    void inventoryErrorBecomesFallbackSection() {
        when(catalog.findById("p1"))
            .thenReturn(Mono.just(new Product("p1", "Notebook")));
        when(inventory.findByProductId("p1"))
            .thenReturn(Mono.error(
                new DownstreamUnavailableException("inventory")));
        when(recommendations.findByProductId("p1"))
            .thenReturn(Mono.just(List.of()));

        StepVerifier.create(service.getView("p1"))
            .assertNext(view -> {
                assertEquals(
                    SectionStatus.FALLBACK,
                    view.inventory().status());
                assertEquals(
                    "downstream_unavailable",
                    view.inventory().reason());
                assertFalse(view.inventory().value().known());
            })
            .verifyComplete();
    }

    @Test
    void recommendationErrorDoesNotFailRequiredProduct() {
        when(catalog.findById("p1"))
            .thenReturn(Mono.just(new Product("p1", "Notebook")));
        when(inventory.findByProductId("p1"))
            .thenReturn(Mono.just(new Inventory(5, true)));
        when(recommendations.findByProductId("p1"))
            .thenReturn(Mono.error(
                new DownstreamUnavailableException(
                    "recommendations")));

        StepVerifier.create(service.getView("p1"))
            .assertNext(view -> {
                assertEquals("p1", view.product().id());
                assertEquals(
                    SectionStatus.AVAILABLE,
                    view.inventory().status());
                assertEquals(
                    SectionStatus.FALLBACK,
                    view.recommendations().status());
                assertTrue(view.recommendations().value().isEmpty());
            })
            .verifyComplete();
    }

    @Test
    void missingRequiredProductFailsAggregation() {
        when(catalog.findById("missing"))
            .thenReturn(Mono.empty());
        when(inventory.findByProductId("missing"))
            .thenReturn(Mono.just(new Inventory(5, true)));
        when(recommendations.findByProductId("missing"))
            .thenReturn(Mono.just(List.of()));

        StepVerifier.create(service.getView("missing"))
            .expectError(ProductNotFoundException.class)
            .verify();
    }
}
~~~

Five tests demonstrate:

- When all sources have data, the aggregate returns AVAILABLE.
- Empty inventory is distinguished from inventory errors.
- Inventory errors can fall back without breaking the product.
- Recommendation errors do not cause product and inventory to be lost.
- Empty catalog is a domain error because this source is required.

### Testing zip Empty Behavior Directly

This is a standalone test snippet that can be added to a test class:

~~~java
@Test
void zipCompletesEmptyWhenOneSourceIsEmpty() {
    StepVerifier.create(
            Mono.zip(
                Mono.just("product"),
                Mono.<Integer>empty(),
                (name, stock) -> name + ":" + stock))
        .verifyComplete();
}
~~~

The combinator is not invoked because the stock value is missing. If business requirements expect a partial result, normalize optional sources before calling zip.

## 21. Testing HTTP with WebTestClient

Integration tests verify the controller, JSON serialization, and exception mapping.

### ProductAggregationHttpTest.java

~~~java
package com.example.aggregation;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductAggregationHttpTest {

    @Autowired
    private WebTestClient client;

    @Test
    void allServicesAvailableReturnsCompleteView() {
        client.get()
            .uri("/api/products/p1/view")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.product.id").isEqualTo("p1")
            .jsonPath("$.inventory.status")
                .isEqualTo("AVAILABLE")
            .jsonPath("$.inventory.value.available")
                .isEqualTo(8)
            .jsonPath("$.recommendations.status")
                .isEqualTo("AVAILABLE")
            .jsonPath("$.recommendations.value")
                .isArray();
    }

    @Test
    void emptyInventoryIsReportedAsEmpty() {
        client.get()
            .uri("/api/products/no-stock/view")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.inventory.status")
                .isEqualTo("EMPTY")
            .jsonPath("$.inventory.value.known")
                .isEqualTo(false);
    }

    @Test
    void inventoryFailureUsesFallbackWithoutLosingProduct() {
        client.get()
            .uri("/api/products/inventory-error/view")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.product.id")
                .isEqualTo("inventory-error")
            .jsonPath("$.inventory.status")
                .isEqualTo("FALLBACK")
            .jsonPath("$.inventory.reason")
                .isEqualTo("downstream_unavailable");
    }

    @Test
    void recommendationFailureKeepsOtherSections() {
        client.get()
            .uri("/api/products/recommendation-error/view")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.product.id")
                .isEqualTo("recommendation-error")
            .jsonPath("$.inventory.status")
                .isEqualTo("AVAILABLE")
            .jsonPath("$.recommendations.status")
                .isEqualTo("FALLBACK")
            .jsonPath("$.recommendations.value")
                .isArray();
    }

    @Test
    void noRecommendationsIsEmptyNotFallback() {
        client.get()
            .uri("/api/products/no-recommendations/view")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.recommendations.status")
                .isEqualTo("EMPTY")
            .jsonPath("$.recommendations.value")
                .isArray();
    }

    @Test
    void missingCatalogProductReturns404() {
        client.get()
            .uri("/api/products/missing/view")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody()
            .jsonPath("$.code")
                .isEqualTo("PRODUCT_NOT_FOUND");
    }
}
~~~

The HTTP tests verify that partial responses have explicit statuses. An empty recommendation list because the service had no data is EMPTY; an empty list because the service errored is FALLBACK. Both responses have the same value shape but different meanings.

## 22. Running the Project

Requires Java 17+ and Maven 3.8+.

~~~bash
java -version
mvn -version
mvn -q clean test
~~~

The project has 5 service tests and 6 HTTP tests. The empty-zip test in the previous section is a standalone snippet; adding it to a test class increases the total test count by one.

When all 11 tests across both classes pass, Maven exits with code 0. Illustrative summary example:

~~~text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is expected output, not the result of running Maven while authoring this lesson.

Start the application:

~~~bash
mvn spring-boot:run
~~~

Call a normal product:

~~~bash
curl -i "http://localhost:8080/api/products/p1/view"
~~~

The response contains the product, AVAILABLE inventory, and AVAILABLE recommendations.

Call the empty inventory case:

~~~bash
curl -i "http://localhost:8080/api/products/no-stock/view"
~~~

The response is still HTTP 200 because the required product exists. The inventory section has status EMPTY and known=false.

Call the inventory error case:

~~~bash
curl -i "http://localhost:8080/api/products/inventory-error/view"
~~~

The response still includes the product. The inventory section has status FALLBACK and reason downstream_unavailable.

Call the recommendation error case:

~~~bash
curl -i "http://localhost:8080/api/products/recommendation-error/view"
~~~

The response still includes the product and inventory. Recommendations has FALLBACK with an empty list.

Call a missing catalog item:

~~~bash
curl -i "http://localhost:8080/api/products/missing/view"
~~~

Expected status: HTTP 404 Not Found, body with code PRODUCT_NOT_FOUND.

## 23. Common Mistakes and Fixes

1. **Treating Mono.empty() as onError.** Empty is normal completion; use defaultIfEmpty/switchIfEmpty.
2. **Using defaultIfEmpty to handle timeouts.** Timeout is an error; use onErrorResume or retry.
3. **Using onErrorResume to handle empty.** Empty does not trigger error handlers; use switchIfEmpty.
4. **Using switchIfEmpty to handle HTTP errors.** WebClient retrieve typically emits WebClientResponseException for error statuses; explicitly map statuses to empty or domain errors.
5. **Eager fallback causing database calls despite cache hits.** Use Mono.defer(() -> database.find(...)).
6. **Creating the publisher beforehand and placing it inside defer.** Defer just returns the pre-built publisher; put the gateway invocation inside the supplier.
7. **Mono.zip with an optional source that can be empty.** Normalize empty into a Section/default/Optional before zip.
8. **Assuming zipDelayError replaces empty automatically.** It delays errors; it does not turn empty into a value.
9. **Zipping Mono<Void> with Mono<T>.** Mono<Void> emits no element; use thenReturn, delayUntil, or Mono.when.
10. **Catching every Throwable and returning default data.** Can mask programming bugs, authentication, or validation errors; filter recoverable exceptions.
11. **Retrying after fallback.** Fallback has already turned the error into onNext; retry never sees the error. Retry before fallback.
12. **Retrying empty with retryWhen.** retryWhen handles onError; empty requires a bounded repeat/polling policy.
13. **Placing timeouts only outside the aggregate.** One slow source can stall the entire response; set per-service timeouts and an overall deadline.
14. **Not distinguishing EMPTY from FALLBACK.** Consumers misinterpret the cause; include status in the response.
15. **Returning exception messages in the API.** Can leak URLs, hosts, or internal details; use safe error codes.
16. **Using onErrorComplete to hide all errors.** Errors disappear into empty; log/record metrics and use an explicit stateful policy.
17. **Using onErrorContinue as a general mechanism.** Semantics depend on operators; handle errors directly on each publisher.
18. **Calling subscribe() inside an aggregation service.** Loses error propagation and cancellation; compose publishers and return them.
19. **Using sequential flatMap for independent sources.** Increases latency; use zip when all needed sources are independent.
20. **Using zip for a source that depends on another source's value.** The combinator only runs when all have values; use flatMap/zipWhen.
21. **Ignoring cancellation.** When zip terminates early, other sources may be cancelled; external calls must clean up.
22. **Not recording fallback rates.** Outages can go unnoticed; add counters by service and bounded reason.
23. **Caching fallback data for too long.** Stale data can become wrong source data; define TTL and stale status.
24. **Using default 0 for unknown inventory.** 0 means out of stock; use a known flag or Section status.
25. **Only testing the happy path.** Misses empty/error cases; test each source and each state independently.
26. **Not testing downstreams returning HTTP 404.** WebClient can turn it into an error; verify status mapping against the contract.
27. **Lacking an overall deadline.** Total retry/fallback duration exceeds SLA; calculate the time budget and add an outer timeout.
28. **Forgetting that a fallback publisher can also error.** Decide whether fallback errors propagate or have a second fallback; never assume it always succeeds.

## 24. Aggregation Design Checklist

Before releasing an aggregation API, answer:

- Which sources are required and which are optional?
- What is the business meaning of empty for each source?
- Should empty become 404, an empty list, or an EMPTY section?
- Which errors are recoverable and which must propagate?
- Does the response distinguish EMPTY from FALLBACK?
- Could a fallback value be mistaken for real data?
- Are there safe reason codes and metrics for fallbacks?
- Is fallback creation made lazy with Mono.defer where needed?
- Are retries bounded in count and limited to transient errors?
- Are retries placed before fallbacks?
- Is empty accidentally being retried?
- Is the per-downstream timeout reasonable?
- Is there an overall deadline for the aggregate?
- Does Mono.zip receive publishers that always emit a value for every optional branch?
- Is Mono<Void> accidentally being zipped?
- Are independent sources called concurrently?
- Do dependent sources properly use flatMap/zipWhen?
- Does cancellation release HTTP/database resources?
- Does WebClient status mapping distinguish 404 from 5xx?
- Do error responses avoid leaking internal exceptions?
- Are success, empty, error, timeout, not-found, and fallback failure tested?
- Are there metrics for downstream latency, error, empty, and fallback rates?
- Are logs/traces sufficient for investigation without recording secrets or PII?

## 25. Self-Check Exercises

**Question 1.** With which signal does Mono.empty() terminate?  
**Answer:** onComplete without onNext.

**Question 2.** Does defaultIfEmpty() handle empty or error?  
**Answer:** Only empty completion.

**Question 3.** How does switchIfEmpty() differ from defaultIfEmpty()?  
**Answer:** switchIfEmpty switches to another Publisher; defaultIfEmpty emits a default value.

**Question 4.** Why should Mono.defer be used for cache fallbacks?  
**Answer:** To invoke/create the fallback publisher only when the cache is empty, avoiding eager side effects.

**Question 5.** Does onErrorResume handle Mono.empty()?  
**Answer:** No; it only handles onError.

**Question 6.** Does doOnError replace an error with a fallback?  
**Answer:** No; it only performs a side effect to observe the error.

**Question 7.** Does Mono.zip emit a tuple if one source is empty?  
**Answer:** No; the result completes empty and the combinator is not called.

**Question 8.** Does zipDelayError turn empty into a value?  
**Answer:** No; it delays errors, but empty still makes the result empty.

**Question 9.** Why cannot Mono<Void> be used as a zip component?  
**Answer:** Mono<Void> emits no elements for the combinator to receive.

**Question 10.** How do you preserve a value after a Mono<Void> side effect?  
**Answer:** Use flatMap followed by thenReturn(value), or delayUntil when appropriate.

**Question 11.** Should retry be placed before or after fallback?  
**Answer:** Usually before fallback so retry still sees the error.

**Question 12.** Does retryWhen retry when a source is empty?  
**Answer:** No; it handles errors. Empty needs a separate repeat/polling policy.

**Question 13.** Why should partial results have a status?  
**Answer:** So consumers can distinguish real data, missing data, and fallback data.

**Question 14.** How should an empty required catalog source be handled?  
**Answer:** Convert it into a domain error like ProductNotFoundException and map it to HTTP 404.

**Question 15.** When should Mono.zip be used instead of flatMap?  
**Answer:** When sources are independent and all must produce values to build the result.

**Question 16.** Does WebClient retrieve() automatically treat 404 as Mono.empty?  
**Answer:** Not by default; error statuses normally become WebClientResponseException. 404 must be mapped explicitly.

**Question 17.** Should fallback errors be logged/measured?  
**Answer:** Yes, via logs/metrics with bounded reasons and no sensitive data.

**Question 18.** What happens if a fallback also errors?  
**Answer:** That error propagates unless there is a subsequent recovery policy; decide explicitly.

## 26. Takeaways

Reactor distinguishes value, empty completion, and error. defaultIfEmpty/switchIfEmpty handle empty; onErrorReturn/onErrorResume handle errors; doOnError only observes; onErrorMap changes error types. Mono.defer ensures fallbacks are created only when needed.

Mono.zip requires each source to emit a value. If one source is empty, the zip result is also empty; if one source errors, zip can terminate early and cancel other sources. zipDelayError delays errors but does not turn empty into a value. For aggregation, normalize optional sources into Section<T> with AVAILABLE, EMPTY, or FALLBACK status before zip. Required sources can turn empty into domain errors such as 404.

Place timeouts and bounded retries before fallbacks; retry handles errors, not empty. Fall back only on recoverable errors, keep reason codes safe, record metrics/logs, and do not let fallback data masquerade as real data. Use zip for independent sources, flatMap/zipWhen for dependent sources, and Mono.when for Mono<Void> side effects. Separately test success, empty, error, timeout, cancellation, and partial responses.

### References

- Project Reactor 3.6, [Reference Guide — Error Handling](https://projectreactor.io/docs/core/3.6.11/reference/index.html#which.errors).
- Project Reactor 3.6, [Reference Guide — Empty Mono with zip/zipWhen](https://projectreactor.io/docs/core/3.6.11/reference/index.html#faq.zipWhen).
- Project Reactor 3.6, [Mono Javadoc](https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Mono.html).
- Project Reactor 3.6, [Flux Javadoc](https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Flux.html).
- Spring Framework 6.1, [WebClient Reference](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).
- Spring Framework 6.1, [WebClient.ResponseSpec Javadoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/web/reactive/function/client/WebClient.ResponseSpec.html).
- Spring Boot 3.3, [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3.5/reference/html/features.html#features.testing).
