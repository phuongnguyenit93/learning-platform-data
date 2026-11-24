# Rolling Deployment with Graceful Shutdown and In-Flight Requests

> **Module:** Spring Boot – web-runtime. **Group:** Integrated Practice. This lesson practices **rolling out a service v1 → v2 without cutting off an already-started HTTP request**, while **stopping new requests from being routed to the retiring instance**. We combine **Spring Boot 3.3.x, Java 17+, Maven, Docker, Kubernetes Deployment/Service, Actuator readiness/liveness, SIGTERM, and in-flight request observation**. Later sections cover standalone tests, verification, rollback, common pitfalls, SLOs, and extensions for DBs, SSE, and WebSockets. Timings, images, and replica counts are **lab values** that must be tuned to real traffic and infrastructure.

## 1. Objectives and Acceptance Criteria

Completing this lesson means you understand and can verify:

1. Why rolling deployments need **two complementary mechanisms**: the load balancer/Service **stops picking the old Pod for new requests**, and Spring Boot **lets already-accepted requests finish**.
2. Spring Boot **3.3** requires `server.shutdown=graceful` to enable graceful shutdown, and `spring.lifecycle.timeout-per-shutdown-phase` is a **per-phase** timeout, not the total JVM shutdown duration.
3. Kubernetes involves `terminationGracePeriodSeconds`, `preStop`, Pod `Terminating`, and EndpointSlice `ready=false`; **`preStop` consumes the same shared grace period**.
4. Readiness differs from liveness; exposing `/readyz` and `/livez` on the **main application port** helps Kubernetes route accurately.
5. Docker `ENTRYPOINT ["java","-jar",...]` forwards stop signals cleanly to the JVM; `kill -9`/SIGKILL is never graceful.
6. A ~12-second request can still return HTTP 200 from **v1** if the v1 Pod receives SIGTERM mid-flight, provided the grace budget suffices and the client stays connected.
7. New requests to the **Service** after a successful rollout must hit v2; requests already running on v1 never migrate mid-flight to v2.
8. Tomcat does not necessarily return HTTP 503 after SIGTERM; **network connection refusal/reset** is also how new requests are rejected.
9. JUnit/Maven tests cover happy paths while **process/pod-level tests** prove graceful drain; standard JUnit alone cannot simulate Pod termination.
10. Distinguish "the Service can return 200" from "zero errors across every request"; rolling updates require enough replicas/capacity, readiness gating, drain propagation, and real observation.
11. Inspect logs, EndpointSlices, rollout events, status codes 499/502/503/504, retries, active counts, timeouts, and completion proof.
12. Maintain a rollback plan, POST idempotency, streaming/long-job policies, and tune settings only from measured causes.

**Lab success criteria:**

- Before updating, `/api/info` returns `release=v1` and the app is ready.
- In a single-Pod deletion test, a `/api/slow?waitMs=12000` request already active on that Pod **returns 200 with release v1** after the Pod enters termination, given the 25-second drain budget—never rely solely on `kubectl` exit codes.
- After `v1 → v2` completes, all ready Pods under the Deployment serve `release=v2`, and the Service stops routing normal traffic to terminating Pods per policy.
- **New** requests during the rollout incur no 5xx or connection errors beyond the measured error budget; if any occur, inspect route propagation, capacity, probes, and external layers.
- Logs show `slow-start` and `slow-done` for the in-flight request before clean process exit, with no unbounded hang.
- A broken release can be rolled back via `kubectl rollout undo` with verified recovery.

## 2. Before–During–After Model of a Version Rollout

~~~text
Before rollout:
                  Service / Ingress
                    |
            +-------+-------+
            |       |       |
            v       v       v
           Pod A    Pod B   Pod C
             v1      v1      v1
             READY   READY   READY

During rolling update:
                  Service / Ingress
                    |
             +------+------+-------+
             |      |      |       |
             v      v      v       v
           Pod A  Pod B  Pod C    Pod D
             v1     v1     v1      v2
           READY   READY  READY   warming...
                                     |
                                   READY
                                     |
           Pod A transitions Terminating -> endpoint ready=false
           Pod A stops receiving new requests via normal routing
           In-flight request on Pod A drains up to deadline
           Pod A exits; Pod D and remaining v2 Pods serve traffic

After rollout:
                  Service / Ingress
                    |
            +-------+-------+
            |       |       |
            v       v       v
           Pod D   Pod E   Pod F
             v2      v2      v2
             READY   READY   READY
~~~

**Note:** Kubernetes is not required to terminate Pod A first, nor are creation/deletion timings fixed as drawn. This depicts the general behavior of `replicas: 3`, `maxSurge: 1`, `maxUnavailable: 0`. Actual rollout speed depends on scheduling, image pulls, startup, readiness, `minReadySeconds`, and cluster capacity.

### Where Do In-Flight Requests Go?

A request already inside Pod A **stays on Pod A** until it finishes, cancels, drops, or hits a deadline. A Kubernetes Service cannot move an active Java controller thread mid-execution from Pod A to Pod D. Rolling updates are not live migration of call stacks, threads, transactions, or WebSocket sessions.

A new request arriving after Pod A leaves Service routing is directed by the load balancer to Pod B, C, or D depending on state; new cluster requests are not halted globally. It is the **old Pod** that stops accepting new work once signaled to terminate, while healthy Pods keep serving.

## 3. Terminology: Rolling Update, Traffic Draining, and Graceful Shutdown

| Component | Role | Pitfall |
|---|---|---|
| Deployment RollingUpdate | Replaces ReplicaSet/Pods with new image per availability policy | Does not guarantee in-flight requests finish by itself |
| Service / EndpointSlice | Selects ready endpoints for traffic | Route propagation lags, and external LBs cache endpoints |
| Readiness probe | Reports whether a Pod should receive **new requests** | Does not mean the Pod is dead or old requests cancelled |
| Liveness probe | Reports whether the process is wedged and needs restarting | Should not kill Pods over flaky external dependencies |
| Startup probe | Gives apps time to boot before liveness kicks in | Does not replace readiness gating |
| `preStop` lifecycle hook | Runs *before SIGTERM* | Hook duration eats out of `terminationGracePeriodSeconds` |
| SIGTERM | Requests controlled process shutdown | Works only if the JVM receives it and callbacks finish |
| Spring graceful shutdown | Stops accepting new HTTP requests, waits on active ones up to timeout | Does not finish infinite streams or cancel all background jobs |
| Shutdown phase timeout | `spring.lifecycle.timeout-per-shutdown-phase` | Not total allowed Pod lifetime |
| SIGKILL | Hard kill when grace expires or explicitly killed | Skips normal Java shutdown hooks/cleanup |
| In-flight request | Request already inside the server/handler awaiting completion | Different from an idle keep-alive socket |
| Old / new release | Deployed build version | A Service returning a mix of v1/v2 **mid-rollout** is normal |

### Conditions for Avoiding Disruption

No single property guarantees zero downtime. You need:

~~~text
Enough capacity for surge pods
    + Clean startup
    + Readiness opens only when genuinely able to serve
    + Service/Ingress drops terminating endpoints in time
    + Spring Boot stops accepting new connections
    + Existing requests finish within deadline
    + Sensible client retries / idempotency
    + DB/API compatibility across v1-v2
    + Observability + rollback
    = Sharp drop in rollout errors
~~~

Treat **zero-downtime** as a quantitative SLO measured by 5xx rates, connection errors, and user impact—never an absolute promise solely from `maxUnavailable=0`.

## 4. Spring Boot 3.3: Does Graceful Shutdown Need to Be Enabled?

**Yes.** **Spring Boot 3.3** documentation specifies enabling it explicitly:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s
~~~

Do not apply defaults from **newer** Spring Boot releases to 3.3. Docs for 3.5+/current may note graceful enabled by default; this lesson deliberately pins **3.3**.

Spring Boot supports graceful shutdown across Tomcat, Jetty, Reactor Netty, and Undertow (both Servlet and Reactive). When `ApplicationContext` closes, graceful drain runs in an early phase stopping `SmartLifecycle` beans. The server gives active requests time to finish while refusing new ones.

How new requests are refused **varies by embedded server**:

| Server | Once Graceful Drain Starts | What Clients May Observe |
|---|---|---|
| Tomcat | Stops accepting at the network layer | Connection refused/reset/EOF; not necessarily HTTP 503 |
| Jetty | Stops accepting at the network layer | Network or protocol-specific errors |
| Reactor Netty | Stops accepting at the network layer | New connections/streams refused per implementation |
| Undertow | May accept connections and return HTTP 503 | `503 Service Unavailable` |

Never write tests demanding **every** server return `503`: on Tomcat, TCP-layer refusal sends **no HTTP response**. Persistent HTTP/1.1 or HTTP/2 connections can also introduce race windows; verify actual request start times rather than just socket-open timestamps.

