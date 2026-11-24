# Default Listeners List and Their Responsibilities

The Spring TestContext Framework uses `TestExecutionListener` to attach supporting behaviors to a test's lifecycle. Each listener receives callbacks when the test class is prepared, the test instance is created, and a test method starts or ends. As a result, features such as dependency injection for tests, ApplicationContext management, transactions, SQL script execution, and application event recording work consistently without the test having to invoke each component manually.

Default listeners are automatically registered by Spring when initializing TestContext. They have a defined execution order so preparation happens before the test runs and cleanup runs after the test completes. When extension is needed, you can add custom listeners or alter the list via `@TestExecutionListeners` configuration.

## 1. Where Does TestExecutionListener Fit in the TestContext Framework?

`TestExecutionListener` is a Spring interface located in the `org.springframework.test.context` package. It is part of the Spring TestContext Framework, not JUnit Platform's identically named `TestExecutionListener` interface.

Spring uses `TestContextManager` to coordinate listeners. The manager holds the `TestContext`, updates information about the test class, test instance, test method, and exception, and then invokes the corresponding callback on each listener. When integrating with JUnit Jupiter, `SpringExtension` connects JUnit's lifecycle to `TestContextManager`. Annotations such as `@SpringJUnitConfig` already integrate Spring Extension, so you normally do not need to declare `@ExtendWith(SpringExtension.class)` separately when using that annotation.

A test class can declare Spring configuration as follows:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
class CustomerServiceTest {
    @Autowired
    private CustomerService customerService;

    @Test
    void findsCustomer() {
        // Perform checks with beans injected by Spring.
    }
}
~~~

When the test runs, Spring Extension creates and uses `TestContextManager`. Listeners are invoked at appropriate milestones to prepare the context, inject the test instance, open transactions, or perform related tasks. The test class only declares what to verify; lifecycle integration is handled by the framework.

## 2. Callbacks in the Test Lifecycle

The `TestExecutionListener` interface defines the following main callbacks:

| Callback | Timing | Scope |
|---|---|---|
| beforeTestClass | Before the class's test methods begin | Once per test class |
| prepareTestInstance | After creating the test instance, before running test setup fixtures | Per test instance |
| beforeTestMethod | Before each test method | Per test method |
| beforeTestExecution | Immediately before the test method body | Per test method |
| afterTestExecution | Immediately after the test method body, even if the method throws an exception | Per test method |
| afterTestMethod | After the test method completes and method cleanup callbacks are processed | Per test method |
| afterTestClass | After all test methods of the class complete | Once per test class |

The two pairs `beforeTestMethod` and `beforeTestExecution`, and `afterTestExecution` and `afterTestMethod`, serve different milestones. For instance, one listener might prepare a transaction before the test method runs, while another listener needs to time only the test body. Putting both tasks in the same callback could cause the measurement scope or activation timing to be wrong.

Starting callbacks such as `beforeTestClass`, `prepareTestInstance`, `beforeTestMethod`, and `beforeTestExecution` are invoked in sorted listener order. Ending callbacks such as `afterTestExecution`, `afterTestMethod`, and `afterTestClass` are invoked in reverse order so cleanup happens in the opposite order of preparation. This mirrors the principle of opening resources in one order and closing them in reverse order.

## 3. Spring Framework's Default Listeners List

As of Spring Framework 6.1, the TestContext Framework's default listener list consists of eight listeners in the following order:

| Order | Listener | Primary Responsibility |
|---:|---|---|
| 1 | ServletTestExecutionListener | Prepares request/response state for web tests |
| 2 | DirtiesContextBeforeModesTestExecutionListener | Handles `@DirtiesContext` in BEFORE modes |
| 3 | ApplicationEventsTestExecutionListener | Records application events during tests when enabled |
| 4 | DependencyInjectionTestExecutionListener | Injects dependencies into the test instance |
| 5 | DirtiesContextTestExecutionListener | Handles `@DirtiesContext` in AFTER modes |
| 6 | TransactionalTestExecutionListener | Manages test-declared transactions |
| 7 | SqlScriptsTestExecutionListener | Runs SQL scripts declared with `@Sql` |
| 8 | EventPublishingTestExecutionListener | Publishes Spring application events for test lifecycle milestones |

