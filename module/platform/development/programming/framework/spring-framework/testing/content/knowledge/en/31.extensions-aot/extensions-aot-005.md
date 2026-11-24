# `ContextCustomizerFactory` and Contributing to the Cache Key

The Spring TestContext Framework creates and manages an `ApplicationContext` for integration tests. Because initializing a context can be time-consuming, Spring stores created contexts in a cache and reuses them when another test has an equivalent configuration. An important extension mechanism during the context preparation phase is `ContextCustomizerFactory`.

`ContextCustomizerFactory` allows a library or project to inspect a test class's metadata and create a `ContextCustomizer`. The customizer is applied to the `ConfigurableApplicationContext` before the context is refreshed. A customizer can add property sources, register bean definitions, or adjust the test environment. These customizers also become part of `MergedContextConfiguration`, which is used as the lookup key in the context cache.

This creates a crucial requirement: `ContextCustomizer` must implement `equals()` and `hashCode()` reflecting all information that changes the `ApplicationContext`. If two different configurations are treated as equal, Spring may reuse the wrong context. If two customizers have the same configuration but are always treated as unequal, the cache loses reuse capability and the suite runs more slowly.

## 1. Where Does `ContextCustomizerFactory` Fit in the TestContext Framework?

The Spring TestContext Framework uses `TestContextManager` to coordinate the test lifecycle and create `TestContext`. When an `ApplicationContext` needs to be loaded, Spring builds a `MergedContextConfiguration` from the test class metadata, including configuration sources and related customizations.

Part of the bootstrap process can be pictured as follows:

~~~~text
Test class
    |
    v
TestContextBootstrapper
    |
    +--> Read @ContextConfiguration, profiles, properties...
    |
    +--> Discover ContextCustomizerFactory
    |        |
    |        v
    |    createContextCustomizer(...)
    |        |
    |        v
    |    ContextCustomizer
    |
    v
MergedContextConfiguration
    |
    +--> Used as cache key
    |
    v
ContextCache
    |
    +--> Matching context exists? -- Yes --> Reuse context
    |                                          |
    |                                          v
    |                                        Test
    |
    +--> Not yet? ----> Create context
                          |
                          v
                   ContextCustomizer
                   customizeContext(...)
                          |
                          v
                   ApplicationContext refresh
                          |
                          v
                         Test
~~~~

The factory does not create the `ApplicationContext` directly. The factory only produces an object describing how to customize the context. Spring places the customizers into the merged configuration, uses that configuration to look up the cache, and applies the customizers if a new context must be created.

Two main interfaces:

- `ContextCustomizerFactory`: inspects test class metadata and creates a `ContextCustomizer`.
- `ContextCustomizer`: modifies `ConfigurableApplicationContext` before the context is refreshed.

These interfaces reside in the `org.springframework.test.context` package.

## 2. What Is the Responsibility of `ContextCustomizerFactory`?

`ContextCustomizerFactory` declares the method:

~~~~java
ContextCustomizer createContextCustomizer(
        Class<?> testClass,
        List<ContextConfigurationAttributes> configAttributes
);
~~~~

The factory receives the test class and the configuration attributes collected from `@ContextConfiguration`. Based on that metadata, the factory creates an appropriate customizer.

The factory can read:

- Custom annotations on the test class.
- Meta-annotations placed on other annotations.
- Attributes of `@ContextConfiguration`.
- The test type or class hierarchy structure if that is part of the test convention.
- Metadata needed to prepare property sources, beans, or context infrastructure.

A factory should generally not initialize external services, open database connections, or perform expensive work. Discovery happens while preparing the test configuration; the customizer is the object applied to the context when Spring needs to create a context.

A good factory has these characteristics:

- Produces deterministic results from test metadata.
- Does not depend on shared mutable state.
- Returns a customizer with stable `equals`/`hashCode`.
- Does not initialize contexts or manage its own cache.
- Describes only the changes actually needed for the `ApplicationContext`.

## 3. When Is `ContextCustomizer` Applied?

`ContextCustomizer` has the method:

~~~~java
void customizeContext(
        ConfigurableApplicationContext context,
        MergedContextConfiguration mergedConfig
);
~~~~

Spring calls this method during `ApplicationContext` preparation, before the context is refreshed. Therefore, a customizer is suitable for altering the environment or registering configuration that must be present before singleton beans are instantiated.

For example, a customizer can add a `MapPropertySource` to the `Environment`:

~~~~java
context.getEnvironment()
        .getPropertySources()
        .addFirst(propertySource);
~~~~

After the context refreshes, beans can read that property via `@Value`, `Environment`, or another configuration mechanism.

A customizer can also register bean definitions via the bean factory or appropriate context. However, if the need is simply declaring fixed beans for tests, `@TestConfiguration` or `@Import` is usually easier to understand. `ContextCustomizer` is valuable when the modification must be decided from test class metadata or needs to be packaged as a reusable mechanism.

Do not use a customizer to mutate an already-refreshed context. Singleton beans may have already been created and dependency injection completed. If configuration is needed before beans are initialized, perform it during the `customizeContext` phase.

## 4. Example: Custom Annotation to Select a Tenant for Tests

Suppose an application needs testing with different tenants. We want to write:

~~~~java
@SpringJUnitConfig(TenantTestConfig.class)
@TestTenant("north")
class NorthTenantTest {
    // Tests with tenant north.
}

@SpringJUnitConfig(TenantTestConfig.class)
@TestTenant("south")
class SouthTenantTest {
    // Tests with tenant south.
}
~~~~

Each test class needs an `ApplicationContext` with the corresponding `test.tenant-id` property. We can build a three-part mechanism:

1. The `@TestTenant` annotation holding the tenant identifier.
2. A `ContextCustomizerFactory` reading the annotation and creating the customizer.
3. A `ContextCustomizer` adding the property source before context refresh.

### Declaring the Annotation

~~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Inherited
public @interface TestTenant {
    String value();
}
~~~~

`@Retention(RUNTIME)` ensures the annotation is present when Spring reads metadata at runtime. `@Target(TYPE)` restricts the annotation to classes/interfaces. `@Inherited` allows the annotation to be inherited under Java rules from a superclass; if you need to support meta-annotations or complex merged attributes, use `AnnotatedElementUtils` when reading the annotation.

### Creating the `ContextCustomizer`

~~~~java
public final class TenantContextCustomizer implements ContextCustomizer {

    private final String tenantId;

    public TenantContextCustomizer(String tenantId) {
        this.tenantId = tenantId;
    }

    @Override
    public void customizeContext(
            ConfigurableApplicationContext context,
            MergedContextConfiguration mergedConfig
    ) {
        if (tenantId == null) {
            return;
        }

        Map<String, Object> properties = Map.of(
                "test.tenant-id", tenantId
        );

        MapPropertySource propertySource =
                new MapPropertySource("testTenant", properties);

        context.getEnvironment()
                .getPropertySources()
                .addFirst(propertySource);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof TenantContextCustomizer that)) {
            return false;
        }
        return Objects.equals(this.tenantId, that.tenantId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId);
    }
}
~~~~

`TenantContextCustomizer` keeps `tenantId` immutable. When the context is created, the customizer adds a high-priority property source so beans can read the selected tenant.

The key point is that `equals()` and `hashCode()` use `tenantId`. Two customizers for the same tenant can be treated as equal; two customizers with different tenants will not be equal.

If a customizer does not override `equals()` and `hashCode()`, Java uses identity equality inherited from `Object`. Each time the factory creates a new instance, those instances are treated as distinct even when holding the same `tenantId`. The context cache may fail to reuse contexts across tests with identical configuration.

### Creating the Factory

~~~~java
public final class TenantContextCustomizerFactory
        implements ContextCustomizerFactory {

    @Override
    public ContextCustomizer createContextCustomizer(
            Class<?> testClass,
            List<ContextConfigurationAttributes> configAttributes
    ) {
        TestTenant annotation =
                AnnotatedElementUtils.findMergedAnnotation(
                        testClass,
                        TestTenant.class
                );

        String tenantId = annotation != null
                ? annotation.value()
                : null;

        return new TenantContextCustomizer(tenantId);
    }
}
~~~~

The factory looks for the annotation on the test class. If there is no annotation, the customizer receives `null` and does not alter the context. This approach always creates a customizer with clear semantics; a no-op customizer for tests that do not declare a tenant still has stable equality.

If you want to use meta-annotations, `AnnotatedElementUtils.findMergedAnnotation(...)` supports finding merged annotations across composed annotations. This is useful when a project creates a high-level annotation such as `@NorthTenantTest` meta-annotated with `@TestTenant("north")`.

### Registering the Factory

