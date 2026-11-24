# @Mock, @InjectMocks, and Initialization via MockitoExtension

## 1. Three Components Solving Three Different Tasks

In Java 17+/Spring Boot testing with JUnit Jupiter, we often want to test **the real logic of a service** without calling a real database, network, or notification system. Mockito helps replace those **external dependencies of the service** with test doubles (mocks) whose behavior we can control.

Three core tools:

- **`@Mock`** (Mockito): creates a mock for a dependency, such as a repository, client, or notification interface. You define what the mock returns using stubbing and can verify which calls it received.
- **`@InjectMocks`** (Mockito): instantiates or uses the **real object under test** (system under test, SUT) and attempts to pass declared mocks/spies into its dependencies. This annotation **does not turn the SUT into a mock**.
- **`@ExtendWith(MockitoExtension.class)`** (JUnit Jupiter + Mockito): integrates Mockito into the JUnit 5 lifecycle to automatically initialize/inject Mockito-annotated fields, manage the session, and check stubbing under appropriate strictness.

An easy way to visualize it:

~~~text
JUnit Jupiter runs the test
        |
        v
MockitoExtension initializes @Mock fields
        |
        v
@InjectMocks constructs/prepares the REAL service
        |                          |
        +---- StockPort mock ------+
        +---- ReceiptPort mock ----+
        |
        v
@Test invokes the real service
        |
        +--> mock returns stubbed results
        +--> assertions check output
        +--> verify checks important interactions
~~~

Without `MockitoExtension` or an equivalent Mockito initialization mechanism, `@Mock` fields may remain unassigned, resulting in `null`. Simply declaring `@Mock` without configuring behavior does **not automatically simulate real business behavior**.

## 2. @Mock: Creating Fake Dependencies and Controlling Behavior

Suppose a service calls an inventory access interface:

~~~java
public interface StockPort {
    boolean reserve(String sku, int quantity);
}
~~~

In a test class using `MockitoExtension`:

~~~java
@Mock
StockPort stockPort;
~~~

Mockito creates a fake implementation of `StockPort`. When the test calls `stockPort.reserve(...)`, by default **no real inventory logic runs**. For methods returning `boolean`, an unstubbed mock returns `false` under the usual default answer. For many other types, default values can be `0`, `null`, an empty collection, or another appropriate value depending on the version/API.

To describe a specific scenario, declare **stubbing**:

~~~java
when(stockPort.reserve("SKU-1", 2)).thenReturn(true);
~~~

Meaning: when the mock receives the exact call `reserve("SKU-1", 2)`, it returns `true`. This is a **test rule**, not real inventory state. After calling the SUT, you can verify the interaction:

~~~java
verify(stockPort).reserve("SKU-1", 2);
~~~

`verify(...)` checks **once** by default for a call matching the arguments; if the contract requires another count, use `times(n)` or `never()`.

Comparison table:

| Task | Tool | Example |
| --- | --- | --- |
| Create a fake dependency | `@Mock` | `@Mock StockPort stockPort;` |
| Define the mock's return value | `when(...).thenReturn(...)` | Return `true` when in stock |
| Invoke real business logic | Method on the SUT | `service.reserve(...)` |
| Verify the returned result | JUnit assertion | `assertTrue(accepted)` |
| Verify a dependency was called | Mockito `verify` | Called with the right SKU and quantity |
| Verify a dependency was not called | `verifyNoInteractions` or `verify(..., never())` | Do not send confirmation when out of stock |

**Do not equate stubbing with assertion.** `when(...).thenReturn(...)` only sets up initial conditions. Whether a test PASSES or FAILS must be determined by assertions, verifications, and runner checks.

## 3. @InjectMocks: The Real SUT Receives Created Mocks

Consider a service receiving two dependencies through its constructor:

~~~java
public ReservationService(StockPort stockPort, ReceiptPort receiptPort) {
    this.stockPort = stockPort;
    this.receiptPort = receiptPort;
}
~~~

In the test:

~~~java
@Mock
StockPort stockPort;

@Mock
ReceiptPort receiptPort;

@InjectMocks
ReservationService service;
~~~

