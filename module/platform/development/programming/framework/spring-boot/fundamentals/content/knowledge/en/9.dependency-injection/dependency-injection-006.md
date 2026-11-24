# Injecting a List, Set, or Map of Multiple Beans of the Same Type

In a Spring Boot application, there are times when a service needs to use **multiple implementations of the same interface**. For example, a payment system may support cards, e-wallets, and bank transfers; a notification system may have email, SMS, and push notifications. If every time we added a new implementation we had to edit the constructor to add another parameter, the code would quickly become unwieldy.

Spring supports **collection injection**: when a dependency has a specific element type, the container can find all matching beans and provide them as a **List**, **Set**, array, or **Map<String, T>**.

Example:

~~~java
public interface PaymentHandler {
    boolean supports(String method);
    void pay(long orderId);
}
~~~

If the context has three beans implementing `PaymentHandler`, a constructor can accept:

~~~java
public PaymentDispatcher(List<PaymentHandler> handlers) {
    this.handlers = handlers;
}
~~~

Spring resolves the matching beans and passes the collection into the constructor. This lets the service work with a set of implementations configured in the context while reducing coupling to individual concrete classes.

## 1. How Does Collection Injection Work?

The Spring IoC container does not only resolve a single bean for a single dependency. For certain special dependency types, Spring can look up **multiple candidates of the same type** and aggregate them into a collection.

Common forms:

| Dependency type | Result |
|---|---|
| **T[]** | Array containing beans matching type T. |
| **List<T>** | List of beans matching type T. |
| **Set<T>** | Set of beans matching type T. |
| **Map<String, T>** | Map from bean name to beans matching type T. |

Here, **T** can be a concrete class or an interface. The most common usage is declaring the dependency as an interface so implementations can be replaced or extended.

~~~text
ApplicationContext
    ├── cardPaymentHandler : PaymentHandler
    ├── walletPaymentHandler : PaymentHandler
    └── bankTransferHandler : PaymentHandler
                  │
                  ▼
       Injection point: List<PaymentHandler>
                  │
                  ▼
       [card, wallet, bank transfer]
~~~

Importantly, collection elements are **beans resolved by the container**. Spring does not simply scan every Java class in the project and call `new` on every class implementing the interface. Each implementation must be registered as a bean via component scanning, `@Bean`, imports, auto-configuration, or another valid bean registration mechanism.

## 2. Preparing Multiple Implementations of the Same Type

Suppose an application needs multiple payment channels:

~~~java
package com.example.payment;

public interface PaymentHandler {
    String method();
    void pay(long orderId);
}
~~~

Card payment implementation:

~~~java
package com.example.payment;

import org.springframework.stereotype.Component;

@Component("cardPaymentHandler")
public class CardPaymentHandler implements PaymentHandler {
    @Override
    public String method() {
        return "card";
    }

    @Override
    public void pay(long orderId) {
        System.out.println("Card payment for order " + orderId);
    }
}
~~~

E-wallet implementation:

~~~java
package com.example.payment;

import org.springframework.stereotype.Component;

@Component("walletPaymentHandler")
public class WalletPaymentHandler implements PaymentHandler {
    @Override
    public String method() {
        return "wallet";
    }

    @Override
    public void pay(long orderId) {
        System.out.println("Wallet payment for order " + orderId);
    }
}
~~~

Bank transfer implementation:

~~~java
package com.example.payment;

import org.springframework.stereotype.Component;

@Component("bankTransferPaymentHandler")
public class BankTransferPaymentHandler implements PaymentHandler {
    @Override
    public String method() {
        return "bank-transfer";
    }

    @Override
    public void pay(long orderId) {
        System.out.println("Bank transfer payment for order " + orderId);
    }
}
~~~

If the package is within component scan scope, Spring can register these three classes as three beans. Each bean shares the assignable type **PaymentHandler**, while having a distinct bean name.

Besides component annotations, implementations can also be registered using Java configuration:

~~~java
@Configuration
public class PaymentConfiguration {
    @Bean
    PaymentHandler cardPaymentHandler() {
        return new CardPaymentHandler();
    }

