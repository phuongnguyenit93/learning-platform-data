# Impact of Incomplete Type Information, `FactoryBean`, and Indirectly Registered Beans

## Objectives

When designing auto-configuration, you can easily run into a paradox: the application **has** a bean, yet `@ConditionalOnBean` reports it missing, or `@ConditionalOnMissingBean` still registers a fallback bean, causing duplicates. Three commonly overlooked causes are **insufficient type metadata**, **beans created by `FactoryBean`**, and **beans registered indirectly or too late**.

After this lesson, you will be able to distinguish a bean definition from an actual object, predict condition outcomes from declared types, accurately identify products of a `FactoryBean`, check bean registration timing, and write isolated tests for these scenarios. Examples target Spring Boot 3.3.x, Spring Framework 6.1, and Java 17+.

## 1. What Do Bean Conditions Actually "See"?

`@ConditionalOnBean`, `@ConditionalOnMissingBean`, and `@ConditionalOnSingleCandidate` belong to the group of conditions evaluated against **bean definitions already processed at evaluation time**. The condition inspects the information currently held by the `BeanFactory`; it does not wait for all singletons to be instantiated before inspecting their runtime types.

- `@ConditionalOnBean(T.class)`: matches only when a candidate satisfying requirement `T` already exists. If multiple types/names/annotations are specified, all requirements must be satisfied, though not necessarily by the same bean.
- `@ConditionalOnMissingBean(T.class)`: matches when **no** candidate satisfies the corresponding requirement yet. If an actual bean exists in practice yet the system cannot recognize it as `T`, the condition may report "missing."
- `@ConditionalOnSingleCandidate(T.class)`: requires an uniquely identifiable candidate; can match when multiple beans of type `T` exist if one is designated `@Primary`. It also depends on type info and timing.
- On a `@Bean` method, when `value`, `type`, or `name` is not specified, the default type to check is **the declared return type of the method**, not the runtime type of the returned object.
- The `search` parameter controls whether parent contexts are searched (default `SearchStrategy.ALL`); `name` checks by name, `annotation` checks annotations, and `parameterizedContainer` allows recognizing types wrapped in a specified generic container. These are distinct criteria; checking by name can help when the product type cannot yet be inferred, provided the name is a stable contract.

Mental model to keep in mind:

```text
Bean is defined / discovered
          |
          v
BeanDefinition registered in BeanFactory at time t?
          | no -> condition cannot see candidate yet
          v yes
Does container know what type/attributes the candidate has?
          | metadata too generic or undetermined
          v
OnBeanCondition matches type / name / annotation + search
          |
          +--> match / no match -> decides conditional definition registration
          |
          v
Later: instantiate objects, inject dependencies, use beans
```

**"Not seeing type `T`" does not mean "no bean exists,"** and **"having class `T` on the classpath" does not mean "a `T` bean exists."** `@ConditionalOnClass` answers the second question about the classpath, while bean conditions address the state of the `BeanFactory`.

## 2. Incomplete Type Info: Methods Returning an Interface, `Object`, or Raw Generics

Consider this example:

```java
interface PaymentGateway {
    String pay();
}
final class CardGateway implements PaymentGateway {
    @Override public String pay() { return "card"; }
}

@Configuration(proxyBeanMethods = false)
class UserConfig {
    @Bean
    PaymentGateway gateway() {
        return new CardGateway();
    }
}
```

When Spring processes the bean definition for `gateway`, the declared return type is `PaymentGateway`. A `@ConditionalOnBean(PaymentGateway.class)` condition has a basis to match, whereas `@ConditionalOnBean(CardGateway.class)` is **not guaranteed** to match merely because the method later returns `new CardGateway()`. Changing the signature to `CardGateway gateway()` lets the system recognize both `CardGateway` and the `PaymentGateway` interface.

