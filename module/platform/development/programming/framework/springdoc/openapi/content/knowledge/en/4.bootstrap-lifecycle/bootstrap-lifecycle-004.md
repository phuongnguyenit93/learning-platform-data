# Opening Swagger UI and Verifying the Specification Source Being Loaded

Swagger UI is a browser interface for viewing and testing operations described in an OpenAPI document. When opening the Swagger UI page, the browser also loads a configuration file before loading the OpenAPI JSON/YAML from the configured URL. Therefore, seeing the Swagger UI page is not enough to confirm that the UI is reading the right documentation for the current application.

With springdoc-openapi in Spring Boot, distinguish between three URLs:

1. **Swagger UI URL:** the HTML/JavaScript page opened by the user, usually **/swagger-ui.html**.
2. **Swagger configuration URL:** the endpoint returning configuration for Swagger UI, defaulting to **/v3/api-docs/swagger-config**.
3. **OpenAPI document URL:** the endpoint returning the JSON/YAML specification, defaulting to **/v3/api-docs** or **/v3/api-docs.yaml**.

This hands-on lesson guides you through opening the UI, tracing browser requests, verifying the source URL, inspecting document content, and troubleshooting common errors when changing paths, using multiple groups, or deploying under a context path or reverse proxy.

## 1. Understanding the Swagger UI Loading Flow

When a user visits the UI page, the typical flow proceeds as follows:

~~~text
Browser
   |
   | GET /swagger-ui.html
   v
Springdoc Swagger UI resource
   |
   | Load Swagger UI JavaScript/CSS
   |
   | GET /v3/api-docs/swagger-config
   v
Swagger UI configuration
   |
   | Reads url / urls / configUrl
   |
   | GET /v3/api-docs
   | or /v3/api-docs/{group}
   v
OpenAPI JSON/YAML
   |
   v
Render operations, schemas and responses
~~~

In the default configuration, swagger-config usually points to the document URL **/v3/api-docs**. If the application declares multiple **GroupedOpenApi** beans, the configuration may contain a **urls** list for users to choose a document.

Each request is a separate checkpoint. The UI page may load successfully while swagger-config returns 401/404; swagger-config may load successfully while the document URL returns 404; or the document may load but contain operations from a different group or environment.

## 2. Default Springdoc URLs

With Spring MVC or WebFlux and the corresponding Springdoc UI starter, common URLs are:

| Purpose | Default URL | Content |
| --- | --- | --- |
| Swagger UI page | /swagger-ui.html | Entry point/redirect to UI |
| UI resources | /swagger-ui/index.html | Static UI page |
| OpenAPI JSON | /v3/api-docs | Specification in JSON format |
| OpenAPI YAML | /v3/api-docs.yaml | Specification in YAML format |
| Swagger UI config | /v3/api-docs/swagger-config | Document URLs and UI settings |

URLs may change depending on server.servlet.context-path, WebFlux base path, Springdoc configuration, or reverse proxies. The table above shows paths inside the application without additional prefixes.

Open the following URLs one by one in the same environment:

~~~text
http://localhost:8080/swagger-ui.html
http://localhost:8080/v3/api-docs/swagger-config
http://localhost:8080/v3/api-docs
http://localhost:8080/v3/api-docs.yaml
~~~

If using HTTPS, a different hostname, or another port, replace the base URL with the address of the running application. Do not assume local URLs match production URLs.

## 3. Distinguishing the UI URL and the Specification URL

The following two properties serve different purposes:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
  api-docs:
    path: /openapi
~~~

In the example:

- The Swagger UI entry point is **/docs**.
- OpenAPI JSON is **/openapi**.
- OpenAPI YAML is usually **/openapi.yaml**.
- Swagger UI config is served under the API docs path by default, e.g., **/openapi/swagger-config**.

Changing **springdoc.swagger-ui.path** only changes the path to open the UI. It does not automatically change the OpenAPI document URL. Changing **springdoc.api-docs.path** is what changes the base path of the document and swagger-config.

