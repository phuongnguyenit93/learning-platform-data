# Marking APIs `deprecated` and Documenting the Replacement Path

When an endpoint, parameter, or field is no longer recommended for use, mark it `deprecated` and provide replacement details clear enough for consumers to migrate. `springdoc-openapi` can emit this status into OpenAPI from Java annotations or Swagger annotations. OpenAPI represents the status via the boolean `deprecated` property; documentation should also include the reason, replacement option, timeline, and migration instructions.

Deprecation is a lifecycle notice for an API. It does not automatically disable the endpoint, alter responses, or delete code. Consumers can still call the old API during the transition period. Retiring or removing an endpoint is a separate change, typically with compatibility impact, that must be governed by versioning policy.

A solid replacement roadmap has four parts: precisely identifying the deprecated element, publishing the replacement API, announcing it in documentation and runtime responses, and monitoring migration progress before ending support.

## 1. How does deprecation differ from hiding or removing an API?

The following states carry different meanings:

| State | Meaning | Existing Consumers |
|---|---|---|
| Active | API is supported and recommended for use | Continue using |
| Deprecated | API still works but should not be used for new integrations; migrate to replacement | Can continue calling during the transition window |
| Hidden from docs | Endpoint is excluded from the OpenAPI document | Runtime may still work; consumers no longer see it in documentation |
| Disabled | Runtime rejects or no longer serves the endpoint | Requests may receive 404, 410, or configured error |
| Removed | Route, parameter, or field has been deleted from contract/runtime | Consumers depending on the removed element may break |

Do not use `@Hidden` or `@Operation(hidden = true)` as a substitute for deprecation. Hidden only controls documentation visibility; it does not inform consumers that the API still exists yet is about to be replaced. Likewise, do not delete an endpoint immediately upon marking it `deprecated`.

Deprecation also does not make a change backward-compatible by itself. If the old API retains its exact behavior and is merely marked `deprecated`, consumers have time to migrate. If you simultaneously change data types, remove fields, or alter response semantics, that remains a contract change requiring separate evaluation.

## 2. The `deprecated` attribute in OpenAPI

OpenAPI provides a boolean `deprecated` property on key objects:

| OpenAPI Object | Marking Scope | Example |
|---|---|---|
| Operation Object | Entire HTTP operation | `GET /api/v1/products` |
| Parameter Object | A path, query, header, or cookie parameter | Query parameter `archived` |
| Header Object | A documented response/request header | Header `X-Legacy-Mode` |
| Schema Object | A model or schema property | Property `legacyCode` |

When `deprecated` is `true`, the document advises consumers to avoid using that element. It is consumer-guidance metadata; it does not by itself convey an end-of-support date or replacement URL.

Abbreviated OpenAPI example:

~~~yaml
paths:
  /api/v1/products:
    get:
      deprecated: true
      summary: List products (deprecated)
      description: Use GET /api/v2/products. The v1 endpoint is scheduled for discontinuation after 2027-12-31.
      parameters:
        - name: archived
          in: query
          deprecated: true
          description: Use the status query parameter in API v2.
          schema:
            type: boolean
      responses:
        '200':
          description: Product list
components:
  schemas:
    Product:
      type: object
      properties:
        legacyCode:
          type: string
          deprecated: true
          description: Use productCode.
        productCode:
          type: string
~~~

The OpenAPI property is just a boolean flag. If details such as the version where deprecation began, sunset date, replacement URL, or migration steps are needed, record them in `description`, `externalDocs`, a clearly defined extension, or HTTP response headers.

## 3. Marking operations with `@Operation(deprecated = true)`

Swagger annotations provide a `deprecated` attribute on `@Operation`. This is the explicit way to flag an HTTP method in documentation:

~~~java
@RestController
@RequestMapping("/api")
class ProductController {

    @Operation(
        operationId = "listProductsV1",
        summary = "List products v1",
        description = """
            Legacy API, not recommended for new integrations.
            Use GET /api/v2/products.
            Migration guide: https://docs.example.com/migrations/products-v1
            """,
        deprecated = true,
        externalDocs = @ExternalDocumentation(
            description = "Guide for migrating from Products API v1 to v2",
            url = "https://docs.example.com/migrations/products-v1"
        )
    )
    @GetMapping("/v1/products")
    List<ProductResponse> listProductsV1() {
        return productService.listV1();
    }
}
~~~

