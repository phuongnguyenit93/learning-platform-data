# Reading Class-Level Conditions Before Analyzing Individual @Bean Methods in Spring Boot Auto-Configuration

## 1. Why Must You Read from the Class Down to Each Bean Method?

An auto-configuration may declare multiple beans, not all of which fit every application. For example, a library provides a core client, optional metrics, and an adapter that only works when a JDBC library is present:

~~~java
@AutoConfiguration
@ConditionalOnProperty(prefix = "acme.client", name = "enabled",
                       havingValue = "true")
class AcmeClientAutoConfiguration {

    @Bean
    AcmeClient acmeClient() {
        return new AcmeClient();
    }

    @Bean
    @ConditionalOnProperty(prefix = "acme.client.metrics",
                           name = "enabled", havingValue = "true")
    AcmeMetrics acmeMetrics() {
        return new AcmeMetrics();
    }
}
~~~

When reading the code, start with **class-level conditions**, and only then move into each `@Bean` method:

1. Is this class a candidate auto-configuration and is it loaded by Spring Boot?
2. Do the conditions attached at the class level allow the configuration to participate?
3. Does the class import any child configurations, registrars, or component scans?
4. What specific conditions does each `@Bean` method have?
5. If a method is registered, what beans do its parameters require and what is its exact return type?

Reading this way helps distinguish the **overall condition gate** from **per-bean conditions**. A class-level condition typically affects a broader configuration scope; a method-level condition only controls the bean declared by that method.

However, do not interpret "read the class first" as "every class-level condition is evaluated before every method-level condition". Spring has multiple evaluation phases. In particular, classpath checks and bean-registry checks do not necessarily run in the same phase.

## 2. What Is an Auto-Configuration Class?

`@AutoConfiguration` is a specialized Spring Boot annotation meta-annotated with `@Configuration`. Thus, an auto-configuration remains a source of bean declarations under Spring's Java Configuration mechanism while following Boot's specific discovery and ordering rules.

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AcmeClientAutoConfiguration {

    @Bean
    AcmeClient acmeClient() {
        return new AcmeClient();
    }
}
~~~

The snippet above illustrates a class capable of providing beans. To be automatically discovered by Boot when packaged into a JAR, the class must be listed in:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

File contents, one class per line:

~~~text
com.acme.client.autoconfigure.AcmeClientAutoConfiguration
~~~

If the class is not listed in imports, having `@AutoConfiguration` on the source alone does not guarantee it will be applied. Conversely, a candidate class can still be filtered out by conditions during configuration processing.

**Read the top of the class first:** note `@AutoConfiguration`, all `@Conditional...` annotations, `@Import`, `@EnableConfigurationProperties`, and `before/after` attributes. This metadata shapes scope, dependencies, and processing order before you evaluate individual bean methods.

## 3. Two Condition Scopes: Class-Level and Method-Level