After Mockito initializes the annotations, `service` is an **instance of `ReservationService`**, while `stockPort` and `receiptPort` inside the service reference the corresponding mocks. When we call `service.reserve(...)`, the real Java logic of the service executes; outgoing calls to dependencies are controlled by Mockito.

### How Does Mockito Choose an Injection Strategy?

According to the `@InjectMocks` specification, Mockito tries strategies in order:

1. **Constructor injection**: selects a suitable constructor per Mockito's rules (preferring the largest constructor) and looks up matching mocks/spies for its parameters.
2. **Setter/property injection**: when needed and applicable, looks for setters/properties by type; in some cases with multiple dependencies of the same type, it further distinguishes by name.
3. **Field injection**: can inject into fields by type/name if prior strategies do not complete and the case is supported.

If constructor injection creates the object successfully, Mockito does not continue trying the remaining strategies just to inject every other field. **Mockito does not guarantee catching all missing dependencies.** For some constructors, missing dependencies may be passed as `null`; for unmockable dependencies or incompatible types, injection may not occur. Therefore:

- Prefer explicit **constructor injection** in application code and mark required dependencies `final`.
- Consider `Objects.requireNonNull(...)` in constructors so missing dependencies fail fast.
- Do not treat `@InjectMocks` as a full dependency injection framework or proof that every field was assigned.
- Do not expect Mockito to automatically build a nested dependency tree: each dependency needing a mock/spy or real instance must be provided explicitly.

`@InjectMocks` **is not `@Autowired`**. It does not look up Spring beans, open an `ApplicationContext`, read `application.yml`, or start a server or database connection.

## 4. MockitoExtension: Who Initializes the Annotations?

With JUnit Jupiter, integration is registered via annotation:

~~~java
@ExtendWith(MockitoExtension.class)
class ReservationServiceTest {
    @Mock
    StockPort stockPort;

    @Mock
    ReceiptPort receiptPort;

    @InjectMocks
    ReservationService service;
}
~~~

JUnit invokes the extension through the test lifecycle. `MockitoExtension` sets up the needed mocks and injections before the `@Test` body executes, coordinates with `@BeforeEach`, and finishes the Mockito session after each test invocation. When the extension is registered, **do not** also call `MockitoAnnotations.openMocks(this)` for the same class.

The right imports are:

~~~java
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
~~~

The three annotations belong to different packages: `@ExtendWith` is in JUnit Jupiter; `@Mock` and `@InjectMocks` are in Mockito; `MockitoExtension` is the bridge from the `mockito-junit-jupiter` artifact.

### Difference from JUnit 4

`@RunWith(MockitoJUnitRunner.class)` is the JUnit 4 approach. In a JUnit Jupiter `@Test` class, use `@ExtendWith(MockitoExtension.class)`, and do not mix `@RunWith`/`@Before`/`org.junit.Test` with `org.junit.jupiter.api.Test` unless you have a specific compatibility purpose.

## 5. Complete Example: Testing a Service with Two Dependencies

Suppose the **item reservation** feature has these rules:

- The SKU must be non-blank and the quantity must be positive.
- The service asks the stock port whether the requested quantity can be reserved.
- If stock is insufficient, return `false` and **do not send** a confirmation.
- If stock is available, send a confirmation for the reservation and return `true`.

We want to test those exact rules **without accessing a real inventory store or sending real notifications**.

### 5.1. Dependency Interfaces

**File `src/main/java/com/example/testing/StockPort.java`:**

~~~java
package com.example.testing;

public interface StockPort {
    boolean reserve(String sku, int quantity);
}
~~~

**File `src/main/java/com/example/testing/ReceiptPort.java`:**

~~~java
package com.example.testing;

public interface ReceiptPort {
    void send(String sku, int quantity);
}
~~~

The two interfaces form the boundary between business logic and external systems. In a real application, Spring bean adapters can call a database/HTTP/email service; in this unit test, Mockito replaces the adapters with mocks.

### 5.2. Real Class Under Test

**File `src/main/java/com/example/testing/ReservationService.java`:**

~~~java
package com.example.testing;

import java.util.Objects;

