# Inheriting Configuration from a Superclass

In a Spring project, many integration tests require the same group of foundational beans: a datasource, repositories, shared services, transaction configuration, or infrastructure components for testing. If every test class redeclares the entire configuration, test code becomes repetitive and hard to keep consistent.

The Spring TestContext Framework allows placing shared configuration on a parent test class and having subclasses inherit it. When a subclass declares additional configuration, the framework can merge metadata from classes across the inheritance hierarchy. As a result, each subclass only needs to describe the configuration specific to the scenario it tests.

This mechanism follows explicit rules: configuration can be inherited and augmented, or intentionally replaced using the corresponding `inherit...` attributes. Understanding how merging works helps avoid missing beans, unintentionally retaining unwanted profiles, or creating multiple distinct ApplicationContexts.

## Why Place Shared Configuration on a Parent Class?

Suppose multiple persistence-layer tests all require:

- A datasource dedicated to testing.
- Transaction manager configuration.
- Foundational repository and service beans.
- A shared profile such as `integration`.
- Shared properties for the database or mock services.

You can create an abstract parent test class holding the baseline configuration:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = PersistenceTestConfig.class)
@ActiveProfiles("integration")
abstract class AbstractPersistenceTest {
}
~~~

Concrete tests extend the parent class:

~~~java
class CustomerRepositoryTest extends AbstractPersistenceTest {

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void findsCustomerByEmail() {
        // Test the repository.
    }
}
~~~

The child test class receives the Spring configuration from the parent class. If multiple test classes inherit an equivalent merged configuration, the TestContext Framework can reuse the ApplicationContext through the context cache.

The parent class is typically declared `abstract` to indicate it serves as a shared foundation rather than a standalone test suite. It can contain shared fixtures or helper methods, while keeping responsibilities at the foundational level. Each subclass still needs to describe the specific behavior it verifies.

## How Spring Test Merges Configuration Across the Inheritance Hierarchy

When a subclass declares `@ContextConfiguration`, the Spring TestContext Framework inspects the configuration of that class along with relevant superclasses. Inheritance attributes determine which metadata is retained and which is replaced.

~~~mermaid
flowchart TD
    A["AbstractPersistenceTest"] --> B["Base configuration: PersistenceTestConfig"]
    A --> C["Base profile: integration"]
    D["CustomerRepositoryTest"] --> E["Specific configuration: CustomerTestConfig"]
    D --> F["Specific profile: customer"]
    B --> G["Merged configuration"]
    E --> G
    C --> H["Merged profile list"]
    F --> H
    G --> I["ApplicationContext for test"]
    H --> I
~~~

With default inheritance, parent configuration is included first, and configuration declared on the subclass is appended. Distinguish adding configuration from creating parent/child contexts: standard `@ContextConfiguration` inheritance produces a single merged configuration for the test's context; it does not automatically create two ApplicationContexts in a parent-child relationship.

Common metadata groups have their own inheritance rules:

| Annotation / Attribute | Default | How a Subclass Adjusts It |
|---|---|---|
| `@ContextConfiguration` – locations/classes | Inherits parent configuration | `inheritLocations = false` to replace inherited configuration |
| `@ContextConfiguration` – initializers | Inherits initializers | `inheritInitializers = false` to ignore initializers from the parent class |
| `@ActiveProfiles` | Merges parent and child profiles | `inheritProfiles = false` to use only the subclass's profiles |
| `@TestPropertySource` – locations | Inherits resource locations | `inheritLocations = false` to omit locations from the parent class |
| `@TestPropertySource` – properties | Inherits inline properties | `inheritProperties = false` to omit inline properties from the parent class |

Not all test annotations share the same inheritance attributes. Check the contract of each specific annotation rather than assuming all metadata on a superclass is appended or replaced by a single uniform rule.

## Inheriting @ContextConfiguration locations and classes

`@ContextConfiguration` allows declaring resource locations, annotated classes, or both depending on how it is configured. The `inheritLocations` attribute defaults to `true`. When a subclass declares its own configuration, Spring merges the parent configuration with the subclass configuration.

