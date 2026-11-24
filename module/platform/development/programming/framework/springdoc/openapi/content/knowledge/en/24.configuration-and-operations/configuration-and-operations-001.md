# Organizing springdoc Properties in application.yml or properties

springdoc-openapi uses Spring Boot's standard configuration mechanism. springdoc properties are placed in application.yml, application.yaml, or application.properties, and can be overridden by profile, environment variable, system property, or command-line argument. As a result, the same artifact can run in local, test, staging, and production with API documentation configuration suited to each environment.

The key is to organize the configuration into two groups:

- **OpenAPI documentation configuration:** enabling/disabling the JSON endpoint, documentation path, packages and paths to scan, and API groups.
- **Swagger UI configuration:** enabling/disabling the UI, page path, OpenAPI definition URL, and display options.

There is no need to build a separate configuration mechanism for springdoc. Use Spring Boot's property source and profile rules, keep default values in the shared configuration, and override only the values that differ in each environment.

## 1. Springdoc Reads Configuration from the Spring Environment

Springdoc uses Spring configuration properties. Values can come from YAML, properties, environment variables, system properties, command-line arguments, or external configuration sources loaded by Spring Boot.

Examples of commonly used properties:

| Property | Purpose |
| --- | --- |
| **springdoc.api-docs.enabled** | Enables or disables the OpenAPI endpoint |
| **springdoc.api-docs.path** | Changes the OpenAPI endpoint path |
| **springdoc.packages-to-scan** | Restricts the packages scanned by springdoc |
| **springdoc.paths-to-match** | Includes only paths matching the pattern in the documentation |
| **springdoc.paths-to-exclude** | Excludes paths from the documentation |
| **springdoc.group-configs** | Declares multiple documents by group |
| **springdoc.swagger-ui.enabled** | Enables or disables Swagger UI |
| **springdoc.swagger-ui.path** | Changes the Swagger UI page path |
| **springdoc.swagger-ui.displayRequestDuration** | Displays request duration in Try it out |

Properties may vary depending on the springdoc version. Check the reference for the exact dependency version in use before adding a new property to your configuration.

## 2. Choosing YAML or properties

