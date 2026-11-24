# Enabling Probes Inside and Outside Kubernetes Environments

## 1. What Problem Do Probes Solve?

A running Java process is not necessarily able to accept requests. Conversely, an application finishing initialization may need more time rather than needing to be restarted. Probes are periodic checks that help infrastructure take the right action for each situation.

In Spring Boot Actuator, distinguish two questions:

| Check | Question to answer | Meaning for infrastructure |
| --- | --- | --- |
| Liveness | Does the internal state allow the application to continue operating or self-recover? | When failures reach the threshold, Kubernetes restarts the container according to the Pod policy. |
| Readiness | Does this indicate the application is ready to receive traffic? | When not ready, Kubernetes removes the Pod from normal Service serving targets; readiness failure alone does not require restarting the container. |

For example, an application running an initial data load can be alive yet not ready. Do not use a single signal for both decisions. Spring Boot exposes application state via `ApplicationAvailability`; Actuator converts those states into health results. [Spring Boot 3.3: Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability)

This lesson uses Spring Boot **3.3.13**, JDK **21**, Spring MVC, and Actuator. URLs assume HTTP, the root context path, and the default Actuator base path. The example intentionally omits Spring Security to focus on verifying probe configuration.

## 2. Distinguishing State, URL, and the Probe Caller

Three layers must work together:

1. **Internal state:** `ApplicationAvailability` holds liveness/readiness states.
2. **HTTP exposure:** Actuator creates the `liveness` and `readiness` health groups and serves them at the corresponding URLs.
3. **Probing and action:** kubelet, a load balancer, or a monitoring system calls the URL and decides what to do when the check fails.

`AvailabilityProbesAutoConfiguration` is the auto-configuration involved in creating the indicators and probe groups in Spring Boot 3.3. Application authors usually only need property configuration rather than writing a controller returning `UP`. [AvailabilityProbesAutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/availability/AvailabilityProbesAutoConfiguration.html)

**Enabling probes in Spring Boot does not automatically create `livenessProbe` or `readinessProbe` in the Pod.** Both sides must be configured. Likewise, running an image with Docker does not turn that environment into Kubernetes.

## 3. Activation Rules in Spring Boot 3.3

The primary property is:

```properties
management.endpoint.health.probes.enabled=true
```

With standard auto-configuration and no user-defined probe groups:

| Environment detected by Spring Boot | Probe property unset | Set to `true` | Set to `false` |
| --- | --- | --- | --- |
| Kubernetes | Automatically enables both probe groups | Explicitly enables | Disables probe auto-configuration |
| Outside Kubernetes: laptop, VM, plain Docker | Does not automatically enable both probe groups | Explicitly enables | Not enabled |

The two default URLs once enabled are `/actuator/health/liveness` and `/actuator/health/readiness`. `/actuator/health` working on its own does not prove both probe groups are enabled. [Spring Boot 3.3: Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)