Spring Framework allows `@Conditional` to appear at the type level or method level. Boot annotations such as `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, and `@ConditionalOnMissingBean` are all built on this mechanism.

| Annotation Location | Controlled Scope | Question When Reading |
| --- | --- | --- |
| On `@Configuration` / `@AutoConfiguration` | Class configuration scope, including declarations tied to that configuration | Is the overall configuration eligible to participate? |
| On a `@Bean` method | Only the bean definition provided by that method | Is this specific bean eligible to be registered? |
| On nested `@Configuration` | A group of beans bundled into a child configuration | Can this optional feature group be enabled independently? |

Example of a class with a shared condition and two methods with individual conditions:

~~~java
@AutoConfiguration
@ConditionalOnProperty(prefix = "acme", name = "enabled",
                       havingValue = "true")
class AcmeAutoConfiguration {

    @Bean
    CoreService coreService() {
        return new CoreService();
    }

    @Bean
    @ConditionalOnProperty(prefix = "acme", name = "metrics-enabled",
                           havingValue = "true")
    MetricsService metricsService() {
        return new MetricsService();
    }
}
~~~

For `CoreService` or `MetricsService` to be provided through this configuration, the class-level condition must allow the configuration to participate. In addition:
- `CoreService` has no separate condition, so it depends only on the class-level condition and its other conditions/metadata.
- `MetricsService` must also satisfy `acme.metrics-enabled=true`.
- If the class-level condition does not match, a method-level condition cannot "re-open" a configuration that has already been excluded.

According to Spring's `@Conditional` contract, conditions at the `@Configuration` level apply to the `@Bean`, `@Import`, and `@ComponentScan` declarations associated with that class. Conditions applied to the same element must match using **AND** logic: if even one condition fails, the element is ineligible for registration. If you want two independent branches, you should generally separate them into distinct nested configurations or auto-configuration classes.

## 4. Do Not Confuse Scope with Condition Evaluation Phase

Spring Framework defines two phases in `ConfigurationCondition`:

| Phase | Meaning | What Is Already Available? |
| --- | --- | --- |
| `PARSE_CONFIGURATION` | Evaluated while the parser is processing the configuration class | Spring is deciding whether to continue parsing the class, imports, and configuration structure |
| `REGISTER_BEAN` | Evaluated when registering a regular bean definition | Configuration classes have been parsed; bean definitions processed earlier can be inspected |

Common condition groups:

- **Classpath conditions** such as `@ConditionalOnClass` / `@ConditionalOnMissingClass`: decide whether a configuration fits the libraries present on the classpath. At the class level, Boot can read annotation metadata using ASM to check without loading optional classes into the JVM.
- **Bean conditions** such as `@ConditionalOnBean` / `@ConditionalOnMissingBean`: inspect bean definitions already processed up to the evaluation point. They are sensitive to registration order and must be read together with auto-configuration metadata and before/after ordering.
- **Property conditions** such as `@ConditionalOnProperty`: inspect `Environment`; can be used at the class level to toggle an entire configuration or at the method level to toggle a single bean.
- **Web/resource conditions**: check the application context type or whether a resource exists; commonly used to scope feature groups.

Do not infer that every annotation starting with `@ConditionalOn` runs in the same phase. When writing a custom condition, if you need to decide during class parsing or during bean registration, implement `ConfigurationCondition` and choose the phase intentionally.

### Specific Note on Class-Level Bean Conditions

`@ConditionalOnBean` and `@ConditionalOnMissingBean` can appear at the class or method level. When placed at the class level, the condition applies to the configuration class scope and affects registration of that configuration; when placed on a method, it controls only that bean method. Boot notes that bean conditions are not simply an early class-parsing gate: the configuration class is still processed according to configuration lifecycle rules, while bean conditions are evaluated during the bean registration phase.

Because these conditions depend on already-processed bean definitions, Boot recommends placing them in **auto-configurations**, which are applied after user-declared bean definitions. When only a single bean needs a prerequisite, placing the condition directly on the `@Bean` method usually makes the intent clearer and avoids constraining unrelated sibling beans.

## 5. Read Class-Level Conditions First: Classpath, Property, Profile, and Web Context

### 5.1. @ConditionalOnClass and @ConditionalOnMissingClass

These two annotations check the presence/absence of classes on the classpath:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.VendorClient")
class VendorAutoConfiguration {

    @Bean
    VendorAdapter vendorAdapter() {
        return new VendorAdapter();
    }
}
~~~

If `com.vendor.sdk.VendorClient` is not on the classpath, the configuration does not match. The `name` attribute accepts a class name string, which is appropriate when you want to avoid directly referencing an optional type in the annotation.

**Pitfall when placing the condition on a method:** if a `@Bean` method's return type or signature directly references an optional class, the JVM may need to load/resolve that type before the method-level condition has a chance to exclude the bean. To protect optional libraries, isolate methods whose signatures depend on that class inside a nested configuration guarded by a class condition:

~~~java
@AutoConfiguration
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.VendorClient")
    static class VendorClientConfiguration {

        @Bean
        VendorAdapter vendorAdapter(com.vendor.sdk.VendorClient client) {
            return new VendorAdapter(client);
        }
    }
}
~~~

This is a code organization pattern: the SDK dependency is still required on the compile classpath when compiling the module containing the method signature, even though it may be absent at runtime. The nested configuration keeps the SDK references isolated from the always-loaded auto-configuration class. If the condition is a custom meta-annotation, Boot requires using `name` when referencing optional classes in composed annotations.

### 5.2. @ConditionalOnProperty and @Profile

Use a property condition when configuration comes from `application.yml` or an `Environment` source:

~~~java
@AutoConfiguration
@ConditionalOnProperty(prefix = "acme.client", name = "enabled",
                       havingValue = "true")
class AcmeClientAutoConfiguration {
    // Shared beans when client is enabled
}
~~~

If only metrics are optional, move the condition down to the metrics method instead of disabling the entire client. `@Profile("production")` is also a class-level or method-level condition to restrict configuration by active profile.

### 5.3. @ConditionalOnWebApplication

A library containing both servlet integration and core logic can split them:

~~~java
@AutoConfiguration
class AcmeAutoConfiguration {

    @Bean
    CoreService coreService() {
        return new CoreService();
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnWebApplication(type =
            ConditionalOnWebApplication.Type.SERVLET)
    static class ServletConfiguration {

        @Bean
        ServletAdapter servletAdapter() {
            return new ServletAdapter();
        }
    }
}
~~~

As a result, core beans do not necessarily depend on a web context; only the servlet adapter group requires a servlet application. The `CoreService` and `ServletAdapter` types in the illustration must be defined in the project.

## 6. Reading Individual @Bean Methods: Specific Conditions, Return Type, and Dependencies

After understanding the class-level scope, read each method along four points:

1. Bean name (by default the method name, unless specified with `@Bean(name=...)`).
2. Return type (the type metadata Spring sees when analyzing the bean).
3. Condition annotations directly on the method.
4. Method parameters (dependencies required to create the bean).

Example:

~~~java
@Bean
@ConditionalOnBean(DataSource.class)
@ConditionalOnMissingBean(ReportRepository.class)
JdbcReportRepository reportRepository(DataSource dataSource) {
    return new JdbcReportRepository(dataSource);
}
~~~

Interpretation:
- Register the bean only if a matching `DataSource` bean is already registered and visible to the condition.
- At the same time, no matching `ReportRepository` bean exists yet.
- The method accepts `DataSource` to instantiate the repository.
- Both conditions on the method must match.

`@ConditionalOnBean` checks **beans in the BeanFactory**, not just classes on the classpath. Having the `DataSource` class in the JDK or a dependency does not mean a `DataSource` bean exists. If a method requires that bean, the condition and injection parameter should express the same prerequisite.

### Return Type Is Part of Condition Metadata

When `@ConditionalOnMissingBean` does not specify a type/name, the target type of the method condition defaults to the method's **return type**:

~~~java
@Bean
@ConditionalOnMissingBean
DefaultReportFormatter reportFormatter() {
    return new DefaultReportFormatter();
}
~~~

A concrete return type `DefaultReportFormatter` gives Spring richer type information during condition evaluation. Avoid overly generic declarations:

~~~java
@Bean
@ConditionalOnMissingBean
Object reportFormatter() {
    return new DefaultReportFormatter();
}
~~~

In the second form, the metadata only exposes `Object`, leaving the condition without enough type information as expected. Boot recommends providing the most informative return type possible, especially with bean conditions.

## 7. Combined Example: Class Condition and Method Conditions Working Together

The following example illustrates three layers of decisions:

- Class-level: the entire auto-configuration applies only when `acme.library.enabled=true`.
- Method-level property: metrics are registered only when `acme.library.metrics.enabled=true`.
- Method-level bean conditions: the publisher is created only when `AuditStore` is present; the default formatter is created only when the user has not provided a `Formatter`.

~~~java
package com.example.demo;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.library",
        name = "enabled",
        havingValue = "true"
)
class LibraryAutoConfiguration {

    @Bean
    CoreService coreService() {
        return new CoreService();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.library.metrics",
            name = "enabled",
            havingValue = "true"
    )
    MetricsService metricsService() {
        return new MetricsService();
    }

    @Bean
    @ConditionalOnBean(AuditStore.class)
    AuditPublisher auditPublisher(AuditStore store) {
        return new AuditPublisher(store);
    }

    @Bean
    @ConditionalOnMissingBean(Formatter.class)
    DefaultFormatter defaultFormatter() {
        return new DefaultFormatter();
    }
}
~~~

The classes `CoreService`, `MetricsService`, `AuditStore`, `AuditPublisher`, `Formatter`, and `DefaultFormatter` are application/library types; they are fully defined in the test file in section 9. This example focuses on condition structure rather than a standalone source file to compile on its own.

Result table:

| Configuration | CoreService | MetricsService | AuditPublisher | DefaultFormatter |
| --- | --- | --- | --- | --- |
| `acme.library.enabled=false` | No | No | No | No |
| `enabled=true`, metrics missing/off, no AuditStore | Yes | No | No | Yes |
| `enabled=true`, metrics=true, AuditStore present, no Formatter yet | Yes | Yes | Yes | Yes |
| `enabled=true`, user provides AuditStore and Formatter | Yes | Depends on metrics property | Yes | No (backs off) |

This is the outside-in analysis approach: class-level conditions first, then evaluating individual methods. Do not conclude that all methods share the same state just because one method-level property is turned off.

## 8. Bean Definition Registration Order and Why Bean Conditions Are Order-Sensitive

`@ConditionalOnBean` and `@ConditionalOnMissingBean` rely on bean definitions processed up to the moment the condition runs. Therefore:
- User-declared beans are normally registered before auto-configuration, allowing users to override defaults.
- If an auto-configuration depends on a bean created by another auto-configuration, you must order them using `@AutoConfiguration(after = ...)` or `@AutoConfigureAfter` when appropriate.
- Do not place bean conditions in a regular component-scanned configuration if it could be processed before the bean the condition is waiting for.
- A class being on the classpath is not a substitute for a registered bean definition.
- A registered bean definition does not mean the instance has already finished initializing.

Example:

~~~java
@AutoConfiguration
class StorageAutoConfiguration {

    @Bean
    StorageClient storageClient() {
        return new StorageClient();
    }
}

@AutoConfiguration(after = StorageAutoConfiguration.class)
class SearchAutoConfiguration {

    @Bean
    @ConditionalOnBean(StorageClient.class)
    SearchIndexer searchIndexer(StorageClient storage) {
        return new SearchIndexer(storage);
    }
}
~~~

`after` ensures ordering metadata: Search auto-configuration is processed after Storage auto-configuration. It does not create `StorageClient` itself if the storage configuration does not participate or its bean is excluded by another condition. It also does not control instance initialization order; instance creation depends on injection and container lifecycle.

## 9. Runnable Testing with ApplicationContextRunner

Testing auto-configuration needs to cover combinations of class-level and method-level conditions. `ApplicationContextRunner` allows creating isolated contexts, attaching properties and user configurations to verify which beans are registered.

Create `src/test/java/com/example/demo/ConditionScopeTest.java` in a Java 17+ project using Spring Boot 3.3 and the `spring-boot-starter-test` dependency:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionScopeTest {

    static final class CoreService {
    }

    static final class MetricsService {
    }

    interface AuditStore {
        String name();
    }

    static final class MemoryAuditStore implements AuditStore {
        @Override
        public String name() {
            return "memory";
        }
    }

    static final class AuditPublisher {
        private final AuditStore store;

        AuditPublisher(AuditStore store) {
            this.store = store;
        }

        String destination() {
            return store.name();
        }
    }

    interface Formatter {
        String format();
    }

    static final class DefaultFormatter implements Formatter {
        @Override
        public String format() {
            return "default";
        }
    }

    static final class CustomFormatter implements Formatter {
        @Override
        public String format() {
            return "custom";
        }
    }

    @AutoConfiguration
    @ConditionalOnProperty(
            prefix = "acme.library",
            name = "enabled",
            havingValue = "true"
    )
    static class LibraryAutoConfiguration {

        @Bean
        CoreService coreService() {
            return new CoreService();
        }

        @Bean
        @ConditionalOnProperty(
                prefix = "acme.library.metrics",
                name = "enabled",
                havingValue = "true"
        )
        MetricsService metricsService() {
            return new MetricsService();
        }

        @Bean
        @ConditionalOnBean(AuditStore.class)
        AuditPublisher auditPublisher(AuditStore store) {
            return new AuditPublisher(store);
        }

        @Bean
        @ConditionalOnMissingBean(Formatter.class)
        DefaultFormatter defaultFormatter() {
            return new DefaultFormatter();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserExtensions {

        @Bean
        AuditStore auditStore() {
            return new MemoryAuditStore();
        }

        @Bean
        CustomFormatter customFormatter() {
            return new CustomFormatter();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(LibraryAutoConfiguration.class));

    @Test
    void classConditionDisablesAllLibraryBeans() {
        runner.withPropertyValues(
                "acme.library.enabled=false",
                "acme.library.metrics.enabled=true")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(CoreService.class);
                    assertThat(context).doesNotHaveBean(MetricsService.class);
                    assertThat(context).doesNotHaveBean(AuditPublisher.class);
                    assertThat(context).doesNotHaveBean(DefaultFormatter.class);
                });
    }

    @Test
    void methodConditionsOnlyDisableTheirOwnBeans() {
        runner.withPropertyValues("acme.library.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(CoreService.class);
                    assertThat(context).doesNotHaveBean(MetricsService.class);
                    assertThat(context).doesNotHaveBean(AuditPublisher.class);
                    assertThat(context).hasSingleBean(DefaultFormatter.class);
                });
    }

    @Test
    void userBeansSatisfyConditionsAndReplaceDefault() {
        runner.withPropertyValues(
                "acme.library.enabled=true",
                "acme.library.metrics.enabled=true")
                .withUserConfiguration(UserExtensions.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(CoreService.class);
                    assertThat(context).hasSingleBean(MetricsService.class);
                    assertThat(context).hasSingleBean(AuditStore.class);
                    assertThat(context).hasSingleBean(AuditPublisher.class);
                    assertThat(context.getBean(AuditPublisher.class).destination())
                            .isEqualTo("memory");
                    assertThat(context).hasSingleBean(CustomFormatter.class);
                    assertThat(context).doesNotHaveBean(DefaultFormatter.class);
                    assertThat(context.getBean(Formatter.class).format())
                            .isEqualTo("custom");
                });
    }
}
~~~

Run with the Gradle wrapper in a project that already has test dependencies:

~~~bash
./gradlew test --tests "com.example.demo.ConditionScopeTest"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.demo.ConditionScopeTest"
~~~

**Expected result:** 3 tests PASS. Assertions verify beans in the context rather than relying on specific stdout.

- Test 1: the class condition does not match, so no beans from LibraryAutoConfiguration are registered.
- Test 2: the class condition matches; individual method-level conditions do not match, so the core bean and default formatter are still registered.
- Test 3: metrics property is enabled, and user config provides AuditStore and Formatter; the publisher is created, the default formatter backs off, and the custom formatter is used.

`AutoConfigurations.of(...)` supplies the auto-configuration to the runner. `withUserConfiguration(...)` simulates application-declared beans; Spring Boot processes them before auto-configuration, making it suitable for testing `@ConditionalOnBean` and `@ConditionalOnMissingBean`.

## 10. Reading the Condition Evaluation Report to Understand Why a Bean Was Skipped

When a bean does not appear, do not guess solely from source code. Enable `--debug` when running the application or set `debug=true` so Spring Boot prints the **Condition Evaluation Report**.

In tests, you can add a listener:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))
        .run(context -> {
            // context assertions
        });
~~~

The snippet above is a diagnostic snippet to add to the runner; you need the proper class imports and to run inside a test with configured logging.

The report typically distinguishes:
- **Positive matches:** conditions that matched; configuration/bean is eligible.
- **Negative matches:** conditions that did not match and why.
- **Unconditional classes:** configurations without corresponding conditions.

For applications with Spring Boot Actuator and an appropriately exposed endpoint, `/actuator/conditions` provides condition evaluation information. Check the environment's security/exposure configuration before using this endpoint.

### Ordered Debugging Checklist

1. Is the auto-configuration in `AutoConfiguration.imports`?
2. Which class-level conditions apply, and which condition did not match?
3. Which class-level imports or nested configurations are being brought in?
4. Does the bean method have its own condition? Does the condition check properties, classpath, or bean types?
5. If it is `@ConditionalOnBean`, was the prerequisite registered **before evaluation time**?
6. Does the method return type carry sufficient type information?
7. If the bean has multiple candidates, does the consumer face ambiguity or need `@Primary`/`@Qualifier`?
8. If an optional class is absent from the classpath, is it being referenced in the signature of a method outside a guarded nested configuration?

## 11. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| The class has `@ConditionalOnProperty` false, but a method has its property true, so the bean method still runs | A method condition cannot re-open a configuration already excluded by a class-level condition |
| Class-level and method-level conditions share the same scope | Class-level applies broadly to the configuration; method-level applies to a single bean |
| All conditions run before Spring reads the methods | The phase depends on the condition type; classpath conditions and bean conditions run at different times |
| Having `AuditStore` on the classpath satisfies `@ConditionalOnBean(AuditStore.class)` | A matching bean definition must exist in the BeanFactory |
| A method with `@ConditionalOnMissingBean` without an explicit type infers from its parameters | The default target relies on the method's return type; declare a concrete return type |
| A false method condition makes all sibling beans disappear | Only that bean method is blocked by its own condition; class conditions have broad scope |
| Adding `@DependsOn` makes an earlier `@ConditionalOnBean` match | `@DependsOn` relates to instance initialization order, not retroactively registering bean definitions |
| Using method-level `@ConditionalOnClass` to guard optional return types is always safe | The JVM may have to resolve the method signature before the condition runs; isolate inside a nested configuration |
| `@ConditionalOnExpression` referencing beans is always safe | Beans may be initialized very early and miss post-processing; avoid referencing beans in expressions |
| Seeing the context start successfully means all expected beans are present | Beans can be excluded by conditions while the context still starts; tests must assert bean presence/absence |

## 12. Design Principles and How to Review Auto-Configuration

When reviewing an auto-configuration, use the following sequence:

- **Top of the class:** verify `@AutoConfiguration`, the entry in imports, class-level conditions, `@Import`, nested configurations, properties, and before/after metadata.
- **Categorize conditions:** does the condition inspect classpath, environment, web context, or bean registry? Do not infer phase purely from the annotation name.
- **Each @Bean:** record the bean name, return type, method-level conditions, and parameter dependencies.
- **Shared conditions:** place them on the class only if the entire configuration genuinely shares the same requirement.
- **Individual conditions:** place them on methods or nested configurations so optional features do not accidentally block core beans.
- **Optional dependencies:** use class conditions and nested configurations to isolate types not always present on the runtime classpath.
- **Bean conditions:** place them in auto-configurations; check ordering against upstream auto-configurations if beans from other configurations are needed.
- **Overrides:** use `@ConditionalOnMissingBean` so defaults back off when the user provides a matching bean.
- **Return types:** declare the most specific type possible, especially with bean-type conditions.
- **Test matrix:** test class condition true/false, method condition true/false, prerequisite bean present/absent, user override, and optional classpath present/absent.

A simplified mental-model diagram:

~~~mermaid
flowchart TD
    A["Read @AutoConfiguration and imports"] --> B["Read class-level conditions"]
    B --> C{"Configuration applied?"}
    C -->|"No"| X["No beans from this configuration"]
    C -->|"Yes"| D["Read each @Bean method"]
    D --> E["Check method-level conditions"]
    E --> F{"Method matches?"}
    F -->|"No"| Y["Skip this bean method"]
    F -->|"Yes"| G["Register bean definition"]
    G --> H["Resolve dependencies and initialize per lifecycle"]
~~~

The diagram is a reading and analysis guide. In practice, conditions are evaluated in their appropriate phases; not all of them are a single linear check before Spring inspects every method.

## Official References

- [Spring Boot 3.3.13 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): condition annotations, class conditions, bean conditions, imports, auto-configuration ordering, and `ApplicationContextRunner`.
- [Spring Framework 6.1 — `@Conditional` JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/context/annotation/Conditional.html): TYPE/METHOD scopes and semantics of conditions on `@Configuration`.
- [Spring Framework 6.1 — `ConfigurationCondition.ConfigurationPhase` JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.ConfigurationPhase.html): `PARSE_CONFIGURATION` and `REGISTER_BEAN`.
- [Spring Boot 3.3.13 — `@ConditionalOnBean` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): requires bean already present in BeanFactory.
- [Spring Boot 3.3.13 — `@ConditionalOnMissingBean` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): registering defaults based on bean absence.
