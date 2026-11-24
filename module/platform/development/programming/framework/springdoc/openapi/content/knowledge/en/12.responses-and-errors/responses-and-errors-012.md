# Reusing Responses in `components`

In a Spring Boot API, many operations return the same type of response. For instance, multiple endpoints can return `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, or `500 Internal Server Error` with an identical error structure. Repeating full response descriptions on every controller method quickly makes the OpenAPI document verbose, hard to maintain, and prone to drift.

OpenAPI provides `components.responses` to define a reusable Response Object. Each operation references that definition via `$ref`. Springdoc-openapi can include these components in the generated specification via `OpenAPI` configuration and reference them from `@ApiResponse(ref = ...)`.

Key reminder: a component describes the response content; the status code is still declared on the operation. The same response component can be shared across operations when semantics, body, headers, and media types are genuinely identical.

## 1. Why Use `components.responses`?

Suppose an application exposes these endpoints:

- `GET /api/documents/{id}` retrieves a document.
- `DELETE /api/documents/{id}` deletes a document.
- `GET /api/users/{id}` retrieves a user.
- `GET /api/orders/{id}` retrieves an order.

All four endpoints can return `404 Not Found` with the same error structure containing `code`, `message`, `timestamp`, and `path`. If every operation defines schemas and examples inline, the same rules get duplicated repeatedly.

Reusing responses provides several benefits:

- **Consistency**: every operation shares the exact same error response structure.
- **Maintainability**: update descriptions, headers, or examples in one component.
- **Readability**: each operation's `responses` section stays concise and focused on endpoint-specific outcomes.
- **Contract verification**: you can assert that operations reference a standard response component.
- **Reduced drift**: prevents one endpoint from documenting `404` with a `message` field while another documents `detail` even though runtime returns the same JSON.

Do not reuse merely to save lines. If two responses have different semantics or structures, define two separate components even if they share the same underlying error schema.

## 2. Structure of `components.responses`

In OpenAPI, `components` holds reusable definitions. `components.responses` holds named Response Objects:

```yaml
components:
  responses:
    NotFound:
      description: Resource not found
      content:
        application/json:
          schema:
            type: object
            properties:
              code:
                type: string
              message:
                type: string
```

A Response Object typically contains:

| Part | Purpose |
|---|---|
| `description` | Explains the meaning of the response. This field is required. |
| `headers` | Describes returned headers outside standard headers handled separately. |
| `content` | Maps media types to body schemas and examples. |
| `links` | Describes links to follow-up operations. |

A response component does not contain a status code. The status is the key under the operation's `responses`, such as `'404'`, `'401'`, or `default`.

## 3. Defining Shared Responses and Referencing Them with `$ref`

The example below defines one error schema and three reusable responses:

```yaml
openapi: 3.1.0
info:
  title: Document API
  version: 1.0.0
paths:
  /api/documents/{id}:
    get:
      summary: Get document by ID
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Document found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/DocumentResponse'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '404':
          $ref: '#/components/responses/NotFound'
        '500':
          $ref: '#/components/responses/InternalServerError'

components:
  schemas:
    DocumentResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        name:
          type: string
    ApiError:
      type: object
      required: [code, message]
      properties:
        code:
          type: string
        message:
          type: string
        timestamp:
          type: string
          format: date-time
        path:
          type: string
  responses:
    Unauthorized:
      description: Request is unauthenticated or credentials are invalid
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
    NotFound:
      description: Resource not found for the given ID
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
    InternalServerError:
      description: An unexpected error occurred while processing the request
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
```

Here:

- `components.schemas.ApiError` defines the shared error body structure.
- `components.responses.NotFound` defines the complete response, including description and content.
- The operation uses `$ref: '#/components/responses/NotFound'` to reference that response.
- `404` is still declared on the operation; the `NotFound` component does not determine the status code on its own.

One schema can be used across multiple response components. For instance, `ApiError` can serve as the body for `Unauthorized`, `NotFound`, and `InternalServerError` while each response keeps its own description.

## 4. Reusing Responses Across Multiple Operations

When multiple operations share the same response semantics, media types, and structures, they can reference a single component:

```yaml
paths:
  /api/documents/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'
    delete:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'

  /api/users/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'
