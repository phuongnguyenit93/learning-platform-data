# Mock Reset Between Tests and Shared State in Spring Boot

## 1. The problem: the second test is affected by the first

When testing a Spring Boot service whose dependency is replaced with a mock, two types of state are easily confused:

1. **Internal state of a Mockito mock:** stubbings like `when(...).thenReturn(...)`, recorded calls for `verify(...)`, custom `Answer`s, and behavior configured on the mock.
2. **State of the application and test environment:** mutable fields on singleton beans, caches, static variables, database rows, queues, temp files, session state, global config, or hand-written fake objects.

Resetting a mock clears **that mock's stubbings and invocation history**, yet it does not reset the entire `ApplicationContext`, the service using the mock, or the database back to square one.

Suppose two tests share one `@MockBean` replacing `QuoteGateway`:

- Test A stubs `findQuote("Q1")` to return `"Quote 1"`, then calls `QuoteService.text("Q1")`.
- Test B expects no stub from Test A and tests the quote-not-found case.
- If the mock is reused **without being reset**, Test B may observe configurations or invocations from Test A, causing wrong outputs or failed verifications.
- If Spring Boot resets the mock per lifecycle rules, **A's configuration never leaks into B**, even while `ApplicationContext` is cached and reused.

This lesson sits under **bean replacement in tests**: distinguishing Mockito-managed `@Mock` from `@MockBean` placed into `ApplicationContext` by Spring Boot, understanding `MockReset.AFTER`/`BEFORE`/`NONE`, knowing when to use `Mockito.reset()`/`clearInvocations()`, and cleaning up non-mock state without abusing `@DirtiesContext`.

**Example version scope:** Java 17, Spring Boot 3.3.5, JUnit Jupiter, Mockito, and Gradle. In Spring Boot 3.3, the standard bean-replacement annotation is **org.springframework.boot.test.mock.mockito.MockBean**. From Spring Boot 3.4 onward, this API is deprecated in favor of Spring Framework's **@MockitoBean**; see the version note at the end and do not mix imports between the two mechanisms.

## 2. How do mocks, spies, fakes, beans, and context caching differ?

| Component | Object created/controlled | Can data persist across tests? | Common isolation approach |
|---|---|---|---|
| **@Mock + MockitoExtension** | Mock is a test field initialized by Mockito per Jupiter lifecycle | Under default `PER_METHOD`, each test gets a fresh fixture; manual reset rarely needed | `@ExtendWith(MockitoExtension.class)`, per-test setup |
| **@MockBean (Spring Boot 3.3)** | Mock replaces/adds a bean in `ApplicationContext` and injects into test field | Context can be cached, while mock resets per default `MockReset` | Keep `MockReset.AFTER`; avoid excess setup stubs |
| **@SpyBean (Spring Boot 3.3)** | Spy wraps a real bean in the context | Mockito tracks invocations/stubbings; **real internal bean state can still persist** | Reset mock metadata and explicitly clean real state |
| **Hand-written fake bean** | Simple implementation possibly storing data in a `Map`/`List` | Yes, if registered as a singleton in a cached context | Clear fake before each test or create isolated fixtures |
| **Singleton `@Service`** | Real application bean | Yes, if it holds mutable fields and context is reused | Design statelessly; reset test data deliberately |
| **Database / Redis / message broker** | Storage systems outside Mockito | Yes, subject to transactions and cleanup policies | Transaction rollback, cleanup scripts, isolated schemas/containers |
| **ApplicationContext cache** | Spring container and bean set shared across matching test configs | Yes, across tests matching the context cache key | Keep tests independent; use `@DirtiesContext` only when needed |

**Key point:** JUnit Jupiter defaults to creating **a new test class instance per test method** (`Lifecycle.PER_METHOD`). That **does not mean** Spring creates a new `ApplicationContext` per test. Spring TestContext actively caches contexts to keep suites fast. A singleton inside the context can be the exact same instance across multiple test methods even while test class instances differ.

Similarly, `@TestInstance(PER_CLASS)` or **static** variables allow test-class state to survive across methods even without a Spring context. Always identify the **owner of state** before deciding how to reset it.

## 3. What does Mockito reset actually clear?

Mockito provides two operations that are easily confused:

| Operation | Clears invocation/verification history? | Clears configured stubbings? | When to use |
|---|---|---|---|
| **Mockito.reset(mock)** | Yes | **Yes** | Required when refreshing the same reused mock, typically due to a container |
| **Mockito.clearInvocations(mock)** | Yes | **No** | Keeping complex stubs while measuring a separate interaction phase |
| **No action** | No | No | Recommended when each test already has its own mock/fixture |
| **Create new mock** | New mock has no old history | New mock has no old stubs | Natural choice in unit tests |

