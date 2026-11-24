# Strict Stubbing and Detecting Unused Mock Configurations with Mockito

## 1. The Problem Strict Stubbing Solves

In Spring Boot unit tests, developers commonly replace a repository, REST client, or other dependency with a **mock** to control return values. A statement like **when(repository.findById(42L)).thenReturn(...)** configures fake behavior, known as **stubbing**. However, if the code under test never calls `repository.findById(42L)`, that stub verifies nothing. Worse, it can hide that the code took the wrong branch or that the test was copy-pasted from another scenario.

**Strict stubbing** is Mockito's quality check for mock configuration. Under **Strictness.STRICT_STUBS**, Mockito helps detect:
1. **Unused stubbing:** A mock method is configured to return a result, yet no matching invocation occurs during the test run. The typical outcome is **UnnecessaryStubbingException**.
2. **Stubbing argument mismatch:** The test configures a mock for one set of arguments, while the code under test invokes the same method with different arguments. In cases Mockito identifies as a stubbing argument mismatch, it reports **PotentialStubbingProblem** early.
3. **Stubbed interactions can automatically count as verified** when using **verifyNoMoreInteractions** under STRICT_STUBS; thus you do not necessarily have to write separate `verify` calls for every stubbed invocation just to satisfy no-more-interactions checks.

This mechanism keeps tests readable, reduces dead fake data, and catches setup mistakes early. It **does not prove business algorithms are right** if assertions are weak or missing; you still must write assertions for expected outputs and behavior.

**Lesson scope:** Mockito running with JUnit Jupiter in a Spring Boot project. Examples use Java 17, Spring Boot 3.3.5, and Gradle. Strict stubbing is a Mockito feature, not a Spring Boot setting automatically applied to every test double.

## 2. Terminology: Mock, Stubbing, Invocation, Verification, and Strictness

| Concept | Meaning | Example |
|---|---|---|
| **Mock** | Substitute object for a dependency, usually created by Mockito | `@Mock InvoiceRepository repository` |
| **Stubbing** | Configuring behavior when a mock method is called with given inputs | `when(repo.findById(42L)).thenReturn(Optional.of(invoice))` |
| **Invocation** | Actual method call on a mock occurring while code runs | `service.amountVnd(42L)` calls `repo.findById(42L)` |
| **Verification** | Assertion that a mock did or did not receive an invocation | `verify(repo).findById(42L)` |
| **Strictness** | Extra validation level applied to stubbing/verification | `STRICT_STUBS`, `WARN`, `LENIENT` |

For instance, calling **when(repo.findById(42L)).thenReturn(...)** creates a stub; only when execution reaches a matching **repo.findById(42L)** call is that stub used. Calling **verify(repo).findById(42L)** is a separate interaction check, distinct from using the stub. A mock can exist without any stubbing; a test can interact with a mock without triggering unused-stubbing checks if it defines no stubs.

**Strict stubbing does not mean every mock call must be declared upfront.** Mockito still applies default answers to many unstubbed calls (such as `null`, `false`, `0`, or empty values depending on type/version/configuration). Strict mode focuses on useless stub setups and argument mismatches that look like bugs. If a test requires that only explicitly allowed interactions occur, add verifications or appropriate assertions rather than relying on strict stubbing alone.

## 3. When Does STRICT_STUBS Take Effect?

When using **MockitoExtension** with JUnit Jupiter:

1. **Before each test:** The extension creates `@Mock` instances, processes `@InjectMocks`, and starts a Mockito session with the configured strictness.
2. **During the test:** `when/thenReturn` or `doReturn/when` registers stubs. Methods on the class under test invoke the mock; Mockito looks up matching stubs by method and matchers/arguments.
3. **When a recognizable argument mismatch happens:** `STRICT_STUBS` can report `PotentialStubbingProblem` right at the invocation, helping catch whether the SUT passed the right ID or value.
4. **When the test/session finishes:** Mockito compares registered stubs against used invocations and can throw `UnnecessaryStubbingException` for unused stubs. When a test has already failed for another reason, additional reporting depends on the version and integration.

