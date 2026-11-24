# On-Demand Lookup with ObjectFactory and ObjectProvider in Spring Core Container

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain **on-demand lookup**: injecting a lookup handle and requesting the target bean only when it is actually needed.
- Distinguish `ObjectFactory<T>` and `ObjectProvider<T>`, choosing the right API when a dependency is required, optional, or has multiple implementations.
- Predict how `singleton`, `prototype`, and request scopes affect the result of `getObject()`.
- Write Spring code using constructor injection while handling missing beans, multiple beans, and bean ordering.
- Avoid confusing on-demand lookup with lazy initialization by default, creating a new instance every time, or automatic lifecycle management.

**Context:** The Spring IoC Container is responsible for creating beans, resolving dependencies, and managing scopes. When a singleton needs a fresh prototype object for each operation, or a plugin exists only in certain configurations, injecting a target bean directly at startup often cannot express that requirement.

## 2. The Problem: Direct Bean Injection vs. On-Demand Lookup

Direct injection style:

```java
public class JobService {
    private final JobContext context;

    public JobService(JobContext context) {
        this.context = context;
    }

    public void runJob() {
        context.execute();
    }
}
```

This is a structural example assuming `JobContext` has an `execute()` method. `JobService` holds a `JobContext` reference resolved when the service is created. If `JobService` is a singleton while `JobContext` is a prototype, that reference **does not automatically turn into** a new prototype on each `runJob()` call.

Instead:

```java
import org.springframework.beans.factory.ObjectProvider;

public class JobService {
    private final ObjectProvider<JobContext> contexts;

    public JobService(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    public void runJob() {
        JobContext current = contexts.getObject();
        current.execute();
    }
}
```

Spring injects a provider capable of looking up `JobContext`. Every call to `getObject()` asks the container to resolve the bean **at invocation time**, following active scope, qualifier, and candidate rules. For a prototype bean, each call can yield a new object; a singleton bean still typically returns the same object. Both snippets above only illustrate injection style and are not standalone runnable programs.

### Mechanism Sequence

1. Spring creates `JobService` and injects `ObjectProvider<JobContext>` (or `ObjectFactory<JobContext>`).
2. The service stores the lookup handle, not necessarily a `JobContext` bean instance.
3. When handling a job, the service calls `getObject()` or another method on the provider.
4. The container selects a valid candidate, resolves its scope, and supplies the bean; missing-bean, non-uniqueness, or initialization errors may surface **at lookup time**.

**Important distinction:** A provider defers *resolving the dependency through the provider*, but does not guarantee that all candidate singletons remain uninitialized. Non-lazy singletons may already have been created by Spring during context startup.

## 3. How Are the Two Interfaces Related?

Both belong to the `org.springframework.beans.factory` package:

```java
@FunctionalInterface
public interface ObjectFactory<T> {
    T getObject();
}

// Type relationship; other methods omitted to focus on the main idea.
public interface ObjectProvider<T> extends ObjectFactory<T> {
    // getIfAvailable(), getIfUnique(), stream(), orderedStream(), ...
}
```

This is an outline of the interface relationship, **not replacement code for Spring sources**. `ObjectFactory<T>` is a minimal contract with a single `getObject()` operation. `ObjectProvider<T>` extends that interface with optional lookup, unique-only lookup, passing bean creation arguments, and iterating over multiple candidates. Therefore, an `ObjectProvider<T>` can also be used anywhere an `ObjectFactory<T>` is accepted.

| Requirement | `ObjectFactory<T>` | `ObjectProvider<T>` |
| --- | --- | --- |
| Obtain a bean when called | `getObject()` | `getObject()` |
| Return `null` or fallback if bean is missing | No dedicated API | `getIfAvailable()`, `getIfAvailable(Supplier)` |
| Skip if no unique candidate exists | No dedicated API | `getIfUnique()`, `getIfUnique(Supplier)` |
| Act only if a bean / unique bean exists | No dedicated API | `ifAvailable(Consumer)`, `ifUnique(Consumer)` |
| Retrieve multiple beans of the same type | No dedicated API | `stream()`, `orderedStream()`, `iterator()` |
| Pass bean creation arguments at call time | Not directly supported | `getObject(Object... args)` |

In typical Spring applications, **prefer `ObjectProvider<T>` when you need optionality, multiple candidates, ordering, or fallbacks**; `ObjectFactory<T>` suffices when only a required bean getter is needed.

