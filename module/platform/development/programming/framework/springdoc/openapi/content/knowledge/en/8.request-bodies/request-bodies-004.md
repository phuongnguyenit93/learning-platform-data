# Multiple Content Types for the Same Operation

An endpoint can accept the same data in multiple formats. For example, an order creation operation might accept JSON from a web application and XML from a legacy integration system. In OpenAPI, request formats are declared under `requestBody.content`; each media type can share the same schema or use its own separate schema.

With Spring Boot, three parts must stay synchronized: the controller mapping must accept the corresponding `Content-Type` headers, message converters must be able to read each format, and the springdoc documentation must accurately describe those media types and schemas. Declaring a content type in OpenAPI alone does not make the server automatically support that type.

## 1. Distinguishing `Content-Type` and `Accept`

These two HTTP headers control opposite directions:

| Header | Direction applied | Meaning |
| --- | --- | --- |
| `Content-Type` | Request sent to server | Indicates the format in which the request body is encoded. |
| `Accept` | Response returned to client | Indicates the format in which the client wants to receive the response. |

Example of a client sending JSON:

```http
POST /api/orders
Content-Type: application/json
Accept: application/json

{"customerId":"C-100","items":[{"sku":"KB-01","quantity":2}]}
```

If the same operation also accepts XML, the client can send:

```http
POST /api/orders
Content-Type: application/xml
Accept: application/json

<createOrderRequest>
  <customerId>C-100</customerId>
  <items>
    <item><sku>KB-01</sku><quantity>2</quantity></item>
  </items>
</createOrderRequest>
```

In the second example, the request body is XML while the response can still be JSON because `Content-Type` and `Accept` serve two different purposes. An API can accept JSON and XML while returning only JSON; in that case, request and response documentation must be described independently.

## 2. How does OpenAPI describe multiple media types?

In OpenAPI, `requestBody.content` is a map whose keys are media types. Each key holds a schema and may have its own examples or encoding:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
    application/xml:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
```

An HTTP request has only one primary body format at a time, indicated by `Content-Type`. The JSON and XML entries in the documentation are alternatives for the same operation, not two bodies that must be sent simultaneously.

Each media type can reference the same schema when the data structure is equivalent. If the formats have different structures, a separate schema can be declared for each media type. However, the documentation must accurately reflect the data that the controller and converters can actually read.

## 3. Accepting JSON and XML in the same controller method

In Spring MVC, the `consumes` attribute on a mapping declares the media types the method accepts. For example, both JSON and XML are converted into the same `CreateOrderRequest` DTO:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping(consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }, produces = MediaType.APPLICATION_JSON_VALUE)
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
```

This mapping allows Spring to select the method when a request arrives with one of the two declared `Content-Type` values. `produces` indicates that the method returns a JSON response. The body is read into the same Java type; the service does not need to know whether the client sent JSON or XML as long as both converters produce the same DTO.

Spring Boot typically configures a Jackson JSON converter out of the box in web applications. To read XML with Jackson, the project needs an appropriate XML module—commonly `jackson-dataformat-xml`—and must ensure the XML converter is registered. Without a suitable converter, even if `consumes` declares XML, the server still cannot deserialize the body as expected.

Example Maven dependency for XML:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-xml</artifactId>
</dependency>
```

When using Spring Boot dependency management, you normally do not need to specify the Jackson module version manually. For Gradle configuration:

```kotlin
implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-xml")
```

Serialization/deserialization behavior also depends on annotations, XML element names, and DTO structure. Test with real XML payloads, especially with nested collections, namespaces, and XML attributes.

## 4. Describing JSON and XML with springdoc

Springdoc can infer the request body from `@RequestBody`, the DTO type, and the mapping's `consumes`. When you need explicit control over the schema per media type, use `@Operation` with `@Content`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.http.MediaType;

@Operation(
    summary = "Create order",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Order details, accepts JSON or XML",
        required = true,
        content = {
            @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = CreateOrderRequest.class)
            ),
            @Content(
                mediaType = MediaType.APPLICATION_XML_VALUE,
                schema = @Schema(implementation = CreateOrderRequest.class)
            )
        }
    )
)
```

Here, the fully qualified `@io.swagger.v3.oas.annotations.parameters.RequestBody` is used to distinguish the OpenAPI description annotation from `org.springframework.web.bind.annotation.RequestBody` used on the controller parameter. The two annotations have distinct roles:

- Spring `@RequestBody` instructs the framework to read the HTTP body and bind it to the argument.
- Swagger `@RequestBody` describes the request body in the OpenAPI specification, including description, required, and content.

The `@Operation` block must be placed on the corresponding controller method. If `consumes` on the mapping only accepts JSON while the annotation advertises XML as well, the documentation will diverge from runtime behavior. Keep the media type lists consistent in both places, or rely on inferred metadata when no customization is needed.

