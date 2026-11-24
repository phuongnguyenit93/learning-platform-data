# Distinguishing Liveness, Readiness, and Startup Probes

## 1. Three Checks Answer Three Different Questions

A running Java process is not enough to conclude an application can serve users. For example, the HTTP server may have opened its port while lookup data is still loading; or the application may temporarily stop accepting new requests to self-recover. Restarting in both situations could prevent the application from ever completing its work.

A **probe** is a check performed by kubelet, the container management agent on each Kubernetes node, which uses the result to decide what action to take. In this lesson, probes use HTTP to read signals provided by Spring Boot Actuator.

| Type | Question to answer | Action when failures reach threshold | Lifecycle |
| --- | --- | --- | --- |
| Liveness | Is the internal state of this instance still healthy, or able to self-recover? | Kubelet stops the container; restarting follows the restart policy | Checked periodically after the startup phase if a startup probe exists |
| Readiness | Is this instance ready to receive traffic? | Marked not ready so Service stops routing traffic to the Pod; container keeps running | Checked repeatedly; can transition back and forth between ready and not ready |
| Startup | Has the current startup passed the chosen initialization milestone? | Stops the container if allowed attempts are exhausted; restarting follows the policy | Stops checking after the first success; runs again if the container restarts |

When a startup probe is configured, kubelet does not run liveness or readiness probes until the startup probe succeeds. After that, liveness and readiness operate independently; readiness does not wait for a liveness check to succeed first. See [Kubernetes Pod probe model](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

Tie each signal to the **desired remediation action**. Restarting handles a broken internal state that does not self-recover. Stopping traffic fits an instance that needs time to recover. Granting extra initialization time solves a slow-starting application that is still making progress.

## 2. Spring Boot Provides Signals; Kubernetes Takes Action

Flow of responsibilities when using HTTP probes:

```text
Application state / health checks
    -> Actuator returns HTTP status at endpoint
    -> kubelet calls endpoint per probe configuration
    -> kubelet applies success/failure thresholds
    -> updates readiness or stops container
```

Spring Boot manages two states via `ApplicationAvailability`:

- `LivenessState.CORRECT`: internal state is considered valid.
- `LivenessState.BROKEN`: internal state is broken; infrastructure needs to restart it.
- `ReadinessState.ACCEPTING_TRAFFIC`: ready to receive traffic.
- `ReadinessState.REFUSING_TRAFFIC`: should temporarily not receive traffic.

Liveness semantics are defined in the [LivenessState API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/LivenessState.html); [ReadinessStateHealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/availability/ReadinessStateHealthIndicator.html) reads readiness state to produce a health result.

Actuator **does not restart the JVM itself** when reporting an error. Calling an endpoint with `curl` on a local machine does not create Kubernetes orchestration either. Likewise, publishing `REFUSING_TRAFFIC` does not erect a filter blocking all HTTP requests. It provides a signal so the orchestrator stops sending new requests to this instance.

Default liveness is also not a detector for every Java error: it does not automatically prove every business flow works, every lock is uncontended, or every request succeeds. An issue affects probes only when it is reflected in availability/health state or causes probe calls to fail.

## 3. Relationship to the Startup Process

Spring Boot distinguishes between context initialization and finishing startup tasks. An application can have valid liveness while readiness still refuses traffic. Readiness transitions to accepting traffic after `ApplicationRunner` and `CommandLineRunner` beans have finished executing. See [Spring Boot 3.3 Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

Constructed example: a service must load a conversion table before calculating prices.

```text
New container starts
  |
  +-- JVM and Spring context initializing
  |     Endpoints may not be reachable yet
  |
  +-- Context ready, runner loading conversion table
  |     Liveness can be UP; readiness remains OUT_OF_SERVICE
  |
  +-- Runner completes
        Readiness transitions to UP
        Pod can be selected by Service when other Ready conditions are also met
```

Do not infer port-opening timing solely from an in-memory enum. HTTP checks also depend on the web server, port, path, network, and security configuration. Nor should you conclude an application is ready merely from a log line containing `Started`.

If a mandatory task runs asynchronously and the runner exits before that task finishes, the runner's return time no longer represents initialization completion. With such a design, you need a readiness check reflecting the actual completion condition; avoid letting the ready signal appear too early.

### Startup Probe Is Not the `/actuator/startup` Endpoint

`startupProbe` is a field in Kubernetes configuration. It needs a suitable check, such as calling the liveness or readiness endpoint.

Actuator's `/actuator/startup` endpoint reports startup step information when the corresponding recording is configured; it is not the default startup probe endpoint. Do not pick a path just because its name contains `startup`. Refer to the [Actuator endpoints list](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Two choices serve different purposes:

| Startup probe calls | Chosen milestone | Consequence in the conversion-table loading example |
| --- | --- | --- |
| `/actuator/health/liveness` | Application can already answer liveness signals successfully | Startup can finish before loading completes; readiness continues keeping the Pod out of traffic |
| `/actuator/health/readiness` | Application has met configured readiness conditions | Startup budget must cover the table-loading phase; if readiness depends on external systems, outages there can also exhaust the startup budget |

This table shows how to choose a contract for a specific application. There is no universal requirement that startup must always call one of these two paths. In the example below, startup calls liveness and data loading is guarded by readiness.

## 4. A Spring Boot Experiment Runnable on a Local Machine

This standalone example uses Java 17 or later and Spring Boot 3.3.13. It requires Maven, a free port 8080, and the ability to download dependencies. It is a minimal lab project and does not require adding endpoints to an existing module just to have an API.

Create these exact three files:

```text
probe-demo/
├── pom.xml
└── src/main/
    ├── java/example/probes/ProbeDemoApplication.java
    └── resources/application.yml
```

### 4.1. `pom.xml`

```xml
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
    <artifactId>probe-demo</artifactId>
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
```

### 4.2. `src/main/resources/application.yml`

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true

demo:
  startup-delay-ms: 30000
```

`probes.enabled=true` enables the probe groups even when running outside Kubernetes. The example uses only the application port 8080, without a separate `management.server.port`.

### 4.3. `src/main/java/example/probes/ProbeDemoApplication.java`

```java
package example.probes;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ProbeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProbeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner warmUp(
            @Value("${demo.startup-delay-ms:30000}") long delayMillis) {
        return args -> Thread.sleep(delayMillis);
    }

    @RestController
    static class HelloController {
        @GetMapping("/hello")
        String hello() {
            return "hello\n";
        }
    }

    @RestController
    @Profile("probe-lab")
    static class LabController {
        private final ConfigurableApplicationContext context;

        LabController(ConfigurableApplicationContext context) {
            this.context = context;
        }

        @PostMapping("/lab/refuse")
        String refuse() {
            AvailabilityChangeEvent.publish(
                    context, ReadinessState.REFUSING_TRAFFIC);
            return "REFUSING_TRAFFIC\n";
        }

        @PostMapping("/lab/accept")
        String accept() {
            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);
            return "ACCEPTING_TRAFFIC\n";
        }

        @PostMapping("/lab/break")
        String breakLiveness() {
            AvailabilityChangeEvent.publish(context, LivenessState.BROKEN);
            return "BROKEN\n";
        }
    }
}
```

`Thread.sleep` only simulates loading required data; it is not a recommendation to add sleep delays to real applications. The `/lab/*` routes are strictly for the experiment and exist only when the `probe-lab` profile is active. Run the experiment on the loopback address as shown below; do not enable these control routes in a real deployment.

### 4.4. Building and Observing the Startup Process

In the `probe-demo` directory, open the first terminal:

```shell
mvn -q -DskipTests package
java -jar target/probe-demo-1.0.0.jar --spring.profiles.active=probe-lab --server.address=127.0.0.1
```

The project uses Spring dependencies, so the Maven build prepares the classpath and creates the JAR; do not run `javac ProbeDemoApplication.java` alone without providing dependencies.

In a second terminal, use `curl` or `curl.exe` on Windows:

```shell
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/liveness
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/readiness
```

The two commands above use POSIX shell `/dev/null`; when running PowerShell with `curl.exe`, replace `/dev/null` with `NUL`. The `curl -i` commands below work without changing file paths.

Once the server can serve probes while the runner is still waiting, the statuses are:

```text
200
503
```

If called too early, the connection is not yet open and `curl` may print `000` with a connection error; that is not an HTTP status 000 returned by Spring. If called after the runner completes, both are `200`. The observation window depends on machine startup time and must not be equated with an absolute wall-clock timestamp.

After the runner completes:

```shell
curl -i http://127.0.0.1:8080/actuator/health/liveness
curl -i http://127.0.0.1:8080/actuator/health/readiness
```

With the configuration above, both return HTTP status `200` and body:

```json
{"status":"UP"}
```

Date headers, header order, and other headers depend on the run; they do not need to match to determine status.

### 4.5. Readiness Fails While the Process Keeps Running

Perform only after the application is ready:

```shell
curl -s -X POST http://127.0.0.1:8080/lab/refuse
curl -i http://127.0.0.1:8080/actuator/health/readiness
curl -i http://127.0.0.1:8080/actuator/health/liveness
curl -s http://127.0.0.1:8080/hello
```

Results to compare:

| Command | Result |
| --- | --- |
| POST `/lab/refuse` | Body `REFUSING_TRAFFIC` and a newline character |
| GET readiness | HTTP `503`, body `{"status":"OUT_OF_SERVICE"}` |
| GET liveness | HTTP `200`, body `{"status":"UP"}` |
| Direct GET `/hello` | Body `hello` and a newline character |

This is evidence that readiness and liveness can differ. The fact that `/hello` still responds also shows that readiness is an orchestration signal: calling the application address directly can still reach it. In a Kubernetes deployment, the Service takes time to reflect state changes; existing connections and paths bypassing the Service must be evaluated separately.

Restore and verify again:

```shell
curl -s -X POST http://127.0.0.1:8080/lab/accept
curl -i http://127.0.0.1:8080/actuator/health/readiness
```

POST returns `ACCEPTING_TRAFFIC` with a newline; readiness returns to HTTP `200`, body `{"status":"UP"}`.

### 4.6. Liveness Failure Does Not Make the JAR Exit by Itself

Perform after restoring readiness:

```shell
curl -s -X POST http://127.0.0.1:8080/lab/break
curl -i http://127.0.0.1:8080/actuator/health/liveness
curl -i http://127.0.0.1:8080/actuator/health/readiness
```

POST returns `BROKEN` with a newline. Liveness returns HTTP `503` with body `{"status":"DOWN"}`. In this experiment, readiness still returns HTTP `200` with body `{"status":"UP"}` because only the liveness state was changed; the two groups do not merge automatically. This illustrates independence, not a complete recovery design for a business application.

The JAR stays running on the local machine. On Kubernetes with a corresponding liveness probe, kubelet observes failures up to the threshold and stops the container. End the experiment with `Ctrl+C`.

## 5. Combining All Three Probes in Container Configuration

The YAML snippet below is a **fragment of a single container** under `spec.template.spec.containers` of a Deployment. It is not a full manifest for running `kubectl apply`. The container already has the application image above, listens on port 8080 on the Pod address, and does not enable the `probe-lab` profile.

```yaml
ports:
  - name: http
    containerPort: 8080

startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 36
  successThreshold: 1

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
  successThreshold: 1

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
  successThreshold: 1
```

Do not carry `--server.address=127.0.0.1` from the local run command into this container: kubelet must be able to reach the port on the Pod address.

Reading the configuration by scenario:

1. **JVM/context starting up:** the startup probe has a design budget of roughly `36 × 5 = 180` seconds. Liveness and readiness have not started yet.
2. **Liveness endpoint succeeds for the first time:** the startup probe completes. The other two probes begin running according to their configurations.
3. **Runner still loading table:** readiness fails, so the application does not receive traffic via the Service's ready-endpoint selection.
4. **Runner completes:** readiness succeeds; the Pod can become Ready when other conditions are also satisfied.
5. **Later, readiness fails enough times:** the instance is temporarily removed from the serving pool while keeping the chance to self-recover.
6. **Later, liveness fails three consecutive times:** kubelet stops the container; with a Deployment, the usual restart policy is `Always`.

In this choice, 180 seconds is the budget until **the liveness milestone succeeds**, not a guarantee that the runner finishes within 180 seconds. If an operational requirement mandates completing all initialization within a budget, choose a startup check representing that milestone and consider whether it depends on external systems.

The multiplications are estimates for sizing configuration, not a guarantee of the exact termination timestamp. Check phase, timeout duration, scheduling, and container termination time all affect actual timing. See [how to protect slow-starting containers](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/#protect-slow-starting-containers-with-startup-probes).

### Meaning of the Parameters

| Parameter | How it is used |
| --- | --- |
| `periodSeconds` | Check interval; readiness may be checked more frequently when a Pod is not Ready |
| `timeoutSeconds` | Maximum wait time for a single check; must be enough for normal responses without hanging indefinitely |
| `failureThreshold` | Consecutive failures required to consider the probe failed |
| `successThreshold` | Consecutive successes required to recover; startup and liveness must be 1 |
| `initialDelaySeconds` | Delay before the first check; when a startup probe exists, liveness/readiness delays start after startup succeeds |

In the example, readiness uses two failures to limit reacting to a transient glitch. Liveness uses a longer period and three failures to avoid restarting on a brief slowdown. These are illustrative values; choose them based on measured startup time and latency of the application.

If you raise liveness `initialDelaySeconds` very high to work around slow startup, that same delay also slows down failure detection on subsequent container restarts. A startup probe lets you separate the initialization budget from the steady-state liveness cadence.

## 6. Choosing Check Contents by Scenario

Suppose there are three instances of a pricing service and one shared database.

### 6.1. Do Not Tie a Shared Database to Liveness

If the database goes down and every instance reports broken liveness, all three will be restarted. That does not fix the database; it also wipes warm caches and causes a connection storm when the JVMs come back up. Therefore, liveness decisions should reflect internal failures that a restart can plausibly resolve.

### 6.2. Readiness Must Reflect Committed Serving Capability

Consider two concrete designs:

- The pricing service can only work with data from the database: putting a truly essential dependency check into readiness may be appropriate, but you must accept that all instances can lose readiness together.
- The service can still return valid results from cached data within a defined staleness limit: losing database connectivity does not necessarily require removing instances from service. Check the actual serving condition instead of treating every dependency as mandatory.

Default liveness/readiness groups do not automatically include every health indicator such as the database. When intentionally extending readiness, you can configure `management.endpoint.health.group.readiness.include=readinessState,db` **only if** the `db` indicator actually exists and application policy needs it. Do not copy this setting into a lab project without a DataSource. See [checking external state in probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state).

`/actuator/health` is the overall aggregated health result. Using that same path for startup, liveness, and readiness forces three different actions to rely on one shared set of conditions, potentially including external dependencies. Two dedicated groups express those decisions more accurately.

## 7. Port, HTTP Status Code, and Access Control Are All Part of the Probe Contract

### Checking on the Right Serving Path

If a separate management port is configured, probes may succeed on the management port while the business port no longer accepts connections. Spring Boot 3.3 supports adding paths on the application port:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
```

This adds `/livez` and `/readyz` on the main port. If you choose this approach, update `httpGet.path` and port in the manifest accordingly. This YAML snippet is an optional alternative, not a second configuration file for the experiment. Refer to [Actuator Kubernetes probe configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

### HTTP Status Codes Must Reflect Failure

In the experiment's default configuration, `UP` health returns 200; `DOWN` and `OUT_OF_SERVICE` return 503. For HTTP probes, kubelet evaluates the HTTP status code; it does not read the `status` string in JSON to infer failure. An endpoint returning `200` with JSON stating an error produces a false positive on kubelet's side.

Kubernetes treats HTTP codes from 200 up to below 400 as success; therefore, a redirect to a login page can mask the condition being checked. Verify the status code and path directly rather than only seeing an HTML page returned. See [HTTP liveness probe](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/#define-a-liveness-http-request).

If Spring Security is present, configure access so kubelet can reach the required probe endpoints. Enabling exposure only makes endpoints exist; it does not grant access in every SecurityFilterChain configuration. Do not open all of Actuator just to fix a 401/403 on probes. The standalone example does not add the Spring Security dependency, so no credentials are needed for the lab commands.

## 8. Evidence-Based Diagnosis

On a test cluster that already has a real Deployment, use the following commands to observe without inducing faults on a live production system:

```shell
kubectl get pods
kubectl get endpointslices
kubectl get events --sort-by=.metadata.creationTimestamp
```

Use an actual Pod name from the output to inspect `kubectl describe pod` and `kubectl logs --previous` when needed. There is no fixed stdout for these commands because Pod names, timestamps, and restart counts depend on the cluster.

| Symptom | Question to investigate |
| --- | --- |
| Pod is `Running` but not Ready | Has startup succeeded; is readiness failing with HTTP error, timeout, or genuinely still initializing? |
| `RESTARTS` increases with liveness/startup failure events | Are the path/port correct; is the budget sufficient; does the check accidentally depend on a shared system? |
| `RESTARTS` increases without corresponding probe events | Check exit code, OOMKilled, and previous logs; do not attribute every restart to liveness |
| Readiness 503, liveness 200 | Could be a valid temporary state; verify serving conditions and recovery time |
| Both endpoints 200 while business APIs fail | Probes do not cover that failure; inspect metrics, logs, and business requirements |
| Readiness flaps continuously | Check thresholds, latency, resource limits, and the cost of the check itself |

Probes should be fast, strictly bounded in time, and free of side effects. Each check should not reload an entire cache or perform write transactions. With many replicas, check cost multiplies by replica count and call frequency.

## 9. Design Decision Self-Check

1. **The context is running, but a 45-second conversion table load is in progress. Should liveness report broken?** Not merely because loading is unfinished. Readiness should remain not ready; the startup budget should match the chosen startup milestone.
2. **An instance temporarily lacks capacity for more work, but can self-recover. Which action fits?** Stopping new traffic to the instance is usually better than restarting immediately. Clear conditions are needed for readiness to return, avoiding synchronized flapping under overload.
3. **A shared database fails for 20 seconds. Why can restarting all three JVMs make things worse?** Restarting does not fix the database, loses useful state, and adds a burst of connection pressure when the instances come back up together.
4. **Startup calls liveness and succeeds after 8 seconds, while the runner finishes after 40 seconds. Does it receive traffic at second 8?** No, if readiness is still failing and traffic goes through a Service mechanism that respects readiness. Startup finishing does not replace the Ready condition.
5. **Readiness returns 503 yet calling `/hello` directly still works. Is that a contradiction?** No. Readiness state provides an orchestration signal; blocking processing inside the application requires its own mechanism.
6. **Can one endpoint that always returns 200 be used for all three probes?** That endpoint only proves a simple request can still be answered. It does not reflect completed initialization or business readiness conditions; choose checks suited to each decision.

When explaining a probe configuration, always trace: **checked condition → endpoint/HTTP code → observation thresholds → kubelet action → how the instance returns to service**. This chain helps evaluate both signal accuracy and configuration consequences.
