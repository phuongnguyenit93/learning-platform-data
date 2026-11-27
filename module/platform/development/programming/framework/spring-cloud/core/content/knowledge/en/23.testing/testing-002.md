# Testing Auto-Configuration with ApplicationContextRunner

> **Chapter:** Testing  
> **Module:** SPRING_CLOUD_CORE

Auto-configuration often has many conditional branches: a library may or may not be on the classpath, a dependency bean may already be supplied by the application, a property may toggle a capability on or off, and a default bean may need to back off when the user customizes it. Simply verifying that an application starts successfully is not enough to prove every branch works properly.

Spring Boot provides **ApplicationContextRunner** to test auto-configuration in a small ApplicationContext where you can configure the exact classpath, properties, and input beans. Tests run fast, remain isolated, and let you directly inspect which beans were created, which were skipped, and why a condition did not match. This is the right tool for developing starters and integrations in **SPRING_CLOUD_CORE**.

This lesson builds a continuous Catalog example: activating an adapter only when the SDK is on the classpath and an SDK bean exists, creating a default implementation if the application has not provided a `CatalogClient`, and then creating a health indicator when the client contract exists. The tests cover the success branch, fallback branch, missing class, missing bean, and property configuration.

## 1. Why Use ApplicationContextRunner?

An auto-configuration can work in a development environment yet fail in another application because of differences in classpath, bean registry, and properties.

For example, a catalog module might have these rules:

- Integrate the SDK only if the `CatalogSdk` class exists.
- Create the adapter only if the context already has a `CatalogSdk` bean.
- Create the default `CatalogClient` only if the application has not provided an implementation.
- Create `CatalogHealthIndicator` only when a `CatalogClient` bean exists.

If you only run one test that starts the application with all dependencies present, you have only tested one branch. ApplicationContextRunner lets you create multiple contexts with different inputs to test each conditional branch.

### 1.1. What Does ApplicationContextRunner Do?

The runner creates a separate ApplicationContext for each `run` call. A test can configure:

| API | Purpose |
| --- | --- |
| withConfiguration(AutoConfigurations.of(...)) | Import the auto-configurations to test |
| withUserConfiguration(...) | Register configuration supplied by the application or test |
| withBean(...) | Add fixture beans into the context |
| withPropertyValues(...) | Set properties for the test run |
| withClassLoader(...) | Swap the classloader, commonly used to simulate a missing optional class |
| withInitializer(...) | Customize the context before refresh |
| run(context -> ...) | Run the context and execute assertions |

Each call to `run` creates an isolated context and the runner handles closing the context after the callback. Therefore, the test does not need to hold the context or call `close` manually.

### 1.2. What the Runner Does Not Do Automatically

ApplicationContextRunner does not boot an entire application like `SpringApplication.run`. It does not automatically scan all application packages, load all production configurations, or open an embedded web server.

That is intentional: the test only imports relevant configuration so conditional branches are easy to observe. If you need to test a servlet context or reactive web context, use the specialized runners shown later.

## 2. Testing Dependencies

Typically, an auto-configuration module needs the appropriate Spring Boot dependencies and test sources need Spring Boot Test.

Maven example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-autoconfigure</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-test-autoconfigure</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.assertj</groupId>
    <artifactId>assertj-core</artifactId>
    <scope>test</scope>
</dependency>
~~~

In applications using `spring-boot-starter-test`, many test dependencies are already pulled in. For an auto-configuration library, you can declare specific test artifacts individually to avoid bringing unnecessary dependencies into runtime.

Always use dependency management/BOM compatible with the Spring Boot release your module supports. Do not manually mix `spring-boot-test` and `spring-boot-autoconfigure` versions from different releases.

## 3. Preparing the Auto-Configuration Under Test

We use a Catalog module example with an optional SDK. The following types serve as the contracts or fixtures of the example:

- `CatalogSdk`: a type from a vendor SDK library.
- `CatalogClient`: the interface used by the application.
- `SdkCatalogClient`: the default adapter bridging to the SDK.
- `CatalogHealthIndicator`: a health indicator backed by the client.
- `CatalogClientProperties`: client timeout configuration.

### 3.1. Auto-Configuration with Classpath and Bean Conditions

