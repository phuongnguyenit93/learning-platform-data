# SpringExtension with JUnit Jupiter

SpringExtension is the bridge between **JUnit Jupiter** and the **Spring TestContext Framework**. When a test needs Spring to manage the ApplicationContext, inject dependencies into the test instance, apply test transactions, or execute TestContext callbacks, SpringExtension brings those capabilities into the JUnit Jupiter test lifecycle.

JUnit Jupiter provides an extension model instead of JUnit 4's runner model. Accordingly, how Spring is integrated also changes:

- With JUnit 4, `@RunWith(SpringRunner.class)` is typically used.
- With JUnit Jupiter (JUnit 5), use `@ExtendWith(SpringExtension.class)`, or a composed annotation that already registers this extension such as `@SpringJUnitConfig` or Spring Boot's test annotations.

SpringExtension is not a Spring container, nor does it automatically turn every test into an integration test. It connects JUnit's extension points to TestContextManager. The test still needs to declare how to create the ApplicationContext and choose the proper testing scope.

## 1. JUnit Jupiter and the Extension Model

JUnit Jupiter is the programming model of JUnit 5. A test class uses annotations such as:

- @Test to declare a test method.
- @BeforeEach and @AfterEach for setup and teardown around each test.
- @BeforeAll and @AfterAll to run tasks before/after the entire test class.
- @Nested to group related tests.
- @ParameterizedTest to run the same test with multiple data sets.
- @Tag to categorize tests.

JUnit Jupiter extends the test lifecycle through the **Extension** mechanism. An extension can participate at moments such as test instance creation, before/after each test, before/after the test class, exception handling, or resolving method parameters.

SpringExtension implements the appropriate extension points so the Spring TestContext Framework can coordinate with JUnit Jupiter. Thus, tests can use Spring Test capabilities without needing a JUnit 4 Runner.

Minimal example:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class MySpringTest {

    @Autowired
    private MyService myService;

    @Test
    void performsExpectedBehavior() {
        assertNotNull(myService);
    }
}
~~~

The two annotations have distinct responsibilities:

- @ExtendWith(SpringExtension.class) registers SpringExtension with JUnit Jupiter.
- @ContextConfiguration declares the configuration used to create the ApplicationContext for the test.

Merely registering the extension without suitable context configuration does not specify which beans the test needs. Spring Test has a default configuration lookup mechanism in some cases, yet explicit tests should declare configuration or use the corresponding composed annotation.

## 2. How Does SpringExtension Connect to the TestContext Framework?

SpringExtension does not rewrite the JUnit lifecycle. It receives callbacks from JUnit Jupiter and forwards them to **TestContextManager**.

TestContextManager manages the TestContext for the test class. TestContext holds information about the test, the ApplicationContext, and the listeners participating in execution. TestExecutionListeners provide behaviors such as injecting dependencies into the test instance, managing test transactions, handling `@DirtiesContext`, and executing SQL scripts as configured.

You can visualize the relationship as follows:

~~~mermaid
flowchart TD
    J["JUnit Jupiter Engine"] --> E["SpringExtension"]
    E --> M["TestContextManager"]
    M --> T["TestContext"]
    T --> C["ApplicationContext"]
    M --> L["TestExecutionListeners"]
    L --> DI["Dependency injection"]
    L --> TX["Test-managed transactions"]
    L --> SQL["SQL scripts / lifecycle support"]
    C --> B["Spring beans"]
~~~

Main callbacks forwarded along the lifecycle:

| JUnit Jupiter extension point | Spring TestContext operation |
|---|---|
| BeforeAllCallback | beforeTestClass |
| TestInstancePostProcessor | prepareTestInstance |
| BeforeEachCallback | beforeTestMethod |
| BeforeTestExecutionCallback | beforeTestExecution |
| AfterTestExecutionCallback | afterTestExecution |
| AfterEachCallback | afterTestMethod |
| AfterAllCallback | afterTestClass |
| ParameterResolver | Resolves parameters from ApplicationContext when supported by Spring |

