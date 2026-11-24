# Restricting Actuator Access and Value Display Policies During Diagnostics

## 1. Why Is Actuator Useful Yet Requires Its Own Security Boundary?

Spring Boot Actuator makes applications observable without writing boilerplate management APIs. When a service fails to start properly, binds `@ConfigurationProperties` incorrectly, selects the wrong profile, fails to connect to a database, or has an inactive auto-configuration, endpoints such as `health`, `env`, `configprops`, `conditions`, `beans`, `metrics`, and `loggers` can drastically cut down diagnosis time.

However, precisely because Actuator knows so much about the application, it can also disclose valuable details to unauthorized actors: property names, bean structure, internal hostnames, URLs, dependency status, thread names, runtime metrics, API paths, and even data inside heap dumps or logs.

For example, in configuration:

```yaml
payments:
  gateway:
    endpoint: "https://gateway.example.test"
    api-key: "${PAYMENTS_API_KEY}"
  retry:
    max-attempts: 3
```

An `/actuator/env` request can help operations determine **which source loaded a property**. Yet that diagnostic request must never become a mechanism for exposing `PAYMENTS_API_KEY`.

The system must be protected across **multiple independent layers**:

1. Is the endpoint **enabled** and present in the application context?
2. Is the endpoint **exposed** over HTTP or JMX?
3. Can network clients reach the management address/port?
4. Are requests **authenticated** and **authorized** with the proper role?
5. In the response, which values are **sanitized/masked**?
6. Is returned data saved into logs, APMs, proxies, caches, or tickets?
7. Should administrative access be temporary, audited, and timeboxed rather than permanently open?

**Principle:** Having permission to reach an endpoint does not mean having permission to view every value inside that endpoint. And a response masking values does not mean the endpoint is safe to expose to the Internet.

This lesson belongs to the **Troubleshooting** group under **Spring Boot Externalized Configuration**. The illustrative lab uses Java 21, Spring Boot 3.3.13, Gradle, Spring MVC, and Spring Security. All hostnames, keys, and test credentials are mock values.

### Learning Outcomes

After this lesson, you will be able to:

- Distinguish `enabled`, `exposed`, `reachable`, `authenticated`, `authorized`, and `sanitized`.
- Know the default HTTP exposure of Spring Boot Actuator 3.3.
- Declare an HTTP endpoint allowlist and avoid uncontrolled `include: "*"`.
- Use Spring Security `SecurityFilterChain` with `EndpointRequest` for authorization.
- Understand what happens when a custom `SecurityFilterChain` causes Boot's automatic Actuator security to back off.
- Understand `management.endpoint.env.show-values` and `management.endpoint.configprops.show-values` policies.
- Distinguish `never`, `when-authorized`, and `always`; know how to configure `roles` and limitations when using JMX.
- Apply `SanitizingFunction` to mask additional sensitive keys per application policy.
- Choose protection strategies for `health`, `info`, `metrics`, `loggers`, `heapdump`, `logfile`, `threaddump`, and custom endpoints.
- Run a local demo with a dedicated diagnostics profile and test `401`, `403`, `200`, and non-disclosure of mock keys.
- Design temporary access channels for operations teams and a teardown process after incident resolution.

## 2. Read Concepts Accurately: enabled Is Not the Same as exposed

Spring Boot Actuator includes built-in endpoints such as:

```text
health, info, env, configprops, conditions, beans,
mappings, metrics, loggers, threaddump, heapdump,
logfile, httpexchanges, scheduledtasks, caches,
startup, prometheus, shutdown, quartz...
```

Not every endpoint is always available. Some endpoints require additional beans/conditions; for instance `prometheus` needs a registry, `httpexchanges` needs a repository, `startup` needs startup-step recording, and `logfile` needs a configured log file.

There are two important switches:

**Enablement:** is the endpoint created and able to function?

```properties
management.endpoint.env.enabled=false
```

**Exposure:** is the endpoint published over a transport such as HTTP or JMX?

```properties
management.endpoints.web.exposure.include=health,info
```

In Spring Boot 3.3, built-in endpoints are generally enabled except `shutdown`, yet **only `health` is exposed over HTTP and JMX by default**. An endpoint like `env` may exist in the system without having a public HTTP route.

Summary table:

| State | Meaning | Behavior to watch |
| --- | --- | --- |
| Not enabled | Endpoint not created as an available endpoint | Cannot be invoked normally |
| Enabled, not exposed over HTTP | No corresponding Actuator HTTP route | Could still be exposed over JMX if configured |
| Enabled and exposed over HTTP | Route can exist | Must still evaluate firewall and Spring Security |
| Reachable but unauthenticated | Caller reaches route without identity | Can return 401 depending on policy |
| Authenticated but insufficient role | Has identity but lacks required role | Usually returns 403 |
| Authorized for endpoint | Request accepted | Values inside can still be masked |
| `show-values` permits raw view | Certain values can be displayed | `SanitizingFunction` can still mask extras |

Do not treat a single `404` as sole proof that an endpoint is disabled. Depending on security chains and gateways, an unexposed path might be blocked by a security layer before reaching route resolution.

### 2.1. Default Protection Is a Starting Point, Not the Whole Strategy

With Spring Security on the classpath and **no** custom `SecurityFilterChain`, Spring Boot normally protects Actuator endpoints other than health via auto-configuration. However, once you define **any** custom `SecurityFilterChain` bean, that automatic security configuration backs off so the application assumes full responsibility.

Therefore, adding a chain to protect business APIs can alter how Actuator is protected if you do not declare rules for Actuator.

**Never rely on "Spring Boot automatically protects Actuator" after writing your own security configuration.** Always verify effective filter chains and actual HTTP results.

## 3. HTTP Exposure: Allowlist Instead of Opening Everything

Minimal configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
```

If metrics are needed for internal monitoring:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
```

`prometheus` is only truly available when the required dependency and registry exist. Adding an endpoint name to the allowlist does not automatically add dependencies.

During an approved diagnostic session, you can **temporarily** expose additional endpoints:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,env,configprops,conditions"
```

Sensitive endpoints must be blocked by network controls and security roles; never make them public just because they sit under `/actuator`.

### 3.1. `exclude` Beats `include`

Example:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: "env,configprops,heapdump,logfile,shutdown"
```

Configuration-wise, `exclude` takes precedence over `include`. However, in production it is **discouraged** to use `include: "*"` and hope a denylist stays complete forever. When the framework or a dependency introduces a new endpoint, that endpoint could accidentally become exposed.

An easier-to-audit approach is **listing only permitted endpoints**. When operations needs a new endpoint, make a reviewed and tested config change.

In YAML, the `*` character should be quoted. For example, use:

```yaml
include: "*"
```

rather than a bare star that a YAML parser may interpret differently than intended.

### 3.2. Web Exposure and JMX Exposure Are Independent

Properties:

```properties
management.endpoints.web.exposure.include=health,info
management.endpoints.jmx.exposure.include=health
```

control two separate channels.

If system policy does not use JMX for management, you can disable JMX exposure:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        exclude: "*"
```

This is especially important with `show-values: when-authorized`: for sanitizable Actuator endpoints in Spring Boot 3.3, **JMX is considered already authorized for the purpose of showing values**. Therefore, do not rely on HTTP roles to protect an endpoint exposed via JMX.

If the organization requires JMX, establish dedicated JMX connection rules, authentication, encryption, and network access permissions. HTTP RBAC does not automatically protect JMX.

## 4. Three Security Layers That Must Work Together

A system can be protected along these lines:

```text
Client
  |
  | 1. VPN / private network / firewall / NetworkPolicy
  v