## 4. Choosing an API Based on Dependency Contract

`ObjectFactory<T>` only has `getObject()`: when called, it must resolve a matching bean; missing beans or unresolved multiple candidates are errors. `ObjectProvider<T>` expands choices to fit the consumer's exact contract:

| Need at Call Time | API | When No Bean Exists | When Multiple Candidates Remain Ambiguous |
| --- | --- | --- | --- |
| Must obtain one bean | `getObject()` | Throws missing-bean error | Throws non-unique error |
| Missing bean is valid | `getIfAvailable()` / `ifAvailable(...)` | Returns `null` / skips callback | Can still throw error |
| Act only if a single bean can be chosen | `getIfUnique()` / `ifUnique(...)` | Returns `null` / skips callback | Returns `null` / skips callback |
| Run all matching plugins | `stream()` / `orderedStream()` | Empty stream | Iterates multiple beans without forcing one |

`@Qualifier`, `@Primary`, and bean metadata still participate in resolution: if multiple beans exist and one valid primary bean is marked, a single-bean lookup can still succeed. Overloads accepting `Supplier<T>` create the fallback only under each API's missing/unselected condition; objects manually instantiated inside a supplier are not automatically Spring-managed. None of these methods swallow bean initialization failures. The next lesson analyzes each method individually across four bean configurations and exact outputs; in this lesson, the core takeaway is that **`ObjectFactory` is minimal, while `ObjectProvider` lets the consumer choose the lookup policy**.

## 5. Complete Runnable Example with Spring Framework and Java 17+

The example uses **Spring Framework 6.2.19** to pin a concrete dependency version, without Spring Boot. We will observe a prototype bean created upon invocation, an absent optional plugin, and multiple beans ordered by `@Order`.

Create three files:

```text
provider-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/Demo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'provider-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'Demo'
}
```

**`src/main/java/Demo.java`**

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

import org.springframework.beans.factory.ObjectFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;
import org.springframework.core.annotation.Order;

public class Demo {
    interface RequestToken {
        int number();
    }

    static final class Token implements RequestToken {
        private final int number;

        Token(int number) {
            this.number = number;
        }

        @Override
        public int number() {
            return number;
        }
    }

    interface OptionalNotifier {
        void notifyUser(String message);
    }

    interface Formatter {
        String name();
    }

    static final class ConsumerService {
        private final ObjectFactory<RequestToken> tokenFactory;
        private final ObjectProvider<RequestToken> tokenProvider;
        private final ObjectProvider<OptionalNotifier> notifierProvider;
        private final ObjectProvider<Formatter> formatterProvider;

        ConsumerService(
                ObjectFactory<RequestToken> tokenFactory,
                ObjectProvider<RequestToken> tokenProvider,
                ObjectProvider<OptionalNotifier> notifierProvider,
                ObjectProvider<Formatter> formatterProvider) {
            this.tokenFactory = tokenFactory;
            this.tokenProvider = tokenProvider;
            this.notifierProvider = notifierProvider;
            this.formatterProvider = formatterProvider;
        }

        void demonstrate() {
            System.out.println("before-lookup");

            RequestToken first = tokenFactory.getObject();
            RequestToken second = tokenProvider.getObject();

            System.out.println("different=" + (first != second));
            System.out.println("numbers=" + first.number() + "," + second.number());
            System.out.println("notifier=" +
                    (notifierProvider.getIfAvailable() == null ? "absent" : "present"));
            System.out.println("unique-formatter=" +
                    (formatterProvider.getIfUnique() == null ? "none" : "one"));
            System.out.println("formatters=" + formatterProvider.orderedStream()
                    .map(Formatter::name)
                    .collect(Collectors.joining(",")));
        }
    }

    @Configuration
    public static class Config {
        private final AtomicInteger sequence = new AtomicInteger();

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        RequestToken requestToken() {
            int next = sequence.incrementAndGet();
            System.out.println("create-token-" + next);
            return new Token(next);
        }

        @Bean
        @Order(10)
        Formatter plainFormatter() {
            return () -> "plain";
        }

        @Bean
        @Order(1)
        Formatter jsonFormatter() {
            return () -> "json";
        }

