# Listener Ordering and Before/After Callback Symmetry

The Spring TestContext Framework allows extending the test lifecycle through `TestExecutionListener`. A listener can prepare data before a test, record results after a test, manage transactions, inject dependencies, or integrate additional test infrastructure. When multiple listeners participate together, callback order directly affects how resources are prepared, used, and released.

Spring guarantees an important rule: **before** callbacks are invoked in the order the listeners are registered, whereas **after** callbacks are invoked in reverse order. This is wrapping behavior, similar to how nested layers open and close resources in a stack-like fashion. An earlier listener can open a scope for a later listener; upon completion, the later listener closes its scope first, and only then does the earlier listener close the outer scope.

Understanding this ordering helps you write custom listeners that are compatible with Spring's default listeners, especially when tests use transactions, SQL scripts, context lifecycle, or resources requiring cleanup.

## 1. `TestExecutionListener` and `TestContextManager`

`TestExecutionListener` is an interface in `org.springframework.test.context`. It receives test lifecycle events through `TestContextManager`. A listener is not a JUnit extension replacing Spring; it is an extension point inside the Spring TestContext Framework.

`TestContextManager` manages the `TestContext` of a test class and coordinates listeners at defined points. `TestContext` provides information about the test class, test instance, test method, application context, and any exception from the current execution.

Some responsibilities commonly implemented via listeners:

- Preparing mock servlet request/response for web tests.
- Injecting dependencies into the test instance.
- Starting or ending test transactions.
- Running SQL scripts before or after a test method.
- Refreshing or marking an application context for removal from the cache.
- Logging, timing, or collecting diagnostic data.
- Integrating the resource lifecycle of a testing library.

The callbacks in `TestExecutionListener` have empty default implementations. Therefore, a custom listener can extend `AbstractTestExecutionListener` and override only the required callbacks.

## 2. Callbacks in the Test Lifecycle

`TestExecutionListener` defines the following main callbacks:

| Callback | When Invoked | Typical Responsibilities |
| --- | --- | --- |
| `beforeTestClass(TestContext)` | Before `@BeforeAll` callbacks of the testing framework. | Preparing class-level resources. |
| `prepareTestInstance(TestContext)` | After creating the test instance, before method setup callbacks. | Processing the test instance or preparing data needed for the instance. |
| `beforeTestMethod(TestContext)` | Before `@BeforeEach` callbacks and before the test method. | Preparing state for a single test method. |
| `beforeTestExecution(TestContext)` | Immediately before executing the test method, after setup such as `@BeforeEach`. | Measuring time or recording the start of the test body. |
| `afterTestExecution(TestContext)` | Immediately after the test method body, before teardown such as `@AfterEach`. | Measuring method execution time or collecting results immediately after the method. |
| `afterTestMethod(TestContext)` | After `@AfterEach` callbacks of the testing framework. | Cleanup that needs to run after test method teardown. |
| `afterTestClass(TestContext)` | After `@AfterAll` callbacks of the testing framework. | Releasing class-level resources. |

With JUnit Jupiter integrated via `SpringExtension`, the general sequence is as follows:

```text
Test class starts
    |
    v
beforeTestClass
    |
    v
@BeforeAll
    |
    v
Create test instance
    |
    v
prepareTestInstance
    |
    v
beforeTestMethod
    |
    v
@BeforeEach
    |
    v
beforeTestExecution
    |
    v
Test method
    |
    v
afterTestExecution
    |
    v
@AfterEach
    |
    v
afterTestMethod
    |
    v
@AfterAll
    |
    v
afterTestClass
```

The diagram illustrates the order at a high level. Other JUnit extensions may participate in their own lifecycle, but Spring TestContext hooks are placed at the corresponding boundaries shown above.

`prepareTestInstance` has no symmetric callback named `afterPrepareTestInstance`. The callback pairs that represent opening/closing a scope are `beforeTestClass`/`afterTestClass`, `beforeTestMethod`/`afterTestMethod`, and `beforeTestExecution`/`afterTestExecution`.

## 3. Ordering Rule: Forward for Before, Reverse for After

