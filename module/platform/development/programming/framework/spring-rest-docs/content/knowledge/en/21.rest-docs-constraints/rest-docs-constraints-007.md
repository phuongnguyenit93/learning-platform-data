# Constraints on Nested Objects and Collections

## Learning Objectives

In the **SPRING_REST_DOCS** module, API requests often contain more than flat fields. A DTO may include child objects, lists of objects, sets of identifiers, or maps. For example, an order has a nested shipping address and a list of line items. Constraints placed at multiple levels must be checked properly so the API rejects invalid data.

Jakarta Bean Validation supports **cascade validation** via `@Valid` and **container element constraints** to constrain elements inside collections, maps, or supported containers. Spring REST Docs can help place constraint descriptions into snippets, but you must understand how DTO properties map to JSON field paths.

After this lesson, you will be able to:

- Distinguish constraints on object references, child objects, and individual collection elements.
- Use `@Valid` to cascade validation into nested objects and collection elements.
- Combine `@NotNull`, `@NotEmpty`, `@Size`, `@Valid`, and constraints on generic types.
- Constrain Map keys/values and List/Set elements.
- Understand validation error property paths.
- Use `ConstraintDescriptions` for each DTO class and map descriptions to JSON field paths in REST Docs.
- Avoid assuming Spring REST Docs automatically recurses through the entire object graph.

## 1. Nested Objects and Collections in Requests

Example order creation API:

```json
{
  "customerId": 42,
  "shippingAddress": {
    "recipient": "An Nguyen",
    "street": "12 Nguyen Trai",
    "postalCode": "700000"
  },
  "items": [
    { "productId": 101, "quantity": 2 },
    { "productId": 205, "quantity": 1 }
  ],
  "notes": "Deliver during business hours"
}
```

| JSON path | Data Type | Example Rule |
| --- | --- | --- |
| customerId | Number | Required, positive |
| shippingAddress | Object | Required and child object must be validated |
| shippingAddress.recipient | String | Must not be blank |
| shippingAddress.postalCode | String | Follows the API's postal code format |
| items | Array | Required, 1 to 50 elements |
| items[].productId | Number | Required, positive |
| items[].quantity | Number | Required, 1 to 100 |
| notes | String | Optional, maximum 500 characters |

A constraint placed on a parent field does not automatically validate every child field. You must configure cascading in the right places and declare constraints at each level.

## 2. @Valid and Cascade Validation

### 2.1. @Valid on a Nested Object

Address DTO:

```java
public class AddressInput {

    @NotBlank
    @Size(max = 120)
    private String street;

    @NotBlank
    @Size(max = 80)
    private String recipient;

    @NotBlank
    @Pattern(regexp = "^[0-9]{6}$")
    private String postalCode;

    // Getters/setters
}
```

Order DTO:

```java
public class CreateOrderRequest {

    @NotNull
    @Positive
    private Long customerId;

    @NotNull
    @Valid
    private AddressInput shippingAddress;
}
```

The two annotations on `shippingAddress` serve different purposes:

- `@NotNull` requires an address object to be provided.
- `@Valid` instructs the `Validator` to continue checking constraints on the `AddressInput` object.

With `@Valid` alone, a null `shippingAddress` will not cascade validation into the child object; there is no object to validate. If the address is required, combine `@NotNull` and `@Valid`.

With `@NotNull` alone, the reference cannot be null, but constraints on `street`, `recipient`, and `postalCode` will not necessarily be checked via cascading.

### 2.2. @Valid Does Not Replace Constraints on the Parent Object

`@Valid` is a cascade validation directive, not an indication that the object must exist. Nor does it verify on its own that the child object has required fields, positive values, or proper formatting. Those conditions must be declared in `AddressInput` or a custom validator.

### 2.3. Multi-Level Cascading

Validation can traverse multiple object levels if each referenced property is marked for cascading:

```java
public class CustomerInput {

    @NotBlank
    private String name;

    @NotNull
    @Valid
    private ContactInput contact;
}

public class ContactInput {

    @NotBlank
    @Email
    private String email;
}

public class CreateCustomerRequest {

    @NotNull
    @Valid
    private CustomerInput customer;
}
```

When the `Validator` validates `CreateCustomerRequest`, cascading proceeds through `customer` and then `contact`. Constraints on each DTO are applied as the cascade reaches the corresponding object.

Do not assume every object field cascades automatically. Verify each entry point into a child object has `@Valid` or an appropriate cascading mechanism.

## 3. Constraints on Collections and Individual Elements

### 3.1. Requiring a Collection to Have Elements

```java
public class CreateOrderRequest {

    @NotEmpty
    @Size(max = 50)
    private List<Long> productIds;
}
```

Meaning:

- `@NotEmpty` rejects null and empty collections.
- `@Size(max = 50)` caps the collection at 50 elements.

