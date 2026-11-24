# Coordinating Readiness, Load Balancer Deregistration, and SIGTERM Signals

## 1. Problem: the application must stop accepting new requests before leaving the system

In the **Graceful Shutdown** topic of **Spring Boot - web-runtime**, stopping an instance should not simply mean “kill the process and let another instance serve”. For a service behind a load balancer, there may be in-progress requests, keep-alive connections, uncommitted transactions, open SSE/WebSockets, scheduled jobs, and background consumers.

The goal of **graceful shutdown** is to:
1. Inform the orchestration system that the instance **should no longer receive new requests**.
2. Give the load balancer/Service/Ingress **time to stop selecting the old endpoint**.
3. Send **SIGTERM** so the JVM process proactively closes the ApplicationContext.
4. Let Spring Boot and the HTTP server **stop accepting new requests and wait for running requests to finish within limits**.
5. Clean up remaining tasks and connections according to the shutdown policy.
6. Exit before the runtime's deadline expires and triggers SIGKILL.
7. Ensure new replicas are **ready** and sufficient capacity remains before, during, and after the rollout.

**Three concepts to keep separate:**
- **Readiness** is the signal answering “should new traffic be routed to this instance?”
- **Deregistration/connection draining** is updating endpoint selection at the load-balancing layer and giving old connections a chance to finish.
- **SIGTERM + graceful shutdown** is the process shutdown signal/policy, preventing the server from accepting new requests and giving running requests time to complete.

No single mechanism replaces all three. Flipping readiness to false **does not kill the JVM**, while sending SIGTERM too early can leave the load balancer routing requests to an endpoint no longer accepting connections.

**Scope:** Spring Boot **3.3.13**, Java **17+**, Spring MVC/embedded Tomcat, and Kubernetes Pod lifecycle. Spring Boot 3.3 requires enabling **server.shutdown=graceful**; do not confuse it with the default of newer Spring Boot versions. Timeout values in the examples are **for the lab only** and must be validated under real deployment conditions.

## 2. Overall model and responsibility boundaries

~~~text
Client
  |
  v
DNS / external Load Balancer / Ingress
  |
  v
Kubernetes Service / EndpointSlice routing
  |
  +--------------+-------------------+
  |              |                   |
  v              v                   v
Pod A          Pod B               Pod C
Ready          Ready               Ready
  |              |                   |
  |      Rolling update: B terminating
  |              |
  |              +--> EndpointSlice terminating=true
  |              |                  ready=false
  |              +--> Routing update propagates asynchronously
  |              +--> Optional preStop hook completes
  |              +--> Kubelet sends TERM to container process
  |              +--> Spring context closes
  |              +--> Embedded web server drains in-flight requests
  |              +--> JVM exits
  |              |
  |              +--> SIGKILL if termination grace expires
  |
  +--> New requests should go to remaining ready endpoints
~~~

**This is a target model, not an absolute timing-guaranteed sequence.** Kubernetes updating EndpointSlices and kubelet executing shutdown happen on concurrent branches; load balancers, Ingresses, and clients may cache or pool connections. Once a Pod is marked terminating, EndpointSlice has **ready=false**, yet routing components still need time to receive and apply the update.

Do not confuse **Kubernetes Service** (routing) with **Spring Boot readiness probe** (status reporting) or with the **Servlet connector** (the socket accepting HTTP). All three belong to different control boundaries.

## 3. Readiness, liveness, and startup probes serve distinct goals

| Mechanism | Question | Failure typically leads to |
| --- | --- | --- |
| Readiness probe | Can the instance accept new traffic yet? | Pod is removed from ready endpoints for normal traffic |
| Liveness probe | Is the process/app stuck broken and needing a restart? | Kubelet may restart the container per policy |
| Startup probe | Has the app passed its slow startup phase yet? | Temporarily shields liveness/readiness from premature checks per config |
| Kubernetes terminating state | Is the Pod being deleted/stopped? | EndpointSlice gets terminating=true, ready=false |
| Load balancer deregistration | Has routing stopped choosing the endpoint? | New traffic shifts to other endpoints once updated |
| Spring Boot graceful shutdown | Are current requests awaited for completion? | Server stops accepting new, drains within deadline |
| SIGTERM | Has the process been asked to terminate? | JVM shutdown hooks run if signal received and runtime allows |
| SIGKILL | Forced immediate stop? | Java shutdown hooks do not run; in-progress work may be lost |

**Readiness false is not liveness broken.** When intentionally draining a healthy Pod, only report “do not accept new traffic”, without flipping liveness to failing and causing kubelet to restart unnecessarily.

**Startup probe** helps when an app warms up, runs migrations, or builds caches slowly. Before ready, the app may listen on a port while not yet fit to serve business traffic. Once ready, the readiness probe steers traffic to the instance.

### 3.1. Spring Boot availability states

Spring Boot provides:
- **LivenessState.CORRECT** / **BROKEN**.
- **ReadinessState.ACCEPTING_TRAFFIC** / **REFUSING_TRAFFIC**.
- **ApplicationAvailability** to read the current states.
- **AvailabilityChangeEvent** to publish state changes when the application controls them.

During startup: before the app completes startup/runners, readiness is typically **REFUSING_TRAFFIC**; once ready, it becomes **ACCEPTING_TRAFFIC**. During graceful shutdown, Spring Boot 3.3 sets **REFUSING_TRAFFIC** internally. However, at shutdown time the HTTP connector has already begun stopping new request acceptance, so **the external readiness endpoint may become unreachable**. That is why readiness responses during shutdown should not be treated as a permanently callable API.

### 3.2. Why not depend on the database for liveness?

If a shared database slows down, 10 Pods all tying liveness to the DB may restart simultaneously, worsening the outage. Liveness should reflect the health of the application process itself. For readiness, weigh whether an external dependency is truly essential and can fail locally; putting a shared dependency into every Pod's readiness can cause the Service to lose all endpoints at once.

Per Spring Boot, readiness/liveness health groups do not automatically include every external HealthIndicator by default. Only add them if you have verified the impact.

## 4. Proper Spring Boot Actuator readiness probe

Spring Boot 3.3 with **spring-boot-starter-actuator** provides health groups:
- **/actuator/health/liveness**
- **/actuator/health/readiness**

