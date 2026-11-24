# Recording Effective Configuration and Verifying the Specification After Startup

An `application.yml` file containing the expected value does not prove the application is running with that value. Spring Boot can load configuration from packaged files, external files, profiles, environment variables, system properties, `SPRING_APPLICATION_JSON`, and command-line arguments. A higher-priority source can override values in the file a developer is inspecting.

With `springdoc-openapi`, configuration drift can disable documentation endpoints, alter URLs, omit operations, or generate an unexpected specification. You should inspect the effective configuration after application startup, identify the source supplying each value, and compare it against the live OpenAPI JSON/YAML and Swagger UI.

## 1. Distinguishing Declared Configuration from Effective Configuration

Suppose `application-prod.yml` declares:

```yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: false
```

However, the production container defines environment variables:

```bash
SPRINGDOC_API_DOCS_ENABLED=false
SPRINGDOC_API_DOCS_PATH=/internal/openapi
```

The application may run with `springdoc.api-docs.enabled=false` and path `/internal/openapi`, even though the YAML file says `true` and `/v3/api-docs`. When the endpoint does not appear, reading the YAML file alone will not reveal the overriding source.

Distinguish three concepts:

| Concept | Meaning | How to Inspect |
| --- | --- | --- |
| Declared value | Value written in a specific file or configuration source | Read the file, environment variables, or startup arguments. |
| Effective value | Value resolved by Spring `Environment` after merging sources | Actuator `env` or `Environment` inside the application. |
| Bound value | Value bound to a `@ConfigurationProperties` bean | Actuator `configprops`. |

Effective and bound values are usually identical, yet the two views uncover different issues. `env` helps locate the property source and origin; `configprops` shows whether the setting successfully bound to the configuration object.

## 2. Adding Spring Boot Actuator

The `env`, `configprops`, and `conditions` endpoints belong to Spring Boot Actuator. Add the dependency if the application does not already include it:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

By default, only the `health` endpoint is exposed over HTTP. To use configuration-diagnostic endpoints, expose them explicitly. Example configuration for an internal test environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,env,configprops,conditions"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Common endpoint URLs:

| Endpoint | Primary Information | Helps Answer |
| --- | --- | --- |
| `/actuator/env` | Property sources in Spring `Environment` | Which source did a property come from? |
| `/actuator/env/{property}` | Details for a specific property | What is the effective value and origin of this property? |
| `/actuator/configprops` | Bound `@ConfigurationProperties` beans | Was configuration bound to the bean, and what values are active? |
| `/actuator/conditions` | Auto-configuration condition outcomes | Why was an auto-configuration enabled or disabled? |
| `/actuator/mappings` | Registered request mappings | Does the documentation endpoint have a mapping in the application? |

The `mappings` endpoint is helpful for confirming live paths, though it is not dedicated to inspecting OpenAPI content. Expose it only when there is a specific diagnostic need.

## 3. Exposing an Endpoint Does Not Mean Allowing Public Access

Actuator separates whether an endpoint is enabled, exposed, and authorized. An endpoint is usable only when it is enabled, exposed over HTTP/JMX, and the request passes security rules.

In the example above, `include` only selects which endpoints are published. If the application uses Spring Security, protect diagnostic endpoints with operational roles or restrict access to an administrative network. Never open `env` and `configprops` to the internet merely for convenience.

`env` and `configprops` responses can expose property names, configuration structure, file paths, service hosts, or sensitive information. Current Spring Boot releases sanitize sensitive values on these endpoints by default. Even so, do not rely on sanitization as the sole defense; restrict exposure and authenticate callers.

If authorized personnel need to view unsanitized values, you can configure role-based visibility in Spring Boot versions supporting `show-values`:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: OPS
    configprops:
      show-values: when-authorized
      roles: OPS
