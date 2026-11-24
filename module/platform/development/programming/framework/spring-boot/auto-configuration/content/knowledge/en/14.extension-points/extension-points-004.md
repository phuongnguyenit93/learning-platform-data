# Applying multiple customizers in a deterministic order

## 1. What kind of extension point is a customizer?

In Spring Boot Auto-Configuration, a *customizer* is typically a bean encapsulating an operation that customizes an object being built by the framework or by an auto-configuration. Instead of each module recreating the entire object from scratch, a module can register a bean implementing a callback interface, while **the owner of the target object** gathers and invokes those callbacks.

Real-world examples in Spring Boot 3.3:

- `WebServerFactoryCustomizer<T>` customizes the web server factory before the web server starts.
- `Jackson2ObjectMapperBuilderCustomizer` customizes `Jackson2ObjectMapperBuilder` while preserving most of Boot's Jackson auto-configuration.
- Internal libraries can define `PaymentClientCustomizer`, `PipelineCustomizer`, or a similar interface, and apply the list of extension beans when constructing the main object.

When **multiple customizers** act on the same object, ordering can directly affect the outcome: customizer A sets a timeout, B overrides the timeout; customizer X registers a processing step, Y expects that step to exist. Therefore, you must define: **who collects the customizers, who determines the order, when callbacks run, and how conflicts are handled**.

Objectives of this lesson:

1. Understand `@Order`, `Ordered`, and how Spring sorts multiple beans in a deterministic order.
2. Know how to collect and apply them via `ObjectProvider<T>.orderedStream()` or a Spring-injected bean list.
3. Distinguish **customizer application order** from **auto-configuration registration order** and **bean instantiation order**.
4. Design extension points with clear contracts, avoiding reliance on class-scanning order or duplicate priorities.
5. Verify with a standalone test program using Java 17+, Spring Boot 3.3, and `ApplicationContextRunner`.

## 2. Why does ordering produce different results?

Suppose a builder object holds configuration:

```text
mode = "standard"
interceptors = []
```

Three customizers operate on the builder:

| Customizer | Action | Intent |
| --- | --- | --- |
| `DefaultModeCustomizer` | `mode = "basic"` | Set default |
| `AddAuditCustomizer` | Append `"audit"` to interceptors | Register additional feature |
| `OverrideModeCustomizer` | `mode = "strict"` | Override final configuration |

If `DefaultModeCustomizer` runs before `OverrideModeCustomizer`, the final `mode` is `strict`. If reversed, `mode` becomes `basic`. For list additions, element order is also part of the observable behavior. **There is no universal rule like "the last customizer always wins"**: a later one might overwrite a property, only append data, or fail due to a broken invariant. The result depends on the target object's contract and how each callback mutates it.

This yields two separate responsibilities:

- **The customizer author** assigns an appropriate priority and writes callbacks that only touch what they own.
- **The customizer consumer** must fetch the right beans, sort them according to the chosen contract, and invoke them sequentially on the right target object.

Merely putting `@Order` on beans without the consumer sorting the list or invoking callbacks **creates no execution sequence whatsoever**.

## 3. Spring's ordering mechanisms

### 3.1. `@Order`: smaller numbers run earlier

Spring Framework provides `org.springframework.core.annotation.Order`:

```java
@Bean
@Order(10)
PipelineCustomizer normalizeCustomizer() {
    return draft -> draft.addStep("normalize");
}

@Bean
@Order(30)
PipelineCustomizer auditCustomizer() {
    return draft -> draft.addStep("audit");
}
```

This is a **code snippet** placed in a `@Configuration` class, assuming `PipelineCustomizer` is a functional interface and `draft` has an `addStep` method. When collected by a mechanism **that respects ordering**, the bean with order `10` is applied before the bean with order `30`. The general rule is **the lower the numeric value, the higher the priority**.

