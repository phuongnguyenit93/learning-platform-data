# Errors Before Publisher Creation Versus Errors Emitted on the Stream

In a Spring WebFlux application, a method returning **Mono** or **Flux** can fail at two different points in time: a synchronous error occurring before the method creates and returns the Publisher, or an error emitted while the Publisher is being subscribed to and executed. These two cases behave differently when integrating Spring Cloud CircuitBreaker with Resilience4j.

A reactive Circuit Breaker protects signals emitted by the Publisher it wraps. If code throws an exception before creating the Publisher and before calling the Circuit Breaker, the reactive pipeline does not yet exist to receive the error. Conversely, if the error is represented as an **onError** signal, the breaker can observe the outcome, record the failure according to configuration, and trigger the fallback. Understanding this boundary prevents missed errors, avoids counting business validation errors in the failure rate, and keeps reactive APIs consistently returning Publishers.

## 1. Two distinct error timings

A reactive method does not mean every line of code inside it automatically runs asynchronously. Java expressions are still evaluated immediately when the method is called, unless they are placed inside a deferred operator such as **Mono.defer** or **Mono.fromCallable**.

Consider two scenarios:

~~~java
Mono<Product> findProduct(String id) {
    Product product = catalogClient.findImmediately(id);
    return Mono.just(product);
}
~~~

If **findImmediately** throws an exception, the exception is thrown immediately when calling **findProduct**. The method never returns a Mono; the caller receives a synchronous exception and has no Publisher to subscribe to.

In the second scenario:

~~~java
Mono<Product> findProduct(String id) {
    return Mono.fromCallable(() -> catalogClient.findImmediately(id));
}
~~~

The client call is deferred until subscription. If it throws an exception, Reactor converts the exception into an **onError** signal on the Publisher. The caller receives a Mono and can handle the error using reactive operators.

| Scenario | When it occurs | Observable result |
|---|---|---|
| Throwing an exception before creating the Publisher | Immediately when the Java method is called | Method does not return a Mono/Flux |
| Returning **Mono.error(exception)** | When the Publisher is subscribed to | Publisher emits an onError signal |
| Exception thrown inside **Mono.defer** | When the supplier is invoked at subscribe time | Reactor converts the exception into onError |
| Exception from an HTTP request during WebClient execution | During subscription and data exchange | Publisher emits onError |
| Exception inside the **map** operator | When an element passes through the operator | Publisher emits onError |

The takeaway: a Java exception only becomes a reactive stream error when it is converted into a Publisher error signal. Merely declaring a return type of Mono or Flux is not enough to guarantee that.

## 2. Synchronous errors before Publisher creation

Errors before Publisher creation commonly come from parameter validation, null object access, URI construction, immediate data conversion during the method call, or calling an API that can throw synchronous exceptions.

Example:

~~~java
Mono<Product> getProduct(String id) {
    if (id == null || id.isBlank()) {
        throw new IllegalArgumentException("id must not be blank");
    }

    return catalogClient.getProduct(id);
}
~~~

When **id** is invalid, the method throws **IllegalArgumentException** immediately. The caller does not receive a Mono on which to call **onErrorResume**, **doOnError**, or subscribe. If this error occurs before calling **ReactiveCircuitBreaker.run**, the Circuit Breaker fallback cannot handle it either.

In a reactive API, input errors should be represented using an error Publisher:

~~~java
Mono<Product> getProduct(String id) {
    if (id == null || id.isBlank()) {
        return Mono.error(
            new IllegalArgumentException("id must not be blank")
        );
    }

    return catalogClient.getProduct(id);
}
~~~

The method always returns a Mono. With invalid input, the Mono emits **onError** upon subscription. However, if this check sits before the Circuit Breaker, the input error does not pass through the breaker and does not increase the failure rate of the Catalog service.

This is usually the right separation of responsibilities: request validation errors belong to the calling application; the Circuit Breaker only measures the dependent operation it is assigned to protect. Do not let malformed client requests mislead the breaker into thinking the Catalog service is down.

## 3. Using Mono.error to represent errors inside a reactive pipeline

**Mono.error** creates a Publisher that terminates with an onError signal. It is useful when a condition is detected synchronously, yet the application wants to preserve its reactive return contract.

Example:

~~~java
Mono<Product> getProduct(String id) {
    if (id == null || id.isBlank()) {
        return Mono.error(new InvalidProductIdException(id));
    }

    return catalogClient.getProduct(id);
}
~~~

The error is emitted upon subscription rather than thrown out of the method as a synchronous exception. Downstream components can use reactive operators to handle it:

~~~java
return getProduct(id)
    .onErrorResume(
        InvalidProductIdException.class,
        error -> Mono.just(Product.unavailable(id))
    );
~~~

