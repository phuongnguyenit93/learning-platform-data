# Describing Structures Independently of Persistence Entity Classes

An OpenAPI specification describes the contract clients consume over HTTP. This contract should reflect the API's request and response data, whereas JPA entities reflect how the application stores and links data in the database. Springdoc-openapi can infer schemas from controller Java types; therefore, if controllers directly accept and return entities, storage structures easily become unintended API structures. Using dedicated DTOs for requests and responses keeps schemas independent, controls exposed data, and lets database structures change without forcing clients to change alongside them.

## 1. Persistence Entities and API Schemas Solve Two Different Problems

Entities are designed to satisfy persistence requirements: primary keys, relationships, managed state, optimistic locking, audit fields, and ORM rules. API DTOs are designed to represent data clients need to send or receive. Both models may share some fields, yet that does not mean they should share the same class.

| Aspect | Persistence entity | DTO/API schema |
|---|---|---|
| Goal | Store and manage data state | Publish an HTTP contract for clients |
| Structure | Driven by tables, relationships, and ORM | Driven by use cases and integration needs |
| Data fields | May include internal keys, audit, version, lazy relations | Includes only fields permitted to be sent or published |
| Lifecycle | Can change during migrations or database tuning | Evolves according to API compatibility policy |
| Validation | Persistence constraints and domain rules | Input validation and contract constraints |
| Representation | May use database-friendly types | Can rename, flatten, aggregate, or convert types |

For example, a `products` table may contain `costPrice`, `supplierId`, `internalNote`, `createdBy`, `updatedAt`, and `version`. Clients of a catalog API only need `id`, `name`, `sellingPrice`, and `category`. Returning the entity directly can expose internal fields, or JPA relationships can complicate JSON unexpectedly.

The design principle is: controllers accept and return data types representing the API contract; services/repositories work with domain models or entities; a mapping layer converts between the two models.

## 2. Risks of Using Entities Directly in Controllers

Consider a simple entity:

```java
@Entity
@Table(name = "products")
public class ProductEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    private BigDecimal sellingPrice;
    private BigDecimal costPrice;
    private String internalNote;

    @ManyToOne(fetch = FetchType.LAZY)
    private CategoryEntity category;

    @OneToMany(mappedBy = "product", fetch = FetchType.LAZY)
    private List<ProductImageEntity> images;

    @Version
    private long version;

    // getters and setters
}
```

If a controller returns `ProductEntity` directly, springdoc can use that class structure to generate the schema. This leads to several issues:

- `costPrice` or `internalNote` may appear in documentation and responses even though clients are not allowed to see them.
- `category` and `images` may pull in many related schemas, including fields outside the endpoint's contract.
- Bidirectional relationships such as `ProductEntity` and `ProductImageEntity.product` can cause circular references or serialization errors if unhandled.
- Lazy relationships may trigger unexpected queries or fail when the persistence session has closed.
- Renaming columns, storage types, or entity relationships can alter the OpenAPI schema unintentionally.
- Entities may hold ORM-managed fields that clients should never submit for updates.

Hiding individual fields with annotations can address certain cases, yet the entity remains shared across multiple use cases. When API and persistence requirements differ, dedicated DTOs establish a clearer, easier-to-control boundary.

## 3. Separating Request DTOs and Response DTOs

A use case typically needs at least two models: data clients send in and data the server returns. Example of creating a product:

```java
public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    @Schema(description = "Product name", example = "Ballpoint pen")
    String name,

    @NotNull
    @DecimalMin("0.0")
    @Schema(description = "Selling price", example = "12000")
    BigDecimal sellingPrice,

    @NotNull
    Long categoryId
) {}
```

The response can publish a different structure:

```java
public record ProductResponse(
    @Schema(description = "Product ID", example = "101")
    Long id,

    String name,

    BigDecimal sellingPrice,

    CategorySummary category
) {}

public record CategorySummary(
    Long id,
    String name
) {}
```

The request accepts only `categoryId`, while the response returns `category` as a summary object. Clients do not need to send the product `id`, JPA `version`, or the entire category entity. `costPrice` and `internalNote` appear in neither DTO.

Other use cases can have their own DTOs:

| Use case | Example DTO | Main data |
|---|---|---|
| Create product | `CreateProductRequest` | Name, selling price, category ID |
| Update product | `UpdateProductRequest` | Editable fields; may differ from creation request |
| Return details | `ProductResponse` | ID, name, selling price, category summary |
| Return list | `ProductListItem` | Minimal fields for list screens |
| Search | `ProductSearchRequest` or query parameters | Keywords, filters, and pagination |

There is no need to create new DTOs merely because endpoint names differ if the contract is genuinely identical. However, when write permissions, returned data, or lifecycles of two use cases differ, separate DTOs express the contract more accurately.

## 4. Controllers Using DTOs to Generate OpenAPI Schemas

When controller signatures use DTOs, springdoc can infer request body and response schemas from those types:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    ProductResponse create(
        @Valid @RequestBody CreateProductRequest request
    ) {
        return productService.create(request);
    }

    @GetMapping("/{id}")
    ProductResponse getById(@PathVariable Long id) {
        return productService.getById(id);
    }
}
```

Springdoc reads `CreateProductRequest` to document the request body and `ProductResponse` to document the response. The schema is shaped by the contract the controller publishes, not by the `products` table.

An OpenAPI excerpt might look like this:

```yaml
paths:
  /api/products:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
      responses:
        '201':
          description: Product created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductResponse'
components:
  schemas:
    CreateProductRequest:
      type: object
      required:
        - name
        - sellingPrice
        - categoryId
      properties:
        name:
          type: string
          maxLength: 120
          example: Ballpoint pen
        sellingPrice:
          type: number
          example: 12000
        categoryId:
          type: integer
          format: int64
    ProductResponse:
      type: object
      properties:
        id:
          type: integer
          format: int64
        name:
          type: string
        sellingPrice:
          type: number
        category:
          $ref: '#/components/schemas/CategorySummary'
```

This is an illustrative structure. Actual schemas depend on the springdoc version, Jackson configuration, data types, and validation annotations. Check `/v3/api-docs` or `/v3/api-docs.yaml` to verify the generated content.

## 5. Converting Between Entities and DTOs in Services or Mappers

Controllers should not traverse persistence relationships themselves or hold heavy conversion logic. Mapping can live in services or dedicated mappers.

Example manual mapping:

```java
@Service
class ProductService {

    private final ProductRepository productRepository;
    private final CategoryRepository categoryRepository;

    ProductService(
        ProductRepository productRepository,
        CategoryRepository categoryRepository
    ) {
        this.productRepository = productRepository;
        this.categoryRepository = categoryRepository;
    }

    ProductResponse create(CreateProductRequest request) {
        CategoryEntity category = categoryRepository.findById(request.categoryId())
            .orElseThrow(() -> new CategoryNotFoundException(request.categoryId()));

        ProductEntity entity = new ProductEntity();
        entity.setName(request.name());
        entity.setSellingPrice(request.sellingPrice());
        entity.setCategory(category);

        ProductEntity saved = productRepository.save(entity);
        return toResponse(saved);
    }

    ProductResponse getById(Long id) {
        ProductEntity entity = productRepository.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id));
        return toResponse(entity);
    }

    private ProductResponse toResponse(ProductEntity entity) {
        CategoryEntity category = entity.getCategory();
        CategorySummary categorySummary = category == null
            ? null
            : new CategorySummary(category.getId(), category.getName());

        return new ProductResponse(
            entity.getId(),
            entity.getName(),
            entity.getSellingPrice(),
            categorySummary
        );
    }
}
```

Explicit mapping controls which fields are copied, which fields are computed, and which relationships are summarized. In this example, `costPrice`, `internalNote`, `images`, and `version` are kept out of the response.

When there are many DTOs, MapStruct can generate mapping code at compile time:

```java
@Mapper(componentModel = "spring")
public interface ProductMapper {

    @Mapping(target = "id", ignore = true)
    @Mapping(target = "category", ignore = true)
    @Mapping(target = "images", ignore = true)
    @Mapping(target = "version", ignore = true)
    ProductEntity toEntity(CreateProductRequest request);

    @Mapping(target = "category", source = "category")
    ProductResponse toResponse(ProductEntity entity);

