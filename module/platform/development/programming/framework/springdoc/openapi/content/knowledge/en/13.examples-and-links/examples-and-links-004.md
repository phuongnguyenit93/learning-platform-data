# Success Examples, Invalid Data, and Edge Cases

Examples in OpenAPI help readers understand what requests to send, what responses they can receive, and how the API responds when data is invalid. With springdoc-openapi, you can describe examples directly on schemas using <code>@Schema</code>, or declare multiple named examples using <code>@ExampleObject</code> in request and response content.

A good set of examples must accurately reflect the contract: success examples must be valid against the schema; error examples must show what data is rejected and how error responses are structured; edge-case examples must clarify minimum, maximum, empty, missing, null, or special-format values. OpenAPI annotations only generate documentation. Actual validation and error handling still have to be implemented in the application.

## 1. Distinguishing example and examples

OpenAPI can describe a single simple example or a set of named examples:

| Approach | Purpose | When to use |
|---|---|---|
| <code>@Schema(example = "...")</code> | A single example at the schema level | Simple representative value for a property |
| <code>@Content(example = "...")</code> | A single example for a media type | Simple content needing only one illustrative payload |
| <code>@Content(examples = ...)</code> | Multiple named examples for a media type | Requests/responses with multiple scenarios |
| <code>@ExampleObject</code> | A named example with description and value | Distinguishing success, edge, and error cases |

In OpenAPI, a Media Type Object can contain either <code>example</code> or <code>examples</code>. These two properties are mutually exclusive within the same media type. When multiple examples are needed, use <code>examples</code> and assign a distinct name to each example.

Each <code>ExampleObject</code> can provide:

- <code>name</code>: identifier key of the example in the <code>examples</code> map.
- <code>summary</code>: short title for readers to pick an example.
- <code>description</code>: explanation of the purpose, conditions, or expected outcome.
- <code>value</code>: sample data embedded inline.
- <code>externalValue</code>: URL pointing to external example content instead of <code>value</code>.

Normally, use <code>value</code> so the documentation is self-contained. If using <code>externalValue</code>, ensure the URL is accessible and its content is versioned alongside the contract.

## 2. Success examples at the schema level

For a simple property, you can place an example directly on the DTO:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
    @Schema(
        description = "Product code",
        example = "SKU-100",
        maxLength = 40
    )
    @NotBlank
    @Size(max = 40)
    String productCode,

    @Schema(
        description = "Order quantity",
        example = "2",
        minimum = "1",
        maximum = "100"
    )
    @NotNull
    @Min(1)
    @Max(100)
    Integer quantity,

    @Schema(
        description = "Payment method",
        example = "CARD"
    )
    @NotNull
    PaymentMethod paymentMethod
) {}

enum PaymentMethod {
    COD,
    CARD,
    BANK_TRANSFER
}
~~~

<code>@Schema(example = "...")</code> works well for a single example per field. In the annotation, the <code>example</code> value is declared as a string; springdoc/swagger-core interprets it according to the schema type when generating the documentation. When you need to illustrate a complete request object with multiple interrelated fields, use <code>@ExampleObject</code> at the request body content level.

## 3. Declaring multiple request examples with @ExampleObject

