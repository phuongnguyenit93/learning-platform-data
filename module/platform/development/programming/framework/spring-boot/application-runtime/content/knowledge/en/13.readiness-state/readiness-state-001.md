# Distinguishing Liveness, Readiness, and Network Port Availability

## 1. Three Irreplaceable Questions

When a Spring Boot application is running, the three questions below belong to three different layers:

1. **Liveness:** Is the application still in an internal state where it can work or self-recover? If the internal state cannot recover, should the instance be restarted?
2. **Readiness:** Should the instance **be sent new requests right now**? It may be loading data, temporarily overloaded, or undergoing a controlled shutdown, even while the process is still alive.
3. **Network port availability:** Has the web server bound/listened on the TCP port yet, and can a client connect from its location to the right host, port, and protocol?

An instance can have **liveness = CORRECT** but **readiness = REFUSING_TRAFFIC** while Spring Boot is running an `ApplicationRunner`. It can also have initialized the web server on `8080` without having reached the ready milestone yet. Conversely, a successful TCP connect does not prove that controllers can handle requests or that business data is ready.

> **An open port does not mean ready; live does not mean ready; a health endpoint returning 200 does not by itself prove that all APIs and dependencies are healthy.**

This article applies to Spring Boot 3.3.x, Spring Framework 6.1.x, and Java 17+; it specifically explains `ApplicationAvailability`, Actuator probes, and Kubernetes routing.

## 2. Semantic Distinction Table

| Signal | Question Answered | Common Values/APIs | What Does the System Typically Do? |
| --- | --- | --- | --- |
| **Liveness** | Is the instance's internal state valid and free of unrecoverable corruption? | `LivenessState.CORRECT` / `BROKEN` | Kubernetes may restart the container after the liveness probe fails past its threshold |
| **Readiness** | Does the instance want to receive new traffic right now? | `ReadinessState.ACCEPTING_TRAFFIC` / `REFUSING_TRAFFIC` | Kubernetes typically removes the instance from traffic-receiving endpoints when the readiness probe fails |
| **TCP bind/listen** | Is a socket at an address/port ready to accept connections? | `server.address`, `server.port`, embedded web server | Diagnoses sockets, firewalls, NAT, Service targetPort |
| **HTTP response** | Can a route return a response? | `/ping`, controller, Actuator health | Checks the ability to handle a single HTTP endpoint |
| **Business readiness** | Does an essential operation satisfy the business contract? | HealthIndicator, synthetic transaction, SLO | Drives fallback, alerts, and traffic routing by design |

**Liveness** should describe internal failures that a restart is likely to resolve; by default, it should not depend on external databases, caches, brokers, or HTTP APIs. If a shared dependency breaks, restarting all replicas en masse can cause a cascading failure.

**Readiness** represents "send me new traffic or not yet", not "I am dead". An instance that is not ready can still run background work or prepare to recover.

**Port** is a socket/infrastructure state. Having a TCP connection does not guarantee an HTTP endpoint returns 200; an HTTP 200 from `/ping` likewise does not guarantee `/actuator/health/readiness` returns UP.

## 3. Spring Boot's ApplicationAvailability

Spring Boot 3.3 provides an `ApplicationAvailability` bean that supplies the current availability state:

```java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;

// Inside a Spring bean with ApplicationAvailability availability injected:
LivenessState liveness = availability.getLivenessState();
ReadinessState readiness = availability.getReadinessState();
```

This is an **illustrative snippet**, not a standalone Java file; `availability` must be injected by Spring.

`LivenessState` has `CORRECT` and `BROKEN`; `ReadinessState` has `ACCEPTING_TRAFFIC` and `REFUSING_TRAFFIC`. These values are **runtime state information**; they do not automatically open/close network ports or reconfigure the entire load balancer on their own. To make them externally observable, you need an exposure mechanism such as Actuator health groups and an orchestrator that actually reads the probes.

While an application is starting up, Boot considers liveness not yet reached until the context refreshes and Boot publishes the corresponding state. That does **not** mean "not yet live" is necessarily a fault requiring an immediate restart: Kubernetes startupProbe/liveness probe thresholds determine when to act.

