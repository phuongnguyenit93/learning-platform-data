# Property to Enable or Disable the Specification Endpoint

Springdoc automatically creates HTTP endpoints to serve the OpenAPI document from the Spring Boot application's controllers, request mappings, and Swagger annotations. The `springdoc.api-docs.enabled` property controls whether Springdoc publishes these specification endpoints. The default value is `true`; set it to `false` to disable the API Docs endpoints in environments where documentation should not be published.

This is an application-level setting, typically placed in `application.yml`, `application.properties`, a profile-specific configuration file, or an environment variable. Distinguish it from `springdoc.swagger-ui.enabled`, which controls the Swagger UI interface. API Docs and the UI are two parts that can be enabled or disabled independently.

## 1. What Does `springdoc.api-docs.enabled` Do?

The property is a Boolean:

| Value | Behavior |
|---|---|
| `true` | Springdoc enables the OpenAPI endpoints according to the current configuration. This is the default value. |
| `false` | Springdoc disables the API Docs endpoints it provides. |

YAML example:

```yaml
springdoc:
  api-docs:
    enabled: false
```

`application.properties` example:

```properties
springdoc.api-docs.enabled=false
```

This property controls the documentation endpoints on the Springdoc side. It does not alter business mappings such as `/api/orders`, does not remove controllers, does not modify OpenAPI annotations, and does not change API authorization rules.

Springdoc v2 documents the default value `true` in its configuration properties table, and the official FAQ instructs using `springdoc.api-docs.enabled=false` to disable `/v3/api-docs` and related specification endpoints. <https://springdoc.org/v2/core-properties.html>

## 2. Which Endpoints Are Affected?

With default configuration, the application typically serves the following URLs:

| Endpoint | Purpose |
|---|---|
| `/v3/api-docs` | OpenAPI document in JSON format |
| `/v3/api-docs.yaml` | OpenAPI document in YAML format |
| `/v3/api-docs/{group}` | OpenAPI document for a `GroupedOpenApi` |
| `/v3/api-docs/swagger-config` | Configuration used by Swagger UI to locate documents |

When `springdoc.api-docs.enabled=false`, the API Docs endpoints registered by Springdoc are no longer served under the standard configuration. If you changed `springdoc.api-docs.path`, check the custom path instead of only calling `/v3/api-docs`.

Example when the path is changed:

```yaml
springdoc:
  api-docs:
    path: /openapi
    enabled: true
```

The corresponding URLs are typically:

```text
/openapi
/openapi.yaml
/openapi/{group}
/openapi/swagger-config
```

`springdoc.api-docs.path` only changes the base path; it does not enable or disable the endpoints. If you want to disable the endpoints, use `enabled: false`.

## 3. Explicitly Enabling the Specification Endpoint

In local environments or integration tests, you can explicitly declare the endpoint as enabled:

```yaml
springdoc:
  api-docs:
    enabled: true
```

After the application starts, fetch the JSON:

```bash
curl -i http://localhost:8080/v3/api-docs
```

Or fetch the YAML:

```bash
curl -i http://localhost:8080/v3/api-docs.yaml
```

A valid JSON response typically contains `openapi`, `info`, and `paths` fields. Example beginning of a document:

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Order API",
    "version": "1.0.0"
  },
  "paths": {
    "/api/orders": {
      "get": {
        "summary": "List orders"
      }
    }
  }
}
```

The actual OpenAPI version and content depend on configuration, annotations, and endpoints discovered by Springdoc. The JSON snippet only illustrates the structure.

## 4. Disabling the Specification Endpoint

To disable API Docs in an environment, set:

```yaml
springdoc:
  api-docs:
    enabled: false