When `springdoc` reads the annotation, the corresponding operation is generated with `deprecated: true`. Swagger UI and OpenAPI readers can then display the operation as deprecated.

Keep `operationId` stable throughout the legacy operation's lifecycle. Do not change `operationId` by locale or modify it just to add the word deprecated; SDK generators may use `operationId` as the method name. Status and migration guidance belong in `deprecated`, `summary`/`description`, and `externalDocs`.

## 4. Using `@Deprecated` in Java

Java has the `@Deprecated` annotation to mark classes, methods, constructors, fields, or API members that are no longer recommended. Since Java 9, the annotation supports two attributes:

- `since`: the version in which deprecation started.
- `forRemoval`: indicates whether the API is scheduled for removal in a future release or merely no longer recommended.

Example:

~~~java
/**
 * Lists products under the API v1 contract.
 *
 * @deprecated Use {@link #listProductsV2(ProductStatus)}.
 *             See the guide at https://docs.example.com/migrations/products-v1.
 */
@Deprecated(since = "2.4", forRemoval = true)
@GetMapping("/api/v1/products")
List<ProductResponse> listProductsV1() {
    return productService.listV1();
}
~~~

`springdoc` can recognize `@Deprecated` on models and operations to mark the corresponding OpenAPI elements. Use `@Operation(deprecated = true)` when declaring the status directly in Swagger annotations; use `@Deprecated` to synchronize status across source code, compiler warnings, and Javadoc.

Example declaring both:

~~~java
@Deprecated(since = "2.4", forRemoval = true)
@Operation(
    operationId = "listProductsV1",
    summary = "List products v1",
    deprecated = true,
    description = "Use GET /api/v2/products. See the migration guide at https://docs.example.com/migrations/products-v1."
)
@GetMapping("/api/v1/products")
List<ProductResponse> listProductsV1() {
    return productService.listV1();
}
~~~

Do not treat `since` and `forRemoval` as sunset dates. `since` is a code version label; `forRemoval` only expresses intent to remove in the future. OpenAPI `deprecated` remains a boolean and does not automatically turn those two values into a retirement schedule.

### Writing Javadoc for deprecated APIs

Javadoc should explain why the legacy API is no longer recommended, what replaces it, and link to the migration guide:

~~~java
/**
 * Finds a product by legacy code.
 *
 * @deprecated Since version 2.4, use {@link #findByProductCode(String)}.
 *             The legacyCode parameter is no longer supported in the new API.
 *             See https://docs.example.com/migrations/product-lookup.
 */
@Deprecated(since = "2.4", forRemoval = true)
public ProductResponse findByLegacyCode(String legacyCode) {
    return repository.findByLegacyCode(legacyCode);
}
~~~

The replacement notice must point to an API that actually exists. Before publishing documentation, verify that the replacement method or endpoint is implemented and documented in OpenAPI.

## 5. Configuring `springdoc` to automatically detect `@Deprecated`

`springdoc` includes a deprecating model converter to mark corresponding schemas when Java models contain `@Deprecated`. In the current configuration, this converter is enabled by default:

~~~yaml
springdoc:
  model-converters:
    deprecating-converter:
      enabled: true
~~~

When you need to disable automatic marking from Java `@Deprecated`, the property is:

~~~yaml
springdoc:
  model-converters:
    deprecating-converter:
      enabled: false
~~~

Normally, keep the converter enabled so code and documentation do not drift apart. Disable it only with a clear reason and when replaced by tested alternative metadata. This property controls the deprecating model converter; it is not a global switch to strip every `deprecated` flag explicitly declared by `@Operation` or `@Schema`.

After changing configuration, inspect `/v3/api-docs` to confirm operations and schemas carry the expected `deprecated` flag. Do not rely solely on Swagger UI changing colors or striking through an operation.

## 6. Marking a parameter `deprecated`

An endpoint may remain active while one query parameter or header has a replacement. Use `@Parameter(deprecated = true)` to mark an individual parameter:

~~~java
@GetMapping("/api/v2/products")
@Operation(summary = "Search products")
List<ProductResponse> searchProducts(
    @Parameter(
        name = "archived",
        description = "Deprecated. Use status=ARCHIVED or status=ACTIVE.",
        deprecated = true
    )
    @RequestParam(required = false) Boolean archived,

    @Parameter(
        name = "status",
        description = "Product status to filter by."
    )
    @RequestParam(required = false) ProductStatus status
) {
    ProductStatus effectiveStatus = status;
    if (effectiveStatus == null && archived != null) {
        effectiveStatus = archived ? ProductStatus.ARCHIVED : ProductStatus.ACTIVE;
    }
    return productService.search(effectiveStatus);
}
~~~

During the transition period, the server can keep accepting `archived` and map it to `status`. If both parameters appear together, define a precedence rule or return 400 to avoid ambiguous requests. That rule must be documented in the operation description and tested.

Do not rename the parameter at runtime while only renaming it in OpenAPI. For instance, if the server still accepts `archived`, documentation must reflect `archived` as deprecated and `status` as the new parameter. Removing `archived` is a contract change and requires scheduled notice.

## 7. Marking a field or schema `deprecated`

A JSON property can be retained for compatibility while discouraged for new clients. Use `@Schema(deprecated = true)` on fields or record components:

~~~java
@Schema(description = "Product information in the catalog")
public record ProductResponse(
    UUID id,

    @Schema(
        deprecated = true,
        description = "Legacy code. Use productCode; this field will be removed in the next major API version."
    )
    String legacyCode,

    @Schema(
        description = "Official product code."
    )
    String productCode,

    String name
) {}
~~~

The OpenAPI schema for `legacyCode` will contain `deprecated: true`. Consumers can keep reading this field during the transition period; the server must continue supplying a value while the current contract still commits to it.

If an entire model is deprecated, you can place `@Schema(deprecated = true)` at the class level. If only one field is obsolete, mark only that field so consumers do not mistakenly think the entire model is about to be removed.

Do not drop the field from JSON responses right when adding `deprecated: true`. Code generators and SDKs may display warnings to developers, yet the runtime contract must keep the field throughout the support window.

## 8. Describing replacements via `description` and `externalDocs`

OpenAPI has no built-in standard property named `replacementOperationId` or `sunsetDate`. Therefore, describe the replacement path using text fields and links:

~~~java
@Operation(
    operationId = "getProductV1",
    summary = "Get product (deprecated)",
    deprecated = true,
    description = """
        This API is kept for compatibility with existing consumers.

        Replaced by GET /api/v2/products/{productCode}.
        Path parameter id is replaced by productCode.
        Response field legacyCode is replaced by productCode.

        Deprecation start date: 2027-01-01.
        Scheduled sunset date: 2027-12-31.
        """,
    externalDocs = @ExternalDocumentation(
        description = "Migration guide and v1-to-v2 mapping table",
        url = "https://docs.example.com/migrations/products-v1"
    )
)
@GetMapping("/api/v1/products/{id}")
ProductResponse getProductV1(@PathVariable UUID id) {
    return productService.getV1(id);
}
~~~

The `description` should answer practical questions:

- Why is the legacy operation or field deprecated?
- Which endpoint, parameter, or schema replaces it?
- How is an old request translated into a new request?
- Which fields or semantics differ in the new response?
- Until what milestone will the old API remain operational?
- By when must consumers complete migration?

Avoid vague notes like "Use v2 instead". Consumers need to know the path, method, parameters, schemas, and how differences are handled.

## 9. Publishing response headers for deprecated endpoints

OpenAPI describes the contract, while HTTP response headers can announce deprecation status at the moment consumers actually call the endpoint. RFC 9745 defines the `Deprecation` header; RFC 8594 defines the `Sunset` header.

Example response from a legacy endpoint:

~~~http
HTTP/1.1 200 OK
Deprecation: @1798761600
Sunset: Fri, 31 Dec 2027 23:59:59 GMT
Link: <https://docs.example.com/migrations/products-v1>; rel="deprecation"
Link: </api/v2/products>; rel="successor-version"
Content-Type: application/json
~~~

Meaning:

- `Deprecation` is an RFC 9651 Structured Field Date formatted as `@` plus a Unix timestamp in seconds. For example, `@1798761600` corresponds to `2027-01-01T00:00:00Z`.
- `Sunset` uses an HTTP-date per RFC 8594. The `Sunset` timestamp must not be earlier than the `Deprecation` timestamp.
- `Link` with `rel=deprecation` points to documentation explaining the deprecation and migration instructions.
- `Link` with `rel=successor-version` can point to the successor-version resource in a versioned-resource system.

