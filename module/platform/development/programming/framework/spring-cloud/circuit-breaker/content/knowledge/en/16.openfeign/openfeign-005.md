# Declaring fallback and fallbackFactory to Inspect Error Causes

Spring Cloud OpenFeign allows declaring a fallback for a Feign client when a remote call fails or the Circuit Breaker rejects the call because it is in the OPEN state. There are two common approaches: the **fallback** attribute points to an alternative implementation class, while **fallbackFactory** points to a factory that receives the error cause and creates the fallback instance.

If you only need to return a fixed degraded result, fallback is the simpler option. If you need to distinguish timeouts, HTTP errors, connection failures, or calls rejected by the Circuit Breaker, fallbackFactory is more useful because its create method receives the Throwable. Whichever approach you use, the fallback must reflect proper business semantics, avoid hiding dependency incidents, and avoid making additional calls to the same failing dependency.

## 1. When Does Fallback Run in Spring Cloud OpenFeign?

A Feign client is an interface describing HTTP calls to another service. When Spring Cloud OpenFeign's Circuit Breaker support is enabled, calls are protected by a Circuit Breaker. If a call throws an error or is rejected because the Circuit Breaker is OPEN, the framework can invoke the fallback declared for the client.

Situations that typically lead to fallback:

- The target service does not respond or encounters a connection error.
- The HTTP client triggers a timeout.
- An HTTP response is converted into an exception by the configured Feign ErrorDecoder.
- The Circuit Breaker is OPEN and rejects new calls.
- Another error is propagated out of a call protected by the Circuit Breaker.

Fallback does not run for every response with unexpected business content. If Feign decodes a response successfully and returns a normal object, the framework generally treats the call as completed normally. To treat a specific response as an error, convert it into an exception using an ErrorDecoder or handle the result according to an appropriate policy.

Overview flow:

~~~mermaid
flowchart TD
    A[Service calls Feign client] --> B[Circuit Breaker]
    B --> C{Call allowed?}
    C -- No --> D[Fallback or fallbackFactory]
    C -- Yes --> E[Feign sends HTTP request]
    E --> F{Result}
    F -- Success --> G[Return decoded response]
    F -- Exception --> D
    D --> H[Return degraded result or error]
~~~

Fallback is caller-side alternative handling. It does not restore the target service, does not automatically retry, and does not roll back an operation that the server may have already executed.

## 2. Prerequisites to Enable Circuit Breaker for OpenFeign

You need Spring Cloud OpenFeign and a corresponding Circuit Breaker implementation. When using Resilience4j, you can add the dependencies via a Spring Cloud BOM compatible with the project's Spring Boot version:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-openfeign</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
~~~

Enable the Circuit Breaker integration in application.yml:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

The application must enable Feign client scanning, typically with @EnableFeignClients on a configuration class or the main application class:

~~~java
@SpringBootApplication
@EnableFeignClients
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

If Circuit Breaker support is not enabled, the fallback or fallbackFactory attribute will not be applied through Spring Cloud OpenFeign's protection flow as expected. Verify that the property is loaded in the active profile and that the implementation starter is on the classpath.

## 3. Declaring the Feign Client

Suppose the order service needs to call the inventory service. The interface defines the inventory lookup operation:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(
        name = "inventory-service",
        contextId = "inventoryClient",
        fallback = InventoryFallback.class
)
public interface InventoryClient {

    @GetMapping("/inventory/{sku}")
    Inventory getInventory(@PathVariable("sku") String sku);
}
~~~

Here:

- name is the target service name or client identifier.
- contextId distinguishes client configuration when the application has multiple Feign clients calling the same service.
- fallback points to the alternative implementation class of the InventoryClient interface itself.
- getInventory is the business method invoked over HTTP.

If using service discovery and load balancing, the application needs the corresponding load balancer dependency. If the client specifies a direct URL in configuration, routing behaves differently. Either way, the Circuit Breaker and fallback are configured on the Feign client using the ID generated by Spring Cloud OpenFeign.

