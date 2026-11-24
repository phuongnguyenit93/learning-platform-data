# Singleton Beans, Shared Mocks, and Mutable State

## 1. Why Does a Test PASS Individually but FAIL in the Full Suite?

In the **Spring Boot - testing** module, under **Isolation and Parallel Execution**, a common phenomenon is that two tests pass when run individually, yet occasionally fail when run together or with JUnit parallelism enabled. The root cause may lie not in the assertions, but in **shared objects**:

- Spring beans default to **singleton** scope: the same `ApplicationContext` returns the exact same bean instance wherever that bean is injected.
- Spring TestContext **caches `ApplicationContext`** across test classes with equivalent configurations, allowing multiple tests to share the same singleton instance.
- `@MockitoBean` replaces a bean in the context with a **Mockito mock**, which lives inside the context; if multiple tests share that context, they can stub, verify, or reset **the same mock** simultaneously.
- A `static Map`, cache, fake clock, singleton repository, or embedded service can accumulate state across tests.
- JUnit may create a **new test class instance per method** while the Spring beans injected into it are **still the same singletons**.

Broken example:

~~~java
@Component
class UnsafeCounter {
    private int count;

    void increment() {
        count++; // Not atomic, persists across multiple test methods.
    }

    int value() {
        return count;
    }
}
~~~

The snippet above is a **counter-example**, not part of the runnable project below. Test A calls `increment()` once and asserts `value()==1`; Test B does the same. When the Spring context is reused, Test B may observe `2`. If both tests run concurrently, `count++` also introduces race conditions and lost updates. Adding `Thread.sleep` only hides or amplifies the bug without fixing synchronization.

The goal is **proper isolation at each level**:

1. **Dedicated test fixtures per test** when testing pure business logic.
2. **Stateless beans** if a service is shared.
3. **Partitioned mutable state** namespaced by test ID/tenant/cart with thread-safe primitives if a singleton must hold state.
4. **Do not run tests relying on shared `@MockitoBean`/`@DirtiesContext` in parallel**, or redesign so a shared mock is unnecessary.
5. Use `@ResourceLock`, `@Isolated`, fixture cleanup, and `@DirtiesContext` **within their proper scope**, rather than applying them indiscriminately to mask inter-test dependencies.

This lesson includes a **Java 17, Spring Boot 3.5.16, JUnit Jupiter, Mockito, AssertJ** project with 13 test cases across five classes: pure unit tests with isolated mocks, an isolated Spring mock bean test, a parallel Spring singleton test with partitioned state, a latch-based atomic concurrency test, and a static resource lock example.

## 2. Different Scope Layers That Are Easily Confused

| Scope | Created / Managed by | Automatically isolated per `@Test`? |
| --- | --- | --- |
| Local variable in a method | JVM per call | Generally yes |
| Test instance field, JUnit `PER_METHOD` | JUnit creates a new test instance per method | **Yes for the field**, not for injected objects |
| Test instance field, JUnit `PER_CLASS` | One test instance for the whole class | **No** |
| `static` field | JVM/classloader | No; shared across instances/classes |
| Spring `@Singleton` bean | One `ApplicationContext` | No; shared inside the context |
| `@Prototype` bean | Spring creates per container request | Does not automatically turn injection into a singleton into per-call prototype |
| `@MockitoBean` | Spring test bean override in context | Reset between methods by default; **not a separate mock per method** |
| Mockito `@Mock` in Jupiter tests | MockitoExtension/test instance | Typically separate per test invocation |
| `Mockito.mock(...)` inside a method | Test method | Separate if reference is not shared |
| Cached `ApplicationContext` | Spring TestContext `ContextCache` in JVM | Can be shared across multiple test classes |
| In-memory H2 database with fixed name | Datasource/JVM/connection | No, if sharing the same DB URL |
| External broker / DB / Redis / filesystem | Infrastructure | No, unless separate namespaces/resources are created |

The statement "JUnit creates a new test instance for each test" is **true for the default lifecycle**, but does not prove that Spring singletons, mocks inside a cached context, static Maps, or databases have been reset. When a test exhibits races or flakiness, draw the **ownership graph of every mutable object**.

### Example of a Reference Graph

~~~text
JUnit Test A instance ───┐
                        ├─> cached Spring ApplicationContext
JUnit Test B instance ───┘           |
                                     +─> CheckoutService singleton
                                     |       |
                                     |       +─> PricingClient singleton/mock
                                     |
                                     +─> CartRegistry singleton
                                              |
                                              +─> mutable Map cartId -> total
~~~

Two different test instances do **not** create two different `CartRegistry` instances. When one test calls `clear()` on the entire map in `@BeforeEach`, it modifies data that another test may currently need.

## 3. Spring Singletons Do Not Necessarily Cause Races

Singleton merely means one bean instance per context. **An immutable/stateless singleton can be completely safe under parallel execution.**

Example:

~~~java
@Service
public class TaxCalculator {
    public long addFixedTax(long cents) {
        return Math.addExact(cents, 100L);
    }
}
~~~

This is an illustrative snippet requiring the `@Service` import. It holds no mutable per-request state. Having multiple threads call the same instance will not cause cross-test data leakage via internal fields.

Conversely, a service holding per-request state in a field:

~~~java
@Service
public class BadCheckoutService {
    private String currentCartId;

    public void setCurrentCartId(String cartId) {
        currentCartId = cartId;
    }

    public String currentCartId() {
        return currentCartId;
    }
}
~~~

is a **counter-example**. Two requests/tests sharing the bean can overwrite each other's `currentCartId`. Changing `String` to `volatile String` only guarantees visibility of the latest value, not **request isolation**. The proper approach is passing `cartId` into methods and using request-local data or properly keyed storage.

Rule: **singleton services should be stateless, or internal state must have explicit concurrency semantics and scoping.**

## 4. Three Distinct Failure Modes: Race, Leak, and Reset Conflict

**State leak (sequential):** Test A creates state in a singleton without cleaning up; Test B runs afterward and sees that state. This bug can occur even with parallelism disabled.

**Data race (parallel):** Test A and B mutate an unsynchronized `HashMap`/field concurrently; results are nondeterministic. Races can cause lost updates and stale reads even if the store starts empty.

**Shared mock conflict:** Test A stubs `when(gateway.price("pen")).thenReturn(100)`, while Test B changes it to 200 or Spring resets the mock before A finishes verifying. Each test passes alone, but verification counts calls from another test, or stubbing disappears mid-test.

