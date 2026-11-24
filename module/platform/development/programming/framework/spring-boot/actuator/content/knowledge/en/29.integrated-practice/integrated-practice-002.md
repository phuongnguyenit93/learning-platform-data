# Build a health indicator for an external dependency and the right readiness group

A running application is not necessarily ready to accept work. The Java process may be alive and the HTTP port responding, yet the connection to a mandatory service is broken. Conversely, a failing recommendation service does not necessarily require taking the entire application out of service.

This lab builds a health indicator that checks an HTTP dependency, then places its result into the appropriate readiness group. The goal is to produce meaningful operational signals: remove an instance from traffic when needed, without restarting every instance just because an external service is having an outage.

The example uses Spring Boot 3.3.x, Java 17+, and a Servlet application. Decisions about mandatory dependencies, optional dependencies, and degraded serving must be settled before writing configuration.

## 1. Separate three questions before writing code

| Signal | Question to answer | Action typically attached to the signal |
| --- | --- | --- |
| Liveness | Is the process still in a state where it can keep running? | If it fails long enough, the orchestrator may restart the container |
| Readiness | Should this instance receive new requests right now? | If it fails, the orchestrator may stop routing new requests to the instance |
| Aggregated health | What status are registered components reporting? | Diagnostics; not automatically a traffic-routing policy |

**Do not put every external dependency into liveness.** Restarting the application usually does not fix an external service that has lost connectivity. If all instances restart together, the system also loses serving capacity and creates a recovery load spike.

Readiness should not blindly include every dependency either. Consider the impact on serving capability:

| Situation | Decision to consider |
| --- | --- |
| An instance has a local connection misconfiguration or lost its own network path to a mandatory service | Readiness may need to fail to shift traffic to healthy instances |
| The recommendation service fails but core functionality still works | Monitor via health/metrics; usually keep out of readiness |
| Sufficiently fresh cached data or a fallback mechanism meets the contract | Not necessarily necessary to pull the instance; reflect degradation on the appropriate signal |
| Only a small fraction of APIs needs that dependency | Instance-wide readiness may be too broad; consider per-feature or per-route policy |
| Every instance depends on a shared service that is down | Putting that dependency in readiness can pull all instances; you must consciously accept that consequence |

In Boot 3.3.x, default probe groups rely on application liveness and readiness state; external dependencies do not automatically become readiness members. Adding them means the designer is changing operational policy.

## 2. Lab policy

Suppose there is a service dedicated to creating shipments:

- `shipping` is a mandatory shipping provider gateway. Within this assumed scope, the service has no cached data or fallback to finish work when shipping is unavailable.
- `recommendations` provides optional suggestions. Without suggestions, core functionality can still serve requests.
- Liveness depends only on `livenessState`.
- Readiness combines `readinessState` with `shipping`.
- Aggregated health still observes both dependencies.

This is an intentionally illustrative policy. If shipping is a shared service and goes completely down, every instance using this policy can become unready. Users may then receive errors from the routing layer instead of application-controlled business errors. Before applying this, decide which outcome fits the system contract.

Do not use this lab to deduce a rule that “when an external dependency fails, readiness must always be DOWN.”

Check flow:

```text
GET /actuator/health/readiness
    -> read application readinessState
    -> run shipping health indicator
        -> GET shipping /healthz with timeout
    -> aggregate status
    -> map status to HTTP code

GET /actuator/health/liveness
    -> read only livenessState

GET /actuator/health
    -> aggregate registered health contributors
       including shipping and recommendations in the example
```

## 3. Design the dependency check

### 3.1. External endpoint contract

The example defines each dependency's `GET /healthz` contract as follows:

- Returns a 2xx code when the lightweight check succeeds.
- Returns 503 when the dependency does not satisfy that contract.
- Does not create orders, reserve inventory, send emails, or mutate data.
- Small response; this lab does not need to read the body to determine status.

Do not apply a “2xx means healthy” rule to another API if that API returns HTTP 200 with a body like `{"status":"DOWN"}`. You must understand the real contract and inspect the right signal.

Avoid calling another system's aggregated health endpoint without knowing what it contains. An optional component in that system could make its aggregated health DOWN even though the operation your application needs still works. Services calling each other's health endpoints in a cycle can also create recursive check chains.

