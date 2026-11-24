# Relationship Between startupProbe, livenessProbe, and readinessProbe in Spring Boot on Kubernetes

## 1. Three Probes Solve Three Different Questions

Kubernetes provides three common **container probes** to decide whether a container has finished starting up, needs a restart, or should receive new routed requests. In Spring Boot projects, Spring Boot Actuator typically provides HTTP health endpoints for kubelet to perform these checks.

Three core questions:

1. **startupProbe:** Has the application passed its initial startup phase enough for regular liveness/readiness checks to begin?
2. **livenessProbe:** Is the application still operating validly, or has it fallen into a state where the **container should be restarted**?
3. **readinessProbe:** Is the application currently **ready to receive new traffic** from a Kubernetes Service?

Do not treat the three probes as three different names for the exact same check. They have different **frequencies**, **failure consequences**, and **lifecycle milestones**.

| Probe | Purpose | When Consecutive Failures Reach Threshold | When Check Succeeds |
| --- | --- | --- | --- |
| **startupProbe** | Give the application time to start up | Kubelet terminates the container to restart per restart policy | Ends the startup check phase; allows liveness/readiness probes to begin running |
| **livenessProbe** | Detect a stuck/unrecoverable container | Kubelet restarts the container | Keeps running; does not make the Pod Ready by itself |
| **readinessProbe** | Decide whether the instance receives requests from the Service | Pod is marked unready; removed from corresponding Service endpoints | Pod can be considered Ready when other Pod/container conditions are also met |

**Sentence to remember:** startup protects **startup time**, liveness protects **recovery via restart**, readiness protects **traffic routing**.

These checks are executed by **kubelet**. Spring Boot does not directly decide whether kubelet restarts a Pod or selects Service endpoints; Boot simply provides state information or endpoints that Kubernetes can call.

## 2. Which States Does Spring Boot Provide to Kubernetes?

Spring Boot models availability with APIs in package **org.springframework.boot.availability**.

### 2.1. LivenessState

Two values:

- **LivenessState.BROKEN:** the application is assessed as not in a healthy live state.
- **LivenessState.CORRECT:** the application is considered live.

When deployed with Actuator, this state is mapped via **LivenessStateHealthIndicator** into the `liveness` health group.

### 2.2. ReadinessState

Two values:

- **ReadinessState.REFUSING_TRAFFIC:** the instance should not receive new traffic yet.
- **ReadinessState.ACCEPTING_TRAFFIC:** the instance indicates it is ready to receive traffic.

Actuator uses **ReadinessStateHealthIndicator** to expose the `readiness` health group.

### 2.3. Spring Boot Has No Equivalent StartupState

A critical point: **`startupProbe` is a Kubernetes mechanism**, not a third enum value in **ApplicationAvailability**. By default, Spring Boot provides two state groups—**liveness** and **readiness**—and does not have a default **/actuator/health/startup** Actuator endpoint merely because Kubernetes supports `startupProbe`.

Do not confuse **Actuator /actuator/startup** (an endpoint observing startup steps when the app configures appropriate `ApplicationStartup` tracking) with **a health probe for kubelet**. It is not a health group with matching UP/DOWN status by default.

In many Spring Boot applications, `startupProbe` can **call the liveness endpoint itself** with a larger startup budget; `readinessProbe` will continue checking the ready condition afterward. How to choose is explained in section 6.

## 3. Spring Boot Lifecycle and When Probes Operate

In Spring Boot 3.5, typical availability states during a successful startup:

~~~text
SpringApplication.run(args)
      |
      v
[STARTING]
  LivenessState.BROKEN
  ReadinessState.REFUSING_TRAFFIC
  Context / HTTP server being created
      |
      v
ApplicationContext.refresh()
      |
      v
ApplicationStartedEvent
  -> LivenessState.CORRECT
      |
      v
ApplicationRunner / CommandLineRunner
  (background data, warm-up, validation...)
  ReadinessState is still REFUSING_TRAFFIC
      |
      v
ApplicationReadyEvent
  -> ReadinessState.ACCEPTING_TRAFFIC
      |
      v
Application runs and can process traffic
      |
      v
Shutdown / graceful shutdown
  -> ReadinessState.REFUSING_TRAFFIC
  -> close web server, release resources
~~~

Key Boot milestones:

- **ApplicationStartedEvent:** occurs after refresh and before runners. Boot emits **LivenessState.CORRECT** immediately after the event.
- **ApplicationReadyEvent:** occurs after runners complete. Boot emits **ReadinessState.ACCEPTING_TRAFFIC** immediately after the event.
- Prior to that, readiness is considered **REFUSING_TRAFFIC**; an application still initializing is not naturally permitted to receive traffic.
- During graceful shutdown, Boot begins refusing new traffic per supported runtime/shutdown mechanics.

These are **in-memory application states**, not proof that HTTP endpoints are reachable at every moment. Before the web server binds its port, kubelet may get connection errors instead of JSON health status. During startup, some web stacks may not yet accept requests even when the context has progressed far along. Separate **availability state** from **whether probes can reach the endpoint over the network**.

## 4. Requirements for Kubernetes to Actually Use Those States

Spring Boot reporting **LivenessState.CORRECT** alone does not guarantee Kubernetes knows about it. You need at least:

1. The **Spring Boot Actuator** dependency if using standard health endpoints.
2. Probe health groups enabled and exposed by configuration.
3. HTTP listener, port, path, and security/network policies allowing **kubelet access**.
4. Appropriate **livenessProbe** and **readinessProbe** in the PodSpec.
5. If needed, a separate **startupProbe** with a sensible startup time budget.

Spring Boot Actuator 3.5 provides:

| Common Endpoint | Checks | Default Mapping When Healthy | Default Mapping When Unhealthy |
| --- | --- | --- | --- |
| **/actuator/health/liveness** | **LivenessState** | CORRECT → **UP**, HTTP **200** | BROKEN → **DOWN**, HTTP **503** |
| **/actuator/health/readiness** | **ReadinessState** | ACCEPTING_TRAFFIC → **UP**, HTTP **200** | REFUSING_TRAFFIC → **OUT_OF_SERVICE**, HTTP **503** |

The statuses/HTTP codes in the table are **Actuator defaults**. If you add health indicators or customize status mappings, results may differ. An HTTP 503 on the readiness endpoint **does not mean every business controller automatically returns 503** when the app is refusing.

In a Kubernetes environment, Boot can enable liveness/readiness probe groups automatically. To test locally or in environments not detected as Kubernetes, set:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

If the application runs a separate Actuator management server, distinguish the management port from the main application port. Section 9 explains adding **/livez** and **/readyz** on the main port to test web infrastructure more realistically.

## 5. Relationship Between the Three Probes on Kubelet's Side

Kubernetes's most important operational rule:

**If a container defines a startupProbe, kubelet does not execute livenessProbe or readinessProbe for that container until startupProbe succeeds.**

Diagram:

~~~text
Container process created
          |
          v
    Has startupProbe?
       /       \
     No         Yes
      |          |
      |          v
      |    Run startupProbe
      |          |
      |       Succeeded? -- no --> continue retrying
      |          |                 within failure budget
      |         Yes                      |
      |          |            Reached failure threshold
      |          |                       |
      |          |                 restart container
      |          v
      +----> LivenessProbe and ReadinessProbe
               run independently on schedule
                        |
         +--------------+---------------+
         |                              |
  Liveness failed                Readiness failed
  past threshold                 past threshold
         |                              |
  Restart container             Do not route requests
                                via Service endpoint
~~~

**StartupProbe only plays a role during the startup phase.** After it succeeds the first time, kubelet stops running `startupProbe` for the rest of the current container's lifetime and hands over to liveness/readiness probes. A service becoming unready 20 minutes later does **not** trigger `startupProbe` again; readiness continues evaluating throughout the lifecycle.

**ReadinessProbe and livenessProbe do not wait for each other to succeed.** Without a `startupProbe`, both can be invoked in parallel on their configured schedules. Readiness failing **does not automatically prevent liveness from running**; to delay liveness during slow app startups, consider a `startupProbe` or an appropriate `initialDelaySeconds`.

## 6. How to Choose the Endpoint for startupProbe?

This is a critical question when designing Spring Boot and Kubernetes together.

### Option A — StartupProbe Calls the Liveness Endpoint

For Spring Boot, this is the approach commonly recommended in official documentation when protecting a **slow startup phase**:

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 60

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 2
~~~

This is a **fragment belonging to a container inside a Kubernetes PodSpec**, not a complete Deployment manifest. Boot must expose those paths on port 8080 as configured.

Mechanism:

1. `startupProbe` waits for HTTP liveness to report **UP**. Until then, liveness/readiness probes are paused.
2. After context refresh succeeds and Boot emits **LivenessState.CORRECT**, `startupProbe` can begin succeeding. **It does not necessarily wait for runners to finish**.
3. From here `readinessProbe` begins running and keeps receiving **OUT_OF_SERVICE/503** until startup runners complete and Boot reports **ACCEPTING_TRAFFIC**.
4. If liveness genuinely transitions to `BROKEN` later and fails past threshold, kubelet can restart.

**Advantage:** separates **"the container passed initial boot and can now be monitored for liveness/readiness"** from **"the application is ready to serve"**. A valid runner taking tens of extra seconds will not look like a liveness failure; readiness simply keeps failing until ready.

**Limitation:** if `startupProbe` succeeds right as Boot reaches started while a runner hangs indefinitely, readiness may stay `REFUSING` forever while liveness stays `CORRECT`. That is not a `startupProbe` bug; you need **runner deadlines, timeouts, and failure policies**, or health/metrics to detect stuck startup work.

### Option B — StartupProbe Calls the Readiness Endpoint

You can configure `startupProbe` to check **/actuator/health/readiness** if your container's "startup succeeded" condition **is defined as startup tasks complete and readiness achieved**.

However:

- `startupProbe` will now not succeed until **ApplicationReadyEvent** and `ACCEPTING_TRAFFIC` or custom readiness indicators report healthy.
- All liveness/readiness probes will remain paused throughout that period.
- If readiness depends on an external system that is currently down, the container can be killed/restarted endlessly by `startupProbe` for **never becoming ready**, even while the Spring Boot process is completely alive. That may be an undesired design.

Therefore **do not use startupProbe=readiness reflexively**. With Spring Boot, having `startupProbe` target **liveness** alongside a separate `readinessProbe` usually expresses clearer boundaries of responsibility.

### Option C — No startupProbe Configured

Many applications do not need a `startupProbe`. Spring Boot already holds readiness at `REFUSING_TRAFFIC` until runners finish, so Kubernetes does not send Service traffic to the Pod too early. If `livenessProbe` has enough allowance for normal bootstrap and causes no false restarts, you can use **only livenessProbe + readinessProbe**.

**StartupProbe is helpful when the problem is:** `livenessProbe` starts too early and fails repeatedly while the JVM and Spring Boot are still booting normally, leading to `CrashLoopBackOff`. It is **not** a mandatory component of every Deployment.

## 7. Calculating Time for startupProbe and Thresholds

Key fields of an HTTP probe:

- **periodSeconds:** check interval.
- **timeoutSeconds:** maximum wait time for each probe attempt.
- **failureThreshold:** consecutive failures before kubelet deems the probe failed per threshold.
- **successThreshold:** success threshold; liveness and startup must stay at 1; readiness may require multiple successes.
- **initialDelaySeconds:** wait before kubelet begins probing; with `startupProbe` you usually do not need to overuse this once the failure budget is sufficient.

Example:

~~~yaml
startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 60
~~~

The startup budget is typically estimated as:

~~~text
failureThreshold × periodSeconds
= 60 × 5 seconds
≈ 300 seconds
~~~

This is a **configuration estimate**, not a guarantee that kubelet waits exactly 300 seconds from process launch: actual wall-clock time is affected by scheduling, initial delay, per-probe duration, timeouts, and probe distribution.

If the application takes 40–60 seconds on a cold start, pick a budget based on real measurements plus an appropriate margin. **Do not set an enormous failureThreshold** just to mask a deadlock or permanent configuration error: the system must still have a bounded limit to recover.

Comparing the two thresholds:

~~~text
startupProbe:  60 times × 5 seconds ≈ 300 seconds at startup
livenessProbe: 3 times × 10 seconds ≈ 30 seconds after startup
~~~

The goal is **lenient during startup**, **more responsive during operation**. The liveness failure budget must still account for GC pauses, CPU throttling, network lag, and endpoint responsiveness.

## 8. Runnable Spring Boot 3.5 / Java 17+ Example

The example creates a simple web application with:

- An **ApplicationRunner** simulating initialization taking about 10 seconds.
- **Actuator liveness/readiness probes**.
- **/livez** and **/readyz** on the main port.
- A controller enabled only in Spring profile **local-demo**, letting you toggle readiness between `ACCEPTING_TRAFFIC` and `REFUSING_TRAFFIC`.
- `curl` commands to observe real HTTP statuses.

**Do not copy readiness-modifying endpoints into production without security controls.** The demo isolates them with a profile and only instructs running them on localhost.

### 8.1. Project and Dependencies

Create a Spring Initializr project with:

- Maven, **Java 17 or newer**.
- Spring Boot **3.5.x**, group **com.example**, artifact **probe-demo**, package **com.example.demo**.
- Dependencies: **Spring Web**, **Spring Boot Actuator**.

In the POM generated by Initializr, the core dependencies:

~~~xml
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
~~~

This is a **POM fragment**; use a Maven project with the Spring Boot parent/BOM and build plugin provided by Initializr, not a standalone `pom.xml`.

Structure:

~~~text
probe-demo/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/demo/ProbeDemoApplication.java
  src/main/resources/application.properties
~~~

### 8.2. Complete Java File

Create **src/main/java/com/example/demo/ProbeDemoApplication.java**:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ProbeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProbeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner simulateSlowStartup(
            ApplicationAvailability availability,
            org.springframework.core.env.Environment environment) {
        return args -> {
            long millis = environment.getProperty(
                    "demo.startup-delay-ms", Long.class, 10_000L);

            System.out.println("RUNNER_BEGIN readiness="
                    + availability.getReadinessState());

            Thread.sleep(millis);

            System.out.println("RUNNER_END");
        };
    }

    @RestController
    @Profile("local-demo")
    static class LocalProbeController {

        private final ApplicationContext context;
        private final ApplicationAvailability availability;

        LocalProbeController(
                ApplicationContext context,
                ApplicationAvailability availability) {
            this.context = context;
            this.availability = availability;
        }

        @GetMapping("/demo/state")
        public Map<String, String> state() {
            return Map.of(
                    "liveness", availability.getLivenessState().name(),
                    "readiness", availability.getReadinessState().name());
        }

        @PostMapping("/demo/refuse")
        public ResponseEntity<Void> refuse() {
            AvailabilityChangeEvent.publish(
                    context, ReadinessState.REFUSING_TRAFFIC);
            return ResponseEntity.noContent().build();
        }

        @PostMapping("/demo/accept")
        public ResponseEntity<Void> accept() {
            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);
            return ResponseEntity.noContent().build();
        }
    }
}
~~~

**Compile note:** the example references **Environment** via its fully qualified name **org.springframework.core.env.Environment**, leaving an unused import of **Value**. Java allows unused imports and the program compiles fine; you can remove the `Value` import for tidiness without affecting behavior. Do not confuse it with `@Value` property expressions.

**ApplicationRunner.run(...)** declares `throws Exception`, so calling **Thread.sleep(millis)** inside the lambda is valid; if interrupted, startup can fail rather than silently treating the app as ready before mandatory preparation finishes.

**AvailabilityChangeEvent.publish(ApplicationContext, ReadinessState)** is a Spring Boot 3.5 API. It updates the availability state managed by Boot; it does not close web sockets or trigger a restart.

**@Profile("local-demo")** ensures the POST endpoints are registered only when the `local-demo` profile is active. However, a profile is not an authentication mechanism; in production do not enable this profile or expose unprotected state-control endpoints.

### 8.3. application.properties

Create **src/main/resources/application.properties**:

~~~properties
server.port=8080

# Enable health groups outside Kubernetes as well to test on localhost.
management.endpoint.health.probes.enabled=true

# Expose HTTP health endpoint (do not expose all of actuator).
management.endpoints.web.exposure.include=health

# Expose additional probes on main server port:
# /livez and /readyz
management.endpoint.health.probes.add-additional-paths=true

management.endpoint.health.show-details=never

# Simulated runner startup duration, in milliseconds.
demo.startup-delay-ms=10000
~~~

Locally, both access styles work:

~~~text
http://localhost:8080/actuator/health/liveness
http://localhost:8080/actuator/health/readiness

http://localhost:8080/livez
http://localhost:8080/readyz
~~~

When the management port is separate, **/livez** and **/readyz** are added on the main application port to reduce the risk of management-context probes reporting healthy while the main connector fails to accept requests.

### 8.4. Build and Run

From the Spring Initializr project root directory:

~~~bash
# Build:
./mvnw package

# Run local demo, bind 127.0.0.1 only to limit access scope:
java -jar target/probe-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=local-demo --server.address=127.0.0.1
~~~

Windows PowerShell/cmd uses **.\mvnw.cmd package** for the build step. If Initializr used a different artifact/version, substitute the real JAR name in `target`.

In logs, specifically the two lines printed by the runner itself are:

~~~text
RUNNER_BEGIN readiness=REFUSING_TRAFFIC
RUNNER_END
~~~

They are spaced roughly 10 seconds apart assuming the thread is not interrupted. Spring Boot and Maven may print additional logs; do not assert the two lines sit immediately adjacent in total stdout.

**Observation while the runner executes:** at `RUNNER_BEGIN`, Boot has refreshed the context yet is not ready. `ReadinessState` prints as `REFUSING_TRAFFIC`. Depending on the web server and connector state, querying probes right now may return **503/OUT_OF_SERVICE** or the endpoint may not be reachable yet. Do not treat connection errors early in startup as a bug in readiness logic.

### 8.5. Check After the Application Is Ready

Once Spring Boot reports startup success, from a second terminal:

~~~bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/demo/state
~~~

Key statuses/bodies (omitting unnecessary HTTP headers):

~~~text
GET /livez
HTTP 200
{"status":"UP"}

GET /readyz
HTTP 200
{"status":"UP"}

GET /demo/state
HTTP 200
{"liveness":"CORRECT","readiness":"ACCEPTING_TRAFFIC"}
~~~

JSON objects from **Map.of** may serialize keys in varying order; check only each field's value without relying on JSON key order.

### 8.6. Switch Readiness to Refusing, Then Recover

Call the demo endpoints:

~~~bash
curl -i -X POST http://localhost:8080/demo/refuse
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/demo/state
~~~

Under default configuration, expect:

~~~text
POST /demo/refuse -> HTTP 204
GET  /readyz      -> HTTP 503, {"status":"OUT_OF_SERVICE"}
GET  /livez       -> HTTP 200, {"status":"UP"}
GET  /demo/state  -> HTTP 200,
                    {"liveness":"CORRECT","readiness":"REFUSING_TRAFFIC"}
~~~

Explanation: **readiness** signals unwillingness to accept traffic so `readinessProbe` fails; **liveness** stays healthy so Kubernetes does not restart solely for this change. **/demo/state** remains directly callable and returns 200 because `REFUSING_TRAFFIC` is not an automatic filter blocking controllers.

Recover:

~~~bash
curl -i -X POST http://localhost:8080/demo/accept
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/demo/state
~~~

Result:

~~~text
POST /demo/accept -> HTTP 204
GET  /readyz      -> HTTP 200, {"status":"UP"}
GET  /demo/state  -> HTTP 200,
                     {"liveness":"CORRECT","readiness":"ACCEPTING_TRAFFIC"}
~~~

Only publish `ACCEPTING_TRAFFIC` in a real application once serving preconditions are met. The demo intentionally allows manual toggling to observe behavior, **not as a production management pattern**.

## 9. Kubernetes Deployment: Connecting the Three Probes to Boot

After packaging the application into a container image capable of listening on port **8080**, a sample Deployment might look like:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: probe-demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: probe-demo
  template:
    metadata:
      labels:
        app: probe-demo
    spec:
      containers:
        - name: app
          image: registry.example.com/probe-demo:1.0.0
          ports:
            - name: http
              containerPort: 8080

          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 60

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
~~~

**Note:** the image address **registry.example.com/probe-demo:1.0.0** is a structural example; build/push a real image and replace it with your real registry/tag. This lesson omits a Dockerfile because the focus is startup/liveness/readiness probes, not the container build workflow. Do not enable the `local-demo` profile in the Deployment.

**Why use /livez and /readyz?** `application.properties` in section 8 enables **management.endpoint.health.probes.add-additional-paths=true**, allowing these endpoints to run on the **main HTTP server port**. Kubelet tests a request-handling path close to the real application port.

**Why point startupProbe at /livez instead of /readyz?** The goal is to give Boot enough time to reach liveness `CORRECT` without being killed early. Afterward `readinessProbe` continues waiting for all startup runners to finish; an app not being ready yet does not necessarily mean it is broken.

**Why do liveness and readiness have different periods?** A liveness restart is costly and can trigger cascading failures; readiness can be polled more frequently to pull traffic promptly. Tune using real data rather than copying fixed thresholds.

**Do not use the example image/configuration in production** before tuning CPU/memory requests, shutdown, security, Service, observability, and realistic startup budgets.

## 10. Startup Probe Does Not Replace Readiness Probe

A common misconception: "Once `startupProbe` succeeds, the Pod is ready and does not need `readinessProbe`."

Reality:

- **StartupProbe success** only confirms the condition checked by `startupProbe` itself.
- If `startupProbe` targets **/livez**, it can pass as soon as Boot reaches started, while **ApplicationRunners are still executing** and readiness is still `REFUSING_TRAFFIC`.
- **ReadinessProbe** is what determines whether new traffic should be routed, including transitioning to unready at **runtime**.
- `livenessProbe` also keeps running after startup with its own duty of detecting faults that require a restart.

Example timeline:

~~~text
0s  Container created; Boot is starting up
    startupProbe (/livez): fail / connection refused
    liveness/readiness not running yet

18s ApplicationContext refresh finishes
    ApplicationStartedEvent -> LivenessState.CORRECT
    startupProbe (/livez): succeeds on next check

20s LivenessProbe: /livez -> 200/UP
    ReadinessProbe: /readyz -> 503/OUT_OF_SERVICE
    Runner begins loading data

33s Runner finishes
    ApplicationReadyEvent
    ReadinessState.ACCEPTING_TRAFFIC

35s ReadinessProbe: /readyz -> 200/UP
    Pod can become Ready and be added to Service endpoints
~~~

**The second marks are hypothetical examples**, not measured benchmarks or a guarantee that Spring Boot always boots in 18/33 seconds. Actual probe timing depends on `periodSeconds`, scheduling, machine load, and program lifecycle.

A `startupProbe` pointing to `/livez` neither replaces `readinessProbe`'s role nor implies Service traffic is automatically routed immediately after the started milestone.

## 11. When Is startupProbe Truly Necessary?

### Scenario A — Spring Boot Starts Fast

The application is stable, and context refresh plus runners finish within seconds. `livenessProbe` never causes restarts before Boot is live. You may only need:

~~~yaml
livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  periodSeconds: 5
  failureThreshold: 2
~~~

Omitting `startupProbe` keeps configuration simpler. Measure startup times in cold deployments, not just on a laptop.

### Scenario B — Context Refresh Takes Two Minutes

For example, a large classpath, many singletons, or expensive initialization. If `livenessProbe` starts too early and fails enough times, kubelet may restart before the application finishes booting. A `startupProbe` with a larger budget prevents erroneous restart loops.

Critically, **`startupProbe` must check a milestone the app can reach on a healthy boot**, and its budget must exceed valid startup time while still remaining bounded.

### Scenario C — Long Runner Warm-Up After Refresh

Spring Boot may already be live yet not ready. While the runner executes, **readinessProbe fails as designed**. Usually there is no need to restart the app simply because the runner has not finished yet. If a runner hangs or exceeds a business deadline, the runner itself needs timeouts/failure policies to fail startup.

### Scenario D — External DB Temporarily Failing

If the pod is already live yet a mandatory DB dependency cannot serve, readiness may fail per policy. **Liveness should not depend directly on the DB**: restarting all replicas during a shared DB outage rarely fixes the cause.

If `startupProbe` points to readiness containing a DB check, a DB outage can cause `startupProbe` to kill/restart endlessly. Distinguish **unable to start up** from **started up yet unable to receive traffic because a dependency is unready**.

## 12. Why Not Put Every Dependency into Liveness?

Spring Boot documentation recommends **liveness should not depend on external systems** such as databases, web APIs, or shared caches. Why:

1. The DB fails temporarily.
2. Every pod reports liveness DOWN if liveness is tied to the DB.
3. Kubernetes restarts every pod.
4. Multiple pods simultaneously reconnect, reload data, and contend for resources.
5. The system can turn a recoverable fault into a cascading failure.

Conversely, **readiness** may include a critical dependency when an instance cannot handle requests if that dependency fails. Still weigh:

- Dependency shared by all replicas: the entire Service can end up with zero ready endpoints on outage.
- Optional dependency: consider fallback/circuit breakers and keep the instance ready if primary features still serve.
- Dependency broken on only one pod: a readiness check can help isolate that specific pod from routing.

By default in Spring Boot 3.5, Actuator **does not automatically add every HealthIndicator to liveness/readiness groups**. To add a custom check to readiness, configure it explicitly, for example:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,customCheck
~~~

This is a **configuration example** when the project already has a **HealthIndicator** with id **customCheck**. If you have not defined that indicator, do not add this property to the demo. Probe policies must reflect real business requirements, avoiding treating every external outage as a reason to restart the process.

## 13. A Separate Management Port Can Mislead Probes

Suppose:

~~~properties
server.port=8080
management.server.port=8081
~~~

Actuator health endpoints on port 8081 can continue returning UP even while main application port 8080 stops accepting requests due to a web connector or connection pool problem.

To reduce that risk, Spring Boot offers:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

When enabled, probe health groups get additional paths **/livez** and **/readyz** on the **main application port** by default. In Kubernetes, point startup/liveness/readiness to that main port if you want to test web infrastructure closer to end users.

Pick probe paths aligned with network policies and security settings. Do not expose other sensitive Actuator endpoints merely to serve as health probes.

Some organizations choose a separate management port to restrict access; you can still use management endpoints for monitoring while exposing the two minimal probe paths on the main port.

## 14. StartupProbe, Readiness, and Graceful Shutdown

In a rolling deployment, traffic shifting typically needs three phases:

~~~text
New Pod:
  Start container
    -> startupProbe success
    -> readinessProbe success
    -> New Pod joins Service endpoints

Running Pod:
  livenessProbe keeps checking liveness
  readinessProbe reflects changes in serving capability

Old Pod being terminated:
  readiness switches to REFUSING_TRAFFIC
  -> Pod is removed from Service endpoints during update
  -> graceful shutdown finishes in-flight requests
  -> container closes
~~~

Spring Boot 3.5 lets you configure graceful shutdown:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

**Distinction:**

- Readiness false asks infrastructure to **stop routing new traffic**; propagation is not instantaneous.
- Graceful shutdown manages **in-flight requests** and closes the web server per supported contract.
- Kubernetes **`terminationGracePeriodSeconds`** caps how long a container gets to stop politely before being killed.
- A **`preStop` hook** can be considered when a buffer is needed for load balancers to update, but must be designed around the actual shutdown flow.

During shutdown, endpoints can become unreachable once the web server starts closing, so do not demand that HTTP probes always observe `REFUSING_TRAFFIC` in every single millisecond.

## 15. How HTTP Probes Differ from TCP and Exec Probes

Kubernetes supports different probing handlers:

| Handler | What It Checks | When to Use |
| --- | --- | --- |
| **httpGet** | Connects and receives an acceptable HTTP response status | Well suited for Actuator health groups |
| **tcpSocket** | Whether a TCP connection to the port can be established | Simple, yet does not confirm the app is ready |
| **exec** | Runs a command inside the container and reads exit code | When there is no HTTP server or internal checks are needed |
| **grpc** | Calls the gRPC health checking protocol | When the app exposes a matching gRPC health protocol |

**An open TCP socket does not mean the application finished startup runners.** A Spring web server can bind its port before `ApplicationReadyEvent`. If readiness must express application-level conditions, use **/actuator/health/readiness** or a health endpoint with equivalent semantics rather than TCP port alone.

A passing HTTP probe in Kubernetes is normally a status in the **200–399** range. Statuses like 503 or connection failures count as failures. Do not treat HTTP 3xx redirects to a login page as valid for a health probe; configure security/paths clearly so kubelet reaches the real endpoint.

## 16. Diagnosing Probe Failures with Kubernetes Tools

When a pod is NotReady or restarts repeatedly, pinpoint the exact failing probe type before tweaking thresholds.

Common commands:

~~~bash
kubectl get pods
kubectl describe pod probe-demo-xxxxx
kubectl logs probe-demo-xxxxx -c app
kubectl logs probe-demo-xxxxx -c app --previous
kubectl get endpointslices -l kubernetes.io/service-name=probe-demo
~~~

The name **probe-demo-xxxxx** only illustrates a Pod name pattern; replace it with the real name. The final EndpointSlice command only applies when a Kubernetes Service named **probe-demo** exists with matching EndpointSlice labels.

### StartupProbe Fails

Symptom: kubelet logs **Startup probe failed** repeatedly; the container may be restarted and enter `CrashLoopBackOff`.

Check:

- Does Spring Boot get past context refresh within the startup budget?
- Are port/path right, and does the app bind on **0.0.0.0** inside the container?
- Is Spring Actuator present and are probe groups enabled?
- Is security or a network policy blocking kubelet?
- Is `startupProbe` checking readiness with an external dependency instead of liveness?
- Are CPU throttling, DB connection waits, DNS, and GC making startup too slow?

### LivenessProbe Fails

Symptom: kubelet logs **Liveness probe failed** and restarts even while the Java process may still exist.

Check:

- Is it hitting **/livez** rather than accidentally hitting **/readyz**?
- Does liveness depend on a shared DB/API?
- Is the server overloaded so health checks time out? Tune resources/timeouts and find the bottleneck.
- Is there a deadlock/blocked event loop or thread starvation preventing both requests and probes from being served?

Do not fix by unconditionally disabling liveness if the program has a real deadlock.

### ReadinessProbe Fails

Symptom: Pod has unready status yet **does not necessarily restart**.

Check:

- Have runners or mandatory initialization finished?
- Is a custom readiness indicator `DOWN`/`OUT_OF_SERVICE`?
- Is `ApplicationAvailability` `REFUSING_TRAFFIC` due to business logic or shutdown?
- Are **successThreshold/failureThreshold** making Pod Ready updates slower than expected?
- Do Pod labels/Service selector and port match?

Do not raise the `startupProbe` budget when the real issue is **readiness permanently failing to return UP due to a broken dependency**.

## 17. Decision Table: Choosing Probes per Scenario

| Scenario | Probe to Focus On | Sensible Action |
| --- | --- | --- |
| Cold JVM and context startup take a long time | **startupProbe** | Increase bounded startup budget using liveness endpoint |
| App booted, yet runner is seeding DB | **readinessProbe** | Stay unready until runner completes |
| One instance deadlocks and stops making progress | **livenessProbe** | Restart once failures reach threshold |
| Shared DB temporarily fails, yet process is healthy | **readiness**, considering fallbacks | Do not mark liveness BROKEN solely for DB outage |
| One pod's mandatory local cache is unready | **readinessProbe** | Stop routing to that pod; reinitialize in a controlled way |
| A non-essential feature fails | Can stay **ready** | Use fallbacks/circuit breakers instead of pulling the whole pod |
| Rolling deploy must avoid sending traffic to unready pods | **readinessProbe** | Coordinate Deployment strategy and probes |
| Pod receives SIGTERM and is draining | **readiness + graceful shutdown** | Pull new traffic, finish in-flight work within timeout |
| Actuator on management port, yet main port is broken | **probe paths on main port** | Enable additional-paths and check `/livez` `/readyz` |
| Pod restarts after 30s while init takes 90s | **startupProbe** | Provide matching startup budget and check real timeouts |

## 18. Common Misconceptions

1. **"StartupProbe is mandatory for every Spring Boot application."** No; it is helpful when liveness runs too early on slow-starting apps.
2. **"StartupProbe passing means the app is ready."** Not if it checks liveness; runners may still be running.
3. **"StartupProbe runs forever throughout runtime."** No; it runs only until its first success for the container.
4. **"ReadinessProbe failure restarts the container."** No; it changes Service routing eligibility, not direct process termination.
5. **"LivenessProbe waits for readiness to become true."** No; the two probes are independent after `startupProbe` succeeds.
6. **"ReadinessState.REFUSING_TRAFFIC closes the HTTP port automatically."** No; it is availability state and an Actuator health signal; infrastructure handles traffic routing.
7. **"An open TCP port means the app is ready."** No; startup runners may still be running.
8. **"Every dependency should go into liveness."** No; external dependency outages can trigger cascading restarts.
9. **"Root /actuator/health and the readiness health group are identical."** No; their `HealthIndicator` sets and check goals can differ.
10. **"If a Service has no ready Pods, every client is guaranteed HTTP 503."** No; clients may get connection errors or ingress/proxy errors depending on the platform.
11. **"Having Actuator automatically gives you all probes in every environment."** No; dependencies, exposure, and probe groups must match configuration/version.
12. **"Changing readiness via an HTTP test endpoint is a safe production pattern."** No; strict security policies and controlled transition conditions are required.

## 19. Questions and Exercises

**Exercise 1.** A Spring Boot app needs 110 seconds to refresh its context. `LivenessProbe` starts after 10 seconds, runs every 10 seconds, and fails past its threshold before the app binds its port. Which probe should you add, which endpoint should it check, and by what principle do you pick the budget?

**Exercise 2.** `StartupProbe` calls `/livez` and has succeeded. An `ApplicationRunner` is still warming up for 15 seconds. What is the typical `ReadinessState`, and should Kubernetes route Service traffic to that pod?

**Exercise 3.** After the app is ready, controller/health logic sets readiness to `REFUSING_TRAFFIC` while liveness remains `CORRECT`. Must the container restart? What changes on the Kubernetes Service?

**Exercise 4.** Why can `startupProbe` targeting `/readyz` be inappropriate when the readiness group checks a shared DB that is temporarily failing?

**Exercise 5.** If Actuator runs on port 8081 and the real application runs on 8080, why can probing `/actuator/health/readiness` only on 8081 produce misleading signals?

**Exercise 6.** When probing Spring Boot readiness state, is `tcpSocket` on 8080 sufficient? Why or why not?

**Exercise 7.** A pod is in graceful shutdown. Readiness switches to `REFUSING_TRAFFIC`, yet an in-flight HTTP request is still allowed to finish. Is that contradictory?

**Exercise 8.** Give an example where `startupProbe` is unnecessary yet `readinessProbe` is still advisable.

### Suggested Answers

1. Consider **startupProbe** targeting the liveness path, choosing `periodSeconds × failureThreshold` big enough to cover valid startup with margin; simultaneously investigate why refresh is slow.
2. Usually **REFUSING_TRAFFIC** until runners finish; `readinessProbe` is not yet passing, so the Service should not send traffic there.
3. No; readiness governs routing, whereas liveness is what triggers restarts after hitting its failure threshold.
4. A DB outage can prevent `startupProbe` from passing so kubelet kills/restarts a healthy app; using liveness for startup and a separate readiness probe is usually better.
5. A healthy management connector does not guarantee the main connector can serve; enable additional probe paths on the main port.
6. No; TCP only confirms the port accepts connections, not readiness logic.
7. No; readiness refuses **new traffic**, while graceful shutdown lets **in-flight requests** finish per policy.
8. A fast-starting service that occasionally needs to pull out of routing when a mandatory local cache is lost.

## 20. Deployment and Retention Checklist

- [ ] Clearly distinguished **startup = allow boot**, **liveness = restart when needed**, **readiness = accept traffic**.
- [ ] Is Spring Boot Actuator on the classpath when using standard health endpoints?
- [ ] Are liveness/readiness groups enabled appropriately for the environment?
- [ ] Does kubelet check the exact **port**, **path**, HTTP scheme, and security?
- [ ] Are probe paths on the main port when the management port is separate?
- [ ] Is `startupProbe` configured only when needed and with a sensible failure budget?
- [ ] Does `startupProbe` avoid accidentally depending on an unstable external readiness condition?
- [ ] Does liveness avoid depending on shared DB/cache/web APIs?
- [ ] Does readiness reflect conditions **truly mandatory** for accepting requests?
- [ ] Do runners have timeouts/failure handling instead of returning early while mandatory async tasks remain unfinished?
- [ ] Tested cold startup, CPU throttling, pod restarts, and rolling deployments?
- [ ] Verified that liveness `BROKEN` and readiness `REFUSING` actually produce distinct Kubernetes consequences?
- [ ] Are graceful shutdown, `terminationGracePeriodSeconds`, and load balancer draining compatible?
- [ ] Are unprotected debug endpoints for toggling readiness excluded from production?

**Conclusion:** `startupProbe`, `livenessProbe`, and `readinessProbe` are three controls with **different goals that complement one another**. Spring Boot Actuator supplies the two core availability signals, while Kubernetes `startupProbe` is the **startup-window protection mechanism**. A common design is **startupProbe → liveness endpoint**, **livenessProbe → liveness endpoint**, **readinessProbe → readiness endpoint**, tuned to actual startup time and serving criteria.

### Official Documentation

1. Spring Boot 3.5 Reference — Actuator / Kubernetes Probes / Application Lifecycle: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
2. Spring Boot 3.5 Reference — SpringApplication events and Application Availability: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
3. Spring Boot 3.5 API — ApplicationAvailability: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html
4. Spring Boot 3.5 API — AvailabilityChangeEvent: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
5. Kubernetes — Liveness, Readiness and Startup Probes: https://kubernetes.io/docs/concepts/workloads/pods/probes/
6. Kubernetes — Configure Liveness, Readiness and Startup Probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/

Example application uses **Java 17+ / Spring Boot 3.5.x**. YAML follows common Kubernetes structure, though actual APIs, cluster policies, networking/security, registries, and resource settings must be verified before applying.