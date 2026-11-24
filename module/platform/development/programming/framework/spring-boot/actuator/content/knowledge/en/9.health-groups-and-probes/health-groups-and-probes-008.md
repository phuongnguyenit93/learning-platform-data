# Exposing Probes on the Main Port with /livez, /readyz, or additional-path

## 1. Why Does the Probe Port Matter?

Suppose an application handles business requests on port `8080`, while Actuator runs on port `8081`. A successful check on `8081` does not prove that connections to `8080` still work. If the main port's connection acceptor runs into trouble, checks going through the management port can miss the problem.

The goal of this lesson is to keep management endpoints on a separate port while exposing both health checks on the application serving port:

- **Liveness:** whether the application instance is still in a state where it can continue operating.
- **Readiness:** whether the application instance is ready to receive traffic.
- **Health group:** a collection of health checks used to compute a health result.
- **Additional path:** another HTTP address to reach the result of the same group.

The two short paths `/livez` and `/readyz` are a convenient way to put probes on the main port. Spring Boot also lets you choose custom names via the `additional-path` property. This is an Actuator exposure feature; there is no need to write a controller returning the string `UP`. See [Spring Boot 3.3 probe documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

## 2. Separating Three Decisions: State, Group, and Address

The processing flow can be read in the following order:

```text
Application state
        ↓
Health check components
        ↓
liveness or readiness group
        ↓
Health result + HTTP status code
        ↓
Path on main port or management port
```

Changing an address does not automatically make an application any readier. Conversely, a properly configured group accessed only on the wrong port can still give inadequate operational evidence.

For the two-port example in this lesson:

| Purpose | Address |
| --- | --- |
| Business request | `http://localhost:8080/hello` |
| Liveness group via Actuator | `http://localhost:8081/actuator/health/liveness` |
| Readiness group via Actuator | `http://localhost:8081/actuator/health/readiness` |
| Liveness on main port | `http://localhost:8080/livez` |
| Readiness on main port | `http://localhost:8080/readyz` |

The last two rows appear only after additional paths are configured. Do not prepend `/actuator` before `/livez` or `/readyz`.

When verifying, record **scheme, host, port, and path**. Recording only "probe returned 200" is not enough to know where the check went.

## 3. Option 1: Enabling the Two Standard Paths

The following configuration targets Spring Boot 3.3.x with Spring MVC and Actuator:

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

Decisions in the configuration:

| Property | Role |
| --- | --- |
| `server.port=8080` | Main application port |
| `management.server.port=8081` | Separates management HTTP to another port |
| `management.endpoints.web.exposure.include=health` | Exposes the `health` endpoint over HTTP |
| `management.endpoint.health.probes.enabled=true` | Enables probe group support even when testing outside Kubernetes |
| `management.endpoint.health.probes.add-additional-paths=true` | Adds `/livez` and `/readyz` on the main port |
| `management.endpoint.health.show-details=never` | Keeps health responses concise without exposing check details |

Do not confuse `enabled` with `add-additional-paths`: one property enables probe support, while the other exposes additional addresses. The fact that a group exists at `/actuator/health/readiness` does not mean `/readyz` exists.

Port separation is configured with `management.server.port`. Changing the endpoint prefix is a different setting using `management.endpoints.web.base-path`; that action does not replace choosing the port for probes. See [management HTTP configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

## 4. Standalone Example for Practice

The example uses Java 17 or later, Maven, and Spring Boot `3.3.13` to pin an illustrative version in the 3.3.x line. No database, Docker, or Spring Security is needed for this practice.

Create the structure:

```text
probe-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── probe/
        │           └── ProbeApplication.java
        └── resources/
            └── application.yml
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

Contents of `src/main/java/example/probe/ProbeApplication.java`:

```java
package example.probe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ProbeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProbeApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "hello";
    }
}
```

Put the YAML from section 3 into `src/main/resources/application.yml`. The `hello()` method merely provides a simple business request to confirm the main port; the probe endpoints are registered by Actuator.

Run in the directory containing `pom.xml`:

```bash
mvn clean package
java -jar target/probe-demo-1.0.0.jar
```

Do not run `javac ProbeApplication.java` on its own: this program requires Spring libraries and Maven packaging. Wait for the application to finish starting, then open another terminal to verify.

### 4.1. Checking the Business Port

```bash
curl -sS -w '\nHTTP %{http_code}\n' http://localhost:8080/hello
```

Expected output:

```text
hello
HTTP 200
```

### 4.2. Checking Probes on the Main Port

```bash
curl -sS -w '\nHTTP %{http_code}\n' http://localhost:8080/livez
curl -sS -w '\nHTTP %{http_code}\n' http://localhost:8080/readyz
```

With the application finished starting and in normal state, each command is expected to return:

```text
{"status":"UP"}
HTTP 200
```

On Windows PowerShell, use `curl.exe` instead of `curl` if `curl` points to another command.

### 4.3. Comparing Against Groups on the Management Port

```bash
curl -sS -w '\nHTTP %{http_code}\n' http://localhost:8081/actuator/health/liveness
curl -sS -w '\nHTTP %{http_code}\n' http://localhost:8081/actuator/health/readiness
```

Under the same steady conditions, each command is also expected to return:

```text
{"status":"UP"}
HTTP 200
```

The additional addresses do not replace these two group addresses. When comparing two consecutive calls, remember that state can change between the two instants; do not demand byte-for-byte identity if the application is transitioning state.

### 4.4. Control Experiment: Disabling Additional Addresses

Stop the process with `Ctrl+C`, then re-run:

```bash
java -jar target/probe-demo-1.0.0.jar --management.endpoint.health.probes.add-additional-paths=false
```

After startup completes:

| Check | Expected result for this exact example |
| --- | --- |
| `8080/hello` | `200`, body `hello` |
| `8081/actuator/health/liveness` | `200`, status `UP` |
| `8081/actuator/health/readiness` | `200`, status `UP` |
| `8080/livez` | `404` |
| `8080/readyz` | `404` |

This experiment distinguishes "probe groups exist" from "groups are additionally exposed on the main port." The condition for this table is that no other controller, filter, or routing rule handles those addresses.

## 5. Option 2: Choosing custom additional-path per Group

If infrastructure mandates custom path names, replace the `management.endpoint.health` configuration from section 3 with:

```yaml
management:
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: false
      group:
        liveness:
          additional-path: "server:/health-live"
        readiness:
          additional-path: "server:/health-ready"
