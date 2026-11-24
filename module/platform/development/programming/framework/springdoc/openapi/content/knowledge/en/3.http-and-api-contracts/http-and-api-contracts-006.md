# Data Type Contracts Differ from Business Rules

An OpenAPI schema describes the shape and checkable constraints on HTTP data: which fields are required, which data types are accepted, string lengths, numeric ranges, and allowed enum values. Those conditions form the data contract between client and server.

Business rules answer a different question: given the current state of the system, is this user allowed to perform that action? A request can have completely valid types, valid formats, and pass Bean Validation, yet still cannot be executed because the product is discontinued, inventory is insufficient, the account is locked, or the order status does not allow cancellation.

When building a Spring Boot API with springdoc-openapi, keep these two layers distinct:

- **Data type contract:** described using OpenAPI Schemas, DTOs, and deterministic input constraints.
- **Business rules:** enforced in the application/domain layer based on policies and actual state; outcomes are published via response statuses and error schemas.

You cannot replace business checks by adding minimum, enum, or required to a schema. Conversely, you should not push malformed JSON types or out-of-bounds strings deep into a domain service when they can be rejected right at the HTTP boundary.

The Java examples in this lesson use Java 17 and Spring Boot 3+ with Jakarta Validation. Legacy Spring Boot 2 applications use the javax.validation package and require compatible library versions; keep the namespace aligned with your project's platform.

## 1. Four Common Constraint Layers

An order-creation API is an intuitive example:

| Layer | Question | Example | Appropriate handling place |
|---|---|---|---|
| Syntax and data types | Can the body be parsed and are the types valid? | quantity is an integer, productId is a UUID | HTTP message conversion, DTO |
| Input constraints | Are values within declared bounds? | quantity greater than 0, non-blank name | Jakarta Bean Validation |
| Business rules | Is the action valid in the current context? | Product is on sale, customer is eligible to buy | Domain/application service |
| Data integrity | Does concurrent execution violate invariants? | Unique SKU within tenant, non-negative stock count | Database constraints and transactions |

These layers complement one another. A DTO-level constraint does not guarantee the database has no duplicate rows from two concurrent requests. Likewise, a database constraint does not replace a clear error response for the client.

For example, the following request can be valid in terms of types and constraints:

~~~json
{
  "productId": "cbd37c4a-6f6b-4ed9-bad2-77e8ec4d3f61",
  "quantity": 2,
  "deliveryMode": "STANDARD"
}
~~~

Yet the server may still reject it because the product does not exist, is no longer sold, or only has one unit left in stock. Those conditions cannot be decided from just the three fields of the request.

## 2. What Does a Data Contract Describe?

The OpenAPI Schema Object describes the structure of representations that the API receives or returns. Common keywords include:

| Keyword | Meaning | Example |
|---|---|---|
| type | JSON type | string, integer, number, boolean, object, array |
| required | List of required properties in an object | required: [productId, quantity] |
| format | Format hint for a type | uuid, date, date-time, email |
| enum | Set of accepted values | [STANDARD, EXPRESS] |
| minLength, maxLength | String length bounds | Name from 1 to 80 characters |
| minimum, maximum | Numeric bounds | minimum: 1 |
| pattern | Regular expression | Item code matching a fixed pattern |
| minItems, maxItems | Number of elements in an array | Maximum 50 items |
| items | Schema of each element | Array of UUIDs or objects |
| additionalProperties | Whether unlisted properties are allowed | Disallow unknown fields when needed |

These keywords are useful when rules can be determined from the representation itself. They do not query the database, do not know which tenant the current user belongs to, do not read order statuses, and do not lock inventory.

format also needs proper understanding: some tools treat format merely as a display annotation without strict format enforcement. When format matters, check validator configuration and still validate data on the server.

## 3. What Do Business Rules Depend On?

Business rules usually depend on at least one factor outside the current body:

- State of an aggregate or resource in the database.
- Identity, role, scope, or tenant of the caller.
- Current time, deadlines, or operating schedules.
- Inventory, limits, balances, or remaining quota.
- State of another resource.
- Transaction history or configured policies.
- Outcome of a concurrent operation from another request.

Examples:

| Rule | Why is it not just a schema constraint? |
|---|---|
| SKU must be unique within a tenant | Requires comparing against existing data and the caller's tenant |
| Only sell ACTIVE products | Depends on the product's current state |
| Cannot order quantity exceeding stock | Stock changes continuously and faces concurrent contention |
| Only the order owner may cancel | Depends on the principal and resource ownership |
| Cancel orders only before shipment | Depends on order status at processing time |
| Discount must not exceed campaign budget | Depends on policy and remaining budget |
| Transfer must not exceed available balance | Depends on balance, concurrent transactions, and accounting rules |

These conditions can be documented in OpenAPI descriptions, operation documentation, and error responses. However, documentation is not an enforcement mechanism; the server must validate them at the proper layer.

## 4. Distinguishing Single-Field Constraints, Cross-Field Constraints, and Domain Invariants

Not every rule involving multiple fields belongs in the domain model. Examine what data is needed to decide:

1. **Single-field constraint:** depends on only one value, e.g., quantity must be positive.
2. **Cross-field constraint within the same request:** depends solely on the payload, e.g., startDate must precede endDate.
3. **Domain invariant:** depends on system state or policy, e.g., delivery date must fall within the operating schedule of the chosen warehouse.

Cross-field constraints can be checked with class-level Bean Validation if they are determinable from the payload alone. For example, start date before end date:

~~~java
@ValidDateRange
public record CreateCampaignRequest(
    @NotNull LocalDate startDate,
    @NotNull LocalDate endDate
) {}
~~~

The @ValidDateRange validator can compare the two fields without querying the database. If the condition depends on store timezone, configured holidays, or other active campaigns, that is a policy to evaluate in the application/domain layer.

@ValidDateRange here is an illustrative name for a custom constraint; the project must declare the matching annotation and ConstraintValidator, or use an existing validator.

The boundary is not whether a rule touches multiple fields. The boundary is whether the rule can be decided from the request alone or requires authoritative system context.

## 5. Designing Request DTOs with Bean Validation

DTOs at the HTTP boundary should clearly express what data clients are permitted to send and what constraints can be checked independently:

~~~java
public record CreateOrderRequest(
    @NotNull
    UUID productId,

    @NotNull
    @Positive
    Integer quantity,

    @NotNull
    DeliveryMode deliveryMode,

    @Size(max = 200)
    String note
) {}
~~~

Enum:

~~~java
public enum DeliveryMode {
    STANDARD,
    EXPRESS
}
~~~

Controller triggering validation:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderApplicationService orderService;

    OrderController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse created = orderService.create(request);
        return ResponseEntity
            .created(URI.create("/api/orders/" + created.id()))
            .body(created);
    }
}
~~~

@NotNull, @Positive, and @Size check local input conditions. They do not verify whether productId exists or whether the user is allowed to purchase that product.

With @RequestBody, Spring MVC uses HttpMessageConverter to deserialize the body before calling the controller. Afterward, @Valid or @Validated triggers Bean Validation. Syntactically invalid JSON or values that cannot convert to Java types are typically rejected at the conversion step; parseable data violating constraints is rejected at the validation step.

## 6. Do Not Pull Database State into DTOs as a Pseudo-Constraint

A misleading design is creating a custom validator that queries a repository:

~~~java
// Not recommended for ordinary request DTOs
@ExistingActiveProduct
UUID productId;
~~~

This kind of validator can run, yet it couples the DTO to persistence, makes transactions hard to control, and is prone to stale checks if state changes between validation and write time.

For example: the validator confirms the product is ACTIVE at 10:00:00.001. An administrator pauses the product at 10:00:00.005. The order creation request continues at 10:00:00.010. The stale validation outcome no longer reflects the state when the business action runs.

Keep DTO validators for stable, local conditions decidable from the payload. Query data and enforce policies inside the service/domain transaction.

## 7. Enforcing Business Rules in the Application/Domain Layer

The application service orchestrates the use case; domain objects or policies hold business decisions. Example:

~~~java
@Service
class OrderApplicationService {

    private final ProductRepository products;
    private final InventoryService inventory;
    private final OrderRepository orders;

    @Transactional
    public OrderResponse create(CreateOrderRequest request) {
        Product product = products.findById(request.productId())
            .orElseThrow(ProductNotFoundException::new);

        product.ensurePurchasable(request.quantity());

        inventory.reserve(product.id(), request.quantity());

        Order order = Order.create(
            product.id(),
            request.quantity(),
            request.deliveryMode(),
            request.note()
        );

        return OrderResponse.from(orders.save(order));
    }
}
~~~

ensurePurchasable can check product status, sale start/end dates, or domain policies. inventory.reserve is responsible for reserving stock safely under concurrent requests.

