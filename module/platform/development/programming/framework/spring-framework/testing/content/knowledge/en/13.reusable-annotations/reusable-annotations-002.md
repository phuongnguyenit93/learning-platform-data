# Packaging SpringExtension and Shared Context Configuration

Many tests in a Spring project often repeat the same group of annotations: connecting JUnit Jupiter with Spring, loading a shared configuration set, enabling a test profile, declaring properties, and attaching tags for the pipeline. If each test class declares all of that configuration on its own, changes to the environment or context initialization must be updated in many places. A test might accidentally omit `SpringExtension`, use the wrong profile, or load a different set of beans from the rest of the tests.

Spring allows packaging annotations into a **composed annotation** for reuse. With JUnit Jupiter, the built-in `@SpringJUnitConfig` annotation already combines `SpringExtension` and `@ContextConfiguration`. When a project needs its own convention, you can create a new annotation placing the Spring annotations as meta-annotations, and then use `@AliasFor` to expose the attributes that individual tests need to change.

The goal is to create a shared configuration that is easy to read, extensible, and still preserves per-test-class customization. This lesson focuses on packaging `SpringExtension`, context configuration, profiles, properties, tags, and how to reuse configuration without losing `ApplicationContext` caching.

## 1. Why Package Annotations?

A basic Spring test might require many annotations:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestConfig.class)
@ActiveProfiles("test")
@TestPropertySource(locations = "classpath:/order-test.properties")
@Tag("integration")
class OrderServiceIntegrationTest {
    // ...
}
```

If many classes use this same configuration, the declarations are repeated. When the profile is renamed, the property file changes, or context configuration is split across modules, the team has to update every class. Repeating annotations also makes tests drift easily: one class has `@ActiveProfiles("test")`, while another forgets the profile and accidentally reads the default configuration.

A composed annotation groups related metadata into one meaningful project-level annotation:

```java
@OrderIntegrationTest(classes = OrderTestConfig.class)
class OrderServiceIntegrationTest {
    // ...
}
```

Readers immediately recognize that the test group uses the shared integration configuration. When needed, the annotation can expose some attributes such as the configuration list or properties specific to the test class.

Packaging annotations is appropriate when many tests share the same policy. There is no need to create a custom annotation just to replace a simple annotation appearing in one or two places. Choose a configuration group that has a stable meaning and is used by many tests.

## 2. What Does `SpringExtension` Do?

JUnit Jupiter has an extension model so external frameworks can participate in the test lifecycle. `SpringExtension` is the bridge between JUnit Jupiter and the Spring TestContext Framework.

When registered:

```java
@ExtendWith(SpringExtension.class)
class CustomerServiceTest {
}
```

JUnit invokes the callbacks of `SpringExtension`. The extension forwards lifecycle milestones to `TestContextManager`, enabling Spring to:

- Create or retrieve an `ApplicationContext` from the context cache.
- Inject dependencies into the test instance via `@Autowired`.
- Prepare test transactions when the test uses `@Transactional`.
- Process annotations such as `@Sql`, `@DirtiesContext`, and `@ActiveProfiles`.
- Support resolving parameters from the Spring context in lifecycle methods or test methods when appropriate.

`SpringExtension` does not determine all application beans on its own. Context configuration still must be supplied via `@ContextConfiguration`, `@SpringBootTest`, a test slice, or a corresponding bootstrap mechanism.

## 3. Using `@ExtendWith` and `@ContextConfiguration` Directly

In plain Spring Framework, the explicit way to declare this is to combine the two annotations:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class CustomerServiceTest {

    @Autowired
    CustomerService customerService;

    @Test
    void findsCustomerById() {
        // ...
    }
}
```

`@ExtendWith(SpringExtension.class)` enables JUnit Jupiter integration. `@ContextConfiguration` indicates the configuration used to build the `ApplicationContext`, such as Java configuration classes, XML resources, or initializers.

With Java configuration:

```java
@Configuration
@ComponentScan(basePackageClasses = CustomerService.class)
class TestConfig {
}
```

