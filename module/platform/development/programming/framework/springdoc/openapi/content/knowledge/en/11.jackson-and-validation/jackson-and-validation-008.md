# @Valid and Nested Data Structures

## 1. Why Do Nested Structures Need Layered Validation?

JSON requests in Spring Boot applications rarely consist solely of flat fields. An order creation request may include shipping details, a list of line items, and a delivery address. Each nested object has its own rules: the recipient name must not be blank, the product ID must be valid, quantity must exceed 0, and the line item list must contain at least one element.

If only the top-level object is validated, nested objects can still pass invalid data into business logic. Bean Validation solves this via **cascaded validation**: when a property is annotated with **@Valid**, the validator recurses into the referenced object or elements inside that property.

In API documentation, Springdoc OpenAPI must describe nested JSON structures and their constraints. Jackson determines how JSON maps to Java objects; Bean Validation checks objects after binding; Springdoc reads Java types, Jackson metadata, and validation annotations to build schemas. These three parts are closely connected yet hold distinct responsibilities.

This lesson covers using **@Valid** to validate nested objects, collections, arrays, and multi-level hierarchies; how Jackson affects property names and presence; and how to verify that OpenAPI schemas match runtime behavior.

## 2. Request Processing Flow in Spring MVC

For an endpoint accepting JSON, processing normally proceeds in this order:

1. The client sends an HTTP request with an appropriate Content-Type, typically application/json.
2. Spring selects an HttpMessageConverter and Jackson parses the JSON.
3. Jackson deserializes the payload into a Java DTO.
4. Spring triggers Bean Validation if the parameter is annotated with @Valid or @Validated according to configuration.
5. The validator checks constraints on the outer object and nested objects cascaded via @Valid.
6. If data is valid, the controller executes business logic.
7. If data is invalid, Spring raises a validation error for an exception handler to turn into an appropriate HTTP response.

Example:

~~~java
@PostMapping("/api/orders")
public OrderResponse create(
    @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

**@RequestBody** instructs Spring to read the request body and bind it to CreateOrderRequest. **@Valid** requests constraint validation on the object after deserialization. If the DTO contains nested objects or collections, mark those properties for cascading so the validator traverses deeper into the structure.

Jackson and Bean Validation handle two different kinds of errors:

- Malformed JSON, incompatible types that cannot deserialize, or missing creator fields can trigger message-reading errors, typically mapped to 400 Bad Request.
- JSON that deserializes cleanly yet violates @NotBlank, @Min, or another constraint triggers validation errors, typically via MethodArgumentNotValidException in Spring MVC.

OpenAPI describes the schemas and error responses clients need to know. Springdoc does not run Jackson deserialization or execute Bean Validation when generating documentation.

## 3. @Valid Performs Cascaded Validation

The **jakarta.validation.Valid** annotation marks a location requiring recursive validation. It is not a value-checking constraint itself. @Valid merely instructs the validator to step into the referenced object and check the constraints declared on it.

Example:

~~~java
public record AddressRequest(
    @NotBlank
    String street,

    @NotBlank
    String city,

    @Pattern(regexp = "^[0-9]{5,10}$")
    String postalCode
) {}

public record CreateCustomerRequest(
    @NotBlank
    String fullName,

    @Email
    String email,

    @Valid
    AddressRequest address
) {}
~~~

When the validator checks CreateCustomerRequest, constraints on fullName and email run. Because address has @Valid, the validator also validates street, city, and postalCode inside AddressRequest whenever address is non-null.

An important point: **@Valid alone does not require the nested object to exist**. If address is null, the validator cannot descend into it and typically skips cascading. If business rules require address to be present, combine @NotNull:

~~~java
public record CreateCustomerRequest(
    @NotBlank
    String fullName,

    @NotNull
    @Valid
    AddressRequest address
) {}
~~~

In this example:

- @NotNull requires address to have a value.
- @Valid triggers validation of fields inside AddressRequest.
- @NotBlank on street and city checks the content of the nested fields.

Combining constraints and cascading cleanly separates object presence from the validity of its inner properties.

## 4. @Valid with Collections and Nested Elements

A List or Set property can hold many nested objects. To validate each element, configure cascaded validation on the collection property or on the type argument using container element constraints.

Example using type-use annotations:

~~~java
public record CreateOrderRequest(
    @NotEmpty
    @Size(max = 50)
    List<@NotNull @Valid OrderLineRequest> items
) {}

public record OrderLineRequest(
    @NotNull
    @Positive
    Long productId,

    @NotNull
    @Min(1)
    @Max(1000)
    Integer quantity
) {}
~~~

When validating CreateOrderRequest:

- @NotEmpty requires items to be non-null and have at least one element.
- @Size(max = 50) limits the list to at most 50 line items.
- @NotNull on the element forbids null entries in the list.
- @Valid on the element validates each OrderLineRequest.
- @Positive and @Min/@Max validate values on each line item.

You can also place @Valid on the collection property:

~~~java
public record CreateOrderRequest(
    @NotEmpty
    @Valid
    List<OrderLineRequest> items
) {}
~~~

This also cascades validation to collection elements. Type-use annotations clarify which constraints target individual elements, such as @NotNull, while @Valid triggers nested object validation.

For arrays or Sets, the same principles apply:

~~~java
public record BatchRequest(
    @NotEmpty
    List<@NotNull @Valid CustomerRequest> customers,

    @NotNull
    @Valid
    AddressRequest[] deliveryAddresses
) {}
~~~

Verify support in your Bean Validation provider and Java/Jakarta Validation version, especially for container element constraints and deeply nested collections.

## 5. Cascading Across Multiple Object Levels

Data can be nested across multiple levels. For instance, an order contains a customer, an address, line items, and delivery details.

~~~java
public record CreateOrderRequest(
    @NotNull
    @Valid
    CustomerRequest customer,

    @NotEmpty
    List<@NotNull @Valid OrderLineRequest> items,

    @NotNull
    @Valid
    DeliveryRequest delivery
) {}

public record CustomerRequest(
    @NotBlank
    String name,

    @NotNull
    @Valid
    AddressRequest address
) {}

public record DeliveryRequest(
    @NotBlank
    String recipient,

    @NotNull
    @Valid
    AddressRequest address,

    @Future
    LocalDate deliveryDate
) {}
~~~

When the controller validates CreateOrderRequest, the validator traverses customer, customer.address, every element of items, delivery, and delivery.address thanks to @Valid at each link.

Each level can enforce its own constraints:

- Parent objects check whether child objects are provided.
- Child objects check their own fields.
- Collections check element counts.
- Collection elements check values and deeper nested objects.

If @Valid is forgotten at any link, cascading stops there. For example, if customer has @Valid yet customer.address lacks @Valid, the validator checks constraints on CustomerRequest without descending into AddressRequest.

## 6. How Do @Valid, @NotNull, @NotEmpty, and @NotBlank Differ?

These annotations often appear together but test different conditions:

| Annotation | Typical Applicable Types | Condition |
|---|---|---|
| @Valid | Objects, collections, container elements | Cascades validation into child objects or elements |
| @NotNull | Any reference type | Value must not be null |
| @NotEmpty | CharSequence, Collection, Map, array | Not null and not empty |
| @NotBlank | CharSequence | Not null and contains at least one non-whitespace character |
| @Size | CharSequence, Collection, Map, array | Size falls within allowed bounds |
| @NotEmpty + @Valid | Collection of objects | Collection must have elements and each object undergoes cascaded validation |
| @NotNull + @Valid | Nested object | Object must exist and its child fields are validated |

Example:

~~~java
public record RegistrationRequest(
    @NotNull
    @Valid
    ProfileRequest profile,

    @NotEmpty
    List<@NotNull @Valid ContactRequest> contacts
) {}
~~~

Profile must be non-null and deeply validated. Contacts must contain at least one item, each item must be non-null, and each item's inner constraints are checked.

@Valid alone does not replace @NotNull, @NotEmpty, or @NotBlank. Conversely, @NotNull only checks that a reference is non-null without inspecting inner fields.

## 7. @Valid on Maps and Nested Containers

Bean Validation supports cascaded validation on multiple container types, not just Lists. For a Map, you can validate keys or values using type-use annotations.

Example validating Map values:

~~~java
public record ContactDirectoryRequest(
    @NotEmpty
    Map<
        @NotBlank String,
        @NotNull @Valid ContactRequest
    > contacts
) {}

public record ContactRequest(
    @NotBlank
    String phone,

    @Email
    String email
) {}
~~~

Here:

- Keys must be non-blank strings.
- Values must be non-null.
- Each ContactRequest has its phone and email validated.

To validate keys and values, place constraints on the respective type arguments. For nested containers such as Map<String, List<AddressRequest>>, cascade at every layer containing objects to validate:

~~~java
Map<String, List<@NotNull @Valid AddressRequest>> addressesByType
~~~

The JSON shape of a Map is typically an object with dynamic property names, while an inner List is an array. The OpenAPI schema should reflect that structure. Springdoc can infer generic types and nested schemas, though you should inspect the generated documentation when using complex containers.

## 8. Jackson Determines JSON Property Names

Jackson handles conversion between JSON and Java objects. JSON property names do not have to match field or component names in Java records.

Example:

~~~java
public record CustomerRequest(
    @JsonProperty("full_name")
    @NotBlank
    String fullName,

    @JsonProperty("email_address")
    @Email
    String email
) {}
~~~

Client sends JSON:

~~~json
{
  "full_name": "Nguyen Van An",
  "email_address": "an@example.com"
}
~~~

Jackson maps full_name to component fullName and email_address to email. Springdoc normally uses Jackson metadata when generating OpenAPI property names, so the documentation should display full_name and email_address if those are the actual JSON names.

You can also use a class-level naming strategy:

~~~java
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record CustomerRequest(
    @NotBlank String fullName,
    @Email String emailAddress
) {}
~~~

With this configuration, Jackson converts property names to snake_case per the naming strategy. Check the OpenAPI document to confirm generated property names match the running ObjectMapper.

## 9. Jackson Aliases, Ignore, and Read/Write Access

Several Jackson annotations affect whether a property is accepted during deserialization or emitted during serialization.

| Annotation/Setting | Jackson Behavior | What to Check in OpenAPI |
|---|---|---|
| @JsonProperty | Sets property name or configures access | Schema uses the right JSON name |
| @JsonAlias | Accepts alternative names when deserializing | Input aliases need not be published as canonical properties |
| @JsonIgnore | Skips property per annotation configuration | Property may be omitted from schema |
| @JsonIgnoreProperties(ignoreUnknown = true) | Ignores unknown properties when deserializing | Does not turn arbitrary properties into published schema fields |
| @JsonProperty(access = READ_ONLY) | Serialized only, not normally accepted as input | May show readOnly |
| @JsonProperty(access = WRITE_ONLY) | Accepted as input only, not normally serialized in output | May show writeOnly |
| @JsonInclude | Controls when a property is written to JSON output | Does not replace required or validation |

Example DTO with a read-only field:

~~~java
public record ProductResponse(
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    Long id,

    @NotBlank
    String name
) {}
~~~

If the same DTO is shared between requests and responses, id may be treated by Jackson as read-only. In real projects, however, consider splitting CreateProductRequest and ProductResponse so input and output contracts remain clearer.

Alias example:

~~~java
public record SearchRequest(
    @JsonProperty("keyword")
    @JsonAlias({"q", "searchTerm"})
    String keyword
) {}
~~~

Jackson accepts q or searchTerm when reading JSON, while the canonical published property name should be keyword. Aliases exist for input compatibility; avoid treating every alias as a separate schema property if the API does not want new clients using legacy names.

## 10. Jackson and Distinguishing Missing Properties from Null

JSON can represent a property in three states:

1. Property omitted.
2. Property present with value null.
3. Property present with a concrete value.

These three cases can have different meanings, especially for partial update APIs like PATCH.

Example:

~~~json
{
  "displayName": null
}
~~~

differs from:

~~~json
{}
~~~

In an ordinary Java DTO, both cases can produce null unless a separate presence-tracking mechanism exists. Jackson configuration, constructor binding, primitive types, and custom deserializers can alter how they are distinguished.

Notes:

- Reference types like String or Integer can receive null unless rejected by a constraint or deserializer.
- Primitives like int cannot hold null; if omitted, Java's default may be 0.
- @NotNull validates the post-binding value and does not itself distinguish omitted properties from explicit null.
- @JsonInclude(NON_NULL) controls response serialization and does not make a request property optional.
- OpenAPI required states whether the property must be present; nullable states whether null values are allowed.

For PATCH, if you need to distinguish “no change” from “clear value,” design an explicit DTO or presence mechanism, such as a specialized wrapper or JsonNode. Do not rely on a single nullable field when the two states carry distinct business meanings.

## 11. Validation Constraints Reflected in the OpenAPI Schema

Springdoc can read Bean Validation constraints to enrich schema metadata. Common mappings include:

| Bean Validation | Typical Schema Metadata |
|---|---|
| @NotNull | Rejects null values; tooling may also add the property to required depending on schema/version and config |
| @NotBlank | Non-empty string after trimming whitespace |
| @Size(min, max) | minLength/maxLength or minItems/maxItems depending on type |
| @Min / @DecimalMin | minimum |
| @Max / @DecimalMax | maximum |
| @Positive | exclusiveMinimum or equivalent limit |
| @Pattern | pattern |
| @Email | email format or equivalent metadata |
| @NotEmpty | At least one character/element per type |
| @Digits | Digit and fraction limits where supported |

Exact mapping depends on the Springdoc, swagger-core, Bean Validation provider, and OpenAPI versions emitted. Not every custom constraint translates automatically into a schema keyword.

Note that OpenAPI has two separate concepts: required determines whether a property must appear in the object, while nullable/type determines whether it accepts null. @NotNull is a runtime constraint forbidding null; check the generated document to see how it is represented as required, nullable, or both. Likewise, minLength: 1 cannot fully express @NotBlank because a string containing only spaces still has length greater than 0.

Example:

~~~java
public record AddressRequest(
    @NotBlank
    @Size(max = 120)
    String street,

    @NotBlank
    @Pattern(regexp = "^[A-Z]{2,3}$")
    String countryCode,

    @NotNull
    @Positive
    BigDecimal latitude
) {}
~~~

OpenAPI can describe street's maximum length, countryCode's pattern, and latitude's numeric bound. Still, inspect the generated JSON rather than assuming all annotations map identically across versions.

## 12. @Valid Alone Does Not Make a Nested Schema Required

A DTO may declare:

~~~java
public record OrderRequest(
    @Valid
    AddressRequest address
) {}
~~~

The AddressRequest type lets Springdoc know the nested object structure and generate nested schemas. @Valid enables cascaded validation at runtime. However, @Valid alone does not mean address must be present.

If address is required, declare:

~~~java
public record OrderRequest(
    @NotNull
    @Valid
    AddressRequest address
) {}
~~~

Springdoc can reflect @NotNull in the schema according to version and configuration. Verify both the object's required list and nullability schema so clients understand accurately.

Similarly, for collections:

~~~java
public record OrderRequest(
    @NotEmpty
    List<@Valid OrderLineRequest> items
) {}
~~~

@Valid validates each element, while @NotEmpty requires at least one element in the collection. If items must not be null, add @NotNull on the type argument.

## 13. Validation Groups and Nested Validation

A DTO may be reused across multiple flows, such as creation and updates. Validation groups allow selecting constraint subsets per action.

Example group definitions:

~~~java
public interface OnCreate {}
public interface OnUpdate {}
~~~

DTO:

~~~java
public record ProductRequest(
    @NotBlank(groups = {OnCreate.class, OnUpdate.class})
    String name,

    @NotNull(groups = OnCreate.class)
    @Positive(groups = {OnCreate.class, OnUpdate.class})
    BigDecimal price
) {}
~~~

Controllers can select the group when triggering validation:

~~~java
@PostMapping("/api/products")
public ProductResponse create(
    @Validated(OnCreate.class)
    @RequestBody ProductRequest request
) {
    return productService.create(request);
}

@PutMapping("/api/products/{id}")
public ProductResponse update(
    @PathVariable Long id,
    @Validated(OnUpdate.class)
    @RequestBody ProductRequest request
) {
    return productService.update(id, request);
}
~~~

In practice, ensure the Default group and custom groups are configured properly; constraints without explicit groups belong to Default. When cascading into a nested object under a different group, use **@ConvertGroup** alongside @Valid to map the current group to the nested object's group.

Example:

~~~java
public record CreateOrderRequest(
    @Valid
    @ConvertGroup(from = Default.class, to = OnCreate.class)
    AddressRequest address
) {}
~~~

Validation groups are runtime behavior. Springdoc cannot automatically produce one shared schema that expresses every distinct group constraint set across every operation. If create and update requests have differing contracts, use separate DTOs or define separate request schemas so clients do not have to guess which constraints apply.

## 14. Class-Level Validation and Cross-Field Rules

Some rules require inspecting multiple properties together. For example, start date must precede end date, or at least one of email and phone must be supplied.

You can create a class-level constraint:

~~~java
@ValidDateRange
@Schema(description = "End date must be after start date.")
public record BookingRequest(
    @NotNull LocalDate startDate,
    @NotNull LocalDate endDate
) {}
~~~

A custom validator checks the relationship between startDate and endDate. OpenAPI Schemas can usually represent types, required flags, and per-property constraints, but cannot always express full cross-field logic purely in JSON Schema.

If metadata cannot be placed on the class as shown, document the rule in the schema or operation description. The custom validator still needs to run at runtime; @Schema.description merely explains the rule to documentation readers. Also document the validation error response if clients need the error structure. Never assume that having a custom validator causes Springdoc to emit an equivalent schema keyword automatically.

## 15. Defining the Validation Error Response

When validation fails, Spring MVC normally throws an exception. Applications can use @RestControllerAdvice to standardize the response.

Example error DTOs:

~~~java
public record ValidationErrorResponse(
    String code,
    String message,
    List<FieldViolation> violations
) {}

public record FieldViolation(
    String field,
    String message
) {}
~~~

Exception handler:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ValidationErrorResponse> handleValidation(
        MethodArgumentNotValidException exception
    ) {
        List<FieldViolation> violations =
            exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldViolation(
                    error.getField(),
                    error.getDefaultMessage()
                ))
                .toList();

        ValidationErrorResponse body = new ValidationErrorResponse(
            "VALIDATION_FAILED",
            "Request contains invalid data",
            violations
        );

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

You can document the 400 response in OpenAPI:

~~~java
@ApiResponse(
    responseCode = "400",
    description = "Invalid request data",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ValidationErrorResponse.class)
    )
)
~~~

