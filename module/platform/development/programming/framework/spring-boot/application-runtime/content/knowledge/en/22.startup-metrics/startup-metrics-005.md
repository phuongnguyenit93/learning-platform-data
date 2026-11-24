# Buffer Limits and Lifecycle of Measurement Data in Spring Boot

## 1. Lesson Objectives

Spring Boot provides the `ApplicationStartup` mechanism to observe the steps `SpringApplication` and `ApplicationContext` perform during startup. Each step is represented by a `StartupStep` and can have a name, identifier, parent–child relationship, tags, and execution timing. A useful implementation is `BufferingApplicationStartup`: it keeps completed steps in memory for direct inspection or export via Actuator.

However, this data has a finite lifecycle. Beyond simply enabling measurement, operators must also answer:

- How many records does the buffer hold, and what is the unit of that limit?
- When full, are new steps discarded or do they overwrite old steps?
- When taking a snapshot via GET, is data deleted?
- When calling POST/drain, where does the data go?
- After a JVM restart, can you retrieve the old timeline?
- Does the absence of a step actually prove it never ran?

**Core rule:** `BufferingApplicationStartup` uses capacity measured in **the number of stored startup step events**, not bytes, milliseconds, or file size. When the buffer is full, new steps are not recorded; it is **not a ring buffer** that automatically evicts old steps. Snapshot only reads, whereas drain returns the data and removes the events from the buffer. There is no automatic persistent storage.

This lesson uses **Spring Boot 3.3.13, Spring Framework 6.1.x, Java 17+** as a reference baseline to avoid mixing behavior across versions.

## 2. Startup Measurement Components

| API or component | Role |
| --- | --- |
| ApplicationStartup | Interface that creates a StartupStep via start(name) |
| StartupStep | An instrumented step; has name, ID, parentId, tags, and end() |
| BufferingApplicationStartup | Implementation holding a bounded number of steps in RAM |
| StartupTimeline | Collection of TimelineEvents along with the timeline start time |
| StartupTimeline.TimelineEvent | Start time, end time, duration, and associated StartupStep |
| getBufferedTimeline() | Retrieves a snapshot without consuming the buffer |
| drainBufferedTimeline() | Retrieves and removes currently buffered events |
| addFilter(Predicate) | Retains only steps matching the filters |
| Actuator startup endpoint | Exports the timeline as JSON via GET or POST |
| FlightRecorderApplicationStartup | Sends startup steps to Java Flight Recorder, a different mechanism |
| Micrometer startup timers | application.started.time and application.ready.time: aggregate measurements |

Spring Boot does not automatically instrument every line of Java and every library. ApplicationStartup collects steps that Spring Framework, Spring Boot, or code intentionally records using this API. Work that runs without a StartupStep will not automatically appear in the timeline.

### Starting and Ending a Step

~~~java
StartupStep step = recorder.start("demo.load-cache");
try {
    warmUpCache();
} finally {
    step.end();
}
~~~

This is an illustrative snippet inside a method, requiring `import org.springframework.core.metrics.StartupStep` and a defined `warmUpCache()`. Placing `end()` in `finally` lets the recorder know the step completed even if the code throws an exception. Depending on recording behavior, a complete event may only be produced once the step ends; calling `start(name)` alone does not guarantee the timeline has `endTime` or `duration`.

A StartupStep can have tags attached:

~~~java
StartupStep step = recorder.start("demo.load");
step.tag("component", "pricing");
try {
    initializePricing();
} finally {
    step.end();
}
~~~

This is also illustrative code requiring a real `initializePricing()` service. Attach only non-sensitive metadata; avoid tokens, passwords, and customer data in tags.

## 3. Capacity Is an Event Count Limit, Not Byte Size

Creating the recorder:

~~~java
BufferingApplicationStartup recorder =
        new BufferingApplicationStartup(2048);
~~~

