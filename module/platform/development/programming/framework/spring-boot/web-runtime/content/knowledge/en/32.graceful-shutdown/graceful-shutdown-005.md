# Differences in Connection Rejection Behavior Across Embedded Servers

**Module:** Spring Boot - web-runtime  
**Parent topic:** Graceful Shutdown

## 1. Scenario: same graceful shutdown, yet clients observe different errors

A system using Spring Boot deploys multiple replicas behind a load balancer. When a pod receives SIGTERM for a version update, running requests are allowed to finish, while new requests should go to healthy pods. Operations configured:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

However, when observing direct connections to the stopping pod, results differ:

- With **embedded Tomcat**, a client opening a new HTTP connection may be rejected at the network level: no valid HTTP status code is received.
- With **embedded Jetty**, new request rejection also falls under the **network-level** group.
- With **Reactor Netty** (typically WebFlux's embedded reactive server), new requests are rejected at the **network layer**.
- With **embedded Undertow**, during the **grace period** the server still accepts new connections but **immediately returns HTTP 503 Service Unavailable**.

This is an intentional difference among embedded web servers per **Spring Boot 3.3**. It does not mean one server is more graceful than another on a simple scale. **Same goal: give in-flight requests a chance to complete, prevent new work from starting.** The difference lies in the **rejection mechanism and what HTTP clients, gateways, and metrics observe**.

According to official Spring Boot 3.3 docs, Jetty, Reactor Netty, and Tomcat stop accepting new requests at the network layer; Undertow accepts new connections but returns 503. The docs also emphasize that **persistent connections** can alter observed behavior. Therefore, you cannot assign a single type of network exception to all Tomcat requests, nor guarantee Undertow always returns 503 once the process has finished shutting down.

### Learning objectives

After this lesson, you can:

1. Describe **ApplicationContext close**, **SmartLifecycle**, shutdown hooks, timeouts, and grace periods.
2. Distinguish **network-level refusal**, **HTTP 503**, **proxy 502/504**, **connection reset**, **timeout**, **EOF**, and **connection refused**.
3. Explain the **Tomcat / Jetty / Reactor Netty / Undertow** behavior table for Spring Boot 3.3.
4. Identify the impact of **HTTP keep-alive**, connection pooling, HTTP/2, WebSocket/SSE, proxies, and load balancers.
5. Build a **runnable Spring Boot 3.3 + Java 17+ app**, switching among Tomcat, Jetty, and Undertow via Maven profiles.
6. Launch the JAR, open a slow request, send **SIGTERM** to the JVM, and verify the differences using curl/a Java client.
7. Design **readiness draining**, Kubernetes `preStop`/`terminationGracePeriodSeconds`, and client retries/idempotency.
8. Distinguish results from a **direct client** versus **through an ingress**, knowing when observed 503s come from the edge.
9. Track in-flight durations, rejection/error ratios, and diagnose common shutdown issues.

## 2. When does graceful shutdown operate in Spring Boot?

A typical shutdown sequence:

~~~text
Pod/Service RUNNING
     |
     | SIGTERM / ApplicationContext close
     v
Application starts graceful shutdown
     |
     +--> HTTP server stops admitting new work
     |
     +--> Existing in-flight requests can finish
     |     within the configured shutdown phase grace budget
     |
     +--> Readiness moves toward REFUSING_TRAFFIC
     |
     +--> SmartLifecycle beans stop across phases
     |
     v
Context closed / server stopped / process exits
~~~

**Graceful does not mean keeping the server alive forever.** Graceful shutdown is a window of opportunity to finish current work. When **spring.lifecycle.timeout-per-shutdown-phase** expires or the host/orchestrator forces the process to stop, an in-progress request can be cut off. This duration is the **timeout for the lifecycle shutdown phase**, not a dedicated deadline per HTTP request and not an absolute total cap on all process cleanup.

In Spring Boot 3.3:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Or equivalent YAML:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

**server.shutdown=graceful** is the setting that must be stated explicitly for Spring Boot 3.3 to select graceful shutdown. **server.shutdown=immediate** performs a shutdown without that request waiting stage.

**Do not blindly copy defaults from Spring Boot 3.5/4.x.** In newer versions, graceful shutdown may be enabled by default and the list of supported embedded servers can change. A runbook must record the **actual Spring Boot version and embedded server**, without assuming behavior from docs of another version.

### Why does the stop signal matter?

**SIGTERM** on Linux/containers typically triggers the JVM shutdown hook; Spring Boot closes the ApplicationContext along the shutdown flow. **SIGKILL** does not run cleanup/shutdown hooks. An IDE **Stop** button or process manager may force-kill instead of sending the proper signal.

Cases that may fail to trigger the expected behavior:

- Using **kill -9** or the container getting OOMKilled.
- Killing only the **Maven launcher** while a forked JVM still runs the application.
- Orchestrator exhausting its termination grace period and sending SIGKILL.
- JVM crash or power loss.
- Omitting `server.shutdown=graceful` on a Boot branch that requires configuring it.
- Web server/custom connector not running under Spring Boot's managed lifecycle.

Therefore, the experiment will run **java -jar** and send SIGTERM directly to the **app JVM PID**. Do not use **mvn spring-boot:run** and assume the Maven PID is the app PID.

## 3. Comparison table of the four embedded servers in Spring Boot 3.3

| Embedded server | Common web stack | Rejecting new requests during grace period | What a direct client may observe | Key takeaway |
| --- | --- | --- | --- | --- |
| **Tomcat** | Default **Servlet/MVC** | Stops accepting new requests at the **network layer** | Connect failure, connection closed/reset, no HTTP response; timing-dependent | Does not return an application-level HTTP 503 by default for new requests. |
| **Jetty** | **Servlet/MVC**, also reactive-capable | Stops accepting new requests at the **network layer** | Network exception/EOF/timeout or connection cannot be reused | Does not promise a fixed curl error code. |
| **Reactor Netty** | Default **Reactive WebFlux** | Stops accepting new requests at the **network layer** | Network-level failure, closed connection, retryable transport errors per client | Does not become an MVC embedded server just by using WebClient. |
| **Undertow** | **Servlet/MVC**, also has reactive integration in Boot 3.3 | Can still accept connections yet **returns HTTP 503 Service Unavailable** for new requests | HTTP status 503 within graceful window; after server closes, may see network error | HTTP 503 is a server-side rejection mechanism while still accepting connections. |

**Source:** Spring Boot 3.3 Graceful Shutdown, section detailing new request rejection methods. Examples of network exceptions in the table are **observable possibilities**, not outputs guaranteed by Spring Boot across every OS/kernel/proxy.

**Important:** Spring Boot 3.3's Servlet stack primarily uses **Tomcat, Jetty, Undertow**. Reactor Netty is normally the server for **WebFlux/reactive**, not an embedded Servlet container. Comparing the four servers compares graceful shutdown mechanisms in Boot 3.3, **not four interchangeable Servlet containers**.

### How to pick the right server

- **spring-boot-starter-web** pulls **spring-boot-starter-tomcat** by default.
- To test **Jetty**, exclude the Tomcat starter and add **spring-boot-starter-jetty**.
- To test **Undertow**, exclude the Tomcat starter and add **spring-boot-starter-undertow**.
- **spring-boot-starter-webflux** pulls Reactor Netty by default for the reactive server. If both Spring MVC and WebFlux are present, Spring Boot usually prioritizes Servlet MVC; having Reactor Netty libraries to use WebClient **does not prove the server is Netty**.

Use the dependency tree/startup logs to verify the actual web server. Do not use an HTTP client's class name as evidence of which HTTP server is listening on the port.

## 4. How does network-level refusal differ from HTTP 503?

### 4.1. Rejection at the network layer

Network-level model:

~~~text
Client                  Tomcat / Jetty / Reactor Netty
  |
  | TCP connect / request on connection
  |----------------------------------------->
  |             listener/accept path stopping
  |
  |<---------- close/refusal/reset/timeout ----
  |
  +--> may have NO valid HTTP response status
~~~

**Network-level** means new requests are not processed as normal HTTP requests producing an application-generated response status. However, the concrete outcome depends on the time window and TCP/socket state:

- **Connection refused (ECONNREFUSED)**: no listener is accepting connects on that address/port, or the network stack returns RST.
- **Connection reset by peer (ECONNRESET)**: connection is reset after establishment or mid-send/receive.
- **EOF / Empty reply from server**: socket closes before the client receives a valid HTTP response.
- **Timeout**: SYN, TLS handshake, or response fails to finish before the client deadline.
- **Connection closed**: client library detects the connection cannot continue or a keep-alive socket was closed.

Not all of the mechanisms above happen every time with Tomcat. The phrase **network-layer refusal** is an official behavioral description, not a guarantee of a specific Linux errno or fixed curl line.

### 4.2. Rejection via HTTP status 503

Undertow model:

~~~text
Client                          Undertow in grace period
  | TCP connect
  |-------------------------------------------->
  | TCP established
  |<--------------------------------------------|
  | GET /ping HTTP/1.1
  |-------------------------------------------->
  | HTTP/1.1 503 Service Unavailable
  |<--------------------------------------------|
~~~

**HTTP 503** is a valid HTTP response: the request reached an HTTP handler/connector capable of returning a status. The client can record the response status, apply a 503 policy, and avoid confusing it with a DNS/TCP error.

However, **503 does not mean the business request ran or definitely had no system-wide side effects**. A 503 can come from Undertow shutdown, a load balancer, gateway overload, an upstream service, a circuit breaker, or the app itself. To identify the source, check response headers, per-hop logs, readiness state, and tracing.

**503 does not necessarily include Retry-After.** A layer might attach Retry-After, but Spring Boot Undertow graceful shutdown should not be assumed to automatically provide that header. Clients need their own retry policies.

### 4.3. Going through an ingress changes things further

~~~text
Client ----> Load Balancer / Nginx ----> Pod shutting down
                      |
                      +--> maybe 502 / 503 / 504
                      +--> maybe TCP close
                      +--> maybe route to healthy pod
~~~

If a client goes through a gateway, HTTP **502 Bad Gateway** may mean the gateway could not connect upstream; **503** may mean the gateway ran out of healthy backends or upstream Undertow returned 503; **504** may mean an upstream timeout at the gateway. These statuses **do not directly reveal which embedded server group is running**.

To test the raw mechanism, send requests **directly to the JVM's listening port**, bypassing CDNs, ingresses, or service meshes (unless intentionally testing edge behavior). In production, never bypass TLS/security to expose pods publicly: direct tests belong only in local or safe test networks.

## 5. Timing and keep-alive create different results

A graceful shutdown spans several moments in time:

~~~text
T0: RUNNING; requests and new connections accepted
T1: request A enters /slow and is still in flight
T2: SIGTERM reaches JVM; context shutdown starts
T3: server begins rejecting new requests according to mechanism
T4: request A finishes, grace budget no longer needed
T5: connector and JVM stop; no HTTP listener
~~~

Between **T1–T3**, if a new client connects before shutdown logic takes effect, the request may still be accepted. Between **T3–T4**, Undertow can usually return 503; Tomcat/Jetty/Netty can trigger network-level failures. After **T5**, even Undertow has no connector left to return 503. Therefore, a single call made after the app has exited **does not prove the difference**.

### Persistent / keep-alive HTTP connections

HTTP/1.1 keeps connections open by default. An HTTP client with a connection pool may reuse a socket opened before shutdown. How requests are rejected on a persistent connection **can differ** from how a new TCP connection is rejected—a point emphasized by Spring Boot docs.

Accordingly:

- **New TCP connection** and **new HTTP request on an old socket** are two distinct test cases.
- A fresh curl invocation to localhost usually creates a new client connection; adding **Connection: close** helps avoid keeping the connection after the response.
- With Apache HttpClient, Java HttpClient, WebClient, or load balancers, connection pools may still hold old sockets.
- **HTTP/2** multiplexes multiple streams over one connection; a new stream is not a new TCP connection. Protocol and connector implementations affect shutdown behavior.
- Long polling, SSE, and WebSockets have long lifecycles; do not extrapolate from a short GET.

When testing, record: **HTTP version**, direct/proxy path, reused vs fresh connection, TLS, time since SIGTERM, and server version.

## 6. Timeout: a chance to complete, not a 200 OK promise

Configuration:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

gives Spring Boot a **shutdown-phase timeout**. A request that started before shutdown and finishes within the grace budget has a chance to return normally. A 60-second request can be terminated before finishing if grace is only 20 seconds.

**Things that MUST NOT be inferred:**

- Not every request gets its own 20 seconds.
- The process does not always terminate at exactly second 20.
- Not every request running before SIGTERM is guaranteed to return 200.
- Infinite WebSocket/SSE connections are not kept alive until the client disconnects on its own.
- Kubernetes `terminationGracePeriodSeconds` does not automatically equal Boot's timeout.
- Infrastructure does not stop routing traffic at the exact instant of SIGTERM, due to endpoint/proxy update lag.

Stop times of other SmartLifecycle beans and cleanup also require budget. If a pod is killed after 10 seconds, configuring a 20-second Boot grace will not let a 15-second request complete.

## 7. Java 17+ demo comparing Tomcat, Jetty, and Undertow

The demo intentionally creates two endpoints:

- **GET /ping**: fast handler returning plain text **pong**.
- **GET /slow?delayMs=15000**: sleeps for an allowed duration, then returns **done:15000**. It holds an **in-flight request** while SIGTERM is sent, letting us observe the grace window before the JVM exits.

We use **Spring Boot 3.3.13**, **Java 17+**, Maven, and Servlet Spring MVC. Reactor Netty has its own section because it is a reactive server; do not force Reactor Netty into the Servlet profiles.

Structure:

~~~text
graceful-server-demo/
  pom.xml
  src/main/
    java/com/example/graceful/
      GracefulServerApplication.java
    resources/
      application.properties
  src/test/
    java/com/example/graceful/
      HttpEndpointsTests.java
  NewRequestProbe.java
~~~

### 7.1. Complete pom.xml with three Maven profiles

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
    <artifactId>graceful-server-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <exclusions>
                <exclusion>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-tomcat</artifactId>
                </exclusion>
            </exclusions>
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

    <profiles>
        <profile>
            <id>tomcat</id>
            <activation>
                <activeByDefault>true</activeByDefault>
            </activation>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-tomcat</artifactId>
                </dependency>
            </dependencies>
        </profile>

        <profile>
            <id>jetty</id>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-jetty</artifactId>
                </dependency>
            </dependencies>
        </profile>

        <profile>
            <id>undertow</id>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-undertow</artifactId>
                </dependency>
            </dependencies>
        </profile>
    </profiles>

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

**Why exclude Tomcat from starter-web?** If both Tomcat and Jetty/Undertow are present by adding a starter without excluding Tomcat, the classpath contains multiple Servlet containers; the auto-configured server might not be the one you expect. This lesson uses profiles to include **only one container starter**.

**Maven activeByDefault:** `tomcat` activates when no other profile is selected; explicitly choosing **-Pjetty** or **-Pundertow** replaces the default profile from the same POM. **Do not activate multiple server profiles simultaneously.**

After building, check console startup logs or the dependency tree:

~~~bash
mvn -Pjetty dependency:tree
mvn -Pundertow dependency:tree
~~~

Do not use image or service names as proof. To compare containers, verify the real server inside the process.

### 7.2. application.properties

Create **src/main/resources/application.properties**:

~~~properties
server.port=8080
spring.application.name=graceful-server-demo

# Spring Boot 3.3: enable graceful shutdown explicitly
server.shutdown=graceful

# Lifecycle phase grace period, not a per-request timeout
spring.lifecycle.timeout-per-shutdown-phase=20s

# Enable readiness/liveness endpoints for local demo.
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health

logging.level.com.example.graceful=INFO
~~~

**/actuator/health/readiness** can be used to observe state while the application is running. During shutdown, the HTTP connector may stop accepting new requests, so **the probe is not guaranteed to return JSON**. Rather than relying on a single readiness call after SIGTERM, combine application lifecycle events, access logs, connection errors, and proxy metrics.

### 7.3. Complete Java application

Create **src/main/java/com/example/graceful/GracefulServerApplication.java**:

~~~java
package com.example.graceful;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class GracefulServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(GracefulServerApplication.class, args);
    }
}

