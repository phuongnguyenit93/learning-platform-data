# Keeping Names, operationId, and References Stable When Modifying the Model

Springdoc-openapi generates an OpenAPI contract from controllers, DTOs, Spring annotations, and Jackson metadata. When refactoring Java code, renaming classes, or reorganizing packages, the generated documentation can change accordingly even when HTTP behavior remains unchanged. Conversely, a minor change to a JSON property name, path, or `operationId` can directly impact clients and code generation tools. Therefore, distinguish internal source-code names from public API names, and actively keep `operationId`, schema components, and `$ref` references stable.

## 1. Internal Names and Public Names Belong to Different Contracts

An endpoint has multiple names across different layers:

| Element | Example | Where It Impacts |
|---|---|---|
| Java method name | `findProductById` | Source code; can affect default operationId if not explicitly declared |
| DTO class name | `ProductView` | Source code; can affect default schema component name |
| Java property name | `productCode` | Source code; can be mapped by Jackson to a different JSON name |
| JSON property name | `product_code` | HTTP payload and OpenAPI schema |
| Path template | `/api/products/{productId}` | Public URL and OpenAPI operation |
| `operationId` | `products_getById` | Operation identifier in OpenAPI, client generators, and operation links |
| Schema component name | `Product` | `components.schemas` and `$ref`s pointing to the schema |
| Response component name | `NotFound` | `components.responses` and response `$ref`s |

Do not let renaming Java classes or methods accidentally alter identifiers that clients rely on. A good convention is to treat URLs, JSON names, operationIds, and component names as part of the API contract; Java names can change whenever needed as long as public mappings stay stable.

## 2. Why Does operationId Need to Be Stable?

Each operation in OpenAPI can have an `operationId` to uniquely identify it. Client generators frequently use this value to name generated functions. Some tools that link operations or generate SDKs also depend on it.

Operation example:

```yaml
paths:
  /api/products/{productId}:
    get:
      operationId: products_getById
      summary: Get product by ID
      parameters:
        - name: productId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Product found
```

If `operationId` is omitted, springdoc may generate a value based on mappings or method names. When renaming a method from `findById` to `getById`, the default operationId can change depending on version and configuration inference rules. Regenerated clients may change method names, causing SDK-consuming code to stop compiling even though URLs and JSON remain unchanged.

Set operationId explicitly with `@Operation`:

```java
@Operation(
    operationId = "products_getById",
    summary = "Get product by ID"
)
@GetMapping("/{productId}")
ProductResponse getById(
    @PathVariable("productId") UUID productId
) {
    return productService.getById(productId);
}
```

Afterward, you can rename the Java method, move packages, or extract services while keeping the `products_getById` operationId. Choose a naming convention that is predictable, unique within an OpenAPI document, and independent of internal class names.

### Rules for Naming operationId

- Use a consistent convention, such as `products_getById`, `products_create`, `products_search`.
- Every operation within the same OpenAPI document must have a unique operationId.
- Avoid overly generic names like `get`, `create`, or `search` when an API has multiple resource groups.
- Do not change operationId solely because a Java method was renamed or packages were restructured.
- If an operationId truly must change, treat it as an SDK-impacting change and document it in release notes.

OperationId does not replace the HTTP method or path. Clients still call endpoints by URL and method; operationId is an identifier in the document, yet it can become the public API surface of generated SDKs.

## 3. Keeping Schema Component Names Stable When Renaming Java DTOs

Springdoc normally generates component schemas based on Java types. If the `ProductResponse` class is renamed to `ProductView`, the generated component name may change accordingly. References like `#/components/schemas/ProductResponse` can then disappear, affecting other documents, client generators, or contract checkers.

Use `@Schema(name = ...)` to set a stable public component name:

```java
@Schema(
    name = "Product",
    description = "Product information published via the API"
)
public record ProductResponse(
    UUID id,
    String name,
    BigDecimal price
) {}
```

When refactoring the Java name:

```java
@Schema(
    name = "Product",
    description = "Product information published via the API"
)
public record ProductView(
    UUID id,
    String name,
    BigDecimal price
) {}
```

If the controller signature changes from `ProductResponse` to `ProductView`, the schema can still be published under the name `Product` because the component name is explicitly declared. Verify the actual output in `components.schemas`, as generic types, wrapper schemas, model converters, and springdoc versions can affect naming.

### Component Names Must Be Unique

Two classes in different packages may share the same simple name, such as `admin.ProductResponse` and `catalog.ProductResponse`. If both are published in the same document, component names may get suffixes or adjustments to avoid collisions. Do not rely on auto-suffixed names as long-term identifiers.

Assign clear, unique names:

```java
@Schema(name = "AdminProduct")
public record AdminProductResponse(Long id, String name, String internalStatus) {}

@Schema(name = "CatalogProduct")
public record CatalogProductResponse(Long id, String name, BigDecimal price) {}
```

Component names should describe API concepts and do not need to match Java class or database table names.

## 4. Keeping JSON Property Names Independent of Java Field Names

Property names in the schema must match the JSON keys clients actually send or receive. If you rename a Java field to match code style, you can preserve the wire-format name with `@JsonProperty`.

```java
public record ProductResponse(
    @JsonProperty("product_code") String productCode,
    @JsonProperty("display_name") String displayName
) {}
```

Public payload:

```json
{
  "product_code": "P-001",
  "display_name": "Ballpoint pen"
}
```

If refactoring the Java field from `productCode` to `sku`, keep the JSON name via the annotation:

```java
public record ProductResponse(
    @JsonProperty("product_code") String sku,
    @JsonProperty("display_name") String displayName
) {}
```

Clients continue sending/receiving `product_code`; the change stays inside Java code. Springdoc normally uses Jackson metadata to produce property names, though you should still check the schema after changing naming strategies, mix-ins, or custom serializers.

### Distinguishing @JsonProperty and @Schema(name)

- `@JsonProperty("product_code")` controls the runtime JSON property name and provides metadata for introspection tools.
- `@Schema(name = "Product")` on a class sets the schema component name.
- `@Schema` on a property primarily describes type, description, example, access mode, and constraints; do not use it in place of Jackson when changing runtime JSON key names.

If documentation shows the right name yet runtime JSON still differs, inspect the Jackson `ObjectMapper` and actual converters. If JSON is right yet the schema is wrong, inspect springdoc model converters and metadata annotations.

## 5. Keeping Paths and Path Parameter Names Stable

Paths are a direct part of the API. Changing `/api/products/{id}` to `/api/products/{productId}` can affect clients, gateways, caching rules, policies, and reference docs, even though the passed value is still the same UUID.

To keep path parameters consistent, explicitly specify names in both the mapping and the parameter:

```java
@GetMapping("/{productId}")
ProductResponse getById(
    @PathVariable("productId") UUID id
) {
    return productService.getById(id);
}
```

The Java variable name is `id`, while the public path parameter name remains `productId`. When refactoring the Java variable name to `productKey`, the mapping and annotation still keep `productId`:

```java
@GetMapping("/{productId}")
ProductResponse getById(
    @PathVariable("productId") UUID productKey
) {
    return productService.getById(productKey);
}
```

Similarly, explicitly declare query parameter and header names:

```java
@GetMapping
List<ProductResponse> search(
    @RequestParam(name = "keyword", required = false) String term,
    @RequestHeader(name = "X-Request-Id", required = false) String requestId
) {
    return productService.search(term, requestId);
}
```

Renaming Java variables does not alter the query parameter `keyword` or header `X-Request-Id`. Avoid depending on whether builds retain Java parameter names; declaring explicit HTTP names makes both documentation and runtime more stable.

## 6. Keeping Shared Parameter and Response Component Names Stable

When multiple operations share the same query parameter, header, or response, you can define components and reference them via `$ref`. Component names become identifiers that other documents may depend on.

Example:

```yaml
components:
  parameters:
    PageSize:
      name: size
      in: query
      description: Maximum number of items per page
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
  responses:
    ProductNotFound:
      description: Product not found
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
```

Operation referencing components:

```yaml
paths:
  /api/products/{productId}:
    get:
      parameters:
        - name: productId
          in: path
          required: true
          schema:
            type: string
            format: uuid
        - $ref: '#/components/parameters/PageSize'
      responses:
        '404':
          $ref: '#/components/responses/ProductNotFound'
```

If `ProductNotFound` is renamed to `NotFound`, every `$ref` pointing to the old name must be updated. External documents or other pipelines may also reference that name. When backward compatibility is needed, you can keep the old name as a component alias pointing to the new definition:

```yaml
components:
  responses:
    ProductNotFound:
      $ref: '#/components/responses/NotFound'
    NotFound:
      description: Resource not found
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
```

Use aliases only when structure and semantics are compatible. Never create circular `$ref` chains or self-referencing aliases.

## 7. Keeping Schema $refs Stable When Java Structure Is Reorganized

Referenced schemas commonly appear as:

```yaml
schema:
  $ref: '#/components/schemas/Product'
```

If packages or Java class names change while the component name is preserved, reference paths can remain stable. You can use `@Schema(name = "Product")` on DTOs to control component names. New class names should not automatically become public names if the goal is preserving the existing contract.

When migrating a schema to a new model, you can keep the old component as an alias:

```yaml
components:
  schemas:
    ProductResponse:
      $ref: '#/components/schemas/Product'
    Product:
      type: object
      required: [id, name]
      properties:
        id:
          type: string
          format: uuid
        name:
          type: string
```

Legacy operations or external documents continue referencing `ProductResponse`; new operations can reference `Product`. Verify that OpenAPI tools used by your system handle schema `$ref` aliases properly.

### Do Not Rename Components Solely to Mirror Internal Refactoring

For instance, renaming `ProductResponse` to `CatalogItemView` may be a purely internal Java rename. If the payload has not changed, the schema name does not need to change. Conversely, if the public model truly takes on different semantics, create a new component and transition systematically rather than silently renaming the old identifier.

## 8. Where Else Is operationId Referenced?

`operationId` is not only used for generating client function names. OpenAPI Link Objects can reference operations by `operationId`, and tools may use it to link workflows or generate documentation.

Link Object example:

```yaml
paths:
  /api/orders:
    post:
      operationId: orders_create
      responses:
        '201':
          description: Order created
          links:
            GetCreatedOrder:
              operationId: orders_getById
              parameters:
                orderId: '$response.body#/id'
  /api/orders/{orderId}:
    get:
      operationId: orders_getById
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Order details
```

If `orders_getById` changes, Link Objects pointing to the old operationId become invalid. Therefore, when changing an operationId, find and update any related links, callbacks, reference documentation, and client generator configurations.

## 9. Declaring Stable Names with Annotations in Springdoc

A controller can assign public names for operations, path parameters, responses, and schemas:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @Operation(
        operationId = "products_getById",
        summary = "Get product by ID"
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Product found",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            ref = "#/components/responses/ProductNotFound"
        )
    })
    @GetMapping("/{productId}")
    ProductResponse getById(
        @Parameter(description = "Product UUID")
        @PathVariable("productId") UUID id
    ) {
        return productService.getById(id);
    }
}

