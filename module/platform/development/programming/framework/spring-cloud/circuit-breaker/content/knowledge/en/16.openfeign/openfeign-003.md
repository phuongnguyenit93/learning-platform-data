# Customizing Names with CircuitBreakerNameResolver

When Spring Cloud CircuitBreaker is enabled for OpenFeign, each Feign client method can be protected by its own circuit breaker. The framework needs to generate a name to identify that circuit breaker. This name is used when looking up Resilience4j configuration, recording metrics, emitting events, and diagnosing calls.

Spring Cloud OpenFeign provides `CircuitBreakerNameResolver` so applications can customize how names are generated from the client and the invoked method. A stable naming rule accurately maps configuration to each call, prevents confusion across clients or overloaded methods, and keeps dashboards and logs readable.

## How Are Circuit Breakers Named?

When circuit breaker support is enabled for OpenFeign, the framework generates a name for each protected call. The default naming rule has changed across Spring Cloud generations. Some versions use a combination of client and method; newer versions may also include parameter types in the name to distinguish overloaded methods.

Therefore, do not assume the generated name is always identical across all versions. If the application requires a specific convention, provide a `CircuitBreakerNameResolver` bean and verify the actual name generated in the version being used.

The resolver receives three pieces of information:

| Parameter | Meaning |
|---|---|
| `feignClientName` | The client name passed into the resolver by OpenFeign. |
| `target` | The Feign Target describing the client interface and call destination. |
| `method` | The method on the Feign interface being invoked. |

The resolver contract returns a name string. That string must be stable across runs and usable consistently in configuration, metrics, and logs.

## Why Customize Names?

Suppose an application has two Feign clients calling an inventory service: one client reads quantities for display, and another client reserves products. These two flows have different failure characteristics and fallback policies. If names are based only on methods like `get` or `execute`, the clients may generate duplicate or hard-to-distinguish names.

A good naming rule should meet these criteria:

- Include a component identifying the Feign client.
- Include the protected method name.
- Distinguish overloaded methods when needed.
- Contain no per-request dynamic data such as SKU, user ID, or order ID.
- Map easily to instance names in Resilience4j configuration.
- Remain stable across application restarts and across multiple replicas.

Do not generate circuit breaker names from full URLs or request parameters. If every SKU produces a different name, the application can create a huge number of instances and metric series. Each instance also receives only a fraction of traffic, leaving the sliding window with too few samples to evaluate failures and slow calls.

## Enabling Circuit Breaker for OpenFeign

The application needs the OpenFeign starter and the corresponding Spring Cloud CircuitBreaker implementation, such as Resilience4j. Then enable OpenFeign's circuit breaker feature:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

Example of a Feign client:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "inventory-service")
public interface InventoryClient {

    @GetMapping("/inventory/{sku}")
    InventoryResponse getBySku(@PathVariable("sku") String sku);
}
~~~

When `getBySku` is called, OpenFeign creates a call protected by a circuit breaker according to the active configuration. The resolver allows the application to control the name bound to this call.

## Implementing CircuitBreakerNameResolver

The following example generates names from the client, method, and parameter types. Including parameter types distinguishes overloaded methods with the same name.

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

import feign.Target;
import org.springframework.cloud.openfeign.CircuitBreakerNameResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FeignCircuitBreakerNamingConfiguration {

    @Bean
    public CircuitBreakerNameResolver circuitBreakerNameResolver() {
        return (feignClientName, target, method) -> {
            String parameterTypes = Arrays.stream(method.getParameterTypes())
                    .map(Class::getTypeName)
                    .collect(Collectors.joining("_"));

            String rawName = feignClientName + "_" + method.getName()
                    + (parameterTypes.isEmpty() ? "" : "_" + parameterTypes);

            return rawName.replaceAll("[^A-Za-z0-9_-]", "_");
        };
    }
}
~~~

The resolver builds the name from three components:

1. The Feign client name passed in by the framework.
2. The method name.
3. The parameter types in declaration order.

Afterward, characters other than letters, digits, underscores, and hyphens are replaced with underscores so the name is easy to use in configuration. This is an illustrative convention; the application should inspect normalized names to avoid two different signatures accidentally turning into the same string.

For `getBySku(String sku)` on client `inventory-service`, the name could be:

~~~text
inventory-service_getBySku_java_lang_String
~~~

If the interface has two methods with the same name but different parameter types, the signature portion produces distinct names. There is no need to include the actual SKU value in the name; parameter types are sufficient to distinguish at the method level.

The `target` parameter provides additional information about the interface and Feign target. If the system has clients sharing a service name that need separate policies, you can use appropriate target information to create distinct namespaces. Choose stable identifying components that do not depend on dynamic URLs or runtime data.

## Applying a Resolver Globally or to a Single Feign Client

There are two ways to organize the bean depending on the desired scope.

**Global resolver:** place the bean in a Spring configuration scanned by the application. The resolver can then be used for Feign clients across the application. This approach suits cases where all clients share one naming convention.

**Per-client resolver:** declare a separate configuration class and attach it to the `configuration` attribute of `@FeignClient`. For example:

~~~java
@FeignClient(
        name = "inventory-service",
        configuration = InventoryFeignNamingConfiguration.class
)
public interface InventoryClient {

    @GetMapping("/inventory/{sku}")
    InventoryResponse getBySku(@PathVariable("sku") String sku);
}
~~~

The referenced configuration class:

~~~java
public class InventoryFeignNamingConfiguration {

    @Bean
    public CircuitBreakerNameResolver circuitBreakerNameResolver() {
        return (feignClientName, target, method) ->
                feignClientName + "_" + method.getName();
    }
}
~~~

