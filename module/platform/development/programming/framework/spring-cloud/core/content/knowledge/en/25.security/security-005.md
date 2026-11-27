# Masking Sensitive Values in env, configprops, and Logs

> **Chapter:** Security  
> **Module:** SPRING_CLOUD_CORE

Spring Cloud applications often receive configuration containing database passwords, client secrets, access tokens, API keys, session signing cookies, or URIs with embedded credentials. These values can appear in multiple places: the Spring `Environment`, `@ConfigurationProperties` beans, Actuator endpoints, and application logs. Masking them in only one place leaves secrets exposed through the others.

Spring Boot Actuator sanitizes values in `/actuator/env` and `/actuator/configprops` by default. You can adjust the display policy with `show-values` and extend rules using `SanitizingFunction`. Application logs are a separate stream: Actuator sanitization does not automatically filter log messages, exceptions, HTTP headers, MDC, or data sent to centralized logging systems.

This lesson explains how to protect all three surfaces in **SPRING_CLOUD_CORE**: keeping sensitive configuration values masked, controlling Actuator read access, building custom sanitization rules, logging via allowlists, and testing to detect leaked secrets.

## 1. Identifying Which Data Needs to Be Masked

Before configuring anything, inventory the sensitive data your application uses. Passwords and tokens are not the only secrets. Connection URLs can contain usernames/passwords; headers can carry bearer tokens; certain topology details or personal identifiers also require restricted visibility.

| Data Group | Example | Risk if Leaked |
| --- | --- | --- |
| Passwords | `spring.datasource.password` | Unauthorized access to databases or systems sharing credentials |
| Client secrets | `spring.security.oauth2.client.registration.catalog.client-secret` | Application impersonation when calling an OAuth provider |
| Access/refresh tokens | `access-token`, `refresh-token` | Session hijacking or calling APIs on behalf of a user |
| API keys | `partner.api-key` | Unauthorized use of API quotas or permissions |
| Cryptographic keys | `jwt.private-key`, `keystore.password` | Unauthorized token signing or data decryption |
| Cookies/session IDs | `Cookie`, `Set-Cookie`, session identifier | Login session hijacking |
| Connection strings | URI containing userinfo or query credentials | Exposure of connection details and access privileges |
| Personal data | email, phone number, identifiers | Personal data leakage and data policy violations |

A value can be sensitive even when the property name does not include keywords such as `password` or `token`. For example, `catalog.client.endpoint` may hold a URI with userinfo, while `tenant-key` may be a tenant-specific credential. Automatic rules reduce risk, but must be supplemented by a system-specific secret inventory.

### 1.1. Distinguishing the Three Surfaces to Protect

| Surface | How Data Enters | Primary Protection Mechanism |
| --- | --- | --- |
| Environment and Config Data | YAML, properties, environment variables, JVM arguments, Config Server | Secret source management and Actuator sanitization |
| ConfigurationProperties | Binder maps properties to bean fields | Sanitization in configprops, avoiding `toString()` leaks |
| Logs | Code logging messages, exceptions, headers, MDC, requests/responses | Do not log secrets; filter data before logging and in the pipeline |

`SanitizingFunction` handles data that Actuator passes to sanitizable endpoints. It is not a global filter for every string in the JVM. In particular, it does not modify logs already written by SLF4J, Logback, or Log4j2.

## 2. Actuator Masks Values in env and configprops by Default

Spring Boot Actuator sanitizes values returned from `/actuator/env` and `/actuator/configprops` to `******` by default. This rule applies even when endpoints are exposed over HTTP; operators can still view property names, property sources, prefixes, and bean structures while values remain masked.

Example configuration containing secrets:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    password: ${ORDERS_DB_PASSWORD}

catalog:
  client:
    base-url: https://catalog.internal
    access-token: ${CATALOG_ACCESS_TOKEN}
~~~

Responses from `/actuator/env` or `/actuator/configprops` show that the properties exist, while their values are replaced with `******`. This is Actuator's default protective behavior; there is no need to write a custom controller just to mask basic properties.

### 2.1. Do Not Confuse Sanitization with Encryption or Secret Storage

Sanitization only changes how values are presented in endpoint responses. It does not:

- Encrypt values in YAML files or environment variables.
- Replace a secret manager or key management system.
- Remove secrets from the JVM heap.
- Mask values when application code logs them directly.
- Prevent anyone with direct access to configuration sources or secret stores from reading them.
- Automatically rotate compromised credentials.

Secrets must still be supplied via an appropriate source such as a secret manager, protected Kubernetes Secrets, Vault, or the platform's secret management mechanism. Never commit real passwords or tokens to a repository on the assumption that Actuator masks them.

### 2.2. Exposure and Sanitization Are Separate Layers

To access an endpoint over HTTP, it must be exposed:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - env
          - configprops
~~~

Exposure only makes endpoints reachable over HTTP. The sanitization policy decides whether values are displayed. Authentication/authorization is yet another layer determining who is permitted to call the endpoint.

Do not broaden exposure just for quick debugging and forget to narrow it back down. env and configprops can reveal property names, bean names, profiles, internal addresses, and integration structures even when secret values are masked.

## 3. Configuring show-values per Endpoint

Spring Boot supports three options for sanitizable endpoints:

| Value | Behavior |
| --- | --- |
| `never` | Always mask values |
| `always` | Display raw values to endpoint callers |
| `when-authorized` | Display raw values only to authenticated callers holding configured roles |

Safe configuration for production environments:

~~~yaml
management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

`never` keeps values masked even when callers are logged in. This is the right choice when there is no operational requirement to inspect secrets through Actuator.

### 3.1. Using when-authorized When Operationally Needed

In some environments, operations teams need to view certain configuration values to investigate incidents. You can restrict this by role:

~~~yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles:
        - CONFIG_AUDITOR
    configprops:
      show-values: when-authorized
      roles:
        - CONFIG_AUDITOR
~~~

For HTTP endpoints, the user must be authenticated and hold a role listed in the endpoint configuration. If `roles` is omitted, every authenticated user is permitted to view raw values by default when `show-values` is `when-authorized`. Therefore, declare explicit roles rather than relying on the default.

Distinguish `show-values` roles from endpoint access permissions in Spring Security:

- `show-values` and `roles` decide whether values are returned raw or masked.
- The security filter chain decides whether the user may invoke the endpoint at all.
- Exposure decides whether the endpoint is open over HTTP.

All three layers must be configured. An endpoint can be protected from anonymous access yet still let too many authenticated users view raw values if roles are not restricted.

### 3.2. Be Careful with JMX

Spring Boot documentation specifies that JMX is treated as authorized for the `when-authorized` mechanism. Therefore, do not assume HTTP roles protect data when an endpoint is exposed over JMX.

If using JMX:

- Control who can connect to the MBean server.
- Secure the management port and remote JMX configuration.
- Do not expose JMX to untrusted networks.
- Consider keeping `show-values: never` for endpoints containing secrets.
- Audit JMX policies independently from Spring Security HTTP rules.

### 3.3. Do Not Enable always in Production

`always` displays values to anyone able to invoke the endpoint, regardless of role. It is not an appropriate way to troubleshoot production issues. When verifying configuration, inspect the secret source, bean status, or a non-secret check flag such as `credentialConfigured=true`.

Even if `SanitizingFunction` can still mask certain keys, do not use that as a reason to enable `always`. Any key missed by custom rules can be exposed.

## 4. Extending Rules with SanitizingFunction

Sensitive property names vary across systems. An application may use `partner-token`, `signing-material`, `private-key-content`, or an internal name outside the default keyword set.

Spring Boot provides the `SanitizingFunction` interface to customize value masking in Actuator data. `SanitizableData` provides the key, value, and PropertySource of the data being processed. The function can decide to mask based on key name, value, or configuration source.

Example using the fluent API available in Spring Boot 3.5+:

~~~java
import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ActuatorSanitizationConfiguration {

    @Bean
    SanitizingFunction sensitiveConfigurationSanitizer() {
        return SanitizingFunction.sanitizeValue()
                .ifKeyMatches(
                        ".*(password|client[-_.]?secret|access[-_.]?token"
                        + "|refresh[-_.]?token|api[-_.]?key|private[-_.]?key"
                        + "|authorization|cookie).*");
    }
}
~~~

The example rule matches keys whose names relate to password, client secret, token, API key, private key, authorization, or cookie. `ifKeyMatches` performs case-insensitive key matching in current APIs.