An order creation operation may need a success example, a boundary-quantity example, and an invalid-data example:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    @Operation(
        summary = "Create order",
        description = "Create an order from a product code, quantity, and payment method.",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            required = true,
            content = @Content(
                mediaType = "application/json",
                examples = {
                    @ExampleObject(
                        name = "validOrder",
                        summary = "Valid order",
                        description = "Order two products by card.",
                        value = """
                            {
                              "productCode": "SKU-100",
                              "quantity": 2,
                              "paymentMethod": "CARD"
                            }
                            """
                    ),
                    @ExampleObject(
                        name = "minimumQuantity",
                        summary = "Quantity at minimum boundary",
                        description = "quantity equal to 1 is the smallest valid value.",
                        value = """
                            {
                              "productCode": "SKU-100",
                              "quantity": 1,
                              "paymentMethod": "COD"
                            }
                            """
                    ),
                    @ExampleObject(
                        name = "invalidQuantity",
                        summary = "Invalid: quantity equals 0",
                        description = "This example intentionally violates @Min(1); the server must return a validation error.",
                        value = """
                            {
                              "productCode": "SKU-100",
                              "quantity": 0,
                              "paymentMethod": "CARD"
                            }
                            """
                    )
                }
            )
        )
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Order created",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = OrderResponse.class),
                examples = @ExampleObject(
                    name = "createdOrder",
                    summary = "Confirmed order",
                    value = """
                        {
                          "orderId": "ORD-2026-001",
                          "status": "CONFIRMED",
                          "total": 259900.00
                        }
                        """
                )
            )
        ),
        @ApiResponse(
            responseCode = "400",
            description = "Invalid request",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ApiError.class),
                examples = {
                    @ExampleObject(
                        name = "quantityTooSmall",
                        summary = "Quantity below limit",
                        value = """
                            {
                              "code": "VALIDATION_FAILED",
                              "message": "Request contains invalid fields",
                              "details": {
                                "quantity": "must be greater than or equal to 1"
                              }
                            }
                            """
                    ),
                    @ExampleObject(
                        name = "missingProductCode",
                        summary = "Missing product code",
                        value = """
                            {
                              "code": "VALIDATION_FAILED",
                              "message": "Request contains invalid fields",
                              "details": {
                                "productCode": "must not be blank"
                              }
                            }
                            """
                    )
                }
            )
        )
    })
    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse response = new OrderResponse(
            "ORD-2026-001",
            "CONFIRMED",
            new java.math.BigDecimal("259900.00")
        );
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}

record OrderResponse(
    String orderId,
    String status,
    java.math.BigDecimal total
) {}

record ApiError(
    String code,
    String message,
    java.util.Map<String, String> details
) {}
~~~

In the example:

- <code>validOrder</code> is a typical valid payload.
- <code>minimumQuantity</code> illustrates the valid lower boundary.
- <code>invalidQuantity</code> intentionally does not satisfy the schema because <code>quantity</code> must be 1 or greater.
- Response <code>201</code> describes the successful result.
- Response <code>400</code> has two different error examples so integrators understand the structure of <code>details</code>.

Error request examples are clearly labeled so readers do not confuse them with payloads that can be sent successfully. If Swagger UI lets users select and send this example via Try it out, the server must reject it according to actual validation.

The examples use Java text blocks, requiring Java 15 or later. For older Java projects, replace text blocks with escaped strings or place examples in a separate OpenAPI configuration.

## 4. Describing success and error responses

Response examples are placed under each corresponding status code and media type. An operation can return several types of responses:

| HTTP status | Scenario | Example content |
|---|---|---|
| <code>201</code> | Resource created successfully | ID, status, and resource data |
| <code>400</code> | Invalid request | Error code and violating field details |
| <code>404</code> | Resource not found | Error code and identifier information |
| <code>409</code> | Business conflict | Error code such as insufficient stock or duplicate data |
| <code>422</code> | Syntactically valid data that cannot be processed under business rules | Business error code and cause |

Do not lump every error into response <code>400</code> if the application clearly distinguishes <code>404</code>, <code>409</code>, or <code>422</code>. Each status needs a schema and examples matching the system's actual response.

For a response without a body such as <code>204 No Content</code>, do not declare a JSON example. Only describe the status and headers if present.

Conflict error response example:

~~~java
@ApiResponse(
    responseCode = "409",
    description = "Insufficient stock to fulfill the order",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ApiError.class),
        examples = @ExampleObject(
            name = "insufficientStock",
            summary = "Insufficient stock",
            value = """
                {
                  "code": "INSUFFICIENT_STOCK",
                  "message": "Requested quantity is not available",
                  "details": {
                    "productCode": "SKU-100",
                    "available": "1",
                    "requested": "3"
                  }
                }
                """
        )
    )
)
~~~

