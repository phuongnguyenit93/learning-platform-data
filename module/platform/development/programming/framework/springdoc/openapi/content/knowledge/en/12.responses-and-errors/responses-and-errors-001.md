# @ApiResponse, @ApiResponses, and the Operation Status Code Set

An operation in OpenAPI needs to describe the responses that a client can receive: when processing succeeds, when input data is invalid, when a resource does not exist, or when the caller lacks permission. With springdoc-openapi, the **@ApiResponse** and **@ApiResponses** annotations help clearly declare each HTTP status code, response content, and corresponding schema.

Response descriptions must closely reflect the actual behavior of the controller and exception handler. OpenAPI annotations only generate documentation; they do not change the status code, produce a response body, or handle exceptions on their own. This lesson explains how to build an operation's response set, combine it with ResponseEntity and @ResponseStatus, and inspect the generated JSON specification.

## 1. What Does the Operation Response Object Describe?

In OpenAPI, each operation has a **responses** object containing the possible responses. Each response is keyed by an HTTP status code or the **default** key.

Condensed example:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      responses:
        '200':
          description: Order found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '404':
          description: Order not found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiError'
        default:
          description: Errors outside the listed responses
~~~

Each Response Object typically has the following fields:

| Field | Meaning |
|---|---|
| description | Describes the meaning of the response; this is a required field in the Response Object |
| headers | HTTP headers returned with the response |
| content | Body content per media type and schema |
| links | Links to other operations that can be invoked next from the response |

A response does not necessarily have a body. For example, HTTP 204 No Content indicates that the operation succeeded without response content. In that case, the response may only need description and headers if applicable.

An operation can declare multiple response codes. Document the codes that the API can actually return and that are meaningful to clients; there is no need to list every HTTP code that exists in the standard.

## 2. Role of @ApiResponse and @ApiResponses

**@ApiResponse** describes one response case of an operation. Its most important attributes are usually:

- responseCode: HTTP code as a string, such as "200", "201", "404", or "default".
- description: meaning of the response.
- content: media type and schema of the response body.
- headers: returned headers.
- links: links to follow-up operations.
- ref: reference to a shared response component if the document is organized that way.

**@ApiResponses** is an annotation containing a list of @ApiResponse entries. It lets you declare multiple response cases on the same controller method.

Example:

~~~java
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;

@GetMapping("/{id}")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Order found"
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Order not found"
    )
})
public OrderResponse getOrder(@PathVariable String id) {
    return orderService.findById(id);
}
~~~

A response can be described more completely using content and schema. When representing a response body, declare the media type and data type so Swagger UI and client generators understand the response structure.

Do not confuse annotation names with HTTP behavior. @ApiResponse(responseCode = "404") does not make the controller automatically return 404. It only declares in OpenAPI that the operation has a 404 response.

## 3. Describing a Success Response with a Schema

Example of an endpoint returning order details:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import java.net.URI;
import java.util.Optional;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@GetMapping("/{id}")
@Operation(
    operationId = "getOrderById",
    summary = "Get order by ID"
)
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Order found",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Order not found",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public ResponseEntity<?> getOrder(
    @PathVariable String id
) {
    Optional<OrderResponse> result = orderService.findById(id);
    if (result.isPresent()) {
        return ResponseEntity.ok(result.get());
    }
    return ResponseEntity.status(HttpStatus.NOT_FOUND)
        .body(new ApiError("ORDER_NOT_FOUND", "Order not found", null));
}
~~~

In the example:

- 200 describes a body of type OrderResponse.
- 404 describes the case where the resource is not found.
- ResponseEntity allows the controller to choose the actual status code based on the processing result.
- @ApiResponses declares both branches in the OpenAPI contract.

The implementation returns ApiError in the 404 branch, so the actual body matches the documented schema. The ResponseEntity<?> return type reflects two different body types; if you want clients to have a clear error type, keep the success and error schemas separate as in OpenAPI.

