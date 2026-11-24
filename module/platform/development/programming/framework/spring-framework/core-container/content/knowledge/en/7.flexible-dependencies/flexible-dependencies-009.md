# Limiting Provider Usage to Avoid Hiding Dependencies in Spring Core Container

## 1. Objectives and Design Problem

Spring's **`ObjectProvider<T>`** allows deferring bean lookups and expressing dependencies that may be missing, have multiple candidates, or need per-scope retrieval. This tool is useful, yet placing providers everywhere across business classes can turn mandatory dependencies into hidden lookups. An application might start up despite missing critical components, only to fail inside a specific business branch — or worse, silently skip a required action.

Example: a payment service **must** have `PaymentGateway` to charge money. If a `PaymentGateway` constructor parameter is replaced with `ObjectProvider<PaymentGateway>`, calling `getIfAvailable()` and skipping when it returns `null`, a configuration bug gets turned into an acceptable "no gateway" state. That is **dependency hiding**: the class signature no longer communicates that the feature cannot succeed without a gateway.

This lesson aims at **bounded and intentional** provider usage:

- Explicitly state when a dependency is **mandatory**, **optional**, or **only needs runtime lookup**.
- Distinguish constructor injection from Service Locator; recognize provider misuse as a generic tool to fetch arbitrary beans from the container.
- Keep missing core-component errors surfacing early (*fail fast*).
- Use `ObjectProvider<T>` appropriately at integration boundaries, scoped factories, auxiliary features, or plugin sets.
- Understand `getObject()`, `getIfAvailable()`, `getIfUnique()`, `ifAvailable()`, `stream()`, and `orderedStream()` accurately.
- Write a runnable Java 17 + Spring Framework 6.2 example and tests covering missing-bean cases.
- Avoid treating lazy lookup as a fix for circular dependencies, error handling, or missing configuration.

**Guiding principle:** If a class **cannot fulfill its business contract** without `T`, declare `T` directly in the constructor. Introduce `ObjectProvider<T>` only when there is a valid reason regarding retrieval timing, cardinality, or optionality.

## 2. The Nature of `ObjectProvider<T>`

`ObjectProvider<T>` resides in `org.springframework.beans.factory`, bound by Spring to the BeanFactory and the injection point's `T` type. It is a handle providing **on-demand bean requests**, not a copy of bean `T`. Calls on the provider resolve against BeanFactory state at call time; outcomes also depend on bean types, qualifiers, scopes, and candidate selection rules.

Commonly used methods:

| Method | Basic Meaning | What to Watch Out For |
| --- | --- | --- |
| `getObject()` | Retrieve a mandatory `T` bean | Missing bean throws `NoSuchBeanDefinitionException`; unresolved multiple candidates throw `NoUniqueBeanDefinitionException`; bean creation errors can still occur |
| `getIfAvailable()` | Retrieve a bean if available | Returns `null` when no candidates exist; **does not auto-resolve** ambiguity or initialization failures |
| `getIfAvailable(supplier)` | Retrieve bean or invoke supplier for default when missing | Fallback can mask misconfiguration if `T` is actually required |
| `ifAvailable(consumer)` | Execute action only if a bean is obtained | Fits auxiliary tasks; do not use to silently skip mandatory steps |
| `getIfUnique()` | Retrieve bean if a unique candidate resolves | May return `null` when no bean exists or no winner resolves under selection rules |
| `stream()` | Iterate 0..n matching beans | No ordering guarantee |
| `orderedStream()` | Iterate 0..n beans using Spring's comparator | Suitable only when business ordering is explicitly declared and tested |

**Common confusion:** a provider **does not by default** make every dependency optional. If a service calls `getObject()` at runtime, a missing bean still throws an exception — it just shifts the failure from service initialization to execution time. If a service calls `getIfAvailable()` and ignores `null`, it may have silently altered the business contract to "allowed to be missing."

Nor does a provider guarantee the target bean has not yet been created: default singletons may already have been instantiated during context startup. A provider is a flexible lookup mechanism, not an absolute lazy switch.

## 3. What Is Dependency Hiding?

A constructor is where you declare what is required to build a properly functioning object. Compare two designs.

### 3.1. Clear Contract: Mandatory Dependency

```java
// Illustrative: PaymentGateway is an application interface.
final class PaymentService {
    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    String pay(String orderId) {
        return gateway.charge(orderId);
    }
}
```

