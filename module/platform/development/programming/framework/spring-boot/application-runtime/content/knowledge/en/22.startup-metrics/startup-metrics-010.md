# Evaluating Cold Start, Restart, and First-Use Latency in Spring Boot

A Spring Boot application may print `Started ... in ... seconds` very quickly yet handle its first request slowly. Conversely, starting the JVM for the first time can take many seconds, while subsequent requests are fast because classes are loaded, the JIT has compiled hot code, connection pools hold open connections, and caches are populated. If you measure only one "startup time" number, you risk optimizing the wrong layer or shifting latency from startup onto the first user.

Three **scenarios** must be distinguished, measured with explicit timestamps and test conditions:

1. **Cold start:** launching **a fresh JVM/process**, creating a new Spring ApplicationContext, and initializing the web server, beans, and dependencies. This can extend to container/Pod cold start, yet image pull/scheduling time must be separated from Java time.
2. **Restart:** specify clearly whether this means a **full JVM restart**, a **container/Pod restart**, or a **DevTools restart that only swaps the ApplicationContext/classloader within the same JVM**. Each carries different costs and retained caches.
3. **First use:** after the application is reported Ready, the first request or task touches code paths, `@Lazy` beans, serializers, DNS, TLS, JPA queries, templates, or un-warmed caches. This is **real first-use latency**, not necessarily captured inside `ApplicationReadyEvent` time.

**Principle:** an app that reaches "Ready faster" does not necessarily deliver a better experience if it merely defers work to the first request. Measure both **time-to-ready** and **first useful response**, along with CPU/memory resources and readiness correctness.

Examples use **Java 17+ and Spring Boot 3.3.x**. DevTools coverage is strictly for local measurement and development; bringing DevTools into production is not recommended.

## 1. Define the Three Startup Types Before Comparing

| Scenario | JVM/process | Spring ApplicationContext | What may be retained | Measurement purpose |
|---|---|---|---|---|
| **Process cold start** | Creates new JVM | Creates new | OS page cache, image layers, external DNS/caches may still be warm | How long from JVM launch to ready? |
| **Process restart** (stop then run JAR again) | **New JVM** | Creates new | OS page cache or external service caches; **no old JVM heap/JIT retained** | Is the second startup faster thanks to a warm environment? |
| **Container restart** | Usually new JVM process | Creates new | Image may be cached on node; external volumes/caches depend on config | Restart time-to-ready under the orchestrator |
| **DevTools restart** | **Same JVM** | Closes old context, creates new | Base classloader/dependencies and some JVM state still exist | Fast feedback loop during development |
| **First use after Ready** | JVM already running | Context active | JIT/classes/caches/pools warm up across requests | Latency of first request/job vs. later ones |

**Cold start does not automatically mean cold OS cache.** Running `java -jar app.jar` the first time after a reboot can differ from the first run of **a new JVM** on a machine that ran the app earlier. Without controlling OS caches, call the measurement accurately **fresh-process startup**, rather than claiming "completely cold machine".

Similarly, **JVM restart** and **DevTools restart** are not equivalent measurements. DevTools intentionally keeps the base classloader of rarely changed libraries, so restarts are usually faster than launching a fresh JVM.

## 2. Clocks and Milestones to Distinguish

A real timeline may look like this:

~~~text
t0   Launcher starts creating the process
 |
 | JVM bootstrap: load runtime, read classpath/JAR, initial class loading
 |
t1   SpringApplication begins startup sequence
 |
 | ApplicationContext creates/refreshes beans
 |
t2   ApplicationStartedEvent
 |    -> Context refreshed, before ApplicationRunner/CommandLineRunner
 |
 | ApplicationRunner/CommandLineRunner execute
 |
t3   ApplicationReadyEvent
 |    -> Boot milestone indicating normal startup is about to finish
 |
 | Spring Boot updates availability/readiness state per lifecycle
 |
t4   Application readiness probe actually succeeds
 |
 | Traffic is routed to instance (may incur router/Service lag)
 |
t5   First business request arrives
 |    -> May lazy-init beans, build connection pool, load caches, JIT...
 |
t6   First business response completes
 |
t7   An equivalent subsequent request completes
~~~

**Do not assume all milestones coincide.**

- `ApplicationStartedEvent` is published after context refresh, **before** runners.
- `ApplicationReadyEvent` is published very late in the startup sequence, **after** runners; event duration can be obtained from `getTimeTaken()`.
- `ApplicationReadyEvent` does not measure Pod creation, image download, or DNS/network routing.
- A readiness probe is **an HTTP/exec check** with its own schedule and thresholds. When kubelet sees success can be **later** than the ready event milestone.
- The first response can stretch longer due to deferred work. A lightweight health endpoint succeeding does not guarantee heavy business paths are warm.
- If an app has an `ApplicationRunner` synchronously performing long work, the gap from `ApplicationStartedEvent` to `ApplicationReadyEvent` reflects that runner time.

### Metrics to Report Separately

