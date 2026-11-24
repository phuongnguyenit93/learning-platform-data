# Configuration Loading and Integration Test Management Issues

Spring integration tests often require multiple components to work together: dependency injection, application configuration, repositories, transactions, the web layer, message listeners, and external services. The Spring TestContext Framework provides mechanisms to create an `ApplicationContext`, inject dependencies into tests, manage transactions, and reuse contexts across tests. When configuration is unclear or each test requires a different context, the test suite can start very slowly, become difficult to diagnose on failure, or accidentally share state across scenarios.

Good integration test design begins by choosing the right context scope, declaring configuration and property sources accurately, and then managing the context lifecycle according to actual needs. A context should contain only the beans needed for testing; mutable data and resources need dedicated isolation; and a context should only be closed and recreated when its state is genuinely no longer safe to reuse.

## 1. What Does the Spring TestContext Framework Manage?

The TestContext Framework is Spring's testing integration foundation. It coordinates with JUnit Jupiter through `SpringExtension` and provides a `TestContext` containing information about the test class, test method, `ApplicationContext`, and related attributes.

Some important components:

| Component | Responsibility |
|---|---|
| `SpringExtension` | Connects the JUnit Jupiter lifecycle with the Spring TestContext Framework |
| `TestContextManager` | Coordinates callbacks and listeners for the test class/method |
| `TestContext` | Provides the current context, test instance, test method, and test attributes |
| `TestExecutionListener` | Executes behaviors such as dependency injection, transactions, and `@DirtiesContext` handling |
| `TestContextBootstrapper` | Determines how to build the test context configuration |
| `ContextLoader` / `SmartContextLoader` | Creates the `ApplicationContext` from the merged configuration |

With JUnit Jupiter, you can enable the Spring extension directly:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = CustomerServiceTestConfig.class)
class CustomerServiceIntegrationTest {
    @Autowired
    private CustomerService customerService;

    @Test
    void loadsCustomerServiceFromSpringContext() {
        assertThat(customerService).isNotNull();
    }
}
```

When using Spring Boot, `@SpringBootTest`, `@DataJpaTest`, `@WebMvcTest`, and similar test slices already integrate the necessary extension mechanism. There is no need to mechanically add `@ExtendWith(SpringExtension.class)` when a higher-level annotation already provides it.

The TestContext Framework does not simply create a context once per test. It builds the merged configuration, looks up a matching context in the cache, creates a new one if none exists, and manages listeners according to the test lifecycle. Understanding this mechanism explains why two test classes can share the same context or why a small change in annotations causes the suite to boot additional times.

## 2. Choosing the Right Way to Load Configuration

Spring offers multiple ways to create a test context. Choose according to the scope you need to test.

### 2.1. `@ContextConfiguration` for a Scoped Spring Context

`@ContextConfiguration` declares resource locations or configuration classes to load an `ApplicationContext`. It is suitable for Spring integration tests that do not need all of Spring Boot's auto-configuration.

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = {
        CustomerServiceConfig.class,
        CustomerRepositoryTestConfig.class
})
class CustomerServiceIntegrationTest {
    @Autowired
    private CustomerService customerService;

    @Test
    void createsCustomer() {
        Customer customer = customerService.create("Lan");

        assertThat(customer.name()).isEqualTo("Lan");
    }
}
```

`classes` usually contains `@Configuration`, components, or configuration classes that the loader can process. If using XML, you can declare `locations`:

```java
@ContextConfiguration(locations = "classpath:/test-context.xml")
class LegacyIntegrationTest {
    // Dependencies are retrieved from the XML context.
}
```

You can use `@SpringJUnitConfig` as a concise way to combine `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`:

```java
@SpringJUnitConfig(CustomerServiceTestConfig.class)
class CustomerServiceTest {
    // The test uses the specified Spring configuration.
}
```

When configuration is explicitly specified via classes, readers know which beans the context needs. This also avoids accidentally scanning the entire application when a test only needs a small part.

### 2.2. `@SpringBootTest` to Load a Spring Boot Application

