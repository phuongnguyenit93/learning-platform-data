# Measuring Context Count, Suite Time, and Optimizing Shared Configuration

## 1. Practice Objective

When a JUnit test uses `@SpringBootTest`, Spring may have to scan components, create beans, bind properties, and start connection pools, HTTP filters, JPA, or message listeners. If each class uses a different configuration, the `ApplicationContext` can be loaded repeatedly even though the assertions take only a few milliseconds.

This lesson belongs to the **Integrated Practice** group, covering **Measuring context count, suite time, and optimizing shared configuration** in the **Spring Boot - testing** module. The goal is to accurately measure the **number of contexts actually created**, **cache hit/miss counts**, **Gradle Test task duration**, **JUnit testcase durations**, and **suite wall-clock time**; and then reduce startup overhead while preserving test isolation.

The example uses **Java 17+**, **Spring Boot 3.3.5**, **Spring Framework 6.1**, **JUnit Jupiter**, and compatible Gradle 8.x. The project includes a plain Java service, two Spring integration test classes sharing a context, one class with a different property, and test-only instrumentation. No Docker, database, or broker is required.

### What You Will Learn

- How Spring TestContext builds `MergedContextConfiguration` as a cache key.
- Static caching inside the test JVM; Gradle forks do not share caches.
- Default context cache max size of 32 entries and LRU eviction.
- The `org.springframework.test.context.cache` DEBUG logger and how to read `hitCount`/`missCount`.
- Why `@TestPropertySource`, `@MockBean`, `@DynamicPropertySource`, and `@DirtiesContext` affect reuse.
- Counting context creations with a singleton marker instead of inferring from cache misses.
- Measuring build wall time separately from Gradle `TestResult` and JUnit XML.
- Establishing a baseline, varying one variable at a time, benchmarking, and preserving test coverage/stability.
- Choosing unit tests or test slices instead of full `@SpringBootTest` when appropriate.
- Caveats around Testcontainers, context lifecycle, and parallel tests.

## 2. Distinguishing the Metrics

| Metric | Question Answered | Do Not Misinterpret As |
| --- | --- | --- |
| Context creations | How many context instances are loaded in one JVM? | Not the number of `@Test` methods |
| Cache `hitCount` | How many times did Spring find a matching context? | Not the number of passing tests |
| Cache `missCount` | How many lookups had no cached entry? | Not necessarily equal to new contexts created |
| Cache `size` | How many entries remain in the cache? | Not the total ever created |
| Cache `maxSize` | Storage limit for contexts | Not the number of contexts always needed |
| Gradle Test task elapsed | How long did the test task take? | Does not include full compilation and CI overhead |
| JUnit XML `time` | Testcase duration recorded by the runner | Not necessarily context refresh time |
| CLI wall time | From Gradle invocation until completion | Includes build setup/compile/test/report |
| CI workflow duration | How long until the job/shard finishes? | Includes queue/cache/upload time |
| Heap/GC/flaky rate | Does optimization introduce resource/race problems? | Cannot be ignored in exchange for a high hit rate |

If reporting “reduced from 10 to 4 contexts,” you must record the counting method, JVM PID, test set, cache/fork settings, and whether `@DirtiesContext` is used. A run with 4 Gradle workers and a subsequent run with 1 worker cannot have single-PID context counts compared directly.

## 3. How Does the Spring TestContext Cache Work?

```text
SharedOneTest ------> merged context key K1
                       cache MISS -> create Context #1

SharedTwoTest ------> merged context key K1
                       cache HIT  -> reuse Context #1

PropertyVariantTest -> merged context key K2
                       cache MISS -> create Context #2

Static ContextCache **in one test JVM**
  K1 => Context #1
  K2 => Context #2
```

Spring TestContext constructs a `MergedContextConfiguration` from `@ContextConfiguration` classes/locations/initializers, `@ActiveProfiles`, `@TestPropertySource`, resource base path, loader, parent context, and `ContextCustomizerFactory` customizers. Spring Boot `@MockBean`/`@SpyBean`, `@DynamicPropertySource` methods, and imports can all contribute to producing a distinct key.

