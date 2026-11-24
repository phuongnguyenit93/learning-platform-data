# Length Limits, Numeric Ranges, String Patterns, and Array Sizes

Schemas in OpenAPI do not merely describe whether a value is a `string`, `integer`, or `array`. Schemas can also express limits so clients know what shape valid data must take: how long a string must be, what range a number falls in, what pattern a string must match, and the minimum or maximum number of elements an array may contain.

With Spring Boot, constraints are typically declared with Bean Validation annotations such as `@Size`, `@Min`, `@Max`, `@DecimalMin`, `@DecimalMax`, and `@Pattern`. Springdoc can read this metadata to generate OpenAPI schemas. However, the generated documentation and runtime validation are two parts that must be verified separately: a schema that merely documents limits does not by itself cause Spring to reject invalid request data.

## 1. Constraint Groups in Schema Object

Commonly used keywords for this topic:

| Data Type | OpenAPI/JSON Schema Keyword | Meaning |
|---|---|---|
| String | `minLength` | Minimum number of characters. |
| String | `maxLength` | Maximum number of characters. |
| String | `pattern` | Regular expression the value must match. |
| Number | `minimum` | Minimum value, inclusive by default. |
| Number | `maximum` | Maximum value, inclusive by default. |
| Number | `exclusiveMinimum` | Exclusive lower bound. |
| Number | `exclusiveMaximum` | Exclusive upper bound. |
| Array | `minItems` | Minimum number of elements. |
| Array | `maxItems` | Maximum number of elements. |
| Array | `uniqueItems` | Elements must be unique under JSON value comparison. |

These limits are typically placed on the `Schema Object` of a property or item. They can appear in `components.schemas`, request bodies, responses, or parameter schemas.

Example of a product DTO with a name, price, and tag list:

```yaml
type: object
required:
  - name
  - price
  - tags
properties:
  name:
    type: string
    minLength: 3
    maxLength: 80
    pattern: '^[A-Za-z0-9 -]+$'
  price:
    type: number
    minimum: 0.01
    maximum: 999999.99
  tags:
    type: array
    minItems: 1
    maxItems: 10
    uniqueItems: true
    items:
      type: string
      minLength: 1
      maxLength: 30
```

The schema states the data structure and limits that can be checked automatically. More complex business rules, such as a total price having to match a product category, still need to be documented and enforced at the application layer.

## 2. String Length Limits

### 2.1. `minLength` and `maxLength`

`minLength` specifies the minimum number of characters; `maxLength` specifies the maximum number of characters. For example, a product name must be 3 to 80 characters long:

```yaml
name:
  type: string
  minLength: 3
  maxLength: 80
```

With Bean Validation, use `@Size` on `String` or `CharSequence` types:

```java
public record CreateProductRequest(
        @NotBlank
        @Size(min = 3, max = 80)
        String name
) {}
```

Springdoc can map string `@Size` bounds to `minLength` and `maxLength`. `@NotBlank` adds the requirement that the string must not be null, empty, or whitespace-only. `@Size(min = 3)` and `@NotBlank` address two different aspects: length and non-whitespace content.

`@Size` does not trim leading or trailing whitespace automatically. If business rules require trimming strings, normalize the data or use appropriate validation before processing.

### 2.2. Distinguishing `@Size`, `@NotEmpty`, and `@NotBlank`

| Annotation | Is `null` Valid? | Is Empty String Valid? | Is Whitespace-Only String Valid? |
|---|---:|---:|---:|
| `@Size(min = 1)` | Yes | No | Yes |
| `@NotEmpty` | No | No | Yes |
| `@NotBlank` | No | No | No |

`@Size` only checks size and generally does not require the value to be non-null. If a field is required, combine it with `@NotNull`, `@NotEmpty`, or `@NotBlank` according to the data type and desired rule.

Example:

```java
public record ProfileRequest(
        @NotBlank
        @Size(max = 60)
        String displayName,

        @NotEmpty
        @Size(max = 200)
        String biography
) {}
```

