# Adding Actuator and Exposing Only Required Endpoints

In a Spring Boot system composed of multiple services, development and operations teams need to know whether an application is running, ready to accept requests, which version it is running, and whether any error signs exist. **Spring Boot Actuator** provides management and observability endpoints to answer those questions. However, a management endpoint can leak configuration, runtime information, or allow modifying application state. Therefore, adding Actuator must go hand in hand with deciding **which endpoints truly need to be accessible, who may access them, and over which network**.

This lesson belongs to the **Initialization** chapter of the **SPRING_CLOUD_CORE** module. Learners will add Actuator to a Spring Boot application, configure an allowlist of endpoints, protect health/info data, configure a management port, integrate health probes, and verify the results before deployment.

## 1. Learning Objectives

After this lesson, you can:

- Explain what Actuator provides and distinguish between an endpoint being enabled, permitted for access, and exposed over HTTP/JMX.
- Add `spring-boot-starter-actuator` to Maven or Gradle without manually pinning a version outside Spring Boot's dependency management.
- Expose only endpoints with a clear purpose using `management.endpoints.web.exposure.include`.
- Restrict endpoint access levels, protect endpoints with Spring Security, and restrict the management network path.
- Configure health details, liveness/readiness probes, and recognize the risks when health checks depend on external systems.
- Verify via HTTP requests, logs, and integration tests that endpoints outside the allowlist are inaccessible.

## 2. Where Does Actuator Fit in a Spring Cloud Application?

Actuator is a **Spring Boot** feature. It provides a set of endpoints and observability abstractions such as `HealthContributor`, `HealthIndicator`, `InfoContributor`, and metrics. Spring Cloud projects may contribute their own integrations or health indicators; Actuator aggregates and exposes that information according to the application's configuration.

For example, an `order-service` might use Spring Cloud Discovery Client to locate `inventory-service`. Actuator helps observe application status and any present `HealthContributor` beans. However:

- Adding Actuator **does not create a service registry** and does not automatically register services.
- Exposing `/actuator/health` does not mean all discovery details, configuration, or dependencies are exposed publicly.
- Having a health indicator on the classpath does not mean it must appear in every health group or return details to every caller.
- Actuator does not replace logging, tracing, a metrics backend, alerting, or authentication mechanisms.

General flow:

~~~mermaid
flowchart LR
    APP[Spring Boot application] --> HC[HealthContributor / InfoContributor]
    APP --> MET[Micrometer metrics]
    HC --> ACT[Spring Boot Actuator]
    MET --> ACT
    ACT --> AUTH[Access control and Security]
    AUTH --> EXP[HTTP / JMX exposure]
    EXP --> OPS[Probe / Monitoring / Operations]
~~~

**Access control**, **exposure**, and **security** are separate control layers. A solid configuration verifies all three.

## 3. Adding the Actuator Dependency

The official starter is `org.springframework.boot:spring-boot-starter-actuator`. The starter's version should be managed by the chosen Spring Boot parent/BOM or Spring Boot Gradle plugin. Do not assign an arbitrary version just for Actuator.

### 3.1. Maven

Add the dependency to `pom.xml`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

The snippet above assumes the project already uses Spring Boot dependency management. If the project uses an internal parent, import the `spring-boot-dependencies` BOM according to project conventions to manage versions.

### 3.2. Gradle

With Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

With Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
~~~

When the application uses Spring Cloud, continue keeping the Spring Boot/Spring Cloud version pair compatible according to the chosen release train. Actuator belongs to Spring Boot; you do not need a separate Spring Cloud starter just to get `/actuator/health`.

### 3.3. Testing After Adding the Starter

Start the application and send a request:

~~~bash
curl -i http://localhost:8080/actuator/health
~~~

The default HTTP endpoint path has the form `/actuator/{id}`. If a web application exposes the health endpoint, the response normally reports `UP` when relevant health contributors are healthy. If the application has no web server, Actuator can still be used via JMX or other management mechanisms.