The list above describes the listeners belonging to Spring Framework 6.1. The actual list depends on the Spring version and testing libraries placed on the classpath. Spring Boot or extension modules may add listeners for specific features; do not assume every listener observed in a Spring Boot project is a core Spring Framework listener.

Spring TestContext uses `SpringFactoriesLoader` to discover `TestExecutionListener` implementations registered by the framework and libraries on the classpath. Listeners are sorted by their order before `TestContextManager` uses them. Consequently, adding testing dependencies to a project can alter the actual list without the test class explicitly listing those listeners.

### 3.1. ServletTestExecutionListener

`ServletTestExecutionListener` supports testing Servlet-based web applications. When a test uses appropriate web configuration, the listener prepares mock request and response objects and sets request attributes in `RequestContextHolder`. As a result, application code can access request information through Spring's mechanism without needing a real Servlet container.

For example, a component using `RequestContextHolder` to read the current request can be tested in a mock web environment:

~~~java
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;

public class CurrentRequestService {
    public String currentRequestId() {
        RequestAttributes attributes =
                RequestContextHolder.currentRequestAttributes();
        return (String) attributes.getAttribute(
                "requestId",
                RequestAttributes.SCOPE_REQUEST);
    }
}
~~~

In a web test, the request context is prepared so application code can use the API above. The listener also manages cleaning up request state along the test lifecycle so data from one request does not leak to another test.

This listener is only meaningful when the test has an appropriate web environment, such as a `WebApplicationContext` configured with `@WebAppConfiguration`. For ordinary unit tests or non-web contexts, there is no need to create requests manually just to use this listener.

### 3.2. DirtiesContextBeforeModesTestExecutionListener

`DirtiesContextBeforeModesTestExecutionListener` handles cases where `@DirtiesContext` requires evicting the context before a test class or test method runs. BEFORE modes are typically used when an earlier test may have altered context configuration state and the current test needs a fresh context.

Example:

~~~java
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.BEFORE_CLASS)
class FreshContextTest {
    // The test class runs with a fresh context per the declared mode.
}
~~~

`@DirtiesContext` marks the `ApplicationContext` as no longer suitable for reuse. The pre-test listener handles BEFORE modes; the `DirtiesContextTestExecutionListener` further down handles AFTER modes. Splitting into two listeners lets Spring place context eviction at the right lifecycle milestones.

Do not use `@DirtiesContext` merely to delete business data in the database. This annotation affects the cache and lifecycle of `ApplicationContext`; database data should be cleaned up using transactions, SQL cleanup, or an appropriate test data mechanism.

### 3.3. ApplicationEventsTestExecutionListener

`ApplicationEventsTestExecutionListener` provides the ability to record Spring application events published during a test. When `@RecordApplicationEvents` is enabled, the test can inject `ApplicationEvents` and query events published within the test scope.

Example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEvent;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

class OrderCreatedEvent extends ApplicationEvent {
    OrderCreatedEvent(Object source) {
        super(source);
    }
}

@SpringJUnitConfig(TestConfiguration.class)
@RecordApplicationEvents
class OrderEventTest {
    @Autowired
    private ApplicationEvents applicationEvents;

    @Autowired
    private OrderService orderService;

    @Test
    void publishesOrderCreatedEvent() {
        orderService.createOrder();

        long count = applicationEvents
                .stream(OrderCreatedEvent.class)
                .count();

        assertEquals(1, count);
    }
}
~~~

`ApplicationEvents` helps tests verify that event-driven behavior occurred without manually installing an observer listener in each test. The listener manages the recorder along the test lifecycle and scopes event data appropriately to the running test.

`@RecordApplicationEvents` is a crucial condition to enable recording. Without requesting recording, do not assume every event across the entire context is stored for the test to query.

### 3.4. DependencyInjectionTestExecutionListener

`DependencyInjectionTestExecutionListener` injects Spring dependencies into the test instance. This is the listener that enables fields or methods marked with injection annotations to receive beans from `ApplicationContext`.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
class ProductServiceTest {
    @Autowired
    private ProductService productService;

    @Test
    void loadsProduct() {
        // productService has already been injected by Spring into the test instance.
    }
}
~~~

