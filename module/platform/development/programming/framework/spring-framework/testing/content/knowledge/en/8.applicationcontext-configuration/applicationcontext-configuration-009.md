# ContextCustomizer and Its Impact on Test Configuration

In the Spring TestContext Framework, **ContextCustomizer** is an extension point for adjusting an ApplicationContext while Spring is creating the context for a test. It is invoked after the context is instantiated but before the context is refreshed. Because of this timing, tests can add property sources, register beans, or modify part of the configuration before Spring creates singletons and completes startup.

ContextCustomizer is commonly used when configuration must depend on the test class itself or test metadata. For example, a test class declares a custom annotation to choose a service region, a group of tests needs to supply a replacement bean, or a test needs to register properties dynamically provided by a test resource.

The two main components are:

- **ContextCustomizer**: applies modifications to the ConfigurableApplicationContext.
- **ContextCustomizerFactory**: inspects the test class and creates the corresponding ContextCustomizer.

Crucially, ContextCustomizer participates in both creating and caching the ApplicationContext. The configuration it adds can affect beans, properties, and behavior across every test class sharing that context. Therefore, a customizer needs clear inputs, deterministic behavior, and proper equals/hashCode rules so Spring Test accurately identifies which contexts can be shared.

## 1. Where Does ContextCustomizer Fit in Test Context Creation?

A Spring test does not necessarily create a new ApplicationContext every time a test method runs. The TestContext Framework builds a merged configuration, uses it to look up a context in the cache, and creates a new context only when no matching one exists.

During bootstrapping:

1. Spring reads metadata from the test class such as @ContextConfiguration, @ActiveProfiles, and @TestPropertySource.
2. The TestContext Framework merges configuration metadata into MergedContextConfiguration.
3. ContextCustomizerFactory implementations are discovered and asked to create customizers for the test class.
4. The list of customizers is included in the merged configuration.
5. Spring checks the ApplicationContext cache using that configuration.
6. If a new context is needed, ContextLoader creates the context and invokes the customizers before refresh.
7. After a successful refresh, the context is placed in the cache so compatible tests can reuse it.

This flow can be visualized as follows:

~~~mermaid
flowchart TD
    A["Test class and annotations"] --> B["MergedContextConfiguration"]
    B --> C["ContextCustomizerFactory"]
    C --> D["ContextCustomizer"]
    D --> E["Build cache key"]
    E --> F{"Matching context already in cache?"}
    F -->|"Yes"| G["Reuse ApplicationContext"]
    F -->|"No"| H["ContextLoader creates context"]
    H --> I["ContextCustomizer customizes context"]
    I --> J["Refresh ApplicationContext"]
    J --> K["Store context in cache"]
    G --> L["Run test"]
    K --> L
~~~

ContextCustomizer can affect the environment, bean factory, or context settings before refresh. For example, a property source added before refresh can be read when Spring creates beans and resolves placeholders.

**A customizer is not a callback executed before each test method.** If an ApplicationContext is cached and reused, the customizer is not re-applied per method. It belongs to the context preparation phase.

## 2. The Two Core Interfaces

### ContextCustomizer

The interface resides in the package:

~~~java
import org.springframework.test.context.ContextCustomizer;
~~~

The main contract has one method:

~~~java
void customizeContext(
        ConfigurableApplicationContext context,
        MergedContextConfiguration mergedConfig
);
~~~

Where:

- context is the configurable ApplicationContext being prepared.
- mergedConfig holds the merged configuration of the test class, such as locations, classes, initializers, active profiles, property sources, context customizers, and context loader.

A customizer can use context.getEnvironment() to add property sources, or use the bean factory to register bean definitions. Because the method runs before refresh, changes participate in bean creation.

~~~java
public final class RegionContextCustomizer
        implements ContextCustomizer {

    private final String region;

    public RegionContextCustomizer(String region) {
        this.region = region;
    }

    @Override
    public void customizeContext(
            ConfigurableApplicationContext context,
            MergedContextConfiguration mergedConfig
    ) {
        Map<String, Object> properties =
                Map.of("service.region", region);

        context.getEnvironment()
                .getPropertySources()
                .addFirst(
                        new MapPropertySource(
                                "testRegion",
                                properties
                        )
                );
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof RegionContextCustomizer that)) {
            return false;
        }
        return region.equals(that.region);
    }

    @Override
    public int hashCode() {
        return region.hashCode();
    }
}
~~~