**The test class name is not part of the cache key by default.** Two differently named classes with identical effective configuration can reuse the same context; conversely, two classes with the same intent that differ by one inline property can create two contexts.

The Spring Test cache is a **static variable inside the JVM**, not a Gradle build cache or an external cache. Different Gradle test JVM forks, modules, or CI jobs do not share static state.

## 4. Default Cache `size=32` and LRU

Spring Framework 6.1 defaults to `maxSize=32`. When there are more context keys than the limit, LRU eviction closes the least recently used context; a later test needing that key again will have to reload it.

JVM property:

```properties
spring.test.context.cache.maxSize=32
```

**Set this in the test worker JVM** via Gradle `Test.systemProperty`, not only on the Gradle daemon. Increasing from 32 to 64 only makes sense when logs/measurements show eviction and enough heap is available. Keeping many full contexts with Hikari pools, JPA, and Kafka threads can increase GC pressure/OOM risk and slow down the suite.

`hitCount`/`missCount` count lookups, not context creations. `size` is the number of currently live entries, excluding dirty or evicted contexts. This lesson uses a test-only bean marker to count context creations, then combines that with cache statistics for interpretation.

## 5. Enabling Cache Statistics

`src/test/resources/application-test.yml`:

```yaml
spring:
  main:
    web-application-type: none

logging:
  level:
    org.springframework.test.context.cache: DEBUG
```

Example **illustrative format, not actual stdout**:

```text
DefaultContextCache ... size = 2, maxSize = 32,
parentContextCount = 0, hitCount = 40, missCount = 2
```

The logger may emit multiple snapshots of cumulative counters; **do not sum multiple log lines**. Some very early cache lookups may not appear if the logging profile only takes effect after Boot initializes logging. When you need tracking from JVM startup, configure the logging backend before Spring context startup.

Enable `DEBUG` while diagnosing, and disable/reduce it in routine CI runs if logs grow too large; do not log test secrets or PII.

## 6. Runnable Project

```text
context-suite-lab/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/cachelab/
│   ├── ContextSuiteApplication.java
│   └── TotalsService.java
├── src/test/java/com/example/cachelab/
│   ├── ContextProbeConfig.java
│   ├── TotalsServiceUnitTest.java
│   ├── ReuseFirstTest.java
│   ├── ReuseSecondTest.java
│   └── VariantPropertiesTest.java
├── src/test/resources/application-test.yml
└── scripts/summarize_junit.py
```

The two Spring tests `ReuseFirstTest` and `ReuseSecondTest` use the exact same configuration K1. `VariantPropertiesTest` adds `@TestPropertySource` → K2. `TotalsServiceUnitTest` does not use Spring. Keeping all application and example classes in the same package lets Spring component scanning work cleanly.

## 7. Gradle Build

`settings.gradle`:

```groovy
rootProject.name = 'context-suite-lab'
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

    // Single worker JVM, allowing reuse of the static context cache.
    maxParallelForks = 1
    forkEvery = 0

    // Pass project property into the JVM running JUnit.
    systemProperty(
        'spring.test.context.cache.maxSize',
        providers.gradleProperty('contextCacheSize')
                 .orElse('32')
                 .get())

    reports {
        junitXml.required = true
        html.required = true
    }

    testLogging {
        events 'passed', 'failed', 'skipped'
        showStandardStreams = true
        exceptionFormat =
          org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }

    afterSuite { descriptor, result ->
        if (descriptor.parent == null) {
            long millis = result.endTime - result.startTime
            println(
                'TEST_SUMMARY ' +
                'cases=' + result.testCount +
                ' passed=' + result.successfulTestCount +
                ' failed=' + result.failedTestCount +
                ' skipped=' + result.skippedTestCount +
                ' elapsedMs=' + millis)
        }
    }
}
```

Explanation:

- `spring-boot-starter` is sufficient to create a Boot context without web or JPA infrastructure.
- `spring-boot-starter-test` provides Spring Test, JUnit Jupiter, Mockito, and AssertJ.
- `maxParallelForks=1` limits Gradle test workers; by default each `Test` task runs in a forked JVM.
- `forkEvery=0` prevents recycling the worker after each test class; `forkEvery=1` incurs heavy startup cost and eliminates cache reuse opportunities.
- `spring.test.context.cache.maxSize` is passed to the right test JVM via `Test.systemProperty`.
- `showStandardStreams=true` lets us observe `CTX_CREATED`; production CI should only enable verbose stdout when actually needed.
- The root `afterSuite` prints task-level counts and duration; **it does not measure context startup separately**.
- JUnit parallel execution is disabled in this lab to reduce race factors.
- Do not add `ignoreFailures=true` or `|| true` to produce fake green builds.

If the project does not yet include a Gradle Wrapper, `./gradlew`/`.\gradlew.bat` will not exist; generate a compatible Wrapper or use an installed Gradle 8.x.

## 8. Java Application and Real Service

`src/main/java/com/example/cachelab/ContextSuiteApplication.java`:

```java
package com.example.cachelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextSuiteApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContextSuiteApplication.class, args);
    }
}
```

`src/main/java/com/example/cachelab/TotalsService.java`:

```java
package com.example.cachelab;

import org.springframework.stereotype.Service;

@Service
public class TotalsService {
    public long totalCents(long price, int quantity) {
        if (price < 0 || quantity < 0) {
            throw new IllegalArgumentException(
                    "price and quantity must be non-negative");
        }
        return Math.multiplyExact(price, quantity);
    }
}
```

`TotalsService` can be tested with plain Java; the Spring tests are only meant to demonstrate bean wiring and caching, not because multiplication requires `@SpringBootTest`.

## 9. Test-Only Probe to Count Context Creations

`src/test/java/com/example/cachelab/ContextProbeConfig.java`:

```java
package com.example.cachelab;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class ContextProbeConfig {

    private static final AtomicInteger CREATED =
            new AtomicInteger();

    @Bean
    ContextMarker contextMarker() {
        int ordinal = CREATED.incrementAndGet();
        System.out.println(
                "CTX_CREATED pid=" +
                ProcessHandle.current().pid() +
                " ordinal=" + ordinal);
        return new ContextMarker(ordinal);
    }
}

record ContextMarker(int ordinal) {
}
```

Spring creates the `ContextMarker` singleton **once whenever a context importing this configuration is initialized**. When two classes reuse the same cached context, the existing bean is injected and the counter does not increment.

Limitations:
- The static counter lives only within **one test JVM**, so you must check the PID.
- Reloads after `@DirtiesContext` or eviction increment the ordinal.
- Contexts that do not import the probe are not counted.
- A context startup failure before the bean is created will not print the marker.
- Test class execution order is not fixed; **do not assert that the ordinal must equal 1 or 2**.
- A top-level `@TestConfiguration` is not picked up by Boot scanning like production config; tests must explicitly `@Import` it.
- The marker counts context instances, not refresh duration. For detailed timings, use Spring `ApplicationStartup`, JFR, or an appropriate profiler.

## 10. Unit Tests Without an ApplicationContext

`src/test/java/com/example/cachelab/TotalsServiceUnitTest.java`:

```java
package com.example.cachelab;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TotalsServiceUnitTest {

    private final TotalsService service = new TotalsService();

    @Test
    void computesWithoutSpringContext() {
        assertEquals(600L, service.totalCents(200, 3));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.totalCents(-1, 2));
    }
}
```

Both tests load no Spring context and can run very quickly. When a service only contains pure logic, this is usually the right test level. Reserve Spring integration tests for behaviors such as bean wiring, profiles, transactions, filters, and external integrations.

## 11. Shared Spring Configuration K1: First Class

`src/test/java/com/example/cachelab/ReuseFirstTest.java`:

```java
package com.example.cachelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = ContextSuiteApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@Import(ContextProbeConfig.class)
class ReuseFirstTest {

    @Autowired TotalsService service;
    @Autowired ContextMarker marker;

    @Test
    void calculatesWithSpringBean() {
        assertEquals(240L, service.totalCents(120, 2));
    }

    @Test
    void receivesContextMarker() {
        assertTrue(marker.ordinal() > 0);
    }
}
```

These are 2 `@Test` methods. Key K1 captures the application class, `NONE` web environment, `test` profile, and imported configuration.

