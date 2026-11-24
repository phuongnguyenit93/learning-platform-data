# Practice: Measuring BufferingApplicationStartup and Identifying Slow Startup Phases

## 1. Problem Statement and Success Criteria

When a Spring Boot application starts slowly, a summary log like `Started Application in 4.2 seconds` does not answer **which phase** consumed the time: reading configuration, component scanning, parsing `@Configuration`, creating beans, connecting to databases, warming up caches, or executing runners.

This practice lab uses **`BufferingApplicationStartup`** to record a timeline of `StartupStep` entries emitted by Spring Framework and application code. We deliberately introduce a slow initialization step, measure it, inspect parent-child relationships, and then remove the delay to measure again. The goal is not to produce a pretty benchmark number, but to build a **data-backed bottleneck-finding workflow**.

Technologies:
- **Java 17+**, Maven, **Spring Boot 3.5.16**, Spring Framework 6.2.x.
- `spring-boot-starter-web` and `spring-boot-starter-actuator`.
- `BufferingApplicationStartup` initialized **before `SpringApplication.run`**.
- `GET /actuator/startup` to save a JSON snapshot; `POST` only when genuinely wanting to drain.
- `jq` or a **Python 3 standard library** script to analyze both JSON files.
- JUnit 5 / AssertJ to test custom instrumentation.

The lab runs two configurations on **the same JAR**:
1. `--demo.catalog.delay-ms=800`: intentionally waits about 800 ms inside a bean factory method.
2. `--demo.catalog.delay-ms=0`: no wait, still creates the bean and returns the same response.

A passing practice result must pinpoint **`demo.catalog.initialize` as slow in the 800 ms mode**, explain how it sits inside `spring.beans.instantiate` and `spring.context.refresh`, and confirm the wait vanished in the control run. Actual durations must be **read from JSON**, never fabricated.

## 2. Where Does `BufferingApplicationStartup` Fit in the Startup Lifecycle?

Spring Framework defines:
- `org.springframework.core.metrics.ApplicationStartup` — interface producing measurement steps.
- `org.springframework.core.metrics.StartupStep` — a unit of work with name, ID, parent ID, tags, and `end()`.
- `ApplicationStartup.DEFAULT` — **no-op** implementation with no useful timeline recording.

Spring Boot defines:
- `org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup` — bounded buffer holding recorded steps with timestamps and durations.
- `StartupTimeline` and `StartupTimeline.TimelineEvent` — snapshot data objects.
- Actuator `startup` endpoint — exposes the timeline as JSON when an appropriate buffering tracker is attached.

~~~mermaid
flowchart TD
  MAIN["main(args)"] --> TRACKER["SpringApplication.setApplicationStartup(BufferingApplicationStartup)"]
  TRACKER --> RUN["SpringApplication.run(args)"]
  RUN --> FRAMEWORK["Framework: spring.boot.*, spring.context.*, spring.beans.*"]
  FRAMEWORK --> CUSTOM["App: demo.catalog.initialize"]
  CUSTOM --> END["StartupStep.end()"]
  END --> BUFFER["In-memory bounded timeline"]
  BUFFER --> GET["GET /actuator/startup: snapshot"]
  BUFFER --> POST["POST /actuator/startup: drain"]
  GET --> ANALYZE["Compare duration, tags, id, parentId, and timestamps"]
~~~

**Important:** this illustrates data flow. Steps can be **nested**, rather than running strictly sequentially top-to-bottom across every branch of the diagram. `spring.beans.instantiate` typically includes dependency/bean initialization time, so a custom child's duration may already sit inside its parent's window.

### Why Configure It Before `run()`?

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(4096));
app.run(args);
~~~

The snippet above needs `MyApplication` and corresponding imports. If you create `BufferingApplicationStartup` **after** the context has refreshed, you get **no retroactive data** for earlier steps. Do not instantiate a new recorder inside `@PostConstruct` expecting to see configuration parsing that already happened before it.

### Fields of `StartupStep` and Timeline Events

| Field | Meaning | Notes |
| --- | --- | --- |
| `startupStep.name` | Work unit name, e.g. `spring.beans.instantiate` | Internal name, not an immutable API |
| `startupStep.id` | Step identifier within this startup run | Not a timestamp or business ID |
| `startupStep.parentId` | Parent step ID if present | Top-level steps may omit this field |
| `startupStep.tags[]` | Key/value metadata, e.g. `beanName=catalog` | Must not contain secrets/PII |
| `startTime`, `endTime` | Start/end timestamps of the measured interval | Interpret against clock/recording scope |
| `duration` | ISO-8601 Duration such as `PT0.812S` | A string, not numeric ms |

Do not match steps across two runs by `id`: IDs are assigned per recording. Compare by **name + tags + context**, not raw ID numbers.

## 3. Conditions for a Reproducible Measurement

Before coding:
- Run `java -version` and confirm JDK **17+**.
- Run `mvn -version` to confirm Maven and the Java version Maven uses.
- Keep the artifact, JVM flags, profiles, CPU quota, RAM/heap, and downstream resources identical across both runs.
- Do not enable DevTools restarts between runs; use a **fresh JVM process** for slow and fast.
- Confirm port `18096` is not occupied by another process.
- Wait for readiness before capturing the Actuator snapshot; an unready app may not yet serve HTTP.
- Never call `POST /actuator/startup` before saving the GET snapshot.
- Never treat a single startup run as sufficient for production performance conclusions.
- If bootstrap fails immediately, the HTTP endpoint may not open; use stack traces/FailureAnalyzer or JFR enabled from launch.

Measuring **end-to-end** from process spawn to readiness is not the same as the timeline. The buffering tracker only measures **instrumented segments** and may not cover JVM bootstrap before `main`, external routing/readiness propagation, or post-refresh tasks.

## 4. Creating the Spring Boot Maven Project

Structure:

~~~text
startup-buffer-lab/
├── pom.xml
├── measure.sh
├── analyze_startup.py
└── src/
    ├── main/
    │   ├── java/com/example/startupbuffer/
    │   │   ├── StartupBufferApplication.java
    │   │   ├── CatalogConfiguration.java
    │   │   └── CatalogController.java
    │   └── resources/application.yaml
    └── test/java/com/example/startupbuffer/
        └── CatalogConfigurationTest.java
~~~

`measure.sh` and `analyze_startup.py` are analysis utilities on the **development machine**. The Java application does not depend on Python in production.

### 4.1. `pom.xml`

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
    <artifactId>startup-buffer-lab</artifactId>
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

**Maven parent 3.5.16** manages Boot/Framework and JUnit dependencies. The project does not need Spring Security just for the lab, though real applications must secure the `startup` endpoint.

### 4.2. `src/main/resources/application.yaml`

~~~yaml
spring:
  application:
    name: startup-buffer-lab
  main:
    banner-mode: "off"

server:
  port: 18096

demo:
  catalog:
    delay-ms: 800

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,startup
~~~

- `demo.catalog.delay-ms` is an experimental parameter, not a standard Spring Boot property.
- `management.endpoints.web.exposure.include` exposes the `startup` endpoint over HTTP **in the lab**.
- Readiness/health endpoints help observe when the application is ready.
- Never expose bean/class/tag details to the public Internet; configure security/network/access per real system policies.

### 4.3. `src/main/java/com/example/startupbuffer/StartupBufferApplication.java`

~~~java
package com.example.startupbuffer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class StartupBufferApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupBufferApplication.class);

        // Tracker MUST be attached before run() to capture framework steps.
        application.setApplicationStartup(
                new BufferingApplicationStartup(4096));

        application.run(args);
    }
}
~~~

`4096` is an example capacity. The buffer stores **at most capacity steps**; once full, new steps are dropped. It is **not** a ring buffer that overwrites older steps.

Spring Boot can expose the configured recorder in the bean factory for application components to inject; do not declare another `@Bean BufferingApplicationStartup` and accidentally end up with two instances inconsistent with `SpringApplication`'s tracker.

### 4.4. `src/main/java/com/example/startupbuffer/CatalogConfiguration.java`

~~~java
package com.example.startupbuffer;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.metrics.ApplicationStartup;
import org.springframework.core.metrics.StartupStep;

@Configuration(proxyBeanMethods = false)
public class CatalogConfiguration {

    @Bean
    CatalogData catalog(
            ApplicationStartup applicationStartup,
            Environment environment) {

        long delayMillis = environment.getProperty(
                "demo.catalog.delay-ms", Long.class, 800L);

        StartupStep step =
                applicationStartup.start("demo.catalog.initialize");

        step.tag("component", "catalog");
        step.tag("delayMode",
                delayMillis == 0 ? "fast" : "slow");

        try {
            if (delayMillis < 0 || delayMillis > 10000) {
                throw new IllegalArgumentException(
                        "delay-ms must be between 0 and 10000");
            }

            if (delayMillis > 0) {
                Thread.sleep(delayMillis);
            }

            System.out.println(
                    "CATALOG_INITIALIZED items=3 delay_ms="
                            + delayMillis);

            return new CatalogData(
                    List.of("alpha", "beta", "gamma"));

        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Catalog initialization interrupted", e);
        } finally {
            step.end();
        }
    }

    public record CatalogData(List<String> items) {
    }
}
~~~

**Analysis:**

1. Bean `catalog` is instantiated as a singleton during bootstrap.
2. The factory method injects Spring-managed `ApplicationStartup` and `Environment`; no need to construct a separate recorder inside the method.
3. Custom step `demo.catalog.initialize` measures from before validation/sleep until the end of the factory method.
4. `step.tag` records stable metadata without leaking secrets.
5. `try/finally` ensures the step ends even if validation throws an exception.
6. When `delayMillis=800`, `Thread.sleep(800)` simply simulates slow initialization; when 0, it does not sleep.
7. `CatalogData` is a Java record returning a fixed list. Both experimental branches produce **identical output data**.

Do not use `Thread.sleep` in production startup to "wait for the database to be ready". Real applications need connection timeouts, explicit validation/retry policies, migration/schema checks, and proper readiness semantics.

### 4.5. `src/main/java/com/example/startupbuffer/CatalogController.java`

~~~java
package com.example.startupbuffer;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {

    private final CatalogConfiguration.CatalogData catalog;

    public CatalogController(
            CatalogConfiguration.CatalogData catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/catalog")
    public List<String> catalog() {
        return catalog.items();
    }
}
~~~

The controller forces Spring to resolve the dependency on `CatalogData` and lets us verify functional equivalence between slow and fast modes. An "optimization" is meaningless if it merely skips required work and causes the API to return wrong data.

### 4.6. Build

~~~bash
mvn -q -DskipTests package
~~~

After creating the JUnit file in section 12:

~~~bash
mvn -q test
~~~

The project has two parts: **application + recorder**, and **parser/performance observation tests**. Only proceed to the `java -jar` commands once the JAR builds cleanly.

## 5. Running and Saving the Slow Timeline

In Terminal A:

~~~bash
java -jar target/startup-buffer-lab-0.0.1-SNAPSHOT.jar \
  --demo.catalog.delay-ms=800
~~~

For Windows PowerShell, use a single-line command:

~~~powershell
java -jar target/startup-buffer-lab-0.0.1-SNAPSHOT.jar --demo.catalog.delay-ms=800
~~~

Line printed by the application itself when the bean is created:

~~~text
CATALOG_INITIALIZED items=3 delay_ms=800
~~~

Boot also prints its own startup logs; do not rely on a rigid stdout string across every JVM/logging configuration.

In Terminal B, wait for the server to be ready and check:

~~~bash
curl -fsS http://127.0.0.1:18096/catalog
curl -fsS http://127.0.0.1:18096/actuator/health/readiness
~~~

Expected `/catalog` body:

~~~json
["alpha","beta","gamma"]
~~~

Once the application is ready, readiness health typically returns JSON containing `"status":"UP"` under default configuration. Otherwise, inspect startup logs; never treat an HTTP connection error as duration evidence.

### Save Data Before Draining

~~~bash
curl -fsS http://127.0.0.1:18096/actuator/startup \
  -o slow-startup.json
~~~

This command uses **GET**, which only reads a snapshot and **does not clear the buffer**. Upon success, `slow-startup.json` contains the timeline of recorded `StartupStep` entries.

If `jq` is installed:

~~~bash
jq '.springBootVersion' slow-startup.json
jq '.timeline.events | length' slow-startup.json
~~~

**If events are empty:** the app might be using the no-op tracker, was already drained, or you hit the wrong process/port. Never conclude "the app had no startup steps".

### Finding the Custom Step

~~~bash
jq '.timeline.events[]
    | select(.startupStep.name == "demo.catalog.initialize")' \
  slow-startup.json
~~~

Example **illustrating structure**, not fixed measurements:

~~~json
{
  "startTime": "2026-01-01T10:00:00Z",
  "endTime": "2026-01-01T10:00:00.801Z",
  "duration": "PT0.801S",
  "startupStep": {
    "name": "demo.catalog.initialize",
    "id": 101,
    "parentId": 100,
    "tags": [
      {"key": "component", "value": "catalog"},
      {"key": "delayMode", "value": "slow"}
    ]
  }
}
~~~

**Do not** use `101` or `801 ms` as expected output in JUnit. IDs/timestamps/durations depend on the environment. The delay value is an 800 ms *input*, not a guarantee that measured time will equal exactly 800 ms.

### Finding `spring.beans.instantiate` for `catalog`

~~~bash
jq '.timeline.events[]
    | select(.startupStep.name == "spring.beans.instantiate")
    | select(any(.startupStep.tags[]?;
        .key == "beanName" and .value == "catalog"))' \
  slow-startup.json
~~~

If the `catalog` bean takes significant time and custom `demo.catalog.initialize` sits beneath it (by ID/parent/timestamps), that is evidence the slow work lies inside the factory method. If a bean has a different name due to wiring, inspect the actual tags rather than hardcoding an ID.

**Do not add parent and child durations together**: custom step time is usually **already included** inside bean instantiation time.

## 6. Running and Saving the Fast Timeline

Stop the slow JVM with Ctrl+C or send TERM to its exact PID. Only when port `18096` is no longer held by the old process, start a new JVM:

~~~bash
java -jar target/startup-buffer-lab-0.0.1-SNAPSHOT.jar \
  --demo.catalog.delay-ms=0
~~~

Line printed by the code:

~~~text
CATALOG_INITIALIZED items=3 delay_ms=0
~~~

Capture snapshot:

~~~bash
curl -fsS http://127.0.0.1:18096/catalog
curl -fsS http://127.0.0.1:18096/actuator/startup \
  -o fast-startup.json
~~~

The `/catalog` body remains:

~~~json
["alpha","beta","gamma"]
~~~

In fast mode, the custom step still exists without `Thread.sleep(800)`. Hence when comparing **the custom step itself**, slow is noticeably longer than fast. Exact differences are read by the script from both files rather than hardcoded in the text.

### Quick Inspection with `jq`

~~~bash
jq -r '.timeline.events[]
    | select(.startupStep.name == "demo.catalog.initialize")
    | [.duration, .startupStep.id, .startupStep.parentId]
    | @tsv' slow-startup.json

jq -r '.timeline.events[]
    | select(.startupStep.name == "demo.catalog.initialize")
    | [.duration, .startupStep.id, .startupStep.parentId]
    | @tsv' fast-startup.json
~~~

Note that `duration` is an **ISO-8601 string** such as `PT0.800S`. To sort or subtract, parse into numeric milliseconds rather than sorting raw strings.

## 7. Reading the JSON Response and GET/POST Rules

Spring Boot Actuator 3.5 defines the response (abbreviated sample):

~~~json
{
  "springBootVersion": "3.5.16",
  "timeline": {
    "startTime": "2026-01-01T10:00:00Z",
    "events": [
      {
        "startTime": "2026-01-01T10:00:00.100Z",
        "endTime": "2026-01-01T10:00:00.120Z",
        "duration": "PT0.020S",
        "startupStep": {
          "name": "spring.beans.instantiate",
          "id": 3,
          "parentId": 2,
          "tags": [
            {"key": "beanName", "value": "someBean"}
          ]
        }
      }
    ]
  }
}
~~~

`duration` follows `java.time.Duration.toString()`, usually formatted as `PT...S`; when parsing, use `Duration.parse()` in Java or an appropriate ISO parser in other tools.

### GET — View Snapshot

~~~bash
curl -fsS -X GET \
  http://127.0.0.1:18096/actuator/startup \
  -o snapshot.json
~~~

Does not clear data in the buffer; suitable for inspection.

### POST — Drain

~~~bash
curl -fsS -X POST \
  http://127.0.0.1:18096/actuator/startup \
  -o drained.json
~~~

Returns the data and **removes** buffered steps. A subsequent GET may see very few events or none at all. Never use POST just to "peek" and discard the response if you still need that run's measurements.

If two monitoring clients both call POST, the second client may miss records already drained by the first. Designate **a single consumer responsible for draining** if shipping data to an analytics pipeline.

### Capacity and Filters

Per Spring Boot 3.5 Javadoc:
- `new BufferingApplicationStartup(4096)` starts recording automatically.
- When the buffer is full, **new steps are not recorded**; it is not an overwriting ring buffer.
- `addFilter(Predicate<StartupStep>)` retains only steps matching all filters.
- `getBufferedTimeline()` reads a snapshot.
- `drainBufferedTimeline()` retrieves and clears buffered steps.
- `startRecording()` does not need to be called again; calling it when steps already exist may throw `IllegalStateException`.

If a filter drops parent steps, the `parentId` chain cannot be reconstructed even when the custom step remains. During initial investigation, prefer ample capacity and minimal filtering.

## 8. Automated JSON Analysis with the Python 3 Standard Library

To compare two snapshots without manual counting, create **`analyze_startup.py`** at the project root.

The script:
- reads both JSON files;
- parses ISO-8601 Durations into milliseconds using `Decimal`;
- finds the custom step `demo.catalog.initialize`;
- sorts the Top 8 steps by **numeric duration**;
- walks the parent chain via `id`/`parentId` if related events were retained;
- prints slow duration, fast duration, and delta **from real data**.

~~~python
#!/usr/bin/env python3
import json
import re
import sys
from decimal import Decimal

DURATION = re.compile(
    r"^PT(?:(\d+)H)?(?:(\d+)M)?"
    r"(?:(\d+(?:\.\d+)?)S)?$"
)
TARGET = "demo.catalog.initialize"


def milliseconds(text):
    match = DURATION.fullmatch(text)
    if match is None:
        raise ValueError("Unsupported ISO duration: " + text)

    hours, minutes, seconds = match.groups()
    total = (
        Decimal(hours or "0") * 3600
        + Decimal(minutes or "0") * 60
        + Decimal(seconds or "0")
    )
    return total * 1000


def tags(event):
    return {
        tag["key"]: tag["value"]
        for tag in event["startupStep"].get("tags", [])
    }


def describe(event):
    step = event["startupStep"]
    bean = tags(event).get("beanName")
    label = step["name"] + ((" bean=" + bean) if bean else "")
    return label + " ms=" + f"{milliseconds(event['duration']):.3f}"


def print_parents(event, by_id):
    parent = event["startupStep"].get("parentId")
    visited = set()
    found = False

    while parent is not None and parent in by_id:
        if parent in visited:
            print("  cycle-detected")
            return

        visited.add(parent)
        current = by_id[parent]
        print("  PARENT " + describe(current))
        found = True
        parent = current["startupStep"].get("parentId")

    if not found:
        print("  PARENT not available in snapshot")


def analyze(path):
    with open(path, encoding="utf-8") as file:
        payload = json.load(file)

    events = payload["timeline"]["events"]
    by_id = {
        event["startupStep"]["id"]: event
        for event in events
    }
    matches = [
        event
        for event in events
        if event["startupStep"]["name"] == TARGET
    ]

    print("FILE=" + path)
    print("BOOT=" + payload["springBootVersion"])
    print("EVENTS=" + str(len(events)))

    if len(matches) != 1:
        raise ValueError(
            "Expected one custom startup step, found "
            + str(len(matches))
            + ". Check buffer capacity, filters, mode and bean."
        )

    selected = matches[0]
    duration = milliseconds(selected["duration"])

    print("CUSTOM " + describe(selected))
    print("TAGS " + str(tags(selected)))
    print_parents(selected, by_id)

    print("TOP_INCLUSIVE_STEPS:")
    top = sorted(
        events,
        key=lambda event: milliseconds(event["duration"]),
        reverse=True
    )
    for event in top[:8]:
        print("  " + describe(event))

    return duration


def main():
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: python3 analyze_startup.py "
            "slow-startup.json fast-startup.json"
        )

    slow = analyze(sys.argv[1])
    print()
    fast = analyze(sys.argv[2])
    delta = slow - fast

    print()
    print(f"SLOW_CUSTOM_MS={slow:.3f}")
    print(f"FAST_CUSTOM_MS={fast:.3f}")
    print(f"CUSTOM_DELTA_MS={delta:.3f}")
    print("Delta is for the custom step, not total app startup.")


