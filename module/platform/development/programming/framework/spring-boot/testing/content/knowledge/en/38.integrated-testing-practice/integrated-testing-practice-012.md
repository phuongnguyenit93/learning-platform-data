# Running the Test Suite in CI and Investigating a Parallel-Only Failure

## 1. Integrated Practice Objective

In the **Spring Boot - testing** module under **Integrated Practice**, this lesson simulates a real incident: unit tests and Spring Boot integration tests PASS when run sequentially on a developer's machine; after CI enables parallel JUnit execution, a shopping-cart check unexpectedly reads another customer's value. Re-running the failing test in isolation usually PASSES. The goal is to **gather evidence, reproduce the race in a controlled way, fix the business root cause, and re-verify in CI**, rather than raising timeouts or turning off all parallelism.

~~~text
Dev: ./gradlew test                         -> PASS
Dev: ./gradlew integrationTest (serial)     -> usually PASS
CI:  ./gradlew integrationTest (parallel)   -> intermittently FAIL
                       |
                       v
   Two JUnit methods / request workers share the same
   Spring @Singleton bean holding mutable currentCustomer
                       |
                       v
   A writes "alpha" -> B writes "beta" -> A reads "beta"
                       |
                       v
   Root cause: per-request identity stored in a shared field
~~~

**Separate evidence from hypothesis:** CI-only does not automatically mean data race. A runner-only failure can also stem from Docker, timezone, file path, network quota, order-dependent tests, PostgreSQL transactions, clock drift, test filters, or JVM configuration. You must run single-variable experiments with sufficient logs and artifacts to tell them apart.

This lesson uses **Java 17, Spring Boot 3.5.16, Gradle 8.14.x, JUnit Jupiter, Mockito, and AssertJ**, splitting fast `test` from `integrationTest` backed by a real Spring context. There are exactly **5 test classes and 10 JUnit test methods**: 4 unit and 6 integration. One test intentionally uses `CountDownLatch` to **prove the bug** in the broken singleton: it PASSES when observing the defect, which must never be misread as the broken service being safe. The remaining tests verify the fix using a **stateless singleton + ID-partitioned state + atomic per-key operations**.

Expected outcomes stated here are **derived from the code**, not Gradle/JUnit logs observed at authoring time.

## 2. Distinguishing Four Levels of Parallel Execution

| Level | Configuration | Shared Resources |
| --- | --- | --- |
| Gradle task parallelism | `./gradlew --parallel` | Tasks/subprojects may run concurrently |
| Gradle forked test JVMs | `Test.maxParallelForks=2` | Each fork has its own JVM/static/Spring cache; external DB may still be shared |
| JUnit Jupiter threads in one JVM | `junit.jupiter.execution.parallel.enabled=true` | Tests can share the Spring `ApplicationContext` and singletons |
| Multi-runner CI matrix/shards | Multiple jobs/nodes | Separate JVMs; DB/topic/bucket/Redis key prefixes may collide |
| Application workers | `@Async`, HTTP servlet, Kafka listener | Not governed by Jupiter scheduling; can still be concurrent when JUnit is serial |

**`maxParallelForks=1` does not disable JUnit parallelism.** It only caps the number of forked JVMs for a `Test` task. Inside a single fork, Jupiter can still use four threads according to `junit-platform.properties`. Conversely, `junit.jupiter.execution.parallel.enabled=false` does not stop servlet workers or executors spawned by tests.

Because the race in this lesson requires sharing **the same Spring singleton**, the sample config keeps `maxParallelForks=1` so JUnit tests hit the same `ApplicationContext` cache. Raising forks might hide the symptom by spreading test classes across separate JVMs without making production code any safer.

## 3. Evidence Collection Checklist When CI Turns Red

Record before rerunning:

1. Commit SHA, CI job/run, Gradle Wrapper version, Java runtime, and OS.
2. Whether the task was `test` or `integrationTest`; test class/method name, assertion failure, and original stack trace.
3. JUnit parallel properties/`@Execution`, Gradle forks, and CI shard identifier.
4. Spring active profiles, context config/cache, bean identity, and bean overrides.
5. Data owner key, file path, schema, topic, queue, and container IDs if applicable.
6. `@BeforeEach`/`@AfterEach`, relative timestamps, and still-running background work.
7. JUnit XML/HTML from the failing task plus thread/owner-key logs.
8. Recent changes to mock resets, `@DirtiesContext`, cleanup, Gradle dependencies, or CI runners.

A test that PASSES on rerun is only **a sign of a flaky/hard-to-reproduce failure**, not proof of a fix. Archive the first failure's artifacts before running controlled experiments.

## 4. Spring TestContext Cache and Singletons

JUnit defaults to `@TestInstance(PER_METHOD)`: each test method gets its own test class instance. This **does not create separate Spring beans**. When two `@SpringBootTest` classes share the same context configuration, Spring TestContext can cache and reuse one `ApplicationContext` within the same JVM:

~~~text
JUnit test A instance ──┐
                        ├─ cached ApplicationContext
JUnit test B instance ──┘       |
                                +-- CheckoutService @Service singleton
                                +-- CartBalances @Component singleton
                                +-- UnsafeUserSession @Component singleton
                                              |
                                              +-- volatile currentCustomer
~~~

If test A runs `session.enter("alpha")` and then test B calls `enter("beta")`, A can read back `"beta"`. `volatile` guarantees write visibility, not a per-request copy of the field. `AtomicReference` does not fix it either because it is still **one shared slot**. Having `@BeforeEach` call `clear()` on the singleton can even wipe state actively used by another test.

