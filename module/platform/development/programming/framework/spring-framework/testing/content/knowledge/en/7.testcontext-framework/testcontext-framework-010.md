# Relationship with JUnit 4 and TestNG Support in Legacy Code

The Spring TestContext Framework is designed to manage Spring's testing integration independently of any specific test framework. It provides mechanisms to create and reuse an `ApplicationContext`, prepare test instances, manage lifecycle events, and execute testing behaviors registered through `TestExecutionListener`.

JUnit Jupiter is the modern integration path via `SpringExtension`. In legacy systems, the same TestContext foundation can also be used with JUnit 4 and TestNG. The key distinction is that the core of Spring TestContext is shared, while how a test framework calls into that core is implemented by its respective adapter.

Understanding this boundary helps maintain legacy test suites, combine multiple test frameworks during migration phases, and plan a transition to JUnit Jupiter without rewriting all Spring configuration.

## 1. The TestContext Framework and Test Frameworks

A Spring application can have tests written across multiple test frameworks over different stages of development. For example, an older module uses JUnit 4, an integration test suite uses TestNG, and new code uses JUnit Jupiter.

The Spring TestContext Framework provides common components:

- **TestContextManager:** coordinates the test lifecycle and communicates with listeners.
- **TestContext:** holds information about the test class, test method, test instance, and application context.
- **TestExecutionListener:** performs behaviors before/after a test class or test method, such as dependency injection, transaction management, and processing test annotations.
- **Context cache:** reuses application contexts when tests have equivalent configuration.

Each test framework needs an appropriate lifecycle integration:

| Test Framework | Common Spring Integration Approach |
|---|---|
| JUnit Jupiter | `SpringExtension`, typically via `@ExtendWith` or a composed annotation |
| JUnit 4 | `SpringRunner` or the `SpringClassRule` and `SpringMethodRule` rules |
| TestNG | Base classes `AbstractTestNGSpringContextTests` and `AbstractTransactionalTestNGSpringContextTests` |

Overview diagram:

```text
                  Spring TestContext Framework
              TestContextManager / TestContext / Listeners
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
       JUnit Jupiter        JUnit 4           TestNG
       SpringExtension      SpringRunner      AbstractTestNG...
             |                |                |
             v                v                v
        JUnit Platform    JUnit 4 runner     TestNG lifecycle
```

Adapters feed each framework's events into the TestContext Framework. They do not turn JUnit 4, JUnit Jupiter, and TestNG into the same framework; each framework retains its own annotations, execution rules, and configuration style.

## 2. JUnit 4 Support with SpringRunner

In JUnit 4, Spring provides `SpringRunner`, an alias for `SpringJUnit4ClassRunner`. This runner connects the JUnit 4 lifecycle with the Spring TestContext Framework.

A test class can declare:

```java
import org.junit.Test;
import org.junit.runner.RunWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit4.SpringRunner;

import static org.junit.Assert.assertEquals;

@RunWith(SpringRunner.class)
@ContextConfiguration(classes = LegacyTestConfig.class)
public class LegacyGreetingTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    public void returnsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }
}
```

In this example:

1. `@RunWith(SpringRunner.class)` instructs JUnit 4 to use SpringRunner to execute the test class.
2. `@ContextConfiguration` specifies configuration sources to create the Spring test context.
3. Spring prepares the test instance and injects `GreetingService`.
4. JUnit 4 runs the method annotated with `@Test`.
5. Spring TestContext Framework coordinates the necessary listeners and callbacks around execution.

Annotations such as `@Autowired`, `@ContextConfiguration`, `@ActiveProfiles`, `@TestPropertySource`, `@DirtiesContext`, `@Transactional`, `@Rollback`, `@Commit`, and `@Sql` continue to work as supported by the Spring TestContext Framework. Specific configuration must still satisfy the requirements of each annotation and corresponding listener.

### SpringRunner and the Single-Runner Limit

