# Choosing Allowed Endpoints to Expose by Environment in Spring Boot Actuator and JMX

## 1. Objectives

In a Spring Boot application, **Actuator** provides management endpoints to observe runtime state, health, metrics, logging, and certain operational actions. Spring Boot can expose these endpoints over **HTTP** and/or **JMX**, depending on configuration and endpoint conditions.

Not every endpoint should be present in every environment. An endpoint helpful to developers during debugging may disclose too much information or allow state changes when deployed to production. Therefore, you must design a policy for **which endpoints are enabled, which are exposed over HTTP, and which are exposed over JMX**, combined with security at the proper layer.

This lesson focuses on:

- Distinguishing `enabled` from `exposed` in Spring Boot Actuator.
- Configuring include/exclude separately for JMX and HTTP.
- Choosing policies for dev, staging, and production.
- Understanding the impact of Spring profiles and configuration precedence.
- Avoiding exposing endpoints with sensitive data or application-mutating operations.
- Verifying which endpoints are actually exposed, rather than just reading YAML files.

**Principle:** an endpoint should only be exposed to the tools and environments that genuinely need it. `exposure` selects the management surface, while authentication, authorization, TLS, network policy, and returned data must still be protected separately.

## 2. Distinguishing Enable, Exposure, and Access Rights

Three layers to understand:

1. **Availability/enabled:** is the endpoint created and active in the ApplicationContext? Usually governed by `management.endpoint.<id>.enabled` properties or global settings.
2. **Exposure:** is the endpoint published over a specific technology? For example, `management.endpoints.jmx.exposure.include` and `management.endpoints.web.exposure.include`.
3. **Security/access:** is a client allowed to connect and execute operations? For HTTP this is the security chain/network; for JMX it is connector/MBeanServer policies and runtime management controls.

General flow:

```text
Spring Boot Actuator endpoint
        |
        +-- enabled? -------- no --> no endpoint available
        |
        v yes
Endpoint exposure selection
        |
        +-- web include/exclude --> HTTP endpoint
        |
        +-- jmx include/exclude --> JMX MBean
                                            |
                                    JMX connector/auth
                                            |
                                   JConsole / JMX client
```

An endpoint can be enabled yet **not exposed over JMX**. Conversely, adding an endpoint name to the JMX include list cannot guarantee its presence if the endpoint is disabled, lacks a dependency, or fails another configuration condition.

Pay special attention to differences between Spring Boot versions. Additional properties such as endpoint-specific access may exist in newer versions and alter availability. When deploying to production, check the reference docs for the exact major/minor version running.

## 3. JMX and HTTP Exposure Configurations Are Independent

Typical properties:

```properties
management.endpoints.jmx.exposure.include=health,info,metrics
management.endpoints.jmx.exposure.exclude=env,beans

management.endpoints.web.exposure.include=health,info
management.endpoints.web.exposure.exclude=env,heapdump
```

Here, the JMX list and the HTTP list can differ. If `metrics` is included in JMX but not in web, JMX monitoring can access the Metrics endpoint while the corresponding HTTP URL is not exposed.

Conversely, `health` may be exposed over HTTP to serve a load balancer, while not necessarily needing JMX exposure if the system already runs health checks via another channel.

**Exclude wins over include** in exposure configuration: if an endpoint appears in both include and exclude for the same technology, the exclude setting removes that endpoint from the corresponding surface.

For production, prefer an explicit include list of needed endpoints instead of a wildcard exposing everything.

## 4. Profile-Based Configuration Examples

A shared configuration can restrict HTTP by default:

```yaml
# application.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health,info
```

In development, local tools may need additional endpoints for debugging:

```yaml
# application-dev.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,loggers
    jmx:
      exposure:
        include: health,info,metrics,beans,loggers,threaddump
```

In staging, the goal is usually to validate close to production while still allowing controlled diagnostics:

```yaml
# application-staging.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
    jmx:
      exposure:
        include: health,info,metrics,threaddump
```

In production, a narrower policy:

```yaml
# application-prod.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health,info,metrics
```

