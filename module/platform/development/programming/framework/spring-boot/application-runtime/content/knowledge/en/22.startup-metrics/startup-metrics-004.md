# Reading Steps, Tags, and Parent-Child Relationships in Spring Boot Startup Data

**Module:** Spring Boot Application Runtime → **Startup Measurement**. This lesson explains how to read `ApplicationStartup` and `StartupStep` data: **step name**, **ID**, **key/value tags**, **parentId**, start/end timestamps, and `duration`. The focus is building the exact parent–child tree from Actuator `/actuator/startup` data, avoiding confusing array order with execution order, avoiding double-counting nested step durations, and knowing when the timeline alone is insufficient to conclude why startup is slow.

**Example:** Java **17+**, Spring Boot **3.5.x**, Spring Web, Spring Boot Actuator, Maven; includes Java code creating one parent step and two child steps in `ApplicationRunner` along with a standard-library-only Python 3 script to analyze the JSON file. Timestamps, IDs, and durations in illustrative diagrams **are not fixed stdout** of the application.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Describe the lifecycle `ApplicationStartup.start(name)` → `StartupStep.tag(...)` → `StartupStep.end()`.
2. Configure `BufferingApplicationStartup` **before** `SpringApplication.run(...)` to collect all instrumented steps during startup.
3. Use `GET /actuator/startup` to get a **snapshot** and `POST /actuator/startup` to **drain** the buffer.
4. Read `timeline.events[]`, `startupStep.name/id/parentId/tags`, and `startTime/endTime/duration` accurately.
5. Understand that `parentId` may be absent or reference a step not present in an excerpt; know how to build a tree by ID rather than sorting IDs.
6. Distinguish multiple `spring.beans.instantiate` entries by `beanName` tags.
7. Convert ISO-8601 duration string `PT0.012S` into **12 milliseconds**.
8. Distinguish **inclusive elapsed** of a parent from exclusive elapsed, and compute union intervals when children overlap in time.
9. Create parent step `lab.warmup` and two children `lab.warmup.load`, `lab.warmup.index`; correlate Java console markers with JSON.
10. Use `jq`/a script to print the tree, print tags, and rank durations **numerically**.
11. Understand buffer capacity limits, filters, multiple contexts/replicas, and the impact of GET/POST.
12. Know that startup step data **is not by itself a bean dependency graph, CPU profile, or critical path**.
13. Combine the timeline with JFR, logs, and repeated runs when identifying a startup bottleneck.
14. Deploy observability with access control, without leaking PII/secrets from tags.

**Key takeaway:** `id` identifies a step within one collection, `parentId` links the measurement structure, `name + tags` explain what was measured, and `start/end/duration` describe timing. Do not rely on just one of those fields to infer the entire startup.

## 2. What Are ApplicationStartup and StartupStep?

Spring Framework provides the `org.springframework.core.metrics.ApplicationStartup` interface. When recording a unit of work, call:

~~~java
StartupStep step = startup.start("lab.cache.warmup");
try {
    step.tag("component", "catalog");
    step.tag("entries", "500");
    // Perform work here.
} finally {
    step.end();
}
~~~

This is a **snippet** requiring a valid `ApplicationStartup startup` variable and `org.springframework.core.metrics.StartupStep` import; it is not a standalone Java file.

A `StartupStep` has:

| API | Role |
|---|---|
| `getName()` | Technical name of the step, typically `namespace.action` |
| `getId()` | Unique step ID within the startup/recorder |
| `getParentId()` | Parent step ID if any, may be `null` |
| `getTags()` | Collection of key/value tags for the step |
| `tag(String,String)` | Attaches a tag |
| `tag(String,Supplier<String>)` | Attaches a tag with a value provided by a supplier |
| `end()` | Marks the step finished so the recorder calculates duration |

Call `start(...)` **before** the work to measure, add tags before ending, and then call `end()` in `finally`. If you forget `end()`, the recorder may not have a completed event to supply a duration; do not just attach tags and assume the system closes the span automatically. Do not attempt to call `tag(...)` after `end`; the API contract requires that an ended step is no longer modified.

Step names should have a clear namespace like `lab.catalog.load`. Multiple steps **are allowed to share the same name** because the name specifies the **type of work**, not a unique instance. To identify a specific instance, read ID and tags.

### 2.1. Recorders

| Implementation | What does it record? | Where is it read? |
|---|---|---|
| `ApplicationStartup.DEFAULT` | Minimal/low-overhead default mode | Do not expect a detailed Actuator timeline |
| `BufferingApplicationStartup` (Spring Boot) | Steps, tags, timings in a bounded buffer | `/actuator/startup` or `StartupTimeline` API |
| `FlightRecorderApplicationStartup` (Spring Framework) | Startup events for Java Flight Recorder | JFR file/JDK Mission Control |

`BufferingApplicationStartup` is the sensible choice when learning how to read **JSON, tags, and parentId**. `FlightRecorderApplicationStartup` fits when you need correlation with CPU, GC, classloading, and JVM events; it is not an interchangeable JSON buffer variant without changing collection.

### 2.2. Where to Configure the Recorder?

It must be configured on `SpringApplication` before running:

~~~java
SpringApplication app =
        new SpringApplication(StartupLabApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(4096));
app.run(args);
~~~

`4096` is the **maximum number of steps stored in the buffer**, not byte size or milliseconds. When capacity is full, the recorder stops recording new steps; do not treat it as a ring buffer retaining the last 4096 steps. In large apps, the actual step count can exceed this threshold.

Creating `BufferingApplicationStartup` only inside a bean after startup is too late to record early phases. And merely declaring Actuator `startup` exposure while the app still uses the default recorder **is insufficient**.

## 3. JSON from Actuator /actuator/startup

Spring Boot 3.5 produces data equivalent to the following sample (with very many steps omitted):