Worse, if declared as `@Bean Object gateway() { return new CardGateway(); }`, most useful type signals disappear during the prediction phase. Conditions checking `CardGateway` or `PaymentGateway` may fail to match, causing a `@ConditionalOnMissingBean(PaymentGateway.class)` to register a default bean even though the user already provided a gateway.

This also happens with certain definitions created via factory methods, `Supplier<?>`, factories returning an overly broad interface, raw generics, proxies, or types known only after instantiation. Not all proxies are "invisible": what matters is **the type the container can infer at evaluation time**, together with assignability from that type to the requested type.

| Declaration / Available Metadata | Checking `PaymentGateway` | Checking `CardGateway` |
| --- | --- | --- |
| `@Bean CardGateway gateway()` | Basis to match | Basis to match |
| `@Bean PaymentGateway gateway()` | Basis to match | Not guaranteed |
| `@Bean Object gateway()` | Not guaranteed | Not guaranteed |
| BeanDefinition declares class `CardGateway` | Basis to match | Basis to match |
| Definition cannot describe type before instantiation | Not guaranteed | Not guaranteed |

The table describes **early recognition capability**, not an absolute guarantee for every lifecycle phase and container inference mechanism. Already-created singletons, generic `ResolvableType`, or extra metadata can cause later lookups to differ; a condition evaluated earlier **does not re-run automatically** just because the type later becomes clearer.

**How to handle:** declare `@Bean` with the most specific return type needed by consumers/conditions. If the API design intentionally exposes only an interface, write conditions against the interface rather than expecting the implementation type. Preserve generic types when conditions or injections rely on `ResolvableType`; avoid `Object` or raw types out of convenience.

## 3. `FactoryBean<T>`: The "Factory" Bean vs. the Factory's Product

`FactoryBean<T>` is a Spring interface used to **supply an object** through the container; it differs from the `@Bean` annotation and from a service class simply named "factory."

When a factory is registered under the name `gateway`:

- `context.getBean("gateway")` retrieves the **product** created by `FactoryBean#getObject()`.
- `context.getBean("&gateway")` retrieves the **FactoryBean instance itself**.
- For conditions checking the product type, what matters is the type the factory **declares**. `getObjectType()` plays an essential role; it can be called very early, before the factory finishes initializing.
- `getObjectType()` should return a stable, sufficiently specific type that can be determined **without instantiating the product**. If it returns `null`, Spring may have to rely on generics or other metadata; when it still cannot be inferred, type-based checks may treat the product type as undetermined. Returning a broad type from `getObjectType()` (`PaymentGateway.class`) also does not promise the product is `CardGateway`, even if `getObject()` actually returns one.

Example of a factory declaring its public product type as `PaymentGateway`:

```java
final class GatewayFactory implements FactoryBean<PaymentGateway> {
    @Override
    public PaymentGateway getObject() {
        return new CardGateway();
    }

    @Override
    public Class<?> getObjectType() {
        return PaymentGateway.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }
}

@Configuration(proxyBeanMethods = false)
class FactoryConfig {
    @Bean
    GatewayFactory gateway() {
        return new GatewayFactory();
    }
}
```

`@ConditionalOnBean(PaymentGateway.class)` can detect the product declared by the factory; `@ConditionalOnBean(CardGateway.class)` **cannot assume it can rely on** `getObject()` to discover the implementation. Do not "fix" this by forcing early product instantiation just to satisfy a condition; doing so can increase circular dependencies, touch unready beans, or trigger bootstrap side effects.

### 3.1. Product Metadata for Programmatic Registration

When a library registers a `FactoryBean`'s bean definition via API instead of `@Bean`, it can publish the product type through the `FactoryBean.OBJECT_TYPE_ATTRIBUTE` attribute on `BeanDefinition` when needed. Illustrative example of **code inside a registrar**, with a `registry` variable available:

```java
RootBeanDefinition definition = new RootBeanDefinition(GatewayFactory.class);
definition.setAttribute(FactoryBean.OBJECT_TYPE_ATTRIBUTE, PaymentGateway.class);
registry.registerBeanDefinition("gateway", definition);
```