        @Bean
        ConsumerService consumerService(
                ObjectFactory<RequestToken> tokenFactory,
                ObjectProvider<RequestToken> tokenProvider,
                ObjectProvider<OptionalNotifier> notifierProvider,
                ObjectProvider<Formatter> formatterProvider) {
            return new ConsumerService(
                    tokenFactory, tokenProvider, notifierProvider, formatterProvider);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            System.out.println("context-ready");
            context.getBean(ConsumerService.class).demonstrate();
        }
    }
}
```

**Run** in the `provider-demo` directory with an available Gradle installation and toolchain-compatible JDK:

```bash
gradle run --quiet
```

Or use `./gradlew run --quiet` when the project includes a Gradle Wrapper (on Windows, use `gradlew.bat run --quiet`). The Java program is compiled via Gradle's `compileJava` task; you cannot run `javac Demo.java` standalone without providing the Spring JARs on the classpath.

**Lines printed by the program (stdout):**

```text
context-ready
before-lookup
create-token-1
create-token-2
different=true
numbers=1,2
notifier=absent
unique-formatter=none
formatters=json,plain
```

**Explanation of each observation:**

1. `requestToken()` produces a **prototype**. The context starts up without creating a token yet, because nothing requested the target bean before `demonstrate()`.
2. `tokenFactory.getObject()` and `tokenProvider.getObject()` each trigger a prototype creation, so `different=true`; the counter increments from 1 to 2.
3. There is no `@Bean OptionalNotifier`. Injecting `ObjectProvider<OptionalNotifier>` still succeeds, and `getIfAvailable()` returns `null`.
4. There are two `Formatter` beans with no unique candidate selected, so `getIfUnique()` returns `null`.
5. `orderedStream()` iterates both formatters in the order Spring determines from `@Order(1)` then `@Order(10)`: `json,plain`. Regular `stream()` does not guarantee this ordering.

This demo is sufficient to practice both interfaces and clearly observe scope effects. Environment/Gradle configuration logs, if any, are not part of the stdout lines printed by `Demo` itself.

## 6. Scope Defines What "Each Call" Means

| Target Bean Scope | Two `provider.getObject()` Calls Under Same Conditions | Notes |
| --- | --- | --- |
| `singleton` (default) | Typically **same instance** within one container | Provider does not turn a singleton into a prototype; non-lazy singletons may already be initialized at refresh. |
| `prototype` | **Two distinct instances** across normal resolutions | Each lookup creates a new instance; the container does not manage full prototype destruction after creation. |
| `request` | Typically same instance within the **same HTTP request**; different requests get different instances | Only look up while request scope is active, unless an appropriate proxy mechanism is configured. |
| `session` | Typically same instance within a session; different sessions get different instances | Provider does not extend or change the bean's scope. |

For example, a singleton calling `provider.getObject()` twice can receive the same singleton. Adding `@Scope("prototype")` on the **target bean** is what changes instantiation rules; the consumer's scope does not need to change.

For prototypes holding resources that require closing (sockets, files, clients...), design an appropriate lifecycle-cleanup mechanism; do not assume `getObject()` registers destruction callbacks for all prototypes. When using a request-scoped dependency inside a singleton, a provider retrieves the scoped object at request-processing time, though calling it from a thread with no active request context can raise `ScopeNotActiveException`.

## 7. Multiple Beans, @Qualifier, and @Primary

Suppose there are two `PaymentGateway` implementations:

```java
@Bean("cardGateway")
PaymentGateway cardGateway() {
    return new CardGateway();
}

@Bean("bankGateway")
PaymentGateway bankGateway() {
    return new BankGateway();
}
```

This is an illustrative configuration snippet; `PaymentGateway`, `CardGateway`, and `BankGateway` are hypothetical domain types. If a consumer injects `ObjectProvider<PaymentGateway>` without a qualifier and the container cannot pick an unambiguous candidate, calling `getObject()` / `getIfAvailable()` may report multiple candidates.

**Specifying the target at the injection point:**

```java
public PaymentService(
        @org.springframework.beans.factory.annotation.Qualifier("cardGateway")
        ObjectProvider<PaymentGateway> gateways) {
    this.gateways = gateways;
}
```

With the corresponding field and constructor in `PaymentService`, this provider is constrained to the `cardGateway` candidate; `getObject()` looks up under that condition. This is an illustrative constructor snippet, not a complete standalone class to compile on its own.

**If you want a default candidate**, you can declare `@Primary` on the appropriate bean. Spring can prioritize the primary in single-bean lookups; `getIfUnique()` does not naively count all definitions and always return null when the count exceeds one. **If you want to use all implementations**, call `stream()` or `orderedStream()` and avoid single-bean lookups.

```java
// Placed inside a bean injected with ObjectProvider<PaymentGateway>.
gateways.orderedStream().forEach(gateway -> gateway.healthCheck());
```

In the snippet above, `PaymentGateway` must declare a `healthCheck()` method. `orderedStream()` uses Spring's ordering rules such as `Ordered`/`@Order`; `stream()` has no fixed ordering guarantee. Obtaining and consuming the stream can trigger resolution/creation of matching beans; do not use a stream merely to check existence if you do not want to instantiate all of them.

## 8. Common API Utilities in Application Code

### 8.1. Fallback Only When Needed

```java
NotificationSender sender =
        senders.getIfAvailable(() -> new ConsoleNotificationSender());
