# ApplicationStartup and StartupStep — Measuring and Analyzing the Spring Boot Startup Sequence

## 1. The Problem: Which Step Makes "Slow Application Startup" Slow?

When launching a Spring Boot application, the log line `Started ... in ... seconds` reports an aggregate startup duration, but it **does not automatically show** how much time was spent on component scanning, parsing `@Configuration`, creating beans, executing `BeanFactoryPostProcessor`, or a custom initialization operation.

Spring Framework provides **`ApplicationStartup`** and **`StartupStep`** to describe **named, tagged work steps with start/end timestamps** during `ApplicationContext` initialization. Spring Boot adds `BufferingApplicationStartup`, wired to Actuator `/actuator/startup`; Spring Framework also has `FlightRecorderApplicationStartup` to view steps alongside JVM events via Java Flight Recorder (JFR).

One thing to understand right away:

> `ApplicationStartup` is **not a type of application event** and `StartupStep` is **not a required Spring bean**. They are execution-step recording APIs that can be used to diagnose startup.

Questions this lesson helps answer:

- What does `ApplicationStartup.DEFAULT` do, and when must recording be enabled?
- What is the order of `start("step.name")`, `tag(...)`, and `end()`?
- When should you use `BufferingApplicationStartup`, and when `FlightRecorderApplicationStartup`?
- How does reading JSON from `GET /actuator/startup` differ from `POST /actuator/startup`?
- How do step `id` and `parentId` help analyze relationships?
- How do you insert a custom step into creating a bean, and avoid forgetting `end()` on error?
- Why can't you sum the durations of all steps to get JVM startup time?
- What are the considerations around buffer capacity, monitoring overhead, secrets in tags, and endpoint access control?

## 2. Mechanism and Data Flow

`SpringApplication` and the Spring Framework container already have built-in internal instrumentation points. When an `ApplicationStartup` implementation is configured at the **beginning of the launch process**, instrumented framework parts create corresponding `StartupStep` instances.

~~~mermaid
flowchart TD
    MAIN["main(String[] args)"] --> CONFIG["SpringApplication.setApplicationStartup(...)"]
    CONFIG --> RUN["SpringApplication.run(args)"]
    RUN --> TRACKER["ApplicationStartup.start(name)"]
    TRACKER --> STEP["StartupStep: id, name, parentId, tags"]
    STEP --> END["StartupStep.end()"]
    END --> BUF["BufferingApplicationStartup: timeline in memory"]
    END --> JFR["FlightRecorderApplicationStartup: JFR events"]
    BUF --> HTTP["Actuator GET/POST /actuator/startup"]
    BUF --> CODE["getBufferedTimeline() / drainBufferedTimeline()"]
    JFR --> VIEW["JFR / JDK Mission Control / jfr CLI"]
~~~

This is a diagram of two **implementation choices**. In a standard example, you configure **one** implementation for a `SpringApplication`. It does not mean a single step is automatically recorded to both places in every application.

### From Named Step to Measured Duration

Suppose the framework needs to process a configuration:

~~~java
StartupStep step = applicationStartup.start("demo.catalog.prepare");
try {
    prepareCatalog();
} finally {
    step.end();
}
~~~

This snippet requires an `applicationStartup` variable of type `ApplicationStartup` and a defined `prepareCatalog()` method. When using a recording implementation, the interval from `start` to `end` becomes an observable step in the timeline/JFR.

If the code does not call `end()`, the step may not be included in the completed record or may distort the observation structure. **Always use `try/finally`**, especially with constructors, bean factories, I/O, or steps that may throw exceptions.

### A Step Is a Work Interval, Not Just a Log Line

A step can include:
- CPU time;
- I/O waits;
- lock waits;
- class loading;
- child steps created while the parent step is open.

Therefore, a step's duration is the **elapsed processing time of the enclosed section**, not its isolated CPU time, nor does it automatically prove all time belongs to one specific bean.

## 3. ApplicationStartup: Spring Framework's Foundational API

Interface in package:

~~~java
org.springframework.core.metrics.ApplicationStartup
~~~

There are two basic members:

| Member | Signature/value | Meaning |
| --- | --- | --- |
| `ApplicationStartup.start(String name)` | Returns `StartupStep` | Starts tracking a step with a technical name |
| `ApplicationStartup.DEFAULT` | No-op implementation | Low overhead; **does not collect** an actual startup timeline |

The default path is designed to be minimal: merely enabling Spring Boot Actuator does not mean all startup steps have been recorded into a buffer. To use the startup endpoint for diagnostics, an appropriate tracker must be configured before key steps take place.

### Why Must It Be Configured Early?

If an application only creates `new BufferingApplicationStartup(2048)` after the context has refreshed, work that occurred earlier **is not retroactively recorded**. Thus the standard pattern is:

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);
application.setApplicationStartup(
        new BufferingApplicationStartup(2048));
application.run(args);
~~~

This is a snippet requiring the appropriate imports/classes. The key point is that `setApplicationStartup(...)` is called **before** `run(args)`.

Creating a `@Bean BufferingApplicationStartup` afterward without configuring it on `SpringApplication` is **not an equivalent operation**; it can create a second tracker unused by framework steps. In modern Boot, the tracker configured for the application can also be injected via infrastructure; you should not register another bean of the same type unnecessarily.

