# Designing DTOs, Input Validation, and Mapping to Storage Models

In a Spring WebFlux application using Spring Data Relational R2DBC, data flows from an HTTP request through multiple layers before being written to the database. DTOs define the API contract; validation verifies that the request is valid; the application service enforces business rules; mappers convert data into domain or entity models; and R2DBC repositories handle reactive persistence.

Separating these responsibilities prevents the API from depending directly on the database schema. When adding internal columns, renaming properties, or changing storage strategies, the HTTP contract can stay intact. Conversely, when the API changes, entities and schemas do not have to change mechanically alongside it.

A typical processing flow:

~~~mermaid
flowchart TD
    A[HTTP request JSON] --> B[WebFlux deserialization]
    B --> C[Request DTO]
    C --> D[Bean Validation]
    D --> E[Application service]
    E --> F[Domain/business validation]
    F --> G[Mapper]
    G --> H[R2DBC persistence entity]
    H --> I[Reactive repository]
    I --> J[(Database)]
    J --> K[Saved entity]
    K --> L[Response mapper]
    L --> M[Response DTO]
    M --> N[HTTP response JSON]
~~~

This lesson covers designing request/response DTOs, using Bean Validation in WebFlux, performing asynchronous business validation, converting DTOs into R2DBC entities, handling create/update/PATCH, standardizing API errors, and testing the entire reactive flow.

## 1. Distinguishing DTOs, Domain Models, and Persistence Entities

Three types of objects may contain similar data while serving different purposes.

| Object Type | Responsibility | Example Fields |
| --- | --- | --- |
| Request DTO | Describes data the client is allowed to send. | name, price, categoryId |
| Domain model/command | Represents business intent and rules. | CreateProductCommand, Product |
| Persistence entity | Represents data mapped by Spring Data to a table. | id, name, price, categoryId, createdAt |
| Response DTO | Describes data the API is allowed to return. | id, name, price, createdAt |

Do not use a single entity as both the request body and response body for every endpoint. Doing so can let clients submit fields that only the server should manage, or leak internal data when serializing responses.

For example, the `products` table has the following columns:

~~~sql
CREATE TABLE products (
    id UUID PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price > 0),
    category_id UUID NOT NULL,
    internal_cost NUMERIC(12, 2),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE
);
~~~

The client only needs to send the name, selling price, and category. The client must not decide `id`, `internal_cost`, `created_at`, or `updated_at`.

Request DTO:

~~~java
public record CreateProductRequest(
    String name,
    BigDecimal price,
    UUID categoryId
) {}
~~~

The persistence entity can contain more fields:

~~~java
@Table("products")
public record ProductEntity(
    @Id UUID id,
    String name,
    BigDecimal price,
    @Column("category_id") UUID categoryId,
    @Column("internal_cost") BigDecimal internalCost,
    @Column("created_at") Instant createdAt,
    @Column("updated_at") Instant updatedAt
) {}
~~~

The Response DTO returns only public fields:

~~~java
public record ProductResponse(
    UUID id,
    String name,
    BigDecimal price,
    UUID categoryId,
    Instant createdAt
) {}
~~~

This separation prevents mass assignment: clients cannot directly overwrite fields like `internalCost` or audit timestamps simply by adding them to the JSON.

## 2. Designing Request DTOs by Use Case

Design DTOs around API operations rather than trying to reuse one large DTO for every situation.

For example:

- `CreateProductRequest`: minimal data to create a product.
- `ReplaceProductRequest`: all fields the client is allowed to replace in a PUT.
- `PatchProductRequest`: fields that can be partially updated.
- `ProductResponse`: data returned to the caller.
- `ProductSummaryResponse`: small projection for lists.

Create and update often have different requirements. When creating, `name` and `price` may be required. When partially updating, fields may be omitted. Sharing one DTO can make validation ambiguous.

DTOs should represent the HTTP contract and should not carry persistence annotations like `@Table`, `@Id`, or `@Column`. Similarly, R2DBC entities should not take on the responsibilities of a request model.

### Using Appropriate Data Types