JUnit 4 uses one runner per test class via `@RunWith`. If a class already needs another runner, you cannot declare an additional independent `@RunWith` for SpringRunner.

For example, a test class using another library's runner will conflict if you try adding `@RunWith(SpringRunner.class)`. In that case, Spring provides two rules to integrate TestContext while keeping the existing runner:

- `SpringClassRule` handles class-scoped events.
- `SpringMethodRule` handles method-scoped events and prepares the test instance.

## 3. Using SpringClassRule and SpringMethodRule When Another Runner Is Needed

If a JUnit 4 test class must use another runner, you can register the Spring rules:

```java
import org.junit.ClassRule;
import org.junit.Rule;
import org.junit.Test;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit4.rules.SpringClassRule;
import org.springframework.test.context.junit4.rules.SpringMethodRule;

@ContextConfiguration(classes = LegacyTestConfig.class)
public class LegacyRunnerTest {

    @ClassRule
    public static final SpringClassRule springClassRule =
            new SpringClassRule();

    @Rule
    public final SpringMethodRule springMethodRule =
            new SpringMethodRule();

    @Test
    public void runsWithSpringTestContext() {
        // Test uses Spring TestContext configuration and features.
    }
}
```

In this example, the test class does not declare `@RunWith(SpringRunner.class)`. The rules provide the Spring integration point within the JUnit 4 lifecycle. Another runner can still drive the test class as required by the library in use.

Both rules must be registered to cover class-level and method-level events. Adding only one rule is not equivalent to the full integration of SpringRunner.

Rules are a JUnit 4 API. You cannot copy `@ClassRule` and `@Rule` directly into a JUnit Jupiter test class and expect them to be handled the same way. When migrating to Jupiter, replace them with appropriate Jupiter extensions or APIs.

## 4. Spring Annotations That Still Work in JUnit 4 Tests

One advantage of the TestContext Framework is that many annotations describing configuration and test intent are not tied specifically to JUnit Jupiter. With the proper JUnit 4 adapter, legacy tests can continue using familiar Spring capabilities.

Example of testing a service with a profile and transaction:

```java
@RunWith(SpringRunner.class)
@ContextConfiguration(classes = LegacyPersistenceConfig.class)
@ActiveProfiles("test")
@Transactional
public class LegacyOrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    public void findsSavedOrder() {
        Order order = new Order("ORDER-42");

        orderRepository.save(order);

        assertEquals(
                "ORDER-42",
                orderRepository.findById("ORDER-42")
                        .orElseThrow()
                        .getId()
        );
    }
}
```

With test-managed transactions properly configured, Spring can start a transaction before the test and roll it back by default afterward. `@Commit` or `@Rollback(false)` can override rollback behavior when truly needed. An appropriate transaction manager and persistence configuration must exist; adding `@Transactional` alone does not create a database or schema for the test.

The key point is that the JUnit 4 runner supplies the lifecycle for Spring TestContext to apply those features. Rules for transactions, context caching, and listeners still belong to the Spring TestContext Framework.

## 5. TestNG Support via Spring Base Classes

TestNG has its own lifecycle with annotations such as `@BeforeClass`, `@BeforeMethod`, `@AfterMethod`, `@AfterClass`, `@Test`, and features like groups and DataProviders. Spring provides TestNG integration through base classes in the `org.springframework.test.context.testng` package.

The commonly used class is `AbstractTestNGSpringContextTests`. A test class extends this class to connect TestNG lifecycle milestones with the Spring TestContext Framework.

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.testng.AbstractTestNGSpringContextTests;
import org.testng.annotations.Test;

import static org.testng.Assert.assertEquals;