@RestController
class WorkController {

    private static final Logger log =
            LoggerFactory.getLogger(WorkController.class);

    @GetMapping(value = "/ping", produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }

    @GetMapping(value = "/slow", produces = MediaType.TEXT_PLAIN_VALUE)
    public String slow(
            @RequestParam(name = "delayMs", defaultValue = "15000")
            int delayMs) throws InterruptedException {

        // Demo guard: allow request sleep only in 0..30000 ms.
        int bounded = Math.max(0, Math.min(delayMs, 30000));
        log.info("slow.begin delayMs={}", bounded);

        Thread.sleep(bounded);

        log.info("slow.end delayMs={}", bounded);
        return "done:" + bounded;
    }
}
~~~

**This is runnable code** with Java 17 and Spring Boot Servlet MVC. Only the main class is public, and `WorkController` is package-private in the same package, scanned by Spring component scan. No database or external service is involved.

**Intentional characteristics of the demo:**

- **Thread.sleep** simulates an in-progress HTTP request. Do not use `Thread.sleep` as a production business architecture; it is only used to open an observation window.
- **delayMs=15000** is shorter than the 20s grace timeout, giving request A a chance to finish. That still does not guarantee completion if SIGTERM arrives too late or the container is killed early.
- **Bounded delay** prevents an unbounded input from holding a Servlet worker too long. Production needs async jobs/timeouts/appropriate schedulers.
- **slow.begin/slow.end logs** confirm the request entered the controller **before SIGTERM was sent**. Do not rely solely on a 1-second sleep if the server starts up slowly.
- **/ping** acts as the new-request probe, not a health/readiness management endpoint.