### 3.2. Distinguish application state from HTTP call results

| External check result | Health indicator in example | Meaning |
| --- | --- | --- |
| HTTP 2xx | UP | Dependency satisfies the check contract |
| HTTP 503 | DOWN | Dependency reports unavailable |
| HTTP 401/403 | DOWN | Application cannot execute the configured check; verify permissions/auth |
| HTTP 404 | DOWN | Possibly wrong URL or wrong endpoint contract |
| Timeout, DNS error, connection or TLS error | DOWN | From this instance, dependency usability cannot be confirmed |
| Any other unacceptable HTTP status | DOWN | Does not satisfy the check contract |

A 401 from the dependency does not become a 401 on readiness. The indicator turns that result into DOWN; the health group then maps DOWN to 503.

DOWN describes an observation from the current instance and check. It does not by itself prove the entire external system is broken.

### 3.3. Choose reasonable timeouts and cost

The example uses a 300 ms connect timeout and a 700 ms read timeout. These values are lab parameters and must be tuned to real latency and the probe budget.

Do not treat `connect timeout + read timeout` as a strict total deadline for every request. DNS, multi-step connection establishment, redirects, and HTTP client characteristics can affect total duration. If a strict total deadline is needed, design and test a mechanism suited to the client in use.

Do not retry multiple times on each probe invocation. Probes are already invoked periodically by the orchestrator; retrying across multiple layers easily amplifies load right when the dependency is weak.

## 4. Build the standalone demo application

Project structure:

```text
dependency-health-lab/
├── pom.xml
├── dependency_stub.py
└── src/main/
    ├── java/demo/health/
    │   ├── DependencyHealthApplication.java
    │   ├── HttpDependencyHealthIndicator.java
    │   └── DependencyHealthConfiguration.java
    └── resources/application.yml
```

Use JDK 17+ and Maven. The dependency stub script uses Python 3 and the standard library. Boot version 3.3.5 is pinned so the example has a concrete environment; choosing a deployment version should follow your own maintenance policy.

### 4.1. Dependencies and startup class

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>dependency-health-lab</artifactId>
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

No extra dependency is needed for the health indicator beyond the Actuator starter. The Web starter provides the HTTP Servlet stack and `RestClient` used in the example.

`src/main/java/demo/health/DependencyHealthApplication.java`:

```java
package demo.health;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DependencyHealthApplication {
    public static void main(String[] args) {
        SpringApplication.run(DependencyHealthApplication.class, args);
    }
}
```

### 4.2. Health indicator

`src/main/java/demo/health/HttpDependencyHealthIndicator.java`:

```java
package demo.health;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

public final class HttpDependencyHealthIndicator implements HealthIndicator {
    private final RestClient client;

    public HttpDependencyHealthIndicator(RestClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            ResponseEntity<Void> response = client.get()
                    .uri("/healthz")
                    .retrieve()
                    .toBodilessEntity();

            int code = response.getStatusCode().value();
            if (response.getStatusCode().is2xxSuccessful()) {
                return Health.up().withDetail("httpStatus", code).build();
            }
            return Health.down()
                    .withDetail("reason", "unexpected-http-status")
                    .withDetail("httpStatus", code)
                    .build();
        } catch (RestClientResponseException ex) {
            return Health.down()
                    .withDetail("reason", "http-error")
                    .withDetail("httpStatus", ex.getStatusCode().value())
                    .build();
        } catch (ResourceAccessException ex) {
            return Health.down()
                    .withDetail("reason", "transport-error")
                    .build();
        } catch (RestClientException ex) {
            return Health.down()
                    .withDetail("reason", "client-error")
                    .build();
        }
    }
}
```

Key points to read from the code:

1. The indicator makes a lightweight GET request, not a business endpoint with side effects.
2. 4xx/5xx responses are converted by `retrieve()` into `RestClientResponseException` under default error handling; the code catches it explicitly to record the HTTP status code.
3. Resource access errors are caught explicitly and mapped to DOWN.
4. Do not put the response body, full URL, credentials, or exception object into details of these error branches.
5. Do not store a “failed” flag inside the object. Subsequent checks re-evaluate so it can automatically return to UP when the dependency recovers.