    @Bean
    PaymentHandler walletPaymentHandler() {
        return new WalletPaymentHandler();
    }
}
~~~

The default bean names in the example above are the factory method names: **cardPaymentHandler** and **walletPaymentHandler**. When declared via `@Bean`, the implementation class does not need `@Component`.

Avoid both component-scanning a class and declaring an additional `@Bean` that creates the same implementation unintentionally, as that may register two separate beans for the same role.

## 3. Injecting `List<T>`

**List<T>** is a convenient choice when a service needs to iterate over implementations in a meaningful order.

~~~java
package com.example.payment;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class PaymentDispatcher {
    private final List<PaymentHandler> handlers;

    public PaymentDispatcher(List<PaymentHandler> handlers) {
        this.handlers = handlers;
    }

    public void pay(String method, long orderId) {
        PaymentHandler handler = handlers.stream()
                .filter(candidate -> candidate.method().equals(method))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Unsupported method: " + method));

        handler.pay(orderId);
    }
}
~~~

If three `PaymentHandler` beans exist, Spring can pass a `List` containing all three. Because the service depends only on the interface, when a newly registered implementation is added, the list can include the new element without editing the constructor.

### 3.1. Element ordering in a List

Spring supports sorting beans in ordered collection dependencies, typically arrays and Lists, based on mechanisms such as:

- The **Ordered** interface.
- The **@Order** annotation.
- **@Priority** where supported by Spring.

Example:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(1)
public class CardPaymentHandler implements PaymentHandler {
    // ...
}
~~~

~~~java
@Component
@Order(2)
public class WalletPaymentHandler implements PaymentHandler {
    // ...
}
~~~

~~~java
@Component
@Order(3)
public class BankTransferPaymentHandler implements PaymentHandler {
    // ...
}
~~~

Smaller order values have higher priority in standard sorting order. If no order is declared, do not rely on the accidental order of component scanning or bean registration as a business contract.

An implementation can also implement `Ordered`:

~~~java
import org.springframework.core.Ordered;

public class CardPaymentHandler implements PaymentHandler, Ordered {
    @Override
    public int getOrder() {
        return 10;
    }

    // PaymentHandler methods...
}
~~~

Avoid mixing multiple ordering sources without understanding Spring's precedence rules and how its comparator behaves. Adopting one consistent convention across implementations is easier to maintain.

**@Order controls the order inside sorted injection points; it does not determine singleton initialization order.** Bean startup initialization order is a separate concern involving dependencies, lazy initialization, `@DependsOn`, and lifecycle.

### 3.2. When is List a good fit?

List fits well when:

- You need to run all implementations in a specific sequence.
- You need to apply multiple validators or rules in order.
- You need a pipeline of multiple processors.
- You need to iterate through strategies and find a matching one.
- You want to verify the list of implementations in tests.

If order is part of business semantics, declare **@Order** explicitly and test that order. Do not let outcomes depend on class names or file ordering.

## 4. Injecting `Set<T>`

**Set<T>** is suitable when you need a set of beans of the same type and do not want processing order to be part of the contract.

~~~java
import java.util.Set;
import org.springframework.stereotype.Service;

@Service
public class PaymentCapabilityRegistry {
    private final Set<PaymentHandler> handlers;

    public PaymentCapabilityRegistry(Set<PaymentHandler> handlers) {
        this.handlers = handlers;
    }

    public boolean supports(String method) {
        return handlers.stream()
                .anyMatch(handler -> handler.method().equals(method));
    }
}
~~~

Spring resolves the matching beans and converts them into the requested `Set` type. Because `Set` does not express ordering the way `List` does, **do not rely on iteration order** to decide business strategies. If order matters, use `List` and `@Order`.

### 4.1. Set does not automatically deduplicate different beans just because they share a type

The three beans `CardPaymentHandler`, `WalletPaymentHandler`, and `BankTransferPaymentHandler` are three distinct instances, so a normal `Set` can hold all three.

A `Set` eliminates duplicates based on object equality/hashCode rules. If beans are designed with custom `equals`/`hashCode` that treat two instances as equal, the created `Set` collection might retain only one element. For Spring strategy beans, you generally should not override equality in a way that treats independent implementations as equal if the goal is to keep all of them.

### 4.2. Do not use Set when order matters

For example, a list of validators that must run sequentially:

~~~text
1. Format validation
2. Authorization check
3. Limit check
4. Business state validation
~~~

If order affects the outcome, **List<Validator>** with `@Order` expresses intent better than **Set<Validator>**. `Set` is better suited for answering "what capabilities exist?" or "does any implementation satisfy a condition?" without depending on order.

## 5. Injecting `Map<String, T>`

**Map<String, T>** is useful when you need to look up a bean by name. With collection injection, the map key is the **bean name**, and the value is the bean instance of type `T`.

~~~java
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class PaymentHandlerRegistry {
    private final Map<String, PaymentHandler> handlersByBeanName;

    public PaymentHandlerRegistry(
            Map<String, PaymentHandler> handlersByBeanName) {
        this.handlersByBeanName = handlersByBeanName;
    }

    public PaymentHandler getByBeanName(String beanName) {
        PaymentHandler handler = handlersByBeanName.get(beanName);
        if (handler == null) {
            throw new IllegalArgumentException(
                    "No PaymentHandler bean found: " + beanName);
        }
        return handler;
    }
}
~~~

If the context has beans declared with names:

- **cardPaymentHandler**
- **walletPaymentHandler**
- **bankTransferPaymentHandler**

then the map has the structure:

~~~text
handlersByBeanName
├── "cardPaymentHandler"          → CardPaymentHandler
├── "walletPaymentHandler"        → WalletPaymentHandler
└── "bankTransferPaymentHandler"  → BankTransferPaymentHandler
~~~

This map is not a map from payment method name to handler unless bean names are intentionally aligned with `method()`. Keys reflect **bean names**, not values returned from `handler.method()`.

### 5.1. Default bean names and custom names

With a component:

~~~java
@Component
public class CardPaymentHandler implements PaymentHandler {
}
~~~

The default bean name is typically **cardPaymentHandler**, following component naming rules. With:

~~~java
@Component("creditCard")
public class CardPaymentHandler implements PaymentHandler {
}
~~~

the key will be **creditCard**. With `@Bean`:

~~~java
@Bean
PaymentHandler walletHandler() {
    return new WalletPaymentHandler();
}
~~~

the default bean name is **walletHandler**.

If the application renames a bean, code looking up the map by name must be updated accordingly. Therefore, when a name is part of an external business contract, define a dedicated business key instead of forcing public APIs to depend on internal bean names.

### 5.2. `Map<String, T>` vs. `Map<DomainKey, T>`

Spring collection injection specifically supports **Maps with String keys** so bean names serve as keys. Example:

~~~java
Map<String, PaymentHandler> handlers;
~~~

Do not expect Spring to automatically build:

~~~java
Map<PaymentMethod, PaymentHandler> handlers;
~~~

where `PaymentMethod` is an enum or arbitrary domain type, by inferring keys from a method on each bean. If you want to map by a business code, inject a `List` or `Map<String, T>` and build the registry yourself:

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, PaymentHandler> handlersByMethod =
        handlers.stream().collect(Collectors.toMap(
                PaymentHandler::method,
                Function.identity()
        ));
~~~

This snippet illustrates converting a `List` into a map keyed by **method()**. If two handlers return the same method, `Collectors.toMap` throws an exception for duplicate keys unless a merge function is provided. That is usually desirable because it surfaces duplicate capability configuration instead of silently picking one bean.

## 6. Example Comparing the Three Collection Types

Suppose three `PaymentHandler` implementations are registered. A class can accept each collection type depending on its purpose:

~~~java
@Service
public class PaymentCatalog {
    private final List<PaymentHandler> orderedHandlers;
    private final Set<PaymentHandler> handlerSet;
    private final Map<String, PaymentHandler> handlersByName;

    public PaymentCatalog(
            List<PaymentHandler> orderedHandlers,
            Set<PaymentHandler> handlerSet,
            Map<String, PaymentHandler> handlersByName) {
        this.orderedHandlers = orderedHandlers;
        this.handlerSet = handlerSet;
        this.handlersByName = handlersByName;
    }
}
~~~