The service cannot validly exist without a gateway. When Spring constructs `PaymentService` via constructor injection and finds no `PaymentGateway` bean, bean creation fails and the root cause surfaces at context startup (typically wrapped in `UnsatisfiedDependencyException`). That is a missing-configuration signal that needs fixing.

### 3.2. Anti-Pattern: Provider Used to Mask Errors

```java
// Illustrative ANTI-PATTERN: do not use for real payment processing.
final class HiddenPaymentService {
    private final ObjectProvider<PaymentGateway> gatewayProvider;

    HiddenPaymentService(ObjectProvider<PaymentGateway> gatewayProvider) {
        this.gatewayProvider = gatewayProvider;
    }

    String pay(String orderId) {
        PaymentGateway gateway = gatewayProvider.getIfAvailable();

        if (gateway == null) {
            return "SKIPPED:" + orderId; // Pretends the main flow completed!
        }

        return gateway.charge(orderId);
    }
}
```

This illustrates flawed design, requiring `PaymentGateway` and importing `ObjectProvider` in its project; it is not a standalone program. The flaw is not that Spring permits `getIfAvailable()`; the flaw is that business logic **requires payment**, yet the code treats a missing gateway as valid. The system can boot, serve traffic across layers, and only when receiving an order discover it cannot charge or return a bogus status.

Even when using:

```java
PaymentGateway gateway = gatewayProvider.getObject();
return gateway.charge(orderId);
```

the dependency remains partially hidden: the signature `HiddenPaymentService(ObjectProvider<PaymentGateway>)` does not state directly that it **requires** a gateway, and a missing bean is reported late when `pay` runs. When lazy lookup or scope switching is unnecessary, accepting `PaymentGateway` directly is clearer.

### 3.3. Signs of Provider Overuse

Re-evaluate the design if you notice any of these signs:

1. Almost every constructor takes multiple `ObjectProvider<...>` parameters even though services use those dependencies immediately.
2. Many methods call `getIfAvailable()` or `getIfUnique()` and quietly ignore failing to obtain a bean.
3. Code calls `ApplicationContext.getBean(...)` or `BeanFactory.getBean(...)` with class/bean-name strings instead of declaring constructor dependencies.
4. A service asks the container whether it can process payments, persist data, or enforce permissions, instead of receiving the mandatory components for those tasks.
5. Unit tests must spin up a real Spring context just to execute a pure-Java business method.
6. Missing beans are discovered only when a user hits a rare endpoint or under production load.
7. Providers appear solely to dodge a dependency cycle without fixing responsibilities between classes.

These are **warning signs to inspect**, not an outright ban on providers. An adapter that genuinely needs to obtain a prototype bean per request has a legitimate reason to use a provider even when that prototype is crucial.

## 4. Classify Dependencies Before Choosing an Injection Type

The first question is: **If this bean does not exist, can the feature still fulfill its contract properly?**

| Dependency Category | Example | Preferred Form | Behavior When Missing |
| --- | --- | --- | --- |
| Mandatory | `PaymentGateway` to charge, repository to persist | Constructor `PaymentGateway`/`Repository` | Configuration error surfaces as early as possible |
| Single optional | Auxiliary telemetry/audit adapter | `Optional<AuditSink>` if resolved once | Skip or use a clearly specified fallback |
| Multiple optional implementations | Metric plugins, extension listeners | `List<Hook>` or `ObjectProvider<Hook>.stream()` | Empty set is a valid case |
| Needs on-demand lazy lookup | Task triggering a rarely used plugin | `ObjectProvider<Plugin>` at usage boundary | Must explicitly define what 0/1/n beans mean |
| Needs scoped instances | `prototype` or scoped bean fetched per use | `ObjectProvider<Worker>` or dedicated factory | Do not assume every fetch yields a new instance; check scope |
| Needs dynamic domain selection | Pick processor by tenant/channel code | `StrategyRegistry` / factory interface or explicit map | Missing strategy must have an explicit business policy |

**Do not choose a type merely so Spring can start.** Choose types to express the true contract. If omitting a component is genuinely permitted, document the fallback, activation rules, and observability; if the component is required, keep explicit constructor injection.

You can use `@Qualifier` to pinpoint the required implementation:

