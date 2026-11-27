# Evaluating Return Results with Predicates When Supported by the Version

In many systems, a call to a dependency can return an HTTP response or a result object that is technically valid yet carries an unsuccessful business or operational meaning. For example, a partner service returns HTTP 503 inside a response object, a payment API returns status TEMPORARY_UNAVAILABLE, or an inventory service returns a result indicating data cannot currently be supplied.

If a call finishes normally and returns a value, the Circuit Breaker normally treats it as a success. However, in certain Resilience4j versions and APIs, a **result predicate** can be used to evaluate the return value itself. The predicate decides which results should be recorded as failures based on the contents of the result object.

Be sure to distinguish a result predicate from an exception predicate. A result predicate inspects the returned value; an exception predicate classifies thrown errors. A result predicate only changes how the Circuit Breaker records metrics—it does not convert a response into an exception, replace the response, or automatically trigger a fallback. Whether configuration via YAML or a reactive adapter is supported also depends on the Resilience4j and Spring Cloud CircuitBreaker versions in use.

## 1. Why Evaluate Return Values?

By default, a Circuit Breaker classifies a call based on whether the operation completes normally or throws an exception. This works for most network calls: connection errors, timeouts, or client exceptions are typically failure signals.

Sometimes, however, a client receives a valid response whose body indicates the dependency cannot serve the request. For example:

~~~java
public record PartnerResponse(int statusCode, String message) {
}
~~~

A call might return:

| HTTP status | Client Return Value | Operational Meaning |
|---|---|---|
| 200 | PartnerResponse(200, "OK") | Successful call |
| 404 | PartnerResponse(404, "Not found") | May be a normal business outcome |
| 429 | PartnerResponse(429, "Rate limited") | Dependency or quota is throttling traffic |
| 503 | PartnerResponse(503, "Unavailable") | Dependency is temporarily unable to serve requests |

If all of these responses are returned normally, the Circuit Breaker may treat them all as successes. In that case, the statistical failure rate fails to reflect the dependency's actual state. A result predicate lets you identify specific response values that should be recorded as failures.

Do not assume every non-2xx HTTP status is an infrastructure error. 404 may be a valid business outcome; 409 may indicate a request conflict; 429 or 503 is typically a signal requiring investigation into load or availability. Classification rules must align with the API contract and business semantics.

## 2. How Result Predicates Work

A predicate is a function that accepts a value and returns a boolean. With configuration APIs supporting result predicates, Resilience4j uses the function's return value to decide whether the call's measurement is recorded as a success or a failure.

General rules:

- Predicate returns **true**: the outcome is recorded as a failure.
- Predicate returns **false**: the outcome is recorded as a success.
- Call throws an exception: handled by the exception classification policy rather than passing through the result predicate as a normal response.

For example, treat only responses with status 500 or higher as failures:

~~~java
Predicate<Object> recordServerErrors = result ->
        result instanceof PartnerResponse response
                && response.statusCode() >= 500;
~~~

For a response with status 200, the predicate returns false. For a response with status 503, the predicate returns true. For a result type other than PartnerResponse, the instanceof expression evaluates to false.

General processing flow:

~~~mermaid
flowchart TD
    A[Dependency call] --> B{How does it finish?}
    B -- Throws exception --> C[Classify via exception policy]
    B -- Returns value --> D{Is result predicate supported?}
    D -- No --> E[Apply API default rule]
    D -- Yes --> F[Evaluate return value]
    F -- true --> G[Record as failure]
    F -- false --> H[Record as success]
    C --> I[Update Circuit Breaker metrics]
    G --> I
    H --> I
    E --> I
~~~

The result predicate participates in recording the outcome of a single call. Once the measurement is updated, the Circuit Breaker computes failure rate and slow call rate over the sliding window and can transition state if configured thresholds are reached.

## 3. Configuring a Result Predicate in Java When Supported by the API

Resilience4j provides programmatic configuration on CircuitBreakerConfig via the **recordResult(Predicate<Object>)** method in versions that offer this feature.

Example:

~~~java
import java.time.Duration;
import java.util.function.Predicate;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

public class PartnerCircuitBreakerConfiguration {

