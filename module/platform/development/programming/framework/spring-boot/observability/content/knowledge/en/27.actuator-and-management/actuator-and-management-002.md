# Management Server in Spring Boot

A Spring Boot application serves user traffic on port 8080 while also exposing health checks, metrics, and operational information. If management endpoints share the same listener as public APIs, they can be subject to the same network exposure and traffic policy. Spring Boot lets you configure the **management server** to control how Actuator endpoints are served: sharing the application's web server or running on a dedicated port, with an appropriate address, base path, and SSL policy.

The management server is the web infrastructure layer serving Actuator endpoints. It is not a metrics backend or a tracing Collector. Management server configuration determines where endpoints like /actuator/health, /actuator/metrics, and /actuator/prometheus can be accessed; which endpoints actually exist and are exposed still depends on dependencies, endpoint exposure, and security configuration.

The **Management server** lesson belongs to the **Actuator and Management** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module focuses on setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; learning context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in real environments.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the role of the management server in Spring Boot Actuator.
- Distinguish between management endpoints sharing the application port and running on a separate port.
- Configure management port, address, base path, and SSL as needed.
- Understand that endpoint availability, exposure, and authorization are three separate layers.
- Design a management network boundary so only operational systems have access.
- Configure health/readiness/liveness endpoints for deployment environments.
- Inspect metrics endpoints without over-exposing them.
- Diagnose port bind failures, 404, 401/403, and failed health checks.

## 2. What Is the Management Server?

Spring Boot Actuator provides endpoints for health, metrics, environment, beans, mappings, and many other operational details. The management server is the HTTP server surface on which these endpoints are exposed.

In the default configuration, Actuator endpoints typically share the same web server/port as the application, under the base path /actuator. For example:

```text
Application API:       http://localhost:8080/api/orders
Management health:     http://localhost:8080/actuator/health
Management metrics:    http://localhost:8080/actuator/metrics
```

If a separate management port is configured, endpoints can be served on a different listener:

```text
Application API:       http://localhost:8080/api/orders
Management health:     http://localhost:8081/actuator/health
Management metrics:    http://localhost:8081/actuator/metrics
```

The ports and paths above are examples only. The management server may use a separate web server or a separate listener depending on configuration and web application type.

## 3. Shared Port or Separate Port?

| Model | Characteristics | When Suitable |
| --- | --- | --- |
| Same port | Actuator endpoints share the listener with application endpoints | Simple systems that already have gateway/security/network controls |
| Separate management port | Management endpoints are served on a dedicated port | Need a separate network boundary and routing policy for operations |
| Separate management address | Management listener binds to a specific interface/address | Hosts with multiple network interfaces needing interface restriction |

A separate port does not automatically make endpoints secure. If a firewall/security group allows internet access to that port, management endpoints can still be exposed. Combine bind address, firewall, Kubernetes NetworkPolicy, service routing, and Spring Security.

### When Is a Separate Port Not Needed?

Some environments use a service mesh or ingress policy that can protect the same application port with a route allow-list. In that case, management endpoints are only reachable from internal networks or monitoring agents. What matters is the actual boundary and verified policy, not just the port number.

## 4. Configuring the Management Port

Setting a separate management port:

```yaml
server:
  port: 8080
management:
  server:
    port: 8081
```

After configuring this, the application API continues listening on port 8080, while the management server uses port 8081. If management.server.port is not set, management endpoints typically use the application web server.

### Binding the Management Address

Example binding the management listener only to loopback:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
```

A loopback address is only suitable if the management client runs on the same host/network namespace. In containers/Kubernetes, binding 127.0.0.1 can prevent kubelet, sidecars, or external monitoring agents from reaching it. Choose the address based on the actual network topology.

### Management Base Path

The base path can be changed:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
```

The health endpoint can then be /manage/health on the management port. Changing the base path alters the URL; it does not replace authentication or network restrictions.

## 5. Management Server SSL

If the management server runs on a separate port, separate SSL can be configured according to the properties supported by the Spring Boot version:

```yaml
server:
  port: 8080
management:
  server:
    port: 8443
    ssl:
      enabled: true
      key-store: classpath:management-keystore.p12
      key-store-type: PKCS12
      key-store-password: $MANAGEMENT_KEYSTORE_PASSWORD$
```

This example illustrates TLS configuration; property details and separate SSL support depend on the Spring Boot version. Do not commit keystore passwords or private keys to source control. Use appropriate secret management and certificate rotation.

