# Extensions and How SpringExtension Participates in the Lifecycle

JUnit Jupiter extends the test lifecycle through its *Extension* mechanism. An extension can participate at defined moments before, during, and after tests execute. This mechanism enables framework integration, resource management, supplying data to tests, or customizing execution without modifying the JUnit engine.

In Spring Framework Testing, `SpringExtension` is the bridge between JUnit Jupiter and the Spring TestContext Framework. It receives callbacks from JUnit, forwards the corresponding lifecycle events to `TestContextManager`, and supports injecting dependencies from the Spring `ApplicationContext` into test instances and test parameters. As a result, a JUnit Jupiter test can use the Spring context, beans, dependency injection, and Spring testing features.

## 1. What Is an Extension in JUnit Jupiter?

In JUnit Jupiter, `Extension` is the extensibility mechanism provided by JUnit. Rather than requiring a single runner to control the entire test class, JUnit allows registering one or more extensions. Each extension can implement one or more extension APIs to participate in specific parts of the lifecycle.

Commonly used extension APIs include:

| Extension API | Role |
|---|---|
| `BeforeAllCallback` | Participates before test methods in the class begin |
| `AfterAllCallback` | Participates after test methods in the class finish |
| `TestInstancePostProcessor` | Processes the test instance after JUnit creates it |
| `BeforeEachCallback` | Participates before each test method |
| `BeforeTestExecutionCallback` | Participates immediately before the test method executes |
| `AfterTestExecutionCallback` | Participates immediately after the test method finishes |
| `AfterEachCallback` | Participates after each test method |
| `ParameterResolver` | Supplies values for constructor or method parameters supported by the extension |

A single extension can implement multiple interfaces. JUnit invokes each callback at the corresponding moment and supplies an `ExtensionContext` so the extension can access information about the running test.

An extension does not need to know the entire internal structure of the test engine. It simply registers at the extension points it needs. This allows integrations such as Spring, Mockito, or project-specific custom extensions to cooperate within JUnit Jupiter.

## 2. What Does SpringExtension Do?

`SpringExtension` lives in Spring Framework's `spring-test` module. It implements JUnit Jupiter's extension APIs and connects them to the Spring TestContext Framework.

You can visualize the relationship as follows:

```text
JUnit Jupiter
     |
     | invokes extension callbacks
     v
SpringExtension
     |
     | forwards events
     v
TestContextManager
     |
     +---- TestContext
     |
     +---- TestExecutionListeners
     |
     v
Spring ApplicationContext
     |
     +---- Spring beans
     +---- dependency injection
     +---- test context and related resources
```

Role of each component:

- **JUnit Jupiter** manages test discovery and execution, creates test instances, and invokes extension callbacks.
- **SpringExtension** receives JUnit callbacks and adapts them to Spring's test lifecycle.
- **TestContextManager** coordinates test instance preparation and events before/after test classes, test methods, and test execution.
- **TestContext** holds the context for a test run, including information about the test class, method, and associated application context.
- **TestExecutionListener** performs specific behaviors during the Spring test lifecycle, such as dependency injection, transaction management, or handling test annotations.
- **ApplicationContext** holds the Spring beans and configuration loaded for the test.

SpringExtension does not define application configuration on its own. Tests still need to declare appropriate Spring configuration, such as `@ContextConfiguration`, `@SpringJUnitConfig`, `@SpringBootTest`, or a Spring Boot test slice.

## 3. Registering SpringExtension with @ExtendWith

