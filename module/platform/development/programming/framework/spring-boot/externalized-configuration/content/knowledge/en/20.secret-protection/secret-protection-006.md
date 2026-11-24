# Hiding Values During Diagnostics with Actuator env and configprops

## 1. The problem: needing to observe configuration without leaking secrets

When a Spring Boot application runs in a real environment, operators often need to know:

- Which profiles are currently active?
- Why did a bean receive a different endpoint than in `application.yml`?
- Did a setting come from an environment variable, command-line argument, or Config Data file?
- Which fields were bound on a `@ConfigurationProperties` object?
- Was a value overridden by a higher-precedence source?

Spring Boot Actuator provides endpoints to aid diagnostics. Two endpoints directly tied to externalized configuration are:

- **`/actuator/env`**: information from `ConfigurableEnvironment` and `PropertySource`s.
- **`/actuator/configprops`**: beans whose configuration is bound via `@ConfigurationProperties`.

Yet application configuration does not consist only of hosts, ports, and timeouts. It can carry highly sensitive data: passwords, tokens, API keys, URIs with credentials, database passwords, signing keys, connection strings, or infrastructure-specific values.

Suppose the application is supplied configuration:

```yaml
inventory:
  endpoint: https://inventory.example.invalid/api
  connect-timeout: 2s
  api-token: "DO_NOT_USE_REAL_SECRET_IN_EXAMPLES"

spring:
  datasource:
    username: app_user
    password: "DO_NOT_USE_REAL_PASSWORD_IN_EXAMPLES"
```

An operator may need to confirm `inventory.connect-timeout` was loaded, yet **there is no reason for a public diagnostic page to return `inventory.api-token` or `spring.datasource.password`**.

In modern Spring Boot generations, Actuator **masks values (sanitize/redact)** in `env` and `configprops` by default. Values are replaced with a placeholder string such as `******`. Property names, source information, or bean structure may still appear depending on the endpoint and version.

This lesson explains how value masking works, how to control `show-values`, how to restrict who has permission to view, how to verify results, and the limitations of value-masking mechanisms. The goal is not "how to expose all information," but **diagnosing the necessary issues with least-privilege access**.

## 2. Three protective layers that must remain separate

A common mistake is thinking `show-values: never` alone makes an endpoint completely safe, or thinking placing an endpoint behind a login screen eliminates all secret-leak risks.

In reality, there are **three independent decisions**:

1. **Does the endpoint exist and is it exposed?** Controlled by access/enablement and `management.endpoints.web.exposure.*` or JMX.
2. **Who is allowed to call the endpoint?** Controlled by Spring Security, reverse proxies, mTLS, IAM, management networks, and authorization rules.
3. **Which values are shown when the endpoint responds?** Controlled by `management.endpoint.env.show-values`, `management.endpoint.configprops.show-values`, and any configured `SanitizingFunction`s.

Diagram:

```text
Client / operator
       |
       v
Can connect to management interface?
       |
       v
Is endpoint enabled/accessible and exposed?
       |
       v
Does Security allow the request?
       |
       v
Actuator gathers configuration info
       |
       v
Apply show-values + sanitization
       |
       v
HTTP/JMX response to client
```

Do not conflate:

- **`404 Not Found`**: the endpoint may not be exposed, not registered, or the path is wrong.
- **`401 Unauthorized`**: the request requires authentication.
- **`403 Forbidden`**: authenticated, yet not permitted to access.
- **`200 OK` with `******` values**: the endpoint is accessible, yet values are masked.
- **`200 OK` with raw values**: may be intentional for an authorized account, or may be a serious security bug.

A masked response does not mean the list of key names, property source names, bean names, file paths, or environment structure is harmless. **Metadata** itself can sometimes disclose architectural and deployment details.

## 3. Definition of the `env` endpoint

`env` is an Actuator endpoint providing a view into `ConfigurableEnvironment`. In Spring Boot, configuration from multiple sources is arranged into a prioritized list of `PropertySource`s.

A generalized response might contain:

```json
{
  "activeProfiles": ["prod"],
  "propertySources": [
    {
      "name": "systemEnvironment",
      "properties": {
        "INVENTORY_API_TOKEN": {
          "value": "******"
        }
      }
    }
  ]
}
```

This is an illustrative structure only; exact field names and response formatting may differ by version, property source, and query form. The `******` value is a sanitized representation, not the real token.

`env` is useful for observing:

- Active profiles and default profiles.
- The list of participating property sources.
- Values or information about a supplied key.
- Which source supplied a value and, in some cases, the property's *origin*.
- How multiple sources declare the same key and the order in which they are evaluated.

Example endpoint querying a specific property:

```text
GET /actuator/env/inventory.connect-timeout
```

This is a **read-only configuration path**, not an API for updating values. Querying a specific key narrows the result, yet **does not bypass security or sanitization rules**.

### 3.1. `env` is not like reading an entire YAML file

Actuator `env` does not simply return the raw contents of `application.yml`. It looks into `Environment` after configuration sources have been organized, potentially including environment variables, command-line args, system properties, and sources added by libraries.

Thus:

```text
Value in application.yml          = localhost
Value from environment variable   = inventory.internal
Effective value chosen by resolver = inventory.internal
```

If two sources declare the same key, check the ordering and effective value. When `show-values=never`, the endpoint may not return original values. **Diagnosing via sources and metadata does not require exposing all secrets**.

## 4. Definition of the `configprops` endpoint

`configprops` presents Spring Boot-managed beans bound via `@ConfigurationProperties`.

Example:

```java
package com.example.inventory;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "inventory")
public record InventoryProperties(
        URI endpoint,
        Duration connectTimeout,
        String apiToken
) {}
```

And registration:

```java
@SpringBootApplication
@EnableConfigurationProperties(InventoryProperties.class)
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
```

At context startup, the Binder may receive:

```yaml
inventory:
  endpoint: https://inventory.example.invalid/api
  connect-timeout: 2s
  api-token: "DO_NOT_USE_REAL_SECRET_IN_EXAMPLES"
```

`configprops` gives insight into **bound configuration objects and binding metadata**, rather than just raw `PropertySource` entries. A response may include branches such as `contexts`, `beans`, `prefix`, `properties`, and `inputs`. In modern default configurations, sensitive values are presented sanitized.

**Differences:**

| Aspect | `env` | `configprops` |
| --- | --- | --- |
| Focuses on | Property sources in `Environment` | `@ConfigurationProperties` beans |
| Common question | "Which source did this key come from?" | "How did the configuration object bind?" |
| Can show | PropertySource, profiles, origin | Prefix, bean, fields, and binding inputs |
| Value-hiding setting | `management.endpoint.env.show-values` | `management.endpoint.configprops.show-values` |
| Risk | Exposing tokens, passwords, infrastructure sources | Exposing bound object data and application structure |