This is a supplemental rule tailored to the system's naming conventions. Tune the regex to actual properties, avoiding patterns that are too broad and mask non-sensitive data or too narrow and miss a secret.

### 4.1. Filtering by Key and Value

Some secrets cannot be identified by key name alone. For instance, a generically named property `endpoint` might hold a URI containing userinfo or a token. `SanitizingFunction` can filter by value:

~~~java
@Bean
SanitizingFunction redactCredentialLikeValues() {
    return SanitizingFunction.sanitizeValue()
            .ifKeyContains("endpoint", "connection")
            .ifValueStringMatches(".*://[^/]*:[^/@]+@.*");
}
~~~

Chained fluent filters broaden the set of data to mask: this example masks when the key contains `endpoint`/`connection` or when the value matches the URI pattern. Do not interpret the filter chain as requiring both conditions to be true simultaneously. Nor does a single URI regex cover every credential encoding, query parameter, or connection format; never rely on a single expression as proof that all sensitive URIs are detected.

If a dedicated property source holds secrets, you can inspect `SanitizableData.getPropertySource()` to mask all values from that source. This helps when key names do not follow uniform conventions, provided you verify the actual PropertySource name/type in each environment.

### 4.2. SanitizingFunction Does Not Replace show-values

Even when `show-values` is set to `always` or `when-authorized`, sanitization applied by custom `SanitizingFunction` beans remains in effect. This lets you keep a group of keys permanently masked even when users are authorized to view other configuration values.

Conversely, if a custom function fails to recognize a secret, you cannot assume it will stay masked across all `show-values` configurations. Keep `never` as the default policy and write tests for critical sensitive keys.

### 4.3. API Differences Across Spring Boot Versions

`SanitizingFunction` existed in earlier Spring Boot versions, while fluent helpers such as `ifKeyContains`, `ifKeyMatches`, and `ifLikelyCredential` were added in newer releases, including Spring Boot 3.5.

If your module must support older releases, verify the exact API against your BOM. You can implement the functional interface directly using `SanitizableData.getKey()` and `withSanitizedValue()` if those methods exist in the target version. Do not copy code using newer helpers into an older Spring Boot branch without compiling and testing it.

Example direct implementation without fluent helpers:

~~~java
import java.util.Locale;

import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LegacySanitizationConfiguration {

    @Bean
    SanitizingFunction sensitiveKeysSanitizer() {
        return data -> {
            String key = data.getKey().toLowerCase(Locale.ROOT);
            if (key.contains("client-secret")
                    || key.contains("access-token")
                    || key.endsWith(".password")
                    || key.endsWith(".api-key")) {
                return data.withSanitizedValue();
            }
            return data;
        };
    }
}
~~~

This snippet illustrates `withSanitizedValue()`; verify that the method exists in your target Spring Boot version. Custom `SanitizingFunction` beans are applied in order until one modifies the value, so avoid conflicting rules across multiple functions and test them together as a set.

## 5. Writing Tests for Actuator Sanitization

Do not rely on visually checking a single local response to conclude masking works. Write tests with a fake canary value, then verify the response omits the canary and contains the masked replacement.

Example test configuration:

~~~java
@ConfigurationProperties(prefix = "catalog.client")
public class CatalogClientProperties {

    private String accessToken;

    public String getAccessToken() {
        return accessToken;
    }

    public void setAccessToken(String accessToken) {
        this.accessToken = accessToken;
    }
}
~~~

Testing endpoints with `show-values: never`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "catalog.client.access-token=actuator-test-secret-123",
        "management.endpoints.web.exposure.include=env,configprops",
        "management.endpoint.env.show-values=never",
        "management.endpoint.configprops.show-values=never"
})
@AutoConfigureMockMvc
class ActuatorSanitizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void envDoesNotExposeSecretValue() throws Exception {
        mockMvc.perform(get("/actuator/env/catalog.client.access-token"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        not(containsString("actuator-test-secret-123"))))
                .andExpect(content().string(containsString("******")));
    }

    @Test
    void configpropsDoesNotExposeSecretValue() throws Exception {
        mockMvc.perform(get("/actuator/configprops"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        not(containsString("actuator-test-secret-123"))));
    }
}
~~~

