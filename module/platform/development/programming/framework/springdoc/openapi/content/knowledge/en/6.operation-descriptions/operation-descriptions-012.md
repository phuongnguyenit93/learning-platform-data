# Checking Precedence When Configuration and Annotations Interact

In Spring Boot with `springdoc-openapi`, an operation can receive information from multiple sources: Spring MVC mappings, data types and annotations on DTOs, Swagger/OpenAPI annotations, an `OpenAPI` bean, customizers, and `springdoc.*` properties. When multiple sources describe the same aspect—such as responses, schemas, servers, or summary—the generated document may differ from what developers expect.

There is no single rule like "annotations always beat configuration" or "configuration always beats annotations" across every case. Each source has its own scope. Spring determines how real requests are routed and serialized; Springdoc collects that information to build documentation; Swagger annotations add metadata; customizers can modify the constructed OpenAPI model; and configuration properties control how Springdoc operates. To resolve conflicts accurately, first identify which field is affected and which source has authority over that field.

## 1. Distinguishing the Layers of Information

An OpenAPI document is built from several layers of data. You can view them by role:

| Source | Decision Scope | Example | Directly Affects Runtime API? |
|---|---|---|---|
| Spring MVC/WebFlux mappings | HTTP method, path, params, headers, consumes, produces, and invoked handler | `@GetMapping`, `@RequestMapping` | Yes |
| Java types and serialization config | Actual data read, written, and serialized to JSON/XML | DTOs, Jackson, `@JsonProperty`, `@JsonIgnore` | Yes |
| Swagger/OpenAPI annotations | Metadata describing operations, parameters, schemas, requests, responses, and security | `@Operation`, `@Schema`, `@ApiResponse` | No |
| `OpenAPI` bean or `@OpenAPIDefinition` | Document-level metadata such as title, version, contact, license, servers | `new OpenAPI().info(...)` | No |
| Springdoc properties | Enabling/disabling endpoints, paths, scanning scope, default media types, UI, and integration behavior | `springdoc.api-docs.path` | Usually no; mainly affects doc generation/serving |
| Customizers | Modifying the OpenAPI model or operations during doc generation | `OperationCustomizer`, `OpenApiCustomizer` | No |
| Swagger UI properties | How the UI loads and renders documentation | `springdoc.swagger-ui.path`, `doc-expansion` | No |

Key takeaway: documentation metadata never replaces runtime configuration. For instance, `@Operation(summary = "... ")` can change the operation description text, yet it does not change the URL registered by Spring MVC. Likewise, `@SecurityRequirement` documents a security requirement in OpenAPI, while Spring Security enforces access permissions.

## 2. Spring Mappings Determine Real Requests

Springdoc derives endpoints from handlers registered by Spring. Annotations such as `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PathVariable`, `@RequestParam`, and attributes like `headers`, `consumes`, `produces` determine which requests route to which methods.

Example:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping(value = "/{id}", produces = "application/json")
    @Operation(
        summary = "Look up product",
        description = "Retrieves product details by identifier."
    )
    ProductResponse getById(@PathVariable Long id) {
        return productService.getById(id);
    }
}
```

In this case:

- The Spring mapping creates the `GET /api/products/{id}` route and restricts response content types according to `produces`.
- `@PathVariable` binds the `id` parameter from the path.
- `@Operation` supplies summary and description for the operation in documentation.

If summary or description in `@Operation` states the endpoint uses POST while the mapping is GET, real requests will still not become POST. `@Operation` does not declare routes or HTTP methods; Swagger annotations do not alter mappings registered with Spring. When descriptions and mappings contradict each other, fix the description or mapping to match the intended contract, then re-verify both the live API and generated documentation.

Properties like `springdoc.paths-to-match`, `springdoc.packages-to-scan`, or corresponding settings in `GroupedOpenApi` restrict which endpoints are included in documentation. They neither add routes nor alter mappings. An endpoint can work normally yet stay absent from documentation if it lies outside the scan scope of the document or group being viewed.

## 3. Swagger Annotations Supplement Spring-Inferred Metadata

Springdoc can infer methods, paths, parameters, and many schemas from Spring handlers and Java types. Swagger annotations help describe information not fully conveyed by method signatures.

| Annotation | Typically Added Content |
|---|---|
| `@Tag` | Operation group name and description |
| `@Operation` | Summary, description, operationId, tags, and operation metadata |
| `@Parameter` | Parameter description, example, required flag, and schema |
| `@ApiResponse` | Response description by status code, media type, and schema |
| Swagger `@RequestBody` | Request body description, content, and examples |
| `@Schema` | Schema and property descriptions, examples, format, and constraints |
| `@SecurityScheme` | Declaring authentication mechanisms in documentation |
| `@SecurityRequirement` | Attaching security scheme requirements to an operation or controller |
| `@Hidden` | Excluding supported elements from documentation |

When an annotation describes a field Springdoc can infer, the annotation is typically used to clarify or adjust the generated metadata. However, how complex attributes such as response content, schema composition, or references merge can depend on Springdoc and Swagger Core versions. Do not assume an entire object is replaced wholesale or that every attribute merges identically.

Example of describing responses:

```java
@GetMapping("/{id}")
@Operation(summary = "Get product by ID")
@ApiResponses({
    @ApiResponse(responseCode = "200", description = "Product found"),
    @ApiResponse(responseCode = "404", description = "Product not found")
})
ProductResponse getById(@PathVariable Long id) {
    return productService.getById(id);
}
```

Springdoc can infer the success response from the `ProductResponse` return type. Annotations add meaning to status codes and descriptions. If you need to declare exact media types or schemas for each response, use `@Content` and `@Schema` to express the full contract.

## 4. DTOs, Jackson, and `@Schema` Serve Different Roles

This is a frequent source of confusion. Jackson and serialization settings determine the JSON the application actually sends or receives. `@Schema` describes schemas in the OpenAPI document. Springdoc can read metadata from both sources, yet documentation annotations do not alter Jackson serialization output.

Example:

```java
public record ProductResponse(
    @JsonProperty("product_name")
    @Schema(description = "Product name", example = "Keyboard")
    String name,

    @JsonIgnore
    @Schema(description = "Internal note")
    String internalNote
) {
}
```

`@JsonProperty("product_name")` determines the property name in JSON. `@JsonIgnore` tells Jackson to skip the property according to active configuration. `@Schema` adds descriptive documentation; it will not make `internalNote` reappear in JSON if Jackson excludes that field. Similarly, `@Parameter(required = true)` or `@Schema(requiredMode = ...)` documents requirements in the contract; Spring's validation and binding decide whether real requests are rejected.

If documentation and live payloads diverge, check in order:

1. The actual DTO or record used by the controller.
2. Jackson annotations such as `@JsonProperty`, `@JsonIgnore`, `@JsonView`, `@JsonUnwrapped`, and naming strategies.
3. `ObjectMapper` configuration, Jackson modules, and custom serializers/deserializers.
4. `@Schema` or `@ArraySchema` annotations that may add or adjust metadata.
5. Actual JSON in requests/responses and the corresponding schema in `/v3/api-docs`.

Do not use `@Schema` to mask a runtime JSON discrepancy. To change the payload, fix the DTO or serialization configuration. If the payload is right yet the description is unclear, update annotations or documentation customizers.

## 5. `OpenAPI` Bean and `@OpenAPIDefinition`

Document-level information can be declared with `@OpenAPIDefinition` or an `OpenAPI` bean. Example:

```java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Product API",
        version = "1.0.0",
        description = "Product management API"
    )
)
class OpenApiDefinitionConfiguration {
}
```

Or:

```java
@Configuration
class OpenApiBeanConfiguration {

    @Bean
    OpenAPI productApi() {
        return new OpenAPI()
            .info(new Info()
                .title("Product API")
                .version("1.0.0")
                .description("Product management API"));
    }
}
```

Both mechanisms supply document-level metadata. If the same field is declared in multiple sources, do not rely on a blanket assumption that annotations or beans always win. How Springdoc combines metadata depends on its processing order and library version. The most maintainable approach is choosing one primary owner for `Info`, `Servers`, `Security`, or shared metadata, then using customizers for conditional adjustments.

If the project needs different title or version values per group, configure them explicitly per group using an appropriate customizer. Do not rely on declaring multiple `OpenAPI` beans expecting Springdoc to pick the right bean by group name.

## 6. Spring Boot Property Precedence Applies to `springdoc.*`

When the same Springdoc property is declared across multiple configuration sources, choosing the effective value follows Spring Boot's property source mechanism. For example, `springdoc.api-docs.path` may appear in a shared config file, a profile-specific file, environment variables, system properties, or command-line arguments.

In typical Spring Boot applications, command-line arguments take precedence over system properties, environment variables, and config file settings. Profile-specific configuration can override corresponding values in shared config files. Detailed ordering can include additional sources such as test properties, `@DynamicPropertySource`, or framework-supplied config; consult the documentation for your exact Spring Boot version when investigating edge cases.

Shared file example:

```yaml
springdoc:
  api-docs:
    path: /v3/api-docs
```

`application-prod.yml` file:

```yaml
springdoc:
  api-docs:
    path: /internal/openapi
```

If the `prod` profile is active, the profile-specific value is selected for this property unless a higher-precedence property source overrides it further. A command-line argument can be passed:

```bash
java -jar app.jar --springdoc.api-docs.path=/ops/openapi
```

In that case, verify the effective value instead of reading only a single YAML file. If the app enables Spring Boot Actuator, `/actuator/env` or `/actuator/configprops` endpoints can assist diagnosis, though expose them only in accordance with system security policy.

Note: Spring Boot property precedence only resolves conflicts among configuration sources sharing the same key. It does not mean `springdoc.*` properties automatically override `@Operation`, `@Schema`, or Spring mappings. Those belong to separate layers of information.

## 7. Springdoc Properties Control Scope and Document Generation

`springdoc.*` properties can affect which endpoints enter documentation, the documentation path, and how Springdoc handles responses. Examples:

```yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  packages-to-scan:
    - com.example.api
  paths-to-match:
    - /api/**
  default-consumes-media-type: application/json
  default-produces-media-type: application/json
  override-with-generic-response: true
```

Meanings:

| Property | Effect |
|---|---|
| `api-docs.enabled` | Enables or disables documentation endpoints |
| `api-docs.path` | Changes the documentation endpoint path |
| `packages-to-scan` | Restricts packages considered when generating docs |
| `paths-to-match` | Filters endpoints by path |
| `default-consumes-media-type` | Sets default media type for request bodies when inference is needed |
| `default-produces-media-type` | Sets default media type for responses when inference is needed |
| `override-with-generic-response` | Controls applying generic responses from `@ControllerAdvice` to operations per Springdoc mechanics |

These properties do not share the same scope. `paths-to-match` filters operations; `default-produces-media-type` supplies missing media type info; `override-with-generic-response` affects how generic responses are brought into the document. Do not use a property to patch a runtime mapping or serialization discrepancy.

### Responses from `@ControllerAdvice`

An application can define shared errors using `@RestControllerAdvice` and `@ExceptionHandler`. Springdoc may include these generic responses in the documentation of many operations. If an operation also declares `@ApiResponse` for the same status code, check the final result directly in the generated document because response merging depends on library version and content structure.

Example configuration controlling generic response application:

```yaml
springdoc:
  override-with-generic-response: false
```

Set `false` when you do not want Springdoc to automatically apply generic responses that way and the team wants to document responses per operation. Before changing it, check the documentation for your Springdoc version and verify the impact across all groups.

## 8. Customizers Can Modify the Model After Generation

When annotations and standard settings are not enough, Springdoc offers extension points to customize the document. Distinguish the scope of each type:

| Customizer Type | Scope |
|---|---|
| `OperationCustomizer` | Modifies a single operation while Springdoc processes a handler method |
| `OpenApiCustomizer` | Modifies the OpenAPI model of the default document |
| `GlobalOpenApiCustomizer` | Modifies models applied to the default document and groups as supported by Springdoc |

Example using `OperationCustomizer` to add metadata based on the handler:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.context.annotation.Bean;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface InternalApi {
}

@Bean
OperationCustomizer operationDescriptionCustomizer() {
    return (operation, handlerMethod) -> {
        if (handlerMethod.getMethod().isAnnotationPresent(InternalApi.class)) {
            operation.addTagsItem("Internal");
        }
        return operation;
    };
}
```

Example using `OpenApiCustomizer` to adjust shared metadata:

```java
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
OpenApiCustomizer openApiDescriptionCustomizer() {
    return openApi -> {
        if (openApi.getInfo() != null) {
            openApi.getInfo().setDescription("API documentation standardized by the platform team.");
        }
    };
}
```

Customizers are Java code executed during document generation. If a customizer sets `description` after Springdoc has read `@Operation(description = ...)`, the final value may be the one written by the customizer. When multiple customizers modify the same field, execution order matters. Use Spring's ordering mechanisms when supported by your integration version, keep logic modifying a given field in one place, and inspect the document after changes.

Do not use customizers to hide mapping bugs, alter runtime responses, or inject sensitive data into documentation. Customizers modify only the OpenAPI model, not controllers or API serialization output.

## 9. Swagger UI Is a Separate Presentation Layer

`springdoc.swagger-ui.*` properties control UI behavior such as the UI path, filtering, operation expansion, document list, or displaying request durations. They do not replace metadata inside the OpenAPI document.

Example:

```yaml
springdoc:
  swagger-ui:
    path: /docs
    filter: true
    doc-expansion: none
    display-request-duration: true
```

If Swagger UI displays stale documentation, inspect the URL the UI loads, browser or proxy caches, and the actual OpenAPI endpoint. Changing `doc-expansion` does not modify operations; changing `swagger-ui.path` does not change `/v3/api-docs`.

## 10. Troubleshooting Matrix When Multiple Sources Interact

| Scenario | Source to Check First | Resolution |
|---|---|---|
| Wrong URL or HTTP method in documentation | Spring mapping and actual handler | Fix the mapping or filter scope; do not try to fix routes via `@Operation` |
| Summary/description differs from expected | `@Operation`, app metadata, and customizers | Pick one source of ownership for content; check if customizers overwrite it |
| JSON field name differs from schema | Jackson, DTO, and `@Schema` | Verify live payload; align schema with serialization |
| Error response duplicated or altered | `@ControllerAdvice`, `@ApiResponse`, `override-with-generic-response` | Inspect operation JSON and adjust generic response application |
| Endpoint is missing | `packages-to-scan`, `paths-to-match`, groups, and `@Hidden` | Check each filter condition and the active group document |
| Title/version differs from expected value | `@OpenAPIDefinition`, `OpenAPI` bean, customizers | Pick one primary metadata source; inspect final value |
| API Docs path differs from config file | Profiles, environment variables, system properties, command line | Check effective Spring Boot property sources |
| Swagger UI renders wrong or fails to load docs | `swagger-ui.url`, group URLs, browser/proxy cache | Open JSON/YAML endpoint directly and check requests in Network tab |

This matrix shows where to start investigating. With some structures, multiple sources may be merged; verify the final value instead of inferring from a single annotation or configuration file.

## 11. Systematic Workflow for Checking Conflicts

When documentation does not reflect expectations, follow these steps in order:

1. **Verify runtime behavior.** Call the real endpoint and record URL, method, status code, headers, and request/response JSON.
2. **Fetch the document directly.** Call `/v3/api-docs` or the group URL instead of relying solely on Swagger UI.
3. **Identify the incorrect field.** Classify whether it is path/method, parameter, schema, response, document-level metadata, or UI presentation.
4. **Locate the field's owner.** For example, mappings belong to Spring; JSON names belong to Jackson; summaries belong to operation metadata; API Docs paths belong to Springdoc configuration.
5. **Check secondary sources.** Look for annotations, `OpenAPI` beans, `@ControllerAdvice`, customizers, and config profiles that may also apply.
6. **Change one source at a time.** Isolating edits pinpoints which source produces the outcome.
7. **Re-read generated JSON/YAML.** Inspect the final field, schema references, response codes, media types, and URLs.
8. **Re-verify live API and Swagger UI.** Ensure documentation matches live behavior and the UI loads the right document.

Example using `curl` to fetch the document:

```bash
curl -s http://localhost:8080/v3/api-docs
```

You can save output to a temporary file in development to diff before and after edits. When comparing, focus on the relevant operation rather than just looking at total JSON size.

## 12. Example: Inspecting a Response Affected by Multiple Sources

Suppose a controller declares:

```java
@GetMapping("/{id}")
@ApiResponses({
    @ApiResponse(responseCode = "200", description = "Success"),
    @ApiResponse(responseCode = "404", description = "Product not found")
})
ProductResponse getById(@PathVariable Long id) {
    return productService.getById(id);
}
```

The application also has a `@RestControllerAdvice` handling `ProductNotFoundException`. If Springdoc automatically applies generic responses, the operation may receive a response inferred from the advice. When documentation has two competing descriptions for status `404`, do not guess which one wins across all versions.

Inspect the operation in the generated JSON. Then pick one convention:

- Let shared responses come from the advice and reduce duplicate declarations per controller.
- Or disable generic response application via Springdoc config and document responses per operation.
- Or intentionally use a customizer to standardize responses after Springdoc builds the operation.

In all three cases, runtime responses produced by exception handlers and actual HTTP statuses still require separate testing. OpenAPI descriptions only tell clients what the server is expected to return.

## 13. Principles for Keeping Configuration Maintainable

- Every metadata field should have one primary owner, especially title, version, servers, and security schemes.
- Let Spring mappings and DTOs reflect runtime behavior; use Swagger annotations to clarify the contract.
- Keep `@Operation`, `@ApiResponse`, and `@Schema` close to the controllers/DTOs they describe.
- Use customizers for genuinely shared rules or metadata-dependent logic that annotations struggle to express.
- Do not use `springdoc.*` properties to try to fix routing or serialization issues.
- Separate profile configurations intentionally and check effective property sources.
- When multiple customizers modify the same field, define ordering and write tests for the final value.
- Inspect JSON/YAML documents directly in CI to catch unexpected changes.
- Ensure OpenAPI documentation and live endpoints remain consistent before distributing to clients.

## 14. Checklist Before Concluding About Precedence

- [ ] Identified which exact field is in conflict.
- [ ] Confirmed Spring's actual route, method, and payload.
- [ ] Checked mappings, DTOs, Jackson, and validation where relevant.
- [ ] Checked Swagger annotations on controllers and DTOs.
- [ ] Checked `@OpenAPIDefinition` and `OpenAPI` beans for overlapping metadata declarations.
- [ ] Checked customizers and OpenAPI model modification order.
- [ ] Checked `springdoc.*` properties along with active profiles and effective property sources.
- [ ] Distinguished API Docs configuration from Swagger UI configuration.
- [ ] Opened the JSON/YAML document directly to confirm final values.
- [ ] Tested the runtime API after updating documentation.

When multiple sources interact, the reliable way to determine precedence is to understand each layer's scope and verify the final output produced by Springdoc. Spring governs HTTP behavior, Jackson governs data representation, Swagger annotations and metadata describe the contract, Springdoc configuration controls document generation, and customizers can normalize the model before it is returned. Giving each field one clear owner keeps documentation consistent and prevents hard-to-diagnose conflicts.