`@SpringBootTest` creates a test context based on Spring Boot's startup mechanism. If `classes` is not specified, Spring Boot searches for a suitable `@SpringBootConfiguration` class, typically the class annotated with `@SpringBootApplication`, by scanning from the test's package up through parent packages.

```java
@SpringBootTest
class OrderServiceIntegrationTest {
    @Autowired
    private OrderService orderService;

    @Test
    void loadsApplicationServices() {
        assertThat(orderService).isNotNull();
    }
}
```

If there are multiple application configuration classes or the test lies outside the scanned package tree, explicitly specify the configuration class:

```java
@SpringBootTest(classes = LearningApplication.class)
class OrderServiceIntegrationTest {
    // Loads the application starting from LearningApplication.
}
```

A common error is `Unable to find a @SpringBootConfiguration`. Check the test's package, the location of the main application class, and the `classes` attribute before adding a dummy application configuration just to make the test start.

### 2.3. Choosing the Web Environment

`@SpringBootTest` lets you specify how the web environment is created via `webEnvironment`:

| Value | Behavior |
|---|---|
| `MOCK` | Creates a mock web application context if the application has a web stack; does not start a real HTTP server. This is the default. |
| `RANDOM_PORT` | Starts a real server on a random port. |
| `DEFINED_PORT` | Starts a real server on the configured port, typically 8080 if unchanged. |
| `NONE` | Creates an application context without a web environment. |

Example of testing an endpoint with `MockMvc` using the full application context:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class OrderApiIntegrationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsOrderFromApplicationContext() throws Exception {
        mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk());
    }
}
```

When you need to test an HTTP server, port binding, or socket-level interaction, use `RANDOM_PORT`:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {
    @LocalServerPort
    private int port;

    @Test
    void startsHttpServerOnAnAvailablePort() {
        assertThat(port).isPositive();
    }
}
```

`RANDOM_PORT` has higher server startup overhead than `MOCK`, so use it only when real server behavior is part of the test goal. One thing to remember: HTTP requests are processed on a server thread, while the test method's transaction runs on the test thread. A test-managed transaction does not automatically wrap the server request's transaction; data created by the request may be committed and require separate cleanup.

### 2.4. Test Slices for a Layer of the Application

Spring Boot provides slice annotations such as `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, and other slices. They load a set of beans tailored to a specific layer, typically excluding unrelated parts of the application.

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;
}
```

`@WebMvcTest` focuses on MVC: controllers, binding, validation, converters, filters, and selected web configuration. Services are typically replaced with mocks so the test focuses on the HTTP contract.

```java
@DataJpaTest
class OrderRepositoryTest {
    @Autowired
    private OrderRepository orders;
}
```

`@DataJpaTest` focuses on entities, repositories, and JPA configuration. It typically uses a test transaction rolled back after each method. If you need to add configuration beans or import a component, declare the extension explicitly rather than switching all repository tests to `@SpringBootTest`.

A test slice is not a full replica of the application. If a bean is not loaded in a slice, that may be intentional behavior. Add the exact required configuration using `@Import`, `@TestConfiguration`, or the corresponding extension annotation.

## 3. Adding Test-Specific Configuration

Do not modify production configuration just to satisfy a test condition. Spring Test allows adding test configuration via configuration classes, profiles, and property sources.

### 3.1. `@TestConfiguration` and `@Import`

`@TestConfiguration` marks additional configuration intended only for tests. A nested `@TestConfiguration` class inside a test can add beans while preserving Spring Boot's main application configuration detection.

```java
@SpringBootTest
@Import(TestClockConfiguration.class)
class SubscriptionIntegrationTest {
    @Autowired
    private SubscriptionService subscriptions;
}

@TestConfiguration
class TestClockConfiguration {
    @Bean
    @Primary
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-11-12T08:30:00Z"), ZoneOffset.UTC);
    }
}
```

`@Import` makes explicit the additional configuration loaded with the context. `@Primary` helps Spring choose the test bean when multiple beans of the same type exist. If the dependency uses `@Qualifier`, provide the matching name/qualifier.