Management address/port
  |
  | 2. Endpoint enabled + HTTP allowlist
  v
/actuator/{id}
  |
  | 3. Spring Security authentication + authorization
  v
Endpoint handler
  |
  | 4. show-values + SanitizingFunction
  v
JSON or response artifact
  |
  | 5. Log/proxy/APM/ticket/retention policy
  v
Authorized consumer
```

Each layer prevents a different type of risk.

For example:

- Disabling `env` exposure removes the HTTP route from Actuator web mappings.
- NetworkPolicy blocks callers outside the management network.
- Spring Security requires the `OPS` role before invoking the endpoint.
- `show-values=never` masks values even when an OPS role calls it successfully.
- `SanitizingFunction` masks specific keys even when policy is opened to display values.
- Diagnostic procedures forbid copying responses containing internal data into public tickets.

One strong layer cannot replace all other layers.

## 5. Evaluating Endpoints by Risk Level

| Endpoint | Data/action | Typically recommended policy |
| --- | --- | --- |
| `health` | Overall status and possibly dependencies | Usable for probes; restrict details |
| `info` | Application-defined metadata | Publish only non-sensitive allowlist |
| `metrics` | Measurements, metric names, tags/labels | Restrict to monitoring role/network |
| `prometheus` | Metrics exposition | Allow only authorized scrapers |
| `env` | Property source/key list, values per sanitizer | Usually off; temporary exposure for OPS |
| `configprops` | ConfigurationProperties beans and bound data | Usually off; temporary exposure for OPS |
| `conditions` | Auto-config match/mismatch reasons | Use in restricted diagnostics |
| `beans` | Bean names/types and dependencies | Authorized operations staff only |
| `mappings` | Request mappings and endpoint structure | Never public |
| `loggers` | View and potentially change logging levels | Admin privileges, control POST/CSRF |
| `heapdump` | Process memory dump | Very sensitive; never permanently exposed |
| `threaddump` | Stack traces, thread names | Restricted; can disclose data |
| `logfile` | Log file contents | Restricted; can contain sensitive data |
| `httpexchanges` | HTTP request-response metadata | Depends on repository; review retention |
| `shutdown` | Request application shutdown | Disabled by default; never open casually |
| `quartz` | Job and scheduler data | Can contain sensitive information |
| Custom endpoint | Depends on developer code | Protect according to actual data and actions |

`health` is not safe by default if you decide to show full component details such as database hostnames or dependency errors. `info` can also become sensitive if developers insert commit metadata or connection strings into it.

### 5.1. State-Changing Endpoints Warrant Extra Caution

Endpoints such as `loggers` can alter log levels at runtime; leaving DEBUG on too long can generate heavy log traffic and expose data. `shutdown` can terminate the process. Custom endpoints can even trigger jobs or change configuration.

Classify **read-only** vs. **write/operation** endpoints. Spring Security enables CSRF for state-changing HTTP requests by default; if a caller gets `403` on POST, do not disable CSRF globally without assessment. For machine-targeted management endpoints, you can design a dedicated security chain with strong auth, narrow CSRF policy, tight scope, and tests.

## 6. What Do `env` and `configprops` Help Diagnose?

**`/actuator/env`** provides information about `ConfigurableEnvironment` and property sources. It is useful when you need to know:

- Did the application read the key set in the environment?
- Which sources exist and in what order?
- Does a property appear in multiple sources?
- Were the right profiles enabled?
- Is a specific property visible in a source?

**`/actuator/configprops`** provides consolidated information on `@ConfigurationProperties` beans, showing which beans were bound, under which prefixes, and how bound data is represented within what the endpoint permits.

These two endpoints are **not completely equivalent**:

```text
/env         -> view of property sources in Environment
/configprops -> view of configuration properties beans
```

A key existing in `Environment` while a bean still receives different data can be caused by wrong canonical name, conversion/validation, constructor binding, binding timing, or an already-created bean. `/env` by itself does not prove every business object applied that value.

### 6.1. Even Seeing Source Metadata Carries Risk

Even if every value displays as `******`, an `/env` response can reveal:

- That `SPRING_DATASOURCE_URL` is in the environment.
- That a config file sits at a specific path.
- Custom property names of enabled features.
- Relationships between configs and secrets.
- Which config sources were imported.

Therefore, masking reduces **value** risk without eliminating all **metadata and structural** risks. Restricting access to `/env` remains essential.

## 7. Value Display Policy: `show-values`

Spring Boot 3.3 supports `show-values` for endpoints capable of containing sensitive values, notably `env`, `configprops`, and `quartz`.

Example:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

Configuration values and meanings:

| Value | Meaning | Risk |
| --- | --- | --- |
| `never` | Values are masked | Safer, though key/source metadata can still leak |
| `when-authorized` | Only principals deemed authorized can view unmasked values, unless custom sanitizer applies | Requires proper auth and roles |
| `always` | Allows anyone who can reach the endpoint to view values, unless custom sanitizer applies | Dangerous if endpoint is reachable |

In Spring Boot 3.3, the default is **`never`**, where values are typically replaced with:

```text
******
```

Notably: since Spring Boot 3.x, `/env` and `/configprops` **mask all values by default**, not only keys containing `password` or `secret`. Do not rely on older version descriptions assuming only certain key patterns get masked.

### 7.1. `never`: Right Production Choice When You Still Need Source Info

```yaml
management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

You can confirm **the key exists** and understand its source without returning raw values.

Still, because property paths, sources, and bean names are internal details, continue restricting endpoint access to OPS/diagnostics roles and the management network.

### 7.2. `when-authorized`: Conditional and Requires Specifying roles

Example:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: "OPS"
    configprops:
      show-values: when-authorized
      roles: "OPS"
```

Over HTTP, Spring Boot considers a user authorized to view raw values when:

1. They are **authenticated**.
2. They hold a role in the endpoint's `roles` list (if configured).

**If `roles` is not configured, any authenticated HTTP user may be considered authorized to view values**, provided the endpoint permits their access. This is an important reason to declare specific roles whenever enabling `when-authorized`.

In Spring Security, `hasRole("OPS")` typically requires authority `ROLE_OPS`. Configuring a user with `roles: OPS` maps to that authority.

### 7.3. `always`: Not a Default Debugging Method

Dangerous example:

```properties
management.endpoint.env.show-values=always
```

If the endpoint is exposed and a caller gets past network/auth layers, values can appear in plaintext except for keys masked by custom sanitizers.

Never enable `always` in production just to locate a bind failure. Lower-risk solutions usually exist: inspect metadata, check allowlisted keys, add a boolean-returning diagnostic endpoint, or use restricted roles with `SanitizingFunction`.

### 7.4. JMX Requires Special Attention

Per Spring Boot 3.3 documentation, for sanitizable endpoints, **JMX callers are treated as authorized** when evaluating `when-authorized`. That means `roles` in `env` configuration does not turn an HTTP role policy into an automatic ACL for JMX.

If there is no need for JMX, declare:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        exclude: "*"
```

If JMX is required, secure transport, authentication, and JMX access rights per infrastructure policy. Never treat `when-authorized` as sufficient across every protocol.

## 8. `SanitizingFunction`: Mask Extra Keys Even When Authorized

Spring Boot lets you define beans of type:

```java
org.springframework.boot.actuate.endpoint.SanitizingFunction
```

to decide when a value is masked under the application's custom policy.

Documentation emphasizes that even when `show-values` is `when-authorized` or `always`, a custom `SanitizingFunction` **still applies**. Thus, security teams can keep certain sensitive value types always rendered as `******`, even for users with diagnostic privileges.

Example policy:

```text
diagnostics.api-key    -> always mask
any *.password         -> always mask
any *.token            -> always mask
any *.secret           -> always mask
other safe diagnostics -> may show if right role
```

### 8.1. Using `SanitizingFunction` in Spring Boot 3.3

```java
package dev.example.actuator;

import java.util.Locale;

import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class SanitizationConfiguration {

    @Bean
    public SanitizingFunction appSensitiveValues() {
        return data -> {
            String key = data.getKey()
                    .toLowerCase(Locale.ROOT)
                    .replace("_", "-");

            boolean sensitive =
                    key.contains("api-key")
                    || key.contains("apikey")
                    || key.contains("password")
                    || key.contains("token")
                    || key.contains("credential")
                    || key.contains("private-key")
                    || key.contains("secret")
                    || key.contains("authorization");

            return sensitive
                    ? data.withSanitizedValue()
                    : data;
        };
    }
}
```

`SanitizableData.withSanitizedValue()` returns a new sanitized data object with the value replaced. The code **does not modify `Environment` or real configuration beans**; it changes how data is presented in endpoints.

The substring list above is an **illustrative policy**, not able to cover every secret. Secrets can use keys without sensitive keywords or live in other structures. Data classification and endpoint controls remain necessary.

### 8.2. Never Log or Unmask Values Inside a Sanitizing Function

Wrong intent:

```java
// Never do this inside a sanitizer:
System.out.println("Current value: " + data.getValue());
```

In a diagnostic system, the sanitizer itself must be a component that **reduces leaks**, not a place collecting raw values.

### 8.3. When a Sanitizer Is Not Enough

`SanitizingFunction` applies only to endpoints using the corresponding sanitization mechanism. It does not automatically protect:

- Responses from a custom `@RestController`.
- Logs containing `${PAYMENTS_API_KEY}` printed by the app itself.
- Stack traces or exception messages into which code embeds secrets.
- Heap dumps and memory snapshots.
- Trace tags, metric labels, or message headers containing sensitive data.
- Request/response bodies recorded by debug loggers or HTTP client logging.

Never deploy a sanitizer and claim the system is immune to every form of secret leak.

## 9. Distinguish Endpoint Call Permission from Value View Permission

Suppose `/actuator/env` is exposed, Spring Security requires role `OPS` to call it, and `show-values` is set to `when-authorized` with roles `OPS`.

Then:

| Caller | HTTP permission to `/env` | Value display policy |
| --- | --- | --- |
| Anonymous | Denied; usually 401 | No value response |
| Authenticated `VIEWER` | Denied; usually 403 | No value response |
| Authenticated `OPS` | Allowed | Can view values except keys masked by custom sanitizer |
| `OPS` yet key `diagnostics.api-key` | Allowed | Value stays `******` thanks to custom sanitizer |
| Caller via JMX | Depends on JMX access | Does not rely on HTTP roles for authentication |

If HTTP policy allowed a `VIEWER` to call `/env` while endpoint `roles` required OPS, the viewer **could receive metadata with values masked**. However, there is usually no business reason to let viewers read property source lists.

Best practice is a two-layer design:

```text
HTTP authorization     -> allowed to access endpoint?
show-values + sanitizer -> how much detail may be viewed?
```

Do not merge both concerns into a single property.

## 10. Spring Boot's SecurityFilterChain: Avoid Exposing Actuator When Customizing

An application using Spring Security that declares a custom filter chain:

```java
@Bean
SecurityFilterChain applicationSecurity(HttpSecurity http) { ... }
```

causes part of Boot's security auto-configuration to **back off**. Therefore, explicitly declare security for both Actuator and business APIs.

A two-chain configuration is a clear illustration:

- Priority-1 chain matches Actuator endpoints via `EndpointRequest.toAnyEndpoint()`.
- Priority-2 chain handles application APIs.
- Health/info have lighter policies as needed.
- Env/configprops/metrics require the OPS role.
- All remaining endpoints default to deny.
- Do not disable CSRF across the entire application.

In real production, use OIDC/JWT/mTLS or an organization-approved authentication mechanism instead of experimental Basic Auth.

### 10.1. Note on Separate Management Ports

If Actuator runs on a separate management port, context structure and routing can differ from same-port configurations. Test against **the exact topology production runs**, especially when applying filter chains and ingress/network policies.

In the lab below, HTTP app and management endpoints share **localhost:8089** to ensure easy reproducible testing. Separating the management port is covered in section 22.

## 11. Hands-On Project: Actuator Diagnostic Guard

We build a project containing:

1. A `@ConfigurationProperties` bean so `/configprops` has inspectable data.
2. A business endpoint `GET /public-status` returning only non-sensitive status.
3. Actuator with minimal exposure in base config.
4. Profile `diagnostics` temporarily exposing `env`, `configprops`, `metrics`.
5. Spring Security requiring the `OPS` role.
6. `show-values=when-authorized`, while certain keys stay masked by `SanitizingFunction`.
7. JUnit/MockMvc verifying 200, 401, 403, and non-leakage of dummy data.

Never use production credentials. Every value in the lab can be replaced with self-created non-sensitive data.

### 11.1. Project Structure

```text
actuator-diagnostic-guard/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/actuator/
    │   │   ├── ActuatorGuardApplication.java
    │   │   ├── DiagnosticProperties.java
    │   │   ├── PublicStatusController.java
    │   │   ├── ActuatorSecurityConfiguration.java
    │   │   └── SanitizationConfiguration.java
    │   └── resources/
    │       ├── application.yaml
    │       └── application-diagnostics.yaml
    └── test/
        └── java/dev/example/actuator/
            └── ActuatorAccessTest.java
```

Generate the project via Spring Initializr with Gradle, Java 21, Spring Boot 3.3.x, and Web, Actuator, Security, and Test dependencies. Use the Gradle Wrapper generated by the project.

### 11.2. `settings.gradle`

```groovy
rootProject.name = 'actuator-diagnostic-guard'
```

### 11.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

There is no Spring Cloud in this lab. Properties like `management.endpoint.env.show-values` and `SanitizingFunction` are Spring Boot Actuator features and do not require Config Server or `@RefreshScope`.

### 11.4. Main Class

`src/main/java/dev/example/actuator/ActuatorGuardApplication.java`:

```java
package dev.example.actuator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ActuatorGuardApplication {

    public static void main(String[] args) {
        SpringApplication.run(ActuatorGuardApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` registers configuration records so Spring Boot Binder manages them. It has nothing to do with exposing Actuator endpoints.

### 11.5. Configuration Record

`src/main/java/dev/example/actuator/DiagnosticProperties.java`:

```java
package dev.example.actuator;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "diagnostics")
public record DiagnosticProperties(
        String mode,
        URI upstream,
        Duration timeout,
        String apiKey
) {}
```

This is an immutable record. It receives properties such as:

```text
diagnostics.mode
diagnostics.upstream
diagnostics.timeout
diagnostics.api-key
```

In the lab, `apiKey` is merely a dummy marker. In real projects, do not log this record with `toString()`, as a record's default `toString()` can print `apiKey`. For real secrets, use appropriate secret-handling types and avoid unnecessary serialization/logging.

### 11.6. Status API Returning Allowlist Only

`src/main/java/dev/example/actuator/PublicStatusController.java`:

```java
package dev.example.actuator;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublicStatusController {

    private final DiagnosticProperties settings;

    public PublicStatusController(DiagnosticProperties settings) {
        this.settings = settings;
    }

    @GetMapping("/public-status")
    public Map<String, Object> status() {
        return Map.of(
                "status", "ok",
                "mode", settings.mode(),
                "timeoutMs", settings.timeout().toMillis());
    }
}
```