In Kubernetes, probes may be auto-enabled when Spring Boot detects a Kubernetes environment. To run consistently locally without depending on environment detection, declare explicitly:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

**management.endpoint.health.probes.add-additional-paths=true** also maps:
- **/livez** on the **application HTTP port**.
- **/readyz** on the **application HTTP port**.

This is especially useful if you run Actuator on a **different management.server.port**, because the health endpoint on the management port may stay alive while the application port fails to accept requests. Probing on the **actual application port** verifies the HTTP path serving real traffic.

When ready, the health endpoint JSON normally reports **status UP** with HTTP 200. When readiness refuses traffic, health status may be **OUT_OF_SERVICE** and typically maps to HTTP 503 by default. While the HTTP connector is closing, clients may observe **connection refused/EOF** instead of JSON 503; do not promise a fixed status during shutdown.

### 4.1. Secure Actuator configuration

By default Spring Boot exposes only the health endpoint over HTTP. Do not expose sensitive endpoints such as `env`, `beans`, `heapdump`, or `shutdown` just for Kubernetes probes.

If you have a custom Spring Security `SecurityFilterChain`, ensure **/readyz** and **/livez** are reachable by kubelet/ingress per network policy, while other endpoints remain protected. Never create a public administrative route letting arbitrary clients mark the app unready or shut down the server.

## 5. Graceful shutdown in Spring Boot 3.3

### 5.1. Enable graceful shutdown explicitly

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

**server.shutdown=graceful**: enables graceful shutdown of the embedded web server. With Spring Boot 3.3, configure it explicitly instead of assuming the default matches newer versions.

**spring.lifecycle.timeout-per-shutdown-phase=30s**: bounds the wait time **per phase** while stopping SmartLifecycle beans. Web server graceful shutdown runs at an early stage of stopping. This **is not a hard limit on total JVM shutdown time of exactly 30 seconds under all conditions**; multiple phases, destroy callbacks, or dependencies can consume additional time.

Per Spring Boot 3.3, graceful shutdown is supported on Tomcat, Jetty, Reactor Netty, and Undertow. How new requests are rejected varies:
- **Tomcat, Jetty, and Reactor Netty**: stop accepting new requests at the network layer.
- **Undertow**: may accept new connections and return **503 Service Unavailable**.

Therefore **never claim that every server returns HTTP 503 right after SIGTERM**. On Tomcat, new requests may hit connection refused or a network error. Keep-alive, HTTP/2, and requests already inside the server before shutdown started make real observations more nuanced.

### 5.2. What graceful shutdown protects

- Gives **in-flight HTTP requests** time to finish within the allowed window.
- Blocks admitting new HTTP requests once shutdown triggers.
- Reduces unnecessary connection resets if requests are short enough.
- Coordinates with the ApplicationContext lifecycle so beans are stopped/destroyed.

**Not guaranteed:**
- All transactions and background tasks completing if they exceed the time limit.
- Tasks that already left the request thread, external job queues, or Kafka/JMS consumers draining properly via `server.shutdown` alone.
- Long-lived WebSocket/SSE connections staying alive forever without affecting shutdown.
- SIGKILL allowing `@PreDestroy` to run.
- All reverse proxies stopping traffic the instant the app receives SIGTERM.

To stop jobs/consumers, use separate shutdown logic, `SmartLifecycle`, or integration mechanisms with appropriate time budgets.

## 6. Coordination order: drain traffic first, TERM second, kill last

Conceptual timeline:

~~~text
t0                  t1                 t2                 t3
|-------------------|------------------|------------------|
Deployment update   Endpoint changed   SIGTERM delivered  JVM exit
Pod terminating     ready=false        to process 1       when done
    |                  |                    |
    +--> Control plane updates EndpointSlice |
    +--> Endpoint routing changes propagate  |
    +--> preStop can delay TERM              |
                                            +--> Spring readiness REFUSING_TRAFFIC
                                            +--> Web server refuses new requests
                                            +--> In-flight requests finish
                                            +--> Beans/resources stop
    |
    +------------- terminationGracePeriodSeconds ------------+
                                                             |
                                                             +--> SIGKILL if process still alive
~~~

**Key point:** the **terminationGracePeriodSeconds** timer starts when the Pod is requested to terminate, **not after preStop finishes sleeping**. `preStop` spends time out of that same budget. The remaining time must suffice for the JVM to perform graceful shutdown and cleanup.

At the same time, endpoint termination propagation is asynchronous. Kubernetes updating EndpointSlice does not mean an external Load Balancer, Ingress, or client connection pool learns immediately. Thus a **drain delay** can help depending on the environment, though it should be measured rather than guessed arbitrarily.

### 6.1. preStop runs before SIGTERM

In a typical Linux container, when a Pod is terminating:
1. Kubelet starts the graceful termination countdown.
2. If a **preStop** lifecycle hook exists and the grace period is non-zero, kubelet runs the hook.
3. Once the hook finishes, kubelet asks the container runtime to send **SIGTERM** (or the configured stop signal) to process 1.
4. The runtime waits for the process to exit until the grace period expires.
5. If the container is still running on expiry, the runtime sends **SIGKILL**.

This is the sequence for **kubelet on the node**, while EndpointSlice updates/proxy propagation can proceed concurrently on the control plane.

### 6.2. What does preStop sleep do and not do?

Example hook:

~~~yaml
lifecycle:
  preStop:
    exec:
      command: ["/bin/sh", "-c", "sleep 8"]
~~~

During these 8 seconds:
- The Java process **has not yet received SIGTERM from the normal shutdown flow**, so it can still serve existing requests.
- The Pod is already marked terminating and EndpointSlice typically reflects **ready=false**, helping routing avoid picking the endpoint for normal requests.
- Proxies that update slowly get time to apply the new state.

However:
- This **is not confirmation that the load balancer finished draining**.
- External LBs may hold routing/keep-alive longer than 8 seconds.
- If the image lacks **/bin/sh** or the `sleep` binary, the hook will fail.
- Sleeping too long eats away time from actual graceful shutdown.
- Internal app readiness may still be ACCEPTING_TRAFFIC during the sleep unless a separate unready mechanism is used.