Suppose three listeners are registered in the order `ListenerA`, `ListenerB`, `ListenerC`.

When starting a lifecycle phase, `before` callbacks are invoked in registration order:

```text
ListenerA.before...
    ListenerB.before...
        ListenerC.before...
            Test / wrapped execution
```

When ending the phase, `after` callbacks are invoked in reverse order:

```text
            ListenerC.after...
        ListenerB.after...
    ListenerA.after...
```

You can picture listener A wrapping B, and B wrapping C. A opens its resource first; B opens its resource next; C opens its resource last. When closing, C releases first, then B, and finally A. This rule prevents an outer resource from being closed while an inner resource still needs to use it.

Spring documentation calls this **wrapping behavior**. If A is registered before B:

- Every `before` callback of A is called before B's `before` callback.
- A's `after` callback is called after B's `after` callback.

This is the ordering rule between listeners for the same lifecycle phase. It does not mean every `before...` callback always runs before every `after...` callback of another listener; each callback is still invoked at its own point in the test lifecycle.

## 4. Ordering Example with Two Listeners

We can create logging listeners to observe the order:

```java
public class FirstListener extends AbstractTestExecutionListener {

    @Override
    public void beforeTestMethod(TestContext testContext) {
        System.out.println("A beforeTestMethod");
    }

    @Override
    public void afterTestMethod(TestContext testContext) {
        System.out.println("A afterTestMethod");
    }
}

public class SecondListener extends AbstractTestExecutionListener {

    @Override
    public void beforeTestMethod(TestContext testContext) {
        System.out.println("B beforeTestMethod");
    }

    @Override
    public void afterTestMethod(TestContext testContext) {
        System.out.println("B afterTestMethod");
    }
}
```

If A is registered before B, the expected log order is:

```text
A beforeTestMethod
B beforeTestMethod
... test method and framework lifecycle ...
B afterTestMethod
A afterTestMethod
```

What matters is not the specific log output, but the symmetry: `before` callbacks open scopes in the order A then B; `after` callbacks close scopes B then A.

## 5. Why Does Spring Need Wrapping Behavior?

Listeners often depend on resources managed by another listener. One example in Spring is `TransactionalTestExecutionListener` and `SqlScriptsTestExecutionListener`.

`TransactionalTestExecutionListener` manages test transactions. `SqlScriptsTestExecutionListener` executes SQL scripts declared with `@Sql`. Spring registers the SQL listener after the transaction listener so that scripts can run inside the transaction managed by the transaction listener.

The sequence can be pictured as:

```text
TransactionalTestExecutionListener.before...
    Start transaction
    |
    v
SqlScriptsTestExecutionListener.before...
    Run SQL setup within transaction
    |
    v
Test method
    |
    v
SqlScriptsTestExecutionListener.after...
    Run SQL teardown within transaction if configured
    |
    v
TransactionalTestExecutionListener.after...
    Commit or roll back per test configuration
```

The SQL listener needs to run after the transaction has started. Conversely, its SQL cleanup needs to run before the transaction listener completes the transaction. If the `after` order were not reversed, the transaction could end before the SQL teardown executes.

This is why listener ordering is not just for sorting logs. It defines the resource scopes that other listeners can use.

## 6. Registering Custom Listeners with `@TestExecutionListeners`

For listeners used only in a single test class or a group of classes, you can register them explicitly:

```java
@SpringJUnitConfig(TestConfig.class)
@TestExecutionListeners(
        listeners = {
                FirstListener.class,
                SecondListener.class
        },
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class ListenerOrderTest {

    @Test
    void shouldRunWithCustomListeners() {
        // Test body.
    }
}
```

`MERGE_WITH_DEFAULTS` instructs Spring to keep the default listeners and merge the custom listeners into the list. This is usually the right choice when you want to add a listener to a test while still needing dependency injection, transactions, servlet mocks, or other default features.

If you declare `@TestExecutionListeners` without choosing a merge mode, the default is `REPLACE_DEFAULTS`. In that case, the default listener list may be replaced by the declared list, causing features like dependency injection or transactions to stop working as before. Only replace defaults when you truly want to manage the entire listener list yourself.