## 4. Timeline: Started Is Different from Ready

For the standard Spring Boot 3.3.x startup flow:

```text
SpringApplication.run(...)
   |
   +--> Prepare Environment, create ApplicationContext
   +--> Load bean definitions, refresh context
   |       +--> web server initialization if this is a web application
   |       +--> WebServerInitializedEvent/ContextRefreshedEvent
   |
   +--> log "Started ..." if startup INFO is enabled
   +--> ApplicationStartedEvent
   +--> AvailabilityChangeEvent(LivenessState.CORRECT)
   |
   +--> ApplicationRunner / CommandLineRunner
   |       (work that must complete before ready)
   |
   +--> ApplicationReadyEvent
   +--> AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
   +--> return ApplicationContext
```

**Started milestone:** The context has refreshed; `ApplicationStartedEvent` occurs **before** runners. Spring Boot publishes `LivenessState.CORRECT` immediately **after** the started event.

**Ready milestone:** Boot has finished invoking all runners successfully; `ApplicationReadyEvent` occurs **after** runners. Boot publishes `ReadinessState.ACCEPTING_TRAFFIC` immediately **after** the ready event.

Therefore, when code is executing inside an `ApplicationReadyEvent` listener, reading the readiness value immediately will not necessarily show `ACCEPTING_TRAFFIC`: the event that updates the state in standard order arrives **after** the ready event. To observe the state transition, listen for `AvailabilityChangeEvent<ReadinessState>` or read it after `SpringApplication.run(...)` returns.

The log line `Started ExampleApplication in ... seconds` does not prove that runners have completed. It is not synonymous with readiness UP. `WebServerInitializedEvent` is also not `ApplicationReadyEvent`.

### 4.1. State by Phase

| Phase | Liveness | Readiness | HTTP/server |
| --- | --- | --- | --- |
| **Starting** (before refresh) | `BROKEN` in the lifecycle model before the live milestone | `REFUSING_TRAFFIC` | Server/probe may not be reachable yet |
| **Started** (after refresh, handling startup) | `CORRECT` | `REFUSING_TRAFFIC` | Web server may have bound, but is not considered traffic-ready |
| **Ready** (after runners) | `CORRECT` | `ACCEPTING_TRAFFIC` | Ready to receive routed traffic when probes and infrastructure agree |
| **Graceful shutdown** | May still be `CORRECT` | `REFUSING_TRAFFIC` | Typically stops accepting new requests, finishes in-flight requests depending on configuration |
| **Shutdown complete** | Instance no longer running | Instance no longer running | Port/server has stopped |

HTTP connector conditions and probe response capability can vary by phase, web server, network, and deployment setup. This table describes **availability states**, not a guarantee that every TCP attempt at every milestone will receive an HTTP response.

### 4.2. When a Runner Fails or Runs in the Background

If a runner throws an exception outward, Boot handles the startup failure; the success-path `ApplicationReadyEvent` is not published, and the context/server may be closed. The fact that a port was bound before the error does not prove that startup ultimately succeeded.

If a runner starts an asynchronous task and returns immediately, Boot **does not automatically wait for that Future/thread**. If the preparation is mandatory, you must explicitly wait for the result or design a dedicated readiness gate; otherwise, Boot may transition to ready too early.


## 5. Distinguishing Socket, HTTP, and Readiness

An "open" network port is the result of multiple independent steps:

```text
Spring Boot selects web application type
   -> Web server is created / server.port configured
   -> OS binds/listens on address:port
   -> Network path from client to port works?
   -> HTTP connector accepts and processes request?
   -> Controller/filter/Actuator health returns response?
   -> Is readiness health group UP?
   -> Does actual business logic succeed?
```

Common examples:

- Configuring `server.port=8080` does **not** guarantee binding succeeds: the port may already be occupied by another process.
- A successful TCP handshake to 8080 only confirms that a socket can accept connections; it does not prove that data has been preloaded or that repositories are working.
- HTTP `404 Not Found` may indicate the server is processing requests, but the path you called is wrong; it gives no readiness information yet.
- HTTP `200 OK` on `/ping` only tests a single route. If `/ping` always returns `pong`, it does not check the database or required datasets.
- `/actuator/health/readiness` returning `UP` is meaningful **within the scope of the health indicators configured in this group**, not for all business operations.
- `Connection refused` or a timeout can happen because the server has not started, due to a firewall, wrong port, NetworkPolicy, Service/Ingress, or shutdown; you cannot immediately conclude `LivenessState.BROKEN`.
- The web server is initialized during context refresh and may become visible before runners complete, while readiness is still `REFUSING_TRAFFIC`.

When TCP connect succeeds and when an HTTP request can be handled mid-startup are also affected by the connector lifecycle; **it is not guaranteed that you will always receive HTTP 503 while a runner is executing**. If the HTTP endpoint is not yet capable of accepting requests, the client may receive no HTTP response at all.

### 5.1. Commonly Confused Addresses/Ports

- `server.address=127.0.0.1` binds on loopback: clients outside the host/container cannot connect even when `ApplicationAvailability` is ready.
- `server.port=8080` is the application port; `management.server.port=8081` (if configured) is the Actuator port and can be separate. The two connectors may not be in the same state.
- Docker `EXPOSE` does not mean the port is published to the host; container networking must still be configured.
- Kubernetes `containerPort`, Service `targetPort`, selectors, EndpointSlice, NetworkPolicy, and Ingress must all be correct. Readiness UP inside a Pod does not fix a misconfigured network path.
- TLS termination and proxies can cause clients to see different errors than direct access to the Pod.
- Testing from `localhost` on the machine running the app is not the same as a request from another Pod or from the Internet.

## 6. Actuator Liveness/Readiness Probes

When the `spring-boot-starter-actuator` dependency is present and the probe health groups are enabled/exposed over the web, Spring Boot 3.3 provides:

```text
GET /actuator/health/liveness
GET /actuator/health/readiness
```

The two primary indicators are `LivenessStateHealthIndicator` and `ReadinessStateHealthIndicator`, reflecting state from `ApplicationAvailability`.

In Kubernetes, Spring Boot can automatically enable these health groups when it detects a Kubernetes environment. To enable them explicitly **in local environments as well**:

```properties
management.endpoint.health.probes.enabled=true
```

Ensure that the Actuator dependency, HTTP exposure, and security are compatible. Without Actuator, declaring paths in Kubernetes does not create endpoints automatically.

### 6.1. Common HTTP Status Mapping

| State | Default Health Status | Typical HTTP Status |
| --- | --- | --- |
| `LivenessState.CORRECT` | `UP` | `200 OK` |
| `LivenessState.BROKEN` | `DOWN` | `503 Service Unavailable` |
| `ReadinessState.ACCEPTING_TRAFFIC` | `UP` | `200 OK` |
| `ReadinessState.REFUSING_TRAFFIC` | `OUT_OF_SERVICE` | `503 Service Unavailable` |

This is the default health status mapping in the corresponding configuration; it can be customized via `management.endpoint.health.status.http-mapping.*` and health-group status mapping. **Receiving no HTTP response** is completely different from **receiving an HTTP 503 response**.

### 6.2. Additional Probe Paths on the Main Port

If Actuator runs on a separate management port, probes on the management port may return 200 even while the main HTTP port is failing. To check health on the **same main port**, Boot 3.3 supports:

```properties
management.endpoint.health.probes.add-additional-paths=true
```

When enabled, default additional paths are added:

```text
GET /livez
GET /readyz
```

These paths are created on the **main server port**. For example, with `server.port=8080` and `management.server.port=8081`, a request to `http://localhost:8080/readyz` checks readiness through the main connector. A health group can also declare a custom path such as `management.endpoint.health.group.readiness.additional-path=server:/ready-check`.

Additional paths help prevent "management port healthy, main port broken", yet still do not guarantee that every controller or business transaction is healthy. Additional end-to-end checks must be used if operational requirements call for them.


## 7. Runnable Java 17+ / Spring Boot 3.3.13 Example