| Metric name | Conceptual formula | Purpose |
|---|---|---|
| `JVM-to-Ready` | Process launch → readiness probe succeeds | Orchestrator/launcher perspective |
| `Spring started time` | SpringApplication internal timer → `ApplicationStartedEvent` | Spring context + pre-runner lifecycle |
| `Spring ready time` | SpringApplication internal timer → `ApplicationReadyEvent` | Includes runners before Ready |
| `Ready-to-first-response` | After Ready → first business response completes | Connects startup with user experience |
| `First-request latency` | First request arrives → first response returns | Cold path of the request |
| `Steady-request latency` | Equivalent request once warm | Baseline reference value |
| `First-use penalty` | First-request latency − warm baseline latency | Estimated added cold latency |

`First-use penalty` must be measured using **equivalent** requests; if the first request reads a large dataset while the next reads only from cache, state explicitly that caching itself is the variable under evaluation.

## 3. Using ApplicationStartedEvent and ApplicationReadyEvent

Spring Boot 3.3 provides `Duration getTimeTaken()` on both events:

- `ApplicationStartedEvent.getTimeTaken()`: time Spring Boot recorded for the app to **start** (after refresh, before runners).
- `ApplicationReadyEvent.getTimeTaken()`: time for the app to be **ready** per Spring Boot's lifecycle.

The value can be `null` if undetermined; observation code should handle this rather than unconditionally calling `toMillis()`.

Illustrative example inside a Spring bean:

~~~java
@Component
class StartupEventReporter {

    @EventListener
    void started(ApplicationStartedEvent event) {
        Duration duration = event.getTimeTaken();
        System.out.println(
                "started_ms=" + (duration == null
                        ? "unknown" : duration.toMillis()));
    }

    @EventListener
    void ready(ApplicationReadyEvent event) {
        Duration duration = event.getTimeTaken();
        System.out.println(
                "ready_ms=" + (duration == null
                        ? "unknown" : duration.toMillis()));
    }
}
~~~

This is an **illustrative snippet**, requiring imports for `Component`, `EventListener`, `Duration`, `ApplicationStartedEvent`, and `ApplicationReadyEvent`. The full runnable program is in section 7.

**Do not compute arbitrarily:** `ready_ms - started_ms` can help estimate the interval between two internal milestones of the same run when both Durations are valid, yet it does not prove the entire gap belongs solely to `ApplicationRunner`. Other events, listeners, and tasks can also contribute to the startup sequence.

### Does the "Started in..." Log Measure the Whole JVM?

Spring Boot typically logs a line like:

~~~text
Started DemoApplication in 3.218 seconds (process running for 3.741)
~~~

This is a **format example**, not an actual measurement in your environment. The "in ... seconds" number reflects startup as calculated by Boot, while "process running for ..." relates to JVM process uptime. The two values can differ and neither includes scheduler image download, waiting for Pod assignment, or network latency to the app.

When comparing multiple runs, **do not take timestamps between log lines from different processes** to infer exact latency. Wall clocks, log flushing, buffering, and start points can differ.

## 4. Which Phases Do ApplicationStartup and the Startup Endpoint Reveal?

Spring Framework has `ApplicationStartup` to record `StartupStep` entries during startup: registering/instantiating beans, processing lifecycle, and Spring-instrumented steps. Spring Boot provides the `BufferingApplicationStartup` implementation.

Configure in `main`:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(2048));
app.run(args);
~~~

This is an illustrative snippet requiring `DemoApplication` plus imports for `SpringApplication` and `org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup`. Configuration must occur **before `run(args)`** to capture initial startup steps.

With `spring-boot-starter-actuator` and the `startup` endpoint exposed over HTTP, you can call:

~~~bash
curl -s http://localhost:8080/actuator/startup
~~~

For Spring Boot 3.3, the endpoint supports:

- **`GET /actuator/startup`**: snapshot of steps remaining in the buffer.
- **`POST /actuator/startup`**: retrieves and **drains** steps from the buffer. Subsequent GETs no longer return those drained steps as before.

The response is JSON with fields such as `timeline.startTime`, `timeline.events[].duration`, and `startupStep.name`, `startupStep.id`, `startupStep.parentId`, `startupStep.tags`. Do not mistake each step duration for a sequential non-overlapping slice: steps have parent-child relationships and can be nested; **do not sum all durations to infer startup time**.

### Startup Endpoint Does Not Appear Just Because Actuator Is Present

You must configure **SpringApplication with BufferingApplicationStartup**, as well as expose the endpoint:

~~~properties
management.endpoints.web.exposure.include=health,metrics,startup
~~~

Without configuring buffering, setting `management.endpoints.web.exposure.include=startup` alone is **not enough** to produce proper data. If the endpoint was disabled by another setting, verify enablement as well. In production, **secure this endpoint** and never expose full startup/bean metadata to the Internet.

The buffer has a **finite capacity**. Choose a size large enough for the detail needed, watch for dropped steps if too small, and account for overhead. When benchmarking performance, keep instrumentation consistently enabled or disabled across runs so results remain comparable.

## 5. FlightRecorderApplicationStartup and JFR: Finding Deeper Causes

When the timeline shows startup is slow yet you don't know why, Java Flight Recorder (JFR) helps correlate Spring startup steps with JVM events such as class loading, allocations, GC, CPU, or observable I/O operations.

Spring Framework provides `FlightRecorderApplicationStartup`:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setApplicationStartup(new FlightRecorderApplicationStartup());
app.run(args);
~~~

