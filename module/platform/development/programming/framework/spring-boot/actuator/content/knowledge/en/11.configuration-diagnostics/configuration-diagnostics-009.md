# Restricting Structural and Configuration Information Exposed in Production

Actuator helps operators observe a running application. The very data useful for diagnostics can also reveal how the system is organized: bean names, API paths, configuration sources, implementation classes, build info, or internal service addresses.

In production, you must define **who needs to know what information, over which channel, and for what duration**. A load balancer typically only needs to know whether the application is ready to accept requests; it does not need a bean list or the full configuration.

This lesson uses properties of **Spring Boot 3.3.x**. The Java example targets **Java 21, Spring MVC/Servlet, and Spring Security 6.x**; it is a configuration class integrated into an existing application, not a standalone Java program. Access rules in the example must be paired with the application's authentication mechanism.

## 1. Data to restrict goes beyond passwords

Two groups must be distinguished:

- **Sensitive configuration values**: passwords, tokens, connection strings with credentials, or private keys.
- **Structural and operational context information**: key names, configuration source names, profiles, class names, paths, dependent services, OS details, and build metadata.

The second group can still appear after values are replaced with `******`. For instance, the key name `partner.payment.internal-url` already reveals an integration dependency; a source containing a file path can reveal deployment layout.

| Endpoint or data category | Information that may be exposed | Usually appropriate handling |
| --- | --- | --- |
| `env` | Environment properties, sources, profiles, and declaration origins | Closed in normal production mode; open only under control when diagnostics are needed |
| `configprops` | Bound configuration groups, bean properties, and inputs | Restrict to operators with specific duties |
| `beans`, `mappings`, `conditions` | Beans, classes, API paths, and auto-configuration condition results | Keep internal; do not expose merely for lookup convenience |
| `health` | Status, component names, and check details | Return only minimal info to public callers |
| `info` | Information supplied by contributors, potentially including Git and build | Review each field before opening |
| `threaddump`, `heapdump`, `logfile` | Execution threads, memory, or logs | Treat as internal investigation data; may contain sensitive data |
| `httpexchanges` | Collected HTTP exchange information | Review both collection config and read permissions |
| `metrics`, `prometheus` | Metric names, tags, and operational characteristics | Open only to required monitoring systems; audit tags |

Some endpoints only exist when corresponding dependencies, beans, or configurations are present. Not seeing an endpoint in one run does not prove the next deployment will still omit it.

Beyond reading data, some endpoints also support state-mutating operations, such as `loggers`. When reviewing permissions, examine allowed operations as well, not just endpoint names.

## 2. Five control layers with distinct responsibilities

| Layer | Question to answer | Example |
| --- | --- | --- |
| Endpoint enablement | Is this endpoint needed in the application? | `management.endpoint.env.enabled` |
| Channel exposure | Is the endpoint mapped over HTTP or JMX? | `management.endpoints.web.exposure.include` |
| Network reachability | Which hosts or processes can connect? | Separate management port, listen address, network rules |
| Authentication & authorization | Who is the caller and which endpoints may they read? | `SecurityFilterChain`, role `OPS` |
| Response content | Which fields and values may the caller receive? | `show-values`, `show-details`, `show-components` |

Someone authorized to view values also needs permission to access the endpoint. An endpoint mapped over HTTP can still be blocked by a security layer. A port inside an internal network still needs access restricted to the intended consumers.

In Spring Boot 3.3, a disabled endpoint is removed from the application context by Actuator's mechanism. If you only want to change exposure channels, use exposure settings. Precedence has `exclude` override `include`; therefore check both when an endpoint does not appear as expected.

