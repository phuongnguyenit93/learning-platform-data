# Scoping Static Mocks and Avoiding State Leakage Across Tests with Mockito

`Mockito.mockStatic(...)` lets you replace the behavior of `static` methods during a controlled execution window. It is a practical tool when testing legacy code or a static call that is hard to extract from business logic immediately. However, if you open a static mock and **forget to close it**, the mock behavior stays active on the creating thread, causing subsequent tests to see wrong results, fail with errors like “static mocking is already registered in the current thread,” or become dependent on how the test runner reuses threads.

This lesson explains the `MockedStatic<T>` lifecycle, closing scopes reliably with `try-with-resources` or guaranteed teardown, verifying restored real behavior, Mockito's thread-local boundaries, and design options to reduce reliance on static mocking in Spring Boot.

## 1. The Problem to Solve: A Static Mock Is a Resource with a Lifecycle

Suppose business code calls:

```java
int fee = RegionFees.baseFee("HCM");
```

In reality, `RegionFees.baseFee("HCM")` returns `18_000`. A test wants to simulate a `4_000` fee to verify how the service uses the returned value. Mockito can create a controller:

```java
MockedStatic<RegionFees> staticFees = Mockito.mockStatic(RegionFees.class);
staticFees.when(() -> RegionFees.baseFee("HCM")).thenReturn(4_000);
```

While the static mock is **active**, calls to `RegionFees.baseFee("HCM")` on the thread that created the mock go through Mockito's stubbing mechanism. If `staticFees` is not closed, that override remains active on that thread even after the test method finishes.

`MockedStatic<RegionFees>` is not merely a variable holding sample data; it is a **handle managing a scoped mock**. Mockito recommends closing the handle as soon as that test section finishes. The safest and clearest approach is `try-with-resources`, because Java invokes `close()` upon exiting the block even if an exception is thrown.

Distinguish three things:

| Component | Role | What happens when it ends? |
| --- | --- | --- |
| Real `static` method | Existing logic in application code | Still exists in the class; never permanently rewritten |
| `MockedStatic<T>` | Controller for static mocking in the corresponding **scope/thread** | `close()` ends the active static mock |
| Real external state | Static mutable fields, caches, DB, files, Spring singletons… | **Not automatically reset** just by closing `MockedStatic` |

The last point is crucial: **closing a static mock restores calls to the real method; it does not undo side effects that happened earlier**.

## 2. Within What Scope Does a Static Mock Apply?

Per the `MockedStatic` contract in Mockito 5, a static mock only affects **the thread that created it**, and the `MockedStatic` object must not be used from other threads. Therefore:

- A `MockedStatic<T>` opened on the JUnit thread affects subsequent static calls **on that same thread** until closed.
- Work executed via `CompletableFuture`, `@Async`, a thread pool, or another request thread **does not automatically inherit** stubs from the JUnit thread.
- Never share the same `MockedStatic` handle to call `when`, `verify`, or `close` across multiple threads; it is not thread-safe for cross-thread usage.
- Test runners can reuse threads across multiple tests. Hence a leaked static mock can break other tests, though you **must not assume every test runs on the same thread** to explain every failure.

Its scope is **thread-local and active-duration based**, not automatically “just inside one test method.” A `try-with-resources` block sets an explicit boundary between mocked behavior and real behavior.

### Inside the Scope, What Happens to Unstubbed Static Calls?

When using `Mockito.mockStatic(RegionFees.class)` with standard default answers, **unstubbed** static methods can return Mockito defaults: `0` for `int`, `false` for `boolean`, `null` for many reference types. **Do not assume other calls will execute real logic.**

For instance, stubbing only `RegionFees.baseFee("HCM")` can cause `RegionFees.baseFee("HN")` on the mocked thread to return `0`, even though the real logic returns `22_000`. Design tests to account for side effects of replacing the whole class's static methods. If you want unstubbed calls to keep real behavior, consider `Mockito.mockStatic(RegionFees.class, Mockito.CALLS_REAL_METHODS)`, while carefully checking real-method side effects including during stubbing. Never default to `CALLS_REAL_METHODS` without understanding the target class.

## 3. Preferred Approach: Using `try-with-resources`

