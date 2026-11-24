# @ExampleObject and Multiple Examples for a Content Type

A schema describes the structure of data that an API accepts or returns, but integrators often need to see concrete payloads to understand how to populate fields, combine values, and represent different scenarios. OpenAPI supports declaring a single example or multiple examples for the same media type. With springdoc-openapi, the `@ExampleObject` annotation lets you attach named examples, summaries, and values directly to a request body, response, or parameter.

Helpful examples help readers understand the contract faster, while also enabling Swagger UI to display sample payloads for testing the API. However, examples only illustrate usage; they do not replace the schema, enforce validation, or change the data that the controller processes.

## 1. Distinguishing schema and example

A schema answers the question of what structure and constraints the data has. An example answers the question of what a concrete payload looks like.

| Component | Purpose | Example |
| --- | --- | --- |
| Schema | Describes types, fields, required fields, and constraints | quantity is an integer greater than 0 |
| Example | Illustrates a concrete value | {"sku":"KB-01","quantity":2} |
| Description | Explains meaning and conventions | sku is the product code in the catalog |

A single schema can have multiple valid examples. For example, for the same `CreateOrderRequest` schema, we can illustrate a single-item order, a multi-item order, or an order with a delivery note. All examples follow the same structure while clarifying different usage scenarios.

Schema example:

~~~yaml
CreateOrderRequest:
  type: object
  required: [customerId, items]
  properties:
    customerId:
      type: string
    items:
      type: array
      minItems: 1
      items:
        type: object
        required: [sku, quantity]
        properties:
          sku:
            type: string
          quantity:
            type: integer
            minimum: 1
    deliveryNote:
      type: string
~~~

Valid example according to the schema:

~~~json
{
  "customerId": "C-100",
  "items": [
    {"sku": "KB-01", "quantity": 2}
  ],
  "deliveryNote": "Deliver during business hours"
}
~~~

If an example contains `quantity: 0` while the schema specifies `minimum: 1`, the documentation becomes contradictory. Therefore, check examples alongside the schema and runtime validation.

## 2. Example Object in OpenAPI

OpenAPI uses the Example Object to store information about an example. Commonly used fields include:

| Field | Meaning |
| --- | --- |
| summary | Short title of the example |
| description | More detailed explanation; Markdown may be used depending on tool support |
| value | Example value embedded directly in the specification |
| externalValue | URL pointing to external example content |
| $ref | Reference to an Example Object defined elsewhere |

At the Media Type Object level, OpenAPI has two options:

- example: a single example.
- examples: a map of multiple Example Objects, each with its own key.

Do not declare both `example` and `examples` in the same Media Type Object. When you need multiple payloads for the same media type, use `examples`.

Example:

~~~yaml
content:
  application/json:
    schema:
      $ref: '#/components/schemas/CreateOrderRequest'
    examples:
      singleItem:
        summary: Single-item order
        value:
          customerId: C-100
          items:
            - sku: KB-01
              quantity: 2
      multipleItems:
        summary: Multi-item order
        value:
          customerId: C-200
          items:
            - sku: KB-01
              quantity: 1
            - sku: MS-02
              quantity: 3
~~~

The keys `singleItem` and `multipleItems` are identifier names in the `examples` map. They help Swagger UI or other tools distinguish between choices.

## 3. Declaring multiple examples for a request body using @ExampleObject