```

`senders` has type `ObjectProvider<NotificationSender>`; the two classes/interfaces in the example are hypothetical domain types. If a valid candidate exists, Spring returns the configured bean. Only when no bean exists does the lambda instantiate a default object **outside the container**. Consequently, a self-created fallback does not automatically receive lifecycle callbacks, proxies, AOP, or dependency injection like a Spring-managed bean.

If the requirement is to run only when a unique candidate exists:

```java
senders.ifUnique(sender -> sender.send("ready"));
```

`NotificationSender` is assumed to have `send(String)`. If no bean exists or no unique candidate can be chosen, the action does not run.

### 8.2. Passing Arguments When Instantiating a Bean

`ObjectProvider<T>` provides `getObject(Object... args)` to request a bean with runtime arguments, often useful for prototypes with parameterized constructors or factory methods. Illustrative configuration snippet:

```java
public record ExportTask(String format) {}

@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
ExportTask exportTask(String format) {
    return new ExportTask(format);
}

// Inside the injected consumer bean:
ExportTask csv = tasks.getObject("csv");
// tasks has type ObjectProvider<ExportTask>.
```

`getObject("csv")` requests creating a prototype object with argument `format="csv"`. This is **not** an extra method on `ObjectFactory<T>` and should not be used to pass arbitrary arguments to an already created singleton. For runnable code, place the record, factory method, and provider injection inside a valid class/configuration as shown in the `Demo` example.

### 8.3. Iterating Multiple Beans

```java
List<String> formatterNames = formatterProvider.orderedStream()
        .map(Formatter::name)
        .toList();
```

This snippet uses `Formatter`/`formatterProvider` from the `Demo` program and Java 17. `orderedStream()` fits prioritized plugin/filter pipelines. `stream()` or a for-each loop over the provider fits when order has no business significance. Spring Framework 6.2 adds several overloads for filtering candidates; consult the exact version's Javadoc if using those APIs.

## 9. Comparison with Other Dependency Injection Approaches

| Approach | Characteristics | When Suitable |
| --- | --- | --- |
| Direct `T` injection | Dependency resolved when consumer is created | Required dependency, frequently used, compatible scope. |
| `ObjectFactory<T>` | Obtains an object on `getObject()` call | Needs minimal runtime lookup, e.g. fetching a prototype per operation. |
| `ObjectProvider<T>` | Runtime lookup, optional, unique, and multi-candidate support | Optional features, plugins, prototypes, multiple implementations. |
| `@Lazy T` at injection point | Spring typically injects a proxy and resolves the target when the proxy is used | Want to keep calling API as a direct object; awkward for expressing absent beans and multiple candidates. |
| `Optional<T>` | Expresses optionality at **injection time** | Only need presence/absence at consumer startup, no repeated lookup needed. |
| `jakarta.inject.Provider<T>` | Standard `get()` API per JSR-330/Jakarta Inject | Prefer standard DI API; requires the corresponding Jakarta Inject dependency. |
| `ApplicationContext.getBean(...)` | Direct lookup through context | Infrastructure code genuinely needing container operations; avoid scattering in business services. |

**Distinguishing `ObjectFactory<T>` and `FactoryBean<T>`:** `ObjectFactory` is a lookup handle handed to consumers; `FactoryBean` is an extension point for a container component to **produce** objects for a bean definition. They are not synonymous and should not be swapped merely because of similar names.

## 10. Common Errors and How to Fix Them

**Error 1 — Assuming a provider always creates a new instance.**

Wrong: "Calling `getObject()` twice always returns two distinct objects."

Right: the outcome depends on the **target bean's scope**. Check whether the bean has `@Scope("prototype")`; for singletons, instance reuse is expected behavior.

**Error 2 — Assuming `getIfAvailable()` swallows multiple-bean errors.**

When no bean exists, the method returns `null`. However, if multiple equal candidates exist, `NoUniqueBeanDefinitionException` can still occur. If ambiguity should be skipped, use `getIfUnique()`; if all are needed, use `stream()`; if one must be chosen, configure qualifiers/primary.

**Error 3 — Calling `getObject()` right inside the consumer's constructor.**

```java
// Ineffective if the goal is per-invocation lookup:
this.worker = workerProvider.getObject();
```

Calling this early effectively resolves and caches one bean when constructing the consumer. If you want a fresh prototype per operation, store the **provider** and call `getObject()` inside the processing method.

**Error 4 — Forgetting to handle a `null` result.**

```java
// May throw NPE if no bean exists:
provider.getIfAvailable().run();