This listener performs autowiring and prepares the test instance according to Spring's mechanism. It is commonly used with `@SpringJUnitConfig`, `@ContextConfiguration`, or other TestContext configurations.

Distinguish injecting dependencies into the test instance from injecting into application beans. The Spring container still instantiates and injects application beans per its configuration; this listener adds the preparation step for the test object itself created by JUnit.

If a unit test only needs to verify the logic of a Java class, you can instantiate that class via constructor and pass fakes or mocks directly. In that case, there is no need to enable TestContext just to inject a field.

### 3.5. DirtiesContextTestExecutionListener

`DirtiesContextTestExecutionListener` handles AFTER modes of `@DirtiesContext`, such as evicting the context after a test method or after a test class. When the context is marked dirty, Spring removes it from the context cache and closes it according to lifecycle management.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
class ContextMutationTest {
    @Test
    @DirtiesContext(
            methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void changesContextState() {
        // Test modifies context configuration state.
    }
}
~~~

Subsequent tests needing the corresponding context will have to obtain a fresh context from configuration. This can make tests run slower because Spring must reinitialize beans and related components.

Mark a context dirty only when a test genuinely alters the structure or state of the context in a way that affects other tests. If the issue is merely data in a table, transaction rollback or SQL cleanup is usually more suitable.

### 3.6. TransactionalTestExecutionListener

`TransactionalTestExecutionListener` supports test-managed transactions. When a test class or test method is annotated with `@Transactional`, the listener can start a transaction before the test method and roll it back after the test completes by default.

Example:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.annotation.Transactional;

@SpringJUnitConfig(TestConfiguration.class)
@Transactional
class ProductRepositoryTest {
    @Autowired
    private ProductRepository repository;

