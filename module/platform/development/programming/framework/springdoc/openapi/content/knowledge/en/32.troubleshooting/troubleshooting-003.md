# UI Fails to Load swagger-config or Static Resources

## 1. Identifying the Right Error Type Before Fixing

Swagger UI can open the HTML page yet still fail to display APIs. This case is usually not a controller or schema bug at the outset. The UI needs to load several resources and call at least one configuration endpoint before fetching the OpenAPI document.

A typical page load involves these steps:

1. The browser opens the Swagger UI URL, for example /swagger-ui.html.
2. The application returns HTML or redirects to the index page.
3. The browser loads JavaScript, CSS, fonts, and UI assets.
4. Swagger UI loads `swagger-config` to learn the OpenAPI document URL and UI options.
5. Swagger UI calls OpenAPI JSON/YAML, usually /v3/api-docs.
6. The UI parses the document and renders operations, schemas, and security metadata.

Failures at each step produce different symptoms. A blank page, a spinner that never stops, a "Failed to load API definition" message, or JavaScript errors alone are not enough to conclude the cause.

You need to determine which request fails in Browser Developer Tools, then correlate the status code, redirect, response body, Content-Type, and actual URL.

## 2. Distinguishing Three Resource Groups

When investigating, divide requests into three groups:

| Group | Example URL | Role |
|---|---|---|
| UI page | /swagger-ui.html, /swagger-ui/index.html | Returns HTML to initialize Swagger UI |
| Static resources | /swagger-ui/swagger-ui-bundle.js, swagger-ui.css, favicon, or WebJar assets | Runs and styles the UI |
| Specification and configuration | /v3/api-docs/swagger-config, /v3/api-docs | Provides configuration and the OpenAPI document |

Specific static file names depend on the packaged Swagger UI version. Check the Network tab to see which exact resource is failing.

`swagger-config` usually contains the document URL or document list, default document name, and various UI settings. OpenAPI JSON/YAML is the actual contract containing paths, operations, schemas, responses, and security.

If `swagger-config` fails to load, the UI may not know where to fetch the document. If `swagger-config` loads successfully but the OpenAPI document fails, the page may render the UI shell without displaying operations.

## 3. Using the Network Tab to Find the First Failing Request

Open Browser Developer Tools, select Network, enable Preserve log, then reload the Swagger UI page.

Inspect in order:

- Document request to /swagger-ui.html or the configured UI URL.
- Redirect to /swagger-ui/index.html if applicable.
- JavaScript bundle and CSS.
- Request to `swagger-config`.
- Request to /v3/api-docs or the configured document URL.
- Requests to the API server if trying out an operation.

Record for the failing request:

- Full Request URL.
- HTTP status.
- Method.
- Response Content-Type.
- Response body or the beginning of the response.
- Redirect chain.
- Initiator.
- Corresponding Console errors.

Do not look only at the status on the first row. A request may return 302 to a login page, then redirect to an HTML page returning 200. Swagger UI receives HTML instead of JSON and reports a parse error, even though the final request looks successful.

If there are multiple errors, address the first root failing request. Subsequent JS or rendering errors may simply be side effects of a bundle file or config failing to load.

## 4. Checking Default Endpoints

With standard Springdoc configurations, commonly used URLs are:

~~~text
/swagger-ui.html
/swagger-ui/index.html
/v3/api-docs/swagger-config
/v3/api-docs
/v3/api-docs.yaml
~~~

Not every application uses these exact default paths. Properties can change the API docs path, Swagger UI path, or document URL.

Test each URL from the same environment the browser accesses:

~~~bash
curl -i http://localhost:8080/swagger-ui.html
curl -i http://localhost:8080/v3/api-docs/swagger-config
curl -i http://localhost:8080/v3/api-docs
~~~

Use `-i` to inspect status and response headers. When checking redirects, do not follow redirects automatically at first. Then you can use `-L` to inspect the final response.

