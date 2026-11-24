# Components That Form the Context Cache Key

The Spring TestContext Framework stores initialized `ApplicationContext` instances in a shared cache within the test process. When another test requests a context with an equivalent configuration, Spring can retrieve the existing context instead of initializing all beans again.

To decide whether two requests can share a context, Spring creates a **cache key** from the merged configuration metadata. Therefore, having two tests run in the same test class or use the same service is not enough to conclude they will share a context. The attributes that make up the context configuration are the deciding factors.

Understanding the cache key helps explain why a small change—such as adding a profile, changing an inline property, adding a mock bean, or changing a resource base path—can cause a cache miss and create a new context.

## 1. How Does the Context Cache Work?

When Spring Test prepares a test with Spring integration, the TestContext Framework reads annotations and metadata on the test class, merges inherited configuration, and creates a context configuration description. That description is used to look up the context in the cache.

```text
Test class A ──┐
               ├── equivalent configuration metadata ──► same cache key
Test class B ──┘                                           │
                                                           ▼
                                               Cached ApplicationContext

Test class C ───── differing metadata ─────────────────► different cache key
                                                           │
                                                           ▼
                                               create new ApplicationContext
```

The cache key is built from the merged configuration object, typically represented by `MergedContextConfiguration`. The fields in this object participate in `equals()` and `hashCode()` comparisons. If keys are equal, Spring can reuse the corresponding context; if they differ, Spring must find or create another entry.

This means the test class name is not itself a component of the key. Two differently named test classes can still share a context if their context metadata is equivalent. Conversely, two tests in the same class can still request different contexts if they use nested configurations or customization mechanisms that produce different metadata.

## 2. Main Fields That Form the Cache Key

In Spring Framework TestContext, the cache key is based on the following configuration components:

| Component | Common configuration source | Why it affects the key |
|---|---|---|
| Resource locations | `@ContextConfiguration(locations = ...)` | Specifies configuration files or resources to load. |
| Configuration classes | `@ContextConfiguration(classes = ...)` | Specifies Java configuration classes or components used to create the context. |
| Context initializer classes | `@ContextConfiguration(initializers = ...)` | Specifies initializers invoked before context refresh. |
| Context customizers | `ContextCustomizerFactory` implementations, e.g., dynamic properties or bean overrides | Carries additional customizations applied during context creation. |
| Context loader | `@ContextConfiguration(loader = ...)` | Specifies the context loading strategy. |
| Parent context | `@ContextHierarchy` | Specifies the parent context in a hierarchical structure. |
| Active profiles | `@ActiveProfiles` | Specifies profiles enabled when creating the context. |
| Property source descriptors | `@TestPropertySource(locations = ...)` | Describes property source files to load. |
| Inline property source values | `@TestPropertySource(properties = ...)` | Adds property values directly in the annotation. |
| Web resource base path | `@WebAppConfiguration` | Specifies the root resource directory of the web application context. |

These are components of the merged metadata; a specific annotation may contribute to one or more fields. Fields not used in the current test type typically hold default or empty values.

### 2.1. Resource Locations

The `locations` attribute of `@ContextConfiguration` specifies configuration resources, such as XML files:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(locations = "classpath:/orders-test-context.xml")
class XmlConfiguredOrderTest {
}
```

If another test uses a different XML file, the locations metadata differs and typically produces a different cache key:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(locations = "classpath:/billing-test-context.xml")
class BillingContextTest {
}
```

A resource location can be a classpath resource or a resource path compatible with the loader in use. Spring compares the merged resource configuration, so changing the referenced file can lead to a different context. Merely editing the contents of the same file while keeping the resource name and other metadata unchanged does not automatically create a new key; if the old context is already cached, the test may continue receiving the previously created context.

### 2.2. Configuration Classes

When using Java configuration, classes specified via the `classes` attribute participate in the key:

```java
@SpringJUnitConfig(classes = {
        OrderServiceTestConfiguration.class,
        RepositoryTestConfiguration.class
})
class OrderServiceContextTest {
}
```

Another test uses only one configuration:

```java
@SpringJUnitConfig(classes = OrderServiceTestConfiguration.class)
class OrderServiceOnlyTest {
}
```

The two configurations above are not equivalent merely because both contain `OrderServiceTestConfiguration`. The first test additionally requires `RepositoryTestConfiguration`, so the object graph may differ. Spring must distinguish configuration class metadata to avoid placing a test into a context missing beans or containing inappropriate beans.

Nested configuration classes, imported configurations, and configurations discovered via component scanning also affect context contents. However, distinguish between classes listed directly in `classes` and classes loaded indirectly: the key contains the input configuration metadata and associated customizers; Spring does not simply use the names of all runtime beans as an independent list for comparison.

### 2.3. Context Initializer Classes

`ApplicationContextInitializer` is called before context refresh. An initializer can add property sources, register bean definitions, or adjust the environment. Because initializers can alter the created context, the list of initializer classes participates in the cache key.

```java
class TestEnvironmentInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        Map<String, Object> values = Map.of("feature.enabled", "true");
        context.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource("testOverrides", values)
        );
    }
}

@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = FeatureConfiguration.class,
        initializers = TestEnvironmentInitializer.class
)
class FeatureContextTest {
}
```

If a test uses a different initializer, or adds an initializer to the list, the initializer metadata changes and the context may not be shared. If an initializer holds dynamic state while the initializer class remains the same, Spring does not automatically infer that every runtime value inside the initializer is a separate key field. When dynamic data changes, consider context lifecycle management mechanisms rather than expecting the cache to automatically detect every change.

### 2.4. Context Customizers

`ContextCustomizer` is one of the most important components for understanding modern testing annotations. Spring Test can discover `ContextCustomizerFactory` implementations and use them to create customizations applied when the context is built. This set of customizers participates in the cache key.

Common cases:

- `@DynamicPropertySource` registers dynamic properties into the test environment.
- Annotations that replace beans with mocks or spies, such as `@MockitoBean` and `@MockitoSpyBean` in Spring Framework versions that support them.
- Test customizations provided by Spring Boot or other test libraries.
- Custom context customizers written by the project and registered via the appropriate factory mechanism.

Example of a test with a mock bean:

```java
@SpringJUnitConfig(classes = OrderServiceTestConfiguration.class)
class OrderServiceWithMockGatewayTest {

    @MockitoBean
    NotificationGateway notificationGateway;

    @Autowired
    OrderService orderService;
}
```

Declaring a bean override can make the context customizer differ from a test without overrides. If tests use different sets of mocks/spies, they can produce different keys and not share a context. Specific APIs and override rules depend on the Spring Framework version; older projects may use mock bean mechanisms provided by Spring Boot Test.

Do not assume every annotation on a test class is directly a key field. Some annotations are translated into context customizers; some annotations only affect test execution after the context has already been created. What determines the key is which metadata is placed into `MergedContextConfiguration`.

### 2.5. Context Loader

The context loader is responsible for creating and loading the `ApplicationContext` from the merged configuration. The default loader is usually sufficient for common Java configuration or XML configuration.

A custom loader can be specified:

```java
@ContextConfiguration(
        classes = OrderTestConfiguration.class,
        loader = CustomOrderContextLoader.class
)
class CustomLoaderTest {
}
```

When loader classes differ, Spring must treat them as different context configurations because the way the context is created may differ. Only use a custom loader when context loading genuinely requires customization; an unnecessary custom loader makes configuration harder to share and maintain.

### 2.6. Parent Context

With `@ContextHierarchy`, an application can have a parent context and a child context. For example, the parent context contains services and repositories, while the child context contains web configuration:

```java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
        @ContextConfiguration(
                name = "root",
                classes = RootTestConfiguration.class
        ),
        @ContextConfiguration(
                name = "web",
                classes = WebTestConfiguration.class
        )
})
class WebLayerContextTest {
}
```

Parent context metadata participates in the child context's key. If the parent context configuration differs, the corresponding child context cannot automatically be considered the same context either. This ensures a web context is not reused with a parent containing different beans or dependencies.

### 2.7. Active Profiles

Profiles determine which beans with `@Profile` conditions are registered. The list of profiles activated via `@ActiveProfiles` participates in the cache key:

```java
@SpringJUnitConfig(classes = PaymentConfiguration.class)
@ActiveProfiles("test")
class TestPaymentContext {
}

@SpringJUnitConfig(classes = PaymentConfiguration.class)
@ActiveProfiles("integration")
class IntegrationPaymentContext {
}
```

Two tests requesting different profiles may have contexts containing different beans and must be distinguished. If tests use the same set of profiles, profile metadata can allow sharing a context, provided other key fields are also equivalent.

If the project has a custom profile resolver, the profile values resolved for the test must also be understood in the context of the merged metadata. Do not assume that shell, IDE, or runtime environment profiles automatically replace `@ActiveProfiles`; Spring Test has its own rules for determining active profiles.

### 2.8. Property Source Descriptors and Inline Properties

`@TestPropertySource` can load properties from files:

```java
@SpringJUnitConfig(classes = FeatureConfiguration.class)
@TestPropertySource(locations = "classpath:/feature-test.properties")
class FeatureFilePropertyTest {
}
```

Or declare them inline:

```java
@SpringJUnitConfig(classes = FeatureConfiguration.class)
@TestPropertySource(properties = {
        "feature.enabled=true",
        "orders.max-items=25"
})
class FeatureInlinePropertyTest {
}
```

Both property source descriptors and inline values participate in the key. Therefore, changing file paths or adding or changing inline properties can produce a different cache key. Two tests using the same Java configuration where one enables `feature.enabled` and the other disables it should not share a context.

Properties supplied by other sources, such as system properties or environment variables, are not necessarily represented identically to `@TestPropertySource`. If a test needs a distinct stable value, declare that source explicitly in the test configuration.

### 2.9. Web Resource Base Path

For web tests using `@WebAppConfiguration`, the resource base path attribute specifies the root resource directory of the web application context:

```java
@WebAppConfiguration("src/test/webapp")
@SpringJUnitConfig(classes = WebMvcTestConfiguration.class)
class WebApplicationContextTest {
}
```

The resource base path participates in the key. Two tests using different web resource directories may receive different contexts, even when the Java configuration classes are identical.

If no path is specified, Spring uses the default value of `@WebAppConfiguration`. When a test does not use a web application context, the resource base path component typically has no effect on the key.

## 3. Which Changes Produce a Cache Hit or Cache Miss?

A practical way to understand the key is to compare two tests and determine whether their metadata differs.

| Change | Typical impact |
|---|---|
| Only renaming the test class, keeping all context configuration identical | Can share the context. |
| Using the same configuration classes and same profiles | Can hit the cache if other fields are equivalent. |
| Adding or removing a class in `classes` | Different cache key. |
| Changing resource locations | Different cache key. |
| Adding an initializer class | Different cache key. |
| Changing active profiles | Different cache key. |
| Changing inline properties or property source files | Different cache key. |
| Changing the context loader | Different cache key. |
| Changing the parent context in a hierarchy | Child context cache key differs. |
| Changing the web resource base path | Different cache key. |
| Adding or changing bean overrides/context customizers | Can produce a different cache key. |
| Only changing assertions or local data of a test method | Typically does not change the cache key. |

Example of two tests that can share a context:

```java
@SpringJUnitConfig(classes = SharedTestConfiguration.class)
class CustomerServiceTest {
    @Autowired
    CustomerService customerService;
}

@SpringJUnitConfig(classes = SharedTestConfiguration.class)
class CustomerRepositoryIntegrationTest {
    @Autowired
    CustomerRepository customerRepository;
}
```