The example above adds the service.region property at the top of the configuration source list. If a lower-precedence source also defines this key, the test-supplied value takes precedence.

Implementing equals/hashCode based on region is especially significant for caching. Two customizers with the same region configuration are treated as equivalent; customizers with different regions will not be treated as the same configuration.

In Java 17 and later, you can use a record to get equals/hashCode based on data components automatically:

~~~java
record RegionContextCustomizer(String region)
        implements ContextCustomizer {

    @Override
    public void customizeContext(
            ConfigurableApplicationContext context,
            MergedContextConfiguration mergedConfig
    ) {
        context.getEnvironment()
                .getPropertySources()
                .addFirst(
                        new MapPropertySource(
                                "testRegion",
                                Map.of("service.region", region)
                        )
                );
    }
}
~~~

A record fits well when the customizer is an immutable configuration completely defined by its constructor values.

### ContextCustomizerFactory

The factory is responsible for deciding which test classes need a customizer and creating the corresponding customizer.

The interface resides in the package:

~~~java
import org.springframework.test.context.ContextCustomizerFactory;
~~~

Main method:

~~~java
ContextCustomizer createContextCustomizer(
        Class<?> testClass,
        List<ContextConfigurationAttributes> configAttributes
);
~~~

- testClass is the class being prepared for TestContext.
- configAttributes is the list of context configuration attributes discovered from the test class and related test hierarchy.
- The factory returns a ContextCustomizer if customization is needed; it can return null if the test class does not need that customizer.

Factories are commonly used to read custom annotations, inspect metadata, or determine values to pass into the context.

## 3. Complete Example: Annotation Selecting a Service Region

Suppose the application has a service.region property. Each test class can choose its own region without editing application.yml or changing the machine's environment.

### Step 1: Declare the Test Annotation

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface TestRegion {
    String value();
}
~~~

The annotation is placed on the test class:

~~~java
@TestRegion("test-southeast")
@SpringJUnitConfig(RegionTestConfiguration.class)
class SoutheastRegionTest {
    // Tests
}
~~~

### Step 2: Create the ContextCustomizer

~~~java
import java.util.Map;

import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.test.context.ContextCustomizer;
import org.springframework.test.context.MergedContextConfiguration;

public record TestRegionContextCustomizer(String region)
        implements ContextCustomizer {

    @Override
    public void customizeContext(
            ConfigurableApplicationContext context,
            MergedContextConfiguration mergedConfig
    ) {
        context.getEnvironment()
                .getPropertySources()
                .addFirst(
                        new MapPropertySource(
                                "testRegion",
                                Map.of("service.region", region)
                        )
                );
    }
}
~~~

The customizer does one thing: puts the selected region value into the Environment before context refresh.

### Step 3: Create the ContextCustomizerFactory

~~~java
import java.util.List;

import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.test.context.ContextConfigurationAttributes;
import org.springframework.test.context.ContextCustomizer;
import org.springframework.test.context.ContextCustomizerFactory;

public class TestRegionContextCustomizerFactory
        implements ContextCustomizerFactory {

    @Override
    public ContextCustomizer createContextCustomizer(
            Class<?> testClass,
            List<ContextConfigurationAttributes> configAttributes
    ) {
        TestRegion annotation =
                AnnotatedElementUtils.findMergedAnnotation(
                        testClass,
                        TestRegion.class
                );

        if (annotation == null) {
            return null;
        }

        return new TestRegionContextCustomizer(annotation.value());
    }
}
~~~

AnnotatedElementUtils.findMergedAnnotation searches for the annotation using Spring's merged annotation mechanism, including composed or inherited annotation cases according to supported rules.

If the test class does not declare @TestRegion, the factory needs no extra configuration and returns null. If present, the factory creates a customizer with the annotation's value.

### Step 4: Register the Factory

Spring Test discovers ContextCustomizerFactory implementations via SpringFactoriesLoader. Register the factory in:

~~~text
src/test/resources/META-INF/spring.factories
~~~

Contents:

~~~properties
org.springframework.test.context.ContextCustomizerFactory=\
com.example.test.TestRegionContextCustomizerFactory
~~~

Replace com.example.test with the actual package containing your factory.