`Deprecation` and `Sunset` do not alter the semantics of the current response. `Deprecation` notifies that the resource is or will be deprecated; `Sunset` communicates when the resource is expected to become unresponsive. If you only want to announce deprecation without a finalized retirement date, do not invent a fake `Sunset` date.

### Declaring response headers in OpenAPI

You can document these headers using `@ApiResponse`:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Legacy endpoint response; see migration guide.",
    headers = {
        @Header(
            name = "Deprecation",
            description = "Structured Field Date indicating the deprecation timestamp.",
            schema = @Schema(type = "string", example = "@1798761600")
        ),
        @Header(
            name = "Sunset",
            description = "HTTP-date when the endpoint is scheduled to stop serving.",
            schema = @Schema(type = "string", example = "Fri, 31 Dec 2027 23:59:59 GMT")
        ),
        @Header(
            name = "Link",
            description = "Links to the migration guide and successor resource.",
            schema = @Schema(type = "string")
        )
    }
)
~~~

If the actual response does not emit a header, do not declare it as always present. OpenAPI must describe runtime behavior, including cases where headers only appear on deprecated endpoints or versions.

## 10. Adding deprecation headers in Spring Boot

With Spring MVC, you can use a `HandlerInterceptor` or `OncePerRequestFilter` to add headers to legacy routes. Example filter scoped only to the `/api/v1` prefix:

~~~java
@Component
class DeprecatedApiHeadersFilter extends OncePerRequestFilter {

    private static final String DEPRECATION_DATE = "@1798761600";
    private static final String SUNSET_DATE = "Fri, 31 Dec 2027 23:59:59 GMT";

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith(
            request.getContextPath() + "/api/v1/"
        );
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        response.setHeader("Deprecation", DEPRECATION_DATE);
        response.setHeader("Sunset", SUNSET_DATE);
        response.addHeader(
            "Link",
            "<https://docs.example.com/migrations/products-v1>; rel=\"deprecation\""
        );
        response.addHeader(
            "Link",
            "</api/v2/products>; rel=\"successor-version\""
        );
        filterChain.doFilter(request, response);
    }
}
~~~

The filter must be scoped to the exact paths and timeframe. If only a few operations in `/api/v1` are deprecated, use an explicit route list or dedicated metadata rather than attaching headers to the whole prefix.

With Spring WebFlux, use a `WebFilter` or corresponding filter function; do not use `OncePerRequestFilter` because it is a Servlet API. With a gateway, headers can be injected at the gateway if the gateway knows exact routes and lifecycle policies.

If the API is called from a cross-origin browser, check CORS exposed headers. Browser JavaScript cannot read custom response headers unless `Access-Control-Expose-Headers` exposes them.

## 11. Linking to the migration guide and replacement API

A migration guide should be a stable document with a public, versioned URL. It can be linked from:

- The OpenAPI Operation via `externalDocs`.
- The `Deprecation` response header via `Link` `rel=deprecation`.
- The successor resource via `Link` `rel=successor-version` when fitting a version-history model.
- The API portal or changelog page.

Example `Link` headers:

~~~http
Link: <https://docs.example.com/migrations/products-v1>; rel="deprecation"
Link: </api/v2/products>; rel="successor-version"
Link: </api/version-history/products>; rel="version-history"
~~~

The `deprecation` link relation is registered by RFC 9745 to point to human-readable documentation about the deprecation. The `successor-version` and `version-history` relations are defined in RFC 5829 for navigating versioned resources. If the replacement path is not a versioned resource in that sense, record the replacement URL in the migration guide or an organization-defined extension instead of misapplying link relation semantics.

Do not point replacement links to an unreleased endpoint, one requiring different permissions consumers cannot obtain, or a document only reachable in an internal environment.

## 12. Building a phased replacement roadmap

Do not mark an endpoint `deprecated` and remove it in the same release if consumers need time to adapt. A roadmap can be split into phases:

| Phase | Provider Actions | Consumer Expectations |
|---|---|---|
| 1. Prepare replacement | Build new API, new schemas, migration guide, and contract tests | No immediate changes required |
| 2. Publish new API | Release new endpoint and OpenAPI docs | New integrations can adopt the new API |
| 3. Mark old API deprecated | Update OpenAPI, Java annotations, response headers, and changelog | Plan migration |
| 4. Transition | Maintain old API, monitor usage, support consumers | Gradually migrate to new API |
| 5. Sunset | Send final notice, publish cutoff date, resolve remaining support | Complete migration |
| 6. Retire | Return agreed status, e.g. 410 Gone, or remove route per policy | Stop calling old API |

