# Securing Management Endpoints, Diagnostic Logs, and Dump Data

## 1. Why Must Management Endpoints Be Protected?

Spring Boot Actuator provides endpoints to check health, view metrics, change log levels, and collect diagnostic information. These endpoints aid application operations, but can also reveal internal configuration or alter process behavior.

Endpoints such as `health`, `metrics`, `loggers`, `env`, `configprops`, `threaddump`, and `heapdump` carry different levels of sensitivity. Some return only high-level status; others can expose bean names, configuration, stack traces, in-memory data, or allow changing log levels. Exposing all endpoints on the same network as business APIs lets outsiders gather reconnaissance data for attacks or impose load on the process.

With Spring Boot applications compiled into a **GraalVM Native Image**, an extra verification step is needed: endpoint and diagnostic tool support may differ from the HotSpot JVM. An endpoint appearing in Actuator does not mean every JVM diagnostic capability works identically in a native executable.

This lesson belongs to the **Observability** chapter of the **SPRING_BOOT_NATIVE_IMAGE** module. It focuses on:

- Exposing only the Actuator endpoints that are truly necessary.
- Protecting management endpoints with authentication, authorization, and network restrictions.
- Managing dynamic log levels, sensitive log data, and auditing administrative actions.
- Safely collecting thread dumps, heap dumps, and core dumps.
- Distinguishing JVM diagnostics from Native Image monitoring capabilities.
- Testing security configurations and incident response workflows.

## 2. Classifying Endpoints by Purpose and Sensitivity

Do not treat all Actuator endpoints as a single group with the same risk. Classify them before configuring exposure:

| Endpoint | Purpose | Risks to consider |
| --- | --- | --- |
| `health` | Check application status and health indicators | Health details can reveal dependencies, hosts, or infrastructure status |
| `info` | Display application/build information | Can leak version, commit, service names, or deployment details |
| `metrics` | Read Micrometer measurements | Metric/tag names can expose internal structure; overly broad queries add load |
| `prometheus` | Export metrics for Prometheus | Can expose tags and high cardinality; only needs to be open to scrapers |
| `loggers` | Read or modify logger levels | Authorized callers can enable DEBUG/TRACE, exposing data and increasing log volume |
| `threaddump` | View stack traces, thread states, and locks | Can expose packages, internal endpoints, SQL, or stack data |
| `heapdump` | Create a heap dump | Can contain tokens, passwords, sessions, personal data, and payloads |
| `env` / `configprops` | Inspect environment and configuration properties | Risks leaking secrets, URLs, keys, and security configuration |
| `mappings` / `conditions` / `beans` | Diagnose routes, auto-configuration, and beans | Exposes application structure and active components |
| `shutdown` | Request application shutdown | Impacts availability; usually should not be enabled |

A conservative starting configuration exposes only probe and metrics endpoints:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.endpoint.health.show-details=when-authorized
management.endpoint.health.roles=OPS
management.endpoints.web.base-path=/actuator
```

The `prometheus` endpoint only works when the application has the matching registry, such as the Micrometer Prometheus dependency. If the environment does not use Prometheus, omit it from the list.

Do not use `management.endpoints.web.exposure.include=*` in production. If diagnostic endpoints are needed during an investigation, enable them under strict control, restrict who can access them, and disable them again afterward.

### 2.1. Distinguishing Enabled Endpoints from Exposed Endpoints

Actuator has two layers of control:

- **Endpoint availability/enabled:** whether the endpoint is registered and active in the application context.
- **Web exposure:** whether the endpoint is published over HTTP.

An endpoint can be enabled without being exposed over the web. Conversely, adding an endpoint to the exposure list cannot make a disabled endpoint or one missing dependencies appear automatically.

Keeping these two configuration layers separate shrinks the attack surface. For endpoints only needed via JMX or another admin channel, there is no need to expose them over HTTP.

## 3. Separating the Management Port from the Business API Port

One way to reduce risk is using a dedicated management port:

```properties
server.port=8080

