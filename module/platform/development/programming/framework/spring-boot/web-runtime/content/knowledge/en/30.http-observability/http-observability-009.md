# Connecting Actuator, Health, and Readiness to Spring Boot Web Runtime State

A Spring Boot web application can have **a running JVM process yet not be ready for requests**, or **remain alive yet be ineligible to serve traffic**. Behind a load balancer or Kubernetes, deciding whether to **restart a process**, **temporarily stop routing requests to an instance**, or **keep serving it** should never rely on an endpoint hardcoded to return `"OK"`. Spring Boot Actuator provides **`HealthEndpoint`**, **health groups**, and **`ApplicationAvailability`** to reflect these states through HTTP probes.

Part of **Spring Boot - web-runtime → HTTP Observability**, this lesson examines **connecting Actuator, health, and readiness to web server lifecycles, Servlet requests, health checks, and operations**. Examples use **Java 17+, Spring Boot 3.3.13, Spring MVC, embedded Tomcat, and Maven**, including liveness/readiness probes on the **main HTTP port**, a toggleable custom `HealthIndicator`, publishing `AvailabilityChangeEvent`, and integration tests using real HTTP. Kubernetes, reverse proxies, Spring Security, graceful shutdown, and failure scenarios are covered to help prevent probe misconfigurations that cause downtime.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish **process alive**, **HTTP listener reachable**, **application health**, **liveness**, **readiness**, and **startup**.
2. Understand **`ApplicationAvailability`**, **`LivenessState.CORRECT`/`BROKEN`**, **`ReadinessState.ACCEPTING_TRAFFIC`/`REFUSING_TRAFFIC`**, plus `ApplicationStartedEvent` and `ApplicationReadyEvent`.
3. Enable **`spring-boot-starter-actuator`** and inspect **`/actuator/health`**, **`/actuator/health/liveness`**, and **`/actuator/health/readiness`**.
4. Use **`management.endpoint.health.probes.enabled`** outside Kubernetes and **`management.endpoint.health.probes.add-additional-paths`** to expose **`/livez`** and **`/readyz`** on the main server port.
5. Distinguish **`management.server.port`** from **`server.port`**, understanding why a health check on a separate management connector can report UP even when the main web connector cannot accept connections.
6. Implement a **`HealthIndicator`** and include it in the readiness group via **`management.endpoint.health.group.readiness.include`**, while keeping liveness decoupled from external dependencies.
7. Publish **`AvailabilityChangeEvent`** at appropriate times to pause or resume traffic intake for valid domain reasons.
8. Write **`@SpringBootTest(RANDOM_PORT)`** tests checking HTTP 200/503 across liveness and readiness transitions rather than relying solely on `MockMvc`.
9. Configure **Kubernetes `livenessProbe`, `readinessProbe`, and `startupProbe`** properly, accounting for period/timeout/failure thresholds and drain time.
10. Diagnose false positives, false negatives, cascading restarts, 503s, 401/404 health endpoints, slow startups, wrong-port proxies, and readiness coupled to flaky upstreams.

Prerequisites: Maven/Java 17, Spring Boot embedded web runtime, HTTP status codes, dependency injection, Servlet containers, and multi-replica deployments.

## 2. "App Running" Does Not Mean "Ready for Traffic"

Trace how an application starts up:

~~~text
JVM process launched
    |
    v
Spring ApplicationContext creating beans
    |
    v
Embedded Tomcat HTTP connector initialized
    |
    v
ApplicationStartedEvent, context refreshed
    |
    v
ApplicationRunner / CommandLineRunner
    cache warmup, resource initialization
    |
    v
ApplicationReadyEvent
    |
    v
ApplicationAvailability:
    ReadinessState.ACCEPTING_TRAFFIC
    |
    v
Kubernetes/load balancer may route traffic
~~~

**Three core concepts:**

- **Liveness:** is the process still capable of working properly or recovering on its own? If broken beyond recovery, infrastructure may **restart the instance**.
- **Readiness:** should this instance receive new traffic **right now**? If not ready, infrastructure should **temporarily remove it from load-balancer endpoints** without necessarily restarting it.
- **Startup:** is periodic liveness/readiness checking allowed to begin yet? Kubernetes provides a dedicated `startupProbe` to defer the other two probes when startup takes significant time.

An existing PID does **not** prove HTTP routing works; an open HTTP port does **not** prove startup finished; and **`/actuator/health` returning 200** does not prove all business use cases succeed.

### 2.1. Operational Decision Table

| Signal | Question | Appropriate infrastructure reaction |
| --- | --- | --- |
| Process/container exit | Is the process still alive? | Restart container per restart policy. |
| Startup probe fails | Has minimum startup finished? | Hold off liveness/readiness; restart if threshold exceeded. |
| Liveness fails | Is the process wedged/unrecoverable? | Restart instance once `failureThreshold` is exceeded. |
| Readiness fails | Can this instance take more requests right now? | Remove from Service endpoints; **do not restart merely for readiness failure**. |
| Business endpoint fails | Is a specific feature erroring? | Track SLOs, alert, apply retries/circuit breakers/fallbacks; do not turn into liveness failure automatically. |
| Actuator health details | Which health contributors are DOWN/UP? | Inspect components; decide which health group each indicator belongs in. |

**Key design rule:** keep liveness simple and reliable; let readiness reflect **this instance's** ability to serve traffic. Never blindly point liveness at **global `/actuator/health`**, because global health often aggregates databases, disk space, or downstream services and can trigger fleet-wide restarts.

## 3. Spring Boot `ApplicationAvailability`

Spring Boot provides **`org.springframework.boot.availability.ApplicationAvailability`** with two dimensions:

- **`LivenessState`**: **`CORRECT`** or **`BROKEN`**.
- **`ReadinessState`**: **`ACCEPTING_TRAFFIC`** or **`REFUSING_TRAFFIC`**.

These are **in-memory states of the application instance**, not HTTP responses themselves. Actuator maps them into HTTP health groups via dedicated health indicators. Changing an availability state does not automatically make business HTTP controllers return 503: the **orchestrator/load balancer** polls the probe to adjust routing, and requests sent directly to a Pod IP still reach the app while the connector is up.

### 3.1. Startup Lifecycle

| Spring Boot 3.3 stage | Liveness | Readiness | Meaning |
| --- | --- | --- | --- |
| Starting up | **BROKEN** | **REFUSING_TRAFFIC** | App is not live/ready yet; HTTP endpoints may not exist yet. |
| Context refreshed, `ApplicationStartedEvent` | **CORRECT** | **REFUSING_TRAFFIC** | App is live, startup runners have not completed yet. |
| `ApplicationReadyEvent` and subsequent availability event | **CORRECT** | **ACCEPTING_TRAFFIC** | Startup tasks finished; considered ready. |

These reflect the **Spring Boot 3.3** lifecycle model, not a guarantee that HTTP connections succeed at every millisecond of startup. Before the connector binds its port, probes get **connection refused/timeout**, not JSON 503 from Actuator.

