# Objects, Arrays, Primitives, and Optional Request Bodies

In an HTTP API, the request body is the data payload a client sends to the server to create, update, or perform an operation. When described in OpenAPI, the body does not always have to be a JSON object. It can be an object, an array, a primitive value such as a string, number, or boolean, binary data, a form, or even optional. Choosing the right structure lets clients know exactly what content to send and helps Spring Boot bind the data into controller parameters properly.

With springdoc-openapi, body details are usually inferred from parameters annotated with `@RequestBody`, Java types, and descriptive annotations. When finer control is needed, you can use the OpenAPI `RequestBody`, `Content`, `Schema`, and `ExampleObject` annotations. This lesson focuses on the top-level shape of the body, the difference between an optional body and optional fields, and how to express these cases in OpenAPI and Spring MVC.

## 1. Where does the request body live in OpenAPI?

In OpenAPI 3.x, the request body is described by the `requestBody` field inside an operation. This field contains:

- `description`: explains the purpose or rules of the submitted data.
- `required`: indicates whether the entire request body is mandatory.
- `content`: maps media types to their corresponding content descriptions.

Example of an operation accepting a JSON object:

```yaml
paths:
  /api/v1/products:
    post:
      summary: Create product
      requestBody:
        required: true
        description: Product details to create.
        content:
          application/json:
            schema:
              type: object
              required:
                - name
              properties:
                name:
                  type: string
                price:
                  type: number
      responses:
        '201':
          description: Product created.
```

`content` is a map, so an operation can accept multiple media types if the server genuinely supports them. For example, the same logical body could be accepted as `application/json` or `application/xml`, though each media type needs an appropriate schema and handling logic.

Do not confuse `requestBody.required` with `required` inside a schema. The first applies to the entire body; `required` inside an object schema lists the mandatory properties within that object.

## 2. JSON objects: the common choice for multi-field requests

A JSON object represents an entity or a dataset with named fields. It is suitable when a request has multiple properties, needs per-field validation, or is likely to expand in the future.

Example:

```json
{
  "name": "Mechanical keyboard",
  "price": 1250000,
  "active": true
}
```

Corresponding schema:

```yaml
type: object
required:
  - name
  - price
properties:
  name:
    type: string
    minLength: 1
    maxLength: 120
  price:
    type: number
    format: double
    minimum: 0
  active:
    type: boolean
    default: true
```

In this example, `name` and `price` are required fields; `active` may be omitted. When the client omits `active`, the server may apply a default value if the application implements that behavior. The `default` value in OpenAPI is descriptive and does not automatically populate a DTO or database field.

### 2.1. Required fields and optional fields

For an object schema, the `required` list defines the fields the client must provide:

```yaml
type: object
required:
  - email
  - displayName
properties:
  email:
    type: string
    format: email
  displayName:
    type: string
  phone:
    type: string
```

Here `email` and `displayName` are required; `phone` is optional. Fields omitted from `required` do not have to be sent. That does not mean the server must accept arbitrary values or auto-generate default values.

In Java, Bean Validation is commonly used to validate input:

```java
public record CreateCustomerRequest(
    @NotBlank
    @Email
    String email,

    @NotBlank
    @Size(max = 100)
    String displayName,

    @Size(max = 30)
    String phone
) {
}
```

With springdoc, the schema can be inferred from the DTO type and validation annotations if supporting dependencies and configuration are present. Inspect the generated JSON/YAML document to confirm which fields appear in `required`, `format`, `minLength`, or `maxLength`.

### 2.2. Omitted fields, null, and default values

These three states must be distinguished:

| Data sent by client | Possible meaning |
|---|---|
| Field omitted | Client did not provide the property |
| Field has value `null` | Client explicitly provided an empty/null value |
| Field has a concrete value | Client provided that value |

The business meaning of an omitted field versus a `null` field depends on the API contract. For example, in a `PATCH`, omitting `phone` might mean keeping the existing phone number, whereas sending `phone: null` might mean clearing the phone number. If the API cannot distinguish between the two cases due to DTO mapping behavior, choose a clear convention and document it.

OpenAPI 3.0 uses `nullable: true` to permit `null` values in a schema:

```yaml
type: object
properties:
  phone:
    type: string
    nullable: true
```

In OpenAPI 3.1, `null` is described following JSON Schema—for instance using a union type of `string` and `null` or `anyOf`. The syntax must match the OpenAPI version published by the document. Do not mix 3.0's `nullable` into a 3.1 schema as if the two notations meant the exact same thing.

A `default` value does not make a field required either. If the client omits a field, the server only applies a default when the code or binding mechanism explicitly implements it.

## 3. Top-level array in a request body

A request body can be a JSON array directly instead of a wrapping object:

```json
[
  {
    "productId": 101,
    "quantity": 2
  },
  {
    "productId": 205,
    "quantity": 1
  }
]
```

The schema looks like:

```yaml
type: array
minItems: 1
maxItems: 100
items:
  type: object
  required:
    - productId
    - quantity
  properties:
    productId:
      type: integer
      format: int64
    quantity:
      type: integer
      minimum: 1
```

`type: array` describes the body as an array; `items` describes the type of each element. You can use `minItems`, `maxItems`, and `uniqueItems` to document array limits if they are actual API rules.

A top-level array suits operations that accept a pure list, such as importing multiple IDs or performing bulk updates under a fixed rule. However, if the request needs additional metadata such as data source, processing mode, idempotency key, or notes, an object wrapping an array is usually easier to extend.

Example of a wrapping object containing a list:

```json
{
  "source": "web-checkout",
  "items": [
    {
      "productId": 101,
      "quantity": 2
    },
    {
      "productId": 205,
      "quantity": 1
    }
  ]
}
```

A wrapping object also makes it possible to add new properties without changing the top-level shape of the request. Whichever shape you choose, keep the contract simple and appropriate for the operation.

## 4. Top-level primitive types

OpenAPI allows a request body to be a primitive JSON value: `string`, `number`, `integer`, or `boolean`. For example, an API might directly accept a search string:

```json
"springdoc-openapi"
```

Schema:

```yaml
type: string
minLength: 2
maxLength: 100
```

Or an API might directly accept an integer:

```yaml
type: integer
minimum: 1
maximum: 10
```

And a boolean:

```yaml
type: boolean
```

Primitives work well when the body has exactly one value with crystal-clear semantics. However, for APIs that may need additional properties in the future, an object is usually more extensible. For instance, instead of sending `"springdoc-openapi"`, a client could send `{"query":"springdoc-openapi","language":"en"}` if the operation needs more context.

In Spring MVC, a JSON integer body can be mapped to the corresponding Java type. For plain text, explicitly declare the `text/plain` media type:

```java
@PostMapping(path = "/search", consumes = MediaType.TEXT_PLAIN_VALUE)
public SearchResult search(
    @RequestBody String query
) {
    return searchService.search(query);
}

@PutMapping("/settings/page-size")
public void updatePageSize(
    @RequestBody Integer pageSize
) {
    settingsService.updatePageSize(pageSize);
}
```

The Java type and message converters determine how content is converted. A `String` body with `text/plain` differs from a quoted JSON string with `Content-Type: application/json`. Declare the exact media type the endpoint actually accepts.

If the contract calls for a top-level JSON string, do not assume every Spring MVC configuration will map it identically to `text/plain` into a `String` parameter. The choice of Java type and `HttpMessageConverter` should be verified against the application's converter ordering; `JsonNode` or a wrapper DTO can be used when explicit handling is needed.

## 5. Optional request body: `required` at the `requestBody` level

An operation can allow clients to call it without sending a body. In that case, OpenAPI describes:

```yaml
requestBody:
  required: false
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/UpdatePreferencesRequest'
```

`required: false` means the entire request body may be absent. It does not mean every field inside the object is optional. Conversely, a required body can still contain many optional fields:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        required:
          - displayName
        properties:
          displayName:
            type: string
          phone:
            type: string
```

In the second example, the client is required to send a JSON body and must include `displayName`; `phone` may be omitted. These are two distinct levels of requiredness.

### 5.1. Mapping an optional body in Spring MVC

Spring MVC lets you declare `required = false` on `@RequestBody`:

```java
@PatchMapping("/preferences")
public PreferencesResponse updatePreferences(
    @RequestBody(required = false) UpdatePreferencesRequest request
) {
    if (request == null) {
        return preferencesService.getCurrent();
    }
    return preferencesService.update(request);
}
```

When no body is sent, Spring can pass `null` for the non-required parameter. Code must handle this case safely. If the parameter remains required by default, a request without a body typically causes a request-reading error before reaching controller logic.

With springdoc, Spring's `@RequestBody` annotation is used to detect the request body. Depending on the springdoc version and annotation placement, `required` can be inferred from the Spring parameter. After adding `required = false`, open `/v3/api-docs` and check that `requestBody.required` is `false`. If the generated docs do not reflect it properly, you can declare the OpenAPI description explicitly.

### 5.2. Overriding metadata with OpenAPI annotations

You can use OpenAPI annotations to describe the request body more clearly:

```java
import io.swagger.v3.oas.annotations.parameters.RequestBody;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.PatchMapping;