The duration of each phase depends on consumer count, change magnitude, and support agreements. No single wait time fits every API. Public APIs with external partners require longer windows than an internal API controlled by one team.

### Phase 1: prepare the replacement

Before announcing deprecation, a working replacement API must exist in a testable environment. Verify that the replacement:

- Covers the primary use cases of the old API.
- Has clear schemas, security schemes, scopes, and error responses.
- Has request/response documentation and examples.
- Can run in parallel with the old API during the transition period.
- Has a migration guide explaining equivalents and differences.

Do not announce a sunset date before the replacement is ready or before consumers have a feasible path to migrate.

### Phase 2: release the replacement first

Let consumers try the new API before marking the old API `deprecated`. This helps surface contract differences, permission errors, rate limits, or missing features while adjustments are still easy.

### Phase 3: mark and announce

In the same release, synchronize:

- OpenAPI document: `deprecated: true` and replacement description.
- Java source: `@Deprecated(since = ..., forRemoval = ...)`.
- Runtime: `Deprecation` and `Link` headers; add `Sunset` once a cutoff date is announced.
- Release notes/changelog: list affected endpoints and consumers.
- Migration guide: old and new request examples.

### Phase 4: monitor usage

Track request volume to the old endpoint by controlled client/application identifier. Use aggregate metrics to identify which consumers still depend on it, without logging tokens, sensitive request bodies, or unnecessary personal data just for deprecation tracking.

Directly notify registered consumer owners if integration policy permits. Documentation and headers signal clients; they do not replace direct coordination with partners bound by SLAs.

### Phases 5 and 6: sunset then retire

Before the sunset date, send a final notice and verify critical consumers have migrated. When the cutoff arrives:

- Follow the published policy accurately.
- If keeping a tombstone endpoint to respond explicitly, you can return `410 Gone` with a link to the migration guide.
- Do not serve old business data with altered semantics without notice.
- Clean up deprecated code, tests, routes, and metadata once removal is complete.

`410 Gone` is an option when the resource has been permanently removed. If the endpoint redirects to a new API, evaluate HTTP method, body, authentication, and semantics before using `301`/`308`; redirects are not always safe or equivalent across all HTTP methods.

## 13. Migration guides need concrete mapping tables

A replacement guide should enable consumers to migrate requests and responses without guesswork. For example, API v1 uses a boolean `archived` flag, whereas API v2 uses a `status` enum:

| Element | API v1 (deprecated) | API v2 (replacement) |
|---|---|---|
| Endpoint | `GET /api/v1/products` | `GET /api/v2/products` |
| Filter archived products | `archived=true` | `status=ARCHIVED` |
| Filter active products | `archived=false` | `status=ACTIVE` |
| No status filter | Omit `archived` | Omit `status` or `status=ALL` per contract |
| Product code in response | `legacyCode` | `productCode` |
| Pagination | `page`, `size` | `page`, `size` |
| Authentication | Bearer token | Same scheme if policy unchanged |

Old request example:

~~~http
GET /api/v1/products?archived=true&page=0&size=20
Accept: application/json
~~~

New request:

~~~http
GET /api/v2/products?status=ARCHIVED&page=0&size=20
Accept: application/json
~~~

Old response example:

~~~json
{
  "items": [
    {
      "id": "p-101",
      "legacyCode": "OLD-101",
      "name": "Ballpoint pen"
    }
  ]
}
~~~

New response:

~~~json
{
  "items": [
    {
      "id": "p-101",
      "productCode": "OLD-101",
      "name": "Ballpoint pen"
    }
  ]
}
~~~

The migration guide should further clarify:

- Have sort order, pagination, or default filters changed?
- Have nullability, date/time formats, or enum values changed?
- Does the new API require different OAuth scopes or roles?
- Which error codes changed?
- Are rate limits, timeouts, or payload limits different?
- Must consumers update generated SDKs or retry configurations?

Do not merely swap URLs in the guide. A new endpoint may have different semantics even if the schema looks similar; document every difference affecting client logic.