**`ApplicationRunner`/`CommandLineRunner`** is ideal for work that must finish before readiness—such as loading mandatory config or warming essential local state. Do not place critical warmup inside **`@PostConstruct`** assuming it controls readiness ordering: bean initialization and application ready events occur at different stages.

### 3.2. Shutdown Lifecycle

When told to shut down, Spring Boot can transition to **`ReadinessState.REFUSING_TRAFFIC`**, then execute graceful shutdown if configured. The HTTP connector stops accepting new requests during draining and probes may **stop returning JSON**, even while in-memory state briefly persists.

~~~text
Running: liveness CORRECT, readiness ACCEPTING_TRAFFIC
    |
    v
SIGTERM / graceful shutdown
    |
    v
readiness REFUSING_TRAFFIC
    |
    v
Stop accepting new requests, drain in-flight requests
    |
    v
Close context and connector
~~~

Kubernetes Pod termination also involves `EndpointSlice` updates and `terminationGracePeriodSeconds`, not HTTP probes alone. Coordinate readiness, `preStop` hooks when needed, graceful shutdown timeouts, and load-balancer propagation delays.

### 3.3. Reading Availability State from Java

~~~java
package com.example.probe;

import java.util.Map;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AvailabilityController {
    private final ApplicationAvailability availability;

    public AvailabilityController(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @GetMapping("/demo/availability")
    public Map<String, String> currentState() {
        return Map.of(
            "liveness", availability.getLivenessState().name(),
            "readiness", availability.getReadinessState().name());
    }
}
~~~

This class appears in the demo. After startup, it normally returns **`CORRECT`/`ACCEPTING_TRAFFIC`**. **This reflects pure availability state**: it **does not evaluate custom `HealthIndicator`s** added to the readiness group. You can observe `ApplicationAvailability` reporting `ACCEPTING_TRAFFIC` while the HTTP readiness endpoint returns 503 due to a `DOWN` contributor; that is expected behavior, not a contradiction.

## 4. Actuator `HealthEndpoint`, Statuses, and HTTP Responses

### 4.1. Enabling Actuator

Add the Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

By default, Spring Boot 3.3 **exposes only the `health` endpoint over HTTP**; metrics/info require explicit exposure configuration. Default URL:

~~~text
GET http://localhost:8080/actuator/health
~~~

Minimal response when UP:

~~~json
{"status":"UP"}
~~~

**Health details are hidden by default.** Never set `show-details=always` on public endpoints just for convenience; details can expose hostnames, filesystems, databases, and internal topology.

### 4.2. `HealthContributor` and `HealthIndicator`

Actuator aggregates status from **`HealthContributor`** beans; built-in **`HealthIndicator`** examples include `diskSpace`, `db` (when `DataSource` exists), `redis`, plus application-defined custom indicators. An indicator returns:

- **UP:** component is functioning normally.
- **DOWN:** component failed.
- **OUT_OF_SERVICE:** component should not serve traffic right now.
- **UNKNOWN:** state could not be determined clearly.

Aggregation uses **`StatusAggregator`**; HTTP status mapping uses **`HttpCodeStatusMapper`**. Defaults:

| Health status | Default HTTP response |
| --- | --- |
| UP | 200 OK |
| DOWN | **503 Service Unavailable** |
| OUT_OF_SERVICE | **503 Service Unavailable** |
| UNKNOWN | Typically **200** (no default failure mapping) |

Custom status mappings can alter this; if customizing mappings, remember default `DOWN`/`OUT_OF_SERVICE` mappings may need redeclaration. **Never write Kubernetes probes parsing raw JSON `"UP"` text when HTTP status code is the standard signal.**

### 4.3. Global Health Is Not Liveness

~~~text
/actuator/health                Aggregates contributors in global health
/actuator/health/liveness       Liveness group (typically livenessState)
/actuator/health/readiness      Readiness group (typically readinessState)
/livez                          Liveness path on main server port if enabled
/readyz                         Readiness path on main server port if enabled
~~~

If the database health contributor goes `DOWN`, global `/actuator/health` returns **503**, while liveness remains **200** because the process itself is healthy. Separating these prevents restarting an entire application fleet during a shared database outage.

## 5. Enabling Liveness/Readiness Probes in Boot 3.3

### 5.1. Auto-Enable in Kubernetes

Spring Boot 3.3 detects Kubernetes environments automatically and enables **`liveness`** and **`readiness`** health groups there. Locally outside Kubernetes, **enable them explicitly**:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Enabling probes in Spring Boot does not alter Kubernetes behavior on its own: you still must declare **`livenessProbe`/`readinessProbe`** in your workload manifest so kubelet polls them.

### 5.2. Health Group URLs

With probes enabled:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Once the app is ready and healthy, both respond HTTP **200** with body:

~~~json
{"status":"UP"}
~~~

These are two **distinct health groups**. Never point liveness at the readiness URL just because both return `UP` under normal conditions.

### 5.3. Adding `/livez` and `/readyz` on the Main Web Port

An important configuration:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

In Spring Boot 3.3, **`management.endpoint.health.probes.add-additional-paths=true`** exposes:

~~~text
/livez    -> liveness group on main server port
/readyz   -> readiness group on main server port
~~~

If **`server.servlet.context-path`** is set, verify the real main-server URL. When using a separate management port, **`/actuator/health/...`** lives on the management port while **`/livez` and `/readyz`** live on the **main server port**. Custom additional paths require the `server:` or `management:` prefix per Spring Boot's group additional-path API.

### 5.4. Why Main-Port Probes Matter

Consider this topology:

~~~text
                 +--> Port 8080 (main web server)
kubelet / LB ----|
                 +--> Port 8081 (management web server)
~~~

With **`management.server.port=8081`**, Actuator runs on a **separate web infrastructure/connector**. Consequently:

- Management port 8081 can keep returning `/actuator/health/readiness` **200**.
- Meanwhile, main port 8080 could be unable to accept new connections due to thread pool exhaustion, connector failure, or network routing issues.
- A Kubernetes probe hitting only 8081 suffers a **false positive**, continuing to route traffic to a broken instance.

Pointing kubelet at **`/livez` and `/readyz` on port 8080** ensures probes exercise the **main connector's HTTP path** alongside availability/group health. Even then, a lightweight probe returning 200 **does not prove every API, database, auth flow, or message queue is healthy**—pair probes with SLO monitoring and business checks.

## 6. Should Readiness Check Databases, Redis, or External APIs?

### 6.1. Keep External Dependencies Out of Liveness

**Liveness** should reflect unrecoverable internal failure. Adding DB, Redis, or partner APIs to liveness means a single DB outage can **restart all pods**. Restarts trigger connection storms, cold caches, and startup CPU spikes, turning a dependency hiccup into a **cascading failure**.

**Conservative rule:** leave liveness on the default **`livenessState`**; only add an indicator if it reliably detects an internal deadlock/failure that a restart genuinely cures.

### 6.2. Be Selective with Dependencies in Readiness Too

Readiness answers **should this specific instance take traffic**. Adding checks can make sense when:
- This instance requires a **local data snapshot** to serve valid answers.
- This replica's own local pool/resource is exhausted and needs cooldown.
- A mandatory local cache has not finished warming up.
- This instance must complete a local bootstrap task before accepting traffic.

Be very cautious when:
- A database is shared across **all replicas**: when the DB blips, every instance turns unready simultaneously, leaving the Service with zero endpoints.
- An optional recommendation service fails while the API has a working fallback; pulling the entire app out of rotation is counterproductive.
- Frequent probes run expensive network calls or long timeouts, adding load onto a struggling dependency.

**Recommendation:** keep the readiness group limited to **`readinessState`** plus lightweight, tight-timeout indicators directly tied to **this instance's** ability to accept traffic. Use fallbacks, circuit breakers, and SLO alerts rather than polling every downstream inside readiness probes.

### 6.3. Customizing Health Groups

Spring Boot lets you include specific contributor IDs:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: "readinessState,localCapacity"
~~~

Here:
- **`readinessState`** is Boot's built-in indicator backed by `ApplicationAvailability`.
- **`localCapacity`** is the custom `HealthIndicator` built in the next section.
- The liveness group excludes `localCapacity`, so `localCapacity` going `DOWN` never triggers a liveness failure.

**Important:** Spring Boot validates health group membership at startup. Including a nonexistent ID fails startup. Verify bean names, noting the rule stripping the **`HealthIndicator`** suffix. Never disable **`management.endpoint.health.validate-group-membership`** just to hide a misconfigured ID.

## 7. Complete Java 17 Spring Boot Project

The demo implements:
1. Web app exposing `GET /demo/ping` and `GET /demo/availability`.
2. Actuator health groups plus `/livez` and `/readyz` on the main HTTP port.
3. Custom `HealthIndicator` **`localCapacity`** backed by an `AtomicBoolean`, defaulting to UP.
4. A control controller active **only under the `demo` profile** allowing toggles to `ReadinessState.REFUSING_TRAFFIC` and `localCapacity` DOWN.
5. JUnit integration tests using **real HTTP requests** asserting **200/503** responses and confirming liveness stays UP during readiness failures.
6. Control endpoints **disabled in production deployments**, and the `demo` profile bound to loopback for lab safety.

### 7.1. Directory Tree

~~~text
web-runtime-health-demo/
  pom.xml
  mvnw
  mvnw.cmd
  src/
    main/
      java/com/example/probe/
        ProbeApplication.java
        ProbeController.java
        LocalCapacityState.java
        LocalCapacityHealthIndicator.java
        DemoControlController.java
      resources/
        application.yml
        application-demo.yml
    test/
      java/com/example/probe/
        ProbeIntegrationTest.java
~~~

All Java files use package **`com.example.probe`**, with the main class at the root package so component scan discovers everything. Maven wrapper scripts are normally generated by Spring Initializr; if creating the POM manually without wrapper files, run **`mvn`** instead.

### 7.2. pom.xml

~~~xml
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
    <artifactId>web-runtime-health-demo</artifactId>
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

The version is pinned to demonstrate Spring Boot 3.3 APIs. For production, choose a maintained release receiving security patches and exclude demo control endpoints/profiles from deployments.

### 7.3. ProbeApplication.java

**src/main/java/com/example/probe/ProbeApplication.java**

~~~java
package com.example.probe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProbeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProbeApplication.class, args);
    }
}
~~~