### Augmenting Parent Configuration in a Subclass

For example, the parent class supplies foundational beans, while the subclass adds Customer-specific configuration:

~~~java
@Configuration
class SharedTestConfig {

    @Bean
    Clock testClock() {
        return Clock.systemUTC();
    }
}

@Configuration
class CustomerTestConfig {

    @Bean
    CustomerPolicy customerPolicy() {
        return new CustomerPolicy();
    }
}

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = SharedTestConfig.class)
abstract class AbstractServiceTest {
}

@ContextConfiguration(classes = CustomerTestConfig.class)
class CustomerServiceTest extends AbstractServiceTest {

    @Autowired
    Clock testClock;

    @Autowired
    CustomerPolicy customerPolicy;
}
~~~

With the default `inheritLocations = true`, annotated classes from both the parent and subclass are merged to build the context. The test can receive both the foundational `testClock` bean and the dedicated `customerPolicy` bean.

Similarly, if the parent class declares an XML resource location and the subclass declares an additional location, the framework can merge the locations list according to inheritance rules. The selected loader processes the merged configuration sources.

### Replacing Inherited Configuration

Sometimes a child test class needs a completely different context. For instance, the parent class uses a real database configuration for integration tests, while the subclass needs a minimal context containing only fake configuration. In that case, you can set `inheritLocations = false`:

~~~java
@Configuration
class FastTestConfig {

    @Bean
    CustomerRepository customerRepository() {
        return new InMemoryCustomerRepository();
    }
}

@ContextConfiguration(
    classes = FastTestConfig.class,
    inheritLocations = false
)
class CustomerFastTest extends AbstractServiceTest {
    // Use only FastTestConfig as the context configuration.
}
~~~

Although this attribute is named `inheritLocations`, in the modern configuration model it governs inheritance of both resource locations and annotated classes for `@ContextConfiguration`. When set to `false`, configurations declared on superclasses are excluded from the inherited list for the subclass.

Use replacement when the subclass genuinely needs an independent configuration set. If you only need to add a bean, add a configuration class or use `@Import` instead of discarding the entire baseline configuration.

## Inheriting ContextInitializers

`@ContextConfiguration` also supports `initializers` to declare `ApplicationContextInitializer` instances. Initializers run during context preparation, before the context is refreshed, and can adjust the environment or register needed configuration.

Example:

~~~java
class SharedContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.getEnvironment()
            .getPropertySources()
            .addFirst(new MapPropertySource(
                "shared-test",
                Map.of("feature.audit.enabled", "false")
            ));
    }
}

class CustomerContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.getEnvironment()
            .getPropertySources()
            .addFirst(new MapPropertySource(
                "customer-test",
                Map.of("customer.region", "test-region")
            ));
    }
}

@ExtendWith(SpringExtension.class)
@ContextConfiguration(
    classes = SharedTestConfig.class,
    initializers = SharedContextInitializer.class
)
abstract class AbstractInitializedTest {
}

@ContextConfiguration(
    classes = CustomerTestConfig.class,
    initializers = CustomerContextInitializer.class
)
class CustomerInitializedTest extends AbstractInitializedTest {
}
~~~

By default `inheritInitializers = true`, so initializers from the parent class are inherited alongside the subclass's initializers. Spring invokes initializers in the order merged by the framework; parent initializers are applied before subclass initializers. If you need to replace the initializer list, set `inheritInitializers = false` on the subclass.

Initializers can modify property sources or customize the context, so execution order matters. Avoid having two initializers overwrite the same property without clear intent. Whenever possible, use `@TestPropertySource` or `@DynamicPropertySource` for regular property configuration so intent stays easier to read.

## Inheriting Profiles with @ActiveProfiles

`@ActiveProfiles` activates one or more profiles when creating an ApplicationContext. The `inheritProfiles` attribute defaults to `true`, meaning profiles of the parent class and subclass are merged.

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = SharedTestConfig.class)
@ActiveProfiles("integration")
abstract class AbstractIntegrationTest {
}