```java
// Illustrative snippet inside a Spring-managed bean:
OrderService(@Qualifier("primaryPaymentGateway") PaymentGateway gateway) {
    this.gateway = gateway;
}
```

This still expresses a **mandatory dependency**, while selecting the desired bean. `@Primary` resolves certain multi-candidate situations, though it is no substitute for explicit contract design.

## 5. Complete Example: Mandatory Core, Optional Extensions

We will build a small application using **direct constructor injection for `PaymentGateway`**, and using a provider only at the **post-payment hook boundary**, where zero or more implementations may exist.

The application builds two separate Spring contexts:

- Core-only context: gateway exists, no hooks; payment still succeeds.
- Core-plus-hooks context: payment still executes, plus two auxiliary hooks in order.

The goal is verifying that the provider is used to **extend behavior**, not to legitimize missing core components.

### 5.1. Project Structure

```text
bounded-provider/
├── pom.xml
└── src/main/java/demo/BoundedProviderDemo.java
```

Contents of `pom.xml` (plain Spring Framework, Java 17):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bounded-provider</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Contents of `src/main/java/demo/BoundedProviderDemo.java`:

```java
package demo;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

public class BoundedProviderDemo {

    interface PaymentGateway {
        String charge(String orderId);
    }

    interface PaymentHook {
        void afterPayment(String receipt);
    }

    static final class PaymentService {
        private final PaymentGateway gateway;

        PaymentService(PaymentGateway gateway) {
            this.gateway = gateway;
        }

        String pay(String orderId) {
            return gateway.charge(orderId);
        }
    }

    static final class CheckoutFacade {
        private final PaymentService payments;
        private final ObjectProvider<PaymentHook> hooks;

        CheckoutFacade(PaymentService payments,
                       ObjectProvider<PaymentHook> hooks) {
            this.payments = payments;
            this.hooks = hooks;
        }

        void checkout(String orderId) {
            String receipt = payments.pay(orderId);
            System.out.println("receipt=" + receipt);

            // Hooks are extensions: having zero hooks is still valid.
            hooks.orderedStream().forEach(hook -> hook.afterPayment(receipt));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CoreConfig {

        @Bean
        PaymentGateway paymentGateway() {
            return orderId -> "PAID:" + orderId;
        }

        @Bean
        PaymentService paymentService(PaymentGateway gateway) {
            return new PaymentService(gateway);
        }

        @Bean
        CheckoutFacade checkoutFacade(
                PaymentService payments,
                ObjectProvider<PaymentHook> hooks) {
            return new CheckoutFacade(payments, hooks);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class OptionalHooksConfig {

        @Bean
        @Order(10)
        PaymentHook auditHook() {
            return receipt -> System.out.println("audit=" + receipt);
        }

        @Bean
        @Order(20)
        PaymentHook metricsHook() {
            return receipt -> System.out.println("metrics=" + receipt);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(CoreConfig.class)) {
            System.out.println("core only:");
            context.getBean(CheckoutFacade.class).checkout("42");
        }

        try (var context = new AnnotationConfigApplicationContext(
                CoreConfig.class, OptionalHooksConfig.class)) {
            System.out.println("core plus hooks:");
            context.getBean(CheckoutFacade.class).checkout("42");
        }
    }
}
```