## 12. Shared Spring Configuration K1: Second Class

`src/test/java/com/example/cachelab/ReuseSecondTest.java`:

```java
package com.example.cachelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = ContextSuiteApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@Import(ContextProbeConfig.class)
class ReuseSecondTest {

    @Autowired TotalsService service;
    @Autowired ContextMarker marker;

    @Test
    void handlesZeroQuantity() {
        assertEquals(0L, service.totalCents(120, 0));
    }

    @Test
    void usesValidMarkerInstance() {
        assertTrue(marker.ordinal() > 0);
    }
}
```

These are 2 `@Test` methods. The effective configuration matches the first class, so K1 can be reused in the same test JVM if the context is still cached. Do not use static fields to exchange markers between classes, as that makes tests depend on execution order.

## 13. PropertyVariantTest: Adding a Property Creates K2

`src/test/java/com/example/cachelab/PropertyVariantTest.java`:

```java
package com.example.cachelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = ContextSuiteApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@Import(ContextProbeConfig.class)
@TestPropertySource(properties = "lab.variant=extra")
class PropertyVariantTest {

    @Autowired TotalsService service;
    @Autowired ContextMarker marker;
    @Autowired Environment environment;

    @Test
    void seesAdditionalProperty() {
        assertEquals(
                "extra",
                environment.getProperty("lab.variant"));
    }

    @Test
    void stillUsesRealService() {
        assertEquals(1000L, service.totalCents(250, 4));
        assertTrue(marker.ordinal() > 0);
    }
}
```

These are 2 `@Test` methods. The class still uses the `test` profile, but its **different `@TestPropertySource`** yields key K2. A project running these 3 Spring test classes in the same JVM, with a cache large enough for K1/K2 and no `@DirtiesContext`, is expected to have **two context creations**—though that is an expectation, not an observed measurement.

## 14. Method Inventory and How to Interpret It

| Class | `@Test` methods | Context |
| --- | ---: | --- |
| TotalsServiceUnitTest | 2 | None |
| ReuseFirstTest | 2 | K1 |
| ReuseSecondTest | 2 | K1 |
| PropertyVariantTest | 2 | K2 |
| **Total** | **8** | 3 Spring classes |

**8 `@Test` methods** are counted from source code, which does not mean “8 tests PASSED.” There are no parameterized tests. If the JUnit task fails during compilation or dependency resolution, XML reports may not even be generated. You only obtain actual results after running the suite and reading the reports.

## 15. Running the Suite with Default Cache

Linux/macOS:

```bash
./gradlew --no-daemon clean test \
  -PcontextCacheSize=32 --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat --no-daemon clean test -PcontextCacheSize=32 --console=plain
```

After running:
1. Search the output for `CTX_CREATED pid=... ordinal=...`.
2. Look for `org.springframework.test.context.cache` DEBUG stats.
3. Read `TEST_SUMMARY cases=... passed=... failed=... skipped=... elapsedMs=...`.
4. Open the Gradle HTML report at `build/reports/tests/test/index.html`.
5. Inspect JUnit XML reports at `build/test-results/test/TEST-*.xml`.

Each piece of evidence has a different scope. Do not sum multiple cache lookup snapshots to get the context count, and do not report Gradle Test task elapsed time as total build time.

## 16. Measuring Wall Clock Time While Preserving Error Exit Codes

Bash:

```bash
set -o pipefail
/usr/bin/time -p ./gradlew --no-daemon clean test \
  -PcontextCacheSize=32 --console=plain 2>&1 |
  tee suite-context.log
```

`set -o pipefail` prevents `tee` from masking Gradle's exit status. Keep the log outside `build` so `clean` does not delete it.

PowerShell:

```powershell
$sw = [System.Diagnostics.Stopwatch]::StartNew()
& .\gradlew.bat --no-daemon clean test -PcontextCacheSize=32 --console=plain
$code = $LASTEXITCODE
$sw.Stop()
Write-Host ("SUITE_WALL_MS=" + $sw.ElapsedMilliseconds)
exit $code
```

