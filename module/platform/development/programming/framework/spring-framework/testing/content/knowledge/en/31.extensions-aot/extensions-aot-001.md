# `@TestExecutionListeners` and Merge Rules with Default Listeners

## 1. Role of `TestExecutionListener`

The Spring TestContext Framework provides `TestExecutionListener` to extend Spring's test lifecycle. A listener receives a `TestContext` and is invoked at points such as before/after the test class, when preparing the test instance, before/after a test method, or immediately before/after the test method body.

A listener can be used to perform common work across multiple tests, for example:

- Preparing data or state before a test method runs.
- Recording execution time, test class information, and test method information.
- Storing or reading metadata in `TestContext`.
- Integrating test resources with the Spring application context.
- Cleaning up resources after a test or after a test class.

`@TestExecutionListeners` is an annotation for registering `TestExecutionListener` implementations with `TestContextManager`. This annotation is commonly used alongside `@ContextConfiguration`, `@SpringJUnitConfig`, or other Spring testing annotations.

An important point when adding a listener is understanding how the annotation interacts with Spring's default listeners. If misconfigured, tests may lose capabilities that Spring automatically provides, such as dependency injection, transaction management, or `@DirtiesContext` handling.

## 2. Default Listeners of the Spring TestContext Framework

When a test uses the Spring TestContext Framework without explicitly declaring `@TestExecutionListeners`, Spring automatically registers a list of default listeners discovered through the `SpringFactoriesLoader` mechanism.

The default listeners handle common responsibilities, such as:

| Listener | Primary Role |
|---|---|
| `ServletTestExecutionListener` | Prepares the web request context for Servlet testing when an appropriate web configuration is present. |
| `DirtiesContextBeforeModesTestExecutionListener` | Handles `@DirtiesContext` modes that require marking the context before a test method or class. |
| `ApplicationEventsTestExecutionListener` | Records application events within the test scope when the application events feature is used. |
| `DependencyInjectionTestExecutionListener` | Performs dependency injection into the test instance, such as fields annotated with `@Autowired`. |
| `DirtiesContextTestExecutionListener` | Marks the application context as dirty according to the `@DirtiesContext` configuration. |
| `TransactionalTestExecutionListener` | Manages test-managed transactions for tests annotated with `@Transactional`. |
| `SqlScriptsTestExecutionListener` | Executes SQL scripts declared with `@Sql`. |
| `EventPublishingTestExecutionListener` | Publishes test lifecycle events so other components can listen to them. |
| `MockitoResetTestExecutionListener` | Resets Spring-managed mocks according to the corresponding reset configuration. |

The exact list depends on the Spring Framework version and the libraries present on the test classpath. Some listeners only operate when the corresponding application context type or feature is present. Therefore, the table above describes typical listeners in modern Spring versions, rather than an immutable list for all versions.

When using `@SpringBootTest`, `@WebMvcTest`, or test slice annotations, Spring still relies on the TestContext Framework. The default listeners required for Spring Test remain part of the test preparation and execution mechanism.

## 3. Registering a Custom Listener with `@TestExecutionListeners`

For example, suppose a test needs a listener that records the execution time of the test method body. You can create a listener by extending `AbstractTestExecutionListener` to override only the necessary callbacks:

```java
import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public class TestTimingListener extends AbstractTestExecutionListener {

    private static final String START_TIME =
            TestTimingListener.class.getName() + ".startTime";

    @Override
    public void beforeTestExecution(TestContext testContext) {
        testContext.setAttribute(START_TIME, System.nanoTime());
    }

    @Override
    public void afterTestExecution(TestContext testContext) {
        Object value = testContext.removeAttribute(START_TIME);
        if (value instanceof Long startTime) {
            long elapsedNanos = System.nanoTime() - startTime;
            System.getLogger(getClass().getName()).log(
                    System.Logger.Level.INFO,
                    "Test {0} took {1} ms",
                    testContext.getTestMethod().getName(),
                    elapsedNanos / 1_000_000);
        }
    }
}
```

