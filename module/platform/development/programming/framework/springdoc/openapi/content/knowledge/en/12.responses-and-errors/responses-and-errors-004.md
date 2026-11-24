# Bodyless Responses Like 204 and Avoiding Incorrectly Inferred Schemas

Not every successful request needs to return JSON. When a client deletes a resource, updates data without needing a new representation, or sends an operation that only requires confirmation of completion, the server can return a response without a message body. HTTP `204 No Content` is a common choice for this scenario.

In Spring Boot, a controller's return type affects how Spring handles the response and how Springdoc infers schemas. If an endpoint actually returns no body while the method declares a DTO, `String`, `Object`, or generic wrapper, the OpenAPI documentation can end up with an incorrect schema. The HTTP status, Java return type, response annotations, and OpenAPI Response Object must all express one consistent contract.

## 1. What Does a Bodyless Response Mean?

An HTTP response consists of a status line, headers, and optionally a message content (body). A bodyless response can still carry headers to provide metadata, but the client receives no JSON/XML representation in the content section.

Common cases:

| Case | Status or method | Meaning |
|---|---|---|
| Resource deleted successfully | `204 No Content` | Operation complete, no representation returned |
| Updated successfully without returning new data | `204 No Content` | Client knows the operation completed |
| Request received and currently processing | `202 Accepted` | May return a body describing processing state; may also have no body if specified by contract |
| Client sends a HEAD request | `HEAD` | Response has no content; metadata headers corresponding to GET may still appear |
| Representation unchanged per request condition | `304 Not Modified` | Client uses cached copy; response has no content |
| Server instructs client to reset display state | `205 Reset Content` | Response has no content and carries 205's specific semantics |

Do not use all of these statuses interchangeably. `204` is usually appropriate when the operation has completed and no representation is needed. `202` says processing was accepted but may not be finished yet. `304` applies only to conditional requests such as `If-None-Match` or `If-Modified-Since`. `205` means resetting the client's document view and is less common in business APIs.

## 2. HTTP Rules for 204 No Content

According to HTTP Semantics, `204 No Content` indicates that the request has been fulfilled and there is no content to send in the response. The response terminates immediately after the header section. The server must not send message content or trailer fields in a 204 response and must not send a `Content-Length` header in this response.

A 204 response can still carry useful metadata headers. For example:

- `ETag` indicating the new validator of the resource after an update.
- `Cache-Control` controlling caching behavior.
- Business headers published by the API, if consistent with HTTP semantics.

Example:

```http
HTTP/1.1 204 No Content
ETag: "product-42-v8"
Cache-Control: no-store
```

The response above has no JSON body yet still provides an ETag for the client to use on the next update. If you need to return updated data such as name, price, or resource state, use a response with a body, typically `200 OK`.

## 3. Returning 204 Properly in Spring Boot

With Spring MVC, there are two common ways to produce a 204 response.