### 7.4. Test HTTP behavior before testing shutdown

Create **src/test/java/com/example/graceful/HttpEndpointsTests.java**:

~~~java
package com.example.graceful;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpEndpointsTests {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();

    private String get(String path) throws Exception {
        HttpRequest req = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                req, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        return response.body();
    }

    @Test
    void pingWorks() throws Exception {
        assertEquals("pong", get("/ping"));
    }

    @Test
    void slowZeroReturnsImmediately() throws Exception {
        assertEquals("done:0", get("/slow?delayMs=0"));
    }
}
~~~

Run:

~~~bash
mvn -Ptomcat test
mvn -Pjetty test
mvn -Pundertow test
~~~

**The JUnit tests above verify that the endpoints work on each container**; they **cannot test how new requests are rejected after SIGTERM**, because SpringBootTest starts/closes the application context inside the test process and does not create an independent process lifecycle/control connection like the experiment. To verify graceful shutdown, you must test at the process level via **java -jar**, signals, and real client requests.

## 8. SIGTERM experiment: measuring during the exact drain phase

Perform on **Linux/macOS/WSL/Bash**. On native Windows PowerShell, signal/process control differs; use WSL/containers to repeat the SIGTERM experiment accurately. Do not use IDE Stop because it may force-terminate.

### Step 1. Build one container variant