These are two distinct concerns:
- **Thread safety:** two threads adding to the same key do not lose updates.
- **Isolation:** two tests use unique keys and clean up only their own data.

A `ConcurrentHashMap` with thread-safe operations still suffers cross-test leaks if every test uses the same `"test"` key. You must solve both.

## 5. Symptoms That Distinguish Root Causes

| Symptom | Suspect | How to Verify |
| --- | --- | --- |
| FAILS when Jupiter is concurrent, PASSES serially | Bean/static/mock/shared resource race | Log owner + thread; use latches to build interleaving |
| FAILS serially depending on prior test | State leak or missing cleanup | Run test pairs in reversed orders |
| Mockito too-many-invocations | Same mock shared across tests | Compare context/mock identity and reset lifecycle |
| ApplicationContext no longer active | `@DirtiesContext`, cache eviction | Spring TestContext cache logs |
| DB rows remain despite `@Transactional` test | HTTP/async thread uses another transaction | Verify commits and owner cleanup |
| Random rows appear across CI shards | Shared external schema/topic | Namespace by run/shard |
| Fails only on CI lacking Docker | Testcontainers failed to start | Check container engine, logs, readiness |
| Fails in one timezone only | Clock/DST/locale | Inject `Clock` or set explicit test clock |
| Local PASS, small runner timeout | CPU/RAM/network bottleneck | Check time budgets and CI resource usage |
| `NO-SOURCE`/0 tests | Wrong source set or test task | Check XML counts, `testClassesDirs`, runtime classpath |

Do not "fix" failures with `Thread.sleep`: it shifts scheduling probabilities without establishing a synchronization contract.

## 6. Lab Architecture and Exact Test Count

~~~text
Anti-pattern to diagnose:
  UnsafeUserSession @Component
      volatile currentCustomer
      enter(String); currentCustomer()
  RacySessionInvestigationTest
      A enter alpha -> B enter beta -> A read beta
      -> test PASSES because it proves the bug reproduces

