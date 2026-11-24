# Process Termination Grace Periods and Load Balancer Traffic Draining in Spring Boot

During a Spring Boot rolling update, an old Pod may stop accepting connections too early while the Ingress or external load balancer is still routing requests to it. Users see **502, 503, 504, connection refused, or connection reset** even though the app worked normally before and after the deploy. Conversely, keeping the process alive too long delays rollouts or forces Kubernetes to issue `SIGKILL` when the deadline expires. You must separate two timing windows controlled by different systems:

- **Process termination grace period:** from the moment Pod/container/process termination begins until the JVM exits. In Kubernetes, this is capped by **`terminationGracePeriodSeconds`**, covering **`preStop`**, **`SIGTERM`** handling, **graceful HTTP shutdown**, resource cleanup, and any overhead.
- **Traffic withdrawal duration:** the time it takes **EndpointSlices, Services, kube-proxy, Ingress, service meshes, cloud load balancers, and clients** to update backend state, stop sending new requests, and let existing requests/connections finish. Each layer has its own **propagation delay** and potentially its own **deregistration delay/connection draining**.

This lesson belongs to **Spring Boot - web-runtime → Application Deployment**, directly covering **Process Termination Grace Periods and Load Balancer Traffic Draining**. Examples use **Java 17, Spring Boot 3.3.13, Spring MVC, embedded Tomcat, Spring Boot Actuator, Maven, and Kubernetes**. Sections on AWS ALB, HTTP/2, gRPC, and WebSocket are scoped carefully and do not assume every deployment uses the same load balancer. Example timeouts are illustrative, **not universal optimal values**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the **Pod termination** lifecycle, `preStop`, `SIGTERM`, `SIGKILL`, and process exit.
2. Distinguish **`ReadinessState`**, HTTP `/readyz`, Pod Ready, EndpointSlice `ready`/`serving`/`terminating`, and LB target draining.
3. Understand why **`preStop` consumes part of `terminationGracePeriodSeconds`** rather than extending the deadline.
4. Explain Boot **`server.shutdown=graceful`** and **`spring.lifecycle.timeout-per-shutdown-phase`**, knowing Boot timeouts do not override Kubernetes hard deadlines.
5. Tabulate the independent **clocks/timeouts**: client timeout, proxy timeout, LB deregistration, web request drain, background work, and container termination.
6. Size the **traffic withdrawal** wait via real measurements instead of an arbitrary random sleep.
7. Design rollouts for **short REST calls, long requests, HTTP/1.1 keep-alive, HTTP/2, SSE, WebSocket, and gRPC**.
8. Configure Actuator health probes **`/livez` and `/readyz` on the main web server port**.
9. Run the Java 17/Spring Boot project and test real HTTP with **`@SpringBootTest(RANDOM_PORT)`**.
10. Send **`SIGTERM` with an active in-flight request**, observing completion and process exit.
11. Understand the impact of **Deployment `RollingUpdate`, `maxSurge`, `maxUnavailable`, `minReadySeconds`, capacity, and `PodDisruptionBudget`**.
12. Collect timelines across the app, Kubernetes, Ingress, and external load balancer to explain 5xx responses during rollouts.

Prerequisites: HTTP status codes, Java, Spring Boot, Servlet/Tomcat, Kubernetes Pod/Service/Deployment basics, and reading application logs.

## 2. Defining Commonly Confused Timings

### 2.1. Backend Traffic Withdrawal Delay

**Traffic withdrawal delay** is the interval between an event requesting an instance be removed from normal routing and the moment route-making components **actually stop picking** that instance for new requests. It can span Kubernetes API event propagation, EndpointSlice watchers, proxy worker updates, cloud target registration controllers, and connection reuse.

A proxy that already updated its endpoint list may still finish an **in-flight request** on the old backend; an existing live connection does not automatically mean the proxy is still picking that backend for new requests. Distinguish:
- **Stopping new routing** to the backend.
- **Letting already-sent requests finish**.
- **Keeping existing TCP/HTTP keep-alive connections open**.
- **Closing/force-terminating connections** when the drain deadline expires.

### 2.2. Process Termination Duration

**Process termination duration** covers everything inside the JVM/container:
- receiving `SIGTERM`;
- Spring Boot closing `ApplicationContext`;
- the web server stopping intake of new requests;
- waiting for in-flight requests within the allowed budget;
- stopping background producers/executors;
- closing DB/HTTP pools and files;
- process exit.

Kubernetes enforces a **Pod-level limit** covering the entire sequence including `preStop`. If exceeded, **`SIGKILL`** may follow. The JVM cannot negotiate extra time with kubelet just because a request is still running.

### 2.3. Independent “Clocks”

| Clock | Controlled by | Meaning |
| --- | --- | --- |
| `terminationGracePeriodSeconds` | Kubernetes Pod spec/kubelet | Pod's hard shutdown budget. |
| `preStop` duration | Pod lifecycle hook | Hook execution time, spent **inside** the Pod grace period. |
| Boot graceful timeout | Spring lifecycle | Wait time per `SmartLifecycle` shutdown phase. |
| Application cleanup duration | Spring beans and libraries | Closing pools/executors/files; may have independent deadlines. |
| EndpointSlice update latency | Kubernetes controllers/watchers | Publishing endpoint state into Kubernetes API and consumers. |
| Ingress/LB routing propagation | Ingress/mesh/cloud LB | Time to shift new requests away from the old backend. |
| LB deregistration delay | External LB/provider target group | Time draining targets/connections; independent of Pod deadline. |
| Client/request timeout | Client/gateway/proxy/server | When the caller stops waiting for a response. |
| Stream/session lifetime | HTTP/2, WebSocket, gRPC, SSE | Often much longer than Pod grace. |

Do not sum all values naively, because some steps run **in parallel** and some deadlines sit in separate systems. However, where two timeouts intersect, determine **which timeout expires first on the actual request path**.

## 3. Timeline: Kubernetes Pod Termination and Load Balancer