## 14. Documenting both the old and replacement operations in OpenAPI

During the transition window, the OpenAPI document can contain both the old and new operations. The old operation has `deprecated: true` with a description pointing to the replacement; the new operation has official documentation without the `deprecated` flag.

Example:

~~~java
@RestController
class ProductApiController {

    @Deprecated(since = "2.4", forRemoval = true)
    @Operation(
        operationId = "searchProductsV1",
        summary = "Search products using API v1",
        description = "Deprecated since version 2.4. Use GET /api/v2/products with query parameter status. Migration guide: https://docs.example.com/migrations/products-v1.",
        deprecated = true,
        externalDocs = @ExternalDocumentation(
            description = "Products API v1 migration guide",
            url = "https://docs.example.com/migrations/products-v1"
        )
    )
    @GetMapping("/api/v1/products")
    ProductPage searchV1(
        @RequestParam(required = false) Boolean archived
    ) {
        return productService.searchV1(archived);
    }

    @Operation(
        operationId = "searchProductsV2",
        summary = "Search products using API v2",
        description = "Filter products by status: ACTIVE, ARCHIVED, or ALL."
    )
    @GetMapping("/api/v2/products")
    ProductPage searchV2(
        @RequestParam(required = false) ProductStatus status
    ) {
        return productService.searchV2(status);
    }
}
~~~

In OpenAPI, consumers can see both operations side by side and choose the new one. Do not hide the old operation while it is still supported; hiding it removes the signal that the endpoint remains active yet in transition.

If API v1 and v2 are split into two separate OpenAPI groups, ensure the v1 group still publishes the `deprecated` flag and the v2 group contains the replacement operation. You can attach `externalDocs` at the operation or tag level pointing to the shared guide.

## 15. Testing compatibility behavior during the transition window

While the legacy endpoint remains supported, verify that it continues fulfilling its published contract:

- Path, method, and authentication still work.
- Legacy requests still parse under the legacy schema.
- Legacy responses still contain committed fields.
- Deprecated parameters still work if policy states they remain supported.
- Deprecation headers are emitted accurately.
- The new API works independently with the new schema.
- Mapping legacy requests to new business logic does not alter semantics beyond announced differences.

If both endpoints share a service, test both adapters so modifying v2 logic does not inadvertently alter v1. Contract tests should retain representative request/response examples for real consumers.

## 16. Testing the `deprecated` flag in the OpenAPI document

Do not only test that the endpoint returns the right response. Verify that OpenAPI JSON includes the `deprecated` flag and replacement details:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductOpenApiDeprecationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void marksLegacyOperationAsDeprecated() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/v1/products'].get.deprecated"
            ).value(true))
            .andExpect(jsonPath(
                "$.paths['/api/v1/products'].get.externalDocs.url"
            ).value("https://docs.example.com/migrations/products-v1"))
            .andExpect(jsonPath(
                "$.paths['/api/v2/products'].get.deprecated"
            ).doesNotExist());
    }
}
~~~

Checking a parameter:

~~~java
@Test
void marksLegacyParameterAsDeprecated() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.paths['/api/v2/products'].get.parameters[?(@.name=='archived')].deprecated[0]"
        ).value(true));
}
~~~

Checking a schema property:

~~~java
@Test
void marksLegacySchemaPropertyAsDeprecated() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.components.schemas.ProductResponse.properties.legacyCode.deprecated"
        ).value(true));
}
~~~

Whether JSONPath expressions support filter predicates depends on the implementation in use. If the matcher does not support filter syntax, parse the JSON document into an object and locate the parameter by `name`. The goal is verifying the `deprecated` flag is in the right place without depending on parameter ordering.

## 17. Testing deprecation headers at runtime

When legacy APIs send `Deprecation`, `Sunset`, and `Link` headers, write tests ensuring headers are actually emitted on responses. `MockMvc` example:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class DeprecatedProductApiTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void legacyEndpointPublishesDeprecationInformation() throws Exception {
        mockMvc.perform(get("/api/v1/products")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(header().string("Deprecation", "@1798761600"))
            .andExpect(header().string(
                "Sunset",
                "Fri, 31 Dec 2027 23:59:59 GMT"
            ))
            .andExpect(header().string(
                "Link",
                org.hamcrest.Matchers.containsString("rel=\"deprecation\"")
            ));
    }
}
~~~