Both serve diagnostics and should not be treated as public inventories of system secrets.

## 5. Adding Spring Boot Actuator to an application

With Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

With Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

With Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
```

These snippets assume dependency versions are managed by the Spring Boot parent, BOM, or plugin per project setup. Do not arbitrarily pin a separate Actuator version when dependency management is already consistent.

After adding Actuator, endpoints may be auto-configured, yet **that does not mean all endpoints are immediately reachable over HTTP**.

In the default configuration of many modern Spring Boot versions, **only `health` is exposed over HTTP and JMX**; `env` and `configprops` must be intentionally exposed to be called externally. Access/enablement settings can also affect endpoint availability.

## 6. Security baseline: do not expose `env` and `configprops` by default

For production, a conservative starting configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
    jmx:
      exposure:
        include: "health"

  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Notable points:

- Only `health` and `info` are requested for HTTP exposure in the example.
- Neither `env` nor `configprops` is in the web exposure list.
- Only `health` is exposed over JMX in the example.
- `show-values: never` is explicitly declared as a defensive policy to prevent showing values if someone later changes exposure.
- This is **not** a reason to allow arbitrary access to the remaining endpoints; `health`/`info` also require considering detail level and access network.

If `info` is not needed in production, keep the list to `health` only.

### 6.1. `show-values: never` does not disable the endpoint

Suppose you change it to:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,env,configprops"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Now `env` and `configprops` are requested to be exposed over HTTP provided they are enabled and appropriate web infrastructure exists. Setting `show-values: never` **does not turn the endpoint into a 404**; it only controls how values are presented.

Even when values are `******`, a response can still reveal property names, bean structure, profiles, or configuration source names. Therefore, protect the endpoint as an administrative resource.

### 6.2. Exposure differs from access

Newer Spring Boot versions add granular access configuration for endpoints, such as restricting to read-only or setting `none`. Mechanisms like `management.endpoint.<id>.access` and global limits may vary by version.

When securing a deployed application, consult documentation for the exact version:

- **Is the endpoint allowed to exist?**
- **Over which channels is it exposed?**
- **Who is permitted to call it?**
- **When responding, how much data is masked?**

Do not use a single setting as a substitute for answering all of these questions.

## 7. `show-values`: three modes controlling how data is displayed

Two central properties:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

Three values are commonly supported by Spring Boot:

| Value | Meaning when endpoint returns data | Caution level |
| --- | --- | --- |
| `never` | Always sanitize values, typically to `******` | Default/conservative choice |
| `when-authorized` | Show raw values to callers deemed authorized, except values masked by custom sanitizers | Use only when truly needed with tight authorization |
| `always` | Allow showing raw values to anyone able to call the endpoint, unless masked by custom sanitizers | High risk; avoid on real systems |

YAML form:

```yaml
management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

In modern Spring Boot 3.x/4.x releases, the default is `never`. Examples use lowercase/kebab-case values for readability. Older version docs may show uppercase enum forms like `NEVER`, `WHEN_AUTHORIZED`, `ALWAYS`; check your exact application version when comparing.

**Important:** both `env` and `configprops` have separate settings. Changing `env.show-values` does not change `configprops`'s policy.

### 7.1. `never`: masks all values by default

With:

```yaml
management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Values are sanitized even if the caller is logged in, provided the endpoint follows the standard behavior of that Spring Boot version.

Illustrative response example:

```json
{
  "name": "systemEnvironment",
  "properties": {
    "WAREHOUSE_API_TOKEN": {
      "value": "******"
    },
    "WAREHOUSE_CONNECT_TIMEOUT": {
      "value": "******"
    }
  }
}
```

Even non-sensitive values like timeouts may be masked. This is an intentional trade-off: **data protection takes priority over returning all details for convenient debugging**.

This mechanism does not remove secrets from `Environment`, prevent beans from using secrets, or encrypt original data; it only affects representations on sanitized endpoints.

### 7.2. `when-authorized`: conditional on caller

Example:

```properties
management.endpoint.env.show-values=when-authorized
management.endpoint.env.roles=ACTUATOR_ADMIN
management.endpoint.configprops.show-values=when-authorized
management.endpoint.configprops.roles=ACTUATOR_ADMIN
```

When Spring Boot determines the HTTP caller is authenticated and holds an appropriate role, values **may** be shown unmasked. Otherwise, values remain sanitized, assuming the request is allowed to reach the endpoint.

This is an option for an operational workflow that genuinely needs to inspect values, yet it does not provide the whole security setup on its own. Authentication, authorization, network controls, and logging controls must be configured separately.

### 7.3. `always`: why it should be avoided

```properties
management.endpoint.env.show-values=always
management.endpoint.configprops.show-values=always
```

If any caller reaches the endpoint, values can appear unmasked, including keys not masked by custom sanitizers.

Dangers:

- A reverse proxy misconfiguration can expose the endpoint to the Internet.
- A read-only observer account can read credentials of other services.
- Monitoring tools may store raw JSON into log systems or tickets.
- Copying responses into bug reports can send secrets to inappropriate channels.
- Values placed under key names lacking `password` or `token` can still be secrets.

Therefore, **never use `always` as a "quick debugging trick" in production**. For local demos, if you truly need to illustrate this mode, use only fake values, an isolated process, and no real sensitive data.

## 8. `when-authorized`: what is `roles`?

According to Actuator behavior documented by Spring Boot:

- For **HTTP endpoints**, "authorized" relates to authenticated status and the roles configured for the endpoint.
- If `roles` is not declared, under applicable configuration, **any authenticated user** may be treated as authorized to view values.
- If `roles` is declared, only principals satisfying a matching role are treated as authorized.
- For **JMX endpoints**, Actuator docs state that users are always considered authorized when evaluating `show-values=when-authorized`. Thus you cannot rely on `roles` alone assuming JMX masks values like HTTP.

Example:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: "ACTUATOR_ADMIN"

    configprops:
      show-values: when-authorized
      roles: "ACTUATOR_ADMIN"
```

Intent: role `ACTUATOR_ADMIN` represents the operator group permitted to inspect configuration data under a controlled process.

**Note on role interpretation:** in Spring Security, `hasRole("ACTUATOR_ADMIN")` normally corresponds to authority `ROLE_ACTUATOR_ADMIN` per the `ROLE_` prefix convention. However, actual authority assignment depends on security configuration. Test with a real application principal and verify the `roles` setting takes effect properly.

### 8.1. Does omitting `roles` mean no authorization?