~~~text
t0: Pod receives deletionTimestamp, grace period begins
 |
 +-- EndpointSlice controllers/watchers receive update
 |      +-- ready=false / terminating=true
 |      +-- kube-proxy, ingress, mesh, LB update routes
 |
 +-- preStop hook (if configured)
 |      +-- JVM is usually still accepting requests
 |      +-- this hook consumes time from the grace budget
 |
 +-- kubelet instructs runtime to send SIGTERM
 |      +-- Spring ApplicationContext begins closing
 |      +-- Boot graceful web server stop
 |      +-- waits for in-flight requests
 |      +-- resource cleanup
 |
 +-- JVM exits
 |
t0 + terminationGracePeriodSeconds:
 if process is still alive, kubelet may send SIGKILL
~~~

This is a generalized diagram. **EndpointSlice propagation and `preStop` are not strictly sequential.** Ingress routes can still be stale when `SIGTERM` arrives, which is why sensitive rollouts often add a **`preStop` buffer** or coordinate with an LB controller. Still, a fixed `preStop` does not guarantee every backend across all zones/proxies has updated.

### 3.1. The Countdown Starts Before preStop

If `terminationGracePeriodSeconds=45` and `preStop=10` seconds, Java **does not get 45 extra seconds after `preStop`**. Assuming zero overhead, only 35 seconds remain. Kubelet has a brief extension behavior in certain cases if `preStop` is still running when the grace period ends, but **never rely on that extension in design**.

Do not set `preStop` `sleep=30` and `terminationGracePeriodSeconds=30` expecting Boot to get 20 seconds of graceful shutdown. Time can run out before the process even receives `SIGTERM`.

### 3.2. SIGTERM and SIGKILL

- **`SIGTERM`** requests graceful termination; Java/Spring can run shutdown hooks and bean destroy callbacks.
- **`SIGKILL`** terminates immediately: no `@PreDestroy`, no flushing transactions or files gracefully.
- **Exit 143** normally corresponds to signal 15 per Unix conventions, and **exit 137** to signal 9; always check Pod status and reason (especially `OOMKilled`) for the real cause.
- **Readiness probe failure** only marks the Pod unready for normal routing; it **does not trigger restarts** like liveness/startup failures.

### 3.3. PID 1 Must Receive the Signal Properly

The Dockerfile should use exec form:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/traffic-drain-demo-0.0.1-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

If a shell-form `ENTRYPOINT` runs via a shell that does not forward `SIGTERM`, Java may miss graceful shutdown completely. If a wrapper script is necessary, use **`exec java -jar /app/app.jar`** so Java replaces the shell. Verify Kubernetes, container runtime, and shell signal behavior on the real image.

## 4. EndpointSlice ready, serving, and terminating

### 4.1. Pod Readiness Does Not Mean the Pod Vanished

Kubernetes EndpointSlices track critical conditions:
- **`ready`**: endpoint is ready for normal routing.
- **`terminating`**: endpoint belongs to a terminating Pod.
- **`serving`**: serving state usable by consumers to drain connections on terminating endpoints.

In modern Kubernetes, a terminating Pod's endpoint has **`ready=false`** for backward compatibility with older consumers, while **`serving` may still be `true`**. This is not a contradiction: the Service stops picking it for regular new traffic, while drain-aware consumers can use `serving` to track endpoints finishing existing connections.

~~~json
{
  "addresses": ["10.0.0.42"],
  "conditions": {
    "ready": false,
    "serving": true,
    "terminating": true
  }
}
~~~

This is an abbreviated JSON illustrating a single endpoint. **Exception:** Services configured with **`publishNotReadyAddresses=true`** have special `ready` semantics; do not assume `ready` is always `false` there.

### 4.2. Kubernetes Does Not Wait for the Next readinessProbe Cycle on Deletion

Kubernetes can update the EndpointSlice as soon as Pod deletion is recorded **without waiting** for `readinessProbe` to fail. Saying “`periodSeconds=5`, `failureThreshold=3` so removing the Pod takes at least 15 seconds” is incorrect for the **Pod termination** path. `readinessProbe` sampling applies to unready transitions while the app is running, whereas Pod deletion has its own endpoint termination flow.

### 4.3. Backend Withdrawal Does Not Happen Simultaneously Everywhere

EndpointSlice consumers (kube-proxy, Ingress, controllers) receive events and update their data planes with real latency. Clients can also hold open HTTP/2 or keep-alive connections. **You cannot prove a backend stopped receiving requests merely by observing `EndpointSlice ready=false` at one instant.**

### 4.4. Observing with kubectl

~~~bash
kubectl get endpointslices \
  -l kubernetes.io/service-name=traffic-drain-demo \
  -o yaml

kubectl get pods -l app=traffic-drain-demo -w
kubectl describe pod POD_NAME
~~~

Replace `POD_NAME` with an actual name. Use timestamped logs and API watches to construct the timeline between `ready`/`serving`/`terminating` and the last request Ingress routed to the old Pod. Deleted Pods may disappear from `kubectl`; centralize logs and capture events during staging rollouts.

## 5. Load Balancer Layers That Can Sit on the Request Path

~~~text
Browser/client
       |
       v
Cloud external LB / CDN
       |
       v
Ingress Controller / API Gateway / Service Mesh
       |
       v
Kubernetes Service / kube-proxy or eBPF data plane
       |
       v
PodIP:8080 -> Spring Boot Tomcat
~~~

Some architectures route an external LB straight to Pod IPs, some use NodePort, some include Envoy sidecars, and some have no Ingress. Thus **do not apply one drain timeout to every architecture**.

### 5.1. Kubernetes Service and Data Plane

Service selectors pick Pods via EndpointSlices. Once `ready=false`, regular new traffic should stop targeting the backend, once the data plane receives and applies the update. In-flight requests may still finish on the removed backend. Measure **routing propagation delay**, not just the readiness endpoint.

### 5.2. Ingress and Service Mesh

An Ingress can hold upstream connection pools and cache route configs. While backends change:
- it can stop selecting the old backend;
- it can keep in-flight requests open;
- it can close idle connections or wait for timeouts;
- it can retry GETs on upstream resets;
- it can emit 502/503 if the backend dies with no healthy endpoints left.

For side-effecting POSTs, **automatic retries without idempotency keys** can cause duplicate orders or payments. Do not reflexively raise retry counts just because rollouts see connection resets.

