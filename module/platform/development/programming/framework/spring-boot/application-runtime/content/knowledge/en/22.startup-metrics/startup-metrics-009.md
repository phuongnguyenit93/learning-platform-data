# Relating Startup Measurement Data to Actuator Startup When Properly Configured

## 1. Measuring Startup: Beyond Asking How Many Seconds Startup Takes

In a Spring Boot application, startup time can be spent on many different tasks: preparing the `Environment`, loading bean definitions, running `BeanFactoryPostProcessor`, instantiating singletons, initializing the embedded web server, opening connections to external systems, running `ApplicationRunner`, and publishing readiness to receive traffic.

A log line such as:

```text
Started MyApplication in 4.572 seconds (process running for 5.221)
```

reports **an overall Spring Boot measurement** (numbers are illustrative only). It does not automatically show which bean took time, which steps ran nested inside others, or why time to readiness was longer. When detailed diagnostics are needed, Spring Framework provides `ApplicationStartup` and `StartupStep`; Spring Boot 3.3 adds `BufferingApplicationStartup` and the Actuator `/actuator/startup` endpoint to retrieve buffered steps **if properly configured before running the application**.

Three layers should be separated:

1. **Overall timing**: the "Started ... in ..." log, `ApplicationStartedEvent` and `ApplicationReadyEvent`, as well as aggregate metrics `application.started.time`/`application.ready.time` when Actuator/Micrometer is present.
2. **Startup step data**: `ApplicationStartup` creates `StartupStep` instances with name, id, parent id, tags, and processing interval.
3. **Data retrieval channel**: `/actuator/startup` exposes a JSON timeline when using `BufferingApplicationStartup`, adding the Actuator dependency, and exposing the endpoint properly.

This lesson applies to **Spring Boot 3.3.x, Spring Framework 6.1.x, and Java 17+**. The goal is not merely turning on a URL, but **correlating the data accurately**: knowing in which phase each step was measured, avoiding mis-summing nested durations, distinguishing startup steps from aggregate metrics, and avoiding turning a diagnostic endpoint into a security hole.

## 2. How Do Startup Time, Started Time, and Ready Time Differ?

During a standard run, Spring Boot passes through major milestones:

```text
main()
    |
SpringApplication.run(args)
    |
Prepare Environment and ApplicationContext
    |
ApplicationContext.refresh()
    |
ApplicationStartedEvent
    |
LivenessState.CORRECT
    |
ApplicationRunner / CommandLineRunner
    |
ApplicationReadyEvent
    |
ReadinessState.ACCEPTING_TRAFFIC
    |
SpringApplication.run() returns context
    |
Instance continues serving traffic
```

**Started** and **ready** are not the same milestone:

- `ApplicationStartedEvent` is published after context refresh, **before** `ApplicationRunner`/`CommandLineRunner`.
- `ApplicationReadyEvent` is published after runners and before Boot announces accepting readiness in the default availability sequence.
- Time to ready can include steps inside runners that the "Started ..." log does not fully represent.
- A runner performing mandatory work for 10 seconds can delay ready, even if context refresh itself barely changed.

### 2.1. Two Aggregate Metrics in Actuator

Spring Boot Actuator 3.3 provides **application startup time metrics**:

| Metric | Meaning |
| --- | --- |
| `application.started.time` | Time to reach the started milestone |
| `application.ready.time` | Time to reach the ready milestone to serve requests per Boot's lifecycle |

These metrics are tagged with the fully qualified name of the application class. When the metrics endpoint is enabled/exposed, you can query:

```text
GET /actuator/metrics/application.started.time
GET /actuator/metrics/application.ready.time
```

These are **not** two sub-URLs of `/actuator/startup`. They belong to the Micrometer metrics system, which can be exported to a registry such as Prometheus depending on dependencies/config. `/actuator/startup` provides a **step timeline** to diagnose latency contributors.

### 2.2. The "process running for" Log Phrase Has a Different Scope

The phrase "process running for ..." in the log also includes the JVM/process runtime prior to when Boot wrote the log, so it can differ from the "Started ... in ..." figure. Do not subtract two arbitrary log numbers and claim the difference is bean initialization time.

When comparing releases, choose **the same metric type**, launch method, environment, and load conditions. An aggregate log, a startup step, and a Java Flight Recorder event can measure different intervals.

## 3. What Is ApplicationStartup?

`org.springframework.core.metrics.ApplicationStartup` is Spring Framework's abstraction for recording **phases/operations** during startup. Each `start(String name)` call creates a `StartupStep`. A step can attach tag metadata and is marked complete with `end()`.

Model:

```text
ApplicationStartup
    |
    +-- StartupStep: spring.boot.application.starting
    |       id=...
    |       start -> end
    |
    +-- StartupStep: spring.context.refresh
    |       id=...
    |       +-- StartupStep: spring.beans.instantiate
    |       |       tags: beanName=...
    |       +-- ...
    |
    +-- StartupStep: app.demo.warmup
            tags: phase=runner
            start -> end
```

Actual names and step relationships depend on the implementation, framework version, and which code paths are instrumented. This diagram illustrates data shape, **not a guarantee that every step matches these exact names and structure**.

### 3.1. Components of StartupStep

| Property | Meaning |
| --- | --- |
| `name` | Operation name, e.g., `spring.beans.instantiate` |
| `id` | Identifier for a step within the current recording |
| `parentId` | Parent step ID when nested; may be absent |
| `tags` | Key/value metadata, e.g., `beanName=homeController` |
| `startTime` | Timestamp when the step started in the timeline |
| `endTime` | Timestamp when the step ended |
| `duration` | Step duration, usually expressed as an ISO-8601 Duration |

The last three fields belong to the **timeline event** record collected by the buffering implementation, not all direct methods on the `StartupStep` interface.

### 3.2. Default ApplicationStartup Produces No Useful Trace