Not quite. There is still a security layer controlling **endpoint access**. Yet with `when-authorized`, if no specific role is specified, merely "being logged in" can be enough to **view raw values** in HTTP responses.

That is why you should not configure:

```properties
management.endpoint.env.show-values=when-authorized
```

and assume only admin accounts can see values. Check the definition of authorized and apply both endpoint roles and appropriate HTTP access policies.

### 8.2. Rejected requests differ from receiving masked data

Suppose a security chain specifies **only `ACTUATOR_ADMIN`** may access `/actuator/env`. Regular users will receive 401/403, not a 200 response with masked values.

In another configuration allowing operators to read the endpoint, while `show-values=when-authorized` treats only admins as authorized to see values, operators can receive a sanitized response.

Both approaches can meet secret-protection goals. You must design and test **both HTTP status codes and response bodies**.

## 9. Important issue: JMX is not like HTTP

A risky misconception:

> "I set `show-values=when-authorized` and `roles=ACTUATOR_ADMIN`, so every actuator access path protects data just like HTTP."

In modern Actuator documentation, for **JMX**, users are considered authorized when evaluating `when-authorized`. Consequently, role configuration designed for HTTP **does not provide equivalent guarantees over JMX**.

If JMX diagnostics are not needed, do not expose `env` and `configprops` over JMX:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "health"
```

If the environment genuinely requires JMX, protect the JMX/RMI management interface with authentication, trusted networks, firewalls/TLS, and appropriate access controls. Do not treat `management.endpoint.env.roles` as end-to-end JMX protection.

Safe recommendations for most applications:

- Expose as few endpoints over JMX as possible.
- Keep `show-values: never` when raw values are unnecessary.
- Use `when-authorized` only after controlling all relevant access channels, not HTTP alone.
- In security audits, check both web and JMX exposure, not just one list.

## 10. Separate profile configuration for local diagnostics

Instead of keeping `env` and `configprops` permanently exposed in production, enable them in an isolated diagnostic profile.

Shared `application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
    jmx:
      exposure:
        include: "health"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

