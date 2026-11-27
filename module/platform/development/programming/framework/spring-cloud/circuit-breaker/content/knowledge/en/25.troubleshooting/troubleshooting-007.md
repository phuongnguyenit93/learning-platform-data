# Annotation Has No Effect Due to Self-Invocation or Missing AOP

When using Resilience4j's `@CircuitBreaker` annotation in a Spring application, an annotated method may still invoke the dependent service directly without the circuit breaker opening, running the fallback, or incrementing metrics. Two common causes are that the method is called internally within the same bean (self-invocation), bypassing the Spring AOP proxy, or the application lacks the required AOP configuration to register the annotation-handling aspect.

For the annotation to take effect, the method must be called through a Spring proxy and the Resilience4j aspect must be present in the ApplicationContext. Check dependencies, how Spring creates beans, proxy type, method visibility, and the actual call path. If you prefer not to rely on AOP, you can use the programmatic API of Spring Cloud CircuitBreaker or Resilience4j to wrap calls explicitly.

## How Does the Annotation Work Through Spring AOP?

The `@CircuitBreaker` annotation does not modify method bytecode on its own. Resilience4j provides an aspect integrated with Spring AOP. When a bean is created and a method is invoked through a proxy, the aspect detects the annotation, looks up the circuit breaker configuration by name, and executes the call through the breaker.

High-level processing flow:

~~~mermaid
flowchart TD
    A[Bean A managed by Spring] --> B[Caller invokes bean through proxy]
    B --> C[Resilience4j CircuitBreakerAspect]
    C --> D[Read @CircuitBreaker and instance name]
    D --> E[Execute call through circuit breaker]
    E --> F{Call outcome}
    F -->|Success| G[Return result]
    F -->|Exception or OPEN circuit| H[Fallback if present]
~~~

When a caller invokes the bean directly through the proxy object, the aspect has a chance to intercept the call before the target method runs. If a method invokes another method via `this.otherMethod()`, the internal call executes on the target object and does not pass back through the proxy. The aspect is not invoked a second time, so the annotation on `otherMethod` is not applied on that call path.

This is a characteristic of proxy-based AOP in Spring. Placing the annotation in the right spot is not enough; what matters is whether the call passes through the proxy.

## Recognizing Self-Invocation Errors

The example below has two methods in the same service:

~~~java
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    public Inventory findForOrder(String sku) {
        // Internal call does not go through the Spring proxy.
        return findFromRemote(sku);
    }

    @CircuitBreaker(
            name = "inventoryRead",
            fallbackMethod = "inventoryFallback"
    )
    public Inventory findFromRemote(String sku) {
        return inventoryClient.fetch(sku);
    }

    public Inventory inventoryFallback(String sku, Throwable error) {
        return Inventory.unavailable(sku);
    }
}
~~~

When another bean calls `inventoryService.findForOrder(sku)`, the external call passes through the proxy, but `findForOrder` is not annotated. Next, `findForOrder` calls `this.findFromRemote(sku)` on the target object itself. Because the second call bypasses the proxy, the Resilience4j aspect never runs for `findFromRemote`.

Common symptoms:

- Exceptions from the dependent service propagate straight to the caller.
- The fallback declared in the annotation is never invoked.
- Failure rate, slow-call rate, or call counts for the instance do not increase as expected.
- The circuit breaker does not change state even though downstream is failing.
- Calling the annotated method directly from another bean works normally.

Do not conclude that the annotation or Resilience4j configuration is broken based solely on an internal call. Trace the call path to determine whether the method is called from another bean or from the same object.

## How to Fix Self-Invocation: Extract the Protected Method into a Separate Bean

The clearest and most maintainable fix is to move the protected dependency call into a separate Spring bean. When the business service invokes this bean via dependency injection, the call passes through the proxy and the aspect can apply.

~~~java
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import org.springframework.stereotype.Service;

@Service
public class ProtectedInventoryClient {

    private final InventoryClient inventoryClient;

    public ProtectedInventoryClient(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @CircuitBreaker(
            name = "inventoryRead",
            fallbackMethod = "inventoryFallback"
    )
    public Inventory find(String sku) {
        return inventoryClient.fetch(sku);
    }

    public Inventory inventoryFallback(String sku, Throwable error) {
        return Inventory.unavailable(sku);
    }
}
~~~

The business service uses the Spring-managed bean:

~~~java
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ProtectedInventoryClient protectedInventoryClient;

