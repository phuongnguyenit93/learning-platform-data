# Observing Startup Time via the startup Endpoint

An application takes several seconds to start, but a single log line “Started ... in ... seconds” does not show where the time went. Spring might be instantiating beans, processing configuration, waiting on an application initialization step, or performing multiple nested tasks. The Spring Boot Actuator `startup` endpoint lets you inspect the recorded startup steps, along with their timestamps, durations, and parent-child relationships.

The goal of this guide is to learn how to collect data properly from the start, take a safe snapshot, read durations in the right units, and find leads for investigating slow startup. This guide uses Spring Boot 3.3.x; the examples pin Boot 3.3.13 and JDK 21 for reproducibility, which does not imply they are the latest versions.

## 1. Understanding the Role of startup

During startup, `SpringApplication` and `ApplicationContext` perform many tasks. Instrumented parts create `StartupStep` instances: each step has a name, an ID, an execution duration, and optional attached metadata called tags.

Separate the three responsibilities:

```text
ApplicationStartup
    -> receives StartupStep start/end milestones

BufferingApplicationStartup
    -> stores recorded steps in a bounded buffer

Actuator startup endpoint
    -> exposes buffered data over HTTP
```

The endpoint is where you read the data, not a switch that automatically retrofits data for earlier startups. If you do not enable the appropriate recording mechanism before running the application, adding `startup` to the exposure list later will not recover skipped steps.

Some common steps relate to bean creation or context initialization. Not every Java statement, database query, or piece of JVM code automatically becomes its own step. When a step is long, the data shows that the measured interval took time; to determine exactly how CPU, I/O, class loading, or GC contributed, you may need additional profiling tools.

Spring Boot supports choosing an `ApplicationStartup` when configuring the `SpringApplication` object; `BufferingApplicationStartup` is the choice that serves the buffer and JSON endpoint. [Startup Tracking in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.startup-tracking).

### 1.1. Measurements That Are Easily Confused

| Information | What question does it answer? |
| --- | --- |
| Total startup time log line | Roughly how long did this run take up to that log milestone? |
| `startup` timeline | During which intervals did the recorded steps occur? |
| `application.started.time` | Metric for the time until the application has started |
| `application.ready.time` | Metric for the time until the application is ready to serve traffic |
| Deployment platform readiness or startup probe | Should the system route traffic to the application or keep waiting for it? |

The `startup` endpoint is not a `startupProbe` and does not replace readiness. The two metrics `application.started.time` and `application.ready.time` are not a detailed list of steps either. Work in runners or during serving preparation can make these aggregate milestones differ. [Application Startup Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.application-startup).

## 2. Configuring Data Recording Before Running

The key point is in `main`, before calling `run`:

```java
SpringApplication application = new SpringApplication(StartupDemoApplication.class);
application.setApplicationStartup(new BufferingApplicationStartup(2048));
application.run(args);
```

This is a configuration snippet, not yet a standalone Java file. The full example later includes the corresponding imports and class.

`2048` is the buffer capacity by step count, not milliseconds and not bytes. A finite capacity bounds the amount of information kept in memory. When the limit is reached, new steps may no longer be recorded; do not treat this as a ring buffer that automatically keeps the newest 2048 steps.

Do not place `BufferingApplicationStartup` into a late-created `@Bean` and expect it to record all the work Spring performed earlier. Also do not manually call `startRecording()` on every HTTP read: the constructor already starts recording, while the API for resetting the recording baseline has its own usage conditions.

If you need to filter out some data, you can use `addFilter` before `run`. Example replacing the configuration part in `main`:

```java
BufferingApplicationStartup startup = new BufferingApplicationStartup(4096);
startup.addFilter(step ->
        step.getName().startsWith("spring.beans.")
                || step.getName().startsWith("demo."));
application.setApplicationStartup(startup);
```

The snippet above assumes the variable `application` already exists and `run` has not been called yet; it is not a second program. The filter decides which steps are stored, not which work is executed. When a parent step is filtered out, remaining child steps may reference a `parentId` that is absent from the snapshot. This must be accounted for when building a tree.

