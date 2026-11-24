# Handling In-Flight Requests and New Requests at the Spring Boot Server Lifecycle Level

## 1. The Problem: A Server Serving HTTP Is Asked to Stop

A Spring Boot instance is receiving traffic: request A has entered the controller and is calling the database, while request B has just arrived. When the process receives **SIGTERM**, the application must solve two distinct problems:

1. **Already accepted (in-flight) requests:** try to let them finish within a bounded wait window.
2. **New requests:** prevent them from starting new work on an instance about to shut down.

This is the exact purpose of **graceful shutdown** at the embedded web server lifecycle level. It reduces mid-flight cutoffs during deployments, scale-downs, or restarts, while stopping the server from endlessly accepting new work.

~~~text
                 time --------------------------------------->

Server RUNNING                   Server DRAINING          STOPPED
     |                                 |                      |
A ---+---- in-flight HTTP request -----+---- completes? ------+
     |                                 |    within deadline
B ---+---- request finishes            |
     |                                 |
C -------------------------------------+---- new request:
                                           blocked / rejected
                                           per server behavior

               SIGTERM / ApplicationContext.close()
                                 |
                                 v
                   Graceful shutdown begins
~~~

**In-flight** does not mean a request already sent by the client but not yet received by the server; here it refers to requests already accepted by the web server and currently being processed. Requests arriving right near the shutdown moment can hit a **race condition**, so which group they belong to must be determined by the server's acceptance point, not just when the client clicked send.

**Preliminary conclusion:** graceful shutdown means **stopping new intake + waiting for in-flight requests within a deadline**; it is not a promise that every request succeeds or every client receives HTTP 503.

This lesson uses **Spring Boot 3.3.13, Spring Framework 6.1, and Java 17+**. The runnable example uses embedded Spring MVC/Tomcat, then compares with Jetty, Undertow, and Reactor Netty.

## 2. How Do Immediate Shutdown and Graceful Shutdown Differ?

### 2.1. Immediate: Does Not Wait for Older Requests via Drain Mechanism

In **Spring Boot 3.3.x**, the default value of **`server.shutdown`** is **`immediate`**. When the context closes, the server is instructed to stop without performing Boot's graceful wait phase for in-flight HTTP requests.

~~~properties
server.shutdown=immediate
~~~

This can cause active requests to lose connections or fail mid-way. However, do not claim every request is guaranteed to fail: a request may already have finished before the stop action took effect.

### 2.2. Graceful: Reject New, Wait for Old

To enable graceful shutdown in **Boot 3.3.x**, configure explicitly:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Spring Boot starts the graceful phase when **`ApplicationContext.close()`** executes and the server is still active. In-flight requests are given a chance to complete; new requests are no longer served normally.

**Version difference:** starting in **Spring Boot 3.4**, graceful shutdown became the default. When studying or operating Boot **3.3** apps, do not extrapolate from Boot 3.4/3.5/4.x docs that graceful is always enabled out of the box.

### 2.3. Timeout Is a Bound, Not a Mandatory Exact 20-Second Sleep

**`spring.lifecycle.timeout-per-shutdown-phase=20s`** sets the maximum wait window **for each stopping phase of `SmartLifecycle` beans**.

- If requests finish early, the server can finish draining before 20 seconds.
- If a request runs past the limit, shutdown moves on; the unfinished request may be cut off or fail.
- There is no guarantee of a specific HTTP response for timed-out requests.
- This is **not the total shutdown timeout** across all lifecycle phases, callbacks, and containers.
- Nor is it **the timeout of HTTP clients**, reverse proxies, databases, or controllers.

An application with multiple stop phases may need a total duration **larger than one timeout-per-phase**, plus `preStop` and cleanup time. Compare the entire budget against Docker/Kubernetes configuration.

## 3. Position of Graceful Shutdown in the ApplicationContext Lifecycle

Spring Boot controls the embedded server through the **`WebServer`** abstraction and manages shutdown during **`ApplicationContext`** closure.

On a normal JVM shutdown path:

~~~text
SIGTERM / context.close()
     |
     v
JVM shutdown hook (if stopping via JVM shutdown)
     |
     v
ApplicationContext.close()
     |
     +-- ContextClosedEvent
     |
     +-- LifecycleProcessor / SmartLifecycle stop
     |      |
     |      +-- Earliest phase: graceful web-server shutdown
     |      |       +-- prevent new HTTP intake
     |      |       +-- wait for in-flight within bounds
     |      |
     |      +-- subsequent SmartLifecycle phases
     |
     +-- destroy beans / @PreDestroy / destroy methods
     |
     v
Resources are released and process can exit
~~~

According to Spring Boot 3.3 documentation, graceful web-server shutdown occurs **in the earliest phase of stopping `SmartLifecycle` beans**. That matters because many in-flight HTTP requests still need services, datasources, repositories, and other bean resources.

