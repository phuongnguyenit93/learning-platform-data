# Overriding Configuration with Profiles and Environment Variables

A Spring Boot application typically runs across multiple environments such as local, test, staging, and production. Each environment may use different ports, service URLs, logging levels, and API documentation publication policies. Spring Boot supports splitting configuration by profile and overriding properties via environment variables or startup arguments.

With `springdoc-openapi`, this approach lets you enable Swagger UI during development, change the documentation path in staging, or disable documentation endpoints in production. Environment configuration must be designed intentionally: the same property can be declared in multiple places, and the final value depends on the precedence order of the configuration sources.

## 1. Shared Configuration in `application.yml`

Place values shared across all environments in `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
    disable-swagger-default-url: true

logging:
  level:
    org.springdoc: INFO
```

In this example, OpenAPI JSON is published at `/v3/api-docs`, Swagger UI is accessed at `/swagger-ui.html`, and Swagger UI's default Petstore URL is disabled. This is the baseline configuration; profiles or environment variables can override individual properties without modifying this file.

Only place values in the shared configuration that are genuinely identical across environments. Internal URLs, credentials, database details, and environment-dependent security policies should be placed in separate configuration sources.

## 2. Creating Profile-Specific Configuration Files

Spring Boot automatically loads profile-specific files matching `application-{profile}.yml`. For example:

```text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
```

`application-local.yml` can enable full documentation for development:

```yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true

logging:
  level:
    org.springdoc: DEBUG
```

`application-prod.yml` can disable Swagger UI and the OpenAPI endpoint if production should not publish documentation:

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false

logging:
  level:
    org.springdoc: WARN
```

If production needs JSON documentation for an internal system, you can keep `springdoc.api-docs.enabled: true`, disable `springdoc.swagger-ui.enabled: false` separately, and protect the JSON/YAML endpoints with Spring Security or a gateway. Disabling the UI does not mean the OpenAPI endpoint is disabled; the two properties serve distinct purposes.

## 3. Activating Profiles

You can select a profile via an environment variable:

```bash
SPRING_PROFILES_ACTIVE=prod
```

Or pass an argument when running the JAR:

```bash
java -jar app.jar --spring.profiles.active=prod
```

When the `prod` profile is active, Spring Boot loads the shared configuration and then applies values from `application-prod.yml` according to Config Data precedence order. If multiple profiles are activated, each corresponding file can be loaded; when the same property is declared in multiple places, profile order and configuration source precedence affect the final value. Avoid activating profiles with conflicting policies simultaneously without verifying the result.

`spring.profiles.active` is a profile-selection property, not a business property. Do not place it inside an `application-{profile}.yml` file to activate that same profile. Select profiles from non-profile-specific configuration, environment variables, system properties, or the command line.

## 4. Using `spring.config.activate.on-profile` in a Single YAML File

If you want to consolidate multi-environment configuration into a single file, Spring Boot supports multi-document YAML using the `---` separator:

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

logging:
  level:
    org.springdoc: WARN
```

The first document is not tied to any profile, so it is applied globally. The second document is activated only when the `prod` profile is active. This works well for small applications, but as per-environment configuration grows, separate `application-{profile}.yml` files are usually easier to read and review.

Do not declare `spring.profiles.active`, `spring.profiles.include`, or `spring.profiles.group` inside a document activated via `spring.config.activate.on-profile`. Profile-selection properties must reside in a non-profile-specific document.

## 5. Profile Groups for an Environment with Multiple Configurations

A production environment may require multiple small configuration groups, such as production database, observability, and documentation policy. You can bundle them into a profile group:

```yaml
spring:
  profiles:
    group:
      production:
        - prod-database
        - prod-observability
        - prod-docs
```

Activating `production` causes Spring Boot to activate its member profiles as well. Each corresponding file can maintain a focused responsibility:

```text
application-prod-database.yml
application-prod-observability.yml
application-prod-docs.yml
```

Example `application-prod-docs.yml`:

```yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
```

Profile groups let pipelines select an environment with a single name while separating configuration by concern. Declare groups in non-profile-specific configuration; do not place groups inside profile-specific member files.

## 6. Precedence Order of Configuration Sources

Spring Boot has multiple sources providing the same property. When a property appears in multiple places, the higher-priority source determines the effective value. A common summary, from lowest to highest, is:

1. Default values declared inside the application.
2. Configuration files packaged inside the JAR, such as `application.yml`.
3. Profile-specific configuration files, such as `application-prod.yml`.
4. External configuration files loaded by Spring Boot outside the application.
5. Operating system environment variables.
6. Java system properties, for example `-Dspringdoc.api-docs.enabled=false`.
7. `SPRING_APPLICATION_JSON`.
8. Command-line arguments, for example `--springdoc.api-docs.enabled=false`.

This is a simplified diagram for understanding common sources; the full order also includes test properties, Devtools, JNDI, and other configuration sources. With Config Data, file locations, active profiles, and import order also influence the outcome. When an exact determination is required, check the Spring Boot documentation for your exact version and inspect runtime values in the deployment environment.

For example, `application-prod.yml` enables API docs:

```yaml
springdoc:
  api-docs:
    enabled: true
```

However, the production environment sets the variable:

```bash
SPRINGDOC_API_DOCS_ENABLED=false
```

The final value is `false` because environment variables have higher precedence than Config Data files. This is intentional override behavior, not Spring Boot ignoring the profile.

## 7. Mapping Properties to Environment Variable Names

Spring Boot relaxed binding allows converting property names to environment variable format using these rules:

- Convert the name to uppercase.
- Replace dots (`.`) with underscores (`_`).
- Remove hyphens (`-`).
- Keep underscores as separators.

Examples:

| Property | Environment variable |
| --- | --- |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `server.port` | `SERVER_PORT` |
| `springdoc.api-docs.enabled` | `SPRINGDOC_API_DOCS_ENABLED` |
| `springdoc.api-docs.path` | `SPRINGDOC_API_DOCS_PATH` |
| `springdoc.swagger-ui.enabled` | `SPRINGDOC_SWAGGER_UI_ENABLED` |
| `springdoc.swagger-ui.path` | `SPRINGDOC_SWAGGER_UI_PATH` |
| `springdoc.swagger-ui.disable-swagger-default-url` | `SPRINGDOC_SWAGGER_UI_DISABLE_SWAGGER_DEFAULT_URL` |

Container deployment example using only environment variable overrides:

```bash
SPRING_PROFILES_ACTIVE=prod
SERVER_PORT=8081
SPRINGDOC_API_DOCS_ENABLED=true
SPRINGDOC_API_DOCS_PATH=/internal/openapi
SPRINGDOC_SWAGGER_UI_ENABLED=false
```

The application uses the `prod` profile, listens on port `8081`, publishes OpenAPI JSON at the internal path `/internal/openapi`, and disables Swagger UI. The documentation endpoint still needs access control if it is intended only for internal systems.

For list or map properties, environment variable naming has specific indexing rules; do not guess variable names for complex structures. If you need to configure multiple `springdoc.group-configs`, YAML or external configuration files are usually easier to control and review.

## 8. Overriding via Command Line and `SPRING_APPLICATION_JSON`

Command-line arguments are useful when running manually or in a deployment job:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --springdoc.api-docs.enabled=true \
  --springdoc.swagger-ui.enabled=false \
  --springdoc.api-docs.path=/internal/openapi