Intuitive example:

~~~java
QuoteGateway gateway = mock(QuoteGateway.class);
when(gateway.findQuote("Q1"))
        .thenReturn(Optional.of("Quote 1"));

gateway.findQuote("Q1"); // One invocation recorded.

clearInvocations(gateway); // Clears invocations, KEEPS stubbing.
// gateway.findQuote("Q1") still returns Optional containing "Quote 1".

reset(gateway); // Clears invocations AND stubbing.
// No longer configured to return "Quote 1".
~~~

This snippet illustrates code inside a Java method with appropriate imports, not a standalone file. When a mock method returning `Optional` is unstubbed, Mockito's standard default answer returns **`Optional.empty()`**; other return types or custom `Answer`s yield different defaults.

**`Mockito.reset` does not allocate a new mock instance.** It clears configurations and call history attached to the passed mock instance. If the application also holds a separate **cache `Map`** containing `"Q1"` or a singleton call counter, `reset(gateway)` leaves those objects untouched.

**Avoid resetting mid-test just to split a long test into phases.** That can wipe out stubs/interactions the test still needs to verify and makes tests harder to read. If you have multiple independent behaviors, splitting into smaller tests is better.

## 4. How does Spring Boot 3.3 `@MockBean` reset automatically?

**`@MockBean`** adds a mock bean or replaces an existing bean in `ApplicationContext`. Placed on a test field, the same mock instance is injected into that field; services depending on the replaced bean receive that mock from the context.

In Spring Boot 3.3, the attribute:

~~~java
@MockBean(reset = MockReset.AFTER)
QuoteGateway gateway;
~~~

uses **`org.springframework.boot.test.mock.mockito.MockReset`**, offering three values:

| Mode | When reset occurs | Effect across consecutive tests |
|---|---|---|
| **AFTER** | After each test method | Default; stubs and invocations from the finished test are cleared before the next run |
| **BEFORE** | Before each test method | Each test starts with a clean mock; helpful when needing guaranteed pre-test cleanup |
| **NONE** | No automatic reset | Stubbings/invocations can persist across tests reusing the context; choose only deliberately |

If written simply as:

~~~java
@MockBean
QuoteGateway gateway;
~~~

then **`reset` defaults to `MockReset.AFTER`**, so omitting `reset = ...` works for most tests. Spring Boot handles this via its Spring TestContext/Mockito integration (including **`ResetMocksTestExecutionListener`**). Using a standard Spring Boot test annotation like `@SpringBootTest` activates the associated infrastructure.

**Both `AFTER` and `BEFORE` isolate mock state**, just at different lifecycle points. Neither clears singleton application state or databases. If a test supplies custom `@TestExecutionListeners` and accidentally replaces all default listeners, Spring Boot's reset mechanism can stop working; always merge with defaults when customizing listeners.

**Reset is unrelated to `Strictness.STRICT_STUBS`.** Mockito strict stubbing detects unused stubs or argument mismatches within one test; Spring Boot's `MockReset` controls **when** mock state is wiped. Never treat disabling strictness as a reset mechanism, nor resetting as a cure for `UnnecessaryStubbingException`.

## 5. Runnable example: Spring Boot + default `@MockBean` reset

The sample project has `QuoteService` depending on `QuoteGateway`. At normal runtime, `DefaultQuoteGateway` is the real bean returning empty results; in tests, `@MockBean` replaces it with a Mockito mock. Tests verify both business output and clean mock state before each case.

### 5.1. Project structure

~~~text
settings.gradle
build.gradle
src/main/java/demo/reset/ResetDemoApplication.java
src/main/java/demo/reset/QuoteGateway.java
src/main/java/demo/reset/DefaultQuoteGateway.java
src/main/java/demo/reset/QuoteService.java
src/test/java/demo/reset/QuoteServiceWithMockBeanTest.java
src/test/java/demo/reset/QuoteServiceUnitTest.java
src/test/java/demo/reset/MockitoResetSemanticsTest.java
src/test/java/demo/reset/SharedStateIsolationTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-boot-mock-reset-demo'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

In Spring Boot 3.3.5, `spring-boot-starter-test` pulls in libraries such as JUnit Jupiter, Mockito, Mockito Jupiter integration, Spring Test, and AssertJ. Plain unit tests do not need `@SpringBootTest`; use `@SpringBootTest` when testing context bean replacement.

### 5.2. Production classes

**src/main/java/demo/reset/ResetDemoApplication.java**

~~~java
package demo.reset;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResetDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResetDemoApplication.class, args);
    }
}
~~~

**src/main/java/demo/reset/QuoteGateway.java**

~~~java
package demo.reset;

import java.util.Optional;