This test assumes `CatalogClientProperties` is registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. If filtering `configprops` by prefix, adjust the URL and JSON assertions according to your Spring Boot version. You do not need to assert the entire response; what matters is that the canary secret never appears.

### 5.1. Testing Roles for when-authorized

With `show-values: when-authorized`, test at least three cases:

| Caller | Expected Outcome |
| --- | --- |
| Unauthenticated | Blocked by Security according to policy |
| Authenticated but missing `CONFIG_AUDITOR` role | Endpoint may return metadata, yet secret values remain masked |
| Authenticated with `CONFIG_AUDITOR` role | Can view values per policy unless a SanitizingFunction applies |

Tests must cover both endpoint authorization and `show-values`. Testing only an authorized user risks overlooking that regular authenticated users can also view secrets.

## 6. Application Logs Do Not Use Actuator Sanitization

This is the most critical boundary of this lesson. `SanitizingFunction` only processes data passed through the sanitizer by supported Actuator endpoints. It does not run on calls such as:

~~~java
log.info("Catalog configuration: {}", catalogClientProperties);
log.debug("Resolved environment: {}", environment);
log.error("Catalog request failed: {}", exception.getMessage());
~~~

Lines like these can leak secrets if `toString()` includes credential fields, if an object dumps the entire Environment, or if an exception message contains a URL or header with credentials.

Seeing `/actuator/env` return `******` does not mean the same property is masked in logs. If application code logs the raw value, log appenders receive the raw value.

### 6.1. Never Log Secrets in the First Place

The best approach is never putting secrets into log messages. Instead of logging tokens or passwords, log configuration state and non-sensitive diagnostics:

~~~java
log.info(
        "Catalog client initialized: credentialConfigured={}, timeoutMs={}",
        hasAccessToken,
        properties.getConnectTimeout().toMillis());
~~~

This example provides operational signals without logging the token. If you need to identify active configuration, log property names, profiles, configuration source names, or a non-sensitive configuration ID. Do not log weak hashes of secrets as a workaround if those hashes could be used to guess or correlate credentials.

### 6.2. Data That Should Never Be Logged

Avoid directly logging:

- `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`.
- Access tokens, refresh tokens, API keys, client secrets, and passwords.
- The entire `Environment`, `PropertySource`, or `@ConfigurationProperties` objects containing secret fields.
- HTTP request/response bodies that may contain credentials or personal data.
- URLs with userinfo or query parameters carrying keys/tokens.
- Full environment variables of the process/container.
- Secrets inside MDC, tracing baggage, or structured log key/value pairs.
- Unchecked exception messages when they might contain URLs, headers, or sensitive payloads.

Be especially careful with HTTP wiretap and request/response logging filters. Debug modes can log all headers and bodies; if enabled temporarily, strictly limit the environment, duration, endpoints, and captured data.

### 6.3. Watch Out for toString() on Configuration Beans

Libraries that auto-generate `toString()` can include every field in logs. For example, Lombok `@Data` or `@ToString` may include an access token field unless excluded.

If using Lombok, exclude secrets from `toString()`:

~~~java
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class CatalogCredentials {

    private String clientId;

    @ToString.Exclude
    private String clientSecret;
}
~~~

For hand-written classes, build a `toString()` containing only safe fields or omit overriding it if unnecessary. Do not log configuration objects as a shortcut to inspect all settings.

### 6.4. Handling Exceptions and URLs

An exception thrown by an HTTP client can include the full URI or part of the request. If the URI contains userinfo or a token in the query string, logging the stack trace or message can leak the secret.

Prefer logging:

- Exception type.
- Error code or HTTP status.
- Route template instead of the full URL.
- Correlation ID or trace ID without credentials.
- Dependency name or service ID if permitted.

If stack traces must be recorded for diagnostics, ensure exceptions strip credentials from URLs/headers/bodies before logging. Never log `exception.getMessage()` unconditionally.

## 7. Structured Logging and Pipeline Redaction

Structured logging enables log collectors to process individual fields instead of parsing free-form strings. Spring Boot supports JSON formats such as ECS, GELF, and Logstash in versions featuring structured logging.

Example enabling Logstash JSON:

~~~yaml
logging:
  structured:
    format:
      console: logstash
      file: logstash
~~~

If the application emits structured fields into JSON, specific paths can be excluded with `logging.structured.json.exclude`:

~~~yaml
logging:
  structured:
    json:
      exclude:
        - http.request.headers.authorization
        - http.request.headers.cookie
        - request.query.access_token
~~~

Path names must match the actual fields written into JSON. The example above only works if those fields exist in the structured log. It does not automatically search for and mask tokens embedded inside the `message` string.

### 7.1. Excluding a Field Is Not Masking Substrings

`logging.structured.json.exclude` removes members by path. If a message already contains a token such as:

~~~text
Calling partner with access token abc123...
~~~

then excluding a header field does not remove the token from that message string. Fix the code generating the log message or apply an appropriate customizer/formatter for your active format.

Spring Boot provides `StructuredLoggingJsonMembersCustomizer` for advanced JSON customization. With Logback or Log4j2, you can also configure framework encoders/layouts/filters. Always inspect the final output after all formatting stages; do not assume one exclude setting covers every log destination.

### 7.2. Defense in Depth at the Log Collection Pipeline

Outside the application, the log collection pipeline can apply an extra redaction layer prior to storage or display. This layer helps when a third-party library inadvertently logs sensitive data.

However, post-collection redaction is only a supplementary layer. Secrets may already have passed through stdout, agents, buffers, queues, or intermediate stores before being masked. Minimize sensitive data at the source and restrict log read permissions, retention periods, download rights, and query access.

### 7.3. Avoid Untested Regex Redaction

A regex filter can miss encoded tokens, nested JSON, URL encoding, or format changes. Overly broad regexes can erase useful diagnostic data; overly narrow regexes can let secrets slip through.

Prefer explicit field structures and allowlists of permitted log data. If regex redaction is unavoidable, test it against realistic payload variants and inspect logs after passing through both encoders and pipelines.

## 8. Safely Logging HTTP Requests

In Spring Cloud applications, inter-service requests frequently carry authentication headers. When logging requests, pick fields using an allowlist:

~~~java
log.info(
        "Outbound request: dependency={}, method={}, route={}, status={}, traceId={}",
        "catalog-service",
        method,
        "/api/catalog/{id}",
        statusCode,
        traceId);
~~~

Never log the full header map. If certain technical headers are needed, explicitly select safe ones such as `Content-Type` or a controlled correlation ID.

For inbound requests, log the route template instead of raw URLs if query strings might hold sensitive data. Do not log bodies by default; log only approved fields stripped of personal data and secrets.

### 8.1. Do Not Put Secrets in MDC or Tracing Baggage

MDC and tracing baggage are frequently copied into structured logs or trace exporters. Therefore:

- Place only approved correlation IDs, request IDs, and actor IDs in MDC.
- Never place Authorization headers, session tokens, or client secrets in MDC.
- Never place passwords or sensitive data in span attributes.
- Audit trace export configurations and observability platform access permissions.
- Use pseudonymous identifiers when direct identifiers are unnecessary.

If a value is considered secret in a log message, it is equally secret when added to MDC or tracing baggage.

## 9. Testing to Ensure Logs Do Not Contain Secrets

A straightforward test can use Spring Boot's `OutputCaptureExtension` to capture logs emitted during tests and verify that a canary secret never appears.

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class CatalogLoggingSecurityTest {

    @Test
    void startupLogDoesNotContainClientSecret(CapturedOutput output) {
        String fakeSecret = "log-test-secret-456";

        CatalogStartupLogger logger =
                new CatalogStartupLogger(fakeSecret);

        logger.logConfigurationSummary();

        assertThat(output.getOut())
                .doesNotContain(fakeSecret);
        assertThat(output.getErr())
                .doesNotContain(fakeSecret);
    }
}
~~~

`CatalogStartupLogger` is an illustrative class to be replaced with the actual component emitting logs in your application. Tests must exercise the exact code path under protection; merely constructing a string without triggering the logger proves nothing.

### 9.1. Testing Both Messages and Exceptions

Include scenarios covering:

- Startup logs when credentials are configured.
- HTTP request logs containing Authorization/Cookie headers.
- Exceptions from HTTP clients containing URIs or query parameters.
- Debug logs when wiretap is enabled.
- MDC/tracing baggage propagated into structured logs.
- Logs on retry, timeout, and circuit breaker branches.
- Logs during configuration refresh or bean recreation.