`displayName` must have non-whitespace content and at most 60 characters. `biography` must be non-null, non-empty, and no longer than 200 characters; a whitespace-only string still passes `@NotEmpty`, so if that is unacceptable, use `@NotBlank`.

### 2.3. Unicode String Length

Length in schemas and how Java counts `String.length()` can differ for certain Unicode characters outside the Basic Multilingual Plane, such as emojis represented as UTF-16 surrogate pairs. JSON Schema defines string length in Unicode code points (characters); some Java checks based on `CharSequence.length()` count UTF-16 code units.

If length limits have strict business meaning for multilingual content, test accented letters, combining characters, and emojis. Do not assume character counting in clients, schema validators, and the Java runtime yields the same result for every Unicode string.

## 3. String Patterns with `pattern`

`pattern` uses a regular expression to describe string formatting. For example, an order code consisting of uppercase letters, digits, and hyphens:

```yaml
orderCode:
  type: string
  minLength: 5
  maxLength: 24
  pattern: '^[A-Z0-9-]+$'
```

In Java, use `@Pattern`:

```java
public record CreateOrderRequest(
        @NotBlank
        @Size(min = 5, max = 24)
        @Pattern(regexp = "^[A-Z0-9-]+$")
        String orderCode
) {}
```

`@Pattern` checks that the string matches the regular expression using Java's regex engine. Springdoc can translate the declared expression into the `pattern` keyword in the schema.

### 3.1. Anchor expressions with `^` and `$`

In JSON Schema, `pattern` is generally evaluated as needing to match somewhere within the string; it does not implicitly require matching the entire string. To validate the whole string, place the `^` anchor at the start and `$` at the end:

```regex
^[A-Z]{2}-[0-9]{6}$
```

This expression matches codes like `AB-123456`. Without anchors, a longer string containing a matching substring can still satisfy the JSON Schema pattern condition.

### 3.2. Differences between Java regex and OpenAPI regex

Bean Validation `@Pattern` uses Java regex syntax, whereas `pattern` in OpenAPI/JSON Schema is based on ECMA-262 regular expression syntax. Most simple patterns like `[A-Z0-9-]+` work in both, but some advanced features or escapes may differ.

To improve compatibility between server and client validators:

- Prefer standard character classes, quantifiers, and anchors.
- Avoid relying on lookbehinds, named groups, or engine-specific features unless necessary.
- Test the same set of sample values on Java validation and the OpenAPI/JSON Schema validators used by consumers.
- Check escaping when placing regexes in Java strings and YAML/JSON. For example, backslashes may need extra escaping in Java string literals.

Example of a `YYYY-MM-DD` date regex that only checks string shape:

```java
@Pattern(regexp = "^\\d{4}-\\d{2}-\\d{2}$")
String dateText
```

This pattern does not guarantee the date exists on the calendar. A value like `2026-19-45` still matches the shape. If the data is a date, use `LocalDate` and an appropriate format instead of using regex to simulate all calendar rules.

### 3.3. Using `format` or `pattern`?

`format` describes a known data format, such as `email`, `date`, `date-time`, `uuid`, or `uri`. `pattern` describes an application-specific regex rule.

```yaml
email:
  type: string
  format: email

productCode:
  type: string
  pattern: '^[A-Z]{3}-[0-9]{5}$'
```

Do not write overly complex regexes to replace standard formats when OpenAPI already has a suitable `format`. Conversely, `format: email` is not necessarily identical to every server-side email validation rule; if business rules impose specific limits, add validation and document them clearly.

## 4. Numeric Ranges and Inclusive/Exclusive Bounds

### 4.1. `minimum` and `maximum`

`minimum` and `maximum` represent inclusive bounds by default. For example, a product price from 0 to 1,000,000:

```yaml
price:
  type: number
  minimum: 0
  maximum: 1000000
```

With Bean Validation, use `@Min` and `@Max` for applicable integer types:

```java
public record QuantityRequest(
        @Min(1)
        @Max(500)
        Integer quantity
) {}
```

For `BigDecimal` or decimal values, use `@DecimalMin` and `@DecimalMax`:

```java
public record PriceRequest(
        @DecimalMin("0.01")
        @DecimalMax("999999.99")
        BigDecimal price
) {}
```

Both `@DecimalMin` and `@DecimalMax` are inclusive by default. Use `inclusive = false` if the boundary value itself is disallowed.

### 4.2. Exclusive bounds

For example, a quantity must be greater than 0 and less than 100:

```java
public record DiscountRequest(
        @DecimalMin(value = "0", inclusive = false)
        @DecimalMax(value = "100", inclusive = false)
        BigDecimal percentage
) {}
```

OpenAPI 3.0 and 3.1 represent exclusive bounds differently:

| Meaning | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Greater than 0 | `minimum: 0` and `exclusiveMinimum: true` | `exclusiveMinimum: 0` |
| Less than 100 | `maximum: 100` and `exclusiveMaximum: true` | `exclusiveMaximum: 100` |

In OpenAPI 3.0, `exclusiveMinimum` and `exclusiveMaximum` are booleans paired with `minimum`/`maximum`. In OpenAPI 3.1, the exclusive keywords take the numeric bound itself per JSON Schema 2020-12. When changing the output OpenAPI version, inspect the generated schema rather than assuming the old representation remains valid.

### 4.3. `@Positive`, `@PositiveOrZero`, `@Negative`

Bean Validation also provides annotations expressing numeric sign:

| Annotation | Condition |
|---|---|
| `@Positive` | Strictly greater than 0. |
| `@PositiveOrZero` | Greater than or equal to 0. |
| `@Negative` | Strictly less than 0. |
| `@NegativeOrZero` | Less than or equal to 0. |

Example:

```java
public record InventoryAdjustment(
        @PositiveOrZero Integer remaining,
        @NegativeOrZero Integer correction
) {}
```

Springdoc can map common numeric constraints to corresponding bounds. Verify the output in `/v3/api-docs`, especially when combining multiple annotations or using special numeric types.

### 4.4. `@Digits` and decimal precision

`@Digits(integer = 6, fraction = 2)` limits the number of digits in the integer and fractional parts. This is a digit-count rule, not quite the same as a `minimum`/`maximum` range.

```java
public record PaymentRequest(
        @Digits(integer = 6, fraction = 2)
        @DecimalMin(value = "0.01")
        BigDecimal amount
) {}
```

When describing precision in OpenAPI, consider `multipleOf` if the rule genuinely corresponds to a numeric step, such as `multipleOf: 0.01` for multiples of one hundredth of a unit. However, `multipleOf` does not fully capture all digit-count limits of `@Digits`, especially for the integer part. Keep runtime validation and add a clear description if the schema cannot express the exact rule.

## 5. Array Sizes

### 5.1. `minItems` and `maxItems`

For arrays, `minItems` is the minimum number of elements and `maxItems` is the maximum number of elements:

```yaml
tags:
  type: array
  minItems: 1
  maxItems: 10
  items:
    type: string
```

Bean Validation `@Size` can be used on Java `Collection`, `Map`, and arrays:

```java
public record ProductRequest(
        @NotEmpty
        @Size(max = 10)
        List<String> tags
) {}
```

`@NotEmpty` requires the collection to be non-null and have at least one element. `@Size(max = 10)` sets the upper bound. Springdoc can express these limits using `minItems`/`maxItems`.

If you need both minimum and maximum counts, you can use `@Size(min = 1, max = 10)`; `@NotEmpty` is then usually unnecessary for size checking, though `null` handling must still be considered. `@Size` allows null, so if the field must be present, combine it with `@NotNull` or `@NotEmpty`.

### 5.2. `uniqueItems`

`uniqueItems: true` requires array elements not to repeat under JSON value comparison:

```yaml
permissions:
  type: array
  uniqueItems: true
  items:
    type: string
```

For example, `['READ', 'WRITE']` is valid, while `['READ', 'READ']` violates uniqueness.