public final class ReservationService {
    private final StockPort stockPort;
    private final ReceiptPort receiptPort;

    public ReservationService(StockPort stockPort, ReceiptPort receiptPort) {
        this.stockPort = Objects.requireNonNull(stockPort, "stockPort");
        this.receiptPort = Objects.requireNonNull(receiptPort, "receiptPort");
    }

    public boolean reserve(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        if (!stockPort.reserve(sku, quantity)) {
            return false;
        }

        receiptPort.send(sku, quantity);
        return true;
    }
}
~~~

No `@Service` annotation is needed for JUnit to run this example; it is plain Java. In real Spring Boot, you can add `@Service` and let Spring manage the instance at runtime. Unit tests only care about the real class's behavior, so a Spring context is not required.

### 5.3. JUnit Jupiter Class Using @Mock, @InjectMocks, and MockitoExtension

**File `src/test/java/com/example/testing/ReservationServiceTest.java`:**

~~~java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ReservationServiceTest {
    @Mock
    StockPort stockPort;

    @Mock
    ReceiptPort receiptPort;

    @InjectMocks
    ReservationService service;

    @Test
    void reserve_whenStockIsAvailable_returnsTrueAndSendsReceipt() {
        // Arrange: simulate dependency accepting reservation of 2 items.
        when(stockPort.reserve("SKU-1", 2)).thenReturn(true);

        // Act: invoke the service's REAL LOGIC.
        boolean accepted = service.reserve("SKU-1", 2);

        // Assert: result and important interactions.
        assertTrue(accepted);
        verify(stockPort).reserve("SKU-1", 2);
        verify(receiptPort).send("SKU-1", 2);
    }

    @Test
    void reserve_whenStockIsInsufficient_returnsFalseWithoutReceipt() {
        // Arrange: stock rejects.
        when(stockPort.reserve("SKU-1", 2)).thenReturn(false);

        // Act
        boolean accepted = service.reserve("SKU-1", 2);

        // Assert: do not send confirmation when out of stock.
        assertFalse(accepted);
        verify(stockPort).reserve("SKU-1", 2);
        verifyNoInteractions(receiptPort);
    }

    @Test
    void reserve_whenQuantityIsZero_throwsBeforeCallingDependencies() {
        // No stub: parameters are validated before using dependencies.
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> service.reserve("SKU-1", 0)
        );

        assertEquals("Quantity must be positive", error.getMessage());
        verifyNoInteractions(stockPort, receiptPort);
    }

    @Test
    void reserve_whenSkuIsBlank_throwsBeforeCallingDependencies() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> service.reserve("  ", 2)
        );

        assertEquals("SKU must not be blank", error.getMessage());
        verifyNoInteractions(stockPort, receiptPort);
    }
}
~~~

Each test has its own scenario, fresh mocks from the `MockitoExtension` session, and stubs only the calls that will actually occur. In the in-stock test, we verify **both the return value and that confirmation was requested**. In the out-of-stock test, `verifyNoInteractions(receiptPort)` ensures the service does not mistakenly request sending a confirmation.

The zero-quantity test **must not** stub `stockPort.reserve(...)` because the service must throw before that call. Adding unused stubbing can trigger warnings/errors under `MockitoExtension` with strict stubs.

### 5.4. Gradle Configuration and Running