This division explains why certain behaviors happen before `@BeforeEach`, while others occur right around the test method invocation.

### Sequence Around a Test Method

For a test class using SpringExtension, the general sequence is:

1. JUnit creates the test instance according to the configured lifecycle.
2. SpringExtension receives the instance via TestInstancePostProcessor and asks TestContext to prepare the instance, including dependency injection.
3. Pre-test-method callbacks execute.
4. JUnit runs `@BeforeEach`.
5. SpringExtension receives the `beforeTestExecution` callback.
6. JUnit executes the test method.
7. SpringExtension receives the `afterTestExecution` callback.
8. JUnit runs `@AfterEach`.
9. SpringExtension receives the `afterEach` callback to finish test method processing in TestContext.

At the test class level, `beforeAll`/`afterAll` callbacks correspond to `beforeTestClass`/`afterTestClass` on TestContext.

This order explains an important point: dependency injection into test instance fields runs before `@BeforeEach` executes, so the test can use injected beans inside setup methods.

This is a high-level description of the lifecycle. When multiple extensions participate together, callback order also depends on how JUnit registers extensions and each extension's ordering rules.

## 3. Registering SpringExtension Directly

The most explicit approach is combining `@ExtendWith` and `@ContextConfiguration`:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = GreetingTestConfig.class)
class GreetingServiceTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void createsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }
}
~~~

Test configuration can be a small Java configuration:

~~~java
@Configuration
class GreetingTestConfig {

    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }
}
~~~

And the component under test:

~~~java
public class GreetingService {

    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

When the test runs:

- JUnit Jupiter discovers the test class and registers SpringExtension.
- Spring TestContext uses GreetingTestConfig to create the ApplicationContext.
- SpringExtension asks TestContext to prepare the test instance.
- The GreetingService bean is injected into the field.
- The test method calls the bean and verifies the result.

This example illustrates integrating the extension and dependency injection. If you only want to test string concatenation in GreetingService, you can instantiate the object directly without Spring. Using a context here demonstrates the wiring mechanism; in real applications, choose a context when configuration or Spring behavior is part of what needs to be verified.

## 4. Using @SpringJUnitConfig for Concise Configuration

Spring provides the **@SpringJUnitConfig** composed annotation for JUnit Jupiter. This annotation combines:

- @ExtendWith(SpringExtension.class)
- @ContextConfiguration

Thus, instead of writing two separate annotations, you can declare:

~~~java
@SpringJUnitConfig(GreetingTestConfig.class)
class GreetingServiceTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void createsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }
}
~~~

`@SpringJUnitConfig` can accept `classes` or `locations` just like context configuration. When you also need to specify an initializer or loader, you can use the corresponding `@ContextConfiguration` attributes through the composed annotation.

Comparison table:

| Declaration Style | Role |
|---|---|
| @ExtendWith(SpringExtension.class) + @ContextConfiguration | Registers the extension and declares the context separately |
| @SpringJUnitConfig | Composed shorthand for the two annotations above |
| @SpringJUnitWebConfig | Composed shorthand for contexts with web configuration |
| @SpringBootTest | Initializes a Spring Boot test context; this annotation already integrates SpringExtension |

If a test needs to verify a standard Spring Framework context, `@SpringJUnitConfig` is a readable choice. If a test needs Spring Boot bootstrapping, use the appropriate Boot annotation.

## 5. Dependency Injection into Test Classes

SpringExtension collaborates with TestContext to prepare the test instance. Thanks to this, tests can receive beans via fields, setters, or other injection styles supported by Spring Test.

### Field Injection

~~~java
@SpringJUnitConfig(TestConfig.class)
class AccountServiceTest {

    @Autowired
    private AccountService accountService;

    @Test
    void loadsAccount() {
        Account account = accountService.find("ACC-01");

        assertEquals("ACC-01", account.id());
    }
}
~~~