With XML:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(locations = "classpath:/spring/customer-test-context.xml")
class CustomerServiceXmlTest {
}
```

`@ContextConfiguration` can accept both `classes` and `locations` if the context needs to combine Java configuration with XML. Avoid declaring the same configuration sources on both a class and its superclass unless you understand how Spring merges metadata.

## 4. `@SpringJUnitConfig` Is a Built-in Composed Annotation

Spring provides `@SpringJUnitConfig` in the `org.springframework.test.context.junit.jupiter` package. This annotation combines:

- `@ExtendWith(SpringExtension.class)` for JUnit Jupiter integration.
- `@ContextConfiguration` to specify how to create the Spring `ApplicationContext`.

Therefore, you can write it concisely:

```java
@SpringJUnitConfig(classes = CustomerTestConfig.class)
class CustomerServiceTest {

    @Autowired
    CustomerService customerService;

    @Test
    void findsCustomerById() {
        // ...
    }
}
```

`@SpringJUnitConfig` provides the `classes` and `locations` attributes as aliases for the corresponding attributes of `@ContextConfiguration`.

Example of loading Java config and XML together:

```java
@SpringJUnitConfig(
    classes = CustomerTestConfig.class,
    locations = "classpath:/spring/legacy-customer-beans.xml"
)
class CustomerMigrationTest {
}
```

If you only need `SpringExtension` plus `@ContextConfiguration`, prefer `@SpringJUnitConfig`. This annotation already expresses the exact intent without needing to write a new composed annotation.

## 5. Spring Boot Test Annotations Already Integrate SpringExtension

In Spring Boot, common testing annotations are already wired to Spring Test. For example:

- `@SpringBootTest` initializes the context using Spring Boot's bootstrap mechanism.
- `@WebMvcTest` creates a web slice for testing MVC.
- `@DataJpaTest` creates a JPA slice for testing persistence.
- Other slices such as `@JsonTest` or `@RestClientTest` also integrate Spring Test for their specific purposes.

Consequently, tests using these annotations usually do not need to add `@ExtendWith(SpringExtension.class)` or `@SpringJUnitConfig` again.

Example:

```java
@SpringBootTest
class ApplicationIntegrationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void startsApplicationContext() {
        assertNotNull(context);
    }
}
```

`@SpringBootTest` already supplies the appropriate bootstrapper and extension. If you add `@SpringJUnitConfig` on the same class, you may create two unnecessary sets of context metadata or conflict with how Spring Boot selects configuration. Choose the bootstrap annotation that fits the test type.

## 6. What Is a Composed Annotation?

An annotation can be placed on another annotation's definition. The inner annotation is called a meta-annotation. Spring reads this metadata through its merged annotations mechanism to find direct and indirect annotations on a test class.

For example, a custom annotation can include `@SpringJUnitConfig`, `@ActiveProfiles`, and `@Tag`:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig
@ActiveProfiles("integration")
@Tag("integration")
public @interface IntegrationSpringTest {
}
```

Then the test class only needs:

```java
@IntegrationSpringTest
class OrderServiceIntegrationTest {
}
```

This annotation packages a policy: use `SpringExtension`, create the context via Spring Test, activate the `integration` profile, and attach the JUnit `integration` tag.

For the annotation to work properly at runtime, keep `@Retention(RetentionPolicy.RUNTIME)`. Spring and JUnit must be able to read the metadata when tests are discovered and executed.

## 7. `@AliasFor` Exposes Configuration Attributes for Each Test Class

A composed annotation often needs to allow each test to specify its own configuration classes. Spring provides `@AliasFor` so an attribute of a custom annotation overrides an attribute of a meta-annotation.

Example:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig
@ActiveProfiles("integration")
public @interface IntegrationSpringTest {

    @AliasFor(annotation = SpringJUnitConfig.class, attribute = "classes")
    Class<?>[] classes() default {};
}
```

Usage:

```java
@IntegrationSpringTest(classes = OrderTestConfig.class)
class OrderServiceIntegrationTest {
}
```

Spring forwards the `classes` value of `@IntegrationSpringTest` to the `classes` attribute of `@SpringJUnitConfig`, and then to `@ContextConfiguration`. The test class does not need to declare `@ContextConfiguration` separately.

`@AliasFor` keeps shared configuration in one annotation while still letting tests supply the varying parts. If there is no need to change an attribute, there is no reason to expose it.

## 8. Packaging Context Configuration and Properties into a Reusable Annotation

A practical annotation can combine `SpringExtension`, context classes, profiles, and tags. Property sources can be declared separately on the test class if each test needs different files or values:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig
@ActiveProfiles("integration")
@Tag("integration")
public @interface OrderIntegrationTest {

    @AliasFor(annotation = SpringJUnitConfig.class, attribute = "classes")
    Class<?>[] classes() default {};

    @AliasFor(annotation = SpringJUnitConfig.class, attribute = "locations")
    String[] locations() default {};
}
```