For example, Tomcat:

~~~bash
mvn -Ptomcat -DskipTests clean package
~~~

To test Jetty or Undertow, after finishing the previous measurement, rebuild the corresponding JAR:

~~~bash
mvn -Pjetty -DskipTests clean package
~~~

or:

~~~bash
mvn -Pundertow -DskipTests clean package
~~~

**Run only one variant at a time**, because the JAR output is rebuilt with a different dependency classpath. Do not build Undertow and claim you are running Tomcat without checking startup logs.

### Step 2. Start the JVM directly

In terminal A, from the project directory:

~~~bash
java -jar target/graceful-server-demo-0.0.1-SNAPSHOT.jar > server.log 2>&1 &
APP_PID=$!
echo "$APP_PID"
~~~

Once the app is running, in terminal B:

~~~bash
curl -si http://127.0.0.1:8080/ping
curl -si http://127.0.0.1:8080/actuator/health/readiness
~~~

**/ping** returns **pong** normally. Readiness is usually UP once ready, though health JSON contents can vary with auto-configuration. **APP_PID** must be the PID of the Java process running the JAR, not the shell or Maven PID.

### Step 3. Hold an in-flight request

In terminal B:

~~~bash
curl -sS --max-time 30 \
  "http://127.0.0.1:8080/slow?delayMs=15000" > slow.out &
SLOW_PID=$!
echo "$SLOW_PID"
~~~

Check **server.log** or console to confirm **slow.begin delayMs=15000** appeared. **Only after that** send SIGTERM; if the request has not entered the controller yet, it may become a new request and get rejected instead of being an in-flight request.

### Step 4. Send SIGTERM and immediately try a new request

In terminal A:

~~~bash
kill -TERM "$APP_PID"
~~~

In terminal B, while the slow request is still waiting:

~~~bash
curl -v -i --http1.1 \
  --connect-timeout 2 --max-time 4 \
  -H 'Connection: close' \
  http://127.0.0.1:8080/ping
~~~

The new curl command creates a fresh client invocation aimed at a new connection. **Do not use curl -f/--fail** here, because HTTP 503 causes curl to exit non-zero and can make it harder to distinguish a valid HTTP 503 response from a network error.

Then:

~~~bash
wait "$SLOW_PID"
cat slow.out
~~~

If `/slow` finishes within the grace budget and is not cut off by infrastructure, the file contains:

~~~text
done:15000
~~~

This is the **expected result when the request runs to completion**. If the process is force-killed, times out, or the timing is off, the file may be empty/incomplete; do not pretend this outcome is guaranteed on every run.

### Step 5. Compare

- **Tomcat/Jetty**: `/ping` arriving after graceful shutdown takes effect usually **does not receive HTTP 503 directly from the server**, encountering a network-level refusal/closed connection instead. The curl error text can vary across OS and timing.
- **Undertow**: during the grace period while still keeping its connector accepting requests, **/ping can return HTTP/1.1 503 Service Unavailable**. If tested after the app has exited, it may also show connection refused.
- **`/slow` request**: has a chance to return **done:15000** because it started before stopping and is under the 20s grace timeout. Actual results depend on when the signal arrived relative to request progress.
- **No proxy**: hitting `127.0.0.1` directly isolates app server errors from ingress 502/503s.

**Repeat:** run each variant with the same delay, grace timeout, and client. Record timestamp since SIGTERM, duration, HTTP status or network exception, server type, and OS. Do not run once and claim universal invariance across all versions.

## 9. Standalone Java 17 client to classify HTTP statuses and network errors

To take repeatable measurements and clearly print **HTTP_RESPONSE** vs **NETWORK_FAILURE**, create **NewRequestProbe.java** in the root directory. It is a standalone Java program using only JDK 17:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class NewRequestProbe {

    public static void main(String[] args)
            throws InterruptedException {

        URI uri = URI.create("http://127.0.0.1:8080/ping");

        for (int attempt = 1; attempt <= 8; attempt++) {

            // New client each time: reduces socket reuse within
            // the client itself, independent of Boot's Java SDK.
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            HttpRequest req = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(3))
                    .GET()
                    .build();

            try {
                HttpResponse<String> resp = client.send(
                        req, HttpResponse.BodyHandlers.ofString());

                System.out.println("attempt=" + attempt
                        + " HTTP_RESPONSE status="
                        + resp.statusCode());

            } catch (IOException ex) {
                System.out.println("attempt=" + attempt
                        + " NETWORK_FAILURE type="
                        + ex.getClass().getSimpleName());
            }

            Thread.sleep(400);
        }
    }
}
~~~