The direct way to use SpringExtension is to place `@ExtendWith(SpringExtension.class)` on the test class:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = GreetingTest.TestConfig.class)
class GreetingTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void returnsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }

    @Configuration
    static class TestConfig {

        @Bean
        GreetingService greetingService() {
            return new GreetingService();
        }
    }
}
```

In this example:

1. `@ExtendWith(SpringExtension.class)` registers SpringExtension with JUnit Jupiter.
2. `@ContextConfiguration` declares the configuration used to build the Spring test context.
3. Spring creates the `ApplicationContext` and registers the `GreetingService` bean.
4. SpringExtension coordinates with the TestContext Framework to inject the bean into the `greetingService` field of the test instance.
5. When the test method runs, the test can invoke the injected bean.

The example assumes `GreetingService` is a class with a `greet(String)` method returning a greeting. The imports and configuration demonstrate the integration mechanism; real projects use their own application beans and configurations.

If you only register `SpringExtension` without supplying suitable context configuration, Spring cannot know which beans to create. The extension handles lifecycle integration; test configuration must still specify the source for creating the context.

## 4. Using @SpringJUnitConfig for Conciseness

Spring provides the composed annotation `@SpringJUnitConfig`. This annotation combines registering `SpringExtension` with declaring `@ContextConfiguration`.

Equivalent example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(GreetingTest.TestConfig.class)
class GreetingTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void returnsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }

    @Configuration
    static class TestConfig {

        @Bean
        GreetingService greetingService() {
            return new GreetingService();
        }
    }
}
```

Using `@SpringJUnitConfig` reduces the number of annotations to declare when a test needs a Spring context in the standard way. You can pass configuration classes or configuration locations via attributes supported by `@ContextConfiguration`.

In Spring Boot applications, annotations such as `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, and corresponding test slices already integrate SpringExtension. When using these annotations, you normally do not need to register `@ExtendWith(SpringExtension.class)` again.

## 5. When Does SpringExtension Participate?

SpringExtension maps JUnit Jupiter callbacks to `TestContextManager` events. Key points include:

| JUnit Jupiter Callback | Action Forwarded to TestContextManager | Timing in Lifecycle |
|---|---|---|
| `BeforeAllCallback` | `beforeTestClass()` | Before `@BeforeAll` methods |
| `TestInstancePostProcessor` | `prepareTestInstance()` | After JUnit creates the test instance |
| `BeforeEachCallback` | `beforeTestMethod()` | Before `@BeforeEach` methods |
| `BeforeTestExecutionCallback` | `beforeTestExecution()` | After `@BeforeEach`, right before the test method |
| `AfterTestExecutionCallback` | `afterTestExecution()` | Right after the test method, before `@AfterEach` |
| `AfterEachCallback` | `afterTestMethod()` | After `@AfterEach` methods |
| `AfterAllCallback` | `afterTestClass()` | After `@AfterAll` methods |

This table shows the primary callback milestones. Each `TestContextManager` event can trigger configured `TestExecutionListener` instances to perform their corresponding behavior.

### Before the Test Instance Is Used

JUnit creates the test instance according to its lifecycle. Once the instance is created, JUnit invokes registered `TestInstancePostProcessor` extensions. SpringExtension translates this event into `TestContextManager.prepareTestInstance()`.

This is the stage where Spring prepares the test instance, such as injecting dependencies marked `@Autowired` into fields of the test class. Consequently, with field injection, dependencies are already available before `@BeforeEach` methods and test methods are invoked.

### Before and After Each Test Method

SpringExtension translates before/after test method callbacks into Spring TestContext Framework events. Listeners can use these milestones to set up state, manage transactions, or perform behaviors required by test annotations.

Notably, `beforeTestMethod()` runs before JUnit's `@BeforeEach` methods. The `beforeTestExecution()` event runs after `@BeforeEach` and immediately before the test method. In reverse, `afterTestExecution()` runs immediately after the test method, while `afterTestMethod()` is called after `@AfterEach` methods.

This distinction is helpful when you need to understand whether an operation belongs to the test method preparation stage or to the execution window of the test method itself.

### Before and After the Test Class

SpringExtension also forwards class-level callbacks to `beforeTestClass()` and `afterTestClass()`. These events allow the Spring TestContext Framework and its listeners to perform work scoped to the entire test class.

Do not confuse class-level callbacks with per-method callbacks. A class with multiple test methods still has multiple before/after method cycles, while class-level events execute according to the class lifecycle.

## 6. Relationship Between Extension Callbacks and @BeforeEach, @AfterEach

JUnit Jupiter has lifecycle methods declared by test authors, such as `@BeforeAll`, `@BeforeEach`, `@AfterEach`, and `@AfterAll`. Extension callbacks are integration points invoked around these methods.

For a standard test method, the main order can be visualized as follows:

```text
JUnit creates test instance
        |
        v