### 5.3. AWS Application Load Balancer

An AWS ALB target group has a **deregistration delay**; AWS documentation lists **300 seconds by default** when unmodified. When a target deregisters, its state becomes **draining**, then unused upon completion.

**ALB's 300 seconds do not extend a Pod's 45-second `terminationGracePeriodSeconds`.** If kubelet sends `SIGKILL` at 45 seconds, the LB cannot make a dead JVM keep answering. Conversely, a target with no remaining in-flight requests can finish draining early rather than always waiting all 300 seconds.

AWS ALB deregistration delay **differs** from AWS Network Load Balancer; NLB has its own handling for existing TCP connections and connection termination. Verify your exact LB type/provider and version before applying settings.

### 5.4. Why Might an LB Keep Sending Requests After EndpointSlice Updates?

Possible reasons:
- controller has not processed the Kubernetes event yet;
- external LB API target update is still pending;
- ingress workers have not reloaded config;
- connection reuse/HTTP/2 streams continue;
- clients are calling Pod IPs or node endpoints directly;
- network/proxy propagation delays.

Do not confuse “an existing request finished on the old backend” with “the LB still picked the old backend for a new request”: distinguish them via route-selection or target-state logs at the proxy layer.

## 6. Spring Boot 3.3 Graceful Shutdown

### 6.1. Explicit Configuration

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

In Boot 3.3, graceful shutdown supports **Tomcat, Jetty, Reactor Netty, and Undertow**. It runs when `ApplicationContext` closes, in an early **`SmartLifecycle`** stop phase. Tomcat, Jetty, and Reactor Netty generally stop accepting new requests at the network layer; Undertow may immediately return 503 for new requests.

**Do not assume the entire process is guaranteed to exit in 20 seconds.** `timeout-per-shutdown-phase` caps waiting per `SmartLifecycle` phase, while additional phases plus `@PreDestroy` cleanup, DB pool closing, executors, and client shutdown also take time. In deployments, measure actual **`SIGTERM` → process exit** time.

### 6.2. If the Load Balancer Has Not Withdrawn the Pod Yet

When the JVM receives `SIGTERM`, Tomcat starts graceful shutdown and may refuse new requests. If Ingress still routes new requests to that Pod, users see connection refused/502 even while older in-flight requests finish cleanly. Thus **traffic withdrawal** must occur reliably **before** the backend stops accepting new connections at your target SLO percentile.

### 6.3. Readiness and ApplicationAvailability

Spring Boot provides:
- **`LivenessState.CORRECT`/`BROKEN`**.
- **`ReadinessState.ACCEPTING_TRAFFIC`/`REFUSING_TRAFFIC`**.
- **`ApplicationAvailability`** to read state.
- **`AvailabilityChangeEvent.publish`** to broadcast state changes when needed.

During shutdown, Boot can transition readiness to `REFUSING_TRAFFIC`. However, **changing readiness is only a signal**: it does not close sockets, force Ingress to sync immediately, or block direct Pod IP calls. New HTTP requests stop only due to **web server graceful shutdown** or network/proxy routing decisions, not the enum alone.

### 6.4. Actuator /livez and /readyz on the Main Port

Configuration:

~~~yaml
management:
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
~~~

Boot 3.3 exposes:
- `/actuator/health/liveness`
- `/actuator/health/readiness`
- **`/livez`** on the main server port
- **`/readyz`** on the main server port

If `management.server.port` differs from `server.port`, the management connector health endpoint can stay UP even when the main HTTP connector is broken. Exposing additional paths on the main port stays closer to the actual web traffic path. Never place shared DBs/external dependencies in liveness, as restarting Pods rarely fixes upstream outages.

## 7. Calculating the Time Budget

### 7.1. Notation

| Symbol | Quantity |
| --- | --- |
| G | Pod's `terminationGracePeriodSeconds`. |
| P | `preStop` hook duration. |
| L | Routing propagation from Pod termination/EndpointSlice until proxies stop selecting the backend. |
| R | Remaining time for in-flight HTTP requests to finish after `SIGTERM`. |
| A | Background work drain, bean destruction, pool/file cleanup. |
| M | Safety margin for scheduling, GC, network jitter, and sidecars. |
| D | Independent LB deregistration/connection draining timeout, if any. |

A **conservative budget** is:

~~~text
G > P + R + A + M

If using preStop to wait out propagation:
P should cover L at your target percentile + buffer.

L and P can overlap in parallel.
D is an LB-side timeout; it does not extend G.
~~~

Measure each quantity with timestamps. Additional `SmartLifecycle` phases or sidecar teardowns also consume time and belong in the budget. No single-line formula guarantees zero errors across all systems.

### 7.2. Numeric Example

Suppose staging measurements show:
- `L_p99` ≈ 7 seconds.
- `P` = 10 seconds to cover propagation plus buffer.
- Request drain budget `R` = 18 seconds.
- Cleanup `A` = 4 seconds.
- Margin `M` = 8 seconds.

~~~text
P + R + A + M
= 10 + 18 + 4 + 8
= 40 seconds

Try G = 45 seconds in the lab.
Boot graceful phase timeout = 20s.
~~~

**Never pick `G=45` blindly from an example formula.** If requests take 35 seconds, external proxy withdrawal `p99` is 20 seconds, or `@PreDestroy` blocks for 15 seconds, `G` will be too small. If the client timeout is 3 seconds, raising `G` to 60 will not save a client waiting 30 seconds.

### 7.3. Example Timeline

~~~text
t= 0s Pod terminating, grace countdown G=45s
t= 0s EndpointSlice/Ingress/LB update concurrently
t= 0..10s preStop; JVM still serves requests during buffer
t=10s SIGTERM arrives at Java
t=10..28s Boot waits for in-flight HTTP requests
t=28..32s app cleanup
t=32s JVM exits
t=45s hard deadline if JVM is still alive
~~~

Treat these timestamps as illustrative rather than a guarantee: steps can be shorter, longer, or overlap. They illustrate why **`preStop` is not added on top of `G`**, and why budget must remain for post-`SIGTERM` shutdown.

### 7.4. preStop sleep: Benefits and Limits