~~~json
{
  "springBootVersion": "3.5.16",
  "timeline": {
    "startTime": "2026-11-09T08:00:00Z",
    "events": [
      {
        "startTime": "2026-11-09T08:00:00.100Z",
        "endTime": "2026-11-09T08:00:00.240Z",
        "duration": "PT0.140S",
        "startupStep": {
          "id": 100,
          "name": "lab.warmup",
          "parentId": 10,
          "tags": [
            {"key": "component", "value": "catalog"},
            {"key": "environment", "value": "local"}
          ]
        }
      },
      {
        "startTime": "2026-11-09T08:00:00.110Z",
        "endTime": "2026-11-09T08:00:00.155Z",
        "duration": "PT0.045S",
        "startupStep": {
          "id": 101,
          "name": "lab.warmup.load",
          "parentId": 100,
          "tags": [
            {"key": "dataSet", "value": "sample"}
          ]
        }
      },
      {
        "startTime": "2026-11-09T08:00:00.160Z",
        "endTime": "2026-11-09T08:00:00.225Z",
        "duration": "PT0.065S",
        "startupStep": {
          "id": 102,
          "name": "lab.warmup.index",
          "parentId": 100,
          "tags": [
            {"key": "index", "value": "prefix"}
          ]
        }
      }
    ]
  }
}
~~~

The JSON sample above **only illustrates the API**. Times, IDs, and durations measured by the JVM/runtime will vary. `parentId=10` of `lab.warmup` is a framework step omitted from the example. Do not treat the absence of id 10 in **this excerpt** as a system error.

### 3.1. Core Fields

| Path | Data type | Meaning |
|---|---|---|
| `springBootVersion` | String | Spring Boot version outputting the timeline |
| `timeline.startTime` | ISO-8601 timestamp String | Recording start milestone |
| `timeline.events` | Array | List of buffered events |
| `events[].startTime` | ISO instant | When the step started |
| `events[].endTime` | ISO instant | When the step ended |
| `events[].duration` | ISO-8601 Duration | Elapsed time of this step |
| `events[].startupStep.name` | String | Type of step measured |
| `events[].startupStep.id` | Number | Unique ID used to link steps |
| `events[].startupStep.parentId` | Number, optional | Parent step ID if any |
| `events[].startupStep.tags` | Array | List of key/value pairs |
| `tags[].key` | String | Label name, e.g., `beanName` |
| `tags[].value` | String | Label value, e.g., `myService` |

**Never default parentId to 0.** `StartupStep.getParentId()` returns a nullable `Long`. The serializer may **omit the parentId field** when there is no parent, while `id=0` (if present) is still a valid step ID. A parser should use `step.get("parentId")` and distinguish `null/missing` from the number 0.

### 3.2. Duration Is ISO Seconds, Not Milliseconds

Some examples:

| Duration string | Seconds | Milliseconds |
|---|---:|---:|
| `PT0.0005S` | 0.0005 | 0.5 |
| `PT0.012S` | 0.012 | 12 |
| `PT0.045S` | 0.045 | 45 |
| `PT0.125S` | 0.125 | 125 |
| `PT1S` | 1 | 1,000 |
| `PT1M3S` | 63 | 63,000 |

On Java 17:

~~~java
long millis = java.time.Duration.parse("PT0.125S").toMillis();
System.out.println(millis);  // 125
~~~

This is a Java snippet **placed inside a method**; to compile standalone, wrap it in a class with `public static void main`. Avoid misreading `PT0.012S` as "0.012 ms"; the `S` suffix denotes **seconds**.

### 3.3. Array Order of Events Is Not Parent–Child Order

A child can **appear before its parent in the JSON array** because it called `end()` before the parent; the official REST docs also illustrate that ordering. Therefore:

- Do not rely on the preceding element's position to pick a parent.
- Do not assume `id=100` must precede `id=101` in the array.
- Do not assume a larger ID means a step ran after a smaller-ID step **finished**.
- Do not infer relationships solely from two timestamps falling inside each other.
- Build an `id → step` index and link via `child.parentId`; then sort siblings by `startTime` if you want display ordering.

This is the difference between a **flat event list representation** and a **step tree**. The tree layout must be built by relationship linking, not by how the serializer orders elements.

## 4. Properly Understanding the parentId Relationship

### 4.1. Nesting Relationship Recorded by Instrumentation

The `StartupStep.getParentId()` Javadoc describes the parent as the most recently started step when the current step was created, according to recorder semantics. In Java:

~~~java
StartupStep parent = startup.start("lab.warmup");
try {
    StartupStep child = startup.start("lab.warmup.load");
    try {
        // Measure child work.
    } finally {
        child.end();
    }
} finally {
    parent.end();
}
~~~

Expected on the same thread/active recorder:

~~~text
lab.warmup        id=100
  lab.warmup.load id=101 parentId=100
~~~

This is an illustrative snippet requiring a valid `startup` variable. Child is created while parent has not yet ended. This structure means **nested measurement**, not that a bean declared a dependency via `@DependsOn`, not the Spring bean graph, and not a distributed trace across other services.

### 4.2. ID, name, and parentId Serve Different Roles

- `id` identifies **a step instance** within one recording.
- `name` identifies the step **type**; the same name can appear hundreds of times.
- `parentId` identifies the **parent step** by ID within the recorder.
- `tags` identify the specific instance/subject, e.g., `beanName`.
- `startTime/endTime` give the time interval.
- `duration` gives elapsed time, not yet CPU cost.

When comparing two startups, do not match by id because IDs can differ. Compare by **name + tags + measurement environment** and examine the duration distribution; avoid relying only on name when there are multiple instances.

### 4.3. Root and Unrecorded Parent

Cases encountered with `parentId`:

| Data | Interpretation | Handling |
|---|---|---|
| `parentId` absent/null | Step has no parent known to the recorder | Display top-level |
| `parentId=100` and id 100 exists in JSON | Clear link exists | Attach as child of 100 |
| `parentId=100` yet id 100 is absent | Snapshot/filters/capacity/partial excerpt | Label **missing parent** |
| `parentId=0` | Parent is step ID 0 if it exists | Do not convert to null |
| `parentId` points to its own ID | Corrupted data | Report error, do not construct a cycle |
| Duplicate IDs in the same file | Corrupted data or wrongly merged files | Do not silently overwrite in dictionary |

If you filter only steps whose name starts with `lab.`, the parent of `lab.warmup` may be a framework step that was **filtered out of display** yet still exists in the JSON; that is not "missing raw data". Distinguish **missing from data** from **not selected**.

### 4.4. Concurrent Steps

If steps are created by multiple threads, intervals can overlap. One time interval falling inside a parent's interval **does not automatically prove** its parentId must point to that parent. Rely only on `parentId` actually recorded by instrumentation. In systems with async bootstrap and context propagation, do not assume parent context automatically propagates across every thread pool.

A tree indicates **instrumentation-recorded relationships**, not the full graph of CPU, locking, futures, or service calls. When identifying the critical path or cross-thread causality, supplement with JFR, a profiler, tracing, or correlated logs.

## 5. Reading Tags to Distinguish Steps with the Same Name

Two example events:

~~~json
{
  "id": 21,
  "name": "spring.beans.instantiate",
  "parentId": 4,
  "tags": [{"key": "beanName", "value": "orderService"}]
}
~~~

~~~json
{
  "id": 22,
  "name": "spring.beans.instantiate",
  "parentId": 4,
  "tags": [{"key": "beanName", "value": "dataSource"}]
}
~~~

Both steps have the **same name** yet different `beanName` values, reflecting different beans. To identify a slow bean, inspect the duration of the enclosing event and then check the `beanName` tag.

**Tags are an array**, not a map:

~~~json
"tags": [
  {"key": "component", "value": "catalog"},
  {"key": "stage", "value": "preload"}
]
~~~

Read each item by `key`, `value`. Converting to a dictionary can lose data if multiple tags share a key; retain the list when exact verification is needed. Do not put passwords/tokens/full SQL/request bodies/PII into tag values because the startup endpoint can expose this metadata. Use technical names and low-cardinality labels.

### 5.1. Do Custom Tags Slow Down Startup?

Attaching short string tags has minimal overhead, but if computing the value queries a DB, reads a large file, or calls a remote API, obtaining the metadata itself can slow down and skew the measurement. `StartupStep.tag(String,Supplier<String>)` lets some recorders evaluate values lazily, but do not turn the supplier into a heavy operation.

Place measurements close to the code you want to understand and use cheap metadata. If you do not need a particular tag to distinguish steps, do not add it just to "fill columns".

## 6. Inclusive Duration, Exclusive Duration, and Bottlenecks

A parent step starts before its child steps and ends after them. **The parent's duration is inclusive elapsed**, so it already encompasses its children.

~~~text
Parent: [================================]  150 ms
Child A:    [==========]                    45 ms
Child B:                  [=============]   65 ms
~~~

With non-overlapping children, example calculation:

- Parent inclusive = 150ms.
- Child A = 45ms, child B = 65ms.
- Parent time outside both children, if no other measured span exists = `150 - 45 - 65 = 40ms`.
- **Wrong:** Total startup of this segment is 150 + 45 + 65 = 260ms, because child time is added twice.

### 6.1. When Children Overlap, You Cannot Subtract the Sum of Durations

Example:

~~~text
P: [0ms ................................... 100ms]
A:     [10ms ................. 70ms]        60ms
B:                [40ms ................ 95ms] 55ms
~~~

A and B overlap by **30ms**; the union of child intervals has length `60 + 55 - 30 = 85ms`. The parent's exclusive elapsed portion is `100 - 85 = 15ms`. Naive subtraction `100 - 60 - 55 = -15ms` is wrong.

To calculate properly: take child intervals, clamp within the parent interval, sort by start, merge overlapping intervals, compute the union; then subtract the union from parent inclusive duration. Still explain that **exclusive elapsed** is not **CPU time**: the parent could be waiting on I/O without consuming CPU.

### 6.2. Do Not Sum All Step Durations into "Startup Time"

Comparison table:

| Metric | Meaning | Can it be summed simply? |
|---|---|---|
| Inclusive step duration | Elapsed time from `start` to `end` | No if nested/overlapping |
| Parent exclusive elapsed | Interval portion not covered by direct children | Requires union of intervals |
| CPU time | CPU execution time | Cannot be inferred directly from event duration |
| Critical path | Work chain determining end-to-end latency | Requires dependency/concurrency analysis |
| Startup-to-ready | From process/Boot start to ready | Not inherently equal to any step duration |
| Total step count | Volume of data captured by the recorder | Does not prove the app is fast/slow |

A top duration may be a parent wrapper. Always drill down into children and tags. A 600ms step may be 580ms waiting on a database, not a Java block using 600ms of CPU.

## 7. Runnable Demo: Java 17, Spring Boot 3.5, Web + Actuator

### 7.1. Project Structure

Create a Spring Initializr or Maven project:

- Group `com.example`, artifact `startup-steps-lab`.
- Package `com.example.startupsteps`.
- Java 17, Spring Boot 3.5.x.
- Dependencies: Spring Web, Spring Boot Actuator.
- Packaging JAR.

~~~text
startup-steps-lab/
  pom.xml
  mvnw                  (if using Maven Wrapper)
  mvnw.cmd
  src/main/java/com/example/startupsteps/
    StartupStepsLabApplication.java
    WarmupRunner.java
  src/main/resources/application.properties
~~~

