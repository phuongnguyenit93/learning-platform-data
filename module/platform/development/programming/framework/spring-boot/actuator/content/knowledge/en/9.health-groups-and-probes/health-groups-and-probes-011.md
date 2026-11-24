# Observing Probe States During Startup, Traffic Draining, and Shutdown

## 1. Starting from an Application Redeployment

One application instance has just opened its HTTP port while still preparing data. Another instance is finishing in-flight requests before shutting down. Both may still have a running Java process, yet neither should receive new work from the load balancer.

This lesson walks through observing three sources of evidence simultaneously:

- **Internal state:** what does the application publish via `ApplicationAvailability` and `AvailabilityChangeEvent`?
- **HTTP probes:** what HTTP status code and payload do the probe paths return, or are they not yet reachable?
- **Business requests:** can direct calls still reach the application; do in-flight requests finish?

Probes are checks used by external systems to decide how to treat an application instance. Liveness reflects internal operability; readiness reflects traffic-acceptance capability. These two questions must be observed separately. State can be read in code via `ApplicationAvailability`. [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

**Lab scope:** Spring Boot 3.3.x, Servlet application with embedded Tomcat, Java 21, sharing a single port for business traffic and Actuator. The example pins Spring Boot 3.3.0 to reproduce the steps. No Kubernetes, database, or Spring Security is required. Do not generalize default values in this lesson to every Spring Boot version.

After the lab, you should be able to explain why an application can have passing liveness and failing readiness, why failing readiness does not prove the business port is closed, and why losing connectivity during shutdown differs from receiving an HTTP 503 response.

## 2. Reading Three State Layers Accurately

### 2.1. In-Memory State Is Not an HTTP Status Code

State names differ at each layer:

| Layer | Example |
| --- | --- |
| Readiness in application | `ReadinessState.REFUSING_TRAFFIC` |
| Corresponding health result | `OUT_OF_SERVICE` |
| Default HTTP status code when endpoint can respond | `503` |

With default indicators and mappings, the pairs to compare in this lesson are:

| Internal state | Health | HTTP |
| --- | --- | --- |
| `LivenessState.CORRECT` | `UP` | `200` |
| `LivenessState.BROKEN` | `DOWN` | `503` |
| `ReadinessState.ACCEPTING_TRAFFIC` | `UP` | `200` |
| `ReadinessState.REFUSING_TRAFFIC` | `OUT_OF_SERVICE` | `503` |

These results assume each group contains only its corresponding indicator, with no extra checks added and no custom HTTP mappings. `ReadinessStateHealthIndicator` reads readiness, while `HttpCodeStatusMapper` handles the HTTP status code layer. [ReadinessStateHealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/availability/ReadinessStateHealthIndicator.html), [SimpleHttpCodeStatusMapper](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

### 2.2. Failing to Connect Means No Health Response Yet

There are two distinct observations:

```text
HTTP 503
{"status":"OUT_OF_SERVICE"}
```

and:

```text
curl: failed to connect
HTTP 000
```

The second snippet describes a connection failure; the exact error message depends on the operating system and curl. `000` is the value curl displays when no HTTP code was received, not a status code returned by Spring Boot.

A single timeout is also not enough to conclude the application transitioned to `BROKEN`. Cross-check timestamps, lifecycle logs, the port being called, and process status.

### 2.3. Readiness Is a Signal for Routing Components

In the example below, `/demo/drain` only publishes an event changing readiness. That method does not close the connector and does not install a filter rejecting all endpoints.

Therefore, we explicitly verify two things during the same phase:

1. The readiness probe returns `503`.
2. A direct call to `/demo/work` can still complete.

A load balancer integrated with readiness uses the probe signal to stop routing traffic. With a direct curl call to `127.0.0.1`, no load balancer enforces that decision on behalf of the caller.

## 3. Milestones to Observe

| Milestone | Internal liveness | Internal readiness | What is visible externally |
| --- | --- | --- | --- |
| Creating application, no success state yet | `BROKEN` | `REFUSING_TRAFFIC` | HTTP may not be reachable yet |
| Context started, runner working | `CORRECT` | `REFUSING_TRAFFIC` | In the lab: liveness `200`, readiness `503` |
| Startup complete | `CORRECT` | `ACCEPTING_TRAFFIC` | Both probes return `200` |
| Explicitly draining via `/demo/drain` | `CORRECT` | `REFUSING_TRAFFIC` | Readiness `503`; connector still active |
| Allowing traffic again via `/demo/resume` | `CORRECT` | `ACCEPTING_TRAFFIC` | Readiness returns to `200` |
| Closing context, performing graceful shutdown | Does not switch to `BROKEN` merely due to normal shutdown | Switches to `REFUSING_TRAFFIC` | Probe reachability may vanish very quickly |
| Shutdown complete | No state left to query through the stopped app | No state left to query | No HTTP response from this process |

Do not assume every row spans enough time for curl to catch. Sampling once per second can miss a very brief state transition. Distinguishing internal state from probe reachability is essential when reading the lifecycle. [Spring Boot — Application Lifecycle and Probe States](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.lifecycle).

### 3.1. Why Is There a "Started Yet Not Ready" Window?

In a normal startup sequence, Spring Boot fires `ApplicationStartedEvent`, then publishes `LivenessState.CORRECT`. After runners complete, it fires `ApplicationReadyEvent`, then publishes `ReadinessState.ACCEPTING_TRAFFIC`. The ordering between application events and availability events matters when writing listeners. [EventPublishingRunListener, Spring Boot 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/context/event/EventPublishingRunListener.java).

The example holds a runner for 15 seconds to create a clear observation window. Simply seeing the log line `Started ProbeLabApplication` and concluding readiness succeeded overlooks the work the runner is still performing.

The availability listener below prints `event.getState()`. Do not perform another state read inside the listener to infer that all other listeners have already processed the same event.

### 3.2. When Application Shutdown Begins

In a Servlet context, the shutdown path publishes `REFUSING_TRAFFIC` before continuing to close the context. The sample code logs that event and `ContextClosedEvent`. [ServletWebServerApplicationContext.doClose](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/web/servlet/context/ServletWebServerApplicationContext.java).

Graceful shutdown gives in-flight requests a window to finish. With Tomcat, stopping new requests happens at the network layer; there is no guarantee every probe call during shutdown receives a 503 JSON body. Undertow rejects requests differently. [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html).

## 4. Creating the Standalone Lab Program

Create a separate directory with the following structure:

```text
probe-lab/
  pom.xml
  src/main/java/example/probes/ProbeLabApplication.java
  src/main/resources/application.properties
```

This is a full Spring Boot application, not a single Java file runnable with `javac ProbeLabApplication.java`. Maven provides libraries and builds the executable JAR. The first build needs access to the Maven dependency repository.

### 4.1. pom.xml File

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
    <groupId>example</groupId>
    <artifactId>probe-lab</artifactId>
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

### 4.2. application.properties File

```properties
server.address=127.0.0.1
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
management.endpoints.web.exposure.include=health
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.liveness.include=livenessState
management.endpoint.health.group.readiness.include=readinessState
management.endpoint.health.show-details=never
```

This configuration explicitly enables probes outside Kubernetes and exposes only the health endpoint over HTTP. Each group is restricted to its corresponding state indicator so the experiment is not affected by results from other checks. The paths used in this lesson are `/actuator/health/liveness` and `/actuator/health/readiness`. [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

`server.shutdown=graceful` makes the graceful shutdown choice explicit. `spring.lifecycle.timeout-per-shutdown-phase=20s` is the timeout per lifecycle shutdown phase, not a promise that the entire shutdown always lasts exactly 20 seconds.

`server.address=127.0.0.1` keeps the lab program on the local machine. The state-changing endpoints below are for lab use. Do not copy them into public management APIs when deploying applications.

### 4.3. ProbeLabApplication.java File

```java
package example.probes;

import java.io.IOException;
import java.time.Instant;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ProbeLabApplication {

    public static void main(String[] args) throws IOException {
        ConfigurableApplicationContext context =
                SpringApplication.run(ProbeLabApplication.class, args);
        try {
            System.out.println("LAB: press Enter to close");
            System.in.read();
        } finally {
            context.close();
        }
    }

    @Bean
    ApplicationRunner warmup() {
        return args -> {
            System.out.println("WARMUP begin");
            Thread.sleep(15_000);
            System.out.println("WARMUP end");
        };
    }

    @EventListener
    public void availabilityChanged(AvailabilityChangeEvent<?> event) {
        Object state = event.getState();
        System.out.println(Instant.now() + " AVAIL "
                + state.getClass().getSimpleName() + "=" + state);
    }

    @EventListener
    public void contextClosed(ContextClosedEvent event) {
        System.out.println(Instant.now() + " CONTEXT closing");
    }

    @RestController
    static class LabController {

        private final ConfigurableApplicationContext context;
        private final ApplicationAvailability availability;

        LabController(ConfigurableApplicationContext context,
                ApplicationAvailability availability) {
            this.context = context;
            this.availability = availability;
        }

        @PostMapping("/demo/drain")
        String drain() {
            AvailabilityChangeEvent.publish(context,
                    ReadinessState.REFUSING_TRAFFIC);
            return availability.getReadinessState().name();
        }

        @PostMapping("/demo/resume")
        String resume() {
            AvailabilityChangeEvent.publish(context,
                    ReadinessState.ACCEPTING_TRAFFIC);
            return availability.getReadinessState().name();
        }

        @GetMapping("/demo/work")
        String work() throws InterruptedException {
            System.out.println("WORK begin");
            Thread.sleep(10_000);
            System.out.println("WORK end");
            return "completed";
        }
    }
}
```

Intentional points built into the program:

- The runner waits 15 seconds so probes can be called before startup work finishes.
- `/demo/drain` and `/demo/resume` change readiness; they do not change liveness.
- `/demo/work` takes about 10 seconds to observe an in-flight request during application shutdown.
- After startup completes, the main thread waits for Enter and then calls `context.close()`. This closes the context cleanly even if a runner tool does not forward stop signals as expected.
- Listeners only log information; they do not attempt to keep the context alive just to serve probes.

The sleep in the example only creates an easily observable delay; it is not real initialization work. In a real application, tie readiness to actual serving conditions. If critical work is offloaded to a background thread and the runner returns immediately, this lesson's runner window no longer represents that work.

Keep terminal stdin open when running. If run with closed stdin, `System.in.read()` may hit EOF and immediately close the context right after startup.

## 5. Preparing Two or Three Terminals

From the `probe-lab` directory, build the JAR:

```powershell
mvn -q package
```

Run the application in terminal A:

```powershell
java -jar target/probe-lab-1.0.0.jar
```

The HTTP commands below use PowerShell and `curl.exe` to avoid confusion with the `curl` alias in some PowerShell versions. On Linux/macOS, use `curl` and adjust line-break syntax for your shell.

In terminal B, start the readiness polling loop **before** launching the application in A, or right afterward:

```powershell
while ($true) {
    Get-Date -Format "HH:mm:ss.fff"
    curl.exe --noproxy "*" -sS --max-time 1 -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/actuator/health/readiness
    "curl_exit=$LASTEXITCODE"
    Start-Sleep -Milliseconds 500
}
```

The loop runs until you press Ctrl+C in **terminal B**. That only ends the polling observation. To shut down the application the lab's way, press Enter in **terminal A** when `LAB: press Enter to close` appears.

`--max-time 1` bounds one HTTP sample's duration. It is not the application shutdown timeout. When no HTTP response arrives, keep both the curl error and exit code to distinguish it from a `503` response.

## 6. Experiment 1 — Catching the Started-Yet-Unready Window

Once terminal A has printed `WARMUP begin` and before it prints `WARMUP end`, call quickly from another terminal:

```powershell
curl.exe --noproxy "*" -sS --max-time 2 -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/actuator/health/liveness
curl.exe --noproxy "*" -sS --max-time 2 -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/actuator/health/readiness
```

With the lesson's configuration, the expected results of the two calls in order are:

```text
{"status":"UP"}
HTTP 200
{"status":"OUT_OF_SERVICE"}
HTTP 503
```

If running the polling loop beforehand, earlier samples may show connection errors and `HTTP 000`. That does not contradict the responses once HTTP becomes reachable.

After `WARMUP end` and after availability transitions to `ACCEPTING_TRAFFIC`, readiness must become:

```text
{"status":"UP"}
HTTP 200
```

Key lines printed by the program itself appear in the following order; timestamps on `AVAIL` lines are omitted in this listing:

```text
AVAIL LivenessState=CORRECT
WARMUP begin
WARMUP end
AVAIL ReadinessState=ACCEPTING_TRAFFIC
LAB: press Enter to close
```

Spring Boot/Tomcat logs may interleave with these lines. Do not treat this as complete stdout or a fixed timing schedule.

**Explanation:** the context is running well enough for the liveness probe to succeed, yet the runner's startup work is not finished. The application has not yet announced readiness to accept traffic.

If you miss the 15-second window and see only `200`, restart the application after opening the polling loop. Do not rename states or conclude the mechanism is broken simply because the first sample was taken too late.

## 7. Experiment 2 — Proactively Refusing Traffic via Readiness

Wait for the application to become ready, then call:

```powershell
curl.exe --noproxy "*" -sS -X POST -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/demo/drain
```

The response from the **control command** is:

```text
REFUSING_TRAFFIC
HTTP 200
```

`200` here indicates the state-change operation was processed. It is not the readiness probe result.

Call both probes again using the commands from Experiment 1. Liveness still gives `UP / 200`, while readiness switches to `OUT_OF_SERVICE / 503`.

Next, call the business endpoint directly:

```powershell
curl.exe --noproxy "*" -sS --max-time 15 -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/demo/work
```

After about 10 seconds, the expected output is:

```text
completed
HTTP 200
```

This is an important verification: the program only changed the readiness signal, while business handlers remain mapped and the connector still accepts direct requests. This lesson does not include a routing component reading readiness to remove the instance from target lists.

Return the application to ready state:

```powershell
curl.exe --noproxy "*" -sS -X POST -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/demo/resume
```

The operation returns `ACCEPTING_TRAFFIC / HTTP 200`; subsequent readiness checks return to `UP / HTTP 200`.

Publishing `ACCEPTING_TRAFFIC` in this lesson is a controlled manual action. A real service should publish this state only once serving conditions are restored; do not use the event to mask an unresolved error.

## 8. Experiment 3 — Shutting Down with an In-Flight Request

The goal is to gather evidence that an existing request gets a chance to finish while accepting new requests stops.

1. Ensure readiness is `UP / 200`.
2. Keep the probe polling loop running in terminal B.
3. In terminal C, call `/demo/work` again with `--max-time 15`.
4. Wait for terminal A to print `WORK begin` for the call just issued.
5. Immediately afterward, press Enter in terminal A.

Command in C:

```powershell
curl.exe --noproxy "*" -sS --max-time 15 -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/demo/work
```

Wait for `WORK begin` before closing so you know the request entered the handler method. If you close before the request reaches the server, you are testing new-request acceptance rather than an in-flight request.

Observe the following evidence:

- Availability log publishes `ReadinessState=REFUSING_TRAFFIC`.
- Listener logs `CONTEXT closing`.
- Tomcat begins graceful shutdown.
- For the request that entered and finished within the timeout, terminal C receives `completed / HTTP 200`.
- Once the server stops, probes no longer receive HTTP responses from the application.

The graceful shutdown infrastructure invokes `WebServer.shutDownGracefully` during the lifecycle stop phase; it does not keep a separate health server running just to answer after the application closes. [WebServerGracefulShutdownLifecycle](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/web/context/WebServerGracefulShutdownLifecycle.java).

**The loop is not required to catch a 503 in this experiment.** You may see `200` on the sample before closing and a connection error on the very next sample. Use the event logs to confirm the state transition instead of assuming readiness never changed just because a 503 JSON response was not captured.

**Shutdown is not required to wait the full 20 seconds.** If in-flight requests finish sooner, the server can complete stopping earlier. This timeout also does not guarantee an arbitrary request always completes: latency, processing errors, client-side timeouts, and OS-forced process termination can all alter the outcome.

After the application finishes shutting down, call once more:

```powershell
curl.exe --noproxy "*" -sS --max-time 2 -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/actuator/health/readiness
```

The expected result is receiving no HTTP response from the stopped process. Do not describe this outcome as `{"status":"DOWN"}` when only a connection error occurred.

### Testing with OS Stop Signals

For an application running in a terminal, Ctrl+C usually triggers the JVM's graceful shutdown path, though how an IDE or process manager sends stop signals can differ. In this lesson, pressing Enter calls `context.close()` as an explicit observation trigger.

On Linux, you can send `SIGTERM` to the exact Java PID to test signal-based shutdown. `SIGKILL`, `kill -9`, or forceful process termination does not represent a graceful shutdown experiment. Do not use them to claim Spring Boot ignored the graceful shutdown timeout.

## 9. Connecting to Kubernetes or Load Balancers

In Kubernetes, failing readiness removes an instance from eligible Service targets; failing liveness past threshold triggers a container restart. A startup probe can protect a slow-starting application; readiness does not replace that protection. Checks have periods and thresholds, so do not assume external components change decisions at the exact instant the application publishes an event. [Kubernetes — Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

When reasoning about draining an instance from traffic, record separately:

1. Time the application changes readiness.
2. Time the checker observes the change.
3. Time the routing decision takes effect.
4. Time the server starts and finishes stopping.

Local practice only directly measures application milestones and direct HTTP calls. It does not yet prove propagation time for a specific routing system.

If Actuator runs on a separate management port, record both the probe port and the business port in your evidence. A successful result on a separate management port does not fully verify the business request path. Do not substitute an observation on one port for a conclusion about the other.

## 10. Mistakes That Lead to Wrong Conclusions

| Observation or claim | How to verify and explain |
| --- | --- |
| "Started log appeared so readiness must pass" | Check `WARMUP end` and the `ACCEPTING_TRAFFIC` event; runners may still be executing |
| "Readiness 503 means the JVM is broken" | Check liveness and logs; draining from traffic can be an intentional action |
| "Drain succeeded yet business curl still works, so it's broken" | Check whether drain closes the connector or only publishes an event; direct curl bypasses routers |
| Checking only `/actuator/health` | Call `/health/liveness` and `/health/readiness` specifically; overall health does not substitute for per-group measurements |
| `404` when calling probes | Check path, port, group enablement, and exposure; do not treat it as `OUT_OF_SERVICE` |
| `401`, `403`, or login redirect | Check actual security configuration; these are not availability state codes |
| Curl shows `000` | Read the connection/timeout error and exit code; do not call it HTTP 503 |
| Did not see readiness 503 on shutdown | Check availability logs; the server may have stopped accepting connections before the next sample |
| Missed the warmup window | Start the polling loop before restarting the app; do not artificially stretch theoretical phases |
| In-flight request did not finish | Check `WORK begin`, client timeout, shutdown timeout, processing errors, and how the process was terminated |
| Looking at a single health sample and inferring the whole lifecycle | Record a timestamped observation sequence and correlate with logs from the same run |

## 11. Evidence-Based Self-Check

Build a table for your own run; record actual observed results and timestamps rather than copying a canned timeline:

| Experiment phase | Evidence to keep |
| --- | --- |
| HTTP not open yet | Curl error, exit code, presence or absence of HTTP code |
| Runner waiting | `WARMUP begin` log, results from both probes |
| Ready | `ACCEPTING_TRAFFIC` event, passing readiness |
| Drained | POST response, failing readiness, still-passing liveness |
| Direct call during drain | `/demo/work` result and explanation of router's role |
| Shutting down with in-flight request | `WORK begin`, traffic-refusal event, context closing log, client result |
| Stopped | Probe call receiving no HTTP response from the application |

Answer these questions based on that evidence:

1. Why can the same startup show `liveness=200` and `readiness=503`?
2. In the example code, which exact statement changes readiness? Is there any statement there blocking all business requests?
3. Why does POST `/demo/drain` return 200 while GET readiness probe returns 503?
4. If shutdown only shows "200 then connection error," what evidence confirms the application did switch its availability state to refusing traffic?
5. Why can an in-flight request and a new request arriving after shutdown begins have different outcomes?
6. When is measuring on a separate management port insufficient to claim the business port works?

The learning outcome to achieve is explaining each observation using the exact mechanism layer: internal events and state, health/HTTP projection, routing decisions, and server shutdown behavior.