Order values can be negative, zero, or positive. Spring provides the constants `Ordered.HIGHEST_PRECEDENCE` and `Ordered.LOWEST_PRECEDENCE`. Avoid arbitrarily assigning extreme values to every customizer: doing so makes coordination across modules difficult. Reserve clearly published ranges for each phase—for example, `0–99` for defaults, `100–199` for business transformations, `200–299` for final checks—if the extension point you own needs them. This is a **design convention**, not a Spring requirement.

`@Order` can be placed on a **component class** or a **`@Bean` method**. `@Order` on a `@Bean` method is useful when the same implementation class produces multiple beans that each need a distinct priority.

### 3.2. `Ordered`: order value obtained from the instance

Instead of an annotation, a class can implement `org.springframework.core.Ordered`:

```java
final class OrderedAuditCustomizer implements PipelineCustomizer, Ordered {

    @Override
    public int getOrder() {
        return 30;
    }

    @Override
    public void customize(PipelineDraft draft) {
        draft.addStep("audit");
    }
}
```

This code illustrates **a class depending on the application's `PipelineCustomizer` and `PipelineDraft` types**; `org.springframework.core.Ordered` must be imported in a real file. This approach can fit when priority is part of the implementation or must be determined from constructor parameters. Because Spring compares instantiated objects, collecting and sorting can **instantiate the customizers**; do not assume this is purely a metadata operation.

If a bean has both `Ordered` and `@Order`, clearly identify which order source the comparator uses and avoid declaring two conflicting values. For an extension point you author, it is usually best to choose **one consistent way to declare priority** per implementation.

### 3.3. `PriorityOrdered`: special priority group

`PriorityOrdered` extends `Ordered` and is treated by Spring as a **group with higher precedence** than beans implementing only `Ordered`. Therefore, you cannot simply take all `getOrder()` numbers and treat the whole list as one plain numeric comparison when mixing `PriorityOrdered` and `Ordered`. This is typically a contract for framework infrastructure such as post-processors. For ordinary application customizers, `@Order` or `Ordered` is sufficient and simpler.

### 3.4. Undeclared order and ties

Customizers without a specified priority are generally treated as low priority according to the comparator's rules. **Do not rely on component-scan order, file names, bean names, or method declaration order to control callbacks.**

If two customizers have the same priority, do not treat their relative order as a stable contract across Spring versions, profiles, or import styles. When relative order between them changes the outcome, **assign distinct values**, or combine tightly coupled operations into one customizer. You can also build an explicit secondary tie-breaker in your own extension point, provided you publish and test that contract.

## 4. Collecting and applying in the right order

### 4.1. Recommended for auto-configuration: `ObjectProvider<T>.orderedStream()`

`ObjectProvider<T>` lets you retrieve beans of the same type on demand. The call:

```java
customizers.orderedStream()
    .forEach(customizer -> customizer.customize(builder));
```

returns a **sorted sequential Stream** using the BeanFactory's shared order comparator. In a standard Spring application context, this comparator considers `Ordered` and `@Order`. Calling `forEach` sequentially on that stream invokes each customizer in sorted order. Each callback receives **the same builder** to mutate its state before the builder creates the final object.

Comparing the approaches:

| Collection method | Guarantees `@Order`/`Ordered` priority? | Notes |
| --- | --- | --- |
| `ObjectProvider<T>.orderedStream()` | **Yes, per the factory's order comparator** | Expresses intent most clearly for an optional customizer list |
| Inject `List<T>` or `T[]` via Spring | **Yes, under standard collection autowiring** | Spring sorts matching beans by order metadata |
| `ObjectProvider<T>.stream()` / `iterator()` | **Does not guarantee priority order** | Usually close to registration order, not an application contract |
| Calling `getBeansOfType()` and iterating `Map.values()` | **Does not automatically guarantee `@Order` order** | If using a map, you must sort properly before invoking callbacks |

For a Spring-injected list, you can write:

```java
@Bean
Pipeline pipeline(List<PipelineCustomizer> customizers) {
    PipelineDraft draft = new PipelineDraft();
    customizers.forEach(customizer -> customizer.customize(draft));
    return draft.build();
}
```