### Does Startup Tracking Belong to Framework or Boot?

- Spring Framework 5.3+ defines `ApplicationStartup` and `StartupStep` in `spring-core`.
- Spring Framework provides `FlightRecorderApplicationStartup` in `org.springframework.core.metrics.jfr`.
- Spring Boot 2.4+ has `BufferingApplicationStartup` in `org.springframework.boot.context.metrics.buffering`.
- Spring Boot Actuator provides the `startup` endpoint for the **buffer implementation**.
- Specific steps recorded by Spring/Boot are implementation details whose names/tags may change across updates.

## 4. StartupStep: Lifecycle, Information, and Tags

`org.springframework.core.metrics.StartupStep` has memorable APIs:

| API | Data type | Meaning |
| --- | --- | --- |
| `getName()` | `String` | Technical name of the step |
| `getId()` | `long` | Unique ID for the step during startup |
| `getParentId()` | `Long` (nullable) | ID of the parent step if any |
| `tag(String key, String value)` | `StartupStep` | Attaches key/value metadata |
| `tag(String key, Supplier<String> value)` | `StartupStep` | Attaches metadata provided by a supplier |
| `getTags()` | `StartupStep.Tags` | The step's tags |
| `end()` | `void` | Marks the step done so the implementation finalizes recording |

### Correct Lifecycle

~~~mermaid
flowchart LR
    CREATE["applicationStartup.start(name)"] --> TAG["step.tag(key, value)"]
    TAG --> EXECUTE["Execute actual work"]
    EXECUTE --> FINALLY["finally: step.end()"]
    FINALLY --> OBSERVE["Timeline/JFR records step"]
~~~

A step can have zero tags. Multiple tags can be added **before `end()`**. Do not mutate step state after `end()`: the Javadoc requires that an ended step must no longer be modified.

### What Should Step Names Look Like?

Spring Framework recommends dot-separated technical namespaced names that can be reused across multiple instances of the same kind of work:

~~~text
demo.catalog.prepare
demo.cache.warmup
company.connector.initialize
~~~

**Do not start custom names with `spring.`**, as this namespace is reserved for internal framework use. Do not set a step name to a random per-run ID; the name should describe the **type of operation**, while classification details belong in tags.

### Tags: Used to Understand "Which Step"

~~~java
StartupStep step =
        applicationStartup.start("demo.connector.prepare");

step.tag("component", "pricing-client");
step.tag("mode", "initial-load");

try {
    initializeConnector();
} finally {
    step.end();
}
~~~

This is a snippet requiring the corresponding variable and method. It expresses:
- name = `demo.connector.prepare`;
- tag `component` = `pricing-client`;
- tag `mode` = `initial-load`.

Tags are **metadata strings**, not arbitrary Java objects or unbounded metrics labels. Do not attach passwords, access tokens, connection strings, user data, or a dump of the entire `Environment` to tags. Such contents can appear in Actuator JSON/JFR or diagnostic logs.

### Supplier Tag

~~~java
step.tag("configCount", () -> Integer.toString(configs.size()));
~~~

The snippet requires a suitable `configs` variable. Supplier lets the implementation compute the tag representation when appropriate, potentially avoiding expensive string construction in some situations. However, **do not use a Supplier to perform side effects** or access objects already freed after the step ends; prefer short, stable descriptive data.

### ID and parentId Are Not Database Keys

`id` identifies a step within a timeline; `parentId` indicates a parent-child relationship when the framework/implementation records one. Do not use `id` as a durable business identifier across deployments: another startup may start numbering from the beginning or produce a different step order.

**Do not assume parentId is always present**: top-level steps may have no parent and serialized data may omit this field. In code, `getParentId()` can be `null`; do not unbox directly to `long` without checking.

## 5. Default Spring Steps Worth Recognizing

Spring Framework already instruments many processing paths. The names below are **examples from Spring Framework 6.2 documentation**, not an immutable API contract:

| `StartupStep` name | Work typically measured | Example tag |
| --- | --- | --- |
| `spring.context.refresh` | Refreshing the application context | Implementation-dependent |
| `spring.context.base-packages.scan` | Component scanning base packages | `packages` |
| `spring.context.config-classes.parse` | Parsing configuration classes | `classCount` |
| `spring.context.config-classes.enhance` | Enhancing configuration classes | `classCount` |
| `spring.context.bean-factory.post-process` | Running `BeanFactoryPostProcessor` | `postProcessor` |
| `spring.context.beandef-registry.post-process` | Running registry post-processor | `postProcessor` |
| `spring.context.beans.post-process` | Bean post-processing phase | Step-dependent |
| `spring.beans.instantiate` | Creating a bean along with related dependencies | `beanName`, `beanType` |
| `spring.beans.smart-initialize` | `SmartInitializingSingleton` callback | `beanName` |
| `spring.context.annotated-bean-reader.create` | Creating annotated bean definition reader | Step-dependent |

Spring Boot may add `spring.boot.*` steps related to bootstrap/lifecycle. Specific steps appear only when the corresponding feature is used.

### Interpretation Example

If the JSON contains:

~~~json
{
  "name": "spring.beans.instantiate",
  "tags": [
    {"key": "beanName", "value": "pricingClient"}
  ]
}
~~~

this is part of describing **one step**, not the entire Actuator response. It suggests the instantiation of bean `pricingClient` was recorded.

However, do not conclude "this step's duration is the time of the **constructor alone**" if it also includes dependency resolution, factory calls, proxy creation, or child startup steps. To know which part actually took time, check stacks/JFR, child steps, and initialization code.

### Warnings About Timeline Ordering

- `id` is an identifier, **not a millisecond count**.
- One step can start earlier yet finish after another step.
- `timeline.events` should not be assumed by default to be a linear trace "step 1 finishes before step 2 runs".
- The sum of step durations can be **greater than** total startup time due to nested/concurrent steps.
- A recorded step does not guarantee that all initialization logic of the same name is measured on every runtime branch.

## 6. Comparing Three Ways to Use ApplicationStartup

| Option | Where | Collected data | Use when |
| --- | --- | --- | --- |
| `ApplicationStartup.DEFAULT` | Spring Framework | No real recording; no-op | Most normal apps, prioritizing low overhead |
| `BufferingApplicationStartup(capacity)` | Spring Boot | Step timeline, timestamps, and durations in memory buffer | Quick diagnostics, using `/actuator/startup` JSON |
| `FlightRecorderApplicationStartup` | Spring Framework | StartupStep becomes JFR events | Deep investigation, correlating class loading, allocations, GC, and JVM events |

You should not call `BufferingApplicationStartup` a "metrics library replacing Micrometer", or JFR a "default Actuator endpoint". They have different **storage/observation paths**.

### DEFAULT: Why Is Almost Nothing Visible?

~~~java
ApplicationStartup tracker = ApplicationStartup.DEFAULT;
StartupStep step = tracker.start("demo.noop");

step.tag("component", "example");
step.end();
~~~

The Java 17 snippet requires importing the two interfaces. The logic runs cleanly, but **no timeline is collected** by the no-op implementation. This is intentional behavior to reduce startup overhead.

### Buffering: Capacity Limit Matters

~~~java
BufferingApplicationStartup tracker =
        new BufferingApplicationStartup(2048);
~~~

This constructor starts recording. According to Spring Boot 3.5 Javadoc:

- The buffer has finite capacity.
- **When full, new steps are not recorded.**
- This is **not a ring buffer** that automatically evicts old steps to keep new ones.
- You can use `addFilter(Predicate<StartupStep>)` to keep only needed step types.
- You can use `getBufferedTimeline()` to take a snapshot.
- You can use `drainBufferedTimeline()` to **retrieve and remove steps from the buffer**.
- `startRecording()` does not need to be called right after the constructor; the constructor already calls it internally. Calling it after steps exist can throw `IllegalStateException`.

`2048` is an **example capacity**, not the default value for every application. Applications with many beans/configuration classes can generate more than this. If late startup steps are missing from the timeline, check capacity before concluding the framework does not instrument them.

### FlightRecorder: When You Need to Know What the JVM Is Doing Too

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new FlightRecorderApplicationStartup());
app.run(args);
~~~

This snippet requires importing `org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup`, `SpringApplication`, and class `MyApplication`. To capture a recording, you must **enable Java Flight Recorder in the JVM** (e.g., `-XX:StartFlightRecording=...`) and run an appropriate workload.

When using this implementation, the `/actuator/startup` endpoint does not automatically provide a timeline buffer, because Boot's endpoint requires `BufferingApplicationStartup`. That is an architectural difference, not an Actuator malfunction.

## 7. Complete Spring Boot Example: Custom StartupStep in a Bean Factory

The example uses Spring Boot **3.5.16**, Java **17+**, Maven, Spring Web, and Actuator. The program has a `DataCatalog` bean initialized with a short delay **for illustration only**, a controller to verify the bean, and tracker configuration from `main`.

Directory structure:

~~~text
startup-steps-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/startupsteps/
    │   │   ├── StartupStepsApplication.java
    │   │   └── CatalogController.java
    │   └── resources/application.yaml
    └── test/java/com/example/startupsteps/
        └── BufferingApplicationStartupTest.java
~~~

### File pom.xml

~~~xml
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
    <artifactId>startup-steps-demo</artifactId>
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
~~~

### File src/main/resources/application.yaml

~~~yaml
spring:
  application:
    name: startup-steps-demo
  main:
    banner-mode: "off"

server:
  port: 18083

management:
  endpoints:
    web:
      exposure:
        include: health,startup
~~~

`management.endpoints.web.exposure.include` allows viewing the startup endpoint over HTTP **in a lab environment**. In production, access must be strictly restricted: bean names, initialization paths, or tags can reveal internal structure. Do not expose the startup endpoint publicly by default.

### File src/main/java/com/example/startupsteps/StartupStepsApplication.java

~~~java
package com.example.startupsteps;

import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.annotation.Bean;
import org.springframework.core.metrics.ApplicationStartup;
import org.springframework.core.metrics.StartupStep;
import org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup;