In Spring Framework 6.1, this attribute's value must be a `Class<?>` or an appropriate `ResolvableType`; **do not put a class name string like `"com.example.PaymentGateway"`** into the attribute. Treat the metadata as an accurate commitment about the product; incorrect declarations will mislead both conditions and autowiring. If accurate generics or a good `getObjectType()` already exist, adding the attribute manually is usually unnecessary.

Do not conflate three questions: "is there a definition named `gateway`?", "what type of product is `gateway`?", and "what type of factory is `&gateway`?". A name-based condition and a type-based condition can yield different outcomes without contradiction.

## 4. Indirectly Registered Beans: Registration Source and **Timing** Matter More Than Syntax

Beans can come from `@ComponentScan`, `@Import`, `ImportBeanDefinitionRegistrar`, `BeanDefinitionRegistryPostProcessor`, bean definitions created by a library via API, or `registerSingleton(...)`. All of these are valid mechanisms, yet **none automatically guarantees** a condition will see the bean.

| Mechanism | What to Check |
| --- | --- |
| `@Component` + component scan | Did the scanner run before the condition? Does the definition expose the right class/type? Do not rely on accidental scan order. |
| `@Bean` inside `@Import`ed configuration | Was the configuration processed/registered yet? Does the `@Bean` signature reveal the checked type? |
| `ImportBeanDefinitionRegistrar` | At which phase is the registrar triggered? What `beanClass`, factory method, or `targetType` does the added definition carry? |
| `BeanDefinitionRegistryPostProcessor` | Does the registration callback run **before** the condition that needs it? A late-running post-processor can add beans after the condition has already decided. |
| `registerSingleton` or runtime registration | When is the instance added? If after condition evaluation, the condition does not re-evaluate automatically. |

Example using `ImportBeanDefinitionRegistrar` with an explicit type:

```java
public final class GatewayRegistrar implements ImportBeanDefinitionRegistrar {
    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata metadata, BeanDefinitionRegistry registry) {
        registry.registerBeanDefinition(
                "gateway", new RootBeanDefinition(CardGateway.class));
    }
}

@Configuration(proxyBeanMethods = false)
@Import(GatewayRegistrar.class)
class UserImportedConfig {
}
```

Corresponding imports (for placing this snippet inside a Spring program):

```java
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
import org.springframework.core.type.AnnotationMetadata;
```

`RootBeanDefinition(CardGateway.class)` carries a predictable type. **If** the registrar is processed before the condition, a `@ConditionalOnBean(CardGateway.class)` check can see the bean; if the registrar/processor only adds the definition after the condition runs, it still will not see it. Do not look solely at the final state ("the bean exists") to conclude it existed when the condition ran.

### 4.1. Distinguishing Registration Order from Initialization Order

In Spring Boot, user-defined beans are normally processed before auto-configuration; hence official documentation recommends using `@ConditionalOnBean`/`@ConditionalOnMissingBean` primarily **on auto-configuration**. If auto-config B depends on a bean provided by auto-config A, declare the registration relationship like this:

```java
@AutoConfiguration(after = GatewayAutoConfiguration.class)
class GatewayMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(PaymentGateway.class)
    GatewayMetrics gatewayMetrics() {
        return new GatewayMetrics();
    }
}
```

This is an **illustrative snippet**, assuming `GatewayAutoConfiguration` and `GatewayMetrics` already exist. `afterName` can be used to avoid direct class coupling. `@AutoConfigureAfter`/`@AutoConfigureBefore` express the same relationship.

`after` adjusts **definition processing order between auto-configurations**, **does not** force the bean to be instantiated earlier, and is no cure for wrong type metadata. `@DependsOn` controls initialization-time dependencies, not making a bean definition known earlier when conditions run. Ordinary `@Order` also does not replace this auto-config ordering relationship. If you use conditions on `@Bean` methods within the same configuration or across scanned classes in an unclear order, outcomes can depend on analysis timing; separate the source bean creator from the dependent auto-config and state before/after relationships explicitly.