If running behind a context path, for example `/catalog`, test the public URL with the prefix:

~~~bash
curl -i https://api.example.com/catalog/v3/api-docs/swagger-config
~~~

One endpoint returning 404 while another returns 200 often helps isolate path configuration, security, or resource mapping.

## 5. Checking the Right Springdoc Starter

Swagger UI static assets are typically provided by starters with the `-ui` suffix. For example:

- Spring MVC: springdoc-openapi-starter-webmvc-ui.
- Spring WebFlux: springdoc-openapi-starter-webflux-ui.

If the application only uses an API-only starter, OpenAPI JSON/YAML can work while Swagger UI assets are not packaged.

Maven dependency example for Spring MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>PINNED_COMPATIBLE_VERSION</version>
</dependency>
~~~

With WebFlux, choose the corresponding `webflux-ui` artifact. Replace `PINNED_COMPATIBLE_VERSION` with a release compatible with your application's Spring Boot and Java versions.

Do not add both `webmvc-ui` and `webflux-ui` just to fix static resource errors. Choose the starter matching the web stack. If you only need the document for CI or a developer portal, an API-only starter is a reasonable choice, but do not expect Swagger UI to be present.

## 6. Checking API Docs and Swagger UI Enable/Disable Configuration

Properties commonly needing inspection:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
~~~

`api-docs.enabled` controls the OpenAPI endpoint. `swagger-ui.enabled` controls the built-in Swagger UI.

Some configurations may disable Swagger UI in production while keeping the OpenAPI endpoint. In that case `/v3/api-docs` works while the UI URL is not served.

Conversely, if `api-docs.enabled` is disabled, Swagger UI may load HTML and JS but fail to fetch the document.

Check the final merged configuration after Spring Boot combines `application.yml`, profile-specific YAML, environment variables, and command-line arguments. Do not read just one config file and conclude that the property has that value at runtime.

## 7. Distinguishing swagger-config Errors from OpenAPI Document Errors

Swagger UI normally loads configuration from the `swagger-config` endpoint. With default configuration, this endpoint is typically `/v3/api-docs/swagger-config`.

If this request returns 404, 401, 403, or HTML, the UI may not know which OpenAPI URL to load.

If `swagger-config` returns valid JSON but the document URL inside is wrong, the next step to `/v3/api-docs` will fail.

Open the `swagger-config` response and inspect relevant fields such as `url` or `urls`. Then copy that exact document URL and call it directly with curl.

Do not hard-code the default config URL if the application changed `springdoc.api-docs.path` or `swagger-ui.config-url`. Check the actual output of the running Springdoc version.

## 8. Configuring config-url and Document URL

Springdoc allows configuring the `swagger-config` URL and OpenAPI document URL via Swagger UI properties. Check the documentation for the version in use for exact property names and binding.

Illustrative configuration example:

~~~yaml
springdoc:
  swagger-ui:
    config-url: /v3/api-docs/swagger-config
    url: /v3/api-docs
    disable-swagger-default-url: true
~~~

`config-url` points to the Swagger UI configuration endpoint. `url` points to a specific OpenAPI document. When using multiple documents, a `urls` list can be configured instead of a single `url`.

Do not configure conflicting `url` and `urls`. When using `GroupedOpenApi`, point to the right group document. `disable-swagger-default-url` helps prevent Swagger UI from displaying an unrelated default document when the application's API document configuration has not been loaded properly.

If the API docs path changed, update both the config URL and document URL according to the actual configuration. Do not assume that changing `api-docs.path` automatically fixes every hard-coded URL in HTML or a reverse proxy.

## 9. Checking Response Content-Type and Body

An endpoint may return status 200 yet contain something other than the expected JSON or JavaScript.

Common failure examples:

- `swagger-config` returns `text/html` because it was redirected to a login page.
- `/v3/api-docs` returns a gateway JSON error wrapper.
- JavaScript bundle returns an HTML 404 page.
- CSS returns Content-Type `text/html`.
- Proxy returns a maintenance page instead of the asset.
- API docs return an empty body due to a filter or response transformation.

