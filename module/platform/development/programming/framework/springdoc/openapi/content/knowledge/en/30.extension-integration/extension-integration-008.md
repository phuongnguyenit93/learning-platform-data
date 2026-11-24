# Endpoint Scope Permitted for Exposure to Tool Callers

A tool caller can be an agent, workflow engine, API client, or integration system that reads OpenAPI to discover operations and decide which ones it can invoke. When publishing documentation for these systems, endpoint scope must be tightly bounded. A document containing every controller can accidentally expose admin APIs, internal endpoints, or high-impact actions in the tool catalog available to clients.

With springdoc-openapi, the right approach is to create a dedicated group for tool callers, include only approved operations, and accurately describe authentication and the impact of each operation. The OpenAPI document defines the capabilities a client can discover; Spring Security, gateways, and the endpoints themselves decide whether a caller is actually permitted to execute an action.

## 1. Define the Exposure Scope Before Creating a Group

Start with a list of operations permitted for exposure. An operation is identified by an HTTP method and path pair, such as `GET /api/tools/products` or `POST /api/tools/orders`. Do not just list controllers or packages, because a single controller may hold both read and state-changing operations.

Example scope for a tool client managing catalog lookups and order creation:

| Operation | Expose? | Reason |
| --- | --- | --- |
| `GET /api/tools/products` | Yes | Catalog lookup; does not mutate data. |
| `POST /api/tools/orders` | Conditional | Creates an order; has business impact and requires a dedicated write scope. |
| `DELETE /api/admin/orders/{id}` | No | Administrative action; can destroy data. |
| `GET /actuator/env` | No | Operational endpoint that can expose sensitive configuration. |
| `POST /api/internal/reindex` | No | Internal task with broad system impact. |
| `GET /api/debug/**` | No | Diagnostic endpoints not intended for external clients. |

By default, prefer read operations with a clearly bounded data scope. Include write operations in the group only when there is a business need along with proper authentication, authorization, input limits, auditing, and retry handling. Avoid placing bulk deletes, command execution, arbitrary file access, or user-supplied URL fetching into a shared tool group.

This list constitutes the API's exposure policy. It should be reviewed with business owners and operations teams before adding entries to a registry or handing it to tool callers.

## 2. Create a Separate Group Using GroupedOpenApi

Do not reuse the default document containing all endpoints as a tool catalog. Create a separate group, such as `tool-caller-v1`:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ToolCallerAllowlistOpenApiConfiguration {

    @Bean
    GroupedOpenApi toolCallerApi() {
        return GroupedOpenApi.builder()
            .group("tool-caller-v1")
            .packagesToScan("com.example.api.tools")
            .pathsToMatch("/api/tools/**")
            .pathsToExclude(
                "/api/tools/admin/**",
                "/api/tools/internal/**"
            )
            .build();
    }
}
~~~

In the example, controllers live in a package dedicated to tool endpoints; the path filter limits published URLs; and exclude filters remove admin and internal branches. These filters combine to narrow the scope. If a valid controller sits outside the scanned package, its operations will not appear even if the path matches.

With the default base path, the document is accessible at:

- JSON: `/v3/api-docs/tool-caller-v1`
- YAML: `/v3/api-docs/tool-caller-v1.yaml`

The group ID is the document's public identifier. Keep it stable within a contract version and introduce a new group ID when releasing an incompatible contract, such as `tool-caller-v2`.

## 3. Use an Exact Allowlist by Path and HTTP Method

`packagesToScan`, `pathsToMatch`, and `pathsToExclude` are helpful filters, but a broad prefix like `/api/tools/**` can automatically pick up new operations added later. For a tightly scoped tool group, maintain an allowlist covering both method and path.

Example using an `OpenApiCustomizer` attached to the group to drop operations outside the allowlist:

This example is an alternative or extension to the group configuration in the previous section. If combining both, register only one bean for the `tool-caller-v1` group and merge filters into the same builder; do not declare two `GroupedOpenApi` beans with the same group ID.

~~~java
import io.swagger.v3.oas.models.PathItem;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Map;
import java.util.Set;

