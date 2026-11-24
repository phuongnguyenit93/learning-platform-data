# Choosing Scalar Starters and Properties by Supported Springdoc Branch

Springdoc offers multiple starters for Spring Web MVC, Spring WebFlux, the OpenAPI endpoint, Swagger UI, and Scalar. Choosing the wrong starter can leave the application without a documentation UI, load the wrong web stack, or pull in unnecessary dependencies.

Scalar is an API reference UI capable of reading an OpenAPI document and providing a REST API client directly in the browser. Scalar does not replace Springdoc's OpenAPI generator: controllers, annotations, DTOs, and configuration are still used by Springdoc to produce the JSON/YAML specification. Scalar is simply a way to display and interact with that specification, similar to the role of Swagger UI.

To choose the right dependency, determine in order:

1. Whether the application uses Spring Web MVC or Spring WebFlux.
2. Whether only OpenAPI JSON/YAML is needed or a documentation UI is required.
3. If a UI is needed, whether to use Swagger UI, Scalar, or both.
4. Whether the project uses Spring Boot 2, 3, or 4 and the corresponding Springdoc branch.

## 1. Distinguishing Springdoc API, Swagger UI, and Scalar

The three components have distinct responsibilities:

| Component | Responsibility | Common Endpoint |
| --- | --- | --- |
| Springdoc API | Generates and serves the OpenAPI document from the application | /v3/api-docs, /v3/api-docs.yaml |
| Swagger UI | Reads the OpenAPI document and renders an interactive UI | /swagger-ui.html |
| Scalar | Reads the OpenAPI document and renders API Reference plus a REST client | /scalar |

The OpenAPI document is the shared contract. You can expose only the document for CI pipelines or external developer portals without embedding a UI in the application. You can also use either UI or provide both if there is a clear operational reason.

Do not add a UI starter just to get a JSON endpoint. The API-only starter is sufficient to generate the OpenAPI document and avoids unnecessary UI assets.

## 2. Choosing the Springdoc Branch by Spring Boot Version

Before choosing an artifact, check the Spring Boot version in the project. General rule:

| Spring Boot | Springdoc Branch | Notes |
| --- | --- | --- |
| 4.x | Springdoc 3.x | Use the documentation and starters of the 3.x branch |
| 3.x | Springdoc 2.x | Use the documentation and starters of the 2.x branch |
| 2.x or 1.x | Springdoc 1.x | Legacy branch; artifacts use older names |

In the v2 branch documentation, Springdoc 2.10.0 is the version used in module examples. The detailed compatibility matrix also depends on the Spring Boot minor version; for example, Boot 3.5.x uses Springdoc 2.8.x to 2.10.x, Boot 3.4.x uses 2.7.x to 2.8.x, and Boot 3.3.x uses 2.6.x.

Springdoc v1.8.0 is the final legacy release noted by the v1 documentation for Spring Boot 1.x/2.x and has reached end of open-source support. Do not take v1 artifacts and mix them with v2/v3 starters. Likewise, do not use Springdoc 3.x starters for Boot 4 in a Boot 3 application just because 3.x is a newer branch.

## 3. Choosing Between Web MVC and WebFlux

Springdoc provides a matching set of artifacts for each web stack:

| Application Platform | API-only | Swagger UI | Scalar |
| --- | --- | --- | --- |
| Spring Web MVC | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webmvc-scalar |
| Spring WebFlux | springdoc-openapi-starter-webflux-api | springdoc-openapi-starter-webflux-ui | springdoc-openapi-starter-webflux-scalar |

The artifacts in the table apply to the Springdoc v2/v3 starter branches. Choose according to the actual web stack:

- Projects using `spring-boot-starter-web` typically choose the `webmvc` variant.
- Projects using `spring-boot-starter-webflux` typically choose the `webflux` variant.
- Do not add both Web MVC and WebFlux starters at the same time just to get both UI types.

Web MVC and WebFlux have different request-handling models. Choosing the corresponding starter ensures Springdoc registers the right integration for the application's controllers, handler mappings, and resources.

## 4. Starter Decision Table

| Need | Recommended Starter |
| --- | --- |
| Expose only OpenAPI JSON/YAML for CI or another portal | webmvc-api or webflux-api |
| Provide Swagger UI | webmvc-ui or webflux-ui |
| Provide only Scalar UI | webmvc-scalar or webflux-scalar |
| Want both Swagger UI and Scalar | Swagger UI/API starter with Scalar standalone integration; see version conditions below |