Do not return UP inside `catch` just to avoid a red probe. Also do not use UNKNOWN as a way to abstain from deciding while still expecting readiness to fail: under default mapping, UNKNOWN returns HTTP 200.

The example handles only expected client errors. Programming bugs outside that scope should be tested and fixed rather than catching every `Throwable` and hiding the root cause.

### 4.3. Register two indicators and configure timeouts

`src/main/java/demo/health/DependencyHealthConfiguration.java`:

```java
package demo.health;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class DependencyHealthConfiguration {
    @Bean
    HealthIndicator shippingHealthIndicator(RestClient.Builder builder,
            @Value("${dependencies.shipping.base-url}") String baseUrl,
            @Value("${dependencies.connect-timeout-ms:300}") int connectTimeoutMs,
            @Value("${dependencies.read-timeout-ms:700}") int readTimeoutMs) {
        return createIndicator(builder, baseUrl, connectTimeoutMs, readTimeoutMs);
    }

    @Bean
    HealthIndicator recommendationsHealthIndicator(RestClient.Builder builder,
            @Value("${dependencies.recommendations.base-url}") String baseUrl,
            @Value("${dependencies.connect-timeout-ms:300}") int connectTimeoutMs,
            @Value("${dependencies.read-timeout-ms:700}") int readTimeoutMs) {
        return createIndicator(builder, baseUrl, connectTimeoutMs, readTimeoutMs);
    }

    private HealthIndicator createIndicator(RestClient.Builder builder,
            String baseUrl, int connectTimeoutMs, int readTimeoutMs) {
        if (connectTimeoutMs < 1 || readTimeoutMs < 1) {
            throw new IllegalArgumentException("Health-check timeouts must be positive");
        }

        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(connectTimeoutMs);
        factory.setReadTimeout(readTimeoutMs);

        RestClient client = builder
                .requestFactory(factory)
                .baseUrl(baseUrl)
                .build();
        return new HttpDependencyHealthIndicator(client);
    }
}
```

`RestClient.Builder` is injected by Boot. The request factory is configured with explicit timeouts; values less than 1 are rejected to avoid accidentally using a 0 timeout meaning unlimited in this client.

Both bean methods use the same indicator class but have separate URLs. The health contributor ID is derived from the bean name:

| Bean name | Contributor ID used in health group |
| --- | --- |
| `shippingHealthIndicator` | `shipping` |
| `recommendationsHealthIndicator` | `recommendations` |

Because the `HealthIndicator` suffix is stripped when determining the ID, the `include` configuration uses `shipping`, not the full `shippingHealthIndicator` name.

If you rename a bean, you must re-check the ID and group configuration. Do not create two differently named beans that accidentally check the exact same URL.

### 4.4. Configure health groups

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080
spring:
  application:
    name: dependency-health-lab
dependencies:
  shipping:
    base-url: http://localhost:9091
  recommendations:
    base-url: http://localhost:9092
  connect-timeout-ms: 300
  read-timeout-ms: 700
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      validate-group-membership: true
      logging:
        slow-indicator-threshold: 2s
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,shipping
```

Meaning of the options:

- `probes.enabled: true` enables probes even when running outside Kubernetes.
- Liveness includes only `livenessState`, not shipping or recommendations.
- Readiness keeps `readinessState` and adds `shipping`. By keeping application state, an application refusing traffic is still reflected even while shipping is UP.
- `recommendations` is excluded from readiness, yet remains a health contributor for diagnostics.
- `validate-group-membership: true` catches nonexistent member IDs at startup. Do not disable this check just to hide a misspelled name.
- `show-details: never` keeps HTTP responses compact and does not expose dependency details.
- `add-additional-paths: true` creates `/livez` and `/readyz` on the main HTTP port.
- `logging.slow-indicator-threshold: 2s` is the threshold for logging a slow-indicator warning. It does not cancel the check, does not replace timeouts, and does not guarantee the endpoint finishes within 2 seconds.

Endpoints to distinguish:

| Endpoint | Scope |
| --- | --- |
| `/actuator/health` | Aggregated health |
| `/actuator/health/liveness` | Liveness group |
| `/actuator/health/readiness` | Readiness group |
| `/livez` | Additional path for liveness on the main port |
| `/readyz` | Additional path for readiness on the main port |

In this example all share port 8080. If `management.server.port` is separated later, the additional paths on the main port route probes through the server handling application traffic, rather than merely confirming the management server responds. They still do not replace business-transaction testing.

## 5. Simulate external dependencies

`dependency_stub.py` is a standalone program:

```python
import argparse
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, required=True)
parser.add_argument("--mode-file", type=Path, required=True)
args = parser.parse_args()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/healthz":
            code = 404
        else:
            try:
                mode = args.mode_file.read_text(encoding="ascii").strip()
            except FileNotFoundError:
                mode = "up"

            if mode == "slow":
                time.sleep(2)
            code = 200 if mode in ("up", "slow") else 503

        try:
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *values):
        pass

