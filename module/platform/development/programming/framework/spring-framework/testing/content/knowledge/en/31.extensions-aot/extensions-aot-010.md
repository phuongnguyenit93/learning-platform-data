# Only Extend Infrastructure When Built-in Configuration Does Not Suffice

The Spring TestContext Framework already provides many mechanisms for configuring tests: `@ContextConfiguration`, `@SpringBootTest`, `@TestPropertySource`, `@DynamicPropertySource`, `@ActiveProfiles`, `@Import`, `@TestConfiguration`, `ApplicationContextInitializer`, and related annotations. In most projects, these declarative mechanisms are sufficient to create an application context matching the test scenario.

You should only write a custom extension when a recurring requirement or an infrastructure rule cannot be expressed clearly with built-in mechanisms. When extending is necessary, choose the narrowest extension point that satisfies the need. A custom initializer for a small change is usually easier to understand and has less blast radius than a custom `TestContextBootstrapper` altering how every test is initialized.

## 1. Start from Built-in Configuration

Before creating an extension, identify precisely what the test needs to change: which beans are loaded, which properties must be set, which profiles must be activated, which resources must be initialized, or which lifecycle events must be observed.

| Need | Built-in Mechanism to Try First |
|---|---|
| Selecting configuration or context resources | `@ContextConfiguration(classes = ...)`, `locations = ...` |
| Loading full Spring Boot configuration | `@SpringBootTest` |
| Adding test-only configuration | `@TestConfiguration`, `@Import` |
| Setting static properties for tests | `@TestPropertySource`, `@SpringBootTest(properties = ...)` |
| Injecting URLs or ports of running resources into context | `@DynamicPropertySource` |
| Selecting profiles | `@ActiveProfiles` |
| Selecting profiles via custom rules | `ActiveProfilesResolver` |
| Running logic before context refresh | `ApplicationContextInitializer` |
| Adding behavior around Spring's test lifecycle | `TestExecutionListener` |
| Customizing the context by test annotations or metadata | `ContextCustomizerFactory` |
| Loading contexts from special sources or environments | Custom `SmartContextLoader` |
| Changing how Spring TestContext merges configuration and bootstraps | Custom `TestContextBootstrapper` |

For example, if you only need to enable a feature flag in a test, using a property directly is usually enough:

```java
@SpringBootTest(properties = "feature.catalog.enabled=true")
class CatalogFeatureTests {
    // Test the feature when enabled.
}
```

If multiple tests need the same profile or property, group the configuration into a shared annotation or configuration class before creating a custom SPI. The goal is to clarify test configuration, not to add an extra infrastructure layer just to replace a few lines of annotations.

## 2. Choose the Narrowest Extension Point

Spring TestContext has extension points at multiple levels:

```text
Test class and annotations
        |
        v
TestContextBootstrapper
  Merges metadata, loader, listeners, and customizers
        |
        v
ContextLoader / SmartContextLoader
  Creates or loads ApplicationContext
        |
        v
ContextCustomizerFactory -> ContextCustomizer
  Adjusts context based on test metadata
        |
        v
ApplicationContextInitializer
  Initializes context before refresh
        |
        v
ApplicationContext is refreshed
        |
        v
TestExecutionListener
  Observes test class/method lifecycle
```

The diagram illustrates the primary roles; not every callback is called directly in the exact sequence shown in every configuration. Actual order depends on the bootstrapper, context loader, and `TestContext` lifecycle.

Choose by scope:

- Changing properties or registering configuration before refresh: initializer.
- Applying an annotation-driven customization across many tests: context customizer factory.
- Performing behavior at Spring Test lifecycle milestones: test execution listener.
- Changing how resources are read or contexts created: context loader.
- Replacing the overall bootstrap algorithm: test context bootstrapper.

Do not pick an extension with a broader scope than needed. The higher up in the bootstrap layer you intervene, the more default Spring Test behavior can be affected.

## 3. `ApplicationContextInitializer` for Context Initialization

`ApplicationContextInitializer` is invoked during context preparation, before the context is refreshed. It fits when you need to add a property source, register startup configuration, or apply a controlled change to `ConfigurableApplicationContext`.

Example creating an initializer to add a test property source:

```java
import java.util.Map;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;

public class TestFeatureInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        Map<String, Object> properties = Map.of(
            "feature.catalog.enabled", "true",
            "feature.catalog.source", "test"
        );

        context.getEnvironment().getPropertySources().addFirst(
            new MapPropertySource("catalogTestProperties", properties)
        );
    }
}
```

Registering the initializer on a test:

```java
import org.springframework.test.context.ContextConfiguration;

@ContextConfiguration(
    classes = CatalogConfiguration.class,
    initializers = TestFeatureInitializer.class
)
class CatalogFeatureTests {
}
```

`addFirst(...)` places the property source at higher precedence than subsequent property sources. Therefore, only use this approach when the test genuinely needs to override values. If only a single test needs a property, `@TestPropertySource` or the `properties` attribute on `@SpringBootTest` is usually simpler.

### When to Use `@DynamicPropertySource`?

If values are available only after a test resource starts—such as the URL of Testcontainers or a mock server—`@DynamicPropertySource` usually expresses intent more clearly than an initializer:

```java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

class ExternalServiceTests {

    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("catalog.base-url", () -> mockServerUrl());
    }
}
```

`DynamicPropertyRegistry` accepts a supplier to fetch the value when the property is accessed. In real tests, `mockServerUrl()` must return a URL from a resource that has already started and has a lifecycle matching the context. Do not write a custom initializer just to inject a dynamic URL into the environment when `@DynamicPropertySource` already handles the requirement.

## 4. `ContextCustomizerFactory` for Annotation-Driven Customization

An `ApplicationContextInitializer` declared directly on a test suits a few known tests. When you need to apply an annotation-based rule across many tests without repeating initializer declarations, you can create a `ContextCustomizerFactory`.

For example, define an annotation marking tests that need a property enabled:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface EnableCatalogTestMode {
}
```

The factory checks the annotation on the test class and returns a customizer if needed:

```java
import java.util.List;

import org.springframework.test.context.ContextConfigurationAttributes;
import org.springframework.test.context.ContextCustomizer;
import org.springframework.test.context.ContextCustomizerFactory;

public class CatalogTestContextCustomizerFactory
        implements ContextCustomizerFactory {

    @Override
    public ContextCustomizer createContextCustomizer(
            Class<?> testClass,
            List<ContextConfigurationAttributes> configAttributes) {

        if (testClass.isAnnotationPresent(EnableCatalogTestMode.class)) {
            return new CatalogTestContextCustomizer();
        }
        return null;
    }
}
```

The customizer modifies the environment before context refresh:

```java
import java.util.Map;

import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.test.context.ContextCustomizer;
import org.springframework.test.context.MergedContextConfiguration;

public final class CatalogTestContextCustomizer implements ContextCustomizer {

    @Override
    public void customizeContext(
            ConfigurableApplicationContext context,
            MergedContextConfiguration mergedConfig) {

        context.getEnvironment().getPropertySources().addFirst(
            new MapPropertySource(
                "catalogTestMode",
                Map.of("feature.catalog.mode", "test")
            )
        );
    }

    @Override
    public boolean equals(Object other) {
        return other != null && other.getClass() == getClass();
    }

    @Override
    public int hashCode() {
        return getClass().hashCode();
    }
}
```

For Spring TestContext to discover the factory, register it in `META-INF/spring.factories` of the test module or shared test library:

```properties
org.springframework.test.context.ContextCustomizerFactory=\
com.example.testing.CatalogTestContextCustomizerFactory
```

Then tests can declare:

```java
@EnableCatalogTestMode
@SpringBootTest
class CatalogFeatureTests {
}
```

`ContextCustomizer` is part of the merged context configuration. `equals()` and `hashCode()` must reflect configuration state that affects the context. In the example above, the customizer has no parameters, so two instances of the same class are equivalent. If a customizer holds values that vary by test, those values must participate in `equals()` and `hashCode()` so Spring does not mistakenly reuse a context created with a different configuration.

Because factories are discovered via the classpath, they can broadly affect tests in the module. Register this SPI only when the rule is truly shared; for an individual test, declaring `initializers` or configuring properties directly is more readable.

## 5. `TestExecutionListener` for the Spring Test Lifecycle

`TestExecutionListener` receives callbacks at phases of the Spring TestContext lifecycle, such as preparing the test instance, before and after a test method, or before and after a test class. It suits infrastructure behavior that must run consistently at Spring Test lifecycle points.

Spring provides `AbstractTestExecutionListener` so you only override the callbacks you need:

```java
import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public class TestAuditListener extends AbstractTestExecutionListener {

    @Override
    public void beforeTestMethod(TestContext testContext) {
        String methodName = testContext.getTestMethod().getName();
        System.out.println("Starting Spring test: " + methodName);
    }

    @Override
    public void afterTestMethod(TestContext testContext) {
        String methodName = testContext.getTestMethod().getName();
        System.out.println("Finished Spring test: " + methodName);
    }
}
```

Register the listener on a test while preserving default listeners:

```java
import org.springframework.test.context.TestExecutionListeners;