Spring Framework defines `ApplicationStartup.DEFAULT` as a **no-op** implementation to minimize overhead when startup analysis is not needed. Do not assume Spring Boot automatically keeps a detailed timeline for every run.

To retrieve JSON from the `startup` endpoint, you must register `BufferingApplicationStartup` when constructing `SpringApplication`, before calling `run(...)`. Enabling Actuator after startup finishes cannot recreate steps that were never recorded.

### 3.3. ApplicationStartup Differs from @Timed and Profilers

`StartupStep` describes measurement points actively marked by the framework or application code. It is **not a full CPU/heap/I/O time profiler**. If a piece of code is not instrumented as a separate step, the timeline cannot automatically infer that segment's exact cost.

For CPU, allocations, GC, classloading, lock contention, and stack traces, Java Flight Recorder (JFR) or a dedicated profiler may be more suitable. Startup step data and JFR complement each other rather than fully replacing one another.

## 4. Why Choose BufferingApplicationStartup for Actuator Startup?

Spring Boot provides `org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup`. This implementation retains startup steps in a **bounded-capacity buffer** so they can be exported as a timeline.

Enable programmatically in Java **before `run`**:

```java
SpringApplication app = new SpringApplication(MyApplication.class);

app.setApplicationStartup(
        new BufferingApplicationStartup(2048));

app.run(args);
```

This is a snippet inside `main`, requiring `MyApplication` and imports for `SpringApplication` and `BufferingApplicationStartup`. `2048` is the **step count capacity** of the buffer, not time in milliseconds and not memory size in bytes.

### 4.1. Bounded Buffer

Per Boot 3.3 JavaDoc:

- The buffer records steps until reaching **capacity**.
- Once capacity is full, new steps may **not be recorded**.
- You can add filters via `addFilter(...)` to collect only needed steps.
- You can take a snapshot with `getBufferedTimeline()`.
- You can drain events with `drainBufferedTimeline()`.

**Important consequence:** if a bean or runner step is missing, do not conclude "that step does not exist" when the buffer may have filled up before that step ran. Increase capacity purposefully, filter appropriately, or change collection strategy.

### 4.2. Do Not Swap applicationStartup After Startup to Recover History

If you create `BufferingApplicationStartup` after `SpringApplication.run(...)` and merely assign it to an arbitrary bean, steps already passed **are not retroactively recorded**. Similarly, only installing Actuator without calling `setApplicationStartup(...)` before `run(...)` will not populate the endpoint with steps.

**Start measuring before what you want to measure** is an unbreakable rule of startup tracing.

## 5. Conditions for /actuator/startup to Exist and Have Data

With **Spring Boot 3.3**, an HTTP application wanting to use `/actuator/startup` must satisfy these conditions:

1. The application has the **`spring-boot-starter-actuator`** dependency.
2. `SpringApplication` was configured with **`BufferingApplicationStartup`** before `run`.
3. The `startup` endpoint is **enabled** per Spring Boot Actuator configuration.
4. The `startup` endpoint is **exposed over HTTP** if you want to query it with `curl`.
5. The HTTP server, management port, base path, and Spring Security/network policy permit requests to reach the endpoint.

In Boot 3.3, most endpoints are **enabled** by default except `shutdown`, yet by default only **`health` is exposed over HTTP**. Thus **enabled and exposed are two distinct concepts**.

### 5.1. Minimal Exposure Configuration

```properties
# With Actuator dependency and BufferingApplicationStartup in main.
management.endpoints.web.exposure.include=health,startup,metrics
```

When wanting to explicitly state that the startup endpoint is enabled:

```properties
management.endpoint.startup.enabled=true
```

The second line is usually unnecessary when keeping default enablement, yet helpful if the application uses opt-in enablement.

**Do not use**:

```properties
management.endpoints.web.exposure.include=*
```

arbitrarily in production. `*` exposes many endpoints carrying internal information; some also perform write operations. Prefer a small allowlist, firewalls, and authentication/authorization.

### 5.2. If Using a Separate Management Port

If you set:

```properties
management.server.port=9090
management.endpoints.web.base-path=/actuator
```

then the endpoint is typically at `http://host:9090/actuator/startup`, not port 8080. If you change the base path or add a context path, compute the URL from the actual configuration. Do not infer from a 404 on `localhost:8080` that the buffer is broken if the management server runs on a different port.

### 5.3. Security Must Be Designed Before Exposing

`startup` can expose:

- Bean names and subsystem types.
- The application class name.
- Startup step structure.
- Tags attached by the framework or app.
- Timestamps, durations, and relationships between steps.

Such information can help an attacker understand application internals. If a custom step accidentally attaches an API key or user identifier to a tag, the risk is even greater.

**Expose the endpoint only to authorized operators**, preferring internal environments and network restrictions. If Spring Security is present and you define a custom `SecurityFilterChain`, actively protect Actuator; do not assume auto-security still applies once you override configuration.

## 6. Actuator Startup GET and POST: Different Side Effects

Per Spring Boot 3.3 Actuator REST API, `/actuator/startup` supports:

| Method | Effect | Mutates buffer? |
| --- | --- | --- |
| `GET /actuator/startup` | Retrieves a **snapshot** of steps currently held in the buffer | **Does not remove** data |
| `POST /actuator/startup` | **Drains**: retrieves current steps and removes them from the buffer | **Yes**, clears those entries from the current buffer |

Example:

```bash
curl -i http://127.0.0.1:8080/actuator/startup
```

The command above is a default **GET**. To drain:

```bash
curl -i -X POST http://127.0.0.1:8080/actuator/startup
```

**Warning:** `POST` is not an "equivalent read to GET". If a collector already sent POST and drained, a subsequent GET can return few or no events. Do not call POST repeatedly on an instance and then claim startup data mysteriously vanished.

### 6.1. Safe Workflow When Data Must Be Kept