management.server.port=8081
management.endpoints.web.base-path=/actuator
management.endpoints.web.exposure.include=health,info,metrics,prometheus
```

Here, business APIs listen on port 8080 while Actuator HTTP endpoints listen on port 8081. However, **a separate port does not automatically create security**. If port 8081 remains open to the internet or user networks, endpoints can still be accessed.

If management endpoints only serve process agents on the same machine, you can bind to loopback:

```properties
management.server.address=127.0.0.1
```

This option fits when scrapers or admin tools run in the same host/network namespace. In Kubernetes, containers and sidecars can share a network namespace inside the same Pod; scrapers running outside the Pod cannot reach a container's loopback address. When probing or scraping from outside the Pod is needed, bind to an appropriate internal interface and restrict access with NetworkPolicies, firewalls, or a separate Service.

Defense layers should be combined: a separate management port if needed, binding to an internal interface, NetworkPolicies/firewalls, authentication, authorization, TLS or mTLS, and auditing of management actions. Do not use a different port as an excuse to skip authentication; internal networks can still be accessed by compromised workloads or accounts.

## 4. Securing Actuator with Spring Security

When Spring Security is on the classpath, explicitly configure who can access management endpoints. The example below uses the Servlet stack and a dedicated operations role:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ActuatorSecurityConfiguration {

@Bean
@Order(1)
SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
    http
        .securityMatcher(EndpointRequest.toAnyEndpoint())
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().hasRole("OPS")
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
}
```

`EndpointRequest.toAnyEndpoint()` builds a matcher from Actuator endpoint mappings instead of hardcoding individual URLs. The `@Order(1)` chain handles management endpoints first; the application chain serves as the fallback for remaining requests. The example assumes the application already configures an authentication provider or user store and assigns the `OPS` role to operator accounts.

HTTP Basic is only safe over TLS with passwords managed in a secret store. Production setups can use OAuth2 Resource Server, mTLS at ingress, or an internal identity provider. Avoid placing passwords directly in source code or committed configuration files.

### 4.1. Per-Endpoint Authorization

Not every management endpoint needs the same role. You can separate reading health/metrics from modifying log levels or downloading dumps:

- `MONITOR`: read health and metrics.
- `OPS`: read operational info and modify logger levels.
- `DIAGNOSTICS`: generate thread dumps or heap dumps.
- `SECURITY_ADMIN`: access endpoints containing sensitive configuration, if truly required.

When fine-grained policies are needed, use specific request matchers or an authorization manager suited to the endpoints. Check both read and write permissions; the `loggers` endpoint accepts POST requests to modify configuration.

### 4.2. CSRF and State-Changing Endpoints

Spring Security enables CSRF protection by default for many Servlet applications. POST operations such as changing log levels may require a CSRF token. Do not disable CSRF globally just to make an operational command work.

If management endpoints are strictly machine-to-machine, use non-cookie authentication and design a deliberate CSRF policy scoped strictly to the management matcher. If using sessions/cookies in a browser, keep CSRF protection enabled and supply tokens for state-changing actions.

### 4.3. WebFlux Uses Reactive Security

WebFlux applications use `SecurityWebFilterChain` and `ServerHttpSecurity`, not Servlet's `SecurityFilterChain`. Configure the corresponding reactive Actuator matcher, authorization rules, and authentication mechanism on the reactive stack. Do not copy Servlet security beans directly into a reactive application.

## 5. Restricting Health Endpoint Information

The health endpoint is typically required for load balancers, orchestrators, and monitoring. Returning full details to every caller, however, can reveal topology, dependencies, and infrastructure state.

Configuration:

```properties
management.endpoint.health.show-details=when-authorized
management.endpoint.health.roles=OPS
management.endpoint.health.show-components=when-authorized
```

For callers lacking the appropriate role, the endpoint can return only the overall status. Authorized operators see component details.