```java
assertEquals(18_000, RegionFees.baseFee("HCM")); // Real behavior.

try (MockedStatic<RegionFees> fees =
         Mockito.mockStatic(RegionFees.class)) {
    fees.when(() -> RegionFees.baseFee("HCM")).thenReturn(4_000);

    assertEquals(4_000, RegionFees.baseFee("HCM"));
    fees.verify(() -> RegionFees.baseFee("HCM"));
}

assertEquals(18_000, RegionFees.baseFee("HCM")); // Real behavior returns.
```

This is an illustrative excerpt; full imports and runnable code are in Section 5. Read it across three checkpoints: **before scope** (18,000) → **inside scope** (4,000) → **after scope** (18,000).

Why prefer `try-with-resources`:

1. `MockedStatic<T>` implements `AutoCloseable` via `ScopedMock`; Java calls `close()` automatically at the end of the block.
2. If an assertion fails or code inside the block throws an exception, exiting the block still closes the resource.
3. Anyone reading the test immediately sees the stub's exact scope right where it is created.
4. The test does not need to store handles in `static` fields or fixtures spanning multiple tests.
5. The test can assert real behavior right after the block to verify the boundary closed properly.

Keep the scope **as narrow as possible**: spanning an entire test class or `@BeforeAll` just to stub one call in one test causes unrelated tests to run with faked behavior unintentionally.

## 4. When Manual Teardown Is Needed: `@BeforeEach` Paired with `@AfterEach`

Sometimes multiple tests in one class need the same static mock setup. When you cannot wrap each test in `try-with-resources`, open the scope in `@BeforeEach` and close it in `@AfterEach`.

```java
private MockedStatic<RegionFees> fees;

@BeforeEach
void setUp() {
    fees = Mockito.mockStatic(RegionFees.class);
}

@AfterEach
void tearDown() {
    if (fees != null) {
        fees.closeOnDemand();
    }
}
```

This is an **excerpt**, not a complete test class; Section 5 has full imports. `@AfterEach` must **close the handle** rather than merely setting `fees = null`. Assigning `null` drops the test's reference without deregistering the active static mock controller in Mockito.

Differences between lifecycle methods:

| API | Meaning | When to use |
| --- | --- | --- |
| `close()` | Closes the scoped mock; throws an error if already closed | `try-with-resources` or teardown where each scope has a single clear owner |
| `closeOnDemand()` | Closes if still active; no-op if already closed | Teardown that must tolerate the scope having already been closed early |
| `isClosed()` | Reports whether the handle has been closed | Diagnostic assertions, not a replacement for `close()` |
| `reset()` on `MockedStatic` controller | Clears stubbing and interaction history of an **active mock** | Never used to end a scope |
| `clearInvocations()` | Clears recorded invocation history | Never used to end a scope |

In JUnit Jupiter, `@AfterEach` is designed to run after every test execution, even when a test or assertion fails. Even so, when the scope is needed only for one block, `try-with-resources` stays closer to usage and leaves fewer leak paths. If setup opens multiple resources, clean up each one explicitly and avoid overwriting an unclosed handle.

**Avoid `@BeforeAll` + `@AfterAll` for per-scenario static mocks:** the scope would span the whole test class. Tests not meant to use the stub can be affected. Under parallel execution, thread-local scoping also makes opening on one thread and using/closing on another broken by design.

## 5. Complete Example: Java 17+, Spring Boot, and Mockito

This small project uses Java 17, Spring Boot 3.3.5, and JUnit Jupiter. `spring-boot-starter-test` provides Mockito for tests. Mockito 5 uses the inline mock maker by default on standard JVMs, allowing static mocking of application-owned classes. On Java 21+, explicit instrumentation/Java agent configuration may be required depending on JDK and runtime; see the environment notes near the end.

Example business rules:

- Standard regional fees: HCM = 18,000, HN = 22,000, other regions = 30,000 (VND).
- Orders of **200,000 or more**: free delivery.
- Negative order amount: throws `IllegalArgumentException`.
- A test can temporarily static-mock the HCM fee to 4,000 to verify the service uses that value, then confirm the real fee returns.

### 5.1. File Layout and Gradle