In a **Spring Boot 3.x project using Gradle Groovy DSL** that already has the Spring Boot plugin, repositories, and Java 17+, the relevant dependency/test task configuration is:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` in standard Spring Boot 3.x provides JUnit Jupiter, Mockito core, and the Mockito JUnit Jupiter integration. If a Java project **does not use the Spring Boot starter**, you must declare JUnit Jupiter and `org.mockito:mockito-junit-jupiter` separately with compatible versions, along with Mockito core if not already pulled in.

Run from the directory containing the Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.testing.ReservationServiceTest"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.testing.ReservationServiceTest"
~~~

With the four Java files as shown and valid dependencies, all four tests will pass when assertions and verifications hold. Because the example contains no `System.out.println`, **there is no fixed stdout printed by the code itself**. Gradle displays task status and results depending on log/IDE configuration.

In this test, `@InjectMocks` automatically instantiates `ReservationService` via its two-argument constructor. The two arguments receive the `StockPort` and `ReceiptPort` mocks declared in the test class.

## 6. When to Use @InjectMocks vs. Calling new Directly?

`@InjectMocks` keeps test classes concise when dependencies are simple. However, the same example can initialize the service using an **explicit constructor**:

~~~java
@ExtendWith(MockitoExtension.class)
class ReservationServiceExplicitTest {
    @Mock
    StockPort stockPort;

    @Mock
    ReceiptPort receiptPort;

    private ReservationService service;

    @BeforeEach
    void setUp() {
        service = new ReservationService(stockPort, receiptPort);
    }

    @Test
    void reserve_whenStockIsAvailable_returnsTrue() {
        when(stockPort.reserve("SKU-1", 1)).thenReturn(true);

        assertTrue(service.reserve("SKU-1", 1));
        verify(receiptPort).send("SKU-1", 1);
    }
}
~~~

This is an **illustrative class placed in the same `com.example.testing` package**, requiring JUnit `@BeforeEach`, `@Test`, `@ExtendWith`, Mockito `@Mock`, `MockitoExtension`, and static imports `when`, `verify`, `assertTrue`. With proper imports saved as `ReservationServiceExplicitTest.java`, it can run in the same project.

By the time JUnit invokes `@BeforeEach`, `MockitoExtension` has already initialized the mocks. `new ReservationService(stockPort, receiptPort)` shows readers all required dependencies clearly and avoids implicit injection when constructors get complex.

| Situation | Which approach? | Why |
| --- | --- | --- |
| Small service, all dependencies are clear mocks/spies | `@InjectMocks` | Reduces setup boilerplate while still running the real SUT |
| Constructor has multiple dependencies of the same type, or real config/value objects | `new SUT(...)` in `@BeforeEach` | Makes it clear which mock goes into which parameter |
| Need to combine mocks with real objects | Explicit constructor | Avoids assuming Mockito creates every object |
| Want Spring to inject real beans in `ApplicationContext` | Spring TestContext, do not use `@InjectMocks` as a substitute | Mockito is not Spring DI |
| Test has no dependencies | `new SUT()` directly | No Mockito needed |

There is no requirement to use `@InjectMocks` in every unit test. Choose the SUT instantiation style that makes **intent and dependencies clearest** to readers.

## 7. What Else Does MockitoExtension Do Besides Initializing @Mock?

### 7.1. Lifecycle and Strict Stubbing Checks

`MockitoExtension` opens a Mockito session around each test execution and finishes it after the test ends. The default configuration in modern Mockito versions uses `STRICT_STUBS` to catch unnecessary or mismatched stubbing.

Common mistake:

~~~java
@Test
void reserve_whenQuantityIsZero_throws() {
    when(stockPort.reserve("SKU-1", 2)).thenReturn(true); // Unused.

    assertThrows(
            IllegalArgumentException.class,
            () -> service.reserve("SKU-1", 0)
    );
}
~~~

The service throws before calling the mock, so the stub for `reserve("SKU-1", 2)` **is never used**. In strict mode, Mockito can report `UnnecessaryStubbingException` at the end of the test. The fix is to **remove the unused stub line**, not to turn off strictness reflexively.

If a stub genuinely has a valid reason to be used only on some branches, Mockito offers `lenient()` or `@MockitoSettings(strictness = ...)`. Limit relaxation to the necessary scope and understand why; in small unit tests, stubbing directly in each test is usually simpler.

### 7.2. Mocks as Method Parameters

In addition to fields, `MockitoExtension` can supply a mock as a parameter to `@Test` or certain lifecycle methods:

~~~java
@Test
void canCreateLocalMock(@Mock StockPort localPort) {
    when(localPort.reserve("SKU-X", 1)).thenReturn(true);
    assertTrue(localPort.reserve("SKU-X", 1));
}
~~~

This is a **method snippet inside a test class already annotated with `@ExtendWith(MockitoExtension.class)`**; it requires importing `@Test`, `@Mock`, `when`, and `assertTrue`. The `localPort` mock is supplied for that invocation, is not automatically the same instance as a `@Mock StockPort stockPort` field, and does not mean `@InjectMocks` will inject this parameter mock into an already-created service.

Use parameter mocks for dependencies needed by only one test. For mocks injected into `@InjectMocks`, class-level `@Mock` fields as in the main example make the injection relationship clearer.

## 8. Why @Mock Is Not Spring's @MockitoBean

In a **unit test**, you use Mockito to instantiate the real service via constructor and pass mocks in. There is no Spring context:

~~~text
JUnit + MockitoExtension
   -> @Mock StockPort
   -> @InjectMocks ReservationService
   -> call business method directly
~~~

In a **Spring integration/slice test**, Spring builds an `ApplicationContext` and decides which beans are injected. If you need to replace a dependency bean in the context, use the Spring Test bean override mechanism (e.g., `@MockitoBean` on supported Spring Framework/Spring Boot versions; older projects may use Spring Boot's `@MockBean`). That is a **different scope** from plain Mockito `@Mock`.

| `@Mock` + `@InjectMocks` | Mock bean in Spring TestContext |
| --- | --- |
| Creates mocks owned by the test; SUT is created by Mockito/test | Replaces or registers a mock at the `ApplicationContext` level |
| Does not require starting Spring Boot | Requires Spring testing support to build a context |
| Fits unit tests of business logic | Fits web slice or integration tests needing bean wiring |
| Does not automatically interact with `@Autowired` | Spring manages injection into relevant beans/tests |

**Common trap:** writing `@SpringBootTest`, declaring a `@Mock SomeRepository` field, and assuming the `SomeRepository` bean Spring injects into a real service is also replaced. Plain `@Mock` **does not replace Spring beans automatically**. Depending on your goal, choose a unit test with explicit constructor injection or use Spring Test bean overriding.

Also do not add `@SpringBootTest` just because an application class has `@Service`. If the logic only relies on mocked dependencies, JUnit + `MockitoExtension` is usually sufficient and runs faster without starting a Spring context.

## 9. Important Limitations of @InjectMocks

### Missing Dependencies Do Not Always Cause Clear Injection Errors

Example:

~~~java
@Mock
StockPort stockPort;

@InjectMocks
ReservationService service; // Missing ReceiptPort mock.
~~~

In some cases, Mockito may attempt to pass `null` for an unresolved dependency, and `ReservationService`'s constructor in the main example will catch it with `Objects.requireNonNull`. In other classes without null checks, the error may only surface when business logic runs. Therefore, never assume `service != null` means wiring is complete.

### Does Not Inject Like Spring

Mockito does not read bean qualifiers, Spring configuration, transaction proxies, security contexts, or dependencies managed by the Spring container. `@InjectMocks` operates on the object and declared mocks/spies according to Mockito's injection strategies; it **is not a clone of `@Autowired`**.

### Does Not Automatically Build Every Dependency or Nested Graph

If service A depends on service B, and B depends on C, you cannot expect `@InjectMocks A` to discover and construct B and C like Spring does. Declare the needed mocks, construct real objects explicitly, or move to a Spring context test if real wiring is what you are testing.

### Ambiguous Dependencies of the Same Type

If a constructor takes two arguments of the same interface, inferring which mock goes where becomes hard to read and error-prone. An explicit constructor call in `@BeforeEach` shows exactly which mock goes into which parameter. With property/field injection, Mockito has type-and-name matching rules in certain cases, but you should not rely on implicit rules if the test code becomes ambiguous.

### Mocking the Object Under Test Is a Common Mistake

~~~java
@Mock
ReservationService service;
~~~

This creates a **fake service**; `service.reserve(...)` will not execute real logic unless intentionally configured as a spy/partial mock. If the goal is to unit test `ReservationService` logic, use a real instance (`@InjectMocks` or `new`) and **mock its dependencies**.

## 10. Debugging When Mockito Tests Behave Unexpectedly

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `NullPointerException` on `@Mock` field in test | Mockito annotations not initialized, missing `MockitoExtension` | Add `@ExtendWith(MockitoExtension.class)` and correct imports |
| SUT is `null` or constructor reports missing dependency | `@InjectMocks` could not create/inject all mocks, missing mock, or incompatible constructor | Check constructor and mock declarations; consider explicit `new` |
| Unit test returns `false` even though `true` was expected | `boolean` mock unstubbed, returning default `false` | Add `when(...).thenReturn(true)` with matching arguments |
| `UnnecessaryStubbingException` | Stub unused during test execution under strict stubs | Remove redundant stub; place stubbing close to the test that needs it |
| `Wanted but not invoked` | `verify` found no matching invocation | Check business path and actual arguments passed |
| `MissingMethodInvocationException` during stubbing | Used `when(...)` on a non-mock object or invalid expression | Only stub mock dependencies managed by Mockito |
| Used `@Mock` yet the real Spring bean is still called | Mockito mock did not replace the Spring bean in context | Use appropriate bean override or a context-free unit test |
| Test passes alone but fails in suite | Shared state, external test data, or order dependence | Isolate fixtures, avoid mutable static state and external side effects |
| Test only `verify`s many internal calls and breaks on refactor | Testing implementation rather than contract | Assert outputs and verify only key interactions |

### If Not Using MockitoExtension

Mockito supports `MockitoAnnotations.openMocks(this)` for manual annotation initialization, e.g., placed in `@BeforeEach` and closing the returned handle in `@AfterEach`. That can fit special integrations, but requires managing resource closure across the lifecycle. **Do not simultaneously enable `MockitoExtension` and call `openMocks` for the same annotations**, as that creates overlapping sessions/mocks and unpredictable state.

Using `Mockito.mock(StockPort.class)` followed by `new ReservationService(...)` is also valid when you prefer not to use annotations; what matters is creating the mocks before passing them to the SUT.

## 11. Practical Workflow and Checklist

When designing a unit test with dependencies:

1. **Identify the real SUT:** which service/class holds the business decision being tested?
2. **List external dependencies:** repositories, HTTP clients, notifiers… Only mock what the test does not need to run for real.
3. **Initialize:** `@ExtendWith(MockitoExtension.class)`, `@Mock` for dependencies, `@InjectMocks` for the SUT or explicit `new`.
4. **Arrange:** set up test data and stub exact calls that will happen with `when(...).thenReturn(...)`.
5. **Act:** invoke the method **on the real SUT**.
6. **Assert:** check return values/exceptions, then verify only contract-critical interactions.
7. **Run independently:** tests must not depend on execution order or state from prior tests; eliminate unused stubbing.

Pre-commit checklist:

- [ ] Uses the correct `org.junit.jupiter.api.Test`, `org.mockito.Mock`, `org.mockito.InjectMocks`, and `org.mockito.junit.jupiter.MockitoExtension`.
- [ ] `@ExtendWith(MockitoExtension.class)` is actually active or an equivalent Mockito initialization mechanism is in place.
- [ ] The `@InjectMocks` target is the **real** SUT, not a mock of the SUT itself.
- [ ] Every required dependency has an appropriate mock or real instance.
- [ ] Stubs match the right arguments and cover only the calls needed for the scenario.
- [ ] Results are checked with assertions, not just seeing code run without throwing.
- [ ] `verify` is used for important effects/interactions without locking down trivial implementation details.
- [ ] Mockito mocks are not confused with mock beans in Spring `ApplicationContext`.
- [ ] Tests run independently without hitting a real DB/email/API unless that is the goal of the chosen test type.

**Key takeaway:** `@Mock` creates **fake dependencies**; `@InjectMocks` builds or prepares the **real business object** and supplies the mocks; `MockitoExtension` connects that process to the **JUnit Jupiter** lifecycle. Stubbing sets conditions, calling the SUT executes business logic, and assertions/verifications prove the outcome.

### References

- [Mockito — @InjectMocks Javadoc](https://www.javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/InjectMocks.html)
- [Mockito — MockitoExtension Javadoc](https://www.javadoc.io/doc/org.mockito/mockito-junit-jupiter/latest/org.mockito.junit.jupiter/org/mockito/junit/jupiter/MockitoExtension.html)
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/)