// Safer:
provider.ifAvailable(service -> service.run());
```

Assumes the bean has a `run()` method. If the behavior is mandatory when no bean exists, `getObject()` accurately reflects the contract.

**Error 5 — Using a provider instead of designing scopes and lifecycles.**

A provider does not create a request context, does not close resources held by prototypes, and does not automatically make an object thread-safe. Only look up beans within valid contexts/scopes and keep appropriate lifetimes.

**Error 6 — Relying on unguaranteed order.**

If pipeline ordering matters, use `orderedStream()` with `@Order`/`Ordered` metadata, rather than relying on bean registration order or the unspecified order of `stream()`.

**Error 7 — Masking configuration errors with arbitrary fallbacks.**

A fallback can let a program "run" while missing essential functionality. Use `getIfAvailable` only for genuinely **optional** dependencies; core components should use `getObject()` or direct injection to fail fast.

## 11. Design and Testing Checklist

Before picking an API, answer four questions:

1. Is the dependency **required or optional**? Required: `getObject()`; optional: `getIfAvailable()`/`ifAvailable()`.
2. Are there **multiple implementations**? If all are needed, use streams; if a single one is needed, constrain with qualifiers/primary or use `getIfUnique()`.
3. What is the target bean's **scope**? Singletons do not change instances per lookup; prototypes create new ones; web scopes need an active context.
4. Does the consumer need to control **lookup timing**? If not, direct constructor injection is usually simpler and clearer.

Scenarios worth covering in tests:

- `OptionalNotifier` not registered: consumer still starts and `getIfAvailable() == null`.
- One valid notifier registered: provider returns notifier; `ifAvailable` callback executes.
- Two non-primary formatters registered: `getIfUnique() == null`, while `getObject()`/`getIfAvailable()` may report non-uniqueness.
- `@Primary` placed on one formatter: verify default bean selection via single lookup.
- Prototype `RequestToken` requested twice: two distinct instances; switch scope to singleton: same instance.
- Compare `orderedStream()` against `@Order` declarations; test logic relying on expected order.

**Self-practice questions:**

1. Why does injecting `ObjectFactory<PrototypeBean>` into a singleton enable obtaining a new prototype object on each use?
2. How do `getIfAvailable()` and `getIfUnique()` differ when two equal candidates exist?
3. If `@Scope("prototype")` is replaced with singleton in the `Demo` example, how do the token-related output lines change?
4. When does `@Lazy` make more sense, and when does `ObjectProvider<T>` express intent more clearly?

**Answer hints:** (1) The service holds a lookup handle; each call lets the container apply prototype scope. (2) `getIfAvailable()` can throw a non-uniqueness error; `getIfUnique()` returns `null`. (3) The token bean is typically created once and both lookups receive the same instance; two creations are no longer guaranteed and `different` becomes `false`. (4) `@Lazy` is convenient when you only need a proxy to defer touching a target; a provider fits when the consumer itself decides lookup timing, optionality, or handling multiple candidates.

## 12. Official Reference Documentation

- [Spring Framework — ObjectFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectFactory.html)
- [Spring Framework — ObjectProvider Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectProvider.html)
- [Spring Framework — Scoped Beans as Dependencies](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework — Autowiring Collaborators](https://docs.spring.io/spring-framework/reference/core/beans/autowire.html)
- [Spring Framework — Classpath Scanning and @Lazy injection points](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)

**Remember:** `ObjectFactory` and `ObjectProvider` enable **on-demand lookup**; **scope and bean selection rules** determine what gets returned, while the provider method determines how missing or non-unique cases are handled.