### spring.lifecycle.timeout-per-shutdown-phase Is Not the Total JVM Timeout

Setting 25 seconds caps **a single shutdown phase**. An application can have multiple `SmartLifecycle` phases plus resource cleanup. In particular, a slow `@PreDestroy` can extend shutdown well past the graceful web phase.

Consequently, Kubernetes `terminationGracePeriodSeconds` should never equal 25 just because the Spring property is 25s. Leave headroom for `preStop`, route propagation, remaining phases, resource closing, OS/runtime scheduling, and safety margin.

## 5. Traffic Draining on Kubernetes: What Happens When a Pod Is Deleted?

Timeline when a Deployment retires an old Pod:

~~~text
T0  API Server marks Pod Terminating
    |  Kubernetes starts the termination grace countdown
    |
    +--> EndpointSlice marks endpoint terminating=true
    |    ready=false for regular traffic endpoints
    |    Service/Ingress routing updates asynchronously
    |
    +--> Kubelet runs preStop (if defined)
    |    hook consumes the shared terminationGracePeriodSeconds
    |
T1  preStop finishes; kubelet/container runtime sends SIGTERM to process
    |
T2  JVM closes Spring ApplicationContext
    |  Spring Boot starts graceful web shutdown
    |  no new accepts; in-flight requests are awaited
    |
T3  In-flight work finishes or phase times out
    |  Remaining Spring lifecycle phases and cleanup run
    |
T4  Process exits
    |
T5  If termination grace expires while process still runs:
    container runtime sends SIGKILL
~~~

**Note on races and lag:** the EndpointSlice controller, `kube-proxy`/Service proxy, ingress controllers, and external load balancers update asynchronously. Terminating endpoints receive `ready=false` for normal traffic; some dataplanes inspect `serving` and `terminating` for draining, and edge cases when all endpoints are terminating can differ. Never assume "the microsecond a Pod enters Terminating, zero new requests anywhere in the world reach it."

### EndpointSlice Conditions

Kubernetes exposes three key conditions:

- `ready`: endpoint is ready to serve regular traffic. Terminating endpoints normally transition to `ready=false` for backward compatibility.
- `serving`: indicates whether the endpoint is still serving, useful to observe draining while terminating.
- `terminating`: indicates the backing Pod is terminating.

Illustrative state:

~~~json
{
  "conditions": {
    "ready": false,
    "serving": true,
    "terminating": true
  }
}
~~~

This is an example—**not guaranteed on every controller or Pod state**; `serving` depends on Pod readiness and controller sync timing. A `serving+terminating` endpoint must not be misread as `ready` for **new regular traffic**.

## 6. Readiness, Liveness, and Startup Probes

Spring Boot Actuator integrates `ApplicationAvailability` with health probe groups:

- Readiness `ACCEPTING_TRAFFIC`: eligible to receive new requests.
- Readiness `REFUSING_TRAFFIC`: not ready or shutting down; does not imply the app is broken.
- Liveness `CORRECT`: process is healthy or recoverable.
- Liveness `BROKEN`: process is stuck and should be restarted per policy.

These states diverge during startup and shutdown. **During shutdown**: the app may remain **liveness `CORRECT`** so it can finish active requests while **readiness is `REFUSING_TRAFFIC`**. Never configure liveness to fail just because readiness failed, or kubelet may kill the Pod before the drain budget finishes.

Spring Boot Actuator:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Probe paths:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
GET /livez       (on main application port)
GET /readyz      (on main application port)
~~~

Enabling `add-additional-paths=true` exposes `/livez` and `/readyz` on the **same HTTP port as the API**, avoiding situations where a separate management port stays alive while the main app port is dead. Kubernetes environments may auto-enable Boot probes, though setting them explicitly lets us test locally too.

**Before TERM**, `/readyz` returns HTTP 200 UP when ready. **After TERM**, Tomcat may have already closed new accepts, so `curl /readyz` fails to connect rather than returning JSON 503. That does not mean readiness failed to transition: **closing the listener** is part of graceful shutdown.

### Avoid Blindly Coupling Readiness/Liveness to an External DB

If liveness depends on a shared database, a brief DB outage can trigger cluster-wide Pod restarts. If readiness strictly depends on the DB, the entire Service can lose all endpoints. Define carefully which dependencies prevent serving a given traffic class; track dependency health via dedicated metrics and keep liveness focused on process viability.

## 7. Planning the Time Budget Before Writing YAML

The lab's longest request runs **20 seconds**. Example budget:

| Interval | Value | Role |
|---|---:|---|
| Longest intentional lab request | 20s | API bounds `waitMs <= 20000` |
| Spring graceful web phase | 25s | `spring.lifecycle.timeout-per-shutdown-phase=25s` |
| Optional `preStop` for LB route convergence | 5s | Inside Pod grace, *before TERM* |
| Other lifecycle phases + estimated cleanup | 10s | Must be measured on real app |
| Safety margin | 20s | Scheduling/jitter/LB/termination overhead |
| Kubernetes Pod termination grace | **60s** | 5 + 25 + 10 + 20 = 60s |

**Do not treat this table as a universal formula:** adding two extra `SmartLifecycle` phases could allow 25s each, overflowing the "other 10s." Infinite SSE/WebSocket connections can hit the phase timeout. Always measure real shutdown durations, enforce deadlines on work/cleanup, and never stretch grace periods to excuse unbounded work.

### Should You Always Add a preStop Sleep?

No. Kubernetes already marks terminating EndpointSlices `ready=false`. Adding a sleep can help ingress/external LB route propagation in certain infrastructures, but:

- Sleep **does not flip Spring readiness** or close the connector; during `preStop` sleep, the app can still accept direct TCP connections.
- Sleep eats away time available for Spring drain after TERM.
- Long delays slow down rollouts and hold old resources longer during autoscaling.
- Distroless images lacking `/bin/sh` or `sleep` will fail exec hooks.
- Measure actual LB deregistration latency before picking 5 seconds; some stacks need no `preStop`.

In this lab we use **5 seconds** to make the timeline visible, noting it is an **optional example**.

## 8. Complete Lab Project Structure

~~~text
rolling-drain-lab/
  pom.xml
  Dockerfile
  src/
    main/
      java/
        example/
          rollout/
            RollingDrainApplication.java
      resources/
        application.properties
    test/
      java/
        example/
          rollout/
            RollingDrainApplicationTests.java
  k8s/
    deployment.yaml
    service.yaml
~~~

The lab uses **Spring MVC/Tomcat** with synchronous `Thread.sleep` so we can easily observe an in-flight Servlet request. This is an intentional simulation—**never use `Thread.sleep` in production APIs**. Real services need bounded DB/outbound timeouts, concurrency caps, idempotency, and async jobs for long-running work.

### Environment Preparation

- JDK 17+ and Apache Maven installed.
- Docker for building images.
- A lab Kubernetes cluster where you can create Deployments, Services, and Pods (e.g., **kind**, minikube, or a test cluster).
- `kubectl` pointed at the right cluster/namespace—check `kubeconfig` first so you never touch production.
- With `kind`, **load local Docker images** onto the nodes or push to a cluster-accessible registry.
- A Bash terminal for `kill -TERM`, `seq`, and `grep` (on Windows, use WSL or a compatible Linux shell).
- `curl` for HTTP; the cluster needs access to pull a debug client image, or use an org-approved debug image.

The Docker/`kubectl` commands below are **lab instructions**, not runs executed on the reader's cluster.

## 9. Complete Maven pom.xml

Create `rolling-drain-lab/pom.xml`:

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
    <artifactId>rolling-drain-lab</artifactId>
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

`spring-boot-starter-web` provides Spring MVC/Tomcat, `actuator` provides health/readiness/liveness, and `starter-test` provides JUnit 5 and `TestRestTemplate`. The Boot parent manages compatible versions without manually pinning Spring Framework or Tomcat.

`3.3.13` is pinned here to preserve Boot 3.3 semantics. In production, use a supported, patched release aligned with your organization; check graceful defaults and health probe properties whenever upgrading Boot major/minor versions.

## 10. application.properties: Single Place for Shutdown Budget

Create `src/main/resources/application.properties`:

~~~properties
spring.application.name=rolling-drain-lab
server.port=8080

# Boot 3.3: graceful shutdown must be enabled explicitly.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s

# Actuator availability probes exposed directly on main application port.
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true

# Release comes from Docker build ARG -> ENV; Pod name from Downward API.
app.release=${APP_RELEASE:v1}
app.instance=${POD_NAME:local}

# Do not expose raw exceptions/stacktraces in public error responses.
server.error.include-message=never
server.error.include-exception=false
server.error.include-stacktrace=never
~~~