Compile:

~~~bash
javac NewRequestProbe.java
java NewRequestProbe
~~~

**Usage:** start the probe right after SIGTERM is sent, while `/slow` is still running. It makes 8 attempts, spaced by 400ms plus HTTP request duration. It helps observe a sequence of outcomes, though it cannot eliminate all lifecycle race conditions.

**Illustrative example, not guaranteed stdout** for Undertow:

~~~text
attempt=1 HTTP_RESPONSE status=503
attempt=2 HTTP_RESPONSE status=503
attempt=3 HTTP_RESPONSE status=503
attempt=4 NETWORK_FAILURE type=ConnectException
~~~

With Tomcat/Jetty, you will typically see **NETWORK_FAILURE** lines in the middle of the grace window; exception classes may vary (`ConnectException`, `SocketException`, `HttpTimeoutException`, other `IOException` subclasses). An HTTP 200 can also appear on the first attempt if the probe starts before shutdown takes effect.

**Do not treat a 200 result as proof that graceful shutdown failed** when the request was accepted before the server closed intake. Likewise, do not treat a network failure after Undertow exited as proof that Undertow does not support 503 during the grace period.

Java `HttpClient` can retain connection pools or asynchronous events; creating a new client per attempt in a short test reduces reuse inside the client, though you cannot claim every network layer/hop is guaranteed to open a fresh TCP connection. Combine direct curl measurements with network captures if greater precision is needed.

## 10. Client-side errors: classifying and retrying properly

An API-integrating client must distinguish **HTTP responses** from **transport failures**. For example:

| Result | Interpretation | How to retry? |
| --- | --- | --- |
| **HTTP 503** | Server/edge returned Service Unavailable; has status and maybe Retry-After | Can retry with backoff/jitter if business logic is safe. |
| **HTTP 502** | Gateway got an error from upstream or could not connect | Check gateway; apply bounded retry policy. |
| **HTTP 504** | Gateway did not get a response within deadline | Request may have run; retry must consider idempotency. |
| **Connection refused** | Could not establish TCP connection to target | Check endpoint readiness/network; retry against healthy instance if suitable. |
| **Connection reset / EOF** | Connection was cut during communication | For write requests, business outcome may be unknown. |
| **Connect/response timeout** | Did not finish within client deadline | Uncertain whether the server processed it or not. |
| **HTTP 200** | Received successful HTTP response | Do not retry needlessly. |

**Retry safety matters more than the exception type.** A payment POST may have committed before the response reset during shutdown. The client must not blindly issue another POST just because it saw ECONNRESET or 504. Design **Idempotency-Key**, transaction deduplication, queryable transaction status, and contract-bounded retries.

Principles:

- Only retry GET/HEAD or idempotent operations when business conditions allow; even GET can have side effects in poorly written systems, so understand the contract.
- For non-idempotent POSTs, use a request idempotency key and server-side dedup; do not retry blindly.
- Use **exponential backoff + jitter** and a total retry budget/deadline to avoid retry storms during cluster-wide rollouts.
- Respect **Retry-After** when a trusted HTTP response includes it; do not assume Undertow provides this header automatically.
- Avoid sending retries to a terminating pod; load balancers/service discovery must remove unready targets.
- Track response statuses and network exceptions separately. If you only count **http.server.requests{status="503"}**, you can miss network rejections that never produced an HTTP response.
- Bound connection pooling and handle stale keep-alive sockets per your HTTP client library.
- When detecting transient termination, prefer routing to a healthy instance over retrying the same target IP.

## 11. Kubernetes: readiness and drain must precede disconnection

Graceful shutdown **inside the JVM** is only part of a zero-downtime rollout. The system also needs load balancer/ingress coordination:

~~~text
Kubernetes decides to terminate Pod A
       |
       +--> Endpoint is marked terminating / traffic drain begins
       |
       +--> preStop hook (optional time for propagation)
       |
       +--> SIGTERM to application process
       |
       +--> Boot graceful shutdown (e.g. up to 20 s phase)
       |
       +--> existing requests finish if time permits
       |
       +--> container stops or Kubernetes sends SIGKILL at deadline
~~~

**Readiness** in Spring Boot reflects AvailabilityState, with **ACCEPTING_TRAFFIC** while running normally and **REFUSING_TRAFFIC** during graceful shutdown. However, once the HTTP connector starts rejecting new requests, **HTTP probes may no longer receive a JSON readiness response**. That outcome does not contradict the in-memory `REFUSING_TRAFFIC` state.

Part of a Deployment manifest **illustrating relevant fields**, not a complete Deployment YAML:

~~~yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 40
      containers:
        - name: app
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 2
            timeoutSeconds: 1
          lifecycle:
            preStop:
              exec:
                command:
                  - /bin/sh
                  - -c
                  - sleep 5
~~~

**Explanation:**

- Kubernetes grace **40s** must suffice for **preStop 5s + Spring Boot grace phase 20s + startup/shutdown overhead and network drain margin**. These are illustrative numbers, not fixed standards.
- `preStop` sleep can give load balancers/endpoint controllers time to update targets before SIGTERM is sent. It does not guarantee every proxy updates in exactly 5 seconds and does not immediately change the app's AvailabilityState.
- Kubernetes marks terminating endpoints; traffic routing/discovery behavior also depends on version, EndpointSlice/ingress implementation, and connection reuse.
- If the container entrypoint is a shell wrapper that does not forward SIGTERM to the JVM, graceful shutdown may not run properly. Run the Java process with proper signal forwarding/PID 1.
- If the app has requests longer than 20s, consider service-level timeouts/retries, adjust grace per SLO, or move long tasks to queues/jobs.
- When using a separate **management.server.port**, probes on the management port may stay UP while the app port fails; consider additional probes on the main port or combined endpoints when deployment requires it.
- **Do not misuse liveness** to mark unready during rollouts; liveness reports whether the process needs restarting, readiness reports whether it can take traffic. Confusing the two causes restart loops.