If a controller returns a fixed type and has no dynamic status branches, springdoc can partially infer the response from the return type. However, error responses or special branches should be documented explicitly.

## 4. Distinguishing 200, 201, 202, and 204 Responses

All 2xx codes indicate that a request succeeded to some extent, but they do not carry the same meaning.

| Code | Common meaning | Example |
|---|---|---|
| 200 OK | Request succeeded; usually includes a response body | Querying order details |
| 201 Created | A new resource has been created | Creating a customer or order |
| 202 Accepted | Request has been accepted for processing, not necessarily completed | Submitting a background job |
| 204 No Content | Request succeeded and returns no response body | Deleting a resource |

Example of creating an order returning 201:

~~~java
@PostMapping
@Operation(
    operationId = "createOrder",
    summary = "Create a new order"
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Order has been created",
        headers = @Header(
            name = "Location",
            description = "URL of the newly created order",
            schema = @Schema(type = "string", format = "uri")
        ),
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid request data",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public ResponseEntity<OrderResponse> createOrder(
    @Valid @RequestBody CreateOrderRequest request
) {
    OrderResponse created = orderService.create(request);
    URI location = URI.create("/api/orders/" + created.getId());

    return ResponseEntity.created(location).body(created);
}
~~~

ResponseEntity.created(location) produces a 201 response and the Location header. In OpenAPI, if you want clients to know about this header, describe the header in @ApiResponse.

Example of a delete operation returning 204:

~~~java
@DeleteMapping("/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
@ApiResponse(
    responseCode = "204",
    description = "Order has been deleted"
)
public void deleteOrder(@PathVariable String id) {
    orderService.delete(id);
}
~~~

Do not document a 204 response with a JSON body. According to HTTP semantics, a 204 response has no content. If you need to return confirmation details or deleted data, choose an appropriate status code and response design, typically 200 with a body.

## 5. Describing Error Responses with a Shared Schema

Operations often return the same error format. You can create a shared DTO:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "ApiError",
    description = "Error information returned by the API"
)
public class ApiError {

    @Schema(
        description = "Stable error code for client handling",
        example = "ORDER_NOT_FOUND"
    )
    private String code;

    @Schema(
        description = "Human-readable message",
        example = "Order not found"
    )
    private String message;

    @Schema(
        description = "Identifier for log lookup",
        example = "req-7f9a2c"
    )
    private String traceId;

    // Constructor, getters, and setters.
}
~~~

Then use this schema for error responses:

~~~java
@ApiResponse(
    responseCode = "404",
    description = "Resource not found",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ApiError.class)
    )
)
~~~

A consistent error schema makes it easier for clients to parse responses and map business error codes. However, share it only when the structure and semantics are genuinely the same. Validation errors may require a list of field violations; conflict errors may require current state information. If responses differ, create specific schemas or a clearly designed composition structure.

## 6. Describing Multiple Error Codes for an Operation

An order query endpoint may have the following cases:

- 400: invalid parameters.
- 401: unauthenticated.
- 403: authenticated but unauthorized.
- 404: order not found.
- 429: request limit exceeded if the system enforces rate limiting.
- 500: unexpected server error.

Not every endpoint has all of these codes. Base the list on your actual security policy, controller, exception handler, and gateway.

Declaration example:

~~~java
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Order found",
        content = @Content(
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid query parameters",
        content = @Content(
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "401",
        description = "Authentication required",
        content = @Content(
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "403",
        description = "Access denied",
        content = @Content(
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Order not found",
        content = @Content(
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
~~~

If all error responses share the same schema, you can use a shared response component to avoid repeating metadata. Even so, each operation should still declare the exact set of status codes that can occur in its context.

## 7. Distinguishing @ApiResponse from @ResponseStatus

The two annotations serve different purposes:

| Annotation | Effect |
|---|---|
| @ApiResponse | Describes a response in OpenAPI documentation |
| @ApiResponses | Groups multiple response descriptions for an operation |
| @ResponseStatus | Sets the actual HTTP status for a handler when Spring processes a request |
| @ExceptionHandler | Chooses how an exception is handled in a controller or advice |
| ResponseEntity | Allows returning status, headers, and body per runtime branch |

Example:

~~~java
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
@ApiResponse(
    responseCode = "201",
    description = "Resource created successfully"
)
public ProductResponse create(
    @RequestBody ProductRequest request
) {
    return productService.create(request);
}
~~~

Here @ResponseStatus sets the actual status to 201; @ApiResponse records that same status in the documentation.

If you only have @ApiResponse(responseCode = "201") while the method does not use ResponseEntity, @ResponseStatus, or another mechanism to return 201, the application may still return the default 200 status. This is a form of contract drift to avoid.

When using ResponseEntity, the status can vary across processing branches. In that case, list the corresponding branches in @ApiResponses and verify them with runtime tests.

## 8. @ApiResponse Does Not Replace Exception Handling

Suppose a service throws OrderNotFoundException. For the application to actually return HTTP 404, there must be exception-handling logic, such as @RestControllerAdvice:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(
        OrderNotFoundException exception
    ) {
        ApiError body = new ApiError(
            "ORDER_NOT_FOUND",
            exception.getMessage(),
            null
        );

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }
}
~~~

On the controller operation, you need to describe the 404 response with the ApiError schema. Having an exception handler does not automatically guarantee that every operation is completely documented in OpenAPI; check your project's springdoc configuration and the generated output.

Similarly, MethodArgumentNotValidException can be mapped to 400, AccessDeniedException to 403, or a business exception to 409. Each mapping must stay consistent across:

1. The actual exception thrown.
2. The exception handler deciding the status and body.
3. The @ApiResponse declaring the status and schema.
4. Tests verifying the actual response.

If an exception can be thrown across many operations, the team can consider shared response declarations or customizers. Do not assume that adding @ApiResponse to an exception handler will automatically apply accurately to every operation under every configuration.

## 9. Describing a Response Without a Body

Some status codes do not need a body or are not allowed to have a body under HTTP semantics. A common example is 204 No Content.

You can declare it as:

~~~java
@ApiResponse(
    responseCode = "204",
    description = "Deleted successfully"
)
~~~

If the response only has headers, declare headers without adding content:

~~~java
@ApiResponse(
    responseCode = "202",
    description = "Task accepted",
    headers = {
        @Header(
            name = "Location",
            description = "URL to track task status",
            schema = @Schema(type = "string", format = "uri")
        )
    }
)
~~~

For a 202 response, a body may or may not exist depending on the design. If the API returns a task identifier in the body, declare the corresponding content and schema. If it only returns Location, describe that header so clients know how to track progress.

Avoid declaring content with an empty schema or an unrelated schema for a bodyless response. Doing so can cause generators to produce methods that expect data the server never sends.

## 10. Describing Response Headers

A response can carry metadata via HTTP headers, such as Location, ETag, Retry-After, or X-Request-Id.

Example:

~~~java
@ApiResponse(
    responseCode = "201",
    description = "Resource created successfully",
    headers = {
        @Header(
            name = "Location",
            description = "URL of the newly created resource",
            schema = @Schema(type = "string", format = "uri")
        ),
        @Header(
            name = "ETag",
            description = "Resource version identifier",
            schema = @Schema(type = "string")
        )
    },
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ProductResponse.class)
    )
)
~~~

Documenting headers is useful when clients need the URL of a new resource, cache control, or conditional update values. Verify that the server actually returns those headers at runtime. Annotations do not automatically add Location or ETag to the response.

For the Retry-After header when returning 429 or 503, describe its type and unit/meaning in description so clients know how to wait before retrying. Do not declare a header merely because a gateway might return it in some cases if the application does not commit to that behavior.

## 11. Describing Media Types and Response Bodies

A response can return JSON, XML, plain text, or binary content. The content attribute lets you describe multiple media types.

JSON response example:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Returns product information",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ProductResponse.class)
    )
)
~~~

