# Enabling server.shutdown=graceful in Spring Boot 3.3

## 1. What Problem Does Graceful Shutdown Solve?

When a Spring Boot web application is deploying a new version, scaling down, undergoing a rolling update, or asked by an administrator to stop, HTTP requests may still be in flight. If the server stops abruptly, a request can be cut off mid-calculation, mid-database call, mid-write, or while sending the response. Clients often cannot tell whether the transaction completed, so retries can cause further business errors.

**Graceful shutdown** is a controlled way to stop the embedded web server: the server **stops accepting new requests** and **gives already accepted requests a window to complete**. After that wait window, the ApplicationContext must still proceed to close remaining components.

With **Spring Boot 3.3**, enable it explicitly in `application.properties`:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Version accuracy is critical: **`server.shutdown` defaults to `immediate` in Spring Boot 3.3**. Do not mistakenly apply information from Spring Boot 3.4 or later, where graceful shutdown is enabled by default on supported embedded servers. Spring Boot 3.3 documentation instructs users to **explicitly set `server.shutdown=graceful`**.

Spring Boot 3.3 supports this feature across four embedded web servers: **Tomcat**, **Jetty**, **Undertow**, and **Reactor Netty**, for both servlet and reactive models as applicable.

Graceful shutdown does **not** mean every request is guaranteed to succeed, every long-lived connection closes neatly as the app wishes, or every bean stops within the same time window. It is one part of **closing the ApplicationContext**, requiring coordination with readiness, load balancers, client timeouts, and external resources.

## 2. Distinguishing immediate and graceful

| Aspect | immediate | graceful |
| --- | --- | --- |
| Default in Spring Boot 3.3 | **Yes** | No; must be enabled explicitly |
| Goal | Close the web server during shutdown without providing a matching drain phase | Prevent new requests and wait for accepted requests to finish within bounds |
| In-flight HTTP requests | At risk of interruption | Have a chance to complete |
| New requests arriving during shutdown | No normal serving path remains | Rejected with behavior depending on the embedded server |
| Related timeout | Other lifecycle mechanisms still exist | Shutdown phase has a wait window for graceful web server stop |
| Guarantees zero lost requests | No | **Also not absolute** |
| Safely stops Kafka consumers/external tasks automatically | No | No |
| Replaces Kubernetes readiness automatically | No | No |

**Do not merely increase the timeout.** For example:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=90s
~~~

does not enable graceful mode if **`server.shutdown`** remains **`immediate`** in Boot 3.3.

Conversely, enabling graceful with a very short deadline can leave long requests without enough time to finish.

### Timeline Illustration

~~~text
T0    Request A starts processing (expected to take 8 seconds)
T2    JVM receives SIGTERM / context begins closing
      |
      +--> server begins stopping new requests
      +--> request A is allowed to continue within the wait budget
      |
T8    Request A returns a successful response unless another error occurs
      |
      +--> remaining SmartLifecycle phases continue stopping
      +--> bean destruction, resources, and process exit
~~~

These milestones are **hypothetical examples**, not durations guaranteed by Spring Boot. Client timeouts, proxies, databases, application errors, or forced JVM kills can still interrupt execution.

## 3. Two Key Properties and Boot 3.3 Defaults

### server.shutdown

~~~properties
server.shutdown=graceful
~~~

Supported Spring Boot values:

- **immediate**: default mode in Boot 3.3.
- **graceful**: enables graceful shutdown for the embedded web server.

Spring Boot binds this string to the shutdown behavior option of the Boot-managed server. This is a **bootstrap configuration**, so editing the file while the JVM is running does not immediately switch the live server's shutdown mode; proper reconfiguration or a restart is required.

### spring.lifecycle.timeout-per-shutdown-phase

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

This property is a **Duration**, specifying the **maximum wait budget for each SmartLifecycle phase group**. Per Spring Boot 3.3 Common Application Properties, the default value is **30s**. This lesson uses 20s for easier testing and does **not** claim 20s is the default.

Values can use suffixes such as **ms**, **s**, **m**:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=45000ms
~~~