**Readiness does not eliminate races completely.** A gateway may have chosen an upstream before the target was removed or may reuse a keep-alive connection. Clients must still handle graceful rejections.

## 12. Reactor Netty must be tested with a separate reactive project

**Reactor Netty** is the standard embedded HTTP server of Spring WebFlux. In Spring Boot 3.3, it belongs to the group that **stops accepting new requests at the network layer** during graceful shutdown. Yet the Servlet demo in section 7 lacks a Reactor Netty profile because:

- **Reactor Netty is not a Servlet container**.
- **spring-boot-starter-webflux** brings Reactor Netty into the reactive server path.
- Adding the WebFlux dependency merely to use WebClient in an MVC project **does not prove the server switched to Netty**.
- Runtime comparisons must test the right stack, classpath, and application type.

Another minimal WebFlux demo can have the Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

With a separate pom and without **spring-boot-starter-web**, the default server is typically Reactor Netty. A reactive REST controller or RouterFunction and similar shutdown properties can serve `/ping` and `/slow`, but **do not copy Thread.sleep onto the Reactor Netty event loop**.

Example **reactive controller method snippet** inside a separate WebFlux `@RestController`:

~~~java
@GetMapping(value = "/slow", produces = "text/plain")
public Mono<String> slow() {
    return Mono.delay(Duration.ofSeconds(15))
            .map(ignored -> "done:15000");
}
~~~

It needs imports for **reactor.core.publisher.Mono**, **java.time.Duration**, **org.springframework.web.bind.annotation.GetMapping**, and a `@RestController` class; it is not a standalone program. To compare against the Servlet demo, write a runnable reactive project with matching environment/proxy/persistence, rather than mixing two stacks in one benchmark and blaming differences solely on the connector.

## 13. Long-lived requests: SSE, WebSocket, streaming, and HTTP/2

Graceful shutdown is straightforward to observe with short requests. However, **long-lived connections** complicate things:

- **SSE**: HTTP responses can stay open for minutes/hours. The grace timeout may expire before the stream ends.
- **WebSocket**: after handshake, it is a long-lived bidirectional connection; the protocol has close frames and requires reconnect/resubscribe. Do not treat WebSocket like a finite-body GET.
- **HTTP streaming/long polling**: response remains unfinished, affecting the drain budget.
- **HTTP/2**: multiple streams over one connection; admitting new streams and closing the connection follow separate semantics.
- **Connection pools** at clients/proxies: pre-existing sockets may persist when graceful shutdown starts.

**Strategy:** cap session/stream lifetimes, notify clients of server draining when appropriate, close cleanly per protocol, reconnect with backoff/jitter, and restore subscriptions/state. If zero message loss is required, use event IDs, offsets/cursors, acks, and a durable broker. Graceful shutdown does not provide replay or exact-once delivery on its own.

**Do not set the grace timeout to infinity** to “keep WebSockets alive forever”. If the orchestrator has a deadline, the pod will eventually be killed anyway; design for reconnects instead.

## 14. Observing accurately at each layer

If you only look at the Spring Boot app's HTTP **503 count**, a gracefully shutting Tomcat server may reject at the network layer and **emit zero 503 responses**. Thus a dashboard tracking only server-side HTTP 5xx could report “zero errors” while upstream clients continuously hit connection errors.

Measure across layers together:

| Location | Signal | Helps distinguish |
| --- | --- | --- |
| Spring Boot process | Lifecycle shutdown begin/end, graceful shutdown logs, active requests | Did shutdown actually trigger? |
| Embedded connector | Connection accept/close, threads, active connections, HTTP status | At which layer was new work rejected? |
| Client HTTP library | ConnectException/SocketException/EOF/timeout, HTTP status, retries | Did it receive an HTTP response? |
| Ingress / API Gateway | 502/503/504 by upstream, healthy endpoint count, target draining | Did the edge generate the status or pass it through from Undertow? |
| Kubernetes | Pod deletion timestamp, readiness, terminating endpoints, SIGTERM/SIGKILL, restart reason | Was grace enough, or was it killed early? |
| Distributed traces | In-flight span durations, outbound spans and exit status | Which requests completed in time? |
| Load balancer | Connection reuse, queuing, failover, target selection | Why did clients still hit a terminating pod? |

**Micrometer Actuator** can emit **http.server.requests** for HTTP requests processed through the observation pipeline and **http.client.requests** for compatible clients. However, network-level rejections before the handler usually do not generate server HTTP request metrics. You must inspect **client-side errors/edge metrics**.

**Logging a 503 status on Undertow does not by itself prove shutdown was the root cause.** Cross-correlate with **timestamp, pod, lifecycle event, request ID/traceId, and upstream status origin**. Do not log Authorization headers/Cookies/bodies while investigating.

Use low-cardinality metric tags: service, method, route template, status/outcome, dependency. Do not put raw URIs/session IDs/request IDs into metric labels.

## 15. Differences at application, container, and gateway

Layers involved:

~~~text
End user
   |
   | request / response
   v
CDN / WAF / Ingress / Load balancer
   |
   | fresh / reused upstream connection
   v
Tomcat / Jetty / Undertow / Reactor Netty
   |
   | when accepted
   v
Spring MVC or WebFlux handler
   |
   v
Business transaction / DB / downstream
~~~

**When Tomcat closes intake**, the application controller never gets a chance to return 503 for a request that hasn't entered the framework. **When Undertow returns 503 at the connector during graceful shutdown**, normal controllers may not be invoked. Do not add `@ControllerAdvice` expecting it to catch every network refusal and produce a JSON 503.

If a gateway wants to normalize behavior, it can convert upstream connection failures into HTTP 502/503 and retry against a healthy pod. When doing so:

1. Distinguish safe vs unsafe retries.
2. Do not retry infinitely or amplify load storms.
3. Do not conflate upstream-originated statuses with proxy-generated statuses in metrics.
4. Do not assume raw HTTP 503 always carries a domain body/header.
5. Record enough correlation/traces to match client/gateway/app without logging secrets.
6. Check TLS/HTTP version/keep-alive semantics and the proxy's own connection draining.

**An HTTP 503 from Undertow might never reach the end user.** A gateway may swallow or rewrite the status per policy, or pick another healthy replica so the user only sees 200.

## 16. Misconceptions to avoid

**Misconception 1: "If the server is graceful, new requests always return 503."**  
False. Per Boot 3.3, Tomcat, Jetty, and Reactor Netty reject at the network layer; Undertow may return 503 during the grace period.

**Misconception 2: "Connection refused definitely means the server crashed abnormally."**  
False. A server intentionally configured to stop accepting new connections during graceful shutdown can produce the exact same symptom on the client.

**Misconception 3: "HTTP 503 proves Undertow is running."**  
False. Proxies, app overload, circuit breakers, or many other systems can also return 503. Check the origin.

**Misconception 4: "If Undertow returns 503, every call after SIGTERM returns 503."**  
False. Once the connector/process closes, clients hit network failures; timing races also exist around transitions.

**Misconception 5: "server.shutdown=graceful guarantees every request completes."**  
False. Timeouts, SIGKILL, JVM crashes, long-lived connections, or external resource failures can still sever requests.

**Misconception 6: "spring.lifecycle.timeout-per-shutdown-phase=20s is a dedicated deadline per request."**  
False. It is a timeout per shutdown phase, not the maximum duration of each request.

**Misconception 7: "With readiness probe enabled, zero new requests arrive during shutdown."**  
False. Endpoint propagation/connection reuse and timing races can still send requests to a draining pod.

**Misconception 8: "If a POST hits a reset, just retry it."**  
False. The server may have committed the transaction before the response was lost. Use idempotency keys and know the outcome before retrying.

**Misconception 9: "Using WebClient means the embedded server is Netty."**  
False. Spring MVC still normally runs Tomcat unless you change the web application type/server classpath.

**Misconception 10: "Enabling Actuator readiness and calling it after SIGTERM must always return REFUSING_TRAFFIC JSON."**  
False. The HTTP connector may have already stopped accepting requests; internal readiness state does not guarantee HTTP probes remain reachable.

## 17. Troubleshooting by symptom

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| Tomcat returns connection refused instead of HTTP 503 | Network-level shutdown rejection is normal behavior | Measure fresh connections directly during grace window, read logs. |
| Undertow shows no 503 | Measured too late, no in-flight request holding grace open, gateway masking it, or server isn't Undertow | Check server startup log, T2–T4 timing, direct localhost curl. |
| Jetty test returns HTTP 200 again | Request arrived before shutdown took effect or reused an old socket | Record timestamps, use a new client, check shutdown start logs. |
| 502 at Nginx while Tomcat is stopping | Nginx failed to connect upstream | Compare direct curl vs proxy, check edge access/error logs. |
| HTTP 503 at gateway yet server is Tomcat | Gateway returned 503 / no backends | Check status origin, healthy targets, and gateway policy. |
| In-flight /slow did not complete | Phase timeout, SIGKILL, signal sent too early, interrupted sleep | Check slow.begin/slow.end, signals, clocks, grace budgets. |
| Graceful did not trigger | server.shutdown=immediate, kill -9, wrong JVM PID, forced IDE Stop | Check config, process signals, lifecycle logs. |
| CORS/authorization yields 403 while measuring | Request rejected by security/filters before shutdown | Use public local `/ping` test, avoid mixing auth tests. |
| Readiness probe returns no response after SIGTERM | HTTP connector stopped accepting | Inspect readiness state/lifecycle logs before signal or orchestrator metrics. |
| Reactor Netty library present yet Tomcat starts | WebClient dependency; MVC still selects Servlet | Inspect actual web server factory/startup logs. |
| Requests cut off despite 20s timeout | Orchestrator termination grace is shorter or user code errored | Check preStop + Boot grace + overhead and pod events. |
| No HTTP 503 in app metrics despite client errors | Rejected before the HTTP handler | Inspect client connect errors and edge metrics. |
| POST sent twice during rollout | Unbounded retry on reset/503 | Add idempotency key and dedup. |
| WebSocket dropped across pod termination | Connection longer than grace budget | Design close/reconnect/resubscribe and durable replay. |
| Shutdown phase took longer than 20s | Multiple lifecycle phases/other cleanup | Measure each phase; do not treat timeout-per-phase as total process timeout. |

## 18. Hands-on exercises

**Exercise 1 — Direct Tomcat:** build the Tomcat profile, call 15s `/slow`, send SIGTERM after `slow.begin` logs, then use a new curl process to call `/ping`. Classify results into HTTP status vs network failure; do not expect one specific error message.

**Exercise 2 — Undertow:** repeat with the Undertow Maven profile. Use the same 20s grace, 15s in-flight, and probe within 2 seconds after SIGTERM. Observe possible HTTP 503 during the grace period, followed by network refusal after the server stops.

**Exercise 3 — Jetty:** repeat with Jetty and compare with Tomcat: both do network-level rejection, yet exact exceptions/timing may differ.

**Exercise 4 — Grace budget:** test `/slow?delayMs=30000` with 20s grace. Measure the result and explain why the in-flight request is not guaranteed to finish; do not use hard kills to simulate graceful shutdown.

**Exercise 5 — Client pool:** use a Java HTTP client keeping a connection alive and send a follow-up request on the old socket, comparing against a fresh `HttpClient` each time. Document HTTP version and pooling for each case.

**Exercise 6 — Proxy:** put the app behind a local test Nginx/Ingress, send SIGTERM, and compare direct-vs-edge results. If the edge returns 502/503, determine whether the edge generated it or passed it through from Undertow.