This file must be on the test runtime classpath. If the factory resides in a shared test library, register it in that library's resources so consuming modules can discover the factory.

### Step 5: Use the Property in Application Configuration

~~~java
@Configuration
class RegionTestConfiguration {

    @Bean
    RegionService regionService(Environment environment) {
        return new RegionService(
                environment.getRequiredProperty("service.region")
        );
    }
}
~~~

Test the service:

~~~java
@TestRegion("test-southeast")
@SpringJUnitConfig(RegionTestConfiguration.class)
class SoutheastRegionTest {

    @Autowired
    private RegionService regionService;

    @Test
    void usesRegionFromTestAnnotation() {
        assertEquals(
                "test-southeast",
                regionService.region()
        );
    }
}
~~~

When Spring creates the context for the test class:

1. The factory reads @TestRegion.
2. The factory creates TestRegionContextCustomizer.
3. Spring creates the context.
4. The customizer adds service.region to the Environment.
5. The context refreshes and creates RegionService.
6. RegionService reads the supplied property.

This example shows how ContextCustomizer turns metadata on a test class into ApplicationContext configuration.

## 4. Why Are ContextCustomizer equals and hashCode Important?

The Spring TestContext Framework caches ApplicationContexts to avoid reinitializing contexts with equivalent configurations. The cache key is based on MergedContextConfiguration. That merged configuration includes the set of ContextCustomizers, which participates in the configuration's equals/hashCode.

Therefore, a customizer is not just a callback invoked during context creation. It is also part of the identity of the context configuration.

There are two common design mistakes.

### Not Implementing Equality for a Stateful Customizer

Suppose a factory always instantiates a new object:

~~~java
return new RegionContextCustomizer(annotation.value());
~~~

If the customizer relies only on Object's default equals/hashCode, two instances with the same region still differ because of object identity. Spring may treat equivalent configurations as different and create multiple cache entries.

Consequences:

- ApplicationContexts are initialized repeatedly.
- The test suite runs slower.
- The cache consumes more entries.
- Tests that appear to share identical configuration fail to reuse a shared context.

Using a record or implementing equals/hashCode based on all configuration values affecting the context helps Spring recognize equivalence.

### Equality Ignoring Data That Alters the Context

A more dangerous case is when two customizers hold different configurations yet equals/hashCode treats them as equal.

For example, two test classes request different regions, but the customizer compares only class name. When cache keys are treated as identical, the second test can receive a context already created with the first test's region.

This is a test configuration bug that can be very hard to diagnose because each test passes when run alone, yet fails with incorrect configuration data when run together in a suite.

Design rules:

- Customizers should be immutable after creation.
- Equality must include every value that affects the context.
- Do not put per-test-method data into a customizer.
- Do not use current timestamps or random values in a customizer unless that value is an intentional part of the configuration.
- Factories must produce customizers with equal equality whenever configurations are genuinely equivalent.

## 5. Impact on the ApplicationContext Cache

MergedContextConfiguration contains many factors used to determine whether a context can be reused, such as:

- Resource locations and configuration classes.
- Context initializer classes.
- Context loader.
- Active profiles.
- Property source locations and inline properties.
- Parent context if in a hierarchy.
- Context customizers.

When a ContextCustomizer changes configuration, it can change the cache key. This is necessary when two tests require different contexts.

Example:

| Test class | Customizer | Can Context Be Shared? |
|---|---|---|
| SoutheastRegionTest | region = test-southeast | Can be shared with tests having the same configuration |
| SoutheastRegionAnotherTest | region = test-southeast | Can be reused if the remaining configuration is also equivalent |
| EuropeRegionTest | region = test-europe | Needs a different context because configuration differs |
| Test without TestRegion | Does not have this customizer | Does not share the same customizer configuration as the group above |

"Same" here applies to the entire MergedContextConfiguration, not just the customizer alone. The same region with different bean configuration, profiles, or property sources can still produce a different context.

### Customizers Do Not Re-Run When a Context Is Cached

If two test classes have equivalent configurations and the cache returns an existing context, Spring does not create a new context and does not re-run customizeContext for that reuse.

This means a customizer is not the right place to:

- Reset data before each test method.
- Generate new random data per test.
- Set state that varies by test order.
- Open resources where each test method needs a separate instance.
- Perform side effects that must re-run on every test.