@PatchMapping("/preferences")
@Operation(
    summary = "Update preferences",
    requestBody = @RequestBody(
        required = false,
        description = "The body can be omitted to read back the current preferences.",
        content = @Content(
            schema = @Schema(implementation = UpdatePreferencesRequest.class)
        )
    )
)
public PreferencesResponse updatePreferences(
    @org.springframework.web.bind.annotation.RequestBody(required = false)
    UpdatePreferencesRequest request
) {
    if (request == null) {
        return preferencesService.getCurrent();
    }
    return preferencesService.update(request);
}
```

Here there are two annotations with the simple name `RequestBody`: one from Spring MVC for request binding, and one from OpenAPI for documentation. The example uses the fully qualified Spring annotation on the parameter to avoid import conflicts. When using the OpenAPI annotation at the operation level, inspect the generated documentation to confirm the schema and `required` flag are accurate.

## 6. Absent body, empty body, and JSON `null` are not the same

The three requests below have different meanings:

| Request body | Meaning at the HTTP/JSON layer |
|---|---|
| No body bytes sent | No request body content |
| Sends `{}` | Empty JSON object present |
| Sends `null` | JSON content with value `null` |

With `{}`, the server receives an object with no properties. With `null`, the JSON parser reads a `null` value rather than an empty object. When no body is sent, the message converter may not be invoked or the optional parameter receives `null`, depending on the parameter type and configuration.

If the API accepts an optional body, clearly state the behavior when the body is absent. If the API accepts an empty object to trigger a default action, document the `{}` case separately. If JSON `null` is accepted, ensure the Java type, message converters, and validation support that exact behavior.

Do not rely on `required = false` alone to imply that both `{}` and `null` are valid. This flag addresses whether the body can be absent; rules for the body's content are still governed by the schema and the application.

## 7. Declaring a request body in Springdoc: from DTO to schema

For object bodies, the most common approach is creating a dedicated DTO and placing it on the `@RequestBody` parameter. Springdoc reads the DTO type to generate the schema:

```java
public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    String name,

    @NotNull
    @DecimalMin("0.0")
    BigDecimal price,

    Boolean active
) {
}

@RestController
@RequestMapping("/api/v1/products")
public class ProductController {

