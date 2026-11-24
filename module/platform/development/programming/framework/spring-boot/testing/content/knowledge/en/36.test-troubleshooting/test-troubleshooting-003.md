# Context Failure Threshold and Repeated Messages Masking the Root Cause in Spring Boot Test

## 1. Real-World Scenario: Dozens of Tests Red, Yet Only One Broken Configuration

You upgrade Spring Boot or change a property for the `test` profile. When running the full `@SpringBootTest` suite, many classes fail with the same error:

~~~text
java.lang.IllegalStateException:
ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context for
[MergedContextConfiguration@... testClass=..., classes=..., ...]
~~~

Beginners often conclude they need to raise the threshold, add `@DirtiesContext`, clear the cache, or fix every test marked red. Yet this message is usually **not the root cause**. It states that **an ApplicationContext initialization with the same context-cache key already failed**, and the Spring TestContext Framework **deliberately declined to retry** for subsequent tests sharing that key because only one failed attempt is allowed by default.

The first failure in that group might be:

~~~text
java.lang.IllegalStateException:
Failed to load ApplicationContext for
[MergedContextConfiguration@...]
Caused by: org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'paymentClient'
Caused by: java.lang.IllegalArgumentException:
Missing property payment.gateway.url
~~~

Only the final line `Missing property payment.gateway.url` tells you what actually needs fixing. Subsequent `failure threshold exceeded` messages are **consequences of sharing the same cache key**, not proof that independent test logic has bugs.

**Topic:** "Context failure threshold and repeated messages masking the root cause", under **Test Troubleshooting** in Spring Boot testing. The focus is **how to trace back to the cause of the first context load** and understand why a wave of repeated failures appears.

After this lesson, you will be able to:

1. Explain context-cache keys, cache misses, and `ApplicationContext` loading in Spring TestContext.
2. State the **context failure threshold policy introduced in Spring Framework 6.1**, **defaulting to 1 per key**.
3. Distinguish an **actual failed initialization** from a **preemptively skipped load**.
4. Configure `spring.test.context.failure.threshold` properly and know where the **JVM system property in the test worker** must be set.
5. Understand why `-D...` passed to Gradle does not always forward automatically to the test worker JVM unless the build script passes it along.
6. Recognize how `@ActiveProfiles`, `@SpringBootTest(properties=...)`, `@TestPropertySource`, `@MockBean`, `@DynamicPropertySource`, and other test settings change the cache key.
7. Read stack traces along `Caused by` to find the lowest meaningful failure instead of reading only the red test summary.
8. Prioritize the **chronologically first** test class/initialization attempt rather than assuming the alphabetically first class holds the root error.
9. Enable targeted logs, read Gradle XML/HTML test reports, and avoid relying on `--stacktrace` as a substitute for the test exception chain.
10. Build a **Java 17 + Spring Boot 3.3.5 project** using `TestContextManager` to simulate context initialization failures while **keeping the JUnit suite PASSING**.
11. Verify `threshold=1`, `threshold=2`, independent context keys, successful context reuse, and property profile differences.
12. Distinguish **context failure threshold**, **cache max size**, **`@DirtiesContext`**, and **JUnit retry plugins**.
13. Handle common root causes properly: bean definitions, missing properties, database connectivity, migrations, credentials, port conflicts, and incompatible test overrides.
14. Avoid exposing secrets in diagnostic logs or destabilizing CI by globally disabling the threshold.

**Example versions:** Java **17**, Spring Boot **3.3.5**, Spring Framework **6.1.x**, Spring TestContext, and JUnit Jupiter 5 selected by Spring Boot dependency management. The example uses stable 6.1 APIs: `TestContextManager.getTestContext().getApplicationContext()`, `@ContextConfiguration`, `@TestPropertySource`, and `ContextCacheUtils`.

## 2. Separating Spring Boot Context Loading from Test Logic

For a `@SpringBootTest`, before any `@Test` runs, Spring TestContext prepares the `ApplicationContext`:

~~~text
JUnit discovers test classes
        |
        v
SpringExtension / TestContextManager
        |
        v
Build MergedContextConfiguration (context cache key)
        |
        +--- Cache HIT ------> reuse already active ApplicationContext
        |
        +--- Cache MISS
                 |
                 v
          Is failure count for key >= threshold?
                 |
              +--+--+
              |     |
             YES    NO
              |     |
              v     v
         Skip load  Actually create/refresh context
              |     |
              |  +--+------------------+
              |  |                     |
              | SUCCESS               FAILURE
              |  |                     |
              | Cache context        Increment failure count for key
              |                        |
              v                        v
         IllegalStateException     Initial load error + causal chain
~~~

Key takeaways:

- **Failures before the `@Test` body** can happen during component scan, auto-configuration, bean initialization, web server bootstrap, database migrations, or `TestExecutionListener` execution.
- When context loading fails, the framework records a **failure count** for that **context cache key**.
- When the threshold is **1**, the next request needing the same key is **preemptively skipped** and throws `IllegalStateException`.
- Spring **does not retry building all beans again**, because environmental/configuration faults rarely vanish on their own.
- Only tests sharing the **same key** share that threshold counter. Different keys have independent counters.
- A **successful** context load is cached and reused; subsequent tests hit the cache cleanly as long as it remains valid.

**This is a Spring TestContext mechanism, not Spring Boot application retry logic.** It does not resend HTTP requests or retry Kafka consumers or JDBC transactions. `ApplicationContext failure threshold exceeded` during test bootstrapping is completely unrelated to Resilience4j retries or circuit breakers in business code.

### 2.1. Why Does the Initial Error Appear in a Different Test?

Consider three test classes A, B, and C sharing the same configuration:

~~~text
Worker 1: Class A --> cache key K --> first load --> FAIL (DB URL invalid)
Worker 1: Class B --> cache key K --> load skipped (threshold 1 exceeded)
Worker 1: Class C --> cache key K --> load skipped (threshold 1 exceeded)
~~~

In parallel CI runs or non-deterministic Gradle test ordering, **which class touches the cache first** can vary. A report sorted alphabetically by test class might display Class B at the top even though Class A triggered the actual bootstrap failure. Therefore, **find the chronologically first context initialization failure in logs/reports**, then trace `Caused by`.

Do not treat `testClass=SomeTest` inside `MergedContextConfiguration` as proof that `SomeTest` has a business logic bug. That string merely describes the loaded configuration metadata, not the root exception.

### 2.2. Threshold=1 Does Not Mean "Only One Test Can Fail"

If there are distinct keys K1, K2, and K3:

~~~text
K1: first attempt FAIL -> subsequent K1 attempts skipped
K2: first attempt FAIL -> subsequent K2 attempts skipped
K3: first attempt SUCCESS -> K3 context cached/reused normally
~~~

The failure count is tracked **per key**, not per JVM and not as a "global failure limit for the whole suite." If 10 distinct context keys are misconfigured, you can see 10 actual failed loads—one per key. If 100 tests share one broken key, the first fails and the rest skip.

### 2.3. What Makes Up a Context Cache Key?

In Spring Framework 6.1 / Spring Boot 3.3, elements typically contributing to `MergedContextConfiguration` include:

| Element | Example | Why It Matters |
|---|---|---|
| `classes` | `@ContextConfiguration(classes=...)`, Boot app class | Different classes produce a different key |
| `locations` | XML/config resources | Different resources mean different config |
| `contextInitializerClasses` | Custom `ApplicationContextInitializer` | Different context initialization |
| `contextCustomizers` | Boot test customizers, `@MockBean`, `@DynamicPropertySource` | Bean overrides/dynamic definitions distinguish keys |
| `contextLoader` | Selected context loader | Affects bootstrapping |
| `activeProfiles` | `@ActiveProfiles("test")` vs `"staging"` | Different properties/beans |
| `propertySourceDescriptors` | Locations from `@TestPropertySource` | Different property sources |
| `propertySourceProperties` | `@SpringBootTest(properties="x=1")` | Different inline properties |
| `parent` | Context hierarchy | Related parent state and keys |
| `resourceBasePath` | WebApplicationContext resource path | Different web resources |

A test with `@MockBean PaymentGateway` and a test without the mock produce two distinct keys, so they do not share a failure count. Two classes with the **exact same configuration** share a key regardless of class name.

**Do not randomly tweak properties/profiles just to dodge the threshold.** Doing so changes what is being tested, inflates cached contexts, and hides bugs. Change keys only for explicit contract or configuration reasons.

## 3. Spring 6.1 Failure Threshold: Default Value and Configuration

**Since Spring Framework 6.1**, `DefaultCacheAwareContextLoaderDelegate` supports the policy:

~~~properties
spring.test.context.failure.threshold=1
~~~

The **default = 1**. The value must be a **positive integer**. This is a **Spring TestContext JVM system property** or a property supplied via `SpringProperties`; it is **not `spring.main.*`** and should not simply be placed in `application.yml` assuming TestContext reads it before building the context.

| Value | Behavior Per Context Key |
|---:|---|
| `1` (default) | Allows **one actual load attempt**; if it fails, subsequent attempts skip |
| `2` | Allows **up to two actual failed load attempts** before skipping |
| `3` | Allows **up to three actual load attempts** before skipping |
| `1000000` | Practically disables the threshold in a normal suite; not recommended as a default |

Setting `2` does **not** mean Spring retries twice inside a single `getApplicationContext()` call. It means **if a subsequent load request arrives** for the same failed key, the framework allows one more real attempt until the threshold is reached. There is no backoff or recovery logic.

### 3.1. JVM System Property in the Gradle Test Worker

**Explicit configuration in `build.gradle`:**

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()
    systemProperty 'spring.test.context.failure.threshold', '1'
}
~~~

This is the right place because Gradle runs tests inside a worker JVM. In projects supporting diagnostic overrides, you can forward the value from the Gradle process to the test JVM:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()

    systemProperty 'spring.test.context.failure.threshold',
            System.getProperty(
                    'spring.test.context.failure.threshold', '1')
}
~~~

With the second **forwarding** snippet, the following command reaches the test JVM properly:

~~~bash
./gradlew test -Dspring.test.context.failure.threshold=2
~~~

(Wait—let's check the fence in original file 003 lines 190-192: it used `~~~bash`! Let's make sure we keep `~~~bash` verbatim!)

**Note:** `-Dspring.test.context.failure.threshold=2` is a JVM system property on the Gradle process. If the build script **does not forward it into the `Test` task**, do not assume the forked test JVM sees it. Alternatives are setting `systemProperty` directly on the `Test` task or reading an explicit environment variable in the build script.

**Do not replace 1 with 1000000 as a "bug fix."** That forces every test class to retry loading a broken context, bloating logs and slowing CI. Large values are only short-term diagnostic tools in targeted runs, after which you restore the default and fix the root cause.

### 3.2. Scope of the Failure Count

The count belongs to the **context cache** per key. By default, the cache is **static within the test JVM**, so it is shared across multiple Spring test classes in the same process.

When Gradle:
- Runs with `maxParallelForks > 1`: each test worker JVM has its own cache and counters.
- Uses `forkEvery`: a fresh JVM loses counters from the previous JVM.
- Runs `./gradlew test` twice: test workers across two executions do not share static Java state.
- Runs tests in the IDE vs Gradle separately: caches are separate.

A cache key that failed in JVM A can attempt a fresh first load in JVM B. That is not a broken threshold policy—it is **separate process scope**.

**Do not confuse** `spring.test.context.failure.threshold` with `spring.test.context.cache.maxSize` (LRU cache defaulting to 32). The former bounds **failed loads per key**; the latter bounds **how many successfully loaded contexts remain cached**. Raising `maxSize` will not fix bean creation; raising failure threshold will not fix LRU cache evictions.

## 4. Mechanically Distinguishing the Two Error Messages

### 4.1. Actual First Failure

An actual load failure typically contains:

~~~text
java.lang.IllegalStateException:
Failed to load ApplicationContext for [MergedContextConfiguration@...]
    at org.springframework.test.context.cache.DefaultCacheAwareContextLoaderDelegate.loadContext(...)
Caused by: org.springframework.beans.factory.UnsatisfiedDependencyException:
Error creating bean with name 'orderController'
Caused by: org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'paymentClient'
Caused by: java.lang.IllegalStateException:
MISSING_PAYMENT_URL: payment.gateway.url is absent in test environment
~~~

This is an **illustrative trace**; bean names and line numbers depend on the project. How to read it:

1. `Failed to load ApplicationContext` states **context bootstrap failed**.
2. `UnsatisfiedDependencyException` indicates a bean could not resolve a dependency.
3. `BeanCreationException` points to `paymentClient` as the failing bean in the chain.
4. `MISSING_PAYMENT_URL` at the deepest point is the **actionable failure**.
5. If the deepest cause is `ConnectException` or `PSQLException`, the root cause may lie in DB service/port/config rather than Java injection.
6. Do not rush to edit the topmost bean in the chain before reading deeper causes.

**The final `Caused by` line is not always the whole answer.** If the root is a `java.lang.NullPointerException` with no message, you still need the frames, methods, and bean context above it. Still, it is the right place to start; in many cases, the deepest meaningful cause names the missing property or unreachable resource.

### 4.2. Repeated Messages After Reaching the Threshold

~~~text
java.lang.IllegalStateException:
ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context for
[MergedContextConfiguration@...]
~~~

This second message **does not mean Spring tried to initialize `paymentClient` again**. On the contrary, the skip policy exists to **avoid retrying**. It may omit the deeper `Caused by: ... MISSING_PAYMENT_URL` chain, which is why opening only the last failing test's stack trace leaves you guessing what to fix.

**Proper distinction:**
- "Failed to load ApplicationContext": inspect the full chain and actual bean/resource.
- "Failure threshold exceeded / skipping repeated attempt": find the **first failure** for that cache key; do not try to "fix" the skip message.
- "Failed to load ..." appearing for multiple keys: there may be **multiple root causes**; do not force the entire suite into one hypothesis.

### 4.3. Standardizing a Repeatable Diagnostic Workflow

When reading CI logs:
1. Note `MergedContextConfiguration` and relevant `classes`, `activeProfiles`, `propertySourceProperties`, and `contextCustomizers`.
2. Search for **stack traces without the skip message**.
3. Inside those traces, locate the deepest `Caused by` with bean, property, port, or file details.
4. Compare keys to group test failures sharing the same cause.
5. Fix the configuration, then run **one representative test** followed by the **full suite**.
6. Avoid turning report presentation order into an assumption about execution order; HTML reports often sort alphabetically by test class rather than initialization time.

A grep filter helps **locate** entries in logs, not replace reading the full trace:

~~~bash
grep -nE "Failed to load ApplicationContext|failure threshold|Caused by:" build.log
~~~

This command suits Linux/macOS with `grep`; on Windows PowerShell use `Select-String`. Even after filtering, open surrounding lines to understand the true root cause rather than reading single matched lines.

## 5. Runnable Project: Spring Boot 3.3.5, Java 17, JUnit Jupiter

To study the mechanism **without making the entire test suite intentionally red**, the project:
- Includes a real Spring Boot app with `GreetingService` and 2 normal `@SpringBootTest` tests.
- Includes a **plain JUnit class** (not annotated `@SpringBootTest`) containing nested "probe classes" annotated with `@ContextConfiguration`.
- Uses `TestContextManager` inside test bodies to ask Spring TestContext to load those probe contexts.
- Intentionally throws marker exceptions from probe bean configs, while JUnit **`assertThrows`** catches them and verifies subsequent loads are properly skipped.
- Uses static counters in fixture configs to distinguish **actual failed loads** from preemptively skipped ones.
- Includes one test that temporarily switches the system property to `threshold=2` and restores it in `finally`, with parallel execution disabled to avoid global-property interference.
- Uses `@TestPropertySource` on two probe types sharing the **same config class with different inline properties**, proving distinct keys maintain separate failure counts.

**Benefit:** Initialization failures are triggered **intentionally in a sandbox** and asserted as data without causing unexpected CI failures. No DB, Docker, HTTP server, or external service is needed.

### 5.1. Directory Structure

~~~text
settings.gradle
build.gradle
src/main/java/demo/threshold/ThresholdDemoApplication.java
src/main/java/demo/threshold/GreetingService.java
src/test/resources/junit-platform.properties
src/test/java/demo/threshold/HealthyBootContextTest.java
src/test/java/demo/threshold/ContextFailureThresholdTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'context-failure-threshold-demo'
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

    // Demo asserts threshold=1 except where a method
    // temporarily sets threshold=2 and restores it.
    systemProperty 'spring.test.context.failure.threshold', '1'

    // Cache and failure counters are shared only within the same JVM.
    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**src/test/resources/junit-platform.properties**

~~~properties
junit.jupiter.execution.parallel.enabled=false
~~~

Why disable Jupiter parallelism: one demo test temporarily mutates the **JVM-global system property** `spring.test.context.failure.threshold`, while tests creating Spring contexts must read a consistent value. In real projects you can enable parallel tests when resources/isolation are controlled, but **do not share a mutable system property across parallel context loaders**.

**Dependency note:** `spring-boot-starter-test` already includes `spring-test`/JUnit Jupiter. Do not add a separate `spring-test` version manually. Do not mix Boot 2 `javax.*` packages with Boot 3 `jakarta.*`. The source focuses on Spring TestContext without an HTTP starter.

### 5.2. Main Class

**src/main/java/demo/threshold/ThresholdDemoApplication.java**

~~~java
package demo.threshold;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ThresholdDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ThresholdDemoApplication.class, args);
    }
}
~~~

**src/main/java/demo/threshold/GreetingService.java**

~~~java
package demo.threshold;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            return "Hello, guest";
        }
        return "Hello, " + name;
    }
}
~~~

A simple service providing a **healthy Boot context** without external resources. If `@SpringBootTest` in the next class fails to start, the fault lies in app/test config rather than a DB environment or the intentionally broken probe.

### 5.3. Two Smoke Tests on a Real, Healthy Context

**src/test/java/demo/threshold/HealthyBootContextTest.java**

~~~java
package demo.threshold;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class HealthyBootContextTest {

    @Autowired
    GreetingService greetings;

    @Autowired
    ConfigurableApplicationContext context;

    @Test
    void healthyContextCanInjectService() {
        assertEquals("Hello, Lan", greetings.greet("Lan"));
        assertSame(greetings, context.getBean(GreetingService.class));
    }

    @Test
    void healthyContextIsUsableForAnotherMethod() {
        assertEquals("Hello, guest", greetings.greet(" "));
        assertTrue(context.isActive());
    }
}
~~~

**Exactly 2 JUnit `@Test` methods** in this class. `WebEnvironment.NONE` ensures no embedded HTTP server starts. Both methods in the same class can share the context; the test does not assert absolute context load counts.

**Remember:** `HealthyBootContextTest` is managed automatically by `SpringExtension` via `@SpringBootTest` and injects `ConfigurableApplicationContext` to call `isActive()`. The failing probe configs in the plain JUnit class use `@TestConfiguration` so `@SpringBootApplication`'s normal component scan does not pick them up into the real context. The diagnostic class below is plain JUnit calling `new TestContextManager(...)` **explicitly** to test Spring TestContext mechanics without letting `SpringExtension` fail before entering `@Test`.

## 6. Test Harness: Creating Intentional Startup Failures While JUnit Passes

**src/test/java/demo/threshold/ContextFailureThresholdTest.java**

~~~java
package demo.threshold;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.TestContextManager;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.cache.ContextCacheUtils;

import static org.junit.jupiter.api.Assertions.*;

class ContextFailureThresholdTest {

    private static final String THRESHOLD =
            "spring.test.context.failure.threshold";

    // Each call creates a TestContextManager, yet identical
    // context-cache keys still share Spring Test's static cache.
    private static ApplicationContext load(Class<?> probeClass) {
        return new TestContextManager(probeClass)
                .getTestContext()
                .getApplicationContext();
    }

    private static String causeMessages(Throwable failure) {
        StringBuilder result = new StringBuilder();
        Throwable item = failure;

        while (item != null) {
            result.append(item.getClass().getSimpleName())
                    .append(": ")
                    .append(item.getMessage())
                    .append('\n');
            item = item.getCause();
        }

        return result.toString();
    }

    private static void checkSkipped(IllegalStateException failure,
                                     int expectedThreshold) {
        String message = failure.getMessage();

        assertNotNull(message);
        assertTrue(
                message.contains(
                        "ApplicationContext failure threshold ("
                        + expectedThreshold + ") exceeded"),
                message);

        assertTrue(
                message.contains(
                        "skipping repeated attempt to load context"),
                message);
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class BrokenAConfig {
        static final AtomicInteger ATTEMPTS = new AtomicInteger();

        @Bean
        String brokenBean() {
            ATTEMPTS.incrementAndGet();
            throw new IllegalStateException(
                    "ROOT_A: payment.gateway.url missing");
        }
    }

    @ContextConfiguration(classes = BrokenAConfig.class)
    static class ProbeA {
        // Metadata-only; not a JUnit test class.
    }

    @Test
    void firstFailureKeepsRootCauseSecondAttemptIsSkipped() {
        BrokenAConfig.ATTEMPTS.set(0);

        IllegalStateException first = assertThrows(
                IllegalStateException.class,
                () -> load(ProbeA.class));

        assertTrue(
                causeMessages(first).contains(
                        "ROOT_A: payment.gateway.url missing"));

        IllegalStateException second = assertThrows(
                IllegalStateException.class,
                () -> load(ProbeA.class));

        checkSkipped(second, 1);
        assertEquals(1, BrokenAConfig.ATTEMPTS.get());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class BrokenBConfig {
        static final AtomicInteger ATTEMPTS = new AtomicInteger();

        @Bean
        String brokenBean() {
            ATTEMPTS.incrementAndGet();
            throw new IllegalStateException(
                    "ROOT_B: data source cannot connect");
        }
    }

    @ContextConfiguration(classes = BrokenBConfig.class)
    static class ProbeB {
    }

    @Test
    void anotherConfigurationKeyGetsItsOwnFirstAttempt() {
        BrokenBConfig.ATTEMPTS.set(0);

        IllegalStateException first = assertThrows(
                IllegalStateException.class,
                () -> load(ProbeB.class));

        assertTrue(causeMessages(first).contains("ROOT_B:"));
        assertEquals(1, BrokenBConfig.ATTEMPTS.get());

        IllegalStateException next = assertThrows(
                IllegalStateException.class,
                () -> load(ProbeB.class));

        checkSkipped(next, 1);
        assertEquals(1, BrokenBConfig.ATTEMPTS.get());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class VariantBrokenConfig {
        static final AtomicInteger ATTEMPTS = new AtomicInteger();

        @Bean
        String brokenByVariant(Environment environment) {
            ATTEMPTS.incrementAndGet();

            throw new IllegalArgumentException(
                    "VARIANT_FAILURE:"
                    + environment.getProperty("case.variant"));
        }
    }

    @ContextConfiguration(classes = VariantBrokenConfig.class)
    @TestPropertySource(properties = "case.variant=alpha")
    static class VariantAlphaProbe {
    }

    @ContextConfiguration(classes = VariantBrokenConfig.class)
    @TestPropertySource(properties = "case.variant=beta")
    static class VariantBetaProbe {
    }

    @Test
    void differentInlinePropertiesCreateIndependentCacheKeys() {
        VariantBrokenConfig.ATTEMPTS.set(0);

        IllegalStateException alpha = assertThrows(
                IllegalStateException.class,
                () -> load(VariantAlphaProbe.class));

        IllegalStateException beta = assertThrows(
                IllegalStateException.class,
                () -> load(VariantBetaProbe.class));

        assertTrue(causeMessages(alpha).contains(
                "VARIANT_FAILURE:alpha"));
        assertTrue(causeMessages(beta).contains(
                "VARIANT_FAILURE:beta"));

        // Each property variant has its own key, so both
        // attempt real context initialization exactly once.
        assertEquals(2, VariantBrokenConfig.ATTEMPTS.get());

        IllegalStateException alphaAgain = assertThrows(
                IllegalStateException.class,
                () -> load(VariantAlphaProbe.class));

        checkSkipped(alphaAgain, 1);
        assertEquals(2, VariantBrokenConfig.ATTEMPTS.get());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class HealthyConfig {
        @Bean
        String greetingMarker() {
            return "HELLO_FROM_HEALTHY_CONFIG";
        }
    }

    @ContextConfiguration(classes = HealthyConfig.class)
    static class HealthyProbe {
    }

    @Test
    void successfulContextIsCachedAndReused() {
        ApplicationContext first = load(HealthyProbe.class);
        ApplicationContext second = load(HealthyProbe.class);

        assertSame(first, second);
        assertEquals(
                "HELLO_FROM_HEALTHY_CONFIG",
                first.getBean("greetingMarker", String.class));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class KeyValueConfig {
        @Bean
        String selectedVariant(Environment environment) {
            return environment.getRequiredProperty("case.variant");
        }
    }

    @ContextConfiguration(classes = KeyValueConfig.class)
    @TestPropertySource(properties = "case.variant=one")
    static class KeyOneProbe {
    }

    @ContextConfiguration(classes = KeyValueConfig.class)
    @TestPropertySource(properties = "case.variant=two")
    static class KeyTwoProbe {
    }

    @Test
    void sameBeanConfigurationWithDifferentPropertiesIsNotSameContext() {
        ApplicationContext one = load(KeyOneProbe.class);
        ApplicationContext two = load(KeyTwoProbe.class);

        assertNotSame(one, two);
        assertEquals("one",
                one.getBean("selectedVariant", String.class));
        assertEquals("two",
                two.getBean("selectedVariant", String.class));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class BrokenThresholdTwoConfig {
        static final AtomicInteger ATTEMPTS = new AtomicInteger();

        @Bean
        String alwaysFailing() {
            ATTEMPTS.incrementAndGet();
            throw new IllegalStateException(
                    "ROOT_T2: deliberate failure");
        }
    }

    @ContextConfiguration(classes = BrokenThresholdTwoConfig.class)
    static class ThresholdTwoProbe {
    }

    @Test
    void thresholdTwoAllowsTwoActualLoadFailuresThenSkips() {
        String previous = System.getProperty(THRESHOLD);

        BrokenThresholdTwoConfig.ATTEMPTS.set(0);
        System.setProperty(THRESHOLD, "2");

        try {
            IllegalStateException first = assertThrows(
                    IllegalStateException.class,
                    () -> load(ThresholdTwoProbe.class));

            IllegalStateException second = assertThrows(
                    IllegalStateException.class,
                    () -> load(ThresholdTwoProbe.class));

            assertTrue(causeMessages(first).contains("ROOT_T2:"));
            assertTrue(causeMessages(second).contains("ROOT_T2:"));
            assertEquals(
                    2,
                    BrokenThresholdTwoConfig.ATTEMPTS.get());

            IllegalStateException third = assertThrows(
                    IllegalStateException.class,
                    () -> load(ThresholdTwoProbe.class));

            checkSkipped(third, 2);
            assertEquals(
                    2,
                    BrokenThresholdTwoConfig.ATTEMPTS.get());
        } finally {
            if (previous == null) {
                System.clearProperty(THRESHOLD);
            } else {
                System.setProperty(THRESHOLD, previous);
            }
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class NestedCauseConfig {
        @Bean
        String nestedFailure() {
            IllegalArgumentException database =
                    new IllegalArgumentException(
                            "ROOT_NESTED: database port is invalid");

            throw new IllegalStateException(
                    "Service initialization failed",
                    database);
        }
    }

    @ContextConfiguration(classes = NestedCauseConfig.class)
    static class NestedCauseProbe {
    }

    @Test
    void rootCauseMayBeDeeperThanBeanCreationException() {
        IllegalStateException first = assertThrows(
                IllegalStateException.class,
                () -> load(NestedCauseProbe.class));

        String chain = causeMessages(first);

        assertTrue(chain.contains(
                "Service initialization failed"));
        assertTrue(chain.contains(
                "ROOT_NESTED: database port is invalid"));

        Throwable deepest = first;

        while (deepest.getCause() != null) {
            deepest = deepest.getCause();
        }

        assertInstanceOf(
                IllegalArgumentException.class, deepest);
    }

    @Test
    void configuredDefaultThresholdIsOneInThisTestWorker() {
        // build.gradle passes the JVM property to Test worker.
        assertEquals(
                "1",
                System.getProperty(THRESHOLD));

        assertEquals(
                1, ContextCacheUtils.retrieveContextFailureThreshold());
    }
}
~~~

**Exact count:** `ContextFailureThresholdTest` has **8 `@Test`** methods; `HealthyBootContextTest` has **2 `@Test`** methods. Total project count is **10 JUnit Jupiter test methods**. Nested classes `ProbeA`, `ProbeB`, `VariantAlphaProbe`, etc. **have no `@Test` methods** and are not discovered by JUnit as independent test classes; they simply supply metadata to `TestContextManager`.

**Why can everything PASS even though beans intentionally throw?** Inside the JUnit test methods, `assertThrows(IllegalStateException.class, () -> load(...))` **expects** an exception from `TestContextManager`. The check PASSES if Spring throws as expected, and fails if the bean loads normally. On the application side, these nested probe configurations are **test-only failures** not `@Import`ed into the main Boot context.

**Why attach marker names?** `ROOT_A`, `ROOT_B`, `VARIANT_FAILURE`, `ROOT_T2`, and `ROOT_NESTED` help distinguish the root exception from the `Failed to load ApplicationContext` wrapper. In real systems, exception messages can expose JDBC URLs or credentials; **never place real passwords/tokens into test fixtures or public logs**.

### 6.1. What Do the Assertions Demonstrate?

| JUnit Test | What Is Proven |
|---|---|
| `firstFailureKeepsRootCauseSecondAttemptIsSkipped` | Default threshold 1: first attempt throws root marker; second attempt skips; bean init count stays 1 |
| `anotherConfigurationKeyGetsItsOwnFirstAttempt` | Another key gets its own first failure attempt and skips on the next |
| `differentInlinePropertiesCreateIndependentCacheKeys` | Two different `@TestPropertySource` configs -> two real attempts; alpha retry skips |
| `successfulContextIsCachedAndReused` | Successful context is cached and returns the exact same instance |
| `sameBeanConfigurationWithDifferentPropertiesIsNotSameContext` | Even with the same `@Configuration` class, different properties yield distinct contexts |
| `thresholdTwoAllowsTwoActualLoadFailuresThenSkips` | With threshold 2: two real failures, third skips |
| `rootCauseMayBeDeeperThanBeanCreationException` | Cause chain wraps a deeper real `IllegalArgumentException` |
| `configuredDefaultThresholdIsOneInThisTestWorker` | Gradle passed system property 1 to the test worker |

With real `@SpringBootTest` tests, failures happen **before the test body**, so JUnit marks a failure. With a plain JUnit harness, we inspect Spring's behavior inside the test body, keeping the suite green. The two models do not conflict; they test at two different levels.

### 6.2. Do Not Rely on `ApplicationContext.getId()` to Infer a Cache Hit

In `successfulContextIsCachedAndReused`, `assertSame(first,second)` verifies **exact object identity**, rather than comparing `getId()` (two separate contexts can receive the same string ID). For distinct keys, `assertNotSame(one,two)` verifies distinct instances, and bean property values are also checked.

In `BrokenAConfig.ATTEMPTS`, the counter is a **static** field on the test fixture, persisting across context attempts within the JVM. If Spring does not actually try constructing the bean a second time, the counter stays at 1. Static counters **are not automatically reset by the Spring context cache**; the project resets each counter at the start of the method using that key and runs JUnit tests sequentially.

### 6.3. Why Not Use an Intentionally Broken `@SpringBootTest`?

If you write:

~~~java
@SpringBootTest(properties = "payment.gateway.url=")
class IntentionallyBrokenBootTest {
    @Test
    void mustNotStart() {
        // This body is never reached when context fails to start.
    }
}
~~~

This snippet is **not part of the runnable project** and defines no bean requiring that property, illustrating a design pitfall. If context initialization genuinely fails, JUnit usually **never enters the test body** to assert the exception. A `@Test` containing `assertThrows` in its body cannot catch errors occurring earlier during **test instance preparation**.

To test Spring TestContext's failure policy as an API, use `TestContextManager` inside a plain JUnit test as in the main example. To test full Boot app startup failures, use a separate harness or `ApplicationContextRunner` to assert the root failure—noting that **`ApplicationContextRunner` alone does not prove Spring TestContext's failure threshold**, because it does not go through the same context cache policy.

## 7. Run Commands, Gradle Reports, and Expected Outcomes

The project requires JDK 17, a Gradle version compatible with the Spring Boot 3.3.5 plugin, and access to Maven Central if dependencies are not cached. No Docker, database, HTTP network, or SMTP is required.

If the Gradle Wrapper has been created:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If you created the files above **without generating `gradlew`, `gradlew.bat`, and the wrapper JAR**, `./gradlew` will not run yet. Use an installed Gradle binary to generate the wrapper, or run:

~~~bash
gradle test
~~~

Run classes individually:

~~~bash
./gradlew test --tests demo.threshold.HealthyBootContextTest
./gradlew test --tests demo.threshold.ContextFailureThresholdTest
~~~

To prevent Gradle from returning `UP-TO-DATE` and skipping a fresh execution during diagnosis:

~~~bash
./gradlew test --rerun-tasks
~~~

Reports:
- HTML: `build/reports/tests/test/index.html`.
- JUnit XML: `build/test-results/test/TEST-*.xml`.
- Stdout/stack traces may be captured by Gradle and displayed in HTML/XML depending on test logging config.
- The first log mentioning `ROOT_A` typically accompanies initializing the broken config, though **log/report ordering across tests must not be treated as a contract**.

**Expected outcome based on source and Spring 6.1 API:** **10 JUnit test methods are designed to PASS**, while several deliberate context load attempts inside those tests throw exceptions caught by `assertThrows`. This is a technical expectation from the code; **it is not a claim that Gradle was executed in the reader's environment**. Framework/Gradle logs may print stack traces from probe loads because those are intentional test inputs rather than unexpected failures.

**If the threshold-2 test fails:** First check that `junit-platform.properties` disables parallelism and that Gradle passed `systemProperty` 1 to the worker. Inside the method, the property is temporarily set to `"2"` before the first `TestContextManager` for `ThresholdTwoProbe` is created, and restored in `finally`. That way, each new `TestContextManager` reads threshold 2. No external tests should concurrently mutate `spring.test.context.failure.threshold` in the same JVM.

## 8. Investigating Real Failures in a Reliable Sequence

### 8.1. Start with a Failure Showing the Full Cause Chain

1. Run a single **representative failing test class** to cut down noise:
   `./gradlew test --tests com.example.OrderRepositoryTest --rerun-tasks`.
2. If it shares a context key with the other failing classes, running it alone in a fresh test JVM typically makes it the **first attempted load**, exposing the root cause instead of a skip.
3. Read the JUnit XML/HTML report and full stack trace rather than only `> Task :test FAILED`.
4. Locate `Failed to load ApplicationContext` and the `Caused by` entries below it.
5. Read the bean name, property key, resource path, host/port, active profile, and nested exceptions.
6. Cross-check with real config: `@ActiveProfiles`, `@SpringBootTest(properties)`, `@MockBean`, `@DynamicPropertySource`.
7. Fix the root issue and rerun the representative test.
8. Run the full suite and confirm no other keys are still failing.
9. Do not raise the threshold merely to silence "skipping repeated attempt" messages.

**Running a class in isolation can change the context key or hide cross-class interference**, so if a failure only appears in the full suite, keep the full-run logs and compare configurations and execution order instead of assuming the bug disappeared. Test pollution or shared singleton bugs can hide in isolated runs.

### 8.2. Classifying Causes from the Root Exception

| Root Exception | Likely Causes | Check Next |
|---|---|---|
| `NoSuchBeanDefinitionException` | Bean not scanned/imported, excluded by profile, wrong mock override | Component scan, `@Import`, `@Profile`, test slice |
| `NoUniqueBeanDefinitionException` | Multiple beans of same type without qualifier | `@Primary`, `@Qualifier`, named beans |
| `UnsatisfiedDependencyException` | Dependency chain failed to wire | Read deeper `Caused by` |
| `BeanCreationException` | `@Bean`/constructor/`@PostConstruct` threw | Check bean name, init method, nested cause |
| `BindException`/configuration bind errors | Missing/malformed/invalid property | Test profile, env vars, binding prefix |
| `IllegalArgumentException: Could not resolve placeholder` | Missing property | Root key, Spring config, env-specific properties |
| `PSQLException`, `ConnectException` | Wrong DB hostname/port/credentials/network | Container readiness, DB URL, firewall |
| `FlywayException`/Liquibase exception | Migration failed | SQL scripts, schema permissions, version |
| `BindException: Address already in use` | Fixed port already taken | Random port, resource lifecycle |
| Jackson/validation/linkage errors | Missing dependency or version conflict | Dependency tree, Boot BOM, Jakarta APIs |
| Security config startup failure | Missing keystore/cert/credential | Test security profile, secrets mapping |
| TLS/SSL handshake exceptions | Incompatible truststore/cert | TLS config/test server |
| `OutOfMemoryError` or resource exhaustion | JVM/container memory, too many contexts | Heap, cache size, test forks, lifecycle |

**This table is a diagnostic guide, not proof.** A `BeanCreationException` might stem from a DB connection timeout, and an `IllegalStateException` might just be a wrapper. Always read the actual cause chain and dependency graph before picking a fix.

### 8.3. Distinguishing Application Faults from Test Environment Faults

A `@SpringBootTest` can fail due to:
- Misconfiguration **in test sources**: `@MockBean` missing generics, wrong profile, test class outside scan package, `@DynamicPropertySource` returning the port of an unstarted container.
- Misconfiguration **in the real application**: missing `@ConfigurationProperties`, circular dependency, invalid bean name, broken migration.
- **Test-only** infrastructure: PostgreSQL container not ready, external API stub not started, Docker socket unavailable, localhost port occupied.
- Library/version mismatches: `javax.*` vs `jakarta.*` when upgrading Boot 2->3, driver and Hibernate mismatches.
- Resources **contaminated by an earlier test**: static state, global properties, shared cached context, incomplete cleanup.

Each group must be fixed where ownership resides. The context failure threshold merely reports that repeated loads for the same key were skipped; it **does not classify** the cause.

## 9. Why Is `@DirtiesContext` Not the Default Fix?

`@DirtiesContext` tells Spring to **evict and close the cached context**. It is appropriate when a test **dirtied a working context**, e.g., mutating singletons or configuration that cannot be reset safely.

However, if a context **never loaded successfully** due to a missing datasource property:
- There is no usable context whose state needs resetting.
- Marking it dirty does not supply the missing URL or fix the bean.
- Retrying a guaranteed-broken context wastes time and bloats logs.
- For external PostgreSQL/Kafka, closing the context does not even reset out-of-process data or resources.

**Do not assume `@DirtiesContext` resets a key's failure count.** In Spring 6.1, counters live in `ContextCache`; any effect of eviction depends on implementation and version. Never use this annotation as a "threshold reset button" when your goal is fixing the root cause.

### 9.1. A Wrong Example

~~~java
@SpringBootTest
@DirtiesContext
class OrderIntegrationTest {
    // If the DataSource cannot connect, the context still fails.
}
~~~

This is an illustrative snippet (not part of the runnable project). Adding the annotation can mask another issue or slow builds down, yet cannot fix a broken DB URL. Find the root exception.

### 9.2. A Valid Example

If a test mutates Spring-managed state so subsequent tests see tainted beans and no safe reset exists, `@DirtiesContext(methodMode=AFTER_METHOD)` can isolate the context after that method. Still, **that is a post-startup state issue**, distinct from **context loading failure thresholds**. Separate the two causes so you choose the right tool.

## 10. Failure Threshold Is Not Cache Size, Retry, or Circuit Breaker

| Concept | Setting / Function | Target |
|---|---|---|
| **Failure threshold** | `spring.test.context.failure.threshold`, default 1 | Number of real failed context loads allowed for the **same key** before skipping |
| **Context cache size** | `spring.test.context.cache.maxSize`, default 32 | Number of successfully loaded contexts retained in the LRU cache |
| **`@DirtiesContext`** | BEFORE/AFTER method/class phases | Evict/close a context when state becomes dirty |
| **JUnit retries/flaky test reruns** | Project-specific tool/plugin | Re-run test method/task per policy |
| **Spring Retry/Resilience4j** | Retry HTTP/DB/business operations | Application runtime behavior, not TestContext bootstrap |
| **Testcontainers readiness** | Wait strategies/startup attempts | External container lifecycle |
| **Gradle forks** | `maxParallelForks`, `forkEvery` | JVM test workers and cache isolation |
| **Spring Boot startup logging** | DEBUG/TRACE/test reports | Observability for each real load |

**`Threshold=1` does not mean "only 1 error is allowed in the whole suite."** It prevents cascading failed loads **per context configuration**. Similarly, "setting `cache.maxSize` to 64" will not make `NoSuchBeanDefinitionException` go away.

### 10.1. Example of a Suite with Two Root Causes

~~~text
Group K1 (profile=test, mock PaymentGateway):
  actual failure: missing paymentClient bean
  12 subsequent skips

Group K2 (profile=integration, Testcontainers PostgreSQL):
  actual failure: DB connection refused
  8 subsequent skips

Group K3 (unit slice with mocked repository):
  loads successfully and tests run
~~~

If you only grep `failure threshold exceeded` and assume a single root cause, you will fix K1 and then be surprised that K2 still fails. **Group by key first, then investigate each group's root cause.**

## 11. Special Context Key Pitfalls in Spring Boot Testing

### 11.1. `@ActiveProfiles`

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceTest {
    // Context key includes active profile "test".
}
~~~

If another class omits `@ActiveProfiles("test")`, they get different keys, and a test might fail only on profile `test` because the datasource URL comes from that profile's file. Each key has its own threshold counter.

**Do not change `@ActiveProfiles` just to turn tests green.** Profiles are test conditions; switching them can test an environment that does not represent the contract under verification.

### 11.2. `@SpringBootTest(properties=...)`

~~~java
@SpringBootTest(
        properties = "feature.mail.enabled=false")
class MailDisabledTest {
}
~~~

Inline properties become part of the merged configuration. If another class sets `feature.mail.enabled=true`, the context key differs and startup differs via conditional beans. If a property only needs to vary in one method, pick the right test context/fixture rather than assuming `System.setProperty` after startup reconfigures already-created beans.

### 11.3. `@MockBean` and `@TestConfiguration`

In Spring Boot 3.3, `@MockBean`/`@SpyBean` contribute to test context customizers, preventing two classes with different mocks from sharing a context even when both use `@SpringBootTest`. If startup fails solely due to broken mock setup, every class with identical overrides hits the corresponding threshold.

**Pure unit tests** do not need `@SpringBootTest` to create mocks. For logic independent of Spring wiring, JUnit + Mockito avoids context startup, cache keys, and failure thresholds altogether. Conversely, when testing auto-configuration or bean graphs, `@SpringBootTest` makes sense.

### 11.4. `@DynamicPropertySource` and Testcontainers

~~~java
@DynamicPropertySource
static void db(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.datasource.url",
            () -> postgres.getJdbcUrl());
}
~~~

This snippet assumes a started static `postgres` container and is not part of the runnable project in section 5. Spring TestContext includes `@DynamicPropertySource` metadata in cache keys, **not necessarily** treating every new runtime port as a separate key. If the next test class reuses a cached context after the previous container stopped, the connection pool still targets the old port and fails. That is a **resource/context lifecycle mismatch**—align scopes or separate contexts rather than raising the threshold.

**Testcontainers also has readiness wait strategies**: an unready container is an infrastructure root error. The failure threshold only stops Spring from rebuilding the context against an unreachable DB; it does not restart containers.

## 12. Limitations of Rerunning Single Tests to Find Errors

In many cases, rerunning **one test class** in a fresh JVM puts its actual load failure first, making it easy to read. However, there are at least four risks:

1. **Order-dependent pollution:** Test A leaves global state that breaks Test B. Running B alone fails to reproduce it. Inspect full-suite execution order.
2. **External resource races:** A port/broker/database is contended only during parallel CI. Running alone avoids contention and passes.
3. **Different context keys:** A standalone run may omit suite-level customizers, environment variables, or test platform settings; keep annotations/config equivalent.
4. **Gradle cached test results:** An `UP-TO-DATE` task may skip execution; pass `--rerun-tasks` when fresh verification is required.

**Advice:** Save artifacts from the **first failing CI run**, including XML test results, complete logs, and test environment metadata—not just a summary screenshot. After extracting the root cause, build the smallest reproduction **that still preserves the failing conditions**.

### 12.1. Which Log Levels Are Useful?

- `org.springframework.test.context.cache` at `DEBUG`: cache size/hits/misses/failure statistics; helps group keys and spot context churn.
- `org.springframework.test.context` or `org.springframework.beans.factory.support` at `DEBUG`: context/test listener/bean lifecycle; use selectively due to volume.
- `org.springframework.boot.autoconfigure.condition` and `--debug`/Condition Evaluation Report: helpful when `@Conditional`/auto-configuration omits a bean you expected.
- `org.testcontainers` at `INFO`/`DEBUG`: container startup/readiness; enable only when using containers.
- JDBC/migration logs: enable detailed levels only after narrowing the fault to the DB; mask credentials.

**Do not enable `TRACE` for all of Spring and HTTP clients unconditionally on CI**, as logs may expose secrets, PII, and headers while generating massive output. Start from the exception cause chain and enable targeted packages.

### 12.2. What Does Gradle `--stacktrace` Show?

`./gradlew test --stacktrace` usually prints the **Gradle task failure stack**, e.g., `There were failing tests. See report at ...`. That trace explains why the Gradle task failed, **not necessarily** the Spring test class's full exception. To see the root failure:
- Open the HTML/XML test reports.
- Configure Gradle `testLogging` for failed tests and full exception format if needed.
- Use `--info` or appropriate flags for diagnostic logs; `--debug` is not always mandatory.
- Collect raw stderr/stdout when CI aggregates logs.

**Example logging configuration during diagnosis:**

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'failed'
        exceptionFormat = 'full'
        showCauses = true
        showStackTraces = true
    }
}
~~~

This is an optional Gradle snippet; the runnable demo uses a concise event list in `testLogging`, while learners can switch to full logging while troubleshooting. Do not treat output with specific line numbers as fixed expected stdout, as it varies by Gradle/Spring/JDK version.

## 13. CI Investigation Workflow for Floods of Failure-Threshold Messages

**Step 1.** Confirm you are reading **the same CI run**. Do not stitch stack traces from two executions with different profiles or forks.

**Step 2.** Search for traces containing `Failed to load ApplicationContext` and `Caused by`. If you only see `failure threshold exceeded`, check the rest of the log/test XML or rerun a representative key in a **fresh JVM** to capture the real cause.

**Step 3.** Group by merged configuration:
- `classes`/Spring Boot main application.
- `activeProfiles`.
- `propertySourceProperties` and dynamic customizers.
- Mock overrides/test slices/context loaders.
- Parent context if using a hierarchy.

**Step 4.** From the actual load failure, extract **root cause + action**:
- `Could not resolve placeholder`: which property?
- `Connection refused`: which host/port, is the container ready?
- `NoSuchBeanDefinition`: missing component scan/import or active profile?
- `BeanCurrentlyInCreation`/circular dependency: which bean chain?
- Liquibase/Flyway migration failure: statement/schema/permissions?
- `BindException: Address already in use`: who holds the fixed port?

**Step 5.** Check external resource startup order, test profiles, Gradle JVM properties, CI secrets mapping, Spring Security/SSL config, and datasource URLs. Never log secret values to prove configuration.

**Step 6.** Fix the cause; run the representative test; then run the full suite with the same configuration, especially if multiple keys were involved.

**Step 7.** If failures occur only in parallel, isolate shared external resources, and use `@ResourceLock`/`@Isolated` only at the right scope—do not turn the failure threshold into a mutex.

**Step 8.** Once the suite passes, keep the default threshold and add an appropriate regression test/fixture guardrail so the error does not recur.

### 13.1. What Not to Do

- Do not permanently set `spring.test.context.failure.threshold=1000000` just to "clean skip messages out of the test report"; it produces more bootstrap errors instead.
- Do not add `@DirtiesContext` to every class that fails to load.
- Do not rewrite expected test assertions en masse when `@Test` bodies never executed.
- Do not assign root cause to whichever test class appears alphabetically first in XML reports.
- Do not swap profiles/`@MockBean` to switch into a context that no longer tests what is required.
- Do not leave Spring `DEBUG` enabled across CI indefinitely if secrets might leak.
- Do not clear static memory/caches inside a live test JVM while other tests actively use contexts without considering thread safety.
- Do not pass Gradle `--offline` when dependencies are missing; dependency resolution failures are not Spring `ApplicationContext` bootstrap failures.
- Do not claim "one test failed = the whole app is broken" when failures span distinct test keys, slices, or external resources.

## 14. Tricky Cases: Repeated Errors That Look Like Root Causes but Are Not

### 14.1. `BeanCreationException` Across Multiple Contexts

If Boot runs three slices—`@WebMvcTest`, `@DataJpaTest`, and `@SpringBootTest`—they typically have distinct keys. The same `BeanCreationException` across all three **might** stem from a shared broken test `@Configuration` or three independent bean graphs. Never assume a single context failure count is shared across all three slices.

### 14.2. First Context Load Succeeds, Then a Bean Fails During Test Execution

The failure threshold tracks **context loading** only. If context initialization succeeds and `@Test` throws `NullPointerException`, that is **not a context load failure** and triggers no threshold skips for that key. If a post-startup listener throws during another test phase, identify which lifecycle stage failed.

### 14.3. External Resource Recovers After Failure

With `threshold=1`, you may need a fresh test execution once an external resource recovers, because the failed load was already recorded for that key in the current JVM. That is an **intentional trade-off**: it eliminates wasted retries at the cost of not automatically retrying context loads for the same key if external conditions change mid-suite.

The reliable fix is not raising the threshold; prepare resources **before** Spring builds the context using readiness/wait strategies, proper lifecycle ownership, and sensible waits.

### 14.4. Parallel Tests and Non-Intuitive Log Ordering

When Jupiter/Gradle runs multiple worker JVMs, the first message in a **combined log file** may not correspond to the first attempt per key or worker. Track timestamps, test worker IDs, test classes, and config groupings whenever logs provide them. The context cache is static per JVM; each JVM maintains separate failure counts.

### 14.5. Failure Count Is Not Bean Constructor Call Count

A single actual context load attempt can instantiate **many beans**, perform internal bean initialization retries, or fail inside a `BeanFactoryPostProcessor` before an expected bean is even created. The **bean constructor counter** in our demo is merely instrumentation on a bean engineered to fail at init. In production, constructor invocation counts cannot replace Spring cache failure metrics.

## 15. Distinguishing Root-Cause Visibility from Framework Behavior

A single initial failure can be logged multiple times because:
- Spring's context loader logs the exception.
- JUnit reports the test preparation failure.
- The Gradle test task captures stderr.
- A CI uploader/summarizer posts the same error excerpt.

These are **multiple log copies of one actual failed load**, not multiple load attempts. Conversely, each `failure threshold exceeded` message represents **a separate failed test node** (one skipped attempt) without re-instantiating the broken bean.

When reporting an incident, separate these metrics:

| Metric | Meaning |
|---|---|
| Failed test cases | How many tests did not run/finish cleanly |
| Failing context keys | How many distinct configurations failed |
| Actual failed context loads | How many times the loader genuinely tried to initialize and failed |
| Preemptive skips | How many tests the threshold blocked from reloading |
| Actual root causes | May be fewer than or equal to the number of keys; requires analysis |
| Log messages | Not equal to attempt count, as logs get duplicated |

Reporting "30 red tests" without mentioning they all share one misconfigured test datasource misrepresents the blast radius. A good report says: "1 root cause: invalid test DB URL; context key had 1 actual load failure and 29 skipped attempts; fixed property, representative test and suite passed"—**reporting exact numbers only when measured from a real run**, not copied from an illustrative example.

## 16. Closer Look at the `TestContextManager` Harness

In the example code, `load(...)` executes:

~~~java
new TestContextManager(probeClass)
        .getTestContext()
        .getApplicationContext();
~~~

**Stage 1:** `TestContextManager` reads test class annotations: `@ContextConfiguration`, `@TestPropertySource`, and other metadata.

**Stage 2:** It constructs a `TestContext` with the corresponding `MergedContextConfiguration` and `CacheAwareContextLoaderDelegate`.

**Stage 3:** When `getApplicationContext()` is invoked, the framework checks the cache entry or evaluates the **failure count/threshold** before loading the context.

**Stage 4:** If loading fails, the exception propagates and JUnit `assertThrows` catches it. Once the same key reaches the threshold, the delegate immediately throws "skipping repeated attempt" **before running bean initialization**.

**Stage 5:** Thanks to the `AtomicInteger` counter in `BrokenAConfig`, we observe the bean factory method is not called a second time. This is **substantive evidence**, not guesswork from message strings alone.

**Why not annotate the probes with `@ExtendWith(SpringExtension.class)`?** The nested probe types contain no JUnit tests. They are **metadata-only classes**, and the harness creates the manager explicitly. Attaching `SpringExtension` directly to a `@Test` class with a broken context causes Spring to load before the test method runs, preventing `assertThrows` inside the test body from investigating it.

**Why set `spring.test.context.failure.threshold=1` in Gradle?** To keep the reproduction independent of a learner's global machine settings that might specify another threshold. In a production project, you can omit the explicit property to use the default. `configuredDefaultThresholdIsOneInThisTestWorker` proves only that the **worker property is 1**, not that every Spring Framework version shares that default; Spring 6.1 docs are the source for default semantics.

**Why temporarily switch the threshold in the sixth test?** To demonstrate that `2` allows two **actual failed load attempts across two separate calls**, rather than `getApplicationContext()` retrying twice internally. The test restores the system property in `finally` and runs the suite sequentially. This is a reproduction technique, not a recommendation to mutate JVM globals in applications.

## 17. Hands-On Exercises

**Exercise 1 — Read Exceptions by Layer.** Given a trace `Failed to load ApplicationContext` -> `UnsatisfiedDependencyException` -> `BeanCreationException` -> `IllegalArgumentException("payment.gateway.url missing")`, identify the root cause and affected bean.

**Exercise 2 — Default Threshold.** With 5 classes sharing key K and threshold 1, if the first load fails, how many actual failed attempts occur? How many are skipped? (Assume all five require the context without extra JVM forks.)

**Exercise 3 — Threshold=2.** With key K, three load calls would fail if actually executed; which are actual attempts and which are skipped? Explain using counters.

**Exercise 4 — Cache Keys.** Two classes share the same config class, yet one has `@TestPropertySource(properties="case.variant=alpha")` and the other has `beta`. Why are their failure counts independent?

**Exercise 5 — Healthy Context Reuse.** Use `assertSame` to verify two loads of the same successful key return the exact same context instance. Why is `getId()` insufficient proof?

**Exercise 6 — CI Report.** Take a Gradle `TEST-*.xml` from a real failing project and group failures by context key and root cause without exposing sensitive data.

**Exercise 7 — Gradle Worker.** Change a property in `application.properties` without passing `spring.test.context.failure.threshold` to the test worker JVM. Why might threshold behavior remain unchanged?

**Exercise 8 — Gradle CLI Forwarding.** Update `build.gradle` so `./gradlew test -Dspring.test.context.failure.threshold=2` forwards into the `Test` task. Verify from inside the test worker.

**Exercise 9 — Disabled Threshold.** Try a large value like `1000000` in a sandbox with an intentionally broken bean. What happens to actual attempts, logs, and runtime? Why not keep this value in CI?

**Exercise 10 — Multiple JVM Forks.** Run two Gradle forks with the same failing application configuration. Why can there be **two** root context attempts instead of one across the machine?

**Exercise 11 — Testcontainers Readiness.** Simulate a slow-starting database container where the context loads before the DB is ready. Is raising the threshold or adding a wait strategy the durable fix?

**Exercise 12 — `@DirtiesContext`.** A context fails to load due to a missing property. Why is dirtying the context not an appropriate fix? What if the context loads successfully, yet a singleton gets mutated?

**Exercise 13 — Missing Bean.** `NoSuchBeanDefinitionException` appears beneath `UnsatisfiedDependencyException`. Trace the root bean dependency path, `@Profile`, and component scan.

**Exercise 14 — Multiple Keys.** `WebMvcTest` passes, `DataJpaTest` fails to start, and `SpringBootTest` also fails on the datasource. Why can you not infer a single global failure count across all three?

**Exercise 15 — Broken Mock Override.** Temporarily remove `@MockBean` from a test class and observe the cache key change. Do not claim the test is fixed just because the class now boots with a different bean graph.

**Exercise 16 — Async Contamination.** One test modifies a system property and restores it late, causing another class's context load to fail. Write an isolation/serialization plan and check JUnit parallel mode.

**Exercise 17 — Cause Chain Helper.** Extend `causeMessages` to store each layer's class + message in an immutable list, masking credential strings instead of dumping `Throwable.toString()`.

**Exercise 18 — Classification.** Categorize root errors from a CI report into missing property, DB unavailable, bean graph, port conflict, migration, and corrupted test fixture; propose owners and fixes.

**Exercise 19 — Diagnostic Noise.** Distinguish 20 test failures, 1 context key, 1 actual failed load, 19 skips, and 50 duplicate log lines. Why does each count measure something different?

**Exercise 20 — Regression.** After fixing a root cause, add an appropriate guardrail test, run the representative test and full suite, and confirm threshold messages disappear without altering the default threshold.

## 18. Diagnostic Checklist Before Changing Config

1. Does the project use Spring Framework 6.1+? Spring Boot 3.3.5 does.
2. Does the error line say **`failure threshold`** or **`Failed to load ApplicationContext`**?
3. Did you capture the full exception chain rather than only Gradle's task failure summary?
4. Did you find the root cause for **each failing context key**?
5. Are there multiple keys due to profiles, mocks, test slices, property sources, or context hierarchies?
6. Did the JVM test worker actually receive `spring.test.context.failure.threshold`?
7. Did anyone raise the threshold arbitrarily to hide errors and slow CI down?
8. Are tests running across multiple JVM forks or CI shards, each with its own cache?
9. Is `@DirtiesContext` being misused to fix startup failures?
10. Does the failure genuinely occur during Spring context initialization rather than in the test body?
11. If a bean is missing, did you check scan/import/qualifier/profile before adding a mock?
12. If the DB fails, did you check connection/readiness/migration/URL/credentials **without printing secrets**?
13. If it fails only in the full suite, did you inspect shared state, parallel races, and global properties?
14. Are external resources stopping before a cached context reuses them?
15. Did you read test HTML/XML reports instead of assuming `--stacktrace` has everything?
16. Do logs include test class, JVM, profile, and context config metadata?
17. After fixing, did you run both a representative test and the full suite?
18. Does your conclusion separate root context failures, skipped attempts, and test failures?
19. Did you avoid claiming "ran Gradle and tests are green" when you only wrote sample code?
20. Is there a regression test/documentation for the root issue without prolonging the incident with log spam?

## 19. Official References

- [Spring Framework 6.1 — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/ctx-management/failure-threshold.html): policy since Spring 6.1, default 1, and JVM property.
- [Spring Framework 6.1 — Context Caching](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/ctx-management/caching.html): context cache key, static cache, LRU, DEBUG stats.
- [Spring Framework 6.1 — TestContext Framework](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework.html): loading, configuration, and test lifecycle mechanics.
- [Spring Framework 6.1 API — TestContextManager](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/context/TestContextManager.html): `getTestContext` and managing test contexts.
- [Spring Framework 6.1 API — TestContext](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/context/TestContext.html): `getApplicationContext` loading/retrieving cached contexts.
- [Spring Framework 6.1 API — CacheAwareContextLoaderDelegate](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/context/CacheAwareContextLoaderDelegate.html): threshold constants and context loader contract.
- [Spring Framework 6.1 API — DefaultCacheAwareContextLoaderDelegate](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/context/cache/DefaultCacheAwareContextLoaderDelegate.html): default cache and failure threshold.
- [Spring Framework 6.1 API — ContextCacheUtils](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/context/cache/ContextCacheUtils.html): retrieving failure threshold/cache size.
- [Spring Framework — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html): evicting/closing contexts, distinct from startup failures.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, testing slices, and TestContext.
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): properties and profiles in Spring Boot.
- [JUnit Jupiter 5 — User Guide](https://docs.junit.org/5.11.4/user-guide/): JUnit lifecycle, tests, and assertions.
- [Gradle — Test Java/JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): JVM test workers, test reports, and `Test.systemProperty`.
- [Gradle — Command Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--rerun-tasks`, `--info`, `--stacktrace`.

**Key takeaway:** `ApplicationContext failure threshold (1) exceeded` is usually **a secondary signal**: Spring TestContext tried loading the **same context cache key** and failed, so it **skips repeated attempts** for that key. Never "fix" the skip message by raising the threshold or adding `@DirtiesContext`; trace back to the **first actual failed load, read nested `Caused by` entries, and fix the underlying bean, property, or resource**. Spring Boot 3.3.5 / Spring Framework 6.1 defaults to `threshold=1`, tracked **per cache key within the test JVM**. Good testing and incident reporting separate **failed test cases**, **actual context load failures**, **preemptive skips**, and **root causes**, then verify the fix with both a representative test and the full suite.