Run in the `bounded-provider` directory with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BoundedProviderDemo
```

Lines printed by **the program itself** (excluding Maven or environment logs):

```text
core only:
receipt=PAID:42
core plus hooks:
receipt=PAID:42
audit=PAID:42
metrics=PAID:42
```

### 5.2. Why Is This Design Sound?

**`PaymentService` takes `PaymentGateway` directly.** In both contexts, the gateway is a mandatory component. Removing the `paymentGateway()` bean from `CoreConfig` while keeping `PaymentService` causes the context to fail creating the service due to a missing dependency. That matches the requirement "cannot pay without a gateway."

**`CheckoutFacade` takes `ObjectProvider<PaymentHook>` at the extension boundary.** Zero, one, or many hooks are permitted. In the first context, `orderedStream()` is empty so no audit/metrics output appears. In the second context, both hooks run in `@Order(10)` then `@Order(20)` sequence.

**Intentional provider scope.** Providers are not scattered into `PaymentService`, are not used to look up `PaymentGateway` when `pay` is invoked, and do not alter its core contract. The `CheckoutFacade` boundary class coordinates extensions that may legitimately be absent.

**The two contexts are independent startup configurations.** The example does not claim you can dynamically add beans to an already refreshed ApplicationContext and have every provider hot-plug them under all circumstances.

**On hook error handling:** The example does not catch exceptions from hooks. If a hook throws after the gateway returned a receipt, `checkout` will fail even though payment may already have succeeded. In real applications, define error policies, idempotency, and event timing (e.g., after transaction commit) before running hooks synchronously; **providers do not define these policies**.

## 6. Choosing Error Policies by Dependency Role

Choosing `ObjectProvider` makes sense only when the consumer **actively specifies which conditions permit absence and which must fail**. Instead of memorizing API tables, evaluate three business cases:

| Role | Recommended Access | When Missing or Ambiguous |
| --- | --- | --- |
| Mandatory gateway, used immediately | Direct `PaymentGateway` constructor parameter | Context reports missing/ambiguous early; never fakes success |
| Single optional auxiliary adapter | `Optional<AuditSink>`, or `getIfAvailable()` if deferred lookup is needed | Absence permitted, **ambiguity still must fail** |
| Extension point for 0..n hooks | `ObjectProvider<Hook>.stream()` / `orderedStream()` | Empty set is valid; multiple hooks all execute |
| Enable feature only if unique choice exists | `getIfUnique()` or `ifUnique(...)` | Both missing and ambiguous are skipped **only if that policy is explicitly approved** |

`getIfAvailable(Supplier)` and `getIfUnique(Supplier)` are not equivalent: the first fallback applies when a bean is absent, while the second also applies when no unique candidate can be selected. A valid `@Primary` can pick one bean among multiple candidates; fallbacks do not replace handling bean initialization errors. If a fallback is instantiated with `new`, it does not receive injection, proxies, or lifecycle callbacks from Spring.

In the checkout example, `PaymentService` takes the gateway directly to fail fast, while `CheckoutFacade` iterates all hooks at the extension boundary. This is the design boundary to evaluate; exception and outcome details for each method were demonstrated in the dedicated lesson on `getObject`/`getIfAvailable`/`getIfUnique`.

## 7. Catching Errors in the Right Place Instead of Dodging Dependencies

A misleading pattern:

```java
// ANTI-PATTERN: do not use for mandatory business operations.
try {
    repositoryProvider.getObject().save(order);
} catch (Exception ignored) {
    // Silently ignores all data persistence failures.
}
```

This snippet has at least three flaws: a critical dependency is looked up late, missing-bean errors get mixed with persistence errors, and exceptions are swallowed without trace. The system may report a transaction succeeded even though data was never saved.

A better approach is **direct constructor injection** with explicit business error policies:

```java
// Illustrative snippet inside a class where OrderRepository, Order, and Receipt are declared.
final class OrderApplicationService {
    private final OrderRepository repository;

    OrderApplicationService(OrderRepository repository) {
        this.repository = repository;
    }

    Receipt submit(Order order) {
        repository.save(order);
        return new Receipt(order.id());
    }
}
```

This is illustrative code: `OrderRepository`, `Order`, and `Receipt` are application-defined types. When the repository is unregistered, Spring detects the missing dependency during bean creation. When `save` fails due to infrastructure issues, the exception propagates cleanly to transactional boundaries, error handlers, and observability tools. Dependency injection does not replace transaction or retry policies.

If an operation is genuinely "best effort" (such as emitting an optional metric), catch errors **of the auxiliary operation**, log/count failures appropriately, and define the impact on the request. Still, distinguish **no plugin present** from **plugin present but failed**; conflating the two makes operations hard to debug.

## 8. Where Providers Belong: Intentional Boundaries

Providers earn their keep where they genuinely control timing or bean cardinality.

### 8.1. Extension Point with 0..n Beans

```java
// Illustrative snippet in a boundary class, not a standalone runnable app.
final class HookDispatcher {
    private final ObjectProvider<DomainHook> hooks;

    HookDispatcher(ObjectProvider<DomainHook> hooks) {
        this.hooks = hooks;
    }

