# Lifecycle of @Test, @BeforeEach, @AfterEach, @BeforeAll, and @AfterAll

JUnit Jupiter provides annotations to mark test methods and define steps that must run before or after each test. Understanding this lifecycle properly helps prepare data consistently, release resources at the right time, and prevent the state of one test from affecting another.

The five annotations have related yet distinct roles:

- **@Test** marks a method as a test to execute.
- **@BeforeEach** runs before each corresponding test execution.
- **@AfterEach** runs after each corresponding test execution.
- **@BeforeAll** runs once before all tests in the class.
- **@AfterAll** runs once after all tests in the class complete.

These annotations belong to JUnit Jupiter's org.junit.jupiter.api package. They form the foundation for organizing tests in Java projects and Spring projects using JUnit 5.

## 1. General Lifecycle of a Test Class

For a class with multiple @Test methods, the general order is:

~~~text
@BeforeAll
    |
    +-- @BeforeEach
    |       |
    |       +-- First @Test
    |       |
    |     @AfterEach
    |
    +-- @BeforeEach
    |       |
    |       +-- Second @Test
    |       |
    |     @AfterEach
    |
    +-- ... remaining tests ...
    |
@AfterAll
~~~

For example, a class with two tests goes through the following steps:

1. JUnit creates a test instance according to the configured lifecycle mode.
2. @BeforeAll methods execute once.
3. Before the first test, @BeforeEach methods execute.
4. The first @Test method runs.
5. @AfterEach methods execute.
6. The BeforeEach → Test → AfterEach cycle repeats for the second test.
7. After all tests in the class finish, @AfterAll methods execute.

By default, JUnit does not guarantee whether the first test or the second test in the example above runs first. What is guaranteed is that the corresponding lifecycle callbacks are placed before and after each respective test execution.

### Observing the Order with a Small Example

~~~java
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class LifecycleExampleTest {

    @BeforeAll
    static void beforeAll() {
        System.out.println("BeforeAll");
    }

    @BeforeEach
    void beforeEach() {
        System.out.println("BeforeEach");
    }

    @Test
    void firstTest() {
        System.out.println("firstTest");
    }

    @Test
    void secondTest() {
        System.out.println("secondTest");
    }

    @AfterEach
    void afterEach() {
        System.out.println("AfterEach");
    }

    @AfterAll
    static void afterAll() {
        System.out.println("AfterAll");
    }
}
~~~

One possible run output looks like this:

~~~text
BeforeAll
BeforeEach
secondTest
AfterEach
BeforeEach
firstTest
AfterEach
AfterAll
~~~

Which test name appears first may vary. Even if the order of the two tests differs, BeforeAll still runs once at the start of the class, each test still gets BeforeEach and AfterEach, and AfterAll runs at the end.

## 2. @Test: Marking a Test Method

@Test tells JUnit which method should be executed as a test. A test typically verifies a specific behavior by preparing inputs, invoking the component under test, and asserting the expected outcome.

Example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class CalculatorTest {

    @Test
    void addsTwoNumbers() {
        Calculator calculator = new Calculator();

        int result = calculator.add(2, 3);

        assertEquals(5, result);
    }
}
~~~

The addsTwoNumbers method is discovered and executed by JUnit. The assertion confirms that the actual result equals 5.

Several important rules:

- @Test methods must not be declared private or static.
- Methods normally return void.
- Methods may have package-private visibility; public is not required.
- Methods may accept parameters if an appropriate ParameterResolver supplies those values.
- @Test does not prepare data on its own, clean up resources on its own, or guarantee that external state is reset between tests.

In JUnit Jupiter, if you need to check for an exception, use an assertion such as assertThrows. Do not use the expected attribute on the @Test annotation as was common in JUnit 4.

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

@Test
void rejectsNegativeQuantity() {
    assertThrows(
            IllegalArgumentException.class,
            () -> orderService.createOrder(-1)
    );
}
~~~

## 3. @BeforeEach: Preparing Before Each Test

@BeforeEach marks a method that must run before each corresponding test method. This is the right place to create fresh fixtures, instantiate objects under test, prepare dedicated data, or reset mocks to the required state.

