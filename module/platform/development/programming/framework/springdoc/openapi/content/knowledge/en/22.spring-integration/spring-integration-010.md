# Interface Annotations and Inherited Controllers

## 1. Why Place the API Contract on an Interface?

In a Spring Boot application, a controller often both receives HTTP requests and calls services to execute business logic. As the number of endpoints grows, teams may want to separate the HTTP contract description from the implementation so multiple controllers, adapters, or API versions can share a common convention.

A Java interface can describe method signatures and endpoint-related annotations. A controller implementing the interface supplies the actual processing logic. Spring MVC can detect mappings on interface methods in supported configurations; Springdoc can also read OpenAPI annotations placed on interfaces to generate operations, parameters, responses, and metadata.

A common pattern:

- **API interface** describes paths, HTTP methods, operation summaries, parameters, request bodies, and responses.
- **Controller implementation** provides code calling services and returning results.
- **DTOs** describe request/response data structures using Java types and schema annotations.
- **Springdoc** combines handler mappings with OpenAPI metadata to generate JSON/YAML documentation.

This organization makes API contracts easier to reuse and leaves controllers with fewer descriptive annotations. However, you must understand precisely how Java, Spring Framework, and Springdoc resolve annotations on interfaces, superclasses, and overridden methods.

## 2. Three Mechanisms to Distinguish

When placing annotations on interfaces or superclasses, three distinct mechanisms are involved:

1. **Java annotation inheritance**: the Java language rules for annotations marked with `@Inherited`.
2. **Spring annotation lookup**: Spring Framework has mechanisms for finding merged annotations across classes, interfaces, methods, and overridden methods.
3. **Springdoc metadata resolution**: Springdoc inspects handler methods and Swagger annotations to build the OpenAPI model.

Do not collapse these three mechanisms into a single rule. An annotation might be recognized by Spring MVC to register a route, while the corresponding OpenAPI annotation may not necessarily be interpreted identically by Springdoc across every version.

For example, Java's `@Inherited` applies only to class-level annotations and superclass chains. It does not make annotations automatically inherit from interfaces, nor does it apply to method or parameter annotations. Spring Framework can find annotations on interfaces through dedicated merged-annotation APIs; that is framework behavior, not Java's `@Inherited` rule.

Therefore, after placing annotations on interfaces or base controllers, inspect both runtime mappings and the generated OpenAPI document.

## 3. Annotations Commonly Placed on an API Interface

The following annotations are commonly useful when defining a contract:

| Annotation | Purpose |
|---|---|
| @RequestMapping, @GetMapping, @PostMapping | Declare URLs and HTTP methods |
| @Operation | Summary, description, operationId, and operation metadata |
| @ApiResponses, @ApiResponse | Describe status codes and responses |
| @Parameter | Describe path/query/header/cookie parameters |
| @Parameters | Group multiple parameter annotations |
| @RequestBody | Describe the OpenAPI request body |
| @Tag | Group operations in documentation |
| @SecurityRequirement | Attach security requirements to an operation |
| @Hidden | Hide endpoints or elements from documentation within supported scopes |
| @Schema | Describe DTOs, properties, enums, and validation metadata |

Distinguish Spring MVC annotations from Swagger annotations:

- `org.springframework.web.bind.annotation.RequestBody` marks the parameter receiving the HTTP body.
- `io.swagger.v3.oas.annotations.parameters.RequestBody` adds OpenAPI documentation for the request body.

Both annotations share the same simple name but serve different roles. Both can be used on the same parameter with proper imports.

## 4. Defining an API Interface with Mappings and OpenAPI Metadata

Example interface describing an endpoint to fetch a product:

~~~java
@RequestMapping("/api/products")
public interface ProductApi {

    @Operation(
        operationId = "getProductById",
        summary = "Get product by ID",
        description = "Returns detailed information of a product."
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
            description = "Product not found",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = ApiError.class)
            )
        )
    })
    @GetMapping("/{id}")
    ProductResponse findById(
        @Parameter(
            description = "Product identifier",
            example = "42"
        )
        @PathVariable("id") Long id
    );
}
~~~

The interface holds mappings and metadata for OpenAPI. It does not need to know which specific service or repository will execute the query.