If the response emits multiple `Link` headers, frameworks or test matchers may merge or return multiple values. In that case, read the header value list and assert each relation instead of comparing a full string in a fixed order.

This test checks concrete example dates. In real applications, place deprecation and sunset dates in centralized configuration or a policy object so the filter, OpenAPI descriptions, and release notes never drift onto different dates. Do not read the current time on each request to produce shifting header values.

If the API is called from a cross-origin browser, check CORS exposed headers. Browser JavaScript cannot read custom response headers unless `Access-Control-Expose-Headers` exposes them.

## 18. Versioning rules and removal timing

A deprecation policy should clearly state:

1. How API versions are identified: path, media type, header, or schema version.
2. How deprecation is announced: OpenAPI, HTTP headers, release notes, and support channels.
3. Minimum support windows by API category.
4. How changes to sunset dates are communicated.
5. HTTP status returned after an endpoint stops serving.
6. How consumers with SLAs or custom support contracts are handled.

Core principles:

- Adding `deprecated: true` generally does not alter the wire contract, yet serves as a lifecycle signal consumers and tools can act on.
- Removing an operation, required parameter, or response field that consumers depend on can be a breaking change.
- Changing field semantics without changing the schema can also be a breaking change.
- Adding a replacement endpoint does not automatically make the old API backward-compatible with the new API.
- Removing the old API must follow the versioning policy and published milestones.

If using semantic versioning for API contracts, removing a published operation typically requires a major version or a new API version per policy. With path versioning, you can keep `/api/v1` during the transition period and publish `/api/v2`. Do not assume every organization must use the same versioning scheme; what matters is that consumers know which contract is supported and until when.

## 19. Using HTTP `410 Gone` after retirement

Once an endpoint is permanently retired, you can return `410 Gone` to state explicitly that the resource has been removed. Example:

~~~java
@RestControllerAdvice
class RemovedApiExceptionHandler {

    @ExceptionHandler(RemovedApiException.class)
    ResponseEntity<ProblemDetail> handleRemovedApi(RemovedApiException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.GONE);
        problem.setTitle("API discontinued");
        problem.setDetail(
            "Use GET /api/v2/products. Guide: https://docs.example.com/migrations/products-v1"
        );
        problem.setType(URI.create(
            "https://docs.example.com/problems/deprecated-api-removed"
        ));

        return ResponseEntity.status(HttpStatus.GONE)
            .header(
                HttpHeaders.LINK,
                "<https://docs.example.com/migrations/products-v1>; rel=\"deprecation\""
            )
            .body(problem);
    }
}
~~~

This is an example response after the old route has been switched to a tombstone mechanism or exception handler. It does not by itself replace removing old mappings and must be integrated with actual application routing.

`410 Gone` fits when the provider knows the resource was removed with no intent to restore it. If the endpoint is only temporarily unavailable, use an appropriate status per semantics instead of `410`. If the route simply disappears and the server returns `404`, consumers struggle to distinguish a resource that never existed from one that was retired.

## 20. Common mistakes when marking elements `deprecated`

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Swagger UI does not show operation as deprecated | Annotation not scanned by `springdoc` or flag not set | Use `@Operation(deprecated = true)`, check `/v3/api-docs` |
| Java method is `@Deprecated` yet schema unchanged | Model converter disabled or annotation on wrong member | Check `@Deprecated` and `springdoc.model-converters.deprecating-converter.enabled` |
| Only description mentions deprecated without OpenAPI flag | Forgot `deprecated = true` | Set explicit flag on Operation, Parameter, or Schema |
| Old API vanishes immediately after marking | Used `@Hidden` or deleted route simultaneously | Keep endpoint operational during transition window |
| Consumers do not know which endpoint to use | Description merely says "use v2" | State path, method, parameters, schema, and migration guide |
| Replacement does not work yet | Announced deprecation before releasing new API | Prepare and test replacement first |
| `Deprecation` header has wrong format | Used HTTP-date for `Deprecation` | Use Structured Field Date `@UnixTimestamp` per RFC 9745 |
| `Sunset` earlier than `Deprecation` | Inconsistent timeline configuration | Ensure `Sunset` is not earlier than the `Deprecation` date |
| Response emits header yet OpenAPI omits it | Missing `@ApiResponse(headers = ...)` | Add header metadata and test the document |
| Swagger UI shows replacement yet runtime returns 404 | OpenAPI annotation mismatched actual route | Test HTTP mappings and documentation together |
| Removing old field breaks SDK consumers | No transition window or breaking-change review | Keep old field, add new field, monitor usage before removal |
| Browser cannot read `Deprecation` header | CORS does not expose response headers | Add `Deprecation`, `Sunset`, and `Link` to `Access-Control-Expose-Headers` |
| Replacement link points to wrong environment | Hard-coded internal host or staging URL | Use environment-appropriate public URLs and verify before release |