@TestExecutionListeners(
    listeners = TestAuditListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class CatalogServiceTests {
}
```

`MERGE_WITH_DEFAULTS` is critical when you only want to add a listener. If the default list is replaced unintentionally, the listeners Spring provides for dependency injection, transactions, or other test features may stop working as before.

If the requirement pertains only to JUnit Jupiter's own lifecycle, a JUnit extension such as `BeforeEachCallback` or `AfterEachCallback` may fit better. Use `TestExecutionListener` when you need integration with `TestContext`, `ApplicationContext`, or the lifecycle managed by Spring Test.

## 6. `ActiveProfilesResolver` for Profile Selection Rules

If profiles are selected by a custom rule, `ActiveProfilesResolver` lets you compute the profile list based on the test class:

```java
import org.springframework.core.env.Profiles;
import org.springframework.test.context.ActiveProfilesResolver;

public class EnvironmentProfileResolver implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        if (testClass.isAnnotationPresent(UseExternalSystemProfile.class)) {
            return new String[] {"test", "external"};
        }
        return new String[] {"test"};
    }
}
```

Declaring the resolver:

```java
@ActiveProfiles(resolver = EnvironmentProfileResolver.class)
class ExternalCatalogTests {
}
```

This is a narrow extension dedicated to selecting profiles. If you only need to activate fixed profiles, `@ActiveProfiles("test")` is simpler and clearer. Do not let a resolver depend on environment variables that change unpredictably between AOT processing and test execution.

## 7. Custom `ContextLoader` and `TestContextBootstrapper`

`ContextLoader` or `SmartContextLoader` is responsible for loading or creating an `ApplicationContext` from test configuration. Spring already provides loaders for standard cases like Java configuration, XML, and web contexts. Only write a custom loader when tests must create a context from a special source or environment unsupported by built-in loaders.

A loader can be specified on `@ContextConfiguration`:

```java
@ContextConfiguration(
    classes = CatalogConfiguration.class,
    loader = CustomCatalogContextLoader.class
)
class CatalogContextTests {
}
```

`TestContextBootstrapper` sits at a higher level: it decides how Spring Test merges metadata, selects the context loader, listeners, and other bootstrap components. `@BootstrapWith` lets you specify a custom bootstrapper:

```java
@BootstrapWith(CustomCatalogTestBootstrapper.class)
class CatalogInfrastructureTests {
}
```

This choice has major impact on the entire test initialization pipeline. Use it only when narrower extension points cannot meet the need. When replacing the bootstrapper, you must understand the defaults Spring provides and ensure annotations like `@ContextConfiguration`, `@WebAppConfiguration`, `@ActiveProfiles`, and `@TestPropertySource` still behave according to the expected contract.

## 8. Keeping the Context Cache Working Properly

Spring TestContext caches `ApplicationContext` instances based on merged configuration. Adding customizers or altering how bootstrapping works can change cache keys and the number of contexts created.

When writing a customizer:

- Configuration affecting the context must be represented in `equals()` and `hashCode()`.
- Do not include objects with random identity in a customizer if two tests with equivalent configuration should share a context.
- Avoid creating per-test-method resources inside a singleton context without a clear management mechanism.
- Do not read continuously mutating global state to determine context setup when the factory is invoked.
- Use `@DirtiesContext` when a test genuinely corrupts the context and needs it evicted from the cache, not as a synchronization lock or a way to clean up every out-of-context resource.

For example, if a customizer takes a `tenantId`, two different tenants may need separate contexts when the tenant configures beans. In that case, `tenantId` must participate in equality. If the tenant is merely per-request data, passing it via the request or Reactor Context is better than creating an application context per tenant.

## 9. Compatibility with `TestContext` AOT

Spring Framework supports ahead-of-time processing for test contexts. During the build phase, Spring can analyze test configuration and generate context initialization code to reduce work at test runtime. This is especially important for applications using Spring AOT or native images.

When writing extensions, distinguish two phases:

- **AOT processing:** Spring analyzes test classes, configuration, and application contexts to generate metadata or initialization code.
- **Runtime:** tests use the context prepared from AOT results or a context created via the standard runtime mechanism.

An extension that works in standard runtime is not guaranteed to be compatible with AOT. For example, an extension relying on arbitrary classpath scanning, reading files existing only on a developer machine, generating dynamic classes, or inferring configuration from runtime environment state may not be fully reflected in AOT output.

When AOT support is required:

1. Prefer annotations and static configuration that Spring can analyze.
2. Keep customizers and initializers deterministic and repeatable for the same input metadata.
3. Avoid depending on filesystem paths or environment variables that vary between build and runtime.
4. If code requires reflection, resources, or proxies not statically discoverable, declare appropriate runtime hints using Spring AOT mechanisms such as `RuntimeHintsRegistrar`.
5. Test extensions in both regular test mode and the AOT mode your project uses.

If a test cannot run in AOT mode because it depends on runtime behavior that cannot be predetermined, Spring Framework provides `@DisabledInAotMode` in supported versions (Spring Framework 6.2 and later). Use this annotation only when the test is genuinely incompatible with AOT; do not use it to mask an extension that could be redesigned.

## 10. Runtime Hints When Extensions Use Reflection or Resources

In a native image environment, operations relying on reflection, resource loading, or dynamic proxies may need metadata provided ahead of time. Spring AOT supplies a runtime hints API to declare those needs.

Example of a registrar:

```java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class CatalogTestRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
            CatalogPayload.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
```

Register the registrar with `@ImportRuntimeHints` on the relevant configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration
@ImportRuntimeHints(CatalogTestRuntimeHints.class)
class CatalogTestConfiguration {
}
```

This is an illustrative example of declaring reflection hints; the member categories registered must match actual usage. Do not add broad hints for every class or every method if the application only needs a specific constructor or method. If an extension does not use reflection, resources, or dynamic proxies, there is no need to add a registrar just because AOT is enabled.

## 11. Signs That an Extension Is Overly Complex

Revisit the design if:

- An extension merely sets a single property that built-in annotations already handle.
- A custom bootstrapper is written just to add one listener.
- A global factory alters the context for every test even though only one group of tests needs that behavior.
- A customizer reads random state, making cache keys unpredictable.
- An extension creates resources without a clear lifecycle cleanup mechanism.
- Tests pass only when run individually because the extension uses static mutable state.
- AOT processing and runtime produce different configurations.
- `@DirtiesContext` is added to many tests to work around conflicts caused by the extension.

In these situations, step back to identify the real requirement and try a narrower configuration mechanism.

## 12. Decision Process for Whether to Extend Infrastructure

1. Describe what the test needs: properties, profiles, beans, context, resources, or lifecycle.
2. Check built-in annotations and hooks such as `@TestPropertySource`, `@DynamicPropertySource`, `@Import`, initializers, or resolvers.
3. If logic is needed before refresh, choose `ApplicationContextInitializer`.
4. If metadata- or annotation-based customization must apply across many tests, consider `ContextCustomizerFactory`.
5. If callbacks at Spring Test lifecycle points are needed, choose `TestExecutionListener` and merge with default listeners.
6. Choose a custom loader or bootstrapper only when you must change how contexts are created or the overall bootstrap algorithm.
7. Verify cache keys, resource lifetimes, and the blast radius of the extension.
8. Check AOT compatibility; add runtime hints only when reflection, resources, or proxies genuinely require them.

Extending Spring TestContext should be a decision justified by a concrete limitation of existing configuration. Use built-in declarative mechanisms for common needs, pick the smallest extension point when custom logic is required, and keep extensions deterministic, with clear lifecycles, compatible with the context cache and AOT. This approach keeps test infrastructure readable, easy to upgrade, and prevents complicating unrelated tests.