For example: a Spring MVC application that only needs to generate an OpenAPI document for a pipeline to download does not need a UI starter. If the development team wants to open a UI directly in the application, choose the UI starter matching the UI product the team wants to use.

## 5. Dependencies for Spring Boot 3 and Springdoc 2.x

For Spring Boot 3 using Spring Web MVC and needing only Scalar, declare:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-scalar</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

For Spring WebFlux, replace the artifact with:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-scalar</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

If only OpenAPI JSON/YAML is needed on Web MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

If Swagger UI is needed on Web MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

The examples above use Springdoc version 2.10.0 to illustrate the Boot 3 branch. Choose a minor version compatible with the project's Spring Boot minor version instead of upgrading Springdoc on its own to a version outside the compatibility matrix.

## 6. Dependencies for Spring Boot 4 and Springdoc 3.x

For Spring Boot 4, use starters from the Springdoc 3.x branch. Artifact names follow the same convention by web stack and UI:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-scalar</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

For WebFlux, use `springdoc-openapi-starter-webflux-scalar`. If only the API document or Swagger UI is needed, choose the corresponding `webmvc-api`/`webflux-api` or `webmvc-ui`/`webflux-ui` artifact.

The example uses `3.2.0` per the current branch documentation at the time of writing. Do not use this version number for Spring Boot 3 projects; Boot 3 requires the Springdoc 2.x branch.

## 7. Managing Dependency Versions with the BOM

Springdoc provides a BOM to synchronize module versions. The BOM has been available since Springdoc 2.8.7; it should be used when the project declares multiple Springdoc artifacts:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-bom</artifactId>
            <version>2.10.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-scalar</artifactId>
    </dependency>
</dependencies>
~~~

For the Springdoc 3.x branch, use the 3.x BOM from the same branch. Do not mix a 2.x BOM with 3.x starters or vice versa.

The Scalar standalone integration is a separate Scalar dependency and is not part of the Springdoc BOM. If the project uses it to combine both UIs, manage the Scalar version independently and inspect the dependency tree to avoid multiple Scalar versions appearing together.

## 8. Springdoc's Dedicated Scalar Starter

If you only want the Scalar UI, choose the dedicated starter:

- `springdoc-openapi-starter-webmvc-scalar` for Spring Web MVC.
- `springdoc-openapi-starter-webflux-scalar` for Spring WebFlux.

This starter integrates Scalar with Spring Boot and Springdoc. The OpenAPI document is still served by Springdoc, typically at `/v3/api-docs`; the Scalar page is typically available at `/scalar`.

Example access flow:

~~~text
Browser
   |
   v
GET /scalar
   |
   v
Scalar UI served by Spring Boot
   |
   v
GET /v3/api-docs
   |
   v
Springdoc returns OpenAPI JSON
   |
   v
Scalar renders API Reference
~~~

There is no need to add the Scalar standalone integration when `springdoc-openapi-starter-webmvc-scalar` or `springdoc-openapi-starter-webflux-scalar` is already selected. These two integration approaches serve different roles; combining both unintentionally can create duplicate auto-configurations or endpoints.

## 9. Configuring Scalar in application.yml

Scalar properties use the `scalar` prefix, not `springdoc.scalar`. Basic configuration example:

~~~yaml
springdoc:
  api-docs:
    path: /v3/api-docs

scalar:
  enabled: true
  path: /scalar
  url: /v3/api-docs
  theme: deepSpace
  layout: modern
  dark-mode: false
  hide-search: false
  hide-models: false
  hide-test-request-button: false
  document-download-type: both
~~~

Meaning of the properties:

| Property | Purpose |
| --- | --- |
| scalar.enabled | Enable or disable the Scalar UI |
| scalar.path | Path of the API Reference page |
| scalar.url | URL of the OpenAPI document that Scalar should read |
| scalar.theme | Color theme of the UI |
| scalar.layout | `modern` or `classic` layout |
| scalar.dark-mode | Initial dark mode state |
| scalar.hide-search | Hide or show the search input |
| scalar.hide-models | Hide or show the schema/model section |
| scalar.hide-test-request-button | Hide or show the send test request feature |
| scalar.document-download-type | Choose to download JSON, YAML, both, or hide the download button |

Specific values and supported enum sets depend on the Scalar version bundled with the starter. If a property does not bind, check the dependency version and property name in the documentation for the exact Scalar version in use.