You can declare a nested test configuration inside the test class:

```java
@SpringBootTest
class PaymentIntegrationTest {
    @Autowired
    private PaymentService paymentService;

    @TestConfiguration
    static class PaymentTestConfiguration {
        @Bean
        PaymentGateway paymentGateway() {
            return new InMemoryPaymentGateway();
        }
    }
}
```

The nested configuration class is static so it does not require an instance of the enclosing test class. If using a top-level configuration class, import it explicitly when you need to add it to the context.

### 3.2. `@ActiveProfiles` to Select Profiles

`@ActiveProfiles` activates profiles for the test context. For example, the application has `application-integration.yml`:

```java
@SpringBootTest
@ActiveProfiles("integration")
class CustomerIntegrationTest {
    // Loads common configuration and configuration for the integration profile.
}
```

A profile can contain endpoints, database names, logging settings, or feature flags for the test environment. Do not put production credentials in test profiles and do not use profiles to hide unclear configuration.

When inheriting test classes, `@ActiveProfiles` inherits profiles from the superclass by default. If a subclass needs to completely define its own profiles, you can use `inheritProfiles = false`.

```java
@ActiveProfiles(value = "repository-test", inheritProfiles = false)
class IsolatedRepositoryTest extends BaseIntegrationTest {
}
```

Name profiles according to their purpose and keep them consistent across your IDE, Gradle/Maven, and CI. Avoid enabling a profile via a local-only environment variable without including the corresponding configuration in the test execution workflow.

### 3.3. `@TestPropertySource`

`@TestPropertySource` adds a property source to the `Environment` of the test context. Configuration can be read from a file:

```java
@SpringBootTest
@TestPropertySource(locations = "classpath:/integration-test.properties")
class NotificationIntegrationTest {
}
```

Or declared as inline properties:

```java
@SpringBootTest
@TestPropertySource(properties = {
        "notification.delivery.enabled=false",
        "notification.retry.max-attempts=2"
})
class NotificationIntegrationTest {
}
```

Inline properties take higher precedence than file locations declared in the same `@TestPropertySource`. When testing a specific value, inline properties help the test self-document its conditions without creating extra files.

Spring Boot also supports the `properties` attribute on `@SpringBootTest`:

```java
@SpringBootTest(properties = "feature.invoice.enabled=true")
class InvoiceFeatureIntegrationTest {
}
```

Do not declare the same key in too many places without knowing which source wins. When a property does not have the expected value, check the active profiles, loaded files, inline properties, and dynamic sources before changing beans.

## 4. Dynamic Properties for Runtime-Allocated Resources

Some test dependencies do not have a fixed URL or port before startup. For example, Testcontainers allocates a random database port; a mock server assigns a port after starting; a test service may create a temporary directory or endpoint. `@DynamicPropertySource` allows registering properties from values supplied at runtime.

```java
@SpringBootTest
@Testcontainers
class CustomerDatabaseIntegrationTest {
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
```

The method annotated with `@DynamicPropertySource` must be `static` and accept a `DynamicPropertyRegistry`. Each `registry.add` registers a supplier; the value is retrieved when the property is accessed. This is useful for endpoints, ports, and credentials provided by test resources.

Dynamic properties have higher precedence than standard property sources such as `@TestPropertySource`, system properties, environment variables, and application-declared property sources. This ensures runtime container details are used when creating the datasource.

If `@DynamicPropertySource` is used in a superclass, subclasses can inherit the same method. When the supplier returns different values across subclasses while configuration is cached and shared, ensure the context is not reused with a stale endpoint. In that case, `@DirtiesContext` on the base class or a test structure with clearly separated contexts may be necessary.

Do not use dynamic properties for values that are actually known and stable. For a fixed feature flag or timeout, inline properties are usually easier to read. Use dynamic properties when the value is only available after resource initialization.

## 5. Inherited Configuration and Context Hierarchy

Spring lets you share test configuration via a superclass or organize contexts into multiple levels.

### 5.1. Inheriting `@ContextConfiguration`

