# Schemas for Numeric, Boolean, String, Enum, and Date/Time Parameters

When springdoc-openapi inspects Spring controllers, the library infers most parameter data types from Java types and Spring MVC metadata. An `Integer` parameter typically becomes an `integer` schema, `Boolean` becomes `boolean`, `String` becomes `string`, and an enum type is represented with its list of allowed values. Date/time types can be represented as strings with an appropriate `format`.

Schemas help clients understand what data to send and enable tools like Swagger UI to render parameters with the right types. However, a schema is a description in the OpenAPI contract. Spring MVC remains responsible for converting HTTP strings into Java types; Bean Validation checks runtime constraints; Jackson handles JSON data in request bodies and responses. Accurate documentation requires keeping all three aligned.

## 1. Schemas Inferred from Java Types

OpenAPI uses several primitive data types to describe parameters and properties:

| Common Java Type | Typically Generated OpenAPI Type | Meaning |
| --- | --- | --- |
| `byte`, `short`, `int`, `Integer` | `integer`, typically `int32` | 32-bit integer. |
| `long`, `Long` | `integer`, typically `int64` | 64-bit integer. |
| `BigInteger` | `integer`, format may be omitted | Arbitrary-precision integer; should not default to `int64` range limits. |
| `float`, `Float` | `number`, `float` | Single-precision floating-point number. |
| `double`, `Double` | `number`, `double` | Double-precision floating-point number. |
| `BigDecimal` | `number` | High-precision decimal number, suitable for currency and financial calculations. |
| `boolean`, `Boolean` | `boolean` | True or false value. |
| `String`, `char`, `Character` | `string` | Text or character. |
| `UUID` | `string`, `uuid` | UUID identifier. |
| Java `enum` | `string` with value list | A value chosen from a set of constants. |
| `LocalDate` | `string`, `date` | Calendar date without time or time zone. |
| `OffsetDateTime`, `Instant`, `Date` | `string`, typically `date-time` | Point in time expressible in standard date-time format with offset or UTC. |

This is a common mapping, not an immutable rule for every custom type. Jackson modules, custom converters, annotations, and Springdoc versions can affect how data is described. Inspect the actual JSON specification whenever data types are critical to the contract.

## 2. Numeric Parameters: integer and number

OpenAPI distinguishes `integer` from `number`. `format` helps describe common bit widths or precision:

- `integer` with `int32`: 32-bit integer, typically corresponding to Java `int` or `Integer`.
- `integer` with `int64`: 64-bit integer, typically corresponding to Java `long` or `Long`.
- `number` with `float` or `double`: floating-point numbers.
- `number` without a specific format: can be used for `BigDecimal` or decimal numbers not tied to binary precision.

Example controller searching products by price range:

```java
@RestController
@RequestMapping("/api/products")
@Validated
class ProductController {

    @GetMapping
    List<ProductResponse> search(
        @Parameter(description = "Minimum price", example = "100000")
        @RequestParam(required = false)
        @DecimalMin("0.00")
        BigDecimal minPrice,

        @Parameter(description = "Maximum price", example = "5000000")
        @RequestParam(required = false)
        @DecimalMin("0.00")
        BigDecimal maxPrice,

        @Parameter(description = "Maximum number of results", example = "50")
        @RequestParam(defaultValue = "20")
        @Min(1) @Max(100)
        Integer limit
    ) {
        return productService.search(minPrice, maxPrice, limit);
    }
}
```

For numeric parameters, springdoc can infer types from `BigDecimal` or `Integer`; `@Parameter` adds descriptions and examples; constraints like `@DecimalMin`, `@Min`, and `@Max` can be reflected as schema limits when Bean Validation is recognized. `@RequestParam`'s `defaultValue` is the value Spring MVC uses when the client omits the parameter; it also affects whether the parameter is required.

If you need to add limits or metadata purely for documentation, you can nest `@Schema` inside `@Parameter`:

```java
@Parameter(
    description = "Number of records per page",
    example = "25",
    schema = @Schema(minimum = "1", maximum = "100", defaultValue = "25")
)
@RequestParam(defaultValue = "25")
Integer size
```

`@Schema(minimum = "1")` documents the limit in OpenAPI. For the server to actually reject values below 1, you need runtime constraints like `@Min(1)` with method validation enabled. Do not rely solely on documentation to safeguard input data.

For monetary amounts, prefer `BigDecimal` over `float` or `double` to avoid binary floating-point rounding errors. Explicitly document the unit in the description, such as VND, USD, or the smallest currency unit. `minimum` and `maximum` must match the unit the API accepts.

## 3. Boolean: true, false, and Default Values

`boolean` or `Boolean` types are represented as a `boolean` schema. For query parameters, clients typically pass `true` or `false` in the URL:

```java
@GetMapping("/api/products")
List<ProductResponse> search(
    @Parameter(description = "Only fetch active products", example = "true")
    @RequestParam(defaultValue = "false")
    boolean active
) {
    return productService.findByActive(active);
}
```

Sample request:

```http
GET /api/products?active=true
```

With primitive `boolean`, Java always holds either `true` or `false`; it cannot represent `null`. With `Boolean`, the application can distinguish three states: `true`, `false`, and `null` when the parameter is declared optional without a default value. This distinction is useful if `null` means "do not filter by status".

Avoid strings like `yes/no`, `1/0`, or `on/off` unless the endpoint has a dedicated converter. Publish the exact format clients must send and test how Spring converts real values.

## 4. String: Length, Pattern, and Format

`String` is typically represented as a `string` schema. Commonly used constraints include:

- `minLength` and `maxLength`: length bounds.
- `pattern`: regular expression the value must match.
- `format`: meaningful formats such as `email`, `uuid`, `uri`, `date`, or `date-time`.
- `example`: illustrative value so readers understand the format.

Example customer code parameters:

```java
@GetMapping("/api/customers")
List<CustomerResponse> find(
    @Parameter(
        description = "Email address to search for",
        example = "support@example.com",
        schema = @Schema(format = "email", maxLength = 254)
    )
    @RequestParam(required = false)
    @Email @Size(max = 254)
    String email,

    @Parameter(
        description = "Reference code consisting of 6 to 12 alphanumeric characters",
        example = "CUS8A21",
        schema = @Schema(minLength = 6, maxLength = 12, pattern = "^[A-Za-z0-9]+$")
    )
    @RequestParam(required = false)
    @Size(min = 6, max = 12) @Pattern(regexp = "^[A-Za-z0-9]+$")
    String reference
) {
    return customerService.find(email, reference);
}
```

Here, `@Schema` publishes format and bounds; `@Email`, `@Size`, and `@Pattern` are validation constraints. Constraints only execute if a validation provider and method validation are configured. Moreover, `@Email` may accept a wide variety of addresses depending on the validator; if the contract requires stricter rules, use an intentional pattern and test it.

Do not invent arbitrary `format` values. OpenAPI allows custom formats, but client generators reliably understand only a set of common formats. When a format is not a standard one recognized by tools, explain it clearly via `description`, `pattern`, and examples.

## 5. Enum: Publishing Allowed Value Sets

When a Java parameter uses an enum, springdoc typically generates a string schema containing the corresponding list of values. Example:

```java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}
```

```java
@GetMapping("/api/orders")
List<OrderResponse> findByStatus(
    @Parameter(description = "Order status", example = "PENDING")
    @RequestParam(required = false)
    OrderStatus status
) {
    return orderService.findByStatus(status);
}
```

The schema typically looks like:

```yaml
type: string
enum:
  - PENDING
  - CONFIRMED
  - SHIPPED
  - CANCELLED
```

Enums reduce typos and create dropdown choices in Swagger UI. However, accepted values depend on how Spring converts parameters and how Jackson is configured for bodies. If the application uses custom converters, `@JsonValue`, or custom enum serialization, ensure the schema lists the exact wire-format values the API actually accepts or returns.

