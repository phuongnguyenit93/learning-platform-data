# Enabling Graceful Shutdown and Stopping New Requests

> **Module:** Spring Boot – web-runtime → **Graceful Shutdown**. This Knowledge article focuses on the HTTP server **graceful shutdown** mechanism and orchestrating **stopping new request acceptance while continuing to finish in-flight requests** within a finite time window. Examples are accurate for **Java 17+, Spring Boot 3.3.x (e.g., 3.3.13), Spring Framework 6.1.x**. Infrastructure sections outside the JVM illustrate Docker, Kubernetes, and load balancers. Do not equate stopping HTTP with canceling or completing all background jobs, database transactions, or connections from other systems.

## 1. Learning objectives

After completing this lesson, you can:

1. Explain how **immediate shutdown** differs from **graceful shutdown** and **traffic draining**, including the states of serving, stopping new intake, waiting for in-flight requests, and closing resources.
2. Enable graceful shutdown in Spring Boot **3.3** using `server.shutdown=graceful` and configure `spring.lifecycle.timeout-per-shutdown-phase` with an appropriate time unit.
3. Understand that Spring Boot triggers shutdown when `ApplicationContext` closes, at a very early phase of stopping `SmartLifecycle` beans, rather than expecting any arbitrary HTTP endpoint call to shut down the JVM automatically.
4. Distinguish Jetty, Reactor Netty, Tomcat, and Undertow when rejecting new requests: the first three stop accepting at the network layer, while Undertow may return **HTTP 503**; do not promise the same status across all servers/clients.
5. Distinguish `SIGTERM`, `SIGKILL`, EOF, IDE Stop, `kill -9`, Docker stop, and Kubernetes Pod termination.
6. Use `spring-boot-starter-actuator`, `/actuator/health/readiness`, and `/readyz` properly so the orchestrator **stops sending traffic before the process disappears**; do not confuse readiness with liveness.
7. Allocate `terminationGracePeriodSeconds` across **preStop + network deregistration + Spring graceful drain + other lifecycle phases + margin**, since these intervals are not independent.
8. Create a **runnable Java 17+ Maven project**, send a slow request, deliver a TERM signal properly, and observe old requests completing while new requests are rejected.
9. Test zero/low-downtime rolling deployments, persistent connections, HTTP/2, SSE, WebSocket, async jobs, cleanup, and grace-period expiration scenarios.
10. Identify and fix common errors: failing to forward TERM to PID 1, setting the property on the wrong Boot version, confusing health endpoints with closing the connector, infinite `@PreDestroy` sleeps, timeouts exceeding the grace period, or breaking idempotency.

## 2. Why is graceful shutdown needed?

Web applications rarely stop only when there is zero traffic. Real-world scenarios include:

- Deploying a new version via rolling update: old instances are replaced while still serving users.
- Kubernetes scale-down/eviction, node drain, autoscaling, and maintenance.
- Docker or systemd sending a stop signal to the process.
- Operators restarting to fix issues or update configurations, certificates, or connections.
- Health/liveness policies causing the orchestrator to decide to restart a Pod.
- Systems crashing due to errors or `SIGKILL`/OOM: some cases **have no opportunity for graceful shutdown**.

Suppose A is processing a customer's `POST /orders` taking 6 seconds, while B sends `GET /health`. If the JVM is killed immediately, A may lose its TCP connection/response, causing the user to see an error even though the transaction committed; if the server keeps accepting new requests until the process dies, the number of interrupted requests grows.

**Ideal goal of graceful shutdown:**

~~~text
t0: Application healthy, accepting traffic
    |
t1: Receives graceful shutdown signal (TERM / context close)
    |
t2: Begins rejecting / requesting routing to stop sending new requests to this instance
    |
t3: Requests already genuinely accepted before t2 get a chance to complete
    |    (within the configured waiting window)
    |
t4: Remaining components terminate, resources are released
    |
t5: Process exits; orchestrator may terminate if grace period is exceeded
~~~

Situations **that cannot be guaranteed**: if a request runs forever, hangs on the database, the browser gives up, or the process runs out of memory, not every request will succeed. Graceful shutdown only provides **a finite drain window**, not a promise of absolute success or exactly-once processing.

## 3. Three terms to distinguish

| Term | Meaning | What it does **not** guarantee |
|---|---|---|
| **Graceful shutdown** | Stop accepting new requests, give accepted requests time to finish, then stop the app | Does not guarantee handling all background jobs or infinite streams |
| **Traffic draining / deregistration** | Load balancer/ingress/service discovery stops picking the instance for **new traffic** | Does not automatically close listeners or cancel work inside the JVM |
| **Grace period** | Allowed waiting window before forced stop/closing a phase | Not a per-HTTP-request timeout or a client SLA |
| **Readiness** | Is the instance ready to accept new traffic? | Not whether the process is alive or dead |
| **Liveness** | Does the process need to be restarted because it is unhealthy? | Should not be equated with a temporary dependency unavailability |
| **In-flight request** | HTTP request already accepted by the instance and currently being processed | Not all related work resides inside the HTTP connector |
| **Graceful completion** | Request finishes within the window and response is returned if client is still connected | Does not prove side effects roll back if the client timed out |
| **Hard termination** | `SIGKILL`/power loss/OOM or force stop | Does not run full lifecycle callbacks |

**Readiness and closing the connector are two complementary layers of defense.** Marking not-ready helps the LB avoid sending more requests once routing updates; the Spring Boot web server can stop accepting requests directly. Because LB propagation is asynchronous, there is a race window between “LB still thinks it's healthy” and “server has stopped accepting”.

## 4. How Spring Boot 3.3 enables graceful shutdown

Minimal configuration:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Equivalent YAML:

~~~yaml
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

**Version-specific note:** **Spring Boot 3.3** documentation instructs enabling via `server.shutdown=graceful`; do not take the “graceful enabled” default from newer Spring Boot branch docs and back-project it onto Boot 3.3. If immediate shutdown is desired, there is `server.shutdown=immediate`; this lesson intentionally uses `graceful`.

### Meaning of the two properties

- `server.shutdown=graceful`: chooses **graceful** when closing the embedded web server and application context under normal lifecycle shutdown.
- `spring.lifecycle.timeout-per-shutdown-phase=20s`: up to **20 seconds per SmartLifecycle shutdown phase**; Spring Boot uses this timeout for the graceful web shutdown phase. Do not call it **an exact 20-second total process timeout** when other phases or cleanup exist.
- `server.port`, `server.tomcat.connection-timeout`, and `server.tomcat.keep-alive-timeout` do not replace these properties. Connector/keepalive timeouts apply to other HTTP network stages.
- Spring Boot documentation states that shutdown is part of closing `ApplicationContext` and runs in an **early phase** of stopping `SmartLifecycle` beans, giving in-flight requests a chance to run before bean dependencies are destroyed.

### Intentional configuration example for a simple service