`AbstractTestExecutionListener` provides empty implementations for callbacks, so a listener does not have to override every method. The example stores the start time using `TestContext.setAttribute(...)`, then retrieves and removes the value with `removeAttribute(...)`. This approach avoids using global variables to hold state across test methods.

Registering the listener for a test class:

```java
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
@TestExecutionListeners(
        listeners = TestTimingListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class OrderServiceTests {
    // Test methods of the class.
}
```

The example uses `MERGE_WITH_DEFAULTS` so that the custom listener is added alongside the default listeners. This is the typical approach when you only want to extend the test lifecycle while still needing standard Spring features.

## 4. Two Merge Modes: `REPLACE_DEFAULTS` and `MERGE_WITH_DEFAULTS`

`TestExecutionListeners.MergeMode` has two values:

| Mode | Behavior | When to Use |
|---|---|---|
| `REPLACE_DEFAULTS` | Replaces the default listener list with the listeners declared in the annotation (combined with inheritance rules if any). This is the default value of `mergeMode`. | Only when intentionally controlling the entire list of listeners to use and accepting responsibility for the replaced default capabilities. |
| `MERGE_WITH_DEFAULTS` | Merges the declared listeners with the default listener list discovered by Spring. | When wanting to add a custom listener while preserving standard Spring Test behavior. |

### `REPLACE_DEFAULTS`

If you write:

```java
@TestExecutionListeners(
        listeners = TestTimingListener.class
)
class OrderServiceTests {
}
```

`mergeMode` is not specified, so Spring uses `REPLACE_DEFAULTS`. The default list is no longer automatically retained just because the test class has this annotation.

The consequences can be:

- `@Autowired` fields in the test instance are not injected if `DependencyInjectionTestExecutionListener` is missing.
- Test-managed transactions are not started/ended as expected if `TransactionalTestExecutionListener` is missing.
- `@DirtiesContext` context refresh rules are not applied if the corresponding listener is missing.
- `@Sql` scripts may not execute if `SqlScriptsTestExecutionListener` is missing.

`REPLACE_DEFAULTS` does not mean Spring stops creating the application context or ignores Spring Test entirely. It only controls the list of registered `TestExecutionListener` instances. However, omitting listeners can significantly alter test behavior.

If you truly need to replace the default listeners, explicitly declare all the listeners the test requires:

```java
@TestExecutionListeners(
        listeners = {
                DependencyInjectionTestExecutionListener.class,
                DirtiesContextTestExecutionListener.class,
                TransactionalTestExecutionListener.class,
                TestTimingListener.class
        },
        mergeMode = TestExecutionListeners.MergeMode.REPLACE_DEFAULTS
)
class SpecializedInfrastructureTests {
}
```

The list above is only an abbreviated example. Tests using `@Sql`, web context, application events, Mockito reset, or other features may require adding the corresponding listeners. When replacing all defaults, you must base the list on the features actually used and the Spring version in use.

### `MERGE_WITH_DEFAULTS`

With:

```java
@TestExecutionListeners(
        listeners = TestTimingListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class OrderServiceTests {
}
```

Spring merges `TestTimingListener` with the default listeners. As a result, the test can both record timing and continue to use dependency injection, test transactions, `@Sql`, `@DirtiesContext`, and other default features where appropriate.

In most cases where you add a listener to a test class, `MERGE_WITH_DEFAULTS` is the right choice.

## 5. Distinguishing Merge from Listener Inheritance

`mergeMode` and `inheritListeners` control two different concerns:

- `mergeMode` determines whether Spring's default listener list is merged with the declared listeners or replaced.
- `inheritListeners` determines whether listeners declared on a superclass are inherited by subclasses.

`inheritListeners` defaults to `true`. When a test class extends a base test class annotated with `@TestExecutionListeners`, the listeners from the superclass are inherited according to the annotation's rules. You can set `inheritListeners = false` to prevent inheriting listeners from the superclass.

