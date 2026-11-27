# Exposing Management Endpoints in Spring Boot

Exposing management endpoints is the configuration that determines which Spring Boot Actuator management endpoints are published over HTTP or JMX. This is an important part of observability: health, metrics, Prometheus, and loggers support operations, while diagnostic endpoints can also reveal configuration, environment variables, the bean graph, or allow changing runtime behavior.

In the SPRING_BOOT_OBSERVABILITY module, Actuator provides the management surface to inspect service state and access telemetry. This lesson belongs to the Actuator and Management chapter, focusing on endpoint exposure, enablement, web/JMX, management port/base path, security, Kubernetes probes, testing, and troubleshooting.

## 1. What Is a Management Endpoint?

An Actuator endpoint is an access point that provides management information or operations in a Spring Boot application. Common endpoints include:
- health: status of the application and dependencies.
- info: application information configured to be published.
- metrics: measurements from the Micrometer registry.
- prometheus: metrics exposition for Prometheus when the corresponding registry is present.
- loggers: read or change log levels at runtime.
- env/configprops: configuration information and property binding.
- beans: list of Spring beans.
- threaddump/heapdump: runtime diagnostic data.

Not every endpoint is exposed by default. Spring Boot applies an exposure policy to limit the accessible surface.

### 1.1. Three Concepts to Distinguish

1. **Endpoint enabled:** whether the endpoint is enabled in the application context.
2. **Exposure:** which transport publishes the endpoint, e.g., web or JMX.
3. **Access control:** who can access the endpoint and from which network/interface.

Exposing an endpoint does not mean everyone is allowed to access it if security/network policies are properly configured. An endpoint not exposed over HTTP can still be available over JMX if JMX exposure is enabled.

## 2. Configuring Web Exposure

Spring Boot manages web exposure via the `management.endpoints.web.exposure` property group.

Example exposing only health, info, and metrics:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - metrics
```

If a Prometheus scrape endpoint is needed, add prometheus when the corresponding registry and endpoint are present:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - prometheus
```

Endpoint names are Actuator endpoint IDs, not arbitrary URL names. The default path usually takes the form /actuator/{id}, though the base path and path mappings can be changed.

### 2.1. Excluding Endpoints

An exclude list can be declared:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - "*"
        exclude:
          - env
          - configprops
          - beans
```

Exclude limits which endpoints are exposed over the web when using a broad include. It is better to start with an explicit include allowlist. A wildcard include can accidentally expose new endpoints added in future Spring Boot upgrades.

### 2.2. Wildcards in YAML

The value `*` is a special character in YAML, so it must be quoted:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

Even though wildcard is valid, use it only in controlled test environments. Production should expose only the endpoints actually needed.

## 3. Web Exposure and JMX Exposure

Actuator supports multiple exposure technologies. Web exposure typically serves HTTP; JMX exposure serves management over JMX.

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - prometheus
    jmx:
      exposure:
        include:
          - health
          - metrics
```

An endpoint can be exposed on the web without being exposed over JMX, or vice versa. Check both transports if the application enables JMX. JMX must also be protected at the runtime/network layer.

## 4. Endpoint Enablement and Exposure

Exposure is not the only way to control an endpoint. Some endpoints can be disabled via `management.endpoint.<id>.enabled`; exposure only decides which enabled endpoints are published over a transport.

Example:

```yaml
management:
  endpoint:
    shutdown:
      enabled: false
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
```

A disabled endpoint will not become active just by adding it to include. Default enabled state depends on the endpoint and Spring Boot version. Check the reference documentation for your exact version.

## 5. Common Endpoints in Observability

