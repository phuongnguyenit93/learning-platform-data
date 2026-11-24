# Diagnosing Missing Metrics Caused by Unexecuted Measurements or Missing Binders

## 1. A Missing Metric and a Zero-Valued Metric Are Two Different Situations

When you look for a metric in Actuator and do not see it, do not start by flooding the app with requests or adding arbitrary dependencies. First determine: has the meter been registered, has the instrumented code path run, and does the component registering the measurements exist in the application?

In Micrometer, a meter is the measurement instrument, such as a `Counter`, `Timer`, or `Gauge`; a metric is the measurement data exposed from that meter. A meter is identified by its name and tag set. The same name can have multiple tag sets and correspondingly multiple time series. [Micrometer meter concepts](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).

| Observation | What you can conclude | What you cannot yet conclude |
| --- | --- | --- |
| Name appears in `/actuator/metrics`, COUNT=0 | A matching meter exists and its current value is 0 | Cannot claim the meter is unregistered |
| Name is absent, querying it directly returns 404 | No matching meter was found in the registry observed by the endpoint, assuming the endpoint URL is right | Cannot yet determine if it is due to no activity, a missing binder, or filtering |
| Name exists, yet querying with a tag returns 404 | That name exists, though the requested tag set may not | Does not prove the entire metric has disappeared |
| Actuator has data, yet external monitoring does not | Creation and registration work at least in the inspected registry | Does not prove external export, scraping, and queries are right |

The goal of this lesson is to produce evidence distinguishing activity-driven lazy registration from a missing measurement binder, and then inspect causes easily confused with those two cases. Examples run with Spring Boot 3.3.13 and Java 21.

## 2. Tracing the Path of a Measurement

```text
Source to observe: request, connection pool, queue, JVM...
  -> instrumentation / MeterBinder / observation handler
  -> register meter via MeterFilter: accept, deny, or rename/retag
  -> record or read meter value in MeterRegistry
  -> Actuator metrics exposes currently available data
  -> registry exports data to monitoring system if configured
```

This is a responsibility model for narrowing scope, not a claim that every measurement must pass through a class named MeterBinder. Some measurements register directly in code, some are created by framework integrations when an operation completes, and some meter sets are bound by a binder at startup.

`MeterRegistry` holds meters. A `MeterBinder` registers one or more meters into a registry via `bindTo`. Under normal Spring Boot configuration, `MeterBinder` beans are automatically bound to the Spring-managed registry. Simply having a binder class on the classpath, or instantiating one with `new` without binding it, does not guarantee meters exist. [Registering custom metrics and MeterBinder in Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.registering-custom).

Exposing the metrics endpoint only opens HTTP read access. It does not generate business measurements, invoke every method in the application, create a missing connection pool, or activate every optional binder.

## 3. First Case: The Meter Is Created Only When the Execution Path Runs

### 3.1. Eager Registration vs. On-Demand Registration

The two snippets below illustrate two different registration times. They assume `registry` is a Spring-injected `MeterRegistry`; these are illustrative snippets, not two standalone programs.

Registering immediately when initializing a component:

```java
Counter counter = Counter.builder("lab.registered").register(registry);
```

The counter already exists even before `increment` is called; its initial value can be 0. There is no need to emit a fake event just to make the meter name appear.

Registering inside an execution path:

```java
Timer timer = registry.timer("lab.work.duration", "operation", "compute");
int result = timer.record(() -> 42);
```

If this snippet only lives inside the `/work` handler, nothing requests registering `lab.work.duration` before the first call. The first call both registers the timer and records one run. `Timer` measures event count and total time; actual durations depend on runtime execution, so do not hardcode a specific timing number in tests. [Timer in Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html).

### 3.2. Activity Must Pass Through the Exact Instrumented Spot

Not every request makes every metric appear:

- Outbound HTTP call metrics require the client to actually execute calls through the matching observation integration; sending HTTP requests into the application does not substitute for that.
- Method-level metrics require the method to be invoked through the active instrumentation mechanism.
- Metrics for a particular tag set only appear when the branch producing that tag set executes.
- Measurements recorded upon completion may not appear while a request or job is still in flight.

For example, if waiting for `http.server.requests`, send a request into the application, wait for it to finish, and then read again. Calling the Actuator endpoint itself can also generate HTTP measurements, so the list fetched before and after an HTTP GET to metrics can differ. When you want unambiguous evidence of a cause, use a dedicated metric name for your test action rather than inferring from any change in the list.

Do not assume putting `@Timed` on an arbitrary method is enough in every application. Verify the annotation processor, aspect/proxy, and actual call path. The hands-on example below uses `Timer.record` directly to show registration and recording timing clearly.

### 3.3. A Controlled Test

1. Record the metric names list and query result before the action.
2. Perform exactly one action capable of reaching the instrumented code.
3. Wait for the action to finish, then read again on the same instance and same tag set.
4. Repeat once to verify COUNT increases as expected.

If the name appears and COUNT increments with the action, you have evidence of activity-triggered registration. If it is still absent, verify whether the code path was actually reached before moving on to binders, filters, and registries.

Do not call `registry.timer(name)` just to "check if the timer exists": that method can create the timer and alter what you are investigating. Use a search API such as `registry.find(name).timer()` or the metrics endpoint; with the search API, a null result means no matching timer was found.

## 4. Second Case: The Meter-Producing Component Is Not Bound

A binder typically registers a group of measurements for a specific source. If the binder does not exist or the source it monitors does not exist yet, sending more traffic to unrelated endpoints will not fix it.

Check across these layers:

| Layer | Question to verify | Suitable evidence |
| --- | --- | --- |
| Runtime library | Is the artifact providing the integration actually present at runtime? | Dependency graph and actual packaged app |
| Source object | Has the pool, cache, client, or observed object been created? | Running bean/object, not merely a config file entry |
| Auto-configuration conditions | Do classes, beans, properties, and profiles satisfy conditions? | Auto-configuration conditions report, startup logs, or context inspection |
| Binder | Does the appropriate binder bean or equivalent integration exist? | Actual bean and bean creation config |
| Binding to registry | Was the binder bound to the right registry? | `bindTo` call site or registry auto-configuration flow |
| Meter accepted | Do filters allow registering that name? | Effective enablement config and active MeterFilters |

Not every library provides measurements via the same MeterBinder bean pattern; some integrations use listeners, observations, or client customizers. Look up the mechanism matching the exact library and version in use.

Practical condition examples in Spring Boot 3.3:

- Tomcat metrics depend on Tomcat's MBean registry being enabled; do not assume embedded Tomcat guarantees every `tomcat.*` name exists.
- Caches created after the binding phase may need explicit registration; the cache library's statistics setting can also be a condition.
- HTTP client metrics require using a client/builder with matching observation integration; a manually instantiated client outside that flow may go unmeasured.

Add a dependency only after identifying which artifact is missing and why it is needed at runtime. Do not mix arbitrary Micrometer versions by trial and error; keep version management aligned with your project's Spring Boot version.

## 5. Causes That Look Like a Missing Binder

### 5.1. Meter Rejected by a Filter