    @Test
    void savesProductInsideTestTransaction() {
        repository.save(new Product("P-01", "Keyboard"));

        assertTrue(repository.findById("P-01").isPresent());
    }
}
~~~

In this example, the save and query operations run inside the test's transaction. After the test, data is normally rolled back so it does not remain as committed application data.

Several annotations control transaction behavior:

- `@Rollback` specifies whether the test transaction rolls back; default is rollback.
- `@Commit` requests committing the transaction when the test completes.
- `@BeforeTransaction` marks a method to run before the test-managed transaction begins.
- `@AfterTransaction` marks a method to run after the test-managed transaction ends.

The listener must be able to locate an appropriate transaction manager in the context. If multiple transaction managers exist, configuration must help Spring pick the right manager for the test. Remember also that a test-managed transaction does not automatically encompass tasks running on other threads; asynchronous operations or application-initiated transactions may have independent lifecycles.

Do not use `@Commit` casually in tests sharing a database. Committed data can affect later runs and make tests depend on environment state.

### 3.7. SqlScriptsTestExecutionListener

`SqlScriptsTestExecutionListener` executes SQL scripts declared with `@Sql`. This is a way to prepare data before a test or clean up data after a test without writing extensive setup commands in Java.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
@Sql(
        scripts = "/sql/products-before.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class ProductSqlTest {
    @Test
    @Sql(
            scripts = "/sql/products-after.sql",
            executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
    void readsPreparedProductData() {
        // Verify data created by products-before.sql.
    }
}
~~~

`BEFORE_TEST_METHOD` is the default phase when no other phase is declared. `AFTER_TEST_METHOD` is commonly used to execute cleanup scripts. More detailed configuration is possible with `@SqlConfig`, such as selecting datasource, transaction manager, encoding, or transaction mode.

This listener coordinates with test transactions when configuration allows. Scripts can join an existing transaction or execute in a separate transaction per `@SqlConfig`. Therefore, understand listener order and transaction configuration if setup data must be rolled back with the test or must persist outside the transaction.

`@Sql` can be placed at the class or method level. When multiple declarations coexist, default merge behavior and `@SqlMergeMode` determine how scripts at both levels combine. Clearly separate shared baseline data from test-specific data so scripts remain easy to follow.

### 3.8. EventPublishingTestExecutionListener

`EventPublishingTestExecutionListener` publishes Spring application events corresponding to milestones of the test lifecycle. Components inside `ApplicationContext` can listen to these events using `@EventListener` or Spring's listener mechanism.

Published events correspond to milestones such as:

- BeforeTestClassEvent
- PrepareTestInstanceEvent
- BeforeTestMethodEvent
- BeforeTestExecutionEvent
- AfterTestExecutionEvent
- AfterTestMethodEvent
- AfterTestClassEvent

For example, a component can listen to the event before the test body executes:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.test.context.event.BeforeTestExecutionEvent;

public class TestLifecycleObserver {
    @EventListener
    public void beforeTestExecution(
            BeforeTestExecutionEvent event) {
        Class<?> testClass = event.getTestContext().getTestClass();
        System.out.println(
                "Starting test in " + testClass.getSimpleName());
    }
}
~~~

This listener helps integrate reactions to test lifecycle milestones into Spring's event system. It differs from `ApplicationEventsTestExecutionListener`: `EventPublishingTestExecutionListener` publishes events describing the test lifecycle; `ApplicationEventsTestExecutionListener` supports recording application events published by the application for the test to query.

## 4. What Does Listener Order Affect?

The default order reflects dependencies between tasks. A web test needs the request context prepared early in the lifecycle. The test instance needs dependency injection before running checks. Transactions must be established at the right milestone so repository operations and SQL scripts join the proper transaction. When the test finishes, cleanup listeners run in reverse order to close resources that were opened.

You can visualize the preparation and teardown sequence as follows:

~~~text
Test preparation
    |
    v
ServletTestExecutionListener
    |
    v
DirtiesContextBeforeModesTestExecutionListener
    |
    v
ApplicationEventsTestExecutionListener
    |
    v
DependencyInjectionTestExecutionListener
    |
    v
DirtiesContextTestExecutionListener
    |
    v
TransactionalTestExecutionListener
    |
    v
SqlScriptsTestExecutionListener
    |
    v
EventPublishingTestExecutionListener
    |
    v
Test execution and end callbacks invoked in reverse order
~~~

The diagram shows listener ordering in Spring Framework 6.1; it does not mean every listener performs work in every test. A listener acts only when relevant conditions or annotations are met. For instance, the transaction listener does not open a transaction if the test lacks transaction configuration; the SQL listener does not run scripts if the test does not declare `@Sql`.

If a listener needs data prepared by another listener, registration order can determine the outcome. Therefore, when adding a custom listener, determine clearly which default listener its callbacks must run before or after. For ending callbacks, remember the invocation order is reversed.

## 5. Registering Default and Custom Listeners

Spring automatically discovers default listeners from the framework's registration mechanism. Normally, a test only needs to declare TestContext configuration and functional annotations such as `@Transactional`, `@Sql`, or `@RecordApplicationEvents`; manually listing each listener is unnecessary.

When you need to add a custom listener, use `@TestExecutionListeners`. The example below registers a listener to record test body execution time:

~~~java
import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public class TestTimingListener
        extends AbstractTestExecutionListener {

    private static final String START_TIME =
            TestTimingListener.class.getName() + ".START_TIME";

    @Override
    public void beforeTestExecution(TestContext testContext) {
        testContext.setAttribute(START_TIME, System.nanoTime());
    }

    @Override
    public void afterTestExecution(TestContext testContext) {
        Object value = testContext.removeAttribute(START_TIME);
        if (value instanceof Long startTime) {
            long elapsedNanos = System.nanoTime() - startTime;
            System.out.printf(
                    "%s.%s took %d ns%n",
                    testContext.getTestClass().getSimpleName(),
                    testContext.getTestMethod().getName(),
                    elapsedNanos);
        }
    }
}
~~~

You can attach the listener to a test class:

~~~java
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.TestExecutionListeners.MergeMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
@TestExecutionListeners(
        listeners = TestTimingListener.class,
        mergeMode = MergeMode.MERGE_WITH_DEFAULTS)
class TimedServiceTest {
    // Test methods have their execution time tracked.
}
~~~

The critical point is `mergeMode = MERGE_WITH_DEFAULTS`. When declaring a custom listener, using the default `REPLACE_DEFAULTS` mode can replace the default listener list. In that case, features such as test instance injection, transactions, or running `@Sql` may stop working as expected. `MERGE_WITH_DEFAULTS` preserves default listeners and appends the custom listener to the list.

`AbstractTestExecutionListener` provides empty implementations for callbacks, so a listener only needs to override the milestones it cares about. If ordering control is needed, implement `Ordered` or use `@Order`. Lower order values take precedence in starting callbacks; ending callbacks are invoked in reverse order.

Do not create a custom listener for behavior that already has a dedicated annotation or extension. Listeners fit best when integrating a shared rule into the TestContext lifecycle, such as collecting metrics, preparing specialized fixtures, or managing a resource shared across many tests.

## 6. Distinguishing Spring Framework Listeners from Spring Boot Extensions

Spring Boot builds on the Spring TestContext Framework and may add listeners to support its own testing features. For instance, mock bean features, mock resetting, REST Docs, or other testing tools can register additional listeners through their respective modules.

Hence, when inspecting a Boot project, the active listener list may be longer than Spring Framework 6.1's eight core listeners. This difference comes from the Spring version, Boot version, and testing dependencies present on the classpath.

Spring Framework 6.2 adds bean override infrastructure for tests, including annotations such as `@TestBean`, `@MockitoBean`, and `@MockitoSpyBean`; that version adds `BeanOverrideTestExecutionListener` to handle bean overriding. When checking the default list of a newer version, consult the exact documentation or source code for the version in use rather than blindly applying the 6.1 list.

If a test uses `@MockitoBean` to replace a bean in `ApplicationContext`, that is Spring TestContext's bean override mechanism in supported versions. Mockito's `@Mock` still only creates a mock inside the test instance; it does not automatically replace a bean in the context. Distinguishing these two mechanisms avoids cases where a test holds a mock while the Spring-injected service still receives the real bean.

## 7. When Should You Pay Attention to Each Listener?

Not every test needs to understand every listener in detail. You can start from the feature the test is using:

| Testing Need | Related Listener | What to Observe |
|---|---|---|
| Inject beans into the test class | DependencyInjectionTestExecutionListener | The test instance receives the right bean from the context |
| Test code depending on the current request | ServletTestExecutionListener | Request attributes and mock servlet objects are ready |
| Need a fresh context before/after tests | The two DirtiesContext... listeners | The context is evicted from the cache at the right time |
| Roll back data after tests | TransactionalTestExecutionListener | Test-managed transaction and rollback |
| Prepare or clean up SQL data | SqlScriptsTestExecutionListener | Scripts run in the right phase and transaction mode |
| Verify application events | ApplicationEventsTestExecutionListener | Events are recorded within the test scope |
| React to test lifecycle | EventPublishingTestExecutionListener | Lifecycle events are published to the Spring context |

When a feature does not work, check in sequence the enabling annotation, whether the context is the right type, whether the listener is in the active list, and whether callback order is appropriate. For example, `@Transactional` will not create a transaction if the context lacks a suitable transaction manager; `@Sql` cannot run scripts if no datasource is configured; `@RecordApplicationEvents` does not record events if test configuration does not enable the feature.

## 8. Some Principles When Working with Listeners

- Use default listeners when the feature is already supported by Spring via annotations such as `@Autowired`, `@Transactional`, `@Sql`, `@DirtiesContext`, or `@RecordApplicationEvents`.
- Keep track of the listener list per framework version; Spring Boot's list may include extensions from Boot and dependencies.
- Use `MERGE_WITH_DEFAULTS` when you only want to add a custom listener while keeping core TestContext functionality.
- Pick callbacks matching the exact milestone to handle: preparing the class, preparing the test instance, before method, before method body, or after method completion.
- Extend `AbstractTestExecutionListener` if you only need to override a few callbacks.
- Choose order deliberately when a listener depends on data or state produced by another listener.
- Avoid storing global mutable state inside listeners; prefer `TestContext` attributes or resources with clear lifecycles.
- Clean up resources in the matching ending callback and ensure cleanup tolerates cases where the test throws an exception.
- Use `@DirtiesContext` for changes affecting the context; use transactions or SQL cleanup for database data.
- When testing a Spring feature, choose an appropriate test scope. Pure Java unit tests do not need to create a TestContext if no Spring behavior needs verification.

Default listeners form the integration layer between the test lifecycle and Spring services. Knowing their order and responsibilities explains why a test receives injected beans, runs in a transaction, sees a mock request, or records events. When extension is needed, a custom listener can join that same mechanism, provided the default list and callback order are preserved appropriately for the testing goal.