45,000 milliseconds equals 45 seconds. When configuring Kubernetes, balance the total shutdown budget rather than treating this single figure as the maximum total JVM lifetime.

### spring.main.register-shutdown-hook

Spring Boot 3.3 defaults to:

~~~properties
spring.main.register-shutdown-hook=true
~~~

Normally you do not need to declare this since the default is true. Its role is registering a shutdown hook to close the ApplicationContext when the JVM exits via normal shutdown. If this setting is disabled, or signals never reach the JVM, setting **`server.shutdown=graceful`** alone is not enough to trigger the shutdown path you expect.

### Properties or YAML

File **src/main/resources/application.properties**:

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Equivalent **src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Pick one clear format for demos. In production, environment variables, command-line arguments, or profiles can override file values. To enable via command line:

~~~bash
java -jar target/graceful-demo-0.0.1-SNAPSHOT.jar --server.shutdown=graceful --spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

The JAR name in the example matches the POM in section 6; if artifactId/version differ, adjust the path accordingly.

## 4. Graceful Shutdown Mechanism Inside ApplicationContext

Spring Boot performs graceful shutdown as part of **`ApplicationContext.close()`**. It sits in an **early stopping phase of `SmartLifecycle` beans**. The goal is to prevent new requests from pouring in while their dependencies are about to be closed.

~~~text
Process receives SIGTERM or code explicitly closes context
       |
       v
JVM shutdown hook / ApplicationContext.close()
       |
       v
DefaultLifecycleProcessor coordinates stop by phase
       |
       +--> Graceful web server shutdown
       |      - Stops accepting new requests per server mechanism
       |      - Waits for accepted requests to complete
       |      - Continues shutdown path once phase timeout expires
       |
       +--> Other SmartLifecycle groups
       |      - Consumers, schedulers, background workers...
       |
       v
Bean destruction callbacks
  @PreDestroy, DisposableBean.destroy(), custom close()
       |
       v
Close resources and JVM exit
~~~

This diagram is a conceptual model. Exact ordering among infrastructure beans also depends on phases, dependencies, and the web server type. In Spring, lifecycle startup normally runs in ascending phase order and shutdown in descending phase order. **Do not assign an arbitrary phase** to a resource used by HTTP requests without understanding the web server's shutdown order.

### Per-Phase Timeout Is Not a Total JVM Timeout

Example with three distinct groups:

~~~text
HTTP graceful phase:        waits up to 20 seconds
Background workers phase:   waits up to 20 seconds
Infrastructure phase:       waits up to 20 seconds
Bean destroy callbacks:     own duration depending on implementation
~~~

If each group uses its full budget, total shutdown can **exceed 20 seconds**, even before counting other callbacks. Conversely, if all work finishes quickly, Spring does not wait out the full timeout.

For a group of 5 `SmartLifecycle` beans **sharing the same phase**, the 20s timeout is the wait budget for **the entire phase group**, not 5 times 20s. Timeout expiration also does not automatically interrupt every thread or close external resources.

### Stop HTTP Before Destroying Resources

Suppose a request uses an HTTP client or database connection pool. If a dependent bean closes too early, the request can fail even while the server tries to drain. Ensure:

- The request-accepting layer starts stopping first.
- Resources needed by already accepted requests stay active long enough.
- Tasks have reasonable timeouts and cancellation.
- Cleanup does not block indefinitely.
- Asynchronous `SmartLifecycle.stop(Runnable)` implementations invoke the callback **after genuinely stopping**.

Graceful web shutdown cannot rescue a request that fails because the application destroyed a dependency prematurely.

## 5. Differences Among Embedded Web Servers

According to the **Spring Boot 3.3 Graceful Shutdown Reference**:

| Server | How new requests are prevented | What to check when testing |
| --- | --- | --- |
| **Tomcat** | Stops accepting at the **network layer** | Clients may see connection refused/reset |
| **Jetty** | Stops accepting at the **network layer** | Network behavior varies with timing and connections |
| **Reactor Netty** | Stops accepting at the **network layer** | Check reactive requests and connection reuse |
| **Undertow** | May keep accepting connections while returning **HTTP 503 Service Unavailable** for new requests | 503 is the characteristic documented behavior |