A `MeterFilter` can deny registration, rename meters, or alter tags. When denied, the registration call may receive a non-recording (NOOP) meter; business code still runs, so a handler returning 200 does not prove a measurement was stored. [Micrometer 1.13 Meter filters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

Example Spring Boot configuration blocking meters whose names start with this prefix:

```properties
management.metrics.enable.lab.queue.depth=false
```

Also check broader settings like `management.metrics.enable.all=false`, prefix rules, and custom `MeterFilter` beans. Use values effective in the running profile and instance. If you just edited config during diagnosis, verify the application applied it; do not assume every filter updates dynamically or replays historical data.

A binder can exist and call register, yet the meter still is not retained because of a filter. This is a different root cause from a missing binder.

### 5.2. Recording into a Different Registry

Prefer injecting the Spring-managed registry. If a component creates `new SimpleMeterRegistry()` on its own and records only into it, the application's Actuator endpoint will not automatically look in that private registry.

Similarly, if using static APIs on `Metrics`, understand the relationship between the global registry and the application's registry, especially if `management.metrics.use-global-registry` was changed. Do not conclude from identical registry class names that two components share the same instance.

During investigation, inspect the registry injected at the recording site and the registry used by the endpoint/exporter. With a composite registry, inspect child registries as well; a missing target registry also differs from a missing binder.

### 5.3. Wrong Name or Wrong Tag Set

Read `/actuator/metrics` to get actual names and query those names. Actuator's endpoint uses meter names from code, not names normalized by an exporter for another backend.

Names exported to Prometheus can convert dots and append unit or statistic suffixes. Do not copy a Prometheus time series name into Actuator's selector and conclude the metric is missing.

Query before filtering tags, then add tags one by one from `availableTags`. Example:

```shell
curl -i http://127.0.0.1:8080/actuator/metrics/lab.work.duration
curl -i "http://127.0.0.1:8080/actuator/metrics/lab.work.duration?tag=operation:compute"
```

In version 3.3.13, the endpoint returns no result when no meter matches the name and tags; measurements sharing a name can be aggregated across multiple tag sets. A higher-than-expected COUNT may come from viewing multiple series combined, not necessarily from repeated handler execution. [Lookup and aggregation in MetricsEndpoint](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/metrics/MetricsEndpoint.java).

### 5.4. Gauge Lacks a Valid Value or Source Object Was Garbage-Collected

A gauge samples its current value when observed, requiring no business request to increment a counter. The state object observed by a gauge must retain a strong reference in an appropriate place. If the object is reclaimed by the garbage collector, depending on the registry you may see NaN or missing data. That situation should not be "fixed" by sending more requests. [Gauge lifecycle in Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html).

A gauge value of 0 can also be a valid result, such as an empty queue. Evaluate the measurement's meaning instead of treating every zero as a bug.

### 5.5. Data Exists in the App, Yet Has Not Reached the Monitoring System

If Actuator already shows the meter and expected values, move on to checking the exporting registry, exporter config, collection pipeline, export/scrape intervals, target labels, and the monitoring system's query time range.

Do not keep waiting on an export cycle to explain why a meter is absent from the local registry. Likewise, do not add another binder just because a dashboard is empty when Actuator already confirms the meter exists.

## 6. Standalone Lab with Three Registration Patterns

The lab uses three dedicated names to avoid confusion with HTTP metrics generated by the verification commands themselves:

| Name | Where registered | Before calling /work |
| --- | --- | --- |
| `lab.registered` | Counter bean registered at startup | Present, COUNT=0 |
| `lab.work.duration` | Inside the /work handler | Absent |
| `lab.queue.depth` | Conditional MeterBinder | Present only when binder is enabled and meter is not filtered |

The binder uses a gauge with a simulated value of 7; this is not a real queue. The /work handler returns 42 and is used to verify the timer. It uses GET because it is only an illustrative computation and makes no business state changes.

### 6.1. Creating the Project

Use JDK 21, Maven 3.6.3 or later, and Python 3. Connectivity to Maven repositories is required if dependencies are not cached.

```text
metrics-diagnosis-lab/
├── pom.xml
├── verify.py
└── src/main/
    ├── java/example/metrics/MetricsDiagnosisLab.java
    └── resources/application.properties
```

File pom.xml:

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
    <groupId>example</groupId>
    <artifactId>metrics-diagnosis-lab</artifactId>
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

File src/main/resources/application.properties:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,metrics
lab.binder-enabled=false
```

The example listens only on loopback for local practice and omits Spring Security dependencies. When applying this in a real service, preserve the service's authentication/authorization policy; do not expose metrics publicly just for diagnostic convenience.

File src/main/java/example/metrics/MetricsDiagnosisLab.java:

```java
package example.metrics;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MetricsDiagnosisLab {
    public static void main(String[] args) {
        SpringApplication.run(MetricsDiagnosisLab.class, args);
    }

    @Bean
    Counter registeredCounter(MeterRegistry registry) {
        return Counter.builder("lab.registered")
            .description("Registered without increments")
            .register(registry);
    }

    @Bean
    @ConditionalOnProperty(name = "lab.binder-enabled", havingValue = "true")
    MeterBinder queueDepthBinder() {
        return new QueueDepthBinder();
    }

    static final class QueueDepthBinder implements MeterBinder {
        private final AtomicInteger depth = new AtomicInteger(7);

        @Override
        public void bindTo(MeterRegistry registry) {
            Gauge.builder("lab.queue.depth", depth, AtomicInteger::get)
                .description("Simulated queue depth")
                .register(registry);
        }
    }

    @RestController
    static class WorkController {
        private final MeterRegistry registry;

        WorkController(MeterRegistry registry) {
            this.registry = registry;
        }

        @GetMapping("/work")
        public Map<String, Integer> work() {
            Timer timer = registry.timer("lab.work.duration", "operation", "compute");
            int result = timer.record(() -> 42);
            return Map.of("result", result);
        }
    }
}
```

`QueueDepthBinder` holds `depth` in a bean field, so the source object keeps a strong reference as long as the binder lives. Spring Boot calls bindTo during binder binding; the /work handler does not call the binder or create the gauge on the binder's behalf.

### 6.2. Build and Start

Run from the project root directory:

```shell
mvn package
java -jar target/metrics-diagnosis-lab-1.0.0.jar
```

This project has Spring Boot dependencies; running `javac` on a single file will not provide the full classpath. Keep the application running and open a second terminal in the same directory. Verify port 8080 belongs to this application.

### 6.3. Verifying with the Python Standard Library

The file verify.py takes two options to check whether the gauge and timer are exposed. Each run of the script needs a fresh application process that has not had /work called yet, because the script intentionally checks state before the first write.

```python
import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8080"


def read_json(path):
    request = Request(BASE + path, headers={"Accept": "application/json"})
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read()
        return response.code, json.loads(raw) if raw else None


def metric(name):
    return read_json("/actuator/metrics/" + name)


def statistic(body, name):
    matches = [item["value"] for item in body["measurements"]
               if item["statistic"] == name]
    assert len(matches) == 1, body
    return matches[0]


def gauge(stage, present):
    code, body = metric("lab.queue.depth")
    if present:
        assert code == 200 and statistic(body, "VALUE") == 7, (code, body)
        print(f"gauge {stage}: VALUE=7")
    else:
        assert code == 404, (code, body)
        print(f"gauge {stage}: HTTP=404")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gauge", choices=["present", "absent"], default="absent")
    parser.add_argument("--timer", choices=["present", "absent"], default="present")
    args = parser.parse_args()
    gauge_present = args.gauge == "present"
    timer_present = args.timer == "present"

    code, body = metric("lab.registered")
    assert code == 200 and statistic(body, "COUNT") == 0, (code, body)
    print("registered counter: COUNT=0")

    code, body = metric("lab.work.duration")
    assert code == 404, (code, body)
    print("timer before work: HTTP=404")
    gauge("before work", gauge_present)

    for _ in range(2):
        code, body = read_json("/work")
        assert code == 200 and body == {"result": 42}, (code, body)
    print("work: result=42, calls=2")

    code, body = metric("lab.work.duration")
    if timer_present:
        assert code == 200 and statistic(body, "COUNT") == 2, (code, body)
        assert statistic(body, "TOTAL_TIME") >= 0, body
        code, filtered = read_json(
            "/actuator/metrics/lab.work.duration?tag=operation:compute")
        assert code == 200 and statistic(filtered, "COUNT") == 2, (code, filtered)
        print("timer after work: COUNT=2")
    else:
        assert code == 404, (code, body)
        print("timer after work: HTTP=404")

    code, body = read_json(
        "/actuator/metrics/lab.work.duration?tag=operation:other")
    assert code == 404, (code, body)
    print("unmatched tag: HTTP=404")
    gauge("after work", gauge_present)

    code, body = read_json("/actuator/metrics")
    assert code == 200, (code, body)
    names = set(body["names"])
    assert "lab.registered" in names, names
    assert ("lab.work.duration" in names) == timer_present, names
    assert ("lab.queue.depth" in names) == gauge_present, names


if __name__ == "__main__":
    main()
```

With the initial configuration, run:

```shell
python verify.py
```

Exact stdout:

```text
registered counter: COUNT=0
timer before work: HTTP=404
gauge before work: HTTP=404
work: result=42, calls=2
timer after work: COUNT=2
unmatched tag: HTTP=404
gauge after work: HTTP=404
```

The results show three distinct situations: the counter is registered yet has recorded no events; the timer appears after the execution path is called; the gauge stays missing because the binder is disabled. Two /work requests cannot create a gauge whose binder was not registered.

The script does not assert fixed TOTAL_TIME or MAX values because they depend on runtime duration and registry implementation. It checks COUNT, business result, HTTP status, and the names list to confirm the exact lessons intended.

### 6.4. Enabling the Binder and Observing Before Activity Occurs

Stop the app with Ctrl+C and start a new process:

```shell
java -jar target/metrics-diagnosis-lab-1.0.0.jar --lab.binder-enabled=true
```

In the second terminal:

```shell
python verify.py --gauge present
```

Stdout:

```text
registered counter: COUNT=0
timer before work: HTTP=404
gauge before work: VALUE=7
work: result=42, calls=2
timer after work: COUNT=2
unmatched tag: HTTP=404
gauge after work: VALUE=7
```

The gauge already exists before calling /work because the binder was created and bound at initialization. The requirement here was the binder, not traffic to /work.

### 6.5. Binder Present, Yet the Gauge Is Filtered Out

Stop the previous process, then run:

```shell
java -jar target/metrics-diagnosis-lab-1.0.0.jar --lab.binder-enabled=true --management.metrics.enable.lab.queue.depth=false
```

Verify:

```shell
python verify.py --gauge absent
```

The gauge is absent again even though the binder creation condition is enabled. The timer still appears and COUNT increments after /work. Do not add a second binder to fix this case; inspect the filter blocking that exact gauge name.

### 6.6. Handler Works Fine, Yet the Timer Records No Data

Stop the previous process, then run:

```shell
java -jar target/metrics-diagnosis-lab-1.0.0.jar --lab.binder-enabled=true --management.metrics.enable.lab.work.duration=false
```

Verify:

```shell
python verify.py --gauge present --timer absent
```

The handler still returns 42 on both calls and the gauge still has VALUE=7, yet the timer does not appear after the activity. A filter blocking a measurement does not mean it blocks executing the `Timer.record` callback.

In an environment with active filters, this is why you must verify both business results and measurement data rather than inferring "the request succeeded, so the timer must have incremented."

## 7. Procedure Applied to Real Incidents

### Step 1: Confirm the Endpoint Before Investigating One Metric Name

Verify `/actuator/metrics` works on the right management port/base path and that the caller has read permissions. 401/403 is an access issue to solve first; a 404 on the whole endpoint does not mean an individual metric has not been created.

Keep exposure small per service policy. There is no need to expose `*` just to read metrics. The metrics endpoint is for diagnostics, not historical storage or scraping by monitoring systems in place of a dedicated exporter. [Metrics endpoint contract](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

### Step 2: Confirm Exact Name, Instance, and Tag Set

Save the names list, read the metric unfiltered first, and then add tags. If requests pass through a load balancer, ensure the test action and the metric read hit the same instance or understand how upstream aggregation works.

Local in-memory data can be lost on process restarts. A name that appeared on an old instance does not prove a new instance has created the same meter.

### Step 3: Identify Who Is Responsible for Registration

Locate where builder/register, `registry.counter`, `registry.timer`, binder, listener, or observation handler is called. Determine whether that code runs at startup or when activity occurs.

If no mechanism registers the expected business metric, waiting longer will not create it. Add purposeful instrumentation with stable names and tags rather than assuming Actuator automatically understands every business operation.

### Step 4: Trigger One Representative Operation

Pick an action whose side effects fit the investigation environment. In production systems, do not create orders, send emails, or write real data just to see a counter. Use a staging environment or an approved operation.

Confirm the instrumented handler/method/client actually ran and finished. Re-read the metric and check COUNT or VALUE according to meter type; do not expect COUNT to increment on a gauge.

### Step 5: Check Binders and Conditions

If still absent, check runtime dependencies, the observed source, binder/integration beans, properties, and profiles. You can inspect the auto-configuration conditions report or context in development. Do not expose beans/conditions publicly just for convenience.

If the source is created dynamically after startup, check whether the integration tracks new sources automatically or requires explicit binding. Avoid duplicate registrations that emit warnings or retaining references to out-of-scope sources.

### Step 6: Rule Out Filters and Registries

Check enablement config, MeterFilter beans, and the registry actually receiving data. When setting breakpoints or diagnostic logs, use lookup APIs instead of APIs that have the side effect of registering a new meter.

Also check warnings for duplicate IDs, mismatched meter types, or tag changes after filters. Keep tag sets bounded; do not use requestId, userId, or URLs containing raw IDs as tags just for "easy search," as that creates excessive time series.

### Step 7: Only Then Inspect the External Export Path

If the registry/Actuator already has accurate data, inspect the exporter, export/scrape schedule, and backend queries. If there is no local data yet, return to the measurement creation point; editing dashboards cannot solve an unregistered meter.

## 8. Conclusions to Avoid

| Hasty conclusion | Why it is insufficient | Better verification |
| --- | --- | --- |
| No requests yet, so all metrics are absent | Many meters register at startup | Check where the meter is registered and whether 0 is valid |
| Sending many requests will surely create the metric | A binder may be missing or requests miss the measured source | Trigger one exact action and verify the code path |
| Dependency present means binder is active | Bean/property/runtime conditions and registry binding still matter | Confirm the integration is active in the running app |
| Binder exists, so the metric must exist | A filter may deny it; binder may bind to the wrong registry | Check active filters and target registry |
| COUNT=0 means the metric is missing | The meter exists, just with zero recorded events or a valid 0 | Distinguish existence from value |
| Gauge NaN means the API has not been called | Source object may be GC'd or value is invalid | Check source lifecycle and value supplier |
| Empty dashboard means Actuator created no metrics | Pipeline may break at export or query | Cross-check registry, Actuator, then backend layer by layer |

## 9. Self-Check Exercises

1. A Counter was registered at startup and never incremented. Must it be absent from the metrics list?
2. A Timer sits inside the /work handler and the handler has never been called. What should you check before adding dependencies?
3. A Gauge lives only inside a binder disabled by a property condition. Will calling /work 100 more times fix it?
4. Binder enabled, handler ran, yet the meter name is still absent. Which two layers should you check right next?
5. Querying without tags returns data, adding tag operation:other gives 404. Can you conclude the binder disappeared?
6. How can calling registry.timer(name) in a debugger while searching for a meter skew the investigation?

Reference guide: question 1 a counter can exist with COUNT=0; question 2 check the execution path and registration timing; question 3 no, binder creation/binding conditions must be met; question 4 filters and registry, plus confirming the binder actually bound; question 5 no, it may just be the wrong tag set; question 6 a lookup assumed to be read-only can register a new timer.

A diagnostic result should identify who creates the meter, when it is created, which action records data, which registry receives it, which filters apply, and which test confirms the cause. That evidence lets you fix the exact missing condition instead of making a metric appear via an accidental change.