The Spring TestContext Framework discovers `ContextCustomizerFactory` via `SpringFactoriesLoader`. Register the factory in the file:

    src/test/resources/META-INF/spring.factories

Contents:

~~~~properties
org.springframework.test.context.ContextCustomizerFactory=\
com.example.test.TenantContextCustomizerFactory
~~~~

If the factory belongs to a test support library reused by multiple modules, the metadata file must be packaged inside the artifact consumed by tests on the test classpath. If used only in a single project, placing it in test resources is sufficient.

Spring can discover multiple factories from `spring.factories` files on the classpath. Do not overwrite entries from other libraries when creating a new file; use the build's proper metadata-merging mechanism so all required factories are preserved.

## 5. Using the Property Provided by the Customizer in Beans

Test configuration can read the newly added property. For example, using `Environment` to avoid depending on placeholders inside annotations:

~~~~java
@Configuration
public class TenantTestConfig {

    @Bean
    TenantInfo tenantInfo(Environment environment) {
        return new TenantInfo(
                environment.getRequiredProperty("test.tenant-id")
        );
    }
}

public record TenantInfo(String tenantId) {
}
~~~~

Test class:

~~~~java
@SpringJUnitConfig(TenantTestConfig.class)
@TestTenant("north")
class NorthTenantTest {

    @Autowired
    TenantInfo tenantInfo;

    @Test
    void shouldUseNorthTenant() {
        assertThat(tenantInfo.tenantId()).isEqualTo("north");
    }
}
~~~~

When Spring creates the context for `NorthTenantTest`, the factory reads `"north"`, the customizer adds the property source, then the context refreshes and the `TenantInfo` bean is created with the corresponding value.

Another test class:

~~~~java
@SpringJUnitConfig(TenantTestConfig.class)
@TestTenant("south")
class SouthTenantTest {

    @Autowired
    TenantInfo tenantInfo;

    @Test
    void shouldUseSouthTenant() {
        assertThat(tenantInfo.tenantId()).isEqualTo("south");
    }
}
~~~~

The customizer for `"south"` does not equal the customizer for `"north"`. Therefore, even if other configuration elements are identical, Spring still must use two separate cache entries because the properties and beans are configured differently.

## 6. What Is `MergedContextConfiguration`?

`MergedContextConfiguration` is the object describing the merged configuration for a test class. It holds the metadata needed by Spring to create an `ApplicationContext`.

Elements that commonly affect the configuration include:

- Resource locations or configuration classes.
- `ApplicationContextInitializer` classes.
- Active profiles.
- Property source descriptors and inline properties.
- `ContextCustomizer` instances.
- `ContextLoader`.
- Parent context if a context hierarchy exists.
- Resource base path for web application contexts.

`MergedContextConfiguration` implements `equals()` and `hashCode()`. Spring uses these values when looking up contexts in `ContextCache`.

The `ContextCustomizer` collection is part of the configuration being compared. Therefore, customizer equality is not merely an internal class detail; it directly affects whether Spring reuses an `ApplicationContext`.

The cache key can be described in a simplified way:

~~~~text
Cache key
    =
MergedContextConfiguration
    |
    +--> Classes / locations
    +--> Initializers
    +--> Active profiles
    +--> Property sources
    +--> Context customizers
    +--> Context loader
    +--> Parent context
    +--> Web resource path
~~~~

Two tests with the same cache key can reuse the same `ApplicationContext`. If any part of the configuration differs according to `MergedContextConfiguration` semantics, Spring creates or looks up a different cache entry.

## 7. Why Are `equals()` and `hashCode()` of a Customizer So Important?

`ContextCustomizer` is placed into `MergedContextConfiguration`. When Spring compares two `MergedContextConfiguration` instances, the customizers are also compared. This creates two types of bugs if equality is wrong.

### Bug 1: Failing to Override `equals`/`hashCode`

Suppose each time the factory runs, it creates:

    new TenantContextCustomizer("north")

These two instances have the same `tenantId`, but if `Object.equals()` is used, they are not equal because they are two different objects.

Consequence:

- Test class A creates a context with tenant `north`.
- Test class B with equivalent configuration also creates a new `north` customizer.
- The cache keys contain customizers that differ by identity.
- Spring may create an extra `ApplicationContext` instead of reusing the existing context.

The tests may still pass, but the suite starts up slowly and the cache becomes fragmented.

### Bug 2: `equals`/`hashCode` Ignoring Configuration Data