If you only use `@Size(max = 50)`, a null collection may still be valid. If you only use `@NotNull`, an empty collection remains valid.

### 3.2. Constraining Elements via Container Element Constraints

Jakarta Bean Validation supports placing constraints directly on generic type arguments:

```java
public class CreateOrderRequest {

    @NotEmpty
    @Size(max = 50)
    private List<@NotNull @Positive Long> productIds;
}
```

Here:

- `@NotEmpty` and `@Size` apply to the `List`.
- `@NotNull` and `@Positive` apply to each `Long` element.

A list with three elements whose second element is null will violate `@NotNull`. A value of `0` or a negative number violates `@Positive`.

These are **container element constraints**, supported since Bean Validation 2.0. The project must use an API/provider that supports this metadata; legacy setups supporting only Bean Validation 1.1 will not fully understand this syntax.

### 3.3. Cascade Validation on Objects Inside a List

When a collection holds child DTOs, place `@Valid` on the type argument:

```java
public class OrderItemInput {

    @NotNull
    @Positive
    private Long productId;

    @NotNull
    @Min(1)
    @Max(100)
    private Integer quantity;
}

public class CreateOrderRequest {

    @NotEmpty
    @Size(max = 50)
    private List<@NotNull @Valid OrderItemInput> items;
}
```

Validation layers:

1. The `items` list must not be null or empty thanks to `@NotEmpty`.
2. The list has at most 50 elements thanks to `@Size`.
3. Each element is non-null thanks to `@NotNull` on the type argument.
4. For each non-null object, `@Valid` cascades into `OrderItemInput`.
5. `productId` and `quantity` are checked by the constraints in `OrderItemInput`.

If you forget `@Valid` on the type argument, constraints on `OrderItemInput` may not cascade when validating `CreateOrderRequest`.

## 4. Constraints on Sets, Collections, and Arrays

Container element constraints are not limited to `List`:

```java
public class AssignRolesRequest {

    @NotEmpty
    @Size(max = 10)
    private Set<@NotBlank @Pattern(regexp = "^[A-Z_]+$") String> roles;
}
```

The `Set` must have one to ten roles; each element is a non-blank string containing only uppercase letters or underscores.

With arrays:

```java
public class BulkDeleteRequest {

    @NotNull
    @Size(min = 1, max = 100)
    private Long @Positive [] ids;
}
```

Type-use syntax on an array expresses a constraint on the component type. For complex syntax, check `Validator` metadata and write an actual test to confirm annotations are read at the intended position.

Collection-level constraints and element-level constraints are two distinct levels. `@Size` on a list does not inspect individual elements; `@NotBlank` on a type argument does not limit list length.

## 5. Constraints on Maps: Keys and Values

Jakarta Bean Validation lets you place constraints on the key and value type arguments of a `Map`:

```java
public class UpdateSettingsRequest {

    @NotEmpty
    @Size(max = 30)
    private Map<
            @NotBlank @Pattern(regexp = "^[a-z][a-z0-9_.-]*$") String,
            @NotBlank @Size(max = 200) String
    > settings;
}
```

In this example:

- The map must contain at least one entry and at most 30 entries.
- Each key must be non-blank and match the pattern.
- Each value must be non-blank and at most 200 characters.

If the value is a complex object:

```java
public class UpdatePreferencesRequest {

    @NotEmpty
    private Map<
            @NotBlank String,
            @NotNull @Valid PreferenceInput
    > preferences;
}
```

`@Valid` on the value type argument cascades validation into each `PreferenceInput`. Key constraints are still validated separately.

When documenting a `Map` as a JSON object, dynamic keys may not map cleanly to fixed field paths. Document key/value rules with explanatory prose or supplemental snippets rather than trying to create descriptors for every unknown key.

## 6. Optional and Other Containers

Bean Validation can support value extraction for containers supported by the provider. A familiar case is `Optional`:

```java
public class SearchRequest {

    private Optional<@Size(min = 2, max = 40) String> keyword =
            Optional.empty();
}
```

Constraints on the type argument apply to the wrapped value when present and extracted. Exact behavior depends on value extractors and the provider. Do not assume every custom wrapper is supported automatically; a custom `ValueExtractor` may need to be registered.

`Optional` also does not replace API JSON conventions. Jackson may deserialize missing fields, null, or concrete values depending on configuration; verify actual mapping before documenting requiredness/optionality.

## 7. Triggering Validation on HTTP Endpoints