    CategorySummary toSummary(CategoryEntity entity);
}
```

This is a directional example; real mappers must configure target types, relationships, and ignored fields to fit your project's entities. For relationships like `categoryId`, you normally look up the category entity from a repository or use a mapping method supported by `@Context`/a service. Do not let a mapper instantiate related entities solely from IDs if checking existence and access permissions is a business rule.

## 6. Structuring Mapping to Avoid Unintended Entity Updates

Do not bind requests directly onto entities and save the entire object. That can allow clients to set fields the endpoint never intended to make editable, such as `id`, `version`, `createdBy`, `costPrice`, or other relationships.

Instead, assign only fields permitted for update:

```java
@Transactional
ProductResponse update(Long id, UpdateProductRequest request) {
    ProductEntity entity = productRepository.findById(id)
        .orElseThrow(() -> new ProductNotFoundException(id));

    entity.setName(request.name());
    entity.setSellingPrice(request.sellingPrice());

    if (request.categoryId() != null) {
        CategoryEntity category = categoryRepository.findById(request.categoryId())
            .orElseThrow(() -> new CategoryNotFoundException(request.categoryId()));
        entity.setCategory(category);
    }

    return productMapper.toResponse(entity);
}
```

`UpdateProductRequest` should clearly define which fields are required, which are optional, and what `null` means. If the API uses PATCH, distinguish "property omitted" from "property sent as null"; a plain Java DTO may not preserve that distinction using nullable fields alone. Consider wrappers, JSON Merge Patch, or a dedicated update model when contracts need to separate the two states.

## 7. Using @Schema to Document the Contract Rather Than Entities

DTOs can carry Swagger annotations to enrich descriptions for clients:

```java
@Schema(name = "ProductResponse", description = "Product information published via API")
public record ProductResponse(
    @Schema(description = "Product ID", example = "101", accessMode = Schema.AccessMode.READ_ONLY)
    Long id,

    @Schema(description = "Display name", example = "Ballpoint pen")
    String name,

    @Schema(description = "Selling price in the store's currency", example = "12000")
    BigDecimal sellingPrice,

    @Schema(description = "Abbreviated category information")
    CategorySummary category
) {}
```

Annotations can document:

- `description`: business meaning of the schema or property.
- `example` / `examples`: sample values for clients.
- `format`: formats such as `uuid`, `date`, `date-time`.
- `allowableValues`: permitted values in an appropriate schema.
- `minimum`, `maximum`, `minLength`, `maxLength`: data constraints.
- `accessMode`: usage direction `READ_ONLY`, `WRITE_ONLY`, or `READ_WRITE`.
- `implementation`: specifies a class used to describe the schema when the declared type is not specific enough.

Placing descriptions on API DTOs keeps documentation semantically accurate even when entity field names or table structures change. There is no need to add OpenAPI annotations onto entities solely for controllers when entities are not public models.

## 8. When to Specify a Schema with @Schema(implementation = ...)

In most cases, a concrete DTO type in the controller signature suffices for springdoc to infer the schema. `@Schema(implementation = ...)` helps when the Java type at that location is a generic wrapper, an interface, an overly broad return type, or when a specific representative schema must be published.

Response example:

```java
@ApiResponse(
    responseCode = "200",
    description = "Product information",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ProductResponse.class)
    )
)
@GetMapping("/{id}")
ResponseEntity<?> getById(@PathVariable Long id) {
    return ResponseEntity.ok(productService.getById(id));
}
```

In the example, the annotation tells documentation to describe the response as `ProductResponse`. However, the `ResponseEntity<?>` signature still loses type information at the Java layer. Where possible, declare an explicit type:

```java
ResponseEntity<ProductResponse> getById(@PathVariable Long id) {
    return ResponseEntity.ok(productService.getById(id));
}
```

A schema override changes only OpenAPI documentation. It does not transform the returned object at runtime. If a method actually returns an entity while an annotation declares `ProductResponse`, the actual JSON will still carry the entity's structure and the contract will be wrong. The right approach is converting entities to DTOs before returning responses.

Similarly for request bodies, you can specify the schema in Swagger `@RequestBody` using `@Content(schema = @Schema(implementation = ...))`. This adjusts documentation only; the controller still needs a corresponding parameter and binding mechanism.

## 9. Nested Schemas, Aggregation, and Flattening Data

API schemas do not have to mirror entity relationships. You can trim or aggregate data to suit clients.

For instance, an entity has `ProductEntity -> CategoryEntity`, yet the response only needs partial category information:

```java
public record ProductDetailResponse(
    Long id,
    String name,
    BigDecimal sellingPrice,
    CategorySummary category,
    List<ProductImageResponse> images
) {}