Example:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ShoppingCartTest {

    private ShoppingCart cart;

    @BeforeEach
    void setUp() {
        cart = new ShoppingCart();
    }

    @Test
    void newCartIsEmpty() {
        assertTrue(cart.isEmpty());
    }

    @Test
    void cartCanContainAnItem() {
        cart.add(new Item("keyboard", 1));

        assertTrue(cart.contains("keyboard"));
    }
}
~~~

Each test starts with a fresh ShoppingCart. The test that adds an item does not alter the fixture used by the other test.

@BeforeEach is commonly used to:

- Create objects and fake dependencies for testing.
- Prepare input data for a scenario.
- Initialize mocks or configure mock behavior.
- Set up temporary directories, temporary files, or resources used only within a single test.
- Reset fixture state to a predictable initial state.

Avoid putting every preparation step into an overly large setup method. When each test requires different conditions, keep scenario-specific data inside the test or extract clearly named helper methods. The more readable the setup is, the easier maintainers can understand why the test expects a given result.

### How Many Times Does @BeforeEach Run?

For standard @Test methods, @BeforeEach runs once before each test method. It is also applied to each execution of test template types such as @RepeatedTest and @ParameterizedTest.

For instance, if a @ParameterizedTest has four argument sets, the setup runs for each invocation. Each invocation is treated as a separate test execution.

## 4. @AfterEach: Cleaning Up After Each Test

@AfterEach marks a method that runs after each corresponding test execution. It is commonly used to close resources, delete temporary files, stop a test-only server, or restore state modified by the test.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class FileWriterTest {

    private Path temporaryFile;

    @BeforeEach
    void createTemporaryFile() throws IOException {
        temporaryFile = Files.createTempFile("writer-test-", ".txt");
    }

    @Test
    void writesContentToFile() throws IOException {
        Files.writeString(temporaryFile, "JUnit Jupiter");

        String content = Files.readString(temporaryFile);

        org.junit.jupiter.api.Assertions.assertEquals(
                "JUnit Jupiter", content);
    }

    @AfterEach
    void deleteTemporaryFile() throws IOException {
        if (temporaryFile != null) {
            Files.deleteIfExists(temporaryFile);
        }
    }
}
~~~

Cleaning up inside @AfterEach ensures resources are released even when an assertion in the test fails. Cleanup methods should tolerate incomplete setup state, such as checking for null before closing or deleting a resource.

If a @BeforeEach method fails, the corresponding test method and subsequent setup methods will not run. @AfterEach callbacks still execute so they have an opportunity to clean up any resources already created. Therefore, cleanup should remain safe when only part of the setup completed.

### When Is @AfterEach Needed?

Use @AfterEach when a test creates or modifies resources that must be reclaimed after each run:

- Closing streams, sockets, clients, or connections opened by the test itself.
- Stopping a local server started specifically for the test.
- Deleting temporary files or directories.
- Unregistering subscriptions or listeners.
- Restoring system properties, simulated environment variables, or shared state modified by the test.

For plain Java objects that only exist inside the test instance and hold no external resources, manual cleanup is often unnecessary. The garbage collector manages memory lifecycle. Reserve @AfterEach for side effects that must be explicitly reclaimed.

## 5. @BeforeAll: Preparing Once for the Entire Class

@BeforeAll marks a method that runs once before tests in the test class execute. This annotation suits resources that are expensive to initialize and can be safely shared across the test class, such as a test server or read-only reference data.

By default, a @BeforeAll method must be static. The reason is that JUnit creates a separate test instance for each test method by default; thus, at the time BeforeAll runs, JUnit does not pick a specific instance on which to invoke an instance method.

~~~java
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class SharedResourceTest {

    @BeforeAll
    static void startSharedResource() {
        System.out.println("Start shared resource once");
    }

    @Test
    void firstScenario() {
        // Use the shared resource.
    }

    @Test
    void secondScenario() {
        // Continue using the shared resource.
    }
}
~~~

@BeforeAll runs only once per class, whether the class has one or many test methods. If a class has multiple tests, BeforeAll does not re-initialize shared resources before each test; that is a different responsibility from BeforeEach.

Some appropriate use cases:

- Starting a mock/stub server shared across the class.
- Creating an immutable reference dataset.
- Initializing an expensive resource that multiple tests can safely use.
- Checking or preparing a shared environment before tests begin.

Do not use BeforeAll to create state that one test might mutate and a subsequent test depends on. If data must remain independent between tests, create or restore it in BeforeEach.

## 6. @AfterAll: Releasing Shared Resources