If both tests have the same context metadata and no differing customizers, Spring can reuse one context. Different test classes do not inherently require creating a new context.

Conversely, a small difference in properties is enough to split the cache:

```java
@SpringJUnitConfig(classes = SharedTestConfiguration.class)
@TestPropertySource(properties = "feature.mode=compact")
class CompactModeTest {
}

@SpringJUnitConfig(classes = SharedTestConfiguration.class)
@TestPropertySource(properties = "feature.mode=full")
class FullModeTest {
}
```

Both tests share the same configuration class but require different environments. They need separate contexts so beans are created with the appropriate properties.

## 4. @DynamicPropertySource and Dynamic Values

`@DynamicPropertySource` allows registering properties whose values are provided by a static method, often used when a test starts an external resource such as a database container or message broker container:

```java
abstract class BaseDatabaseIntegrationTest {

    static PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16");

    static {
        database.start();
    }

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
    }
}
```

`@DynamicPropertySource` methods are reflected through a context customizer in the cache key. However, note that the key does not always reflect every runtime return value of the suppliers. Two subclasses may inherit the same dynamic property method while the suppliers read from different resources.

For example, if the same method is inherited while an external resource changes between subclasses, Spring may treat the customizer metadata as equivalent and reuse the old context. When dynamic properties genuinely change between subclasses, Spring documentation recommends using `@DirtiesContext` on the parent class or adjusting test organization so the context is recreated at the right time.

Key takeaway: the dynamic property method declaration is part of the metadata; changing the value returned by a supplier does not guarantee the cache key will automatically change.

## 5. Bean Overrides and Mocks Affect the Cache Key

In a test context, mock/spy bean annotations can alter the bean definitions placed into the context. Therefore, they are typically handled via context customizers and affect the cache key.

Example with the newer Spring Framework API:

```java
@SpringJUnitConfig(classes = OrderServiceTestConfiguration.class)
class OrderServiceWithMockRepositoryTest {

    @MockitoBean
    OrderRepository orderRepository;
}
```

Another test may replace a different bean:

```java
@SpringJUnitConfig(classes = OrderServiceTestConfiguration.class)
class OrderServiceWithMockGatewayTest {

    @MockitoBean
    NotificationGateway notificationGateway;
}
```

The two tests can have different context customizers because the sets of overridden beans are not the same. As the number of mock/spy combinations grows, the number of cache keys can also grow and lower the cache hit rate.

To avoid unnecessary cache fragmentation:

- Share a single test configuration when tests genuinely need the same object graph.
- Avoid declaring different mock beans in each class if you can test with manual mocks outside the context.
- Only replace beans in the context when the test needs to verify integration between a Spring bean and the replaced collaborator.
- Group tests with the same set of overrides under the same configuration when that organization remains clear.

Annotation names and bean override capabilities vary by version. In older Spring Boot projects, you may encounter `@MockBean`; in newer Spring Framework versions, prefer Spring Test APIs such as `@MockitoBean` and `@MockitoSpyBean` when supported by the version.

## 6. Configuration Inheritance and Its Impact on the Cache Key

The TestContext Framework merges configuration from superclasses and subclasses according to Spring Test annotation inheritance rules. Therefore, when comparing cache keys, look at the merged configuration rather than only annotations declared directly on the test class.

```java
@SpringJUnitConfig(classes = SharedServiceTestConfiguration.class)
abstract class BaseServiceTest {
}

class CreateOrderTest extends BaseServiceTest {
}

class CancelOrderTest extends BaseServiceTest {
}
```

Two subclasses that do not add other configurations can share metadata inherited from the superclass. If one subclass adds a configuration class, profile, property source, or customizer, the key can differ.

