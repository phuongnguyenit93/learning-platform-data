# Understanding @AutoConfigureObservability and Auto-Configuration Behavior in Tests

> Scope: Spring Boot 3.3.x, Java 21, JUnit Jupiter, and Micrometer managed by Spring Boot. The configurations below are standalone learning examples; they are not a requirement to change configuration across every project.

## 1. What Does the Test Need to Observe?

Suppose an order-processing operation has been instrumented with observability code. When running the application, you want to know how often the operation runs, how long it takes, and where it sits in a call chain. When testing, you may only want to confirm the observation name and tags; you may want to check how Spring wires the beans; or you may need to prove that data reaches a collector.

Those three goals require three different test levels. Before adding annotations, write down clearly what you need to prove:

| Goal | Evidence to Check | Suitable Environment |
| --- | --- | --- |
| Business code creates the right observation | Name, tags, start/stop lifecycle | Unit test with TestObservationRegistry |
| Spring configuration wires components properly | Beans and recorded entries in the registry | Test with an ApplicationContext |
| Data is exported outward | Data actually received by a test collector | Integration test with a test-controlled collector |

For example, asserting that a bean exists only answers a configuration question. It does not yet answer whether data has actually been sent and received.

## 2. Components to Identify

Observability helps reveal a system's internal state through signals such as logs, metrics, and traces. In this lesson, the focus is Micrometer observations, metrics, and tracing. Spring Boot helps wire them together via auto-configuration. [Spring Boot 3.3 Observability Documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

| Component | Role in Tests |
| --- | --- |
| Observation | A single execution of an observed operation |
| ObservationRegistry | Where observation handling is configured |
| ObservationHandler | Receives observation lifecycle events and handles them accordingly |
| MeterRegistry | Holds meters, such as Counter and Timer |
| Tracer | API for working with tracing spans |
| Exporter or sender component | Ships signals to a collector system |