Suppose the customizer holds `tenantId`, but `equals()` only checks the class:

~~~~java
@Override
public boolean equals(Object other) {
    return other instanceof TenantContextCustomizer;
}

@Override
public int hashCode() {
    return TenantContextCustomizer.class.hashCode();
}
~~~~

Then the `north` and `south` customizers are treated as equal.

Consequence:

- The `north` test creates a context with property `test.tenant-id=north`.
- The `south` test has a cache key treated as equivalent.
- Spring may return the `north` context to the `south` test.
- The `south` test sees beans already created with tenant `north`.

This is a more severe bug than a cache miss because a test may run against the wrong configuration without necessarily failing immediately.

### Design Rule

`equals()` and `hashCode()` must be based on all immutable state that affects the resulting context.

| Customizer State | Should Participate in Equality? | Reason |
| --- | --- | --- |
| Tenant ID placed into `Environment` | Yes | Changes properties and beans in the context. |
| List of applied profiles or feature flags | Yes | Changes context configuration. |
| Registered bean names or bean definitions | Yes | Changes context contents. |
| Value used only for logging, without affecting context | Not necessarily | Does not change context semantics. |
| Timestamp when the customizer was created | No | Makes every instance distinct and breaks caching. |
| Test class used only for logging | Not necessarily | Can fragment the cache if actual configuration is identical. |
| Class/type used to register different beans | Yes | Changes the bean graph in the context. |

A customizer should be an immutable value object. Do not mutate `tenantId`, property maps, or bean lists after creating the customizer, because the hash code could change while the object is part of a cache key.

## 8. Testing Equality Directly

You can write unit tests for the customizer to verify equality semantics:

~~~~java
class TenantContextCustomizerTest {

    @Test
    void customizersForSameTenantAreEqual() {
        var first = new TenantContextCustomizer("north");
        var second = new TenantContextCustomizer("north");

        assertThat(first).isEqualTo(second);
        assertThat(first.hashCode()).isEqualTo(second.hashCode());
    }

    @Test
    void customizersForDifferentTenantsAreNotEqual() {
        var north = new TenantContextCustomizer("north");
        var south = new TenantContextCustomizer("south");

        assertThat(north).isNotEqualTo(south);
    }
}
~~~~

This is a small but valuable unit test because broken equality can cause subtle cache bugs. It does not replace integration tests proving that the context actually receives the right property.

You can also test the factory:

~~~~java
@Test
void factoryCreatesCustomizerFromTestAnnotation() {
    ContextCustomizerFactory factory =
            new TenantContextCustomizerFactory();

    ContextCustomizer first = factory.createContextCustomizer(
            NorthTenantTest.class,
            List.of()
    );

    ContextCustomizer second = factory.createContextCustomizer(
            AnotherNorthTenantTest.class,
            List.of()
    );

    assertThat(first).isEqualTo(second);
}
~~~~

The example assumes both test classes have the same tenant annotation and other metadata does not affect the customizer. The goal is to verify that the factory creates customizers based on configuration values, not on the object identity of the test class.

## 9. Why Should You Not Arbitrarily Include the Test Class in Equality?

Some factories may want to keep `Class<?> testClass` in the customizer to read annotations or log. That does not automatically mean the class must participate in `equals`/`hashCode`.

If two test classes have the same context configuration, Spring can reuse the context between them. If customizer equality includes `testClass`, each test class creates a separate cache key even though the actual context is identical.

For example:

- `NorthTenantTest` and `AnotherNorthTenantTest` both declare `@TestTenant("north")`.
- The factory creates two customizers with the same `tenantId`.
- If equality is based only on `tenantId`, they can share a context.
- If equality also includes `testClass`, the cache splits into two entries.

Only include the test class in equality when the context is genuinely configured differently based on that class. If the class is merely a metadata source while the resulting customization is identical, equality should be based on the configuration outcome.

This principle also applies to annotation instances. Do not use an annotation proxy's identity for equality if the annotation values are what actually determine the configuration.

## 10. `ContextCustomizerFactory` and `@DynamicPropertySource`

`@DynamicPropertySource` is a real-world example of the customizer mechanism in the Spring TestContext Framework. Spring detects methods annotated with `@DynamicPropertySource` and uses a customizer to add dynamic properties into the `Environment` when the context is prepared.

Example:

~~~~java
@Testcontainers
@SpringBootTest
abstract class AbstractDatabaseIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~~