Enablement and exposure mechanisms are described in [Actuator Endpoints — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

## 3. Allowlist-based production setup

A baseline policy might be:

- Enable and expose only `health`.
- Have `health` return overall status without a component tree or details.
- Expose no endpoints over JMX in this deployment profile.
- Do not open the Actuator link discovery page.
- Keep `env` and `configprops` values masked if intentionally enabled later.
- Do not automatically publish Git, build, or environment details via built-in `info` contributors.

Place the following into `src/main/resources/application-prod.yml`:

```yaml
spring:
  jmx:
    enabled: false

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include:
          - health
      discovery:
        enabled: false
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      enabled: true
      show-details: never
      show-components: never
    env:
      show-values: never
    configprops:
      show-values: never
  info:
    defaults:
      enabled: false
    env:
      enabled: false
    git:
      enabled: false
    build:
      enabled: false
    java:
      enabled: false
    os:
      enabled: false
    process:
      enabled: false
```

You must activate the `prod` profile in the deployed process, such as via `SPRING_PROFILES_ACTIVE=prod`. Simply creating `application-prod.yml` does not activate the profile automatically.

### How to read this configuration

`enabled-by-default: false` switches endpoint enablement to explicit opt-in. `health.enabled: true` re-enables the needed endpoint; the HTTP list contains only `health`.

`show-details: never` reduces check detail output; `show-components: never` omits the component tree. A healthy system without extra configuration modifying responses can return:

```json
{"status":"UP"}
```

The status may differ from `UP`, accompanied by the corresponding HTTP code. Reducing response payload must not turn a failing state into a false success.

`env.show-values: never` and `configprops.show-values: never` only set value display policies; these two lines do not enable endpoints that are disabled.

`discovery.enabled: false` disables the links page at the Actuator root path. Exposed endpoint paths still need their own access policies. Changing base path from `/actuator` to another name merely moves the access location.

### Effects and limits of the `info` section

In Spring Boot 3.3, Git or build contributors can activate when corresponding resources exist. The configuration above disables the listed built-in contributors rather than assuming build metadata always resembles development environments.

`management.info.defaults.enabled: false` disables contributors enabled by default; do not interpret it as a command that removes all information the application might publish itself. Any application-authored `InfoContributor` must be reviewed separately.

If `info` is opened later, inspect the actual response and retain only fields serving identified needs. Do not place passwords under `info.*` expecting `env`'s masking policy to protect this endpoint.

## 4. Value masking still needs reduced exposure

In Spring Boot 3.3, `env` and `configprops` mask values by default. There are three policies to know:

| `show-values` value | Meaning |
| --- | --- |
| `never` | Keep values masked |
| `when-authorized` | Allow users determined to be authorized to view unmasked values |
| `always` | Display values to everyone who can reach the endpoint, except parts handled by custom sanitizers |

You must separate **endpoint access permission** from **value-viewing permission**. Setting `show-values` does not replace HTTP access control.

When using `when-authorized`, the endpoint's `roles` setting specifies roles allowed to view values. If no roles are configured, all authenticated users qualify by default to view values. Explicitly specify operational roles instead of relying on a broad "authenticated" condition.

Masked responses can still contain:

- Property names or configuration groups.
- Source names, profiles, file paths, and declaration locations.
- Object structures from which capabilities in use can be inferred.

Therefore, an operational requirement merely needing to know whether the application is alive is not sufficient reason to expose all of `env`, even with `show-values=never`.

If a custom `SanitizingFunction` is used, it can still mask values even when the policy permits display. Verify actual output using non-sensitive sample data. Masking coverage on supported endpoints does not automatically extend to logs, custom endpoints, error responses, or arbitrary memory contents.

## 5. HTTP authorization for a Servlet application

Suppose an application has dependencies:

```text
org.springframework.boot:spring-boot-starter-web
org.springframework.boot:spring-boot-starter-actuator
org.springframework.boot:spring-boot-starter-security
```

The class below illustrates two security chains:

1. Requests to exposed Actuator endpoints: `health` may be called without logging in; remaining endpoints require role `OPS`.
2. Remaining requests: denied within the scope of the example.

```java
package learning.operations;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                    .permitAll()
                .anyRequest().hasRole("OPS"));
        http.httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .anyRequest().denyAll());
        http.httpBasic(withDefaults());
        return http.build();
    }
}
```

Place this class within the application's component-scan scope. It does not include `main`, user creation mechanisms, or an identity provider.

### Things to understand before integrating

- `EndpointRequest` locates endpoints using Actuator's mechanism. A matcher using `HealthEndpoint.class` covers paths belonging to the health endpoint, so review health groups and component paths as well.
- `@Order(1)` places the Actuator chain before the catch-all chain. Spring Security uses the first matching chain.
- `hasRole("OPS")` checks the `ROLE_OPS` authority per Spring Security's default role convention.
- The second chain intentionally denies everything else to illustrate a complete boundary. When integrating into a service with business APIs, replace it with a designed and tested business security policy; copying this class verbatim will deny those APIs.
- HTTP Basic is a sample authentication mechanism. For production connections, protect credentials with HTTPS or a properly designed secure transport. Use the application's identity system instead of adding hardcoded shared accounts in code.
- The example retains default CSRF protection. Tests here use `GET` only.

When declaring a custom `SecurityFilterChain`, Spring Boot's auto-configured Actuator security yields control to the application. You must cover both Actuator requests and remaining requests; do not assume a chain matching only Actuator will automatically protect business APIs.

With the production settings from the previous section, endpoints other than health remain disabled. Having role `OPS` does not make a disabled endpoint appear automatically. The security chain also covers cases where an endpoint is intentionally enabled in diagnostic mode.

Matcher reference: [EndpointRequest API — Spring Boot 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

## 6. Controlled diagnostics instead of permanent expansion

A configuration incident may require reading `env` or `configprops`. When that need arises, define beforehand:

- Which property or configuration group needs inspection.
- Which operator or operational account is authorized to read it.
- Which application replica and network channel are used for diagnostics.
- End time, where evidence is stored, and who is responsible for revoking access.

You can prepare `application-ops.yml` as an intentional additive configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - env
          - configprops
  endpoint:
    env:
      enabled: true
      show-values: never
    configprops:
      enabled: true
      show-values: never
```

This approach assumes profiles activate in the order `prod,ops`, with the production settings from earlier still loaded. The later profile's HTTP exposure list is explicitly set to `health,env,configprops`. Other endpoints remain disabled per default policy.

An additive profile file does not act as an expiration mechanism by itself. Deployment systems and operational procedures must handle enabling it on time, turning it off after use, and verifying the final configuration.

With the security layer from Section 5:

| Caller | Minimal health | `env` and `configprops` in `prod,ops` mode |
| --- | --- | --- |
| Unauthenticated | Can read | Denied |
| Authenticated without `OPS` role | Can read | Denied |
| Holding `OPS` role | Can read | Can read, though values remain masked by `show-values: never` |

If source and structural details are enough to diagnose, keep the masking policy intact. Prefer targeted queries like `/actuator/env/demo.region` or `/actuator/configprops/demo` when reading; however, choosing a narrow URL in an operator's tool does not restrict permission to call other URLs on the same endpoint.

### When viewing values is genuinely required

If the task requires viewing unmasked values, you can replace the display policy in the controlled diagnostic configuration using four properties:

```properties
management.endpoint.env.show-values=when-authorized
management.endpoint.env.roles=OPS
management.endpoint.configprops.show-values=when-authorized
management.endpoint.configprops.roles=OPS
```

This replaces the corresponding display policy, rather than being a second `management` YAML block pasted into the same YAML document.

Under the HTTP policy illustrated, anyone without role `OPS` is denied before receiving a response. Users with that role can see unmasked values, except parts still handled by custom sanitizing functions.

If another HTTP policy allows regular users to access the endpoint, `roles=OPS` on the display layer only keeps values masked for them; structural details can still be returned. Both permission layers must be evaluated.

Once diagnostics finish, return the process to the normal production profile and re-verify the endpoint from the exact access path used. Do not merely edit a file in source code and assume closing the endpoint is complete.

## 7. Separating the management path when appropriate for deployment

If the product has a dedicated management path, an additional configuration might be:

```yaml
server:
  port: 8080

management:
  server:
    port: 9091
    address: 127.0.0.1
```

Then the main application uses port `8080`, while Actuator listens on loopback at port `9091`. In Spring Boot 3.3, a separate management address is configured like this only when the management port differs from the main port.

Choose the address according to the actual deployment model. Loopback belongs to the process or container network namespace; a monitoring tool on another host cannot connect to it automatically. If external tools need to connect, design internal addressing, network policies, and authentication appropriately.

Points to check:

- Does the load balancer or reverse proxy also forward the management port to the Internet?
- Can non-operational hosts connect directly to that port?
- Is the separate management port or path protected by the intended authorization policy?
- Which port must probes call, and do they still accurately check the main application's ability to serve?

A working management port does not guarantee the business port is operating normally. When using health groups or additional paths like `/livez`, `/readyz`, inspect both routing and security for those paths.

Reference on setting port and address: [Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### Check JMX and other channels too

Restricting HTTP does not automatically restrict JMX. The production settings in Section 3 exclude Actuator endpoints from JMX exposure and disable Spring-managed JMX in this profile.

Those settings are not a kill switch for every JVM MBean, third-party library MBean, or remote JMX configuration started by the process. When the platform enables remote JMX, inspect connection permissions and authentication for that channel separately.

In particular, do not copy HTTP value-viewing role assumptions over to JMX: under `when-authorized` on supported endpoints, JMX treats callers as authorized to view values. Therefore, securing the JMX channel and choosing which endpoints are exposed on it remain mandatory design tasks.

Reference: [Monitoring and Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

## 8. Verifying against the live process

### 8.1. Confirming the exact configuration in effect

Before testing HTTP, confirm the right build, profile, overriding sources, and target address. Command-line arguments, environment variables, or external configuration can make actual values differ from the production file inside the JAR.

Do not expose `env` publicly just to prove `env` is closed. Use deployment manifests, process configuration, integration tests, and observe responses over authorized management channels.

When multiple application replicas exist, check all replicas or ensure test requests reach the intended replica. An un-updated replica can keep exposing data even after the observed replica has closed it.

### 8.2. Checking the health response

Suppose the example runs on the verification host at `127.0.0.1:8080`, sharing a port for business and management HTTP:

```shell
curl -i "http://127.0.0.1:8080/actuator/health"
```

In Windows PowerShell, use `curl.exe` if `curl` is a PowerShell alias.

For a healthy test application, the expected body is:

```json
{"status":"UP"}
```

There are no `components`, `details`, database names, disk paths, or connection details in this response. If custom health groups exist, check each group: a group-specific setting can give a different visibility level from the global setting.

Test further:

```shell
curl -i "http://127.0.0.1:8080/actuator/health?show-details=always"
```

Arbitrary URL query parameters do not override server-side configuration properties. In the example, the response still has no component tree or details.

### 8.3. Checking unexposed endpoints

In `prod`-only mode, run these requests:

```shell
curl -i "http://127.0.0.1:8080/actuator/env"
curl -i "http://127.0.0.1:8080/actuator/configprops"
curl -i "http://127.0.0.1:8080/actuator/beans"
curl -i "http://127.0.0.1:8080/actuator/mappings"
curl -i "http://127.0.0.1:8080/actuator/conditions"
curl -i "http://127.0.0.1:8080/actuator/info"
curl -i "http://127.0.0.1:8080/actuator"
```

Do not expect every URL to return the exact same code:

| Response code | Meaning to verify |
| --- | --- |
| `401` | Request blocked because no accepted credentials were provided |
| `403` | Policy denied access |
| `404` | No matching resource at the requested path |
| `200` | Must inspect body to verify which data is actually returned |

A `401` for an anonymous caller only proves that specific call was blocked. It does not prove the endpoint is disabled or that higher-privileged callers cannot read it.

Repeat with an operational account provisioned in the test environment. Under the health-only production policy, even someone with the `OPS` role receives no configuration or structural data from disabled endpoints.

With HTTP Basic on the test host, you can use:

```shell
curl -i --user ops "http://127.0.0.1:8080/actuator/env"
```

This lets `curl` prompt for the password instead of placing the password directly on the command line. The `ops` account must be supplied by the application's identity mechanism; the username alone does not create the `OPS` role.

If the system uses a separate management port, different base path, or HTTPS, use the actual deployment address instead of the example's address.

### 8.4. Checking diagnostic mode and external paths

In `prod,ops` mode:

1. Unauthenticated callers and callers with the wrong role cannot read `env`, `configprops`.
2. Callers with role `OPS` can read responses, yet values remain masked under the `never` policy.
3. When intentionally switched to `when-authorized`, use a non-sensitive sample value to verify authorized callers see it.
4. Endpoints absent from the diagnostic list still expose no data.
5. After closing diagnostic mode, repeat the test with the operational account.

Test through both public routes and internal routes. A proxy blocking `/actuator` might protect the public path while the direct service port still exposes data to a wider network scope than intended.

Verification evidence should record the address or route type, timestamp, build, caller type, response status code, and fields permitted to appear. Avoid saving full real configuration into screenshots or test logs when you only need to prove one property.

## 9. Maintaining observability without overexposing

A health-only list is the example's starting point. If production needs Prometheus, add the corresponding endpoint intentionally: required dependency, enablement, exposure, credentials dedicated to the scraping system, and proper network path.

There is no need to grant a metrics-scraping account the same clear-config-viewing permissions as an incident investigator. In real applications, permissions can be scoped per endpoint and role.

Metric tags must also be audited. Tags containing internal addresses, customer info, or user-supplied values can expose unwanted data and inflate time-series cardinality.

Disabling one observability endpoint does not mean all data collection or other exporters in the application have stopped. Identify clearly which read channel is being reduced and which monitoring systems remain active.

Similarly, restricting Actuator must go alongside auditing exposure paths outside Actuator:

- Do error responses and custom error pages include stack traces or configuration in the body?
- Do business endpoints or custom endpoints return configuration objects directly?
- Do logs print the entire `Environment`, authentication headers, or objects holding secrets?
- Do custom `info` contributors and health extensions include unexpected data?

These paths have their own owners and controls; `env`'s masking policy does not automatically cover them.

## 10. Common deployment mistakes

| Practice | Why it falls short | Focused fix |
| --- | --- | --- |
| Expose `"*"`, then exclude a few known endpoints | Can inadvertently expose new endpoints when dependencies or features are added | Use an explicit allowlist of endpoints to expose |
| Mask passwords only, while leaving all of `env` open | Key names and config sources can still be read | Reduce endpoints, restrict readers, and minimize payload |
| Use `when-authorized` without specifying roles | Any authenticated user may be considered authorized to view values | Specify roles by duty and test |
| Rely on a hard-to-guess base path | Anyone knowing the URL can still call it directly | Enforce network controls and access permissions |
| Add a security chain just for Actuator, omitting the rest | Requests outside the matcher may lack expected protection | Design chains covering the entire application |
| Test only as an unauthenticated caller | Leaves unknown what regular users or operational accounts can read | Test each permission group |
| Enable global health details and test only the root health path | Groups, extra paths, or component paths may differ | Audit all permitted health paths |
| Close HTTP but leave JMX or direct management ports overly broad | Data remains reachable through another channel | Inventory and verify every channel |
| Enable diagnostic mode and forget to close it | Temporary exposure becomes permanent | Attach an operational TTL and verify after revocation |

## 11. Applied exercise

A service has three needs:

1. The load balancer needs to know whether the application can serve traffic.
2. The metrics collection system needs to read monitoring data.
3. The operations team occasionally needs to investigate why a setting was overridden.

Build a table with: caller, required endpoint, network channel, read permissions, and permitted response data.

Your solution should demonstrate:

- Probes receive only the needed status; if using readiness, test the exact designed health group and path.
- The metrics-scraping account holds task-scoped permissions and does not automatically receive permission to read configuration values.
- `env` or `configprops` diagnostics occur only over a controlled channel, by authorized personnel, with a plan to close afterward.
- Endpoints such as `beans`, `mappings`, and `conditions` are not opened merely because another task needed configuration inspection.
- Tests cover anonymous callers, wrong-role callers, right-role callers, and configuration after revocation.

Use the [Spring Boot 3.3 property appendix](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html) to match property names to the exact version deployed. Results must prove both that **operational data remains readable as needed** and that **data beyond the need is restricted**.