Example of a base class registering a shared listener:

```java
@TestExecutionListeners(
        listeners = BaseAuditListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
abstract class BaseIntegrationTests {
}
```

A subclass can add its own listener while still keeping inherited listeners:

```java
@TestExecutionListeners(
        listeners = TestTimingListener.class,
        inheritListeners = true,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class OrderIntegrationTests extends BaseIntegrationTests {
}
```

In this example, the subclass inherits the listener configuration from the base class while also declaring the timing listener. `MERGE_WITH_DEFAULTS` continues to request merging with Spring's default listeners.

If a subclass needs its own set of listeners and does not want to receive listeners from the base class:

```java
@TestExecutionListeners(
        listeners = IsolatedTestListener.class,
        inheritListeners = false,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class IsolatedRepositoryTests extends BaseIntegrationTests {
}
```

Here, `inheritListeners = false` only disables inheriting listeners from the superclass. Because `mergeMode` is still `MERGE_WITH_DEFAULTS`, Spring's default listeners are still merged into the list. Do not confuse these two attributes as a single option.

## 6. Listener Execution Order

Spring orders `TestExecutionListener` instances using its ordering mechanism. A listener can implement `Ordered` or use the `@Order` annotation to specify its order. Default listeners also have an order designed so that steps such as dependency injection and transaction management coordinate properly.

Example:

```java
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.test.context.support.AbstractTestExecutionListener;

@Order(Ordered.LOWEST_PRECEDENCE)
public class DiagnosticTestExecutionListener extends AbstractTestExecutionListener {
    // Record diagnostic information only.
}
```

Choose the order based on actual dependencies. For instance, a listener that needs to read beans injected into the test instance should not run before the listener responsible for dependency injection. A listener that needs to observe test transactions must be positioned appropriately relative to when the transaction listener begins or ends the transaction.

The callbacks have different timing semantics:

| Callback | Typical Timing | Used For |
|---|---|---|
| `beforeTestClass` | Before running the class's test methods | Preparing class-level resources. |
| `prepareTestInstance` | After creating the test instance and before the test method runs | Preparing or augmenting state on the test instance. |
| `beforeTestMethod` | Before the execution lifecycle of each test method | Preparing data or state for a method. |
| `beforeTestExecution` | Immediately before the test method body | Measuring method execution time or starting tracing. |
| `afterTestExecution` | Immediately after the test method body | Ending tracing or recording the method execution result. |
| `afterTestMethod` | After the test method lifecycle | Cleaning up state after a method. |
| `afterTestClass` | After the class's test methods finish | Releasing class-level resources. |

`beforeTestExecution` and `afterTestExecution` are useful when you want to measure only the test method body. If you need to measure fixture setup/teardown or the work of other callbacks as well, choose the callback that matches the time span you want to capture.

## 7. Using `TestContext` to Store Listener State

`TestContext` is the object Spring passes to a listener. It provides information about the test class, test instance, test method, application context, and an attribute store for listeners to hold state scoped to the test context.

Some common operations:

```java
testContext.getTestClass();
testContext.getTestInstance();
testContext.getTestMethod();
testContext.getApplicationContext();
testContext.setAttribute("my.key", value);
testContext.getAttribute("my.key");
testContext.removeAttribute("my.key");
```

Only call `getApplicationContext()` in callbacks where the test context already has an application context ready. You should not force the context to initialize early just for a listener to log or measure time, because doing so can increase overhead or alter the test's lazy loading behavior.

Name attributes with a dedicated namespace, for example using the listener's fully qualified name as a prefix, to avoid key collisions with other listeners. Clean up attributes after use, especially if the value holds references to the test instance, requests, or short-lived resources.

## 8. Registering a Default Listener Across the Entire Test Suite