Place methods referencing the SDK inside a nested configuration so the optional class is not loaded when the SDK is absent:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
@EnableConfigurationProperties(CatalogClientProperties.class)
public class CatalogSdkAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
    @ConditionalOnBean(type = "com.vendor.catalog.CatalogSdk")
    static class SdkPresentConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient catalogClient(
                CatalogSdk sdk,
                CatalogClientProperties properties) {
            return new SdkCatalogClient(sdk, properties);
        }
    }
}
~~~

There are three distinct conditions:

1. `ConditionalOnClass` verifies the SDK class is on the runtime classpath.
2. `ConditionalOnBean` verifies the context already has an SDK bean.
3. `ConditionalOnMissingBean` ensures the application can replace the default `CatalogClient` implementation.

The nested configuration guards the method signature that directly references the SDK. The `type` attribute uses a string class name so the bean condition does not reference the SDK class in the outer configuration.

### 3.2. Auto-Configuration Depending on CatalogClient

The health indicator only makes sense when the client contract exists. Place it in an auto-configuration ordered after the client-creating configuration:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

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

`AutoConfiguration(after = ...)` ensures the health auto-configuration is processed after the Catalog SDK configuration. Bean conditions are still evaluated against the bean definitions available at that point; declaring ordering does not create `CatalogClient` by itself.

If the application provides its own `CatalogClient`, the health auto-configuration can still work without the SDK. This is a branch that should be tested separately.

### 3.3. Registering Auto-Configuration in a Library

In Spring Boot 3, libraries typically list auto-configurations in:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example contents:

~~~text
com.example.catalog.CatalogSdkAutoConfiguration
com.example.catalog.CatalogHealthAutoConfiguration
~~~

When using ApplicationContextRunner, tests can import classes directly via `AutoConfigurations.of(...)`. This lets you test conditions without depending on packaging metadata. However, the library still needs a separate test to verify that the imports file is packaged properly.

## 4. Creating a Basic ApplicationContextRunner

A minimal runner:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            CatalogSdkAutoConfiguration.class,
                            CatalogHealthAutoConfiguration.class));
}
~~~

`AutoConfigurations.of(...)` marks the classes as auto-configurations so the runner processes them using Spring Boot's ordering mechanism. If you only use `withUserConfiguration(...)`, the configuration is registered as user configuration; that can make condition evaluation order differ from real auto-configuration behavior.

A test running the context:

~~~java
@Test
void contextStarts() {
    contextRunner.run(context -> {
        assertThat(context).hasNotFailed();
    });
}
~~~

`run` accepts a callback with an `AssertableApplicationContext`. You can assert startup status, beans by type or name, bound property values, and exceptions if the context fails to start.

Do not stop at `hasNotFailed()`. A context that starts successfully can still be missing beans that the module is supposed to provide.

## 5. Testing Default Beans and User Overrides

### 5.1. Branch with SDK Class and SDK Bean Present

When the SDK class is present and the context has a `CatalogSdk` bean, auto-configuration can create `SdkCatalogClient`. Health auto-configuration can also create the indicator.

~~~java
@Test
void createsDefaultClientWhenSdkAndSdkBeanExist() {
    contextRunner
            .withBean(CatalogSdk.class, FakeCatalogSdk::new)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(CatalogClient.class);
                assertThat(context.getBean(CatalogClient.class))
                        .isInstanceOf(SdkCatalogClient.class);
                assertThat(context)
                        .hasSingleBean(CatalogHealthIndicator.class);
            });
}
~~~

`withBean` registers the fixture before the context is refreshed. `FakeCatalogSdk` is a test fixture matching the SDK's API; in a real project you can use a fake implementation, mock, or factory creating a test SDK.

### 5.2. Branch Where the Application Supplies Its Own Implementation

When the user has already registered a `CatalogClient`, the default bean must back off:

~~~java
@Configuration(proxyBeanMethods = false)
static class CustomCatalogConfiguration {

    @Bean
    CatalogClient catalogClient() {
        return new CachedCatalogClient();
    }
}

@Test
void backsOffWhenApplicationProvidesClient() {
    contextRunner
            .withBean(CatalogSdk.class, FakeCatalogSdk::new)
            .withUserConfiguration(CustomCatalogConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(CatalogClient.class);
                assertThat(context.getBean(CatalogClient.class))
                        .isInstanceOf(CachedCatalogClient.class);
                assertThat(context)
                        .hasSingleBean(CatalogHealthIndicator.class);
            });
}
~~~

