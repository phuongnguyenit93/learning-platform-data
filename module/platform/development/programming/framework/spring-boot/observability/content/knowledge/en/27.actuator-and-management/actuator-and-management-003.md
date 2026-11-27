# Management Port in Spring Boot Actuator

> **Chapter:** Actuator and Management  
> **Lesson:** Management port  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. What Is a Management Port?

A Spring Boot application typically opens an HTTP port to serve business requests. At the same time, the operations platform needs endpoints such as health, metrics, info, or prometheus to check status and collect telemetry.

The management port is the network port serving Spring Boot Actuator management endpoints. These endpoints can share the application's port or be served on a separate port. Separating the port creates an operational access path independent of business traffic.

Example:
- Application server: 8080
- Management server: 8081
- Health: http://localhost:8081/actuator/health
- Metrics: http://localhost:8081/actuator/metrics

Separating the port does not automatically secure the endpoints. You still need to decide which endpoints are exposed, which callers are authorized, and configure TLS, authentication, and network policies.

~~~mermaid
flowchart LR
  U["API clients"] -->|8080| A["Spring Boot application"]
  A --> B["Business controllers"]
  M["Monitoring / probes"] -->|8081| C["Actuator management server"]
  C --> D["Health / metrics / info"]
  A --> E["Application services"]
  E --> F["Database / dependencies"]
~~~

## 2. Same Port or Separate Port?

Spring Boot Actuator supports two models:

| Model | Configuration | Characteristics |
| --- | --- | --- |
| Same port | No separate management.server.port set | Management endpoints use the main web server |
| Separate port | Set management.server.port different from server.port | Management endpoints use a separate management web server as configured |

Same port is simple and fits many applications. Separate port is useful when you want to:
- Separate probe/monitoring paths from public ingress.
- Apply dedicated firewall or network policies.
- Manage a separate bind address or TLS configuration.
- Separate platform and application port mappings.

A separate port also introduces an extra listener and operational configuration. You must open the right port in containers/services and configure probes, TLS, security chains, and monitoring targets.

## 3. Configuring Application Port and Management Port

Example application.yml:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
~~~

The API is served on 8080; Actuator web endpoints are served on 8081 under the default base path, provided the corresponding endpoints are exposed.

The management base path defaults to /actuator. It can be changed:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
~~~

The health endpoint can then be /manage/health depending on endpoint mapping. The base path is the HTTP path; the management port is the TCP port. These two settings are independent.

If management.server.port is not set, management endpoints typically share the application port. If set to a different value, Spring Boot configures a separate management web server depending on the web application type and version.

## 4. Which Address Should the Management Server Bind To?

You can bind the management listener to a specific interface. For example, binding only to loopback:

~~~yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
~~~

Callers from other containers or hosts usually cannot reach it over an external network interface. This configuration is only suitable when the probe/agent runs in the same network namespace or has local access.

In Kubernetes, kubelet probes access the Pod IP from the node. Binding the listener to 127.0.0.1 can prevent probes from connecting. Understand the network namespace and probe target before choosing an address.

If monitoring needs access from an internal network, bind to the appropriate interface and restrict callers with firewalls, security groups, or NetworkPolicies. Avoid binding the management listener to all interfaces without controls.

## 5. Endpoint Exposure Does Not Mean Authorization

Actuator provides an exposure mechanism to decide which endpoints are published over web/JMX. For example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

This configuration allows the listed endpoints to be published over the web if the corresponding endpoints are present on the classpath. It does not replace authentication/authorization.

Distinguish between:
- Exposure: whether the endpoint is published over web/JMX.
- Authorization: which callers are allowed to invoke the endpoint.
- Network reachability: whether callers can connect to the listener.
- Endpoint access: whether read/write access to the endpoint is permitted by policy and version.
- Data sanitization: whether the response leaks sensitive data.

An endpoint not exposed over the web can still be exposed over JMX depending on other settings. An exposed endpoint blocked by Spring Security still cannot be accessed if the caller lacks permissions.

Do not expose env, configprops, heapdump, threaddump, or logfile publicly just for quick debugging. These endpoints can leak configuration, runtime state, or sensitive data.