The API clearly separates capacity limits, filtering, taking a snapshot, and draining data from the buffer. [Boot 3.3 BufferingApplicationStartup](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html).

## 3. Enabling the Endpoint and Choosing How to Read It

The application needs Actuator, the appropriate `BufferingApplicationStartup` recorder, and the endpoint exposed over the web channel. With default paths, the relevant configuration is:

```yaml
management:
  endpoint:
    startup:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,startup
```

Enabling the endpoint and exposing it over HTTP are two different conditions. Adding only `enabled: true` does not automatically expose it over the network; adding it only to `include` does not replace the requirement of having a recorder. The effective configuration is also affected by profiles and overriding property sources. [Startup Endpoint Conditions and Exposure Rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 3.1. GET Preserves Data; POST Drains Data

| Request | Success result | Effect on buffer |
| --- | --- | --- |
| `GET /actuator/startup` | `200 OK` and snapshot JSON | Does not remove the returned steps |
| `POST /actuator/startup` | `200 OK` and JSON of drained steps | Removes the drained steps from the buffer |

**POST here does not mean “measure again from scratch”.** It performs a data-retrieval operation commonly called a drain. It does not restart the application, does not re-run bean creation, and does not return an empty 204. If you need to compare against a fresh startup, you must collect data from that new run.

For observability tools that need to preserve data for others, prefer `GET`. If you use `POST` to export data to another storage system, you must manage who owns draining and handle storage failures. One tool draining the buffer can prevent later readers from seeing earlier steps.

After a drain, a subsequent `GET` does not necessarily always return an empty array: the system may have just produced new steps, such as from late bean creation. The key point to understand is that steps that have been drained do not remain in the buffer just because a user wants to view them again. [Startup GET and POST Contract](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html).

## 4. Runnable Example: Recording an Intentional Initialization Step

The example creates a `warmupData` bean containing a `demo.warmup` step. This step intentionally waits about 120 ms to produce a noticeable measured interval. This is a simulated delay for the exercise, not an optimization technique or a recommendation to add sleep time to a real application.

### 4.1. Structure and Dependencies

Create a new Maven project:

```text
startup-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/StartupDemoApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/example/StartupEndpointTest.java
```

Use JDK 21 and Maven. The verification file in section 8 can be added after reviewing the application code.

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>startup-demo</artifactId>
    <version>1.0.0</version>
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

The web starter provides HTTP, Actuator provides management endpoints, and the test starter is only used for verification. For an existing project, keep the project's own version management mechanism; you do not need to restructure the entire project to apply three lines of `ApplicationStartup` configuration.

### 4.2. application.yml

```yaml
spring:
  application:
    name: startup-demo

server:
  address: 127.0.0.1
  port: 8099

management:
  endpoint:
    startup:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,startup
```

The example listens only on loopback `127.0.0.1:8099` and omits Spring Security to focus on the collection mechanism. This is a local practice configuration. In a secured application, callers must satisfy the existing security policy; exposure does not automatically grant access permissions.

If you use a different management port or Actuator base path, update the URLs in the commands accordingly. If port 8099 is already in use, choose an available port.

### 4.3. StartupDemoApplication.java

```java
package example;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.annotation.Bean;
import org.springframework.core.metrics.ApplicationStartup;
import org.springframework.core.metrics.StartupStep;

@SpringBootApplication
public class StartupDemoApplication {
    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(StartupDemoApplication.class);
        application.setApplicationStartup(new BufferingApplicationStartup(2048));
        application.run(args);
    }

    @Bean
    WarmupData warmupData(ApplicationStartup startup) throws InterruptedException {
        StartupStep step = startup.start("demo.warmup");
        step.tag("component", "warmupData");
        try {
            // Simulate a slow initialization step for this local exercise.
            Thread.sleep(120);
            return new WarmupData("ready");
        } finally {
            step.end();
        }
    }

    @Bean
    ApplicationRunner reportWarmup(WarmupData data) {
        return args -> System.out.println("warmup=" + data.status());
    }

    record WarmupData(String status) {
    }
}
```

Three details are worth noting:

1. The recorder is attached to `SpringApplication` before `run` begins.
2. Initialization code uses `ApplicationStartup.start("demo.warmup")` to mark the work interval to observe, then adds the tag `component=warmupData`.
3. `step.end()` is inside `finally`, ensuring the measured interval ends even if the work throws an exception.

Do not forget to end a step before expecting it to appear as a complete event in the timeline. Tags should be short, meaningful, and free of passwords, tokens, or user data.

`reportWarmup` only prints the result status, not a fixed duration. The OS scheduler and other work may cause the actual wait time to differ from 120 ms; do not treat the measured result as a constant determined by the source code.

### 4.4. Compiling, Running, and Capturing a Snapshot

In the directory containing `pom.xml`:

```bash
mvn clean package
java -jar target/startup-demo-1.0.0.jar
```

Maven resolves dependencies and invokes the JDK compiler; do not compile a Spring application with a `javac` command without a classpath. If you have already added the verification file in section 8, `package` also runs that verification.

In addition to the Spring Boot logs, the program itself prints:

```text
warmup=ready
```

Keep the application running and open another terminal to save the data:

```bash
curl -i http://127.0.0.1:8099/actuator/startup
curl -fsS http://127.0.0.1:8099/actuator/startup -o startup.json
```

The first command inspects the HTTP status and headers. The second saves only the JSON; do not use the output with headers from `curl -i` as a pure JSON file. On PowerShell, use `curl.exe` if needed to avoid confusion with the alias.

If configured properly and the caller is authorized, the read response is `200 OK`. The event count, IDs, timestamps, and durations vary between runs; they are not values that must match the documentation identically.

## 5. Reading the Timeline and Parent-Child Relationships

A snapshot has the following main structure:

| Field | How to interpret |
| --- | --- |
| `springBootVersion` | The Spring Boot version of the application |
| `timeline.startTime` | Start timestamp recorded by the timeline, not a guarantee of covering from when the OS created the process |
| `timeline.events` | Events recorded at the time the data was retrieved |
| `event.startTime`, `event.endTime` | Start and end timestamps of the measured interval |
| `event.duration` | Duration as an ISO-8601 string |
| `startupStep.name` | Measured step name |
| `startupStep.id` | Step ID within that recording |
| `startupStep.parentId` | Reference to the parent step when present |
| `startupStep.tags` | Array of `key/value` pairs providing additional context |

Below is a shortened JSON excerpt from a verification run of the example above: keeping only the `demo.warmup` step and the bean-creation step wrapping it. The numbers and timestamps are data from that measurement run; parent steps outside the excerpt are not included.

```json
{
  "springBootVersion": "3.3.13",
  "timeline": {
    "startTime": "2026-11-06T05:08:38.068083100Z",
    "events": [
      {
        "endTime": "2026-11-06T05:08:39.212704100Z",
        "duration": "PT0.1217529S",
        "startTime": "2026-11-06T05:08:39.090951200Z",
        "startupStep": {
          "name": "demo.warmup",
          "id": 44,
          "tags": [
            {
              "key": "component",
              "value": "warmupData"
            }
          ],
          "parentId": 43
        }
      },
      {
        "endTime": "2026-11-06T05:08:39.212704100Z",
        "duration": "PT0.1227533S",
        "startTime": "2026-11-06T05:08:39.089950800Z",
        "startupStep": {
          "name": "spring.beans.instantiate",
          "id": 43,
          "tags": [
            {
              "key": "beanName",
              "value": "warmupData"
            }
          ],
          "parentId": 4
        }
      }
    ]
  }
}
```

In this excerpt:

- Step 44 is `demo.warmup`, with `parentId=43`.
- Step 43 is `spring.beans.instantiate`, with tag `beanName=warmupData`.
- Therefore, the simulated wait lies inside the creation of the `warmupData` bean.
- Step 43 also references step 4, but step 4 was omitted from the illustrative JSON excerpt.

Do not confuse `parentId` with “the step that ran immediately before”. This is a nesting relationship, not a sequence number for chaining all events into a linear path. Also do not use the array index as an ID: the array may contain child steps that finish before their parent steps.

If you build a tree from filtered data, you must accept that some parent steps will be missing. Do not assign a different parent step because of that or treat the data as corrupted. IDs are not stable keys for matching across two different startups either.

### 5.1. duration Is Not a Pre-formatted Millisecond Number

`PT0.1217529S` means 0.1217529 seconds, which equals 121.7529 ms. Do not strip the prefix and interpret the numeric part as milliseconds. Do not sort duration strings lexicographically to find the longest step.

In Java, use `java.time.Duration`. Standalone file `DurationExample.java`:

```java
import java.time.Duration;

public class DurationExample {
    public static void main(String[] args) {
        Duration duration = Duration.parse("PT0.1217529S");
        System.out.println(duration.toNanos() / 1_000_000.0);
    }
}
```

Run with JDK 21:

```bash
javac DurationExample.java
java DurationExample
```

Exact stdout:

```text
121.7529
```

Dividing nanoseconds by `1_000_000.0` preserves the fractional part when representing milliseconds. If you only call `toMillis()`, sub-millisecond precision will not be retained in the integer result. [JDK 21 Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html).

### 5.2. Do Not Sum All Durations as Total Startup Time

A parent step's duration usually already includes the time of child steps executing inside it. In the JSON above, the bean creation step of about 122.7533 ms wraps the `demo.warmup` step of about 121.7529 ms. Adding them together to get about 244.5062 ms would count the wait time nearly twice.

A simple arithmetic scenario:

```text
Parent step:  0 -------------------------- 600 ms
Child step A:     100 ----- 300 ms
Child step B:               300 ----- 500 ms

Parent step duration: 600 ms
Sum of parent + A + B durations: 1000 ms
```

1000 ms is not the actual elapsed time of this 600 ms piece of work.

Even subtracting the sum of child durations from the parent duration requires caution: steps may be missing due to filtering or buffer exhaustion, there may be overlapping intervals, and there may be concurrent work. A “self time” calculation is only reliable when all child intervals have been identified and overlaps are handled properly.

Sorting long steps helps find leads, but does not by itself prove the root cause or the critical path determining total startup time.

## 6. Ranking Long Steps with a Small Tool

To read the saved JSON file, you can use Python 3 and the standard library. The following program supports non-negative durations in `PT...` format with hours, minutes, and seconds like the startup data under consideration; it raises an error if it encounters a format outside that scope rather than guessing the unit.

Save as `rank_startup.py`:

```python
import json
import re
import sys
from decimal import Decimal

PATTERN = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$")


def duration_ms(text):
    match = PATTERN.fullmatch(text)
    if match is None or not any(match.groups()):
        raise ValueError(f"Unsupported duration: {text}")
    hours, minutes, seconds = (Decimal(value or "0") for value in match.groups())
    return (hours * 3600 + minutes * 60 + seconds) * 1000


with open(sys.argv[1], encoding="utf-8") as stream:
    document = json.load(stream)

events = document["timeline"]["events"]
ranked = sorted(events, key=lambda event: duration_ms(event["duration"]), reverse=True)
for event in ranked[:10]:
    step = event["startupStep"]
    tags = {tag["key"]: tag["value"] for tag in step.get("tags", [])}
    parent = step.get("parentId", "-")
    print(f"{duration_ms(event['duration']):.3f} ms "
          f"id={step['id']} parent={parent} {step['name']} "
          f"bean={tags.get('beanName', '-')}")
```

Run on real data:

```bash
python rank_startup.py startup.json
```

The program converts durations to numeric values using `Decimal`, sorts descending, and prints at most 10 events. It uses `beanName` to identify bean-creation steps; a custom step may use other tags, so `bean=-` does not mean the step is useless.

If you save the exact shortened JSON excerpt from section 5 as `startup-excerpt.json`, the command:

```bash
python rank_startup.py startup-excerpt.json
```

prints:

```text
122.753 ms id=43 parent=4 spring.beans.instantiate bean=warmupData
121.753 ms id=44 parent=43 demo.warmup bean=-
```

This is the output for that specific sample data, not a guaranteed measurement on another machine. After finding these two lines, you need to recognize that the second line lies inside the first; do not conclude there are two independent bottlenecks.

## 7. Intentional Collection and Investigating Slow Steps

A useful observation workflow includes:

1. **Lock down measurement conditions:** same JDK version, build, profile, configuration, resources, and network conditions; note whether warm caches, DevTools, or debug mode are active.
2. **Save a snapshot early after the milestone to observe:** use `GET`, preserving the raw data along with run metadata.
3. **Check completeness:** was the buffer large enough, was a filter applied, did another tool already drain it, and has the step of interest already ended?
4. **Find long intervals and read parent-child relationships:** cross-reference tags, beans, and corresponding initialization code.
5. **Supplement with evidence:** check logs, JFR, or information about external waiting operations if the timeline does not yet explain the cause.
6. **Make controlled changes and measure again multiple times:** compare under the same conditions, distinguishing environmental variance from the effect of the change.

Do not claim an optimization succeeded based on a single faster run. Class loading time, disk state, DNS, external connections, and CPU resources can vary between measurements.

If you need to drain data from the buffer to store elsewhere, for example locally without Spring Security you can use:

```bash
curl -fsS -X POST http://127.0.0.1:8099/actuator/startup -o startup-drained.json
```

This command saves the JSON response of the drain. If the client fails to write the file after the server has already drained the data, the old data does not automatically return to the buffer. When multiple monitoring tools are present, agree on which one may drain and which ones only read snapshots.

`GET` does not delete steps, but that does not mean two GET requests always return identical JSON: new steps may still be recorded due to late initialization or additional work. A good verification compares whether old IDs are still present, rather than requiring the event count to remain constant.

### 7.1. Do Not Shift Cost and Consider It Eliminated

Enabling lazy initialization can reduce time before a startup milestone, but can also shift bean creation and failure detection to first use. When evaluating, also check readiness time and first-request latency; do not look only at a lower startup number.

Similarly, moving work to a background task does not prove the application is ready from a business standpoint. You must determine which work is truly a prerequisite for serving traffic and manage readiness accordingly.

If you need to correlate Spring steps with JVM events such as class loading or GC, `FlightRecorderApplicationStartup` is another JFR integration option. It does not automatically replace this endpoint's `BufferingApplicationStartup` requirement. Changing the recorder must align with the appropriate collection goal; do not assume every recorder provides the same JSON buffer.

## 8. Verifying the Snapshot and Drain Contract Automatically

One detail when writing tests is that the recorder configuration is in `main`. By default, `@SpringBootTest` does not invoke `main`, so a test may initialize a different context than the real application. Use `useMainMethod=ALWAYS` to apply that exact configuration in this example. [Calling main in Boot 3.3 tests](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.using-main).

Save the file `src/test/java/example/StartupEndpointTest.java`:

```java
package example;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        useMainMethod = SpringBootTest.UseMainMethod.ALWAYS)
@AutoConfigureMockMvc
class StartupEndpointTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test void snapshotPreservesAndPostDrainsRecordedSteps() throws Exception {
        JsonNode first = snapshot();
        Set<Long> originalIds = ids(first);
        assertThat(originalIds).isNotEmpty();
        assertThat(first.path("springBootVersion").asText()).isEqualTo("3.3.13");
        boolean foundWarmup = false;
        for (JsonNode event : first.path("timeline").path("events")) {
            if (event.path("startupStep").path("name").asText().equals("demo.warmup")) {
                foundWarmup = true;
                assertThat(java.time.Duration.parse(event.path("duration").asText()).toMillis())
                        .isGreaterThanOrEqualTo(100L);
                assertThat(event.path("startupStep").has("parentId")).isTrue();
            }
        }
        assertThat(foundWarmup).isTrue();
        Files.writeString(Path.of("target/startup-snapshot.json"), first.toPrettyString());
        assertThat(ids(snapshot())).containsAll(originalIds);
        String body = mvc.perform(post("/actuator/startup"))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        assertThat(ids(mapper.readTree(body))).containsAll(originalIds);
        Set<Long> after = ids(snapshot());
        assertThat(after).doesNotContainAnyElementsOf(originalIds);
    }

    private JsonNode snapshot() throws Exception {
        return mapper.readTree(mvc.perform(get("/actuator/startup"))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString());
    }

    private Set<Long> ids(JsonNode root) {
        Set<Long> result = new HashSet<>();
        root.path("timeline").path("events").forEach(event ->
                result.add(event.path("startupStep").path("id").asLong()));
        return result;
    }
}
```

Run:

```bash
mvn test
```

The test uses in-process MockMvc without needing to start a real HTTP server. It verifies:

- Startup data is present and the custom step `demo.warmup` exists.
- The custom step has a parent step and reflects the simulated delay.
- A subsequent GET still retains the read IDs.
- POST returns those IDs in the JSON.
- GET after drain no longer contains the drained IDs.

The 100 ms threshold in the test only serves the 120 ms simulated wait step, not a performance benchmark for a real application. The test also saves a snapshot at `target/startup-snapshot.json`; you can pass that file to the ranking script to observe the data from the test run itself.

The count and list of steps when running in a test context may differ from running a JAR with a real server. The test verifies the snapshot/drain contract in the tested configuration; it does not turn test-environment timing into production startup timing.

## 9. Diagnosing Missing Data or Misunderstood Timing

| Symptom | What to check |
| --- | --- |
| Cannot call `/actuator/startup` | Are the port and path right; is Actuator present, the recorder configured before run, and the endpoint enabled and exposed? |
| HTTP 401 or 403 | Authentication and authorization; for POST, also check CSRF in the security policy |
| Test lacks the endpoint while running the app has it | Check whether the test applies customizations made in main |
| Timeline no longer contains old steps | Did some tool call POST or the drain API; are you looking at a different process/run? |
| Missing the final steps | Capacity, filter, capture timing, and whether the step has already ended |
| A parentId is not found in the data | The parent step may have been filtered out, omitted from the excerpt, or not retained; do not reparent it to another step |
| Some durations are very small or display 0 ms | Check units and rounding; integer milliseconds can lose fractional parts |
| Sum of durations exceeds the logged time | Nested or overlapping steps are counted multiple times |
| An operation to investigate is not visible | Check whether the operation was marked with StartupStep; the endpoint does not automatically measure every statement |
| App has not opened HTTP or failed to start | Do not rely on the endpoint as the sole investigation channel; use logs or pre-configured tools |
| Startup appears faster after lazy initialization | Also check first-use cost and when the application is actually ready |

You should not increase the buffer indefinitely or add every value to tags to fix missing information. First determine the scope to measure; larger capacity and more detail both carry memory and processing costs.

Startup data exists in the memory of the process under examination, not as a historical store across deployments. On restart, treat it as a new recording and save snapshots out-of-process if you want to compare later.

## 10. Keeping Observability Permissions Appropriate for Production

The timeline can reveal bean names, application classes, initialization structure, and tags you added yourself. Expose it only to people or systems that genuinely need observability; protect both the transport and exported JSON files.

In an application with Spring Security, GET read permissions and POST drain permissions may need to be managed separately. CSRF can also cause POST to be rejected even when GET works; do not disable CSRF application-wide just so a curl command works. Apply an appropriate policy for administrative clients.

Stop the practice application with Ctrl+C when finished. The expected outcome when using this endpoint is a clear chain of evidence: the recorder is enabled early enough, data is retained or drained intentionally, durations are read accurately, and slow intervals are matched to the right work before drawing optimization conclusions.
