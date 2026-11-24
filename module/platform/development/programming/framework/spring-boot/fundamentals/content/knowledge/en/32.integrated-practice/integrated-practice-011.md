# Observing Health, Beans, and Startup Information Within Permitted Scope

Spring Boot Actuator provides endpoints that help development and operations teams understand the state of a running application. Three information sources that are commonly helpful when investigating a service are:

- **Health**: what state are the application and its dependencies in, and is it ready to accept requests?
- **Beans**: which beans did Spring register in the ApplicationContext, and what are their types, scopes, and dependency relationships?
- **Startup information**: which steps ran during startup, which steps took time, and which configurations need inspection?

This data aids troubleshooting, yet it can also reveal internal architecture, class names, dependencies, topology, or operational details. Observation must therefore stay within **permitted scope**: enable only required endpoints, expose them over appropriate transports, restrict who can access them, and return only the level of detail needed for the task.

This lesson uses Spring Boot 3.x, Spring MVC, and Spring Security 6 in HTTP examples. You will practice enabling Actuator, reading health status, restricting health details, inspecting the bean inventory, recording startup steps with `BufferingApplicationStartup`, securing endpoints by role, separating the management network, and writing tests for both permitted and denied access.

## 1. Observation Goals and Data Minimization

An operational endpoint should answer a specific question. Never expose all data merely because Actuator provides an endpoint for it.

| Need | Appropriate information | Suggested access scope |
| --- | --- | --- |
| Load balancer checking service | Overall health status | Probe allowed to read status |
| Orchestrator checking readiness/liveness | Readiness and liveness state | Pod/node network or internal listener |
| SRE checking dependencies | Needed health components/details | Authorized operations accounts |
| Developer investigating bean wiring | Bean names, types, dependencies | Dev/staging environments or internal admins |
| Team analyzing slow startup | Startup steps and durations | Admin/SRE with controlled access |
| Metrics scraper | Selected metrics | Monitoring system's service identity |

Three principles should apply:

1. **Least privilege**: each caller only sees the exact data needed.
2. **Data minimization**: responses include only info required for operational decisions.
3. **Defense in depth**: combine endpoint exposure, authentication, authorization, network isolation, and auditing.

Not every read-only endpoint is harmless. Health details can reveal internal dependencies; the beans endpoint can enumerate application architecture; the startup endpoint can reveal class names, beans, and initialization steps. Treat them as internal operational data.

## 2. Adding Spring Boot Actuator

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Actuator provides standard endpoints such as `health`, `info`, `beans`, `conditions`, `env`, `configprops`, `metrics`, `loggers`, and others depending on dependencies and configuration.

In web applications, the default base path is typically:

~~~text
/actuator
~~~

Example health URL:

~~~http
GET /actuator/health
~~~

Minimal status response:

~~~json
{
  "status": "UP"
}
~~~

Adding the dependency does not mean every endpoint is exposed over HTTP. In standard Spring Boot 3.x setups, default HTTP and JMX exposure only includes `health`. Most endpoints are enabled by default, yet enablement and exposure are two separate decisions.

## 3. Distinguishing Enablement, Exposure, and Authorization

An endpoint is usable over HTTP when the key conditions align:

1. The endpoint is enabled.
2. The endpoint is exposed over HTTP.
3. The request hits the right management listener/path.
4. The caller passes authentication and authorization.
5. The response policy permits displaying the corresponding detail level.

~~~mermaid
flowchart TD
    A["Request to /actuator/..."] --> B{"Endpoint enabled?"}
    B -->|No| X["Endpoint unavailable"]
    B -->|Yes| C{"Exposed over HTTP?"}
    C -->|No| Y["No HTTP endpoint"]
    C -->|Yes| D{"Right listener/network?"}
    D -->|No| Z["Cannot reach management service"]
    D -->|Yes| E{"Authenticated and authorized?"}
    E -->|No| F["401 / 403"]
    E -->|Yes| G["Apply response disclosure policy"]
    G --> H["Return only permitted data"]
~~~

### 3.1. Enablement

You can disable unused endpoints:

~~~properties
management.endpoint.beans.enabled=false
~~~

Or adopt opt-in for endpoints:

~~~yaml
management:
  endpoints:
    enabled-by-default: false
  endpoint:
    health:
      enabled: true
    beans:
      enabled: true
    startup:
      enabled: true
~~~

With opt-in, only explicitly enabled endpoints are active. If an endpoint must be accessed over HTTP, it still needs to be exposed.

### 3.2. Exposure

A minimal HTTP allowlist:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health"
~~~

When you also need to observe beans and startup in an internal environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,beans,startup"
~~~

The `startup` endpoint also requires configuring startup-step recording via `BufferingApplicationStartup`; adding the endpoint name to the include list alone does not generate startup data.

You can use exclude:

~~~properties
management.endpoints.web.exposure.include=health,beans,startup,env
management.endpoints.web.exposure.exclude=env
~~~

Exclude takes precedence over include. Even so, a short allowlist is usually easier to review than including everything and excluding dangerous endpoints one by one.

### 3.3. Authorization

Exposure only determines whether an endpoint appears over HTTP. It does not mean every caller is allowed to read it. Use Spring Security or a matching protection mechanism to restrict users and service accounts.

If the application defines its own `SecurityFilterChain`, check the actual rules: in standard Servlet setups, providing a custom chain causes Spring Boot's default Actuator security auto-configuration to defer to the application's security configuration.

## 4. What Does the Health Endpoint Answer?

The health endpoint aggregates status from configured `HealthIndicator` and `HealthContributor` beans. An application may have contributors for databases, disk space, messaging, readiness/liveness, or custom integrations.

Example:

~~~http
GET /actuator/health
~~~

Simple public response:

~~~json
{
  "status": "UP"
}
~~~

Status is not limited to only UP or DOWN. Health status can be aggregated across multiple contributors and mapped via configured status ordering/mappings. Common statuses include:

- `UP`: component reports normal operation.
- `DOWN`: component reports it is not functioning.
- `OUT_OF_SERVICE`: component is out of service for requests.
- `UNKNOWN`: state could not be determined.

If a contributor reports an unhealthy state, the aggregated endpoint status can reflect it per status aggregation rules.

### 4.1. Health Is Not a Full Functional Test

`UP` only says that configured health contributors report healthy state according to their own logic. It does not prove every API returns the right results, every business flow succeeds, the database schema is completely valid, the system handles production load, or every downstream service is ready for every request type.

Health checks should be designed around a specific operational decision, such as whether to route traffic to an instance.

### 4.2. Common Health Contributors

Depending on dependencies and configuration, an application may include contributors for:

| Contributor | Typically checks |
| --- | --- |
| `db` | DataSource/database connectivity |
| `diskSpace` | Disk space against configured thresholds |
| `ping` | Basic check of the application context |
| `livenessState` | Application liveness state |
| `readinessState` | Application readiness state |
| Custom indicator | Chosen dependency or operational condition |

Do not assume every contributor exists in every project. For instance, `db` requires matching database health integration.

## 5. Creating a Custom `HealthIndicator`

An integration can provide a health indicator to report status for a dependency lacking a built-in Actuator contributor.

Example:

~~~java
package com.example.shop.monitoring;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class BillingHealthIndicator implements HealthIndicator {

    private final BillingGateway billingGateway;

    public BillingHealthIndicator(BillingGateway billingGateway) {
        this.billingGateway = billingGateway;
    }

    @Override
    public Health health() {
        boolean available = billingGateway.isAvailable();

        if (available) {
            return Health.up()
                    .withDetail("provider", "billing")
                    .build();
        }

        return Health.down()
                .withDetail("provider", "billing")
                .withDetail("reason", "dependency unavailable")
                .build();
    }
}
~~~

This is a conceptual example; `isAvailable()` needs appropriate timeouts and error handling for real clients. A health check should never perform an unbounded network call that hangs probes.

### 5.1. Do Not Put Secrets into Health Details

Never return passwords, tokens, authorization headers, connection strings, or credential-bearing URLs in details. Health responses can be polled by load balancers or monitoring agents. Putting credentials in details turns the health endpoint into a secret leak vector.

Return minimal metadata, such as logical dependency name, status, or non-sensitive error codes:

~~~java
return Health.down()
        .withDetail("dependency", "billing")
        .withDetail("reason", "connection unavailable")
        .build();
~~~

### 5.2. Do Not Call Heavy Dependencies on Every Probe