```

After restarting the application, verify the configured URLs:

```bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
curl -i http://localhost:8080/v3/api-docs/swagger-config
```

The endpoints are no longer served by Springdoc. Typically, requests receive 404 if no other route handles the same path. If Spring Security, a gateway, or a reverse proxy intercepts the request first, the status may be 401, 403, or another response. Therefore, inspect the status, response body, and which layer is returning the response.

Disabling the endpoint does not remove metadata from the source code. Annotations such as `@Operation`, `@Schema`, and `@ApiResponse` can remain intact to re-enable documentation in another environment or for use in a build step that generates artifacts.

## 5. Distinguishing API Docs from Swagger UI

Springdoc has two independent properties:

```yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
```

| `api-docs.enabled` | `swagger-ui.enabled` | Expected Result |
|---:|---:|---|
| `true` | `true` | Both OpenAPI JSON/YAML and Swagger UI are available |
| `true` | `false` | API Docs available, no Swagger UI interface |
| `false` | `true` | Springdoc API Docs disabled; UI entry/resources may still be enabled, but cannot load the default document from the disabled swagger-config/API Docs |
| `false` | `false` | Both API Docs and Swagger UI provided by Springdoc are disabled |

If `api-docs.enabled=false` while Swagger UI remains enabled, the default UI cannot retrieve the OpenAPI document from the disabled Springdoc endpoint. Configuring the UI to display a static OpenAPI file or an external document is an advanced setup; you must configure the document source and verify `swagger-config` and the source URL for your Springdoc version.

If you only want to provide JSON/YAML for a pipeline without Swagger UI, you can use the corresponding API-only starter. With Spring MVC and Springdoc v2, the artifact typically used is:

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>${springdoc.version}</version>
</dependency>
```

For WebFlux applications, choose `springdoc-openapi-starter-webflux-api`. If you also want the UI, use the `*-ui` starter appropriate for your stack. The chosen dependency determines which components are included in the application; `api-docs.enabled` remains the configuration toggle for the specification endpoints.

## 6. Setting Values by Spring Profile

Typically, local and test need API Docs, while production may disable direct publication of the endpoints.

`application.yml`:

```yaml
springdoc:
  api-docs:
    enabled: true
```

`application-prod.yml`:

```yaml
springdoc:
  api-docs:
    enabled: false
```

Run production with the `prod` profile:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Or use an environment variable:

```bash
SPRING_PROFILES_ACTIVE=prod
```

When the `prod` profile is active, `false` in `application-prod.yml` overrides the default `true` from `application.yml`. If the `prod` profile is not activated, the default configuration keeps API Docs enabled.

Another configuration is enabling API Docs in staging while disabling it in production:

```yaml
# application-staging.yml
springdoc:
  api-docs:
    enabled: true
```

```yaml
# application-prod.yml
springdoc:
  api-docs:
    enabled: false
```

Staging may be used by QA, partners, or contract test pipelines. If the documentation is meant only for authorized users, still protect the endpoint using Spring Security or a gateway.

## 7. Controlling via Environment Variable or Command Line

Spring Boot relaxed binding maps the property:

```text
springdoc.api-docs.enabled
```

to the environment variable:

```text
SPRINGDOC_API_DOCS_ENABLED
```

Linux/container example:

```bash
SPRINGDOC_API_DOCS_ENABLED=false java -jar app.jar
```

Docker Compose example:

```yaml
services:
  orders-api:
    image: example/orders-api:latest
    environment:
      SPRINGDOC_API_DOCS_ENABLED: "false"
```

PowerShell example:

```powershell
$env:SPRINGDOC_API_DOCS_ENABLED = "false"
java -jar app.jar
```

You can pass it via the command line:

```bash
java -jar app.jar --springdoc.api-docs.enabled=false
```

Environment variables or command-line arguments can override values in YAML according to Spring Boot's property source precedence order. If the production file sets `false` yet the endpoint remains active, check environment variables, command line, config server, and active profiles.

## 8. Changing the Path Is Not the Same as Disabling the Endpoint

The following two configurations have different meanings:

```yaml
springdoc:
  api-docs:
    path: /internal/openapi
    enabled: true
```

The endpoint remains enabled, only moved from `/v3/api-docs` to `/internal/openapi`.

```yaml
springdoc:
  api-docs:
    path: /internal/openapi
    enabled: false
```

The API Docs endpoint is disabled; changing the path does not make the endpoint reappear.