The shell stopwatch includes build setup, compilation, test execution, and reporting—not just context cold starts. If tests are skipped via `UP-TO-DATE`, the measurement is not comparable to a full run.

## 17. Reading JUnit XML to Find Slow Cases

Create `scripts/summarize_junit.py`:

```python
#!/usr/bin/env python3
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

files = sorted(
    Path("build/test-results/test").glob("TEST-*.xml")
)
if not files:
    print("No JUnit XML found; check test task execution.")
    sys.exit(2)

cases = []
fail_count = 0
skip_count = 0

for file in files:
    try:
        root = ET.parse(file).getroot()
    except ET.ParseError as error:
        print(f"Invalid report {file}: {error}")
        sys.exit(2)

    for case in root.iter("testcase"):
        seconds = float(case.get("time", "0") or "0")
        clazz = case.get("classname", file.stem)
        name = case.get("name", "unknown")
        failure = (
            case.find("failure") is not None
            or case.find("error") is not None
        )
        skipped = case.find("skipped") is not None
        cases.append((seconds, clazz, name))
        fail_count += int(failure)
        skip_count += int(skipped)

print("XML_FILES=", len(files))
print("TESTCASES=", len(cases))
print("FAILED_OR_ERROR=", fail_count)
print("SKIPPED=", skip_count)
print(
    "REPORTED_CASE_SECONDS_SUM=",
    round(sum(row[0] for row in cases), 3),
)
print("SLOWEST_CASES:")
for seconds, clazz, name in sorted(cases, reverse=True)[:10]:
    print(f"{seconds:.3f}s {clazz}#{name}")
```

Run it:

```bash
python3 scripts/summarize_junit.py
```

**This script does not measure context count or total wall time**; the sum of testcase durations recorded in XML does not necessarily include context startup and can exceed wall-clock time when tests run in parallel. If XML files are missing because `compileTestJava` failed, the script reports missing reports—you cannot conclude zero test failures.

## 18. Controlled Experiments

### A: cache size 32

```bash
./gradlew --no-daemon clean test -PcontextCacheSize=32 --console=plain
```

Expect 2 context keys K1/K2 in the lab, with no eviction needed at `maxSize=32`, assuming no other config differences are introduced. Read the markers and DEBUG logs to verify.

### B: cache size 1

```bash
./gradlew --no-daemon clean test -PcontextCacheSize=1 --console=plain
```

Interleaving K1/K2 can trigger eviction and reload. However, if the run order is `K1 → K1 → K2`, there may still be only two creations; if `K1 → K2 → K1`, there may be three. **Do not hardcode the expected context creation count from `maxSize` without knowing class execution order.**

### C: Making configurations differ

In a sandbox, add `@TestPropertySource(properties="lab.variant=other")` to `ReuseSecondTest` and rerun; it will no longer share key K1. Revert afterward and compare results.

### D: Testing `@DirtiesContext`

In a sandbox only, annotate one class with `@DirtiesContext(classMode=AFTER_CLASS)`. If a subsequent class needs that invalidated key again, Spring reloads it. The outcome depends on execution order; do not treat `@DirtiesContext` as a substitute for tuning cache `maxSize`.

**Change only one variable per experiment.** Record the same test set, JDK/Gradle versions, forks, CPU/RAM, and executed test count.

## 19. Sources of Cache Key Fragmentation

| Difference | Impact |
| --- | --- |
| Different `@ActiveProfiles` | May produce a different cache key |
| Different `@TestPropertySource` | Inline property locations/values participate in the key |
| Different `@SpringBootTest(properties=...)` | Different Boot config metadata |
| Different `@MockBean` or `@SpyBean` | Different TestContext customizers |
| Different `@DynamicPropertySource` methods | Context customizers may differ |
| Per-class nested `@TestConfiguration` | Different configuration class identities |
| Different `@Import` | Different bean/configuration scope |
| `@WebMvcTest` vs `@SpringBootTest` | Different slice vs full context |
| `RANDOM_PORT` vs `NONE` | Different web environment |
| `@DirtiesContext` | Not just a key change; invalidates the context |
| Different test class name | Does not create a new key by itself |
| Different Gradle fork | Static cache lives in a completely different JVM |

