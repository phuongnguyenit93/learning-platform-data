# Attaching `BufferingApplicationStartup` to `SpringApplication` — Measuring Spring Boot 3.3 Startup Steps

## 1. Objectives

A Spring Boot application can take a few seconds or tens of seconds to begin serving. Looking at the log line "Started … in … seconds" only shows the **overall time**, without revealing the breakdown: which step spent time creating beans, resolving dependencies, refreshing `ApplicationContext`, starting the web server, or running startup callbacks.

Spring Framework provides the **`ApplicationStartup`** contract. Spring Boot provides the **`BufferingApplicationStartup`** implementation to record **`StartupStep`** entries into a bounded buffer, complete with start time, end time, duration, step name, and related tags.

**Core task:** you must create and **attach `BufferingApplicationStartup` to the `SpringApplication` instance before calling `run(args)`**. This timing is decisive because the earliest startup steps occur before the application context and application beans are created.

After this lesson, you will be able to:

1. Explain `ApplicationStartup`, `StartupStep`, `BufferingApplicationStartup`, and `StartupTimeline`.
2. Properly configure `SpringApplication#setApplicationStartup(...)` in Java 21 / Spring Boot 3.3.13.
3. Understand the meaning of `capacity`, that once full new steps are no longer stored, and how to use `addFilter(...)` to reduce data volume.
4. Read the timeline via `getBufferedTimeline()` or `drainBufferedTimeline()`.
5. Add Actuator to inspect the startup timeline via **`GET /actuator/startup` (snapshot)** and **`POST /actuator/startup` (drain)**.
6. Understand the relationship between detailed startup step records, `ApplicationStartedEvent`, `ApplicationReadyEvent`, readiness, and total startup time.
7. Run a complete Maven application and test it with JUnit without depending on specific startup durations.
8. Identify misconfigured timing, buffer full conditions, 404 endpoints, data loss from draining, and security risks.

This lesson uses **Java 21, Spring Boot 3.3.13, Maven, and Spring Boot Actuator**. The example does not require a database or message broker.

## 2. Why Measure Startup Step by Step?

Suppose there are two startups:

```text
Run A: Started Demo in 2.1 seconds
Run B: Started Demo in 8.5 seconds
```

Looking only at total time does not reveal whether the difference comes from classpath scanning, bean creation, database migration, external calls in `@PostConstruct`, or waiting on an executor in `ApplicationRunner`.

When collecting startup steps, you can see technical names like:

```text
spring.boot.application.starting
spring.context.refresh
spring.beans.instantiate
```

These names are **examples of step types** during startup, not a guarantee that every application/version produces the exact same set of names and counts. Boot and Framework may add/remove measured steps across versions, depending on auto-configuration and context type.

A record in the timeline can carry:

| Field | Meaning |
| --- | --- |
| `startupStep.name` | Name of the measured action, usually dot-separated namespace |
| `startupStep.id` | Step identifier within the startup recording |
| `startupStep.parentId` | Parent step if any, representing nesting |
| `startupStep.tags` | Metadata such as bean name or operation type |
| `startTime` | Timestamp when the step started |
| `endTime` | Timestamp when the step ended |
| `duration` | Duration of the step |

**Do not sum all `duration` values to deduce startup time**: steps can be nested or belong to the same larger phase. Summing parent and child durations double-counts, and parallel activity can push the sum of durations past wall-clock time.

## 3. Four Related Concepts

### 3.1. `ApplicationStartup`

Spring Framework interface:

```java
package org.springframework.core.metrics;

public interface ApplicationStartup {
    StartupStep start(String name);
}
```

This is an **illustration of the main contract**, not a file you need to define yourself. When Framework or application code calls `start(name)`, it opens a startup step. That step is completed via `StartupStep.end()`.

`ApplicationStartup.DEFAULT` is the default implementation with very low overhead; it does not mean timeline data will automatically be buffered or exposed to Actuator.

### 3.2. `StartupStep`

`org.springframework.core.metrics.StartupStep` represents a unit of work:

```java
StartupStep step = startup.start("demo.bootstrap.check");
try {
    // Operation to measure.
    step.tag("component", "local-config");
}
finally {
    step.end();
}
```

This is an **illustrative code snippet inside a scope that already has `startup`**, not a standalone program. Step names should be namespaced, stable, and descriptive of the operation; tags should be small with a moderate number of distinct values. Do not put access tokens, passwords, sensitive data, or per-user data into tags.