```

`when-authorized` reveals unsanitized values only to authenticated callers holding the specified role. A custom `SanitizingFunction` may still mask values. In environments where viewing values is unnecessary, keep `show-values: never`. Check the documentation for your exact Spring Boot version because Actuator capabilities and property names can vary across versions.

## 4. Using `/actuator/env` to Find Overriding Sources

When a property lacks the expected value, query that specific property rather than reading all of `env`:

```bash
curl -u ops https://service.example.com/actuator/env/springdoc.api-docs.enabled
curl -u ops https://service.example.com/actuator/env/springdoc.api-docs.path
curl -u ops https://service.example.com/actuator/env/springdoc.swagger-ui.enabled
```

`curl -u ops` prompts interactively for a password in the terminal when none is supplied. Use an authentication mechanism approved by your organization; never record real passwords or tokens in shell-history commands or documentation.

The `env` response typically shows:

- What value the property resolves to, if visibility permissions allow.
- Which property sources contain that property.
- Source names, such as `systemEnvironment`, `systemProperties`, `commandLineArgs`, or Config Data sources.
- Origin or declaration location, such as filename and line number when metadata is available.

Detailed JSON structure can vary by Spring Boot version. Look for the property name, `propertySources`, and origin rather than depending on the exact field order or secondary keys of a sample response.

For example, if `springdoc.api-docs.enabled` originates from `systemEnvironment`, inspect `SPRINGDOC_API_DOCS_ENABLED` in the deployment. If it originates from `commandLineArgs`, inspect `--springdoc.api-docs.enabled=...` in the launch command or container configuration.

`/actuator/env` shows what Spring sees. It does not by itself explain why a specific bean was or was not created; use `configprops` and `conditions` for those questions.

## 5. Using `/actuator/configprops` to Verify Binding

`configprops` displays beans annotated with `@ConfigurationProperties` along with binding details. When investigating springdoc configuration, search for the `springdoc` prefix or relevant property group in the response:

```bash
curl -u ops https://service.example.com/actuator/configprops
```

Verify:

- Does the configuration bean appear?
- Is the prefix correct?
- Do bound properties hold the expected values?
- Does `inputs` or origin metadata (if provided by your version) indicate which input source was used?
- Were any properties ignored due to typos, unconvertible types, or unloaded config?

Not every property necessarily appears in `configprops`: this endpoint focuses on `@ConfigurationProperties` beans, whereas `env` reflects property sources in `Environment`. If a property exists in `env` yet is missing from `configprops`, check whether it belongs to a bound configuration prefix/bean and whether your library version supports that property.

For springdoc, cross-check key properties:

| Property | Effect to Confirm |
| --- | --- |
| `springdoc.api-docs.enabled` | Whether the OpenAPI endpoint is enabled. |
| `springdoc.api-docs.path` | Base path of OpenAPI JSON. |
| `springdoc.api-docs.version` | OpenAPI version written to the document's `openapi` field. |
| `springdoc.packages-to-scan` | Controller packages included in documentation. |
| `springdoc.paths-to-match` | Paths selected for documentation. |
| `springdoc.paths-to-exclude` | Paths excluded from documentation. |
| `springdoc.swagger-ui.enabled` | Whether Swagger UI is enabled. |
| `springdoc.swagger-ui.path` | Entry path to the UI. |

The list of properties depends on the springdoc version. Consult the property reference for the exact branch in use; never assume the latest property exists in an older application.

## 6. Using `/actuator/conditions` to Understand Auto-Configuration

`conditions` shows which auto-configuration conditions matched or did not match. This is useful when:

- A springdoc starter is in dependencies, yet auto-configuration is not triggered.
- The application uses WebFlux, yet loaded the WebMVC starter, or vice versa.
- A custom bean caused default auto-configuration to back off.
- Required classpath, property, or existing-bean conditions were not met.

Query the endpoint:

```bash
curl -u ops https://service.example.com/actuator/conditions
```

Search for entries related to springdoc or OpenAPI under positive matches and negative matches. Auto-configuration class names and report structure vary by version. Read the condition messages to see which conditions succeeded or failed.

`conditions` is neither a list of all effective properties nor proof that the final document is correct. For instance, auto-configuration may match while `paths-to-match` filters out every controller. In that case, inspect `env`, `configprops`, and the OpenAPI document.

## 7. Inspecting Effective Configuration Inside the Application

In code or a temporary diagnostic check, you can read `Environment` to see what values Spring resolved:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class OpenApiConfigurationProbe implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(
        OpenApiConfigurationProbe.class
    );

    private final Environment environment;

    OpenApiConfigurationProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        Boolean apiDocsEnabled = environment.getProperty(
            "springdoc.api-docs.enabled", Boolean.class, true
        );
        String apiDocsPath = environment.getProperty(
            "springdoc.api-docs.path", "/v3/api-docs"
        );
        Boolean swaggerUiEnabled = environment.getProperty(
            "springdoc.swagger-ui.enabled", Boolean.class, true
        );

        log.info("OpenAPI enabled: {}", apiDocsEnabled);
        log.info("OpenAPI path: {}", apiDocsPath);
        log.info("Swagger UI enabled: {}", swaggerUiEnabled);
    }
}
```

