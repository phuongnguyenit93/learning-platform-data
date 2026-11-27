# Configuring the Prometheus Endpoint for Spring Boot

In a production environment, a Spring Boot application needs to expose a metrics endpoint so Prometheus can scrape it periodically. Spring Boot Actuator combined with the Micrometer Prometheus registry creates the `/actuator/prometheus` endpoint, where the application exports meters in a format Prometheus can read. This practice exercise configures the dependencies, endpoint, access control, and scrape job, then verifies that the data appears in Prometheus.

This lesson belongs to the **Integrated Practice** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module guides setting up observability for Spring Boot with Micrometer Observation, metrics, logs, and distributed tracing; including context propagation, tags and cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in live environments. The exercise focuses on the metrics flow from Spring Boot through Actuator to Prometheus.

## 1. Understanding the Scrape Flow

Prometheus typically uses a pull model: Prometheus actively calls the application's HTTP endpoint on a schedule and stores the received samples. The application does not need to push metrics to Prometheus.

```mermaid
flowchart LR
    A[HTTP request to Spring Boot] --> B[Micrometer meters]
    B --> C[PrometheusMeterRegistry]
    C --> D[/actuator/prometheus]
    E[Prometheus server] -->|Periodic HTTP scrape| D
    D -->|Prometheus exposition format| E
    E --> F[PromQL and dashboards]
```

Each component has a distinct responsibility:

- **Spring Boot Actuator:** provides management and observability endpoints for the application.
- **Micrometer:** collects, normalizes, and manages meters such as Counter, Timer, and Gauge.
- **Prometheus registry:** converts meters into the exposition format Prometheus understands.
- **Prometheus server:** scrapes the endpoint, stores time series, and enables querying with PromQL.

The `/actuator/metrics` and `/actuator/prometheus` endpoints serve two different purposes. `/actuator/metrics` inspects meters through the Actuator API; `/actuator/prometheus` exports data in scrape format. Adding Actuator alone without the Prometheus registry is not enough to get the Prometheus endpoint.

## 2. Adding Dependencies

The application requires Actuator and the Micrometer Prometheus registry. Use Spring Boot dependency management to select versions compatible with the running Spring Boot version.

### Gradle

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

### Maven

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

The Prometheus registry is loaded when the application starts. Spring Boot auto-configuration creates the appropriate registry if the dependency is present and not excluded by configuration. Avoid pinning a Micrometer version different from the one managed by Spring Boot unless there is an explicit compatibility reason.

## 3. Configuring the Endpoint in Spring Boot

Declare the application name and expose the Prometheus endpoint in `application.yml`:

```yaml
spring:
  application:
    name: orders-service

management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    tags:
      application: ${spring.application.name}
      environment: ${APP_ENV:local}
```

Explanation:

- `spring.application.name` sets the logical name of the application.
- `management.endpoints.web.exposure.include` allows the `prometheus` endpoint to be accessed over HTTP. The endpoint must be exposed before Prometheus can scrape it.
- `management.metrics.tags` adds common tags to meters for analysis by application and environment.

By default, management endpoints use the `/actuator` base path, so the scrape URL is `http://<host>:<port>/actuator/prometheus`. You can change the base path via `management.endpoints.web.base-path`, but if you do, update `metrics_path` in Prometheus accordingly.

Do not expose all endpoints with `include: "*"` just to enable Prometheus. Management endpoints such as `env`, `configprops`, `beans`, or `heapdump` can reveal sensitive information. Only expose the endpoints you need and apply appropriate security policies.

### 3.1. Distinguishing Expose vs. Enable

Expose controls whether an endpoint is made available over the web transport. Enable controls whether the endpoint itself is turned on. A disabled endpoint will not work even if it is included in the exposure list. The Prometheus endpoint is normally auto-configured when the registry is present; if the project has customized `management.endpoint.*` or disabled endpoints, check that configuration.

### 3.2. Using a Separate Management Port

In a production environment, you can separate management endpoints from the request-serving port:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

When this configuration is active, Prometheus must scrape port `8081`, not application port `8080`. You can combine firewalls, Kubernetes NetworkPolicies, or internal networks so only Prometheus can reach the management port. Bind address and Service settings must fit the runtime environment; do not bind the management port to loopback if Prometheus runs in another container or machine.