## 21. Pre-deprecation checklist

Before merging changes, confirm:

1. The replacement API already exists and has been tested.
2. The reason for deprecation is clearly explained.
3. The exact operation, parameter, or schema within scope is marked `deprecated`.
4. `operationId`, paths, and JSON property names remain stable during the transition window.
5. Descriptions clearly state the replacement path, method, and parameters.
6. External documentation or the migration guide is accessible.
7. Deprecation and sunset dates align with policy.
8. Runtime response headers follow RFC formatting.
9. The OpenAPI document has `deprecated: true` at the right operation/parameter/schema.
10. The old API continues functioning throughout the announced support period.
11. Contract tests cover both the old API and the new API.
12. Consumer owners are notified via agreed channels.
13. Usage telemetry is sufficient to track migration progress.
14. CI checks contract changes and blocks removing old APIs before the allowed milestone.

## 22. Implementation workflow in a Spring Boot project

1. Inventory endpoints, parameters, schema properties, and consumers using the element slated for replacement.
2. Design the new endpoint or field; check schemas, security, error responses, and semantics.
3. Write a migration guide with mapping tables and before/after request/response examples.
4. Release the replacement and verify with integration/contract tests.
5. Annotate Java members with `@Deprecated(since, forRemoval)` where appropriate.
6. Annotate OpenAPI with `@Operation(deprecated = true)`, `@Parameter(deprecated = true)`, or `@Schema(deprecated = true)`.
7. Add descriptions, `externalDocs`, and response headers per policy.
8. Emit `Deprecation` and `Link` headers; emit `Sunset` only once a retirement date is published.
9. Monitor usage and assist consumers in migrating.
10. Verify the sunset milestone and send final notices.
11. Retire the route or field per versioning policy; consider `410 Gone` for removed resources.
12. Clean up deprecated metadata once the old API is truly removed and update historical docs.

Marking elements `deprecated` helps providers and consumers recognize when a component is approaching end of life. The highest value comes from actionable replacement information: the new endpoint, data mapping, timeline, documentation, and runtime signals. When these stay synchronized across Java, OpenAPI, HTTP responses, and CI, consumers can migrate predictably and providers reduce risk when retiring legacy APIs.

## 23. References

- [Springdoc OpenAPI FAQ](https://springdoc.org/faq.html): how `springdoc` handles `@Deprecated` and configures the deprecating model converter.
- [Springdoc OpenAPI Core Properties](https://springdoc.org/core-properties.html): `springdoc.model-converters.deprecating-converter.enabled`.
- [Swagger Core – Operation annotation](https://docs.swagger.io/swagger-core/v2.2.34/apidocs/io/swagger/v3/oas/annotations/Operation.html): the `deprecated` attribute of `@Operation`.
- [Swagger Core – Schema annotation](https://github.com/swagger-api/swagger-core/blob/master/modules/swagger-annotations/src/main/java/io/swagger/v3/oas/annotations/media/Schema.java): schema metadata, including `deprecated` status.
- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object): the `deprecated` property on operations.
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object): the `deprecated` property on parameters.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): the `deprecated` keyword in schemas.
- [Oracle Java – How to Deprecate APIs](https://docs.oracle.com/en/java/javase/21/core/how-deprecate-apis.html): `@Deprecated`, `since`, `forRemoval`, and Javadoc `@deprecated`.
- [RFC 9745 – The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745.html): the `Deprecation` header and `deprecation` Link relation.
- [RFC 8594 – The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594.html): announcing when a resource is expected to become unresponsive.
- [RFC 5829 – Link Relation Types for Version Navigation](https://www.rfc-editor.org/rfc/rfc5829.html): `successor-version` and `version-history`.
- [IANA Link Relation Types](https://www.iana.org/assignments/link-relations): official registry of Link relations.