## 10. Changing the OpenAPI Path and Scalar Path

The two endpoints have separate purposes:

- `springdoc.api-docs.path` changes the OpenAPI JSON URL.
- `scalar.path` changes the Scalar UI page URL.

Example:

~~~yaml
springdoc:
  api-docs:
    path: /openapi

scalar:
  path: /reference
  url: /openapi
~~~

After changing the configuration, expected URLs:

| Content | URL |
| --- | --- |
| Scalar UI | /reference |
| OpenAPI JSON | /openapi |
| OpenAPI YAML | /openapi.yaml |

Do not use `springdoc.swagger-ui.path` to change the Scalar path. That property is for Swagger UI. When using Scalar, adjust `scalar.path`.

When the application has `server.servlet.context-path`, such as `/catalog`, verify the final URL in the browser. Scalar must fetch the right OpenAPI document including the context path, for example `/catalog/openapi`. Relative or absolute URLs should be chosen according to how the application is exposed by the reverse proxy.

## 11. Combining Swagger UI and Scalar from Springdoc 2.10.0

If you want to provide both UIs in a Spring MVC application, you can use Springdoc's Swagger UI starter together with the Scalar standalone integration:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>

<dependency>
    <groupId>com.scalar.maven</groupId>
    <artifactId>scalar-webmvc</artifactId>
    <version>${scalar.version}</version>
</dependency>
~~~

For WebFlux, use `springdoc-openapi-starter-webflux-ui` together with `com.scalar.maven:scalar-webflux`.

Starting from Springdoc 2.10.0, when an application uses another Springdoc starter (Swagger UI or API-only) alongside the Scalar standalone integration, Scalar standalone is enabled by default. You can set `scalar.enabled=false` to disable it or `scalar.url` to point to the OpenAPI document; if no URL is specified, Scalar standalone may display a demo document.

Example:

~~~yaml
scalar:
  enabled: true
  path: /scalar
  url: /v3/api-docs
~~~

Then:

- Swagger UI is typically at `/swagger-ui.html`.
- Scalar UI is at `/scalar`.
- Both read the same OpenAPI document `/v3/api-docs`.

This is the use case for the Scalar standalone integration. Do not add `springdoc-openapi-starter-webmvc-scalar` to this same configuration if the goal is simply having both UIs; pick one clear integration strategy.

## 12. Combining API-Only with Scalar Standalone

Some applications want to keep the backend focused on serving only the API document, while the UI can be added as an independent integration module. With Springdoc 2.10.0 or later, you can combine:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>2.10.0</version>
</dependency>

<dependency>
    <groupId>com.scalar.maven</groupId>
    <artifactId>scalar-webmvc</artifactId>
    <version>${scalar.version}</version>
</dependency>
~~~

Scalar standalone can be enabled separately and pointed to Springdoc's OpenAPI endpoint. This approach is useful when you do not want Swagger UI but still need Scalar. If only Scalar is needed, Springdoc's dedicated `webmvc-scalar` starter is usually the simpler choice.

## 13. Configuring Multiple OpenAPI Documents in Scalar

Scalar can display multiple documents in the same UI through the `sources` configuration if the integrated Scalar version supports this property.

Example:

~~~yaml
scalar:
  enabled: true
  sources:
    - url: /v3/api-docs/public
      title: Public API
      slug: public
    - url: /v3/api-docs/partner
      title: Partner API
      slug: partner
~~~

Each source is an independent OpenAPI document. The title, slug, and URL must match the actual group endpoint generated by Springdoc. If you need to designate a default source, verify the exact property name supported by the Scalar version in use; different integration versions may use `default` or `isDefault`.

Do not declare a global `scalar.url` if you want each source to have its own URL and the frontend to prioritize individual source content. After configuring, check the document selector in Scalar and access permissions for each group endpoint.

## 14. Configuring Scalar Behind a Reverse Proxy

When the application runs behind a reverse proxy, Scalar needs to know the public URL to fetch the right OpenAPI document. Starting from Springdoc 2.9.1 on the v2 branch and 3.1.1 on the v3 branch, the Scalar starter no longer automatically registers `ForwardedHeaderFilter` (Web MVC) or `ForwardedHeaderTransformer` (WebFlux).

If the application sits behind a trusted proxy and needs to process `Forwarded` or `X-Forwarded-*` headers, configure Spring Boot:

~~~properties
server.forward-headers-strategy=framework
~~~