Use curl:

~~~bash
curl -i http://localhost:8080/v3/api-docs/swagger-config
curl -i http://localhost:8080/v3/api-docs
curl -I http://localhost:8080/swagger-ui/swagger-ui-bundle.js
~~~

Inspect `Content-Type` and the first few lines of the body. `swagger-config` and OpenAPI JSON must be JSON; JS and CSS must be served with appropriate MIME types.

Do not accept an HTML file just because the status is 200. If the endpoint requires authentication, handle redirects and credentials properly instead of ignoring the response content.

## 10. Spring Security Blocking swagger-config or Static Resources

A filter chain requiring authentication for all requests can block both Swagger UI and the OpenAPI endpoint.

Illustrative example for a Servlet application:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(
            "/swagger-ui.html",
            "/swagger-ui/**",
            "/v3/api-docs",
            "/v3/api-docs/**"
        ).hasRole("API_DOCS")
        .anyRequest().authenticated()
    );

    return http.build();
}
~~~

If documentation is allowed to be publicly accessible in the corresponding environment, `permitAll` can be used for these matchers. For internal documentation, use a dedicated role or scope.

The key point is to include the UI page, static assets, `swagger-config`, and the OpenAPI document. Allowing only `/swagger-ui.html` while blocking `/swagger-ui/**` lets HTML load while JS/CSS fail with 401 or 403.

Do not open up the entire application to fix documentation errors. Only adjust matchers for the necessary paths and keep authorization on business APIs.

## 11. Checking SecurityFilterChain Order and Matchers

An application can have multiple `SecurityFilterChain` beans with different `securityMatcher` configurations. Swagger UI requests may be handled by a different chain than business APIs.

When investigating:

1. Check which chain matches `/swagger-ui/**` requests.
2. Check the `@Order` ordering of the chains.
3. Check whether matchers include the context path or not.
4. Check which rule is evaluated first.
5. Check whether the authentication entry point redirects to login.
6. Check CSRF only when the request method or flow genuinely requires it.

GET requests to the UI and document normally do not need a CSRF token, but if the application has custom CSRF or special filters, verify actual behavior. Do not disable CSRF application-wide just to get Swagger UI to load.

If the UI is protected by a session cookie, the browser must retain the session when calling `swagger-config` and the OpenAPI document. When using bearer tokens, document configuration and how the UI sends tokens must align with the security scheme.

## 12. Handling Redirects to the Login Page

A common sign is `swagger-config` returning 302 to `/login`. If curl follows redirects, the final response may be 200 HTML.

Test without following redirects:

~~~bash
curl -i http://localhost:8080/v3/api-docs/swagger-config
~~~

If the response is 302 and `Location` points to login, the request is being intercepted by Spring Security or proxy authentication.

If policy requires login, ensure the browser is logged in and the session cookie is sent to the same origin. If CI needs to fetch the document, use credentials with permission to read docs and verify the response is not HTML.

Do not use `curl -L` and look only at the final status. Inspect the entire redirect chain to avoid mistaking a login page for an OpenAPI document.

## 13. Static Resource Mapping Altered or Overridden

The Swagger UI bundle is normally served from resources packaged in dependencies. `WebMvcConfigurer`, `ResourceHandlerRegistry`, or a custom `ResourceResolver` configuration can unintentionally alter mappings.

Causes:

- The application defines a catch-all resource handler with no fallback.
- A custom path pattern captures `/swagger-ui/**` before the WebJar handler.
- Static resource locations were replaced.
- Resource chain or version strategy fails to resolve assets.
- A controller mapping accidentally claims `/swagger-ui/**` URLs.
- Context path or servlet path is miscalculated.

If `addResourceHandlers` has been configured, check the mapping for static assets and ensure it does not override mappings needed by Springdoc/Swagger UI.