`inheritListeners` allows listener configuration to be inherited along the test class hierarchy. When a superclass contains `@TestExecutionListeners`, you must explicitly decide whether to inherit those listeners. If overriding the configuration, consider both `inheritListeners` and `mergeMode` to avoid accidentally losing necessary listeners.

## 7. Setting Order with `Ordered` or `@Order`

Listeners discovered by default by Spring are sorted using `AnnotationAwareOrderComparator`. You can declare the order by implementing `Ordered` or adding the `@Order` annotation.

Example using `Ordered`:

```java
public class AuditTestExecutionListener
        extends AbstractTestExecutionListener
        implements Ordered {

    @Override
    public int getOrder() {
        return 500;
    }

    @Override
    public void beforeTestMethod(TestContext testContext) {
        // Record information before test method.
    }

    @Override
    public void afterTestMethod(TestContext testContext) {
        // Record information after test method.
    }
}
```

Or using `@Order`:

```java
@Order(500)
public class AuditTestExecutionListener
        extends AbstractTestExecutionListener {
    // Required callbacks.
}
```

A smaller order value takes precedence earlier in the list. Therefore, a listener with order `500` is called before a listener with order `1000` on `before` callbacks, and is called after the `1000` listener on `after` callbacks.

When a listener needs to run inside another listener, place it after the outer listener. When a resource needs to be prepared first for other listeners, place the resource-managing listener at an earlier position. Choose order values deliberately and avoid relying on unspecified ordering among listeners with the same order.

### Illustrating Order and Wrapping

Suppose:

| Listener | Order |
| --- | ---: |
| `OuterListener` | 100 |
| `AuditListener` | 500 |
| `InnerListener` | 900 |

Callback order:

```text
before: Outer(100) -> Audit(500) -> Inner(900)
after:  Inner(900) -> Audit(500) -> Outer(100)
```

If `OuterListener` opens a transaction or resource scope and `InnerListener` executes SQL needing that transaction, the order above allows the SQL to run within the transaction scope.

## 8. Combining Custom Listeners with Default Listeners

Spring provides many default `TestExecutionListener` implementations, such as listeners for servlet mocks, dependency injection, transactions, SQL scripts, application events, bean overrides, and resetting Mockito mocks. The specific list varies by Spring version and the modules on the classpath.

Do not copy a fixed order list from one version and treat it as a contract for all versions. Consult the Javadoc and documentation of the Spring version you are using, and depend only on the ordering relationships your application actually needs.

When adding a custom listener, you should normally merge with defaults:

```java
@TestExecutionListeners(
        listeners = AuditTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
```

If a listener needs to be used broadly across many modules or test suites, it can be registered as a default listener through Spring Test's `SpringFactoriesLoader` mechanism. Default registration must follow the metadata mechanism and Spring version in use. A self-registered listener needs a public no-arg constructor so Spring can instantiate it.

For a custom listener serving only a single test class, registering via annotation is usually easier to understand and limits the blast radius.

## 9. Writing Listeners with Symmetric Before and After Callbacks

A listener often opens a resource in a `before` callback and closes the corresponding resource in an `after` callback. Example of a listener that times a test method:

```java
public class TimingTestExecutionListener
        extends AbstractTestExecutionListener {

    private static final String START_TIME =
            TimingTestExecutionListener.class.getName() + ".START_TIME";

    @Override
    public void beforeTestExecution(TestContext testContext) {
        testContext.setAttribute(START_TIME, System.nanoTime());
    }

    @Override
    public void afterTestExecution(TestContext testContext) {
        Long start = (Long) testContext.removeAttribute(START_TIME);
        if (start != null) {
            long elapsedNanos = System.nanoTime() - start;
            System.out.println("Test duration: " + elapsedNanos + " ns");
        }
    }
}
```

The listener stores the start time in `TestContext` and removes the attribute when done. `TestContext` is the appropriate place to store state tied to a test execution rather than using a static mutable map shared across the entire JVM.

The `beforeTestExecution` and `afterTestExecution` callbacks wrap the test method body. Hence the measured time excludes `@BeforeEach` and `@AfterEach`. If you want to include per-method setup and teardown as well, use the `beforeTestMethod` and `afterTestMethod` pair.