The endpoint deliberately **omits** `settings.apiKey()` or the full record. This is the diagnostic-safe response pattern: **output only permitted fields**, rather than serializing a large configuration object and trying to strip secrets afterward.

For production, evaluate whether even `mode` or `timeout` should be public; the lab uses mock data and localhost.

## 12. Base Configuration: Restrict Actuator from the Start

`src/main/resources/application.yaml`:

```yaml
server:
  address: 127.0.0.1
  port: 8089

diagnostics:
  mode: "training"
  upstream: "https://example.test"
  timeout: 750ms
  api-key: "${LAB_API_KEY:LAB_ONLY_NOT_A_SECRET}"

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
      discovery:
        enabled: false
    jmx:
      exposure:
        exclude: "*"

  endpoint:
    health:
      show-details: never
    env:
      show-values: never
    configprops:
      show-values: never
```

Points to remember:

- Process listens only on `127.0.0.1` because this is a local lab.
- Only health/info are exposed by default in this setup.
- JMX endpoints are not exposed.
- Raw values from `env` and `configprops` are disallowed in the base profile.
- `LAB_API_KEY` has a placeholder default that is **mock text, not a real token**. Never use default secrets in production.
- Disabling the discovery page reduces advertised endpoint catalog details, though it **is not a firewall**.

Another option to narrow further is disabling `env`/`configprops` completely when unused:

```yaml
management:
  endpoint:
    env:
      enabled: false
    configprops:
      enabled: false
```

Once disabled, a profile opening exposure alone is not enough for the endpoint to run; it must be re-enabled intentionally. In the lab, we keep them enabled yet unexposed in the base config for easy switching to the diagnostics profile.

### 12.1. Why Avoid `management.endpoints.web.exposure.include: "*"`?

Because it can expose `beans`, `mappings`, `threaddump`, `loggers`, or other endpoints you have not evaluated. If a new dependency introduces a new endpoint, a wildcard changes the attack surface without any endpoint-list review.

For operational endpoints, an **explicit allowlist** is easier to read, test, and control than a long denylist.

## 13. Temporary Diagnostics Profile

`src/main/resources/application-diagnostics.yaml`:

```yaml
spring:
  security:
    user:
      name: ops
      password: "${OPS_PASSWORD}"
      roles: OPS

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,env,configprops"

  endpoint:
    env:
      show-values: when-authorized
      roles: "OPS"
    configprops:
      show-values: when-authorized
      roles: "OPS"
```

Meaning:

- Sensitive endpoints are exposed only when the `diagnostics` profile is enabled.
- Lab user `ops` has role `OPS`. `OPS_PASSWORD` must be passed into the process via environment variable, never committed as a real password in YAML.
- Even after a request passes HTTP authorization, the `roles` property of `show-values` enforces role-based display policy.
- Custom `SanitizingFunction` continues masking specific keys even when the request is authorized.
- The `diagnostics` profile must never remain permanently enabled in production. If production diagnostics are needed, apply an approved, timeboxed, audited change with rollback.

In projects with an identity provider or centralized RBAC, configuring user/password via properties is purely for demo purposes. Production should use organization-managed authentication.

### 13.1. What Is the Risk of Using `when-authorized` While Forgetting `roles`?

Per Spring Boot 3.3, if no role list is set, any authenticated HTTP user may be considered authorized for value-display purposes.

Therefore, this is overly broad if many users can log in:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
```

Always add specific roles and continue controlling endpoint access in Spring Security.

## 14. Spring Security for Actuator and Application APIs

Create `src/main/java/dev/example/actuator/ActuatorSecurityConfiguration.java`:

```java
package dev.example.actuator;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {

        http.securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                EndpointRequest.to("health", "info"))
                        .permitAll()
                        .requestMatchers(
                                EndpointRequest.to(
                                        "metrics", "env", "configprops"))
                        .hasRole("OPS")
                        .anyRequest()
                        .denyAll())
                .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public-status")
                        .permitAll()
                        .anyRequest()
                        .denyAll())
                .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Breakdown:

1. `@Order(1)` gives the Actuator chain priority first.
2. `EndpointRequest.toAnyEndpoint()` matches Actuator HTTP endpoints via Spring Boot's mechanism, not brittle hardcoded path strings.
3. Health/info are readable without auth in the local lab.
4. Env/configprops/metrics require Spring Security role OPS.
5. Remaining Actuator endpoints hit `denyAll()`.
6. The application chain is separate, permitting only `/public-status` per the demo matcher and denying all other URLs.
7. CSRF is not disabled globally. The lab uses GET only.
8. `httpBasic` is for demo purposes; on real networks combine TLS/mTLS/SSO and network restrictions. **Never use Basic Auth over unencrypted HTTP on public networks.**

### 14.1. When Adding a Custom Chain, Boot Auto-Security Backs Off

If you define only the first chain without a general chain for the rest, other business APIs may not be protected as you assume. Spring Boot documentation highlights that once you define a custom `SecurityFilterChain`, corresponding security auto-configuration no longer applies wholesale across the application.

Hence the example has **two chains**, even though the demo app has only one business API. In real products, replace the second chain with your application's auth policy rather than keeping `denyAll()` if the app serves additional valid APIs.

### 14.2. `EndpointRequest` Is Better Than Hardcoding Paths in Many Cases

Default endpoint URL is:

```text
/actuator/{id}
```

yet base path can be changed via:

```properties
management.endpoints.web.base-path=/manage
```

With a separate management port, context paths can also differ. `EndpointRequest` is designed to match Actuator endpoints according to configuration, including related subpaths, reducing reliance on hardcoded URL strings.

This does not replace network policies or rules for non-Actuator APIs.

### 14.3. Avoid Broad CSRF "Fixes"

If you later want to change log levels via `loggers`, POST requests can be blocked by CSRF protection under default settings. Do not immediately write:

```java
// Do not copy-paste disabling CSRF globally:
http.csrf(csrf -> csrf.disable());
```

Only consider a CSRF exception for a management endpoint **clearly intended for non-browser clients**, with strong auth, narrow authorization, network isolation, and tests. For browser cookie/session routes, CSRF is an essential defense.

## 15. Registering Custom Sanitization

Use the `SanitizationConfiguration` class from section 8. In the demo, `api-key` holds a dummy value yet remains masked.

For example, when an OPS user calls:

```text
GET /actuator/env/diagnostics.api-key
```

the response can have a structure similar to:

```json
{
  "property": {
    "source": "...",
    "value": "******"
  }
}
```

The snippet illustrates only the masked `value` field; the full structure depends on endpoint, source, and version.

Meanwhile, a non-sensitive property such as `diagnostics.timeout` can appear for OPS when `show-values: when-authorized`, provided no custom sanitizer masks it.

**Important:** you do not need to access the raw `api-key` to "prove the sanitizer works." Verifying the response **does not contain the test marker** is sufficient.

## 16. Running the Project in Default Mode

From the project directory:

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Verify:

```bash
curl -i http://127.0.0.1:8089/actuator/health
curl -i http://127.0.0.1:8089/public-status
curl -i http://127.0.0.1:8089/actuator/env
```

Expected:

- `/actuator/health` can return `200` and overall status.
- `/public-status` returns the small allowlisted information set.
- `/actuator/env` **is not exposed in the base profile**; no diagnostic data endpoint is available.
- `/actuator/heapdump`, `/actuator/logfile`, `/actuator/mappings` are not exposed merely because the Actuator dependency is present.

Exact status codes for unexposed paths can depend on security filter chains and routing (e.g. `403` or `404`), yet what matters is **no endpoint data is returned**. In integration tests, check both HTTP policy and exposure.