When using `@RequestMapping` at the interface level, method mappings underneath are combined with the base path per Spring MVC rules. Verify the final URL by calling the endpoint or inspecting handler mappings, especially when the controller implementation also declares another class-level mapping.

Avoid repeating the same base path on both the interface and the implementation. Declaring two mapping sources can lead to unexpected path concatenation or ambiguous mappings.

## 5. Controller Implementing the Interface

The controller implements the interface and supplies the processing logic:

~~~java
@RestController
public class ProductController implements ProductApi {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @Override
    public ProductResponse findById(Long id) {
        return productService.findById(id);
    }
}
~~~

In this pattern:

- Spring MVC registers endpoints from mappings detected on the contract/interface per Spring version capabilities.
- The controller implementation supplies the method body.
- Springdoc reads mappings and OpenAPI metadata to create operations.
- The DTO `ProductResponse` is used as the response type and schema.

There is no need to copy `@GetMapping` and `@Operation` onto the implementation if the interface is already the contract source and annotation resolution works properly in your project's version. If annotations exist in both places, clarify which is the primary source and verify the final result.

## 6. Should Mappings Be Placed on the Interface or Implementation?

Mappings can be placed on either the interface or the controller implementation. What matters is choosing a consistent convention.

| Placement | When suitable | What to verify |
|---|---|---|
| Mapping on interface | Want contracts independent of implementations and reusable | Spring MVC and Springdoc must recognize interface annotations |
| Mapping on implementation | Controller manages its own routes without sharing contracts | OpenAPI metadata may live alongside implementation code |
| Mapping on superclass | Multiple controllers share handler methods or base paths | Verify inherited methods and generic types |
| Mapping on both interface and implementation | Use only with clear intent | Avoid duplicate declarations or incompatible mappings |

A practical rule is placing mappings and OpenAPI descriptions on the interface while the controller implementation contains only logic. If the project follows another convention, keep that convention consistent and add tests verifying mappings.

## 7. Annotations on Interface Methods and the @Inherited Rule

A common misconception is that annotations on an interface are automatically inherited because the controller implements the interface. That is incorrect under Java's `@Inherited` language rule.

`@Inherited` affects only annotations placed on a class when the annotation type itself carries `@Inherited`. It does not apply to:

- Annotations on an interface implemented by a class.
- Annotations on methods.
- Annotations on parameters.
- Annotations on fields.

Example:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface ApiFamily {
    String value();
}
~~~

If `@ApiFamily` is placed on a superclass, a subclass can see the annotation via `@Inherited`. However, if `@ApiFamily` is placed on an interface, an implementing class does not receive that annotation through `@Inherited` alone.

For Swagger annotations like `@Operation`, `@Parameter`, or `@ApiResponse`, do not rely on Java `@Inherited`. Rely on Springdoc/Spring annotation lookup capabilities and verify against the actual generated document.

## 8. How Does Spring MVC Find Mappings on Interfaces?

Spring Framework supports declaring request mappings on controller interfaces in supported models. Handler mapping inspects controller classes and methods to locate corresponding mappings, including annotations discoverable through the interface hierarchy.

However, several points should be kept consistent:

- Place mappings on interface methods if the interface is the API contract.
- Place `@RequestMapping` base paths in one clear location.
- Do not define different mappings on the interface and implementation for the same method.
- Avoid reusing a single interface for multiple controllers with incompatible base paths or behaviors.
- Verify actual URLs when methods are inherited or overridden.

When using proxies or special AOP configurations, annotation lookup and method signatures can be affected by how the framework resolves target methods. Consistent annotations and Spring MVC-layer tests help catch issues early.

## 9. Controllers Inheriting Methods from an Abstract Base Class

Besides interfaces, a controller can inherit handler methods from a superclass:

~~~java
public abstract class BaseReadController<T, ID> {

    protected abstract T loadById(ID id);

    @GetMapping("/{id}")
    public ResponseEntity<T> getById(@PathVariable ID id) {
        return ResponseEntity.ok(loadById(id));
    }
}
~~~

Concrete controller:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController
        extends BaseReadController<ProductResponse, Long> {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @Override
    protected ProductResponse loadById(Long id) {
        return productService.findById(id);
    }
}
~~~