| Endpoint | Purpose | Notes |
| --- | --- | --- |
| health | Application/dependency status | May contain component details |
| info | Service/build information | Publish only selected fields |
| metrics | Read meter measurements | Per-process diagnostics |
| prometheus | Scrape metrics | Requires Prometheus registry |
| loggers | View/change log levels | Runtime modification |
| threaddump | Thread state diagnostics | Output can be large |
| heapdump | Download heap dump | May contain secrets/PII in memory |
| env | View property sources | Risk of leaking secrets |
| configprops | View bound configuration | Risk of leaking configuration |
| beans | List bean graph | Reveals internal structure |
| mappings | List request mappings | Reveals API surface |
| conditions | Auto-configuration report | Useful for debugging |

Endpoint names and behavior depend on version/dependencies. Expose only the endpoints the operations team actually uses.

## 6. Health Endpoint and Health Details

The health endpoint usually serves orchestration and load balancers. It can aggregate status from the database, broker, disk space, and custom health indicators.

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
  endpoint:
    health:
      show-details: when-authorized
```

Typical values for show-details include never, when-authorized, or always depending on version. Production should restrict details to authorized callers.

### 6.1. Liveness and Readiness

Kubernetes distinguishes:
- **Liveness:** whether the process needs to be restarted.
- **Readiness:** whether the instance is ready to accept traffic.

Spring Boot supports health groups/probes in applicable versions. Exposing health does not automatically guarantee liveness/readiness paths are configured properly. Check health group IDs and deployment probe paths.

### 6.2. Do Not Put Slow Dependencies in Liveness

If liveness depends on a database or broker, a dependency outage can cause Kubernetes to restart application instances en masse. Liveness should reflect the process's ability to keep running; readiness can reflect dependencies required to serve traffic.

## 7. Metrics and Prometheus Exposure

The metrics endpoint allows inspecting meters in the process:

```http
GET /actuator/metrics
GET /actuator/metrics/http.server.requests
```

The Prometheus endpoint is usually exposed separately:

```http
GET /actuator/prometheus
```

For the Prometheus endpoint to work, the application needs the Micrometer Prometheus registry. Simply exposing the `prometheus` ID without the corresponding registry will not produce metrics exposition.

The Actuator metrics endpoint is useful for verifying meters and measurements at the process level. Dashboards, alerting, retention, and historical queries are typically handled by Prometheus or an observability backend.

Metrics can reveal route names, service behavior, traffic volume, and dependency details. Restrict access via network policies, authentication where appropriate, and only to trusted scrapers/operators.

## 8. Loggers Endpoint and Runtime Changes

The loggers endpoint allows reading logger configurations and changing log levels at runtime.

```http
GET /actuator/loggers/com.example.orders
```

```http
POST /actuator/loggers/com.example.orders
Content-Type: application/json

{
  "configuredLevel": "DEBUG"
}
```

Runtime overrides typically exist only in-process and are lost on restart. This endpoint requires strict authorization because DEBUG/TRACE can increase log volume and the risk of leaking data. After investigation, revert the level and record the change.

## 9. Management Port and Base Path

By default, Actuator web endpoints typically reside under the base path /actuator on the same server port. A separate management port can be configured:

```yaml
management:
  server:
    port: 9001
  endpoints:
    web:
      base-path: /manage
      exposure:
        include:
          - health
          - prometheus