Fix:
  CheckoutService @Service (no customer field)
      addItem(customerId,sku)
        -> DefaultPriceGateway (stateless)
        -> CartBalances @Component
              ConcurrentHashMap<customerId,total>
              atomic per-key compute()
  Test fixtures: unique UUID customerId per method
  Cleanup: remove(only this test's ID)
~~~

| Task | Class | `@Test` methods |
| --- | --- | ---: |
| `test` | `CheckoutServiceUnitTest` | 2 |
| `test` | `CartBalancesConcurrencyTest` | 2 |
| `integrationTest` | `RacySessionInvestigationTest` | 1 |
| `integrationTest` | `SafeCheckoutParallelTest` | 3 |
| `integrationTest` | `SafeCheckoutOtherClassTest` | 2 |
| **Total** | **5 test classes** | **10 methods** |

**There is no intentionally FAILING test in the default suite.** The red assertion for demonstrating the defect before the fix appears in a separate explanatory snippet, not a runnable file, so the default pipeline can stay green when the diagnostic test works as intended.

## 7. File Structure

~~~text
settings.gradle
build.gradle
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.properties

src/main/java/com/example/parallellab/
  ParallelCiApplication.java
  PriceGateway.java
  DefaultPriceGateway.java
  CartBalances.java
  CheckoutService.java
  UnsafeUserSession.java
src/main/resources/application.properties

src/test/java/com/example/parallellab/
  CheckoutServiceUnitTest.java
  CartBalancesConcurrencyTest.java

src/integrationTest/java/com/example/parallellab/
  RacySessionInvestigationTest.java
  SafeCheckoutParallelTest.java
  SafeCheckoutOtherClassTest.java
src/integrationTest/resources/
  junit-platform.properties
  application-it.properties

.github/workflows/java-test-ci.yml
~~~

Integration tests use a separate source set so the unit task does not start Spring. Both tasks produce independent JUnit XML and HTML reports. All Java and Gradle sources are written completely with files, packages, and imports so you can assemble the sample project; wrapper scripts/JARs are generated by Gradle Wrapper rather than embedding binaries in the README.

## 8. Gradle Build: Two Tasks and One JUnit Parallel Switch

**`settings.gradle`:**

~~~groovy
rootProject.name = 'spring-parallel-ci-lab'
~~~

**`build.gradle`:**

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

sourceSets {
    integrationTest {
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}

configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    testLogging {
        events 'failed', 'skipped'
        exceptionFormat 'full'
    }
}

tasks.register('integrationTest', Test) {
    description = 'Spring integration and concurrency tests'
    group = 'verification'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()

    maxParallelForks = 1
    shouldRunAfter(tasks.named('test'))

    systemProperty 'junit.jupiter.execution.parallel.enabled',
        (project.findProperty('itParallel') ?: 'true').toString()

    testLogging {
        events 'failed', 'skipped'
        exceptionFormat 'full'
        showStandardStreams = true
    }

    reports {
        junitXml.required = true
        html.required = true
    }
}

tasks.named('check') {
    dependsOn(tasks.named('integrationTest'))
}
~~~

**Wiring explanation:**
- The `integrationTest` source set gets its own compile and resource tasks from the Java plugin.
- `integrationTestImplementation` inherits **libraries** from `testImplementation`, without mixing in `src/test/java` compiled classes.
- `testClassesDirs` and `classpath` must point explicitly to the integration source set rather than relying on the built-in `test` task convention.
- `useJUnitPlatform()` enables JUnit Jupiter test discovery.
- `maxParallelForks=1` keeps one test JVM; Jupiter threads can still run concurrently.
- `project.findProperty('itParallel')` reads `-PitParallel=true|false` and forwards the system property **into the forked test JVM**, not only the Gradle daemon.
- `shouldRunAfter(test)` is only an ordering rule; `check.dependsOn(integrationTest)` hooks the integration task into the verification lifecycle.
- `reports` stores separate JUnit XML/HTML outputs per task.

### Gradle Wrapper and Java

~~~bash
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
./gradlew --version
~~~

PowerShell:

~~~powershell
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
.\gradlew.bat --version
~~~

Spring Boot 3.5.16 documents support for Gradle 7.6.4+ in the 7.x line or 8.4+ in the 8.x line, with Java 17+. Here we choose Gradle 8.14.3 and use the **Wrapper** for both local and CI runs; do not upgrade Boot 3.5 to Gradle 9 on your own and assume it is supported.

## 9. JUnit Properties Only for `integrationTest`

**`src/integrationTest/resources/junit-platform.properties`:**

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
~~~

In JUnit Jupiter, enabling `parallel.enabled` is the first step; `mode.default`/`mode.classes.default` decide which classes and methods can run concurrently. This lesson picks fixed parallelism of 4 for predictable measurement and observation.

Because the `Test` task sets the `junit.jupiter.execution.parallel.enabled` system property, `-PitParallel=false` **overrides the file setting** in the forked JVM. Two experiments:

~~~bash
./gradlew integrationTest -PitParallel=false --rerun-tasks
./gradlew integrationTest -PitParallel=true --rerun-tasks
~~~

Note: the race diagnostic test also **spawns its own threads via `ExecutorService`** inside a `@Test`; it still forces interleaving even when Jupiter scheduling is sequential. The toggle controls **JUnit test node scheduling**, not a magic switch that disables all business concurrency.

## 10. Application + Test Profile

**`src/main/java/com/example/parallellab/ParallelCiApplication.java`:**

~~~java
package com.example.parallellab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ParallelCiApplication {
    public static void main(String[] args) {
        SpringApplication.run(ParallelCiApplication.class, args);
    }
}
~~~

**`src/main/resources/application.properties`:**

~~~properties
spring.main.banner-mode=off
logging.level.com.example.parallellab=INFO
~~~

**`src/integrationTest/resources/application-it.properties`:**

~~~properties
lab.integration-mode=true
~~~

Spring integration tests use `@ActiveProfiles("it")`. The `lab.integration-mode` property confirms that `integrationTest` resources are on the runtime classpath; it is not a business feature flag. Never place production secrets in test profiles.

## 11. `PriceGateway` and Stateless Implementation

**`src/main/java/com/example/parallellab/PriceGateway.java`:**

~~~java
package com.example.parallellab;

public interface PriceGateway {
    long unitPriceCents(String sku);
}
~~~

**`src/main/java/com/example/parallellab/DefaultPriceGateway.java`:**

~~~java
package com.example.parallellab;

import org.springframework.stereotype.Component;

@Component
public class DefaultPriceGateway implements PriceGateway {

    @Override
    public long unitPriceCents(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank"
            );
        }

        return switch (sku) {
            case "pen" -> 100L;
            case "book" -> 400L;
            default -> throw new IllegalArgumentException(
                    "Unknown sku: " + sku
            );
        };
    }
}
~~~

This bean is stateless—it remembers neither customer names nor prior calls. Integration tests use the real gateway; unit tests create private Mockito mocks instead of sharing `@MockitoBean` inside a cached Spring context.

## 12. `CartBalances`: Per-`customerId` State and Atomic `compute`

**`src/main/java/com/example/parallellab/CartBalances.java`:**

~~~java
package com.example.parallellab;

import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Component;

@Component
public class CartBalances {

    private final ConcurrentMap<String, Long> totals =
            new ConcurrentHashMap<>();

    public long add(String customerId, long cents) {
        if (customerId == null || customerId.isBlank()
                || cents <= 0) {
            throw new IllegalArgumentException(
                    "invalid customer or amount"
            );
        }

        return totals.compute(
                customerId,
                (key, oldValue) -> Math.addExact(
                        oldValue == null ? 0L : oldValue,
                        cents
                )
        );
    }

    public long total(String customerId) {
        Objects.requireNonNull(customerId);
        return totals.getOrDefault(customerId, 0L);
    }

    public void remove(String customerId) {
        Objects.requireNonNull(customerId);
        totals.remove(customerId);
    }
}
~~~

`ConcurrentHashMap.compute` performs atomic remapping per key, preventing lost updates when two threads add to the same cart concurrently. Still, it is **not a distributed data store** and does not prevent test A from deleting test B's key by mistake. Every test must use a unique owner key and clean up only its own data.

For a shared key: 6 workers × 50 adds of 1 cent must equal **300 cents**. For two keys A/B: A can be removed while B stays intact. Both invariants are explicitly verified by the unit tests below.

## 13. `CheckoutService`: Fixing Request State Architecturally

**`src/main/java/com/example/parallellab/CheckoutService.java`:**

~~~java
package com.example.parallellab;