**Mono.error** does not by itself determine whether an error is recorded by the Circuit Breaker. Where the error Publisher sits relative to **ReactiveCircuitBreaker.run** determines whether the breaker observes that error. If Mono.error is passed inside the Publisher protected by the Circuit Breaker, the error can be recorded according to Resilience4j's exception configuration. If the error is returned before calling the breaker, it stays outside the breaker's measurement scope.

Therefore, distinguish two goals: converting an error into a reactive signal to keep the API consistent, and placing an error inside the Circuit Breaker scope to evaluate dependency health. Not every reactive error should count as a failure of the dependent service.

## 4. Using Mono.defer to catch exceptions when creating the source Publisher

Some clients or helper functions may throw an exception as soon as the method is called to construct a Publisher. If that call is passed directly as an argument to **run**, the exception can occur before the Circuit Breaker receives the Publisher:

~~~java
return reactiveCircuitBreakerFactory.create("catalog").run(
    catalogClient.getProduct(id),
    error -> fallback(id, error)
);
~~~

Java must evaluate **catalogClient.getProduct(id)** before invoking **run**. If the client method throws a synchronous exception while building the Publisher, **run** is never called and the fallback has no chance to receive that error.

Place Publisher creation inside **Mono.defer** to defer calling the client until subscribe time:

~~~java
Mono<Product> getProduct(String id) {
    return reactiveCircuitBreakerFactory.create("catalog").run(
        Mono.defer(() -> catalogClient.getProduct(id)),
        error -> fallback(id, error)
    );
}
~~~

Upon subscription, the supplier inside **Mono.defer** executes. If **catalogClient.getProduct(id)** throws a synchronous exception, Reactor turns the exception into an onError signal. The Publisher has already been passed through the Circuit Breaker, so the breaker can observe the error and apply the configured fallback.

**Mono.defer** is especially useful when:

- The method creating the Publisher can throw synchronous exceptions.
- Request creation needs to be deferred until subscription occurs.
- A fresh Publisher needs to be created for each subscription.
- You want errors during source Publisher construction to enter the protected reactive pipeline.

Note: **Mono.defer** only defers when the supplier is invoked and converts exceptions into reactive signals. It does not turn a blocking API into a non-blocking one. If the supplier invokes a synchronous client, that operation still blocks the subscribing thread.

## 5. Placing validation outside the Circuit Breaker and dependency calls inside

A reactive service often needs both request validation and protection for calls to a dependent service. You can organize the boundary as follows:

~~~java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class CatalogService {

    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;
    private final ProductMapper productMapper;
    private final ProductCache productCache;

    CatalogService(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient,
            ProductMapper productMapper,
            ProductCache productCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
        this.productMapper = productMapper;
        this.productCache = productCache;
    }

    Mono<Product> getProduct(String id) {
        if (id == null || id.isBlank()) {
            return Mono.error(
                new InvalidProductIdException(id)
            );
        }

        return circuitBreakerFactory.create("catalog").run(
            Mono.defer(() -> catalogClient.getProduct(id))
                .map(productMapper::toDomain),
            error -> fallback(id, error)
        );
    }

    private Mono<Product> fallback(String id, Throwable error) {
        if (error instanceof CallNotPermittedException) {
            log.warn("Circuit Breaker catalog rejected call, id={}", id);
        } else {
            log.warn("Failed to fetch product from Catalog, id={}", id, error);
        }

        return productCache.findById(id)
            .switchIfEmpty(Mono.error(
                new CatalogUnavailableException(id, error)
            ));
    }
}
~~~

This example separates responsibilities into three parts:

1. **Validation:** checks the ID before creating the Circuit Breaker. Invalid input returns Mono.error and is not counted as a dependency failure.
2. **Source Publisher:** **Mono.defer** defers the client call. Synchronous exceptions thrown during Publisher creation are converted into onError.
3. **Fallback:** receives the error from the Circuit Breaker and returns cached data or an appropriate business error.

The **map** step in the example sits inside the protected Publisher. If the mapper throws an exception while processing the response, that error is also emitted as onError and can be recorded by the Circuit Breaker. This is an appropriate choice if an unmappable response indicates the Catalog service broke its contract.

If mapper errors are internal programming bugs and should not affect Catalog health evaluation, place the mapping after the Circuit Breaker finishes. Then the breaker measures only the client call; mapping errors are handled at the application layer.

## 6. Distinguishing errors emitted on the stream from recovered errors

Reactive Streams propagate errors via the **onError** signal. An operator can observe an error, transform it, or recover using another Publisher.