Spring Boot also supports health groups such as liveness and readiness. In orchestrated environments, you can enable probe endpoints:

```properties
management.endpoint.health.probes.enabled=true
```

Liveness should reflect whether the process needs a restart. Do not include external dependencies such as databases, message brokers, or third-party APIs in liveness if a temporary dependency outage would cause the orchestrator to restart instances en masse. Readiness can reflect whether the application is ready to accept traffic and the dependencies essential for current requests.

## 6. Securing the Loggers Endpoint and Changing Log Levels

Actuator `loggers` lets you inspect active logger levels and change levels at runtime. This helps when you need to enable DEBUG briefly during an investigation.

An endpoint must be exposed over HTTP to have a route. If you need diagnostic endpoints in a dedicated operational profile, configure an explicit list and activate it only alongside prepared security/network policies:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus,loggers,threaddump,heapdump
```

This list is an example for a protected diagnostic profile. Do not add `env`, `configprops`, or wildcards just for convenience; evaluate support for each endpoint on the native runtime before enabling.

Default endpoint examples:

```text
GET  /actuator/loggers/com.example.orders
POST /actuator/loggers/com.example.orders
```

Body to change level:

```json
{
  "configuredLevel": "DEBUG"
}
```

You can reset the level back to INFO after the investigation:

```json
{
  "configuredLevel": "INFO"
}
```

Levels changed via the endpoint usually persist only within the running process; they do not automatically update config files or source configuration and can be lost on restart. To change default levels across deployments, update centralized configuration or environment config through the release process.

Operational procedures should enforce:

- Allowing access only to authenticated operator roles.
- Restricting changes to the specific package/logger under investigation; avoid setting DEBUG on the root logger.
- Writing audit logs recording who made the change, logger name, old/new levels, and timestamp.
- Setting an investigation time window and restoring the level afterward.
- Monitoring log volume, CPU, and latency while DEBUG/TRACE is active.

Never log tokens, passwords, session cookies, authorization headers, or payloads containing personal data simply because DEBUG level is enabled.

## 7. Designing Safe Diagnostic Logs

Logs should answer three questions: which request failed, which component failed, and when. Logs should not become a copy of full requests/responses or runtime configuration.

A structured log event:

```json
{
  "timestamp": "2026-11-23T10:15:30Z",
  "level": "WARN",
  "service": "order-api",
  "traceId": "9c12f7a4...",
  "event": "payment-provider-timeout",
  "provider": "primary",
  "durationMs": 1500
}
```

Principles:

- Use a correlation ID or trace ID to link logs across services.
- Record the event name, service, severity, and necessary duration.
- Redact or omit secrets, tokens, cookies, passwords, and personal data.
- Avoid logging full request bodies, multipart contents, or object dumps.
- Bound log volume and retention; maintain a rotation policy.
- Enforce access control on centralized logs and encrypt at rest/in transit.
- Maintain separate audit logs for configuration changes, dump downloads, and diagnostic data access.

When using MDC in reactive applications, do not assume `ThreadLocal` automatically follows requests across thread switches. Configure context propagation compatible with Reactor/Micrometer and test trace IDs across async branches.

## 8. Thread Dumps: Investigating Threads, Locks, and Deadlocks

A thread dump shows thread states at a point in time, stack traces, wait states, and certain lock details. It helps when an application hangs, latency spikes, thread pools exhaust, or deadlock is suspected.

Actuator provides the `threaddump` endpoint on supported runtimes:

```text
GET /actuator/threaddump
```

When analyzing:

1. Look for threads stuck in `BLOCKED` or prolonged `WAITING` states.
2. Check whether multiple threads are waiting on the same lock or resource.
3. Identify worker pools saturated by a single category of task.
4. Compare multiple thread dumps taken at intervals to distinguish normal waiting from hangs.
5. Correlate timestamps with request latency, metrics, and logs sharing the trace/correlation ID.

A single thread dump is only an instantaneous snapshot; you cannot conclude deadlock or starvation from one stack trace alone. Combine multiple snapshots with thread pool metrics.

Thread dumps can also reveal internal class names, URLs, SQL, filenames, or data on the stack. Restrict access permissions and treat files as sensitive diagnostic data.

## 9. Heap Dumps and Data Leakage Risks

A heap dump captures a representation of in-memory objects at collection time. On the JVM, Actuator provides the `heapdump` endpoint on supported runtimes:

```text
GET /actuator/heapdump
```

Heap dumps can be very large and contain passwords, access tokens, refresh tokens, API keys, sessions, cookies, request/response payloads, personal data, business data, cached objects, and configuration loaded into the process.

Never expose this endpoint on public networks. Only authorized diagnostic roles should be permitted to trigger dumps, with strict controls over storage location, encryption, retention, and download access.

Generating a heap dump can consume CPU, I/O, and disk space; in some cases it also impacts latency or memory pressure. Never trigger dumps continuously in production as a routine health check.

### 9.1. Heap Dump Handling Workflow

1. Confirm the incident warrants a heap dump, such as suspected memory leaks or growing retained objects.
2. Check free disk space and load impact on the instance.
3. Grant temporary diagnostic access to the responder.
4. Capture a dump on one selected instance; avoid dumping all instances simultaneously.
5. Store the file in a dedicated, encrypted location with restricted read access.
6. Analyze with tools compatible with the dump format.
7. Document findings without pasting objects containing secrets into tickets/logs.
8. Delete the file per retention policy and confirm temporary copies are also purged.

Heap dumps are not artifacts to attach freely to issue trackers or send over chat. If sharing is required, sanitize them according to your organization's data security procedures.

## 10. Core Dumps and Native Process Crashes

A native executable is an OS process. When a process crashes due to a native error, segmentation fault, or fatal signal, the OS/container runtime can produce a **core dump**. A core dump differs from a JVM heap dump: it can contain all or part of the process memory image along with registers and debugger information.

Core dumps are valuable when a native process exits abnormally without a Java exception, when a bug occurs in a native library/JNI, when crash analysis requires a debugger and matching symbols, or when runtime stack traces cannot pinpoint the failure site.

Core dumps can also contain secrets and application data. Restrict write permissions, storage paths, retention, encryption, and access controls. Do not enable unbounded core dumps on nodes/containers with small disks.

On Linux, core dump creation also depends on `ulimit`, kernel core patterns, filesystem permissions, and container/orchestrator configuration. Coordinate with platform operations to enable controlled capture and retain matching symbols/build metadata for analysis.

## 11. Diagnostic Differences Between JVM and GraalVM Native Image

Do not assume HotSpot JVM diagnostic tooling is fully available in a native executable. Native Image has its own runtime, memory model, and monitoring capabilities; features must be supported by your GraalVM version and sometimes enabled at build time.

| Capability | JVM HotSpot | GraalVM Native Image |
| --- | --- | --- |
| Actuator health/metrics | Usually supported via Spring and Micrometer | Usually usable if dependencies and native metadata are compatible |
| Dynamic log levels | Managed by Spring Boot logging system | Depends on packaged logging implementation and endpoint |
| Thread dump | Can use Actuator/JVM diagnostic tools | Must verify `ThreadMXBean`/monitoring support of the specific runtime |
| Heap dump | JVM tools and Actuator integration available on supported runtimes | Depends on monitoring feature and how the endpoint generates dumps; do not assume HotSpot MXBean exists |
| JFR/JMX | Depends on JDK/runtime and config | Native Image has its own monitoring features that must be enabled and verified per version |
| Core dump | Can capture JVM process core dumps | Can collect native process core dumps per OS/container |
| `jcmd`, `jmap`, `jstack` | Supported depending on JDK and attach permissions | Do not work identically to HotSpot processes by default |

Some GraalVM Native Image versions support monitoring features such as thread dumps, heap dumps, or JFR when enabled during image creation. An example option might look like:

```text
--enable-monitoring=threaddump,heapdump
```

This example depends on the GraalVM version and distribution. Before adding options, check the feature list supported by your installed `native-image` toolchain. Enabling a monitoring feature also does not automatically guarantee the corresponding Actuator endpoint works: endpoint implementations may rely on JMX/MXBeans or APIs not exposed by the native runtime identically to HotSpot.

For each dump/monitoring feature, build and invoke the endpoint on the actual native executable. If the runtime does not support it, use appropriate diagnostic mechanisms such as process metrics, OS core dumps, structured logs, or tracing instead of relying on an unverified endpoint.

## 12. Collecting Metrics and Logs When Dumps Are Unavailable

In production, many incidents can be isolated without taking a heap dump. Collect low-overhead signals first:

- CPU usage, process RSS, and container memory usage.
- GC or memory metrics provided by the runtime.
- Request rate, error rate, and latency percentiles.
- Thread counts, executor queues, and connection pool usage.
- HTTP client timeouts/retries and database pool metrics.
- Logs carrying correlation IDs and trace IDs.
- Restart counts, exit codes, and container termination reasons.

Native Image has its own runtime and memory manager; available GC types, metrics, and their semantics depend on the GraalVM version, image configuration, and platform. Do not assume heap metrics on native carry the same meaning or metric set as HotSpot JVM. Distinguish heap usage from RSS/container memory: RSS also includes code, native allocations, stacks, and other memory regions.

When suspecting a leak, compare trends over time under equivalent load. A single snapshot showing higher RSS does not prove an object leak. Combine memory metrics, allocation behavior, request patterns, and cgroup limits to find the cause.

## 13. Testing Management Endpoint Security

Do not stop at reviewing configuration files. Test HTTP behavior in a production-like environment.

| Case | Expected outcome |
| --- | --- |
| Unauthenticated caller invokes health | Only defined public info is allowed or returns 401 |
| Regular caller invokes metrics/loggers | Returns 401/403 per policy |
| `MONITOR` role reads metrics | Succeeds if endpoint is exposed |
| `MONITOR` role modifies logger level | Denied if only `OPS` is authorized |
| `OPS` role modifies logger level | Succeeds, is audited, and can be reverted |
| Unauthorized caller invokes heapdump/threaddump | Returns 401/403 |
| Management port accessed from public network | Blocked by firewall/NetworkPolicy |
| Health details requested by user lacking role | Does not return component details |
| Endpoint not in exposure allowlist | Not published over the web |

Example MVC test with `MockMvc`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ActuatorSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void metricsRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/actuator/metrics"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "OPS")
    void opsCanReadMetrics() throws Exception {
        mockMvc.perform(get("/actuator/metrics"))
            .andExpect(status().isOk());
    }
}
```

