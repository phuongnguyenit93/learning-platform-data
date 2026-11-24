# `ObjectProvider` for optional dependencies and on-demand retrieval in Spring Boot Auto-Configuration

In Spring Boot, an auto-configuration often wants to provide a feature that **can work even if an extension bean does not exist**. For example, a transaction processor can send events to an `AuditSink` when the application has configured an audit store, while still running normally when no `AuditSink` exists. Another need is to **retrieve a dependency only when actually needed** rather than pulling it in during construction of the consuming bean.

`org.springframework.beans.factory.ObjectProvider<T>` addresses both of these needs. It is a Spring Framework interface; Spring can inject a provider of type `T` directly through a constructor, `@Bean` method, or injection point. The provider is a **bean lookup handle**: you call its methods to obtain a bean, detect when none exists, handle multiple candidates, or iterate over beans of the same type.

**Remember from the start:** injecting `ObjectProvider<AuditSink>` **does not require** the context to contain an `AuditSink`. However, **when you actually call** `getObject()` or `getIfAvailable()`, Spring still has to resolve the bean according to standard rules: it may return a bean, create a lazy bean, or throw an exception if missing/non-unique. `ObjectProvider` does not turn every bean conflict into `null`.

## 1. Problem: required or optional dependency?

Suppose a library has an interface:

```java
public interface AuditSink {
    void write(String event);
}
```

With standard constructor injection:

```java
public class PaymentService {
    private final AuditSink auditSink;

    public PaymentService(AuditSink auditSink) {
        this.auditSink = auditSink;
    }
}
```

These are **illustrative snippets** that need to be placed in appropriately named Java files; if `PaymentService` is registered as a bean while the context **has no** `AuditSink`, dependency injection can fail with `NoSuchBeanDefinitionException` wrapped in a bean creation error. Conversely, if there are **multiple beans of the same type** with no way to choose one, Spring can report `NoUniqueBeanDefinitionException`.

However, for an extension feature, lacking an `AuditSink` may be completely valid: the app still processes payments and simply skips the audit step. We want the payment processing bean to **always exist** and **only ask for the audit bean when a transaction occurs**.

```java
import org.springframework.beans.factory.ObjectProvider;

public class PaymentService {
    private final ObjectProvider<AuditSink> auditSinks;

    public PaymentService(ObjectProvider<AuditSink> auditSinks) {
        this.auditSinks = auditSinks;
    }

    public void pay(String event) {
        // Process payment first...
        AuditSink sink = auditSinks.getIfAvailable();
        if (sink != null) {
            sink.write(event);
        }
    }
}
```

This code illustrates the principle; `AuditSink` must still exist at **compile time** because it is referenced in the type signature, but an **`AuditSink` bean in the context** is not required. A runnable example and complete tests are in section 5.

## 2. Mechanism: inject the provider first, look up the bean later

A constructor accepting `ObjectProvider<T>` is injected by Spring with an appropriate provider object. That **does not require Spring to immediately find and instantiate an instance of `T`** to pass into the constructor. Each time code invokes the provider, it asks the BeanFactory to resolve the object by type `T` and the current candidate rules.

```text
ApplicationContext starts building the PaymentService bean
    |
    | Inject ObjectProvider<AuditSink>
    v
PaymentService is created even without AuditSink
    |
    | Later the application calls pay(...)
    v
auditSinks.getIfAvailable()
    |
    +-- No AuditSink ----------> null ------> Skip audit
    |
    +-- One matching bean -----> That bean -> Call write(...)
    |
    +-- Multiple beans, ambiguous -> NoUniqueBeanDefinitionException
```

There are **two independent axes** here:

1. **Optionality:** `getIfAvailable()` can return `null` when no candidate is found, so the extension is not required to be configured.
2. **On-demand retrieval:** `getIfAvailable()` or `getObject()` is called at a time of your choosing, instead of always resolving the dependency inside the consumer's constructor.

