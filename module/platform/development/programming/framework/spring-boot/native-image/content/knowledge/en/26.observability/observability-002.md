# Actuator, Health, and Verifying Application Readiness to Accept Requests

## 1. Why Do You Need a Health Endpoint in Spring Boot Native Image?

An application may have produced a native executable and the process may be running, but that does not prove the application can accept requests. The Spring context may not have finished startup, the HTTP server may not have opened its port yet, migrations may still be running, caches may not be warmed up, or an essential dependency may not be ready.

Spring Boot Actuator provides the `health` endpoint to report the status of the application and the components it checks. Spring Boot also manages two separate availability states:

- **Liveness:** whether the process and its internal state can continue operating or need to be restarted.
- **Readiness:** whether the instance is ready to accept traffic or should temporarily stop receiving requests.

These two states are especially useful when running a Spring Boot Native Image in a container or Kubernetes. Native Image can shorten startup time, but readiness still must accurately reflect when the application finishes its startup work and can serve requests.

After this lesson, you will be able to:

- Enable Actuator and verify the `/actuator/health` endpoint.
- Distinguish between liveness, readiness, and startup probes.
- Configure health groups and a custom `HealthIndicator`.
- Control readiness during warm-up or maintenance.
- Configure Kubernetes probes on the main server port.
- Protect health details and test the endpoints on a native executable/container.

## 2. Adding Spring Boot Actuator

### 2.1. Dependency

With Maven, add the starter to your application:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

With Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Use the version managed by the Spring Boot plugin or BOM. Spring Boot 4.x changes some internal packages and modules in Actuator compared to 3.x, so do not copy `HealthIndicator` imports from a different major version.

### 2.2. Default Health Endpoint

After the application starts, send a request:

```bash
curl -i http://localhost:8080/actuator/health
```

A minimal response typically looks like:

```http
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
```

`UP` means the health contributors included in the overall check are reporting healthy status. If a contributor reports `DOWN` or `OUT_OF_SERVICE`, the default HTTP status typically changes to `503 Service Unavailable`.

By default, Actuator only exposes the `health` endpoint over HTTP. Other endpoints such as `env`, `beans`, `configprops`, `loggers`, or `heapdump` may contain sensitive information and should not be opened indiscriminately.

If you also need to expose `info`, configure the list explicitly:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

### 2.3. Health Response Structure

The health endpoint aggregates status from multiple `HealthContributor` beans, such as database, disk space, Redis, RabbitMQ, or custom indicators.

```json
{
  "status": "UP",
  "components": {
    "db": {
      "status": "UP"
    },
    "diskSpace": {
      "status": "UP"
    },
    "ping": {
      "status": "UP"
    }
  }
}
```

Whether components and `details` appear depends on the `management.endpoint.health.show-components` and `management.endpoint.health.show-details` configuration. By default, details are not publicly shown. The example below illustrates the response when the caller is authorized to view components:

You can query an individual component if that component is permitted to be displayed:

```bash
curl -i http://localhost:8080/actuator/health/db
curl -i http://localhost:8080/actuator/health/diskSpace
```

Component names are typically based on the contributor's bean name. When inspecting a response, distinguish the overall status from the status of an individual component.

## 3. Liveness, Readiness, and Startup Probes

### 3.1. Liveness: Can the Instance Continue Running?

Liveness reflects the internal state of the application. If liveness transitions to `BROKEN`, the deployment platform can restart the container to recover the instance.

A good liveness probe typically checks only the internal conditions necessary for the process to keep functioning. Do not include the database, Redis, message brokers, or external APIs in liveness. If a shared database experiences an outage, having every instance fail liveness simultaneously can cause a restart storm and amplify the incident.

Spring Boot tracks liveness status via `ApplicationAvailability`. Once the `ApplicationContext` has refreshed successfully, the application is considered live. If an internal component breaks unrecoverably, the application can publish an `AvailabilityChangeEvent` to transition to `LivenessState.BROKEN`.

### 3.2. Readiness: Can the Instance Accept Requests Yet?

Readiness indicates whether the deployment platform should route traffic to the instance. When readiness is `REFUSING_TRAFFIC`, Kubernetes removes the instance from endpoints receiving traffic; when it is `ACCEPTING_TRAFFIC`, the instance can receive requests.

By default, Spring Boot transitions readiness to `ACCEPTING_TRAFFIC` after the application context is initialized and `ApplicationRunner`/`CommandLineRunner` beans have completed. This is the right place to perform startup work that must finish before accepting requests.

For example, if the application needs to load a product catalog or warm up a cache before serving requests, you can keep readiness in the refusing-traffic state throughout that process.

### 3.3. Startup Probe: Giving the Application Extra Startup Time

A Kubernetes `startupProbe` protects the application during startup. While the startup probe has not yet succeeded, Kubernetes does not apply the normal liveness/readiness failure thresholds. This is helpful for applications with long startup tasks, even when a native executable starts faster than the JVM.

The three probes serve different roles:

| Probe | Question | On failure |
|---|---|---|
| Startup | Has the application completed its initial startup phase? | Kubernetes keeps waiting within the startup probe limit; restarts if threshold is exceeded |
| Liveness | Can the instance still keep operating? | Kubernetes restarts the container |
| Readiness | Is the instance ready to accept traffic? | Kubernetes temporarily stops routing traffic to the instance |

### 3.4. States Across the Spring Boot Lifecycle

States change across the application lifecycle:

| Phase | Liveness | Readiness | HTTP server |
|---|---|---|---|
| Starting | `BROKEN` | `REFUSING_TRAFFIC` | Not open yet |
| Context refreshed | `CORRECT` | `REFUSING_TRAFFIC` | Not accepting new requests yet |
| Runners complete, app ready | `CORRECT` | `ACCEPTING_TRAFFIC` | Accepting requests |
| Graceful shutdown | `CORRECT` | `REFUSING_TRAFFIC` | Stops accepting new requests, finishes in-flight requests if graceful shutdown is enabled |
| Shutdown complete | No state left | No state left | Closed |

Therefore, you should not use the overall `/actuator/health` endpoint as a readiness probe without checking which contributors are being aggregated. Overall health might report `DOWN` due to an auxiliary service while the instance is still alive and can still serve a subset of requests.

## 4. Enabling Health Groups for Liveness and Readiness

### 4.1. Explicit Configuration

Spring Boot can automatically enable Kubernetes probes when it detects a Kubernetes environment. The default value of `management.endpoint.health.probes.enabled` has changed across Spring Boot versions: some 3.x releases disable it by default outside Kubernetes, whereas newer 4.x releases enable it by default. For consistent configuration across environments, enable it explicitly:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
```

Once enabled, two health groups are exposed under the health endpoint:

```bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
```

By default, the liveness group contains `livenessState` and the readiness group contains `readinessState`. Spring Boot does not automatically add all external health indicators to these two groups.

### 4.2. Why Shouldn't You Bundle Every Indicator Into Readiness?

A shared database might fail while the application can still handle cached read requests or return a temporary notice. If you put the database into readiness for every instance, all instances could be removed from the service at once.

Only add an external dependency to readiness when that dependency is truly required for the instance to accept the traffic it serves. If the application has fallbacks or circuit breakers, an outage in an auxiliary dependency does not necessarily mean the entire instance must stop accepting requests.

Never put external dependencies into liveness. Failed liveness triggers a restart; restarting cannot fix a broken database or external API.

### 4.3. Adding an Indicator to the Readiness Group

Suppose the application needs an inventory gateway to be operational before accepting order creation requests:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,inventoryGateway
```

`inventoryGateway` is the health contributor name. When adding a contributor to a group, ensure the bean actually exists in the `ApplicationContext`. By default, Spring Boot validates health group membership at startup; misspelling a contributor name can cause application startup to fail.

## 5. Writing a Custom `HealthIndicator`

### 5.1. Example Checking a Required Dependency

A custom indicator should check a specific capability with a short timeout and return a clear status:

```java
package com.example.orders.health;

import java.time.Duration;

import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("inventoryGateway")
public class InventoryGatewayHealthIndicator implements HealthIndicator {

    private final InventoryGatewayClient client;

    public InventoryGatewayHealthIndicator(InventoryGatewayClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            client.ping(Duration.ofMillis(300));
            return Health.up().build();
        }
        catch (Exception ex) {
            return Health.down()
                    .withDetail("dependency", "inventory-gateway")
                    .build();
        }
    }
}
```

The example uses the Spring Boot 4.x API. For Spring Boot 3.x, import `Health` and `HealthIndicator` from `org.springframework.boot.actuate.health` instead of `org.springframework.boot.health.contributor`.

`InventoryGatewayClient.ping(...)` is an illustrative client API. In a real application, ensure the HTTP client/database driver timeout is actually configured; merely passing a timeout argument to a method without enforcing a timeout at the transport layer will not protect the probe.

### 5.2. Do Not Turn Probes Into Heavy Business Requests

Health indicators are invoked periodically by monitoring systems and kubelet. An indicator should:

- Perform lightweight checks with short timeouts.
- Not load entire datasets or run expensive queries.
- Not mutate business state.
- Not perform data writes just to prove the system is working.
- Not log errors repeatedly at excessive rates while a dependency is degraded.
- Not return tokens, internal URLs, SQL, stack traces, or credentials in public `details`.

If a probe needs to check multiple dependencies, consider using a periodically updated signal or caching results with a short TTL. A TTL that is too long can cause the probe to keep reporting `UP` even after a dependency just failed; a TTL of 0 can cause every probe invocation to generate an extra request to the dependency. Choose based on probe frequency and the application's fault tolerance.

### 5.3. Reactive Health Indicator

For WebFlux applications or dependencies with reactive APIs, use `ReactiveHealthIndicator` so checks do not block the event loop. Avoid calling blocking JDBC or `Thread.sleep` inside a reactive health check. If you must use a blocking client, run it on an appropriate scheduler and bound the wait time.

## 6. Controlling Readiness During Startup and Warm-Up

### 6.1. Using `ApplicationRunner` for Synchronous Startup Work

Spring Boot only transitions to `ACCEPTING_TRAFFIC` after `ApplicationRunner` and `CommandLineRunner` complete. If the application needs to load business configuration or warm up data before accepting traffic, place that work in a runner rather than spawning an untracked background thread.

```java
package com.example.orders.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class OrderReferenceDataLoader implements ApplicationRunner {

    private final OrderReferenceDataService service;

    public OrderReferenceDataLoader(OrderReferenceDataService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        service.loadRequiredReferenceData();
    }
}
```

If the runner fails with an unhandled exception, Spring Boot can terminate startup. This is usually the right behavior if the application cannot serve requests without the required data.

### 6.2. Keeping Readiness in Refusing-Traffic State During Asynchronous Warm-Up

If warm-up needs to continue after the application context is ready, you can publish an `AvailabilityChangeEvent` to control the state:

```java
package com.example.orders.startup;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class OrderWarmupCoordinator {

    private final ApplicationEventPublisher events;

    public OrderWarmupCoordinator(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void warmupStarted() {
        AvailabilityChangeEvent.publish(
                events, this, ReadinessState.REFUSING_TRAFFIC);
    }

    public void warmupCompleted() {
        AvailabilityChangeEvent.publish(
                events, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
```

Only call `warmupCompleted()` once the data is truly ready. If warm-up fails, stay in the refusing-traffic state and handle the error according to the application's retry or fail-fast policy.

### 6.3. Liveness for Unrecoverable Internal Failures

In case an internal component breaks to the point where the instance can no longer serve requests, you can publish a liveness state:

```java
package com.example.orders.health;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class LocalCacheVerifier {

    private final ApplicationEventPublisher eventPublisher;

    public LocalCacheVerifier(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void checkLocalCache() {
        try {
            // Verify internal cache invariants.
        }
        catch (CacheCompletelyBrokenException ex) {
            AvailabilityChangeEvent.publish(
                    eventPublisher, this, LivenessState.BROKEN);
        }
    }
}
```

Only use `BROKEN` when restarting the instance is a sensible recovery measure. Do not use it to reflect a transient database disconnect, a remote API timeout, or a retryable business error.

## 7. Health Groups and Endpoint Paths on the Main Server Port

### 7.1. Why Can a Separate Management Port Create False Positives?

An application can expose Actuator on a separate port:

```yaml
management:
  server:
    port: 8081
```

In that case, kubelet could call the health endpoint on port `8081` and receive `UP`, while the main HTTP server on port `8080` is not accepting connections. The management context may use different web infrastructure from the main application context, so a probe on the management port does not necessarily prove the request-serving port is working.

### 7.2. Adding `/livez` and `/readyz` on the Main Port

Spring Boot supports adding paths for both health groups on the main server port:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
```

Then:

| Endpoint | Port | Meaning |
|---|---|---|
| `/actuator/health` | Management or main port per configuration | Overall health |
| `/actuator/health/liveness` | Management or main port | Liveness group |
| `/actuator/health/readiness` | Management or main port | Readiness group |
| `/livez` | Main server port | Additional liveness group path |
| `/readyz` | Main server port | Additional readiness group path |

If you do not use a separate management port, the two Actuator group endpoints are usually sufficient. If a separate management port is protected inside an internal network, `/livez` and `/readyz` on the main port help verify the primary HTTP path as well.

### 7.3. Customizing Additional Paths

You can configure an additional path for each health group:

```yaml
management:
  endpoint:
    health:
      group:
        liveness:
          additional-path: "server:/health/live"
        readiness:
          additional-path: "server:/health/ready"
```

The `server:` prefix indicates the main server port; `management:` indicates the management port if configured. When defining custom paths, update the deployment platform's probe configuration accordingly.

## 8. Configuring Kubernetes Probes

### 8.1. Deployment Example

Suppose the native executable listens on port `8080` and uses `/livez` and `/readyz` on the main port:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-service
          image: example/order-service:native
          ports:
            - name: http
              containerPort: 8080
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

These values are examples only. With `periodSeconds: 5` and `failureThreshold: 30`, `startupProbe` allows up to about 150 seconds before the container is considered to have failed startup. Set thresholds based on startup times measured in the deployment environment, not just on a developer machine.

### 8.2. Choosing Endpoints by Port

If Actuator only runs on the management port, configure probes to use the management port. If additional paths are enabled, prefer `/livez` and `/readyz` on the main server port to confirm the traffic-serving HTTP server is also operational.

Do not use the same readiness endpoint for liveness if that endpoint can transition to `DOWN` due to an external dependency. When a database goes down, readiness may transition to failing according to application policy, while liveness should remain `UP` to avoid mass restarts.

## 9. Securing Actuator Health

### 9.1. Keeping Health Details in a Safe Mode

By default, Spring Boot does not expose health details to public requests. You can configure this explicitly:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: OPS
```

Only users with the `OPS` role can view details. Do not set `show-details: always` on an endpoint reachable from public networks if details contain hostnames, databases, clusters, exceptions, or internal information.

### 9.2. Allowing Kubelet to Call Probes

If the application uses Spring Security and declares its own `SecurityFilterChain`, Actuator's default security configuration may no longer apply. You must permit the probe endpoints according to the network architecture and ports in use.

Example rule for probe paths on the main server port:

```java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/livez", "/readyz", "/actuator/health/**").permitAll()
        .anyRequest().authenticated());
```

This is one part of a `SecurityFilterChain` configuration; other endpoints still require their own protection rules. If the management server has a separate port/network, verify the security chain applied to the management context and ensure only kubelet/monitoring can access it.

## 10. What Must Be Checked for Spring AOT and Native Image?

### 10.1. Actuator and Health Indicators Are Spring Beans

Spring AOT analyzes the `ApplicationContext` at build time and generates initialization code along with the required runtime hints. Health indicators auto-configured by Spring Boot and custom indicators declared with `@Component` or `@Bean` can normally be discovered by AOT.

For a static custom `HealthIndicator`, you generally do not need to write reflection hints manually just to invoke `health()`. Add hints if the implementation or an internal library actually uses reflection, resource loading, serialization, JNI, or dynamic proxies that AOT cannot infer.

### 10.2. Configuration Conditions Are Evaluated at Build Time

If a custom health indicator is enabled via `@Profile` or `@ConditionalOnProperty`, that condition may be evaluated when Spring AOT runs. Profiles/properties needed for the native artifact must be supplied during the AOT build. Do not expect enabling a different profile when running the executable to create a bean that was excluded from the bean graph at build time.

### 10.3. Testing Both Native Executable and Container

After building the native image, run the executable directly and test the health endpoints. Then run the container image with the same ports, environment variables, security rules, and database/network setup as the deployment environment.

Points to confirm:

- The Actuator health endpoint is exposed and returns an HTTP response.
- Liveness transitions to `UP` after context refresh.
- Readiness only transitions to `UP` after runners and warm-up finish.
- Custom health indicators appear in the configured group.
- Health indicators enforce timeouts and do not hang probes.
- Additional paths `/livez` and `/readyz` work on the main server port if using a separate management port.
- Probes behave as expected during graceful shutdown.
- No metadata or native libraries are missing when running the native executable.

### 10.4. Manual Verification Commands

```bash
# Overall health
curl -i http://localhost:8080/actuator/health

# Two probe groups
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness

# Additional paths on the main server port
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
```

Run these commands while the application is starting up, after startup, when a critical dependency is disconnected, during warm-up, and during shutdown. Checking only once after startup will miss important lifecycle states.

## 11. Automated Testing

### 11.1. Testing a Custom HealthIndicator

Test the indicator in isolation to verify `UP` and `DOWN` states without rebuilding native every time:

```java
package com.example.orders.health;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.Status;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;

@ExtendWith(MockitoExtension.class)
class InventoryGatewayHealthIndicatorTests {

    @Mock
    InventoryGatewayClient client;

    @InjectMocks
    InventoryGatewayHealthIndicator indicator;

    @Test
    void reportsDownWhenInventoryGatewayIsUnavailable() {
        doThrow(new IllegalStateException("unavailable"))
                .when(client).ping(any(Duration.class));

        Health health = indicator.health();

        assertThat(health.getStatus()).isEqualTo(Status.DOWN);
    }
}
```

This is a unit test for the indicator logic. It does not prove that the Actuator endpoint or security filter exposes the path properly.

### 11.2. Testing the HTTP Health Endpoint

With Spring MVC, you can use `MockMvc` to assert the HTTP status and JSON response:

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderHealthEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesReadinessProbe() throws Exception {
        mockMvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}
```

This test requires the context to have finished startup and readiness to be `ACCEPTING_TRAFFIC`. If the test involves warm-up or mutates availability state, set the expected state before asserting.

### 11.3. Testing Readiness Transitions

Verify at least the following state transitions:

1. Before warm-up finishes: `/readyz` returns a not-ready status.
2. After warm-up finishes: `/readyz` returns `UP`.
3. When an instance's required dependency fails: the readiness group transitions to failing per policy.
4. When a non-essential auxiliary dependency fails: readiness remains `UP` if the application has a fallback.
5. When shutdown begins: readiness stops accepting new traffic.

### 11.4. Native Integration Tests

Keep the bulk of unit/integration tests on the JVM for fast feedback. Select key tests to run against the native executable or native test image, especially:

- Actuator endpoint mapping and JSON serialization.
- Custom `HealthIndicator` implementations depending on libraries with reflection/native integration.
- Security rules for probe endpoints.
- Application availability events and warm-up lifecycle.
- Additional endpoint paths on the main server port.

Native tests or smoke tests after building the image verify behavior in the final executable. JVM tests cannot catch every metadata issue or Native Image runtime difference.

## 12. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `/actuator/health` returns 404 | Missing Actuator dependency, web exposure, or changed base path | Add starter, check `management.endpoints.web.base-path` and exposure |
| `/actuator/health/readiness` returns 404 | Probes not enabled or group not created | Set `management.endpoint.health.probes.enabled=true` |
| `/readyz` returns 404 while `/actuator/health/readiness` works | Additional paths not enabled | Set `add-additional-paths=true` and check the main server port |
| Readiness is `UP` too early | Warm-up runs in background after runners finish without controlling availability | Use a synchronous runner or publish `REFUSING_TRAFFIC` until warm-up finishes |
| Liveness is `DOWN` when database fails | DB/external check was added to liveness | Use only internal state in liveness; move appropriate dependencies to readiness |
| All replicas removed from service when a shared API fails | Readiness depends on a shared external system | Evaluate fallbacks/circuit breakers and include only truly required dependencies in readiness |
| Probe succeeds but main API does not accept requests | Actuator runs on a separate management port | Use additional paths on the main server port or probe the main port directly |
| Health endpoint returns 401/403 | Spring Security blocks kubelet or custom filter chain does not permit the path | Permit the exact probe paths and restrict access via appropriate network/port rules |
| Response leaks hostnames or exceptions | `show-details=always` or custom details are overly verbose | Use `when-authorized`/`never`, strip secrets and sensitive info |
| Health check hangs or is slow | Indicator makes network/database calls without timeout | Configure timeouts on the client and inspect slow indicator logs |
| Custom indicator does not appear in native image | Bean was excluded by AOT conditions or not registered in bean graph | Check profiles/properties at AOT build time and bean registration |
| Health group causes startup failure | `include` contains a non-existent contributor name | Verify bean names and membership; keep validation enabled to catch misconfigurations |

## 13. Lab: Verifying order-service Is Ready to Accept Requests

**Scenario:** `order-service` is built as a GraalVM Native Image and deployed as three replicas on Kubernetes. The service needs to warm up reference data and check the inventory gateway before accepting order creation requests.

### Step 1 — Add Actuator

Add `spring-boot-starter-actuator`, build the application, and confirm `/actuator/health` returns a response.

### Step 2 — Enable Liveness/Readiness Probes

Configure:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: readinessState,inventoryGateway
```

### Step 3 — Create a Custom Indicator

Create `InventoryGatewayHealthIndicator` with a short timeout, register the bean name `inventoryGateway`, and test both `UP` and `DOWN` states.

### Step 4 — Control Warm-Up

Run warm-up inside `ApplicationRunner` if the work must finish before startup readiness. If warm-up runs asynchronously, publish `ReadinessState.REFUSING_TRAFFIC` when starting and `ACCEPTING_TRAFFIC` when finished.

### Step 5 — Configure Kubernetes

Add `startupProbe`, `livenessProbe`, and `readinessProbe` pointing to `/livez` and `/readyz` on the main HTTP port. Set `failureThreshold`, `periodSeconds`, and `timeoutSeconds` based on measured startup time and latency.

### Step 6 — Build and Test Native

Build the native executable/container image. Test against a test database/inventory gateway environment. Verify startup, warm-up, dependency outages, readiness transitions, and graceful shutdown.

### Results Checklist

| Item | Result to record |
|---|---|
| Spring Boot version | _(record)_ |
| Native build tool/version | _(record)_ |
| Actuator health endpoint | PASS/FAIL |
| Liveness group | PASS/FAIL |
| Readiness group | PASS/FAIL |
| Custom indicator | PASS/FAIL |
| Main-port additional paths | PASS/FAIL |
| Security for kubelet probes | PASS/FAIL |
| Native executable/container | PASS/FAIL |
| Readiness after warm-up | PASS/FAIL |
| Readiness when dependency fails | PASS/FAIL |
| Graceful shutdown | PASS/FAIL |

## 14. Key Takeaways

The Actuator health endpoint reports component status; liveness and readiness serve two distinct operational decisions. Liveness answers whether the instance needs a restart, while readiness answers whether traffic should be routed to the instance. The startup probe protects the application during initialization.

With Spring Boot Native Image, Actuator and custom health indicators declared as Spring beans can be processed by Spring AOT. Verify conditions/profiles finalized at build time, ensure probes operate on the right HTTP port, and run smoke/integration tests on the native executable/container. Do not include external dependencies in liveness, include only truly required dependencies in readiness, and keep health details in a safe mode.

### Official References

- [Spring Boot — Actuator Endpoints and Health Information](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot 4.2 — HealthIndicator API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/health/contributor/HealthIndicator.html)
- [Spring Boot 4.2 — ApplicationAvailability API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/availability/ApplicationAvailability.html)
- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html)
- [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html)
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
