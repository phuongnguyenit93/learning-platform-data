# Setting Up Spring Boot Actuator for Discovery Experiments

In Spring Cloud Service Discovery experiments, applications need to expose clear signals about their operational status so that the registry or orchestration layer can evaluate instances. Spring Boot Actuator provides operational endpoints, among which the health endpoint is commonly used to check whether an application is ready to serve requests. When combined with Consul, Eureka, or another discovery client, Actuator helps observe service status and verify how that status affects instance discovery.

Actuator does not replace DiscoveryClient, ServiceRegistry, or the registry server. It provides health and operational information; the discovery mechanism or registry health check decides how to use that information.

## 1. What Is Spring Boot Actuator?

Spring Boot Actuator adds endpoints for observing and managing a running application. Endpoints can expose information such as:

- **health:** overall status and the status of individual health indicators.
- **info:** application metadata supplied via configuration or InfoContributors.
- **metrics:** measurement metrics provided by Micrometer and integrated components.
- **env, configprops, beans, loggers:** configuration and runtime details for diagnostics.

Not every endpoint is exposed over HTTP by default. In the default configuration, health is the web endpoint exposed; other endpoints must be explicitly exposed. This is an important safeguard because many endpoints can disclose configuration, internal topology, or sensitive data.

Within the scope of service discovery, the first endpoint you usually need to check is:

    GET /actuator/health

If the application is operating normally and all relevant health indicators pass, the endpoint typically returns status UP with HTTP 200. When health status fails, the endpoint may return HTTP 503. The exact HTTP status code also depends on status mapping and health endpoint configuration.

## 2. Adding the Actuator Dependency

Actuator is packaged in the spring-boot-starter-actuator starter. Projects should use Spring Boot dependency management or the Spring Boot parent/plugin to keep the starter version synchronized with the Spring Boot version in use.

**Maven**

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

**Gradle**

    dependencies {
        implementation 'org.springframework.boot:spring-boot-starter-actuator'
    }

Web applications usually already include spring-boot-starter-web or an equivalent web stack. The Actuator starter provides the endpoints and health infrastructure; the web stack enables accessing endpoints over HTTP.

For discovery experiment applications, the discovery dependency is added separately depending on the registry in use. For example:

- Consul: spring-cloud-starter-consul-discovery.
- Eureka client: spring-cloud-starter-netflix-eureka-client.

Use a Spring Cloud release train compatible with your project's Spring Boot version. Adding Actuator does not automatically register a service with Consul or Eureka; the application still needs the corresponding discovery dependency and configuration.

## 3. Configuring Health and Info Endpoints

Spring Boot uses /actuator as the default base path for web endpoints. Thus the default health endpoint is /actuator/health.

You can explicitly declare the endpoints to use in application.yml:

    spring:
      application:
        name: discovery-lab-service

    server:
      port: 8080

    management:
      endpoints:
        web:
          base-path: /actuator
          exposure:
            include: health,info
      endpoint:
        health:
          show-details: never
          probes:
            enabled: true
      info:
        env:
          enabled: true

    info:
      app:
        name: discovery-lab-service
        purpose: service-discovery-lab

Meaning of the configuration properties:

| Property | Effect |
|---|---|
| spring.application.name | Logical name of the application; usually used as the service ID when registering with discovery |
| server.port | Main HTTP port of the application |
| management.endpoints.web.base-path | Prefix for Actuator endpoints; defaults to /actuator |
| management.endpoints.web.exposure.include | List of endpoints exposed over HTTP |
| management.endpoint.health.show-details | Controls displaying health details; never avoids exposing internal details |
| management.endpoint.health.probes.enabled | Enables health groups for liveness and readiness |
| management.info.env.enabled | Enables the InfoContributor that reads info.* properties from Environment |

In the example above, the application exposes health and info. Endpoints such as metrics, env, configprops, and beans are not exposed simply because Actuator is present. Add endpoints only when there is a specific need and proper access permissions have been configured.

If you do not need the info endpoint, omit info from exposure.include and skip declaring the info.* group. For service discovery experiments, the health endpoint is usually mandatory; info is helpful for identifying instances and application versions when inspecting the registry.

## 4. Distinguishing Health, Liveness, and Readiness

/actuator/health represents the aggregated overall status from health indicators. In distributed environments, a single overall status is sometimes insufficient to answer two distinct questions:

- **Liveness:** is the application process still alive and able to continue running?
- **Readiness:** is the application ready to receive requests from other services?

Spring Boot provides health groups for these two states. When enabled:

    management:
      endpoint:
        health:
          probes:
            enabled: true

