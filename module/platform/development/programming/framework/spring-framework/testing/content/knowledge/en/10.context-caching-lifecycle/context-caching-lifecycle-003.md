# Properties, Profiles, Bean Overrides, and Cache Fragmentation

The Spring TestContext Framework caches initialized ApplicationContext instances so that multiple tests with the same configuration can reuse a context. This mechanism reduces suite execution time, especially when a context must initialize many beans, connect to a database, or spin up test infrastructure.

The cache only reuses a context when the merged configurations of the tests are equivalent. Test properties, active profiles, and bean override declarations can all make configurations differ. If each test class creates its own configuration variant, the suite may initialize many nearly identical contexts. That phenomenon is commonly called **cache fragmentation**.

Understanding the components that contribute to the cache key helps you organize tests so that contexts are reused when configurations are genuinely the same, while keeping test environments separate when the risks being verified differ.

## 1. How Does the Spring TestContext Cache Work?

When a test needs a Spring ApplicationContext, the TestContext Framework creates or finds a context based on the test's merged configuration. This configuration is represented by MergedContextConfiguration.

Overview flow:

~~~text
Test class A                 Test class B
     |                            |
     v                            v
MergedContextConfiguration   MergedContextConfiguration
     |                            |
     +-------------+--------------+
                   |
                   v
              Cache lookup
                   |
          +--------+--------+
          |                 |
       Cache hit         Cache miss
          |                 |
          v                 v
    Reuse context       Create context
          |                 |
          +--------+--------+
                   |
                   v
              Run test
~~~

Two test classes can share an ApplicationContext even if their class names and test methods differ, as long as their merged configurations produce the same cache key.

Conversely, two classes testing the same controller but declaring different profiles, properties, or bean overrides may require two separate contexts. This is necessary if they represent two different application configurations.

### What Does the Cache Store?

The cache stores initialized ApplicationContext instances along with the configuration metadata used to look up that context. The cache does not store assertion results, per-method test data, or stubbing state as part of the context configuration.

For example:

- Two test classes using the same MVC configuration, same profiles, same properties, and same bean overrides can share a context.
- Two test classes differing only in name but having equivalent configuration can still share a context.
- Two test classes using different test and integration profiles usually have different cache keys.
- A test class declaring an additional mock bean or replacing a different implementation can produce a separate cache key.

The key takeaway is that **the test class name is not the sole factor determining a cache hit**. Spring compares the merged configuration.

## 2. Components That Form the Cache Key

The Spring TestContext Framework builds the cache key from parts of MergedContextConfiguration. The main attributes include:

| Component | Meaning | Example |
|---|---|---|
| locations | XML paths or context configuration resources | classpath:/test-context.xml |
| classes | Configuration classes or components to load | TestConfig.class |
| contextInitializerClasses | Registered initializers | DatabaseInitializer.class |
| contextCustomizers | Context customizations discovered via annotations or factories | @DynamicPropertySource, bean overrides |
| contextLoader | ApplicationContext loader | Spring Test or Spring Boot loader |
| parent | Parent context configuration in a hierarchy | Shared parent context |
| activeProfiles | Activated profiles | test, integration |
| propertySourceDescriptors | Descriptors of declared property sources | Files in @TestPropertySource |
| propertySourceProperties | Declared inline properties | feature.payment.stub=true |
| resourceBasePath | Web resource root path if applicable | @WebAppConfiguration configuration |

Annotations and extensions can contribute metadata to these parts. For example, @DynamicPropertySource and bean override declarations are added to context customizers.

Not every change in a test creates a new cache key. Changing input data in a test method, changing Mockito stubbing during test execution, or renaming methods typically does not alter the context configuration.

## 3. Property Sources and Their Impact on the Cache

Tests can supply properties in several ways:

- @TestPropertySource
- The properties attribute of @SpringBootTest
- @DynamicPropertySource
- Profile-specific configuration files such as application-test.yml
- Properties declared in configuration classes or the Environment

Property sources are used to build the Environment when the context starts. If test declarations differ, Spring may need to create different contexts to ensure each test receives the right configuration values.

### Inline Properties in @TestPropertySource

Example:

~~~java
@SpringJUnitConfig(PaymentConfiguration.class)
@TestPropertySource(properties = {
        "payment.mode=stub",
        "payment.timeout=2s"
})
class StubPaymentConfigurationTest {
}
~~~

Another class declares:

~~~java
@SpringJUnitConfig(PaymentConfiguration.class)
@TestPropertySource(properties = {
        "payment.mode=sandbox",
        "payment.timeout=2s"
})
class SandboxPaymentConfigurationTest {
}
~~~

The two tests share the same configuration class, but their inline properties differ. The resulting merged configurations differ, so they may create two separate cache entries.

This makes sense if the two classes need to verify two implementations or two operating modes. If multiple classes simply need the same set of properties, share a configuration annotation or a base test class so declarations stay consistent.

### Properties in @SpringBootTest

Spring Boot allows declaring properties directly:

~~~java
@SpringBootTest(properties = {
        "feature.invoice.enabled=true",
        "payment.mode=stub"
})
class InvoiceFeatureTest {
}
~~~

These values are part of the test configuration. If another test class uses payment.mode=sandbox or changes feature.invoice.enabled, it may need a separate context.

Avoid declaring the same set of properties in different ways across classes. For example, one class using @SpringBootTest(properties=...) and another using a separate property file even when contents are equivalent. The source metadata can differ and reduce cache reusability.

### Files in @TestPropertySource

Properties can be loaded from files:

~~~java
@SpringJUnitConfig(ReportConfiguration.class)
@TestPropertySource(locations = "classpath:/report-test.properties")
class ReportServiceTest {
}
~~~

If multiple classes use this same file and their other configurations are equivalent, they have the opportunity to share a context.

If each class points to a different file, the cache key may differ even when both files currently have identical contents. Therefore, consolidate shared properties into a meaningful single source and only create separate files when tests genuinely need separate configurations.

### Property Precedence Order

Test properties can override application configuration. In Spring Test, inline properties of @TestPropertySource have higher precedence than properties loaded from the annotation's own resource locations. Test property sources also take precedence over several standard environment and application configuration sources.

@DynamicPropertySource has higher precedence than @TestPropertySource, system properties, environment variables, and standard @PropertySource sources according to Spring's mechanism.

When the same key appears in multiple sources, identify which source is winning before concluding why a bean was created with an unexpected value. You can inspect the Environment directly in a test if you need to verify the loaded configuration.

Do not declare the same key in too many places. Having one clear owning source for a property keeps tests easy to understand and avoids creating unnecessary configuration variants.

## 4. Active Profiles and Creating Separate Contexts

Profiles determine which groups of beans or configurations are activated. @ActiveProfiles declares the profiles that Spring TestContext uses when creating the context for a test.

Example:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class CustomerServiceTest {
}
~~~

Another test:

~~~java
@SpringBootTest
@ActiveProfiles("integration")
class CustomerIntegrationTest {
}
~~~

The two tests use different profiles, so they may create two separate contexts. This is often necessary because profiles can select different datasources, message brokers, payment gateways, or implementations.

### Multiple Profiles

Multiple profiles can be declared:

~~~java
@SpringBootTest
@ActiveProfiles({"test", "stub-payment"})
class PaymentServiceTest {
}
~~~

Spring activates the declared profiles. These profiles affect beans with @Profile, corresponding property files, and other configuration conditions.

If multiple tests need the same set of profiles, use a shared configuration to avoid minor differences caused by inconsistent declarations.

### Profile Inheritance

@ActiveProfiles can be inherited from a superclass. By default, a subclass's profiles are merged with the profiles declared on the superclass.

~~~java
@SpringBootTest
@ActiveProfiles("test")
abstract class BaseIntegrationTest {
}

@ActiveProfiles("stub-payment")
class PaymentServiceTest extends BaseIntegrationTest {
}
~~~

The subclass can run with both test and stub-payment.

If you want the subclass to completely replace the superclass's profiles, use inheritProfiles = false:

~~~java
@ActiveProfiles(
        profiles = "integration",
        inheritProfiles = false
)
class RealPaymentIntegrationTest extends BaseIntegrationTest {
}
~~~

The resulting merged profiles affect the cache key. Therefore, two subclasses inheriting from the same base class that intentionally choose different profiles can create two contexts.

