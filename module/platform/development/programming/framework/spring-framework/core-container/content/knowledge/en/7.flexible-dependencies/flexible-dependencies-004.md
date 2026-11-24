# Expressing Optional Dependencies with Optional in Spring Core Container

## Objectives

A class may **require** a repository to complete its core business logic, yet only **optionally use** an audit logger, notification sender, or external integration adapter when those beans are registered. The latter kind of dependency is an *optional dependency*.

In the Spring Core Container, `java.util.Optional<T>` is an explicit way to declare that **bean `T` may be absent**. When Spring resolves an injection point of type `Optional<T>`:

- If a suitable `T` bean is found, Spring injects `Optional.of(bean)` (semantically, a **present** value).
- If no suitable `T` bean exists, Spring injects `Optional.empty()` instead of failing due to a missing dependency.
- If multiple competing `T` beans exist and Spring cannot pick a single bean uniquely, `Optional` **does not make the ambiguity error disappear**: it must still be resolved with qualifiers, primary, or dependency redesign.
- If a candidate bean fails during initialization, `Optional` **does not silently swallow that error**.

After this lesson, you will know how to inject `Optional<T>` via constructors, `@Bean` methods, and setters; read values safely; distinguish "absent" from "ambiguous"; and choose the right mechanism for optional features.

## 1. What Does `Optional<T>` Express?

`Optional<T>` is a Java container representing one of two states:

| State | Check | Interpretation in Dependency Injection |
| --- | --- | --- |
| `Optional.empty()` | `isEmpty() == true` | Spring found no `T` bean matching that injection point |
| `Optional.of(value)` | `isPresent() == true` | Spring resolved a matching `T` bean |

Conceptual example:

```java
// Illustrative snippet inside a Spring-managed class.
final class CheckoutService {
    private final Optional<AuditSink> auditSink;

    CheckoutService(Optional<AuditSink> auditSink) {
        this.auditSink = auditSink;
    }

    void checkout(String orderId) {
        auditSink.ifPresent(sink -> sink.record(orderId));
        // Required checkout steps are still executed.
    }
}
```

`AuditSink` in the example is an application-defined interface, not a built-in Spring API. With a **single constructor**, Spring can use that constructor automatically without `@Autowired`. When no `AuditSink` bean exists, the `auditSink` field receives `Optional.empty()` and the checkout flow continues.

Key point: `Optional<AuditSink>` expresses that **an `AuditSink` bean is not required**. It does **not** mean the optional bean is auto-generated, lazily initialized, allowed to have multiple copies, or will automatically appear in the container later.

## 2. How Does Spring Resolve `Optional<T>`?

Suppose Spring needs to create a consumer bean whose constructor takes an `Optional<AuditSink>` parameter:

1. The container reads the generic type inside `Optional` to determine that the actual dependency is `AuditSink`.
2. Spring searches for beans with a compatible type that satisfy autowire conditions at the injection point (such as `@Qualifier`, generics, bean definition, and related metadata).
3. If resolution yields **one valid candidate**, Spring passes an `Optional` containing that bean to the constructor.
4. If there are **no candidates**, Spring passes `Optional.empty()` to the constructor; this is an anticipated case.
5. If there are **multiple candidates** and bean selection mechanisms still cannot identify a unique bean, bean creation may fail due to ambiguity.

`Optional<T>` only changes how a **missing dependency** is handled; it does not replace bean selection mechanisms. For instance, if two beans implement `AuditSink`, Spring can choose one marked `@Primary`, or you can place `@Qualifier("stdoutAuditSink")` on the `Optional<AuditSink>` parameter. Without a resolution rule, Spring does not turn ambiguity into `Optional.empty()`.

**Relationship with `null`:** When Spring performs injection properly, you receive **an `Optional` object**, not `null` representing a missing dependency. Calling the constructor directly via `new CheckoutService(null)` outside Spring violates the class contract; `Optional` does not prevent callers from passing `null`.

## 3. Complete Example: Audit and Email Features Toggled by Bean Presence

We will build a plain Spring Framework application (without Spring Boot) running two separate containers:

- The first container holds only common configuration: it has `smsNotifier`, but **no** `AuditSink` and no `Notifier` with qualifier `email`.
- The second container holds common configuration **and** integration configuration: additionally registering the audit bean and email bean.

This demonstrates an empty `Optional<T>` when beans are absent, and a populated one when matching beans appear. The email scenario also proves that **having a bean of the right type is not enough** if the injection point specifies a different qualifier.