The parameter `2048` means the configured number of events to keep in the buffer. This is only an example value in the Spring Boot documentation, **not a default capacity for every application**. SpringApplication will not automatically create `BufferingApplicationStartup(2048)` merely because Actuator is present.

Suppose capacity is 3:

~~~text
Step A ends -> written to buffer: [A]
Step B ends -> written to buffer: [A, B]
Step C ends -> written to buffer: [A, B, C]
Step D ends -> buffer full, not recorded
Step E ends -> buffer full, not recorded
Snapshot    -> [A, B, C]
~~~

If a structure were designed as a ring buffer, it might hold C, D, E. However, **`BufferingApplicationStartup` does not use such a replacement policy**. Once full, new steps are skipped until space becomes available in the buffer. In concurrent execution, completion order can differ from start order, so do not equate "first in buffer" with "earliest started method".

### Impact When the Buffer Is Full

- The application can still start and reach `ReadinessState.ACCEPTING_TRAFFIC` normally.
- Observation data is incomplete, typically causing later-stage steps to be missing from the timeline.
- It does not mean Spring skipped creating beans or running runners.
- It does not guarantee `parentId` in an event still has a matching parent event if part of the timeline was dropped.
- No calculation can recover a step that was never written into the buffer.
- A response with exactly `capacity` events is a signal to check, **not absolute proof** that overflow occurred.

Capacity is a **count** limit, not maximum RAM. Events store timestamps, name strings, tags, and object structures, so heap consumption depends on content and the JVM; you cannot assert that 2048 events always occupy a fixed number of MB.

## 4. Data Lifecycle from Recorder Creation to Process Exit

~~~text
Create BufferingApplicationStartup(capacity)
                 |
                 v
Recorder starts recording
                 |
SpringApplication.setApplicationStartup(recorder)
                 |
SpringApplication.run(args)
                 |
Spring Framework / Boot creates StartupSteps
                 |
StartupStep.end()
                 |
  +-- filter does not match -> not recorded
  +-- buffer has room       -> record TimelineEvent
  +-- buffer full           -> ignore new event
                 |
                 v
JVM continues running
  |
  +-- getBufferedTimeline() -> snapshot, buffer unchanged
  |
  +-- drainBufferedTimeline() -> return events, remove from buffer
  |
  +-- more steps after drain -> can record more if room remains
  |
  +-- JVM exits / restarts -> RAM of old recorder is lost
~~~

**Three milestones to remember:**

1. **Before `SpringApplication.run`:** you must register `ApplicationStartup` to capture initial startup steps. Creating the recorder too late will not capture past history.
2. **After the app is Ready:** the buffer can remain alive in the same JVM for GET/POST or Java API access. If instrumented steps run after Ready, they may appear too, though this is not a new startup.
3. **After process exit/restart:** RAM data from the old recorder is gone. Only JSON files, collectors, or recordings exported to persistent storage preserve history.

With multiple Pods/replicas, each JVM has its own recorder. To compare rollouts, store each instance's ID, build version, profile, start time, and configuration alongside the data.

## 5. Read/Drain APIs and Storage Semantics

### `getBufferedTimeline()`: Snapshot

~~~java
StartupTimeline current = recorder.getBufferedTimeline();
int count = current.getEvents().size();
~~~

This is illustrative code with an existing recorder, requiring importing `StartupTimeline`. The method returns a snapshot of recorded events **without removing them** from the recorder. Calling it multiple times with no new steps/drains usually yields the same event count.

The snapshot is a separate object holding the event list. If code continues holding a reference to it, memory may still be retained even if the recorder is drained afterward.

### `drainBufferedTimeline()`: Retrieve and Remove Events

~~~java
StartupTimeline captured = recorder.drainBufferedTimeline();
int count = captured.getEvents().size();
~~~

This method returns currently buffered events and removes them from the buffer. If you then call `getBufferedTimeline()` and no new steps occurred, the event count will be 0. Events inside the `captured` object still exist while the caller holds a reference; draining **does not mean GC reclaims RAM immediately**.