### 7.4. ProbeController.java — Reading AvailabilityState

**src/main/java/com/example/probe/ProbeController.java**

~~~java
package com.example.probe;

import java.util.Map;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    private final ApplicationAvailability availability;

    public ProbeController(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @GetMapping("/demo/ping")
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }

    @GetMapping("/demo/availability")
    public Map<String, String> availability() {
        return Map.of(
                "liveness", availability.getLivenessState().name(),
                "readiness", availability.getReadinessState().name());
    }
}
~~~

**`GET /demo/availability`** reads Spring Boot's **`ApplicationAvailability`** directly without aggregating health contributors. If `localCapacity` goes `DOWN`, this endpoint can still show readiness `ACCEPTING_TRAFFIC` while `/readyz` returns **503**. That is accurate: the readiness health group combines **`readinessState` and `localCapacity`** without mutating `ApplicationAvailability`.

### 7.5. LocalCapacityState.java — Simulated Per-Replica State

**src/main/java/com/example/probe/LocalCapacityState.java**

~~~java
package com.example.probe;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class LocalCapacityState {

    private final AtomicBoolean accepting =
            new AtomicBoolean(true);

    public boolean isAccepting() {
        return accepting.get();
    }

    public void setAccepting(boolean value) {
        accepting.set(value);
    }
}
~~~

**`AtomicBoolean`** makes flag reads/writes thread-safe across request threads in the lab. It does not model real database capacity, does not sync across pods, and does not persist across restarts. Production readiness predicates should check observable conditions with clear timeouts, failure handling, and concurrency guarantees.

### 7.6. LocalCapacityHealthIndicator.java

**src/main/java/com/example/probe/LocalCapacityHealthIndicator.java**

~~~java
package com.example.probe;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("localCapacityHealthIndicator")
public class LocalCapacityHealthIndicator implements HealthIndicator {

    private final LocalCapacityState state;

    public LocalCapacityHealthIndicator(LocalCapacityState state) {
        this.state = state;
    }

    @Override
    public Health health() {
        if (state.isAccepting()) {
            return Health.up().build();
        }

        return Health.down()
                .withDetail("reason", "local capacity unavailable")
                .build();
    }
}
~~~

Bean name **`localCapacityHealthIndicator`** maps in Actuator to indicator ID **`localCapacity`** after stripping the `HealthIndicator` suffix. That matches `readiness.include: readinessState,localCapacity` in `application.yml`.

When `state=false`:
- The indicator returns **`DOWN`**.
- The readiness health group aggregates to **`DOWN`** and returns HTTP **503**.
- The liveness group (containing only `livenessState`) remains **`UP`/200** while application liveness is `CORRECT`.
- Global health **may also go `DOWN`** since it aggregates all indicators—another reason never to use global health as liveness.

**Never let `health()` call external APIs without timeouts**, run heavy DB queries, or throw unhandled unchecked exceptions under high-frequency polling. Health checks must be fast and side-effect-free, and health details should be visible only to authorized callers.

### 7.7. DemoControlController.java — Toggling Readiness via Events

**src/main/java/com/example/probe/DemoControlController.java**

~~~java
package com.example.probe;

import java.util.Map;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("demo")
@RestController
@RequestMapping("/demo/control")
public class DemoControlController {

    private final ApplicationEventPublisher events;
    private final LocalCapacityState capacity;

    public DemoControlController(
            ApplicationEventPublisher events,
            LocalCapacityState capacity) {
        this.events = events;
        this.capacity = capacity;
    }