**preStop sleep is a conditional coordination tool, not a mandatory requirement for every cluster or a cure-all for every reset.**

### 6.3. Proactively marking unready before TERM

If the system has an **authenticated and network-restricted** control channel, readiness false can be published before actually shutting down the server:

~~~java
// Fragment: method invoked from a trusted internal control flow.
// Requires importing ApplicationContext, AvailabilityChangeEvent, and ReadinessState.
void beginDrain(ApplicationContext context) {
    AvailabilityChangeEvent.publish(
            context,
            ReadinessState.REFUSING_TRAFFIC
    );
}
~~~

This is a **fragment**, not a public REST endpoint or standalone Java program. Once readiness flips to false while the HTTP connector remains open, external probes can observe **/readyz** as unready prior to SIGTERM. The system can wait for sufficient propagation and then trigger shutdown.

**Important:** readiness false **is only a signal for routing**, and does not automatically stop serving direct requests. If a client calls the Pod IP or reuses an old connection, requests can still enter the app until shutdown is called. Combine it with an admission policy if new requests must be rejected immediately.

Never create an unauthenticated public **POST /drain**; attackers could cause all instances to remove themselves from the Service. Outside Kubernetes, pre-setting unready and deregistering at a specific load balancer must use the LB's own API/control plane rather than relying solely on a Spring event.

## 7. Kubernetes EndpointSlice: ready=false vs immediate removal

In modern Kubernetes versions, an endpoint representing a terminating Pod can **remain in the EndpointSlice** during the drain period with conditions:

~~~yaml
conditions:
  ready: false
  serving: true
  terminating: true
~~~

This is an **observable state example**. For a terminating Pod:
- **terminating=true**: Pod is shutting down.
- **ready=false** is set so regular clients/load balancers do not choose that endpoint for new traffic.
- **serving** provides additional information usable for draining; not every consumer handles this condition identically.

Do not confuse **EndpointSlice ready=false** with **Spring Boot AvailabilityState REFUSING_TRAFFIC**: they can occur at different times. A Pod can be terminating and pulled from routing **even before the app receives SIGTERM**.

Never claim endpoints are “deleted instantaneously” when a Pod starts terminating. Kubernetes can retain the record with `terminating=true` to support connection draining. Once the Pod finishes, the record is finally removed from the Service endpoint set.

### 7.1. External load balancers may need separate deregistration

Consider a Kubernetes Service behind Ingress/NGINX/Envoy or an external cloud load balancer. Different components may:
- Watch EndpointSlices directly or indirectly.
- Cache upstream endpoints.
- Maintain keep-alive connections to Pods.
- Enforce their own connection-draining timeouts.
- Retry another endpoint when an upstream closes.

**There is no fixed sleep duration guaranteed to suit every LB.** Observe upstream resets, ingress 5xx, endpoint transition timestamps, and running request durations to size `preStop`/termination grace.

If using an external LB managing target groups asynchronously from Kubernetes Service, check the provider's deregistration delay as well, not just the Pod readiness probe.

## 8. Shutdown time budget: calculating across the whole chain

Initial design example:

| Interval | Illustrative duration | Meaning |
| --- | --- | --- |
| Kubernetes termination grace | **55 seconds** | Total budget before SIGKILL |
| preStop drain delay | **8 seconds** | Wait for routing propagation, before SIGTERM |
| Spring lifecycle phase timeout | **30 seconds/phase** | Wait limit per SmartLifecycle phase, including graceful web server phase |
| Reserve | **17 seconds** if only one 30s phase | For other phases, cleanup, scheduling jitter |

Illustrative math: **55 = 8 + 30 + 17**. However, you **must not** conclude the JVM is guaranteed to exit in 38 seconds: `spring.lifecycle.timeout-per-shutdown-phase` is a **per-phase** limit, and there may be multiple phases, bean destruction, and external operations. Measure actual shutdown wall-clock time, then raise termination grace or optimize shutdown.

### 8.1. Sizing rules

- Termination grace must cover **preStop + graceful in-flight time + other shutdown phases + cleanup + margin**.
- Normal request and gateway timeouts must fit within the remaining time.
- If work takes longer than the budget, return **202 Accepted + durable job ID** or checkpoint/requeue instead of holding an HTTP request indefinitely.
- Do not extend preStop sleep indefinitely to mask an overly slow shutdown bug.
- If the app has multiple containers/sidecars, check shutdown ordering and Pod-wide deadlines.
- To minimize downtime, combine rolling update **maxUnavailable, maxSurge, PodDisruptionBudget, and capacity** rather than only increasing `terminationGracePeriodSeconds`.

### 8.2. If SIGKILL occurs

SIGKILL cannot be caught by the JVM to run shutdown hooks. In-progress work can be cut off mid-way:
- DB transactions may roll back upon connection close, though actual state must be verified.
- Remote API side effects may have already happened even though no response was sent.
- Received yet unacked messages may be redelivered.
- Partially written files may linger without atomic renames/checkpoints.

Graceful shutdown is therefore a risk-reduction layer, **not a substitute for idempotency, transaction boundaries, and durable work queues**.

## 9. Runnable lab: Spring Boot MVC with readiness and slow requests

This lab proves:
1. When the app is ready, **/readyz** and **/livez** return healthy responses.
2. An HTTP request running inside a Controller can complete when the JVM receives SIGTERM if grace is sufficient.
3. Spring Boot stops accepting new requests during graceful shutdown.
4. Once the app has stopped, health probes on the application port stop responding.
5. Docker exec-form ENTRYPOINT delivers the signal to the right Java process.

### 9.1. Project tree

~~~text
graceful-demo/
├── pom.xml
├── Dockerfile
├── k8s.yaml
└── src/
    ├── main/
    │   ├── java/com/example/graceful/GracefulDemoApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/graceful/ProbeIntegrationTest.java
~~~

The Dockerfile and `k8s.yaml` are described below; they use the same project, though only Maven/Java are needed to test SIGTERM locally.

### 9.2. Complete pom.xml

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

    <groupId>com.example</groupId>
    <artifactId>graceful-demo</artifactId>
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

### 9.3. application.yml