This example logs only non-secret flags and paths. Never dump the entire `Environment`, `System.getenv()`, or `configprops` into logs: they can contain credentials, tokens, internal URLs, and infrastructure details. After diagnostics, remove the temporary probe or restrict it to a diagnostic profile.

The default value in `getProperty(..., defaultValue)` is only a fallback for the probe code itself. It does not replace springdoc's true defaults and does not prove the property was bound into a bean. Cross-check with Actuator and the runtime document.

## 8. Verifying OpenAPI Endpoints After Application Startup

Once effective configuration is known, call the live endpoints. Example:

```bash
curl -i https://service.example.com/v3/api-docs
curl -i https://service.example.com/v3/api-docs.yaml
curl -i https://service.example.com/v3/api-docs/swagger-config
```

If `springdoc.api-docs.path` was changed, substitute the effective path in the URLs. If the application has a context path, management port, or reverse proxy prefix, use the URL clients actually call.

Cross-check responses:

| Effective Configuration | Result to Verify |
| --- | --- |
| `springdoc.api-docs.enabled=true` | OpenAPI endpoint is registered and can return the document unless blocked by security/proxy. |
| `springdoc.api-docs.enabled=false` | OpenAPI endpoint is not served under springdoc configuration; inspect live status and mappings. |
| `springdoc.api-docs.path=/internal/openapi` | JSON document is at the configured base path; YAML and Swagger UI config URLs match the base path/version. |
| `springdoc.api-docs.version` | The `openapi` field in JSON reflects the configured and supported specification version. |
| `springdoc.packages-to-scan` | Operations come only from selected packages. |
| `springdoc.paths-to-match` / `paths-to-exclude` | Paths appear/disappear as filtered. |
| `springdoc.swagger-ui.enabled=false` | Swagger UI is disabled, while OpenAPI JSON may remain active. |

Do not conclude an endpoint is disabled solely from a `401`, `403`, or `404` response. `401`/`403` usually indicates the request is protected; `404` can result from a wrong path, proxy rewrite, or an unregistered endpoint. Combine `env`, `conditions`, `mappings`, and startup logs to pinpoint the cause.

## 9. Verifying OpenAPI Document Content

When the document returns `200`, verify its contents instead of stopping at HTTP status. A basic checklist:

1. `openapi`: OpenAPI version matches `springdoc.api-docs.version` and library version.
2. `info`: title, version, and description match the environment or group.
3. `servers`: public scheme, host, port, and prefix match what clients will call.
4. `paths`: intended operations are present; internal or excluded operations do not appear unexpectedly.
5. `components.schemas`: DTOs, enums, formats, and validation metadata are accurate.
6. `components.securitySchemes` and `security`: schemes and security requirements match the contract.
7. `requestBody`, `parameters`, `responses`: media types, required flags, status codes, headers, and schemas are accurate.
8. `$ref`: every reference points to an existing component.

