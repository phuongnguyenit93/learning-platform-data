# Setting Up health/liveness and health/readiness Endpoints for Infrastructure

## 1. From Application State to Infrastructure Decisions

A running Java process is not necessarily ready to accept requests. Conversely, an application temporarily pausing incoming requests does not necessarily need to be restarted. When deploying multiple replicas, infrastructure needs two distinct signals to choose the right action.

| Signal | Question to answer | Action when checks fail past threshold |
| --- | --- | --- |
| Liveness | Is this replica still in an internal state that can operate or self-recover? | Kubernetes restarts the container per the applicable policy. |
| Readiness | Is this replica ready to receive new requests? | Kubernetes marks it not ready to remove it from normal Service distribution; the container stays running. |
| Startup | Has the application passed the allowed startup phase? | If failures exhaust the threshold, the container is restarted. |

A probe is a periodic check performed by infrastructure. An endpoint is the HTTP address the application exposes for that check. Spring Boot produces the signals; kubelet reads them and enforces the policy. Merely enabling endpoints does not tell infrastructure which addresses to call.

For example, a service has finished building its Spring context yet is still loading startup data. It can be alive while not ready to serve clients. Using the same check for both purposes can cause infrastructure to repeatedly restart an application that simply needs more time.

The three probe types and their corresponding actions are described in the [Kubernetes documentation](https://kubernetes.io/docs/concepts/workloads/pods/probes/). This lesson uses Spring Boot 3.3.x, Java 21, and plain HTTP; it does not assume Spring Security is present.

## 2. Which Addresses Does Spring Boot Provide?

When probe groups are enabled, with default paths and port:

| Address | Meaning |
| --- | --- |
| `GET /actuator/health` | Aggregated overall health; may include many different checks. |
| `GET /actuator/health/liveness` | Group dedicated to liveness. |
| `GET /actuator/health/readiness` | Group dedicated to readiness. |

`health` is the Actuator endpoint ID; `liveness` and `readiness` are health groups beneath it. Therefore, HTTP exposure configuration uses `health`, not a list `liveness,readiness`.

Spring Boot automatically enables the probe groups when it detects a Kubernetes environment. For consistent runs both locally and in deployed environments, this lesson explicitly sets `management.endpoint.health.probes.enabled=true`. With the default mapping, `UP` returns HTTP 200; `DOWN` and `OUT_OF_SERVICE` return HTTP 503. See [Spring Boot 3.3: Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Infrastructure checkers should rely on HTTP status codes and connection/timeout errors. Do not merely search for the string `UP` in JSON. A proxy returning a login page or a custom controller always returning 200 can produce false signals.

## 3. Creating a Runnable Sample Application

This is a standalone Gradle project for practice, not a request to modify the build configuration of an existing module. Use Java 21 and Gradle 8.5. Spring Boot version 3.3.0 below is pinned for a reproducible example in the 3.3 line; when integrating into a real project, keep the 3.3.x version managed by your project.

### 3.1. Build Declaration

`settings.gradle` file:

```groovy
rootProject.name = 'probe-demo'
```

`build.gradle` file:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

`spring-boot-starter-web` provides the HTTP server; `spring-boot-starter-actuator` provides the health endpoint. The BOM manages dependency versions. There is no need to write custom controllers for `/actuator/health/liveness` or `/actuator/health/readiness`.

### 3.2. Main Class and Lab Tool for Changing Readiness

`src/main/java/example/probes/ProbeDemo.java` file:

```java
package example.probes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ProbeDemo {
    public static void main(String[] args) {
        SpringApplication.run(ProbeDemo.class, args);
    }

    @RestController
    @Profile("probe-lab")
    @RequestMapping("/lab/readiness")
    static class ReadinessLabController {
        private final ApplicationContext context;

        ReadinessLabController(ApplicationContext context) {
            this.context = context;
        }

        @PostMapping("/refuse")
        String refuse() {
            AvailabilityChangeEvent.publish(context, ReadinessState.REFUSING_TRAFFIC);
            return "REFUSING_TRAFFIC";
        }

        @PostMapping("/accept")
        String accept() {
            AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC);
            return "ACCEPTING_TRAFFIC";
        }
    }
}
```

The two `/lab/readiness/*` paths are lab tools that exist only when the `probe-lab` profile is active. The run command below binds the server to loopback so these tools are usable only from the lab machine. Do not enable that profile in a Deployment.

`AvailabilityChangeEvent.publish(...)` updates the state tracked by `ApplicationAvailability`; the readiness indicator translates that state into a health response. It does not automatically block business controllers. Hence `/lab/readiness/accept` can still be called directly after readiness fails. The event-publishing API is defined at [AvailabilityChangeEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html).

### 3.3. Actuator Configuration

`src/main/resources/application.yml` file:

```yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      show-components: never
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
```

Here both groups are explicitly limited using the indicator names `livenessState` and `readinessState`. `show-details` and `show-components` keep responses minimal, avoiding exposing internal structure to probes. The two groups remain distinguished by URL.

`server.shutdown=graceful` lets the server complete active requests during shutdown. `timeout-per-shutdown-phase` is the timeout per shutdown phase, not a promise that the entire JVM always exits in exactly 20 seconds. See [Spring Boot 3.3: Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html).

### 3.4. Running the Application

From the project directory, generate the wrapper once if not already present:

```bash
gradle wrapper --gradle-version 8.5
```

Run on Linux/macOS:

```bash
./gradlew bootRun --args='--spring.profiles.active=probe-lab --server.address=127.0.0.1'
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=probe-lab --server.address=127.0.0.1"
```

Wait for the application to finish starting. Do not run `javac ProbeDemo.java` with an empty classpath: this class requires Spring libraries and resource configuration provided by Gradle.

## 4. Verifying Success and Failure over HTTP

The following commands use Bash and `curl` in a separate window. In PowerShell, use `curl.exe` to avoid confusion with the PowerShell command alias. The outputs below assume the exact sample configuration, a ready application, and no environment overrides.

### 4.1. Both Groups Operating Normally

```bash
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/actuator/health/liveness
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/actuator/health/readiness
```

Output, for each command in turn:

```text
{"status":"UP"}
HTTP 200
{"status":"UP"}
HTTP 200
```

There is no need to print all headers because date, connection, and other fields can vary. This check confirms the path, HTTP status code, and status payload.

### 4.2. Temporarily Draining the Replica from the Request Flow

```bash
curl -sS -X POST -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/lab/readiness/refuse
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/actuator/health/readiness
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/actuator/health/liveness
```

Output:

```text
REFUSING_TRAFFIC
HTTP 200
{"status":"OUT_OF_SERVICE"}
HTTP 503
{"status":"UP"}
HTTP 200
```

HTTP 200 from the POST command only indicates that the state-change operation succeeded. Readiness returning 503 is the signal infrastructure uses to stop routing new requests. Liveness stays 200 because the application is still operating; there is no reason to restart due to this action alone.

Restore readiness:

```bash
curl -sS -X POST -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/lab/readiness/accept
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/actuator/health/readiness
```

Output:

```text
ACCEPTING_TRAFFIC
HTTP 200
{"status":"UP"}
HTTP 200
```

On a local machine, without kubelet, HTTP 503 does not cause the process to restart or stop accepting direct connections. With Kubernetes, removing/re-adding a replica in Service routing also depends on probe thresholds and routing propagation time.

### 4.3. Signals Change Across the Lifecycle

Spring Boot marks liveness `CORRECT` after the context is refreshed and readiness `ACCEPTING_TRAFFIC` after `ApplicationRunner`/`CommandLineRunner` finish. Before the HTTP port opens, probes may encounter connection errors; not every stage yields a 503 JSON response. Mandatory loading tasks should live inside managed startup; a self-spawned async task might still be running when Boot announces readiness. See [Spring Boot 3.3: Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

Default probes are not a detector for every deadlock, business bug, or resource exhaustion. A 200 response only proves that the selected check succeeded at that instant. Logs, operational metrics, and independent functional checks are still necessary.

## 5. Connecting Both Endpoints to Kubernetes

When sharing port 8080, probe configurations point directly to the two Actuator addresses. Below is a `spec.template.spec` snippet to merge into an existing Deployment; the `probe-demo:1.0.0` image must be built and made available to the cluster first. Do not enable `probe-lab` and do not bind `server.address` to loopback when running the container for infrastructure serving.

```yaml
terminationGracePeriodSeconds: 40
containers:
  - name: probe-demo
    image: probe-demo:1.0.0
    ports:
      - name: http
        containerPort: 8080
    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 30
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
      failureThreshold: 3
      successThreshold: 1
```

Reading the snippet in order:

1. `startupProbe` allows an approximate startup budget of `30 × 5 = 150` seconds. While startup has not succeeded yet, kubelet does not run liveness/readiness. This is an approximate design budget, not a clock guaranteed to the exact second.
2. Startup uses liveness. It may succeed before business startup tasks finish; readiness still prevents Service from sending requests too early. If a post-context task can hang indefinitely, add a timeout or error-reporting mechanism for that task.
3. Liveness runs periodically; three consecutive failures reach the restart threshold. Do not use a huge initial startup delay to mask liveness errors over the whole lifecycle.
4. Readiness runs independently after startup. Failing enough times marks the replica not ready; once it recovers for `successThreshold`, it can receive requests again.
5. `terminationGracePeriodSeconds` must suffice for actual shutdown work, including tasks beyond HTTP request handling. The 40-second value is just a sample configuration to measure and tune.

Threshold, period, and timeout fields are defined in the [Kubernetes probe configuration guide](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/). Pick values from startup times and latencies measured under load; overly tight timeouts can turn a short CPU spike into repeated restarts.

Kubelet typically calls the Pod IP and container port directly, bypassing Ingress hostnames. `containerPort` names the port for reference; it does not open an HTTP server by itself. If the application binds only to `127.0.0.1` inside the container, requests from the node to the Pod IP can fail.

## 6. If Actuator Runs on a Separate Management Port

Suppose customer-facing APIs run on 8080 and Actuator runs on 9090. If kubelet only checks 9090, the management port can still return 200 while the customer-facing server fails. Expose the probe groups on the main port and point infrastructure checks to that port.

Replace the `management` block in the previous configuration with:

```yaml
management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      show-components: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
```

Then use the following address map:

| Port | Path | Used for |
| --- | --- | --- |
| 9090 | `/actuator/health/liveness`, `/actuator/health/readiness` | Accessing Actuator via the management port. |
| 8080 | `/livez`, `/readyz` | Probes traversing the main server. |

In the Kubernetes YAML from the previous section, change `startupProbe.httpGet.path` and `livenessProbe.httpGet.path` to `/livez`; change `readinessProbe.httpGet.path` to `/readyz`; keep `port: http` on port 8080. Do not point them to 9090 and assume the main API's connection-accepting path has been checked.

Manual verification:

```bash
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/livez
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/readyz
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:9090/actuator/health/readiness
```

When the application is ready, each command returns body `{"status":"UP"}` and line `HTTP 200`. These additional paths are a feature of probe groups, described in [Spring Boot 3.3: probes on the main port](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

If configuring a context path, base path, or reverse proxy rules, verify the actual URL on the port kubelet calls. Do not piece paths together from memory. `/livez` and `/readyz` in the example assume no extra context path.

## 7. Deciding Which Checks Belong to Each Group

Avoid pointing both probes at `/actuator/health`. Suppose overall health includes a database check: a database outage can make overall health fail even while the application process is fine. If used for liveness, all replicas may restart together without fixing the database.

Keep liveness focused on internal operability. For readiness, ask: when this dependency fails, can the replica still serve valuable functionality, and does removing this replica route clients to a healthier replica?

| Design scenario | Decision to consider |
| --- | --- |
| Optional cache fails while primary data path still works | Keeping readiness succeeding can be reasonable if the system can still serve. |
| A replica-local resource fails while other replicas are fine | Failing readiness can help shift traffic to other replicas. |
| Shared database goes down, every replica needs it | Including the database in readiness can leave the entire Service with zero ready replicas; choose the policy intentionally. |

If you have decided the database is mandatory and the application genuinely has a `db` check, you can replace just the readiness group with:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include:
            - readinessState
            - db
```

This is a group override snippet, not a full `application.yml`. Do not apply this snippet verbatim to the sample application that has no DataSource. A nonexistent group member can cause group validation to fail at startup.

Do not use `include: '*'` just to avoid deciding members. For custom checks, the check operation must be lightweight, time-bounded, and free of side effects like writing business data. A readiness endpoint that overloads the database on every probe makes the system worse.

## 8. HTTP Status Codes, Security, and Networking

Kubernetes HTTP probes treat codes 200–399 as success; JSON is not parsed to infer business status. Therefore, avoid redirects to a login page: a redirect chain can make check results differ from expectations. Keep probe responses direct and verify from the actual deployment network path. See [HTTP probe rules](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

The sample application does not include Spring Security. If a project already has a `SecurityFilterChain`, existing security rules may return 401/403 or redirect before health is handled. When integrating:

- Allow only the GET method and the exact probe addresses infrastructure needs, including `/livez` and `/readyz` if used.
- Preserve authentication/authorization rules for business APIs and remaining management endpoints; do not open all of `/actuator/**` just so probes can run.
- Check network rules, sidecars, and port settings so the node can probe the Pod; do not assume reachability from a laptop means kubelet can reach it.
- Do not put passwords or long-lived tokens in probe paths. Responses only need the HTTP status code and minimal status.

`show-details: never` is not an authentication mechanism. A separate management port does not automatically create a secure network boundary either. Network policies and access policies must be configured per environment.

If you have customized `management.endpoint.health.status.http-mapping`, re-test with a failure scenario. A failure status mapped to 200 causes infrastructure to keep the replica in rotation. When declaring custom mappings, remember to retain default error mappings according to the contract of your Boot version.

## 9. Symptom-Based Diagnosis

| Symptom | Check first |
| --- | --- |
| `/actuator/health` has data yet `/liveness` or `/readiness` returns 404 | Are probes enabled; does the URL include `/actuator/health/`; was base path changed? |
| 401, 403, or redirect | Spring Security rules, proxy authentication, and additional paths on the main port. |
| `Connection refused` | Has the process opened the port; wrong port or bind address; calling main or management port? |
| 503 with `OUT_OF_SERVICE` on readiness | Is startup finished; did the lab tool leave `REFUSING_TRAFFIC`; did an added member fail? |
| Replica keeps restarting continuously | Probe events, startup budget, CPU/timeouts, whether liveness accidentally depends on an external system. |
| Management 9090 succeeds while API 8080 fails | Are probes going through the main port via `/livez` and `/readyz`? |
| Fails to start after adding a group member | Does the check name exist in the current configuration/dependencies? |

When a real Deployment already exists, use the following commands to inspect state and events; replace the label selector with the actual label if the application name differs:

```bash
kubectl get pods -l app=probe-demo
kubectl describe pods -l app=probe-demo
kubectl logs -l app=probe-demo --all-containers=true --tail=100
```

Distinguish `Running` from `Ready`: a container can be running while not ready to accept requests. Read both restart counts and probe messages. Do not simply raise timeouts before verifying HTTP codes, ports, and addresses.

## 10. Practice Confirming the Contract with Infrastructure

1. Run the sample with the `probe-lab` profile. Record HTTP codes and bodies for both groups during normal operation.
2. Call the `refuse` operation; verify readiness is 503 while liveness stays 200. Explain why the Java process keeps running and why `accept` can still be called directly.
3. Call `accept`; verify readiness returns to 200 without restarting.
4. Stop the application, switch to the management 9090 configuration, and re-run. Verify both Actuator addresses and both paths on 8080.
5. In a lab Kubernetes environment, use the chosen paths/ports and observe `Ready` and restart counts. Do not carry lab state-changing tools into a production Deployment.
6. Simulate a controlled slow startup or a wrong path once in a lab environment; read events to distinguish startup failure, HTTP routing error, and not-ready state. Restore the configuration after the test.

The goal is a clear contract: the application publishes two signals with distinct meanings; infrastructure calls the right addresses, ports, and thresholds; failure tests prove the system drains the replica or restarts it in the right situations.