Suppliers can return values known only after a container starts, such as a JDBC URL with a dynamic port. Dynamic properties are added to the `Environment` before beans such as the datasource that need those values are created.

A notable caveat is that the cache key does not always reflect every runtime value a supplier will return. With the `@DynamicPropertySource` customizer, equality is based on the set of discovered dynamic property methods. If the same method is inherited but returns different values depending on the subclass or resource lifecycle, two test classes may be considered to have equivalent customizer configurations even when the dynamic values change.

For example, a superclass has a `@DynamicPropertySource` method using a container that is restarted or changed per subclass. If the cache keeps the old context, the datasource may continue using the old URL.

When dynamic properties vary between subclasses, Spring recommends using `@DirtiesContext` at the appropriate scope so the context is evicted from the cache and recreated. You can also design the configuration so dynamic values remain stable throughout the lifetime of the shared context.

Do not assume that re-evaluating a supplier automatically updates beans already created in the context. `Environment` may return a new value, but singleton beans like `DataSource` initialized earlier may still hold the old configuration.

## 11. Comparing `ContextCustomizer` with Other Configuration Mechanisms

Spring Test offers many extension points. Choose the simplest mechanism that fits the need.

| Mechanism | Use When | Related to Context Cache Key? |
| --- | --- | --- |
| `@TestPropertySource` | A test class needs static properties declared directly. | Property source descriptors are included in `MergedContextConfiguration`. |
| `@DynamicPropertySource` | Properties are only available after a resource starts, such as a container port. | Dynamic property customizer participates in context customizers. |
| `@ContextConfiguration(initializers = ...)` | An `ApplicationContextInitializer` is needed to apply configuration when the context is created. | Initializer classes are part of merged configuration. |
| `@TestConfiguration` / `@Import` | Test beans need to be declared explicitly in configuration. | Configuration classes/imports affect merged configuration. |
| `@MockitoBean` or bean override | A bean in the context needs to be replaced with a mock or test bean. | Bean override context customizer participates in the cache key. |
| `ContextCustomizerFactory` | Test class metadata needs to be read to produce reusable context customizations via an SPI. | `ContextCustomizer` created by the factory is part of the cache key. |

### When to Use `@TestPropertySource`

If every test simply needs a fixed property:

    @TestPropertySource(properties = "feature.search.enabled=false")

this is usually easier to understand than a custom annotation and factory.

### When to Use `@DynamicPropertySource`

If a test needs a port or URL supplied by a container, `@DynamicPropertySource` is a built-in API and usually avoids writing a custom factory.

### When to Use `ApplicationContextInitializer`

If you need to operate on the context via an initializer class declared directly in `@ContextConfiguration`, `ApplicationContextInitializer` may fit. This mechanism is helpful when the configuration is known at the class level and does not require a discovery SPI driven by custom annotations.

### When to Use `ContextCustomizerFactory`

Use a factory when you want to encapsulate configuration conventions across many test classes, for example:

- Test annotations selecting a tenant, region, or feature set.
- Automatically registering beans based on test class metadata.
- Integrating a test support library that must adjust the context before refresh.
- Creating configuration shareable across multiple modules without requiring each test class to declare its own initializer.

Do not create a factory just to replace a simple property already supported by `@TestPropertySource`.

## 12. `ContextCustomizer` and Bean Overrides

Bean replacement mechanisms in Spring Test can also use context customizers to describe bean overrides and contribute to the cache key.

For example, suppose a test needs to replace `PaymentGateway` with a mock. The bean override annotation identifies which bean is replaced and what kind of override is applied. Override information must participate in the merged configuration, because a context with a mock gateway differs from a context with the real implementation.

This shows that the cache key does not only care about properties. Any customization that alters the bean graph or context behavior needs to be represented with proper equality.

If a customizer registers different beans while `equals`/`hashCode` ignores the bean type or qualifier, Spring may reuse a context with the wrong bean override. Conversely, if equality includes information that does not affect the bean graph, the cache can become fragmented.

When integrating bean overrides, mock frameworks, or test support libraries, inspect how the library represents metadata in its customizer and how it defines equality. Do not build a second customizer doing the same job if Spring already provides the appropriate mechanism.

## 13. Factory Discovery and Ordering

`ContextCustomizerFactory` instances are discovered via `SpringFactoriesLoader`. The `META-INF/spring.factories` metadata file can list multiple implementations for the same key:

~~~~properties
org.springframework.test.context.ContextCustomizerFactory=\
com.example.test.TenantContextCustomizerFactory,\
com.example.test.FeatureFlagContextCustomizerFactory
~~~~

Factories should be independent whenever possible. If two factories modify the same property source or register the same bean name, the result may depend on application order.

When order matters, implement `Ordered` or use `@Order` to declare precedence using the mechanism Spring supports for factories. However, a better design is usually to avoid having two customizers contend over the same part of the configuration.

Distinguish factory ordering from `TestExecutionListener` callback ordering. `ContextCustomizerFactory` participates in the context configuration bootstrap phase; `TestExecutionListener` participates in the test method/class execution lifecycle. The two SPIs serve two different phases.

## 14. Impact on Cache Hits, Cache Misses, and Performance

The context cache helps Spring avoid recreating `ApplicationContext` instances with equivalent configurations. Having customizers participate in the cache key can increase or decrease cache hits.

### Cache Hit

Two tests have the same merged configuration and equal customizers. Spring can return the previously created `ApplicationContext`.

Example:
- Both test classes use `TenantTestConfig`.
- Both declare `@TestTenant("north")`.
- `TenantContextCustomizer` equality is based on `tenantId`.
- Other configuration elements are equivalent.

Both tests can share the `north` context.

### Cache Miss

Configurations differ or customizers are not equal. Spring creates a new context.

Example:
- One test uses tenant `north`.
- One test uses tenant `south`.
- Customizer equality is based on `tenantId`.

Spring needs separate contexts because properties and beans are configured differently.

### Unintended Cache Miss

A customizer fails to override `equals`/`hashCode` or includes a timestamp/random value in equality. Every bootstrap produces a different cache key even though context semantics are identical.

Consequences can include:
- Increased suite execution time.
- More `ApplicationContext` instances created.
- More connection pools or resources opened.
- Cache reaching its limit quickly and evicting older contexts.
- Slower tests with no isolation benefit.

### Semantic Cache Collision

A customizer omits a value that actually affects the context. Two different configurations are treated as equal and Spring may reuse an inappropriate context.

This is why equality must be just right: neither omitting state that affects the context nor including irrelevant state.

## 15. Monitoring the Context Cache

The Spring TestContext Framework has logging for the context cache. You can enable `DEBUG` level to view cache statistics and context accesses:

    logging.level.org.springframework.test.context.cache=DEBUG

The logs help identify:
- Cache hits and cache misses.
- Number of contexts currently held.
- Contexts evicted from the cache.
- Suites creating more contexts than expected.

If a test suite shows an unusual increase in context count, check:
- Do test classes have the same configuration while customizer equality differs?
- Is there a timestamp or random value inside a customizer?
- Are annotation attributes normalized consistently?
- Do tests truly need separate contexts?
- Is `@DirtiesContext` being used too broadly?
- Do dynamic properties change while the cache still holds an old context?

Do not try increasing the cache size before understanding why there are so many cache keys. Raising the limit can mask broken customizer equality and consume even more resources.

## 16. `ContextCustomizer` and AOT

Context customization is part of `ApplicationContext` preparation. When a project uses AOT test processing or a native image, the changes required for the context must fit the AOT mechanism supported by the Spring version.

A customizer relying on stable test class metadata, such as annotation values, is usually more predictable than a customizer reading external environment state or generating random data at bootstrap time.

When designing for AOT environments:

- Keep customization based on clear and stable test metadata.
- Do not use the current timestamp or random values as part of context configuration without a corresponding AOT mechanism.
- Ensure factory and customizer classes are on the classpath discoverable by test AOT processing.
- Verify that generated bean definitions or property sources can be processed in the AOT model of the Spring version in use.
- Run tests in the target AOT/native configuration itself rather than assuming success solely from regular JVM tests passing.

AOT does not change the fundamental requirement on customizer equality for the context cache. If a customizer affects context configuration, that state still needs to be represented stably and accurately.

## 17. Common Mistakes

**Failing to override `equals()` and `hashCode()`.**

Each time the factory creates a new customizer, object identity can make cache keys differ. Use value equality based on state that affects the context.

**`equals()` ignoring differing properties or beans.**

Two tests with different tenant/feature configurations may be treated as equal. The context cache may return a context configured for the other test. Include every context-affecting value in equality.

**Putting a timestamp or random ID in a customizer.**

Values changing on every creation cause constant cache misses. Use only stable configuration state meaningful to the context.