    public CircuitBreakerConfig createConfig() {
        Predicate<Object> recordServerErrors = result ->
                result instanceof PartnerResponse response
                        && response.statusCode() >= 500;

        return CircuitBreakerConfig.custom()
                .slidingWindowSize(20)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(10))
                .recordResult(recordServerErrors)
                .build();
    }
}
~~~

This snippet illustrates building the configuration directly from the builder. Enum types and API signatures must match the Resilience4j version managed by the project; check the actual dependency's Javadoc or API before use.

When integrating with Spring Cloud CircuitBreaker, you can supply the created CircuitBreakerConfig through the corresponding Resilience4j implementation's configuration mechanism or customizer. Exact registration depends on the Spring Cloud and starter versions in use. The goal is to ensure the factory uses the configuration containing the result predicate for the right instance ID.

If your version lacks **recordResult**, do not try to call a nonexistent method or assume an unsupported YAML property will work on its own. Instead, convert business outcomes that must count as failures into exceptions before they pass through the Circuit Breaker; that approach leverages the more widely supported exception classification policy.

## 4. Configuring the Predicate via application.yml When Supported by the Binder

Some versions of the Spring Boot Resilience4j integration allow configuring the predicate by implementation class name via the **recordResultPredicate** property. Support for binding this property is version-dependent. Confirm the documentation and configuration metadata of the exact version running before using it.

When supported by the binder, the configuration takes this general form:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      partner:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        recordResultPredicate: com.example.resilience.RecordPartnerResultAsFailure
~~~

The predicate class must implement the interface required by your binder version. Illustrative example of a response-checking predicate:

~~~java
package com.example.resilience;

import java.util.function.Predicate;

public class RecordPartnerResultAsFailure
        implements Predicate<Object> {

    @Override
    public boolean test(Object result) {
        if (!(result instanceof PartnerResponse response)) {
            return false;
        }

        return response.statusCode() >= 500;
    }
}
~~~

Package name, constructor, and interface must match the predicate instantiation mechanism of your version. If the binder does not support this property, the YAML setting may be ignored or fail to map as expected. Do not assume every Spring Cloud CircuitBreaker version supports **recordResultPredicate** merely because Resilience4j core has the **recordResult** API.

A practical check is to start the application with the configuration, inspect binding logs, and test a response that the predicate should mark as a failure. Reading the YAML file alone is not enough to confirm the predicate is registered on the Circuit Breaker.

## 5. Distinguishing Result Predicates and Exception Predicates

The two predicate types process two different kinds of input:

| Criterion | Result Predicate | Exception Predicate |
|---|---|---|
| Input | Returned value | Thrown Throwable |
| Purpose | Evaluate whether a response carries a failure meaning | Evaluate whether an exception should count as failure or be ignored |
| Example | Response with status 503 | TimeoutException or IOException |
| Common core API | recordResult(Predicate<Object>) | recordException(Predicate<Throwable>) |
| Alters return value? | No | No |
| Triggers fallback automatically? | No | No |

Example combining both policies at the core configuration level:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .recordResult(result ->
                result instanceof PartnerResponse response
                        && response.statusCode() >= 500)
        .recordException(error ->
                error instanceof java.io.IOException
                        || error instanceof java.util.concurrent.TimeoutException)
        .build();
~~~

The snippet above illustrates independent classification. If you use a custom **recordException**, review the default rules and ignore-exception configuration of your Resilience4j version. An ignored exception will not be counted as a successful call to lower the failure rate.

Do not use a result predicate to replace an exception predicate. If WebClient throws WebClientResponseException for error HTTP responses, the Circuit Breaker receives an exception rather than a PartnerResponse. In that case, the exception policy is where classification belongs, unless the application converts the error into a response value before calling the Circuit Breaker.

## 6. Predicates Only Classify Metrics; They Do Not Turn Results into Caller Errors

This is a common source of confusion. When a result predicate returns true, Resilience4j records that outcome as a failure in Circuit Breaker statistics. That does not mean the original response is automatically replaced with an exception or a fallback.