Probes can be invoked frequently by orchestrators. A health indicator calling multiple remote services sequentially, running heavy queries, or waiting through long retries can amplify load during an outage.

Designs should use short deterministic timeouts, avoid lengthy retries per probe, check only dependencies essential to the health decision, avoid high-frequency repetitive logging, and consider short-lived status caching when semantics allow.

### 5.3. `ReactiveHealthIndicator`

Reactive applications can use `ReactiveHealthIndicator` to check dependencies via reactive APIs. Never block the event loop with a long blocking call just to compute health status.

## 6. Restricting Health Details and Components

Overall health status is usually enough for probes. Details like datasource names, cluster names, broker state, or error reasons should be restricted to SREs.

Spring Boot provides two key properties:

- `management.endpoint.health.show-details`: controls displaying details.
- `management.endpoint.health.show-components`: controls displaying health components.

Common modes:

| Value | Meaning |
| --- | --- |
| `never` | Never show details/components in this mode |
| `when-authorized` | Show only when the caller is considered authorized |
| `always` | Always show to callers accessing the endpoint |

Example keeping responses minimal:

~~~yaml
management:
  endpoint:
    health:
      show-details: never
      show-components: never
~~~

If admins need details:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles:
        - ACTUATOR_ADMIN
~~~

With `when-authorized`, configured roles specify which users may view details. If roles are not explicitly restricted, any authenticated user may count as authorized under the endpoint's default behavior; never assume only admins see details without configuring roles.

### 6.1. Public Status and Private Details

A common design:

- Unauthenticated health checkers only read `status`.
- Authenticated SREs with the proper role read components/details.
- Anonymous or ordinary users never receive internal dependency information.

Combine this response policy with Spring Security. `show-details=when-authorized` does not replace URL protection and management network isolation.

### 6.2. Do Not Include Raw Exceptions in Details

Exception messages can contain hostnames, schemas, SQL fragments, URLs, usernames, or request payloads. In custom indicators, map exceptions to a safe reason code/summary instead of exposing raw exception objects in responses.

## 7. Liveness and Readiness

In container/orchestrator environments, two distinct questions exist:

- **Liveness**: is the process/application alive and able to continue operating?
- **Readiness**: is this instance currently ready to accept traffic?

Spring Boot tracks application availability states and can expose corresponding health groups.

When probes are enabled:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
~~~

Common endpoints:

~~~http
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

### 7.1. Liveness Should Not Depend on Every Downstream Service

If the database temporarily drops connections and liveness turns DOWN, Kubernetes can continuously restart every instance. That often makes incidents worse when a shared dependency is degraded.

Liveness should reflect whether the process needs a restart to recover. A temporarily unavailable external dependency usually belongs in readiness rather than liveness, depending on architecture.

### 7.2. Readiness Reflects Ability to Serve Traffic

Readiness can incorporate prerequisites required to handle requests. Example group configuration:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: "readinessState,db"
        liveness:
          include: "livenessState"
~~~

Evaluate this choice per application. Only include `db` in readiness if requests need the database to operate and that health check accurately reflects serving capacity.

Do not add every dependency to both liveness and readiness out of habit.

### 7.3. Probe Paths on the Main Server

If management endpoints run on a separate port, probes might check the management server while the main application server has issues. Spring Boot supports exposing probe paths on the main server port via:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

When supported and configured, `/livez` and `/readyz` on the main server port can serve probes. Verify exact URLs and ports in your deployment.

## 8. What Does the `beans` Endpoint Show?

`/actuator/beans` lists bean definitions/instances known to the Spring context, organized by context hierarchy. Information can include bean name, aliases, bean type, scope, resource/declaration source, dependencies, and owning context.

Example request:

~~~http
GET /actuator/beans
~~~

Illustrative response:

~~~json
{
  "contexts": {
    "application": {
      "beans": {
        "orderService": {
          "aliases": [],
          "scope": "singleton",
          "type": "com.example.shop.order.OrderService",
          "dependencies": [
            "orderRepository"
          ]
        }
      }
    }
  }
}
~~~

This JSON illustrates the general shape, not an exhaustive schema across every Spring Boot version.

### 8.1. When Is the `beans` Endpoint Useful?

