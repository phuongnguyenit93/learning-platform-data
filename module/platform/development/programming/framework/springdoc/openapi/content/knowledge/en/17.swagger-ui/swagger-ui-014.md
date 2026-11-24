# Extending the UI with Version-Appropriate Resources or Configuration

Swagger UI provided by springdoc-openapi can be customized at multiple levels. Configuration properties handle changing paths, selecting OpenAPI documents, arranging layout, and toggling features. When deeper UI changes are needed—such as adding CSS, JavaScript, a favicon, or modifying the initialization HTML page—you need to extend the static resources Swagger UI uses. Implementation details depend on the springdoc version, Spring Boot version, and whether the app uses Web MVC or WebFlux.

## 1. Choosing the right extension level

Before editing resources, pinpoint the exact goal:

| Need | Appropriate approach |
|---|---|
| Change the Swagger UI entry URL | `springdoc.swagger-ui.path` |
| Disable the UI while keeping OpenAPI JSON/YAML | `springdoc.swagger-ui.enabled=false` |
| Select an existing OpenAPI file | `springdoc.swagger-ui.url` |
| Allow choosing among multiple documents or groups | `springdoc.swagger-ui.urls` and `urls-primary-name` |
| Switch layout to a component provided by Swagger UI | `springdoc.swagger-ui.layout` |
| Adjust sorters, filters, expansion, and display options | Swagger UI properties under the `springdoc.swagger-ui` prefix |
| Add stylesheets, scripts, favicon, or customize HTML | Customize static resources via `SwaggerIndexPageTransformer` |
| Alter UI structure with a custom plugin | Integrate a Swagger UI plugin/layout via a customized initialization page |

There is no need to override the entire `index.html` just to change colors or add a logo. Whenever replacing the initialization page, the application must continue providing the right `swagger-config` URL, OpenAPI documents, and assets injected by springdoc. Missing the default transformation step can result in Swagger UI loading HTML without loading API definitions.

## 2. Checking Spring Boot and springdoc compatibility before extending

Classes used to customize Swagger UI resources are part of springdoc's integration layer. Artifact names, packages, and transformer signatures change across major versions. Before writing code, identify the Spring Boot version, Web MVC vs. WebFlux, and current springdoc dependency.

| Spring Boot line | Corresponding springdoc line | Common UI dependency |
|---|---|---|
| Spring Boot 2.x and legacy 1.x apps | springdoc 1.x; final open-source release is 1.8.0 | `springdoc-openapi-ui` |
| Spring Boot 3.x | springdoc 2.x | `springdoc-openapi-starter-webmvc-ui` or `springdoc-openapi-starter-webflux-ui` |
| Spring Boot 4.0.x | springdoc 3.0.x | `springdoc-openapi-starter-webmvc-ui` or `springdoc-openapi-starter-webflux-ui` |
| Spring Boot 4.1.x | springdoc 3.1.x to 3.2.x | `springdoc-openapi-starter-webmvc-ui` or `springdoc-openapi-starter-webflux-ui` |

Maven dependency example for Spring Boot 3 with Web MVC:

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
```

For WebFlux, use `springdoc-openapi-starter-webflux-ui`. If only JSON/YAML docs are needed without a UI, use the corresponding `webmvc-api` or `webflux-api` starter.

Do not add multiple major versions of springdoc simultaneously or manually pin a Swagger UI WebJar version incompatible with the starter. The starter manages the bundled Swagger UI version integrated by springdoc. When upgrading Spring Boot, consult the compatibility matrix and migration guide for the exact major version before copying old transformer code.

## 3. Configuring the UI with application.yml

springdoc's Swagger UI configuration properties use the `springdoc.swagger-ui` prefix. They can be set in YAML or properties files; Spring Boot supports relaxed binding, so YAML keys usually use kebab-case.

Example setting the UI path, choosing a built-in layout, and pointing to a static OpenAPI file:

```yaml
springdoc:
  swagger-ui:
    enabled: true
    path: /docs/swagger-ui.html
    layout: BaseLayout
    url: /openapi/store-api.yaml
    disable-swagger-default-url: true