import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PriceGateway prices;
    private final CartBalances balances;

    public CheckoutService(
            PriceGateway prices,
            CartBalances balances
    ) {
        this.prices = Objects.requireNonNull(prices);
        this.balances = Objects.requireNonNull(balances);
    }

    public long addItem(String customerId, String sku) {
        if (customerId == null || customerId.isBlank()
                || sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "invalid customer or sku"
            );
        }

        long cents = prices.unitPriceCents(sku);
        if (cents <= 0) {
            throw new IllegalArgumentException(
                    "price must be positive"
            );
        }
        return balances.add(customerId, cents);
    }

    public long total(String customerId) {
        return balances.total(customerId);
    }
}
~~~

This service can safely be a singleton because it holds only immutable references to its dependencies, with no `currentCustomer` or `currentCart` field. Identity is passed on every method call. Mutable state lives in a key-scoped store with atomic updates.

If real money were involved, you would need database transactions, a ledger, and idempotency protection for retried requests; this in-memory map teaches concurrency isolation, not a payment system replacement.

## 14. `UnsafeUserSession`: Buggy Class for Reproducing and Verifying

**`src/main/java/com/example/parallellab/UnsafeUserSession.java`:**

~~~java
package com.example.parallellab;

import org.springframework.stereotype.Component;

/** COUNTER-EXAMPLE: DO NOT USE FOR PRODUCTION REQUESTS. */
@Component
public class UnsafeUserSession {

    private volatile String currentCustomer;

    public void enter(String customerId) {
        currentCustomer = customerId;
    }

    public String currentCustomer() {
        return currentCustomer;
    }

    public void clear() {
        currentCustomer = null;
    }
}
~~~

With this singleton, calls to `enter` and `currentCustomer` **do not form a transaction**. `volatile` only makes B's write visible to A; it does not preserve A's own identity. Even `AtomicReference<String>` or synchronizing each method individually cannot save the `enter(A) → enter(B) → read(A)` sequence.

Why keep this class in the learning project? To demonstrate how a diagnostic test can **deterministically reproduce the defect** by coordinating threads rather than waiting for CI to fail intermittently. The fixed `CheckoutService` **does not use this class**.

## 15. Unit Tests Using `MockitoExtension`

**`src/test/java/com/example/parallellab/CheckoutServiceUnitTest.java`:**

~~~java
package com.example.parallellab;

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
class CheckoutServiceUnitTest {

    @Mock PriceGateway prices;

    private CheckoutService checkout;
    private CartBalances balances;
    private String customerId;

    @BeforeEach
    void setup() {
        balances = new CartBalances();
        checkout = new CheckoutService(prices, balances);
        customerId = "unit-" + UUID.randomUUID();
    }

    @Test
    void mockPriceAndStoreArePrivateToThisMethod() {
        when(prices.unitPriceCents("pen")).thenReturn(125L);

        assertThat(checkout.addItem(customerId, "pen"))
                .isEqualTo(125L);
        assertThat(checkout.total(customerId))
                .isEqualTo(125L);

        verify(prices).unitPriceCents("pen");
    }

    @Test
    void invalidPriceDoesNotMutateCart() {
        when(prices.unitPriceCents("pen")).thenReturn(0L);

        assertThatThrownBy(
                () -> checkout.addItem(customerId, "pen")
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessageContaining("price must be positive");

        assertThat(checkout.total(customerId)).isZero();
        verify(prices).unitPriceCents("pen");
    }
}
~~~

**Two unit methods.** `MockitoExtension` manages mock creation per test lifecycle, and `new CartBalances()` creates a private store. Because Spring does not boot, these tests never rely on a cached `ApplicationContext` or shared `@MockitoBean`. When a business service only needs pure behavior checks, prefer this style to keep CI fast.

## 16. Unit Tests for Thread Safety and Key Isolation

**`src/test/java/com/example/parallellab/CartBalancesConcurrencyTest.java`:**

~~~java
package com.example.parallellab;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CartBalancesConcurrencyTest {

    @Test
    void concurrentAddsToOneKeyAreAtomic()
            throws Exception {
        CartBalances balances = new CartBalances();
        ExecutorService pool = Executors.newFixedThreadPool(6);
        CountDownLatch ready = new CountDownLatch(6);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();
        String id = "stress-" + UUID.randomUUID();

        try {
            for (int worker = 0; worker < 6; worker++) {
                tasks.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "start timed out"
                        );
                    }
                    for (int i = 0; i < 50; i++) {
                        balances.add(id, 1L);
                    }
                    return null;
                }));
            }

            assertThat(ready.await(
                    5, TimeUnit.SECONDS
            )).isTrue();

            start.countDown();
            for (Future<?> task : tasks) {
                task.get(5, TimeUnit.SECONDS);
            }

            assertThat(balances.total(id))
                    .isEqualTo(300L);
        } finally {
            start.countDown();
            pool.shutdownNow();
            assertThat(pool.awaitTermination(
                    5, TimeUnit.SECONDS
            )).isTrue();
        }
    }

    @Test
    void removeOneKeyCannotDeleteTheOtherKey() {
        CartBalances balances = new CartBalances();
        String a = "a-" + UUID.randomUUID();
        String b = "b-" + UUID.randomUUID();

        balances.add(a, 100L);
        balances.add(b, 400L);
        balances.add(a, 50L);

        assertThat(balances.total(a)).isEqualTo(150L);
        assertThat(balances.total(b)).isEqualTo(400L);

        balances.remove(a);

        assertThat(balances.total(a)).isZero();
        assertThat(balances.total(b)).isEqualTo(400L);
    }
}
~~~