File `application-local-observability.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,env,configprops"

  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Launch for demo purposes, e.g.:

```bash
java -jar app.jar --spring.profiles.active=local-observability
```

Expectations:

- `/actuator/env` and `/actuator/configprops` are exposed only when this profile is active and higher sources do not override the policy.
- Values remain masked via `show-values: never`.
- No real tokens need to be put into configuration.
- Learners can observe key names and binding structure without accidentally printing raw values.

**Do not treat the word `local` in a profile name as a security measure.** An operator could still accidentally enable the profile in another environment via `spring.profiles.active`. Network, security, and deployment policies determine where endpoints are reachable from.

If production must strictly never expose the two endpoints, enforce guardrails in deployment configuration, policies, or exposure verification tests rather than relying solely on profile naming conventions.

## 11. Protecting endpoints with Spring Security

For web applications with Spring Security, configure Actuator access permissions explicitly if exposing diagnostic endpoints.

A Spring Boot 3.x, Spring Security 6.x example for a Servlet application:

```java
package com.example.security;

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
    SecurityFilterChain actuatorChain(HttpSecurity http)
            throws Exception {

        http.securityMatcher(EndpointRequest.toAnyEndpoint());

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ACTUATOR_ADMIN"));

        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Meaning:

- The first security chain applies to Actuator endpoints via `EndpointRequest`.
- Only principals with role `ACTUATOR_ADMIN` are allowed to access those endpoints.
- The second security chain handles the rest of the application and requires authentication in this example.
- This is an illustrative configuration, not a complete production policy for all APIs. Depending on the app, you may need OAuth2 resource server, sessions, CSRF, identity management, CORS, and appropriate authorization.
- Secure user/role provisioning is required. **Do not add an admin account with a hardcoded password into source code** just for an example.

**Version caution:** the package of `EndpointRequest` in Spring Boot 4 may differ from Spring Boot 3. For instance, Boot 4.x releases moved this API to a namespace related to `org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest`. Use the import matching the dependency version you are building against; do not copy an old import if the IDE reports it does not exist.

### 11.1. When custom `SecurityFilterChain`s exist

Spring Boot normally auto-configures security for Actuator when Spring Security is on the classpath and the application does **not** define its own `SecurityFilterChain`. Once a project defines one or more custom chains, Actuator security auto-configuration may yield control to the project.

This creates a risk: after adding `management.endpoints.web.exposure.include=env,configprops`, an existing chain with an overly broad `permitAll()` rule can make the endpoints unintentionally accessible.

Therefore, inspect the application's actual security policy and write HTTP client tests. **Do not conclude "Spring Security is on the classpath so `env` is safe"** when the project has custom security.

### 11.2. Separating the management port

One isolation option:

```properties
management.server.port=9091
management.server.address=127.0.0.1
```

This is an example of binding the management interface to loopback so only processes on the same machine can reach it under a simple network model. In containers/Kubernetes, `127.0.0.1` is scoped to the container's network namespace and can break monitoring scrapes if poorly designed.

Adjust to the environment and verify actual network routes:

- Expose only necessary endpoints.
- Protect the management port with network policies/firewalls or internal proxy services.
- Use TLS when transmitting sensitive data over network connections.
- Authenticate and authorize risky endpoints.
- Do not make the management port public just because the main app serves public APIs.

**Separating ports does not replace authentication.** If the management port is accidentally forwarded or published, information can still be accessed.

## 12. Establishing a cautious policy for `env` and `configprops`

An illustrative baseline when you **must** expose the two endpoints over an internal web network:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,env,configprops"
    jmx:
      exposure:
        include: "health"

  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Accompanying operational requirements:

1. Allow access only from management network sources.
2. Protect via Spring Security or an equivalent authentication layer.
3. Keep `never` even for admins if the need is solely identifying key/source names.
4. Never write responses to logs or monitoring stores lacking access control.
5. Never store hardcoded secrets in the repository to "make diagnostics easier".

If you need to inspect a **non-sensitive** value like a timeout, it is usually better to provide controlled diagnostic info—such as a health detail or metric exposing only safe parameters—rather than opening all of `env` with `always`.

## 13. Allowing admins to view values in limited situations

When an incident truly requires knowing certain property values, you may consider:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,env,configprops"
    jmx:
      exposure:
        include: "health"

  endpoint:
    env:
      show-values: when-authorized
      roles: "ACTUATOR_ADMIN"
    configprops:
      show-values: when-authorized
      roles: "ACTUATOR_ADMIN"
```

Understand the consequence: **authorized admins can see secrets too**, except values further masked by a custom `SanitizingFunction`. Apply this only if that level of access is genuinely approved.

In practice, holding an "application admin" account does not automatically mean that person needs to read DB passwords or signing keys. Often an operational principal only needs to see status and source names; permission to read raw secrets should belong to a separately controlled secret workflow.

Accompanying safeguards:

- Management network or controlled tunnel.
- Strong authentication and dedicated endpoint role.
- Time/scope limits on access permissions.
- Access auditing per organizational rules.
- Avoid recording responses containing secrets in terminal history, tickets, logs, or chat.
- Revoke access/disable exposure after diagnostics if enabled temporarily.

Do not "temporarily turn on" `always` just because `when-authorized` is not working yet. When a role check fails, fix the security configuration and tests instead of removing the protection layer.

## 14. Why custom `SanitizingFunction` still matters

In modern Spring Boot versions, Actuator documentation describes an extension point named **`SanitizingFunction`**.

Purpose: even when `show-values` permits showing data to authorized callers, a custom `SanitizingFunction` can still **mask specific values** by key name, source, or suitable criteria.

For instance, the application wants to strictly never show values related to:

```text
internal-signing-material
client-private-credential
integration-authorization
partner-api-key
```

even when an admin uses `when-authorized`. A custom sanitizer can enforce that rule.

Note: `SanitizingFunction` is an **endpoint serialization extension**, not a solution for encrypting stored data, hiding secrets from heap memory, or protecting against all forms of logging.

### 14.1. Example `SanitizingFunction` bean

In Spring Boot versions with the matching API:

```java
package com.example.security;

import java.util.Locale;

import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ActuatorSanitizationConfiguration {

    @Bean
    SanitizingFunction applicationSecretSanitizer() {
        return data -> {
            String key = data.getKey().toLowerCase(Locale.ROOT);

            if (key.contains("authorization")
                    || key.contains("api-key")
                    || key.contains("private-credential")
                    || key.contains("signing-material")) {
                return data.withSanitizedValue();
            }

            return data;
        };
    }
}
```

Explanation:

- The function receives `SanitizableData`.
- `getKey()` reports the key name currently being processed.
- If it matches an application-defined rule, `withSanitizedValue()` returns the data with the value masked.
- If it does not match, return the original data to continue through the sanitizer mechanism.
- Never log `data.getValue()`, as it may contain secrets.

API examples and extension points depend on the Spring Boot version; check the Javadoc for your project's version before copying code verbatim. This illustrates **intentional sanitization extension**.

### 14.2. Using convenience APIs in supported versions

In some newer versions, helpers can be used such as:

```java
@Bean
SanitizingFunction customKeyMasking() {
    return SanitizingFunction.sanitizeValue()
            .ifKeyContains("authorization", "private-credential");
}
```

This example clarifies **which key names to mask** without writing a full lambda. Convenience methods may be added across releases; use the API present in your actual dependency rather than copying a method that does not exist in older Spring Boot versions.

### 14.3. Do not rely on simple key names to find every secret

A token might be placed under names like:

```text
external.service.auth
integration.header-value
cloud.client.configuration
third-party.connection
```

Not every key contains the word `password` or `token`. Therefore:

- First, **do not show raw values** unless needed.
- If showing is needed, write sanitizer rules matching your application's configuration contract.
- Check nested paths, lists, Maps, URIs, and structured fields.
- Keep the sensitive-key list updated when adding new integrations.
- Write tests verifying fake sensitive values remain masked.

Sanitizers are **defense in depth**, never the sole line of protection.

## 15. Beware of outdated Spring Boot 2 guides

Some older documentation and blogs use:

```properties
management.endpoint.env.keys-to-sanitize=...
management.endpoint.configprops.keys-to-sanitize=...
```

These names appeared in docs for certain Spring Boot 2.x versions. In modern Boot 3.x/4.x versions, the sanitization workflow and extension points have changed; those legacy properties must not be assumed to still take effect.

If old configuration is copied to a newer system, a dangerous situation can arise:

1. The file contains a property ignored by the newer version.
2. Operators assume sensitive keys are masked by the old pattern.
3. `show-values` gets opened broadly.
4. The endpoint risks returning raw values unintentionally.

Therefore:

- Prefer `show-values: never` for both endpoints.
- When custom masking is needed, consult `SanitizingFunction` docs for your exact version.
- Do not rely on "the property appears in YAML" to assert the mechanism is active.
- Write real HTTP tests checking responses, especially after Spring Boot upgrades.

**Verify endpoint behavior**, not just configuration key names.

## 16. A safe hands-on lab with fake data

Let's create a small application to observe both `env` and `configprops`. No real tokens or live service connections are needed.

### 16.1. Sample configuration

`src/main/resources/application.yml`:

```yaml
demo:
  endpoint: https://demo.example.invalid/api
  timeout: 1500ms
  api-token: "EXAMPLE_NOT_A_REAL_TOKEN"

management:
  endpoints:
    web:
      exposure:
        include: "health,env,configprops"
    jmx:
      exposure:
        include: "health"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

### 16.2. Configuration properties class

```java
package com.example.actuatorlab;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        URI endpoint,
        Duration timeout,
        String apiToken
) {}
```

### 16.3. Registering the record

```java
package com.example.actuatorlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(DemoProperties.class)
public class ActuatorLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ActuatorLabApplication.class, args);
    }
}
```

The project uses `spring-boot-starter-actuator` and an appropriate web starter for HTTP endpoints, such as `spring-boot-starter-web` in a Spring MVC app. If security is needed, add `spring-boot-starter-security` and a genuinely appropriate policy; never rely on an unprotected sample for production.

### 16.4. Starting in an isolated environment

Illustrative command:

```bash
java -jar app.jar
```

In a demo without Spring Security and with an HTTP server, the exposure config can make `/actuator/env` and `/actuator/configprops` reachable. **Run such a demo only on an isolated test machine/network, with all values being fake data.**

Query:

```bash
curl -i http://127.0.0.1:8080/actuator/env
```

Or:

```bash
curl -i http://127.0.0.1:8080/actuator/configprops
```

Key observations:

- The response shows the endpoint is reachable under demo conditions.
- Configuration values are sanitized per `show-values: never`.
- The string `EXAMPLE_NOT_A_REAL_TOKEN` does not appear in either endpoint's response.
- Property names or bean structure may still appear.

**There is no requirement to disable sanitization** to prove the endpoint works. Instead of looking for the token in the response, proactively assert that the fake token **does not appear**.

## 17. Predicting results when changing `show-values`

With the same fake data, you can build a table of policy meaning before running:

| `env.show-values` | HTTP caller | Raw values |
| --- | --- | --- |
| `never` | Caller permitted to access endpoint | Sanitized |
| `when-authorized` | Does not satisfy role | Sanitized, if request is still permitted |
| `when-authorized` | Authenticated and satisfies role | May be shown, unless masked by custom sanitizer |
| `always` | Any caller reaching the endpoint | May be shown, unless masked by custom sanitizer |

Same for `configprops.show-values`, though the two properties can be configured differently.

For JMX, do not apply this HTTP table directly without accounting for JMX rules; under `when-authorized`, JMX callers are treated as authorized per modern Actuator docs.

Safe practice should prioritize:

1. Keeping `never`.
2. Adding tests proving masked responses.
3. If you truly must test `when-authorized`, using only **fake** tokens, with an admin principal and a regular principal, running in a test environment.
4. Never practicing `always` with any real-environment credentials.

## 18. HTTP testing across three layers: exposure, authentication, masking

To be sure secrets do not leak, asserting `status=200` is not enough. Tests must verify three aspects:

- Whether the endpoint is exposed as intended.
- Whether users with the right role are permitted and users with wrong roles are blocked.
- In successful responses, whether sensitive values are masked.

Example test strategy:

```text
Scenario A: production baseline
  GET /actuator/env -> not exposed / rejected
  GET /actuator/configprops -> not exposed / rejected

Scenario B: diagnostic profile, never
  GET /actuator/env -> permitted if security allows
  Body lacks fake token
  GET /actuator/configprops -> permitted if security allows
  Body lacks fake token

Scenario C: when-authorized, admin role
  Other operator role: cannot view raw values
  Admin: recognized as authorized
  Custom sanitizer still masks protected keys
```

These are **test design** scenarios, with no guarantee every project uses the same HTTP status when an endpoint is unexposed or a principal lacks permission.

### 18.1. Integration test example with MockMvc

In a Servlet project using Spring Boot Test + Spring Security, you can write an illustrative test:

```java
package com.example.actuatorlab;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest(properties = {
    "demo.api-token=EXAMPLE_NOT_A_REAL_TOKEN",
    "management.endpoints.web.exposure.include=health,env,configprops",
    "management.endpoint.env.show-values=never",
    "management.endpoint.configprops.show-values=never"
})
@AutoConfigureMockMvc(addFilters = false)
class ActuatorMaskingTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void envDoesNotEchoToken() throws Exception {
        MvcResult result = mockMvc.perform(
                get("/actuator/env"))
            .andReturn();

        String body = result.getResponse().getContentAsString();

        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        assertThat(body).doesNotContain("EXAMPLE_NOT_A_REAL_TOKEN");
    }

    @Test
    void configpropsDoesNotEchoToken() throws Exception {
        MvcResult result = mockMvc.perform(
                get("/actuator/configprops"))
            .andReturn();

        String body = result.getResponse().getContentAsString();

        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        assertThat(body).doesNotContain("EXAMPLE_NOT_A_REAL_TOKEN");
    }
}
```

**Important condition of this example:** `addFilters = false` is used solely to **isolate the sanitization check** and avoid depending on the project's login mechanism; never treat it as production security configuration or proof that the endpoint is properly authorized.

In a real test suite, add **another test with security filters enabled**, using appropriately granted fake accounts/roles, to check HTTP 401/403/200 per policy. When the project has multiple context paths or a separate management port, adjust test client creation accordingly.

Depending on the Spring Boot version, the package of `@AutoConfigureMockMvc` may be organized differently; use the import matching your actual test dependency. The goal is testing behavior, not tying the lesson to a single minor version.

### 18.2. Do not assert entire rigid JSON snapshots

Response structures can change across Spring Boot versions, property sources, and auto-configured beans. A test comparing an entire long JSON snapshot is brittle even when masking policy works properly.

Focus assertions on:

- The endpoint is indeed reachable in the test context.
- The fake secret string **does not appear**.
- The sanitized placeholder appears in the expected field if the JSON has that field.
- Non-sensitive configuration info remains diagnosable as designed.

You can check specific JSON paths in a version-pinned integration test; do not expect the exact same shape across every Spring Boot release.

## 19. Testing `when-authorized` should not use real secrets

A safe approach is creating **a fake credential** dedicated to testing:

```text
demo.api-token=DEMO_FAKE_TOKEN_DO_NOT_USE
```

Then use two test principals:

- `ROLE_ACTUATOR_VIEWER`: may be allowed to read the endpoint yet not permitted to view raw values.
- `ROLE_ACTUATOR_ADMIN`: the principal defined by policy as eligible to view raw values in the test environment.

Check two conditions:

1. Does the `SecurityFilterChain` permit the HTTP request to reach the endpoint?
2. If the request returns 200, does `show-values` make the value masked or raw?

Do not assume if a viewer receives 403 that it was the result of sanitization. 403 is request authorization; sanitization only applies to **generated response content**.

Some tests should keep `show-values=never` even for admins. If you must test `when-authorized` with raw values, use a non-sensitive fake token and ensure test logs are not shipped to places lacking access control.

## 20. Configuration changes must use the exact endpoint name

A common mistake is writing:

```properties
management.endpoints.env.show-values=never
```

This path is wrong because `endpoints` (plural) is for settings covering **the set of endpoints and exposure**; `endpoint` (singular) is for configuring **a specific endpoint**.

Correct:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

And:

```properties
management.endpoints.web.exposure.include=health,env,configprops
```

Distinction:

```text
management.endpoints.web.exposure.include
         ^
     endpoints (plural)

management.endpoint.env.show-values
         ^
     endpoint (singular)
```

Corresponding YAML:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,env,configprops"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

When a configuration property is misspelled, Spring Boot may not apply it to Actuator as intended. Therefore **observe actual behavior**, rather than just reading the file and seeing the config line present.

## 21. Masking values does not mean hiding metadata

Even when `show-values=never`, the endpoint can still return:

- `PropertySource` names or source file locations.
- Property group names.
- Active profiles.
- Bean names and `@ConfigurationProperties` bean types.
- Configuration paths from `origin`, depending on response.
- Object structure or lists of declared keys.

This information can reveal:

```text
spring.datasource.url          // uses a database
cloud.partner.endpoint         // has a partner integration
internal.auth.issuer           // name of an auth system
payment.signing-key            // existence of signing material
prod-eu-west                   // operational region or profile
```

Not necessarily secret values, yet still **internal information**. Thus, masked responses must not automatically be considered safe to share publicly.

For support tickets or incident docs:

- Extract only the keys genuinely needed.
- Strip internal infrastructure source names/paths if unnecessary for the recipient.
- Do not attach full `/actuator/env` or `/actuator/configprops` responses without data review.
- Avoid saving configuration snapshots into long-retention uncontrolled log stores.

Protecting secrets includes **reducing unnecessary dissemination of internal information**.

## 22. Masking values does not replace secret management

Suppose Actuator returns:

```json
{
  "value": "******"
}
```

This does **not** mean:

- The underlying environment variable was removed.
- The password was encrypted in the configuration file.
- The secret is absent from Java memory.
- All startup logs were sanitized.
- Stack traces and exception messages cannot contain secrets.
- A custom endpoint written by the application automatically inherits sanitization.
- Someone with host/container access cannot read the value from other sources.

Actuator sanitization **is only one output control layer**. Combine it with:

1. A secret manager or appropriate secret-provisioning method.
2. Principle of least privilege.
3. Never putting real secrets in the source repository.
4. Never printing `@ConfigurationProperties.toString()` if objects contain credentials.
5. Never logging all environment variables or startup arguments containing secrets.
6. Never storing diagnostic responses in unprotected CI/CD artifacts.
7. Rotating/revoking credentials on signs of leakage.
8. TLS, network controls, and data-read auditing.

A common mistake is masking passwords in `env` while still having:

```java
log.info("Inventory configuration: {}", inventoryProperties);
```

With a record, `toString()` usually includes its components, so the token can appear in logs. **Actuator's sanitizer does not intervene in this log statement.**

A better approach is logging selected safe parameters:

```java
log.info(
    "Inventory integration configured, timeout={}",
    inventoryProperties.timeout()
);
```

Even then, consider whether the timeout, endpoint host, or remaining values match the authorization level of the logging system.

## 23. Secrets inside URIs or Maps are still secrets

Not every credential is named `password`.

Example of a connection string containing username and password inside a URI:

```text
jdbc:.../database?user=demo&password=FAKE_ONLY
https://demo-user:FAKE_ONLY@service.example.invalid
```

Or:

```yaml
integration:
  headers:
    Authorization: "Bearer FAKE_TEST_VALUE"
```

Or a configuration Map:

```yaml
partner:
  clients:
    alpha:
      authentication: "FAKE_TEST_VALUE"
```

When `show-values=always` or callers under `when-authorized` are allowed raw values, **highly sensitive strings can appear**, even if property names do not match a few custom sanitizer keywords.

Therefore:

- Design sanitizers around both **fields and data structures**.
- Consider header names like `Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key` if they appear in configuration.
- Do not assume a URI string converted to `URI` will automatically be masked.
- Write tests covering Maps, nested objects, and project-specific key names.
- When raw values are not needed, keep `never` instead of trying to craft a perfect blocklist of keywords.

## 24. Traps when using reverse proxies or API Gateways

Some deployments route management endpoints through:

```text
Operator -> Load Balancer -> API Gateway -> Reverse Proxy -> Spring Boot
```

At each layer, ask:

1. Does the proxy publish `/actuator/**` to the Internet?
2. Does the gateway strip auth headers or forward authenticated requests improperly?
3. Is TLS guaranteed across every necessary hop?
4. Does the WAF/logging layer store endpoint response bodies?
5. Is there shared caching for responses containing management data?
6. Could path rewriting make `/internal/env` actually point to `/actuator/env`?
7. Is a named URL protected only by "hard-to-guess paths" or by real authentication?

Setting `show-values=never` in Spring Boot helps mask values, yet does not fix routing, identity, and metadata exposure bugs outside the application.

Do not configure a proxy to "allow all internal" just because an IP belongs to a private network. Internal networks still carry risks of lateral movement, compromised accounts, or misconfigured routing rules.

## 25. Environment decision table

| Environment | Expose `env/configprops`? | Recommended `show-values` | Notes |
| --- | --- | --- | --- |
| Normal production | No, unless clearly needed | `never` | Prefer not exposing |
| Production with approved diagnostics | Internal only, with authorization | `never` first | Open raw only with reason and procedure |
| Staging with sensitive data | Restricted like production | `never` | Do not treat staging as harmless |
| Personal dev machine with fake data | Can expose for hands-on practice | `never` | Use fake tokens, loopback |
| Security tests | Expose in dedicated test context | Test `never`/`when-authorized` | Assert both HTTP access and body |
| Administrative JMX | Minimize as much as possible | `never` if exposed | `when-authorized` on JMX has separate rules |

There is no "safe dev profile" if it uses real credentials, listens on public ports, or logs full responses. Risk classification must be based on **data and reachability**, not just environment names.

## 26. When might you need to see a non-sensitive value?

There are cases where runtime parameters are genuinely helpful:

- Is the configured timeout `250ms` or `2s`?
- Was the retry count overridden from `3` to `5`?
- Is integration mode `SAFE` or `FAST`?
- Is a feature flag enabled or disabled?
- What is the batch limit?

If you want to expose **values reviewed as safe** to operators, design options include:

1. Create a custom diagnostic endpoint **returning only an approved allowlist of info**, with authentication/authorization.
2. Expose appropriate metrics or health details instead of returning entire property objects.
3. Use operational configuration or deployment status viewers with separate authorization.
4. Keep `env` and `configprops` masking everything by default.
5. When temporary raw viewing is needed, use an access-controlled procedure and never record responses in external systems.

This is usually safer than `show-values=always` on a general-purpose endpoint holding many secret sources.

### 26.1. What must an allowlist endpoint check?

If writing one yourself:

```java
@GetMapping("/internal/config-summary")
Map<String, Object> summary() {
    return Map.of(
        "mode", settings.mode(),
        "batchSize", settings.batchSize()
    );
}
```

this example only illustrates **picking two non-sensitive fields**. A custom endpoint still needs Spring Security, network policies, and caller verification; nothing protects it automatically just because the path starts with `/internal`.

Never accidentally return the entire `settings` in a Map after a refactor, as a token could be added to that object in the future.

## 27. Incident checklist: `env` returning unexpected values

When someone reports "`/actuator/env` is leaking values," analyze in order:

1. **Confirm the path**: which endpoint, over HTTP or JMX, which Spring Boot version?
2. **Check exposure**: was the endpoint exposed unintentionally?
3. **Check security**: which security filter chain applies, which roles are actually effective?
4. **Check `show-values`**: is `always` or `when-authorized` coming from a higher-precedence source?
5. **Check roles**: is `management.endpoint.env.roles` properly set, or is any logged-in user considered authorized?
6. **Check custom sanitizers**: is the bean created, does the key match the condition, are tests run?
7. **Check other sources**: does the app log secrets, trace requests/responses, or have another custom endpoint?
8. **Check who accessed it**: review access logs/audits per policy without creating extra secret copies.
9. **Reduce surface immediately**: stop exposure, set `never`, narrow network and permissions on signs of misconfiguration.
10. **Handle exposed secrets**: assess scope, rotate/revoke credentials if needed, and update playbooks.

When an incident involves real data, **do not reproduce it by printing more real secrets into terminals or chat**. Use fake values in tests to confirm the new configuration masks properly.

## 28. Checklist when `configprops` is missing values or beans do not appear

Not all missing data in `/actuator/configprops` is a sanitization issue.

Possible causes:

- `@ConfigurationProperties` class is not registered.
- Bean does not exist because auto-configuration conditions were not met.
- Prefix in Java and configuration file do not match.
- Value was loaded from a different source than the user expected.
- Configuration bean is created only under a specific profile or condition.
- Response is sanitized so `******` appears, not a "missing value".
- Security mode rejected the request.
- Endpoint is not exposed over HTTP.
- Different Spring Boot version has a different response structure.

Workflow:

1. Verify the bean is created and Spring-managed.
2. Check `@ConfigurationProperties(prefix=...)`.
3. Inspect property source names, possibly via secured `env`.
4. Check active profiles.
5. Confirm converters/Binders handle the Java type properly.
6. Check whether `show-values` is masking contents.
7. Never turn on `always` just to look at one field when safer checks exist.

A `******` value is not evidence that the application is using the literal password `******`. It is normally the endpoint's **sanitized representation**.

## 29. Testing with `curl`: how to read status codes

Suppose the app runs at `127.0.0.1:8080` in a test environment with fake data.

```bash
curl -i http://127.0.0.1:8080/actuator/health
```

Try:

```bash
curl -i http://127.0.0.1:8080/actuator/env
```

When unexposed, you may see 404; when blocked by security, 401 or 403. When permitted, you may see 200 with a masked body.

In environments using HTTP Basic, the tool can prompt for a password. Do not pass real passwords directly in commands saved in shell history or sent in support docs.

A way to call with a username without attaching the password as an argument:

```bash
curl -i -u admin \
  https://management.example.invalid/actuator/env
```

`curl` can prompt for the password; this only illustrates accessing a hypothetical endpoint and does not replace your project's security rules. When using OAuth2, mTLS, or dedicated gateways, the invocation differs accordingly.

**Do not send raw JSON responses that might contain secrets into tickets/chat**. If verification is needed, use a script/test checking that "no fake token appears" and report only the result.

## 30. Distinguishing Actuator sanitization from log masking

There are three places configuration data can leak:

```text
A. Actuator responses
   /actuator/env, /actuator/configprops

B. Application logs
   log.info("{}", properties), exception messages

C. External diagnostics
   CI logs, support bundles, monitoring exports
```

Actuator's `show-values` mechanism affects **A**. It does not automatically govern **B** or **C**.

Example:

```java
record AuthProperties(String clientId, String clientSecret) {}
```

When logging:

```java
log.debug("auth = {}", authProperties);
```

`record.toString()` can print `clientSecret` as well. Setting `management.endpoint.configprops.show-values=never` does not change this log.

If a secret string has already appeared in centralized logs, changing `show-values` does not delete saved records. Separate protection, retention, and rotation procedures are needed.

Commonly overlooked leak channels:

- Java startup arguments containing `--app.token=...`.
- Exceptions containing URIs with embedded credentials.
- Thread dumps or process environment dumps.
- HTTP exchange logging if sensitive bodies/headers exist.
- Actuator snapshots collected and saved by exporters.
- Debug config snippets sent over email or issue trackers.

A good policy must protect **sources, transit, storage, and diagnostic outputs**.

## 31. Common mistakes and fixes

### 31.1. Turning on `include="*"` for convenience and forgetting to turn it off

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

This requests exposing every exposable endpoint; it increases the attack surface and can expose unnecessary endpoints. Choose a minimal allowlist such as `health` or `health,info`.

### 31.2. Keeping `show-values=always` in production

Even behind a firewall, a routing or permission change can expose values. Use `never` by default and open raw viewing only under an approved process.

### 31.3. Using `when-authorized` without declaring `roles`

Per documented Actuator behavior, on HTTP, any authenticated user can be treated as authorized when `roles` is omitted. If restriction is needed, declare the right role and test.

### 31.4. Thinking HTTP roles protect JMX

JMX has its own rules. Limit JMX exposure and secure the JMX interface; do not assume HTTP role settings apply equivalently.

### 31.5. Thinking Spring Security auto-protects all endpoints when custom chains exist

Once an application declares a `SecurityFilterChain`, Spring Boot may yield security control. Check actual matchers and avoid letting `permitAll` cover actuator accidentally.

### 31.6. Using `keys-to-sanitize` properties from old docs

Do not rely on Spring Boot 2 properties as a guarantee in Boot 3/4. Check your version's docs, use `SanitizingFunction` if extension is needed, and verify responses with tests.

### 31.7. Masking only keys containing `password`

Credentials can live in `authorization`, `header-value`, URIs, Maps, or other names. A simpler and safer approach is `show-values=never` when raw values are unnecessary.

### 31.8. Seeing `******` and thinking the app lost data

The underlying data can still be used by the binder. Values are replaced in Actuator responses, not necessarily in runtime objects.

### 31.9. Handing raw JSON to external support

Even masked responses can contain property names and internal topology; if raw, the risk is far worse. Share only the minimal reviewed subset.

### 31.10. Using a separate management port without network policy

A separate port only changes the listening point. If published to a wide network or mis-forwarded by a proxy, endpoints remain reachable.

### 31.11. Using production data to test masking

You can use fake tokens with clear sentinels. No real passwords are needed to prove an endpoint masks strings properly.

### 31.12. Checking status without checking the response body

HTTP 200 does not mean the response is sanitized. Tests must confirm fake secrets do not appear.

### 31.13. Testing responses while forgetting security filters

If tests disable filters to isolate sanitizers, they have not verified IAM, roles, or network access. Add tests with filters enabled.

### 31.14. Forgetting another endpoint might return secrets itself

Actuator `env` and `configprops` have their own sanitization mechanisms. Custom endpoints, controllers, loggers, or exporters written by the app do not automatically inherit all of those protections.

### 31.15. Editing a YAML file and thinking configuration changed in the running process

Spring Boot configuration is typically loaded at startup. For beans created and bound once, editing YAML while the app is running does not guarantee beans or endpoint policies refresh automatically. To verify a new Actuator configuration, restart or use a properly implemented and tested refresh mechanism.

## 32. Exercise 1: distinguishing exposure and masking

Given:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health"
  endpoint:
    env:
      show-values: never
```

Questions:

1. Is `/actuator/env` exposed over HTTP according to this list?
2. Is `show-values: never` the only reason the endpoint cannot be reached?
3. If `env` is added to `include`, will raw values be shown or masked?
4. If Spring Security blocks all requests to `env`, should we expect a 200 response with `******`?

Solution guide:

- The `include` list does not contain `env` yet.
- `show-values` governs how values are displayed, not exposure policy.
- If the endpoint is exposed and the request is permitted, `never` still masks values.
- A security-blocked request may receive 401/403 rather than a configuration body.

## 33. Exercise 2: choosing role-based policy

Requirements:

- Regular operators have permission to call certain diagnostic endpoints.
- Only an approved admin group can view raw values when genuinely needed.
- Keys containing `private-credential` are always masked.
- JMX is not used to inspect env/configprops.

Suggested configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,env,configprops"
    jmx:
      exposure:
        include: "health"
  endpoint:
    env:
      show-values: when-authorized
      roles: "ACTUATOR_ADMIN"
    configprops:
      show-values: when-authorized
      roles: "ACTUATOR_ADMIN"
```

Then:

1. Configure HTTP security allowing the appropriate operator/admin groups.
2. Write a custom `SanitizingFunction` masking `private-credential` even when accessed by an admin.
3. Test a principal without the role and an admin principal.
4. Test that responses do not contain fake secrets matching the private key.
5. Do not use real production data in any test.

If raw values are unnecessary, simpler and more conservative is keeping `never`.

## 34. Exercise 3: finding mistakes in configuration

Given:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
  endpoint:
    env:
      show-values: always
    configprops:
      show-values: when-authorized
```

Issues to identify:

- Too many endpoints exposed.
- `env` can return raw values to anyone reaching the endpoint.
- `configprops` sets `when-authorized` without restricting a specific role; any authenticated user may be deemed authorized.
- Unknown whether Spring Security, firewall, TLS, or JMX policies exist.
- If someone created a custom `SecurityFilterChain` missing an Actuator matcher, access may be overly broad.

Recommended fix under least privilege: expose only truly needed endpoints, set `show-values: never` by default, protect network and HTTP, restrict JMX, and verify with integration tests.

## 35. Exercise 4: reading test results accurately

A test calls `/actuator/env` and observes:

```text
status = 200
body contains "demo.api-token"
body contains "******"
body does not contain "FAKE_DEMO_TOKEN"
```

Question: what can be concluded?

- The endpoint responded.
- Property names may be returned.
- The fake token value did not appear in the response.
- Some data was presented in sanitized form.

What cannot be concluded from this test:

- The endpoint is properly authorized for all principals.
- All sensitive keys are masked.
- There are no leaks in logs or custom endpoints.
- Production is running the exact same configuration.
- JMX cannot return raw values.

This is why multiple layers of testing and deployment verification are required.

## 36. Exercise 5: distinguishing `env` and `configprops`

Suppose an application has:

```java
@ConfigurationProperties(prefix = "notifications")
public record NotificationProperties(
        String token,
        Duration timeout
) {}
```

And YAML + environment variables can both declare the two keys.

Explain:

1. To know the order and source declaring `notifications.timeout`, inspect `env`.
2. To know a `NotificationProperties` bean exists and how it bound, inspect `configprops`.
3. When both endpoints have `show-values=never`, do not expect them to return raw tokens.
4. If one source overrides `timeout`, the bean receives the chosen value at binding time.
5. Never enable `always` just to debug a source-ordering issue; prefer metadata and controlled tests.

## 37. Exercise 6: responding when a secret leaked via an endpoint

Scenario: operations discovers `/actuator/env` in a real environment previously returned raw tokens due to `show-values=always`.

Actions to consider:

1. Restrict/disable exposure immediately per operational procedures.
2. Switch the policy to `never`.
3. Inspect security matchers, roles, reverse proxies, and firewalls.
4. Determine the timeframe the endpoint was reachable and which accounts/IPs called it.
5. Do not redistribute the JSON during investigation.
6. Evaluate rotating/revoking potentially exposed tokens.
7. Locate and handle copies saved in logs, monitoring, or tickets.
8. Add integration tests blocking fake raw tokens.
9. Inspect related endpoints like `configprops` and JMX channels.
10. Document configuration changes, docs, and operational playbooks.

Masking from now onward **does not make previously exposed copies of the secret disappear**.

## 38. Summary: principles for safe diagnostics

`env` and `configprops` are very useful when troubleshooting Spring Boot Externalized Configuration:

```text
/env
    -> Environment / PropertySources / sources and profiles

/configprops
    -> Bound @ConfigurationProperties beans
```

Yet every diagnostic benefit must sit inside a defense-in-depth model:

```text
Expose only when needed
        |
        v
Restrict network and JMX channels
        |
        v
HTTP authentication + authorization
        |
        v
show-values = never (safe default)
        |
        v
Custom SanitizingFunction if truly needed
        |
        v
Test responses do not leak fake secrets
        |
        v
Control logs, tickets, and support workflows
```

Principles to remember:

1. **`management.endpoint.env.show-values` and `management.endpoint.configprops.show-values` are two separate settings.**
2. **`never`** masks values in Actuator responses; the right modern default to start with.
3. **`when-authorized`** shows raw values only to callers deemed authorized; if `roles` is omitted, on HTTP merely being logged in can suffice.
4. **`always`** is very risky because it can display raw values to anyone reaching the endpoint.
5. **Exposing an endpoint does not mean allowing raw values**, and masking does not replace security.
6. **JMX has separate authorization behavior**; do not assume HTTP roles protect JMX.
7. **`SanitizingFunction`** adds masking for keys the app considers sensitive, even when policy allows viewing raw values.
8. **Never use old `keys-to-sanitize` guides without checking the Spring Boot version.**
9. **Masking values does not remove secrets from `Environment`** and does not protect all logs/custom endpoints.
10. **Test with fake values**, verifying both access and bodies; never use real credentials to demonstrate bugs.

The highest-safety choice for most deployments: **do not expose `env`/`configprops` on public channels, keep `show-values: never`, protect the management interface, and expose only the diagnostic information truly needed**.

### Further reading

- [Spring Boot — Actuator Endpoints, Exposing Endpoints, and Sanitize Sensitive Values](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Environment (env) REST API](https://docs.spring.io/spring-boot/api/rest/actuator/env.html)
- [Spring Boot — Configuration Properties (configprops) REST API](https://docs.spring.io/spring-boot/api/rest/actuator/configprops.html)
- [Spring Boot — SanitizingFunction Javadoc](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/endpoint/SanitizingFunction.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