The example assumes the `metrics` endpoint is exposed and the application uses an authentication entry point returning 401 for anonymous callers. If your actual policy returns 403 or uses OAuth2/mTLS, adjust assertions to match your application's authentication mechanism.

Beyond `MockMvc`, test against the separate management port and from the real network zones. `MockMvc` does not verify firewalls, ingress, TLS termination, or NetworkPolicies.

## 14. Testing on the Native Executable

A native test suite should verify:

1. Only endpoints in the allowlist are exposed.
2. Anonymous callers cannot access endpoints requiring authentication.
3. Appropriate roles can read their corresponding endpoints.
4. Insufficiently privileged roles cannot change log levels or download dumps.
5. Health details are shown only to authorized callers.
6. The `loggers` endpoint modifies levels properly and can be reverted.
7. `threaddump` works if supported by the runtime.
8. `heapdump` works if supported by the runtime and endpoint implementation; generated dump files are in an analyzable format.
9. Core dumps are collected per OS/container policy during a controlled crash test.
10. The native executable does not write secrets or sensitive payloads into diagnostic logs.

During the native build, verify monitoring options were accepted and took effect. Do not infer support merely because an endpoint appears in the Actuator discovery document. Invoke the actual endpoint and inspect content type, file output, size, permissions, and error logs.