This is a **code snippet** using application classes. Spring sorts beans matching the type by ordering metadata when autowiring the list. Using `ObjectProvider<PipelineCustomizer>` is often convenient in auto-configuration because it makes clear that **there might be zero customizers**, while deferring resolution until actually needed.

### 4.2. Application timing is determined by the consumer

There are two distinct moments:

1. When Spring registers the customizers' **bean definitions**.
2. When code invokes `customize(target)` on the resolved **bean instances**.

`@Order` determines relative position in the collection sorted by Spring; it **does not trigger callbacks** at definition registration time. If customizers are normal beans, their constructors may run before or after another customizer according to the dependency graph, but the callback only runs when the consumer invokes it.

Examples to distinguish:

- `@AutoConfiguration(after = OtherAutoConfiguration.class)`: affects **auto-configuration / bean definition processing order**, especially when `@ConditionalOnBean` and `@ConditionalOnMissingBean` care whether a definition already exists.
- `@DependsOn("otherCustomizer")`: affects **bean instance initialization order** by dependency, and does not automatically sort `customize()` execution.
- `@Order(10)` on a customizer: describes **priority order when components are sorted**; the consumer must respect that order.
- `@Primary`: selects one preferred bean when single-value injection has multiple candidates; **not** a way to exclude other customizers from an `ObjectProvider<T>` list.

Remember that `@Order` on a **`@Configuration` class** only pertains to evaluating configuration classes; it **does not automatically propagate** the order value to all `@Bean` methods inside that class. To give each `@Bean`-created customizer an order, place `@Order` on the method itself or the implementation, or use `Ordered`.

## 5. Extension point contract when multiple customizers exist

Suppose you own `PipelineCustomizer` in an internal starter. The contract should clearly answer:

1. **Target object:** do callbacks mutate a builder/configuration before `build()` or can they mutate a live object? Applying before building/freezing the main object is recommended.
2. **Mutation style:** "last-write-wins" setters, appending to a collection, or read-only validation? Do not mix these behaviors without defining precedence.
3. **Ordering:** are `@Order`, `Ordered`, or another fixed order supported? What is the default priority? Does a tie between two customizers matter?
4. **Bean sources:** collect all beans matching the type, or filter with qualifiers/`@ConditionalOnProperty`? Beans from unimported modules will not appear in the list.
5. **Invocation timing:** apply once when building a singleton, per request, or on every prototype creation? Avoid confusing "bean was created" with "callback already ran".
6. **Error handling:** if a callback throws an exception, fail fast at startup or ignore? For critical infrastructure configuration, failing fast with a clear message is usually easier to reason about than silently ignoring.
7. **Invariants:** after all customizers run, validate required values, duplicate configuration, interceptor counts, or performance limits.
8. **Idempotency:** if a target can be customized multiple times, is a callback safe when invoked again? Avoid appending the same interceptor repeatedly without idempotency.

This set of rules enables extensibility without forcing users to replace the entire auto-configuration or rely on internal bean names. When multiple customizers touch the same property, you can publish a "defaults first, fine-tuning next, validation last" order. If a behavior must guarantee **nothing can overwrite it later**, do not treat `@Order` as absolute security: enforce invariants upon completion, or design the builder API to restrict unauthorized changes.

## 6. Complete Java 17+ example using Spring Boot 3.3

The following test simulates an auto-configuration that supplies a default `Pipeline`. The user registers three customizers with orders `30`, `10`, and `20` **out of ascending order** in source code. The auto-configuration retrieves all customizers via `ObjectProvider.orderedStream()` and applies them to a `PipelineDraft` before building `Pipeline`.

Create `src/test/java/example/customizers/OrderedCustomizerTests.java` in a project with Java 17+, Spring Boot 3.3.x, `spring-boot-starter-test` (JUnit Jupiter, AssertJ), and JUnit Platform:

```java
package example.customizers;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

import static org.assertj.core.api.Assertions.assertThat;

class OrderedCustomizerTests {

    @FunctionalInterface
    interface PipelineCustomizer {
        void customize(PipelineDraft draft);
    }

    static final class PipelineDraft {
        private final List<String> stages = new ArrayList<>();
        private String mode = "standard";

        void addStage(String name) {
            stages.add(name);
        }

        void setMode(String mode) {
            this.mode = mode;
        }

        Pipeline build() {
            return new Pipeline(List.copyOf(stages), mode);
        }
    }

    static final class Pipeline {
        private final List<String> stages;
        private final String mode;

        Pipeline(List<String> stages, String mode) {
            this.stages = stages;
            this.mode = mode;
        }

        List<String> stages() {
            return stages;
        }

        String mode() {
            return mode;
        }
    }

    @AutoConfiguration
    static class PipelineAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(Pipeline.class)
        Pipeline pipeline(ObjectProvider<PipelineCustomizer> customizers) {
            PipelineDraft draft = new PipelineDraft();
            customizers.orderedStream()
                    .forEach(customizer -> customizer.customize(draft));
            return draft.build();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomizersConfiguration {

        @Bean
        @Order(30)
        PipelineCustomizer finalCustomizer() {
            return draft -> {
                draft.addStage("final");
                draft.setMode("fast");
            };
        }

        @Bean
        @Order(10)
        PipelineCustomizer baseCustomizer() {
            return draft -> {
                draft.addStage("base");
                draft.setMode("base");
            };
        }

        @Bean
        @Order(20)
        PipelineCustomizer validateCustomizer() {
            return draft -> draft.addStage("validate");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserPipelineConfiguration {
        @Bean
        Pipeline pipeline() {
            return new Pipeline(List.of("user"), "custom");
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            PipelineAutoConfiguration.class));

    @Test
    void appliesAllCustomizersInOrder() {
        runner.withUserConfiguration(CustomizersConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Pipeline.class);
                    Pipeline pipeline = context.getBean(Pipeline.class);
                    assertThat(pipeline.stages())
                            .containsExactly("base", "validate", "final");
                    assertThat(pipeline.mode()).isEqualTo("fast");
                });
    }

    @Test
    void noCustomizersKeepsDefaultValues() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(Pipeline.class);
            Pipeline pipeline = context.getBean(Pipeline.class);
            assertThat(pipeline.stages()).isEmpty();
            assertThat(pipeline.mode()).isEqualTo("standard");
        });
    }

    @Test
    void userPipelineMakesDefaultAutoConfigurationBackOff() {
        runner.withUserConfiguration(
                    UserPipelineConfiguration.class,
                    CustomizersConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Pipeline.class);
                    Pipeline pipeline = context.getBean(Pipeline.class);
                    assertThat(pipeline.stages()).containsExactly("user");
                    assertThat(pipeline.mode()).isEqualTo("custom");
                });
    }
}
```

### 6.1. Running the tests

In a project directory with Gradle wrapper configured for JUnit Platform:

```bash
./gradlew test --tests example.customizers.OrderedCustomizerTests
```

If using Maven with Surefire/JUnit 5:

```bash
./mvnw -Dtest=OrderedCustomizerTests test
```

**Expected result:** three tests PASS. Gradle/Maven stdout depends on version and logging configuration, so no fixed output line is asserted.

### 6.2. Why does the code work this way?

**Test `appliesAllCustomizersInOrder`:** the three beans are declared in source order `final`, `base`, `validate`, but `orderedStream()` sorts by `@Order`: `10 → 20 → 30`. Hence `stages()` equals `["base", "validate", "final"]`. `baseCustomizer` sets mode `base`; `finalCustomizer` runs later and sets mode `fast`, so the final result is `fast`. The test checks both **callback order** and **property override**.

**Test `noCustomizersKeepsDefaultValues`:** with no `PipelineCustomizer` beans present, `ObjectProvider.orderedStream()` yields an empty stream; the default `Pipeline` is still created with `mode = "standard"` and an empty stage list. This is the benefit of an optional extension point: the starter works when nobody customizes it.