Field injection is usually concise and familiar in tests. However, fields are not initialized until Spring prepares the test instance. Do not access that field inside another field initializer expression of the test class.

### Setter or Method Injection

Spring Test also supports injection into methods annotated with `@Autowired`. This is useful when a test needs to prepare some dependencies via a method, though setup should be kept simple so the test remains easy to follow.

~~~java
@SpringJUnitConfig(TestConfig.class)
class ReportServiceTest {

    private ReportService reportService;

    @Autowired
    void setReportService(ReportService reportService) {
        this.reportService = reportService;
    }

    @Test
    void generatesReport() {
        assertNotNull(reportService.generate());
    }
}
~~~

In most cases, field injection or constructor injection is clear enough. Avoid mixing multiple injection styles in the same test class without a specific reason.

### Constructor Injection for Test Instances

JUnit Jupiter allows test classes to have custom constructors. Spring Test provides `@TestConstructor` to indicate that constructor parameters should be autowired from the ApplicationContext.

~~~java
@SpringJUnitConfig(TestConfig.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class AccountServiceConstructorTest {

    private final AccountService accountService;

    AccountServiceConstructorTest(AccountService accountService) {
        this.accountService = accountService;
    }

    @Test
    void loadsAccount() {
        assertNotNull(accountService);
    }
}
~~~

You can configure the default constructor autowire mode across the entire test suite with the property:

~~~properties
spring.test.constructor.autowire.mode=all
~~~

This global configuration changes how Spring handles test class constructors. Enable it only when the development team wants to apply it consistently and understands the impact on tests with constructor parameters meant for other JUnit extensions.

Constructor injection makes the test's dependencies explicit right at the class declaration. In return, the test class needs appropriate constructor autowiring configuration. If you prefer not to alter constructor mode, field injection or setter injection can be simpler.

## 6. Injecting Beans into Test Method Parameters

SpringExtension also implements `ParameterResolver`. Consequently, JUnit Jupiter can ask the extension to supply parameters managed by Spring.

Example:

~~~java
@SpringJUnitConfig(TestConfig.class)
class AccountServiceParameterTest {

    @Test
    void loadsAccount(AccountService accountService) {
        Account account = accountService.find("ACC-01");

        assertEquals("ACC-01", account.id());
    }
}
~~~

SpringExtension resolves parameters from the ApplicationContext when the parameter falls within its supported scope. This lets a method declare only the dependencies it uses without storing them as fields.

Parameters can also be used in JUnit Jupiter lifecycle methods when the extension supports them and parameters resolve appropriately:

~~~java
@BeforeEach
void prepareTestData(AccountRepository repository) {
    repository.deleteAll();
}
~~~

Note that deleting data through a repository is a real side effect against the running context. Use such setup only when the test requires a database and has a proper data isolation strategy.

### When Multiple ParameterResolvers Participate

JUnit Jupiter can register multiple extensions that implement `ParameterResolver`. For example, MockitoExtension can supply `@Mock` parameters, while SpringExtension can supply beans from the ApplicationContext.

If multiple resolvers claim the same parameter, JUnit may fail because it cannot determine the right resolver. Use clear annotations and parameter types, and avoid declaring the same dependency with two competing resolution mechanisms.

For mocks that need to replace beans inside the Spring context, choose a bean override mechanism compatible with the Spring version in use. For mocks serving only a pure unit test, you can use MockitoExtension without SpringExtension.

## 7. Combining SpringExtension with Spring Boot Test

In Spring Boot applications, specialized test annotations usually register SpringExtension via their meta-annotations. For example:

- @SpringBootTest
- @WebMvcTest
- @DataJpaTest
- @JsonTest
- Other Spring Boot test slices

Therefore, there is no need to add `@ExtendWith(SpringExtension.class)` again when using the corresponding Boot annotation.

Example testing the application context:

~~~java
@SpringBootTest
class ApplicationContextTest {

    @Autowired
    private ApplicationService applicationService;

    @Test
    void loadsApplicationService() {
        assertNotNull(applicationService);
    }
}
~~~

Example testing an MVC slice:

~~~java
@WebMvcTest(AccountController.class)
class AccountControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsAccountEndpointResponse() throws Exception {
        mockMvc.perform(get("/accounts/ACC-01"))
                .andExpect(status().isOk());
    }
}
~~~