```text
settings.gradle
build.gradle
src/main/java/com/example/staticmock/StaticMockApplication.java
src/main/java/com/example/staticmock/RegionFees.java
src/main/java/com/example/staticmock/DeliveryQuoteService.java
src/test/java/com/example/staticmock/DeliveryQuoteServiceTest.java
src/test/java/com/example/staticmock/DeliveryQuoteSpringBootTest.java
src/test/java/com/example/staticmock/ExtensionManagedStaticTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'static-mock-scope'
```

**`build.gradle`**

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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use a Gradle Wrapper compatible with Java 17. Spring Boot 3.3.5's test dependency manages compatible JUnit/Mockito versions for the example without manually mixing `mockito-core` and `mockito-inline`. Static mocking requires the inline mock maker; since Mockito 5, inline is the default on standard JVMs unless overridden by a custom `MockMaker` config.

**`src/main/java/com/example/staticmock/StaticMockApplication.java`**

```java
package com.example.staticmock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StaticMockApplication {
    public static void main(String[] args) {
        SpringApplication.run(StaticMockApplication.class, args);
    }
}
```

**`src/main/java/com/example/staticmock/RegionFees.java`**

```java
package com.example.staticmock;

public final class RegionFees {
    private RegionFees() {
    }

    public static int baseFee(String region) {
        return switch (region) {
            case "HCM" -> 18_000;
            case "HN" -> 22_000;
            default -> 30_000;
        };
    }
}
```

This is a utility class with a static method and **no mutable static state**. Switch expressions work in Java 17. The example assumes non-null `region`; handling `null` in switch is outside this lesson's contract.

**`src/main/java/com/example/staticmock/DeliveryQuoteService.java`**

```java
package com.example.staticmock;

import org.springframework.stereotype.Service;

@Service
public class DeliveryQuoteService {
    public int quote(String region, int orderAmount) {
        if (orderAmount < 0) {
            throw new IllegalArgumentException(
                    "orderAmount must be non-negative");
        }
        if (orderAmount >= 200_000) {
            return 0;
        }
        return RegionFees.baseFee(region);
    }
}
```

The service is stateless. The target of static mocking is **`RegionFees.baseFee`**, not `DeliveryQuoteService.quote`; tests still run the service's real logic and assert its output.

### 5.2. Preferred Test: Explicit Scope per Test Method

**`src/test/java/com/example/staticmock/DeliveryQuoteServiceTest.java`**

```java
package com.example.staticmock;

import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;
import org.mockito.Mockito;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.times;

class DeliveryQuoteServiceTest {
    private final DeliveryQuoteService service =
            new DeliveryQuoteService();

    @Test
    void temporaryStaticFeeIsRestoredAfterScope() {
        assertEquals(18_000, service.quote("HCM", 100_000));

        try (MockedStatic<RegionFees> fees =
                     Mockito.mockStatic(RegionFees.class)) {
            fees.when(() -> RegionFees.baseFee("HCM"))
                    .thenReturn(4_000);

            assertEquals(4_000, service.quote("HCM", 100_000));
            fees.verify(() -> RegionFees.baseFee("HCM"), times(1));
        }

        assertEquals(18_000, service.quote("HCM", 100_000));
    }

    @Test
    void scopeIsClosedEvenWhenBlockThrows() {
        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> {
                    try (MockedStatic<RegionFees> fees =
                                 Mockito.mockStatic(RegionFees.class)) {
                        fees.when(() -> RegionFees.baseFee("HN"))
                                .thenReturn(1_000);
                        assertEquals(1_000,
                                service.quote("HN", 100_000));
                        throw new IllegalStateException("simulated failure");
                    }
                });

        assertEquals("simulated failure", failure.getMessage());
        assertEquals(22_000, service.quote("HN", 100_000));
    }

    @Test
    void businessRuleDoesNotNeedStaticMock() {
        assertEquals(0, service.quote("HCM", 200_000));
        assertEquals(30_000, service.quote("OTHER", 150_000));
        assertThrows(IllegalArgumentException.class,
                () -> service.quote("HCM", -1));
    }
}
```

The first test checks three points: **before/during/after scope**. `verify(..., times(1))` verifies the service called the static method once when `quote` ran inside the scope. The second test intentionally throws **inside** the block to demonstrate `try-with-resources` still closes the scope before the outer assertion checks the real 22,000 fee. The third test relies on real behavior to verify free-shipping and default-region rules.