This test verifies the starter's extension contract: the default bean is only created when no matching bean already exists. The application can swap the implementation without excluding the entire auto-configuration.

If you need to verify that the exact instance is used, create the custom object upfront, register it via supplier, and assert `isSameAs`. That is useful when the bean holds state or is a mock with specific expectations.

## 6. Testing Classpath Conditions with FilteredClassLoader

An optional dependency may be present on the test classpath yet absent in a user's application. `FilteredClassLoader` simulates the case where a class cannot be seen by the ApplicationContext.

~~~java
import org.springframework.boot.test.context.FilteredClassLoader;

@Test
void doesNotCreateSdkIntegrationWhenSdkClassIsMissing() {
    contextRunner
            .withClassLoader(new FilteredClassLoader(CatalogSdk.class))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .doesNotHaveBean(CatalogClient.class);
                assertThat(context)
                        .doesNotHaveBean(CatalogHealthIndicator.class);
            });
}
~~~

This test is especially valuable when auto-configuration has optional dependencies. If code references the SDK class in an outer configuration, method signature, or annotation in an unguarded way, the test can catch the class-loading error.

`FilteredClassLoader` only affects the classloader of the context under test. It does not remove JARs from the build or alter the test process classpath.

### 6.1. Distinguishing Missing Class from Missing Bean

Two scenarios are often confused:

- **Missing class:** the SDK is not on the runtime classpath; `ConditionalOnClass` does not match.
- **Missing bean:** the SDK class is present, but there is no `CatalogSdk` bean; `ConditionalOnBean` does not match.

You can test the missing-bean branch with a separate test:

~~~java
@Test
void doesNotCreateClientWhenSdkBeanIsMissing() {
    contextRunner.run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context).doesNotHaveBean(CatalogClient.class);
        assertThat(context).doesNotHaveBean(CatalogHealthIndicator.class);
    });
}
~~~

Without this test, an implementation might accidentally assume classpath presence implies the bean already exists. Testing both conditions separately clarifies the auto-configuration's contract.

## 7. Testing Dependent Beans with ConditionalOnBean

`CatalogHealthAutoConfiguration` only creates the health indicator when a `CatalogClient` bean exists. You can test this directly without importing the client-creating auto-configuration:

~~~java
@Test
void doesNotCreateHealthIndicatorWithoutClient() {
    new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    CatalogHealthAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .doesNotHaveBean(CatalogHealthIndicator.class);
            });
}
~~~

At the same time, test the branch with a user-provided client without the SDK:

~~~java
@Test
void createsHealthIndicatorForUserProvidedClientWithoutSdk() {
    new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    CatalogHealthAutoConfiguration.class))
            .withUserConfiguration(CustomCatalogConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(CatalogClient.class);
                assertThat(context)
                        .hasSingleBean(CatalogHealthIndicator.class);
            });
}
~~~

The second test confirms that the health auto-configuration depends on the `CatalogClient` contract rather than how the client was created. This is the benefit of depending on an interface instead of a concrete SDK implementation.

## 8. Testing Properties and ConfigurationProperties

Auto-configuration often branches on properties or binds properties into configuration objects. `withPropertyValues` lets you set specific values per test.

Suppose the module has properties:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public class CatalogClientProperties {

    private Duration timeout = Duration.ofSeconds(2);

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Because `CatalogSdkAutoConfiguration` uses `EnableConfigurationProperties(CatalogClientProperties.class)`, the runner can verify binding:

~~~java
@Test
void bindsCatalogClientProperties() {
    contextRunner
            .withPropertyValues(
                    "catalog.client.timeout=750ms")
            .run(context -> {
                assertThat(context).hasNotFailed();

                CatalogClientProperties properties =
                        context.getBean(CatalogClientProperties.class);

                assertThat(properties.getTimeout())
                        .isEqualTo(Duration.ofMillis(750));
            });
}
~~~

If auto-configuration uses `ConditionalOnProperty`, write at least two tests: property enabled and property disabled. Assert whether the bean exists or not in the context rather than only asserting the Environment value.

Example condition:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class CatalogMetricsAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "catalog.client",
            name = "metrics-enabled",
            havingValue = "true")
    CatalogMetrics catalogMetrics() {
        return new CatalogMetrics();
    }
}
~~~