1. Use `GET` to observe/inspect first.
2. Save the snapshot in an appropriately access-controlled location if analysis is needed.
3. Use `POST` only when intending to **hand off and clear the buffer**, with an established collector/owner and storage strategy.
4. If automation collects multiple times, control duplicate events and drain ordering.
5. If GET after POST shows zero events, check POST history before increasing capacity.

For apps with Spring Security, `POST` can also be blocked by **authorization or CSRF policy**. Do not disable CSRF for all endpoints just for the convenience of one `curl` command; design policies per API and deployment.

### 6.2. POST Does Not Turn Off Instrumentation

Draining removes existing events from the buffer rather than altering the `ApplicationStartup` configuration. New steps can continue to be recorded if the system still collects per implementation/capacity. However, the endpoint's purpose is the **startup sequence**, not an unbounded stream of every HTTP request; do not use it to replace runtime metrics/traces.

## 7. Reading the JSON Structure of /actuator/startup

Actuator REST API 3.3 describes a response containing `springBootVersion` and `timeline`. Inside `timeline`:

```json
{
  "springBootVersion": "3.3.13",
  "timeline": {
    "startTime": "2025-06-19T07:16:19.477Z",
    "events": [
      {
        "startTime": "2025-06-19T07:16:19.875Z",
        "endTime": "2025-06-19T07:16:19.878Z",
        "duration": "PT0.003S",
        "startupStep": {
          "name": "spring.beans.instantiate",
          "id": 3,
          "parentId": 2,
          "tags": [
            { "key": "beanName", "value": "catalogService" }
          ]
        }
      }
    ]
  }
}
```

**This JSON illustrates structure, not the exact output of a specific application.** Real runs will have different timestamps, durations, step ids, and tags. Not every step has a `parentId` or tags.

### 7.1. Meaning of Each Field

| JSON path | How to interpret |
| --- | --- |
| `springBootVersion` | Spring Boot version of the instance returning data |
| `timeline.startTime` | Start point of the timeline |
| `timeline.events` | List of steps recorded in the buffer |
| `events[].startTime` | Timestamp when the step started |
| `events[].endTime` | Timestamp when the step ended |
| `events[].duration` | Step duration in Duration syntax, e.g., `PT0.003S` |
| `events[].startupStep.name` | Step name |
| `events[].startupStep.id` | Step ID in the timeline |
| `events[].startupStep.parentId` | Parent step ID, when present |
| `events[].startupStep.tags` | Additional key/value metadata |

For example, `PT0.003S` means **3 milliseconds** in ISO-8601 Duration. `PT1.25S` means 1.25 seconds. Do not treat this as a Unix timestamp or nanosecond count. In Java you can use `java.time.Duration.parse(...)` to parse this format.

### 7.2. Use IDs to Build the Tree, Not Array Order as Hierarchy

If a step has `parentId=2`, it falls under the step with `id=2`. From that you can build a graph/tree, locate parent-child relationships, and see which intervals sit inside a larger phase.

Element order in `timeline.events` **is not a guarantee that an earlier element is always the parent**. Link using `id` and `parentId`. Some steps have no parent, and a full buffer/filter can mean not all steps are present to build a complete tree.

### 7.3. Tags Help Narrow Down Beans but Do Not Measure Everything

For instance, `spring.beans.instantiate` with `beanName=priceCalculator` helps locate a bean created during startup and its corresponding step duration.

Yet consider:

- Does that bean have `@PostConstruct` callbacks, constructors, or an underlying dependency graph?
- Is it truly the main cause or merely enclosing child steps?
- Part of the work may already have run in earlier auto-configuration.
- External DB/API dependencies can be slow without having their own step.
- If a `@Lazy` bean was not created at startup, it may not appear in the timeline.

Tags are investigation hints, **not a complete profiler**.

## 8. Major Mistake: Summing All Event Durations

Many `StartupStep` instances can be **nested or overlap in time**:

```text
Context refresh                     [---------------------- 500 ms]
  BeanFactory setup                  [---- 120 ms]
  Instantiate Bean A                      [------ 200 ms]
    Instantiate dependency B              [--- 80 ms]
  Instantiate Bean C                              [-- 40 ms]
```

If you sum `500 + 120 + 200 + 80 + 40 = 940 ms` and say context refresh took 940 ms, you have **counted time inside parent steps multiple times**. A nested step is usually a time component of its parent step.

Analysis rules:

1. Use `startTime`/`endTime` to compute actual phase intervals.
2. Use `parentId` to construct relationships.
3. Distinguish a parent's **inclusive duration** from a child's own interval.
4. For exclusive time, compute the union of direct child intervals accurately, handling overlap; do not naively subtract summed durations when concurrency exists.
5. Compare runs that share the **same version/config/environment**.

**No simple sum-of-durations function** yields accurate end-to-end startup time across all applications.

### 8.1. "Top 10 Slow Steps" Is Useful Yet Insufficient

Sorting steps by duration helps spot:

- A bean taking a long time to instantiate.
- Slow context refresh.
- An abnormally long custom warm-up step.

However, a long top-level step can be an **enclosing parent** over many child steps. Expand descendants before changing configuration. Check the critical path and total time to ready; do not optimize a step that has no impact on the ready milestone.

### 8.2. A Missing Step Does Not Mean the Work Did Not Run

It may be because:

- `ApplicationStartup` is set to no-op.
- `BufferingApplicationStartup` was registered too late.
- The buffer filled up before the step occurred.
- A filter excluded the step.
- A collector already ran POST/drain.
- The work was not instrumented.
- A lazy bean was only created when a request arrived after startup.
- You queried the wrong instance/pod/management port.

Use this checklist before concluding part of the lifecycle was skipped.

## 9. Complete Java 17+ Example: Actuator Startup and a Custom Step

The example runs **Spring Boot 3.3.13 + Java 17**, with an HTTP server on localhost, Actuator, and `BufferingApplicationStartup` configured **before `run`**. An `ApplicationRunner` creates a custom `StartupStep` named `app.demo.warmup`; a controller exposes `GET /demo/ping`.