The generated OpenAPI document may look similar to:

```yaml
paths:
  /api/orders:
    post:
      summary: Create order
      requestBody:
        required: true
        description: Order details, accepts JSON or XML
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
          application/xml:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
```

## 5. Using separate schemas for each media type

Not every format has to share the same schema. For example, a legacy import API might accept a flat XML structure while JSON uses a modern nested structure. OpenAPI allows each media type to be described with its own schema:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
    application/xml:
      schema:
        $ref: '#/components/schemas/LegacyOrderDocument'
```

If the controller method accepts a single DTO, the application must have a mechanism to convert both representations into that DTO, such as a custom `HttpMessageConverter`, deserializer, or adapter at the ingestion layer. You can accept the body as a `String` or `byte[]` and parse it manually, though you then assume responsibility for format checking, parse errors, size limits, and input security.

When two formats have different business rules or completely different processing logic, consider splitting them into separate operations/endpoints instead of publishing one operation with misleading schemas. OpenAPI allows only one operation per path and HTTP method pair; avoid creating two Java methods with the same path and HTTP method just to represent two bodies and expecting documentation to merge accurately automatically.

## 6. Receiving `multipart/form-data` with files and metadata

`multipart/form-data` is commonly used when a request contains files alongside metadata fields. This is also a request body media type, though its schema usually differs from standard JSON/XML.

Example controller receiving a file and a JSON metadata part:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@PostMapping(
    path = "/api/documents",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
DocumentResponse upload(
        @RequestPart("file") MultipartFile file,
        @RequestPart("metadata") CreateDocumentMetadata metadata) {
    return documentService.upload(file, metadata);
}
```

DTO describing the multipart body:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.web.multipart.MultipartFile;

public class UploadDocumentRequest {

    @Schema(type = "string", format = "binary", description = "File to upload")
    private MultipartFile file;

    @Schema(description = "Document metadata details")
    private CreateDocumentMetadata metadata;

    // Getters and setters
}
```

You can describe the schema and encoding of each part in OpenAPI:

```java
@Operation(
    summary = "Upload document",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
            schema = @Schema(implementation = UploadDocumentRequest.class),
            encoding = @Encoding(
                name = "metadata",
                contentType = MediaType.APPLICATION_JSON_VALUE
            )
        )
    )
)
```

Add the `io.swagger.v3.oas.annotations.media.Encoding` import and place the annotation on the upload method. `format: binary` indicates that the file part contains binary data; `encoding` specifies that the `metadata` part is sent as JSON. Part names in the schema must match those in `@RequestPart`.

The corresponding specification may look like:

```yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        properties:
          file:
            type: string
            format: binary
          metadata:
            $ref: '#/components/schemas/CreateDocumentMetadata'
      encoding:
        metadata:
          contentType: application/json
```

With multipart, the boundary is generated by the client in the `Content-Type` header; do not manually hardcode `multipart/form-data` without a boundary when using `curl` or browser FormData. Let the HTTP tool generate the boundary automatically.

## 7. Receiving `form-urlencoded`, `text/plain`, and binary data

Beyond JSON/XML/multipart, an operation can accept other body types if the application has corresponding converters.

### `application/x-www-form-urlencoded`

This format sends key/value pairs in the body. Spring provides `FormHttpMessageConverter`, which can read `MultiValueMap`:

```java
@PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
Receipt submitForm(@RequestBody MultiValueMap<String, String> form) {
    return formService.submit(form);
}
```

OpenAPI can describe the body as an object:

```yaml
requestBody:
  required: true
  content:
    application/x-www-form-urlencoded:
      schema:
        type: object
        required:
          - email
        properties:
          email:
            type: string
            format: email
          campaign:
            type: string
```

If using `@ModelAttribute` to bind form fields, verify how springdoc represents them in your current version. In Spring MVC, `@ModelAttribute` typically binds data from request parameters; it is not equivalent in all cases to a `requestBody` described with `application/x-www-form-urlencoded`.

### `text/plain`

For plain text bodies, the controller can accept `String`:

```java
@PostMapping(path = "/notes", consumes = MediaType.TEXT_PLAIN_VALUE)
void addNote(@RequestBody String content) {
    noteService.add(content);
}
```

The OpenAPI schema is a string:

```yaml
requestBody:
  content:
    text/plain:
      schema:
        type: string
