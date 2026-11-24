# `Optional`, `@Nullable`, and Optional Dependencies

> **Spring Boot Fundamentals · Dependency Injection**  
> Constructor injection helps a class clearly declare the dependencies it needs to operate. Yet sometimes an integration is only enabled in certain environments, an extension is provided by another module, or an auxiliary service may be absent. Spring supports several ways to express optional dependencies, notably **`Optional<T>`**, **`@Nullable`**, and **`ObjectProvider<T>`**. Choosing the right approach helps the application start reliably while making behavior explicit when a bean does not exist.

## 1. Required Dependencies vs. Optional Dependencies

Suppose an order-processing service needs a repository to save orders:

```java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
```

`OrderRepository` is a required dependency. If Spring cannot find a matching bean, the application typically cannot create `OrderService` and context startup fails. This is good behavior: the system should not silently run while missing an essential component.

Conversely, suppose the application has an integration that sends audit notifications. In some environments, auditing is enabled; in a demo or test environment, that integration may not be installed. If core business operations remain valid without an audit sink, we can describe this dependency as **optional**.

| Dependency kind | When bean does not exist | Desired behavior |
| --- | --- | --- |
| Required | Consumer bean cannot be created; context startup usually fails | Fail fast to catch missing configuration |
| Optional | Consumer can still be created | Use fallback, skip auxiliary feature, or handle per clear policy |
| Multiple beans of same type | Candidate may be ambiguous | Use qualifier/primary or process a collection |
| Bean needed only at some point after startup | Lookup not strictly needed when creating consumer | Use provider/lazy lookup when appropriate |

**Optionality is a business and architectural decision, not merely a way to avoid startup errors.** Before making a dependency optional, define what the application is allowed to do when that bean is absent.

### 1.1. How does Spring handle required dependencies?

With the constructor:

```java
@Service
public class ReportService {

    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }
}
```

Spring must resolve a matching `ReportRepository` bean. If there is no candidate, an error such as `NoSuchBeanDefinitionException` or a bean creation error wrapped in `UnsatisfiedDependencyException` will typically occur.

That is not an error to hide by adding `null` arbitrarily. If the service cannot work without the repository, letting Spring fail immediately at startup is the right choice.

### 1.2. When is a dependency genuinely optional?

A dependency can be optional when:

- It provides an auxiliary capability and does not determine core business correctness.
- A valid fallback exists when the bean is absent.
- Enabling/disabling the integration is intentional per environment or module.
- The consumer can operate safely without the bean.
- The missing-bean state is observable or logged if that matters.

Do not make a core dependency optional just so the application "gets past startup." For example, if a payment service needs a gateway to complete transactions, a missing gateway must surface as a configuration error or unavailable state rather than silently skipping payment.

## 2. `Optional<T>` in Constructor Injection

`java.util.Optional<T>` represents a value that may or may not be present. Spring supports `Optional<T>` as an injection parameter type: if a matching bean exists, the consumer receives `Optional.of(bean)`; if none exists, the consumer receives `Optional.empty()`.

Example:

```java
package com.example.orders;

import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final Optional<AuditSink> auditSink;

    public OrderService(Optional<AuditSink> auditSink) {
        this.auditSink = auditSink;
    }

    public void placeOrder(Order order) {
        // Process and save the order here.

        auditSink.ifPresent(sink ->
                sink.publish(new OrderPlacedEvent(order.id())));
    }
}
```

Assume `AuditSink` is an application interface:

```java
package com.example.orders;

public interface AuditSink {
    void publish(OrderPlacedEvent event);
}
```

If an `AuditSink` implementation is registered, Spring injects it inside the `Optional`. If no matching bean exists, `auditSink` is `Optional.empty()` and the service is still created.

This example assumes auditing is a secondary feature. If auditing is a mandatory compliance requirement, do not skip it like this; configure the application so it fails to start or refuses traffic when audit infrastructure is unavailable.

### 2.1. Using Optional properly

Some ways to handle it:

```java
auditSink.ifPresent(sink -> sink.publish(event));
```

Execute only when the bean exists.