    void dispatch(Event event) {
        hooks.orderedStream().forEach(hook -> hook.onEvent(event));
    }
}
```

`DomainHook` and `Event` are application types. If having zero hooks does not break business requirements, a provider is appropriate. If compliance demands that an audit hook always be present, **do not** treat an empty stream as success; validate configuration or declare a mandatory component.

### 8.2. Factory When Per-Task Prototypes Are Needed

```java
// Illustrative: JobWorker is a prototype bean in configuration.
final class JobWorkerFactory {
    private final ObjectProvider<JobWorker> workers;

    JobWorkerFactory(ObjectProvider<JobWorker> workers) {
        this.workers = workers;
    }

    JobWorker newWorker() {
        return workers.getObject();
    }
}
```

This uses a provider for **retrieval timing**, not to make `JobWorker` optional. When the bean is missing, `getObject()` fails instead of silently fabricating a dummy worker. You can hide Spring details behind a domain factory interface such as `WorkerFactory` so other business classes stay unaware of `ObjectProvider`.

If the bean has `@Scope("prototype")`, each resolution request can yield a new instance; if it remains a singleton, the provider typically returns that singleton. Never infer scope solely from the presence of a provider.

### 8.3. Single Optional Bean Integration

For a rarely used dependency that may be absent and only needs resolving **once** at consumer creation, `Optional<T>` is usually simpler:

```java
// Illustrative snippet in a Spring-managed bean:
final class NotificationFacade {
    private final java.util.Optional<NotificationAdapter> adapter;

    NotificationFacade(java.util.Optional<NotificationAdapter> adapter) {
        this.adapter = adapter;
    }

    void notifyCreated(String id) {
        adapter.ifPresent(value -> value.send(id));
    }
}
```

Conversely, if on-demand lookup or scope awareness is needed, a provider may fit. Avoid `ObjectProvider<T>` merely because it seems "more flexible" when no extra flexibility is actually required.

### 8.4. Selecting an Implementation by Runtime Key

A service receiving a shipping method code and needing the right strategy can use a **registry** rather than querying the BeanFactory on every branch:

```java
// Illustrative interface and consumer, not a standalone program.
interface CarrierRegistry {
    Carrier forCode(String code);
}

final class ShippingService {
    private final CarrierRegistry registry;

    ShippingService(CarrierRegistry registry) {
        this.registry = registry;
    }

    void ship(String carrierCode, Parcel parcel) {
        registry.forCode(carrierCode).send(parcel);
    }
}
```

`Carrier` and `Parcel` are application types. The registry can inject `Map<String, Carrier>`, `List<Carrier>`, or `ObjectProvider<Carrier>` at the **infrastructure layer** and enforce selection and duplicate-key checks. `ShippingService` sees only the domain interface `CarrierRegistry`. Bean lookup decisions stay centralized and easy to test rather than leaking across every service.

## 9. Service Locator and Hidden Dependencies

**Service Locator** is a design pattern where a class queries a central registry for dependencies at runtime, such as holding `ApplicationContext` directly and calling `getBean("paymentGateway")` inside a method.

```java
// ANTI-PATTERN illustrating a design smell.
final class LocatorCheckoutService {
    private final ApplicationContext context;

    LocatorCheckoutService(ApplicationContext context) {
        this.context = context;
    }