In a real MVC test, the controller typically needs service dependencies. The test must provide suitable mocks or replacement beans so the slice context can start. The example above focuses on registering SpringExtension via the test annotation and using MockMvc; it does not show complete configuration for every controller.

If you use `@SpringBootTest`, the context can be broader and initialize many auto-configurations. Choose `@WebMvcTest`, `@DataJpaTest`, or another slice when only testing a portion of the system. SpringExtension supports the lifecycle for those context types; the bootstrapper annotation determines which context is created.

## 8. Configuring Profiles and Properties for the Test Context

SpringExtension works with the bootstrapped TestContext. Tests can declare profiles or properties to configure the context before beans are created.

Example using profiles:

~~~java
@SpringJUnitConfig(TestConfig.class)
@ActiveProfiles("test")
class ProfileAwareServiceTest {

    @Autowired
    private StorageService storageService;

    @Test
    void usesTestStorageImplementation() {
        assertEquals("in-memory", storageService.type());
    }
}
~~~

Example supplying inline properties:

~~~java
@SpringJUnitConfig(TestConfig.class)
@TestPropertySource(properties = {
        "feature.checkout.enabled=true",
        "service.region=test-region"
})
class CheckoutConfigurationTest {

    @Autowired
    private CheckoutFeature checkoutFeature;

    @Test
    void enablesCheckout() {
        assertTrue(checkoutFeature.isEnabled());
    }
}
~~~

These annotations affect context creation. This differs from passing a `MockEnvironment` directly into an object: in a test context, properties participate in Spring's configuration process and can affect `@Value`, `@Profile`, `@Conditional`, and other beans.

When dynamic properties supplied after initializing test resources are needed, Spring supports `@DynamicPropertySource` with a static method registering properties via `DynamicPropertyRegistry`. This pattern is common when using Testcontainers to obtain runtime-assigned hosts/ports. When testing that behavior, the test must use an appropriate test context.

## 9. TestContext Listeners and Spring Testing Utilities

SpringExtension is the integration point with JUnit Jupiter; many Spring testing behaviors are carried out by `TestExecutionListener` instances in the TestContext Framework.

Some examples:

### Dependency Injection

`DependencyInjectionTestExecutionListener` prepares the test instance and injects Spring-managed dependencies. As a result, `@Autowired` fields in the test are populated before the test method runs.

### Test Transactions

`TransactionalTestExecutionListener` coordinates with the `@Transactional` annotation to create a test-managed transaction when configuration supports it. By common default, the transaction is rolled back after the test so data does not persist long-term.

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class AccountRepositoryTest {

    @Autowired
    private AccountRepository repository;

    @Test
    void savesAccount() {
        repository.save(new Account("ACC-01"));

        assertTrue(repository.findById("ACC-01").isPresent());
    }
}
~~~

Rollback does not mean all side effects are undone. Messages sent to a broker, outgoing HTTP requests, or dispatched emails are not automatically retracted just because the database transaction rolled back. Isolate or replace external dependencies when testing.

### SQL Scripts

With appropriate configuration, `@Sql` can execute scripts before or after a test method to prepare or clean up data:

~~~java
@Test
@Sql("/sql/accounts-test-data.sql")
void findsAccountFromScript() {
    assertTrue(repository.findById("ACC-01").isPresent());
}
~~~

Scripts must reside on the test classpath and match the database in use. This is a utility for tests involving persistence, not a requirement for pure unit tests.

### Refreshing ApplicationContext