**Version marker:** `APP_RELEASE` is baked into the v1/v2 image env; `POD_NAME` comes from the Kubernetes Downward API. That way, Deployment rollouts only **update the container image** to advance the version marker—avoiding running `kubectl set env` and `kubectl set image` separately and triggering two rollouts.

**Do not confuse:** `server.tomcat.connection-timeout` governs request-line/connector idle timeouts, not how long a controller may run after SIGTERM. `spring.mvc.async.request-timeout` governs MVC async processing and does not make a synchronous controller cancellable.

## 11. Java Application: Tracking Release, Instance, and Active Work

Create `src/main/java/example/rollout/RollingDrainApplication.java`:

~~~java
package example.rollout;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PreDestroy;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RollingDrainApplication {

    public static void main(String[] args) {
        SpringApplication.run(RollingDrainApplication.class, args);
    }

    public record InfoReply(
            String release, String instance, int active) {
    }

    public record SlowReply(
            String release, String instance, String callId,
            long waitMs, long elapsedMs, boolean completed) {
    }

    @RestController
    static class Api {
        private static final Logger log =
                LoggerFactory.getLogger(Api.class);

        private final String release;
        private final String instance;
        private final AtomicInteger active = new AtomicInteger();

        Api(@Value("${app.release:v1}") String release,
            @Value("${app.instance:local}") String instance) {
            this.release = release;
            this.instance = instance;
        }

        @GetMapping("/api/info")
        public InfoReply info() {
            return new InfoReply(
                    release, instance, active.get());
        }

        @GetMapping("/api/slow")
        public ResponseEntity<?> slow(
                @RequestParam(defaultValue = "500")
                long waitMs) throws InterruptedException {

            // Demo caps max wait at 20s; disallow unbounded sleep.
            if (waitMs < 0 || waitMs > 20000) {
                return ResponseEntity.badRequest().body(
                    Map.of("error", "waitMs must be 0..20000"));
            }

            final String callId = UUID.randomUUID().toString();
            final long started = System.nanoTime();
            int inflight = active.incrementAndGet();

            log.info(
                "slow-start release={} instance={} id={} "
                    + "waitMs={} active={}",
                release, instance, callId, waitMs, inflight);

            try {
                Thread.sleep(waitMs);
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - started);

                log.info(
                    "slow-done release={} instance={} id={} "
                        + "elapsedMs={}",
                    release, instance, callId, elapsedMs);

                return ResponseEntity.ok(new SlowReply(
                    release, instance, callId,
                    waitMs, elapsedMs, true));
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                log.warn(
                    "slow-interrupted release={} instance={} id={}",
                    release, instance, callId);
                throw ex;
            } finally {
                int remaining = active.decrementAndGet();
                log.info(
                    "slow-cleanup release={} instance={} "
                        + "id={} active={}",
                    release, instance, callId, remaining);
            }
        }

        @PreDestroy
        void onDestroy() {
            log.info(
                "resources-destroying release={} instance={} "
                    + "active={}",
                release, instance, active.get());
        }
    }
}
~~~

### Code Walkthrough

- `/api/info` returns the release, Pod name, and active request count on **this instance**. When called through a Service, the load balancer may hit a **different Pod on every call**; to inspect a specific Pod during drain testing, target the Pod IP from a debug Pod or correlate logs.
- `/api/slow?waitMs=12000` holds one Servlet worker thread for 12 seconds. This **blocking demo** in Spring MVC makes graceful drain of an in-flight request easy to observe. Never use `Thread.sleep` for long production work.
- `active.incrementAndGet()` runs right after validation, and `decrementAndGet()` in `finally` keeps the counter accurate on both success and interruption.
- `slow-start`, `slow-done`, `slow-cleanup`, and `resources-destroying` logs let us distinguish completed work from bean destruction.
- `callId` correlates start/done logs inside a Pod; this generated UUID is not a business idempotency key.
- The HTTP response reports the **v1 or v2 release of the Pod that handled it**; Kubernetes never rewrites it mid-flight. A request started on v1 and finished during drain returns `release=v1` even while the Service begins routing new traffic to v2.
- `@PreDestroy` only observes cleanup; **never sleep inside `@PreDestroy` to wait for requests**. Boot's built-in graceful web shutdown awaits in-flight requests in its earlier lifecycle phase.
- Success responses arrive only if the client stays connected. Logging `slow-done` does not by itself prove TCP bytes reached the browser—check client status and errors too.

### Example JSON Outputs

`GET /api/info` on a v1 Pod:

~~~json
{
  "release": "v1",
  "instance": "rolling-drain-lab-7c49f9b79c-k8d2n",
  "active": 0
}
~~~

The Pod name is **illustrative**. Running locally, `instance` defaults to `local`.

`GET /api/slow?waitMs=12000` completing on a v1 Pod:

~~~json
{
  "release": "v1",
  "instance": "rolling-drain-lab-7c49f9b79c-k8d2n",
  "callId": "d3bd11b9-e7c4-49ec-a281-e2fbcbf12b4d",
  "waitMs": 12000,
  "elapsedMs": 12003,
  "completed": true
}
~~~

`elapsedMs` is illustrative; real runs vary with scheduling/GC jitter—never assert exact `12003ms`. Invalid `waitMs` returns HTTP 400 immediately without sleeping.

## 12. In-JVM Unit/Integration Smoke Tests

Create `src/test/java/example/rollout/RollingDrainApplicationTests.java`:

~~~java
package example.rollout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "app.release=test-v1")
class RollingDrainApplicationTests {

    @Autowired
    TestRestTemplate http;

    @Test
    void infoContainsTestRelease() {
        ResponseEntity<RollingDrainApplication.InfoReply> r =
                http.getForEntity(
                    "/api/info",
                    RollingDrainApplication.InfoReply.class);

        assertEquals(HttpStatus.OK, r.getStatusCode());
        assertNotNull(r.getBody());
        assertEquals("test-v1", r.getBody().release());
        assertTrue(r.getBody().active() >= 0);
    }

    @Test
    void shortRequestFinishesWithSameRelease() {
        ResponseEntity<RollingDrainApplication.SlowReply> r =
                http.getForEntity(
                    "/api/slow?waitMs=30",
                    RollingDrainApplication.SlowReply.class);

        assertEquals(HttpStatus.OK, r.getStatusCode());
        assertNotNull(r.getBody());
        assertEquals("test-v1", r.getBody().release());
        assertEquals(30L, r.getBody().waitMs());
        assertTrue(r.getBody().completed());
    }

    @Test
    void rejectsUnboundedWait() {
        ResponseEntity<String> r =
                http.getForEntity(
                    "/api/slow?waitMs=25000", String.class);

        assertEquals(HttpStatus.BAD_REQUEST, r.getStatusCode());
    }

    @Test
    void readinessIsUpBeforeShutdown() {
        ResponseEntity<String> r =
                http.getForEntity("/readyz", String.class);

        assertEquals(HttpStatus.OK, r.getStatusCode());
        assertNotNull(r.getBody());
        assertTrue(r.getBody().contains("UP"));
    }
}
~~~

These tests use `RANDOM_PORT`, opening a real HTTP socket without colliding with port 8080. They verify endpoints, version marker config, validation, and **pre-shutdown** readiness.

**Never claim this JUnit suite tested graceful shutdown.** It does not send SIGTERM to a running JVM with an active slow request. Use the process-level and Pod-level tests below to prove draining.

Run:

~~~bash
mvn clean verify
~~~

With compatible Java 17/Maven/dependencies, Maven builds:

~~~text
target/rolling-drain-lab-0.0.1-SNAPSHOT.jar
~~~

Check test counts and results in the actual Surefire report rather than fabricating a fixed transcript.

## 13. Local SIGTERM Test Before Kubernetes

Goal: **an 8-second request enters the controller before SIGTERM**; after TERM, Tomcat stops accepting new requests while the in-flight request completes within the 25s shutdown phase.

Run the JAR locally in a Linux/WSL/macOS terminal:

~~~bash
java -jar target/rolling-drain-lab-0.0.1-SNAPSHOT.jar
~~~

In a second terminal:

~~~bash
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/api/info
curl -i "http://localhost:8080/api/slow?waitMs=200"
~~~

To test `SIGTERM`, **make sure no other server holds port 8080**. Run this standalone Bash script from the project root (not part of the Java app):

~~~bash
#!/usr/bin/env bash
set -euo pipefail

JAR="target/rolling-drain-lab-0.0.1-SNAPSHOT.jar"
java -jar "$JAR" > rolling-drain.log 2>&1 &
APP_PID=$!

ready=false
for i in $(seq 1 45); do
    if curl -fsS "http://localhost:8080/readyz" \
            >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 1
done