**Do not assume every server returns 503.** With Tomcat, clients may receive no HTTP response at all because new connections are not accepted. With persistent connections, HTTP/2, or reverse proxies, request handling also depends on current transport state.

The exact moment a request is considered accepted matters greatly. A request sent by a client right before SIGTERM but not yet accepted by the server may still be rejected. Conversely, a request sent right after SIGTERM before the listener finishes stopping accept may race and be accepted. Do not use an unsynchronized network test to claim a framework bug.

### Streaming and Long-Lived Connections

SSE, WebSockets, long polling, streaming downloads, and long-lived HTTP/2 connections require separate testing. Graceful shutdown can apply rules to stop accepting new requests, but does not guarantee every connection finishes within the deadline. When connection lifetime exceeds the shutdown budget, protocol-specific close signaling, resumability, or client reconnects are required.

## 6. Runnable Java 17+ Maven Project to Verify

This section provides a **complete POM**, **complete Java class**, and **`application.properties`** to test with Spring Boot **3.3.13**, a release in the 3.3 branch. The project intentionally uses default **Spring MVC + embedded Tomcat** for clear observation.

### 6.1. File Structure

~~~text
graceful-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/demo/GracefulShutdownDemoApplication.java
        └── resources/application.properties
~~~

If created via Spring Initializr, the project also includes Maven Wrapper **mvnw** and **mvnw.cmd**. The example below also runs with Maven installed locally.

### 6.2. Complete pom.xml

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

**Explanation:** the parent manages libraries matching Boot 3.3; `starter-web` brings Spring MVC and Tomcat; the Maven plugin builds an executable JAR. Actuator is not needed for basic HTTP tests. The POM includes versions and Java configuration ready to build in a Maven/JDK 17+ environment with access to dependencies.

### 6.3. application.properties

Create **src/main/resources/application.properties**:

~~~properties
server.port=8080

# Spring Boot 3.3 defaults to immediate, so choose graceful explicitly:
server.shutdown=graceful

# Wait at most 20 seconds per lifecycle phase group:
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

If port 8080 is already occupied by another program, change `server.port` and update the curl URLs to match. Avoid adding multiple Spring profiles unnecessarily so the test stays repeatable.

### 6.4. Complete Java File

Create **src/main/java/com/example/demo/GracefulShutdownDemoApplication.java**:

~~~java
package com.example.demo;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class GracefulShutdownDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                GracefulShutdownDemoApplication.class, args);
    }

    @RestController
    static class WorkController {

        private final AtomicInteger inFlight = new AtomicInteger();

        @GetMapping("/ping")
        public String ping() {
            return "pong";
        }

        @GetMapping("/work")
        public ResponseEntity<String> work(
                @RequestParam(defaultValue = "8") int seconds) {

            if (seconds < 1 || seconds > 30) {
                return ResponseEntity.badRequest()
                        .body("seconds must be between 1 and 30");
            }

            int count = inFlight.incrementAndGet();
            System.out.println("WORK_BEGIN seconds=" + seconds
                    + " active=" + count);

            try {
                TimeUnit.SECONDS.sleep(seconds);
                return ResponseEntity.ok("completed=" + seconds);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return ResponseEntity.status(
                        HttpStatus.SERVICE_UNAVAILABLE)
                        .body("interrupted");
            } finally {
                int remaining = inFlight.decrementAndGet();
                System.out.println("WORK_END seconds=" + seconds
                        + " active=" + remaining);
            }
        }
    }
}
~~~

This is a **complete Java file** matching the Spring Boot project with the POM above.