**src/main/resources/application.yml:**

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
  endpoints:
    web:
      exposure:
        include: health
~~~

- **server.shutdown: graceful**: required in Spring Boot 3.3 to enable finishing running requests on shutdown.
- **timeout-per-shutdown-phase: 30s**: sufficient for lab requests up to 15 seconds in the web server phase, excluding overhead.
- **probes.enabled**: creates liveness/readiness health groups even when running locally.
- **probes.add-additional-paths**: exposes **/readyz** and **/livez** on port 8080.
- **exposure.include: health**: avoids exposing sensitive unnecessary Actuator endpoints.

Do not set a separate **management.server.port** in the lab, so probes verify the main web server itself.

### 9.4. Complete Java source

**src/main/java/com/example/graceful/GracefulDemoApplication.java:**

~~~java
package com.example.graceful;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class GracefulDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(GracefulDemoApplication.class, args);
    }
}

@RestController
class DemoController {
    private final ApplicationAvailability availability;
    private final AtomicInteger inFlight = new AtomicInteger();

    DemoController(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @GetMapping("/api/slow")
    Map<String, Object> slow(
            @RequestParam(defaultValue = "5000") long ms
    ) throws InterruptedException {
        if (ms < 0 || ms > 15000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "ms must be 0..15000"
            );
        }

        inFlight.incrementAndGet();
        try {
            // Simulate blocking work running on a Servlet worker.
            Thread.sleep(ms);
            return Map.of(
                    "status", "completed",
                    "requestedMs", ms
            );
        } finally {
            inFlight.decrementAndGet();
        }
    }

    @GetMapping("/api/state")
    Map<String, Object> state() {
        return Map.of(
                "readiness", String.valueOf(
                        availability.getReadinessState()
                ),
                "liveness", String.valueOf(
                        availability.getLivenessState()
                ),
                "inFlight", inFlight.get()
        );
    }
}
~~~

**Code explanation:**
- **@SpringBootApplication** enables Spring Boot auto-configuration, Tomcat, and Actuator.
- **ApplicationAvailability** reads the current readiness/liveness states.
- **/api/slow?ms=5000** creates a synchronous request holding a Servlet worker for ~5 seconds and returning JSON. `Thread.sleep` is demo-only, not something to do in production code.
- **ms < 0 or > 15000** intentionally returns HTTP 400 so the lab cannot be used as an unbounded work endpoint.
- **AtomicInteger inFlight** counts requests inside the `slow` method; it does not count other requests, sockets, async tasks, or requests on other replicas.
- **/api/state** prints Spring Boot states and the count of running slow requests, useful for observing before SIGTERM.
- Java 17 supports all these APIs. A single file with public `GracefulDemoApplication` and package-private `DemoController` is valid.

During graceful stop, Spring Boot closes `ApplicationContext` and Tomcat waits for in-flight requests up to the timeout. **Do not expect `/api/state` to remain reachable once the connector stops accepting HTTP requests**, even though internal readiness already flipped to `REFUSING_TRAFFIC`.

### 9.5. Probe integration test

**src/test/java/com/example/graceful/ProbeIntegrationTest.java:**

~~~java
package com.example.graceful;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ProbeIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void probesAreAvailableOnMainPort() {
        assertEquals(
                HttpStatus.OK,
                http.getForEntity("/livez", String.class).getStatusCode()
        );
        assertEquals(
                HttpStatus.OK,
                http.getForEntity("/readyz", String.class).getStatusCode()
        );
    }
}
~~~

This is an integration test with a real embedded web server on a **random port**, confirming both probes return HTTP 200 once ready. It **does not** by itself prove SIGTERM graceful shutdown because the test runs inside the same JVM. The signal test below requires a separate process.

### 9.6. Local build and run

Requires Java 17+, Maven, and port 8080 free:

~~~bash
mvn test
mvn package
java -jar target/graceful-demo-1.0.0.jar
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -s http://localhost:8080/api/state
curl -s "http://localhost:8080/api/slow?ms=1000"
~~~

Once the app starts up, probes typically return **HTTP 200** and health JSON with **status UP**. `/api/state` returns readiness **ACCEPTING_TRAFFIC**, liveness **CORRECT**, and `inFlight` 0 when no slow requests are active; this is a snapshot so numbers vary by timing.

For a successful single slow request, JSON contains the values:

~~~json
{"requestedMs":1000,"status":"completed"}
~~~

Key ordering in a `Map` is not guaranteed by `Java Map.of`; the illustration only asserts the two fields and values. `curl -i` prints additional headers in stdout.

### 9.7. Testing SIGTERM with an in-flight request (Linux/macOS)

Run in the project directory, with no other app using port 8080:

~~~bash
java -jar target/graceful-demo-1.0.0.jar > demo.log 2>&1 &
APP_PID=$!

# Wait for ready before sending request; requires curl.
until curl -fsS http://localhost:8080/readyz > /dev/null; do
  sleep 1
done

curl -sS "http://localhost:8080/api/slow?ms=5000" > slow.json &
REQUEST_PID=$!

# Wait briefly so the request enters the Controller.
sleep 1

# Send TERM to the java process; do not use kill -9.
kill -TERM "$APP_PID"

wait "$REQUEST_PID"
cat slow.json
wait "$APP_PID"
~~~

When the request genuinely entered the Controller before SIGTERM and the timeout suffices, **slow.json** is expected to contain JSON with **status completed** and **requestedMs 5000**; the JVM may exit right after in-flight work completes and beans stop. If shell load/scheduling shifts so the request had not entered the Controller at TERM time, curl can fail—this is an interactive test, not a deterministic timed proof.

Open `demo.log` to inspect graceful shutdown lines for the current runtime version; do not rely on an exact log string as an API contract.

**Do not use kill -9** to test graceful shutdown: SIGKILL does not run shutdown hooks. On Windows, stopping from an IDE or some process-kill commands may differ from Linux SIGTERM; you can test inside Linux Docker to reproduce the semantics.

### 9.8. Expected results and limits