@SpringBootApplication
public class StartupStepsApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(StartupStepsApplication.class);

        // Swap the implementation before app.run(...).
        if (Boolean.getBoolean("demo.startup.jfr")) {
            app.setApplicationStartup(
                    new FlightRecorderApplicationStartup());
        } else {
            app.setApplicationStartup(
                    new BufferingApplicationStartup(4096));
        }

        app.run(args);
    }

    @Bean
    DataCatalog dataCatalog(ApplicationStartup applicationStartup) {
        StartupStep step =
                applicationStartup.start("demo.catalog.prepare");

        step.tag("component", "dataCatalog");
        step.tag("strategy", "sample-bootstrap");

        try {
            // Lab only: create an observable duration.
            Thread.sleep(150);

            return new DataCatalog(List.of(
                    "alpha", "beta", "gamma"));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Catalog setup interrupted", e);
        } finally {
            step.end();
        }
    }

    @Bean
    ApplicationRunner printCatalog(DataCatalog catalog) {
        return args -> System.out.println(
                "CATALOG_SIZE=" + catalog.items().size());
    }

    public record DataCatalog(List<String> items) {
    }
}
~~~

**Why does this approach make sense?**

1. `main` configures `ApplicationStartup` before Boot creates/parses the context, so the framework records as many startup steps as possible.
2. System property `-Ddemo.startup.jfr=true`, if set, selects the JFR implementation. Without the property, the application uses buffering and the Actuator startup endpoint.
3. `@Bean dataCatalog(ApplicationStartup applicationStartup)` obtains the tracker provided by Spring rather than creating a new recorder inside the bean.
4. Custom name `demo.catalog.prepare` does not collide with the `spring.*` namespace.
5. Two tags have fixed values and contain no secrets or high-cardinality data.
6. `Thread.sleep(150)` makes the initialization duration easy to see in the lab. Do not leave artificial sleeps in production.
7. Uses `try/finally` to ensure `step.end()` even when initialization throws an error.
8. `ApplicationRunner` requires `DataCatalog`, so the bean is created before the runner executes; if the app enables global lazy init, this dependency can also pull bean creation earlier. Do not conclude a custom step was recorded pre-ready just from the method name; inspect the timeline.
9. Nested record `DataCatalog` is a normal Java 17 record returned by `@Bean`.

### File src/main/java/com/example/startupsteps/CatalogController.java

~~~java
package com.example.startupsteps;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {
    private final StartupStepsApplication.DataCatalog catalog;

    public CatalogController(
            StartupStepsApplication.DataCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/catalog")
    public List<String> catalog() {
        return catalog.items();
    }
}
~~~

The controller verifies the bean was created. A `/catalog` request **does not necessarily** produce a new startup step after the application is ready: `ApplicationStartup` is for startup instrumentation, not general request tracing.

### Build and Run

~~~bash
mvn -q test
mvn -q -DskipTests package
java -jar target/startup-steps-demo-0.0.1-SNAPSHOT.jar
~~~

On successful startup, the line intentionally printed by the runner is:

~~~text
CATALOG_SIZE=3
~~~

Boot may print framework logs before/after this line; do not treat it as the entire stdout.

Call the API:

~~~bash
curl -fsS http://127.0.0.1:18083/catalog
~~~

Expected JSON response:

~~~json
["alpha","beta","gamma"]
~~~

This is the controller's response body, not `/actuator/startup` data. Startup duration/timestamps depend on hardware and the JVM, so no fixed millisecond value is attached to the example.

## 8. The /actuator/startup Endpoint: GET Snapshot and POST Drain

With **Spring Boot Actuator**, suitable web exposure, and `BufferingApplicationStartup`:

~~~bash
curl -fsS http://127.0.0.1:18083/actuator/startup
~~~

GET returns a JSON timeline in which you can find the custom step `demo.catalog.prepare`.

An **abbreviated structural sample**:

~~~json
{
  "springBootVersion": "3.5.16",
  "timeline": {
    "startTime": "2026-01-01T00:00:00Z",
    "events": [
      {
        "startTime": "2026-01-01T00:00:01Z",
        "endTime": "2026-01-01T00:00:01.150Z",
        "duration": "PT0.150S",
        "startupStep": {
          "id": 21,
          "parentId": 12,
          "name": "demo.catalog.prepare",
          "tags": [
            {"key": "component", "value": "dataCatalog"},
            {"key": "strategy", "value": "sample-bootstrap"}
          ]
        }
      }
    ]
  }
}
~~~

**This is not the exact output of a single run**: all timestamps, `id`, `parentId`, duration, and event counts above are illustrative data. A real startup can have hundreds of steps and `parentId` may be absent for top-level steps.

### Fields to Understand

| JSON field | Type/meaning |
| --- | --- |
| `springBootVersion` | Boot version of the application |
| `timeline.startTime` | Timeline start timestamp |
| `timeline.events[]` | Recorded steps |
| `startTime`, `endTime` | Step start/end timestamps |
| `duration` | Duration in ISO-8601 duration format, e.g., `PT0.150S` |
| `startupStep.name` | Technical name of the step |
| `startupStep.id` | ID within the timeline |
| `startupStep.parentId` | Parent step ID if any |
| `startupStep.tags[]` | Key/value metadata entries |

`duration` is not a JSON number of seconds; if parsing in Java, use `java.time.Duration.parse(...)` or an equivalent parser.

### GET Does Not Remove Data from the Buffer

~~~bash
curl -fsS -X GET \
  http://127.0.0.1:18083/actuator/startup \
  -o startup-before.json
~~~

GET is a **snapshot**. It reads the recorded timeline and does not intentionally remove steps from the buffer.

### POST Drains Data from the Buffer

~~~bash
curl -fsS -X POST \
  http://127.0.0.1:18083/actuator/startup \
  -o startup-drained.json
~~~

POST returns the timeline containing recorded steps and **drains** them from the buffer. After POST, a subsequent GET may return very few or no steps if no new steps were recorded.

This is a **semantic difference**, not just a different HTTP verb:
- GET suits repeated observation/comparison;
- POST suits collecting data and freeing the buffer;
- Once POST finishes, you cannot rely on a subsequent GET to reconstruct all drained data unless you saved the POST response or restart the application.

In environments with multiple observability tools, you must determine **who owns draining**: two consumers both calling POST can leave the second consumer with empty data. Do not use POST just to "take a quick look" and discard the response.

### Analyzing with jq

If `jq` is installed:

~~~bash
# Count events in the snapshot
jq '.timeline.events | length' startup-before.json

# Find the custom step and extract duration + tags
jq '[.timeline.events[]
     | select(.startupStep.name == "demo.catalog.prepare")
     | {duration, startupStep}]' startup-before.json