## 6. Health Endpoint on the Management Port

The health endpoint is commonly used to check application status:

~~~http
GET /actuator/health
~~~

When a separate management port is configured, the health endpoint can be served on the management port. Spring Boot can provide health groups such as liveness and readiness depending on version/configuration.

- Liveness: Does the process need to restart because it is no longer functioning properly?
- Readiness: Is the instance ready to receive business traffic?
- General health: The aggregated status of configured health contributors.

Do not indiscriminately include every dependency in liveness. If the database is temporarily unavailable and liveness fails, the platform may continuously restart pods even while the process is alive; that can worsen the incident.

Readiness is better suited to temporarily stop routing traffic to an unready instance. Liveness should reflect whether the process itself needs a restart, avoiding dependencies on downstream services that can recover independently.

## 7. Management Port and Kubernetes Probes

Kubernetes startup/readiness/liveness probes can call Actuator health groups. Example Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0
          ports:
            - name: http
              containerPort: 8080
            - name: management
              containerPort: 8081
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: management
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: management
            periodSeconds: 10
~~~

This is an example configuration. You must enable/provide the corresponding health groups in the Spring Boot version in use and verify the actual paths. containerPort declares the port inside the Pod; it does not automatically open firewalls or create a Kubernetes Service.

If a probe uses the port name management, the container must declare that exact port name and the application must bind the listener to an interface reachable by kubelet.

A readiness failure removes the Pod from the endpoints serving traffic via the Service. A liveness failure can cause kubelet to restart the container after exceeding the failure threshold. A startup probe delays liveness/readiness evaluation during a long startup phase.

Configure timeout, period, and failure threshold according to actual startup/recovery behavior. Do not make them overly sensitive such that brief spikes or a slow management server trigger a restart loop.

## 8. Is a Separate Management Port Truly Independent?

A separate management port creates a separate listener, not a separate OS process. It still runs in the same JVM, sharing the heap, CPU, and most of the application context.

This means:
- CPU starvation can slow down both API and Actuator responses.
- JVM pauses/GC affect both listeners.
- The health endpoint may not reflect every failure mode if the management server stays alive while the business server fails.
- Thread pool/connector behavior depends on the web server and Spring Boot version.
- A separate port does not isolate endpoints from code or dependency bugs in the same process.

If you need to verify that the business server is actually accepting requests, configure an appropriate health check or probe the application port separately. The management health endpoint only proves the management endpoint path works and health contributors report their status.

## 9. TLS for the Management Port

The management server can be configured with separate SSL in Spring Boot versions that support it. Distinguish between SSL on the application server and the management server; when using a separate port, management TLS configuration can differ.

Conceptual example:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:server.p12
    key-store-password: ${SERVER_KEYSTORE_PASSWORD}

management:
  server:
    port: 9443
    ssl:
      enabled: true
      key-store: classpath:management.p12
      key-store-password: ${MANAGEMENT_KEYSTORE_PASSWORD}
~~~

Properties and separate SSL support for the management server depend on the Spring Boot version/web server. Check the reference docs for your exact version. Do not commit keystore passwords or private keys to source control; use secret management.

If a monitoring agent scrapes over HTTPS, configure CA/truststore and hostname verification properly. Do not disable certificate validation to work around scrape errors in production.

## 10. Spring Security on Management Endpoints

When Spring Security is present, Actuator endpoints are subject to the security filter chain. If you define custom SecurityFilterChain beans, ensure management endpoints are protected properly without accidentally locking out health probes or opening metrics to all callers.

Illustrative example of a separate security chain:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {
        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(EndpointRequest.to("health"))
                        .permitAll()
                        .anyRequest().hasRole("OPS"))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .anyRequest().authenticated())
                .build();
    }
}
~~~

This is a skeleton example. You need the Actuator/Security dependencies, authentication provider, matchers, and appropriate chain ordering. If the health endpoint needs unauthenticated probe access, only permit that specific endpoint/group and consider network isolation. Do not permit all actuator paths just to make probes work.

A separate management port does not automatically create a security boundary in Spring Security. Authorization must still be configured and tested.