A `preStop` sleep helps give the data plane time to update before Tomcat closes its connector, yet it:
- does not confirm the LB removed the backend;
- does not guarantee zero incoming traffic;
- does not cancel/complete WebSockets or gRPC streams;
- directly consumes the Pod grace budget;
- fails if the container image lacks `sh`/`sleep`;
- does not act as an explicit deregistration API call for every cloud target controller.

Prefer explicit ingress/LB drain/ack mechanisms where available, or measure propagation repeatedly to pick an **evidence-based buffer**. Never mandate one arbitrary sleep number across an entire organization when apps have distinct traffic and LB paths.

## 8. Handling Different Types of HTTP Requests

### 8.1. Short REST Requests

For fast REST GET/POSTs, web graceful shutdown waits for requests already accepted by Tomcat. Align client/proxy/server timeouts with valid request durations. While the server stops accepting yet proxies remain stale, new requests can fail—that is the `preStop`/LB withdrawal gap to tune.

### 8.2. HTTP/1.1 Keep-Alive

Clients or proxies reuse TCP connections rather than opening a fresh socket per request. During backend draining, proxy behavior on existing keep-alive connections can differ from selecting backends for new connections. Test with connection reuse, not only single-shot `curl` calls.

### 8.3. HTTP/2 and gRPC

HTTP/2 multiplexes multiple streams over one connection; unary gRPC calls and long-lived streaming RPCs have different deadlines and cancellation behaviors. `GOAWAY`/draining semantics depend on server/proxy implementations; do not assume identical `GOAWAY` behavior across all runtimes. Test real clients, gateways, library versions, deadlines, and reconnects.

### 8.4. SSE and WebSocket

SSE/WebSocket connections can stay open for hours. No reasonable `terminationGracePeriodSeconds` waits for every session to close naturally. Instead:
- signal upcoming server drain;
- stop accepting new sessions;
- close connections cleanly so clients reconnect;
- support resume tokens/last-event IDs where needed;
- persist important state before shutdown;
- bound close-handshake duration.

### 8.5. HTTP 202 Detached Jobs

If a REST endpoint returns `202` while an executor continues a long background job, web graceful shutdown does not track that job because the HTTP request already finished. Use durable queues/job state, intake stop, checkpoints, idempotent retries, or worker handoff. Never inflate `G` indefinitely as a substitute for job orchestration.

## 9. Runnable Demo: Spring Boot 3.3, Java 17

The demo provides:
- **`GET /demo/work?delayMs=1000`**: handles an HTTP request with a bounded delay.
- **`GET /demo/state`**: reports `ApplicationAvailability` and current demo in-flight count.
- **`/livez` and `/readyz`** on the main Tomcat port via Actuator.
- **`ContextClosedEvent` log** and `@PreDestroy` log to trace lifecycle timing.
- **JUnit HTTP tests** checking 200, 400, readiness 503, and liveness 200.
- Process-level shell test sending `SIGTERM` while a request is in flight.

### 9.1. Directory Tree

~~~text
traffic-drain-demo/
  pom.xml
  Dockerfile
  src/main/java/com/example/drain/
    DrainApplication.java
    WorkController.java
    ShutdownTimeline.java
  src/main/resources/application.yml
  src/test/java/com/example/drain/
    DrainHttpIntegrationTest.java
~~~

### 9.2. pom.xml

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
    <artifactId>traffic-drain-demo</artifactId>
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

Spring Boot 3.3.13 is the lab baseline, not a guarantee of active support at the time of your production rollout. For new projects, pick a supported, security-patched Spring Boot release.

### 9.3. DrainApplication.java

~~~java
package com.example.drain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DrainApplication {
    public static void main(String[] args) {
        SpringApplication.run(DrainApplication.class, args);
    }
}
~~~

### 9.4. WorkController.java

~~~java
package com.example.drain;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class WorkController {

    private static final Logger log =
            LoggerFactory.getLogger(WorkController.class);

    private final AtomicInteger inFlight = new AtomicInteger();
    private final ApplicationAvailability availability;

    public WorkController(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @GetMapping("/demo/work")
    public Map<String, Object> work(
            @RequestParam(defaultValue = "1200") long delayMs)
            throws InterruptedException {

        if (delayMs < 0 || delayMs > 15000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "delayMs must be 0..15000");
        }

        int active = inFlight.incrementAndGet();
        long start = System.nanoTime();
        log.info("request-start active={} delayMs={}",
                active, delayMs);

        try {
            // Only simulates a slow request, not a benchmark.
            Thread.sleep(delayMs);
            long elapsed =
                    (System.nanoTime() - start) / 1_000_000;

            return Map.of(
                    "status", "completed",
                    "delayMs", delayMs,
                    "elapsedMs", elapsed);
        }
        finally {
            int remaining = inFlight.decrementAndGet();
            log.info("request-end remaining={}", remaining);
        }
    }

    @GetMapping("/demo/state")
    public Map<String, Object> state() {
        return Map.of(
                "readiness",
                availability.getReadinessState().name(),
                "liveness",
                availability.getLivenessState().name(),
                "inFlightDemoRequests",
                inFlight.get());
    }
}
~~~

**Explanation:**
- `AtomicInteger` tracks only the demo endpoint, not all active Tomcat requests.
- `delayMs` has an upper bound of 15 seconds to avoid unbounded sleeping endpoints in the lab.
- Blocking `Thread.sleep` keeps a Servlet worker occupied in flight when `SIGTERM` arrives.
- `finally` decrements the counter even on `InterruptedException`; it makes no promise a request succeeds under a forced kill.
- `ReadinessState` in `/demo/state` is a routing signal. `REFUSING_TRAFFIC` does not make the method return 503 if hit directly before the connector closes.
- **Never expose a delay endpoint on a public production ingress**; it can easily be abused to exhaust request threads.

### 9.5. ShutdownTimeline.java

~~~java
package com.example.drain;

import jakarta.annotation.PreDestroy;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownTimeline {

    private static final Logger log =
            LoggerFactory.getLogger(ShutdownTimeline.class);

    @EventListener
    public void contextClosing(ContextClosedEvent event) {
        log.info("event=context-close-requested");
    }

    @PreDestroy
    public void destroyed() {
        log.info("event=timeline-bean-destroyed");
    }
}
~~~