Each parameter is resolved as an independent dependency:

| Parameter | Used for |
|---|---|
| **orderedHandlers** | Iterating over handlers in configured order. |
| **handlerSet** | Representing the set of handlers provided by the context. |
| **handlersByName** | Looking up a handler by bean name. |

In real code, you do not need to inject all three if you only need one. Each collection may contain the same beans, yet their access patterns and contracts differ.

## 7. `@Qualifier` When You Only Want a Subset of Beans

Sometimes a context contains multiple beans of the same type, but a consumer only needs a **subset**. In that case, qualifiers can be used.

Example with annotated processors:

~~~java
@Component
@org.springframework.beans.factory.annotation.Qualifier("online")
public class CardPaymentHandler implements PaymentHandler {
    // ...
}
~~~

~~~java
@Component
@org.springframework.beans.factory.annotation.Qualifier("online")
public class WalletPaymentHandler implements PaymentHandler {
    // ...
}
~~~

~~~java
@Component
@org.springframework.beans.factory.annotation.Qualifier("offline")
public class BankTransferPaymentHandler implements PaymentHandler {
    // ...
}
~~~

The consumer receives only the online group:

~~~java
@Service
public class OnlinePaymentDispatcher {
    private final List<PaymentHandler> handlers;

    public OnlinePaymentDispatcher(
            @org.springframework.beans.factory.annotation.Qualifier("online")
            List<PaymentHandler> handlers) {
        this.handlers = handlers;
    }
}
~~~

At a collection injection point, a qualifier **filters candidates** to include only beans matching that qualifier. It does not force selecting just one bean as it does when injecting a single dependency.

### 7.1. Qualifiers are not just bean names

A bean name can act as a fallback qualifier in some situations, but the primary purpose of **@Qualifier** is metadata for filtering candidates semantically. Name qualifiers after roles like **online**, **retryable**, or **regional** instead of tying everything to class names.

You can define a custom qualifier annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

