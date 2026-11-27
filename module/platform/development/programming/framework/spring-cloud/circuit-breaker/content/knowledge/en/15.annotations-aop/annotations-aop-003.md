# Naming Instances and Linking Them to YAML Configuration

In Resilience4j, each Circuit Breaker is identified by an instance name. This name helps the application distinguish dependencies such as Inventory, Payment, or Shipping, while linking protected calls to their corresponding configuration in `application.yml`.

When using AOP annotations, the name in the `name` attribute of `@CircuitBreaker` is the key Resilience4j uses to look up the instance in the registry. For example, `@CircuitBreaker(name = "inventory")` links to the configuration `resilience4j.circuitbreaker.instances.inventory`. If the name in the annotation and the YAML key do not match, the method may run with default configuration instead of the thresholds expected by the development team.

This lesson focuses on consistent instance naming, inheriting shared configuration, writing fallbacks, and how Spring AOP applies the Circuit Breaker to methods. It also distinguishes Resilience4j annotations from Spring Cloud's `CircuitBreakerFactory` API to avoid confusion between the two integration styles.

## 1. Instance Name as the Linking Key

An application may call multiple dependencies from the same service. Each dependency should have its own Circuit Breaker to track failure rate, slow calls, and state independently.

Example:

| Dependency | Instance Name | Configuration Path |
| --- | --- | --- |
| Inventory | inventory | resilience4j.circuitbreaker.instances.inventory |
| Payment | payment | resilience4j.circuitbreaker.instances.payment |
| Shipping | shipping | resilience4j.circuitbreaker.instances.shipping |

The instance name is used in two places:

1. In Java code, on the annotation or the Circuit Breaker creation API.
2. In `application.yml`, under the `instances` key of the Circuit Breaker configuration.

With an annotation:

~~~java
@CircuitBreaker(name = "inventory")
public InventoryResponse getInventory(String sku) {
    return inventoryClient.getInventory(sku);
}
~~~

Resilience4j uses the name `inventory` to look up the configuration of the corresponding instance. The YAML key must have the same name:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        failureRateThreshold: 40
        slidingWindowSize: 20
~~~

Use short, stable, lowercase names that express the dependency or protected operation. Avoid using Java class names or method names as instance names if they do not clearly describe the dependency.

`inventory` and `Inventory` should not be treated as interchangeable spellings. Keep the exact same string across annotations, configuration, and dashboards.

## 2. Preparing Dependencies for AOP Annotations

Resilience4j has two common integration styles in Spring applications:

- **Annotation AOP:** uses annotations such as `@CircuitBreaker`, `@Retry`, and `@Bulkhead`. Resilience4j creates aspects to intercept method calls and apply policies.
- **Spring Cloud CircuitBreaker API:** uses `CircuitBreakerFactory` to create a Circuit Breaker object and wrap calls with `run` or `execute`.

To use annotations in Spring Boot 3, an application typically needs Actuator, Spring AOP, and the Resilience4j Spring Boot integration:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-aop</artifactId>
    </dependency>

    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-spring-boot3</artifactId>
    </dependency>
</dependencies>
~~~

Use dependency management appropriate for your project's Spring Boot and Resilience4j versions to select compatible artifacts. For Spring Boot 2, the integration artifact has a different name; do not copy the Spring Boot 3 dependency into a Spring Boot 2 project.

If the project uses Spring Cloud CircuitBreaker, Spring Cloud's Resilience4j starter provides the `CircuitBreakerFactory` API. That starter and Resilience4j's AOP annotation integration serve two different usage styles. Do not assume that merely adding the Spring Cloud CircuitBreaker starter activates all AOP annotations. When you intend to use `@CircuitBreaker`, ensure the dependency providing Resilience4j aspects is present.

## 3. Declaring Shared Configuration and Per-Instance Overrides in YAML

Resilience4j lets you declare shared configuration under `configs` and per-instance configuration under `instances`. Each instance can inherit a base configuration and override only the properties that need to differ.

Example:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3

    instances:
      inventory:
        baseConfig: default
        failureRateThreshold: 40
        waitDurationInOpenState: 8s

      payment:
        baseConfig: default
        slidingWindowSize: 50
        minimumNumberOfCalls: 20

      shipping:
        baseConfig: default
~~~

This configuration creates one default rule set and three instances:

- `inventory` inherits the default properties, but opens the circuit at a 40% failure rate and waits 8 seconds before probing.
- `payment` inherits the default configuration, but uses a 50-call window and requires a minimum of 20 samples.
- `shipping` uses the full default configuration.

The structure can be visualized as follows:

~~~text
resilience4j.circuitbreaker
        |
        +-- configs
        |     |
        |     +-- default
        |
        +-- instances
              |
              +-- inventory ---> baseConfig: default
              |                    + override some properties
              |
              +-- payment -----> baseConfig: default
              |                    + override window
              |
              +-- shipping ----> baseConfig: default
~~~

When adding a new dependency, decide explicitly whether it uses the default configuration or needs its own instance. Declaring a YAML key does not automatically protect every HTTP call to that dependency; application code must still invoke the method through the corresponding annotation or `CircuitBreakerFactory`.

## 4. Linking YAML Names with @CircuitBreaker

The `@CircuitBreaker` annotation belongs to the `io.github.resilience4j.circuitbreaker.annotation` package. The `name` attribute specifies the instance name that the aspect uses.

Example of a service calling Inventory:

~~~java
package com.example.order.inventory;

import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final InventoryClient inventoryClient;

    public InventoryService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @CircuitBreaker(
        name = "inventory",
        fallbackMethod = "inventoryFallback"
    )
    public InventoryResponse getInventory(String sku) {
        return inventoryClient.getInventory(sku);
    }

    public InventoryResponse inventoryFallback(
            String sku,
            Throwable cause) {
        return InventoryResponse.unavailable(sku);
    }
}
~~~

The name `inventory` in the annotation links to:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        baseConfig: default
        failureRateThreshold: 40
~~~

When `getInventory` is called through the Spring proxy, Resilience4j's aspect applies the Circuit Breaker named `inventory`. If the instance is configured in YAML, that instance's properties are used when initializing the Circuit Breaker.

The fallback in the example has the same return type as the original method. It accepts the original parameters in the same order, followed by an additional exception parameter at the end. Using `Throwable` illustrates the general signature; in real applications, more specific exception types can be used to distinguish connection errors, Circuit Breaker rejections, or business errors.

## 5. Rules for Writing Fallback Methods

A fallback is an alternative method invoked when a protected call fails or is rejected by the Circuit Breaker. Resilience4j locates the fallback based on the name declared in the annotation and the method signature.

Given the original method:

~~~java
@CircuitBreaker(name = "inventory", fallbackMethod = "inventoryFallback")
public InventoryResponse getInventory(String sku, boolean includeReserved) {
    return inventoryClient.getInventory(sku, includeReserved);
}
~~~

The fallback can be declared as:

~~~java
public InventoryResponse inventoryFallback(
        String sku,
        boolean includeReserved,
        Throwable cause) {
    return InventoryResponse.unavailable(sku);
}
~~~

Rules to keep in mind:

- The fallback has the same or a compatible return type as the original method.
- The original method's business parameters are preserved in the same order.
- The exception parameter is placed last.
- A specific exception type can be used if the fallback should only handle a particular group of errors.
- If no fallback is declared, the exception can be propagated to the caller.
- If the fallback itself throws an exception, the error from the fallback is also propagated up to the calling layer.

Do not return fake data such as zero inventory and let the caller interpret it as real data. Clearly represent an `UNAVAILABLE` status, cached data, or a degraded result. The fallback should accurately reflect business requirements.

Example of a specialized fallback:

~~~java
public InventoryResponse inventoryFallback(
        String sku,
        io.github.resilience4j.circuitbreaker.CallNotPermittedException cause) {
    return InventoryResponse.unavailable(sku);
}
~~~

If using a specialized fallback, ensure that the exception type can actually be passed into the fallback in the library version you are using. If you want to handle multiple error types in one method, you can accept `Throwable` and classify inside it.

## 6. One Instance Name Can Be Used Across Multiple Methods

You can use the same instance across multiple methods if they protect the same dependency and should share statistical state.

~~~java
@Service
public class InventoryService {

    private final InventoryClient inventoryClient;