## 4. Using fallback When the Cause Is Not Needed

The fallback class must implement the same interface as the Feign client and be managed by Spring as a bean:

~~~java
import org.springframework.stereotype.Component;

@Component
public class InventoryFallback implements InventoryClient {

    @Override
    public Inventory getInventory(String sku) {
        return Inventory.unavailable(sku);
    }
}
~~~

In the example, Inventory.unavailable is a degraded result defined by the domain model. It can be replaced with cached data, an undetermined status, or a controlled business error.

Advantages of fallback:

- Less code and easy to read.
- Suitable when all error causes share the same fallback response.
- No need to handle Throwable inside the fallback class.

The limitation is that the fallback method does not directly receive the error cause. If you need to record or distinguish a timeout from an OPEN Circuit Breaker, a simple fallback class does not provide enough information to make cause-based decisions.

Do not use fallback to return a value that looks successful but does not reflect reality. For example, unknown inventory does not mean inventory equals 0. Represent the degraded state explicitly so the business layer does not make wrong decisions.

## 5. Using fallbackFactory to Receive the Error Cause

When you need to know why a call failed, declare fallbackFactory on the Feign client:

~~~java
@FeignClient(
        name = "inventory-service",
        contextId = "inventoryClient",
        fallbackFactory = InventoryFallbackFactory.class
)
public interface InventoryClient {

    @GetMapping("/inventory/{sku}")
    Inventory getInventory(@PathVariable("sku") String sku);
}
~~~

The factory implements FallbackFactory<T> where T is the Feign client interface. The create method receives a Throwable and returns an object implementing that interface.

~~~java
import org.springframework.cloud.openfeign.FallbackFactory;
import org.springframework.stereotype.Component;

@Component
public class InventoryFallbackFactory
        implements FallbackFactory<InventoryClient> {

    private static final Logger log =
            LoggerFactory.getLogger(InventoryFallbackFactory.class);

    @Override
    public InventoryClient create(Throwable cause) {
        Throwable reason = cause != null
                ? cause
                : new IllegalStateException("Fallback cause is unavailable");

        return sku -> {
            log.warn(
                    "Inventory fallback activated for sku={}, causeType={}",
                    sku,
                    reason.getClass().getSimpleName()
            );

            return Inventory.unavailable(sku);
        };
    }
}
~~~

The factory receives the cause when creating the fallback implementation. The returned object provides the alternative methods when the Feign client needs to fall back. In the example, the cause is retained to log along with the SKU when the method is invoked.

Use the exact return types defined by the interface. If the Feign method returns Inventory, the fallback must also return Inventory. If the interface has multiple methods, the fallback object must implement all of them.

## 6. Classifying Causes in fallbackFactory

The Throwable may be the direct exception or an exception wrapped inside another cause. Therefore, checking only the outermost exception sometimes misses the root error type. You can traverse the cause chain to locate the exception type of interest.

Example:

~~~java
import java.util.concurrent.TimeoutException;

import feign.FeignException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;

private static <T extends Throwable> T findCause(
        Throwable error,
        Class<T> expectedType) {

    Throwable current = error;

    while (current != null) {
        if (expectedType.isInstance(current)) {
            return expectedType.cast(current);
        }

        Throwable next = current.getCause();
        if (next == current) {
            break;
        }
        current = next;
    }

    return null;
}
~~~

This helper can be used inside the factory:

~~~java
@Override
public InventoryClient create(Throwable cause) {
    CallNotPermittedException rejected =
            findCause(cause, CallNotPermittedException.class);

    TimeoutException timeout =
            findCause(cause, TimeoutException.class);

    FeignException httpFailure =
            findCause(cause, FeignException.class);

    if (rejected != null) {
        log.warn("Inventory call rejected because circuit breaker is OPEN");
    } else if (timeout != null) {
        log.warn("Inventory call timed out");
    } else if (httpFailure != null) {
        log.warn("Inventory HTTP call failed with status={}",
                httpFailure.status());
    } else {
        log.warn("Inventory call failed; causeType={}",
                cause == null ? "unknown" : cause.getClass().getName());
    }

    return sku -> Inventory.unavailable(sku);
}
~~~