**Expected when running the unaltered code:** all three tests PASS. This is inferred from the provided code, not an observed Gradle output in this environment.

Note: `RegionFees.baseFee("HCM")` inside the `fees.when(...)` lambda is used by Mockito to **define the stub**, so do not expect it to count as a business call toward `verify(times(1))`. The test calls `service.quote("HCM", 100_000)` only once inside the scope.

### 5.3. When `@BeforeEach`/`@AfterEach` Is Needed with Spring Boot

**`src/test/java/com/example/staticmock/DeliveryQuoteSpringBootTest.java`**

```java
package com.example.staticmock;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class DeliveryQuoteSpringBootTest {
    @Autowired
    private DeliveryQuoteService service;

    private MockedStatic<RegionFees> fees;

    @BeforeEach
    void openScope() {
        fees = Mockito.mockStatic(RegionFees.class);
    }

    @AfterEach
    void closeScope() {
        if (fees != null) {
            fees.closeOnDemand();
        }
    }

    @Test
    void hanoiFeeCanBeStubbedForThisTest() {
        fees.when(() -> RegionFees.baseFee("HN"))
                .thenReturn(2_000);

        assertEquals(2_000, service.quote("HN", 100_000));
    }

    @Test
    void hcmFeeCanBeStubbedForAnotherTest() {
        fees.when(() -> RegionFees.baseFee("HCM"))
                .thenReturn(7_000);

        assertEquals(7_000, service.quote("HCM", 100_000));
    }
}
```

`@SpringBootTest` starts the application context and injects the service. By default JUnit Jupiter creates a fresh test instance per test method (`PER_METHOD`), yet **the Spring context can be cached** across methods/classes; creating a fresh test instance does not close a static mock. `closeScope()` is what terminates each scenario's scoped mock.

In this setup, tests are assumed to run sequentially on the thread executing the callbacks. If you enable JUnit parallel execution or offload work to other threads, re-evaluate **thread ownership** for opening, using, and closing static mocks. Never use a `static MockedStatic<...>` field or pass the handle to other threads.

### 5.4. Automatic Lifecycle Management via MockitoExtension

Mockito 5 also supports managed static mocks when a field or parameter of type `MockedStatic<T>` is annotated with `@Mock` and processed by the corresponding Mockito/JUnit extension.

**`src/test/java/com/example/staticmock/ExtensionManagedStaticTest.java`**

```java
package com.example.staticmock;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(MockitoExtension.class)
class ExtensionManagedStaticTest {
    @Mock
    private MockedStatic<RegionFees> fees;

    @Test
    void extensionManagesStaticScope() {
        fees.when(() -> RegionFees.baseFee("HN"))
                .thenReturn(5_000);

        DeliveryQuoteService service = new DeliveryQuoteService();
        assertEquals(5_000, service.quote("HN", 100_000));
    }
}
```

Here `MockitoExtension` manages creation and release along the test lifecycle. Do not open another `Mockito.mockStatic(RegionFees.class)` for the same class while the extension-managed scope is active; that can trigger a duplicate registration error on the same thread.

The `@Mock MockedStatic<T>` mechanism is safe only when **the extension/runner actually manages its lifecycle**. If you create the handle manually, you must still close it manually or via `try-with-resources`; an `@Mock` on another field does not clean up manual static mocks.

## 6. Counter-Example: Why Forgetting to Close Leaks State

The snippet below is **intentionally broken to illustrate an anti-pattern** and must not be placed into Section 5's runnable suite:

```java
class LeakyStaticTest {
    @Test
    void stubsStaticAndForgetsCleanup() {
        MockedStatic<RegionFees> fees =
                Mockito.mockStatic(RegionFees.class);
        fees.when(() -> RegionFees.baseFee("HCM"))
                .thenReturn(0);

        assertEquals(0, RegionFees.baseFee("HCM"));
        // Forgot fees.close(): static mock can remain active on this thread.
    }

    @Test
    void expectsRealFee() {
        assertEquals(18_000, RegionFees.baseFee("HCM"));
    }
}
```