~~~text
Test A                     Test B
  stub mock -> 100
                             stub same mock -> 200
  invoke checkout("pen")
                             verify(mock, times(1))...
  verify(mock, times(1))
                             @AfterEach resets shared mock
  -> stubbing/verify can interfere with each other
~~~

Spring `@MockitoBean` resets mocks after each test method by default, but **per-test-lifecycle resets do not serialize all tests**. Spring Framework documentation warns **against running tests in parallel** when they use `@MockitoBean` or `@MockitoSpyBean` in the standard manner.

Three failures require **three different fixes**; raising timeouts or scattering `Mockito.reset` everywhere does not address the root cause.

## 5. Spring TestContext ContextCache

Spring TestContext caches `ApplicationContext` instances to avoid repeatedly restarting Spring Boot. The cache keys primarily on context configuration: classes/locations/active profiles/test properties/context customizers and related metadata. Bean overrides like `@MockitoBean` are context customizers and therefore affect the cache key.

Key points to remember:

- Two test classes with equivalent context configurations **can reuse the same context** within one JVM.
- The context cache is **process-static**, not shared across multiple Gradle forks/JVM processes.
- `@BeforeEach` runs before every method, but does not automatically reset singleton beans.
- `@AfterEach` deleting a test's data can fail if it deletes **state currently in use by another test**.
- `@DirtiesContext` marks the context dirty so the framework evicts and closes it; this incurs restart overhead and risks breaking concurrent tests using that context.
- `@MockitoBean` field names/qualifiers can affect the cache key. Keep names consistent when intentionally reusing the same override configuration.
- Different test configurations can create **two contexts**, yet both may still point to the **same database, Redis, broker, or static field** outside the context.

Context caching is **not** a bug; it is a valuable optimization. Write tests that tolerate bean instance reuse.

## 6. Mockito @Mock vs Spring @MockitoBean: Not the Same

| API | Where it lives | Effect |
| --- | --- | --- |
| `@Mock` + `MockitoExtension` | Test instance/Mockito test lifecycle | Pure mock, does not replace a Spring bean automatically |
| `Mockito.mock(PricingClient.class)` | Wherever you hold the reference | Easy per-method fixture, no Spring needed |
| `@InjectMocks` | Mockito test fixture | Constructor/field injection into a Mockito-created object; does **not** replace context beans |
| `@MockitoBean` | Bean override in Spring test context | Replaces a bean in `ApplicationContext` so other Spring beans inject the mock |
| `@MockitoSpyBean` | Wraps a bean in the Spring context | Invokes real code for unstubbed methods; watch out for side effects and AOP |
| Spring Boot `@MockBean` | Legacy API, deprecated since Boot 3.4 | With Boot 3.5, prefer Spring Framework's `@MockitoBean` |

`@MockitoBean` import:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
~~~

Spring Framework 6.2 `@MockitoBean` defaults to `reset` **AFTER**: automatically resetting stubbing/interactions after each test method. `@MockitoBean(enforceOverride = true)` requires that **a real bean must already exist** to replace; it will not silently create a new mock when no target exists. Without enforcement, a missing bean may be created to satisfy dependencies, which can mask test setup bugs.

**Do not place `@Mock` on a field and expect Spring's `@Autowired CheckoutService` to pick it up.** They belong to two different DI containers/lifecycles. In pure unit tests, call `new CheckoutService(mock, new CartRegistry())` directly; in Spring integration tests, use `@MockitoBean` or an appropriate test configuration.

## 7. Meaning and Limits of Default MockReset.AFTER

Suppose a test declares:

~~~java
@MockitoBean
PricingClient pricingClient;
~~~

After a test method, Spring TestContext resets the mock according to `MockReset.AFTER`. This **clears Mockito stubbing/interaction history** per the reset policy, but:

1. Does not create a new bean instance per method.
2. Does not clear `CartRegistry` or other singletons' state.
3. Does not roll back database/Redis/queue state.
4. Does not guarantee background async tasks have completed.
5. Is unsafe for **concurrent tests sharing the mock**, as Test A may reset while B is invoking/verifying.
6. Does not ensure task callbacks are canceled before reset.
7. Does not prevent double invocations caused by running endpoints or schedulers.

If you need `reset=MockReset.NONE` (e.g., multi-stage flows), you **must manage** mock history/lifecycle manually and definitely avoid mixing it with parallel tests. `Mockito.clearInvocations(mock)` keeps stubbing while `Mockito.reset(mock)` wipes both stubbing and invocations; both can break concurrently running tests if the mock is shared.

**Preferred choice:** for testing pure business logic, use per-method Mockito mocks with `MockitoExtension`. When Spring wiring with `@MockitoBean` is needed, **serialize/exclude from parallel execution** per official guidance.

## 8. Practical Rules for @Isolated, @Execution, and @ResourceLock

JUnit Jupiter offers multiple coordination levels:

- **`@Execution(CONCURRENT)`**: allows tests to run in parallel per engine configuration.
- **`@Execution(SAME_THREAD)`**: keeps tests inside the class in `same_thread` execution mode; **does not prevent another class from running concurrently**.
- **`@Isolated`** on a test class: instructs Jupiter not to run that class concurrently with other Jupiter tests **within the same execution plan/engine**. Useful for classes using `@MockitoBean`.
- **`@ResourceLock("shared-key", mode = READ_WRITE)`**: tests **declaring compatible lock keys** are coordinated by JUnit; the JUnit lock covers `@BeforeEach`/`@AfterEach` lifecycles.
- **`@DirtiesContext`**: evicts/recreates the context, *not a lock*; avoid careless use with parallelism.
- **`@TestInstance(PER_CLASS)`**: shares one test instance, not synchronization.

Critical limitation: JUnit's `@Isolated` and `@ResourceLock` **do not lock across separate JVMs/CI shards/machines**, and do not await async background threads spawned after a test method returns. External Redis/DB/brokers require separate namespaces or resource-level isolation outside JUnit.

If test methods share a static map and you want to serialize them, **every test accessing that resource must declare the same `@ResourceLock`**. One test forgetting the lock can still run concurrently even when all others lock properly.

## 9. Demo Design: Same Singleton, State Partitioned by Cart ID

The example uses a singleton `CheckoutService`:

~~~text
Test / HTTP request (cartId=unique)
       |
       v
CheckoutService singleton (stateless)
       |
       +---- PricingClient singleton (or @MockitoBean)
       |
       +---- CartRegistry singleton
                 |
                 +-- ConcurrentHashMap<cartId, totalCents>
~~~

`CheckoutService` holds no `currentCartId` field; every method accepts `cartId` as an argument. `CartRegistry` still holds **mutable state**, using a `ConcurrentHashMap` and atomic `compute` per key. Each test generates its own ID and cleans up only its own ID.

**Two separate concerns**:

- **Thread safety:** two threads adding to the **same cart ID** do not lose updates.
- **Test isolation:** two tests using **two different cart IDs** never read/write/delete each other's state.

A thread-safe Map **does not automatically provide test isolation** if all tests use the ID `"test-cart"` and call `clear()` on the entire map.

## 10. Project Structure and Gradle

Sample project:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/isolation/
    IsolationDemoApplication.java
    PricingClient.java
    DefaultPricingClient.java
    CartRegistry.java
    CheckoutService.java
src/test/java/com/example/isolation/
    CheckoutPureUnitTest.java
    CheckoutSpringMockTest.java
    CheckoutSpringParallelTest.java
    CartRegistryConcurrencyTest.java
    StaticScratchLockTest.java
src/test/resources/
    junit-platform.properties
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'spring-singleton-isolation-demo'
~~~

**`build.gradle` (Java 17, Spring Boot 3.5.16):**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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

tasks.named('test', Test) {
    useJUnitPlatform()
    // Caps Gradle test JVM forks; does NOT disable
    // concurrency inside the JUnit Jupiter engine.
    maxParallelForks = 1
}
~~~

`spring-boot-starter-test` provides JUnit Jupiter, Mockito, the Mockito Jupiter extension, AssertJ, and Spring TestContext. No database, web server, Docker, or external network is required in the sample app.

### Enabling Bounded Jupiter Parallelism

**`src/test/resources/junit-platform.properties`:**

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
~~~

These settings allow **roughly four workers** inside the same test JVM. `CheckoutSpringMockTest` uses `@Isolated` so it does not contend over mocks/context with other tests in the same Jupiter engine; pure/concurrent tests use only isolated state.

This configuration is **for learning and demonstrating isolation**, not a blanket recommendation to turn on parallelism across an entire production suite immediately. Suites with `@MockitoBean`, `@DirtiesContext`, or shared DB/brokers should be evaluated and grouped carefully. Every test using a mock bean should be excluded from parallel execution or run in its own execution plan; `@Isolated` demonstrates blocking concurrency within one engine.

## 11. Spring Boot Application

**`src/main/java/com/example/isolation/IsolationDemoApplication.java`:**

~~~java
package com.example.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationDemoApplication.class, args);
    }
}
~~~

The production components below reside in package `com.example.isolation` so `@SpringBootApplication` component-scans them.

No scheduler or background worker is added to the demo: this lesson focuses on singletons/mocks and parallel tests without introducing a third asynchronous actor that obscures results.

## 12. PricingClient and Default Implementation

**`src/main/java/com/example/isolation/PricingClient.java`:**

~~~java
package com.example.isolation;

public interface PricingClient {
    long unitPriceCents(String sku);
}
~~~

**`src/main/java/com/example/isolation/DefaultPricingClient.java`:**

~~~java
package com.example.isolation;

import org.springframework.stereotype.Component;

@Component
public class DefaultPricingClient implements PricingClient {

    @Override
    public long unitPriceCents(String sku) {
        return switch (sku) {
            case "pen" -> 200L;
            case "book" -> 500L;
            case "eraser" -> 50L;
            default -> throw new IllegalArgumentException(
                    "Unknown sku: " + sku
            );
        };
    }
}
~~~

This bean is **stateless**, so multiple threads can call the same instance without creating shared data. A `null` `sku` input throws `NullPointerException` due to switching on null (Java 17); the service validates inputs.

In `CheckoutSpringMockTest`, `@MockitoBean(enforceOverride=true)` replaces the **PricingClient bean** (which is `DefaultPricingClient`) with a Mockito mock. In `CheckoutSpringParallelTest`, Spring uses the production `DefaultPricingClient` with no mock override.

This is a key reason to use a real bean override in integration tests: pure Mockito `@Mock` does **not** replace the instance Spring injects into `CheckoutService`.

## 13. CartRegistry: Mutable Yet Explicitly Scoped with Atomic Updates

**`src/main/java/com/example/isolation/CartRegistry.java`:**

~~~java
package com.example.isolation;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Component;

@Component
public class CartRegistry {

    private final ConcurrentMap<String, Long> totals =
            new ConcurrentHashMap<>();

    public long add(String cartId, long cents) {
        if (cartId == null || cartId.isBlank() || cents <= 0) {
            throw new IllegalArgumentException(
                    "Invalid cart or price"
            );
        }

        return totals.compute(
                cartId,
                (id, previous) -> Math.addExact(
                        previous == null ? 0L : previous,
                        cents
                )
        );
    }

    public long total(String cartId) {
        if (cartId == null || cartId.isBlank()) {
            throw new IllegalArgumentException(
                    "Invalid cart"
            );
        }
        return totals.getOrDefault(cartId, 0L);
    }

    public void remove(String cartId) {
        totals.remove(cartId);
    }
}
~~~

`ConcurrentHashMap.compute` computes and updates **one key** atomically per ConcurrentHashMap's contract. If eight threads concurrently call `add("shared", 1)` 50 times each, the result must be **400** with no lost increments.

**However**, `remove(cartId)` called by one test while another worker is still updating the same key can delete valid state. Thread safety does not equate to proper business sequencing. In the suite, each test cleans up **only its own key after tasks finish**.

`Math.addExact` detects overflow rather than silently wrapping a `long`; real money requires currencies, ledgers, and DB atomicity. This in-memory store **does not survive restarts** and does not protect across multiple pods; it is a test model.

## 14. CheckoutService: Singleton Without Storing Cart ID in a Field

**`src/main/java/com/example/isolation/CheckoutService.java`:**

~~~java
package com.example.isolation;

import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PricingClient prices;
    private final CartRegistry carts;

    public CheckoutService(
            PricingClient prices,
            CartRegistry carts
    ) {
        this.prices = Objects.requireNonNull(prices, "prices");
        this.carts = Objects.requireNonNull(carts, "carts");
    }

    public long addItem(String cartId, String sku) {
        if (cartId == null || cartId.isBlank()
                || sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "Invalid item request"
            );
        }

        long cents = prices.unitPriceCents(sku);
        if (cents <= 0) {
            throw new IllegalArgumentException(
                    "Non-positive item price"
            );
        }
        return carts.add(cartId, cents);
    }

    public long total(String cartId) {
        return carts.total(cartId);
    }
}
~~~

`CheckoutService` holds **no mutable per-request fields**, only references to collaborators. It is singleton-safe regarding *its own service fields*, while its collaborator `CartRegistry` is mutable. Tests still need isolation by `cartId`.

This is an **additive operation with side effects**: calling `addItem("A","pen")` twice sums to 400; it is not idempotent. If an operation arrives over HTTP/queues and can be retried, add a business idempotency key and persistent unique constraint/ledger, which is outside this lesson's test isolation scope.

## 15. Pure Unit Tests: Dedicated Mock and Store per Method

**`src/test/java/com/example/isolation/CheckoutPureUnitTest.java`:**

~~~java
package com.example.isolation;

import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CheckoutPureUnitTest {

    @Mock
    PricingClient pricingClient;

    private CheckoutService checkout;
    private CartRegistry carts;
    private String cartId;

    @BeforeEach
    void setUp() {
        carts = new CartRegistry();
        checkout = new CheckoutService(pricingClient, carts);
        cartId = "unit-" + UUID.randomUUID();
    }

    @Test
    void unitMockAndStoreAreFreshForEachMethod() {
        when(pricingClient.unitPriceCents("pen"))
                .thenReturn(100L);

        assertThat(checkout.addItem(cartId, "pen"))
                .isEqualTo(100L);
        assertThat(carts.total(cartId))
                .isEqualTo(100L);
        verify(pricingClient).unitPriceCents("pen");
    }

    @Test
    void separateSkuPricesAccumulateWithinOneFixture() {
        when(pricingClient.unitPriceCents("book"))
                .thenReturn(300L);
        when(pricingClient.unitPriceCents("pen"))
                .thenReturn(50L);

        checkout.addItem(cartId, "book");
        checkout.addItem(cartId, "pen");

        assertThat(carts.total(cartId))
                .isEqualTo(350L);
        verify(pricingClient).unitPriceCents("book");
        verify(pricingClient).unitPriceCents("pen");
    }

    @Test
    void invalidPriceDoesNotMutateLocalStore() {
        when(pricingClient.unitPriceCents("pen"))
                .thenReturn(0L);

        assertThatThrownBy(
                () -> checkout.addItem(cartId, "pen")
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessageContaining("Non-positive item price");

        assertThat(carts.total(cartId)).isZero();
    }
}
~~~

**Three tests** use `@Mock` from `MockitoExtension`, creating `new CartRegistry()` and `new CheckoutService(...)` in `@BeforeEach`. JUnit's default lifecycle is `PER_METHOD`, so every test gets its own instances/fixtures. These tests can run in parallel without touching a shared Spring context.

**Do not use `@SpringBootTest` for pure business unit tests.** Each test only needs the behavior of `CheckoutService` and `CartRegistry`; booting a context adds overhead and creates opportunities for state leakage.

If you want `@InjectMocks`, Mockito can instantiate `CheckoutService`, provided you ensure `CartRegistry` and mock injection are clear; direct constructor injection in the example keeps the dependency graph easier to inspect.

## 16. Spring Mock Bean Test: Using @Isolated to Prevent Overlap

**`src/test/java/com/example/isolation/CheckoutSpringMockTest.java`:**

~~~java
package com.example.isolation;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.Isolated;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@Isolated
@Execution(ExecutionMode.SAME_THREAD)
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CheckoutSpringMockTest {

    @Autowired
    CheckoutService checkout;

    @Autowired
    CartRegistry carts;

    @Autowired
    ApplicationContext context;

    @MockitoBean(enforceOverride = true)
    PricingClient pricingClient;

    private String cartId;

    @BeforeEach
    void createOwnCartId() {
        cartId = "mock-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanOwnCartOnly() {
        carts.remove(cartId);
    }

    @Test
    void springMockReplacesOnlyPricingDependency() {
        when(pricingClient.unitPriceCents("pen"))
                .thenReturn(350L);

        assertThat(context.getBean(PricingClient.class))
                .isSameAs(pricingClient);
        assertThat(checkout.addItem(cartId, "pen"))
                .isEqualTo(350L);
        verify(pricingClient).unitPriceCents("pen");
    }

    @Test
    void differentStubIsSetIndependentlyForEachTest() {
        when(pricingClient.unitPriceCents("book"))
                .thenReturn(700L);

        assertThat(checkout.addItem(cartId, "book"))
                .isEqualTo(700L);
        assertThat(carts.total(cartId))
                .isEqualTo(700L);
        verify(pricingClient).unitPriceCents("book");
    }

    @Test
    void invalidMockPriceDoesNotMutateSharedRegistry() {
        when(pricingClient.unitPriceCents("pen"))
                .thenReturn(0L);

        assertThatThrownBy(
                () -> checkout.addItem(cartId, "pen")
        ).isInstanceOf(IllegalArgumentException.class);

        assertThat(carts.total(cartId)).isZero();
        verify(pricingClient).unitPriceCents("pen");
    }
}
~~~

**Three tests** verify real Spring wiring with a bean override. Each test has its own cart ID and cleans up only its own cart; the Spring context/mock **may still be reused**, so these are not three separate `PricingClient` mocks.

Because Jupiter parallelism is enabled at the project level, this class carries **`@Isolated`** so it does not run alongside other Jupiter tests in the same execution plan. `@Execution(SAME_THREAD)` further specifies sequential execution across methods of this class. This is a deliberate measure for a test using a shared mock bean, not a requirement for every Spring test.

**Limitation:** `@Isolated` does not stop another Gradle fork process, Maven fork, or CI shard from accessing the same external resource. `@MockitoBean` `AFTER` reset still requires all async work of the test to finish before method teardown runs.

### Why Not Call Mockito.reset in @BeforeEach?

Spring test mocks are reset after each test method by default. Manually resetting before a test can mask lifecycle bugs and—more importantly—**break concurrent tests** if the mock is shared. With an isolated class, each method declares only the stubbing it needs, verifies only its own calls, and avoids order-dependent behavior.

## 17. Parallel Spring Integration Tests: Mutable Singleton Partitioned by ID

**`src/test/java/com/example/isolation/CheckoutSpringParallelTest.java`:**

~~~java
package com.example.isolation;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@Execution(ExecutionMode.CONCURRENT)
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CheckoutSpringParallelTest {

    @Autowired
    CheckoutService checkout;

    @Autowired
    CartRegistry carts;

    private String cartId;

    @BeforeEach
    void createOwnCart() {
        cartId = "parallel-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanOnlyOwnCart() {
        carts.remove(cartId);
    }

    @Test
    void penIsAddedToUniqueCart() {
        assertThat(checkout.addItem(cartId, "pen"))
                .isEqualTo(200L);
        assertThat(checkout.total(cartId))
                .isEqualTo(200L);
    }

    @Test
    void bookIsAddedToUniqueCart() {
        assertThat(checkout.addItem(cartId, "book"))
                .isEqualTo(500L);
        assertThat(checkout.total(cartId))
                .isEqualTo(500L);
    }

    @Test
    void twoUniqueCartsNeverShareTotals() {
        String second = "parallel-extra-" + UUID.randomUUID();

        try {
            assertThat(checkout.addItem(cartId, "pen"))
                    .isEqualTo(200L);
            assertThat(checkout.addItem(second, "book"))
                    .isEqualTo(500L);

            assertThat(carts.total(cartId)).isEqualTo(200L);
            assertThat(carts.total(second)).isEqualTo(500L);
        } finally {
            carts.remove(second);
        }
    }
}
~~~

**Three tests** can run in parallel inside the same Spring context. They use the production `DefaultPricingClient` (stateless) and the same singleton `CartRegistry`, yet each method has its own unique cart ID/cleanup. No test calls `carts.clearAll()`.

Conditions for safety:

- `CartRegistry.add` uses atomic `compute`, not a plain HashMap.
- IDs are never hard-coded identically across methods.
- `@AfterEach` deletes only the ID created by that test.
- No background task continues using the ID after cleanup.
- Test fields belong to the per-method test instance, not `@TestInstance(PER_CLASS)`.
- Tests do not mutate global properties, default locale/timezone, or shared DB tables without isolation.

**A shared singleton can be safe under parallel testing**, provided state ownership and concurrency semantics are proven. Do not assume every singleton needs `@DirtiesContext`.

## 18. Concurrent Unit Test: Proving Same-Key Updates Do Not Lose Increments

**`src/test/java/com/example/isolation/CartRegistryConcurrencyTest.java`:**

~~~java
package com.example.isolation;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import static org.assertj.core.api.Assertions.assertThat;

@Execution(ExecutionMode.CONCURRENT)
class CartRegistryConcurrencyTest {

    @Test
    void concurrentAddsToSameCartUseAtomicCompute()
            throws Exception {
        CartRegistry carts = new CartRegistry();
        ExecutorService pool =
                Executors.newFixedThreadPool(8);
        CountDownLatch ready = new CountDownLatch(8);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Void>> tasks = new ArrayList<>();

        try {
            for (int t = 0; t < 8; t++) {
                tasks.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Start gate timeout"
                        );
                    }
                    for (int i = 0; i < 50; i++) {
                        carts.add("shared-cart", 1L);
                    }
                    return null;
                }));
            }

            assertThat(
                    ready.await(5, TimeUnit.SECONDS)
            ).isTrue();

            start.countDown();
            for (Future<Void> task : tasks) {
                task.get(5, TimeUnit.SECONDS);
            }

            assertThat(carts.total("shared-cart"))
                    .isEqualTo(400L);
        } finally {
            start.countDown();
            pool.shutdownNow();
            assertThat(
                    pool.awaitTermination(5, TimeUnit.SECONDS)
            ).isTrue();
        }
    }

    @Test
    void independentCartsCanUpdateConcurrently()
            throws Exception {
        CartRegistry carts = new CartRegistry();
        ExecutorService pool =
                Executors.newFixedThreadPool(4);
        List<String> ids = new ArrayList<>();
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int i = 0; i < 4; i++) {
                String id = "cart-" + UUID.randomUUID();
                ids.add(id);
                tasks.add(pool.submit(() -> {
                    for (int k = 0; k < 100; k++) {
                        carts.add(id, 2L);
                    }
                }));
            }

            for (Future<?> task : tasks) {
                task.get(5, TimeUnit.SECONDS);
            }
            for (String id : ids) {
                assertThat(carts.total(id))
                        .isEqualTo(200L);
            }
        } finally {
            pool.shutdownNow();
            assertThat(
                    pool.awaitTermination(5, TimeUnit.SECONDS)
            ).isTrue();
        }
    }
}
~~~

