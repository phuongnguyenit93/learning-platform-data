# Distinguishing Missing Bean Errors from Assertion Failures

When a Spring test fails, you need to determine at which stage it failed. A missing bean error typically occurs when Spring creates the `ApplicationContext` or injects dependencies for the test and a requested bean cannot be found. An assertion failure occurs after the test method has executed up to a verification statement, yet the actual value does not match the expected outcome.

Both types of errors can appear in the same project, or even the same test class, but their causes and fixes are different. Mistaking a context initialization error for a business logic failure can lead you to tweak assertions while the test has never actually run. Conversely, treating every test failure as a bean configuration error can cause you to overlook a genuine bug in application behavior.

## 1. Looking at the lifecycle of a Spring test

A Spring integration test typically goes through the following stages:

```text
Build and test discovery
          |
          v
Create / retrieve ApplicationContext from cache
          |
          v
Create test instance and inject dependencies
          |
          v
Run lifecycle callbacks (@BeforeEach, ...)
          |
          v
Run test method
          |
          v
Execute assertions
          |
          v
Completion and cleanup callbacks
```

Missing bean errors usually occur during context creation or dependency injection—that is, before the test method body executes assertions. Assertion failures occur during result verification after the action has been invoked.

Not every failure before an assertion is a missing bean error. For example, a test not being discovered, a missing JUnit extension, a failure inside `@BeforeEach`, a database connection failure, or a failure building a test fixture can also fail the test. Therefore, read the exception type and failure location rather than relying solely on the `Tests failed` summary line.

## 2. What is a missing bean error?

In Spring, dependency injection must locate a bean matching the required type and qualifier. If no bean satisfies those conditions, Spring cannot finish instantiating the object or configuring dependent beans.

For example, a service requiring a repository:

```java
@Service
public class AccountService {

    private final AccountRepository repository;

    public AccountService(AccountRepository repository) {
        this.repository = repository;
    }
}
```

If the `ApplicationContext` lacks an `AccountRepository` bean, Spring cannot instantiate `AccountService`. The test may receive an outer wrapper exception such as `UnsatisfiedDependencyException` or `BeanCreationException`, while the deeper root cause is `NoSuchBeanDefinitionException`.

### 2.1. Common exceptions

| Exception / message | Typical meaning | Where to check |
|---|---|---|
| `NoSuchBeanDefinitionException` | No bean found matching the requested type or name | Component scan, configuration, profile, import, and test slice |
| `UnsatisfiedDependencyException` | Spring could not supply a dependency while creating a bean | Read `Caused by` to find the missing bean or constructor parameter |
| `BeanCreationException` | Bean could not be created | Check deeper cause; may be missing dependency, bad config, or initialization error |
| `NoUniqueBeanDefinitionException` | Multiple matching beans exist when Spring expects a single bean | Use `@Qualifier`, `@Primary`, or inject a collection/provider |
| `BeanDefinitionOverrideException` | Duplicate bean definition name and overriding is disallowed | Check bean registration configuration and bean names |
| `ApplicationContextException` | A problem during context startup or operation | Read nested causes; do not immediately assume a missing bean |

A common message for a missing bean is:

```text
No qualifying bean of type 'com.example.AccountRepository' available
```

Or in the logs, a cause chain may appear:

```text
Failed to load ApplicationContext
  Caused by: UnsatisfiedDependencyException
    Caused by: NoSuchBeanDefinitionException
      No qualifying bean of type 'com.example.AccountRepository' available
```

The outer exception indicates Spring could not create the context or bean. The innermost exception usually reveals which specific dependency was not found. When diagnosing, read the entire `Caused by` chain, starting from the deepest meaningful cause.

### 2.2. Bean not found vs. multiple beans are two different situations

Suppose there are two implementations:

```java
@Component
class SmtpNotificationSender implements NotificationSender {
}

@Component
class InMemoryNotificationSender implements NotificationSender {
}
```

If a service injects `NotificationSender` without a selection rule, Spring can throw `NoUniqueBeanDefinitionException`. This is not a missing bean error; there are more candidates than needed.

You can resolve it with `@Qualifier`:

```java
@Service
class NotificationService {

    private final NotificationSender sender;

    NotificationService(
            @Qualifier("inMemoryNotificationSender") NotificationSender sender) {
        this.sender = sender;
    }
}
```

Or mark a default bean with `@Primary` if that makes sense for the application. When a test needs a specific implementation, declare the desired bean explicitly in the test configuration or use the corresponding qualifier.

## 3. Where do missing bean errors appear in tests?