if __name__ == "__main__":
    main()
~~~

Run once both JSON files exist:

~~~bash
python3 analyze_startup.py \
  slow-startup.json fast-startup.json
~~~

You cannot write a fixed numeric output for the script because the two JSON files come from **two real runs**. It prints `CUSTOM_DELTA_MS`, each step's duration, and the top list dynamically.

### Why Use `Decimal`?

Because `PT0.12S` and `PT0.9S` cannot be sorted lexicographically as millisecond numbers; `Decimal` avoids string-comparison errors and floating-point inaccuracies. The regex intentionally handles the common non-negative `PT[H]H[M]M[S]S` form. If a response contains another ISO variant, the script fails loudly so you can extend the parser rather than silently drawing wrong conclusions.

### Do Not Infer Root Cause Solely from Top 8

If the top list includes `spring.context.refresh`, `spring.beans.instantiate`, and `demo.catalog.initialize`, those three events can reflect **the same nested time**. The top list is a starting point for investigation, **not a summation table of total cost**. Improvement in the custom step is confirmed by changing the delay input and source code; in a real system, add JFR/CPU/DB metrics to explain why.

## 9. Automating Both Modes with Bash

Create **`measure.sh`**. The script runs **two JVMs sequentially**, fetches JSON via GET without draining, and avoids stale PIDs. Designed for Linux/macOS with Bash/curl and Python 3.

~~~bash
#!/usr/bin/env bash
set -euo pipefail

jar="target/startup-buffer-lab-0.0.1-SNAPSHOT.jar"
base="http://127.0.0.1:18096"
pid=""