**Two unit methods.** Latches replace sleep-based guessing about thread scheduling; every worker reaches the ready gate and is released together. `Future.get(timeout)` propagates task exceptions and bounds wait time. The `finally` block releases the latch, shuts down the test-created pool, and awaits termination before returning. This test does not formally prove all possible interleavings, but it provides strong regression value.

## 17. Spring Integration Test: Deterministic Reproducer of the Buggy Class

**`src/integrationTest/java/com/example/parallellab/RacySessionInvestigationTest.java`:**

~~~java
package com.example.parallellab;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("it")
class RacySessionInvestigationTest {

    @Autowired UnsafeUserSession unsafe;
    @Autowired ApplicationContext context;

    @Test
    void forcedOverlapShowsAnotherCustomerInSingletonField()
            throws Exception {
        assertThat(context.getBean(UnsafeUserSession.class))
                .isSameAs(unsafe);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch alphaEntered = new CountDownLatch(1);
        CountDownLatch betaEntered = new CountDownLatch(1);

        try {
            Future<String> alpha = pool.submit(() -> {
                unsafe.enter("alpha");
                alphaEntered.countDown();
                if (!betaEntered.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "beta entry timed out"
                    );
                }
                return unsafe.currentCustomer();
            });

            Future<String> beta = pool.submit(() -> {
                if (!alphaEntered.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "alpha entry timed out"
                    );
                }
                unsafe.enter("beta");
                betaEntered.countDown();
                return unsafe.currentCustomer();
            });

            String observedByAlpha = alpha.get(
                    5, TimeUnit.SECONDS
            );
            String observedByBeta = beta.get(
                    5, TimeUnit.SECONDS
            );

            // PASSES when detecting the BUG in the intentionally broken class:
            assertThat(observedByAlpha).isEqualTo("beta");
            assertThat(observedByAlpha).isNotEqualTo("alpha");
            assertThat(observedByBeta).isEqualTo("beta");
        } finally {
            alphaEntered.countDown();
            betaEntered.countDown();
            pool.shutdownNow();
            assertThat(pool.awaitTermination(
                    5, TimeUnit.SECONDS
            )).isTrue();
            unsafe.clear();
        }
    }
}
~~~

**One integration method.** Latches force A to write before B, and A to read only after B writes. A observing `"beta"` proves the shared request-state defect. This test **PASSES when the bug reproduces**, because its purpose is diagnostic. Never mistake a passing diagnostic test for safe production code.

If you want a **red regression** prior to fixing, on an experimental branch temporarily flip A's assertion to:

~~~java
// SNIPPET, DO NOT place into the example's default suite:
assertThat(observedByAlpha).isEqualTo("alpha");
~~~

It will FAIL whenever forced interleaving hits the defect, reporting expected `alpha` / actual `beta`. Once you refactor the real service to drop mutable request fields, write regression tests against the **fixed service** verifying per-customer isolation instead of leaving a red assertion on an anti-pattern class.

**Toggle limitation:** `-PitParallel=false` does not stop the two worker threads spawned by this method. The reproducer still surfaces the bug; it tests code concurrency rather than measuring JUnit's scheduler.

## 18. Spring Integration Tests for the Fixed Version

**`src/integrationTest/java/com/example/parallellab/SafeCheckoutParallelTest.java`:**

~~~java
package com.example.parallellab;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInfo;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@Execution(ExecutionMode.CONCURRENT)
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("it")
class SafeCheckoutParallelTest {

    private static final Logger log =
            LoggerFactory.getLogger(SafeCheckoutParallelTest.class);

    @Autowired CheckoutService checkout;
    @Autowired CartBalances balances;
    @Autowired Environment environment;

    private String customerId;

    @BeforeEach
    void setupOwnId(TestInfo info) {
        customerId = "it-" + UUID.randomUUID();
        log.info("START method={} owner={} thread={}",
                info.getDisplayName(), customerId,
                Thread.currentThread().getName());
    }

    @AfterEach
    void cleanupOwnId() {
        balances.remove(customerId);
        log.info("END owner={} thread={}",
                customerId,
                Thread.currentThread().getName());
    }

    @Test
    void penPriceBelongsOnlyToOwnCart() {
        assertThat(environment.getProperty(
                "lab.integration-mode"
        )).isEqualTo("true");

        assertThat(checkout.addItem(customerId, "pen"))
                .isEqualTo(100L);
        assertThat(checkout.total(customerId))
                .isEqualTo(100L);
    }

    @Test
    void bookPriceBelongsOnlyToOwnCart() {
        assertThat(checkout.addItem(customerId, "book"))
                .isEqualTo(400L);
        assertThat(checkout.total(customerId))
                .isEqualTo(400L);
    }

    @Test
    void anotherCustomerDoesNotChangeMyBalance() {
        String other = "it-second-" + UUID.randomUUID();

        try {
            checkout.addItem(customerId, "pen");
            checkout.addItem(other, "book");

            assertThat(checkout.total(customerId))
                    .isEqualTo(100L);
            assertThat(checkout.total(other))
                    .isEqualTo(400L);
        } finally {
            balances.remove(other);
        }
    }
}
~~~

**Three methods** annotated with `@Execution(CONCURRENT)`, each using a UUID and removing only its own key. JUnit's default `PER_METHOD` keeps `customerId` on the test instance isolated across methods; `CheckoutService` and `CartBalances` are shared singletons whose contracts handle concurrent access properly.