- Verifying whether a service was registered as a bean.
- Identifying which concrete bean implementation is active.
- Investigating missing or wrong dependency injection.
- Seeing whether a configuration/module was loaded.
- Inspecting the bean graph when multiple auto-configurations participate.
- Comparing contexts across local, staging, and production within permitted scope.

### 8.2. What Can the `beans` Endpoint Disclose?

The bean list can reveal internal package and class names, integration adapters or vendor libraries, datasource/cache/message clients, module structure and dependency graphs, security/configuration components, and environment-enabled features.

This is architectural metadata. Attackers can use it to infer frameworks, dependencies, and attack surfaces. Never expose `beans` to anonymous users or public ingress.

### 8.3. The `beans` Endpoint Is Not a Bean-Fixing Tool

This endpoint is primarily for observation. It does not replace a Spring debugger, bean factory diagnostics, or integration tests. When a bean is wrong, fix package scanning, configuration, conditions, or dependency injection in source/configuration.

## 9. Observing the `beans` Endpoint Within Permitted Scope

In development environments, you can expose `beans` temporarily:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,beans"
~~~

In production, enable it only with a clear operational use case and protect it with appropriate roles and network controls.

| Caller | Health status | Health details | Beans inventory |
| --- | --- | --- | --- |
| Anonymous probe | May be allowed | No | No |
| Ordinary authenticated user | Per policy | No | No |
| SRE/admin | Yes | Yes if needed | Yes when approved |
| Public internet | Do not expose internal data | No | No |

If continuous bean-graph inspection is unnecessary, keep `beans` unexposed and enable it only during controlled investigation windows, then revoke it.

Never paste full `beans` responses into shared logs or public tickets. If evidence is needed, extract the minimal excerpt, strip unnecessary metadata, and store it under proper access control and retention policies.

Bean names are not a public contract. External business systems must never rely on bean names in Actuator responses.

## 10. Startup Information and `StartupEndpoint`

A Spring application may create many beans and run many steps before becoming ready for traffic. When startup is slow, summary logs usually show only total startup duration without pinpointing which steps took time.

Spring Framework provides the `ApplicationStartup` abstraction to record startup steps. Spring Boot provides `BufferingApplicationStartup` to retain those steps in a bounded buffer.

Combined with Actuator's `startup` endpoint, operations teams can inspect startup steps and durations to investigate initialization.

### 10.1. Configuring `BufferingApplicationStartup`

In the main class:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ShopApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(2048)
        );

        application.run(args);
    }
}
~~~

`2048` is an illustrative buffer capacity. Size the capacity based on expected startup steps and available resources. The buffer is bounded; do not treat it as unlimited historical storage.

Configure the startup recorder before calling `run` so bootstrap steps are recorded.

### 10.2. Enabling and Exposing the `startup` Endpoint

Configuration example:

~~~yaml
management:
  endpoint:
    startup:
      enabled: true
  endpoints:
    web:
      exposure:
        include: "health,beans,startup"
~~~

When the application uses `BufferingApplicationStartup` and the endpoint is enabled and exposed, you can request:

~~~http
GET /actuator/startup
~~~

The endpoint returns startup step data structured according to the Spring Boot version. Content can include step names, durations, tags, and bean/configuration details.

If the endpoint returns no data, verify `BufferingApplicationStartup` was actually configured before startup.

### 10.3. `startup` Endpoint vs. Startup Logs

| Source | Question answered |
| --- | --- |
| Application logs | Which messages did the app print during startup? |
| Startup endpoint | What is the structured breakdown and duration of recorded startup steps? |
| Metrics | What are aggregated runtime indicators like request count/latency/memory? |
| Tracing | Which components did a specific request or operation traverse? |

The startup endpoint is neither a duplicate of application logs nor a full CPU instruction profiler. It lets you inspect instrumented steps captured during startup.

### 10.4. Startup Data Is Also Internal Information

Startup steps can reveal bean names, configuration classes, packages, and initialized integrations. This information helps admins, not end users.

Protect `/actuator/startup` as an internal diagnostic endpoint. Never expose it just to render startup duration on a public dashboard.

## 11. Distinguishing the `startup` Endpoint from the `info` Endpoint

`/actuator/info` typically serves metadata from `InfoContributor`s, such as application name, version, or build details. It is not equivalent to startup steps.