**Exercise 7 — Kubernetes:** set 40s termination grace, 5s preStop, and 20s Boot grace; perform a rolling update. Measure pod events, failed request rate, readiness, and logs; if 5xx remains, check propagation and connection reuse.

**Exercise 8 — Retry safety:** write a POST client with `Idempotency-Key`, simulate a reset after commit, and verify retries do not duplicate the transaction. Do not treat a curl GET probe as sufficient to verify payment safety.

## 19. Implementation and review checklist

- [ ] Documented exact **Spring Boot version** and **embedded server implementation/version**.
- [ ] For Boot 3.3, explicitly enabled **server.shutdown=graceful** if drain is needed.
- [ ] Set **spring.lifecycle.timeout-per-shutdown-phase** per latency/SLO and request workloads.
- [ ] Ensured **SIGTERM reaches the right JVM**; never use SIGKILL expecting graceful behavior.
- [ ] Verified Tomcat/Jetty/Reactor Netty differ from Undertow regarding **network-level refusal vs HTTP 503**.
- [ ] Avoided building alert/retry logic solely around 503; monitor network/client errors too.
- [ ] Tested both **fresh TCP connections** and **requests over keep-alive connections**.
- [ ] Tested directly against the pod and through the ingress to separate the origin of 502/503/504.
- [ ] Configured readiness, endpoint drain, and sufficiently large Kubernetes `terminationGracePeriodSeconds`.
- [ ] Accounted for preStop, lifecycle phase timeouts, and cleanup overhead.
- [ ] Tracked HTTP statuses and network error metrics on the client/proxy side.
- [ ] Avoided logging credentials/cookies/bodies when diagnosing shutdown.
- [ ] For POST/PUT/DELETE, defined clear idempotency/retry semantics.
- [ ] For WebSocket/SSE, implemented reconnect/close/resubscribe and replay where needed.
- [ ] Tested SIGTERM on the packaged JAR, not just MockMvc unit tests.
- [ ] Observed in-flight request completion and server graceful shutdown logs.
- [ ] Repeated tests when switching Tomcat/Jetty/Undertow/Reactor Netty or upgrading Spring Boot.
- [ ] Avoided using Boot 4.x default behavior to describe a Boot 3.3 application.

## 20. Self-check questions

**1. Why does Tomcat not necessarily return HTTP 503 during graceful shutdown?**  
Because Boot 3.3 describes it as stopping acceptance of new requests at the network layer; many new requests never reach the HTTP handler to produce a response.

**2. Which server belongs to the group that can return HTTP 503 immediately during the grace period?**  
Undertow on Spring Boot 3.3.

**3. Which three servers belong to the network-level refusal group?**  
Tomcat, Jetty, Reactor Netty.

**4. Is Reactor Netty an embedded Servlet container?**  
No. It is typically the WebFlux reactive server; Tomcat/Jetty/Undertow are the common Servlet servers.

**5. What does server.shutdown=graceful mean?**  
It gives the server a phase to stop admitting new work while letting in-flight requests have a chance to finish when the context stops.

**6. Does a 20s timeout per shutdown phase guarantee every request finishes within 20s?**  
No. It is a grace budget for the lifecycle phase, not a per-request SLA.

**7. Why can Undertow also produce ConnectException after SIGTERM?**  
Because once the server has finished shutting down, there is no listener left to return 503.

**8. If a gateway returns HTTP 502 while Tomcat is stopping, where does the error come from?**  
Usually the gateway failed to get an HTTP response from upstream, though logs must be checked to verify.

**9. Can you infer the server type from an HTTP 503 alone?**  
No. A 503 can come from Undertow, a load balancer, the application, or another component.

**10. Why must comparisons test fresh connections and keep-alive separately?**  
Because sockets open before shutdown may behave differently from new connections, especially with HTTP/2 and connection pools.

**11. Why not test with kill -9?**  
SIGKILL bypasses shutdown hooks/cleanup and therefore does not simulate graceful shutdown.

**12. With Kubernetes preStop 5s and Spring grace 20s, is setting termination grace to 20s enough?**  
Not reliably, because it leaves no margin for preStop, request draining, and shutdown overhead.

**13. If an HTTP request loses its response after a reset, is it guaranteed not to have been processed?**  
No. Business side effects may have committed before the response was lost.

**14. When Actuator readiness stops returning JSON after SIGTERM, does that mean Boot failed to emit REFUSING_TRAFFIC?**  
Not necessarily. The HTTP connector may have already stopped accepting new requests.

**15. Can you use WebClient in MVC and conclude the app runs a Reactor Netty server?**  
No. You must inspect the actual embedded server startup/factory.

## 21. Official documentation and operational references

- **Spring Boot 3.3 – Graceful Shutdown:** https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html — differing rejection mechanisms among Tomcat/Jetty/Reactor Netty and Undertow, server.shutdown, timeout-per-shutdown-phase, IDE SIGTERM.
- **Spring Boot 3.3 – Embedded Web Servers:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html — switching embedded servers and starter dependencies for Servlet/reactive.
- **Spring Boot 3.3 – Servlet Web Applications:** https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html — Tomcat/Jetty/Undertow MVC, ServletWebServerFactory, and runtime.
- **Spring Boot 3.3 – Actuator Endpoints / Kubernetes Probes:** https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html — readiness/liveness and lifecycle during shutdown.
- **Spring Boot 3.3 – Reactor Netty/WebFlux:** https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html — reactive runtime and connector.
- **Spring Framework – SmartLifecycle:** https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html — phases/ordering and lifecycle stop callbacks.
- **Kubernetes – Pod Lifecycle:** https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/ — SIGTERM, preStop, grace periods, terminating endpoints.
- **Kubernetes – Container Lifecycle Hooks:** https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/ — preStop and shutdown orchestration.
- **RFC 9110 – HTTP Semantics (503):** https://www.rfc-editor.org/rfc/rfc9110.html — Service Unavailable and Retry-After semantics.
- **RFC 9112 – HTTP/1.1:** https://www.rfc-editor.org/rfc/rfc9112.html — connection management, persistent connections.