```java
String channel = auditSink
        .map(AuditSink::channelName)
        .orElse("audit-disabled");
```

Produce a fallback value when the bean does not exist.

```java
AuditSink sink = auditSink.orElseThrow(
        () -> new IllegalStateException("Audit is required here"));
```

Turn a missing bean into an error at the exact point where a feature genuinely needs it. If missing audit is a configuration error, it is usually better to catch it earlier during startup rather than waiting for a rare request.

Avoid calling `get()` without checking:

```java
AuditSink sink = auditSink.get(); // Can throw NoSuchElementException.
```

If you already know for sure the bean must exist, consider declaring a required dependency directly in the constructor. Using `Optional` and always calling `get()` usually adds complexity with no benefit.

### 2.2. Optional does not mean Spring injects null

With the `Optional<AuditSink>` type, the two states are represented using the Optional API itself:

- Bean present: `Optional.of(auditSinkBean)`.
- Bean absent: `Optional.empty()`.

The consumer does not have to check the `Optional` object itself for `null`. Spring provides a valid wrapper in both cases.

### 2.3. What happens when there are multiple beans of the same type?

`Optional<T>` solves the **zero-bean** situation; it does not resolve ambiguity when multiple candidates exist.

Suppose two `AuditSink` beans exist without a clear selection rule:

```java
@Bean
AuditSink fileAuditSink() {
    return new FileAuditSink();
}

@Bean
AuditSink remoteAuditSink() {
    return new RemoteAuditSink();
}
```

When injecting `Optional<AuditSink>`, Spring still must determine which bean matches. If multiple equal candidates exist, resolution can fail with a non-unique bean error, such as `NoUniqueBeanDefinitionException`.

Use `@Qualifier`:

```java
public OrderService(
        @Qualifier("remoteAuditSink") Optional<AuditSink> auditSink) {
    this.auditSink = auditSink;
}
```

Or use `@Primary` on the bean chosen as the default candidate. If you want to use all implementations, inject `List<AuditSink>` or `Map<String, AuditSink>` instead of a single `Optional`.

## 3. `@Nullable`: A Parameter That Can Receive Null

Another way to describe an optional dependency is marking the injection parameter with `@Nullable`. When no matching bean exists, Spring can pass `null` for that parameter instead of requiring a mandatory bean.

Example using the Spring Framework 6 annotation (commonly paired with Spring Boot 3):

```java
package com.example.orders;

import org.springframework.lang.Nullable;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationService {

    private final NotificationSender sender;

    public OrderNotificationService(
            @Nullable NotificationSender sender) {
        this.sender = sender;
    }

    public void notifyOrder(Order order) {
        if (sender != null) {
            sender.sendOrderPlaced(order);
        }
    }
}
```

If a matching `NotificationSender` bean exists, Spring passes that bean. If none exists, Spring can pass `null` because the parameter is marked nullable.

`@Nullable` also expresses a **nullability contract**: the consumer must accept the possibility that the value is absent. It is not an annotation that makes any bean optional in arbitrary places; injection behavior depends on the location and Spring's supported mechanisms.

### 3.1. Choosing the right `@Nullable` annotation

Several annotations named `Nullable` exist in the Java ecosystem. For Spring Boot 3.x applications using Spring Framework 6, the common import is:

```java
import org.springframework.lang.Nullable;
```

Use the annotation supported by the framework and your project's nullability analysis tools. In Spring Framework 7 and newer ecosystems, Spring is moving toward JSpecify-based null-safety; older Spring annotations may be deprecated depending on version. If your project uses a newer version, follow that version's documentation and use `org.jspecify.annotations.Nullable` when appropriate.

Do not mix identically named annotations from different libraries arbitrarily without knowing how Spring, your IDE, and compiler plugins recognize them.

### 3.2. Always check for null in the consumer

Because Spring can pass `null`, code must handle it explicitly:

```java
if (sender != null) {
    sender.sendOrderPlaced(order);
}
```

If you forget the check, a `NullPointerException` will only occur in environments that do not provide the bean. That is why `Optional` is often easier to read: the compiler and API nudge the author to represent both states.