These two tests **do not start Spring**, and have no mocks/shared contexts. `CartRegistry` is created **locally in each method**. The first test uses `CountDownLatch` to force eight workers to reach the starting line together rather than using `Thread.sleep` and "hoping" they contend. `Future.get(timeout)` ensures workers finish before assertions.

If you replace `ConcurrentHashMap.compute` with:

~~~java
// COUNTER-EXAMPLE: non-atomic read-modify-write.
long old = totals.getOrDefault(cartId, 0L);
totals.put(cartId, old + cents);
~~~

the concurrency test can expose lost increments. Note that concurrency tests are **not a formal proof** of every possible thread interleaving; they provide valuable regression coverage. For more critical mutations, stress/linearizability testing and verification on production-like systems are needed.

## 19. JUnit @ResourceLock for a Static Mutable Resource

Sometimes legacy tests must still read/write a shared static cache that cannot be refactored immediately. JUnit's `@ResourceLock` allows serializing tests that share the same **lock key**.

**`src/test/java/com/example/isolation/StaticScratchLockTest.java`:**

~~~java
package com.example.isolation;

import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

import static org.assertj.core.api.Assertions.assertThat;

@Execution(ExecutionMode.CONCURRENT)
class StaticScratchLockTest {

    private static final Map<String, Integer> SCRATCH =
            new HashMap<>();

    @Test
    @ResourceLock(
            value = "legacy-static-scratch",
            mode = ResourceAccessMode.READ_WRITE
    )
    void firstWriterUsesJunitResourceLock() {
        SCRATCH.clear();
        SCRATCH.put("count", 1);
        assertThat(SCRATCH.get("count")).isEqualTo(1);
    }

    @Test
    @ResourceLock(
            value = "legacy-static-scratch",
            mode = ResourceAccessMode.READ_WRITE
    )
    void secondWriterUsesTheSameJunitResourceLock() {
        SCRATCH.clear();
        SCRATCH.put("count", 2);
        assertThat(SCRATCH.get("count")).isEqualTo(2);
    }
}
~~~