**Test `userPipelineMakesDefaultAutoConfigurationBackOff`:** the application declares `Pipeline` itself, so `@ConditionalOnMissingBean(Pipeline.class)` excludes the default pipeline in auto-configuration. The user-registered customizers are still beans, but because **no default pipeline builder invokes them**, they are not applied to the user-created `Pipeline` instance. This is an important contract: customization only happens in the callback consumer; it does not "auto-inject" into arbitrary objects of the same type.

### 6.3. Meaning of the annotations

- `@AutoConfiguration` marks the part supplying the default object; in the test, it is explicitly imported via `AutoConfigurations.of(...)`.
- `@ConditionalOnMissingBean(Pipeline.class)` lets auto-configuration back off when the application supplies the final product. This is a bean definition condition, unrelated on its own to callback execution order.
- `@Configuration(proxyBeanMethods = false)` declares the user's customization beans.
- `@Bean @Order(...)` sets the order on **each customizer bean**.
- `ObjectProvider<PipelineCustomizer>` collects all beans matching the type; `orderedStream()` provides the right order and `forEach` applies them one by one.
- `List.copyOf(stages)` creates an immutable copy of the stage list in the output object, preventing a mutable builder from altering configuration after `build()`.

The test example above is a complete Java file in an appropriate Spring Boot test project. It **does not require** registering the nested auto-configuration in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` because the test supplies it explicitly. For a production starter, auto-configurations are discovered via that imports file per Spring Boot 3.3 documentation.

## 7. In real Spring Boot: multiple web server and Jackson customizers

### 7.1. `WebServerFactoryCustomizer`

Spring Boot 3.3 provides `WebServerFactoryCustomizer<T extends WebServerFactory>` so extension beans receive the web server factory before the server starts. Example declaring an application customizer for a servlet web server:

```java
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.servlet.server.ConfigurableServletWebServerFactory;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(100)
public class MyServerPortCustomizer
        implements WebServerFactoryCustomizer<ConfigurableServletWebServerFactory> {

    @Override
    public void customize(ConfigurableServletWebServerFactory factory) {
        factory.setPort(9090);
    }
}
```

This is a **complete class in a Spring Boot 3.3 Servlet project**; save it as `MyServerPortCustomizer.java` and add the project's package. It does not need to call `customize` itself: Spring Boot has a mechanism that consumes beans implementing this interface. In Boot 3.3 documentation, auto-configured web-server customizers typically have order `0` and are processed before user customizers unless users specify a different order. `@Order(100)` here intentionally expresses "runs after order 0" per the sorting contract.

**Lifecycle warning:** `WebServerFactoryCustomizer` is typically invoked by `WebServerFactoryCustomizerBeanPostProcessor` at a very early stage of the `ApplicationContext`. The Spring Boot API itself notes that dependencies should preferably be retrieved lazily rather than forcing early autowiring of complex beans into the customizer. Do not perform side effects such as network calls or accessing unready infrastructure beans inside this callback.

If two customizers both call `factory.setPort(...)`, the later setter call usually determines the final port, though multiple modules should not contend over the same property. Use `server.port` when a simple port configuration suffices; only use a customizer when you genuinely need programmatic access to the factory.

### 7.2. `Jackson2ObjectMapperBuilderCustomizer`

In Spring Boot 3.3, `Jackson2ObjectMapperBuilderCustomizer` lets you modify Jackson's builder configuration while still using the default auto-configuration flow. There can be multiple customizer beans: choosing date formats, registering serializers/modules, or tuning naming strategies. If two customizers set **the same property** on the builder, application order can change the outcome.

Example illustrating intent:

```java
@Bean
@Order(100)
Jackson2ObjectMapperBuilderCustomizer useSnakeCase() {
    return builder -> builder.propertyNamingStrategy(
            com.fasterxml.jackson.databind.PropertyNamingStrategies.SNAKE_CASE);
}
```

This snippet needs imports for `org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer`, `@Bean`, and `@Order`; place it in an appropriate configuration class with Jackson on the classpath. Do not rely on an arbitrary `@Order` value to beat every library customizer: check the actual order, defaults, and Spring Boot contract. You should verify the **final ObjectMapper** with serialization tests.

If your only need is configuring a supported property such as `spring.jackson.property-naming-strategy`, prefer the explicit property. Customizers fit transformations hard to express in properties or when genuinely building an extension point.

### 7.3. Difference from customizers you define yourself

Spring Boot knows about and automatically calls the customizer types **that Boot itself has support for**. A custom `MyCustomizer` interface you define **will not be called automatically** just because beans implement it with `@Order`. You must write the consumer—for example inside a `@Bean` factory method—to collect and apply callbacks via `orderedStream()` as shown in the test.

## 8. Handling multiple customizers modifying the same setting

Do not treat ordering as the sole solution to every conflict. Identify the operation type:

| Operation type | Example | What to watch out for |
| --- | --- | --- |
| Reassigning the same property | A sets timeout `5s`, B sets `10s` | "Last write wins" usually holds for simple setters; publish the policy |
| Appending elements | A adds `AuthFilter`, B adds `AuditFilter` | List order can affect request flow; check for duplicate elements |
| Registering handlers by key | A and B both register key `json` | Detect duplicate keys or define explicit override rights |
| Reading and validating | C checks timeout within allowed range | Should run after related mutations to avoid validating incomplete state |
| Finalizing the builder | D calls `build()` or locks configuration | Subsequent customizers may fail to modify; define the finalize stage clearly |

A clean pattern is a **staged sequence**:

1. Default customizers establish safe baselines.
2. Optional customizers configured via properties.
3. Business customizers add interceptors/handlers.
4. A validation/finalize step **called separately by the builder owner** after all callbacks to verify invariants.

Even if you could give a validator the highest order number, a finalize step separate from the customizer set makes it easier to guarantee that no customizer modifies state after validation. For the same critical key, you can fail fast if two callbacks contend to set it, rather than resolving conflicts with an arbitrary `@Order` number.

### Idempotency

If the consumer might invoke customizers multiple times on the same builder, callbacks that append to a list can create duplicate elements. For example:

```java
void customize(PipelineDraft draft) {
    draft.addStage("audit");
}
```

This is a simple snippet, not idempotent. The design may require the builder to check `contains("audit")` or store stages by unique key. You do not need to force idempotency on every callback if the contract guarantees each builder is customized once; however, make that clear so extension authors do not misunderstand.

## 9. Ambiguous ordering and how to verify

### 9.1. Typical mistakes

- **Only putting `@Order` on customizer classes while manually iterating `getBeansOfType().values()`:** a map does not guarantee `@Order` priority. Use `orderedStream()` or sort with a proper comparator.
- **Inferring order from `@Bean` declaration order:** source order is not a callback invocation contract.
- **Confusing `@Order` with `@DependsOn`:** the former sorts items in the collection processed by the consumer; the latter specifies **instance initialization** order.
- **Using `@AutoConfiguration(after=...)` to control callbacks:** this orders auto-configuration processing and affects bean definition conditions, without automatically changing the application order of a customizer list.
- **Putting `@Order` on a `@Configuration` class thinking beans inside inherit it:** each customizer bean must carry its own order if needed.
- **Using `@Primary` to "pick a winning customizer":** when a consumer collects all customizers by type, `@Primary` does not remove the other beans. It primarily helps select a candidate for single-value dependency injection.
- **Leaving two customizers with the same order and expecting stable output:** use distinct values or a secondary ordering contract.
- **Assigning absolute order values without checking the library in use:** an extension point may reserve order ranges or apply extra priority handling. Always check the API and test.
- **A customizer depending on the very object being built:** can cause circular dependencies if the consumer must instantiate the customizer to build that object. Separate configuration input from the resulting product.
- **Running callbacks too early:** especially with web server factories, avoid forcing complex infrastructure initialization while a BeanPostProcessor is running.
- **Assuming startup success is enough:** test the **final** state of the builder or product after all customizers have been applied.

### 9.2. Testing the right thing to prove

First verify that the customizer bean is registered and recognized under the expected type. Next test **the order in which callbacks are invoked**, not just customizer constructor order. To observe this directly, you can record callback names into a `List<String>` in tests like the `Pipeline` lesson above. Finally, verify the **resulting state** actually used by the system, such as mode, timeout, interceptor list, or serialized JSON.

A minimal test suite for a team-authored extension point should include:

1. No customizers → default object is still created.
2. One customizer → expected modification is applied.
3. Multiple customizers with different orders → application order and final state are accurate.
4. Two customizers modifying the same property → conflict policy is verified.
5. Adding or removing customizers via conditional beans → consumer collects only matching beans.
6. User-defined product present and auto-configuration backs off → clear understanding of whether customizers are still consumed.

`ApplicationContextRunner` fits starters/auto-configuration well because it creates an isolated context per case and makes asserting bean presence/absence and final object state straightforward. Use `ConditionEvaluationReport` when suspecting a customizer was not registered due to a condition; use callback tracing when suspecting ordering. Those two kinds of evidence solve two different classes of problems.

## 10. Self-check questions

1. Three customizers are annotated `@Order(200)`, `@Order(10)`, `@Order(100)`. If the consumer uses `ObjectProvider.orderedStream()`, what is the application order? **10, 100, 200**.
2. Two beans both have `@Order(10)`, and the outcome depends on which runs last. What should you do? **Give them different order values or combine dependent operations into one customizer; do not rely on source declaration position**.
3. Does `@Order(5)` on a customizer force its constructor to run before a bean with order 10? **No.** It describes sorting order, and does not directly control singleton startup.
4. A team added `@AutoConfiguration(after = OtherConfig.class)` yet callbacks still do not run in the expected order. Why? **`after` orders auto-configuration definitions, not customizer application order.**
5. Does `ObjectProvider.stream()` make the same ordering guarantee as `orderedStream()`? **No.** `orderedStream()` states a sorting contract; `stream()` does not guarantee ordering.
6. A user customizer has `@Order(100)` and the default web-server customizer has order 0. The user expects their callback to run after. Is that reasonable? **Yes, if the extension point uses matching ordering**; verify against actual configuration and other customizers rather than treating it as a guarantee for every bean.
7. You only create a `PipelineCustomizer` bean with `@Order`, and no code invokes `customize`. Does `Pipeline` change? **No.** The consumer must actually apply the callbacks.
8. A starter has `@ConditionalOnMissingBean(Pipeline.class)` and the user creates their own `Pipeline`. Do the customizers the starter intended to apply still run automatically on the user's pipeline? **No**, unless the user or another mechanism explicitly invokes them.
9. Two customizers both set a timeout, and the one with the larger order runs later. Should the later one always win? **Not necessarily.** Define property ownership and check conflicts/validation per the extension point contract.

## 11. Reference materials (Spring Boot 3.3 / Spring Framework 6.1)

- [Spring Framework 6.1 — ObjectProvider.orderedStream()](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/beans/factory/ObjectProvider.html): returns a sequential stream sorted by the shared order comparator, respecting `Ordered`/`@Order` in a standard context.
- [Spring Framework 6.1 — Ordered](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/Ordered.html): lower numbers have higher priority; equal numbers carry no relative ordering guarantee.
- [Spring Framework 6.1 — Bean annotation](https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/context/annotation/Bean.html): `@Bean` methods may carry `@Order`, though ordering does not govern singleton startup.
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): `WebServerFactoryCustomizer` beans and default customizer ordering.
- [Spring Boot 3.3 — WebServerFactoryCustomizer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/server/WebServerFactoryCustomizer.html): callbacks invoked before the web server starts and notes on very early lifecycle.
- [Spring Boot 3.3 — Jackson auto-configuration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jackson/package-summary.html): `Jackson2ObjectMapperBuilderCustomizer`.