For production, rehearse dump procedures in staging or on a canary instance first. Measure dump creation time, file size, CPU, RSS, and impact on request latency. Provision enough disk space and a process to purge files after analysis.

## 15. Incident Response and Dump Data Governance Workflow

A runbook can be structured in sequence:

1. **Detection:** alerts from latency, error rate, memory, CPU, or restart count.
2. **Isolation:** identify service, instance, native image version, timestamp, and trace ID.
3. **Low-overhead collection:** logs, metrics, health, and process/container status.
4. **Deep diagnostics:** thread dumps or heap dumps if supported by runtime and needed.
5. **Crash analysis:** collect core dumps when a native process hits a fatal error.
6. **Data protection:** encrypt, restrict access, write audit entries, and enforce retention.
7. **Analysis:** use tools compatible with the dump format and build symbols.
8. **Remediation:** fix the bug, rebuild the native image, and verify in staging.
9. **Closure:** revert log levels, turn off temporary exposure, and delete expired dumps.

Every dump should carry minimal metadata: service, non-sensitive instance ID, image/build version, timestamp, dump type, requester, ticket/incident reference, and expiration time. Never put secrets or object contents into metadata.

## 16. Lab: Securing Actuator and Rehearsing Diagnostics

**Scenario:** A Spring Boot service runs as a native image in a container. Operations need health and metrics for monitoring; only the `OPS` group may view/change loggers, and only the `DIAGNOSTICS` group may collect dumps.