print(f"stub listening on 127.0.0.1:{args.port}", flush=True)
ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
```

The script reads the status file on every request:

- `up`: returns HTTP 200.
- `down`: returns HTTP 503.
- `slow`: waits 2 seconds before returning HTTP 200.
- Any other value: returns 503.
- If the status file does not exist yet, the stub defaults to `up`.

Do not use this program as a production health endpoint; it only helps actively trigger failures and recovery in the lab.

### 5.1. Initialize and start the processes

The file-modification commands below use PowerShell and ASCII data so Python reads them consistently.

In the project directory, create the initial states:

```powershell
Set-Content -LiteralPath shipping.mode -Value up -Encoding ascii
Set-Content -LiteralPath recommendations.mode -Value up -Encoding ascii
```

First terminal, still in the project directory:

```powershell
python dependency_stub.py --port 9091 --mode-file shipping.mode
```

First stdout line:

```text
stub listening on 127.0.0.1:9091
```

Second terminal:

```powershell
python dependency_stub.py --port 9092 --mode-file recommendations.mode
```

First stdout line:

```text
stub listening on 127.0.0.1:9092
```

Third terminal, package the application:

```powershell
mvn clean package
```

After a successful build, run:

```powershell
java -jar target/dependency-health-lab-1.0.0.jar
```

Wait for the application to finish starting. Ports 8080, 9091, and 9092 must be free. If you change dependency ports, update the URLs in `application.yml` accordingly.

### 5.2. Verify the initial state

In another terminal:

```powershell
curl.exe -i http://localhost:8080/actuator/health
curl.exe -i http://localhost:8080/actuator/health/liveness
curl.exe -i http://localhost:8080/actuator/health/readiness
curl.exe -i http://localhost:8080/readyz
```

With baseline components such as disk healthy and both stubs in up mode, the endpoints above return HTTP 200 with status UP. Headers such as response timestamps can vary; do not match the entire HTTP stdout as a fixed string.

On Linux/macOS, use `curl` instead of `curl.exe` and write the mode files with the appropriate tool. Keep the values `up`, `down`, `slow` and the working directory consistent with the stubs.

## 6. Run failure and recovery scenarios

Each scenario changes only one condition so the outcome can be explained clearly.

### 6.1. Optional dependency fails

Set recommendations to down:

```powershell
Set-Content -LiteralPath recommendations.mode -Value down -Encoding ascii
curl.exe -i http://localhost:8080/actuator/health
curl.exe -i http://localhost:8080/actuator/health/readiness
curl.exe -i http://localhost:8080/actuator/health/liveness
```

Expectations:

- Aggregated health: DOWN, HTTP 503.
- Readiness: UP, HTTP 200.
- Liveness: UP, HTTP 200.

This is not a contradiction. Aggregated health is reporting a failing component, while readiness is enforcing a different policy: the instance can still serve core functionality.

If `/actuator/health` were used as the readiness probe in this situation, the optional dependency would indirectly pull the instance out of traffic. That is why the exact group endpoint must be chosen.

Restore:

```powershell
Set-Content -LiteralPath recommendations.mode -Value up -Encoding ascii
```

### 6.2. Mandatory dependency fails

```powershell
Set-Content -LiteralPath shipping.mode -Value down -Encoding ascii
curl.exe -i http://localhost:8080/actuator/health/readiness
curl.exe -i http://localhost:8080/actuator/health/liveness
```

Expectations:

- Readiness: DOWN, HTTP 503.
- Liveness: UP, HTTP 200.

Shipping is unavailable so readiness fails under the chosen policy. Liveness does not fail because restarting the application will not resolve shipping.

Restore:

```powershell
Set-Content -LiteralPath shipping.mode -Value up -Encoding ascii
curl.exe -i http://localhost:8080/actuator/health/readiness
```

When the application is still accepting traffic and other conditions are normal, readiness returns to UP/HTTP 200. No Java restart is needed to clear a DOWN flag in the indicator.

### 6.3. Dependency still responds but too slowly

```powershell
Set-Content -LiteralPath shipping.mode -Value slow -Encoding ascii
curl.exe -i http://localhost:8080/actuator/health/readiness
```

The stub intentionally waits 2 seconds before responding, longer than the 700 ms read timeout. For this check, the read error maps to DOWN and readiness returns 503.

That does not mean the dependency will definitely never finish the request. It means the instance did not receive a response within the wait limit configured for the check.

Do not claim total endpoint duration is exactly 700 ms: there is also connection setup, scheduling, and application processing time. Measure real total latency when choosing probe timeouts.

Restore:

```powershell
Set-Content -LiteralPath shipping.mode -Value up -Encoding ascii
```

### 6.4. Dependency stops listening

Stop only the shipping stub process with Ctrl+C in its terminal, then call readiness again. The connection error must map to DOWN/503; liveness remains UP/200.

Restart the shipping stub with the exact same command, ensure the mode file is up, and verify recovery. Do not stop the Java application or the recommendations stub in the same test run, because you would no longer isolate the cause.

### 6.5. Acceptance table

Assuming the application is ready, other baseline components are healthy, and only the conditions in the table change:

| Shipping | Recommendations | Aggregated health | Readiness | Liveness |
| --- | --- | --- | --- | --- |
| UP | UP | UP / 200 | UP / 200 | UP / 200 |
| UP | DOWN | DOWN / 503 | UP / 200 | UP / 200 |
| DOWN | UP | DOWN / 503 | DOWN / 503 | UP / 200 |
| Timeout | UP | DOWN / 503 | DOWN / 503 | UP / 200 |
| Restored UP | UP | UP / 200 | UP / 200 | UP / 200 |

Outside this table, when the application state is `ReadinessState.REFUSING_TRAFFIC`, the `readinessState` member reports OUT_OF_SERVICE. If shipping is UP and there is no higher-severity failure status in the group, readiness remains OUT_OF_SERVICE/503. A healthy dependency must not make an application that is refusing work become ready.

## 7. Connect to orchestrator probes

The following YAML block sits inside a container element of a PodSpec; this is not a complete Deployment file:

```yaml
ports:
  - name: http
    containerPort: 8080

startupProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 2
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
  successThreshold: 2
```

Operational meaning:

- The startup probe gives the application a startup window before liveness/readiness are evaluated. It does not replace the readiness policy.
- Liveness continues to check only the application's liveness.
- Readiness requires consecutive failures up to the threshold before being marked unready; the success threshold helps reduce flapping during recovery.
- The probe timeout must leave headroom over the actual total health endpoint duration. The illustrative 2-second value must be re-measured under real load and network conditions.

Do not calculate instance removal time using an exact formula of `periodSeconds × failureThreshold`. Probe start timing, per-call latency, and routing propagation all have an effect.

Readiness failure does not kill the process or cancel in-flight requests by itself. The orchestrator updates traffic routing state; handling in-flight requests and graceful shutdown must be designed separately. Conversely, liveness failure can lead to a restart once the threshold is reached.

If the application uses a separate management port, choose the probe path and port intentionally. A healthy management port does not guarantee the business port is accepting connections.

## 8. Refinements needed before production

### 8.1. Do not turn probes into outage-inducing load

In the example, every read of a group containing shipping executes the shipping check. When orchestrators, monitoring tools, and operational utilities call health simultaneously, total request rate can be higher than expected.

Evaluate:

- Number of instances and number of callers hitting the probe.
- Cost of the check, connection limits, and latency when the dependency is degraded.
- Whether short-lived result caching or background checking is needed.
- If cached results are used, the last check timestamp and acceptable staleness limit.

Do not return UP indefinitely from a stale successful result. When adding caching or background checks, define an expiration policy for overdue checks, prevent concurrent probes from triggering duplicate fresh checks (stampede), and test recovery.

A lightweight check is also only a point-in-time measurement. It does not guarantee a business request immediately afterward will succeed. Business code still needs its own timeouts, error handling, and recovery mechanisms.

### 8.2. Preserve status and HTTP code semantics

Under the health endpoint's default mapping:

| Status | Default HTTP code |
| --- | --- |
| UP | 200 |
| DOWN | 503 |
| OUT_OF_SERVICE | 503 |
| UNKNOWN | 200 |

Therefore, choosing UNKNOWN for a mandatory failure can allow the probe to keep passing. If designing custom statuses, consider both status aggregation order and HTTP mapping.

When declaring custom HTTP mappings, maintain clear desired behavior for DOWN and OUT_OF_SERVICE; do not assume all default mappings remain preserved after customization. Do not change DOWN to HTTP 200 just to stop the orchestrator from reporting failures.

### 8.3. Protect details while keeping probes working

This lab's configuration exposes only the health endpoint and hides details. If details need to be inspected, use an authorized mechanism in the appropriate environment; do not expose internal URLs, credentials, tokens, or provider error payloads.

The sample application does not add Spring Security. When integrating into an application with a `SecurityFilterChain`, test the exact probe paths in use. A 401/403 response from the security layer or a login page redirect is not a passing health result. Do not open all Actuator endpoints just to fix access to `/livez` and `/readyz`.

In the example, expected error branches record only the HTTP status code or a bounded reason name. That helps ensure controlled enabling of details does not accidentally expose the dependency's full response body.

### 8.4. Application state must still have a say

Do not replace `readinessState,shipping` with just `shipping` without considering the consequences. While the application is starting, stopping, or explicitly refusing work, shipping being UP is not enough to confirm the instance is ready.

Do not actively publish `LivenessState.BROKEN` just because an external dependency returns 503. Keep dependency evaluation in the chosen readiness policy or diagnostic signal.

If actively controlling `ReadinessState` via availability events, define which component is responsible for changing state and when it is allowed to recover. Avoid letting a dependency-check task overwrite a traffic-refusal decision made during application shutdown.

### 8.5. For reactive applications

Do not place the example's blocking HTTP call on a WebFlux event loop thread. In reactive applications, prefer `ReactiveHealthIndicator`, a client such as `WebClient`, and timeouts within the reactive pipeline.

Do not call `block()` on an event loop thread to reuse this indicator verbatim. If blocking code must be integrated, run it via an appropriate mechanism and test resource limits. Liveness/readiness membership policy still needs to be decided just as in a Servlet application.

## 9. Verification checklist and follow-up exercise

A complete verification must cover both the indicator code and the group policy:

1. Valid HTTP 2xx makes the indicator UP.
2. HTTP 503 and dependency authentication errors make the indicator DOWN.
3. Connection errors and read timeouts map to the appropriate health result.
4. After a failure, the next successful check recovers.
5. Contributor IDs match group configuration and misspelled names are caught at startup.
6. Optional dependency DOWN does not fail readiness.
7. Mandatory dependency DOWN makes readiness return 503 without failing liveness.
8. `readinessState` refusing traffic still takes effect when the external dependency is UP.
9. Total endpoint latency fits within the measured budget; slow indicators are not confused with timeouts.
10. Actual probe paths use the right port, right access permissions, and do not leak sensitive data.

Mock HTTP tests are useful to confirm error mapping, recovery, health groups, and HTTP codes. They do not by themselves prove connect/read timeouts over a real network; slow responses, dropped connections, and DNS issues must be tested separately in a controlled environment.

Follow-up exercise: replace the assumption “shipping is mandatory with no fallback” with a scenario where the application has cached data fresh enough to serve requests. Rewrite the readiness decision first, stating staleness limits and conditions under which traffic must stop, before editing configuration or code. Do not just delete shipping from the group to make the probe green.

A health indicator provides a bounded observation. Readiness turns that observation into a traffic-routing decision; liveness decides whether a restart could help. Keeping those three roles distinct is what makes probes useful during an incident.