### 3.1. Missing bean when creating ApplicationContext

With `@SpringJUnitConfig`, `@ContextConfiguration`, or `@SpringBootTest`, Spring must create the `ApplicationContext` before the test method runs. If a required bean cannot be created, the test usually halts during context preparation.

Example:

```java
@SpringJUnitConfig(AccountService.class)
class AccountServiceTest {

    @Autowired
    private AccountService accountService;

    @Test
    void loadsService() {
        assertNotNull(accountService);
    }
}
```

This snippet registers only `AccountService` as the component configuration source. If `AccountService` needs `AccountRepository` and no configuration or component scan supplies the repository, the context may fail to initialize. The `assertNotNull` statement is never executed.

### 3.2. Missing bean in a test slice

Test slices intentionally load only part of the application. For example, `@WebMvcTest(OrderController.class)` focuses on the MVC layer, so business services are not automatically scanned and registered as they are when running the full application.

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderService orderService;
}
```

If `OrderService` is not part of the loaded slice, injecting that field can cause context startup to fail. For controller tests, it is standard practice to provide a mock bean for business dependencies:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;
}
```

`@MockitoBean` is a Spring Framework annotation introduced in version 6.2 to create or replace a bean in the test context with a Mockito mock. With older Spring Boot versions, projects may use Spring Boot Test's `@MockBean`; `@MockBean` was deprecated in Spring Boot 3.4 in favor of Spring Framework's bean override annotations. Use the annotation available and compatible with your project's version.

If a test needs to verify the real service itself, choose an appropriate context scope, such as `@SpringBootTest` or a test configuration importing the service and its required dependencies. Do not pull a real service into an MVC slice merely to satisfy field injection if the test's goal is solely controller behavior.

### 3.3. Missing bean because configuration was not loaded

A bean may exist in source code yet not appear in the test's context. Common causes include:

- The class is not covered by component scanning.
- The configuration class containing `@Bean` was not imported or listed in `@ContextConfiguration`.
- The bean is created only when a profile is active, and the test did not activate that profile.
- `@Conditional`, `@ConditionalOnProperty`, or environment conditions are not met.
- A test slice excludes the configuration or component from scanning.
- The bean is restricted by module, package, or classpath, and a required dependency is absent.
- The test uses the wrong configuration class or wrong application context hierarchy.

Example of a bean active only when the `test` profile is enabled:

```java
@Configuration
@Profile("test")
class TestGatewayConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
```

The test must activate the profile and load the corresponding configuration:

```java
@SpringJUnitConfig(TestGatewayConfiguration.class)
@ActiveProfiles("test")
class PaymentServiceTest {

    @Autowired
    private PaymentGateway paymentGateway;
}
```

If `@ActiveProfiles` is missing or the profile is overridden by test configuration, the bean may not be registered. When diagnosing, check the actual active profiles in `Environment` and the bean registration conditions.

## 4. What is an assertion failure?

An assertion checks whether the actual result matches the contract described by the test. In JUnit Jupiter, methods such as `assertEquals`, `assertTrue`, `assertNotNull`, `assertThrows`, and `assertAll` fail when the expected condition is not met.

Example:

```java
@Test
void calculatesDiscount() {
    PriceCalculator calculator = new PriceCalculator();

    int actual = calculator.discount(100, 10);

    assertEquals(90, actual);
}
```

If the method returns `95`, the test fails with `AssertionFailedError` or the corresponding JUnit assertion error type. This indicates the test method ran, the call executed, and the result did not match expectations.

A report might display:

```text
org.opentest4j.AssertionFailedError:
Expected :90
Actual   :95
    at PriceCalculatorTest.calculatesDiscount(PriceCalculatorTest.java:12)
```

Here, you need to check the discount formula, input data, and expected value. Adding beans to the `ApplicationContext` will not fix a numerical discrepancy in pure Java calculation logic.

## 5. Distinguishing missing bean errors from assertion failures by symptoms

| Symptom | Missing bean / context error | Assertion failure |
|---|---|---|
| Timing | Usually before the test method | Inside the test method or an assertion in a lifecycle callback |
| Common exceptions | `NoSuchBeanDefinitionException`, `UnsatisfiedDependencyException`, `BeanCreationException` | `AssertionFailedError`, `AssertionError`, or assertion library error |
| Message | `No qualifying bean`, `Failed to load ApplicationContext` | `expected ... but was ...`, `expected true but was false` |
| Stack trace | Passes through Spring bean factory, dependency resolution, context loader | Points to the assertion line in the test or assertion helper |
| Did the test method run? | Usually not | Yes; at least up to the failing assertion |
| What to check | Bean definitions, profiles, scans, qualifiers, test slices, context config | Expected/actual values, logic, fixtures, mock stubbing, and functional contract |

