# Wrong Mockito Stubbing, Unused Mocks, or Verifying at the Wrong Time

## 1. Problem: Tests Fail Even When Business Logic Looks Right

In Java/Spring Boot testing, Mockito replaces external dependencies with **test doubles**: repositories, HTTP clients, message senders, and payment adapters. Yet misconfiguring mocks causes tests to fail not because business code is broken, but because **test setup, the object under test, arguments, or verification timing do not match**.

Common errors:

- `UnnecessaryStubbingException`: `when(...).thenReturn(...)` was configured, yet the execution path never invoked that stub.
- `PotentialStubbingProblem`: code called a method with an argument different from the stubbed one under strict stubbing.
- `Wanted but not invoked`: Mockito recorded no interaction matching `verify(...)`.
- `TooManyActualInvocations` or `NeverWantedButInvoked`: actual call count differed from `times(1)` or `never()`.
- `InvalidUseOfMatchersException`: matchers and raw values mixed improperly, or matchers used outside stubbing/verification.
- `NotAMockException`: passing a real object or a different proxy to `verify/reset/when` incorrectly.
- `WrongTypeOfReturnValue`: stub returns an incompatible type, or a spy ran its real method unexpectedly.
- Stubbing declared on **mock A**, while the real `service` holds **bean B** or a separate instance; verifying A always sees 0 invocations.
- `verify` executes **before** a `CompletableFuture`, `@Async` task, listener, or HTTP request finishes.
- A `@Spy` stubbed via `when(spy.method())` runs the real method **during stub setup**, causing I/O, state mutation, or an exception.
- Mockito defaults unstubbed methods to `null`, `false`, `0`, or empty defaults, steering tests down unintended branches.

This lesson is part of **Test Troubleshooting**, titled **"Wrong Mockito stubbing, unused mocks, or verifying at the wrong time."** Examples use **Java 17+**, **Spring Boot 3.3.5**, **JUnit Jupiter**, and Mockito 5 provided by Spring Boot dependency management. Part of the tests are pure Mockito unit tests; others use `@SpringBootTest` and `@MockBean` matching Spring Boot 3.3.

### After This Lesson, You Will Be Able To

1. Distinguish **stubbing**, **invocation**, and **verification**.
2. Diagnose `UnnecessaryStubbingException`, `PotentialStubbingProblem`, `WantedButNotInvoked`, and `TooManyActualInvocations`.
3. Declare `@Mock`, `@ExtendWith(MockitoExtension.class)`, and inject the exact dependencies used by the subject under test.
4. Use `when(...).thenReturn(...)`, `thenThrow(...)`, and `doThrow(...).when(...)` for the right method signatures.
5. Use `any()`, `anyString()`, `eq()`, `isNull()`, and `ArgumentCaptor` without weakening contracts.
6. Verify invocation counts with `times`, `never`, `atLeastOnce`, and call ordering with `InOrder`.
7. Understand `STRICT_STUBS`, minimal stubbing, and why `lenient` must not be enabled suite-wide.
8. Know when to use `doReturn(...).when(spy)` to avoid invoking real methods during setup.
9. Contrast `@Mock`/`@InjectMocks` with `@MockBean` inside a Spring `ApplicationContext`.
10. Verify async work after waiting on a bounded **completion signal**, and understand the limits of `Mockito.timeout(...)`/`after(...)`.
11. Confirm the mock actually belongs to the object under test and diagnose proxies, Spring context caching, and resets.
12. Follow an evidence-based troubleshooting checklist before changing expected assertions.

**Version note:** Spring Boot 3.3 uses `org.springframework.boot.test.mock.mockito.MockBean`. `@MockitoBean` belongs to Spring Framework 6.2 and newer Boot lines, so it is **not the corresponding annotation in this Boot 3.3.5 project**.

## 2. Three Distinct Actions: Stub, Call, Verify

```text
TEST SETUP                         CODE UNDER TEST                     ASSERTION
  @Mock InventoryClient
       |
  when(inventory.find("SKU-1"))
       .thenReturn(Optional.of(...))
       |                                 service.reserve("SKU-1", 2)
       |                                       |
       +--------- mock records <---------------+-- inventory.find("SKU-1")
                                                 |
                                            service computes
                                                 |
                                               repo.save(...)
                                                                           |
                                                            verify(inventory).find("SKU-1")
                                                            verify(repo).save(...)
```

**Stubbing** defines *what a mock returns or throws if invoked accordingly*. It **does not invoke business methods**, does not confirm code used the stub, and does not prove side effects occurred.

**Invocation** is the subject under test actually calling the mock during execution. Mockito records method, arguments, and interaction order.

**Verification** inspects invocation history at **the moment `verify` runs**. `verify(mock).method(...)` defaults to `verify(mock, times(1)).method(...)`. It does not wait for background jobs or future callbacks unless a timed verification mode is used—and even verification timeouts are not business-completion guarantees.

### A Common Mistake

```java
when(inventory.find("SKU-1"))
        .thenReturn(Optional.of(new Stock("SKU-1", 10)));

// Forgot to call service.reserve(...).

verify(inventory).find("SKU-1"); // Wanted but not invoked.
```

This is an **illustrative error snippet**, not among the tests expected to pass in the project. The call inside `when` merely **configures the stub**; it does not count as a business invocation to verify.

## 3. Symptom Matrix and First Questions to Ask

| Message | First Diagnostic Question | Fix Direction |
| --- | --- | --- |
| `UnnecessaryStubbingException` | Does this test branch actually call the stub? | Remove or move stub into the test that needs it |
| `PotentialStubbingProblem` | Do actual arguments differ from the stub? | Compare invocation vs stub, fix stub or code |
| `Wanted but not invoked` | Did code reach the call? Same mock instance? | Trace branch/injection; do not add `times(0)` |
| `Arguments are different!` | `equals`, whitespace, object identity, nullability? | Assert/capture argument per contract |
| `TooManyActualInvocations` | Did a retry, loop, or listener call multiple times? | Confirm expected attempts; do not tweak `times` blindly |
| `NeverWantedButInvoked` | Did an unexpected branch execute? | Inspect branch and timing |
| `InvalidUseOfMatchersException` | Mixed matchers with raw args? | Wrap fixed values in `eq` |
| `WrongTypeOfReturnValue` | Wrong return type or spy ran real method? | Check generics/overloads and `doReturn` |
| `NotAMockException` | Is the verified variable actually a Mockito mock? | Verify the right mock/proxy, not a real object |
| `NullPointerException` on result | Unstubbed method or wrong branch? | Stub the right method/args or handle nulls |
| Unit test green, Spring test verifies 0 | `service` holds a real bean or another instance | Use `@MockBean` matching context/type/qualifier |
| Async verify fails intermittently | Assertion ran before background work finished | Await future/latch/observable state |
| Spy triggers network call during setup | Used `when(spy.realCall())` | Use `doReturn(...).when(spy)` |
| `verifyNoMoreInteractions` turns red easily | Test locks down trivial helper calls | Verify only contract-critical interactions |

The same exception can have multiple causes; always read the **stack trace and actual interactions list** printed by Mockito before changing expected counts.

## 4. When to Choose Unit Tests vs Spring Integration Tests?

| Goal | Tool | What the Test Proves |
| --- | --- | --- |
| Service calls right repository/client | `MockitoExtension`, `@Mock` | Invocations and business branches |
| Service skips repository when validation fails | `verifyNoInteractions` | No side effects at the mock boundary |
| Inspect passed argument fields | `ArgumentCaptor` | Exact object/fields sent to save/publish |
| Ordering across dependency calls | `InOrder` | Relative invocation order |
| Spy on a legacy implementation | `spy` + `doReturn` | Partial mocking / real-method interactions |
| Async callback invokes mock after completion | `CompletableFuture`/latch | Completion boundary + interaction |
| Bean inside Spring context replaced by mock | `@SpringBootTest` + `@MockBean` | Spring bean wiring and proxy context |
| HTTP controller delegates to service | `@WebMvcTest` + `@MockBean`/`MockMvc` | Request mapping and service delegation |
| Real DB queries and transactions | Testcontainers/`@DataJpaTest`/JDBC integration | Real DB behavior, not just mock calls |

**Do not boot all of Spring Boot** just to test a Java method taking two dependency interfaces. Equally, never use plain Mockito `@Mock` and assume a bean inside `@SpringBootTest` was replaced; they are distinct mechanisms.