For example, if a call returns PartnerResponse with status 503 and the predicate flags it as a failure, the caller may still receive that very PartnerResponse. The Circuit Breaker recorded a failure measurement, yet the response is not necessarily converted into an error.

A result predicate does NOT perform the following actions:

- It does not automatically throw an exception to the caller.
- It does not automatically convert the response into another data type.
- It does not automatically invoke Spring Cloud CircuitBreaker's fallback simply because the predicate returned true.
- It does not automatically retry the call.
- It does not automatically alter the HTTP status returned to the end client.

If business logic requires a 503 response to become an exception so the fallback runs, convert the response into an error explicitly before passing through the Circuit Breaker, or handle it after the call according to your design.

Example converting an error response into an exception:

~~~java
Mono<PartnerResponse> remoteCall = webClient.get()
        .uri("/partner")
        .exchangeToMono(response ->
                response.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .map(body -> new PartnerResponse(
                                response.statusCode().value(),
                                body))
        )
        .flatMap(result -> {
            if (result.statusCode() >= 500) {
                return Mono.error(
                        new PartnerUnavailableException(result.message()));
            }
            return Mono.just(result);
        });

return circuitBreaker.run(
        remoteCall,
        error -> fallbackPartnerResponse()
);
~~~

In this example, status codes 500 and above are converted into exceptions. The Reactive Circuit Breaker can then handle the exception via the publisher's fallback mechanism. This is exception-based handling in a reactive flow; do not confuse it with the synchronous API's result predicate automatically applying to every Mono or Flux element.

## 7. Being Careful with WebClient and Response Statuses

WebClient offers several ways to handle HTTP responses. With **retrieve()**, 4xx and 5xx responses are converted into WebClientResponseException errors by default unless the application customizes status handling.

Example:

~~~java
Mono<PartnerResponse> result = webClient.get()
        .uri("/partner")
        .retrieve()
        .bodyToMono(PartnerResponse.class);
~~~

In this case, if the server returns 503, the publisher typically emits an error instead of emitting a PartnerResponse with statusCode equal to 503. The result predicate will not receive that response as a normal value.

If you want to evaluate the status as a value, you can use **exchangeToMono** or an appropriate response-mapping mechanism to convert status and body into a business result type. Then, depending on the adapter and version, verify whether the Circuit Breaker actually applies the result predicate for that execution style.

For reactive adapters, do not assume CircuitBreakerConfig's result predicate evaluates each **onNext** item of a Flux or the **onNext** value of a Mono. Some reactive adapters record success on publisher completion and failure on **onError**; per-value result evaluation may not be supported identically to the synchronous API. If you need to classify responses in a reactive pipeline, the clearest and most controllable approach is to convert business responses that count as errors into exceptions before passing the publisher to **ReactiveCircuitBreaker.run**.

## 8. Designing Predicates Around Business Semantics

Predicates should be short, deterministic, and stable. Avoid writing rules based on unstable message strings or locale-dependent text.

For example, with a payment service response:

~~~java
Predicate<Object> recordPaymentFailure = result ->
        result instanceof PaymentResponse response
                && (response.status() == PaymentStatus.TEMPORARY_UNAVAILABLE
                    || response.status() == PaymentStatus.PROCESSING_ERROR);
~~~

Design guidelines:

- Only classify outcomes indicating the dependency cannot serve requests or is degrading.
- Do not treat normal business errors such as product not found or transaction declined as infrastructure errors if the API contract defines them as valid outcomes.
- Do not rely on free-form message text as the primary criterion when the response already provides a stable status code or enum.
- Safely handle unexpected data types and null values.
- Keep the predicate pure—do not perform network calls, database queries, or operations with side effects.
- Do not log full payloads or sensitive data inside a predicate.
- Document every rule so operations teams understand why a response counts as a failure.

A predicate must not depend on mutable external state such as global variables or calls to other services. If evaluating a result requires additional business context, normalize that data into the response or move classification logic into an explicit step before the Circuit Breaker.

## 9. Impact on the Sliding Window and Circuit Breaker State

When a result predicate flags a response as a failure, that failure measurement enters window statistics. If the failure rate hits the threshold and minimumNumberOfCalls is met, the Circuit Breaker can transition from CLOSED to OPEN.