### 16.1. Health Details Differ from Health Endpoint Reachability

Example:

```yaml
management:
  endpoint:
    health:
      show-details: never
```

Health can publish `UP` status without exposing details for individual datasources, disk, brokers, or dependencies.

If OPS needs details, consider `show-details: when-authorized` with appropriate roles while protecting the access path. Do not assume a public health response always has just one field if the app customized details.

## 17. Enabling the diagnostics Profile Locally

Stop the app and start with the `diagnostics` profile using a **self-created local-only password**—never copy a real credential.

Bash:

```bash
export OPS_PASSWORD='local-training-password'
./gradlew bootRun --args='--spring.profiles.active=diagnostics'
unset OPS_PASSWORD
```

PowerShell:

```powershell
$env:OPS_PASSWORD = 'local-training-password'
.\gradlew.bat bootRun --args="--spring.profiles.active=diagnostics"
Remove-Item Env:OPS_PASSWORD
```

Note: the password in the example is a **training placeholder**, not an operational password. It must never be used outside localhost. In production, use an identity provider or managed secrets source.

Open another terminal and call without auth:

```bash
curl -i http://127.0.0.1:8089/actuator/env
```

Expected: `401 Unauthorized` under the lab chain.

With curl, you can use:

```bash
curl -i -u ops http://127.0.0.1:8089/actuator/env
```

`curl -u ops` prompts for the password, avoiding putting passwords directly on the command line. Enter the lab password configured in the app's terminal. If authentication succeeds and role OPS matches, the request can return `200` with permitted data.

Check a single key:

```bash
curl -i -u ops \
  http://127.0.0.1:8089/actuator/env/diagnostics.api-key
```

Expect the sensitive key's value to remain `******` thanks to the custom `SanitizingFunction`.

### 17.1. Never Capture Full Responses During Real Incident Handling

In production, `/actuator/env` responses can list many sources and keys. Do not paste the whole output into chat, tickets, or logs for debugging help. Describe the issue using:

```text
Property name: payments.gateway.timeout
Source category: environment / Config Data
Was present: true
Was bindable: true
Expected unit/type: Duration
```

Never attach secret values or config objects containing credentials.

## 18. Testing Access Control with MockMvc

Create `src/test/java/dev/example/actuator/ActuatorAccessTest.java`:

```java
package dev.example.actuator;

import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "spring.security.user.password=test-password-only",
        "diagnostics.api-key=test-credential-only"
})
@ActiveProfiles("diagnostics")
@AutoConfigureMockMvc
class ActuatorAccessTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCanReadMinimalHealth() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        not(containsString("test-credential-only"))));
    }

    @Test
    void anonymousCannotReadEnvironment() throws Exception {
        mvc.perform(get("/actuator/env"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void viewerCannotReadEnvironment() throws Exception {
        mvc.perform(get("/actuator/env")
                        .with(user("viewer").roles("VIEWER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void opsCanReadButSensitiveValueIsStillMasked()
            throws Exception {
        mvc.perform(get("/actuator/env/diagnostics.api-key")
                        .with(httpBasic(
                                "ops", "test-password-only")))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        not(containsString("test-credential-only"))));
    }

    @Test
    void opsCanReadConfigpropsWithoutLeakingTestCredential()
            throws Exception {
        mvc.perform(get("/actuator/configprops")
                        .with(httpBasic(
                                "ops", "test-password-only")))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        not(containsString("test-credential-only"))));
    }
}
```

Here:

- `spring-security-test` simulates requests with users/roles or HTTP Basic credentials.
- `@ActiveProfiles("diagnostics")` exposes only endpoints needed for the lab.
- Tests require no Vault token, database, or public network.
- Two tests use `not(containsString(...))` to verify the mock credential **does not appear** in responses from both endpoints.
- `401` and `403` prove authentication and authorization are two separate decisions.
- A `200` test alone does not prove data safety; verify masking.

Run:

macOS/Linux:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

### 18.1. Testing the OPS Role with `when-authorized`

An additional test can call the endpoint for a non-sensitive property:

```text
diagnostics.mode=training
```

and verify OPS sees `training` when `show-values=when-authorized`, while a non-OPS user cannot access the endpoint.

If a team allows VIEWER onto the endpoint while only OPS may view raw values, verify VIEWER's values remain masked. However, that design should only be used when endpoint metadata is evaluated as non-sensitive for VIEWER.

### 18.2. Testing That Unexpected Endpoints Are Not Exposed

Add tests for paths:

```text
/actuator/heapdump
/actuator/logfile
/actuator/beans
/actuator/mappings
/actuator/shutdown
```

In the lab profile, they **must not return functional endpoint payloads**. Because multiple filter chains can exist, do not hardcode asserting `404` on every unexposed path; instead, confirm no successful data response is returned, and inspect exposure configuration separately.

### 18.3. Production Tests Must Also Check Topology

MockMvc does not fully simulate firewalls, ingress, Kubernetes NetworkPolicies, or TLS. For production, add integration/smoke tests from two network zones: callers permitted to reach management endpoints and callers forbidden from reaching them.

Never conclude that a role unit test proves a management port is blocked from the Internet.

## 19. Evaluating `show-values=always` via Risk Assessment

A common operational scenario:

> "On-call needs the real value of property X; can we just turn on `always` for 15 minutes?"

Before deciding, weigh:

1. Could property X hold credentials, tokens, private keys, PII, or internal endpoints?
2. Can the issue be deduced via key/source without viewing raw values?
3. Could you write a diagnostic endpoint returning only a comparison result without disclosing the value?
4. Can an instance be reached via VPN/`kubectl port-forward` instead of exposing ingress?
5. Can `when-authorized` and a dedicated role be used?
6. Are custom sanitizers and tests in place ensuring sensitive keys remain masked?
7. Will proxies/access logs or tracing record the response?
8. Is there a time limit, audit trail, and an owner responsible for disabling the endpoint afterward?

Usually the reasonable answer is not turning on `always`. A "check" endpoint might simply return:

```json
{
  "property": "payments.gateway.timeout",
  "present": true,
  "parsed": true,
  "withinExpectedRange": true
}
```

That suffices to diagnose many errors without publishing raw values.

## 20. Configuration Diagnostic Scenarios

### 20.1. Application Fails to Read an Environment Variable

Goal: know whether `PAYMENTS_RETRY_TIMEOUT` entered the process and whether Binder uses the exact key `payments.retry.timeout`.

Approach:

1. Check deployment config passed the env var.
2. Check variable name and relaxed binding.
3. If needed, use an OPS-only endpoint to verify the property name appears in Environment.
4. Use masked `/configprops` to confirm the corresponding configuration bean exists.
5. Never print all env vars and never open `/env` publicly.

If the property is non-sensitive and viewing the value is mandatory, use a limited display policy; never set `always` for the entire endpoint.

### 20.2. Wrong Profile Causes Service to Call Wrong Backend

Goal: know the active profiles and which config sources are applied.

Choose the least-data approach:

```java
environment.getActiveProfiles()
```

or an internal diagnostic endpoint returning only approved profile names. You do not need to dump every property source that could contain secrets.

### 20.3. `@ConfigurationProperties` Has Wrong Data

Goal: distinguish missing properties from type conversion issues.

Debug direction:

- Check prefix/root registration.
- Check canonical names and profile/precedence.
- Check startup conversion/validation errors.
- For running apps, cross-check masked info from `/env` and `/configprops`.
- Never switch `show-values` to `always` just to print potentially sensitive strings.

### 20.4. A Bean Is Missing Due to Auto-Configuration Conditions