### Approach 1: Using `ResponseEntity<Void>`

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
class ProductController {

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(@PathVariable Long id) {
        productService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
```

`ResponseEntity.noContent().build()` sets the status to `204` and builds a bodyless response. `Void` clearly states that the method returns no representation. This approach is convenient when the controller needs to set status or headers dynamically across processing branches.

### Approach 2: Using `void` with `@ResponseStatus`

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.ResponseStatus;

@DeleteMapping("/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
void delete(@PathVariable Long id) {
    productService.delete(id);
}
```

`@ResponseStatus(HttpStatus.NO_CONTENT)` instructs Spring to return status 204; the `void` type indicates that the method provides no response body. This is concise when the status is fixed and you do not need to construct a `ResponseEntity`.

### When You Need to Return Headers with 204

You can use `ResponseEntity` to add metadata:

```java
@PutMapping("/{id}/activate")
ResponseEntity<Void> activate(@PathVariable Long id) {
    String newVersion = productService.activate(id);

    return ResponseEntity.noContent()
        .eTag(newVersion)
        .build();
}
```

The ETag value must follow the HTTP entity-tag format used by your application. The response still has no body; the header only supplies metadata about the resource version.

Do not return a DTO with all fields set to null and treat it as an empty response. JSON `{}` or `{"data":null}` is still message content and has different semantics from 204.

## 4. Describing a 204 Response in OpenAPI

In the OpenAPI Response Object, `description` is required; `content` is optional. For a bodyless response, omit `content` altogether.

OpenAPI YAML example:

```yaml
paths:
  /api/products/{id}:
    delete:
      summary: Delete product
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '204':
          description: Product deleted successfully; response has no body.
        '404':
          description: Product not found.
```

Here, the 204 response has no `content`, no media type, and no schema. This is the right representation for a response without a message body.

Do not describe 204 with a dummy schema such as:

```yaml
'204':
  description: Success
  content:
    application/json:
      schema:
        type: object
```

The schema above claims the server returns a JSON object. It contradicts 204 semantics and can cause Swagger UI or client generators to produce code that reads a nonexistent body.

Similarly, do not create `type: string`, `type: null`, or an empty DTO to represent a 204 response. If there is no content, express that directly by omitting `content`.

## 5. Declaring 204 with Swagger Annotations in Springdoc

With Springdoc, use `@ApiResponse` to describe the status code and description. Do not declare `content` for a 204 response.

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;

@DeleteMapping("/{id}")
@Operation(summary = "Delete product by ID")
@ApiResponses({
    @ApiResponse(
        responseCode = "204",
        description = "Product deleted; no response body."
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Product not found."
    )
})
ResponseEntity<Void> delete(@PathVariable Long id) {
    productService.delete(id);
    return ResponseEntity.noContent().build();
}
```

The 204 annotation declares only `responseCode` and `description`. Do not add `@Content`, `@Schema(implementation = Void.class)`, or a media type to this response. The `ResponseEntity<Void>` return type also helps Springdoc recognize that the method has no success payload.

If you want to document response headers, declare them inside `@ApiResponse` without adding `content`:

```java
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.media.Schema;

@ApiResponse(
    responseCode = "204",
    description = "Product status updated; no body.",
    headers = @Header(
        name = "ETag",
        description = "New resource validator",
        schema = @Schema(type = "string")
    )
)
```

OpenAPI will document ETag in `responses.204.headers`. Headers are not the response body and do not introduce a content schema.

## 6. Endpoints with Both Body and Bodyless Responses

An operation can return multiple status codes with different structures. For example, an update endpoint might return `200 OK` with the representation when the client asks for updated data, or `204 No Content` when only confirming the update.

OpenAPI must describe each response independently:

```yaml
responses:
  '200':
    description: Updated successfully; returns the updated product.
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ProductResponse'
  '204':
    description: Updated successfully; no representation returned.
  '404':
    description: Product not found.
```

Example controller with multiple branches:

```java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;

@PatchMapping("/{id}")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Updated and returned new representation",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "204",
        description = "Updated; no body returned"
    )
})
ResponseEntity<ProductResponse> patch(
    @PathVariable Long id,
    @RequestBody ProductPatchRequest request,
    @RequestParam(defaultValue = "true") boolean returnRepresentation
) {
    ProductResponse updated = productService.patch(id, request);

    if (returnRepresentation) {
        return ResponseEntity.ok(updated);
    }
    return ResponseEntity.noContent().build();
}
```

This example uses the generic type `ResponseEntity<ProductResponse>` because one branch actually returns a body. For operations with multiple responses, Springdoc may infer a schema from the return type and combine it with response annotations. Inspect the generated OpenAPI JSON to ensure the schema appears only under the 200 response and that the 204 response has no `content`. If the documentation still attaches a schema to 204, check annotations on interfaces/controllers, customizers, shared responses, and the Springdoc version in use.

If an operation can only return 204, use `ResponseEntity<Void>` or `void` with `@ResponseStatus` instead of declaring a DTO and returning null.

## 7. Avoiding Incorrectly Inferred Schemas from Java Return Types

Springdoc often uses a controller's return type to infer a response schema when explicit metadata is absent or when completing responses. Therefore, the Java type must reflect HTTP behavior.

| Return type | Commonly inferred meaning | Suitable for 204? |
|---|---|---|
| `ResponseEntity<Void>` | No response payload | Yes |
| `void` | Method returns no representation | Yes, when status is set to 204 |
| `ResponseEntity<ProductResponse>` | May return `ProductResponse` | Not suitable if all branches have no body |
| `ProductResponse` | Has a `ProductResponse` response body | Not suitable for an operation that only returns 204 |
| `String` | Has a string response body | Not suitable for an operation that only returns 204 |
| `ResponseEntity<Object>` | Unclear payload, may be inferred as a broad schema | Avoid unless genuinely returning dynamic bodies |
| `ResponseEntity<ApiEnvelope<Void>>` | Has an envelope body, even though `data` is Void | Not an empty response |

### `Void` Is Different from `ApiEnvelope<Void>`

These two types do not share the same semantics:

```java
ResponseEntity<Void>
```

Represents a response with no body.

```java
ResponseEntity<ApiEnvelope<Void>>
```

Represents a response whose body is a JSON envelope object. Example:

```json
{
  "requestId": "req-42",
  "data": null
}
```

If the API returns a JSON envelope, describe the envelope schema and use an appropriate status such as 200. If the API returns no content, use 204 and do not declare an envelope.

### Do Not Rely on Null Values to Determine Status

Returning `null` from a controller with a DTO return type does not automatically make the server return 204. The outcome depends on mappings, message converters, configuration, and how Spring handles return values. Set the status explicitly with `ResponseEntity.noContent()` or `@ResponseStatus(HttpStatus.NO_CONTENT)`.

## 8. Generic Responses and Shared Responses from ControllerAdvice

A project may use a common wrapper like `ApiResponse<T>` or declare shared error responses via `@RestControllerAdvice`. These mechanisms are useful for responses with bodies, but they must not be applied mechanically to 204 responses.

Example wrapper:

```java
public record ApiResponse<T>(
    String code,
    String message,
    T data
) {
}
```

If a method returns `ApiResponse<Void>`, the response still has a JSON body containing `code`, `message`, and `data: null`. This is not a no-content response.

Springdoc can propagate generic responses from `@ControllerAdvice` to operations. The `springdoc.override-with-generic-response` property controls applying generic responses per Springdoc's mechanism. When a project uses this setting, inspect the 204 operation's responses to ensure no inappropriate content is added.

For example, an error response with a body can still be documented separately:

```java
@ApiResponse(
    responseCode = "404",
    description = "Product not found",
    content = @Content(
        mediaType = "application/problem+json",
        schema = @Schema(implementation = ProblemDetail.class)
    )
)
```

A 404 response having content does not mean the 204 response needs content too. Each status code has its own Response Object and must be described according to its actual behavior.

## 9. Describing 205, 304, and HEAD Without Adding a Body Schema

### 205 Reset Content

`205 Reset Content` informs the client that the server fulfilled the request and asks the user agent to reset the document view. The server must not generate content in a 205 response and must indicate a zero-length response per HTTP rules.

OpenAPI:

```yaml
'205':
  description: Request completed; client should reset the document view.
