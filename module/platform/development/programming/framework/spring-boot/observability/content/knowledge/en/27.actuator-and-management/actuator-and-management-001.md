# Spring Boot Actuator

In the **Actuator and Management** chapter of the **SPRING_BOOT_OBSERVABILITY** module, Spring Boot Actuator provides management and monitoring features for running applications. Actuator exposes endpoints to inspect health, metrics, application info, configuration, and runtime state. When combined with Micrometer Observation and Micrometer Tracing, Actuator becomes an essential part of inspecting logs, metrics, traces, and service health in real-world environments.

Actuator is not just a set of URLs to open up to the internet. Each endpoint has a different purpose, sensitivity level, and protection requirement. Some endpoints are suitable for health probes, some are intended for privileged operators, while endpoints that modify configuration or display the environment need strict restrictions. It is important to distinguish between an endpoint being **enabled**, **exposed** over HTTP/JMX, and **authorized** by security policy.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Explain the role of Spring Boot Actuator in application operations.
2. Distinguish between endpoint enablement, exposure, and authorization.
3. Configure HTTP/JMX exposure following the principle of least privilege.
4. Use the health, info, metrics, and prometheus endpoints.
5. Understand the risks of env, configprops, loggers, threaddump, and heapdump.
6. Configure management port, base path, and network boundary.
7. Configure liveness/readiness health groups for deployment platforms.
8. Connect Actuator with Micrometer metrics, Observation, and tracing.
9. Write tests for health status, endpoint exposure, and security.
10. Build a runbook for health probe failures, missing metrics, and management access issues.

## 2. What Is Actuator?

Spring Boot Actuator provides production-ready features to monitor and manage applications. Actuator integrates with the ApplicationContext and framework components to expose information via endpoints.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Spring Boot dependency management selects compatible versions. Do not add a separate version manually if the project uses the Boot BOM/parent.

After adding the starter, endpoints can be auto-configured depending on dependencies, environment, and version. By default, only a few endpoints are exposed over HTTP; this does not mean all endpoints are public or all information is accessible.

~~~mermaid
flowchart TD
    App["Spring Boot application"]
    App --> Actuator["Spring Boot Actuator"]
    Actuator --> Health["Health endpoints"]
    Actuator --> Metrics["Micrometer metrics"]
    Actuator --> Info["Application info"]
    Actuator --> Runtime["Runtime diagnostics"]
    Metrics --> Registry["MeterRegistry"]
    Registry --> Backend["Prometheus / metrics backend"]
    App --> Obs["Observation / Tracing"]
    Obs --> TraceBackend["Trace backend"]
    App --> Logs["Logging pipeline"]
    Logs --> LogBackend["Log backend"]
~~~

Actuator provides an interface for accessing health and metrics within the application. It does not replace a metrics backend, tracing exporter, or log storage. These signals have separate pipelines but can share the same service identity to support correlation.

## 3. Endpoint Enablement, Exposure, and Authorization

Three concepts must be distinguished:

| Concept | Question | Example |
| --- | --- | --- |
| Enablement | Is the endpoint created/allowed to operate? | management.endpoint.health.enabled=true |
| Exposure | Which transport makes the endpoint accessible? | HTTP or JMX. |
| Authorization | Does the caller have permission to access the endpoint? | Spring Security role/operator. |

An endpoint can be enabled without being exposed over HTTP. An exposed endpoint can still be blocked by the security layer. Therefore, configuring an endpoint to be exposed does not mean everyone is allowed to access it.

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Only expose the endpoints needed for monitoring. Avoid wildcard configurations in production unless there is a verified security boundary and threat model.

Specific endpoints can be excluded:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
        exclude: env,configprops,heapdump,threaddump
~~~

The endpoint list and property semantics can change across versions. Check the reference docs for the Spring Boot minor version in use.

## 4. Health Endpoint

/actuator/health provides overall status and can aggregate health indicators from the application, database, disk space, broker, or other dependencies.

~~~http
GET /actuator/health
~~~

Example response:

~~~json
{
  "status": "UP"
}
~~~

When displaying components/details is allowed, the response can include detailed information:

~~~json
{
  "status": "UP",
  "components": {
    "db": { "status": "UP" },
    "diskSpace": { "status": "UP" },
    "ping": { "status": "UP" }
  }
}
~~~

Do not expose health details publicly if they reveal topology, database types, dependency names, or internal information. Use an appropriate role for operators to view details; health probes may only need status.

### Readiness and Liveness