if [ "$ready" != true ]; then
    echo "App not ready; inspect rolling-drain.log"
    kill -TERM "$APP_PID" 2>/dev/null || true
    exit 1
fi

curl -fsS --max-time 25 \
    "http://localhost:8080/api/slow?waitMs=8000" \
    > local-inflight.json &
CALL_PID=$!

# Confirm this exact instance holds the work, avoiding premature TERM.
started=false
for i in $(seq 1 40); do
    if curl -fsS "http://localhost:8080/api/info" \
            2>/dev/null | grep -q '"active":1'; then
        started=true
        break
    fi
    sleep 0.2
done

if [ "$started" != true ]; then
    echo "Slow request was not observed active; do not claim PASS"
    kill -TERM "$APP_PID" 2>/dev/null || true
    wait "$CALL_PID" || true
    exit 1
fi

kill -TERM "$APP_PID"
echo "Attempt NEW request after TERM:"
curl -i --max-time 2 "http://localhost:8080/api/info" || true

wait "$CALL_PID"
cat local-inflight.json
echo
wait "$APP_PID" || true
tail -n 40 rolling-drain.log
~~~

Expected:

- The 8s curl receives `completed=true` and `release=v1` while staying connected.
- Logs show `slow-start`, `slow-done`, and `slow-cleanup` before `resources-destroying` once drain completes.
- The **new** request after TERM reports connection refused/reset (or hits a signal-boundary race); HTTP 503 is not mandatory on Tomcat.
- Wall-clock shutdown time stays within observed bounds rather than taking an exact 25,000ms.
- If the script never sees `active=1` due to a port collision or an early completion, the test is **inconclusive/invalid**. Clean up old processes, ensure port 8080 is free, and re-run.

**Never use `kill -9` to test graceful shutdown**: SIGKILL skips JVM shutdown hooks. IDE Stop buttons or Windows `Stop-Process` may terminate differently from Linux `TERM`; test signals on Linux/WSL/containers.

## 14. Dockerfile with Version Marker and JVM Receiving SIGTERM

Create `Dockerfile`:

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app
COPY target/rolling-drain-lab-0.0.1-SNAPSHOT.jar app.jar

ARG RELEASE=v1
ENV APP_RELEASE=${RELEASE}

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

**Why written this way?**

- Exec-form `ENTRYPOINT` delivers stop signals directly to `java` as the container process, avoiding a wrapper shell swallowing `TERM`.
- `ARG RELEASE` sets the version during `docker build`; `ENV APP_RELEASE` embeds the marker in the image. Building v2 only changes the build arg/tag and `kubectl set image`.
- `eclipse-temurin:17-jre` includes `/bin/sh` and `sleep` for the lab's `preStop` hook. Distroless images require a different hook mechanism.
- Never launch Java via `sh -c "java -jar ... &"`, where the shell fails to wait on its child or forward `TERM`.

Build two versions from the same codebase for learning:

~~~bash
mvn clean package
docker build --build-arg RELEASE=v1 \
    -t rolling-drain-lab:v1 .

docker build --build-arg RELEASE=v2 \
    -t rolling-drain-lab:v2 .
~~~

Both images share **identical code** with distinct release markers. In real production rollouts, v2 introduces new code/schemas; the lab fixes the marker to isolate rollout/drain behavior from app compatibility.

With a default `kind` cluster named `kind`:

~~~bash
kind load docker-image rolling-drain-lab:v1
kind load docker-image rolling-drain-lab:v2
~~~

On minikube, remote clusters, or other containerd setups, push/load images per your cluster workflow. Never assume local laptop images exist automatically on Kubernetes nodes, and never push lab images to a production registry without permission.

### Docker Stop Test Without Kubernetes

~~~bash
docker run -d --rm --name rolling-drain-local \
  -p 8080:8080 rolling-drain-lab:v1

# Terminal A: in-flight request:
curl -i "http://localhost:8080/api/slow?waitMs=8000"

# Terminal B: once the request is inside the app:
docker stop -t 40 rolling-drain-local
~~~

Both terminals must overlap **concurrently**; stopping after curl exits proves nothing about draining. `docker stop -t 40` grants 40 seconds before force-kill, exceeding the 25s phase. If the Docker stop signal was customized, check image/runtime config.

## 15. Kubernetes Service: One Stable Address Across Pods

Create `k8s/service.yaml`:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: rolling-drain-lab
spec:
  type: ClusterIP
  selector:
    app: rolling-drain-lab
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
~~~

`Service` selects Pods labeled `app: rolling-drain-lab`, providing internal DNS `rolling-drain-lab` in the namespace and forwarding Service port 80 to container port 8080.

**Never change the Service selector between v1 and v2** during a Deployment rolling update. Both old and new Pods share the same `app` label; readiness/EndpointSlices and Deployment strategy govern which endpoints take new traffic. Blue-green deployments with two separate Deployments/selectors or traffic-switching policies are a different strategy.

## 16. Kubernetes Deployment: Rolling Update with Bounded Availability

Create `k8s/deployment.yaml`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rolling-drain-lab
spec:
  replicas: 3
  revisionHistoryLimit: 4
  minReadySeconds: 5
  progressDeadlineSeconds: 240

  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0

  selector:
    matchLabels:
      app: rolling-drain-lab

  template:
    metadata:
      labels:
        app: rolling-drain-lab
    spec:
      terminationGracePeriodSeconds: 60

      containers:
        - name: app
          image: rolling-drain-lab:v1
          imagePullPolicy: IfNotPresent

          ports:
            - name: http
              containerPort: 8080

          env:
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name

          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 2

          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3

          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 30

          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]

          resources:
            requests:
              cpu: "100m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
~~~

### Reading the Deployment Accurately

- `replicas: 3`: desires 3 serving Pods instead of a single JVM.
- `maxSurge: 1`: allows creating one extra Pod during rollout, avoiding taking an old Pod down before spare capacity starts.
- `maxUnavailable: 0`: ensures desired replicas stay available during updates; **does not guarantee** sufficient cluster CPU, accurate ingress routing, or zero 5xxs.
- `minReadySeconds: 5`: requires a new Pod to stay Ready for 5s before counting as Available; this is not a drain timer.
- `progressDeadlineSeconds: 240`: marks `ProgressDeadlineExceeded` if the rollout stalls; does not auto-roll back or heal bugs.
- `terminationGracePeriodSeconds: 60`: total termination budget, including `preStop`.
- `preStop sleep 5`: illustrates route convergence delay in the lab; **optional**—measure before using in production.
- `readinessProbe` checks `/readyz`, `livenessProbe` checks `/livez`, and `startupProbe` protects startup. Keeping them distinct prevents readiness blips from triggering restarts.
- `POD_NAME` injected via Downward API so `/api/info` identifies each Pod.
- `resources` are illustrative; size from real traffic, GC, threads, and memory footprints.
- `imagePullPolicy: IfNotPresent` works with pre-loaded local `kind` images; never deploy mutable tags in production without digest pinning.

The lab YAML uses no separate management port; Actuator's additional probe paths run on port 8080. If Spring Security is added, allow kubelet health probes through without exposing sensitive Actuator endpoints.

## 17. Deploying v1 and Checking the Baseline

Once `v1` is built and loaded onto the lab cluster:

~~~bash
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/deployment.yaml

kubectl rollout status deployment/rolling-drain-lab \
    --timeout=240s

kubectl get deployment rolling-drain-lab
kubectl get pods -l app=rolling-drain-lab -o wide
kubectl get endpointslices \
    -l kubernetes.io/service-name=rolling-drain-lab
~~~

You should see 3 Ready/Available Pods. If Pods hit `ImagePullBackOff`, check image tags and cluster loading; if `CrashLoopBackOff`, inspect startup logs. If readiness never turns UP, check `/readyz`, `startupProbe`, port mappings, and `application.properties`.

### Smoke-Testing via the Service

A convenient local curl test uses **port-forward** to the Service:

~~~bash
kubectl port-forward service/rolling-drain-lab 8080:80
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/api/info
curl -i "http://localhost:8080/api/slow?waitMs=300"
~~~

`kubectl port-forward service/...` is fine for quick API checks, **not a load balancer availability/performance test**. Port-forward often tunnels to one selected Pod; if that Pod terminates, the port-forward session drops. Never run requests over `port-forward` during a rollout and claim the Service had downtime—use an in-cluster client hitting Service DNS or a real Ingress.

### Checking Pod Versions via Logs

~~~bash
kubectl logs deployment/rolling-drain-lab --tail=30
kubectl get pods -l app=rolling-drain-lab -o wide
~~~

With multiple replicas, `kubectl logs deployment/...` picks one Pod; to inspect a specific Pod, run `kubectl logs pod/NAME` and correlate by `instance`/`callId`. Never merge unlabeled Pod logs and guess which Pod handled a request.