The goal of this experiment is to demonstrate that **the server already has a port inside the runner and liveness is CORRECT, yet readiness is still REFUSING_TRAFFIC**; only after the runner finishes does Boot transition readiness to ACCEPTING_TRAFFIC.

### 7.1. build.gradle

Gradle Groovy project with Gradle Wrapper, using Java 17:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
```

File `settings.gradle`:

```groovy
rootProject.name = 'availability-port-lab'
```

Create `src/main/resources/application.properties`:

```properties
server.port=8080
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=WARN

management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
```

The example assumes port `8080` is free. If it is already in use, choose another port and update the verification commands accordingly.

### 7.2. Complete Java Code in One File

Create `src/main/java/com/example/availability/AvailabilityPortLabApplication.java`:

```java
package com.example.availability;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AvailabilityPortLabApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(AvailabilityPortLabApplication.class, args);

        ApplicationAvailability availability =
                context.getBean(ApplicationAvailability.class);

        System.out.println("07 main: liveness=" + availability.getLivenessState()
                + ", readiness=" + availability.getReadinessState());
    }

    @EventListener
    public void started(ApplicationStartedEvent event) {
        System.out.println("01 ApplicationStartedEvent");
    }

    @Bean
    ApplicationRunner warmUp(ApplicationAvailability availability,
                             ServletWebServerApplicationContext context) {
        return args -> {
            System.out.println("02 runner: port=" + context.getWebServer().getPort());
            System.out.println("03 runner: liveness=" + availability.getLivenessState());
            System.out.println("04 runner: readiness=" + availability.getReadinessState());
            Thread.sleep(2500);
        };
    }

    @EventListener
    public void ready(ApplicationReadyEvent event) {
        System.out.println("05 ApplicationReadyEvent");
    }

    @EventListener
    public void readinessChanged(AvailabilityChangeEvent<ReadinessState> event) {
        if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
            System.out.println("06 readiness=ACCEPTING_TRAFFIC");
        }
    }

    @RestController
    public static class PingController {
        @GetMapping("/ping")
        public String ping() {
            return "pong";
        }
    }
}
```

Explanation:

- `spring-boot-starter-web` starts embedded Tomcat (the default for Spring MVC) during context refresh.
- `ServletWebServerApplicationContext#getWebServer().getPort()` reads the server port at the moment the runner executes after refresh. Having a port does not by itself prove readiness.
- `ApplicationAvailability` can be injected like a normal bean; inside the runner, liveness is already `CORRECT` while readiness has not yet transitioned to `ACCEPTING_TRAFFIC`.
- `@EventListener(ApplicationReadyEvent)` only prints a marker; accepting readiness is published via `AvailabilityChangeEvent` **after** the ready event.
- `Thread.sleep(2500)` is a simulated delay, not a production pattern for waiting on dependencies.
- `/ping` only returns the string `pong`, not a readiness probe.
- Because this is a web application, do not close `ApplicationContext` immediately after `run`: the server must keep running to serve traffic.

### 7.3. Run and Compare stdout

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

When there are no other custom listeners, the lines **explicitly printed by the Java code** appear in order:

```text
01 ApplicationStartedEvent
02 runner: port=8080
03 runner: liveness=CORRECT
04 runner: readiness=REFUSING_TRAFFIC
05 ApplicationReadyEvent
06 readiness=ACCEPTING_TRAFFIC
07 main: liveness=CORRECT, readiness=ACCEPTING_TRAFFIC
```

Gradle/logs may add other lines; compare only the lines starting with numbers. Lines 02 and 04 directly demonstrate the difference between "the port has been initialized by the server" and "ready".

### 7.4. HTTP After the Application Is Ready

Open a second terminal after line 07:

```bash
curl -i http://localhost:8080/ping
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
```

Results under the default configuration:

- `/ping` returns HTTP 200 with body `pong`.
- `/livez` and `/actuator/health/liveness` return status `UP`, HTTP 200.
- `/readyz` and `/actuator/health/readiness` return status `UP`, HTTP 200.

Try calling `/readyz` while the runner is sleeping. If the connector is already able to process requests, the health endpoint typically reflects readiness `OUT_OF_SERVICE` with HTTP 503. However, under specific configurations or timing windows, the request may fail to connect or not yet be handled; do not assume "always seeing 503 before ready" is a guarantee of every web server.