~~~properties
server.port=8080

# Spring Boot 3.3: explicitly enable graceful.
server.shutdown=graceful

# Drain window for the web server shutdown phase.
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

This config only governs the application lifecycle **when the context closes normally**. It does not turn `kill -9` into graceful shutdown and does not dictate how long Kubernetes waits; that belongs to the orchestrator.

## 5. How does Spring Boot actually stop accepting new requests?

Spring Boot 3.3 supports graceful shutdown on **Tomcat, Jetty, Reactor Netty, and Undertow**, for both Servlet MVC and reactive web applications. Official documentation clearly distinguishes the mechanisms:

| Embedded server | What happens to new requests during drain | What to expect when testing |
|---|---|---|
| **Tomcat** | Stops accepting new requests at the network layer | New TCP connections may be refused/reset/fail to connect; HTTP 503 is not promised |
| **Jetty** | Stops accepting new requests at the network layer | Depends on version, connection, and persistent connections |
| **Reactor Netty** | Stops accepting new requests at the network layer | WebFlux HTTP server may reject at network level; test client behavior |
| **Undertow** | May accept connections but returns **HTTP 503 Service Unavailable** for new requests | New requests may receive an explicit HTTP 503 |

**Do not write an automated assertion saying “after SIGTERM every new request must receive HTTP 503” when using Tomcat.** A request may fail with connection refused or reset before any HTTP status exists. With keep-alive/persistent connections, HTTP/2 multiplexing, or requests sent right as shutdown begins, boundary outcomes can vary. Assert **that no new business work is accepted after drain**, rather than forcing all clients to observe the exact same code.

### When is a request considered “accepted”?

Boundary race conditions:

~~~text
Client C1 opens a TCP connection before TERM
Client C1 sends request headers after TERM?
Client C2 sends a new HTTP/2 stream over an old connection?
Load balancer sends a request while EndpointSlice is updating?
~~~

“Connection already opened earlier” does not necessarily mean “application request has started”. Handling depends on the server, HTTP protocol, and connector state. Tests should therefore look at **actual request start logs/metrics**, not just socket open times. For async streaming, if a request stays open indefinitely, draining may wait until the grace timeout.

## 6. Spring ApplicationContext and SmartLifecycle lifecycle

Graceful shutdown occurs when `ApplicationContext` is closed. Spring Framework provides lifecycle management where `SmartLifecycle` supports:

- `start()`: starts operation.
- `stop(Runnable callback)`: requests asynchronous stop and **calls callback.run()** when finished.
- `getPhase()`: determines ordering.
- `isRunning()`/`isAutoStartup()`: state and auto-start.

Phases follow the rule: lower phase **starts earlier**, **stops later**; higher phase starts later, stops earlier. Spring Boot web graceful shutdown resides in an early phase of the stopping sequence so in-flight HTTP can continue before lower-level resources are cleaned up.

### Why does timeout-per-shutdown-phase not equal total process time?

Suppose there are three lifecycle phase groups, each able to wait up to 20 seconds, plus other destroy callbacks; total wall-clock shutdown can exceed 20 seconds. Setting `terminationGracePeriodSeconds` to exactly 20 seconds just because the Spring property is 20s can cause Kubernetes to send SIGKILL before cleanup finishes.

**Do not assign an arbitrary number as the phase of a critical bean** just to make sure it stops “after Tomcat”. If you have background consumers, queue publishers, schedulers, or resource pools that depend on HTTP/draining, read the phase contracts of the relevant components, establish intentional stop ordering, and write integration tests. In particular, do not close the DataSource too early while in-flight controllers are still running transactions.

### What is the right role for @PreDestroy?

`@PreDestroy` and DisposableBean destruction typically run during the bean cleanup stage after lifecycle stops. They are suitable for small resource cleanup/closing handles, **not a reliable strategy for doing your own traffic drain via `Thread.sleep(30000)`**. If you need to stop receiving business jobs before shutdown, design dedicated admission/readiness and consumer lifecycles.

~~~java
// Snippet inside a @Component; not a standalone program.
@PreDestroy
public void onDestroy() {
    logger.info("Closing application-owned resource");
    resource.close();
}
~~~

If `resource.close()` can hang, add a bounded timeout and metrics; avoid an infinitely blocking `@PreDestroy` that causes the process to be SIGKILLed when the orchestration grace window expires.

## 7. SIGTERM, SIGKILL, and signal delivery

On Linux/containers, there is a fundamental difference:

| Stop method | Typical mechanism | Can graceful shutdown happen? |
|---|---|---|
| `kill -TERM PID` | Sends SIGTERM to the process | Yes, if the JVM receives TERM and app shuts down normally |
| Docker `docker stop` | Sends stop signal (default TERM), waits stop timeout then forces | Yes if entrypoint forwards signal and grace is sufficient |
| Kubernetes Pod termination | preStop if configured, then TERM, and finally KILL on grace expiry | Yes if TERM reaches the JVM PID 1/proper process |
| `kill -9 PID` | Immediate SIGKILL | **No**; JVM does not run shutdown hooks properly |
| OOM kill/power loss | No chance to run lifecycle | **No** |
| IDE Stop button | Depends on whether IDE sends TERM or force-terminates | Must not assume it equals SIGTERM |
| CTRL+C in terminal | Usually sends SIGINT/interrupt to foreground process group | Usually gives JVM a chance to shut down, but test in target environment |
| Windows Task Manager / Stop-Process | Depends on process termination mechanism | Not equivalent to Linux SIGTERM |

**Exec-form Dockerfile ENTRYPOINT** should be used so the JVM is the process receiving signals:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/graceful-demo-0.0.1-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

If a shell-form entrypoint is used and the shell does not `exec` Java, signals may hit the shell instead of reaching the JVM properly. Not every shell entrypoint is broken, but it must actively forward TERM and wait on the child process. Avoid launchers/background helpers that prevent the JVM from seeing signals.

### When termination is too abrupt

- On Linux, `kill -9` cannot be caught by a Java shutdown hook.
- Container runtimes can force terminate when the grace period expires.
- Cloud load balancers may still route traffic briefly due to propagation delay.
- If the kernel OOM killer terminates the JVM, there is no chance to complete in-flight requests.
- Therefore transactional durability, idempotency, retry safety, and distributed architecture must still tolerate **unexpected termination**.

Graceful shutdown reduces disruption during **intentional shutdowns**; it does not make a system immune to crashes.

## 8. Readiness vs liveness: how to tell the load balancer to stop sending requests?

**Readiness:** Should the instance be selected for **new traffic**?  
**Liveness:** Is the instance healthy enough to keep running, or must it be restarted?

Spring Boot provides `ApplicationAvailability` along with `ReadinessState` and `LivenessState`. During the shutdown lifecycle, readiness transitions to `REFUSING_TRAFFIC`; liveness can remain `CORRECT` during the drain phase. This is normal: the app is **still alive to finish old requests but does not want new requests**.