`ContextClosedEvent` fires when the context begins closing, which does not mean all HTTP requests are finished when that first log line prints. `@PreDestroy` is a single bean callback. These two markers help compare timestamps, **not prove an external LB finished draining**.

### 9.6. application.yml

~~~yaml
spring:
  application:
    name: traffic-drain-demo
  lifecycle:
    timeout-per-shutdown-phase: 20s

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
~~~

Actuator `/livez` and `/readyz` sit on the main web port. If a separate `management.server.port` is added later, verify health groups and main-port additional paths separately. Never expose all Actuator endpoints publicly.

### 9.7. Dockerfile

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/traffic-drain-demo-0.0.1-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Exec-form `ENTRYPOINT` lets Java receive signals from the container runtime. If lifecycle `preStop` uses `sh -c sleep`, verify your actual image has `sh` and `sleep`—many distroless images do not. Never switch to a shell-form `ENTRYPOINT` just to add a sleep.

### 9.8. Build and Run

Linux/macOS:

~~~bash
mvn clean package
java -jar target/traffic-drain-demo-0.0.1-SNAPSHOT.jar
~~~

Windows:

~~~text
mvn.cmd clean package
java -jar target/traffic-drain-demo-0.0.1-SNAPSHOT.jar
~~~

Another terminal:

~~~bash
curl -i http://localhost:8080/demo/state
curl -i "http://localhost:8080/demo/work?delayMs=100"
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/livez
~~~

Once the app is ready, `/demo/state` has the structure:

~~~json
{
  "readiness": "ACCEPTING_TRAFFIC",
  "liveness": "CORRECT",
  "inFlightDemoRequests": 0
}
~~~

`/readyz` and `/livez` normally return **HTTP 200**, JSON **`{"status":"UP"}`**. Sending `delayMs=20000` returns **400**. JSON property order and HTTP Date/Server headers may vary across runs.

## 10. Testing Over Real HTTP with RANDOM_PORT

`MockMvc` tests do not open a Tomcat network connector and thus cannot verify server threads, ports, or `SIGTERM`. The test below uses **`@SpringBootTest(RANDOM_PORT)`**, followed by a separate process-level test for shutdown.

### 10.1. DrainHttpIntegrationTest.java

~~~java
package com.example.drain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationEventPublisher;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class DrainHttpIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    @Autowired
    ApplicationEventPublisher events;

    private String url(String path) {
        return "http://localhost:" + port + path;
    }

    private int status(String path) {
        return http.getForEntity(
                url(path), String.class)
                .getStatusCode().value();
    }

    @Test
    void readinessAndWorkUseRealHttp() {
        assertThat(status("/livez")).isEqualTo(200);
        assertThat(status("/readyz")).isEqualTo(200);
        assertThat(status("/demo/work?delayMs=30"))
                .isEqualTo(200);
        assertThat(status("/demo/work?delayMs=20000"))
                .isEqualTo(400);
    }

    @Test
    void refusingTrafficDoesNotBreakLiveness() {
        try {
            AvailabilityChangeEvent.publish(
                    events, this,
                    ReadinessState.REFUSING_TRAFFIC);

            assertThat(status("/readyz")).isEqualTo(503);
            assertThat(status("/livez")).isEqualTo(200);
            assertThat(http.getForObject(
                    url("/demo/state"), String.class))
                    .contains("REFUSING_TRAFFIC");
        }
        finally {
            AvailabilityChangeEvent.publish(
                    events, this,
                    ReadinessState.ACCEPTING_TRAFFIC);
        }
    }
}
~~~

**Test notes:**
- `TestRestTemplate` returns status 503 directly for assertions instead of throwing an exception via an error handler.
- `AvailabilityChangeEvent.publish` transitions the **readiness health group** to `OUT_OF_SERVICE`/503 while liveness remains `CORRECT`/200.
- Direct HTTP `/demo/state` continues responding before the connector closes, illustrating that readiness is purely a signal.
- The test shares a context with mutable availability; when parallel test execution is enabled, isolate contexts or synchronize to avoid races.
- Never expose a public `/drain` or `/control` toggle endpoint in production.
- This test **does not** test LB propagation, `preStop`, `SIGTERM`, or process exit. Run dedicated deployment tests for those.

Run:

~~~bash
mvn test
~~~

## 11. Testing SIGTERM with an In-Flight Request

Run in a Linux/macOS lab or staging environment—**never in production**. Ensure port 8080 is free:

~~~bash
java -jar target/traffic-drain-demo-0.0.1-SNAPSHOT.jar \
  > server.log 2>&1 &
APP_PID=$!

# Wait for /readyz 200 before sending the request.
curl -fsS http://localhost:8080/readyz

# Slow request sent before SIGTERM.
curl -sS -o long-response.json \
  -w "HTTP=%{http_code} total=%{time_total}\n" \
  "http://localhost:8080/demo/work?delayMs=7000" &
REQ_PID=$!

sleep 1
kill -TERM "$APP_PID"

wait "$REQ_PID"
wait "$APP_PID"
~~~

**Observations to record:**
1. If the request entered Tomcat before `SIGTERM` and completes within the graceful window, it normally returns **HTTP 200**.
2. New requests sent **after** the connector starts closing may fail to connect, depending on server/connection reuse.
3. Inspect `server.log` for `context-close-requested`, Tomcat graceful logs, and `timeline-bean-destroyed`.
4. Measure the duration from `SIGTERM` to process exit; do not assume it always takes 20s.
5. If the request exceeds the graceful deadline or the process gets `SIGKILL`, the response may be lost.
6. The script assumes the app is already ready; in automated tests, retry `/readyz` with a timeout instead of a single call.
7. Windows `Stop-Process` is not always equivalent to POSIX `SIGTERM`; use a Linux container matching production to test signal semantics.

**Never run `kill -9` to “help” the script exit** when measuring graceful shutdown. For hard-kill recovery, run a separate test and label it explicitly as a forced-failure scenario.

## 12. Kubernetes Deployment and Service

