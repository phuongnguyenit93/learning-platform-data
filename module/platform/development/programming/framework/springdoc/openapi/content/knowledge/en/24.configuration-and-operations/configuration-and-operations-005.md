# Restricting Packages, Paths, Media Types, and Headers Included in Documentation

In a Spring Boot application, not every controller falls within the API publication scope for the same user audience. An application may contain public endpoints, administrative endpoints, internal APIs, web UI routes, and health-check-only routes. If springdoc is left to scan all endpoints by default, the OpenAPI document can include many operations not meant for the consumer viewing the documentation.

springdoc-openapi provides filters to restrict which operations are included in the specification by Java package, URL path, request/response media types, and mapping header conditions. These filters affect the **generated documentation**; they do not alter runtime routes and do not replace Spring Security. Understanding that boundary prevents mistakenly treating hiding an endpoint in Swagger UI as a security measure.

## 1. At What Stage Are Filters Applied?

Simplified documentation-generation flow:

1. Spring Boot initializes Spring-managed controllers and request mappings.
2. springdoc collects describable endpoints.
3. Filters evaluate package, path, consumes, produces, and header conditions.
4. Matching operations are included in the OpenAPI document.
5. Swagger UI or other consumers read the generated document.

For example, suppose an application has the following controllers:

| Controller | Package | Path | Purpose |
|---|---|---|---|
| `PublicOrderController` | `com.acme.api.publicapi` | `/api/v1/orders/**` | Partner API |
| `AdminOrderController` | `com.acme.api.admin` | `/admin/orders/**` | Admin API |
| `InternalHealthController` | `com.acme.internal.health` | `/internal/health` | Internal checks |
| `WebPageController` | `com.acme.web` | `/pages/**` | HTML pages, not a public REST API |

Partner documentation should contain only the first endpoint group. You can restrict packages and paths to avoid including the remaining controllers in the document. If the application needs multiple independent documents, create groups instead of trying to rely on one global configuration for every consumer.

## 2. Common Filtering Properties

Core properties use the `springdoc` prefix:

| Property | Purpose | Default Value Documented by springdoc |
|---|---|---|
| `springdoc.packages-to-scan` | Specifies packages to scan | `*` |
| `springdoc.packages-to-exclude` | Excludes packages from scanning | Not set |
| `springdoc.paths-to-match` | Specifies paths to include in the document | `/*` |
| `springdoc.paths-to-exclude` | Excludes paths from the document | Not set |
| `springdoc.consumes-to-match` | Filters by request media types accepted by the mapping | `/*` |
| `springdoc.produces-to-match` | Filters by response media types declared by the mapping | `/*` |
| `springdoc.headers-to-match` | Filters by request mapping header conditions | `/*` |

Similar filters can also be configured individually per API group under `springdoc.group-configs`. Within a group, multiple values in a list allow specifying multiple packages, paths, or media types to match. When combining multiple filter types, an endpoint must satisfy the package/path scope as well as the corresponding mapping conditions.

Note: `springdoc.default-consumes-media-type` and `springdoc.default-produces-media-type` set default media types for descriptions, not endpoint selection filters. Do not confuse them with `consumes-to-match` and `produces-to-match`.

## 3. Restricting Controllers by Package

`packages-to-scan` limits which packages containing Spring controllers are inspected by springdoc. This is useful when source code is organized by bounded context or API group.

Example including only controllers in public API packages:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.api.publicapi
    - com.acme.api.shared
~~~

You can exclude internal packages:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.api
  packages-to-exclude:
    - com.acme.api.internal
    - com.acme.api.maintenance
~~~

### Choosing a Package Broad Enough Without Being Too Broad

Consider this source structure:

~~~text
com.acme
├── api
│   ├── publicapi
│   │   ├── order
│   │   └── customer
│   ├── admin
│   └── internal
├── web
└── infrastructure
~~~

If you want to scan both `order` and `customer`, you can pick the parent package `com.acme.api.publicapi`. Selecting `com.acme` is too broad and may pull administrative, internal, or web controllers into the documentation. Pick packages aligned with the API boundary consumers actually need.