    @PostMapping
    public ResponseEntity<ProductResponse> create(
        @Valid @RequestBody CreateProductRequest request
    ) {
        ProductResponse created = productService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

If the body is a top-level array, the parameter type can be a `List` of an element DTO:

```java
@PostMapping("/products/batch")
public List<ProductResponse> createBatch(
    @Valid @RequestBody List<@Valid CreateProductRequest> requests
) {
    return productService.createBatch(requests);
}
```

The generated schema should have `type` `array` and `items` pointing to the `CreateProductRequest` schema. If rules require a non-empty list or item count limits, add appropriate validation to the collection and verify those constraints appear in the documentation.

Bean Validation annotations express input constraints. For the schema to generate accurately, the project needs the validation integration dependency and compatible versions. After generating docs, verify `required` fields, `minLength`, `maxLength`, `minimum`, and `format`.

If you need to explain additional rules that the schema does not express adequately, use `@Schema`:

```java
public record CreateProductRequest(
    @Schema(
        description = "Product name displayed to customers.",
        example = "Mechanical keyboard"
    )
    @NotBlank
    @Size(max = 120)
    String name,

    @Schema(
        description = "Selling price in the store's currency.",
        example = "1250000",
        minimum = "0"
    )
    @NotNull
    @DecimalMin("0.0")
    BigDecimal price
) {
}
```

Do not reuse a response DTO as a request just because the two structures currently look alike. Request and response may have different required rules—for instance, clients must not send `id`, `createdAt`, or server-managed status fields.

## 8. Describing request examples with `ExampleObject`

Examples help integrators grasp the body structure faster than schemas alone. Examples can be declared for a media type overall or per media type:

```java
@Operation(
    summary = "Create product",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = CreateProductRequest.class),
            examples = @ExampleObject(
                name = "simple-product",
                summary = "Basic product",
                value = """
                    {
                      "name": "Mechanical keyboard",
                      "price": 1250000,
                      "active": true
                    }
                    """
            )
        )
    )
)
```

An example must be valid against the schema and reflect data the server accepts. Never use real personal data or secret tokens in examples. If there are multiple request variants, give each example its own name and description—such as physical product, digital product, or a request omitting optional fields.

## 9. Multiple media types for one request body

The `content` field can describe multiple content types:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateProductRequest'
    application/xml:
      schema:
        $ref: '#/components/schemas/CreateProductXml'
```

The client selects one media type via the `Content-Type` header. The server must actually be capable of reading that media type, such as via `consumes`, `HttpMessageConverter`, or matching configuration. Merely adding XML in OpenAPI does not make Spring support XML automatically.

Some common media types:

| Media type | Data shape |
|---|---|
| `application/json` | JSON object, array, or value |
| `application/xml` | XML document |
| `application/x-www-form-urlencoded` | URL-encoded form key/value pairs |
| `multipart/form-data` | Multiple parts, commonly used for file uploads and accompanying fields |
| `text/plain` | Plain text content |
| `application/octet-stream` | Binary data |

## 10. Form and multipart request bodies

Not every request body is JSON. With `application/x-www-form-urlencoded`, fields are sent as an encoded form. With `multipart/form-data`, each part can have its own data type and headers; it is commonly used when uploading files alongside metadata.

Example multipart description:

```yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required:
          - file
        properties:
          file:
            type: string
            format: binary
          description:
            type: string
```

In Spring MVC, an endpoint can receive a file via `MultipartFile`:

```java
@PostMapping(
    path = "/documents",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public DocumentResponse upload(
    @RequestPart("file") MultipartFile file,
    @RequestPart(value = "description", required = false) String description
) {
    return documentService.upload(file, description);
}
```

With multipart, `@RequestPart` is usually appropriate when individual parts need conversion via a message converter. `@RequestParam` can also be used for form fields depending on the endpoint structure. Inspect the generated schema and ensure part names match what clients must send.

## 11. Considerations when choosing body shape

| Shape | When appropriate | Points to consider |
|---|---|---|
| Object | Request has multiple properties or needs extensibility | Clearly define required, optional, and null fields |
| Array | Sending a homogeneous list without extra metadata | Limit element count and describe per-item errors if any |
| Primitive | Body contains only a single simple value | Hard to extend when additional info is needed |
| Optional body | Operation allows clients to send no content | Must clearly define behavior when the body is absent |
| Multipart | Uploading files or combining files with metadata | Describe each part, media type, and file limits |

There is no single best shape for every API. Choose the shape that accurately expresses the business meaning and can be processed consistently on the server.

## 12. Common mistakes when describing request bodies

| Mistake | Consequence | Fix |
|---|---|---|
| Setting `requestBody.required: false` because one field is optional | Clients think the entire body can be omitted | Keep the body required and omit that field from the schema's `required` list |
| Using body `required` to describe fields | Fails to express required fields inside the object | Declare `required` at both levels for their proper purpose |
| Using `nullable` to express an optional field | Clients misunderstand and think they must send `null` | Omit the field from `required`; use `nullable` only if `null` is accepted |
| Using a top-level array despite needing metadata | Hard to add processing modes or source info | Consider an object wrapping an array |
| Advertising XML or multipart when server cannot receive it | Swagger UI sends requests that get rejected | Synchronize `content`, `consumes`, and message converters |
| Examples mismatch schema | Clients copy failing requests | Verify examples against the schema and validation |
| Assuming `default` auto-applies on the backend | Actual value may be `null` | Implement defaults in the DTO, controller, or service |
| Assuming absent body, `{}`, and `null` are identical | Ambiguous API behavior | Define and test each case separately |
| Using response DTO as request | Clients may send server-managed fields | Create a separate request DTO with writable fields only |

## 13. Inspecting request bodies in generated documentation

After starting the Spring Boot application, query the default OpenAPI endpoint:

```bash
curl -s http://localhost:8080/v3/api-docs
```

Locate the corresponding operation in `paths`, then check:

1. Does `requestBody` appear on the right operation?
2. Does body-level `required` accurately reflect whether the body can be absent?
3. Does `content` have the exact media types the controller accepts?
4. Is the top-level schema correctly `object`, `array`, `string`, `number`, `boolean`, or another content type?
5. Do fields inside the object have the right `required` list, types, limits, and nullability?
6. Do examples match the schema and validation rules?

You can use Swagger UI to enter a body and send test requests. For optional bodies, also test omitting the body completely. For JSON objects, test a complete object, an object missing required fields, an object with optional fields omitted, and `null` values if permitted by the contract.

## 14. Takeaways

- `requestBody` describes data sent by the client; `content` maps media types to schemas and examples.
- A top-level body can be an `object`, `array`, `string`, `number`, `integer`, `boolean`, or binary/form content.
- `requestBody.required` governs the entire body; `schema.required` governs required fields inside an object.
- Optional fields, nullable fields, and fields with default values are three distinct concepts.
- An absent body, an empty object `{}`, and JSON `null` carry different semantics.
- In Spring MVC, `@RequestBody(required = false)` allows the body parameter to be absent; code must handle `null`.
- Springdoc can infer schemas from DTOs and annotations, though generated docs must be verified to ensure contract accuracy.
- Every advertised media type must actually be supported by the server.

When describing request bodies with springdoc-openapi, start from the data clients need to send and the meaning of each field. Choose the right top-level shape, clarify whether the body is required, and align the schema, examples, and Spring MVC data binding. That way, Swagger UI and client generators can produce requests that match your API contract.