Abbreviated example:

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Store API",
    "version": "1.0.0"
  },
  "servers": [
    { "url": "https://api.example.com/store" }
  ],
  "paths": {
    "/api/orders": {
      "get": {
        "operationId": "listOrders",
        "responses": {
          "200": { "description": "OK" }
        }
      }
    }
  }
}
```

This is a structural reference example, not a fixed document for every application. The `openapi` value and schema generation depend on configuration and springdoc version. Inspect your service's actual response.

## 10. Distinguishing Configuration Errors, Auto-Configuration Errors, and Documentation Errors

Some symptoms look alike yet require checking different places:

| Symptom | Where to Check First | Possible Cause |
| --- | --- | --- |
| Property in YAML is right yet endpoint remains off | `/actuator/env/{property}` | Overridden by environment variable, system property, or command line. |
| Property appears in `env` yet bean ignores it | `/actuator/configprops` | Misbound, wrong prefix, or property does not belong to that config bean. |
| Springdoc auto-configuration does not appear | `/actuator/conditions` | Missing starter, wrong web stack, or unmet classpath/bean condition. |
| `/v3/api-docs` returns `404` yet `api-docs.enabled=true` | `/actuator/env`, `/actuator/mappings`, proxy | Custom path, context path, security, or wrong rewrite. |
| `/v3/api-docs` returns `200` yet misses controllers | `paths`, `packages-to-scan`, `paths-to-match` | Filter excluded endpoints or controller was not discovered. |
| JSON has operations yet Swagger UI fails to open | `swagger-config`, UI path, Network tab | UI disabled, wrong config URL, broken assets, or blocked by security. |
| Document still matches previous release after code edit | Startup logs, process/instance, cache | Calling wrong instance, stale artifact, or OpenAPI cache. |
| `servers` shows internal host or wrong prefix | `servers`, forwarded headers, proxy config | Application did not receive public URL metadata. |
| Security scheme is right yet requests are rejected | Spring Security runtime | Wrong token, role, issuer, audience, or runtime rule. |

## 11. Notes on Caching and Post-Startup Changes

Springdoc may cache the computed OpenAPI document to reduce specification-generation overhead. If the same process keeps returning an old document after changing mappings, annotations, or configuration data, check:

- Whether requests are hitting the right newly deployed instance and artifact.
- Whether the instance's profile and property sources actually changed.
- Whether caching exists at springdoc, reverse proxy, gateway, or CDN layers.
- Whether the application needs a restart to load startup-time configuration.

The `springdoc.cache.disabled` property can disable document caching in supported versions, yet it should not be used as a production configuration-refresh mechanism. Editing `application.yml`, environment variables, or most startup settings does not automatically update every running bean. If your system uses Spring Cloud Config/refresh or a custom reload mechanism, verify whether that property is refreshed and whether the consuming bean supports refresh.

After changing startup-time configuration, the reliable verification path is typically redeploying/restarting the instance with the new configuration, waiting for readiness, and re-querying the documentation endpoints via the actual public address.

## 12. Post-Startup Verification Workflow

Follow this sequence to gather evidence from configuration to the live document:

1. **Verify the instance:** check version/build info, pod/container, or hostname to be certain you are hitting the intended instance.
2. **Verify the profile:** check startup logs or `SPRING_PROFILES_ACTIVE` in deployment config.
3. **Inspect Environment:** call `/actuator/env/{property}` for critical springdoc properties and record property sources/origins without saving secrets.
4. **Verify binding:** call `/actuator/configprops` and confirm configuration beans received the expected values.
5. **Inspect conditions:** use `/actuator/conditions` if you suspect springdoc auto-configuration did not activate.
6. **Inspect mappings:** use `/actuator/mappings` or startup logs to confirm OpenAPI and Swagger UI URLs were registered.
7. **Fetch documents:** call JSON/YAML at the effective path and verify HTTP status and content type.
8. **Cross-check content:** verify `openapi`, `servers`, `paths`, schemas, security, and responses.
9. **Verify UI:** call `swagger-config`, open Swagger UI, and confirm it loads the right document.
10. **Record evidence:** note the profile, build version, non-sensitive property sources, tested endpoints, and comparison results.

You do not need to expose all of Actuator for this workflow. Enable only the required endpoints in diagnostic environments, protect them, and disable or tighten exposure afterward if required by operational policy.

## 13. Automated Checks in CI or Smoke Tests

You can test the OpenAPI document using MockMvc inside a test context:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiStartupContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesExpectedOrdersOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$['paths']['/api/orders']['get']").exists());
    }
}
```