```

If you need to pass a group of properties as JSON, you can use `SPRING_APPLICATION_JSON`:

```bash
SPRING_APPLICATION_JSON='{"springdoc":{"api-docs":{"enabled":true,"path":"/internal/openapi"},"swagger-ui":{"enabled":false}}}' \
SPRING_PROFILES_ACTIVE=prod \
java -jar app.jar
```

The JSON must be valid, and property names must match the Spring Boot structure. Avoid placing secrets or tokens on the command line or in JSON if they could appear in process lists, logs, or deployment platform diagnostics.

Do not use too many override mechanisms simultaneously for the same property. If YAML files, environment variables, JSON, and command-line arguments all set the same value, tracing the source of the final configuration becomes harder. Choose one deliberate configuration source per environment.

## 9. Loading External Configuration Outside the JAR

You can place separate configuration outside the artifact to change settings without rebuilding the application. Example deployment directory:

```text
/opt/store-service/
  app.jar
  config/
    application.yml
    application-prod.yml
```

Spring Boot automatically searches several standard external configuration locations. You can add extra locations using `spring.config.additional-location`:

```bash
SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:/etc/store-service/ \
SPRING_PROFILES_ACTIVE=prod \
java -jar /opt/store-service/app.jar
```

`spring.config.additional-location` adds search locations alongside the default ones. If you use `spring.config.location`, the default locations are replaced; you must list every location the application still needs to read. When you only want to supplement with external deployment files, `additional-location` is usually less surprising.

The `optional:` prefix lets the application start if the location does not exist. Use it only when that configuration is truly optional; for files containing connection settings or critical policies, a missing file should cause deployment to fail clearly rather than silently falling back to defaults.

## 10. Managing Secrets Separately from Regular Configuration

Profiles and environment variables are well suited for varying properties across environments, but you should not commit passwords, private keys, client secrets, or access tokens to Git. Use a secret manager, Kubernetes Secret, Docker secret, or the platform's secret provisioning mechanism.

For example, environment variables can reference credentials supplied by the deployment platform:

```bash
SPRING_DATASOURCE_USERNAME=store_app
SPRING_DATASOURCE_PASSWORD=<value-provided-by-secret-manager>
```

In application configuration, reference only the property:

```yaml
spring:
  datasource:
    username: ${SPRING_DATASOURCE_USERNAME}
    password: ${SPRING_DATASOURCE_PASSWORD}
```

Never put real secret values in examples, profile files, or OpenAPI documentation. Environment variables can also be exposed via process inspection, logs, or diagnostic tools; for high-security environments, prefer mounted secrets or an integrated secret manager.

## 11. Profile-Based Configuration for springdoc

A simple matrix might look like this:

| Environment | API docs JSON/YAML | Swagger UI | Purpose |
| --- | --- | --- | --- |
| `local` | Enabled | Enabled | Developing and trying out APIs. |
| `test` | Enabled when contract tests require it | Optional | Checking documentation and integration. |
| `staging` | Enabled | Enabled with controls | QA and API review before release. |
| `prod` | Disabled or enabled with protection | Usually disabled or access-restricted | Reducing the public documentation surface. |

Example `application-staging.yml`:

```yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /docs
```

Example `application-prod.yml` when internal pipelines still need to fetch JSON:

```yaml
springdoc:
  api-docs:
    enabled: true
    path: /internal/openapi
  swagger-ui:
    enabled: false
```

When production keeps API docs enabled, protect `/internal/openapi` and its corresponding JSON/YAML variants with Spring Security or a gateway. Changing the path is not an authentication mechanism; an obscure URL can still be discovered or called directly.

## 12. Verifying Effective Configuration

When the application runs in the wrong environment or springdoc does not use the expected values, check in order:

1. Confirm the active profile from startup logs or deployment configuration (`SPRING_PROFILES_ACTIVE`, command line).
2. Confirm that `application-{profile}.yml` is packaged or mounted at the right location.
3. Verify environment variable names according to relaxed binding rules, especially hyphens and dots.
4. Check whether command-line arguments, Java system properties, or `SPRING_APPLICATION_JSON` are overriding the property.
5. Call the actual OpenAPI endpoint to verify its path and enabled/disabled state.
6. Check Swagger UI separately; the UI may be disabled while the JSON endpoint remains enabled.
7. If Spring Boot Actuator is present, use `env` or `configprops` in a secured environment to inspect configuration sources and bound values. Do not expose these endpoints publicly because they can disclose configuration details.
8. Check startup logs to spot malformed YAML, nonexistent profiles, or unloaded config locations.

Do not rely solely on whether a YAML file contains the desired value. What needs verification is the effective property after all configuration sources are merged.

## 13. Testing Profiles and Environment Variables

You can use `@ActiveProfiles` to test profile configuration in Spring Boot tests:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("prod")
class ProductionDocsConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void disablesSwaggerUiInProductionProfile() {
        assertThat(environment.getProperty(
            "springdoc.swagger-ui.enabled", Boolean.class
        )).isFalse();
    }
}
```