If management endpoints have TLS terminated at an ingress/proxy, verify that traffic between the proxy and the application is also protected according to the threat model. Edge TLS does not automatically protect every network hop inside the cluster.

## 6. Endpoint Availability, Exposure, and Security

These three concepts are distinct:

1. **Availability:** whether the endpoint exists, usually depending on dependencies/auto-configuration.
2. **Exposure:** which web/JMX surface the endpoint is exposed on.
3. **Authorization:** which callers are allowed to access the endpoint.

Example exposing only a few web endpoints:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

The list of endpoints to expose depends on purpose and registry. Do not use wildcard * in production without evaluating each endpoint. Some endpoints such as env, configprops, beans, heapdump, or threaddump can leak sensitive information or consume resources.

### Exposure Is Not Authentication

Adding metrics to the exposure list only makes the endpoint servable over the web; it does not automatically require login. Protect endpoints with Spring Security or network access controls.

Example security matcher that must be adapted to the Spring Security version and application requirements:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/actuator/health/**").permitAll()
            .requestMatchers("/actuator/**").hasRole("OPS")
            .anyRequest().authenticated()
        )
        .build();
}
```

This example illustrates an authorization policy for a same-port setup. If using a separate management port and a separate security chain, ensure the matchers, chain order, and actuator request matchers are right. Do not open all endpoints just so health probes can access them.

## 7. Health, Readiness, and Liveness

Health endpoints help the platform determine application status. With Spring Boot Actuator, health groups can serve separate probes:

- **Liveness:** Is the process still alive and able to keep running?
- **Readiness:** Is the instance ready to accept new traffic?
- **Overall health:** What status are the configured health indicators reporting?

Example probe configuration:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
```

Common paths in probe-enabled environments:

```text
/actuator/health/liveness
/actuator/health/readiness
```

Probe endpoints may be exposed depending on configuration and Spring Boot version. Verify them in the application runtime instead of assuming enabling a property is enough.

### Do Not Include Every Dependency in Liveness

If a database or Kafka temporarily loses connectivity, a liveness check depending on those services can mark the process as dead and cause the orchestrator to restart continuously. Liveness should reflect the process's ability to self-recover; readiness can reflect whether the instance can currently accept traffic. Choose health indicators and groups based on the application's failure semantics.

### Separate Management Port and Health Probes

If a Kubernetes probe is configured to call port 8081, the management server must bind to an interface reachable from kubelet/container network. If bound to loopback or with a TLS mismatch, the probe can fail even though the application port is healthy. Verify probe scheme, port, path, headers, and certificate policy.

## 8. Metrics and Prometheus Endpoint

The management server can expose Actuator metrics and the Prometheus scrape endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

The Prometheus registry dependency must be present in the application. The endpoint is typically:

```text
/actuator/prometheus
```

If using a separate management port, the scrape target must use the corresponding management port and base path. A successful Prometheus scrape only proves the metrics endpoint returns data; it does not prove the tracing exporter or logs pipeline is working.

### Do Not Expose Metrics Publicly

Metrics can reveal route names, dependency topology, throughput, error rates, and internal service behavior. Restrict endpoint access via internal networks, authenticated scrapes, or service monitor policies. Only expose the endpoints needed for monitoring.

## 9. Environment-Specific Management Configuration

The management server often has different configurations per environment:

```yaml
spring:
  config:
    activate:
      on-profile: local
management:
  server:
    port: 8081
    address: 127.0.0.1
```

In production, port/address can be supplied via environment variables or deployment configuration. For example:

```text
MANAGEMENT_SERVER_PORT=8081
MANAGEMENT_SERVER_ADDRESS=0.0.0.0
MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=health,metrics,prometheus
```

Environment variables follow Spring Boot's relaxed binding rules. When using profile-specific files, profiles can override the base configuration; verify effective configuration at runtime without printing secrets.

## 10. Management Server and Web Application Types

Spring Boot can run a Servlet-based web application or a reactive WebFlux application. Management web infrastructure and whether a separate management context/server is created depend on application type, classpath, and version.

Do not assume a separate management port always creates a separate OS process. Typically it is still the same JVM/process but with a separate listener/context. If using a custom embedded server, reverse proxy, or management context configuration, verify the actual open listeners and ports.

### Port Collision

If the management port is already used by another process, startup can fail with a bind exception. Check occupied ports, host networking/replica collisions, container targetPort, management address, and TLS keystore.

## 11. Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| /actuator/health returns 404 | Actuator missing, different base path, or endpoint not exposed | Check dependency, base-path, and exposure |
| Management port not listening | management.server.port not bound or startup failed | Read startup logs and effective config |
| Port bind exception | Port already in use or address does not exist | Check process/port mapping and bind address |
| API port healthy but management port fails | Separate management listener failed or network policy blocks it | Check listener, firewall, and service routing |
| Health probe timeout | Wrong port/path/scheme or bind address unreachable | Test probe from the right network namespace |
| Health readiness DOWN | Health indicator reports dependency not ready | Inspect component details and readiness policy |
| Liveness restart loop | Liveness depends on unstable external service | Decouple liveness from inappropriate dependency checks |
| /actuator/metrics 401/403 | Security policy requires role/auth | Check credentials and matchers |
| Prometheus scrape 404 | Endpoint not exposed or registry missing | Check dependency and exposure |
| Prometheus scrape timeout | Network route or overloaded management server | Check service monitor, port, and resources |
| TLS handshake failure | Wrong certificate, trust chain, hostname, or scheme | Check TLS client/server configuration |
| Sensitive endpoint exposed | Overly broad exposure or wrong network boundary | Narrow include list and access policy |

### Deployment Checklist

1. Choose same port or separate management port based on the network boundary.
2. Determine a management address reachable from probes/monitoring agents.
3. Configure base path and SSL per environment.
4. Expose only necessary endpoints.
5. Protect endpoints with authentication/authorization and network controls.
6. Separate readiness/liveness according to failure semantics.
7. Update Kubernetes probes/service monitors to the right port/path.
8. Verify port listeners, TLS, status codes, and scrape output after deployment.

## 12. Hands-On: Separating Management Server from Application API

**Context:** order-service serves its API on port 8080. The monitoring agent needs to scrape metrics and Kubernetes needs health probes. The team wants the management server on port 8081 and reachable only from the internal network.

### Part A — Preparation

1. Add Spring Boot Actuator and the Prometheus registry.
2. Set application port 8080 and management port 8081.
3. Configure the management address according to the appropriate network namespace.
4. Expose health, metrics, and prometheus.
5. Protect management endpoints according to policy.
6. Configure liveness/readiness probes to target the management port.

### Part B — Verification

| Case | Action | Expected Observation |
| --- | --- | --- |
| A — Application | Call API on port 8080 | API still serves requests |
| B — Health | Call /actuator/health on port 8081 | Health endpoint returns status |
| C — Metrics | Call /actuator/metrics with appropriate permissions | Meter list is accessible |
| D — Prometheus | Scrape /actuator/prometheus | Metrics exposition is returned |
| E — Unauthorized | Call protected endpoint without credentials | Receives 401/403 per policy |
| F — Network boundary | Try accessing from an unauthorized network | Connection is blocked |
| G — Probe | Run readiness/liveness checks | Probe hits the right scheme/port/path |
| H — Port conflict | Use an already occupied management port in test | Startup reports clear bind failure |

### Part C — Self-Assessment Questions

1. How does the management server differ from the application server in role?
2. Why does a separate port not automatically secure Actuator endpoints?
3. How do availability, exposure, and authorization differ?
4. When should the management server be bound to loopback?
5. Why should liveness not depend on all external dependencies?
6. If the Prometheus scrape target still uses port 8080 after moving the management port to 8081, what happens?
7. Why do you need to verify the base path after changing it?
8. How does management SSL differ from TLS termination at ingress?
9. How can health probes access the management port inside a container?
10. Which endpoints require careful consideration before exposing publicly?

## 13. Takeaway

**Management server** determines where and over which listener Actuator endpoints are served. Spring Boot can share the application port or configure a separate management port via management.server.port; address, base path, and SSL can be tuned according to network topology and version.

Endpoint availability, web exposure, and security authorization are three separate layers. A separate port does not replace authentication, firewalls, or network policies. Only expose needed health/metrics endpoints, protect operational information, and point probes to the right port/path. Separate liveness from readiness so dependency outages do not trigger restart loops. After deployment, verify listeners, TLS, status codes, access policies, and Prometheus scrapes from the proper network boundary. Proper management server administration enables safe Spring Boot observability while still supporting health checks, metrics, and production operations.