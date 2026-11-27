# Integrating Health Checks and Managing Actuator Access Control

## 1. Role of Actuator in a Spring Data REST Application

Spring Data REST exposes repositories as REST resources, typically under an API base path such as /api. Spring Boot Actuator provides operational endpoints to monitor health, metrics, configuration, and runtime information. The two endpoint groups serve different purposes:

- Repository resources belong to the business API, for example /api/orders.
- Actuator endpoints belong to the management API, using the /actuator prefix by default, for example /actuator/health.

Configuring Spring Data REST's base path via RepositoryRestConfiguration.setBasePath("/api") does not automatically move Actuator to /api/actuator. Actuator has its own management configuration. If you change the management base path or port, update URLs in monitoring, ingress, probes, and firewalls accordingly.

An Actuator endpoint is only available when the endpoint is enabled for access and exposed over a technology such as HTTP or JMX. Therefore, both endpoint exposure and access permissions must be configured.

## 2. Adding Dependencies and Enabling Required Endpoints

With Spring Boot, add the Actuator starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

If the application needs authentication and authorization for endpoints via Spring Security, add the corresponding starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
~~~

By default, Spring Boot exposes only the health endpoint over HTTP and JMX. You do not need to expose all endpoints to have a basic health check. Minimal configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when-authorized
      roles: ACTUATOR_ADMIN
~~~

HTTP endpoints typically follow the pattern /actuator/{id}. You can verify health with:

~~~bash
curl -i http://localhost:8080/actuator/health
~~~

Only add an endpoint to exposure.include after determining what data it returns and which users are permitted to access it. For example, env, configprops, beans, heapdump, logfile, and mappings can disclose internal details. Using * exposes all eligible endpoints, so it should not be used casually in network-accessible environments.

## 3. Distinguishing Exposure, Endpoint Access, and Spring Security

Three configuration layers serve different purposes:

| Layer | Question Addressed | Configuration / Mechanism |
|---|---|---|
| Endpoint access | Is the endpoint allowed to operate, and is it read-only? | Properties management.endpoint.*.access and management.endpoints.access.* in supported Spring Boot versions |
| Exposure | Which endpoints are published over HTTP or JMX? | management.endpoints.web.exposure.include/exclude and management.endpoints.jmx.exposure.include/exclude |
| Security | Who is allowed to call an exposed endpoint? | Spring Security SecurityFilterChain, RequestMatcher, and roles/authorities |

Exposure configuration does not replace authentication. An exposed endpoint still needs protection via network policies, firewalls, or Spring Security if it is not meant for public access. Likewise, granting permission to an endpoint does not automatically expose it over HTTP.

When using endpoint access properties, check the documentation for your exact Spring Boot version because property names and control capabilities have changed across release lines. For Spring Boot 3.5, the Actuator documentation details exposure and Spring Security setup in the Endpoints section.

## 4. Securing Actuator with SecurityFilterChain

When Spring Security is on the classpath and the application has not declared a SecurityFilterChain, Spring Boot auto-configures protection for actuator endpoints other than health. Once the application defines any SecurityFilterChain bean, Boot's default actuator security backs off. You must then write rules for both Actuator and the rest of the application's requests.

The example below targets Spring Boot 3.5 with a Servlet/MVC application. The first chain matches only Actuator; health is permitted without login, while remaining endpoints require the ACTUATOR_ADMIN role. The second chain secures the API and remaining routes.

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().hasRole("ACTUATOR_ADMIN")
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

EndpointRequest.toAnyEndpoint() scopes the first chain to actuator endpoints, while EndpointRequest.to("health") matches the health endpoint and its subpaths. Declaring hasRole("ACTUATOR_ADMIN") maps to the ROLE_ACTUATOR_ADMIN authority in Spring Security.

If using form login, OAuth2 Resource Server, or another authentication mechanism, replace httpBasic with the configuration appropriate for your system. When the application has multiple chains, set @Order explicitly and inspect each chain's request matcher; the first matching chain determines which rules apply.

Do not omit the application chain after adding an Actuator chain. If only the actuator chain exists, requests to Spring Data REST such as /api/orders may no longer be protected as intended.

### 4.1. Hiding Health Details from Unauthorized Callers

You can allow probes to call health without credentials while showing details only to authenticated users with the appropriate role:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: ACTUATOR_ADMIN
~~~

Common values for show-details and show-components:

- never: never return details or components.
- when-authorized: return details only when the caller holds the configured role.
- always: always return details.

Keep never or when-authorized in production. Health details can reveal hostnames, databases, service names, or internal topology. If the health endpoint uses permitAll, anonymous callers should receive only the overall status.

## 5. Custom HealthIndicator for Business Components

Spring Boot auto-configures certain HealthIndicators when corresponding dependencies are detected, such as a DataSource health indicator when a datasource is present. You can add a health indicator for application-specific components using the HealthIndicator interface.

Example checking a catalog component:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class CatalogStoreHealthIndicator implements HealthIndicator {

    private final CatalogStore catalogStore;

    public CatalogStoreHealthIndicator(CatalogStore catalogStore) {
        this.catalogStore = catalogStore;
    }

    @Override
    public Health health() {
        boolean available = catalogStore.isAvailable();

        if (available) {
            return Health.up()
                    .withDetail("component", "catalog-store")
                    .build();
        }

        return Health.down()
                .withDetail("component", "catalog-store")
                .build();
    }
}
~~~