Example of curated metadata:

~~~yaml
info:
  app:
    name: shop-api
    version: "1.4.0"
~~~

You can expose `info` if its contents have been reviewed and fit the intended callers. Never put secrets, internal repository URLs, or sensitive info into `info` metadata.

`/actuator/startup` inspects bootstrap steps; `/actuator/beans` shows the bean inventory; `/actuator/health` reports health state. Each endpoint has its own purpose and disclosure risk.

## 12. Securing Endpoints with Spring Security

When Spring Security is on the classpath and the application does not define its own `SecurityFilterChain`, Spring Boot provides default protection for Actuator endpoints other than health in standard configurations.

Once the application defines its own chain, proactively define rules for both Actuator and application APIs. The example below targets a Servlet/MVC application using Spring Security 6.

### 12.1. Separating the Actuator Chain and Application Chain

~~~java
package com.example.shop.security;

import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {

        http.securityMatcher(EndpointRequest.toAnyEndpoint());

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health"))
                    .permitAll()
                .requestMatchers(EndpointRequest.to("beans", "startup"))
                    .hasRole("ACTUATOR_ADMIN")
                .anyRequest()
                    .denyAll()
        );

        http.httpBasic(withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated()
        );

        http.httpBasic(withDefaults());

        return http.build();
    }
}
~~~

How this works:

- The first chain applies exclusively to Actuator endpoints.
- Health status allows anonymous access for probes.
- `beans` and `startup` require the `ACTUATOR_ADMIN` role.
- All other Actuator endpoints are denied by the catch-all rule.
- The second chain protects the rest of the application so business APIs are never left unprotected.

This is an authorization example, not a complete production identity setup. Applications need a real authentication mechanism such as OIDC/OAuth2 resource server or appropriate service identities. HTTP Basic should only be used with TLS and proper credential handling.

### 12.2. Role Mapping Must Be Explicit

`hasRole("ACTUATOR_ADMIN")` normally checks for the `ROLE_ACTUATOR_ADMIN` authority per Spring Security's default convention.

If your identity provider emits a different claim or omits that prefix, configure a `GrantedAuthority` mapper or use `hasAuthority` with normalized authorities.

Never assume a JWT claim named `roles` automatically turns into Spring Security roles without configuring a converter.

### 12.3. Anonymous Health Status Does Not Mean Anonymous Details

The security chain allows GET health. The health endpoint configuration still sets:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles:
        - ACTUATOR_ADMIN
~~~

Thus probes can read status, while details and components appear only to callers the endpoint considers authorized.

### 12.4. Do Not Forget Requests Outside Actuator

If you only define a chain using `securityMatcher(EndpointRequest.toAnyEndpoint())` without a second chain, requests that do not match that chain will not be protected by it. When customizing security, make sure every application route is covered by an appropriate policy.

### 12.5. CSRF and Write Operations

The endpoints in this lesson mainly use GET. If you later expose endpoints supporting POST/DELETE such as runtime-mutating operations, evaluate CSRF policy, authentication, and authorization for the client type.

Never disable CSRF globally just to make one Actuator request work. For machine-to-machine management clients, scope filter chains and CSRF rules narrowly with clear justification.

## 13. Separating the Management Port and Network

You can run management endpoints on a dedicated port:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: "health,beans,startup"
~~~

The application API listens on 8080, while the management server listens on 9001. This helps isolate routing and network policies, though changing the port does not add authentication by itself.

### 13.1. Restricting the Listener to an Interface

If management only needs local access in certain deployments:

~~~yaml
management:
  server:
    port: 9001
    address: 127.0.0.1
~~~

Binding loopback can fit same-host monitoring agents. In containers/orchestrators, verify network namespaces and probe topology; binding loopback can block kubelet or scrapers coming from the Pod network.

### 13.2. Network Controls

Combine firewalls/security groups allowing the management port only from operations networks, Kubernetes NetworkPolicies restricting which Pods/services may connect, separate internal Services for management, reverse proxies/ingresses that never route management paths publicly, TLS or mTLS for management traffic, and dedicated service accounts for monitoring/admin.

Never treat a separate port as the sole security control. If port 9001 is still routed to the internet, the endpoints remain externally reachable.