With **org.mockito.junit.jupiter.MockitoExtension**, the default strictness in the Mockito 5 releases used here is **STRICT_STUBS**. You can declare it explicitly with **@MockitoSettings(strictness = Strictness.STRICT_STUBS)** to document intent and avoid confusion when migrating between test integrations. `MockitoExtension` lives in **mockito-junit-jupiter**; it is not a standalone JUnit Platform engine.

**Distinguish where mocks are configured:** Calling plain **Mockito.mock(...)** without `MockitoExtension`, a JUnit runner, or a managed `MockitoSession` does not guarantee the same end-of-test unused-stubbing checks. Check which session or integration runs the test; merely having Mockito on the classpath is not enough.

## 4. Two Main Error Signals

### 4.1. UnnecessaryStubbingException: Stub Defined but Never Used

Suppose a test configures:

~~~java
// Assume repository is a Mockito mock and service uses repository.
when(repository.findById(42L))
        .thenReturn(Optional.of(new Invoice(42L, 120_000L)));

// This label-formatting method never calls repository:
assertEquals("INV-42", service.label(42L));
~~~

This snippet illustrates code inside a test method with existing mock/service; it is not a standalone Java program. The assertion passes, yet the invoice lookup stub was never used. Under `STRICT_STUBS` and a managed Mockito lifecycle, Mockito throws `UnnecessaryStubbingException`. The message typically prints the line number of the unused stub so you can locate and remove it.

**Proper fix:** Delete the `when(...)` line because this test only tests invoice label formatting. If you need to test the repository-lookup path, write a separate test with that invocation and assertion. Never add a fake call to `repository` just to mark the stub as used.

A frequent culprit is putting shared stubs into **@BeforeEach** when each test only exercises a subset of branches. With `MockitoExtension`, prefer stubbing right inside each test that needs it instead of assuming every test shares the same fixture.

### 4.2. PotentialStubbingProblem: Stub Arguments Differ from Invocation

~~~java
when(repository.findById(42L))
        .thenReturn(Optional.of(new Invoice(42L, 120_000L)));

// Inside InvoiceService, this call actually asks for findById(43L):
service.amountVnd(43L);
~~~

If the test meant to check invoice 42 yet passed ID 43 to the service, the mismatch can trigger `PotentialStubbingProblem` when the code under test invokes the mock. Check **the stubbed ID**, **the ID passed to the SUT**, **argument matchers**, and **the actual code path** before lowering strictness.

Not every mock call with different arguments is guaranteed to raise the exact same exception: Mockito applies heuristics to distinguish accidental mismatches from valid cases, and strictness scope affects the outcome. Sometimes the symptom is a default value returned by the mock, a failing assertion, or an unused stub error later. Read the actual failure rather than guessing by exception name alone.

**A legitimate scenario:** The service intentionally queries multiple IDs. In that case, stub every ID the test wants to control, use suitable matchers, or reorganize the test. If stubbing the same method multiple times triggers false warnings inside `when(...)`, you can use **doReturn(...).when(mock)** or **BDDMockito.willReturn(...).given(mock)** per Mockito's guide. Only mark something `lenient` after confirming the mismatch is intentional.

## 5. Complete Example: Spring Boot 3.3.5 + JUnit Jupiter + Mockito

This example contains three tests **designed to PASS**, alongside two error scenarios marked **@Disabled**. During normal builds, the broken demos are skipped; learners can temporarily enable each one to observe strict stubbing in action.

### 5.1. Structure

~~~text
settings.gradle
build.gradle
src/main/java/demo/testing/TestingApplication.java
src/main/java/demo/testing/Invoice.java
src/main/java/demo/testing/InvoiceRepository.java
src/main/java/demo/testing/InvoiceService.java
src/test/java/demo/testing/InvoiceServiceTest.java
src/test/java/demo/testing/StrictStubsFailureDemoTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'mockito-strict-stubs-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    // Test starter provides JUnit Jupiter and mockito-junit-jupiter.
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