The test class can choose the necessary configuration:

```java
@OrderIntegrationTest(
    classes = {OrderTestConfig.class, SharedTestConfig.class}
)
@TestPropertySource(
    locations = "classpath:/order-test.properties",
    properties = "feature.audit.enabled=false"
)
class OrderServiceIntegrationTest {

    @Autowired
    OrderService orderService;
}
```

In the example:

- `@SpringJUnitConfig` packages `SpringExtension` and `@ContextConfiguration`.
- `@ActiveProfiles("integration")` activates the shared profile.
- `@TestPropertySource` allows loading dedicated files and properties.
- `@Tag("integration")` allows build tools to filter the test group.
- `@AliasFor` forwards attributes supplied by the test class to the corresponding meta-annotation.

The property source is placed directly on the test class so the shared annotation does not force every test to use the same file or the same values. If a group truly shares fixed properties, you can add `@TestPropertySource` as a meta-annotation without exposing aliases or create a dedicated composed annotation for that group.

This is a structural example. In a real project, only put policies that are genuinely shared into the annotation. If every test class has completely different properties and contexts, the annotation can become an obscure configuration layer.

## 9. Important Rules When Declaring `@AliasFor`

`@AliasFor` has several rules that must be followed:

- The custom annotation must be retained at runtime so Spring can read metadata.
- The referenced meta-annotation must actually be present in the annotation composition.
- The data type of the alias attribute must be compatible with the target attribute.
- When aliasing two attributes in the same annotation, they must have compatible types and default values.
- For an alias overriding a meta-annotation attribute, the default value must follow Spring's rules so merged annotations can determine a consistent value.
- Do not create multiple overlapping alias paths where one attribute could override different sources.

A simple and safe example is aliasing `classes` with an empty default to match the `classes` attribute of `@SpringJUnitConfig`:

```java
@AliasFor(annotation = SpringJUnitConfig.class, attribute = "classes")
Class<?>[] classes() default {};
```

If you want to support both `value` and `classes` as two synonymous names in the custom annotation, you must declare an alias within the same annotation:

```java
@AliasFor("classes")
Class<?>[] value() default {};

@AliasFor("value")
Class<?>[] classes() default {};
```

Do not add this alias pair if the team only needs the single name `classes`. Each additional alias is another metadata rule to maintain.

When Spring reports an error about an alias, check the annotation composition, attribute names, types, and default values before changing how the context is bootstrapped.

## 10. Reusing Context Configuration with Shared Configuration Classes

A composed annotation decides how a test activates Spring, while `@ContextConfiguration` defines the context configuration. For multiple tests to share the same context, shared beans should be grouped into one or more configuration classes.

Example:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = OrderService.class)
@Import({PersistenceTestConfig.class, SharedTestBeans.class})
class SharedIntegrationTestConfig {
}
```

Tests can reference the same configuration:

```java
@SpringJUnitConfig(SharedIntegrationTestConfig.class)
class OrderServiceIntegrationTest {
}

@SpringJUnitConfig(SharedIntegrationTestConfig.class)
class CustomerServiceIntegrationTest {
}
```

If the merged context configurations of two tests are equivalent, Spring Test can reuse the same `ApplicationContext` from the cache. This reduces the time spent creating datasources, services, repositories, and singleton beans.

Place shared configurations in an appropriate test-support module or test package. Do not put a bean that only serves a single test into the shared configuration if it changes the context for all other tests.

## 11. Separating Shared Configuration from Per-Test Configuration

A maintainable test configuration typically has two layers:

- **Shared configuration:** foundational beans, profiles, test datasource, fixed clock, fakes, or test adapters used by many classes.
- **Specific configuration:** bean overrides, properties, or imports needed only by a specific group of tests.

Shared configuration example:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = OrderService.class)
class SharedTestConfig {

    @Bean
    Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Specific configuration for payment tests:

```java
@TestConfiguration(proxyBeanMethods = false)
class PaymentTestConfig {