| Scenario | Reasonable expectation |
| --- | --- |
| `/readyz` while app is running/ready | HTTP 200, status UP |
| `/api/slow?ms=1000` normally | HTTP 200, JSON completed |
| SIGTERM after 5-second `/api/slow` started | Request has a chance to finish within 30s grace |
| New request after Tomcat starts graceful stop | Not accepted; client may see network error |
| `/readyz` once HTTP connector closed | May become unreachable; not required to return JSON 503 |
| SIGKILL or overly short termination timeout | In-flight requests may be cut off |
| SIGTERM sent to shell wrapper not forwarding signals | JVM may fail to run shutdown hook in time |

**Never claim zero-downtime based solely on a single-instance demo.** Zero-downtime rolling updates require other ready replicas without saturation and updated load balancer routing.

## 10. Docker: signals must reach the right JVM

**Dockerfile** at project root:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/graceful-demo-1.0.0.jar /app/app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

**JSON exec-form ENTRYPOINT** makes the Java process PID 1 inside the container, receiving stop signals sent by the container runtime. Avoid shell form:

~~~dockerfile
# DO NOT use if the shell does not exec/forward TERM properly:
ENTRYPOINT java -jar /app/app.jar
~~~

A shell wrapper can become PID 1 and fail to forward SIGTERM as intended. If a start script is mandatory, the final line should use **exec java -jar ...**, and you must understand signals, PID 1 signal handling, zombie reaping, or init processes.

Build/run:

~~~bash
mvn package
docker build -t graceful-demo:1.0.0 .
docker run --rm --name graceful-demo -p 8080:8080 graceful-demo:1.0.0
~~~

In another terminal, once the server is ready:

~~~bash
curl -s http://localhost:8080/readyz
curl -s "http://localhost:8080/api/slow?ms=5000" &
sleep 1
docker stop --time 50 graceful-demo
wait
~~~

**docker stop --time 50** sends the stop signal to PID 1 and waits up to 50 seconds before force-killing per Docker semantics. It **does not simulate Kubernetes EndpointSlice deregistration**; it only verifies JVM signal/shutdown and request completion.

If using a distroless image, **/bin/sh** or `sleep` may be absent, so an exec-sleep Kubernetes preStop needs adjustment. Exec-form Java works with shell-less images; do not configure a preStop hook depending on missing tools.

## 11. Complete Kubernetes Deployment and Service for the lab

To demonstrate readiness, Pod termination, and Service endpoints, create **k8s.yaml**. The **graceful-demo:1.0.0** image must be placed in the cluster first, e.g., **kind load docker-image graceful-demo:1.0.0** if using kind. On other clusters, substitute an image pushed to your organization's registry per your deployment process.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: graceful-demo
spec:
  replicas: 3
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
      terminationGracePeriodSeconds: 55
      containers:
        - name: web
          image: graceful-demo:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 1
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 1
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
                command: ["/bin/sh", "-c", "sleep 8"]
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              memory: 512Mi
---
apiVersion: v1
kind: Service
metadata:
  name: graceful-demo
spec:
  selector:
    app: graceful-demo
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
~~~

**How to read the manifest:**
- **replicas: 3**: keeps other instances alive during rollout; does not guarantee enough capacity if load exceeds remaining capacity.
- **maxSurge: 1, maxUnavailable: 0**: rolling update config prioritizing available replicas per Kubernetes Deployment semantics. Truly avoiding disruption still requires sufficient CPU/memory, rollout pacing, and proper probes.
- **readinessProbe /readyz**: Kubernetes picks Pods for traffic when the probe reports ready. Once a Pod is terminating, EndpointSlice has `ready=false` per termination semantics.
- **livenessProbe /livez**: checks liveness; never flip liveness to broken just to drain.
- **startupProbe /livez**: gives the app startup headroom before liveness/readiness apply per probe policy. Not needed for every app, yet helpful for slow startups.
- **preStop sleep 8**: extends Pod lifetime before TERM so route updates propagate.
- **terminationGracePeriodSeconds 55**: Pod-wide budget covering preStop, post-TERM time, and cleanup.
- **resources**: lab example only; measure actual heap/CPU.
- **Service ClusterIP**: routes to valid endpoints; test from inside the cluster or via appropriate port-forwarding.

### 11.1. Hands-on with kind

If you already have **kind**, **kubectl**, Docker, and a running cluster:

~~~bash
docker build -t graceful-demo:1.0.0 .
kind load docker-image graceful-demo:1.0.0
kubectl apply -f k8s.yaml
kubectl rollout status deployment/graceful-demo
kubectl get pods -l app=graceful-demo
kubectl get endpointslices -l kubernetes.io/service-name=graceful-demo
~~~

Without an existing kind cluster, create one via a separate step before running. Do not use **kubectl delete --force --grace-period=0** to test graceful shutdown because it bypasses the goal of the test.

When rolling out again:

~~~bash
kubectl rollout restart deployment/graceful-demo
kubectl rollout status deployment/graceful-demo
kubectl get pods -l app=graceful-demo
kubectl get endpointslices -l kubernetes.io/service-name=graceful-demo
~~~

To watch transitional states, open another terminal running **kubectl get pods -l app=graceful-demo -w** and inspect EndpointSlices with `get -o yaml` briefly. Because termination can finish quickly, not every inspection catches intermediate states; check Kubernetes events/logs if needed.

### 11.2. Do not assume preStop means “refusing traffic”

During the 8-second sleep, the Java app is still running and may internally report ACCEPTING_TRAFFIC. **Pod termination metadata** sets EndpointSlice `ready=false`, letting compliant routing components stop picking it. Yet a slow-updating proxy or a client hitting the Pod IP directly can still send requests to the container.

If strictness is required, use an active authenticated drain flow **before SIGTERM**, or integrate LB provider-specific deregistration, wait for observed propagation, and then stop. Never expose a public endpoint allowing arbitrary users to trigger shutdown/drain.

### 11.3. Distinguishing Pod Ready vs Available during rollouts

Deployment evaluates replica availability via readiness and `minReadySeconds` if configured; a newly started Pod that isn't ready yet must not receive traffic. **maxUnavailable=0** does not guarantee zero downtime if the readiness probe is overly optimistic, DB migrations are incompatible, or all replicas share a broken dependency.

Production should also evaluate **PodDisruptionBudget**, node drains, autoscaling, topology, rolling strategies, and capacity when only N-1 instances remain.