@ContextConfiguration(classes = LegacyTestConfig.class)
public class LegacyTestNgGreetingTest
        extends AbstractTestNGSpringContextTests {

    @Autowired
    private GreetingService greetingService;

    @Test
    public void returnsGreeting() {
        assertEquals(greetingService.greet("Lan"), "Hello, Lan");
    }
}
```

In this example:

1. TestNG recognizes methods annotated with `org.testng.annotations.Test`.
2. The Spring base class integrates TestNG with the TestContext Framework.
3. Spring creates or retrieves the context per configuration and prepares the test instance.
4. Dependencies are injected before the test method uses them.
5. Pre/post-test events are forwarded to Spring TestContext so listeners perform their corresponding work.

Unlike JUnit 4, the test class does not declare `@RunWith`. Unlike JUnit Jupiter, it also does not register `@ExtendWith(SpringExtension.class)`. The integration mechanism here is Spring's TestNG base class.

### Do Not Confuse TestNG Annotations with JUnit Annotations

Both frameworks can use identical annotation names, yet they belong to different packages and are handled differently by test runners:

| Purpose | JUnit 4 | TestNG |
|---|---|---|
| Test method | `org.junit.Test` | `org.testng.annotations.Test` |
| Before each method | `org.junit.Before` | `org.testng.annotations.BeforeMethod` |
| After each method | `org.junit.After` | `org.testng.annotations.AfterMethod` |
| Before class | `org.junit.BeforeClass` | `org.testng.annotations.BeforeClass` |
| After class | `org.junit.AfterClass` | `org.testng.annotations.AfterClass` |

Using the wrong import can prevent the intended runner from discovering the test or keep callbacks from running as expected. Check annotation packages when maintaining legacy tests, especially when the IDE adds imports automatically.

## 6. TestNG with Transaction Support

Spring provides `AbstractTransactionalTestNGSpringContextTests` for TestNG tests needing transaction support. This class extends Spring's TestNG TestContext integration and adds utilities for persistence/JDBC testing.

Example:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.testng.AbstractTransactionalTestNGSpringContextTests;
import org.springframework.transaction.annotation.Transactional;
import org.testng.annotations.Test;

import static org.testng.Assert.assertEquals;

@ContextConfiguration(classes = LegacyPersistenceConfig.class)
@Transactional
public class LegacyOrderTest
        extends AbstractTransactionalTestNGSpringContextTests {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    public void findsSavedOrder() {
        Order order = new Order("ORDER-42");

        orderRepository.save(order);

        assertEquals(
                orderRepository.findById("ORDER-42")
                        .orElseThrow()
                        .getId(),
                "ORDER-42"
        );
    }
}
```

The transactional base class provides test transaction support via Spring TestContext. Actual behavior also depends on the transaction manager and application configuration. With standard test-managed transactions, data changes are rolled back after the test unless configured to commit.

This transactional base class also exposes several JDBC utilities such as `jdbcTemplate` and SQL script execution methods, helpful in persistence tests. When using a JPA repository, you can inject the repository as shown; when direct SQL operations are needed, the JDBC utilities help prepare and verify data.

Do not assume every TestNG test needs the transactional base class. If a test only verifies service or controller logic, `AbstractTestNGSpringContextTests` is usually sufficient. Choose the transactional class only when the test's goal and configuration genuinely require transactions.

## 7. Different Lifecycles While Sharing TestContext

JUnit 4 and TestNG have different lifecycle extension points. Spring's adapters connect those points to shared TestContext Framework events.

| Need | JUnit 4 | TestNG |
|---|---|---|
| Preparing test instance | SpringRunner or Spring rules | Spring TestNG base class |
| Before test method | Runner/rule coordinated with TestContext | Base class TestNG callback |
| After test method | Runner/rule coordinated with TestContext | Base class TestNG callback |
| Before/after test class | Runner or SpringClassRule | Base class class-level callback |
| Dependency injection | TestContext listener | TestContext listener |
| Test-managed transaction | Spring transaction listener | Spring transaction listener |
| Context configuration | Spring TestContext annotations | Spring TestContext annotations |

Differences in lifecycle ordering can affect tests if they rely on state created inside `@Before`, `@BeforeMethod`, `@After`, or `@AfterMethod`. When switching frameworks, do not merely swap imports and assume every callback will run in the exact old order.