**Do not force all configs to match if the business contract requires differences.** An integration test using a dedicated test profile to disable a real scheduler or apply separate DB isolation should not drop that profile just to chase a higher cache hit rate.

## 20. `@MockBean` and Shared Configuration

In Spring Boot 3.3, `@MockBean` creates or replaces a bean in the `ApplicationContext`; the set of mocked beans becomes a context customizer. Two classes mocking different collaborators may require two separate contexts. Avoid building a mega-configuration with dozens of mocks just to force them onto one shared context.

Boot resets `@MockBean` according to the test lifecycle—by default after each method—but **resetting a mock does not delete SQL rows, Kafka messages, Redis keys, or other singleton state**. When sharing a context, test data must be cleaned up at the appropriate layer.

For pure service logic, use JUnit + `MockitoExtension` without Spring. For MVC, use `@WebMvcTest` with mocked controller collaborators. Use full `@SpringBootTest` integration tests when broad wiring is genuinely needed.

## 21. `@DirtiesContext` and Cleanup

`@DirtiesContext` closes the context and removes it from the cache. Use it when a test mutates bean definitions or corrupts singleton state that cannot be safely reset. If only DB fixtures are involved, you should generally use transaction rollback or namespace-scoped cleanup rather than rebuilding the whole application context.

Do not blindly remove `@DirtiesContext` everywhere to optimize speed: it may be masking or protecting against a real state leak. Find the source of the leak and design an equivalent reset or ownership boundary first.

During parallel execution, one thread invalidating a context can break another thread currently using it. Do not enable JUnit parallel execution for classes that use `@DirtiesContext` or unisolated shared mocks/DB state.

## 22. `@DynamicPropertySource` and Testcontainers

A test using `PostgreSQLContainer` may register a JDBC URL like this:

```java
@DynamicPropertySource
static void database(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
}
```

**This is an extension snippet**; it requires declaring `PostgreSQLContainer<?> postgres` with the proper imports, Testcontainers dependencies, and lifecycle, and is not part of the lab project.

Risks:
- `@DynamicPropertySource` methods act as context customizers and can fragment the cache.
- A static JUnit `@Container` per class may be stopped after that class finishes while the Spring context remains cached and holds a `DataSource` pointing at the old port.
- Boot 3.3 `@ServiceConnection` reduces manual connection boilerplate but does not automatically align container and context lifetimes.
- A shared DB still needs schema/row namespaces and cleanup; context caching does not provide data isolation.
- The official Testcontainers JUnit Jupiter extension does not support parallel test execution within `@Testcontainers`; do not use `@Execution(CONCURRENT)` on a `@Testcontainers` class as a supported benchmarking pattern.

Align container lifetime with context lifetime, or use per-class context invalidation when genuinely necessary, then measure again.

## 23. Gradle Forks, Parallel Threads, and Multi-Module Builds

`maxParallelForks=1` lets classes sharing the same Spring configuration reuse the cache. `maxParallelForks=4` spawns multiple test JVMs, each loading its own contexts independently; sometimes total wall time drops thanks to parallel throughput while memory usage and context startup counts increase. `forkEvery=1` usually eliminates cross-class reuse and pays repeated JVM startup costs. JUnit `parallel.enabled=true` is **thread-level concurrency within one JVM**, distinct from Gradle process forks.

Multiple Gradle Test tasks, modules, or CI shards also do not share a static Spring cache. When aggregating results, group logs by worker PID, task/module, and JUnit report. Never take cache stats from one worker and attribute them to the entire pipeline.

## 24. Optimizing in the Right Order

1. **Define scope**: task(s), test classes, JDK/Gradle/Boot versions, CI resources.
2. **Measure baseline**: marker creations/PID, cache stats, wall time, task elapsed time, JUnit counts.
3. **Locate the bottleneck**: context startup, SQL, network, fixtures, compilation, or GC?
4. **Move unit-style tests off `@SpringBootTest`** when Spring is unnecessary.
5. **Use slices** such as `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, and `@RestClientTest` matching the contract.
6. **Standardize configs** for groups of tests that truly share intent: profiles, imported `TestConfiguration`, mock policy.
7. **Reduce `@DirtiesContext`** only after safe state cleanup is in place.
8. **Align Testcontainers lifecycles** with context reuse.
9. **Tune `maxSize`/forks/parallelism** when measurements prove benefit and memory is sufficient.
10. **Run the full suite** verifying coverage, pass/failed/skipped counts, and flaky rate do not degrade.

One heavy cached full context can still be slower than three lightweight slices. The goal is the **right total cost**, not minimizing context count at any expense.

## 25. Spring Framework 6.1 Failure Threshold

Spring TestContext 6.1 has a default context failure threshold of **1**. If loading a context for key K fails once, subsequent classes requiring K can fail fast without attempting another full startup.

Property name:

```properties
spring.test.context.failure.threshold=1
```

When investigating, distinguish the root `Failed to load ApplicationContext` error from subsequent `ApplicationContext failure threshold exceeded` errors. Never mistake a fail-fast failing suite for a “context optimization,” and do not raise the threshold to hide bean, config, or DB startup failures.

## 26. Pre- and Post-Optimization Checklist

- [ ] Same code revision, JDK, Gradle, Spring Boot, and test task selection?
- [ ] Same testcase counts for executed, passed, failed, and skipped?
- [ ] Marker count per PID and cache stats recorded?
- [ ] Cache `maxSize` passed into the test worker JVM?
- [ ] Gradle test task time distinguished from total wall-clock time?
- [ ] JUnit XML time not treated as an exact context startup timer?
- [ ] Differences in `@TestPropertySource`/`@MockBean`/`@DynamicPropertySource` investigated?
- [ ] `@DirtiesContext` kept only where the context truly becomes dirty?
- [ ] Unit tests running without Spring where appropriate?
- [ ] Slices still protecting MVC/JPA/JSON/security contracts?
- [ ] Filters/auth not disabled and integration coverage not dropped just for speed?
- [ ] Databases/topics/Redis/filesystems using test-specific namespaces?
- [ ] Testcontainers context/container lifecycle controlled?
- [ ] Unsupported extension parallelism or shared mock races avoided?
- [ ] Memory/GC checked before increasing cache size or forks?
- [ ] Multiple samples run, comparing median and variance?
- [ ] Regression QA and rollback plan in place?
- [ ] No claim that tests PASSED without actually running them?

## 27. Official Documentation

- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): keys, static cache, size 32, LRU, and DEBUG logging.
- [Spring Framework 6.1 — ContextCache Javadoc](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/test/context/cache/ContextCache.html): hits/misses/size.
- [Spring Framework — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/failure-threshold.html): default failure threshold of 1.
- [Spring Framework — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html): invalidation.
- [Spring Framework — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html): safety with shared state.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@TestConfiguration`, slices.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection`.
- [Testcontainers JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Container` lifecycle, parallel extension limitation.
- [Gradle — Testing in Java/JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): test worker forks, reports, logging.
- [Gradle — Performance](https://docs.gradle.org/current/userguide/performance.html): task profiling and parallel tuning.
- [JUnit Jupiter](https://junit.org/junit5/docs/current/user-guide/): lifecycle and parallel execution.
- [Python ElementTree](https://docs.python.org/3/library/xml.etree.elementtree.html): XML parsing.

## 28. Conclusion

**Optimizing a Spring Boot test suite must be grounded in two kinds of evidence: context lifecycle and execution timing.** The Spring TestContext cache is static per JVM, keyed by merged configuration, and defaults to 32 contexts with LRU eviction. Profiles, inline properties, mocks, dynamic properties, `@DirtiesContext`, and Gradle forks can all affect reuse.

This Java 17+/Boot 3.3.5 project demonstrates **8 `@Test` methods**: two Spring-free unit tests, two classes sharing K1, and one class with K2 due to an inline property. The `ContextMarker` bean lets you observe context creations per JVM, while the Gradle summary, JUnit reports, and shell stopwatch measure different time scopes. This is reference code, **not a claim that Gradle/JUnit passed without running them**.

An optimization succeeds only when fair measurements show lower wall time or resource cost **and** all business/integration assertions, test isolation, and pass/fail/skip counts remain protected.
