# @ConditionalOnClass, @ConditionalOnBean, and @ConditionalOnMissingBean

> **Chapter:** Auto-Configuration Customization  
> **Module:** SPRING_CLOUD_CORE

Spring Boot and Spring Cloud use auto-configuration to automatically create integration beans when environment conditions match. A configuration might only run when an optional library is on the classpath; an adapter bean might only make sense when another service already exists; and a default bean should only be created when the application has not yet provided its own implementation.

Three annotations—**`@ConditionalOnClass`**, **`@ConditionalOnBean`**, and **`@ConditionalOnMissingBean`**—address these three distinct decisions. They allow auto-configuration to adapt to the actual dependencies and beans in the ApplicationContext while letting applications customize behavior without modifying the integration library's source code.

This lesson uses a catalog module example in the **SPRING_CLOUD_CORE** system to explain classpath conditions, bean conditions, auto-configuration processing order, how to build overridable fallbacks, and how to test each conditional branch.

## 1. Auto-Configuration and Activation Conditions

Auto-configurations are Spring configurations imported automatically based on the classpath, existing beans, and properties. A well-designed auto-configuration does not assume every application has the same dependencies or the same implementation.

For example, a catalog integration module might provide:

- A `CatalogClient` adapter when the vendor SDK is present.
- A `CatalogHealthIndicator` when a `CatalogClient` has already been created.
- A default `CatalogClient` implementation if the application has not provided its own.

If all beans were created unconditionally, the application could run into missing-class errors, missing dependencies, or bean conflicts when users provide custom configuration. Condition annotations let Spring apply only the required parts of the configuration.

~~~mermaid
flowchart TB
    A["Auto-configuration is imported"]
    A --> B{"Is SDK on the classpath?"}
    B -->|No| X["Skip SDK integration configuration"]
    B -->|Yes| C{"Does a CatalogClient bean already exist?"}
    C -->|Yes| D["Keep the application's implementation"]
    C -->|No| E["Create the default CatalogClient"]
    D --> F{"Is CatalogClient in the context?"}
    E --> F
    F -->|Yes| G["Create health indicator if missing"]
    F -->|No| H["Do not create health indicator"]
~~~

Conditions can be placed on configuration classes or on individual `@Bean` methods. Annotation placement determines whether Spring skips the entire configuration or only a single bean method.

## 2. @ConditionalOnClass: Configure Only When a Class Is on the Classpath

`@ConditionalOnClass` checks whether one or more classes can be found by the application's classloader. This condition is useful when an auto-configuration integrates an optional library.

For example, `CatalogSdk` is only present when an application adds the vendor SDK. The module should not attempt to create the adapter if that SDK is absent.

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;

@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
public class CatalogSdkAutoConfiguration {
    // Beans requiring CatalogSdk are declared in this configuration.
}
~~~

The `name` attribute accepts the fully qualified class name as a string. This is useful when you want to avoid a direct class reference to an optional class in the annotation.

### 2.1. Using value or name

You can use a class literal when the class is on the compile classpath:

~~~java
@AutoConfiguration
@ConditionalOnClass(CatalogSdk.class)
public class CatalogSdkAutoConfiguration {
}
~~~

Or use the class name:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
public class CatalogSdkAutoConfiguration {
}
~~~

Practical difference:

| Attribute | Type | When appropriate |
| --- | --- | --- |
| `value` | `Class<?>[]` | The class is available on the compile classpath and the annotation is placed directly on the configuration |
| `name` | `String[]` | You want to reference an optional class by name, especially in a meta-annotation or to avoid class literals |

Spring Boot reads configuration class metadata using ASM so it can evaluate classpath conditions without loading every type referenced in annotations. However, if you create a composed annotation (meta-annotation), use `name` to avoid loading the optional class too early during annotation processing.

### 2.2. Be Careful with @Bean Return Types

A common pitfall is placing a classpath condition on a bean method whose parameter types or return type belong to an optional library. If the optional class is resolved before the condition excludes the method, the application can hit a class-loading error.

When an auto-configuration depends on an optional class, the safe pattern is to place bean methods referencing that class inside a nested configuration class guarded by a class-level classpath condition:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class CatalogSdkAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
    @ConditionalOnBean(type = "com.vendor.catalog.CatalogSdk")
    static class CatalogSdkPresentConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient catalogClient(CatalogSdk sdk) {
            return new SdkCatalogClient(sdk);
        }
    }
}
~~~