- Public class, path, and package match.
- WorkController is a nested static class annotated with **`@RestController`**, discovered by component scan.
- `GET /ping` checks that the web server is up.
- `GET /work` accepts query parameter **`seconds`**, bounded from 1 to 30.
- **`AtomicInteger`** lets us log the count of in-flight requests.
- **`TimeUnit.SECONDS.sleep`** only simulates waiting; it is not a business database-processing pattern.
- **`try/finally`** decrements the counter and prints `WORK_END` even on interruption.
- The `InterruptedException` branch returning 503 is **decided by the controller itself**, not representing the 503 Undertow may return during shutdown.
- It uses no Spring APIs absent from Boot 3.3 and depends on no undeclared modules.

### 6.5. Build the JAR

~~~bash
java -version
mvn -version
mvn clean package
~~~

If using Maven Wrapper:

~~~bash
# Linux/macOS:
./mvnw clean package

# Windows PowerShell or cmd:
# .\mvnw.cmd clean package
~~~

Based on `artifactId`/`version` in the POM, the generated file is:

~~~text
target/graceful-demo-0.0.1-SNAPSHOT.jar
~~~

If using another project, use the exact executable JAR name built rather than guessing from documentation.

### 6.6. Run the Application and Test a Normal Request

In the first Linux/macOS terminal (**Terminal A**):

~~~bash
java -jar target/graceful-demo-0.0.1-SNAPSHOT.jar &
APP_PID=$!
echo "Java PID=$APP_PID"
~~~

Wait for Spring Boot to report started. Save **APP_PID** in Terminal A so SIGTERM targets the **real JVM**, not Maven's wrapper PID from `mvn spring-boot:run`.

In **Terminal B**:

~~~bash
curl -i http://localhost:8080/ping
~~~

Expected status/body while the server runs normally:

~~~text
HTTP/1.1 200
...
pong
~~~

The **`...`** in the sample output indicates omitted headers, not literal output. Actual `Content-Type` and headers depend on Tomcat/Spring MVC and the client.

### 6.7. Start a Long Request Then Send SIGTERM

In **Terminal B**:

~~~bash
curl -i "http://localhost:8080/work?seconds=8"
~~~

`curl` will wait for the response. In **Terminal A**, watch the application log:

~~~text
WORK_BEGIN seconds=8 active=1
~~~

Right after seeing this line, send in **Terminal A**:

~~~bash
kill -TERM "$APP_PID"
~~~

In a successful run where the request was accepted and had enough of the 20s window, expected application-printed lines are:

~~~text
WORK_BEGIN seconds=8 active=1
WORK_END seconds=8 active=0
~~~

And the main output from `curl` can look like:

~~~text
HTTP/1.1 200
...
completed=8
~~~

Maven, Spring Boot, and Tomcat emit additional logs, and headers may vary. Do not treat the output block above as a full console snapshot. A **200** result is expected for a request already started and processed within the deadline, not a promise that every SIGTERM always yields 200.

**The test must verify three things:** the request actually started before the signal; the JVM received SIGTERM rather than a forced kill; the client received a complete response within the shutdown budget.

### 6.8. New Requests While the Server Is Stopping

If you send:

~~~bash
curl -i --max-time 3 http://localhost:8080/ping
~~~

after graceful shutdown has started, embedded Tomcat normally stops accepting at the network layer. Clients may hit connection refused, connection reset, or other errors depending on timing and keep-alive.

**Do not assert Tomcat must return HTTP 503.** For Undertow, Boot 3.3 documentation notes new requests may be accepted and receive **503 Service Unavailable**. If `/ping` happens to succeed right in the race window around SIGTERM, that alone does not prove graceful mode is disabled.

### 6.9. Testing Insufficient Timeout

Change the properties:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=3s
~~~

Run again, send **`/work?seconds=8`**, and send SIGTERM once the request begins.

Observable behaviors:

- Spring runs out of budget waiting for the web server to finish the request.
- Shutdown proceeds to subsequent steps.
- The client may receive a connection error or incomplete response.
- Request-processing threads may keep running longer depending on the server and task type.
- The JVM may take more than 3 seconds to exit due to other lifecycle phases or cleanup.

**Do not assume a fixed stdout or status code for an intentionally exceeded timeout.** Per-phase timeout expiration does not mean the JVM immediately interrupts every thread at 3 seconds.