`packages-to-exclude` is helpful when a root package has many controllers and only a few branches should not be published. However, a clean package hierarchy is usually easier to maintain than a long exclusion list.

## 4. Restricting Endpoints by Path

`paths-to-match` filters by the URL path declared on request mappings. For example, publishing only API version 1:

~~~yaml
springdoc:
  paths-to-match:
    - /api/v1/**
~~~

You can specify multiple path regions:

~~~yaml
springdoc:
  paths-to-match:
    - /api/v1/orders/**
    - /api/v1/customers/**
  paths-to-exclude:
    - /api/v1/orders/internal/**
    - /api/v1/customers/debug/**
~~~

Patterns like `/api/v1/**` cover endpoints across multiple nested levels; `/api/v1/orders/*` typically matches only a single child path level. When designing patterns, test with a representative path at the deepest level in your application and verify the result in `/v3/api-docs`.

### Combining Package and Path

Package and path answer two different questions:

- Package: which area of the codebase does the controller belong to?
- Path: which URL does the operation expose?

Example:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.api.publicapi
  paths-to-match:
    - /api/v1/**
  paths-to-exclude:
    - /api/v1/internal/**
~~~

A controller inside the scanned package that declares a path outside `/api/v1/**` will not be included in the document. Likewise, a matching path on a controller outside the selected package is also out of scope. This combination is effective for bounding documentation by both codebase structure and URL contract.

## 5. Filtering by Request Media Type: consumes

`consumes` describes the request content type accepted by an endpoint, typically corresponding to the request's `Content-Type`. In Spring MVC/WebFlux, this condition can be declared directly on the mapping:

~~~java
@PostMapping(
    path = "/api/v1/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

If you only want endpoints accepting JSON or multipart in the documentation:

~~~yaml
springdoc:
  consumes-to-match:
    - application/json
    - multipart/form-data
~~~

Upload endpoint example:

~~~java
@PostMapping(
    path = "/api/v1/files",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public FileResponse upload(@RequestPart("file") MultipartFile file) {
    return fileService.upload(file);
}
~~~

When consumers need upload documentation, `multipart/form-data` must remain in the filter. Setting only `application/json` may exclude the upload endpoint based on its consumes condition.

Do not set `consumes-to-match` too narrowly if the system has endpoints accepting XML, form data, binary payloads, or multiple request formats. If there is no need to filter by Content-Type, keep the default to avoid accidentally omitting operations.

## 6. Filtering by Response Media Type: produces

`produces` describes the response content type an endpoint can return, typically tied to content negotiation via the `Accept` header.

Example REST endpoint returning JSON:

~~~java
@GetMapping(
    path = "/api/v1/orders/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public OrderResponse getOrder(@PathVariable UUID id) {
    return orderService.findById(id);
}
~~~

Example endpoint streaming Server-Sent Events:

~~~java
@GetMapping(
    path = "/api/v1/orders/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<OrderEvent> streamEvents() {
    return orderService.streamEvents();
}
~~~

If you only want documentation for JSON responses:

~~~yaml
springdoc:
  produces-to-match:
    - application/json
    - application/problem+json
~~~

To include streaming APIs, add the corresponding media type to the list:

~~~yaml
springdoc:
  produces-to-match:
    - application/json
    - application/problem+json
    - text/event-stream
~~~

`consumes` and `produces` are not interchangeable. An endpoint might accept JSON and return PDF, or accept multipart and return JSON. Choose media types matching actual request and response directions.

## 7. Filtering by Request Mapping Header Conditions

Spring supports header conditions on `@RequestMapping`, `@GetMapping`, `@PostMapping`, and related mapping annotations. Example:

~~~java
@GetMapping(
    path = "/api/v1/legacy/orders",
    headers = "X-API-Version=v1",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public List<OrderResponse> legacyOrders() {
    return orderService.findLegacyOrders();
}
~~~

Here, the `headers` condition requires requests to carry header `X-API-Version` with value `v1`. You can filter for mappings declaring that header condition:

~~~yaml
springdoc:
  headers-to-match:
    - X-API-Version=v1
~~~

`headers-to-match` selects request mappings that declare a header condition. It does not mean springdoc automatically adds a header parameter to every operation, nor does it force every runtime request to include this header.

### Distinguishing Header Conditions from Header Parameters

The following two declarations serve different purposes:

~~~java
// Header is a condition for Spring to select the handler method
@GetMapping(path = "/api/v1/orders", headers = "X-API-Version=v1")
public List<OrderResponse> listV1() {
    return orderService.findAll();
}

// Header is input data for the operation
@GetMapping(path = "/api/v1/orders/search")
public List<OrderResponse> search(
        @RequestHeader("X-Correlation-Id") String correlationId) {
    return orderService.search(correlationId);
}
~~~

To represent an input header in OpenAPI, use `@RequestHeader` or `@Parameter(in = ParameterIn.HEADER)`. To protect endpoints with a Bearer token or API key, model an OpenAPI security scheme instead of treating authentication headers as documentation filters.

For `Accept` and `Content-Type`, prefer `produces` and `consumes` over writing conditions in `headers`, because these two dedicated attributes express content negotiation properly.

## 8. Global Configuration Example in application.yml

The example below produces a document containing only v1 public APIs, excluding internal paths and keeping JSON/multipart formats:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.api.publicapi
  packages-to-exclude:
    - com.acme.api.publicapi.internal
  paths-to-match:
    - /api/v1/**
  paths-to-exclude:
    - /api/v1/internal/**
    - /api/v1/debug/**
  consumes-to-match:
    - application/json
    - multipart/form-data
  produces-to-match:
    - application/json
    - application/problem+json
~~~

Do not add `headers-to-match` to this example because standard public APIs do not necessarily declare header conditions on request mappings. Adding `headers-to-match` when controllers lack matching header conditions can strip expected operations from the document. Configure this filter only when routing genuinely branches on headers.

Dedicated example for header conditions:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.api.versioned
  paths-to-match:
    - /api/**
  headers-to-match:
    - X-API-Version=v2
~~~

Global properties affect the default document. If an application needs documentation for multiple consumers with different scopes, use group-specific filters in the next section.

## 9. Creating Multiple OpenAPI Groups with Dedicated Filters

An application can publish multiple OpenAPI documents. For example:

- `partner-v1`: partner API, containing only version 1 paths.
- `admin`: administrative API, containing only controllers in the admin package.
- `partner-v2`: version 2 API, matching only routes with the corresponding version header.

Each group has a unique name and is accessed by default at `/v3/api-docs/{groupName}`. You can configure them with `GroupedOpenApi` in Java:

~~~java
@Configuration
public class OpenApiGroupsConfig {

    @Bean
    GroupedOpenApi partnerV1Api() {
        return GroupedOpenApi.builder()
            .group("partner-v1")
            .packagesToScan("com.acme.api.partner")
            .pathsToMatch("/api/v1/**")
            .pathsToExclude("/api/v1/internal/**")
            .producesToMatch(
                MediaType.APPLICATION_JSON_VALUE,
                "application/problem+json"
            )
            .consumesToMatch(
                MediaType.APPLICATION_JSON_VALUE,
                MediaType.MULTIPART_FORM_DATA_VALUE
            )
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

    @Bean
    GroupedOpenApi partnerV2Api() {
        return GroupedOpenApi.builder()
            .group("partner-v2")
            .packagesToScan("com.acme.api.versioned")
            .pathsToMatch("/api/**")
            .headersToMatch("X-API-Version=v2")
            .build();
    }
}
~~~

`packagesToScan`, `packagesToExclude`, `pathsToMatch`, `pathsToExclude`, `consumesToMatch`, `producesToMatch`, and `headersToMatch` correspond to the filters described above. Use your project's actual packages/paths and ensure mappings declare header conditions when a group uses `headersToMatch`.

### Configuring Groups via application.yml

If you prefer not to declare a bean per group, you can use `springdoc.group-configs`:

~~~yaml
springdoc:
  group-configs:
    - group: partner-v1
      display-name: Partner API v1
      packages-to-scan:
        - com.acme.api.partner
      paths-to-match:
        - /api/v1/**
      paths-to-exclude:
        - /api/v1/internal/**
      consumes-to-match:
        - application/json
        - multipart/form-data
      produces-to-match:
        - application/json
        - application/problem+json

    - group: admin
      display-name: Admin API
      packages-to-scan:
        - com.acme.api.admin
      paths-to-match:
        - /admin/**

    - group: partner-v2
      display-name: Partner API v2
      packages-to-scan:
        - com.acme.api.versioned
      paths-to-match:
        - /api/**
      headers-to-match:
        - X-API-Version=v2
~~~

Each document can be fetched separately:

| Group | Default URL |
|---|---|
| `partner-v1` | `/v3/api-docs/partner-v1` |
| `admin` | `/v3/api-docs/admin` |
| `partner-v2` | `/v3/api-docs/partner-v2` |

Pick one consistent way to manage groups. Avoid creating the same group name across multiple configuration mechanisms unnecessarily, as mixing `GroupedOpenApi` beans with property-configured groups can make it harder for maintainers to tell where each document comes from.

## 10. Filtering Documentation Is Not Endpoint Protection

This is the most critical operational rule:

- `packages-to-scan`, `paths-to-match`, and other filters determine only which operations appear in OpenAPI.
- They do not remove controllers from the Spring application context.
- They do not prevent users from calling URLs directly.
- They do not grant or revoke access permissions.
- They do not replace Spring Security, API gateway policies, network policies, or service-layer authorization checks.

For instance, if `/admin/users` is excluded from public documentation yet unprotected by Spring Security, users can still call that URL if they know the address and the endpoint allows access.

To protect endpoints, configure authorization separately:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .requestMatchers("/api/v1/**").authenticated()
            .anyRequest().permitAll()
        )
        .build();
}
~~~

This example targets Servlet/Spring MVC applications; WebFlux applications require equivalent reactive security configuration. Security policies must be tested independently from OpenAPI output.

If you only want to hide a controller or operation from documentation, you can use `@Hidden` on the controller/method or `@Operation(hidden = true)` on the operation. This also affects only the OpenAPI description and does not remove the endpoint at runtime.

## 11. Verifying Filtering Results in the OpenAPI Document

After configuring filters, do not rely solely on Swagger UI. Inspect the OpenAPI JSON directly to see which operations were generated.

Fetch the default document:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Fetch a group's document:

~~~bash
curl -s http://localhost:8080/v3/api-docs/partner-v1
~~~

If `jq` is available, list the paths:

~~~bash
curl -s http://localhost:8080/v3/api-docs/partner-v1 | jq -r '.paths | keys[]'
~~~

Expected output for the `partner-v1` group might contain only:

~~~text
/api/v1/orders
/api/v1/orders/{id}
/api/v1/files
~~~

Paths like `/admin/**`, `/api/v1/internal/**`, or `/internal/health` should not appear in the public document if excluded by filters.

### Testing with MockMvc

You can automate contract verification with an integration test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiFilteringTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void partnerDocumentContainsOnlyPartnerPaths() throws Exception {
        mockMvc.perform(get("/v3/api-docs/partner-v1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/v1/orders']").exists())
            .andExpect(jsonPath("$.paths['/admin/users']").doesNotExist())
            .andExpect(jsonPath("$.paths['/api/v1/internal/debug']").doesNotExist());
    }
}
~~~

This is an illustrative example; adapt paths and groups to your actual configuration. For WebFlux applications, use `WebTestClient` to perform the same assertions.

Beyond verifying whether paths exist or not, verify:

1. Does the operation have the right HTTP method?
2. Does `requestBody.content` have the right media types?
3. Does `responses.*.content` have the right media types?
4. Are required header parameters documented?
5. Are `operationId` values unique and following conventions?
6. Are referenced schemas in `components.schemas` still complete?

## 12. Common Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Document has no endpoints | `packages-to-scan` or `paths-to-match` is too narrow; package/path does not match actual controllers | Check declared packages, mapping paths, and temporarily remove filters one by one to isolate |
| Some endpoints disappear after adding media filters | `consumes-to-match` or `produces-to-match` omits the mapping's media type | Add the right media types such as JSON, XML, multipart, or SSE |
| Upload API disappears | Filtered only `application/json` while endpoint consumes `multipart/form-data` | Add multipart to `consumes-to-match` |
| SSE API disappears | `produces-to-match` omits `text/event-stream` | Add the streaming media type if it should be published |
| Header-filtered group is empty | Mapping lacks matching `headers` condition or expression mismatches | Check `@RequestMapping(headers = ...)` and `headers-to-match` |
| Header does not appear as a parameter in Swagger UI | Confused `headers-to-match` with header parameter declaration | Use `@RequestHeader` or `@Parameter(in = HEADER)` to document inputs |
| Endpoint is hidden yet still callable | Filters affect documentation only, not authorization | Protect endpoints with Spring Security or an API gateway |
| Swagger UI shows the wrong group | Wrong document URL or group name used | Check `/v3/api-docs/{group}` and Swagger UI configuration |
| New path does not appear after config change | Confused controller path with context path/proxy prefix or document cache | Check actual mapping path, public URL, and cache state |
| Two methods with same path and HTTP method yield one operation | OpenAPI represents one operation per path + HTTP method pair; overloading by consumes does not create two independent operations | Document media types within one operation or split into distinct groups/URLs |
| Global configuration affects other documents | Filter placed at `springdoc` level instead of inside a group | Move group-specific conditions into `springdoc.group-configs` or `GroupedOpenApi` |

## 13. Maintainable Filter Design Workflow

When scoping OpenAPI for a large project, follow this sequence:

1. List documentation consumers: public clients, partners, admins, internal services, or developer portals.
2. Choose package boundaries reflecting the controller groups to publish.
3. Choose paths by API version or domain; add exclusions for debug/internal paths if needed.
4. Set `consumes-to-match` and `produces-to-match` only when there is a clear requirement to filter by media type.
5. Set `headers-to-match` only when request mappings genuinely branch on headers.
6. Create separate groups if consumers require different endpoint scopes.
7. Inspect OpenAPI JSON directly and write integration tests for included/excluded paths.
8. Test Spring Security separately to ensure internal endpoints cannot be accessed without authorization.
9. Review filter changes as API contract changes, since operations disappearing from the document can affect code generators and consumers.

A good configuration is clear, concise, and mirrors actual API boundaries. Do not add every filter simply because it exists; the more filters you add, the easier it is to drop operations unintentionally when controllers or media types evolve.

## 14. Pre-Release Checklist

- [ ] `packages-to-scan` includes only controller packages belonging to the target documentation.
- [ ] `packages-to-exclude` excludes inappropriate packages where needed.
- [ ] `paths-to-match` covers the intended API versions and domain paths.
- [ ] `paths-to-exclude` excludes internal/debug paths properly.
- [ ] `consumes-to-match` retains all request media types needed by consumers.
- [ ] `produces-to-match` retains all response media types, including streaming if applicable.
- [ ] `headers-to-match` is used only when mappings declare matching header conditions.
- [ ] Input header parameters are documented separately with `@RequestHeader`/`@Parameter`.
- [ ] Group names are unique and document URLs have been verified.
- [ ] OpenAPI JSON is verified automatically, not just visually via Swagger UI.
- [ ] Spring Security/API gateway protects endpoints independently of documentation filters.
- [ ] Consumers or code-generation pipelines have been checked after operations were added or removed.

## 15. Official References

- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html) — list of core properties, defaults, and package/path/media type/header filters.
- [springdoc-openapi Core Properties Reference](https://springdoc.org/core-properties.html) — detailed reference for current configuration properties.
- [springdoc-openapi FAQ](https://springdoc.org/faq.html) — examples for `packagesToScan`, `pathsToMatch`, API groups, and hiding operations.
- [springdoc-openapi v2 Properties](https://springdoc.org/v2/properties.html) — configuration properties for the Spring Boot 3 line.
- [Spring Framework — Mapping Requests (MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html) — path, consumes, produces, and headers conditions on request mappings.
- [Spring Framework — Mapping Requests (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html) — request mapping conditions in the reactive stack.

Restricting packages, paths, media types, and headers produces an OpenAPI document scoped accurately to each consumer. Treat them as documentation contract filters, combine them with groups when multiple API views are needed, and always keep authorization in the runtime security layer rather than relying on whether an endpoint appears in Swagger UI.