The bean name produces the health component name per Spring naming rules; in this example, the component may appear as catalogStore. Return only details needed for operations. Never include passwords, tokens, connection strings, or business data in health responses.

Health checks must be fast, have timeouts, and avoid generating heavy load. Avoid calling a chain of external APIs or running expensive queries on every probe. If dependent systems must be checked, decide clearly whether the check belongs in readiness or only in monitoring signals.

## 6. Liveness and Readiness for Container Deployments

Spring Boot provides health groups for Kubernetes:

- /actuator/health/liveness indicates whether the process is still alive to continue running or needs a restart.
- /actuator/health/readiness indicates whether the instance is ready to accept traffic.

You can enable the probe groups explicitly:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db,catalogStore
~~~

In Kubernetes environments, Spring Boot auto-configures probe groups when a suitable environment is detected; probes.enabled turns them on explicitly when clear control is desired. Adjust the include list to match the application's actual component names.

Do not put databases, brokers, or external services into liveness. If a database has a temporary glitch and liveness also goes DOWN, Kubernetes can restart all instances at once and trigger a cascading outage. Readiness can check dependencies required to serve requests; liveness should reflect internal process state.

Example probe configuration:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
~~~

If the management port is separated via management.server.port, probes must target that port. Also consider exposing health group paths on the application port if infrastructure requires probes to evaluate the actual traffic-serving path.

## 7. Separating Management Port and Restricting Network Surface

You can separate Actuator from the API's public port:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,info
~~~

A separate port lets you apply separate firewalls, service network policies, or ingress rules for management traffic. When binding management.address to loopback, only processes or proxies on the same host can connect; make sure the monitoring agent actually runs somewhere it can reach that address.

If Kubernetes probes need to reach the management port, configure the port and network policy accordingly. Never assume separating ports alone replaces authentication; if the port is reachable over the network, security rules are still required.

## 8. Testing Access Control and Health Responses

Test through the HTTP layer with MockMvc to verify SecurityFilterChain, endpoint exposure, and actual responses.

~~~java
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
    void healthIsPublic() throws Exception {
        mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
    }

    @Test
    void metricsRequiresActuatorAdmin() throws Exception {
        mockMvc.perform(get("/actuator/metrics"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "ACTUATOR_ADMIN")
    void actuatorAdminCanReadMetricsWhenExposed() throws Exception {
        mockMvc.perform(get("/actuator/metrics"))
                .andExpect(status().isOk());
    }
}
~~~

This example assumes the metrics endpoint is exposed in the test configuration. If the application uses authentication other than HTTP Basic or the entry point returns 403 instead of 401, adjust assertions to match your actual security contract. Add spring-security-test to test scope when using @WithMockUser.

Beyond the tests above, verify:

1. Health responses do not disclose details to anonymous users.
2. Callers with the ACTUATOR_ADMIN role receive details as configured.
3. Repository requests such as /api/orders still pass through the application security chain.
4. Unexposed endpoints return 404 or are unregistered per your version's configuration, rather than assuming security rules alone control exposure.
5. Readiness transitions to DOWN when a required dependency is unavailable; liveness does not go DOWN merely because an external dependency is disrupted.
6. When the management port is separate, test health on the exact port and path.

## 9. Common Issues

| Symptom | Common Cause | How to Resolve |
|---|---|---|
| /actuator/health returns 404 | Missing Actuator dependency, endpoint disabled, or wrong path/port | Check starter, management base path, port, and exposure |
| /actuator/metrics returns 404 | Metrics not exposed or endpoint unavailable | Add metrics to exposure.include; check registry dependency if Prometheus is needed |
| Receiving 401 or 403 | SecurityFilterChain requires authentication or role mismatch | Check matchers, authentication, and ROLE_ACTUATOR_ADMIN |
| Spring Data REST API suddenly unprotected | Custom Actuator chain caused Boot security auto-configuration to back off, with no application chain defined | Add a dedicated chain for application requests and set @Order |
| Health returns UP but app receives no traffic | Readiness does not reflect required dependencies or startup state | Check the readiness health group and probe path/port |
| Kubernetes keeps restarting instances on database failure | Database included in liveness | Move the dependency to readiness or separate monitoring |
| Health details do not appear | show-details is never or caller lacks configured role | Check show-details, health.roles, and principal authorities |
| Separated management port causes probes to fail | Probe targeting wrong port, bind address, or network policy | Check management.server.port/address and probe configuration |
| Sensitive information leaked via Actuator | Broad endpoint exposure or show-details=always | Narrow exposure, protect with Spring Security/network rules, and hide details |

## 10. Deployment Checklist

1. Add spring-boot-starter-actuator and verify the health endpoint works.
2. Keep exposure minimal; never expose * on public networks.
3. Distinguish exposure, endpoint access, and authorization.
4. When declaring a SecurityFilterChain, configure both the actuator chain and the application chain.
5. Allow public health access at summary level only; restrict health details by role.
6. Implement HealthIndicators for custom dependencies with timeouts and safe details.
7. Configure liveness/readiness according to their purpose; never put external dependencies into liveness.
8. If separating the management port, update probes, firewalls, monitoring, and network policies.
9. Use MockMvc to test anonymous access, admin access, and business APIs.

## Official Documentation

- [Spring Boot 3.5 – Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot – Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot – Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
- [Spring Boot – Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Multiple SecurityFilterChain instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Data REST – Reference](https://docs.spring.io/spring-data/rest/reference/)