Spring Boot supports health groups for liveness and readiness:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
        liveness:
          include: livenessState
~~~

The include configuration is only an example; whether to include the database in readiness depends on the architecture. If a temporary database disconnection causes all replicas to be marked unready, traffic may be drained from the entire service even when the application can still handle some other requests. Do not include external dependencies in liveness: liveness should reflect whether the process needs a restart, avoiding restart loops caused by dependency outages.

- **Liveness**: Is the process still alive and able to keep running?
- **Readiness**: Is the instance ready to receive traffic?
- **Startup probe**: Intended for platforms that need a long startup time before applying liveness.

Kubernetes or the deployment platform can call these health group endpoints. Ensure the probe path, port, and access policy match the cluster configuration.

## 5. Info Endpoint

/actuator/info provides application information configured via InfoContributor, build metadata, git metadata, or custom contributors.

~~~http
GET /actuator/info
~~~

~~~yaml
info:
  app:
    name: order-service
    description: Order processing API
    version: 2.4.0
~~~

Do not put secrets, environment variables, private repository URLs, or sensitive information into info. Version/build metadata should be useful for operations without revealing unnecessary internal details.

## 6. Metrics and Prometheus Endpoints

The Actuator metrics endpoint allows viewing registered meters:

~~~http
GET /actuator/metrics
GET /actuator/metrics/http.server.requests
~~~

The endpoint can return measurements and available tag values. It is suitable for debugging meters in a single instance; a metrics backend is suitable for storing, aggregating, and querying over time.

If using the Prometheus registry, add the dependency:

~~~groovy
dependencies {
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

The Prometheus scrape endpoint is typically:

~~~http
GET /actuator/prometheus
~~~

The Prometheus server scrapes the URL of each instance or service discovery target. Protect the endpoint from unauthorized access; metrics can reveal service names, routes, dependencies, and internal activity.

Metrics are not traces. /actuator/metrics is not the place to view distributed traces. A separate tracing bridge/exporter and trace backend are needed to query spans.

## 7. Runtime and Diagnostics Endpoints

| Endpoint | Purpose | Risks/Notes |
| --- | --- | --- |
| env | View Environment properties. | May leak configuration and secrets if sanitization/access is misconfigured. |
| configprops | View bound configuration properties. | May leak sensitive configuration; requires sanitization. |
| loggers | View/change logging levels at runtime. | May increase log volume or enable logging of sensitive data. |
| threaddump | Capture thread state/stacks. | May expose class names, arguments, or internal contents; large payload. |
| heapdump | Generate a heap dump. | May contain secrets, tokens, PII, and in-memory data. |
| conditions | View auto-configuration conditions. | Reveals application structure and dependencies. |
| beans | List Spring beans. | Reveals internal application context. |
| mappings | List handler mappings. | Reveals API routes. |
| scheduledtasks | List scheduled tasks. | Reveals job names and execution schedules. |

Do not expose these endpoints broadly. Heap dumps are especially sensitive: treat dump files as confidential production data, and restrict storage location, retention time, and who can download them.

### Loggers Endpoint

/actuator/loggers can view logger levels and, in some configurations, allow changing log levels at runtime. If an operator increases DEBUG/TRACE for investigation, there must be a dedicated authorization role, auditing of logger level changes, an enablement duration and rollback procedure, output review to avoid secrets/PII, and limits on log volume/storage.

## 8. Management Port and Base Path

By default, Actuator web endpoints are typically served on the same application port under the base path /actuator. This can be changed:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
~~~

A separate management port can be used:

~~~yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
~~~

This example is only suitable when the process and monitoring agent can access loopback. In containers/Kubernetes, binding to loopback can prevent probes from the node or sidecar from reaching it. Choose the address/interface according to your network architecture.

A separate management port can create a separate management web server context with differences in SSL, base path, and security. Do not assume a management port is automatically secure: firewall, network policy, authentication, and authorization are still required.

When the health endpoint runs on the management port, probes must call the right port/path. If the management context fails to start or is blocked by a firewall, the platform may mark the instance unhealthy even while the application port is still handling requests. Test from the exact network namespace/agent that will be used in production.

## 9. Protecting Actuator with Spring Security

In production, only expose necessary endpoints and protect them with Spring Security or network-level controls. Example SecurityFilterChain:

~~~java
@Configuration(proxyBeanMethods = false)
class ActuatorSecurityConfiguration {

    @Bean
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(EndpointRequest.to("health", "info"))
                        .permitAll()
                        .anyRequest().hasRole("OPS"))
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

This is an illustrative example for applications with appropriate authentication. If health details contain internal information, a separate role may be needed for details. If the application already has other security chains, check the order and matcher to prevent the Actuator chain from accidentally capturing all requests.

Principles:
- Only open minimal health status for probes.
- Metrics/prometheus only for authorized monitoring systems.
- env/configprops/heapdump/threaddump/loggers only for privileged operators with auditing.
- Use TLS when traversing untrusted networks.
- Do not embed credentials in URLs or script logs.
- Apply network policy/firewall alongside application authorization.

## 10. Health Contributors and Custom Health Indicators

Applications can add a HealthIndicator to check a specific dependency or subsystem:

~~~java
@Component
class SearchHealthIndicator implements HealthIndicator {

    private final SearchClient searchClient;

    SearchHealthIndicator(SearchClient searchClient) {
        this.searchClient = searchClient;
    }

    @Override
    public Health health() {
        try {
            searchClient.ping();
            return Health.up().withDetail("service", "search").build();
        } catch (Exception ex) {
            return Health.down()
                    .withDetail("service", "search")
                    .withDetail("error", ex.getClass().getSimpleName())
                    .build();
        }
    }
}
~~~

A health check should have a short, explicit timeout, avoid heavy queries/data scans, not return credentials or full exception messages, distinguish readiness/liveness, and avoid cascading failures during dependency outages.

A health check calling numerous downstream services every second can worsen an incident. Use lightweight pings/caching or client-managed health signals when appropriate.

## 11. Metrics, Tracing, and Actuator Integration

~~~mermaid
flowchart LR
    App["Spring Boot"]
    App --> Actuator["Actuator endpoints"]
    App --> Metrics["Micrometer meters"]
    App --> Obs["Observation / Tracing"]
    Metrics --> Registry["MeterRegistry"]
    Registry --> MetricsBackend["Prometheus / metrics backend"]
    Obs --> TraceExporter["Tracing exporter"]
    TraceExporter --> TraceBackend["OTLP / Zipkin backend"]
    Actuator --> Operator["Authorized operator / probe"]
~~~

Points to remember:
- Exposing /actuator/metrics does not automatically enable an exporter.
- Having /actuator/prometheus requires the Prometheus registry dependency.
- Having trace spans requires a tracing bridge/exporter and appropriate sampling.
- Health UP does not guarantee every business operation is working.
- A metric missing from Actuator may be because the meter has not been created yet, a registry filter, or endpoint access; it is not necessarily due to the exporter backend.

## 12. Production Reference Configuration

~~~yaml
management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
  server:
    port: 9091
~~~

This configuration assumes security/network policy already protects the management port. Do not use show-details: always on a public endpoint. For Prometheus, only allow trusted scrape targets to access it. If you want to use the metrics endpoint internally for debugging, consider controlled exposure rather than opening everything.

~~~yaml
info:
  app:
    name: order-service
    version: "2.4.0"
    environment: production
~~~

Do not put secrets or environment dumps into info.

## 13. Testing Actuator Endpoints

You can use Spring Boot tests and MockMvc to verify endpoints:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ActuatorEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void healthEndpointIsAvailable() throws Exception {
        mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}
~~~

Tests need the application's actual security configuration and endpoint exposure. If a health indicator reflects a real database or dependency, mock/replace the dependency in tests.

Important tests:
1. Health endpoint returns the right status when dependencies are healthy/unhealthy.
2. Readiness/liveness groups do not pull in unnecessary dependencies.
3. Sensitive endpoints are denied to anonymous/non-operator callers.
4. Prometheus endpoint is only accessible by the monitoring identity.
5. Base path and management port match deployment config.
6. Health details are hidden or only shown when authorized.
7. Loggers endpoint is audited and does not allow unauthorized roles to change levels.
8. Heapdump/threaddump are not exposed outside the operator boundary.

## 14. Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| /actuator/health returns 404 | Health endpoint is not enabled/exposed or base path differs. | Check dependency, endpoint enablement, and base-path. |
| Endpoint enabled but unreachable | Not exposed via HTTP/JMX or blocked by security. | Check exposure and SecurityFilterChain. |
| Prometheus endpoint does not exist | Missing registry dependency or endpoint not exposed. | Check runtime dependency and exposure include. |
| Health DOWN but app still serves requests | Health indicator checks non-essential dependency or readiness/liveness mapping is wrong. | Inspect component details and health group membership. |
| Kubernetes probe fails | Wrong management port/path/address or security policy blocks probe. | Curl from a network context equivalent to the probe. |
| Health details not shown | show-details policy requires authorization. | Check authenticated role and health settings. |
| Metrics endpoint missing meter | Meter not created yet, excluded by filter, or different registry. | Trigger activity, check MeterRegistry and availableTags. |
| Heapdump download denied | Endpoint not enabled/exposed or access policy. | Only enable temporarily for operators per procedure. |
| Cannot connect to Actuator port | Wrong bind address/firewall/network policy. | Check listener and route from the monitoring system. |
| Log level does not change | Security or endpoint exposure; wrong logger name. | Check authorization and logger configuration. |

## 15. Runbook: Actuator Unreachable

1. Confirm the actuator starter is on the runtime classpath.
2. Identify the Boot version and endpoint property semantics.
3. Check the endpoint enabled state.
4. Check HTTP/JMX exposure include/exclude.
5. Confirm base path, management port, and bind address.
6. Check SecurityFilterChain, roles, and authentication.
7. Call the endpoint from the exact network namespace of the probe/monitoring agent.
8. For health failures, inspect component status and readiness/liveness groups.
9. For missing metrics, confirm the meter is created and the registry is not filtering it out.
10. For Prometheus, check the registry dependency, scrape target, and response format.
11. Review audit/logs for access denied or config binding warnings.
12. Only expose diagnostic endpoints temporarily per operator procedure and revoke them after investigation.

## 16. Self-Check Exercises

### Exercise 1 — Endpoint Enablement

You set management.endpoints.web.exposure.include=health,info. Why is /actuator/metrics unreachable?

**Answer:** Metrics is not in the HTTP exposure list. An endpoint can be enabled without being exposed over HTTP.

### Exercise 2 — Health UP

/actuator/health returns UP. Can you conclude all business operations are functioning normally?

**Answer:** No. Health only reflects the configured health indicators. It does not prove every route, queue, query, or business workflow is healthy.

### Exercise 3 — Liveness and Database

The database is temporarily unavailable. Should DB be included in the liveness group so Kubernetes restarts the pod?

**Answer:** Usually no. Liveness should reflect whether the process needs to be restarted; a dependency outage can affect the entire cluster and cause a restart loop. Readiness may be considered depending on service semantics.

### Exercise 4 — Prometheus Endpoint

Actuator has /actuator/metrics but not /actuator/prometheus. What is the common cause?

**Answer:** Missing Prometheus registry dependency or the endpoint is not exposed over HTTP.

### Exercise 5 — Management Port

Actuator runs on port 9091, but the Kubernetes probe calls port 8080. What happens?

**Answer:** The probe calls the wrong port if the endpoints only listen on the management port. Probe port/path must be aligned with the management server config and network policy.

### Exercise 6 — Heapdump

Should heapdump be exposed to all developers for convenient debugging?

**Answer:** No. Heap dumps can contain tokens, passwords, PII, and in-memory data. Only operators with appropriate permissions should access them under a controlled process.

## 17. Deployment Checklist

- [ ] Actuator dependency is managed by the Spring Boot BOM.
- [ ] Endpoint enablement, exposure, and authorization are configured separately.
- [ ] Only expose health/info/metrics/prometheus as needed.
- [ ] Health details are shown only to authorized callers.
- [ ] Liveness does not depend on non-essential external services.
- [ ] Readiness accurately reflects the instance's ability to receive traffic.
- [ ] Management port/base path/bind address match network and probes.
- [ ] env/configprops/heapdump/threaddump/loggers are strictly protected.
- [ ] Prometheus registry dependency and scrape endpoint are verified.
- [ ] Metrics endpoint is protected from unauthorized access.
- [ ] Tracing exporter is configured separately; Actuator does not replace the trace backend.
- [ ] Custom HealthIndicators have timeouts and do not cause cascading failures.
- [ ] SecurityFilterChain has clear role/operator policies.
- [ ] Integration tests verify endpoint status, exposure, and authorization.
- [ ] Auditing is in place for logger level changes and diagnostic access.
- [ ] A runbook and procedure exist to disable temporary exposure after incidents.

**Takeaway:** Spring Boot Actuator provides a management interface for health, metrics, info, and runtime diagnostics. Distinguish between an endpoint being enabled, exposed, and authorized; only open what monitoring/operators genuinely need. Liveness/readiness must reflect deployment semantics, the management port must match network probes, and metrics/traces/logs still require their respective registries/exporters/backends. Protect diagnostic endpoints as part of the production security boundary.