**Behaviors to observe:**

- Boot automatically records framework startup steps.
- The runner records an extra step tagged `phase=runner`.
- `GET /actuator/startup` returns a JSON timeline containing steps still in the buffer.
- `GET /actuator/metrics/application.started.time` and `...ready.time` return separate aggregate measurements.
- `POST /actuator/startup` drains the buffer, which can leave a subsequent GET without old data.

### 9.1. Project Structure

```text
startup-timeline-demo/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/com/example/startup/
    StartupTimelineApplication.java
    PingController.java
```

### 9.2. settings.gradle

```groovy
rootProject.name = 'startup-timeline-demo'
```

### 9.3. build.gradle (Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

The example script uses Spring Boot's BOM to manage starter versions. The `./gradlew` commands below assume the project already has a **Gradle Wrapper**; if not, generate one with a compatible Gradle installation or via Spring Initializr.

### 9.4. application.properties

```properties
# Allow access only from localhost in this lab.
server.address=127.0.0.1
server.port=8080

# Expose only the endpoints needed for this lesson.
management.endpoints.web.exposure.include=health,startup,metrics

# Usually enabled by default; set explicitly to avoid ambiguity.
management.endpoint.startup.enabled=true
```

**Security note:** this file is **safe only as a local demo** running on localhost. Do not copy startup/metrics exposure to production without proper access control, firewalls, or authentication/authorization.

### 9.5. StartupTimelineApplication.java

```java
package com.example.startup;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.metrics.StartupStep;

@SpringBootApplication
public class StartupTimelineApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupTimelineApplication.class);

        // Must be set BEFORE run() to record startup steps.
        application.setApplicationStartup(
                new BufferingApplicationStartup(2048));

        application.run(args);
    }

    @Bean
    ApplicationRunner recordDemoWarmup(
            ConfigurableApplicationContext context) {

        return args -> {
            StartupStep step = context.getApplicationStartup()
                    .start("app.demo.warmup");

            try {
                step.tag("phase", "runner");

                int checksum = 0;
                for (int i = 0; i < 1000; i++) {
                    checksum += i;
                }

                System.out.println("WARMUP_CHECKSUM=" + checksum);
            } finally {
                // Important: end the step even if the code throws.
                step.end();
            }
        };
    }
}
```

This is a **complete Java file**. It uses `ConfigurableApplicationContext.getApplicationStartup()` to obtain the configured recorder; Spring Framework also supports injecting `ApplicationStartup` into eligible components.

**Why use `try/finally`?** `StartupStep.end()` must be called even if work throws an exception so the measured step completes. Forgetting `end` leaves an open step without a final duration, impairing timeline viewing or interpretation.

The name `app.demo.warmup` **does not use the `spring.*` prefix** because that namespace belongs to internal Spring steps. The `phase=runner` tag is fixed metadata and contains no secrets or personal data.

The `checksum` exercise simply illustrates observable execution. For integers from 0 to 999, the exact sum is **499500**, regardless of the machine. Do not conclude this tiny loop's duration represents database or network cold starts.

### 9.6. PingController.java

```java
package com.example.startup;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/demo/ping")
    public String ping() {
        return "pong";
    }
}
```

This is a complete Java file. It uses no database, does not attempt to warm all services, and does not replace a readiness probe. Its sole purpose is providing a simple business endpoint confirming the server accepts requests.

### 9.7. Running the Application

From the project with Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD:

```bat
gradlew.bat bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

When Boot runs successfully, the program prints:

```text
WARMUP_CHECKSUM=499500
```

Framework logs such as "Started StartupTimelineApplication in ..." also appear with machine-dependent measurements. **No exact seconds, `StartupStep` counts, or full framework log ordering are guaranteed.**

Open a second terminal:

```bash
curl -i http://127.0.0.1:8080/demo/ping
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/actuator/startup
```

The body of the demo endpoint `/demo/ping` is:

```text
pong
```

`/actuator/health` is the health endpoint, whereas `/actuator/startup` returns the **JSON timeline**. Do not expect `/actuator/health` to explain which steps spent time.

### 9.8. Inspecting Separate Application Started/Ready Metrics

```bash
curl -i http://127.0.0.1:8080/actuator/metrics/application.started.time
curl -i http://127.0.0.1:8080/actuator/metrics/application.ready.time
```

When metrics are recorded and the endpoint is exposed, the response typically contains fields like:

```json
{
  "name": "application.ready.time",
  "description": "Time taken for the application to be ready to service requests",
  "measurements": [
    {
      "statistic": "VALUE",
      "value": 1.234
    }
  ],
  "availableTags": [
    {
      "tag": "main.application.class",
      "values": ["com.example.startup.StartupTimelineApplication"]
    }
  ]
}
```

**The JSON above only illustrates content and structure**, not guaranteed output, and `1.234` is not a measured figure from this lesson. Specific statistic names/types and tags depend on the Spring Boot/Micrometer version and runtime; rely on the actual JSON returned.

**Do not** look for this metric inside `/actuator/startup`. They come from Actuator's Micrometer metrics system, even though both are used for startup diagnostics.

### 9.9. Taking a Snapshot Without Draining

```bash
curl -fsS http://127.0.0.1:8080/actuator/startup \
  -o startup-snapshot.json
```

This command is for POSIX shells; on Windows PowerShell you can use `curl.exe` with compatible syntax or `Invoke-RestMethod`. Use `GET` to avoid clearing buffer data. Once saved, you can inspect `startup-snapshot.json` in an editor or any JSON parser.

### 9.10. Draining Only When Truly Intended

```bash
curl -fsS -X POST http://127.0.0.1:8080/actuator/startup \
  -o startup-drained.json