## 5. Runnable Verification Practice: Five Scenarios

The exercise below uses Spring Boot 3.3.13, JUnit 5, and `ApplicationContextRunner`. It needs no web server or database connection; each test creates an isolated context. This is a **complete test example**, independent of the illustrative snippets above.

Create a Java 17+ Gradle project with this layout:

```text
bean-condition-lab/
  settings.gradle
  build.gradle
  src/test/java/demo/BeanConditionVisibilityTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'bean-condition-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}

test {
    useJUnitPlatform()
}
```

`src/test/java/demo/BeanConditionVisibilityTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.FactoryBean;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
import org.springframework.core.type.AnnotationMetadata;

import static org.assertj.core.api.Assertions.assertThat;

class BeanConditionVisibilityTest {

    interface Gateway {
        String id();
    }

    public static final class FastGateway implements Gateway {
        public FastGateway() {}
        @Override public String id() { return "fast"; }
    }

    @AutoConfiguration
    static class ProbeAutoConfiguration {

        @Bean
        @ConditionalOnBean(Gateway.class)
        String interfaceDetected() {
            return "interface visible";
        }

        @Bean
        @ConditionalOnBean(FastGateway.class)
        FastMarker concreteDetected() {
            return new FastMarker();
        }

        @Bean
        @ConditionalOnMissingBean(Gateway.class)
        Gateway fallbackGateway() {
            return () -> "fallback";
        }
    }

    static final class FastMarker {}

    @Configuration(proxyBeanMethods = false)
    static class BroadReturnConfig {
        @Bean
        Gateway gateway() {
            return new FastGateway();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ConcreteReturnConfig {
        @Bean
        FastGateway gateway() {
            return new FastGateway();
        }
    }

    static final class GatewayFactory implements FactoryBean<Gateway> {
        @Override public Gateway getObject() {
            return new FastGateway();
        }
        @Override public Class<?> getObjectType() {
            return Gateway.class;
        }
        @Override public boolean isSingleton() {
            return true;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class FactoryConfig {
        @Bean
        GatewayFactory gateway() {
            return new GatewayFactory();
        }
    }

    public static final class GatewayRegistrar
            implements ImportBeanDefinitionRegistrar {
        @Override
        public void registerBeanDefinitions(
                AnnotationMetadata metadata,
                BeanDefinitionRegistry registry) {
            registry.registerBeanDefinition(
                    "gateway", new RootBeanDefinition(FastGateway.class));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(GatewayRegistrar.class)
    static class ImportedConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(ProbeAutoConfiguration.class));

    @Test
    void noGatewayRegistersFallback() {
        runner.run(ctx -> {
            assertThat(ctx).hasBean("fallbackGateway");
            assertThat(ctx).doesNotHaveBean("interfaceDetected");
            assertThat(ctx).doesNotHaveBean("concreteDetected");
        });
    }

    @Test
    void interfaceReturnHidesConcreteImplementation() {
        runner.withUserConfiguration(BroadReturnConfig.class).run(ctx -> {
            assertThat(ctx).hasBean("interfaceDetected");
            assertThat(ctx).doesNotHaveBean("concreteDetected");
            assertThat(ctx).doesNotHaveBean("fallbackGateway");
        });
    }

    @Test
    void concreteReturnExposesBothTypes() {
        runner.withUserConfiguration(ConcreteReturnConfig.class).run(ctx -> {
            assertThat(ctx).hasBean("interfaceDetected");
            assertThat(ctx).hasBean("concreteDetected");
            assertThat(ctx).doesNotHaveBean("fallbackGateway");
        });
    }

    @Test
    void factoryBeanExposesItsDeclaredProductType() {
        runner.withUserConfiguration(FactoryConfig.class).run(ctx -> {
            assertThat(ctx).hasBean("interfaceDetected");
            assertThat(ctx).doesNotHaveBean("concreteDetected");
            assertThat(ctx).doesNotHaveBean("fallbackGateway");
            assertThat(ctx.getBean("gateway")).isInstanceOf(FastGateway.class);
            assertThat(ctx.getBean("&gateway"))
                    .isInstanceOf(GatewayFactory.class);
        });
    }

    @Test
    void importedRegistrarMakesConcreteTypeVisible() {
        runner.withUserConfiguration(ImportedConfig.class).run(ctx -> {
            assertThat(ctx).hasBean("interfaceDetected");
            assertThat(ctx).hasBean("concreteDetected");
            assertThat(ctx).doesNotHaveBean("fallbackGateway");
        });
    }
}
```