Per-method tasks should use @BeforeEach, @AfterEach, an appropriate TestExecutionListener, or dedicated fixtures. Context-scoped resources can use bean lifecycles or resource management tied to the context.

## 6. ContextCustomizer Modifying Environment and Property Precedence

A common use case is adding a property source before context refresh. Example:

~~~java
context.getEnvironment()
        .getPropertySources()
        .addFirst(
                new MapPropertySource(
                        "customTestProperties",
                        Map.of(
                                "feature.search.enabled", "true",
                                "service.timeout", "1500"
                        )
                )
        );
~~~

addFirst puts the new source at the top of the list, so its values take precedence when multiple sources define the same key.

This warrants caution. If a customizer adds a source at a high-precedence position, it can override values declared in:

- @TestPropertySource.
- application-test.properties or application-test.yml.
- System properties.
- Environment variables.
- Other configuration sources already in the Environment.

Actual ordering depends on which sources Spring Boot or Spring Test has already registered and where the customizer inserts its source. Do not assume values in files always win over properties supplied by a customizer.

If you only need to add default values for tests, use addLast or check whether the key already exists before adding. If overriding is intentional, give the source a clear name and write tests asserting the final effective value.

### Example Verifying a Property Supplied by a Customizer

A context test can inject Environment and assert the value:

~~~java
@TestRegion("test-southeast")
@SpringJUnitConfig(RegionTestConfiguration.class)
class RegionEnvironmentTest {

    @Autowired
    private Environment environment;

    @Test
    void exposesRegionProperty() {
        assertEquals(
                "test-southeast",
                environment.getProperty("service.region")
        );
    }
}
~~~

This test verifies that the property source participated in the context. If the goal is to verify beans constructed from the property, test the corresponding bean rather than only asserting strings in Environment.

## 7. ContextCustomizer Can Register Beans or Modify the BeanFactory

Beyond Environment, a customizer receives ConfigurableApplicationContext. It can modify the bean factory before refresh.

For example, registering a test-only singleton:

~~~java
@Override
public void customizeContext(
        ConfigurableApplicationContext context,
        MergedContextConfiguration mergedConfig
) {
    context.getBeanFactory().registerSingleton(
            "testClock",
            Clock.fixed(
                    Instant.parse("2026-11-12T00:00:00Z"),
                    ZoneOffset.UTC
            )
    );
}
~~~

Beans created afterward can use the registered Clock according to autowiring type and bean name rules in the context.

For configurations needing full lifecycle management or bean definitions with scope/metadata, you can register a BeanDefinition instead of a singleton instance. Example:

~~~java
RootBeanDefinition definition =
        new RootBeanDefinition(TestClockProvider.class);

context.getBeanFactory().registerBeanDefinition(
        "testClockProvider",
        definition
);
~~~

Registering bean definitions must respect BeanFactory rules for bean names, dependencies, and processing order. If multiple customizers register the same name, establish a conflict policy rather than relying on arbitrary ordering.

Customizers should make predictable configuration changes. Avoid calling context.refresh() manually, eagerly instantiating all beans yourself, or accessing beans prematurely before the context finishes refreshing.

## 8. ContextCustomizer vs. Other Test Configuration Mechanisms

Spring has multiple mechanisms to supply configuration for tests. ContextCustomizer is a lower-level extension point, useful when configuration must be generated from test class metadata.

| Mechanism | How Configuration Is Supplied | When to Use |
|---|---|---|
| @TestPropertySource | Declares inline or file properties | Fixed properties, readable directly on the test |
| @ActiveProfiles | Selects profiles for the context | Configuring beans by profile |
| @ContextConfiguration(initializers = ...) | Declares ApplicationContextInitializer | When a specific, explicitly named initializer is needed |
| @DynamicPropertySource | Registers dynamic properties via suppliers | Runtime values such as Testcontainers host/port |
| @Import / @TestConfiguration | Adds configurations or beans | Tests needing explicit extra beans |
| ContextCustomizerFactory | Creates customizers based on test metadata | Reusable, auto-discovered customization rules |

### Comparison with ApplicationContextInitializer

ApplicationContextInitializer can also customize ConfigurableApplicationContext before refresh:

~~~java
public class RegionInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext context
    ) {
        context.getEnvironment()
                .getPropertySources()
                .addFirst(
                        new MapPropertySource(
                                "initializerProperties",
                                Map.of("service.region", "test-region")
                        )
                );
    }
}
~~~