The exception types above are common examples. Actual exceptions depend on the HTTP client, ErrorDecoder, Circuit Breaker adapter, and library versions. A timeout may be represented by another exception type or sit deeper in the cause chain. Check actual logs before writing classification rules.

Do not rely solely on error messages to identify errors. Messages can vary by version, locale, or implementation. Prefer exception types, HTTP status codes, and stable error codes.

## 7. Comparing fallback and fallbackFactory

| Criterion | fallback | fallbackFactory |
|---|---|---|
| Configuration value | Class implementing the Feign interface | Class implementing FallbackFactory |
| Receives Throwable | No | Yes, in create(Throwable) |
| How alternative behavior is created | A single fallback bean | Factory creates the fallback object |
| Suitable when | The same alternative response applies to all errors | Need to classify errors or log by cause |
| Complexity | Low | Higher |
| Example | Return a generic unavailable status | Timeout uses cache, Circuit Breaker OPEN returns a temporary status |

For a given Feign client, choose the declaration that fits the requirement. Do not declare both fallback and fallbackFactory on the same client. Both must produce alternative behavior compatible with the interface.

If fallbackFactory simply returns the exact same result for every error without recording the cause, the benefit of a factory is negligible. Conversely, if you need to observe the cause or differentiate degradation policies, a factory is the clearer choice.

## 8. Designing Fallback by Error Type

Not all errors should produce the same response. For example, with the inventory service:

| Cause | Potentially Appropriate Handling |
|---|---|
| Circuit Breaker OPEN | Return temporarily unavailable status or cached data |
| Timeout | Use cache if data is still within freshness limits |
| Connection error | Return degraded status and record connection failure |
| HTTP 503 | May use cache or indicate service busy |
| HTTP 404 | Check business semantics; product not found may be a valid result |
| Authentication error 401/403 | Report configuration or access error; do not pretend data does not exist |
| Data or mapping error | Record integration error and handle according to business policy |

FallbackFactory can branch based on the cause:

~~~java
@Override
public InventoryClient create(Throwable cause) {
    boolean circuitOpen =
            findCause(cause, CallNotPermittedException.class) != null;

    boolean timedOut =
            findCause(cause, TimeoutException.class) != null;

    return sku -> {
        if (circuitOpen || timedOut) {
            return inventoryCache.findFresh(sku)
                    .orElseGet(() -> Inventory.unavailable(sku));
        }

        return Inventory.unavailable(sku);
    };
}
~~~

The snippet assumes inventoryCache is a cache component provided by the application. Set a freshness limit for cached data and clearly indicate the data source in the result if the business logic needs to know it is stale data.

Do not call InventoryClient itself again inside the fallback. Doing so can create a loop calling back into the same failing dependency, increasing load and preventing the fallback from acting as a backup path.

## 9. Fallback Does Not Replace ErrorDecoder

Feign's ErrorDecoder converts unsuccessful HTTP responses into exceptions. Fallback or fallbackFactory handles exceptions emerging from the protected call.

The two components have different responsibilities:

- ErrorDecoder decides which HTTP responses are represented as exceptions and which exception types are created.
- FallbackFactory receives the failure cause that exited the call layer and creates an alternative response object.
- Circuit Breaker records the call outcome according to its policy and integration order.
- The business layer decides whether to accept degraded data or return an error to the user.

An example custom ErrorDecoder can preserve status information:

~~~java
import feign.Response;
import feign.codec.ErrorDecoder;

public class PartnerErrorDecoder implements ErrorDecoder {