| Spring Boot stage | Liveness | Readiness | Request handling |
|---|---|---|---|
| Starting | BROKEN or insufficient info yet | REFUSING_TRAFFIC | Not accepting traffic yet |
| Started, not ready | CORRECT | REFUSING_TRAFFIC | Not picked as primary target yet |
| Ready | CORRECT | ACCEPTING_TRAFFIC | Accepting traffic |
| Graceful shutdown | CORRECT | REFUSING_TRAFFIC | Rejects new, processes in-flight |
| Shutdown complete | No runtime left | No probes left | Process stopped |

Do not blindly make readiness probes depend directly on every external service; a shared DB outage can turn all Pods not-ready and leave zero endpoints. Liveness especially **must not** fail just because a downstream API is temporarily slow if the app can recover or circuit-break.

### Using Spring Boot Actuator

Add Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

With Spring Boot 3.3, in Kubernetes environments, liveness/readiness health groups may be auto-enabled. To ensure the lab works locally as well, declare explicitly:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Corresponding paths:

~~~text
GET /actuator/health/liveness    (liveness health group)
GET /actuator/health/readiness   (readiness health group)
GET /livez                       (additional path on main app port)
GET /readyz                      (additional path on main app port)
~~~

`management.endpoint.health.probes.add-additional-paths=true` exposes `/livez` and `/readyz` on the **main web server port**. This is useful if Actuator runs on a separate management port, because an alive management port does not guarantee the application port is still accepting traffic. Do not expose all actuator `env`, `configprops`, `heapdump`, `shutdown` endpoints just to get probes.

**During shutdown:** Boot switches readiness state to refusing, yet the HTTP listener itself is also stopping acceptance of new requests. A probe called after TERM **may become unreachable** rather than returning readiness=503 JSON. What matters is that the orchestrator/drainer uses the state and termination lifecycle; tests must not require `curl /readyz` to return HTTP 503 after TERM once Tomcat has refused TCP.

## 9. Coordinating two layers: removing instance from routing and closing the connector

Distinguish clearly:

~~~text
Load Balancer Layer                  Spring Boot process
------------------------------       -----------------------------
Mark endpoint not ready              Receive TERM / context close
Stop selecting for new traffic        Switch readiness REFUSING_TRAFFIC
Existing requests may continue        Embedded server stops new accepts
Propagation takes time                Finish in-flight during grace
External connections may persist      Close resources + exit
~~~

Changing readiness alone means the process can still receive direct traffic, traffic via another load balancer, or requests already queued in transit. Closing the connector alone means the LB may keep sending requests to an instance whose socket is closed, causing the gateway to return 502/503 until routing updates. **Combine both** and allow time for network convergence.

### Should you create a custom Filter returning 503 while draining?

A custom admission filter can be useful in systems requiring pre-drain before TERM, but it is not a prerequisite for Boot graceful shutdown to work. If the filter starts returning 503 **too early**, in-flight requests or health probes may be impacted; if too late, the LB hasn't dropped the instance yet. A state machine and concurrency/cross-proxy tests are needed.

Do not put `Thread.sleep(5000)` in controllers to wait for the load balancer; that is an anti-pattern that increases latency for active requests. If a time buffer is needed for route deregistration, use orchestrator lifecycle hooks or a verified drain protocol.

## 10. Kubernetes Pod termination: order and total limit

Kubernetes typically sends SIGTERM when a Pod is asked to stop under its termination policy. A simplified flow:

~~~text
kubectl delete pod / Deployment rolling update
         |
         v
Pod enters Terminating; grace-period countdown begins
         |
         +--> EndpointSlice marks terminating endpoint ready=false
         |    (traffic removal propagates asynchronously)
         |
         +--> kubelet runs preStop if configured
         |    (this time is PART OF the same termination grace budget)
         |
         v
kubelet/container runtime sends TERM to process
         |
         v
Spring Boot graceful shutdown drains in-flight requests
         |
         v
JVM cleanup and exit
         |
         +--> if still running after grace period: SIGKILL
~~~

**Crucial detail:** Kubernetes starts counting `terminationGracePeriodSeconds` **before** executing `preStop`. The hook is invoked before TERM and must finish before TERM is sent. If the hook takes 8 seconds, those 8 seconds are **not added on top of the grace period**. Kubelet may request a brief special extension when preStop exceeds the deadline, but you should not rely on that as dependable budget in your design.

A terminating Pod's EndpointSlice sets `ready=false`, avoiding normal traffic routing; however, propagation across kube-proxy/ingress/external LB is not instantaneous. Some workloads need a short `preStop` wait so external load balancers update before TERM; that is a measured trade-off, **not a mandatory default**.

### Example 45-second budget allocation

| Item | Example seconds | What to keep in mind |
|---|---:|---|
| Kubernetes `terminationGracePeriodSeconds` | 45 | Total time for the entire process |
| Optional preStop/drain delay | 5 | Consumes part of 45, not added on top |
| Spring graceful web phase | 20 | `spring.lifecycle.timeout-per-shutdown-phase=20s` |
| Other lifecycle phases/resource cleanup | Reserve 10 | May have multiple phases; must measure |
| Network/runtime/overhead margin | Reserve 10 | Absorbs variance, signal delivery |
| Planned total allocation | 5 + 20 + 10 + 10 = 45 | Planning estimate, not a hard timing guarantee |

An application with **multiple SmartLifecycle phases**, slow `@PreDestroy`, or running background jobs may need a larger Kubernetes grace period or a revised cleanup flow. Do not blindly apply the formula `terminationGracePeriodSeconds = spring.lifecycle.timeout-per-shutdown-phase` to every system.

### Valid illustrative Deployment YAML

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: graceful-demo
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: graceful-demo
  template:
    metadata:
      labels:
        app: graceful-demo
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: graceful-demo:1.0
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8080
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: 8080
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /livez
              port: 8080
            periodSeconds: 2
            failureThreshold: 30
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
~~~

**Proper usage:** this manifest works when the cluster already has the image `graceful-demo:1.0` (built/pushed or loaded into the local cluster), and the image includes `/bin/sh` and `sleep`. With distroless images lacking a shell, use another mechanism or omit the hook. Only enable a 5-second preStop if you have verified route draining time is needed; `preStop` can be omitted when EndpointSlice/controllers suffice. This is an **illustrative configuration requiring tuning**, not a drop-in manifest for any production cluster.

`maxUnavailable: 0` with `maxSurge: 1` helps rolling updates keep ready replicas available when scheduling/capacity allows; it **does not promise zero downtime** if there is only one unhealthy backend, bad affinity, insufficient PodDisruptionBudget/cluster capacity, or an LB still routing to the old Pod. Verify your ingress/LB behavior.

### Why avoid using a public HTTP shutdown endpoint?