Test configurations can be inherited from a parent class. By default, locations and classes are merged according to annotation inheritance rules. If a subclass needs to replace the parent class's configuration, you can set `inheritLocations = false`.

```java
@SpringJUnitConfig(classes = SharedIntegrationConfig.class)
abstract class BaseIntegrationTest {
}

@ContextConfiguration(classes = CustomerTestConfig.class)
class CustomerRepositoryTest extends BaseIntegrationTest {
}
```

When full control over the subclass configuration is needed:

```java
@ContextConfiguration(
        classes = CustomerTestConfig.class,
        inheritLocations = false)
class IsolatedCustomerTest extends BaseIntegrationTest {
}
```

`@ActiveProfiles` and `@TestPropertySource` also have their own inheritance rules, enabling inheritance by default. The `inheritProfiles`, `inheritLocations`, and `inheritProperties` attributes change how they are combined. Read the exact meaning of each annotation because `inheritLocations` does not control profiles or property sources.

A base test class should hold configuration that is genuinely common and stable. If every subclass has to disable most of the parent class's configuration, the inheritance hierarchy may be making the context hard to understand and reuse.

### 5.2. `@ContextHierarchy` for Parent and Child Contexts

In some applications, especially traditional Spring MVC web applications, you may need a root context containing services/repositories and a child context containing controllers or web configuration. `@ContextHierarchy` describes that structure:

```java
@WebAppConfiguration
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class LegacyWebIntegrationTest {
    @Autowired
    private WebApplicationContext webContext;
}
```

The child context can access beans from the parent context, while the parent does not depend on the child. Separating levels simulates how traditional web applications initialize root and servlet contexts.

You do not need a hierarchy for every Spring Boot application. If only a single application context is needed, `@SpringBootTest` or a slice test is usually simpler. A hierarchy is suitable when a multi-context structure is an architectural aspect you need to verify.

## 6. How Does Spring Cache `ApplicationContext`?

Initializing an `ApplicationContext` can be expensive because Spring must scan components, create beans, configure datasources, start servers, or connect to resources. The TestContext Framework maintains a shared context cache within the same JVM so tests with equivalent configuration do not have to reboot.

The cache key is built from the merged configuration. Key components participating in the key include:

- Resource locations and configuration classes.
- Context initializer classes.
- Context customizers, including test-supplied configurations and dynamic properties.
- Context loader.
- Parent context if using a hierarchy.
- Active profiles.
- Property source descriptors and inline property values.
- Resource base path of the web context.

Two test classes with the same merged configuration can receive the same context from the cache. Differing by even a single profile, property, configuration class, or customizer can produce a different cache key and result in a new context.

The cache is shared within the same process/JVM of the test suite. It does not automatically share contexts across two different Gradle forked processes or across two independent CI runs.

### 6.1. Why Does a Suite Have Too Many Contexts?

Suppose ten test classes all use `@SpringBootTest`, but each class declares a different inline property:

```java
@SpringBootTest(properties = "feature.a.enabled=true")
class FeatureATest {
}

@SpringBootTest(properties = "feature.b.enabled=true")
class FeatureBTest {
}
```

Different configurations can produce different cache keys. If each class also uses different profiles or mock beans, the number of contexts grows further. Creating new contexts repeatedly is often the reason an integration suite is slow.

Group configurations that are genuinely identical into a shared configuration. If two test groups need different values, determine whether they actually need separate contexts or can vary input data at the test method level. Do not merge configurations just to get a cache hit if doing so compromises test independence.

### 6.2. Cache Limits and LRU Policy

The context cache has a size limit. By default, the cache holds at most 32 contexts; when the limit is exceeded, the least-recently-used (LRU) context can be evicted and closed.

You can adjust the size using a system property:

```text
-Dspring.test.context.cache.maxSize=64
```

Consider increasing the limit only after understanding why the suite needs many contexts. Increasing the cache can reduce restarts but also keeps more beans, connection pools, and resources in memory. If cache misses come from accidentally differing configurations, fixing the configuration is usually more effective than raising the limit.

### 6.3. Viewing Cache Statistics