## 11. Metrics and Prometheus Scrape via Management Port

If using the Micrometer Prometheus registry and the endpoint is exposed, Prometheus can scrape the management port:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  server:
    port: 8081
~~~

The Prometheus target can point to order-service:8081/actuator/prometheus on the internal network. Service names/ports depend on deployment manifests and service discovery.

Do not expose the metrics endpoint over public ingress unless needed. Metrics can contain service names, routes, dependencies, JVM stats, and business dimensions. Even without PII, they can reveal system topology and behavior.

If the application port and management port differ, the scrape config must use the management target. Health probes can use the management port while API traffic uses the application port.

## 12. Reverse Proxy, Ingress, and Port Mapping

Inside a container, server.port and management.server.port are container ports. Host mappings, Kubernetes Service targetPort, or proxy upstreams must point to the right listener.

Docker example:

~~~bash
docker run -p 8080:8080 -p 8081:8081 order-service:latest
~~~

Example Kubernetes Service exposing only the application port:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: order-service
spec:
  selector:
    app: order-service
  ports:
    - name: http
      port: 80
      targetPort: 8080
~~~

The management port is omitted from this public Service. Monitoring can scrape the Pod management port directly, use a separate internal-only Service, or use appropriate scrape discovery.

Do not create a public Ingress to the management port unless there is a specific operational requirement and full security controls. An ingress routing path does not replace authentication/network policies.

## 13. Management Port and Graceful Shutdown

When the application shuts down, the management listener belongs to the same process lifecycle. Readiness should transition to not accepting traffic before the instance stops completely if graceful shutdown is configured.

A proper sequence:
1. The instance starts shutting down.
2. Readiness transitions to refusing traffic.
3. Load balancers/service routing stop sending new requests.
4. The server finishes in-flight requests within the shutdown grace period.
5. The process stops and the management listener closes.

Do not rely on a separate management port to keep the health endpoint alive independently after the application process has stopped. The listener shares the same JVM and therefore shuts down with the process lifecycle.

## 14. Troubleshooting the Management Port

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| API works but Actuator is unreachable | Wrong management port or listener not bound | Startup logs, port config, process listeners |
| Actuator still runs on 8080 | management.server.port not applied | Profiles/property sources and effective config |
| Kubernetes probe connection refused | Wrong port name/path or bound to loopback | Pod listeners, probe targetPort, bind address |
| Probe returns 404 | Health group/path not enabled or base path changed | Endpoint mapping and exposure |
| Probe returns 401/403 | Security chain blocks probe | Endpoint matchers and auth policy |
| Prometheus scrape timeout | Network policy, wrong port, or management server overloaded | Target, connectivity, scrape logs |
| Metrics endpoint returns 404 | Prometheus registry missing or endpoint not exposed | Dependency, exposure include |
| Port open but responses slow | JVM CPU/GC/thread starvation | Process metrics, thread dumps |
| TLS handshake failure | CA, certificate, hostname, or protocol mismatch | Certificate chain/truststore |
| Management port publicly exposed | Service/Ingress misconfigured | Service ports, ingress, firewall |
| Health green but API fails to serve | Management listener healthy while application path broken | Probe application port and business checks |
| Prolonged shutdown | Graceful shutdown/readiness lifecycle | Shutdown phase logs and probe state |

### Investigation Procedure

1. Confirm server.port, management.server.port, and active profiles.
2. Check startup logs to see which port the management server starts on.
3. Check listener bind address and container ports.
4. Call the health endpoint from the same network path as probes/monitoring.
5. Check base path, exposure, and authorization.
6. Check TLS if HTTPS is used.
7. Check Kubernetes Service, targetPort, NetworkPolicy, and ingress.
8. Compare management health against the application port and business requests.
9. Check metrics scrapes and endpoint latency.

## 15. Real-World Scenario: Separating the Management Port in Kubernetes

**Context:** order-service serves its API on 8080. The platform requires health probes and Prometheus scrapes to use a separate internal port, without going through public ingress.

### Step 1 — configure listeners

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

### Step 2 — declare container ports