    @PostMapping("/refuse")
    public Map<String, String> refuse() {
        AvailabilityChangeEvent.publish(
                events, this, ReadinessState.REFUSING_TRAFFIC);
        return Map.of("readiness", "REFUSING_TRAFFIC");
    }

    @PostMapping("/accept")
    public Map<String, String> accept() {
        AvailabilityChangeEvent.publish(
                events, this, ReadinessState.ACCEPTING_TRAFFIC);
        return Map.of("readiness", "ACCEPTING_TRAFFIC");
    }

    @PostMapping("/capacity/off")
    public Map<String, Boolean> capacityOff() {
        capacity.setAccepting(false);
        return Map.of("localCapacity", false);
    }

    @PostMapping("/capacity/on")
    public Map<String, Boolean> capacityOn() {
        capacity.setAccepting(true);
        return Map.of("localCapacity", true);
    }
}
~~~

**`AvailabilityChangeEvent.publish(...)`** is Spring Boot's API to signal availability state changes. Switching to **`REFUSING_TRAFFIC`** makes `readinessState` report **`OUT_OF_SERVICE`**, turning `/readyz` to 503 while liveness stays UP.

**Warning:** this experimental controller alters load-balancing signals; **never expose it in production**. `@Profile("demo")` excludes the bean under other profiles, and `application-demo.yml` binds loopback for the lab. Never treat `@Profile` alone as authentication; if enabled in any shared environment, secure these POST endpoints properly. Production apps should adjust readiness via internal lifecycle hooks, overload control, or secure maintenance workflows—not open public endpoints.

### 7.8. application.yml — Wiring Probes

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: web-runtime-health-demo

server:
  port: 8080
  shutdown: graceful

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: "readinessState,localCapacity"

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

**Critical YAML syntax note:** in a real file, **never split two separate `spring:` root keys as shown in the split illustration above**, because strict YAML parsers reject duplicate mapping keys at startup. Use the **merged `application.yml` below**, which is the actual file to copy:

~~~yaml
spring:
  application:
    name: web-runtime-health-demo
  lifecycle:
    timeout-per-shutdown-phase: 30s

server:
  port: 8080
  shutdown: graceful

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: "readinessState,localCapacity"
~~~

**Use only the second YAML block** for `src/main/resources/application.yml`. It configures:
- **`health,info`** as exposed HTTP Actuator endpoints, omitting `env`, `beans`, and `heapdump`.
- **`probes.enabled: true`** so local testing does not require faking a Kubernetes environment.
- **`add-additional-paths: true`** exposing `/livez` and `/readyz` on the main server port.
- **`readiness.include`** combining availability state with the `localCapacity` indicator.
- **`graceful`** and **`timeout-per-shutdown-phase: 30s`** allowing in-flight requests to drain within budget during shutdown.
- **`show-details: never`** preventing internal details from leaking on public health endpoints.

**Do not confuse the explanatory YAML snippet with the runnable file**; only the merged block is valid for the project. With ConfigMaps or Helm charts, validate against your YAML parser and keep keys unique.

### 7.9. application-demo.yml — Loopback-Only Binding in the Lab

**src/main/resources/application-demo.yml**

~~~yaml
server:
  address: 127.0.0.1
~~~

When the **`demo` profile** is active, the HTTP server binds only to loopback, reducing the risk of external hosts hitting `POST /demo/control/*`. The default production profile excludes that controller and omits `server.address=127.0.0.1`, allowing Kubernetes pods to listen on Pod IPs (unless overridden elsewhere).

**Never package or enable the `demo` profile in production manifests.** Secure management surfaces using network policies and service mesh/ingress rules per organizational standards.

### 7.10. Running the Project

Linux/macOS:

~~~bash
./mvnw clean package
java -jar target/web-runtime-health-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=demo
~~~

Windows PowerShell/CMD:

~~~text
mvnw.cmd clean package
java -jar target/web-runtime-health-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=demo
~~~

If the project has no Maven wrapper, run **`mvn clean package`**. Ensure port 8080 is free; once Spring Boot is ready, run:

~~~bash
curl -i http://localhost:8080/demo/ping
curl -i http://localhost:8080/demo/availability
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
~~~

Once startup completes with `localCapacity=true`, all health routes return **HTTP 200** with status `UP`. The availability JSON looks like:

~~~json
{"liveness":"CORRECT","readiness":"ACCEPTING_TRAFFIC"}
~~~

JSON key ordering is not part of the contract; inspect values by key.

## 8. Experiment: Readiness 503 While Liveness Stays 200

### 8.1. Changing `ApplicationAvailability` Readiness

With the `demo` profile running:

~~~bash
curl -i -X POST http://localhost:8080/demo/control/refuse
curl -i http://localhost:8080/demo/availability
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/livez
~~~

Expected:
- `POST /demo/control/refuse` returns 200 JSON from the controller.
- `GET /demo/availability` shows **`REFUSING_TRAFFIC`**.
- `GET /readyz` returns **503 Service Unavailable**; body is typically **`{"status":"OUT_OF_SERVICE"}`** from `readinessState`.
- `GET /livez` stays **200 `{"status":"UP"}`** because liveness didn't change.

**Why is `/readyz` still reachable during `REFUSING_TRAFFIC`?** Readiness is a signal **for Kubernetes to remove the instance from Service routing**; hitting localhost directly still reaches the active HTTP connector and handler. Never treat `readiness=false` as a firewall blocking direct traffic.

Recover:

~~~bash
curl -i -X POST http://localhost:8080/demo/control/accept
curl -i http://localhost:8080/readyz
~~~

Readiness returns to **200 UP**, assuming `localCapacity` is healthy.

### 8.2. Custom `HealthIndicator` Failing Readiness Independently

~~~bash
curl -i -X POST http://localhost:8080/demo/control/capacity/off
curl -i http://localhost:8080/demo/availability
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/actuator/health
~~~

Expected:
- `ApplicationAvailability` **still reports `ACCEPTING_TRAFFIC`** because no readiness event was published.
- **`/readyz`** returns **503 `DOWN`** due to the **`localCapacity`** health contributor.
- **`/livez`** remains **200 `UP`**.
- Global **`/actuator/health`** also returns **503** because of the custom `DOWN` indicator.

This illustrates why **`AvailabilityState`** and **health group aggregation** must be kept distinct: the readiness group can fail via a contributor even while the application readiness enum stays `ACCEPTING_TRAFFIC`.

Recover:

~~~bash
curl -i -X POST http://localhost:8080/demo/control/capacity/on
curl -i http://localhost:8080/readyz
~~~

Note that if you were still in `REFUSING_TRAFFIC` from the previous experiment, turning capacity back on alone isn't enough—you also need **`/demo/control/accept`**.

### 8.3. State Combination Matrix

| LivenessState | ReadinessState | localCapacity | /livez | /readyz |
| --- | --- | --- | --- | --- |
| CORRECT | ACCEPTING_TRAFFIC | true | 200 UP | 200 UP |
| CORRECT | REFUSING_TRAFFIC | true | 200 UP | 503 OUT_OF_SERVICE |
| CORRECT | ACCEPTING_TRAFFIC | false | 200 UP | 503 DOWN |
| CORRECT | REFUSING_TRAFFIC | false | 200 UP | 503 (multiple failing statuses in group) |
| BROKEN | Any | Any | 503 DOWN | Depends on readiness group |