### 6.10. Running on Windows and IDEs

Windows does not provide Unix SIGTERM in PowerShell terminals the same way. You can test inside a Linux container or WSL, or write an integration test explicitly calling **`ConfigurableApplicationContext.close()`** in a lifecycle-controlled program.

The **`taskkill /F`** command is a forced termination, not an equivalent to graceful SIGTERM. An IDE's Stop button may also kill the process or fail to send a proper signal. Spring Boot 3.3 Reference warns that graceful shutdown in an IDE may not work properly if the IDE does not send an appropriate SIGTERM.

## 7. Why Does Spring Boot Need the Right Stop Signal?

On Linux, the normal flow:

~~~text
Docker/Kubernetes/systemd sends SIGTERM
             |
             v
JVM starts orderly shutdown
             |
             v
Spring Boot shutdown hook closes ApplicationContext
             |
             v
Graceful web server + bean lifecycles stop
~~~

**SIGTERM** requests a polite stop. **SIGKILL** forces the process to terminate immediately without letting the JVM run shutdown hooks. Therefore:

~~~bash
kill -TERM "$APP_PID"
~~~

is a valid graceful test, whereas:

~~~bash
kill -KILL "$APP_PID"
~~~

is a forced termination test. Under SIGKILL, `@PreDestroy`, `SmartLifecycle.stop`, request draining, and message flushing cannot be guaranteed.

### Docker ENTRYPOINT and PID

Example Dockerfile given an executable JAR:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/graceful-demo-0.0.1-SNAPSHOT.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This is an illustrative Dockerfile for an image with a compatible JDK/JRE and JAR. **Exec form** lets the JVM receive signals directly as the main process, avoiding a shell wrapper that fails to forward SIGTERM.

If an entrypoint script runs **`java -jar`** without **`exec`** or without forwarding signals, the JVM may never receive the stop request properly. In containers, inspect the actual PID/process tree rather than only checking properties in `application.properties`.

Example Docker stop:

~~~bash
docker stop --time 50 graceful-demo-container
~~~

The container name **`graceful-demo-container`** is just an example. Docker sends a stop signal and may force-kill when time runs out. **50 seconds is Docker's budget**, not 50 seconds dedicated solely to Spring's graceful phase.

## 8. Kubernetes: terminationGracePeriodSeconds and Readiness

A container application in Kubernetes usually configures **`terminationGracePeriodSeconds`**. It is the **total time for the Pod to terminate gracefully**, covering `preStop` (if any), signaling the process, and the wait before forced kill. It is **not synonymous with** `spring.lifecycle.timeout-per-shutdown-phase`.

PodSpec fragment:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: app
      image: registry.example.com/graceful-demo:0.0.1
      ports:
        - containerPort: 8080
~~~

The image is illustrative; a real image must be built and pushed. This is a fragment inside a Pod template, not a complete Deployment manifest.

During a rolling update, removing a Pod from routing has latency:

1. Pod is marked terminating.
2. Kubernetes/EndpointSlice/Service reflects that the Pod is no longer ready for new traffic per platform mechanics.
3. Ingress and external load balancers must receive the update.
4. `preStop` hook may run, then SIGTERM arrives at the container.
5. Spring starts graceful web shutdown.
6. In-flight requests get a chance to finish.
7. The JVM closes remaining resources within the grace budget.

A load balancer or proxy may still hold older connections briefly. **Readiness and graceful shutdown complement each other**: readiness helps route traffic away, while graceful handles in-flight connections/requests on the stopping instance itself.

### Calculating the Total Shutdown Budget

Suppose:

~~~text
Web graceful phase:  up to 20s
Worker drain phase:  up to 15s
Resource cleanup:    5s
preStop hook:        5s
Overhead:            add a safety margin
~~~

In the worst case, you need **more than 45 seconds**. Choosing `terminationGracePeriodSeconds=20` can get the Pod killed before cleanup finishes, even though the web graceful phase is configured for 20s. Numbers here are illustrative; measure in the real environment.