### 7.5. When the Runner Throws

If you replace `Thread.sleep(2500)` with:

```java
throw new IllegalStateException("Mandatory data unavailable");
```

then the runner causes startup to fail: the success-path `ApplicationReadyEvent` and `ReadinessState.ACCEPTING_TRAFFIC` **do not occur**, `SpringApplication.run` does not return normally, and line `07 main` does not appear. The web server/context is typically closed by Boot during failure handling, even though a server start log may have been printed earlier.


## 8. Kubernetes Probes: Right Purpose, Right Action

Kubernetes distinguishes:

- **`livenessProbe`:** If it fails repeatedly up to the threshold, kubelet can restart the container. Suitable when internal state cannot self-recover.
- **`readinessProbe`:** When the probe fails, the Pod/instance is marked not ready and is removed from receiving traffic via the corresponding Kubernetes Service. It does not restart by default just for lacking readiness.
- **`startupProbe`:** When configured, it protects a slow startup phase from being evaluated too early by liveness/readiness probes. While the startup probe has not succeeded yet, the other probes do not run under the startup probe mechanism; if the startup probe fails up to its limit, the container can be restarted.

An illustrative container YAML snippet using `/livez` and `/readyz` on the main port:

```yaml
containers:
  - name: availability-port-lab
    image: example/availability-port-lab:1.0
    ports:
      - containerPort: 8080
    startupProbe:
      httpGet:
        path: /livez
        port: 8080
      periodSeconds: 5
      failureThreshold: 30
    livenessProbe:
      httpGet:
        path: /livez
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /readyz
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 3
```

This is a **sample configuration snippet** inside a Pod/Deployment, not a complete Deployment YAML. The image `example/availability-port-lab:1.0` is only an illustrative name. `periodSeconds`, `failureThreshold`, and `timeoutSeconds` must be tuned for startup time and operational needs.

When using `startupProbe`, note that `/livez` can succeed right after context refresh, before runners complete; however, `readinessProbe` still guards traffic delivery until startup finishes. For applications without long startups, `startupProbe` is not always necessary.

Kubernetes only removes a Pod from Service routing when readiness is used. A client calling the **Pod IP directly** can bypass that routing. If all Pods are unready, the response from a Service/Ingress/load balancer also depends on the implementation; sometimes it is a connection failure, sometimes the proxy returns 503. Do not attribute every situation to "Spring Boot returned 503".

## 9. External Dependencies: When to Include in Readiness/Liveness?

Suppose 20 Spring Boot replicas share one database. The database loses connectivity for 30 seconds; the replicas can still retry or use a cache/fallback—only the external dependency is disrupted.

If the **liveness probe** depends on the DB, all replicas may be restarted one after another, causing connection pools and warm-up load to hit the database simultaneously. This is a **cascading failure**. Therefore, Spring Boot documentation recommends not tying external system checks into liveness by default.

For **readiness**, decide according to the contract:

1. If a dependency is **mandatory for every request** with no fallback, consider removing the instance from traffic when the dependency fails.
2. If a dependency is **optional**, with proper circuit breakers/fallbacks, do not take the instance out of service.
3. If a dependency is **per-instance**, a readiness indicator can help isolate just the affected instance.
4. If a dependency is **shared by all replicas**, marking all of them unready can leave the entire service with zero endpoints even when some operations could still work. Evaluate the trade-off against the business contract.

Spring Boot 3.3 **does not automatically add every database, cache, or API HealthIndicator to the readiness/liveness groups**. By default, probe groups rely on their corresponding state. To add a custom HealthIndicator named `catalog` to readiness, you can use:

```properties
management.endpoint.health.group.readiness.include=readinessState,catalog
```

This is a **pattern that depends on already having a HealthIndicator named catalog**; the configuration does not generate the indicator itself. Custom checks should have short timeouts, avoid unbounded I/O, and avoid placing heavy load on the system during an incident.

### 9.1. Do Not Use Port-Open Instead of a Health Endpoint