For resources requiring cleanup, ensure the `after` callback can release resources even when the test method fails. Do not clean up only on the success path. Spring TestContext provides information about exceptions in `TestContext`, so the listener can inspect the test status for appropriate logging or cleanup.

## 10. Distinguishing Callback Pairs by Scope

Do not choose callbacks solely based on their before/after names. Look at which part of the test lifecycle the listener needs to wrap.

| Need | Callbacks to Consider | Wrapped Scope |
| --- | --- | --- |
| Prepare resources used for the entire test class | `beforeTestClass` / `afterTestClass` | The entire class, including all methods in the class. |
| Prepare before each test method and clean up after teardown | `beforeTestMethod` / `afterTestMethod` | Setup method, test method, and teardown method. |
| Measure or observe only the test method body | `beforeTestExecution` / `afterTestExecution` | Only the test method execution. |
| Inject or post-process the test instance | `prepareTestInstance` | After the instance is created, before method setup. No symmetric `after` callback. |

For example, if a listener opens a transaction before `@BeforeEach`, the appropriate callback is usually `beforeTestMethod`; if you only want to start a timer right before assertions/test logic, use `beforeTestExecution`.

## 11. Callback Order When a Listener Throws an Exception

Listener callbacks are part of the test infrastructure. If an `after` callback throws an exception, Spring TestContext still attempts to invoke the remaining `after` listeners; the first exception is rethrown and subsequent exceptions may be attached as suppressed exceptions. This ensures cleanup in other listeners still has a chance to run.

Therefore:

- `after` callbacks should clean up safely when called after a failed test.
- Do not let a single cleanup error prevent other resources from being released.
- When multiple cleanup steps are needed within the same listener, use `try/finally` to ensure subsequent steps still execute.
- Preserve the original test exception in diagnostic information; avoid replacing it with a contextless cleanup error.

Example:

```java
@Override
public void afterTestMethod(TestContext testContext) {
    try {
        closeTemporarySession(testContext);
    }
    finally {
        removeTemporaryState(testContext);
    }
}
```

Do not assume an `after` callback only runs when the test succeeds. Cleanup should be designed to handle cases where the test method throws an exception as well.

## 12. Relationship with the JUnit Lifecycle and Framework Limitations

`TestExecutionListener` belongs to the Spring TestContext Framework, while `@BeforeEach`, `@AfterEach`, `@BeforeAll`, and `@AfterAll` belong to JUnit Jupiter. Spring integrates the two lifecycle systems via `SpringExtension`.

This means listener callbacks and JUnit lifecycle methods are two distinct hook layers:

- `beforeTestMethod` runs before `@BeforeEach`.
- `beforeTestExecution` runs after `@BeforeEach` and immediately before the test method.
- `afterTestExecution` runs immediately after the test method and before `@AfterEach`.
- `afterTestMethod` runs after `@AfterEach`.

Do not use listeners to replace every `@BeforeEach` or `@AfterEach`. Listeners are suitable when integrating at the `TestContext` level, applying across multiple test classes, or coordinating with other listeners. JUnit lifecycle methods are suitable for local setup/teardown of a test class.

Not every testing framework adapter supports all callbacks. For example, some JUnit 4 setups using `SpringMethodRule` do not support `beforeTestExecution` and `afterTestExecution`. When choosing a callback, verify support in the framework integration being used.

## 13. Listener Order in Tests with Transactions and SQL Scripts

Consider a test using `@Transactional` and `@Sql`:

```java
@SpringJUnitConfig(DatabaseTestConfig.class)
@Transactional
@Sql(
        scripts = "/sql/insert-person.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
        scripts = "/sql/delete-person.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
class PersonSqlTest {

    @Test
    void shouldReadPersonInsertedBySqlScript() {
        // Read data prepared by the SQL script.
    }
}
```

`TransactionalTestExecutionListener` and `SqlScriptsTestExecutionListener` coordinate thanks to registration order and wrapping behavior. The transaction listener opens the transaction first; the SQL listener runs setup scripts inside that transaction. On the `after` side, the SQL listener is invoked before the transaction listener, so teardown scripts can run in the same transaction before the transaction ends.