## 5. Sample Project: File Layout

The example builds a `ReservationService` that queries `InventoryClient` and writes to `ReservationRepository` when stock is sufficient. It highlights short-circuit branches, verify counts, `ArgumentCaptor`, and repository failures. The async part adds `DeferredPublisher` and `EventSink` with an injected executor.

```text
mockito-diagnostics-lab/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/mockdiagnostics/
│   ├── MockitoDiagnosticsApplication.java
│   ├── Stock.java
│   ├── Reservation.java
│   ├── InventoryClient.java
│   ├── ReservationRepository.java
│   ├── ReservationService.java
│   ├── StatefulFormatter.java
│   ├── EventSink.java
│   └── DeferredPublisher.java
└── src/test/java/com/example/mockdiagnostics/
    ├── ReservationServiceTest.java
    ├── SpyDiagnosticsTest.java
    ├── AsyncVerificationTest.java
    └── ReservationServiceSpringTest.java
```

All Java files share one package to keep imports concise. The project uses **Java 17** and Spring Boot 3.3.5, requiring no H2, Docker, Kafka, or HTTP server. `@SpringBootApplication` registers two simple default adapters so the context can boot in the example; Spring tests replace them via `@MockBean`.

## 6. `settings.gradle` and `build.gradle`

`settings.gradle`:

```groovy
rootProject.name = 'mockito-diagnostics-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat =
            org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
}
```

`spring-boot-starter-test` includes Mockito, Mockito JUnit Jupiter integration, JUnit Jupiter, AssertJ, and Spring Test. The Spring Boot BOM keeps versions aligned; do not force an incompatible Mockito major version because of an old StackOverflow snippet.

**If the Gradle Wrapper is missing**, `./gradlew` will not exist; use a compatible pre-installed Gradle binary or generate and commit the wrapper. That is a build-environment step, not a Mockito failure.

## 7. Minimal Spring Boot Application

`src/main/java/com/example/mockdiagnostics/MockitoDiagnosticsApplication.java`:

```java
package com.example.mockdiagnostics;

import java.util.Optional;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MockitoDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MockitoDiagnosticsApplication.class, args);
    }

    // Two demo adapters so the application can start
    // without a real inventory system or database.
    // Spring @MockBean replaces these two beans in tests.

    @Bean
    InventoryClient defaultInventoryClient() {
        return sku -> Optional.empty();
    }

    @Bean
    ReservationRepository defaultReservationRepository() {
        return reservation -> { };
    }
}
```

These are **lab-only dummy adapters**, not production inventory/repository designs. Production uses real HTTP/JDBC adapters tested at their integration boundaries. Defining **one bean** per interface lets `@MockBean InventoryClient` and `@MockBean ReservationRepository` replace them cleanly by type in Spring tests.

## 8. Domain Records and Dependency Contracts

`src/main/java/com/example/mockdiagnostics/Stock.java`:

```java
package com.example.mockdiagnostics;

public record Stock(String sku, int available) {
    public Stock {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku required");
        }
        if (available < 0) {
            throw new IllegalArgumentException("negative stock");
        }
    }
}
```

`src/main/java/com/example/mockdiagnostics/Reservation.java`:

```java
package com.example.mockdiagnostics;

public record Reservation(String sku, int units) {
    public Reservation {
        if (sku == null || sku.isBlank() || units <= 0) {
            throw new IllegalArgumentException("invalid reservation");
        }
    }
}
```

`src/main/java/com/example/mockdiagnostics/InventoryClient.java`:

```java
package com.example.mockdiagnostics;

import java.util.Optional;

public interface InventoryClient {
    Optional<Stock> find(String sku);
}
```

`src/main/java/com/example/mockdiagnostics/ReservationRepository.java`:

```java
package com.example.mockdiagnostics;

public interface ReservationRepository {
    void save(Reservation reservation);
}
```

Because `Reservation` is a **record**, it implements value-based `equals/hashCode` over its components; thus `verify(repository).save(new Reservation("SKU-1", 2))` compares by value rather than object identity. If you replace the record with a plain Java class lacking `equals`, verifying against a newly constructed instance will report an argument mismatch even with identical fields; in that case consider `ArgumentCaptor` or `argThat`.

## 9. `ReservationService`: Subject Under Test

`src/main/java/com/example/mockdiagnostics/ReservationService.java`:

```java
package com.example.mockdiagnostics;

import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public class ReservationService {

    private final InventoryClient inventory;
    private final ReservationRepository repository;

    public ReservationService(
            InventoryClient inventory,
            ReservationRepository repository) {
        this.inventory = Objects.requireNonNull(inventory);
        this.repository = Objects.requireNonNull(repository);
    }

    public Reservation reserve(String sku, int units) {
        if (sku == null || sku.isBlank() || units <= 0) {
            throw new IllegalArgumentException("invalid request");
        }

        Stock stock = inventory.find(sku)
                .orElseThrow(() ->
                        new InsufficientStockException(
                                "stock not found: " + sku));

        if (stock.available() < units) {
            throw new InsufficientStockException(
                    "not enough stock: " + sku);
        }

        Reservation result = new Reservation(sku, units);
        repository.save(result);
        return result;
    }

    public static final class InsufficientStockException
            extends RuntimeException {

        public InsufficientStockException(String message) {
            super(message);
        }
    }
}
```

### Every Branch Matters for Mockito

- **Invalid input**: throws before `inventory.find`. Stubbing `inventory` in such a test leaves the stub **unused** -> strict stubbing throws `UnnecessaryStubbingException`.
- **Not found**: calls `inventory` once, **never calls `repository`**.
- **Insufficient stock**: calls `inventory`, then throws without saving.
- **Success**: calls `inventory`, then `repository.save`, returns record.
- **Repository throws**: `inventory` then `repository` were called, exception propagates to caller; `verify` can still confirm the invocation before the throw.

There are no retries, async calls, or Spring transactions in this class. Therefore, in unit tests, calling `verify(...)` **right after `reserve` returns or throws** is the proper timing. Compare this later with the async section.

## 10. Unit Tests with `MockitoExtension` and Strict Stubbing

`src/test/java/com/example/mockdiagnostics/ReservationServiceTest.java`:

```java
package com.example.mockdiagnostics;

import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ReservationServiceTest {

    @Mock
    InventoryClient inventory;

    @Mock
    ReservationRepository repository;

    ReservationService service;

    @BeforeEach
    void setUp() {
        // Subject receives the exact two mocks created by MockitoExtension.
        service = new ReservationService(inventory, repository);
    }

    @Test
    void reservesWhenStockIsEnough() {
        when(inventory.find("SKU-1"))
                .thenReturn(Optional.of(new Stock("SKU-1", 8)));

        Reservation result = service.reserve("SKU-1", 2);

        assertEquals(new Reservation("SKU-1", 2), result);
        verify(inventory).find("SKU-1");
        verify(repository).save(new Reservation("SKU-1", 2));
        verifyNoMoreInteractions(inventory, repository);
    }

    @Test
    void lowStockDoesNotWrite() {
        when(inventory.find("SKU-2"))
                .thenReturn(Optional.of(new Stock("SKU-2", 1)));

        assertThrows(
                ReservationService.InsufficientStockException.class,
                () -> service.reserve("SKU-2", 3));

        verify(inventory).find("SKU-2");
        verify(repository, never()).save(any(Reservation.class));
    }

    @Test
    void missingSkuDoesNotWrite() {
        when(inventory.find("SKU-3"))
                .thenReturn(Optional.empty());

        assertThrows(
                ReservationService.InsufficientStockException.class,
                () -> service.reserve("SKU-3", 1));

        verify(inventory).find("SKU-3");
        verifyNoInteractions(repository);
    }

    @Test
    void invalidInputSkipsDependencies() {
        // No stub declared: validation branch must exit early.
        assertThrows(
                IllegalArgumentException.class,
                () -> service.reserve(" ", 1));

        assertThrows(
                IllegalArgumentException.class,
                () -> service.reserve("SKU-4", 0));

        verifyNoInteractions(inventory, repository);
    }

    @Test
    void captorInspectsSavedReservation() {
        when(inventory.find("SKU-5"))
                .thenReturn(Optional.of(new Stock("SKU-5", 6)));

        service.reserve("SKU-5", 4);

        ArgumentCaptor<Reservation> captor =
                ArgumentCaptor.forClass(Reservation.class);

        verify(repository).save(captor.capture());

        Reservation saved = captor.getValue();
        assertEquals("SKU-5", saved.sku());
        assertEquals(4, saved.units());
    }

    @Test
    void repeatedCallsRequireExplicitCount() {
        when(inventory.find("SKU-6"))
                .thenReturn(Optional.of(new Stock("SKU-6", 10)));

        service.reserve("SKU-6", 1);
        service.reserve("SKU-6", 2);

        verify(inventory, times(2)).find("SKU-6");
        verify(repository).save(new Reservation("SKU-6", 1));
        verify(repository).save(new Reservation("SKU-6", 2));
    }

    @Test
    void inOrderChecksRequiredSequence() {
        when(inventory.find("SKU-7"))
                .thenReturn(Optional.of(new Stock("SKU-7", 3)));

        service.reserve("SKU-7", 1);

        InOrder order = inOrder(inventory, repository);
        order.verify(inventory).find("SKU-7");
        order.verify(repository)
                .save(new Reservation("SKU-7", 1));
        order.verifyNoMoreInteractions();
    }

    @Test
    void repositoryFailureIsPropagated() {
        when(inventory.find("SKU-8"))
                .thenReturn(Optional.of(new Stock("SKU-8", 5)));

        doThrow(new IllegalStateException("storage unavailable"))
                .when(repository)
                .save(any(Reservation.class));

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> service.reserve("SKU-8", 2));

        assertEquals("storage unavailable", error.getMessage());
        verify(inventory).find("SKU-8");
        verify(repository).save(new Reservation("SKU-8", 2));
    }
}
```

