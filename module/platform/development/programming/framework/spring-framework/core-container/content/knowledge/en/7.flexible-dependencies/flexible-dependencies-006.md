# Spring ObjectProvider: Distinguishing `getObject()`, `getIfAvailable()`, and `getIfUnique()`

## 1. The Problem: When a Dependency May Be Missing or Have Multiple Beans

When a class needs a service managed by the Spring IoC Container, the standard approach is constructor injection:

```java
// Illustrative: PaymentGateway must have exactly one matching bean.
PaymentService(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

This works well for **required** dependencies: if a bean is missing or multiple unresolved candidates exist, an error surfaces while constructing the object. However, some features are optional, depend on configuration, or require choosing a bean at usage time. In those cases, instead of requesting `PaymentGateway` directly, we can inject:

```java
// Illustrative: constructor of a Spring bean.
PaymentService(ObjectProvider<PaymentGateway> gatewayProvider) {
    this.gatewayProvider = gatewayProvider;
}
```

`ObjectProvider<T>` belongs to `org.springframework.beans.factory` and is a specialized variant of `ObjectFactory<T>`. It allows **on-demand bean retrieval** and controls behavior when no bean exists or when multiple beans of the same type exist. The provider is tied to the Spring `BeanFactory`; each time a provider method is called, target bean resolution can be evaluated against the factory's current state.

Three core methods:

- `getObject()`: **requires resolving one bean**; missing beans or ambiguous multiple beans throw an error.
- `getIfAvailable()`: **allows a missing bean** and returns `null` if absent; however, it **does not ignore ambiguous multiple-bean errors**.
- `getIfUnique()`: **returns a bean only when there is a single winning candidate**; returns `null` when no bean exists or no unique choice can be made.

**Most common pitfall:** The name `getIfAvailable` does not mean "if any bean exists, return an arbitrary one"; likewise, `getIfUnique` does not mean "there must be literally one bean definition in the entire container." Both still follow Spring's candidate selection rules, where an eligible `@Primary` bean can be chosen as the unique result among multiple same-type beans.

## 2. Behavior Matrix to Remember

Suppose `ObjectProvider<PaymentGateway> provider` requests a bean of type `PaymentGateway` with no qualifier narrowing the choice.

| Candidate State | `getObject()` | `getIfAvailable()` | `getIfUnique()` |
| --- | --- | --- | --- |
| No matching bean | Throws `NoSuchBeanDefinitionException` | `null` | `null` |
| Exactly one matching bean | Returns that bean | Returns that bean | Returns that bean |
| Two beans, no winning candidate | Throws `NoUniqueBeanDefinitionException` | Throws `NoUniqueBeanDefinitionException` | `null` |
| Two beans, exactly one `@Primary` bean | Returns primary bean | Returns primary bean | Returns primary bean |
| Multiple beans, qualifier leaves one candidate | Returns matching bean | Returns matching bean | Returns matching bean |

`NoUniqueBeanDefinitionException` is a subclass of `NoSuchBeanDefinitionException` in Spring's exception hierarchy; when distinguishing the two cases, put `catch (NoUniqueBeanDefinitionException)` **before** `catch (NoSuchBeanDefinitionException)`.

This table describes outcomes when bean instantiation itself succeeds. If the factory invokes a constructor/factory method and a bean initialization failure occurs, provider methods can still throw the corresponding `BeansException`. `getIfAvailable()` and `getIfUnique()` are **not** mechanisms for swallowing bean creation failures.

### "Unique" Means Resolving to One Winning Candidate

Spring uses the container's selection policy to resolve uniqueness. Beyond literally having a single bean, signals such as:

- `@Primary`: an explicitly marked primary candidate.
- `@Fallback` since Spring Framework 6.2: when one non-fallback bean exists among fallback candidates, the regular bean can be selected.
- Default-candidate metadata and other container candidate resolution rules.

can determine a single winner. Therefore, **do not manually check `provider.stream().count() == 1` and assume it always behaves identically to `getIfUnique()`**: counting all beans does not replicate the full singular-dependency resolution policy.

## 3. `getObject()`: Retrieving a Required Bean

Syntax:

```java
PaymentGateway gateway = provider.getObject();
```

Behavior:

1. Spring searches for beans matching the generic type `PaymentGateway`, qualifiers, and relevant candidate conditions.
2. If one candidate matches, or one winning candidate emerges after resolution, the provider returns that object.
3. If no candidate exists, it throws `NoSuchBeanDefinitionException`.
4. If multiple candidates remain without a unique choice, it throws `NoUniqueBeanDefinitionException`.
5. If bean creation fails, the initialization error still propagates to the caller.

`getObject()` fits when **at the moment the feature executes, the dependency is mandatory**. For example, official payment processing should only run if a gateway is properly configured; failing is the right policy rather than silently running an unauthorized default.

You can catch exceptions to add domain context, while distinguishing misconfiguration from programming bugs:

```java
// Illustrative inside a method with a provider variable of type ObjectProvider<PaymentGateway>.
try {
    PaymentGateway gateway = provider.getObject();
    gateway.pay();
} catch (NoUniqueBeanDefinitionException ex) {
    throw new IllegalStateException("Multiple unresolved payment gateways", ex);
} catch (NoSuchBeanDefinitionException ex) {
    throw new IllegalStateException("Payment gateway is not configured", ex);
}
```

This snippet illustrates the API and error policy only; the `pay()` method belongs to a hypothetical domain interface implemented in a real project. Avoid catching generic `Exception` and returning a dummy value, as that hides system configuration errors.

### `getObject(Object... args)`

Beyond the no-arg overload, `getObject(Object... args)` can pass **bean creation arguments** to the factory in appropriate cases, particularly when retrieving prototype-scoped beans with parameterized constructors or factory methods. This is **not** an API for passing qualifiers, not a way to select a bean by name, and should not be used to alter initialization state of an existing singleton. If using this overload, verify the specific bean creation mechanism and scope.

## 4. `getIfAvailable()`: Allowing an Absent Dependency

Syntax:

```java
PaymentGateway gateway = provider.getIfAvailable();
if (gateway != null) {
    gateway.pay();
}
```

`getIfAvailable()` returns `null` when **no bean satisfies the criteria**. Unlike `getObject()`, a missing bean is treated as a valid outcome. However, if two equal gateways exist and no winning candidate can be determined, the call **still throws `NoUniqueBeanDefinitionException`**.

A fitting scenario is an optional email service:

```java
// Illustrative snippet using an application-defined NotificationSender.
final class OrderService {
    private final ObjectProvider<NotificationSender> senders;