A Java `Set` is not completely equivalent to every case of `uniqueItems`. `Set` depends on the Java type's `equals()`/`hashCode()`; JSON Schema compares JSON values according to schema rules. If using `List`, the server may accept duplicate elements even if OpenAPI documents `uniqueItems: true`, unless runtime validation also checks uniqueness.

Hibernate Validator has the `@UniqueElements` constraint for collections, though this is a Hibernate Validator extension rather than a standard Bean Validation annotation. If used, ensure the dependency is present and check whether springdoc translates that constraint into `uniqueItems` in your project's version. When certainty is needed, declare the schema explicitly and test runtime validation separately.

### 5.3. Constraints on individual elements

An array schema can both limit the number of elements and constrain each item:

```yaml
tags:
  type: array
  minItems: 1
  maxItems: 10
  uniqueItems: true
  items:
    type: string
    minLength: 1
    maxLength: 30
    pattern: '^[a-z0-9-]+$'
```

In Java, use type-use constraints on collection elements:

```java
public record ProductRequest(
        @NotEmpty
        @Size(max = 10)
        List<@NotBlank @Size(max = 30) @Pattern(regexp = "^[a-z0-9-]+$") String> tags
) {}
```

For nested element or nested DTO validation to run, use appropriate cascaded validation, typically `@Valid` on the collection property. Example:

```java
public record OrderRequest(
        @NotEmpty
        @Size(max = 50)
        List<@Valid OrderLineRequest> lines
) {}

public record OrderLineRequest(
        @NotBlank String productCode,
        @Positive Integer quantity
) {}
```

Array bounds and per-element constraints are two distinct layers. `maxItems: 50` does not limit the character count of `productCode`; constraints must be declared on the item or on properties inside the item.

## 6. Declaring Limits Directly with Swagger Annotations

When Bean Validation cannot fully express the desired schema or when extra documentation metadata is needed, use `@Schema` and `@ArraySchema`.

Example for strings:

```java
@Schema(
        description = "Uppercase product code consisting of letters, digits, and hyphens",
        minLength = 5,
        maxLength = 24,
        pattern = "^[A-Z0-9-]+$"
)
private String productCode;
```

Example for arrays:

```java
@ArraySchema(
        minItems = 1,
        maxItems = 10,
        uniqueItems = true,
        schema = @Schema(type = "string", minLength = 1, maxLength = 30)
)
private List<String> tags;
```

Swagger annotations supplement OpenAPI descriptions. They do not replace Bean Validation. Declaring `minLength`, `maximum`, or `uniqueItems` only in annotations without runtime validation means Spring may still accept requests violating those limits.

Avoid declaring the same rule in multiple places with different values. For instance, `@Size(max = 80)` alongside `@Schema(maxLength = 100)` creates documentation that contradicts server behavior. Use one primary source of constraints whenever possible, then inspect the metadata generated by springdoc.

## 7. `required`, `nullable`, and Value Limits Are Three Distinct Concepts

A property can be:

- **Required**: must appear in the JSON object.
- **Nullable**: if present, the value may be `null`.
- **Constrained**: if a value is present, it must satisfy `minLength`, `maximum`, `maxItems`, or other constraints.

For example, `nickname` may be optional, yet if sent must be 2 to 30 characters long:

```yaml
type: object
properties:
  nickname:
    type: string
    minLength: 2
    maxLength: 30
```

Here `nickname` is not in the `required` list, so it may be omitted. If sent, it must still satisfy the length limit. Whether `null` is allowed is a separate rule and depends on the OpenAPI version.

OpenAPI 3.0 typically uses `nullable: true` alongside type to allow null. OpenAPI 3.1 is based on JSON Schema 2020-12 and can use a union type like `type: [string, 'null']`. Do not confuse an omitted field with a null value; in Spring, `@NotNull` and binding/constructor behavior can also affect validation when a field is omitted.

## 8. How Bean Validation Is Converted into Schemas by Springdoc

Springdoc reads model metadata and supported annotations to build schemas. Some common mappings:

| Bean Validation | Commonly Corresponding Schema | Notes |
|---|---|---|
| `@Size(min, max)` on string | `minLength`, `maxLength` | `@Size` also applies to collections/maps/arrays. |
| `@Pattern(regexp)` | `pattern` | Java regex and JSON Schema regex have differences. |
| `@Min`, `@DecimalMin` | `minimum` or exclusive bound | Depends on `inclusive` and OpenAPI version. |
| `@Max`, `@DecimalMax` | `maximum` or exclusive bound | Depends on `inclusive` and OpenAPI version. |
| `@Positive`, `@PositiveOrZero` | Numeric lower bound | Check output with the version in use. |
| `@Negative`, `@NegativeOrZero` | Numeric upper bound | Check output with the version in use. |
| `@NotNull` | Required/non-nullable depending on location and version | Not synonymous with `minLength` or `minItems`. |
| `@NotEmpty` | Required and minimum size on applicable types | Inspect actual schema. |
| `@Digits` | May need supplemental metadata | Not all digit-count limits map cleanly to a single keyword. |

For springdoc to read constraints, the project needs the corresponding Bean Validation dependency, typically `spring-boot-starter-validation` in Spring Boot. If the provider is missing or annotations come from a package not used by the runtime, metadata may not be processed as expected.

For nested DTOs, use `@Valid` to enable cascaded validation at runtime. Springdoc can still read schemas of nested types, but that does not guarantee cascaded validation is enabled.

## 9. Inspecting Generated Schemas

After adding constraints, start the application and read the documentation at `/v3/api-docs` or the configured path. Find the corresponding schema and verify:

1. Is the property type accurately `string`, `integer`, `number`, or `array`?
2. Do `minLength` and `maxLength` match `@Size`?
3. Does `pattern` have the right expression, anchors, and escaping?
4. Do `minimum`/`maximum` have the right bounds and inclusivity/exclusivity?
5. For OpenAPI 3.0/3.1, are exclusive bounds in the format expected for that version?
6. Do `minItems`, `maxItems`, and `uniqueItems` appear properly on the array schema?
7. Are item constraints inside `items` rather than mistakenly placed at the array level?
8. Do required and nullable accurately reflect request requirements?

Example expected output for `CreateProductRequest`:

```yaml
CreateProductRequest:
  type: object
  required:
    - name
    - price
    - tags
  properties:
    name:
      type: string
      minLength: 3
      maxLength: 80
    price:
      type: number
      minimum: 0.01
      maximum: 999999.99
    tags:
      type: array
      minItems: 1
      maxItems: 10
      uniqueItems: true
      items:
        type: string
        minLength: 1
        maxLength: 30
```

This is an illustrative structure. Actual output may use `$ref` for schemas, determine `required` from record/constructor metadata, and represent numeric bounds differently depending on the OpenAPI version.

## 10. Verifying Validation at Runtime

OpenAPI documentation helps clients catch bad data before sending, yet the server must still validate requests. Example:

```java
public record CreateProductRequest(
        @NotBlank
        @Size(min = 3, max = 80)
        String name,

        @NotNull
        @DecimalMin("0.01")
        @DecimalMax("999999.99")
        BigDecimal price,

        @NotEmpty
        @Size(max = 10)
        List<@NotBlank @Size(max = 30) String> tags
) {}
```

Controller:

```java
@PostMapping("/api/products")
ProductResponse create(
        @Valid @RequestBody CreateProductRequest request) {
    return productService.create(request);
}
```

`@Valid` instructs Spring to run Bean Validation on the request body. Errors such as a name that is too short, a negative price, or an empty tag list will produce validation failures. The application should standardize errors into a consistent response, typically `400 Bad Request`, and document that error response in OpenAPI.

### 10.1. Integration test example