`@DirtiesContext` marks the context as altered or no longer safe to reuse. TestContext removes that context from the cache and closes the corresponding context according to the lifecycle.

Do not attach `@DirtiesContext` to every test. Refreshing the context can take significant time. Use it only when a test genuinely alters context state in a way that affects other tests.

Listeners can be extended or customized. However, before adding a custom listener, identify which callback is missing and whether existing Spring Test extension points already satisfy the requirement.

## 10. Test Instance Lifecycle and ApplicationContext Cache

JUnit Jupiter creates a new test instance for each test method by default (`PER_METHOD`). SpringExtension prepares each such instance, but the `ApplicationContext` may be reused across multiple test classes with compatible configurations.

This means:

- Test instances are generally independent across methods under the default lifecycle.
- ApplicationContext is not necessarily recreated for each method.
- Singleton beans in the context can be shared across multiple tests.
- Mutating state in a singleton bean can affect tests running later.
- `@DirtiesContext` can cause a context to be evicted from the cache when a test has modified context state.

Therefore, do not assume each test method receives a fresh set of singleton beans. If a bean holds state, tests must reset state or use appropriate fixtures/configuration. Database data also needs isolation via transactions, cleanup, or separate namespaces.

The Spring TestContext Framework caches `ApplicationContext` instances to reduce startup time. Caching relies on the context configuration; tests using the same configuration can share a context. Changing profiles, properties, initializers, or bean definitions can require a different cache entry.

Cache optimization should never become a reason for tests to depend on execution order. Tests must be able to run individually and in different orders while still yielding reliable results.

## 11. Coordinating with Other JUnit Extensions

JUnit Jupiter allows registering multiple extensions. SpringExtension can coexist with other extensions such as MockitoExtension, data management extensions, or project-authored extensions.

Example registering two extensions:

~~~java
@ExtendWith({
        SpringExtension.class,
        MockitoExtension.class
})
@ContextConfiguration(classes = TestConfig.class)
class CombinedExtensionTest {

    @Mock
    private PaymentGateway paymentGateway;

    @Autowired
    private PaymentService paymentService;

    @Test
    void handlesGatewayResult() {
        when(paymentGateway.charge(any()))
                .thenReturn(PaymentResult.approved());

        PaymentResult result =
                paymentService.pay(new PaymentCommand("ORDER-01"));

        assertTrue(result.approved());
    }
}
~~~

This example only illustrates registering extensions and using mocks. In a real Spring context, `PaymentService` has usually already been created with a `PaymentGateway` bean. A `@Mock` field created by MockitoExtension does not automatically replace that bean inside the ApplicationContext. To make the service in the context use a mock, register a mock/override bean using the mechanism appropriate for your Spring version or test configuration.

This is a common mistake: having a `@Mock` field in the test class, while the bean injected into the service remains the real implementation. The two objects belong to two different management mechanisms.

When combining extensions, distinguish between:

- Mock objects created by MockitoExtension for the test instance.
- Beans managed by the Spring ApplicationContext.
- Bean overrides registered in the context.
- Dependencies supplied by a JUnit `ParameterResolver` for method parameters.

Do not assume a `@Mock` field automatically replaces a bean in Spring. When testing a pure service, constructing the service directly with mocks is simplest. When testing context wiring with a replacement bean, use bean overrides or test configuration.

## 12. SpringExtension Is Not SpringRunner

The two class names are easily confused:

| Component | Framework | Registration |
|---|---|---|
| SpringRunner | JUnit 4 | @RunWith(SpringRunner.class) |
| SpringExtension | JUnit Jupiter | @ExtendWith(SpringExtension.class) |

The JUnit 4 Runner extends the lifecycle via a runner model. JUnit Jupiter uses an extension model, allowing multiple extensions to participate on one test class.

Do not use `@RunWith(SpringRunner.class)` on test classes executed by the Jupiter Engine. If a project still has JUnit 4 tests, they require the JUnit Vintage Engine and matching setup; Jupiter tests should use SpringExtension.