    @Bean
    PaymentPort paymentPort() {
        return new FakePaymentAdapter();
    }
}
```

The test combines the two configurations:

```java
@SpringJUnitConfig(classes = {
    SharedTestConfig.class,
    PaymentTestConfig.class
})
class PaymentWorkflowTest {
}
```

In Spring Boot, `@TestConfiguration` is designed for supplementary configuration in tests. It can be imported with `@Import(PaymentTestConfig.class)` or included in the appropriate class list. If using plain Spring Framework, a `@Configuration` class in the test source set can also serve as test configuration.

## 12. Using `@Import` to Extend Shared Contexts

When a test needs an additional specific module, `@Import` helps compose configurations without creating one huge configuration for all tests:

```java
@Configuration(proxyBeanMethods = false)
class MessagingTestConfig {

    @Bean
    OrderEventPort orderEventPort() {
        return new InMemoryOrderEventPort();
    }
}
```

A test that needs to verify events:

```java
@SpringJUnitConfig(classes = {
    SharedIntegrationTestConfig.class,
    MessagingTestConfig.class
})
class OrderEventIntegrationTest {
}
```

`@Import` can bring configuration classes or component classes into the context. If a test needs XML resources, `@ImportResource` can be placed on the test configuration. Keep configuration sources clear so readers know which module each bean comes from.

Do not use overly broad component scanning just to find one test bean. `@Import` with specific classes keeps the context scope clear and reduces the risk of registering unintended beans.

## 13. Packaging Spring Boot Test Configuration

If the project primarily uses Spring Boot, a composed annotation can be based on `@SpringBootTest` instead of `@SpringJUnitConfig`:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("integration")
@Tag("integration")
public @interface IntegrationBootTest {

    @AliasFor(annotation = SpringBootTest.class, attribute = "classes")
    Class<?>[] classes() default {};

    @AliasFor(annotation = SpringBootTest.class, attribute = "properties")
    String[] properties() default {};
}
```

Usage:

```java
@IntegrationBootTest(
    classes = OrdersApplication.class,
    properties = "feature.external-notifications=false"
)
class OrderApplicationIntegrationTest {
}
```

This annotation packages `@SpringBootTest`, so there is no need to add `@SpringExtension` or `@SpringJUnitConfig`. `@SpringBootTest` already uses the Spring Boot test bootstrapper and integrates `SpringExtension`.

If tests need a real web environment, decide whether that is a shared policy or just a choice for one test class. You can expose the `webEnvironment` attribute via `@AliasFor` if the team genuinely needs multiple modes. Do not hardcode `RANDOM_PORT` in an annotation also used for service tests that do not need a server.

## 14. Packaging Dedicated Test Slices

Slices have different goals. You can create a composed annotation for a group of MVC tests:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@WebMvcTest
@ActiveProfiles("web-test")
@Tag("web")
public @interface WebLayerTest {

    @AliasFor(annotation = WebMvcTest.class, attribute = "controllers")
    Class<?>[] controllers() default {};
}
```

Usage:

```java
@WebLayerTest(controllers = OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;
}
```

`@WebMvcTest` already integrates Spring Test. The composed annotation simply adds a profile, a tag, and a shorter API name for the controller list.

Similarly, you can create annotations for `@DataJpaTest` or `@JsonTest` if the team has genuinely shared configuration. Do not create a single shared annotation that includes mutually exclusive slices; a test should clearly choose the scope to verify.

## 15. Using `@ActiveProfiles` and Properties in Reusable Configuration

Profiles help select beans/configurations by environment. A composed annotation can fix a shared profile:

```java
@SpringJUnitConfig(SharedIntegrationTestConfig.class)
@ActiveProfiles("integration")
@TestPropertySource(properties = {
    "feature.notifications.enabled=false",
    "feature.audit.enabled=true"
})
@Tag("integration")
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface SharedIntegrationTest {
}
```

Tests using the annotation receive the same default profile and properties. If a test needs different properties, you can expose attributes via `@AliasFor` or define a dedicated composed annotation for that group.

Do not add every test property to the shared annotation. A property tied to a specific feature can cause all tests using the annotation to receive unnecessary configuration. Keep the shared part at a genuinely stable baseline.

### Inline Properties vs. Property Files

`@TestPropertySource(properties = ...)` fits a small, explicit set of values. `locations` fits when there are many properties or you want to reuse a file. Both can be provided; inline properties take higher precedence than properties loaded from resources via the same annotation.

When using a composed annotation, name aliases clearly so users can distinguish them:

```java
@AliasFor(annotation = TestPropertySource.class, attribute = "locations")
String[] propertyLocations() default {};