    String checkout(String id) {
        PaymentGateway gateway =
                context.getBean(PaymentGateway.class);
        return gateway.charge(id);
    }
}
```

Although Spring provides `ApplicationContext`, this mixes **business responsibilities and IoC plumbing**. The constructor exposes only `ApplicationContext`, hiding the required `PaymentGateway`. Misconfiguration is deferred until `checkout` runs. Unit testing gets harder because tests must mock the container or boot a Spring context.

`ObjectProvider<PaymentGateway>` improves on a general locator because `PaymentGateway` remains visible in the constructor signature, yet overusing it still introduces **hidden lookups** and defers failures to runtime. Practical rules:

- Put mandatory dependencies in the constructor as **concrete interfaces**.
- When lazy/prototype behavior is needed, place the provider inside a **clearly scoped factory or adapter**.
- Do not pass `ApplicationContext` across domain layers just to "grab whatever is needed."
- Do not hide dependencies behind `ObjectProvider<Object>` or look up beans by arbitrary string names.
- If the true bound is "all plugins of type X," use a typed `ObjectProvider<X>` at the extension boundary; qualifiers can also filter groups.

In certain framework/infrastructure components, accessing `ApplicationContext` directly can be justified. The evaluation criterion is **how much Spring coupling leaks out** and **how explicit the class contract remains**, not a dogmatic ban on an API.

## 10. Do Providers Solve Circular Dependencies?

Providers should not be used indiscriminately to dodge structural dependency cycles.

Suppose `OrderService` depends on `InvoiceService` and `InvoiceService` depends back on `OrderService`. Switching one edge to `ObjectProvider<OrderService>` may **defer** when the bean is requested, yet the bidirectional responsibility coupling still exists. If `provider.getObject()` is invoked inside a constructor or while both beans are still initializing, circular dependency failures can still occur.

Intentional design fixes:

1. Extract shared responsibilities into a third service that both depend on.
2. Decouple post-processing actions via domain events where business rules allow.
3. Move coordinated flow into an orchestration service instead of two services calling back and forth.
4. Use a provider only when **lookup timing** and lifecycle genuinely require it; test both bootstrap and runtime paths.

`@Lazy` is another tool that alters initialization or dereferencing timing in appropriate situations. However, adding `@Lazy` does not change which services a class actually relies on, nor does it make bidirectional coupling architecturally sound.

## 11. Providers, Scope, and When Errors Surface

The same provider carries different risks depending on scope.

| Condition | On Provider Call | Design Implication |
| --- | --- | --- |
| Normal singleton | May return an already-created bean | Provider does not automatically make singletons lazy |
| `@Lazy` singleton | May be created on first request | Initialization errors can surface later |
| Prototype | May create a new instance per resolution | Requires awareness of cost, lifecycle, and resource cleanup |
| Scoped proxy/request scope | May delegate through proxy to active scope | Calling outside active scope can fail |
| Multiple beans via `stream()` | Resolves candidates during stream consumption | Queries only when needed, yet terminal ops can instantiate multiple beans |

If business logic strictly requires an adapter, yet for performance you prefer not to instantiate it before a task runs, you can keep the provider in a factory/coordination layer behind a method whose name signals **required** (e.g., `requiredWorker()` calling `getObject()`). Crucially, **do not turn absence into "nothing to do"** and always test rarely executed branches.

If a bean is requested only along a rare execution path (e.g., a weekend batch job), a provider can hide missing configuration until that job triggers. Counteract this with startup validation or integration tests exercising that path. Never assume successful context startup means every dynamically queried dependency resolves cleanly.

## 12. Performance and Observability Considerations

Providers are not automatic performance boosters. Each call may perform bean resolution; stream calls inspect multiple candidates and can trigger instantiation. Calling a provider inside tight loops or hot request paths adds unnecessary overhead.

Recommended practices:

- If the candidate set is fixed, inject `List<T>` or capture `provider.orderedStream().toList()` once in an appropriate spot.
- If dynamic resolution is needed, invoke the provider only when actually required; avoid repeated `getObject()` calls without understanding scope.
- If hooks execute synchronously, define timeouts, failure policies, and error ownership per hook; providers do not supply isolation or retries.
- If "no plugin" is a normal state, expose it via operational logs/metrics without spamming logs on every request.
- If "no gateway" is a misconfiguration, let the application fail loudly; do not equate it with an optional state.
- Avoid logging sensitive info simply to debug bean lists; treat bean names as technical metadata, not business data.

**Testing and maintainability costs** matter too. A class with constructor `PaymentService(PaymentGateway gateway)` is trivial to unit-test with a fake gateway; `PaymentService(ApplicationContext context)` demands complex mocking and forces readers to inspect method bodies to learn which beans the service uses.

## 13. Testing So Providers Never Mask Misconfiguration

A solid test suite verifies **both valid missing dependencies and invalid missing dependencies**.

### 13.1. Missing Optional Hooks Must Succeed

With `CoreConfig` in the complete example, the context registers zero `PaymentHook` beans yet checkout still returns a receipt. This serves as a contract test for the extension point. If a refactor causes code to fail when no hooks exist, the test catches it.

### 13.2. Multiple Hooks Must Run in Order

When `OptionalHooksConfig` is included, both audit and metrics must run. `@Order(10)` precedes `@Order(20)`; tests should assert **both membership and order**, instead of relying on method declaration order or component scanning.

### 13.3. Missing Mandatory Gateway Must Fail the Context

You can add the following to **the same `BoundedProviderDemo` class** from section 5 to verify fail-fast behavior using a configuration without a gateway:

```java
// Additional snippet: declare inside BoundedProviderDemo.
@Configuration(proxyBeanMethods = false)
static class MissingGatewayConfig {
    @Bean
    PaymentService paymentService(PaymentGateway gateway) {
        return new PaymentService(gateway);
    }
}