**There are 8 `@Test` methods** in this unit test class. Each test stubs only what its branch actually invokes. `MockitoExtension` initializes `@Mock` fields before each method, and `@BeforeEach` passes those exact instances into the service.

### Closer Look at Verify Counts

`repeatedCallsRequireExplicitCount` calls `reserve` **twice**, so `inventory.find("SKU-6")` runs twice. Writing `verify(inventory).find("SKU-6")` defaults to **exactly once** and fails with too many invocations. `times(2)` is right because **the test intentionally triggers two calls**—never bump `times` to force a passing test if the service is retrying unexpectedly.

In the same test, `repository` receives **two distinct arguments**, once each; two separate `verify(repository).save(new Reservation(...))` statements are accurate. `verify(repository, times(2)).save(new Reservation("SKU-6", 1))` would be **wrong**, because that specific argument occurred only once.

### `@BeforeEach` Should Construct the Service, Not Stub Everything

`@BeforeEach` runs `new ReservationService(inventory, repository)` and **does not** do:

```java
when(inventory.find("SKU-1"))
    .thenReturn(Optional.of(new Stock("SKU-1", 10)));
```

for every test. Any validation test that throws before lookup would leave that stub unused, causing strict mode to fail at teardown even after business assertions pass. Declare stubbing inside the test that needs it; reserve `lenient` for well-understood exceptions.

## 11. Wrong Stubbed Arguments and `PotentialStubbingProblem`

Suppose a test exercises `SKU-10` yet mistakenly stubs `SKU-11`:

```java
when(inventory.find("SKU-11"))
    .thenReturn(Optional.of(new Stock("SKU-11", 5)));

service.reserve("SKU-10", 2);
```

This is an **intentionally broken snippet, outside the runnable tests**. Under `MockitoExtension`'s default `Strictness.STRICT_STUBS`, invoking a stubbed method with mismatched arguments throws `PotentialStubbingProblem`. Without strictness, the mock returns a default value for the unmatched call, sending code down the wrong branch and producing a confusing `NullPointerException` or domain error.

### Proper Fix

- Inspect the actual invocation in the failure message.
- Check whether the service normalizes, trims, or transforms identifiers.
- If the contract requires `"SKU-10"`, stub `"SKU-10"` and `verify(inventory).find("SKU-10")`.
- If the service legitimately accepts a range of valid arguments, use a tight matcher or controlled `thenAnswer`.
- Do not swap in `anyString()` just to silence red tests when the argument value is part of the contract under test.

Example with an explicit matcher:

```java
when(inventory.find(org.mockito.ArgumentMatchers.eq("SKU-10")))
    .thenReturn(Optional.of(new Stock("SKU-10", 5)));
```

This snippet assumes `inventory` mock, static/matcher import, and a test invoking that exact argument so it does not trigger unused stubbing.

### `PotentialStubbingProblem` Does Not Automatically Mean a Production Bug

Mockito flags this as a **potential mismatch**: if business branches validly call the same method with varying arguments, check whether the test over-specified its stubbing. When multiple scenario-dependent stubbings on the same method are genuinely required, `doReturn(...).when(mock)...` or `willReturn(...).given(mock)...` can avoid declaration-time ambiguity. Never switch the whole suite to `Strictness.LENIENT` as a first resort.

## 12. `UnnecessaryStubbingException`: Unused Stubs Can Be a Useful Signal

Illustrative broken example:

```java
when(inventory.find("SKU-1"))
    .thenReturn(Optional.of(new Stock("SKU-1", 8)));

// Invalid-input branch throws before calling inventory:
assertThrows(IllegalArgumentException.class,
    () -> service.reserve("", 2));
```

The business assertion passes, yet `MockitoExtension` catches the unused stub at the end of the test and fails with `UnnecessaryStubbingException`. Clean tests **delete the `when(...)` line**; there is no reason to mock behavior for an uncalled dependency.

Another example: a happy-path test declares three stubs yet needs only one:

```java
when(inventory.find("SKU-1")).thenReturn(Optional.of(...));
when(inventory.find("SKU-2")).thenReturn(Optional.of(...));
when(inventory.find("SKU-3")).thenReturn(Optional.of(...));

service.reserve("SKU-1", 1);
```

This is pseudocode with `...`, **not runnable**. Both `SKU-2` and `SKU-3` stubs are superfluous. Do not turn off Mockito's check; trim fixture setup that does not serve the scenario.

### When Is `lenient` Reasonable?

```java
lenient().when(inventory.find("SKU-COMMON"))
        .thenReturn(Optional.of(new Stock("SKU-COMMON", 1)));
```

This snippet requires static import `Mockito.lenient`. Leniency relaxes strict-stubbing checks **for that specific stub**, allowing it to go unused without failing. Still, it is a **last resort** when a complex shared fixture cannot reasonably be split, not a habit for every test.

Priority order:

1. Delete unused stubs.
2. Move stubs from `@BeforeEach` into the tests that actually invoke them.
3. Split fixtures/builders per scenario.
4. Replace overly narrow stubs with contract-appropriate matchers when justified.
5. Only with clear justification, place `lenient()` on a single stub and document why.
6. Avoid `@MockitoSettings(strictness=LENIENT)` across an entire test class when only one stub is awkward.

## 13. Default Answers and Unexpected `NullPointerException`s

A plain Mockito mock never runs the real implementation. For unstubbed methods:

- Reference types typically return `null`.
- Primitives default to `0`/`false`.
- Well-known types such as collections or `Optional` return empty defaults in modern Mockito.
- `void` methods are no-ops by default.
- Smart/deep stubs are specialized options unnecessary for most unit tests.

If code invokes `inventory.find("SKU-2")` while the test stubbed `"SKU-1"`, do not automatically assume it returns `null`: for an `Optional` return type, Mockito returns `Optional.empty()`. Tests then hit `InsufficientStockException` in our example—or `PotentialStubbingProblem` beforehand under strict mode. **Never infer the root cause from the final exception alone**; compare actual invocations against the stub list.

### Do Not Use `RETURNS_DEEP_STUBS` to Mask Design

`mock(Foo.class, RETURNS_DEEP_STUBS)` enables `when(foo.getBar().getBaz().value())...`, yet tightly couples tests to internal call chains, hinders refactoring, and hides null boundaries. Inject clean collaborators directly or instantiate real DTOs for simple value objects.

## 14. `ArgumentMatchers`: Use Uniformly and Tightly

Suppose a method takes two arguments, `publisher.send(channel, event)`:

**Wrong**:

```java
when(publisher.send(anyString(), "payload"))
    .thenReturn(true);
```

**Right**:

```java
when(publisher.send(anyString(), eq("payload")))
    .thenReturn(true);
```

Both snippets are **outside the runnable project** since `publisher.send` is illustrative. Whenever any argument in an invocation uses a matcher, every other argument in that same invocation must also use a matcher (`eq`, `any`, etc.).

### Matchers Are Not "Magic Values"