These are **design examples**, not a mandatory default list. If production does not need Actuator JMX, you can configure:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        exclude: "*"
```

If using a Spring Boot version that supports a global property to turn off JMX management exposure, you can also use the corresponding option per that version's documentation. Do not confuse disabling Actuator JMX exposure with completely disabling a JVM remote JMX connector.

## 5. Include and Exclude by Environment: Apply Carefully

Suppose a dev profile has:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "*"
        exclude: env,configprops,heapdump
```

When broad exposure is needed for debugging, still use an isolated development environment and avoid passing secrets into endpoints. However, wildcards have significant impact: if a new version or dependency adds an endpoint, that endpoint can appear automatically without modifying the configuration.

Therefore, production should favor an allowlist:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: health,info,metrics
```

Do not treat excluding a short list of sensitive endpoints as equivalent to an allowlist: an endpoint not listed in exclude can still be exposed if include is a wildcard.

In YAML, the `*` character must be placed in quotes so the parser does not treat it as an alias marker. In `.properties`, you can use `management.endpoints.jmx.exposure.include=*` per properties syntax.

## 6. Preliminary Recommendation Table by Environment

| Endpoint | Development | Staging | Production | Notes |
| --- | --- | --- | --- | --- |
| `health` | Usually expose | Usually expose | Usually expose over needed channel | Limit sensitive details |
| `info` | Can expose | Can expose | Can expose if content is safe | Build/commit metadata may disclose info |
| `metrics` | Useful | Useful | Depends on monitoring infra | May contain sensitive metric names and tags |
| `beans` | Only when debugging | Rarely needed | Usually do not expose | Discloses ApplicationContext structure |
| `env` | Needs control | Restricted | Do not expose broadly | Properties may disclose configuration |
| `configprops` | Controlled debug | Restricted | Do not expose broadly | Configuration structure may be sensitive |
| `loggers` | Convenient for debugging | As needed | Only for authorized operators | Can change runtime log levels |
| `threaddump` | When needed | Can allow for diagnostics | Only with incident procedure | May disclose thread names and internal activity |
| `heapdump` | Very restricted | Very restricted | Avoid permanent exposure | Heap dumps may contain secrets/PII |
| `shutdown` | Restricted and intentional | Rarely | Do not expose broadly | Stopping the app has severe side effects |

Not all of these endpoints are always present or exposable across every technology/version. This table helps classify needs and risks, not a guaranteed list of available endpoints.

## 7. Example Using Environment Variables Instead of Multiple YAML Files

If the system deploys via containers or orchestration, exposure can be controlled with environment variables:

```text
MANAGEMENT_ENDPOINTS_JMX_EXPOSURE_INCLUDE=health,info,metrics
MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=health,info
```

Spring Boot supports relaxed binding for environment variables in many cases. However, final configuration depends on property source precedence, profiles, command-line flags, and the platform. Therefore, verify the **effective** properties, not just the values sitting in one file.

For example, deployment manifests should use environment-specific variables:

```text
DEV:
  MANAGEMENT_ENDPOINTS_JMX_EXPOSURE_INCLUDE=health,info,metrics,beans

PROD:
  MANAGEMENT_ENDPOINTS_JMX_EXPOSURE_INCLUDE=health,info,metrics
```

Avoid letting every deployment arbitrarily override policy if the infrastructure requires governance. Sensitive environments should have CI/CD guardrails or platform policies to prevent uncontrolled wildcard exposure.

## 8. Endpoint-Specific Enabled Configuration

An endpoint can be turned off completely if not needed:

```yaml
management:
  endpoint:
    shutdown:
      enabled: false
```

Or in some cases:

```yaml
management:
  endpoint:
    env:
      enabled: false