```

All three operations share one `NotFound` definition. If the error response later gains a header or changes media type, update the component once and re-verify the dependent operations.

However, if one endpoint returns `404` meaning "Document not found" and another returns `404` meaning "User not found", consider a generic response component with a neutral description, or create separate components if resource-specific semantics need to be explicit. Avoid reusing an overly specific description across unrelated endpoints.

## 5. Defining Components in a Spring Boot Application

When springdoc generates documentation from controllers, shared responses can be registered via an `OpenAPI` bean. Springdoc merges these components into the exported specification.

### 5.1. Declaring Components Using the OpenAPI Model

Example creating an error schema and `NotFound`/`Unauthorized` responses using Swagger Core models:

```java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.IntegerSchema;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiResponseConfiguration {

    @Bean
    OpenAPI openAPI() {
        Schema<?> errorSchema = new Schema<>()
                .type("object")
                .addRequiredItem("code")
                .addRequiredItem("message")
                .addProperty("code", new StringSchema()
                        .example("DOCUMENT_NOT_FOUND"))
                .addProperty("message", new StringSchema()
                        .example("Document not found"))
                .addProperty("status", new IntegerSchema()
                        .example(404));

        Content errorContent = new Content().addMediaType(
                "application/json",
                new MediaType().schema(
                        new Schema<>().$ref("#/components/schemas/ApiError")
                )
        );

        ApiResponse notFound = new ApiResponse()
                .description("Resource not found")
                .content(errorContent);

        ApiResponse unauthorized = new ApiResponse()
                .description("Authentication required")
                .content(errorContent);

        Components components = new Components()
                .addSchemas("ApiError", errorSchema)
                .addResponses("NotFound", notFound)
                .addResponses("Unauthorized", unauthorized);

        return new OpenAPI()
                .info(new Info().title("Document API").version("1.0.0"))
                .components(components);
    }
}
```

`Components.addResponses(name, response)` registers a response by name. `Components.addSchemas(name, schema)` registers the error schema referenced by the responses. The names `NotFound`, `Unauthorized`, and `ApiError` must match `$ref` pointers in the document.

The example uses `application/json` and the `ApiError` schema for illustration. In a real application, align the media type, fields, and examples with the actual error DTO returned by controllers or `@RestControllerAdvice`.

### 5.2. Using Response Components in Controllers

Once components are registered, methods can reference them with `@ApiResponse(ref = ...)`:

```java
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import java.util.UUID;

@RestController
class DocumentController {

    @GetMapping("/api/documents/{id}")
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Document found",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = DocumentResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "401",
            ref = "#/components/responses/Unauthorized"
        ),
        @ApiResponse(
            responseCode = "404",
            ref = "#/components/responses/NotFound"
        )
    })
    DocumentResponse findById(@PathVariable UUID id) {
        return documentService.findById(id);
    }
}
```

`responseCode` specifies the key in the operation's `responses`; `ref` points to the response component. For responses with complex bodies, referencing avoids duplicating `content`, `schema`, and examples on every method.

Expected OpenAPI output shape:

```yaml
responses:
  '200':
    description: Document found
  '401':
    $ref: '#/components/responses/Unauthorized'
  '404':
    $ref: '#/components/responses/NotFound'
```

Inspect the actual output from your springdoc and Swagger Annotations versions. If `$ref` does not appear as expected, verify that the component is registered in the right OpenAPI document and that the annotation uses the `ref` attribute properly.

## 6. Reusing Responses with Multiple Media Types

A response component can define multiple representations under `content`, just like a response declared inline on an operation:

```yaml
components:
  responses:
    ExportReady:
      description: Export file is ready
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ExportMetadata'
        application/zip:
          schema:
            type: string
            format: binary
```

When an operation references `ExportReady`, it inherits the description and both media types. Clients can choose the representation via the `Accept` header if the endpoint actually supports both JSON and ZIP.

In the controller, `produces` must match the documented media types:

```java
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import java.util.UUID;

@GetMapping(
        path = "/api/exports/{id}",
        produces = {
            MediaType.APPLICATION_JSON_VALUE,
            "application/zip"
        }
)
@ApiResponse(
        responseCode = "200",
        ref = "#/components/responses/ExportReady"
)
ResponseEntity<?> downloadExport(@PathVariable UUID id) {
    // Return JSON or ZIP based on content negotiation.
    return exportService.getRepresentation(id);
}
```

The response component describes the possible representations; the controller and message converters still perform content negotiation and emit the right `Content-Type`.

## 7. Reusing Headers and Examples Inside Responses

A response component can include headers, content, and examples, letting you reuse body-adjacent metadata as well.

### 7.1. Response Headers

Example of a `429 Too Many Requests` response with a `Retry-After` header:

```yaml
components:
  responses:
    TooManyRequests:
      description: Request rate limit exceeded
      headers:
        Retry-After:
          description: Number of seconds to wait before retrying the request
          schema:
            type: integer
            minimum: 1
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
```

When an operation references `TooManyRequests`, clients know to inspect `Retry-After` before retrying. At runtime, the server or gateway must actually send this header; declaring it in OpenAPI does not add headers to HTTP responses.

### 7.2. Shared Response Examples

Examples can be placed directly inside the Media Type Object of a response component:

```yaml
components:
  responses:
    NotFound:
      description: Resource not found
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
          examples:
            documentMissing:
              summary: Document does not exist
              value:
                code: DOCUMENT_NOT_FOUND
                message: Document not found
                status: 404