Do not blindly add new resource handlers. First inspect asset responses and current mappings. If the error only appeared after adding custom resource configuration, temporarily compare against a minimal configuration in a test branch to identify the conflict.

## 14. MIME Types and X-Content-Type-Options

Browsers can block JavaScript or CSS if the server returns an incorrect MIME type, especially when the response includes `X-Content-Type-Options: nosniff`.

For example:

- `.js` files must be served with a JavaScript MIME type.
- `.css` files need Content-Type `text/css`.
- HTML pages need Content-Type `text/html`.
- OpenAPI JSON needs Content-Type `application/json`.

If a JS file returns `application/json` or `text/html`, inspect the proxy, static resource handler, and error page mapping.

Do not remove `nosniff` to hide MIME type errors. Fix the `Content-Type` at the resource-serving source. Browser protection headers should be kept per security policy.

## 15. Reverse Proxy and Context Path

An application may run at the internal root path yet be published under a prefix:

~~~text
Public URL:
https://api.example.com/catalog/swagger-ui.html

Internal application:
http://catalog-service:8080/swagger-ui.html
~~~

If the reverse proxy does not forward the prefix properly, the HTML page may load while relative requests to `/swagger-ui/**` or `/v3/api-docs/**` are sent to the wrong path.

Check:

- Spring Boot's context path.
- Prefixes added or stripped by ingress or reverse proxy.
- `Location` header in redirects.
- `swagger-config` URL inside HTML/JS.
- Document URL inside `swagger-config`.
- Forwarded headers and public scheme/host.
- Static asset paths requested by the browser.

If the application uses `server.servlet.context-path=/catalog`, public URLs need to reflect that context path. Do not add the prefix twice if the proxy already rewrites the path before forwarding to the application.

## 16. Forwarded Headers and Public URLs

When running behind a proxy, Spring Boot may need to process `Forwarded` or `X-Forwarded-*` headers to build accurate URLs.

Common configuration example:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Exact values depend on the Spring Boot version and proxy architecture. `ForwardedHeaderFilter` or native configuration may be needed depending on the environment.

The proxy must strip client-supplied forwarded headers and set trusted values itself. If the application trusts arbitrary headers, an attacker can cause documents or redirects to contain spoofed hosts or schemes.

If `swagger-config` or the OpenAPI document generates internal URLs such as `http://localhost:8080`, inspect the public host, scheme, prefix, and forwarded header chain. Avoid fixing this by hard-coding the production URL in all profiles if the application needs to run across multiple environments.

## 17. CORS When UI and OpenAPI Document Have Different Origins

If Swagger UI is hosted on one origin and the OpenAPI document on another, the browser enforces the same-origin policy.

For example:

~~~text
Swagger UI:
https://docs.example.com

OpenAPI document:
https://api.example.com/v3/api-docs
~~~

The server serving the document must allow the docs site's origin via CORS. If the UI tries out APIs on another origin, the API server also needs an appropriate CORS policy.

Check:

- Does `Access-Control-Allow-Origin` match the UI page's origin?
- Are `OPTIONS` preflight requests handled?
- Is the `Authorization` header allowed?
- Do cookies/sessions require credentials?
- Wildcard origins are not used alongside credentialed requests.

If the UI and document share the same origin, avoid overly broad unnecessary CORS configurations. CORS does not replace authentication and does not decide who is authorized to read documentation.

## 18. Content Security Policy Blocking JavaScript or CSS

CSP can block Swagger UI scripts, styles, fonts, or fetch calls. The Console typically shows "Refused to load" or "Refused to connect" messages due to policy violations.

Check these directives:

- `script-src` for JavaScript bundles.
- `style-src` for CSS.
- `font-src` for fonts if used by the bundle.
- `img-src` for logos or images.
- `connect-src` for `swagger-config`, the OpenAPI document, and the API server.

If using a CDN, the CDN origin must be permitted under the appropriate directives. When self-hosting assets, prefer the same origin to minimize external sources.