```

This is a **replacement snippet for the corresponding section**; keep `server.port`, `management.server.port`, and exposure settings from section 3. When editing a YAML file, merge under the existing `management` key rather than creating two sibling `management` keys.

Restart and check:

```bash
curl -sS -w '\nHTTP %{http_code}\n' http://localhost:8080/health-live
curl -sS -w '\nHTTP %{http_code}\n' http://localhost:8080/health-ready
```

Under normal state, each command is expected to return `{"status":"UP"}` and `HTTP 200`. In this alternative configuration, the application uses the two new names; do not keep pointing probes at `/livez` and `/readyz`.

### 5.1. Understanding the Prefix and Path Constraints

`additional-path` expresses both **where to expose** and **the path**, not merely a relative URL. Spring Boot has a dedicated type [AdditionalHealthEndpointPath](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/AdditionalHealthEndpointPath.html) for this concept.

| Value | Interpretation |
| --- | --- |
| `server:/health-live` | Exposed at `/health-live` on the main port |
| `management:/health-live` | Exposed at `/health-live` on the management port when a separate port is configured |
| `/health-live` | Missing the prefix selecting where to expose |
| `server:/health/live` | Contains multiple path segments, does not satisfy single-segment constraint |
| `server:http://localhost:8080/health-live` | Confusing path configuration with a full URL |

Choose `server:` when you need to check through the main port. In the two-port example, choosing `management:` still places the check on the management side.

Each group has one `additional-path` property; do not treat it as a comma-separated list of addresses. If standard names suffice, use Option 1. If infrastructure dictates custom names, configure each group explicitly via Option 2 for clarity.

## 6. Putting the Right Addresses into Kubernetes

Below is a **single-container configuration snippet**, not a full Deployment manifest. It uses the standard configuration from section 3:

```yaml
ports:
  - name: http
    containerPort: 8080
  - name: management
    containerPort: 8081

startupProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 30

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
  failureThreshold: 3
```

The name `http` points to port `8080` in the same container spec. If you chose custom paths in section 5, update the paths on all three probes accordingly.

When `startupProbe` is declared, Kubernetes waits for this probe to succeed before running liveness and readiness. Readiness failure makes the Pod unready to receive traffic through the Service; liveness failure reaching the threshold triggers a container restart. Because their consequences differ, do not share one address merely because both currently return `200`. See [Kubernetes probe guide](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

The intervals in the example are starting points for practice; measure your application's startup time and latency to choose suitable values. Do not use very short timeouts to mask a slow check.

## 7. Reading Results Correctly and Handling Common Errors

A probe should provide evidence at both layers:

1. **Connectivity and routing:** right port, right path, right protocol, reaching the application.
2. **Published state:** whether the group result accurately reflects traffic-acceptance or continued-operation conditions.

`/readyz` running over the main port still does not exercise every business API. Thus, this check does not replace functional testing. A controller always returning `200` also does not prove the readiness group is allowing traffic.

| Symptom | Direction to check |
| --- | --- |
| `/actuator/health/readiness` works yet `/readyz` returns `404` | Check `add-additional-paths` and custom group addresses |
| `/livez` returns `404` | Confirm you are calling the main port; check probes are enabled and do not use `/actuator/livez` |
| Neither Actuator groups nor additional addresses are reachable | Confirm Actuator starter is present, `health` endpoint is enabled, and exposed over HTTP |
| Response `401`, `403`, or redirect to login | Check actual Spring Security rules for the exact probe addresses |
| Cannot connect or timed out | Check process, listening port, network, and protocol before reasoning about health status |
| Changed paths in app yet Kubernetes keeps failing | Synchronize `httpGet.path` and `httpGet.port` with the new configuration |
| Management port reports healthy yet users cannot reach main port | Check whether probes actually go through `server:` and the business port |

If the application uses Spring Security, permit the exact addresses the checker needs to call according to your system's access policy. Do not assume a rule matching `/actuator/**` covers `/livez` or `/health-ready`. Keep probe responses minimal and check HTTP status codes too; do not just look for `UP` in the body.

URLs in this lesson assume the root context path, HTTP, and no path-rewriting proxy. When an application has a context path prefix, HTTPS, or proxy routing, verify the actual URL the checker calls; do not copy the lesson's URLs verbatim while ignoring deployment configuration.

## 8. Self-Verification Practice

1. Run the standard configuration; tabulate results for `/hello`, `/livez`, `/readyz`, and both group addresses on the management port.
2. Disable `add-additional-paths`; verify whether the loss affects only the additional addresses or the groups as well.
3. Switch to `server:/health-live` and `server:/health-ready`; update the curl commands and probe configuration.
4. Explain why calling `management:/health-ready` does not fulfill the goal of checking the main port.
5. Confirm there is no controller returning a fake `UP` and no security rule turning probes into login responses.

After this practice, you should be able to state four facts for each probe: **which group is read, which path is exposed, which port is called, and what action occurs on failure**.