Do not let controllers decide rules such as “if inventory exceeds quantity, create the order”. When rules are scattered in controllers, batch jobs and message consumers may apply inconsistent behavior. Keeping invariants in the domain/application service ensures every entry point uses the same policy.

## 8. Business Rules Must Be Safe Under Concurrency

A common bug is checking first and writing afterward:

~~~java
if (inventoryRepository.getAvailable(productId) >= quantity) {
    inventoryRepository.decrease(productId, quantity);
}
~~~

Two requests can simultaneously read available stock of 5, each ordering 4 units, and both proceed. Checking only in Java does not prevent race conditions.

With a relational database, you can use a conditional update statement to check and deduct stock in a single atomic operation:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :productId
  AND available >= :quantity;
~~~

After running it, check the number of updated rows:

- One row: reservation succeeded.
- Zero rows: the product does not exist or remaining stock is insufficient; determine the exact error according to policy and necessary queries.

Another option is optimistic locking with a version field or pessimistic locking depending on workload. Either way, transactions and the database must protect the final invariant; OpenAPI schemas cannot do this.

## 9. Unique SKU Example and Limits of Pre-Checks

Suppose SKU only needs to be unique per tenant. The DTO can validate the format:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Pattern(regexp = "^[A-Z0-9-]{3,32}$")
    String sku,

    @NotBlank
    @Size(max = 120)
    String name
) {}
~~~

SKU format is a request constraint. Uniqueness is a database-dependent invariant:

~~~java
if (productRepository.existsByTenantIdAndSku(tenantId, request.sku())) {
    throw new DuplicateSkuException(request.sku());
}
~~~

Pre-checking helps return a friendly error, but is insufficient to guarantee uniqueness because two transactions can both check before either writes data.

The database needs an appropriate unique constraint:

~~~sql
ALTER TABLE product
ADD CONSTRAINT uk_product_tenant_sku UNIQUE (tenant_id, sku);
~~~

When the constraint is violated, the application must translate the persistence error into a stable business/API error, such as SKU_ALREADY_EXISTS with HTTP 409. Never return SQL statements, table names, or stack traces to clients.

## 10. Documenting the Data Contract in OpenAPI

OpenAPI should accurately reflect the request DTO's constraints. Example:

~~~yaml
components:
  schemas:
    CreateOrderRequest:
      type: object
      required:
        - productId
        - quantity
        - deliveryMode
      properties:
        productId:
          type: string
          format: uuid
        quantity:
          type: integer
          minimum: 1
        deliveryMode:
          type: string
          enum:
            - STANDARD
            - EXPRESS
        note:
          type: string
          maxLength: 200
~~~

The schema tells clients to send a UUID, quantity as an integer of at least 1, and deliveryMode from the enum. The schema does not state whether the product is currently on sale or has enough stock.

With springdoc, Swagger annotations can supplement descriptions:

~~~java
@Schema(name = "CreateOrderRequest")
public record CreateOrderRequest(
    @Schema(
        description = "Identifier of the product to purchase.",
        example = "cbd37c4a-6f6b-4ed9-bad2-77e8ec4d3f61"
    )
    @NotNull
    UUID productId,

    @Schema(
        description = "Quantity must be a positive integer.",
        minimum = "1",
        example = "2"
    )
    @NotNull
    @Positive
    Integer quantity,

    @NotNull
    DeliveryMode deliveryMode,

    @Size(max = 200)
    String note
) {}
~~~

Springdoc can infer certain schema constraints from Bean Validation annotations. Exact results depend on version, annotation type, validation groups, and configuration. Inspect /v3/api-docs to confirm the generated schema; do not assume every custom validator is automatically converted into JSON Schema.

## 11. Documenting Business Rules with Descriptions and Error Responses

Dynamic rules still need to be published so clients know why a structurally valid request might be rejected:

~~~java
@Operation(
    summary = "Create an order",
    description = """
        Creates an order for a product currently eligible for sale.
        The request must provide quantity as a positive integer.
        The server checks product status and inventory at processing time.
        If the product is no longer on sale or stock is insufficient, the API returns a business error.
        """
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Order created"
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Request body has invalid types or violates input constraints"
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Product not found"
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Product is no longer on sale or stock is insufficient"
    )
})
~~~

description helps integrators understand the rules, while response statuses help clients handle outcomes. Do not set a fake maximum value on quantity just because current inventory happens to be 20; inventory can change right after the document is generated.

## 12. Choosing HTTP Status by Error Nature

The status code should reflect why the request could not be processed. A common policy:

| Status | Use when | Example |
|---|---|---|
| 400 Bad Request | Body has invalid syntax, wrong types, or violates request constraints | quantity is a string, missing required field |
| 401 Unauthorized | Missing or invalid credentials | Expired JWT |
| 403 Forbidden | Caller is not allowed to perform the action | Lacks permission to create orders in tenant |
| 404 Not Found | Required resource does not exist or is hidden per policy | productId not found |
| 409 Conflict | Cannot execute due to conflict with current state | Duplicate SKU, order already paid, stock changed |
| 412 Precondition Failed | HTTP precondition no longer holds | ETag/If-Match mismatch |
| 422 Unprocessable Content | Server understands content type and syntax but cannot process content instructions per API semantics | Syntactically valid payload violating processing rules for which the API designates 422 |

400 and 422 may be chosen differently across APIs for validation errors. What matters is picking a consistent policy, stating it clearly in OpenAPI, and not returning 500 for input errors or predictable business conflicts.

409 is especially fitting when a request conflicts with a resource's current state. If an API uses 422 for certain semantic errors, keep the distinction stable so clients do not have to guess.

## 13. Creating a Stable Error Contract

Do not let clients depend on exception messages or default error structures that vary by framework. You can use Problem Details and add stable error codes:

~~~java
public record ApiProblem(
    URI type,
    String title,
    int status,
    String detail,
    String code,
    List<FieldViolation> violations
) {}

public record FieldViolation(
    String field,
    String code,
    String message
) {}
~~~

Validation error example:

~~~json
{
  "type": "https://api.example.com/problems/request-validation",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "code": "REQUEST_VALIDATION_FAILED",
  "violations": [
    {
      "field": "quantity",
      "code": "POSITIVE",
      "message": "Quantity must be greater than zero."
    }
  ]
}
~~~

Business error example:

~~~json
{
  "type": "https://api.example.com/problems/insufficient-stock",
  "title": "Order cannot be created",
  "status": 409,
  "detail": "The requested quantity is no longer available.",
  "code": "INSUFFICIENT_STOCK",
  "violations": []
}
~~~

The error contract should separate field errors from use-case errors. violations suits field-level validation; a problem-level code lets clients identify business errors without parsing the detail string.

## 14. Mapping Validation Errors and Domain Errors in Spring Boot

Input errors and business errors can be handled in @RestControllerAdvice:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiProblem> handleInvalidBody(
            MethodArgumentNotValidException exception) {
        List<FieldViolation> violations =
            exception.getBindingResult().getFieldErrors().stream()
                .map(error -> new FieldViolation(
                    error.getField(),
                    toApiCode(error),
                    "The supplied value is invalid."
                ))
                .toList();

        ApiProblem problem = new ApiProblem(
            URI.create("https://api.example.com/problems/request-validation"),
            "Request validation failed",
            400,
            "One or more request fields are invalid.",
            "REQUEST_VALIDATION_FAILED",
            violations
        );
        return ResponseEntity.badRequest().body(problem);
    }

    @ExceptionHandler(InsufficientStockException.class)
    ResponseEntity<ApiProblem> handleInsufficientStock(
            InsufficientStockException exception) {
        ApiProblem problem = new ApiProblem(
            URI.create("https://api.example.com/problems/insufficient-stock"),
            "Order cannot be created",
            409,
            "The requested quantity is no longer available.",
            "INSUFFICIENT_STOCK",
            List.of()
        );
        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
~~~

This is an abbreviated example for request body validation and a domain error. Applications using method validation may also need to handle HandlerMethodValidationException; JSON parse errors or type conversion errors may travel through different exceptions. Standardize them under the same error contract while keeping error codes reflective of the true cause.

toApiCode is an application helper that maps constraints or binding errors to stable public codes such as NOT_NULL, POSITIVE, or INVALID_FORMAT. Do not expose Spring's internal message codes directly as a contract if you want clients decoupled from the framework.

Do not turn every exception into 400. Programming bugs, dependency failures, or unexpected errors must still be handled as server errors and logged internally with a correlation ID.

## 15. Do Not Let OpenAPI Schemas Promise What the Server Does Not Guarantee

A schema can accidentally publish wrong or overly tight constraints:

- maximum is set to current stock.
- enum contains statuses that vary by configuration or tenant yet is hardcoded as a global value set.
- required marks a field that the server actually allows omitting.
- format: email is treated as proof that an email address exists.
- uniqueItems: true is used to imply unique SKU in the database.
- pattern is used instead of checking resource ownership.

Schemas must reflect a predictable, stable contract. If valid choices vary by user/tenant, describe the general data type in the schema and provide an endpoint to fetch valid options or document the dynamic rule on the operation.

uniqueItems only checks whether elements within an array in the payload are distinct under JSON Schema semantics. It does not check whether a value duplicates a record stored in the database.

## 16. Separating Request DTOs and Response DTOs

Do not reuse a persistence entity as both request body and response body simply because they share some fields. Entities often contain internal fields, server-managed state, persistence relationships, and rules that do not belong in the public contract.

Example:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    String name,

    @NotNull
    @Positive
    BigDecimal price
) {}

public record ProductResponse(
    UUID id,
    String name,
    BigDecimal price,
    ProductStatus status,
    Instant createdAt
) {}
~~~

Clients must not send id, status, or createdAt when creating a product if those fields are server-managed. Responses can publish them as read-only data.

Separate DTOs help OpenAPI generate two meaningful schemas, clarifying which fields clients may control and which fields the server determines. It also reduces mass assignment risk when Jackson binds requests directly onto entities.

## 17. Testing Each Constraint Layer

A good test suite should verify the right layer:

| Test | What to verify | Example |
|---|---|---|
| DTO validation test | Local request constraints | quantity of 0 is rejected |
| Controller test | Status and error body at the HTTP boundary | invalid request returns 400 |
| Domain unit test | Invariants and policies | DISCONTINUED product cannot be sold |
| Application service test | Repository and domain orchestration | nonexistent product throws domain error |
| Persistence integration test | Unique/FK/check constraints | two requests cannot create duplicate SKUs |
| Concurrency test | Invariants under multiple transactions | non-negative stock after concurrent requests |
| OpenAPI contract test | Document reflects request/response | quantity has type integer and minimum 1 |

Do not use an OpenAPI test to prove business rules run properly. Conversely, a domain unit test does not prove /v3/api-docs documents the 409 response.

## 18. Testing DTOs and Bean Validation

Example testing a DTO independently:

~~~java
class CreateOrderRequestValidationTest {

    private final Validator validator =
        Validation.buildDefaultValidatorFactory().getValidator();

    @Test
    void rejectsZeroQuantity() {
        CreateOrderRequest request = new CreateOrderRequest(
            UUID.randomUUID(),
            0,
            DeliveryMode.STANDARD,
            null
        );

        Set<ConstraintViolation<CreateOrderRequest>> violations =
            validator.validate(request);

        assertThat(violations).anySatisfy(violation ->
            assertThat(violation.getPropertyPath().toString())
                .isEqualTo("quantity")
        );
    }
}
~~~

This test needs no database because positive quantity is a local constraint. Do not mock repositories to test @Positive; test what Bean Validation is responsible for.

## 19. Testing Business Rules

Domain unit test example:

~~~java
class ProductTest {

    @Test
    void discontinuedProductCannotBePurchased() {
        Product product = Product.discontinued(
            UUID.randomUUID(),
            "PEN-1024"
        );

        assertThatThrownBy(() -> product.ensurePurchasable(1))
            .isInstanceOf(ProductNotPurchasableException.class);
    }
}
~~~

Domain tests need no HTTP statuses or OpenAPI annotations. They verify invariants independently of how the API presents errors.

In application service tests, verify that when a product does not exist or stock is insufficient, no Order is created and no invalid side effects occur. For transactions and persistence constraints, use integration tests against an appropriate database to verify actual behavior.

## 20. Testing the HTTP Contract and OpenAPI Document

MockMvc can verify that constraint-violating requests return 400:

~~~java
@Test
void invalidQuantityReturnsBadRequest() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "productId": "cbd37c4a-6f6b-4ed9-bad2-77e8ec4d3f61",
                  "quantity": 0,
                  "deliveryMode": "STANDARD"
                }
                """))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value(
            "REQUEST_VALIDATION_FAILED"
        ))
        .andExpect(jsonPath("$.violations[0].field").value("quantity"));
}
~~~

And verify that a validly typed request violating a business rule returns 409:

~~~java
@Test
void unavailableProductReturnsBusinessConflict() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "productId": "cbd37c4a-6f6b-4ed9-bad2-77e8ec4d3f61",
                  "quantity": 2,
                  "deliveryMode": "STANDARD"
                }
                """))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("INSUFFICIENT_STOCK"));
}
~~~