**Distinguish deferred lookup from lazy bean creation:** A singleton `AuditSink` not marked `@Lazy` may **already be instantiated during ApplicationContext refresh** because Spring typically pre-instantiates non-lazy singletons. A provider does not automatically make all target beans lazy. If you genuinely need to defer creating `AuditSink` until the first lookup, design the target bean as `@Lazy` or use an appropriate scope and test the behavior. With a lazy singleton, the first lookup creates the instance; subsequent lookups normally receive the **same singleton**. With prototype scope, each lookup can create a **new instance**.

A provider also **does not guarantee a cheap or asynchronous operation**: when creating a bean requires an expensive constructor or resource connections, calling `getObject()` can still block and throw initialization errors.

## 3. Key methods of `ObjectProvider<T>`

Common API group in Spring Framework 6.x/Spring Boot 3.x:

| API | When no matching bean exists | When one candidate is selected | When multiple candidates cannot be uniquely resolved |
| --- | --- | --- | --- |
| `getObject()` | Throws `NoSuchBeanDefinitionException` | Returns the bean | Throws `NoUniqueBeanDefinitionException` |
| `getIfAvailable()` | Returns `null` | Returns the bean | May throw `NoUniqueBeanDefinitionException` |
| `getIfAvailable(Supplier<T>)` | Calls supplier to get fallback | Returns the bean without calling fallback | May still throw non-unique error |
| `ifAvailable(Consumer<T>)` | Does not invoke consumer | Invokes consumer with the bean | May still throw non-unique error |
| `getIfUnique()` | Returns `null` | Returns the bean | Returns `null` if no primary candidate is determined |
| `getIfUnique(Supplier<T>)` | Uses fallback | Returns the bean | Uses fallback when no unique candidate can be determined |
| `ifUnique(Consumer<T>)` | Does not invoke consumer | Invokes consumer | Does not invoke consumer if no unique candidate can be determined |
| `stream()` | Empty stream | Stream containing the matching candidate | Stream of multiple candidates; does not require selecting a single bean |
| `orderedStream()` | Empty stream | Stream containing the candidate | Stream sorted according to the corresponding `Ordered`/`@Order` mechanism |

**Note on `@Primary`:** when there are multiple beans of the same type but **one bean is identified by Spring as the single primary candidate** via `@Primary`, single-bean lookups can select that candidate. Therefore `getIfUnique()` must not be understood mechanically as "returns `null` if the bean count is greater than one"; container autowire rules must be considered.

### 3.1. `getObject()`: dependency required at call time

```java
AuditSink sink = auditSinks.getObject();
sink.write("created-order");
```

Use this when the current operation **cannot proceed without** `AuditSink`. Injecting the provider initially does not fail, but **this call** will throw an exception if no bean is found or no unique candidate can be selected.

### 3.2. `getIfAvailable()` and fallback supplier

```java
AuditSink sink = auditSinks.getIfAvailable();
if (sink != null) {
    sink.write("order-paid");
}
```

If you want a fallback implementation **not registered in the Spring context**:

```java
AuditSink sink = auditSinks.getIfAvailable(
        () -> event -> System.out.println("Local audit: " + event)
);
sink.write("order-paid");
```

This is an **excerpt** using an `AuditSink` interface that has a `write(String)` method. The supplier is only invoked if no suitable bean exists; the object created by the supplier **does not automatically become a bean**, so do not expect Spring to autowire dependencies, run lifecycle callbacks, or apply bean post-processors to this object. For a default that needs to be managed by Spring, design a default bean in auto-configuration using `@ConditionalOnMissingBean`.

### 3.3. `getIfUnique()`: proceed only if a single bean is selected

```java
AuditSink unique = auditSinks.getIfUnique();
if (unique != null) {
    unique.write("only-if-unique");
}
```

If there is no bean or multiple candidates without a single selectable one, `unique` is `null`. This is a reasonable way to express that a feature should only activate when configuration is unambiguous, though important production misconfigurations should not be silently ignored without logging/reporting.