The annotation snippet above can be placed inside the operation's <code>@ApiResponses</code> list. Ensure the <code>ApiError</code> DTO permits that <code>details</code> structure; if details have multiple value types, you can use a dedicated DTO or a flexible JSON type with a clearly documented schema.

## 5. Corresponding YAML examples in OpenAPI

The annotations above produce a structure roughly like the following in the OpenAPI document:

~~~yaml
paths:
  /orders:
    post:
      summary: Create order
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateOrderRequest"
            examples:
              validOrder:
                summary: Valid order
                value:
                  productCode: SKU-100
                  quantity: 2
                  paymentMethod: CARD
              minimumQuantity:
                summary: Quantity at minimum boundary
                value:
                  productCode: SKU-100
                  quantity: 1
                  paymentMethod: COD
              invalidQuantity:
                summary: Invalid: quantity equals 0
                description: Intentionally violates min 1 limit.
                value:
                  productCode: SKU-100
                  quantity: 0
                  paymentMethod: CARD
      responses:
        "201":
          description: Order created
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OrderResponse"
              examples:
                createdOrder:
                  summary: Confirmed order
                  value:
                    orderId: ORD-2026-001
                    status: CONFIRMED
                    total: 259900.00
        "400":
          description: Invalid request
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiError"
              examples:
                quantityTooSmall:
                  summary: Quantity below limit
                  value:
                    code: VALIDATION_FAILED
                    message: Request contains invalid fields
                    details:
                      quantity: must be greater than or equal to 1
~~~

Example names in the <code>examples</code> map help tools display a list of choices. The <code>value</code> content must have JSON types matching the schema: quantity is a number, status is a string, and the error object has the right structure.

## 6. Examples for empty data and edge cases

Edge-case examples help avoid ambiguous interpretations of valid data. Choose scenarios that affect how the client calls the API or processes the response.

### 6.1. Empty list and populated list

A search endpoint can return a valid empty results page:

~~~java
import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;

@ApiResponse(
    responseCode = "200",
    description = "Search results",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = OrderPageResponse.class),
        examples = {
            @ExampleObject(
                name = "emptyPage",
                summary = "No results",
                value = """
                    {
                      "items": [],
                      "page": 0,
                      "size": 20,
                      "totalElements": 0
                    }
                    """
            ),
            @ExampleObject(
                name = "pageWithItems",
                summary = "Page with items",
                value = """
                    {
                      "items": [
                        {
                          "orderId": "ORD-2026-001",
                          "status": "CONFIRMED"
                        }
                      ],
                      "page": 0,
                      "size": 20,
                      "totalElements": 1
                    }
                    """
            )
        }
    )
)

record OrderPageResponse(
    List<OrderSummary> items,
    int page,
    int size,
    long totalElements
) {}

record OrderSummary(String orderId, String status) {}
~~~

When there are no results, return <code>200</code> with an empty array rather than <code>null</code>, unless the contract adopts another convention. Examples must match the <code>items</code> type and the published pagination properties.

### 6.2. Minimum and maximum values

If the schema specifies <code>quantity</code> from 1 to 100, include examples for both boundaries:

| Value | Expected outcome |
|---:|---|
| 0 | Invalid |
| 1 | Valid, lower boundary |
| 2 | Valid, typical value |
| 100 | Valid, upper boundary |
| 101 | Invalid |

Do not test only midpoint values. Off-by-one bugs often appear right at boundary values.

### 6.3. Missing field, null, and empty string

The following three payloads have different meanings:

~~~json
{
  "productCode": "SKU-100"
}
~~~

~~~json
{
  "productCode": "SKU-100",
  "note": null
}
~~~

~~~json
{
  "productCode": "SKU-100",
  "note": ""
}
~~~

The first payload omits the <code>note</code> key; the second has the key with a null value; the third has an empty string. The schema must make clear whether the field is required, whether null is allowed, and whether empty strings are accepted.