@AliasFor(annotation = TestPropertySource.class, attribute = "properties")
String[] properties() default {};
```

## 16. Inheriting Configuration via a Test Superclass

Besides composed annotations, Java class inheritance can share configuration across multiple test classes:

```java
@SpringJUnitConfig(SharedIntegrationTestConfig.class)
@ActiveProfiles("integration")
abstract class AbstractIntegrationTest {

    @Autowired
    protected OrderRepository orderRepository;
}
```

A subclass inherits:

```java
class OrderRepositoryTest extends AbstractIntegrationTest {

    @Test
    void findsOrderById() {
        // Uses orderRepository injected from the shared context
    }
}
```

Spring Test supports inheriting context metadata from a superclass. `@ContextConfiguration` inherits locations/classes and initializers by default according to its corresponding inheritance attributes. `@ActiveProfiles` also supports profile inheritance by default.

However, inheritance makes configuration less visible at the test class. If a subclass declares its own configuration, you need to understand how metadata is merged and whether `inheritLocations` or `inheritProfiles` is enabled.

Base classes also easily become a place that accumulates too many dependencies and setups. Keep them small, containing only truly shared configuration or fixtures. A composed annotation usually expresses intent more directly when the goal is simply reusing metadata without inheriting Java behavior.

## 17. Combining Composed Annotations with a Superclass

Both approaches can work together. For example, an annotation defines the context policy, while a base class provides helpers or fixtures:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig(SharedIntegrationTestConfig.class)
@ActiveProfiles("integration")
@Tag("integration")
public @interface SharedIntegrationTest {
}
```

```java
abstract class AbstractOrderTest {

    @Autowired
    protected OrderRepository orderRepository;

    protected Order createTestOrder(String customerId) {
        return new Order(customerId);
    }
}
```

```java
@SharedIntegrationTest
class OrderRepositoryTest extends AbstractOrderTest {
}
```

The annotation handles configuration; the superclass provides helpers. This separation ensures test classes do not have to extend a base class just to receive `@ExtendWith` or `@ContextConfiguration`.

## 18. `@TestExecutionListeners` and Shared Configuration