```

The example is shared across every operation referencing the component. If examples need to vary per resource, consider separate response components or sharing a schema while placing operation-level descriptions/examples in a way compatible with your OpenAPI version.

## 8. Using a Response Component with `default`

OpenAPI supports the `default` key in `responses` to cover statuses not listed individually. It can reference a shared response:

```yaml
paths:
  /api/documents/{id}:
    get:
      responses:
        '200':
          description: Document found
        '404':
          $ref: '#/components/responses/NotFound'
        default:
          $ref: '#/components/responses/UnexpectedError'
```

`default` is not a specific status code. It is a fallback response for status codes not declared individually. If the API has important errors such as `400`, `401`, `403`, `404`, or `409`, it is usually better to document them explicitly so clients know how to handle each case; `default` should act only as a fallback.

The example above assumes `components.responses.UnexpectedError` is defined in the same OpenAPI document.

Do not use `default` to hide a known success or error response. Client generators may handle explicit responses and `default` differently.

## 9. When Should You Split Response Components?

Not every response sharing a schema belongs in the same response component. Distinguish reusing a **Response Object** from reusing a **Schema Object**:

| Need | What to reuse |
|---|---|
| Same error body, same media type, same headers, and same meaning | Response component, e.g., `NotFound`. |
| Same body structure with endpoint-specific descriptions | Shared schema component; separate responses per operation. |
| Same response with different headers across operations | Base response component or shared schema; define separate responses if differing headers are part of the contract. |
| Same status with different bodies by context | Separate response components per context. |
| Same status code only, different meanings | Do not share a response based on status code alone. |

For instance, `404` for a document and `404` for an order may both use `ApiError` while needing different descriptions. You can create two responses:

```yaml
components:
  responses:
    DocumentNotFound:
      description: Document not found
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
    OrderNotFound:
      description: Order not found
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
```

Both response components share the schema while preserving resource-specific semantics.

## 10. `$ref` Rules When Using Response Objects

A response component is referenced via a Reference Object. Example:

```yaml
'404':
  $ref: '#/components/responses/NotFound'
```

Points to keep in mind:

- Local references begin with `#/components/responses/` and the component name must exist.
- Keys in `components.responses` are case-sensitive; `NotFound` and `notFound` are distinct names.
- The component must be a valid Response Object, with `description` at a minimum.
- Never point a response to `components.schemas`; schemas and responses are different object types.
- In OpenAPI 3.0, sibling fields placed next to `$ref` in a Reference Object are ignored.
- In OpenAPI 3.1, Reference Objects allow `summary` and `description` to override the corresponding metadata; other arbitrary fields are not valid extensions.

The following example does not override `content` in OpenAPI 3.0:

```yaml
'404':
  $ref: '#/components/responses/NotFound'
  content:
    application/problem+json:
      schema:
        $ref: '#/components/schemas/Problem'
```

If you need a different body or headers, create a separate response component. In OpenAPI 3.1, you can override `description` or `summary` under Reference Object rules, but you still cannot arbitrarily override `content` with sibling fields.

## 11. Verifying Response Components Exported by springdoc

After registering components and adding `@ApiResponse(ref = ...)`, open `/v3/api-docs` or your configured docs endpoint. Verify both sides:

1. `components.responses` contains the component under the expected name.
2. The component has accurate `description`, `content`, schema, headers, and examples.
3. Every `$ref` from an operation points to a real component.
4. The operation's response codes match runtime branches.
5. Schemas referenced inside the response component exist in `components.schemas`.
6. Media types in the component match the `Content-Type` returned by the server.
7. Documented headers are present in runtime responses when triggered.