# List some bean instantiation steps
jq '[.timeline.events[]
     | select(.startupStep.name == "spring.beans.instantiate")
     | {duration, startupStep}]' startup-before.json
~~~

Output depends on the actual number of events. A bean does not necessarily appear exactly once in every context design/startup mode. You should not treat the JSON event array order as the sole causal model.

## 9. Unit Test for BufferingApplicationStartup (No Spring Context Needed)

You can verify the contract independently with JUnit 5. Test file of the project above:

**`src/test/java/com/example/startupsteps/BufferingApplicationStartupTest.java`**

~~~java
package com.example.startupsteps;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.boot.context.metrics.buffering.StartupTimeline;
import org.springframework.core.metrics.StartupStep;

import static org.junit.jupiter.api.Assertions.*;

class BufferingApplicationStartupTest {

    @Test
    void recordsACompletedStepAndKeepsSnapshot() {
        BufferingApplicationStartup tracker =
                new BufferingApplicationStartup(8);

        StartupStep step = tracker.start("demo.test.prepare");
        step.tag("component", "test");
        step.end();

        StartupTimeline snapshot = tracker.getBufferedTimeline();
        assertEquals(1, snapshot.getEvents().size());
        assertEquals("demo.test.prepare",
                snapshot.getEvents().get(0)
                        .getStartupStep().getName());

        // Snapshot does not remove buffer contents.
        assertEquals(1,
                tracker.getBufferedTimeline().getEvents().size());

        StartupTimeline drained = tracker.drainBufferedTimeline();
        assertEquals(1, drained.getEvents().size());

        assertTrue(tracker.getBufferedTimeline()
                .getEvents().isEmpty());
    }