@Configuration
class ToolCallerOpenApiConfiguration {

    private static final Map<String, Set<PathItem.HttpMethod>> ALLOWED = Map.of(
        "/api/tools/products", Set.of(PathItem.HttpMethod.GET),
        "/api/tools/orders", Set.of(PathItem.HttpMethod.POST)
    );

    @Bean
    GroupedOpenApi toolCallerApi() {
        OpenApiCustomizer allowOnlyApprovedOperations = openApi -> {
            if (openApi.getPaths() == null) {
                return;
            }

            openApi.getPaths().entrySet().removeIf(entry -> {
                Set<PathItem.HttpMethod> allowedMethods = ALLOWED.get(entry.getKey());
                if (allowedMethods == null) {
                    return true;
                }

                PathItem pathItem = entry.getValue();
                for (PathItem.HttpMethod method : PathItem.HttpMethod.values()) {
                    if (allowedMethods.contains(method)) {
                        continue;
                    }
                    removeOperation(pathItem, method);
                }
                return pathItem.readOperations().isEmpty();
            });
        };

        return GroupedOpenApi.builder()
            .group("tool-caller-v1")
            .pathsToMatch("/api/tools/**")
            .addOpenApiCustomizer(allowOnlyApprovedOperations)
            .build();
    }

    private static void removeOperation(
        PathItem pathItem,
        PathItem.HttpMethod method
    ) {
        switch (method) {
            case GET -> pathItem.setGet(null);
            case PUT -> pathItem.setPut(null);
            case POST -> pathItem.setPost(null);
            case DELETE -> pathItem.setDelete(null);
            case OPTIONS -> pathItem.setOptions(null);
            case HEAD -> pathItem.setHead(null);
            case PATCH -> pathItem.setPatch(null);
            case TRACE -> pathItem.setTrace(null);
        }
    }
}
~~~

The allowlist above keeps only `GET /api/tools/products` and `POST /api/tools/orders`. If `DELETE` is later added to `/api/tools/orders`, the customizer still removes that operation. When upgrading Swagger Core, check the `PathItem.HttpMethod` enum and setters of the version in use to make sure the customizer still covers all supported HTTP methods.

This is a filter at the document-generation layer. It does not remove mappings from Spring MVC and does not prevent direct requests to the endpoint. Runtime policies must still be configured separately.

## 4. Distinguishing @Hidden from Per-Group Filtering

You can use `@Hidden` to exclude a controller or operation from documentation:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AdminOrderController {

    @Hidden
    @DeleteMapping("/api/admin/orders/{id}")
    void deleteOrder(@PathVariable String id) {
        // Handle administrative action.
    }
}
~~~

`@Hidden` is appropriate when an operation should not appear in any OpenAPI document. If an endpoint must appear in internal documentation yet stay absent from the tool-caller group, do not apply `@Hidden` globally. Use group-specific filters such as `pathsToExclude` or `OpenApiCustomizer`.

Hiding an operation from OpenAPI only changes the generated document. The mapping still exists and can still be called if a request gets past runtime security layers. Never use `@Hidden` as an authorization mechanism.

## 5. Expose Only Operations with Clear Semantics

`operationId` is often used by client generators or integration layers to create stable function names. Choose unique, concise, action-descriptive `operationId` values:

The snippet below focuses on operation metadata; parameters and implementation are abbreviated.

~~~java
@GetMapping("/api/tools/products")
@Operation(
    operationId = "searchProducts",
    summary = "Search products",
    description = "Look up products currently permitted for sale. This operation only reads catalog data."
)
ProductSearchResponse searchProducts(...) {
    // ...
}
~~~

Avoid generic names like `getData`, `process`, or `execute`. Do not rename `operationId` arbitrarily after clients have bound tools to that name. If incompatible behavior or schema changes are needed, treat it as a breaking contract change and release a new version accordingly.

The description should answer:

- What does the operation do and which resource type does it apply to?
- Does it change state or create data?
- Can it be retried safely?
- Which parameters are required and what length/size limits apply?
- Is the response paginated or capped in result count?
- Which business errors can occur?