Spring Boot Actuator has `/actuator/shutdown`, which is **disabled by default**; do not turn on public HTTP shutdown just to make orchestration “stop easily”. If an admin endpoint is needed, place it on a management network with strict auth and policies; usually TERM/Pod lifecycle is safer with a smaller attack surface.

## 11. Runnable lab: Spring Boot MVC finishing old requests during the graceful phase

The lab uses **one MVC/Tomcat application**, a slow HTTP route, and an in-flight counting route. The goal is not to build a job queue system, but to directly observe the listener stopping new intake.

~~~text
Terminal A:
  java -jar graceful-demo.jar
      |
      +-- GET /api/work?delayMs=8000  [accepted request, takes 8s]
      +-- GET /api/work?delayMs=100   [new request attempted after TERM]
      +-- GET /api/active             [count of requests inside controller]
      +-- GET /readyz                [liveness/readiness]
   
Terminal B:
  curl 8s request
  kill -TERM PID
  try new curl
  wait for 8s request + JVM exit
~~~

### 11.1. Project structure

~~~text
graceful-demo/
  pom.xml
  src/
    main/
      java/
        example/
          graceful/
            GracefulDemoApplication.java
      resources/
        application.properties
    test/
      java/
        example/
          graceful/
            GracefulDemoApplicationTests.java
~~~

### 11.2. Complete Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>graceful-demo</artifactId>
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

Here `spring-boot-starter-web` brings Spring MVC and embedded Tomcat; `spring-boot-starter-actuator` provides health probes; `spring-boot-starter-test` is test-scoped only. WebFlux, GraphQL, or WebSocket are omitted since they are outside this use case.

### 11.3. Complete application.properties

~~~properties
server.port=8080

# Spring Boot 3.3 requires explicit opt-in:
server.shutdown=graceful

# Duration for EACH shutdown phase, including graceful web drain:
spring.lifecycle.timeout-per-shutdown-phase=20s

# Health probes usable both locally and on the main app port:
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true

# Do not expose exceptions or stacktraces from Spring Boot error handler:
server.error.include-message=never
server.error.include-exception=false
server.error.include-stacktrace=never
~~~

Do not set `management.endpoint.shutdown.enabled=true`; no HTTP shutdown endpoint is needed for the lab to work.

### 11.4. Complete application Java file

Create `src/main/java/example/graceful/GracefulDemoApplication.java`:

~~~java
package example.graceful;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class GracefulDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(GracefulDemoApplication.class, args);
    }

    public record WorkResult(long delayMs, boolean completed) {
    }

    @RestController
    static class WorkController {
        private static final Logger log =
                LoggerFactory.getLogger(WorkController.class);

        private final AtomicInteger active = new AtomicInteger();

        @GetMapping("/api/work")
        public ResponseEntity<WorkResult> work(
                @RequestParam(defaultValue = "150") long delayMs)
                throws InterruptedException {

            // Demo only: guard against negative or unbounded input.
            if (delayMs < 0 || delayMs > 30000) {
                return ResponseEntity.badRequest().build();
            }

            int count = active.incrementAndGet();
            log.info("work-start delayMs={} active={}",
                    delayMs, count);

            try {
                Thread.sleep(delayMs);
                log.info("work-finished delayMs={}", delayMs);
                return ResponseEntity.ok(
                        new WorkResult(delayMs, true));
            } finally {
                int remaining = active.decrementAndGet();
                log.info("work-cleanup active={}", remaining);
            }
        }

        @GetMapping("/api/active")
        public Map<String, Integer> active() {
            return Map.of("active", active.get());
        }
    }

    @Component
    static class ResourceLifecycle {
        private static final Logger log =
                LoggerFactory.getLogger(ResourceLifecycle.class);

        @PreDestroy
        void onDestroy() {
            log.info("application-resources-destroying");
        }
    }
}
~~~

**Explanation:**

- `WorkController` uses `AtomicInteger` to count requests currently inside the handler, not a static global counter shared across processes. This is for local lab measurement, not a full production metric.
- `Thread.sleep(delayMs)` is **intentionally blocking** to observe draining in Servlet MVC. Do not use it to simulate production tasks; real workloads need DB/HTTP timeouts and bounded work.
- The code does not call `System.exit` in the controller; Spring Boot manages graceful shutdown when the context closes normally.
- `@PreDestroy` only logs to show the lifecycle cleanup order; it does not sleep or decide which requests are accepted.
- Success body is a record serialized to JSON by Jackson on MVC, e.g., `{"delayMs":8000,"completed":true}`.
- After TERM, Tomcat may reject new connections **at the network layer**, so clients may not receive any HTTP status. Nothing in the controller Java code forces Spring to return HTTP 503.
- If the client already closed the connection before work finishes, the server may fail while writing the response; seeing the `work-finished` log does not guarantee the caller received the body.

### 11.5. JUnit integration test (without killing the JVM in tests)

Create `src/test/java/example/graceful/GracefulDemoApplicationTests.java`:

~~~java
package example.graceful;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class GracefulDemoApplicationTests {

    @Autowired
    TestRestTemplate http;

    @Test
    void shortRequestCompletes() {
        ResponseEntity<GracefulDemoApplication.WorkResult> response =
                http.getForEntity(
                    "/api/work?delayMs=10",
                    GracefulDemoApplication.WorkResult.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(10L, response.getBody().delayMs());
        assertEquals(true, response.getBody().completed());
    }

    @Test
    void activeCountEventuallyReturnsToZero() {
        ResponseEntity<Map> response =
                http.getForEntity("/api/active", Map.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(0, response.getBody().get("active"));
    }
}
~~~

The two tests verify normal REST behavior. **They do not prove graceful shutdown works**, because killing the JVM running JUnit inside the same process is unsuitable. The next process-level integration test is needed to check TERM and in-flight requests. In the test, `RANDOM_PORT` overrides `server.port=8080` to avoid port conflicts.

### 11.6. Run tests and build the executable JAR

~~~bash
mvn clean package
~~~

Expect **Maven BUILD SUCCESS** and both JUnit methods to pass when dependencies/JDK match. Output file:

~~~text
target/graceful-demo-0.0.1-SNAPSHOT.jar
~~~

Run the server in one terminal:

~~~bash
java -jar target/graceful-demo-0.0.1-SNAPSHOT.jar
~~~

Another terminal:

~~~bash
curl -i http://localhost:8080/api/work?delayMs=100
curl -i http://localhost:8080/api/active
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/livez
~~~

When the app is ready, `/readyz` and `/livez` normally return HTTP 200 with a JSON health group containing `"status":"UP"`; this is **before shutdown**. The `/api/work?delayMs=100` request returns HTTP 200 with JSON containing `delayMs:100` and `completed:true`.

### 11.7. Testing SIGTERM on a real process on Linux/WSL/macOS

Run the Bash script below from the project root **after verifying port 8080 is free**. Do not run the server from another terminal simultaneously. The script waits for `/readyz` to report ready, starts an 8-second request, sends TERM after 1 second, and then tries a new request:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

JAR="target/graceful-demo-0.0.1-SNAPSHOT.jar"
java -jar "$JAR" > graceful-demo.log 2>&1 &
APP_PID=$!

ready=false
for i in $(seq 1 30); do
  if curl -fsS http://localhost:8080/readyz >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done

if [ "$ready" != true ]; then
  echo "App was not ready in 30s"
  cat graceful-demo.log
  kill -TERM "$APP_PID" 2>/dev/null || true
  exit 1
fi

curl -fsS \
  "http://localhost:8080/api/work?delayMs=8000" \
  > /tmp/graceful-inflight.json &
REQUEST_PID=$!

sleep 1
kill -TERM "$APP_PID"

echo "Trying a NEW request after SIGTERM:"
curl -i --max-time 2 \
  "http://localhost:8080/api/work?delayMs=100" || true

wait "$REQUEST_PID"
echo "Existing request result:"
cat /tmp/graceful-inflight.json
echo

wait "$APP_PID" || true
echo "Application log:"
tail -n 35 graceful-demo.log
~~~

Utilities like Bash, curl, seq, tail, and the `/tmp` path assume **Linux/macOS/WSL**. On Windows PowerShell, `Stop-Process` usually does not reproduce the same SIGTERM semantics; run in WSL/Linux containers to test process signals accurately. The script runs `java -jar` directly, not `mvn spring-boot:run`, because the Maven launcher obscures PID/signal behavior.

**Expected result when the 8-second request was actually accepted by the server:**

~~~text
Trying a NEW request after SIGTERM:
(curl may report Connection refused/reset or an HTTP error depending on connector)
Existing request result:
{"delayMs":8000,"completed":true}
Application log:
... work-start delayMs=8000 ...
... Commencing graceful shutdown ...
... work-finished delayMs=8000 ...
... work-cleanup active=0 ...
... application-resources-destroying ...
~~~

**This is illustrative output, not a byte-for-byte transcript.** Logger timestamps/format/order and the new connection's status depend on runtime, OS, and process timing; `tail` does not always show every line. The core test assertion is that the request accepted before TERM **completes within 20 seconds** and the HTTP server **does not accept new work after graceful shutdown starts**. If a race causes the slow request not to be accepted before TERM yet, re-run with log/metric synchronization instead of just sleeping 1 second; do not declare a test pass based on a race.

### 11.8. Testing a request longer than the grace period

Change the request duration in another test run to 25 seconds when `timeout-per-shutdown-phase=20s`. If the request is still in-flight after the drain window, it is **not guaranteed** to finish; the connector may close or the process may be killed by orchestration per configuration. In production, request/dependency-level timeouts must not exceed grace, or else route long jobs to a different policy/deadline/async model. Do not increase grace indefinitely just to let every piece of work keep running.

### 11.9. Docker test

Build the image from the Dockerfile in section 7:

~~~bash
mvn clean package
docker build -t graceful-demo:1.0 .
docker run -d --rm --name graceful-demo \
  -p 8080:8080 graceful-demo:1.0
~~~

When the app is ready, run a long request in another terminal and then stop the container with an intentional timeout:

~~~bash
curl -fsS "http://localhost:8080/api/work?delayMs=8000"
~~~

~~~bash
docker stop -t 30 graceful-demo
~~~

The two commands are run **concurrently in two terminals** so the request is still in-flight when stop happens; waiting for curl to finish before stopping does not test draining. `docker stop -t 30` gives the container 30 seconds after the stop signal before forced termination; it needs to cover the web shutdown phase and related cleanup. Docker may use a different stop signal if configured differently on the image/runtime; verify in practice.

## 12. Do not confuse stopping HTTP with stopping all background work

Spring Boot graceful server shutdown focuses on **HTTP in-flight requests**. Many other types of work have separate lifecycles:

| Work type | Fully covered automatically by server.shutdown=graceful? | What more is needed? |
|---|---|---|
| Synchronous MVC request in progress | Given a drain window by the server if accepted before shutdown | Bounded service/dependency timeouts |
| WebFlux HTTP reactive request | Has connector web-server drain | Proper cancellation/discard/cleanup |
| Scheduled `@Scheduled` job | Not an HTTP in-flight request by default | Stop new schedules, wait/cancel running work per executor policy |
| `@Async` tasks | Not managed solely by the web server | Task executor shutdown policy, bounded queues/timeouts |
| Kafka/Rabbit/JMS consumers | Not an HTTP request | Stop polls/listeners, commit/ack policy, and replay/idempotency |
| Quartz scheduler | Has its own scheduler lifecycle | Appropriate graceful stop/quiesce config |
| Background file transfer/object storage | May outlive HTTP response/202 | Abort/complete/clean up multipart uploads and temp files |
| DB transactions | Not automatically rolled back by TERM | Transaction manager/driver timeouts and data integrity |
| WebSocket sessions | Long-lived and bidirectional | Protocol close/drain policy, reconnect |
| SSE/long polling | Long-lived HTTP stream | Max lifetime, cancellation, reconnect semantics |
| Distributed locks/leases | Does not rely on HTTP connector | Bounded leases, release/renew, failover |
| Manually created `new Thread(...)` | Spring may not manage its lifecycle | Executor service/SmartLifecycle and shutdown coordination |

A scheduled job pushing data to Kafka might be running when the web connector stops accepting new requests. If the process stops and the job has not checkpointed, you need at-least-once processing and idempotency or a matching protocol, rather than expecting an HTTP property to guarantee exactly-once.

### Blocking new work in background workers

A consumer may need two steps:

1. **Quiesce:** stop pulling more messages/tasks from the broker/queue.
2. **Drain:** finish already claimed tasks and commit/ack safely within the timeout.
3. **Close:** release producer/consumer connections.
4. **Force stop:** after the deadline, abort in a controlled manner and rely on retries/recovery when a new instance starts.

These steps can be managed via `SmartLifecycle`, listener containers, or executor shutdown policies, **not** replaced by `@PreDestroy Thread.sleep(...)` without ownership/metrics.

## 13. SmartLifecycle for custom components: avoiding deadlocks and forgotten callbacks

If an application manages a background task consumer with an asynchronous stop, `SmartLifecycle` can be used. In this interface:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
}
~~~

This is an **abbreviated API excerpt** for explanation, not a Java file redefining the Spring interface in the project. When implementing `stop(Runnable callback)` yourself:

- Signal the component to stop accepting new work before draining.
- Send the stop signal to the appropriate worker/executor.
- Wait for/cancel jobs within a limit and record metrics.
- **Always call `callback.run()` after stop processing**, including on error paths, so the lifecycle processor does not wait until the deadline.
- Do not block an event loop or lifecycle thread arbitrarily.
- Choose `getPhase()` deliberately based on resource dependencies and the web server; phase order reverses at shutdown.
- Avoid designs where the HTTP server waits on background jobs while jobs wait on a bean dependency that has already closed.

Example pseudo-flow:

~~~text
stop(callback):
    acceptingNewTasks = false
    askConsumerToStopPolling()
    finishOrCancelAlreadyClaimedTasksBeforeDeadline()
    commit/ack/rollbackAccordingToProtocol()
    releaseOwnedResources()
    callback.run()
~~~

**Do not turn pseudo-flow into production code** without the specific broker SDK and task contract. With Spring Kafka, RabbitMQ, Quartz, or TaskExecutor, prefer library-supported lifecycle settings and test thoroughly.

## 14. Startup–readiness–shutdown: the complete lifecycle

Traffic is only stable when **both startup and shutdown** are coordinated. A newly started instance may open its TCP port earlier than caches/warmup/authorization/configuration finish; readiness prevents routing traffic before it is ready.

~~~text
STARTUP
  process starts
  context initialization
  Liveness CORRECT, Readiness REFUSING_TRAFFIC
  ApplicationReadyEvent / startup tasks complete
  Readiness ACCEPTING_TRAFFIC
  load balancer begins routing

RUNNING
  new HTTP requests accepted
  in-flight requests complete
  health/metrics monitored

TERMINATION
  Pod marked Terminating / context close
  Readiness REFUSING_TRAFFIC
  no new requests accepted by web server
  in-flight requests drain
  other components cleanup
  process exits
~~~

A passing health probe **does not mean** every business path will succeed; an overly heavy readiness probe can also cause load/DB storms. Design simple liveness reflecting JVM recoverability; readiness reflects traffic acceptance and carefully selected critical dependencies.

### Waiting for readiness during rolling updates

If the orchestrator considers a new Pod available too early, it may take down the old Pod before the new Pod is ready to serve. Coordinate `readinessProbe`, `startupProbe` if startup is slow, rollout strategy, replica count, PodDisruptionBudget, and autoscaling. Graceful shutdown of the old Pod cannot fix readiness of the new Pod.

## 15. Long-lived connections: keep-alive, HTTP/2, SSE, and WebSocket

### HTTP/1.1 keep-alive

A client can keep a TCP connection open to send multiple HTTP requests. When graceful shutdown starts, server-specific behavior may differ between **an already open connection** and **a new request**. Do not test drain by merely opening a socket before TERM and sending the request after; verify that the request reached the servlet/handler before shutdown started.

An HTTP response may add `Connection: close` or close the connection after the response depending on the server/protocol, but it is not a header Spring Boot guarantees to send on every request during graceful shutdown across all servers. When testing, accept connection refused/reset rather than insisting on HTTP 503 on Tomcat.

### HTTP/2 multiplexing

Multiple concurrent streams share one connection; graceful draining may involve GOAWAY/stream rules depending on the implementation. Do not take HTTP/1.1 behavior on Tomcat and assume new HTTP/2 requests will always fail with the same code. Test actual clients, gateways, and server versions, especially with gRPC/HTTP2 if your service uses them.

### SSE and streaming

A `text/event-stream` response can remain open for minutes or hours. Without bounds, graceful shutdown may wait until the phase timeout and then close an incomplete stream. Define heartbeats, max stream lifetime, event resume IDs, and client reconnect; during drain, you can send a “server retiring” message per your app protocol if the response is still writable, though delivery to every client is not guaranteed.

### WebSocket

A WebSocket is not a short HTTP request after handshake. Bidirectional connections need close handshakes, session draining, or separate client reconnect policies, which may not share the same semantics as Servlet in-flight HTTP requests. If using Spring WebSocket/STOMP, check how the framework/broker stops session subscriptions, acks, pending messages, and coordinates with the load balancer.

### Large downloads/uploads

Multi-GiB uploads/downloads can outlast the shutdown grace period; consider resumable uploads, chunking, direct object-storage access, storage cleanup, or policies avoiding instance removal during critical transfers. Do not set a 10-minute phase on every service just for rare file uploads; separating workloads/routes may be better.

## 16. Database transactions, idempotency, and client disconnect

Gracefully waiting for in-flight HTTP requests does not mean “duplicate business operations can never happen”. For example:

1. Client sends a POST to create an order to instance A.
2. A commits the DB transaction.
3. TERM arrives at A or the gateway/client disconnects before the response reaches the client.
4. Client sees timeout/connection reset and assumes the request failed.
5. Client retries the POST to instance B and risks creating a second order.

Mitigations:

- Use an **idempotency key** or unique business constraint for critical mutations.
- Let clients query transaction/job state by a stable identifier.
- Do not write logic saying “whenever IOException happens while writing response, roll back what was committed” — the transaction may already be complete.
- For distributed transactions/sagas, design dedicated retry/reconciliation logic.
- For queue-based consumers, at-least-once delivery requires deduplication and committing/acking at the right point.

Graceful shutdown reduces the probability of mid-request cuts; **it does not replace transactional correctness**.

## 17. Measuring load and calculating drain budget from in-flight workload

If the HTTP server has 100 running requests, some taking 15 seconds and the rest 0.2 seconds, a 20-second grace can suffice when dependencies are healthy. But if a DB query hangs for 90 seconds, the 20-second phase expires before it completes.

What to measure:

- Active HTTP server requests and duration histograms/tail latency per route.
- Active servlet worker threads/queued requests; count of tasks being processed.
- Outbound HTTP client connection pool pending/active.
- Active/pending DB connections, query timeouts, transaction durations.
- Time from SIGTERM to “graceful shutdown complete”.
- In-flight requests remaining when grace times out.
- Client disconnects/502/503/504 during deployment windows.
- Pod terminating counts/EndpointSlice readiness and ingress backend routing logs.
- Background consumer pending work/unacked messages and cleanup duration.

**A mental formula, not a guarantee:**

~~~text
T_required_for_shutdown >= max(remaining_times_of_inflight_requests)
                          + lifecycle_cleanup
                          + network/orchestrator_margin

T_Kubernetes >= T_preStop + T_spring_lifecycle_total
                + T_other_cleanup + margin
~~~

If multiple lifecycle phases stop in parallel or depend on each other, compute based on the real **critical path** and verify Spring's **per-phase** lifecycle timeout. Do not base max request duration on p50; use proper request-time limits to establish a finite bound.

### Graceful does not mean raising thread counts

If a service is overloaded, a rolling shutdown wave shifts traffic onto remaining replicas. You may need more replicas/`maxSurge`, warmup, and readiness gating rather than just raising `server.tomcat.threads.max` or `timeout-per-shutdown-phase`.

## 18. Observability and logs needed during shutdown

A well-instrumented lifecycle can log:

~~~text
time=... event=termination_requested instance=pod-a
time=... event=readiness_refusing_traffic instance=pod-a
time=... event=graceful_shutdown_started active_http_requests=12
time=... event=graceful_shutdown_completed active_http_requests=0 elapsed_ms=...
time=... event=resource_cleanup_started
time=... event=process_exit
~~~

This is a **desired log schema**, not Spring Boot's default log format. Events can be recorded with SLF4J and metrics/Actuator/Micrometer according to your version/monitoring system; do not expose credentials/PII in request paths or bodies.

### Useful telemetry across layers

| Layer | Observable |
|---|---|
| Kubernetes | Pod Terminating, deletionTimestamp, terminationGracePeriodSeconds, preStop outcome, exit code 137/143 context |
| EndpointSlice | Endpoint terminating, `ready=false`, routing state |
| Ingress/LB | Requests to terminating endpoint, 502/503/504, connection errors |
| JVM/Spring Boot | TERM observed, web graceful begin/end, SmartLifecycle stop duration, @PreDestroy |
| HTTP server | Active connections/in-flight requests, long tail durations |
| Downstream | Interrupted/timed-out/canceled calls, database rollback/commit |
| Client | Retry count, connection resets, response completed vs timed out |

Exit code `143` usually corresponds to the Linux SIGTERM exit convention and `137` usually corresponds to SIGKILL, **but you cannot conclude the cause from the number alone**: runtime/entrypoint/process signal handling affect the result. Inspect `kubectl describe pod`, events, OOMKilled, logs, and actual termination timing.

### Avoid confusing liveness with readiness

If an instance transitions to `REFUSING_TRAFFIC` to drain, that is **not** a bug needing an immediate restart. If the liveness probe is misconfigured to check readiness and fails, kubelet may kill the instance earlier than intended. Use separate endpoints/health groups for their respective purposes.

## 19. Minimum test matrix

| Scenario | How to perform | Result to observe |
|---|---|---|
| Graceful enabled | Boot 3.3 properties + TERM | Lifecycle graceful start/end present, stops new accepts |
| Old request completes | Start 8s work then TERM, 20s phase | Request returns 200 if client still listening, work-finished logged |
| New request after TERM | Open new TCP/curl connection | No new work processed; Tomcat may refuse/reset |
| Undertow behavior | App using Undertow and grace config | New request may receive HTTP 503 |
| Immediate mode | Separate test `server.shutdown=immediate` | Do not expect graceful-style drain |
| SIGKILL | `kill -9` in sandbox | No guarantee of lifecycle cleanup |
| Grace timeout | Work > phase budget | Request may be cut off, cleanup/forced close per runtime |
| Docker stop | `docker stop -t 30` | JVM receives stop signal and has enough drain time |
| Broken shell ENTRYPOINT | Shell does not forward TERM | Lifecycle not triggered properly, stop timeout gets exhausted |
| preStop delay | preStop 5s, grace 45s | TERM after preStop; both share the budget |
| Local readiness | `/readyz` before TERM | 200/UP when ready |
| Probes after TERM | HTTP port may be closed | Do not require JSON 503 from Tomcat |
| Pod rolling update | Replicas >= 2, maxUnavailable 0 | Error rate/availability meets SLO during rollout |
| Ingress stale route | Endpoint terminating | LB quickly stops routing, measure 502/503 |
| HTTP/1.1 keep-alive | Reuse old connection and send requests | Check exact request vs connection semantics |
| HTTP/2 streams | Multiplexed client | No new streams outside policy during drain |
| SSE/WebSocket | Long stream/duplex session | Bounded termination, reconnect |
| Async/background jobs | Work not managed by HTTP connector | Separate stop polling/cancel/ack/cleanup |
| POST mutation | Commit before response lost | Idempotency key prevents duplicate |
| Slow cleanup | Long `@PreDestroy`/SmartLifecycle | Sufficient Kubernetes grace; no unexpected SIGKILL |

**Important for active kill tests:** run only on local/staging test instances. Do not kill production Pods to “prove it works” without a change window, failure budget, and recovery plan. Acceptance data must come from real HTTP statuses, logs, and metrics, not from a kill command returning exit code 0.

## 20. Common anti-patterns

| Anti-pattern | Why it is wrong | Better approach |
|---|---|---|
| Omitting `server.shutdown=graceful` on Boot 3.3 and assuming it is on | Version-specific default differs from newer docs | Declare the property explicitly and test |
| Using `kill -9` to test graceful | SIGKILL does not run shutdown hooks | `SIGTERM` to the exact JVM PID |
| `docker stop` 3s timeout while Spring phase is 20s | Container is force-killed before draining | Coordinate stop timeout and grace budget |
| Shell-form Docker ENTRYPOINT not forwarding TERM | JVM may never receive the signal | Use exec-form ENTRYPOINT |
| Changing readiness without stopping accept | Direct/stale routing can still deliver requests | Combine readiness and connector drain |
| Closing server without removing from LB | Gateway keeps routing to closed instance | Drain propagation / K8s EndpointSlice |
| Requiring Tomcat to return HTTP 503 for new requests | Server usually rejects at network layer | Assert no new work, accept refused/reset |
| Setting preStop 30s with grace 30s | Zero time left for TERM/cleanup | preStop is part of total grace |
| Thinking per-shutdown-phase is total process shutdown timeout | There can be multiple phases | Budget total lifecycle/cleanup time |
| Infinite `@PreDestroy` sleep to “wait for requests” | Does not track in-flight, can hang | Built-in graceful + separate task lifecycle |
| Closing DB pool before requests drain | In-flight controllers fail mid-transaction | Dependency-aware lifecycle ordering |
| Shutting down old Pod before new Pod is ready | Rolling update causes downtime | Readiness + maxUnavailable + capacity |
| Liveness checking DB/readiness causing restart storms | Dependency outage kills all Pods | Separate health probe purposes |
| Trusting 200 from another management port as app health | App port can fail independently | `/readyz` on main port when appropriate |
| Exposing Actuator shutdown publicly | Creates a DoS vector to kill the app | Use orchestrator signals, secure management |
| Not handling SSE/WebSocket separately | Streams can block drain until timeout | Bounded lifetime/reconnect/close |
| Waiting on 2-minute tasks with 20s grace | Forces SIGKILL/aborted work | Async jobs, resumable/idempotent workflows |
| Treating controller completion as client receiving response | Network/client may disconnect | Client reconciliation, idempotency |
| Testing only the happy path | Misses boundary races | Process-level TERM, long requests, LB tests |

## 21. Safe deployment workflow

1. **Verify the actual Boot/server version** in the dependency tree and runtime; do not assume Boot 3.3 behaves like newer Boot.
2. Enable `server.shutdown=graceful` and set `spring.lifecycle.timeout-per-shutdown-phase` based on request/workload limits.
3. Add Actuator readiness/liveness probes suited to the environment; use `/readyz` on the app port if health groups must genuinely verify the main port.
4. Map the client→LB→Pod path and determine ingress/backend deregistration timing and keepalive/HTTP2 behavior.
5. Allocate `terminationGracePeriodSeconds` enough for preStop, lifecycle phases, cleanup, and buffer.
6. Ensure the JVM receives TERM, especially Docker PID 1/entrypoint and runtime signal policies.
7. Review HTTP request timeouts, DB timeouts, and job/stream lifetimes so no work runs unbounded.
8. Review background executors, message listeners, and schedulers with separate stop/ack/commit policies.
9. Write a process-level integration test starting a slow request then sending TERM, checking in-flight completion and no-new-work.
10. Test forced kills to prove durability/recovery, without expecting graceful behavior on SIGKILL.
11. Test rolling updates with proper replicas/capacity; measure 5xx, connection errors, p95/p99, in-flight, and cleanup.
12. Apply canary/rollback; keep metrics/alerts for shutdown drain duration and forced terminations.
13. Do not expose HTTP shutdown administration on public surfaces.
14. Document owners and deadlines for each resource group.
15. Re-test periodically when upgrading Boot/containers/orchestrator/gateway, as defaults and network behaviors can change.

### Example consistent time budget

~~~text
App P95 normal request:         300 ms
Explicit HTTP request cap:      10 s
Spring graceful web phase:      20 s
Other phases + cleanup:         <=10 s
Kubernetes preStop if needed:    5 s
Kubernetes total grace:         45 s
Unallocated safety margin:      10 s
~~~

This is **an example for discussion and measurement**, not a default config recommended for every service. If you have long streaming requests or multiple SmartLifecycle phases, adjust your model/workload budgets. Never give a business operation a hard deadline larger than the shutdown window while promising “every request will finish”.

## 22. Review questions with answers

**1. Should Boot 3.3 configure `server.shutdown=graceful` explicitly?**  
Yes. Boot 3.3 docs show enabling it via this property; do not project newer versions' defaults onto it.

**2. Does `spring.lifecycle.timeout-per-shutdown-phase=20s` mean the whole JVM surely stops in exactly 20s?**  
No. It is the timeout **per lifecycle shutdown phase**; other phases/destroy callbacks may remain.

**3. Will Tomcat always return HTTP 503 for new requests after TERM?**  
No. Tomcat, Jetty, and Reactor Netty stop accepting at the network layer; clients may see connection refusal/reset. Undertow may return 503.

**4. How does SIGTERM differ from SIGKILL?**  
TERM gives the JVM a chance to close the context/run shutdown hooks; SIGKILL prevents normal cleanup from running.

**5. Is IDE Stop always equivalent to SIGTERM?**  
No. You must check your specific IDE; process-level TERM tests are more reliable on Linux/WSL.

**6. Does Readiness=REFUSING_TRAFFIC mean the JVM is dead?**  
No. The app may still be alive processing old requests during drain; liveness remains CORRECT.

**7. Why is a readinessProbe needed if Boot graceful already blocks new requests?**  
So the orchestrator/LB stops picking the instance, avoiding failed traffic to a closed listener.

**8. Is the Spring Boot health endpoint guaranteed to still return JSON 503 while the listener is shutting down?**  
No. Once the connector stops accepting, the HTTP probe may fail to connect.

**9. Are 5 seconds of preStop added on top of terminationGracePeriodSeconds?**  
No. The countdown starts before preStop; it eats into the same budget.

**10. Does `server.shutdown=graceful` alone make a Kafka consumer stop polling/acking safely?**  
No. Message listeners/broker clients have their own lifecycles, acks, and retries.

**11. Is a `@PreDestroy` sleep(30000) a reliable drain mechanism?**  
No. It does not manage HTTP in-flight requests and can cause shutdown to hang.

**12. Why is idempotency needed when a client is disconnected mid-POST?**  
Because the server may have committed while the response never reached the client; retrying could duplicate.

**13. Why should livenessProbe not depend completely on a shared external DB?**  
A DB outage can cause all Pods to restart simultaneously, creating cascading failures.

**14. Does `maxUnavailable: 0` guarantee zero downtime on its own?**  
No. Sufficient replicas/capacity, proper readiness, and correct LB propagation/traffic behavior are also required.

**15. Can a 1-hour SSE stream affect a 20s graceful phase?**  
Yes. If the stream does not finish, the phase can expire; you need bounded lifetime/reconnect/close strategies.

**16. What is the risk of using a Dockerfile shell-form ENTRYPOINT?**  
Signals sent to the shell may not be forwarded to Java; the process fails to run the shutdown lifecycle properly.

**17. Why must you run process-level tests instead of only JUnit @SpringBootTest?**  
JUnit does not reliably simulate the JVM receiving TERM and the entire application context closing while HTTP requests are running.

**18. Should a public HTTP /actuator/shutdown be used for Kubernetes to stop a Pod?**  
No; the endpoint is disabled by default and a public shutdown creates a major attack surface. Prefer TERM/orchestrator.

**19. When an in-flight request completes yet the client disconnects, is the user guaranteed to have received the response?**  
Not yet. The network can break after commit; operation-status queries/idempotency are needed.

**20. If the Spring graceful phase is 20s yet Kubernetes grace is only 10s, what happens?**  
Kubernetes may force-terminate the process before the drain phase finishes. Budgets must be coordinated.

## 23. Official documentation and further reading

- [Spring Boot 3.3 – Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): `server.shutdown=graceful`, `spring.lifecycle.timeout-per-shutdown-phase`, and per-server behavior.
- [Spring Boot 3.3 – Actuator Endpoints / Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): liveness, readiness, `/readyz`, application availability during startup/shutdown.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): health probes and shutdown properties.
- [Spring Framework – Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `SmartLifecycle`, getPhase, stop callbacks, and @PreDestroy.
- [Spring Framework – Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): application context and event lifecycle.
- [Spring Boot – Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): readiness/liveness availability states.
- [Kubernetes – Pod Lifecycle / Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): terminationGracePeriodSeconds, SIGTERM/SIGKILL, EndpointSlice terminating readiness.
- [Kubernetes – Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/): preStop timing and container stop.
- [Kubernetes – Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): health probe configuration.
- [Kubernetes – EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/): endpoint conditions and traffic routing.
- [Docker – Stop Containers](https://docs.docker.com/reference/cli/docker/container/stop/): `docker stop` and stop timeout.
- [Docker – Dockerfile ENTRYPOINT](https://docs.docker.com/reference/dockerfile/#entrypoint): exec form, PID 1, signal forwarding.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP 503 semantics.
- [Spring Boot 3.3 – Production-ready features](https://docs.spring.io/spring-boot/3.3/reference/actuator/index.html): metrics, health endpoints, and operational concerns.

**Conclusion:** To stop an HTTP service safely, **explicitly enable graceful shutdown on Spring Boot 3.3**, give the application a finite drain window, coordinate readiness/traffic deregistration and Kubernetes/Docker stop budgets, observe in-flight requests, and design recovery for situations that cannot be graceful. “Stopping new request acceptance” must be enforced at both the **connector** and **routing infrastructure**, while in-flight work, background jobs, and transactions each have their own lifecycles.