After draining, the recorder can store new steps within its remaining capacity, but steps dropped when the buffer was full **are not automatically replayed**.

### `startRecording()`: Not an Arbitrary Reset Button

The `BufferingApplicationStartup` constructor starts recording. The `startRecording()` API is only valid under certain conditions; Spring Boot 3.3 Javadoc explicitly notes it can throw `IllegalStateException` if steps have already been buffered. Do not use it as a command to re-measure an already-started `ApplicationContext`, because calling the method does not re-create beans or refresh the context.

### `addFilter()`: Reducing Events Kept in the Buffer

~~~java
recorder.addFilter(step ->
        step.getName().startsWith("spring.beans."));
~~~

New filters are combined with existing filters using **AND**. Adding two mutually exclusive prefix conditions may retain zero steps. If you need OR, express OR inside the same predicate:

~~~java
recorder.addFilter(step ->
        step.getName().startsWith("spring.beans.")
        || step.getName().startsWith("spring.context."));
~~~

Filters should only be added **before run** so recording rules stay consistent. Filters do not delete previously recorded events and do not restore rejected events. If a filter keeps only bean creation steps, you can miss slowness causes in scanning, class loading, configuration, or other stages. Choose filters based on the measurement question.


## 6. Java 17 Example Verifying Capacity, Snapshot, Drain, and Filter

The example creates sequential steps manually so results are deterministic, without depending on how many beans a real app has. Place **`src/main/java/demo/BufferCapacityProof.java`** in the Gradle project from the next section:

~~~java
package demo;

import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.core.metrics.StartupStep;

public class BufferCapacityProof {

    public static void main(String[] args) {
        BufferingApplicationStartup recorder =
                new BufferingApplicationStartup(3);

        for (int i = 1; i <= 5; i++) {
            StartupStep step = recorder.start("demo.step." + i);
            step.end();
        }

        System.out.println("SNAPSHOT_ONE="
                + recorder.getBufferedTimeline().getEvents().size());
        System.out.println("SNAPSHOT_TWO="
                + recorder.getBufferedTimeline().getEvents().size());

        System.out.println("DRAINED="
                + recorder.drainBufferedTimeline().getEvents().size());
        System.out.println("AFTER_DRAIN="
                + recorder.getBufferedTimeline().getEvents().size());

        recorder.start("demo.after-drain").end();
        System.out.println("NEW_EVENT="
                + recorder.getBufferedTimeline().getEvents().size());

        BufferingApplicationStartup filtered =
                new BufferingApplicationStartup(3);
        filtered.addFilter(
                step -> step.getName().startsWith("demo.keep."));

        filtered.start("demo.skip.one").end();
        filtered.start("demo.keep.one").end();
        filtered.start("demo.skip.two").end();
        filtered.start("demo.keep.two").end();

        System.out.println("FILTERED="
                + filtered.getBufferedTimeline().getEvents().size());
    }
}
~~~

With Spring Boot 3.3.13 and sequentially ended steps, the lines printed by the program are:

~~~text
SNAPSHOT_ONE=3
SNAPSHOT_TWO=3
DRAINED=3
AFTER_DRAIN=0
NEW_EVENT=1
FILTERED=2
~~~

Line-by-line explanation:

- `SNAPSHOT_ONE=3`: five steps ended, only three fit in the buffer.
- `SNAPSHOT_TWO=3`: the second snapshot does not consume data.
- `DRAINED=3`: drain returns the exact three events present.
- `AFTER_DRAIN=0`: the recorder no longer holds the retrieved events.
- `NEW_EVENT=1`: the recorder continues accepting steps after drain; it does not recover the fourth and fifth steps that were dropped.
- `FILTERED=2`: only two steps named `demo.keep.` match the predicate.

**Determinism:** this is a sequential example without multiple threads contending for the buffer or ending steps out of order. With real startup, do not assert that an application always produces an exact fixed number of steps across versions.

