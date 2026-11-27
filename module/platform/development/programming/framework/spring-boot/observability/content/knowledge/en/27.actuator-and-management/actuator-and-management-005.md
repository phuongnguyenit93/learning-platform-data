# Including and Excluding Endpoints in Spring Boot Actuator

In the **Actuator and Management** chapter of the **SPRING_BOOT_OBSERVABILITY** module, including and excluding endpoints are the two mechanisms that control which endpoints are exposed over the management interface. Spring Boot Actuator provides endpoints for health checks, metrics, application information, and administrative operations. An endpoint existing in the application does not mean it is automatically made public over HTTP or JMX.

By default, Actuator only exposes a limited set of web endpoints. Administrators can configure `include` to allow a set of endpoints and `exclude` to remove endpoints from exposure. This is one layer of attack-surface control and must work alongside Spring Security, network policies, authentication/authorization, and environment-specific configuration.

In the **SPRING_BOOT_OBSERVABILITY** module, Actuator is the window for inspecting Spring Boot health, metrics, and operational state. Misconfiguring exposure can leak environment details, configuration, or the bean graph, or expose endpoints capable of altering application state. This lesson explains include/exclude semantics, HTTP/JMX exposure, configuration examples, sensitive endpoints, and how to verify what is actually accessible.

## 1. Existing Endpoints vs. Exposed Endpoints

An Actuator endpoint can be viewed across three layers:

1. **Endpoint availability:** whether the endpoint is provided by dependencies/auto-configuration and runtime conditions.
2. **Exposure:** whether the endpoint is exposed over web or JMX.
3. **Access/security:** whether the caller is allowed to access the endpoint under access policies and security rules.

```text
Actuator endpoint implementation
          |
          v
   Endpoint available?
          |
          v
   Exposure configuration
      |             |
      v             v
    HTTP           JMX
      |             |
      v             v
 Security / access controls
          |
          v
      Authorized caller
```

For example, the metrics endpoint may exist on the classpath without being exposed over HTTP. If calling `/actuator/metrics` returns 404, you cannot conclude the metrics registry is broken; the endpoint might not be included or the management base path may differ.

Conversely, including an endpoint only controls exposure. It does not authenticate callers, encrypt data, or replace authorization. Do not expose sensitive endpoints to the internet just because the Spring Security dependency is present.

## 2. What Do Include and Exclude Mean?

Common web exposure properties:

- `management.endpoints.web.exposure.include`: list of endpoints exposed over HTTP.
- `management.endpoints.web.exposure.exclude`: list of endpoints excluded from HTTP exposure.

Example:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
        exclude: env,configprops
```

This example requests exposing health, info, metrics, and prometheus over the web while excluding env and configprops from web exposure. The actual available endpoints depend on dependencies and runtime conditions. Exclude takes precedence when an endpoint appears in both include and exclude; therefore, use exclude as an explicit deny layer.

If include is not configured, Spring Boot uses the default web exposure set for the corresponding version (usually only health). When setting include explicitly, treat it as an allowlist of desired endpoints. Do not assume every new endpoint added by a dependency will automatically be exposed.

The wildcard `*` can be used to represent all endpoints, but exposing all web endpoints is generally unsuitable for production. If a wildcard is used, you must exclude endpoints that should not be public and enforce strict security/network controls; an explicit allowlist is usually easier to review.

## 3. Configuring Include for HTTP

A narrowly scoped production configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
```

If the application needs to query metrics via the Actuator metrics endpoint for internal diagnostics:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Only include metrics when there is a need to query this endpoint. In many systems, the Prometheus scrape endpoint is the primary metrics collection interface, while `/actuator/metrics/{metricName}` is for direct inspection.

The management base path can be changed:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info,prometheus
```

The paths can then be `/manage/health`, `/manage/info`, and `/manage/prometheus` instead of `/actuator/...`. Base path is not a security mechanism; changing the path does not stop callers from probing for endpoints.

## 4. Explicitly Excluding Endpoints

Example removing endpoints from web exposure:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: env,configprops,heapdump,threaddump,loggers
```

This example illustrates the semantics, not a recommended production configuration. A wildcard include widens the web surface; excluding a few endpoints does not guarantee the remaining list is safe. A new dependency can introduce an endpoint that the wildcard automatically exposes.

In particular, do not use a wildcard include as a quick fix for a 404 endpoint error in production. Identify the needed endpoints and include them explicitly. If there are endpoints that must not be accessible, exclude them explicitly and check security policies independently.