`anyString()` belongs inside mock stubbing/verification argument positions; it does not mean "generate a random string to pass into the service." Never write:

```java
service.reserve(anyString(), 2); // Wrong usage.
```

Matchers are a Mockito recording mechanism, not test data generators. Pass a concrete value like `"SKU-1"` to the code under test.

### Null Matching

In Mockito 5, `anyString()` matches **non-null** strings only, not `null`. To assert null, use `isNull()`, or `nullable(String.class)` when both null and non-null are valid per contract. Example:

```java
verify(inventory).find(isNull());
```

That snippet makes sense only if the code under test actually calls `inventory.find(null)`; `ReservationService` in this project **intentionally validates first**, so that call never occurs. Using a non-matching matcher to "verify null" on invalid input will rightly fail.

### Overloads and Generic Types

If an interface overloads `find(String)` and `find(UUID)`, bare `any()` can confuse overload resolution or bind the wrong overload. Prefer `anyString()` or `any(UUID.class)` with explicit types. For methods returning `Optional<List<T>>`, make sure `thenReturn(...)` matches the exact return type.

## 15. `void` Methods: `doThrow`/`doNothing` Instead of `when(...).thenReturn`

`ReservationRepository.save` returns `void`. This **does not compile**:

```java
when(repository.save(new Reservation("SKU-1", 2)))
    .thenThrow(new IllegalStateException());
```

Java cannot pass a `void` expression as an argument to `when`. The valid form is:

```java
doThrow(new IllegalStateException("storage unavailable"))
    .when(repository)
    .save(new Reservation("SKU-1", 2));
```

To leave a mock's void method doing nothing, you rarely need `doNothing` because void mocks are no-ops by default. `doNothing().when(spy).dangerousVoid()` *is* useful to prevent a spy from running a real side effect. `doAnswer(...)` helps when simulating callbacks or controlled side effects, though never turn a mock into a miniature application when a simple DTO or real object works.

### Verifying Exception Branches After `doThrow`

`save` is invoked once before the repository throws. After `assertThrows`, `verify(repository).save(...)` still passes because Mockito recorded the call. Do not assume "throwing an exception means Mockito ignores the invocation count."

## 16. `@Spy`: Stubbing Bugs That Execute Real Methods During Setup

`src/main/java/com/example/mockdiagnostics/StatefulFormatter.java`:

```java
package com.example.mockdiagnostics;

import java.util.Locale;

public class StatefulFormatter {

    private int calls;

    public String normalize(String raw) {
        calls++;

        if (raw == null) {
            throw new IllegalArgumentException("raw is null");
        }

        return raw.trim().toUpperCase(Locale.ROOT);
    }

    public int calls() {
        return calls;
    }
}
```

`spy(new StatefulFormatter())` creates a **partial mock**: unstubbed methods execute the real implementation. Writing `when(spy.normalize(" hi ")).thenReturn("FIXED")` forces Java to evaluate `spy.normalize(...)` before passing its result into `when(...)`; the real method executes **once during stubbing**. If it writes to a DB or sends HTTP requests, test setup just triggered real side effects.

### Using `doReturn` to Skip Execution During Setup

`src/test/java/com/example/mockdiagnostics/SpyDiagnosticsTest.java`:

```java
package com.example.mockdiagnostics;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class SpyDiagnosticsTest {

    @Test
    void doReturnSkipsRealMethodDuringSetup() {
        StatefulFormatter formatter =
                spy(new StatefulFormatter());

        doReturn("FIXED")
                .when(formatter)
                .normalize(" hi ");

        assertEquals(0, formatter.calls());

        assertEquals("FIXED",
                formatter.normalize(" hi "));

        // normalize was stubbed, so real logic did not run.
        assertEquals(0, formatter.calls());
        verify(formatter).normalize(" hi ");
    }

    @Test
    void whenOnSpyCallsRealMethodDuringStubbing() {
        StatefulFormatter formatter =
                spy(new StatefulFormatter());

        when(formatter.normalize(" hi "))
                .thenReturn("FIXED");

        // During when(...) evaluation, the real method executed once.
        assertEquals(1, formatter.calls());

        // Calling the stubbed method returns the stubbed value.
        assertEquals("FIXED",
                formatter.normalize(" hi "));
        assertEquals(1, formatter.calls());
    }
}
```

**There are 2 `@Test` methods** in this class. They use `spy` directly without `MockitoExtension` because there are no `@Mock` fields or session strictness requirements.

### A Spy Is Not Identical to the Original Object

Mockito spies generally copy state from the instance passed to `spy(realObject)`, rather than always delegating every call back to that original reference. If you keep references to both `realObject` and `spyObject`, checking state on the original does not reflect spy calls. The test calls `formatter.calls()` strictly on the **spy**, avoiding this trap.

### `@SpyBean` and Spring AOP Proxies

In Spring Boot 3.3, `@SpyBean` wraps a real Spring bean; it can still trigger real side effects if stubbed via `when(spy.method())`. For beans wrapped by Spring AOP proxies—`@Transactional`, `@Cacheable`, or security advice—know whether you are spying the proxy or target; when needed, consult Spring's `AopTestUtils` documentation. Never call `spy(new SomeService())` and assume Spring interceptors were tested.

## 17. `verify()` Defaults to Exactly One Invocation

These assertions express different contracts:

```java
verify(inventory).find("SKU-1");             // Exactly 1 time.
verify(inventory, times(1)).find("SKU-1");   // Equivalent.
verify(inventory, times(2)).find("SKU-1");   // Exactly 2 times.
verify(inventory, never()).find("SKU-1");    // Exactly 0 times.
verify(inventory, atLeastOnce()).find("SKU-1");// >= 1 time.
```

These **snippets** reference the project's `inventory` mock and static imports `times`, `never`, `atLeastOnce`. They cannot all pass against a single invocation history; each verification mode enforces a distinct contract.

### Misunderstood Call Counts

- A retry decorator may invoke a repository/client multiple times.
- A loop may call an adapter once per item; verify counts matching item count.
- A callback might be registered twice.
- `@BeforeEach` or fixture setup might have called the mock unexpectedly.
- A Mockito mock retained history across tests without resetting, especially with static mocks or misconfigured Spring context resets.
- A method ran during spy stubbing with `when(...)`.
- `verifyNoMoreInteractions` flags unverified helper calls, coupling tests to incidental implementation details.

**Never change `times(1)` to `atLeastOnce()` simply because the test observed 2 calls.** Determine whether the second call is legitimate or a bug; if code ought to call once, keep the assertion and fix the code.

## 18. `ArgumentCaptor`: Inspecting the Exact Object Sent

In `captorInspectsSavedReservation`:

```java
ArgumentCaptor<Reservation> captor =
        ArgumentCaptor.forClass(Reservation.class);

verify(repository).save(captor.capture());

Reservation saved = captor.getValue();
assertEquals("SKU-5", saved.sku());
assertEquals(4, saved.units());
```

`ArgumentCaptor` inspects arguments **after the invocation occurred**. It does not replace invoking the service. Without `repository.save`, `verify(...).save(captor.capture())` fails with no invocation.

### When to Use Captor vs `equals`?

- DTO/record with clean `equals` -> `verify(repo).save(new Reservation(...))` is concise.
- Need to inspect specific fields or a transformation -> captor reads clearly.
- Objects lacking stable `equals` -> captor or `argThat` fits well.
- Multiple invocations -> `captor.getAllValues()` to assert the full list per contract.
- Avoid using captor as a lazy "any matcher" during stubbing when you only need a canned response; `eq`/`any` is clearer.

### Captor Does Not Prove a DB Commit Happened

`verify(repo).save(...)` only proves the service **called the dependency**. If the repository mock is a no-op, nothing was written to a database. To protect JDBC/JPA transactions, write integration tests against a real database and query state past the transaction/commit boundary.

## 19. `InOrder` and `verifyNoMoreInteractions`

`InOrder` checks **invocation ordering** across mocks:

```java
InOrder order = inOrder(inventory, repository);
order.verify(inventory).find("SKU-7");
order.verify(repository).save(
        new Reservation("SKU-7", 1));
order.verifyNoMoreInteractions();
```

This helps when business rules mandate **checking stock before persisting**. Yet if logic makes benign calls such as metrics or tracing getters, avoid over-constraining the full call history unnecessarily.

### Avoid `verifyNoMoreInteractions` on Every Test