@AfterAll marks a method that runs once after all tests in the class have finished. This is the right place to release resources created in @BeforeAll.

By default, an @AfterAll method must be static.

~~~java
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class SharedResourceTest {

    @BeforeAll
    static void startSharedResource() {
        System.out.println("Start shared resource");
    }

    @Test
    void scenarioA() {
        // Verify behavior A.
    }

    @Test
    void scenarioB() {
        // Verify behavior B.
    }

    @AfterAll
    static void stopSharedResource() {
        System.out.println("Stop shared resource");
    }
}
~~~

The @BeforeAll and @AfterAll pair should be designed together: whatever resource is created once needs a corresponding release point. If initialization fails partway through, the release method should also check whether the resource was actually created before closing it.

Do not put per-test data cleanup in @AfterAll. Cleaning up only at the end of the class allows one test to see data left behind by a previously executed test. For per-run data, use @AfterEach or an appropriate framework rollback mechanism.

## 7. Static Rules and Test Class Instance Lifecycle

An important aspect of JUnit Jupiter is the lifecycle of the test object. This lifecycle determines how many instances are created and whether BeforeAll/AfterAll methods can be instance methods.

### Default: PER_METHOD

JUnit Jupiter uses TestInstance.Lifecycle.PER_METHOD by default. JUnit creates a new instance of the test class for each test method.

Consequences:

- Instance fields of the test class are re-initialized for each test method.
- One test mutating an instance field does not change the instance field for another test method.
- Static fields remain shared across tests.
- External resources such as databases, files, system properties, or servers can still be shared even though a new test instance is created.

Example:

~~~java
class CounterTest {

    private int count = 0;

    @Test
    void incrementsCounter() {
        count++;
        org.junit.jupiter.api.Assertions.assertEquals(1, count);
    }

    @Test
    void counterStartsAtZero() {
        org.junit.jupiter.api.Assertions.assertEquals(0, count);
    }
}
~~~

With PER_METHOD, the two test methods receive two separate instances. Therefore, mutating the count field in the first test does not make the second test start with value 1.

### Switching to PER_CLASS

You can configure a single shared instance for the entire test class using @TestInstance(TestInstance.Lifecycle.PER_CLASS):

~~~java
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class PerClassLifecycleTest {

    private String sharedValue;

    @BeforeAll
    void initializeOnce() {
        sharedValue = "initialized";
    }

    @Test
    void firstTest() {
        org.junit.jupiter.api.Assertions.assertEquals(
                "initialized", sharedValue);
    }

    @Test
    void secondTest() {
        org.junit.jupiter.api.Assertions.assertEquals(
                "initialized", sharedValue);
    }
}
~~~

When using PER_CLASS:

- JUnit creates only one instance for the entire test class.
- @BeforeAll and @AfterAll can be instance methods, without needing static.
- Instance fields are shared among test methods.
- State mutated in one test can affect another test if not reset.
- If parallel execution is enabled, multiple tests mutating shared state concurrently can cause race conditions.

PER_CLASS is useful when instance methods are needed for BeforeAll/AfterAll or when there is a clear reason to share a fixture. Still, proactively reset state in BeforeEach and avoid letting test execution order dictate outcomes.

A global default can be set in junit-platform.properties:

~~~properties
junit.jupiter.testinstance.lifecycle.default = per_class
~~~

Changing the global default can affect many test classes. If only one class needs PER_CLASS, placing @TestInstance directly on that class makes the intent easier to see.

### Comparing the Two Modes

| Characteristic | PER_METHOD (default) | PER_CLASS |
|---|---|---|
| Number of instances | One instance per test method | One instance for the entire class |
| Instance fields | Re-initialized per test method | Shared across tests |
| Default @BeforeAll | static | Can be an instance method |
| Default @AfterAll | static | Can be an instance method |
| Risk of state leak via instance fields | Lower | Higher if not reset |
| Best suited when | Independent tests and separate fixtures are needed | Instance lifecycle or intentional state sharing is needed |

Regardless of the mode used, static fields, databases, filesystems, and external services can still create shared state. PER_METHOD does not automatically isolate the entire test execution environment.

## 8. Rules for Declaring Lifecycle Methods

Methods annotated with @BeforeEach, @AfterEach, @BeforeAll, and @AfterAll must obey JUnit Jupiter's rules:

- Must return void.
- Must not be declared private.
- May be declared package-private, protected, or public.
- May declare throws if setup or cleanup operations throw checked exceptions.
- May accept parameters if a supporting ParameterResolver is available.
- @BeforeEach and @AfterEach are instance methods.
- @BeforeAll and @AfterAll are static by default, unless the test class uses PER_CLASS.

JUnit also provides built-in parameters such as TestInfo and TestReporter. Example:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestInfo;

class UserServiceTest {

    @BeforeEach
    void prepare(TestInfo testInfo) {
        System.out.println(
                "Preparing: " + testInfo.getDisplayName());
    }
}
~~~

TestInfo can provide the display name, method name, and tag information of the current test. This mechanism is helpful when logging test information without manually managing global variables.

## 9. Lifecycle Ordering with Inheritance and @Nested

JUnit Jupiter supports test classes inheriting from a superclass and nested test classes via @Nested. Lifecycle callbacks follow rules so setup and cleanup occur in a logical order.

### Inheriting from a Superclass

If both superclass and subclass declare lifecycle methods:

- @BeforeAll in the superclass runs before @BeforeAll in the subclass.
- @BeforeEach in the superclass runs before @BeforeEach in the subclass.
- @AfterEach in the subclass runs before @AfterEach in the superclass.
- @AfterAll in the subclass runs before @AfterAll in the superclass.

This rule lets the parent class prepare common fixtures first while the child class adds specific fixtures. At teardown, the child class releases its own resources before the parent class releases shared ones.

~~~java
abstract class BaseServiceTest {

    @BeforeEach
    void prepareBaseFixture() {
        System.out.println("Base setup");
    }

    @AfterEach
    void cleanBaseFixture() {
        System.out.println("Base cleanup");
    }
}

class PaymentServiceTest extends BaseServiceTest {

    @BeforeEach
    void preparePaymentFixture() {
        System.out.println("Payment setup");
    }

    @AfterEach
    void cleanPaymentFixture() {
        System.out.println("Payment cleanup");
    }

    @Test
    void processesPayment() {
        // Verify payment behavior.
    }
}
~~~

With the test above, the setup order is Base setup followed by Payment setup. The cleanup order is Payment cleanup followed by Base cleanup.

### Using @Nested

A @Nested class groups related tests together, often to describe states or scenarios of the same subject.

The outer class lifecycle still applies to tests inside the nested class. For each test in a nested class, outer class setup runs before nested class setup; nested class cleanup runs before outer class cleanup.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class OrderServiceTest {

    @BeforeEach
    void prepareOrderService() {
        System.out.println("Outer setup");
    }

    @Nested
    class WhenOrderIsPaid {

        @BeforeEach
        void preparePaidOrder() {
            System.out.println("Nested setup");
        }

        @Test
        void cannotCancelPaidOrder() {
            // Verify cancellation rule for paid orders.
        }
    }
}
~~~

If you need to declare @BeforeAll or @AfterAll in a nested test class, use the PER_CLASS lifecycle on the nested class per JUnit Jupiter rules. This allows nested class callbacks to be instance methods.

### Multiple Lifecycle Methods in the Same Class

You can declare multiple methods annotated with @BeforeEach or @AfterEach. JUnit has a deterministic ordering mechanism, but ordering among methods of the same kind within a class is intentionally designed not to encourage reliance on an obvious order such as alphabetical order.

Do not write tests where setupA must run before setupB solely because of method names or declaration order. If two steps depend on each other, invoke them in the proper sequence from a single setup method or encapsulate them in a clearly named helper method.

## 10. Do Not Depend on Test Execution Order

JUnit Jupiter does not guarantee that test methods will execute in the order written in the file. By default, ordering is determined by a deterministic yet intentionally non-obvious algorithm.

A good test design should ensure:

- Every test can run independently.
- A test does not require another test to run first to create data.
- A test's result does not depend on field values left behind by another test.
- A test produces consistent results whether run individually or as part of the full test suite.

JUnit provides @TestMethodOrder and @Order to specify order when genuinely needed. However, if test A must run before test B so B has data, consider combining the two steps into an explicit scenario or creating a dedicated fixture for B. Using test ordering to hide dependencies often makes a suite hard to parallelize and hard to diagnose when failures occur.

## 11. Lifecycle with @ParameterizedTest, @RepeatedTest, and @TestFactory