Example:

- slidingWindowSize is the last 10 calls.
- minimumNumberOfCalls is 5.
- failureRateThreshold is 50%.
- 5 calls have been recorded, of which 3 responses were flagged as failures by the predicate.

The failure rate is:

\[
\frac{3}{5}\times100\%=60\%
\]

The 60% rate exceeds the 50% threshold, so the Circuit Breaker can open the circuit. The response from the fifth call can still be returned to the caller via normal execution; the state transition decision affects subsequent calls.

Also watch the slow call rate. A response marked as successful by the predicate can still be a slow call if its execution duration exceeds **slowCallDurationThreshold**. Conversely, a response marked as a failure by the predicate does not have to be slow.

## 10. Testing Predicates and Operational Observability

Because a predicate encodes critical classification logic, test it with both outcomes considered successful and outcomes considered failures.

Example test scenario table:

| Input | Expected Predicate | Statistical Outcome |
|---|---:|---|
| PartnerResponse status 200 | false | Success |
| PartnerResponse status 404 | false per example policy | Success |
| PartnerResponse status 429 | false per example policy | Success; monitor quota separately |
| PartnerResponse status 503 | true | Failure |
| Result object of another type | false | Success |
| IOException | Result predicate not called | Per exception policy |

The table above reflects only the example predicate treating responses 500 and above as failures. If the API contract defines 429 as a signal that the dependency cannot serve requests, adjust the rule accordingly.

Monitor the following:

- Failure rate and count of calls flagged as failures by the predicate.
- Response counts broken down by business status group.
- Count of Circuit Breaker transitions to OPEN and HALF_OPEN.
- Counts of recorded or ignored exceptions.
- Actual fallback invocation count.
- Discrepancies between responses returned to callers and Circuit Breaker statistical outcomes.

To avoid misleading dashboards, maintain separate business metrics for response statuses. The Circuit Breaker's failure rate does not replace HTTP status reporting or business transaction success rates.

## 11. Common Mistakes

- **Assuming every normal response is a business success**: a response can carry a temporarily-unavailable status without throwing an exception.
- **Assuming a result predicate invokes fallback on its own**: predicates only classify measurements; triggering a fallback requires an error or explicit alternative handling.
- **Confusing result predicates with exception predicates**: one receives the return value, while the other receives a Throwable.
- **Assuming YAML properties are always supported**: binders and adapters vary by version; verify against your exact version.
- **Using a result predicate on a reactive publisher without verification**: the adapter may only record onComplete/onError rather than evaluating every onNext value.
- **Ignoring WebClient.retrieve() default behavior**: 4xx/5xx responses normally become exceptions, so the result predicate may never receive the response object.
- **Treating every non-2xx status as an infrastructure error**: 404 or 409 can be normal business outcomes.
- **Writing predicates with side effects**: making network calls or data queries inside a predicate adds latency and makes classification unpredictable.
- **Failing to test unexpected types or null**: a predicate can throw an exception when encountering an unexpected result.

## 12. Adoption Workflow

When you want to evaluate return results using a predicate in Spring Cloud CircuitBreaker with Resilience4j, follow this sequence:

1. Identify which responses represent technical and business success.
2. Distinguish error-status responses from exceptions thrown by the client.
3. Verify whether your Resilience4j core version supports **recordResult** and whether your active adapter applies it.
4. If using YAML, verify whether the Spring Boot Resilience4j binder version supports **recordResultPredicate**.
5. Write a pure predicate with type checks and clear rules.
6. Test successful responses, responses classified as failures, exceptions, and unexpected result types.
7. Verify the failure rate, Circuit Breaker state, and actual responses received by callers.
8. If the API or adapter does not support result predicates, convert business results that must count as failures into exceptions before the Circuit Breaker and handle them via exception policies and fallbacks.

Result predicates let the Circuit Breaker inspect return-value contents more deeply when supported by your library version and API. They complement exception classification policies while influencing the sliding window's failure rate. By understanding predicate limitations, how WebClient handles statuses, and how reactive adapters behave, development teams can classify dependency health accurately without conflating error metrics, caller responses, and fallback mechanisms.