`/actuator/conditions` shows which auto-configurations matched/mismatched. It can expose class names, dependencies, and runtime structure. If needed, expose temporarily to OPS, never on public ingress.

### 20.5. Too Few Logs to Pinpoint an Error

`/actuator/loggers` can allow changing log levels at runtime when properly exposed and authorized. The risk is that raising DEBUG on packages containing HTTP clients or authentication can send secrets or request data into logs.

Before raising log levels:

- Target only the needed package/class.
- Set a time limit and revert plan.
- Restrict the operation with a dedicated role.
- Do not disable CSRF globally for POST convenience.
- Monitor log volume and retention.
- Check whether libraries log request headers/bodies.

### 20.6. Needing a Heap Dump to Investigate a Leak

`heapdump` can hold in-memory data, including credentials and request payloads. Never treat "it's just a debug file" as justification to allow downloading over public HTTP.

A safer workflow: capture dumps via authorized host/container admin mechanisms, store in a restricted repository with retention limits, encrypt at rest, and limit viewer access. Never download dumps to unmanaged personal machines or attach them to public tickets.

## 21. Health Endpoint: Minimal for Probes, Detailed Internally

Health is often the only endpoint load balancers/orchestrators poll continuously. Yet **status** and **details** require distinct policies.

Minimal public config:

```yaml
management:
  endpoint:
    health:
      show-details: never
```

When details are needed for administrative roles:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      roles: "OPS"
```

However, if the security filter chain lets anonymous users access `/actuator/health`, unauthenticated callers see only data permitted by `show-details`; only the OPS role receives details. Test the actual response of your version, as health groups and components also have their own properties.

A public application may expose `health` for probes, yet must never inadvertently expose:

- Database connection URLs.
- Message broker endpoints.
- Exception messages containing secrets.
- Internal host inventories.
- Backend service names public callers have no need to know.

### 21.1. Health Groups and Kubernetes Probes

Spring Boot Actuator can support health groups such as `liveness` and `readiness`, well suited for Kubernetes probes when enabled/configured. These endpoints serve traffic orchestration and do not need to return full details.

If using a separate management port, evaluate whether probes test the main handling path or only the management context, and whether the main port is genuinely ready. A healthy management server does not automatically prove the main HTTP application is accepting requests on the business port.

## 22. Management Port and Address: Reducing Network Surface

Spring Boot supports a dedicated port:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
```

For a strictly local lab:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
```

Per Spring Boot documentation, `management.server.address` can bind to a separate address only when the management server uses a **different port** from the main server.

Advantages of a separate port:

- Easier to apply firewalls or NetworkPolicies opening the management port only to authorized callers.
- Can route monitoring traffic and business traffic across separate networks.
- Can configure dedicated TLS or extra protection via mTLS/gateway.
- Can restrict which systems scrape metrics.

However, **a separate port is not an authentication mechanism**. If that port is reachable from an untrusted network, Actuator still needs proper protection. Never equate `management.server.port=8081` with "internal only."

### 22.1. Kubernetes: Do Not Default to Loopback for Scraped Endpoints

Binding the management server to `127.0.0.1` inside a pod can prevent Prometheus or kubelet from connecting outside the network namespace depending on your topology.

Before applying:

- Identify where probes/scrapers run.
- Verify whether Services or ingresses expose the management port.
- Use NetworkPolicy to restrict permitted sources.
- If role-based access is needed, configure proper authentication.
- Never expose the port via a public LoadBalancer just for monitoring convenience.
- Test connectivity from the pod or monitoring namespace.

### 22.2. Changing Base Path Does Not Protect Endpoints

Example:

```yaml
management:
  endpoints:
    web:
      base-path: "/internal-management"