**`LivenessState.BROKEN`** is an orchestrator restart signal, not a button to press manually in production hoping to "heal the app". The demo only toggles readiness and deliberately provides no broken-liveness API to discourage unnecessary restarts.

## 9. Integration Test: Real HTTP Checking 200 and 503

Using `MockMvc` alone verifies controller and `HealthEndpoint` logic, yet fails to prove endpoints bind to the main HTTP connector, omits real port routing, and cannot distinguish a management port from the app port. Prefer **`@SpringBootTest(webEnvironment=RANDOM_PORT)`** with **`TestRestTemplate`** over real TCP against embedded Tomcat.

### 9.1. Complete ProbeIntegrationTest.java

**src/test/java/com/example/probe/ProbeIntegrationTest.java**

~~~java
package com.example.probe;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("demo")
class ProbeIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    private String url(String path) {
        return "http://localhost:" + port + path;
    }

    private int status(String path) {
        return http.getForEntity(url(path), String.class)
                .getStatusCode().value();
    }

    private void post(String path) {
        ResponseEntity<String> response =
                http.postForEntity(
                        url(path), null, String.class);
        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.OK);
    }

    @Test
    void readinessCanFailWithoutLivenessFailing() {
        try {
            post("/demo/control/accept");
            post("/demo/control/capacity/on");

            assertThat(status("/demo/ping")).isEqualTo(200);
            assertThat(status("/livez")).isEqualTo(200);
            assertThat(status("/readyz")).isEqualTo(200);
            assertThat(status("/actuator/health/readiness"))
                    .isEqualTo(200);

            // Publish ReadinessState.REFUSING_TRAFFIC.
            post("/demo/control/refuse");

            assertThat(status("/readyz")).isEqualTo(503);
            assertThat(status("/livez")).isEqualTo(200);

            // Accept traffic again; local capacity then fails.
            post("/demo/control/accept");
            post("/demo/control/capacity/off");

            assertThat(status("/readyz")).isEqualTo(503);
            assertThat(status("/livez")).isEqualTo(200);
            assertThat(status("/actuator/health")).isEqualTo(503);

            post("/demo/control/capacity/on");
            assertThat(status("/readyz")).isEqualTo(200);
        }
        finally {
            // Reset shared test ApplicationContext state.
            post("/demo/control/accept");
            post("/demo/control/capacity/on");
        }
    }
}
~~~

**Test logic:** hits the random main web port, toggles availability and the local indicator, and proves readiness can return 503 while liveness stays UP. **`TestRestTemplate`** intentionally does not throw exceptions on 4xx/5xx, allowing direct assertion of HTTP 503.

**Practical caveat:** this test mutates state inside a shared Spring `ApplicationContext`. If your test suite runs tests in parallel against the same context, isolate contexts or synchronize tests to prevent races. Additionally, **`@SpringBootTest` only executes after the application context finishes starting**, so it does not cover the startup window; testing startup readiness requires launching an external process and polling concurrently.

### 9.2. Running Tests

~~~bash
./mvnw test
~~~

With the full POM above, Spring Boot Test, AssertJ, and JUnit come from `starter-test`. The test activates the `demo` profile so `/demo/control` exists; omitting **`@ActiveProfiles("demo")`** causes the POST endpoints to return 404—not an Actuator bug.

### 9.3. What Is Verified vs. What Is Not?

**Verified over real HTTP:**
- `/livez` and `/readyz` are mapped on the main server port.
- `AvailabilityChangeEvent` updates the readiness health group.
- The `localCapacity` indicator drives readiness group status.
- HTTP 503 on readiness failure leaves liveness unaffected.
- Global health can go `DOWN` independently of liveness.

**Not automatically verified here:**
- Kubelet removing a Pod from `EndpointSlice` in a real cluster.
- Load balancer/ingress behavior during connection draining.
- `terminationGracePeriodSeconds` under `SIGTERM`.
- Spring Security/network policies in deployment.
- Kubernetes `startupProbe` and threshold tuning.
- Web connector resilience under real saturation.

For production sign-off, test in staging with real manifests, proxies, and injected failures.

## 10. Kubernetes Probes: Configuration and Meaning

### 10.1. Example Deployment YAML

Package the app in a container exposing main HTTP port **8080** without enabling the `demo` profile. Kubernetes deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-runtime-health-demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: web-runtime-health-demo
  template:
    metadata:
      labels:
        app: web-runtime-health-demo
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: example.invalid/web-runtime-health-demo:1.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 24
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
            successThreshold: 1
~~~

**`example.invalid/...`** is a placeholder image name, not a hosted image. Build/push your own image and define `Service`, resource limits, security context, volumes, and network policies before deploying.

**Important:** this Deployment **does not activate the `demo` profile**, so the app does not bind loopback via `application-demo.yml` and excludes `POST /demo/control` endpoints. If another config sets `server.address=127.0.0.1`, kubelet probing the Pod IP gets connection refused; in real containers bind **`0.0.0.0`** or an address reachable on the Pod network.

### 10.2. Distinguishing Probes in the Manifest

- **`startupProbe`**: until it succeeds, kubelet **holds off running `livenessProbe`/`readinessProbe`**, protecting slow-starting apps from early restarts. `5s × 24 = ~120s` budget depending on call timing and timeout rules, not a millisecond-exact deadline.
- **`livenessProbe`**: repeated failures beyond `failureThreshold` trigger kubelet to restart the container.
- **`readinessProbe`**: on failure, the Pod is marked unready and pulled from Service endpoints while the process gets a chance to recover.
- **`periodSeconds`**: interval between probe checks.
- **`timeoutSeconds`**: max wait per probe attempt.
- **`failureThreshold`**: consecutive failures before taking action.
- **`successThreshold`**: for readiness, consecutive passes to become ready again (normally 1).

Avoid thresholds so tight that GC pauses, cold starts, TLS handshakes, or jitter trip them—and avoid thresholds so loose that broken instances serve traffic for minutes. Tune based on startup distributions, p99 latency, SLOs, and load testing.

### 10.3. Is `startupProbe` Always Required?

Not always. Spring Boot initializes readiness to `REFUSING_TRAFFIC` during startup, so readiness failures never restart a Pod. However, **`livenessProbe` can kill a slow-starting app**, especially during initial JVM warmup, database migrations, or cache loading. **`startupProbe`** helps whenever startup time is long or variable by deferring liveness checks until basic startup finishes.

Using **`/livez`** for `startupProbe` in this lab verifies the app reached live state and the main HTTP connector responds; **`/readyz`** can also serve as `startupProbe` if startup should wait until traffic-ready, provided you avoid deadlocks or dependencies that might stay down indefinitely. Match probe design to actual application lifecycle rather than copying one template blindly.