If the second test runs on the same thread **after** the first test, it can observe `0` from the forgotten scoped mock and FAIL. On a different thread or in reverse order, it might pass—a classic **flaky / order- and schedule-dependent test**. Moreover, another test calling `Mockito.mockStatic(RegionFees.class)` while the old static mock is still active on that thread can fail with an error like “static mocking is already registered in the current thread.”

**Fix at the root cause:** place `mockStatic` inside `try-with-resources`, pair setup with `close`/`closeOnDemand` in teardown, or let the extension manage its lifecycle. Do not “fix” it by adding `@TestMethodOrder` to run the victim test first, nor by forking a fresh JVM to mask an existing leak.

### What If an Assertion Fails Mid-Test?

With manual cleanup:

```java
MockedStatic<RegionFees> fees = Mockito.mockStatic(RegionFees.class);
fees.when(() -> RegionFees.baseFee("HN")).thenReturn(1_000);
assertEquals(99_000, RegionFees.baseFee("HN")); // Intentionally FAILS.
fees.close(); // Never reached because the assertion failed.
```

the `close()` call after the assertion **never executes**. With `try-with-resources`, Java still cleans up the scoped mock when unwinding out of the block from `AssertionFailedError`. That is a key reason to prefer language-managed resource blocks over cleanup lines at the end of a test.

A clear alternative if manual control is required:

```java
MockedStatic<RegionFees> fees = Mockito.mockStatic(RegionFees.class);
try {
    fees.when(() -> RegionFees.baseFee("HN")).thenReturn(1_000);
    assertEquals(1_000, RegionFees.baseFee("HN"));
} finally {
    fees.close();
}
```

These counter-examples are **excerpts** meant for a test class with proper imports, not standalone Java files. `try-with-resources` is usually shorter and less error-prone.

## 7. APIs Easily Confused with `close()`

`MockedStatic` provides methods to control stubbing and interactions, yet **only closing the scope removes the static mock's effect**:

- `fees.when(...).thenReturn(...)` defines behavior inside the scope.
- `fees.verify(...)` checks that expected static calls occurred.
- `fees.reset()` clears stubbing and invocation history while the scope remains active; unstubbed calls may continue receiving default answers.
- `fees.clearInvocations()` clears verification history, **without** restoring real method logic.
- `fees.isClosed()` merely reports status, **without** releasing resources.
- `fees.close()` releases the scope; calling it a second time throws an error.
- `fees.closeOnDemand()` releases if needed and is safe if already closed.
- `Mockito.reset(otherMock)` or setting `fees = null` does not terminate an active `MockedStatic`.

For example, resetting a static mock and calling `RegionFees.baseFee("HCM")` can **still skip the real method** because static mocking remains active. Thus “another test got fee 0” after a reset does not prove a production bug; check whether an unclosed scoped mock is still active.

Do not rely on clearing global framework state as a substitute for clear resource ownership. Managing the handle where it is created keeps tests isolated and easy to debug.

## 8. Combining with Spring Boot: Context Cache vs. Static Mock Scope

Spring TestContext can **cache `ApplicationContext`** to cut startup time; singleton beans are reused across compatible tests. This is completely independent of Mockito's `MockedStatic` lifecycle.

| Mechanism | Managed unit | State after test |
| --- | --- | --- |
| JUnit `PER_METHOD` | Test class instance | New test object in the next test; does not release a leaked static mock |
| Spring TestContext cache | `ApplicationContext` and beans | Reused across tests with equivalent context config |
| Mockito `MockedStatic` | Scoped mock on creating thread | Remains active until `close`/`closeOnDemand` or extension completion |
| External data | DB, message broker, files, global caches | Needs separate cleanup/isolation; not rolled back by closing a static mock |

`@DirtiesContext` tells Spring to discard a dirty context, yet it is **not an API to close `MockedStatic`**. Using `@DirtiesContext` to “fix” a static mock leak only slows down the suite without fixing the cause.

Similarly, `@MockBean` or Spring context bean overrides are not equivalent to `Mockito.mockStatic`: one replaces a **Spring bean dependency** in the test context, while the other intercepts **static method calls on a thread**. To test static calls made by a service, know which thread executes the service. A `MockMvc` setup may run the MVC pipeline directly on the test thread, whereas requests to a real embedded server typically run on server worker threads; do not assume a JUnit-thread static mock covers both.

