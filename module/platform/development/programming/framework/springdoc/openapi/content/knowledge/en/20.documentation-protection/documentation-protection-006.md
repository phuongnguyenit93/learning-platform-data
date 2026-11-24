# Disabling Swagger UI or OpenAPI Endpoints Separately by Environment

Springdoc can publish API documentation in JSON/YAML format while also providing Swagger UI to view, search, or test operations. These two parts are independent capabilities: disabling the Swagger UI interface does not automatically disable OpenAPI endpoints, and disabling OpenAPI endpoints does not mean business APIs are protected.

Spring Boot allows enabling/disabling each part with `springdoc.swagger-ui.enabled` and `springdoc.api-docs.enabled`. Different values can be set per profile such as `dev`, `test`, `staging`, and `prod`, or passed via environment variables at deployment time. That way, development environments can enable full documentation while production exposes only what operational policy permits.

## 1. Distinguishing Swagger UI from OpenAPI Endpoints

Springdoc typically exposes two groups of endpoints:

| Component | Default Path | Function |
|---|---|---|
| OpenAPI JSON | `/v3/api-docs` | Returns the OpenAPI document in JSON format |
| OpenAPI YAML | `/v3/api-docs.yaml` | Returns the OpenAPI document in YAML format |
| Grouped OpenAPI | `/v3/api-docs/{group}` | Returns the document of a `GroupedOpenApi` |
| Swagger UI entry | `/swagger-ui.html` | Path to open the UI, usually redirects to UI resources |
| Swagger UI resources | `/swagger-ui/**` | HTML, JavaScript, CSS, and UI assets |

Swagger UI is a web application that reads an OpenAPI document and renders its operations. The `/v3/api-docs` endpoint supplies the contract data to Swagger UI and to other tools such as client generators, contract tests, or integration pipelines.

Therefore, disabling one component does not implicitly disable the other:

- Disabling Swagger UI while keeping API Docs: users cannot open the UI in the application, yet tools can still download JSON/YAML.
- Keeping Swagger UI while disabling API Docs: the UI may still be served, yet it cannot load the default document unless another OpenAPI source is configured.
- Disabling both: the application does not serve the UI or Springdoc documentation endpoints at those paths.

Common Springdoc properties:

```yaml
springdoc:
  swagger-ui:
    enabled: true
  api-docs:
    enabled: true
```

By default, both features are typically enabled when the Springdoc starter is added to an application. Configure them explicitly so behavior across environments stays predictable.

## 2. Disabling Swagger UI Only While Keeping OpenAPI JSON/YAML

This case fits when production does not need an interactive UI, yet pipelines or integration systems still need to download the OpenAPI document.

```yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: true
```

Expected results:

- `/swagger-ui.html` and the Swagger UI interface are no longer served per Springdoc configuration.
- `/v3/api-docs` still returns OpenAPI JSON.
- `/v3/api-docs.yaml` still returns OpenAPI YAML.
- `/v3/api-docs/{group}` URLs remain accessible if the application defines groups and API Docs is enabled.

For example, a pipeline can fetch the document to generate a client:

```bash
curl -fsS https://api.example.com/v3/api-docs -o openapi.json
```

Disabling the UI is not a measure to protect documentation content. If the OpenAPI document contains internal information, restrict access to the API Docs endpoint with Spring Security, a gateway, or distribute the document only through a dedicated channel.

## 3. Disabling OpenAPI Endpoints While Keeping Swagger UI

This case is less common. It can be appropriate when Swagger UI is configured to load a static OpenAPI file or a document from another server.

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: true
    url: /contracts/orders-openapi.yaml
```

In this example, Swagger UI continues to be served while the document source is switched to `/contracts/orders-openapi.yaml`. That file must actually exist and be served by the web server or application at that URL. If `url` or `urls` is not configured to point to another OpenAPI source, the UI may open yet display a specification-loading error because the default Springdoc endpoint is disabled.

If there are multiple static documents, you can configure a list:

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: true
    urls:
      - name: Orders API
        url: /contracts/orders-openapi.yaml
      - name: Customers API
        url: /contracts/customers-openapi.yaml
    urls-primary-name: Orders API
```