**Do not forget `end()`**. For an unended step, the buffer does not have a properly completed end/duration record in the usual way; forgetting `end()` also distorts parent/child relationships of subsequent steps.

### 3.3. `BufferingApplicationStartup`

Full name:

```java
org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup
```

This implementation belongs to **Spring Boot**, not the `org.springframework.core.metrics` package (that package contains the `ApplicationStartup` and `StartupStep` interfaces).

Instantiation:

```java
BufferingApplicationStartup recorder =
        new BufferingApplicationStartup(2048);
```

The `2048` parameter is the **capacity in number of recorded steps**, not bytes, milliseconds, threads, or a time limit.

The recorder stores completed steps along with timestamps and durations. Once capacity is reached, **new steps are no longer recorded into the buffer** until an appropriate buffer-clearing action occurs. This is a data-completeness limit, not an error that stops the application from starting.

### 3.4. `StartupTimeline`

`org.springframework.boot.context.metrics.buffering.StartupTimeline` is a container holding:

- `getStartTime()` — the timeline start timestamp;
- `getEvents()` — the recorded `StartupTimeline.TimelineEvent` entries.

Each `TimelineEvent` has `getStartupStep()`, `getStartTime()`, `getEndTime()`, and `getDuration()`. `getStartupStep()` provides `getName()`, `getId()`, `getParentId()`, and `getTags()`.

Distinguish an **in-progress step** from a **completed and buffered event**. Do not expect to immediately see a step right after calling `start(...)` if `end()` has not yet been called.

## 4. How to Attach Properly to SpringApplication

This is the **core** code:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        BufferingApplicationStartup recorder =
                new BufferingApplicationStartup(2048);

        application.setApplicationStartup(recorder);
        application.run(args);
    }
}
```

Key steps:

1. Create a `SpringApplication` instance with the primary source class.
2. Create **one** `BufferingApplicationStartup` with an appropriate capacity.
3. Call **`application.setApplicationStartup(recorder)` before `application.run(args)`**.
4. Call `run` so Spring Boot uses the recorder for startup steps.

### 4.1. Why Not Use Only Static `SpringApplication.run(...)`?

The common shorthand:

```java
SpringApplication.run(DemoApplication.class, args);
```

is concise, but gives you no **opportunity to configure the `SpringApplication` instance** before it runs itself. If you want to attach a custom startup recorder, construct `new SpringApplication(...)`, call the setter, and then `run`.

This does not mean static `run` is wrong in every application. It simply does not directly satisfy the requirement here: **setting a specific `ApplicationStartup` before startup**.

### 4.2. Why Not Put It in @PostConstruct?

**Wrong timing:**

```java
@PostConstruct
void configureStartupLater() {
    // By this point Spring has already created/initialized this bean.
    // Many initial startup steps have already passed.
}
```

This snippet illustrates a timing mistake, not complete code. A `@PostConstruct`, `@Bean`, `ApplicationRunner`, or `ApplicationReadyEvent` listener runs **after startup has already begun**. Creating `BufferingApplicationStartup` only at that point cannot retroactively measure earlier steps.

### 4.3. No Need to Manually Call startRecording() on Every Run

The `new BufferingApplicationStartup(capacity)` constructor **already starts recording**. The API has `startRecording()`, but you do not need to call it out of habit. Once steps are recorded in the buffer, calling it again can throw `IllegalStateException`. Do not treat it as an arbitrary reset button while production is running.

### 4.4. Attach to the Right SpringApplication

In systems with multiple `SpringApplication` instances or a context hierarchy, attaching a recorder to one instance does not mean it tracks all independent contexts. Identify the exact instance calling `run(...)`, and interpret the timeline only in terms of the instrumented steps.

## 5. What Is BufferingApplicationStartup Used to Measure?

A condensed flow:

```text
new BufferingApplicationStartup(2048)
             |
             v
SpringApplication.setApplicationStartup(recorder)
             |
             v
SpringApplication.run(args)
   |
   +-- Environment and bootstrap
   +-- Create ApplicationContext
   +-- Load bean definitions
   +-- Refresh context
   |     +-- Bean instantiation
   |     +-- Context lifecycle callbacks
   |
   +-- ApplicationStartedEvent
   +-- ApplicationRunner / CommandLineRunner
   +-- ApplicationReadyEvent
             |
             v