`verifyNoMoreInteractions(inventory, repository)` forbids any additional unverified interactions. That is a strict contract; adding a harmless auxiliary lookup breaks the test. Reserve it for boundaries where **absence of extra calls truly matters** (payment charges, idempotent writes, retry budgets), rather than making it a ritual on every getter.

`verifyNoInteractions(repository)` is different: it asserts `repository` received **zero calls across all methods**. `verify(repository, never()).save(...)` asserts only that **that specific method** with that matcher was not called; other methods on `repository` might still run without failing it. Pick strictness intentionally.

## 20. Mock Instance Mismatch: Which Object Does the Service Hold?

A very common bug:

```java
InventoryClient mockA = mock(InventoryClient.class);
InventoryClient mockB = mock(InventoryClient.class);

ReservationService service =
        new ReservationService(mockB, repository);

service.reserve("SKU-1", 1);

verify(mockA).find("SKU-1"); // Wrong instance.
```

This is an **intentionally broken snippet**, requiring `mockB` to be stubbed with valid stock to even reach `verify`. The core point: `verify(mockA)` cannot observe calls made on `mockB`. Debugging this by changing to `verify(mockA, times(0))` merely hides that the service is not using the mock you thought it was.

### Diagnostic Clues

- Multiple `new ReservationService(...)` calls across fixture setup.
- `@Mock` fields paired with `@InjectMocks` or manual constructors creating a separate service instance.
- Spring test declaring `@Mock` while `@Autowired` service retains the real Spring bean collaborator.
- Multiple `@Qualifier` beans where the test mocked the wrong bean name.
- Verifying a manually created `spy(...)` while Spring invokes a separate target bean.
- An async callback capturing an old object while the test verifies a fresh mock.
- `Mockito.reset(mock)` called between the business invocation and `verify`, wiping invocation history.

### Diagnosing Identity

`Mockito.mockingDetails(object).isMock()` and `isSpy()` reveal whether Mockito considers an object a mock or spy. `mockingDetails(mock).getInvocations()` prints recorded interactions during troubleshooting, though never build business assertions on internal string formatting. With Spring proxies, proxy and target identities can differ, so verify bean wiring rather than assuming every proxy is directly a Mockito mock.

## 21. `@Mock`, `@InjectMocks`, and `@MockBean` Are Different

| Annotation | Role | Context |
| --- | --- | --- |
| `@Mock` | Creates mock for field/parameter | `MockitoExtension`/unit test |
| `@InjectMocks` | Tells Mockito to inject mocks via constructor/setter/fields best-effort | Object under test; does not register a Spring bean |
| `@Spy` | Partial mock around a real object | Mockito-managed |
| `@MockBean` (Boot 3.3) | Registers/replaces bean in Spring `ApplicationContext` | Spring Boot Test |
| `@SpyBean` (Boot 3.3) | Wraps an existing Spring bean with a spy | Spring Boot Test |

**`@InjectMocks` is not a dependency injection container.** If overloaded constructors, matching field types/names, or missing dependencies confuse injection, Mockito does not fail as clearly as a Spring context. For a service with two dependencies, explicit `new ReservationService(inventory, repository)` makes wiring obvious and easy to debug.

**`@MockBean` is not equivalent to `@Mock`.** It registers or replaces a Spring bean by type or name so `@Autowired ReservationService` receives the mock from the context. Boot 3.3 resets `@MockBean` **after each test method** by default. Still, resetting mocks does not reset databases, caches, topics, or other mutable singletons; do not confuse it with `@DirtiesContext`.

## 22. Spring Boot Integration Test Using `@MockBean` Properly

`src/test/java/com/example/mockdiagnostics/ReservationServiceSpringTest.java`:

```java
package com.example.mockdiagnostics;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ReservationServiceSpringTest {

    @Autowired
    ReservationService service;

    @MockBean
    InventoryClient inventory;

    @MockBean
    ReservationRepository repository;

    @Test
    void mockBeansAreInjectedIntoSpringManagedService() {
        when(inventory.find("SPR-1"))
                .thenReturn(Optional.of(new Stock("SPR-1", 4)));

        Reservation result = service.reserve("SPR-1", 2);

        assertEquals(new Reservation("SPR-1", 2), result);
        verify(inventory).find("SPR-1");
        verify(repository).save(new Reservation("SPR-1", 2));
    }

    @Test
    void invalidInputDoesNotUseSpringMockBeans() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.reserve(" ", 1));

        verifyNoInteractions(inventory, repository);
    }
}
```

**There are 2 `@Test` methods.** Here Spring Boot constructs the real `ReservationService` and injects both `@MockBean`s, replacing the two demo adapters from `MockitoDiagnosticsApplication`. Do not add `@ExtendWith(MockitoExtension.class)` to this Spring test: Spring Boot Test already manages mock lifecycle via TestContext support.

### Why Don't Spring Tests Enforce Strict Stubbing Identically to Unit Tests?

`@MockBean` is managed and reset by Boot's TestContext support; strictness details do not necessarily mirror a standalone `MockitoExtension` session. Therefore, do not rely on unused stubs throwing identically across both styles. Regardless of framework enforcement, keep stubbing minimal per test.

### Multiple Spring Beans Implementing the Same Interface

If two `InventoryClient` beans exist (primary and fallback), `@MockBean InventoryClient` by type alone may be ambiguous or target the wrong one. Specify `name` or `@Qualifier` and verify the injected collaborator is the mock under test. Never add an ambiguous typed mock assuming it replaces every instance.

### When Mock Behavior Is Needed During Context Refresh

Per Spring Boot docs, `@MockBean` stubbing inside a test method runs **after** the Spring context refreshes. If a bean invokes a dependency during `@PostConstruct`, `SmartInitializingSingleton`, or application startup, stubbing inside `@Test` comes **too late**. Use a `@TestConfiguration` `@Bean` pre-configured with stubs before refresh, or refactor side effects out of startup. That is a **lifecycle timing error**, not just a threading issue.

## 23. `@MockBean` vs `@MockitoBean` Across Spring Versions

**In this Spring Boot 3.3.5 project:**

```java
import org.springframework.boot.test.mock.mockito.MockBean;
```

Spring Framework 6.2 introduced `org.springframework.test.context.bean.override.mockito.MockitoBean` and `MockitoSpyBean`, and Spring Boot 3.4+ began deprecating Boot's legacy `@MockBean`/`@SpyBean`. Never copy `@MockitoBean` imports into a Boot 3.3 / Framework 6.1 project and blame Mockito when compilation fails.

When upgrading frameworks, read release notes and re-verify:
- Bean override matching by name/type.
- Qualifier behavior.
- Context cache keys.
- Reset/lifecycle semantics.
- Injection/proxy identity.
- Initialization-time stubbing.
- Test slices using the updated annotations.

Never mix instructions from two versions inside the same runnable project.

## 24. Async Verification: Timing Is Part of the Contract

In a synchronous method like `ReservationService.reserve`, dependency calls finish before the call returns. In `@Async` methods, Reactor callbacks, `CompletableFuture`, schedulers, or message listeners, calling `publishLater` may **merely schedule the work**.

A broken test:

```java
publisher.publishLater("EV-1"); 
verify(sink).publish("EV-1"); // May execute before the worker runs.
```

This snippet is outside the project's test code; the flaw is verifying immediately after enqueuing. If the worker has not run yet, Mockito throws `Wanted but not invoked`. Adding `Thread.sleep(1000)` only hides the race locally without making CI reliable.

### Proper Fix: Wait for the Future Before Verifying

`CompletableFuture.runAsync(...)` returns a future representing the task. When the test calls `future.get(5, SECONDS)` and succeeds, the subsequent `verify` sits behind a meaningful **happens-before / completion boundary** without relying on sleep.

For listeners or workers that return no future, use a `CountDownLatch`, a `CompletableFuture` probe, Awaitility, or bounded polling on observable output state. Never verify before the async dependency reaches the completion point under test.

## 25. `EventSink` and `DeferredPublisher`: Complete Async Code

`src/main/java/com/example/mockdiagnostics/EventSink.java`:

```java
package com.example.mockdiagnostics;

public interface EventSink {
    void publish(String eventId);
}
```

`src/main/java/com/example/mockdiagnostics/DeferredPublisher.java`:

```java
package com.example.mockdiagnostics;

import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

public final class DeferredPublisher {

    private final Executor executor;
    private final EventSink sink;

    public DeferredPublisher(Executor executor, EventSink sink) {
        this.executor = Objects.requireNonNull(executor);
        this.sink = Objects.requireNonNull(sink);
    }

    public CompletableFuture<Void> publishLater(String eventId) {
        Objects.requireNonNull(eventId);

        return CompletableFuture.runAsync(
                () -> sink.publish(eventId),
                executor);
    }
}
```

Injecting the `Executor` gives tests full control over threads and lifecycle without needing `@SpringBootTest` for this unit. In production, the adapter can use a Spring-managed executor; in unit tests, `Executors.newSingleThreadExecutor()` is created and shut down per test.

If you switch to Reactor `Mono` or `@Async`, verify publisher/scheduler/subscription semantics; never call `future.get` on an unsubscribed reactive `Publisher`.

## 26. `AsyncVerificationTest`: Futures, Controlled Gates, and Worker Failures

`src/test/java/com/example/mockdiagnostics/AsyncVerificationTest.java`:

```java
package com.example.mockdiagnostics;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@ExtendWith(MockitoExtension.class)
class AsyncVerificationTest {

    @Mock
    EventSink sink;

    @Test
    void waitsForCompletionBeforeVerifyingInteraction()
            throws Exception {

        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            DeferredPublisher publisher =
                    new DeferredPublisher(pool, sink);

            CompletableFuture<Void> done =
                    publisher.publishLater("EV-1");

            done.get(5, TimeUnit.SECONDS);

            verify(sink).publish("EV-1");
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void controlledGateMakesNeverVerificationMeaningful()
            throws Exception {

        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Executor gatedExecutor = command ->
                pool.execute(() -> {
                    started.countDown();
                    try {
                        if (!release.await(
                                5, TimeUnit.SECONDS)) {
                            throw new IllegalStateException(
                                    "gate timed out");
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(e);
                    }
                    command.run();
                });

        try {
            DeferredPublisher publisher =
                    new DeferredPublisher(gatedExecutor, sink);

            CompletableFuture<Void> done =
                    publisher.publishLater("EV-2");

            assertTrue(started.await(5, TimeUnit.SECONDS));

            // Worker has started yet is blocked by the gate.
            // Assert "not called yet" at this controlled point.
            verifyNoInteractions(sink);

            release.countDown();
            done.get(5, TimeUnit.SECONDS);

            // Assert "called" only after worker completion.
            verify(sink).publish("EV-2");
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }

    @Test
    void asyncFailureSurfacesViaFuture()
            throws Exception {

        doThrow(new IllegalStateException("sink unavailable"))
                .when(sink).publish("EV-3");

        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            DeferredPublisher publisher =
                    new DeferredPublisher(pool, sink);

            CompletableFuture<Void> done =
                    publisher.publishLater("EV-3");

            ExecutionException error = assertThrows(
                    ExecutionException.class,
                    () -> done.get(5, TimeUnit.SECONDS));

            IllegalStateException cause = assertInstanceOf(
                    IllegalStateException.class,
                    error.getCause());

            assertEquals("sink unavailable", cause.getMessage());
            verify(sink).publish("EV-3");
        } finally {
            pool.shutdownNow();
        }
    }
}
```

**There are 3 `@Test` methods** in the async class. No `Thread.sleep` is used; each test creates and shuts down its own executor. Worker failures surface through `ExecutionException.getCause()` from `CompletableFuture.get`, not by calling `assertThrows` directly on `publishLater`.

### Key Lesson in the Gated Test

`verifyNoInteractions(sink)` runs **while the worker is paused** at a latch after the test confirmed `started`. That makes the negative assertion meaningful at a deterministic state. After releasing the gate, `done.get(...)` confirms completion before `verify(sink).publish("EV-2")` runs.

Calling `verify(sink, never()).publish(...)` **before completion without a gate** might pass at instant T just before the worker calls the mock. A verification call cannot prove "this will never happen in the future" while an asynchronous task is still running.

### Is `awaitTermination` Needed?

In all three tests, `done.get` or the failing future finishes before `finally` on the normal path, so `shutdownNow` cleans up the executor. If a test times out, `shutdownNow` attempts interruption and the test fails; in production-grade concurrency fixtures running blocking tasks, add a bounded `awaitTermination` so workers never leak into subsequent tests. Never use `Thread.stop` or unbounded waits.

## 27. `Mockito.timeout` and `Mockito.after`: Helpful Yet Easy to Misread

Mockito offers timed verification modes:

```java
verify(sink, timeout(1000)).publish("EV-1");
verify(sink, timeout(1000).times(2)).publish("EV-1");
verify(sink, after(500).never()).publish("EV-2");
```

These are **illustrative snippets**, not meant to pass together against the demo's invocation history. Requires static imports `Mockito.timeout` and `Mockito.after`.

- `timeout(1000)` polls for up to ~1000 ms and **returns early as soon as the condition passes**, without waiting for the entire background job to finish.
- `timeout(...).times(2)` succeeds once two calls appear, yet does not prove a third call will not happen **after `verify` returns**.
- `after(...)` sleeps for the observation window before verifying, useful for checking no interaction occurs within a bounded window, though it never proves permanent absence.
- Mockito docs advise using timed verification **sparingly**; when business methods expose futures, latches, or completion state, those provide stronger boundaries.
- `timeout` does not replace `StepVerifier` for reactive streams, `MockMvc` for HTTP requests, Kafka acknowledgments, or DB transaction commits.
- Mockito docs note restrictions when combining timed verification with `InOrder`; do not build async ordering tests on unsupported API combinations.

**Preference:** await the real completion signal -> assert business state -> verify contract-critical interactions. Reserve `timeout` for cases where no completion signal can be exposed and a bounded eventual check suffices.

## 28. Testing `@Async`, HTTP, Kafka, and Callbacks: What to Await?

| System | Reliable Readiness/Completion Signal | Do Not Assume |
| --- | --- | --- |
| `CompletableFuture` | `future.get(timeout)`/`join` with outer timeout policy | Scheduling succeeded = processing finished |
| Spring `@Async` void | Latch/test probe or business outcome | Caller returned = listener done |
| Reactor `Mono`/`Flux` | `StepVerifier`/subscription outcome | Returning `Publisher` = subscribed |
| MockMvc synchronous request | `mvc.perform(...).andExpect(...)` | Unsuitable for un-dispatched async controllers |
| Spring MVC async controller | `asyncStarted` + `asyncDispatch` when applicable | Initial perform already holds final response |
| Kafka listener | Partition assignment, message result, bounded wait | Producer send ack = consumer processed |
| RabbitMQ | Queue/listener readiness, bounded consumer result | Publish confirm = consumer ACK |
| DB transaction | Query past transaction/commit boundary | Mock `repository.save` = row persisted |
| Scheduled job | Job completion/status/event probe | `Scheduler.start` = job finished |

Never attempt to fix verification timing by calling `Mockito.reset` mid-test. Resetting wipes both stubbing and invocation history, making timing races even harder to see.

## 29. `Mockito.verifyNoMoreInteractions` and Strict Stubs Are Different

Two related yet distinct concepts:

- **Strict stubbing** audits declared stubs to detect unused stubs and argument mismatches.
- **`verify` / `verifyNoMoreInteractions`** audits **invocation history** to enforce call contracts.

A test can have **zero unused stubs** and still throw `Wanted but not invoked` if it verifies the wrong method. Conversely, a test might verify one method accurately while leaving another unused stub behind. `STRICT_STUBS` interacts with `verifyNoMoreInteractions` by treating stubbed invocations as verified in certain modes, yet never rely on that nuance to turn unit tests into brittle snapshots of every call.

**Rule:** keep stubbing minimal, assert outcomes first, and verify important boundary interactions afterward. Avoid over-mocking and asserting incidental implementation details.

## 30. `Mockito.mockingDetails`: Inspecting What Object the Test Actually Holds

While debugging, you can inspect:

```java
System.out.println(
    Mockito.mockingDetails(inventory).isMock());

System.out.println(
    Mockito.mockingDetails(inventory).getInvocations());
```

This is a **diagnostic snippet**, requiring `org.mockito.Mockito` and an initialized `inventory` mock. Output is not fixed: invocations depend on runtime history. Never commit `System.out` prints permanently; they can leak sensitive arguments into CI logs. On build servers, use redacted loggers/test reports and remove temporary probes after fixing.