```

Endpoints may then reside under /manage instead of /actuator. Exact port/path depends on application configuration.

A separate management port helps isolate management traffic from application traffic, but does not automatically secure endpoints. Binding to the right interface, firewalls/network policies, and authentication/authorization are still needed.

### 9.1. Bind Address and Network Boundary

If the management server binds to all network interfaces, endpoints may be reachable from more network segments than intended. Verify deployment networks, container ports, service definitions, and ingress rules. Do not expose the management port over public ingress without a clear protection architecture.

## 10. Spring Security for Management Endpoints

When Spring Security is present, configure authorization tailored to each endpoint:
- health/info: can allow narrow or public access depending on the returned information.
- prometheus: only authorized scrapers.
- metrics: operator/monitoring identity.
- loggers: operators authorized for runtime changes.
- env/configprops/heapdump: privileged administrative permissions or not exposed.

SecurityFilterChain depends on the application and Spring Security version. Check endpoint paths, management port, and other filter chains before applying matchers.

### 10.1. Authentication and Authorization

Authentication identifies who the caller is. Authorization decides which endpoints the caller may call and which actions they may perform. Having authentication while allowing all authenticated users to call heapdump/loggers is still too permissive.

### 10.2. CSRF and Endpoint Operations

Some Actuator endpoints support POST or modify state. Review CSRF policies and the types of clients accessing them. Do not disable CSRF globally across the application just to call a management endpoint; configure narrow scopes per use case.

## 11. Sensitive Endpoints and Data Exposure

Some endpoints reveal internal information or in-memory data.

Be cautious with:
- env/configprops: property values, endpoint URLs, credentials if redaction is misconfigured.
- heapdump: object graph, tokens, secrets, personal data.
- threaddump: thread names, stack traces, class names, and request context.
- beans/mappings/conditions: application structure and dependency details.
- loggers: ability to change runtime logging.
- shutdown: ability to shut down the application if the endpoint is enabled and exposed.

Do not expose these endpoints publicly. Use allowlists, role-based authorization, network segmentation, and auditing.

## 12. Environment-Specific Configuration

application.yml:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
```

application-local.yml:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - "*"
```

application-prod.yml:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - prometheus
  endpoint:
    health:
      show-details: when-authorized
```

Local environments can expose many endpoints for debugging on a developer machine. Production should publish endpoints needed for health checks and metrics scraping, while diagnostic endpoints are only opened under a controlled procedure.

Do not rely on profile names to protect the network. Deployment configuration and security policies must still be enforced.

## 13. Testing Endpoint Exposure

Tests should verify both exposed endpoints and unexposed endpoints. You can use Spring Boot integration tests with MockMvc or WebTestClient depending on the application stack.

```java
@SpringBootTest
@AutoConfigureMockMvc
class ActuatorExposureTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void healthEndpointIsExposed() throws Exception {
        mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
    }
}
```

This example assumes the default web base path and a security policy allowing the test caller. If the app uses a separate management port or WebFlux, configure the test client accordingly.

### 13.1. Checking Hidden Endpoints

Send requests to endpoints not in the include allowlist and verify they cannot be accessed over the web. The response may be 404 or another status depending on security/routing configuration.

### 13.2. Checking Authorization

Test that callers without the operator role cannot call loggers POST or sensitive endpoints. Callers with the appropriate role can only perform granted operations.

## 14. Troubleshooting Management Endpoint Exposure

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Endpoint returns 404 | Not exposed, endpoint disabled, or different base path | Check include, enabled, and base path |
| Endpoint returns 401 | Not authenticated | Check authentication |
| Endpoint returns 403 | Caller lacks permission | Check authorization/roles |
| prometheus does not exist | Missing registry or not exposed | Check dependency and web exposure |
| Health details do not appear | show-details policy disallows caller | Check health config and role |
| Endpoint works locally but missing in prod | Profile/config override | Check effective properties |
| Management port unreachable | Port not published, bind/network policy | Check container/service/firewall |
| Endpoint unexpectedly public | Overly broad ingress or bind address | Check network path and deployment |
| Endpoint included but inactive | Endpoint disabled or missing dependency | Check endpoint availability |
| JMX accessible even though web hidden | JMX exposure is independent | Check JMX include/exclude |
| Metrics have no data | No meters yet or wrong registry | Generate requests and inspect MeterRegistry |
| Security config not applied | Different filter chain/matcher or separate management context | Check security chains and port |
| Sensitive endpoint leaks info | Broad exposure or overly permissive roles | Narrow allowlist and permissions |

### Investigation Procedure