Example verification using MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReusableResponseOpenApiTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsNotFoundAsReusableResponse() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                        "$.components.responses.NotFound.description"
                ).value("Resource not found"))
                .andExpect(jsonPath(
                        "$.paths['/api/documents/{id}'].get.responses['404']['$ref']"
                ).value("#/components/responses/NotFound"));
    }
}
```

Path names, groups, and descriptions in tests must match the actual document. If the spec is split across multiple `GroupedOpenApi` beans, check the matching `/v3/api-docs/{group}` URL and ensure the components are registered in every document that uses them.

## 12. Verifying Runtime Responses

A valid `$ref` does not prove the endpoint actually returns that response. Test runtime behavior for the scenarios producing each status:

```java
@Test
void returnsDocumentNotFoundResponse() throws Exception {
    mockMvc.perform(get("/api/documents/{id}", UUID.randomUUID()))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code").value("DOCUMENT_NOT_FOUND"))
            .andExpect(jsonPath("$.message").exists());
}
```

This test assumes the application turns a not-found error into a JSON response with `code` and `message`. If your application uses `ProblemDetail`, `application/problem+json`, or another error envelope, adjust the assertions and components accordingly.

Additional cases worth testing:

- `401` with body and `WWW-Authenticate` if required by the auth scheme.
- `403` accurately reflecting insufficient permissions.
- `429` with `Retry-After` if the API documents retry guidance.
- `500` using the standardized error body without leaking stack traces or internal details.
- Shared responses from `@RestControllerAdvice` genuinely matching the declared component structure.

## 13. Using Response Components in Static Docs or Multiple Groups

If a team maintains a static OpenAPI YAML/JSON file rather than generating everything from controllers, define `components.responses` directly in that file and reference them with `$ref` as shown in Section 3.

If the application uses multiple `GroupedOpenApi` definitions, each group can produce a separate document. Verify that response components are registered in the document to which the operation belongs. A `$ref` in group `internal` does not automatically mean the component exists in group `public`.

When configuring in code, use `OpenApiCustomizer` for the default document or group-attached customizers per your project setup. Choose the right customizer scope and verify every group's output; never assume one configuration bean affects every document exported by the app.

## 14. Common Pitfalls

- **Placing responses in `components.schemas`**: schemas only describe bodies; response components belong in `components.responses`.
- **Forgetting `description`**: a Response Object requires a description.
- **Wrong component name or case mismatch**: `$ref` fails to resolve if the component name does not match.
- **Using `$ref` to a schema in a response slot**: point to `#/components/responses/...`, or wrap the schema inside a response object.
- **Declaring a component without referencing it**: components do not attach themselves to operations or generate runtime responses.
- **Adding `$ref` without registering the component**: produces broken references or validator errors.
- **Reusing a response solely because of status code**: status `404` does not mean every endpoint shares the same description, body, and headers.
- **Placing `content` beside `$ref` to override it**: sibling fields are ignored per Reference Object rules; create a separate component when content differs.
- **Assuming response annotations alter runtime behavior**: `@ApiResponse` documents OpenAPI only; controllers/advice still have to return the right status and body.
- **Overlooking document groups**: a component may exist in the default document while missing from the group under inspection.

## 15. Workflow for Implementing Shared Responses

1. **Identify repeated responses**: find responses sharing identical semantics, media types, schemas, and headers.
2. **Extract shared schemas**: create `components.schemas` entries for bodies reused across responses.
3. **Create Response Objects**: add descriptions, content, headers, examples, or links under `components.responses`.
4. **Register components**: declare them in OpenAPI YAML or add them via a springdoc `OpenAPI` bean/customizer.
5. **Reference from operations**: use `$ref` in YAML or `@ApiResponse(ref = "#/components/responses/...")`.
6. **Verify generated docs**: confirm components exist and every reference resolves cleanly.
7. **Run runtime tests**: confirm controllers or exception handlers return the exact status, content type, body, and headers.
8. **Review contract changes**: when modifying a shared component, assess every referencing operation because changes affect multiple clients.

## 16. Review Checklist

- [ ] Shared responses are placed in `components.responses`.
- [ ] Shared body schemas are placed in `components.schemas`.
- [ ] Every Response Object has a clear `description`.
- [ ] Media types and schemas reflect runtime bodies.
- [ ] Headers and examples are declared when clients need them.
- [ ] Operations reference components properly via `$ref` or `@ApiResponse(ref = ...)`.
- [ ] Status codes remain declared on operations.
- [ ] Component names and JSON Pointers match exact casing.
- [ ] No sibling `content` or arbitrary fields sit beside `$ref` expecting overrides.
- [ ] Components are present in every published document/group.
- [ ] `/v3/api-docs` contains no broken references.
- [ ] Integration tests verify both runtime responses and OpenAPI references.

## 17. References

- [OpenAPI Specification 3.1.2 – Components Object](https://spec.openapis.org/oas/v3.1.2.html#components-object)
- [OpenAPI Specification 3.1.2 – Response Object](https://spec.openapis.org/oas/v3.1.2.html#response-object)
- [OpenAPI Specification 3.1.2 – Reference Object](https://spec.openapis.org/oas/v3.1.2.html#reference-object)
- [Swagger Annotations – `@ApiResponse`](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/io/swagger/v3/oas/annotations/responses/ApiResponse.html)
- [Swagger Core – OpenAPI model](https://github.com/swagger-api/swagger-core)
- [springdoc-openapi documentation](https://springdoc.org/)

`components.responses` lets you define a Response Object once and reuse it across operations. Reuse when semantics, schemas, media types, and headers truly match; split into separate responses when descriptions differ while still sharing underlying schemas. Finally, verify `$ref` entries in OpenAPI and actual HTTP responses so documentation and application uphold one contract.