### 3.3. `@Nullable` does not resolve bean ambiguity

If two matching `NotificationSender` beans exist, a nullable parameter does not tell Spring which bean to choose. `@Nullable` only makes **absence** acceptable; if multiple indistinguishable candidates exist, you need `@Qualifier`, `@Primary`, or another injection style.

Example:

```java
public OrderNotificationService(
        @Nullable @Qualifier("emailSender") NotificationSender sender) {
    this.sender = sender;
}
```

Here, the qualifier selects the bean role; nullable permits a bean with that qualifier to be absent.

## 4. Comparing `Optional<T>` and `@Nullable`

Both can represent an optional dependency at Spring-supported injection points, yet they communicate intent differently.

| Criterion | `Optional<T>` | `@Nullable T` |
| --- | --- | --- |
| Representation when bean is absent | `Optional.empty()` | `null` |
| Representation when bean is present | `Optional.of(bean)` | Bean directly |
| Consumer must handle | Inspect Optional or use its API | Perform null check |
| Explicitness in data type | High: type states it may be absent | Relies on annotation |
| Nullability contract | Optional wrapper is non-null; element may be absent | Parameter value itself may be null |
| Usage style | `ifPresent`, `map`, `orElse`, `orElseThrow` | `if (value != null)` |
| Suitable when | You want optionality visible in the Java type | Codebase uses nullability annotations consistently or needs direct type |
| Trade-off | Adds wrapper and should not be overused | Easy to miss null checks; annotation must be recognized by tooling/framework |

### 4.1. Choose one style per dependency

Avoid combining both on the same parameter, such as `@Nullable Optional<AuditSink>`. That creates two layers of "might be missing":

- The Optional may be empty.
- The Optional parameter itself may be null.

In normal designs, Spring injects a non-null `Optional`, so marking the wrapper nullable adds no value and makes the API confusing.

Choose `Optional<T>` **or** `@Nullable T` based on project conventions and how the consumer handles it.

### 4.2. Optional injection vs. Optional in business data

These are two distinct contexts:

- `Optional<AuditSink>` in a constructor: represents whether **a bean exists or not** in the `ApplicationContext`.
- `Optional<PromotionCode>` in a business method: represents whether **data for a single operation** exists or not.

Do not turn every optional field into an optional Spring bean. For instance, a secondary shipping address, promo code, or backup phone number is business data, not dependency injection.

## 5. `ObjectProvider<T>` When Flexible or Deferred Lookup Is Needed

`Optional<T>` and `@Nullable T` are typically resolved when Spring creates the consumer bean. If you need to **obtain the bean at the moment of use**, support lazy lookup, or work with multiple candidates, Spring provides `ObjectProvider<T>`.

Example:

```java
package com.example.orders;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ObjectProvider<AuditSink> auditSinkProvider;

    public OrderService(ObjectProvider<AuditSink> auditSinkProvider) {
        this.auditSinkProvider = auditSinkProvider;
    }

    public void placeOrder(Order order) {
        // Process order...

        auditSinkProvider.ifAvailable(
                sink -> sink.publish(new OrderPlacedEvent(order.id())));
    }
}
```

Spring can inject the provider even when no `AuditSink` exists. Only when `ifAvailable` is called does the provider look up a matching bean in the context.

Commonly used methods:

| Method | Behavior |
| --- | --- |
| `getIfAvailable()` | Returns bean if found; returns `null` if absent; may fail if multiple ambiguous candidates exist |
| `getIfUnique()` | Returns bean if there is a unique or primary candidate; returns `null` if absent or ambiguous |
| `ifAvailable(Consumer<T>)` | Invokes consumer when a matching bean is available |
| `ifUnique(Consumer<T>)` | Invokes consumer when a unique bean is found |
| `getObject()` | Retrieves required bean; throws error if no matching candidate exists |
| `stream()` | Iterates over beans matching the provided type |
| `orderedStream()` | Iterates over beans in Spring-determined order when ordering metadata exists |