Observations emit events; registered handlers decide how events are turned into metrics or traces. Therefore, simply instantiating an ObservationRegistry is not enough to prove that metrics or trace data exist. [Micrometer 1.13 Observation Mechanism](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

A SimpleMeterRegistry keeps metrics in memory and does not automatically ship them outward. It is a useful tool for checking measurement results without a monitoring system. [MeterRegistry and SimpleMeterRegistry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html).

## 3. What Does the Annotation Change?

The annotation has the full name:

```java
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
```

It is placed on test classes and enables observability auto-configuration support. In Spring Boot 3.3, both of the following attributes default to true:

```java
@AutoConfigureObservability(metrics = true, tracing = true)
```

metrics and tracing express whether reporting metrics or traces to external systems is permitted in tests. They do not mean that export libraries are automatically downloaded, a collector is automatically started, or all configuration conditions are bypassed. [AutoConfigureObservability 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/actuate/observability/AutoConfigureObservability.html).

Consider the annotation alongside the test type:

| Case | Behavior to Remember in Spring Boot 3.3 |
| --- | --- |
| Plain @SpringBootTest | Restricts auto-configuration of non-in-memory registries and trace-reporting components |
| @SpringBootTest with @AutoConfigureObservability | Re-enables auto-configuration of reporting components if dependencies, properties, and bean conditions match |
| Slice test with @AutoConfigureObservability | Provides an in-memory MeterRegistry, an ObservationRegistry, and a no-op Tracer when the required classes are present |

No-op means the component satisfies the interface without performing real trace recording. In particular, adding the annotation to a slice test does not turn it into an export test. [Spring Boot 3.3 Metrics and Tracing Testing Rules](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.tracing).

## 4. How to Reason About Auto-Configuration

When results differ from expectations, check in order:

1. **Test type:** are you loading the full application configuration or a slice?
2. **Dependencies:** are the observation API, registry, tracing bridge, and required exporter actually on the classpath?
3. **Test opt-in choices:** is the annotation present, and how are metrics/tracing set?
4. **Configuration conditions:** do properties, exclusions, or custom-declared beans change the outcome?
5. **Behavior:** did the operation run, did the observation finish, and does the evidence you assert belong to the right layer?

This is a diagnostic sequence. It helps avoid changing dependencies when the root cause is simply using a test type that does not load the configuration under test.

### Limits of metrics = false and tracing = false

The following configuration is suitable for stating an intent not to enable external reporting mechanisms in the test:

```java
@AutoConfigureObservability(metrics = false, tracing = false)
```

Do not conclude that every Counter, Timer, or ObservationRegistry disappears. Measuring in memory and shipping externally are two different things. Also check custom-declared beans: the annotation is not a network blocker for every piece of code in the application.

An application-declared bean can use @ConditionalOnEnabledTracing to participate in the tracing enablement condition. This conditional annotation checks management.tracing.enabled and also matches when the property is unset. [ConditionalOnEnabledTracing 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/tracing/ConditionalOnEnabledTracing.html).

## 5. Standalone Experiment: Comparing Default Configuration and Annotated Configuration

The example below uses two test classes and a shared configuration. No HTTP server or external collector is needed. The tracingModeProbe bean is just a marker to inspect the tracing condition, not an exporter or tracer.

### 5.1. Gradle Configuration

In a separate practice project, use the following build.gradle. JDK 21 and a compatible Gradle version are required; you can use Gradle Wrapper 8.5 prepared for that project.

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    testImplementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.micrometer:micrometer-observation-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This project is only for running tests, so it needs neither the Boot application packaging plugin nor a main method. Dependencies without explicit versions are managed through the selected BOM.

### 5.2. Shared Configuration

File src/test/java/example/ObservabilityTestApplication.java:

```java
package example;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.actuate.autoconfigure.tracing.ConditionalOnEnabledTracing;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration
@EnableAutoConfiguration
class ObservabilityTestApplication {

    @Bean
    @ConditionalOnEnabledTracing
    String tracingModeProbe() {
        return "tracing-condition-matched";
    }
}
```

### 5.3. Default Test Still Measures in Memory

File src/test/java/example/DefaultObservabilityTest.java:

```java
package example;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = ObservabilityTestApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class DefaultObservabilityTest {

    @Autowired
    ObservationRegistry observations;

    @Autowired
    MeterRegistry meters;

    @Autowired
    ApplicationContext context;

    @Test
    void recordsLocalMetricWithoutEnablingTracingReporting() {
        assertThat(context.containsBean("tracingModeProbe")).isFalse();

        String name = "lesson.default.work";
        Timer existing = meters.find(name).timer();
        long before = existing == null ? 0L : existing.count();

        Observation.createNotStarted(name, observations)
            .observe(() -> {
                int result = 6 * 7;
                assertThat(result).isEqualTo(42);
            });

        Timer recorded = meters.get(name).timer();
        assertThat(recorded.count()).isEqualTo(before + 1L);
    }
}
```

The measurement is checked after observe finishes. Using the count delta instead of assuming the total is always 1 makes the test less sensitive to data already present in the registry. Timer provides both recording count and duration; this test intentionally chooses count as stable evidence. [Timer Semantics](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

### 5.4. Re-enabling Observability Opt-In for Integration Tests

File src/test/java/example/OptInObservabilityTest.java:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = ObservabilityTestApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@AutoConfigureObservability
class OptInObservabilityTest {

    @Autowired
    ApplicationContext context;

    @Test
    void permitsTheTracingConditionToMatch() {
        assertThat(context.containsBean("tracingModeProbe")).isTrue();
        assertThat(context.getBean("tracingModeProbe", String.class))
            .isEqualTo("tracing-condition-matched");
    }
}
```

Run from the practice project directory on Windows:

```powershell
.\gradlew.bat test --tests 'example.DefaultObservabilityTest' --tests 'example.OptInObservabilityTest'
```

Expected result: both test methods pass. The first class proves that local metering works in a default test; the second proves that the probe bean's condition is allowed to match when the annotation is present. There are no tracing dependencies or collectors in the example, so you must not conclude that a span was exported.

This is test code run with Gradle/JUnit, not a standalone program compiled with javac. Do not treat the entire startup log as standard stdout, because logs also depend on the environment.

## 6. When You Only Need to Test a Single Observation

Suppose the goal is to test the observation contract: right name, right tags, and proper completion. You can skip loading Spring by creating a TestObservationRegistry for each test.

File src/test/java/example/ObservationContractTest.java, using the same Gradle configuration above:

```java
package example;

import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistryAssert;
import org.junit.jupiter.api.Test;

class ObservationContractTest {

    @Test
    void observesACompletedCalculation() {
        TestObservationRegistry registry = TestObservationRegistry.create();

        Observation.createNotStarted("lesson.calculation", registry)
            .lowCardinalityKeyValue("operation", "multiply")
            .observe(() -> {
                int answer = 6 * 7;
                if (answer != 42) {
                    throw new IllegalStateException("Unexpected result");
                }
            });

        TestObservationRegistryAssert.assertThat(registry)
            .doesNotHaveAnyRemainingCurrentObservation()
            .hasObservationWithNameEqualTo("lesson.calculation")
            .that()
            .hasLowCardinalityKeyValue("operation", "multiply")
            .hasBeenStarted()
            .hasBeenStopped();
    }
}
```

Run separately:

```powershell
.\gradlew.bat test --tests 'example.ObservationContractTest'
```

Expected result: one test passes. A fresh registry is created inside the method so data from other test runs is not used as evidence. This test checks the Observation contract, not Spring's auto-configuration choices or data shipping. The utilities and assertion chain are provided by micrometer-observation-test. [Testing Observations with Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/observation/testing.html).

## 7. When to Move to Testing a Real Collector?

Only raise the test level when the requirement is to verify the data pipeline. When doing so, prepare the full registry or tracing bridge libraries, the appropriate exporter, a test collector endpoint, and the necessary properties. Put the collector under the test's control and assert on the data it receives.

If export is batched or asynchronous, await a bounded condition—such as the collector having received a signal bearing the test's distinct name and tags. Sleeping a fixed number of milliseconds and declaring success does not prove that data shipping completed.

Pick unique markers for test data to avoid confusion with data from earlier runs. With tracing you also need to control sampling; with metrics you need to understand the publishing interval or scraping mechanism. A passing test is meaningless if it never inspected the receiving side.

## 8. Common Misconceptions

| Symptom or Inference | What to Re-check |
| --- | --- |
| Annotation is present but no data appears in the collector | Verify test type, libraries, configuration conditions, and receiving-side data; do not check only beans |
| A Tracer exists so real traces must be produced | Check whether it is a no-op tracer in a slice test |
| metrics = false means every Timer must disappear | Separate local measurement from external reporting |
| TestObservationRegistry already proves Boot configuration is right | It only proves the code using that registry; you need a context test to verify configuration |
| Tests occasionally get wrong counts | Check shared registries, parallel test execution, and duplicate meter names |
| Measured durations do not match a fixed value | Pick assertions suited to the goal; do not use machine latency as a business contract |
| Probe bean test passed so the exporter is running | Inspect the collector's received data directly before drawing that conclusion |

## 9. Hands-On Practice

1. Run the two configuration tests in section 5 and explain why the difference in the probe bean does not mean all metrics exist or are absent.
2. Change OptInObservabilityTest to @AutoConfigureObservability(metrics = false, tracing = false). Update the probe bean expectation to absent, then re-test.
3. Change the operation tag in ObservationContractTest's code while keeping the assertions unchanged. Identify which assertion catches the contract mismatch.
4. If a new requirement is to prove a collector received data, write down the collector-side evidence needed and the components missing from the current example.

You have mastered this lesson when you can choose the right test level, predict the annotation's role by test type, and make only conclusions that your assertions actually prove.