Avoid vague descriptions like "perform the requested action." Tool callers need to know exactly which data is read or modified before deciding to invoke an operation.

## 6. Describing a Read-Only Operation

Example controller providing catalog search:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import org.springframework.http.MediaType;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

@RestController
@Validated
class ToolProductController {

    @GetMapping(
        value = "/api/tools/products",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    @Operation(
        operationId = "searchProducts",
        summary = "Search products",
        description = "Read-only catalog search; maximum 50 results per call.",
        tags = {"Tool catalog"},
        security = @SecurityRequirement(
            name = "toolOAuth",
            scopes = {"catalog.read"}
        )
    )
    ProductSearchResponse searchProducts(
        @Parameter(description = "Search keyword, up to 80 characters")
        @RequestParam(required = false)
        @Size(max = 80)
        String q,
        @Parameter(description = "Maximum number of results, from 1 to 50")
        @RequestParam(defaultValue = "20")
        @Min(1) @Max(50)
        int limit
    ) {
        // Call catalog read service and return DTO.
        return new ProductSearchResponse(List.of(), 0);
    }
}

record ProductSummary(String id, String name) {}

record ProductSearchResponse(List<ProductSummary> items, int count) {}
~~~

The example constrains `limit` in both runtime validation and parameter metadata. Documenting limits in descriptions or schemas does not replace validation. The server must reject out-of-bounds inputs even if a client ignores the OpenAPI document.

Jakarta Validation annotations require a runtime provider, typically supplied by `spring-boot-starter-validation`. For method parameters such as `q` and `limit`, `@Validated` enables AOP proxy-based method validation in configurations using method validation; check the validation behavior of your running Spring MVC version. For request bodies, `@Valid` triggers object validation after deserialization.

Responses should use DTOs containing only fields permitted for exposure. Never return persistence entities directly if they contain internal fields, lazy relationships, or properties not meant for tool callers.

## 7. Describing a Write Operation

If a tool caller needs to create orders, clearly describe the impact and use a dedicated scope:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ToolOrderController {

    @PostMapping("/api/tools/orders")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(
        operationId = "createOrder",
        summary = "Create order",
        description = """
            Creates a new order and mutates business state.
            Call only when the user has requested order creation and confirmed the contents.
            Do not auto-retry without verifying whether the previous request was already processed.
            """,
        tags = {"Tool orders"},
        security = @SecurityRequirement(
            name = "toolOAuth",
            scopes = {"orders.write"}
        )
    )
    OrderCreatedResponse createOrder(
        @Valid @RequestBody CreateOrderRequest request
    ) {
        // Verify resource permissions, run business checks, and create order.
        return new OrderCreatedResponse("pending");
    }
}

record CreateOrderRequest(
    @NotBlank
    @Schema(description = "Product ID permitted for ordering")
    String productId,
    @Min(1)
    @Schema(description = "Quantity greater than 0")
    int quantity
) {}

record OrderCreatedResponse(String status) {}
~~~

For write operations, consider adding an idempotency key for safe retries, quantity caps, per-resource permission checks, actor auditing, and correlation IDs. Do not let tool callers decide on their own to retry an order-creation request based solely on a timeout; a timeout does not prove the server failed to process the request.

## 8. Declaring OAuth2 Scopes in OpenAPI

OpenAPI should describe the minimum permissions required for each operation. Example using OAuth2 client credentials for server-to-server integration:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "toolOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        clientCredentials = @OAuthFlow(
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "catalog.read",
                    description = "Read published catalog"
                ),
                @OAuthScope(
                    name = "orders.write",
                    description = "Create orders"
                )
            }
        )
    )
)
class ToolCallerSecuritySchemeConfiguration {
}
~~~

Read operations declare `catalog.read`; write operations declare `orders.write`. Clients should only be granted scopes necessary for their tasks. Never grant `orders.write` to an integration that only searches the catalog.