Spring MVC can detect handler methods inherited from a superclass. The final path is `/api/products/{id}`. Method `getById` is defined in the base class, while concrete data is supplied by `loadById` in the subclass.

For OpenAPI, the inherited method can be recognized by Springdoc as an operation of the concrete controller. However, the generic response schema `T` may require close inspection if type resolution cannot infer `ProductResponse` in the active configuration or version.

## 10. Placing OpenAPI Annotations on a Superclass

`@Operation` and response metadata can be placed directly on base class methods:

~~~java
public abstract class BaseReadController<T, ID> {

    @Operation(
        summary = "Get resource by ID",
        description = "Reads a single resource by identifier."
    )
    @ApiResponse(
        responseCode = "200",
        description = "Resource found"
    )
    @GetMapping("/{id}")
    public ResponseEntity<T> getById(
        @PathVariable ID id
    ) {
        return ResponseEntity.ok(loadById(id));
    }

    protected abstract T loadById(ID id);
}
~~~

Subclasses can share the operation description. However, a generic description may be too abstract for concrete resources. If each controller needs different summaries, responses, or error semantics, override metadata at an appropriate layer or use separate interface contracts.

Do not assume superclass method annotations are automatically inherited by Java rules. Springdoc can locate metadata from the actual method referenced by `HandlerMethod`, yet when a subclass overrides a method, annotation lookup on overridden methods must be verified in the framework version in use.

## 11. Method Overriding and Annotation Conflicts

When a subclass overrides a handler method, annotations on the superclass method are not automatically copied to the overriding method by Java reflection.

Example:

~~~java
public abstract class BaseController {

    @Operation(summary = "Common operation")
    @GetMapping("/status")
    public abstract StatusResponse status();
}
~~~

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController extends BaseController {

    @Override
    public StatusResponse status() {
        return productService.status();
    }
}
~~~

In this case, the overridden method has no direct annotations. Spring has mechanisms to resolve merged annotations and mapping metadata through the method hierarchy, though resolution behavior for each annotation type differs from ordinary Java inheritance rules.

If operation metadata must remain stable, place annotations on interface methods or declare them explicitly on implementation methods. Avoid declaring two different summaries or responses on superclass and subclass without a tested precedence rule.

When a subclass needs operation content tailored to itself, declare metadata explicitly on the overriding method so maintainers clearly see the intent.

## 12. Generic Base Controllers and Response Schemas

Generic base controllers help reuse handler logic:

~~~java
public abstract class BaseCrudController<T, ID> {

    @GetMapping("/{id}")
    public T getById(@PathVariable ID id) {
        return findOne(id);
    }

    protected abstract T findOne(ID id);
}
~~~

Concrete controller:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController
        extends BaseCrudController<ProductResponse, Long> {

    @Override
    protected ProductResponse findOne(Long id) {
        return productService.findById(id);
    }
}
~~~

Springdoc may need to resolve generic types from the subclass to generate response schemas. If the OpenAPI document shows a generic schema, empty object, or incorrect type, check type resolution and declare responses explicitly.

Example using `@ApiResponse`:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Product",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ProductResponse.class)
    )
)
~~~

If the same base controller is reused across multiple domain types, do not hard-code `ProductResponse` in the base class. Place response metadata on the interface or concrete method of each controller so schemas match each endpoint.

## 13. Annotations on Interface Parameters and Request Bodies

An API interface can describe parameters and request bodies alongside mappings:

~~~java
@RequestMapping("/api/products")
public interface ProductApi {

    @Operation(summary = "Create product")
    @ApiResponse(
        responseCode = "201",
        description = "Created successfully",
        content = @Content(
            schema = @Schema(implementation = ProductResponse.class)
        )
    )
    @PostMapping
    ProductResponse create(
        @io.swagger.v3.oas.annotations.parameters.RequestBody(
            description = "Product details to create",
            required = true
        )
        @org.springframework.web.bind.annotation.RequestBody
        @Valid
        ProductCreateRequest request
    );
}
~~~

The example uses fully qualified names to distinguish the two annotations both named `RequestBody`. In real codebases, imports and short names can be used if there is no conflict.

Parameter annotations can also be placed on interface methods:

~~~java
@GetMapping("/search")
List<ProductResponse> search(
    @Parameter(description = "Product name or partial name")
    @RequestParam("q") String query
);
~~~

Inspect the OpenAPI document to ensure parameters are described with accurate location, name, requiredness, schema, and example. If the controller implementation declares parameters differing from the interface signature, mappings and parameter metadata can fall out of sync.

## 14. Tags and Security Metadata on Interfaces

You can use `@Tag` to group APIs and `@SecurityRequirement` to describe security:

~~~java
@Tag(
    name = "Products",
    description = "Operations for managing products"
)
@RequestMapping("/api/products")
public interface ProductApi {

    @Operation(
        summary = "Get product",
        security = @SecurityRequirement(name = "bearerAuth")
    )
    @GetMapping("/{id}")
    ProductResponse findById(@PathVariable("id") Long id);
}
~~~

If multiple controllers share an interface, a tag on the interface can help group related operations. However, class-level annotations on an interface are not automatically carried over to implementing classes by Java `@Inherited`. Springdoc may read interface annotations depending on scanning mechanisms and versions; verify that tags appear in the OpenAPI document.

An easier-to-control approach is placing `@Tag` on the concrete controller when the tag belongs specifically to that controller, while placing `@Operation` and parameter metadata on contract methods. If the tag belongs to the shared contract, place it on the interface and add verification tests.

Security requirements must also be verified at the right level. Do not assume a security annotation on an interface automatically enforces security across all operations if the document has global security settings or overriding customizers.

## 15. Interfaces Shared Across Multiple API Versions

An interface can define a contract shared across multiple controllers or API versions, though differences in paths and responses must be considered.

Example:

~~~java
public interface ProductReadApi {

    @GetMapping("/{id}")
    @Operation(summary = "Get product by ID")
    ProductResponse findById(@PathVariable("id") Long id);
}
~~~

Different version controllers:

~~~java
@RestController
@RequestMapping("/api/v1/products")
public class ProductV1Controller implements ProductReadApi {
    // implementation
}
~~~

~~~java
@RestController
@RequestMapping("/api/v2/products")
public class ProductV2Controller implements ProductReadApi {
    // implementation may return a different DTO if the contract is designed separately
}
~~~

If both controllers implement the same interface, Spring MVC can register two distinct paths for the same signature. Springdoc needs to create two corresponding operations. However, a shared summary or response schema may become unsuitable if version 2 changes semantics.

When API versions differ in requests/responses, use separate interfaces or contracts per version instead of forcing everything into one generic interface. Share only what is genuinely identical.

## 16. Multiple Interfaces and Ambiguous Mappings

A controller can implement multiple API interfaces:

~~~java
@RestController
public class ProductController
        implements ProductReadApi, ProductWriteApi {
    // implementations
}
~~~

This can be useful for separating read and write contracts. Ensure that:

- Paths and HTTP methods across interfaces do not conflict.
- `operationId` values are unique across the entire document.
- Tags and security requirements accurately reflect functional groups.
- Method signatures are compatible.
- No two interfaces define conflicting metadata for the same method.
- Spring MVC registers only one matching handler mapping per request.

If two interfaces both declare `GET /api/products/{id}` with different responses or summaries, the controller can produce ambiguous mappings or inconsistent documentation. Separate the endpoints or merge the contracts before implementation.

## 17. Creating Composed Annotations for Internal Conventions

Projects can create composed annotations to bundle repeated metadata. Example annotation for endpoints requiring bearer authentication:

~~~java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Operation(
    security = @SecurityRequirement(name = "bearerAuth")
)
public @interface AuthenticatedApiOperation {
}
~~~

Composed annotations can reduce repetition if Springdoc and Swagger Core support meta-annotation lookup for them. However, not every Swagger annotation is processed like a Spring composed annotation in every version.

Therefore, after creating a composed annotation:

1. Confirm the annotation has runtime retention.
2. Check the appropriate target: `TYPE`, `METHOD`, or `PARAMETER`.
3. Verify whether Springdoc reads that meta-annotation.
4. Fetch `/v3/api-docs` to verify the generated security or metadata.
5. If unsupported, use direct annotations or a customizer.

Do not create composed annotations solely to hide important rules that readers need to see directly on the API contract.