Exact behavior also depends on bean scope and creation semantics. A provider does not automatically turn a prototype into a singleton or guarantee a bean initializes without error; it solely provides a lookup mechanism.

### 5.1. Optional vs. Provider: lookup timing differs

| | `Optional<T>` | `ObjectProvider<T>` |
| --- | --- | --- |
| Value injected into consumer | Wrapper containing bean or empty | A provider object |
| Lookup timing | When resolving dependencies at consumer creation | When calling the provider |
| Repeated bean usage | Holds injected Optional reference | Can look up on each invocation |
| Retrieving all beans of same type | Not its primary purpose | Provides `stream()`/`orderedStream()` |
| Useful for | A stable optional dependency | Lazy lookup, multiple beans, dynamically scoped beans, or factory/provider needs |
| Complexity | Simple | More flexible, adds a layer of indirection |

If you only need a single optional bean at startup, `Optional<T>` is usually sufficient. Do not pick `ObjectProvider` just because it looks more powerful; use it when dynamic or lazy lookup is genuinely needed.

### 5.2. Cases with multiple implementations

A plugin-based application may have multiple `PaymentNotifier` or `AuditSink` beans. To invoke all of them:

```java
@Service
public class EventPublisher {

    private final List<AuditSink> sinks;

    public EventPublisher(List<AuditSink> sinks) {
        this.sinks = sinks;
    }

    public void publish(OrderPlacedEvent event) {
        sinks.forEach(sink -> sink.publish(event));
    }
}
```

Spring typically injects an empty collection if no matching bean exists, so the consumer can iterate over the list without needing `Optional<List<AuditSink>>` in normal scenarios.

If you need to look up the list of beans at usage time, `ObjectProvider<AuditSink>` with `orderedStream()` is an option.

## 6. Optional Setter Injection and `@Autowired(required = false)`

Spring also supports optional dependencies through certain method injection styles. Example setter:

```java
@Component
public class LegacyReportService {

    private MetricsRecorder metricsRecorder;

    @Autowired(required = false)
    public void setMetricsRecorder(MetricsRecorder metricsRecorder) {
        this.metricsRecorder = metricsRecorder;
    }
}
```

With `required = false`, Spring does not require finding a bean for this injection point. If the dependency is absent, the injection method may not be invoked.

You can combine nullable annotations on setter parameters where appropriate, though you should pick one consistent style.

### 6.1. Why is constructor injection usually still better?

Setter injection allows dependencies to be attached after the object has been constructed. This can create a temporary state lacking the dependency, and the field usually cannot be `final`.

Constructor injection declares dependencies right at object creation:

```java
@Service
public class ReportService {

    private final Optional<MetricsRecorder> metricsRecorder;

    public ReportService(Optional<MetricsRecorder> metricsRecorder) {
        this.metricsRecorder = metricsRecorder;
    }
}
```

For dependencies that are genuinely optional and used throughout the service's lifecycle, this is generally easier to read, easier to test, and avoids partially configured object states.

### 6.2. Be cautious with `@Autowired(required = false)` on constructors

A constructor determines how the object is created, so making the entire constructor optional can cause Spring to pick another constructor or instantiation path. When expressing an optional dependency, **putting `Optional<T>` or `@Nullable` on a parameter of the required constructor** is usually clearer.

Use `required = false` mainly for intentional method/field injection or legacy code, not as the default for new constructor injection.

## 7. Optional Dependencies and Fallback Behavior

Merely recognizing a missing bean is not enough. The consumer needs **well-defined behavior** for when the bean is absent.

Suppose the system has a `MetricsRecorder`:

```java
public interface MetricsRecorder {
    void recordOrderPlaced();
}
```

If metrics are purely an observability utility, they can be skipped when not installed:

```java
@Service
public class OrderMetricsService {

    private final Optional<MetricsRecorder> recorder;

    public OrderMetricsService(Optional<MetricsRecorder> recorder) {
        this.recorder = recorder;
    }

    public void recordPlaced() {
        recorder.ifPresent(MetricsRecorder::recordOrderPlaced);
    }
}
```