**Steps:**

1. Add Spring Boot Actuator and expose only `health`, `info`, `metrics`, plus `prometheus` if the registry is present.
2. Configure health details to display only for authorized roles.
3. Separate the management port from the API port if required by architecture.
4. Configure Spring Security matchers for Actuator and role-based authorization.
5. Place the management port behind a firewall/NetworkPolicy; permit access only from scrapers and admin networks.
6. Test `GET` loggers and `POST` level changes using the `OPS` role; audit the action and restore the level.
7. Capture a thread dump on a JVM test instance to practice analyzing thread states and locks.
8. Verify `heapdump`/`threaddump` capabilities on the native executable of your GraalVM version; if unsupported, document the alternative mechanism.
9. Run a controlled crash test in staging to verify core dumps and file storage permissions.
10. Verify dumps are never pushed to public artifact stores; confirm encryption, retention, and deletion.
11. Run anonymous, under-privileged role, and valid-role tests against the native management port.
12. Disable temporary diagnostic endpoints and verify exposure returns to the initial allowlist.

**Success criteria:**

- All Actuator endpoints are never exposed in production.
- Management endpoints enforce authentication, authorization, and network restrictions.
- Health details are hidden from unauthorized callers.
- Log level changes are audited and have a restoration procedure.
- Thread/heap/core dumps are treated as sensitive data with controlled storage.
- Dump/monitoring features are verified on the exact GraalVM Native Image runtime.
- Native integration tests confirm endpoints and policies behave as expected.

## 17. Summary

Actuator provides observability data and management endpoints, but exposure must be restricted strictly to what is needed. Combine endpoint allowlists, dedicated management ports, network policies, TLS, authentication, authorization, and auditing. The `loggers` endpoint must be controlled because it can change log levels; logs must carry correlation IDs without containing secrets or sensitive payloads.

Thread dumps, heap dumps, and core dumps are diagnostic artifacts capable of revealing in-process data. Collect them only when needed, restrict access, encrypt them, and enforce retention. With GraalVM Native Image, verify each monitoring feature on the actual runtime version; never assume HotSpot tools or Actuator dump endpoints behave identically to the JVM. Test both access controls and dump behavior on the native executable so operational runbooks accurately reflect the deployed artifact's capabilities.