Declare 8080 for HTTP and 8081 for management. Ensure the application binds to an interface reachable by kubelet and monitoring agents.

### Step 3 — configure probes

Readiness/liveness use the corresponding Actuator paths on the named port `management`. Verify the health groups exist in your Boot version and app configuration.

### Step 4 — restrict the network

The public Service only targets 8080. The management port is scraped via Pod discovery or an internal-only Service. Network policies only allow necessary node/probe/monitoring sources.

### Step 5 — protect endpoints

Expose health and prometheus as needed. Other endpoints are not published. Configure appropriate authorization or network isolation; do not rely on a separate port as the sole layer of protection.

### Step 6 — verify

- API requests succeed on the application port.
- Health probes return expected results on the management port.
- Prometheus scrape receives metrics.
- Management port does not pass through public ingress.
- Pod readiness changes properly when the app is not ready.
- Liveness does not restart the pod due to a temporary dependency failure outside liveness scope.

**Expected outcome:** management traffic has a dedicated, restricted access path, while application traffic maintains normal routing.

## 16. Exercises and Self-Check Questions

### Exercise A — same port and separate port

Run the application with management endpoints on the application port. Then set a different management.server.port. Compare URLs, listeners, startup logs, and access paths.

### Exercise B — bind address

Bind the management server to 127.0.0.1 and try accessing it from another container/network. Explain why probes may fail. Choose an appropriate bind address and network controls.

### Exercise C — endpoint exposure and security

Expose health, info, metrics, and prometheus in a test environment. Configure Spring Security so health probes are accessible per policy while other operational endpoints require role OPS. Test 200/401/403/404 responses.

### Exercise D — Kubernetes probes

Configure startup/readiness/liveness on the management port. Simulate slow startup, readiness failure, and liveness failure. Confirm expected routing/restart behavior.

### Exercise E — TLS

Enable HTTPS for the management listener if supported by your version. Verify the certificate chain, hostname, and Prometheus scrape TLS config. Do not disable certificate verification.

### Exercise F — network isolation

The public Service exposes only the application port. Create an internal management path for monitoring/probes. Verify there is no public ingress to actuator paths outside policy.

### Self-Check Questions

1. How does the management port differ from the application port in purpose?
2. When should you use the same port versus a separate port?
3. Which listener does management.server.port affect?
4. How does the management base path differ from the port?
5. Does endpoint exposure mean authorization?
6. Why can binding 127.0.0.1 cause Kubernetes probes to fail?
7. How do liveness and readiness differ?
8. Why should you not put every dependency into liveness?
9. Is a separate management port a separate process?
10. What needs to be checked when configuring TLS on the management listener?
11. How do you protect Actuator with Spring Security?
12. Should Prometheus scrape the management port or the application port?
13. Why should the management port not be exposed via public ingress?
14. Does green health on the management port prove the business API is working?
15. How do you verify the management port in Docker/Kubernetes?

**Completion criteria:** able to configure same/separate management port; understand bind address and base path; distinguish exposure/network/auth; configure health probes; secure management endpoints; connect Prometheus; verify TLS, container networking, and graceful shutdown.

## 17. Takeaway

- The management port is the listener serving Actuator web endpoints; it can share the application port or be separated.
- management.server.port configures the management port; server.port configures the application server.
- A separate port is not a separate process and does not automatically secure endpoints.
- Exposure, authorization, and network reachability are three separate layers.
- Expose only needed endpoints; protect metrics and operational info with security/network policies.
- The bind address must be compatible with the probe/monitoring network; loopback can block callers outside the namespace.
- Readiness determines whether an instance receives traffic; liveness determines whether the process needs a restart.
- Do not let a temporary dependency failure fail liveness if a restart will not fix the problem.
- Align Kubernetes port names, probes, Service targetPort, and NetworkPolicy with the management listener.
- A separate management port still shares JVM resources and lifecycle with the application server.
- Verify TLS, scrape targets, shutdown behavior, and application health along the real access path.

## References

- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Reference — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
- [Spring Boot Reference — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot Reference — Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.security)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Kubernetes — Services](https://kubernetes.io/docs/concepts/services-networking/service/)