## 5. Web Exposure and JMX Exposure Are Separate Configurations

Actuator can expose endpoints over HTTP or JMX. Web exposure settings do not automatically determine JMX exposure.

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
    jmx:
      exposure:
        include: health,info,metrics
```

In this example, HTTP only exposes health/info/prometheus, while JMX exposes health/info/metrics. If the application does not use JMX, consider disabling JMX exposure or configuring an allowlist aligned with your management platform.

Do not assume an endpoint excluded from the web is also removed from JMX. Check both transports if the runtime enables JMX. Similarly, inspect separate management ports/interfaces if the application isolates management traffic from application traffic.

## 6. Which Endpoints Are Commonly Used?

| Endpoint | Purpose | Considerations When Exposing |
| --- | --- | --- |
| health | Overall health status | Minimal status may be public; details require protection |
| info | Application info provided by config | Publish only approved fields |
| metrics | Query metrics in registry | May reveal metric/tag names and internal state |
| prometheus | Expose metrics for Prometheus scrape | Restrict access to trusted scrapers |
| env | Environment properties | May leak configuration and secrets if not sanitized |
| configprops | Configuration properties | May reveal application structure/configuration |
| beans | Bean definitions | Internal information about application structure |
| conditions | Auto-configuration conditions | Useful for debugging, but exposes runtime details |
| mappings | Request mappings | May expose internal routes |
| loggers | View/change log levels | Can change verbosity and increase log volume |
| heapdump | Generate heap dump | May contain sensitive data, resource-intensive |
| threaddump | Thread dump | May reveal thread names, stacks, and runtime info |
| shutdown | Shut down application if enabled | Dangerous operational endpoint; never expose casually |

An endpoint may not exist if the corresponding dependency or condition is absent. The list and semantics depend on the Spring Boot version. Check the reference documentation for your exact version before configuring.

## 7. Include Does Not Replace Authentication and Authorization

Even the health or prometheus endpoints can reveal useful information to an attacker, such as which database a service depends on, which broker is used, or which application version is running. Decide which endpoints may be accessed anonymously and which belong strictly to the monitoring network.

Key principles:

- Explicitly expose only required endpoints.
- Open management ports/interfaces only within trusted networks.
- Require authentication for non-public management endpoints.
- Apply authorization by role/service identity.
- Restrict health details and sensitive data.
- Monitor access logs/audits for administrative actions.

If Spring Security is present, the application needs security rules for management endpoints. Include configuration does not create those rules automatically. Example security matchers and DSL depend on the Spring Security version, management port, and filter chain structure; configure them for your specific app rather than copying a generic rule across all deployments.

Do not allow all requests to `/actuator/**` just because Prometheus needs to scrape `/actuator/prometheus`. You can create a separate rule for the scraper identity and another for health probes, while administrative endpoints require stronger roles.

## 8. Health Endpoint and Health Details

The health endpoint is commonly used by load balancers, orchestrators, and monitoring systems. Health can be exposed publicly with a minimal response, while only authenticated callers can view component details.

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
```

Valid values and authorization behavior depend on the Spring Boot version/configuration. Do not enable `always` in production if the response contains database names, brokers, disk paths, or internal dependencies. Note that health groups/readiness/liveness are separate settings for health content and grouping; exposure decides which endpoint groups are accessible over a transport.

Health details are not the same as endpoint include/exclude. A health endpoint can be exposed yet only return overall status to unauthorized callers; authorized callers receive details per policy.

## 9. Configuration by Environment Profile

A common pattern is keeping the base configuration safe and expanding in a controlled manner in internal profiles:

```yaml
# application.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

```yaml
# application-prod.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
```

```yaml
# application-dev.yml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: shutdown
```

Do not let the `dev` profile become accidentally active in production. Check profile activation, environment variables, command-line overrides, and config servers; properties can be overridden by configuration sources with higher precedence than YAML files.

## 10. Endpoint Exposure and Access Policy by Version

Newer Spring Boot versions may provide additional endpoint access configuration, such as choosing which endpoints are permitted by access policy and limiting the data endpoints return. These properties differ from exposure:

- **Exposure** determines whether the endpoint is published over web/JMX.
- **Access policy** determines whether the endpoint is allowed to be accessed under Actuator's access mechanism.
- **Security authorization** determines which callers are permitted access.

Do not confuse these three layers. An endpoint disabled by access policy does not become safe just because its path is hard to guess; and an exposed endpoint still needs network/security controls. Property names and default access policies vary across Spring Boot releases; consult the metadata for your deployed version.

## 11. Verifying Which Endpoints Are Actually Exposed

After configuring, verify from the runtime rather than only reading YAML:

1. Start the application with profiles and environment variables matching deployment.
2. Call the management base path or endpoint discovery links if enabled.
3. Verify included endpoints return the expected responses.
4. Verify excluded endpoints are unreachable over HTTP.
5. If JMX is enabled, verify JMX exposure separately.
6. Test security rules with anonymous callers and role-bearing callers.
7. Confirm the health response does not leak component details to unauthorized callers.
8. Verify which management port/interface exposes the endpoints.

Example checks:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/prometheus
curl -i http://localhost:8080/actuator/env
```

Expectations depend on configuration: health/prometheus may be allowed per policy; env must not be exposed or must be protected. Status codes alone are not enough to distinguish between a missing endpoint, unexposed endpoint, denied access, or security filter block. Inspect responses, application logs, and security configuration in a test environment.

### Verification Matrix

| Endpoint | Included? | Excluded? | Outcome to Verify |
| --- | --- | --- | --- |
| health | Yes | No | Probe reachable, details match policy |
| info | Yes | No | Only approved information shown |
| prometheus | Yes | No | Scraper identity can access |
| env | No | Yes or outside allowlist | Callers cannot read environment |
| shutdown | No | Yes | No shutdown action from web |

This is an illustrative matrix; adjust according to endpoint availability and application policy.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using wildcard include in production | New dependencies may expose new endpoints | Explicit allowlist |
| Thinking include is authentication | Unauthenticated callers can access if security does not block | Configure Security/network separately |
| Excluding from web only, forgetting JMX | Endpoint may still be exposed via JMX | Check each transport |
| Public env/configprops | Leaks configuration or internal metadata | Do not expose or strictly protect |
| Public heapdump | Data leakage risk and heavy resource load | Restrict access permissions and process |
| Using health details always | Leaks dependency/component names | Use when-authorized or suitable policy |
| Changing base path for "security" | Endpoints can still be discovered | Authentication, authorization, and network controls |
| Testing only in local profile | Production has different overrides | Test deployment-like profiles/configs |

## 13. Scenario Exercise

A Spring Boot application currently uses this configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: shutdown
```

The operations team only needs health probes and Prometheus scrapes. The application also has env, configprops, beans, mappings, loggers, and heapdump endpoints available.

**Questions:**

1. In principle, which endpoints does the current configuration expose?
2. Why is excluding only shutdown insufficient?
3. How should the production allowlist be written?
4. Does including health mean every caller can view health details?
5. How should HTTP and JMX exposure be checked?

**Analysis Hints:**

- Wildcard allows all eligible endpoints to be exposed over the web; excluding shutdown only removes that endpoint.
- Endpoints such as env, configprops, beans, mappings, loggers, or heapdump can disclose information or allow mutations.
- If only health and Prometheus are needed, use an explicit allowlist `health,prometheus` (adding `info`/`metrics` if there is a clear purpose).
- Exposure does not govern authentication/authorization or health detail visibility. Configure health details for authorized callers.
- Inspect web exposure and JMX exposure separately; apply security/network policies for scrapers and management callers.

### Completion Checklist

| Topic | Can Explain/Verify |
| --- | --- |
| Endpoint availability | Distinguish available endpoints from exposed ones |
| Include | Create an allowlist of required endpoints |
| Exclude | Remove endpoints from exposure and understand precedence |
| Wildcard | Recognize the risks of including everything |
| HTTP/JMX | Configure and verify each transport separately |
| Security | Do not confuse exposure with authentication/authorization |
| Health details | Restrict component information by permission |
| Profiles | Control dev/prod differences and property overrides |
| Access policy | Distinguish exposure, Actuator access, and Spring Security |
| Verification | Test allowed endpoints, blocked endpoints, and callers with different roles |

**Takeaway:** Include and exclude control which Actuator endpoints are exposed over a transport; they do not authenticate callers. Use an explicit allowlist for production, check HTTP and JMX separately, restrict health details, and protect management endpoints with security/network policies. Endpoints such as env, configprops, beans, mappings, loggers, and heapdump can disclose sensitive data or modify state, so open them only when clearly justified. Verify configuration in the target profile/runtime and test both allowed and blocked endpoints.