### 3.1. Project Setup

Structure:

```text
spring-optional-di/
├── pom.xml
└── src/main/java/demo/OptionalInjectionDemo.java
```

`pom.xml` (Java 17+, Spring Framework 6.2.19):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-optional-di</artifactId>
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
                <version>3.13.0</version>
                <artifactId>maven-compiler-plugin</artifactId>
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

### 3.2. Standalone Runnable Java Code

`src/main/java/demo/OptionalInjectionDemo.java`:

```java
package demo;

import java.util.Optional;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class OptionalInjectionDemo {

    interface AuditSink {
        void record(String event);
    }

    interface Notifier {
        String channel();
    }

    static final class CheckoutService {
        private final Optional<AuditSink> auditSink;
        private final Optional<Notifier> emailNotifier;

        CheckoutService(Optional<AuditSink> auditSink,
                        Optional<Notifier> emailNotifier) {
            this.auditSink = auditSink;
            this.emailNotifier = emailNotifier;
        }

        void checkout() {
            System.out.println("audit=" +
                    (auditSink.isPresent() ? "present" : "absent"));

            auditSink.ifPresent(sink -> sink.record("order-42"));

            String selectedChannel = emailNotifier
                    .map(Notifier::channel)
                    .orElse("disabled");
            System.out.println("email=" + selectedChannel);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CommonConfig {

        @Bean
        Notifier smsNotifier() {
            return () -> "sms";
        }

        @Bean
        CheckoutService checkoutService(
                Optional<AuditSink> auditSink,
                @Qualifier("email") Optional<Notifier> emailNotifier) {
            return new CheckoutService(auditSink, emailNotifier);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class EnabledConfig {

        @Bean
        AuditSink stdoutAuditSink() {
            return event -> System.out.println("AUDIT: " + event);
        }

        @Bean
        @Qualifier("email")
        Notifier emailNotifier() {
            return () -> "email";
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(CommonConfig.class)) {
            System.out.println("without optional beans:");
            context.getBean(CheckoutService.class).checkout();
        }

        try (var context = new AnnotationConfigApplicationContext(
                CommonConfig.class, EnabledConfig.class)) {
            System.out.println("with optional beans:");
            context.getBean(CheckoutService.class).checkout();
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.OptionalInjectionDemo
```

**Standard output printed by the program** (excluding Maven/logging framework messages):

```text
without optional beans:
audit=absent
email=disabled
with optional beans:
audit=present
AUDIT: order-42
email=email
```

Explanation:

- With only `CommonConfig`, Spring still creates `CheckoutService` despite the absence of `AuditSink` and an `email`-qualified `Notifier` bean. Both `Optional` parameters are empty.
- `smsNotifier` is a real `Notifier` bean, but it **does not satisfy the `email` qualifier**. It is not chosen as the email notifier, and missing email causes no error.
- When `EnabledConfig` is added, `stdoutAuditSink` and `emailNotifier` are registered; both parameters receive populated `Optional` instances.
- `checkout()` uses `ifPresent` for auditing and `map(...).orElse(...)` for email. The main flow needs no `null` checks and never calls `get()` on an empty Optional.
- Each `AnnotationConfigApplicationContext` is a separate container. Registering additional beans in the second case **starts another container**, rather than dynamically mutating a running container.

### 3.3. Placing `Optional<T>` on a Component Constructor

In a project using component scanning, you can keep the contract directly in the constructor:

```java
// Illustrative: interface AuditSink belongs to the application;
// the class must be within component scan scope.
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
class PurchaseProcessor {
    private final Optional<AuditSink> auditSink;

    PurchaseProcessor(Optional<AuditSink> auditSink) {
        this.auditSink = auditSink;
    }

    void handle(String event) {
        auditSink.ifPresent(sink -> sink.record(event));
    }
}
```

This is an **illustrative snippet meant to be placed in a project that has AuditSink**, not a standalone program. Constructor injection keeps fields `final`, makes dependencies explicit, and makes instantiating mocks in unit tests easy via `Optional.empty()` or `Optional.of(fake)`.

There is no need for `@Autowired` if the class has only one constructor. When a class has multiple constructors, Spring follows specific constructor-selection rules; `Optional<T>` alone does not dictate which constructor Spring chooses.

## 4. Common Places to Inject `Optional<T>`

### Constructor — Preferred for Class Contracts

```java
// Illustrative snippet in a Spring-managed class:
private final Optional<AuditSink> auditSink;

public MyService(Optional<AuditSink> auditSink) {
    this.auditSink = auditSink;
}
```