### 10.4. Kubernetes Service Traffic vs. Direct Pod Traffic

Failing readiness removes the Pod from normal `EndpointSlice`/Service routing. However:
- Direct calls to the Pod IP/localhost still hit the endpoint.
- Existing open connections or proxy caches may keep sending requests briefly during transition.
- If **all pods go unready**, the Service runs out of endpoints; ingress/load balancers return 503 or connection errors depending on configuration.
- Readiness failures never protect against application bugs or missing authorization.

Combine health probes with graceful shutdown, connection draining, bounded retries, idempotency, and telemetry.

## 11. Separate Management Ports and Common Traps

### 11.1. Two-Port Example

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

**This is an alternative/additional deployment snippet**, not something to drop into the demo assuming both ports expose identical health URLs. Here:
- **`/actuator/health`**, **`/actuator/health/liveness`**, **`/actuator/health/readiness`** live on **port 8081**.
- **`/livez`**, **`/readyz`** live on **main port 8080** because `add-additional-paths=true`.
- Custom management context/base paths shift URLs per Spring Boot's rules.

**Kubelet probes should hit 8080 `/livez` and `/readyz`** to exercise the serving web runtime. Port 8081 works well for internal monitoring/scraping, never as the sole proof that the main HTTP connector is healthy.

### 11.2. Why a Separate Health Endpoint Misses Main Connector Failures

The two ports can differ in:
- Tomcat connectors and thread pools;
- request queues and connection limits;
- TLS certificates and termination;
- network policies, firewalls, and ingress routing;
- Servlet contexts and filters;
- port binding and socket errors.

Management health returning UP because `ApplicationAvailability` says `ACCEPTING_TRAFFIC` does not prove main-port requests can succeed. **Exposing `/livez` and `/readyz` on the main port improves connection-level reliability**, yet still must be paired with request metrics and tracing.

### 11.3. Context Paths and Custom Paths

In a Servlet app:

~~~yaml
server:
  servlet:
    context-path: /shop

management:
  endpoints:
    web:
      base-path: /manage
~~~

When sharing the main port, the health endpoint typically becomes **`/shop/manage/health`**, and main-server additional paths must be verified against the context path and actual mappings. When `management.server.port` is split onto its own port, the management base path resolves relative to **`management.server.base-path`** rather than `server.servlet.context-path`.

**Never guess Kubernetes probe paths** when prefixes are customized: curl the Pod IP/port directly and verify active mappings before deploying.

## 12. How Should Custom `HealthIndicator`s Be Designed?

### 12.1. Avoid Side Effects

A `HealthIndicator` can be invoked every few seconds from multiple callers. It must:
- execute fast with strict timeouts;
- never mutate business state;
- avoid long locks or heavy transactions;
- avoid calling every partner API synchronously on each check;
- never retain invalid references to `HttpServletRequest`;
- never log secrets or raw connection strings;
- return a clear status on failure.

The demo indicator reads an `AtomicBoolean`, adding virtually zero overhead. In production, use a **short-TTL cached result** or state refreshed by a background worker if the underlying check is expensive—avoiding caches so long that probes report UP long after failure.

### 12.2. Health Group Membership

Spring Boot supports custom health groups:

~~~yaml
management:
  endpoint:
    health:
      group:
        dependencies:
          include: "db,redis"
~~~

This snippet is **valid only if `db` and `redis` indicators actually exist** via DataSource/Redis auto-config. Including a missing contributor fails startup validation. Custom groups are great for internal monitoring, **not as default liveness/readiness probes**.

Groups support per-group `show-details`, roles, and status mappings—still avoid `show-details=always` on public endpoints. Creating a custom group does not turn it into a Kubernetes probe unless the manifest explicitly targets that endpoint.

### 12.3. `ReactiveHealthIndicator`

In **Spring WebFlux/Reactor**, reactive checks should implement **`ReactiveHealthIndicator`** returning **`Mono<Health>`** without blocking the event loop. Spring Boot provides `ReactiveHealthContributorRegistry` and adapts synchronous `HealthContributor`s where appropriate. Liveness/readiness concepts, `ApplicationAvailability`, and HTTP statuses carry over, though connector/runtime/async semantics differ from MVC/Tomcat.

### 12.4. Health Status Is Not Authentication

HTTP 200 from `/readyz` does not mean a caller is authorized or data is valid. Health routes check instance viability/readiness, while authentication/authorization protect business APIs. Never put internal business data into health details exposed to the Internet.

## 13. Spring Security, Networking, and HTTP Observability

### 13.1. Security Can Block Actuator Probes

When **`spring-boot-starter-security`** is present, health/probe endpoints pass through the Spring Security filter chain. Defining your own **`SecurityFilterChain`** overrides Boot's default rules; `/readyz` is no longer guaranteed to permit anonymous callers. A **`401 Unauthorized`** on a readiness probe is a probe integration bug, not an unready health contributor.

Good operational practice:
- Allow kubelet/monitoring to invoke liveness/readiness via appropriate auth/network rules.
- Never open **`env`, `configprops`, `heapdump`, `beans`, or `loggers`** publicly.
- Restrict probe endpoints via IP/network policies, especially on the management port.
- Test **`GET /readyz` without cookies or sessions**, matching how kubelet calls probes.
- In custom `SecurityFilterChain`s, verify matchers cover **`/livez`, `/readyz`**, actuator health groups, and application context paths.

### 13.2. `EndpointRequest` vs. Path-Based Matchers

Spring Boot Actuator provides **`EndpointRequest`** matchers for endpoints. However, **`/livez` and `/readyz`** are additional paths on the main server and are not always matched by a rule matching only `/actuator/health`. Verify real runtime security behavior—and never fix a 401 by adding `permitAll("/**")`.

If using mTLS/sidecars/gateways instead of anonymous health endpoints, confirm kubelet actually holds valid credentials or network exemption rather than relying on browser cookies or user logins.

### 13.3. Metrics, Traces, and Readiness

With Spring Boot Actuator, collect HTTP metrics, thread/resource metrics, and traces together:
- **`/readyz`**: binary traffic-routing signal.
- **`http.server.requests`**: HTTP server latency and errors.
- **Tomcat metrics**: threads, connections, sessions (when enabled).
- **JVM metrics**: GC, heap/memory.
- **Tracing**: pinpoints where requests stall or fail.
- **Business SLOs**: success rates of critical operations.

An instance returning `/readyz` 200 while 40% of requests return 500 still demands incident response. Do not force readiness `DOWN` on every 5xx spike, or fleet-wide unready pods could wipe out all endpoints right when fallback serving is needed.

## 14. Graceful Shutdown and Readiness Drain

### 14.1. How Graceful Shutdown Works

In Spring Boot 3.3:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

lets Spring Boot manage graceful shutdown on supported web servers. Tomcat stops accepting new requests and waits for in-flight requests up to the configured timeout, though infinite streams or lingering connections are not guaranteed to finish cleanly.