## 18. Experiment 1 — Old Pod Receives TERM Mid-Request

**This is the most decisive test proving graceful shutdown**, isolated from variable image-rollout timing. We start a slow request directly against a **Pod IP** from an in-cluster debug Pod, confirm the request is active, and delete that exact Pod. The ReplicaSet creates a replacement, while the already-accepted request finishes on the old Pod if draining works.

### 18.1. Create an In-Cluster Debug Client

~~~bash
kubectl run drain-client \
  --image=curlimages/curl:8.11.1 \
  --restart=Never \
  --command -- sleep 3600

kubectl wait --for=condition=Ready pod/drain-client \
  --timeout=120s
~~~

The cluster must be able to pull `curlimages/curl:8.11.1`, or substitute an approved debug image. The Pod simply stays idle with `curl` available to call Service/Pod IPs inside the cluster.

### 18.2. Pick One v1 Pod and Get Its Pod IP

~~~bash
OLD_POD=$(kubectl get pods \
  -l app=rolling-drain-lab \
  -o jsonpath='{.items[0].metadata.name}')

OLD_IP=$(kubectl get pod "$OLD_POD" \
  -o jsonpath='{.status.podIP}')

echo "Testing pod: $OLD_POD / $OLD_IP"
~~~

Verify `OLD_POD` is Running/Ready and on v1. If the namespace hosts multiple workloads, run inside the dedicated lab namespace with exact selectors.

### 18.3. Start a 12-Second Request on the Old Pod

Run in a Bash terminal:

~~~bash
kubectl exec drain-client -- \
  curl -fsS --max-time 30 \
  "http://$OLD_IP:8080/api/slow?waitMs=12000" \
  > pod-inflight.json &
CALL_PID=$!
~~~

Calling the **Pod IP directly** bypasses Service load balancing intentionally so the destination stays pinned even after Kubernetes drops the endpoint from the Service; **production clients must never call Pod IPs directly**.

### 18.4. Confirm the Request Entered the Controller First

~~~bash
seen=false

for i in $(seq 1 40); do
  if kubectl exec drain-client -- \
       curl -fsS --max-time 2 \
       "http://$OLD_IP:8080/api/info" \
       | grep -q '"active":1'; then
    seen=true
    break
  fi
  sleep 0.2
done

if [ "$seen" != true ]; then
  echo "Slow request was not confirmed active; test inconclusive"
else
  echo "Confirmed in-flight request on $OLD_POD"
fi
~~~

Never run `kubectl delete pod` before confirming `active:1`: if `curl` stalled starting up or hit the wrong Pod, deleting too early tests only refusal—**not in-flight drain**.

### 18.5. Delete That Exact Pod

Only after `seen=true`:

~~~bash
kubectl delete pod "$OLD_POD" --wait=false

kubectl get pods -l app=rolling-drain-lab -w
~~~

`--wait=false` returns immediately while the container walks through its terminating lifecycle. Here, `preStop sleep 5` runs before TERM, leaving Boot's 25s graceful phase to finish the request. For a ~12s total request, TERM usually arrives mid-execution well inside the budget (exact timings vary by scheduler/cluster).

In the terminal holding `CALL_PID`:

~~~bash
wait "$CALL_PID"
cat pod-inflight.json
echo
~~~

**Acceptance criteria for PASS:** `curl` from the debug Pod receives HTTP 200 with `"release":"v1"` and `"completed":true`; old Pod logs (captured before deletion completes) show `slow-start`, `slow-done`, and `slow-cleanup` prior to exit. The ReplicaSet brings up a replacement Pod with no Service selector changes.

**FAIL or inconclusive outcomes:**

- `curl` drops or exits nonzero: check TERM timing, `preStop`, grace period, OOMKill, pod networking, direct-IP routing, client timeout, and exceptions.
- The request finished **before the Pod actually received TERM**: it succeeded, yet **did not prove Spring graceful drain**. Compare log timestamps against Pod termination events; re-test with a longer duration (within 20s) or shorter lab `preStop`.
- The Pod wasn't deleted or the `kubectl exec` session dropped due to API server issues: do not blame Boot graceful shutdown without evidence.
- The Pod vanished before logs were captured: use centralized logging or stream `kubectl logs` while the Pod exists; Kubernetes cannot always retrieve logs from deleted Pods.

### 18.6. Inspecting EndpointSlices

While the Pod is terminating, run:

~~~bash
kubectl get endpointslices \
  -l kubernetes.io/service-name=rolling-drain-lab \
  -o yaml
~~~

Look for `ready`, `serving`, and `terminating` conditions on the old Pod alongside the remaining ready endpoints. Endpoints can be updated quickly, so a single snapshot might miss transient states—combine logs, events, and metrics rather than guessing from one poll.

**Key distinction:** a terminating Pod can still be **`serving` an existing request** while **`ready=false`** keeps new regular traffic off it. That is by design, not a contradiction.

## 19. Experiment 2 — Actual Rolling Update from v1 to v2

Once the ReplicaSet has restored 3 Ready v1 Pods after the deletion test, roll out the new image.

### 19.1. Ensure v2 Exists on Cluster Nodes

~~~bash
docker build --build-arg RELEASE=v2 \
  -t rolling-drain-lab:v2 .

kind load docker-image rolling-drain-lab:v2
~~~

On non-kind clusters, push `v2` to the configured registry and update the image reference accordingly. Confirm the **new image embeds `APP_RELEASE=v2`**.

### 19.2. Update the Deployment with One Image Change

~~~bash
kubectl set image deployment/rolling-drain-lab \
  app=rolling-drain-lab:v2

kubectl rollout status deployment/rolling-drain-lab \
    --timeout=240s
~~~

A **single image mutation** drives the rollout. Never follow up with `kubectl set env APP_RELEASE=v2`, because the v2 image already embeds its marker and adding a separate env mutation triggers a second rollout.

### 19.3. Watch the Rollout

~~~bash
kubectl get pods -l app=rolling-drain-lab -w
kubectl describe deployment rolling-drain-lab
kubectl rollout history deployment/rolling-drain-lab
kubectl get replicasets -l app=rolling-drain-lab
kubectl get endpointslices \
  -l kubernetes.io/service-name=rolling-drain-lab
~~~

As a new Pod warms up and becomes Ready/Available, the Deployment retires an old Pod; total Pods temporarily exceed 3 due to `maxSurge` and terminating Pods. Seeing both v1 and v2 **mid-rollout** is normal—what matters is that the Service keeps ready endpoints and requests are not dropped outside budget.

### 19.4. Verify New Requests After Rollout

Via the debug Pod targeting Service DNS:

~~~bash
kubectl exec drain-client -- \
  curl -fsS --max-time 5 \
  http://rolling-drain-lab/api/info
~~~

Once the rollout completes and old v1 Pods finish retiring from regular traffic, responses return `"release":"v2"`. If v1 still answers, check rollout status, stale keep-alive clients, Service endpoints, image cache, labels, or mutable tags.

**Never promise** that a request already running on v1 before the rollout will magically return `v2`. An in-flight request on v1 stays v1 until completion/drain—that is correct.

## 20. Measuring Continuous Availability During a Rolling Update

One check before and one check after a rollout do not prove there were zero drops in between. Run a **continuous request loop** against the Service from an **in-cluster client** or real ingress:

~~~bash
# Terminal 1: 100 sequential requests via Service DNS.
for i in $(seq 1 100); do
  kubectl exec drain-client -- \
    curl -sS -f \
    -o /dev/null \
    -w "status=%{http_code} total=%{time_total}\n" \
    --max-time 3 \
    "http://rolling-drain-lab/api/info" \
    || echo "request-failed i=$i"
  sleep 0.1
done
~~~

In a second terminal, trigger the `v1 → v2` rollout while the loop runs. Expected:

- Mid-rollout responses come from either v1 or v2, preserving compatibility/SLOs.
- Once finished, new responses come strictly from v2.
- Any 5xx, nonzero `curl` exit, connection reset, or timeout requires investigation. Note that `kubectl exec` adds CLI/control-plane overhead, so never treat CLI exec timings as a real latency benchmark.
- To measure p95/p99 latency and concurrency accurately, use a real load generator (k6, Gatling, hey, wrk, JMeter) in authorized staging against idempotent test routes within safe limits.
- Testing over `kubectl port-forward Service` is unstable because the tunnel binds to a single Pod that can disappear mid-rollout.

**Never run heavy load tests against production without an approved change window and traffic budget.** This lab uses single/low-rate requests to verify mechanics cleanly.

## 21. Why Zero Downtime Does Not Come Automatically from maxUnavailable=0