@ContextConfiguration(classes = CustomerTestConfig.class)
@ActiveProfiles("customer")
class CustomerIntegrationTest extends AbstractIntegrationTest {
}
~~~

The child test runs with both the `integration` and `customer` profiles. This is useful when the parent profile enables shared integration environment settings while the child profile enables settings specific to one feature area.

If a subclass needs completely separate profiles, you can set `inheritProfiles = false`:

~~~java
@ActiveProfiles(
    profiles = "isolated",
    inheritProfiles = false
)
class IsolatedCustomerTest extends AbstractIntegrationTest {
}
~~~

In that case, the parent class's `integration` profile is not inherited into the child test. Be careful because the omitted profile may provide beans or properties that the child configuration still requires. Profiles are part of the context configuration and affect both bean selection and the context cache.

## Inheriting Property Sources with @TestPropertySource

`@TestPropertySource` has two groups of information: resource locations pointing to property files and inline properties declared directly. These two groups have separate inheritance attributes:

- `inheritLocations` defaults to `true`.
- `inheritProperties` defaults to `true`.

Example of a parent class declaring shared properties:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = SharedTestConfig.class)
@TestPropertySource(properties = {
    "service.retry.max=3",
    "service.region=global-test"
})
abstract class AbstractPropertyTest {
}
~~~

A subclass adds its own properties:

~~~java
@TestPropertySource(properties = {
    "service.region=customer-test",
    "customer.feature.enabled=true"
})
class CustomerPropertyTest extends AbstractPropertyTest {
}
~~~

With default inheritance, inline properties from the parent class are combined with properties from the subclass. If the same key appears multiple times, pay attention to property source precedence: declarations on the subclass take higher precedence than declarations inherited from the parent class, and inline properties take higher precedence than resource property locations. Therefore, `service.region` resolves to `customer-test` in the example.

If you only want to discard the parent class's inline properties while keeping resource locations, use:

~~~java
@TestPropertySource(
    properties = "customer.feature.enabled=true",
    inheritProperties = false
)
class CustomerWithoutBaseInlinePropertiesTest extends AbstractPropertyTest {
}
~~~

If you only want to replace resource locations, set `inheritLocations = false`. The two attributes control independently, so you do not have to discard both groups when you only want to replace one.

`@DynamicPropertySource` is another mechanism for registering dynamic properties, commonly used with Testcontainers when ports or endpoints are only known at runtime. When inheriting test classes, static methods are discovered by the framework according to its rules; keep the property registration method in the parent class if all subclasses share the resource, and avoid declaring multiple methods overwriting the same key unintentionally.

## Combining Multiple Annotations Across an Inheritance Hierarchy

A parent test class can centralize baseline configuration while subclasses add each metadata group. Example:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
    classes = SharedTestConfig.class,
    initializers = SharedContextInitializer.class
)
@ActiveProfiles("integration")
@TestPropertySource(properties = {
    "feature.audit.enabled=false",
    "service.retry.max=2"
})
abstract class AbstractIntegrationTest {
}

@ContextConfiguration(
    classes = BillingTestConfig.class,
    initializers = BillingContextInitializer.class
)
@ActiveProfiles("billing")
@TestPropertySource(properties = {
    "billing.currency=VND",
    "service.retry.max=4"
})
class BillingIntegrationTest extends AbstractIntegrationTest {

    @Autowired
    BillingService billingService;
}
~~~

The configuration of the Billing test is formed from metadata on both classes:

- Annotated classes: shared configuration and Billing configuration.
- Initializers: shared initializer and Billing initializer.
- Profiles: `integration` and `billing`.
- Inline properties: shared properties and Billing properties; the `service.retry.max` value on the subclass overrides the inherited value.
- JUnit extension: `SpringExtension` is declared on the parent class and applied to the subclass according to JUnit's extension discovery mechanism.