Note that an assertion inside `@BeforeEach` or a test helper can also fail before the main test method is invoked. Therefore, stack traces and exception types remain more reliable than looking solely at overall timing.

## 6. Do not confuse Mockito's @Mock with a Spring bean

This is a common reason why a test appears to create a mock yet Spring still reports a missing bean.

`@Mock` creates a Mockito mock object. It does not automatically register that object into the `ApplicationContext`. `@InjectMocks` tells Mockito to instantiate the object under test and inject mocks according to Mockito's rules; that object does not automatically become a Spring bean either.

Pure unit test example:

```java
@ExtendWith(MockitoExtension.class)
class AccountServiceUnitTest {

    @Mock
    private AccountRepository repository;

    @InjectMocks
    private AccountService service;

    @Test
    void returnsAccountWhenRepositoryFindsIt() {
        when(repository.findById(42L))
                .thenReturn(Optional.of(new Account(42L)));

        assertEquals(42L, service.findById(42L).id());
    }
}
```

This test does not need a Spring `ApplicationContext`. Mockito creates the mock repository itself and injects it into the service.

Conversely, if a test has `@Autowired AccountService` and uses `SpringExtension`, Spring looks up the `AccountService` bean in the context. A `@Mock AccountRepository` field does not satisfy the requirement to create an `AccountRepository` bean for that context.

When you need to mock a dependency inside a Spring context, use `@MockitoBean` (Spring Framework 6.2+) or the compatible Spring Boot annotation in older versions:

```java
@SpringJUnitConfig(AccountTestConfiguration.class)
class AccountServiceSpringTest {

    @Autowired
    private AccountService service;

    @MockitoBean
    private AccountRepository repository;

    @Test
    void delegatesLookupToRepository() {
        when(repository.findById(42L))
                .thenReturn(Optional.of(new Account(42L)));

        assertEquals(42L, service.findById(42L).id());
    }
}
```

The example assumes `AccountTestConfiguration` registers `AccountService` and other required beans. `@MockitoBean` supplies the mock inside the context so Spring can inject it into the service. If the configuration still lacks `AccountService`, mocking the repository cannot create the service bean on its own.

## 7. Missing bean errors vs. test instance injection errors

Not every issue involving `@Autowired` is a `NoSuchBeanDefinitionException`.

### 7.1. SpringExtension is not registered

In a plain JUnit Jupiter test, `@Autowired` is not processed automatically by JUnit. For Spring to perform dependency injection on the test instance, you must register `SpringExtension`, typically via `@ExtendWith(SpringExtension.class)` or a composed annotation such as `@SpringJUnitConfig`.

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class SpringManagedTest {

    @Autowired
    private AccountService service;
}
```

If the extension is missing, JUnit can still run the test method as a regular test, yet the `service` field is never injected by Spring. When code accesses that field, the result may be a `NullPointerException` or a failed `assertNotNull` assertion. This is a test framework integration error, not necessarily Spring searching for a bean and failing to find it.

### 7.2. SpringExtension is present, yet the dependency does not exist

If the extension is active and Spring prepares the test instance without a matching bean, injection can fail with a dependency resolution error. In that case, check context configuration and bean definitions.

### 7.3. Test constructor or method parameter is not supported by a resolver

JUnit Jupiter uses `ParameterResolver` to supply parameters to test constructors and methods. If a parameter is not supported by any resolver, JUnit can throw `ParameterResolutionException`.

Example:

```java
@Test
void testWithUnresolvedParameter(AccountService service) {
    // If no ParameterResolver supports this parameter,
    // JUnit cannot invoke the method.
}
```

Do not assume that declaring a bean-typed parameter is enough for Spring to inject it automatically. Register `SpringExtension` and use an injection mechanism supported by Spring Test, such as appropriate annotations on parameters or a test constructor per the active configuration. If the error is `ParameterResolutionException`, check resolvers and parameter annotations before concluding a bean is missing.

## 8. Cases where a dependency is optional

A missing dependency is not always an error. If the application defines it as optional, Spring can inject it in a way that permits absence.

Example:

```java
@Component
class OptionalAuditService {

    private final ObjectProvider<AuditClient> auditClientProvider;

    OptionalAuditService(ObjectProvider<AuditClient> auditClientProvider) {
        this.auditClientProvider = auditClientProvider;
    }

    void audit(String event) {
        AuditClient client = auditClientProvider.getIfAvailable();
        if (client != null) {
            client.send(event);
        }
    }
}
```

`ObjectProvider#getIfAvailable()` allows the bean to keep working when no `AuditClient` is present. Similarly, `Optional<T>` or injection with `@Autowired(required = false)` can express non-mandatory dependencies using the appropriate API and injection site.

If a dependency is declared as required via a constructor, Spring must find a matching bean. Do not make a required dependency optional merely to get a test to start; clarify the application contract and configure the test accordingly.

## 9. Reading stack traces in the right order

When a test fails, start from the summary to see which test and exception failed. Then locate the assertion line or Spring's cause chain.

Example context error:

```text
AccountServiceTest > loadsService FAILED
    java.lang.IllegalStateException: Failed to load ApplicationContext
        Caused by: UnsatisfiedDependencyException:
            Error creating bean with name 'accountService'
        Caused by: NoSuchBeanDefinitionException:
            No qualifying bean of type 'AccountRepository' available
```

How to read it:

1. `Failed to load ApplicationContext` tells you the test has no ready context.
2. `UnsatisfiedDependencyException` tells you Spring was creating `accountService` but could not satisfy a dependency.
3. `NoSuchBeanDefinitionException` pinpoints the bean type that could not be found.
4. Check configuration classes, scan paths, profiles, test slices, and repository mocking.

Example assertion error:

```text
AccountServiceTest > returnsAccountWhenRepositoryFindsIt FAILED
    org.opentest4j.AssertionFailedError:
    Expected: 42
    Actual:   0
        at AccountServiceTest.returnsAccountWhenRepositoryFindsIt(AccountServiceTest.java:28)
```

How to read it:

1. The context was created sufficiently for the test method to execute.
2. The stack trace points to the assertion statement inside the test method.
3. Check whether fixtures and mock stubbing return the right data.
4. If inputs are right, check service logic and expected values.

Do not search only for the keyword `FAILED`. The same summary line can represent a context error, a setup error, an assertion failure, or an unexpected runtime exception in code.

## 10. Checking the context independently when a missing bean is suspected

When Spring configuration is in doubt, you can write a small test that only verifies context startup and that the required beans exist.

```java
@SpringJUnitConfig(AccountTestConfiguration.class)
class AccountContextTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void registersAccountService() {
        assertTrue(context.containsBean("accountService"));
        assertNotNull(context.getBean(AccountService.class));
    }
}
```

This test separates context configuration from business logic. If the context cannot initialize, the failure happens before the assertion. If the context initializes yet the bean is missing, the assertion or `getBean` points out the missing configuration more directly.

You can query beans by type:

```java
Map<String, AccountService> beans =
        context.getBeansOfType(AccountService.class);

assertEquals(1, beans.size());
```

If the application has multiple valid implementations, do not assert a count of 1 unless the contract requires it. Check qualifiers or the specific bean you expect.

## 11. Checking test slice configuration and full configuration

Choosing the right context scope prevents many missing bean errors.

| Annotation / setup | Primary scope | What to watch out for |
|---|---|---|
| Unit test with Mockito | No Spring context | Use `@Mock`, `@InjectMocks`, and `MockitoExtension` |
| `@SpringJUnitConfig` | Spring TestContext with specified config | Must supply required configuration and beans |
| `@ContextConfiguration` | Loads Spring configuration sources for tests | Check classes, locations, and context hierarchy |
| `@WebMvcTest` | Spring Boot MVC slice | Mock or import out-of-slice services/dependencies |
| `@WebFluxTest` | Spring Boot WebFlux slice | Supply mock beans for out-of-slice services/dependencies |
| `@DataJpaTest` | Spring Boot persistence slice | Does not load full service/web layers by default |
| `@SpringBootTest` | Broader Spring Boot application context | May require infrastructure, properties, and external dependencies |

The `*Test`-suffixed annotations in the table such as `@WebMvcTest`, `@WebFluxTest`, `@DataJpaTest`, and `@SpringBootTest` are Spring Boot Test features. Plain Spring Framework provides the TestContext Framework and the corresponding context-building mechanisms.

If a test needs both a real controller and a real service while mocking the repository, configure a context scope broad enough to create the controller/service and replace the repository with a test bean or mock bean. If a test only checks controller HTTP mappings and responses, using an MVC/WebFlux slice with a mocked service is faster and clearer.

## 12. Distinguishing missing bean errors from mock setup errors

A mock can exist yet be configured improperly. In that case, the context still initializes and the test method runs, yet assertions fail or exceptions occur while invoking the mock.