| Data | Typical Java Type | Notes |
| --- | --- | --- |
| Money/price | `BigDecimal` | Avoid `double`/`float` for monetary amounts requiring precision. |
| UUID ID | `UUID` | Ensure matching JSON and database formats. |
| Absolute date/time | `Instant` or `OffsetDateTime` | Clearly specify timezone and storage format. |
| Calendar date | `LocalDate` | Do not attach a timezone if the domain concept is date-only. |
| Quantity | `Integer`/`Long` | Use a type with sufficient range and check bounds. |
| Status | `Enum` or string code | Do not let clients arbitrarily set internal states. |
| Child list | `List<DTO>` | Use nested validation. |

Do not use `String` for every field just because JSON transmits data as text. DTO types should express intent and allow Jackson/validation to catch malformed data early.

## 3. Bean Validation for Request DTOs

Spring WebFlux supports Jakarta Bean Validation when a validation provider is present and the request body is marked for validation. With Spring Boot, the usual dependency is the validation starter.

Example Gradle dependency:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
~~~

Request DTOs can declare constraints directly:

~~~java
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
    @NotBlank(message = "Name is required")
    @Size(max = 160, message = "Name must not exceed 160 characters")
    String name,

    @NotNull(message = "Price is required")
    @DecimalMin(value = "0.01", message = "Price must be greater than zero")
    BigDecimal price,

    @NotNull(message = "Category is required")
    UUID categoryId
) {}
~~~

These constraints validate data locally without accessing the database:

- `@NotNull`: value must not be null.
- `@NotBlank`: string must not be null, not empty, and contain at least one non-whitespace character.
- `@NotEmpty`: string, collection, or array must not be null/empty depending on supported type.
- `@Size`: restricts length or element count.
- `@Positive`/`@PositiveOrZero`: checks numeric sign.
- `@DecimalMin`/`@DecimalMax`: restricts decimal bounds.
- `@Email`: validates email address shape per the validator.
- `@Pattern`: validates strings against a regular expression.
- `@Past`/`@Future`: checks temporal relationships.

Validation does not replace database constraints. A request that is valid at the HTTP layer can still conflict with data written by another request.

### Combining Multiple Constraints

A single field can have multiple constraints:

~~~java
public record RegisterCustomerRequest(
    @NotBlank
    @Email
    @Size(max = 254)
    String email,

    @NotBlank
    @Size(min = 8, max = 100)
    String password
) {}
~~~

Each constraint verifies one condition. Avoid writing a huge regex for everything when standard annotations express the rules clearly.

For money, use `BigDecimal` and restrict both value and precision/scale if required by the API contract. `@Digits` can restrict integer and fractional digits:

~~~java
@Digits(integer = 10, fraction = 2)
@DecimalMin("0.01")
BigDecimal price
~~~

The database should still enforce `NUMERIC`/`DECIMAL` with matching precision and scale.

## 4. Validation for Nested Objects and Collections

If a request contains nested objects, place `@Valid` to trigger recursive validation.

~~~java
public record CreateOrderRequest(
    @NotNull
    UUID customerId,

    @NotEmpty
    @Size(max = 100)
    List<@NotNull @Valid CreateOrderLineRequest> items
) {}

public record CreateOrderLineRequest(
    @NotNull
    UUID productId,

    @NotNull
    @Positive
    Integer quantity
) {}
~~~

Here:

- `@NotEmpty` requires the list to contain at least one element.
- `@Size(max = 100)` limits the number of line items in a single request.
- `@NotNull` on the element prevents the list from containing null entries.
- `@Valid` instructs the validator to inspect each `CreateOrderLineRequest`.
- `@Positive` ensures `quantity` is greater than 0.

If you only place `@Valid` on a collection without `@NotEmpty`, an empty list may still pass validation. If you only place `@NotNull` on the collection, an empty list is accepted. Choose constraints matching the business contract.

### Object-Level Validation

Some rules depend on multiple fields, such as a start date needing to precede an end date. You can create a class-level constraint:

~~~java
@ValidDateRange
public record SearchBookingRequest(
    @NotNull LocalDate startDate,
    @NotNull LocalDate endDate
) {}
~~~

Validator:

~~~java
public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, SearchBookingRequest> {

    @Override
    public boolean isValid(
            SearchBookingRequest value,
            ConstraintValidatorContext context) {

        if (value == null
                || value.startDate() == null
                || value.endDate() == null) {
            return true;
        }

        return !value.endDate().isBefore(value.startDate());
    }
}
~~~

Individual `@NotNull` constraints are responsible for catching missing fields. The class-level validator returns `true` when either field is missing to avoid duplicate errors or null dereferences. If you want to attach the error to a specific field, use `ConstraintValidatorContext` to add a property node.

Custom Bean Validation validators should perform synchronous, fast checks with no side effects. Do not call a reactive database by blocking inside a `ConstraintValidator`.

## 5. Enabling Validation in a WebFlux Controller

For annotated controllers, mark the request body with `@Valid`:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService products;

    public ProductController(ProductService products) {
        this.products = products;
    }

    @PostMapping
    public Mono<ResponseEntity<ProductResponse>> create(
            @Valid @RequestBody CreateProductRequest request) {

        return products.create(request)
            .map(response -> ResponseEntity
                .created(URI.create("/api/products/" + response.id()))
                .body(response));
    }
}
~~~

WebFlux decodes the JSON into the DTO and runs validation before passing the request into the controller. If the request body is invalid, the request-handling pipeline terminates with a binding/validation error.

There is no need to invoke the validator manually and subscribe in the controller for standard request bodies. Using Spring's built-in validation mechanism ensures errors are handled within the request lifecycle.

### Validating Query Parameters and Path Variables

Simple parameters like `page`, `size`, or `quantity` also need validation:

~~~java
@GetMapping
public Flux<ProductResponse> list(
        @RequestParam(defaultValue = "0") @Min(0) int page,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {

    return products.list(page, size);
}
~~~

How method validation is activated and which exception types are raised can vary across Spring Framework versions. With Spring Framework 6.1 and later, native MVC/WebFlux method validation has its own mechanisms and exceptions; applications using class-level `@Validated` AOP may follow a different path. Configure validation according to your Spring Boot version and standardize the corresponding validation exception types in exception advice.

Do not allow clients to request an unbounded page size. A maximum limit prevents a single request from producing an excessive amount of data.

## 6. Consistent Validation Error Handling

WebFlux may throw `WebExchangeBindException` when a request body fails binding/validation. Method validation errors may use different exceptions depending on the framework version and controller declaration style.

Standardize them into an error response DTO instead of returning raw exceptions:

~~~java
public record ApiValidationError(
    String code,
    String message,
    Map<String, String> fieldErrors
) {}
~~~

Example exception advice for request body errors:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiValidationError> handleBodyValidation(
            WebExchangeBindException exception) {

        Map<String, String> errors = exception.getFieldErrors().stream()
            .collect(Collectors.toMap(
                FieldError::getField,
                error -> Objects.requireNonNullElse(
                    error.getDefaultMessage(),
                    "Invalid value"
                ),
                (first, ignored) -> first
            ));

        ApiValidationError body = new ApiValidationError(
            "VALIDATION_FAILED",
            "Request contains invalid fields",
            errors
        );

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

The example illustrates a synchronous handler for validation exceptions. If the application standardizes all handlers on reactive return types, it can return `Mono<ResponseEntity<ApiValidationError>>`. Add handlers for the method validation exceptions used by your project's Spring version.

Example response:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request contains invalid fields",
  "fieldErrors": {
    "name": "Name is required",
    "price": "Price must be greater than zero"
  }
}
~~~

Do not return stack traces, SQL, internal table names, or connection details in the response. For clients, stable error codes and field paths are more useful than raw database or validator messages.

### Do Not Rely on Error Wording for Client Logic

Messages may change by locale or version. If the frontend needs stable logic, use error codes such as `VALIDATION_FAILED`, `PRODUCT_NOT_FOUND`, or `PRODUCT_CODE_CONFLICT`; messages are only for display.

## 7. Distinguishing Input Validation from Business Validation

Not every rule belongs in Bean Validation.

Checks can be divided into three layers:

| Layer | Type of Check | Examples |
| --- | --- | --- |
| Request validation | Checks data shape and bounds. | Name non-blank, positive price, non-empty items. |
| Domain/application validation | Checks business rules. | Product must belong to an active category; user is authorized to order. |
| Database constraints | Protects integrity at the storage level. | `UNIQUE code`, `FOREIGN KEY category_id`, `CHECK price > 0`. |

Bean Validation should not access the database to verify that a category exists or an email is unused. Standard validators are synchronous; querying the database from there often leads to blocking or hard-to-control asynchronous workarounds.

Instead, the service performs asynchronous checks using repositories:

~~~java
public Mono<Product> create(CreateProductCommand command) {
    return categories.findById(command.categoryId())
        .switchIfEmpty(Mono.error(
            new CategoryNotFoundException(command.categoryId())
        ))
        .flatMap(category -> {
            if (!category.active()) {
                return Mono.error(
                    new CategoryInactiveException(category.id())
                );
            }

            ProductEntity entity = mapper.toNewEntity(command);
            return products.save(entity);
        });
}
~~~

This is a reactive domain check: the repository returns a publisher, and the service composes it with `flatMap` and `switchIfEmpty`. No blocking is needed to fetch the category before saving.

### Pre-Write Checks Do Not Replace Constraints

Suppose a service checks that an email does not exist before inserting. Two concurrent requests could both pass the check and both insert. A unique constraint in the database is the final safeguard.

The proper flow is:

1. Input validation fails fast with clear errors.
2. Business validation produces appropriate messages.
3. Database constraints protect data under concurrency.
4. The service translates specific constraint failures into domain/API errors.

Do not omit unique constraints just because an `exists` query runs before `insert`.

## 8. Converting DTOs into Commands and Persistence Entities

Do not let the controller build entities directly or contain persistence logic. A mapper can convert DTOs into commands:

~~~java
public record CreateProductCommand(
    String name,
    BigDecimal price,
    UUID categoryId
) {}
~~~

Pure mapper:

~~~java
@Component
public class ProductRequestMapper {

    public CreateProductCommand toCommand(CreateProductRequest request) {
        return new CreateProductCommand(
            request.name().trim(),
            request.price(),
            request.categoryId()
        );
    }
}
~~~

Application service accepting the command:

~~~java
@Service
public class ProductService {

    private final ProductRepository products;
    private final CategoryRepository categories;
    private final ProductMapper mapper;
    private final Clock clock;

    public ProductService(
            ProductRepository products,
            CategoryRepository categories,
            ProductMapper mapper,
            Clock clock) {
        this.products = products;
        this.categories = categories;
        this.mapper = mapper;
        this.clock = clock;
    }

    public Mono<ProductResponse> create(CreateProductCommand command) {
        return categories.findById(command.categoryId())
            .switchIfEmpty(Mono.error(
                new CategoryNotFoundException(command.categoryId())
            ))
            .flatMap(category -> {
                if (!category.active()) {
                    return Mono.error(
                        new CategoryInactiveException(category.id())
                    );
                }

                ProductEntity entity = mapper.toNewEntity(
                    command,
                    clock.instant()
                );

                return products.save(entity)
                    .map(mapper::toResponse);
            });
    }
}
~~~

In this example, `ProductMapper` performs pure conversions between commands, entities, and responses. `Clock` is injected for deterministic timestamp testing instead of calling global time everywhere.

The controller only coordinates HTTP and converts the request DTO into a command:

~~~java
@PostMapping
public Mono<ResponseEntity<ProductResponse>> create(
        @Valid @RequestBody CreateProductRequest request) {

    CreateProductCommand command = requestMapper.toCommand(request);

    return productService.create(command)
        .map(response -> ResponseEntity
            .created(URI.create("/api/products/" + response.id()))
            .body(response));
}
~~~

Depending on the architecture, the controller may pass the DTO directly to the service and map inside the service. What matters is preventing persistence entities from unintentionally becoming the request/response contract.

## 9. R2DBC Entity Mapping

Spring Data Relational maps entities to tables using annotations such as `@Table`, `@Id`, and `@Column`.

~~~java
@Table("products")
public record ProductEntity(
    @Id UUID id,
    String name,
    BigDecimal price,
    @Column("category_id") UUID categoryId,
    @Column("created_at") Instant createdAt,
    @Column("updated_at") Instant updatedAt
) {}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ReactiveCrudRepository<ProductEntity, UUID> {
}
~~~

Mappers can be written manually:

~~~java
@Component
public class ProductMapper {

    public ProductEntity toNewEntity(
            CreateProductCommand command,
            Instant now) {

        return new ProductEntity(
            null,
            command.name(),
            command.price(),
            command.categoryId(),
            now,
            now
        );
    }

    public ProductResponse toResponse(ProductEntity entity) {
        return new ProductResponse(
            entity.id(),
            entity.name(),
            entity.price(),
            entity.categoryId(),
            entity.createdAt()
        );
    }
}
~~~

If IDs are database-generated, a new entity can leave `id` as `null` according to the configured ID strategy and database. Spring Data R2DBC can capture the generated ID and return the saved entity depending on column type, driver, and mapping configuration. Verify this with integration tests on the target database.

Do not return entities directly to the API. The response mapper is where public fields are selected, formats are adjusted, or internal columns are hidden.

### When to Use MapStruct?

MapStruct fits repetitive mapping across many DTOs, commands, and entities. It generates mapping code at compile time, helping catch certain type mismatches early.

For small mappings, explicit constructors or factory methods are often easier to read. Regardless of the tool used, business decisions such as default values, field ownership, and ID generation timing must be made explicit rather than letting a mapper blindly copy every property.

## 10. Using map and flatMap Properly in Reactive Mapping

In a reactive service:

- `map` is used when synchronously transforming an already emitted value.
- `flatMap` is used when the next step returns a `Mono`/`Flux`.
- `then` is used when only the completion of the previous publisher matters, ignoring its value.
- `switchIfEmpty` handles a publisher that emits no elements.
- `onErrorMap` transforms an error type while keeping the error signal.

Synchronous mapping example:

~~~java
return productRepository.findById(id)
    .map(mapper::toResponse);
~~~

Example requiring an asynchronous category check:

~~~java
return categoryRepository.findById(categoryId)
    .switchIfEmpty(Mono.error(
        new CategoryNotFoundException(categoryId)
    ))
    .flatMap(category ->
        productRepository.save(
            mapper.toEntity(command, category)
        )
    )
    .map(mapper::toResponse);
~~~

Do not use `map` when the lambda returns a `Mono`, or you will create `Mono<Mono<T>>`. Do not use `block` to obtain a reactive result before mapping.

### Do Not Subscribe Manually in Controller/Service

Do not write:

~~~java
public Mono<ProductResponse> create(CreateProductRequest request) {
    productRepository.save(mapper.toEntity(request)).subscribe();
    return Mono.just(new ProductResponse(...));
}
~~~

This detaches the write operation from the returned publisher. The caller could receive a response before the insert completes, insert errors will not propagate to the HTTP pipeline, and the transaction context will no longer be properly controlled.

Return the fully composed publisher instead:

~~~java
public Mono<ProductResponse> create(CreateProductCommand command) {
    return productRepository.save(mapper.toEntity(command))
        .map(mapper::toResponse);
}
~~~

## 11. Create, PUT, and PATCH Need Different DTOs

Create, replace, and partial update have different semantics.

### Create

Create DTOs typically require mandatory fields and do not accept server-generated IDs:

~~~java
public record CreateProductRequest(
    @NotBlank @Size(max = 160) String name,
    @NotNull @DecimalMin("0.01") BigDecimal price,
    @NotNull UUID categoryId
) {}
~~~

### PUT: Replacing Updatable Representation

PUT usually represents a replacement state for the resource per the API contract. Required fields need explicit validation:

~~~java
public record ReplaceProductRequest(
    @NotBlank @Size(max = 160) String name,
    @NotNull @DecimalMin("0.01") BigDecimal price,
    @NotNull UUID categoryId
) {}
~~~

The service should load the existing entity, verify permissions, and transition state according to domain rules. Do not treat the request as a complete entity and save it directly.

### PATCH: Partial Update

PATCH allows sending only a subset of fields. For example:

~~~java
public record PatchProductRequest(
    @Size(max = 160) String name,
    @DecimalMin("0.01") BigDecimal price
) {}
~~~

In this simple example, `null` can be treated by convention as "unchanged." However, clients then cannot use `null` to clear a nullable field. A Java record also cannot inherently distinguish an omitted field from a field explicitly sent as `null` after deserialization.

If the API needs three states — omitted field, explicit `null` to clear, value to update — use a presence-aware representation such as `JsonNullable` with the appropriate Jackson module or a custom deserializer/patch document. Do not guess semantics from `null`.

### Updating the Existing Entity

~~~java
public Mono<ProductResponse> patch(
        UUID id,
        PatchProductRequest request) {

    return products.findById(id)
        .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
        .flatMap(current -> {
            String name = request.name() == null
                ? current.name()
                : request.name().trim();

            BigDecimal price = request.price() == null
                ? current.price()
                : request.price();

            ProductEntity updated = new ProductEntity(
                current.id(),
                name,
                price,
                current.categoryId(),
                current.createdAt(),
                clock.instant()
            );

            return products.save(updated);
        })
        .map(mapper::toResponse);
}
~~~

This example treats `null` as unchanged and does not allow patching the category. If the category is also updatable, verify that the category exists and is active before saving. If fields can be cleared with `null`, use a presence-aware DTO to distinguish clearly.

Do not allow PATCH requests to change `id`, `createdAt`, `internalCost`, or owner/tenant simply by sending out-of-contract properties.

## 12. Checking Permissions and Tenant-Scoped Data

A request can be type-valid yet unauthorized to access a resource. For example, a client sends an existing `categoryId` that belongs to a different tenant.

Never trust `tenantId`, `ownerId`, or `userId` sent in the request when those values must come from the authenticated identity. Read the identity from the security context or server-verified metadata, then apply it to queries/services.

Example:

~~~java
public Mono<ProductResponse> create(
        CreateProductCommand command,
        UUID authenticatedTenantId) {

    return categories.findByIdAndTenantId(
            command.categoryId(),
            authenticatedTenantId
        )
        .switchIfEmpty(Mono.error(
            new CategoryNotFoundException(command.categoryId())
        ))
        .flatMap(category ->
            products.save(mapper.toNewEntity(
                command,
                authenticatedTenantId
            ))
        )
        .map(mapper::toResponse);
}
~~~

Tenant-scoped queries prevent reading another tenant's data. Database constraints can provide additional protection if the schema is designed to enforce tenant relationships.

Validation and authorization are two separate concerns: valid fields do not mean the user is permitted to perform the operation.

## 13. Translating Business and Constraint Errors into HTTP Responses

The application service should emit explicit domain exceptions instead of returning `null` or free-form error strings.

Examples:

- `ProductNotFoundException`: resource does not exist.
- `CategoryNotFoundException`: invalid reference.
- `CategoryInactiveException`: disallowed by business rules.
- `ProductCodeAlreadyExistsException`: unique code conflict.

Controller advice maps exceptions into statuses and error DTOs:

~~~java
@RestControllerAdvice
public class ProductApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ApiError> handleNotFound(
            ProductNotFoundException exception) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError(
                "PRODUCT_NOT_FOUND",
                "Product was not found"
            ));
    }

    @ExceptionHandler(ProductCodeAlreadyExistsException.class)
    public ResponseEntity<ApiError> handleConflict(
            ProductCodeAlreadyExistsException exception) {

        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError(
                "PRODUCT_CODE_CONFLICT",
                "Product code already exists"
            ));
    }
}
~~~