In this example, `CatalogSdk` is used inside the nested configuration only when that class is present. The outer auto-configuration does not need to declare the SDK type in its own method signatures.

This structure also helps group beans that share a dependency on an optional library into a single conditional configuration block.

### 2.3. Classpath Conditions Do Not Check for Beans

Having a class on the classpath does not mean a bean using that class has been created. `@ConditionalOnClass` only verifies that the class can be loaded.

For example:

- The SDK is in the dependency graph.
- But the SDK's auto-configuration is disabled via a property.
- Or the application did not create an SDK bean.
- Or the SDK configuration is invalid.

In these cases, the classpath condition can still match. If an adapter bean needs another bean, combine it with `@ConditionalOnBean`.

## 3. @ConditionalOnBean: Configure Only When Dependent Beans Exist

`@ConditionalOnBean` checks whether the ApplicationContext contains a bean matching the specified type, name, or annotation. It is appropriate when a configuration only makes sense if another component has already been created.

For instance, `CatalogHealthIndicator` requires `CatalogClient`. Without the client, the indicator cannot function and should not be created.

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnBean(CatalogClient.class)
public class CatalogHealthAutoConfiguration {

    @Bean
    CatalogHealthIndicator catalogHealthIndicator(CatalogClient client) {
        return new CatalogHealthIndicator(client);
    }
}
~~~

Here the condition is placed on the class, so the entire `CatalogHealthAutoConfiguration` is only applied when a `CatalogClient` bean is already present at the time Spring evaluates the condition.

You can place the condition on a method if only one bean needs that dependency:

~~~java
@Bean
@ConditionalOnBean(CatalogClient.class)
CatalogMetrics catalogMetrics(CatalogClient client) {
    return new CatalogMetrics(client);
}
~~~

### 3.1. Ways to Specify a Bean

The annotation supports attributes for identifying the target bean; commonly used ones include:

| Attribute | Meaning |
| --- | --- |
| `value` | Bean types that must be present |
| `type` | Fully qualified names of bean types as strings |
| `name` | Bean names that must be present |
| `annotation` | Annotations that the bean must carry |

Use `value` when the type is already on the compile classpath. Use `type` when referencing the type as a string name. Use `name` when the configuration contract relies on a specific bean name.

Avoid binding to bean names if applications may swap implementations while keeping the same contract. Checking by interface usually produces more extensible auto-configuration.

### 3.2. @ConditionalOnBean Does Not Check Remote Service Health

A bean condition only inspects bean definitions in the ApplicationContext. It does not call endpoints, query a registry, ping a database, or verify that a remote dependency is reachable.

For example, `CatalogClient` exists, but DNS for the catalog service is failing. `@ConditionalOnBean(CatalogClient.class)` still matches. To check service availability, use a health indicator or appropriate runtime logic.

### 3.3. Condition Evaluation Timing Matters Greatly

`@ConditionalOnBean` only sees bean definitions that have already been processed at the time the condition is evaluated. Therefore, it belongs primarily in auto-configurations, where Spring Boot can order configurations predictably.

If you place the condition in a regular component-scanned configuration, a bean in a configuration processed later may not yet be visible when the condition runs. The outcome may differ from what the configuration author expected.

When auto-configuration A provides `CatalogClient` and auto-configuration B depends on that client, declare ordering so B is processed after A.

~~~java
@AutoConfiguration(after = CatalogSdkAutoConfiguration.class)
@ConditionalOnBean(CatalogClient.class)
public class CatalogHealthAutoConfiguration {
    // Beans depending only on CatalogClient are declared here.
}
~~~

`@AutoConfigureAfter` adjusts ordering between auto-configurations; it does not create missing beans and does not guarantee a bean will exist. The condition still evaluates against actual bean definitions.

## 4. @ConditionalOnMissingBean: Create a Fallback When the Application Has Not Provided One

`@ConditionalOnMissingBean` checks that no matching bean exists in the context yet. This is the key annotation for creating default beans that applications can override.

For example, a module provides a default `CatalogClient` implementation:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class CatalogClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient(CatalogSdk sdk) {
        return new SdkCatalogClient(sdk);
    }
}
~~~

If the application has no `CatalogClient` bean, Spring creates `SdkCatalogClient`. If the application has already declared a bean implementing `CatalogClient`, the default method is skipped and the application's bean is used.

### 4.1. Allowing Users to Customize the Implementation

An application can provide its own implementation:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomCatalogConfiguration {

    @Bean
    CatalogClient catalogClient() {
        return new CachedCatalogClient();
    }
}
~~~