`pom.xml` below uses Spring Boot **3.5.16** as a concrete 3.5.x release. If an enterprise repository has another approved version, adjust the parent version accordingly and re-verify APIs.

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>startup-steps-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
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
~~~

Use Maven to manage the Spring classpath; do not run `javac` on a single file without the libraries. If Initializr created a Maven Wrapper, keep the files and use `./mvnw`; otherwise, use an installed `mvn`.

### 7.3. Main: Attach Recorder Before Run

File `StartupStepsLabApplication.java`:

~~~java
package com.example.startupsteps;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class StartupStepsLabApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupStepsLabApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(4096));

        application.run(args);
    }
}
~~~

**Do not** use the shorthand `SpringApplication.run(StartupStepsLabApplication.class, args)` if you need to set the recorder programmatically in Java before run. One normal run suffices; do not refresh the context a second time just to emit steps.

### 7.4. Runner: One Parent and Two Children

File `WarmupRunner.java`:

~~~java
package com.example.startupsteps;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.metrics.ApplicationStartup;
import org.springframework.core.metrics.StartupStep;
import org.springframework.stereotype.Component;

@Component
public final class WarmupRunner implements ApplicationRunner {

    private final ApplicationContext applicationContext;

    public WarmupRunner(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        ConfigurableApplicationContext context =
                (ConfigurableApplicationContext) applicationContext;
        ApplicationStartup startup = context.getApplicationStartup();

        StartupStep parent = startup.start("lab.warmup");
        parent.tag("component", "catalog");
        parent.tag("environment", "local");

        System.out.println("LAB_PARENT id=" + parent.getId()
                + " parentId=" + parent.getParentId());

        try {
            measureChild(
                    startup, "lab.warmup.load",
                    "dataSet", "sample", 40);
            measureChild(
                    startup, "lab.warmup.index",
                    "index", "prefix", 80);
        } finally {
            parent.end();
            System.out.println("LAB_PARENT_END id=" + parent.getId());
        }
    }

    private static void measureChild(
            ApplicationStartup startup, String name,
            String tagKey, String tagValue, long millis)
            throws InterruptedException {

        StartupStep child = startup.start(name);
        child.tag(tagKey, tagValue);

        System.out.println("LAB_CHILD id=" + child.getId()
                + " name=" + child.getName()
                + " parentId=" + child.getParentId());

        try {
            Thread.sleep(millis);
        } finally {
            child.end();
            System.out.println("LAB_CHILD_END id=" + child.getId());
        }
    }
}
~~~

**Reading the code by lifecycle:**

1. `ApplicationRunner` runs after `ApplicationContext.refresh()` and before `ApplicationReadyEvent` on a successful startup.
2. Injecting `ApplicationContext` is normal; the Spring Boot context in the demo also implements `ConfigurableApplicationContext` to retrieve `getApplicationStartup()`.
3. Parent `lab.warmup` is created and kept **open** while creating the two children.
4. Children `lab.warmup.load` and `lab.warmup.index` are both created on the same thread while the parent has not ended; `child.getParentId()` matches the parent ID.
5. Parent has two tags; each child has one tag distinguishing its work.
6. `Thread.sleep(40)`/`Thread.sleep(80)` are simulated delays to make durations easy to observe, **not exact duration guarantees**; JVM scheduling/logging/GC can increase the time.
7. `end()` in `finally` ensures the step finishes even on `InterruptedException`.
8. `parent.getParentId()` may point to an open framework step or be null depending on the recorder. Do not hardcode the value.
9. Console markers help correlate JSON `id/parentId` without guessing from names or array positions.
10. The demo makes no real DB/network calls, so do not attribute the delay results to external bottlenecks.

### 7.5. Actuator Configuration

File `application.properties`:

~~~properties
spring.application.name=startup-steps-lab
server.address=127.0.0.1
server.port=8080

management.endpoints.web.exposure.include=health,startup
management.endpoint.startup.access=unrestricted
~~~

`management.endpoints.web.exposure.include` exposes the `startup` endpoint over HTTP. `management.endpoint.startup.access=unrestricted` allows both GET snapshot and POST drain in the Spring Boot 3.5 lab, unless a global policy or Spring Security/CSRF restricts access. By default not all Actuator endpoints are exposed on the web; **do not** set `include=*` just to view startup.

`server.address=127.0.0.1` restricts the local lab, avoiding exposing bean metadata to the network. When running in Kubernetes/containers, adjust binding/interfaces and security as appropriate; do not copy localhost config if kubelet/ingress must connect from another network.

## 8. Running the Lab and Collecting Real Data

### 8.1. Linux/macOS

~~~bash
java -version
./mvnw -version
./mvnw clean package
java -jar target/startup-steps-lab-0.0.1-SNAPSHOT.jar
~~~

### 8.2. Windows PowerShell

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd clean package
java -jar target/startup-steps-lab-0.0.1-SNAPSHOT.jar
~~~

If there is no Maven Wrapper, use `mvn clean package`. Ensure JDK 17+ is in `JAVA_HOME`/PATH. Stop any other app on port 8080 or change the port. Do not run two processes on the same port and accidentally collect JSON from the wrong process.

### 8.3. Markers on the Console

Expected similar to:

~~~text
LAB_PARENT id=<parent-id> parentId=<framework-id-or-null>
LAB_CHILD id=<child1-id> name=lab.warmup.load parentId=<parent-id>
LAB_CHILD_END id=<child1-id>
LAB_CHILD id=<child2-id> name=lab.warmup.index parentId=<parent-id>
LAB_CHILD_END id=<child2-id>
LAB_PARENT_END id=<parent-id>
~~~

Values inside angle brackets are **descriptive variable placeholders**, not literal stdout. When reading real logs:

- Parent ID is an automatically generated integer.
- Both children's `parentId` must equal the **ID of LAB_PARENT** in a recorder supporting nested steps.
- `LAB_PARENT_END` comes after both `LAB_CHILD_END` lines.
- Do not demand that all Java/system logs be adjacent or IDs be contiguous.

### 8.4. GET Snapshot

In another terminal:

~~~bash
curl -i http://127.0.0.1:8080/actuator/startup
curl -s http://127.0.0.1:8080/actuator/startup -o startup.json
~~~

On Windows:

~~~powershell
curl.exe -i http://127.0.0.1:8080/actuator/startup
curl.exe -s http://127.0.0.1:8080/actuator/startup -o startup.json
~~~

When the lab runs properly, GET typically returns HTTP 200 with JSON containing `springBootVersion`, `timeline.startTime`, `timeline.events`. Calling GET multiple times returns a **snapshot** and **does not remove** existing steps. Because the recorder can record additional steps while the app runs if instrumented code runs, a later snapshot can differ from an earlier one.

**Do not use POST before the first GET** if you want to save all current startup steps.

### 8.5. Extracting Custom Steps with jq

If `jq` is installed:

~~~bash
jq '.timeline.events | length' startup.json

jq -r '
  .timeline.events[]
  | select(.startupStep.name | startswith("lab."))
  | [
      .startupStep.id,
      (.startupStep.parentId // "none"),
      .startupStep.name,
      .duration
    ]
  | @tsv
' startup.json
~~~

With enough room left in the buffer, the three custom names are `lab.warmup`, `lab.warmup.load`, and `lab.warmup.index`. `jq` only extracts records; parent/child linking must rely on the two id/parentId columns, not just line position.

Reading tags:

~~~bash
jq -r '
  .timeline.events[]
  | select(.startupStep.name == "lab.warmup")
  | .startupStep.tags[]
  | "\(.key)=\(.value)"
' startup.json
~~~

Expected:

~~~text
component=catalog
environment=local
~~~

If the tag array may be empty, use `.tags[]?` for general queries. For framework steps, common keys like `beanName` help distinguish instances sharing the same `name`.

### 8.6. GET Differs from POST Drain

~~~bash
curl -s -X POST http://127.0.0.1:8080/actuator/startup -o drained.json
curl -s http://127.0.0.1:8080/actuator/startup -o after-drain.json
~~~

According to the Spring Boot 3.5 REST API:

- `GET` retrieves a **snapshot**, without clearing the buffer.
- `POST` **drains** recorded steps and returns them in the response; those steps are removed from the buffer.
- A subsequent GET usually no longer contains the old steps; new steps may appear if recorded after the drain.
- `POST` **does not** restart the JVM, clear bean definitions, or shut down the application.
- Because POST mutates observed data, coordinate among users of the same endpoint; one person draining can cause others to miss data.

If POST returns 403/405, check Actuator permissions, access level, and CSRF/security; do not immediately blame `BufferingApplicationStartup`.

## 9. Building the Parent–Child Tree: Do Not Rely on Array Order

Standard processing workflow:

1. Read all `timeline.events`.
2. For each event, take `startupStep.id` and add it to a dictionary/index.
3. Check for duplicate IDs; if duplicated in the same file, the data/record merge is invalid.
4. For each step with a `parentId`, look up the parent via the index.
5. If the parent exists, attach the child to the parent.
6. If `parentId` is null, mark as root.
7. If `parentId` is present yet the parent does not exist, mark **missing parent**; do not convert to 0.
8. Sort siblings by `startTime` then `id` for readability.
9. Print `name` and tags, along with duration converted to milliseconds.
10. Guard against cycles/depth when processing malformed JSON; do not recurse infinitely.

Output shape:

~~~text
id=100 lab.warmup duration=140ms tags=[component=catalog]
  id=101 lab.warmup.load duration=45ms tags=[dataSet=sample]
  id=102 lab.warmup.index duration=65ms tags=[index=prefix]
~~~

**Note:** A parent step can appear after its child in the array because the parent ends later; official REST docs explicitly illustrate this. Do not iterate sequentially and assign the preceding element as the parent of the next element.

## 10. Python 3 Script to Read JSON and Rank by Duration

The `analyze_startup.py` script below uses only the **standard library**. It builds an ID index, constructs the tree of steps starting with a prefix (default `lab.`), prints tags and durations in milliseconds, and warns about references to parents absent from the JSON. It does not modify any files.

~~~python
#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

def iso_seconds(value):
    """Parse PT...H...M...S, the common Boot duration form."""
    m = re.fullmatch(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?",
        value,
    )
    if not m:
        raise ValueError(f"Unsupported duration: {value!r}")
    h = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = float(m.group(3) or 0)
    return h * 3600 + minutes * 60 + seconds

def main():
    if len(sys.argv) not in (2, 3):
        print("Usage: python3 analyze_startup.py startup.json [prefix]")
        return 2

    document = json.loads(
        Path(sys.argv[1]).read_text(encoding="utf-8")
    )
    events = document.get("timeline", {}).get("events", [])
    prefix = sys.argv[2] if len(sys.argv) == 3 else "lab."

    by_id = {}
    for event in events:
        key = event["startupStep"]["id"]
        if key in by_id:
            raise ValueError(f"Duplicate startup step id: {key}")
        by_id[key] = event

    selected = {
        key: event for key, event in by_id.items()
        if event["startupStep"]["name"].startswith(prefix)
    }
    children = {key: [] for key in selected}
    roots = []
    missing = []

    for key, event in selected.items():
        parent = event["startupStep"].get("parentId")
        if parent in selected:
            children[parent].append(key)
        else:
            roots.append(key)
            if parent is not None and parent not in by_id:
                missing.append((key, parent))

    def order(key):
        event = selected[key]
        return event.get("startTime", ""), key

    roots.sort(key=order)
    for siblings in children.values():
        siblings.sort(key=order)

    def visit(key, level, path):
        if key in path:
            print("  " * level + f"[CYCLE at id={key}]")
            return
        event = selected[key]
        step = event["startupStep"]
        tags = ", ".join(
            f"{tag.get('key')}={tag.get('value')}"
            for tag in step.get("tags", [])
        )
        ms = iso_seconds(event["duration"]) * 1000
        print(
            "  " * level
            + f"id={key} parent={step.get('parentId')} "
            + f"{step['name']} {ms:.2f}ms"
            + (f" tags=[{tags}]" if tags else "")
        )
        for child in children[key]:
            visit(child, level + 1, path | {key})

    print("Spring Boot version:", document.get("springBootVersion"))
    print("All events:", len(events))
    print("Selected:", len(selected), "prefix:", repr(prefix))
    for root in roots:
        visit(root, 0, set())

    for child, parent in missing:
        print(f"WARNING missing parent: child={child}, parent={parent}")

    ranked = sorted(
        selected.values(),
        key=lambda e: iso_seconds(e["duration"]),
        reverse=True,
    )
    print("Top selected durations:")
    for e in ranked[:10]:
        step = e["startupStep"]
        ms = iso_seconds(e["duration"]) * 1000
        print(f"  {ms:9.2f}ms  id={step['id']} {step['name']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
~~~

Run on Linux/macOS:

~~~bash
python3 analyze_startup.py startup.json
python3 analyze_startup.py startup.json spring.beans.instantiate
~~~

Windows:

~~~powershell
py -3 analyze_startup.py startup.json
py -3 analyze_startup.py startup.json spring.beans.instantiate
~~~

**Notes about the parser:**

- By default it only prints `lab.` steps. If a parent is a framework step in the JSON yet filtered out by the prefix, it is printed as a **root of the filtered display view**, not an absolute root of the timeline.
- It prints `WARNING missing parent` only if the parent ID is genuinely **absent from the original JSON**; prefix filtering is not treated as missing data.
- The script sorts children by `startTime` without modifying `parentId`.
- The duration parser handles the `PT...H...M...S` forms common in the Startup REST API, not a general parser for all ISO-8601 forms with days/months/negatives; Java `Duration.parse` can be used when JDK compliance is needed.
- To print more steps, pass an appropriate prefix; an empty prefix prints the entire tree and can be very long.
- For malformed data with a completely closed parentId cycle lacking any root, the script does not print that closed branch; a production analyzer should check all nodes and cycles.
- Top values are **inclusive elapsed**; inspect the hierarchy before concluding a bottleneck.
- JSON files from multiple replicas/JVM restarts **must not** be merged into a single `id` map because IDs are only unique within one recording.

### 10.1. Lab Correlation

When running the script on `startup.json` retrieved via GET **before POST**, you typically see:

~~~text
id=<P> parent=<framework-id-or-None> lab.warmup ...ms tags=[component=catalog, environment=local]
  id=<C1> parent=<P> lab.warmup.load ...ms tags=[dataSet=sample]
  id=<C2> parent=<P> lab.warmup.index ...ms tags=[index=prefix]
~~~

`<P>`/`<C1>`/`<C2>` here are placeholder symbols in the description, not byte-for-byte output. Child steps are nested properly if parent IDs match and durations fall within the outer interval. Do not hardcode ID numbers from documentation.

## 11. Analyzing a Slow Bean from Name and Tags

Hypothetical example:

| name | tags | inclusive duration |
|---|---|---:|
| `spring.beans.instantiate` | `beanName=reportService` | 650ms |
| `spring.beans.instantiate` | `beanName=dataSource` | 580ms |
| `spring.beans.instantiate` | `beanName=cacheService` | 400ms |

If the `dataSource` record is a child of `reportService` and its interval is contained within it, the 580ms **is already included in** the 650ms parent; do not add them to get 1230ms. What to do:

1. Check IDs and `parentId` to confirm the two steps are actually related.
2. Check `startTime`/`endTime` to confirm the child interval lies inside the parent.
3. Inspect whether `dataSource` initialization waits on DNS/DB connection/driver init.
4. Run multiple times in the same profile/environment and measure p50/p95 to avoid concluding from a single spike.
5. For slow steps without children, try adding custom `ApplicationStartup.start(...)` inside the code or use JFR/tracing.
6. Optimize the root cause and then measure **end-to-end time-to-ready**, not just reducing a few steps.

### 11.1. Lazy Initialization Does Not Always Make the App Truly "Faster"

`spring.main.lazy-initialization=true` can prevent many beans from being initialized at startup, reducing recorded steps and shortening startup time. However, the work is only **deferred** to the first request or operation, which can increase latency and delay catching configuration errors.

Measure both startup and first-request latency, real readiness, JDBC warmup, external dependencies, and error behavior before/after optimization. Fewer recorded steps could simply be due to filters, capacity, lazy init, or a different recorder, not yet proof of improved performance.

## 12. Buffer Capacity and Missing-Step Conditions

`BufferingApplicationStartup(4096)` records up to 4096 events according to capacity; per Javadoc, when the buffer reaches capacity, **new steps are not recorded further**. This is not a ring buffer that automatically drops early steps to keep late ones. Consider:

- Apps with many beans/auto-configurations can exceed capacity.
- Custom `ApplicationRunner` runs late, so runner steps might not be recorded even though console logs appear.
- Filters can intentionally exclude certain step names.
- A POST drain command retrieved data and left a subsequent GET without old records.
- A partially extracted JSON file can lack a referenced parent.
- Applications with multiple contexts/replicas can result in curling the wrong instance.

Do not conclude `lab.warmup.index` did not execute just because it is missing from the timeline; check logs, recorder configuration, capacity, filters, and whether POST was called.

### 12.1. Filters Affect the Tree

Example replacing `main` with this block (snippet, do not run twice):

~~~java
BufferingApplicationStartup startup =
        new BufferingApplicationStartup(4096);
startup.addFilter(step ->
        step.getName().startsWith("lab.")
        || step.getName().startsWith("spring.beans."));

SpringApplication app =
        new SpringApplication(StartupStepsLabApplication.class);
app.setApplicationStartup(startup);
app.run(args);
~~~

This reduces the number of events to analyze, yet excluded `spring.boot.*` or `spring.context.*` parent steps cause the tree to miss some ancestors. Thus filters are suitable only when you understand which context you are losing.

If adding **multiple** predicates via `addFilter`, the Javadoc specifies a step must satisfy all filters to be recorded; do not assume they OR together automatically. The snippet above deliberately uses `||` **within one predicate**.

### 12.2. GET Snapshot and POST Drain Differ from Buffer Overflow

- **Buffer overflow:** the step was never written to the buffer after capacity ran out.
- **Filter:** the step was rejected by a predicate before being written.
- **POST drain:** the step was recorded, then removed from the buffer when returned.
- **Unended step:** the step is still open and may not yet have a completed timeline event.
- **Wrong process:** hit the right endpoint path, but on a different JVM.

All of these cause "missing steps", yet their remedies differ greatly. Record the collection mechanism and timing.

## 13. FlightRecorderApplicationStartup and JFR

When you need to know whether a slow step is due to classloading/GC/CPU/locks or I/O, you can switch to Spring Framework's `FlightRecorderApplicationStartup` and record JFR. Example **replacing the main setup**:

~~~java
import org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup;

SpringApplication app =
        new SpringApplication(StartupStepsLabApplication.class);
app.setApplicationStartup(new FlightRecorderApplicationStartup());
app.run(args);
~~~

This is a snippet; do not place the `import` line inside a Java method when copying into a real file. Use this recorder instead of Buffering in **a separate run**; it **does not** produce an equivalent `/actuator/startup` JSON buffer.

Run on a JDK supporting JFR:

~~~bash
java -XX:StartFlightRecording:filename=startup.jfr,duration=30s \
     -jar target/startup-steps-lab-0.0.1-SNAPSHOT.jar
~~~

On Windows PowerShell put the entire command on one line or use valid PowerShell continuation. Analyze with `jfr print` or JDK Mission Control. The JSON timeline helps identify step/tags/parent; JFR provides the JVM perspective on allocations, thread scheduling, GC, classloading, and CPU samples. Use them together rather than equating duration with CPU time.

## 14. Multiple Contexts, Threads, and Replicas

In an app with multiple ApplicationContexts or worker threads, you cannot assume a single tree describes all activity. `parentId` follows recorder semantics, not distributed tracing across services or context propagation across threads. Two steps with overlapping intervals are not automatically parent/child.

In multi-Pod Kubernetes, each JVM has step IDs belonging to **its own recording**. `id=50` on Pod A is not `id=50` on Pod B. When comparing startup runs, record process/pod ID, version, profile, Java version, cold/warm cache, and machine load; match by `name + tags` and context, not by using `id` as a cluster-wide key.

With framework instrumentation, steps can be recorded across phases like bean creation, context refresh, and runners, yet not every part of JVM launch/OS/container image pull is recorded in `ApplicationStartup`. To measure end-to-end from the platform, combine timestamps from the process supervisor/container, Spring Boot startup logs, and application ready state.

## 15. Security, Performance, and Investigation Workflow

### 15.1. Securing the Startup Endpoint

`/actuator/startup` can leak bean/package names and tags. In production:

- Expose only on a protected management interface; not to the public internet.
- Enforce authentication/authorization, restricted network, and access/audit as needed.
- Do not attach tokens, credentials, request bodies, or PII to tags.
- Define who has permission to POST drain since it removes retained records.
- Choose a capacity suited to heap and retention.
- Do not continuously GET large payloads without evaluating serialization/network overhead.
- If Spring Security is enabled, check CSRF for POST; do not blindly disable all security just to fetch the endpoint.

### 15.2. Bottleneck Investigation Workflow

1. Record the exact JDK, Spring Boot version, profile, classpath, container image, and test environment.
2. Enable `BufferingApplicationStartup` before run; capacity large enough to retain the steps to observe.
3. Start fresh; do not use an already-drained file or data from a different JVM.
4. GET a snapshot and save the JSON with a timestamp/run identifier.
5. Verify `timeline.events` contains the important groups; flag missing parents.
6. Build the `id → parentId` tree and inspect `name + tags`.
7. Rank durations numerically by **milliseconds**, not lexicographically on ISO duration strings.
8. Drill down into large parent steps to avoid double-counting.
9. Inspect unmeasured steps, I/O/GC/JIT, and dependency waits via JFR/logs/metrics.
10. Test one controlled optimization; re-measure across multiple runs and check time-to-ready/first-request.
11. Document conclusions based on evidence; do not treat a single duration as proof of a CPU bottleneck.

## 16. Common Troubleshooting

| Symptom | Causes to consider | How to verify |
|---|---|---|
| GET startup 404 | Missing Actuator, missing exposure/access, or wrong recorder | Check Maven dependencies, properties, `setApplicationStartup` |
| GET 401/403 | Authentication/authorization | Check Spring Security and access policy |
| POST 403/405 | Read-only access or CSRF/security | Check endpoint access, filter chain, and request method |
| Missing `lab.warmup.*` steps | Buffer full, filtered, already drained, or runner has not run | Compare LAB markers, capacity, request timeline |
| Empty ParentId | Top-level/no parent reported | Keep null, do not coerce to 0 |
| ParentId references unseen ID | Parent filtered, buffer/partial snapshot | Mark missing parent, do not fabricate |
| Events array has child before parent | Steps stored by completion/timing | Index by ID, do not rely on position |
| Duration `PT0.3S` misread as 0.3ms | Wrong unit | Convert to 300ms |
| Sorting duration with `sort_by(.duration)` fails | ISO duration is a string, not a number | Parse ISO duration before sorting |
| Multiple `spring.beans.instantiate` | Each bean is a step of the same type/name | Use beanName tag and ID |
| Summed duration exceeds total startup | Nested/overlapping spans | Do not sum inclusive durations |
| Exclusive parent becomes negative | Subtracted sum of overlapping children | Merge union intervals |
| Large step yet low CPU | Waiting on I/O, GC, lock, or child | JFR/metrics and step tree |
| Step count drops after enabling lazy | Deferred bean creation to first request | Measure time-to-ready and first-request latency |
| IDs do not match across runs | IDs are not stable across runs | Match name + tags + environment |
| JSON from wrong Pod | Routed through load balancer/management | Target a specific instance when taking snapshot |
| Tags leak data | Attached secrets/PII | Fix tagging, protect endpoint |
| Filter loses ancestors | Predicate retains only some steps | Document filter, try full buffer |
| JFR used and startup JSON empty | Flight Recorder differs from buffering recorder | Use JFR tooling, or Buffering to get JSON |

## 17. Self-Verifying Exercises

**Exercise A — Find three steps.** Run the lab, GET a snapshot before draining, and locate `lab.warmup`, `lab.warmup.load`, and `lab.warmup.index`. Record each `id`, `parentId`, `duration`, and `tags`. Confirm both children point to the actual parent ID.

**Exercise B — Read tags.** For `lab.warmup`, list `component=catalog` and `environment=local`. For the two children, read `dataSet=sample` and `index=prefix`. Explain why step name alone does not tell the whole story.

**Exercise C — Array order.** Compare the order of `LAB_PARENT`/`LAB_CHILD` in the console with the order of JSON records; explain why a parent can appear after a child in the events list.

**Exercise D — Missing parent.** Copy the JSON file, delete the parent record while keeping `child.parentId`, and run the script. Verify the script warns about the missing parent and does not silently convert it to 0.

**Exercise E — Duration.** Convert `PT0.040S`, `PT0.080S`, and `PT0.125S` to ms. Use `Duration.parse` or the Python parser to check and explain why `Thread.sleep` does not produce an exact fixed duration.

**Exercise F — Inclusive/exclusive.** Parent 100ms, child A 10–70ms and B 40–95ms. Compute union 85ms, exclusive 15ms, and explain why subtracting the sum of durations can turn negative.

**Exercise G — GET/POST.** In a fresh process, run GET → GET → POST → GET in sequence; compare event counts and describe the drain effect.

**Exercise H — Buffer/filter.** In a lab copy, set a small capacity or filter only `lab.`, and compare data with the unfiltered 4096 configuration. Observe why the framework parent step disappears while the child's `parentId` can still point to the old ID.

**Exercise I — Real optimization.** Find a `spring.beans.instantiate` with a large duration in a test app, read `beanName`, parent/children, verify root cause with JFR or dependency timing; after optimizing, measure startup-to-ready and first request multiple times rather than relying on a single duration value.

### Acceptance Checklist

- [ ] Configured `BufferingApplicationStartup` before `SpringApplication.run`.
- [ ] Built and ran Maven project Java 17+ Spring Boot 3.5 Web + Actuator.
- [ ] GET `/actuator/startup` returns JSON with `timeline.events`.
- [ ] Can read `name/id/parentId/tags/startTime/endTime/duration`.
- [ ] Knows `parentId` is optional; never defaults to 0.
- [ ] Builds tree by ID, not by event array order.
- [ ] Distinguishes multiple same-name steps via tags.
- [ ] Converts `PT0.012S` to 12ms.
- [ ] Sees two children with `parentId` equal to the parent ID in the lab.
- [ ] Knows parent duration is inclusive and does not double-add children.
- [ ] Knows how to merge union intervals when steps overlap.
- [ ] GET snapshot does not clear, POST drain clears the buffer.
- [ ] Understands capacity/filters can cause missing steps.
- [ ] Does not equate `parentId` with the bean dependency graph.
- [ ] Does not equate elapsed duration with CPU time.
- [ ] Knows how to protect the Actuator endpoint and avoid secrets in tags.
- [ ] Has a workflow correlating multiple runs and JFR when investigating bottlenecks.

## 18. Official Documentation

1. **Spring Boot 3.5 — Application Startup tracking**, Buffering and Flight Recorder: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
2. **Spring Boot 3.5 — Actuator Startup REST API**, GET snapshot, POST drain, and JSON schema: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/startup.html
3. **Spring Boot 3.5 — Actuator Endpoints**, HTTP exposure/access/security: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
4. **Spring Framework 6.2 — ApplicationStartup API**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/metrics/ApplicationStartup.html
5. **Spring Framework 6.2 — StartupStep API** (ID, parentId, tags, end): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/metrics/StartupStep.html
6. **Spring Boot 3.5 — BufferingApplicationStartup API** (capacity/filters/timeline): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html
7. **Spring Framework 6.2 — FlightRecorderApplicationStartup API**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/metrics/jfr/FlightRecorderApplicationStartup.html
8. **Java SE 17 — Duration.parse / toMillis**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html

**Conclusion:** To read a startup timeline accurately, link **`id → parentId`** to build the hierarchy, use **`name + tags`** to know what each step is doing, and then examine **`startTime/endTime/duration`** to analyze timing. Do not treat array order as a tree, do not merge IDs across runs, and do not sum all inclusive durations into a startup total. When parents are missing or buffers have been drained/filtered, document observation limits. To find the real bottleneck, combine the timeline with JFR/metrics and verify across multiple startups.