```

changes the URL without adding an authorization layer. Security by obscurity is insufficient; you need an exposure allowlist, network isolation, and authentication.

### 22.3. Disabling HTTP Management When Unneeded

You can use:

```properties
management.server.port=-1
```

or:

```yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
```

However, disabling HTTP management does not necessarily disable the JMX transport. Check both if policy forbids remote management channels.

## 23. Per-Environment Authorization: A Suggested Matrix

| Environment | Health | Info/Metrics | Env/Configprops | Heap/Logfile | Show values |
| --- | --- | --- | --- | --- | --- |
| Local dev | Health for local | Can open for learning | Can enable temporarily with test role | Only when truly needed | `never` or `when-authorized` for lab |
| CI tests | Health + test probes | Per test | Only in test profile | Usually off | Verify masking |
| Staging | Health for platform | Monitoring role | OPS on internal network | Via approval workflow | Default `never` |
| Production | Minimal health/readiness | Authorized scraper/OPS | Off or temporarily opened with approval | Never permanently exposed | `never` as baseline |

These are policy recommendations, not mandatory configurations. An organization with mTLS/SSO/dedicated management networks may grant access differently, while **least privilege and data minimization** still apply.

### 23.1. Rules for Temporarily Opening Endpoints During Incidents

A runbook may require:

1. Ticket/incident ID.
2. Approver and scope of endpoints to open.
3. Target hosts/pods and allowed network sources.
4. Short-TTL roles/credentials.
5. Keys allowed for inspection and keys mandatory to mask.
6. Start/end timestamps.
7. Audit trail of requests or configuration changes.
8. Closing exposure/roles once complete.
9. Verification that no sensitive access paths remain open.
10. Cleanup of diagnostic data from inappropriate storage.

A temporary endpoint must have **its closing procedure planned at the moment it is opened**.

## 24. Warnings About `info` and Build/Git Metadata

An application can publish build info or Git info via `/actuator/info` when configured accordingly. Details like version or commit ID help operations, yet can also reveal internal metadata.

Never put:

```text
internal.repo.url
employee.email
deployment.secret
private.scm.token
```

into `info` carelessly. If public clients only need the version, create a small allowlist of permitted fields and avoid exposing broad provenance.

`info` does not share `env`'s `show-values` policy; do not assume setting `management.endpoint.env.show-values=never` protects arbitrary fields you feed into info contributors.

## 25. `metrics` and `prometheus`: Measurements Are Not Harmless by Default

Metrics do not usually hold plaintext passwords, yet uncontrolled tags/labels can contain:

- Customer IDs or paths with PII.
- Raw URLs with query strings.
- Tokens if the app builds tags from Authorization headers.
- Tenant names, regions, internal service names.
- Usernames, hosts, or sensitive resource labels.

Therefore:

- Expose metrics only to authorized scrapers.
- Control metric tag cardinality and label contents.
- Avoid using user input or secrets as tags.
- Apply network policies for monitoring.
- Test actual sample exposition.
- Do not add `prometheus` to public ingress by default.

`show-values` on `/env` has no effect on obscuring labels emitted by metrics code.

## 26. Diagnostics Does Not Mean Collecting All Data

A good practice is creating an **allowlist-shaped** diagnostic report:

```json
{
  "application": "payment-service",
  "environment": "production",
  "activeProfileCount": 1,
  "requiredKeyPresent": true,
  "requiredKeyConverted": true,
  "configRevision": "r42",
  "readiness": "UP"
}
```

Do not return:

```json
{
  "dbPassword": "plaintext",
  "vaultToken": "plaintext",
  "allEnvironmentVariables": "..."
}
```

For critical config fields, instead of printing raw values, check:

- Present/absent.
- Valid type when bound.
- Within a safe range.
- Source belongs to an allowed category.
- Current revision.
- Dependency connectivity succeeded.
- Value is compatible with a published contract.

If including `configRevision`, never use raw hashes of secrets or low-entropy data that could be brute-forced. Use managed revision identifiers such as approved Git commits/config versions, not fingerprints revealing sensitive values.

## 27. Responding to an Actuator Exposure Leak

If `/actuator/env` or `/actuator/heapdump` is discovered exposed publicly:

1. Identify the endpoint, URL, timeframe, access sources, and current exposure.
2. **Block the access path** via network/ingress and exposure config, taking care not to break required health probes.
3. Review logs/audits in a manner that avoids spreading data further.
4. Assess what data could have leaked: key names, property values, memory snapshots, log files, mapping info.
5. If any secret may have been exposed, execute approved incident response and credential rotation/revocation policies.
6. Audit other endpoints (`configprops`, `logfile`, `heapdump`, custom endpoints).
7. Add regression tests ensuring dangerous paths cannot be re-exposed.
8. Review ingress, firewalls, ACLs, RBAC, security chains, monitoring exporters, and log sinks.
9. Write a postmortem focusing on root cause and missing control layers.

Merely switching `show-values` from `always` to `never` is **insufficient** if dumps were already accessed or other endpoints remain open.

## 28. Common Configuration Pitfalls

### 28.1. `404` When Calling `/actuator/env`

Possible causes:

- `spring-boot-starter-actuator` not added.
- Endpoint not exposed over HTTP.
- Endpoint has `enabled=false`.
- Base path is no longer `/actuator`.
- Calling the wrong port.
- Gateway/ingress does not route the management path.
- Security chain/gateway intentionally hides or blocks the route.

Fix: verify dependency, `management.endpoints.web.exposure.include`, `management.endpoint.env.enabled`, management port/base path, and security rules. Do not enable wildcards just to test.

### 28.2. `401` When Endpoint Is Exposed

This may be the intended policy: the request is unauthenticated. Use provisioned OPS credentials in the right environment; never disable security to eliminate 401.

### 28.3. `403` for a Logged-In User

Check:

- Does the user have the right authority/role (`ROLE_OPS`)?
- Does `hasRole("OPS")` match the principal?
- Was a different custom filter chain matched than expected?
- Does the endpoint require a non-GET HTTP method and get blocked by CSRF?
- Does the gateway/ingress have another ACL?

For admin POST requests, `403` can come from CSRF rather than roles alone. Do not disable CSRF globally by default.

### 28.4. Authorized Yet Values Are Still `******`

If:

```properties
management.endpoint.env.show-values=never
```

then this is expected behavior, even when OPS has access. If using `when-authorized`, check endpoint `roles`, the principal, and whether a custom `SanitizingFunction` applies.

**The goal is not "view raw secrets at any cost."** If a key belongs to the always-mask list, the sanitizer is doing its job.

### 28.5. `when-authorized` Yet Every Logged-In User Sees Values

Check whether:

```properties
management.endpoint.env.roles=OPS
```

is set. Without roles, the default rule can treat any authenticated HTTP user as authorized. Also inspect the endpoint's HTTP access policy and custom security chains.

### 28.6. Not Seeing New Data After Editing `application.yaml`

Actuator inspects values/beans inside **the current process**. Core Spring Boot does not watch files outside the JAR and rebind every bean by default. If Config Data changes without restarting/refreshing via a supported mechanism, the process may keep the old snapshot.

Do not confuse "endpoint is masking the value" with "value is still stale." Separate loading, precedence, binding, and sanitization questions.

### 28.7. Management Endpoints Reachable Outside VPN

Check network exposure, ingress routes, Service types, port bindings, firewalls, and NetworkPolicies. Spring Security should still exist, yet a network mistake must never turn sensitive endpoints into public targets.

### 28.8. `/actuator/configprops` Data Differs from Business API

The service may have copied values from the configuration bean at initialization; or multiple beans, prefixes, or custom bindings exist. `/configprops` reflects configuration properties, not whether every client/resource applied the values.

### 28.9. `include: "*"` Unexpectedly Opens a New Endpoint

A dependency/framework upgrade added an endpoint and the wildcard exposed it. Switch to an allowlist; add exposure tests in CI.

### 28.10. `management.server.address` Has No Effect

In Spring Boot, to bind management endpoints to a separate address, the management port must be **different** from the main server port. When sharing the same port, control the bind address on the main server and network.

### 28.11. Disabled HTTP Yet JMX Remains Open

Web exposure and JMX exposure are independent. If policy forbids JMX, set `management.endpoints.jmx.exposure.exclude="*"` and verify infrastructure JMX transport.

### 28.12. Downloaded Heap Dump Contains Secret Data

Masking `env/configprops` does not erase data from the heap. Treat dumps as sensitive artifacts handled through a secure diagnostics workflow.

## 29. Questionnaire to Define Policy for Each Endpoint

When reviewing an endpoint, answer:

| Question | Suggested notes |
| --- | --- |
| Who uses it? | Load balancer, Prometheus, SRE, on-call, developer |
| Needs HTTP or JMX? | Pick one or both with separate controls |
| Always on or temporary? | Baseline vs. incident profile |
| Contains sensitive data? | Key names, raw values, hostnames, dumps, logs |
| Read-only or write-capable? | GET vs. POST/DELETE |
| Which roles? | Public health, METRICS, OPS, incident-admin |
| Which network tier? | Internal Service, VPN, port-forward, mTLS |
| Is there a sanitizer? | `never`, roles, custom masking |
| Is there auditing? | Who called, when, incident ID |
| Is there a retention policy? | Where responses/logs/dumps are stored |
| Are there tests? | 200, 401, 403, fail-closed, secrets absent |
| What happens on close? | Revert exposure, rotate credentials if needed |

An endpoint should only be approved when it has an owner and a defined operational purpose.

## 30. Practice Exercises

### Exercise A — Enabled, Exposed, or Authorized?

Given:

```properties
management.endpoint.env.enabled=true
management.endpoints.web.exposure.include=health,info
```

Explain why `/actuator/env` is not yet HTTP-accessible, even though the endpoint may be enabled. If `env` is added to include, what additional protections are required?

### Exercise B — Role-Based `show-values`

An endpoint has:

```properties
management.endpoint.env.show-values=when-authorized
management.endpoint.env.roles=OPS
```

Predict the payload returned to anonymous, authenticated VIEWER, and authenticated OPS under two Spring Security setups: only OPS may call the endpoint vs. both VIEWER and OPS may call the endpoint.

### Exercise C — Sanitizer Always Masks Secrets

Use `SanitizingFunction` to mask every key containing `"credential"` or `"api-key"`. Write a test with mock values and verify responses do not contain the marker. Does the sanitizer protect heap dumps? Why or why not?

### Exercise D — Adding a Custom SecurityFilterChain

An app previously relied on Boot auto-security. A developer adds a chain for `/api/**`. Explain why Actuator rules must be re-checked and propose a setup using `EndpointRequest.toAnyEndpoint()`.

### Exercise E — Profiles for Diagnostics

Design `application.yaml` exposing `health,info`; `application-diagnostics.yaml` exposing `env,configprops` as well while requiring the OPS role. Write the command to start the local profile with a dummy password from an environment variable; describe teardown once finished.

### Exercise F — Kubernetes Management Port

The app uses port 8080 for APIs and 8081 for Actuator. Describe Service/NetworkPolicy rules so Prometheus can scrape metrics while public ingress cannot reach `/actuator/env`.

### Exercise G — HTTP Methods and CSRF

Operations wants to change logger levels via POST. When receiving `403`, what causes besides wrong role should be checked? Why not disable CSRF globally?

### Exercise H — Distinguishing `/env` and `/configprops`

`Environment` sees `demo.timeout`, yet `DemoProperties` still uses the old value. List possible causes: startup snapshot, wrong prefix, conversion, profile, bean recreation, custom lifecycle. Do you need to view raw secrets to find the cause?

### Exercise I — Metadata Leak Even When Values Are Masked

In an `/env` response, all values are `******`, yet `internal.db.backup-host` and absolute file paths appear. Why does this response still require role/network restrictions?

### Exercise J — Audit and Timebox

An incident requires opening `/actuator/conditions` for 30 minutes. Design a checklist covering owner, approval, access scope, audit, testing, and rollback. Do not enable wildcards.

### Exercise K — Reviewing Health Policy

Everyone can call `/actuator/health`, yet details contain database hostnames. Update configuration so anonymous callers see overall status only, while OPS can view details when authorized.

### Exercise L — When `/env` Is Unnecessary

If an incident only needs to verify whether `retry.timeout` parses as `Duration` and is greater than 0, propose an allowlisted diagnostics endpoint returning a boolean/normalized unit without exposing all property sources.

## 31. Self-Check Questions

**1.** Which endpoint does Spring Boot 3.3 expose over HTTP by default?

**2.** How does enablement differ from exposure?

**3.** If an app already defines a custom `SecurityFilterChain`, should you assume Boot auto-security still covers all of Actuator?

**4.** Between `include` and `exclude`, which takes precedence?

**5.** Should `include: "*"` be used in production as a long-term baseline?

**6.** What are the three values of `show-values`?

**7.** What is the default `show-values` for `env/configprops` in Boot 3.3?

**8.** With `when-authorized` and missing `roles`, can any authenticated HTTP user be treated as authorized?

**9.** Does `SanitizingFunction` continue masking values when an OPS user is authorized?

**10.** Does `SanitizingFunction` protect data inside heap dumps?

**11.** Does JMX authorization work like HTTP roles for `show-values`?

**12.** What does `EndpointRequest.toAnyEndpoint()` help with?

**13.** Is `management.endpoints.web.base-path=/manage` a security boundary?

**14.** Why must public Actuator `health` still consider details?

**15.** Why can `/actuator/metrics` still carry risk even without containing passwords?

**16.** How do `401` and `403` differ?

**17.** Can a POST to `/actuator/loggers` return `403` due to CSRF?

**18.** Is setting `management.server.port=8081` alone enough network protection?

**19.** Can `management.server.address` be set differently when management shares the same port as the main server?

**20.** Why should you avoid copying full `/env` responses into public tickets?

**21.** After editing YAML on disk, `/env` still showing old data—is that necessarily an Actuator bug?

**22.** Is a 200 test with OPS enough to prove secrets cannot leak?

### Suggested Answers

1. `health` by default.
2. Enablement determines whether the endpoint is available; exposure determines publication over transports.
3. No; custom chains cause security auto-configuration to back off.
4. `exclude` takes precedence over `include`.
5. No; prefer an allowlist.
6. `never`, `when-authorized`, `always`.
7. `never`; values are masked.
8. Yes; always configure explicit roles.
9. Yes; custom sanitizers still apply.
10. No; heap dumps are a different data artifact.
11. No; JMX is treated as authorized for `show-values` policy and requires separate JMX protection.
12. Matches Actuator endpoints based on metadata/config paths, even when base path changes.
13. No; it only changes the URL.
14. Details can disclose dependencies and internal topology.
15. Tags/labels/metric names can contain sensitive data.
16. 401 usually means unauthenticated; 403 means authenticated yet lacking permission or blocked by another policy.
17. Yes.
18. No; firewalls, network policies, and auth are still needed.
19. Binding a separate management address is only supported when using a separate port.
20. Because it can reveal keys, sources, hosts, structure, and sometimes values depending on policy.
21. No; Boot Config Data does not watch files to rebind; check lifecycle.
22. No; also verify masking, sensitive metadata, and logs.

## 32. Production Deployment Checklist

Before opening an Actuator endpoint for diagnostics:

- [ ] Identified which endpoints are genuinely required.
- [ ] Used a web allowlist, never wildcard exposure by default.
- [ ] Checked endpoint enablement separately from exposure.
- [ ] Checked JMX exposure if the organization has JMX transport.
- [ ] Identified source networks permitted to connect to the management port.
- [ ] Protected with appropriate Spring Security/SSO/mTLS.
- [ ] Dedicated role exists for OPS/incident diagnostics.
- [ ] Not relying on Boot auto-security when custom filter chains exist.
- [ ] Public health/info only when data is genuinely safe.
- [ ] Do not expose health details to anonymous callers unnecessarily.
- [ ] Kept env/configprops `show-values=never` in baseline.
- [ ] If using `when-authorized`, explicitly configured `roles`.
- [ ] Never use `always` for routine incidents.
- [ ] Configured custom sanitizers for domain-sensitive keys.
- [ ] Verified sanitizers do not alter real config values.
- [ ] Not relying on sanitizers to protect heapdump/logfile/traces.
- [ ] Never print secrets into logs or other APIs.
- [ ] Protected metric tags against PII/tokens.
- [ ] If log levels must change, properly managed permissions and CSRF.
- [ ] Enforced auditing, approvals, and time limits when opening a diagnostic profile.
- [ ] Tests cover 401/403/200 per role.
- [ ] Tests verify dummy tokens never appear in responses.
- [ ] Tests verify unexposed endpoints return no data.
- [ ] Smoke tests run through the actual production management port/ingress.
- [ ] NetworkPolicy/firewall and TLS match topology.
- [ ] Procedures exist for handling diagnostic artifacts that may hold sensitive data.
- [ ] Plan exists to restore baseline exposure after incidents.
- [ ] Rotation/revocation procedures exist if secret leaks are detected.
- [ ] Every custom endpoint has an owner.
- [ ] Documented applicable Spring Boot/Spring Security versions during upgrades.

## 33. Summary

Diagnosing configuration errors means answering **the right question with the least data**. Spring Boot Actuator provides strong observability, yet endpoints like `/env` and `/configprops` can reveal far more than the target of investigation.

A policy summarized as a diagram:

```text
Need to diagnose?
       |
       v
Select only required endpoint
       |
       v
Enable/expose intentionally
       |
       v
Restrict management network
       |
       v
Authenticate + authorize
       |
       v
Mask values by default
       |
       v
Optional OPS reveal with role + sanitizer
       |
       v
Audit response / retention / close after incident
```

**Key takeaways:**

- `enabled` does not mean `exposed`.
- `exposed` does not mean `authorized`.
- `authorized` does not mean permitted to see all raw values.
- `show-values=when-authorized` does not replace endpoint authorization.
- `SanitizingFunction` does not replace network isolation and does not protect heapdumps/logs.
- Custom `SecurityFilterChain`s require explicit Actuator protection.
- An incident may justify temporarily opening an endpoint, yet always requires timeboxing, auditing, and closing afterward.

By following these principles, development and operations teams can still leverage Actuator to find `Environment`, profile, and binding issues without turning diagnostic paths into a sensitive-data leak channel.

### Official References

1. [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): enablement, HTTP/JMX exposure, Spring Security, CSRF, and sanitization.
2. [Spring Boot 3.3 — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html): base path, management port, bind address, SSL, and disabling HTTP management.
3. [Spring Boot 3.3 — Actuator REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/index.html): endpoint URLs, requests, and responses.
4. [Spring Boot 3.3 — `SanitizingFunction` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/SanitizingFunction.html): custom value sanitization.
5. [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): `Environment`, property sources, profiles, and configuration binding.
6. [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): filter chains, authorization, and request matchers.
7. [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): protection for state-changing HTTP requests.
8. [Spring Boot 3.3 — Actuator Health](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health): health groups, components, and show-details.