Logs capture method, owner, and thread for later investigation. Under parallel execution, log line ordering is **non-deterministic**—do not assert on log order. Never log payment data or real PII.

## 19. Another Integration Class Sharing the App Context

**`src/integrationTest/java/com/example/parallellab/SafeCheckoutOtherClassTest.java`:**

~~~java
package com.example.parallellab;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Execution(ExecutionMode.CONCURRENT)
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("it")
class SafeCheckoutOtherClassTest {

    @Autowired CheckoutService checkout;
    @Autowired CartBalances balances;

    private final String customerId =
            "other-" + UUID.randomUUID();

    @AfterEach
    void cleanupOwnId() {
        balances.remove(customerId);
    }

    @Test
    void penAndBookAddToMyCart() {
        checkout.addItem(customerId, "pen");
        checkout.addItem(customerId, "book");

        assertThat(checkout.total(customerId))
                .isEqualTo(500L);
    }

    @Test
    void invalidSkuDoesNotMutateMyCart() {
        assertThatThrownBy(
                () -> checkout.addItem(customerId, "unknown")
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessageContaining("Unknown sku");

        assertThat(checkout.total(customerId)).isZero();
    }
}
~~~

**Two methods.** They can run concurrently with `SafeCheckoutParallelTest` inside the same JVM and cached Spring context (given matching context cache keys). The tests do not assert fixed context identity; they assert that business invariants hold regardless of context reuse or reload.

A failure surfacing only when both classes run concurrently typically indicates a shared resource lacking a namespace. Check whether every `@AfterEach` deletes only the ID created by that test.

## 20. Recounting Tests and Expected Outcomes

| Class | Task | Methods | Expected |
| --- | --- | ---: | --- |
| CheckoutServiceUnitTest | test | 2 | Mock price 125, price 0 rejected |
| CartBalancesConcurrencyTest | test | 2 | Atomic 6×50=300, remove A keeps B |
| RacySessionInvestigationTest | integrationTest | 1 | Alpha observes Beta due to anti-pattern |
| SafeCheckoutParallelTest | integrationTest | 3 | Pen 100, Book 400, isolated owner data |
| SafeCheckoutOtherClassTest | integrationTest | 2 | Pen+Book 500, unknown SKU stays 0 |
| **Total** | **2 tasks** | **10** | **4 unit, 6 integration** |

This count matches the `@Test` methods in code. There are no `@ParameterizedTest`, `@Disabled`, or intentionally failing dummy tests in the runnable suite. Actual CI runs can still FAIL due to environment, compilation, or code issues; never report "10 tests PASS" without executing them.

## 21. Commands for Three Controlled Experiments

**Fast unit tests:**

~~~bash
./gradlew clean test
~~~

**Sequential Jupiter integration tests:**

~~~bash
./gradlew integrationTest -PitParallel=false --rerun-tasks
~~~

**Parallel Jupiter integration tests:**

~~~bash
./gradlew integrationTest -PitParallel=true --rerun-tasks
~~~

**Selecting a specific test class:**

~~~bash
./gradlew integrationTest \
  --tests "com.example.parallellab.RacySessionInvestigationTest" \
  -PitParallel=true --rerun-tasks

./gradlew integrationTest \
  --tests "com.example.parallellab.SafeCheckoutParallelTest" \
  -PitParallel=true --rerun-tasks
~~~

**Full lifecycle:**

~~~bash
./gradlew clean check -PitParallel=true --stacktrace
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
.\gradlew.bat integrationTest -PitParallel=false --rerun-tasks
.\gradlew.bat integrationTest -PitParallel=true --rerun-tasks
.\gradlew.bat integrationTest --tests "com.example.parallellab.RacySessionInvestigationTest" -PitParallel=true --rerun-tasks
.\gradlew.bat clean check -PitParallel=true --stacktrace
~~~

`--rerun-tasks` forces Gradle to re-execute tasks so you do not mistake up-to-date/cached output for a fresh test run. To run a single test method, pass `--tests "fully.qualified.Class.method"` to the right **Test task**—it will not search classes in other source sets.

## 22. GitHub Actions Workflow Preserving Artifacts Even on FAIL

**`.github/workflows/java-test-ci.yml`:**

~~~yaml
name: java-test-ci

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - uses: gradle/actions/setup-gradle@v4

      - name: Show Java and Gradle version
        run: |
          java -version
          ./gradlew --version

      - name: Run unit tests
        run: ./gradlew --no-daemon test --stacktrace

      - name: Run integration tests with parallel Jupiter
        run: ./gradlew --no-daemon integrationTest -PitParallel=true --rerun-tasks --stacktrace