With Spring proxies, a bean may be an AOP proxy wrapping a target, so `isMock()` on the proxy may not directly reflect the underlying Mockito target. Verify Spring Test bean override wiring and real collaborator behavior via integration assertions instead of relying on a single print statement.

## 31. `WrongTypeOfReturnValue` and Stubbing Spies

`WrongTypeOfReturnValue` arises when a stub specifies a return value incompatible with the method signature or when a spy, overload, or concurrent access confuses Mockito during setup. Steps:

1. Check the method signature and interface generic types.
2. Check overloads and imports for `when`/`given`.
3. If the object is a spy, use `doReturn(...).when(spy).method(...)` so the real method does not run during stubbing.
4. Never stub the same mock concurrently across threads without lifecycle synchronization.
5. Never use raw types or unsafe casts to force an invalid result and turn a test false-green.
6. Keep Mockito aligned with JDK 17 and the Spring Boot BOM.

### Stubbing `final` or `static` Methods

Mockito 5 supports mocking many `final` and `static` methods depending on the mock maker/instrumentation, with constraints. For static mocks, wrap `MockedStatic` in `try-with-resources` to close its scope and prevent leaking behavior across tests. Even better, needing numerous static mocks usually signals hard-to-test code; inject `Clock`, HTTP clients, or repositories instead of mocking global static state.

## 32. Using `@BeforeEach`, Reset, and Spring TestContext Properly

Many suites end up with setups like:

```java
@BeforeEach
void setup() {
    Mockito.reset(inventory);
    when(inventory.find("SKU-DEFAULT")).thenReturn(...);
}
```

This is **intentionally risky pseudocode**. With `MockitoExtension`, each test already receives fresh mocks and its own strictness session. Manual `reset` is usually unnecessary, and a default stub goes unused in early-return branches. With `@MockBean`, Spring Boot 3.3 resets mocks automatically after every test method by default; calling `Mockito.reset` mid-execution can wipe recorded calls before `verify`.

Structure fixtures cleanly:
- Common setup **constructs the subject** and immutable test data.
- Each test **stubs only its branch**.
- Each test verifies after work completes.
- If a shared mock spans async/test methods, ensure workers finish and join before reset.
- When Spring's context cache reuses a context, remember mock resets do not reset mutable beans, DB rows, or caches.
- With Testcontainers/brokers, use dedicated namespaces or real cleanup; resetting mocks deletes neither rows nor messages.

## 33. Diagnosing Mockito Exceptions from Reports

| Exception / Message | Signal | How to Investigate |
| --- | --- | --- |
| `UnnecessaryStubbingException` | Declared stub never invoked | Trace branch, trim setup |
| `PotentialStubbingProblem` | Actual args differ from stub | Compare actual call vs stub |
| `WantedButNotInvoked` | No matching invocation recorded | Check mock instance, branch, timing |
| `TooManyActualInvocations` | Call count exceeded expectation | Check retries, loops, duplicate listeners |
| `NeverWantedButInvoked` | Forbidden method got called | Check early-return/guards |
| `ArgumentsAreDifferent` | Same method, mismatched arguments | Check captor, `equals`, matcher, normalization |
| `InvalidUseOfMatchersException` | Matcher syntax misuse | Use matchers for all args in that call |
| `NotAMockException` | Argument to `verify/reset` is not a mock | Check `@Mock`/`@MockBean`/spy identity |
| `WrongTypeOfReturnValue` | Incompatible stub return or spy real call | Check overload/return type and `doReturn` |
| `UnfinishedStubbingException` | `when(...)` missing `thenReturn`/completion | Finish stubbing, avoid nested stubs |
| `UnfinishedVerificationException` | `verify(mock)` missing method call | Chain the method call onto `verify(mock)` |
| `NullInsteadOfMockException` | Mock field is null | `MockitoExtension` missing or field uninitialized |
| `NotAMockException` on Spring bean | Proxy/target mismatch or wrong instance | Check Boot `@MockBean` wiring |

Exception names above summarize common categories; **exact wording** varies by Mockito version, Java proxies, and code structure. Never assert exact framework message text in business tests unless intentionally testing framework behavior.

## 34. 12-Step Debugging Workflow

1. Read the failing test class/method and **first meaningful cause** in the Gradle/JUnit report.
2. Determine whether failure happened **during stubbing**, **while code under test ran**, **at `verify`**, or **in `MockitoExtension` teardown**.
3. Inspect actual recorded invocations safely without exposing sensitive data.
4. Confirm the SUT holds the exact mock instance you are verifying.
5. In Spring tests, distinguish context `@MockBean` from test-field `@Mock`.
6. Check argument types/values, whitespace, `equals/hashCode`, matchers, and null behavior.
7. Confirm the test branch actually reaches the dependency call.
8. If strict stubbing flags unused stubs, remove superfluous stubs before considering `lenient`.
9. If counts mismatch, hunt down retries, loops, or duplicate listeners rather than loosening `verify`.
10. If a spy triggers real logic during setup, switch to `doReturn`/`doThrow`.
11. For async code, await a completion signal, future, or transaction outcome before `verify`; never use `Thread.sleep`.
12. Run the test alone and then the full suite; check JUnit reports, Spring context cache/shared state, and CI scheduling.

### Separating Compilation Errors from Mockito Runtime Failures

If `when(repository.save(...))` fails to compile because the method returns `void`, Gradle fails at `compileTestJava` and **JUnit never runs**. Do not look for `UnnecessaryStubbingException` in an ungenerated XML report. Likewise, importing `@MockitoBean` on Boot 3.3 is a version/API compile mismatch, not a mock interaction failure.

## 35. Anti-Patterns to Avoid

| Anti-Pattern | Why It Is Dangerous | Solution |
| --- | --- | --- |
| Stubbing every dependency in `@BeforeEach` | Triggers unused stubs and noisy setup | Stub per test |
| Enabling class-wide `lenient` for green tests | Masks argument mismatches and dead stubs | Use selective leniency sparingly |
| Calling `verify` without calling SUT | Zero invocations | Act before Assert/Verify |
| Mocking the service instead of its dependencies | Skips testing the real service logic | Keep real service, mock boundaries |
| Using `@Mock` in Spring test with `@Autowired` SUT | Does not replace the Spring bean | `@MockBean` / proper test config |
| Verifying a different mock instance | Invocation history sits elsewhere | Constructor injection, verify wiring |
| Verifying before async completion | Creates flaky race conditions | Await future/latch/business state |
| Using `Thread.sleep` to wait | Non-deterministic, slows CI | Bounded completion signal |
| `when(spy.realCall())` on side-effecting methods | Runs real logic during setup | `doReturn`/`doThrow` |
| Using `any()` for every parameter | Erodes contract checks | `eq`/captor on important values |
| Mixing matchers with raw arguments | Invalid Mockito syntax | Wrap remaining args with `eq(raw)` |
| `verifyNoMoreInteractions` everywhere | Over-specifies internal calls | Verify only critical boundary calls |
| Loosening `times` when failing | Can hide duplicate charges/retries | Investigate the extra invocation |
| `reset(mock)` before `verify` | Erases invocation history | Drop unnecessary resets |
| Treating default mock answers as business success | Unstubbed mocks return empty/defaults | Stub explicitly and assert outcomes |
| Asserting call counts only, skipping return values | Passes despite broken business math | Assert return/error + interaction |
| Stubbing Spring `@MockBean` after context refresh | Cannot alter startup side effects | Pre-configure `@TestConfiguration` `@Bean` or refactor |
| Inferring DB writes from `verify(repo.save)` | Mock is a no-op; no DB transaction ran | Real DB integration tests |

## 36. Test Boundaries and Observability When Troubleshooting

In Spring Boot, a Mockito failure is often a secondary symptom; pinpoint the **real** boundary:

- **Unit service**: assert business outcome and verify adapter call.
- **Spring context**: bean replacement/qualifiers/proxies; read startup logs if wiring fails.
- **HTTP layer**: `MockMvc`/`WebTestClient` verify request/response, not just controller mocks.
- **Persistence**: DB integration and transactions, never inferred from a mocked repository.
- **Messaging**: producer send call differs from consumer ACK/processing; test readiness/outcome.
- **Asynchronous**: future/latch completion, error propagation, and thread ownership.
- **Retry**: verify both attempt count and final state.
- **Metrics**: Mockito verification does not prove Micrometer counters or traces were recorded; test registry/observation handlers explicitly when required.

