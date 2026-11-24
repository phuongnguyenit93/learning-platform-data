# Differences Between Springdoc Configuration and UI Tool Configuration

Springdoc-openapi and Swagger UI are commonly installed together in a Spring Boot application, yet they perform two distinct jobs. Springdoc reads controllers, DTOs, annotations, and Spring configuration to generate the OpenAPI document. Swagger UI receives that document and renders it into a documentation page where users can search, expand operations, and send test requests.

Because both tools expose many properties under the same `springdoc` prefix, it is easy to mistake a UI change for an API contract change. For example:

- `springdoc.paths-to-match` determines which endpoints are included in the OpenAPI document.
- `springdoc.swagger-ui.doc-expansion` only determines how operations are expanded on the page.
- `springdoc.api-docs.path` changes the URL of the OpenAPI document.
- `springdoc.swagger-ui.path` changes the URL of the Swagger UI HTML page.

Distinguishing these two configuration layers helps diagnose issues accurately when the JSON/YAML does not change despite UI changes, or when the UI still renders while the OpenAPI document is missing operations.

## 1. Two Tools, Two Responsibilities

| Component | Responsibility | Configuration Examples |
|---|---|---|
| Springdoc core | Scans controllers, selects endpoints, generates paths, operations, schemas, responses, and security definitions | springdoc.paths-to-match, springdoc.packages-to-scan, springdoc.api-docs.path |
| OpenAPI model customization | Augments or modifies OpenAPI contract content | OpenAPI bean, OpenApiCustomizer, OperationCustomizer |
| Swagger UI | Renders the document, navigates tags/operations, displays schemas, and supports Try it out | springdoc.swagger-ui.doc-expansion, operations-sorter, filter |
| Swagger UI network/auth configuration | Selects documents, config endpoint, OAuth UI, and browser request options | springdoc.swagger-ui.url, urls, config-url, oauth.* |

Springdoc generates the OpenAPI document. Swagger UI is a client-side application that reads that document. Swagger UI configuration does not modify controllers, schemas, or responses that Springdoc has already generated.

## 2. Processing Flow from Application to UI

~~~mermaid
flowchart TD
    A[Spring Controller / DTO / Annotation] --> B[Springdoc]
    C[Spring Boot application properties] --> B
    D[OpenAPI bean / Customizer] --> B
    B --> E[OpenAPI JSON or YAML]
    B --> F[Swagger UI config JSON]
    G[Swagger UI properties] --> F
    E --> H[Swagger UI in browser]
    F --> H
    H --> I[Render operations / schemas]
    H --> J[Try it out HTTP request]
    J --> K[Spring Boot API endpoint]
~~~

Common default endpoints:

| Endpoint | Content |
|---|---|
| /v3/api-docs | OpenAPI document in JSON format. |
| /v3/api-docs.yaml | OpenAPI document in YAML format. |
| /v3/api-docs/swagger-config | Configuration JSON fetched by Swagger UI to discover the document URL and UI options. |
| /swagger-ui.html | HTML page that opens Swagger UI. |
| /swagger-ui/** | Static UI resources such as JavaScript and CSS. |

Swagger UI typically loads the configuration first, then uses the URL inside that configuration to fetch the OpenAPI JSON/YAML. Therefore, these two endpoints have different meanings:

- `springdoc.swagger-ui.url`: URL of the OpenAPI document.
- `springdoc.swagger-ui.config-url`: URL of the Swagger UI configuration file.

Do not point `config-url` to an OpenAPI YAML file. Swagger UI expects a config document at that URL; the API definition URL is declared via `url` or `urls`.

## 3. Configuring OpenAPI Generation

The core property group determines what Springdoc reads and where it exposes the contract.

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /internal/openapi
    version: OPENAPI_3_1
  packages-to-scan:
    - com.example.catalog.api
    - com.example.billing.api
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
  writer-with-default-pretty-printer: true
~~~

Meaning:

- `api-docs.enabled`: enables or disables the endpoint serving the OpenAPI document.
- `api-docs.path`: changes the JSON document path.
- `api-docs.version`: selects OpenAPI 3.0 or 3.1 as supported by the Springdoc branch.
- `packages-to-scan`: restricts packages containing controllers to inspect.
- `paths-to-match`: includes only matching paths in the document.
- `paths-to-exclude`: excludes paths from the document.
- `writer-with-default-pretty-printer`: formats JSON for better readability.

These properties affect the OpenAPI document. For example, excluding `/api/internal/**` from the documentation does not delete the corresponding controller and does not block HTTP requests to that controller. To protect runtime endpoints, use Spring Security, a gateway, or network policies.

### 3.1. Customizing Document Content with Java

If shared metadata, security schemes, or server URLs are needed, create an `OpenAPI` bean:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI customOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("Catalog API")
                        .version("1.4.0")
                        .description("API for managing the product catalog."));
    }
}
~~~

To customize individual documents or groups, use `OpenApiCustomizer` and `OperationCustomizer`. This is customization of the contract, not customization of the Swagger UI layout.

~~~java
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiExtensionConfiguration {

    @Bean
    OpenApiCustomizer addOwnerExtension() {
        return openApi -> openApi.addExtension("x-owner", "catalog-team");
    }
}
~~~

After adding a customizer, inspect `/v3/api-docs` to confirm the extension actually appears in the document.

## 4. Configuring the Swagger UI Path

The `springdoc.swagger-ui` property group primarily controls the UI page and how the UI loads the document.

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    path: /docs
    config-url: /internal/openapi/swagger-config
    url: /internal/openapi
    doc-expansion: none
    operations-sorter: alpha
    tags-sorter: alpha
    display-request-duration: true
    display-operation-id: true
~~~

In the example:

- The UI page is at `/docs`.
- The UI loads configuration from `/internal/openapi/swagger-config`.
- The UI fetches the OpenAPI document from `/internal/openapi`.
- Tags and operations are sorted alphabetically.
- Operations are collapsed by default.
- The UI displays request execution duration and `operationId`.

When changing `api-docs.path` or using a separate config URL, verify the actual configuration endpoint served by the application. If the default configuration does not point to the new path, update `config-url` accordingly.

### 4.1. url, urls, and config-url

| Property | Points To | When to Use |
|---|---|---|
| springdoc.swagger-ui.url | A single OpenAPI JSON/YAML document | A single custom API definition. |
| springdoc.swagger-ui.urls | A list of multiple OpenAPI documents | Swagger UI needs a dropdown to switch between multiple services/groups. |
| springdoc.swagger-ui.config-url | Swagger UI configuration document | Using UI configuration stored at a separate endpoint or source. |

Example listing two groups:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Catalog
        url: /v3/api-docs/catalog
      - name: Billing
        url: /v3/api-docs/billing
    urls-primary-name: Catalog
~~~

When `urls` is configured, the single `url` property is ignored. Names and URLs in the list must be unique because Swagger UI uses them as identifiers.

## 5. Properties That Only Affect Display

The properties below change the viewer experience without changing paths or schemas in OpenAPI:

~~~yaml
springdoc:
  swagger-ui:
    doc-expansion: none
    operations-sorter: alpha
    tags-sorter: alpha
    filter: true
    max-displayed-tags: 30
    default-models-expand-depth: 1
    default-model-expand-depth: 1
    display-operation-id: true
    display-request-duration: true
    show-extensions: true
    show-common-extensions: true
~~~

Some options:

| Property | Effect |
|---|---|
| doc-expansion | `list`, `full`, or `none` controls initial expansion level. |
| operations-sorter | Sorts operations alphabetically or by HTTP method. |
| tags-sorter | Sorts tags. |
| filter | Displays an operation/tag filter input box. |
| max-displayed-tags | Limits the number of displayed tags. |
| default-models-expand-depth | Expansion depth of the models list. |
| display-operation-id | Displays `operationId` in the UI. |
| display-request-duration | Displays the duration of Try it out requests. |
| show-extensions | Displays `x-` vendor extensions in the UI. |
| show-common-extensions | Displays constraints such as `minLength`, `maxLength`, `minimum`, and `maximum`. |

If users want a more compact Swagger UI, change `doc-expansion` or `filter`. If they want to remove an endpoint from the contract, change `paths-to-exclude`, `GroupedOpenApi`, or appropriate annotations. Do not use UI properties to fix issues in the OpenAPI document.

## 6. Try It Out Is Not Authorization

Swagger UI can send requests directly from the browser. Two commonly used property groups:

~~~yaml
springdoc:
  swagger-ui:
    try-it-out-enabled: true
    supported-submit-methods:
      - get
      - post
      - put
    persist-authorization: false
~~~

- `try-it-out-enabled` controls the default expanded state of the Try it out area.
- `supported-submit-methods` specifies which HTTP methods the UI allows sending as test requests.
- An empty `supported-submit-methods` list disables Try it out for all operations without removing operations from the UI.
- `persist-authorization` determines whether Swagger UI preserves authorization data across browser refreshes/restarts.

These properties only control the browser UI. They do not alter server endpoints, do not block users from calling the API via `curl`/Postman, and do not replace Spring Security. To forbid `POST` in production, enforce it on the server or gateway.

## 7. Swagger UI OAuth Configuration and the Security Contract

There are two authentication-related layers with different goals:

1. **OpenAPI security definition** describes the scheme and which operations require that scheme.
2. **Swagger UI OAuth configuration** helps the browser execute the login flow to test the API.

Example defining a Bearer scheme in OpenAPI:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiSecurityDocumentation {

    @Bean
    OpenAPI securedApi() {
        return new OpenAPI()
                .info(new Info()
                        .title("Secured Catalog API")
                        .version("1.4.0"))
                .components(new Components()
                        .addSecuritySchemes(
                                "bearerAuth",
                                new SecurityScheme()
                                        .type(SecurityScheme.Type.HTTP)
                                        .scheme("bearer")
                                        .bearerFormat("JWT")
                        ));
    }
}
~~~

An operation can reference the scheme via `SecurityRequirement` or a security requirement in the OpenAPI model. The JSON/YAML will then contain `components.securitySchemes` and the corresponding `security`. If the application already has an `OpenAPI` bean declaring title/version/server, add the security scheme to that same bean instead of creating two competing `OpenAPI` beans.

Swagger UI can be configured to support OAuth:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: catalog-docs
      use-pkce-with-authorization-code-grant: true
    oauth2-redirect-url: https://api.example.com/docs/oauth2-redirect.html
~~~

Only declare the client ID and flow settings appropriate for the identity provider. Never put `springdoc.swagger-ui.oauth.client-secret` in production because this value is sent to the browser and can be inspected by users. For public clients, use Authorization Code + PKCE when supported by the identity provider.

OAuth UI configuration does not create a security scheme in OpenAPI if no scheme has been defined yet. Conversely, a security scheme in OpenAPI does not configure the identity provider or issue tokens to the browser on its own.

## 8. Configuring Swagger UI with Java

When configuration via `application.yml` is not enough, Springdoc allows providing a `SwaggerUiConfigProperties` bean. The project FAQ illustrates using a `@Primary` bean to modify UI properties:

~~~java
import org.springdoc.core.properties.SwaggerUiConfigProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration
class SwaggerUiConfiguration {

    @Bean
    @Primary
    SwaggerUiConfigProperties swaggerUiConfig(
            SwaggerUiConfigProperties config) {
        config.setShowCommonExtensions(true);
        return config;
    }
}
~~~

This is configuration for Swagger UI. If you need to adjust the OpenAPI model, use an `OpenAPI` bean, `OpenApiCustomizer`, or `OperationCustomizer` accordingly.

Avoid configuring the same value in multiple places without clear precedence rules. If `application.yml` sets `doc-expansion: full` while a Java bean writes `none`, check the actual value in the config document loaded by the UI.

## 9. config-url and Swagger UI Configuration Precedence

Swagger UI can receive configuration from:

- The object passed when initializing Swagger UI.
- The document fetched via `configUrl`.
- Query parameters in the URL.

According to Swagger UI documentation, the config document loaded from `configUrl` takes precedence over the initialization config object; query parameters have the highest precedence. However, Springdoc disables overriding configuration via query parameters by default. The `springdoc.swagger-ui.query-config-enabled` property has been disabled by default since v1.6.0 for security reasons.

If deploying an external config document yourself:

1. Ensure the config URL returns JSON with the structure Swagger UI expects.
2. Ensure the OpenAPI document URL is present in `url` or `urls` of the config.
3. Ensure the browser can access both the config and the OpenAPI document.
4. Configure CORS if the URLs are on different origins.
5. Inspect DevTools Network to see which config the UI loads and which values are applied.

Do not use query strings to alter sensitive Swagger UI settings in production. Keep query config disabled unless there is a clear reason and a security advisory review has been performed.

## 10. Disabling the UI and Disabling the OpenAPI Document Are Two Different Things

| Property | Effect |
|---|---|
| springdoc.api-docs.enabled=false | Disables the OpenAPI document endpoint generated by Springdoc. |
| springdoc.swagger-ui.enabled=false | Disables the Swagger UI page. |

A deployment may disable Swagger UI while still serving OpenAPI JSON/YAML for CI or an API catalog. Conversely, the UI may be enabled to display an external OpenAPI file in special configurations, provided the document source and UI configuration are fully set up.

Do not treat hiding Swagger UI as an API protection measure. The `/v3/api-docs` endpoint and business APIs still require proper authorization. If documentation is internal-only, control access at Spring Security or the reverse proxy.

## 11. Verifying the Right Configuration Layer

After changing configuration, check both server output and the browser UI.

### 11.1. Verifying the OpenAPI Document

Example:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o build/openapi.json
~~~

Verify:

- `openapi` and `info` have the expected values.
- `paths` contains only the selected endpoints.
- `components.schemas`, security schemes, and responses are accurate.
- The API docs endpoint is at the configured path.

If changing `springdoc.paths-to-match`, `springdoc.paths-to-exclude`, `api-docs.version`, or customizers, the result should be reflected in JSON/YAML.

### 11.2. Verifying the Swagger UI Config Document

With default configuration:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/swagger-config
~~~

Check:

- `url` or `urls` points to the right OpenAPI document.
- `urlsPrimaryName` matches an entry when using a list of multiple documents.
- `oauth2RedirectUrl` has the right public URL if OAuth is used.
- UI properties such as `docExpansion`, `filter`, and `supportedSubmitMethods` are included in the config when applicable.

If `swagger-config` is right yet the UI page does not update, check browser cache, static resource versions, and DevTools Network.

### 11.3. Testing Both Endpoints with MockMvc

An integration test can confirm that both the OpenAPI document and Swagger UI config are served:

~~~java
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
class DocumentationConfigurationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void servesOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.openapi").exists())
                .andExpect(jsonPath("$.paths").exists());
    }

    @Test
    void servesSwaggerUiConfiguration() throws Exception {
        mockMvc.perform(get("/v3/api-docs/swagger-config"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.url").value("/v3/api-docs"));
    }
}
~~~

The example assumes documentation endpoints are accessible in tests. If Spring Security protects these endpoints, add appropriate authentication to the test requests; do not change production policy just to make tests pass.

If the application changes `api-docs.path` or uses `urls` for multiple documents, adjust the endpoints and assertions to match the chosen configuration. JSON tests do not replace browser tests: you still need to check JavaScript/CSS, redirects, CORS, and Try it out behavior.

### 11.4. Checking the UI Page

Open `/swagger-ui.html` or the configured custom path and verify:

- The UI loads JavaScript/CSS successfully.
- The UI fetches the right `swagger-config`.
- The UI fetches the right OpenAPI JSON/YAML.
- Layout, sorting, filtering, and expansion behave as expected.
- Try it out is enabled only for the configured methods.
- Authorization flow uses the right redirect URL and identity provider.

A UI that renders successfully does not prove the OpenAPI schema is accurate. Conversely, valid OpenAPI JSON does not guarantee Swagger UI can load the file or render properly when the config URL, CORS, or static resources are misconfigured.

## 12. Common Mistakes

Property lists vary by Springdoc branch and the bundled Swagger UI version. Spring Boot 3 projects use Springdoc v2 documentation; Spring Boot 4 uses the current branch documentation. When a property is not recognized, check the matching documentation branch and bundled Swagger UI version instead of assuming all versions share the same option set.

- **Using `springdoc.paths-to-match` to sort operations**: this property filters endpoints in the document; use `operations-sorter` for the UI.
- **Using `doc-expansion` to remove operations from OpenAPI**: this property only changes UI expansion behavior.
- **Confusing `api-docs.path` with `swagger-ui.path`**: one path is the OpenAPI document, the other is the HTML page.
- **Confusing `config-url` with `url`**: `config-url` returns UI configuration; `url` points to the OpenAPI document.
- **Customizing OpenAPI with `SwaggerUiConfigProperties`**: use an `OpenAPI` bean/customizer for schemas, paths, and security definitions.
- **Customizing the UI with an `OpenAPI` bean**: use `springdoc.swagger-ui.*` or Swagger UI configuration.
- **Disabling `api-docs.enabled` while still expecting the UI to read the internal document**: the UI needs a valid spec source.
- **Disabling `swagger-ui.enabled` and thinking API docs are disabled too**: the two properties control two different endpoints.
- **Treating `supported-submit-methods` as authorization**: users can still call the API outside Swagger UI.
- **Exposing OAuth client secret to the browser**: secrets can be leaked; use a public client and PKCE when appropriate.
- **Enabling query config override without security review**: keep `queryConfigEnabled` disabled by default.
- **Changing `config-url` and forgetting CORS**: the browser may block fetching config from another origin.
- **Checking only the HTML page**: you must check both JSON/YAML and `swagger-config`.
- **Assuming UI `filter` is an API filter**: the UI filter only hides displayed items visually.

## 13. Configuration Selection Workflow

1. **Identify the goal**: changing contract content or the documentation viewing experience.
2. **Choose the Springdoc core layer** if you need to filter controllers/paths, change the OpenAPI version, or adjust schemas.
3. **Choose an `OpenAPI` bean/customizer** if you need to add metadata, servers, security schemes, or operation details.
4. **Choose Swagger UI properties** if you need to change layout, sorting, expansion, filtering, or Try it out.
5. **Choose `url`/`urls`** if you want the UI to load one or multiple OpenAPI documents.
6. **Choose `config-url`** if you want the UI to load the configuration document from a separate endpoint.
7. **Configure OAuth UI** while keeping secrets server-side and using PKCE for public clients when appropriate.
8. **Protect API docs and UI** with security policies; do not rely on hiding the page.
9. **Check OpenAPI JSON/YAML and `swagger-config`** after making changes.
10. **Check browser runtime** to confirm the UI loads the right document, assets, and request behavior.

## 14. Review Checklist

- [ ] Distinguished Springdoc core properties from Swagger UI properties.
- [ ] `api-docs.path` and `swagger-ui.path` are used for their intended purposes.
- [ ] `paths-to-match`/`packages-to-scan` only filter OpenAPI content.
- [ ] `OpenAPI` bean/customizers are used to change the contract.
- [ ] `url` or `urls` points to the OpenAPI document.
- [ ] `config-url` points to the UI configuration JSON.
- [ ] UI sorting, filtering, and expansion are not mistaken for contract changes.
- [ ] Try it out settings are not treated as server-side authorization.
- [ ] OAuth client secret is not sent to production browsers.
- [ ] Query config override remains disabled unless justified and security-reviewed.
- [ ] CORS is configured if the UI fetches spec/config from another origin.
- [ ] `api-docs.enabled` and `swagger-ui.enabled` are managed separately.
- [ ] CI checks OpenAPI JSON/YAML and `swagger-config`.
- [ ] Browser tests confirm the UI loads the right document and assets.

## 15. References

- [springdoc-openapi – Core and UI configuration properties](https://springdoc.org/properties.html)
- [springdoc-openapi – Swagger UI properties reference](https://springdoc.org/ui-properties.html)
- [springdoc-openapi v2 – FAQ for Spring Boot 3](https://springdoc.org/v2/faq.html)
- [springdoc-openapi – Getting Started](https://springdoc.org/getting-started.html)
- [Swagger UI – Configuration reference](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Swagger UI – OAuth 2.0 configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/oauth2/)
- [OpenAPI Specification](https://spec.openapis.org/oas/)

Springdoc determines which contract is generated and what that contract contains; Swagger UI determines how users see and interact with the documentation. Use core properties and OpenAPI customizers for the document, use `springdoc.swagger-ui.*` for the UI, distinguish `url` from `config-url`, and inspect OpenAPI JSON/YAML, `swagger-config`, and browser runtime separately. This layering avoids editing the wrong place and maintains a clear boundary between API documentation, presentation tools, and real endpoint security.