Only enable forwarded header handling when the infrastructure has configured a trusted proxy to strip or overwrite forged headers from clients. Do not let the application directly trust `Forwarded`/`X-Forwarded-*` values sent by arbitrary external clients.

After configuring, verify:

1. The `/scalar` page opens with the public host and scheme.
2. Scalar fetches the right OpenAPI document URL.
3. OpenAPI `servers` in the document point to the appropriate public API address.
4. Test requests from Scalar reach the API server at the right host, port, and context path.

If the Scalar page loads but the document returns 404, usually check the context path, `api-docs.path`, `scalar.url`, and proxy configuration before changing the starter.

## 15. Protecting Scalar and OpenAPI with Spring Security

Scalar UI and the OpenAPI document can expose endpoints, schemas, server URLs, and example requests. For internal APIs, protect both the UI and the document instead of merely hiding UI links.

Example:

~~~java
@Bean
SecurityFilterChain apiDocsSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/scalar", "/scalar/**").hasAuthority("DOCS_READ")
        .requestMatchers("/v3/api-docs", "/v3/api-docs/**", "/v3/api-docs.yaml")
            .hasAuthority("DOCS_READ")
        .anyRequest().authenticated()
    );
    return http.build();
}
~~~

If using a custom OpenAPI path, update the matchers accordingly. If Swagger UI is present, add matchers for `/swagger-ui.html` and `/swagger-ui/**`. Also check `swagger-config` and static resources that the UI needs to load.

Do not allow all documentation endpoints to be publicly accessible just so Scalar can render. If the UI needs to call the OpenAPI document from the browser, both endpoints must have appropriate authentication policies and the browser must be able to send credentials as designed.

## 16. Scalar Authentication and Sensitive Data

Scalar can display authentication options based on the security schemes declared in the OpenAPI document. The scheme name in Scalar configuration must match the scheme name in `components.securitySchemes` exactly.

For example, if OpenAPI has an HTTP bearer scheme named `BearerAuth`, Scalar must reference `BearerAuth` specifically, not invent a different name.

Never put real access tokens, API keys, or client secrets into Scalar configuration sent to the browser. Values prefilled in the UI can be observed by any user with permission to open the page. Prefill features should only be used in dev/test environments with dummy or scoped credentials.

Scalar does not replace Spring Security. Having an Authorize or Test Request button in the UI does not mean the runtime API is protected. `SecurityFilterChain`, OAuth2 resource server, and endpoint authorization policies must still be configured separately.

## 17. Scalar Properties to Choose by Goal

There is no need to enable every option. Select properties according to documentation readers' needs:

| Goal | Suggested Property | Notes |
| --- | --- | --- |
| Change the UI path | scalar.path | Not `springdoc.swagger-ui.path` |
| Specify the OpenAPI document | scalar.url | Must point to an endpoint being served |
| Choose light/dark theme | scalar.theme, scalar.dark-mode | Theme values depend on the Scalar version |
| Hide schemas from sidebar | scalar.hide-models | Changes presentation only |
| Hide the search bar | scalar.hide-search | Does not change OpenAPI content |
| Hide the send request button | scalar.hide-test-request-button | Does not replace server-side authorization |
| Choose document download type | scalar.document-download-type | `json`, `yaml`, `both`, or `none` depending on version |
| Sort operations/tags | scalar.operation-sorter, scalar.tag-sorter | Check enum values for the version |

Property names can be accepted by Spring Boot relaxed binding in either kebab-case or camelCase. However, use one style consistently in `application.yml` and consult the Scalar documentation matching the locked dependency.

## 18. Common Starter Selection Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| No `/v3/api-docs` | Only added external UI or API endpoint is disabled | Choose the appropriate API starter and check `springdoc.api-docs.enabled` |
| No `/scalar` | Used API-only or Swagger UI starter without adding Scalar integration | Choose the Scalar starter or integrate `scalar-webmvc`/`webflux` per version |
| WebFlux app with `webmvc-scalar` added | Wrong web stack selected | Replace with `webflux-scalar` |
| Scalar displays demo documentation | `scalar.url` does not yet point to the OpenAPI document | Configure `scalar.url` to the right endpoint |
| Scalar reports 404 when loading document | `api-docs.path`, context path, or proxy URL mismatch | Compare URLs in the Network tab |
| Both Swagger UI and Scalar are unstable | Mixed dedicated Scalar starter with standalone integration | Choose one integration model; if both are needed, use UI/API starter with Scalar standalone from v2.10.0 |
| Dependency not found | Used v2/v3 artifact names on the v1 branch | Use the right compatible branch or upgrade |
| `NoSuchMethodError`/`ClassNotFound` error | Springdoc modules have mismatched versions or Scalar dependencies conflict | Use the BOM for the right branch and inspect the dependency tree |
| Wrong Scalar host behind proxy | Forwarded headers are not handled or not trusted | Configure proxy and `server.forward-headers-strategy` properly |
| Scalar UI opens but test requests fail | Incorrect API security, CORS, or server URL | Check browser network, CORS, and security policy |
| Changing theme has no effect | Theme value is not in the Scalar version's enum | Look up the theme list for the exact version |

## 19. Verification After Adding the Starter

After the application starts, check in order:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
curl -I http://localhost:8080/scalar
~~~

If using custom paths, replace the URLs with configured values. For Scalar UI, also inspect the request fetching the OpenAPI document in the browser's Network tab.

Items to verify:

1. OpenAPI JSON returns HTTP 200 and contains `openapi`, `info`, `paths`.
2. OpenAPI YAML returns the right content type and corresponding content.
3. Scalar UI returns HTML and successfully loads JavaScript/CSS.
4. Scalar fetches the right document URL, not the demo spec.
5. Operations and schemas display accurately.
6. Test Request calls the right API server and handles authentication as intended.
7. When Spring Security is enabled, unauthorized users cannot read internal documentation.

You can use an integration test to verify the endpoints:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ApiDocumentationEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void openApiDocumentIsAvailable() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ))
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$.paths").exists());
    }

    @Test
    void scalarPageIsAvailable() throws Exception {
        mockMvc.perform(get("/scalar"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_HTML));
    }
}
~~~

The Scalar page test may need adjustments depending on how resource handlers and redirects are implemented in the version in use. If the page returns a redirect, check the `Location` header and follow the redirect rather than concluding the starter is broken.

## 20. Starter Selection and Scalar Configuration Checklist

- [ ] Identified the Spring Boot version and compatible Springdoc branch.
- [ ] Not using Springdoc 2.x for Spring Boot 4 or Springdoc 3.x for Spring Boot 3.
- [ ] Identified whether the application uses Spring Web MVC or WebFlux.
- [ ] Chosen API-only, Swagger UI, or Scalar according to requirements.
- [ ] Scalar artifact matches the web stack: `webmvc-scalar` or `webflux-scalar`.
- [ ] Springdoc modules use the same version or BOM from the same branch.
- [ ] Not adding both the dedicated Scalar starter and Scalar standalone integration without a clear design.
- [ ] If both Swagger UI and Scalar are needed, verified standalone integration conditions from Springdoc 2.10.0 onward.
- [ ] Scalar properties use the `scalar` prefix, not confused with `springdoc.swagger-ui`.
- [ ] `scalar.url` points to the right OpenAPI JSON document.
- [ ] `scalar.path` does not conflict with application routes.
- [ ] Checked context path, reverse proxy, and forwarded headers.
- [ ] Security protects both the Scalar page and the OpenAPI document per system policy.
- [ ] No real tokens or secrets placed in prefill configuration exposed to the browser.
- [ ] Verified `/v3/api-docs`, `/v3/api-docs.yaml`, and `/scalar`.

Choosing the right starter begins with the web stack and UI requirements, then moves to Scalar properties. For Spring Boot 3 use Springdoc 2.x; for Boot 4 use Springdoc 3.x; the v1 branch is legacy and uses older artifact names. If only Scalar is needed, prefer Springdoc's dedicated Scalar starter. If both Swagger UI and Scalar are needed, use the Scalar standalone model per the instructions for the exact branch and version. Finally, verify the OpenAPI URL, proxy, and security so the UI renders the right documentation without inadvertently exposing internal contracts.

## References

- [Springdoc OpenAPI v2 — Modules and Scalar support](https://springdoc.org/v2/modules.html)
- [Springdoc OpenAPI v2 — Properties](https://springdoc.org/v2/properties.html)
- [Springdoc OpenAPI v2 — Migration from v1](https://springdoc.org/v2/migrating-from-springdoc-v1.html)
- [Springdoc OpenAPI — Current modules](https://springdoc.org/modules.html)
- [Springdoc OpenAPI v1 — Legacy documentation](https://springdoc.org/v1/)
- [Scalar — Java integration](https://scalar.com/products/api-references/integrations/java)