1. Identify the actual URL, port, and management base path.
2. Check whether the endpoint is enabled.
3. Check web/JMX exposure separately.
4. Check dependencies required by the endpoint, e.g., Prometheus registry.
5. Check authentication and authorization.
6. Check management server bind address, ingress, and network policies.
7. Check profiles and property source precedence.
8. Check whether the endpoint response contains sensitive information.
9. Check startup logs for endpoint mappings.
10. Add integration tests for endpoints that must be exposed and endpoints that must stay hidden.

## 15. Hands-On: Exposing Actuator Safely

The goal is to publish health and metrics for monitoring while restricting diagnostic endpoints.

### Preparation

- Spring Boot application with Actuator.
- Appropriate MeterRegistry.
- Spring Security if authorization is needed.
- Local environment and production-like profile.
- HTTP client or integration tests.

### Step 1 — Expose only health/info

Configure the web exposure allowlist to include health and info. Start the application and verify both endpoints work.

### Step 2 — Expose metrics

Add metrics. Send requests and read http.server.requests via the metrics endpoint.

### Step 3 — Add Prometheus registry

Add the appropriate registry and expose prometheus. Verify the endpoint returns the exposition format.

### Step 4 — Test hidden endpoints

Call env, configprops, heapdump, and loggers when they are not in the allowlist. Verify they cannot be accessed over the web.

### Step 5 — Test separate management port

Configure a separate port/base path. Verify application traffic and management traffic hit the right listeners.

### Step 6 — Configure security

Restrict metrics to scrapers/operators. Restrict loggers to operators authorized to make runtime changes. Verify unauthorized callers receive the expected response.

### Step 7 — Check health details

Set show-details according to authorization. Verify regular callers do not see dependency details and only authorized operators see them.

### Step 8 — Check Kubernetes probes

Configure appropriate liveness/readiness paths and ensure liveness does not mistakenly depend on external dependencies.

### Step 9 — Check network exposure

Verify the management port does not have a public ingress route unless explicitly required with matching protection layers.

### Step 10 — Acceptance

Review allowlist, security, port, path, metrics registry, and endpoint responses. Document which endpoints are intended for scrapers, operators, and health probes.

### Acceptance Checklist

| Item to Prove | Expected Outcome |
| --- | --- |
| Enablement | Know which endpoints are enabled |
| Web exposure | Only allowlisted endpoints are exposed |
| JMX exposure | Separate policy, not confused with web |
| Metrics | Appropriate registry and endpoint |
| Prometheus | Endpoint works when registry is present |
| Security | Role-appropriate authentication/authorization |
| Management port | Bind/path/network controlled |
| Health | Details and probes follow policy |
| Sensitive endpoints | env/heapdump/loggers protected |
| Profiles | Local and production have appropriate exposure |
| Testing | Both required and hidden endpoints are tested |
| Operations | Change and audit process exists |

## 16. Principles to Remember

1. **Enablement, exposure, and authorization are three separate layers.** An enabled endpoint is not necessarily exposed; an exposed endpoint does not mean the caller is authorized.
2. **Prefer an explicit include allowlist.** Wildcards can expose new endpoints during upgrades.
3. **Web and JMX exposure are independent.** Check both transports.
4. **Metrics/Prometheus require the right registry.** Exposing the endpoint ID does not automatically create an exporter.
5. **A separate management port does not secure endpoints by itself.** Network policies, bind address, and security are still required.
6. **Health details must be restricted.** Distinguish liveness from readiness and avoid dependency outages causing restart loops.
7. **Protect sensitive endpoints.** env, configprops, heapdump, threaddump, beans, and loggers can reveal or alter application state.
8. **Authentication does not replace authorization.** Grant permissions per endpoint and specific action.
9. **Verify environment-specific configuration.** Check effective properties and deployment routing.
10. **Test both exposed and hidden endpoints.** Verify responses and caller permissions.

Exposing management endpoints properly lets monitoring and operators access needed signals while limiting the management surface. By distinguishing enablement, transport exposure, and access control, using allowlists, properly isolating the management network, and testing by role, Spring Boot Actuator can support production observability without leaking excessive internal information.