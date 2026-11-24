# Reading Tomcat Metrics and Activation Conditions for Related Indicators

A Servlet application can still serve HTTP normally without displaying Tomcat thread and connector metrics. Conversely, seeing a few session metrics does not prove every Tomcat metrics group has been fully activated.

To read accurately, you need to know which resources Tomcat holds, where measurements pull their data, and which conditions the application has satisfied. This lesson explains behavior according to Spring Boot 3.3.0, Micrometer 1.13.0, and embedded Tomcat 10.1.24, with a Java 17 example runnable on JDK 21.

## 1. What Questions Do Tomcat Metrics Answer?

In a Spring MVC application using embedded Tomcat, Tomcat accepts connections, dispatches requests to servlets, and manages Servlet container resources. Metrics help observe those resources, such as connection counts, busy workers, and active sessions.

Distinguish four concepts before reading numbers:

| Concept | Role | Why Not Count Them Interchangeably? |
| --- | --- | --- |
| Connection | Communication channel between client and server | One keep-alive connection can serve many requests; HTTP/2 also multiplexes request streams on one connection |
| HTTP request | A single HTTP interaction | Request count is neither connection count nor user count |
| Worker thread | Thread executing handler work | An open connection does not mean it continuously occupies a dedicated busy worker |
| HTTP session | Session state managed by the application/container | One session can span many requests and connections; an app without sessions still serves traffic |

Therefore, `connections.current=100` does not mean 100 requests are currently executing, and `sessions.active.current=10` does not mean exactly 10 people are using the application at that second.

### Observation Data Flow

```text
Actually running Tomcat instance
    -> state of Manager and related MBeans
    -> Micrometer Tomcat meter binders
    -> MeterRegistry
    -> Actuator inspection endpoint or data exporter
```

MBeans are managed objects in the JMX infrastructure. Internal MBeans can expose information about connectors, thread pools, and request processors. Registering them is a separate layer from exposing an HTTP endpoint to read metrics.

## 2. Conditions to Check Layer by Layer

| Condition Layer | What to Confirm |
| --- | --- |
| Server and app type | The app is actually running with Tomcat, not merely carrying a config file containing `tomcat` |
| Libraries and auto-config | Actuator/Micrometer, a registry, and matching Tomcat integration are present |
| Tomcat management source | MBean registry is enabled for groups read from MBeans |
| Lifecycle | Tomcat and related components have been initialized |
| Meter filters | No configuration or filter blocks the names you want to read |
| Access method | To read over HTTP, the `metrics` endpoint must be exposed and accessible |

A correct setting at the final layer does not fix a missing condition in an earlier layer. Opening `/actuator/metrics` does not create Tomcat MBeans; enabling the MBean registry does not automatically expose the HTTP endpoint.

### 2.1. Confirm the Server Actually in Use

The standard starter web in the example uses embedded Tomcat. However, a project may have swapped servers, used another application type, or deployed with external container configuration.

A WebFlux application using Reactor Netty does not have Tomcat resources like this Servlet model. Setting `server.tomcat.mbeanregistry.enabled=true` does not turn Netty into Tomcat.

For applications deployed to an external Tomcat, MBean management and container lifecycle also belong to the deployment environment. Do not assume an embedded Tomcat property will configure an entire external container.

### 2.2. MBean Registry Condition

Spring Boot 3.3 documents enabling Tomcat instrumentation via the MBean registry. The property to watch is:

```yaml
server:
  tomcat:
    mbeanregistry:
      enabled: true
```