The second test needs deterministic product and stock fixtures to reproduce the error. Both requests share the exact same shape, yet yield different outcomes because system state differs.

Testing the OpenAPI document separately:

~~~java
@Test
void documentsInputConstraintAndBusinessErrorResponse() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.components.schemas.CreateOrderRequest.properties.quantity.type"
        ).value("integer"))
        .andExpect(jsonPath(
            "$.components.schemas.CreateOrderRequest.properties.quantity.minimum"
        ).value(1))
        .andExpect(jsonPath(
            "$.paths['/api/orders'].post.responses['409']"
        ).exists());
}
~~~

JSONPath paths and schema names depend on the project's naming configuration. What matters is that the document publishes both statically checkable request constraints and the business error responses the operation can return.

## 21. Common Mistakes When Mixing Schemas and Business Rules

| Symptom | Cause | Fix |
|---|---|---|
| Swagger UI reports max quantity 5 even as stock changes | Putting current inventory into maximum | Keep schemas aligned with stable limits; return business errors when stock is low |
| Request has a valid UUID yet API returns 404 | Confusing UUID format with resource existence | Document 404 and check the repository in the service |
| Bean Validation queries the database | DTO coupled to persistence and mutable state | Move the rule to the application/domain layer |
| Duplicate SKUs when two requests run concurrently | Only using existsBy... before insert | Add a unique constraint and handle conflict |
| Domain tests must boot Spring context | Business logic lives in controllers or framework-coupled services | Move invariants into unit-testable domain/policy classes |
| OpenAPI shows minimum yet server still accepts smaller values | Schema annotation is not equivalent to runtime validation | Add Bean Validation and HTTP tests |
| API returns 500 on duplicate SKU | Unmapped persistence exception | Translate into an error code and status 409 |
| Clients must parse messages to identify errors | Error contract lacks stable codes | Provide problem codes and an error schema |
| uniqueItems interpreted as system-wide unique SKU | Confusing array uniqueness with database uniqueness | Use a database unique constraint |
| email format treated as proof email exists | Format only checks syntax, not ownership | Use a business verification flow |
| Single DTO used for both create and response | Mixing entity/request/response | Separate DTOs by data direction |
| Every error returns 400 | Not distinguishing invalid input from state conflict | Establish a clear status policy |

## 22. Operation Design Checklist

Before publishing an operation in OpenAPI, answer:

1. Can the request be parsed according to the declared media type and data types?
2. Which fields are required? Are there single-field constraints checkable from the payload?
3. Are there cross-field constraints depending solely on the payload?
4. Which rules require principal, tenant, database, time, or resource state?
5. Which rules require transactions, locking, or database constraints?
6. Is the request DTO separated from the entity and response DTO?
7. Does the OpenAPI schema accurately describe stable constraints?
8. Does the description explain key business rules and rejection conditions?
9. Do responses include statuses and error schemas for validation, not found, forbidden, and conflict?
10. Are error codes stable so clients handle them without parsing messages?
11. Do tests separate DTO validation, domain rules, persistence integrity, and the HTTP contract?
12. Are there concurrency tests for critical invariants like uniqueness or inventory?

## 23. References

- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): validation on controller methods, @Valid, method validation, and related exceptions.
- [Spring Framework – @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): deserializing request bodies, HttpMessageConverter, and triggering Bean Validation.
- [OpenAPI Specification 3.1.1 – Schema Object](https://spec.openapis.org/oas/v3.1.1.html#schema-object): describing data structures and schema keywords.
- [OpenAPI Specification – Specification versions](https://spec.openapis.org/oas/): OpenAPI versions and corresponding schema iterations.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): meanings of status codes 400, 403, 404, 409, 412, and other HTTP codes.
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/): constraint annotations, validators, and validation groups.

## 24. Summary of Practice

OpenAPI schemas and Bean Validation describe and validate data sent by clients over HTTP. The domain/application layer decides whether an action is valid under current state and policy. The database protects final invariants under concurrent transactions.

In Spring Boot, use DTOs and @Valid for input constraints decidable from the payload; keep rules depending on resources, tenants, permissions, inventory, or state in domain/application services; use transactions and database constraints for integrity. Springdoc must publish request/response schemas and corresponding business error responses so consumers understand both what data to send and what outcomes they can receive.