    OrderService(ObjectProvider<NotificationSender> senders) {
        this.senders = senders;
    }

    void completed(Order order) {
        senders.ifAvailable(sender -> sender.send(order));
    }
}
```

This snippet demonstrates usage and is not a standalone runnable Java file: `NotificationSender` and `Order` are undefined domain types. `ifAvailable(Consumer<T>)` invokes the callback only when a bean can be resolved. If no bean exists, the callback is skipped. If multiple beans are ambiguous, `NoUniqueBeanDefinitionException` can still occur.

### Providing a Default with `Supplier`

`getIfAvailable(Supplier<T> defaultSupplier)` creates a substitute object when **no bean exists**:

```java
PaymentGateway selected = provider.getIfAvailable(
        () -> new OfflinePaymentGateway()
);
```

This is an illustrative snippet with application types; it compiles only after defining `PaymentGateway` and `OfflinePaymentGateway`.

Points to remember:

- The supplier is typically **invoked only when no matching bean exists**. Avoid side effects inside the supplier.
- The supplier **cannot be used to mask ambiguity errors**. Two non-primary gateways still cause `getIfAvailable(supplier)` to throw `NoUniqueBeanDefinitionException`.
- Objects constructed directly by the supplier with `new` are **not automatically Spring-managed beans**: they do not receive dependency injection, lifecycle callbacks, AOP proxies, or container destruction callbacks.
- If the fallback must be Spring-managed, register it as a conditionally enabled bean or design an explicit selection mechanism.

For an "optional feature" policy, `getIfAvailable()` or `ifAvailable(...)` usually expresses intent better than catching and ignoring exceptions from `getObject()`.

## 5. `getIfUnique()`: Skipping When No Clear Choice Exists

Syntax:

```java
PaymentGateway gateway = provider.getIfUnique();
if (gateway == null) {
    // Either no candidates exist or multiple equal candidates remain.
}
```

The crucial difference from `getIfAvailable()` is that **`getIfUnique()` returns `null` even when multiple beans exist if a single unique bean cannot be chosen**. It is therefore suited when a behavior should activate only if the dependency can be safely inferred from configuration and skipping the feature is acceptable.

Limitation: `null` **does not explain why**. If domain logic needs to report missing configuration differently from ambiguous configuration, `getIfUnique()` lacks the information to distinguish them; prefer `getObject()`/`getIfAvailable()` and handle the respective exceptions.

With a default value:

```java
PaymentGateway gateway = provider.getIfUnique(
        () -> new OfflinePaymentGateway()
);
```

`getIfUnique(Supplier<T>)` uses the fallback **when no candidate exists or when no winner can be determined**. That is the exact difference from `getIfAvailable(Supplier<T>)`.

Additionally, `ifUnique(Consumer<T>)` runs the callback when a single unique bean is selected, and skips it when no bean exists or multiple beans are ambiguous. Genuine bean initialization errors can still be thrown.

### When Is This "Silently Wrong"?

Do not use `getIfUnique()` for a mandatory flow requiring one configured gateway: if two equal gateways are accidentally registered, `null` could trick you into thinking the feature is legitimately disabled. For required dependencies, `getObject()` surfaces misconfiguration immediately upon invocation.

## 6. Complete Java 17+ Example: Four Bean Resolution Scenarios

The following example creates **four separate `ApplicationContext` instances** to verify the behavior matrix: no gateway, one gateway, two non-primary gateways, and two gateways with one primary. Each context uses standard `@Configuration` and `@Bean` without Spring Boot.

### 6.1. Structure

```text
object-provider-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── ObjectProviderDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'object-provider-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'ObjectProviderDemo'
}
```

Uses Spring Framework `6.2.19` (available on Maven Central) and JDK 17 or higher. Gradle must be a version compatible with the chosen JDK.

### 6.2. Source `src/main/java/ObjectProviderDemo.java`

```java
import java.util.function.Supplier;