YAML represents nested structures clearly and is well suited when there are many springdoc properties:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  packages-to-scan:
    - com.example.shop.api
  paths-to-match:
    - /api/**
  swagger-ui:
    enabled: true
    path: /docs
    displayRequestDuration: true
~~~

The same configuration in application.properties:

~~~properties
springdoc.api-docs.enabled=true
springdoc.api-docs.path=/v3/api-docs
springdoc.packages-to-scan=com.example.shop.api
springdoc.paths-to-match=/api/**
springdoc.swagger-ui.enabled=true
springdoc.swagger-ui.path=/docs
springdoc.swagger-ui.displayRequestDuration=true
~~~

Both formats have the same meaning when loaded by Spring Boot. Choose one format as the standard across the entire application. If the same directory contains both application.properties and application.yml (or application.yaml), the .properties file takes precedence. Mixing both formats for the same property group makes it easy for operators to misread which value is currently in effect.

With YAML, pay attention to indentation and data types. Booleans should be written as true or false, lists should use list syntax, and you should not put an entire configuration into a single string if you want Spring Boot to bind it as a structured object.

## 3. Organizing Shared Configuration by Group

A maintainable structure places shared values in application.yml, then groups properties under springdoc.api-docs, springdoc.swagger-ui, and springdoc.group-configs.

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
    version: openapi_3_1
  packages-to-scan:
    - com.example.shop.api
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
  swagger-ui:
    enabled: true
    path: /docs
    displayRequestDuration: true
    deepLinking: true
~~~

In this example:

- api-docs controls the endpoint that generates OpenAPI JSON.
- packages-to-scan and paths-to-match define the scope of APIs included in the documentation.
- paths-to-exclude excludes endpoints that should not appear.
- swagger-ui controls the UI page and display behavior.

Do not put every property into one long, ungrouped list. When a property changes, maintainers should immediately see whether it affects the generated documentation or the user interface.

## 4. Splitting Configuration by Profile

Spring Boot supports profile-specific configuration files using the convention application-{profile}.yml or application-{profile}.properties.

A common layout:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
~~~

application.yml holds shared values:

~~~yaml
springdoc:
  api-docs:
    path: /v3/api-docs
  packages-to-scan:
    - com.example.shop.api
  paths-to-match:
    - /api/**
  swagger-ui:
    path: /docs
~~~

application-dev.yml enables both the documentation and UI for development:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
    displayRequestDuration: true
~~~

application-test.yml can keep the OpenAPI endpoint enabled for contract testing while disabling unnecessary UI:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

application-prod.yml depends on the documentation publication policy:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

There is no mandatory rule requiring production to disable OpenAPI. If the documentation is part of a developer portal or needed by integration partners, you can keep the endpoint enabled while placing it behind authentication, authorization, a gateway, or an internal network. The decision should be based on the API publication policy.

Activate a profile using an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=dev
~~~

Or a command-line argument:

~~~bash
java -jar shop-api.jar --spring.profiles.active=prod
~~~

If multiple profiles are enabled, a profile listed later can override values from an earlier one. For example, SPRING_PROFILES_ACTIVE=prod,region-eu allows application-region-eu.yml to override corresponding properties in application-prod.yml.

Do not set spring.profiles.active inside a configuration file that is only activated by another profile. Select profiles from the runtime environment, command-line arguments, or a higher-level configuration source.

## 5. Using Multiple Documents in One YAML File

If you want to keep a single file while still separating configuration by environment, YAML supports multiple documents with the --- separator and the spring.config.activate.on-profile condition.

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true

---
spring:
  config:
    activate:
      on-profile: test
springdoc:
  swagger-ui:
    enabled: false

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
~~~

The first document is always loaded. Subsequent documents are applied only when the profile expression matches. This approach works well for short configurations; if each environment has many differences, separate application-{profile}.yml files are usually easier to read and manage.

## 6. Understanding Precedence When Overriding Properties

Spring Boot loads multiple PropertySources. A higher-priority source can override values from a lower-priority source. In everyday operations, you can keep this order in mind:

| Source | Example | Effect |
| --- | --- | --- |
| Config packaged inside the JAR | application.yml | Default values for the application |
| Profile-specific file inside the JAR | application-prod.yml | Overrides shared config by profile |
| External config file outside the JAR | ./config/application.yml | Overrides packaged config |
| External profile file outside the JAR | ./config/application-prod.yml | Further overrides by profile |
| Environment variable | SPRINGDOC_APIDOCS_ENABLED | Overrides file config |
| Java system property | -Dspringdoc.api-docs.enabled=false | Overrides environment variables |
| SPRING_APPLICATION_JSON | JSON passed at startup | Overrides lower-priority sources |
| Command-line argument | --springdoc.api-docs.enabled=false | Usually takes higher precedence when running the application |

This is a simplified order explaining the most common sources, not the complete PropertySource list. Spring Boot also has default properties, @PropertySource, JNDI, servlet init parameters, and test-specific sources. When accurate diagnosis is needed, check the complete list for the Spring Boot version you are running.

For example, if the file sets:

~~~yaml
springdoc:
  api-docs:
    enabled: true
~~~

But an environment variable sets:

~~~bash
SPRINGDOC_APIDOCS_ENABLED=false
~~~

Then the effective value is false. You should not look at application.yml alone and assume the endpoint is definitely enabled.

## 7. Rules for Converting Property Names to Environment Variables

Spring Boot uses relaxed binding. To convert a canonical property name into an environment variable name:

1. Replace dots . with underscores _.
2. Remove hyphens -.
3. Convert everything to uppercase.

Examples:

| Property | Environment variable |
| --- | --- |
| springdoc.api-docs.enabled | SPRINGDOC_APIDOCS_ENABLED |
| springdoc.swagger-ui.enabled | SPRINGDOC_SWAGGERUI_ENABLED |
| springdoc.api-docs.path | SPRINGDOC_APIDOCS_PATH |
| springdoc.swagger-ui.path | SPRINGDOC_SWAGGERUI_PATH |

Note that hyphens are removed, not converted into underscores. Therefore, springdoc.api-docs.enabled becomes SPRINGDOC_APIDOCS_ENABLED, not SPRINGDOC_API_DOCS_ENABLED.

You can set variables on Linux/macOS:

~~~bash
export SPRINGDOC_APIDOCS_ENABLED=true
export SPRINGDOC_SWAGGERUI_ENABLED=false
java -jar shop-api.jar
~~~

In PowerShell:

~~~powershell
$env:SPRINGDOC_APIDOCS_ENABLED = "true"
$env:SPRINGDOC_SWAGGERUI_ENABLED = "false"
java -jar shop-api.jar
~~~

Set variables in containers or Kubernetes using environment-specific manifests/deployment configurations. Do not hardcode sensitive values in a Dockerfile or committed manifests if they can be provided via a secret store.

## 8. Externalizing Configuration Outside the JAR

You do not need to rebuild the application just to change the documentation path or toggle Swagger UI. Spring Boot automatically searches for configuration files on the classpath and in several locations outside the working directory, such as:

- The current directory.
- The ./config/ directory.
- Direct subdirectories of ./config/.

Deployment example:

~~~text
deployment/
  shop-api.jar
  config/
    application.yml
    application-prod.yml
~~~

Files outside the JAR can override packaged configuration. This allows the image/JAR to stay unchanged across environments while configuration is supplied at runtime.

If you want to add a configuration directory while keeping the default locations, use spring.config.additional-location. If you use spring.config.location, the specified locations replace the default ones. Both properties are processed very early at startup, so they must be passed via environment variables, system properties, or command-line arguments.

Example:

~~~bash
java -jar shop-api.jar \
  --spring.config.additional-location=optional:file:./runtime-config/
~~~

The optional: prefix allows the application to continue starting if that location does not exist. Use it only when a missing file is genuinely acceptable; for mandatory configuration, let the application fail fast.

## 9. Using Placeholders to Reuse Values

YAML and properties support placeholders to read values from the Spring Environment. You can declare a default value using a colon after the property name.

Example:

~~~yaml
springdoc:
  api-docs:
    path: ${DOCS_API_PATH:/v3/api-docs}
  swagger-ui:
    path: ${DOCS_UI_PATH:/docs}
~~~

When DOCS_API_PATH or DOCS_UI_PATH is set, Spring Boot uses the provided value. Otherwise, the default value after the colon is used.

In placeholders, write property names in canonical lowercase kebab-case. For example, ${springdoc.api-docs.path:/v3/api-docs} helps relaxed binding work consistently across configuration sources.

Do not use placeholders with arbitrary defaults to mask a missing required value. If a missing URL, issuer, or operational detail prevents the application from working properly, let startup fail with a clear error.

## 10. Configuring Document Groups in YAML

When an application has multiple API domains, you can define groups to generate multiple OpenAPI documents. Group configuration resides under springdoc.group-configs.

~~~yaml
springdoc:
  group-configs:
    - group: orders
      display-name: Orders API
      packages-to-scan:
        - com.example.shop.orders
      paths-to-match:
        - /api/orders/**
    - group: catalog
      display-name: Catalog API
      packages-to-scan:
        - com.example.shop.catalog
      paths-to-match:
        - /api/products/**
~~~

Each group has its own name, packages, and paths. Springdoc creates a corresponding documentation endpoint for each group, typically in the form /v3/api-docs/{group} if the base path is unchanged. Swagger UI can display these documents in the API selector dropdown when the URL/group configuration is set appropriately.

Do not create groups solely to distinguish environments. Groups define documentation boundaries by domain or user audience; profiles describe deployment configuration. The two concepts serve different purposes.

## 11. Configuring Groups in properties

In application.properties, list elements use indices:

~~~properties
springdoc.group-configs[0].group=orders
springdoc.group-configs[0].display-name=Orders API
springdoc.group-configs[0].packages-to-scan=com.example.shop.orders
springdoc.group-configs[0].paths-to-match=/api/orders/**

springdoc.group-configs[1].group=catalog
springdoc.group-configs[1].display-name=Catalog API
springdoc.group-configs[1].packages-to-scan=com.example.shop.catalog
springdoc.group-configs[1].paths-to-match=/api/products/**
~~~

The [0] and [1] indices identify elements in the list. When overriding a list from another configuration source, Spring Boot uses the entire list from the highest-priority source; elements that are not redeclared are not automatically merged from lower-priority lists.

For example, if application.yml defines two groups, while application-prod.yml declares only the orders group, then under the prod profile the group list may contain only orders. To keep both, you must declare both groups in full in the overriding source. This rule also applies to list properties such as packages-to-scan and paths-to-match.

## 12. Keeping Swagger UI Configuration Separate from OpenAPI

Swagger UI and the OpenAPI endpoint can be enabled or disabled independently:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

The configuration above still allows clients to fetch the OpenAPI JSON, but does not serve the Swagger UI interface. Conversely, if api-docs.enabled=false, Swagger UI cannot load the documentation from the default endpoint unless configured to use an OpenAPI definition at another URL.

Some commonly used UI settings:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    path: /docs
    displayRequestDuration: true
    deepLinking: true
    docExpansion: none
    filter: true
~~~

Properties such as displayRequestDuration, deepLinking, docExpansion, and filter correspond to Swagger UI options. Check property names and data types for your springdoc version because UI options may follow the bundled Swagger UI version.

If you want to change the UI while still using the same OpenAPI JSON, adjust only the springdoc.swagger-ui group. If you want to change the generated contract content, adjust core settings such as packages-to-scan, paths-to-match, api-docs.path, or API annotations.

## 13. Managing Secrets and Credentials

application.yml is usually committed with the source code, so do not put real passwords, tokens, private keys, or client secrets in this file.

For a secret value that Spring Boot needs to read, retrieve it from a secret manager, platform-injected environment variables, or a configuration tree. For example, Docker/Kubernetes mounts secrets as files:

~~~text
/run/secrets/
  docs.auth.username
  docs.auth.password
~~~

You can load those files with:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

The file names and contents become corresponding properties in the Spring Environment, such as docs.auth.password.

However, do not put secrets into Swagger UI OAuth configuration if the page is downloaded by a browser. A client secret embedded in JavaScript configuration or sent to the browser is no longer secret. For Swagger UI running as a public client, use a client ID and Authorization Code with PKCE; protecting documentation endpoints should be handled by Spring Security, a reverse proxy, or an API gateway.

Do not expose Actuator env or configprops publicly for debugging convenience. These endpoints can reveal configuration names and values; if needed for diagnostics, restrict access and enforce masking according to policy.

## 14. Do Not Confuse springdoc Configuration with Spring Boot Configuration

Properties like server.port, management.server.port, spring.profiles.active, and spring.config.* are core Spring Boot settings. springdoc.* properties control documentation generation and the UI.

Example:

~~~yaml
server:
  port: 8080

spring:
  profiles:
    active: dev

springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
~~~

Do not place server.port under springdoc. The YAML may be syntactically valid, but a misplaced property name will not bind to the intended configuration.

Similarly, springdoc.swagger-ui.path is the UI path, whereas springdoc.api-docs.path is the OpenAPI definition path. Changing one value does not automatically change the other.

## 15. Inspecting Effective Configuration

When the application behaves differently from the expected configuration, check the actual values in the Spring Environment rather than just opening the YAML file.

Suggested steps:

1. Confirm which profile is active, such as dev, test, or prod.
2. Confirm whether external configuration files are loaded and placed in the right location.
3. Check whether environment variables have the exact names required after relaxed binding conversion.
4. Check whether command-line arguments or system properties are overriding the file.
5. Check the actual /v3/api-docs endpoint and Swagger UI path.
6. If needed, use Actuator env or configprops in a secured environment to inspect property sources and values.

Quick diagnostic example:

~~~bash
java -jar shop-api.jar \
  --spring.profiles.active=dev \
  --springdoc.api-docs.enabled=true
~~~

Command-line arguments can override values from files. Therefore, after debugging, remove temporary arguments from deployment scripts if you do not want them to become the default configuration on subsequent runs.

## 16. Testing OpenAPI Configuration in Environments

An integration test can verify that the documentation endpoint is enabled and generates the expected information:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "springdoc.api-docs.enabled=true",
    "springdoc.api-docs.path=/v3/api-docs"
})
@AutoConfigureMockMvc
class OpenApiConfigurationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void openApiEndpointUsesConfiguredPathAndContainsInfo() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$.info.title").exists());
    }
}
~~~

This test assumes the OpenAPI documentation is permitted in the test security context. If Spring Security protects the endpoint, configure appropriate test authentication or access rules.

In addition to the JSON endpoint, include a smoke test for Swagger UI if the UI is enabled in that environment. You can verify that the UI path returns a redirect or an HTML page according to the springdoc version's behavior.

With multiple profiles, run tests or smoke tests for each supported profile. In particular, verify:

- Local/dev: are both documentation and UI enabled properly?
- Test: is the endpoint needed for contract tests working?
- Staging: do URLs, groups, and security match production?
- Production: is the documentation published in accordance with policy?

## 17. Common Configuration Mistakes

**Changed application.yml but the value did not change.** An external file outside the JAR, a profile, an environment variable, or a command-line argument may be overriding it. Check the PropertySources and active profiles.

**Environment variable fails to override the property.** Check the naming rules: dots become _, hyphens are removed, and everything is uppercase. For example, springdoc.api-docs.enabled is SPRINGDOC_APIDOCS_ENABLED.

**Swagger UI cannot load OpenAPI JSON.** Check springdoc.api-docs.enabled, springdoc.api-docs.path, the URL configured in Swagger UI, the context path, and security rules.

**OpenAPI JSON remains enabled even though Swagger UI is disabled.** springdoc.swagger-ui.enabled and springdoc.api-docs.enabled are independent; set both according to the desired policy.

**Groups disappear after activating a profile.** A list in a higher-priority source replaces the entire lower-priority list. Declare all groups you want to keep in that profile.

**Property is in the file but has no effect.** Check spelling, the springdoc prefix, data type, and whether your springdoc version supports that property.

**Both YAML and properties exist and produce unexpected values.** In the same location, .properties takes precedence. Standardize on a single format.

**Dev documentation appears in production.** Check SPRING_PROFILES_ACTIVE, profile files, external config, and environment variables in the deployment.

**Client secret exposed through Swagger UI.** Remove secrets from configurations sent to the browser. Use a public client with PKCE or protect documentation using server-side mechanisms.

**Unsure which property overrides which.** Check the PropertySource precedence order; in a secured environment, use Actuator env/configprops to trace it.

## 18. Configuration Organization Checklist

- [ ] Choose YAML or properties as the primary format.
- [ ] Group properties under springdoc.api-docs, springdoc.swagger-ui, and springdoc.group-configs.
- [ ] Place shared values in application.yml.
- [ ] Override only differences in application-{profile}.yml.
- [ ] Select the profile from the runtime environment or command line.
- [ ] Use exact environment variable names following relaxed binding.
- [ ] Understand external configuration sources and precedence order.
- [ ] Do not assume lists are merged across profiles.
- [ ] Externalize deployment configuration outside the JAR when needed.
- [ ] Retrieve secrets from a secret manager, environment, or configtree.
- [ ] Do not send client secrets to Swagger UI running in the browser.
- [ ] Protect Actuator env/configprops if used for debugging.
- [ ] Verify OpenAPI JSON and Swagger UI with smoke/integration tests.
- [ ] Confirm production configuration follows the documentation publication policy.

## 19. Conclusion

Organizing springdoc properties by group keeps OpenAPI documentation and Swagger UI configuration easy to read, while Spring Boot profiles and externalized configuration help the same application run correctly across multiple environments. Keep shared values in application.yml or application.properties, override only differences in profiles, use environment variables or external files outside the JAR for deployment settings, and manage secrets through dedicated sources. When issues arise, check active profiles along with PropertySource precedence and verify the live endpoints. Remember that configuration lists are replaced completely when overridden and Swagger UI is not a place to store secrets.

## 20. References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): PropertySource precedence, application files, profiles, environment variables, placeholders, config locations, and config trees.
- [Spring Boot — Properties and Configuration](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html): file configuration, profiles, and diagnosing property sources.
- [springdoc-openapi — Configuration Properties](https://springdoc.org/properties.html): core properties, group configs, and Swagger UI properties.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): using management endpoints to observe and diagnose the application.