Use profiles to describe environments or bean groups that need to be enabled. Avoid creating a separate profile per test method if the methods only differ in input data; business data should be prepared in the test instead of turning it into a new ApplicationContext configuration.

### Default and System Profiles

When a test does not declare @ActiveProfiles, Spring may use the Environment's default profile. When @ActiveProfiles is used, Spring Test manages the list of profiles specified by the annotation or resolver.

If a project relies on spring.profiles.active from the JVM or runtime environment, clearly verify whether that mechanism is used by the test loader as expected. To keep tests reproducible, declare required profiles directly in the test or shared configuration rather than implicitly depending on the host machine.

## 5. Bean Overrides and Their Impact on the Cache

In many tests, a bean is replaced with a mock, spy, or test-specific implementation. Spring Test refers to such declarations as bean overrides.

With Spring Framework 6.2 and later, you can use:

- @MockitoBean to replace a bean with a Mockito mock.
- @MockitoSpyBean to wrap an existing bean with a Mockito spy.
- @TestBean to replace a bean with an instance provided by a static factory method.

Override declarations are processed during context construction and participate in context customizers. Therefore, two test classes with different sets of bean overrides may require different cache keys.

### @MockitoBean

Example:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;
}
~~~

Spring creates a mock for the OrderService bean in the test context and injects that mock into the controller.

Another class can use the same controller slice and the same override:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerValidationTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;
}
~~~

If the merged configuration is equivalent, both classes can reuse the same context. Mock behaviors configured in each test method can be reset according to the annotation's policy without creating a new context.

### Different Overrides Can Create Different Cache Entries

For example, one test replaces OrderService, while another replaces both OrderService and InventoryService:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @MockitoBean
    OrderService orderService;
}
~~~

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerWithInventoryTest {
    @MockitoBean
    OrderService orderService;

    @MockitoBean
    InventoryService inventoryService;
}
~~~

The two sets of overrides differ, so the context customizers may differ and the cache keys are not identical.

If multiple classes need the same set of overrides, use a composed annotation or shared test configuration to keep metadata consistent. If a test needs real beans to verify wiring or profile selection, do not override the bean that is the subject under verification.

### Bean Name, Qualifier, and Selection by Type

When multiple beans share the same type, Spring must determine which bean to replace. You can use a name or qualifier:

~~~java
@MockitoBean(name = "primaryOrderService")
private OrderService orderService;
~~~

Or:

~~~java
@MockitoBean
@Qualifier("primaryOrderService")
private OrderService orderService;
~~~

The field name can serve as a fallback qualifier in some cases. Therefore, renaming a field can affect which bean is selected when multiple candidates exist. Declare qualifiers explicitly when intent needs to remain stable.

Attributes such as bean type, name, qualifier, and override strategy are part of the metadata used to create the override. If they differ between tests, the context configuration can differ.

### Override Strategies

@MockitoBean supports bean replacement strategies, depending on the Spring Framework version:

- REPLACE_OR_CREATE: replace the bean if present, or create a new mock bean if absent.
- REPLACE: require that an existing bean be replaced.
- WRAP: wrap an existing bean with a spy.

If a test needs to prove that a real production bean is configured, using an override can mask that exact risk. Choose a strategy aligned with your goal and avoid declaring overrides more broadly than necessary.

### @MockitoSpyBean

A spy wraps a real bean so that certain methods can be observed or stubbed while keeping the rest of the implementation intact:

~~~java
@SpringBootTest
class PricingIntegrationTest {

    @MockitoSpyBean
    private PricingPolicy pricingPolicy;

    @Test
    void usesConfiguredPricingPolicy() {
        // Invoke real service and observe the Spring-managed policy.
    }
}
~~~

A spy wraps a matching existing bean. Because it changes bean configuration in the context, declaring a spy can also affect cache identity. Do not replace the same bean with a mock in one group of tests and a spy in another if the goal can be achieved with a single shared configuration.

### @TestBean

@TestBean allows replacing a bean with an instance created by a static factory method:

~~~java
@SpringBootTest
class ShippingServiceTest {

    @TestBean
    ShippingGateway shippingGateway;