Treat this as a **design decision**: the class accepts operating without `AuditSink`. If the core functionality still works without that dependency, declaring `Optional` is appropriate. If lacking the dependency breaks core behavior, keep `AuditSink` as a required `AuditSink` parameter instead of masking a configuration error.

### `@Bean` Method Parameters

```java
@Configuration(proxyBeanMethods = false)
class ServiceConfig {
    @Bean
    MyService myService(Optional<AuditSink> auditSink) {
        return new MyService(auditSink);
    }
}
```

This illustrates configuration in a project where `MyService` and `AuditSink` are already defined. Spring resolves factory method parameters according to dependency injection rules, making this convenient when you prefer not to put Spring annotations inside business classes.

### Setter or Field with `@Autowired`

```java
// Illustrative snippet in a Spring-managed bean:
private Optional<AuditSink> auditSink = Optional.empty();

@Autowired
void setAuditSink(Optional<AuditSink> auditSink) {
    this.auditSink = auditSink;
}
```

For an injection point of type `Optional<T>`, the absence of bean `T` **does not** cause a required setter to fail: Spring can pass `Optional.empty()`. This is a key difference from a setter taking plain `AuditSink` with `@Autowired(required = false)`: Spring can **skip calling the setter altogether** if that setter's dependency cannot be resolved.

Field injection `@Autowired private Optional<AuditSink> auditSink;` is also supported, though constructor injection is usually easier to maintain and test.

## 5. Reading `Optional` Safely

`Optional` itself provides methods covering both states:

| Java API | When Value Is Present | When Value Is Absent |
| --- | --- | --- |
| `isPresent()` / `isEmpty()` | Checks presence state | Checks presence state |
| `ifPresent(action)` | Invokes `action` with bean | Does nothing |
| `ifPresentOrElse(action, emptyAction)` | Invokes `action` | Runs `emptyAction` |
| `map(transform)` | Transforms value and wraps in a new Optional | Returns `Optional.empty()` |
| `orElse(fallback)` | Returns present value | Returns fallback |
| `orElseGet(supplier)` | Returns present value | Invokes supplier lazily |
| `orElseThrow(...)` | Returns present value | Throws application-chosen exception |

Common patterns:

```java
// Illustrative snippet inside a class that already has the auditSink field:
// 1. Action executed only if the integration is present.
auditSink.ifPresent(sink -> sink.record("PAYMENT_SUCCESS"));

// 2. Alternative path if the bean is missing.
auditSink.ifPresentOrElse(
        sink -> sink.record("PAYMENT_SUCCESS"),
        () -> System.out.println("Audit adapter not installed")
);

// 3. Extracting a value with a pure-Java fallback.
String status = auditSink
        .map(sink -> "audit-enabled")
        .orElse("audit-disabled");
```

**Distinguishing `orElse` and `orElseGet`.** `orElse(expensiveFallback())` still evaluates the argument expression at call time even when the Optional is populated. `orElseGet(() -> expensiveFallback())` invokes the supplier only when the Optional is empty. However, if you want to **perform a side effect** when no bean exists, `ifPresentOrElse` or `if (optional.isEmpty())` usually communicates intent more clearly.

Avoid calling `optional.get()` without checking: if the Optional is empty, Java throws `NoSuchElementException`. Likewise, avoid `optional.orElse(null)` if it forces callers back into `null` checks when `map`, `ifPresent`, or a meaningful fallback can handle it directly.

**Do not store `Optional` in a field solely to replace every nullable field.** In Spring DI, using `Optional<T>` at the **dependency injection boundary** communicates the contract clearly. Internally, depending on your needs, you can keep the Optional or map it to a valid fallback strategy to reduce branching; that internal choice does not change how Spring selects beans.

## 6. Combining `Optional<T>` with `@Qualifier` and `@Primary`

### `@Qualifier`: One Bean Type, Multiple Purposes

If an application has multiple `Notifier` beans but only one serves email:

```java
// Inside a Spring configuration; these are illustrative snippets.
@Bean
@Qualifier("email")
Notifier smtpNotifier() {
    return () -> "smtp";
}

@Bean
@Qualifier("sms")
Notifier smsNotifier() {
    return () -> "sms";
}

// At the injection point (constructor or @Bean factory method):
MyService(@Qualifier("email") Optional<Notifier> notifier) {
    // ...
}
```