During CI debugging, JUnit XML/HTML reports and full stack traces distinguish failures inside the test method from failures in `MockitoExtension` teardown. With `UnnecessaryStubbingException`, assertions inside the test body may pass while the extension fails afterward; that is still a failed test whose setup needs fixing.

## 37. Running the Project and Reading Reports

If the Gradle Wrapper is present:

```bash
./gradlew clean test
./gradlew test --tests 'com.example.mockdiagnostics.ReservationServiceTest'
./gradlew test --tests 'com.example.mockdiagnostics.SpyDiagnosticsTest'
./gradlew test --tests 'com.example.mockdiagnostics.AsyncVerificationTest'
./gradlew test --tests 'com.example.mockdiagnostics.ReservationServiceSpringTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test
.\gradlew.bat test --tests "com.example.mockdiagnostics.ReservationServiceTest"
```

On machines with a compatible Gradle installed and no wrapper:

```bash
gradle clean test
```

Default Gradle `Test` reports:

```text
build/reports/tests/test/index.html
build/test-results/test/TEST-*.xml
```

**Total methods in source: 15 `@Test` methods**, comprising 8 `ReservationService` unit tests, 2 spy tests, 3 async tests, and 2 Spring Boot integration tests. This is a **source code count**, not a claim of 15 tests PASSED. **Gradle/JUnit was not executed while authoring this lesson**; confirm results only after generating and reading build reports.

### When Tests Do Not Compile

Check Java 17, Spring Boot 3.3.5 Gradle plugin/dependencies, package/class filenames, static imports, and `useJUnitPlatform()`. Failure to download dependencies or locate the toolchain is a build-environment failure, not a stubbing mismatch.

### When a Run Succeeds Yet HTML Reports Lack Expected Cases

A `--tests` filter may have excluded them, JUnit failed discovery, or Gradle reported `UP-TO-DATE`. Run `clean test` or `--rerun-tasks` for a verified fresh run. Never equate "0 failures" with "everything tested" when 0 methods executed.

## 38. Hands-On Exercises

1. Run the unit tests; observe `@ExtendWith(MockitoExtension.class)` creating mocks automatically.
2. Intentionally move a happy-path stub into `@BeforeEach` and run the invalid-input test; read `UnnecessaryStubbingException`.
3. Stub `inventory.find("SKU-X")` while calling `reserve("SKU-Y", ...)`; analyze `PotentialStubbingProblem`.
4. Omit calling `service.reserve` before `verify`; read `Wanted but not invoked`.
5. In `repeatedCallsRequireExplicitCount`, change `times(2)` back to default; read the invocation history.
6. Add an accidental duplicate `save` inside the service; observe `verifyNoMoreInteractions` and count assertions catching it.
7. Convert `Reservation` from a record to a class without `equals`; use `ArgumentCaptor` to inspect fields rather than object identity.
8. Test `anyString()` paired with `eq("SKU-1")`, keeping the argument contract tight.
9. Mix `anyString()` and a raw argument in a two-parameter method; observe matcher misuse failure.
10. Test `doThrow` on void `repository.save` and assert exception propagation.
11. Exercise spy `StatefulFormatter` with both `when` and `doReturn`; compare `calls()` right after setup.
12. Add a simulated network side effect to a spy method and see why `when(...)` stubbing is dangerous.
13. Remove `@MockBean` from the Spring test while still injecting the Spring service; observe the default adapter output and verification error.
14. Register two beans implementing `InventoryClient` in a sandbox and test `@MockBean` by name/qualifier.
15. Try stubbing `@MockBean` inside a test method when a dependency is called during context refresh; observe the lifecycle limitation.
16. In `AsyncVerificationTest`, remove `done.get` and verify immediately; observe the race risk without "fixing" it with sleep.
17. Use a `CountDownLatch` gate to assert zero interactions before release, then verify once after completion.
18. Experiment with `verify(sink, timeout(1000))`; explain why it cannot guarantee a second call will not arrive later.
19. Open the JUnit HTML/XML report after a teardown failure in `MockitoExtension` and pinpoint the stack frame location.
20. Add a real HTTP/DB integration test and verify why `verify(mock)` alone does not prove persisted state.
21. Migrate the project to a newer Spring Boot/Framework version in a sandbox and verify the `@MockBean`/`@MockitoBean` API change.
22. Run the full suite across varied JUnit/Gradle configurations and investigate any flakiness.

## 39. Pre-Merge QA Checklist

- [ ] Identified the real SUT and mocked at the right collaborator boundary?
- [ ] Mocks created via `MockitoExtension` or Spring TestContext with proper lifecycle?
- [ ] Constructor or Spring bean actually receives the exact mock instance?
- [ ] Every stub is exercised by that test's scenario?
- [ ] No leftover unused stubs in `@BeforeEach`?
- [ ] Strictness is not disabled suite-wide to mask mismatches?
- [ ] Stubbed arguments match real calls with accurate matcher types and null handling?
- [ ] Raw arguments and matchers are never mixed improperly?
- [ ] `void` methods stubbed with `doThrow`/`doNothing` when needed?
- [ ] Spies stubbed safely to prevent real side effects during setup?
- [ ] Business outcome/error assertions run before `verify`?
- [ ] `verify` checks exact methods, args, and counts per business contract?
- [ ] When multiple calls occur, checked retries/loops/callbacks before altering `times`?
- [ ] `ArgumentCaptor` used when inspecting individual object fields?
- [ ] `InOrder` verifies ordering only when business rules require it?
- [ ] `verifyNoMoreInteractions` avoids over-specifying trivial helper calls?
- [ ] `verifyNoInteractions`/`never` runs only after completion or behind a controlled gate?
- [ ] Async work is awaited via future/latch/result with a finite timeout?
- [ ] No `Thread.sleep` or wall-clock guessing used to synchronize workers?
- [ ] `@MockBean` matches Spring Boot 3.3 API and exact bean type/name/qualifier?
- [ ] No stubs configured too late after Spring context refresh?
- [ ] Spring mock resets not confused with DB/cache cleanup?
- [ ] Compile/setup failures distinguished from Mockito runtime failures?
- [ ] Logs and mock diagnostics never leak tokens or PII?
- [ ] Gradle/CI executed and JUnit reports read before claiming a real PASS?

## 40. References

- [Mockito Core 5 — Mockito Javadoc](https://javadoc.io/doc/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/Mockito.html): stubbing, verification, spies, `doReturn`, `lenient`, `timeout`/`after`.
- [Mockito — MockitoExtension Javadoc](https://javadoc.io/doc/org.mockito/mockito-junit-jupiter/5.17.0/org.mockito.junit.jupiter/org/mockito/junit/jupiter/MockitoExtension.html): JUnit Jupiter lifecycle and strict stubbing.
- [Mockito — UnnecessaryStubbingException Javadoc](https://javadoc.io/doc/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/exceptions/misusing/UnnecessaryStubbingException.html): unused stubs and selective leniency.
- [Mockito — PotentialStubbingProblem Javadoc](https://javadoc.io/doc/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/exceptions/misusing/PotentialStubbingProblem.html): argument mismatches and strict stubbing.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@MockBean`, `@SpyBean`, Spring context/cache/reset.
- [Spring Boot 3.3 — MockBean Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): bean override and `MockReset.AFTER`.
- [Spring Framework 6.2 — MockitoBean and MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): migration context, not used in this Boot 3.3 project.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit `@Test`, extensions, parameterized/async test considerations.
- [Gradle — Testing in JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `useJUnitPlatform`, test filters, and HTML/XML reports.

## 41. Conclusion

**A Mockito failure can only be diagnosed accurately by separating three steps: what was stubbed, which mock the code under test actually called, and when verification ran.** When `MockitoExtension` reports `UnnecessaryStubbingException`, delete superfluous stubs first; on mismatches, compare actual arguments; on `WantedButNotInvoked`, verify the execution branch and mock instance before touching `verify`. For spies, `doReturn(...).when(spy)` avoids running real methods during setup. In Spring Boot 3.3, `@MockBean` replaces collaborators inside the `ApplicationContext`, whereas unit-test `@Mock` does not.

**For async code**, always wait on a bounded completion signal before verifying business interactions; `Mockito.timeout` is merely polling verification, not proof the worker finished. Never inflate `times`, enable `lenient` suite-wide, or insert `Thread.sleep` just to force tests green. Protect business contracts with clean unit tests, proper Spring wiring, and QA checks grounded in actual JUnit/Gradle reports **after real execution**, never inferred from README counts.