A TCP probe only proves TCP handshake capability. For liveness/readiness states managed by Spring Boot, use the corresponding HTTP probes. You can supplement them with synthetic checks through controllers/services if the true requirement is measuring the end-to-end request path, but do not put expensive checks into liveness every few seconds.

## 10. Application Proactively Changing ReadinessState

An application can update availability state after startup—for example, taking itself out of traffic when an internal queue is full or a mandatory component needs recovery time. Spring Boot supports publishing `AvailabilityChangeEvent`:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;

// Inside a Spring bean with ApplicationEventPublisher publisher injected:
AvailabilityChangeEvent.publish(
        publisher, this, ReadinessState.REFUSING_TRAFFIC);
```

When the condition recovers and **true readiness has been verified**:

```java
AvailabilityChangeEvent.publish(
        publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
```

These snippets are **illustrative and require real classes/fields**. Publishing a readiness event **does not close/open sockets**; the health group reflects the new state when queried, and then Kubernetes/the LB observes it on its probe schedule and updates routing. There can be a delay between the event and the routing change.

Avoid having multiple modules independently publish conflicting states, because newer changes can overwrite earlier decisions. If readiness depends on multiple conditions, have a single owner aggregate the state.

Only use `LivenessState.BROKEN` for genuinely unrecoverable internal states where a restart can fix the issue. Do not mark BROKEN merely because an external API returned a transient error.

## 11. Graceful Shutdown and Readiness

An instance can stay **live** to finish in-flight requests while switching readiness to `REFUSING_TRAFFIC` to avoid receiving new requests when the deployment is terminating it.

In a Spring Boot web server application that supports graceful shutdown, you can configure:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Handling in-flight requests and rejecting new ones depends on the embedded server type, Kubernetes termination grace period, `preStop` configuration, and proxy behavior. Once the server has stopped accepting requests, probes may receive no HTTP response even though the application updated readiness internally.

`SIGKILL` or crashes do not guarantee cleanup callbacks run; the system still needs appropriate timeouts, retries, and idempotency.

## 12. Checklist When "Started but Receiving No Traffic"

1. Which **host, Pod, namespace, and port** are right? Main port or management port?
2. Did the context refresh while a runner has not finished? Was `ApplicationStartedEvent` fired without `ApplicationReadyEvent` yet?
3. Is `ApplicationAvailability` currently `CORRECT/REFUSING_TRAFFIC` or `CORRECT/ACCEPTING_TRAFFIC`?
4. Is the Actuator dependency present, probe group enabled, and HTTP endpoint exposure/security configured properly?
5. What HTTP status do `/actuator/health/readiness` or `/readyz` on the main port return? If unreachable, check networking first.
6. Is the port bound to the right interface? Are Docker port publishing, Kubernetes Service selectors, targetPort, EndpointSlice, and NetworkPolicy correct?
7. If the management port returns 200, is the main port actually accepting requests? Are additional paths on the main port needed?
8. Has Kubernetes added the Pod to Endpoints yet? Are probe period/threshold and propagation delay causing a lag?
9. Which contributors are in the readiness health group? Is a dependency check slow, timing out, or flapping?
10. Is the instance currently in graceful shutdown, draining, or having just received SIGTERM?
11. If port/connectivity/health are all fine but clients still fail, check the actual HTTP route, auth, reverse proxy, DNS, TLS, and business logic.
12. If a runner launched a background task and returned, did readiness go up too early?

**Do not draw conclusions from a single metric.** Combining the event timeline, Boot state, HTTP probes, TCP sockets, Service routing, and one minimal business request will pinpoint the failure at the right layer.

## 13. Common Misconceptions

| Claim | Why Is It Inaccurate? |
| --- | --- |
| "8080 is open so the app is ready" | A port carries no information about runners or readiness state |
| "Liveness is CORRECT so the DB must be healthy" | Liveness reflects internal state and normally does not check the DB |
| "Readiness false means we must restart" | It only indicates traffic should temporarily stop being sent |
| "/ping returns 200 so the app is ready" | A simple ping may not verify business preconditions |
| "Management port is UP so main port is UP" | The two connectors can fail independently |
| "Kubernetes always returns 503 when unready" | Service/Ingress may produce connection errors or responses depending on implementation |
| "Probes are auto-created just from Kubernetes YAML" | Spring must actually have the endpoint and proper HTTP exposure |
| "@EventListener(ApplicationStartedEvent) reads readiness accepting" | Started comes before runners; readiness accepting comes after ready |
| "@Async runner finished means background data is loaded" | The runner can return before the background task completes |
| "Enabling startupProbe means readinessProbe is unnecessary" | Startup and readiness serve different purposes |
| "Every dependency must be put into liveness" | Easily triggers mass restarts and cascading failures |
| "/readyz UP guarantees no API will fail" | A health group has a specific check scope and does not cover the whole system |
| "A readiness event makes the OS close the TCP port" | The event changes state; routing must be handled by infrastructure |
| "If a port is bound, external clients can always reach it" | Bind interface, firewall, proxy, and Service routing can still be wrong |

## 14. Self-Check

**Q1:** An application has refreshed its context, but a runner is preloading data for 10 seconds. What are liveness/readiness?

**A:** Along the default startup path after the started event: `CORRECT` and `REFUSING_TRAFFIC`. The port may already be initialized, but the ready milestone has not been reached.

**Q2:** Why does a TCP connect to 8080 succeed while readiness is still not reached?

**A:** A TCP connection verifies the socket, not that runners have finished or that the health group is `UP`.

**Q3:** When a readiness probe fails, does Kubernetes necessarily restart the Pod?

**A:** No; readiness normally controls routing. Liveness/startup probes are what tie to restart policies when failures exceed thresholds.

**Q4:** Should an optional Redis cache be used as a liveness check?

**A:** Usually no. An external Redis failure does not mean the instance lost its ability to self-recover; restarting can cause cascading failures.

**Q5:** How do you check readiness on the main port when Actuator uses a separate management port?

**A:** Enable `management.endpoint.health.probes.add-additional-paths=true`, check `/readyz` on the main port, and ensure security/networking allow the probe.

**Q6:** After `ApplicationReadyEvent`, which availability event does Boot publish?

**A:** `AvailabilityChangeEvent` with `ReadinessState.ACCEPTING_TRAFFIC` on the successful startup path.

**Q7:** If the application publishes `ReadinessState.REFUSING_TRAFFIC` itself, does the port close automatically?

**A:** No. This is internal state; infrastructure observes the probe and adjusts routing according to its configuration.

**Q8:** If all Pods are unready, is it guaranteed that Spring Boot itself returns 503?

**A:** No. Service/Ingress/proxies may have no endpoint to connect to; HTTP behavior depends on the proxy type and network deployment.

## 15. Takeaways and Official Documentation

- **Liveness:** `CORRECT/BROKEN` — internal state; restarting is only helpful for unrecoverable errors.
- **Readiness:** `ACCEPTING_TRAFFIC/REFUSING_TRAFFIC` — whether new requests should be received.
- **Network port:** server/socket/network path; **an open port does not prove ready**.
- **Boot 3.3 order:** context refresh → started → liveness correct → runners → ready → readiness accepting.
- **Actuator:** health groups `/actuator/health/liveness` and `/actuator/health/readiness`; enable explicitly with `management.endpoint.health.probes.enabled=true` when needed.
- **Main port:** `management.endpoint.health.probes.add-additional-paths=true` creates `/livez` and `/readyz`.
- **Kubernetes:** liveness failures can restart, readiness failures pull traffic; startupProbe protects slow startups.
- **External dependencies:** avoid putting them in liveness; weigh readiness based on criticality, fallback capability, and cluster-wide impact.

Official documentation for Spring Boot **3.3.13**:

- [SpringApplication — Application Availability and Events](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html).
- [Actuator Endpoints — Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).
- [API — ApplicationAvailability](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html).
- [API — LivenessState](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/LivenessState.html).
- [API — ReadinessState](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ReadinessState.html).

To diagnose "the application is still running but not receiving requests", separate **process/liveness**, **startup/readiness**, **port/network**, **HTTP endpoint**, and **business contract**. Each layer has different causes and remedies.