Swagger UI is only a viewing interface. Disabling Springdoc-generated API Docs does not prevent Swagger UI from loading a static file or an external OpenAPI URL.

## 4. Disabling Both Swagger UI and API Docs

If production does not need to serve documentation from the application, you can disable both:

```yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: false
```

Once the application starts with this configuration:

- Swagger UI is not served.
- Springdoc-generated OpenAPI endpoints are not registered/served as usual.
- Business APIs continue working according to their controllers and runtime configuration.
- Annotations such as `@Operation`, `@Schema`, or `@ApiResponse` remain in source code; only HTTP documentation publishing is disabled.

When documentation endpoints are no longer served, requests typically receive 404, though the actual status may differ if Spring Security, a reverse proxy, a gateway, or an error handler intercepts requests first. Verify in the target deployment environment rather than relying on a single expected status.

## 5. Configuration via Spring Profiles

Spring Profiles provide a clean way for each environment to define its own documentation policy. For example, enable documentation in local and staging, and disable it in production.

### Default configuration in `application.yml`

```yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
```

### Production configuration in `application-prod.yml`

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
```

When running in production, activate the `prod` profile:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Or set an environment variable:

```bash
SPRING_PROFILES_ACTIVE=prod
```

When the `prod` profile is active, values in `application-prod.yml` override the corresponding defaults. Locally, without activating the production profile, both features remain enabled per `application.yml`.

### Using an intermediate profile for staging

Staging often needs documentation for QA or partner testing, yet access should still be restricted:

```yaml
# application-staging.yml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
```

Then protect Swagger UI and API Docs with an appropriate authentication mechanism. Do not treat staging as inherently safe; it may contain production-like data or connect to live services.

## 6. Profile Configuration in a Single YAML File

If you prefer keeping configuration in one file, use multi-document YAML and `spring.config.activate.on-profile`:

```yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
---
spring:
  config:
    activate:
      on-profile: prod
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
```

The first document applies by default. The second document applies only when the `prod` profile is active. Splitting `application-prod.yml` is often easier to maintain when environment configs grow long or are owned by deployment teams.

Do not set `spring.profiles.active` inside a configuration document that is itself activated by another profile. Select the profile from the command line, environment variables, or deployment configuration.

## 7. Controlling via Environment Variables

In containers or deployment platforms, Springdoc properties can be passed directly as environment variables:

| Spring property | Environment variable | Meaning |
|---|---|---|
| `springdoc.swagger-ui.enabled` | `SPRINGDOC_SWAGGER_UI_ENABLED` | Enable/disable Swagger UI |
| `springdoc.api-docs.enabled` | `SPRINGDOC_API_DOCS_ENABLED` | Enable/disable OpenAPI endpoints |
| `springdoc.swagger-ui.path` | `SPRINGDOC_SWAGGER_UI_PATH` | Change UI entry path |
| `springdoc.api-docs.path` | `SPRINGDOC_API_DOCS_PATH` | Change API Docs path |

Production run example:

```bash
SPRINGDOC_SWAGGER_UI_ENABLED=false \
SPRINGDOC_API_DOCS_ENABLED=false \
java -jar app.jar
```

On Windows PowerShell:

```powershell
$env:SPRINGDOC_SWAGGER_UI_ENABLED = "false"
$env:SPRINGDOC_API_DOCS_ENABLED = "false"
java -jar app.jar
```

Environment variables override application configuration according to Spring Boot's property source precedence. If YAML specifies `enabled: false` while the deployment environment sets the variable to `true`, the effective value can become `true`. When troubleshooting, check the active profile and the actual property sources.

## 8. Changing Documentation URLs Does Not Disable Documentation

You can change the default paths:

```yaml
springdoc:
  api-docs:
    path: /internal/openapi
  swagger-ui:
    path: /api-reference
