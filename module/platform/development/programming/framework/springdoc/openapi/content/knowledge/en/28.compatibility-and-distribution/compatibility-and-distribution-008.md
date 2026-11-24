# Publishing Multiple Versions or Groups on One UI

A Spring Boot system can maintain multiple API versions simultaneously, segment documentation by user group, or aggregate docs across multiple services. If each document has its own separate URL, developers must remember multiple addresses and switch between pages. `springdoc-openapi` and Swagger UI support publishing distinct OpenAPI documents inside a single UI, where users select the document to view from a dropdown list.

Two parts need coordination:

- **Generating each OpenAPI document:** use `GroupedOpenApi` or `springdoc.group-configs` to restrict packages, paths, and mapping conditions for each group.
- **Displaying the documents:** Swagger UI takes a list of document URLs and displays a selector in the top bar. For internal groups managed by `springdoc`, groups are registered into Swagger UI config; for external documents or static files, you can declare `springdoc.swagger-ui.urls`.

One interface can let users pick among multiple documents, yet each selection still loads a separate OpenAPI document. This selector does not merge APIs into one unified specification. If you need a single merged contract file for publishing or SDK generation, add a separate merge step in the pipeline.

## 1. Distinguishing API version, OpenAPI version, and group

Before configuring, distinguish concepts that are often loosely called "version":

| Concept | Example | Meaning |
|---|---|---|
| API version | `/api/v1/orders`, `/api/v2/orders` | Contract version used by clients |
| OpenAPI Specification version | `openapi: 3.1.1` | Syntax and rule version of the OpenAPI specification |
| Document version | `info.version: 2.4.0` | Version of the API document released by the team |
| Group | `orders-v1`, `admin`, `partner` | A view or subset of operations selected to form a document |
| `springdoc` version | `2.x`, `3.x` | Version of the documentation library, coupled to Spring Boot |

A group does not automatically create a new API version. For example, a `partner` group may hold partner endpoints across multiple domains; an `orders-v1` group may hold only version 1 of the orders API. The development team decides the name, scope, and lifecycle of each group.

The `openapi` field in the document is also not the API version. Both v1 and v2 API documents can perfectly well use OpenAPI 3.1. One document can set `info.version` to `1.8.0` while its API paths contain `/v1`.

## 2. Multi-document model in a single Swagger UI

Suppose an application has three documents:

| Display Name | Scope | OpenAPI URL |
|---|---|---|
| Orders API v1 | Legacy contract for clients not yet upgraded | `/v3/api-docs/orders-v1` |
| Orders API v2 | Current contract | `/v3/api-docs/orders-v2` |
| Admin API | Operations for administrators | `/v3/api-docs/admin` |

Users open one Swagger UI page, then pick a document from the top-bar selector:

~~~mermaid
flowchart TD
    B[Developer opens /swagger-ui.html]
    U[Swagger UI and document selector]
    V1[/v3/api-docs/orders-v1]
    V2[/v3/api-docs/orders-v2]
    A[/v3/api-docs/admin]
    B --> U
    U -->|Select Orders v1| V1
    U -->|Select Orders v2| V2
    U -->|Select Admin| A
~~~

Each URL returns an independent OpenAPI document. When switching documents, Swagger UI fetches the corresponding specification and renders that document's operations. Document URLs may reside in the same application or come from other services.

## 3. Creating versioned groups with `GroupedOpenApi`

The direct approach in Java is declaring one `GroupedOpenApi` bean per group. Each group requires a unique name and can filter by path, package, or both.

Suppose controllers are organized by URL:

~~~text
/api/v1/orders/**
/api/v2/orders/**
/admin/**
~~~

Configuration:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi ordersV1Api() {
        return GroupedOpenApi.builder()
            .group("orders-v1")
            .pathsToMatch("/api/v1/orders/**")
            .build();
    }

    @Bean
    GroupedOpenApi ordersV2Api() {
        return GroupedOpenApi.builder()
            .group("orders-v2")
            .pathsToMatch("/api/v2/orders/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .packagesToScan("com.acme.api.admin")
            .pathsToMatch("/admin/**")
            .build();
    }
}
~~~

Springdoc generates default URLs:

| Group | URL |
|---|---|
| `orders-v1` | `/v3/api-docs/orders-v1` |
| `orders-v2` | `/v3/api-docs/orders-v2` |
| `admin` | `/v3/api-docs/admin` |

The group name becomes part of the document URL. Use stable, readable names that contain no environment-specific details such as hostnames or ports. If a group filters by both package and path, an operation must belong to a scanned package and match the path.

Internal groups registered by `springdoc` appear in Swagger UI configuration for users to pick. Do not re-declare internal group URLs via `springdoc.swagger-ui.urls` just to create an identical duplicate selector.

## 4. Creating groups via `application.yml`

If you prefer managing groups in Spring Boot configuration, use `springdoc.group-configs`. When configuring this way, do not declare a duplicate `GroupedOpenApi` bean for the same group.

~~~yaml
springdoc:
  group-configs:
    - group: orders-v1
      display-name: Orders API v1
      paths-to-match:
        - /api/v1/orders/**

    - group: orders-v2
      display-name: Orders API v2
      paths-to-match:
        - /api/v2/orders/**

    - group: admin
      display-name: Admin API
      packages-to-scan:
        - com.acme.api.admin
      paths-to-match:
        - /admin/**
      paths-to-exclude:
        - /admin/internal/**
~~~

`group` is the identifier used in the document URL. `display-name` is the UI display label if the `springdoc` version in use supports this property. `paths-to-match`, `paths-to-exclude`, `packages-to-scan`, and `packages-to-exclude` scope the group's operations.

You can configure profile-specific lists if environments expose different groups. However, avoid making production docs depend on a developer-only profile; define clearly which groups constitute released contracts.

### Choosing Java beans or YAML?

| Need | Suitable Approach |
|---|---|
| Fixed group scope requiring Java customizers | `GroupedOpenApi` bean |
| Group list is mostly package/path filters varying by config | `springdoc.group-configs` |
| Per-group metadata or document customization needed | `GroupedOpenApi` combined with `OpenApiCustomizer` |
| Only pulling external service documents into Swagger UI | `springdoc.swagger-ui.urls` |

Pick one clear configuration source per group. Avoid declaring the same group name in both a bean and YAML without specific reason, as maintainers will struggle to tell which configuration governs the document.

## 5. Attaching per-version metadata

Two API versions should have clearly distinguishable titles and `info.version` values. You can attach an `OpenApiCustomizer` to each `GroupedOpenApi`:

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class VersionedOpenApiConfiguration {

    @Bean
    GroupedOpenApi ordersV1Api() {
        return GroupedOpenApi.builder()
            .group("orders-v1")
            .pathsToMatch("/api/v1/orders/**")
            .addOpenApiCustomizer(openApi -> {
                if (openApi.getInfo() == null) {
                    openApi.setInfo(new Info());
                }
                openApi.getInfo()
                    .title("Orders API")
                    .version("1.8.0")
                    .description("Orders API v1 contract.");
            })
            .build();
    }

    @Bean
    GroupedOpenApi ordersV2Api() {
        return GroupedOpenApi.builder()
            .group("orders-v2")
            .pathsToMatch("/api/v2/orders/**")
            .addOpenApiCustomizer(openApi -> {
                if (openApi.getInfo() == null) {
                    openApi.setInfo(new Info());
                }
                openApi.getInfo()
                    .title("Orders API")
                    .version("2.4.0")
                    .description("Orders API v2 contract.");
            })
            .build();
    }
}
~~~

The customizers in this example are bound directly to their respective groups, keeping v1 and v2 metadata independent. If using a shared application-wide `OpenAPI` bean or global customizer, check its scope so it does not unintentionally overwrite `info` across groups.

`info.version` should follow the team's document release rules. It can be a semantic version like `2.4.0`; it does not have to match the group name or the `v2` path segment.

## 6. Adding multiple documents to Swagger UI with `urls`

When you need explicit control over the document list—especially when documents originate from external services or static OpenAPI files—use `springdoc.swagger-ui.urls`.

~~~yaml
springdoc:
  swagger-ui:
    path: /swagger-ui.html
    urls:
      - name: Customer API v1
        url: https://customer-api.example.com/v3/api-docs/v1
      - name: Customer API v2
        url: https://customer-api.example.com/v3/api-docs/v2
      - name: Billing API
        url: https://billing-api.example.com/v3/api-docs
    urls-primary-name: Customer API v2
~~~

Meaning of properties:

- `urls`: list of documents Swagger UI can fetch and display in the selector.
- `urls[].name`: unique display name of the document in the UI.
- `urls[].url`: URL called by the browser to fetch the OpenAPI document; URLs in the list must be unique.
- `urls-primary-name`: name of the document selected by default when Swagger UI loads.
- `path`: path to the Swagger UI HTML page, defaulting to `/swagger-ui.html`.

When `urls` is configured, the single `springdoc.swagger-ui.url` property is ignored. Do not declare both `url` and `urls` expecting them to merge.

### When should `urls` be configured manually?

| Document Source | How to Configure |
|---|---|
| Internal group created via `GroupedOpenApi` | Springdoc registers the group in Swagger UI config |
| Internal group created via `springdoc.group-configs` | Springdoc registers the group in Swagger UI config |
| OpenAPI endpoint from another service | Declare absolute URL in `springdoc.swagger-ui.urls` |
| Static OpenAPI file served by the app | Declare file URL in `springdoc.swagger-ui.urls` |
| Only one static OpenAPI file | Can use `springdoc.swagger-ui.url` |

If manually declaring `urls` for both internal groups and external docs, ensure every document appears only once with unique names and URLs.

## 7. Aggregating documentation from multiple microservices

A developer portal can host a dedicated Swagger UI instance that fetches documents from multiple services:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Identity
        url: https://identity.example.com/v3/api-docs
      - name: Catalog
        url: https://catalog.example.com/v3/api-docs
      - name: Orders
        url: https://orders.example.com/v3/api-docs
      - name: Payments
        url: https://payments.example.com/v3/api-docs
    urls-primary-name: Catalog
~~~

In this model:

- The developer portal serves the Swagger UI page.
- Each microservice remains responsible for generating and publishing its own OpenAPI document.
- Swagger UI loads one document based on user selection.
- Each document can define its own `servers` pointing to the corresponding API host.

This aggregates multiple documents into a single UI. It does not produce a merged OpenAPI document and does not replace an API gateway.

### Configuring CORS on document-providing services

If Swagger UI and the OpenAPI endpoint are on different origins, browsers enforce CORS. The service hosting the document must allow the developer portal's origin to read the OpenAPI endpoint.

Spring MVC configuration example on the document-providing service:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class OpenApiCorsConfiguration {

    @Bean
    WebMvcConfigurer openApiCorsConfigurer() {
        return new WebMvcConfigurer() {
            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/v3/api-docs/**")
                    .allowedOrigins("https://developer.example.com")
                    .allowedMethods("GET")
                    .allowedHeaders("Accept", "Authorization");
            }
        };
    }
}
~~~

Configure CORS on the server that actually serves the OpenAPI document. If users also click Try it out to invoke the API from a browser, business endpoints need matching CORS policies too. CORS for documentation and CORS for API operations are two distinct request flows.

Do not open CORS to every origin in production just so Swagger UI works. Allow only known developer portal origins, required methods, and required headers; combine CORS with authentication and authorization.

## 8. Serving static OpenAPI files alongside the UI

Sometimes the team publishes documents built and verified in CI and does not want Swagger UI depending on a runtime doc-generation endpoint. You can place OpenAPI files inside static resources:

~~~text
src/main/resources/
└── static/
    └── openapi/
        ├── orders-v1.yaml
        ├── orders-v2.yaml
        └── billing-v3.yaml
~~~

When the application serves static resources, the files are accessible at:

~~~text
/openapi/orders-v1.yaml
/openapi/orders-v2.yaml
/openapi/billing-v3.yaml
~~~

Register them in Swagger UI:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Orders API v1
        url: /openapi/orders-v1.yaml
      - name: Orders API v2
        url: /openapi/orders-v2.yaml
      - name: Billing API v3
        url: /openapi/billing-v3.yaml
    urls-primary-name: Orders API v2
~~~

Static files must be valid OpenAPI documents, and URLs must be reachable from the browser. If the application runs behind a context path, reverse proxy, or custom prefix, URLs in `urls` must include that public path.

With a single static file, you can use:

~~~yaml
springdoc:
  swagger-ui:
    url: /openapi/orders-v2.yaml
~~~

Only use single `url` when `urls` is not configured.

## 9. Distinguishing the document fetch URL from the `servers` URL inside the document

These two URLs are frequently confused:

- `springdoc.swagger-ui.urls[].url`: where Swagger UI downloads the OpenAPI file.
- `servers[].url` inside the OpenAPI document: the base URL of the API that users call via Try it out or clients.

For example, Swagger UI fetches the document from a portal:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Orders v2
        url: https://docs.example.com/specs/orders-v2.yaml
~~~

Inside `orders-v2.yaml`, the server may be:

~~~yaml
openapi: 3.1.1
info:
  title: Orders API
  version: 2.4.0
servers:
  - url: https://api.example.com/api/v2
paths:
  /orders:
    get:
      responses:
        '200':
          description: Order list
~~~

Swagger UI fetches the document from `docs.example.com`, while Try it out requests go to `api.example.com`. The two hosts can differ and require separate access, CORS, TLS, and authentication setup.

When deploying behind a reverse proxy, verify `servers` in each document points to a browser-accessible public URL. Do not use internal container-network URLs if developers access Swagger UI externally.

## 10. API versions sharing a path or using headers

Many systems version APIs via path such as `/api/v1/**` and `/api/v2/**`; this is the easiest way to split groups because every version has a clear URL.

Some systems use a header to select versions:

~~~java
@GetMapping(
    path = "/api/orders",
    headers = "X-API-Version=v1"
)
public List<OrderV1Response> listV1() {
    return orderService.listV1();
}

@GetMapping(
    path = "/api/orders",
    headers = "X-API-Version=v2"
)
public List<OrderV2Response> listV2() {
    return orderService.listV2();
}
~~~

In this case, you can separate documents using the group's header condition:

~~~java
@Bean
GroupedOpenApi ordersV1Api() {
    return GroupedOpenApi.builder()
        .group("orders-v1")
        .pathsToMatch("/api/orders")
        .headersToMatch("X-API-Version=v1")
        .build();
}

@Bean
GroupedOpenApi ordersV2Api() {
    return GroupedOpenApi.builder()
        .group("orders-v2")
        .pathsToMatch("/api/orders")
        .headersToMatch("X-API-Version=v2")
        .build();
}
~~~

Each group can describe the same path and HTTP method with different schemas in its own document. However, Spring's mapping header condition does not automatically guarantee the header appears as a request parameter in OpenAPI. If consumers must send the version header, declare it explicitly with `@RequestHeader` or `@Parameter(in = ParameterIn.HEADER)` and verify in the document.

Within a single OpenAPI document, a path + HTTP method pair can have only one operation. You cannot represent two handler methods with different schemas for the same path/method merely by overloading them in one document. Split them into two groups or use distinct versioned paths.

## 11. Organizing groups by consumer and access permissions

Groups can represent versions, domains, or audiences:

| Group | Content | Consumers |
|---|---|---|
| `public-v2` | Public API version 2 | Customers and partners |
| `partner` | Endpoints dedicated to integration partners | Partner developers |
| `admin` | Administrative endpoints | Operations team |
| `internal` | Service-to-service endpoints | Internal developers |

Include only the necessary operations in each document. Use package/path filters to avoid leaking internal endpoints into public docs.

Groups are not a security boundary. Hiding a document from Swagger UI does not stop users from calling an endpoint if runtime does not protect that endpoint. If internal docs must not be public, protect both the Swagger UI page and `/v3/api-docs/{group}` endpoints with Spring Security, an API gateway, or organizational access controls.

If a portal aggregates documents from other services, each service must still enforce read permissions on its own documents. CORS only governs whether browsers can read cross-origin responses; it does not authenticate users and does not replace authorization.

## 12. Maintaining multiple versions across the API lifecycle

When publishing v1 and v2 concurrently, establish a clear lifecycle policy:

1. Keep the v1 document stable for clients that have not upgraded.
2. Publish v2 with its own group name and `info.version`.
3. Mark old operations `deprecated` when starting the retirement roadmap.
4. State the expected end-of-support date in descriptions or release notes.
5. Monitor remaining v1 consumers before removing endpoints and documents.
6. Retain OpenAPI artifacts of older releases for reference and ongoing client support.

Example of marking an old operation:

~~~java
@Operation(
    summary = "Get legacy order",
    deprecated = true
)
@GetMapping("/api/v1/orders/{id}")
public OrderV1Response getOrderV1(@PathVariable long id) {
    return orderService.getV1(id);
}
~~~

`deprecated = true` signals consuming tools that the operation should not be used for new integrations. It does not automatically disable the endpoint or notify clients; the team still needs a migration plan and release notices.

## 13. Verifying Swagger UI and each individual document

After configuring, check each URL individually rather than only opening the Swagger UI page.

Fetch the v1 document:

~~~bash
curl -i http://localhost:8080/v3/api-docs/orders-v1
~~~

Fetch the v2 document:

~~~bash
curl -i http://localhost:8080/v3/api-docs/orders-v2
~~~

Inspect the Swagger UI config served by `springdoc`:

~~~bash
curl -s http://localhost:8080/v3/api-docs/swagger-config
~~~

With an explicit URL list, the config response should contain the exact names and URLs of the documents. Then open:

~~~text
http://localhost:8080/swagger-ui.html
~~~

Verify:

- The selector displays the exact document names.
- The default document is the intended version.
- Selecting v1 shows only v1 operations.
- Selecting v2 shows only v2 operations.
- Each document renders cleanly with accurate schemas and security schemes.
- Try it out calls the `servers` belonging to the currently selected document.

If using a context path such as `/shop`, public URLs carry the corresponding prefix such as `/shop/v3/api-docs/orders-v1` and `/shop/swagger-ui.html`. When configuring `urls` manually, use the URL browsers actually reach after passing through proxies.

## 14. Testing group lists and operation scope

Use integration tests to verify each group returns the right document:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiGroupsTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void ordersV1DocumentContainsOnlyV1Paths() throws Exception {
        mockMvc.perform(get("/v3/api-docs/orders-v1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/v1/orders']").exists())
            .andExpect(jsonPath("$.paths['/api/v2/orders']").doesNotExist());
    }

    @Test
    void ordersV2DocumentContainsOnlyV2Paths() throws Exception {
        mockMvc.perform(get("/v3/api-docs/orders-v2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/v2/orders']").exists())
            .andExpect(jsonPath("$.paths['/api/v1/orders']").doesNotExist());
    }
}
~~~

If groups share a path using header versioning, assertions should check the exact operation, header parameter, and schema of each document. Do not only check that the docs endpoint returns `200`; a document can be syntactically valid yet contain the wrong operations.

For manual `urls` configuration, inspect the `/v3/api-docs/swagger-config` response or run a browser smoke test to confirm the top bar receives the expected list. Document API tests and UI tests complement each other.

## 15. Releasing versioned OpenAPI artifacts

For important APIs, store OpenAPI documents as release artifacts:

~~~text
openapi/
├── orders/
│   ├── v1/
│   │   └── openapi.yaml
│   └── v2/
│       └── openapi.yaml
└── billing/
    └── v3/
        └── openapi.yaml
~~~

A pipeline can:

1. Start the application or use a build-time tool to extract OpenAPI documents.
2. Fetch each group's document.
3. Validate syntax and OpenAPI version.
4. Run lint rules and contract diffs against the previous release's artifact.
5. Save files under immutable API versions.
6. Update the Swagger UI list to point to the published artifacts.

Keep old release URLs stable throughout the client support window. Aliases like `latest` or `current` can exist, but aliases must be updated under control and must not replace specific versioned artifacts.

If documents are fetched from external microservices, the portal must handle unavailable services or transient URL failures gracefully. Do not let one unavailable service wipe out cached documentation for all other services.

## 16. Common mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Swagger UI shows only one document | Only single `url` configured, or groups not registered | Create `GroupedOpenApi`/`group-configs` or configure `urls` list |
| `/v3/api-docs/{group}` returns 404 | Wrong group name or group not created | Check group name, bean scanning, and group config |
| Two documents share the same name in selector | Duplicate `group` or `urls[].name` | Assign unique group names and URL labels |
| Duplicate document URL | Multiple `urls` entries point to the same URL | Each URL in the list must be unique |
| Selecting v1 displays v2 endpoints | `paths-to-match` too broad or wrong package filter | Narrow paths/packages and inspect JSON document |
| Empty group | Path/package does not match actual mappings | Compare request mappings against group filters |
| Cross-domain `urls` fail to load | CORS does not allow Swagger UI origin or URL is private | Configure CORS on doc-serving service and test URL from browser |
| Document loads yet Try it out fails CORS | API server blocks portal origin on business endpoints | Configure separate CORS for API operations |
| Swagger UI still opens old document | Mismatched `urls-primary-name` or stale browser cache | Check `/v3/api-docs/swagger-config`, URLs, and cache |
| `springdoc.swagger-ui.url` has no effect | `springdoc.swagger-ui.urls` is also configured | Use single `url` only when `urls` is absent |
| Document displays yet requests hit wrong host | `servers[].url` in OpenAPI is not the public API URL | Update server URL or configure proxy/forwarded headers |
| Swagger UI fails to render a document | Current UI lacks support for the document's OpenAPI version/features | Verify Swagger UI compatibility and run validator per document |
| Internal docs remain directly accessible | Only hid group in UI without securing doc endpoint | Enforce authentication/authorization on UI and `/v3/api-docs/**` |
| Mixed bean and YAML config behaves unpredictably | Same group declared in multiple sources | Pick one configuration source per group |
| Upgrading v2 breaks v1 clients | v1 controller/schema modified simultaneously | Separate implementations and artifacts by version; preserve old contract during support |

## 17. Workflow for designing a multi-version documentation UI

Follow this sequence:

1. List all API versions, domains, and consumers to publish.
2. Decide whether groups represent versions, consumers, or domains.
3. Choose paths or packages to partition operations cleanly.
4. Create each document using `GroupedOpenApi` or `springdoc.group-configs`.
5. Set appropriate `info.title`, `info.version`, description, and `servers` per document.
6. Verify `/v3/api-docs/{groupName}` URLs and operation scope.
7. Use the Swagger UI group selector for internal groups; use `springdoc.swagger-ui.urls` for external docs or static files.
8. Select the default document via `urls-primary-name` when using an explicit URL list.
9. Check CORS, authentication, context paths, and public URLs when external services or reverse proxies are involved.
10. Validate each document, run contract diffs, and archive artifacts per release.
11. Manage legacy version lifecycles, deprecation, and end-of-support dates.

Keep configuration concise relative to the number of documents genuinely needing publication. Overly broad groups mix unrelated contracts; too many tiny groups clutter the selector. Group names should clearly indicate domain and version.

## 18. Pre-publication checklist

- [ ] Every group has a unique name and deterministic document URL.
- [ ] Package/path filters accurately reflect each group's operation scope.
- [ ] API versions have distinct `info.version` and metadata.
- [ ] OpenAPI Specification version is kept distinct from API version.
- [ ] Internal groups and YAML groups are not duplicated across sources.
- [ ] Swagger UI displays all intended groups.
- [ ] `urls` list has unique names and URLs.
- [ ] `urls-primary-name` selects the right default document when `urls` is used.
- [ ] Document fetch URLs and `servers[].url` are verified separately.
- [ ] External documents have proper CORS on the document-providing side.
- [ ] API operations have proper CORS if Try it out makes cross-origin calls.
- [ ] Docs and Swagger UI are protected per access policy.
- [ ] Every document is validated and contract-diffed prior to release.
- [ ] Artifacts of older versions are retained throughout their support window.
- [ ] Legacy APIs have deprecation and consumer migration plans.

## 19. Official References

- [springdoc-openapi FAQ — Multiple OpenAPI definitions](https://springdoc.org/faq.html) — creating multiple `GroupedOpenApi` beans, `/v3/api-docs/{groupName}` URLs, and YAML group configuration.
- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html) — `springdoc.group-configs`, `springdoc.swagger-ui.urls`, `urlsPrimaryName`, `url`, `configUrl`, and Swagger UI properties.
- [springdoc-openapi Getting Started](https://springdoc.org/getting-started.html) — dependencies integrating Swagger UI and JSON/YAML endpoints.
- [Swagger UI Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/) — configuring Swagger UI URL lists and top bar.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html) — configuring CORS in Spring MVC.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html) — structure of `info`, `servers`, `paths`, and OpenAPI document components.

A single Swagger UI can serve as a shared portal across multiple API versions, groups, or services. Generate independent documents with stable names, configure the appropriate selector, and verify document fetch URLs, server URLs, CORS, and access control. This lets developers switch between contracts within one interface while keeping each API's boundaries and lifecycle clear.