Do not use a single example to implicitly suggest all three cases are equivalent. If the API treats a missing field as unchanged, null as clearing the value, and an empty string as empty content, describe each example separately.

### 6.4. Unicode and special characters

If the API accepts multilingual names, addresses, or notes, add a Unicode example:

~~~json
{
  "customerName": "Nguyễn Thị Ánh",
  "note": "Deliver after 18:00 – call before arriving."
}
~~~

Test accented characters, en-dashes, emojis if the system allows them, and characters requiring escaping such as double quotes or backslashes. JSON must be properly escaped so parsers can read it.

### 6.5. Date-time and time zones

If the API uses timestamps, clearly illustrate the offset or UTC:

~~~json
{
  "createdAt": "2026-11-20T10:30:00+07:00",
  "expiresAt": "2026-11-20T03:30:00Z"
}
~~~

The two timestamps above represent the same instant using two different offsets. Examples help clients recognize that the API requires the date-time format and understand the time-zone convention.

## 7. Examples for query parameters and headers

Not only request bodies need examples. Query parameters and headers can also be described using <code>@Parameter</code>:

~~~java
import java.util.List;

import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/orders/search")
List<OrderResponse> searchOrders(
    @Parameter(
        description = "Status to filter by",
        examples = {
            @ExampleObject(name = "confirmed", value = "CONFIRMED"),
            @ExampleObject(name = "cancelled", value = "CANCELLED")
        }
    )
    @RequestParam(name = "status", required = false) String status
) {
    // ...
    return List.of();
}
~~~

Here, <code>@RequestParam</code> defines the binding name and optionality at runtime; <code>@Parameter</code> adds examples for documentation. If the client omits the query parameter, it is in the absent state. If it sends <code>?status=</code>, that is an empty string value; the application should define how to handle it separately.

For headers, you can use <code>@Parameter</code> alongside <code>@RequestHeader</code> in the same way. Never declare an authentication header example containing a real token or secret. Use a safe dummy value such as <code>Bearer eyJ...demo</code> if you need to illustrate syntax.

## 8. Examples do not replace validation and testing

Adding <code>@ExampleObject</code> does not make Spring validate payloads automatically. An invalid request example is purely documentation content; the server needs real validation:

With Spring Boot, a Bean Validation implementation must be on the classpath, usually via the following starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

When using Spring Boot dependency management, there is no need to specify a version manually for this starter. Next, declare constraints on the DTO and enable validation with <code>@Valid</code> on the controller parameter.

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
    @NotBlank
    @Size(max = 40)
    String productCode,

    @NotNull
    @Min(1)
    @Max(100)
    Integer quantity
) {}
~~~

The controller must enable Bean Validation:

~~~java
@PostMapping("/orders")
ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

To give error responses a consistent structure, you can handle exceptions with <code>@RestControllerAdvice</code>:

~~~java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleValidation(
            MethodArgumentNotValidException exception) {
        Map<String, String> details = exception.getBindingResult()
            .getFieldErrors()
            .stream()
            .collect(java.util.stream.Collectors.toMap(
                error -> error.getField(),
                error -> error.getDefaultMessage() == null
                    ? "Invalid value"
                    : error.getDefaultMessage(),
                (first, second) -> first
            ));

        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .body(new ApiError(
                "VALIDATION_FAILED",
                "Request contains invalid fields",
                details
            ));
    }
}
~~~

This example handler returns the <code>ApiError</code> structure shown in the response examples above. In a real project, standardize error codes, messages, masking of internal details, and handling of other exception types.

Write tests for both valid and invalid payloads. Success examples should verify status, content type, and body. Error examples should verify status <code>400</code>, error codes, and field details. An example in documentation is only trustworthy when it corresponds to verified behavior.

## 9. Verifying generated examples in OpenAPI

After the application starts, fetch the JSON specification:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Verify:

1. The request body has the right media type such as <code>application/json</code>.
2. Named examples appear under <code>content.application/json.examples</code>.
3. Response examples sit under the right status codes such as <code>201</code> or <code>400</code>.
4. Each example has a sufficiently clear summary/description to distinguish it.
5. The schema of each request/response matches the types and constraints of the values.
6. Both <code>example</code> and <code>examples</code> are not declared on the same Media Type Object.
7. Error examples are clearly marked as invalid payloads and cannot be mistaken for successful request samples.

You can inspect the documentation in Swagger UI to verify the list of example choices. Select each request example, observe the displayed JSON, and try sending it in a development environment. Never send error examples to production just to test documentation.

## 10. Guidelines for writing usable examples

- Use synthetic data with a realistic shape; never include real personal information or secrets in documentation.
- Choose short, meaningful names such as <code>validOrder</code>, <code>minimumQuantity</code>, <code>invalidQuantity</code>, <code>emptyPage</code>.
- Each example should illustrate one main purpose so readers understand the difference.
- Clearly state which examples are valid and which intentionally violate the schema.
- Keep IDs, statuses, timestamps, currency units, and enums consistent across requests, responses, and descriptions.
- When a schema changes, update related examples at the same time.
- Do not create examples containing fields absent from the schema unless the API allows extensible fields.
- In response examples, never expose real user tokens, passwords, emails, or personal data.
- For edge-case examples, explicitly state whether the value sits right on the boundary or beyond it.

## 11. Common errors

**Putting multiple examples into a single example.** The <code>example</code> attribute is for a single value only. Use <code>examples</code> with named <code>@ExampleObject</code> entries.

**Example does not match the schema.** Such examples can lead clients to copy invalid payloads. Check data types, required, nullable, enum, min/max, and format.

**Unmarked error examples.** Users might accidentally pick an error payload in Swagger UI. Name and describe them clearly as intentionally invalid.

**Assuming annotations create runtime error responses.** <code>@ApiResponse</code> and <code>@ExampleObject</code> only describe documentation. Exception handlers and validation are required for the server to actually return errors.

**Using status codes that mismatch implementation.** If the application returns <code>400</code> while OpenAPI describes <code>422</code>, clients will handle it incorrectly. Synchronize annotations and exception handlers.

**Ignoring empty and null cases.** Empty arrays, empty objects, missing fields, null, and empty strings have different meanings. Include them in examples only when the contract clearly defines their behavior.

**Date-time examples without offsets.** If the API expects an absolute instant, use date-time with an offset or UTC and document the convention clearly.

## 12. Pre-publication review checklist

- [ ] Success request examples exist for important operations.
- [ ] Success response examples exist for each main status code.
- [ ] Invalid request examples and corresponding error responses are included.
- [ ] Minimum/maximum or near-boundary value examples are included where needed.
- [ ] Empty list, missing field, null, or empty string examples are included if meaningful.
- [ ] Each example has a clear name, summary, or description.
- [ ] Example values match the schema or are clearly marked as intentionally invalid.
- [ ] No real sensitive data appears in examples.
- [ ] OpenAPI annotations and validation/exception handler behavior are consistent.
- [ ] Generated <code>/v3/api-docs</code> output, Swagger UI, and real endpoint tests have been verified.

## References

- [OpenAPI Specification – Example Object](https://spec.openapis.org/oas/latest.html#example-object): the <code>summary</code>, <code>description</code>, <code>value</code>, and <code>externalValue</code> fields.
- [OpenAPI Specification – Media Type Object](https://spec.openapis.org/oas/latest.html#media-type-object): how to declare <code>example</code> and <code>examples</code> for request/response content.
- [Swagger – Adding Examples](https://swagger.io/docs/specification/adding-examples/): examples for request bodies, responses, and parameters.
- [Swagger Core – ExampleObject annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/ExampleObject.html): attributes of the <code>@ExampleObject</code> annotation.
- [springdoc-openapi](https://springdoc.org/): integrating OpenAPI annotations with Spring Boot and Swagger UI.