If a listener needs to be applied broadly across many test classes, you can register it as a default listener via Spring's factories mechanism instead of repeating `@TestExecutionListeners` on every class.

In Spring TestContext configurations that use `SpringFactoriesLoader`, the `META-INF/spring.factories` file can declare:

```properties
org.springframework.test.context.TestExecutionListener=\
com.example.testing.TestTimingListener
```

Spring discovers this listener as a default listener alongside the other default listeners. You should verify the registration mechanism supported in your project's Spring Framework version and ensure the metadata file is in the right location on the test runtime classpath.

Global registration has broad scope: every matching test context may receive that listener. Therefore, a global listener should be general-purpose, low-overhead, and not depend on a bean or configuration that exists only in a single module. For behavior intended only for a subset of tests, an annotation on a base test class or test class is usually clearer.

## 9. Common Mistakes

| Symptom | Cause | Solution |
|---|---|---|
| `@Autowired` fields in the test instance become `null` | `@TestExecutionListeners` was declared using `REPLACE_DEFAULTS`, dropping `DependencyInjectionTestExecutionListener`. | Use `MERGE_WITH_DEFAULTS` or declare the dependency injection listener if intentionally replacing all defaults. |
| `@Transactional` tests do not roll back as expected | `TransactionalTestExecutionListener` is not registered. | Check `mergeMode` and the list of registered listeners. |
| `@Sql` does not run | `SqlScriptsTestExecutionListener` is missing after replacing defaults. | Keep defaults or declare the corresponding SQL listener. |
| `@DirtiesContext` does not mark the context | The listener handling `@DirtiesContext` was omitted from the list. | Use `MERGE_WITH_DEFAULTS` or register the required listeners. |
| Base class listener does not run in subclass | The subclass sets `inheritListeners = false` or declares inheritance configuration differently than intended. | Check `inheritListeners` and the test class inheritance hierarchy. |
| Listener runs in the wrong order | Listener ordering does not match dependencies between callbacks. | Use `Ordered` or `@Order`, and check interaction with default listener ordering. |
| Listener is not discovered globally | `spring.factories` has the wrong key, wrong location, or is not on the test runtime classpath. | Check metadata in `META-INF` and the factories mechanism of the Spring version in use. |
| Listener state leaks between tests | Data is stored in static fields or `TestContext` attributes are not cleaned up. | Store state per `TestContext`, use unique keys, and remove them when finished. |

## 10. Practical Selection Guidelines

When adding a `TestExecutionListener`, decide based on the scope of application:

1. Single test class only: declare `@TestExecutionListeners` on the class and usually choose `MERGE_WITH_DEFAULTS`.
2. A shared group of tests: place the annotation on an abstract base test class and leave `inheritListeners = true` if subclasses need to inherit it.
3. Entire test suite: consider registering a default listener via Spring factories, provided the listener does not depend on configuration specific to a single test.
4. Need to replace all default behavior: use `REPLACE_DEFAULTS` and actively declare every required listener; this is a specialized case.

In most situations, when the goal is simply to add logging, timing, metadata, or custom data preparation, keep the default listeners. That ensures tests continue to receive consistent behavior from the Spring TestContext Framework.

## 11. Conclusion

`@TestExecutionListeners` registers custom listeners into the Spring TestContext lifecycle. `mergeMode` determines whether custom listeners are merged with or replace the default listeners; `inheritListeners` determines whether configuration from a superclass is inherited. When only adding a listener, `MERGE_WITH_DEFAULTS` is usually the safe choice because it preserves dependency injection, test transactions, SQL scripts, and other standard features. Only use `REPLACE_DEFAULTS` when you truly want to manage the listener list yourself and understand which default behaviors must be re-registered.

## References

- [Spring Framework Reference — TestExecutionListener](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel.html)
- [Spring Framework Javadoc — `@TestExecutionListeners`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/TestExecutionListeners.html)
- [Spring Framework Javadoc — `TestExecutionListener`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/TestExecutionListener.html)