```

When an endpoint is disabled, changing the exposure list does not make the endpoint available again. This is useful for high-risk endpoints that the organization does not want enabled on any channel.

With newer Spring Boot versions that have separate access policies, you must also consider access settings; do not assume `enabled` and `exposure` are the only two properties in every version.

**Operational note:** if you disable an endpoint that the monitoring system relies on, update the corresponding dashboards, alert rules, or health probes. These management configurations should be treated as operational contracts.

## 9. JMX Exposure Does Not Mean Opening Remote JMX

Spring Boot can register Actuator endpoints as MBeans in an MBeanServer even when the application **does not open a remote JMX port**. Putting an endpoint in `management.endpoints.jmx.exposure.include` only makes that endpoint eligible to appear through the JMX layer; it does not automatically configure the full RMI connector, authentication, or firewall.

For remote tools to connect, the JVM/container still needs a JMX connector and security policy. Therefore:

- Do not assume JMX is protected just because HTTP Spring Security requires login.
- Do not assume `management.server.port` creates a corresponding remote JMX port.
- Do not assume `management.endpoints.web.exposure.exclude` blocks an endpoint in JMX.
- Do not assume `management.endpoints.jmx.exposure.exclude` blocks an endpoint over HTTP.

HTTP and JMX are two separate exposure technologies. Each access path needs its own security policy.

## 10. Restricting HTTP Actuator with Spring Security

For HTTP, Spring Security can protect actuator requests. An illustrative example uses `EndpointRequest` to allow only health publicly and require authentication for other endpoints:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ActuatorHttpSecurityConfig {
    @Bean
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                .permitAll()
                .anyRequest().authenticated()
            );
        return http.build();
    }
}
```

This is an example for a Spring Boot/Spring Security generation with the matching configuration API. In a real application, you must have security chains for the remaining traffic and consider CSRF, sessions, authentication providers, and the management endpoint port/context path. This example does not automatically protect a JMX connector.

If health is public but returns internal component details, limit the health detail configuration. Allowing public HTTP GET health checks should not mean disclosing database URLs or sensitive infrastructure info.

## 11. Configuring Health Details by Environment

The health endpoint is often needed for orchestration, yet the level of detail varies by caller. Example:

```yaml
management:
  endpoint:
    health:
      show-details: never
```

Or a secured deployment:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
```

For `when-authorized`, you must understand how roles/authorization are determined by Actuator in the version and technology used. Do not assume the exact same HTTP role check automatically applies identically to JMX.

For production, you can choose a public health summary while diagnostic details are granted only to operators over a separately controlled channel.

## 12. Separating Endpoint Exposure from Data Policy

Even a read-only endpoint can disclose:

- Runtime configuration, environment variables, URLs, and connection details.
- Spring bean graph, class names, packages, and dependency names.
- Metric tags containing user IDs or tenant IDs if the application attaches unsafe tags.
- Thread names, stack traces, or debug data.
- Build metadata, SCM commits, or deployment information.

Do not put secrets into an endpoint and rely solely on it not appearing on a UI page. JMX clients can access metadata and attributes via API.

Data classification should start at the source. In a custom actuator endpoint, return only safe summaries and avoid returning raw object graphs. Even well-protected environments still need data minimization, because credentials or accounts can be leaked or over-privileged.

## 13. Custom Actuator Endpoints and Exposure Conditions

Spring Boot supports custom actuator endpoints via annotations such as `@Endpoint`, with operations marked `@ReadOperation`, `@WriteOperation`, or `@DeleteOperation` according to the API version.

Example:

```java
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "queueSummary")
public class QueueSummaryEndpoint {
    private final QueueMetrics metrics;

    public QueueSummaryEndpoint(QueueMetrics metrics) {
        this.metrics = metrics;
    }

    @ReadOperation
    public QueueSummary summary() {
        return new QueueSummary(
            metrics.pendingCount(),
            metrics.runningCount()
        );
    }
}

`QueueMetrics` is an application-defined service; `QueueSummary` is a DTO with two aggregate counts. For custom endpoints, metadata id and operations must conform to the endpoint rules of the Spring Boot version in use. The example illustrates the concept and does not represent every HTTP/JMX operation mapping variant.

This endpoint also needs to be enabled and exposed over the corresponding technology. If you want it exposed in dev but not production, add its id to the dev profile's include list and omit it from the prod include list.

**Do not automatically carry a custom endpoint with write/delete operations into production** without an authorization and validation policy; those operations can alter or delete application state.

## 14. Endpoints and Spring JMX @ManagedResource Are Two Coexisting Mechanisms

Spring Framework supports custom JMX MBeans via `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`, and `MBeanExporter`. Spring Boot Actuator supports its own endpoint abstraction that can be exposed over JMX.

Example:

```text
Spring custom @ManagedResource
  -> MBeanExporter
  -> JMX ObjectName

Spring Boot Actuator @Endpoint
  -> Actuator JMX exposure
  -> JMX MBean
```