Run in the project directory using an installed Gradle:

```bash
gradle test --tests demo.BeanConditionVisibilityTest
```

If the project includes Gradle Wrapper, use `./gradlew test --tests demo.BeanConditionVisibilityTest` on macOS/Linux or `.\gradlew.bat test --tests demo.BeanConditionVisibilityTest` on Windows. JDK 17+ and permission to download dependencies on the first run are required. **Expected result** is that the `test` task succeeds with 5 passing tests; actual logs may vary by Gradle configuration, so do not assume fixed stdout.

The five tests simultaneously demonstrate the key points: when no bean exists, the fallback is registered; an interface return type does not promise recognition of the implementation; a concrete return type makes it visible to the condition; `FactoryBean` publishes a product type distinct from the factory itself; and an `ImportBeanDefinitionRegistrar` registers an explicit type early enough for auto-configuration to recognize it. If you change `getObjectType()` to `null` as an experiment, remember that the generic `FactoryBean<Gateway>` can still provide inference metadata: **do not take that single case as proof that Spring has no knowledge of the type at all**.

## 6. Systematic Diagnosis in Real Scenarios

When a condition gives an unexpected result, ask in this order:

1. **Is it the right condition?** `@ConditionalOnClass` needs the class on the classpath; `@ConditionalOnBean` needs a candidate in `BeanFactory`. Is the condition matching `name`, `type`, `annotation`, or a generic container? Is `search = SearchStrategy.CURRENT` configured, causing beans in a parent context to be ignored?
2. **Had the bean been registered at evaluation time?** Who creates the bean definition? User configuration, another auto-config, `@Import`, a registrar, or a post-processor? Verify `@AutoConfiguration(after = ...)` relationships if there are dependencies between auto-configs. Do not patch with `@DependsOn` when the issue occurs before instantiation.
3. **Which type can the container predict?** Check the `@Bean` return type, `beanClass`, `ResolvableType`, erased generics, type published by a factory method, `FactoryBean#getObjectType()`, and `FactoryBean.OBJECT_TYPE_ATTRIBUTE`. Compare the requested type against **the type visible before instantiation**, not just `instance.getClass()` at the end of startup.
4. **Is it the product or the factory?** Try distinguishing `"gateway"` from `"&gateway"` in a `FactoryBean` context. Do not confuse `getObjectType()` with the factory's `getClass()`.
5. **Was the candidate eligible to be counted?** The condition may filter out ineligible candidates (such as beans not eligible for autowiring), ignore certain types via `@ConditionalOnMissingBean`'s `ignored`/`ignoredType`, or be affected by the context hierarchy.
6. **Gather evidence from the condition report.** In a Spring Boot application, enable debugging with `--debug` or `debug=true`; inspect the **Conditions Evaluation Report** in the logs. If using Actuator and the endpoint is intentionally enabled/exposed, `/actuator/conditions` provides positive/negative matches and reasons. Find the exact configuration and `OnBeanCondition` message about "found/did not find" at evaluation time.
7. **Reproduce with a small test.** Use `ApplicationContextRunner` with `withUserConfiguration(...)` and `AutoConfigurations.of(...)` to vary bean definition kinds, return types, factories, and auto-config order one by one. Assert both the case where the user bean beats the fallback and the case where the fallback must appear.