Spring Boot detects Kubernetes via environment variables of the form `*_SERVICE_HOST` and `*_SERVICE_PORT`. Detection can be overridden with `spring.main.cloud-platform`. A profile name like `k8s`, an image name, or a directory name does not replace this mechanism. [Spring Boot 3.3: Deploying to Kubernetes](https://docs.spring.io/spring-boot/3.3/how-to/deployment/cloud.html#howto.deployment.cloud.kubernetes)

If the goal is simply to have probes in every environment, setting `management.endpoint.health.probes.enabled=true` states the intent directly and avoids relying on platform detection.

Also distinguish these properties:

| Property | Scope of effect |
| --- | --- |
| `management.endpoint.health.enabled` | Enables/disables the health endpoint. |
| `management.endpoints.web.exposure.include` | Selects **endpoint IDs** exposed over HTTP. For probes, ID `health` is required. |
| `management.endpoint.health.probes.enabled` | Enables the two probe groups provided by auto-configuration. |
| `management.endpoint.health.probes.add-additional-paths` | Adds probe paths on the main application port when the probe groups are enabled. |

`liveness` and `readiness` are group names under the `health` endpoint; do not use `include: liveness,readiness` in place of `include: health`. HTTP exposure configuration also does not replace authentication/authorization rules. [Spring Boot 3.3 properties reference](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator)

## 4. Complete Example Running Outside Kubernetes

Create a standalone project with this structure:

```text
probe-demo/
├── pom.xml
└── src/main/
    ├── java/demo/ProbeApplication.java
    └── resources/application.yml
```

Contents of `pom.xml`:

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

    <groupId>demo</groupId>
    <artifactId>probe-demo</artifactId>
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

Contents of `src/main/java/demo/ProbeApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProbeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProbeApplication.class, args);
    }
}
```

Contents of `src/main/resources/application.yml`:

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
```

`spring-boot-starter-web` provides the HTTP server; `spring-boot-starter-actuator` provides management endpoints. Setting `include: health` keeps exposure explicit and intentional; there is no need to expose all endpoints with `"*"`.

From the project directory, using Maven 3.6.3+ and JDK 21:

```shell
mvn package
java -jar target/probe-demo-1.0.0.jar
```

This is a Spring Boot application with dependencies, so use Maven to compile and package; a standalone `javac ProbeApplication.java` command will lack the classpath.

Wait for the application to finish starting, then open another terminal:

```shell
curl -sS http://localhost:8080/actuator/health/liveness
curl -sS http://localhost:8080/actuator/health/readiness
```

Each request returns JSON once the corresponding state is healthy; the body may not end with a trailing newline:

```json
{"status":"UP"}
```

Use `curl -i` if you also want to see the HTTP status code. With the example configuration, the steady-state result after startup is HTTP `200`. During startup, depending on timing, the port may not be open yet or readiness may not be ready; do not mistake a call made too early for a misconfiguration.

## 5. Experiments on Enabling, Disabling, and Platform Detection

Stop the previous process with Ctrl+C and run each case below. Arguments placed **after** the JAR filename are Spring Boot command-line properties and override settings in `application.yml`.

### 5.1. Explicitly Disabling Probes

```shell
java -jar target/probe-demo-1.0.0.jar --management.endpoint.health.probes.enabled=false
```

Once the application is ready, in this example:

- `/actuator/health` still exists.
- `/actuator/health/liveness` and `/actuator/health/readiness` are no longer provided by auto-configuration; requests to them return `404`.
- Disabling probes does not disable the server or the health endpoint.

This outcome assumes no custom group or controller uses those same paths.

### 5.2. Explicitly Enabling Outside Kubernetes

```shell
java -jar target/probe-demo-1.0.0.jar --spring.main.cloud-platform=none --management.endpoint.health.probes.enabled=true
```

Both probe URLs still work. This case proves probes do not strictly depend on Kubernetes.

### 5.3. Testing Auto-Enablement on Kubernetes

To verify **auto-enablement**, remove the `enabled: true` line from `application.yml`, repackage, and run in a Pod that Spring Boot detects as Kubernetes. Do not leave the `true` property set and conclude that detection worked.

You can use the following command to test the platform configuration branch locally after removing the probe property and repackaging:

```shell
java -jar target/probe-demo-1.0.0.jar --spring.main.cloud-platform=kubernetes
```

This is a test **forcing platform detection**; it does not create a cluster, Pod, or kubelet. To simply enable probes during normal local runs, use the probe property rather than forcing full platform detection.

## 6. Configuring Kubernetes to Call Both Probes

The YAML snippet below is **the configuration fragment of a container that already has `name` and `image` in a Pod template**. Merge these keys into the right container; this is not a complete Deployment manifest. The example application listens on port `8080`, uses default paths, and has probes enabled:

```yaml
ports:
  - name: http
    containerPort: 8080

startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 30

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
```

Rationale behind the decisions in the example:

- `startupProbe` allocates a startup budget of roughly `30 × 10 = 300` seconds. Until the startup probe succeeds, kubelet does not run liveness/readiness probes. Once it succeeds, the startup probe finishes its job.
- `livenessProbe` detects conditions requiring a restart after the startup phase.
- `readinessProbe` monitors traffic-receiving readiness throughout serving lifetime.
- `timeoutSeconds` bounds each check's wait time; `failureThreshold` is the consecutive failures required. Durations must be chosen from actual measurements.

Failing readiness does not protect a container from failing liveness. A startup probe prevents restart loops when an application starts slowly. Kubelet evaluates the HTTP status code, not the `"UP"` string in JSON; the HTTP success range for HTTP probes is `200` to below `400`. [Kubernetes: configure liveness, readiness, and startup probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)

Normal HTTP probes target the Pod IP and the specified container port. Probe paths do not need to be exposed via Ingress for kubelet to call them. After deployment, run `kubectl describe pod` with the actual Pod name to inspect failed probe events; hitting the URL from a local machine only verifies part of the path.

## 7. When Actuator Uses a Separate Management Port

Suppose the application serves business traffic on `8080` and Actuator on `8081`. Then the two original probe URLs live on port `8081`. A check on the management port can succeed while the business port can no longer accept connections.

Replace the entire example configuration with:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
```

`add-additional-paths` adds two paths on the main port:

| Path | Port in example | Health group |
| --- | --- | --- |
| `/actuator/health/liveness` | `8081` | `liveness` |
| `/actuator/health/readiness` | `8081` | `readiness` |
| `/livez` | `8080` | `liveness` |
| `/readyz` | `8080` | `readiness` |

The original paths still exist; the additional paths are another way to reach the same health groups. They are not under `/actuator/livez`. The additional-paths property defaults to `false` and does not replace the probe-enabling property. [Spring Boot 3.3 probe properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator)

Verify:

```shell
curl -i http://localhost:8081/actuator/health/liveness
curl -i http://localhost:8081/actuator/health/readiness
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
```

If choosing probes on the main port, change the paths in the Kubernetes snippet to `/livez` for startup/liveness and `/readyz` for readiness; keep `port: http` pointing to `8080`. Do not change the paths while forgetting to update the corresponding port.

Checking via the main port exercises the main HTTP infrastructure. It still does not prove every business API works or every processing flow is healthy.

## 8. Using Probes Outside Kubernetes

Once `management.endpoint.health.probes.enabled=true` is set, systems outside Kubernetes can also call these URLs. Clearly identify which component is responsible for taking action:

| Environment | How can the endpoints be used? | What else must be configured |
| --- | --- | --- |
| Local machine | Call with `curl` to verify status and URL. | No automatic action merely because the endpoint exists. |
| VM with a load balancer | Call readiness to decide whether to include the application instance in the target pool. | Check policy, thresholds, and load balancer behavior. |
| Container run by Docker | Container health check calls an enabled URL. | Check command and restart/handling policy of the container manager. |
| Monitoring system | Collect status, detect outages, and alert. | Separate notification or self-healing mechanisms. |

Example readiness check command for a command runner:

```shell
curl --fail --silent --show-error --max-time 2 http://localhost:8080/actuator/health/readiness
```

This command requires `curl` inside the execution environment itself. When run inside a container, `localhost` refers to that container; when run from the host or another container, the address must match. Do not assume every minimal Java image includes `curl`.

Docker marking a container unhealthy and a system automatically restarting containers are two mechanisms that must be checked separately; do not infer action purely from a status name. Similarly, changing readiness state does not make Spring MVC reject business requests sent straight to the application: the routing component must act on this signal.

## 9. Reading Results and Avoiding False Signals

Once the application has stabilized after startup with default configuration:

| Application state | Corresponding health | Default HTTP code |
| --- | --- | --- |
| `LivenessState.CORRECT` | `UP` | `200` |
| `LivenessState.BROKEN` | `DOWN` | `503` |
| `ReadinessState.ACCEPTING_TRAFFIC` | `UP` | `200` |
| `ReadinessState.REFUSING_TRAFFIC` | `OUT_OF_SERVICE` | `503` |

Spring Boot transitions these states automatically along its lifecycle. After context initialization succeeds, the application can be considered live; readiness is accepted after startup runners complete. A health group can also aggregate additional indicators if configured. [Spring Boot: lifecycle and application availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability)

The HTTP codes above assume health status mappings have not been customized. Do not map `DOWN` or `OUT_OF_SERVICE` to `200` just to make probes pass; doing so deprives infrastructure of failure signals.

Do not mechanically substitute overall aggregated health for liveness: a transient external service outage is not necessarily solved by restarting every application instance. By default, probe groups do not automatically pull in every database, cache, or other service indicator. Adding dependencies to readiness should be based on actual serving capability when that dependency fails. [Spring Boot 3.3: checking external state](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state)

If the application has Spring Security or a proxy, ensure the probe caller receives the actual health response. `401`/`403` may indicate an access-control error; redirecting to a login page can mask the true state. Permit appropriate access only to the chosen probe paths, keep protection policies on other management endpoints, and avoid exposing sensitive health details unnecessarily.

## 10. Layer-by-Layer Diagnosis

| Symptom | Check in order |
| --- | --- |
| `/actuator/health` works, probe URLs return `404` | Version in use; `management.endpoint.health.probes.enabled` property; detected platform; active config/profile. |
| All health URLs return `404` | Are Actuator starter and web server present; is health disabled or excluded from HTTP exposure; did base path/context path/port change? |
| `/actuator/health/readiness` returns `503` | The group is responding; inspect startup progress and readiness state rather than rushing to change the URL. |
| Receiving `401`, `403`, or a login page | Application security rules, proxy, and permissions of the probe caller. |
| Connection refused or timeout | Is the process listening on the port, bind address, correct IP/port, network path, and timeout limit? |
| Works from local machine yet Pod reports probe failure | URL/port in Pod template, HTTP/HTTPS protocol, kubelet reachability to Pod, and Pod events. |
| Actuator on `8081` is fine while main port `8080` is broken | Enable additional paths and configure kubelet to check the main port if appropriate. |
| Application keeps restarting during initialization | Check startup probe, actual initialization duration, and liveness thresholds; failing readiness does not block liveness. |

When diagnosing, record **URL, port, HTTP code, body, and where the request originates**. These facts distinguish probe-group creation errors, endpoint exposure, access control, networking, and application state.

## 11. Verification Practice

1. Run the example outside Kubernetes: both probe URLs return `200` and body `{"status":"UP"}` after startup.
2. Re-run with `--management.endpoint.health.probes.enabled=false`: root health remains, while the two auto-configured group URLs disappear.
3. Re-enable probes with `--spring.main.cloud-platform=none`: verify they still work outside Kubernetes.
4. Move Actuator to `8081`, enable additional paths, and verify all four URLs in the table.
5. In a real Pod, configure startup/liveness/readiness with the exact paths and port. Inspect Pod events to verify kubelet is executing the checks.

Success means you can explain both **why the URL exists** and **who reads the result and acts**, while reproducing the enable/disable cases in your environment.