the following endpoints can be used:

    /actuator/health/liveness
    /actuator/health/readiness

Liveness helps the application runtime platform detect a stuck or malfunctioning process. Readiness reflects capacity to accept traffic; for instance, an application may not be ready during initialization or when a required dependency is not yet connected.

| Signal | Question to Answer | Common Usage |
|---|---|---|
| health | What is the current overall health status? | Application monitoring, registry health checks |
| liveness | Does the process need to be restarted? | Platform liveness probe |
| readiness | Should new requests be routed to this instance? | Readiness probe, traffic admission control |

Do not include every external dependency in liveness. If a database temporarily loses connectivity and liveness also transitions to DOWN, the platform may continuously restart an otherwise healthy process, amplifying the incident. Dependencies required to serve requests usually belong in readiness or a dedicated health group.

In discovery experiments, you can call all three endpoints to observe the difference. If using readiness as the criterion for registry health checks, verify that the registry is configured to call the exact path and that HTTP status codes reflect the system's intended readiness policy.

## 5. Health Indicators and Application Status

Actuator aggregates results from HealthIndicators. Spring Boot provides built-in indicators for supported dependencies on the classpath, such as datasources or integrated components. Applications can also define custom indicators for specific dependencies or business conditions that need monitoring.

Example of a simple custom health indicator:

    import org.springframework.boot.actuate.health.Health;
    import org.springframework.boot.actuate.health.HealthIndicator;
    import org.springframework.stereotype.Component;

    @Component
    public class CatalogDependencyHealthIndicator implements HealthIndicator {

        @Override
        public Health health() {
            boolean reachable = checkCatalogDependency();

            if (reachable) {
                return Health.up().build();
            }

            return Health.down()
                    .withDetail("dependency", "catalog")
                    .build();
        }

        private boolean checkCatalogDependency() {
            // Replace with a timeout-bounded check against the actual dependency.
            return true;
        }
    }

The code above illustrates the structure; in a real application, checkCatalogDependency() must check the actual dependency with a bounded timeout. Avoid executing heavy queries or chaining calls to multiple services on every health check. The health endpoint can be polled periodically by Consul or the deployment platform, so a slow indicator adds load and can cause the instance to be marked unhealthy by the check itself.

Decide which group each indicator belongs to. Essential dependencies for serving requests can affect readiness. An optional dependency or secondary feature may belong only in overall health or a separate metric, avoiding removing an instance from discovery while its core functionality still works.

## 6. Integrating Actuator with Service Discovery

Actuator only provides the endpoint. The registry must be configured to use that endpoint.

### Consul

Spring Cloud Consul typically registers an HTTP health check pointing to /actuator/health. You can declare the configuration explicitly to make experiments easier to observe:

    spring:
      cloud:
        consul:
          host: localhost
          port: 8500
          discovery:
            register: true
            register-health-check: true
            health-check-path: /actuator/health
            health-check-interval: 10s

The Consul Agent must be able to reach this address and path from the agent's network location. If you change the base path, context path, or management port, update the health check URL accordingly. Merely enabling register-health-check does not guarantee the check will pass if the endpoint is unexposed or unreachable.

### Eureka

A Eureka client can use the application's health status through Spring Cloud Netflix Eureka's health check integration. When you want the client to propagate the application's health status to Eureka, configure:

    eureka:
      client:
        healthcheck:
          enabled: true

Place this configuration in application.yml or equivalent application configuration so that health status is initialized properly in the application context. Exact behavior also depends on the Spring Cloud Netflix version and how the application integrates Actuator.

### Distinguishing Responsibilities

| Component | Responsibility |
|---|---|
| Spring Boot Actuator | Exposes health endpoints and operational info |
| HealthIndicator | Evaluates a component or dependency |
| Consul Agent / Eureka client integration | Polls or propagates health signals to the registry |
| DiscoveryClient | Looks up instance lists by service ID |
| LoadBalancer | Selects an appropriate instance to send requests to |

When testing, verify each layer separately. An Actuator endpoint returning UP does not prove the instance is registered; a registered instance also does not prove clients only receive healthy instances.

## 7. Management Port and Endpoint Paths

By default, Actuator uses the same port as the application. You can configure the management server to run on a separate port:

    server:
      port: 8080

    management:
      server:
        port: 8081
      endpoints:
        web:
          exposure:
            include: health,info

With this configuration, business requests use port 8080, while management endpoints use port 8081. Separating ports improves network and access control, but the registry's health check must call the management port. If the Consul Agent still calls service port 8080 at /actuator/health, the check may fail because the endpoint is actually on 8081.