    static ShippingGateway shippingGatewayTestOverride() {
        return new StubShippingGateway();
    }
}
~~~

The exact declaration syntax depends on the Spring Framework version and factory method naming rules. A bean override declaration still participates in context configuration. If multiple tests need the same replacement implementation, place the override in a shared test configuration or composed annotation.

### Difference Between Declaring a Mock and Stubbing

The following two actions have different impacts:

- Declaring @MockitoBean alters the ApplicationContext configuration and can produce a different cache key.
- Calling when(mock.method()).thenReturn(...) inside a test method only configures the behavior of an existing mock; stubbing itself does not cause Spring to create a new context.

Mockito mocks are typically reset after each test according to the bean override's default policy. This allows the context to be reused without stubbing state from a previous test leaking into the next test.

## 6. @DynamicPropertySource and Dynamic Values

@DynamicPropertySource registers properties whose values are supplied when the test needs them, often used with Testcontainers or test services with dynamic ports.

~~~java
@SpringBootTest
@Testcontainers
class DatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }
}
~~~

Dynamic property source methods are discovered and added to context customizers. Therefore, differences in declared methods can produce different context configurations.

One scenario to watch out for is when a superclass declares a shared @DynamicPropertySource while subclasses supply different containers or dynamic values. If subclasses share the same method metadata while returned values vary per subclass, the cache may reuse a context initialized with old values.

When dynamic values genuinely differ across subclasses, organize the contexts so each required set of values has its own configuration. You can use distinct methods or configurations to produce different cache keys, or use @DirtiesContext when an old context must be evicted from the cache after each class. Only use @DirtiesContext when changing dynamic values makes the cached context no longer suitable.

Do not assume values returned by suppliers are always compared as literal properties in the cache key. Context customizers and dynamic property method metadata are what matter in configuration identification. Pay special attention when an inherited method can return different values across subclasses.

## 7. Metadata Inheritance and Configuration Merging

Test classes can inherit from a base class to share configuration. Spring TestContext supports inheritance and merging across many annotations.

Example:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "feature.audit.enabled=true",
        "payment.mode=stub"
})
abstract class BaseApplicationTest {
}
~~~

Subclasses share the configuration:

~~~java
class AuditServiceTest extends BaseApplicationTest {
}

class PaymentServiceTest extends BaseApplicationTest {
}
~~~

If no other configuration is added, both classes can use the same cache entry.

A subclass can add properties:

~~~java
@TestPropertySource(properties = "feature.audit.verbose=true")
class VerboseAuditServiceTest extends BaseApplicationTest {
}
~~~

When properties are inherited and merged, the subclass has a merged configuration that differs from the base class, so it may create a separate context.

### Disabling Inheritance of Property Locations or Properties

@TestPropertySource supports:

- inheritLocations: whether to inherit resource locations from the superclass.
- inheritProperties: whether to inherit inline properties from the superclass.

Example:

~~~java
@TestPropertySource(
        properties = "payment.mode=sandbox",
        inheritProperties = false
)
class SandboxPaymentTest extends BaseApplicationTest {
}
~~~

When inheritProperties = false, the superclass's inline properties are not merged into the subclass. This alters the merged configuration and can make the cache key differ.

Similarly, inheritLocations = false can be used when a subclass needs to replace the inherited list of property files.

### Profile Inheritance

@ActiveProfiles has an inheritProfiles attribute. The default is to inherit and merge profiles from the superclass. When set to false, the subclass uses only its own declared profiles.

~~~java
@ActiveProfiles(
        profiles = "production-like",
        inheritProfiles = false
)
class ProductionLikeTest extends BaseApplicationTest {
}
~~~

Different profiles can activate different beans and property sources, so a separate context is usually needed.

### Avoiding Base Classes With Too Many Variants

A base class with many subclasses where each subclass changes profiles, properties, imports, and bean overrides differently can create many cache entries. A base class should contain configuration that is genuinely shared. Necessary variants should be clearly placed in annotations or separate configurations so readers understand why a context must differ.

## 8. Why Does the Cache Become Fragmented?

The cache becomes fragmented when a suite has many nearly identical context configurations that differ in one or more cache key components.

Example:

| Test class | Profile | Property | Bean override | Cacheability |
|---|---|---|---|---|
| OrderMvcTest | test | payment.mode=stub | OrderService mock | Context A |
| OrderMvcValidationTest | test | payment.mode=stub | OrderService mock | Can reuse Context A |
| OrderMvcSandboxTest | test | payment.mode=sandbox | OrderService mock | Different context |
| OrderMvcWithInventoryTest | test | payment.mode=stub | OrderService and Inventory mock | Different context |
| OrderIntegrationTest | integration | real database | No repository override | Different context |

Not every separate context is wasteful. If a profile or bean override reflects a genuinely different environment, a separate context is necessary. The problem arises when tests accidentally create multiple semantically equivalent configurations with differing metadata.

### Common Causes

**Different inline properties:** one class sets a timeout of 2 seconds while another sets 2000ms even though the effective configuration is equivalent. Different declarations can create different cache keys.

**Multiple property files:** each class has its own test file containing the same set of values, causing location metadata to differ.

**Inconsistent profiles:** some classes use test while others use test-local even though they do not need different environments.

**Different bean overrides:** classes mock different sets of beans or use different qualifiers/bean names.

**Inconsistent configuration imports:** tests with the same goal import additional unnecessary configurations.

**Dynamic property sources:** declared methods or dynamic values varying between subclasses can make a context unsuitable for reuse.

**Excessive @DirtiesContext:** contexts are evicted from the cache after a test or class even though the configuration could be reused.

**Too many independent configurations:** the test suite creates numerous profile/property variants merely to change data for individual scenarios.

### The Cache Key Is Not Based on Test Class Name

Two differently named test classes can still share a context. This is why consolidating common configuration into a base class or composed annotation can improve cache reuse.

Conversely, the same test class can create multiple contexts across different runs if configurations, profiles, or properties are altered by the execution environment. Renaming classes usually does not resolve fragmentation; you must inspect the actual configuration metadata.

## 9. @DirtiesContext and Cache Lifecycle

@DirtiesContext marks an ApplicationContext as no longer suitable for reuse. Spring closes the context and evicts it from the cache according to the declared mode.

Example:

~~~java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ModifiesSharedBeanStateTest {
}
~~~

Some common modes:

| Mode | When context is evicted |
|---|---|
| ClassMode.BEFORE_CLASS | Before the test class runs |
| ClassMode.AFTER_CLASS | After the test class finishes |
| MethodMode.BEFORE_METHOD | Before each test method |
| MethodMode.AFTER_METHOD | After each test method |

ClassMode and MethodMode are two separate enums of the annotation. Use the right mode type corresponding to the scope you want refreshed.

@DirtiesContext is not a component that forms the cache key. It is a lifecycle directive causing a cache entry to be evicted and the context potentially recreated.

If a test only modifies database data, prefer transaction rollback or data cleanup. If a test only modifies @MockitoBean stubbing, the mock reset mechanism usually handles that already. Only use @DirtiesContext when the state or structure of the context itself is modified and cannot be safely restored.

## 10. Cache Size, LRU, and JVM Scope

The Spring TestContext cache is a static cache within the JVM process. Tests running in the same JVM can share the context cache. If the build tool splits tests across multiple JVM forks, each process has its own cache; a context created in one fork is not automatically used in another fork.

By default, the cache has a maximum size of 32 contexts. When the limit is exceeded, Spring uses an LRU (Least Recently Used) policy to evict the least recently used context.

The limit can be changed via a system property:

~~~text
spring.test.context.cache.maxSize=64
~~~

Increasing the cache size can reduce context recreations if the suite has many configurations that are genuinely needed. However, each context may hold many beans, connection pools, and resources, so setting it too high can increase memory usage.

Resolve duplicate configurations before simply increasing maxSize. A suite with many unnecessary variants still wastes time and memory even with a larger cache.

### JVM Forks and Cache Reuse

If Gradle or Maven runs tests across multiple forks, each fork has its own cache. For example, two test classes with the same configuration running in two different JVMs will initialize separate contexts in each JVM.

This can increase execution time even when cache keys are identical. When optimizing a suite, examine both the number of distinct contexts and how the build tool distributes tests.