## 12. Spring ApplicationAvailability and advanced pre-drain workflows

In systems with an orchestrator other than Kubernetes or slow LB deregistration, you can separate three business states:
- **SERVING**: ready to accept requests.
- **DRAINING**: published readiness false, refuses new work with side effects; current requests continue to finish.
- **STOPPING**: SIGTERM, HTTP connector shutdown, closing resources.

These transitions must be orchestrated over an authenticated internal channel. Do not use a custom enum to replace Spring Boot readiness, Kubernetes EndpointSlices, or LB control planes; integrate the states instead.

### 12.1. Marking unready only

~~~java
// Fragment in a trusted lifecycle/control service.
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;

void markUnready(ApplicationContext applicationContext) {
    AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.REFUSING_TRAFFIC
    );
}
~~~

This is an illustrative fragment and does not compile standalone. It changes **Spring Boot's availability state**, and does not automatically:
- close the server socket;
- wait for load balancer caches to update;
- finish running requests;
- execute SIGTERM;
- stop background consumers.

If a trusted preStop flow marks the app unready and sleeps, access must be restricted; a shared secret endpoint is insufficient if network/security controls are misconfigured. Never copy a `permitAll` REST `POST /drain` into production.

### 12.2. Why not mark liveness broken while draining?

Failing the liveness probe can trigger kubelet to restart the container instead of letting it drain normally, resetting connections and causing replica churn. When an instance is healthy yet about to stop, it is proper to have **readiness REFUSING_TRAFFIC** and **liveness CORRECT** until shutdown actually happens.

## 13. What HTTP graceful shutdown cannot handle on its own

### 13.1. `@Async`, scheduled jobs, queues

An HTTP Controller that already finished may have enqueued a background job. If SIGTERM arrives after a 202 response while the job sits in an in-memory executor queue, stopping the web server **does not guarantee the task completes**.

Solutions:
- Use durable queues/DB outboxes and ack per transaction/idempotency where needed.
- Stop accepting new jobs, stop polling/consumption, wait for in-flight jobs under a separate budget.
- For executors, call `shutdown()`, `awaitTermination(...)`, and apply a clear checkpoint/cancel policy if unfinished.
- For scheduled tasks or message consumers, check `SmartLifecycle`, listener container shutdown semantics, and acknowledgment/redelivery.

Do not keep critical state solely in JVM RAM expecting `@PreDestroy` to run in every failure. Node crashes, OOMKills, and SIGKILLs can terminate with zero cleanup.

### 13.2. WebSocket, SSE, and gRPC streaming

A WebSocket/SSE stream can live for hours; waiting indefinitely prevents rollouts from completing. You need policies to:
- Stop creating new subscriptions while draining.
- Notify clients to reconnect to another endpoint if the protocol allows.
- Close streams with appropriate codes/reasons, leaking no secrets.
- Bound max connection age and drain duration.
- Support reconnect/backoff and authorized cursor resumption.
- Never infer Tomcat HTTP graceful shutdown handles every long-lived connection per business protocol.

Clients holding long HTTP/2/gRPC streams or SSE/WS may need separate retry/resume logic; you cannot guarantee “every connection stays open until the user closes it” inside a finite termination window.

### 13.3. Database transactions and side effects

A request may complete a payment provider call before returning a response; SIGKILL leaves the client unaware of the outcome. Retries can create duplicate transactions. Use idempotency keys, outboxes, sagas, or suitable transaction patterns; graceful shutdown lowers probability, rather than replacing correctness.

**Only confirm success to the client once state/side effects satisfy the API's durability criteria.**

## 14. SIGTERM and PID 1 inside containers

### 14.1. Basic Linux signals

- **SIGTERM**: requests controlled process termination; JVM typically runs shutdown hooks in the shutdown sequence.
- **SIGINT**: typically from Ctrl+C; can trigger shutdown per Java runtime.
- **SIGKILL**: forced termination with no chance for shutdown hooks to run.
- **Exit code 137** is typically associated with SIGKILL/128+9, though you must still check container OOMKilled, grace expiry, or other factors; never diagnose from this code alone.
- **Exit code 143** is typically associated with SIGTERM/128+15 in shell/container environments, though Java processes may return other exit codes when handling signals or errors.

Never promise “SIGTERM guarantees all cleanup completes”. If shutdown hooks/phases hang and grace expires, the runtime can force-kill.

### 14.2. Why is shell-form ENTRYPOINT dangerous?

~~~dockerfile
# Recommended:
ENTRYPOINT ["java", "-jar", "/app/app.jar"]

# Do not assume a shell wrapper forwards signals:
# ENTRYPOINT java -jar /app/app.jar
~~~

Exec form runs Java directly as PID 1; shell form typically spawns a shell wrapper. If the wrapper does not forward TERM properly, Java may never be asked to shut down before timeout. If a startup script needs logic, use **exec java -jar ...** at the end of the script.

### 14.3. Stopping from an IDE differs from Linux SIGTERM

An IDE may use a stop action that does not send SIGTERM the way Docker/Kubernetes do. Spring Boot docs warn graceful shutdown behavior in an IDE can differ. Test using **kill -TERM**, **docker stop**, or Kubernetes Pod termination when verifying real behavior.

## 15. Readiness and load balancing with HTTP/2, keep-alive, sticky sessions

### 15.1. New requests can arrive over old connections

Load balancers do not pick a fresh Pod for every HTTP request across all protocols. They may reuse TCP keep-alive connections, multiplex HTTP/2 streams, or preserve sticky affinity. When an endpoint is deregistered:
- LBs typically stop opening new upstream connections once routing updates.
- Yet existing connections/streams may still carry in-flight requests.
- Depending on the proxy, a new request on an existing keep-alive connection may be rejected or rerouted.
- HTTP/2 GOAWAY/drain behavior depends on the specific protocol, server, and proxy.

Never say “EndpointSlice ready=false means all TCP packets to the Pod stop immediately”. Health/routing controls target selection, not always immediately closing existing sockets.

### 15.2. Sticky sessions and WebSockets