For example, TestNG allows configuring multiple groups and method dependency ordering. JUnit 4 has its own execution rules, while JUnit Jupiter has its own lifecycle and extension mechanism. The TestContext Framework can preserve most Spring configuration, yet cannot automatically translate semantics of annotations from older frameworks.

## 8. Spring Features That Can Be Retained in Legacy Code

When maintaining JUnit 4 or TestNG, most TestContext configuration can be retained as long as the corresponding adapter remains in use and configuration requirements are satisfied.

| Feature | Role in Test |
|---|---|
| `@ContextConfiguration` | Specifies configuration or sources to create the context |
| `@ActiveProfiles` | Selects profiles used in testing |
| `@TestPropertySource` | Adds property sources for tests |
| `@Autowired` | Injects beans into the test instance |
| `@DirtiesContext` | Marks the context for cache eviction |
| `@Transactional` | Enables test-managed transactions when supported by configuration |
| `@Rollback`, `@Commit` | Adjusts transaction completion behavior |
| `@Sql` | Runs SQL scripts along the test lifecycle |
| `@TestExecutionListeners` | Customizes the set of listeners participating in the test |

These annotations belong to the Spring TestContext ecosystem. How they are activated depends on whether the test framework is properly integrated and whether annotations are placed in appropriate scopes.

If a legacy test fails after changing runners or base classes, check both the adapter and configuration. Leaving `@Transactional` intact does not guarantee the transaction listener will run if the Spring TestContext lifecycle is not activated.

## 9. Maintaining JUnit 4, TestNG, and Jupiter in the Same Repository

In a long-lived codebase, migration can happen module by module or test group by test group. It is not necessary to migrate every test in a single pass.

You can organize according to these principles:

- JUnit 4 tests continue using `SpringRunner` or Spring rules.
- TestNG tests continue extending Spring TestNG base classes.
- JUnit Jupiter tests use `SpringExtension` or corresponding Spring Boot/JUnit Jupiter annotations.
- Each test is executed by the runner or engine matching the framework it uses.

This requires build configuration that recognizes each framework accurately. For instance, JUnit 4 can run directly via its runner or run on JUnit Platform through the JUnit Vintage Engine if the project configures that engine. TestNG is typically executed by its own TestNG provider/framework; the JUnit Vintage Engine is not an adapter for running TestNG.

With Gradle, a project may need separate test tasks or source sets depending on layout. One task using `useJUnitPlatform()` runs engines registered on JUnit Platform, such as Jupiter and Vintage. Another task using `useTestNG()` runs TestNG. Do not configure the same task as if these two mechanisms were one unified engine.

Illustrative example:

```groovy
dependencies {
    testImplementation "org.springframework:spring-test"

    // JUnit Jupiter
    testImplementation "org.junit.jupiter:junit-jupiter"

    // Only when JUnit 4 tests still run through JUnit Platform
    testImplementation "junit:junit"
    testRuntimeOnly "org.junit.vintage:junit-vintage-engine"

    // Only when TestNG tests still exist
    testImplementation "org.testng:testng"
}

tasks.test {
    useJUnitPlatform()
}

// Can create a separate TestNG task and restrict classes to run
tasks.register("testNgLegacy", Test) {
    useTestNG()
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
}
```

This is an illustrative example of separating execution mechanisms; dependency versions, plugins, source sets, and include/exclude patterns must match the real build. If the same test directory holds all three kinds of tests, configure class filtering or split source sets to avoid a task trying to run tests with the wrong framework.

In Maven, Surefire/Failsafe configuration and corresponding providers must also be checked against the frameworks actually on the classpath. Do not assume that merely adding dependencies causes all test frameworks to be discovered and executed as intended.

## 10. Points to Watch When Running TestNG in Parallel

TestNG supports parallel execution by method, class, instance, or suite depending on configuration. The Spring TestContext Framework caches shared contexts within the test process, so multiple tests can access a single `ApplicationContext` concurrently.