Both tests declare the same lock key and `WRITE` mode. Within the same JUnit Jupiter execution plan, the scheduler will not execute their locked lifecycle scopes simultaneously.

**This is a mitigation for legacy state, not a default architecture.** If a test in another class accesses `SCRATCH` without `@ResourceLock("legacy-static-scratch")`, the lock offers no protection. If two independent Gradle test JVMs modify the same file/Redis, JUnit locks do not coordinate across processes either. Refactoring to per-test fixtures/namespaces remains preferable.

## 20. @TestInstance(PER_CLASS) and @TestMethodOrder Are Not Isolation

JUnit Jupiter defaults to `@TestInstance(PER_METHOD)`: each test method gets a new test instance. If you use:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@Execution(ExecutionMode.CONCURRENT)
class UnsafeSharedFixtureTest {
    private int total;

    @Test
    void one() {
        total++;
    }

    @Test
    void two() {
        total++;
    }
}
~~~

This is a **counter-example**, not included in the runnable project. Both methods can update the same `total` and race. With `PER_CLASS`, JUnit usually applies more conservative default execution mode rules unless `@Execution(CONCURRENT)` is present, but do not rely on that as synchronization for external state.

Likewise, `@TestMethodOrder` specifies order in certain cases; it **does not guarantee test independence**. Test B depending on "A must run first and set singleton state" is a brittle design. Instead, have every test set up all the data it needs.

A test method can use `@BeforeEach` to create local fixtures **even in a `PER_CLASS` test class**, though shared test fields still require synchronization; do not trade away clarity without a concrete benefit.

## 21. @DirtiesContext: Use Only When the Context Truly Needs Replacement

`@DirtiesContext` forces Spring to evict the context from the cache and close it according to the declared mode. For example:

~~~java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD
)
@SpringBootTest
class ExpensiveIsolatedIntegrationTest {
    // Each test method dirties the context and reloads it.
}
~~~

This is an illustrative snippet, not part of the runnable project. It can help when a test truly alters **bean definitions/configuration/context-managed lifecycles** that cannot be cleaned up; however, the downsides are:

- Reloading the context is slow and increases CI CPU/RAM usage.
- Another test may be using the cached context and find it unexpectedly closed.
- Does not roll back/reset external databases/brokers/Redis outside the context.
- Does not clear static fields outside Spring.
- **Spring Framework recommends against running tests with `@DirtiesContext` in parallel**.

If the issue is simply a key in `CartRegistry`, `carts.remove(myCartId)` is much clearer and cheaper. If the issue is a shared mock, `@DirtiesContext` is no substitute for isolating execution schedules/configurations; Spring test mocks already have a reset lifecycle.

## 22. Mock Reset and Async Background Tasks

This is a tricky failure case:

~~~text
Test method:
   stub shared @MockitoBean
   submit async worker
   return immediately

Spring teardown:
   reset @MockitoBean

Async worker:
   calls mock after reset
   -> sees default Mockito response
   -> writes wrong state / throws exception
~~~

If a test involves `@Async`, a Kafka consumer, scheduled task, web request, or `CompletableFuture`, **await business completion** before verifying/resetting/cleaning up. Use:

- `CompletableFuture.get(timeout)` for tasks attached to a Future.
- Awaitility `untilAsserted` for committed DB state.
- `CountDownLatch.await(timeout)` when an explicit signal at an exact point is required.
- Shutdown/cancel executors **created by the test itself** inside `finally`.
- Never shut down a Spring-managed shared executor in every test method.

If you cannot control the lifecycle of background threads, prefer a **dedicated fake collaborator** or serialized integration test instead of a shared `@MockitoBean`. Automatic mock reset **does not wait for asynchronous tasks**.

Mockito `verify(mock, timeout(...))` only proves the invocation occurred, not that the database commit or worker side effects completed. When the contract is business state, await that state.

## 23. AOP Proxies and @MockitoBean: Replacing a Bean Can Alter Behavior Too

An easily overlooked detail in Spring: a real service may be wrapped in an AOP proxy providing `@Transactional`, `@Cacheable`, method security, or `@Retryable`. When `@MockitoBean` **replaces the bean**, the override instance is a mock, not the **real AOP-proxied bean**; verifying interactions with the mock **does not** prove annotation-driven behavior of the original service ran.

Test example:

~~~java
@MockitoBean
PaymentService paymentService;

// Mockito verify(paymentService).charge(...)
// DOES NOT prove @Transactional on the real PaymentService ran.
~~~

This is a snippet, and `PaymentService` is an example name. If the goal is testing transaction/retry/cache behavior, **do not mock the component owning that annotation**. Use the real service and mock a downstream **external gateway**, or write an integration test against a real database/client stub.

`@MockitoSpyBean` is another option, though spy methods can invoke real code, require `doReturn(...).when(spy)...` when stubbing has side effects, and require understanding Spring AOP proxy targets. Do not treat a spy as a universal fix—it is still an override in the test context and should not run in parallel uncontrollably.

## 24. When a Singleton Holds State, Avoid Global Clear

A race-prone pattern:

~~~java
@BeforeEach
void reset() {
    cache.clear(); // Wipes the entire cache used by other tests!
}
~~~

In a parallel suite, Test A might be using cache key `A` while Test B calls `clear()` and erases the data. With independent test namespaces, prefer:

~~~java
@BeforeEach
void setup() {
    cartId = "test-" + UUID.randomUUID();
}

@AfterEach
void cleanup() {
    carts.remove(cartId);
}
~~~

These two snippets illustrate the concept implemented in the complete integration tests above. If a test creates multiple keys, track the owned keys and delete **only those keys**. Never delete another test's resources. For DBs, use a unique schema/container per test class or tenant/transaction ID; for Kafka, use dedicated topics/groups/consumer IDs.

**Insufficient when external operations haven't finished:** if a background worker is still running, it can re-insert rows after cleanup. Await/cancel tasks first, then clean up.

## 25. With a Database, @Transactional in Tests Does Not Roll Back All Threads

Spring `@Transactional` on a JUnit test method creates a **test-managed transaction** bound to the test thread. A request through an embedded HTTP server, `@Async` worker, scheduler, or Kafka consumer can run on a **different thread/transaction** and commit independently to the DB.