**Never treat static mocking as a substitute for full integration test state management.** Closing a scope does not roll back a committed transaction, delete files, drain queues, or reset `static` counters mutated before the mock opened.

## 9. Static Mocks and Asynchronous / Parallel Execution

Mockito documents `MockedStatic` as scoped to the creating thread. Consider this conceptual snippet:

```java
try (MockedStatic<RegionFees> fees =
             Mockito.mockStatic(RegionFees.class)) {
    fees.when(() -> RegionFees.baseFee("HN")).thenReturn(1_000);

    // Test thread has the static mock:
    assertEquals(1_000, RegionFees.baseFee("HN"));

    // Another worker thread normally uses real logic;
    // do not assume the test thread's stub propagates to worker threads.
}
```

If a service offloads work to `CompletableFuture.supplyAsync`, `@Async`, or a web server thread, stubs opened on the JUnit thread **do not automatically apply there**. Likewise, **never pass the same `MockedStatic` to a worker thread for `when` or `close`**, because the API is not designed for cross-thread use.

When tests need to control a dependency used across multiple threads, replacing the static call with an **injectable dependency** (e.g., a `FeePolicy` or `Clock` interface injected via constructor) is far more reliable. Stub/mock at the object boundary and follow that dependency's thread-safety contract. Changing JUnit thread scheduling just to “make the static stub hit” hides timing bugs rather than solving them sustainably.

**Enabling parallel execution:** if two tests static-mock the same class on **two separate threads**, thread-local scoping means they do not automatically collide over the class registration. However, if tests share a mock handle, mutable singleton, DB rows, or fixtures, race conditions still happen. Do not take thread-local scoping as a guarantee that all static-mock tests are parallel-safe.

## 10. When Should You Replace Static Mocks with Dependency Injection?

Static mocking makes sense for legacy code, rarely touched static adapters, or code you cannot refactor right away. Yet if a service increasingly needs static stubs for time, randomness, system state, network, pricing, or feature flags, static mocking signals **hidden dependencies in business code**.

Instead of:

```java
public int quote(String region, int orderAmount) {
    return RegionFees.baseFee(region);
}
```

you can define an interface and inject the dependency:

```java
public interface FeePolicy {
    int baseFee(String region);
}

@Component
public class DefaultFeePolicy implements FeePolicy {
    @Override
    public int baseFee(String region) {
        return RegionFees.baseFee(region);
    }
}

@Service
public class QuoteService {
    private final FeePolicy policy;

    public QuoteService(FeePolicy policy) {
        this.policy = policy;
    }

    public int quote(String region) {
        return policy.baseFee(region);
    }
}
```

These are **design excerpts** meant for separate files/classes with appropriate Spring imports, not part of Section 5's runnable files. In a unit test, you can create `FeePolicy policy = Mockito.mock(FeePolicy.class)`, stub `policy.baseFee("HCM")`, and pass `policy` to `new QuoteService(policy)`. The test then controls the dependency **via objects and constructors** rather than patching thread-wide static calls.

For new code, injection yields clearer, easier-to-test designs. For older code not yet refactored, `try-with-resources` is the safe boundary to prioritize.

## 11. Running the Examples and Verifying Zero State Leakage

In a project with Gradle Wrapper, run:

```bash
./gradlew test --tests com.example.staticmock.DeliveryQuoteServiceTest
./gradlew test --tests com.example.staticmock.DeliveryQuoteSpringBootTest
./gradlew test --tests com.example.staticmock.ExtensionManagedStaticTest
./gradlew test
```

On Windows, use `gradlew.bat test` with the same arguments. When the sample code and environment meet prerequisites, all tests are designed to PASS. Exact Gradle console output depends on version and runner; do not treat the commands above as observed execution logs.

Recommended verification sequence:

1. Run the scoped unit test: inside the block returns the fake fee; after the block returns the real fee.
2. Run the test throwing an exception inside the scope: exiting the block still restores real behavior.
3. Run the multi-method Spring Boot test: scope opens before each test and closes after each test.
4. Run the whole suite as well as individual tests: results must not depend on another test initializing mocks beforehand.
5. When moving to parallel or async execution, explicitly verify **which thread executes the static call**, not just that stubbing ran on another thread.
6. If a test fails with duplicate static mock registration, track down the open, unclosed scope on that thread rather than deleting the failing test.