Kubernetes needs **`terminationGracePeriodSeconds`** larger than the shutdown budget plus any `preStop`/sidecar overhead. The demo manifest uses 45s alongside a 30s shutdown phase strictly as an example; in real systems, measure request durations, hook timings, and load-balancer propagation delays.

### 14.2. After Readiness Turns False, Sleep Before `SIGTERM`?

Maintenance workflows sometimes emit `REFUSING_TRAFFIC`, wait for `EndpointSlice`/ingress updates, and then shut down to minimize dropped requests. However, propagation lag is not a fixed constant—it varies with kubelet, kube-proxy/CNI, load balancers, and traffic. **Never toss in an arbitrary `Thread.sleep()`** assuming draining is guaranteed. Use Kubernetes `preStop` hooks per docs while monitoring in-flight connections and retryable errors.

### 14.3. `SIGKILL` Has No Graceful Shutdown

If a container is `OOMKilled`, a node disconnects, or `SIGKILL` hits, Spring lifecycle callbacks and readiness events never execute. Infrastructure must pair health probes with retries, idempotency, queue redelivery, and durable persistence to survive abrupt termination.

## 15. Failure Scenarios and Debugging

| Symptom | Possible cause | Check |
| --- | --- | --- |
| **404 `/actuator/health/liveness`** locally | Probes disabled outside Kubernetes | Enable `management.endpoint.health.probes.enabled=true`. |
| **404 `/livez`, `/readyz`** | `add-additional-paths` off or wrong URL/context path | Check config and main server mappings. |
| **401/403 on probe** | `SecurityFilterChain`, port, or proxy blocking kubelet | Test anonymous request like kubelet; verify matchers and network policy. |
| **`/actuator/health` 503 while `/livez` 200** | Global health has a `DOWN` contributor; liveness stays `CORRECT` | Inspect health groups/indicators; do not restart pods blindly. |
| **`/readyz` 503, `/livez` 200** | `REFUSING_TRAFFIC` or readiness indicator `DOWN` | Check `ApplicationAvailability`, group membership, event emitters. |
| **`/actuator/health/readiness` 200 yet main app port unreachable** | Management on separate port; main connector broken | Probe `/readyz` on main port; check connectors/threads/sockets. |
| **Probe gets connection refused at startup** | Connector not bound yet or Pod bound to loopback | Add `startupProbe`; check `server.address`/port and startup budget. |
| **Pods crash-loop during DB outage** | DB included in liveness or global health used as liveness | Keep liveness independent of external dependencies. |
| **All pods unready when shared DB fails** | Readiness includes shared DB without fallback | Review dependency policy; avoid wiping out entire fleet unnecessarily. |
| **App reports ready too early** | Essential startup work ran async after `ApplicationReadyEvent` | Move required init into runners or manage readiness explicitly. |
| **Unready despite handling requests fine** | `REFUSING_TRAFFIC`, custom indicator `DOWN`, or wrong group | Check published events, custom state, and 503 body/status. |
| **Slow/timing-out health checks** | Indicator hits DB/HTTP without timeout or hits a lock | Simplify check, add timeouts/caching, separate monitoring. |
| **Startup fails on group include** | Nonexistent contributor ID | Verify `HealthIndicator` bean name/registry and fix `include`. |
| **Monitoring screens reveal secrets** | `show-details=always` or sensitive actuator exposed | Restrict details/roles/networks; never log credentials. |
| **K8s liveness passes while 5xx spikes** | Probes test viability, not business SLOs | Track metrics/traces/error budgets and explicit overload signals. |
| **503 in deploy despite 200 locally** | Context path, management port, proxy rewrite, HTTPS mismatch | Curl Pod/main port directly and compare manifest vs. config. |
| **Requests fail after `SIGTERM`** | Load-balancer propagation lag or short grace period | Audit `EndpointSlice`, graceful shutdown, `preStop`, retries. |
| **`MockMvc` passes yet K8s probe 404s** | `MockMvc` skips main connector, packaging, ingress paths | Use `@SpringBootTest(RANDOM_PORT)` and staging Pod checks. |
| **`UNKNOWN` returns 200** | Default status mapper does not map `UNKNOWN` to 503 | Inspect custom status mappings; never guess from status names. |

### 15.1. Ordered Diagnostic Workflow

1. Verify `spring-boot-starter-actuator`, Spring Boot version, and listening ports.
2. Check whether `/actuator/health` returns JSON/status.
3. Verify `probes.enabled`, `add-additional-paths`, and active URLs.
4. Curl `/livez` and `/readyz` directly on the main port; distinguish HTTP 200, 503, 401, 404, and connection refused.
5. Read `ApplicationAvailability` if an internal diagnostic endpoint exists.
6. Check health group `include`s, indicator bean IDs, and slow health checks.
7. Separate `management.server.port` from `server.port`, bind addresses, and proxy routing.
8. Inspect Spring Security permit rules and proxy filters.
9. In Kubernetes, inspect Pod conditions, events, `EndpointSlice`s, and probe failure counters.
10. When readiness fails fleet-wide, evaluate shared dependencies before restarting pods.
11. During shutdown, verify `terminationGracePeriodSeconds`, graceful shutdown, and in-flight connections.
12. Inspect metrics, traces, and business SLOs for issues probes cannot measure.

Never "fix" probe issues by setting **`management.endpoints.web.exposure.include="*"`** on a public interface or disabling security globally.

## 16. Anti-Patterns to Avoid

**1. Using `/actuator/health` for both liveness and readiness.** Global health aggregates DB/Redis, letting a single shared outage restart every replica.

**2. Running heavy `SELECT` queries every 5 seconds inside readiness.** Frequent probes amplify load on an already struggling database. Keep checks lightweight, timed out, and scoped properly.

**3. Enabling a separate `management.server.port` and probing only that port.** Main web traffic can break while management stays UP. Prefer `/livez` and `/readyz` on the main server port.

**4. Treating `readiness=false` as an HTTP firewall.** It isn't. Orchestrators stop routing Service traffic, yet direct Pod IP callers still reach endpoints. Use security and network policies separately.

**5. Publishing `LivenessState.BROKEN` because a partner API timed out.** Restarting the app rarely fixes an upstream outage and risks cascading failures. Use circuit breakers, fallbacks, alerts, and readiness only when appropriate.

**6. Intercepting 503 readiness responses in `@ControllerAdvice` to return 200.** Readiness 503 is a vital operational signal kubelet relies on.

**7. Side-effectful health checks.** Never write to a DB, emit Kafka messages, refresh tokens, or clear caches inside readiness. Probes must be cheap and idempotent.

**8. Leaving demo control endpoints public.** POST endpoints toggling readiness belong strictly to loopback labs; strip or lock them down in production.

**9. Hardcoding every indicator to return `UP` regardless of failure.** Dishonest health endpoints blind orchestration and monitoring; define real acceptance criteria.

**10. Disabling all Actuator security because kubelet got 401.** Write targeted allow rules/paths/network policies rather than exposing `env`, `heapdump`, and `configprops`.

## 17. Hands-On Exercises