In WebFlux, exception handlers can return reactive types if needed; the examples use `ResponseEntity` directly for synchronous responses once an exception has been raised.

If the repository throws `DuplicateKeyException`, convert it to `ProductCodeAlreadyExistsException` only when the corresponding constraint is identified. Do not turn every `DataIntegrityViolationException` into 409 for the same reason, since `NOT NULL`, `CHECK`, or `FOREIGN KEY` violations have different semantics.

Never expose raw SQL errors, constraint messages, or stack traces outside the API.

## 14. Normalizing Data in the Right Layer

Certain normalizations can be performed in DTO mappers or domain factories:

- Trimming leading/trailing whitespace.
- Normalizing product codes according to conventions.
- Converting empty strings to `null` if allowed by the contract.
- Normalizing enum/string codes.
- Computing derived values that do not depend on the database.

Operations requiring database knowledge or mapping belong in persistence mappers/converters. Business rules should not be hidden inside DTO constructors.

Factory example:

~~~java
public record CreateProductCommand(
    String name,
    BigDecimal price,
    UUID categoryId
) {
    public static CreateProductCommand from(
            CreateProductRequest request) {

        return new CreateProductCommand(
            request.name().trim(),
            request.price(),
            request.categoryId()
        );
    }
}
~~~

Do not apply a single blanket trim or lowercase rule to every string. Display names, addresses, passwords, identifiers, and emails have different semantics. Normalization must be intentional and consistent with search/comparison behavior.