public record ProductImageResponse(
    Long id,
    String url,
    String altText
) {}
```

The `ProductDetailResponse` schema describes nested objects. Clients do not need to know how many other JPA relationships category has or which table stores images.

When list screens need flat data, you can use a separate DTO:

```java
public record ProductListItem(
    Long id,
    String name,
    BigDecimal sellingPrice,
    String categoryName,
    String thumbnailUrl
) {}
```

A flat response saves clients from traversing multiple nested objects and lets the backend aggregate data from multiple tables or services. OpenAPI only documents the `ProductListItem` structure; it does not need to reflect underlying joins or queries.

## 10. Generic Wrappers and Independent API Schemas

Many APIs use a shared envelope:

```java
public record ApiEnvelope<T>(
    boolean success,
    T data,
    String message
) {}
```

A controller can declare a concrete type:

```java
@GetMapping("/{id}")
ApiEnvelope<ProductResponse> getById(@PathVariable Long id) {
    return new ApiEnvelope<>(true, productService.getById(id), null);
}
```

Concrete generic types give springdoc the chance to resolve `T` into `ProductResponse` when building the schema. If the signature uses the raw type `ApiEnvelope` or `ApiEnvelope<?>`, the `data` schema can become generic and lose structure.

Do not switch to raw types merely to shorten controllers. If an endpoint has a distinct response, declare concrete generics or a dedicated envelope DTO. When the framework cannot infer it, use `@ApiResponse` with `@Schema(implementation = ...)` to state the intended schema clearly and inspect the output JSON.

## 11. Keeping APIs Stable When Entities or Databases Change

One major advantage of dedicated DTOs is that databases can change without requiring corresponding HTTP contract changes.

| Persistence change | How the DTO/API can stay unchanged |
|---|---|
| Rename column `selling_price` to `price_amount` | Mapper continues populating `sellingPrice` |
| Change price from `DECIMAL` to integer minor units | Mapper converts back to `BigDecimal` or the published representation |
| Split category table into multiple tables | Service aggregates into `CategorySummary` as before |
| Change images from one-to-many to join table | Mapper still returns `List<ProductImageResponse>` |
| Add `internalRiskScore` to entity | Omit the new field from DTOs if the API has no need to publish it |
| Add `@Version` or audit fields | Keep them in persistence; expose in the API only if explicitly required |

Conversely, changing a DTO can be an API change requiring compatibility review even when the database did not change. For example, renaming `sellingPrice` to `price` can break clients reading the old property. Therefore, manage database migrations and API versioning as two independent processes.

When an API structure must evolve, add optional fields, keep older fields during a transition period, or publish a new API version per system policy. Never let schemas change silently merely because entities were refactored.

## 12. Inspecting OpenAPI to Ensure Persistence Structures Are Not Leaked

After running the application, fetch `/v3/api-docs` or `/v3/api-docs.yaml`. Locate the endpoint's request and response schemas and compare them with your designed DTOs.

Check these points:

1. `requestBody.content` references the right request DTO, not a JPA entity.
2. Response schemas reference the right response DTOs.
3. No internal persistence fields like `costPrice`, `internalNote`, `version`, or `createdBy` appear unless published by the contract.
4. Entity relationships are intentionally represented as nested DTOs, summaries, or flat fields.
5. Required fields, enums, formats, examples, and validation bounds reflect the contract accurately.
6. Error responses and status codes are documented per endpoint behavior.
7. Schemas in `components.schemas` do not accidentally depend on entity classes.

In Swagger UI, inspect the Schemas section and open operations to examine requests/responses. Swagger UI only displays documentation; send real requests to confirm runtime JSON matches the schema.

## 13. Testing Contracts and Runtime Payloads

You can use `MockMvc` to confirm response JSON contains only expected public fields:

```java
@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    ProductService productService;

    @Test
    void returnsPublicProductSchema() throws Exception {
        given(productService.getById(101L)).willReturn(
            new ProductResponse(
                101L,
                "Ballpoint pen",
                new BigDecimal("12000"),
                new CategorySummary(5L, "Stationery")
            )
        );

        mockMvc.perform(get("/api/products/101"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.name").value("Ballpoint pen"))
            .andExpect(jsonPath("$.category.name").value("Stationery"))
            .andExpect(jsonPath("$.costPrice").doesNotExist())
            .andExpect(jsonPath("$.internalNote").doesNotExist());
    }
}
```

The mock annotation name in the example may vary by Spring Boot and test framework version; `@MockBean` can be used in versions where still supported, or configure mocks per project standards. The goal of the test is verifying the actual HTTP payload, not just the DTO class.

You can add OpenAPI documentation checks by calling `/v3/api-docs` in an integration test:

```java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.components.schemas.ProductResponse.properties.sellingPrice"
    ).exists())
    .andExpect(jsonPath(
        "$.components.schemas.ProductResponse.properties.costPrice"
    ).doesNotExist());