StartupTimeline (completed steps)
             |
             +-- Java: getBufferedTimeline()
             +-- Java: drainBufferedTimeline()
             +-- Actuator: GET /actuator/startup
             +-- Actuator: POST /actuator/startup
```

**Important point:** the startup event flow above is the standard Spring Boot flow for context; it is **not a guarantee that every event has a `StartupStep` with the same name** or that every piece of code is automatically instrumented to the same depth.

If your code spawns a `Thread` and works for 20 seconds outside the measured lifecycle, the buffer does not automatically know everything inside that thread. To measure custom logic, add custom startup steps in the right places with clear completion.

## 6. Complete Maven Example with Spring Boot Actuator

The project will:

1. Explicitly instantiate `SpringApplication`.
2. Attach `BufferingApplicationStartup(4096)` **before `run()`**.
3. Run an HTTP server on port `8080`.
4. Enable the Actuator startup endpoint queryable from localhost.
5. Test with JUnit in non-web mode to verify buffer recording and draining without opening a port.

Note: the demo is designed for a **local development environment**. Because the startup timeline can contain bean names, main class, and internal structure information, do not expose this endpoint to the Internet without authentication, authorization, and network restrictions.

### 6.1. Directory Structure

```text
startup-buffer-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/startup/
    │   │   ├── StartupBufferApplication.java
    │   │   └── HelloController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/startup/
            └── StartupBufferTest.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>startup-buffer-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-web` provides the servlet HTTP server and Spring MVC. `spring-boot-starter-actuator` provides management endpoints. `spring-boot-starter-test` provides JUnit Jupiter.

### 6.3. StartupBufferApplication.java

File `src/main/java/com/example/startup/StartupBufferApplication.java`:

```java
package com.example.startup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class StartupBufferApplication {

    public static void main(String[] args) {
        BufferingApplicationStartup recorder =
                new BufferingApplicationStartup(4096);

        SpringApplication application =
                new SpringApplication(StartupBufferApplication.class);

        application.setApplicationStartup(recorder);
        application.run(args);
    }
}
```

This is the complete program. **There is no `recorder.drainBufferedTimeline()` in `main`** because we want steps to remain in the buffer so `/actuator/startup` can read them. If `main` drains right before an operator calls the HTTP endpoint, the startup data may no longer be there.

Do not use `new BufferingApplicationStartup(...)` as a replacement for a Spring application; the recorder is only the measurement component, while `SpringApplication` still handles context bootstrap.

### 6.4. HelloController.java

File `src/main/java/com/example/startup/HelloController.java`:

```java
package com.example.startup;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "hello";
    }
}
```

This controller provides a real web application and adds a bean for Spring to instantiate. Bean instantiation measurement may contain a tag for `helloController`, but you should not hardcode that bean name in startup API tests because instrumentation details can change across versions.

### 6.5. application.properties

File `src/main/resources/application.properties`:

```properties
spring.application.name=startup-buffer-demo
server.port=8080

management.endpoints.web.exposure.include=health,startup
```

**Distinguish:**

- The Actuator dependency puts the corresponding endpoints on Spring's classpath.
- `setApplicationStartup(recorder)` is the key requirement to **collect startup steps**.
- `management.endpoints.web.exposure.include=health,startup` is the configuration to **expose endpoints over HTTP** for the test environment.
- Enabling exposure **does not create a recorder automatically**. If you do not attach `BufferingApplicationStartup` before startup, `/actuator/startup` may not appear even though `startup` is listed under exposure.

In this demo, `spring-boot-starter-security` is not added, so exposed URLs are reachable on the application's HTTP port. **Run only locally or on a restricted test network; do not use this exact configuration in public production.**

### 6.6. Build and Run

Requires JDK 21, Maven, network access to download dependencies, and an available port `8080`.

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/startup-buffer-demo-0.0.1-SNAPSHOT.jar
```

In another terminal:

```bash
curl -i http://localhost:8080/hello
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/startup
```

With `HelloController`, the response body at `/hello` is:

```text
hello
```

With the demo's health endpoint having no failing health dependencies, you can expect JSON similar to:

```json
{"status":"UP"}
```

With `/actuator/startup`, the result is **dynamic JSON** containing actual steps. There is no fixed step count/duration/ID to copy and assume identical across all machines.

Example **abbreviated shape** (not exact stdout):