To find out why a suite creates many contexts, enable DEBUG logging for the cache:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Statistics logs can show hit counts, miss counts, and the number of contexts currently in the cache. If misses grow roughly with the number of test classes, compare their configuration annotations, profiles, properties, imports, and mock beans.

A reused context does not mean all state inside it is reset. Spring singleton beans remain alive for the entire context lifecycle. The cache only manages context reuse, not test data isolation.

## 7. Managing Contexts with `@DirtiesContext`

`@DirtiesContext` marks the current context as no longer safe to reuse. Spring removes the corresponding context from the cache and closes it; the next test requiring that configuration will create a new context.

Example used after a test alters singleton bean state or context configuration in an unrecoverable way:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MutableApplicationConfigurationTest {
    // Test mutates ApplicationContext-level state.
}
```

Common class-level modes:

| `ClassMode` | When the context is marked dirty |
|---|---|
| `BEFORE_CLASS` | Before running test methods in the class |
| `AFTER_CLASS` | After completing the class; this is the default |

At the method level, you can choose:

| `MethodMode` | When the context is marked dirty |
|---|---|
| `BEFORE_METHOD` | Before the test method |
| `AFTER_METHOD` | After the test method; this is the default |

In addition, `@DirtiesContext` can apply to a hierarchy using `HierarchyMode` values, determining whether to evict only the current context or also related contexts in the hierarchy.

### 7.1. When Is `@DirtiesContext` Needed?

This annotation is appropriate when a test modifies the state of the context itself and cannot reliably restore it, such as:

- Modifying a singleton bean or context-level registry that other tests cannot reset.
- Changing runtime context configuration in a way that affects other beans.
- Testing a special scenario that leaves the context unusable after execution.

Do not use `@DirtiesContext` as a way to clean up all test data. If a test only creates database records, use transaction rollback or data cleanup. If a test creates files, delete the files. If a test sends messages, use dedicated queues/topics or clean up messages. Closing an entire context to resolve small-scoped state usually makes the suite slow and hard to scale.

`@DirtiesContext` also does not guarantee clearing data in systems external to the context. Databases, containers, files, and brokers may still retain data after the context is closed.

### 7.2. Be Careful When Using with Parallel Tests

If one test marks a context dirty while another test is using the same context, closing the context can cause unpredictable errors. With parallel execution, avoid having concurrent tests share a context that one test may evict. You can group them onto the same thread, use appropriate resource locks, or design a separate context for tests that mutate state.

## 8. Isolating Data and State in Integration Tests

The context cache and test instance lifecycle do not automatically clean up everything. A cached `ApplicationContext` can contain singleton beans shared across multiple tests. Therefore, data must be managed according to its proper scope.

### 8.1. Test Transactions with a Database

Spring Test supports test-managed transactions via `@Transactional`:

```java
@SpringBootTest
@Transactional
class CustomerServiceIntegrationTest {
    @Autowired
    private CustomerService customers;

    @Autowired
    private CustomerRepository repository;