```

Do not add `content` if the response has no body.

### 304 Not Modified

`304 Not Modified` is used in conditional GET or HEAD requests when the representation has not changed relative to the validator sent by the client. The response has no content; the client uses its cached representation.

OpenAPI:

```yaml
'304':
  description: Representation unchanged; client can use cached copy.
  headers:
    ETag:
      description: Validator of the current representation.
      schema:
        type: string
```

304 is usually generated by conditional request handling or the web/cache layer. Do not describe it as an empty JSON response.

### HEAD

A HEAD request asks for the metadata corresponding to GET without receiving response content. If the documentation describes a HEAD operation, do not declare a body schema for its response. Headers such as `Content-Type` or `Content-Length` may carry metadata corresponding to GET's representation under HTTP HEAD rules; that does not mean HEAD returns a body.

## 10. Reading OpenAPI Output to Confirm a Response Has No Content

After the application starts, open `/v3/api-docs` or the corresponding group URL. The expected 204 response looks like:

```json
{
  "description": "Product deleted successfully; response has no body."
}
```

The response object may also include `headers`, `links`, or relevant extensions, but it should not contain a `content` field.

You can use `curl` and `jq` to check:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/products/{id}"].delete.responses["204"]'
```

Verify that `content` does not exist:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/products/{id}"].delete.responses["204"] | has("content")'
```

The expected output is `false`. If it returns `true`, inspect the response object to see which schema or media type was added.

## 11. Testing Both HTTP Responses and OpenAPI Docs

A controller test should verify status 204 and an empty body:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    ProductService productService;

    @Test
    void deleteReturnsNoContentWithoutBody() throws Exception {
        mockMvc.perform(delete("/api/products/42"))
            .andExpect(status().isNoContent())
            .andExpect(content().string(""));
    }
}
```