**Including the entire test class in equality when contexts are identical.**

The cache splits per class even though the actual configuration is identical. Equality should reflect the customization outcome, not the metadata source if that source does not alter the context.

**Creating property sources after the context has refreshed.**

Beans may have already been initialized with old values. Perform customization before refresh.

**Using `ContextCustomizerFactory` for simple static properties.**

A custom factory adds complexity and introduces another component to the cache key. Prefer `@TestPropertySource` or `@DynamicPropertySource` if they already meet the need.

**Confusing `ContextCustomizerFactory` with `TestExecutionListener`.**

Factories/customizers affect context creation; listeners receive callbacks during the test lifecycle. Use the right SPI for the point where intervention is needed.

**Dynamic properties change while the context is still reused.**

If customizer equality does not reflect new dynamic values, an old context may retain a datasource or bean created with an old URL. Use `@DirtiesContext` when dynamic configuration varies across test classes, or design a stable resource lifecycle.

**Overwriting `spring.factories` metadata from other libraries.**

A new metadata file can drop required factories if packaging does not merge entries. Inspect the final resource on the test runtime classpath.

## 18. Process for Implementing a `ContextCustomizerFactory`

When you need a context customization mechanism reusable across multiple test classes, implement it in this order:

1. Identify the exact part of the `ApplicationContext` that needs to change.
2. Check whether `@TestPropertySource`, `@DynamicPropertySource`, `@TestConfiguration`, or `ApplicationContextInitializer` already meets the need.
3. If an SPI is needed, define a test annotation with runtime retention and immutable attributes.
4. Write the `ContextCustomizerFactory` to read metadata and create the customizer.
5. Write the `ContextCustomizer` to modify `Environment` or register bean definitions before refresh.
6. Implement `equals()` and `hashCode()` over all state affecting the context.
7. Register the factory in `META-INF/spring.factories`.
8. Write unit tests for the factory and customizer equality.
9. Write integration tests verifying the context receives the expected properties/beans.
10. Use two test classes with identical configuration to verify cache reuse.
11. Use two test classes with different configurations to verify contexts are not wrongly shared.
12. Enable cache `DEBUG` logging if diagnosing context creation counts.

A customizer should have a constructor accepting clear state, `final` fields, no external mutable objects retained, and no side effects in `equals`/`hashCode`.

## 19. Pattern for Testing Cache Behavior

You can use two test classes with the same tenant configuration to verify equality and context reuse. Example:

~~~~java
@SpringJUnitConfig(TenantTestConfig.class)
@TestTenant("north")
class FirstNorthTenantTest {
    @Autowired ApplicationContext context;
}

@SpringJUnitConfig(TenantTestConfig.class)
@TestTenant("north")
class SecondNorthTenantTest {
    @Autowired ApplicationContext context;
}
~~~~

If other configuration elements are equivalent, Spring can reuse the context. In a dedicated test checking the cache, you can compare the identity of the injected contexts:

~~~~java
assertThat(firstContext).isSameAs(secondContext);
~~~~

For a different tenant:

~~~~java
@SpringJUnitConfig(TenantTestConfig.class)
@TestTenant("south")
class SouthTenantTest {
    @Autowired ApplicationContext context;
}
~~~~

The `south` context should differ from the `north` context if the tenant property alters the bean graph or context configuration:

~~~~java
assertThat(northContext).isNotSameAs(southContext);
~~~~

These assertions are only appropriate in test infrastructure specifically verifying the context cache. Do not make business tests depend on execution order or share contexts between test classes just to compare identity. When testing the cache, design controlled tests and prevent other tests from dirtying cache state.

## Conclusion

`ContextCustomizerFactory` is the SPI for creating a `ContextCustomizer` based on test class metadata and Spring Test configuration. `ContextCustomizer` modifies `ConfigurableApplicationContext` before refresh. Customizers are placed into `MergedContextConfiguration`, which acts as the context cache key.

Therefore, a customizer's `equals()` and `hashCode()` must reflect every value that changes the `ApplicationContext`. Overly broad equality can cause Spring to reuse the wrong context; identity-based equality or equality containing random state can cause unnecessary cache misses.

Prefer built-in configuration mechanisms when they satisfy the requirement. When a reusable test infrastructure SPI is needed, keep the customizer immutable, register the factory properly, test equality, and verify both cache reuse and cases where separate contexts must be created.