    @Test
    void createsCustomerInsideTestTransaction() {
        customers.create("Lan");

        assertThat(repository.findByName("Lan")).isPresent();
    }
}
```

By default configuration, the test transaction is rolled back after each method. This prevents database data from persisting across test methods within the same transaction manager.

However, rollback does not apply to all side effects. Sent emails, messages received by a broker, written files, or processed HTTP requests may not be rolled back along with the database transaction. For those side effects, use fakes, test containers, dedicated queues, or corresponding cleanup.

### 8.2. Requests via a Real Server Have Separate Transactions

With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, the test method and the HTTP request run on different threads. The test's `@Transactional` transaction does not automatically surround the transaction inside the server request. If the endpoint writes data, delete the data after the test or use fixtures with unique identifiers and explicit cleanup.

### 8.3. Avoid Storing Mutable State in Singleton Beans Unnecessarily

Spring beans default to singleton scope. A bean holding a list, counter, or request data in a field can cause tests to interfere with each other when the context is cached. If state belongs to a single call, keep it in a local variable or model it with an appropriate scope. If state is part of the application, provide meaningful management and reset APIs instead of relying on creating a new context.

## 9. Common Context Loading Errors and How to Handle Them

When a context fails to start, the stack trace often has multiple layers of `BeanCreationException` or `ApplicationContext` failures. Find the root cause in the deepest `Caused by` entries and cross-check with the test configuration.

### 9.1. Spring Boot Configuration Not Found

Common message:

```text
Unable to find a @SpringBootConfiguration
```

Possible causes are that the test lies outside the package tree of the `@SpringBootApplication` class, there are multiple application configurations, or the test module does not properly depend on the module containing the main class.

How to resolve:

- Specify `@SpringBootTest(classes = MainApplication.class)` when needing to load a specific application.
- Check the package and dependencies of the test module.
- For plain Spring tests, use `@ContextConfiguration(classes = ...)` instead of asking Boot to locate a main application.

### 9.2. Cannot Create Bean or Missing Dependency

A `NoSuchBeanDefinitionException` usually indicates that the context does not contain a bean required by the test or another bean. In a test slice, a service not being loaded can be normal behavior.

Determine whether the test is using a full context or a slice. For a slice, import the needed configuration or mock the controller/service's collaborators. For a full context, check component scanning, `@ConditionalOn...` conditions, profiles, and bean configuration.

Do not solve every error by switching to `@SpringBootTest`. If a test is verifying a controller, adding the proper mock dependency to `@WebMvcTest` usually keeps a more appropriate scope.

### 9.3. Property Placeholder Could Not Be Resolved

Example error:

```text
Could not resolve placeholder 'external.api.url'
```

Check whether the key exists in the loaded configuration files, whether the profile is activated, and whether the test needs to provide an inline property or dynamic property.

```java
@SpringBootTest(properties = "external.api.url=http://localhost:8089")
class ExternalClientIntegrationTest {
}
```

If the URL is provided by a mock server, register it via `@DynamicPropertySource` to capture the port after the server starts.

### 9.4. Multiple Beans of the Same Type or Wrong Implementation Selected

When there are multiple beans of the same type, Spring may report `NoUniqueBeanDefinitionException` or select a different implementation than intended. Use `@Qualifier`, `@Primary`, or explicit test bean configuration. Also check profiles and bean creation conditions to see why that implementation appeared.

### 9.5. Database Connection or Migration Failure

The context may fail to start because of a wrong datasource URL, an unready container, incorrect credentials, or a migration error. Check the actual datasource properties, container status, and migration logs. If the test needs a real database, use Testcontainers or a managed test service instead of relying on a local database not declared in the build.

### 9.6. Context Previously Failed

In Spring Framework 6.1 and later, the TestContext Framework has a failure threshold mechanism for the same context cache key. By default, after one context load failure, subsequent attempts with the same key may be skipped and report an error stating that the failure threshold was exceeded. This can be adjusted using the `spring.test.context.failure.threshold` system property.

When you see the threshold message, look for the first load error in the logs. Subsequent skip errors are usually a consequence of the initial failure, not independent causes. Do not raise the threshold to mask root configuration errors.

## 10. Keeping the Context Cache Effective

Several choices help reduce the number of context startups:

- Share configuration among tests that truly have the same profile, properties, and bean graph.
- Avoid creating different inline properties across classes if values can be controlled at the test method level.
- Do not import a new configuration for every class unless there is a specific need.
- Limit replacing beans with different sets of mocks if tests can verify collaborators via unit tests or separate slices.
- Use `@DirtiesContext` only when the context genuinely needs to be evicted from the cache.
- Enable cache logging when the suite is slow to observe hits/misses instead of guessing.

Do not force all tests to share one context. Tests that require different profiles, properties, servers, or bean graphs may need separate contexts. The goal is to reuse equivalent contexts and keep each test's scope clear.

## 11. Organizing Base Integration Tests

A base class can group genuinely shared configuration:

```java
@SpringBootTest
@ActiveProfiles("integration")
abstract class BaseIntegrationTest {
    @Autowired
    protected TestEntityManager entityManager;
}
```

Subclasses reuse the configuration:

```java
class CustomerServiceIT extends BaseIntegrationTest {
    @Autowired
    private CustomerService customers;
}