No explicit Mockito version is declared because Spring Boot dependency management manages the example's testing stack. **useJUnitPlatform()** is essential so Gradle runs JUnit Jupiter. Requires Java 17+ and a Gradle version compatible with Spring Boot 3.3.x; use the project's Gradle Wrapper when present.

**src/main/java/demo/testing/TestingApplication.java**

~~~java
package demo.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}
~~~

**src/main/java/demo/testing/Invoice.java**

~~~java
package demo.testing;

public record Invoice(long id, long amountVnd) {
}
~~~

**src/main/java/demo/testing/InvoiceRepository.java**

~~~java
package demo.testing;

import java.util.Optional;

public interface InvoiceRepository {
    Optional<Invoice> findById(long id);
}
~~~

**src/main/java/demo/testing/InvoiceService.java**

~~~java
package demo.testing;

import java.util.Objects;

public final class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public long amountVnd(long id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Invoice not found: " + id))
                .amountVnd();
    }

    public String label(long id) {
        return "INV-" + id;
    }
}
~~~

`InvoiceService` is a plain Java class inside a Spring Boot project and needs no Spring `ApplicationContext` to test its logic. The goal is cleanly isolating the `InvoiceRepository` dependency using **@Mock** and **@InjectMocks**, rather than `@SpringBootTest`. The tests touch neither database nor network.

### 5.2. Passing Tests: Stubbing Only What Each Test Uses

**src/test/java/demo/testing/InvoiceServiceTest.java**

~~~java
package demo.testing;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.STRICT_STUBS)
class InvoiceServiceTest {

    @Mock
    InvoiceRepository repository;

    @InjectMocks
    InvoiceService service;

    @Test
    void returnsAmountWhenInvoiceExists() {
        when(repository.findById(42L))
                .thenReturn(Optional.of(new Invoice(42L, 120_000L)));

        long amount = service.amountVnd(42L);

        assertEquals(120_000L, amount);
        verify(repository).findById(42L);
    }

    @Test
    void throwsWhenInvoiceDoesNotExist() {
        when(repository.findById(404L)).thenReturn(Optional.empty());

        IllegalArgumentException exception = assertThrows(
                IllegalArgumentException.class,
                () -> service.amountVnd(404L));

        assertEquals("Invoice not found: 404", exception.getMessage());
    }

    @Test
    void labelDoesNotNeedAnyRepositoryStubbing() {
        assertEquals("INV-42", service.label(42L));
        verifyNoInteractions(repository);
    }
}
~~~

Explanation:

- `returnsAmountWhenInvoiceExists()`: stubs exact `findById(42L)`, service queries that ID, assertion checks the amount. **verify** is an intentional interaction assertion; strict stubbing does not require adding `verify` to count the stub as used.
- `throwsWhenInvoiceDoesNotExist()`: mock returns `Optional.empty()`, service throws `IllegalArgumentException`; the test asserts both exception type and message.
- `labelDoesNotNeedAnyRepositoryStubbing()`: this code path only formats a label, so **no stub is created**. `verifyNoInteractions(...)` confirms the method never touches the repository; that is an extra business assertion, not a requirement of strict stubbing.
- Each test receives its own mocks/session from `MockitoExtension`; the stub for the first test is not placed in shared setup for all three.

All three methods succeed under `STRICT_STUBS` with zero redundant stubbing.

### 5.3. Intentionally Failing Tests: Kept @Disabled for Normal Runs

**src/test/java/demo/testing/StrictStubsFailureDemoTest.java**

~~~java
package demo.testing;

import java.util.Optional;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

@Disabled("Teaching demo: remove @Disabled to observe strict failures")
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.STRICT_STUBS)
class StrictStubsFailureDemoTest {

    @Mock
    InvoiceRepository repository;

    @InjectMocks
    InvoiceService service;

    @Test
    void unusedStubTriggersUnnecessaryStubbing() {
        when(repository.findById(42L))
                .thenReturn(Optional.of(new Invoice(42L, 120_000L)));

        // label() never calls findById(), so the stub above is unused.
        assertEquals("INV-42", service.label(42L));
    }