@Target({ElementType.TYPE, ElementType.FIELD, ElementType.PARAMETER,
         ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface OnlinePayment {
}
~~~

Annotate implementations:

~~~java
@Component
@OnlinePayment
public class CardPaymentHandler implements PaymentHandler {
    // ...
}
~~~

Inject the group:

~~~java
public OnlinePaymentDispatcher(
        @OnlinePayment List<PaymentHandler> handlers) {
    this.handlers = handlers;
}
~~~

Custom qualifiers express roles clearly and reduce typos in string names.

## 8. Does `@Primary` Affect Collection Injection?

**@Primary** prioritizes one bean when multiple candidates exist for a single typed dependency. Example:

~~~java
@Component
@Primary
public class CardPaymentHandler implements PaymentHandler {
    // ...
}
~~~

When a constructor asks for:

~~~java
public CheckoutService(PaymentHandler handler) {
    this.handler = handler;
}
~~~

Spring can select `CardPaymentHandler` as the preferred candidate if no qualifier or other factor dictates otherwise.

However, when the dependency is:

~~~java
public PaymentCatalog(List<PaymentHandler> handlers) {
    this.handlers = handlers;
}
~~~

the goal is to receive **all matching candidates**. `@Primary` does not exclude the other beans from the collection. This is an important distinction between injecting a single bean and injecting a collection of beans.

If you only want a subset, use a qualifier. If you want all of them, do not use `@Primary` expecting the collection to contain only one element.

## 9. What Happens When No Matching Bean Exists?

Collection injection does not guarantee an empty collection is always injected. For a required dependency, if Spring finds no matching candidate, resolution may fail and the context will not start.

Example:

~~~java
@Service
public class PaymentDispatcher {
    private final List<PaymentHandler> handlers;

    public PaymentDispatcher(List<PaymentHandler> handlers) {
        this.handlers = handlers;
    }
}
~~~

If no matching `PaymentHandler` bean exists and the dependency is considered required, Spring can throw an error stating the corresponding dependency could not be found. Exact behavior depends on how the injection is declared and the resolution rules.

If business rules allow **zero implementations**, express optionality explicitly rather than assuming a collection will always be empty.

### 9.1. Using `ObjectProvider` when an empty collection is valid

Spring provides **ObjectProvider<T>** to query beans on demand:

~~~java
import java.util.List;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class OptionalPaymentRegistry {
    private final ObjectProvider<PaymentHandler> handlerProvider;

    public OptionalPaymentRegistry(
            ObjectProvider<PaymentHandler> handlerProvider) {
        this.handlerProvider = handlerProvider;
    }

    public List<PaymentHandler> getHandlers() {
        return handlerProvider.orderedStream().toList();
    }
}
~~~

If no `PaymentHandler` exists, **orderedStream()** provides an empty stream and the resulting list is empty. This also defers bean resolution/initialization until the provider is called.

### 9.2. Using `Optional` for a single dependency

If at most one bean can exist and its presence is optional, you can use:

~~~java
public NotificationService(
        Optional<NotificationGateway> gateway) {
    this.gateway = gateway;
}
~~~

`Optional` expresses a single dependency that may be absent. It is not an automatic replacement for **List<T>** or **Map<String, T>** when you want to receive multiple implementations.

### 9.3. Be careful with `@Autowired(required = false)`

Field or method injection with **@Autowired(required = false)** lets Spring skip a missing dependency. However, when no bean exists, the collection field may remain unassigned; you must handle the null case properly. If you want a collection that is always non-null and can be empty, **ObjectProvider.orderedStream()** usually communicates the intent more clearly.

## 10. Generic Types Determine Which Beans Spring Finds

Spring uses the type information at the injection point to determine candidates. For instance:

~~~java
List<PaymentHandler> handlers;
~~~

requests beans compatible with **PaymentHandler**, not every bean in the context.

Similarly:

~~~java
Map<String, PaymentHandler> handlers;
~~~

is interpreted as a map from bean names to beans of type `PaymentHandler`.

### 10.1. Using an interface to gather multiple implementations

This is a common design pattern:

~~~java
public interface FileExporter {
    String format();
    byte[] export(Object data);
}
~~~

~~~java
@Component
class CsvExporter implements FileExporter {
    public String format() { return "csv"; }
    public byte[] export(Object data) { return new byte[0]; }
}
~~~

~~~java
@Component
class JsonExporter implements FileExporter {
    public String format() { return "json"; }
    public byte[] export(Object data) { return new byte[0]; }
}
~~~

Consumer:

~~~java
public ExportService(List<FileExporter> exporters) {
    this.exporters = exporters;
}
~~~

Spring gathers the beans implementing the interface and matching the generic type. The consumer does not need to import `CsvExporter` or `JsonExporter`.

### 10.2. Generic types can distinguish beans

Spring supports generic-aware type matching during autowiring. Example of a generic interface:

~~~java
public interface Store<T> {
    void save(T value);
}
~~~

Two implementations:

~~~java
@Component
public class StringStore implements Store<String> {
    public void save(String value) {
        // ...
    }
}
~~~

~~~java
@Component
public class IntegerStore implements Store<Integer> {
    public void save(Integer value) {
        // ...
    }
}
~~~

Injection:

~~~java
public StringStoreConsumer(List<Store<String>> stores) {
    this.stores = stores;
}
~~~

Spring can use generic metadata to distinguish **Store<String>** from **Store<Integer>** when selecting candidates. This is useful when multiple beans share the same raw interface while representing different data types.

Generic matching still depends on type metadata Spring can infer. If an implementation uses raw types, generics are erased through inheritance structures, or a factory method declares an overly broad return type, matching may not work as expected. In such cases, inspect generic signatures and consider explicit qualifiers.

## 11. Ordering, Duplicates, and Choosing Implementations

When receiving multiple beans, decide how the consumer uses them.

### 11.1. List and `@Order`

Validator example:

~~~java
public interface OrderValidator {
    void validate(OrderRequest request);
}
~~~

~~~java
@Component
@Order(10)
class RequiredFieldsValidator implements OrderValidator {
    public void validate(OrderRequest request) {
        // Validate required fields.
    }
}
~~~

~~~java
@Component
@Order(20)
class StockValidator implements OrderValidator {
    public void validate(OrderRequest request) {
        // Check inventory stock.
    }
}
~~~

~~~java
@Service
class OrderValidationPipeline {
    private final List<OrderValidator> validators;

    OrderValidationPipeline(List<OrderValidator> validators) {
        this.validators = validators;
    }

    void validate(OrderRequest request) {
        validators.forEach(validator -> validator.validate(request));
    }
}
~~~

In this case, validation sequence is part of the behavior, so the order annotation makes the intent clear.

### 11.2. Map when lookup by key is needed

If a service needs to find an exporter by format:

~~~java
public FileExporter findExporter(String format) {
    return exporters.stream()
            .filter(exporter -> exporter.format().equalsIgnoreCase(format))
            .findFirst()
            .orElseThrow(() ->
                    new IllegalArgumentException("Unsupported format"));
}
~~~

You can build a map once in the constructor:

~~~java
this.exportersByFormat = exporters.stream().collect(
        Collectors.toUnmodifiableMap(
                exporter -> exporter.format().toLowerCase(),
                Function.identity()
        )
);
~~~

This avoids scanning the list on every lookup. However, you must explicitly handle cases where two exporters declare the same format, since a map cannot hold two values for a single key this way.

### 11.3. Set when order is not needed

If you only need to know the set of supported capabilities, `Set` expresses that well:

~~~java
Set<String> supportedFormats = exporters.stream()
        .map(FileExporter::format)
        .collect(Collectors.toUnmodifiableSet());
~~~

Do not convert a `List` to a `Set` just to "deduplicate" if two beans share a class yet carry different state or configuration; determine identity and duplication semantics first.

## 12. Bean Scope and Lifecycle of Elements in a Collection

Collection injection does not change the scope of the injected beans. If a singleton consumer receives a `List` of singleton beans, the elements are generally the shared singleton instances from the context.

If a collection contains prototype beans, those prototype instances are typically created at the time Spring resolves the dependency for the consumer. A singleton holding that collection continues to hold the injected references; **Spring does not automatically create new prototypes on each consumer method call**.

Example:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class WorkUnit {
}
~~~

~~~java
@Service
public class WorkCoordinator {
    private final List<WorkUnit> workUnits;

    public WorkCoordinator(List<WorkUnit> workUnits) {
        this.workUnits = workUnits;
    }
}
~~~

Since `WorkCoordinator` is a singleton, the list is resolved when the coordinator is created. Prototype elements are instantiated then and do not automatically change per call.

If you need a new prototype instance on each invocation, inject **ObjectProvider<WorkUnit>** and call **getObject()** when needed:

~~~java
public class WorkCoordinator {
    private final ObjectProvider<WorkUnit> workUnitProvider;

    public WorkCoordinator(ObjectProvider<WorkUnit> workUnitProvider) {
        this.workUnitProvider = workUnitProvider;
    }

    public void execute() {
        WorkUnit unit = workUnitProvider.getObject();
        // Process the new unit.
    }
}
~~~

For request- or session-scoped beans, understand scoped proxies or appropriate providers. A collection injected into a singleton will not automatically give request-scoped elements per-request state unless scoping mechanisms are configured correctly.

## 13. Collection Injection and Bean Registration Conditions

The collection elements reflect the beans the container can resolve **in that context at the time the dependency is created**.

An implementation may be absent because:

- The class is outside component scan scope.
- Its bean configuration was not imported.
- Its profile is inactive.
- `@Conditional` or auto-configuration conditions were not satisfied.
- The dependency containing the implementation class is missing from the classpath.
- The bean definition was excluded or registered with an incompatible type.

Example:

~~~java
@Component
@Profile("production")
public class RealPaymentHandler implements PaymentHandler {
    // ...
}
~~~

~~~java
@Component
@Profile("test")
public class FakePaymentHandler implements PaymentHandler {
    // ...
}
~~~

When the `production` profile is active, the candidate set differs from when the `test` profile is active. Collection injection does not invent replacement implementations; it reflects the active bean configuration.

This makes it easy to assemble strategies per environment, and it also means tests must activate the appropriate profile when verifying production bean sets.

## 14. Verifying Collection Injection in Tests

A context test can verify that Spring injected the expected implementations.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class PaymentHandlerInjectionTest {

    @Autowired
    List<PaymentHandler> handlers;

    @Autowired
    Map<String, PaymentHandler> handlersByName;

    @Test
    void injectsAllPaymentHandlers() {
        assertThat(handlers).hasSize(3);
        assertThat(handlersByName)
                .containsKeys(
                        "cardPaymentHandler",
                        "walletPaymentHandler",
                        "bankTransferPaymentHandler"
                );
    }
}
~~~

This example applies when the application actually has three beans with those names and the test context uses matching component scanning. If additional `PaymentHandler` beans exist from another configuration, the expected count must reflect that configuration.

To verify ordering:

~~~java
assertThat(handlers)
        .extracting(PaymentHandler::method)
        .containsExactly("card", "wallet", "bank-transfer");
~~~

Only use **containsExactly** when implementations have explicitly defined order. When no ordering contract exists, assert membership with **contains** or set comparison so tests do not depend on accidental order.

### 14.1. Verifying qualifiers

A test can inject a qualified collection to confirm it receives only the intended subset:

~~~java
@Autowired
@Qualifier("online")
List<PaymentHandler> onlineHandlers;
~~~

Then assert the expected methods or bean names. This confirms qualifier metadata and context configuration work together.

### 14.2. Unit tests without a context do not test DI

If a test writes:

~~~java
PaymentDispatcher dispatcher =
        new PaymentDispatcher(List.of(fakeHandler));
~~~

the test verifies dispatcher logic using a `List` supplied by the test itself. It **does not verify which beans Spring discovered, whether qualifiers filtered properly, or whether `@Order` sorted the collection**.

Use Spring context tests to verify wiring. To verify business logic in isolation, constructor injection still makes unit tests lightweight using manually constructed collections.

## 15. Common Pitfalls

### 15.1. `NoSuchBeanDefinitionException` when injecting a collection

Usually caused by having zero candidates matching the type or qualifier. Check:

- Is the implementation registered as a bean?
- Does component scan cover its package?
- Are profiles or conditions excluding the bean?
- Do generic types match?
- Did the qualifier at the injection point filter out all candidates?

If having zero implementations is valid, consider `ObjectProvider` instead of a required collection dependency.

### 15.2. `NoUniqueBeanDefinitionException` when injecting a single bean

If a constructor accepts a single **PaymentHandler** while the context has three beans, Spring cannot choose one without a preferred candidate or matching qualifier. Change to **List<PaymentHandler>** if you truly need all of them; use `@Primary`/`@Qualifier` if you only need one.

### 15.3. Map does not have expected keys

Map collection injection uses **bean names** as keys. If a bean is declared as `@Component("card")`, the key is **card**, not the class name or the result of `method()`.

Check actual bean names via the context or Actuator rather than guessing.

### 15.4. List order changes unexpectedly

If `@Order`/`Ordered` has not been declared, do not rely on registration order. Define explicit ordering whenever behavior depends on it. If the collection is a `Set`, never treat iteration order as a contract.

### 15.5. Does `@Primary` drop the other elements?

No. `@Primary` resolves single-candidate selection for a single dependency; collection injection still collects all matching candidates. Use qualifiers to filter groups.

### 15.6. Prototype beans are not fresh on every call

When prototypes are injected into a singleton collection, instances are resolved when the singleton is created. Use `ObjectProvider` to obtain fresh instances when needed.

### 15.7. Two implementations share the same business code

If two handlers both return `"card"` for `method()`, finding the first element in a `List` can depend on order. Decide whether that is valid configuration or a duplicate registration error. You can build a `Map` registry keyed by `method()` and fail fast upon duplicate keys.

### 15.8. Collection includes unexpected beans from auto-configuration

A starter may register a default implementation. When a collection unexpectedly gains an extra element, inspect the bean name, definition source, and condition report. If the default bean is designed to back off, check `@ConditionalOnMissingBean` conditions; if needed, customize or exclude configuration using supported mechanisms.

## 16. When to Choose List, Set, Map, or ObjectProvider?

| Need | Suggested choice | Why |
|---|---|---|
| Execute all strategies in order | **List<T>** | Can be sorted with `@Order`/`Ordered`. |
| Hold a set of capabilities, order-independent | **Set<T>** | Represents an unordered set of elements. |
| Look up by bean name | **Map<String, T>** | Keys are bean names. |
| Receive only a qualified group of beans | **@Qualifier + List/Set/Map** | Filters candidates by metadata. |
| Single bean may be absent | **Optional<T>** or **ObjectProvider<T>** | Expresses an optional dependency. |
| Multiple beans may be absent, empty list needed | **ObjectProvider<T>.orderedStream()** | Queries on demand; can yield an empty stream. |
| Need fresh prototype instances each time | **ObjectProvider<T>** | Requests a bean at the moment of use. |
| Need a single implementation | **T + @Primary/@Qualifier** | Selects one candidate unambiguously. |

No collection type is best for every case. Pick the data type that accurately reflects how the consumer uses the set of beans.

## 17. Design Principles When Extending Systems with Multiple Beans

When building a module where new implementations may be added later:

1. **Define a stable interface** for the role consumers require.
2. **Register each implementation explicitly** via component scanning or `@Bean`.
3. **Inject an interface collection** instead of listing each implementation in the constructor.
4. **Use `@Order` when ordering matters**; never rely on accidental ordering.
5. **Use qualifiers for meaningful groups** such as online/offline or primary/backup.
6. **Use `Map<String, T>` when keys are bean names**, and build a dedicated registry when keys are business data.
7. **Define behavior when no candidates exist**, using `ObjectProvider` if an empty collection is valid.
8. **Watch scopes and mutable state**, especially when a singleton holds a collection of shared beans.
9. **Test wiring in a Spring context**, and unit test consumer logic with fake collections when appropriate.
10. **Avoid accidental duplicate bean registrations**, particularly when combining component scanning and `@Bean` declarations.

## 18. Common Misconceptions

**"Injecting `List<T>` only retrieves the bean marked `@Primary`."**  
No. Collection injection aims to gather all matching candidates; `@Primary` primarily resolves selection for single dependencies.

**"`Set<T>` automatically sorts by `@Order`."**  
Do not rely on `Set` iteration order. Use `List` when ordering is part of behavior.

**"`Map<String, T>` uses the bean's `method()` return value as the key."**  
No. Keys are bean names in the context. If you want business keys, build a registry yourself.

**"Adding a new implementation guarantees it will appear in the collection."**  
Only if the implementation is registered as a bean and satisfies the injection point's conditions, profiles, and qualifiers.

**"With zero candidates, Spring always injects an empty collection."**  
Do not assume that for required dependencies. If having no beans is valid, use an explicit optional mechanism like `ObjectProvider`.

**"`@Qualifier` only picks one bean."**  
Qualifiers can filter candidate sets in collection injection; they do not restrict results to a single element.

**"`@Order` controls bean initialization order."**  
No. It orders elements at sorted collection injection points; startup ordering is a separate lifecycle topic.

**"Prototype beans in a `List` are re-created on every service call."**  
No. A collection injected into a singleton holds the references resolved when the singleton was constructed. Use `ObjectProvider` if you need a fresh instance per use.

**"Injecting a collection means the collection itself is a bean."**  
Not necessarily. The collection is a dependency value synthesized by Spring from element beans. Having a `List`/`Set`/`Map` injected does not imply it has its own bean definition.

## Core Takeaways

Spring can inject multiple beans of the same type as **List<T>**, **Set<T>**, or **Map<String, T>**. **List** fits when iterating in a configured order; **Set** represents an unordered collection; **Map<String, T>** allows lookup by bean name. Qualifiers filter subsets, whereas `@Primary` primarily chooses a single candidate for a single dependency.

A collection only contains beans that are registered and match the context's types, qualifiers, profiles, and conditions. If having no implementations is valid, use `ObjectProvider` to query on demand and handle empty collections explicitly. Once you understand how Spring resolves collections, you can build extensible plugin/strategy architectures without coupling consumers to concrete implementations.