Suppose all three v1 Pods sit at 90% CPU, the cluster lacks capacity to schedule the v2 surge Pod, or v2 readiness reports UP before caches warm up. Even with `maxUnavailable=0`, the rollout can stall, degrade, or cause user errors at the gateway.

Essential prerequisites:

- **Replica count:** one replica provides no buffer for rolling replacement; multiple replicas support availability.
- **Scheduler capacity:** headroom for `maxSurge` Pods; quotas, affinity/anti-affinity, or node exhaustion stall rollouts.
- **Accurate readiness:** v2 reports UP only when ready to serve real traffic, not merely after binding a port.
- **Startup budget:** `startupProbe`/liveness must not kill Pods before boot finishes.
- **Load balancer deregistration:** old endpoints drop out cleanly on termination; measure external LB/ingress propagation lag.
- **Grace budget:** active requests finish inside remaining time after `preStop`/TERM.
- **Capacity shift:** as old Pods drain, traffic shifts to remaining Pods; if already saturated, 5xx/latency spikes.
- **Database compatibility:** v1 and v2 coexist during rollouts; schemas and event formats must remain mutually compatible.
- **Client retries:** brief transient glitches can happen; clients should retry safely without duplicating side effects.
- **Long-lived connections:** WebSockets, HTTP/2 streams, SSE, and large uploads follow different lifetimes than short JSON calls.

**`maxUnavailable=0`** constrains Deployment availability accounting—it is not a certificate guaranteeing **the ingress will never emit a 502**.

## 22. Rollback Commands When v2 Misbehaves

If v2 emits 5xxs, fails readiness, or triggers `ProgressDeadlineExceeded`, roll back to the v1 ReplicaSet:

~~~bash
kubectl rollout history deployment/rolling-drain-lab

kubectl rollout undo deployment/rolling-drain-lab

kubectl rollout status deployment/rolling-drain-lab \
  --timeout=240s

kubectl get pods -l app=rolling-drain-lab
~~~

A rollback is itself a **new rolling update back to the previous template**, following the same drain rules. It does not undo database schema migrations, queued messages, or transactions already executed by v2. If v2 performed irreversible side effects, you need a roll-forward or compensation plan.

In production, roll back to a specific revision if needed, verifying image digests and security compatibility first. Never run `kubectl delete pods --all` to "force a quick rollback," which wipes out availability.

### A Database Compatibility Strategy Across Versions

During the rolling window, both releases run simultaneously:

~~~text
v1 writes old-compatible schema
v2 reads both old and new formats
migration expands columns (backward-compatible)
roll out v2
verify
later contract/remove old schema only after v1 is gone
~~~

This is the **expand-and-contract** pattern for schema evolution. Never let v2 drop columns still needed by in-flight v1 requests.

## 23. Logs, Traces, and Metrics Needed to Prove Drain

To separate genuine graceful drain from lucky timing, collect at least:

| Data Point | Question Answered |
|---|---|
| Pod name + release tag | Did v1 or v2 serve the request? |
| `slow-start` timestamp + `callId` | Did the request enter before SIGTERM? |
| `slow-done` + response status | Did the handler finish cleanly? |
| `slow-cleanup active=0` | Did in-flight work drop to zero? |
| Spring graceful shutdown started/completed | Did Boot's drain phase actually run? |
| `resources-destroying` | When did bean cleanup happen? |
| Pod `deletionTimestamp` / termination events | When did Kubernetes start terminating? |
| EndpointSlice conditions | Was the Pod removed from regular traffic routing? |
| Kubelet / container exit reason | Clean exit vs SIGKILL/OOMKill? |
| Ingress / LB access and error logs | 502/503/504, client disconnects, chosen backend |
| JVM/Tomcat threads, active requests | Thread exhaustion or saturation? |
| HTTP p95/p99, error rate | Did user-facing SLOs hold? |

The lab's `callId` UUID is safe for correlating start/done logs; never log request bodies, access tokens, or user PII in production. For distributed tracing, propagate trusted ingress/tracer trace IDs per policy.

### Viewing Kubernetes Events and Logs

~~~bash
kubectl describe pod "$OLD_POD"
kubectl logs "$OLD_POD" --timestamps
kubectl get events --sort-by=.lastTimestamp
kubectl get pods -l app=rolling-drain-lab -o wide
~~~

Commands targeting the old Pod work **only while the Pod still exists**; once deleted, logs may vanish from `kubectl`. Rely on centralized logging/metrics for durable evidence. `kubectl get events` can be noisy; filter by namespace/selector and respect retention policies in production.

### Timing Issues vs HTTP Status Codes

- **NGINX 499** usually means the client closed the connection before receiving a response—not a standard HTTP status sent to browsers.
- **502** usually means the gateway received an invalid upstream response, reset, or protocol failure.
- **503** can come from a Service having zero ready endpoints, an app shedding load, or Undertow graceful shutdown.
- **504** usually means the gateway timed out waiting on upstream, or the app returned 504 on a slow downstream call.
- **`curl` exit 28** indicates a client timeout, possibly with zero HTTP status received.
- Tomcat during graceful shutdown may reject new TCP connections rather than sending HTTP 503.

A status code alone rarely identifies the failing layer; correlate client, ingress, Spring Boot, and backend logs.

## 24. Graceful Shutdown Does Not Guarantee Every Request Succeeds

Edge cases needing explicit design:

### 24.1. Requests Exceeding the Shutdown Phase

A 60-second request against a 25s Spring graceful phase will be cut short; never claim `server.shutdown=graceful` keeps requests alive indefinitely. Enforce business deadlines, retries/idempotency, or offload long jobs asynchronously.

### 24.2. Client Disconnects Before the Handler Finishes

A request can keep executing and commit to the DB after the browser timed out or closed. Logging `slow-done` does not prove the client received the response. Retrying a POST can duplicate work unless protected by idempotency keys, unique constraints, and reconciliation APIs.

### 24.3. SSE, WebSockets, HTTP/2, and Long Polling

SSE and WebSockets often outlive any reasonable grace period. Implement heartbeats, max connection lifetimes, resume IDs, and reconnect/close protocols; HTTP/2 involves stream multiplexing and `GOAWAY` frames. Never test a 12s Servlet MVC call and assume 2-hour WebSockets are safe during rolling updates.

### 24.4. Large Uploads and Downloads

Long transfers can span Pod termination. Use resumable uploads, chunking, direct-to-object-storage transfers, and client retries rather than stretching Pod grace periods globally for one route.

### 24.5. Background Jobs and Consumers

`server.shutdown=graceful` primarily protects in-flight HTTP requests. `@Scheduled`, `@Async`, Kafka/Rabbit/JMS consumers, Quartz, DB transactions, and custom threads manage their own lifecycles. Stop accepting new jobs, finish/ack/commit/cancel within deadlines using `SmartLifecycle`/executor shutdown policies, and design redelivery/idempotency. Never block background shutdown with arbitrary `@PreDestroy Thread.sleep(60000)` lacking metrics or ownership.

### 24.6. Keep-Alive Connections and Stale Routes

Clients may reuse open TCP keep-alive or HTTP/2 connections to an old Pod, and LBs may hold stale routes for a few seconds. New requests right after TERM can hit resets/refusals even while older requests finish. Coordinate `preStop`, network drain, and safe retries, and test under the exact HTTP protocol used in production.

### 24.7. Crash / OOM / SIGKILL

Graceful shutdown runs only when the context closes cleanly. Power loss, kernel OOMs, `kill -9`, or container SIGKILL at grace expiry bypass all Java hooks. Business invariants must survive **unexpected termination**.

## 25. Common Rollout Failure Matrix