The default auto-configuration with `@ConditionalOnMissingBean(CatalogClient.class)` backs off once the custom bean is registered.

This is a core starter design principle: provide useful defaults without locking users into the library's implementation.

### 4.2. Declare a Sufficiently Specific Return Type

Declare the `@Bean` return type according to the contract the condition needs to check:

~~~java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
CatalogClient catalogClient(CatalogSdk sdk) {
    return new SdkCatalogClient(sdk);
}
~~~

Do not declare a method returning only `Object` if the goal is for Spring to recognize the bean as a `CatalogClient`. During condition evaluation, Spring needs bean type information from metadata and method signatures; an overly generic return type can prevent conditions from recognizing the bean as expected.

If there are multiple contracts, declare the return type using the appropriate public abstraction and configure `@ConditionalOnMissingBean` with the specific contract.

### 4.3. Missing Bean Does Not Mean Missing Implementation on the Classpath

`@ConditionalOnMissingBean` asks whether the ApplicationContext already has a matching bean. It does not ask whether an implementation class sits inside a JAR.

A `CustomCatalogClient` class can be on the classpath, yet if it is not registered as a bean, the condition can still match and create the default bean. Conversely, a bean produced by a factory or `@Bean` method can cause the fallback to be skipped even if the implementation class is not component-scanned.

Distinguishing the classpath from the bean registry helps accurately diagnose why a default bean is created or skipped.

## 5. Combining the Three Conditions in One Module

An auto-configuration can combine all three conditions to achieve flexible behavior:

1. Activate the integration only if the SDK is on the classpath.
2. Create the default `CatalogClient` only if the application has not provided its own bean.
3. Create the health indicator only if a `CatalogClient` actually exists.

You can split these into auto-configurations to express ordering and responsibilities:

~~~java
@AutoConfiguration
public class CatalogSdkAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
    @ConditionalOnBean(type = "com.vendor.catalog.CatalogSdk")
    static class CatalogSdkPresentConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient catalogClient(CatalogSdk sdk) {
            return new SdkCatalogClient(sdk);
        }
    }
}
~~~

Dependent auto-configuration:

~~~java
@AutoConfiguration(after = CatalogSdkAutoConfiguration.class)
@ConditionalOnBean(CatalogClient.class)
public class CatalogHealthAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogHealthIndicator.class)
    CatalogHealthIndicator catalogHealthIndicator(CatalogClient client) {
        return new CatalogHealthIndicator(client);
    }
}
~~~

This structure lets the application replace `CatalogClient` or `CatalogHealthIndicator` with its own beans. Health auto-configuration runs whenever a client contract exists in the context.

If the SDK is absent, `CatalogSdkAutoConfiguration` does not create a default client. If the application supplies its own `CatalogClient` without using the SDK, health auto-configuration can still operate because it only depends on the `CatalogClient` contract.

### 5.1. Registering Auto-Configuration

With Spring Boot 3, a library's auto-configurations are typically listed in the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example contents:

~~~text
com.example.catalog.CatalogSdkAutoConfiguration
com.example.catalog.CatalogHealthAutoConfiguration
~~~

Only registered auto-configurations are automatically imported by Spring Boot. If a class exists but is omitted from the imports file, the application may never evaluate its conditions.

Projects using older Spring Boot versions may use a different auto-configuration registration mechanism, such as `spring.factories` in earlier releases. Match the registration mechanism to the Spring Boot version your library supports.

## 6. Class-Level vs. Bean-Method-Level Conditions

Conditions can be applied at two levels:

| Placement | Outcome when condition does not match |
| --- | --- |
| On `@Configuration` or `@AutoConfiguration` class | The entire configuration is skipped |
| On `@Bean` method | Only that bean method is not applied |

Class-level condition example:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
public class CatalogSdkAutoConfiguration {
    // All beans in this configuration require the SDK.
}
~~~

Method-level condition example:

~~~java
@AutoConfiguration
public class OptionalCatalogMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(CatalogClient.class)
    CatalogMetrics catalogMetrics(CatalogClient client) {
        return new CatalogMetrics(client);
    }

    @Bean
    CatalogDiagnostics catalogDiagnostics() {
        return new CatalogDiagnostics();
    }
}
~~~

In the second example, lacking `CatalogClient` only prevents creating `CatalogMetrics`; `CatalogDiagnostics` can still be created.

Place conditions at the class level when the entire configuration depends on the same condition. Place them on methods when only specific beans depend on that condition.

## 7. How Do Conditions Combine?