The default value of this property is `false`. [Tomcat metrics in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html), [configuration properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

`spring.jmx.enabled` and `server.tomcat.mbeanregistry.enabled` have different responsibilities; do not substitute one property name for the other. For Micrometer to read internal MBeans via this integration, you do not need to open a remote JMX port for external hosts.

### 2.3. Checking Against Version Implementation Details

Documentation descriptions of the MBean registry should not be turned into an assumption that every `tomcat.*` name must disappear when the property is off.

Experiments with Boot 3.3.0 and Micrometer 1.13.0 confirm:

- When MBean registry is enabled, thread, connection, and global request groups from connectors are present.
- When disabled, these connector groups do not appear in the lab configuration.
- The session group still appears, and created session count still increases when the app actively creates sessions.

The reason is that this version's binder can read session metrics directly from `Manager`, whereas other groups look up data via MBeans. That is a distinction by data source, not a contradiction between Tomcat running and HTTP working.

When checking another version or deployment style, verify each group actually present in the registry. Do not use the presence of a session name to prove the connector group is ready.

## 3. Identifying the Metric Groups

The names below appeared in the lesson's experiment. Actual lists also depend on versions, Tomcat components, and active configuration.

### 3.1. Threads and Connections

| Meter | Conceptual Reading | What to Keep in Mind When Interpreting |
| --- | --- | --- |
| `tomcat.threads.current` | Current thread count reported by the management source | Not the busy thread count |
| `tomcat.threads.busy` | Busy thread count per measurement source | Point-in-time state; can miss brief bursts |
| `tomcat.threads.config.max` | Max threads provided by the connector's management attribute | May hold a sentinel value like `-1`; do not assume it is always a usable positive limit |
| `tomcat.connections.current` | Current connection count | Connections do not equal executing requests |
| `tomcat.connections.keepalive.current` | Keep-alive connections per management source | Connections may be waiting for the next reuse |
| `tomcat.connections.config.max` | Connection limit provided by the management source | Distinct from thread limit and current connections |

Connector meters usually carry a `name` tag. The tag value depends on protocol, address, port, and how the connector was created, such as names starting with `http-nio-...`. Do not assume a fixed label `http-nio-8080` is always present.

### 3.2. Request Counts, Errors, and Bytes

| Meter | Metric Type in Example | How to Read |
| --- | --- | --- |
| `tomcat.global.request` | FunctionTimer | Request count and total time provided by Tomcat's request processor |
| `tomcat.global.request.max` | Time Gauge | Maximum processing time reported by Tomcat's attribute |
| `tomcat.global.error` | FunctionCounter | Error count recorded by Tomcat's stats source |
| `tomcat.global.received` | FunctionCounter, byte unit | Bytes received recorded by Tomcat's stats source |
| `tomcat.global.sent` | FunctionCounter, byte unit | Bytes sent recorded by Tomcat's stats source |

FunctionCounter/FunctionTimer reads an existing function or statistics object, rather than requiring business code to call `increment()` for each event. When querying, still read `COUNT`, total time, unit, and the data source's lifecycle carefully.

Do not assume a business error inside a response body always corresponds to a container error. Tomcat metrics also do not explain the business cause of failures.

`tomcat.global.request.max` is a separate metric name; do not assume it is always inside the measurements array of `tomcat.global.request`. Totals and max alone are also insufficient to reconstruct p95 or p99.

### 3.3. Sessions

| Meter | Common Meaning |
| --- | --- |
| `tomcat.sessions.active.current` | Active sessions per Manager |
| `tomcat.sessions.active.max` | High-water mark of active sessions per source stats |
| `tomcat.sessions.created` | Total sessions created per measurement source |
| `tomcat.sessions.expired` | Total sessions expired per measurement source |
| `tomcat.sessions.rejected` | Total sessions rejected per measurement source |
| `tomcat.sessions.alive.max` | Longest session lifetime per source stats |

Micrometer describes the session group and how the binder connects to Tomcat's Manager. [Micrometer Tomcat instrumentation](https://docs.micrometer.io/micrometer/reference/reference/tomcat.html).

An application that never creates sessions can have session values of 0 even while serving heavy traffic. Sessions are also not login counts, account counts, or online user counts.

### 3.4. Servlet and Cache

In the lab configuration, `tomcat.servlet.request`, `tomcat.servlet.request.max`, `tomcat.servlet.error`, along with `tomcat.cache.access` and `tomcat.cache.hit` also appear.

The servlet group can be filtered by servlet name such as `dispatcherServlet`. Cache here belongs to container resources tracked by the binder, not automatically a business cache using Spring Cache. Verify a meter's source before using it to draw conclusions about another caching system.

## 4. Reading Tags and Statistics Before Computing Ratios

### 4.1. Find Names First, Then Filter the Right Connector

In a web app with the endpoint exposed:

```http
GET /actuator/metrics
GET /actuator/metrics/tomcat.threads.busy
GET /actuator/metrics/tomcat.global.request
```

Read `availableTags` to get the actual `name` value. Then filter using that exact value.

PowerShell example—replace the variable value with the actual label you observed:

```powershell
$connectorName = 'http-nio-127.0.0.1-8080'
curl.exe --get 'http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy' --data-urlencode "tag=name:$connectorName"
```

The label in the command is an example, not guaranteed for every run. Connectors using random ports or different addresses can have different names.

Apply the same filter conditions when comparing busy, current, and max. With multiple connectors or a shared executor, aggregating gauges without verifying scope can cause double counting or a meaningless sum.

### 4.2. Do Not Divide by an Invalid Max

For the same pool with a positive limit and compatible measurements, you can look at a ratio such as:

```text
busy ratio = busy / max
```

However, you must verify that the denominator is genuinely a meaningful limit of the pool under examination.

Tomcat states clearly: when a connector is assigned its own executor, the connector's `maxThreads` attribute no longer controls the internal pool; over JMX it may be reported as `-1` to indicate it is unused. [Tomcat HTTP Connector Attributes](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html).

In the lesson's experiment, the connector uses `StandardThreadExecutor` and `tomcat.threads.config.max` takes value `-1`. Do not turn it into 1, do not divide busy by -1, and do not conclude the pool has negative capacity. Inspect the actual executor running the work and metrics suited to that executor.

Virtual thread mode also requires revisiting interpretations built around the platform-thread pool model. Never apply a `busy/max` formula solely because both metric names exist. The example below disables virtual threads to keep the lab scope clear, though that still does not guarantee a connector's max attribute is positive.

### 4.3. A Single Point-in-Time Sample Does Not Prove State Over an Interval

`busy=0` on a single read does not prove there were no requests in the past minute. Short requests can finish between samples.

Conversely, a single high busy reading does not by itself prove the bottleneck is thread starvation; threads may be waiting on a database, external service, or other work. Cross-check processing times, errors, resources, and appropriate observation sources.

## 5. Embedded Verification App Example

The application has a test endpoint `/probe`. Normally it simply returns `ok`; passing `session=true` actively creates or retrieves an HTTP session.

This endpoint helps verify Tomcat's metric sources using real requests. The app creates no custom `tomcat.*` meters; measurements come from built-in integration.

### 5.1. Structure

```text
tomcat-metrics-demo/
├── pom.xml
└── src/main/
    ├── java/example/tomcatmetrics/TomcatMetricsApplication.java
    └── resources/application.yml
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>tomcat-metrics-demo</artifactId>
    <version>1.0.0</version>
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
```

Versions are pinned to reproduce the example's behavior. The standard web starter brings embedded Tomcat into the project; the Actuator starter supplies metrics integration. Do not mix other Spring and Tomcat versions into the dependency set if your goal is reproducing this experiment.

### 5.2. Configuration

`src/main/resources/application.yml`:

```yaml
spring:
  threads:
    virtual:
      enabled: false

server:
  address: 127.0.0.1
  port: 8080
  tomcat:
    mbeanregistry:
      enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

The sample app listens on loopback. The configuration opens the `metrics` endpoint for observation in the lab; endpoint exposure and access permissions in a real application must follow that application's security setup.

There is no need to add `spring.jmx.enabled=true` merely to stand in for Tomcat's MBean registry flag. The two settings are not synonymous.

### 5.3. Java Code

`src/main/java/example/tomcatmetrics/TomcatMetricsApplication.java`:

```java
package example.tomcatmetrics;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication(proxyBeanMethods = false)
@RestController
public class TomcatMetricsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TomcatMetricsApplication.class, args);
    }

    @GetMapping("/probe")
    public String probe(HttpServletRequest request,
                        @RequestParam(name = "session",
                                defaultValue = "false") boolean session) {
        if (session) {
            request.getSession(true);
        }
        return "ok";
    }
}
```

The `session` parameter is solely for the experiment. When `false`, the code does not actively create a session. When `true`, `request.getSession(true)` creates a session if the request does not already have a valid one.

### 5.4. Compiling and Running

Maven and JDK 17 or higher are required; the code runs on JDK 21.

```shell
mvn -q package
java -jar target/tomcat-metrics-demo-1.0.0.jar
```

On the first run, Maven needs to download plugins and dependencies if not already cached. The app keeps running to accept requests; open another terminal to execute read commands. Stop the process with `Ctrl+C` when finished experimenting.

Startup logs contain timestamps, environment info, and values that can vary across machines. There is no fixed set of thread counts, connections, or processing durations valid for every run.

Send a request:

```shell
curl "http://127.0.0.1:8080/probe"
```

Exact response body of the sample endpoint:

```text
ok
```

In PowerShell, if `curl` is an alias for another command, invoke `curl.exe`.

## 6. Reading and Comparison Experiments

### 6.1. Check Names Before Creating a Session

After the application starts, read:

```shell
curl "http://127.0.0.1:8080/actuator/metrics"
curl "http://127.0.0.1:8080/actuator/metrics/tomcat.sessions.created"
curl "http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy"
```

Read names, units, statistics, and tags. Sessions may still be 0; do not modify the endpoint to fake activity just because you see a 0 value.

Requests to Actuator also go through the server. Thus, observing via HTTP can itself generate activity visible in connector request or byte counters.

### 6.2. Actively Create a Session

Note the created session count, then call:

```shell
curl "http://127.0.0.1:8080/probe?session=true"
curl "http://127.0.0.1:8080/actuator/metrics/tomcat.sessions.created"
```

With a fresh call carrying no valid session cookie, the created session count should rise due to the action performed. Do not assert an absolute value such as always 1 if the app has handled other requests beforehand.

If you send back a valid session cookie, a call to `getSession(true)` can reuse the existing session instead of creating a new one. Calling with `curl` without retaining cookies can create multiple sessions across calls. That is not proof of that many distinct users.

### 6.3. Reading Requests and Time Units

Query:

```shell
curl "http://127.0.0.1:8080/actuator/metrics/tomcat.global.request"
curl "http://127.0.0.1:8080/actuator/metrics/tomcat.global.request.max"
```

In the request group, check `COUNT`, total time, and the returned unit. `COUNT` is the number of requests tallied by Tomcat's source, not requests/second automatically.

If you need an average duration, only divide total time by count within the same scope when count is positive. Do not mistakenly divide a sum across multiple connectors by one connector's count.

In the separate max meter, do not infer an entire distribution or end-user-perceived latency from a single max. The container's measurement boundary can differ from proxies, clients, or application-level metrics.

### 6.4. Disable MBean Registry and Restart

Stop the old process and restart:

```shell
java -jar target/tomcat-metrics-demo-1.0.0.jar --server.tomcat.mbeanregistry.enabled=false
```

In the Boot 3.3.0 experiment, thread and global request metrics from the connector are no longer in the registry, yet session metrics remain registered and still reflect session creation.

HTTP still serves `/probe`. Missing one meter group does not mean Tomcat stopped; conversely, working HTTP does not prove MBean sources for every group are ready.

### 6.5. Distinguish Endpoint Not Exposed From Missing Meter

With MBean registry enabled, try exposing only health at startup:

```shell
java -jar target/tomcat-metrics-demo-1.0.0.jar --management.endpoints.web.exposure.include=health
```

In this setup, `/actuator/metrics` is not served over HTTP even though meters may already exist inside the registry. That is a change in access exposure, not proof that Tomcat integration lost data.

To test a filter separately, in another run you can set:

```shell
java -jar target/tomcat-metrics-demo-1.0.0.jar --management.metrics.enable.tomcat=false
```

This prefix filter blocks Tomcat meters within the experiment's configuration scope, while the server still handles HTTP and unblocked groups still work. Do not confuse it with the MBean registry enable flag.

## 7. Comparing With http.server.requests

`http.server.requests` and `tomcat.*` are two distinct observation layers.

| Group | Primary Scope | Appropriate Question |
| --- | --- | --- |
| `http.server.requests` | Spring's HTTP observation on integrated components | What are the characteristics of requests by URI, method, and status? |
| `tomcat.threads.*`, `tomcat.connections.*` | Tomcat connector/pool resources | What state are server resources in? |
| `tomcat.global.*` | Tomcat request processor statistics | What volume and duration has the container source recorded? |
| `tomcat.sessions.*` | Manager sessions tracked by the binder | How are sessions created, retained, or expired? |

After a `/probe` request, the sample application can record `http.server.requests` for that route even when Tomcat's MBean registry flag is off. The lesson's experiment verified that.

You do not need Tomcat MBeans enabled for `http.server.requests` to be a valid meter, and having HTTP meters does not replace pool or connector indicators.

The two counts do not have to match on every read: scopes, measurement completion timing, Actuator requests, and filter conditions can differ. Before comparing, verify whether you are comparing the same route vs. the whole connector, the same timeframe, and the same instance.

## 8. Interpretation Limits

### 8.1. Negative Sentinel Numbers and Non-Finite Values

Sentinel values such as `-1` or non-finite values from a management source should not be coerced to 0 or plugged directly into percentage formulas. Read the source attribute's documentation and inspect the active executor, protocol, and version.

Do not substitute raising max threads in configuration for finding the root cause. First know which attribute actually governs the real executor.

### 8.2. Zero Sessions in Stateless Applications

Applications that do not use HTTP sessions can continuously serve traffic while session creation and active session metrics remain 0. That can be correct behavior by design.

An active session also does not guarantee a user is currently sending a request at sampling time; it can simply remain alive waiting for expiration.

### 8.3. Instance Scope and Lifecycle

Tomcat figures belong to the container and instance serving the data. Restarting or recreating components can start a new lifecycle for source statistics.

Querying through a load balancer can route consecutive reads to different instances. Do not treat a change between two responses as a counter reset or bug in one counter without confirming the source.

### 8.4. Do Not Assume Every Component Exists

A servlet, resource cache, or connector that does not exist or is unused in a configuration may not expose the same set of names as another environment. Some meters also become meaningful only after relevant activity.

Names and tags should be discovered in the actual running environment. Do not manually create fake meters named `tomcat.*` just to make a list match a documentation screenshot.

## 9. Diagnostic Procedure When Indicators Are Missing

Check in order:

1. Confirm the app uses embedded Tomcat rather than another server or deployment model.
2. Confirm a registry and corresponding Actuator/Micrometer auto-configuration exist; inspect auto-configuration conditions if overridden or excluded.
3. Check the effective value of `server.tomcat.mbeanregistry.enabled`, including profiles and startup arguments.
4. Wait for startup to complete and identify which group is needed: session, thread, connector, servlet, or HTTP observation.
5. Check whether `management.metrics.enable.*` or custom filters block the meters.
6. If reading over HTTP, distinguish unexposed endpoint, lack of authorization, or wrong port/base path from an absent meter in the registry.
7. From the list of present names, read actual tags and units before filtering or calculating.

| Symptom | Interpretation to Check |
| --- | --- |
| `tomcat.sessions.*` present but thread/global request missing | Sessions may be read directly while connector MBean source is disabled |
| `http.server.requests` present but Tomcat threads missing | The two groups have different integration paths |
| `/actuator/metrics` unreachable | Could be exposure or authorization config, insufficient to conclude meters do not exist |
| Max threads equals `-1` | Could be an unused connector attribute due to a separate executor |
| Busy equals 0 after a burst of short requests | Requests may have finished before sampling |
| Sessions stay at 0 | Does the application actually create sessions? |
| Tomcat count increases when only reading Actuator | Management requests can also traverse the measured connector |
| Numbers differ from another environment | Check versions, server type, executor, connector, tags, and lifecycle |

Checking JMX Remote is a separate concern from the internal MBean source used for metrics. Do not open a remote management port just to try fixing an unverified meter registration condition.

## 10. Practice

Perform each change in a clean run, keeping before-and-after results:

1. Run the example with MBean registry enabled, inspect the list of `tomcat.*` names, and group them into session, connector, and servlet.
2. Call `/probe` several times without creating a session. Compare request metrics with session metrics and explain why they do not rise by the same rule.
3. Call `/probe?session=true` with a request carrying no valid session cookie. Verify created session count rises, then explain why that number is not user count.
4. Disable MBean registry, restart, and compare name groups. Do not insist every `tomcat.*` name must vanish.
5. Re-enable MBean registry while exposing only health. Distinguish data inside the registry from HTTP access to the metrics endpoint.
6. For a specific connector, read busy, current, and config max. Compute a ratio only when samples are compatible and max is positive and meaningful; if you encounter `-1`, identify the executor mechanism first.
7. Compare `tomcat.global.request` with `http.server.requests` filtered to URI `/probe`. State scope differences clearly before judging whether the two counts match.

When reporting results, state the meter name, connector or servlet tag, statistic type, unit, and MBean registry condition. A Tomcat measurement is only meaningful when tied to the exact source and configuration of the running server.