Do not set CSP to a wildcard as a quick fix. Identify the blocked request and add only the necessary source. If using nonces or hashes for inline scripts, the Swagger UI page setup must be compatible with that policy.

## 19. Stale Cache or Mismatched Asset Versions

Browser cache, reverse proxy cache, or CDN cache can retain old HTML/JS after the application upgraded Springdoc or Swagger UI.

Symptoms:

- New page references a renamed bundle file.
- Old JS calls a config endpoint that no longer exists.
- `swagger-config` still caches an old document URL.
- Some users see errors while an incognito tab works.
- After deployment, one replica serves a different asset version than another replica.

Check `Cache-Control`, `ETag`, `Last-Modified`, and `Age` response headers. Try a hard reload or disabled cache in DevTools to determine whether assets are stale.

Do not purge caches at every layer immediately upon seeing an error. First verify whether HTML, JS, and `swagger-config` belong to the same version. Then adjust the cache policy or versioned asset strategy accordingly.

## 20. Checking Document Group or Custom URL Configuration

If the application has multiple `GroupedOpenApi` beans, `swagger-config` may point to a group that no longer exists or is misnamed.

For example, a `partner` group typically has a document URL like:

~~~text
/v3/api-docs/partner
~~~

Check the group name, `pathsToMatch`, `packagesToScan`, and actual endpoint. If the group was renamed, update `swagger-ui.url` or the `urls` list.

When configuring multiple documents, also check `urlsPrimaryName` or the default document name per the property/version in use. A misconfiguration can let the UI load without selecting the intended document.

Do not use the Swagger UI URL as the OpenAPI URL. `swagger-ui.path` is the UI path; `api-docs.path` is the document path. The two properties have different roles.

## 21. curl Diagnostic Checklist

You can run these commands sequentially against a running application environment:

~~~bash
curl -i http://localhost:8080/swagger-ui.html

curl -i http://localhost:8080/swagger-ui/index.html

curl -i http://localhost:8080/v3/api-docs/swagger-config

curl -i http://localhost:8080/v3/api-docs

curl -I http://localhost:8080/swagger-ui/swagger-ui-bundle.js
~~~

If using a context path or custom path, adjust the URLs accordingly. If the endpoint requires authentication, provide credentials securely from a secret store.

Interpreting results:

- HTML UI error: check the UI starter, path, and security.
- JS/CSS error: check WebJar/static mappings, MIME types, CSP, and proxy.
- `swagger-config` error: check `config-url`, security, redirects, and `api-docs` path.
- OpenAPI JSON error: check `api-docs` enabled, groups, customizers, and exception logs.
- All requests return 200 but UI fails: check `Content-Type`, body, browser console, and asset versions.

## 22. Testing with MockMvc

MockMvc can be used to verify the main endpoints in a Servlet application:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SwaggerUiResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void shouldServeOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ))
            .andExpect(jsonPath("$.openapi").exists());
    }

    @Test
    void shouldServeSwaggerConfiguration() throws Exception {
        mockMvc.perform(get("/v3/api-docs/swagger-config"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ));
    }
}
~~~

The `swagger-config` path can change based on `api-docs.path` and `config-url`. Use the project's actual URL.

Static asset tests can check a specific bundle path, but file names change across Swagger UI versions. Avoid hard-coding asset names if dependencies upgrade frequently; you can check the UI page and use a browser smoke test to confirm referenced assets load successfully.

With WebFlux, use `WebTestClient`. MockMvc/WebTestClient do not fully simulate reverse proxies, browser CSP, or CDNs; those parts need integration tests in a production-like environment.

## 23. Verifying with a Browser Smoke Test

Once server endpoints return the expected responses, open Swagger UI in a browser and verify:

1. The HTML page loads successfully.
2. There are no JavaScript errors in the Console.
3. JS/CSS bundles return 200 with the right MIME types.
4. `swagger-config` returns valid JSON.
5. The document URL in config is accessible.
6. The OpenAPI document contains the expected paths and components.
7. Tags and operations are displayed.
8. Authorize works according to the security scheme.
9. Try it out calls the right host and path in the test environment.
10. There are no CORS/CSP errors or unintended redirects.