With MockMvc, you can verify invalid data is rejected:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProductValidationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsNameShorterThanMinimum() throws Exception {
        mockMvc.perform(post("/api/products")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": "AB",
                                  "price": 10.00,
                                  "tags": ["java"]
                                }
                                """))
                .andExpect(status().isBadRequest());
    }
}
```

This test assumes the application is configured to translate validation errors into HTTP 400. If the application uses a custom error handler, adjust assertions accordingly and verify error response contents.

Include both valid and invalid boundary tests: values equal to minimum, below minimum, strings at maxLength, longer than maxLength, arrays with minimum/maximum element counts, and arrays with duplicate elements when uniqueness is required.

## 11. Common Pitfalls

- **Using `@Size` while forgetting `@NotNull`/`@NotBlank`**: `@Size` allows null; combine constraints according to requiredness.
- **Confusing `maxLength` with byte count**: string length limits are not UTF-8 byte limits or request payload size limits.
- **Using unanchored regexes**: a longer string can contain a matching substring without conforming to the full format.
- **Using Java regex features incompatible with JSON Schema**: prefer common syntax and test with both validators.
- **Confusing inclusive and exclusive bounds**: check `inclusive` on `@DecimalMin`/`@DecimalMax` and the OpenAPI 3.0/3.1 format.
- **Using `@Min` for decimal numbers**: for `BigDecimal`, use `@DecimalMin`/`@DecimalMax`.
- **Constraining only the array without constraining items**: place constraints on `items` or generic elements when needed.
- **Assuming `uniqueItems: true` enforces uniqueness at runtime**: add server-side validation or uniqueness checks.
- **Assuming schema annotations replace Bean Validation**: `@Schema` and `@ArraySchema` only supplement documentation.
- **Not checking output after changing OpenAPI version**: exclusive bounds and nullability change representation between 3.0 and 3.1.

## 12. Workflow for Designing DTO Constraints

1. **Identify data types**: string, integer, decimal number, collection, or array.
2. **Identify business limits**: length, numeric range, regex, element count, uniqueness.
3. **Choose Bean Validation**: `@Size`, `@Pattern`, `@Min`, `@DecimalMin`, `@Positive`, `@NotBlank`, `@NotEmpty`, or custom constraints.
4. **Supplement schema metadata if needed**: use `@Schema`, `@ArraySchema`, or a customizer when constraints are not fully mapped.
5. **Check OpenAPI version**: especially for exclusive bounds and nullability.
6. **Inspect `/v3/api-docs`**: confirm constraints sit on the right property/item with exact values.
7. **Test runtime**: send valid, boundary, and out-of-bounds values; confirm the server rejects invalid data.
8. **Test consumers**: confirm Swagger UI, SDK generators, or validators interpret schemas according to the intended contract.

## 13. Review Checklist

- [ ] `minLength`/`maxLength` match string length limits.
- [ ] `pattern` has anchors when full-string matching is needed and uses compatible regex syntax.
- [ ] `minimum`/`maximum` have accurate values and bound inclusivity.
- [ ] `exclusiveMinimum`/`exclusiveMaximum` match OpenAPI 3.0 or 3.1 syntax.
- [ ] `minItems`/`maxItems` apply at the array level.
- [ ] `uniqueItems` has matching runtime validation if uniqueness is a business requirement.
- [ ] Per-element constraints are placed inside the `items` schema and appropriate type-use validation.
- [ ] Required and nullable are evaluated independently from value limits.
- [ ] Bean Validation provider is present at runtime and `@Valid` is placed properly.
- [ ] `/v3/api-docs` is inspected after changing DTOs or annotations.
- [ ] Integration tests cover valid, boundary, and invalid values.

## 14. References

- [OpenAPI Specification 3.1.2 – Schema Object](https://spec.openapis.org/oas/v3.1.2.html#schema-object)
- [OpenAPI Specification 3.0.4 – Schema Object](https://spec.openapis.org/oas/v3.0.4.html#schema-object)
- [JSON Schema – Validation keywords](https://json-schema.org/draft/2020-12/json-schema-validation)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring Boot – Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [springdoc-openapi FAQ](https://springdoc.org/faq.html)

Schema limits help API consumers understand valid data before sending requests. Declare constraints with Bean Validation so the server enforces them, let springdoc translate them into OpenAPI, and verify both output and runtime at boundary values. When schemas and validation describe the exact same rules, the API contract becomes much more reliable for Swagger UI, SDKs, and integrating systems.