This test assumes `application-prod.yml` sets `springdoc.swagger-ui.enabled: false`. It confirms the value loaded in the test context, but does not replace smoke tests against the actual artifact/container.

For deployed environments, run a smoke test after startup:

- The correct profile is activated.
- Port and context path are correct.
- `/v3/api-docs` or the custom path has the expected status.
- Swagger UI is enabled/disabled according to policy.
- If documentation is retained in production, unauthorized access is denied and authorized callers can download it.

## 14. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Always uses local config when deployed | `SPRING_PROFILES_ACTIVE` is unset or misspelled | Check environment variables and active profile logs. |
| Profile is activated but properties do not change | Profile-specific file is not loaded or misnamed | Use `application-prod.yml` and valid Config Data locations. |
| YAML has a value but runtime uses another | Overridden by env var, system property, or command line | Check higher-priority configuration sources. |
| `SPRINGDOC_API_DOCS_ENABLED` has no effect | Wrong variable name, app uses another property, or dependency does not support the property | Check relaxed binding and springdoc version. |
| Swagger UI is disabled but `/v3/api-docs` is still reachable | Only `springdoc.swagger-ui.enabled` was disabled | Disable `springdoc.api-docs.enabled` separately or protect the endpoint if needed. |
| API docs disabled but Swagger UI static resources remain | Only API docs disabled, UI not disabled | Also set `springdoc.swagger-ui.enabled: false` if you want to disable the UI. |
| `spring.config.location` drops default configuration | This property replaces default locations | Use `spring.config.additional-location` when you want to supplement. |
| App starts despite missing critical config file | `optional:` was used for a mandatory location | Remove `optional:` to fail fast when configuration is missing. |
| Profile test differs from container behavior | Test does not use the same env vars or config mounts as production | Add smoke tests against the actual artifact and deployment configuration. |
| Secrets appear in Git or logs | Secrets placed directly in YAML/command line | Move to a secret manager and restrict access to configuration. |

## 15. Operational Principles

- Place shared values in `application.yml` and environment-specific values in `application-{profile}.yml`.
- Activate profiles via environment variables, system properties, or command-line arguments.
- Use `spring.config.activate.on-profile` for multi-document YAML; do not place profile-selection properties inside profile-specific documents.
- Use profile groups when an environment needs to activate multiple configuration groups.
- Understand precedence order before investigating overridden properties.
- Map environment variables using relaxed binding; do not guess variable names for complex lists/maps.
- Use `spring.config.additional-location` to supplement external configuration outside the JAR; use `spring.config.location` only when replacing default locations.
- Never commit secrets; obtain credentials from a secret manager or deployment platform.
- Separate `springdoc.api-docs.enabled` from `springdoc.swagger-ui.enabled` and protect endpoints if documentation remains published.
- Verify effective properties, live endpoints, and access policies after deployment.

Profiles select configuration sets per environment; environment variables and command-line arguments let the deployment platform override values without modifying the artifact. Understanding precedence order, relaxed binding rules, and the boundary between API docs and Swagger UI allows operations teams to enable documentation in local/staging, control it in production, and avoid misconfiguration or secret exposure.

## References

- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot – Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Springdoc OpenAPI – Properties and Configuration](https://springdoc.org/)