Do not rely on a hard-to-guess path as a security measure. URLs can appear in logs, frontend configs, browser history, or integration docs. If documentation needs protection, use authentication/authorization and appropriate network policies.

## 9. Distinguishing Disabling the Endpoint, Filtering Operations, and Hiding Operations

The configurations below address different needs:

| Mechanism | Effect | Does the API Docs Endpoint Still Exist? |
|---|---|---:|
| `springdoc.api-docs.enabled=false` | Disables the documentation endpoints provided by Springdoc | No, under standard Springdoc configuration |
| `springdoc.paths-to-match` | Includes only paths matching the condition in the document | Yes |
| `springdoc.packages-to-scan` | Scans controllers only in selected packages | Yes |
| `@Hidden` | Hides an operation or controller from the document | Yes |
| Spring Security `denyAll()` | Denies requests to the endpoint via authorization rules | Yes, but inaccessible through the security chain |
| `springdoc.api-docs.path` | Changes the documentation endpoint URL | Yes |

If you only want to exclude an administrative controller from public documentation, you do not need to disable all API Docs. Use `@Hidden`, package/path filters, or a targeted `GroupedOpenApi`. If you want the documentation endpoint not to be published in a given environment, use `api-docs.enabled=false`.

Path filtering example:

```yaml
springdoc:
  paths-to-match:
    - /api/public/**
```

Controller hiding example:

```java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Hidden
@RestController
@RequestMapping("/api/internal")
class InternalController {
}
```

In both examples, the `/v3/api-docs` endpoint can still return a document, but without the filtered or hidden operations.

## 10. Disabling API Docs Does Not Protect Business APIs

`springdoc.api-docs.enabled=false` is not a substitute for Spring Security. It does not automatically require login for `/api/admin/**`, nor does it stop clients from calling controllers if business routes remain permitted.

Examples:

- `/v3/api-docs` is disabled, yet `/api/orders` still returns data under the current authorization rules.
- `/v3/api-docs` remains enabled, while Spring Security restricts who can download the documentation.
- Swagger UI is disabled, yet JSON/YAML can still be downloaded if API Docs is enabled.