A composed annotation can also package a custom listener if every test in the group needs the same behavior:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig(SharedIntegrationTestConfig.class)
@TestExecutionListeners(
    listeners = TestTimingListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
public @interface TimedIntegrationTest {
}
```

`MERGE_WITH_DEFAULTS` keeps Spring's default listeners such as dependency injection, transactions, and SQL scripts, while adding the custom listener. If `REPLACE_DEFAULTS` is used, default listeners may be replaced and familiar features can stop working.

Only package a listener when it is part of a shared policy. A specialized listener serving only one test class should be declared on that test to avoid subjecting every test to extra callbacks or side effects.

## 19. JUnit Tags Can Be Packaged with Annotations

JUnit Jupiter allows using `@Tag` as a meta-annotation. This lets a composed annotation configure Spring and categorize tests at the same time:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig(SharedIntegrationTestConfig.class)
@Tag("integration")
@Tag("database")
public @interface DatabaseIntegrationTest {
}
```

Build tools can filter the `integration` or `database` tag to create appropriate execution groups. Tags do not activate Spring profiles on their own and do not create databases. `@ActiveProfiles`, datasource configuration, or Testcontainers must still be declared separately.

If a test has multiple tags that vary by purpose, you can keep `@Tag` directly on the test class or method instead of stuffing all of them into the shared annotation.

## 20. Composed Annotations and the Context Cache

Spring Test caches `ApplicationContext` instances based on the merged context configuration. Configuration components such as classes/locations, initializers, active profiles, property sources, context loaders, parent contexts, and context customizers can affect whether two tests share a cache entry.

Composed annotations help tests use the same metadata consistently. For example, if ten tests all use `@SharedIntegrationTest`, they share the same base configuration and have the opportunity to reuse the context.

The following changes can cause contexts to differ:

- A test supplies additional configuration classes or XML locations.
- A test uses different profiles.
- Inline properties or property resources differ.
- A test adds bean overrides such as `@MockitoBean` or `@MockitoSpyBean`.
- Context initializers, loaders, or parent contexts differ.
- A test marks the context dirty and requests eviction from the cache.

Do not force all tests to share the same context by dumping every bean into one giant configuration. Group tests by genuinely identical configurations. The cache helps reuse contexts when metadata is equivalent; it is not a reason to mix unrelated environments or dependencies.

## 21. Avoid `@DirtiesContext` in Shared Annotations

You should not place `@DirtiesContext` by default in a shared annotation used by all integration tests. This annotation marks the context for eviction from the cache. If applied to every test class or method, tests may continuously create new contexts and pipeline runtime increases sharply.

Only use `@DirtiesContext` for test groups that genuinely mutate context state or singleton beans in an unrecoverable way. Business data in a database, cache, or message broker should be cleaned up at the data source itself.

If a special group of tests needs a fresh context, create a dedicated annotation whose name clearly expresses that policy, or declare `@DirtiesContext` directly on the relevant class. Do not put rare behavior into the base annotation of the entire suite.

## 22. Organizing Reusable Annotations in a `test-support` Module

When a project has multiple modules, you can create a `test-support` module containing:

- Composed annotations such as `@SharedIntegrationTest`, `@WebLayerTest`, or `@DatabaseIntegrationTest`.
- Shared configuration classes such as `SharedIntegrationTestConfig`.
- Fixture factories and test data builders.
- Fake adapters or test-specific beans.
- Shared listeners and JUnit extensions.

Application modules add the `test-support` dependency in test scope. That way, shared annotations and configurations are not packaged into production artifacts.

Maven dependency example:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>application-test-support</artifactId>
    <version>${project.version}</version>
    <scope>test</scope>
</dependency>
```

With Gradle:

```kotlin
testImplementation(project(":application-test-support"))
```

Ensure the `test-support` module has the necessary Spring Test and JUnit Jupiter dependencies. If the annotations are only used at test compile/runtime, these dependencies should stay in the appropriate scope so test frameworks are not pulled into production runtime.

## 23. Verifying That a Composed Annotation Actually Works

A reusable annotation should have at least one small test confirming the context is created and metadata is applied. Example:

```java
@SharedIntegrationTest
class SharedIntegrationAnnotationTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    Environment environment;

    @Test
    void loadsSharedContextAndActivatesIntegrationProfile() {
        assertNotNull(context.getBean(OrderService.class));
        assertTrue(environment.acceptsProfiles(Profiles.of("integration")));
    }
}
```

This test verifies the class configuration and profile. If the annotation has `classes`, `locations`, or `properties` aliases, include a test using overridden values to prove the aliases forward properly to the meta-annotation.

Example of verifying properties:

```java
@OrderIntegrationTest(
    classes = OrderTestConfig.class,
    properties = "feature.audit.enabled=false"
)
class OrderTestPropertyAliasTest {

    @Value("${feature.audit.enabled}")
    boolean auditEnabled;

    @Test
    void appliesPropertyDeclaredThroughComposedAnnotation() {
        assertFalse(auditEnabled);
    }
}
```

If an alias is wrong, Spring may report an error when parsing the annotation or fail to apply the expected value. Testing a shared annotation once catches errors before many test classes depend on it.

## 24. Common Mistakes When Packaging Annotations

- **Forgetting `@Retention(RUNTIME)`:** Spring/JUnit cannot read metadata at runtime.
- **Forgetting `@Target(TYPE)`:** the annotation cannot be placed on test classes if the target does not permit it.
- **Registering `SpringExtension` redundantly:** adding `@SpringJUnitConfig` to a test that already uses `@SpringBootTest` or a slice annotation with built-in extension integration.
- **Confusing `@SpringJUnitConfig` with `@SpringBootTest`:** one loads the context via `@ContextConfiguration`, while the other uses Spring Boot's bootstrapper and auto-configuration.
- **Not declaring `@AliasFor`:** attributes on the custom annotation are not forwarded to the meta-annotation.
- **Wrong alias name or type:** Spring cannot merge metadata or throws an error when reading the annotation.
- **Putting feature-specific properties in the base annotation:** every test receives unnecessary configuration.
- **Using one annotation for multiple slice types:** tests lack clear scope and configurations can conflict.
- **Inheriting through too many base classes:** configuration and fixtures are buried deep in the hierarchy.
- **Placing `@DirtiesContext` in a shared annotation:** the context cache is invalidated too frequently.
- **Sharing a context while sharing mutable data:** tests become order-dependent or fail when run in parallel.
- **Not testing aliases:** a single annotation change can break the configuration of multiple modules at once.

## 25. Process for Designing Reusable Annotations

When a team wants to standardize Spring tests, follow this sequence:

1. **Identify metadata that genuinely repeats:** extensions, context classes, profiles, properties, tags, or listeners.
2. **Choose the base annotation:** use `@SpringJUnitConfig` for plain Spring Framework; use `@SpringBootTest` or the corresponding test slice for Spring Boot.
3. **Create the composed annotation:** place the meta-annotations on the new annotation with appropriate target and retention.
4. **Expose attributes needing customization:** use `@AliasFor` for configuration classes, locations, or properties that test classes need to provide.
5. **Keep bean configuration in separate classes:** group shared beans into `@Configuration` or `@TestConfiguration`, and extend with `@Import` when needed.
6. **Separate test groups with different goals:** web slices, JPA slices, and full integration tests should have separate annotations if policies differ.
7. **Check the context cache:** use identical metadata for tests that can share a context; avoid unnecessary differences in properties or bean overrides.
8. **Write a test for the annotation itself:** verify the context, profiles, properties, and aliases work properly.
9. **Place in a `test-support` module:** if multiple modules use it, package the annotations and configurations in test scope.

## 26. Complete Example: Integration Annotation for the Order Module

Suppose the order module has many integration tests sharing persistence configuration, the `integration` profile, and the `integration` tag. Each test can declare its own properties when needed.

Shared configuration:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = OrderService.class)
@Import(PersistenceTestConfig.class)
class OrderIntegrationConfig {
}
```