## 7. Spring Boot 3.3 / Java 17 Project with Actuator Startup Endpoint

We create a complete web application to observe **actual Spring Boot startup events**, then perform GET and POST. Uses Gradle, Java 17, and Spring Boot 3.3.13.

### Directory Structure

~~~text
startup-buffer-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          StartupBufferDemo.java
          BufferCapacityProof.java
      resources/
        application.properties
~~~

### File settings.gradle

~~~groovy
rootProject.name = 'startup-buffer-demo'
~~~

### File build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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

tasks.register('bufferProof', JavaExec) {
    group = 'verification'
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'demo.BufferCapacityProof'
}
~~~

The `bufferProof` task only runs the standalone API example from section 6; `bootRun` runs the Spring Boot web application. Requires JDK 17+, compatible Gradle, and dependencies either cached or downloadable from the repository.

### File application.properties

~~~properties
spring.application.name=startup-buffer-demo
server.port=8080
management.endpoints.web.exposure.include=health,info,startup
~~~

The startup endpoint **is not in the default web exposure set**, so `startup` must be added to the list. This configuration is for a controlled lab environment; do not expose the endpoint publicly without proper authentication, authorization, and network policy.

### File StartupBufferDemo.java

~~~java
package demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupBufferDemo {

    public static void main(String[] args) {
        BufferingApplicationStartup startup =
                new BufferingApplicationStartup(2048);

        SpringApplication app =
                new SpringApplication(StartupBufferDemo.class);
        app.setApplicationStartup(startup);
        app.run(args);

        boolean recorded = !startup.getBufferedTimeline()
                .getEvents().isEmpty();
        System.out.println("BUFFER_NONEMPTY=" + recorded);
    }

    @Bean
    ApplicationRunner startupRunner() {
        return args -> System.out.println("RUNNER_COMPLETED");
    }
}
~~~

Key points:

1. `SpringApplication` is created explicitly, not using static `run` before the recorder is set.
2. **`setApplicationStartup(startup)` runs before `app.run(args)`** so Spring/Boot can record startup steps from the beginning of instrumented phases.
3. 2048 is an example capacity, not a mandatory value.
4. `getBufferedTimeline()` in `main` only snapshots without draining, so data remains available for Actuator.
5. `@Bean ApplicationRunner` is called before `SpringApplication.run` completes; the runner code does not create its own custom StartupStep.
6. Embedded Tomcat keeps running so you can use `curl`.
7. Do not create another `@Bean BufferingApplicationStartup`: Spring Boot already received the instance via `SpringApplication` and will use it for startup instrumentation.

### Running the Test

If the project has a Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If there is no Gradle wrapper yet compatible Gradle is installed:

~~~bash
gradle bootRun
~~~

The lines printed by the example itself, in order:

~~~text
RUNNER_COMPLETED
BUFFER_NONEMPTY=true
~~~

Spring Boot, Tomcat, or Gradle logs may interleave. Do not assert a specific app event count: the count depends on auto-configuration, profiles, classpath, framework version, and filters.

Run the standalone capacity proof:

~~~bash
./gradlew -q bufferProof
~~~

The expected output lines are the six lines at the end of section 6. This program does not open a web server.

## 8. GET /actuator/startup Is a Snapshot

After `bootRun` succeeds:

~~~bash
curl -i -X GET http://localhost:8080/actuator/startup
~~~

Spring Boot 3.3 Actuator returns JSON with a structure roughly like:

~~~json
{
  "springBootVersion": "3.3.13",
  "timeline": {
    "startTime": "2025-06-19T07:16:19.477Z",
    "events": [
      {
        "startTime": "2025-06-19T07:16:19.805Z",
        "endTime": "2025-06-19T07:16:19.810Z",
        "duration": "PT0.005S",
        "startupStep": {
          "id": 1,
          "name": "spring.beans.instantiate",
          "tags": [
            {
              "key": "beanName",
              "value": "exampleBean"
            }
          ]
        }
      }
    ]
  }
}
~~~