You do not necessarily have to disable forking to achieve cache reuse. Choosing the number of forks is a trade-off between parallelism, execution time, memory, and isolation.

## 11. Observing Cache Hits and Cache Misses

The Spring TestContext Framework can log cache statistics. Enable DEBUG logging for the logger:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

In the logs, you can observe information such as:

- Cache hit count.
- Cache miss count.
- Current cache size.
- Number of held contexts.
- Eviction statistics.

If misses climb rapidly while many tests appear to use the same configuration, look for differing annotations or metadata among them.

You can enable logging in test configuration:

~~~java
@SpringBootTest(properties = {
        "logging.level.org.springframework.test.context.cache=DEBUG"
})
class ContextCacheDiagnosticsTest {
}
~~~

If you add the logging property inconsistently to only some test classes, that property itself can create a different configuration and affect the cache. During suite-wide diagnostics, prefer configuring logging globally for the test process or setting logging from the build tool.

### Interpreting Statistics Practically

- **Increasing cache hits:** contexts are being reused; this is a good sign when tests genuinely share configuration.
- **Increasing cache misses:** Spring had to create new contexts; check whether these are necessary distinct configurations or inconsistent declarations.
- **Cache size hitting the limit:** evictions may occur when the number of distinct configurations exceeds maxSize.
- **Miss after eviction:** a context may have been removed from the cache due to LRU and had to be recreated.
- **Miss after @DirtiesContext:** may be expected behavior because a test requested closing the context.

Do not optimize solely for hit rate. If tests need two different profiles or two different sets of bean overrides to verify two configurations, two separate contexts are the right evidence.

## 12. How to Reduce Cache Fragmentation

### Share Truly Identical Property Configurations

If multiple tests need the same profiles and properties, group them into a base class or composed annotation.

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "payment.mode=stub",
        "feature.audit.enabled=true"
})
abstract class BaseServiceIntegrationTest {
}
~~~

Subclasses only add separate configuration when the risk genuinely differs.

### Create a Composed Annotation for a Group of Tests

You can define a shared annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "payment.mode=stub"
})
@interface StubPaymentIntegrationTest {
}
~~~

Then:

~~~java
@StubPaymentIntegrationTest
class OrderPaymentTest {
}

@StubPaymentIntegrationTest
class RefundPaymentTest {
}
~~~

This keeps metadata consistent and reduces mistakes where a class forgets to declare a shared property or profile.

### Use Identical Bean Overrides Across Classes

If multiple tests need to mock the same beans, declare overrides with the same type, name, and qualifier. You can use a composed annotation for a group of controller tests:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@WebMvcTest
@MockitoBean(types = {
        OrderService.class,
        CustomerService.class
})
@interface OrderMvcTest {
}
~~~

The type-level attribute syntax of @MockitoBean depends on the Spring Framework version. Check the Javadoc for your project's version before using a composed annotation. If your version does not support that form, place the override declarations in an appropriate shared structure.

### Do Not Create a Profile Per Scenario

If a test only needs to verify a different input, pass the data into the method or configure the mock. Do not create a new profile just to enable a single value for one test case.

Profiles should describe meaningful environments or bean sets, such as test, integration, or stub-payment. Specific data like customer IDs, prices, or quantities belongs in fixtures.

### Keep Property Sources Stable

Share property files when contents are genuinely identical. Avoid creating multiple separate files merely because test names differ. For inline properties, keep representations consistent to avoid nearly equivalent configurations with differing metadata.

### Limit @DirtiesContext

Before marking a context dirty, check whether state can be reset using @AfterEach, transaction rollback, or mock reset mechanisms. A context should only be evicted when it is genuinely no longer safe to reuse.

### Do Not Override the Bean Under Verification

If a test aims to verify that a profile selects the right PaymentGateway, let Spring create the real PaymentGateway. Use mocks in other tests when you need to isolate a service. Mocking the bean being verified can make the test pass without proving the configuration.

## 13. Example: Analyzing Two Test Classes Sharing a Context

Suppose the following two classes test services in the test environment:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "payment.mode=stub")
class OrderServiceIntegrationTest {
}
~~~

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "payment.mode=stub")
class RefundServiceIntegrationTest {
}
~~~