### 13.3. JMX Is a Separate Transport

HTTP exposure does not govern JMX exposure. If the application uses JMX, maintain a JMX allowlist and secure the connector independently. Spring MVC / Spring Security HTTP filter chains do not protect JMX connectors.

## 14. Sample Configurations per Environment

### 14.1. Production: Health Status and Required Metrics

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,prometheus"
  endpoint:
    health:
      show-details: never
      show-components: never
~~~

`prometheus` requires the matching registry/dependency and should only be reachable by authorized monitoring systems. If the project does not use Prometheus, omit it from the allowlist.

### 14.2. Staging: Adding Controlled Diagnostics

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,beans,startup"
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles:
        - ACTUATOR_ADMIN
    startup:
      enabled: true
~~~

Also configure `BufferingApplicationStartup` and Spring Security so `beans` and `startup` are restricted to admins. Do not expose staging management ports publicly just because staging data is less sensitive than production.

### 14.3. Local Development

Locally, developers may need additional endpoints to learn and debug. Even so, never use production credentials or real user data in an expanded local setup.

Use an explicit profile:

~~~yaml
# application-dev.yml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,beans,startup,conditions"
~~~

Ensure the `dev` profile can never be activated accidentally in production. Network and security controls must still apply independently.

## 15. Structured Workflow for Observing Startup and the Bean Graph

When a service starts slowly or misses a bean, investigate methodically:

### Step 1: Check Health Status

Call `/actuator/health` to see whether startup succeeded and what health contributors report. If health status is DOWN, view details only with proper authorization.

### Step 2: Verify the Required Bean

If you suspect a bean was not registered, inspect `/actuator/beans` in an authorized environment. Search for the bean by name, type, or dependencies.

### Step 3: Inspect Module Configuration

If the bean is missing, check package scanning, `@Import`, conditions, profiles, and configuration properties. The `beans` endpoint shows registration outcomes; source and configuration explain why.

### Step 4: Read Startup Steps

If startup is slow, inspect `/actuator/startup` with `BufferingApplicationStartup` enabled. Identify high-duration steps, step types, and related beans/configurations.

### Step 5: Cross-Check Startup Logs

The startup endpoint and logs complement each other. Logs show errors or remote connection issues; startup steps reveal which part of bootstrap consumed time.

### Step 6: Re-Evaluate After Changes

After updating configuration or dependencies, rerun startup in the corresponding environment. Compare health, bean inventory, and startup steps under the same access policy.

## 16. Testing Endpoint Access

Tests should verify both authorized and unauthorized callers.

