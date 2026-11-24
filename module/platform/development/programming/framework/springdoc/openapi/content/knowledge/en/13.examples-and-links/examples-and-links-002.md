# Examples at the Parameter, Schema, and Request or Response Level

Examples help API consumers understand the data they need to send or will receive. A schema can accurately describe types, fields, and constraints yet remain hard to understand without illustrative values. With `springdoc-openapi`, you can add examples at multiple levels: parameters, model properties, request bodies, and response bodies.

What matters is placing the example in the right place. A query parameter example describes a value the client sends in the URL; a schema example illustrates a field or model; a request/response content example describes the full payload tied to a media type. These examples are exported into OpenAPI for Swagger UI and other tools to render, but they do not by themselves alter validation or controller behavior.

## 1. Distinguishing schema, example, and default

Three concepts are often confused:

| Component | Answers the question | Example |
| --- | --- | --- |
| Schema | What shape and constraints does the data have? | `email` is a string with format `email`; `quantity` is an integer at least 1. |
| Example | What does a valid sample value look like? | `"support@example.com"`, `3`. |
| Default | What value is used when the client omits it, according to the contract or application behavior? | Query parameter `page` defaults to `0`. |

An example is not a validation rule. If the schema allows `quantity` from 1 to 100 but the illustrative example is `0`, the documentation becomes contradictory. Similarly, setting `example = "PENDING"` does not make the server automatically reject other enum values; the allowed value set must be described by the schema `enum` and enforced by the Java type or appropriate validation.

## 2. Examples at the parameter level

For a simple parameter, you can use `example` in `@Parameter`:

```java
@GetMapping("/api/orders")
List<OrderResponse> search(
    @Parameter(
        description = "Status code to filter by",
        example = "PENDING"
    )
    @RequestParam(required = false) OrderStatus status,

    @Parameter(
        description = "Page number, starting from 0",
        example = "0"
    )
    @RequestParam(defaultValue = "0") @Min(0) int page
) {
    return orderService.search(status, page);
}
```

`example` is an illustrative value for the parameter. Springdoc combines it with metadata inferred from `@RequestParam`, Java types, and other annotations to build the Parameter Object in OpenAPI.

When multiple choices are needed, use `examples` with named `@ExampleObject` entries:

```java
@GetMapping("/api/orders")
List<OrderResponse> search(
    @Parameter(
        name = "status",
        in = ParameterIn.QUERY,
        description = "Order status",
        examples = {
            @ExampleObject(name = "pending", summary = "Pending processing", value = "PENDING"),
            @ExampleObject(name = "shipped", summary = "Handed over to carrier", value = "SHIPPED"),
            @ExampleObject(name = "cancelled", summary = "Cancelled", value = "CANCELLED")
        }
    )
    @RequestParam(required = false) OrderStatus status
) {
    return orderService.searchByStatus(status);
}
```

Each `ExampleObject` can have `name`, `summary`, `description`, and `value`. `name` identifies the example; `summary` helps readers pick the right case; `value` holds the actual value. Named examples are useful when clients have multiple scenarios to test in Swagger UI.

For numeric or date/time parameters, the example value still needs the right wire format:

```java
@Parameter(
    description = "Filter start date, yyyy-MM-dd format",
    example = "2026-11-01"
)
@RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate from
```

Query parameters are passed in the URL as strings, and Spring then converts them to Java types. Therefore, date/time examples must match the format accepted by the application's converter.

## 3. Examples at the schema property level

When you want to illustrate an individual DTO field, use `@Schema(example = "...")`:

```java
public record CreateCustomerRequest(
    @Schema(
        description = "Customer display name",
        example = "Nguyen An",
        minLength = 1,
        maxLength = 100
    )
    @NotBlank @Size(max = 100)
    String displayName,

    @Schema(
        description = "Contact email address",
        example = "an.nguyen@example.com",
        format = "email"
    )
    @NotBlank @Email
    String email,

    @Schema(
        description = "Expected number of orders",
        example = "3",
        minimum = "1",
        maximum = "100"
    )
    @Min(1) @Max(100)
    Integer expectedOrders
) {}
```

Each property's schema gets its type and constraints inferred from Java or annotations. `example` provides an illustrative value within that schema. `@NotBlank`, `@Email`, `@Min`, and `@Max` are the validation constraints actually enforced when Bean Validation is enabled in the application.

Field-level examples work well when a property has an easily misunderstood format or needs a quick hint. They do not replace a complete request body example: readers may still need to see how fields fit together in a payload.

## 4. Examples for the entire request body

When you want to provide multiple sample payloads for the same operation, declare `examples` inside `@Content`. You can place the OpenAPI request body directly inside `@Operation`:

```java
@PostMapping("/api/customers")
@Operation(
    summary = "Create customer",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        description = "Customer information to create",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateCustomerRequest.class),
            examples = {
                @ExampleObject(
                    name = "individual",
                    summary = "Individual customer",
                    description = "Create a customer with a display name and contact email",
                    value = """
                        {
                          "displayName": "Nguyen An",
                          "email": "an.nguyen@example.com",
                          "expectedOrders": 3
                        }
                        """
                ),
                @ExampleObject(
                    name = "support-contact",
                    summary = "Support contact account",
                    value = """
                        {
                          "displayName": "Support Team",
                          "email": "support@example.com",
                          "expectedOrders": 10
                        }
                        """
                )
            }
        )
    )
)
ResponseEntity<CustomerResponse> create(
    @Valid @RequestBody CreateCustomerRequest request
) {
    CustomerResponse created = customerService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
```

Here:

- `mediaType` specifies that the examples apply to JSON content.
- `schema` indicates the request body shape is `CreateCustomerRequest`.
- `examples` holds multiple named scenarios for users to choose from.
- `summary` and `description` explain the meaning of each payload.
- `value` is the sample JSON; fields and values must match the schema.

The `RequestBody` annotation name is written in full to distinguish it from `org.springframework.web.bind.annotation.RequestBody` used on the controller parameter. The OpenAPI annotation only describes the request body; the Spring parameter annotation actually receives and deserializes the payload.

If you only need one simple example, you can use `example` on `@Content` or `@Schema` depending on the level. When there are multiple scenarios, prefer `examples` to name and describe each case. Do not declare both `example` and `examples` for the same media type if they express different content, as rendering tools may cause confusion.

## 5. Examples for the response body

A response can also have multiple examples, such as a newly created customer and a customer created from an import source:

```java
@PostMapping("/api/customers")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Customer created",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CustomerResponse.class),
            examples = {
                @ExampleObject(
                    name = "created",
                    summary = "New customer",
                    value = """
                        {
                          "id": "4f1b8a22-0c6a-4c8e-9b47-cc3d40f32e10",
                          "displayName": "Nguyen An",
                          "email": "an.nguyen@example.com",
                          "status": "ACTIVE"
                        }
                        """
                ),
                @ExampleObject(
                    name = "imported",
                    summary = "Customer imported from another system",
                    value = """
                        {
                          "id": "aa08b2b6-18d0-4d73-b2e4-6c8d1a8e1f50",
                          "displayName": "Support Team",
                          "email": "support@example.com",
                          "status": "PENDING_REVIEW"
                        }
                        """
                )
            }
        )
    )
})
ResponseEntity<CustomerResponse> create(
    @Valid @RequestBody CreateCustomerRequest request
) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(customerService.create(request));
}
```

The response examples sit inside `content` for status code `201`. If the endpoint has multiple response codes, each code can have its own schema and examples. A `400` error example should describe the error response rather than reusing a success payload.

Error example:

```java
@ApiResponse(
    responseCode = "400",
    description = "Invalid input data",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ApiError.class),
        examples = @ExampleObject(
            name = "invalid-email",
            summary = "Invalid email format",
            value = """
                {
                  "code": "VALIDATION_FAILED",
                  "message": "Request validation failed",
                  "fieldErrors": [
                    {"field": "email", "message": "must be a well-formed email address"}
                  ]
                }
                """
        )
    )
)
```

Do not put sensitive information or real personal data into response examples. Use synthetic data that has a realistic shape without identifying real users.

## 6. External examples with `externalValue`

For large payloads or examples shared across multiple documents, you can reference an external example file using `externalValue`:

```java
@Content(
    mediaType = MediaType.APPLICATION_JSON_VALUE,
    schema = @Schema(implementation = BulkImportRequest.class),
    examples = @ExampleObject(
        name = "large-import",
        summary = "Bulk data import example",
        externalValue = "https://docs.example.com/openapi/examples/bulk-import.json"
    )
)
```

`externalValue` is a URI pointing to the example content. According to the OpenAPI Example Object, an example uses either `value` or `externalValue`; do not use both to describe two different payloads in the same object. The external path must be kept stable and accessible to the documentation viewing tool. Some UIs only show a link or do not fetch external examples, depending on their implementation.

For small files, short data, and examples that should stay bundled with the specification, using `value` is usually more convenient. For very long payloads, binary data, or examples shared across multiple APIs, external references can keep the specification concise.

## 7. Examples for different media types

An operation can accept multiple content formats. For example, an import API supporting JSON and XML. Each media type has its own schema and examples:

```java
@PostMapping(
    path = "/api/imports",
    consumes = {MediaType.APPLICATION_JSON_VALUE, MediaType.APPLICATION_XML_VALUE}
)
@Operation(
    summary = "Import data",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = {
            @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = ImportRequest.class),
                examples = @ExampleObject(
                    name = "json-import",
                    value = "{\"source\":\"warehouse\",\"count\":12}"
                )
            ),
            @Content(
                mediaType = MediaType.APPLICATION_XML_VALUE,
                schema = @Schema(implementation = ImportRequest.class),
                examples = @ExampleObject(
                    name = "xml-import",
                    value = "<importRequest><source>warehouse</source><count>12</count></importRequest>"
                )
            )
        }
    )
)
ResponseEntity<ImportResponse> importData(@RequestBody ImportRequest request) {
    return ResponseEntity.accepted().body(importService.importData(request));
}
```