```

**Only try this if you accept consuming the buffer.** Calling GET again may show very few or no events. For apps with security/CSRF, POST may require appropriate credentials/tokens; the local demo omits `starter-security`.

Do not use POST just to "refresh the report". The startup endpoint has no feature to reconstruct history once events have been drained.

## 10. Correlating 3 Data Sources in One Startup Report

To diagnose a startup, collect:

| Source | Value | Specifically answers |
| --- | --- | --- |
| Spring Boot log | "Started ... in X seconds" | Overview of how long boot took |
| `application.started.time` | Aggregate metric | How long to reach the started milestone |
| `application.ready.time` | Aggregate metric | How long to reach ready to receive traffic |
| `/actuator/startup` | List of steps, durations, tags | What instrumented sections did and how long they took |
| Runner/warm-up logs | Start/end, outcome, internal trace id | Whether business startup steps succeeded |
| JFR/profiler | CPU/GC/allocations/threads | Why a phase cost time at the JVM level |
| Readiness probe | Current readiness for traffic | Whether the instance should receive new requests |

### 10.1. How to Combine Data Meaningfully

Suppose before optimizing, you measure:

```text
application.started.time = 3.2 s
application.ready.time   = 8.4 s
```

These are only **hypothetical** figures. The **5.2 s** gap suggests work after started and before ready, especially runners. Yet do not treat it as "one bean's time" or an exact measurement of un-instrumented steps.

Next:

1. Look for custom step `app.demo.warmup` or runner-related steps in `/actuator/startup`.
2. Check their durations and parent-child relationships.
3. Check runner and dependency-load logs to confirm the work actually completed.
4. If no matching step exists, check whether the code was instrumented and whether the buffer filled/was drained.
5. Re-measure under identical workload and machine limits to confirm the change.

### 10.2. Reports Should Also Record Collection Configuration

A minimal startup report should include:

- Application/version/commit.
- Spring Boot version and Java version.
- JVM flags, heap, CPU/memory limits.
- Launch mode: IDE, `bootRun`, `java -jar`, container, or native image.
- Active profiles and feature flags affecting startup (no secrets).
- `BufferingApplicationStartup` capacity/filters.
- Timestamp and endpoint access method: GET or POST.
- Started/ready metrics if available.
- Top steps with id, parentId, tags, durations.
- Readiness and first-request latency info if optimizing rollout quality.
- Sample size across runs, median and p95/p99 rather than a single sample.

Do not compare "Day A" and "Day B" from just two timelines when JVM cold/warm state, classpath, and CPU limits differ.

## 11. Analyzing Timing JSON with a Small Script

To analyze without relying on a UI tool, you can use standard Python to read `startup-snapshot.json` from the demo. The script below **reads already-saved data** and makes no network requests.

**File:** `inspect_startup.py`

```python
import json
from pathlib import Path

file = Path("startup-snapshot.json")
data = json.loads(file.read_text(encoding="utf-8"))

events = data.get("timeline", {}).get("events", [])

def as_seconds(text):
    # For PT0.003S durations common in this example.
    if text.startswith("PT") and text.endswith("S"):
        return float(text[2:-1])
    return None

rows = []
for event in events:
    step = event.get("startupStep", {})
    name = step.get("name", "unknown")
    seconds = as_seconds(event.get("duration", ""))
    if seconds is not None:
        rows.append((seconds, name, step.get("id")))

rows.sort(reverse=True)
for duration, name, step_id in rows[:10]:
    print(f"{duration * 1000:9.3f} ms  {name}  id={step_id}")
```

Run command, assuming Python 3:

```bash
python inspect_startup.py
```

This is a **standalone script** that runs if the JSON file contains Actuator data. The parser function only handles **ISO-8601 Durations of the form `PT...S`**, not a general parser for minutes/hours; for production use, choose a reliable ISO-8601 parser library or Java `Duration.parse(...)`.

**Important warning:** the script ranks steps by **inclusive duration**. It **does not** compute total startup time, **does not** subtract overlap, **does not** link nested steps, and **does not** replace building the hierarchy from `parentId`. Use it to locate which step to investigate first, not to report "total time of 10 beans".

### 11.1. Why Handle Missing Data?

When filters/capacity/drains affect the buffer, `events` may be empty or incomplete. The script above does not require `parentId` since that field is optional. Checking `duration` before conversion avoids throwing errors when schemas differ or data is missing.

For a serious pipeline, verify `springBootVersion`, the response schema, and handle missing fields gracefully before comparing across versions.

## 12. Adding Custom StartupSteps for Business Phases During Startup

Spring Framework lets application code create custom steps. For example, inside an `ApplicationRunner`:

```java
StartupStep step = context.getApplicationStartup()
        .start("app.cache.preload");