This is **illustrative JSON**, not required verbatim output. IDs, parentIds, timestamps, step names, tags, ordering, and event counts depend on runtime. Duration is in ISO-8601 format, e.g., `PT0.005S` is 5 milliseconds.

Call GET again:

~~~bash
curl -s -X GET http://localhost:8080/actuator/startup
~~~

Existing events **remain stored** if no other drain operation occurred. Do not infer that GET freed heap memory.

## 9. POST /actuator/startup Is a Drain

Send:

~~~bash
curl -i -X POST http://localhost:8080/actuator/startup
~~~

According to Spring Boot 3.3 REST API documentation, POST returns the timeline **and drains** the retrieved events from the buffer.

Immediately afterward, try again:

~~~bash
curl -s -X GET http://localhost:8080/actuator/startup
~~~

When no new steps occur after drain, the key part is:

~~~json
{
  "timeline": {
    "events": []
  }
}
~~~

This is an **abbreviated structural excerpt**, not the full JSON response because the real response also has `springBootVersion` and may have `timeline.startTime`.

**GET = non-destructive snapshot. POST = consumes data.** A second POST usually cannot replay events from the first POST; if new events occurred, it returns only the new ones.

If a collector receives a POST response yet fails to write it to a file/database, the buffer has already been drained and the data does not automatically return. Therefore, GET and save a verified copy before deciding to drain, or build a controlled export mechanism with clear data ownership.

## 10. Sizing Capacity for Real Applications

There is no single good capacity for every service. A project with few beans may need only a few hundred events, while a large project with many auto-configurations and modules may need more.

Recommended workflow:

1. Use a generous capacity in staging, such as 2048 or higher depending on the application.
2. Run with profiles, classpath, feature flags, and containers close to production.
3. GET a snapshot after startup and count `timeline.events`.
4. If the count approaches capacity, increase it and re-run to see whether additional steps appear.
5. If you need to retain multiple runs, **export to persistent storage** rather than keeping everything in RAM for days.
6. When studying only one kind of step, filter by appropriate name/tags to reduce event volume.
7. Benchmark instrumentation overhead, heap, GC, and JSON payload size.
8. Include build, commit, profile, pod, and cold/warm startup metadata for fair comparisons.

**Do not sum all durations to get total startup time.** Steps can be nested and parent-child intervals overlap; summing all durations easily double-counts. Use `parentId` relationships and the timeline to locate slow segments, and cross-check against other aggregate timings.


## 11. When Does a Step Fail to Appear?

An absent event can have several causes:

| Symptom | Possibility | What to check |
| --- | --- | --- |
| GET returns empty events right after startup | Recorder set late, filter blocked, un-instrumented | Main and `setApplicationStartup` before run |
| GET empty after a POST | Buffer was drained | Request history of team/collector |
| Event count equals capacity | Likely became full | Increase capacity and re-measure |
| Only `spring.beans.*` steps visible | Filter selected only beans | Configured predicate |
| Lazy bean missing | Bean not yet instantiated before Ready | Lazy initialization and first request |
| Custom step missing | Missing `end()`, different recorder, or filtered | StartupStep lifecycle, tags, capacity |
| ParentId cannot find parent | Filter/overflow dropped parent event | Do not treat a filtered timeline as a full tree |
| Timestamps out of ID order | Steps finished in different order than started | Rely on startTime/endTime/duration |
| No data after restart | RAM of old JVM was lost | Collector/file before termination |
| Only a few startup phases visible | Not every stage is instrumented | Catalog of StartupSteps supported by framework |

### Asynchronous Tasks and Lazy Beans

