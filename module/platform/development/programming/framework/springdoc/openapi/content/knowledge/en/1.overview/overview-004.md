# Relationship Between Spring Code, Metadata, and the Generated API Contract

Springdoc-openapi generates an OpenAPI specification from a Spring application by combining endpoint information registered by Spring with metadata in Java code. Controller mappings indicate which endpoints exist; parameter and return types suggest request/response structures; Swagger annotations add intentional descriptions; Bean Validation supplies data constraints; Jackson defines how data is serialized and deserialized. Springdoc aggregates these sources into an OpenAPI document so the application can export JSON/YAML and render it via Swagger UI.

Understanding this relationship explains why editing an annotation can alter a schema, why a running route may not appear in documentation, or why an actual JSON response differs from the schema a developer expects. OpenAPI is not a verbatim copy of source code. It is a contract inferred from multiple metadata sources, which can then be customized and verified.

## 1. The Big Picture: From Source Code to API Contract

A Spring controller typically contains several kinds of information:

- Spring annotations describe URLs, HTTP methods, query parameters, headers, request bodies, and request handling.
- Java signatures describe parameter types and return types.
- OpenAPI annotations describe operation names, summaries, descriptions, examples, responses, and security requirements.
- Bean Validation describes data constraints such as required, length, and numeric bounds.
- Jackson annotations and serializer settings affect the JSON read or written.
- Application configuration determines which controllers are instantiated, which packages are scanned, and which documents are published.

Springdoc reads relevant information from the runtime Spring application context, combines them into OpenAPI objects, and serializes them into JSON or YAML. Swagger UI reads that document to display an interactive interface.

~~~mermaid
flowchart TD
    A["Spring Controller and Request Mapping"] --> E["Spring Handler Mapping"]
    B["Java Signatures and DTOs"] --> G["Springdoc: analyzes endpoints and data types"]
    C["Swagger/OpenAPI annotations"] --> G
    D["Bean Validation and Jackson metadata"] --> G
    E --> G
    F["Scan, group, and filter configuration"] --> G
    G --> H["OpenAPI model"]
    I["OpenApiCustomizer / OperationCustomizer"] --> H
    H --> J["OpenAPI JSON"]
    H --> K["OpenAPI YAML"]
    J --> L["Swagger UI"]
    K --> M["Validators, code generators, and CI"]
~~~

The diagram illustrates conceptual relationships. Internal details may vary by Springdoc version and web stack, but the primary metadata sources and outputs serve the same roles.

## 2. Distinguishing Three Layers: Runtime, Metadata, and Document

When reading Springdoc code, distinguish three layers:

| Layer | Question Answered | Example |
|---|---|---|
| Runtime endpoint | Does Spring accept and handle the HTTP request? | **@GetMapping("/products/{id}")** |
| Descriptive metadata | How are the endpoint and data described? | **@Operation**, **@Schema**, **@NotBlank** |
| OpenAPI document | What is in the contract published to clients? | **paths**, **parameters**, **requestBody**, **responses** |

An endpoint can exist at runtime yet be hidden from the document using **@Hidden**, **@Operation(hidden = true)**, package/path filters, or customizers. Conversely, if a controller is not created as a bean or its mapping is not registered by Spring, Springdoc usually has no standard handler to describe.

The OpenAPI document can also be supplemented or modified by customizers. Therefore, the final document does not necessarily contain only what can be inferred from a single Java method.

## 3. Spring Registers Endpoints Before Springdoc Describes Them

In Spring MVC, **@RestController** marks a class as a controller with a default response body. **@RequestMapping** and composed annotations such as **@GetMapping**, **@PostMapping**, **@PutMapping**, and **@DeleteMapping** declare request mapping conditions.

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping("/{id}")
    public ProductResponse findById(@PathVariable UUID id) {
        return productService.findById(id);
    }
}
~~~

Spring MVC discovers controller beans and registers methods along with their RequestMappingInfo in handler mappings. This information includes paths, HTTP methods, and related conditions such as params, headers, consumes, or produces.

Springdoc uses the endpoint information managed by Spring to build operations. Therefore, having the controller component-scanned, the bean initialized, and the mapping registered is the foundational prerequisite.