try {
    step.tag("cache", "catalog");
    catalogCache.loadRequiredData();
} finally {
    step.end();
}
```

This is a **snippet**, requiring `context`, `catalogCache`, importing `StartupStep`, and an application-defined cache API. It is not a standalone Java file. Apply only when cache loading is **intentionally part of startup**; do not preload production data just to generate measurements.

### 12.1. Naming Custom Steps by Convention

- Use a namespaced name, e.g., `app.cache.preload` or `company.module.init`.
- **Avoid the `spring.*` prefix** for custom steps because that namespace belongs to the framework.
- Names should remain stable across releases for easy comparison.
- Tags should have low-cardinality values and expose no sensitive data.
- Never put tokens, raw SQL containing user data, passwords, connection strings with credentials, or customer names into tags.
- Always call `end()`, preferably inside `finally`.

### 12.2. Custom Steps Do Not Turn an Asynchronous Task into a Ready Milestone

If a runner creates a `CompletableFuture` and returns immediately, Spring Boot can become ready before the async task finishes. A custom step running in the background might end after ready, yet that does **not** prove readiness waited for that work.

If warm-up is **mandatory** before receiving traffic, the runner should wait with a bounded timeout or the application must have explicit readiness gating. `ApplicationStartup` is strictly a measurement tool; it **does not orchestrate readiness** for you.

## 13. Buffer Capacity, Filters, and Incomplete-Data Risks

`BufferingApplicationStartup(2048)` does not mean every app needs or fits within 2048 steps. A large app with many auto-configurations and bean definitions can generate more.

### 13.1. Finite Capacity Is an Intentional Design Goal

The buffer bounds memory footprint and overhead. When full, new steps may be dropped. Thus setting capacity too low loses evidence; setting it too high can raise recording/retention cost.

Determine capacity empirically:

1. Enable in staging or locally with representative configuration.
2. Collect a snapshot of one normal startup.
3. Estimate the number of events.
4. Check whether key steps late in runners were recorded.
5. Pick a capacity with reasonable headroom.
6. Review CPU/heap overhead and tag contents before production.

### 13.2. Filters Help Reduce Noise

The implementation supports `addFilter(Predicate<StartupStep>)`. You can select steps by namespace/tags to retain needed steps. However, filters can drop important parent/child relationships, making it hard to explain a long step if its parent was excluded.

Before applying a filter, know your research question: finding a bean creation bottleneck, listener duration, or custom warm-up. Do not filter aggressively and then claim unrecorded things never happened.

### 13.3. The Buffer Is Not Distributed Tracing

Each instance has its own timeline. There is no built-in mechanism merging data from all pods into a single shared timeline. When comparing:

- Target the right instance/pod and version.
- Attach run/instance IDs in collection system metadata **outside the response** if needed.
- Avoid pushing sensitive raw tags to public dashboards.
- Compute per-instance deltas and compare distributions.

## 14. FlightRecorderApplicationStartup Is an Alternative, Not a JSON Startup Endpoint

Spring Framework has `org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup` for Java Flight Recorder. It emits Spring startup-related JFR events to correlate with:

- JVM class loading.
- Allocations and GC.
- Thread scheduling.
- Blocking I/O.
- CPU hotspots.

Example **alternative option** in `main`:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new FlightRecorderApplicationStartup());
app.run(args);
```

This is a snippet requiring `MyApplication` and importing `FlightRecorderApplicationStartup`. If choosing JFR, run with a sample command:

```bash
java -XX:StartFlightRecording:filename=recording.jfr,duration=15s \
  -jar build/libs/myapp.jar
```

The command only illustrates enabling JFR; the JAR must exist and the JDK must support Flight Recorder.

**Must remember:** Spring Boot 3.3's `/actuator/startup` **requires BufferingApplicationStartup**. Merely configuring `FlightRecorderApplicationStartup` and exposing the HTTP endpoint **is not equivalent** to the JSON buffer. They are **two different backends** for the same `ApplicationStartup` abstraction, serving different investigation workflows.

Do not assume both implementations can run concurrently just by calling `setApplicationStartup` twice; the later call replaces the earlier one unless you build a valid composite mechanism yourself.

## 15. Relation to Lazy Initialization and First-Request Latency

If `spring.main.lazy-initialization=true`, many beans may **not be created during startup** and only appear when the first HTTP request arrives. Spring Boot warns that lazy init can shift cost to the first request and delay catching configuration errors.

Consequences when reading `/actuator/startup`:

- The startup timeline may contain fewer bean-instantiation steps.
- `application.ready.time` may be lower.
- It does **not** mean routes are warmed or all dependencies are tested.
- Lazy beans not created at startup may simply spend time once traffic arrives.
- Startup buffering does not replace HTTP latency metrics.

To evaluate whether enabling lazy init helps, measure together:

1. Process-to-ready.
2. Recorded startup steps.
3. First-request latency of **critical paths**.
4. Error rate right after rollout.
5. Memory and GC once lazy beans begin appearing.
6. Impact on network/database when many pods scale up simultaneously.

**Startup optimization must not be traded for failures on the first user without deliberate intent.**

## 16. Relation to Health, Liveness, and Readiness

`/actuator/startup`, `/actuator/health`, and `/actuator/metrics` are three endpoint groups with distinct contracts.

| Endpoint | Question answered |
| --- | --- |
| `/actuator/startup` | Which startup steps were recorded in the timeline, and how long did they take? |
| `/actuator/metrics/application.ready.time` | How long did the recent startup take to reach ready? |
| `/actuator/health/readiness` | Should the **current** instance receive traffic? |
| `/actuator/health/liveness` | Is the **current** instance alive/internally healthy? |
| `/actuator/health` | Aggregate health status across configured indicators |

If `readiness` returns UP, that does not mean a timeline was collected or the startup endpoint is exposed. Conversely, a timeline with many completed steps does not guarantee the application is **currently** healthy.

### 16.1. Startup-Step Instrumentation Is Not Kubernetes startupProbe

`startupProbe` in Kubernetes is a mechanism checking whether a container has started enough to proceed with liveness/readiness probes. It **differs from** `/actuator/startup`, which is a timeline diagnostic endpoint.

Do not configure kubelet `startupProbe` to call `/actuator/startup` merely because the URL contains the word startup. Kubernetes probes need endpoints reporting appropriate **usability state** (`/livez` or an app-designed endpoint), not a diagnostic API that may be disabled, 404, or drained.

### 16.2. When Should You Observe Startup, Metrics, and Readiness Together?

A slow Kubernetes deployment rollout:

- `/actuator/startup` helps locate which Boot/container steps are slow.
- `application.ready.time` lets you compare **overall duration** across versions.
- Readiness probes tell whether the load balancer should send traffic yet.
- Container logs and CPU/GC/JFR reveal environmental factors.

Use coordinated data to avoid optimizing the wrong layer. If the startup timeline looks fine yet the pod is not ready due to an external dependency, investigate readiness policy, networking, and deployment rather than only bean instantiation.

## 17. Troubleshooting When /actuator/startup Does Not Return Expected Data

### 17.1. HTTP 404

Check in order:

1. Was `spring-boot-starter-actuator` added?
2. Did `application.setApplicationStartup(new BufferingApplicationStartup(...))` run **before `run`**?
3. Was `management.endpoint.startup.enabled` turned off?
4. Did `management.endpoints.enabled-by-default=false` disable the endpoint without re-enabling it?
5. Does `management.endpoints.web.exposure.include` contain `startup`?
6. Does `management.endpoints.web.exposure.exclude` take precedence and exclude `startup`?
7. Are you calling the right port and base path?
8. Does the app actually have a running HTTP server?

In Spring Boot 3.3, `startup` is auto-configured conditionally, including requiring a suitable recorder. Adding exposure alone will not make the endpoint appear when using the default no-op startup recorder.

### 17.2. HTTP 401 or 403

This is usually **access control**, not a missing timeline. If Spring Security is installed with a custom security filter chain, check endpoint matchers/authorization and CSRF policy for POST.

**Do not** open all actuator endpoints publicly as a "quick fix" for 403 errors. Instead grant read permissions to the right principals, allowlists, tokens/sessions, or use an appropriate management interface.

### 17.3. GET Has Events Yet Lacks an Expected Step

The step may be un-instrumented, filtered out, dropped because the buffer filled, or from a runner executing later than expected. Check whether custom steps called `end()` and whether you actually used the right recorder on `SpringApplication`.

### 17.4. GET Returns Empty Events After POST

This can be normal behavior because `POST` drains. To compare startup from the beginning, you need **a fresh startup** or the data saved by the collector. There is no "re-read drained history" button.

### 17.5. application.ready.time Is Missing

Verify Actuator/Micrometer metrics are enabled, the metric name is spelled right, the `metrics` endpoint is exposed, the app actually reached ready, and you queried the right URL. If startup failed before ready, the ready metric may not be recorded.

### 17.6. Durations Too Small or Unstable Results

Do not assume a recorder bug when a step takes only a few microseconds. JVM JIT, GC, OS scheduler, disk cache, and network strongly affect individual runs. Instead of overcomplicating a single measurement, gather multiple samples and analyze median/p95.

### 17.7. Management Port Is Green Yet App Still Errors

If the management server runs on a separate port, Actuator endpoints can respond while the main web server fails. The timeline only explains recorded startup; **it does not replace health checks of the main request path**.

## 18. Workflow for Analyzing a Startup Regression

Suppose a new release takes **8.9 s** to ready instead of **4.1 s** (illustrative numbers). A verifiable workflow:

1. Identify Git commit, Spring Boot/Java version, profiles, and resource limits.
2. Ensure both versions configure `BufferingApplicationStartup` identically with sufficient capacity.
3. Enable `startup`/`metrics` on a protected management interface.
4. Collect multiple restarts per version, then save GET snapshots and started/ready metrics.
5. Compare distributions of `application.started.time` and `application.ready.time`.
6. If ready grew while started stayed stable, investigate runners/warm-up after refresh.
7. If started grew, investigate context refresh, bean instantiation, framework initialization, and web server.
8. Use `parentId` to avoid mis-summing durations.
9. Check tags to trace beans or components; correlate with task logs.
10. If the gap appears only under CPU contention, capture JFR and OS resource metrics.
11. Test one clear hypothesis-backed optimization: reduce remote calls, selective lazy init, optimize queries, limit cache preloading.
12. Re-measure time-to-ready, first-request latency, errors, and memory after the change.
13. Confirm the change did not announce readiness prematurely while mandatory dependencies are still missing.
14. Base conclusions on multiple samples and actual steps, not inference from a single timeline.

### 18.1. Avoiding False Causal Conclusions

A step instantiating Bean A appearing in top slow steps does not mean A's constructor code is definitely the sole cause. Bean A may instantiate child dependencies, call external APIs, or wait on threads. Identifying bottlenecks requires combining:

- Nested step hierarchy.
- Stack traces/JFR.
- Database/client timing.
- Correlated logs.
- A controlled change experiment.

Measurements guide where to investigate; **before/after change evidence** confirms improvement.

## 19. Anti-Patterns to Avoid

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| Only adding Actuator starter and expecting full startup JSON | No buffer recorder by default | Configure `BufferingApplicationStartup` before `run` |
| Only exposing `startup` without enabling endpoint | Endpoint may be disabled | Check enablement and exposure separately |
| Configuring recorder after app is ready | Cannot retroactively record past steps | Set in `main` before `run` |
| Calling POST like GET | POST drains the buffer | Use GET for snapshot, POST for intentional handoff |
| Empty GET leads to thinking Boot did nothing | Buffer full/filtered/drained/no-op | Check recorder, capacity, filters, POST history |
| Summing durations of all steps | Double-counts nested/overlapping time | Analyze id/parentId and intervals |
| Treating startup timeline as a full CPU profile | Covers only instrumented points | Use JFR/profiler for JVM hotspots |
| Treating steps as application ready metric | Different data system, different purpose | Query `application.ready.time` separately |
| Confusing Actuator startup with startupProbe | Diagnostic vs. container health | Use health/live endpoints for probes |
| Putting API keys in custom tags | Leaks secrets via endpoint/collector | Non-sensitive metadata tags only |
| Exposing `*` on a public interface | Opens many sensitive endpoints | Endpoint allowlist and auth |
| Observing one pod once | No distribution/variance | Multiple instances and restarts |
| Comparing IDE launch with production JAR | Different startup modes/JVMs | Same launch method/config |
| Optimizing started.time while leaving runners slow | Ready can still stay slow | Measure both ready and runners |
| Enabling lazy init and declaring the app fast | Cost may shift to first request | Measure first-hit latency and errors |
| Filtering too aggressively and losing parent steps | Hard to build hierarchy | Retain enough steps for analysis |
| Low capacity while claiming complete trace | New steps may be dropped | Raise capacity carefully and cross-check |
| Recording custom step yet forgetting `end()` | Duration never finalized | `try/finally` |
| Colliding with `spring.*` custom names | Clashes with framework namespace | `app.*` or custom namespace |
| Pointing readiness check at startup endpoint | Does not measure ability to serve traffic | `/actuator/health/readiness` |
| Having metrics without recording run context | Cannot compare results | Save version/profiles/JVM/resources |
| Assuming GET after POST repeats old data | Drain consumed the buffer | Save snapshot or read from collector |