The `management.endpoints.jmx.exposure.include` property targets **Actuator endpoints** and should not be treated as an automatic filter applied to every `@ManagedResource` manually exported by the application.

Therefore, when reducing the production JMX surface, check both groups: Actuator endpoint exposure and custom `MBeanExporter` beans/autodetection. Excluding `env` does not prevent another custom MBean from exposing the same sensitive data via its own getter.

## 15. Verifying the Effective Configuration

Do not look only at `application-prod.yml`. To confirm actual exposure:

1. Identify the active profiles at runtime (`spring.profiles.active`) and PropertySources precedence.
2. Check management properties loaded from environment, command line, config server, and deployment manifests.
3. Inspect the list of JMX MBeans actually registered in the right MBeanServer.
4. Check HTTP actuator discovery and access on the configured path/port (if permitted).
5. Use an account with real monitoring/operator permissions to verify behavior, rather than using an admin account as a stand-in.
6. Compare the exposed endpoint list against the environment-approved list.

With JMX, you can query MBeans belonging to the appropriate management namespace:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names = server.queryNames(
    new ObjectName("org.springframework.boot:*") ,
    null
);

names.stream()
     .map(ObjectName::getCanonicalName)
     .sorted()
     .forEach(System.out::println);
```

The domain in the example illustrates a common Spring Boot configuration; if a different JMX domain was configured, change the pattern accordingly. Do not use one specific pattern to claim that all Actuator MBeans have appeared.

## 16. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Endpoint does not appear in JMX | Not included, endpoint disabled, JMX unsupported, or wrong MBeanServer | Check enabled, exposure, version, and server |
| Dev exposes properly, prod misses needed metric | Prod profile include omits id or property overridden | Check active profiles and property precedence |
| HTTP endpoint hidden but still visible in JConsole | Web and JMX exposures are two separate lists | Adjust `management.endpoints.jmx.exposure` |
| JMX endpoint hidden but HTTP still accessible | JMX exclude does not control HTTP | Adjust `management.endpoints.web.exposure` and security |
| Enabling wildcard causes new endpoint to appear after upgrade | Include `*` expands to whatever endpoints are present | Prefer an allowlist in production |
| Loggers can be changed remotely | Endpoint exposes write operation and client has permission | Limit exposure and authorization |
| Public health discloses internal details | `show-details` too broad | Narrow data, configure groups/authorization |
| Custom `@ManagedResource` missing from Actuator list | Custom JMX MBean is not part of the Actuator endpoint catalog | Check `MBeanExporter` separately |

## 17. Operational Recommendations Following Least Privilege

**Development:** you may need extensive information to analyze errors. Only expose extra endpoints when needed; if using wildcards, the environment must be isolated and contain no real sensitive data.

**Staging:** prefer a configuration close to production to test deployment and monitoring. Enable extra diagnostics only for a bounded window/controlled form, not permanently wide open.

**Production:** use an allowlist of necessary endpoints, such as `health`, `info`, and a subset of metrics if used by the monitoring system. Endpoints that mutate state or expose internal structure require special protection or should not be exposed.

In particular, avoid using unauthenticated or unencrypted remote JMX on untrusted networks. For HTTP, protect actuator using network policies, authentication, authorization, and restricted response details.

Changing an exposure policy is a governance change: monitoring, alerting, or operational runbooks may depend on an endpoint. Therefore, manage configuration as code, with review and verification of behavior in the target environment.

## 18. Mental Model

```text
                    Spring Boot application
                              |
                       Actuator endpoints
                              |
                   enabled / access policy
                              |
                    +---------+---------+
                    |                   |
              WEB exposure         JMX exposure
                    |                   |
               HTTP path           JMX MBean
                    |                   |
              Spring Security      JMX connector
              + network policy     + JMX permissions
                    |                   |
                   Client / monitoring tools
```

**Conclusion:** to choose which endpoints are allowed to be exposed per environment, design the **set of enabled endpoints**, the **HTTP exposure list**, and the **JMX exposure list** separately, then apply security in the appropriate technology. Spring profiles help configure dev/staging/prod differently, but you must verify the effective values after deployment. In production, prefer a narrow allowlist, avoid wildcards, and do not confuse Actuator's exposure mechanism with all custom MBeans in Spring Framework.