      - name: Upload test evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: junit-test-reports
          path: |
            build/test-results/test/
            build/test-results/integrationTest/
            build/reports/tests/test/
            build/reports/tests/integrationTest/
          if-no-files-found: warn
~~~

This is an illustrative workflow; adapt it to your organization's GitHub Actions policy (review/pin SHAs and upgrade major actions as needed). A failing unit step skips the integration step by default, while `if: always()` still uploads existing reports. Do not use `continue-on-error: true` to hide integration failures.

If tests genuinely use Docker/Testcontainers, the runner must have a working engine, permissions, and image readiness; this sample needs no Docker. With multi-runner CI shards, give each shard its own namespace for external databases, topics, or Redis keys rather than assuming JUnit `@ResourceLock` locks across jobs.

## 23. Test Reports: Verifying Which Tests CI Actually Ran

Gradle `Test` tasks produce XML and HTML reports. With the task names in this project:

~~~text
build/test-results/test/                    (unit XML)
build/reports/tests/test/                   (unit HTML)
build/test-results/integrationTest/         (IT XML)
build/reports/tests/integrationTest/        (IT HTML)
~~~

Expected counts are **4** cases in `test` and **6** in `integrationTest`. In CI, verify:
- Tasks did not report `NO-SOURCE`, `SKIPPED`, or exclude tests.
- XML `<testsuite>`/`<testcase>` entries match the actually executed methods.
- Failed/error/skipped counts are accurate and unfiltered.
- Reports are uploaded for **both tasks**, not just unit HTML.
- `--rerun-tasks` is used during triage to guarantee actual execution.
- Artifacts from the initial failure are not overwritten by a rerun before downloading.

An XML skeleton illustrating fields, **not actual Gradle output**:

~~~xml
<testsuite name="com.example.parallellab.SafeCheckoutParallelTest"
           tests="3" failures="0" errors="0" skipped="0">
  ...
</testsuite>
~~~

Runners and reporters can format attributes differently; use a proper report parser rather than asserting literally against this XML snippet.

## 24. Mechanism Causing Failures Only When Jupiter Methods Overlap

A poorly designed test:

~~~java
@BeforeEach
void setup() {
    globalCart.clear(); // Also deletes other tests' data!
}

@Test
void customerA() {
    checkout.addItem("shared", "pen");
    assertThat(checkout.total("shared")).isEqualTo(100);
}
~~~

This is an incomplete **counter-example** (missing class/imports) and is not part of the runnable demo. When test B also uses `"shared"` or calls `clear()` in `@BeforeEach`, A may read 0 or 500. Both tests may PASS when JUnit runs sequentially because each method assumes clean state.

How to fix:
- Generate a unique ID before each method.
- Pass the ID through the API rather than storing it in a singleton field.
- Use atomic updates for per-key operations.
- Clean up **only** the key owned by the test method.
- Await completion of background jobs before cleanup.
- Avoid global `clearAll()`/`TRUNCATE` when running in parallel.
- When external DBs/queues are needed, allocate a per-run schema, topic, or consumer group.
- For Mockito beans in a cached context, serialize those tests per Spring's guidance.

A proper regression fix must assert **business invariants**, not merely verify method calls or check that "no exception was thrown."

## 25. `@ResourceLock`, `@Isolated`, and Spring Annotation Limits

JUnit Jupiter provides `@ResourceLock("key")` so tests declaring the same lock key are serialized by the scheduler. It covers `@BeforeEach`/`@AfterEach` lifecycle methods, but **only within the same JUnit execution plan**. Every test touching that global resource must declare the matching lock. It **does not synchronize** across two Gradle JVM forks or CI shards.

Example snippet for a legacy system property:

~~~java
@Execution(ExecutionMode.CONCURRENT)
class GlobalPropertyTest {

    @Test
    @ResourceLock(
        value = "app.global.property",
        mode = ResourceAccessMode.READ_WRITE
    )
    void changesPropertyTemporarily() {
        String original =
                System.getProperty("app.global.property");
        try {
            System.setProperty("app.global.property", "test");
            // Assertions belonging to the contract under test.
        } finally {
            if (original == null) {
                System.clearProperty("app.global.property");
            } else {
                System.setProperty("app.global.property", original);
            }
        }
    }
}
~~~

This snippet needs JUnit imports and is not in the runnable source. For classes using `@MockitoBean`, `@MockitoSpyBean`, or `@DirtiesContext`, Spring Framework recommends **against parallel execution**. You can place `@Isolated` on the class or route them into a serial lane; `@Execution(SAME_THREAD)` only orders child methods under their parent and **does not isolate the class from all other classes**. `@DirtiesContext` closes the cached context at reload cost without deleting rows in an external database.

More importantly, `@ResourceLock` on tests cannot fix production code that stores `customerId` in a singleton field when live HTTP requests execute concurrently. You must fix **state ownership** in production code.

## 26. Test Transactions and Worker Threads

`@Transactional` on a Spring test method typically starts a **test-managed transaction** bound to the test thread. An HTTP server thread, `@Async` method, or Kafka listener can run in a separate transaction and commit independently. When the test rolls back, server-committed DB state is not automatically undone.

~~~text
JUnit test thread @Transactional
   BEGIN
   HTTP call -----------------> server thread
                                UPDATE database
                                COMMIT
   test ROLLBACK

Rows committed by the server may still exist.
~~~

In parallel CI runs, leftover state can collide with other tests. You need unique business IDs, explicit scoped cleanup after awaiting committed state, and Testcontainers/production-like DBs when testing locking or transaction isolation. Resetting `@DirtiesContext` or `@MockitoBean` is not a substitute for external DB cleanup.

This example uses an in-memory map to stay focused on the singleton race; it does not claim to test PostgreSQL, RabbitMQ, or Kafka.

## 27. Repeatable CI-Only Failure Triage Process

1. Preserve the original CI failure artifacts (XML/HTML/full logs), commit SHA, and tool versions.
2. Identify the exact task/source set and confirm tests are discovered.
3. Compare `-PitParallel=false` vs `true` on the same source and environment.
4. Log test method, owner key, and thread; inspect setup and teardown.
5. Inventory shared mutable objects: singletons, statics, mocks, database rows, file paths, queues.
6. If a race is suspected, construct minimal interleaving with `CountDownLatch` rather than lucky sleeps.
7. Write a red invariant on the fix branch proving the failure before the fix.
8. Fix production state ownership or apply properly scoped locking.
9. Run regression tests—both unit and integration in serial and parallel modes—multiple times if needed.
10. Verify actual JUnit counts, skipped/error counts, and external DB state.
11. Restore parallel CI for safe tests; serialize groups with unseparable shared mocks, contexts, or global resources.
12. Document root cause, fix, versions, evidence, and verification limits in the issue/PR.

An incident summary could look like:

~~~text
Symptom: expected owner alpha but observed beta under CI parallel
Root cause: mutable currentCustomer in singleton Spring bean
Proof: CountDownLatch forces A.enter -> B.enter -> A.read
Fix: request ID passed explicitly, keyed atomic storage
Regression: owner-specific assertions and scoped cleanup
CI: unit 4 + integration 6 expected; verify actual XML
~~~

This is an **incident summary template**, not a report from an actual CI run. Never label something fixed just because disabling parallelism stopped the failure.

## 28. Pre-Merge QA Checklist

- [ ] Are exact Java, Spring Boot, Gradle Wrapper, and JUnit versions recorded?
- [ ] Are Jupiter threads, Gradle forks, CI shards, and app workers distinguished?
- [ ] Were original failure XML/logs archived before rerunning?
- [ ] Are test task/source set and expected counts verified?
- [ ] Were serial and parallel runs compared using a single `itParallel` switch?
- [ ] Does any test or bean keep mutable current user/cart/tenant/session on a singleton?
- [ ] Is `volatile`/`AtomicReference` misused as request isolation?
- [ ] Are there shared static caches, default timezones, system properties, or ports?
- [ ] Do tests use unique business IDs/namespaces and scoped cleanup?
- [ ] Does any `@BeforeEach`/`@AfterEach` do a global clear affecting other tests?
- [ ] Are background tasks awaited before teardown?
- [ ] Are `@MockitoBean`/`@DirtiesContext` tests running in parallel?
- [ ] Are tests needing `@ResourceLock`/`@Isolated` aware of JVM/shard limits?
- [ ] Do server/async threads commit SQL transactions outside test rollback?
- [ ] Are Testcontainers/Redis/Kafka/DB shared across jobs?
- [ ] Are bounded latches/futures used instead of `Thread.sleep`?
- [ ] Is a diagnostic PASS (observing a bug) distinguished from a post-fix regression PASS?
- [ ] Does the fixed service avoid storing per-request identity in fields?
- [ ] Are atomic `compute` and unique keys covered by tests?
- [ ] Does CI avoid hiding failures with `ignoreFailures` or `continue-on-error`?
- [ ] Are JUnit XML/HTML reports uploaded even when a job fails?
- [ ] Have both serial and parallel suites been executed on target CI?
- [ ] Are unit 4 and integration 6 counts confirmed from actual reports?
- [ ] Are credentials/PII kept out of diagnostic logs?
- [ ] Are test PASS claims withheld until tests have actually been executed?

## 29. Expected Results and Official Documentation

With the right source files and configured environment:

| Command | Expected |
| --- | --- |
| `./gradlew test` | 4 unit tests |
| `./gradlew integrationTest -PitParallel=false` | 6 integration tests; sequential Jupiter scheduler |
| `./gradlew integrationTest -PitParallel=true` | 6 integration tests; parallel Jupiter enabled |
| `./gradlew check` | 10 methods across 2 tasks |
| `RacySessionInvestigationTest` | Alpha observes Beta: proves the anti-pattern class has a bug |
| `SafeCheckoutParallelTest` | Pen 100, Book 400, independent keys |
| `CartBalancesConcurrencyTest` | 6×50 increments = 300, removing A does not delete B |

**These figures represent expected behavior, not actual Gradle/JUnit output.** The sample code has not been compiled/run during authoring; to confirm, assemble the project, run the Gradle Wrapper, and check `build/test-results/test` + `build/test-results/integrationTest`. Log order under parallel tests is non-deterministic. A diagnostic test that observes the bug and PASSES **does not mean the defective class is safe to deploy**.

### Official References

- [Spring Framework 6.2 — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html)
- [Spring Framework 6.2 — TestContext Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework 6.2 — @DirtiesContext](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html)
- [JUnit Jupiter 5.12 — Parallel Test Execution](https://docs.junit.org/5.12.0/user-guide/#writing-tests-parallel-execution)
- [JUnit Jupiter 5.12 — Test Instance Lifecycle](https://docs.junit.org/5.12.0/user-guide/#writing-tests-test-instance-lifecycle)
- [Gradle — Testing in Java/JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Test Task](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/Test.html)
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Gradle plugin requirements](https://docs.spring.io/spring-boot/3.5/gradle-plugin/)
- [Gradle — GitHub Actions CI](https://docs.gradle.org/current/userguide/github-actions.html)
- [Java 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Java 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

**Conclusion:** When a CI-only failure appears after enabling parallelism, gather evidence and distinguish the concurrency layers. Compare serial vs parallel to isolate the failure, use latches to force the race and prove the root cause, and then fix mutable state ownership: **never store customer identity in a singleton field**—pass IDs explicitly and use atomic keyed storage with per-test cleanup. Keep parallelism for independent tests, serialize groups with inseparable shared mocks, contexts, or global resources, and rely on actual JUnit XML reports as evidence.