With sticky sessions or WebSockets, clients stay tied to the old Pod longer than a typical HTTP request. During drain:
- Notify/reconnect per protocol.
- Store session state in a shared store when needed.
- Avoid keeping business data solely in the memory of a dying Pod.
- Support resume/reauthentication when clients move nodes.
- Prevent thundering-herd client reconnects after rollout via jitter.

## 16. Monitoring and measurements during rollouts

Metrics and logs to observe:

| Layer | Indicator | Question |
| --- | --- | --- |
| Kubernetes | Pod Ready/Terminating/Available, EndpointSlice conditions | Has the Pod been marked terminating? |
| Probes | `/readyz`, `/livez` status and probe failures | Did new Pod selection stop? |
| Ingress/LB | upstream 502/503/504, resets, endpoint target count | Did routing updates finish? |
| Tomcat | active requests, busy threads, connections | Are requests still running? |
| Spring lifecycle | time from SIGTERM to context closed | Did shutdown complete within grace? |
| JVM/container | exit code, SIGKILL, OOMKilled, restart count | Force-killed or normal exit? |
| DB/outbound | active connections/transactions, timeouts | Did DB pool close before requests finished? |
| Queue/consumers | unacked jobs, requeues, duplicate processing | Are background tasks safe? |
| Client | resets/timeouts, retry count, p95/p99 | How many errors did users actually see? |
| Rollout | available replicas, unavailable duration | Was capacity insufficient during rollout? |

**What matters is measuring user-visible failures**, not just Kubernetes reporting a successful rollout. A rollout can succeed in deployment status while causing hundreds of HTTP 502s if deregistration lags.

### 16.1. Log correlation

When testing shutdown:
1. Record timestamp when Pod is marked terminating / EndpointSlice ready becomes false.
2. Record timestamp when kubelet preStop starts/ends.
3. Record timestamp when JVM receives TERM or Spring starts shutting down.
4. Record when the HTTP server stops accepting new requests.
5. Record when the last in-flight request completes.
6. Record when the Java process exits.
7. Cross-reference with proxy upstream errors and client retries.

Avoid logging raw Authorization headers, cookies, or sensitive payload bodies. Use non-privileged trace/correlation IDs.

## 17. End-to-end testing runbook

### 17.1. Local JVM SIGTERM test

- [ ] Build runnable jar, enable `server.shutdown=graceful`.
- [ ] Run app as a Java process, wait for `/readyz` healthy.
- [ ] Send a sufficiently long `/api/slow` request.
- [ ] Send SIGTERM after the request has started.
- [ ] Verify the request has a chance to return 200 within grace.
- [ ] Send a new request during shutdown and record network/HTTP outcome, without expecting a fixed 503.
- [ ] Measure time until Java process exits.
- [ ] Inspect shutdown logs, not just curl status.

### 17.2. Docker test

- [ ] Use exec-form ENTRYPOINT; Java receives stop signal.
- [ ] `docker stop` with sufficient wait time.
- [ ] Observe in-flight request and shutdown duration.
- [ ] Intentionally test a shorter stop timeout in the lab to understand SIGKILL; never do this in production.
- [ ] Check cleanup/exit code; do not treat exit 137 as having only one possible cause.

### 17.3. Kubernetes rolling update

- [ ] Have at least two replicas and sufficient capacity when one Pod leaves service.
- [ ] Readiness probe checks the real application port.
- [ ] Liveness does not depend on a shared database and does not fail during normal drain.
- [ ] Pod `terminationGracePeriodSeconds` covers preStop and Spring lifecycle.
- [ ] Terminating Pod's EndpointSlice has `ready=false`.
- [ ] Load balancer/Ingress actually updates routing before the Pod closes its server.
- [ ] Measure upstream resets and 502/503/504 during rollout.
- [ ] Test WebSocket/SSE/gRPC reconnect if applicable.
- [ ] Test background jobs/queues and DB transactions when a Pod stops.
- [ ] Check Available/Ready replica counts after the update.
- [ ] Do not use force delete to infer graceful behavior.

### 17.4. Controlled failure injection

In an authorized staging environment:
1. Run 5–15 second slow requests and SIGTERM with sufficient grace.
2. Increase ingress route update latency to determine needed preStop buffer.
3. Test proxies holding old connections/HTTP/2.
4. Test shutdown with active database transactions and messages; verify no duplicates or redelivery safety.
5. Test SIGKILL or overly short grace and verify idempotent recovery.
6. Test Pod OOMKill; do not assume `@PreDestroy` runs.
7. Test capacity at N-1 replicas during rolling updates.
8. Test liveness/readiness failures separately without causing restart loops.
9. Test reconnect bursts after mass termination with backoff/jitter.

Never perform destructive fault injection in production without approval.

## 18. Common issues and fixes

| Symptom | Possible cause | Check to perform |
| --- | --- | --- |
| Transient HTTP 502/503 on every rollout | LB hadn't removed upstream when JVM closed | EndpointSlice propagation, preStop/drain, LB behavior |
| `/readyz` fails right after SIGTERM without JSON | Connector stopped accepting | Normal; check internal state/logs |
| Pod exits before 10s request finishes | Grace too short or graceful not enabled | `server.shutdown`, lifecycle timeout, TERM timing |
| JVM misses signal in Docker | Shell-form ENTRYPOINT/wrapper | Exec-form, `exec java`, PID 1 |
| Pod gets SIGKILL after preStop sleep | Sleep consumed all termination grace | Sum total budget, shorten preStop or raise grace |
| HTTP 200 still served after readiness false | Direct/old connection; readiness does not close port | Drain/admission/routing policy |
| `/livez` fails during drain, kubelet restarts Pod | Misused liveness to report unready | Separate readiness/liveness |
| Actuator management port healthy while main port fails | Probe checks wrong network stack | `add-additional-paths` and main port |
| External LB still sends to terminating Pod | LB cache/deregistration lag | Provider-specific target drain, traffic telemetry |
| WebSockets reset on every rollout | Missing reconnect/close protocol | Client retry/resume/reauth |
| Kafka jobs processed twice after rollout | Non-durable ack/commit, redelivery | Idempotency and consumer drain |
| Spring lifecycle 30s yet total stop >30s | Timeout is per phase, plus bean destruction | Measure each phase and termination grace |
| New Pod Ready yet requests fail | Overly optimistic probe, warmup unfinished | Real startup/readiness, load test |
| `maxUnavailable=0` rolling update still errors | LB lag, insufficient N-1 capacity, sticky connections | Real traffic test, network/ingress |
| Force delete is “fast” yet drops requests | SIGKILL / non-graceful | Avoid force if draining is desired |
| preStop exec fails to run | Image lacks `/bin/sh` or `sleep` | Use compatible image/hook |