    @Override
    public Exception decode(String methodKey, Response response) {
        return new PartnerServiceException(
                methodKey,
                response.status(),
                "Partner service returned an unsuccessful response"
        );
    }
}
~~~

Afterward, fallbackFactory can look for PartnerServiceException in the cause chain to read the status and choose an appropriate response. The ErrorDecoder configuration must be bound to the right Feign client via Spring Cloud OpenFeign's configuration mechanism.

Avoid converting every HTTP status into the exact same exception without context. Preserving structured status or error codes helps fallback and monitoring distinguish business errors from infrastructure failures.

## 10. Fallback and Circuit Breaker Metrics

Fallback can help callers receive a controlled response, but it should not let dashboards obscure dependency incidents. Distinguish:

- Remote calls that succeeded.
- Remote calls that failed and used fallback.
- Calls rejected because the Circuit Breaker is OPEN.
- Fallbacks that threw errors themselves.

Tracking fallback counts and causes separately helps operations teams see what percentage of requests are served with degraded data. An API might still return HTTP 200 to callers thanks to cache, even while the downstream dependency has been failing for a long time.

Fallbacks also need time and resource bounds. If a fallback queries another cache or database, that backup path can become a new dependency. Prefer already-available data, lightweight operations, and appropriate protection policies.

Do not log full response bodies, tokens, or personal information when recording causes. Logging exception type, status, client ID, operation ID, and correlation ID is usually enough for investigation without exposing unnecessary data.

## 11. Common Mistakes When Declaring Fallbacks

- **Forgetting to enable Circuit Breaker support**: fallback is not triggered via OpenFeign integration if the property is not enabled or the starter is missing.
- **Fallback class not implementing the right interface**: return types and method signatures must match the Feign client.
- **Fallback bean outside Spring scan scope**: the framework cannot instantiate the fallback bean.
- **FallbackFactory not implementing the right generic type**: the generic parameter must be the corresponding Feign client interface.
- **Assuming Throwable is always the root exception**: the cause may be wrapped in multiple layers; traverse the cause chain.
- **Classifying by error message**: messages are less stable than exception types or error codes.
- **Calling the Feign client again inside fallback**: can create loops and continue adding load to the failing dependency.
- **Returning fake data as fresh data**: the business layer may make incorrect decisions.
- **Failing to distinguish HTTP 404 from infrastructure errors**: the response may represent a normal business result.
- **Letting fallback hide failure metrics**: track fallbacks and Circuit Breaker state separately.
- **Declaring both fallback and fallbackFactory on the same client**: choose one appropriate alternative mechanism.
- **Using fallback as a retry mechanism**: fallback does not automatically retry the primary operation.

## 12. Implementation and Verification Workflow

When integrating fallback or fallbackFactory for a Feign client, follow this sequence:

1. Add Spring Cloud OpenFeign and a Circuit Breaker implementation compatible with your Spring Boot version.
2. Enable spring.cloud.openfeign.circuitbreaker.enabled.
3. Declare the Feign interface with fallback or fallbackFactory.
4. Ensure the fallback class or factory is a Spring bean and implements the interface properly.
5. If error classification is needed, implement fallbackFactory and traverse the cause chain safely.
6. Configure ErrorDecoder if specific HTTP responses need to be converted into structured exceptions.
7. Build meaningful business fallback behavior that does not call back into the failing dependency and does not fabricate data.
8. Test success, timeout, HTTP error, connection error, and Circuit Breaker OPEN scenarios.
9. Verify that the caller receives the expected data type or error, and that metrics accurately record fallback counts.
10. Monitor error causes and fallback rates in the live environment.

fallback fits when a simple alternative implementation is enough. fallbackFactory fits when you need to inspect the Throwable to classify causes, log with context, or choose degraded data based on error type. When Circuit Breaker is enabled for OpenFeign, beans are declared properly, and each scenario is tested, the application can maintain controlled responses while preserving visibility into downstream dependency failures.