Dedicated runner for this auto-configuration:

~~~java
private final ApplicationContextRunner metricsRunner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        CatalogMetricsAutoConfiguration.class));
~~~

Test when enabled:

~~~java
@Test
void createsMetricsWhenEnabled() {
    metricsRunner
            .withPropertyValues("catalog.client.metrics-enabled=true")
            .run(context ->
                    assertThat(context).hasSingleBean(CatalogMetrics.class));
}
~~~

Test when the property is set to `false`:

~~~java
@Test
void doesNotCreateMetricsWhenDisabled() {
    metricsRunner
            .withPropertyValues("catalog.client.metrics-enabled=false")
            .run(context ->
                    assertThat(context).doesNotHaveBean(CatalogMetrics.class));
}
~~~

Test when the property is omitted:

~~~java
@Test
void doesNotCreateMetricsWhenPropertyIsMissing() {
    metricsRunner.run(context ->
            assertThat(context).doesNotHaveBean(CatalogMetrics.class));
}
~~~

The separate test for the omitted property confirms default behavior. Keep enabled, disabled, and omitted as independent tests so you know exactly which branch failed.

## 9. Testing Auto-Configuration Ordering

When auto-configuration B uses `ConditionalOnBean` to depend on a bean created by auto-configuration A, import ordering matters.

In the Catalog example:

- `CatalogSdkAutoConfiguration` creates the default `CatalogClient` if conditions match.
- `CatalogHealthAutoConfiguration` is declared `after` the Catalog SDK configuration.
- The health indicator is only created if the `CatalogClient` contract is present in the context.

Combining `ApplicationContextRunner` with `AutoConfigurations.of(...)` tests the auto-configuration flow according to Spring Boot's ordering mechanism. Do not replace this test with a regular test configuration declaring both beans upfront, as that no longer tests actual ordering and conditions.

If a condition unexpectedly fails to match:

1. Verify the auto-configuration is imported.
2. Check ordering metadata.
3. Verify the dependency bean is registered before the condition is evaluated.
4. Check the type/bean name that the condition is looking for.
5. Use the Condition Evaluation Report to inspect positive/negative matches.

`AutoConfigureAfter` only adjusts relative ordering. It does not guarantee the dependency bean exists and does not replace testing the missing-bean branch.

## 10. Web and Reactive Auto-Configuration Runners

`ApplicationContextRunner` fits auto-configurations that do not need a web environment. If configuration depends on the `ApplicationContext` type or web-specific beans, use the matching runner:

| Runner | Environment |
| --- | --- |
| ApplicationContextRunner | Standard ApplicationContext |
| WebApplicationContextRunner | Servlet web application context |
| ReactiveWebApplicationContextRunner | Reactive web application context |

Servlet example:

~~~java
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;

private final WebApplicationContextRunner webRunner =
        new WebApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        CatalogWebAutoConfiguration.class));
~~~

Reactive example:

~~~java
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;

private final ReactiveWebApplicationContextRunner reactiveRunner =
        new ReactiveWebApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        CatalogReactiveAutoConfiguration.class));
~~~

These runners still support configuring properties, user configurations, beans, and classloaders in the same way. They let you test conditions that depend on web application type without opening a real HTTP port.

If the goal is to test HTTP endpoints, filter chains, serialization, or request routing, combine with `WebMvcTest`, `WebFluxTest`, `MockMvc`, `WebTestClient`, or appropriate integration tests. Runners verify bean configuration creation; they do not replace HTTP protocol testing.

## 11. Reading Errors When the Context Fails to Start

Inside the `run` callback, the context may fail to refresh due to missing bean dependencies, invalid configuration, or initialization errors. The runner still lets you inspect startup failures.

Example:

~~~java
@Test
void reportsStartupFailureForInvalidConfiguration() {
    contextRunner
            .withPropertyValues("catalog.client.timeout=not-a-duration")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .isNotNull();
            });
}
~~~

Do not just assert `hasFailed()` and stop. When investigating failures, check the exception cause to distinguish binding errors, missing dependencies, or bean creation failures.