```json
{
  "springBootVersion": "3.3.13",
  "timeline": {
    "startTime": "actual-ISO-8601-timestamp",
    "events": [
      {
        "startTime": "actual-timestamp",
        "endTime": "actual-timestamp",
        "duration": "PT0.004S",
        "startupStep": {
          "name": "spring.beans.instantiate",
          "id": 3,
          "tags": [
            {
              "key": "beanName",
              "value": "helloController"
            }
          ]
        }
      }
    ]
  }
}
```

**Explanation:** the timestamp, duration, id, and tag value above only describe **payload structure**, not verified values from a specific run; an actual response can have many more steps, `parentId`, and many other tags. Do not use this hypothetical snapshot as expected output in automated tests.

## 7. GET Snapshot and POST Drain Are Two Different Operations

In Spring Boot 3.3, the Actuator startup endpoint allows two HTTP methods:

| Request | Purpose | Effect on buffer |
| --- | --- | --- |
| `GET /actuator/startup` | View collected startup steps | **Does not remove** data |
| `POST /actuator/startup` | Return steps and **drain** the buffer | **Removes** retrieved steps |
| `GET` after `POST` | View current buffer state | Few or no events may remain |

Example running against the local app:

```bash
curl -sS http://localhost:8080/actuator/startup
curl -sS http://localhost:8080/actuator/startup
curl -sS -X POST http://localhost:8080/actuator/startup
curl -sS http://localhost:8080/actuator/startup
```

The first two GET commands read a snapshot without intentionally draining. The POST command retrieves and drains buffered events. The final GET usually returns empty `events` if no further steps were recorded; **do not treat a count of zero as an invariant when concurrent recording activity may still happen**.

### 7.1. Why Not Use POST Just to Inspect?

A dashboard or API test using POST can **wipe out buffered data** that another tool intended to collect. If you only want to observe, use GET. Use POST only when intending to collect and drain data, such as a diagnostics system that already persists the response elsewhere.

### 7.2. Unexpected Error Status Codes

If calling GET returns `404`, common causes are:

- `spring-boot-starter-actuator` has not been added.
- The endpoint has not been exposed via `management.endpoints.web.exposure.include`.
- `BufferingApplicationStartup` was not attached to the right `SpringApplication` before `run`.
- The endpoint is disabled, unavailable, or served under a different base path/port.
- The application is not a web application; the demo has the web starter, yet a real system might select `WebApplicationType.NONE`.
- Proxy/routing sends the request to a different instance.

If you receive `401`/`403`, check security, authentication/authorization, and CSRF for POST operations; do not assume it is a recorder bug.

## 8. Using BufferingApplicationStartup Directly in Java

Actuator is not required if you only want to measure and process the timeline in code.

### 8.1. Reading a Snapshot

```java
BufferingApplicationStartup recorder =
        new BufferingApplicationStartup(2048);

SpringApplication app = new SpringApplication(DemoApplication.class);
app.setApplicationStartup(recorder);

ConfigurableApplicationContext context = app.run(args);
try {
    StartupTimeline snapshot = recorder.getBufferedTimeline();

    System.out.println("recorded steps: "
            + snapshot.getEvents().size());
}
finally {
    context.close();
}
```

The snippet above is an **integration example inside another class that has `DemoApplication`, `args`, and required imports**; it is not a standalone program. `getBufferedTimeline()` provides a snapshot of currently existing events **without removing them**.

In a multi-threaded system still recording steps, the snapshot is a point-in-time capture; it does not automatically become a record of all steps created in the future.

### 8.2. Reading Timeline and Fields

```java
StartupTimeline timeline = recorder.getBufferedTimeline();

for (StartupTimeline.TimelineEvent event : timeline.getEvents()) {
    System.out.println(
            event.getStartupStep().getName()
            + " duration=" + event.getDuration());
}
```

This is an **illustrative snippet using the `recorder` variable**. `getDuration()` returns `java.time.Duration`. The order and number of lines depend on the app; do not assert a fixed count of bean steps.

To find the longest steps, you can build a list and sort by `event.getDuration()`, remembering this is elapsed time per step, not necessarily root-cause CPU or I/O. Inspect tags, parent-child nesting, thread activity, and other measurements before concluding.

### 8.3. Draining in Java

```java
StartupTimeline drained = recorder.drainBufferedTimeline();
int count = drained.getEvents().size();

System.out.println("drained events: " + count);
System.out.println("remaining events: "
        + recorder.getBufferedTimeline().getEvents().size());
```