static void verifyRequiredDependency() {
    try (var context = new AnnotationConfigApplicationContext(
            MissingGatewayConfig.class)) {
        throw new AssertionError("Context should reject missing gateway");
    } catch (org.springframework.beans.factory.UnsatisfiedDependencyException expected) {
        System.out.println("missing gateway rejected");
    }
}
```

This is an **additional verification snippet**, not part of `main()`'s default output. To run it, call `verifyRequiredDependency()` from `main`. It intentionally builds `PaymentService` without `PaymentGateway`; when Spring fails due to the missing dependency, we catch `UnsatisfiedDependencyException` and print:

```text
missing gateway rejected
```

Depending on logging configuration, Spring may also log diagnostic messages. This check is valid only when the isolated context truly **registers zero** `PaymentGateway` beans.

In pure-Java unit tests, instantiate `PaymentService` with a fake `PaymentGateway` and assert the output; Spring is unnecessary for `pay` logic. For `CheckoutFacade`, prefer an abstraction like `PaymentHookDispatcher` if you want pure-Java unit tests free of Spring APIs; integration tests then verify the adapter performs lookup/`orderedStream` per contract.

### 13.4. Test Cases Not to Miss

| Scenario | Expected Result |
| --- | --- |
| Zero optional hooks | Core flow completes; no hooks invoked |
| One hook | Hook invoked once at the designated point |
| Multiple hooks | All traversed, respecting order/qualifiers if present |
| Missing mandatory gateway | Context fails to create the corresponding service |
| Two competing unresolved gateways | Ambiguity error reported; never picks arbitrarily |
| Hook bean exists yet initialization fails | Failure identified as bean creation error, not treated as "hook absent" |
| Hook throws during execution | Impact on checkout follows designed error policy |
| Prototype/scope-sensitive bean | Instantiation count and lookup timing verified |

You do not need to mock every `ObjectProvider` method to test business classes. For complex logic, it is usually easier to confine the provider to an adapter tested with a small Spring context, while domain services rely on plain Java interfaces.

## 14. Code Review Checklist

When reviewing a constructor accepting `ObjectProvider<T>`, answer:

1. **Why is a provider needed?** Because the bean is optional, has multiple implementations, is prototype/scoped, needs lazy lookup, or merely out of reluctance to declare dependencies?
2. **What if no `T` bean exists?** Does core functionality stay correct? Are fallbacks, tests, and monitoring defined?
3. **What if multiple `T` beans exist?** Are all needed, one by qualifier, or a business-key registry?
4. **When is the bean retrieved?** At startup, per request, or when a job runs? How far is error detection delayed?
5. **What if bean creation or execution fails?** Does code distinguish configuration/infrastructure failures from valid absence?
6. **Which layer holds the provider?** Is it at an adapter/factory/extension boundary, or leaking into domain services that need no Spring awareness?
7. **Is scope understood properly?** Do singleton, prototype, request scope, and lazy initialization behave as intended?
8. **Could a clearer type be used?** Required `T`, one-time optional `Optional<T>`, fixed group `List<T>`, or an explicit factory/registry interface?
9. **Do tests cover missing/multiple beans?** Especially testing that missing core dependencies must fail.
10. **Can a newcomer tell what the service needs from its constructor?** If readers must inspect every method body to discover context lookups, the design may be hiding dependencies.

This checklist does not mean "providers are bad." A well-placed provider with an explicit contract, bounded scope, and missing-bean tests is a valuable Spring Core Container tool.

## 15. Common Mistakes and Fixes

| Symptom | Mistake | Fix |
| --- | --- | --- |
| App starts yet payments fail when orders arrive | Mandatory `PaymentGateway` hidden in a provider | Constructor-inject `PaymentGateway` directly |
| Bean missing yet code continues as if successful | `getIfAvailable()`/`ifAvailable()` skips a mandatory action | Fail fast or throw a clear business error; test missing case |
| `getIfAvailable()` still throws | Multiple unresolved candidates or bean creation failure | Fix qualifiers/primary/bean factory; do not assume "if available" swallows all errors |
| Not all plugins run | Using `getIfUnique()` for a 0..n extension point | Use `stream()`/`orderedStream()` when all plugins should run |
| Unit tests forced to boot Spring | Domain class holds `ApplicationContext` and looks up beans | Constructor-inject domain interfaces; confine providers to adapters/factories |
| Cyclic A/B services remain hard to follow | Using provider solely to dodge circular dependency error | Split responsibilities; use orchestration/events where appropriate |
| Rules run out of order | Calling `stream()` and relying on registration order | Use `orderedStream()` with explicit `@Order` metadata |
| Assuming provider always yields new beans | Ignoring bean scope | Distinguish singleton/prototype/scoped proxy |
| Errors surface very late | Provider defers lookup of a core dependency | Inject directly or add startup/integration validation |
| Hard to observe plugin failures | Catching `Exception` and ignoring all failures | Define retry/fallback/logging/metrics policies per hook type |

## 16. Exercises and Guided Answers

**Exercise 1 — Choosing the right dependency type.** A `ReportService` **requires** `ReportRepository` to save reports, yet can send metrics to `MetricsSink` if registered. Which constructor expresses the contract better?

```java
// Option A
ReportService(ObjectProvider<ReportRepository> repository,
              ObjectProvider<MetricsSink> metrics) { }