If connection pools or executors close too early, older requests can fail even while the server tries to wait for them. Therefore **dependency lifecycles** and **embedded server lifecycle** must be coordinated.

### 3.1. WebServer API and Result Callback

Spring Boot 3.3 exposes server-level APIs:

~~~java
void shutDownGracefully(GracefulShutdownCallback callback);
void stop();
~~~

These are illustrative API signatures, **not a standalone Java program**.

**`shutDownGracefully(...)`** asks the server to begin a soft shutdown attempt and invoke the callback upon completion. Spring Boot's **`GracefulShutdownResult`** enum defines:

| Value | Meaning |
| --- | --- |
| **`IDLE`** | No active requests remained at the end of the graceful attempt |
| **`REQUESTS_ACTIVE`** | Requests were still active when the grace period expired |
| **`IMMEDIATE`** | Stopped immediately without attempting to wait for active requests |

**This is the server-layer shutdown result, not an HTTP response status sent to clients**. Do not equate **`REQUESTS_ACTIVE`** with 503 or **`IDLE`** with all `@Async` jobs having completed.

In a normal Spring Boot application, **do not expose a public HTTP endpoint to call `WebServer.stop()` or `shutDownGracefully()` directly**. Use `ApplicationContext` lifecycle and standard stop signals so other components also shut down properly.

### 3.2. ApplicationReadyEvent Is Not a Shutdown Event

**`ApplicationReadyEvent`** occurs after normal startup completes. It is not a "server stopped accepting new requests" event. When the app is shutting down, the relevant signals are **`ContextClosedEvent`** and availability/lifecycle states.

Do not write shutdown logic conditioned on whether `ApplicationReadyEvent` was published. Startup readiness and shutdown draining are two separate stages.

### 3.3. Not Every Process Kill Triggers Graceful Shutdown

- **`SIGTERM`** when the JVM is permitted normal shutdown: the shutdown hook gets a chance to close the context.
- **`context.close()`** in code/lifecycle tests: explicitly closes the Spring context via container mechanics.
- **`Ctrl+C`** in an appropriate console: usually leads to normal shutdown, depending on the environment.
- **`SIGKILL`**, JVM crash, power outage: prevents the JVM from completing shutdown hooks.
- **IDE Stop/Terminate**: may perform a hard stop, depending on the IDE and settings.

Thus a test sending **`SIGKILL`** and observing truncated requests **does not prove Spring graceful shutdown is broken**.

## 4. How the Server Handles Already Accepted Requests

An in-flight request can be at any stage:

~~~text
TCP accepted
    |
    +-- HTTP request parsed
    +-- Servlet filters / Security
    +-- DispatcherServlet / HandlerMapping
    +-- Controller -> Service -> Repository
    +-- Call database or external HTTP API
    +-- Serialize response
    +-- Write/flush HTTP response
~~~

When graceful begins, the server **tries to let requests in the active group finish**, while preventing additional new requests. This lowers the odds that a request writing a transaction or building a response is cut mid-flight simply because an instance is deploying.

Still, distinguish the failure causes:

- **Spring web-server graceful timeout**: the server waits only up to the limit.
- **HTTP client timeout**: the caller may give up sooner.
- **Reverse proxy/gateway timeout**: ingress may return 504 even while the server is still processing.
- **Business errors**: database rollbacks, external API failures, validation errors.
- **Network drops between client and server**.
- **Beans/executors closed out of order** in the application lifecycle.

Graceful shutdown **does not turn a failing operation into a successful one**.

### 4.1. Case Where Request Finishes Within the Deadline

Suppose request A begins at second 0 and is expected to run for six seconds. SIGTERM arrives at second 2. The grace period is 15 seconds.

~~~text
t=0                  t=2                   t=6
 |                    |                     |
 +--- A running ------+--- A continues -----+--> response
                      |
                    SIGTERM
                  graceful drain
~~~

Absent other errors, request A has a chance to finish and return a normal result. The server can stop as soon as in-flight work clears, without waiting the full 15 seconds.

### 4.2. Case Where Request Exceeds the Deadline

If A needs 40 seconds while shutdown grace is only 10 seconds, the server **does not promise to wait 40 seconds**. Once the limit expires, the server/container may close the connection; the client may see EOF, reset, timeout, or a proxy error response. Do not invent a fixed HTTP status code for this scenario.

Design realistic request timeouts based on SLOs, check p95/p99 latency, and avoid unbounded waits on remote services lacking timeouts.

### 4.3. Requests Arriving Near the Boundary: Race Conditions

~~~text
t0 client starts sending request B
t1 connector may accept socket/headers
t2 JVM begins closing context
t3 server transitions to graceful draining
t4 is B already in-flight or rejected?
~~~

The answer depends on the exact point where B entered the server, connection type, and implementation. **You cannot decide purely from client-side timestamps**. In rigorous tests, log a marker when the controller starts or use barriers/latches to confirm request A is active before firing SIGTERM.