    @Test
    void wrongArgumentCanTriggerPotentialStubbingProblem() {
        when(repository.findById(42L))
                .thenReturn(Optional.of(new Invoice(42L, 120_000L)));

        // Service calls findById(43L), mismatched against stub for 42L.
        service.amountVnd(43L);
    }
}
~~~

The class above is **completely disabled** so normal builds succeed. To observe the errors, temporarily remove `@Disabled` on the class and run **each method individually**. In the commands below, specify the fully qualified test method to avoid triggering both failures at once.

~~~bash
./gradlew test --tests demo.testing.StrictStubsFailureDemoTest.unusedStubTriggersUnnecessaryStubbing
./gradlew test --tests demo.testing.StrictStubsFailureDemoTest.wrongArgumentCanTriggerPotentialStubbingProblem
~~~

With Windows PowerShell/Command Prompt and Gradle Wrapper:

~~~powershell
.\gradlew.bat test --tests demo.testing.StrictStubsFailureDemoTest.unusedStubTriggersUnnecessaryStubbing
.\gradlew.bat test --tests demo.testing.StrictStubsFailureDemoTest.wrongArgumentCanTriggerPotentialStubbingProblem
~~~

After removing `@Disabled`, each command is **expected to fail intentionally**. The first should report **UnnecessaryStubbingException** pointing to the unused `when(...)` line; the second can report **PotentialStubbingProblem** at the mock call with mismatched arguments. Exact messages and stack traces vary with Mockito, Gradle, and JDK; do not assert a rigid stdout string.

When finished experimenting, **restore `@Disabled`** or delete the failing demo class from real code. Do not “fix” it by switching the whole suite to `LENIENT`; the demo exists to show why unused stubs happen.

### 5.4. Running All Tests and Checking the Report

If the project already has Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

The example suite contains **three PASSING tests** in `InvoiceServiceTest` and **two disabled tests** in `StrictStubsFailureDemoTest`. Gradle's JUnit report at **build/reports/tests/test/index.html** shows passed/skipped/failed counts; check the actual run because other tests in the project or filter settings can affect totals.

If there is no Wrapper, generate one with a compatible Gradle installation or run `gradle test`. The illustrative files above contain all source and build logic for the example; only `./gradlew` requires the project's Wrapper files.

## 6. Fixing Errors the Right Way: Before and After

### 6.1. Remove Stubs That Do Not Serve What Is Tested

**Before:**

~~~java
when(repository.findById(42L))
        .thenReturn(Optional.of(new Invoice(42L, 120_000L)));
assertEquals("INV-42", service.label(42L));
~~~

**After:**

~~~java
assertEquals("INV-42", service.label(42L));
verifyNoInteractions(repository);
~~~

Both snippets are **bodies inside a test method with configured mock/service**, not standalone Java files. After fixing, the test clearly states “formatting a label needs no repository”; stubbing an invoice makes no sense for that requirement. If other tests need invoice 42, each should declare the stub for its own scenario.

### 6.2. Align Arguments Between Test and Code

**Before:**

~~~java
when(repository.findById(42L))
        .thenReturn(Optional.of(new Invoice(42L, 120_000L)));
assertEquals(120_000L, service.amountVnd(43L));
~~~

**After, when invoice 42 is intended:**

~~~java
when(repository.findById(42L))
        .thenReturn(Optional.of(new Invoice(42L, 120_000L)));
assertEquals(120_000L, service.amountVnd(42L));
~~~

If invoice 43 was actually intended, update both the stub and expected data to invoice 43; never force the service to call ID 42 just to satisfy the mock. When encountering `PotentialStubbingProblem`, compare inputs on **both sides** and check any argument matchers in use.

### 6.3. Minimize Shared Stubbing in @BeforeEach

**Pattern that easily produces unused stubs:**

~~~java
@BeforeEach
void setUp() {
    when(repository.findById(42L))
            .thenReturn(Optional.of(new Invoice(42L, 120_000L)));
}

// A test that only calls service.label(42L) will never use this stub.
~~~

**Preferred:**