Example with Spring MVC, Spring Security Test, MockMvc, and an application with the two security chains above:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,beans",
        "management.endpoint.health.show-details=when-authorized",
        "management.endpoint.health.roles=ACTUATOR_ADMIN"
})
@AutoConfigureMockMvc
class ActuatorAccessTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCallerCanReadHealthStatus() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser
    void ordinaryUserCannotReadBeans() throws Exception {
        mvc.perform(get("/actuator/beans"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ACTUATOR_ADMIN")
    void adminCanReadBeans() throws Exception {
        mvc.perform(get("/actuator/beans"))
                .andExpect(status().isOk());
    }
}
~~~

To run this example, the project needs the appropriate Spring Security Test dependencies, such as starter-test and Spring Security's test support module. Ensure Actuator endpoints are enabled and the chains apply to the same web context.

### 16.1. Testing the `startup` Endpoint

To test `/actuator/startup`, the test bootstrap must configure `BufferingApplicationStartup` before the context runs and expose the `startup` endpoint. Adding `startup` to the HTTP include list without configuring the recorder does not verify startup data is present.

### 16.2. Testing Unauthorized Cases as Well

Tests should confirm anonymous callers only read health status if policy permits, ordinary users cannot read `beans`/`startup`, admins can read granted endpoints, un-allowlisted endpoints are not exposed, health details contain no raw secrets, and the management port is not routed through public ingress in deployment topology.

A passing MockMvc security test does not by itself prove firewalls or Kubernetes NetworkPolicies are right. Network layers require corresponding integration/deployment checks.

## 17. Never Put Sensitive Data into Diagnostics

Even when endpoints are locked down, keep the underlying diagnostic data safe:

- Never write passwords/tokens into health details.
- Never embed secrets in bean names or configuration metadata.
- Never attach credentials to custom startup step tags.
- Never log the whole Environment for quick debugging.
- Never put user IDs, emails, or tokens into metric labels.
- Never return raw exception messages that may contain connection strings or request payloads.
- Never paste full `beans` responses into shared logs or public tickets.

Endpoint security restricts who can access the route, but cannot compensate for responses that inherently leak overly sensitive data.

### 17.1. Startup Tags Also Need Care

If code creates custom startup steps or attaches tags, use only analytical values such as feature names or operation categories. Never put credentials, tokens, emails, or payloads into tags.

The startup endpoint stores tags in its buffer and returns them to authorized callers. Treat them like telemetry data.

### 17.2. Health Reasons Should Be Stable and Minimal

A reason like `database unavailable` is usually more helpful than a raw exception exposing hostnames, SQL statements, or usernames. Deep troubleshooting details belong in redacted, access-controlled internal logs.

## 18. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `/actuator/health` works but `/actuator/beans` returns 404 | `beans` not HTTP exposed or disabled | Check enablement and exposure |
| `/actuator/startup` has no data | `BufferingApplicationStartup` not configured | Configure recorder before starting app |
| `beans` returns 401 | Caller unauthenticated | Authenticate with a permitted identity |
| `beans` returns 403 | Caller lacks admin role | Check role/authority mapping |
| Health returns only status | `show-details=never` or caller unauthorized | May be intended behavior per policy |
| Health details leaked to ordinary users | `show-details=always` or overly broad roles | Restrict disclosure and roles |
| Readiness DOWN while process runs | Dependency required for readiness is unhealthy | Inspect indicators/groups and semantics |
| Liveness DOWN on temporary DB outage | DB was inappropriately included in liveness | Separate liveness from readiness |
| `beans` list is huge | Context contains many modules/beans | Filter as needed; review module composition |
| Startup endpoint misses expected step | Buffer capacity, recorder, or instrumentation | Verify configuration and startup lifecycle |
| Custom security chain leaves endpoints open | Chain missing rules or missing catch-all chain | Review all filter chains and matchers |
| Management port is public | Ingress/firewall route is too broad | Separate internal service and network policy |
| MockMvc passes yet cluster probe fails | Network route/port/path differs from test context | Verify actual deployment topology |

## 19. Practical Troubleshooting Playbooks

When asked to investigate an "unhealthy service," "missing bean," or "slow startup," classify the problem first.

### 19.1. Unhealthy Service

1. Read overall status.
2. Identify which health group is DOWN.
3. Inspect details only when authorized.
4. Locate the failing contributor.
5. Check dependencies and timeouts.
6. Never expose exceptions or secrets in responses.
7. Verify liveness and readiness are designed properly.

### 19.2. Bean Not Registered

1. Check the `beans` endpoint in an internal environment.
2. Verify bean name, type, and context.
3. Check package scanning and module configuration.
4. Check profiles and conditional configuration.
5. Verify dependencies exist on the runtime classpath.
6. Fix source/configuration and write a boundary test.

### 19.3. Slow Startup

1. Confirm `BufferingApplicationStartup` was enabled before `run`.
2. Inspect startup steps.
3. Locate high-duration steps.
4. Cross-check startup logs and external calls.
5. Inspect bean initialization, migrations, and network dependencies.
6. Optimize the identified bottleneck.
7. Re-measure under identical conditions.

### 19.4. Endpoint Unreachable

Check in order: endpoint enabled, exposure, base path, management port, network route, authentication, role mapping, and response policy. Never open wildcard exposure just to rule out one cause.

## 20. Pre-Exposure Checklist

Before enabling an endpoint in a shared or production environment, confirm:

1. Who needs the data and for what specific purpose?
2. Is the endpoint truly necessary?
3. Could the data reveal class names, topology, secrets, or user info?
4. Can it return status/summary instead of full details?
5. Is the endpoint on the HTTP/JMX allowlist?
6. Do callers have proper authentication?
7. Are roles/authorities scoped to the right people?
8. Is the management listener on an internal network?
9. Is access audited/logged appropriately?
10. Do negative security tests exist?
11. Is exposure reviewed when upgrading dependencies or adding endpoints?
12. Is there a sunset plan if exposed solely for an incident?

For the three endpoints in this lesson:

| Endpoint | Default HTTP exposure in standard config | Primary data | Recommended policy |
| --- | --- | --- | --- |
| `health` | Yes | Status, optional components/details | Probes read status only; admins view details |
| `beans` | No | Bean inventory/dependency metadata | Internal admin/SRE only |
| `startup` | No | Startup steps/durations/tags | Internal admin/SRE, enable recorder intentionally |

The `startup` endpoint needs a matching recorder; `beans` and `startup` should never be treated as public APIs.

## 21. Practice Exercises

### Exercise 1 — Enable Actuator

Add `spring-boot-starter-actuator` to an MVC application. Call `/actuator/health` and note the response status. Verify why `/actuator/beans` may not be accessible under default exposure.

### Exercise 2 — Create a Custom `HealthIndicator`

Write `BillingHealthIndicator` checking a simulated dependency. Return UP/DOWN with safe reasons only. Never include credential-bearing URLs or raw exceptions in details.

### Exercise 3 — Restrict Health Details

Set `show-details=never` and `show-components=never`. Then switch to `when-authorized` with role `ACTUATOR_ADMIN`. Compare responses for anonymous callers, ordinary users, and admins.

### Exercise 4 — Design Liveness and Readiness

Enable health probes. Put `livenessState` in the liveness group and identify which dependencies truly belong in readiness. Explain why a temporary DB outage should not necessarily trigger continuous process restarts.

### Exercise 5 — Inspect the Bean Inventory

Expose `beans` in a local environment. Locate a service, repository, and configuration bean. Note which architectural details can be inferred from the response and propose who should be allowed to view it.

### Exercise 6 — Enable Startup Recording

Configure `BufferingApplicationStartup` with a suitable capacity. Enable the `startup` endpoint and visit `/actuator/startup`. Identify several startup steps and durations, and explain the buffer's capacity limit.

### Exercise 7 — Separate `startup` from `info`

Configure `info` to return only approved name/version metadata and restrict `startup` to admins. Explain why the two endpoints have different audiences and disclosure risks.

### Exercise 8 — `SecurityFilterChain`

Create a dedicated Actuator chain: `health` permitAll, `beans`/`startup` requiring `ACTUATOR_ADMIN`, other endpoints denied. Create a second chain protecting application routes. Test anonymous, ordinary user, and admin callers.

### Exercise 9 — Management Port

Set application port 8080 and management port 9001. Configure networking so only the monitoring/admin network reaches port 9001. Confirm the management port is not routed through public ingress.

### Exercise 10 — Security Regression Tests

Write tests confirming anonymous callers cannot read `beans`, ordinary users get 403, admins can read `beans`, and health details appear only for permitted roles. Add a negative test for an endpoint outside the allowlist.

### Exercise 11 — Investigate Slow Startup

Use the startup endpoint to pinpoint a high-duration initialization step. Cross-check logs to determine whether it is bean creation, migration, or an external dependency. Propose how to re-measure after fixing.

### Exercise 12 — Disclosure Review

Construct a mock health response containing hostnames, connection strings, and tokens. Redesign it to return only status and safe reasons. Write a test asserting no secret markers appear in the response.

## 22. Key Takeaways

Spring Boot Actuator helps observe application health, the bean graph, and the startup process. `/actuator/health` reports health status and optional components/details; `/actuator/beans` reveals the bean inventory; `/actuator/startup` provides startup steps when `BufferingApplicationStartup` is configured.

In standard Spring Boot configurations, default HTTP exposure includes only `health`. Using `beans` or `startup` requires explicit enablement/exposure and caller restrictions. Keep health details at `never` or `when-authorized` with explicit roles. `beans` and `startup` expose internal metadata and belong strictly to admins/SREs on controlled networks.

Combine allowlist exposure, Spring Security authorization, management port/network policies, response minimization, and negative tests. Health probes only need status; operators may need details. Developers and SREs may need bean inventory or startup timings, whereas end users do not.

**Good observability gives enough visibility to make decisions, strictly within what the caller is permitted to see.** Never expose every endpoint for debugging convenience, never put secrets into health details or startup tags, and always test both permitted and denied access in the target deployment topology.