Simply adding the dependency does not expose every endpoint. By default, Spring Boot only exposes the `health` endpoint over HTTP and JMX. This is a safe starting point for selectively adding endpoints when a specific need arises.

## 4. Understanding the Three Layers: Access, Exposure, and Authentication

An endpoint can only be called when it is available in the application, exposed over the active protocol, and the request passes security rules.

| Control layer | Question | Example |
| --- | --- | --- |
| **Endpoint access / enablement** | Is the endpoint permitted to exist and which operations are allowed? | `management.endpoint.health.access=read-only` |
| **Exposure** | Is the endpoint published over HTTP or JMX? | `management.endpoints.web.exposure.include=health,info` |
| **HTTP authorization / network security** | Who can call it and does the request come over an allowed network? | Spring Security roles, firewall, dedicated management port |

Do not treat `include=health,info` as an authentication mechanism. This property chooses which endpoints have URLs, but it does not identify the caller. Similarly, protecting URLs with Spring Security does not remove an endpoint from exposure.

In newer Spring Boot versions, endpoint access levels can also be configured with `management.endpoints.access.*`. This mechanism is independent of the exposure list. When an endpoint has no permitted access, it may be excluded from the application context.

## 5. Exposing Only Needed Endpoints

### 5.1. Starting with an Allowlist

Example `application.yml` for an internal service needing a health check and application metadata:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

With this setting, the application publishes only two HTTP endpoints:

| Endpoint | Purpose | Typical consumer |
| --- | --- | --- |
| `/actuator/health` | Overall status of the application | Orchestrator, internal load balancer, monitoring |
| `/actuator/info` | Selected application/build metadata | Dashboards or operations team |

Endpoints such as `env`, `configprops`, `beans`, `conditions`, `mappings`, `loggers`, `heapdump`, `threaddump`, and `shutdown` are not in this allowlist. They will not be published over HTTP just because Actuator is capable of providing them.

If the system only needs a health probe, the minimal configuration can be:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health"
~~~

**Do not use `include: "*"` in production configurations without a specific reason and corresponding controls.** A wildcard can cause new endpoints added in future upgrades to become accessible before the operations team has reviewed them.

### 5.2. `exclude` Takes Precedence over `include`

You can use `exclude` to block certain IDs from an included list:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: "env,beans,heapdump,threaddump"
~~~

`exclude` wins over `include`, yet a wildcard setup still carries risk when upgrades introduce new endpoints. For the goal of "exposing only needed endpoints," an explicit allowlist is usually easier to review and maintain.

In YAML, the `*` character has special meaning and must be quoted. There is no need for wildcards when only a few known endpoints are required.

### 5.3. HTTP and JMX Have Separate Exposure Configurations

`management.endpoints.web.exposure.*` controls HTTP. `management.endpoints.jmx.exposure.*` controls JMX. Do not assume changing the HTTP allowlist automatically changes JMX.

If your organization does not use JMX to manage Actuator, you can explicitly exclude all endpoints from JMX:

~~~yaml
management:
  endpoints:
    jmx:
      exposure:
        exclude: "*"
~~~

If using JMX, include only necessary endpoints and secure JMX via JVM/platform management controls. Avoid opening remote JMX to untrusted networks.

### 5.4. Management Base Path

The default prefix is `/actuator`. You can change the prefix:

~~~yaml
management:
  endpoints:
    web:
      base-path: "/management"
      exposure:
        include: "health,info"
~~~

The health endpoint then becomes `/management/health`. Renaming the path is not an authentication measure; users can still probe or learn the URL from configs, logs, or documentation.

A discovery page linking exposed HTTP endpoints can appear at `/actuator` (or the configured management base path). If you do not need this page, disable it:

~~~yaml
management:
  endpoints:
    web:
      discovery:
        enabled: false
~~~

Disabling the discovery page does not alter the exposure rules of individual child endpoints.

## 6. Configuring Endpoint Access by Default-Deny

In Spring Boot versions that support endpoint access control (such as 3.4.x, 3.5.x, and 4.x), you can set the default to `none` and grant read-only access only to needed endpoints:

~~~yaml
management:
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      access: read-only
    info:
      access: read-only
~~~

Meaning:

- `default: none` denies access to endpoints not explicitly granted permission.
- `health.access: read-only` and `info.access: read-only` allow read operations on those two endpoints.
- `max-permitted: read-only` sets a ceiling, preventing an individually configured endpoint from having higher access than that cap.
- `exposure.include` is still required to choose which endpoints are published over HTTP.

Common access values are `none`, `read-only`, and `unrestricted`. `read-only` permits read operations appropriate to the endpoint type; it does not mean requests require no authentication.

**Compatibility note:** check the documentation for your exact Spring Boot version before using `management.endpoints.access.*`. For older lines without this property, use that version's enablement/exposure mechanisms and protect URLs with Spring Security and network policies. Do not copy Boot 4 properties into an older Boot 3.x project without checking configuration property metadata.

## 7. Protecting Endpoints with Spring Security

### 7.1. When Does Boot Auto-Protect?

If Spring Security is on the classpath and the application **does not declare a custom `SecurityFilterChain`**, Spring Boot auto-configures security for Actuator endpoints except health by default. Once the application defines a `SecurityFilterChain` bean, Boot's automatic security configuration yields control; the development team must write rules for both Actuator and business URLs.

Therefore, do not add a filter chain solely for Actuator and forget the chain protecting the main API.

### 7.2. Endpoint Authorization Example

The example below demonstrates using `EndpointRequest` to match Actuator endpoints and require the `ENDPOINT_ADMIN` role. The configuration uses Spring MVC/Servlet and HTTP Basic to keep the focus on rules; production should integrate organizational authentication mechanisms, enable HTTPS, and manage credentials securely.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

// Spring Boot 4.x:
import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
// For Spring Boot 3.x, use import:
// org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;

@Configuration(proxyBeanMethods = false)
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ENDPOINT_ADMIN"))
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This is an example structure for an application with two security zones. The first chain matches Actuator only. The second chain handles remaining requests; replace `authenticated()` with rules appropriate for your API, OAuth2 Resource Server, form login, or existing project mechanism. Do not replace an existing security configuration wholesale with this example without reviewing your application's matchers and filter chain ordering.

`EndpointRequest.toAnyEndpoint()` respects the configured management base path, making it safer than hardcoding `/actuator/**` when the prefix may change. In Spring Boot 4, the package for `EndpointRequest` is `org.springframework.boot.security.autoconfigure.actuate.web.servlet`; in Spring Boot 3.x it is `org.springframework.boot.actuate.autoconfigure.security.servlet`. Use the import matching your project's Boot generation.

### 7.3. Preventing Health Details from Leaking

The health endpoint can aggregate status from databases, message brokers, caches, or `HealthIndicator` beans provided by integration libraries. Detailed output can reveal component names, topology, or internal diagnostic data.

Safe default configuration:

~~~yaml
management:
  endpoint:
    health:
      show-details: "never"
      show-components: "never"
~~~

If operations teams need details after authenticating:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: "ENDPOINT_ADMIN"
~~~

`when-authorized` displays details/components only to authenticated users who hold the configured roles. If no specific role is configured, Spring Boot considers any authenticated user authorized. Never set `always` on a publicly reachable endpoint.

The overall health status can still return `UP`, `DOWN`, or `OUT_OF_SERVICE` without exposing individual contributor details.

## 8. Choosing Endpoints by Operational Purpose

Not all endpoints carry the same risk. The following table helps evaluate each ID before adding it to the allowlist:

| Endpoint | Data / impact | Recommendation |
| --- | --- | --- |
| `health` | Overall status and health groups | Usually needed for probes/monitoring; hide details from unauthorized callers |
| `info` | Application, build, and git metadata if corresponding contributors are active | Publish only reviewed data; avoid secrets or sensitive internal info |
| `prometheus` | Metrics for Prometheus scraping | Enable only if `micrometer-registry-prometheus` is present; restrict to scraper network |
| `metrics` | Metric names and values | Use only when tools require it; protect since metrics can reveal flow names or labels |
| `loggers` | Read/change runtime log levels | Restrict to authorized operators; changing log levels can increase load or expose data |
| `env`, `configprops` | Environment and application configuration (with sanitization) | Do not expose publicly; config metadata remains sensitive even when some values are masked |
| `beans`, `conditions`, `mappings` | Bean wiring, auto-configuration, and route mappings | Use for internal diagnostics; never open to the Internet by default |
| `heapdump`, `threaddump`, `logfile` | Memory dumps, thread stacks, or log contents | Enable only under controlled support workflows; may contain sensitive data and cause heavy load |
| `shutdown` | Shuts down the application | Do not expose without a special operational requirement and strict auth/authorization |

### 8.1. Adding `info` Intentionally

`info` aggregates data from `InfoContributor` beans. For example, you can enable the `env` contributor to expose selected properties prefixed with `info.`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  info:
    env:
      enabled: true
info:
  app:
    name: order-service
    version: "1.4.0"
    description: "Order processing API"
~~~

Do not place passwords, tokens, connection strings, internal URLs, or customer data under `info.*`. Only publish metadata that helps distinguish services and builds.

If the build generates `META-INF/build-info.properties` or `git.properties`, the build/git contributors may add data to the response depending on version settings. Inspect the actual response and disable unnecessary contributors, for example:

~~~yaml
management:
  info:
    git:
      enabled: false
~~~

### 8.2. Exposing Prometheus Only When Needed

The `prometheus` endpoint requires the registry dependency:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Only then consider adding `prometheus` to the allowlist:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
~~~

Allow only the Prometheus server or monitoring network to access this endpoint. Metrics can disclose service names, routes, error types, and internal behavior. Avoid attaching very high-cardinality tags such as user IDs, request IDs, or emails to metrics.

## 9. Management Port and Network Access

By default, Actuator HTTP uses the same port as the main web server. You can separate management endpoints onto a dedicated port:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

Here, the business API is served on `8080`, while Actuator HTTP listens on `8081`. Separating ports makes it easier to apply dedicated network policies, ingress rules, or firewalls; **it does not automatically make port 8081 secure**. Exposure controls, authentication/authorization, and source restrictions are still required.

If administration should only be permitted from the machine's loopback interface:

~~~yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
~~~

Do not apply this loopback configuration blindly in Kubernetes: kubelet or Prometheus may need to reach the Pod's network address. Design the bind address and NetworkPolicy around how probes/scrapers actually connect.

If HTTP management endpoints are not needed at all, disable HTTP exposure completely by excluding all endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
~~~

Or set management server port to `-1` when the version and deployment setup support that option. Before disabling, verify the application does not rely on HTTP health probes.

## 10. Health, Liveness, and Readiness in Distributed Systems

### 10.1. Health Does Not Equal "Ready to Receive Traffic"

`/actuator/health` returns the aggregated status of registered `HealthContributor` beans. If the application uses a database, Redis, or message broker with a corresponding health indicator, those contributors can affect the overall result.

In an orchestrated environment, distinguish:

- **Liveness:** whether the application process is alive and not deadlocked to the point of needing a restart.
- **Readiness:** whether the instance is currently ready to accept business requests.
- **Startup probe:** whether the application has finished a long initialization phase so the orchestrator does not restart it prematurely.

Do not use liveness to check a database, registry, or external service. If an external dependency fails and liveness flips to fail, Kubernetes may restart all instances in waves, worsening an overload incident.

Readiness may include an external dependency when business requests genuinely cannot be served without that dependency. Choose contributors carefully, because an overly broad readiness check can pull every instance out of the load balancer during a shared incident.

### 10.2. Enabling Health Probes

Spring Boot provides `liveness` and `readiness` health groups when probes are enabled. You can configure them explicitly:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