`@Qualifier("email")` only **filters** among `Notifier` beans. When no bean satisfies the condition, you get `Optional.empty()`; when one satisfies it, the Optional holds that bean. If multiple beans **satisfy the same qualifier** without a rule identifying a unique candidate, an ambiguity error can still occur. A qualifier does not guarantee that only one bean remains.

### `@Primary`: Choosing Among Compatible Beans

```java
// Illustrative snippet in @Configuration:
@Bean
@Primary
AuditSink preferredAuditSink() {
    return event -> { /* send to primary audit system */ };
}

@Bean
AuditSink secondaryAuditSink() {
    return event -> { /* send to another system */ };
}
```

For an `Optional<AuditSink>` injection point without a qualifier, `@Primary` helps Spring pick a preferred bean when multiple candidates match. If **two competing primaries** exist or other configuration leaves candidates indistinguishable, Spring can still fail. Wrapping type `T` in `Optional<T>` does not authorize picking "any arbitrary bean" from the candidate pool.

### Generics Must Still Be Declared Properly

The generic type inside `Optional<T>` is critical information. Given `Repository<Customer>` and `Repository<Order>`, an `Optional<Repository<Customer>>` injection point can use generics to distinguish candidates if bean definitions preserve that type metadata. Avoid raw `Optional` or overly broad declarations that prevent Spring from knowing the exact `T` you want.

## 7. How `Optional<T>` Differs from `@Autowired(required=false)`, `@Nullable`, and `ObjectProvider<T>`

These tools all address missing dependencies, yet each has a distinct contract:

| Declaration | If No `T` Bean Exists | Characteristics |
| --- | --- | --- |
| `Optional<T>` at injection point | Receives `Optional.empty()` | Explicitly represents both present and absent states; ideal for single optional dependencies |
| `@Autowired(required=false)` on field `T` | Spring skips assigning field; keeps default | Often requires `null`/default handling; `required` applies at injection-point level |
| `@Autowired(required=false)` on setter `setT(T)` | Setter may be skipped entirely | Setter is not called when dependency cannot be resolved |
| `@Nullable T` on Spring-supported parameter | Receives `null` when bean is absent | Communicates via nullability; must handle null safely |
| `ObjectProvider<T>` | Receives provider; `getIfAvailable()` may return null | Queries bean intentionally at usage time; suits lazy/dynamic lookup |
| Required `T` (no Optional) | Typically fails bean creation on missing dependency | Appropriate for components that cannot function without `T` |

`@Nullable` here refers to an annotation Spring recognizes on **parameters**, such as `@Nullable AuditSink auditSink`. In Spring Framework 6.2, support for type-use nullable annotations is limited; place a supported annotation on the parameter if using this style. `Optional` preserves a more consistent Java model since you do not have to handle `null` parameters.

### Comparing `@Autowired(required=false)`

```java
// Illustrative snippet in a Spring-managed bean:
private AuditSink auditSink; // defaults to null

@Autowired(required = false)
void setAuditSink(AuditSink auditSink) {
    this.auditSink = auditSink;
}
```

When `AuditSink` does not exist, the setter may **never be invoked**. If the class needs a non-`null` default, you must supply an initial value or fallback implementation. With `Optional<AuditSink>`, once Spring injects it, the caller receives an object on which it can directly call `isPresent()` or `ifPresent()`.

Do not mechanically put `@Autowired(required=false)` on a constructor assuming every parameter of that constructor becomes optional like `Optional<T>`. Spring's constructor-selection rules differ from fields/setters; the clearest way to mark a single parameter optional is to declare `Optional<T>` right on that parameter.

### When to Choose `ObjectProvider<T>`?

`Optional<T>` is resolved **when the dependency is injected** into the consumer bean. It does not guarantee lazy creation of `T` and does not re-query if the registry changes.

`ObjectProvider<T>` lets you query on demand:

```java
// Illustrative snippet in a Spring-managed bean:
import org.springframework.beans.factory.ObjectProvider;

final class AuditService {
    private final ObjectProvider<AuditSink> auditProvider;

    AuditService(ObjectProvider<AuditSink> auditProvider) {
        this.auditProvider = auditProvider;
    }

    void record(String event) {
        AuditSink sink = auditProvider.getIfAvailable();
        if (sink != null) {
            sink.record(event);
        }
    }
}
```

`getIfAvailable()` can return `null` when no bean exists, though it does **not** ignore all failures; bean instantiation or multi-candidate disambiguation must still be valid. The provider also offers `ifAvailable(Consumer<T>)` to avoid null checks, `getIfUnique()` when a value is desired only if a unique candidate exists per API semantics, and `stream()`/`orderedStream()` for retrieving multiple beans. In particular, with `prototype` scope, invoking the provider multiple times can return different instances depending on bean registration/scope.