A useful falsification check in an **isolated experiment** is temporarily removing `try-with-resources`, creating an unclosed static mock, and running tests sequentially on the same thread; you will observe later tests receiving stale stubs or registration collisions. Restore `try-with-resources` to fix it. Never commit that counter-example to CI because it pollutes other tests.

### Environment Limitations to Know

- Mockito 5 uses the inline mock maker by default on standard JVMs; if a project forces a different mock maker or runs on a platform without instrumentation support, static mocking may be unavailable.
- On Java 21+, dynamic agent attachment can emit JDK warnings or face restrictions; you may need to configure `mockito-core` as a `-javaagent` on the test JVM per your Mockito/JDK documentation. That is an **instrumentation** concern, completely distinct from forgetting to close `MockedStatic`.
- Some JDK classes, classloader-bound classes, or JVM intrinsics are unsuitable or disallowed for static mocking. Prefer mocking application-owned classes like `RegionFees` in the example.
- Do not equate “mock didn't apply on a worker thread” with “Mockito does not support static mocking”; inspect thread identity, mock maker, and scope.

Official documentation references:

- Mockito `MockedStatic<T>`: https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/MockedStatic.html
- Mockito `ScopedMock` (`close`, `closeOnDemand`, `isClosed`): https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/ScopedMock.html
- Mockito `Mockito.mockStatic` and Java instrumentation: https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html

## 12. Review Checklist for Tests Using Static Mocks

| Review question | Requirement to pass |
| --- | --- |
| Where is the static mock created? | Clear scope-opening point inside the test or setup |
| Who is responsible for closing it? | `try-with-resources`, `finally`, `@AfterEach`, or properly configured extension |
| When an assertion throws, does the scope still close? | Cleanup executes even when the test fails |
| Is the mock closed right after it is needed? | Narrow scope; not active across unrelated tests |
| Is `reset` confused with `close`? | Uses `close`/`closeOnDemand` to end registration |
| Is the same class mocked multiple times on one thread? | Never opens a duplicate scope while an earlier one is still open |
| Do tests share a handle or `static` field? | Never passes handles across threads or tests |
| Does code under test run on async/server threads? | Static stub is opened on the executing thread or replaced by DI |
| Is real behavior verified after closing? | Where appropriate, asserts real values are restored |
| Does closing scope clean up real state? | DB, mutable static fields, caches, and Spring beans are cleaned separately if needed |

### Self-Check Exercises

**A.** A test opens `MockedStatic<RegionFees>` in `@BeforeEach` and only sets the handle to `null` in `@AfterEach`. Is the scope cleaned up? **No**: clearing the reference does not release the static mock registration. Call `close()` or `closeOnDemand()`.

**B.** A test opens a mock in `try-with-resources` and an assertion throws an exception. Is the static mock still active after leaving the block? **No**, Java closes `AutoCloseable` resources automatically when exiting the block (barring extraordinary failures in cleanup itself). That is the advantage of managed scopes.

**C.** `fees.reset()` is called, followed by the real static method while the scope stays open. Does real logic run? **No**; resetting stubbing/invocations does not close the mock.

**D.** The test thread stubs `RegionFees.baseFee("HN")`, while the service calls the method on an `@Async` worker. Is the worker guaranteed to see the stub? **No**; Mockito's static mocks are thread-local.

**E.** Is `@DirtiesContext` the proper fix for an unclosed static mock? **No**; it targets the Spring `ApplicationContext` cache, not Mockito scoped mocks.

**F.** A suite passes individually yet fails together, occasionally reporting “static mocking is already registered.” What should you look for first? **Look for a static mock opened on that thread and left unclosed**, especially in shared setups or early-failing test branches; fix scoping/cleanup rather than changing test order.

**Conclusion:** A static mock is a **resource with clear ownership and lifecycle**. Using `try (MockedStatic<T> mock = Mockito.mockStatic(...)) { ... }` per scenario is the easiest default to verify. For shared setup, pair opening with `@AfterEach` cleanup or let `MockitoExtension` manage the lifecycle. Once closed, verify real behavior returns, and remember that Spring contexts, real data, and worker threads have separate lifecycles requiring separate management.