If the configuration is meant only for one client, place the configuration class in a package not scanned as a global configuration by the main application's component scan. If the bean is accidentally brought into the main context, the rule may apply more broadly than intended. When multiple custom rules are needed, organize them clearly per client and verify the bean scopes Spring creates.

Do not declare multiple global beans of the resolver type without clearly determining which bean is used. If multiple configurations exist, avoid bean conflicts or conditional bean creation that prevents the intended resolver from being selected.

## Mapping Resolver Names to Resilience4j Configuration

The name returned by the resolver is the key used to look up instance configuration. For example, if the resolver generates `inventory-service_getBySku_java_lang_String`, the corresponding instance can be configured in `application.yml`:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-service_getBySku_java_lang_String:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Ensure the name under `instances` matches the exact string returned by the resolver after normalization. If the name does not match, the custom configuration may not be applied as expected and the call may fall back to the default configuration.

When changing naming rules, review these items together:

- Instance keys in `resilience4j.circuitbreaker.instances`.
- TimeLimiter configurations or related policies if they are bound to the same name.
- Dashboards, alerts, and metric queries filtering by the old name.
- Logs, traces, or operational documentation referencing the circuit breaker name.

Avoid arbitrarily renaming resolver rules between releases. Renaming can cause old configuration to stop matching and create new metric series, breaking historical charts.

## Distinguishing Client Name, contextId, and Circuit Breaker Name

These concepts are related but not identical:

| Concept | Role |
|---|---|
| `name` in `@FeignClient` | The service or client name OpenFeign uses to determine the target. |
| `contextId` in `@FeignClient` | Identifier for the Feign client's dedicated configuration context, useful when multiple clients call one service with different configurations. |
| Name returned by `CircuitBreakerNameResolver` | Circuit breaker instance name for the protected call. |

Do not assume `contextId` automatically becomes the circuit breaker name. The resolver receives the arguments provided by the framework; check `feignClientName`, `target`, and `method` in the version in use and choose an appropriate rule. If two clients need separate circuit breakers, ensure the identifying component in the name does not collide.

## Avoiding Duplicate Names and High Cardinality

Duplicate names can cause two different calls to share the same configuration or circuit breaker state. This is especially dangerous when a read operation can fall back to cache while a write operation must return an error when the outcome cannot be confirmed.

Some naming approaches prone to problems:

| Rule | Risk |
|---|---|
| Using only the method name | Two Feign clients both having `getById` can collide. |
| Using only the service name | Methods in the same client share one instance even when they may need different policies. |
| Using the full URL | URLs may contain path variables, query strings, or vary by environment. |
| Using runtime parameters | Every request can generate a new name and cause metric cardinality to explode. |
| Using UUIDs or timestamps | Names are unstable and cannot be mapped to configuration consistently. |

An easy-to-manage rule usually combines the client name with the method name; add parameter types if overloads exist. If multiple clients share the same service name but need different policies, add a stable client identifier. After normalization, verify the uniqueness of the generated names.

## Observing Circuit Breaker Names in Operations

The name returned by the resolver can appear in metrics, events, or logs related to the circuit breaker. Use this name to answer operational questions:

- Which circuit breaker is currently OPEN?
- Which Feign method has an increasing failure rate or slow call rate?
- Which calls are failing fast because the circuit is OPEN?
- Which method is using fallback frequently?
- Which instance configuration needs tuning?

Track successful, failed, slow, and rejected calls, along with `CLOSED`, `OPEN`, and `HALF_OPEN` states. For clients with varying traffic patterns, separating names by method helps pinpoint the exact flow experiencing issues.

A circuit breaker name is a label with a finite value domain. Do not include user ID, SKU, order ID, request ID, or query values in the name. Detailed data can be recorded in logs or traces according to application policy; metrics require stable labels for effective aggregation.

## Testing Naming Rules

Before putting a resolver into production, test these cases:

| Case | Result to Verify |
|---|---|
| A client with a simple method | Name contains the expected client and method. |
| Two clients with methods of the same name | Names do not collide when separate policies are needed. |
| An interface with overloaded methods | Parameter type portion distinguishes the signatures. |
| Method with no parameters | Name has no superfluous signature segment or confusing separators. |
| Parameter type is a nested class or array | Normalized name remains stable without collisions. |
| Client name contains hyphens or special characters | Normalized name is valid and matches configuration. |
| Changing the resolver rule | Resilience4j configuration and dashboards are updated in sync. |
| Running multiple replicas | The same client and method produce the exact same name across all replicas. |

You can write unit tests directly for the resolver by constructing mock values for client, target, and method. Then verify the resulting string across different signatures. In integration tests, enable circuit breaker for OpenFeign, invoke a method, and observe the actual instance name in logs or metrics. This confirms that the framework actually used the intended resolver rather than only testing the name-building function in isolation.

## Implementation Workflow

1. Enable circuit breaker for OpenFeign and confirm which Spring Cloud CircuitBreaker implementation is active.
2. Choose a naming convention based on client and method; include parameter types when overloads must be distinguished.
3. Implement a `CircuitBreakerNameResolver` bean globally or in a Feign client's dedicated configuration.
4. Normalize names with a stable rule and check for potential collisions after normalization.
5. Use the exact generated name as the instance key in Resilience4j configuration.
6. Update metrics, dashboards, alerts, and documentation whenever naming rules change.
7. Test multiple clients, overloaded methods, clients sharing a service name, and multiple replicas.

`CircuitBreakerNameResolver` is the extension point for controlling the identity of circuit breakers created by OpenFeign. When names stably reflect the client and method, Resilience4j configuration maps accurately, metrics stay readable, and call flows with different policies do not accidentally share state. Keep names bounded, define bean scope clearly, and verify actual names in your application's Spring Cloud version.