When multiple conditions are placed on the same configuration or bean method, all corresponding conditions must match for the bean to be created.

Example:

~~~java
@AutoConfiguration
public class CatalogSdkAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
    @ConditionalOnBean(type = "com.vendor.catalog.CatalogSdk")
    static class CatalogSdkPresentConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient catalogClient(CatalogSdk sdk) {
            return new SdkCatalogClient(sdk);
        }
    }
}
~~~

Meaning:

- The SDK class must be on the classpath.
- A `CatalogSdk` bean must exist in the context.
- No `CatalogClient` bean exists yet.

Only when all three conditions match is the default bean registered.

In real-world auto-configurations, you can place classpath conditions on the configuration class and bean conditions on methods to avoid unsafe references to optional classes. The example above illustrates combined logic; if `CatalogSdk` is an optional dependency, use a nested configuration class as shown earlier.

### 7.1. Conditions Are Not Business Execution Order

Conditions decide whether a configuration or bean is registered. They are not callbacks to perform work after the application starts.

Do not put network calls, data generation, remote API invocations, or side effects inside condition logic. Conditions must evaluate quickly, deterministically, and based on classpath/bean registry metadata.

If you need to check a remote dependency, use a health indicator or explicit startup validation instead of a bean condition.

## 8. Common Design Mistakes

### 8.1. Using @ConditionalOnBean in Regular Component Scanning

If a configuration depends on a bean created later, the condition may evaluate before that bean is registered. Move the dependent logic into an auto-configuration and declare appropriate ordering.

### 8.2. Using @ConditionalOnClass to Check for Beans

A class existing does not mean a bean has been created. If a bean dependency is required, use `@ConditionalOnBean`.

### 8.3. Using @ConditionalOnBean to Check the Classpath

If an optional class is missing, referencing it directly in a method signature or configuration can cause a class-loading error before the bean condition can help. Use `@ConditionalOnClass` to guard the configuration part that depends on that class.

### 8.4. Forgetting @ConditionalOnMissingBean on Default Beans

If auto-configuration creates a default bean unconditionally, an application providing its own implementation may hit `NoUniqueBeanDefinitionException` or have to use `@Primary` to work around the conflict. For beans meant to be replaceable by users, include a missing-bean condition.

### 8.5. Using an Overly Generic Return Type

If a `@Bean` method declares a return type of `Object`, Spring may fail to recognize the required contract during condition evaluation. Use the specific interface or class type that the auto-configuration intends to expose.

### 8.6. Putting Overly Broad Conditions on a Class

An unmatched class-level condition makes every bean in that configuration disappear. If only one bean needs an optional dependency, put the condition on the method or extract an appropriate nested configuration.

### 8.7. Assuming Missing-Bean Conditions Are a Security Mechanism

`@ConditionalOnMissingBean` only decides whether the default bean is created. It does not stop other code from registering beans, does not authorize service calls, and does not control registry access.

## 9. Testing Auto-Configuration with ApplicationContextRunner

Spring Boot provides `ApplicationContextRunner` to test auto-configuration in a small, fast, isolated ApplicationContext. This is the right way to verify each conditional branch without booting the full application.

The example below assumes `CatalogSdkAutoConfiguration` and `CatalogHealthAutoConfiguration` are properly registered, `CatalogSdk` is a type from an optional SDK, and the interfaces/clients belong to the module.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.FilteredClassLoader;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            CatalogSdkAutoConfiguration.class,
                            CatalogHealthAutoConfiguration.class));

    @Test
    void createsDefaultClientWhenSdkAndSdkBeanExist() {
        contextRunner
                .withBean(CatalogSdk.class, FakeCatalogSdk::new)
                .run(context -> {
                    assertThat(context).hasSingleBean(CatalogClient.class);
                    assertThat(context).hasSingleBean(CatalogHealthIndicator.class);
                });
    }

    @Test
    void backsOffWhenApplicationProvidesClient() {
        CachedCatalogClient customClient = new CachedCatalogClient();

        contextRunner
                .withBean(CatalogSdk.class, FakeCatalogSdk::new)
                .withBean(CatalogClient.class, () -> customClient)
                .run(context -> {
                    assertThat(context).hasSingleBean(CatalogClient.class);
                    assertThat(context.getBean(CatalogClient.class))
                            .isSameAs(customClient);
                });
    }

    @Test
    void doesNotCreateClientWhenSdkBeanIsMissing() {
        contextRunner
                .run(context -> {
                    assertThat(context).doesNotHaveBean(CatalogClient.class);
                });
    }

    @Test
    void doesNotCreateSdkIntegrationWhenSdkClassIsMissing() {
        contextRunner
                .withClassLoader(new FilteredClassLoader(CatalogSdk.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(CatalogClient.class);
                });
    }

    @Test
    void doesNotCreateHealthIndicatorWithoutClient() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        CatalogHealthAutoConfiguration.class))
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(CatalogHealthIndicator.class);
                });
    }
}
~~~