class OrderServiceIT extends BaseIntegrationTest {
    @Autowired
    private OrderService orders;
}
```

If subclasses have the same merged configuration, Spring can reuse the context. Keep the base class focused on shared configuration and utilities. Avoid putting too much data setup into the base class's `@BeforeEach` because every subclass will receive unnecessary fixtures.

If a group of tests needs different profiles or properties, declare them explicitly on that group and accept a different context key when behavior genuinely differs. Use inheritance only when the configuration relationship makes sense; composition via `@Import` or test configuration can be clearer if tests only share a few beans.

## 12. Process for Diagnosing a Slow or Non-Starting Integration Test

When a test encounters context issues, proceed in order:

1. Identify the test type: full application context, plain Spring context, or test slice.
2. Locate the root configuration: `classes`, `locations`, main application, profiles, and initializers.
3. Inspect properties: loaded files, inline properties, dynamic properties, and runtime sources.
4. Read the root cause in the stack trace, especially bean creation, placeholders, datasource, and migrations.
5. If the context loads successfully but the suite is slow, enable DEBUG logging on `org.springframework.test.context.cache` to check cache hits/misses.
6. Look for `@DirtiesContext`, differing configurations across test classes, and customizers that alter the cache key.
7. Check whether singleton state, transactions, database, or resources outside the context are being shared.
8. Only increase cache size or split contexts after clearly identifying the need and cost.

This process helps distinguish configuration errors, dependency errors, external resource errors, and context reuse issues. These causes have different fixes; addressing the right scope keeps the suite stable without having to expand every test into a full application context.

## 13. Annotation Selection Table by Goal

| Goal | Typically Suitable Annotation/Mechanism | Loaded Scope |
|---|---|---|
| Load a specific set of Spring beans | `@ContextConfiguration`, `@SpringJUnitConfig` | The specified classes or resources |
| Load a Spring Boot application | `@SpringBootTest` | Application context per Boot configuration |
| Test MVC with mock services | `@WebMvcTest` | Web slice |
| Test JPA repositories | `@DataJpaTest` | Persistence slice |
| Add test-specific beans | `@TestConfiguration`, `@Import` | Additional test configuration |
| Select environment-specific configuration | `@ActiveProfiles` | Corresponding profiles |
| Load properties from file or inline | `@TestPropertySource`, `@SpringBootTest(properties = ...)` | Test property source |
| Use runtime-assigned URLs/ports | `@DynamicPropertySource` | Properties retrieved from runtime suppliers |
| Build root/child contexts | `@ContextHierarchy` | Multiple levels of `ApplicationContext` |
| Evict context from cache | `@DirtiesContext` | Context marked as non-reusable |

## 14. Principles to Remember

- Choose `@ContextConfiguration`, `@SpringBootTest`, or a test slice matching the exact scope to be tested.
- Specify `classes` when Spring Boot cannot find the right application configuration or when the test needs a specific configuration.
- Use profiles and property sources purposefully; use `@DynamicPropertySource` for values only available after test resources are initialized.
- The context cache reuses contexts with the same merged configuration within the same JVM; changing profiles, properties, initializers, or customizers can create a new cache key.
- Use `@DirtiesContext` when the state of the context itself cannot be restored; manage databases, files, and brokers with their own mechanisms.
- A new test instance does not mean a new Spring context; singleton beans in a cached context may be shared by multiple tests.
- Transaction rollback helps isolate database data within the same transaction, but does not undo emails, messages, or externally sent requests.
- When context loading fails, find the first root cause; when the suite is slow, observe cache hits/misses and the actual number of contexts created.

Understanding how to load configuration and manage the `ApplicationContext` lifecycle helps integration tests verify the exact Spring components needed while reusing resources efficiently. Each test class should clearly express the configuration, profiles, and properties it needs; data and side effects should be isolated along proper boundaries; and contexts should only be recreated for a specific reason.