### 12.1. Example Deployment

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: traffic-drain-demo
spec:
  replicas: 3
  minReadySeconds: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: traffic-drain-demo
  template:
    metadata:
      labels:
        app: traffic-drain-demo
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: web
          image: registry.example.invalid/traffic-drain-demo:1.0
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
            failureThreshold: 2
            successThreshold: 1
          lifecycle:
            preStop:
              exec:
                command: ["sh", "-c", "sleep 10"]
~~~

**This is an illustrative manifest.** The image at `registry.example.invalid` does not exist; substitute your real registry and image. Your real image must contain `sh` and `sleep` for `preStop` to succeed, or use another supported hook mechanism. Add resource requests/limits, `securityContext`, `ServiceAccount`, RBAC, and network policies per cluster standards.

**Why these choices:**
- 3 replicas can maintain capacity while one Pod leaves rotation, assuming remaining replicas are healthy and sized for load.
- **`maxSurge: 1`**, **`maxUnavailable: 0`** ensures a new Pod comes up before reducing Available replicas. It does not by itself guarantee zero downtime.
- **`minReadySeconds: 5`** requires the new Pod to remain Ready continuously before counting as Available, though it does not check business SLOs.
- **`startupProbe`** lets slow startups finish without premature liveness kills.
- **`readinessProbe`** drives routing; **`livenessProbe`** failing past its threshold triggers restarts.
- **`preStop` `sleep 10s`** is an illustrative buffer before `SIGTERM`, not a universal default for every system.
- **`terminationGracePeriodSeconds: 45`** covers the 10s `preStop` plus subsequent shutdown/cleanup.
- Kubernetes can mark the EndpointSlice `terminating` without waiting for `readinessProbe` to fail twice; do not calculate withdrawal latency solely from `failureThreshold`.

### 12.2. Service

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: traffic-drain-demo
spec:
  selector:
    app: traffic-drain-demo
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
~~~

Build the image:

~~~bash
mvn clean package
docker build -t traffic-drain-demo:1.0 .
~~~

A local tag does not automatically exist at `registry.example.invalid`; tag and push a real image before deploying. Do not apply sample YAML without replacing and verifying image/namespace/quota values.

### 12.3. RollingUpdate Does Not Guarantee Zero Errors

Even `maxUnavailable=0` cannot prevent:
- a new Pod turning Ready too early with cold caches;
- an LB still routing to an old Pod after `SIGTERM`;
- cluster lacking CPU/memory for the surge Pod;
- existing direct connections staying open to old Pods;
- network timeouts or DB bottlenecks;
- WebSocket/gRPC streams exceeding the grace period.

**`PodDisruptionBudget`** governs voluntary disruptions during eviction workflows, not as a replacement or guarantee for every Deployment rollout. Verify controller/version behavior and capacity.

## 13. Measuring Rollouts on Staging

### 13.1. Watch Resources

~~~bash
kubectl get deployments
kubectl get pods -l app=traffic-drain-demo -w
kubectl rollout status deployment/traffic-drain-demo
kubectl describe deployment traffic-drain-demo
kubectl get endpointslices \
  -l kubernetes.io/service-name=traffic-drain-demo \
  -o yaml
~~~

Inspect terminating Pods and EndpointSlice `conditions.ready`/`serving`/`terminating`, correlated with proxy logs. Do not conclude from a single `kubectl get` snapshot that the LB has already synced.

### 13.2. Observe Process Exit and Events

~~~bash
kubectl describe pod POD_NAME
kubectl logs POD_NAME -c web --timestamps
kubectl get pod POD_NAME -o yaml
~~~

Substitute `POD_NAME`. Old Pods may vanish before you query them; use centralized logging and event capture in staging. Inspect `terminated.reason`, `exitCode`, and `OOMKilled`; never assume every exit code 137 is a grace timeout.

### 13.3. Build a Timestamp Table

| Milestone | Definition | Observation source |
| --- | --- | --- |
| t0 | Pod `deletionTimestamp` | K8s API/events. |
| t1 | EndpointSlice `ready` turns false | API watch. |
| t2 | Ingress/LB receives backend update | Proxy/controller logs or target state. |
| t3 | Last new request routed to old Pod | Proxy route-selection/access logs. |
| t4 | `preStop` finishes and JVM receives `SIGTERM` | Kubelet/runtime/application logs. |
| t5 | Spring web graceful phase finishes | Application logs/active requests. |
| t6 | Resource cleanup finishes | App lifecycle logs. |
| t7 | Container process exited | Pod `containerStatuses`/runtime. |

Compute `t1-t0`, `t2-t0`, `t4-t0`, `t5-t4`, and `t7-t0`. **Last request timestamp `t3`** only yields a good estimate under steady traffic; without incoming requests, absence of logs **does not prove** the LB stopped routing on time.

### 13.4. Measure Withdrawal Tail Latency

One clean rollout is not enough to lock in a fixed sleep. Repeat under controlled load including:
- high concurrent requests;
- HTTP keep-alive reuse;
- long requests;
- HTTP/2/gRPC if used;
- Pod CPU throttling or GC pauses;
- Ingress reloads;
- node drains;
- multiple Pods terminating concurrently.

Collect **p50/p95/p99 routing propagation**, 5xx rates, and process exit times. Size budgets from SLO-appropriate percentiles plus a margin, never from averages.

## 14. Proactive Readiness Before Shutdown

### 14.1. ApplicationAvailability

When putting an instance into maintenance before Kubernetes deletes the Pod, you can publish:

~~~java
AvailabilityChangeEvent.publish(
        eventPublisher,
        this,
        ReadinessState.REFUSING_TRAFFIC);
~~~

This snippet needs `ApplicationEventPublisher` and Spring Boot availability imports. Once the readiness group switches to `OUT_OF_SERVICE`, `/readyz` returns **503** while `/livez` stays **200**. However, `/demo/work` will still execute if called via direct Pod IP before the connector closes.

### 14.2. Do Not Expose an Unauthenticated Drain Endpoint

Exposing an unauthenticated public `POST /drain` lets anyone pull every replica out of the Service with simple requests. If a planned-drain control plane is required, protect it with mTLS/admin permissions/network policies/auditing and guard against draining all replicas at once. Coordinate publishing availability, then waiting for verified route withdrawal before sending `SIGTERM`.