After changing paths, open the new URL and verify swagger-config points to the new document. If the UI still tries to load **/v3/api-docs**, a URL may have been overridden or the browser may be using a cached configuration.

## 4. Configuring the Swagger UI Entry Point

Example using application.yml:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
    enabled: true
  api-docs:
    enabled: true
~~~

Users then open:

~~~text
http://localhost:8080/docs
~~~

The **springdoc.swagger-ui.enabled** property enables/disables the UI. **springdoc.api-docs.enabled** enables/disables the specification endpoint. The two properties are independent:

- You can enable OpenAPI JSON/YAML while disabling Swagger UI so clients or pipelines can fetch the document.
- You can disable both when the environment is not allowed to publish documentation.
- If the UI is enabled while API docs are disabled, the UI cannot load a document unless configured to use an external specification source.

Do not confuse hiding the UI with protecting the API. Disabling Swagger UI does not block controller endpoints; endpoint protection must be configured in Spring Security or the gateway.

## 5. Opening swagger-config Directly

This is a crucial step to determine which document Swagger UI is instructed to load.

Open:

~~~text
http://localhost:8080/v3/api-docs/swagger-config
~~~

The response is usually JSON containing configuration fields, for example:

~~~json
{
  "configUrl": "/v3/api-docs/swagger-config",
  "url": "/v3/api-docs",
  "validatorUrl": ""
}
~~~

This is an abbreviated illustrative example. Actual fields may vary by Swagger UI version, Springdoc version, and application configuration.

Look for the following fields:

| Field | Role |
| --- | --- |
| configUrl | URL the UI uses to fetch configuration |
| url | A single OpenAPI document URL |
| urls | List of documents, commonly used for multiple groups |
| urls.primaryName | Name of the document selected by default in some configurations |
| oauth2RedirectUrl | Swagger UI OAuth2 callback URL |
| validatorUrl | Document validation service if configured |

What needs to be verified is whether the URLs in the configuration have the right base path, context path, group, and environment. If the configuration contains **url: /v3/api-docs**, the UI will load that path relative to the page's current origin.

## 6. Verifying Actual Requests with Browser DevTools

Do not just read the configuration JSON; inspect the requests the browser actually sends:

1. Open Swagger UI.
2. Press **F12** to open Developer Tools.
3. Select the **Network** tab.
4. Enable **Preserve log** if the page has redirects.
5. Reload the page with **Ctrl+R**.
6. Filter by **api-docs**, **swagger-config**, or **openapi**.
7. Select the swagger-config request and check Request URL, Status Code, and Response.
8. Find the document request such as /v3/api-docs, select it, and check the Response.
9. Check Initiator to see which UI/config initiated the request.

Columns to pay attention to:

| Attribute | What to Confirm |
| --- | --- |
| Request URL | Correct hostname, port, context path, and group |
| Status Code | 200 when loaded successfully |
| Content-Type | JSON/YAML matching the request |
| Response | Contains openapi, info, paths, components |
| Initiator | Request originated from the expected Swagger UI/config |
| Redirect | Not redirected to a login page or another environment's URL |

If you see the UI displaying stale content, enable **Disable cache** in the Network tab while DevTools is open and reload. Only use this step to rule out browser cache; if the server response is still stale, inspect caches/proxies/CDNs in front of the application.

## 7. Inspecting OpenAPI JSON via Browser or curl

Open the document directly:

~~~text
http://localhost:8080/v3/api-docs
~~~

A valid document usually has top-level components:

~~~json
{
  "openapi": "3.0.1",
  "info": {
    "title": "Book API",
    "version": "v1"
  },
  "paths": {},
  "components": {}
}
~~~

The openapi value in the example is illustrative only; the actual version depends on Springdoc configuration. Do not confuse info.version (the API version documented by the application) with the Springdoc or Spring Boot library version.

In a terminal with curl:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs/swagger-config
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