import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

public class ObjectProviderDemo {

    interface Gateway {
        String name();
    }

    record NamedGateway(String name) implements Gateway {
    }

    @Configuration(proxyBeanMethods = false)
    static class EmptyConfig {
        // No Gateway bean.
    }

    @Configuration(proxyBeanMethods = false)
    static class SingleConfig {
        @Bean
        Gateway card() {
            return new NamedGateway("card");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AmbiguousConfig {
        @Bean
        Gateway card() {
            return new NamedGateway("card");
        }

        @Bean
        Gateway bank() {
            return new NamedGateway("bank");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrimaryConfig {
        @Bean
        @Primary
        Gateway card() {
            return new NamedGateway("card");
        }

        @Bean
        Gateway bank() {
            return new NamedGateway("bank");
        }
    }

    private static String describe(Supplier<Gateway> action) {
        try {
            Gateway gateway = action.get();
            return gateway == null ? "null" : gateway.name();
        } catch (NoUniqueBeanDefinitionException ex) {
            return "NoUniqueBeanDefinitionException";
        } catch (NoSuchBeanDefinitionException ex) {
            return "NoSuchBeanDefinitionException";
        }
    }

    private static void runCase(String label, Class<?> configuration) {
        try (var context =
                     new AnnotationConfigApplicationContext(configuration)) {
            ObjectProvider<Gateway> provider =
                    context.getBeanProvider(Gateway.class);

            System.out.println("== " + label + " ==");
            System.out.println("getObject: " +
                    describe(provider::getObject));
            System.out.println("getIfAvailable: " +
                    describe(provider::getIfAvailable));
            System.out.println("getIfUnique: " +
                    describe(provider::getIfUnique));
            System.out.println("available/default: " +
                    describe(() -> provider.getIfAvailable(
                            () -> new NamedGateway("fallback"))));
            System.out.println("unique/default: " +
                    describe(() -> provider.getIfUnique(
                            () -> new NamedGateway("fallback"))));
        }
    }

    public static void main(String[] args) {
        runCase("EMPTY", EmptyConfig.class);
        runCase("SINGLE", SingleConfig.class);
        runCase("AMBIGUOUS", AmbiguousConfig.class);
        runCase("PRIMARY", PrimaryConfig.class);
    }
}
```

### 6.3. Running the Program

In the project directory:

```bash
gradle run --quiet
```

If using the Gradle Wrapper, run `./gradlew run --quiet` on macOS/Linux or `.\gradlew.bat run --quiet` on Windows PowerShell.

Lines printed by the program's `System.out.println` calls:

```text
== EMPTY ==
getObject: NoSuchBeanDefinitionException
getIfAvailable: null
getIfUnique: null
available/default: fallback
unique/default: fallback
== SINGLE ==
getObject: card
getIfAvailable: card
getIfUnique: card
available/default: card
unique/default: card
== AMBIGUOUS ==
getObject: NoUniqueBeanDefinitionException
getIfAvailable: NoUniqueBeanDefinitionException
getIfUnique: null
available/default: NoUniqueBeanDefinitionException
unique/default: fallback
== PRIMARY ==
getObject: card
getIfAvailable: card
getIfUnique: card
available/default: card
unique/default: card
```

### 6.4. Analyzing Each Configuration

**EMPTY:** No `Gateway` bean exists. `getObject()` throws an error; the two `getIf...` methods without suppliers return `null`. Both supplier overloads return the `NamedGateway("fallback")` created by our code.

**SINGLE:** Only the `card` bean exists; every method returns that bean, and the fallback supplier is never executed.

**AMBIGUOUS:** Both `card` and `bank` share the same type with no `@Primary` or unique resolution hint. `getObject()` and both `getIfAvailable` variants throw `NoUniqueBeanDefinitionException`. `getIfUnique()` returns `null`; its supplier variant returns `fallback`.

**PRIMARY:** Two beans still exist, but `card` is the sole primary. All three methods return `card` without ambiguity. This proves `getIfUnique()` does not require the container to hold literally a single bean definition.

The error strings printed here appear because the `describe` helper **catches and prints the exception name**. Without the helper, calling `getObject()` directly in the EMPTY/AMBIGUOUS cases would raise an exception instead of printing its name. The example is structured to exercise all cases in one run.

## 7. Injecting `ObjectProvider` into Application Beans

### 7.1. Constructor Injection

`ObjectProvider<T>` is commonly passed via constructor, just like other dependencies:

```java
// Illustrative code using the application's Gateway type.
final class CheckoutService {
    private final ObjectProvider<Gateway> gateways;

    CheckoutService(ObjectProvider<Gateway> gateways) {
        this.gateways = gateways;
    }

    String checkout() {
        Gateway selected = gateways.getObject();
        return "Using " + selected.name();
    }
}
```

This is an **illustrative** snippet that will not compile standalone without declaring `Gateway` and registering `CheckoutService` as a bean. The constructor simply stores the provider; the target bean is resolved when `checkout()` runs. If business logic always needs a `Gateway` and there is no reason to defer resolution, injecting `Gateway` directly is simpler and validates configuration at service startup.

### 7.2. Combining with `@Qualifier`

When multiple gateways exist, a qualifier narrows the candidate pool **before** the three methods resolve:

```java
// Illustrative snippet: bean declaration.
@Bean
@Qualifier("external")
Gateway stripeGateway() {
    return new NamedGateway("stripe");
}

// Illustrative snippet: constructor parameter of another bean.
CheckoutService(
        @Qualifier("external") ObjectProvider<Gateway> externalGateway) {
    this.gateways = externalGateway;
}
```

If only one compatible gateway carries the `external` qualifier, `externalGateway.getObject()`, `getIfAvailable()`, and `getIfUnique()` can all select it. If two beans share that qualifier with no clear winner, ambiguity still happens as shown in the table.

**Note:** Do not use `ObjectProvider<Gateway>` and expect Spring to always pick a bean by parameter name. When the domain role is explicit, use `@Qualifier` or intentional bean names/metadata.

### 7.3. Obtaining a Provider from `ApplicationContext`/`BeanFactory`

The example in section 6 calls:

```java
ObjectProvider<Gateway> provider =
        context.getBeanProvider(Gateway.class);
```

This is useful in container orchestration code, framework integration, or wherever `ApplicationContext` is already available. In business services, constructor injection of `ObjectProvider<T>` communicates dependencies more clearly and simplifies unit testing.

For complex generics (such as `Repository<Customer>`), `getBeanProvider(Class<?>)` only represents the raw class. Use the overloads accepting `ResolvableType` or `ParameterizedTypeReference` when generic information must be preserved. Do not pass `List<Gateway>` to `getBeanProvider(...)` expecting Spring to aggregate all Gateways; to iterate multiple beans, obtain a provider for the **element type** and call `stream()`/`orderedStream()`.

## 8. Providers Resolve at Usage Time: Lazy, Scope, and Caching

An important property is **resolution timing**. Injecting `ObjectProvider<Gateway>` avoids forcing the caller to pick a `Gateway` in the constructor. However, this **does not automatically make all `Gateway` singletons lazily initialized**.

In a default Spring container, **non-lazy singletons** can be eagerly instantiated during context `refresh()`. To defer creating the target bean until it is actually needed, combine it with an appropriate mechanism such as `@Lazy` on the bean definition:

```java
@Bean
@Lazy
Gateway expensiveGateway() {
    return new ExpensiveGateway();
}
```

This is an illustrative snippet requiring `ExpensiveGateway` and the `@Lazy` import in a real project. If another component directly depends on that bean, Spring may still initialize it; lazy is a lifecycle and actual-demand property, not a promise that the bean is never created.

### Does Every Call Create a New Object?

**Not necessarily.** The provider resolves beans through the Spring container; **scope** determines whether an instance is reused or newly created:

| Target Bean Scope | Two `provider.getObject()` Calls |
| --- | --- |
| `singleton` (default) | Typically the same Spring-managed instance |
| `prototype` | Typically creates a new instance on each resolution |
| Request/session scope | Depends on the currently active scope and configured proxy |

If an application must create a fresh processor object per request, configure the proper scope or an explicit factory. **`ObjectProvider` does not mean prototype**.

### Does a Provider "See" Bean Registry Changes?

A provider obtained from a `BeanFactory` operates against factory state. In principle, subsequent calls can resolve against current container state, including supported bean registration changes. However, applications should not treat dynamically adding/removing beans at runtime after startup as an arbitrary production mechanism: many bean lifecycle and extension-point structures assume a stable container configuration. Use providers primarily for optionality, lazy lookup, and criteria-based selection.

## 9. Which API Fits Which Business Policy?

| Need | Recommendation | Reason |
| --- | --- | --- |
| A valid bean is mandatory at usage time | `getObject()` | Missing and ambiguous cases are caught as configuration errors |
| Optional feature; missing is fine, multiple is an error | `getIfAvailable()` | Returns `null` when missing, still reports ambiguity |
| Need a substitute object when no bean is registered | `getIfAvailable(supplier)` | Fallback runs only when no bean is found |
| Use bean only if one winner resolves; skip otherwise | `getIfUnique()` | Returns `null` when missing **or** ambiguous |
| Skip bean on missing/ambiguous and supply another object | `getIfUnique(supplier)` | Fallback applies to both cases |
| Run side effect when a valid candidate exists | `ifAvailable(consumer)` / `ifUnique(consumer)` | No manual `null` check needed |
| Iterate all beans of the same type | `stream()` / `orderedStream()` | Avoids forcing one winning bean in single selection |
| Mandatory dependency at service creation | Direct `T` injection | Concise and catches misconfiguration at bean creation |
| Optional dependency resolved once at constructor | `Optional<T>` may fit | Though it lacks flexible policy when multiple candidates are ambiguous |

Distinguish "absent", "non-unique", and "bean creation failure." Do not apply the same fallback to all three if they carry different business meanings.

### How Does `Optional<T>` Differ from `ObjectProvider<T>`?

Constructor injection with `Optional<Gateway>` expresses "Gateway might not exist" at bean creation time. When multiple ambiguous Gateways exist, that remains a bean resolution failure. `ObjectProvider<Gateway>` provides a handle for **deferred querying**, callable multiple times and supporting `getObject`, `getIfAvailable`, or `getIfUnique` policies as needed.

If an object only needs to read an optional dependency once, `Optional<T>` can make intent clearer. If it needs lazy resolution or counting/iterating a bean set, `ObjectProvider<T>` is more appropriate.

## 10. Common Errors and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `getObject()` throws `NoSuchBeanDefinitionException` | No bean matches type/qualifier | Check `@Component`/`@Bean`, component scan, profiles, conditional configuration |
| `getIfAvailable()` still throws despite "Available" in the name | Multiple beans exist with no winner | Add `@Qualifier`/`@Primary` per design, or use `getIfUnique()` if skipping ambiguity is intended |
| `getIfUnique()` returns `null` despite multiple beans | No unique winning candidate could be chosen | This is by design; decide explicitly whether to fall back or error |
| `getIfUnique()` returns a bean even though two same-type beans exist | One bean is prioritized by Spring, e.g. `@Primary` | Inspect selection policy rather than counting raw beans |
| `getIfAvailable(supplier)` skips supplier when two beans are ambiguous | Supplier runs only when no bean exists | Use `getIfUnique(supplier)` if policy allows fallback on non-uniqueness |
| `NullPointerException` after `getIfAvailable()` | Missing `null` check | Use `if (bean != null)`, `ifAvailable(...)`, or the supplier overload |
| Fallback object lacks AOP/injection | Created directly with `new` inside supplier | Register the fallback with the container or supply dependencies manually |
| Provider does not reduce startup time | Target singleton is still eager | Check `@Lazy` and dependency graph; injecting a provider alone does not enforce lazy-init |
| Two `getObject()` calls return same instance when a fresh one was expected | Target bean is singleton-scoped | Switch to prototype where appropriate or use an explicit factory |
| `NoUniqueBeanDefinitionException` caught as "missing bean" | It is a subtype of `NoSuchBeanDefinitionException` | Catch the subtype first, then the superclass |
| Mistakenly caching `getIfUnique() == null` as "not configured" | `null` can mean missing **or** ambiguous | Cache only if the application truly does not need to distinguish the two |
| `getBeanProvider(List.class)` fails to find Gateway beans | Searches for a bean of type List, rather than aggregating Gateways | Use `getBeanProvider(Gateway.class).stream()`/`orderedStream()` |

## 11. Self-Check Exercises

**Exercise 1 — Default values.** In `AmbiguousConfig` from section 6, predict the results of these two calls:

```java
provider.getIfAvailable(() -> new NamedGateway("fallback"));
provider.getIfUnique(() -> new NamedGateway("fallback"));
```

Answer: the first call throws `NoUniqueBeanDefinitionException`; the second call returns `fallback`. "Having beans" is not synonymous with "having a single selectable bean."

**Exercise 2 — Selecting a primary candidate.** Add `@Primary` to `bank()` in `AmbiguousConfig`. What will `getObject()`, `getIfAvailable()`, and `getIfUnique()` all return? Answer: `bank`, assuming no other condition invalidates that bean.

**Exercise 3 — Two primaries.** If both `card()` and `bank()` are marked `@Primary`, can `getObject()` and `getIfAvailable()` resolve using primary? No: primary is no longer unique, so `NoUniqueBeanDefinitionException` may occur. `getIfUnique()` typically returns `null` when no winning candidate can be resolved (independent bean creation errors may still be thrown).

**Exercise 4 — Optional feature.** An invoice rendering module sends email only when an `InvoiceMailer` bean exists; a missing mailer is normal, whereas two mailers of the same type represent a deployment bug. Which should you choose? `getIfAvailable()` or `ifAvailable(...)`: allows a missing bean while still catching ambiguity.

**Exercise 5 — Ambiguous configuration.** A plugin should run only when the system has a clearly determined `Plugin` choice; if absent or unresolvable, skip it safely. Which should you choose? `getIfUnique()`/`ifUnique(...)`, provided skipping ambiguity is genuinely acceptable.

**Exercise 6 — Lifecycle.** Do two calls to `provider.getObject()` always create two new instances? No; it depends on the bean's scope. For a standard singleton, both calls return the same instance.

**Exercise 7 — What gets hidden?** A developer replaces every `getObject()` call with `getIfUnique()` followed by a `null` check. What is the risk? An unresolved two-bean misconfiguration can be misread as "optional feature not configured," leaving setup bugs unreported.

## 12. Conclusion and Reference Sources

- `getObject()`: **must resolve a single winning bean**, otherwise throws an error.
- `getIfAvailable()`: **missing bean returns null**, yet **ambiguous multiple beans still throw**.
- `getIfUnique()`: **missing or ambiguous returns null**, returning a bean only when Spring resolves a unique choice.
- The two `Supplier<T>` overloads have **different** fallback policies and are not interchangeable.
- `@Primary`/`@Qualifier` and candidate resolution rules affect results; uniqueness means **unique after resolution**, not simply counting beans.
- `ObjectProvider` governs *lookup timing and policy*; scope and lazy initialization govern instance lifecycle.

Official documentation:

- [Spring Framework 6.2 — `ObjectProvider<T>` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectProvider.html).
- [Spring Reference — Annotation-based container configuration and autowiring](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html).
- [Spring Reference — Primary and Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html).
- [Spring Reference — Fine-tuning autowiring with qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html).
- [Spring Framework 6.2 — `BeanFactory` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/BeanFactory.html).