## 4. Securing the Prometheus Endpoint

Metrics endpoints can reveal service names, routes, dependency states, and operational details. In production, only allow Prometheus or monitoring systems to access them. You can use a private network, firewall, network policy, reverse proxy, or Spring Security.

If the application uses Spring Security, integrate rules for the scrape endpoint into the existing `SecurityFilterChain`. The following example illustrates an account with a dedicated role for the scraper; adjust matchers and remaining rules according to the application's authentication policy:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/actuator/prometheus").hasRole("METRICS_SCRAPER")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Create scraper credentials using your system's user and secret management mechanism. Never commit production passwords into source code, Git, or container images. If the application uses a separate management port, verify the security matcher configuration and management security context to ensure endpoints on that port are protected as intended.

Prometheus supports Basic Authentication in scrape configs. Example using a secret file mounted into Prometheus:

```yaml
scrape_configs:
  - job_name: orders-service
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["orders-service:8080"]
    basic_auth:
      username: prometheus
      password_file: /etc/prometheus/secrets/orders-service-password
```

The username and password in the example must match the credentials configured in the application. The `password_file` path is inside the Prometheus runtime environment; mount the secret with minimal read permissions. If using a separate management port, change the target to the management port. If the system uses TLS or a reverse proxy, declare the scheme and corresponding authentication settings.

## 5. Configuring the Prometheus Scrape Job

In `prometheus.yml`, declare the target and endpoint path:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: orders-service
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets:
          - orders-service:8080
        labels:
          environment: production
```

`orders-service:8080` is an example of a DNS/service name that Prometheus can resolve within the same deployment network. If Prometheus runs directly on a developer machine and the app runs locally, the target can be `localhost:8080`. If both processes run in separate containers, Prometheus's `localhost` points to the Prometheus container itself; use a service name or address reachable from Prometheus's network.

If the endpoint is protected, add `basic_auth` as shown in the previous section. If using a separate management port, such as `8081`, the target must be `orders-service:8081`. If the base path or endpoint path was customized, update `metrics_path` accordingly.

After changing the configuration, reload Prometheus using your deployment mechanism or restart the process if reload is not enabled. Ensure the YAML is valid before applying it to production.

## 6. Testing and Verifying the Endpoint

Start the application with the profile to be tested. Call the endpoint with `curl`:

```bash
curl -i http://localhost:8080/actuator/prometheus
```

If the endpoint is protected with Basic Authentication, verify with:

```bash
curl -i -u prometheus:"$METRICS_PASSWORD" \
  http://localhost:8080/actuator/prometheus
```

Never pass real passwords directly in commands saved to shell history or shared logs. For production environments, use a secret manager and secure invocation practices following your organization's operational procedures.

When configured properly, the response typically returns HTTP `200` and Prometheus exposition content, for example:

```text
# HELP jvm_memory_used_bytes The amount of used memory
# TYPE jvm_memory_used_bytes gauge
jvm_memory_used_bytes{area="heap",id="...",application="orders-service",environment="production"} ...
```

Actual metric names and tags depend on the version, registry, and registered meters. The example above only illustrates structure; not every application is guaranteed to have those exact labels.

### 6.1. Inspecting Metric Groups

Look for several meter groups commonly present in a Spring Boot application:

- JVM: `jvm_memory_used_bytes`, `jvm_gc_pause_seconds`.
- HTTP server: `http_server_requests_seconds_count`, `http_server_requests_seconds_sum`, and histogram buckets if enabled.
- Process: `process_cpu_usage`, `process_uptime`.
- System: `system_cpu_usage` or corresponding system meters.

Meters may not appear until the corresponding feature is initialized or receives activity. Send a few HTTP requests to generate request meters before concluding that the endpoint is missing data.

## 7. Verifying the Target in Prometheus

Open the Prometheus UI, typically `http://localhost:9090/targets`, and check the `orders-service` job:

- **UP:** the latest scrape succeeded.
- **DOWN:** Prometheus could not connect or the endpoint returned an error; see the error column for details.
- **Target missing:** check `prometheus.yml`, reload, service discovery, and target configuration.