If an `ApplicationRunner` only submits an async task and returns, `ApplicationReadyEvent` can appear before that task finishes. `BufferingApplicationStartup` does not automatically connect background code steps unless they are instrumented. A lazy bean may be instantiated when the first request arrives after Ready; that is not the same as restarting the application. Thus state clearly whether you measure **Spring-defined startup** or also warm-up/background work.

### When Startup Fails

If bean init, context refresh, or a runner causes `SpringApplication.run` to fail before the web server/Actuator is ready, HTTP GET/POST may be unusable to export data. When the requirement is diagnosing very early startup failures, consider controlled programmatic export, logs, or **`FlightRecorderApplicationStartup`/JFR** instead of relying solely on an HTTP endpoint after Ready.

## 12. Distinguishing BufferingApplicationStartup from Micrometer Metrics

Spring Boot Actuator has aggregate metrics:

- **`application.started.time`**: time taken for the application to reach the started milestone.
- **`application.ready.time`**: time taken for the application to reach the ready milestone.

They differ from `StartupTimeline`:

| Characteristic | Startup timeline | Startup time metrics |
| --- | --- | --- |
| Granularity | Many StartupSteps, each with duration and tags | A few aggregate milestones |
| Memory | Bounded event buffer in the JVM | Configured meter registry |
| Retrieval API | `getBufferedTimeline` or GET startup | `/actuator/metrics` or metrics backend |
| Drain API | `drainBufferedTimeline` or POST startup | Unrelated to POST startup |
| Used for | Finding slow steps/beans/phases | Tracking trends across deployments |
| Data across restarts | Lost unless exported | Depends on whether registry/backend persists data |

`POST /actuator/startup` **is not a command to clear Micrometer startup timers**. Conversely, seeing `application.ready.time` does not prove every startup step was buffered. Do not substitute one tool for the other when deep diagnostics are needed.

## 13. When You Need JFR Instead of an In-RAM Buffer

**`FlightRecorderApplicationStartup`** is Spring Framework's implementation for Java Flight Recorder. It is useful when you need to correlate startup with JVM class loading, allocations, GC, thread activity, and other JFR events.

Illustrative configuration in `main`:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new FlightRecorderApplicationStartup());
app.run(args);
~~~

This is an excerpt, requiring import:

~~~java
import org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup;
~~~

and `MyApplication` is a real Spring Boot class.

Example enabling JFR on the JVM:

~~~bash
java -XX:StartFlightRecording:filename=recording.jfr,duration=15s -jar app.jar
~~~

JFR has its own lifecycle, recording policy, and output file. It is not simply a `BufferingApplicationStartup` with larger capacity; using JFR does not mean the `/actuator/startup` endpoint automatically provides a JSON timeline. If you want to GET/POST buffered data, use `BufferingApplicationStartup` per the verified guide.

## 14. Security and Ownership of Startup Data

The startup endpoint contains metadata that can disclose bean names, package names, framework components, and custom tags. **POST also mutates the buffer**, so it can cause other observability groups to lose data they need.

- Do not expose `startup` to the public Internet without authentication and authorization.
- Expose the endpoint only on an appropriate management network/namespace.
- Restrict **POST** permissions more tightly if collectors only need GET.
- Account for Spring Security and CSRF when configuring POST; do not arbitrarily disable CSRF system-wide.
- Do not put passwords, tokens, or customer information into StartupStep tags.
- Record which instance was measured, who drained it, and whether the result was saved successfully.
- Use a single owner/collector for draining; everyone else reads the exported copy.
- Inspect JSON contents before uploading to a third-party system.

Doing GET and copying the file is safer for one-off analysis. When POST is used as a handoff mechanism, it is not a transaction between the JVM buffer and destination storage: a failure after receiving the response can lose data.

## 15. Self-Check Questions

**Question 1:** Does `BufferingApplicationStartup(256)` mean 256 MB?  
**Answer:** No, capacity is the number of events/steps retained under the buffer policy.

**Question 2:** When the buffer is full, does it keep the most recent steps or the earliest recorded steps?  
**Answer:** The earliest recorded events; new steps do not automatically replace old steps.