To observe types **without intentionally instantiating factories/products**, you can inspect the bean factory in a controlled diagnostic check:

```java
String[] names = beanFactory.getBeanNamesForType(
        PaymentGateway.class, true, false);
System.out.println(java.util.Arrays.toString(names));
```

This is an **illustrative snippet** inside a function that has a `beanFactory` variable of type `ListableBeanFactory`. The parameter `allowEagerInit=false` helps avoid eager initialization for type inference. The result at one moment **is not equivalent** to the list of all objects the context may create later; record the invocation phase and compare it with the condition report. Do not call `getBean(...)` in bulk during debugging just to force conditions to "see" types.

## 7. Common Mistakes and Corresponding Fixes

| Symptom | Common Cause | Proper Layer Fix |
| --- | --- | --- |
| `@ConditionalOnMissingBean(FastGateway.class)` still creates default despite `@Bean Gateway gateway()` | Declared type is only the interface | Match by `Gateway` if that is the contract; or return `FastGateway` if conditions need the implementation |
| `FactoryBean` exists yet `@ConditionalOnBean(Product.class)` does not match | `getObjectType()` too broad/`null`, insufficient generics or metadata | Expose an accurate, stable product type available early; when registering programmatically, set proper metadata |
| Confusing the factory bean with its product | Looking up name `gateway` as if its class were `GatewayFactory` | Distinguish `gateway` (product) and `&gateway` (factory); write conditions against the appropriate type |
| Bean exists in context after startup yet earlier condition said "missing" | Definition registered after condition evaluation time | Move registration earlier, declare auto-config ordering, or restructure condition scope |
| Added `@AutoConfiguration(after=...)` yet bug persists | Type is unpredictable or source is not actually an ordered auto-config | Check metadata and registration source; `after` only helps the condition see already-processed definitions |
| Calling `getBean()` manually to make condition match | Using eager initialization as a workaround | Remove the workaround, fix type metadata and registration order; verify with context runner |

## 8. Checklist for Resilient Auto-Configuration Design

- Check only the bean types your library API genuinely needs; prefer a stable interface when that is the user contract, and use an implementation when the condition specifically requires the implementation.
- On `@Bean` methods, return a type specific enough for injection and conditions; avoid `Object` signatures or raw generics where type prediction matters.
- With `FactoryBean`, implement a meaningful `getObjectType()` early without heavy side effects; keep it consistent with `getObject()`'s product.
- With beans created via API/registrars, supply a sufficiently clear bean class/`ResolvableType` or factory product type; avoid malformed product type attributes.
- Place presence/missing conditions primarily in auto-configs; order dependent auto-configs with `after`/`before` and verify with tests, rather than relying on accidental component-scan order.
- Test at least three cases: no user bean, user bean with a clear exposed type, and user bean with a broad type or created via a factory/registrar.
- When a condition behaves unexpectedly, read the **match reason** and inspect **type/timing** before changing business logic.

**Core takeaway:** bean condition outcomes reflect **the definitions processed and types recognizable at evaluation time**. `FactoryBean` adds a layer distinguishing factory from product; indirect registration adds ordering variables. Writing clear metadata and testing across timing scenarios makes fallbacks and auto-configuration integrations predictable.

## Official Documentation

- Spring Boot 3.3 — Creating Your Own Auto-configuration (bean conditions, return types, ordering, `ApplicationContextRunner`): https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — `@ConditionalOnBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
- Spring Boot 3.3 — `@ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Framework 6.1 — `FactoryBean`: https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/beans/factory/FactoryBean.html
- Spring Framework — Using the `@Bean` Annotation (limits of broad return types): https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html