On the query page, run the following queries:

```promql
up{job="orders-service"}
```

A value of `1` means Prometheus scraped the target successfully; `0` means the scrape failed. Next, check a JVM metric:

```promql
jvm_memory_used_bytes{application="orders-service"}
```

After sending requests to the API, check the number of recorded requests:

```promql
sum(rate(http_server_requests_seconds_count{
  application="orders-service"
}[5m]))
```

If the common tag `application` is absent in the data, omit that matcher or use the actual label exported by the endpoint. Metric names and labels must be confirmed from the exposition output before writing dashboards and alerts.

## 8. Adding Common Tags and Controlling Cardinality

Common tags help analyze data by service and environment. You can declare additional tags with small value sets:

```yaml
management:
  metrics:
    tags:
      application: ${spring.application.name}
      environment: ${APP_ENV:local}
      region: ${APP_REGION:local}
```

Do not add `userId`, `orderId`, email, session ID, trace ID, or URLs containing dynamic IDs to metric tags. Every new tag value can create additional time series, increasing Prometheus memory usage and query cost. Use logs or traces to investigate specific requests; keep metrics limited to stable labels such as route template, method, status, and business category.

When deploying multiple replicas, Prometheus scrapes each target. Keep target labels such as `instance` for per-replica investigation; when querying a service-wide SLI, aggregate across instances rather than computing per-instance ratios and averaging those ratios.

## 9. Common Issues and Troubleshooting

| Symptom | Common Causes | How to Check and Fix |
|---|---|---|
| HTTP 404 at `/actuator/prometheus` | Missing Prometheus registry, endpoint not exposed, base path changed, or endpoint disabled | Check dependencies, exposure, enablement, and actual URL |
| HTTP 401 | Endpoint requires authentication but Prometheus did not send credentials or credentials are wrong | Check Basic Auth, secret mount, and application user |
| HTTP 403 | User is authenticated but lacks permissions or request is blocked by security/network policy | Check roles and the active SecurityFilterChain |
| Connection refused or timeout | Wrong host/port, separate management port, bind address, or network policy | Check target from the Prometheus environment itself and check listening ports |
| Prometheus target DOWN | Endpoint returns error or scrape path/timeout is wrong | Open Targets page, read scrape error, and test calling the URL from the Prometheus host/container |
| Target UP but HTTP metrics missing | No requests sent yet, meter not created, wrong query filter, or different metric name | Send test requests, inspect raw endpoint, and check label names |
| Metrics exist but expected tag is missing | Common tag not configured or query uses wrong label | Check `management.metrics.tags` and actual exposition output |
| Scrape slow or timing out | Endpoint exposes too many time series, application overloaded, or scrape timeout too low | Control cardinality, inspect response size, and tune interval/timeout for load |

Do not expose all Actuator endpoints just to work around a 404 error. First identify which endpoint is missing and whether the cause is dependency, enablement, or exposure. After fixing it, re-verify access permissions so you do not accidentally widen the management surface.

## 10. Production Deployment Checklist

- [ ] `spring-boot-starter-actuator` and `micrometer-registry-prometheus` are present and compatible with Spring Boot.
- [ ] The `prometheus` endpoint is exposed and not disabled.
- [ ] `metrics_path` and target port in Prometheus match the Spring Boot configuration.
- [ ] Prometheus can scrape the endpoint from the right network namespace.
- [ ] The endpoint is restricted via private network, firewall, network policy, or appropriate authentication.
- [ ] Not all Actuator endpoints are exposed without an explicit requirement.
- [ ] Common tags use stable, low-cardinality values.
- [ ] Prometheus target displays `UP` and JVM/HTTP metrics are queryable.
- [ ] Dashboards and alerts use verified metric names and labels.
- [ ] Scrape health is monitored and missing targets are handled.

When complete, Spring Boot provides metrics via Actuator and Prometheus scrapes them on the configured schedule. Verify end-to-end from the application endpoint to the Targets page and PromQL queries; only when all three steps work is the metrics pipeline ready for production dashboards and alerting.