    public OrderService(
            ProtectedInventoryClient protectedInventoryClient) {
        this.protectedInventoryClient = protectedInventoryClient;
    }

    public OrderDecision check(String sku) {
        Inventory inventory = protectedInventoryClient.find(sku);
        return OrderDecision.from(inventory);
    }
}
~~~

Here, `OrderService` invokes `ProtectedInventoryClient` through the injected bean. Spring provides the client proxy and the Resilience4j aspect intercepts `find`. Business logic does not need to know proxy details.

Place the circuit breaker at the boundary calling the dependent service. This keeps the protected scope clear, easy to test, and avoids a single internal method handling business logic while calling itself across layers.

## Alternative Approaches and Their Limitations

Self-invocation can be addressed in several ways, though not all are recommended as defaults:

| Approach | How It Works | Notes |
|---|---|---|
| Separate bean | Move the protected method into another Spring bean and inject that bean. | Recommended; clear proxy boundary. |
| Inject self proxy | Inject the bean's own proxy and call the method via the proxy reference. | Can work, but risks circular dependencies and complicates structure. |
| Use `AopContext.currentProxy()` | Retrieve the current proxy and invoke the method through it. | Requires enabling `exposeProxy`; tightly couples code to AOP and is unsuitable as a default. |
| Use programmatic API | Wrap the supplier or publisher directly with the circuit breaker. | Explicit; does not depend on annotation interception. |

If using `AopContext.currentProxy()`, Spring must be configured to expose proxies, such as via `@EnableAspectJAutoProxy(exposeProxy = true)` in appropriate configuration. Calling the proxy from inside the bean couples source code to the AOP mechanism and requires casting. Only use it when there is a specific architectural reason.

Do not use `new InventoryService()` or manually instantiate objects via constructors where annotations are expected. Manually created objects are not managed in the Spring ApplicationContext, so they have no proxy and receive no aspects, transactions, or other proxy-based behaviors.

## Check Dependencies and AOP Configuration

Resilience4j annotations require the Spring support library and corresponding aspect. For Spring Boot 3, the usual dependency is `resilience4j-spring-boot3`; for Spring Boot 2, use a compatible starter such as `resilience4j-spring-boot2`. Never mix artifacts intended for two different Spring Boot generations.

Maven example for Spring Boot 3:

~~~xml
<dependencies>
    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-spring-boot3</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-aop</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Versions should be managed via a BOM or dependency management compatible with your project's Spring Boot and Resilience4j versions. Do not copy an arbitrary version from an example into an application running a different release train.

Roles of the dependencies:

- `resilience4j-spring-boot3` provides Resilience4j integration with Spring Boot 3, configuration binding, and the annotation aspect.
- `spring-boot-starter-aop` provides Spring AOP infrastructure and proxying.
- `spring-boot-starter-actuator` supports health, metrics, and application observability; it does not replace the AOP aspect itself.

With Spring Boot auto-configuration and the appropriate starter, manually declaring `@EnableAspectJAutoProxy` is usually unnecessary. If a Spring application does not use auto-configuration or configures AOP manually, enable the appropriate proxy infrastructure. Adding `@EnableAspectJAutoProxy` without the Resilience4j aspect will not make `@CircuitBreaker` work on its own.

If the annotation is unrecognized at compile time, check the dependency containing the annotation. If the annotation compiles yet produces no interception at runtime, check the starter, aspect, AOP infrastructure, and whether the bean is managed by Spring.

## Verify That the Bean Is Spring-Managed and Proxied

A class annotated with `@Service` or `@Component` normally becomes a Spring bean if its package is covered by component scanning. However, if the application creates an instance with `new`, or component scan excludes the package, that bean has no proxy.

You can check the bean at runtime:

~~~java
import org.springframework.aop.support.AopUtils;
import org.springframework.stereotype.Component;

@Component
public class ProxyDiagnostics {

    private final ProtectedInventoryClient inventoryClient;