```

Then the JSON endpoint is served at the configured API Docs path and Swagger UI gets the new entry path. Changing paths only changes URLs; it does not disable endpoints or restrict who can access them. Users can still download the document if they know the URL and are permitted through network/security layers.

For groups, endpoints remain under the custom API Docs path per Springdoc rules, with the group name appended. When changing paths, synchronize updates across:

- `requestMatchers` in Spring Security.
- Reverse proxy or API gateway rules.
- URLs used by pipelines or clients to fetch OpenAPI.
- `swagger-ui.url` or `swagger-ui.urls` if the UI loads documents via custom endpoints.
- Health checks or contract tests depending on old paths.

Do not use an obscure URL as your sole security measure. URLs are not credentials and can appear in logs, client configs, or browser history.

## 9. Protecting Documentation Endpoints with Spring Security

If you want to keep Swagger UI and API Docs available to a specific user group, protect the endpoints with Spring Security. The example below requires the `DOCS_READ` authority for both the UI and documents:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DocumentationSecurityConfiguration {

    @Bean
    SecurityFilterChain documentationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/swagger-ui.html",
                    "/swagger-ui/**",
                    "/v3/api-docs/**"
                ).hasAuthority("DOCS_READ")
                .anyRequest().authenticated()
            )
            .build();
    }
}
```

This is an example matcher for default paths. If you changed `springdoc.swagger-ui.path` or `springdoc.api-docs.path`, update the matchers to match. When multiple `SecurityFilterChain` beans exist, check their order and `securityMatcher` so documentation requests enter the intended chain.

With an OAuth2 Resource Server, `DOCS_READ` might map from a scope such as `SCOPE_docs:read`. With form login or sessions, authorities may come from user roles. Pick a rule matching your real authentication mechanism.

Swagger UI loads HTML, JavaScript, CSS, and the OpenAPI document. Protecting only JSON while leaving the UI public allows unauthorized users to open the UI page even though they cannot load the docs. Protecting only the UI while leaving JSON public lets users bypass the UI and call API Docs directly. Protect both groups when policy requires it.

## 10. Disabling API Docs Does Not Replace Business API Authorization

`springdoc.api-docs.enabled=false` controls only Springdoc's documentation endpoints. It does not make business controllers private and does not alter authentication rules on `/api/**`.

For example:

- `/v3/api-docs` is disabled, yet `/api/admin/users` remains reachable if Spring Security configures `permitAll()`.
- Swagger UI is disabled, yet `/v3/api-docs` can still expose all paths, schemas, and security metadata.
- API Docs is protected by login, yet business APIs still need separate authorization per resource and operation.

Use Spring Security, gateways, network policies, or equivalent authorization mechanisms to protect real APIs. Disabling documentation only reduces the exposure of documentation through Springdoc endpoints.

## 11. Impact on OpenAPI Generation in Build Pipelines

Some pipelines use the Springdoc OpenAPI Maven Plugin to call a running application, fetch `/v3/api-docs`, and save the document as an artifact. If the profile the pipeline launches sets:

```yaml
springdoc:
  api-docs:
    enabled: false
```

the plugin may fail to fetch the document because the endpoint is turned off. This does not mean OpenAPI annotations are lost; the endpoint is simply not exposed during that run.

Common ways to structure this:

1. Use a dedicated profile for the documentation-generation step where `springdoc.api-docs.enabled=true`.
2. Run the application with a build/test profile, export JSON/YAML as an artifact, and deploy production with a profile that disables API Docs.
3. Store exported documents in a separate artifact repository or static host and enforce access permissions per policy.

Avoid accidentally using a production profile that disables API Docs during a build step that needs to fetch `/v3/api-docs`. Separate build-time configuration from runtime configuration and verify the URL the plugin calls.

## 12. Verifying Configuration After Deployment

After changing a profile or environment variable, restart the application according to your deployment workflow and test each endpoint.

Example when intending to disable both:

```bash
curl -i https://api.example.com/swagger-ui.html
curl -i https://api.example.com/v3/api-docs
curl -i https://api.example.com/v3/api-docs.yaml
```

The expected outcome is that documentation endpoints are no longer served. Statuses may be 404 or a response produced by a security gateway, depending on architecture.