Text response example:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Returns CSV content",
    content = @Content(
        mediaType = "text/csv",
        schema = @Schema(type = "string")
    )
)
~~~

Binary file example:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Download report",
    content = @Content(
        mediaType = "application/octet-stream",
        schema = @Schema(type = "string", format = "binary")
    )
)
~~~

The media type in OpenAPI must match the actual Content-Type. If a controller returns application/pdf while the spec documents application/json, client generators may produce the wrong body-handling type.

When an endpoint supports multiple Accept types, document each type and its corresponding schema. For file downloads, check how the generator handles streams or byte arrays in the target language.

## 12. Default Response and Unlisted Error Codes

OpenAPI allows the **default** key inside responses. It describes the response used for any HTTP status code not listed individually in the operation.

Example:

~~~yaml
responses:
  '200':
    description: Success
  '404':
    description: Not found
  default:
    description: Other error
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ApiError'
~~~

default does not mean HTTP 200 or Spring's default status. It is a catch-all description for response codes not explicitly declared.

You can use @ApiResponse(responseCode = "default", ...) in annotations. However, do not rely solely on default in place of important codes that clients need to handle separately. If clients must distinguish 400 from 409 or 429, list them explicitly.

## 13. Reusing Response Objects

If multiple operations share the same error response, you can define a component in components.responses:

~~~yaml
components:
  responses:
    NotFound:
      description: Resource not found
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
~~~

Operation referencing the response component:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'
~~~

With swagger-annotations, @ApiResponse supports the ref attribute to reference a response defined in the document. When using references, verify that the output $ref has the right component path and that the component exists.

Reuse reduces duplication, but only use it when the description, schema, headers, and semantics of the response are identical. If an order 404 error has different details from a customer 404 error, you may need a separate response component or an explicit description on the operation.

## 14. Responses Across Multiple Runtime Branches

When a controller uses ResponseEntity or an exception handler handles error branches, an operation can return multiple status codes. Example:

~~~java
@PutMapping("/{id}")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Updated successfully",
        content = @Content(
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Product not found",
        content = @Content(
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Product version has changed",
        content = @Content(
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public ResponseEntity<?> updateProduct(
    @PathVariable String id,
    @RequestBody UpdateProductRequest request
) {
    // ProductNotFoundException and VersionConflictException are handled
    // by @RestControllerAdvice to return 404 and 409 respectively.
    return ResponseEntity.ok(productService.update(id, request));
}
~~~

In this example, the ResponseEntity<?> return type is overly generic. In a real application, consider a concrete return type or a clear response design so springdoc can analyze it better. Error branches handled in services/advice must have corresponding tests and documentation.

Do not add status codes to @ApiResponses merely because they are theoretically "possible". Every code should be grounded in actual code, exception handlers, security, gateway rules, or an agreed contract.

## 15. Inspecting Status Codes in OpenAPI JSON

After the application starts, download the document:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

View all responses of an operation:

~~~bash
jq '.paths["/api/orders/{id}"].get.responses' openapi.json
~~~

List the status codes:

~~~bash
jq -r '.paths["/api/orders/{id}"].get.responses | keys[]' openapi.json
~~~

Inspect the schema of the 404 response:

~~~bash
jq '.paths["/api/orders/{id}"].get.responses["404"].content["application/json"].schema' openapi.json
~~~

Check the following points:

- Are all important status codes present?
- Do 2xx responses match the actual status codes at runtime?
- Is 204 mistakenly documented with a body?
- Do error responses have the right media type and schema?
- Are headers such as Location or Retry-After documented?
- Is default masking error codes that clients need to handle individually?
- Do all $ref targets point to existing components?

If springdoc automatically infers a success response, compare it against the explicitly declared response. When differences appear, check annotation order, annotation scope, and library version configuration. The final output in JSON is the document that client generators will read.

## 16. Verifying Runtime Behavior

After inspecting the JSON, send real requests or run integration tests to verify status codes and bodies.

Example with the order lookup endpoint:

~~~bash
# Case when order is found
curl -i http://localhost:8080/api/orders/ORD-1001

# Case when order does not exist
curl -i http://localhost:8080/api/orders/unknown
~~~

Compare status, Content-Type, headers, and body against OpenAPI. If the documentation states 404 but the application returns 200 with an empty body, fix either the implementation or the documentation according to the agreed contract.

Check at least the following:

1. Success branch.
2. Invalid request data.
3. Non-existent resource.
4. Unauthenticated and unauthorized cases, if the operation is protected.
5. Business conflict, if applicable.
6. Bodyless responses such as 204.
7. Whether system or gateway errors are documented at an appropriate scope.

Errors produced by a reverse proxy or API gateway may not pass through Spring MVC. If the public contract guarantees a unified error format at the gateway, verify the spec and tests at the integration layer outside the application.

## 17. Common Pitfalls

| Symptom | Cause to check |
|---|---|
| Swagger UI only shows 200 | Error responses are not declared or the exception handler is not documented on the operation |
| Documentation lists 404 but the application returns 200 | @ApiResponse is only metadata; missing logic to return the actual status |
| 201 response has no Location | Controller does not add the Location header even though documentation describes it |
| 204 response has a body schema | Content declaration conflicts with No Content semantics |
| Client generator does not create an error model | Response lacks content/schema or references an invalid schema |
| Actual error body differs from schema | Exception handler returns a DTO different from @Schema implementation |
| Default response hides important codes | Specific codes such as 400, 401, 403, 404, or 409 are not explicitly declared |
| Media type mismatch | Runtime Content-Type differs from content in OpenAPI |
| Header missing from documentation | headers not declared in @ApiResponse |
| Broken response $ref | Referenced response component or schema does not exist |
| ResponseEntity<?> makes schema overly generic | Return type is too broad; consider a concrete DTO or explicit response description |

## 18. Design Conventions for an Operation's Response Set

An operation that is easy to integrate with should have a concise, clear response set that accurately reflects its behavior:

- Record the success response using the exact status code returned by the controller.
- Describe the body schema for responses that carry content.
- Document important headers such as Location, ETag, or Retry-After.
- List client-actionable error codes separately when clients need to handle them differently.
- Use a unified error schema if the structure is genuinely identical.
- Use default for remaining codes when appropriate, without replacing important codes.
- Do not declare a body for 204.
- Check responses produced by both controllers and exception handlers.
- Keep status codes, descriptions, schemas, and runtime tests consistent.

There is no need to copy the entire system-wide error list into every operation. Select the cases that can occur and are meaningful in the context of that endpoint.

## 19. Review Checklist for @ApiResponse and @ApiResponses

- [ ] Each operation documents an appropriate success response.
- [ ] responseCode matches the runtime status code.
- [ ] Each response has a clear description.
- [ ] Responses with bodies declare the correct media type and schema.
- [ ] Bodyless responses such as 204 do not declare content.
- [ ] Important error codes are listed individually.
- [ ] Error schemas match the DTO returned by the exception handler.
- [ ] Headers such as Location, ETag, or Retry-After are documented when present.
- [ ] default is used properly as a fallback for unlisted codes.
- [ ] Referenced response components and schemas are valid.
- [ ] Checked responses in /v3/api-docs.
- [ ] Ran integration tests for important status branches.

## 20. References

- [OpenAPI Specification – Responses Object](https://spec.openapis.org/oas/latest.html#responses-object)
- [OpenAPI Specification – Response Object](https://spec.openapis.org/oas/latest.html#response-object)
- [Swagger Annotations – API documentation](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/index.html)
- [Spring Framework – @ResponseStatus](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/ResponseStatus.html)
- [Spring Framework – Exception handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [springdoc-openapi – official documentation](https://springdoc.org/)

@ApiResponse and @ApiResponses describe the response set in the OpenAPI contract. ResponseEntity, @ResponseStatus, and exception handlers determine the actual response when the application runs. Keep both sides synchronized and verify the generated JSON along with integration tests before publishing documentation to clients.