~~~java
@Test
void readsAmount() {
    when(repository.findById(42L))
            .thenReturn(Optional.of(new Invoice(42L, 120_000L)));
    assertEquals(120_000L, service.amountVnd(42L));
}

@Test
void formatsLabelWithoutRepository() {
    assertEquals("INV-42", service.label(42L));
}
~~~

These snippets illustrate code **inside a test class** assuming imports, `@Mock`, `@InjectMocks`, and `MockitoExtension` as in the complete example. Shared setups that are **always used** belong in fixtures, whereas stubs needed by only a subset of tests belong right next to their assertions. Especially with `@ParameterizedTest`, `@BeforeEach` runs for every invocation even when some invocations take a branch that does not use the stub.

## 7. STRICT_STUBS, WARN, and LENIENT: Which Level for What Purpose?

| Strictness | When a stub is unused | When arguments mismatch | When to use |
|---|---|---|---|
| **STRICT_STUBS** | Can fail the test with `UnnecessaryStubbingException` | Can fail fast with `PotentialStubbingProblem` | Recommended default for new tests, especially unit tests using `MockitoExtension` |
| **WARN** | Prints warnings/hints rather than failing on this check | Prints hints on detected mismatches | Transitional periods while cleaning up legacy tests; read and fix warnings |
| **LENIENT** | Skips corresponding strict stubbing checks | Skips corresponding mismatch checks | Narrow exceptions when a stub is intentionally unused on certain branches |

**Setting strictness for a test class:**

~~~java
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.STRICT_STUBS)
class ExampleTest {
    // @Mock and @Test...
}
~~~

This snippet is not a standalone Java file; it requires Mockito/JUnit Jupiter imports and test class content. You can switch `STRICT_STUBS` to `WARN` or `LENIENT` at the class level, though you should not relax an entire class just to ignore one unnecessary stub.

**Lowering strictness for a single stub when genuinely justified:**

~~~java
// Requires static import org.mockito.Mockito.lenient;
lenient().when(repository.findById(42L))
        .thenReturn(Optional.of(new Invoice(42L, 120_000L)));
~~~

A stub marked `lenient` opts out of strict unused-stub/argument-mismatch checks; all other stubs in the test remain strictly checked. This is a **last resort after considering removing or moving the stub**. Applying leniency to an entire mock or test class widens the unchecked scope and increases the risk of masking bugs.

**Example at mock scope:**

~~~java
@Mock(strictness = Mock.Strictness.LENIENT)
InvoiceRepository repository;
~~~

Requires importing **org.mockito.Mock**. In Mockito 5, use this `strictness` attribute if you truly need mock-level leniency; the older `@Mock(lenient = true)` syntax is superseded. Avoid applying it to an entire mock when only a single stubbing needs an exception.

**When managing lifecycle manually:** `MockitoSession` lets you specify strictness and close the session via `finishMocking()`. When using JUnit Jupiter, `MockitoExtension` already manages the lifecycle for you; do not attach `MockitoExtension` and simultaneously call `openMocks()` or open a second session for the same fields in each test.

## 8. When Is an Unused Stub a Bug Rather Than Dead Code?

An unused stub can reveal:
- **Wrong code branch:** The test expected the service to query the repository, yet the method never called it.
- **Wrong ID/arguments:** Configured `findById(42L)` while the SUT called `findById(43L)`; one side is wrong for the scenario.
- **Wrong mock instance:** Multiple service or repository instances exist; the stub was placed on mock A while the code calls mock B or a real Spring bean.
- **Stale setup:** A refactoring removed a dependency call while the test kept old setup code.
- **Improper matchers:** `equals` on a DTO is broken, a recreated object is not equal, or matchers were mixed with literals improperly.
- **Expected path not reached:** Input conditions, feature flags, caching, or an early exception caused the service to return before using the stub.
- **Copy-pasted fixture:** `@BeforeEach` configures multiple methods for every test even though most tests do not use them.

**Practical investigation steps:**