Declaring constraints on DTOs only creates metadata. For Spring MVC to validate a request body, the controller typically enables validation with `@Valid`:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @PostMapping
    ResponseEntity<Void> create(
            @Valid @RequestBody CreateOrderRequest request) {
        // Create order
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

The application needs a Bean Validation provider on the classpath. When a request is invalid, Spring MVC normally raises a validation error (such as `MethodArgumentNotValidException` in standard MVC setups), after which an exception handler determines the HTTP response and error body.

A documentation test should verify both behaviors:

- Valid request: the endpoint succeeds and snippets document the payload.
- Invalid request: the endpoint returns an error matching the API contract; tests can document the error structure.

Do not infer response status/body solely from DTO annotations. The outcome also depends on the controller, validation activation, and exception handling.

## 8. Property Paths of Validation Errors

When a nested object or collection fails validation, Bean Validation creates a `ConstraintViolation` with a property path indicating the path to the invalid element:

```java
Set<ConstraintViolation<CreateOrderRequest>> violations =
        validator.validate(request);

for (ConstraintViolation<CreateOrderRequest> violation : violations) {
    System.out.println(violation.getPropertyPath());
    System.out.println(violation.getMessage());
}
```

Paths can look like:

- `shippingAddress.postalCode`
- `items[0].quantity`
- `items[1].productId`
- `preferences[theme].value`

This is a path representation according to the validation object/metadata model. Node, index, or key details may vary by container type and provider.

### 8.1. Property Paths Are Not Automatic JSON Paths

A property path follows the object model. A JSON path is how REST Docs identifies fields inside a JSON payload. The two often correspond, though not always:

- Jackson may rename fields via `@JsonProperty`.
- A DTO may be flattened or transformed before validation.
- Map keys may be dynamic.
- A Java field may serialize into a different structure.

When documenting, use the actual JSON field/path names in REST Docs descriptors and maintain a clear mapping to validation property paths.

## 9. Documenting Nested Fields with Spring REST Docs

Spring REST Docs accepts JSON field paths in payload descriptors. For nested DTOs, describe the child fields accurately.

Example:

```java
requestFields(
    fieldWithPath("customerId")
        .description("Customer ID."),
    fieldWithPath("shippingAddress")
        .description("Shipping address details."),
    fieldWithPath("shippingAddress.recipient")
        .description("Recipient."),
    fieldWithPath("shippingAddress.street")
        .description("Street address."),
    fieldWithPath("shippingAddress.postalCode")
        .description("Postal code."),
    fieldWithPath("items")
        .description("List of items."),
    fieldWithPath("items[].productId")
        .description("Product ID."),
    fieldWithPath("items[].quantity")
        .description("Quantity.")
)
```

REST Docs uses field paths to verify payload structure. Wildcard/array syntax must align with the payload and REST Docs' field path parser; verify generated snippets via tests rather than assuming arbitrary JSONPath expressions are accepted.

### 9.1. ConstraintDescriptions for Nested Classes

`ConstraintDescriptions` retrieves constraints for properties of the class passed to it. For nested objects, query the child class separately:

```java
ConstraintDescriptions addressConstraints =
        new ConstraintDescriptions(AddressInput.class);

List<String> postalCodeRules =
        addressConstraints.descriptionsForProperty("postalCode");
```

Then map the description to the JSON field path:

```java
fieldWithPath("shippingAddress.postalCode")
        .description("Postal code. " +
                String.join(" ", postalCodeRules))
```

Similarly for collection elements:

```java
ConstraintDescriptions itemConstraints =
        new ConstraintDescriptions(OrderItemInput.class);

List<String> quantityRules =
        itemConstraints.descriptionsForProperty("quantity");

fieldWithPath("items[].quantity")
        .description("Item quantity. " +
                String.join(" ", quantityRules))
```

`ConstraintDescriptions` does not automatically know that `AddressInput` is embedded under `shippingAddress` or that `OrderItemInput` is an element of `items`. The application maps property constraints to JSON paths itself.

### 9.2. Constraints on Generic Elements

Container element constraints like `List<@Positive Long>` sit on the type argument, not as a direct property annotation on the `productIds` field. Default `ConstraintDescriptions` focuses on **property constraints**; do not assume calling `descriptionsForProperty("productIds")` will automatically return every constraint placed on generic elements.

Options to handle this:

1. Write element descriptions manually in the field descriptor, backed by the DTO and validation tests.
2. Build a dedicated metadata helper to read container element descriptors from the Bean Validation metadata API, then turn them into descriptions.
3. Implement a suitable custom resolver/description flow if you want to automate custom conventions.

Example manual descriptor:

```java
fieldWithPath("productIds")
        .description(
                "List of IDs; non-empty, maximum 50 items. " +
                "Each ID must be non-null and a positive number."
        )
```

Descriptions must be verified by tests rather than copying annotations without confirming the validator executes them.

## 10. Testing Nested and Collection Constraints

Tests should cover every level:

| Test Case | Condition | Expected Validation Result |
| --- | --- | --- |
| Missing address | `shippingAddress = null` | Violates `@NotNull` on parent field |
| Address with empty street | `shippingAddress.street = ""` | Violates `@NotBlank` in child object |
| Invalid postal code | `postalCode` fails regex | Violates `@Pattern` in child object |
| Empty list | `items = []` | Violates `@NotEmpty` |
| List too long | `items` has 51 elements | Violates `@Size(max=50)` |
| Null element | `items` contains null | Violates `@NotNull` on type argument |
| Quantity equals 0 | `items[0].quantity = 0` | Violates `@Min(1)` |
| Invalid map key format | `settings` has key failing regex | Violates key constraint |
| Blank map value | `settings` has whitespace value | Violates `@NotBlank` on value |

Example Validator test:

```java
Set<ConstraintViolation<CreateOrderRequest>> violations =
        validator.validate(request);

assertThat(violations)
        .extracting(violation ->
                violation.getPropertyPath().toString())
        .contains("items[0].quantity");
```

The exact property path depends on DTO structure and the provider. In project tests, verify the actual path and then use stable assertions.

## 11. Limitations and Common Pitfalls

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Child object is null yet no error raised | Only `@Valid` present, missing `@NotNull` | Add `@NotNull` if the object is required |
| Nested DTO constraints do not run | Missing `@Valid` at cascade point | Place `@Valid` on the child object property |
| List has invalid elements undetected | Missing `@Valid` on type argument for DTO list | Use `List<@Valid ItemInput>` |
| List has null elements | Missing `@NotNull` on type argument | Use `List<@NotNull @Valid ItemInput>` |
| Empty collection is still valid | Only `@Size(max=...)` or `@NotNull` | Add `@NotEmpty` if elements are required |
| `ConstraintDescriptions` omits element constraints | Constraint is on generic type, not default property metadata | Describe manually or read container element metadata separately |
| Nested field description not found | Queried parent class instead of child class | Create `ConstraintDescriptions` for the nested DTO |
| JSON descriptor does not match validation path | Jackson renames/transforms payload or path parser differs | Cross-check JSON payload and property path |
| Container element constraint has no effect | Outdated Bean Validation API/provider | Use an API/provider supporting Bean Validation 2.0+ |
| Validation does not run at HTTP endpoint | Controller missing `@Valid` or missing provider | Check controller, validation dependency, and exception handling |
| Dynamic map keys cannot be listed as field descriptors | Keys are determined at runtime by clients | Document key/value rules in separate explanatory prose |

## 12. Practice Exercise

1. Create `AddressInput` with `recipient`, `street`, and `postalCode`.
2. Create `OrderItemInput` with `productId` and `quantity`.
3. Create `CreateOrderRequest` with `shippingAddress` and `List<OrderItemInput> items`, applying `@NotNull`, `@Valid`, `@NotEmpty`, `@Size`, and container element constraints.
4. Write Validator tests for nested objects, empty lists, null elements, and invalid quantities.
5. Print the `ConstraintViolation` property paths to observe the paths to invalid fields.
6. Write a MockMvc test documenting a valid request with field paths for `shippingAddress` and `items`.
7. Create separate `ConstraintDescriptions` instances for `AddressInput` and `OrderItemInput`; pass `postalCode`/`quantity` descriptions into the corresponding field descriptors.
8. Verify generic `List` constraints with a real test; decide whether to document manually or build a metadata helper.

**Self-Assessment Questions**

1. How does `@Valid` differ from `@NotNull`?
2. Why must `@Valid` be placed at the cascade entry point?
3. Which levels does `List<@NotNull @Valid ItemInput>` validate?
4. Does `@Size` on a `List` constrain individual elements or element count?
5. How do constraints on Map keys differ from constraints on Map values?
6. Which generation of Bean Validation is required for container element constraints?
7. Why might a Validator property path not match a JSON field path?
8. Does `ConstraintDescriptions` automatically recurse into child DTOs and generic elements?

## Official References

- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): cascade validation, container element constraints, value extraction, and property paths.
- [Jakarta Validation API — Valid](https://jakarta.ee/specifications/bean-validation/apidocs/jakarta/validation/valid): marking cascade validation.
- [Jakarta Validation API — ConstraintViolation](https://jakarta.ee/specifications/bean-validation/apidocs/jakarta/validation/constraintviolation): message, invalid value, and property path.
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): integrating Validator with Spring.
- [Spring REST Docs — Documenting Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field descriptors and payload documentation.
- [Spring REST Docs — Bean Validation Constraints](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html): `ConstraintDescriptions` and property constraints.

**Practical Takeaway:** Place constraints at the right data level: parent object constraints for references, `@Valid` for cascading, and container element constraints for individual items or keys/values. When generating documentation, query constraints on each corresponding DTO and map descriptions to actual JSON field paths. Validation tests and REST Docs together verify the request contract, though property metadata does not automatically replace documenting every nested/container rule.