For a `String` parameter that only accepts a fixed set of values, you can declare `allowableValues` or `@Schema(allowableValues = {...})`. However, if the values form a stable domain concept, a Java enum helps avoid repeating the list across multiple places.

## 6. Dates and Times: Choosing the Right Data Type and Format

Dates and times can easily cause confusion because Java types may or may not include time zones. OpenAPI typically uses strings with a format:

| Java Type | Common API Representation | Notes |
| --- | --- | --- |
| `LocalDate` | `type: string`, `format: date` | Calendar date, e.g. `2026-11-20`; no time or time zone. |
| `LocalTime` | `type: string`, usually describing local time | Contains no date or time zone; format conventions must be agreed across the API. |
| `LocalDateTime` | Local date-time string; may be inferred as `date-time` depending on integration | Has no offset; cannot uniquely identify a global instant. If generated schema uses `date-time`, description must clarify it is local time. |
| `OffsetDateTime` | `type: string`, `format: date-time` | Includes offset, e.g. `2026-11-20T09:30:00+07:00`. |
| `Instant` | `type: string`, `format: date-time` | UTC instant, usually with `Z` suffix. |
| `Date` | Typically `type: string`, `format: date-time` | Serialization depends on Jackson and application configuration. |

Example filtering by creation date:

```java
@GetMapping("/api/orders")
List<OrderResponse> findCreatedAfter(
    @Parameter(
        description = "Start date, format yyyy-MM-dd",
        example = "2026-11-01",
        schema = @Schema(type = "string", format = "date")
    )
    @RequestParam
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    LocalDate from
) {
    return orderService.findCreatedAfter(from);
}
```

For instants requiring an explicit time zone, prefer `OffsetDateTime` or `Instant`:

```java
@GetMapping("/api/events")
List<EventResponse> findEvents(
    @Parameter(
        description = "Start timestamp in ISO 8601 with time zone offset",
        example = "2026-11-20T09:30:00+07:00",
        schema = @Schema(type = "string", format = "date-time")
    )
    @RequestParam
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
    OffsetDateTime from
) {
    return eventService.findFrom(from);
}
```

`@DateTimeFormat` guides Spring in converting query, path, or form parameters into Java date/time types. For JSON request/response bodies, Jackson performs serialization and deserialization; `ObjectMapper` configuration, the Java Time module, and `@JsonFormat` can affect JSON formatting. `@Schema(format = "date-time")` only publishes the format in documentation; it does not configure parsers or serializers.

Do not attach `format: date-time` to `LocalDateTime` and assume clients will understand the time zone. That type carries no offset. If the API represents a global instant, pick a type with an offset/UTC and state the time zone rule clearly. If business logic genuinely uses local time, document the applicable time zone, such as the store's or location's time zone.

## 7. Combining Schema, Requiredness, and Default Values

Data type and requiredness are two separate concepts. For example, `Integer` can be a mandatory or optional parameter depending on how it is declared in Spring MVC:

```java
@GetMapping("/api/products/{id}")
ProductResponse get(
    @PathVariable UUID id,
    @RequestParam(required = false) Boolean includeInactive,
    @RequestParam(defaultValue = "0") @Min(0) Integer page
) {
    return productService.get(id, includeInactive, page);
}
```

- `id` is a path parameter, so it is required by URL structure.
- `includeInactive` is an optional query parameter; when omitted, Spring can bind `null`.
- `page` has default value `0`; Spring uses this value when the client omits the parameter.

In OpenAPI, `required` specifies whether the client must send the parameter; `schema` describes the value's type and constraints. `default` is a published or contextually used default value, not a validation mechanism. Do not confuse schema `nullable` with parameter `required`: a parameter can be optional while a required parameter can still have a schema disallowing null values.

## 8. Customizing Schemas When Automatic Inference Is Insufficient