In initial experiments, keep Actuator on the same port to reduce configuration variables. Separate the management port only when the lab specifically investigates management networking, firewalls, or security policies.

Related properties to know:

- management.server.port: port for the management server.
- management.server.address: bind address for the management server.
- management.endpoints.web.base-path: HTTP endpoint prefix.
- management.endpoints.web.path-mapping: maps an endpoint name to a different path.

If you change any of these properties, re-verify the full URL from the exact machine or container performing the health check.

## 8. Securing Actuator Endpoints

Exposing an endpoint and authorizing access to an endpoint are two separate things. management.endpoints.web.exposure.include controls which endpoints can be called over HTTP; Spring Security or network configuration controls who is allowed to call them.

Basic principles:

1. Expose only necessary endpoints. For discovery labs, health is usually sufficient, optionally plus info.
2. Do not broadly expose env, configprops, beans, heapdump, or shutdown on public networks.
3. Keep management.endpoint.health.show-details at never, or show details only when the caller is authenticated.
4. Restrict the management port with firewalls, network policies, or internal networks.
5. If an endpoint requires authentication, configure the registry health check to send appropriate credentials; never embed real secrets in the repository.
6. Never return passwords, tokens, connection strings, or personal data in custom health details.

Example minimal configuration for a lab environment:

    management:
      endpoints:
        web:
          exposure:
            include: health,info
      endpoint:
        health:
          show-details: never

When Spring Security is present, ensure requests from the health checker are authorized to access the right endpoint. Do not disable all security just to make the health check turn UP; configure rules or credentials specifically for the health checker.

## 9. Hands-On Verification of Actuator

After adding the dependency and configuration, start the application and test the endpoints from a host that can reach the application.

**Checking overall status**

    curl -i http://localhost:8080/actuator/health

Expected output when the application is healthy typically has HTTP 200 and a body similar to:

    {
      "status": "UP"
    }

**Checking liveness and readiness**

    curl -i http://localhost:8080/actuator/health/liveness
    curl -i http://localhost:8080/actuator/health/readiness

Both endpoints must be enabled via management.endpoint.health.probes.enabled. If you receive 404, check the Spring Boot version, probes configuration, and endpoint path.

**Checking application info**

    curl -i http://localhost:8080/actuator/info

The info endpoint works over HTTP only when exposed and supplied with data by contributors. If the body is empty, check info.* and management.info.env.enabled.

**Checking from the Consul Agent's perspective**

If the registry runs in another container, do not test the endpoint solely from the host machine. Test calling from the Consul Agent's own network namespace or container to the address the agent uses. The hostname localhost inside a container points only to that container, not to the host machine or another service container.

## 10. Troubleshooting Common Errors

| Symptom | Possible Cause | How to Check |
|---|---|---|
| /actuator/health returns 404 | Missing Actuator, wrong base path, or web endpoint not exposed | Check dependency and management.endpoints.web.base-path |
| /actuator/info returns 404 | info is not exposed | Add info to management.endpoints.web.exposure.include |
| Health returns 503 | A health indicator reports DOWN or OUT_OF_SERVICE | Check logs and health details in a protected environment |
| Health returns 401 or 403 | Spring Security blocks the health checker | Check authorization rules and credentials |
| Reachable from host but registry check fails | Registry Agent cannot reach host/port/path | Check DNS, port mapping, firewall, and network |
| Instance registers but is marked unhealthy | Health check calls wrong endpoint or app is not ready | Check URL and check status in the registry |
| Readiness is DOWN while liveness is UP | Application is alive but not ready to serve | Check required dependencies and startup initialization |
| Endpoint exposes too many details | Health details or endpoint exposure configured too broadly | Restrict exposure and show-details |

Diagnostic steps should be performed in order: verify the dependency, verify the path and port, call the endpoint directly, check access permissions, and only then inspect the registry configuration. This helps distinguish Actuator issues from network or discovery integration issues.

## 11. Conclusion

Spring Boot Actuator provides the health observability foundation for Spring Cloud Service Discovery experiments. To get started, add spring-boot-starter-actuator, expose the health endpoint, enable probes when testing liveness/readiness, and keep detailed information protected. Then configure the registry to call the correct endpoint from the network location the registry actually uses.

During practice, inspect the Actuator status, the check status in the registry, and the instance list returned by DiscoveryClient separately. These three outputs are related but belong to different responsibilities; checking each layer helps pinpoint exactly why an instance is or is not selected to serve requests.

## References

- [Spring Boot Reference — Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Spring Boot Reference — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Reference — Health Information](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health)
- [Spring Cloud Consul — Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Netflix — Eureka Client](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