Example test with `@Transactional`:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class IncorrectAssumptionTest {
    // Test-thread rollback does not automatically roll back
    // DB writes made by the HTTP server thread.
}
~~~

This is an illustrative snippet, not part of the runnable project. If the method calls an HTTP endpoint and the server writes to the DB, test rollback may fail to remove data committed on the server thread. When tests run in parallel, data can leak into other methods/classes.

Solutions:

1. Generate unique business IDs per method.
2. Query/await committed state with proper transaction/isolation.
3. Clean up explicitly after background processing finishes.
4. When using Testcontainers, isolate schemas/containers at the needed level.
5. Never rely on test-thread rollback to clean up external resources.

`@Sql` and `@DirtiesContext` also do not clean up Kafka topics, object storage, or HTTP providers. Every resource needs its own ownership/lifecycle plan.

## 26. Context Cache Keys and @MockitoBean Field Names

Spring Framework 6.2 allows `@MockitoBean` to resolve beans by **field type** and use `@Qualifier`/field name to disambiguate when needed. The field name can act as a **fallback qualifier** and affect the context cache key.

For example, two test classes both mock `PricingClient`, but one names the field `pricingClient` and the other `service`:

~~~java
@MockitoBean
PricingClient pricingClient;
~~~

~~~java
@MockitoBean
PricingClient service;
~~~

These are two snippets, not part of a complete demo. Depending on context/qualifiers, Spring may create **two unnecessary context cache entries**. If both tests genuinely share the same override configuration, use consistent field names or declare an explicit qualifier/name.

The converse must also be remembered: **reusing a context does not mean separate mock instances** per class. Sharing a context means Test A and B can share the same mock even though each class declares its own field.

If multiple bean candidates share the same type, `@MockitoBean` can fail due to an ambiguous target. Do not slap `@Primary` randomly to hide the error; use `@Qualifier` or `@MockitoBean(name="...")`, and `enforceOverride=true` to catch missing targets.

## 27. @ResourceLock and @Isolated Do Not Solve CI Shards

In a Gradle `test` task, `maxParallelForks=1` limits concurrent **Gradle forked test JVMs**. However, JUnit Jupiter can still run multiple tests concurrently **within one JVM** per `junit-platform.properties`. Increasing `maxParallelForks` to 4 spawns more JVMs, each with its own context cache; tests sharing an external PostgreSQL schema or Kafka topic can still collide.

Similarly, CI can split jobs across multiple shards/machines. JUnit's `@ResourceLock` and `@Isolated` coordinate **only within the same engine execution plan**. They are not distributed locks and cannot replace:

- Unique DB/schema/tenant IDs.
- Separate Kafka topic/group names per test run.
- Filesystem temp dirs managed by `@TempDir`.
- Random network ports with clear lifecycle owners.
- Separate Redis key prefixes per CI job/test invocation.
- Per-test-run namespaces instead of global truncates.
- Cleanup guaranteed not to touch resources used by other tests.

**Pick the right isolation level:** method-local for unit tests, keyed shared singletons for Spring integration, per-class containers/schemas when required, and per-job external namespaces for CI shards.

## 28. A Matrix for Choosing a Strategy

| Test scenario | Parallel-safe? | Strategy |
| --- | --- | --- |
| Pure unit test with per-method mocks and store | Yes | `@Mock` + `MockitoExtension`, local fixtures |
| **Stateless** Spring service singleton | Usually yes | Do not mutate global mutable state |
| Spring singleton with `ConcurrentHashMap` by unique ID | Yes if contract is clear | Per-test key, atomic updates, scoped cleanup |
| `@MockitoBean` in a cached context | **Not recommended** | `@Isolated`/serialized test group |
| `@MockitoSpyBean` on a stateful service | **Not recommended** | Serial + understand real method/AOP behavior |
| `@DirtiesContext` between test methods | Not recommended | Run separately, use only when truly needed |
| Legacy shared `static HashMap` | Only with proper lock coordination | `@ResourceLock` or refactor |
| Shared DB table, tests truncate whole table | No | Unique data/schema or serial grouping |
| H2 sharing a fixed DB URL | Conditionally | Unique IDs, proper DB transactions/cleanup |
| Shared embedded Kafka topic/group | Risky | Unique topics/groups; lifecycle isolation |
| Spring `@Async` worker accessing mock after test | Not without joining | Await completion before mock reset |
| Tests mutating `System.setProperty`/default locale | Unsafe without locking | `@ResourceLock`/isolate or avoid global mutation |

**More `@DirtiesContext` or `@Isolated` does not make tests better.** The objective is running **truly independent** tests in parallel while locking or isolating the few tests that rely on unavoidable global resources.

## 29. Diagnosing Flakiness

| Symptom | Common Cause | Evidence to Collect |
| --- | --- | --- |
| PASS alone, FAIL in full suite | Singleton/static/database state leak | IDs, context reuse, teardown logs |
| Mockito `Wanted but not invoked` after concurrent test | Another test reset/stubbed the same mock | Mock identity, test schedule, after lifecycle |
| Mockito `TooManyActualInvocations` | Another test shared the mock, or background task unfinished | Interaction history, owner ID |
| Test A's stubbing vanishes | Test B triggered Spring `MockReset.AFTER` | Mock/context sharing, concurrency |
| Total alternates between 2 and 1 | `count++` / non-atomic HashMap | Concurrent stress/latch |
| Test A's cart vanishes during Test B setup | Global `clear()` in `@BeforeEach` | Cleanup scope |
| Bean state persists after `@BeforeEach` | `@BeforeEach` does not reset Spring singletons | Context cache and bean identity |
| `@DirtiesContext` causes "context no longer active" | Context closed while another test uses it | Parallel Spring docs, cache eviction |
| `@Transactional` test still leaves DB rows | Server/async thread used another transaction | DB commit thread/connection |
| `@MockitoBean` mock persists in another class | Context cache reused | Context cache key & bean override config |
| Mockito test doesn't touch `@Autowired` service's bean | Used `@Mock` instead of `@MockitoBean` | DI wiring, mock identity |
| Spy stubbing runs real code unexpectedly | `when(spy.method())` executes the method | Use `doReturn` on spies when appropriate |
| Parallel tests all write to `./tmp/output.json` | Shared filesystem path | `@TempDir`, per-test directory |
| Tests share Kafka group/topic | Shared offsets and records | Unique groups/topics |
| Bean reset then async callback re-mutates | Worker unfinished | Await worker, cleanup ordering |
| Tests run faster but unreliably | Parallel enabled on unisolated suite | Classify/serialize risky tests |
| Disabling all parallelism "fixes it" | Race masked while state leak remains | Run sequentially in multiple random orders |
| `@TestInstance(PER_CLASS)` adds shared field | One mutable test instance | Per-method lifecycle/local state |
| Different field names create extra contexts | `@MockitoBean` fallback qualifier affects cache key | Standardize field naming |
| Context cache thrashing, slow CI | Too many unique overrides/dirty contexts | Cache stats, group configs |