| Symptom | Possible Cause | Check / Fix |
| --- | --- | --- |
| In-flight curl resets on TERM | Graceful off on Boot 3.3, JVM missed TERM, or short timeout | Check property, `ENTRYPOINT`, logs, and budgets |
| v1 Pod receives new traffic for seconds | Slow LB/ingress propagation, stale keep-alive, Service routing | Check EndpointSlice, ingress logs, tune `preStop`/drain |
| 502 spikes during rollout | Gateway routes to Pod with closed listener | Audit endpoint deregistration and stale LB routes |
| 503 spikes before new Pods turn ready | Too few ready endpoints, broken readiness, low capacity | Check `maxSurge`/`maxUnavailable`, `startupProbe`, HPA |
| 504 spikes | App/downstream slower than gateway idle/total timeout | Trace critical path and align per-hop timeouts |
| `ImagePullBackOff` | Image not loaded/pushed or registry auth failure | Run `kind load docker-image` or check pull secrets |
| `CrashLoopBackOff` | Startup config/port/heap error | Inspect `kubectl logs`/describe and JVM errors |
| Rollout stalls | New Pod not Available, quota/affinity/capacity blocks | Check Deployment conditions, events, readiness |
| App logs lack graceful messages | Property unset, JVM missed TERM, shell wrapper launcher | Check Boot 3.3 property, PID 1, and stop signal |
| `@PreDestroy` logs before `slow-done` | Request hit another Pod, phase timed out, or abnormal lifecycle | Compare `callId`/Pod, timestamps, and active metrics |
| `port-forward` drops when deleting Pod | Tunnel pinned to deleted Pod | Run in-cluster Service requests for availability checks |
| Request finishes before TERM arrives | Test failed to overlap termination | Check timestamps; lengthen work within bounds |
| CPU/latency spikes mid-rollout | Remaining Pods overloaded, cold caches | Add replicas, warm up, adjust surge, load test |
| Liveness fails whenever readiness fails | Misconfigured shared health probes | Isolate `/livez`, avoid fragile DB checks |
| `preStop` burns the entire grace period | Hook sleeps too long; TERM arrives late | Rebalance termination time budget |
| SIGKILL before cleanup finishes | Pod grace shorter than `preStop` + phases | Raise grace based on measurements or shorten work |
| v2 image still reports `v1` | Forgot Docker build arg, cache hit, or stale tag | Check image digest/ENV, rollout history, Pod describe |
| v2 hits schema errors with v1 in-flight | Non-backward-compatible migration | Use expand-contract and rollback plan |
| Duplicate POST on client retry | Timeout after DB commit before response arrived | Add idempotency keys and status lookup |

**Proper triage flow:** inspect user-facing symptom → identify gateway/app/client owner → align Pod/EndpointSlice timelines → check grace/timeouts/hard kills → inspect active work and side effects → fix the right layer → re-verify. Never crank up every timeout and delete health probes just to turn a rollout green.

## 26. Comprehensive Test Matrix

| Case | How to Test | What to Prove |
| --- | --- | --- |
| v1 baseline | Apply Deployment/Service | 3 ready Pods, `/info` reports `v1` |
| Startup readiness | `/readyz` + `startupProbe` | Traffic arrives only once truly ready |
| Local SIGTERM | 8s in-flight + `kill -TERM` | Old request completes before context exits |
| New connection after TERM | `curl /info` to same process | New work refused (connection refused/reset) |
| Pod deletion mid-flight | Call Pod IP 12s, verify `active`, delete Pod | Returns `v1` 200 if within drain budget, logs correlate |
| Terminating EndpointSlice | `get endpointslices -o yaml` | `ready=false` and `terminating=true` observed |
| Replica replacement | Delete one Pod | ReplicaSet brings up Ready replacement |
| Rolling `v1→v2` | Set image `v2` | Deployment rollout completes |
| Rollout availability | In-cluster Service curl loop | Error rate stays within budget |
| Post-rollout | Service `/info` | Returns `v2` |
| Broken v2 readiness | Simulate failing image/config in lab | Rollout does not falsely succeed |
| Rollback `v2→v1` | `rollout undo` | Healthy image restored cleanly |
| Tiny termination grace | Test `terminationGracePeriodSeconds` low in staging | Detects SIGKILL and unfinished work |
| Request > shutdown phase | Longer work in lab extension | Confirms graceful does not wait forever |
| Client abort mid-POST | Idempotent duplicate test | No duplicate mutation |
| Background worker | Stop/cancel/ack test | HTTP graceful doesn't replace worker cleanup |
| SSE/WebSocket/HTTP2 | Protocol-aware clients | Reconnect/drain per protocol policy |
| External ingress | Real HTTPS user path | No duplicate routing errors |
| Resource pressure | Load/scheduler limits | Measure stalls/5xx rather than guessing from YAML |

**Never run scripts containing `kubectl delete pod` in production** without an approved change window, clear owner, rollback plan, and traffic budget. Use lab or staging clusters for fault injection.

## 27. Anti-Patterns and How to Avoid Them

| Mistake | Why It Is Wrong | Better Approach |
| --- | --- | --- |
| Forgetting `server.shutdown=graceful` on Boot 3.3 | Web server can terminate abruptly | Enable explicitly and verify with SIGTERM |
| Treating `maxUnavailable=0` as a zero-downtime guarantee | LBs, errors, and capacity live outside Deployment spec | Run end-to-end SLO tests |
| Sending SIGKILL to test graceful shutdown | SIGKILL skips shutdown callbacks | Use SIGTERM / process-level tests |
| Shell-form Docker entrypoint dropping TERM | JVM never receives stop signal | Use exec-form `ENTRYPOINT` |
| `preStop` sleep 60s with grace 60s | Burns entire budget before TERM arrives | Remember `preStop` shares grace |
| Setting Spring phase 25s and Pod grace 25s | Zero headroom for hooks/cleanup | Measure full lifecycle and add safety buffer |
| Sleeping in `@PreDestroy` to hold requests | Wrong lifecycle ownership, deadlock risk | Rely on built-in graceful web shutdown |
| Relying on readiness without stopping connector | Direct/stale clients still send requests | Combine traffic draining with server refusal |
| Stopping connector without deregistering | LB keeps routing to retiring Pod | Coordinate EndpointSlice/ingress routing |
| Liveness checking shared DB | DB blip restarts entire cluster | Scope liveness to process viability |
| Calling `/readyz` on a separate management port | Management port can stay alive while app port fails | Expose additional paths on main port |
| Testing Pod deletion over `port-forward` | Tunnel dies even while app drains cleanly | Target Pod IP in-cluster for drain test |
| Claiming drain worked just from HTTP 200 | Request may have finished before TERM | Verify start/done/TERM timestamps |
| Expecting every new request to get HTTP 503 | Tomcat refuses at TCP layer | Verify no new accepts without hardcoding 503 |
| Updating image and ENV as two steps | Can trigger two rollouts | Bake release marker into the image |
| Using mutable image tags without digests | Stale cached image causes version confusion | Use immutable tags/digests |
| Ignoring schema compatibility | v1 and v2 overlap live | Expand-contract DB migrations |
| Retrying POST blindly | Duplicates side effects | Idempotency keys |
| Infinite SSE/WS with no max lifetime | Hits drain timeout and drops abruptly | Reconnect/resume strategy |
| Deleting all Pods to roll back | Causes full outage | Controlled `rollout undo` |

## 28. Scalability and Readiness Checks

**Know before rolling out to production:**

- **Application load:** average/peak RPS, p95/p99 tail latency, and longest legitimate in-flight request; size budgets from data.
- **Concurrent requests:** active Servlet threads, queues, connection pools, JDBC acquisitions, and downstream rate limits as serving Pod count shifts mid-rollout.
- **Cold start:** initialization, secrets, TLS, DB migrations, and cache warmup; readiness flips UP only once ready for traffic.
- **Load balancer:** connection draining support, endpoint removal lag, HTTP/2 keep-alive persistence, DNS TTLs, and proxy retries.
- **Pod/node disruption:** voluntary eviction/PDB policies, autoscaling, node drains, and spot/preemptible nodes. `PodDisruptionBudget` helps protect against voluntary disruptions, yet **does not control Deployment rolling updates** the way the Deployment's own `maxUnavailable` does.
- **Graceful timeouts:** count/length of Spring lifecycle phases, `preStop`, Pod termination grace, gateway idle/total timeouts, and client deadlines.
- **Business effects:** DB transactions/callbacks, idempotency, queued events, distributed locks/leases, and emails/payments.
- **Observability:** immutable release + pod labels, correlation IDs, readiness/termination spans, and per-version error rates.
- **Rollback:** immutable revisions/images, backward-compatible DB schemas, rollback thresholds, and on-call ownership.

If a job takes 2 minutes, instead of bumping `terminationGracePeriodSeconds` to 10 minutes across all API Pods, return **202 Accepted + durable job queue + status polling**. Decoupling HTTP request lifetimes from long job lifetimes keeps deployments agile.

## 29. Advanced Exercises

**Exercise 1 — Align real timelines.** Collect timestamps for `slow-start`, Pod `deletionTimestamp`, TERM, `slow-done`, and `resources-destroying`. Prove the request genuinely overlapped TERM; if not, re-run rather than passing an inconclusive test.

**Exercise 2 — Disable graceful in an isolated test image.** Set `server.shutdown=immediate` in a separate lab image and compare long calls and new connections. Never do this in production for "faster restarts."

**Exercise 3 — Shrink Pod grace.** In a test namespace, set `terminationGracePeriodSeconds: 5` with `preStop` 5s and a 12s request; observe what happens and explain why it is unsafe.

**Exercise 4 — Gate readiness accurately.** Add a simulated warmup phase where the Pod binds its port before cache init completes. Hold readiness down until warmup finishes and verify no real traffic lands early.

**Exercise 5 — Lower replica count.** Compare 1 replica vs 3 replicas with `maxUnavailable=0, maxSurge=1` under constant RPS. Measure p99, 5xx, and scheduling friction.