Inheritance attributes such as `inheritLocations` and `inheritInitializers` control whether configuration from the superclass is merged into the subclass. When inheritance rules change, the final metadata changes and may produce a new key.

For nested test classes, Spring also has `@NestedTestConfiguration` rules to decide whether test context annotations are inherited. If a nested test needs a different context, declare it explicitly instead of assuming every nested class has its own key or shares a key.

## 7. Context Hierarchy and the Cache

For layered web applications, you can create a root context and a child web context. The child context references the parent in its metadata. This has two consequences:

1. If the root context is equivalent, tests can reuse the parent context portion.
2. If the parent context differs, the child context's key also differs because the parent is part of the configuration.

Example:

```java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
        @ContextConfiguration(
                name = "root",
                classes = RootConfiguration.class
        ),
        @ContextConfiguration(
                name = "dispatcher",
                classes = DispatcherConfiguration.class
        )
})
class DispatcherContextTest {
}
```

When using a hierarchy, `@DirtiesContext` can be applied to a specific hierarchy level via the `hierarchyMode` attribute. If a parent context is marked dirty, child contexts depending on it may also need to be evicted from the cache. Choose the mode matching the scope of change so you do not evict more contexts than necessary.

## 8. Is @DirtiesContext a Component of the Cache Key?

`@DirtiesContext` is often mistaken for a key configuration field. The primary role of this annotation is to instruct Spring to evict the used context from the cache at a specified point, such as after a method or after a class.

```java
@SpringJUnitConfig(classes = MutableStateConfiguration.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MutatesSharedContextTest {
}
```

When a context is marked dirty, Spring closes and evicts the corresponding entry according to the selected hierarchy rules. A subsequent test with the same cache key may still have to create a new context because the old entry was evicted.

Therefore:

- The cache key answers the question: “What kind of context configuration is the test requesting?”
- `@DirtiesContext` answers the question: “Is the used context still allowed to be reused?”

If you only need to delete data in a repository or reset a stateful bean, use an appropriate data cleanup mechanism. Do not use `@DirtiesContext` to handle every minor state change because recreating a context can take significant time.

## 9. Cache Size, LRU, and Context Lifecycle

The context cache has a default size limit. In the Spring TestContext Framework, the default limit is typically 32 contexts. When the cache is full, Spring uses a least-recently-used (LRU) policy: the least recently used entry may be evicted to make room for a new context.

The limit can be adjusted with a property:

```text
spring.test.context.cache.maxSize=64
```

The property can be supplied via a system property or a Spring property configuration mechanism appropriate to how tests are run. Increasing the cache size can reduce context recreation when a suite has many different configurations, but it also increases the amount of memory the retained contexts can use.

When a context is evicted due to LRU or `@DirtiesContext`, Spring closes the context to release resources. Beans with destruction callbacks, connection pools, or managed resources may be closed according to the context lifecycle.

The cache is a static cache within the test process. Therefore:

- Tests running in the same JVM can share contexts.
- Separate JVM forks have separate caches and do not share initialized contexts.
- Running individual tests in an IDE may not show the same level of cache hits as running the entire suite in one process.
- Test execution order can affect whether an entry undergoes LRU eviction, even though it does not change the cache key.

## 10. Observing Cache Hits and Cache Misses

When you need to understand why tests initialize contexts repeatedly, enable DEBUG logging for the cache:

```text
logging.level.org.springframework.test.context.cache=DEBUG
```

Or configure the corresponding logger in the logging system in use. Spring Test can log cache hit counts, cache miss counts, cache size, and related statistics. This information helps distinguish:

- A new key appearing for the first time and needing context creation.
- A key that already has an entry and is reused.
- An old entry that was removed or evicted so the context had to be recreated.

When reading logs, cross-reference the test class with the merged configuration metadata: classes, locations, profiles, properties, initializers, customizers, loader, parent, and resource base path. Do not draw conclusions based solely on the test class name.