The lines above are **illustrative**. If no new threads record steps concurrently, a snapshot after drain is usually empty. `drainBufferedTimeline()` is not a "non-destructive snapshot" API; avoid calling it from two independent consumers if each expects full startup data.

### 8.4. Do You Need to Create a Bean for the Recorder?

The most accurate approach for measuring **the entire Spring Boot run** is attaching the recorder to `SpringApplication` **before `run`**, as in the main example. Do not just do:

```java
@Bean
BufferingApplicationStartup recorder() {
    return new BufferingApplicationStartup(2048);
}
```

This is an **insufficient example for the goal**, because the bean is created during context initialization, when many startup steps have already passed. Adding `@Bean` does not replace `setApplicationStartup`. Spring Boot can expose the already-attached startup implementation to appropriate components, so you do not need to create a second recorder yourself to read the timeline: reading a different recorder from the one that was set may show an empty buffer or wrong data.

## 9. Recording a Custom StartupStep

Built-in Framework startup steps do not automatically explain every business task. When an important app step needs measuring, you can record a custom step on the **same recorder**.

Example of an existing operation during Java bootstrap:

```java
BufferingApplicationStartup recorder =
        new BufferingApplicationStartup(2048);

StartupStep verifyStep =
        recorder.start("demo.bootstrap.verify-local-config");
try {
    verifyLocalConfiguration();
    verifyStep.tag("result", "ok");
}
finally {
    verifyStep.end();
}

SpringApplication application = new SpringApplication(DemoApplication.class);
application.setApplicationStartup(recorder);
application.run(args);
```

This is a **non-standalone illustration**: `verifyLocalConfiguration()`, `DemoApplication`, and imports must be defined. Work executed before `run` is retained by the recorder because it uses the exact same instance; Spring Boot steps continue to be recorded when `run` starts.

### 9.1. How Should Names and Tags Be Chosen?

Step names should represent stable operations:

```text
demo.bootstrap.verify-local-config
demo.cache.warmup
demo.schema.validate
```

Useful tags might be `component=cache`, `mode=local`, `result=ok`. Avoid using order IDs, emails, tokens, paths containing secrets, or thousands of varying values as tags, because they can leak via the endpoint and cause cardinality explosions when analyzing metrics.

### 9.2. Ensure Every Branch Calls end()

A very easy bug to hit:

```java
StartupStep step = recorder.start("demo.preflight");
if (!configurationExists()) {
    return; // WRONG: step has not ended.
}
step.end();
```

This is an illustrative anti-pattern. Use `try/finally`; do not create a step and allow an exception path or early return to skip `end()`.

### 9.3. What If the Step Is Asynchronous?

If a method only submits a `CompletableFuture` and returns, the duration measured around submission is **not the job completion time**. To measure true completion, choose the end point according to the completion contract, coordinate concurrency, and avoid races/cross-thread misinterpretation. Do not assume `StartupStep` can be held like an arbitrary stopwatch across threads without checking the implementation.

If a task is awaited inside an `ApplicationRunner`, a startup step can measure the actual wait interval and then verify the result. However, if the task only runs in the background and Boot emits `ApplicationReadyEvent` before it completes, a short step does not prove the app is business-ready.

## 10. Managing Capacity and Overhead

### 10.1. Capacity Is Event Count, Not Time

`new BufferingApplicationStartup(2048)` limits the number of buffered steps. If an application has very many beans, auto-configurations, or custom startup steps, 2048 may not be enough to retain the entire process.

When full, new steps **are not stored further**; the application can still start normally, yet the timeline misses later portions. Therefore:

- Choose capacity based on step counts measured in representative runs.
- During a profiling pass, you can raise it to 4096 or higher if the memory budget allows.
- Keep only needed step names using filters when the analysis target is clear.
- Drain data at appropriate times if a continuous collection consumer exists.
- Avoid interpreting "few steps in timeline" as "the app did little startup work".

### 10.2. Filtering Steps

`BufferingApplicationStartup#addFilter(Predicate<StartupStep>)` lets you filter which steps are retained:

```java
BufferingApplicationStartup recorder =
        new BufferingApplicationStartup(4096);

recorder.addFilter(step ->
        step.getName().startsWith("spring.beans."));
```

This is an illustrative snippet, which can be placed **before attaching the recorder and running the application**. With this filter, steps outside `spring.beans.*` may no longer appear in the timeline; this is **by selection**, not because the Framework skipped those steps.

Multiple filters are combined by requiring all conditions to hold together. Do not apply a filter after recording has finished and expect it to delete old data automatically.