This does not mean all test state is automatically isolated. Pay attention to:

- Singleton beans in the context may be used by multiple tests concurrently.
- Shared database data may collide if tests insert the same identifiers.
- Test-managed transactions are bound to the executing thread; actions running on another thread may not join the test's transaction.
- Mutable fixtures placed in fields may be shared across methods depending on lifecycle and TestNG configuration.
- Tests depending on execution order or data created by an earlier test are hard to run reliably in parallel.

If parallel execution is enabled, design isolated data per test, avoid mutating shared singleton state, and control external resources. If tests are not thread-safe, configure appropriate suites or groups instead of expecting SpringExtension/TestContext to resolve all conflicts automatically.

## 11. Migration Path from JUnit 4 to JUnit Jupiter

When migrating JUnit 4 to Jupiter, most test intent and Spring configuration can be preserved while replacing the lifecycle integration layer.

| JUnit 4 | JUnit Jupiter |
|---|---|
| `@RunWith(SpringRunner.class)` | `@ExtendWith(SpringExtension.class)` or composed annotation |
| `org.junit.Test` | `org.junit.jupiter.api.Test` |
| `@Before` | `@BeforeEach` |
| `@After` | `@AfterEach` |
| `@BeforeClass` | `@BeforeAll` |
| `@AfterClass` | `@AfterAll` |
| `@Ignore` | `@Disabled` |
| `@Test(expected = ...)` | `assertThrows(...)` |
| `@Rule`, `@ClassRule` | Appropriate Jupiter extension or API |

A JUnit 4 test:

```java
@RunWith(SpringRunner.class)
@ContextConfiguration(classes = LegacyTestConfig.class)
public class LegacyGreetingTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    public void returnsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }
}
```