### 3.4. `ifAvailable(...)` and `ifUnique(...)`

```java
auditSinks.ifAvailable(sink -> sink.write("payment-accepted"));
auditSinks.ifUnique(sink -> sink.write("single-recipient"));
```

These two methods are useful when you only execute a side effect if a bean is selected. They do not automatically make writing the audit asynchronous. `ifAvailable` still does not resolve a multi-candidate conflict for you.

### 3.5. `stream()` and `orderedStream()` for multi-bean extension points

If a feature is designed to support **multiple plugins** of the same type:

```java
auditSinks.orderedStream()
        .forEach(sink -> sink.write("payment-accepted"));
```

`stream()` has no specific ordering contract; `orderedStream()` uses Spring's comparator, which can take `Ordered` or `@Order` into account. When plugin execution order carries business significance, declare `@Order` on the implementation or bean definition and test the ordering. When iterating the stream, **obtaining each bean can instantiate it**; do not treat `stream()` as a way to inspect metadata without ever instantiating beans.

**Do not confuse:** `ObjectProvider<List<AuditSink>>` looks for a **bean of list type**, which is not equivalent to iterating over all `AuditSink` beans. If the goal is multiple beans implementing the same interface, use `ObjectProvider<AuditSink>.stream()` / `orderedStream()`.

## 4. How does `ObjectProvider` differ from other forms of optional injection?

| Mechanism | Characteristics | Limitations/considerations |
| --- | --- | --- |
| Constructor taking `AuditSink` | Required dependency, resolved when creating the consumer | Missing bean or multiple unresolvable candidates can prevent context startup. |
| `@Autowired(required = false)` | Allows skipping an optional injection point | Primarily used for field/setter and injection config; does not provide repeated lookup APIs like a provider. |
| Constructor taking `Optional<AuditSink>` | Expresses absence of a bean via `Optional.empty()` | Resolution normally occurs at injection time; not intended for repeated on-demand lookups. |
| `@Nullable AuditSink` | Can receive `null` for an optional injection point | Does not provide a mechanism to retrieve at a desired time. |
| `@Lazy` injection | Can inject a lazy proxy to defer target access | If target is absent, errors may occur when the proxy is used; depends on proxying capability for the target type. |
| `ObjectProvider<AuditSink>` | Provides rich APIs for optional, on-demand, unique, and multi-candidate lookup | Consumer must choose when to look up, fallback, and ambiguity-handling policy. |
| `@ConditionalOnBean(AuditSink.class)` | Only registers a configuration/bean when `AuditSink` is already present at condition evaluation time | If you want the consumer bean to **still exist when the dependency is absent**, eliminating the consumer bean is the wrong behavior. |
| `@ConditionalOnMissingBean(MyConsumer.class)` | Allows users to replace the default consumer bean | Addresses configuration override, not a substitute for `ObjectProvider` inside the consumer. |

Example contrasting two intents:

```java
// When AuditSink is NOT present, still create PaymentService:
@Bean
PaymentService paymentService(ObjectProvider<AuditSink> sinks) {
    return new PaymentService(sinks);
}
```

```java
// When AuditSink is NOT present, do NOT register PaymentService at all:
@Bean
@ConditionalOnBean(AuditSink.class)
PaymentService paymentService(AuditSink sink) {
    return new PaymentService(sink);
}
```

These are **architectural excerpts** belonging to two different approaches; `PaymentService` in the second approach must have a constructor accepting `AuditSink`. They express **different** product contracts. You need to decide whether the product allows audit to be absent or treats audit as a mandatory condition before choosing annotations.

## 5. Runnable example: Java 17 + Spring Boot 3.3.5

The following test suite uses `ApplicationContextRunner` to create isolated contexts. An auto-configuration always provides a default `AuditService` if the user has not supplied one, and injects `ObjectProvider<AuditSink>`. `AuditSink` is the optional extension point.