SpringExtension
  prepareTestInstance()
        |
        v
SpringExtension
  beforeEach()
        |
        v
TestContextManager
  beforeTestMethod()
        |
        v
JUnit @BeforeEach
        |
        v
SpringExtension
  beforeTestExecution()
        |
        v
TestContextManager
  beforeTestExecution()
        |
        v
JUnit @Test
        |
        v
SpringExtension
  afterTestExecution()
        |
        v
TestContextManager
  afterTestExecution()
        |
        v
JUnit @AfterEach
        |
        v
SpringExtension
  afterEach()
        |
        v
TestContextManager
  afterTestMethod()
```

This sequence describes the basic integration flow when SpringExtension is registered. If the test class registers additional extensions, callback ordering between extensions can be influenced by registration order and JUnit rules. When coordinating multiple extensions, specify ordering explicitly rather than assuming callbacks run in an arbitrary order.

For example, `@Autowired` fields are prepared during `prepareTestInstance()`, so they can be used inside `@BeforeEach`:

```java
@SpringJUnitConfig(TestConfig.class)
class GreetingServiceTest {

    @Autowired
    private GreetingService greetingService;

    private String input;

    @BeforeEach
    void setUp() {
        input = "Lan";
        // greetingService has already been injected by Spring
    }

    @Test
    void returnsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet(input));
    }
}
```

If dependencies are not injected as expected, inspect the Spring configuration, extension registration annotations, and test instance preparation process. Do not try to work around it by manually calling a SpringExtension callback.

## 7. Dependency Injection for Test Instances

One of the clearest benefits of SpringExtension is supporting dependency injection into the test class itself. The Spring TestContext Framework performs this preparation through the appropriate `TestExecutionListener`.

Field injection example:

```java
@SpringJUnitConfig(TestConfig.class)
class AccountServiceTest {

    @Autowired
    private AccountService accountService;

    @Test
    void loadsAccount() {
        Account account = accountService.findById("ACC-01");

        assertEquals("ACC-01", account.getId());
    }
}
```

The `accountService` field is injected by Spring before the test method executes. The test does not need to instantiate the service or wire its dependencies manually.

### Injection into Test Method Parameters

SpringExtension also implements `ParameterResolver`. Thus, Spring can supply dependencies for method parameters when the parameter is of a type supported by SpringExtension, typically marked with an appropriate injection annotation such as `@Autowired`, `@Qualifier`, or `@Value`.

```java
@SpringJUnitConfig(TestConfig.class)
class AccountServiceTest {