**-i** lets you see the HTTP status and response headers. When you need to save the content for diffing:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
curl -fsS http://localhost:8080/v3/api-docs/swagger-config -o swagger-config.json
~~~

The commands above write files to the current terminal directory. Choose an appropriate working directory and avoid committing documents containing internal information if the repository is not intended to store them.

## 8. Checking That the Document Matches the Right Application and Version

Once the document loads successfully, verify its content:

- info.title has the right API/service name.
- info.version has the contract version published by the team.
- servers has the right environment base URL if declared.
- paths contains the newly implemented endpoints.
- components.schemas contains the expected DTOs.
- components.securitySchemes contains the expected authentication mechanisms.
- Responses and request bodies have the right schemas.
- No internal endpoints outside the document's audience appear.

Visual inspection example:

~~~json
{
  "paths": {
    "/api/books": {
      "get": {
        "summary": "Search books"
      }
    }
  }
}
~~~

If Swagger UI shows the right title but misses new endpoints, the UI may be loading a different group or OpenAPI file. Cross-check swagger-config.url/urls and the document request in Network before editing controllers.

## 9. Configuring the Document Source with springdoc.swagger-ui.url

The application can instruct Swagger UI to load a specific OpenAPI document:

~~~yaml
springdoc:
  swagger-ui:
    url: /v3/api-docs
~~~

The **url** property is useful when specifying a single document source, such as a custom path or a document served by the application. Relative URLs are usually resolved against the UI page's origin/base URL; absolute URLs can point to another host.

If **url** is configured, verify its value in swagger-config and Network. Do not assume changing springdoc.api-docs.path will automatically update hard-coded URLs in the UI configuration.

Do not use URLs pointing to development environments in production configuration. A wrong absolute URL can cause the UI to load a document from another host even when the current application returns the right OpenAPI JSON.

## 10. Selecting One Document Among Multiple OpenAPI Groups

When an application has multiple GroupedOpenApi beans, each group has its own document. Example:

~~~java
@Configuration
public class OpenApiGroups {

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

The documents typically have URLs:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
~~~

You can open each URL directly to verify the group:

~~~text
http://localhost:8080/v3/api-docs/public
http://localhost:8080/v3/api-docs/partner
~~~

If a group document returns 404, verify the group name matches **group("...")**, the application started with that bean, and the request path uses the right api-docs base path.

## 11. Displaying a List of Groups in Swagger UI

Multiple documents can be configured in application.yml:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Partner API
        url: /v3/api-docs/partner
    urls-primary-name: Public API
~~~

Swagger UI will display a selector to choose between Public API or Partner API. **urls-primary-name** selects the default document by name in the list; verify the name in the swagger-config response as representation may vary by version.

Each group needs its own URL and must return the right document. Simply declaring names in the UI does not create groups in Springdoc; groups must be registered with GroupedOpenApi or the corresponding configuration mechanism.

## 12. Distinguishing url, urls, and configUrl

Three easily confused fields:

| Field | When to Use |
| --- | --- |
| url | UI loads a single document |
| urls | UI lets users choose among multiple documents |
| configUrl | UI loads the Swagger UI configuration file |

If **urls** is configured, verify each URL in the list is reachable. If **configUrl** points to the wrong place, the UI may fail to load settings even when the OpenAPI document exists.

When troubleshooting, open the config URL directly first. Then take the exact url or each element of urls from the response and open each document. This pinpoints whether the failure is in the config or the document.

## 13. Changing the API Docs Path

Example of changing the OpenAPI endpoint:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~

After restarting the application, check:

~~~text
GET /openapi
GET /openapi.yaml
GET /openapi/swagger-config
~~~

If Swagger UI still uses the old default URL, inspect the config response and update the document source if needed:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
    url: /openapi
~~~

This example uses a single document. If the application uses **urls** for multiple groups, the list configuration must point to the group URLs under the new API docs path.

## 14. Deploying Under a Context Path

Spring Boot MVC can run under a context path:

~~~yaml
server:
  servlet:
    context-path: /catalog
~~~

In this case, public URLs usually carry the /catalog prefix:

~~~text
/catalog/swagger-ui.html
/catalog/v3/api-docs/swagger-config
/catalog/v3/api-docs
~~~

If you set springdoc.api-docs.path: /openapi, the corresponding URL will reside under the context path:

~~~text
/catalog/openapi
~~~

Do not add the context path twice. Distinguish the path configured inside the application from the public URL seen by the browser.

With Spring WebFlux, the base path is usually configured via **spring.webflux.base-path**. Deployment mechanics and servlet-specific properties differ; verify the application's actual web stack.

## 15. Reverse Proxies and Forwarded Headers

In production, an application may run at http://service:8080, while clients access it via https://api.example.com/catalog. A reverse proxy may add prefixes, terminate TLS, and forward requests to the app.

If the application does not handle forwarded headers properly, swagger-config or OpenAPI servers may contain:

- http instead of https.
- An internal host such as service:8080.
- Missing /catalog prefix.
- Absolute URLs pointing to the wrong host or port.

Spring Boot has a property controlling the forwarded headers strategy:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

The appropriate value depends on the reverse proxy, container, and how headers are forwarded. The proxy must set headers such as Forwarded or X-Forwarded-Proto, X-Forwarded-Host, X-Forwarded-Port, and X-Forwarded-Prefix per agreed configuration.

Only trust forwarded headers from trusted proxies. If the application receives requests directly from the internet and accepts client-supplied headers, the inferred host/scheme can be spoofed. Proxy configuration must strip untrusted headers before writing official ones.

After making changes, verify all of the following:

1. swagger-config loaded by the browser.
2. servers in the OpenAPI document.
3. The document's Request URL in Network.
4. The actual URL Swagger UI uses when clicking Try it out.

## 16. Checking Where Try It Out Sends Requests

Swagger UI may load the right document yet send test requests to the wrong base URL. This is usually related to **servers** in OpenAPI.

Example document:

~~~yaml
servers:
  - url: https://api.example.com/catalog
paths:
  /api/books:
    get:
      summary: Search books
~~~

Try it out combines the server URL and path to form the request. If servers is http://localhost:8080, production users might accidentally call localhost on their own machine.

Check:

- servers[0].url in the OpenAPI JSON.
- The Request URL when clicking Execute.
- Scheme, host, port, and prefix.
- Whether the proxy/gateway routes that path to the right service.

If the server URL depends on the environment, configure it via @OpenAPIDefinition(servers = ...), an OpenAPI bean, or an appropriate URL-generation mechanism. Avoid hard-coding production URLs in source shared across all environments.

## 17. Distinguishing Application-Generated Documents and Static Documents

Swagger UI does not have to load the document generated by Springdoc at /v3/api-docs. The UI can also load a static OpenAPI file or a URL from another system.

Example configuring the UI to load a static file:

~~~yaml
springdoc:
  swagger-ui:
    url: /specs/public-api.yaml
~~~

In that case:

- /v3/api-docs may still exist, but it is not the source the UI is using.
- swagger-config.url may point to /specs/public-api.yaml.
- What the UI displays depends on the static file and its caching/hosting.

This is a common reason why editing a controller does not change Swagger UI: the UI is reading a different OpenAPI file. Identify the actual document request before changing code.

## 18. Checking HTTP Status and Content-Type

A properly loaded JSON document usually returns status 200 and a JSON Content-Type, typically application/json. YAML may return application/vnd.oai.openapi or an appropriate content type configured by the version/framework.

Do not conclude an error based solely on Content-Type. Check status, body, and Swagger UI's ability to parse it.

| Status | Meaning to Investigate |
| --- | --- |
| 200 | Request succeeded; verify the body is the right document |
| 301/302/307/308 | Redirect occurred; verify destination is login/proxy/new path |
| 401 | Authentication required or invalid credentials |
| 403 | Reached server but rejected by policy |
| 404 | Wrong path, group, context path, or endpoint disabled |
| 406 | Content negotiation mismatch |
| 500 | Error generating document, converter, bean, or customizer |

If swagger-config returns 200 while the document returns 401/403, the UI may show a specification loading error. Decide whether docs are public or protected and configure authentication consistently for both the config URL and the document URL.

## 19. When Swagger UI Shows the Page but No Operations

Check in order:

1. Is there a request to swagger-config in Network?
2. Does swagger-config have a valid url or urls?
3. Does the document request return status 200?
4. Does the response contain openapi and paths?
5. Does paths contain the expected operations?
6. Is the UI selecting the right group?
7. Does the Console report JSON/YAML parse errors, CORS errors, or $ref resolution errors?

If the document has paths: {} or is missing endpoints, check Springdoc scanning, group path filters, controller mappings, and springdoc.packages-to-scan/paths-to-match if configured.

If the document has operations but the UI fails to render, check that the document is valid, the OpenAPI version is supported by the Swagger UI in use, and all $ref references resolve.

## 20. When swagger-config Returns 404

Common causes:

- springdoc.api-docs.enabled=false.
- springdoc.api-docs.path changed, but UI/config URLs still use the old path.
- Request is missing the context path or proxy prefix.
- Security/gateway rewrites the URL incorrectly.
- The application uses a starter without the expected OpenAPI endpoint.
- Springdoc version is incompatible with Spring Boot/Web stack.

Check the endpoint with curl:

~~~bash
curl -i http://localhost:8080/v3/api-docs/swagger-config
~~~

If this URL returns 404, open /v3/api-docs directly. If both return 404, inspect springdoc.api-docs.path, springdoc.api-docs.enabled, starter dependencies, and startup logs. If /v3/api-docs works but swagger-config is missing, check the path and UI configuration.

## 21. When the Document Returns 401 or 403

If Spring Security protects docs, allow or require proper credentials for these URLs:

- Swagger UI entry point and static assets.
- Swagger config endpoint.
- OpenAPI JSON/YAML endpoints.
- Group URLs if using multiple documents.

Example matcher for public documentation:

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

If documentation is internal, replace permitAll() with an appropriate role/scope and ensure users can fetch both config and document. Allowing only the UI page while blocking swagger-config or OpenAPI JSON still prevents the UI from displaying the API.

If docs sit behind a gateway, verify the gateway applies the same policy to all documentation endpoints. Do not open business APIs just so Swagger UI can load.

## 22. When the UI Still Loads a Stale Document

There are multiple cache layers:

- Browser cache.
- Service worker if the application is a PWA.
- Reverse proxy or CDN.
- Static hosting cache.
- Static OpenAPI file built into the artifact.
- A different group URL than the one you are inspecting.

Procedure:

1. Enable Disable cache in Network and reload.
2. Open the document URL directly in a new tab.
3. Compare response headers such as ETag, Last-Modified, and Cache-Control.
4. Call the document with curl to rule out UI caching.
5. Verify the document host and path in swagger-config.
6. Inspect static files/build artifacts if the UI uses a URL outside Springdoc.

If curl also returns a stale document, the issue lies in the server, proxy, CDN, or deployed artifact; clearing the browser cache will not resolve it.

## 23. Configuring Swagger UI to Disable the Default Petstore URL

Some Swagger UI configurations may fall back to the sample Petstore URL when no desired document URL is configured. You can explicitly disable the default URL:

~~~yaml
springdoc:
  swagger-ui:
    disable-swagger-default-url: true
    url: /v3/api-docs
~~~

Then verify swagger-config points to your application's document. If using multiple groups, declare urls instead of url and confirm the group list.

Do not rely solely on looking at the UI to infer the source. Always inspect the document request in Network because the UI could be displaying an old configured source or a sample URL.

## 24. Verifying with Integration Tests

You can use MockMvc to verify API docs and swagger-config are served:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SwaggerUiBootstrapTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void servesOpenApiDocument() throws Exception {
        String body = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode document = objectMapper.readTree(body);
        assertThat(document.path("openapi").asText()).startsWith("3.");
        assertThat(document.path("paths").isObject()).isTrue();
    }