The tests demonstrate:
1. No `AuditSink`: `AuditService` is still created; `getIfAvailable()` returns `null`, and `getObject()` throws when actually called.
2. `@Lazy AuditSink`: creating `AuditService` **does not trigger** sink initialization; the sink is only created when the service uses the provider.
3. Two sinks of the same type: `orderedStream()` iterates both according to `@Order`; `getIfAvailable()` reports non-uniqueness when no `@Primary` exists.
4. Two sinks where one is `@Primary`: `getIfUnique()` can select the primary candidate.
5. User supplies `AuditService`: `@ConditionalOnMissingBean(AuditService.class)` causes the default bean to back off.

### 5.1. Directory structure

```text
object-provider-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── ObjectProviderDemoTest.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>object-provider-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 5.2. Standalone test file

Create `src/test/java/demo/ObjectProviderDemoTest.java`:

```java
package demo;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ObjectProviderDemoTest {

    interface AuditSink {
        String id();
        String send(String event);
    }

    record NamedSink(String id) implements AuditSink {
        @Override
        public String send(String event) {
            return id + ":" + event;
        }
    }

    static final class AuditService {
        private final ObjectProvider<AuditSink> sinks;

        AuditService(ObjectProvider<AuditSink> sinks) {
            this.sinks = sinks;
        }

        String send(String event) {
            AuditSink sink = sinks.getIfAvailable();
            return sink == null ? "skipped:" + event : sink.send(event);
        }

        String sendWithFallback(String event) {
            AuditSink sink = sinks.getIfAvailable(
                    () -> new NamedSink("local"));
            return sink.send(event);
        }

        AuditSink requiredSink() {
            return sinks.getObject();
        }

        AuditSink uniqueSink() {
            return sinks.getIfUnique();
        }

        List<String> orderedSinkIds() {
            return sinks.orderedStream()
                    .map(AuditSink::id)
                    .toList();
        }
    }

    @AutoConfiguration
    static class AuditAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(AuditService.class)
        AuditService auditService(ObjectProvider<AuditSink> sinks) {
            return new AuditService(sinks);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class LazySinkConfiguration {
        @Bean
        AtomicInteger sinkCreations() {
            return new AtomicInteger();
        }

        @Bean
        @Lazy
        AuditSink lazySink(AtomicInteger sinkCreations) {
            sinkCreations.incrementAndGet();
            return new NamedSink("remote");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class MultiSinkConfiguration {
        @Bean
        @Order(20)
        AuditSink alphaSink() {
            return new NamedSink("alpha");
        }

        @Bean
        @Order(-5)
        AuditSink betaSink() {
            return new NamedSink("beta");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrimarySinkConfiguration {
        @Bean
        @Primary
        AuditSink preferredSink() {
            return new NamedSink("preferred");
        }

        @Bean
        AuditSink otherSink() {
            return new NamedSink("other");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomServiceConfiguration {
        @Bean
        AuditService customAuditService(ObjectProvider<AuditSink> sinks) {
            return new AuditService(sinks);
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            AuditAutoConfiguration.class));

    @Test
    void missingOptionalSinkDoesNotPreventServiceCreation() {
        runner.run(context -> {
            AuditService service = context.getBean(AuditService.class);

            assertThat(service.send("pay")).isEqualTo("skipped:pay");
            assertThat(service.sendWithFallback("pay"))
                    .isEqualTo("local:pay");
            assertThat(service.uniqueSink()).isNull();
            assertThat(service.orderedSinkIds()).isEmpty();
            assertThatThrownBy(service::requiredSink)
                    .isInstanceOf(NoSuchBeanDefinitionException.class);
        });
    }

    @Test
    void providerDoesNotForceLazySinkCreationAtInjectionTime() {
        runner.withUserConfiguration(LazySinkConfiguration.class)
                .run(context -> {
                    AtomicInteger creations =
                            context.getBean(AtomicInteger.class);
                    AuditService service = context.getBean(AuditService.class);

                    assertThat(creations.get()).isZero();

                    assertThat(service.send("pay")).isEqualTo("remote:pay");
                    assertThat(creations.get()).isEqualTo(1);

                    assertThat(service.send("refund"))
                            .isEqualTo("remote:refund");
                    assertThat(creations.get()).isEqualTo(1);
                });
    }

    @Test
    void multipleSinksCanBeStreamedButNotResolvedAsOne() {
        runner.withUserConfiguration(MultiSinkConfiguration.class)
                .run(context -> {
                    AuditService service = context.getBean(AuditService.class);

                    assertThat(service.orderedSinkIds())
                            .containsExactly("beta", "alpha");
                    assertThat(service.uniqueSink()).isNull();
                    assertThatThrownBy(() -> service.send("pay"))
                            .isInstanceOf(NoUniqueBeanDefinitionException.class);
                });
    }

    @Test
    void primaryCandidateCanMakeUniqueResolutionPossible() {
        runner.withUserConfiguration(PrimarySinkConfiguration.class)
                .run(context -> {
                    AuditService service = context.getBean(AuditService.class);

                    assertThat(service.uniqueSink()).isNotNull();
                    assertThat(service.uniqueSink().id())
                            .isEqualTo("preferred");
                    assertThat(service.send("pay"))
                            .isEqualTo("preferred:pay");
                });
    }

    @Test
    void customServiceMakesAutoConfiguredServiceBackOff() {
        runner.withUserConfiguration(CustomServiceConfiguration.class)
                .run(context -> {
                    assertThat(context.getBeansOfType(AuditService.class))
                            .containsOnlyKeys("customAuditService");
                });
    }
}
```

Run from the `object-provider-demo` directory using **Java 17+** and Maven:

```bash
mvn test
```

**Expected result:** all five tests succeed. Maven Surefire typically prints a summary equivalent to `Tests run: 5, Failures: 0, Errors: 0, Skipped: 0`. The tests have no `System.out.println`, so they do not depend on a specific business stdout line; Maven logs may vary by environment.

| Test | Observation | What it proves |
| --- | --- | --- |
| `missingOptionalSinkDoesNotPreventServiceCreation` | `AuditService` exists, returns `skipped:pay` or fallback `local:pay` | A provider can be injected when the target bean is missing; the chosen method determines how absence is handled. |
| `providerDoesNotForceLazySinkCreationAtInjectionTime` | Counter is 0 before the first `send`, 1 afterwards | Injecting a provider does not eagerly instantiate a `@Lazy` sink; the singleton is reused. |
| `multipleSinksCanBeStreamedButNotResolvedAsOne` | IDs in order `beta, alpha`; looking up a single sink throws an exception | `@Order` governs stream ordering, not selecting a single unique candidate. |
| `primaryCandidateCanMakeUniqueResolutionPossible` | `preferredSink` is selected | `@Primary` enables single-bean lookups to resolve a single candidate. |
| `customServiceMakesAutoConfiguredServiceBackOff` | Only `customAuditService` exists | `@ConditionalOnMissingBean` allows replacing the default consumer; this is a different role from the provider. |

### Why does the example work?

- `AuditService` only depends on `ObjectProvider<AuditSink>`, so Spring can create `AuditService` when no `AuditSink` exists at all.
- `LazySinkConfiguration.lazySink` has `@Lazy`. The context creates the `AtomicInteger` singleton normally, but the `lazySink` definition has not created an instance before code invokes the provider. The first call to `getIfAvailable()` creates the bean; subsequent calls receive the existing singleton.
- `MultiSinkConfiguration` registers two beans of the same type, each with a different bean name. Without `@Primary`, requesting **a single bean** is ambiguous; `orderedStream()` still retrieves both.
- `PrimarySinkConfiguration` has two beans with one marked `@Primary`, allowing the container to select the single candidate according to autowire rules.
- `CustomServiceConfiguration` is processed before auto-configuration and creates the application-supplied `AuditService` bean. The `@ConditionalOnMissingBean(AuditService.class)` condition in auto-configuration does not match; the default consumer backs off.
- The auto-configuration classes **nested inside the test file** are loaded directly by `AutoConfigurations.of`. In a **real starter**, the auto-configuration class must be listed by its fully qualified name in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

The test suite observes **bean resolution behavior**, as opposed to merely asserting that an annotation exists. Missing-bean, lazy, multi-candidate, and backoff branches are verified in isolated contexts.

## 6. Applying `ObjectProvider` in a real auto-configuration

### 6.1. Core feature bean is always present, integration bean is optional

For example, a library provides `JobDispatcher`, while extra logging only runs when a `JobEventPublisher` is present:

```java
// Architectural snippet in an auto-configuration class:
@Bean
@ConditionalOnMissingBean(JobDispatcher.class)
JobDispatcher jobDispatcher(ObjectProvider<JobEventPublisher> publisher) {
    return new JobDispatcher(publisher);
}
```

`JobDispatcher` is the library's bean, while `JobEventPublisher` is an extension point the app may declare. If the app has no publisher, the dispatcher stays alive and can skip the publish step or use a fallback by design. This is an **excerpt**; the related classes must be defined separately.

### 6.2. Do not look up from the provider inside the `@Bean` factory method if you want true deferral

Compare:

```java
@Bean
JobDispatcher eagerResolve(ObjectProvider<JobEventPublisher> provider) {
    // Look up immediately during JobDispatcher creation.
    JobEventPublisher publisher = provider.getIfAvailable();
    return new JobDispatcher(publisher);
}
```

with:

```java
@Bean
JobDispatcher onDemand(ObjectProvider<JobEventPublisher> provider) {
    // Only store the provider; JobDispatcher calls it when actually publishing.
    return new JobDispatcher(provider);
}
```

These are **two illustrative designs** for different constructors, not examples placed side by side to compile verbatim. In the first version, although it receives a provider, the code **immediately calls** `getIfAvailable()`: the benefit of deferred lookup is lost. The second version keeps the provider inside the consumer bean to resolve when needed.

### 6.3. A provider does not replace activation or classpath conditions

If the consumer bean **only makes sense when an external library is present**, you should still consider `@ConditionalOnClass` at the appropriate configuration level. `ObjectProvider<ThirdPartyService>` only handles a **missing bean** at runtime; it does not make the Java class `ThirdPartyService` disappear from the declared signature at class-loading time or make the Maven dependency unnecessary.

If lacking a publisher means the feature **should not exist at all**, `@ConditionalOnBean(JobEventPublisher.class)` at the class/`@Bean` level may be more appropriate. Only use `ObjectProvider` when the consumer remains useful without the dependency or needs to fetch the bean at a specific time.

If the starter provides a **replaceable default bean**, combine `@ConditionalOnMissingBean(Consumer.class)` to back off, and `ObjectProvider<Extension>` so the consumer retrieves extensions at runtime. The two mechanisms serve different purposes.

### 6.4. One application with multiple plugins

```java
public final class ExtensionPipeline {
    private final ObjectProvider<Extension> extensions;

    public ExtensionPipeline(ObjectProvider<Extension> extensions) {
        this.extensions = extensions;
    }

    public void execute(String input) {
        extensions.orderedStream().forEach(e -> e.apply(input));
    }
}
```

This is an **illustrative snippet** assuming an `Extension` interface containing `void apply(String)`. If plugins have `@Order` levels, the ordering of `orderedStream()` serves the pipeline. If there are no plugins, the stream is empty and nothing happens. If operations have side effects, you must decide error, rollback, and execution-order policies; the provider only handles finding the beans.

## 7. Points requiring caution

### 7.1. Missing bean vs. multiple beans

`getIfAvailable()` **only gracefully handles the missing-bean case**. If there are two `AuditSink` beans not resolved via `@Primary`/`@Qualifier`, it can throw `NoUniqueBeanDefinitionException`. Clear choices:

- Want exactly **one** sink: configure one bean, use `@Primary` or `@Qualifier` to select, or fail on ambiguity.
- Want **all** sinks to process: use `orderedStream()` or `stream()` and decide how to order them.
- Want **to process only if a unique one is selected**: `getIfUnique()`/`ifUnique(...)`, and explicitly handle the case where no valid candidate exists.

Do not catch broad exceptions and treat every bean creation error as "dependency missing". Constructor failures, missing config, or I/O errors during bean initialization are separate issues that should not be masked by a fallback.

### 7.2. Lazy initialization and bean lifecycle

`ObjectProvider` defers **when the dependency is requested**, without guaranteeing **that the target object has not been instantiated yet**. A non-lazy singleton may already have been created by Spring during refresh. If expensive initialization must be avoided, combine `@Lazy` or the right bean/scope design and test it like `AtomicInteger` in section 5.

If the dependency has **prototype scope**, each provider call can return a different object, so caching the result of `getObject()` in a field defeats the purpose of "on-demand retrieval every time". For request/session scope, retrieval must occur within an **active scope**, or use an appropriate proxy; calling outside a request may cause Spring to throw `ScopeNotActiveException`. Do not assume a scope error means the bean does not exist.

### 7.3. Dynamic lookup has limits

A provider is tied to the BeanFactory and each call performs **a fresh resolution based on the factory's state at that moment**. However, in a normal Boot application, bean definitions are established during startup. `ObjectProvider` is not a **plugin hot-reload** mechanism, nor does it guarantee you can arbitrarily add, remove, and overwrite bean definitions while singletons are already running.

### 7.4. Generic types and qualifiers

`ObjectProvider<AuditSink>` resolves by type `AuditSink`. If multiple beans exist, `@Qualifier` on the injection point can narrow the candidate set:

```java
// Constructor snippet inside a Spring-managed bean:
public AuditService(
        @Qualifier("criticalAuditSink")
        ObjectProvider<AuditSink> provider) {
    this.provider = provider;
}
```

If you use this example, import `org.springframework.beans.factory.annotation.Qualifier` and declare the `provider` field. A qualifier helps specify the intended bean; you still need to distinguish missing-bean errors from fallback choices. For generic types, Spring can use generic type information for matching; avoid erasing the type with raw `ObjectProvider`, which reduces resolution accuracy.

### 7.5. Avoid pointless lookups inside hot loops

`getObject()`/`getIfAvailable()` performs resolution at call time. When processing millions of events per second, only call on demand when it makes sense: sometimes you should build a pipeline once after the context has stabilized. However, **do not mistakenly cache** a dependency that is prototype-scoped or needs re-resolution. Base the decision on lifecycle and plugin-mutability requirements, not just the API name.

## 8. Diagnosing unexpected auto-configuration behavior

| Symptom | Likely cause | How to check/fix |
| --- | --- | --- |
| Context reports missing `AuditSink` right when creating `AuditService` | Consumer directly injects `AuditSink` elsewhere, or code calls `provider.getObject()` in constructor/`@Bean` | Inspect the call stack, keep the provider and call only when needed; choose `getIfAvailable()` if the dependency is optional. |
| `getIfAvailable()` throws `NoUniqueBeanDefinitionException` | Multiple beans of the same type, no single candidate under container rules | Use `@Qualifier`/`@Primary`, or iterate `orderedStream()` if the design supports multiple plugins. |
| Target bean was already created even though the service only holds a provider | Target bean is a non-lazy singleton pre-instantiated at context refresh | Mark the target bean `@Lazy` when appropriate and measure instance creation in tests. |
| `getIfUnique()` returns `null` even though beans of that type exist | Multiple candidates without a unique selection (or no matching bean exists) | Check bean names/types, `@Primary`, and qualifiers. |
| `stream()` has an unexpected order | `stream()` does not promise `@Order` sorting | Use `orderedStream()` along with appropriate order declarations. |
| `orderedStream()` is non-empty and plugins are created early | Consuming the stream may require instantiating each bean | Distinguish stream creation from terminal operations, and consider lifecycle/lazy semantics. |
| Custom consumer bean exists yet auto-config still creates default | `@ConditionalOnMissingBean` missing/wrong type, or wrong processing order | Check the condition and auto-configuration ordering; use `ApplicationContextRunner`. |
| Turned off `@ConditionalOnBean` but consumer should always exist | The condition drops the consumer bean entirely if the extension is missing | Use `ObjectProvider<Extension>` and design a no-op/fallback inside the consumer. |
| Request-scoped bean accessed outside a request | Scope is not active | Only access within a valid scope, or apply a scoped proxy. |

When investigating, enable `--debug` on the Boot application to inspect the **Condition Evaluation Report** (when auto-configurations match or back off). To analyze **runtime bean resolution**, use isolated tests, log bean names/types, and inspect the stack trace at the exact provider call. Do not conclude a lookup error is a condition failure if the target bean definition was registered but initialization failed.

## 9. Practice questions

**1.** Auto-configuration has `@Bean PaymentService paymentService(ObjectProvider<AuditSink> sinks)`. There is no `AuditSink`. Can `PaymentService` be created?  
**Answer:** Yes, provided no other condition or error prevents it. The provider object does not require an `AuditSink` bean at injection time.

**2.** In the constructor, `paymentService` immediately calls `sinks.getObject()` and currently there is no `AuditSink`. Is it still "optional"?  
**Answer:** Not at call time. `getObject()` requires an object and can throw `NoSuchBeanDefinitionException`.

**3.** Change `getObject()` to `getIfAvailable()`, with two beans of the same type and no `@Primary`. Will it definitely return `null`?  
**Answer:** No. The missing-bean case and the non-unique case are different; `getIfAvailable()` can throw `NoUniqueBeanDefinitionException`.

**4.** A sink is declared `@Bean @Lazy`. The service only holds `ObjectProvider<AuditSink>`. Must the sink be created when building the service?  
**Answer:** No. In the example context, the sink is created when the provider is called for the first time. Do not confuse this with non-`@Lazy` singletons, which may already be pre-instantiated early.

**5.** There are three plugins of the same type that need to run according to `@Order`. Should you use `getIfAvailable()` or `orderedStream()`?  
**Answer:** `orderedStream()` if the design allows **all three** to run; `getIfAvailable()` is aimed at **one** bean.

**6.** `getIfUnique()` sees two beans of the same type, one of which is `@Primary`. Does it necessarily return `null`?  
**Answer:** No. Spring can select the single primary candidate.

**7.** Does using `ObjectProvider` automatically prevent a starter from registering its default consumer bean when the application supplies a custom consumer?  
**Answer:** No. Use `@ConditionalOnMissingBean(Consumer.class)` on the auto-configuration for the backoff mechanism; the provider only resolves dependencies.

**8.** If you put `ObjectProvider<AuditSink>` in a constructor, can you remove the Maven dependency containing the `AuditSink` interface itself from the classpath?  
**Answer:** You cannot infer that. The type name still appears in the Java signature; you must design classpath conditions and split configurations appropriately if the integration is optional at the library level.

## Knowledge summary

`ObjectProvider<T>` lets you **inject a lookup handle** instead of forcing immediate injection of a `T` instance. Use `getIfAvailable()`/`ifAvailable(...)` when a dependency is optional; `getIfUnique()` when it should only be used if a unique candidate is determined; `getObject()` when the dependency is required at call time; and `stream()`/`orderedStream()` when the design supports multiple implementations. Distinguish **on-demand lookup** from **lazy bean initialization**, handle multi-bean ambiguity explicitly, and combine conditions in auto-configuration according to the contract.

### Official references

- Spring Framework 6.1 — `ObjectProvider<T>` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/ObjectProvider.html
- Spring Framework — `BeanFactory` and provider mechanisms: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/BeanFactory.html
- Spring Framework — `@Autowired` and optional injection: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration and `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html