```

If springdoc uses a different component name due to configuration or naming rules, adjust the JSONPath to match the actual document. For thorough coverage, verify schema, response JSON, request validation, and entity-DTO mapping.

## 14. Common Pitfalls When Using Entities as API Schemas

| Symptom | Cause | Resolution |
|---|---|---|
| OpenAPI shows internal fields | Controller directly returns entity or shared DTO contains non-public fields | Create response DTOs containing only fields meant to be published |
| Schema changes after changing JPA relationships | Entity used as response type | Use nested/summary DTOs independent of ORM relationships |
| JSON loops infinitely or nests too deeply | Bidirectional entity relationships serialized directly | Switch to finite DTO structures and explicit mapping |
| Swagger UI shows unnecessary tables/relationships | Schema inferred from entity graph | Design DTOs around use cases |
| Clients can send `id`, `version`, or server-only fields | Request binds directly onto entity | Use a request DTO and assign only permitted fields |
| Document schema differs from runtime JSON | Overrode with `@Schema(implementation = ...)` while still returning entity | Return the DTO actually matching the schema |
| Generic DTO loses `data` type | Used raw type or wildcard | Declare concrete generics or a concrete response DTO |
| Database change breaks clients | Persistence entity treated as API contract | Manage DTOs and API versioning independently of migrations |

## 15. Workflow for Designing Persistence-Independent Schemas

When building a new endpoint, you can follow this sequence:

1. Identify what data clients are allowed to send and what data the server is allowed to return.
2. Design request DTOs and response DTOs around use cases without copying the full entity.
3. Define nested DTOs, summaries, or flat fields tailored to client ergonomics.
4. Apply validation on request DTOs and `@Schema` for descriptions, examples, formats, and bounds.
5. Write explicit mappings between DTOs and entities; check relationships, update permissions, and defaults.
6. Declare concrete DTO types in controller signatures so springdoc infers schemas.
7. Use `@Schema(implementation = ...)` only when adjusting documentation and ensure runtime objects match that structure.
8. Inspect OpenAPI JSON/YAML, Swagger UI, and HTTP payloads.
9. Diff schemas across releases to spot contract changes independently of database migrations.

The OpenAPI schema is the data interface clients depend on. The JPA entity is the storage model the backend can adjust to meet technical needs. Separating the two models with DTOs and explicit mapping lets springdoc publish the true contract, avoids leaking internal details, and keeps clients stable when persistence is refactored.

## 16. References

- [Springdoc OpenAPI](https://springdoc.org/): schema inference from Spring Boot controllers and document customization.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): schema models and data properties in API contracts.
- [Spring Framework – Web MVC Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html): declaring handlers, request bodies, and responses.
- [Spring Data JPA – Entity Persistence](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html): entity and persistence modeling.
- [MapStruct Reference Guide](https://mapstruct.org/documentation/stable/reference/html/): generating mappers between Java types at compile time.