### 10.3. Filtering Can Lose Context

If you keep only bean instantiation steps, you may lose higher-level steps representing the refresh lifecycle. Then `parentId` may reference a step that was not saved due to filtering. This is not necessarily corrupted data; it is the result of the filtering policy.

Depending on the goal, save the full set for initial investigation; narrow the filter only in subsequent passes.

### 10.4. The Buffer Is Not a Tracing Backend

`BufferingApplicationStartup` is an in-memory buffer, not a long-term startup data store, not a distributed tracing backend, and does not automatically ship steps to an observability platform. To retain/compare across deployments, actively collect JSON/timelines and store them appropriately with security and retention policies.

### 10.5. Do Not Enable Too Broadly in Production

Startup collection has overhead (time and memory) and can expose application topology. When profiling production:

- Measure impact via tests on staging/production-like environments.
- Bound capacity, keeping only data needed for analysis.
- Control who can invoke the endpoint.
- Do not expose sensitive endpoints publicly.
- Disable profiling or filter when no longer needed.

## 11. GET/POST Is Not the Same as Restarting the Application

A common misconception is that `POST /actuator/startup` will "re-measure startup" or "restart the app". **Incorrect.** In Spring Boot 3.3, POST returns the timeline and drains the existing buffer. It does not call `SpringApplication.run` again, does not refresh the context, and does not restart beans.

Similarly, GET only views a snapshot; it does not begin a new measurement. To compare cold startup against warm startup, you need **separate launches** under equivalent controlled conditions.

### 11.1. Distinguishing Startup Timeline from Total Startup Time

Other signals exist:

- Log `Started ... in ... seconds`: overall startup time overview.
- `ApplicationStartedEvent#getTimeTaken()`: time to the started milestone (after refresh, before runners) if available.
- `ApplicationReadyEvent#getTimeTaken()`: time to the ready milestone (after runners) if available.
- `ApplicationStartup`/`StartupStep`: fine-grained instrumented work intervals.

Do not treat a final step's duration as total startup time if that step only measured one portion. Nor should you naively compare the sum of all event durations with actual JVM time.

### 11.2. Startup Snapshot Differs from Readiness and Health

A startup endpoint returning 200 with many steps does not mean the instance is currently healthy, ready to handle traffic, or that external dependencies are working. Readiness and liveness are a separate set of signals. An application can record a full timeline yet later enter a runtime failure; the startup recorder is not a live health monitor.

If the goal is knowing when the application is ready to accept new work, use `ReadinessState`/Actuator probes and appropriate business checks; do not rely solely on startup event counts.

## 12. JUnit Verification of Attaching the Recorder

Tests should prove the recorder was applied **before startup**, steps were recorded, snapshots do not remove data, and drain empties the retrieved items. Avoid hardcoding assertions that there must be exactly `179` or `542` events: the count depends on classpath, configuration, environment, and versions.

File `src/test/java/com/example/startup/StartupBufferTest.java`:

```java
package com.example.startup;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.boot.context.metrics.buffering.StartupTimeline;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StartupBufferTest {

    @Test
    void recordsStartupStepsAndSupportsSnapshotAndDrain() {
        BufferingApplicationStartup recorder =
                new BufferingApplicationStartup(4096);

        SpringApplication app =
                new SpringApplication(StartupBufferApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setApplicationStartup(recorder);

        try (ConfigurableApplicationContext context = app.run(
                "--spring.main.banner-mode=off",
                "--logging.level.root=ERROR")) {

            assertTrue(context.isActive());

            StartupTimeline first = recorder.getBufferedTimeline();
            List<StartupTimeline.TimelineEvent> events = first.getEvents();

            assertFalse(events.isEmpty());

            assertTrue(events.stream()
                    .anyMatch(event -> event.getStartupStep()
                            .getName().startsWith("spring.")));

            StartupTimeline second = recorder.getBufferedTimeline();
            assertEquals(events.size(), second.getEvents().size());

            StartupTimeline drained = recorder.drainBufferedTimeline();
            assertEquals(events.size(), drained.getEvents().size());

            assertTrue(recorder.getBufferedTimeline().getEvents().isEmpty());
        }
    }
}
```

Explanation:

1. The test creates a **dedicated recorder** for this startup.
2. `setApplicationStartup(recorder)` is called **before `app.run(...)`**.
3. The test uses `WebApplicationType.NONE` to avoid opening an HTTP port, even though the project has the web starter on the classpath.
4. `getBufferedTimeline()` returns a snapshot; two reads do not lose steps.
5. `drainBufferedTimeline()` returns data and removes it from the buffer; after drain, when no more steps are recorded, the snapshot is empty.
6. It does not depend on specific durations/IDs, making the test more stable.

Run:

```bash
mvn test
```

Expect **one JUnit test** to succeed with this project when dependencies can be downloaded and no unexpected configuration interferes. To test Actuator HTTP `GET`/`POST` end-to-end, use a separate web test or `curl` as in section 7; this test does not open an HTTP endpoint and does not test HTTP security.

**Note when extending the test:** the context may record startup steps from asynchronous callbacks or dedicated components. In that case, asserting "snapshot is empty immediately after drain" requires synchronization or bringing the app to a state where no further steps are recorded. In the current demo, we do not create custom background startup steps.

## 13. How to Read the Timeline to Find Issues

When receiving timeline JSON from `/actuator/startup`, analyze systematically:

1. Record the commit, JDK, Boot version, profiles, CPU/RAM, and runtime environment.
2. Save a snapshot before changing code to establish a baseline.
3. Find steps with large durations; group by name and tags.
4. Inspect `parentId` to identify which phase a step belongs to.
5. Avoid summing parent and child durations.
6. Check for missing steps due to filters/capacity.
7. Combine with CPU profiler, JFR, thread dumps, GC logs, and DB/network traces if slowness is infrastructure-related.
8. Run multiple times, separating cold-start and warm-start, examining distributions rather than a single sample.
9. Compare under identical conditions; do not conclude an optimization worked just because one run was faster.
10. Put changes into tests to re-measure performance and verify normal startup functionality.

### 13.1. A Bean Has a Long Duration

If `spring.beans.instantiate` for a bean shows a high duration, it only tells you Spring measured significant elapsed time while creating/initializing that bean. Causes could be the constructor, `@PostConstruct`, dependency chain, factory method, external I/O, or another class called indirectly.

Do not conclude "slow constructor" based only on the step name without checking dependencies and timestamps.

### 13.2. A Step Wraps an External Call

If an init method calls an external service with a 10-second timeout, the duration may include network wait. The startup recorder does not automatically distinguish DNS, TCP connect, TLS handshake, DB locks, or CPU work in detail. Add network traces, client metrics, or JFR if you need to break down the cause.

### 13.3. Lazy Initialization Configuration

When `spring.main.lazy-initialization=true` is enabled, startup may be faster because some beans are not yet created. However, the cost can shift to the **first request**, and configuration errors surface later. A shorter timeline does not automatically mean better user-perceived latency.

## 14. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `GET /actuator/startup` returns 404 | Actuator not added, endpoint not exposed, or recorder not attached | Check dependency, property, and setter before `run` |
| `GET` returns many steps, `POST` then `GET` is nearly empty | POST drained the buffer | Use GET for non-destructive reading |
| Timeline has very few steps | Buffer too small, filter too narrow, or already drained | Increase capacity carefully; check filters and who called POST |
| `@Bean BufferingApplicationStartup` misses early steps | Bean was created during startup | Set directly on `SpringApplication` before `run` |
| Creating recorder after `SpringApplication.run(...)` | Too late | Create before bootstrap |
| Calling `startRecording()` arbitrarily | Constructor already started recording; calling again after recording can error | Do not call without reason and understanding the contract |
| Custom step does not appear | Forgot `end()` or used a different recorder | `try/finally`, same instance |
| Duration differs across runs | JIT, GC, I/O, CPU, classloading, caches | Measure multiple times under equivalent conditions |
| Total step duration exceeds startup wall time | Nested steps double-counted | Inspect parent/child and intervals, do not sum raw |
| Data present yet app still not ready | Startup recorder is not a readiness probe | Use availability/health separately |
| `POST` gets 403 | Spring Security/CSRF or policy | Check permissions and security config, do not open publicly |
| GET does not show many business steps | Framework only instruments instrumented points | Create custom steps at the right times |
| Setting filter after startup finishes | Does not alter old data | Set filter before `run` |
| Mixing data from two instances | Load balancer routed GET to a different pod | Collect by instance ID/pod |
| Timeline exposes bean/config names | Endpoint exposure too broad | Restrict network, authentication, and authorization |
| Confusing `ApplicationStartup` with `ApplicationReadyEvent` | One is step measurement, the other is a lifecycle event | Define measurement targets and readiness separately |