### Money and Rounding

Do not automatically round `BigDecimal` values in a mapper unless business rules define how. If the database has a scale of two decimal places, determine:

- Does the API accept more than two decimal places?
- Should it round `HALF_UP`, `HALF_EVEN`, or reject?
- Do stored and returned values have the same scale?
- Where is currency determined?

Place the rules in the domain/application layer and ensure matching database precision/scale.

## 15. Pagination and Sorting from Requests

If the API accepts `page`, `size`, or `sort`, never pass arbitrary client-supplied values straight into SQL.

Bound the page size:

~~~java
private Pageable toPageable(int page, int size) {
    if (page < 0) {
        throw new InvalidPageRequestException("Page must be non-negative");
    }

    if (size < 1 || size > 100) {
        throw new InvalidPageRequestException(
            "Page size must be between 1 and 100"
        );
    }

    return PageRequest.of(
        page,
        size,
        Sort.by(Sort.Direction.DESC, "createdAt")
    );
}
~~~

If clients can choose sort fields, use an allowlist of permitted properties. Never concatenate free-form column names into SQL. Bind parameters replace values, not identifiers or keywords.

With custom R2DBC SQL, use named bind parameters for values and whitelist column names/order directions before building the SQL structure.

## 16. Testing DTOs, Validation, and Mapping