## 5. New Requests: Differences Among the Four Embedded Servers

Spring Boot 3.3 supports graceful shutdown for both **Servlet** and **reactive web applications** across four embedded servers: **Tomcat, Jetty, Reactor Netty, and Undertow**.

| Embedded server | How new requests are handled during graceful drain |
| --- | --- |
| **Tomcat** | Stops accepting new requests at the network layer |
| **Jetty** | Stops accepting new requests at the network layer |
| **Reactor Netty** | Stops accepting new requests at the network layer |
| **Undertow** | May accept new connections yet immediately respond **`503 Service Unavailable`** |

**Do not assume every shutdown returns HTTP 503.** With Tomcat, Jetty, and Reactor Netty, new requests may receive **no HTTP response from the application at all** because the socket is refused/closed at the network layer.

### 5.1. Why Might Clients Receive 502, 503, or 504?

If a request passes through:

~~~text
Client -> Ingress/Load Balancer -> Spring Boot instance
~~~

what can happen:

- **Connection refused/reset** at the backend: the proxy synthesizes 502 or 503.
- **Backend does not respond before deadline**: the proxy generates 504.
- **Proxy retries on another replica**: the client still gets HTTP 200.
- **Undertow directly returns 503** for new requests.
- **Client-side timeout**: no HTTP status because no response arrived.

When debugging, determine **whether the status came from the app, embedded server, proxy, or client**. Do not treat 503 as the sole proof that graceful server shutdown works properly.

### 5.2. HTTP Keep-Alive and Persistent Connections

HTTP/1.1 keep-alive can reuse connections; HTTP/2 can multiplex streams over a single connection. Boot 3.3 notes that **persistent connections affect how new requests are rejected**.

An already-entered request may continue processing while a **new request over an existing connection** is rejected/closed as decided by the server. Do not claim all sockets close immediately in the exact same way.

With HTTP/2, stream closures or GOAWAY frames can appear depending on the server. Test with the actual HTTP version and proxy you use; never take a single **HTTP/1.1 `curl`** test as a universal contract for all protocols.

### 5.3. Stopping Acceptance at the Server vs. Stopping Routing at the Load Balancer

A draining instance rejecting new requests is proper; at the system level, **the load balancer should stop routing to that instance** and shift traffic to healthy replicas.

If B receives HTTP 200 through ingress after A received SIGTERM, B may actually have been routed to **instance C**. You need instance IDs, request IDs, or backend logs to tell them apart.

## 6. Ready-to-Use Boot 3.3 Configuration

File **src/main/resources/application.properties**:

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=15s
~~~

Or alternative YAML file:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 15s
~~~

Do not declare both files. Values can be overridden via CLI/environment variables per Spring Boot precedence.

**Mind the units:** write **`15s`** instead of just **`15`** assuming seconds. This is a Spring duration property.

### 6.1. One Shutdown Phase Is Not the Entire Shutdown

Components that can consume time:

~~~text
Time for routing changes / preStop
+ time server waits for in-flight HTTP (web-server stop phase)
+ other SmartLifecycle phases
+ cleanup / destroy callbacks
+ safety margin for OS, JVM, network
~~~

This is a budgeting model, not a rigid formula forcing every stage to burn its full budget. **`spring.lifecycle.timeout-per-shutdown-phase`** applies per phase; a multi-phase shutdown can take longer than a single value.

### 6.2. What Should Guide Graceful Timeout Selection?

Measure at least:

1. Endpoint p95/p99 processing durations.
2. Count and length of in-flight requests during scale-downs.
3. HTTP client timeouts and ingress/gateway timeouts.
4. Durations of file uploads/downloads, streaming, or heavy backend calls.
5. Speed of load-balancer routing updates.
6. Executor/consumer stop and cleanup durations.
7. Total **`terminationGracePeriodSeconds`** in Kubernetes.

Never choose an infinite timeout to mask requests hanging on untimed database/backend calls.

## 7. Runnable Java 17+ Example: Tomcat Draining In-Flight Requests

The project below builds a Spring MVC server with:

- **`GET /ping`** returning immediately.
- **`GET /work?delayMs=8000`** simulating an eight-second request.
- **`server.shutdown=graceful`** and a 15-second grace period.
- Actuator readiness/liveness to observe prior to shutdown.

**`Thread.sleep` is only used to simulate processing time in this lesson, not as a production controller pattern.**

### 7.1. Structure

~~~text
graceful-request-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/drain/GracefulRequestApplication.java
  src/test/java/com/example/drain/GracefulRequestApplicationTest.java
~~~

### 7.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>graceful-request-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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

### 7.3. application.properties

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=15s

management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

With Actuator, both probe properties expose **`/readyz`** and **`/livez`** on the main HTTP port per Spring Boot 3.3 mechanics. Once the server begins refusing new requests, HTTP probes may become unreachable; do not expect probes during draining to always return JSON reflecting internal state.