For test transactions that roll back by default, setup scripts and test operations can be rolled back together with the transaction. Exact behavior also depends on `@SqlConfig`, the transaction manager, and execution phase configuration. Do not infer that every SQL script is always rolled back if the script is configured to run outside a transaction or uses a different transaction mode.

## 14. AOT and Custom Listeners

Ahead-of-Time processing can affect how the application or test context is prepared, but it does not change the wrapping semantics of listener ordering: `TestContextManager` still coordinates callbacks according to the configured listener list.

When tests run in an environment with AOT processing or a native image, custom listeners and the classes they use must be present on the test runtime and instantiable by the mechanism supported in that environment. If a listener is registered via metadata, ensure the metadata is packaged and discovery works in the corresponding build/run environment. With native/AOT tests, do not rely arbitrarily on classpath scanning or dynamic reflection without verifying the application's runtime hints requirements.

Listener ordering should be declared explicitly with `Ordered` or `@Order` when order matters. Do not rely on accidental classpath order or metadata file order to establish critical dependencies.

## 15. Common Mistakes When Configuring Listeners

**Assuming `after` callbacks run in the same direction as `before` callbacks.**

Spring uses wrapping behavior: `before` in registration order, `after` in reverse order. Design listeners on an open-first, close-last model.

**Setting order opposite to resource dependencies.**

A listener that needs to open a transaction or resource scope must come before listeners that use it. Listeners using the resource will clean up before the listener managing the resource closes it.

**Registering a custom listener and accidentally replacing defaults.**

`@TestExecutionListeners` defaults to `REPLACE_DEFAULTS`. If you need to retain dependency injection, transactions, and default listeners, choose `MERGE_WITH_DEFAULTS`.

**Using the same order for multiple listeners and relying on accidental ordering.**

If ordering relationships matter, declare explicit order values and do not depend on unguaranteed ordering among listeners sharing the same order.

**Using `beforeTestMethod` to measure only test method time.**

This callback runs before `@BeforeEach`. If you want to exclude setup time from the measurement, use `beforeTestExecution` and `afterTestExecution`.

**Cleaning up only when the test succeeds.**

`after` callbacks must be designed for cases where the test throws an exception as well. Use `try/finally` to guarantee cleanup inside the listener.

**Using a global listener for logic belonging to a single test.**

Default listeners are applied broadly and can affect many test classes. If only a small group needs it, register via `@TestExecutionListeners` at the appropriate scope.

## 16. Process for Designing and Verifying Listener Order

When creating a custom listener, you can follow these steps:

1. Identify the callback matching the scope: class, method setup/teardown, or test body alone.
2. Identify which listeners need to run earlier and which listeners need to use their resources.
3. Set `Ordered` or `@Order` to establish a clear list.
4. Register the listener with `@TestExecutionListeners`; use `MERGE_WITH_DEFAULTS` if default listeners are still needed.
5. Override `before` callbacks to prepare state or open resources.
6. Override the corresponding `after` callbacks to clean up in reverse order.
7. Use `TestContext` to store execution-scoped state, avoiding static mutable state.
8. Test with logging listeners or ordering assertions in a small test scope.
9. Test the failing test method case as well to ensure cleanup callbacks still handle resources.
10. If using a JUnit adapter or AOT/native environment, verify that the callbacks and listener discovery are supported in that configuration.

## Conclusion

`TestExecutionListener` extends the test lifecycle via `TestContextManager`. Spring guarantees wrapping behavior: `before` callbacks run in listener registration order, and `after` callbacks run in reverse order. This rule allows listeners to open resource scopes in nested order and close them safely in a stack-like manner.

Choose the right callback pair for the scope you need to wrap, set order with `Ordered` or `@Order`, and use `MERGE_WITH_DEFAULTS` when adding custom listeners while still needing Spring's default listeners. Designing `after` callbacks to clean up even when tests fail will keep your test infrastructure stable and extensible.

References: [Spring Framework Reference — TestExecutionListener Configuration](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel-config.html) and [TestExecutionListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/TestExecutionListener.html).