**Do not add unbounded `preStop` sleeps or long unjustified delays.** `preStop` also consumes the grace period; if Kubernetes already handles endpoint termination/draining properly, sleeping may not help much.

### Optional Readiness Probe via Actuator

The demo in section 6 uses only `starter-web`, so it **does not automatically include** `/actuator/health/readiness`. If you want Kubernetes to call that probe, add the dependency to the POM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

This is a **fragment inside `dependencies`**, not another complete POM.

When you need probes enabled even outside Kubernetes:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
~~~

Then you can call the health groups:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

`readinessProbe` fragment for the container:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
~~~

With a separate management port, consider:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

to also expose **`/livez`** and **`/readyz`** on the main HTTP port. This lets probes test the HTTP path closer to real traffic instead of only checking a management connector that is still healthy.

**Note:** once the web server stops accepting connections, readiness endpoints may become unreachable; observing HTTP 503 is not required to conclude the web server has begun shutting down.

## 9. Graceful Shutdown and Non-HTTP Workloads

**`server.shutdown=graceful` does not automatically stop all background software cleanly.** Some examples:

| Component | Is HTTP graceful sufficient? | What to add |
| --- | --- | --- |
| Accepted REST requests | Supported within server/deadline limits | Client timeouts, error handling |
| Kafka/RabbitMQ consumers | No | Stop new intake, ack/checkpoint, retries |
| Long `@Scheduled` tasks | No | Scheduler lifecycle, cancellation |
| Background `CompletableFuture` | No | Await/timeout, executor shutdown |
| Database transactions | Have a chance to complete if request continues | Transaction timeout/rollback |
| Outbound HTTP clients | Not all managed automatically | Connection pool close, connect/read timeouts |
| SSE/WebSockets | Depends on protocol and web server | Draining/reconnect contract |
| Distributed locks/leases | No | Release/expiry and idempotency |
| Shared caches | No | Cache flush/invalidation per use case |
| JVM hit by SIGKILL | No | Durable recovery |

If a request is still running while a required resource closes, the request can fail even while the web server tries to wait. Design `quiesce → drain → release` ordering in `SmartLifecycle` components and place bounded timeouts on network calls.

## 10. Data Safety: Graceful Does Not Replace Idempotency

Consider **`POST /payments`**:

~~~text
Client sends payment
    |
Server writes DB and commits successfully
    |
SIGTERM / network drops response before client receives it
    |
Client times out and retries
    |
Risk of duplicate payment write if not idempotent
~~~

Graceful reduces the frequency of normal-shutdown disruptions, yet cannot guarantee the network, client, or JVM never fails abruptly. For operations with side effects:

- Use an **idempotency key** and unique constraints where appropriate.
- Establish clear transaction boundaries.
- Design safe retries, backoff/jitter, and timeouts.
- For DB + message broker, consider a transactional outbox or durable event log.
- Ensure requests can recover if a worker is killed at any checkpoint.
- Do not rely solely on `@PreDestroy` to commit business data.

**A request returning HTTP 200 after SIGTERM does not prove the whole system has exactly-once processing.** It only evidences the tested HTTP path under those specific conditions.

## 11. Common Confusions and Fixes

| Confusion / error | Correct explanation |
| --- | --- |
| "Spring Boot 3.3 enables graceful automatically." | Wrong; **`server.shutdown` defaults to `immediate`** |
| "Setting shutdown phase timeout enables graceful." | Wrong; you must set **`server.shutdown=graceful`** |
| "A 20s timeout means the JVM exits within 20s." | Wrong; timeout applies **per phase**, plus other cleanup |
| "Every new HTTP request returns 503." | Wrong; Tomcat/Jetty/Netty typically reject at the network layer |
| "SIGKILL also runs @PreDestroy." | Wrong; forced kill bypasses Java shutdown hooks |
| "Clicking Stop in an IDE is always graceful." | Not guaranteed; check how the IDE stops the JVM |
| "curl to /ping after SIGTERM succeeding means graceful failed." | May be due to timing/race or connection reuse |
| "JVM alive after timeout means the property failed." | Phase wait does not force-kill all threads or blocking resources |
| "server.shutdown closes all Kafka consumers." | It is only a web server option; consumers need their own lifecycle |
| "Having readinessProbe means graceful is unnecessary." | Readiness manages routing; graceful drains in-flight requests |
| "Enabling graceful guarantees zero downtime." | Also depends on replicas, load balancers, clients, dependencies |
| "Use taskkill /F to test graceful on Windows." | That is a forced kill |
| "Very long requests will be waited on forever." | Shutdown phases have deadlines |
| "Graceful guarantees no duplicate POSTs." | Idempotency/transaction/retry policies are required |
| "Actuator readiness is built in with starter-web alone." | Requires adding Actuator and configuring probes |
| "The latest Spring Boot branch has the same defaults as 3.3." | Always consult documentation for the exact version |

