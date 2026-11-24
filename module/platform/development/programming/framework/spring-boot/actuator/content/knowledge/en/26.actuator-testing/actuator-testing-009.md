# Testing Meters with SimpleMeterRegistry and Isolating State Across Runs

Suppose a file import job needs to record the number of successfully imported records and its execution duration. A good test must prove that the right meter is updated with the right measurements. The test must also produce the same result when run alone, alongside other tests, or rerun within the same JVM.

`SimpleMeterRegistry` keeps measurements in memory and does not ship them to a monitoring system. Pass this registry into the object under test via its constructor, execute the business behavior, and read the measurements directly. That way the test uses real Micrometer meters with data it controls. [Micrometer Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)

## Choosing Measurements to Assert

| Meter | Meaning in Example | Values to Verify |
| --- | --- | --- |
| `Counter` named `import.records` | Total number of records reported as imported across successful runs. | `count()` increases by the number of records. |
| `Timer` named `import.duration` | Execution count and total duration, including executions that throw an exception. | `count()` and `totalTime(TimeUnit.MILLISECONDS)`. |

Both meters carry the `source=csv` tag in the test. When reading measurements, select by name, tags, and meter type. Two import runs might import five records in total. Then the counter increases by five and the timer counts two executions. If you need to count executions, you can use `Timer.count()` directly. [Counter](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html) · [Timer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html)

## Java and JUnit Example

The example uses Java 17 or later, Gradle, and Micrometer 1.13.0 from the Spring Boot 3.3.0 dependency catalog. Create the following three files in a separate test directory.

**`build.gradle`**

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'io.micrometer:micrometer-core'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed'
    }
}
```

**`src/main/java/demo/metrics/ImportJob.java`**

```java
package demo.metrics;

import java.util.function.IntSupplier;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class ImportJob {

    private final Counter importedRecords;
    private final Timer duration;

    public ImportJob(MeterRegistry registry, String source) {
        this.importedRecords = registry.counter("import.records", "source", source);
        this.duration = registry.timer("import.duration", "source", source);
    }

    public int run(IntSupplier importRecords) {
        return duration.record(() -> {
            int count = importRecords.getAsInt();
            if (count > 0) {
                importedRecords.increment(count);
            }
            return count;
        });
    }
}
```

`ImportJob` holds the registered meters in fields on the instance. `IntSupplier` represents the import operation and returns the number of imported records. If the operation throws an exception before returning a result, the counter remains unchanged. The timer still records one execution and the exception propagates to the caller.

**`src/test/java/demo/metrics/ImportJobTest.java`**

```java
package demo.metrics;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ImportJobTest {

    private MockClock clock;
    private SimpleMeterRegistry registry;
    private ImportJob job;

    @BeforeEach
    void setUp() {
        clock = new MockClock();
        registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        job = new ImportJob(registry, "csv");
    }

    @AfterEach
    void closeRegistry() {
        registry.close();
    }

    @Test
    void countsRecordsAndAccumulatesTheDurationOfTwoRuns() {
        assertEquals(0.0, records().count());
        assertEquals(0L, duration().count());

        assertEquals(2, job.run(() -> {
            clock.add(20, TimeUnit.MILLISECONDS);
            return 2;
        }));
        assertEquals(3, job.run(() -> {
            clock.add(30, TimeUnit.MILLISECONDS);
            return 3;
        }));

        assertEquals(5.0, records().count());
        assertEquals(2L, duration().count());
        assertEquals(50.0, duration().totalTime(TimeUnit.MILLISECONDS), 0.000001);
        assertNull(registry.find("import.records").tag("source", "json").counter());
    }

    @Test
    void timesAFailedRunWithoutCountingImportedRecords() {
        assertEquals(0.0, records().count());
        assertEquals(0L, duration().count());

        var failure = new IllegalStateException("invalid input");
        var thrown = assertThrows(IllegalStateException.class, () -> job.run(() -> {
            clock.add(7, TimeUnit.MILLISECONDS);
            throw failure;
        }));

        assertSame(failure, thrown);
        assertEquals(0.0, records().count());
        assertEquals(1L, duration().count());
        assertEquals(7.0, duration().totalTime(TimeUnit.MILLISECONDS), 0.000001);
    }

    private Counter records() {
        return registry.get("import.records").tag("source", "csv").counter();
    }

    private Timer duration() {
        return registry.get("import.duration").tag("source", "csv").timer();
    }
}
```

- **Create a new clock and registry in `@BeforeEach`.** The `ImportJob` instance is also recreated so its meter fields point to the current test's registry. Two calls within the same passing test share the registry to verify accumulation. The failure test starts fresh with zeroed measurements.
- **Control time with `MockClock`.** Pass the same clock into the registry and advance time right inside the measured operation. The timer observes the exact elapsed interval added. The test needs no `Thread.sleep` and does not depend on machine speed.
- **Look up registered meters.** Use `registry.get(...)` with tags and meter type so the test fails if the expected meter is missing. Use `registry.find(...)` when asserting that a meter does not exist. Calling `registry.counter(...)` during assertions can register a new counter on the fly and mask a missing-registration bug.
- **Close the registry owned by the test.** `@AfterEach` calls `close()` after each test. Starting from zero measurements comes from creating a fresh registry in `@BeforeEach`.

From the directory containing `build.gradle`, run the following command.

```bash
gradle test --tests demo.metrics.ImportJobTest
```

Expect both tests to pass. The success test verifies five records, two executions, and a total duration of 50 ms. The failure test verifies that no records were added, the timer recorded one execution of 7 ms, and the original exception was rethrown to the caller.

## Handling Shared State

**Global registry.** Calls such as `Metrics.counter(...)` use `Metrics.globalRegistry`, which is JVM-static state. When code accepts a registry via constructor, tests can supply a dedicated registry. If you must test legacy code that uses the global registry, isolate the run scope and call `Metrics.removeRegistry(registry)` to detach the temporary registry added by that test, then close that registry during cleanup. Avoid running tests in parallel when they modify the global registry because they can record into each other's measurements. [Micrometer Global Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)

**Spring-managed registry.** Spring Test can reuse the same context across tests that share identical configuration. In that case, the registry bean and objects holding meters persist across multiple tests. If a test intentionally shares a registry, read the count before the action and assert on the delta afterward. Use this approach only when the test controls every recording to that meter during the measurement window. [Spring Test Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)

**Clearing meter registrations.** `registry.clear()` removes meters from the registry. An object that already cached a `Counter` or `Timer` in a field still holds the old reference. If the goal is to rerun with clean state, recreate both the registry and the object using it together as shown in the example.

The tests above verify recording behavior and state isolation. Checking that metrics appear at `/actuator/metrics` or are shipped to a monitoring system requires running through Actuator configuration and the corresponding metrics exporter. [Metrics in Spring Boot Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