Choose `ObjectProvider<T>` when you need repeated lookups, lazy access, scoped beans, or multiple candidates. Choose `Optional<T>` when at consumer creation time you simply need to know **whether a dependency exists or not**.

## 8. Optional Dependencies vs. Optional Features

Not every toggleable feature should be modeled by bean absence:

- **Optional dependency:** `CheckoutService` runs normally without `AuditSink`; this is a good fit for `Optional<AuditSink>`.
- **Feature flag:** configuration may specify `audit.enabled=false` even while an `AuditSink` bean exists. Here, feature state and bean presence are **two separate concepts**.
- **Conditional integration:** if configuration decides whether `AuditSink` is created, `Optional<AuditSink>` becomes how the consumer handles the bean not being registered. Plain Spring Framework has `@Conditional` and conditional bean registration mechanisms; Spring Boot additionally offers `@ConditionalOn...` annotations such as `@ConditionalOnProperty`. Those `@ConditionalOn...` annotations are **Spring Boot** features, not part of the core `spring-context` API used in the Maven example above.

If core behavior **must not operate** when a bean is missing, avoid declaring Optional merely to let the application start. For example, do not turn a mandatory `PaymentGateway` into `Optional<PaymentGateway>` and silently skip payment. Misconfiguration should fail fast in that case.

If a fallback is required when an integration is absent, make that fallback explicit:

```java
// Conceptual illustration: a pure-Java fallback implementation can be chosen.
AuditSink selected = auditSink.orElseGet(() -> event -> {
    // Do not write audit to external system; intentional fallback policy.
});
selected.record("order-42");
```

In a real project, a `NoOpAuditSink` can also be conditionally registered as a bean if consumers should always receive a non-optional dependency. Do not let both a fallback bean and a real bean match simultaneously without a selection rule.

## 9. Common Misconceptions

### "`Optional<T>` hides all bean errors"

**False.** It only represents the **valid absence of a dependency**. A misconfigured `T` bean, unsupported circular dependency, constructor exception, or two indistinguishable candidates can still cause context startup to fail.

### "If two `T` beans exist, Spring returns `Optional.empty()`"

**False.** Two distinct beans do not mean a missing bean. Spring must select one candidate via type matching, qualifiers, `@Primary`, and related metadata; if none can be selected, ambiguity is an error that must be fixed.

### "`Optional<T>` updates automatically if a new bean appears"

**False.** The `Optional` value received via constructor injection is the resolution snapshot at injection time. If business logic needs dynamic lookup, `ObjectProvider<T>` or appropriate container APIs express that intent accurately.

### "`Optional<T>` automatically detects config properties of type `T`"

**False.** Bean lookup and property binding are distinct mechanisms. `Optional<AuditSink>` checks whether the container holds a matching `AuditSink` bean. `application.properties`/`application.yml` does not automatically create an `AuditSink` bean simply because a key exists in a file.

### "Use `Optional` for every dependency"

Not sensible. Use `Optional` when **a missing dependency is a designed, valid case**. Required dependencies should remain direct `T` types so the application fails clearly when configuration is missing.

### "`Optional<List<T>>` and `List<T>` are the same"

They express different contracts. `Optional<List<T>>` states that **the list value itself may be absent**; `List<T>` states that the consumer accepts a list of elements. For multi-bean collection injection, Spring has dedicated rules for candidate sets and certain empty-collection cases (notably on a single constructor). Do not wrap collections in Optional assuming Spring always produces a list of beans or returns empty when no elements exist. Pick `List<T>` when you need 0..n implementations and consider `ObjectProvider<T>.stream()` for dynamic lookups.

## 10. Scenario-Based Troubleshooting