`FakeCatalogSdk`, `CachedCatalogClient`, and `CatalogHealthIndicator` are illustrative fixtures to be provided in the project's test sources. The `FilteredClassLoader` test simulates an environment without the SDK to verify the classpath condition branch.

### 9.1. Test Matrix

| SDK class | SDK bean | Custom CatalogClient | Expected result |
| --- | --- | --- | --- |
| Present | Present | Absent | Creates default client; creates health indicator |
| Present | Present | Present | Uses custom client; does not create default client |
| Present | Absent | Absent | Does not create default client if configuration requires SDK bean |
| Absent | Absent | Absent | Skips SDK auto-configuration |
| Absent | Absent | Present | Can keep custom client; health indicator depends on client contract |

The matrix helps independently test classpath conditions, bean conditions, and missing-bean fallbacks. When multiple auto-configurations are involved, also verify ordering and the actual beans in the context.

## 10. Diagnosing Condition Evaluation

When a bean does not appear, do not jump to the conclusion that a dependency is missing. Determine which condition failed to match.

Useful tools:

- `ApplicationContextRunner` to reproduce conditional branches in small tests.
- Actuator Conditions Endpoint or the condition evaluation report to inspect auto-configuration matches and negative matches.
- Startup logs in debug mode to inspect the condition report.
- `ApplicationContext` bean inspection to confirm which beans are actually registered.
- Dependency tree to verify that classes are on the runtime classpath.

How to read common symptoms:

| Symptom | What to check |
| --- | --- |
| Auto-configuration is not imported | Imports metadata or auto-configuration exclusions |
| `@ConditionalOnClass` does not match | Whether the dependency is on the runtime classpath and visible to the classloader |
| `@ConditionalOnBean` does not match | Whether the dependent bean was created before the condition evaluated, and with the expected type/name |
| Default bean does not appear | Whether a bean with the same contract already exists, or whether the return type is specific enough |
| Two implementations of the same contract exist | Whether the default bean lacks `@ConditionalOnMissingBean`, or whether the user bean was not detected |
| Condition behaves differently across profiles | Whether properties, profiles, or config sources change beans or the classpath |

In Spring Boot, the Actuator Conditions Endpoint is typically accessed via `GET /actuator/conditions` once exposed. This endpoint provides the condition report; it does not fix configuration automatically.

## 11. Rules for Designing Extensible Auto-Configuration

When writing a starter or integration module in the Spring Cloud ecosystem, follow these principles:

1. Guard optional integrations with `@ConditionalOnClass`.
2. Use nested configurations when optional classes appear in method signatures.
3. Create dependent adapters only when the required bean contract exists using `@ConditionalOnBean`.
4. Provide default implementations with `@ConditionalOnMissingBean`.
5. Declare return types by contract so conditions have clear metadata.
6. Order dependent auto-configurations with `@AutoConfigureAfter` or `before` as appropriate.
7. Place conditions at the class level if the whole configuration depends on them; use method level if only a single bean needs them.
8. Keep conditions pure metadata checks without remote calls or side effects.
9. Test both matching and non-matching branches using `ApplicationContextRunner`.
10. Ensure auto-configurations are registered using the mechanism appropriate for the supported Spring Boot version.

A good starter provides replaceable default behavior without forcing every application to use the same SDK or implementation.

## 12. Key Takeaways

`@ConditionalOnClass` checks whether a class is on the classpath; `@ConditionalOnBean` checks whether a bean dependency already exists in the ApplicationContext; `@ConditionalOnMissingBean` lets auto-configuration create a fallback when the application has not provided a matching bean.

These three conditions are commonly combined in auto-configuration: classpath conditions gate optional integrations, bean conditions ensure context dependencies are ready, and missing-bean conditions preserve application customizability. For predictable results, pay attention to auto-configuration ordering, `@Bean` return types, condition placement, and testing both with and without dependencies in **SPRING_CLOUD_CORE**.

## References

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot API — ConditionalOnClass](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
- [Spring Boot API — ConditionalOnBean](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html)
- [Spring Boot API — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)