For tests expected to start cleanly, place `hasNotFailed()` at the top of the callback so failure causes show clearly. Then assert specific beans and properties.

### 11.1. Condition Evaluation Report

When a bean does not appear, you can inspect the context's Condition Evaluation Report to see which conditions matched or failed to match. This is helpful when multiple auto-configurations conditionally register beans.

Avoid relying on internal Spring Boot classes when the test only needs to verify public behavior. Prefer bean presence/absence assertions; read the report only when diagnosing causes.

## 12. Test Matrix for the Catalog Example

A good test suite must verify independent conditional branches:

| SDK class | SDK bean | Custom CatalogClient | Expected result |
| --- | --- | --- | --- |
| Yes | Yes | No | Creates default client and health indicator |
| Yes | Yes | Yes | Uses custom client; default client backs off |
| Yes | No | No | Does not create client or health indicator |
| No | No | No | Skips SDK integration |
| No | No | Yes | Keeps custom client; health indicator can still be created |
| Yes | Yes | No, metrics property off | Client exists; metrics bean is not created |

Besides the matrix above, test property binding, auto-configuration ordering, configuration errors, and profile conditions if the module supports them.

A test suite does not need to assert every bean in the entire application. Focus on the auto-configuration's contract: which beans it provides, which conditions cause them to appear, and how the application can replace them.

## 13. Common Mistakes and How to Avoid Them

1. **Only testing that the context starts:** add bean presence/absence assertions for each conditional branch.
2. **Not testing when an optional class is absent:** use `FilteredClassLoader` to catch class-loading bugs.
3. **Confusing classpath presence with bean existence:** write a separate test where the class is present but the SDK bean is missing.
4. **Using `withUserConfiguration` instead of `AutoConfigurations`:** import auto-configurations via `AutoConfigurations.of` to test real ordering.
5. **Not testing user overrides:** verify the default bean backs off when the application supplies its own implementation.
6. **Not testing missing and disabled properties:** verify both default behavior and explicit values.
7. **Testing multiple conditions in one case:** split cases so you know which condition failed.
8. **Using `ApplicationContextRunner` for web-specific conditions:** choose `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner`.
9. **Only asserting context failed:** inspect the startup failure and root cause.
10. **Testing against internal implementations:** prefer verifying beans and public behavior.
11. **Forgetting to test auto-configuration imports metadata:** importing classes directly in the runner does not prove the imports file is packaged correctly.
12. **Not verifying ordering:** use real auto-configurations and declare appropriate before/after ordering.

## 14. Workflow for Writing Auto-Configuration Tests

When adding an auto-configuration to a Spring Cloud module, you can follow these steps:

1. List each condition: classpath, bean, missing bean, property, and web application type.
2. Create a runner with `AutoConfigurations.of(...)` for the exact auto-configurations under test.
3. Write the default branch test when all dependencies are present.
4. Write the missing-class branch test using `FilteredClassLoader`.
5. Write the branch test where the class exists but the bean does not.
6. Write the user bean override test to verify the missing-bean condition.
7. Write tests for enabled, disabled, and omitted properties.
8. Write dependent bean tests to verify `ConditionalOnBean` and ordering.
9. Use the appropriate web runner if auto-configuration depends on a servlet/reactive context.
10. Inspect startup failures and the Condition Evaluation Report when diagnosing issues.
11. Separately test auto-configuration registration metadata in the packaged artifact.
12. Add integration tests when you need to verify live connections, protocols, or behavior outside the ApplicationContext.

**Key takeaway:** ApplicationContextRunner enables testing auto-configuration in a small context with controlled classpath, properties, and input beans. Combine `AutoConfigurations.of`, `withBean`, `withUserConfiguration`, `withPropertyValues`, and `FilteredClassLoader` to verify conditional branches, default beans, and user overrides. Use web runners when configuration depends on a web context, while real HTTP flows or registry connections require separate integration tests. A strong test suite proves auto-configuration works when dependencies are present, when they are missing, and when the application customizes behavior in **SPRING_CLOUD_CORE**.

## References

- [Spring Boot — Testing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing)
- [Spring Boot API — ApplicationContextRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot API — FilteredClassLoader](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/FilteredClassLoader.html)
- [Spring Boot API — WebApplicationContextRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html)