However, if you want consumers not to care whether metrics are enabled, you can use the **Null Object pattern**: always supply a no-op implementation.

Example:

```java
@Component
@ConditionalOnProperty(
        prefix = "features.metrics",
        name = "enabled",
        havingValue = "false",
        matchIfMissing = true
)
public class NoOpMetricsRecorder implements MetricsRecorder {

    @Override
    public void recordOrderPlaced() {
        // Intentionally perform no operation.
    }
}
```

The real implementation can be registered when the property is enabled:

```java
@Component
@ConditionalOnProperty(
        prefix = "features.metrics",
        name = "enabled",
        havingValue = "true"
)
public class PrometheusMetricsRecorder implements MetricsRecorder {

    @Override
    public void recordOrderPlaced() {
        // Record metric using the real integration.
    }
}
```

With this configuration, the consumer can inject `MetricsRecorder` as **required**, since a matching implementation always exists when conditions and component scanning are set up as expected. Make sure the two conditions never register both beans simultaneously and that the real metrics library is present when the feature is enabled.

### 7.1. Optional bean or Null Object?

| Approach | What the consumer must do | Best suited when |
| --- | --- | --- |
| `Optional<T>` | Check if bean exists before calling | Consumer needs to react differently when integration is unconfigured |
| `@Nullable T` | Check for null | Codebase uses nullability annotations and null is an explicit contract |
| No-op implementation | Always call interface normally | Missing integration has the same "do nothing" meaning for consumers |
| `ObjectProvider<T>` | Look up when needed | Bean may be lazy, scoped, or have multiple candidates |

No-op is not always right. If a missing implementation should raise an alert, return an error, or reject an operation, a no-op can hide the problem. Pick the fallback based on business meaning.

### 7.2. Optional dependency is not the same as an optional feature flag

The two mechanisms can work together, but they are distinct:

- `@ConditionalOnProperty` decides **whether to register a bean** based on a property.
- `Optional<T>` or `@Nullable` decides **how a consumer handles a bean's absence**.

For example, `features.metrics.enabled=false` may prevent the metrics bean from being registered; `Optional<MetricsRecorder>` allows the service to still be created when the bean is absent. With a No-op implementation, consumers do not need optional injection because a substitute bean is always present.

## 8. Optional Bean vs. Optional Configuration Property

Do not confuse an optional dependency with an optional property.

Example property:

```yaml
partner:
  endpoint: https://partner.example
```

If the property might be absent, you can use:

```java
@Value("DOLLAR{partner.endpoint:}")
private String endpoint;
```

or use `@ConfigurationProperties` with appropriate defaults and validation. However, an absent property **does not by itself dictate** whether a `PartnerClient` bean exists.

Factory method example:

```java
@Bean
@ConditionalOnProperty(prefix = "partner", name = "endpoint")
PartnerClient partnerClient(PartnerProperties properties) {
    return new PartnerClient(properties.endpoint());
}
```

Here, the property controls whether the bean is created; a consumer injecting `Optional<PartnerClient>` can handle the case where the bean does not exist. The two layers collaborate while answering two separate questions.

### 8.1. Do not use an empty string as "optional" without defining its meaning

`partner.endpoint: ""` is still a present string value. If using an empty string to mean "disabled," document and check for it explicitly. Usually a boolean property like `partner.enabled` or a clear conditional property is easier to understand.

### 8.2. Validate configuration when a feature is enabled

If `partner.enabled=true`, then endpoint, timeout, and credentials must be valid. Combine `@ConfigurationProperties` with validation so the application fails fast when the feature is enabled with missing config. When disabled, the client bean is not created and consumers execute their chosen fallback.

Do not let optional injection mask misconfiguration of a feature an operator intentionally enabled.

## 9. Beans with Multiple Candidates: Optional Does Not Replace Qualifier

Suppose two implementations exist:

```java
@Component("emailNotificationSender")
class EmailNotificationSender implements NotificationSender {
    // ...
}

@Component("smsNotificationSender")
class SmsNotificationSender implements NotificationSender {
    // ...
}
```

Injecting:

```java
public NotificationService(Optional<NotificationSender> sender) {
    this.sender = sender;
}
```

can still be ambiguous because Spring must decide which candidate represents `NotificationSender`. There are three directions:

1. Use `@Qualifier` to choose the exact implementation.
2. Use `@Primary` if there is a default implementation.
3. Inject `List<NotificationSender>`/`Map<String, NotificationSender>` if you want all of them.

Qualifier example:

```java
public NotificationService(
        @Qualifier("emailNotificationSender")
        Optional<NotificationSender> sender) {
    this.sender = sender;
}
```

In this example, the dependency is only optional if the bean carrying that qualifier might be absent; if multiple beans share the qualifier or configuration is wrong, inspect the actual resolution.

**Optional handles zero candidates; qualifier/primary handles selecting among candidates.** These are two orthogonal dimensions of autowiring.

## 10. Optional Injection and Bean Lifecycle

Differences in lookup timing can affect the application.

### 10.1. `Optional<T>` is resolved when creating the consumer

Example:

```java
@Service
class NotificationFacade {

    private final Optional<NotificationSender> sender;

    NotificationFacade(Optional<NotificationSender> sender) {
        this.sender = sender;
    }
}
```

Spring resolves the `Optional` when creating `NotificationFacade`. The consumer keeps the injected result. If the context has no sender at that moment, the `Optional` remains empty for the lifetime of that instance.

This is a good fit when the bean set is stable after startup.

### 10.2. `ObjectProvider<T>` allows lookup at invocation time

```java
@Service
class NotificationFacade {

    private final ObjectProvider<NotificationSender> senderProvider;

    NotificationFacade(ObjectProvider<NotificationSender> senderProvider) {
        this.senderProvider = senderProvider;
    }

    void notify(Notification event) {
        senderProvider.ifAvailable(sender -> sender.send(event));
    }
}
```

The provider is injected immediately, while the bean is looked up when `ifAvailable` is called. This is useful with certain scopes and when deferring bean retrieval. However, a Spring singleton bean graph generally does not change arbitrarily at runtime; a provider is not an automatic plugin hot-plug mechanism.

### 10.3. Prototype beans and repeated lookups

If a bean has prototype scope, injecting the prototype directly into a singleton constructor usually captures only a single instance when the singleton is created. When you want a fresh instance per operation, `ObjectProvider<T>` or a factory abstraction is more suitable.

Do not use `Optional<T>` as a factory for creating new instances. `Optional` simply wraps an already-resolved value.

## 11. Testing Optional Dependencies

Optional dependencies should be tested in both states: **bean present** and **bean absent**.

### 11.1. Unit test with `Optional.empty()`

With `OrderService` having an `Optional`-accepting constructor:

```java
class OrderServiceTest {

    @Test
    void placesOrderWhenAuditIsAbsent() {
        OrderService service = new OrderService(Optional.empty());

        Order order = new Order("O-100");

        service.placeOrder(order);

        // Assert that core business outcomes remain correct.
    }
}
```

`Order` and order persistence in the example need to be implemented per the application. The purpose is to demonstrate that you can test the consumer without creating a Spring context or registering an audit bean.

### 11.2. Unit test with the bean present

```java
@Test
void publishesAuditWhenSinkIsPresent() {
    AuditSink sink = mock(AuditSink.class);
    OrderService service = new OrderService(Optional.of(sink));

    Order order = new Order("O-101");
    service.placeOrder(order);

    verify(sink).publish(new OrderPlacedEvent(order.id()));
}
```

This example uses Mockito and requires corresponding imports/static setup. It verifies behavior when the dependency is present.

### 11.3. Testing `@Nullable`

```java
@Test
void serviceWorksWithoutOptionalSender() {
    OrderNotificationService service =
            new OrderNotificationService(null);

    assertDoesNotThrow(() -> service.notifyOrder(new Order("O-102")));
}
```

Because `@Nullable` is purely a contract annotation, when calling the constructor directly in a unit test, the test itself must pass `null` to simulate the missing-bean scenario. No Spring container automatically substitutes arguments when a test calls `new`.