Do not expect Springdoc to automatically infer every error response from all @RestControllerAdvice classes across every setup. Explicitly declare important responses on operations or use shared response configurations, then inspect the generated documentation.

Also distinguish Jackson parse errors from Bean Validation errors. Malformed JSON may go through HttpMessageNotReadableException; post-binding constraint failures typically go through MethodArgumentNotValidException. If the API returns two different error shapes, document them separately or normalize them into a single unified error response.

## 16. From Jackson DTO to OpenAPI Schema: Combined Example

Order creation request example:

~~~java
public record CreateOrderRequest(
    @JsonProperty("customer")
    @NotNull
    @Valid
    CustomerRequest customer,

    @JsonProperty("line_items")
    @NotEmpty
    @Size(max = 50)
    List<@NotNull @Valid OrderLineRequest> lineItems,

    @JsonProperty("delivery_note")
    @Size(max = 500)
    String deliveryNote
) {}

public record CustomerRequest(
    @JsonProperty("full_name")
    @NotBlank
    @Size(max = 120)
    String fullName,

    @Email
    String email,

    @NotNull
    @Valid
    AddressRequest address
) {}

public record AddressRequest(
    @NotBlank
    String street,

    @NotBlank
    String city,

    @Pattern(regexp = "^[A-Z]{2,3}$")
    String countryCode
) {}