If a class lies outside component scan, is excluded by **@Profile** or **@Conditional**, or its module is missing from the runtime classpath, OpenAPI annotations on that class will not make the endpoint appear on their own.

## 4. Spring Annotations Describe How Requests Are Routed

Mapping annotations carry direct meaning for the HTTP contract:

| Annotation | Runtime Meaning | Information Typically Reflected in OpenAPI |
|---|---|---|
| **@RequestMapping** | General mapping by path and conditions | Path, method, and corresponding conditions |
| **@GetMapping** | Handles GET | GET operation |
| **@PostMapping** | Handles POST | POST operation |
| **@PutMapping** | Handles PUT | PUT operation |
| **@PatchMapping** | Handles PATCH | PATCH operation |
| **@DeleteMapping** | Handles DELETE | DELETE operation |
| **@PathVariable** | Extracts value from path segment | Path parameter |
| **@RequestParam** | Extracts query/form parameter | Query parameter |
| **@RequestHeader** | Extracts header value | Header parameter when applicable |
| **@RequestBody** | Reads request body | Request body schema |

Spring annotations define routing and binding behavior. They do not replace business descriptions. A method with **@GetMapping** indicates the HTTP method and path, yet does not explain what the operation does, what access permissions apply, or which error responses can occur.

## 5. Java Signatures Provide Data Types for Schema Inference

Parameter types and return types help Springdoc infer basic structures:

~~~java
@GetMapping("/{id}")
public ProductResponse findById(@PathVariable UUID id) {
    return productService.findById(id);
}
~~~

From this method, Springdoc can determine:

- The path is /api/products/{id} when combined with the class mapping.
- The HTTP method is GET.
- id is a path parameter.
- The Java UUID type is represented as type string with format UUID in OpenAPI.
- The ProductResponse return type is analyzed into a response schema.

If a method returns **List<ProductResponse>**, the document can represent the response as an array of the ProductResponse schema. If it returns **Page<ProductResponse>** or a custom wrapper, the schema depends on the concrete type, configuration, and how the library introspects models.