### 14.3. Readiness Must Not Be Used Like Liveness

Never place shared databases or remote API health into liveness just to have Kubernetes restart the fleet when an upstream fails. Liveness reflects internal process recoverability; readiness reflects immediate traffic-handling capacity. Keep them separate to prevent cascading restarts.

## 15. Multi-Layer Timeouts

### 15.1. Client and Proxy Deadlines

A request can be cut short by:
- browser/HTTP client timeout;
- LB idle timeout;
- Ingress upstream read/connect timeout;
- service mesh drain timeout;
- Spring MVC async request timeout;
- transaction/DB timeout;
- Spring graceful shutdown phase;
- Kubernetes forced termination.

Raising the Pod grace period does not fix a client timeout. If the proxy times out in 5 seconds while app work takes 15 seconds, users still see 504 even if the JVM stays alive for 45 seconds. Maintain a per-hop timeout matrix matching the HTTP contract.

### 15.2. Safe Retries

If a connection resets during a rollout, idempotent GETs can retry within a bounded budget. For POSTs creating payments/orders, the old server may have committed before the client lost the response; blind retries cause duplicates. Use **idempotency keys, deduplication, transactional outbox, or reconciliation**.

### 15.3. Never Use Infinite Timeouts

Long-running requests need upper bounds and cancellation. For SSE/WebSocket/gRPC, design drain/reconnect/resume instead of waiting forever. Long background jobs should persist state and hand off rather than stretching Kubernetes `G` indefinitely.

## 16. Troubleshooting Deployment Issues

| Symptom | Possible cause | Check |
| --- | --- | --- |
| 502 right at `SIGTERM` | Ingress still routes to old Pod after Tomcat stops accepting | EndpointSlice, LB update latency, `preStop` buffer. |
| 504 on long requests | Proxy/client timeout before app finishes | Per-hop timeout matrix and request duration. |
| Pod exits with 137 | `SIGKILL` from grace expiration or `OOMKilled` | Pod reason/events, timestamps in logs. |
| Boot 20s yet Pod G=10s | Kubernetes hard deadline fires before Boot phase finishes | Increase `G` with justification or reduce drain. |
| `preStop` sleep 30s, G=30s | No budget left for `SIGTERM` cleanup | Shorten `preStop` or increase `G`. |
| `/readyz` 503 yet direct Pod IP 200 | Readiness is only a signal | Check Service routing; do not treat as a firewall. |
| EndpointSlice `ready=false` yet ingress still sends | Data plane propagation/sync lag | Controller logs, route-selection timestamps. |
| ALB still draining after Pod died | LB delay does not extend Kubernetes Pod grace | Align deadlines and target lifecycle. |
| WebSocket disconnects on rollout | Stream lacks drain/reconnect policy | Design reconnect/resume. |
| Duplicate POST after proxy retries | Missing idempotency | Idempotency keys/deduplication. |
| New Pod Ready yet users get 5xx | Warmup excluded from readiness | Startup/ramp-up checks. |
| Surge Pod Pending | Cluster out of capacity | Resource quotas/autoscaler/placement. |
| Probe gets 401/403 | Spring Security/network blocks kubelet | Auth rules for `/livez`, `/readyz`. |
| `/livez` 404 locally | Actuator probes disabled | `probes.enabled` and `add-additional-paths`. |
| `preStop` exec fails | Image lacks `sh`/`sleep` or command errors | Events/hook logs/image contents. |
| `SIGTERM` never reaches JVM | PID 1 shell not forwarding signals | Exec-form Dockerfile or `exec` wrapper. |
| Graceful does not run in IDE | IDE sends hard kill | Test Linux process/container `SIGTERM`. |
| Rollout failures happen intermittently | Tail propagation/GC/jitter | Repeat staging tests tracking p99 metrics. |
| API work lost after HTTP 202 | Detached job not persisted | Durable queue/job ledger. |

## 17. Runbook for Rollout 5xx Incidents

1. Record rollout window, first/last 5xx timestamps, request IDs, old/new Pod IDs, and LB target states.
2. Distinguish **proxy-generated** errors from **application-returned** errors; 502/503/504 can originate at multiple layers.
3. Check Ready/Available replicas and cluster capacity; check `maxSurge`/`maxUnavailable`.
4. Check Pod `deletionTimestamp`, `preStop` duration, `SIGTERM`, Spring graceful logs, and exit code.
5. Inspect EndpointSlice `ready`/`serving`/`terminating` and controller/data-plane update timing.
6. Check Ingress/LB access logs: last request routed to the old backend and active connections.
7. Compare **P, L, R, A, G, D** to pinpoint late arrivals or short deadlines.
8. Check long-lived HTTP/2/gRPC/WS/SSE connections and client retries.
9. Check `@Async`/background jobs decoupled from in-flight HTTP.
10. Adjust one parameter based on measured data, re-run staging rollout, and compare 5xx and p95/p99.
11. For sensitive data/side-effecting POSTs, verify idempotency before raising retries.
12. In severe incidents, roll back to preserve capacity; never blindly disable readiness/liveness.

## 18. Exercises

### Exercise 1 — Two Clocks
Draw separate timelines for Pod termination `G` and LB route withdrawal `L`. Using `G=45s`, `P=10s`, `R=18s`, `A=4s`, `M=8s`, calculate the margin and explain why AWS ALB's `D` does not add to `G`.

### Exercise 2 — Readiness Signal
Run the HTTP tests, flip readiness to `REFUSING_TRAFFIC`, and observe `/readyz=503` and `/livez=200`. Explain why `/demo/state` can still return JSON over direct HTTP.

### Exercise 3 — SIGTERM Under Load
Call `/demo/work?delayMs=7000`, send `SIGTERM` 1 second later; observe response/client timing, Tomcat logs, and process exit. Repeat in the lab with a hard kill and compare outcomes.

### Exercise 4 — EndpointSlice
Observe `ready`/`serving`/`terminating` during a rolling update. Record timestamps for EndpointSlice updates and Ingress's last request to the old Pod. Distinguish API endpoint updates from proxy data-plane propagation.