@Schema(name = "Product", description = "Public product information")
public record ProductResponse(
    UUID id,
    @JsonProperty("product_code") String productCode,
    String name
) {}
```

Key identifiers are declared explicitly:

- `operationId = "products_getById"` keeps the operation identifier when the Java method is renamed.
- `@GetMapping("/{productId}")` and `@PathVariable("productId")` keep the public path name.
- `@Schema(name = "Product")` keeps the schema component name.
- `@JsonProperty("product_code")` keeps the property name in JSON.
- `@ApiResponse(ref = ...)` uses a stably named response component.

Annotations only describe or map the contract. Referenced response components must actually exist in the final OpenAPI document; they can be defined via `@ApiResponse` at an appropriate configuration point or through customizers. Always verify `$ref`s after springdoc assembles the document.

## 10. Using OpenApiCustomizer to Enforce Naming Rules Centrally

In large systems, `OpenApiCustomizer` can standardize metadata after springdoc builds the OpenAPI model. This is useful when older controller annotations cannot be updated immediately or when a uniform convention must be applied across an endpoint group.

Example setting operationId for an operation by path and HTTP method:

```java
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiNamingConfiguration {

    @Bean
    OpenApiCustomizer stableProductOperationId() {
        return openApi -> {
            var pathItem = openApi.getPaths().get("/api/products/{productId}");
            if (pathItem != null && pathItem.getGet() != null) {
                pathItem.getGet().setOperationId("products_getById");
            }
        };
    }
}
```

This is a customizer example for the corresponding OpenAPI document. When using multiple `GroupedOpenApi` instances, register the customizer on the right group or use the version-appropriate global mechanism to apply across all groups. Paths in the customizer must match paths included in OpenAPI, including context paths or prefixes if published.

Do not generate operationIds by concatenating Java method names in a customizer if the goal is stability across refactorings. Use an explicit mapping table from path/method to public ID or set `@Operation(operationId = ...)` directly on controllers.

### Customizing Schema Component Names

Component names should be placed on DTOs with `@Schema(name = "...")` whenever possible. If you must modify the model after OpenAPI generation, a customizer can update `components.schemas`, provided all corresponding `$ref`s are updated as well. Renaming a key in `components.schemas` without updating references makes the document invalid.

Logic for renaming a component in an OpenAPI model must proceed synchronously:

1. Create or move the schema to the new name.
2. Update all `$ref`s across request bodies, responses, nested properties, and other components.
3. Keep an old component alias if compatibility is required.
4. Verify no references remain to the removed key.

For structures with many nested schemas, do not write a customizer that rewrites `$ref` strings via naive text replacement. Traverse the typed OpenAPI model or use a document processing pass with reference validation.

## 11. Distinguishing Internal Renames from Contract Changes

Not every Java code change is a breaking change. The table below helps categorize them:

| Change | How to Keep the Contract Stable? | Impact If Uncontrolled |
|---|---|---|
| Rename controller method | Keep `@Operation(operationId = ...)` | SDK may rename generated functions |
| Change package or DTO name | Keep `@Schema(name = ...)` | Component schema may be renamed |
| Rename Java field | Keep `@JsonProperty` | JSON property and schema may change |
| Rename parameter variable | Specify `@PathVariable("...")`, `@RequestParam(name = "...")` | Parameter name may change depending on build/introspection metadata |
| Rename path placeholder | Keep URL and public parameter names | Clients must update URL templates/parameters |
| Change `operationId` | Preserve ID or update all consumers | SDKs, links, and referencing tools may break |
| Change schema component key | Preserve name with `@Schema(name)` or `$ref` alias | Older documentation references fail to resolve |
| Change JSON field name | Keep wire format name or publish transitional field | Clients cannot read/write old property |
| Change data type or format | Keep old representation or release a new version | Clients fail deserialization or misprocess values |

Some changes may appear additive yet still require real-world evaluation. For example, adding an optional response property is usually compatible with clients ignoring unknown fields, yet can break clients configured with strict deserialization. Adding a required request property can break existing clients not yet sending that field. Compatibility should be evaluated via OpenAPI diffs, runtime behavior, and client policies.

## 12. Transition Strategies When a JSON Property Must Be Renamed

Renaming a public property is a contract change. If you need to transition from `productCode` to `product_code`, plan request and response directions separately.

### Request: Accept the Old Name During Transition

Jackson's `@JsonAlias` allows deserializing multiple input names while serializing one canonical name:

```java
public record UpdateProductRequest(
    @JsonProperty("product_code")
    @JsonAlias("productCode")
    String productCode
) {}
```

The server accepts both `product_code` and `productCode`, while outputting the canonical `product_code`. `@JsonAlias` does not create two properties in JSON responses and does not necessarily make springdoc publish the old alias as a separate property. If clients need to know the old alias remains supported, state so explicitly in the description or migration documentation.

### Response: Maintain the Old Field During Transition

`@JsonAlias` does not emit two names in a response. If legacy clients still need to read `productCode`, you can temporarily return both the old and new fields, marking the old field deprecated in OpenAPI:

```java
@Schema(name = "ProductResponse")
public record ProductResponse(
    @Schema(description = "Product code using the canonical name")
    @JsonProperty("product_code") String productCode,

    @Deprecated
    @Schema(deprecated = true, description = "Use product_code; will be deprecated per migration schedule")
    @JsonProperty("productCode") String legacyProductCode
) {}
```

In practice, ensure both values stay identical and communicate the deprecation timeline. After the transition period, the old field can be removed in a new API version or per the system's breaking-change policy.

Do not add two fields with the same Java name or use ambiguous Jackson mix-ins to create two wire names. Use a transitional response DTO with explicit mappings.

## 13. Keeping Operations and Components Stable in Multi-Group APIs

Springdoc can produce multiple documents via `GroupedOpenApi`, such as `public`, `admin`, or `internal`. Each group is a separate OpenAPI document with its own `paths` and `components`.

Things to note:

- OperationIds must be unique within each document; ideally use a system-wide unique naming convention to avoid collisions if documents are merged.
- Components are only valid within the document containing them. An internal `$ref` in the `admin` group does not automatically resolve to a component in the `public` group.
- Customizers registered only for one group may not affect other groups.
- When adding endpoints to a group or moving endpoints between groups, inspect generated references and schemas in the target document.

Example group-level customizer registration (builder API depends on springdoc version):

```java
@Bean
GroupedOpenApi publicApi(OpenApiCustomizer publicNamingCustomizer) {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/**")
        .addOpenApiCustomizer(publicNamingCustomizer)
        .build();
}
```

If the same customizer must apply across all groups, consider `GlobalOpenApiCustomizer` for your springdoc version. Avoid registering both local and global customizers if they modify the same operation without clear rules.

## 14. Verifying operationId, Schema Names, and $refs After Refactoring

After the application starts, download `/v3/api-docs` or the corresponding group document endpoint. Check public identifiers:

1. `paths` and HTTP methods have not changed unintentionally.
2. Every operation has an explicit, unique `operationId`.
3. `components.schemas` has stable keys without unexpected suffixes.
4. Property names match actual JSON, including naming strategies and `@JsonProperty`.
5. `components.parameters`, `components.responses`, and `components.requestBodies` keep stable names if reused.
6. Every `$ref` resolves within the same document or to valid external documents.
7. Link Objects and other configurations reference the latest operationIds.
8. Swagger UI displays the right operation, schema, and response names.

You can check operationIds by iterating path items in the OpenAPI JSON. In CI, save a snapshot or generate the baseline document and diff against the previous version. Any diff showing changed operationIds or component keys should be reviewed just like a schema change.

Example expected check structure:

```yaml
paths:
  /api/products/{productId}:
    get:
      operationId: products_getById
      parameters:
        - name: productId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Product found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
components:
  schemas:
    Product:
      type: object
      properties:
        id:
          type: string
          format: uuid
        product_code:
          type: string
```

## 15. Testing Changes with OpenAPI Diff and Client Generation

To tell whether a refactoring alters the contract, compare the OpenAPI document before and after the change. Pay attention to:

- Added/removed operations or changed paths/methods.
- Changed or duplicated operationIds.
- Renamed or removed schema components.
- Broken `$ref`s.
- Renamed properties, changed types, or changed required/enum constraints.
- Changed response statuses, media types, or schemas.
- Changed security requirements or parameters.

A CI pipeline can:

1. Start the application or generate the OpenAPI document from the build.
2. Export `/v3/api-docs` as a JSON/YAML artifact.
3. Compare against the main branch or latest release document using an OpenAPI diff tool.
4. Classify breaking changes and additive changes per project policy.
5. Run a trial client SDK generation to catch method/model renames caused by operationIds or schema keys.
6. Require review whenever public identifiers or wire formats change.

Client generation is a helpful check, though it does not replace contract tests. A changed operationId can alter the SDK even when HTTP requests still work; conversely, successful SDK generation does not prove the runtime server returns the documented schema.

## 16. Common Errors and Resolutions

| Symptom | Cause | Resolution |
|---|---|---|
| Renaming Java method changes SDK function name | OperationId was inferred instead of explicitly declared | Set `@Operation(operationId = ...)` explicitly |
| Renaming DTO changes `$ref` | Component name is derived from class name | Use a stable `@Schema(name = "...")` |
| Component name gets a suffix | Multiple classes share the same name in one document | Assign unique schema names based on API concepts |
| Renaming field changes JSON key | No fixed `@JsonProperty` | Keep wire name with `@JsonProperty` and verify payload |
| Path parameter renamed after refactoring | Mapping/annotation relied on variable name | Declare path placeholder and `@PathVariable("...")` explicitly |
| `$ref` fails after renaming component | Renamed key only without updating all references | Update all refs or maintain an alias for the old name |
| Response link cannot open operation | Link Object still uses old operationId | Find and update all operationId references |
| Public group is right yet admin group is wrong | Customizer applied only to one document | Register customizer on the right group or globally |
| OpenAPI schema is right yet runtime JSON is wrong | Documentation annotations do not alter Jackson serialization | Check ObjectMapper and actual HTTP responses |
| JSON is right yet schema is wrong | Model converter or customizer does not reflect metadata | Inspect `/v3/api-docs` and springdoc configuration |

## 17. Workflow for Refactoring Without Unintended Contract Changes

When renaming classes, methods, or properties in a Spring Boot project, follow this sequence:

1. Capture the current OpenAPI JSON/YAML as a baseline for comparison.
2. Record public identifiers: paths, HTTP methods, operationIds, parameter names, schema components, and `$ref`s.
3. Rename Java code or reorganize packages.
4. Keep operationIds with `@Operation(operationId = ...)`.
5. Keep schema components with `@Schema(name = ...)`.
6. Keep JSON properties with `@JsonProperty` and HTTP parameter names with explicit `@PathVariable`, `@RequestParam`, and `@RequestHeader` names.
7. Keep or create aliases for component `$ref`s if document consumers depend on old names.
8. Check Link Objects and operationId references.
9. Diff OpenAPI before/after, run trial client generation, and execute contract tests.
10. Only publish breaking changes once a migration/versioning plan is in place and consumers are notified.

The goal of preserving identifiers is not to freeze source code. Java code can be refactored frequently as long as the public names clients depend on stay controlled. Explicit naming in annotations, DTOs with stable schemas, and OpenAPI diff checks make refactoring safer without unexpectedly altering SDKs or integration documentation.

## 18. References

- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object): `operationId` and operation metadata.
- [OpenAPI Specification – Components Object](https://spec.openapis.org/oas/latest.html#components-object): schemas, parameters, responses, and reusable components.
- [OpenAPI Specification – Reference Object](https://spec.openapis.org/oas/latest.html#reference-object): `$ref` syntax and semantics.
- [OpenAPI Specification – Link Object](https://spec.openapis.org/oas/latest.html#link-object): linking operations via operationId or operationRef.
- [Swagger Core Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): `@Operation`, `@Schema`, `@Parameter`, and response annotations.
- [Jackson Annotations](https://github.com/FasterXML/jackson-annotations): `@JsonProperty` and `@JsonAlias` for JSON property names.
- [Springdoc OpenAPI](https://springdoc.org/): configuring and customizing OpenAPI from Spring Boot controllers.
