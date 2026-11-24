# Avoiding Duplicate Recording When Operations Are Already Auto-Instrumented

## 1. The Problem Begins with One Operation Having Multiple Recording Sites

Suppose a payment request is processed exactly once. Spring Boot already provides automatic HTTP metrics, yet the application also adds an annotation-based measurement layer and a `Timer.record(...)` block around the same work. Dashboards may display two or three measurements for the same activity.

Distinguish two consequences:

- Multiple sites writing to the **same meter** inflate recorded count and total duration.
- Multiple meters with different names describing the same activity produce redundant data; if dashboards sum them as independent events, aggregated figures are wrong too.

The goal is not eliminating every nested measurement. The goal is defining **which question each meter answers, from where to where it measures, and which component owns recording**.

For example, total HTTP request duration and the duration of a price-check step inside that request are two different questions. They can coexist. Conversely, two layers both claiming to count “completed HTTP requests” for the same execution require reviewing measurement ownership.

## 2. Understand the Metric Creation Flow Before Adding Custom Metrics

One way to visualize the processing flow is:

```text
actual operation
    → measurement start/end points
    → Timer or Observation
    → MeterRegistry
    → endpoint / metric exporter
    → dashboard and alerts
```

An `Observation` represents the lifecycle of an activity. `ObservationHandler` implementations react to that lifecycle to produce metrics, traces, or other observability signals. If the registry already has a handler generating metrics, completing an observation can already record a `Timer`. Adding a `Timer.record(...)` around the same activity is no longer “adding for completeness.” See [Micrometer's Observation Handler mechanism](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

In a Spring Boot application, check built-in instrumentation points first:

| Scope | Existing measurement source | What to verify |
| --- | --- | --- |
| Spring MVC/Spring WebFlux request | Framework request metrics, typically `http.server.requests` | Actuator, observation config, and actual processing flow |
| Outbound HTTP calls | Client metrics configured via Spring Boot-provided builders | Does the client actually use the configured builder? |
| Repository methods | Corresponding Spring Data integration | Repository type and active configuration |
| Methods with `@Observed` or `@Timed` | Aspect or annotation-handling integration | Is the mechanism active and do calls pass through it? |
| Custom business blocks | Application-created Observation or Timer | Is that block genuinely unmeasured with the same meaning? |

Do not assume every `@Service` method is already auto-instrumented. Nor assume merely placing an annotation in code guarantees a metric exists. What must be verified is the active execution mechanism and the runtime metrics that appear.

For HTTP clients, Spring Boot instructs using the auto-configured `RestTemplateBuilder`, `RestClient.Builder`, or `WebClient.Builder` to receive instrumentation support. Creating clients in other ways may bypass that integration. [Spring Boot Metrics documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html) describes these integrations.

## 3. Three Distinctions That Prevent Misdiagnosis

### 3.1. Re-registering a Meter Is Not Re-recording an Event

Meter identity is determined by name and tag set within a registry. For the same meter type and identity, calling builder/register again typically returns the existing meter; it does not increment execution count. Tag declaration order does not create a new identity.

```java
Timer first = registry.timer("checkout.duration", "channel", "web");
Timer second = registry.timer("checkout.duration", "channel", "web");
```

This illustrates with an existing `registry`. Those two lines only look up or register the timer. Without `record(...)` or stopping a sample on the timer, zero duration samples have been recorded.

Conversely, two `record(...)` calls are two recordings, even though both target the same timer object. The registry does not know those two records represent the same piece of work and does not deduplicate by request ID. [Micrometer Meters documentation](https://docs.micrometer.io/micrometer/reference/concepts/meters.html) explains meter identity by name and tags.

### 3.2. Timer Already Has Recording Count, Not Only Duration

`Timer` records both sample count and total time. Do not add a `Counter` solely to recount the exact calls already recorded by a timer when the question and counting boundary are identical.

However, “accepted orders,” “successfully imported rows,” or “payment attempts” can be distinct business events. Counters for those events remain meaningful when clearly defined and not summed indiscriminately with request counts. This point is also emphasized in [Micrometer Counters documentation](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html).

### 3.3. Two Nested Measurements Can Both Be Valid

Suppose a request takes 10 ms, during which a data validation step takes 2 ms:

```text
entire request:      [---------- 10 ms ----------]
data validation:           [-- 2 ms --]
```

One record for the request and one record for the validation step is reasonable. Total request time remains 10 ms. Adding 10 + 2 and calling 12 ms “total request processing time” double-counts the nested portion.

Also distinguish a business operation from retry attempts. One payment operation might call the payment gateway three times due to retries: business operation count is 1, outbound call count is 3. Differing counts here can be completely accurate.

## 4. Java Experiment: One Execution, Yet Count Increments Twice

The following example uses Java 21 and Micrometer 1.13.0. It runs standalone at the Micrometer level to isolate the mechanism without starting Spring Boot or an HTTP server.

`DefaultMeterObservationHandler` acts to automatically turn an observation into a timer. Meanwhile, the buggy branch also records manually into that exact timer. `MockClock` keeps timing deterministic without real sleeps.

### 4.1. Dependency Declaration

Create `pom.xml` in a standalone practice directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>duplicate-recording-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-observation</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

Versions are explicitly pinned to reproduce the standalone experiment. In a real Spring Boot application, use Spring Boot's dependency management to keep Micrometer libraries compatible.

### 4.2. Complete Program

Save at `src/main/java/demo/DuplicateRecordingDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class DuplicateRecordingDemo {
    public static void main(String[] args) {
        sameOperation("DUPLICATED", true);
        sameOperation("ONE_OWNER", false);
        differentScopes();
    }

    private static void sameOperation(String label, boolean duplicate) {
        MockClock clock = new MockClock();
        SimpleMeterRegistry meters =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            ObservationRegistry observations = ObservationRegistry.create();
            observations.observationConfig()
                    .observationHandler(new DefaultMeterObservationHandler(meters));

            Timer timer = Timer.builder("demo.checkout")
                    .tags("channel", "web", "error", "none")
                    .register(meters);
            Timer same = Timer.builder("demo.checkout")
                    .tags("error", "none", "channel", "web")
                    .register(meters);
            System.out.printf("%s sameMeter=%s before=%d%n",
                    label, timer == same, timer.count());

            AtomicInteger workCalls = new AtomicInteger();
            Observation.createNotStarted("demo.checkout", observations)
                    .lowCardinalityKeyValue("channel", "web")
                    .observe(() -> {
                        if (duplicate) {
                            timer.record(() -> doWork(clock, workCalls));
                        } else {
                            doWork(clock, workCalls);
                        }
                    });

            long expectedCount = duplicate ? 2 : 1;
            if (workCalls.get() != 1 || timer.count() != expectedCount) {
                throw new AssertionError("Unexpected recording count");
            }
            System.out.printf(Locale.ROOT,
                    "%s work=%d count=%d totalMs=%.0f%n",
                    label, workCalls.get(), timer.count(),
                    timer.totalTime(TimeUnit.MILLISECONDS));
        } finally {
            meters.close();
        }
    }

    private static void doWork(MockClock clock, AtomicInteger workCalls) {
        workCalls.incrementAndGet();
        clock.add(Duration.ofMillis(10));
    }

    private static void differentScopes() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry meters =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            ObservationRegistry observations = ObservationRegistry.create();
            observations.observationConfig()
                    .observationHandler(new DefaultMeterObservationHandler(meters));
            Timer validation = Timer.builder("checkout.validation")
                    .tag("phase", "basic")
                    .register(meters);

            Observation.createNotStarted("demo.request", observations)
                    .observe(() -> {
                        clock.add(Duration.ofMillis(3));
                        validation.record(() -> clock.add(Duration.ofMillis(2)));
                        clock.add(Duration.ofMillis(5));
                    });

            Timer request = meters.get("demo.request").timer();
            System.out.printf(Locale.ROOT,
                    "DIFFERENT_SCOPES requestCount=%d requestMs=%.0f validationCount=%d validationMs=%.0f%n",
                    request.count(), request.totalTime(TimeUnit.MILLISECONDS),
                    validation.count(), validation.totalTime(TimeUnit.MILLISECONDS));
        } finally {
            meters.close();
        }
    }
}
```

In the first two scenarios, the manual timer carries `channel=web` and `error=none` to match the timer created by the handler for a successful observation in the version under test. This intentionally creates the same identity for the experiment. In real integrations, do not copy framework internal tags to write manually into its HTTP meters.

`AtomicInteger` counts how many times the real work executes; this distinguishes “the work ran twice” from “the work ran once yet metrics were recorded twice.”

### 4.3. Compile and Run

From the directory containing `pom.xml`, use JDK 21 and Maven. Downloading dependencies the first time requires Maven repository access.

On PowerShell/Windows:

```powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=target/dependency
javac --release 21 -cp "target/dependency/*" -d target/classes src/main/java/demo/DuplicateRecordingDemo.java
java -cp "target/classes;target/dependency/*" demo.DuplicateRecordingDemo
```

On Linux/macOS, use the same first two commands and replace the run command with:

```bash
java -cp "target/classes:target/dependency/*" demo.DuplicateRecordingDemo
```

Exact stdout:

```text
DUPLICATED sameMeter=true before=0
DUPLICATED work=1 count=2 totalMs=20
ONE_OWNER sameMeter=true before=0
ONE_OWNER work=1 count=1 totalMs=10
DIFFERENT_SCOPES requestCount=1 requestMs=10 validationCount=1 validationMs=2
```

### 4.4. Why Does This Output Occur?

In `DUPLICATED`:

1. Two registrations with the same identity return the same timer; before running, count is still 0.
2. Actual work runs once and advances the clock by 10 ms.
3. `timer.record(...)` records 10 ms once.
4. When the observation finishes, the handler records another 10 ms.
5. The result is count equal to 2 and total time equal to 20 ms.

In `ONE_OWNER`, we remove the inner `timer.record(...)` call. The observation and its handler own recording once, so count equals 1 and total time equals 10 ms.

In `DIFFERENT_SCOPES`, the outer observation measures the whole 3 + 2 + 5 = 10 ms block; the inner timer measures only the 2 ms step. Each meter has one record and answers a different question.

One easily missed detail: in the buggy scenario, the mean `20/2` is still 10 ms. Looking only at mean latency may fail to catch duplicate recording. Call counts, total duration, tag breakdown, and actual execution count must all be cross-checked.

## 5. Choosing the Component Responsible for Recording in Spring Boot

### 5.1. Keep Automatic Instrumentation When It Already Answers the Question

If you need request counts, HTTP statuses, and request handling durations, check the automatic meter before adding another timer wrapping the controller.

In this case, it is usually best to:

- Keep the framework's HTTP metrics.
- Remove custom timers/annotations added solely to recount the same requests.
- Use appropriate tags and queries to filter the target endpoint.
- If extra metadata is needed, look into observation conventions rather than creating a second meter with the same meaning.

Adding an annotation that creates a differently named meter does not fix semantic duplication. For example, `http.server.requests` and `checkout.http.duration` can still describe the same checkout requests if dashboards use both as checkout request counts. Redefine usage or remove the redundant one, rather than merely renaming it.

### 5.2. Create a Business Measurement When the Question Is Truly Different

Suppose you need to measure price calculation separately; you can create an observation at the business boundary:

```java
return Observation.createNotStarted("checkout.price", observationRegistry)
        .lowCardinalityKeyValue("channel", "web")
        .observe(this::calculatePrice);
```

This illustrates inside a component that already has `ObservationRegistry` and a `calculatePrice` method. The boundary must be defined as “one price calculation,” not “one HTTP request.”

If that observation is already converted into a metric by a handler, do not add a `Timer.record(...)` around `calculatePrice` with the same measurement goal. You can choose a manual Timer instead of an observation if only timing is needed, but choose one mechanism responsible for that boundary.

Business operations may be invoked from HTTP, scheduled jobs, or message consumers. Then price-calculation counts will not necessarily equal HTTP request counts and should not be forced to match.

### 5.3. Annotations Are Also Recording Points to Inventory

`@Timed`, `@Observed`, and manual `Timer`/`Observation` code can all participate in a measurement flow. When annotation handling is active, adding an annotation and also instrumenting manually around the same method body can produce an extra recording or a redundant observation.

Do not assume every Spring Boot version, AOP setup, and invocation style handles annotations identically. For example, `@Timed` on ordinary methods needs a corresponding handler; with Spring AOP, calls must go through the proxy. [Timers and TimedAspect documentation](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html#_the_timed_annotation) describes how the annotation is executed.

When choosing annotations as the recording point, keep the method body focused on business logic. When choosing manual instrumentation to control complex boundaries, remove annotations carrying the same responsibility.

## 6. “Fixes” That Easily Lose or Distort Data

### 6.1. Do Not Add a Second Metric-Creating Handler Just Because Metrics Aren't Visible Yet

In Spring Boot, observation components may already be auto-registered. Before manually calling:

```java
observations.observationConfig()
        .observationHandler(new DefaultMeterObservationHandler(meters));
```

check whether the current registry already has a metric-creating handler. That snippet is needed in Section 4's standalone Micrometer program, not as boilerplate to copy into every Spring Boot application.

Having one handler for metrics and one handler for tracing on an observation is valid usage: the two handlers serve two different outputs. What warrants checking is multiple handlers generating the same kind of metric for one observation.

### 6.2. Do Not Use MeterFilter to Guess Which Record Is a Duplicate

`MeterFilter` can deny meters or transform meter identities. If two sites write into the same meter, a name-based filter cannot tell which write is the “original” and which is the “duplicate.” Denying that meter drops both.

Similarly, renaming two distinct meters to the same name or stripping the tags that distinguish them can merge recording sources into one identity. Therefore, tweaking filters does not replace fixing the recording sites. See [MeterFilter roles and application order](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

### 6.3. Distinguish Disabling Observations from Disabling Meters

When planning to replace an entire integration, Spring Boot allows disabling observations by name prefix. For example, this property has broad scope:

```properties
management.observations.enable.http.server.requests=false
```

It suppresses observations with the matching prefix; it is not a surgical way to remove a duplicate annotation on one controller. Disabling an observation can also affect other outputs relying on that observation, such as tracing. Use it only after defining the replacement scope and verifying which signals must be preserved.

Conversely, `management.metrics.enable...` properties act at the meter layer; they do not automatically stop all related observations/traces. A manual Timer also does not automatically pass through `ObservationPredicate` merely because its name resembles an observation name.

Usually, if extra instrumentation is redundant, removing that extra instrumentation directly is cleaner than turning off HTTP metrics application-wide. [Spring Boot Observability documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html#actuator.observability.preventing-observations) explains disabling observations.

### 6.4. Do Not Use a Divisor to Mask Doubled Counts

Dividing count by 2 on a dashboard only hides one symptom. Error paths, retries, or a call path that skips one of the two instrumentation layers may no longer produce exactly two records. After a minor code change, that divisor breaks the numbers in another way.

Fix the data-recording points and then re-verify the increment for a known set of inputs.

## 7. Verifying on the Application Using COUNT Increments

Test on a controllable instance and choose one specific call flow. For instance, a Spring MVC application with `GET /checkout` and the `metrics` endpoint exposed in a test environment.

Read the automatic metric using its raw Java name while filtering all required tags:

```bash
curl --get "http://127.0.0.1:8080/actuator/metrics/http.server.requests" --data-urlencode "tag=uri:/checkout" --data-urlencode "tag=method:GET" --data-urlencode "tag=status:200"
```

On PowerShell, you can call `curl.exe` to avoid the alias. If the application uses another management port or path, adjust the URL to match actual configuration. Tag names and values must be taken from the actual meter present, without assuming every integration uses the exact same tag set.

Proceed in order:

1. If the meter does not exist yet, send one warm-up request and read the initial value. The absence of a meter is not proof that the current count equals a measured value.
2. Record `COUNT` after the warm-up request finishes.
3. Send exactly N requests matching the filtered tags, with automatic retries disabled, and wait for all to complete.
4. Read the same metric again with the same filters.
5. Under the contract “each completed request is recorded once,” `COUNT_after - COUNT_before` must equal N.

Do not compare the cumulative total directly against N if the process has served earlier requests. Do not assert exact real elapsed duration constants in tests, as duration depends on the environment.

The `metrics` endpoint sums measurements of meters matching the name and selected tags. Missing filters can cause results to include multiple URIs or status groups. Reading Actuator is itself HTTP traffic, so filtering to `uri:/checkout` avoids mixing Actuator calls into the group under test.

If count rises by 2N, inspect recording sites inside the process. If count rises by exactly N in the registry yet the dashboard still doubles, shift focus to queries, labels, and the scraping pipeline.

## 8. Also Check Error Branches, Retries, and Async Boundaries

A happy-path flow giving the right count is not enough to conclude duplicate recording is gone.

- **Error branches:** the same failure can be recorded in both `catch` and `finally`. Choose one recording exit point; error tagging must remain consistent with the metric definition.
- **Retries:** distinguish one logical operation from each attempt. Place measurement outside the retry loop for overall operation time; measure per attempt for outbound call diagnostics. If keeping both, give them distinct names and questions.
- **Asynchronous execution:** method return does not mean work completion. One layer timing submission and another timing execution cover different boundaries; do not label both as completion time of the same work.
- **Proxy call paths:** one branch going through an aspect while another self-invokes within the same object can emit different record counts. Do not rely on aspect bypass to “deduplicate.”
- **Nested call paths:** an outer request and an internal client call are usually two distinct events. If a client calls back into the same application, actual HTTP request count can exceed user clicks.

The checkpoint is actual execution counts per unit of work, not just entry counts into the outermost method.

## 9. Separating Application Bugs from Collection-Pipeline Bugs

| Observation | Where to check |
| --- | --- |
| One real execution, same timer increments count twice | Manual timer, sample, aspect, or observation handler writing together |
| Two differently named metrics summed together as “requests” | Metric definitions and dashboard queries |
| Metric rises accurately in-process, dashboard total doubles | Duplicate scraping, parallel export paths, or flawed aggregation |
| Multiple time series with same name but different URI/status/instance | Data dimensions; not by itself proof of duplicate recording |
| One timer showing count, total, and buckets | Multiple statistics of one meter; not one execution per line |
| One business flow with one outer timer and multiple inner attempts | Check retry contract and measurement scope before deleting |

A `CompositeMeterRegistry` distributing metrics to multiple target registries can be intentional configuration, such as sending to two different monitoring systems. That alone does not prove Java sources are recording twice. An aggregation problem occurs only when the same data converges back into one place and is counted multiple times unintentionally.

Different tag combinations are distinct series. Keep tags finite in cardinality and meaningful for grouping; do not add request IDs or timestamps to turn each record into a new meter. That inflates series count without fixing duplicate recording.

## 10. Locking Down a Non-Duplicated Measurement Design

Before adding or keeping a metric, write a clear sentence matching this template:

```text
This metric measures [unit of work],
from [start point] to [end point],
recorded by [component],
and is used to answer [question].
```

Examples:

- `http.server.requests`: one HTTP request recorded by web integration, used to track request traffic and duration.
- `checkout.price`: one price calculation recorded by a business-layer observation, used to analyze pricing computation.
- `payment.attempt`: one call attempt to the payment gateway, used to evaluate retry effectiveness.

These three names can coexist because they represent three different units of work. Each boundary still needs a single component responsible for recording it.

Check yourself on three scenarios:

1. Registering the same timer twice without calling `record`: does count increase?
2. A 10 ms task recorded by both a manual timer and an observation handler into the same meter: what are the count and total time?
3. A 10 ms request containing a 2 ms validation step: may you sum the two timers to report 12 ms of request time?

Check: does not increase; count equals 2 and total time equals 20 ms in the experiment; do not sum because validation time is already inside request time.

A sound design is proven by matching execution counts against defined boundaries and verifying against runtime data. Clean metric names or plausible-looking charts do not replace that verification.