This is an **alternative** to `BufferingApplicationStartup` in `main`, not a setting to stack concurrently in the example program. Requires importing `org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup`.

Launch JFR **from JVM start** so startup phases are not missed:

~~~bash
java -XX:StartFlightRecording=filename=startup.jfr,duration=30s \
     -jar build/libs/startup-measurement.jar
~~~

Illustrative command for HotSpot/JDK supporting JFR, run in a lab environment. The trailing `\` is only Unix shell line continuation; on Windows put it on one line or use PowerShell syntax.

Notes:

- If you only run `jcmd <PID> JFR.start` **after the app is already Ready**, early startup events have passed; that recording cannot "measure back in time".
- JFR has overhead and files can contain sensitive operational data. Use authorized recordings with proper retention and security.
- `FlightRecorderApplicationStartup` adds startup events to JFR; it **does not replace** measuring external time-to-ready or the first request.
- Use JDK Mission Control or compatible tooling to inspect flames/stacks/timelines, and compare against the same workload with equivalent JVM settings.

## 6. What Is "First-Use Latency"?

After Spring Boot is Ready, a lot of work still happens only when **a processing path is invoked for the first time**:

- **Lazy beans:** `@Lazy` or `spring.main.lazy-initialization=true` defers bean instantiation.
- **Spring MVC/Jackson:** initializes dispatch, serialization, or serializer caching structures when the first request arrives.
- **JPA/Hibernate:** prepares queries/metadata and opens connections the first time the datasource is used.
- **Network:** DNS lookup, TLS handshake, connection establishment/pool warm-up.
- **CPU/JIT:** class loading and JIT compilation of newly executed code branches.
- **Cache:** the first query must load data, whereas later ones can read the cache.
- **Templates/regex/codecs:** compile or initialize internal caches on first use.
- **External dependencies:** a slow/timing-out downstream service can make a cold request long without being a Spring context flaw.

Thus a service can show:

~~~text
Spring ready time       = 1.2s   (hypothetical example)
First HTTP request      = 750ms  (hypothetical example)
Subsequent warm request = 35ms   (hypothetical example)
~~~

These numbers **illustrate how to read results**, not a Spring Boot benchmark. Do not infer real applications exhibit identical gaps.

### Lazy Initialization: Optimization or Cost Shifting?

Spring Boot supports:

~~~properties
spring.main.lazy-initialization=true
~~~

This can shorten startup time by creating beans **on demand**, instead of all during the startup phase. However, there are two important trade-offs:

1. **Shifts latency** onto the first request/operation.
2. **Delays error detection:** a misconfigured bean may only fail when a user hits it for the first time, rather than failing fast at startup.

To verify the impact, measure the full set: `started_ms`, `ready_ms`, readiness probe, first-request latency, and warm-request latency. Do not compare only a single startup log line.

## 7. Java 17+ Spring Boot 3.3 Example: Measuring Ready and First-Use Independently

The example below includes:

- `ApplicationStartedEvent` and `ApplicationReadyEvent` logging internal Durations.
- `BufferingApplicationStartup` for reading startup steps.
- `/readyz` endpoint for time-to-ready experiments on the main port.
- `/demo/use` endpoint accessing a `@Lazy` bean via `ObjectProvider`.
- The lazy bean **intentionally sleeps 300ms in its constructor** to simulate initialization cost; thus the first request usually has a clear cost difference, while subsequent requests do not recreate the bean.

**The 300ms sleep is strictly an educational mechanism**; never treat it as a production optimization technique.

### 7.1 Project Structure

~~~text
startup-measurement/
├── build.gradle
└── src/
    └── main/
        ├── java/com/example/startup/StartupMeasurementApplication.java
        └── resources/application.properties
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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

springBoot {
    mainClass = 'com.example.startup.StartupMeasurementApplication'
}

tasks.named('bootJar') {
    archiveFileName = 'startup-measurement.jar'
}
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=startup-measurement
server.port=8080
management.endpoints.web.exposure.include=health,metrics,startup
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
management.endpoint.health.show-details=never
logging.level.root=INFO
~~~

`management.endpoint.health.probes.enabled=true` enables Kubernetes probe health groups even when running outside Kubernetes. `management.endpoint.health.probes.add-additional-paths=true` exposes `/livez` and `/readyz` on **the main HTTP port**, so measurement does not rely on a separate management port.

### 7.2 Complete Java File

File `src/main/java/com/example/startup/StartupMeasurementApplication.java`:

~~~java
package com.example.startup;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class StartupMeasurementApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(StartupMeasurementApplication.class);

        // Start recording Spring startup steps BEFORE run(args).
        app.setApplicationStartup(new BufferingApplicationStartup(2048));
        app.run(args);
    }

    @Component
    public static class StartupMarkers {

        @EventListener
        public void started(ApplicationStartedEvent event) {
            System.out.println("EVENT_STARTED "
                    + formatDuration(event.getTimeTaken()));
        }

        @EventListener
        public void ready(ApplicationReadyEvent event) {
            System.out.println("EVENT_READY "
                    + formatDuration(event.getTimeTaken()));
        }

        private static String formatDuration(Duration duration) {
            return duration == null
                    ? "duration=unknown"
                    : "durationMs=" + duration.toMillis();
        }
    }

    @Lazy
    @Component
    public static class SlowCatalog {

        public SlowCatalog() {
            try {
                // Intentional cost for first-use experiment.
                Thread.sleep(300);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "catalog initialization interrupted", exception);
            }
            System.out.println("CATALOG_INITIALIZED");
        }

        public String read() {
            return "catalog-ready";
        }
    }

    @RestController
    public static class DemoController {

        private final ObjectProvider<SlowCatalog> catalogProvider;
        private final AtomicInteger requestCount = new AtomicInteger();

        public DemoController(
                ObjectProvider<SlowCatalog> catalogProvider) {
            this.catalogProvider = catalogProvider;
        }

        @GetMapping("/demo/use")
        public Map<String, Object> use() {
            long began = System.nanoTime();

            // ObjectProvider does not force bean creation in the constructor.
            String result = catalogProvider.getObject().read();

            long handlerMillis = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - began);

            return Map.of(
                    "result", result,
                    "requestSequence", requestCount.incrementAndGet(),
                    "handlerMillis", handlerMillis);
        }
    }
}
~~~

### 7.3 Why Does the Example Distinguish Both Phases?

- `StartupMarkers` is a Spring bean created during normal startup that captures both events and prints Boot's measured durations.
- `SlowCatalog` is annotated with `@Lazy`, so the container **need not instantiate it before** code requests the bean.
- `DemoController` injects only `ObjectProvider<SlowCatalog>`; the provider **does not force `SlowCatalog` creation** when the controller constructor runs.
- The first request hitting `getObject()` triggers instantiation of singleton `SlowCatalog`, sleeps 300ms, and prints `CATALOG_INITIALIZED`.
- Subsequent requests receive the same singleton without sleeping again since the constructor does not re-run.
- `System.nanoTime()` measures **time inside the handler** from method entry to return, suitable for intra-process intervals; it **does not include** all HTTP network/serialization/client latency.

Do not expect `handlerMillis` on the first request to equal exactly 300. It also includes other handler work, scheduling, contention, or GC pauses. Conversely, client-reported total request time is typically higher because it includes phases before and after the handler.

**Concurrency:** Spring singleton initialization is managed by the container. If two initial requests arrive together, both can be affected by waiting on bean init even though the constructor executes only once. Run single-threaded experiments before trying concurrent load.

### 7.4 Build and Run

With Gradle wrapper and JDK 17+:

~~~bash
./gradlew bootJar
java -jar build/libs/startup-measurement.jar
~~~

On Windows PowerShell, replace the build step with `.\gradlew.bat bootJar`. Without a Gradle wrapper, prepare a compatible Gradle installation first. Because this is Spring Boot code, it cannot be compiled standalone with `javac StartupMeasurementApplication.java` without Spring libraries on the classpath.

In startup logs, you will see lines like:

~~~text
EVENT_STARTED durationMs=<actual_milliseconds>
EVENT_READY durationMs=<actual_milliseconds>
~~~

`<actual_milliseconds>` is a **descriptive placeholder**, not a literal string printed by the program. Real results vary by environment, and `EVENT_READY` normally appears after `EVENT_STARTED` in the standard lifecycle.

**Do not expect `CATALOG_INITIALIZED` right during startup** unless another component calls `SlowCatalog`. In this program, the bean is accessed at `/demo/use` to create the first-use example.

### 7.5 Reading Startup Timeline and Verifying First Use

After the application is Ready:

~~~bash
curl -s http://localhost:8080/actuator/health
curl -s http://localhost:8080/actuator/startup
curl -s http://localhost:8080/demo/use
curl -s http://localhost:8080/demo/use
~~~

`/demo/use` returns **fields such as**:

~~~json
{"result":"catalog-ready","requestSequence":1,"handlerMillis":315}
~~~

and next time, for example:

~~~json
{"result":"catalog-ready","requestSequence":2,"handlerMillis":0}
~~~

**315 and 0 are illustrative values only**, not guaranteed expectations; JSON object key order is not guaranteed either. `requestSequence` will be 1 and 2 if no other request hit the endpoint; `CATALOG_INITIALIZED` prints once in the log when the singleton is created.

Verification point: the first request pays the slow bean creation cost; the second request does not recreate that bean. Both happen **after the application is already Ready**. Measuring only `ApplicationReadyEvent.getTimeTaken()` **misses that cost completely**.

### 7.6 Distinguishing GET and POST on the Startup Endpoint

~~~bash
curl -s -X GET http://localhost:8080/actuator/startup
curl -s -X POST http://localhost:8080/actuator/startup
~~~

`GET` retrieves a snapshot; `POST` **drains the buffer**, meaning it reads and removes steps from the current buffer. When running multi-step benchmarks, do not call POST at a step where you later expect GET to still return the original timeline.

Careful: `ApplicationStartup` only records **steps instrumented by Spring**. It does not automatically capture every network connection or every third-party bean, and the timeline may be bounded by buffer size. To observe first-use requests, add metrics/tracing on the endpoint itself.

## 8. Measuring Time-to-Ready from Outside the Process

Besides internal events, measure **from when the launcher begins creating the JVM until HTTP readiness actually succeeds**.

Bash example on Linux with **GNU date** (supporting `date +%s%3N`). Run only in a lab environment and ensure port 8080 is not occupied by another process:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

jar="build/libs/startup-measurement.jar"

start_ms=$(date +%s%3N)
java -jar "$jar" > startup-run.log 2>&1 &
pid=$!

trap 'kill -TERM "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true' EXIT

ready=0
for attempt in $(seq 1 300); do
    if curl --silent --fail --max-time 1 \
         http://127.0.0.1:8080/readyz >/dev/null 2>&1; then
        ready=1
        break
    fi

    if ! kill -0 "$pid" 2>/dev/null; then
        echo "JVM exited before readiness"
        exit 1
    fi

    sleep 0.1
done

if [ "$ready" -ne 1 ]; then
    echo "Readiness timeout"
    exit 1
fi

ready_ms=$(( $(date +%s%3N) - start_ms ))
echo "external_ready_ms=$ready_ms"

curl --silent --output /dev/null \
     --write-out 'first_http_total_s=%{time_total}\n' \
     http://127.0.0.1:8080/demo/use

curl --silent --output /dev/null \
     --write-out 'second_http_total_s=%{time_total}\n' \
     http://127.0.0.1:8080/demo/use
~~~

Save the example above as a script if you want to run multiple trials in the lab. Output looks like:

~~~text
external_ready_ms=...
first_http_total_s=...
second_http_total_s=...
~~~

The ellipses `...` here represent **variable timing values**, not fabricated benchmark figures. The script keeps the JVM alive until both results are collected, then sends TERM in the trap.

### Limitations of the Script

- `start_ms` is captured in the shell before the `java` command, so it measures **launch-to-readiness from outside the process**, which does not coincide identically with Spring Boot's internal clock.
- The `0.1s` poll interval, `curl` execution time, and OS scheduling introduce quantization error: readiness may have succeeded **before the probe returned**.
- `date +%s%3N` uses wall clock on GNU date, which can experience clock adjustments; a simple lab script is not a production-grade precision timing harness. For tighter benchmarks, use a monotonic clock and `ProcessBuilder` APIs in a dedicated harness.
- If an HTTP server already exists on port 8080, probes can read the wrong process. Use an isolated port/PID check and isolate the environment.
- Client `curl` total time includes TCP setup, networking, response serialization, and thread scheduling; it is an **external measurement point** with a different scope than `handlerMillis`.
- The script does not enforce universal timeout limits for heavily loaded hosts or OS schedulers; it is tuned for controlled illustration, not a thousand-iteration benchmark harness.
- Do not flush OS caches or alter kernel settings to "create a true cold start" on a shared machine without permission and a safe procedure.

## 9. Three Separate Experiments—Do Not Mix Results

### Experiment A — Fresh-Process Cold Startup

1. Build **one single JAR** and keep its SHA/version fixed.
2. Ensure no other app instance occupies the port.
3. Launch the JAR in a fresh JVM.
4. Measure `ApplicationStartedEvent`, `ApplicationReadyEvent`, external readiness, and the first request.
5. Stop the process and verify it exited.
6. Repeat multiple times, recording each run as a separate sample.

With the same JAR, if the first run is slow and later runs are faster, the cause can be OS file cache, warm external dependencies, or hardware state—**not the old JVM keeping JIT/heap** because each run is a brand-new process.

If a true "cold machine/container image" test is needed, use a dedicated test environment and measure image pull + container scheduling as a separate metric rather than folding them into Boot's numbers.

### Experiment B — Restart

Explicitly state the **restart type**:

**B1. Full JVM restart:** send TERM, wait for exit, run `java -jar` again. New JVM; heap/JIT/compiler state from the old JVM **is not preserved**. OS caches and external caches may still be warm.

**B2. DevTools restart:** in a development environment with `spring-boot-devtools`, modify the classpath and let DevTools create a new restart classloader/context **within the same JVM**. The base classloader may be retained, so duration is usually shorter than process cold startup.

**B3. Pod/container restart:** Kubernetes/container runtime starts a process/container per policy and may reuse image layers; scheduling, probes, volume mounts, DNS, and network routing also apply. Do not extrapolate DevTools restart times to represent production rolling restarts.

### Experiment C — First Use

1. Start the app until readiness succeeds.
2. **Do not call `/demo/use` prior to measurement.**
3. Call the endpoint once, measuring client total and server handler.
4. Call the same endpoint 10–30 more times, recording each latency.
5. Compare the first request with the warm-request distribution.
6. Launch a fresh JVM and repeat to collect **multiple first-use samples**, rather than relying on a single sample.

Avoid sneaky "warming" before the check: a synthetic monitor, custom readiness check, or browser tab might hit the business path before you. Then the "first request" in your log is no longer the bean's first use.

## 10. DevTools Restart: Two Classloaders and Miscomparison Risk

In development, Spring Boot DevTools uses:

- **Base classloader:** loads largely unchanging libraries/dependencies.
- **Restart classloader:** loads application code under active development and gets replaced on DevTools restart.

The restart process typically follows:

~~~text
Existing JVM
    |
    +-- Base classloader remains
    |
    +-- Old context and restart classloader are closed/discarded
    |
    +-- Create new restart classloader
    +-- Create new Spring ApplicationContext
    +-- Startup callbacks run again
~~~

This is usually faster than cold start because some classes do not need reloading. Yet it does not represent **JVM bootstrap**, OS image pulls, or real deployment latency. Furthermore, DevTools applies development-time defaults (e.g., disabling template caching) that can differ from production.

When designing a startup benchmark:

- **Never use DevTools restart time** to promise production container startup times.
- If measuring DevTools, measure **IDE change-to-ready** and **classloader/context restart** separately; do not call it a JVM cold start.
- DevTools is typically excluded from repackaged production JARs; do not try to enable DevTools in production to measure.
- If DevTools misbehaves by leaking references to old classloaders, that is a different lifecycle/resource-ownership bug; it can make later restarts progressively slower or grow heap/metaspace.

A valid outcome might be DevTools restart 0.8 seconds and fresh-process JVM startup 3.5 seconds. Both numbers here are **illustrative**, and the difference does not prove a performance bug.

## 11. Readiness, startupProbe, and Real Serving Capability

In Kubernetes, **readiness** controls whether a Pod should receive traffic from a Service; a **startup probe** sets aside a startup window so liveness/readiness checks do not intervene too early.

Measurement paths can differ:

- `/actuator/health/readiness`: readiness health group.
- `/readyz`: additional path on the **main HTTP port** when `management.endpoint.health.probes.add-additional-paths=true` is configured.
- Business endpoint: used to evaluate whether "the first request actually runs with acceptable latency".

**A Ready Pod does not guarantee everything is warm.** Readiness can be valid per the serving contract while the first request is still slow due to lazy initialization. If business SLAs require strict latency, consider a **controlled warm-up step**, weighing dependencies, timeouts, resources, and whether warm-up must run before readiness.

Example probe snippet inside a Pod/container:

~~~yaml
startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 5
  failureThreshold: 24

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  periodSeconds: 5
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 10
  failureThreshold: 3
~~~

This is only a **container YAML snippet**, not a complete Deployment manifest. Thresholds are examples, not universal standards. While the startup probe has not succeeded, kubelet delays liveness/readiness checks per Kubernetes rules. After startup passes, readiness determines whether the Pod gets traffic; do not wire external services into liveness just to stretch startup time.

## 12. Why Lazy Initialization Can Make Reports Look Better Yet Worsen SLAs

Consider two configurations:

~~~properties
# A: eager initialization per standard behavior
spring.main.lazy-initialization=false
~~~

~~~properties
# B: global lazy initialization
spring.main.lazy-initialization=true
~~~

Hypothetical measurements:

| Option | Ready time | First request | Subsequent warm requests |
|---|---:|---:|---:|
| A: Eager | 4.0 seconds | 90 ms | 65 ms |
| B: Lazy | 2.2 seconds | 1,900 ms | 65 ms |

**This is a hypothetical table illustrating trade-offs, not a real benchmark.** If first-request work is critical, option B can "win" on a startup chart while giving the first user a poor response.

Evaluation criteria should include:

1. Time-to-first-ready and time for the Pod to enter EndpointSlice.
2. First business request latency p50/p95/p99.
3. Warm steady-state throughput and latency.
4. Heap/RSS memory before and after first-use.
5. CPU spikes, GC/classloading/JIT impact.
6. Late-detected errors because beans were not instantiated during startup.
7. Request capacity immediately after Ready.
8. Autoscaling behavior during the initial traffic burst.

**Never trade away fail-fast validation just for prettier startup numbers.** Critical beans such as credential providers, mandatory config validators, or authorization subsystems may need validation before the instance accepts traffic.

## 13. Analyzing "Warm-Up" by Layer—Do Not Treat All Caches Alike

| Warmed layer | Example | Survives JVM restart? |
|---|---|---|
| Class loading and Java heap objects | Singleton beans, internal caches | **No**, if a new JVM |
| JIT compilation and JVM profile data | Hot methods after many invocations | **No by default across separate JVMs** |
| Spring DevTools base classloader | Loaded dependency classes | May be retained **in the same JVM** on DevTools restart |
| OS page cache | JAR/classes read from filesystem | May survive process restart |
| Container image layers/cache | Image already cached on node | May survive container restart/new Pod on same node |
| DNS caches | JVM/OS/service resolver | Depends on layer and TTL |
| Internal database connection pool | HikariCP connections | Old JVM's pool is lost when process exits |
| External database buffer cache | DB server already read data pages | Can survive application restart |
| CDN/distributed cache | Cached data outside the JVM | Can persist, subject to TTL/policy |

This table explains why **a brand-new JVM runs faster on the second launch**, even though no true "JVM warm restart" occurred: OS or external services may already be warm.

Conversely, a DevTools restart does not mean all application singletons stay alive; beans in the old ApplicationContext were destroyed and will be recreated in the new context.

## 14. Organizing a Reliable Benchmark

A startup benchmark does not need extreme complexity, yet must be well controlled:

**Hold variables constant**

- Same JDK vendor/version, JVM flags (heap, GC, CDS, JIT), and Java architecture.
- Same Spring Boot version, dependency graph, profile, and `application.properties`.
- Same JAR checksum, host/container resources, and actual CPU quota.
- Same network/dependency state, database schema, and connection pool config.
- Same launch method: `java -jar`, never mixing numbers from IDE, Gradle wrapper, and native image.
- Same instrumentation state: do not enable JFR for one variant and turn it off for the other.

**Repeat and analyze**

- Every cold start needs a **fresh JVM**; every first-use sample needs a genuine first request of a fresh process or properly reset state.
- Run warm-ups when measuring steady state, without pre-warming a scenario you label "cold".
- Gather multiple samples; report p50/p95, min/max, and standard deviation where meaningful. Do not cherry-pick the best run.
- Any exclusion of failed or timed-out runs must follow documented rules; never delete bad numbers to improve a chart.
- Record raw timestamps and measurement method so others can reproduce.
- When changing code, compare only under matching conditions with balanced test order to reduce OS cache bias.

### Example Result Table to Fill with Real Measurements

| Run | Run type | JVM ready (ms) | Spring Started (ms) | Spring Ready (ms) | First HTTP (ms) | Warm HTTP p50 (ms) |
|---|---|---:|---:|---:|---:|---:|
| 1 | Fresh JVM | ... | ... | ... | ... | ... |
| 2 | Fresh JVM | ... | ... | ... | ... | ... |
| 3 | DevTools restart | N/A under same definition | ... | ... | ... | ... |

Ellipses `...` are **placeholder cells awaiting data**, not an actual benchmark. When measuring DevTools restart in the same JVM, the "JVM ready" column defined as *launcher creates a new JVM* does not have the same meaning; do not fill in a number for a false comparison.

### Charts and Decisions

Never optimize a single metric in isolation. For instance, if startup drops 20% while first-use grows 5x and readiness immediately admits traffic, weigh customer latency requirements. If deployment rollouts finish faster yet produce error bursts in the first second, also measure **time-to-capacity**: how long until the Pod serves target request throughput at an acceptable error rate.

## 15. Pinpointing Causes When Cold Start Is Slow

After measuring the timeline, find the time-consuming phase and form hypotheses:

| Symptom | Potential cause | How to verify |
|---|---|---|
| JVM launch → SpringStarted is long | Classpath scanning, bean creation, config binding, web server startup | BufferingApplicationStartup, JFR, heap/CPU |
| Started → Ready is long | ApplicationRunner, CommandLineRunner, ready listeners | Event durations and per-runner logs |
| Ready event fast yet readiness probe late | Probe period, platform scheduling, server reachability, readiness group | Timestamps of Pod/probe/HTTP and kubelet |
| Ready fast yet first request slow | Lazy beans, servlet init, serialization, DNS/TLS, DB pool/caches | Trace first request, compare with warm request |
| DevTools restart slows down each cycle | Classloader leak, unmanaged threads, cache accumulation | Classloader stats, heap dump, thread count |
| Second JVM restart is faster | OS page cache or warm external dependencies | Reset lab environment, inspect I/O and caches |
| Container "start" drags before Java logs appear | Image pull, scheduling, volume mount, initContainers | Kubernetes Pod events and node/container metrics |
| First request times out yet later requests succeed | Init work pushed to request, slow dependency, or resource contention | Trace CPU/GC/DB, timeouts, startup warming |

Change **one hypothesis at a time** and verify before/after results. Randomly disabling auto-configuration, making all beans lazy, or boosting CPU without measuring root causes often makes apps buggier without reliably improving real experience.

## 16. Spring Boot Startup Time Differs from Pod Startup Time

In Kubernetes, a Pod can spend time across multiple layers:

~~~text
Deployment creates Pod spec
  |
  +-- scheduling waits for node/resources
  +-- image download if node lacks it
  +-- create sandbox/network/mounts/initContainers
  +-- container JVM starts
  +-- SpringApplication startup
  +-- readiness probe succeeds
  +-- EndpointSlice / routing updates
  +-- business request arrives
  +-- first use may require warm-up
~~~

If an SLA states "from scale-out request until added capacity is available", measuring only `ApplicationReadyEvent.getTimeTaken()` is insufficient. It omits scheduling/image/network and router adoption of the new Pod.

Data to combine:

- Kubernetes Pod scheduling/conditions/events and image pull.
- Container start timestamp.
- Spring `ApplicationStartedEvent`/`ApplicationReadyEvent`.
- Readiness probe status and when Service/gateway can route.
- First useful request outcome (success, latency, error rate).
- Load tests when many Pods cold-start together, spiking load on databases/secret managers.

In particular, a Pod Ready in 2 seconds that cannot withstand a traffic burst 20 seconds later has not truly achieved a **2-second time-to-capacity**.

## 17. Common Mistakes

**Mistake 1 — "Every fresh JAR execution is a cold machine start."** False. A new JVM can benefit from a warm OS page cache.

**Mistake 2 — "DevTools restarts by launching a new JVM."** False. DevTools uses classloader/context restart inside the same JVM.

**Mistake 3 — "ApplicationStartedEvent means runners finished."** Wrong. Started is published **before** ApplicationRunner/CommandLineRunner.

**Mistake 4 — "ApplicationReadyEvent means the first request has completed."** Wrong. Ready is a startup milestone; first-use may not have happened yet.

**Mistake 5 — "Enabling spring.main.lazy-initialization=true always improves performance."** False. It can move bean init time to the first request and delay configuration errors.

**Mistake 6 — "Exposing /actuator/startup alone produces a timeline."** False. An appropriate `BufferingApplicationStartup` is required before `run(args)`.

**Mistake 7 — "POST /actuator/startup is the same as GET."** False. POST drains the buffer; GET is a snapshot.

**Mistake 8 — "Summing durations of all StartupSteps equals startup time."** Wrong. Steps nest/overlap; analyze relationships instead of blindly summing.

**Mistake 9 — "Running JFR after Ready captures all startup CPU/GC."** False. Events before recording began were never collected.

**Mistake 10 — "A successful health check means all beans and databases are warm."** False. The readiness health group does not test every business path.

**Mistake 11 — "The first curl was fast on my laptop so all clients will be fast."** False. DNS, TLS, network, CPU quota, caches, and workloads differ.

**Mistake 12 — "Spring startup time equals image pull + scheduler time."** False. Layers have distinct clocks and scopes.

**Mistake 13 — "One measurement sample suffices for production decisions."** False. Noise comes from GC/JIT/OS/page cache/network and scheduling.

**Mistake 14 — "Warming up with real requests is always harmless."** False. If a route has side effects, warm-up can write data, send messages, or charge fees. Warm only with safe/idempotent, bounded operations.

**Mistake 15 — "First-use happens only once in a cluster."** False. Each JVM/instance can hit its own cold path; during scale-out, many Pods may warm simultaneously.

## 18. Practical Exercises

1. Run the project in section 7, recording `EVENT_STARTED` and `EVENT_READY` along with their Durations.
2. Check `GET /actuator/startup` for the timeline; identify at least three `StartupStep` entries with names/tags and parent-child relationships.
3. Call `/readyz` successfully first, then call `/demo/use`. Observe `CATALOG_INITIALIZED` appearing when the first request executes.
4. Call `/demo/use` 10 times and compare `handlerMillis` of the first call vs. later calls. Explain why the two calls might not differ by exactly 300ms.
5. Launch a **fresh JVM** with the same JAR and repeat. Does the first call of the **new process** trigger the lazy bean again?
6. Run the external measurement script and compare `external_ready_ms` with `ApplicationReadyEvent.getTimeTaken()`. List what each figure includes/excludes.
7. Enable `spring.main.lazy-initialization=true` and re-measure. What got faster, and what might get slower?
8. Replace `@Lazy` on `SlowCatalog` with eager init while holding other conditions constant. Observe whether `CATALOG_INITIALIZED` moves into startup.
9. In a separate development project, install DevTools, modify the classpath, and measure restart time; explain how it differs from a JVM restart.
10. Capture JFR from before Java `main` startup, inspect class loading/GC/events, and compare against Spring's timeline.
11. Have a monitor call `/demo/use` before you and explain why a subsequent "first request" measurement is no longer valid.
12. Build a table of 10–20 fresh JVM samples, reporting median and p95 alongside JDK/CPU/JAR/version; do not fabricate measurements.

## 19. Checklist Before Optimizing Startup Time

- **Scenario name:** fresh JVM, cold container/node, JVM restart, DevTools restart, or first-use?
- **Milestone:** launch, started event, ready event, readiness probe, first useful response?
- **Clock:** `System.nanoTime` inside JVM or external monotonic clock; how large is polling uncertainty?
- **Resources:** are CPU quota, heap, GC, I/O, network, DB warm state, and host caches held constant?
- **Build:** same JAR, JDK, profiles, dependency versions, and JVM flags?
- **Tooling:** are `BufferingApplicationStartup`/JFR/Actuator enabled consistently?
- **Readiness:** does it reflect true serving capability, not just an overly lightweight health endpoint?
- **First-use:** are there lazy beans, serializers, TLS, JIT, connection pools, or caches initializing late?
- **Reliability:** multiple runs, p50/p95, raw samples, no cherry-picking?
- **Trade-offs:** does faster startup slow down/time out the first request or delay catching configuration errors?
- **Operations:** during autoscaling/rolling deploys, did time-to-capacity and dependency load actually improve?
- **Security:** avoid exposing sensitive startup details/JFR/Actuator publicly; store profiling files securely?

### Official Documentation

- Spring Boot 3.3 — SpringApplication, *Application Startup Tracking* and *Lazy Initialization*: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Application Startup REST endpoint (GET snapshot / POST drain): https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html
- Spring Boot 3.3 — Actuator endpoints/exposure/security: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Developer Tools, *Restart vs Reload*: https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html
- Spring Boot 3.3 — ApplicationReadyEvent Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Boot 3.3 — ApplicationStartedEvent Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html
- Spring Framework 6.1 — ApplicationStartup / StartupStep: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Kubernetes — Pod Lifecycle and probes: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Oracle JDK 17 — Java Flight Recorder: https://docs.oracle.com/en/java/javase/17/jfapi/

**Conclusion:** Effective startup measurement must separate **JVM/process cold start**, **the true restart type**, and **first-use after Ready**. Use `ApplicationStartedEvent`/`ApplicationReadyEvent` for Boot milestones, `BufferingApplicationStartup`/Actuator and JFR to locate slow phases, measure readiness from outside the process, and measure **the first business request** as a separate metric. Consider an optimization successful only when it improves **time-to-ready, time-to-useful-response, and serving capability under load**, not merely by shrinking the "Started in ... seconds" log line.