Split testing by layer.

### DTO Validation Unit Tests

You can use Jakarta Bean Validation's `Validator` to verify constraints:

~~~java
@Test
void rejectsInvalidCreateProductRequest() {
    CreateProductRequest request = new CreateProductRequest(
        " ",
        BigDecimal.ZERO,
        null
    );

    Set<ConstraintViolation<CreateProductRequest>> violations =
        validator.validate(request);

    assertFalse(violations.isEmpty());
}
~~~

This test verifies DTO constraints without requiring a database.

### WebFlux Controller Tests

Use `WebTestClient` to send invalid requests:

~~~java
@Test
void returnsBadRequestForInvalidProduct() {
    webTestClient.post()
        .uri("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("""
            {
              "name": " ",
              "price": 0,
              "categoryId": null
            }
            """)
        .exchange()
        .expectStatus().isBadRequest()
        .expectBody()
        .jsonPath("$.code").isEqualTo("VALIDATION_FAILED");
}
~~~

Verify that the service is not invoked when request validation fails. The test context configuration should use real WebFlux and exception advice to validate the validation pipeline.

### Mapper Unit Tests

Verify DTO/command conversion to entities:

~~~java
@Test
void mapsCreateCommandToNewEntity() {
    Instant now = Instant.parse("2026-01-01T00:00:00Z");

    ProductEntity entity = mapper.toNewEntity(command, now);

    assertNull(entity.id());
    assertEquals(command.name(), entity.name());
    assertEquals(command.price(), entity.price());
    assertEquals(now, entity.createdAt());
}
~~~

Mapper tests help catch omitted or misassigned fields. If using MapStruct, verify generated mappings through behavioral tests.

### R2DBC Integration Tests

Use a real database or Testcontainers to verify:

- Entities are written to the right columns.
- Generated IDs are returned.
- Enums, UUIDs, `BigDecimal`, and timestamps map properly.
- Constraints are enforced by the database.
- Readback produces the expected response DTO.
- Duplicate errors are translated into appropriate domain/API errors.

Mock repositories cannot verify the actual schema, driver conversions, or constraints.

## 17. Common Mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Using entities as request bodies | API depends on schema and risks mass assignment. | Create dedicated request DTOs. |
| Clients can send `id`/`createdAt`/internal fields | DTO accepts too many properties or binds entities directly. | Declare only fields clients are allowed to send. |
| `@Valid` does not execute | Missing annotation on request body, validation provider, or config. | Add validation dependency and `@Valid`. |
| Nested DTOs are not validated | Missing `@Valid` on nested objects/collections. | Place `@Valid` and appropriate collection constraints. |
| Using Bean Validation to query the database | Synchronous validator gets blocked or breaks the reactive model. | Move existence/permission checks to the reactive service. |
| Exists check still leads to duplicates | Race condition between check and insert. | Keep unique constraints and handle specific duplicates. |
| PATCH cannot clear nullable fields | DTO does not distinguish omitted from explicit `null`. | Use a presence-aware patch representation. |
| Using `map` for a step returning `Mono` | Creates nested `Mono`. | Use `flatMap`. |
| Calling `subscribe`/`block` in controller/service | Detaches publisher from the request lifecycle. | Return and compose Publishers. |
| Response leaks internal columns | Serializing entities directly. | Use response DTOs and mappers. |
| Update overwrites server-managed fields | Copying the entire request onto an entity. | Load the existing entity and update allowlisted fields. |
| Validation failures return 500 | Exception advice does not handle WebFlux exceptions properly. | Standardize binding and method validation exceptions. |
| Data valid at API fails in database | Missing domain check or DB constraint/type mismatch with contract. | Align validation, mapping, and schema. |

## 18. Workflow for Designing a WebFlux Endpoint with R2DBC

When building an endpoint to create or update a resource, follow this sequence:

1. **Define the HTTP contract:** which fields does the request send, and which fields may the response return?
2. **Create dedicated DTOs:** do not reuse persistence entities for requests/responses.
3. **Choose data types:** `BigDecimal` for money, `UUID` for identifiers, date/time types matching semantics.
4. **Declare Bean Validation:** check null, blank, size, range, and nested objects.
5. **Enable validation in WebFlux:** use `@Valid` on request bodies and standardize binding errors.
6. **Build command/domain input:** normalize data according to business rules.
7. **Perform asynchronous checks:** use reactive repositories to verify resources, status, and permissions.
8. **Map to entity:** assign only server-allowed fields and generate intentional metadata.
9. **Save with R2DBC:** compose publishers via `map`/`flatMap`, never `subscribe`/`block`.
10. **Map result to response DTO:** return only public fields.
11. **Translate errors into API errors:** distinguish validation, not-found, conflict, and system errors.
12. **Test each layer:** validator, mapper, WebFlux endpoint, and database integration.

Clear DTO design, validation, and mapping help WebFlux maintain a reactive flow end-to-end from HTTP to R2DBC. Request DTOs protect the API contract; Bean Validation checks local data; the application service enforces asynchronous business rules; mappers convert data into persistence entities; and repositories handle storage. Separating these layers keeps field boundaries controlled, errors consistent, and schema changes minimally disruptive to the API.