## 20. Configuration and Measurement Checklist

**Before startup**

1. Choose Spring Boot/Java versions and record in the experiment log.
2. Add `spring-boot-starter-actuator`.
3. Create a `SpringApplication` instance in `main`.
4. Call `setApplicationStartup(new BufferingApplicationStartup(capacity))` **before `run`**.
5. Pick a capacity suited to the number of steps the app produces.
6. Decide whether filters are needed.
7. Enable `startup` and `metrics` as needed.
8. Expose the exact HTTP endpoints needed.
9. Protect management endpoints; never expose unconditionally to the public.
10. Verify port/base path and target instance.

**After the app is ready**

11. Use `GET /actuator/startup` to take a snapshot.
12. Record `springBootVersion` and `timeline.startTime`.
13. Save raw JSON with appropriate access permissions.
14. Use `GET /actuator/metrics/application.started.time`.
15. Use `GET /actuator/metrics/application.ready.time`.
16. If using `POST`, understand it drains data.
17. Do not infer hierarchy from array order; use id/parentId.
18. Do not sum all durations to get total time.
19. Verify custom startup steps called `end()`.
20. Correlate ready/startup metrics with logs and readiness state.

**Analysis and operations**

21. Investigate long steps while accounting for nested children.
22. Correlate with JFR, CPU, GC, I/O when needed.
23. Measure multiple times across multiple instances.
24. If using lazy init, measure first-request latency.
25. Check whether the buffer filled up or a collector drained it.
26. Never put secrets into tags or raw reports.
27. Do not use `/actuator/startup` as a Kubernetes startupProbe.
28. Keep diagnostic endpoints strictly within needed scope.
29. Verify optimizations did not break correctness/readiness.
30. Document the experiment for comparing future releases.

## 21. Self-Check Questions

**1. Why might adding Actuator not automatically provide /actuator/startup?**

Because Spring Boot 3.3 requires `BufferingApplicationStartup` to be set on `SpringApplication`, and the endpoint must be enabled/exposed and allowed by server/security.

**2. When should setApplicationStartup be called?**

Before `SpringApplication.run(...)`; setting it late cannot record earlier steps.

**3. Does BufferingApplicationStartup(2048) mean 2048 ms?**

No. `2048` is the step capacity retained in the buffer, not a timeout or duration.

**4. How do GET and POST /actuator/startup differ?**

GET returns a snapshot **without draining**; POST returns and **consumes** currently buffered steps.

**5. Is application.ready.time inside /actuator/startup JSON?**

It is an aggregate Micrometer/Actuator metric; access it via the metrics endpoint if enabled/exposed. Startup JSON contains individual steps.

**6. Why not sum all durations?**

Because steps can be nested or overlap in time, counting the same interval multiple times.

**7. If bean A does not appear in the timeline, is it certain it was not created?**

No. The buffer may have filled, a filter excluded it, it was drained, instrumentation was absent, or the bean was created outside the measured phase; investigate further.

**8. Are JFR startup events equivalent to BufferingApplicationStartup?**

No. `FlightRecorderApplicationStartup` uses JFR; Boot 3.3's `startup` endpoint requires the buffered implementation.

**9. Should /actuator/startup be used as a Kubernetes startupProbe?**

No. It is a diagnostic API, not an availability probe.

**10. What signal suggests runners may be delaying ready?**

`application.ready.time` is significantly higher than `application.started.time` in the same run, along with custom runner steps and corresponding logs.

**11. What must a custom step do after starting?**

Attach needed tags and call `end()`, preferably in `finally` to finish even on errors.

**12. When should the startup endpoint not be exposed publicly?**

In most production applications, timeline/bean names can reveal internal structure. Expose only via controlled internal interfaces/permissions.

## 22. Summary

```text
        1. CONFIGURE BEFORE RUN
SpringApplication.setApplicationStartup(
    new BufferingApplicationStartup(...))
                     |
                     v
        2. BOOT RECORDS STARTUP STEPS
      StartupStep name/id/tags/parentId
                     |
                     v
        3. ACTUATOR STARTUP ENDPOINT
        GET = snapshot / POST = drain
                     |
                     v
        4. INTERPRET TIMELINE ACCURATELY
  Do not sum nested durations;
  mind buffer capacity and missing steps
                     |
                     +------------+
                     |            |
   application.started.time   application.ready.time
       (separate metric)        (separate metric)
                     |            |
                     +------------+
                          |
             5. COMPARE SAME ENVIRONMENT
        + logs + readiness + JFR if needed
```

**Remember:** `/actuator/startup` has complete data only when the application **was configured to collect from the start** using `BufferingApplicationStartup`, and the endpoint is properly enabled, exposed, and protected. `GET` is a snapshot, `POST` is a drain. `StartupStep` durations help isolate bottlenecks, yet must not be blindly summed because of nested intervals. Correlate `application.started.time` and `application.ready.time`, logs, readiness, and sometimes JFR to form an accurate, measurable, and verifiable startup story.

## Official Documentation

- [Spring Boot 3.3.13 — SpringApplication: Application Startup Tracking](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3.13 — Actuator Endpoints: startup conditions, exposure and security](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3.13 — Actuator startup REST API (GET and POST)](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html)
- [Spring Boot 3.3.13 — BufferingApplicationStartup JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html)
- [Spring Boot 3.3.13 — Application Startup Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Spring Framework 6.1 — ApplicationStartup and StartupStep](https://docs.spring.io/spring-framework/reference/6.1/core/beans/context-introduction.html)
- [Spring Framework 6.1 — StartupStep API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/metrics/StartupStep.html)