To debug the context cache, Spring TestContext supports logging under `org.springframework.test.context.cache` at DEBUG level. Do not assert exact context counts across all Gradle versions; measure to spot abnormal cache misses or evictions.

## 30. Review Checklist Before Enabling Parallel Execution

- [ ] Have all singleton beans with mutable fields/caches been identified?
- [ ] Have **stateless** singletons been distinguished from mutable state needing thread safety?
- [ ] Do any `static` fields or `PER_CLASS` shared test instances mutate?
- [ ] Does every test using shared storage have a unique ID/namespace?
- [ ] Does cleanup delete only resources owned by that test?
- [ ] Are there no `clearAll()/TRUNCATE` calls affecting other tests?
- [ ] Do all background workers complete before teardown/reset?
- [ ] Are `@MockitoBean` tests serialized or isolated from parallel runs?
- [ ] Is manual `Mockito.reset` avoided on mocks shared across tests?
- [ ] Is default `AFTER` mock reset understood as resetting stubs/interactions, **not creating a new bean**?
- [ ] For pure services, are `@Mock` + dedicated fixtures used instead of `@SpringBootTest`?
- [ ] For Spring wiring, is the right bean mocked via `@MockitoBean`/qualifier?
- [ ] Is `enforceOverride=true` checked when asserting a real target bean exists?
- [ ] Are `@MockitoBean` field names/qualifiers consistent when context reuse is intended?
- [ ] Are real services tested when verifying `@Transactional`/`@Retryable`/`@Cacheable`?
- [ ] Is `@DirtiesContext` used only when necessary and kept out of parallel runs?
- [ ] Are `@ResourceLock` keys declared by **every test sharing that resource**?
- [ ] Is `@Isolated` not mistaken for a distributed lock?
- [ ] Do Gradle forks/CI shards avoid sharing unnamespaced resources?
- [ ] Does database rollback scope cover background threads or are they handled separately?
- [ ] Are Spring test context caching and H2 URL/Redis/Kafka namespaces understood?
- [ ] Do concurrency tests use latches and bounded timeouts rather than speculative `Thread.sleep`?
- [ ] Does Mockito verification check invocations while business invariants are asserted separately?
- [ ] Has the suite been executed multiple times/orders before enabling broad parallelism?
- [ ] Are expected results clearly distinguished from actually executed builds/JUnit runs?

## 31. Run Commands and Expected Outcomes

Given JDK 17+, a Gradle Wrapper, and dependencies:

~~~bash
./gradlew test --tests "com.example.isolation.CheckoutPureUnitTest"
./gradlew test --tests "com.example.isolation.CheckoutSpringMockTest"
./gradlew test --tests "com.example.isolation.CheckoutSpringParallelTest"
./gradlew test --tests "com.example.isolation.CartRegistryConcurrencyTest"
./gradlew test --tests "com.example.isolation.StaticScratchLockTest"
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.isolation.CheckoutPureUnitTest"
.\gradlew.bat test --tests "com.example.isolation.CheckoutSpringMockTest"
.\gradlew.bat test --tests "com.example.isolation.CheckoutSpringParallelTest"
.\gradlew.bat test --tests "com.example.isolation.CartRegistryConcurrencyTest"
.\gradlew.bat test --tests "com.example.isolation.StaticScratchLockTest"
.\gradlew.bat test
~~~

**13 JUnit methods**: 3 pure unit; 3 Spring `@MockitoBean` isolated; 3 Spring parallel state-by-ID; 2 `CartRegistry` concurrency; 2 static scratch `@ResourceLock`.

| Group | Expected |
| --- | --- |
| Pure unit Mockito | Separate stubs per test, totals 100/350, invalid price remains 0 |
| Spring mock bean | `@MockitoBean` replaces `PricingClient` accurately; totals 350/700, invalid remains 0 |
| Spring parallel real beans | Pen 200, book 500, two cart IDs never interfere |
| 8 worker tasks on one cart | 8 × 50 additions × 1 cent = **400 cents** |
| 4 worker tasks on four carts | Each cart 100 additions × 2 cents = **200 cents** |
| Static legacy lock | Both methods share `ResourceLock` key, expected 1/2 inside their respective methods |

These are **outcomes inferred from the source**, not observed Gradle/JUnit output. The sample code **was not compiled/run during authoring**, so it must be executed in a complete project with a Gradle Wrapper to confirm real results. There is no `System.out.println` in the application code, so there is no fixed stdout.

**Conclusion:** Do not blame every flaky test on "running in parallel too fast". Inspect **mutable state ownership**: a new test instance does not mean a new Spring singleton; mocks inside a cached context can be shared across tests, and `AFTER` reset does not make concurrent mocking safe. Use per-method mocks for unit tests, stateless singletons or atomic keyed state + scoped cleanup for parallel Spring tests, and serialize tests that use `@MockitoBean`/`@DirtiesContext` or inseparable global resources. Check data races, state leaks, and background task lifecycles before trusting any parallel test suite.

### Official Documentation

- [Spring Framework 6.2 — TestContext Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html)
- [Spring Framework 6.2 — @MockitoBean / @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Framework 6.2 — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html)
- [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework 6.2 — Dependency Injection for Test Fixtures](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/fixture-di.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — @MockBean Deprecated API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/mock/mockito/MockBean.html)
- [JUnit Jupiter 5.12 — Parallel Execution, @ResourceLock, @Isolated](https://docs.junit.org/5.12.0/user-guide/#writing-tests-parallel-execution)
- [JUnit Jupiter 5.12 — Test Instance Lifecycle](https://docs.junit.org/5.12.0/user-guide/#writing-tests-test-instance-lifecycle)
- [Mockito — MockitoExtension Javadoc](https://javadoc.io/doc/org.mockito/mockito-junit-jupiter/latest/org/mockito/junit/jupiter/MockitoExtension.html)
- [Java SE 17 — ConcurrentHashMap.compute](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)