    public ProxyDiagnostics(ProtectedInventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    public void logProxyStatus() {
        boolean proxy = AopUtils.isAopProxy(inventoryClient);
        boolean classProxy = AopUtils.isCglibProxy(inventoryClient);
        boolean jdkProxy = AopUtils.isJdkDynamicProxy(inventoryClient);

        log.info(
                "inventoryClient: proxy={}, cglib={}, jdk={}",
                proxy,
                classProxy,
                jdkProxy
        );
    }
}
~~~

This snippet illustrates checking whether the injected object is an AOP proxy. `AopUtils.isAopProxy` returning true does not by itself prove the Resilience4j aspect was applied; the bean could be proxied for transactions or another aspect. Combine this with checking dependencies, logs, and actual circuit breaker behavior.

Do not log the entire proxy object or sensitive configuration details. Log only the proxy type and the bean under diagnosis.

## Method Visibility and Proxy Types

Spring AOP generally uses JDK dynamic proxies or CGLIB class proxies:

- **JDK dynamic proxy** creates an interface-based proxy. Callers usually need to access the method through an interface implemented by the proxy.
- **CGLIB class proxy** generates a subclass of the target class to intercept calls. Classes and methods cannot be `final` if overriding is required for interception.
- **Private methods** cannot be invoked through the proxy in the manner needed for aspect interception.
- **Static methods** are not instance calls through a proxy.
- Package-private/protected methods may behave differently depending on proxy type and configuration; public methods on Spring beans are the most predictable choice.

For example, if a bean uses a JDK proxy and the annotated method is not declared on the interface used by the caller, the caller may not invoke it through the proxy as expected. If a class or method is `final`, CGLIB cannot override it for interception.

To minimize hard-to-diagnose issues, place annotations on `public` methods of Spring beans, ensure callers invoke through the appropriate interface/proxy, and avoid `final` classes/methods when using class-based proxies.

## Instance Configuration Must Match the Annotation Name

The name in `@CircuitBreaker(name = "inventoryRead")` must match the instance name in Resilience4j configuration if you intend to use a custom policy:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

If the names do not match, the application may not apply the custom configuration the team expects. During investigation, verify exact casing and instance names. Never use names that vary per request such as SKU or user ID.

The fallback configuration in the annotation must point to a compatible method. For synchronous methods:

~~~java
@CircuitBreaker(name = "inventoryRead", fallbackMethod = "inventoryFallback")
public Inventory find(String sku) {
    return inventoryClient.fetch(sku);
}

public Inventory inventoryFallback(String sku, Throwable error) {
    log.warn("Inventory lookup failed", error);
    return Inventory.unavailable(sku);
}
~~~

The fallback normally accepts the same business parameters as the original method plus an exception parameter at the end; the return type must match the protected method. You can declare overloaded fallback methods for specific exception types if custom handling is needed. If the fallback signature does not match, errors may surface only at runtime when the aspect resolves the fallback method.

For reactive methods, the fallback must preserve the corresponding reactive return type—for instance, if the method returns `Mono<Inventory>`, the fallback must also return `Mono<Inventory>`. Do not return a synchronous object or call `block()` to force a reactive stream into synchronous execution.

## Resilience4j Annotation and Spring Cloud CircuitBreaker Are Two Different Integrations

The naming is easy to confuse:

| Usage | Mechanism |
|---|---|
| `@CircuitBreaker` from `io.github.resilience4j.circuitbreaker.annotation` | Resilience4j aspect using Spring AOP to intercept methods called through a proxy. |
| Spring Cloud CircuitBreaker `CircuitBreakerFactory` | Programmatic API that creates circuit breakers and wraps suppliers/callables. |
| `ReactiveCircuitBreakerFactory` | Programmatic API protecting `Mono`/`Flux` under the reactive abstraction. |

Spring Cloud CircuitBreaker provides abstractions and factories for integrating backends like Resilience4j. The `@CircuitBreaker` annotation is Resilience4j's annotation mechanism, not a generic annotation automatically provided by every Spring Cloud CircuitBreaker backend.

If an application uses the Spring Cloud CircuitBreaker factory, calls can be protected explicitly:

~~~java
public Inventory find(String sku) {
    return circuitBreakerFactory.create("inventoryRead").run(
            () -> inventoryClient.fetch(sku),
            error -> Inventory.unavailable(sku)
    );
}
~~~

This programmatic approach does not rely on annotation proxy interception, so it avoids self-invocation bugs. However, ensure the factory is properly injected and the fallback handles errors according to business policy.

Avoid stacking both the annotation and a programmatic circuit breaker wrapper on the same call unintentionally. Two circuit breaker layers can have separate sliding windows, metrics, fallbacks, and states, making diagnosis harder.

## Diagnostic Procedure When the Annotation Has No Effect

Check in order to isolate the missing layer:

1. **Verify the annotation:** use the exact import `io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker`, not another class or annotation with the same name.
2. **Verify dependencies:** confirm the application has the Resilience4j starter compatible with Spring Boot and Spring AOP infrastructure.
3. **Verify the bean:** confirm the class is instantiated and injected by Spring, not manually constructed with `new`.
4. **Verify the proxy:** confirm the bean used by the caller is a proxy; check JDK/CGLIB proxy type and interface coverage.
5. **Verify the call path:** confirm calls to the protected method come from another bean through the proxy, not self-invocation.
6. **Verify the method:** prefer `public` instance methods; avoid `private`, `static`, `final`, or non-interceptable methods.
7. **Verify the instance name:** confirm the annotation name matches the Resilience4j configuration.
8. **Verify the fallback:** confirm parameter signature and return type compatibility; ensure the fallback does not mask bugs with fake data.
9. **Verify sample count:** confirm the circuit breaker reaches `minimumNumberOfCalls` before rate evaluation.
10. **Check metrics and state:** inspect call counts, failure rate, slow-call rate, and OPEN/CLOSED/HALF_OPEN state.

Symptom table for quick isolation:

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Annotation compiles but has no effect | Missing Resilience4j aspect or AOP starter. | Dependency tree and auto-configuration. |
| Works when called from controller, fails when called from another method in the same class | Self-invocation bypasses proxy. | Call graph and bean boundaries. |
| Bean is not a proxy | Manually instantiated object, package not scanned, or missing AOP. | `ApplicationContext` and `AopUtils`. |
| Proxy exists but circuit breaker does not change | Aspect not registered, method not intercepted, or mismatched instance name. | Logs, dependencies, and per-instance metrics. |
| Fallback never runs | Wrong fallback signature or exception does not pass through protected method. | Parameter types, return type, and call path. |
| Circuit stays CLOSED despite many failing calls | Below `minimumNumberOfCalls` or errors classified as non-failures. | Metrics and exception classification. |

## Testing to Prove Proxy and Circuit Breaker Actually Work

Unit tests invoking an object created via `new` usually do not exercise Spring AOP. Use a Spring context or integration test to obtain the bean from the `ApplicationContext` and invoke it through that bean.

An integration test should:

- Create a Spring bean bearing the annotation.
- Mock or stub the dependent client to throw a recordable exception.
- Invoke the method via the context-injected bean enough times to reach `minimumNumberOfCalls`.
- Verify the fallback runs when errors occur or when the circuit is OPEN.
- Inspect the circuit breaker state and metrics for the exact instance name.
- Add a self-invocation case demonstrating that internal calls bypass the proxy, then verify the separate-bean fix.

Do not merely assert that the method returns the fallback once. A fallback can execute from a supplier exception even before the circuit breaker ever opens. To prove the circuit breaker works, verify sample count, failure rate, and state transitions.

During tests, use an isolated instance and registry per scenario or perform controlled state resets. Prevent an OPEN state from an earlier test from leaking into subsequent tests. When testing OPEN or HALF_OPEN wait durations, use controllable time mechanisms so tests do not depend on long waits.

## Implementation Principles

- Place annotations on `public` methods of Spring-managed beans.
- Ensure callers go through the proxy; extract a separate bean whenever self-invocation occurs.
- Use Resilience4j and AOP starters compatible with your Spring Boot version.
- Never instantiate aspect-protected beans manually with `new`.
- Check JDK/CGLIB proxy mode, interfaces, `final` classes, and method visibility.
- Keep circuit breaker names stable and matching instance configurations.
- Write fallbacks with matching signatures and sound business semantics.
- If you prefer not to rely on AOP, use the Spring Cloud CircuitBreaker factory to wrap calls explicitly.
- Test within a Spring context and verify both metrics and circuit breaker state.

The `@CircuitBreaker` annotation only takes effect when the Resilience4j aspect is registered and calls pass through a Spring AOP proxy. Self-invocation, manually instantiated beans, missing AOP dependencies, or non-interceptable methods can all cause the annotation to be bypassed. Defining proper proxy boundaries, extracting dependency calls into separate beans, and verifying runtime state will ensure the circuit breaker accurately protects calls in Spring Cloud applications.