    public InventoryService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "inventoryFallback")
    public InventoryResponse getBySku(String sku) {
        return inventoryClient.getBySku(sku);
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "inventoryFallback")
    public InventorySummary getSummary(String warehouseId) {
        return inventoryClient.getSummary(warehouseId);
    }

    public InventoryResponse inventoryFallback(String sku, Throwable cause) {
        return InventoryResponse.unavailable(sku);
    }

    public InventorySummary inventoryFallback(
            String warehouseId,
            Throwable cause) {
        return InventorySummary.unavailable(warehouseId);
    }
}
~~~

In this example, both methods use the same name `inventory`. This means they both contribute outcomes to the same Circuit Breaker instance when linked to that instance by the aspect. A heavily failing operation can affect the protection state of the other operation.

If two endpoints have different latency, traffic, or criticality characteristics, consider assigning separate instance names, such as `inventory-read` and `inventory-summary`. Then YAML can configure two independent windows and thresholds.

Do not mechanically create a separate instance for every single method. If all methods call the same dependency and should trip together, sharing one instance may be more appropriate.

## 7. Avoiding Errors from Spring AOP Proxies and Self-Invocation

AOP annotations work through Spring proxies. Calls into a bean from outside pass through the proxy so the aspect can apply the Circuit Breaker.

A common mistake is calling an annotated method from another method in the same class:

~~~java
@Service
public class InventoryService {

    public InventoryResponse load(String sku) {
        return getInventory(sku);
    }

    @CircuitBreaker(name = "inventory")
    public InventoryResponse getInventory(String sku) {
        return inventoryClient.getInventory(sku);
    }
}
~~~

In this example, `load` calls `getInventory` through the object's internal `this`. Self-invocation calls do not go through the Spring proxy, so the aspect may not execute. Consequently, the Circuit Breaker is not applied as expected.

A clearer approach is to place the protected method in another bean and invoke that bean via dependency injection:

~~~java
@Service
public class InventoryGateway {

    private final InventoryClient inventoryClient;

    public InventoryGateway(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "fallback")
    public InventoryResponse getInventory(String sku) {
        return inventoryClient.getInventory(sku);
    }

    public InventoryResponse fallback(String sku, Throwable cause) {
        return InventoryResponse.unavailable(sku);
    }
}
~~~

Another service calls `InventoryGateway` through the Spring-managed bean. The call passes through `InventoryGateway`'s proxy.

Place methods requiring AOP in `public` scope and invoke them via a bean proxy. `private` methods cannot be intercepted by Spring proxy-based AOP as external calls; `final` methods also have restrictions with class-based proxies. Check the proxy type used by your application and avoid designs that rely on internal calls.

## 8. Distinguishing Resilience4j Annotations and Spring Cloud CircuitBreakerFactory

Both integration styles can use the same instance names and Resilience4j configuration groups, but their invocation APIs differ.

| Criterion | Resilience4j annotation | Spring Cloud CircuitBreaker |
| --- | --- | --- |
| Invocation | Attach `@CircuitBreaker` to a method | Create an instance via `CircuitBreakerFactory` |
| Application mechanism | Spring AOP aspect | Wrap a supplier or function via the API |
| Where the name is set | The annotation's `name` attribute | The `create(name)` argument |
| Fallback | `fallbackMethod` in the annotation | Fallback function passed to `run` |
| Best suited for | Spring bean methods declaring policies via annotations | Making protection boundaries explicit in code |

Example of the Spring Cloud CircuitBreaker API:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResponse getInventory(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getInventory(sku),
            error -> InventoryResponse.unavailable(sku)
        );
    }
}
~~~

The name passed to `create` is `inventory`. With the Resilience4j provider, Spring Cloud CircuitBreaker associates this name with the corresponding instance configuration in `application.yml`.

Do not wrap the same call with both an annotation and `CircuitBreakerFactory` without an explicit reason. Nesting two Circuit Breakers can create two sliding windows, two `OPEN` states, and two different fallbacks, making diagnostics harder. Pick one clear protection boundary per dependency.

If an application uses both annotations and the factory in different areas, verify how auto-configuration creates registries and instances in your version. Having the same configuration name does not automatically prove the two integration paths share the same instance lifecycle or state.

## 9. Naming Instances According to Team Conventions

A good naming convention makes configuration, dashboards, and logs easy to read. You can name instances after the dependency:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        baseConfig: default
      payment:
        baseConfig: default
      shipping:
        baseConfig: default
~~~

If a dependency has multiple operation types requiring different thresholds, you can name by dependency and purpose:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        baseConfig: default
      inventory-reservation:
        baseConfig: default
        failureRateThreshold: 30