In a project migrating from JUnit 4 to JUnit Jupiter, check annotation imports. `org.junit.jupiter.api.Test` differs from `org.junit.Test`. A test class using annotations from an incompatible engine may not be discovered or run as expected.

## 13. Common Errors and How to Handle Them

### Missing ApplicationContext or Bean Not Found

The cause is usually that the test has not declared context configuration, configuration lacks component scanning/bean registration, or the wrong bootstrapper annotation is used.

Check `@ContextConfiguration`, `@SpringJUnitConfig`, `@SpringBootTest`, or the test slice in use. Read context startup errors and verify the required bean is present in the configuration.

### Using @ExtendWith Without Context Configuration

SpringExtension registers the integration point, yet the test still needs a configuration source. Add `@ContextConfiguration` or use `@SpringJUnitConfig`. With Spring Boot, choose the appropriate Boot annotation.

### Using JUnit 4 Annotations in a Jupiter Test

Check imports for `@Test`, `@RunWith`, and `@ExtendWith`. A JUnit 4 runner does not replace the JUnit Jupiter extension. Choose the matching engine and annotations for the test class.

### Test Constructor Not Autowired

If a constructor has bean parameters but Spring is not configured to autowire constructors, JUnit may fail to find a suitable `ParameterResolver`. Use `@TestConstructor(autowireMode = ALL)` or configure the `spring.test.constructor.autowire.mode=all` property per suite policy.

### ParameterResolutionException

This error can occur when no resolver supports a parameter or multiple resolvers claim the same parameter. Check the parameter's type and annotations, registered extensions, and constructor configuration. For mock parameters, ensure MockitoExtension or the right mock mechanism is registered.

### Mock in Test Is Not Used by the Service

A `@Mock` field does not automatically replace a bean in the ApplicationContext. Construct the service directly with mocks for unit tests, or register a bean override in the test context.

### Tests Depend on Order or Singleton State

Contexts may be cached and singleton beans can live across multiple tests. Reset state, create independent data, or use `@DirtiesContext` when the context genuinely must be evicted from the cache.

### Slow Tests Due to Overly Broad Context Startup

If you only need a controller, repository, or converter, consider the corresponding test slice. If only testing business logic, no Spring context is needed. Choosing a smaller context scope reduces cost and makes failures easier to isolate.

## 14. Process for Choosing How to Integrate Spring with JUnit Jupiter

Before writing a test, determine what needs to be proven by Spring:

1. If the test only verifies Java logic and dependencies can be passed directly, use plain JUnit Jupiter.
2. If you need bean injection or to verify Spring Framework configuration, use `@SpringJUnitConfig` or `@ExtendWith(SpringExtension.class)` paired with `@ContextConfiguration`.
3. If you need to verify Spring Boot auto-configuration or the application context, use `@SpringBootTest` or `ApplicationContextRunner` depending on scope.
4. If you only need a slice such as MVC, JPA, or JSON, use the corresponding test slice annotation.
5. If you need test transactions, SQL setup, or context lifecycle hooks, leverage TestContext listeners and appropriate Spring annotations.
6. If you need to mock a bean in the context, register a bean override explicitly; do not assume a `@Mock` field replaces the bean automatically.
7. If multiple extensions resolve parameters, check annotations and parameter support to avoid conflicts.

SpringExtension enables JUnit Jupiter to use full Spring TestContext integration: preparing test instances, dependency injection, lifecycle callbacks, parameter resolution, and test-supporting listeners. When combined with the right bootstrapper annotation and context scope, tests can verify Spring-managed behavior while keeping a clean JUnit Jupiter structure.

Treat SpringExtension as the lifecycle bridge between the two frameworks. JUnit Jupiter drives tests and extension points; Spring TestContext manages contexts and listeners; Spring ApplicationContext provides beans. Understanding each part's role helps you choose the right annotation, avoid unnecessary context startups, and know precisely what a test proves.