If a subclass wants to exclude part of the metadata, choose the exact corresponding inheritance attribute. For instance, setting only `inheritProfiles = false` does not remove configuration classes; setting only `inheritLocations = false` does not automatically remove profiles or property sources.

## Configuration Inheritance vs. Context Hierarchy

This is an easy point to confuse. Standard `@ContextConfiguration` inheritance merges the configuration lists of the parent and child classes to load a single ApplicationContext for the test. It does not automatically create a parent context and a child context.

If the application genuinely needs multiple ApplicationContexts with a parent-child relationship, use `@ContextHierarchy`:

~~~java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextHierarchy({
    @ContextConfiguration(classes = RootTestConfig.class),
    @ContextConfiguration(classes = WebTestConfig.class)
})
class WebApplicationIntegrationTest {
    // RootTestConfig creates the parent context.
    // WebTestConfig creates the child web context.
}
~~~

In this case, each configuration level in the hierarchy corresponds to a separate context. The TestContext Framework manages context creation order and the parent-child relationship. You can combine a hierarchy with test class inheritance, but you must understand both mechanisms at play: one merges metadata across the class hierarchy, while the other describes multiple layered contexts.

Do not use `@ContextHierarchy` merely to separate shared configuration from test-specific configuration. If all beans belong in the same ApplicationContext, regular configuration inheritance is simpler.

## Inheriting Configuration in Nested Test Classes

The TestContext Framework also has the concept of configuration for nested test classes, i.e., a test class nested inside another class. This is an enclosing relationship, not a superclass relationship.

`@NestedTestConfiguration` determines whether a nested test class inherits configuration from its enclosing class. The default mode is `INHERIT`; you can set `OVERRIDE` so the nested class does not inherit configuration from the enclosing class under this mechanism.

~~~java
@SpringJUnitConfig(SharedTestConfig.class)
class CustomerTests {

    @Nested
    class ActiveCustomerTests {
        // Inherits TestContext configuration from enclosing class by default.
    }
}
~~~

Do not confuse `@NestedTestConfiguration` with `inheritLocations` on `@ContextConfiguration`. One controls whether a nested test class receives metadata from its enclosing class; the other controls whether a subclass inherits locations/classes along the superclass hierarchy.

## Impact on the ApplicationContext Cache

Spring Test uses a cache to reuse ApplicationContexts when tests have equivalent merged configurations. Inherited configuration directly affects the final configuration and therefore affects the cache key.

If two test classes extend the same parent class without adding differing configurations, they can share a context. If a subclass adds its own profiles, properties, initializers, or annotated classes, the merged configuration may differ and the framework creates another cache entry.

Some consequences:

- Stable shared configuration increases context reuse.
- Every unnecessary profile/property variation can create an extra context.
- Using `@DirtiesContext` causes the context to be evicted from the cache for the specified scope.
- Singleton beans in the context are reused; tests must not allow mutable state to leak between tests.

Configuration inheritance does not mean all child tests always share one ApplicationContext. The context depends on the merged configuration, loader, customizers, and other elements of the cache key.

## Organizing Maintainable Parent Test Classes

A good parent test class should hold configuration truly shared across subclasses:

- Test datasource or infrastructure service configurations.
- Shared profiles for the test group.
- Stable default properties.
- Helper methods that do not retain mutable state between tests.
- Fixture factories that create fresh data per test.

Avoid putting every configuration of the entire project into one giant superclass. When a subclass needs only a small slice yet inherits excessive beans, profiles, and properties, the test structure becomes hard to understand. You can split multiple base classes by capability, such as `AbstractRepositoryTest`, `AbstractWebIntegrationTest`, or `AbstractMessagingTest`, and choose the right base class for each test.

Do not use a superclass to pass data created by a parent test method to a child test method. A parent test class is for sharing configuration and utilities; test data should be prepared independently per test method to avoid order dependencies.

## When Should You Replace the Parent Class's Configuration?

| Subclass Need | Appropriate Attribute | Result |
|---|---|---|
| Add annotated classes or XML locations | Keep `inheritLocations = true` | Merges parent and child configuration |
| Use only its own context configuration | `inheritLocations = false` | Does not inherit locations/classes from parent |
| Add specialized initializers | Keep `inheritInitializers = true` | Inherits and appends initializers |
| Use only its own initializers | `inheritInitializers = false` | Discards inherited initializers |
| Add profiles for a child scenario | Keep `inheritProfiles = true` | Merges parent and child profiles |
| Use a completely separate profile | `inheritProfiles = false` | Uses only profiles declared on the subclass |
| Add properties for the child test | Keep both inheritance attributes of `@TestPropertySource` | Inherits resources and inline properties |
| Replace only inline properties | `inheritProperties = false` | Ignores inline properties from parent |
| Replace only property files | `inheritLocations = false` | Ignores resource locations from parent |

Place the inheritance attribute on the exact matching annotation on the subclass. There is no single global flag to turn off inheritance across all Spring Test configuration annotations.

## Common Misconceptions

**Assuming a subclass always replaces the entire parent configuration.** By default, `@ContextConfiguration` inherits and merges locations/classes. To replace, you must set `inheritLocations = false`.

**Assuming disabling inheritLocations removes all parent configuration.** Profiles, initializers, and property sources have their own inheritance flags. You must adjust the exact annotation containing the metadata you want to replace.

**Assuming configuration inheritance creates a parent/child context.** Standard inheritance produces a single merged configuration. For multiple contexts in a parent-child relationship, use `@ContextHierarchy`.

**Assuming subclass profiles always override parent profiles.** By default they are merged. If you want isolated profiles, use `inheritProfiles = false`.

**Assuming all child tests share a single ApplicationContext.** Context caching depends on the merged configuration. Different profiles, properties, or configuration classes can produce different contexts.

**Putting too much mutable state in the superclass.** Tests can inadvertently depend on data or state modified by another test. Keep the superclass focused on baseline configuration and create dedicated fixtures for each test.

**Using context hierarchies instead of configuration inheritance.** The two mechanisms solve different problems. Only create multiple contexts when the application architecture genuinely needs parent-child contexts.

## How to Inspect the Effective Configuration

When a subclass is missing a bean or using the wrong property, trace each class up the hierarchy:

1. Read `@ContextConfiguration` on the nearest superclass and higher superclasses.
2. Read the annotation on the subclass and check `inheritLocations` and `inheritInitializers`.
3. Aggregate active profiles, checking `inheritProfiles`.
4. Check resource locations and inline properties, along with both inheritance flags of `@TestPropertySource`.
5. Check initializers and their application order.
6. Check whether the test uses `@ContextHierarchy`, `@NestedTestConfiguration`, or a custom bootstrapper.
7. Check the context cache to see whether the final configuration is reused or creates a new context.

You can enable appropriate logging for Spring TestContext to observe configuration discovery, context creation, and caching. When you need to check an effective property, you can inject `Environment` into the test and read the specific key:

~~~java
@Autowired
Environment environment;

@Test
void usesCustomerSpecificRegion() {
    assertThat(environment.getProperty("service.region"))
        .isEqualTo("customer-test");
}
~~~

Inspecting the effective configuration helps distinguish annotation-merging mistakes from property source precedence differences. When a bean is missing, check the merged configuration classes and component scans; do not rush to add a duplicate bean in the subclass before understanding why the parent configuration was not loaded.

## Principles to Remember

Place stable baseline configuration on a parent test class and let subclasses add specific configuration by default. Use `inheritLocations` on `@ContextConfiguration` and `@TestPropertySource`, `inheritInitializers`, `inheritProfiles`, and `inheritProperties` in the right places when you need to replace individual metadata groups. Standard configuration inheritance creates a single ApplicationContext from the merged configuration; `@ContextHierarchy` describes multiple contexts with a parent-child relationship.

When organizing tests this way, shared configuration is declared once, subclasses express their specific needs clearly, and the TestContext Framework can reuse contexts when configurations are equivalent.