1. Read the stack trace at the stubbing line Mockito reports; identify the mock, method, and arguments.
2. Locate inside the **method under test** where the dependency call was expected to use that stub. Use a debugger when control flow is complex.
3. Compare test inputs with stub arguments. If the SUT passes a different ID, find out why and fix the right side.
4. Check instances: did `@InjectMocks` receive the right `@Mock`? Under `@SpringBootTest`, is a different bean injected?
5. If the stub genuinely serves no assertion, **delete it** or move it into the test that needs it.
6. Only apply `lenient` with a clear justification that can be explained in one sentence at the stub site.
7. Rerun the test and inspect both business assertions and Mockito reports; never merely confirm the strictness error vanished.

Do not resolve `UnnecessaryStubbingException` by adding **verify(repository).findById(42L)** when the service does not call it: that verification will fail too. Nor should you call the mock directly inside the test just to consume the stub; doing so hides the real branching bug you wanted to catch.

## 9. Comparing Strict Stubbing with Other Verification Tools

| Tool | What does it check? | How does it differ from strict stubbing? |
|---|---|---|
| **assertEquals/assertThrows** | Return values, exceptions, and business rules | Does not automatically detect unused stubs |
| **verify(mock).method(...)** | Mock method was called with matching arguments | Can be used even without creating any stub |
| **verifyNoInteractions(mock)** | Mock received zero interactions | Asserts the branch did not touch the dependency |
| **verifyNoMoreInteractions(mock)** | No unverified interactions remain | `STRICT_STUBS` treats stubbed invocations as verified for this check |
| **UnnecessaryStubbingException** | Stub was defined but never used | Diagnoses redundant fixtures or wrong execution paths |
| **PotentialStubbingProblem** | Argument mismatch between stubbing and invocation detected by Mockito | Diagnoses suspicious mock setup or processing flow |
| **JUnit assertions/coverage report** | Assertion pass/fail and executed code paths | High coverage can still coexist with unused stubs and weak assertions |

A test can **PASS all assertions** yet be marked failed by `MockitoExtension` at cleanup because of an unused stub. That is expected strict-stubbing behavior, not a Gradle misconfiguration. Conversely, a test with zero unused stubs can still under-test behavior, such as calling a service without asserting its output.

**Do not mechanically put `verifyNoMoreInteractions` on every mock.** That assertion locks down interaction details and can make valid internal refactorings brittle. Verify interactions when they express a real requirement, such as “do not charge twice.”

## 10. Mockito in Spring Boot: @Mock and @MockBean Do Not Share the Same Lifecycle

In the illustrative unit test:
- **@ExtendWith(MockitoExtension.class)** activates Mockito's strict stubbing lifecycle for extension-managed mocks.
- **@Mock** creates a mock `InvoiceRepository` outside any Spring `ApplicationContext`.
- **@InjectMocks** instantiates `InvoiceService` and passes the mock into its constructor. It does not create a Spring bean.
- No **@SpringBootTest** is needed, so tests run fast and clearly show why a stub is or is not used.

In integration tests using **@SpringBootTest**, Spring Boot 3.3.x provides **@MockBean** to create/replace a bean in `ApplicationContext`. Those tests add the Spring TestContext lifecycle, context caching, and mock resetting. **Do not assume every `@MockBean` automatically receives the exact same unused-stubbing checks as mocks managed by `MockitoExtension`**; check the integration configuration and behavior of your specific version.

If a mock is placed in the Spring context yet the SUT still calls another dependency, an unused stub signals a wiring/bean-selection issue to inspect rather than a reason to turn on `lenient`. Use `MockitoExtension` for pure Mockito unit tests; use Spring test support when proving bean wiring, the web layer, or real integrations.

**Spy warning:** With a spy, **when(spy.realMethod())** can invoke the real method during stubbing, triggering side effects or exceptions. For those cases, consider **doReturn(value).when(spy).realMethod(...)**. That is a spy stubbing mechanic; strict stubbing can still catch unused stubs afterward.

## 11. Common Errors and Remedies

| Symptom | Common cause | Action |
|---|---|---|
| `UnnecessaryStubbingException` even though `assertEquals` passed | Stub was never invoked by the SUT; caught after test | Remove the stub or move it into the test that uses it |
| `PotentialStubbingProblem` when calling service | SUT called the mock with arguments differing from the stub | Check inputs, IDs, matchers; fix the scenario |
| Used `@BeforeEach` and tests not needing the repository fail | Shared setup creates stubs for every test | Create stubs inside individual tests or keep unstubbed fixtures |
| Switching to `Strictness.LENIENT` makes build green | Disabled the check instead of fixing the root cause | Restore `STRICT_STUBS`, trace the actual execution path |
| Stub looks used yet Mockito says otherwise | Stubbed mock A while SUT uses mock/bean B | Inspect constructor injection and Spring context |
| Mockito dependency present yet unused stubs are not reported | Missing `MockitoExtension`/`MockitoSession` or strictness lowered | Check test annotations, engine, and lifecycle |
| Test uses overly broad matcher like `anyLong()` | Mock returns data for wrong IDs, hiding bugs | Use exact IDs/matchers when required by the scenario |
| Stubbing the same method multiple times causes mismatch | `when()` declaration triggers prior invocation | Check `doReturn().when` or BDD `willReturn().given` and rationale |
| Removing `@Disabled` on the whole failure demo fails the build | Two intentionally broken tests executed | Run one method at a time, then restore `@Disabled` |
| `verifyNoMoreInteractions` fails when adding an internal call | Test locked down non-contract interactions | Verify only business-critical interactions |
| Using `@MockBean` like `@Mock` in unit tests | Different lifecycles between Spring context and `MockitoExtension` | Choose the right unit/integration layer and check wiring |

## 12. Workflow in Projects and CI

When a Mockito test fails due to strict stubbing:
1. **Read the exception name** and the stubbing line reported by Mockito.
2. **Read the test's requirement:** Which code path should run? Which outcome or interaction must be proven?
3. **Compare the stub with actual invocations:** method, arguments, matchers, mock/bean instance, and control-flow branch.
4. **Fix the root cause:** delete the extra stub, align IDs, or adjust assertions/fixtures to match the rule.
5. **If a genuine exception exists:** scope leniency to that single stub and document why; avoid disabling strictness project-wide.
6. **Rerun tests:** run the exact Gradle/Maven command CI uses and inspect failure/skip reports; do not rely on “compiles successfully.”
7. **Keep tests independent:** each test sets up the stubs it needs without relying on execution order or leftover mock state.

In code reviews, a helpful question is: “Which assertion or business branch does this stub serve?” If you cannot name one, it is probably unnecessary. In CI, strict stubbing enforces cleaner test fixtures, though it must still be paired with outcome assertions and integration tests wherever wiring, database, or HTTP risks live.

## 13. Key Takeaways and References

- **STRICT_STUBS** catches unused stubbing and can catch argument mismatches early; **LENIENT** skips these checks, while **WARN** primarily warns.
- **UnnecessaryStubbingException** usually signals removing or moving a stub, not adding pointless `verify` calls.
- **PotentialStubbingProblem** prompts comparing stubbed arguments against what the SUT actually passes.
- **MockitoExtension** is the natural choice for JUnit Jupiter unit tests. Explicit `@MockitoSettings` clarifies strictness scope.
- **Prefer removing redundant stubs**, keeping fixtures local to each test, and using `lenient` only for concrete, justified exceptions.

References for looking up Mockito behavior and APIs:
- [Mockito Strictness (Javadoc)](https://javadoc.io/static/org.mockito/mockito-core/5.14.2/org/mockito/quality/Strictness.html)
- [UnnecessaryStubbingException (Javadoc)](https://javadoc.io/static/org.mockito/mockito-core/5.11.0/org/mockito/exceptions/misusing/UnnecessaryStubbingException.html)
- [PotentialStubbingProblem (Javadoc)](https://www.javadoc.io/static/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/exceptions/misusing/PotentialStubbingProblem.html)
- [MockitoExtension (Mockito source)](https://github.com/mockito/mockito/blob/main/mockito-extensions/mockito-junit-jupiter/src/main/java/org/mockito/junit/jupiter/MockitoExtension.java)