```

In this example:

- The UI is accessed at `/docs/swagger-ui.html`.
- `BaseLayout` is Swagger UI's default layout.
- `url` points to the OpenAPI file served at `/openapi/store-api.yaml`.
- `disable-swagger-default-url` disables Swagger UI's default Petstore URL.

To serve the static YAML file, place it at `src/main/resources/static/openapi/store-api.yaml`. With Spring Boot's default static resource handling, the file is reachable at `/openapi/store-api.yaml`.

If using OpenAPI generated from controllers, there is normally no need to set `url` separately; springdoc automatically configures `/v3/api-docs`.

### Selecting multiple OpenAPI documents

When an application has multiple groups, use `urls` to show a document selection dropdown:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Public API
    disable-swagger-default-url: true
```

Names and URLs in the list must be unique. `urls` takes precedence when configured alongside `url`; therefore, do not expect a single `url` to be used when `urls` is present.

### Separating the UI endpoint from the application home page

If the application already has `src/main/resources/public/index.html` or a welcome page at the root, the Swagger UI endpoint can collide under default paths. Configure a dedicated path:

```yaml
springdoc:
  swagger-ui:
    path: /docs/swagger-ui.html
```

This keeps the existing home page intact and moves API documentation to its own URL. After changing the path, update security matchers, reverse proxy routes, and internal documentation links if applicable.

## 4. Configuring Swagger UI programmatically

When configuration depends on profiles or Java logic, you can customize `SwaggerUiConfigProperties` via a bean. The example below enables displaying common extensions in schemas:

```java
import org.springdoc.core.properties.SwaggerUiConfigProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration
class SwaggerUiPropertiesConfiguration {

    @Bean
    @Primary
    SwaggerUiConfigProperties swaggerUiConfigProperties(
        SwaggerUiConfigProperties properties
    ) {
        properties.setShowCommonExtensions(true);
        return properties;
    }
}
```

The example uses springdoc 2.x/3.x packages. In springdoc 1.x, packages for several config classes differ. Do not instantiate a fresh `SwaggerUiConfigProperties` with an empty constructor if your goal is to modify Spring Boot-bound settings; inject the existing config bean and update the desired properties.

Use a programmatic bean only when there is a clear reason such as profiles, tenant settings, or environment-computed values. For static values, `application.yml` is easier to read and audit.

## 5. Static resources used by Swagger UI

Swagger UI is packaged as a WebJar. Inside the application, resources typically reside under a classpath path similar to:

```text
META-INF/resources/webjars/swagger-ui/{swagger.version}/
```

Key files include:

| Resource | Role |
|---|---|
| `index.html` | Swagger UI initialization page and injection point for CSS/JavaScript |
| `swagger-ui.css` | Default interface styling |
| `swagger-ui-bundle.js` | Swagger UI interface implementation and core logic |
| `swagger-ui-standalone-preset.js` | Preset components, including default top bar/layout |
| `favicon-32x32.png` | Browser tab icon |
| `.map` files | Source maps for debugging JavaScript/CSS |

Do not directly edit WebJar contents inside downloaded dependencies or replace the entire JavaScript bundle just to adjust CSS. Those files belong to the Swagger UI version bundled by springdoc; upgrading dependencies can change HTML structure, CSS selectors, plugin APIs, or resource paths.

springdoc provides the `SwaggerIndexPageTransformer` extension point to transform resources before sending them to the browser. You can use it to add stylesheet links, scripts, or modify parts of the original resources while keeping springdoc's default processing.

## 6. Adding custom CSS via static resources

Place a custom stylesheet in the application's static resources:

```text
src/
└── main/
    └── resources/
        └── static/
            └── docs-assets/
                └── swagger-ui/
                    └── custom.css
```

Example `custom.css` content:

```css
/* Customize interface to match application branding. */
.swagger-ui .topbar {
    background: #17324d;
}

.swagger-ui .info .title {
    font-weight: 700;
}

.swagger-ui .opblock-tag {
    border-bottom-width: 2px;
}
```

With default static resource configuration, the file is served at `/docs-assets/swagger-ui/custom.css`. Use a distinct prefix such as `docs-assets` to avoid overlapping with the `/swagger-ui/**` resource handler registered by springdoc for the WebJar. If the application customizes `spring.web.resources.static-locations`, the access path may differ.