## 12. Multi-Scenario Testing Before Deployment

A solid test suite should verify:

1. **Short request without shutdown:** `GET /work?seconds=2` returns body `completed=2`.
2. **In-flight request, sufficient deadline:** `GET /work?seconds=8`, SIGTERM sent after `WORK_BEGIN`; observe body `completed=8` absent external errors.
3. **Deadline too short:** timeout=3s, request=8s; do not hardcode a fixed status, monitor connections and logs.
4. **New request after signal:** hit `/ping` with Tomcat and record the connection error type.
5. **Compare immediate:** switch to `server.shutdown=immediate`, rerun the same test, and observe the difference.
6. **Docker:** send `docker stop`, verify the JVM actually receives SIGTERM.
7. **Kubernetes:** scale down or roll out, measure unready time, graceful drain, and Pod exit.
8. **Multiple requests:** one 3s request, one 12s request, 20s budget; check both before exit.
9. **Slow dependency:** request blocked on DB/API, inspect client timeouts and resource closure.
10. **Forced kill:** SIGKILL to test recovery and idempotency.
11. **Long-lived protocols:** SSE/WebSockets/large downloads; observe server-specific connection behavior.
12. **Real traffic:** measure 502/503/504 errors at ingress, not only application logs.

### What Metrics Should Be Collected?

- Timestamp when SIGTERM / `ApplicationContext.close` begins.
- In-flight HTTP request counts and response durations.
- Moment the server stops accepting new requests.
- Time the web graceful phase waited for callback.
- Stop durations of other `SmartLifecycle` phases.
- `@PreDestroy` and client/executor cleanup durations.
- Pod readiness and EndpointSlice/Ingress routing events.
- JVM exit timestamp and exit code.
- Client error counts, request retries, and duplicate business operations.

Logs must not contain credentials, access tokens, or sensitive data. In the demo, the `AtomicInteger` counter is purely for observation, not a production metrics system.

## 13. Self-Check Exercises

**Question 1.** In Spring Boot 3.3, when `server.shutdown` is omitted, what is the default? Write two configuration lines to enable graceful with a 15s timeout.

**Question 2.** Why does `spring.lifecycle.timeout-per-shutdown-phase=20s` not guarantee total JVM shutdown takes at most 20s?

**Question 3.** With Tomcat, must a new request after SIGTERM receive HTTP 503? Why?

**Question 4.** With Undertow, what can happen to a new request during graceful shutdown?

**Question 5.** An HTTP request already started and needs 8 more seconds; the JVM receives SIGTERM with a 20s shutdown phase budget. What does graceful shutdown attempt to achieve? What can still make the request fail?

**Question 6.** Why is running `java -jar` better for testing signals than grabbing the PID of `mvn spring-boot:run`?

**Question 7.** Why do `taskkill /F` or `kill -KILL` prove nothing about whether graceful shutdown works?

**Question 8.** Kubernetes has `terminationGracePeriodSeconds=10` while the web graceful phase timeout is `20s`. What is the risk?

**Question 9.** How does `readinessProbe` differ in responsibility from graceful shutdown during a rolling deploy?

**Question 10.** A message consumer keeps pulling work while the web server is in graceful shutdown. Does the web property automatically stop the consumer?