Composed annotation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig
@ActiveProfiles("integration")
@Tag("integration")
public @interface OrderIntegrationTest {

    @AliasFor(annotation = SpringJUnitConfig.class, attribute = "classes")
    Class<?>[] classes() default {};
}
```

Test using it:

```java
@OrderIntegrationTest(classes = OrderIntegrationConfig.class)
@TestPropertySource(properties = "feature.notifications.enabled=false")
class OrderServiceIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void createsOrderAndPersistsIt() {
        OrderId orderId = orderService.place(validCommand());

        assertTrue(orderRepository.findById(orderId).isPresent());
    }
}
```

Another test can extend the configuration:

```java
@OrderIntegrationTest(classes = {
    OrderIntegrationConfig.class,
    PaymentTestConfig.class
})
@TestPropertySource(properties = {
    "feature.notifications.enabled=false",
    "payment.mode=sandbox"
})
class PaymentWorkflowIntegrationTest {
}
```

In real examples, when a meta-annotation attribute has a fixed default value, design the alias and default value to comply with Spring's `@AliasFor` rules. If exposing an alias makes the default confusing, you can keep profiles/properties fixed in the annotation and create a dedicated annotation for test groups with different needs.

## 27. Choosing Between a Composed Annotation and a Base Test Class

Both approaches aid reuse, but solve different needs:

| Criterion | Composed Annotation | Base Test Class |
| --- | --- | --- |
| Sharing Spring/JUnit metadata | Very suitable | Possible, via inherited annotations |
| Sharing helper methods and fixtures | No | Suitable |
| Allowing the test class to extend another class | Yes | Occupies the superclass slot |
| Configuration visibility on the test class | Clear via one named annotation | Partly located in the superclass |
| Exposing configuration attributes | Use `@AliasFor` | Use annotations directly or override config per Spring rules |
| Appropriate scope | Independently reusable test policies | Java behavior or fixtures needing inheritance |

If you only need to bundle `SpringExtension`, profiles, and context config, a composed annotation is usually cleaner. If you need helpers, sample data, or shared setup/teardown, a base class can be useful. Both can be combined while keeping each mechanism to one clear responsibility.

## 28. Summary

`SpringExtension` connects JUnit Jupiter with the Spring TestContext Framework. `@SpringJUnitConfig` already packages this extension together with `@ContextConfiguration`, while Spring Boot annotations such as `@SpringBootTest` and test slices integrate Spring Test according to their own bootstraps.

When many tests need the same profiles, properties, tags, and configuration set, you can create a composed annotation. `@AliasFor` lets test classes customize attributes such as configuration classes, XML locations, or properties. Bean configuration should be grouped in separate classes and extended with `@Import` when needed. Keeping metadata consistent helps Spring Test reuse `ApplicationContext` instances effectively and helps test classes clearly express the configuration policy in effect.