**Question 3:** Does `getBufferedTimeline` delete data?  
**Answer:** No, it is a snapshot.

**Question 4:** How does `drainBufferedTimeline` differ from a snapshot?  
**Answer:** It returns the existing data and removes it from the buffer.

**Question 5:** Does calling `GET /actuator/startup` twice in a row lose old events?  
**Answer:** No, unless another party drained or the data changed for another reason.

**Question 6:** Is `POST /actuator/startup` safe to call as a test and then call again to get the exact same data?  
**Answer:** No. POST drains; there is no automatic replay.

**Question 7:** Why must `setApplicationStartup` be called before `SpringApplication.run`?  
**Answer:** Because startup steps that already passed cannot be retroactively recorded by a late-attached recorder.

**Question 8:** What reasons can explain an absent event?  
**Answer:** Not instrumented, filtered, buffer full, missing `end()`, already drained, or occurred in a different JVM run.

**Question 9:** Do multiple `addFilter` calls combine with OR or AND?  
**Answer:** AND; if OR is needed, write one predicate using the OR operator.

**Question 10:** Can all durations be summed to obtain total startup?  
**Answer:** Unreliable because steps can be nested/overlapping.

**Question 11:** After drain, while the recorder is still alive, can it receive new steps?  
**Answer:** Yes, if new steps are instrumented and capacity remains, though steps dropped before drain are not automatically replayed.

**Question 12:** When a pod restarts, does the old buffer remain?  
**Answer:** No, unless the data was exported to persistent storage.

**Question 13:** When an app fails before Actuator is Ready, can `/actuator/startup` reliably be called?  
**Answer:** No. Alternative logging/export/JFR strategies are needed if diagnosing startup failures is a primary requirement.

**Question 14:** Does POST startup clear the `application.ready.time` metric?  
**Answer:** No, they are two separate measurement mechanisms.

**Question 15:** When wanting to analyze class loading and GC alongside startup, which tool should be considered?  
**Answer:** Java Flight Recorder with `FlightRecorderApplicationStartup`.

## 16. Startup Measurement Implementation Checklist

1. Specify the exact Spring Boot and Java version, and read the API docs for the actual version.
2. Create `BufferingApplicationStartup` before `run` and attach it with `setApplicationStartup`.
3. Choose capacity based on actual step count, not inferred from byte size or time.
4. Ensure custom `StartupStep` instances call `end` in `finally` where needed.
5. If using filters, verify AND semantics and attach them before running.
6. Distinguish missing data caused by capacity, filtering, instrumentation, or draining.
7. Read snapshots with GET first; POST only when intentionally draining.
8. Store data together with build, profile, instance, timestamp, and startup conditions.
9. Do not treat the in-RAM buffer as persistent storage across restarts.
10. Protect the startup endpoint, especially POST permissions and custom tags.
11. Measure heap and response size when increasing capacity.
12. Do not sum nested durations as total startup time.
13. Cross-check against `application.started.time` and `application.ready.time`.
14. Have a JFR/logging plan if startup failure occurs before HTTP endpoints are reachable.
15. Verify collection across multiple Pods to avoid missing part of a rollout.

**Conclusion:** `BufferingApplicationStartup` has a buffer bounded by **the number of `StartupStep` events**; when full, new steps are not recorded further. **Snapshot/GET does not delete**; **drain/POST retrieves and deletes events** from the recorder. Data does not automatically survive a JVM restart. For reliable startup measurement, design **recording start point, capacity, filters, snapshot/drain lifecycle, security, persistent storage, and completeness checks** together, rather than just enabling Actuator and looking at one JSON response.

### References

- [Spring Boot 3.3: Application Startup Tracking](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3: BufferingApplicationStartup API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html)
- [Spring Boot 3.3: Actuator Startup REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html)
- [Spring Boot 3.3: Endpoints and Web Exposure](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3: Application Startup Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