~~~

In code:

~~~java
@CircuitBreaker(name = "inventory-read")
public InventoryResponse readInventory(String sku) {
    return inventoryClient.read(sku);
}

@CircuitBreaker(name = "inventory-reservation")
public ReservationResult reserve(String sku, int quantity) {
    return inventoryClient.reserve(sku, quantity);
}
~~~

Avoid overly long names or names containing per-request varying values such as user ID, order ID, or tenant ID. An instance is an application-level configuration and statistics unit; creating an instance per request can cause unbounded growth in objects and metrics.

## 10. Verifying That Configuration Is Properly Linked

When a method does not open the circuit at the declared threshold, check in order:

1. Does the annotation import the right package `io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker`?
2. Does the `name` attribute match the key under `resilience4j.circuitbreaker.instances` exactly?
3. Are the AOP dependency and Resilience4j Spring Boot integration present on the classpath?
4. Is the method invoked through a Spring proxy?
5. Is there a self-invocation call from within the same bean?
6. Is the configuration located properly under `resilience4j.circuitbreaker`?
7. Does the instance inherit a `baseConfig` with the right name?
8. Is another configuration or customizer overriding the expected values?
9. Does the fallback have a compatible signature and return type?

Example configuration named `inventory`:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
~~~

The annotation must use the exact same name:

~~~java
@CircuitBreaker(name = "inventory")
public InventoryResponse getInventory(String sku) {
    return inventoryClient.getInventory(sku);
}
~~~

If the annotation uses `name = "inventoryService"` while YAML only has `instances.inventory`, the custom `inventory` configuration will not link to that method. Fix the name at the appropriate declaration source rather than creating unnecessary duplicate YAML keys.

You can inspect metrics and states via Actuator if Micrometer integration is enabled and the required endpoints are exposed. Do not expose all management endpoints to public networks. Exact metric names depend on the Resilience4j and Micrometer versions; query the application's metrics endpoint rather than assuming a fixed name.

## 11. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Method still calls dependency despite exceeding threshold | Annotation is not intercepted by AOP or self-invocation is occurring | Check proxy, AOP dependency, and call path through the bean |
| YAML is not applied | Annotation name differs from YAML instance name | Synchronize the `name` value and the `instances` key exactly |
| Annotation not recognized | Missing Resilience4j Spring Boot integration or wrong package imported | Add the appropriate dependency and use Resilience4j's annotation |
| Fallback does not execute | Wrong name, wrong signature, or incompatible return type | Check original parameters and trailing exception in the signature |
| Two methods affect each other's state | Both use the same instance name | Separate instances if independent policies are needed |
| Dashboard shows unexpected instances | Names are generated dynamically or do not follow convention | Use stable names at the dependency or operation level |
| Circuit Breaker runs twice | Same call is wrapped by both annotation and factory | Choose one clear protection layer |
| New configuration does not take effect immediately | Instance was already created before configuration changed | Clarify the reload mechanism or application instance lifecycle |

## 12. Design Principles

- Use stable, concise instance names that reflect the dependency or operation.
- Keep names in annotations or `create(name)` matching the YAML key exactly.
- Use `configs` to share rules and `instances` to fine-tune each dependency.
- Share an instance across methods only when they truly need the same statistical state.
- Declare fallbacks with return types and parameters compatible with the original method.
- Place protected methods in Spring beans and invoke them through proxies.
- Distinguish Resilience4j AOP annotations from Spring Cloud's `CircuitBreakerFactory` API.
- Avoid unintentionally wrapping the same call with multiple Circuit Breakers.
- Monitor metrics by instance name to identify which dependency is failing.
- Verify dependencies and configuration against the project's exact Spring Boot, Spring Cloud, and Resilience4j versions.

The instance name is the bridge between application code and YAML configuration. When `name` in `@CircuitBreaker` matches the `instances` key, Resilience4j can apply the right sliding window, failure threshold, slow-call threshold, and `OPEN` wait duration to that dependency. Combining naming conventions, well-typed fallbacks, and proper understanding of Spring AOP keeps Circuit Breakers consistent, observable, and easy to operate in Spring Cloud applications.

## References

- [Resilience4j Spring Boot 3 integration](https://resilience4j.readme.io/docs/getting-started-3)
- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Spring Framework AOP proxying mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