### 7.4. Complete Java File

**src/main/java/com/example/drain/GracefulRequestApplication.java**:

~~~java
package com.example.drain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class GracefulRequestApplication {

    public static void main(String[] args) {
        SpringApplication.run(GracefulRequestApplication.class, args);
    }
}

@RestController
class DemoController {

    @GetMapping("/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/work")
    String work(
            @RequestParam(name = "delayMs", defaultValue = "5000")
            long delayMs) {

        if (delayMs < 0 || delayMs > 20000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "delayMs must be between 0 and 20000");
        }

        System.out.println("BEGIN work delayMs=" + delayMs);

        try {
            Thread.sleep(delayMs);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            System.out.println("INTERRUPTED work delayMs=" + delayMs);
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "work interrupted",
                    ex);
        }

        System.out.println("END work delayMs=" + delayMs);
        return "completed:" + delayMs;
    }
}
~~~

**Why is this code valid?**

- One Java file has one public top-level class **`GracefulRequestApplication`** and one package-private class **`DemoController`** in the same package.
- Spring Boot component scan discovers **`@RestController`**.
- **`spring-boot-starter-web`** selects Spring MVC and embedded Tomcat by default.
- **`@RequestParam`** specifies **`delayMs`** explicitly, without relying on compiler parameter-name retention.
- Delay is bounded from 0 to 20,000 ms to avoid accepting arbitrary durations in the demo.
- The controller prints BEGIN before sleeping so tests know the request actually entered the handler.
- Upon completion, the controller prints END and returns body **`completed:8000`** for an 8-second delay.
- When the thread is interrupted, the code preserves the interrupt flag and returns an error. **Do not assume Tomcat always interrupts request workers at graceful timeout**; the catch block handles it defensively if it happens.

### 7.5. Build and Run

From the project directory:

~~~bash
mvn -q -DskipTests package
java -jar target/graceful-request-demo-1.0.0.jar
~~~

Keep this terminal open, referred to as **Terminal A**.

From Terminal B:

~~~bash
curl -i http://localhost:8080/ping
~~~

The HTTP 200 body is:

~~~text
pong
~~~

HTTP headers may vary, so do not assert verbatim response headers.

### 7.6. Create In-Flight Request A

In Terminal B, run:

~~~bash
curl -v --no-buffer "http://localhost:8080/work?delayMs=8000"
~~~

Terminal A will print:

~~~text
BEGIN work delayMs=8000
~~~

**Only send the stop signal after seeing BEGIN.** If you send SIGTERM before the request actually enters the controller, you are testing a **new request being rejected**, not an **in-flight request being drained**.

### 7.7. Send SIGTERM While A Is Running

On Linux/macOS, in Terminal C use:

~~~bash
jps -l
~~~

Identify the exact PID of the JAR process, then:

~~~bash
kill -TERM <java_pid>
~~~

**`<java_pid>` is a placeholder to replace with the real PID.** Send the signal only to the demo process, never accidentally to another app's PID. In a direct terminal, Ctrl+C can also trigger normal shutdown if the console/JVM receives the signal properly.

**Do not use `kill -9` to test graceful.** SIGKILL cuts off the ability to run shutdown hooks.

On Windows, **`Stop-Process`** can terminate the process using a mechanism not equivalent to POSIX SIGTERM; it is best to test in Linux/containers or an integration setup capable of calling **`ApplicationContext.close()`** in a controlled way.

### 7.8. What Happens to Request A?

With an eight-second request and 15-second grace, if SIGTERM arrives after the BEGIN line and no other error occurs, request A usually has a chance to finish.

Terminal A prints:

~~~text
END work delayMs=8000
~~~

Terminal B receives body:

~~~text
completed:8000
~~~

and HTTP 200. Spring Boot/Tomcat logs may appear between BEGIN and END; there is no single fixed stdout sequence across all environments.

**HTTP 200 is not an absolute guarantee:** the request can still fail due to client timeouts, proxies, networking, or business logic. The demo uses `Thread.sleep` to minimize secondary error sources and isolate server behavior.

### 7.9. New Request B While Draining

After SIGTERM has triggered graceful draining, try in Terminal C:

~~~bash
curl -v --max-time 3 http://localhost:8080/ping
~~~

With **Tomcat**, new requests are normally refused at the network layer. Clients may observe connection errors, reset/EOF, or timing-dependent behavior. **Do not assert HTTP 503 from Tomcat.** With **Undertow**, Boot 3.3 docs describe returning 503 for new requests.

If the request was accepted **before the drain boundary**, it may still complete; if the process already exited, you will simply see the server is gone. For proper analysis, log timestamps/instance IDs and know when draining took effect.

### 7.10. Request Exceeding Grace

Restart the app and issue:

~~~bash
curl -v --no-buffer "http://localhost:8080/work?delayMs=20000"
~~~