## 11. Organizing Tests to Leverage the Context Cache

For the cache to be effective, tests with the same needs must actually use the same metadata:

1. Create shared Java configuration classes for groups of tests that share the same object graph.
2. Set active profiles consistently across groups of tests that need to share a context.
3. Use the same property sources and the same inline values if tests need the same environment.
4. Avoid creating unnecessary variations of bean overrides.
5. Reuse initializers and context customizers when configuration goals are the same.
6. Use the same resource base path for tests sharing the same web application context.
7. Only use `@DirtiesContext` when the context genuinely cannot be reused.

Do not force tests to share a context if they need different environments. For example, tests for the `test` profile and the `integration` profile may need different beans; separating contexts is the right behavior. The goal is to avoid accidental differences, not to maximize cache hits at all costs.

## 12. Common Causes of Differing Cache Keys

### Adding Per-Test-Class Properties

Two classes with the same `classes` but declaring different `@TestPropertySource` values will produce different property metadata. If a test does not need a separate environment, consolidate common properties into a shared configuration.

### Inconsistent Active Profiles

One test using `test` and another using `local` can produce different bean graphs. Declare profiles intentionally and consistently within test groups.

### Different Mock Bean Declarations

Context customizers used to override beans can differ when tests declare different mocks/spies. If you do not need to replace a bean in the context, mocking collaborators manually in unit tests avoids creating a new context just for a mock.

### Each Test Using Its Own Configuration Class Despite Identical Content

Two configuration classes with different names and class identities are still two different class metadata entries. If the actual configuration content is identical, consider reusing the same configuration class instead of copying it into multiple classes.

### Dynamic Properties Change Without the Cache Key Reflecting the Value

If a dynamic property supplier changes its result while the customizer remains equivalent, the old context may be reused. Design resource and context lifecycles explicitly, using `@DirtiesContext` when appropriate.

### Inconsistent Context Hierarchy

Tests with the same web configuration but different parents cannot share the child context. Reuse the root configuration when tests genuinely share the underlying layer.

### Different Resource Base Paths

Two web tests using different resource directories may require separate contexts. Standardize the base path if the tests need the same set of resources.

## 13. How to Analyze a Cache Miss Case

Suppose two tests both use `OrderTestConfiguration`, yet logs show Spring creating the context twice. You can analyze sequentially:

| Step | Question to answer |
|---|---|
| 1 | Do both tests have the same list of `classes` and `locations`? |
| 2 | Are the `ApplicationContextInitializer` classes identical? |
| 3 | Are there any differing `@DynamicPropertySource` or context customizers? |
| 4 | Are the sets of `@MockitoBean`, `@MockitoSpyBean`, or bean overrides identical? |
| 5 | Are the active profiles identical? |
| 6 | Does `@TestPropertySource` have the same files and inline properties? |
| 7 | Are the context loader and parent context equivalent? |
| 8 | If it is a web context, is the resource base path identical? |
| 9 | Was the old context evicted from the cache by `@DirtiesContext` or LRU eviction? |
| 10 | Are both tests running in the same JVM or in different forks/processes? |

Cross-referencing metadata step by step helps pinpoint the specific cause instead of blindly increasing cache size or removing annotations by trial and error.

## 14. Summary of Key Components

The Spring TestContext cache key reflects the configuration used to create the `ApplicationContext`: resource locations, configuration classes, initializer classes, context customizers, context loader, parent context, active profiles, property source descriptors, inline properties, and web resource base path.

Differences in these fields can produce a different cache key and cause Spring to create a separate context. Conversely, two differently named test classes can still share a context when the merged metadata is equivalent and the entry remains in the cache.

When optimizing test execution time, observe cache hits/misses, standardize shared configuration, and only create separate contexts when tests genuinely need a different environment. That approach preserves proper test isolation while taking full advantage of the Spring TestContext Framework's context reuse mechanism.