Can be migrated to Jupiter:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = LegacyTestConfig.class)
class GreetingTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void returnsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }
}
```

Or use `@SpringJUnitConfig(LegacyTestConfig.class)` to combine SpringExtension registration and context configuration. If the project already uses `@SpringBootTest` or test slices, the corresponding Spring Boot annotation already provides Jupiter integration.

During migration, review the following points:

1. Replace JUnit 4 annotation imports with the proper Jupiter package imports.
2. Convert lifecycle methods and check setup/cleanup ordering.
3. Convert rules to corresponding Jupiter extensions or APIs.
4. Convert `@Test(expected)` to `assertThrows` for explicit exception assertions.
5. Review parameterized tests, timeouts, and how tests are grouped.
6. Retain Spring TestContext annotations where their meaning remains valid.
7. Update build configuration to run Jupiter; keep Vintage temporarily if JUnit 4 tests remain.

Not every JUnit 4 Rule has a direct one-annotation replacement in Jupiter. Identify the behavior the rule provides, then select an extension, `@TempDir`, `@RegisterExtension`, or an appropriate mechanism.

## 12. Migration Path from TestNG to JUnit Jupiter

Migrating TestNG to Jupiter often requires closer inspection because TestNG has distinct features for suite organization, groups, data providers, and method dependencies.

| TestNG | Common Equivalent in Jupiter |
|---|---|
| `@Test` | `@Test` |
| `@BeforeMethod` | `@BeforeEach` |
| `@AfterMethod` | `@AfterEach` |
| `@BeforeClass` | `@BeforeAll` |
| `@AfterClass` | `@AfterAll` |
| `@DataProvider` | `@ParameterizedTest` combined with `@MethodSource`, `@CsvSource`, or other sources |
| TestNG groups | `@Tag` |
| `dependsOnMethods` | Redesign tests to be independent or turn the workflow into a focused test |
| TestNG listeners | Jupiter extensions or corresponding TestContext mechanisms |

Example of a TestNG test:

```java
@ContextConfiguration(classes = LegacyTestConfig.class)
public class LegacyGreetingTest
        extends AbstractTestNGSpringContextTests {

    @Autowired
    private GreetingService greetingService;

    @Test
    public void returnsGreeting() {
        assertEquals(greetingService.greet("Lan"), "Hello, Lan");
    }
}
```

After migrating to Jupiter, the TestNG base class can be removed in favor of SpringExtension:

```java
@SpringJUnitConfig(LegacyTestConfig.class)
class GreetingTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void returnsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }
}
```

TestContext annotations such as `@ContextConfiguration`, `@ActiveProfiles`, and `@Transactional` can be kept if the testing goal has not changed. What must change is how TestNG supplies the lifecycle and how tests are organized and executed.

In particular, TestNG's `dependsOnMethods` can hide coupling between tests. When moving to Jupiter, evaluate whether those methods can become independent tests with dedicated fixtures or whether the action sequence should become a single workflow verified in one test case.

## 13. Common Errors When Maintaining Legacy Code

| Symptom | Possible Cause | Resolution |
|---|---|---|
| JUnit 4 test cannot use Spring beans | Missing `@RunWith(SpringRunner.class)` or rules not fully registered | Check JUnit 4 adapter and context configuration |
| JUnit 4 class cannot add SpringRunner | Already using another runner | Use `SpringClassRule` and `SpringMethodRule` |
| TestNG fails to inject dependencies | Class does not extend Spring base class or context config missing | Check `AbstractTestNGSpringContextTests` and `@ContextConfiguration` |
| Test method not discovered | Using annotations from the wrong package | Check JUnit/TestNG imports and runner |
| JUnit 4 tests disappear after moving to JUnit Platform | Missing Vintage Engine or task lacks engine configuration | Check dependencies and test task |
| TestNG tests do not run in JUnit Platform task | Confusing TestNG with a default JUnit Platform engine | Configure a separate TestNG runner/task |
| Transaction does not roll back as expected | Missing transaction manager, annotation, or appropriate listener | Check transaction configuration and test integration |
| Tests produce different results under parallel execution | Shared state, data, or resources | Isolate fixtures and control concurrency |
| Tests fail after switching frameworks | Different lifecycle order or annotation semantics | Compare old and new callbacks, rewrite setup/cleanup |

When debugging, classify failures by layer:

- **Build/test runner layer:** is the test discovered and run by the intended framework?
- **Adapter layer:** are SpringRunner, Spring rules, or TestNG base classes activated?
- **TestContext layer:** is the context created, cached, and preparing the test instance properly?
- **Listener layer:** are dependency injection, transactions, or SQL scripts being processed?
- **Business layer:** does the test method receive the right data and verify the right behavior?

Categorizing by layer prevents editing service logic when the real issue is that the test runner never activated Spring.

## 14. How to Maintain Legacy Code During Transition

A repository can maintain multiple test frameworks for a period if boundaries are organized clearly:

1. Document which framework each test class uses.
2. Keep the matching adapter for classes not yet migrated.
3. Configure tasks/providers so each kind of test runs on the right framework.
4. Do not mix JUnit 4, Jupiter, and TestNG annotations in the same test class.
5. Migrate in small batches, starting with independent tests whose behavior is easy to verify.
6. After each batch, run tests on the new engine and confirm listeners/transactions/contexts behave as before.
7. Remove old runner or Vintage/TestNG dependencies only when no tests require them.

There is no need to migrate solely to change syntax. The value of migrating lies in unifying the testing platform, leveraging the extension API, parameterized tests, and Jupiter features while reducing the burden of maintaining multiple runners. If a legacy test suite remains stable and has high migration cost, it can stay on its current adapter while new code uses Jupiter.

The Spring TestContext Framework makes transition manageable because many configuration concepts and testing behaviors are shared. By understanding that SpringRunner, Spring rules, TestNG base classes, and SpringExtension are different ways of integrating into the same TestContext core, a development team can preserve legacy tests, intentionally run multiple frameworks, and gradually migrate to JUnit Jupiter while retaining the meaning of every test.