`@SecurityRequirement` adds security metadata to the OpenAPI document. It does not issue scopes, validate tokens, or configure authorization in Spring Security. The resource server must validate signatures, issuer, audience, expiration, and scopes/authorities per system policy.

## 9. Separating Document Fetch Permission from Operation Execution Permission

There are two independent security decisions:

1. Who is allowed to fetch `/v3/api-docs/tool-caller-v1` to discover the contract?
2. Who is allowed to call `GET /api/tools/products` or `POST /api/tools/orders`?

A system might let an internal registry fetch the document with the `docs.export` authority, while the tool runtime requires `catalog.read` or `orders.write` scopes. Never treat permission to fetch documentation as permission to call APIs, and never assume anyone able to read the document is allowed to execute its operations.

Example authorization rules to integrate into the application's `SecurityFilterChain`:

This snippet shows rules to merge into an existing `authorizeHttpRequests`; import `org.springframework.http.HttpMethod` and retain the application's other rules per current policy.

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(
        HttpMethod.GET,
        "/v3/api-docs/tool-caller-v1",
        "/v3/api-docs/tool-caller-v1.yaml"
    ).hasAuthority("docs.export")
    .requestMatchers(
        HttpMethod.GET,
        "/api/tools/products"
    ).hasAuthority("SCOPE_catalog.read")
    .requestMatchers(
        HttpMethod.POST,
        "/api/tools/orders"
    ).hasAuthority("SCOPE_orders.write")
    .anyRequest().authenticated()
)
~~~

The snippet illustrates rules to merge into an existing security chain. With Spring Security's default OAuth2 Resource Server, scopes map to authorities prefixed with `SCOPE_`. If your application uses a custom converter or gateway, use the actual authority names. Ensure matchers protect the YAML URL as well as JSON.

If Swagger UI needs to fetch `swagger-config`, configure that endpoint according to the UI policy. If the tool registry fetches OpenAPI JSON/YAML directly without Swagger UI, there is no need to expose the UI solely for discovery.

## 10. Using Vendor Extensions When the Tool Registry Needs Custom Metadata

Some integration systems read extra metadata not covered by standard OpenAPI fields, such as tool categories or read-only markers. You can add vendor extensions prefixed with `x-`:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.extensions.Extension;
import io.swagger.v3.oas.annotations.extensions.ExtensionProperty;

@Operation(
    operationId = "searchProducts",
    summary = "Search products",
    extensions = @Extension(
        name = "x-tool",
        properties = {
            @ExtensionProperty(name = "category", value = "catalog"),
            @ExtensionProperty(
                name = "readOnly",
                value = "true",
                parseValue = true
            )
        }
    )
)
~~~

Vendor extensions are extensible metadata. OpenAPI permits extensions under the `x-` convention, but that does not mean every tool caller understands `x-tool.category` or `x-tool.readOnly`. Only add extensions once consumers agree on schema, data types, and handling. Inspect the actual JSON output to verify booleans serialize as booleans rather than strings.

Extensions do not replace HTTP methods, OAuth2 scopes, or runtime authorization. Never mark an operation as `readOnly` solely in metadata if the actual handler has side effects.

## 11. Protecting Data and Constraining Inputs

The OpenAPI document helps tool callers understand schemas, but does not enforce validation on its own. For tool-facing endpoints, constrain:

- Search string lengths and request body sizes.
- Array element counts and pagination page sizes.
- Enum values and ID formats.
- File sizes if uploads are supported.
- Queryable time or date ranges.
- Number of resources modifiable in a single request.

Use Bean Validation annotations such as `@NotBlank`, `@Size`, `@Min`, `@Max`, and `@Pattern` alongside business validation in services. Use separate request/response DTOs to avoid letting tool callers overwrite internal fields such as `ownerId`, `approved`, `role`, or server-managed state.

Do not expose:

- Actuator, debug, internal metrics, or admin endpoints.
- Internal hostnames, IPs, ports, or paths in `servers`.
- Tokens, passwords, API keys, or personal data in `example`/`default`.
- Stack traces, SQL, deployment details, or infrastructure internals in `description`.
- Operations taking arbitrary URLs for the server to fetch without proper SSRF defenses.

When request/response examples are needed, use synthetic data containing no real information. Inspect `example`, `default`, `description`, and `servers` before publishing the document.

## 12. Verifying the Published Operation Set

Include a contract allowlist test to catch new endpoints accidentally leaking into the group. For OpenAPI JSON, read `paths` and verify every method:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.HashSet;
import java.util.Iterator;
import java.util.Locale;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ToolCallerOpenApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    com.fasterxml.jackson.databind.ObjectMapper objectMapper;

    @Test
    @WithMockUser(authorities = "docs.export")
    void publishesOnlyApprovedOperations() throws Exception {
        MvcResult result = mockMvc.perform(
                get("/v3/api-docs/tool-caller-v1")
            )
            .andExpect(status().isOk())
            .andReturn();

        JsonNode document = objectMapper.readTree(
            result.getResponse().getContentAsString()
        );

        assertThat(operations(document)).containsExactlyInAnyOrder(
            "GET /api/tools/products",
            "POST /api/tools/orders"
        );
    }

    private static Set<String> operations(JsonNode document) {
        Set<String> result = new HashSet<>();
        JsonNode paths = document.path("paths");
        Iterator<String> pathNames = paths.fieldNames();
        Set<String> methods = Set.of(
            "get", "put", "post", "delete",
            "patch", "options", "head", "trace"
        );

        while (pathNames.hasNext()) {
            String path = pathNames.next();
            Iterator<String> keys = paths.path(path).fieldNames();
            while (keys.hasNext()) {
                String method = keys.next().toLowerCase(Locale.ROOT);
                if (methods.contains(method)) {
                    result.add(method.toUpperCase(Locale.ROOT) + " " + path);
                }
            }
        }
        return result;
    }
}
~~~

`containsExactlyInAnyOrder` verifies the operation set matches the allowlist exactly: either missing an operation or including an extra one fails the test. The test uses `@WithMockUser(authorities = "docs.export")` to satisfy document protection rules; this authority applies only to fetching OpenAPI, not to business operation scopes.

To use `@WithMockUser`, add `spring-security-test` in test scope if your project's dependency management does not already provide it:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Test YAML separately in the same test class:

~~~java
@Test
@WithMockUser(authorities = "docs.export")
void exportsToolCallerYaml() throws Exception {
    mockMvc.perform(get("/v3/api-docs/tool-caller-v1.yaml"))
        .andExpect(status().isOk())
        .andExpect(content().string(containsString("openapi:")));
}
~~~

This method reuses the test class's `mockMvc` and requires static imports for `org.hamcrest.Matchers.containsString` and `MockMvcResultMatchers.content`. If security matchers protect only JSON, the YAML test will catch the remaining unprotected endpoint.

If the group includes path parameters, preserve templates such as `/api/tools/products/{id}` in the allowlist. If the application uses YAML as the primary artifact, test the `.yaml` URL explicitly and parse it with a YAML parser; JSON tests do not prove the YAML route works as well.

## 13. Verifying Runtime Permissions Separately

Beyond document tests, test the actual endpoints:

| Request | Expected Outcome |
| --- | --- |
| No token calling `GET /api/tools/products` | 401 or entry-point denial behavior. |
| Token lacking `catalog.read` calling `GET /api/tools/products` | 403. |
| Token with `catalog.read` calling `GET /api/tools/products` | Permitted if data and business conditions are valid. |
| Token with only `catalog.read` calling `POST /api/tools/orders` | 403. |
| Token with `orders.write` calling `POST /api/tools/orders` | Permitted if request is valid and resource permissions pass. |

`@WithMockUser` is useful for testing authorization rules but does not verify real JWTs, issuers, audiences, or claim mappings. When using OAuth2 Resource Server, add tests with JWT request post-processors and integration tests for token decoders per security requirements.

For write operations, verify audit logs, idempotency, rate limits, and resource ownership. A token carrying `orders.write` should not automatically allow creating orders for any tenant or customer; the service must verify the principal's data scope.

## 14. Review Workflow Before Publishing

Before handing a group to a tool registry or integrator:

1. Confirm the business owner and purpose of each operation.
2. Compare actual methods/paths against the reviewed allowlist.
3. Confirm the group contains no actuator, admin, debug, or internal endpoints.
4. Check `operationId` uniqueness and stability.
5. Re-read descriptions, request schemas, response schemas, and possible errors.
6. Verify each operation's OAuth2 scopes and security schemes in the document.
7. Check that `servers`, `example`, and `default` do not leak internal info or secrets.
8. Run contract tests to detect extra/missing operations.
9. Run runtime authorization tests for anonymous, missing-scope, and valid-scope callers.
10. Confirm JSON/YAML export for the right group and share only with authorized consumers.
11. Record document version and revocation procedures if exposure scope changes.

When a new endpoint is added under `/api/tools/**`, do not let it automatically become an exposed tool just because the path prefix matches. Require allowlist updates, security review, and tests before release.

## 15. Common Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Tool group contains too many endpoints | `pathsToMatch` too broad or scanning entire package | Isolate tool APIs in a dedicated package and add a method/path allowlist. |
| Admin endpoint disappears from all docs | Used `@Hidden` when internal docs still needed it | Use a filter dedicated to the tool group instead of hiding globally. |
| Hidden endpoint is still callable | Confused `@Hidden` with authorization | Protect mappings via Spring Security/gateway and test runtime access. |
| New endpoint appears automatically in tool docs | Relied only on path prefix without exact allowlist | Compare operation set against a manifest/test allowlist. |
| Tool caller cannot tell what operation does | Vague `summary`, `description`, or `operationId` | Set stable `operationId` and describe impact, inputs, errors, and retry rules. |
| Tool caller invokes write operation unintentionally | Shared scopes or overly broad runtime rules | Separate read/write scopes and enforce authority checks in services. |
| Doc lists OAuth2 requirement yet API is open | Added `@SecurityRequirement` without configuring runtime security | Configure the resource server and test with real tokens. |
| JSON is protected while YAML is public | Matcher covered only JSON URL | Add matchers for `.yaml` and test both. |
| Registry misreads vendor extensions | Consumers lack a unified extension schema | Agree on the `x-*` contract, verify data types, and version it. |
| Document leaks internal hostnames | Server URL inferred from internal/proxy requests | Configure public `servers` and check forwarded headers. |
| Responses contain sensitive fields | Returned entity directly or overly broad DTO | Use an allowlisted response DTO and test schemas/responses. |

## 16. Application Principles

- Create a dedicated group for tool callers; never reuse the full-API document.
- Prefer an allowlist by HTTP method and path; package/path prefixes are only an initial filter layer.
- Use `@Hidden` when excluding an operation from all documents; use dedicated customizers when excluding from a single group.
- Keep `operationId` stable and describe operation impact clearly.
- Prefer read-only operations; write operations require scopes, business confirmation, auditing, and retry controls.
- Describe OAuth2 scopes in OpenAPI and enforce matching permissions at runtime.
- Separate document-fetch permissions from business endpoint execution permissions.
- Add `x-*` vendor extensions only when consumers agree on the contract.
- Constrain inputs, pagination, payload sizes, and returned fields with runtime validation.
- Verify the allowlist, JSON/YAML, security, and `servers` before publishing.

The endpoint scope exposed to tool callers should be a small, owned, allowlist-controlled contract. `GroupedOpenApi` creates a dedicated document; `OpenApiCustomizer` can narrow operations by method/path; OpenAPI metadata describes operations and scopes so consumers understand usage. Those layers only govern what is published. Spring Security, gateways, and services must still authenticate, authorize, rate-limit, audit, and validate data on every request. Only once contract tests confirm the exact operation set and runtime tests confirm access control should the tool group be shared with integrators.

## References

- [Springdoc OpenAPI – Multiple OpenAPI Definitions and GroupedOpenApi](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – Customizers](https://springdoc.org/)
- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object)
- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