The more specific the data types, the clearer the contract. Types such as Object, raw Map, raw ResponseEntity, or ResponseEntity<?> often produce less accurate schemas and may require explicit **@ApiResponse**/**@Schema**.

## 6. Spring Annotations and OpenAPI Annotations Complement Each Other

Spring annotations primarily control runtime behavior. OpenAPI annotations add information intended for contract consumers.

~~~java
@GetMapping("/{id}")
@Operation(
    operationId = "getProductById",
    summary = "View product details",
    description = "Returns information for a single product by UUID."
)
public ProductResponse findById(
        @Parameter(description = "Product UUID", example = "4d7f1e0a-3e0d-4d58-9a2f-8d5f2d0c1001")
        @PathVariable UUID id) {
    return productService.findById(id);
}
~~~

In this example:

- **@GetMapping** routes the request.
- **@PathVariable** binds the path segment to the Java parameter.
- **@Operation** adds operationId, summary, and description.
- **@Parameter** adds a description and example for the path parameter.
- **ProductResponse** provides the response type for schema inference.

Springdoc merges these sources into a single operation. There is no need to repeat the path and HTTP method inside **@Operation**; let Spring mappings be the primary source for routing and use OpenAPI annotations to add descriptive metadata.

## 7. @Operation Describes the Purpose of an Endpoint

**@Operation** is typically placed on a controller method. Commonly used attributes:

| Attribute | Purpose |
|---|---|
| operationId | Stable identifier for the operation |
| summary | Short title |
| description | Explains behavior, conditions, and notes |
| tags | Groups operations |
| deprecated | Marks an operation as deprecated |
| hidden | Excludes an operation from documentation |
| security | Declares operation-level security requirements |

operationId is important for code generators and client tooling. Choose clear names that are unique within the document and stable across refactors.

summary should be brief enough to display in the operation list. description can explain side effects, business rules, pagination, idempotency, or usage conditions.

Do not use deprecated = true as a way to hide an operation. Deprecated informs clients that the operation should not be used for new integrations; the operation can still appear in the document.

## 8. @Tag Organizes Operations by Business Group

**@Tag** is commonly placed at the controller level or on individual operations:

~~~java
@RestController
@RequestMapping("/api/products")
@Tag(
    name = "Products",
    description = "Create, look up, update, and delete products"
)
public class ProductController {
}
~~~

Tags help Swagger UI group endpoints by function. Tag names should reflect business concepts understood by clients, such as Products, Orders, or Customers, rather than package names or technical class names.

One controller can contain multiple operation groups if the application is organized by use case. In that case, assign tags at the method level for clearer grouping.

## 9. @Parameter Describes Inputs Outside the Body

Path, query, header, and cookie parameters can be inferred from Spring method signatures. **@Parameter** adds description, example, schema, or other metadata:

~~~java
@GetMapping
public ProductPageResponse list(
        @Parameter(
            description = "Filter by category",
            example = "Accessories"
        )
        @RequestParam(required = false) String category,
        @Parameter(
            description = "Zero-based page index",
            example = "0"
        )
        @RequestParam(defaultValue = "0") int page) {
    return productService.findAll(category, page);
}
~~~

required = false and defaultValue are Spring metadata that affect how requests are bound. **@Parameter** helps describe the meaning for clients. When inspecting OpenAPI output, confirm that required, in, schema, and example reflect actual behavior.

Path parameters are always needed to form a complete path. If a mapping has {id} yet the method fails to bind or properly describe the parameter, inspect the handler structure and output.

## 10. @RequestBody and Request Schemas

For request bodies, Spring uses **@RequestBody** to read payloads via HttpMessageConverter, typically Jackson for JSON. Springdoc uses the DTO type and DTO metadata to describe the request body in OpenAPI.

~~~java
@PostMapping
@Operation(
    operationId = "createProduct",
    summary = "Create product"
)
public ResponseEntity<ProductResponse> create(
        @Valid @RequestBody CreateProductRequest request) {
    ProductResponse created = productService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

In OpenAPI, a request body typically consists of:

- required: whether the body is mandatory.
- content: media type, such as application/json.
- schema: data structure.
- example or examples: sample payloads.

If an endpoint accepts multiple media types such as JSON and multipart/form-data, document and verify each content type. Do not assume every request body is JSON.

## 11. DTOs Form the Contract Boundary Between API and Domain

DTOs decouple the HTTP structure from persistence entities:

~~~java
public class CreateProductRequest {

    @NotBlank
    @Size(max = 100)
    @Schema(description = "Product name", example = "Mechanical Keyboard K8")
    private String name;

    @NotBlank
    @Size(max = 40)
    @Schema(description = "Unique SKU code", example = "KB-K8-BLK")
    private String sku;

    @NotNull
    @DecimalMin("0.00")
    @Digits(integer = 12, fraction = 2)
    @Schema(description = "Selling price", example = "129.90")
    private BigDecimal price;

    // getters and setters
}
~~~

DTOs tell Springdoc which fields clients can send. Entities may hold audit columns, internal states, lazy relationships, or data that should not be exposed. If entities are used directly for requests/responses, a database change can unintentionally become an API change.

Consider separate DTOs for create, update, and response when operations have different requirements. A create request typically does not accept a server-generated id; a response may contain id and timestamps.

## 12. Bean Validation Adds Data Constraints

Bean Validation annotations such as **@NotNull**, **@NotBlank**, **@Size**, **@Min**, **@Max**, **@DecimalMin**, and **@Pattern** can be used to:

1. Validate data at runtime when a request is validated.
2. Supply metadata to the OpenAPI schema when supported by the version and configuration.

Example:

~~~java
public class CreateProductRequest {

    @NotBlank
    @Size(min = 2, max = 100)
    private String name;

    @NotNull
    @DecimalMin("0.00")
    private BigDecimal price;
}
~~~

The schema can express that name is required with minLength/maxLength bounds, and price has a corresponding minimum. However, inspect the generated document; do not assume every custom validator is automatically translated into a JSON Schema constraint.

A custom validation rule like SKU uniqueness typically depends on a database or service. OpenAPI can describe the rule via description, but cannot enforce uniqueness checks on the client.

## 13. Jackson Determines the Actual JSON Shape

Jackson annotations affect serialization/deserialization and therefore relate directly to schemas:

| Annotation | Common Effect |
|---|---|
| **@JsonProperty** | Property name in JSON |
| **@JsonIgnore** | Skips property during read/write depending on configuration |
| **@JsonProperty(access = WRITE_ONLY)** | Accepted on input only, not serialized in responses |
| **@JsonProperty(access = READ_ONLY)** | Emitted in responses only, not accepted as input |
| **@JsonInclude** | Controls when a property is serialized |
| **@JsonFormat** | Formats dates/times or values |
| **@JsonView** | Selects property groups by view |

Example:

~~~java
public class AccountResponse {

    private UUID id;

    @JsonProperty("display_name")
    private String displayName;

    @JsonIgnore
    private String internalNote;
}
~~~

The actual JSON can use display_name and omit internalNote. When generating schemas, ensure the document reflects the same JSON rules. In particular, never include passwords or secrets in a response DTO and rely solely on UI hiding.

If the same DTO is used for both requests and responses, READ_ONLY, WRITE_ONLY, JsonView, or custom serializers can cause schemas to differ by data direction. Separate DTOs are usually clearer and less surprising.

## 14. Java Return Types Help Describe Responses

Controller return types are an important metadata source:

~~~java
@GetMapping("/{id}")
public ProductResponse get(@PathVariable UUID id) {
    return productService.findById(id);
}
~~~

~~~java
@GetMapping
public List<ProductResponse> list() {
    return productService.findAll();
}
~~~

The first case describes a single ProductResponse; the latter describes an array of ProductResponse.

With **ResponseEntity<ProductResponse>**, the generic type still provides the response body info, while ResponseEntity lets you control status and headers at runtime. If using **ResponseEntity<Void>**, the success response has no body. If using **ResponseEntity<?>**, Object, or raw types, you may need to declare the response schema with **@ApiResponse**.

Do not confuse ResponseEntity with the body schema. ResponseEntity is a wrapper controlling the HTTP response; the inner generic type is usually the body.

## 15. @ApiResponse Describes Individual HTTP Outcomes

An operation can have multiple responses:

~~~java
@GetMapping("/{id}")
@Operation(operationId = "getProductById", summary = "View product details")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Product found",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Product not found",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ErrorResponse.class)
        )
    )
})
public ProductResponse get(@PathVariable UUID id) {
    return productService.findById(id);
}
~~~

responseCode is the HTTP status. description explains the case. content describes the media type and body schema. For a 204 response, there is typically no content body.

Springdoc can infer success responses from the return type, whereas business errors like 400, 404, or 409 usually need explicit descriptions. Writing a response in OpenAPI does not make the controller return that status on its own; runtime code must still execute the corresponding behavior.

## 16. Default Responses and Explicit Responses

You can combine method-signature inference with annotations:

- A method returning ProductResponse suggests the success response schema.
- ResponseEntity allows controlling status/headers.
- **@ApiResponse** explicitly states status codes and schemas for key outcomes.
- **@Content** specifies the media type.
- **@Schema(implementation = ...)** points to the model when the return type is not clear enough.

Once declared explicitly, inspect the final document to avoid duplicate responses, mismatched status codes, or missing schemas. Annotations do not replace reading the output.

## 17. @Schema Describes Models and Properties

**@Schema** can be placed on classes or fields:

~~~java
@Schema(
    name = "ProductResponse",
    description = "Product information returned by the system"
)
public class ProductResponse {

    @Schema(description = "Identifier", format = "uuid")
    private UUID id;

    @Schema(description = "Product name", example = "Mechanical Keyboard K8")
    private String name;

    @Schema(description = "Selling price", minimum = "0", example = "129.90")
    private BigDecimal price;
}
~~~

@Schema adds names, descriptions, examples, formats, bounds, required flags, or model representations. Only declare constraints here when they reflect the actual contract. If the schema states price is non-negative yet runtime accepts negative numbers, the documentation and API contradict each other.

## 18. components/schemas Enables Model Reuse

OpenAPI typically places reused schemas under components/schemas and references them with $ref:

~~~yaml
components:
  schemas:
    ProductResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        name:
          type: string
        price:
          type: number
          minimum: 0
~~~

An operation can reference it:

~~~yaml
responses:
  "200":
    description: Product found
    content:
      application/json:
        schema:
          $ref: "#/components/schemas/ProductResponse"
~~~

Schema reuse avoids duplicating structures and keeps the document concise. When reading OpenAPI JSON, follow $ref to see the actual model rather than looking only at path operations.

## 19. JSON Property Names and Schema Names Need Not Match Java Names

Java field names can differ from JSON names due to Jackson naming strategies or **@JsonProperty**. Schema names can also be customized using **@Schema(name = ...)**.

Example:

~~~java
public class CustomerResponse {

    @JsonProperty("customer_code")
    @Schema(description = "Customer code", example = "CUS-1001")
    private String customerCode;
}
~~~

Clients send and receive customer_code if Jackson configuration applies that annotation. Do not assume clients will see the Java field name customerCode.

When schema names collide or two classes in different packages share the same schema name, inspect components/schemas and disambiguate the names clearly.

## 20. Security Metadata Describes How Clients Authenticate

An OpenAPI security scheme can describe HTTP Bearer authentication:

~~~java
@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class OpenApiConfiguration {
}
~~~

An operation can require the scheme:

~~~java
@SecurityRequirement(name = "bearerAuth")
@GetMapping("/me")
public ProfileResponse profile() {
    return profileService.current();
}
~~~

Security metadata helps Swagger UI show the Authorize button and helps clients understand how to pass credentials. It does not verify tokens or grant permissions. Spring Security, an OAuth2 Resource Server, or the actual authentication mechanism enforces security.

If an operation is public, do not apply a global security requirement mechanically. Accurately document the protection scope.

## 21. Global Configuration and API Information

General document metadata can be declared using **@OpenAPIDefinition**:

~~~java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Product Catalog API",
        version = "1.0.0",
        description = "Product catalog management API"
    )
)
public class OpenApiConfiguration {
}
~~~

info.title, info.version, and info.description describe the API document. The version here is the published contract version; it does not have to match the Maven artifact version or Spring Boot version.

Server, contact, license, externalDocs, and security metadata can be declared at the document level when needed. This metadata helps clients understand the environment and API usage policies.

## 22. Package and Path Configuration Controls Scan Scope

Springdoc can restrict endpoints by package or path. Example:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.catalog.api
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
~~~

If a controller lies outside those packages or its path fails the filter, the operation may be absent from the document even though Spring still registers the handler.

These filters act as documentation scope policies. Before removing a filter to fix a missing operation, verify whether the endpoint is meant to be published. Exposing all internal endpoints in Swagger UI can reveal an API surface not intended for clients.

## 23. GroupedOpenApi Creates Multiple Contracts by Group

One application can serve multiple documents:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .packagesToScan("com.acme.catalog.api.public")
        .pathsToMatch("/api/**")
        .build();
}
~~~

Document groups are typically accessed as /v3/api-docs/{groupName}, such as /v3/api-docs/public.

An operation might appear in the default document yet be missing from the public group due to filters. When inspecting Swagger UI, verify the currently selected group and the corresponding JSON endpoint.

Groups are helpful when you have public APIs, partner APIs, and internal APIs with different scopes. Each group should be treated as a separate contract and verified independently.

## 24. Customizers Modify OpenAPI After Endpoint Analysis

Springdoc provides extension points such as:

- OpenApiCustomizer: customizes the OpenAPI document.
- GlobalOpenApiCustomizer: applies customizations globally across configured scopes.
- OperationCustomizer: customizes operations during document generation.
- Customizers attached to GroupedOpenApi: tailor a specific document group.

Example adding a shared extension:

~~~java
@Bean
OpenApiCustomizer addDocumentExtension() {
    return openApi -> {
        openApi.addExtension("x-owner-team", "catalog-platform");
    };
}
~~~

Customizers can add tags, extensions, security, servers, or remove paths/operations. Consequently, the final OpenAPI output is the result of scanning plus all registered customizations.

When an operation disappears or metadata differs from expectations, locate relevant customizers and inspect their conditions. Never assume the document reflects controller annotations alone.

## 25. Springdoc Generates the Document; Swagger UI Only Displays It

These two parts have distinct roles:

| Component | Role |
|---|---|
| Springdoc runtime | Analyzes endpoints and builds the OpenAPI document |
| /v3/api-docs | Default endpoint serving OpenAPI JSON |
| /v3/api-docs.yaml | Endpoint serving OpenAPI YAML if supported/configured |
| Swagger UI | UI that reads the document and lets users try requests |

Swagger UI is not where the primary contract is defined. If the UI does not show an operation, call the JSON endpoint directly to determine whether the document contains the operation. If JSON is right yet the UI is wrong, check the document URL, group selection, UI configuration, or cache.

Similarly, disabling Swagger UI does not necessarily disable API docs. Both features have separate configuration flags.

## 26. Reading a Generated OpenAPI Operation

Condensed example:

~~~yaml
paths:
  /api/products/{id}:
    get:
      tags:
        - Products
      operationId: getProductById
      summary: View product details
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        "200":
          description: Product found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ProductResponse"
        "404":
          description: Product not found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
~~~

Read an operation in sequence:

1. paths gives the URL template.
2. get/post/put/delete gives the HTTP method.
3. tags, operationId, summary, and description provide metadata.
4. parameters describes inputs outside the body.
5. requestBody describes the input payload if present.
6. responses describes HTTP outcomes.
7. $ref points to shared schemas under components.

This is the structure read by client generators and contract validators; consumers do not need to know the original Java classes to use the document.

## 27. Tracing a Field from Java to OpenAPI

Suppose a DTO has a field:

~~~java
@NotBlank
@Size(max = 80)
@Schema(description = "Display name", example = "Keyboard K8")
private String name;
~~~

Contributing information sources:

| Source | Meaning |
|---|---|
| String | Data type is string |
| @NotBlank | Cannot be null/empty/whitespace-only at runtime |
| @Size(max = 80) | Length limit |
| @Schema(description = ...) | Description for API consumers |
| @Schema(example = ...) | Sample value |
| Jackson metadata | Property name and serialization rules |

The OpenAPI schema can represent the property as string, required, and maxLength 80 along with description/example. Exact details depend on version and how the model is introspected.

The key takeaway is that no single annotation supplies all information. The contract is synthesized from Java types, validation, OpenAPI metadata, and serialization metadata.

## 28. Tracing an Operation from Controller to Document

Example:

~~~java
@PostMapping
@Operation(
    operationId = "createProduct",
    summary = "Create product",
    description = "Creates a new product and returns the created resource."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Product created",
        content = @Content(
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid request",
        content = @Content(
            schema = @Schema(implementation = ErrorResponse.class)
        )
    )
})
public ResponseEntity<ProductResponse> create(
        @Valid @RequestBody CreateProductRequest request) {
    ProductResponse created = productService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

The Spring mapping provides POST and the path combined from class/method. The parameter type with @RequestBody provides the request body. @Valid and DTO constraints describe validation rules. @Operation adds operation semantics. @ApiResponse declares 201 and 400. The generic type of ResponseEntity indicates the success body is ProductResponse.

The resulting document will have a POST operation, requestBody schema CreateProductRequest, response 201 with ProductResponse, and response 400 with ErrorResponse. Runtime must still emit the documented status codes and bodies.

## 29. Inference Order and Explicit Metadata

You can let Springdoc infer many parts from code:

- Mappings from Spring handlers.
- Parameters from method signatures.
- Schemas from DTOs and return types.
- Constraints from Bean Validation.
- Additional metadata from Swagger annotations.

When Java types cannot express the contract sufficiently, use explicit annotations. For example:

- ResponseEntity<?> needs @ApiResponse pointing to the schema.
- A business error code needs a corresponding @ApiResponse.
- A field needing description/example needs @Schema.
- A non-obvious query parameter needs @Parameter.

Do not annotate everything just because you can. Duplicate metadata increases the chance of contradictions and makes maintenance harder. Add annotations where information cannot be inferred or needs an explicit commitment.

## 30. One Source Change Can Affect Multiple Parts of the Document

Code changes can impact the contract in many ways:

| Source Change | OpenAPI Part That Can Change |
|---|---|
| Changing @GetMapping to @PostMapping | HTTP method |
| Changing class-level @RequestMapping | Paths of multiple operations |
| Changing String type to UUID | Parameter schema and format |
| Adding @NotBlank | Required/constraints if supported |
| Changing @JsonProperty | JSON/schema property name |
| Adding @Schema(example=...) | Example |
| Changing return type | Response schema |
| Adding @Hidden | Operation may disappear |
| Changing package/path filters | Document scope |
| Adding a customizer | Final document content |

Consequently, a controller or DTO change can be a breaking change for clients even when the application still compiles and internal tests still pass.

## 31. The OpenAPI Document Is a Controlled Artifact

The document can be saved as JSON/YAML to:

- Review in pull requests.
- Validate structure.
- Generate client SDKs or server stubs.
- Diff against released versions.
- Detect breaking changes.
- Distribute to partners and developer portals.

Do not treat /v3/api-docs merely as a debugging page. For APIs with external clients, the OpenAPI document is a release artifact on par with a schema or contract file.

## 32. Distinguishing Runtime Documents from Exported Files

The OpenAPI document can be fetched directly from a running application or exported during a build. Both approaches serve different purposes:

| Retrieval Method | Advantage | Caveat |
|---|---|---|
| Runtime endpoint | Reflects active profile and running configuration | Must query the right instance and group |
| Build-time export | Easy to store artifacts in CI | Needs suitable runtime config to boot the app |
| Committed file | Easy to review and distribute | Can go stale if not regenerated |

When comparing two documents, ensure they come from the same commit, profile, feature flags, and document group. Otherwise, differences may stem from environment config rather than source code.

## 33. Inspecting the Document Instead of Only Looking at Annotations

A basic inspection workflow:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o target/openapi.json
~~~

List paths:

~~~bash
jq -r '.paths | keys[]' target/openapi.json
~~~

Inspect an operation's responses:

~~~bash
jq '.paths["/api/products/{id}"].get.responses' target/openapi.json
~~~

Inspect a schema:

~~~bash
jq '.components.schemas.ProductResponse' target/openapi.json
~~~

These commands verify the actual output clients will receive. If annotations look right in source yet JSON is wrong, investigate runtime profiles, dependency versions, mapping scans, filters, and customizers.

## 34. Checking Handler Mappings and OpenAPI to Isolate Root Causes

Spring Boot Actuator provides a mappings endpoint to inspect registered handlers. In secured development environments, you can expose the mappings endpoint and inspect /actuator/mappings.

Combine both results:

| Present in Spring Handler Mapping | Present in OpenAPI | Interpretation |
|---|---|---|
| Yes | Yes | Handler is registered by Spring and document contains the operation |
| Yes | No | Check @Hidden, filters, groups, or customizers |
| No | No | Check beans, component scan, profiles, mappings, and proxies |
| No | Yes | Check customizers adding operations manually or reading from a different runtime |

Do not expose actuator mappings publicly unless necessary; this endpoint can reveal internal paths and application structure.

## 35. Easily Misunderstood Cases

**Endpoint runs yet is missing from Swagger UI.** The endpoint may be hidden, excluded from the selected document group, or filtered out by package/path filters. Call the JSON endpoint before editing the controller.

**Swagger UI fails to open yet JSON still exists.** Check the UI dependency, springdoc.swagger-ui.enabled, UI path, and document URL. Do not disable API docs if you only want to hide the UI.

**Schema lacks expected constraints.** Check validation dependencies, @Valid, annotation targets, Springdoc version, and OpenAPI output. Custom constraints do not necessarily translate automatically to JSON Schema.

**JSON response differs from schema.** Check Jackson annotations, naming strategies, serializers, JsonView, and the actual DTO returned.

**Response status differs from documentation.** Check ResponseEntity, exception handlers, status mappings, and HTTP tests.

**Operation vanishes after adding a customizer.** Check OpenApiCustomizer, GlobalOpenApiCustomizer, and OperationCustomizer, including customizers attached specifically to a group.

## 36. Limits of Automatic Inference

Springdoc can infer a lot, yet cannot automatically know all business rules:

- Unique SKU rules require business logic or database checks.
- Resource ownership requires authorization logic.
- Rate-limit conditions depend on a gateway or filter.
- Side effects like sending emails or creating payments need descriptions.
- PATCH semantics and null-field handling must be designed intentionally.
- Retry/idempotency rules may need dedicated headers and descriptions.
- Business-specific error responses must be declared.

If information matters to clients yet does not appear in types or annotations, document it clearly using OpenAPI annotations or customizers. Do not expect the tool to infer semantics that code does not express.

## 37. Version Management and Compatibility

Springdoc must be compatible with the Spring Boot, Spring Framework, and web stack versions the application uses. Choose the starter matching Spring MVC or Spring WebFlux and check the compatibility matrix for the version in use.

When upgrading Spring Boot or Springdoc:

1. Check the dependency tree to detect multiple Swagger/OpenAPI versions coexisting.
2. Check annotation imports and packages.
3. Start the application with the profile intended for release.
4. Export OpenAPI JSON/YAML.
5. Diff the document before and after upgrading.
6. Run validators and contract tests.

A library upgrade can alter how schemas or annotation metadata are inferred. Do not assume the API is unchanged simply because controller source code did not change.

## 38. Multi-Layer Contract Testing

Three complementary types of tests exist:

| Test | Verifies |
|---|---|
| Unit/service test | Business rules |
| HTTP integration test | Runtime status, headers, and body |
| OpenAPI document test | Path, parameter, schema, and response contract |

For example, an HTTP test can verify POST returns 201 and Location. An OpenAPI document test verifies the POST operation documents response 201 with ProductResponse. Both must coexist to catch cases where documentation is right yet runtime is wrong, or vice versa.

Once an API is released, add compatibility checks against a baseline. A change can be valid in code yet break existing clients, such as deleting a response field, changing a type, or removing a promised status code.

## 39. Checklist for Reviewing an API Change

When reviewing a pull request modifying controllers or DTOs, ask:

- [ ] Did the mapping path or HTTP method change?
- [ ] Were parameters added, removed, or modified?
- [ ] Did the request body change required fields, types, or constraints?
- [ ] Did JSON properties change names or serialization rules?
- [ ] Did return types, status codes, or headers change?
- [ ] Do error responses maintain a stable structure?
- [ ] Do security requirements reflect actual authorization?
- [ ] Does operationId remain stable and unique?
- [ ] Do document groups place operations in the right scope?
- [ ] Has OpenAPI JSON/YAML been regenerated and validated?
- [ ] Are there contract tests for significant changes?

This checklist makes OpenAPI part of API review rather than an afterthought once coding finishes.

## 40. Key Takeaways

- Spring mappings determine endpoints and routing conditions at runtime.
- Java method signatures and DTOs supply data types to infer parameters, request bodies, and response schemas.
- Swagger/OpenAPI annotations add intentional descriptions for operations, parameters, responses, and models.
- Bean Validation describes part of the constraints while enforcing data validation when enabled.
- Jackson affects property names and actual JSON output.
- Springdoc aggregates metadata into the OpenAPI document; customizers can modify the result after scanning.
- Swagger UI displays the document, while /v3/api-docs is the JSON contract output.
- Runtime endpoints can exist without being published in the document; hiding docs does not replace security.
- OpenAPI output must be inspected directly, not only by looking at annotations or the UI.
- Contract tests and CI validation keep source, runtime, and documentation consistent.

The relationship between Spring code, metadata, and the API contract is a transformation pipeline. Spring defines endpoints; Java signatures, DTOs, validation, and Jackson add data details; Swagger annotations describe what code cannot express on its own; Springdoc synthesizes everything into an OpenAPI document. Understanding what each source contributes allows developers to explain and control the exact contract changes clients receive.

## References

- Springdoc OpenAPI – Documentation and FAQ: https://springdoc.org/
- Springdoc OpenAPI – FAQ: https://springdoc.org/faq.html
- Spring Framework – Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann.html
- Spring Framework – Request Mapping: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Swagger Core – OpenAPI Annotations: https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations
- OpenAPI Specification: https://spec.openapis.org/oas/latest.html