### Exercise 5 — Does preStop Help?
In staging, test `preStop=0, 5, 10` with sufficiently large `G`, recording 502/503s, p99 route latency, and hard kills. Do not draw conclusions from a single test run.

### Exercise 6 — AWS ALB
Inspect the actual deregistration delay on a target group. Explain why the 300s LB default does not keep a `G=45` Pod alive longer. Design a per-hop timeout matrix.

### Exercise 7 — Streaming
Add SSE or WebSocket with streams outlasting `G`. Design close signaling, reconnection, and resume tokens instead of waiting for natural completion.

### Exercise 8 — Rollout Capacity
With 3 replicas, `maxSurge=1`, `maxUnavailable=0`, assume new Pods take 15s to warm up, Ingress propagation `p99=8s`, and request `p99=6s`. Build the budget and verify cluster capacity exists for the extra replica.

## 19. Operations Checklist

- [ ] Traffic path Client → LB → Ingress → Service → Pod is mapped and verified.
- [ ] `terminationGracePeriodSeconds` covers `preStop`, Boot drain, cleanup, and safety margin.
- [ ] JVM PID 1 receives `SIGTERM` via exec-form `ENTRYPOINT` or proper signal forwarding.
- [ ] `server.shutdown=graceful` declared explicitly for the Boot version.
- [ ] `timeout-per-shutdown-phase` is not mistaken for a hard total process deadline.
- [ ] Health `/livez` and `/readyz` hit the right main port, unblocked by Security.
- [ ] EndpointSlice `ready`/`serving`/`terminating` semantics are understood for the cluster version.
- [ ] Ingress and external LB route withdrawal/deregistration measured in staging.
- [ ] `preStop` buffer is based on observed propagation, not arbitrary sleeps.
- [ ] HTTP request durations and client/proxy timeouts align without conflict.
- [ ] HTTP/2, WebSocket, SSE, and gRPC implement drain/reconnect where used.
- [ ] Background 202 jobs do not rely solely on HTTP graceful shutdown.
- [ ] RollingUpdate has sufficient capacity and readiness warmup.
- [ ] Shared external dependencies are excluded from liveness to prevent restart storms.
- [ ] No manual drain endpoint is exposed to external users.
- [ ] Observing p95/p99 routing propagation, active requests, 5xx rates, and exit reasons.
- [ ] Tested `SIGTERM` with in-flight requests and full staging rollouts.
- [ ] Idempotency/retry policies exist for non-idempotent operations.
- [ ] Rollback procedures and runbooks are ready if hard kills or 5xx spike.

## 20. Self-Check Questions

**1. Does `terminationGracePeriodSeconds` start before or after `preStop`?** Before; `preStop` consumes part of the budget.

**2. Does `preStop` `sleep 10` seconds guarantee ingress stops routing to the old Pod?** No. It depends on propagation and controller/provider behavior.

**3. Does `EndpointSlice` `ready=false` mean the endpoint is immediately deleted from the API?** No; a terminating endpoint can remain with `serving=true` to support draining.

**4. Does `ReadinessState.REFUSING_TRAFFIC` block direct Pod IP calls?** No. It is a health/routing signal.

**5. Does `server.shutdown=graceful` guarantee every request succeeds?** No; request timeouts, client/proxy timeouts, and `SIGKILL` can still interrupt it.

**6. With Boot `timeout-per-shutdown-phase=20s` and `G=15s`, what can kill the process first?** Kubelet once `G` expires.

**7. Does AWS ALB deregistration delay `300s` extend Pod grace from 45s to 300s?** No.

**8. Does `readinessProbe` failure automatically restart the container?** No, it only affects Ready status and Service routing. Liveness/startup govern restarts.

**9. Does `maxUnavailable=0` mean guaranteed zero downtime?** No—networking, readiness, capacity, and long-lived connections still matter.

**10. Why is `MockMvc` insufficient?** It does not exercise the Tomcat connector or Pod termination; real HTTP/process/deployment tests are required.

**11. How do you accurately measure when an LB stops picking a backend?** Correlate LB/proxy access logs, target states, EndpointSlice updates, and controlled traffic rather than reading app logs alone.

**12. When do you need a durable queue for shutdown?** When HTTP 202 jobs must survive process exit/`SIGKILL` or outlast the grace window.

## 21. Official References

1. [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): `server.shutdown`, `SmartLifecycle` stop phase, and web server semantics.
2. [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): health, Kubernetes probes, additional paths, and management port.
3. [Spring Boot 3.3 — SpringApplication Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): liveness/readiness and `AvailabilityChangeEvent`.
4. [Kubernetes — Pod Lifecycle/Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#termination-of-pods): Pod grace, `preStop`, `SIGTERM`/`SIGKILL`.
5. [Kubernetes — Pods and Endpoints Termination Flow](https://kubernetes.io/docs/tutorials/services/pods-and-endpoint-termination-flow/): EndpointSlice `ready`/`serving`/`terminating` conditions.
6. [Kubernetes — Configure Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): liveness/readiness/startup probes.
7. [Kubernetes — Deployment Rolling Update](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#rolling-update-deployment): `maxSurge`, `maxUnavailable`, `minReadySeconds`.
8. [Kubernetes — EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/): routing endpoint state.
9. [AWS ALB — Target Group Attributes](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/edit-target-group-attributes.html): deregistration delay and draining.
10. [AWS ALB — Register/Deregister Targets](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-register-targets.html): connection draining.
11. [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest` `RANDOM_PORT`.

**Conclusion:** Safe Spring Boot deployments require managing **two independent yet coupled clocks**: kubelet's deadline for the JVM to exit, and the time it takes load-balancing layers to stop sending traffic to the old instance. Combine **Actuator readiness**, **Spring Boot graceful shutdown**, **Kubernetes EndpointSlice termination signals**, a measured `preStop` buffer where needed, and a `terminationGracePeriodSeconds` large enough for `preStop` + HTTP drain + cleanup. Validate with **real HTTP, real `SIGTERM`, and staging rolling updates** under keep-alive/streaming loads, sizing to p95/p99 rather than guessing a universal sleep number.