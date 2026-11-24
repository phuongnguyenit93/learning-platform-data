# `parameterizedContainer`: Recognizing Bean Types Through Generic Container Classes in Spring Boot

## 1. The Problem to Solve

In Spring Boot Auto Configuration, bean-based conditions normally check whether the `BeanFactory` already has a bean of the requested type. However, a component may be registered indirectly inside a *generic-typed bean*. For example, an application might not register a standalone `PaymentHandler` bean, and instead register a `HandlerRegistration<PaymentHandler>` bean to hold and manage it.

If you only write `@ConditionalOnBean(PaymentHandler.class)`, the condition normally searches for a `PaymentHandler` bean, and does not treat every `HandlerRegistration<PaymentHandler>` as an independent `PaymentHandler`. The `parameterizedContainer` attribute lets you **expand the set of checked types**: in addition to direct beans of the target type, Spring Boot also checks beans of the specified container class whose generic type parameter matches the target type.

This is an attribute of `@ConditionalOnBean` and `@ConditionalOnMissingBean`, available since Spring Boot 2.1.0. The attribute name is spelled **`parameterizedContainer`** (singular), its API declaration type is `Class<?>[]`, and its default value is an empty array `{}`.

## 2. Syntax and Exact Meaning

Suppose there is a `Service` and a single-type-parameter container class `Registration<T>`. When declared:

- `@ConditionalOnBean(value = Service.class, parameterizedContainer = Registration.class)`: the condition matches if a direct `Service` bean already exists **or** a `Registration<Service>` bean with matching generic type information exists.
- `@ConditionalOnMissingBean(value = Service.class, parameterizedContainer = Registration.class)`: the condition matches if **neither** a direct `Service` bean nor a recognized `Registration<Service>` bean exists.
- If `parameterizedContainer` is omitted, `Registration<Service>` beans are not added to the candidate pool by this mechanism.
- Multiple container classes can be passed, e.g., `parameterizedContainer = {Registration.class, Optional.class}`; `Optional<Service>` is only counted if **`Optional<Service>` itself is registered as a bean**, not because Spring supports injecting `Optional<Service>`.

Note: `Service.class` represents the **target bean type to look for**; `Registration.class` represents the **container class type**. Do not write `Registration<Service>.class` because Java does not allow class literals for parameterized types.

### Comparison Table

For a condition checking `Service.class` and (where applicable) container class `Registration.class`:

| Bean Already in Context | `@ConditionalOnBean(Service.class)` | `@ConditionalOnBean(value=Service.class, parameterizedContainer=Registration.class)` | `@ConditionalOnMissingBean(value=Service.class, parameterizedContainer=Registration.class)` |
| --- | --- | --- | --- |
| No relevant bean | Does not match | Does not match | Matches |
| `Service` | Matches | Matches | Does not match |
| `Registration<Service>` | Does not match | Matches | Does not match |
| `Registration<String>` | Does not match | Does not match | Matches |
| `Service` and `Registration<Service>` | Matches | Matches | Does not match |

The table assumes beans have already been processed at check time, are eligible candidates, and declare sufficiently clear generic types. The outcome is based on **bean type definitions**, not Spring opening the box and looking for a `Service` instance inside.

## 3. Recognition Mechanism in `OnBeanCondition`

Both `@ConditionalOnBean` and `@ConditionalOnMissingBean` are handled by Spring Boot's `OnBeanCondition`:

1. Obtains the target type from `value`/`type` (or infers it from the `@Bean` method's return type where permitted by the API).
2. Finds bean names compatible with the direct target type.
3. For each class declared in `parameterizedContainer`, builds a type with generic info, conceptually `Registration<Service>`, via `ResolvableType.forClassWithGenerics(...)`, then looks up beans matching that type.
4. Combines direct candidates and container-based candidates, then applies the annotation's "bean present" or "bean missing" semantics along with candidate-filtering rules.

`ResolvableType` lets Spring infer generic arguments from metadata such as a `@Bean Registration<Service>` return signature. Java has *type erasure* at runtime, yet type info declared on methods/classes can still be leveraged by Spring; Spring **does not need to call `registration.wrapped()`** or execute application logic to detect the element type.

`parameterizedContainer` does not alter registered beans, does not create a new `Service` bean, does not auto-unwrap during dependency injection, and does not inspect actual contents of `List`/`Map`. A matching condition also does not guarantee the value inside the container is non-`null`: the condition checks metadata and bean definitions, not internal runtime data.

## 4. Runnable Example with Java 17 and Spring Boot 3.5

Goal: automatically create `EnabledFeature` when the application provides a direct `Service` **or** a `Registration<Service>`; if neither exists, create `FallbackFeature`. Test four cases to clearly observe the difference between right and wrong generic types.

Two-file structure:

- `pom.xml`
- `src/test/java/example/ParameterizedContainerTest.java`

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>parameterized-container-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

**`src/test/java/example/ParameterizedContainerTest.java`**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ParameterizedContainerTest {

    interface Service {}

    static final class DefaultService implements Service {}

    // Container class: T represents the wrapped value type.
    record Registration<T>(T wrapped) {}

    record EnabledFeature() {}

    record FallbackFeature() {}

    @Configuration(proxyBeanMethods = false)
    static class WrapperUserConfiguration {
        @Bean
        Registration<Service> registration() {
            return new Registration<>(new DefaultService());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class WrongGenericUserConfiguration {
        @Bean
        Registration<String> registration() {
            return new Registration<>("not a Service");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class DirectServiceUserConfiguration {
        @Bean
        Service service() {
            return new DefaultService();
        }
    }

    @AutoConfiguration
    static class FeatureAutoConfiguration {
        @Bean
        @ConditionalOnBean(
            value = Service.class,
            parameterizedContainer = Registration.class
        )
        EnabledFeature enabledFeature() {
            return new EnabledFeature();
        }

        @Bean
        @ConditionalOnMissingBean(
            value = Service.class,
            parameterizedContainer = Registration.class
        )
        FallbackFeature fallbackFeature() {
            return new FallbackFeature();
        }
    }

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(FeatureAutoConfiguration.class)
            );

    @Test
    void missingServiceCreatesFallback() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(EnabledFeature.class);
            assertThat(context).hasSingleBean(FallbackFeature.class);
        });
    }

    @Test
    void registrationOfServiceEnablesFeature() {
        runner.withUserConfiguration(WrapperUserConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(EnabledFeature.class);
                assertThat(context).doesNotHaveBean(FallbackFeature.class);
                // Service is inside Registration, not a separate Service bean.
                assertThat(context).doesNotHaveBean(Service.class);
            });
    }

    @Test
    void registrationOfStringDoesNotMatchService() {
        runner.withUserConfiguration(WrongGenericUserConfiguration.class)
            .run(context -> {
                assertThat(context).doesNotHaveBean(EnabledFeature.class);
                assertThat(context).hasSingleBean(FallbackFeature.class);
            });
    }

    @Test
    void directServiceAlsoEnablesFeature() {
        runner.withUserConfiguration(DirectServiceUserConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(EnabledFeature.class);
                assertThat(context).doesNotHaveBean(FallbackFeature.class);
            });
    }
}
```

Run in the directory containing `pom.xml` using JDK 17+ and Maven:

```bash
mvn test
```

**Expected result:** all four JUnit tests succeed, and the Maven process exits with code 0. The example does not use `System.out.println`, so there is no fixed stdout string to compare against; the assertions themselves are proof of the presence/absence of each bean.

Key points explained:

- `WrapperUserConfiguration` only creates a `Registration<Service>` bean. The condition with `parameterizedContainer` recognizes the `Service` type argument and activates `EnabledFeature`; it does not register an extra `Service` bean.
- `WrongGenericUserConfiguration` declares `Registration<String>`. This bean does not prove `Service` exists, so the fallback branch is chosen.
- `DirectServiceUserConfiguration` shows the condition still recognizes a direct `Service` bean: `parameterizedContainer` only adds an extra lookup form and does not require every bean to live inside a container class.
- Both `enabledFeature()` and `fallbackFeature()` check the **same target type** `Service.class`, so do not confuse the bean presence/absence logic with the marker types they return.

## 5. When Should You Use It?

Use `parameterizedContainer` when a library or starter registers components via a **single-parameter generic wrapper type**, and auto-configuration needs to treat that wrapper as an indicator that the target component exists. Good design examples are `Registration<Handler>`, `Holder<Plugin>`, or a library-defined wrapper, provided the wrapper itself is registered as a bean with full type information.

Do not use this attribute as a substitute for querying arbitrary generic types. For example, `Map<String, Service>` has two type parameters; declaring `parameterizedContainer = Map.class` does not mean Spring will automatically inspect the `V` parameter of `Map`. When you need to check a specific generic position, compound conditions, or runtime values, consider writing a custom `Condition` using `ResolvableType`/`BeanFactory` appropriately.

## 6. Notes and Common Pitfalls

1. **Overly broad return type.** With `@Bean Object registration()` or a raw type `@Bean Registration registration()`, Spring is not given the full `Registration<Service>` in the declared signature. Prefer an explicit return type: `@Bean Registration<Service> registration()`.
2. **Confusing the wrapper with the inner bean.** The condition may match thanks to `Registration<Service>`, yet `@Autowired Service` will not automatically have a `Service` bean to inject. To obtain the contained value, inject `Registration<Service>` or explicitly register `Service` as another bean.
3. **Forgetting to specify the target type.** `parameterizedContainer = Registration.class` only specifies the wrapper. When looking for `Service`, explicitly declare `value = Service.class`; if left empty, the `@Bean` method type-inference rule may create a different condition than you expect.
4. **Confusing multiple target types with multiple generic positions.** `value = {A.class, B.class}` does not map `A` to the first type parameter and `B` to the second type parameter of a wrapper. With `@ConditionalOnBean`, both requirements must be satisfied; with `@ConditionalOnMissingBean`, neither requirement may be present.
5. **Dependence on bean registration order.** Conditions only see bean definitions processed up to evaluation time. Use `@ConditionalOnBean`/`@ConditionalOnMissingBean` in auto-configuration, since it is processed after user configuration; if depending on another auto-configuration, set proper ordering via `@AutoConfiguration(after = ...)`.
6. **Overlooking candidate eligibility.** Spring Boot filters out non-autowire/default candidates according to condition rules; having a bean definition of that name or a wrapper of that type does not automatically guarantee the condition matches.
7. **Misunderstanding search scope.** `search` defaults to `SearchStrategy.ALL` so it can search parent contexts; `search = SearchStrategy.CURRENT` restricts to the current context. `parameterizedContainer` does not alter this hierarchy rule.

## 7. Quick Self-Check

- There is only a `Registration<Service>` bean and the annotation is `@ConditionalOnBean(Service.class)`: **does not match via the wrapper branch**. Add `parameterizedContainer = Registration.class`: **matches**.
- There is a `Registration<String>` bean, and the annotation asks for `Service.class` with container `Registration.class`: **does not match**, because the inner generic type does not match.
- There is a direct `Service` bean: `@ConditionalOnBean(value = Service.class, parameterizedContainer = Registration.class)` still **matches**, even when no wrapper exists.
- After the condition matches via the wrapper, can `Service` be injected directly? **You cannot assume that**; you need a separate `Service` bean or to access the value through the wrapper.

## Official Reference Documentation

- Spring Boot API — `@ConditionalOnBean`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
- Spring Boot API — `@ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot Reference — Creating Your Own Auto-configuration (bean conditions, processing order, `ApplicationContextRunner`): https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html

**Remember:** `parameterizedContainer` helps bean-type conditions additionally recognize `Registration<T>` as evidence of `T`. It does not turn `T` into a separate bean and does not inspect the `T` object inside the wrapper.