Example:

```java
@Test
void returnsAccount() {
    when(repository.findById(42L))
            .thenReturn(Optional.of(new Account(42L)));

    Account result = service.findById(7L);

    assertNotNull(result);
}
```

The mock is stubbed for `42L`, while the test calls `7L`. Mockito returns a default value when no stub matches; the service may return `null` or follow a different branch. This is a test setup or logic error, not a missing bean error.

When an assertion fails in a test using mocks, check:

- Does the stub match the actual arguments?
- Is the mock injected into the exact object under test?
- Is a different service instance being called than the one created by `@InjectMocks`?
- Was the mock reset between methods by an extension or test configuration?
- Is an exception being thrown by a stub or answer?
- Is the test asserting the right contract outcome?

## 13. Handling errors by root cause

When encountering a missing bean message, address it according to the problem category:

| Cause | Appropriate resolution |
|---|---|
| Bean not picked up by component scan | Adjust package scanning or declare bean configuration in the right scope |
| `@Bean` configuration not loaded | Add configuration to `@ContextConfiguration`, `@Import`, or appropriate Boot config |
| Profile not active | Declare `@ActiveProfiles` or set the right profile for the test |
| External dependency need not run for real | Register a test bean or `@MockitoBean`/compatible mock bean mechanism |
| Test slice excludes dependency | Use a mock bean, `@Import`, or pick a scope matching the test goal |
| Multiple beans of the same type | Choose `@Qualifier`, `@Primary`, or inject multiple beans per contract |
| JUnit does not perform Spring injection | Register `SpringExtension` or use a composed annotation like `@SpringJUnitConfig` |
| Test parameter has no resolver | Configure `ParameterResolver` or a Spring-supported parameter injection mechanism |
| Expected/actual assertion mismatch | Check fixtures, stubs, inputs, logic, and expected contract |

Do not mechanically add fake beans for every error. If a bean is the component under test, supply the real implementation in the context. If a bean is an out-of-scope dependency, mocking is reasonable. If a dependency is genuinely optional, inspect how the application expresses optionality.

## 14. A concise diagnostic workflow

When a Spring test fails, you can follow this sequence:

1. Check whether the test was discovered and started executing.
2. If you see `Failed to load ApplicationContext`, read `Caused by` exceptions to find the root bean or configuration issue.
3. If you see `NoSuchBeanDefinitionException`, check bean type, component scan, `@Bean`, profiles, conditions, and test slice.
4. If you see `NoUniqueBeanDefinitionException`, check implementations and qualifiers.
5. If an `@Autowired` field is `null` without a Spring context error, check `SpringExtension` and test instance creation.
6. If you see `ParameterResolutionException`, check resolvers and parameter annotations.
7. If you see `AssertionFailedError` or `AssertionError`, inspect expected/actual values and the assertion line.
8. If a mock was injected yet results are wrong, check stubbing, invocation arguments, and which instance is under test.
9. If the context fails repeatedly after the first failure, read the context failure threshold message to find the original error from the first load attempt.

Spring TestContext includes a context caching mechanism. Since Spring Framework 6.1, a default failure threshold mechanism can prevent retrying the same failing context repeatedly after an initial failure. When you see a message such as “ApplicationContext failure threshold exceeded”, it is usually the consequence of an earlier context initialization failure. Locate the first log entry for that same context to identify the real cause, rather than treating the threshold message as an independent bean error.

## 15. Test design principles for easy diagnosis

- Name tests to express the condition and outcome, such as `loadsContext_whenRepositoryBeanIsConfigured` or `returnsNotFound_whenAccountDoesNotExist`.
- Keep a test focused on one primary behavior; avoid bundling unrelated configurations and assertions.
- Use plain unit tests when the Spring container is not needed.
- Use Spring context tests when verifying bean wiring, profiles, properties, or lifecycles.
- With test slices, clearly distinguish mocked dependencies from real dependencies belonging to the slice.
- Verify both exception type and root cause when testing cases where a context is expected to fail.
- Use assertions with clear expected/actual info and descriptive condition messages when that aids diagnosis.
- Do not turn configuration errors into skipped tests or relaxed assertions just to make the suite pass.

By reading the failure stage, exception type, and stack trace accurately, you can tell apart a bean that Spring failed to create or inject from a behavior that executed yet produced the wrong outcome. Missing bean errors must be fixed in context configuration and dependency injection; assertion failures require checking data, mock setup, and the logic under test. Clearly distinguishing these two categories helps fix the real root cause and keeps the Spring test suite an accurate reflection of the application's state.