Search for the canary secret across stdout, stderr, and file appenders. If the application ships logs to an agent or centralized store, inspect the final record after pipeline processing.

### 9.2. Testing Endpoint Sanitization

For `env` and `configprops`, verify responses do not contain the canary secret under both `never` and `when-authorized` for users lacking the required role. When a custom `SanitizingFunction` is present, verify application-specific keys are also masked.

Do not use a passing Actuator test to infer that logs are safe. The two data paths require separate test suites.

## 10. Incident Response When a Secret Appears in Logs

If a secret has already appeared in endpoints or logs:

1. Identify the credential type and which systems it grants access to.
2. Revoke or rotate the credential following the provider's procedure.
3. Determine every stdout stream, file, agent, queue, central store, replica, and backup where the log appeared.
4. Restrict read and download permissions on the affected records.
5. Delete or remediate the data in accordance with retention, legal, and audit requirements.
6. Fix the root cause: property naming/sanitization, logger, request filter, exception, or MDC.
7. Add regression tests using canary values.
8. Check whether any other systems accept the same credential.

Deleting logs in only one location does not guarantee the secret is gone from replicas or downstream systems. Assess the propagation blast radius before closing the incident.

## 11. Common Mistakes and How to Avoid Them

1. **Assuming Actuator masks logs too:** `SanitizingFunction` does not filter SLF4J, Logback, or Log4j2.
2. **Enabling `show-values: always` for debugging:** keep `never` or use `when-authorized` with a narrow role.
3. **Omitting `roles` when using `when-authorized`:** all authenticated HTTP users can view raw values by default.
4. **Forgetting JMX:** JMX is treated as authorized under `when-authorized`; secure the MBean server independently.
5. **Protecting endpoints with authentication alone:** you must also limit exposure and value visibility.
6. **Relying on default key rules to catch all secrets:** add custom naming conventions and test internal keys.
7. **Treating a custom sanitizer as a log filter:** it applies only to corresponding Actuator data.
8. **Logging entire configuration beans:** `toString()` can print passwords or tokens to logs.
9. **Logging all HTTP headers/bodies:** log only an allowlist of required fields.
10. **Logging unchecked exception messages:** messages can include URLs, credentials, or payloads.
11. **Putting tokens in MDC/tracing baggage:** those fields can be exported to multiple external systems.
12. **Relying solely on redaction at the log collector:** secrets already passed through buffers or intermediate systems before masking.
13. **Using untested regexes:** they can miss formats or strip needed data.
14. **Skipping checks on file appenders and centralized logs:** clean stdout does not prove every destination is safe.

## 12. Coordinated Protection Rollout Checklist

When configuring a Spring Cloud application:

1. Inventory passwords, tokens, API keys, client secrets, private keys, cookies, and connection strings.
2. Supply secrets from a secret manager or controlled source; never commit real values.
3. Keep `management.endpoint.env.show-values` and `management.endpoint.configprops.show-values` at `never` by default.
4. Use `when-authorized` only when clearly required; declare specific roles and configure Security filter chains.
5. Control JMX independently of HTTP.
6. Add `SanitizingFunction` for custom keys or sources.
7. Never log raw Environment, ConfigurationProperties, headers, bodies, credential-bearing URLs, or unchecked exception messages.
8. Design logs around allowlists and structured fields.
9. Add encoder/pipeline redaction as defense in depth.
10. Write canary tests for Actuator responses and log output.
11. Inspect stdout, files, agents, queues, log stores, and trace exporters.
12. Rotate secrets immediately if exposure is detected.

**Key Takeaway:** Spring Boot Actuator's `env` and `configprops` mask values by default; `show-values` and `SanitizingFunction` govern how these endpoints display data. Application logging is an independent surface: the safest approach is avoiding logging secrets altogether, logging only approved fields, controlling headers/bodies/exceptions/MDC, and testing output across every destination. Protecting configuration, management endpoints, and logs together reduces credential exposure risks in **SPRING_CLOUD_CORE**.

## References

- [Spring Boot — Actuator Endpoints: Sanitize Sensitive Values](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Customizing Sanitization](https://docs.spring.io/spring-boot/how-to/actuator.html)
- [Spring Boot API — SanitizingFunction](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/endpoint/SanitizingFunction.html)
- [Spring Boot — Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