With springdoc-openapi, you can use `@Operation`, `@Content`, and `@ExampleObject` to describe multiple payloads for the same request media type.

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@Operation(
    summary = "Create order",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Order information to create",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateOrderRequest.class),
            examples = {
                @ExampleObject(
                    name = "singleItem",
                    summary = "Single-item order",
                    description = "Used when the customer buys only one item.",
                    value = "{\"customerId\":\"C-100\",\"items\":[{\"sku\":\"KB-01\",\"quantity\":2}]}"
                ),
                @ExampleObject(
                    name = "multipleItems",
                    summary = "Multi-item order",
                    description = "Illustrates an items list containing multiple elements.",
                    value = "{\"customerId\":\"C-200\",\"items\":[{\"sku\":\"KB-01\",\"quantity\":1},{\"sku\":\"MS-02\",\"quantity\":3}]}"
                )
            }
        )
    )
)
@PostMapping(
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

In the code snippet above, there are two annotations with the same simple name `RequestBody`:

- `org.springframework.web.bind.annotation.RequestBody` placed on the controller parameter so Spring reads the HTTP body.
- `io.swagger.v3.oas.annotations.parameters.RequestBody` inside `@Operation` to describe the request body in OpenAPI.

The example uses the fully qualified name for the OpenAPI annotation to avoid importing the wrong one. If you use imports, make sure to use the corresponding package.

The `name` attribute of `@ExampleObject` becomes the key in the `examples` map; it is not a property name in the JSON. `summary` and `description` help the reader pick the right example. `value` holds the sample payload as a string inside the annotation, so the JSON must have double quotes and backslashes escaped according to Java syntax.

These examples apply only to `application/json`. They do not automatically make the endpoint accept XML, form, or multipart data. The controller mapping and message converters must still support the declared media type.

## 4. Multiple examples for a response

You can attach multiple examples to the response of a status code. This is useful when the response shares the same schema but has different values, such as an order that is newly created, processing, or delivered.

~~~java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;

@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Order created",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class),
            examples = {
                @ExampleObject(
                    name = "created",
                    summary = "Newly created order",
                    value = "{\"id\":\"O-100\",\"status\":\"CREATED\",\"total\":398000}"
                ),
                @ExampleObject(
                    name = "accepted",
                    summary = "Order accepted",
                    value = "{\"id\":\"O-101\",\"status\":\"ACCEPTED\",\"total\":125000}"
                )
            }
        )
    )
})
~~~

This annotation block can be placed on the controller method. Each example must conform to `OrderResponse`; if `status` is an enum, the values must match the published enum. Response examples also do not alter the actual object returned by the method.

Examples can also be used to illustrate errors:

~~~java
@ApiResponse(
    responseCode = "400",
    description = "Invalid request data",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ApiError.class),
        examples = {
            @ExampleObject(
                name = "missingField",
                summary = "Missing required field",
                value = "{\"code\":\"INVALID_REQUEST\",\"message\":\"customerId is required\"}"
            ),
            @ExampleObject(
                name = "invalidQuantity",
                summary = "Invalid quantity",
                value = "{\"code\":\"INVALID_QUANTITY\",\"message\":\"quantity must be greater than 0\"}"
            )
        }
    )
)
~~~

Error examples help clients understand the error response structure and the error codes that may appear. Make sure they match the actual exception handler and status codes.

## 5. Multiple examples for a parameter

`@ExampleObject` can also describe sample values for a query parameter or header parameter. Use `@Parameter(examples = ...)` when you want to provide several options or API call scenarios.

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.ExampleObject;

@GetMapping
List<OrderResponse> search(
    @Parameter(
        name = "status",
        in = ParameterIn.QUERY,
        description = "Filter by order status",
        examples = {
            @ExampleObject(name = "created", summary = "New order", value = "CREATED"),
            @ExampleObject(name = "shipping", summary = "Shipping", value = "SHIPPING"),
            @ExampleObject(name = "completed", summary = "Completed", value = "COMPLETED")
        }
    )
    @RequestParam(name = "status", required = false) OrderStatus status
) {
    return orderService.search(status);
}
~~~

Parameter examples are values of the parameter itself, not JSON objects. If the parameter is an enum, the sample values should match the enum or converter that the server accepts.

For query parameters, also distinguish between `example`/`examples` of the OpenAPI Parameter Object and examples in the Schema Object. `@Parameter` describes the parameter at the operation level; `@Schema` describes the data type of the value.

## 6. One media type with multiple examples; multiple media types with their own example sets

Each entry in `content` can have its own schema and examples. For example, an endpoint accepting both JSON and XML:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
      examples:
        standard:
          summary: Standard JSON payload
          value:
            customerId: C-100
            items:
              - sku: KB-01
                quantity: 2
    application/xml:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
      examples:
        standard:
          summary: Standard XML payload
          value: |
            <createOrderRequest>
              <customerId>C-100</customerId>
              <items>
                <item><sku>KB-01</sku><quantity>2</quantity></item>
              </items>
            </createOrderRequest>
~~~

JSON and XML examples must be valid representations of their respective media types. A JSON object cannot be used as-is as an XML example. Each media type has its own `examples` map, even if the schemas reference the same component.

In annotations, you can declare multiple `@Content` entries inside the `content` array of a request body or response. Each `@Content` holds its media type, schema, and corresponding `@ExampleObject` entries. The controller's `consumes` must match the request formats that the server actually supports.

## 7. Distinguishing @ExampleObject from @Schema(example = ...)

`@Schema(example = "...")` and `@ExampleObject` have different scopes:

| Declaration | Scope | When to use |
| --- | --- | --- |
| @Schema(example = "...") | A single sample value attached to a schema/property | Want to illustrate one field or one schema |
| @Content(example = "...") | A single example for a media type | Only need one sample payload at the content level |
| @Content(examples = {...}) | Multiple Example Objects for a media type | Want readers to choose among multiple payloads |
| @Parameter(examples = {...}) | Multiple examples for a parameter | Want to illustrate different query/header values |

Schema property example:

~~~java
public record ProductRequest(
    @Schema(
        description = "Product code",
        example = "KB-01"
    )
    String sku
) {}
~~~

A property-level example helps readers understand a single value. It cannot express multiple complete request scenarios such as `singleItem` and `multipleItems`.

In the OpenAPI Media Type Object, `example` and `examples` are mutually exclusive. Once you use `@Content(examples = {...})`, you should not simultaneously set a single `example` for the same content. With OpenAPI 3.1, the Schema Object also has the `examples` keyword from JSON Schema; this is a different location from the `examples` map of the Media Type Object. Check the exact level in JSON/YAML to avoid confusion.

## 8. Reusing examples via components.examples

When the same sample payload is used across multiple operations, you can define shared examples under `components.examples` and reference them using `$ref`.

~~~yaml
components:
  examples:
    StandardOrder:
      summary: Standard order
      description: Order with one product and quantity equal to two.
      value:
        customerId: C-100
        items:
          - sku: KB-01
            quantity: 2
    OrderWithoutNote:
      summary: Order without delivery note
      value:
        customerId: C-200
        items:
          - sku: MS-02
            quantity: 1

paths:
  /api/orders:
    post:
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
            examples:
              standard:
                $ref: '#/components/examples/StandardOrder'
              withoutNote:
                $ref: '#/components/examples/OrderWithoutNote'
~~~

With annotations, you can reference an existing component example:

~~~java
@Content(
    mediaType = "application/json",
    schema = @Schema(implementation = CreateOrderRequest.class),
    examples = {
        @ExampleObject(
            name = "standard",
            ref = "#/components/examples/StandardOrder"
        ),
        @ExampleObject(
            name = "withoutNote",
            ref = "#/components/examples/OrderWithoutNote"
        )
    }
)
~~~

Referenced components must actually exist in the OpenAPI document. You can create them through an `OpenAPI` model bean or customizer; merely writing a `$ref` string without defining the component creates a broken reference.

Reusing examples is appropriate when the same payload is used across multiple operations or responses. However, if an operation requires a different context, create a dedicated example instead of sharing a generic name that leaves readers unclear about the difference.

## 9. Using externalValue for large examples or external files

`externalValue` points to example content stored at a URL. This approach is useful when payloads are large, span many lines, or are managed in a separate documentation repository.

~~~java
@ExampleObject(
    name = "bulkImport",
    summary = "Bulk import file",
    description = "Full JSON example stored in the documentation repository.",
    externalValue = "https://docs.example.com/openapi/examples/bulk-import.json"
)
~~~

Do not declare both `value` and `externalValue` in the same Example Object. When using `externalValue`:

- The URL must be accessible from the documentation viewer's environment.
- The target content must be well-formed and match the media type being described.
- Do not use URLs containing tokens, passwords, session IDs, or sensitive information.
- Consider access permissions, CORS, and TLS certificates if Swagger UI fetches the resource directly.
- Prefer stable URLs with versioning or a compatibility policy.

An external example is a reference to external content; OpenAPI does not embed that content and does not guarantee the URL remains available.

## 10. Choosing valuable examples for integrators

Multiple examples are only useful when they clarify distinct usage scenarios. Name and describe them by scenario rather than merely numbering them.

Example for a product search endpoint:

| Example name | Illustrated scenario |
| --- | --- |
| keywordOnly | Search by keyword with no other filters |
| categoryAndPrice | Combine category and price range |
| emptyResult | Valid request with no matching results |
| specialCharacters | Keyword with accents or characters requiring URL encoding |

When designing examples:

- Use synthetic but meaningful, easy-to-understand data that is consistent across fields.
- Include a minimal case and a realistic case with multiple fields.
- Illustrate optional fields both when present and when absent.
- For responses, choose examples for important statuses or result types.
- For errors, use error codes and status codes that match the exception handler.
- Do not use real customer data or production secrets.
- Ensure examples satisfy the schema, enums, formats, and validation rules.

There is no need to create dozens of nearly identical examples. Each example should help the reader understand an additional scenario or convention.

## 11. Examples are not validation

A common mistake is assuming that if Swagger UI displays an example, the server will accept that payload. In reality:

- `ExampleObject` only stores a sample payload in the documentation.
- `Schema` describes the published structure and constraints.
- Bean Validation and business logic are what check data at runtime.
- The message converter/Jackson decides how the body is read and types are converted.

For example, declaring:

~~~java
@ExampleObject(
    name = "invalidQuantity",
    summary = "Zero quantity example",
    value = "{\"sku\":\"KB-01\",\"quantity\":0}"
)
~~~

If the schema specifies `minimum: 1`, the example above is invalid. You may intentionally include error examples in the documentation to illustrate a `400` response, but do not place them as a success payload for the request body. Separate valid and invalid examples under the corresponding content/response with clear names.

Swagger UI can let users pick an example and populate it into the Try it out area. The user still has to send the actual request; the server processes it according to the configured controller, converter, validation, and business logic.

## 12. Verifying examples in the generated OpenAPI

After adding annotations, fetch the JSON/YAML specification from springdoc. The default endpoints are usually `/v3/api-docs` and `/v3/api-docs.yaml`, unless the application customizes the path.

~~~bash
curl -sS http://localhost:8080/v3/api-docs
curl -sS http://localhost:8080/v3/api-docs.yaml
~~~

For the create-order operation, verify a structure similar to:

~~~yaml
paths:
  /api/orders:
    post:
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
            examples:
              singleItem:
                summary: Single-item order
                value:
                  customerId: C-100
                  items:
                    - sku: KB-01
                      quantity: 2
              multipleItems:
                summary: Multi-item order
                value:
                  customerId: C-200
                  items:
                    - sku: KB-01
                      quantity: 1
                    - sku: MS-02
                      quantity: 3
~~~

Verification checklist:

1. Are the examples located under the right operation and media type?
2. Is each key in `examples` unique within the same map?
3. Do `summary` and `description` clearly explain the differences?
4. Are the JSON/XML values parseable and valid for the media type?
5. Do the payloads comply with the schema, required fields, enums, and constraints?
6. Do response examples match the right status codes and response schemas?
7. Do `$ref` values in `examples` point to existing components?
8. Is `externalValue` reachable and free of secrets embedded in the URL?
9. Does Swagger UI display the list of choices and sample payloads properly?

If `@ExampleObject` does not appear in the documentation, check that the annotation is placed in the right `@Content`, the right request/response/parameter, and verify the `swagger-core` version used by springdoc. If only one example appears, check whether the code sets a single `example` alongside `examples` or whether other metadata is overwriting `content`.

## 13. Common errors

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Only one example appears in Swagger UI | Using `example` instead of `examples`, or annotation placed at the wrong level | Declare an `@ExampleObject` array inside `@Content(examples = {...})` |
| JSON example fails to parse | `value` string is not properly escaped in Java | Escape double quotes or use `externalValue` |
| Example does not match schema | Sample data is missing fields or has wrong type/enum | Cross-check against the schema and test the payload |
| `$ref` example fails | Component example is not defined | Add `components.examples` and verify `ref` |
| `externalValue` fails to load | Wrong URL, login required, CORS, or TLS error | Check the URL from the browser environment |
| Query example renders as a JSON object | Example placed at schema/content level instead of parameter | Use `@Parameter(examples = {...})` |
| Request body has XML example but endpoint returns 415 | Controller or converter does not support XML | Align `consumes` and message converters |
| Error example used as success payload | Not separating valid request examples from error response examples | Place error examples inside the response with the corresponding status |

## 14. Workflow for designing multiple examples

When you need to publish multiple examples for an operation:

1. Identify the media type and schema of the request or response.
2. Select the distinct scenarios that integrators need to understand.
3. Choose short, meaningful names for each example.
4. Use `@ExampleObject` with `summary`, `description`, and `value`, or `externalValue` if the content is large.
5. Attach the `examples` array to the appropriate `@Content`; for parameters, use `@Parameter(examples = ...)`.
6. Reuse `components.examples` when the same payload appears across multiple operations.
7. Verify the generated JSON/YAML, Swagger UI, and runtime payloads.

For a content type like `application/json`, multiple examples help express different scenarios without creating extra endpoints or duplicate schemas. When examples are consistent with the schema and actual behavior, springdoc documentation becomes easier to read and more useful for integrators.

## References

- [OpenAPI Specification – Example Object](https://spec.openapis.org/oas/latest.html#example-object)
- [OpenAPI Specification – Media Type Object](https://spec.openapis.org/oas/latest.html#media-type-object)
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object)
- [Swagger Core – @ExampleObject Annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/ExampleObject.html)
- [springdoc-openapi – Documentation](https://springdoc.org/)
