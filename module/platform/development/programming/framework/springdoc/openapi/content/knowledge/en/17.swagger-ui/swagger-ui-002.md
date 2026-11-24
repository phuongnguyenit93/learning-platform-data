# UI Paths, Static Resources, and swagger-config

Swagger UI in a Spring Boot application is more than a single HTML page. Springdoc serves an entry point to open the interface, static resources such as JavaScript/CSS, a configuration endpoint for Swagger UI, and one or more OpenAPI documents. These components each have their own URLs and responsibilities.

When you need to change the Swagger UI path, replace logos/styles, move API docs to a separate path, configure OAuth redirects, or troubleshoot UI loading errors, you need to identify the exact component being changed. Changing the HTML URL does not automatically move JavaScript/CSS files; changing the OpenAPI URL does not automatically change the config URL; replacing static files does not modify OpenAPI content either.

This lesson focuses on how Springdoc connects these parts, how to configure them in application.yml, how to customize UI resources, and how to verify actual routes in Spring MVC/WebFlux.

## 1. The four components that make up Swagger UI

In a standard setup, there are four resource groups:

| Component | Default URL example | Role |
| --- | --- | --- |
| Entry point HTML | /swagger-ui.html | URL users open to enter the interface |
| Static resources | /swagger-ui/** | JavaScript, CSS, favicon, index, and UI files |
| Swagger UI configuration | /v3/api-docs/swagger-config | Provides document URLs and UI configuration |
| OpenAPI document | /v3/api-docs, /v3/api-docs.yaml | JSON/YAML API specification displayed by the UI |

Execution flow:

~~~text
Browser
   |
   | GET /swagger-ui.html
   v
Springdoc welcome endpoint
   |
   | redirect/forward to Swagger UI index
   v
/swagger-ui/index.html
   |
   | GET /swagger-ui/swagger-ui.css
   | GET /swagger-ui/swagger-ui-bundle.js
   | GET /swagger-ui/swagger-initializer.js
   v
Swagger UI assets
   |
   | GET /v3/api-docs/swagger-config
   v
Swagger UI configuration
   |
   | GET /v3/api-docs or /v3/api-docs/{group}
   v
OpenAPI document
   |
   v
Render API operations and schemas
~~~

This is a logical diagram. Exact asset paths and redirect/forward behavior may differ by Swagger UI version, Springdoc version, context path, and deployment configuration. When verification is needed, use the Network tab to inspect actual requests.

## 2. Which dependency provides Swagger UI?

With Spring Boot 3 and Spring MVC, the common starter is:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

With Spring WebFlux, choose the corresponding starter:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

The example uses Springdoc 2.10.0 for a compatible Spring Boot 3 branch. Choose the version according to your project's compatibility matrix rather than copying this version across all Boot branches.

The UI starter packages the official Swagger UI integration and automatically registers the required resources and endpoints. Normally there is no need to manually add swagger-ui-dist or copy JavaScript/CSS into the project.

If only OpenAPI JSON/YAML is needed without the UI, use the appropriate API-only starter. Avoid adding the UI starter solely to generate documents if the application does not need to serve Swagger UI.

## 3. Default paths

For an application without a context path or proxy prefix:

| Resource | URL |
| --- | --- |
| Swagger UI entry point | /swagger-ui.html |
| Swagger UI index | /swagger-ui/index.html |
| OpenAPI JSON | /v3/api-docs |
| OpenAPI YAML | /v3/api-docs.yaml |
| Swagger UI config | /v3/api-docs/swagger-config |

For example, when the application runs at localhost:8080:

~~~text
http://localhost:8080/swagger-ui.html
http://localhost:8080/swagger-ui/index.html
http://localhost:8080/v3/api-docs/swagger-config
http://localhost:8080/v3/api-docs
http://localhost:8080/v3/api-docs.yaml
~~~

The first two HTML URLs may go through a redirect or welcome handler depending on the version. The first URL is the friendly entry point advertised by Springdoc; the second URL helps inspect the index resource directly.

## 4. Changing the HTML path with springdoc.swagger-ui.path

The springdoc.swagger-ui.path property changes the UI entry point URL:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs/api.html
~~~

Users open:

~~~text
http://localhost:8080/docs/api.html
~~~

This property adjusts the HTML/welcome endpoint. It does not change the API docs path and does not mean all JavaScript/CSS resources are moved into the /docs directory.

Assets are still served by Swagger UI's resource handler. Therefore, when configuring a custom path, inspect both the entry point and asset requests in the Network tab.

## 5. Changing the API docs path independently of the UI path

The OpenAPI document has its own property:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs/api.html
~~~

In this configuration:

- The interface opens at /docs/api.html.
- OpenAPI JSON is served at /openapi.
- OpenAPI YAML is typically served at /openapi.yaml.
- Swagger UI config is served under the API docs base path, for example /openapi/swagger-config.

Do not use springdoc.swagger-ui.path to change the JSON URL. Also do not use springdoc.api-docs.path to change the HTML URL.

After changing paths, open the document and config endpoints directly to confirm they actually work. If the UI fails to load the document, check the source configuration in swagger-config before changing additional properties.

## 6. Complete configuration in application.yml

Example configuration for a single document:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /openapi
  swagger-ui:
    enabled: true
    path: /docs/api.html
    url: /openapi
    disable-swagger-default-url: true
    try-it-out-enabled: true
    display-request-duration: true
    deep-linking: true
~~~

Meaning:

- api-docs.enabled enables the OpenAPI endpoint.
- api-docs.path changes the base path of the JSON/YAML and config endpoints.
- swagger-ui.enabled enables the UI.
- swagger-ui.path changes the HTML entry point.
- swagger-ui.url specifies a single document for the UI to load.
- disable-swagger-default-url disables the sample Petstore URL.
- try-it-out-enabled enables Try it out by default.
- display-request-duration displays test request duration.
- deep-linking enables direct links to tags/operations.

Properties used in YAML follow Spring Boot relaxed binding. Documentation tables may write names in camelCase; in application.yml, use kebab-case consistently.

## 7. Table of key properties

| Property | Default | Purpose |
| --- | --- | --- |
| springdoc.swagger-ui.path | /swagger-ui.html | HTML entry point |
| springdoc.swagger-ui.enabled | true | Enable/disable Swagger UI |
| springdoc.swagger-ui.config-url | /v3/api-docs/swagger-config | URL to fetch UI configuration |
| springdoc.swagger-ui.url | Not set | A single custom OpenAPI document |
| springdoc.swagger-ui.urls | Not set | List of multiple documents/groups |
| springdoc.swagger-ui.urls-primary-name | Not set | Default document in the list |
| springdoc.swagger-ui.oauth2-redirect-url | /swagger-ui/oauth2-redirect.html | OAuth2 callback |
| springdoc.swagger-ui.disable-swagger-default-url | false | Disable sample Petstore URL |
| springdoc.api-docs.path | /v3/api-docs | Base path of the OpenAPI document |
| springdoc.api-docs.enabled | true | Enable/disable API docs endpoint |

These are properties for configuring URLs and UI loading behavior. Swagger UI has many other properties for layout, filtering, sorting, expansion, OAuth, and CSRF; configure only what is needed to avoid unpredictable behavior.

## 8. What is swagger-config?

Swagger UI needs to know which document to load and which options to apply. Springdoc provides a configuration endpoint, by default:

~~~text
/v3/api-docs/swagger-config
~~~

This endpoint returns configuration JSON. Abbreviated example:

~~~json
{
  "configUrl": "/v3/api-docs/swagger-config",
  "url": "/v3/api-docs",
  "validatorUrl": ""
}
~~~

The actual response may include additional fields for OAuth, URLs, layout, filtering, deep linking, or other properties. Do not rely on the abbreviated example to assume the entire configuration JSON.

swagger-config is not an OpenAPI document. It is configuration for the UI. The OpenAPI document is what contains info, paths, components, security schemes, and API schemas.

## 9. Distinguishing config-url, url, and urls

The three properties play different roles:

| Property | Question answered |
| --- | --- |
| config-url | Where does Swagger UI get its configuration file? |
| url | Which single OpenAPI document does Swagger UI load? |
| urls | Which documents does Swagger UI let users choose from? |

Example:

~~~yaml
springdoc:
  swagger-ui:
    config-url: /v3/api-docs/swagger-config
    url: /v3/api-docs
~~~

If config-url points to an external configuration file, that file must exist and return valid configuration JSON for Swagger UI. Springdoc does not automatically generate an arbitrary file on another server.

The url property is used for a single document. If urls is declared, the urls list takes precedence and the single url is ignored according to Springdoc's Swagger UI configuration.

## 10. Using a static OpenAPI document instead of a dynamically generated one

Swagger UI can load a static OpenAPI file placed in Spring Boot's static resources:

~~~text
src/
  main/
    resources/
      static/
        specs/
          public-api.yaml
~~~

Configuration:

~~~yaml
springdoc:
  swagger-ui:
    url: /specs/public-api.yaml
    disable-swagger-default-url: true
~~~

The UI then reads the static file public-api.yaml. The /v3/api-docs endpoint may still exist, but it is not necessarily the source the UI is using.

This scenario is useful when:

- The document is built by another pipeline.
- The API contract is managed independently of the runtime application.
- You want to display documentation for another service.
- You want to publish an approved OpenAPI snapshot.

The drawback is that static files do not automatically update when controllers change. The pipeline must take responsibility for generating, validating, and replacing the file with the right version.

## 11. Loading multiple documents with urls

When the application has multiple API groups, configure a list:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Partner API
        url: /v3/api-docs/partner
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Public API
~~~

Swagger UI displays a selection dropdown on the Topbar. Names and URLs in the list must be unique because Swagger UI uses them as identifiers.

These URLs must be generated by Springdoc or point to existing static documents. Merely adding an entry to urls does not automatically create an OpenAPI group.

## 12. Registering groups in Springdoc

Example of declaring groups in Java:

~~~java
@Configuration
public class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner")
            .pathsToMatch("/api/partner/**")
            .build();
    }
}
~~~

The corresponding documents typically have paths:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
~~~

The group name in the URL must match the declared group. If the UI displays the name Public API while the URL points to /v3/api-docs/public-v2 when the bean name is public, the document may return 404.

## 13. Declaring groups with application.yml

You can use group-configs:

~~~yaml
springdoc:
  group-configs:
    - group: public
      display-name: Public API
      paths-to-match:
        - /api/public/**
    - group: partner
      display-name: Partner API
      paths-to-match:
        - /api/partner/**
~~~

The group URLs are then generated by name:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
~~~

Do not declare the same group using both a Java bean and group-configs without clear intent. Avoid duplicate group names or overlapping path filters that produce confusing documentation.

## 14. OAuth2 redirect resource

Swagger UI uses a callback page to complete the OAuth2 authorization flow. Corresponding property:

~~~yaml
springdoc:
  swagger-ui:
    oauth2-redirect-url: https://api.example.com/swagger-ui/oauth2-redirect.html
~~~

The default value is typically /swagger-ui/oauth2-redirect.html. If the UI is served under a context path or reverse proxy prefix, the callback URL must reflect the URL reachable by the browser.

When OAuth2 redirect fails, check:

- The callback URL in UI configuration.
- The redirect URI registered at the Identity Provider.
- The HTTPS/HTTP scheme.
- Host, port, and context path.
- Proxy prefix.
- Whether CSP or browser policies block the callback.

Do not embed a client secret in Swagger UI configuration running on production browsers. A client secret sent down to the browser is no longer a secret.

## 15. Where do static resources live in the application?

Springdoc uses a Swagger UI WebJar. The original resources are packaged in the classpath with the structure:

~~~text
META-INF/
  resources/
    webjars/
      swagger-ui/
        {swagger.version}/
          index.html
          swagger-ui-bundle.js
          swagger-ui.css
          swagger-ui-standalone-preset.js
          favicon-32x32.png
          ...
~~~

This is the resource location inside the dependency, not a source directory the application needs to create manually. Springdoc/Spring resource handling serves them through the corresponding web URLs.

Commonly encountered resources:

| File | Role |
| --- | --- |
| index.html | Swagger UI initialization page |
| swagger-ui-bundle.js | Main JavaScript bundle |
| swagger-ui-standalone-preset.js | Standalone UI preset |
| swagger-ui.css | UI stylesheet |
| favicon-32x32.png | Favicon |
| swagger-initializer.js | Initializes UI configuration, depending on packaging/version |

Do not directly edit files inside a dependency JAR. Changes inside a JAR are lost when dependencies are updated and are hard to reproduce across environments.

## 16. Static resource URL and classpath location are not the same

A resource may reside in a WebJar yet be exposed under a URL mapped by Springdoc. For example, the browser may request:

~~~text
/swagger-ui/swagger-ui.css
/swagger-ui/swagger-ui-bundle.js
/swagger-ui/index.html
~~~

Meanwhile, the underlying resource resides under META-INF/resources/webjars/swagger-ui/{version}/ on the classpath.

Therefore, when debugging:

- Use the URL in the Network tab to inspect requests from the browser.
- Use the classpath location to understand where the resource is packaged.
- Use a Spring resource handler/transformer for customization.

Do not infer the public URL simply by appending the raw classpath path onto the host.

## 17. Avoiding conflicts with the application's static index.html

Spring Boot can serve a welcome page from static/index.html or public/index.html. If the application already has its own home page, a Swagger UI entry point at the root can cause conflicts or change the default page.

Springdoc recommends placing the UI at a separate path:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs/swagger.html
~~~

Example:

- Application home page: /
- Swagger UI: /docs/swagger.html
- OpenAPI JSON: /v3/api-docs

Separating the paths prevents the UI's default route from competing with the application's welcome page.

## 18. Using swagger-ui.use-root-path

Springdoc has the property:

~~~yaml
springdoc:
  swagger-ui:
    use-root-path: true
~~~

This property enables Swagger UI to be accessed directly at the application's root path. Only enable it when the application truly intends to dedicate the root to the UI.

If the application already has a home page or static index.html, check for conflicts before enabling it. A custom path can be chosen instead to preserve the home page.

Do not confuse use-root-path with server.servlet.context-path. One property controls the UI's location within the application; the other sets a prefix for the entire MVC application.

## 19. Preserving Spring Boot's static resource configuration

Spring Boot automatically serves static resources from default locations such as:

- classpath:/static/
- classpath:/public/
- classpath:/resources/
- classpath:/META-INF/resources/

If you define a custom WebMvcConfigurer or ResourceHandlerRegistry, verify whether the configuration replaces the default mappings.

Example of an overly broad configuration:

~~~java
@Configuration
public class StaticResourceConfiguration implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/**")
            .addResourceLocations("classpath:/custom-static/");
    }
}
~~~

The /** handler may intercept the URLs Swagger UI needs, depending on ordering and resource handler setup. When assets return 404 or HTML instead of JavaScript/CSS, review custom resource handlers before swapping dependencies.

If you only need to add a separate static folder, use a narrow pattern:

~~~java
registry.addResourceHandler("/assets/**")
    .addResourceLocations("classpath:/custom-assets/");
~~~

Do not register an overly broad handler without clearly understanding Spring MVC's mapping order and fallback behavior.

## 20. Customizing the interface with Swagger UI properties

Many changes do not require editing static files. They can be configured via properties:

~~~yaml
springdoc:
  swagger-ui:
    doc-expansion: none
    operations-sorter: alpha
    tags-sorter: alpha
    display-operation-id: true
    display-request-duration: true
    default-models-expand-depth: 1
    default-model-expand-depth: 1
    filter: true
    deep-linking: true
    try-it-out-enabled: true
~~~

Selected options:

| Property | Effect |
| --- | --- |
| doc-expansion | Default expansion level for tags/operations |
| operations-sorter | Sort operations by path or HTTP method |
| tags-sorter | Sort tags |
| display-operation-id | Display operationId |
| display-request-duration | Display request duration |
| default-models-expand-depth | Models expansion depth |
| filter | Enable the operation filter box |
| deep-linking | Create URLs linking directly to operations/tags |
| try-it-out-enabled | Enable Try it out by default |

These properties change UI behavior, not the OpenAPI schema. To modify request/response contracts, update controllers/DTOs/annotations or an OpenAPI customizer.

## 21. Restricting HTTP methods allowed for Try it out

You can configure which methods the UI allows testing:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - post
      - put
      - patch
      - delete
~~~

If the list is empty, Try it out is disabled for all operations while operations remain displayed.

This is a UI restriction, not an API protection policy. Users can still call endpoints using curl, Postman, or other HTTP clients. The server must enforce authentication and authorization itself.

## 22. Persist authorization and storing tokens in the browser

Swagger UI has the persist-authorization property to retain authentication info across browser refreshes/closures:

~~~yaml
springdoc:
  swagger-ui:
    persist-authorization: false
~~~

By default, persistence should not be enabled without a clear requirement. If enabled, tokens may continue to exist in browser storage/session according to the UI's mechanism, increasing risk on shared machines.

Do not put real tokens into URLs, query parameters, source code, or OpenAPI files. Use the Authorize mechanism and security policies suited to the environment.

## 23. Configuring validatorUrl

Swagger UI does not have to call a remote validation service by default. The validator-url property lets you specify a validator:

~~~yaml
springdoc:
  swagger-ui:
    validator-url: ""
~~~

If the organization runs an internal validator, you can set the corresponding URL. If using an external validator, check whether the document contains internal details and review policies on sending data externally.

The validator checks the validity of the OpenAPI document; it does not verify that runtime endpoints work properly or that the server conforms to the full contract.

## 24. Disabling Swagger UI and API docs independently

Disabling the UI:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
~~~

Disabling API docs:

~~~yaml
springdoc:
  api-docs:
    enabled: false
~~~

The two settings are independent:

- Disable the UI while keeping API docs so pipelines or clients can fetch JSON/YAML.
- Disabling API docs prevents the UI from loading the application-generated document unless configured to use another document.
- Disable both in environments where documentation is not published.

Disabling Swagger UI does not block business APIs. Protect endpoints with Spring Security or a gateway.

## 25. Swagger UI on the Actuator management port

In some architectures, the UI can be exposed via the management port:

~~~yaml
springdoc:
  use-management-port: true

management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: openapi, swagger-ui
~~~

When this feature is enabled, endpoints may be exposed under the management base path depending on Actuator configuration and Springdoc version.

The management port is typically an internal administrative surface. Configure proper network policies, authentication, and authorization; do not open the management port to the internet just for convenient access to Swagger UI.

## 26. Customizing static resources with SwaggerIndexPageTransformer

When properties are insufficient to customize HTML/CSS/JavaScript, Springdoc provides an extension point to transform Swagger UI resources. Springdoc documentation describes WebJar resources and extending SwaggerIndexPageTransformer.

The transformer example below is based on Springdoc v2's extension point for Spring MVC because the signature uses HttpServletRequest. For WebFlux, use the corresponding request/resource types of the reactive stack.

A transformer can:

- Read the original Resource.
- Check the resource type.
- Produce transformed content.
- Return a TransformedResource.
- Call super.transform for resources that do not need changes.

Abbreviated logic example for a resource:

~~~java
public Resource transform(
        HttpServletRequest request,
        Resource resource,
        ResourceTransformerChain chain) throws IOException {

    if (resource.toString().contains("swagger-ui.css")) {
        try (InputStream input = resource.getInputStream()) {
            String css = new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
            );

            String customized = css.replace(
                "old-value",
                "new-value"
            );

            return new TransformedResource(
                resource,
                customized.getBytes(StandardCharsets.UTF_8)
            );
        }
    }

    return super.transform(request, resource, chain);
}
~~~

This is an illustrative body for the extension point, not a complete standalone compilable class. An actual transformer class must extend SwaggerIndexPageTransformer, invoke the constructor matching the Springdoc version in use, and register a SwaggerIndexTransformer bean. Constructor signatures can change between versions.

Transform only the exact resource that needs modification. Do not load entire JavaScript/CSS files into memory and perform arbitrary string replacements if a small theme file or simpler configuration mechanism can be used.

## 27. Registering the transformer bean

In the Springdoc v2 model, official documentation illustrates a SwaggerIndexTransformer bean:

~~~java
@Configuration
public class SwaggerUiResourceConfiguration {

    @Bean
    SwaggerIndexTransformer swaggerIndexTransformer(
            SwaggerUiConfigProperties uiProperties,
            SwaggerUiOAuthProperties oauthProperties,
            SwaggerUiConfigParameters configParameters,
            SwaggerWelcomeCommon welcome) {

        return new BrandSwaggerIndexTransformer(
            uiProperties,
            oauthProperties,
            configParameters,
            welcome
        );
    }
}
~~~

BrandSwaggerIndexTransformer is an application-implemented class extending the corresponding transformer. The constructor must pass the required dependencies to the superclass according to the API of the Springdoc version managed in the project.

Because this extension point sits close to Swagger UI's internal integration, re-check the signature when upgrading Springdoc. Do not copy a transformer class from an older major version to a new version without compiling and testing the UI.

## 28. Avoiding edits to files in dependency JARs

Do not:

- Extract the WebJar and edit swagger-ui-bundle.js directly.
- Edit index.html inside the JAR in the local Maven/Gradle cache.
- Copy all static assets into the project without a version-synchronization process.
- Override all resource paths with a /** handler.

These approaches create an unmanaged fork. When Springdoc upgrades Swagger UI, old files may no longer be compatible with the new initializer or resource structure.

Prioritize in this order:

1. Use official properties.
2. Use a static OpenAPI file or custom URL if only the document source needs to change.
3. Use the transformer extension point when resources need modification.
4. Maintain a custom UI build only when there is a clear product requirement and tests run after every dependency upgrade.

## 29. Security filters must allow the right required resources

When using Spring Security, Swagger UI may need access to:

- Entry point HTML.
- /swagger-ui/** static assets.
- swagger-config endpoint.
- OpenAPI JSON/YAML.
- OAuth2 redirect page.
- Group documents if multiple API groups are used.

Example for a development environment:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        "/swagger-ui.html",
        "/swagger-ui/**",
        "/v3/api-docs/**"
    ).permitAll()
    .anyRequest().authenticated()
);
~~~

If docs need protection, replace permitAll with appropriate roles/scopes for the entire URL group. Do not open only the HTML while blocking CSS/JS/config/document, as the UI will load the page but fail to render the API.

Do not treat hiding Swagger UI as protecting business endpoints. The security filter chain must still check all routes according to application policy.

## 30. Context path and custom path

If the application has a context path:

~~~yaml
server:
  servlet:
    context-path: /catalog
springdoc:
  swagger-ui:
    path: /docs/api.html
  api-docs:
    path: /openapi
~~~

Public URLs may be:

~~~text
/catalog/docs/api.html
/catalog/openapi
/catalog/openapi.yaml
/catalog/openapi/swagger-config
~~~

The context path is the common prefix of the application. springdoc.swagger-ui.path and springdoc.api-docs.path are paths within the application context. Avoid adding /catalog to both the context path and the property paths, otherwise URLs may get duplicated prefixes.

## 31. Reverse proxy and external prefixes

The application may run internally at:

~~~text
http://service:8080
~~~

While users access:

~~~text
https://api.example.com/catalog
~~~

A reverse proxy may terminate TLS and add a prefix. When the proxy does not forward headers properly, Swagger UI may generate absolute URLs pointing to the internal host or missing the prefix.

Check:

- Forwarded or X-Forwarded-Proto.
- X-Forwarded-Host.
- X-Forwarded-Port.
- X-Forwarded-Prefix if the proxy adds a path prefix.
- Spring Boot's server.forward-headers-strategy.
- Absolute URLs in swagger-config and OpenAPI servers.

Only trust forwarded headers coming from trusted proxies. Do not let internet clients dictate the host/protocol the application uses to generate URLs.

## 32. Inspecting static assets with Browser Network

When the interface fails, open DevTools:

1. Open the Swagger UI page.
2. Press F12 and select Network.
3. Reload the page.
4. Filter by swagger-ui, css, js, favicon, or api-docs.
5. Inspect Status, Request URL, Content-Type, and Response.

Some symptoms:

| Request | Common error | Where to inspect |
| --- | --- | --- |
| /swagger-ui.html | 404 | Custom path, context path, UI starter |
| /swagger-ui/index.html | 404 | Static resource mapping, web stack, custom handler |
| swagger-ui.css | 404 | Overridden resource handler or static path |
| swagger-ui-bundle.js | 404 | WebJar dependency/resource path |
| swagger-config | 401/403 | Spring Security or gateway |
| OpenAPI document | 404 | api-docs.path, group, enabled |
| oauth2-redirect.html | 404 | OAuth redirect URL, prefix, or security |

If HTML returns 200 but JavaScript/CSS return 404, the bug lies in the static resource path or handler, not the OpenAPI schema.

## 33. Checking Content-Type of static resources

Browsers need the right content type:

- CSS must have an appropriate Content-Type such as text/css.
- JavaScript must have a JavaScript MIME type.
- HTML must be served as text/html.
- OpenAPI JSON must be parseable as JSON.

If the server returns an HTML login page for a JavaScript request, the browser may report a MIME type error or JavaScript syntax error. Check the response body and status rather than looking only at Console messages.

If a resource is returned with Content-Type text/html or application/octet-stream, review custom ResourceHandlers, gateway rewrites, and MIME/static resource settings.

## 34. Conflicts with custom index.html

If the application has a home page at:

~~~text
src/main/resources/static/index.html
~~~

Swagger UI or the welcome handler may create a route conflict depending on configuration. Use a dedicated path:

~~~yaml
springdoc:
  swagger-ui:
    path: /developer/swagger.html
~~~

Then keep:

- / for the application home page.
- /developer/swagger.html for Swagger UI.
- /v3/api-docs for the OpenAPI document.

Verify the responses of the root URL and custom UI URL after packaging the application, not just when running in an IDE.

## 35. Testing entry point and static resources with MockMvc

You can write integration tests for key routes:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SwaggerUiResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void servesSwaggerUiIndex() throws Exception {
        mockMvc.perform(get("/swagger-ui/index.html"))
            .andExpect(status().isOk());
    }

    @Test
    void servesSwaggerUiStylesheet() throws Exception {
        mockMvc.perform(get("/swagger-ui/swagger-ui.css"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.valueOf("text/css")
            ));
    }

    @Test
    void servesOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ));
    }
}
~~~

This test assumes Spring MVC and default URLs. If the application uses WebFlux, use WebTestClient. If paths were changed or the Swagger UI version returns different asset URLs, adjust the test according to the observed request URLs.

## 36. Testing swagger-config

You can verify the configuration endpoint:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SwaggerUiConfigTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void servesSwaggerConfig() throws Exception {
        String json = mockMvc.perform(get("/v3/api-docs/swagger-config"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode config = objectMapper.readTree(json);

        assertThat(
            config.path("url").asText().contains("/v3/api-docs")
            || config.path("urls").isArray()
        ).isTrue();
    }
}
~~~

The test assumes a default single-document setup. If using a static document, urls, or a custom config-url, the assertion should check the application's expected source instead of hardcoding /v3/api-docs.

## 37. Diagnosing 404 errors

When a UI or resource URL returns 404, classify it first:

| Failing URL | What to investigate |
| --- | --- |
| Custom HTML path | springdoc.swagger-ui.path, enabled, context path |
| /swagger-ui/index.html | UI starter, static resource handler, web stack |
| CSS/JS | WebJar dependency, /** handler, proxy rewrite |
| swagger-config | api-docs.path, config-url, security |
| OpenAPI group | Group name, GroupedOpenApi bean, urls list |
| OAuth redirect | oauth2-redirect-url, prefix, static route |

If all of /swagger-ui/** returns 404, check the starter dependency and whether a WebMvcConfigurer configuration overrides default resource handlers.

If only a single CSS/JS file returns 404, check the exact path requested by the browser and whether the artifact contains that resource.

## 38. Diagnosing 401/403 errors

If HTML returns 200 while config or assets return 401/403:

- Check whether SecurityFilterChain protects /swagger-ui/**.
- Check whether matchers cover /v3/api-docs/swagger-config and the document URL.
- Check whether the gateway requires a session for static resources.
- Check whether a login redirect returns HTML instead of JSON/JavaScript.
- If docs are internal, ensure users have permission to fetch all required resources.

Do not open up all business APIs just to fix Swagger UI loading errors. Scope the matchers strictly to the documentation resources.

## 39. Diagnosing a blank UI or JavaScript errors

If HTML and assets return 200 yet the interface is blank:

1. Open the Console and read the first JavaScript error.
2. Check Network to see if swagger-config loaded successfully.
3. Check whether the document URL returns valid JSON/YAML.
4. Check that responses are not HTML login/error pages.
5. Check whether CSP blocks scripts/styles.
6. Check whether a custom index.html or transformer broke the initializer.
7. Check whether asset versions match the Swagger UI package.

Do not edit the OpenAPI schema when Console reports JavaScript bundle or index.html errors. Fix the UI layer first.

## 40. Diagnosing wrong URLs behind a reverse proxy

If Swagger UI opens but CSS/JS/config point to an internal host:

- Inspect request URLs in Network.
- Check context path and proxy prefix.
- Check forwarded headers.
- Check springdoc.swagger-ui.config-url if overridden.
- Check absolute URLs in swagger-ui.url or urls.
- Check oauth2-redirect-url.

If an absolute URL is configured in swagger-ui.url, verify that the URL is correct for each environment. An absolute URL can bypass the origin the browser is currently visiting.

## 41. Choosing properties or a transformer?

| Need | Appropriate approach |
| --- | --- |
| Change the URL to open Swagger UI | springdoc.swagger-ui.path |
| Change the OpenAPI JSON/YAML URL | springdoc.api-docs.path |
| Select a static OpenAPI file | springdoc.swagger-ui.url |
| Display multiple groups/documents | springdoc.swagger-ui.urls |
| Change the config endpoint | springdoc.swagger-ui.config-url |
| Change the OAuth callback | springdoc.swagger-ui.oauth2-redirect-url |
| Change sorting/display behavior | Swagger UI properties |
| Modify index/CSS/JS content at resource level | SwaggerIndexPageTransformer |
| Modify API schemas/operations | OpenAPI annotations/customizers, not static resources |

Choosing the right extension point reduces complexity and avoids unnecessary forking of Swagger UI resources.

## 42. Pre-deployment checklist

- [ ] Correct WebMVC or WebFlux UI starter selected.
- [ ] springdoc.swagger-ui.path does not conflict with the application home page.
- [ ] springdoc.api-docs.path is configured independently.
- [ ] swagger-config URL is reachable.
- [ ] url or urls point to documents that actually exist.
- [ ] Group names and group URLs match.
- [ ] Static CSS/JS assets return 200 with the right Content-Type.
- [ ] OAuth redirect URL matches host, scheme, and context path.
- [ ] Security filters permit or protect all UI/config/document resources consistently.
- [ ] No resources inside dependency JARs were modified directly.
- [ ] Custom resource handlers do not override /swagger-ui/**.
- [ ] Reverse proxy passes forwarded headers under a trusted configuration.
- [ ] No client secrets are used in production Swagger UI.
- [ ] Tests exist for UI index, assets, swagger-config, and OpenAPI document.
- [ ] Re-verified after building/deploying the actual artifact.

## Conclusion

Swagger UI consists of the entry point HTML, static assets, swagger-config, and the OpenAPI document. springdoc.swagger-ui.path adjusts the UI entry URL; springdoc.api-docs.path adjusts the document URL; config-url specifies where the UI fetches configuration; url/urls specify which documents the UI loads. CSS/JavaScript files are packaged in a WebJar and served through resource handlers.

Prioritize official configuration properties for URL changes and UI behavior. Use SwaggerIndexPageTransformer only when static resource transformation is genuinely necessary. When errors occur, pinpoint which request fails in Network, check status and Content-Type, then fix the corresponding route, resource handler, security matcher, or proxy. That keeps the UI stable across Springdoc and Swagger UI upgrades.

## References

- [Springdoc OpenAPI — Configuration Properties](https://springdoc.org/properties.html)
- [Springdoc OpenAPI v2 — Getting Started](https://springdoc.org/v2/getting-started.html)
- [Springdoc OpenAPI v2 — Swagger UI features and static resource customization](https://springdoc.org/v2/)
- [Swagger UI — Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Spring Boot — Static Content](https://docs.spring.io/spring-boot/reference/web/servlet.html)