### 11.4. Testing real wiring with a Spring context

When you want to verify that Spring actually injects `Optional.empty()` or a nullable parameter, you can use `@SpringBootTest`, `@ContextConfiguration`, or `@SpringJUnitConfig` with a minimal test configuration.

A test class can define a `@TestConfiguration` providing only selected beans, then assert that the consumer is created when the optional bean is absent. For configurations with multiple profiles/conditionals, context integration tests are more valuable than plain unit tests.

Avoid booting the entire application and a real database if the goal is just to verify a constructor accepts `Optional`; keep tests small to pinpoint issues easily.

## 12. Common Errors and How to Handle Them

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` even though dependency is meant to be optional | Parameter still declared as required type, nullable annotation unrecognized, or misconfigured | Use `Optional<T>`, a supported `@Nullable`, or provider; check imports/version |
| `NoUniqueBeanDefinitionException` with `Optional<T>` | Multiple beans of same type and no unique candidate | Use `@Qualifier`/`@Primary` or a collection |
| `NullPointerException` | Using a nullable dependency without null check | Add null check or switch to `Optional` |
| `NoSuchElementException` | Calling `Optional.get()` when Optional is empty | Use `ifPresent`, `orElse`, or `orElseThrow` with a meaningful error |
| Feature skipped even though enabled | Bean not registered due to profile/conditional/property or package scan | Check property, active profile, condition report, and component scan |
| Bean is injected, but initialization fails | Factory method or bean's own dependency throws exception | Read root cause; optional does not suppress creation errors once a bean is selected |
| Provider lookup still fails | Multiple candidates or bean initialization fails | Use qualifier/primary; inspect candidates and startup errors |
| Optional setter is not invoked | `@Autowired(required=false)` and dependency does not exist | Expected behavior; handle the un-injected state |
| Using Optional, yet consumer always requires the bean | Optional design mismatches real behavior | Declare a required dependency or fail fast explicitly |
| Calling constructor directly in test without Spring expecting auto-injection | Unit test calls `new` directly without container | Pass `Optional.empty()` or `null` intentionally |

### 12.1. Distinguishing a missing bean from a bean that fails to initialize

Optional injection handles the case where **no matching candidate is found**. It is not a mechanism to swallow exceptions during bean creation.

For instance, an `AuditSink` bean exists, but its factory method throws an exception due to missing credentials or an unreachable external service. Spring will still fail to create the bean/context. Do not expect `Optional<AuditSink>` to turn configuration or connection failures into `Optional.empty()`.

This is an important distinction:

- No bean exists: optional resolution can return empty/null per the declared type.
- Bean exists but initialization fails: bean creation errors can fail the context.
- Bean exists but runtime operations fail: consumer must handle business/network errors separately.

### 12.2. Checking conditions and bean registration config

If an optional bean does not appear, inspect:

- Is the class containing `@Bean` imported/scanned?
- Does the bean have `@Profile` or `@ConditionalOnProperty`?
- Are the actual property and profile values right?
- Is the required dependency on the classpath?
- Did auto-configuration back off because of another bean?
- Was there an earlier bean initialization error?

For auto-configuration, run the application with `--debug` to view the Condition Evaluation Report when needed.

## 13. Design Rules: Do Not Make Every Dependency Optional

Optional injection is helpful, yet overusing it creates services with many branches and unpredictable states.

Several principles:

1. **Keep dependencies required by default.** If a class cannot do its job properly without a dependency, declare it directly in the constructor.
2. **Make optional only when valid fallback behavior exists.** Document clearly what happens when the bean is absent.
3. **Prefer types that communicate intent.** `Optional<T>` is often easier to read than null when consumers must handle both states.
4. **Use qualifiers for bean selection.** Optional does not replace mechanisms for resolving multiple candidates.
5. **Consider a No-op implementation.** When "do nothing" is valid default behavior, Null Object can eliminate branching in consumers.
6. **Use providers when deferred lookup is needed.** Do not turn providers into a generic service locator where every class looks up beans itself.
7. **Do not hide initialization failures.** Optional is not a way to catch exceptions or ignore broken dependencies.
8. **Keep configuration clear.** When a feature is enabled, its bean and properties must be valid; when disabled, the fallback must make sense.
9. **Test both states.** A test with only the bean present does not prove the consumer handles a missing bean properly.
10. **Follow the project's nullability conventions.** Choose annotations compatible with your Spring/Java version and static analysis tools.

## 14. Practice Exercise: Toggleable Audit Integration

This exercise assumes an order service that can record audit events. Auditing is a secondary feature in demo environments, yet can be enabled in environments needing observability.

### Step 1 — Create the interface

```java
package com.example.orders;