## 19. Self-check questions

**1.** Does readiness false automatically close the HTTP server?  
**Answer:** No. It signals routing/probes and does not close sockets or stop the JVM.

**2.** Does SIGTERM guarantee the load balancer already removed the Pod before shutdown?  
**Answer:** No. Routing updates are asynchronous; coordinate Pod termination, preStop/drain, or LB-specific deregistration.

**3.** In Spring Boot 3.3, which property enables graceful shutdown?  
**Answer:** **server.shutdown=graceful**.

**4.** Is `spring.lifecycle.timeout-per-shutdown-phase=30s` an absolute JVM-wide deadline?  
**Answer:** No, it is a per-phase timeout; other phases and cleanup may exist.

**5.** Does `terminationGracePeriodSeconds` start after `preStop` completes?  
**Answer:** No. It includes `preStop` execution time.

**6.** Can a terminating Pod still appear in an EndpointSlice?  
**Answer:** Yes. `ready=false`, `terminating=true`; `serving` can indicate ability to keep serving draining traffic.

**7.** Is SIGTERM guaranteed to make Tomcat return 503 for new requests?  
**Answer:** No. Tomcat usually stops accepting at the network layer; clients may hit refused/reset/timeout.

**8.** Does `/readyz` on a separate management port always prove the application port still accepts traffic?  
**Answer:** No. Use additional paths on the main port if you need to check the real serving stack.

**9.** Why avoid marking liveness broken to remove a Pod from the LB?  
**Answer:** Liveness failures trigger restarts; readiness is meant for removing from traffic.

**10.** Does an 8-second preStop sleep guarantee all external LBs updated?  
**Answer:** No; measure LB/Ingress propagation and tune per environment.

**11.** What is the risk of Docker shell-form ENTRYPOINT?  
**Answer:** A shell as PID 1 may not forward TERM to Java, preventing shutdown hooks from running in time.

**12.** Does SIGKILL run `@PreDestroy`?  
**Answer:** No. Separate durability, idempotency, and recovery are required.

**13.** If an HTTP request finishes while a background task is still running, does `server.shutdown` guarantee the task finishes?  
**Answer:** No. Tasks/queues have their own lifecycles requiring separate drain/ack/durability.

**14.** Does a Last Event ID on SSE/WebSocket reconnect prove authorization by itself?  
**Answer:** No. Event replay must re-authorize by user/tenant.

**15.** Does `maxUnavailable=0` guarantee zero errors during rollouts?  
**Answer:** No. Capacity, readiness accuracy, LB propagation, proxies, and long-lived sessions all affect it.

**16.** Can `/api/state` always be used to read `REFUSING_TRAFFIC` after server graceful stop begins?  
**Answer:** Not reliably. Tomcat may stop accepting HTTP so the endpoint becomes unreachable; inspect logs and application events.

**17.** A request with side effects hits SIGKILL before returning a response. What is the risk of retrying?  
**Answer:** Executing the side effect twice; idempotency keys/state reconciliation are needed.

## 20. Implementation checklist and conclusion

- [ ] Enabled **server.shutdown=graceful** on Spring Boot 3.3.
- [ ] Configured **spring.lifecycle.timeout-per-shutdown-phase** matching in-flight duration.
- [ ] Separated readiness/liveness properly; `/readyz` and `/livez` run on the main HTTP port.
- [ ] Ensured enough replicas/rolling strategy and capacity as old Pods leave the LB.
- [ ] Understood EndpointSlice `ready=false`, serving/terminating states, and routing lag.
- [ ] Used preStop delay if needed, without abusing it, and budgeted it inside total grace.
- [ ] Sized `terminationGracePeriodSeconds` for preStop + JVM shutdown + margin.
- [ ] Docker/OCI images use exec-form ENTRYPOINT or forward signals properly.
- [ ] Avoided using SIGKILL/force delete to test graceful behavior.
- [ ] Defined policies for WebSocket/SSE/gRPC streams and reconnect/backoff.
- [ ] Background workers, queues, and database/outbound clients have separate shutdown handling.
- [ ] Implemented idempotency, transactions, and durable state to survive forced kills.
- [ ] Monitored client errors, LB resets, in-flight requests, phase duration, and exit reasons.
- [ ] Verified in staging using real SIGTERM, Docker stop, and Kubernetes rollouts.
- [ ] Never exposed drain/shutdown control endpoints publicly.

**Remember:** safe shutdown is a **coordinated protocol across the application, load balancer, and orchestrator**, not just a single Spring Boot property. **Readiness** indicates whether the instance should still be picked for new traffic; **EndpointSlice/LB deregistration** shifts traffic away from the stopping instance; **SIGTERM** starts JVM shutdown; **graceful shutdown** lets running requests complete within limits; **SIGKILL** is the final hard boundary. Only when timing, routing, signals, and task lifecycles align do rolling updates reliably minimize request errors.

## Official references

- Spring Boot 3.3 — Graceful Shutdown, `server.shutdown`, and lifecycle phase timeout: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — Actuator Endpoints, Kubernetes probes, readiness/liveness, and additional paths: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — ApplicationAvailability, ReadinessState, and events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Kubernetes — Pod Lifecycle, termination flow, preStop, SIGTERM/SIGKILL, EndpointSlice conditions: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Kubernetes — Pods and Endpoint Termination Flow: https://kubernetes.io/docs/tutorials/services/pods-and-endpoint-termination-flow/
- Kubernetes — Configure Liveness, Readiness and Startup Probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
- Kubernetes — Container Lifecycle Hooks: https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/
- Kubernetes — Deployment Rolling Updates: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- Spring Framework — SmartLifecycle and ApplicationContext shutdown: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Docker — Dockerfile ENTRYPOINT exec and shell forms: https://docs.docker.com/reference/dockerfile/#entrypoint