### Exercise 1 — Lifecycle Analysis

Draw a timeline from `SpringApplication.run` to `ApplicationReadyEvent`, marking when liveness becomes `CORRECT` and readiness becomes `ACCEPTING_TRAFFIC`. Add an `ApplicationRunner` performing warmup in a lab and observe readiness before startup completes. Explain why HTTP probe listeners may fail to respond during early startup phases.

### Exercise 2 — Readiness vs. Liveness

Run the `demo` profile, `POST /demo/control/refuse`, and compare `/readyz` and `/livez`. Then `POST /demo/control/accept` to verify recovery. Explain why an instance should not be restarted solely because readiness is `REFUSING_TRAFFIC`.

### Exercise 3 — Custom `HealthIndicator`

`POST /demo/control/capacity/off` and observe `/actuator/health`, `/readyz`, `/livez`, and `/demo/availability`. Explain why `ReadinessState` stays `ACCEPTING_TRAFFIC` while the HTTP readiness group returns 503.

### Exercise 4 — Management Port

Add `management.server.port=8081`. Query `/actuator/health/readiness` on 8081 and `/readyz` on 8080. Simulate a misconfiguration affecting only the main port in staging. Explain why management-port probes can yield false positives.

### Exercise 5 — Kubernetes Rollout

Deploy with startup/liveness/readiness probes. Increase legitimate warmup time and tune thresholds so Pods are not restarted prematurely. Inspect Pod `Ready` conditions, rollout strategy, and `EndpointSlice`s. Never enable the `demo` control profile in a cluster.

### Exercise 6 — External Dependency

Suppose all replicas share one Redis cluster while the core feature has a fallback when Redis is `DOWN`. Should Redis be included in readiness? Compare "all pods unready" against "keep serving traffic using fallback". Present separate policies for liveness/readiness and metrics/alerts for Redis outages.

### Exercise 7 — Graceful Shutdown

Enable `server.shutdown=graceful` and send `SIGTERM` during in-flight requests in staging. Observe lifecycle logs, probe transitions, LB draining, and request completion before `terminationGracePeriodSeconds`. Establish SLOs for dropped requests during rollouts and recovery time.

## 18. Pre-Production Checklist

- [ ] Liveness, readiness, startup, and Kubernetes' reactions to each probe are clearly understood.
- [ ] Actuator dependency/health endpoints are present and return proper statuses.
- [ ] Probe groups are enabled for the target environment (`probes.enabled` set if outside Kubernetes).
- [ ] Main server port exposes `/livez` and `/readyz` rather than probing only a separate management port.
- [ ] Probe paths/ports in Kubernetes manifests match `server.servlet.context-path` and active mappings.
- [ ] Liveness does not depend on external services or shared databases.
- [ ] Readiness includes only essential, fast, instance-specific checks.
- [ ] Custom `HealthIndicator` IDs exist and group membership validation remains enabled.
- [ ] `DOWN`/`OUT_OF_SERVICE` return 503 and `UP` returns 200 per verified mappings.
- [ ] `startupProbe` budget covers cold starts, migrations, and bounded warmups.
- [ ] Readiness is not blocked by auth/session cookies while sensitive Actuator endpoints stay protected.
- [ ] Kubelet can reach the Pod IP/main port (not accidentally bound to `127.0.0.1`).
- [ ] Both management and main ports have explicit network and security policies.
- [ ] Graceful shutdown and `terminationGracePeriodSeconds` are measured and coordinated.
- [ ] No demo readiness toggle endpoints exist in production builds/profiles.
- [ ] Probes have zero side effects, log no secrets, and expose no internal details.
- [ ] Both 200 and 503 are tested over real HTTP, plus startup/shutdown behavior in staging.
- [ ] Metrics/logs/traces monitor scenarios where `/readyz` returns 200 while business APIs fail.
- [ ] A shared external dependency outage will not trigger fleet-wide restarts.
- [ ] Runbooks distinguish 401, 404, 503, connection refused, and timeouts.

## 19. Self-Check Questions

**1. Does a readiness failure cause Kubernetes to restart the Pod?** No; readiness primarily removes the Pod from Service endpoints, whereas liveness or startup probe failures trigger restarts per policy.

**2. Should liveness always check the database?** No. DB outages are usually external; restarting all app replicas risks cascading failure.

**3. When does Boot transition readiness to `ACCEPTING_TRAFFIC`?** After `SpringApplication` finishes runners and publishes `ApplicationReadyEvent` followed by the availability change event.

**4. If `/actuator/health` returns 503, does `/livez` also return 503?** No. Global health includes DB/custom contributors while the liveness group stays independent.

**5. What is the risk of setting `management.server.port` different from the main server port?** Management-port health can report success even while the main web connector is broken.

**6. What does `add-additional-paths=true` do?** Exposes `/livez` and `/readyz` health probes on the main server port in Boot 3.3.

**7. Can `ReadinessState.ACCEPTING_TRAFFIC` coincide with `/readyz` returning 503?** Yes, when the readiness group includes a custom `HealthIndicator` that is `DOWN`.

**8. Does `UNKNOWN` health status always return 503?** Not under default status mapping; unmapped statuses including `UNKNOWN` typically return HTTP 200.

**9. Why isn't `MockMvc` sufficient for testing this setup?** It bypasses the real servlet connector, ports, and network routing; `@SpringBootTest(RANDOM_PORT)` HTTP integration tests are needed.

**10. What is `startupProbe` used for?** It lets slow-starting apps finish initializing before liveness/readiness probes begin; once it succeeds, the other two probes take over.

## 20. Official Documentation

1. [Spring Boot 3.3 — Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): health groups, `probes.enabled`, `add-additional-paths`, main vs. management port, status mappings, liveness/readiness.
2. [Spring Boot 3.3 — SpringApplication and Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): startup events, `LivenessState`, `ReadinessState`, `ApplicationAvailability`, `AvailabilityChangeEvent`.
3. [Spring Boot 3.3 — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html): actuator `base-path`, management port/address, web app runtime.
4. [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): `server.shutdown=graceful` and lifecycle shutdown timeouts.
5. [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest(RANDOM_PORT)`, `TestRestTemplate`, and integration tests.
6. [Kubernetes — Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#container-probes): kubelet probe mechanics and Pod lifecycle.
7. [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): manifest fields and probe timings.
8. [Spring Boot 3.3 — Actuator Health API](https://docs.spring.io/spring-boot/3.3/actuator-api/htmlsingle/#health): HTTP health status and response contract.

**Conclusion:** to connect Actuator with the web runtime, treat **liveness** as whether the process can still function properly and **readiness** as whether **this instance** should accept new traffic. Spring Boot tracks both via **`ApplicationAvailability`**, Actuator exposes them as **health groups**, and Kubernetes drives restarts and traffic routing from those probes. Expose **`/livez` and `/readyz` on the main HTTP port** where appropriate, keep external databases out of liveness, keep custom readiness checks lightweight, and verify both **HTTP 200 and 503** against a real runtime.