### 14.1. Quick Diagnostic Checklist

1. Are you sure the `SpringApplication` calling `run` is the exact instance on which `setApplicationStartup` was called?
2. Was the setter called **before** startup began?
3. Was `BufferingApplicationStartup` imported from the right package `org.springframework.boot.context.metrics.buffering`?
4. Did you use a constructor with a positive and sufficiently large capacity?
5. Is there a second `@Bean` causing recorder confusion?
6. Did anyone call `drainBufferedTimeline()` or HTTP POST earlier?
7. Is there a filter excluding the step names you want to measure?
8. Are both `spring-boot-starter-actuator` and the web starter present?
9. Is `startup` exposed via management properties?
10. Are port/base path/authentication/authorization/CSRF configured properly?
11. Is the endpoint going through a load balancer to a different pod?
12. Did someone else just read with POST and drain the data?
13. Are custom steps ended inside `finally`?
14. Are you trying to treat the event count as total readiness time?
15. Did you save a snapshot before restarting if you need to compare?
16. Did you check profiling overhead and avoid sensitive tags?

## 15. Exercises and Self-Check Questions

1. Does `ApplicationStartup` belong to Spring Framework or Spring Boot? Which package does `BufferingApplicationStartup` belong to?
2. Why must `setApplicationStartup` be called before `run`?
3. Distinguish between `StartupStep` and `StartupTimeline.TimelineEvent`.
4. What does capacity `2048` mean? Does it limit startup milliseconds?
5. If the buffer fills up, what happens to new steps and to Boot startup?
6. Why is creating a recorder in `@PostConstruct` too late to record initial steps?
7. From the demo source, replace capacity 4096 with 32 and compare the number of recorded steps.
8. Write a filter keeping only steps whose name starts with `spring.beans.`.
9. If a filter drops parent steps, can `parentId` still reference an unstored parent?
10. Distinguish GET and POST on `/actuator/startup`.
11. Why can calling POST before saving JSON cause data loss for another tool?
12. How does `getBufferedTimeline()` differ from `drainBufferedTimeline()`?
13. In tests, why not assert an exact step count or hardcoded duration?
14. Add custom step `demo.bootstrap.verify-local-config` and tag `result=ok`, ensuring `end()` in `finally`.
15. If an `ApplicationRunner` only submits an async task and returns, does the startup duration of the step measuring submission prove the task finished?
16. Why must durations of all events not be summed to deduce total time?
17. Across two different startups, which environment variables must be controlled to compare fairly?
18. If an app has `spring.main.lazy-initialization=true`, startup is faster, but what might become slower?
19. Does a long bean instantiation step guarantee the bean's constructor is slow?
20. If the startup endpoint returns JSON while `/actuator/health` returns an error, is that a contradiction?
21. In multi-pod Kubernetes, why must you know which instance returned the timeline?
22. Why must the Actuator startup endpoint be protected even though it cannot modify business data?
23. Create a unit test proving GET-like snapshot does not delete and POST-like drain empties the recorder.
24. When do you need JFR or a profiler alongside BufferingApplicationStartup?
25. Explain the difference between `ApplicationReadyEvent#getTimeTaken()` and timeline durations.
26. If you want to store 10 startups for regression analysis, propose a safe collection workflow with version, environment, timestamp, and retention.

**Success criteria:** able to run the Spring Boot 3.3 project, understand accurately how to attach the recorder before startup, query GET/POST with proper semantics, explain buffer/filter behavior, and know how to use the timeline for investigation without confusing it with readiness or business metrics.

## 16. Official References

- Spring Boot 3.3 — SpringApplication / Application Startup Tracking: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — `SpringApplication#setApplicationStartup`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3.13 — `BufferingApplicationStartup`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html
- Spring Boot 3.3.13 — `StartupTimeline`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/metrics/buffering/StartupTimeline.html
- Spring Boot 3.3 — Actuator Startup Endpoint (GET/POST): https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html
- Spring Boot 3.3 — Actuator Endpoints/Exposure/Security: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Framework 6.1 — `ApplicationStartup`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/metrics/ApplicationStartup.html
- Spring Framework 6.1 — `StartupStep`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/metrics/StartupStep.html
- Spring Framework 6.1 — Java Flight Recorder startup implementation: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/metrics/jfr/FlightRecorderApplicationStartup.html