The two default additional paths are `/livez` and `/readyz` on the main application port. Health group paths also remain accessible under `/actuator/health/liveness` and `/actuator/health/readiness` on the management server. This is helpful when using a separate management port while probes also need to verify the main web server.

If only the default health group paths are needed, omit `add-additional-paths`. Confirm that your Spring Boot version and deployment environment activate probes as expected.

### 10.3. Kubernetes Configuration Example

An illustrative snippet where probes call the two paths on the application port:

~~~yaml
containers:
  - name: order-service
    ports:
      - name: http
        containerPort: 8080
      - name: management
        containerPort: 8081
    livenessProbe:
      httpGet:
        path: /livez
        port: http
      periodSeconds: 10
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /readyz
        port: http
      periodSeconds: 5
      failureThreshold: 3
~~~

This is an excerpt of the `containers` section for illustration and must be integrated into an actual Pod/Deployment manifest. When configuring a separate `management.server.port`, probes do not have to call the management port if additional paths are enabled on the application port.

## 11. Testing Actuator Configuration

After starting the application, verify both allowed and disallowed endpoints.

### 11.1. Manual Verification

~~~bash
# Health endpoint is in the allowlist
curl -i http://localhost:8080/actuator/health

# Info endpoint only exists if included and a contributor provides data
curl -i http://localhost:8080/actuator/info

# Env is not in the allowlist so it is not exposed over HTTP
curl -i http://localhost:8080/actuator/env

# Beans is also not exposed over HTTP
curl -i http://localhost:8080/actuator/beans
~~~

Interpreting the responses accurately:

| HTTP Result | Common meaning |
| --- | --- |
| `200 OK` | Endpoint exists, request is authorized and processed successfully |
| `401 Unauthorized` | Endpoint may be accessible, but request lacks authentication |
| `403 Forbidden` | Request was denied by authorization rules or CSRF |
| `404 Not Found` | URL is unmapped, endpoint is not exposed, or does not exist |
| `503 Service Unavailable` | Health status may be `DOWN`/`OUT_OF_SERVICE` per status mapping |

Actual status codes also depend on security filters, management base path, and reverse proxy handling. Therefore, combine HTTP responses with startup logs and runtime configuration when diagnosing issues.

### 11.2. Pre-Release Checklist

- [ ] `spring-boot-starter-actuator` dependency is managed by a compatible Spring Boot version.
- [ ] HTTP allowlist contains only IDs approved by development and operations teams.
- [ ] Wildcards are not used outside test environments without a security review.
- [ ] `env`, `configprops`, `beans`, `heapdump`, `threaddump`, and `shutdown` are not unintentionally exposed.
- [ ] Health details/components are not disclosed to unauthorized callers.
- [ ] Security chains for both Actuator and business APIs are defined when using a custom `SecurityFilterChain`.
- [ ] Management port, bind address, firewall, ingress, and NetworkPolicy match expected traffic flows.
- [ ] Liveness does not depend on databases, registries, or external systems.
- [ ] Readiness checks only dependencies strictly necessary to serve requests.
- [ ] Tested unauthorized requests, unauthenticated requests, and requests with the required role.
- [ ] Verified both HTTP and JMX exposure against organizational policy.

### 11.3. Automated Testing

You can use `@SpringBootTest` with `MockMvc` for Servlet applications or `WebTestClient` for WebFlux/HTTP tests. What to verify:

1. `/actuator/health` is exposed and returns the configured response.
2. `/actuator/info` returns only the selected metadata fields.
3. `/actuator/env` and `/actuator/beans` cannot be invoked over HTTP when excluded from the allowlist.
4. Users without the required role cannot read protected management endpoints.
5. Health details remain hidden from unauthorized users.
6. When running with the production profile, management port and base path match expectations.

Exposure tests should run with a profile or application context close to production. A test that merely checks whether a YAML file contains the string `health,info` does not prove endpoints are actually protected.

## 12. Real-World Scenario: Preparing order-service for Operations

Suppose `order-service` is a Spring Cloud service running in Kubernetes. It uses a database and calls `inventory-service` via discovery/load balancing. The operations team needs:

- Kubernetes to know when the container is alive and ready to receive traffic.
- Monitoring to read service status.
- Dashboards to distinguish running builds.
- Prometheus to scrape metrics over the internal network.
- Internet users unable to read configuration or bean structures.

An initial configuration could look like this:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,info,prometheus"
  endpoint:
    health:
      access: read-only
      show-details: when-authorized
      show-components: when-authorized
      roles: "ENDPOINT_ADMIN"
      probes:
        enabled: true
        add-additional-paths: true
    info:
      access: read-only
    prometheus:
      access: read-only
  info:
    git:
      enabled: false
~~~

This configuration assumes a Spring Boot version supporting `management.endpoints.access.*`, the Prometheus registry dependency is present, and Security is properly configured. If not using Prometheus, remove `prometheus` from the allowlist and drop the registry dependency. If `info` is not needed, remove `info` from the allowlist. If managing health details with another role, synchronize the role with Spring Security configuration.

In this setup, probes can call `/livez` and `/readyz` on `8080`, while monitoring/operators access management port `8081` over the internal network. Service and network policies must permit only authorized sources to reach port `8081`; never expose the management port through public ingress.

The operations team should also determine which health indicators reflect discovery and database dependencies. If the registry is temporarily unavailable while the instance can still serve current requests, liveness should not necessarily fail. Readiness rules must reflect `order-service`'s actual serving contract.

## 13. Common Mistakes

**Exposing all endpoints for debugging convenience.** This can leak configuration, environment variables, bean details, routes, and memory dumps. Start from an allowlist.

**Thinking changing `/actuator` to `/manage` is enough security.** Changing the path only changes the URL, not authentication or authorization.

**Assuming having Spring Security automatically protects Actuator as desired.** Boot applies auto-configuration only when no custom `SecurityFilterChain` exists. When defining custom filter chains, review both Actuator and business APIs.

**Setting `show-details: always` because monitoring needs to know which database failed.** Monitoring usually only needs overall status; detailed output should be reserved for authenticated operators.

**Using liveness to check all dependencies.** This can turn a database or service registry incident into cascading mass restarts.

**Separating the management port and assuming it is already safe.** A dedicated port still needs firewalls, network policies, authentication, and an exposure allowlist.

**Exposing the `prometheus` endpoint while forgetting the registry dependency and network scope.** The endpoint requires the Micrometer Prometheus registry and should only be accessible to internal scrapers.

## 14. Summary

Actuator enables Spring Boot applications to expose health, info, metrics, and structured management data. Within a Spring Cloud system, it helps observe services and integrated health contributors, without replacing discovery, a registry, or security.

The initialization workflow should begin with `spring-boot-starter-actuator`, then identify endpoints by operational need, enforce an **allowlist** via `management.endpoints.web.exposure.include`, restrict endpoint access if supported by the Boot version, secure with Spring Security, and control network access. Health details must be restricted, liveness/readiness must accurately reflect their roles, and every change should be verified with live requests and integration tests.

Expose only endpoints with a clear consumer, purpose, and access policy. This lets Actuator support operations without turning the management interface into an unnecessary attack surface.

## References

- [Spring Boot — Enabling Production-ready Features](https://docs.spring.io/spring-boot/reference/actuator/enabling.html): adding `spring-boot-starter-actuator`.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint access, exposure, security, health details, health groups, and Kubernetes probes.
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html): management base path, management port/address, and disabling HTTP endpoints.
- [Spring Boot — Actuator REST API](https://docs.spring.io/spring-boot/api/rest/actuator/): URLs and responses of HTTP endpoints.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): complete reference of `management.*` properties by version.
- [Spring Security — Servlet Security](https://docs.spring.io/spring-security/reference/servlet/index.html): configuring filter chains, authentication, and authorization.

Always consult documentation for the exact Spring Boot line in use. Some access control properties and the Java package of `EndpointRequest` change across Boot generations; configurations in this lesson must be verified against your actual version before deploying to production.