This test verifies the document inside the Spring test context. It does not verify production container environment variables, proxies, security, or public URLs. Therefore, post-deployment HTTP smoke tests from an environment close to real clients are still required.

A smoke test example can check status and key fields:

```bash
curl -fsS https://service.example.com/v3/api-docs -o openapi.json
```

Then run a JSON parser or OpenAPI validator in the pipeline to verify `openapi`, required paths, response schemas, and `$ref`. Avoid comparing the entire JSON purely as a raw string because field ordering or component names can vary across library versions.

## 14. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Cannot access `/actuator/env` | Actuator not added, endpoint unexposed, or blocked by security | Check dependencies, `management.endpoints.web.exposure.include`, and permissions. |
| `/actuator/env` returns `******` | Sanitization masks sensitive values | Check property source/origin; grant value visibility to ops roles only if truly needed. |
| Property missing from `configprops` | Property does not belong to a `@ConfigurationProperties` bean or did not bind | Use `env` to check property source and verify prefix/binding. |
| `/actuator/conditions` lacks expected details | Hitting wrong instance, endpoint unexposed, or report format varies by version | Confirm instance, exposure, and version-specific auto-configuration names. |
| OpenAPI path differs from config file | Higher-priority source overrides path | Query `/actuator/env/springdoc.api-docs.path` and inspect origin. |
| Docs endpoint returns `404` despite enabled=true | Wrong path, proxy rewrite, context path, or auto-configuration created no mapping | Check `configprops`, `conditions`, `mappings`, and public URL. |
| OpenAPI misses operations | Package/path filters or controller not registered | Cross-check `packages-to-scan`, `paths-to-match`, `paths-to-exclude`, and mappings. |
| Swagger UI is off yet JSON still works | The two enable properties are independent | Inspect `springdoc.swagger-ui.enabled` and `springdoc.api-docs.enabled` separately. |
| Stale document after deployment | Wrong instance, stale artifact, or cache | Check build/version, restart, and springdoc/proxy caches. |
| Actuator leaks configuration details | Overly broad exposure or missing security | Narrow exposure, protect endpoints, and preserve sanitization. |

## 15. Operational Principles

- Distinguish declared file values, effective values in `Environment`, and values bound into beans.
- Use `/actuator/env/{property}` to locate sources and origins of critical properties.
- Use `/actuator/configprops` to confirm typed configuration binding.
- Use `/actuator/conditions` to diagnose auto-configuration; do not treat it as a substitute for inspecting properties or documents.
- Expose only needed Actuator endpoints; protect them with administrative networks and Spring Security.
- Keep `show-values: never` unless inspecting values is necessary; never log secrets.
- Cross-check springdoc properties against live JSON/YAML URLs, Swagger UI, and OpenAPI content after startup.
- Verify `servers`, `paths`, schemas, security, responses, and `$ref`, not just HTTP `200`.
- Confirm the right instance/artifact and inspect caches before concluding the document failed to update.
- Use test contexts in CI and smoke tests post-deployment because the two environments do not share the same configuration sources.

Recording effective configuration explains why a running application behaves differently from a committed config file. `env` identifies sources and origins, `configprops` confirms binding, and `conditions` explains auto-configuration decisions. Next, fetching OpenAPI JSON/YAML and verifying `servers`, `paths`, schemas, security, and Swagger UI confirms the configuration produced the intended contract. Combining controlled Actuator inspection with post-startup smoke tests catches mismatches between deployment configuration and live API documentation early.

## References

- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot – Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Springdoc OpenAPI – Core Configuration Properties](https://springdoc.org/core-properties.html)
- [Springdoc OpenAPI – Configuration Properties](https://springdoc.org/properties.html)