Initializers are typically declared directly in @ContextConfiguration:

~~~java
@ContextConfiguration(
        classes = RegionConfiguration.class,
        initializers = RegionInitializer.class
)
~~~

Key differences:

- An initializer is declared as part of the test configuration, suitable for general or explicit initialization behavior.
- A ContextCustomizer is created through a factory, which can inspect the test class and ContextConfigurationAttributes to decide customization.
- ContextCustomizer is part of the customizer set in MergedContextConfiguration and participates in determining the cache key.
- A factory can automatically apply rules to test classes bearing certain annotations or metadata without declaring an initializer on every class.

If you only need to add a fixed property for one test, @TestPropertySource is usually easier to understand. If you need automatic logic based on annotations or test types, ContextCustomizerFactory fits better.

### Comparison with @DynamicPropertySource

@DynamicPropertySource allows registering properties via DynamicPropertyRegistry:

~~~java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("service.base-url", server::baseUrl);
}
~~~

This mechanism is commonly used with Testcontainers or test servers whose addresses are assigned at runtime. Spring Test has an internal ContextCustomizerFactory to detect and apply @DynamicPropertySource methods.

When the need is simply registering dynamic properties using existing APIs, prefer @DynamicPropertySource. There is no need to write a new factory just to replicate the same capability.

### Comparison with @TestConfiguration and @Import

If a test needs a replacement bean or additional configuration, you can declare @TestConfiguration and import it:

~~~java
@TestConfiguration
class TestClockConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-11-12T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

~~~java
@SpringBootTest
@Import(TestClockConfiguration.class)
class SubscriptionServiceTest {
    // Tests
}
~~~

This approach is explicit and easy to trace when configuration applies only to a known group of tests. ContextCustomizer is more useful when automating metadata-driven rules or packaging customization into reusable test infrastructure.

## 9. Practical Use Cases

### Adding Configuration via a Custom Annotation

A test class declares an annotation describing a test mode, and a factory reads the annotation to create a customizer that adds properties or beans. This lets tests declare intent instead of repeating setup.

For example, @TestRegion above could be extended to accept a profile, tenant name, or feature flag mode. However, annotations should only carry meaningful metadata. Avoid turning an annotation into an overly broad configuration DSL that makes tests hard to read.

### Registering Shared Mock or Fake Beans for a Group of Tests

A factory can recognize an annotation marking tests that need a fixed clock, fake client, or test-only bean. The customizer registers the bean before refresh so other beans can inject it.

For mock beans in a Spring context, prefer the bean-override mechanisms supported by your Spring or Spring Boot version. A customizer registering a singleton directly can work for simple cases, but requires managing names, types, candidate selection, and lifecycles carefully.

### Adding Properties Obtained from Test Resources

If a resource starts before the context and provides connection details, a customizer can place endpoints into the Environment. However, with Testcontainers, @DynamicPropertySource is usually a clearer and better-supported API for this goal.

Do not let a customizer start a heavy container or server itself if that resource can be managed with its own lifecycle. Context caching can keep the resource alive longer than a single test method; the resource lifecycle must match the context lifecycle.

### Applying Configuration Policies to a Category of Test Classes

A factory can inspect annotations, superclasses, or metadata to determine which tests need a shared customization. For example, every test class marked with @UsesTestTenant receives the corresponding tenant property.

Keep the boundary clear: the factory only creates a customizer from metadata. Actual changes to the ApplicationContext belong in customizeContext. Separating these responsibilities makes root-cause analysis easier: a bug lies either in metadata discovery or in applying the configuration.

## 10. Common Mistakes When Writing ContextCustomizers

### Customizer Holding Mutable State

If a customizer holds a Map or object that can be mutated after creation, equals/hashCode can change while the object is part of a cache key. This makes cache behavior unpredictable.

Make customizers immutable, copy input data if necessary, and never store per-test-method state.

### Factory Producing Different Customizers for Equivalent Configurations

If a customizer relies on identity equality, Spring treats every instantiation as a new configuration and reduces context reuse. Use a record or implement equals/hashCode over the values affecting the context.

### Equality Omitting Properties That Affect Configuration

If two customizers have different regions yet equals/hashCode ignores region, the cache may reuse a context with the wrong configuration. All values that alter Environment or bean definitions must participate in equality.