If you want the API Docs endpoint to remain available only to a specific group of users, protect the documentation paths with Spring Security:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DocumentationSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/v3/api-docs/**").hasAuthority("DOCS_READ")
                .anyRequest().authenticated()
            )
            .build();
    }
}
```

This is a different choice from disabling the endpoint. The rule must match `springdoc.api-docs.path` if the path was customized. If multiple `SecurityFilterChain` beans exist, check the matchers and chain order to ensure documentation requests pass through the intended policy.

## 11. Impact on Swagger UI and Static Documentation

By default, Swagger UI retrieves configuration from the `swagger-config` endpoint and then loads OpenAPI JSON/YAML. When API Docs is disabled, the default config URL or document is no longer served under standard settings. Consequently, the UI may open but show a definition-loading error.

If you want the UI to read a static file or external URL while Springdoc API Docs is disabled, verify the dedicated configuration for your Springdoc version. The Springdoc FAQ includes an advanced guide for using a standalone spec file: when `springdoc.api-docs.enabled` is disabled, standard auto-configuration is affected and minimal related beans must be configured before pointing Swagger UI to the spec file. Do not assume that adding `springdoc.swagger-ui.url` alone suffices in every version.

If the goal is only to hide the UI while keeping the document for pipelines, use:

```yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: true
```

If the goal is to disable both documentation and UI:

```yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: false
```

## 12. Impact on Builds and Documentation-Generation Pipelines

Some pipelines start the application and call `/v3/api-docs` to save OpenAPI JSON/YAML as an artifact, run contract checks, or generate SDKs. If the profile used in that step sets `springdoc.api-docs.enabled=false`, the fetch command will fail because the endpoint is not served.

You can separate profiles:

```yaml
# application-openapi-build.yml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
```

The pipeline activates the `openapi-build` profile, downloads the document, and saves it as an artifact. Production uses a separate profile with `api-docs.enabled=false`.

Example:

```bash
java -jar app.jar --spring.profiles.active=openapi-build
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
```

Ensure the document download step runs after the application is ready and with the right profile. Do not use a production profile that disables API Docs for a build step that requires this endpoint to generate artifacts.

## 13. Testing Enable/Disable Configuration

Both states should be tested in separate application contexts or profiles. For the enabled state, confirm the endpoint returns OpenAPI JSON:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "springdoc.api-docs.enabled=true")
@AutoConfigureMockMvc
class ApiDocsEnabledTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$.paths").exists());
    }
}
```

For the disabled state:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "springdoc.api-docs.enabled=false")
@AutoConfigureMockMvc
class ApiDocsDisabledTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void doesNotExposeOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isNotFound());
    }
}
```

The 404 test assumes no other controller, mock proxy, or security rule handles this path. If Spring Security intercepts it first, the request may receive 401/403; configure test security to test endpoint behavior directly or adjust assertions to match the layer under test.

If you changed `springdoc.api-docs.path`, replace the URL in the tests with the custom path. When using groups, also verify `/v3/api-docs/{group}` when enabled and confirm the corresponding endpoints are no longer served when disabled.

## 14. Diagnosing When the Property Has No Effect

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Set to `false` yet `/v3/api-docs` still returns 200 | Profile is inactive or another property source overrides it | Check `SPRING_PROFILES_ACTIVE`, environment, and command line |
| Changed `api-docs.path` yet still calling old URL | Client/proxy/test did not update the path | Check effective configuration and call the new URL |
| Swagger UI opens but fails to load API | API Docs or swagger-config is disabled | Inspect Network tab and config/document endpoints |
| API Docs returns 401/403 instead of 404 | Spring Security or gateway blocks first | Check filter chain, matchers, and proxy |
| Pipeline cannot download OpenAPI | Build profile disables API Docs | Use a build profile with `api-docs.enabled=true` |
| One operation disappears yet endpoint returns 200 | Path/package filter or `@Hidden` excludes the operation | Inspect `paths` in JSON rather than checking status alone |
| API Docs disabled yet business APIs still run | The two endpoint groups are independent | Check authorization on business routes separately |
| Swagger UI with static spec does not work | Document source config is insufficient when auto-configuration is off | Consult the FAQ and bean setup for your version |

## 15. Operational Checklist

- [ ] Determined whether the environment needs to publish OpenAPI JSON/YAML.
- [ ] Set `springdoc.api-docs.enabled` explicitly per profile.
- [ ] Verified the default is `true` when no override is configured.
- [ ] Distinguished `api-docs.enabled` from `swagger-ui.enabled`.
- [ ] Updated custom endpoints if `springdoc.api-docs.path` differs from default.
- [ ] Checked JSON, YAML, swagger-config, and each group endpoint.
- [ ] Distinguished disabling the endpoint from path/package filtering or `@Hidden`.
- [ ] Protected business APIs with independent authorization.
- [ ] If keeping UI while disabling API Docs, configured and verified an external OpenAPI source.
- [ ] Documentation-generation pipelines run with a profile that enables API Docs.
- [ ] Tested both enabled and disabled states in corresponding application contexts.
- [ ] Verified environment variables or command-line arguments do not override unexpectedly.

`springdoc.api-docs.enabled` is the toggle for the specification endpoints provided by Springdoc and defaults to `true`. Set it to `false` when an environment should not publish OpenAPI JSON/YAML; use Spring Profiles or environment variables to control it per environment. This property is independent of Swagger UI, path filters, `@Hidden`, and business API authorization. After making changes, verify the actual JSON/YAML/group URLs and ensure build pipelines still use a documentation-enabled configuration when artifact generation is needed.

## References

- [Springdoc OpenAPI v2 – Core properties](https://springdoc.org/v2/core-properties.html)
- [Springdoc OpenAPI v2 – Features: Disabling API Docs and Swagger UI](https://springdoc.org/v2/features.html)
- [Springdoc OpenAPI v2 – FAQ](https://springdoc.org/v2/faq.html)
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