If other configurations such as classes, initializers, dynamic property methods, and bean overrides are also equivalent, both classes can share an ApplicationContext.

Now the second class is changed:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "payment.mode=sandbox")
class RefundServiceIntegrationTest {
}
~~~

The property now differs. Spring needs a context with an Environment suitable for sandbox mode. A separate cache entry is appropriate.

If the second class only needs to test different refund data while still using stub payment, keep the shared property and prepare the data inside the test. Then, the context can be reused.

### Example: Bean Override Differences

~~~java
@SpringBootTest
class OrderServiceTest {
    @MockitoBean
    PaymentGateway paymentGateway;
}
~~~

~~~java
@SpringBootTest
class RefundServiceTest {
    @MockitoBean
    PaymentGateway paymentGateway;

    @MockitoBean
    NotificationClient notificationClient;
}
~~~

The second class has an additional override. The context customizer reflects a different set of bean overrides, so the cache key may differ.

If both classes need to mock both beans, declare the same set of overrides. If OrderServiceTest does not use NotificationClient and its real bean can initialize safely, there is no need to add a mock just to make the two classes identical. The goal is to keep configurations accurate for each test and share them when genuinely equivalent.

## 14. Considerations for Parallel Execution

The Spring context cache is shared within the JVM, so multiple tests can share a context during parallel execution. Reusing a context does not mean every bean inside it is safe when multiple tests operate concurrently.

Pay attention to:

- Singleton beans with mutable state can be modified by another test.
- Shared mock beans in the context must be reset properly and should not be configured concurrently by multiple tests in conflicting ways.
- Databases and external resources must have per-test isolated data.
- A test using @DirtiesContext can close a context currently in use by another test if parallel execution is not organized properly.
- Shared containers or dynamic resources must have stable lifecycles and properties.

If the suite enables parallel execution, avoid designing tests around a shared mutable bean. Consider disabling parallelism for groups of tests with shared resources that cannot be isolated, or use separate contexts/resources when risks require it.

## 15. Investigation Workflow for a Suite With Many Contexts

When test execution time grows due to frequent ApplicationContext initialization, you can follow this sequence:

1. Enable DEBUG logging for org.springframework.test.context.cache.
2. Identify when the cache size increases and when miss counts increase.
3. Group test classes by context type: MVC, JPA, Boot integration, or custom context.
4. Compare @ActiveProfiles across classes.
5. Compare @TestPropertySource locations and inline properties.
6. Compare @SpringBootTest(properties=...) and other property sources.
7. Compare @MockitoBean, @MockitoSpyBean, @TestBean, bean names, and qualifiers.
8. Check @DynamicPropertySource and subclasses with differing dynamic values.
9. Find @DirtiesContext declarations and why they are needed.
10. Check whether the build tool splits tests across multiple JVM forks.
11. Consolidate genuinely identical configurations into a shared annotation or base class.
12. Re-run the suite and observe cache hits/misses to confirm the changes took effect.

During investigation, do not remove every bean override or profile just to raise the hit count. First, determine whether they represent a distinct configuration risk.

## 16. Design Checklist for Properties, Profiles, and Bean Overrides

Before adding configuration to a test class, determine:

- Does this property genuinely differ from the shared configuration?
- Does this profile describe a distinct environment or bean group?
- Is the bean being overridden outside the risk being verified?
- Can other tests use the same set of bean overrides?
- Is a separate property file necessary?
- Can dynamic properties change across subclasses while the context is cached?
- Can state be reset without closing the ApplicationContext?
- If contexts differ, is that difference intentional and explainable?

A separate configuration is justified when it verifies a meaningful application variant. Cache fragmentation should be addressed when variants only arise from inconsistent declarations or test data mistakenly placed into context configuration.

## Conclusion

Spring TestContext reuses ApplicationContext instances based on cache keys generated from merged configurations. Property sources, active profiles, dynamic property methods, and bean overrides can all make cache keys differ. When multiple test classes use the same configuration, standardize annotations, profiles, properties, and override sets to leverage the cache. When tests need a different environment or bean set, a separate context is necessary. Monitoring cache hits/misses, understanding the impact of @DirtiesContext, and knowing how the build tool splits JVMs will help pinpoint why a suite initializes too many contexts.