**Exercise 6 — Simulate external LB lag.** With an ingress controller logging requests, count how many hit an old Pod after EndpointSlice marks `ready=false`. Use that to decide whether `preStop 5s` is warranted.

**Exercise 7 — Version skew.** Add a new response field in v2 while staying v1/v2-compatible. Practice expand-contract migrations without dropping old DB columns while v1 still serves.

**Exercise 8 — Long streams.** Build an SSE route with heartbeats and a max lifetime; observe how the 25s graceful phase affects it and design `EventSource` `Last-Event-ID` reconnection.

**Exercise 9 — Idempotent POST.** Simulate a POST committing to the DB right before client disconnect; use an idempotency key so a client retry landing on v2 does not create a duplicate.

**Exercise 10 — Fault injection.** Intentionally break readiness on v2 in the lab. Verify the Deployment refuses to mark the rollout successful, observe `ProgressDeadlineExceeded`, and run `rollout undo`.

## 30. Self-Check Questions with Answers

**1. Does RollingUpdate automatically wait for an active controller method to finish?**  
No. Kubernetes orchestrates Pods/endpoints; Spring Boot graceful shutdown lets the old process await in-flight HTTP requests.

**2. Which property must be enabled on Spring Boot 3.3?**  
`server.shutdown=graceful`.

**3. Does `spring.lifecycle.timeout-per-shutdown-phase=25s` guarantee the JVM exits in 25s?**  
No. It bounds one lifecycle phase; `preStop` and other lifecycle phases/cleanup add to total time.

**4. Is a 5s `preStop` added on top of `terminationGracePeriodSeconds`?**  
No. It runs inside and consumes Pod termination grace.

**5. Is a Terminating Pod guaranteed to disappear instantly from every load balancer?**  
No. EndpointSlice sets `ready=false` for normal traffic, yet propagation is asynchronous.

**6. Why is Tomcat not required to return HTTP 503 after TERM?**  
It can stop accepting at the network layer; clients see connection refused, reset, or EOF.

**7. Does `readiness=false` mean the Pod is dead?**  
No. It can remain alive to finish existing in-flight requests.

**8. Should liveness fail while the app is gracefully shutting down?**  
Not merely because readiness is refusing; doing so can terminate drain early.

**9. If a v1 Pod accepted a request before rollout, can the response carry `v2`?**  
In this lab code, no: the response comes from v1 inside the v1 Pod unless an external proxy/logic intercepts it.

**10. Why embed the version marker inside the image?**  
To avoid build/cache/tag confusion and drive rollouts with a single image update.

**11. Does HTTP 200 over `port-forward` prove zero downtime?**  
No. Port-forward can pin to one Pod; use continuous in-cluster or ingress traffic.

**12. Why test deleting a single Pod before the full `v1→v2` rollout?**  
To deterministically overlap an active request with termination instead of relying on unpredictable rollout timing.

**13. What stops a Service from picking a terminating endpoint for new regular traffic?**  
EndpointSlice/Service dataplane rules using conditions like `ready=false`, subject to propagation and LB behavior.

**14. What proves an old request finished during drain?**  
Request started before TERM, finished after TERM, HTTP 200/complete body, matching `callId`/Pod version, and lifecycle logs.

**15. Why can a request return 200 and still leave a graceful test inconclusive?**  
It might have finished before TERM arrived, failing to prove drain behavior.

**16. Does `maxUnavailable: 0` guarantee zero HTTP errors during rollout?**  
No. It is only a Deployment availability constraint, not coverage for gateways, networks, capacity, or DBs.

**17. Does SIGKILL execute `@PreDestroy`?**  
Not reliably; the process is killed immediately without running Java cleanup.

**18. Why use exec-form `ENTRYPOINT`?**  
So the JVM receives stop signals directly rather than being masked by a non-forwarding shell.

**19. Does rolling back `v2→v1` automatically roll back database migrations?**  
No. Schema and data compatibility must be engineered separately.

**20. Is a POST that timed out on the client safe to retry arbitrarily?**  
No. The DB may have committed; idempotency and status reconciliation are required.

**21. Can infinite SSE or WebSockets hold a Pod draining until timeout?**  
Yes. Enforce connection lifetimes, clean closure, and reconnect protocols.

**22. If 503 appears during a rollout, did Spring Boot definitely return it?**  
No. A gateway with no ready backends or an upstream layer can emit 503.

**23. What happens if the startup probe targets the wrong path?**  
The Pod is treated as unhealthy, restarts repeatedly, or never becomes ready; align `/livez` and `/readyz`.

**24. After a rollback, what should be verified?**  
Active image/release, ready replicas, 5xx/p95/p99, security/DB compatibility, logs, and in-flight/queue status.

## 31. Practical Acceptance Checklist

- [ ] Maven build and JUnit smoke tests run on Java 17+.
- [ ] `server.shutdown=graceful` declared explicitly for Spring Boot 3.3.
- [ ] `spring.lifecycle.timeout-per-shutdown-phase` set and accounted for inside Pod grace.
- [ ] Actuator `/livez` and `/readyz` active on the main app port.
- [ ] Docker exec-form `ENTRYPOINT` receives `TERM`.
- [ ] `v1` and `v2` images carry distinct immutable release markers.
- [ ] Lab cluster loaded/pulled image tags cleanly with zero `ImagePullBackOff`.
- [ ] 3 v1 Pods Ready with matching Service/Deployment labels and selectors.
- [ ] `maxSurge=1`, `maxUnavailable=0`, and `minReadySeconds` understood accurately.
- [ ] Pod `terminationGracePeriodSeconds` budgets for `preStop`.
- [ ] `/api/slow` request confirmed active **before** deleting the targeted old Pod.
- [ ] Any PASS claim for graceful drain backed by logs showing `slow-done` **after TERM** and before exit.
- [ ] `curl` from debug Pod to old Pod IP receives `completed=true` within the drain budget.
- [ ] EndpointSlice `terminating` / `ready=false` observed where timing permits.
- [ ] ReplicaSet brings up a Ready replacement Pod after deleting the old Pod.
- [ ] Rolling update `v1→v2` triggered via a single image update.
- [ ] In-cluster Service curl loop experiences no unexpected 5xx/connection failures beyond budget.
- [ ] After rollout completes, fresh `/api/info` calls return `v2`.
- [ ] Failed rollouts can roll back without breaking DB/state compatibility.
- [ ] Pod-bound `port-forward` not treated as Service-wide availability proof.
- [ ] No hazardous load tests executed against production clusters.
- [ ] Metrics/logs cover release, Pod, in-flight count, TERM/drain, errors, and rollback.

## 32. Official References

- [Spring Boot 3.3 – Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): `server.shutdown=graceful`, `spring.lifecycle.timeout-per-shutdown-phase`, and server-specific rejection behavior.
- [Spring Boot 3.3 – Actuator Endpoints/Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): `ApplicationAvailability`, readiness/liveness health groups, `add-additional-paths`, `/livez`/`/readyz`.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): graceful, lifecycle, actuator health, and server properties.
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): Servlet Tomcat/Reactor Netty/Jetty/Undertow configuration.
- [Spring Framework – Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `SmartLifecycle`, bean destruction, and `@PreDestroy`.
- [Kubernetes – Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): RollingUpdate, `maxSurge`, `maxUnavailable`, `minReadySeconds`, `progressDeadlineSeconds`.
- [Kubernetes – Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): Terminating, `preStop`, SIGTERM/SIGKILL, and shared `terminationGracePeriodSeconds`.
- [Kubernetes – EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/): `ready`, `serving`, `terminating` conditions.
- [Kubernetes – Explore Termination Behavior](https://kubernetes.io/docs/tutorials/services/pods-and-endpoint-termination-flow/): observation of Pod/EndpointSlice draining.
- [Kubernetes – Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/): `preStop` timing.
- [Kubernetes – Health Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): readiness, liveness, startup probing.
- [Kubernetes – Service](https://kubernetes.io/docs/concepts/services-networking/service/): DNS/ClusterIP and endpoint routing.
- [Docker – Dockerfile ENTRYPOINT](https://docs.docker.com/reference/dockerfile/#entrypoint): exec form and signal forwarding.
- [Docker – docker container stop](https://docs.docker.com/reference/cli/docker/container/stop/): TERM/timeout behavior.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): 502/503/504 status semantics.

**Conclusion:** A successful rollout takes more than v2 Pods turning Ready. You must ensure **new requests route only to ready Pods**, **existing requests on v1 complete within budget**, and **both releases coexist safely in flight**. Spring Boot graceful shutdown, Kubernetes EndpointSlices/readiness, Pod termination grace, rolling strategy, logs, and idempotency are interlocking pieces of the same problem.