    @Test
    void servesSwaggerUiConfiguration() throws Exception {
        String body = mockMvc.perform(get("/v3/api-docs/swagger-config"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode config = objectMapper.readTree(body);
        assertThat(
            config.path("url").asText().contains("/v3/api-docs")
            || config.path("urls").isArray()
        ).isTrue();
    }
}
~~~

This example assumes default configuration with a single document. If the project changes api-docs.path, uses groups, or configures a static URL, update assertions to match the actual contract. Tests should not lock onto a default URL when the application intentionally configures a different URL.

## 25. Verifying Groups in Integration Tests

For a public group, test the group URL directly:

~~~java
@Test
void servesPublicGroupDocument() throws Exception {
    String body = mockMvc.perform(get("/v3/api-docs/public"))
        .andExpect(status().isOk())
        .andReturn()
        .getResponse()
        .getContentAsString();

    JsonNode document = objectMapper.readTree(body);
    assertThat(document.path("paths").has("/api/public/books")).isTrue();
    assertThat(document.path("paths").has("/api/internal/jobs")).isFalse();
}
~~~

The test above verifies group content, not document read permissions. If the internal group needs protection, add a separate security test for the /v3/api-docs/internal URL.

## 26. Specification Source Verification Checklist

- [ ] Opened the right Swagger UI entry point.
- [ ] Distinguished the UI URL from the API docs URL.
- [ ] swagger-config loaded successfully.
- [ ] Inspected url or urls in swagger-config.
- [ ] Document URL points to the right host, port, context path, and group.
- [ ] Document request in Network returned 200.
- [ ] Content-Type and body match JSON/YAML.
- [ ] info.title and info.version match the API.
- [ ] paths contains expected endpoints.
- [ ] components.schemas and security schemes are accurate.
- [ ] servers uses the right base URL for the environment.
- [ ] Try it out sends requests to the right host/path.
- [ ] No unintended Petstore URL or development URL remains.
- [ ] Verified context path/reverse proxy if deployed behind a gateway.
- [ ] Checked browser/proxy/CDN caches when seeing stale documents.
- [ ] Integration tests exist for critical documents/configs/groups.

## 27. Quick Troubleshooting Workflow

When users report Swagger UI is blank or showing the wrong API, execute:

1. Open the Swagger UI page and record the full URL.
2. Open swagger-config under the current API docs path.
3. Read url or each element of urls.
4. Open the specified document directly.
5. Verify info, paths, components, and servers.
6. Use Network to check status, redirects, content type, and response body.
7. If the path is wrong, check springdoc.swagger-ui.path, springdoc.api-docs.path, context path, and proxy prefix.
8. If the document is wrong, check url, urls, GroupedOpenApi, and static files.
9. If access is denied, check security for UI/config/document alike.
10. If content is stale, rule out browser cache, then check proxy/CDN/artifact.
11. Write an integration test for the URL and group after fixing.

## Conclusion

Being able to open Swagger UI only confirms the browser can load the interface. To know whether the interface displays the right API, trace swagger-config, inspect the URLs in url/urls, and inspect the OpenAPI JSON/YAML response the browser actually loads. The UI URL, configuration URL, and document URL are three separate components; context paths, groups, reverse proxies, and caches can cause them to diverge.

Check in order: UI → swagger-config → OpenAPI document → servers/Try it out. With concrete evidence from Network or curl, you can pinpoint whether the issue lies in the UI, source configuration, documentation endpoint, routing, or caching without guessing from Swagger UI screenshots.

## References

- [Springdoc OpenAPI — Documentation](https://springdoc.org/)
- [Springdoc OpenAPI — Properties and Swagger UI configuration](https://springdoc.org/properties.html)
- [Springdoc OpenAPI v2 — Properties](https://springdoc.org/v2/)
- [Swagger UI — Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