| Operator | Behavior | What does the outer Circuit Breaker observe? |
|---|---|---|
| **doOnError** | Only observes the error, does not recover | Still receives onError |
| **onErrorMap** | Changes the exception type, preserves the error signal | Still receives onError with the new exception |
| **onErrorResume** | Replaces the error with another Publisher | May receive a successful onNext/onComplete |
| **onErrorReturn** | Replaces the error with a fallback value | Receives the value and completes normally |
| **retry** | Resubscribes to the source Publisher per policy | The final outcome is forwarded to the protection layer |
| **Mono.error** | Creates a Publisher emitting onError | Receives onError if within the protection scope |

Where **onErrorResume** is placed matters greatly. If you recover from the error inside the source Publisher before passing it into the Circuit Breaker, the breaker may only see a successful outcome:

~~~java
Mono<Product> source = Mono.defer(() -> catalogClient.getProduct(id))
    .onErrorResume(error -> productCache.findById(id));

return circuitBreakerFactory.create("catalog").run(
    source,
    error -> Mono.error(error)
);
~~~

In this example, errors from Catalog are handled by **onErrorResume** before reaching the Circuit Breaker. If the cache returns data, the Circuit Breaker observes a Publisher completing normally and does not record the original failure.

If you want the Circuit Breaker to record the error first and then run the fallback, pass the unrecovered source Publisher into **run** and provide the fallback as the second parameter:

~~~java
Mono<Product> source =
    Mono.defer(() -> catalogClient.getProduct(id));

return circuitBreakerFactory.create("catalog").run(
    source,
    error -> productCache.findById(id)
        .switchIfEmpty(Mono.error(
            new CatalogUnavailableException(id, error)
        ))
);
~~~

With this approach, the source error passes through the Circuit Breaker before the fallback replaces the result for the caller. Having the fallback return successful data does not erase the failure outcome that the breaker already observed.

## 7. Cases for Mono.just and Mono.fromCallable

A common mistake is placing a call that can throw exceptions inside **Mono.just**:

~~~java
Mono<Product> product =
    Mono.just(catalogClient.findProductImmediately(id));
~~~

The argument to **Mono.just** is evaluated by Java before the method is invoked. Therefore, if **findProductImmediately** throws an exception, no Mono is created at all.

For a synchronous function that returns a value, **Mono.fromCallable** defers the call and converts exceptions into onError:

~~~java
Mono<Product> product =
    Mono.fromCallable(() -> catalogClient.findProductImmediately(id));
~~~

If the synchronous function performs blocking I/O, move it onto an appropriate scheduler, for example:

~~~java
Mono<Product> product =
    Mono.fromCallable(() -> blockingCatalogClient.findProduct(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

You can then place this Publisher inside a Reactive Circuit Breaker if you need to measure the dependent operation. However, when the application already has WebClient or a reactive client, use the native non-blocking API rather than falling back to blocking calls on a scheduler just to reuse an old client.

| Publisher creation approach | When is the source call executed? | Synchronous exception from source call |
|---|---|---|
| **Mono.just(client.call())** | Immediately when the Java expression is evaluated | Thrown outward before Mono is created |
| **Mono.fromCallable(client::call)** | At subscribe time | Converted into onError |
| **Mono.defer(() -> client.callReactive())** | At subscribe time | Converted into onError if supplier throws |
| **client.callReactive()** passed directly to run | Usually when building the Publisher | May throw before run is invoked |

## 8. Which errors should the Circuit Breaker record?

Not every onError indicates an unhealthy dependent service. For example:

- **CallNotPermittedException:** the breaker rejected the call because it is OPEN or has no remaining permits in HALF_OPEN. This is a signal from the protection mechanism, not a new error returned by the dependent service.
- **TimeoutException:** the call exceeded the allowed duration. Can be counted as a failure if part of the health evaluation policy.
- **WebClientResponseException:** HTTP error response from the dependent service. Depending on status code and API contract, it can be recorded or ignored.
- **InvalidProductIdException:** application input error. Should normally occur outside the Circuit Breaker.
- **MappingException:** response conversion error. Decide whether to count toward failure rate based on whether it reflects a dependency contract issue or an internal mapper bug.
- **CancellationException:** processing was cancelled because the caller lost interest or an outer layer timed out. Avoid treating every cancellation as a service failure.

Resilience4j lets you configure which exception types are recorded and which are ignored. These exception groups should reflect the operational semantics of the dependency. If an HTTP 404 means a product does not exist per business rules, it probably should not increase the failure rate. If HTTP 503 indicates the service is unavailable, it usually should count as a failure.

Check the configuration of **recordExceptions**, **ignoreExceptions**, **recordFailurePredicate**, or the corresponding mechanism in the Resilience4j version in use. Do not rely solely on exception class names; determine whether the error indicates degraded availability of the dependency.

## 9. Processing flow diagram

The following diagram shows the separation between errors before Publisher creation and errors emitted on a Publisher protected by a Circuit Breaker:

~~~mermaid
flowchart TD
    A["Call reactive method"] --> B{"Valid input?"}
    B -- "No" --> C["Return Mono.error"]
    C --> D["Caller receives onError on subscribe"]
    B -- "Yes" --> E["Create Publisher with Mono.defer"]
    E --> F["Pass Publisher into Reactive Circuit Breaker"]
    F --> G["Subscribe and call dependency"]
    G --> H{"Outcome"}
    H -- "onNext / onComplete" --> I["Circuit Breaker records outcome"]
    H -- "onError" --> J["Circuit Breaker records per exception policy"]
    J --> K["Run fallback"]
    K --> L["Return fallback Publisher or onError"]
    I --> M["Caller receives result"]
    L --> M
~~~

Input errors are represented using Mono.error so the API still returns a Publisher, while staying outside the Circuit Breaker. Dependency call errors are placed inside the source Publisher with Mono.defer, so the breaker can observe the error signal and apply its recording policy.

## 10. Common implementation mistakes

1. **Throwing an exception before returning a Publisher and expecting the reactive fallback to handle it.** When the method has not yet returned a Mono, the Circuit Breaker fallback is not attached to the pipeline.
2. **Using Mono.just for a call that can throw exceptions.** Java evaluates the call before Mono.just is created; use Mono.defer or Mono.fromCallable as appropriate.
3. **Placing validation in the wrong position.** Input errors do not reflect dependency health; normally return Mono.error before calling the Circuit Breaker.
4. **Using Mono.defer while still running blocking I/O on the event loop.** Defer postpones the operation rather than making it non-blocking.
5. **Recovering from errors with onErrorResume before the Circuit Breaker.** The breaker may only see a successful outcome and fail to record the original error.
6. **Confusing onError with synchronous exceptions.** An error emitted as onError can be handled with reactive operators; an exception thrown before the Publisher exists must be handled at the method invocation boundary.
7. **Counting business errors in the failure rate.** Classify exceptions according to service semantics to avoid tripping the circuit over invalid requests or missing resources.
8. **Having the fallback call the same failing dependency.** Fallbacks should use a cache or an independent source so they do not trigger cascading failures.

## 11. Practice scenario

A Product API service exposes a reactive method **getProduct(id)**. The method accepts an ID from the request, calls Catalog via WebClient, and maps the response to a Product domain object. When Catalog fails, the application can use a cache.

Consider four scenarios:

| Scenario | How it is expressed | Does the Circuit Breaker observe it? |
|---|---|---|
| Empty ID and method throws IllegalArgumentException immediately | Synchronous throw before returning Mono | No; caller receives exception directly |
| Empty ID and method returns Mono.error before calling Circuit Breaker | Error Publisher outside the breaker | No |
| Catalog client throws an exception when creating the Publisher but is called inside Mono.defer within run | Exception is converted into onError | Yes, per exception policy |
| Catalog returns an HTTP error while the Publisher is executing | Publisher emits onError | Yes, per exception policy |

An appropriate implementation:

~~~java
Mono<Product> getProduct(String id) {
    if (id == null || id.isBlank()) {
        return Mono.error(new InvalidProductIdException(id));
    }

    return reactiveCircuitBreakerFactory.create("catalog").run(
        Mono.defer(() -> webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(ProductResponse.class)
        ).map(productMapper::toDomain),
        error -> productCache.findById(id)
            .switchIfEmpty(Mono.error(
                new CatalogUnavailableException(id, error)
            ))
    );
}
~~~

In this example, validation sits outside the breaker; the WebClient request is created inside Mono.defer; errors from HTTP or mapping are emitted as onError within the protected Publisher; and the fallback checks the cache when needed. When testing, observe both the caller's response and Circuit Breaker metrics to confirm which errors count toward the failure rate.

Questions to answer after practicing:

- Which case prevents the method from returning a Publisher?
- Why does Mono.error preserve the reactive contract without automatically feeding the error into the Circuit Breaker?
- How does Mono.defer change when the client is invoked and how exceptions are converted?
- How does placing onErrorResume before versus after the Circuit Breaker affect metrics?
- How should validation errors, timeouts, HTTP errors, and CallNotPermittedException be classified?

## Conclusion

Exceptions thrown before creating a Publisher happen synchronously and cannot be handled by the Circuit Breaker's reactive fallback if the breaker never receives a Publisher. Use Mono.error to preserve the reactive contract for input errors, place validation outside the protection scope if you do not want business errors counted in the failure rate, and use Mono.defer or Mono.fromCallable to convert exceptions thrown during source Publisher creation into onError signals. Place the fallback right after the Circuit Breaker so the breaker observes the original error before recovering the result.