public record OrderLineRequest(
    @NotNull
    @Positive
    Long productId,

    @NotNull
    @Min(1)
    Integer quantity
) {}
~~~

Controller:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public OrderResponse create(
    @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

The OpenAPI documentation should reflect:

- JSON properties are customer, line_items, and delivery_note per Jackson mapping.
- customer is a required object whose child fields follow CustomerRequest.
- line_items is a non-empty array with at most 50 items.
- Each line_items element is OrderLineRequest and undergoes cascaded validation.
- delivery_note has a maximum length limit.
- full_name is a non-blank string with a maximum length limit.
- address is a required object with cascaded validation.
- countryCode has its pattern published if the constraint is supported.
- Request body uses application/json.

OpenAPI can express most structures and single-property constraints. Complex business rules or validation-group dependencies still require extra description or separate schemas/request DTOs.

## 17. Common Pitfalls When Using @Valid with Nested Data

| Symptom | Causes to Check |
|---|---|
| Nested object is not validated | Missing @Valid on the property or at one nesting level |
| Nested object is null yet no error occurs | Has @Valid without @NotNull |
| Empty collection is accepted | Has @Valid without @NotEmpty or @Size(min = 1) |
| Null item inside collection is not rejected | Missing @NotNull on the element |
| Constraints inside each element do not run | Cascaded validation not placed properly on container/type argument |
| Swagger property names differ from JSON | Jackson @JsonProperty or naming strategy not reflected as expected |
| Read-only property still appears in request | Shared DTO or mismatched Jackson access mode/schema access |
| Schema reports wrong requiredness | Confusing @Valid with @NotNull or version-specific constraint inference |
| Validation group not applied | Controller did not activate the right group or missing group conversion on cascade |
| Custom validator missing from schema | Springdoc cannot automatically infer custom business rules |
| Wrong JSON type returns non-validation error | Deserialization failed before Bean Validation ran |
| Schema shows bounds yet backend does not check | Validation not enabled or validation provider missing |

When troubleshooting, inspect in order: actual JSON, Jackson mapping, post-deserialization DTO, @Valid placement, Bean Validation constraints, exception handler, and OpenAPI document. This isolates whether the issue lies in binding, validation, or documentation.

## 18. Verifying Runtime and OpenAPI Documentation Alignment

After updating DTOs or annotations, fetch the OpenAPI JSON from the Springdoc endpoint, typically:

~~~http
GET /v3/api-docs
~~~

Verify these items:

1. Property names match Jackson serialization/deserialization.
2. Nested objects have accurate schemas and appropriate component references.
3. Collections have type array and accurate items schemas.
4. required reflects mandatory properties; nullable reflects null allowance.
5. minLength, maxLength, minimum, maximum, pattern, minItems, and maxItems are accurate.
6. readOnly/writeOnly match Jackson access and request/response direction.
7. Validation groups do not force endpoints sharing a DTO to need distinct schemas.
8. The 400 response documents both validation errors and JSON parse errors accurately.

Write integration tests for these cases:

- Missing required nested object.
- Nested object with blank or invalidly formatted fields.
- Empty collection, collection exceeding bounds, or containing null elements.
- A collection element violating a deeply nested constraint.
- JSON using canonical property names, aliases, and invalid names.
- Properties that are omitted, null, or populated.
- Malformed dates, enums, or numeric types.
- Syntactically invalid JSON.

Runtime tests confirm actual behavior; OpenAPI inspection confirms the published contract. Both complement each other and prevent docs from promising rules the server never enforces.

## 19. Design Principles for Nested DTOs

To keep Jackson, Bean Validation, and Springdoc aligned:

1. Use separate DTOs for requests and responses when read/write access or constraints differ.
2. Place @Valid at every object boundary needing cascaded validation.
3. Combine @NotNull whenever a nested object is required to exist.
4. Use @NotEmpty or @Size when collections need element count bounds.
5. Use type-use constraints to validate individual collection elements.
6. Declare @JsonProperty or naming strategies explicitly when JSON names differ from Java names.
7. Never treat @JsonInclude as a requiredness or validation mechanism.
8. Use validation groups deliberately; consider separate DTOs when create/update contracts diverge.
9. Document class-level business rules in descriptions when schemas cannot express them fully.
10. Inspect OpenAPI JSON/YAML alongside integration tests after DTO, Jackson, or validation changes.

@Valid enables deep validation across object hierarchies; Jackson determines how JSON maps into Java structures; Bean Validation enforces constraints; Springdoc uses that metadata to document the contract. When these layers are configured consistently, clients understand nested request structures accurately and the server rejects invalid inputs under the exact rules published.