**Question 11.** If the database committed yet the client missed 200 due to a connection drop, what mechanism prevents duplicate data on retry?

**Question 12.** An IDE kills the process immediately on Stop. How should you retest?

**Suggested answers:**

1. Immediate; set **`server.shutdown=graceful`** and **`spring.lifecycle.timeout-per-shutdown-phase=15s`**.
2. There are multiple phases, destroy callbacks, and resources outside the web server.
3. No; Tomcat stops accepting at the network layer, so clients may hit connection errors.
4. Undertow may accept and return **503 Service Unavailable**.
5. Tries to let the accepted request complete; network/client/downstream/app failures can still occur.
6. The Java PID is unambiguous; Maven may be an intermediate wrapper process.
7. Forced kills bypass orderly JVM shutdown hooks.
8. Kubelet may force-kill the container before draining finishes.
9. Readiness shifts traffic away from the Pod; graceful handles in-flight work and web server shutdown.
10. No; consumers need their own lifecycle stop/ack/drain.
11. Idempotency keys, unique constraints, and transaction/retry policies.
12. Send SIGTERM to a real JVM on Linux/WSL/container or write a controlled test calling `context.close()`.

## 14. Spring Boot 3.3 Deployment Checklist

- [ ] Confirmed **`3.3.x`** and default **`server.shutdown=immediate`**?
- [ ] Explicitly enabled **`server.shutdown=graceful`**?
- [ ] Shutdown phase timeout large enough for legitimate request durations?
- [ ] Not confusing per-phase timeout with a global JVM deadline?
- [ ] Identified embedded web server: Tomcat, Jetty, Undertow, or Reactor Netty?
- [ ] Tested actual network-layer rejection vs. 503 behavior for your server?
- [ ] JVM receives SIGTERM/`ApplicationContext.close` instead of immediate IDE/Docker wrapper kill?
- [ ] **`spring.main.register-shutdown-hook`** not unintentionally disabled?
- [ ] Docker ENTRYPOINT forwards signals directly to Java?
- [ ] Kubernetes termination grace sufficient for `preStop` + lifecycle + cleanup?
- [ ] Proper readiness/probes/load-balancer draining configured?
- [ ] HTTP clients/proxies have timeouts compatible with long requests?
- [ ] Background consumers, executors, and schedulers have dedicated stops?
- [ ] Database/business operations have idempotency/recovery?
- [ ] Tested SIGTERM and forced termination in staging?
- [ ] Metrics exist for in-flight requests, shutdown latency, and client errors?
- [ ] Not promising zero downtime solely from one property?

## 15. Conclusion and References

For Spring Boot 3.3, the core configuration is:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

**Spring Boot 3.3 defaults to immediate**, so graceful must be enabled explicitly. Spring stops accepting new HTTP requests according to the embedded server's mechanism and allows in-flight requests time to finish during `ApplicationContext` shutdown. The wait duration belongs to the **SmartLifecycle shutdown phase**, not a guarantee for total shutdown time across all resources.

To reduce real-world deployment failures, combine this with **SIGTERM reaching the exact JVM**, **readiness/load-balancer draining**, **Kubernetes `terminationGracePeriodSeconds`**, and **timeout, retry, and idempotency** policies. Not every web server returns 503 for new requests when stopping acceptance.

### Official Sources, Matching the 3.3 Branch

1. Spring Boot 3.3 — Graceful Shutdown, supported servers and configuration: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
2. Spring Boot 3.3 — Common Application Properties, `server.shutdown` default `immediate` and lifecycle timeout default `30s`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
3. Spring Boot 3.3 — SpringApplication, startup/shutdown and availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
4. Spring Boot 3.3 — Actuator health/readiness probes: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
5. Spring Framework 6.1 — Lifecycle/SmartLifecycle: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-nature.html
6. Kubernetes — Pod termination: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination

**Example versions:** Java 17+, Spring Boot 3.3.13, default Spring MVC/Tomcat. When upgrading to Boot 3.4+, re-check defaults and semantics in the target version's documentation rather than copying 3.3 assumptions verbatim.