`@MockitoBean` is from Spring Test 6.2 or later (commonly used with Spring Boot 3.4+ or 4). For older versions, use `@MockBean` from `org.springframework.boot.test.mock.mockito.MockBean`. Tests must mock services and configure security according to the application.

In addition to runtime tests, verify the OpenAPI document:

```java
@Test
void deleteOperationDocuments204WithoutContent() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.paths['/api/products/{id}'].delete.responses['204'].content"
        ).doesNotExist());
}
```

If the application protects API Docs endpoints with Spring Security, tests need appropriate authentication or security test setup. With multiple groups, check the document URL of the group containing the operation under test.

## 12. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| 204 docs contain `ProductResponse` schema | Method returns a DTO even though runtime intends no body | Switch to `ResponseEntity<Void>` or `void` with status 204 |
| Swagger UI displays a JSON body for DELETE 204 | Annotation includes `@Content` or schema inferred from return type | Remove content from the 204 response and inspect OpenAPI JSON |
| API returns empty 200 instead of 204 | Status not set explicitly | Use `ResponseEntity.noContent()` or `@ResponseStatus(NO_CONTENT)` |
| API returns `{}` or `data: null` | Controller returns a DTO/wrapper with a body | Use `Void` if the contract truly has no content |
| 204 response has `Content-Length` or a body | Response handled like a regular response or a filter writes content | Inspect filters, advice, servlet response, and test at the HTTP layer |
| 204 response lacks a description | Relying only on automatic inference or missing annotation | Declare `@ApiResponse(responseCode = "204", description = "...")` |
| Inappropriate shared error response attached to 204 | Generic response/customizer applied too broadly | Check `@ControllerAdvice`, `override-with-generic-response`, and customizers |
| Schema is wrong only in one group | Group has a customizer or endpoint with a different return type | Inspect that group's OpenAPI document directly |

## 13. Checklist for Bodyless Responses

- [ ] Chose a status code aligned with HTTP semantics; do not use 204 for in-progress work.
- [ ] Controller uses `ResponseEntity<Void>` or `void` with `@ResponseStatus(NO_CONTENT)` when returning only 204.
- [ ] Do not return an empty DTO, generic wrapper, or `null` to simulate no-content.
- [ ] `@ApiResponse` for 204 has `responseCode` and `description`, without `content`.
- [ ] OpenAPI Response Object 204 has no `content` or dummy schema.
- [ ] If metadata headers are needed, document them in `responses.204.headers`.
- [ ] Responses with bodies on other statuses are documented separately with appropriate media types and schemas.
- [ ] Checked the effect of generic responses, `@ControllerAdvice`, and customizers.
- [ ] Runtime tests confirm status 204 and an empty body.
- [ ] OpenAPI tests confirm the 204 response has no `content` field.
- [ ] Checked every published documentation group.

A bodyless response must be expressed clearly from the controller to the documentation. Use `ResponseEntity<Void>` or `void` with an appropriate status so Spring returns valid HTTP semantics; use `@ApiResponse` without `content` so OpenAPI does not invent a dummy schema. Testing both HTTP responses and OpenAPI JSON prevents documentation from asking clients to read a payload the server never sends.