    @Test
    void filtersStepsByName() {
        BufferingApplicationStartup tracker =
                new BufferingApplicationStartup(8);

        tracker.addFilter(step ->
                step.getName().startsWith("demo."));

        tracker.start("internal.unwanted").end();

        StartupStep wanted = tracker.start("demo.useful");
        wanted.tag("category", "demo");
        wanted.end();

        StartupTimeline snapshot = tracker.getBufferedTimeline();
        assertEquals(1, snapshot.getEvents().size());
        assertEquals("demo.useful",
                snapshot.getEvents().get(0)
                        .getStartupStep().getName());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The two tests demonstrate:
- A completed step is recorded into the buffer and reading a snapshot does not remove data.
- Drain retrieves and removes buffered steps.
- Filtering by name excludes unwanted steps.

This is an **implementation unit test**, without starting a real `SpringApplication`. It does not prove internal steps like `spring.context.refresh` will be present in every project; to test framework instrumentation, use an integration test or run a JAR with the tracker configured.

**Small note:** if you add a filter, steps not matching the filters are not recorded; this can cause the timeline to miss parent steps needed to display a full tree. In production, do not automatically apply aggressive filters before understanding parent-child data dependencies.

## 10. Properly Analyzing Startup Time from the Timeline

### Why Not Sum the Durations of All Events?

Suppose:
- `spring.context.refresh` is 700 ms long;
- within it, `spring.beans.instantiate` for A is 350 ms long;
- inside A, a custom step `demo.catalog.prepare` is 150 ms long.

If you add 700 + 350 + 150 = 1,200 ms, you **double-count** nested time. Durations are typically inclusive elapsed times of each interval, which can overlap. The sum of event durations is **not the entire process startup time**.

~~~mermaid
gantt
  title Illustrative example of nested steps (not real measurements)
  dateFormat X
  axisFormat %s
  section Context
  refresh : 0, 700
  section Bean
  instantiate A : 150, 500
  section Custom
  catalog.prepare : 200, 350
~~~

The chart above only illustrates overlapping intervals. When processing real data, use start/end and parentId (when available) to build a timeline or flamegraph, avoiding straight addition of step durations.

### Four Numbers That Should Not Be Mixed

| Metric | Measurement boundary | Where collected |
| --- | --- | --- |
| `T_process_ready` | Spawn JVM → readiness probe returns healthy | External script/monitor outside the process |
| `T_main_ready` | Start of `main` → `ApplicationReadyEvent` | Monotonic clock such as `System.nanoTime()` |
| `T_context_refresh` | Instrumented context refresh interval | `spring.context.refresh` step |
| `T_bean_creation` | Bean creation interval by step | `spring.beans.instantiate` or custom step |

An application can optimize context refresh very well yet still spend time on:
- JVM startup before `main` runs;
- config/environment preparation;
- `ApplicationRunner`/`CommandLineRunner` after context refresh;
- readiness propagation from the platform;
- request or connection warm-up after ready.

Therefore, `ApplicationStartup` **does not replace** end-to-end startup or health readiness measurement. It is a tool for explaining **the steps that were instrumented**.

### What Does Top-N Slowest Mean?

You can sort events by duration to find large intervals. However, a long parent step and multiple long child steps do not prove multiple independent bottlenecks. Read from parent down to child:
1. Find the phase with a large duration.
2. Inspect the children of that phase.
3. Compare events of the same type across different beans.
4. Identify time not broken down into child steps.
5. If needed, enable JFR CPU/allocation/I/O profiling to look deeper.

You should store `startTime`/`endTime` and `parentId`, not only duration.

### When to Use @Lazy or Adjust the Dependency Graph?

If `spring.beans.instantiate` points to an expensive bean, the next step is finding why it is expensive: I/O in the constructor, connection pool initialization, cache loading, file scanning, template compilation, reflection/class loading, or a deep dependency chain.

Enabling `spring.main.lazy-initialization=true` can reduce some steps before ready by **deferring the cost to first use**. Do not call that an improvement in total cost without measuring first-hit latency, RSS/heap, and startup validation correctness. If an essential bean fails, lazy init can shift the exception from startup to runtime.

## 11. When You Need JFR Instead of the Buffering Endpoint

`FlightRecorderApplicationStartup` emits Spring-specific startup events so JFR can correlate them with:
- CPU samples;
- class loading;
- Java allocations;
- garbage collection;
- thread scheduling and other JVM events.

In the project from section 7, place the JVM property **before `-jar`** to select the JFR implementation:

~~~bash
java -Ddemo.startup.jfr=true \
  -XX:StartFlightRecording=filename=boot-startup.jfr,settings=profile,dumponexit=true \
  -jar target/startup-steps-demo-0.0.1-SNAPSHOT.jar
~~~

This is a long-running web program; after calling `/catalog`, stop it with Ctrl+C or a controlled shutdown signal so the JVM writes the file if the recording is configured with `dumponexit=true`. Do not use `kill -9` and expect the recording to flush normally.

Inspect the recording with JDK 17+:

~~~bash
jfr summary boot-startup.jfr
jfr metadata boot-startup.jfr
~~~

To print Spring StartupStep events, the event name in Spring Framework 6.x versions can be:

~~~bash
jfr print \
  --events org.springframework.core.metrics.jfr.FlightRecorderStartupEvent \
  boot-startup.jfr
~~~

If no events appear, verify JFR is enabled properly, the application uses `FlightRecorderApplicationStartup`, and the JFR file covers the startup window. Event names must be checked against the metadata of the **exact Spring Framework version**; do not rely blindly on an event name from a different version.

**Do not expect `GET /actuator/startup` to work in JFR mode**: that endpoint requires the buffering tracker rather than directly reading a JFR recording.

### Is JFR or Buffering Better?

- Want **quick JSON** to understand phase/bean names: buffering + actuator.
- Want **allocations/GC/class loading** corresponding to a startup step: JFR + Mission Control.
- Want **long-term latency, throughput, errors**: Micrometer/tracing/load testing; do not force the startup tracker to serve as a general metrics backend.
- Want A/B performance comparisons: avoid enabling JFR on only one branch if recording overhead could skew results.

## 12. Tracking Custom Steps Outside Startup Time

Although the API is named `ApplicationStartup`, code can still call `start(...)` after the app is ready if the implementation still exists. However:
- Its semantics and tooling are designed for **startup and core-container initialization**.
- The buffer is bounded, not a long-term event store.
- The Actuator startup timeline is not a repository for every arbitrary request/job.
- Steps created after ready can add noise when analyzing startup performance.

For request tracing, use the Observation API/Micrometer tracing/OpenTelemetry. For recurring latency metrics over time, use `Timer`/appropriate distribution metrics; do not turn `StartupStep` into a general runtime solution.

## 13. Capacity, Filters, Drain, and Operational Impacts

### Capacity Too Low

Suppose the recorder has capacity 100, yet the framework creates 500 steps. Per Javadoc, once the buffer is full, **new steps are not recorded**. The observed timeline is only the subset retained within the limit (plus filter effects), and must not be interpreted as the entire startup.

How to handle:
1. Increase capacity in a controlled manner, e.g., from 512 to 4096.
2. Inspect which step types generate the most records.
3. Filter by name when the investigation target is clear.
4. Drain data to an appropriate store before the buffer fills if a reliable collection mechanism exists.
5. Measure memory/overhead when increasing capacity; do not use an unbounded number.

### Do Not Call startRecording() at the Wrong Time

The `BufferingApplicationStartup` constructor already starts recording automatically. Calling `startRecording()` again after steps have been recorded can throw `IllegalStateException`. This API is not an "anytime reset button" to re-measure from scratch on the same application instance.

### GET and POST Have Contention Risks

If a monitoring agent sends `POST /actuator/startup` to drain, a developer running GET afterward might think startup had no steps. There is no fixed data ownership per HTTP client. Design one primary collection pipeline, persist the response, and use GET for observation when draining is not needed.

### When App Startup Fails Before the Endpoint Opens

If the context fails during refresh or the web server has not started listening yet, `/actuator/startup` may **never be available**. This is an important limitation: an in-process buffer can vanish when the process exits.

To investigate very early failures:
- read stack traces, `Caused by`, and `FailureAnalyzer`;
- use a JFR recording enabled from JVM launch, if the JVM exits along a path that dumps the recording properly;
- observe logs/events/exit codes, rather than expecting an HTTP endpoint from an app that never finished starting.

### Store Data Responsibly

Startup tags can contain bean, package, and class names, parameters, or values you added yourself. Restrict:
- public exposure of Actuator startup;
- logging raw tags containing secrets/PII;
- overly long retention in diagnostic systems;
- automatically sending full startup graphs to unapproved systems.

Only add enough metadata to correlate slowness causes; there is no need to dump all configuration properties.

## 14. Common Debugging Scenarios

| Symptom | Possible cause | Verification direction |
| --- | --- | --- |
| `/actuator/startup` returns 404 | Missing Actuator, not exposed, access restricted, not using buffering | Check dependency, startup tracker, exposure, and security |
| JSON has no useful events | Default no-op or already POST drained | Enable `BufferingApplicationStartup` before run, check GET before POST |
| Late startup steps missing | Buffer capacity full | Increase capacity or filter deliberately |
| First POST returns events, next POST empty | Drain retrieved and cleared the buffer | Save the response from the first POST |
| Bean named X has long duration | May include dependency init | Inspect parent-child, child steps, and JFR |
| Custom step missing | Code not called, missing `end()`, buffer full, filtered out | Check control flow and tests |
| Filter drops too many steps | Predicate too strict | Re-measure without filter or loosen filter |
| JFR file has no Spring events | Tracker is not JFR, recording does not cover startup | Call `setApplicationStartup` before run, enable JFR before main |
| JFR enabled but actuator startup 404 | Actuator endpoint requires Buffering tracker | Use JFR viewer or switch to buffering in another measurement run |
| Summed duration is too large | Nested/overlapping events | Analyze timeline and parentId |
| Startup steps very fast yet ready is slow | Runners, JVM bootstrap, readiness propagation, un-instrumented code | Measure process→ready and main→ready as well |
| IDs change between deployments | IDs only have meaning within each timeline | Compare by name/tags, not raw IDs |
| Increasing buffer slows startup further | Tracking overhead/GC or environment noise | Controlled benchmark, keep same configuration |
| API has different `spring.*` names than docs | Different Spring Framework version | Check the appendix of the exact version |
| Using startup tracker to measure every request | Wrong tool/semantics | Use Micrometer Observation/Timer/traces |

### Why Is a Startup Event Not the Same as an Application Event?

`ApplicationStartedEvent` / `ApplicationReadyEvent` are **SpringApplication events** in the startup lifecycle. `StartupStep` is a record of a measured interval. A step may wrap event processing, but it is not the event object itself. Do not try `@EventListener(StartupStep.class)` expecting Spring to publish each step as an application event.

### Why Is /actuator/startup Not Readiness?

`/actuator/health/readiness` reflects serving state. `/actuator/startup` returns recorded steps. An app can have a complete set of `StartupStep`s while `REFUSING_TRAFFIC`, or be ready while buffering is not enabled. The two endpoints serve different purposes.

## 15. Practical Startup Time Evaluation Workflow

1. **Lock the goal:** do you need to shorten process→ready, main→ready, context refresh, or first request?
2. **Record the environment:** JDK vendor/version, Spring Boot/Framework version, JAR digest, JVM flags, profiles, CPU/memory limits, storage/DB endpoints.
3. **Enable the tracker early:** `setApplicationStartup(new BufferingApplicationStartup(capacity))` **before** `run(args)`.
4. **Run the application cleanly:** same artifact, same profiles, same external services; do not compare IDE hot restart with a clean process.
5. **Collect GET timeline:** save JSON right after ready, avoiding POST before saving data.
6. **Group steps:** framework phases, bean instantiation, custom startup steps, parent/child.
7. **Find large time regions:** sort durations while mindful of nesting, cross-reference source code/config.
8. **If still unclear:** capture JFR in a separate diagnostic pass to inspect allocations/GC/class loading.
9. **Change one variable intentionally:** e.g., remove I/O from constructors, fix eager dependencies, narrow scan scope, improve cache warm-up.
10. **Re-run across multiple processes:** alternate baseline/variant, compare median/p95, do not use a single startup.
11. **Measure outside the JVM too:** readiness probe, first-hit latency, and resource footprint.
12. **Verify correctness:** bean fail-fast behavior, datasource, scheduler, message listener, and config validation must remain right.
13. **Report step names, before/after durations, environment, and trade-offs**, not just an unsubstantiated "30% faster" number.

### Benchmark Summary Template (No Real Measurements Yet)

~~~text
Artifact / image digest: <recorded from environment>
JDK / Spring Boot / Spring Framework: <actual version>
Tracking implementation: BufferingApplicationStartup(4096)
Recorded steps: <count from timeline>
Missing due capacity/filter: <assessment>
Main-to-ready median: <measured>
External process-to-readiness median: <measured>
Top slow parent steps: <name + measured duration>
Relevant child steps: <name + measured duration>
Change tested: <specific config or code>
Cold first-hit / warm p95 / error rate: <measured>
RSS / heap / CPU: <measured>
Conclusion and rollback plan: <based on data>
~~~

Phrases inside angle brackets are **measurement placeholders**, not assumed results. Store real measurements when experimenting.

## 16. Self-Check Questions

**1. Is `ApplicationStartup` a Spring event?**  
No. It is an instrumentation SPI for startup steps.

**2. Does `ApplicationStartup.DEFAULT` collect a timeline by default?**  
No, it is a no-op.

**3. On which interface is `start(...)` for `StartupStep` called?**  
`ApplicationStartup.start(String name)` returns a `StartupStep`.

**4. Why must `step.end()` be called in `finally`?**  
To complete recording even if initialization logic throws an exception.

**5. Can ID and parentId be used as durable keys across two startups?**  
No. They serve the timeline of a specific recording.

**6. Why shouldn't you create a custom step named `spring.my-feature`?**  
The `spring.*` namespace is reserved for internal framework use; use a custom namespace like `demo.*`.

**7. Why does ApplicationStartup need to be configured before run()?**  
To record steps occurring during SpringApplication/context startup, not just steps after the app is ready.

**8. When BufferingApplicationStartup fills up, does it automatically delete old steps?**  
No. Once capacity is reached, new steps are not recorded.

**9. How do GET /actuator/startup and POST differ?**  
GET reads a snapshot; POST returns data and drains the buffer.

**10. Will calling POST twice in a row necessarily return the same events both times?**  
No. The second call may only contain events generated after the previous drain.

**11. Is having only the Actuator dependency enough to get a startup timeline?**  
No. An appropriate tracker, web exposure, and valid access are required.

**12. Does FlightRecorderApplicationStartup use /actuator/startup instead of JFR?**  
No. It writes events into a JFR recording; the startup endpoint uses the buffering tracker.

**13. Why must step durations not be summed directly?**  
Because intervals can be nested and overlapping, and there is also un-instrumented work.

**14. When context startup fails before HTTP opens, can the startup endpoint be read?**  
Possibly not. Use logs/FailureAnalyzer and JFR/diagnostics started from process launch.

**15. Should you attach an access token to a tag to identify a step?**  
No. Startup data can be exposed via HTTP/JFR/logs.

**16. When seeing slow bean init, should you immediately enable lazy init system-wide?**  
No. Lazy init can shift cost and errors to the first request; measure readiness/cold-hit/heap too and verify business correctness.

## 17. Official Documentation

- [Spring Boot 3.5 — SpringApplication: Application Startup Tracking](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): how to configure buffering and JFR trackers.
- [Spring Boot 3.5 — Actuator Startup REST API](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/startup.html): GET snapshot, POST drain, response fields.
- [Spring Boot 3.5 — BufferingApplicationStartup API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html): capacity, filters, getBufferedTimeline, drainBufferedTimeline.
- [Spring Boot 3.5 — StartupTimeline API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/metrics/buffering/StartupTimeline.html): TimelineEvent, getEvents, getStartTime.
- [Spring Boot 3.5 — Actuator Endpoint Exposure](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): startup endpoint requires Buffering tracker and exposure policy.
- [Spring Framework 6.2 — ApplicationStartup Reference](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html): context instrumentation and custom namespace guidelines.
- [Spring Framework 6.2 — StartupStep API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/metrics/StartupStep.html): getId, parentId, tags, end.
- [Spring Framework 6.2 — Application Startup Steps Appendix](https://docs.spring.io/spring-framework/reference/6.2/core/appendix/application-startup-steps.html): internal steps, names/tags are not an immutable contract.
- [Spring Framework 6.2 — FlightRecorderApplicationStartup API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/metrics/jfr/FlightRecorderApplicationStartup.html): Spring startup data in JFR.
- [Oracle JDK 17 — jfr Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): summary, print, metadata, and reading recordings.

**Conclusion:** `ApplicationStartup` and `StartupStep` help answer more accurately **"which step is making Spring startup slow?"**. Choose `BufferingApplicationStartup` to get quick JSON from Actuator, `FlightRecorderApplicationStartup` for detailed analysis alongside JVM events; set the tracker before `run`, call `end` at the right time, understand parent-child relationships and buffer limits. Treat it as only one part of measurement: **end-to-end readiness, first-hit latency, errors, and resource usage** still need separate evaluation.