Beyond @Test, JUnit Jupiter offers other test types. Understanding how the lifecycle applies avoids false assumptions about setup and cleanup counts.

### @ParameterizedTest

A parameterized test runs the same method with multiple argument sets. Each invocation has its corresponding setup and cleanup lifecycle.

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class UsernameValidatorTest {

    private UsernameValidator validator;

    @BeforeEach
    void setUp() {
        validator = new UsernameValidator();
    }

    @ParameterizedTest
    @ValueSource(strings = {"alice", "bob", "carol"})
    void acceptsValidUsernames(String username) {
        assertTrue(validator.isValid(username));
    }
}
~~~

With three values in ValueSource, the test method executes three times and setup runs for each invocation.

### @RepeatedTest

@RepeatedTest runs a test method multiple times for a specified number of repetitions. BeforeEach and AfterEach execute around each repetition.

~~~java
@RepeatedTest(3)
void generatesUniqueIdentifier() {
    String id = identifierGenerator.nextId();

    assertNotNull(id);
}
~~~

Each repetition can use TestInfo or RepetitionInfo to obtain information about the current repetition. Avoid letting an earlier repetition mutate state that a later repetition relies upon, unless the goal of the test is explicitly to verify a stateful sequence of operations.

### @TestFactory and Dynamic Tests

@TestFactory is a method that produces dynamic tests. An important difference is that @BeforeEach and @AfterEach wrap the factory method, rather than running separately around each dynamic test generated by that factory.

~~~java
import java.util.stream.Stream;

import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;

class DynamicNumberTest {

    @TestFactory
    Stream<DynamicTest> positiveNumbersAreAccepted() {
        return Stream.of(1, 2, 3)
                .map(number -> DynamicTest.dynamicTest(
                        "accepts " + number,
                        () -> org.junit.jupiter.api.Assertions
                                .assertTrue(number > 0)
                ));
    }
}
~~~

If each dynamic test needs a fresh fixture or individual cleanup, create and release the fixture directly inside the dynamic test's executable, or use an appropriate extension/resource management mechanism. Do not assume each dynamic test automatically receives a BeforeEach/AfterEach cycle like an independent @Test method.

## 12. Using Lifecycle Callbacks in Spring Tests

The Spring TestContext Framework integrates with JUnit Jupiter through SpringExtension. Spring test annotations such as @SpringBootTest, @WebMvcTest, and @DataJpaTest already integrate SpringExtension. For test classes using Spring Framework configuration directly, you can register the extension with @ExtendWith(SpringExtension.class) or use an appropriate configuration annotation such as @SpringJUnitConfig.

SpringExtension connects the JUnit lifecycle with test instance preparation, dependency injection, and Spring TestContext callbacks.

Example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class GreetingServiceIntegrationTest {

    @Autowired
    private GreetingService greetingService;

    private String input;

    @BeforeEach
    void prepareInput() {
        input = "Ada";
    }

    @Test
    void returnsGreetingForUser() {
        assertEquals("Hello, Ada", greetingService.greet(input));
    }
}
~~~

In this example, Spring prepares the test instance and injects GreetingService. The @BeforeEach method can use the injected dependency to prepare data for the test.

### Using @BeforeAll in Spring Tests

By default, @BeforeAll is static and therefore cannot access instance fields such as dependencies injected with @Autowired. There are two ways to handle this depending on intent:

- If the callback only needs to operate on static resources or data independent of the test instance, keep the method static.
- If you genuinely need to use instance fields in BeforeAll/AfterAll, configure the test class with @TestInstance(TestInstance.Lifecycle.PER_CLASS) so the callback can be an instance method.

Example:

~~~java
@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class SharedSpringFixtureTest {

    @Autowired
    private ReferenceDataService referenceDataService;

    @BeforeAll
    void prepareReferenceData() {
        referenceDataService.initializeReadOnlyData();
    }

    @Test
    void usesReferenceData() {
        // Verify behavior using reference data.
    }
}
~~~

With PER_CLASS, the test instance is created and Spring has the opportunity to prepare the instance before class-level callbacks run. Even so, only use shared data when it is stable and will not be unexpectedly modified by tests. Per-test data should still be prepared in BeforeEach.

### Relationship with Spring Test Transactions