public interface QuoteGateway {
    Optional<String> findQuote(String code);
}
~~~

**src/main/java/demo/reset/DefaultQuoteGateway.java**

~~~java
package demo.reset;

import java.util.Optional;

import org.springframework.stereotype.Component;

@Component
public class DefaultQuoteGateway implements QuoteGateway {

    @Override
    public Optional<String> findQuote(String code) {
        return Optional.empty();
    }
}
~~~

**src/main/java/demo/reset/QuoteService.java**

~~~java
package demo.reset;

import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class QuoteService {

    private final QuoteGateway gateway;

    public QuoteService(QuoteGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    public String text(String code) {
        return gateway.findQuote(code).orElse("NOT_FOUND");
    }
}
~~~

**Why separate `QuoteGateway` from `QuoteService`?** Constructor-injecting the dependency lets unit tests pass mocks directly and allows Spring Boot tests to replace the **`QuoteGateway` bean** in `ApplicationContext` without altering `QuoteService` logic. Making `gateway` `final` ensures the service never swaps or modifies stubbing at runtime.

### 5.3. Integration test: `@MockBean` and clean state on every run

**src/test/java/demo/reset/QuoteServiceWithMockBeanTest.java**

~~~java
package demo.reset;

import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mockingDetails;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class QuoteServiceWithMockBeanTest {

    @Autowired
    QuoteService quoteService;

    // Spring Boot 3.3: default reset = MockReset.AFTER.
    @MockBean
    QuoteGateway gateway;

    @BeforeEach
    void startsWithCleanMock() {
        verifyNoInteractions(gateway);
        assertThat(mockingDetails(gateway).getStubbings()).isEmpty();
    }

    @Test
    void knownQuoteIsReturned() {
        when(gateway.findQuote("Q1"))
                .thenReturn(Optional.of("Quote 1"));

        assertThat(quoteService.text("Q1")).isEqualTo("Quote 1");
        verify(gateway).findQuote("Q1");
    }

    @Test
    void missingQuoteUsesFallback() {
        when(gateway.findQuote("MISSING"))
                .thenReturn(Optional.empty());

        assertThat(quoteService.text("MISSING")).isEqualTo("NOT_FOUND");
        verify(gateway).findQuote("MISSING");
    }
}
~~~

**Step-by-step analysis:**

1. Spring TestContext finds `ResetDemoApplication`, builds the application context, and replaces the `QuoteGateway` bean with the mock supplied by `@MockBean`.
2. `QuoteService` remains a **real bean**; its dependency is the mock `QuoteGateway`.
3. Each `@Test` receives the exact same setup model without depending on any other `@Test` result.
4. Before every test, `@BeforeEach` checks that the mock has zero prior interactions and zero stubs. Under default settings, Boot's Mockito integration resets after preceding tests. If Spring creates a fresh context instead, the mock also starts clean; tests **should never rely on mock identity across tests**.
5. `knownQuoteIsReturned()` stubs `Q1`, calls the service, and verifies both the return value and the gateway call.
6. `missingQuoteUsesFallback()` sets its own stub for `MISSING` without relying on Q1's configuration.

**JUnit Jupiter guarantees no execution order between these two tests.** The suite does not require `knownQuoteIsReturned` to run before `missingQuoteUsesFallback`; both must pass standalone, in reversed order, or in the full suite.

**Important:** if other application beans call `QuoteGateway` during context startup or auto-setup, `verifyNoInteractions()` in `@BeforeEach` may no longer hold in that application. That assertion fits **this simple sample project**; in real systems, identify which interactions belong to the test contract.

### 5.4. Unit test: `MockitoExtension`, no `@MockBean` reset needed

**src/test/java/demo/reset/QuoteServiceUnitTest.java**

~~~java
package demo.reset;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class QuoteServiceUnitTest {

    @Mock
    QuoteGateway gateway;

    @InjectMocks
    QuoteService quoteService;

    @Test
    void readsFoundQuote() {
        when(gateway.findQuote("Q2"))
                .thenReturn(Optional.of("Quote 2"));

        assertThat(quoteService.text("Q2")).isEqualTo("Quote 2");
        verify(gateway).findQuote("Q2");
    }

    @Test
    void returnsFallbackForUnknownCode() {
        when(gateway.findQuote("UNKNOWN"))
                .thenReturn(Optional.empty());

        assertThat(quoteService.text("UNKNOWN"))
                .isEqualTo("NOT_FOUND");
        verify(gateway).findQuote("UNKNOWN");
    }
}
~~~

Here **`@Mock` is a Mockito mock, not a bean in `ApplicationContext`**, and `@InjectMocks` constructs the system under test with the mock dependency. Under Jupiter's `PER_METHOD` lifecycle, each test gets a brand-new fixture prepared by `MockitoExtension`. Neither `@SpringBootTest` nor manual `Mockito.reset` in `@AfterEach` is needed for isolation.

Do not confuse them:
- `@Mock` **does not replace beans** if you run `@SpringBootTest` and autowire `QuoteService` from the Spring context.
- `@MockBean` is Spring Boot 3.3's mechanism to **inject a mock into the context and replace/register a bean**.
- Never attach both `@Mock` and `@MockBean` to the same dependency without knowing exactly which instance the service receives.

## 6. Empirical comparison of `Mockito.reset` and `clearInvocations`

**src/test/java/demo/reset/MockitoResetSemanticsTest.java**

~~~java
package demo.reset;

import java.util.Optional;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockingDetails;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class MockitoResetSemanticsTest {

    @Test
    void clearInvocationsPreservesStubbing() {
        QuoteGateway gateway = mock(QuoteGateway.class);
        when(gateway.findQuote("Q1"))
                .thenReturn(Optional.of("Quote 1"));

        assertThat(gateway.findQuote("Q1"))
                .contains("Quote 1");

        clearInvocations(gateway);

        verifyNoInteractions(gateway);
        assertThat(mockingDetails(gateway).getStubbings())
                .hasSize(1);

        // Stub remains active after clearing only call history.
        assertThat(gateway.findQuote("Q1"))
                .contains("Quote 1");
    }

    @Test
    void resetRemovesStubbingAndInvocations() {
        QuoteGateway gateway = mock(QuoteGateway.class);
        when(gateway.findQuote("Q1"))
                .thenReturn(Optional.of("Quote 1"));

        assertThat(gateway.findQuote("Q1"))
                .contains("Quote 1");

        reset(gateway);

        verifyNoInteractions(gateway);
        assertThat(mockingDetails(gateway).getStubbings())
                .isEmpty();

        // With Mockito default answer, unstubbed Optional -> empty.
        assertThat(gateway.findQuote("Q1")).isEmpty();
    }
}
~~~

This illustrates the **semantics of both APIs**, not a recommendation to call them in every test. `reset` wipes both the stub returning `"Quote 1"` and past invocations. `clearInvocations` lets a test start verifying a fresh interaction phase while **keeping existing stubs**. If the goal is keeping subsequent tests completely independent, `clearInvocations` **is not enough** to remove prior stubbing.

With Spring Boot `@MockBean`, rely on **automatic reset** rather than repeating `reset(gateway)` in `@AfterEach`. In unit tests using `MockitoExtension`, give each test its own fixture.

## 7. `BEFORE`, `AFTER`, `NONE`: when to pick each mode?

All three values below come from Spring Boot 3.3's **`org.springframework.boot.test.mock.mockito.MockReset`**:

~~~java
// Default: equivalent to reset = MockReset.AFTER.
@MockBean
QuoteGateway gateway;

// Illustrative alternatives only:
// @MockBean(reset = MockReset.BEFORE) QuoteGateway gateway;
// @MockBean(reset = MockReset.NONE)   QuoteGateway gateway;
~~~

These are illustrative field snippets; do not declare three fields all named `gateway` in one real class. When using `BEFORE` or `NONE`, import `MockReset` from the proper Spring Boot 3.3 package.

**`AFTER` — the default worth keeping:** a test sets up stubs, runs assertions, and Spring Boot resets the mock afterward. The next test never sees old stubs. This is simple and built into the framework.

**`BEFORE` — reset right at the start:** useful when test setup/checks demand a clean state at the beginning of each run. It can also help reset a mock that retained state from earlier work, though if concurrent background work shares the context, unexpected resets signal a test-architecture problem to fix.

**`NONE` — no automatic reset:** use only with strong justification, such as preserving shared stubbing under tight control with explicit cleanup. With cached contexts, this easily introduces test-order coupling. `NONE` **does not prevent programmatic reset**; it merely disables automatic reset from this integration.

**Never choose `NONE` to silence a Mockito `UnnecessaryStubbingException`** or to "keep all calls around for an end-of-suite verify." Such workarounds couple tests together and break parallel execution. For multi-step flows, write one clear test covering the phases and business assertions, or separate scenarios at the right abstraction.

## 8. Real state on singleton beans is not reset by Mockito

A Spring bean can hold its own state:

~~~java
@Component
class SequenceService {
    private final AtomicInteger sequence = new AtomicInteger();

    int next() {
        return sequence.incrementAndGet();
    }
}
~~~

This snippet is illustrative only; it needs `Component` and `AtomicInteger` imports inside a valid Java file. If two tests share the singleton `SequenceService` from the context cache, the first test might get `1` from `next()` and the second `2`. **No `@MockBean` automatically resets `SequenceService`'s `AtomicInteger`.**

Similar cases:
- A `FakeGateway` storing mock data in a `Map`.
- `@Cacheable` storing entries in a real `CacheManager`.
- A bean holding sessions, queues, or counters in fields.
- A `static Set` used as a fixture.
- A JPA repository reading a database populated by earlier tests.

**Best practice when possible:** keep business services **stateless**, leaving state in explicitly managed repositories/caches. For stateful fakes, provide a test-only clear method or instantiate a fresh fake per test. Use `@DirtiesContext` only when a fresh context is truly necessary, never as a first resort.

### 8.1. Example: stateful bean explicitly cleaned in `@BeforeEach`

**src/test/java/demo/reset/SharedStateIsolationTest.java**

~~~java
package demo.reset;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class SharedStateIsolationTest {

    @Autowired
    TestCounter counter;

    @BeforeEach
    void cleanMutableState() {
        counter.clear();
    }

    @Test
    void firstIndependentScenario() {
        assertThat(counter.next()).isEqualTo(1);
    }

    @Test
    void secondIndependentScenario() {
        assertThat(counter.next()).isEqualTo(1);
    }

    static final class TestCounter {
        private int count;

        synchronized int next() {
            return ++count;
        }

        synchronized void clear() {
            count = 0;
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class CounterTestConfig {

        @Bean
        TestCounter testCounter() {
            return new TestCounter();
        }
    }
}
~~~

In standard Spring Boot tests, a nested static `@TestConfiguration` **adds test beans** to the application context. Because `TestCounter` is a singleton test bean, it can retain `count` across tests if the context is reused. Each `@BeforeEach` resets `count` to 0; both tests can run independently in any order and get 1.

**Do not copy `reset()` methods onto every production service merely to appease tests.** Here `TestCounter` lives entirely in test sources; for real business data, rely on fresh fixtures, transaction rollbacks, test cache-clearing APIs, or stateless design. `synchronized` prevents basic data races on the counter, yet **does not make shared resetting safe if two tests using this bean run concurrently**.

### 8.2. When is `@DirtiesContext` appropriate?

If state truly resides in the context and cannot be restored reliably, Spring lets you mark the context "dirty":

~~~java
// On a test class; this is an illustrative configuration.
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class StatefulIntegrationTest {
    // Each test can cause the context to be evicted from cache.
}
~~~

This snippet is not a standalone Java file; it requires importing `org.springframework.test.annotation.DirtiesContext` and related test/context annotations.

With `classMode = AFTER_EACH_TEST_METHOD`, Spring closes and evicts the context after every method, forcing subsequent tests to reload a context when needed. **Cost:** slower startup, potentially impacting other tests sharing the cache key. Never use `@DirtiesContext` as an "expensive manual mock reset" since `@MockBean` already resets properly. If only a single test mutates state irreversibly, mark just that test method instead of the entire class.

### 8.3. Databases and external services

**`@Transactional` on Spring tests** usually rolls back database changes executed inside the **test-managed transaction** after the test. It does not guarantee cleanup of:
- Transactions running on other threads, `@Async` tasks, or workflows opening separate transactions.
- Data already committed outside the test's transaction.
- Sent messages, entries in non-DB caches, files, HTTP calls, or third-party state.
- ID sequences, which may continue incrementing despite rollbacks depending on the database.

When testing across HTTP and databases, define clear boundaries: use `@Sql` setup/cleanup, controlled transactions, isolated schemas, Testcontainers, fake servers, or cache reset hooks. **Never assume `Mockito.reset` cleans those up.**

## 9. Why Spring's context cache causes "passes alone, fails in suite"

The **Spring TestContext Framework** reuses `ApplicationContext` instances across compatible test configurations to avoid restarting Spring on every `@Test`. That speeds up suites while letting singletons and test beans outlive individual test methods.

Factors influencing the context cache key include configuration classes, active profiles, test properties, context customizers (including mock bean configs), context hierarchies, and bootstrap options. Never assume a single shared instance everywhere: differing test configurations produce separate contexts.

Leakage symptoms:
- Test B fails after Test A runs, yet passes in isolation.
- Different test ordering or IDEs yield different results.
- Caches or fakes return stale data from prior runs.
- `verifyNoMoreInteractions()` sees calls from another test when a mock uses `NONE` or reset listeners were disabled.
- Tests leave static mutable fields unreset, especially under `@TestInstance(PER_CLASS)`.

Identifying the **exact state layer**:
1. If Mockito verification reports old invocations: inspect **`MockReset` mode, Mockito extensions/sessions, and lifecycle**.
2. If services return stale data despite clean mocks: search caches, singleton mutable state, static fields, or repositories.
3. If DB rows come from another test: inspect transaction boundaries and cleanup.
4. If failures happen only under parallel runs: inspect test concurrency and shared fixtures rather than adding more resets.
5. If `@DirtiesContext` makes the failure vanish: that is a **symptom of context-bound state/lifecycle**, not proof of what state leaked or a true root-cause fix.

**Never write order-dependent tests** like "Test A creates data for Test B," unless it is an explicitly orchestrated integration scenario within one test/workflow. A healthy suite lets you run tests individually or selectively without another test "paving the way."

## 10. JUnit Jupiter: `PER_METHOD`, `PER_CLASS`, `@BeforeEach`, and `@AfterEach`

JUnit Jupiter defaults to **`@TestInstance(Lifecycle.PER_METHOD)`**, creating a fresh test class instance per method. Regular fields on the test class are thus recreated each time. With **`@TestInstance(PER_CLASS)`**, one test class instance persists across all test methods; mutable fields on that instance must be managed carefully.

Example:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class OrderDependentTest {
    private int attempts = 0;

    @Test
    void firstExample() {
        attempts++;
    }

    @Test
    void secondExample() {
        attempts++;
    }
}
~~~

This snippet illustrates the idea and requires JUnit imports; do not add it to a passing suite because it **intentionally introduces cross-test state**. `attempts` in one test depends on which tests ran earlier; naming methods first/second does not enforce order. Under default `@TestInstance(PER_METHOD)`, `attempts` belongs to each new instance; however, **`static` fields** remain shared across the JVM, and **Spring singletons** remain shared via context caching regardless of `PER_METHOD`.

**`@BeforeEach` and `@AfterEach`** handle fixture setup and cleanup. Keep in mind:
- If fixtures can be freshly constructed per test, prefer creating them in `@BeforeEach` or inside the test rather than resetting old objects.
- `@BeforeEach` only cleans what that code explicitly touches; it never clears DB/Redis/caches unless programmed to do so.
- If a test throws an exception, Jupiter still runs lifecycle callbacks per framework rules, though killing the JVM or crashing infrastructure can skip cleanup.
- With Spring Boot `@MockBean` defaulting to `AFTER`, you normally **do not need an `@AfterEach` calling `Mockito.reset(mock)`**. Doing so introduces unnecessary callback-order dependencies.

## 11. Spies and mutable objects: Mockito reset does not reset real state

Spies differ from regular mocks because they **call real methods** unless stubbed. Consider a `@SpyBean` wrapping a counting bean:

~~~java
// Conceptual example, not a standalone program:
@SpyBean
SequenceService sequenceService;
~~~

When Spring Boot resets the Mockito spy after each test, Mockito clears invocations and stubs attached to the spy. Yet if the real `SequenceService` has an `AtomicInteger` already incremented to 7, **resetting the spy does not reset that field to 0**. The next real method call still returns 8. That is a frequent cause of state leakage even when using `@SpyBean` with default resets.

**When stubbing a spy:**
- `when(spy.realMethod())` can invoke the real method during stub setup, triggering side effects.
- Use `doReturn(value).when(spy).realMethod(...)` when avoiding real method execution during setup.
- When using a spy to test real logic plus track interactions, design a separate strategy to clear real state; Mockito only manages Mockito metadata.

Where real dependency behavior is unnecessary, **`@MockBean`** isolates far more cleanly than `@SpyBean`. Use spies intentionally—never as "a stronger mock."

## 12. `MockReset`, strict stubbing, and `verifyNoMoreInteractions`

These concepts serve distinct purposes:

| Mechanism | Question answered | Alters application state? |
|---|---|---|
| **`MockReset.AFTER/BEFORE`** | When is a reused mock bean's state cleared? | No |
| **Mockito `STRICT_STUBS`** | Are stubbings actually needed and matching arguments? | No |
| **`verify(mock).call(...)`** | Did a specific interaction occur? | No |
| **`verifyNoInteractions(mock)`** | Was the mock completely untouched in this scope? | No |
| **`verifyNoMoreInteractions(mock)`** | Are there any unverified interactions remaining? | No |
| **`@DirtiesContext`** | Should the context be evicted from cache and reloaded? | Rebuilds context, does not clean external systems |
| **`@Transactional` rollback** | Do DB changes in the test transaction roll back? | Yes, within the matching transaction boundary |

A `@MockBean` can reset flawlessly while tests still fail due to wrong logic. Conversely, unit tests with valid assertions can still fail under `STRICT_STUBS` due to unused stubs. Never use reset to "sweep away" strict-stubbing errors; remove/move unused stubs and fix mismatches properly.

**`verifyNoMoreInteractions`** inspects unverified invocations at the moment it runs. Resetting before verification destroys interaction evidence and can produce false passes. Never reset until all needed assertions and verifications finish. In our example, Spring Boot resets **after each test**, aligning with that rule.

## 13. Designing tests for parallel execution

Even proper reset modes do not make a mutable bean inherently thread-safe when multiple tests execute concurrently against the **same context**:

~~~text
Test A: stub gateway.findQuote("Q1")
             |
             |             Test B: reset/mock setup
             |                        |
             v                        v
Test A: calls service expecting Q1   Test B: verifies something else
~~~

If tests share a mock and **truly run concurrently**, resets or stubs from Test B can interfere with Test A. Test frameworks offer concurrency controls, though actual behavior depends on JUnit/Gradle config and context usage.

Mitigations:
- Prefer **unit tests with per-method mocks**, avoiding shared singleton mocks.
- For stateful Spring context tests, keep tests sharing mutable fixtures **non-parallel** or explicitly isolate contexts/data.
- When restricting concurrency in JUnit Jupiter, look at **`@ResourceLock`** or **`@Execution(SAME_THREAD)`** scoped appropriately; apply annotations consistently to every test sharing the resource.
- Do not treat `synchronized` on a reset helper as sufficient to guard the whole "reset → stub → call → assert" sequence when another test can interleave.
- For external systems, isolate schemas, databases/containers, topics, or key namespaces per test where suitable; avoid uncontrolled shared mutable resources.

JUnit Jupiter projects normally run sequentially unless parallel execution is enabled, yet never assume CI and IDEs share identical defaults. Stable suites declare concurrency constraints explicitly when relying on them.

## 14. Common failures and investigation guide

| Symptom | Possible cause | Solution |
|---|---|---|
| Test B sees Test A's stubs | `@MockBean(reset = NONE)`, shared non-Spring mock, or reset listener disabled | Restore default `AFTER`/`BEFORE` reset; check test lifecycle |
| `verifyNoInteractions` fails at test start | Mock had prior calls or startup beans called dependency | Trace invocation source; assert only business-required interactions |
| `clearInvocations` still returns old stub | `clearInvocations` **keeps stubbings** | Use `reset` when truly needed, or instantiate fresh mocks |
| `reset(mock)` makes `verify(...)` miss calls | Reset wiped interaction history | Move `verify` before reset or remove manual reset |
| `@Mock` works in unit test, `@Autowired` service still uses real bean | Mockito `@Mock` is not Spring `@MockBean` | Use `@MockBean` in Spring contexts or pass unit mocks directly |
| `@MockBean` resets yet cache returns old data | Real cache/singleton was not cleared | Clear caches/fixtures as needed, not just mocks |
| `@SpyBean` resets yet counter keeps rising | Spy wraps real object holding mutable fields | Clean real state or use fresh mocks/fakes |
| `@DirtiesContext` slows down the suite | Repeatedly reloads contexts, bypassing cache | Limit its scope; set up independent test data |
| Test passes alone, fails in suite | Shared state, ordering, database, or concurrency | Locate state owner and reset at the proper boundary |
| Test fails under parallel runs | Concurrent tests resetting/stubbing shared mock or singleton | Separate fixtures/contexts or constrain parallelism |
| `@Transactional` test leaves rows behind | Writes ran outside test transaction or outside DB | Clean up outside transaction or use isolated environments |
| Unused stub causes `UnnecessaryStubbingException` | Stub unused by code, unrelated to `MockReset` | Remove unused stub / fix test rather than lowering strictness |

**Practical investigation checklist:**

1. **Identify mock type:** `@Mock`, `@MockBean`, `@SpyBean`, or manually created `@Bean` mock?
2. **Identify lifecycle:** JUnit `PER_METHOD`/`PER_CLASS`, `MockitoExtension`, Spring TestContext, context caching?
3. **Check reset mode:** In Spring Boot 3.3 `@MockBean`, default is `AFTER`; did someone change it to `NONE`?
4. **Inspect history and stubbings:** `mockingDetails(mock).getStubbings()`, `verifyNoInteractions`, `verify(...)`, actual stack traces.
5. **Hunt non-mock state:** statics, singleton fields, caches, persistence, sessions, queues, files, system properties.
6. **Check concurrency:** Do concurrent tests share the same context and mock?
7. **Apply minimal fix:** stub per test; clear state at its owner; create fresh fixtures; reserve `@DirtiesContext` for state that cannot be reliably reset.
8. **Rerun the suite:** execute tests individually and together via CI commands, inspecting reports and skipped tests.

Never reflexively multiply resets simply because a test flakes occasionally. The more reset hooks a test needs without clear justification, the more its abstraction and test level need rethinking.

## 15. Running the example and checking results

In the directory containing `build.gradle`, if the project has a Gradle Wrapper:

~~~bash
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Without a Wrapper, use an installed compatible Gradle to generate one or run **`gradle test`**. The example files contain all production and test source, though `./gradlew` only works if wrapper files are present.

The example suite contains **8 `@Test` methods**:
- **2** `@MockBean` tests checking isolated stubbings and invocation history.
- **2** unit tests using `MockitoExtension` and isolated mocks.
- **2** tests demonstrating `reset(...)` and `clearInvocations(...)`.
- **2** tests of a stateful singleton test bean cleared in `@BeforeEach`.

All are designed to PASS; there are no intentional failure tests to toggle on or off. Inspect actual results in **`build/reports/tests/test/index.html`**. Those counts match the sample files assuming no extra tests were added; real projects will differ.

You can target individual classes to observe:

~~~bash
./gradlew test --tests demo.reset.QuoteServiceWithMockBeanTest
./gradlew test --tests demo.reset.MockitoResetSemanticsTest
./gradlew test --tests demo.reset.SharedStateIsolationTest
~~~

Always run the build's **`test`** command in CI rather than trusting green IDE icons alone. When a test depends on leftover state from another test, running a single class or shuffling execution order quickly exposes the flaw.

## 16. Newer version note: `@MockitoBean` replacing `@MockBean`

To avoid doc mismatches during upgrades:

- This lesson's examples use **Spring Boot 3.3.5**, hence **`org.springframework.boot.test.mock.mockito.MockBean`**, **`org.springframework.boot.test.mock.mockito.MockReset`**, and Spring Boot's corresponding reset infrastructure.
- **Spring Boot 3.4** deprecates the old-package `@MockBean`/`@SpyBean` and `MockReset` in favor of **Spring Framework 6.2**'s bean override mechanism, featuring **`org.springframework.test.context.bean.override.mockito.MockitoBean`**, **`MockitoSpyBean`**, and `MockReset` in the new package.
- When upgrading, match exact annotations, imports, bean selection rules, and `TestExecutionListener`s to your Spring Framework version. Never copy Boot 3.3's `@MockBean` blindly into newer apps as a long-term pattern.
- Core principles **remain unchanged**: tests must isolate stubbings, invocations, and application state; renaming annotations does not turn singletons, caches, or databases stateless.

In upgraded projects, consult Spring Framework documentation for `@MockitoBean`/`@MockitoSpyBean` before altering config, since override policies and supported declaration sites differ from the legacy API. Never mix both annotation families in one test class hoping for the best.

## 17. Summary of principles

- **Never call `Mockito.reset` reflexively.** Unit tests with `@Mock` + `MockitoExtension` rarely need resets when every test builds independent fixtures.
- In **Spring Boot 3.3, `@MockBean` resets `AFTER` each test method by default**. `BEFORE`/`NONE` are configurable, though `NONE` easily leaks stubs and invocations across cached contexts.
- **`reset(mock)` clears both stubbings and invocations**; **`clearInvocations(mock)` clears only invocations**, so the two are not interchangeable.
- **`@SpyBean`** resets Mockito metadata, yet **never clears field state on the underlying real object**.
- **ApplicationContext caching** speeds up tests while reusing singleton beans; resetting mocks does not reset caches, static fields, or databases.
- Favor **stateless services, fresh fixtures, and cleanup at the state owner**. Reserve `@DirtiesContext` for when a fresh context is truly necessary, given its cost.
- Never rely on lucky test ordering or concurrency. Test classes standalone and as a suite, verifying behavior against specifications.

**Self-check:** A Spring Boot test declares `@MockBean(reset = MockReset.NONE)` and stubs `gateway.findQuote("Q1")`; a later test calls `"Q1"` without stubbing. Why might its result be affected? Would adding `clearInvocations(gateway)` at the end of the first test fix it? **Answer:** The shared mock in the cached context still holds the stubbing; `clearInvocations` clears call history, **not stubs**. Use automatic `AFTER`/`BEFORE` reset or independent fixtures. If failures persist due to a singleton counter, locate and clear that bean's real state.

## 18. References

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) — `@MockBean` and automatic reset between tests.
- [Spring Boot 3.3 — MockBean Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/MockBean.html) — `reset` attribute and `AFTER` default.
- [Spring Boot 3.3 — MockReset Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/MockReset.html) — `BEFORE`, `AFTER`, `NONE`.
- [Mockito 5 — Mockito.reset and clearInvocations](https://javadoc.io/doc/org.mockito/mockito-core/5.16.0/org.mockito/org/mockito/Mockito.html) — difference between clearing stubs and clearing interactions.
- [Spring Framework — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html) — modern Spring Framework approach.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html) — why Spring reuses `ApplicationContext` instances within suites.