// Option B
ReportService(ReportRepository repository,
              java.util.Optional<MetricsSink> metrics) { }
```

**Answer:** Option B is better when metrics are optional and resolved once. The repository is a mandatory dependency so the constructor catches a missing bean early. If metrics genuinely need dynamic/lazy lookup, a provider can still be used **for metrics only**.

**Exercise 2 — Multiple beans.** If an application has three `AuditHook` beans of the same type and all three must run, is calling `provider.getIfAvailable()` semantically right?

**Answer:** No. That method expects to return a single bean; when multiple candidates cannot be uniquely resolved it can throw. For 0..n hooks, use `stream()` or `orderedStream()` depending on ordering needs.

**Exercise 3 — Provider masking bugs.** A service calls `getIfUnique()` for `FraudDetector`. When two detectors exist with no winner, the service receives `null` and skips fraud detection. Where is the bug?

**Answer:** If fraud detection is mandatory, missing or ambiguous detectors must be treated as misconfiguration. Declare a required dependency, pick the right detector with qualifiers/primary, or build an explicit multi-detector pipeline. Never treat `null` as "pass."

**Exercise 4 — Prototypes.** Each job needs a fresh `JobWorker` with isolated state. Can you inject a prototype `JobWorker` directly into a singleton manager and call it repeatedly to always get a new worker?

**Answer:** Do not assume that works: a singleton's dependencies are normally resolved when the singleton is constructed, so the manager retains the same worker. A provider or factory fetching the prototype per job is appropriate, with scope properly configured.

**Exercise 5 — Design boundaries.** If ten services all hold `ObjectProvider<PaymentGateway>` just to call `getObject()` before charging, how should you refactor?

**Answer:** First verify whether each service actually needs the gateway. Convert mandatory dependencies into `PaymentGateway` or a domain abstraction like `Payments` via constructor injection. If only one adapter needs lazy/prototype semantics, keep the provider **inside that adapter/factory** and expose a plain Java API to the rest. Write tests confirming a missing gateway is an error, not a success.

## Conclusion

`ObjectProvider<T>` is a tool for **making bean resolution timing and policy flexible**, not a license to turn every dependency optional. Keep mandatory dependencies as typed `T` constructor parameters so misconfigurations fail early. Use providers for 0..n extension points, lazy/prototype lookups, or factories/registries that genuinely require dynamic retrieval, confining them to well-defined infrastructure boundaries.

Before introducing a provider, specify exact behavior for **zero**, **one**, **multiple**, or **failing** beans. Until those conditions are clear, adding "flexibility" via a provider can reduce clarity, testability, and operational safety.

## References

- [Spring Framework — ObjectProvider API (6.2)](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectProvider.html): `getObject()`, `getIfAvailable()`, `getIfUnique()`, `stream()`, `orderedStream()`, and bean selection conditions.
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html): constructor injection, mandatory and optional dependencies, collection injection.
- [Spring Framework — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html): constraining candidates with qualifiers.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype, and other scopes.
- [Spring Framework — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html): difference between lazy initialization and dependency resolution.