cleanup() {
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

run_mode() {
  local mode="$1"
  local delay="$2"
  local ready="no"

  java -jar "$jar" "--demo.catalog.delay-ms=$delay" \
    >"$mode.log" 2>&1 &
  pid=$!

  for ((i=0; i<180; i++)); do
    if curl -fsS --max-time 1 \
        "$base/actuator/health/readiness" \
        >/dev/null 2>&1; then
      ready="yes"
      break
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "App exited early: $mode" >&2
      return 1
    fi
    sleep 0.2
  done

  if [[ "$ready" != "yes" ]]; then
    echo "Readiness timeout: $mode" >&2
    return 1
  fi

  curl -fsS "$base/catalog" >"$mode-catalog.json"
  curl -fsS "$base/actuator/startup" \
    >"$mode-startup.json"

  echo "Saved $mode-startup.json"

  kill -TERM "$pid"
  wait "$pid" || true
  pid=""
}

run_mode slow 800
run_mode fast 0
python3 analyze_startup.py \
  slow-startup.json fast-startup.json
~~~

Run:

~~~bash
mvn -q -DskipTests package
bash measure.sh
~~~

**Port ownership warning:** before running, ensure no other application is listening on `18096`. Readiness from another process can fool a simple script. Inspect `slow.log`/`fast.log`, the `CATALOG_INITIALIZED` log, and verify the exact URL before trusting results.

If the app fails to become ready, the script exits non-zero and sends TERM to the running JVM via the trap. `wait` could still linger if an app shutdown hook/worker hangs; in CI, add an external deadline/watchdog. This is a simple lab script, not a replacement for a production benchmark harness.

### Windows PowerShell

You can run the two `java -jar` commands sequentially in terminals and save the HTTP JSON with:

~~~powershell
curl.exe -fsS -o slow-startup.json http://127.0.0.1:18096/actuator/startup
~~~

After stopping the slow run and starting fast, change the output filename to `fast-startup.json`. Use `curl.exe` to avoid PowerShell's legacy `curl` alias and preserve the raw HTTP body. The Python script works identically if Python 3 is installed.

## 10. Analyzing Parent-Child, Inclusive Time, and Self Time

One of the biggest mistakes when analyzing a startup timeline is **summing durations of overlapping steps**.

Model:

~~~mermaid
flowchart TD
  ROOT["spring.context.refresh: inclusive time"] --> BEAN["spring.beans.instantiate(catalog)"]
  BEAN --> CUSTOM["demo.catalog.initialize"]
  ROOT --> OTHER["Other beans/post-processors"]
~~~

Purely **illustrative numbers**:
- `spring.context.refresh`: 1,100 ms;
- `spring.beans.instantiate(catalog)`: 830 ms;
- `demo.catalog.initialize`: 802 ms.

**Wrong:** concluding refresh took 1,100 + 830 + 802 = 2,732 ms.

**Right:** the 802 ms sits inside the 830 ms, and both sit inside the 1,100 ms. Use `parentId`, timestamps, and source code to establish relationships. If multiple child intervals overlap concurrently, computing **exclusive self time** requires subtracting the union of child intervals after resolving overlaps, rather than simply subtracting the sum of child durations from the parent.

A step includes waiting on I/O, locks, GC, or scheduling. `StartupStep.duration` is **elapsed time**, not profiler CPU samples. It tells you "**which segment is slow**", not "**why it is slow**" without inspecting code and other metrics.

### Identifying Where to Look in Real Applications

| Step Group | Where to Inspect Next | Likely Bottleneck |
| --- | --- | --- |
| `spring.context.refresh` | Entire refresh phase | Encompasses many child steps; not a specific root cause itself |
| `spring.context.base-packages.scan` | Base package/component scan | Scanning too broad a package scope |
| `spring.context.config-classes.parse` | Configuration class graph | Heavy imports/conditions, metadata parsing |
| `spring.context.bean-factory.post-process` | BeanFactoryPostProcessor | Slow custom processors |
| `spring.context.beandef-registry.post-process` | BeanDefinitionRegistryPostProcessor | Scanning and bean definition registration |
| `spring.context.beans.post-process` | BeanPostProcessor/proxies | Reflection/proxy/init logic |
| `spring.beans.instantiate` | Bean factory/constructor/dependencies | Synchronous I/O, cache preloading, connections |
| `spring.beans.smart-initialize` | SmartInitializingSingleton | Long warm-up tasks |
| `demo.catalog.initialize` | Lab-defined method | 800 ms sleep removable in fast mode |

`spring.*` names are **Spring Framework implementation details** and can change across versions; do not write CI assertions demanding every step appear with a fixed count and ID.

### Root-Cause Analysis Checklist

1. Filter events with large durations using **numeric Duration**, not string sorting.
2. Skip duplicate parent steps when drilling down into deeper bottlenecks.
3. Follow `parentId` from custom/bean steps to understand context.
4. Check `beanName` and other tags; locate the class/factory method in source.
5. Add custom steps around suspect blocks if framework instrumentation lacks granularity.
6. Cross-check CPU/GC/JFR/I/O/DB traces if code alone does not explain the duration.
7. Create a **single-change** variant, re-measure, and verify responses/behavior remain correct.
8. Never take a duration drop from a warm startup and claim cold process startup will drop by the exact same amount.

## 11. At Which Milestone Is Startup "Finished"?

There are at least four distinct concepts:

| Metric | Start/End Milestone | Tool |
| --- | --- | --- |
| `T_process_ready` | Spawn JVM → readiness endpoint healthy | Out-of-process harness |
| `T_main_ready` | Start of `main` → `ApplicationReadyEvent` | Monotonic clock/logs |
| `T_context_refresh` | Context refresh execution | `spring.context.refresh` |
| `T_custom_catalog` | Start and end of catalog creation method | `demo.catalog.initialize` |

**Do not equate these milestones.** `ApplicationStartedEvent` is published after context refresh yet **before** `ApplicationRunner`/`CommandLineRunner`. `ApplicationReadyEvent` is published **after** runners, after which Spring Boot may transition readiness to ACCEPTING_TRAFFIC. Kubernetes routing/endpoint propagation can add further latency outside the JVM.

If optimizing the custom step barely improves readiness, look at other time buckets such as JVM bootstrap, class loading, GC, server init, runners, remote config, or external readiness polling.

### External Measurement Example (Linux Snippet)

~~~bash
start_ns=$(date +%s%N)
java -jar target/startup-buffer-lab-0.0.1-SNAPSHOT.jar \
  --demo.catalog.delay-ms=800 &
pid=$!

# Run readiness polling with timeout as in measure.sh.
# Measure right when readiness returns success.
end_ns=$(date +%s%N)
ready_ms=$(( (end_ns - start_ns) / 1000000 ))
echo "$ready_ms"
~~~

This is a **methodology snippet**, not a complete standalone script: pasting it without adding the readiness loop captures `end_ns` prematurely. For end-to-end runnable code, use `measure.sh`'s structure and add the two timestamps around it.

On default macOS, `date +%s%N` does not behave like GNU date; use Python `time.perf_counter_ns()` in a harness or another monitoring tool. Never mix timestamps across machines with unsynchronized clocks when computing durations.

## 12. JUnit 5 Tests for Custom `StartupStep`

Create **`src/test/java/com/example/startupbuffer/CatalogConfigurationTest.java`**:

~~~java
package com.example.startupbuffer;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.boot.context.metrics.buffering.StartupTimeline;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CatalogConfigurationTest {

    @Test
    void customStepIsRecorded() {
        BufferingApplicationStartup tracker =
                new BufferingApplicationStartup(16);

        MockEnvironment environment = new MockEnvironment()
                .withProperty("demo.catalog.delay-ms", "0");

        CatalogConfiguration configuration =
                new CatalogConfiguration();

        CatalogConfiguration.CatalogData data =
                configuration.catalog(tracker, environment);

        assertThat(data.items())
                .containsExactly("alpha", "beta", "gamma");

        List<StartupTimeline.TimelineEvent> events =
                tracker.getBufferedTimeline().getEvents();

        assertThat(events).hasSize(1);
        assertThat(events.get(0).getStartupStep().getName())
                .isEqualTo("demo.catalog.initialize");

        assertThat(events.get(0).getDuration())
                .isGreaterThanOrEqualTo(Duration.ZERO);
    }

    @Test
    void failureAlsoEndsTheStep() {
        BufferingApplicationStartup tracker =
                new BufferingApplicationStartup(16);

        MockEnvironment environment = new MockEnvironment()
                .withProperty("demo.catalog.delay-ms", "-1");

        assertThatThrownBy(() ->
                new CatalogConfiguration().catalog(
                        tracker, environment))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("between 0 and 10000");

        List<StartupTimeline.TimelineEvent> events =
                tracker.getBufferedTimeline().getEvents();

        assertThat(events).hasSize(1);
        assertThat(events.get(0).getStartupStep().getName())
                .isEqualTo("demo.catalog.initialize");
    }
}
~~~

Run:

~~~bash
mvn -q test
~~~

The two tests verify:
- The factory method returns expected data and completes the custom `StartupStep`.
- The error branch still invokes `step.end()` via `finally`.
- The tests do not rely on sleep for timing assertions, avoiding the flakiness of benchmarks asserting exact millisecond thresholds.

**Limitation:** this is a unit test of the custom method, **not** proof that the entire Spring container always emits `spring.*` steps with specific counts/IDs. To verify full startup instrumentation, run the JAR and read the endpoint in an integration run.

## 13. Reading `BufferingApplicationStartup` Directly in Java

Actuator is not required to read a buffer instance. The Java API provides:

~~~java
BufferingApplicationStartup recorder =
        new BufferingApplicationStartup(16);

StartupStep step = recorder.start("demo.short.task");
try {
    // Code to measure.
} finally {
    step.end();
}

StartupTimeline snapshot = recorder.getBufferedTimeline();
for (StartupTimeline.TimelineEvent event :
        snapshot.getEvents()) {
    System.out.println(event.getStartupStep().getName()
            + " " + event.getDuration());
}
~~~

This is a **snippet**, requiring imports:
- `BufferingApplicationStartup`,
- `StartupTimeline`,
- `StartupStep`.

Taking a snapshot is non-destructive. Calling:

~~~java
StartupTimeline drained = recorder.drainBufferedTimeline();
~~~

removes the buffered steps from the buffer. In real Boot apps, read only **the instance attached to `SpringApplication`**; a new recorder created after startup contains none of the earlier steps.

`BufferingApplicationStartup` can be injected into Spring Boot-managed beans once that tracker is configured. However, if you drain it yourself inside an `ApplicationRunner`, Actuator may subsequently see empty data—they can share the same buffer.

## 14. Performing A/B Testing More Scientifically

The 800 ms experiment teaches the mechanics. For real workloads:
1. Lock artifact checksums, Spring Boot/JDK versions, profiles, and JVM flags.
2. Fix CPU/RAM/quotas, external services, data sizes, and network conditions.
3. Alternate slow/fast runs across fresh JVMs: A→B→B→A.
4. Save JSON immediately after readiness on each run.
5. Record both `T_process_ready` and `T_custom` without substituting one for the other.
6. Separate cold-start/first-run from warm OS cache when relevant.
7. Compute median, p95, error rate, and variance rather than comparing two single numbers.
8. Verify cold-request endpoint performance after optimization.
9. Preserve data correctness, transactions, and ready semantics.
10. Claim improvement only when differences exceed measurement noise without introducing regressions.

**One variable at a time** is fundamental to causal analysis: if you simultaneously upgrade Spring, add caching, resize datasource pools, and remove a sleep, you cannot attribute startup differences to a single cause.

### Lazy Initialization Can Shift Cost to the First Request

`spring.main.lazy-initialization=true` sometimes reduces eager initialization time, yet can push bean failures/latency **past readiness**. Before enabling it:
- is it acceptable to report ready while beans are uninitialized?
- will a cold first request meet its SLO?
- do you need fail-fast to catch bad credentials/schemas early?
- can heap and thread capacity handle concurrent lazy initialization?

Do not trade away correct system behavior for a lower startup metric.

## 15. When the Buffer Cannot Explain Slowness

`BufferingApplicationStartup` shows **instrumented steps**, not full stack traces or CPU samples. If a step is large yet source code does not explain why, use **`FlightRecorderApplicationStartup`** in a **separate run**.

~~~java
SpringApplication app = new SpringApplication(MyApp.class);
app.setApplicationStartup(
        new FlightRecorderApplicationStartup());
app.run(args);
~~~

This is a snippet requiring importing `org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup` and an appropriate `MyApp` class. When launching the JAR, enable JFR:

~~~bash
java -XX:StartFlightRecording=filename=startup.jfr,dumponexit=true,settings=profile \
  -jar target/startup-buffer-lab-0.0.1-SNAPSHOT.jar
~~~

For this project, you must **change the tracker in `main`** to FlightRecorder and rebuild before the command above actually records Spring-specific startup events. Merely passing JFR flags while keeping the Buffering tracker does not automatically turn buffered steps into JFR events.

JFR helps correlate startup with allocations, classloading, GC, and CPU behavior, while Boot's `/actuator/startup` endpoint is specifically for the Buffering tracker; in JFR mode, do not expect the same JSON timeline from that endpoint.

## 16. Troubleshooting While Running the Lab

| Symptom | First Check | Fix |
| --- | --- | --- |
| `/actuator/startup` returns 404 | Actuator dependency, web exposure/access, and tracker | Expose `startup` properly; verify Boot config |
| `/actuator/startup` returns 401/403 | Endpoint protected by Spring Security | Use valid credentials; do not open publicly |
| Events are empty | No-op tracker or already drained | `setApplicationStartup` before `run`; use GET |
| Very few events | Small capacity/filter or POST called earlier | Increase capacity, remove diagnostic filters, run fresh |
| Custom step missing | Bean not created, filtered/dropped, wrong instance | Check `CATALOG_INITIALIZED` log and mode |
| `parentId` missing | Top-level step or parent not recorded | Use timestamps/source; do not invent parents |
| Durations like `PT0.5S` sort incorrectly | Sorted as strings | Parse numeric Duration |
| Slow/fast JSON look identical | Hit same PID or CLI delay not applied | Verify logs, URL, and `delayMode` |
| App fails to start | Port `18096` occupied or bad config | Check startup failure logs, PID, port |
| Fast custom step is short yet ready is slow | Another phase causes slowness | Analyze Top steps and external readiness |
| Bean tag differs from example | Framework version/instrumentation differs | Inspect raw tags, code, and timestamps |
| JUnit passes yet HTTP fails | Unit test doesn't boot web context | Run the JAR and test Actuator |
| Python parser reports unsupported Duration | ISO format differs from regex | Inspect JSON and extend parser properly |
| JSON lost after POST | Drain is intentional | Save GET snapshot first |
| Process doesn't exit after Ctrl+C | Shutdown hooks/non-daemon threads still alive | Inspect PID/thread dumps, check resources |
| Timeline is fast yet first request is slow | Lazy init or deferred warm-up | Measure cold first hit and error rate |
| Startup API leaks internal data | Endpoint exposed publicly | Lock down security/network; use short recordings |
| Monitoring agent already called POST | Shared buffer was drained | Coordinate collection ownership |

### Missing Parent Chain Does Not Mean No Nesting

The buffer may have filled up, a parent step may have been filtered out, or a custom step may have been created outside the scope you assumed. Inspect full events and timestamps. `parentId` is very helpful, yet not a complete guarantee of every causal dependency.

### Is `Step.duration` CPU Time?

No. `duration` measures elapsed processing time, which can include I/O, lock waiting, sleep, GC, and scheduler delays. For CPU bottlenecks, use profilers/JFR CPU samples; for databases, use SQL timings and connection pool metrics.

### Do Not Put Secrets into Tags

For example, `step.tag("password", value)` or URLs containing tokens are a security risk. Startup JSON/JFR/logs can leave the process and be stored long-term. Use stable component/operation names and restrict endpoint access.

## 17. Result Report Template for a Real Application

After measuring, compile a table with **actually collected data**:

| Report Field | How to Fill |
| --- | --- |
| Artifact / JAR digest | Build hash/version |
| JDK / Boot / Framework | From actual runtime |
| Deployment / CPU quota / heap | From measurement environment |
| Recorder | `BufferingApplicationStartup(capacity)` |
| Slow/fast event counts | `timeline.events.length` of each JSON |
| Custom step name | e.g., `demo.catalog.initialize` |
| Custom duration slow/fast | Convert ISO Duration → ms |
| Parent steps | From parentId and tags, when present |
| Top inclusive steps | Ranked by numeric duration |
| Process→ready slow/fast | External stopwatch |
| Cold first request / correctness | Response + latency + errors |
| Run count, median, p95 | Across multiple processes |
| Change tested | One specific factor |
| Decision/rollback | Based on SLOs and reliability |

**Never write "saved 800 ms" without measuring.** `delay-ms=800` is an experiment input; results are the durations actually collected and analyzed.

## 18. Anti-Patterns to Avoid

**1. Adding Actuator without attaching a recorder.**  
`ApplicationStartup.DEFAULT` is a no-op and yields no timeline.

**2. Initializing the recorder after context refresh.**  
Cannot capture steps that already happened earlier.

**3. Calling POST while still needing to compare data.**  
POST drains the buffer; GET takes a non-destructive snapshot.

**4. Adding parent and child durations together.**  
Inflates totals beyond real startup time by double-counting.

**5. Sorting `duration` as text.**  
ISO Duration strings do not sort numerically like milliseconds.

**6. Inferring root cause from a slow step without reading source.**  
Elapsed duration locates where, not whether it is DB, CPU, I/O, or locks.

**7. Optimizing purely by turning on lazy initialization app-wide.**  
Can push cost/errors to runtime and break cold-request SLOs.

**8. Using data from a single run.**  
OS/JIT/cache/CPU noise makes single-run conclusions unreliable.

**9. Attaching secrets to tags.**  
Metadata can leak via endpoints/logs/recordings.

**10. Matching `StartupStep.id` across two JVMs.**  
IDs are not cross-recording correlation keys.

**11. Increasing capacity indefinitely.**  
Increases memory/overhead; pick capacity deliberately.

**12. Using the Buffering tracker for general request tracing.**  
It is built for startup; use Observation/Micrometer/OpenTelemetry for request tracing.

**13. Forgetting `step.end()` on exceptions.**  
Leaves incomplete steps or drops needed records in the recorder.

**14. Measuring only `context.refresh` without measuring readiness.**  
Runners and platform routing can still add substantial cost.

## 19. Practice Checklist

- [ ] Java 17+, Spring Boot 3.5.16 project built.
- [ ] `BufferingApplicationStartup(4096)` attached before `run(args)`.
- [ ] Actuator `startup` endpoint exposed only in a safe lab environment.
- [ ] Code includes `demo.catalog.initialize` and `step.end()` in `finally`.
- [ ] Slow/fast runs executed in two separate JVMs from **the same JAR**.
- [ ] Slow logged `CATALOG_INITIALIZED items=3 delay_ms=800`.
- [ ] Fast logged `CATALOG_INITIALIZED items=3 delay_ms=0`.
- [ ] `/catalog` returned identical JSON in both modes.
- [ ] Saved `slow-startup.json` and `fast-startup.json` using GET.
- [ ] Did not call POST before saving data.
- [ ] Analyzed event counts, custom step, and tags.
- [ ] Parsed `duration` into numeric milliseconds.
- [ ] Identified parent-child relationships where parentId is available.
- [ ] Did not sum durations of nested steps.
- [ ] Measured readiness externally when making end-to-end startup claims.
- [ ] Ran JUnit to test custom instrumentation and failure path.
- [ ] Recorded versions/config/resources and multiple runs for performance comparisons.
- [ ] Checked lazy-init failures and first-hit latency before deciding on optimizations.
- [ ] Declared a bottleneck only with source code + data + control comparison.

## 20. Self-Check Questions

**1. When must `BufferingApplicationStartup` be configured?**  
Before `SpringApplication.run(...)` so it captures early startup steps.

**2. Is adding `spring-boot-starter-actuator` alone enough?**  
No. `ApplicationStartup.DEFAULT` is a no-op; an appropriate tracker is required.

**3. Why must `StartupStep.end()` be in `finally`?**  
So the recorder knows the step completed even if an exception is thrown.

**4. Does a full buffer overwrite old steps automatically?**  
No; new steps are not recorded once capacity is reached.

**5. How do GET and POST `/actuator/startup` differ?**  
GET snapshots; POST drains.

**6. Is `duration` in JSON numeric ms?**  
No, it is an ISO Duration string such as `PT0.8S`.

**7. Can step IDs be used to match steps across two runs?**  
No, match by name/tags/context and corresponding data.

**8. Why not add `spring.beans.instantiate` and custom child durations?**  
They can overlap; adding them double-counts time.

**9. Does a 900 ms step mean 900 ms of CPU was consumed?**  
No, duration includes waits/I/O/sleep and scheduler effects.

**10. Does removing an 800 ms slow input guarantee total startup drops by exactly 800 ms?**  
No. Measure actual JSON and readiness to conclude.

**11. Why run A/B on the same JAR in isolated JVMs?**  
To isolate a single variable and avoid mixing builds or instances.

**12. If the custom step is missing, what should you check?**  
Whether the bean was created, right tracker attached, capacity/filters/drain, and URL/PID.

**13. Does `ApplicationReadyEvent` fire before or after runners?**  
After `ApplicationRunner`/`CommandLineRunner`.

**14. If config refresh is fast yet readiness is slow, what should you do?**  
Measure process→ready, runners, JVM bootstrap, probes/routing, and uninstrumented steps.

**15. Should you use `FlightRecorderApplicationStartup` when CPU/GC correlation is needed?**  
Yes, in a dedicated run with JFR recording; Actuator buffer JSON does not replace JFR.

**16. Is putting a password into a `StartupStep` tag safe?**  
No; metadata can be exposed externally.

## 21. Official Documentation

- [Spring Boot 3.5 — SpringApplication and Application Startup Tracking](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): attaching trackers before run, lifecycle events, JFR.
- [Spring Boot 3.5 — Actuator Startup REST API](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/startup.html): GET snapshot, POST drain, response JSON fields.
- [Spring Boot 3.5 — BufferingApplicationStartup API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html): capacity, filters, `getBufferedTimeline`, and `drainBufferedTimeline`.
- [Spring Boot 3.5 — StartupTimeline API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/metrics/buffering/StartupTimeline.html): `TimelineEvent`, `getDuration()`, `getStartupStep()`.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): endpoint exposure/access/security/readiness.
- [Spring Framework — Application Startup Steps](https://docs.spring.io/spring-framework/reference/core/appendix/application-startup-steps.html): names and semantics of internal steps.
- [Spring Framework 6.2 — ApplicationStartup API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/metrics/ApplicationStartup.html): DEFAULT no-op, `start(name)`.
- [Spring Framework 6.2 — StartupStep API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/metrics/StartupStep.html): id, parentId, tags, `end()`.
- [Oracle Java 17 — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): ISO Duration parsing.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): unit testing.

**Conclusion:** To accurately pinpoint a slow startup phase, **record `StartupStep` entries before `run`, inspect the JSON snapshot, analyze durations and parent-child relationships, trace to the impactful code, and run a control comparison on the same artifact**. `BufferingApplicationStartup` locates where time went; true root causes must be backed by source/logs/JFR/metrics while verifying readiness, first-hit latency, and business correctness.