```

### `application/octet-stream`

For raw binary bodies, you can accept `byte[]` or `Resource` depending on your handling strategy:

```java
@PostMapping(path = "/raw-file", consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
void uploadRaw(@RequestBody byte[] bytes) {
    fileService.store(bytes);
}
```

The OpenAPI schema typically uses `type: string`, `format: binary`:

```yaml
requestBody:
  content:
    application/octet-stream:
      schema:
        type: string
        format: binary
```

For large files, avoid reading the entire payload into a `byte[]` if that causes memory pressure. Consider streaming or stream-based storage and enforce upload size limits at both the proxy and application layers.

## 8. Declaring `consumes` and `produces` consistently

`consumes` and `produces` on Spring mappings control handler selection by media type:

```java
@PostMapping(
    path = "/api/orders",
    consumes = {"application/json", "application/xml"},
    produces = "application/json"
)
```

- `consumes` filters requests by `Content-Type`.
- `produces` filters responses by `Accept`.
- `requestBody.content` describes the body formats the operation accepts.
- `responses.<status>.content` describes the response formats the operation returns.

Do not use `produces` to declare request formats. Likewise, do not add XML to `requestBody.content` if the controller does not accept XML or lacks a converter to read XML.

If `Content-Type` is not accepted by the mapping, Spring typically returns HTTP 415 Unsupported Media Type. If the client requests a response format via `Accept` that the method cannot produce, Spring typically returns HTTP 406 Not Acceptable. These two errors differ from body parse errors (typically 400) and data validation errors.

Example of an operation that accepts JSON/XML but only returns JSON:

```yaml
paths:
  /api/orders:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
          application/xml:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Order created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
```

If the operation returns both JSON and XML, the response must list both media types in `responses.<status>.content`, and the controller must have the corresponding converters/serializers and `produces` setting.

## 9. Testing each content type

Do not just check whether Swagger UI shows multiple options. Send real requests with each `Content-Type` and verify the controller reads the data:

```bash
# JSON
curl -i http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"customerId":"C-100","items":[]}'

# XML
curl -i http://localhost:8080/api/orders \
  -H "Content-Type: application/xml" \
  -H "Accept: application/json" \
  -d '<createOrderRequest><customerId>C-100</customerId></createOrderRequest>'

# Multipart
curl -i http://localhost:8080/api/documents \
  -F "file=@document.pdf" \
  -F 'metadata={"title":"Contract"};type=application/json'
```

Then fetch `/v3/api-docs` or `/v3/api-docs.yaml` and cross-check:

1. Does the operation have the exact same path and HTTP method as the controller?
2. Does `requestBody.required` accurately reflect whether the body is required?
3. Does `requestBody.content` list all actually supported media types?
4. Does the schema for each media type have the right structure and data types?
5. For multipart, do part names, binary format, and encoding match the controller?
6. Does response content reflect `produces` and the actual serializer?
7. Does a request with an invalid `Content-Type` return 415; is a malformed body handled with an appropriate error?

Have separate integration tests for each representation. A passing test sending JSON does not prove that XML or multipart also works.

## 10. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| OpenAPI shows JSON and XML, but XML returns 415 | Mapping lacks XML in `consumes` | Add the media type to the mapping if the app genuinely supports it |
| XML is accepted but fails to bind to DTO | Missing XML message converter or DTO incompatible with XML structure | Configure Jackson XML/JAXB converter and test the payload |
| Swagger UI only shows one format | Request body metadata was overridden or inferred only one content type | Explicitly declare `@Operation`/`@Content` and inspect generated JSON |
| Multipart file appears as a plain string | Schema does not declare `format: binary` | Use `@Schema(type = "string", format = "binary")` |
| Multipart metadata parses incorrectly | Part name or part content type mismatches | Synchronize `@RequestPart`, schema, and `encoding` |
| Valid request yet response returns 406 | `Accept` does not match `produces` or response converter | Check `Accept`, `produces`, and response converters |
| Form-urlencoded described as query parameters | Used `@ModelAttribute` and doc inference did not match intent | Inspect actual specification; explicitly describe request body if controller accepts form body |

## 11. Workflow for designing multiple content types

When an operation needs to accept multiple formats, follow this sequence:

1. Identify the media types clients actually need to send, such as JSON and XML.
2. Decide whether the formats share a data structure or need separate schemas.
3. Declare `consumes` on the mapping and ensure message converters can read each format.
4. Use Spring's `@RequestBody` to bind the body; add `@Operation` and `@Content` when explicit OpenAPI descriptions are needed.
5. Describe `responses.content` separately according to response formats and `produces`.
6. Inspect the JSON/YAML specification, then run integration tests for each media type and error case.

An operation can accept multiple representations, provided each representation genuinely works at runtime. When the controller, converters, and `requestBody.content` agree, clients can choose the format that suits them while still using a single operation contract.

## References

- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object)
- [OpenAPI Specification – Media Type Object](https://spec.openapis.org/oas/latest.html#media-type-object)
- [Spring Framework – HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring Framework – `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [springdoc-openapi – Documentation](https://springdoc.org/)