Wait for BEGIN, then send SIGTERM. The configured grace period is 15 seconds. This time there is no guarantee the server will wait long enough for the 20-second request. Clients may experience connection closure, timeouts, or an incomplete response.

**Do not hardcode a specific HTTP status code as expected output for an over-deadline case.** Actual behavior depends on the server, threads, TCP sockets, proxies, and when the connection closes.

## 8. JUnit Tests and Process-Level Tests

### 8.1. Verifying Endpoints Work Before Shutdown

File **src/test/java/com/example/drain/GracefulRequestApplicationTest.java**:

~~~java
package com.example.drain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GracefulRequestApplicationTest {

    @Autowired
    private TestRestTemplate client;

    @Test
    void pingReturnsPong() {
        String body = client.getForObject("/ping", String.class);
        assertEquals("pong", body);
    }

    @Test
    void completedWorkReturnsItsDelay() {
        String body = client.getForObject(
                "/work?delayMs=0",
                String.class);
        assertEquals("completed:0", body);
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The test uses `RANDOM_PORT` to avoid colliding with another app on port 8080. **It verifies controllers/routing work**, not server draining. Never treat a **`@SpringBootTest` `contextLoads`** or a unit test calling a controller directly as proof of proper graceful shutdown.

### 8.2. Only a Process-Level Smoke Test Verifies Shutdown Behavior

A thorough test needs to:

1. Build the JAR and launch it in a separate child JVM/process.
2. Wait for the server to become ready.
3. Send long request A, **wait for a log/marker confirming it entered the controller**.
4. Send SIGTERM or invoke context close in a controlled manner.
5. Send new request B after draining takes effect; record both HTTP status **and transport errors**.
6. Verify A completes when remaining duration is shorter than grace, absent external errors.
7. Measure total duration from signal to process exit.
8. Clean up the child process with a deadline so tests never hang.
9. Compare against immediate shutdown and against a request exceeding grace.

You can use **`ProcessBuilder`**, **`Process.isAlive()`**, and **`Process.waitFor(timeout, TimeUnit.SECONDS)`** in Java to manage child processes. However, **`Process.destroy()`** has OS-dependent semantics; to test POSIX SIGTERM accurately, run on Linux/containers and send the actual signal. Never use a test relying on blind `Thread.sleep` as proof that a request was active.

### 8.3. Direct Instance Testing vs. Load-Balanced Testing Are Two Different Tests

**Embedded server test:** send requests directly to instance A, observing A rejecting new requests and draining in-flight work.

**Distributed system test:** send via ingress/load balancer, observing B routed to another ready instance. If B gets 200, it may have come from instance B; never conclude instance A accepted new requests.

## 9. Readiness, Liveness, and Traffic-Acceptance State

Spring Boot provides **`ApplicationAvailability`** with **`LivenessState`** and **`ReadinessState`**. During normal operation, readiness is typically **`ACCEPTING_TRAFFIC`**.

Spring Boot Actuator documentation describes:

| Milestone | ReadinessState | HTTP server behavior |
| --- | --- | --- |
| Normal operation | **`ACCEPTING_TRAFFIC`** | Accepts requests |
| Graceful shutdown | **`REFUSING_TRAFFIC`** | Rejects new requests, drains in-flight |
| Shutdown complete | No serving endpoint left | Server has stopped |

**Do not assume `GET /actuator/health/readiness` is guaranteed to return `REFUSING_TRAFFIC` JSON once graceful starts.** When the HTTP connector rejects new requests, probes may not even reach the server. **Internal availability state and reading that state over HTTP are two distinct concepts.**

### 9.1. Readiness Coordinates Traffic; Graceful Protects In-Flight

~~~text
Kubernetes / Ingress / Load Balancer
        |
        +-- stops routing new requests to Pod A
        |
        v
Pod A / Spring Boot
        |
        +-- graceful stop:
                +-- stops accepting new requests at server
                +-- waits for older in-flight requests within budget
~~~

Readiness does not guarantee load balancers update instantaneously; during a propagation lag, new requests can still reach Pod A. Hence **server-side refusal** and **routing-level removal** complement each other.

### 9.2. Probes on the Main HTTP Port

With Actuator, Boot 3.3 can expose health probes:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

This exposes **`/livez`** and **`/readyz`** on the application port. If probes run only on a separate management port, the management context can keep reporting healthy even when the main application HTTP port has issues. Exposing probes on the main port checks the path closer to real traffic.

Never expose all sensitive Actuator endpoints publicly. In particular, the shutdown endpoint should not be open to the Internet; it is a high-impact control path.

## 10. Kubernetes: SIGTERM, preStop, and terminationGracePeriodSeconds

A rollout/scale-down typically proceeds through:

~~~text
Pod begins terminating
     |
     +-- Endpoints/routing updated (not instantaneous)
     +-- preStop hook if configured
     +-- kubelet sends SIGTERM
     |       |
     |       +-- JVM shutdown hook
     |       +-- Spring context close
     |       +-- graceful web server drain
     |
     +-- total termination grace expires:
             kubelet may send SIGKILL
~~~

**Kubernetes `terminationGracePeriodSeconds` is the total maximum time granted for termination**, including `preStop` duration. There is no default second full budget added after `preStop`.

Illustrative PodSpec snippet:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: app
      image: example/graceful-request-demo:1.0.0
      ports:
        - containerPort: 8080
      readinessProbe:
        httpGet:
          path: /readyz
          port: 8080
        periodSeconds: 3
        timeoutSeconds: 2
      lifecycle:
        preStop:
          exec:
            command:
              - /bin/sh
              - -c
              - sleep 5
~~~

**This is a PodSpec snippet**, not a full Deployment manifest. The image must actually include **`/bin/sh`** and **`sleep`**; on distroless images, this snippet fails due to missing shell.

### 10.1. Does preStop Sleep Replace Graceful Shutdown?

No. `preStop` can be used to let Pod removal propagate through routing, yet while it sleeps, the server **can still accept requests** before SIGTERM is sent. Afterward, Boot still needs graceful draining.

A fixed sleep **does not guarantee** every load balancer has updated. Choose durations empirically or use coordination with better signaling.

### 10.2. Sizing the Budget Sensibly

When you have:

- `preStop` sleep.
- graceful web-server phase.
- other `SmartLifecycle` phases.
- executor shutdown/bean destruction.
- signal or container scheduling delays.

the total duration can exceed a single **`timeout-per-shutdown-phase`** value. Never configure Spring to wait 60 seconds while Kubernetes grants only 30 seconds from the start of termination.

### 10.3. Signals Must Reach the JVM

If a container runs:

~~~sh
sh -c "java -jar app.jar"
~~~

verify whether the shell forwards signals and PID 1 responds properly. A commonly suitable option is:

~~~sh
exec java -jar app.jar
~~~

so the JVM replaces the shell process when running a script. Do not assume every Docker image/entrypoint automatically forwards SIGTERM cleanly.

## 11. Long-Lived Requests: WebSocket, SSE, HTTP/2, and MVC Async

### 11.1. WebSocket

After an HTTP upgrade to WebSocket, connections can stay open for hours. Do not assume **`server.shutdown=graceful`** sends application-specific close frames, saves session state, or forces every client to reconnect cleanly.

For WebSockets, an application may need to:

- Stop accepting new sessions.
- Announce impending shutdown with an appropriate message.
- Close sessions per protocol.
- Let clients reconnect to another instance.
- Persist state needed for recovery.

Test with the exact server and WebSocket implementation in use.

### 11.2. Server-Sent Events (SSE) and Streaming Responses

SSE can hold a response open indefinitely. The server cannot wait forever when grace periods are bounded. Design cancellation/completion, reconnection, and resume semantics (such as `Last-Event-ID` where appropriate) at the application layer.

Similarly, very long file uploads/downloads can exceed deadlines. Use chunking, resumability, or job-based transfers instead of raising grace infinitely.

### 11.3. HTTP/2 Multiplexing

A single HTTP/2 TCP connection carries multiple streams. One stream may already be in flight while a new stream opens right at the drain boundary. How new streams are refused and connections close depends on the HTTP/2 implementation and may involve GOAWAY frames. Never extrapolate HTTP/1.1 keep-alive results to HTTP/2 or gRPC.

### 11.4. Spring MVC Async

MVC controllers returning **`Callable`**, **`DeferredResult`**, or **`CompletableFuture`** can release the initial servlet thread while the response is still pending. That **does not mean the HTTP request has finished**. Server-side draining tracks request state at the Servlet layer.

If the executor used to complete the future shuts down prematurely, the request can fail even while the server is in graceful mode. Executor lifecycles must therefore align with drain duration.

### 11.5. WebFlux/Reactor Netty

Reactor Netty supports graceful shutdown at the embedded server layer. For long-lived reactive streams, completion and timeouts depend on the publisher and server. Never block the Reactor Netty event loop to "keep requests alive", and never assume infinite streams complete before grace expires.

## 12. HTTP Graceful Does Not Guarantee All Background Tasks Drain

**`server.shutdown=graceful`** focuses on the HTTP web server. It is not a durable queue and does not automatically wait for all:

- **`@Async`** fire-and-forget tasks.
- **`@Scheduled`** jobs.
- Kafka/RabbitMQ/message consumers.
- Batch jobs decoupled from HTTP responses.
- WebSocket application state.
- Outbound I/O remaining active after the HTTP response finished.

These components require their own shutdown/lifecycle policies. Example executor configuration:

~~~java
@Bean
ThreadPoolTaskExecutor reportExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("report-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(10);
    return executor;
}
~~~

**This is a snippet** requiring imports for **`@Bean`**, **`ThreadPoolTaskExecutor`**, and placement in a Spring configuration class. It provides no durability guarantee on JVM crash. Executor wait time also consumes its own shutdown budget.

A draining HTTP request may need an executor or DB. If a dependency shuts down before the request completes, graceful mode cannot save that request. Define explicit stop ordering and avoid releasing resources prematurely.

### 12.1. Transaction Commits While Client Loses Connection

An HTTP request writing to a database may have **committed**, yet the client lost the connection and does not know the outcome. When the client retries, duplicate-operation risk remains. Use **idempotency keys**, transaction boundaries, and job state tracking to handle ambiguous outcomes.

Graceful shutdown lowers the probability of mid-flight interruption but **does not guarantee exactly-once by itself**.

### 12.2. Request Completes Before Background Task Finishes

An API might return 202 Accepted and hand off a background task. From the embedded web server's perspective, the HTTP response ended, so the background task **is no longer an in-flight HTTP request**. Shutdown can still lose unfinished tasks if kept only in memory.

For work that must complete, use a queue/broker, outbox, Spring Batch, or persistence to recover after crashes/restarts.

## 13. Common Errors and Diagnostics

### 13.1. "Graceful guarantees all old requests return 200"

No. Graceful provides a wait window; it does not eliminate client/proxy timeouts, DB errors, error handling, or grace deadlines.

### 13.2. "New requests always receive HTTP 503"

No. In Boot 3.3, Tomcat/Jetty/Reactor Netty block at the network layer; Undertow may return 503.

### 13.3. "Boot 3.3 defaults to graceful"

Wrong. Boot 3.3 defaults to immediate; the default changed in Boot 3.4. Verify the exact version before deploying.

### 13.4. "Setting timeout-per-shutdown-phase=20s covers the whole process"

Wrong. Multiple `SmartLifecycle` phases, bean cleanup, and `preStop` can add extra time; containers have a separate total grace limit.

### 13.5. "Having a readiness probe means graceful is unnecessary"

Wrong. Load balancers update routing with delay; in-flight requests still need the server to wait. Both mechanisms complement each other.

### 13.6. "While draining, GET /readyz must return REFUSING_TRAFFIC JSON"

No. Once the web server stops accepting new connections, probes may not be able to reach the endpoint.

### 13.7. "preStop sleep is graceful shutdown"

No. `preStop` only gives routing time to update; it does not make Boot immediate mode wait for in-flight requests.

### 13.8. "SIGKILL still runs @PreDestroy"

Wrong. SIGKILL prevents the JVM from running normal shutdown hooks/cleanup.

### 13.9. "HTTP graceful waits for @Async/@Scheduled jobs too"

Wrong. Tasks decoupled from HTTP requests need their own lifecycle and completion/durability mechanisms.

### 13.10. "HTTP 200 after SIGTERM proves Pod A still accepts new requests"

Not necessarily. The request may already have been in flight, or the proxy routed it to Pod B.

### 13.11. "Keeping a keep-alive connection means the server must accept all new requests on it"

No. Persistent connections affect drain details without creating a contract that new requests are always accepted.

### 13.12. "Just set a very long grace period"

Not a universal solution. Excessive timeouts slow rollouts, exceed Kubernetes grace, and mask hung dependencies. Measure tail latency and improve client retries, cancellation/resumption, and idempotency.

### 13.13. "ApplicationContext.close() and WebServer.stop() are equivalent"

Not quite. `Context.close` coordinates bean lifecycles; calling stop directly can bypass the application's orchestration mechanisms.

### 13.14. "Controller sleep returning 200 proves production is completely safe"

No. The demo only tests pure sleeping/compute requests; production has DBs, outbound HTTP, streaming, queues, transactions, and proxies that must be tested separately.

## 14. Recommended Test Matrix

| Scenario | Expected behavior to evaluate |
| --- | --- |
| Graceful + A finishes before grace | A has a chance to return a normal response |
| Immediate + A running | No graceful drain waiting |
| Graceful + A exceeds deadline | Server does not wait forever; client may fail |
| New B after drain starts | Stopping instance does not serve B as normal traffic |
| B arrives right at boundary | Identify race; do not draw conclusions from one HTTP status |
| Tomcat vs Undertow | Do not expect identical status codes |
| Traffic via load balancer | New requests route to ready replicas |
| HTTP keep-alive/HTTP2 | Observe connection reuse, closure, and stream behavior |
| SSE/WebSocket | Dedicated drain/reconnect strategy exists |
| Unfinished `@Async` job | Dedicated lifecycle/durable recovery exists |
| SIGTERM | Shutdown hooks/context close get a chance to run |
| SIGKILL | No cleanup guarantee |
| Kubernetes rollout | Termination grace covers `preStop` and all phases |

### 14.1. Metrics and Logs to Observe

- Active HTTP requests when shutdown begins.
- Requests completed within grace and requests still active when deadline expires.
- Duration from SIGTERM to web server stopped.
- Total context close duration.
- Connection refusals/resets and HTTP 502/503/504 at each layer.
- Instance ID, request ID, and route to distinguish replicas.
- Tasks/executors still running during cleanup.
- Retries and duplicate operations after rollouts.

Do not assume all of these metrics are built into Boot automatically; depending on your monitoring stack, Actuator/Micrometer, access logs, and custom instrumentation may be needed.

## 15. Production Checklist

- [ ] Fixed Spring Boot version and verified default `server.shutdown`.
- [ ] For Boot 3.3, explicitly enabled **`server.shutdown=graceful`**.
- [ ] Configured `timeout-per-shutdown-phase` with an explicit duration like **`15s`**.
- [ ] Understood timeout applies per lifecycle phase, not globally.
- [ ] Measured p95/p99/tail latency and identified long-running requests.
- [ ] Added timeouts to HTTP/DB calls, avoiding unbounded waits.
- [ ] Configured appropriate readiness probes; prefer checking on the main port if needed.
- [ ] Verified load balancer stops routing to draining instances promptly.
- [ ] Sized Kubernetes `terminationGracePeriodSeconds` larger than planned shutdown budget.
- [ ] Ensured `preStop` does not accidentally consume the entire grace period.
- [ ] Verified JVM receives SIGTERM properly without being swallowed by a wrapper shell.
- [ ] Avoided using SIGKILL to evaluate graceful behavior.
- [ ] Tested in-flight requests completing within grace.
- [ ] Tested new requests being rejected without forcing 503 expectations on Tomcat.
- [ ] Tested requests exceeding the deadline.
- [ ] Tested WebSocket/SSE/HTTP2 if used.
- [ ] Prevented releasing datasources/executors before in-flight requests using them finish.
- [ ] Ensured background tasks have shutdown policies and persistence where critical.
- [ ] Ensured APIs with side effects support retries/idempotency.
- [ ] Placed monitoring at server, proxy, and client layers rather than only one layer.
- [ ] Maintained enough ready replicas during rolling deployments.

## 16. Self-Check Questions

**1. Does Boot 3.3 enable graceful by default?** No. You must set **`server.shutdown=graceful`**; Boot 3.4 changed the default.

**2. How do in-flight requests differ from new requests?** In-flight requests were already accepted by the server and started processing before the drain boundary; new requests arrive after the server begins refusing new intake.

**3. Does 15s graceful guarantee an 8s request returns 200?** Not absolutely; it gives it a chance to finish absent client, proxy, network, or business errors.

**4. Does Tomcat return 503 directly to every new request after draining begins?** No. Tomcat blocks at the network layer; Undertow has the 503 behavior.

**5. Does a 20s per-phase timeout force the whole JVM to exit in 20s?** No; other phases and cleanup can still take time.

**6. Why might GET `/readyz` fail to return JSON while draining?** Because the connector is refusing new requests, probes may be unable to connect.

**7. Can `preStop` sleep replace graceful shutdown?** No; it does not make the server wait for in-flight requests.

**8. Does HTTP graceful automatically wait for `@Scheduled`/`@Async`?** No; background tasks need their own shutdown mechanisms.

**9. If the process receives SIGKILL, is `@PreDestroy` guaranteed to run?** No.

**10. Should one HTTP/1.1 test be used to infer WebSocket/HTTP2 behavior?** No; connection and stream semantics differ.

**11. Why doesn't a client receiving 200 after SIGTERM prove the old instance accepted a new request?** Because a proxy may have routed it to another instance or the request was accepted before draining.

**12. What is needed for a data-writing endpoint whose response might be lost after commit?** Idempotency keys, transaction boundaries, retries, and operation state lookup.

## 17. Conclusion

At the server lifecycle level, **graceful shutdown solves two distinct problems**: stopping new requests from entering the server and waiting for in-flight requests within a bounded time window.

With Spring Boot 3.3:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=15s
~~~

Tomcat, Jetty, and Reactor Netty stop new requests at the network layer; Undertow may return HTTP 503. In-flight requests get a chance to complete before the deadline, though unconditional success is never guaranteed. In production, combine graceful web shutdown with readiness/routing, SIGTERM, Kubernetes grace periods, timeouts, retries/idempotency, and background task lifecycles.

To verify for real, start an in-flight request, wait for the BEGIN marker, send SIGTERM to the exact process, watch A finish, and test a new request after the drain boundary; then retest with an over-deadline request, through a load balancer, and with production protocols.

## 18. Official Documentation

- Spring Boot 3.3.13 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3.13 — Actuator: Application Lifecycle and Probe States: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3.13 — SpringApplication and Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — WebServer.shutDownGracefully API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/server/WebServer.html
- Spring Boot 3.3.13 — GracefulShutdownResult API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/server/GracefulShutdownResult.html
- Spring Framework — SmartLifecycle and bean lifecycle: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot 3.4 release notes — default graceful shutdown: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes