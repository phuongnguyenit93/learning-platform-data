# Distinguishing an Open Server Port from an Application Ready to Serve

## 1. The Problem: Does a LISTENING Port Mean the Application Is Usable?

No. When deploying a Spring Boot service, at least three stages must be distinguished:

1. **Java process is running**: the JVM is alive, but may still be loading configuration, creating Beans, or has not started the HTTP server yet.
2. **Web server has opened the port**: the OS/web server may have bound the address and be listening on TCP; connections to the port can succeed. This does not mean Controllers are answering, initialization tasks have finished, or the app should receive real traffic.
3. **Application is ready to serve (readiness)**: mandatory startup work is complete, the app reports that it can accept traffic, and the orchestrator/load balancer has confirmed the appropriate state before routing requests.

A server can **have port 8080 open yet not be ready**; it can also **have been ready and then temporarily become unready** while the port stays open. Conversely, a `/health` endpoint returning HTTP 200 does not guarantee business workflows function properly. Therefore, do not use the message "Tomcat started on port ...", a TCP connect check, or a simple ping response alone as the acceptance criterion for handing traffic to the app.

This lesson focuses on **web server startup and Spring Boot's readiness signals**, without diving deep into thread tuning, database pools, or authentication mechanisms.

## 2. Five Operational Questions That Must Be Separated

| Question | Observed Signal | What the Signal Actually Proves | What It Does Not Prove |
| --- | --- | --- | --- |
| Is the process alive? | PID/JVM, container status | The process has not exited | Server is listening on a port or ready to process requests |
| Is the TCP port open? | LISTEN socket, TCP connect succeeds | A listener exists on that address and port | HTTP requests can execute or startup is complete |
| Is the HTTP endpoint responding? | HTTP status, body, response time | The network path, server, and that specific endpoint responded | All dependencies or workflows are healthy |
| Is the application live? | LivenessState or liveness probe | The application's internal state is suitable to keep running | It is ready to receive traffic immediately |
| Is the instance ready? | ReadinessState or readiness probe | The instance reports ready/not ready to receive traffic | Every API, dataset, and downstream service works in all cases |

For example: after opening the socket, the server might not have finished an ApplicationRunner loading required data. A TCP probe can succeed while readiness is still **REFUSING_TRAFFIC**. If the health endpoint is also not serving requests at that moment, the HTTP check may time out or fail to connect; never assume it always returns 503.

Also, verify the **right instance, right port, and right protocol**. A proxy or management server might respond while the application's business port is failing.

## 3. Spring Boot Startup Sequence: Web Server and ApplicationReadyEvent Are Two Different Milestones

In Spring Boot 3.x, startup passes through these main milestones:

1. **SpringApplication.run(...)** prepares the environment, reads configuration, creates the ApplicationContext, and loads Bean definitions.
2. **Context refresh** initializes required components and the embedded web server (for instance, embedded Tomcat for Spring MVC); **ServletWebServerInitializedEvent** is published when the web server is initialized, providing the actual port.
3. **ApplicationStartedEvent** is published after context refresh, **before** ApplicationRunner and CommandLineRunner Beans are invoked.
4. Spring Boot updates the state to **LivenessState.CORRECT** after ApplicationStartedEvent.
5. **ApplicationRunner/CommandLineRunner** instances execute. This is the appropriate phase for mandatory startup work before receiving traffic.
6. **ApplicationReadyEvent** is published after the runners finish.
7. Immediately **after** ApplicationReadyEvent, Spring Boot publishes the state change **ReadinessState.ACCEPTING_TRAFFIC**.

This order matters: **ApplicationStartedEvent is not synonymous with ApplicationReadyEvent**. Even when receiving ApplicationReadyEvent inside a synchronous listener, the ReadinessState.ACCEPTING_TRAFFIC state may only be published in the very next step. To inspect the exact availability state, query **ApplicationAvailability** or observe **AvailabilityChangeEvent**.

Simplified diagram:

~~~text
JVM running
   |
   v
Create ApplicationContext, initialize web server
   |  WebServerInitializedEvent
   |  HTTP port may already be bound/open
   v
Context refresh complete
   |  ApplicationStartedEvent
   |  LivenessState.CORRECT
   |  ReadinessState.REFUSING_TRAFFIC
   v
ApplicationRunner / CommandLineRunner running
   |  Prepare data, verify config, mandatory warm-up
   |  Traffic should not be routed to the instance yet
   v
ApplicationReadyEvent
   |
   v
ReadinessState.ACCEPTING_TRAFFIC
   |  Observed by orchestrator via readiness probe
   v
Instance can be selected to receive traffic
~~~

The diagram depicts **logical states and orchestration flow**. Moment-to-moment socket/HTTP behavior depends on the embedded server, connector pausing mechanisms, and actual configuration. Spring Boot documentation notes that in the "Started" phase the server may **refuse to process requests**, even though the context has refreshed. Do not rely on a single log line or a single TCP connect to assume an HTTP endpoint is definitely responding.

### 3.1. Liveness Differs from Readiness

- **Liveness:** whether the application is still functioning properly internally to keep running. Common states are **BROKEN** and **CORRECT**. Kubernetes treats consecutive liveness probe failures as a signal to **restart the container**.
- **Readiness:** whether the instance should accept requests right now. Common states are **REFUSING_TRAFFIC** and **ACCEPTING_TRAFFIC**. Kubernetes uses readiness probe failures to **remove the Pod from matching Service endpoints**; being unready by itself does not trigger a restart.
- **Startup probe:** a Kubernetes mechanism giving slow-starting apps enough time to finish startup before liveness/readiness probes run. It differs from ApplicationStartedEvent and does not certify that all business workflows are ready.

An application can be **live = CORRECT** yet **ready = REFUSING_TRAFFIC**. This is a valid state while runners are executing or while an app temporarily refuses traffic for maintenance or load shedding.

## 4. Signals That Easily Lead to Wrong Conclusions

### 4.1. "Tomcat started on port 8080"

This log only describes a milestone of the embedded web server. It does not prove ApplicationRunners have finished, required caches/data are initialized, or readiness is ACCEPTING_TRAFFIC. Late startup failures can still happen after the port appears in logs.

### 4.2. "Started ReadinessDemoApplication in ... seconds"

The framework's startup log line is not the final readiness contract for the orchestrator. For Spring Boot, rely on lifecycle events and readiness state; do not build probes around string-matching log lines.

### 4.3. TCP Connect Succeeds

A port check shows that host:port accepts connections at the moment of the check. A TCP probe does not know whether Controllers, security filters, routers, runners, or the DB are ready. Using a TCP probe for HTTP service readiness risks **false positives**.

### 4.4. GET / Returns HTTP 200

A default page or simple ping endpoint can work while a critical business flow is broken; many dependencies are not checked. Conversely, HTTP 401/403 on a protected endpoint may be an authentication failure of the caller, not an unready app. Overall health, liveness, readiness, and business checks are distinct measurements.

### 4.5. GET /actuator/health Reports UP or DOWN

Global health may aggregate multiple health indicators (such as DB if configured). Spring Boot's default readiness group represents **readinessState**, and does not by default require every external service to be healthy. Thus global health can be DOWN while the readiness probe is still UP, or vice versa depending on configuration; inspect the components inside each health group.

## 5. Hands-On: Observing Server Initialization Before Readiness Switches to ACCEPTING_TRAFFIC

The following example is a minimal **Spring Boot 3.3.x + Spring MVC + Actuator + Java 17+** application runnable with Maven. It intentionally holds ApplicationRunner for 10 seconds to expose the window between server initialization and application startup completion. Never put this Thread.sleep in a production application.

### 5.1. Create the Project Structure

~~~text
readiness-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/readinessdemo/ReadinessDemoApplication.java
        └── resources/application.yml
~~~

**pom.xml**:

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
    <artifactId>readiness-demo</artifactId>
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

**src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080

management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Here health probes are explicitly enabled for **local environments**, even when not running inside Kubernetes. Spring Boot 3.3 can enable them automatically when detecting a Kubernetes environment, but you should not assume both probe paths are present in every configuration.

Once startup completes, the health groups provide:
- **GET /actuator/health/liveness**
- **GET /actuator/health/readiness**
- **GET /livez** and **GET /readyz** on the **main application port** thanks to add-additional-paths=true.

Do not set a separate management.server.port in this example. If a different management port is used, querying that port may not reflect whether the application port can receive requests; hence /livez and /readyz on the **main server port** are usually better suited for checking the real traffic path.

**src/main/java/com/example/readinessdemo/ReadinessDemoApplication.java**:

~~~java
package com.example.readinessdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.web.servlet.context.ServletWebServerInitializedEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReadinessDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReadinessDemoApplication.class, args);
    }

    @EventListener
    public void webServerInitialized(ServletWebServerInitializedEvent event) {
        System.out.println("WEB_SERVER_INITIALIZED port="
                + event.getWebServer().getPort());
    }

    @EventListener
    public void applicationStarted(ApplicationStartedEvent event) {
        System.out.println("APPLICATION_STARTED");
    }

    @Bean
    ApplicationRunner prepareBeforeTraffic(ApplicationAvailability availability) {
        return args -> {
            System.out.println("RUNNER_BEGIN readiness="
                    + availability.getReadinessState());
            Thread.sleep(10_000);
            System.out.println("RUNNER_END");
        };
    }

    @EventListener
    public void applicationReady(ApplicationReadyEvent event) {
        System.out.println("APPLICATION_READY");
    }

    @EventListener
    public void availabilityChanged(AvailabilityChangeEvent<?> event) {
        if (event.getState() instanceof ReadinessState) {
            System.out.println("READINESS_CHANGE=" + event.getState());
        }
    }
}

@RestController
class PingController {

    @GetMapping("/api/ping")
    String ping() {
        return "pong";
    }
}
~~~

The example clearly logs **web server initialized**, **application started**, **runner begin/end**, **application ready**, and **readiness state changed**. PingController illustrates a minimal business API, not a replacement for the readiness probe. The Java snippet is standalone application code when placed in the proper Maven layout with the two dependencies listed above.

### 5.2. Run and Observe

In the **readiness-demo** directory, use the first terminal:

~~~bash
mvn spring-boot:run
~~~

The messages printed by the sample code will follow this logical order:

~~~text
WEB_SERVER_INITIALIZED port=8080
APPLICATION_STARTED
RUNNER_BEGIN readiness=REFUSING_TRAFFIC
RUNNER_END
APPLICATION_READY
READINESS_CHANGE=ACCEPTING_TRAFFIC
~~~

The framework may print **other logs interleaved**; the list above only describes the order of messages printed by the sample code, not the entire stdout. The step from RUNNER_BEGIN to RUNNER_END takes about 10 seconds due to Thread.sleep; when the HTTP socket starts accepting requests depends on the server.

In a second terminal, check **while the runner is waiting**, then check again **after** receiving READINESS_CHANGE=ACCEPTING_TRAFFIC:

~~~bash
curl -i --max-time 3 http://localhost:8080/readyz
curl -i --max-time 3 http://localhost:8080/api/ping
~~~

On Windows PowerShell, invoke **curl.exe** instead of the curl alias when you need actual curl flags. To inspect the socket, use Get-NetTCPConnection -LocalPort 8080 in PowerShell or ss -lnt on Linux; verify the PID actually owning the port when multiple processes exist.

During startup, requests may **not be accepted yet, be queued, time out, or report unready**, depending on the embedded server and exact check timing; do not hardcode a single HTTP status code in tests. Once ready, with the sample configuration and application operating normally, the result is typically:

~~~http
HTTP/1.1 200

{"status":"UP"}
~~~

for **GET /readyz**; and:

~~~http
HTTP/1.1 200

pong
~~~

for **GET /api/ping**. Actual headers (Content-Type, Content-Length, Date, etc.) and HTTP protocol version depend on the client/server, so the example only highlights the meaningful status/body.

Your observation conclusion must include **log milestones**, **readiness state**, and **HTTP responses**, not just one of the three. If you run the check too late, you may miss the intermediate state; restart the sample application to observe it.

### 5.3. Why Doesn't the Example Use @PostConstruct to Hold Startup?

@PostConstruct is tied to Bean initialization; delaying or blocking there can keep the context from finishing refresh, so it does not clearly demonstrate the "context started but app not ready" stage. **ApplicationRunner/CommandLineRunner** is the right place for startup tasks designed to run **before** the application is considered ready to serve.

Never put infinite delays, user input waits, or network calls without timeouts into a runner. If work must start asynchronously after returning from a runner, Spring Boot may by default switch to ready before that work finishes; in that case you must design a dedicated readiness gate and switch to ACCEPTING_TRAFFIC only when mandatory conditions are met.

## 6. Health Probes and Kubernetes: Who Decides Whether Traffic Reaches an Instance?

In Kubernetes, **kubelet** invokes the container's probes, while **Service/EndpointSlice and networking components** rely on readiness state to route traffic. Application readiness must be **exposed via an endpoint**; merely flipping a Boolean variable in code without wiring it to the probe will not change traffic routing.

An illustrative configuration fragment **placed inside `containers[]`** of a Pod spec:

~~~yaml
startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 5
  failureThreshold: 24

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
  successThreshold: 1
~~~

This is a **configuration fragment** to place inside an actual container definition; it is not a standalone Deployment manifest. Because the sample application enables additional paths, both /livez and /readyz run on the main web port 8080.

- **startupProbe** allows up to roughly 24 × 5 seconds for the probe to succeed, noting that check timing and timeouts affect the actual elapsed window. When startupProbe is configured, Kubernetes holds off running liveness/readiness probes until the startup probe succeeds.
- **livenessProbe** asks "should this container be restarted because the app is no longer live?" Do not couple liveness to a shared DB or external API, as a downstream outage could cause every replica to restart in a cascade.
- **readinessProbe** asks "should this Pod receive requests right now?" When the probe fails enough times to reach the threshold, the Pod is marked unready and removed from the Service's ready endpoints. Kubelet keeps the container running if only readiness fails.

HTTP probes treat status **200–399** as success; error statuses or connection failures count as failures. Do not assume Kubernetes always returns HTTP 503 to clients when no ready endpoints remain: Service, ingress, gateway, and load balancer behaviors vary.

**Important:** An open port will not let Kubernetes send traffic through if your readinessProbe is properly configured. Conversely, if **there is no readinessProbe**, the application may receive routed traffic prematurely before startup runners finish.

## 7. Defining "Ready" According to Business Requirements

By default, Spring Boot switches readiness to ACCEPTING_TRAFFIC when runners finish. That **does not fully verify** business correctness by itself. Define the essential prerequisites for accepting traffic according to your real system:

- Critical configuration has been loaded and validated, and mandatory initial data is ready.
- Local components required by every request (such as a once-loaded lookup table) are built.
- The instance has capacity to accept new requests; if draining or under maintenance, it should switch to unready.
- External dependencies genuinely required to **handle most requests** are evaluated per the system's fault-tolerance strategy. Do not put every dependency into liveness; and do not automatically put every shared dependency into readiness if doing so would pull all replicas out of Service during brief shared-service blips.

You can build a **custom HealthIndicator** and add it to the readiness health group when extra checks are needed, or publish **AvailabilityChangeEvent** to control readiness during intentional pause/resume periods. State transitions must be owned consistently so two components do not overwrite each other unexpectedly.

Illustrative syntax **for use inside a Bean with access to ApplicationContext**, not a standalone program:

~~~java
AvailabilityChangeEvent.publish(
    applicationContext,
    ReadinessState.REFUSING_TRAFFIC
);
~~~

To put the instance back into service, publish **ReadinessState.ACCEPTING_TRAFFIC** after confirming conditions have recovered. If you only update the state inside an ApplicationReadyEvent listener and Spring Boot publishes its own ACCEPTING_TRAFFIC immediately afterward, your state may be overwritten; design timing and state ownership carefully.

## 8. When Readiness Is UP Yet Requests Still Fail

Readiness is a **traffic-routing signal**, not an end-to-end test of every feature. Common situations:

| Symptom | Possible Explanation | What to Check |
| --- | --- | --- |
| Port 8080 LISTENING, /readyz not returning 200 | Startup incomplete, connector not serving yet, or readiness REFUSING_TRAFFIC | Startup events, runners, probe status, timeouts |
| /readyz 200, key API returns 500 | API logic, data, dependency, or security issue outside readiness scope | Logs, traces, functional/smoke tests, custom indicators |
| /actuator/health DOWN, /readyz UP | Global health and readiness group measure different sets of conditions | Health group members, status mapping |
| /readyz 404 | Probes not enabled, different path/context-path, or wrong port called | application.yml, Actuator dependency, target URL |
| /readyz 401/403 | Endpoint blocked by the security layer | SecurityFilterChain and appropriate access rules |
| Management health UP yet main web port refuses connections | Management runs on a separate port/stack | /readyz on main port, network/connector |
| Pod Ready yet unreachable externally | Route, Service selector, ingress, gateway, or network policy misconfigured | Pod conditions, EndpointSlice, Service, ingress, TLS |
| Instance becomes unready after serving | Intentional draining, maintenance, or readiness indicator failed | ReadinessChangeEvent, downstream, pod events |

When building dashboards, separate: **JVM startup time**, **web server initialized time**, **ApplicationReadyEvent time**, **first successful readiness probe**, **Pod Ready time**, and **first successful business smoke test**. These timestamps can differ due to probe cadence and networking.

## 9. Deployment Verification Checklist

1. **Verify target:** which process/container, host, main port, and whether a proxy or separate management port exists.
2. **Verify server:** check web server initialized log, LISTEN socket, and connectivity on the right port. This confirms only the network step.
3. **Verify lifecycle:** observe ApplicationStartedEvent, runner state, ApplicationReadyEvent, and ReadinessState.ACCEPTING_TRAFFIC. Do not collapse them into one milestone.
4. **Verify HTTP probe:** call /readyz or /actuator/health/readiness directly, recording HTTP status/body, latency, and any TLS/security errors.
5. **Verify orchestrator:** in Kubernetes use kubectl describe pod, inspect Events/Conditions, and verify endpoints are ready; Pod Ready can lag behind the app reporting ready.
6. **Verify business path:** run a small smoke test against a real endpoint with essential dependencies, minimal data, and valid permissions.
7. **Verify shutdown/drain:** during rolling updates or shutdown, readiness should switch to REFUSING_TRAFFIC and traffic routing should stop before the process exits; graceful shutdown, drain time, and load balancer propagation must align.

Sample status inspection commands in Kubernetes (replace namespace and deployment/pod names for your environment):

~~~bash
kubectl get pods -n my-namespace
kubectl describe pod my-pod -n my-namespace
kubectl get endpointslices -n my-namespace
~~~

These commands only illustrate what to inspect; actual namespace/pod names depend on your deployment environment. "Pod Running" and "Pod Ready" are two distinct conditions: Running does not prove the readiness probe succeeded.

## 10. Common Design Mistakes and How to Fix Them

**Mistake 1 — Marking ready as soon as the server binds its port.** Traffic arrives while runners are still running or data is unloaded. **Fix:** use a readiness endpoint backed by ApplicationAvailability, add essential checks if needed, and verify after ApplicationReadyEvent/AvailabilityChangeEvent.

**Mistake 2 — Using liveness instead of readiness.** DB overload fails liveness, Kubernetes restarts every container, amplifying the outage. **Fix:** liveness reflects internal health; readiness governs traffic; use failover/circuit breakers for external dependencies.

**Mistake 3 — Using a TCP probe for an HTTP app with complex startup.** Open port passes even while Controllers are not ready. **Fix:** use an HTTP readiness probe with a meaningful path.

**Mistake 4 — Using general /actuator/health for readiness without reviewing indicators.** A flaky non-critical dependency pulls all instances out of Service. **Fix:** define a business-appropriate readiness health group with timeouts and degradation strategies.

**Mistake 5 — Running critical startup work fire-and-forget after runners.** Runner returns quickly, framework signals ready before real initialization finishes. **Fix:** if work is mandatory before traffic, wait for it in the startup phase with a reasonable timeout or actively gate readiness until complete.

**Mistake 6 — Confusing management endpoints with the business port.** Health on a separate management port stays UP while the request-serving connector is broken. **Fix:** expose appropriate probes on the main port and run small end-to-end checks beyond probes.

**Mistake 7 — Assuming ready means every request will succeed.** Readiness only decides routing eligibility; individual requests can still fail due to data, security, dependencies, backpressure, or bugs. **Fix:** combine readiness with business tests, metrics, logging, tracing, and error alerting.

**Mistake 8 — Assuming unready automatically restarts the container.** Kubernetes readiness failure stops Service traffic to the Pod, whereas restarts are governed by liveness/startup failures or other lifecycle policies. **Fix:** choose the right probe for the desired consequence.

## 11. Self-Check Exercises

1. An app logged WEB_SERVER_INITIALIZED, but a runner is building a 15-second cache. Should the Pod be added to the Service yet? **Not yet**, if the cache is mandatory. Wait until the readiness probe succeeds.
2. A Pod returns GET /api/ping = 200, but the readiness probe fails. Will Kubernetes route Service traffic to that Pod? **No**, once the Pod is marked unready and removed from ready endpoints, even though pinging the Pod IP directly may still succeed.
3. An API bug causes 10% of requests to fail while readiness remains UP. Is this a contradiction? **No**. Readiness does not guarantee every feature; business testing and error monitoring are required.
4. After ApplicationStartedEvent, LivenessState is CORRECT but ReadinessState is REFUSING_TRAFFIC. Is this an error state? **No**; this is the intended startup window before accepting traffic.
5. Upon ApplicationReadyEvent, an event listener immediately reads ReadinessState. Why might it not see ACCEPTING_TRAFFIC yet? **Because Spring Boot publishes the readiness state change after ApplicationReadyEvent**; observe AvailabilityChangeEvent for the exact state transition milestone.

## 12. Conclusion

**An open port** only proves part of the network infrastructure. **ApplicationStartedEvent** means the context has refreshed and startup is entering the runner phase. **ApplicationReadyEvent** arrives when runners finish; **ReadinessState.ACCEPTING_TRAFFIC** is the availability signal afterward. **Readiness probes** tell the deployment platform whether to send traffic to an instance, while **business smoke tests** verify critical functional paths work.

When inspecting Spring Boot startup, gather evidence at the right layer: **socket → HTTP → lifecycle → availability → orchestrator → business logic**. Never replace those six checks with a single "port 8080 is open" check.

## Official References

- Spring Boot 3.3 — SpringApplication, Application Events, Application Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Actuator endpoints, Kubernetes probes, lifecycle states: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Common application properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Kubernetes — Configure liveness, readiness and startup probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/