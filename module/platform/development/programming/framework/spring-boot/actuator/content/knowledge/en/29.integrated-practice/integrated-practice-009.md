# Verify startup, readiness, and graceful shutdown

## 1. What must this lab prove?

An application may already have an open HTTP port while still loading required data. During a new release rollout, sending business traffic at that moment easily causes errors. Conversely, when stopping an old instance, terminating the process immediately can break in-flight requests.

This lab uses a Spring MVC application with Actuator to verify the entire lifecycle:

1. **Startup:** the HTTP server is created, then data preparation runs.
2. **Readiness to serve traffic:** allow routing traffic to this instance only once mandatory preparation finishes.
3. **Graceful shutdown:** stop accepting new requests and allow time for already-accepted requests to finish.

The goal is collecting evidence from **HTTP status codes, response bodies, log milestones, and process exit timing**. Seeing only the `Started ...` line or checking that the Java process exists is not enough.

The lab pins **Java 21, Spring Boot 3.3.0, Spring MVC, and embedded Tomcat**. This is a standalone project for learning the mechanism, requiring neither a database nor Kubernetes. Maven is used to package the example; with the same libraries, lifecycle behavior does not depend on whether a main project uses Maven or Gradle.

## 2. Mental model to grasp before running

### 2.1. Liveness and readiness answer two different questions

| Signal | Question | State managed by Spring Boot | Typical orchestrator action |
| --- | --- | --- | --- |
| Liveness | Is the process itself still in a workable state? | `LivenessState.CORRECT` or `BROKEN` | May restart the instance if liveness fails enough times |
| Readiness | Should this instance receive business traffic right now? | `ReadinessState.ACCEPTING_TRAFFIC` or `REFUSING_TRAFFIC` | Adds or removes the instance from the traffic-receiving pool |

An application preparing data can have **passing liveness while failing readiness**. Restarting it repeatedly during this phase can prevent preparation from ever completing.

These states live in `ApplicationAvailability`. Actuator projects them as health groups for probing. In this lab's configuration:

- `/actuator/health/liveness`: liveness group.
- `/actuator/health/readiness`: readiness group.
- `/livez` and `/readyz`: corresponding additional paths, on the same port as business APIs.

Failing readiness does not automatically turn every Controller into HTTP 503. A load balancer must actually consume the probe result and stop sending traffic. If you want the application to reject requests itself when unready, you must add an explicit check; the example below intentionally adds that check for observation.

### 2.2. Startup milestones to distinguish

With the synchronous example in this lab, the relevant order is:

```text
Create and refresh ApplicationContext, start embedded server
    -> ApplicationStartedEvent
    -> liveness transitions to CORRECT
    -> ApplicationRunner performs mandatory preparation
    -> ApplicationReadyEvent
    -> readiness transitions to ACCEPTING_TRAFFIC
```

A wait is placed inside `ApplicationRunner` to create an observation window: HTTP is already answering, yet readiness still refuses traffic. Spring Boot's `Started ...` log line appears before all runners finish, so never use it as the sole condition for routing traffic.

`ApplicationReadyEvent` and the subsequent availability event are two separate milestones. When confirming readiness **state**, inspect the probe or `ApplicationAvailability` rather than treating the event name itself as the state.

## 3. Create the complete lab application

Prepare JDK 21, Maven 3.6.3 or newer, `curl`, three terminal windows, and free port 18080. The PowerShell commands below use `curl.exe` to avoid colliding with the `curl` alias on some PowerShell versions.

Create the `lifecycle-lab` directory with this structure:

```text
lifecycle-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/lifecycle/
    │   ├── LifecycleLabApplication.java
    │   └── WorkController.java
    └── resources/
        └── application.yml
```

### 3.1. File pom.xml

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

    <groupId>com.example</groupId>
    <artifactId>lifecycle-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
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

There is no need to specify individual versions for Spring, Micrometer, or Tomcat libraries; the parent manages a compatible set of versions.

### 3.2. File application.yml

```yaml
server:
  address: 127.0.0.1
  port: 18080
  shutdown: graceful

spring:
  application:
    name: lifecycle-lab
  lifecycle:
    timeout-per-shutdown-phase: 20s

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never

lab:
  warmup-ms: 15000
  fail-warmup: false
```

Meaning of the choices:

- `probes.enabled=true` enables liveness/readiness groups even when running on a personal machine.
- `add-additional-paths=true` creates `/livez` and `/readyz` on the main server. Same-port probes test the application's HTTP serving capability too.
- `server.shutdown=graceful` is declared explicitly for this Spring Boot 3.3 lab.
- `timeout-per-shutdown-phase=20s` is the wait limit for **each shutdown phase**, not a guarantee the whole process always exits in exactly 20 seconds.
- Expose only `health`; the lab does not use the HTTP `shutdown` endpoint.
- The loopback address restricts the server to the lab machine. When moving to containers, configure an appropriate listen address before probing from outside.

### 3.3. File LifecycleLabApplication.java

```java
package com.example.lifecycle;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LifecycleLabApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(LifecycleLabApplication.class);

        application.addListeners(
                (ApplicationListener<ApplicationEvent>) event -> {
                    if (event instanceof ApplicationStartedEvent) {
                        System.out.println("EVENT_STARTED");
                    } else if (event instanceof ApplicationReadyEvent) {
                        System.out.println("EVENT_READY");
                    } else if (event instanceof AvailabilityChangeEvent<?> change) {
                        System.out.println(
                                "AVAILABILITY " + change.getState());
                    }
                });

        application.run(args);
    }

    @Bean
    ApplicationRunner warmup(
            @Value("${lab.warmup-ms:15000}") long warmupMs,
            @Value("${lab.fail-warmup:false}") boolean failWarmup) {

        return args -> {
            if (warmupMs < 0) {
                throw new IllegalArgumentException(
                        "lab.warmup-ms must be non-negative");
            }

            System.out.println("WARMUP_BEGIN");
            Thread.sleep(warmupMs);

            if (failWarmup) {
                throw new IllegalStateException(
                        "Simulated mandatory warmup failure");
            }

            System.out.println("WARMUP_END");
        };
    }
}
```

The listener is registered on `SpringApplication` before `run`, capturing the milestones to observe. `Thread.sleep` simulates mandatory preparation such as loading a lookup table. In a real application, replace it with work that has verifiable completion.

Here the runner executes synchronously. If a runner only submits work to a background thread and returns immediately, Spring Boot can mark readiness true while background work is still incomplete. To make that work a mandatory readiness gate, design an explicit completion/check mechanism.

### 3.4. File WorkController.java

```java
package com.example.lifecycle;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkController {

    private final ApplicationAvailability availability;

    public WorkController(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @GetMapping(value = "/work",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> work(
            @RequestParam(name = "ms", defaultValue = "1000") long ms)
            throws InterruptedException {

        if (ms < 0 || ms > 60000) {
            return ResponseEntity.badRequest()
                    .body("ms must be between 0 and 60000\n");
        }

        if (availability.getReadinessState()
                != ReadinessState.ACCEPTING_TRAFFIC) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("NOT_READY\n");
        }

        System.out.println("WORK_BEGIN ms=" + ms);
        Thread.sleep(ms);
        System.out.println("WORK_END ms=" + ms);

        return ResponseEntity.ok("DONE ms=" + ms + "\n");
    }
}
```

Two intentional points:

1. The readiness check at the top of the method is **application-written logic**, not an automatic Actuator feature blocking all APIs.
2. Once a request passes the check and starts executing, the method does not re-check readiness. Thus, switching to `REFUSING_TRAFFIC` during shutdown does not cause the method to abort in-flight work.

Sleeping on an HTTP handler thread only simulates a request with a clear duration. It is not a design pattern for long-running work in production systems.

### 3.5. Compile and package

From the directory containing `pom.xml`, run:

```powershell
java -version
mvn -version
mvn clean package
```

Both direct `java` and the Java used by Maven must be JDK 21. Once Maven reports build success, `target/lifecycle-lab-1.0.0.jar` exists. Do not run the file with the `.original` suffix.

This is a multi-file Spring Boot program that must be compiled with its dependencies. Running `javac WorkController.java` alone without the Spring classpath is insufficient.

## 4. Experiment A: HTTP opens before readiness is reached

### 4.1. Prepare the observation window

Open terminal B first, then start the polling loop:

```powershell
1..40 | ForEach-Object {
    $liveCode = & curl.exe -s -o NUL -w "%{http_code}" --connect-timeout 1 --max-time 2 http://127.0.0.1:18080/livez 2>$null
    $readyCode = & curl.exe -s -o NUL -w "%{http_code}" --connect-timeout 1 --max-time 2 http://127.0.0.1:18080/readyz 2>$null
    "{0:HH:mm:ss} live={1} ready={2}" -f (Get-Date), $liveCode, $readyCode
    Start-Sleep -Seconds 1
}
```

`000` is printed by curl when no HTTP status code was received; it is not an HTTP status returned by the application. The two calls run sequentially, so do not treat them as an exact simultaneous snapshot.

In terminal A, start the application:

```powershell
java -jar target/lifecycle-lab-1.0.0.jar
```

Starting the polling loop before the app helps avoid missing the 15-second preparation window. If you still cannot act fast enough, restart with `--lab.warmup-ms=30000`.

### 4.2. Cross-check observed states

| Phase | Liveness | Readiness | What is proven |
| --- | --- | --- | --- |
| Process has not opened port yet | No HTTP response yet | No HTTP response yet | Cannot infer health from a non-existent response |
| Past `WARMUP_BEGIN`, before `WARMUP_END` | Typically observed 200 | 503 | Application is alive but not yet ready |
| Startup finished | 200 | 200 | Instance is ready under current readiness group |

Very brief transition windows may not show up in a polling sample. What matters is catching the long runner wait window with liveness 200 and readiness 503, then readiness transitioning to 200 after warmup finishes.

During the warmup window, in terminal C run:

```powershell
curl.exe -i --max-time 2 http://127.0.0.1:18080/actuator/health/liveness
curl.exe -i --max-time 2 http://127.0.0.1:18080/actuator/health/readiness
curl.exe -i --max-time 2 "http://127.0.0.1:18080/work?ms=0"
```

With the example's default configuration, the response parts to verify are:

```text
GET /actuator/health/liveness
HTTP 200
{"status":"UP"}

GET /actuator/health/readiness
HTTP 503
{"status":"OUT_OF_SERVICE"}

GET /work?ms=0
HTTP 503
NOT_READY
```

These are **the parts to verify** across the three responses, not the complete stdout of `curl -i`. Actual HTTP lines also include protocol version and server-dependent headers.

### 4.3. Cross-check startup logs

Lines printed by the example code on a successful startup appear in this order:

```text
EVENT_STARTED
AVAILABILITY CORRECT
WARMUP_BEGIN
WARMUP_END
EVENT_READY
AVAILABILITY ACCEPTING_TRAFFIC
```

Spring/Tomcat logs may interleave between them. Do not use elapsed seconds or absolute line positions of system logs as test assertions.

After `ACCEPTING_TRAFFIC`, call again:

```powershell
curl.exe -i --max-time 2 http://127.0.0.1:18080/readyz
curl.exe -i --max-time 2 "http://127.0.0.1:18080/work?ms=0"
```

Corresponding results must be readiness HTTP 200 and business request HTTP 200 with body:

```text
DONE ms=0
```

**Pass criterion A:** observe the liveness 200 / readiness 503 window during warmup, readiness 200 after warmup completes, and `/work` transitioning from rejection to successful handling.

## 5. Experiment B: keep in-flight requests running during shutdown

### 5.1. Start a sufficiently long request

Keep the ready application running in terminal A. In terminal B run:

```powershell
curl.exe -i --max-time 30 "http://127.0.0.1:18080/work?ms=10000"
```

Wait for terminal A to print:

```text
WORK_BEGIN ms=10000
```

This milestone proves the method accepted and began handling the request. Simply launching curl is not enough, because the request might not have reached the Controller yet.

### 5.2. Request normal process shutdown

Right after `WORK_BEGIN`, press **Ctrl+C in terminal A running `java -jar` directly**. The JVM needs a chance to run shutdown hooks and close the Spring context.

If running on Linux/macOS, you can send `SIGTERM` from another terminal:

```bash
kill -TERM <java-pid>
```

In this illustrative command, replace `<java-pid>` with the verified PID of the lab process. Do not send signals to all Java processes.

An IDE's Stop button may terminate the process differently. `kill -9`, `taskkill /F`, or similar forceful kills cannot be used to demonstrate graceful shutdown.

### 5.3. Collect evidence

With a 10-second request and 20-second shutdown timeout, when shutdown is requested early enough, observe:

- Availability transitions to `REFUSING_TRAFFIC`.
- The request already inside the Controller still prints `WORK_END ms=10000`.
- Curl in terminal B receives HTTP 200 and body `DONE ms=10000`.
- The process exits once remaining work finishes; it does not wait out the entire 20 seconds if work finishes sooner.

Business response body:

```text
DONE ms=10000
```

Right after requesting shutdown, use terminal C to try **new connections**:

```powershell
curl.exe --http1.1 -i -H "Connection: close" --connect-timeout 1 --max-time 2 "http://127.0.0.1:18080/work?ms=0"
curl.exe --http1.1 -i -H "Connection: close" --connect-timeout 1 --max-time 2 http://127.0.0.1:18080/readyz
```

With embedded Tomcat, the server stops accepting connections at the network layer once graceful stop starts. Thus, new requests may get connection refused or no HTTP response. Do not require every post-Ctrl+C request to return HTTP 503.

There is a transition window: a request that slipped in right before the connector stopped may receive 503 from the Controller's readiness check. With long-lived connections or another embedded server, rejection behavior can also differ. Distinguish clearly:

- **503:** an HTTP response came back from the server.
- **Connection error / curl 000:** no HTTP status code to evaluate.
- **In-flight request returning 200:** direct evidence that work continued during the grace period.

The readiness probe may also fail to connect after the connector stops. That does not contradict the `REFUSING_TRAFFIC` transition logged earlier.

**Pass criterion B:** the exact request that logged `WORK_BEGIN` before shutdown completes with the expected response, while new connections are blocked after the server enters shutdown.

## 6. Experiment C: mandatory warmup fails

Ensure the previous process has exited. Restart the polling loop in terminal B, then in terminal A run:

```powershell
java -jar target/lifecycle-lab-1.0.0.jar --lab.warmup-ms=10000 --lab.fail-warmup=true
```

Expectations:

1. `WARMUP_BEGIN` appears.
2. The runner throws `Simulated mandatory warmup failure`.
3. Neither `WARMUP_END`, `EVENT_READY`, nor `AVAILABILITY ACCEPTING_TRAFFIC` appears for this run.
4. The process exits with an error, rather than lingering forever as a ready instance.

Immediately after the Java command exits, in the same PowerShell terminal check:

```powershell
$LASTEXITCODE
```

The exit code must be non-zero. Do not run another external program before reading it, as that can overwrite `$LASTEXITCODE`.

Readiness must never become 200 during a failed run. However, merely not catching 200 in the polling loop is insufficient proof: polling could miss a brief event. Combine it with logs showing no accepting milestone and the runner's error.

**Pass criterion C:** mandatory warmup failure prevents the application from reaching traffic-accepting readiness.

## 7. Experiment D: work exceeds the shutdown timeout

Start a fresh run:

```powershell
java -jar target/lifecycle-lab-1.0.0.jar --lab.warmup-ms=0 --spring.lifecycle.timeout-per-shutdown-phase=3s
```

After readiness reaches 200, in terminal B run:

```powershell
curl.exe -i --max-time 45 "http://127.0.0.1:18080/work?ms=30000"
```

Wait for `WORK_BEGIN ms=30000`, then request shutdown as in Experiment B. Here, remaining work is significantly longer than the 3-second grace budget.

Observe the logs noting the graceful shutdown phase timeout. Once the budget expires, context closing proceeds; the application **no longer guarantees** the long request completes successfully. Depending on timing, server, and resource teardown, the client may see a closed connection or another error. Do not assign a fixed HTTP code to that situation.

Do not conclude that:

- All Java threads are forcibly interrupted at the exact 3-second mark.
- The entire JVM is guaranteed to exit in exactly 3 seconds.
- A client accidentally receiving 200 after the budget expires is a completion guarantee for all cases.

`timeout-per-shutdown-phase` bounds the wait per lifecycle phase. Other phases, resource-cleanup callbacks, and server shutdown can also affect total duration.

**Pass criterion D:** distinguish work completing within budget from work exceeding the graceful budget, backed by log evidence and client outcomes.

## 8. From local lab to deployment behind a load balancer

### 8.1. Probes must actually drive traffic

On a local machine, calling `/readyz` only observes state. In deployment, a component must read that result and update the traffic target list.

A safe rollout flow to verify separately:

```text
New instance starts
    -> warmup completes
    -> readiness passes
    -> orchestrator adds new instance to target pool

Old instance removed from target pool
    -> update propagates to routing layers
    -> receives shutdown signal
    -> drains already-accepted work within budget
    -> exits
```

This is a coordination goal across multiple components, not a promise that every platform executes them in strict lockstep. When terminating a Pod, endpoint updates and shutdown signals can lag or race. Hence single-process tests do not prove zero dropped requests in real deployments.

If using Kubernetes:

- Startup probes protect long startup windows from premature liveness checks.
- Readiness probes decide whether an instance belongs in the ready target set.
- Liveness probes detect states requiring restart; do not casually depend on external services.
- Configure probes with the right port/path, using `/livez` and `/readyz` when additional paths are enabled.
- Override `server.address` to an appropriate listen address, such as `0.0.0.0` inside containers; this lab's loopback address does not serve probes sent to a Pod IP.

Default health groups based on availability state do not by themselves prove all business features or external connections work. Include a dependency in readiness only when losing that dependency truly means the instance should stop taking traffic; avoid causing fleet-wide restarts from a transient shared-service glitch.

### 8.2. Coordinate time budgets

Distinguish at least four durations:

| Budget | Role |
| --- | --- |
| Accepted request duration | Bounds the work the application intends to finish |
| Client/proxy timeout | How long clients or proxies are willing to wait |
| Application lifecycle timeout | How long each context shutdown phase may wait |
| Platform container termination grace period | When the platform escalates to a forced kill |

Planning example: requests need at most 10 seconds, graceful phase gets 20 seconds, container gets 40 seconds. These numbers provide headroom, yet do not prove sufficiency on their own: add pre-shutdown handling, routing propagation delay, other shutdown phases, and safety margin.

If configuring `preStop` in Kubernetes, hook execution also consumes the Pod's termination grace budget. Do not treat a fixed sleep command as proof that every load balancer has finished updating.

Also never set curl timeouts shorter than the test work, then blame graceful shutdown for a client timeout.

### 8.3. Limits of conclusions

HTTP server graceful shutdown does not by itself provide:

- Replay/retry of work after a process is forcibly killed.
- Exactly-once business transaction guarantees.
- Waiting for all asynchronous tasks detached from request lifecycles.
- Safe draining for every custom consumer, scheduler, or executor.

Those components require separate shutdown and recovery contracts. For critical writes, still design transactions, safe idempotency, and ways for clients to reconcile outcomes when connections drop.

## 9. Diagnose unexpected results

| Symptom | Check first | How to handle in the lab |
| --- | --- | --- |
| Probe returns 404 | Actuator starter present, exact path, probes enabled? | Verify `probes.enabled` and `add-additional-paths`, run freshly built JAR |
| Probe returns 401/403 | Did the project add Spring Security or an auth proxy? | Check probe policy; baseline example adds no Security |
| Missed readiness 503 | Did polling start before Java? Did runner really wait? | Increase `lab.warmup-ms`, check `WARMUP_BEGIN/END` |
| Readiness passes too early in real code | Did runner launch background work and return immediately? | Tie mandatory completion condition into readiness properly |
| Readiness 503 yet API still returns 200 elsewhere | Is a router or request check blocking traffic? | Distinguish readiness signal from actual traffic enforcement |
| Ctrl+C drops request immediately | Right `java -jar` process, `server.shutdown`, graceful signal? | Repeat with a request showing `WORK_BEGIN`, no force kill |
| New request gives connection error instead of 503 | Did Tomcat already stop accepting connections? | Expected possibility; separate transport errors from HTTP codes |
| Curl times out before work finishes | Is `--max-time` shorter than test duration? | Use a long enough client budget |
| Port already in use error | Did the previous process exit? | Verify lab PID; stop only that process or change ports consistently |
| Graceful shutdown waits longer than configured | Measuring one phase or entire JVM? Other callbacks/threads? | Capture lifecycle logs and measure per phase before concluding |

If changing ports, change configuration and all probe commands consistently. If swapping Tomcat for another server or switching to WebFlux, re-run experiments for new and in-flight requests; do not carry over connection-layer expectations blindly.

## 10. Evidence log for self-verification

For each run, record Java/Spring Boot versions, CLI flags, start/stop timestamps, and log lines from that exact process. Do not pair `WORK_BEGIN` from one run with a response from another.

| Experiment | Required evidence | What cannot be inferred from this alone |
| --- | --- | --- |
| A — slow startup | Readiness 503 during warmup; then 200; warmup and availability milestones align | All business dependencies are healthy |
| B — request within budget | `WORK_BEGIN` before shutdown signal; `WORK_END` and 200 response afterward | All background task types are also awaited |
| C — warmup failure | Runner error, no accepting milestone in run, non-zero exit code | Every runtime error must fail liveness |
| D — budget exceeded | Timeout log and recorded client outcome | A fixed HTTP code or exact exit instant |

Answer these for yourself after running:

1. Why are an open HTTP port and liveness 200 still insufficient to send business traffic?
2. Does `Started ...` appearing while the runner is still warming up contradict readiness 503?
3. Why does failing readiness not automatically block all Controllers?
4. Why does an unreachable probe during shutdown not mean the health endpoint returned 503?
5. What evidence shows the long request actually entered the Controller before shutdown was requested?
6. What limitations keep graceful shutdown from replacing business recovery design?

After practice, wait for or gracefully stop the lab process and verify the test port is no longer listening. You do not need to enable the shutdown endpoint, expose all of Actuator, or alter a real application's security policy to complete this lab.

## Reference documentation

- [Spring Boot 3.3 — SpringApplication and application availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html).
- [Spring Boot 3.3 — Actuator endpoints and Kubernetes probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).
- [Spring Boot 3.3 — Graceful shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html).