If intending to disable UI while keeping API Docs:

```bash
curl -i https://api.example.com/swagger-ui.html
curl -i https://api.example.com/v3/api-docs
```

Expect the UI not to be served while API Docs still returns JSON. If keeping UI with a static file, verify both the UI URL and the YAML file URL loaded by the UI.

You can check group documents too:

```bash
curl -i https://api.example.com/v3/api-docs/admin
```

When disabling API Docs, test the default URL, YAML, and groups. Do not test only `/v3/api-docs` and conclude all documentation endpoints are off.

## 13. Configuration Matrix by Need

| Need | `swagger-ui.enabled` | `api-docs.enabled` | Notes |
|---|---:|---:|---|
| Full local developer setup | `true` | `true` | Both UI and JSON/YAML are active |
| Pipeline needs document, no UI needed | `false` | `true` | Can fetch `/v3/api-docs` to generate clients |
| UI uses a static OpenAPI file | `true` | `false` | Must configure `swagger-ui.url` or `urls` |
| Production publishes no docs | `false` | `false` | Business APIs still need separate security |
| Staging for QA/partners | `true` | `true` | Should protect both UI and API Docs |

## 14. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Disabled Swagger UI yet `/v3/api-docs` is still accessible | Only set `swagger-ui.enabled=false` | Also set `api-docs.enabled=false` to turn off the document |
| Swagger UI opens yet reports an error loading definition | API Docs disabled or source URL wrong | Configure `swagger-ui.url`/`urls` to another document or enable API Docs |
| Production YAML set yet UI stays enabled | `prod` profile not active or overridden by env var | Check `SPRING_PROFILES_ACTIVE` and property sources |
| Docs endpoint still reachable after changing path | Only changed URL without disabling endpoint or updating proxy | Check `api-docs.enabled`, path, and gateway routes |
| `/v3/api-docs` blocked yet Swagger UI still loads page | Only protected API Docs or only protected UI | Check `/swagger-ui.html`, `/swagger-ui/**`, and `/v3/api-docs/**` |
| Maven plugin fails to fetch OpenAPI | Build profile disables API Docs | Use a build profile with `api-docs.enabled=true` |
| Production disables docs yet business APIs remain open | Confused disabling docs with disabling APIs | Configure authorization for business routes |
| Group docs still leak information | Checked only default document URL | Check `/v3/api-docs/{group}` and corresponding gateway rules |
| Effective configuration differs from expectation | Environment variables or config server override YAML | Check effective values and running profile |

## 15. Per-Environment Deployment Checklist

- [ ] Decided separately whether Swagger UI may be shown in this environment.
- [ ] Decided separately whether OpenAPI JSON/YAML endpoints may be accessed.
- [ ] Configured `springdoc.swagger-ui.enabled` and `springdoc.api-docs.enabled` explicitly.
- [ ] Appropriate profile is activated when running the application.
- [ ] Environment variables do not unintentionally override profile configuration.
- [ ] If UI remains enabled while API Docs is disabled, configured another OpenAPI source.
- [ ] If paths changed, updated Spring Security, gateway, pipelines, and UI URLs.
- [ ] Protected both UI resources and API Docs if documentation is restricted to authorized users.
- [ ] Did not treat disabling docs as a substitute for protecting business APIs.
- [ ] Document-generation pipeline uses a profile with API Docs enabled.
- [ ] Verified JSON, YAML, and all group endpoints after deployment.
- [ ] Verified results externally through the actual production gateway/proxy.

`springdoc.swagger-ui.enabled` controls the UI interface; `springdoc.api-docs.enabled` controls the OpenAPI document endpoints. They can be toggled independently and configured via Spring Profiles or environment variables. When documentation needs protection, use Spring Security or a gateway across both the UI and JSON/YAML; when a pipeline must generate artifacts, run that step with API Docs enabled. This separation lets each environment publish the right level of documentation without altering business API behavior.

## References

- [Springdoc OpenAPI – Official documentation](https://springdoc.org/)
- [Springdoc OpenAPI – Properties and configuration](https://springdoc.org/properties.html)
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