### Adding Property Sources at the Wrong Position

addFirst can override properties from other sources. If a test needs to verify default application configuration, the customizer might accidentally mask those values. Choose the source position deliberately and verify precedence.

### Registering Duplicate Bean Names

Two customizers or test configurations might register the same bean name. The outcome depends on how BeanFactory handles overrides and whether overrides are allowed. Use clearly scoped names, or use official bean-override mechanisms when replacing existing beans.

### Performing Side Effects While Customizing Context

Do not send HTTP requests, access production systems, or write business data inside customizeContext. This method runs during context creation and may run only once due to caching. Non-idempotent side effects make the test suite hard to reproduce.

### Using a Customizer to Reset Per-Test State

Customizers do not run before every method. If you need to reset mocks, repositories, or data before each test, use appropriate lifecycle hooks such as @BeforeEach, @AfterEach, test transactions, or dedicated listeners.

### Creating a Customizer for a Simple Property

If a test only needs a fixed property, @TestPropertySource is usually shorter. Writing a factory and registering spring.factories adds maintenance overhead without commensurate benefit.

## 11. Diagnosing Unexpected Context Configuration

When a bean or property does not have the expected value, isolate which phase failed:

**Factory is not discovered**

- Check whether META-INF/spring.factories is on the test runtime classpath.
- Check that the key is org.springframework.test.context.ContextCustomizerFactory.
- Verify the fully qualified class name, default constructor, and class visibility/loadability.
- Verify the test uses the TestContext Framework and the corresponding bootstrapper.

**Factory is called but does not create a customizer**

- Check whether the test class has the required annotation.
- Check whether the annotation has runtime retention.
- Check annotation lookup logic, meta-annotations, and class hierarchy.
- Check whether the factory returned null due to a non-matching condition.

**Customizer runs but property has no effect**

- Confirm the customizer added the property source to the right context.
- Check the key name and position in the property source list.
- Check whether a higher-precedence source overrode the property afterward.
- Confirm beans read the property after the customizer applied and the context refreshed.
- Check whether code is reading an independently created Environment.

**Test receives the wrong cached context**

- Check the customizer's equals/hashCode.
- Confirm all configuration parameters are included in equality.
- Check the other components of MergedContextConfiguration.
- Only use @DirtiesContext when a test genuinely mutates the context and needs eviction; do not use it to mask an equality bug.

**Tests pass individually but fail in the full suite**

- Check whether singleton beans hold mutable state.
- Check whether the customizer or factory holds static state.
- Check whether tests share a context with equivalent configurations.
- Check whether per-method data was mistakenly placed in a customizer.

## 12. Decision Guide: Should You Write a Custom ContextCustomizer?

Before creating a customizer, check which category your need falls into:

| Need | First Option to Consider |
|---|---|
| A fixed property for a test | @TestPropertySource |
| Selecting beans by profile | @ActiveProfiles and @Profile |
| Adding a test-only bean | @TestConfiguration and @Import |
| Dynamic properties from containers/servers | @DynamicPropertySource |
| An explicitly specified initializer | ApplicationContextInitializer |
| Customization rules based on annotations/metadata across many test classes | ContextCustomizerFactory |
| Replacing a bean in context with a mock | Spring/Boot bean-override mechanism for your version |

Writing a custom ContextCustomizer makes sense when you have a recurring configuration rule that depends on test class metadata and cannot be expressed concisely using built-in declarative APIs.

When implementing one, ensure:

1. The factory is discovered on the test runtime classpath.
2. The factory creates a customizer only when the test class actually needs it.
3. The customizer only modifies the context before refresh.
4. Configuration data is immutable and clearly defined.
5. equals/hashCode reflects all configuration affecting the context.
6. The customizer performs no per-test-method work.
7. Property precedence and bean names are controlled.
8. Tests can run independently and across the entire suite without order dependence.

ContextCustomizer is a powerful TestContext Framework extension because it turns test metadata into reusable ApplicationContext configuration. Yet its participation in context caching demands careful design. When customizers are immutable, equality is accurate, and configuration changes are tightly scoped, tests can safely share contexts while tests requiring distinct configurations still receive isolated contexts. When the need is just a simple property or bean, built-in annotations and initializers usually keep configuration easier to read.