Normally, let springdoc infer types from Java. Override `@Schema` only when you need to express details that Java types or Spring annotations do not capture fully:

```java
@Parameter(
    name = "trackingCode",
    description = "Tracking code consisting of exactly 10 digits",
    required = true,
    example = "0123456789",
    schema = @Schema(
        type = "string",
        minLength = 10,
        maxLength = 10,
        pattern = "^[0-9]{10}$"
    )
)
@RequestParam String trackingCode
```

In this example, the tracking code is kept as `string` even though it consists solely of digits. If documented as `integer`, clients might strip leading zeros or convert to numbers, altering the identifier value. Choose the schema based on data semantics, not merely character appearance.

When customizing, maintain consistency across:

- The Java type received by the controller.
- Conversion rules of Spring MVC or Jackson.
- Runtime constraints enforced by the server.
- `type`, `format`, `enum`, `pattern`, `minimum`, `maximum`, `minLength`, and `maxLength` in OpenAPI.

If the schema says a parameter is numeric while the controller accepts a specifically formatted string, Swagger UI and client generators may build invalid requests. If the schema publishes limits that the server does not check, clients will trust an unenforced contract.

## 9. Verifying Generated Schemas

After adding or changing parameters, verify both the specification and HTTP behavior:

1. Start the application and open `/v3/api-docs` or the configured URL.
2. Locate the operation in `paths`, open `parameters`, and check `name`, `in`, `required`, `schema.type`, `schema.format`, `enum`, `minimum`, `maximum`, `pattern`, and `example`.
3. Open Swagger UI and confirm input controls and enum lists display properly.
4. Send valid values to verify Spring converts them to the right Java types.
5. Send invalid types, out-of-range values, invalid enums, or malformed date/time formats; verify the server returns appropriate errors.
6. For date/time values, inspect offsets or UTC in requests and responses to avoid time shifts across deployments in different time zones.

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Numeric parameter lacks limits in schema | Constraint not recognized or missing metadata | Check Bean Validation and add `@Schema` if needed. |
| Swagger UI accepts plain string when API expects enum | Parameter declared as `String` without publishing allowable values | Use a Java enum or declare `allowableValues`. |
| Date/time fails to parse | Sent format mismatches Spring converter or Jackson config | Distinguish query parameters from JSON bodies; check `@DateTimeFormat` and `@JsonFormat`. |
| Timestamp shifted by hours | Using offset-less type or serializing with environment timezone | Use `Instant`/`OffsetDateTime` and standardize UTC/offset rules. |
| Identifier drops leading zeros | Identifier documented with a numeric schema | Use `string` with appropriate pattern/length. |
| Docs say optional but server reports missing parameter | `required` in mapping mismatches metadata or default value | Check `@RequestParam`, `@PathVariable`, and schemas in `/v3/api-docs`. |

## 10. Guidelines for Application

- Let springdoc infer schemas from Java types first; customize only when the contract needs extra formats or constraints.
- Use numeric types suited to the value domain; prefer `BigDecimal` for currency and `String` for identifiers that may have leading zeros.
- Use Java enums for fixed value sets and ensure schemas match how Spring/Jackson converts values.
- Use `LocalDate` for calendar dates; use `OffsetDateTime` or `Instant` when an explicit timezone point in time is needed.
- Keep `@Schema` metadata separate from data conversion and runtime validation.
- Inspect `/v3/api-docs`, Swagger UI, and real requests whenever changing parameter types.

A good schema accurately describes the values an API accepts and returns. Springdoc helps automate documentation from Java types, yet developers must still clearly define formats, units, value ranges, and time zone rules so clients can integrate accurately.

## References

- [OpenAPI Specification – Data Types and Formats](https://spec.openapis.org/oas/latest.html)
- [Springdoc OpenAPI – Official Documentation](https://springdoc.org/)
- [Swagger Annotations – Schema and Parameter annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
- [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