If the page runs behind a proxy, run the smoke test against the public URL, not just localhost. Proxy configuration is part of the actual path users take.

## 24. Symptoms and Causes Table

| Symptom | First request to check | Common cause |
|---|---|---|
| Swagger UI page 404 | /swagger-ui.html | Missing UI starter or changed path |
| Page loads but is blank | JS/CSS bundle | Static resource 404, CSP, or MIME type |
| Failed to load remote configuration | swagger-config | Security, redirect, wrong config-url |
| Failed to load API definition | OpenAPI JSON/YAML | api-docs disabled, wrong URL, 401/404/5xx |
| Swagger UI shows Petstore/default API | swagger-config | Application document URL not configured properly |
| Fails only after deploy | All requests under public prefix | Reverse proxy, context path, or forwarded headers |
| Local works, other domain fails | swagger-config/document | CORS, CSP, or proxy |
| Some users fail, others succeed | JS/CSS/config cache | Stale browser/CDN cache |
| UI loads but Try it out fails | API operation request | CORS or API security, not static UI |
| JSON document returns HTML | swagger-config or /v3/api-docs | Login redirect or error page |

This table helps select which request to check; final conclusions must rely on actual responses and logs.

## 25. Ordered Troubleshooting Procedure

When Swagger UI fails to display APIs:

1. Open the Network tab and find the first failing request.
2. Confirm whether the UI page is served.
3. Confirm whether JS/CSS/WebJar assets return 200 with proper MIME types.
4. Check whether `swagger-config` returns JSON or is redirected/blocked.
5. Read the document URL inside `swagger-config`.
6. Call OpenAPI JSON/YAML directly and validate the body.
7. Check the starter, `api-docs.enabled`, and `swagger-ui.enabled`.
8. Check Spring Security matchers and filter chain ordering.
9. Check context path, reverse proxy, and forwarded headers.
10. Check CORS/CSP if cross-origin or CDN is involved.
11. Check caching if the issue only appears after deploy or on certain browsers.
12. Run MockMvc/WebTestClient and a browser smoke test.

Do not change multiple properties at once. Fix one cause, re-run the relevant requests, and confirm the issue is resolved. This helps avoid introducing new errors and preserves visibility into the root cause.

## 26. Prevention Principles

To keep Swagger UI loading reliably:

1. Choose the UI starter matching Spring MVC or WebFlux.
2. Keep API docs and Swagger UI enabled in environments where they are needed.
3. Manage `swagger-ui.path`, `config-url`, and the document URL explicitly.
4. Protect the UI, static assets, `swagger-config`, and OpenAPI document consistently under the appropriate policy.
5. Check response `Content-Type` and body, not just status 200.
6. Do not allow a login redirect to be mistaken for a JSON document.
7. Keep static resource mappings free of conflicts with WebJars.
8. Configure context path and reverse proxy consistently.
9. Only trust forwarded headers from controlled proxies.
10. Configure CORS and CSP for actual origins, without opening arbitrary wildcards.
11. Control asset caching and versioning during deployments.
12. Test document endpoints in CI and run browser smoke tests against public URLs.

Swagger UI depends simultaneously on the HTML page, static resources, `swagger-config`, and the OpenAPI document. By inspecting each request in order and comparing status, `Content-Type`, body, and redirects, a development team can pinpoint whether the fault lies in dependencies, security, mappings, proxy, or browser policy rather than tweaking configuration blindly.

## 27. References

- Springdoc OpenAPI documentation: https://springdoc.org/
- Springdoc configuration properties: https://springdoc.org/properties.html
- Swagger UI configuration: https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/
- Spring Security request authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Boot forwarded headers: https://docs.spring.io/spring-boot/reference/howto/webserver.html