| Symptom | What to Check | Fix |
| --- | --- | --- |
| `Optional.isEmpty()` despite writing an implementation | Is the class registered as a bean, within component scan packages, with registration conditions enabled? | Register the bean or adjust scan scope/condition settings |
| Bean implements the interface yet Optional is still empty | Do qualifiers, generics, and autowire-candidate status match? | Fix qualifiers, generic types, or registration metadata |
| Context fails with `NoUniqueBeanDefinitionException` | Multiple valid `T` candidates exist without a single choice | Use `@Qualifier` or `@Primary`; consider multi-bean injection if multiple are needed |
| Context fails with `BeanCreationException` | The selected bean's factory/constructor failed | Fix the bean creation error; `Optional` does not catch initialization errors |
| `NullPointerException` on the Optional variable | Object instantiated with `new` outside Spring, or caller passed `null` | Ensure consumer is Spring-managed; pass `Optional.empty()` in tests |
| `NoSuchElementException` when calling `get()` | Optional is empty and code did not check | Use `ifPresent`, `map`, `orElseGet`, or a meaningful `orElseThrow` |
| `@Autowired(required=false)` setter never runs | Setter has an unresolvable dependency | Consider an `Optional<T>` parameter or explicit default design |
| Expected Optional to make bean lazy, yet it still initializes eagerly | `Optional<T>` resolves at injection time | Use `ObjectProvider<T>` for intentional lazy lookup |

Systematic debugging steps: (1) verify whether bean `T` is registered; (2) check actual type, generics, and component scan; (3) inspect qualifiers and `@Primary`; (4) distinguish **no candidates** from **too many candidates**; (5) if a candidate exists yet startup still fails, inspect the root exception during bean creation.

In tests, you can build two contexts as in the example: one without optional beans and one with them. This verifies both the **fallback path** and the **dependency-present path**. When instantiating the consumer directly in unit tests, pass `Optional.empty()` or `Optional.of(fake)` directly; there is no need to boot a full container for pure-Java business checks.

## 11. Exercises and Guided Answers

**Exercise 1.** In the standalone example, remove `@Qualifier("email")` from the `Optional<Notifier>` parameter of `checkoutService`. With `CommonConfig`, what happens?

*Answer:* Because only `smsNotifier` has type `Notifier`, the Optional parameter can now receive `smsNotifier`, and the program prints `email=sms`. This shows that an "optional" dependency must still be **semantically filtered**; dropping the qualifier can pick an unintended integration.

**Exercise 2.** Keep the change from Exercise 1, and add `EnabledConfig` as well. With two `Notifier` beans (`smsNotifier` and `emailNotifier`) and no `@Primary`, predict the outcome.

*Answer:* Spring must select one `Notifier` for the `Optional<Notifier>` injection point. Without another valid disambiguation rule, the context may fail due to multiple candidates. Wrapping in `Optional` does not turn this into empty.

**Exercise 3.** Promote `AuditSink` from an optional feature to a **mandatory requirement** for completing checkout. How should the constructor parameter type change?

*Answer:* Take `AuditSink` directly instead of `Optional<AuditSink>`. When the bean is not registered, Spring fails consumer creation, surfacing the missing required dependency early.

**Exercise 4.** A consumer wants a fresh `prototype`-scoped `AuditSink` on each operation. Does keeping `Optional<AuditSink>` on the constructor guarantee this?

*Answer:* No. Optional is resolved at injection time. Consider `ObjectProvider<AuditSink>` and calling `getObject()`/`ifAvailable(...)` when needed; be clear on scope policy and missing-bean behavior.

**Exercise 5.** Rewrite obtaining the email channel without calling `get()` and without computing an expensive fallback when Optional is present.

*Answer:*

```java
String channel = emailNotifier
        .map(Notifier::channel)
        .orElseGet(() -> computeFallbackChannel());
```

This is an illustrative snippet assuming `computeFallbackChannel()` exists in the class; the supplier runs only when the Optional is empty.

## Key Takeaways to Remember

- `Optional<T>` is a **contract stating that the absence of bean `T` is acceptable**.
- Unique/resolvable candidate → populated `Optional`; no candidate → `Optional.empty()`.
- Unresolved multiple candidates, bean initialization failures, and misconfigurations **remain errors**.
- Use constructor injection to make optional dependencies explicit; use `@Qualifier` when a specific implementation role is required.
- Use `ifPresent`, `map`, and `orElseGet` instead of unchecked `get()` or unnecessary `null` handling.
- Choose `ObjectProvider<T>` for flexible lookup by timing/scope; use direct `T` dependencies for required functionality.

## Official References

- Spring Framework, [Using `@Autowired`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html) — Optional, `required=false`, constructor and factory method injection.
- Spring Framework, [Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html) — how qualifiers narrow candidates.
- Spring Framework, [Using `@Primary`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-primary.html) — selecting a preferred candidate.
- Spring Framework, [`ObjectProvider<T>` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectProvider.html) — flexible dependency lookup.
- Java SE 17, [`Optional<T>` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html) — `ifPresent`, `map`, `orElse`, `orElseGet`.