public interface AuditSink {
    void publish(String event);
}
```

### Step 2 — Create a conditional implementation

Example of an implementation that logs when a property is enabled:

```java
package com.example.orders;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        prefix = "features.audit",
        name = "enabled",
        havingValue = "true"
)
public class LoggingAuditSink implements AuditSink {

    @Override
    public void publish(String event) {
        System.out.println("AUDIT: " + event);
    }
}
```

This is an illustrative implementation; a real application may write to a dedicated audit system.

### Step 3 — Inject Optional into the service

```java
package com.example.orders;

import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final Optional<AuditSink> auditSink;

    public OrderService(Optional<AuditSink> auditSink) {
        this.auditSink = auditSink;
    }

    public void placeOrder(String orderId) {
        // Execute order placement business logic.

        auditSink.ifPresent(sink ->
                sink.publish("Order placed: " + orderId));
    }
}
```

### Step 4 — Toggle the property

By default, auditing can be disabled:

```yaml
features:
  audit:
    enabled: false
```

When enabled:

```yaml
features:
  audit:
    enabled: true
```

In practice, the property can live in a profile or external config source. When disabled, no `AuditSink` exists and the `Optional` is empty. When enabled, Spring registers `LoggingAuditSink` and the `Optional` holds the bean.

### Step 5 — Write unit tests for both cases

- Instantiate the service with `Optional.empty()` and verify core business logic still runs.
- Instantiate the service with a mock `AuditSink` and verify `publish` is called.
- To verify `@ConditionalOnProperty`, write a context test for both property values and check bean presence/absence.

### Self-check questions

1. How do required and optional dependencies differ when a bean does not exist?
2. What does Spring inject for `Optional<AuditSink>` when no bean exists?
3. How does `@Nullable` differ from `Optional` in representing the missing state?
4. Why doesn't `Optional` automatically resolve having two beans of the same type?
5. When should `ObjectProvider<T>` be used instead of `Optional`?
6. What does `@Autowired(required=false)` on a setter mean?
7. Does optional injection swallow exceptions if a bean exists but fails to initialize?
8. When is a Null Object better than checking `Optional` inside every consumer?
9. Is an optional dependency the same as an optional property?
10. If a feature is enabled but its bean is not registered, what should you check?

## 15. Quick Selection Table

| Need | Suitable option to consider |
| --- | --- |
| Bean must exist for the service to function | Required constructor injection `T` |
| Bean may be absent; consumer wants it explicit in the Java type | Constructor `Optional<T>` |
| Codebase uses nullability annotations and accepts null | Constructor parameter `@Nullable T` |
| Need deferred or repeated bean lookup | `ObjectProvider<T>` |
| Need all implementations | `List<T>`, `Map<String, T>`, or provider stream |
| Auxiliary integration can be disabled; doing nothing is valid | No-op implementation or `Optional`, depending on design |
| Only one bean enabled per environment | `@Profile` or `@ConditionalOnProperty`, paired with suitable injection |
| Multiple beans of the same type | `@Qualifier` or `@Primary` |
| Missing dependency is a serious configuration error | Keep injection required and fail fast |

Optional dependency injection gives applications flexibility when integrations are not always present. Yet that flexibility is only valuable when behavior during absence is clearly designed. Use `Optional<T>` to express two states explicitly, `@Nullable` when nullability is an agreed-upon contract, and `ObjectProvider<T>` when deferred lookup is truly required. For core dependencies, keep them required so Spring detects misconfiguration right from the start.