    @Test
    void loadsAccount(@Autowired AccountService accountService) {
        Account account = accountService.findById("ACC-01");

        assertEquals("ACC-01", account.getId());
    }
}
```

This keeps the dependency scoped only to the test method that uses it, rather than storing it as a class-wide field.

JUnit Jupiter also has its own parameter resolvers for parameters such as `TestInfo` or `TestReporter`. Resolvers cooperate through JUnit's extension mechanism. SpringExtension resolves only the parameters it determines it supports; it does not automatically resolve arbitrary parameters.

### Constructor Injection for Test Classes

If you want to inject dependencies through the test class constructor, configure the Spring TestContext Framework's constructor autowiring mode. You can use `@TestConstructor` to declare the mode explicitly:

```java
@SpringJUnitConfig(TestConfig.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class AccountServiceTest {

    private final AccountService accountService;

    AccountServiceTest(AccountService accountService) {
        this.accountService = accountService;
    }

    @Test
    void loadsAccount() {
        assertEquals(
                "ACC-01",
                accountService.findById("ACC-01").getId()
        );
    }
}
```

The `ALL` mode instructs Spring to autowire all constructor parameters. Projects can also configure the default mode via the corresponding Spring Test property. When constructor injection is not enabled under current configuration, JUnit or Spring may fail to resolve parameters as intended.

Constructor injection expresses required dependencies directly in the class structure. Field or method parameter injection can be more convenient when tests prefer simpler organization or when a dependency serves only certain methods.

## 8. SpringExtension and TestExecutionListener

SpringExtension is the integration layer between JUnit Jupiter and the Spring TestContext Framework. Many concrete test behaviors are executed by `TestExecutionListener` implementations, rather than by code in the test class itself.

Examples of work handled by the TestContext Framework and listeners:

- Injecting dependencies into test instances.
- Managing test transactions when appropriate configuration is used.
- Handling test annotations such as `@Sql` or `@DirtiesContext`.
- Executing actions before/after test methods according to test policies.
- Preparing and cleaning up test state according to registered listeners.

This creates a clear boundary: JUnit drives the test lifecycle, SpringExtension forwards lifecycle milestones, and TestContextManager together with listeners orchestrate Spring Testing features.

When a Spring feature does not behave as expected, check whether annotations are declared correctly, whether the corresponding listener participates, and whether the application context is configured properly. Do not assume that merely adding `@ExtendWith(SpringExtension.class)` automatically enables every Spring Testing feature without additional annotations or configuration.

## 9. How SpringExtension Works with Spring Boot Test

In Spring Boot applications, test annotations typically already register SpringExtension and supply a bootstrapper to build the application context the Spring Boot way.

Example with `@SpringBootTest`:

```java
@SpringBootTest
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        Order order = orderService.createOrder(
                new CreateOrderCommand("CUSTOMER-42")
        );

        assertNotNull(order.getId());
    }
}
```

With a test slice:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    // Test MVC behaviors here
}
```

Annotations such as `@SpringBootTest` and `@WebMvcTest` handle selecting the context type or the slice of components to load. SpringExtension handles integrating JUnit lifecycle events with the Spring TestContext Framework. These are two related yet distinct responsibilities.

With test slices, only a targeted portion of application configuration is loaded. If a controller needs a service that the slice does not automatically provide, the test may need to declare a mock bean or appropriate configuration. SpringExtension does not automatically widen the slice to load missing components.

## 10. Context Caching and the Test Lifecycle

The Spring TestContext Framework includes an `ApplicationContext` caching mechanism keyed by test configuration. When multiple test classes use equivalent configurations, Spring can reuse an already-created context instead of restarting the entire context for each test.

SpringExtension retrieves and uses the `TestContextManager` associated with the test class; the TestContext Framework manages context access and caching. This reduces startup overhead when running many Spring tests.

However, reusing a context means singleton beans in that context can persist across multiple test methods or test classes sharing the context. Do not allow mutable state in shared beans to be arbitrarily modified by tests unless that state is explicitly controlled and cleaned up.

The `@DirtiesContext` annotation marks a context to be evicted from the cache after a test modifies context state in an unrecoverable way. Do not apply this annotation by default to every test, as rebuilding contexts can slow down the suite significantly.

Also distinguish context caching from test data fixtures. Caching reuses the `ApplicationContext`; it does not automatically ensure database data or business state is cleaned between tests. Fixtures and transaction/cleanup strategies must still be designed properly.

## 11. Distinguishing SpringExtension from SpringRunner

In JUnit 4, Spring provided `SpringRunner` (also seen as `SpringJUnit4ClassRunner`) to integrate the Spring TestContext Framework with JUnit 4's runner mechanism.

In JUnit Jupiter, the extensibility mechanism is `Extension`, so the corresponding class is `SpringExtension`.

| JUnit 4 | JUnit Jupiter |
|---|---|
| `@RunWith(SpringRunner.class)` | `@ExtendWith(SpringExtension.class)` |
| Runner integrating with JUnit 4 | Extension integrating with JUnit Jupiter |
| Lifecycle driven by the runner model | Lifecycle driven by callbacks and the extension API |