Serving the stylesheet successfully is not enough on its own; the Swagger UI page must also load it. You can inject a `<link>` tag into `index.html` using the transformer shown in the next section.

## 7. Using SwaggerIndexPageTransformer in Spring Web MVC

The example below targets Spring Boot 3/4 with springdoc 2.x/3.x and Web MVC. Imports belong to the springdoc 2.x/3.x line; verify against the exact dependency API if using a different version.

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletRequest;

import org.springdoc.core.properties.SwaggerUiConfigParameters;
import org.springdoc.core.properties.SwaggerUiConfigProperties;
import org.springdoc.core.properties.SwaggerUiOAuthProperties;
import org.springdoc.webmvc.ui.SwaggerIndexPageTransformer;
import org.springdoc.webmvc.ui.SwaggerIndexTransformer;
import org.springdoc.webmvc.ui.SwaggerWelcomeCommon;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.web.servlet.resource.ResourceTransformerChain;
import org.springframework.web.servlet.resource.TransformedResource;

@Configuration
class SwaggerUiResourceConfiguration {

    @Bean
    SwaggerIndexTransformer swaggerIndexTransformer(
        SwaggerUiConfigProperties swaggerUiConfig,
        SwaggerUiOAuthProperties swaggerUiOAuthProperties,
        SwaggerUiConfigParameters swaggerUiConfigParameters,
        SwaggerWelcomeCommon swaggerWelcomeCommon
    ) {
        return new SwaggerIndexPageTransformer(
            swaggerUiConfig,
            swaggerUiOAuthProperties,
            swaggerUiConfigParameters,
            swaggerWelcomeCommon
        ) {
            @Override
            public Resource transform(
                HttpServletRequest request,
                Resource resource,
                ResourceTransformerChain transformerChain
            ) throws IOException {
                // Preserve the steps springdoc needs to generate the Swagger UI page.
                Resource transformed = super.transform(request, resource, transformerChain);

                if (!"index.html".equals(resource.getFilename())) {
                    return transformed;
                }

                String html;
                try (InputStream input = transformed.getInputStream()) {
                    html = new String(input.readAllBytes(), StandardCharsets.UTF_8);
                }

                String cssUrl = request.getContextPath() + "/docs-assets/swagger-ui/custom.css";
                String cssLink = "<link rel=\"stylesheet\" href=\""
                    + cssUrl + "\">";

                if (!html.contains(cssUrl)) {
                    html = html.replace("</head>", cssLink + "</head>");
                }

                return new TransformedResource(
                    transformed,
                    html.getBytes(StandardCharsets.UTF_8)
                );
            }
        };
    }
}
```

Key takeaways from the example:

1. The bean replaces the default transformer through springdoc's extension point.
2. Call `super.transform(...)` before editing HTML so URLs and Swagger UI configs injected by springdoc are retained.
3. Modify only `index.html`; other resources continue using default handling.
4. The CSS path prepends `request.getContextPath()` so it works when the application has a servlet context path.
5. Use UTF-8 explicitly when reading and writing HTML.
6. Check for the link tag before inserting to prevent duplicates if the transformer runs multiple times.

If Swagger UI sits behind a reverse proxy adding a path prefix, configure trusted forwarded headers and check the actual URL received by the browser. `getContextPath()` reflects only the servlet context path; it does not automatically infer every proxy-added prefix.

## 8. Customizing CSS directly by transforming the stylesheet

If you prefer not to add a separate CSS file, you can transform `swagger-ui.css` and append application CSS at the end. This still uses the transformer, targeting the CSS resource instead:

```java
if ("swagger-ui.css".equals(resource.getFilename())) {
    String css;
    try (InputStream input = resource.getInputStream()) {
        css = new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }

    String customCss = "\n"
        + "/* Application overrides */\n"
        + ".swagger-ui .topbar { background: #17324d; }\n"
        + ".swagger-ui .info .title { font-weight: 700; }\n";

    return new TransformedResource(
        resource,
        (css + customCss).getBytes(StandardCharsets.UTF_8)
    );
}
```

This code serves as an alternative branch to `index.html` inside the previous transformer; do not register a second transformer bean when the application needs only one transformer. Both `index.html` and `swagger-ui.css` can be handled inside the same `transform` method using separate conditional branches.

Appending CSS to the end of the original stylesheet overrides default selectors, while still depending on Swagger UI's CSS class structure. After upgrading the WebJar version, verify selectors still exist and stylesheet ordering remains valid. Avoid broad string replacements like `css.replace("old", "new")` across the entire bundle, which can accidentally alter unrelated content.

## 9. Adding JavaScript, favicon, or changing page title

If custom JavaScript is required, place the file in static resources, for example:

```text
src/main/resources/static/docs-assets/swagger-ui/custom.js
```

Then append a script tag to the springdoc-transformed HTML, similar to stylesheet injection:

```java
String jsUrl = request.getContextPath() + "/docs-assets/swagger-ui/custom.js";
String scriptTag = "<script defer src=\"" + jsUrl + "\"></script>";
html = html.replace("</body>", scriptTag + "</body>");
```

The snippet above supplements the `index.html` handling branch in the transformer. Ensure it is injected only once and loads after Swagger UI elements exist, or use official events/plugins instead of touching the DOM prematurely.

A favicon can be added by updating the `link rel="icon"` tag in `index.html` to point to a file in static resources. The page title can be changed by editing the `<title>` element in HTML, though you should re-verify markup after each Swagger UI upgrade because the HTML template may change.

Never embed tokens, client secrets, passwords, or sensitive environment data into publicly served JavaScript. Any script running in the Swagger UI page can read the DOM and send requests with the user's session permissions. Load only trusted scripts, prefer same-origin resources, and comply with the application's Content Security Policy.

## 10. Customizing the initialization page without losing springdoc config

`index.html` is not just a plain static HTML file. springdoc uses the transformer to inject settings such as document URLs, config URL, OAuth settings, and Swagger UI parameters. Replacing this page with a custom copy without reproducing those config steps leaves the UI unable to locate which OpenAPI document to load.

When modifying the page:

- Prefer extending `SwaggerIndexPageTransformer` and calling `super.transform(...)`.
- Modify only necessary HTML fragments, such as title, CSS links, scripts, or favicon.
- Do not remove `SwaggerUIBundle` initialization or springdoc-generated configuration.
- If a custom layout/plugin is needed, ensure the plugin is registered during initialization and the layout component name matches `springdoc.swagger-ui.layout`.
- Check `configUrl` and OpenAPI URLs after deploying under a context path or reverse proxy.

The `layout` property only selects a component name already registered in the plugin system; setting `layout: CustomLayout` does not create that component automatically. For a custom layout, you must supply the corresponding JavaScript plugin and ensure it loads before Swagger UI initializes.

## 11. Differences between Web MVC and WebFlux

The transformer in the example above is servlet-based. Do not reuse the exact same class or method signature for WebFlux.

| Aspect | Web MVC | WebFlux |
|---|---|---|
| Transformer | `org.springdoc.webmvc.ui.SwaggerIndexPageTransformer` | `org.springdoc.webflux.ui.SwaggerIndexPageTransformer` |
| Request context | `HttpServletRequest` | `ServerWebExchange` |
| Transform signature | Returns `Resource` | Returns `Mono<Resource>` |
| Resource transformer chain | `org.springframework.web.servlet.resource.ResourceTransformerChain` | `org.springframework.web.reactive.resource.ResourceTransformerChain` |
| UI starter | `springdoc-openapi-starter-webmvc-ui` | `springdoc-openapi-starter-webflux-ui` |

With WebFlux, write the transformer using reactive APIs, read resource content inside an appropriate reactive operator, and return `Mono<Resource>`. Never block the event loop with blocking I/O or `block()` calls inside the transformer. Follow the WebFlux sample/demo for your exact springdoc version when implementing.

## 12. Notes specific to major versions

### springdoc 1.x

springdoc 1.x uses older artifacts such as `springdoc-openapi-ui`, and several config classes reside in `org.springdoc.core` instead of `org.springdoc.core.properties`. Version 1.8.0 is the final open-source release supporting Spring Boot 2.x/1.x. Do not copy v2/v3 imports into a 1.x project without checking Javadoc and source code for that exact version.

### springdoc 2.x

springdoc 2.x targets Spring Boot 3. UI artifacts use starter names such as `springdoc-openapi-starter-webmvc-ui`. Several packages changed from v1: for example, `SwaggerUiConfigProperties`, `SwaggerUiOAuthProperties`, and `SwaggerUiConfigParameters` belong to `org.springdoc.core.properties`; `GroupedOpenApi` belongs to `org.springdoc.core.models`.

The Web MVC transformer example in this article uses the 2.x API structure. Even when classes share similar names, verify the exact minor version in case constructors or dependencies change.

### springdoc 3.x

springdoc 3.x targets Spring Boot 4. UI starters continue using `springdoc-openapi-starter-webmvc-ui` or `springdoc-openapi-starter-webflux-ui`. Current documentation illustrates `SwaggerIndexPageTransformer` with four configuration dependencies just like the Web MVC example above. Even so, internal extension points may evolve across minor versions; when upgrading, recompile and test the transformer rather than blindly assuming old imports still work.

Some newer releases also change caching behavior and per-request page transformation. If a transformer injects per-request values such as a CSP nonce, verify that responses do not cache transformed output from an earlier request. Never use a singleton transformer to hold nonces or user-specific data in fields shared across requests.

## 13. Configuration properties not to guess

Swagger UI documents many upstream options, yet not every option has a matching property in `springdoc.swagger-ui`. Check the properties table for your exact springdoc version before adding keys to YAML.

Common misconceptions:

- `springdoc.swagger-ui.layout` selects a registered layout component; it does not load an arbitrary HTML file.
- `springdoc.swagger-ui.url` points to an OpenAPI document; it is not a CSS URL.
- `springdoc.swagger-ui.urls` builds a selectable list of documents; it is not an asset list.
- `springdoc.swagger-ui.path` changes the UI page route; it does not move `/v3/api-docs`.
- `springdoc.swagger-ui.enabled=false` disables the UI; `springdoc.api-docs.enabled=false` disables the JSON/YAML document endpoint.
- Do not assume `springdoc.swagger-ui.custom-css-url`, `custom-js-url`, or `custom-favicon` are supported springdoc properties unless your version's config reference lists them. For custom CSS/JS, use static resources and a transformer.
- `query-config-enabled` allows overriding certain settings via query string. This is a legacy option carrying security warnings; keep it disabled unless requirements and risks have been explicitly evaluated.

If a property is unrecognized, the application may still start without applying the change. Check `/v3/api-docs/swagger-config`, startup logs, and configuration docs rather than relying solely on YAML syntax validity.

## 14. Protecting Swagger UI and extended resources

When adding custom CSS or JavaScript, those files become static endpoints of the application. If Swagger UI is protected by Spring Security, explicitly decide who can access them:

- The UI page, JSON/YAML documents, and CSS/JS resources need consistent access policies.
- Do not make `/v3/api-docs/**` public just because a stylesheet fails to load; inspect matchers for the exact resource first.
- If docs are only for internal developers, require authentication/roles for both the UI and OpenAPI endpoints.
- Never put client secrets into `application.yml` or browser-side JavaScript; OAuth client secrets can be read by users from page source or network traffic.
- When using CSP, ensure `style-src`, `script-src`, and `font-src` permit the actually loaded resources. Prefer same-origin files and avoid inline scripts if policy requires nonces/hashes.

Illustrative matcher example when only developers may view documentation:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        "/docs/swagger-ui.html",
        "/swagger-ui/**",
        "/docs-assets/swagger-ui/**",
        "/v3/api-docs/**"
    ).hasRole("DEVELOPER")
    .anyRequest().authenticated()
);
```

Adjust the URL list to match `springdoc.swagger-ui.path`, `springdoc.api-docs.path`, context path, and actual groups. If a route is renamed, stale security matchers can cause the UI to return 401/403 while backend APIs still work.

## 15. Verifying after extending the UI

After adding configuration or a transformer, test both the UI and data endpoints:

1. The Swagger UI page returns valid HTML or redirects as configured.
2. `swagger-config` loads and contains the right OpenAPI URLs.
3. `/v3/api-docs` or group endpoints return valid OpenAPI JSON.
4. Custom CSS/JS/favicon files return HTTP 200 with proper Content-Type and are not blocked by Spring Security.
5. Final HTML contains each CSS/script link exactly once.
6. Browser DevTools shows no 404, CSP, MIME type, or JavaScript exceptions.
7. Features such as Authorize, Try it out, group selection, requests/responses, and schemas still work.
8. The page continues working under the real context path, reverse proxy, and environment profile.
9. Reload after clearing cache to verify updated stylesheets; when releasing new assets, use fingerprinted filenames or suitable cache policies.

Example testing static resources and OpenAPI with MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class SwaggerUiResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void servesCustomStylesheet() throws Exception {
        mockMvc.perform(get("/docs-assets/swagger-ui/custom.css"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith("text/css"));
    }

    @Test
    void keepsOpenApiDocumentAvailable() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ));
    }
}
```

If security protects documentation endpoints, tests must supply an appropriate principal/authority or assert 401/403 responses separately per policy. Paths in the example are defaults; replace them with the application's configured paths.

## 16. Common errors and how to handle them

| Symptom | Common cause | Resolution |
|---|---|---|
| CSS file returns 404 | Placed in wrong classpath location or URL mismatches static resource mapping | Check `src/main/resources/static` and the URL in the link tag |
| CSS loads 200 yet does not apply | Selector no longer exists, CSS loaded before base stylesheet, or low specificity | Check `<link>` order, selectors, and specificity |
| Swagger UI renders page without any API | Transformer replaced `index.html` and dropped default config | Call `super.transform(...)` before modifying content |
| Swagger UI reports config load error | Wrong `configUrl`, mismatched context path/proxy prefix, or security block | Check `/v3/api-docs/swagger-config`, forwarded headers, and security matchers |
| Changing UI path broke the home page | Swagger UI took over the root welcome page route | Use a dedicated `springdoc.swagger-ui.path` |
| CSS/JS blocked by CSP | `style-src` or `script-src` disallows resource source | Serve assets same-origin and update CSP carefully |
| JavaScript runs twice | Transformer injected duplicate script tags or beans overlapped | Ensure idempotency and register only one transformer |
| Transformer fails to compile after major upgrade | Package or API signature changed | Consult migration guide/Javadoc for exact version and Web MVC/WebFlux |
| Old CSS still appears after deployment | Browser or proxy cached the stylesheet | Use fingerprinted filenames, proper cache-control, and hard reload |
| Swagger UI fails to open behind reverse proxy | HTML uses absolute URLs missing context/proxy prefix | Configure forwarded headers and verify generated URLs in HTML/config |
| UI returns 403 while CSS file works | Security matchers for UI, swagger-config, and OpenAPI are out of sync | Protect the full endpoint set consistently and inspect denied requests |

## 17. Workflow for choosing an extension approach

When Swagger UI needs customization in a Spring Boot project, proceed in this order:

1. Identify Boot version, springdoc major/minor version, and Web MVC vs. WebFlux.
2. Select the right UI starter and verify the version in the compatibility matrix.
3. Use `springdoc.swagger-ui.*` for paths, layouts, document URLs, and documented config options.
4. Place custom CSS/JS/favicons in the application's static resources.
5. If assets must be injected into the page, extend `SwaggerIndexPageTransformer` for the right stack and version; preserve default handling with `super.transform(...)`.
6. Transform only necessary resources; avoid replacing the entire WebJar bundle.
7. Check context path, reverse proxy, CSP, and security matchers.
8. Verify HTML, assets, swagger-config, OpenAPI JSON/YAML, and browser console.
9. After every springdoc/Swagger UI upgrade, re-verify the transformer and CSS selectors.

Configuration properties fit built-in UI adjustments; transformers and static resources serve deeper requirements. Choosing the right version-appropriate extension point ensures the customized UI retains OpenAPI loading, authentication, and API interactivity provided by springdoc.

## 18. References

- [Springdoc OpenAPI v2 Documentation](https://springdoc.org/v2/): Swagger UI configuration, custom static resources, and migration from v1.
- [Springdoc OpenAPI v2 – Configuration Properties](https://springdoc.org/v2/properties.html): springdoc 2.x configuration properties table.
- [Springdoc OpenAPI – Current Documentation](https://springdoc.org/): current documentation and compatibility matrix for newer Spring Boot lines.
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): official options, plugin system, and UI configuration.
- [Spring Framework – Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html): serving static resources in Spring MVC.