## 18. Checking That Annotations Were Recognized by Springdoc

After starting the application, inspect the OpenAPI JSON:

~~~http
GET /v3/api-docs
~~~

Locate the corresponding operation and verify:

- Path and HTTP method are correct.
- Operation `summary`, `description`, and `operationId` are accurate.
- Parameters have accurate names, locations, and schemas.
- Request body has accurate requiredness, media type, and schema.
- Responses have appropriate status codes, content, and schemas.
- Tags are attached to the right operations.
- Security requirements apply to the right scope.
- Operations are not duplicated when both interface and implementation have declarations.
- Generic responses resolve to concrete DTOs.

If using document groups, check each group's OpenAPI endpoint. An operation can be filtered out of a group by path/package filters even when its runtime mapping works.

Do not rely solely on Swagger UI for verification. JSON is more direct evidence of the OpenAPI model generated by Springdoc.

## 19. Testing Mappings and OpenAPI with MockMvc

Test the runtime endpoint:

~~~java
mockMvc.perform(get("/api/products/{id}", 42))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42));
~~~

Verify OpenAPI metadata:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.paths['/api/products/{id}'].get").exists())
    .andExpect(jsonPath(
        "$.paths['/api/products/{id}'].get.summary"
    ).value("Get product by ID"));
~~~

You can add response schema checks:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(jsonPath(
        "$.paths['/api/products/{id}'].get.responses['200']"
    ).exists());
~~~

These tests check two different aspects:

- The request test confirms Spring MVC actually registers and handles the endpoint.
- The OpenAPI test confirms Springdoc documents the endpoint and metadata accurately.

One test passing does not substitute for the other. An endpoint can work while missing from documentation; documentation can also contain operations that runtime no longer serves.

## 20. Common Mistakes with Interfaces and Inherited Controllers

| Symptom | Cause to check |
|---|---|
| Interface mapping does not work | Spring version or configuration does not detect interface mappings |
| Endpoint runs but lacks @Operation metadata | Springdoc has not resolved annotations from the interface method |
| Tag does not appear | Placed @Tag on interface assuming Java @Inherited applies |
| Superclass annotation lost after override | Method annotations are not automatically inherited by Java |
| Path has duplicated prefix | Base @RequestMapping declared on both interface and implementation |
| Operation appears twice | Mappings/metadata declared twice or multiple handlers exist |
| Generic response becomes empty schema | Type erasure or generic resolution lacks sufficient information |
| Parameter has wrong name | Interface and implementation have differing signatures/annotations |
| Security is wrong | SecurityRequirement missing, overridden, or placed at the wrong level |
| Subclass summary unexpected | Conflicting metadata between superclass/interface and overriding method |
| Duplicate operationId | Multiple interfaces or controllers reuse the same operationId |
| Group missing endpoint | Group path/package filter excludes the actual mapping |

When investigating, check handler mappings first, then compare method signatures and annotation hierarchies, and finally inspect OpenAPI JSON. This separates Spring MVC routing bugs from Springdoc metadata bugs.

## 21. Principles for Organizing Interfaces and Inherited Controllers

When using interfaces or base controllers to share API contracts:

1. Place mappings in one consistent source: either the interface or the implementation.
2. Use interfaces for contracts when multiple implementations need to share the same HTTP signature.
3. Use abstract base controllers only when handler logic genuinely needs to be shared.
4. Place `@Operation`, `@ApiResponses`, and `@Parameter` where Springdoc can resolve and verify them.
5. Do not rely on Java `@Inherited` for interface, method, or parameter annotations.
6. Do not declare conflicting annotations on interfaces, superclasses, and overriding methods.
7. With generic base controllers, verify response schemas resolve to concrete types.
8. Place `@Tag` on concrete controllers when clear documentation grouping must be guaranteed.
9. Keep `operationId`s unique and mappings unambiguous.
10. Verify both HTTP runtime and `/v3/api-docs` with tests.

Interfaces help separate HTTP contracts from controller logic; superclasses help reuse handler behavior; Springdoc turns the metadata it recognizes into an OpenAPI document. When you properly distinguish Java annotation rules from Spring's merged-annotation lookup and test actual routes and schemas, teams can reuse contracts without creating duplicate mappings or inaccurate documentation.