Do not use `@RunWith(SpringRunner.class)` to register Spring integration on a test class running with JUnit Jupiter. With JUnit Jupiter, use `@ExtendWith(SpringExtension.class)`, `@SpringJUnitConfig`, or the appropriate Spring Boot test annotation.

## 12. Common Errors When Configuring SpringExtension

| Symptom | Common Cause | What to Check |
|---|---|---|
| Dependency in test field is null | SpringExtension is not registered or test context is misconfigured | Check `@ExtendWith`, `@SpringJUnitConfig`, or Spring Boot annotations |
| Failed to create ApplicationContext | Missing configuration, invalid bean, or wrong environment setup | Read the root cause in context loading errors and inspect `@ContextConfiguration` |
| Test method parameter is not resolved | Parameter type is not supported by SpringExtension or lacks injection annotation | Check `@Autowired`, `@Qualifier`, `@Value`, and parameter type |
| Test constructor is not injected | Constructor autowiring mode is not enabled | Check `@TestConstructor` or the corresponding configuration property |
| Test slice is missing a bean | Slice only loads a limited scope of components | Declare mocks or configuration required by the slice |
| Bean state affects other tests | Context/beans are reused and hold mutable state | Keep tests independent, reset state, or choose an appropriate context strategy |
| JUnit 4 and Jupiter annotations mixed up | Confusing runners with extensions | Use annotations matching the test engine |

When diagnosing issues, separate three questions: is JUnit genuinely running the test with Jupiter; is SpringExtension registered; and does the Spring TestContext Framework have sufficient configuration to build the context and prepare the test instance? These three conditions are related, yet none can substitute for another.

## 13. When to Write a Custom Extension vs. Using SpringExtension

SpringExtension already provides the lifecycle integration needed for tests using the Spring TestContext Framework. Most application tests only need to register the extension through standard annotations.

A custom extension may fit when a project wants to add shared test behavior, such as creating data according to a convention, recording metadata, or setting up test resources. An extension should implement only the callbacks that behavior requires and take responsibility for cleaning up corresponding resources.

Do not write a custom extension to replace SpringExtension or manually invoke internal `TestContextManager` methods if the goal is simply injecting beans or initializing a Spring context. Those capabilities are already provided by the Spring TestContext Framework.

If a project needs a custom extension collaborating with SpringExtension, understand registration order and callback timing clearly. Avoid letting two extensions mutate the same state without explicit coordination rules.

## 14. Tracing the Lifecycle While Debugging

When you need to understand what SpringExtension is doing, trace these milestones:

1. **Verify the test engine:** confirm the test is running under JUnit Jupiter.
2. **Verify extension registration:** look for `@ExtendWith(SpringExtension.class)`, `@SpringJUnitConfig`, or Spring Boot annotations integrating the extension.
3. **Identify context configuration sources:** inspect `@ContextConfiguration`, `@SpringBootTest`, test slices, or corresponding bootstrap configurations.
4. **Inspect the test instance:** check how field injection, method parameters, or constructor parameters are configured.
5. **Follow callbacks:** determine whether the error occurred during instance preparation, before method, before execution, after execution, or after method.
6. **Read listeners and root causes:** if the error originates from Spring TestContext, examine the relevant listener or context configuration instead of looking only at the test method line.
7. **Check shared state:** if tests fail depending on execution order, inspect singleton beans, cached contexts, transactions, and fixture data.

Understanding these milestones helps separate bugs in the business logic under test from errors occurring during test context initialization or management.

SpringExtension is the adapter that brings the Spring TestContext Framework into the JUnit Jupiter lifecycle. Once you understand how the extension is registered, how callbacks are mapped, and how dependencies are prepared, developers can use Spring beans in tests intentionally, choose the right test annotations, and diagnose lifecycle-related errors more clearly.