When a Spring test method is annotated with @Transactional and managed by TestContext transactions, Spring typically starts a transaction for the test and rolls it back after the test completes. This helps isolate data changes in many persistence tests.

A few points to keep in mind:

- @BeforeEach is the right place to prepare data belonging to each test transaction.
- @AfterEach can perform cleanup within the same test method scope.
- @BeforeAll and @AfterAll are class-level callbacks and do not execute inside each test method's individual transaction.
- Transaction rollback does not automatically undo side effects outside the database, such as sent emails, written files, or requests sent to external services.
- If a test commits a transaction or uses a different transaction mechanism, understand its impact on shared data.

Do not assume that simply using PER_METHOD refreshes all database data automatically. JUnit's instance lifecycle and Spring's transaction lifecycle are two separate mechanisms. Choose the right isolation mechanism for each kind of state.

## 13. Common Mistakes and How to Handle Them

### Using @BeforeAll but Forgetting static

With the default PER_METHOD lifecycle, an instance @BeforeAll method is invalid. Declare it static or switch the class to PER_CLASS when there is a valid reason to use instance callbacks.

### Using @AfterAll to Clean Up Per-Test Data

If each test creates its own data, waiting until the end of the class to delete it can allow subsequent tests to read stale data. Use @AfterEach or transaction rollback on a per-test basis.

### Sharing Mutable Fields in PER_CLASS

If one test adds an element to a shared list, the next test may receive the modified list. Create a fresh fixture in BeforeEach, clear state after the test, or use immutable data.

### Assuming Tests Always Run in Declaration Order

Tests may execute in a different order. If a test only passes when another test runs first, eliminate that dependency with an isolated fixture or a clearly structured scenario.

### Creating Resources in BeforeEach Without Closing Them in AfterEach

Creating servers, streams, or files in every test without releasing them causes resources to accumulate, slowing down tests or causing intermittent failures. Pair creation and release points within the same lifecycle scope.

### Using BeforeAll for Mutable Data

Data created once and shared can cause tests to interfere with one another. Only share immutable data or data with a reliable reset process.

### Assuming @AfterEach Only Runs When the Test Passes

Cleanup is still invoked when a test fails and may also run after partial setup failure. Write defensive cleanup that checks state so secondary errors do not mask the original cause.

### Putting Too Much Logic into Lifecycle Methods

A massive setup method makes it hard for readers to tell what the test is actually verifying. Keep only steps shared across multiple tests inside lifecycle methods; scenario-specific data and primary actions belong inside the corresponding test.

## 14. Choosing the Right Annotation for Each Need

| Need | Suitable Annotation | Scope |
|---|---|---|
| Mark a behavior to verify | @Test | Single test method |
| Create a fresh fixture or reset state before a test | @BeforeEach | Per test execution |
| Close resources or clean up data after a test | @AfterEach | Per test execution |
| Initialize a shared resource for the whole class | @BeforeAll | Once per test class |
| Release a class-wide shared resource | @AfterAll | Once per test class |
| Run the same test with multiple data sets | @ParameterizedTest | One invocation per argument set |
| Repeat the same test multiple times | @RepeatedTest | One invocation per repetition |
| Generate dynamic tests from runtime data | @TestFactory | One factory invocation; dynamic nodes have their own lifecycle |

You can use the following questions to choose the right place for code:

1. Is this a system behavior that needs verification? If yes, place it in a @Test method.
2. Does this step need to re-run so every test has an independent initial state? If yes, use @BeforeEach.
3. Does this resource need to be released immediately after each test? If yes, use @AfterEach.
4. Can the resource be created once and safely shared across the class? If yes, consider @BeforeAll.
5. Does that shared resource need to be closed when the class finishes? If yes, use @AfterAll.
6. Does the class-level callback need access to instance fields? If yes, consider PER_CLASS and evaluate the impact of shared state.

## Conclusion

@Test identifies test methods; @BeforeEach and @AfterEach manage per-execution preparation and cleanup; @BeforeAll and @AfterAll manage class-scoped resources. The default PER_METHOD mode gives tests separate instances, while PER_CLASS allows sharing an instance and using non-static class-level callbacks. In Spring projects, SpringExtension connects the JUnit lifecycle with dependency injection and TestContext, while transactions and external state still require their own management mechanisms. Placing each operation in the right lifecycle scope makes tests more independent, reduces resource leaks, and improves maintainability.