The JSON and XML examples represent the same data but use different syntax. The application will only actually accept both formats if the corresponding message converters are present and `consumes` is configured properly. Declaring two `@Content` entries in OpenAPI does not automatically add an XML converter or make the controller support XML.

## 8. Examples for headers or parameter objects

`@ExampleObject` can also be used inside `@Parameter` for header, cookie, or path parameters. For example, the `X-Client-Version` header:

```java
@GetMapping("/api/profile")
ProfileResponse getProfile(
    @Parameter(
        name = "X-Client-Version",
        in = ParameterIn.HEADER,
        description = "Client application version",
        examples = {
            @ExampleObject(name = "android", value = "5.4.0"),
            @ExampleObject(name = "ios", value = "5.3.2")
        }
    )
    @RequestHeader("X-Client-Version") String clientVersion
) {
    return profileService.getProfile(clientVersion);
}
```

Examples on a parameter object help Swagger UI suggest values when trying out requests. For response headers, use `@Header` inside `@ApiResponse` to describe headers returned by the server; do not use `@Parameter(in = HEADER)` for response headers.

## 9. Choosing where to declare examples

| Need | Appropriate annotation or location | Example scope |
| --- | --- | --- |
| One value for a query/path/header parameter | `@Parameter(example = "...")` | One parameter. |
| Multiple choices for a parameter | `@Parameter(examples = @ExampleObject(...))` | Values of a parameter. |
| One field in a DTO | `@Schema(example = "...")` | One schema property. |
| One request payload | `@Content(examples = @ExampleObject(...))` inside OpenAPI RequestBody | One request media type. |
| One response payload | `@Content(examples = @ExampleObject(...))` inside `@ApiResponse` | One response code and media type. |
| Example stored in an external file | `@ExampleObject(externalValue = "...")` | One example referencing an external URI. |

Do not place a complete payload into `@Parameter.example` if the endpoint actually expects a JSON body. Conversely, do not use `@Schema(example)` on a single field as a substitute for a whole-object example when clients need to see relationships across multiple fields.

## 10. Verifying examples in OpenAPI and Swagger UI

After adding examples, inspect the generated specification rather than relying solely on annotations in the source:

1. Start the application and open `/v3/api-docs` or the configured documentation endpoint.
2. Locate the operation under `paths`; inspect `parameters`, `requestBody.content`, and `responses`.
3. For parameters, confirm `example` or the `examples` entries appear under the right parameter.
4. For models, open `components.schemas` and verify property examples alongside schema types/formats.
5. For requests/responses, confirm examples sit under the right media type and example names do not collide within the same scope.
6. Open Swagger UI, select each example, and verify the displayed payload is correct.
7. Use **Try it out** to send the request; check that the server actually accepts the payload under existing validation and converters.
8. If using `externalValue`, try opening the URI from the documentation reader's environment and verify the content still exists.

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Swagger UI shows only one example | Using single `example` instead of `examples`, or UI version does not render a list | Check `/v3/api-docs` and use named `@ExampleObject` entries. |
| Example does not appear on parameter | Placed `@ExampleObject` inside `@Content` instead of `@Parameter`, or vice versa | Place the example according to Parameter Object vs. Media Type Object. |
| Request body example cannot be selected in Try it out | Example was only put in field `@Schema` or description | Declare `examples` inside `@Content` of the request body. |
| Example does not match server-accepted payload | Schema, converter, enum, or validation differs from the example | Align DTO, schema, converter, and runtime constraints. |
| Invalid JSON example | `value` string has syntax errors or missing escapes | Inspect the JSON after decoding from `/v3/api-docs`. |
| `externalValue` fails to load | Wrong URI, deleted file, or tool does not support external loading | Use a stable URI, check access permissions, or embed `value`. |
| Example for XML but endpoint returns 415 | Application lacks an XML message converter or `consumes` mismatches | Configure converters and test actual HTTP requests. |

## 11. Guidelines for applying examples

- Use `@Parameter(example = ...)` for a single parameter value and `@Parameter(examples = ...)` for multiple cases.
- Use `@Schema(example = ...)` to illustrate a field or model.
- Use `@Content(examples = ...)` to provide request/response payloads per media type.
- Name and describe `@ExampleObject` entries so readers know when to choose each example.
- Ensure all examples comply with the schema, enums, formats, and runtime constraints.
- Use `externalValue` for large or shared payloads; maintain stable URIs.
- Check `/v3/api-docs`, Swagger UI, and real requests after updating examples.

Good examples clarify how to use an API with concrete data. Placing examples at the right level tells clients the value of each parameter, the meaning of each field, and the structure of the complete payload. Springdoc converts these annotations into OpenAPI Example Objects; the application must still ensure that schemas, converters, and validation accept the published data.

## References

- [OpenAPI Specification – Example Object and Media Type Object](https://spec.openapis.org/oas/latest.html)
- [Swagger Annotations – `@ExampleObject`, `@Content`, `@Parameter`, and `@Schema`](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
- [Springdoc OpenAPI – Official Documentation](https://springdoc.org/)
- [Swagger UI – Using and Displaying Examples](https://swagger.io/docs/open-source-tools/swagger-ui/usage/)
