# Text, JSON, XML, and Multi-Media-Type Responses

A REST API can return plain text, JSON, XML, or multiple formats for the same operation. In Spring MVC, the return type, `ResponseEntity`, the `produces` attribute, and `HttpMessageConverter` instances determine the actual response content. Springdoc documents those formats under `responses.content` in OpenAPI so clients know which data representations they can receive.

When documenting responses, keep three pieces aligned: the controller must produce the right content, Spring must select an appropriate converter, and OpenAPI must publish the matching media types and schemas. Adding a `@Content` annotation to the docs does not automatically enable the application to serialize XML or return plain text.

## 1. Response Media Types in HTTP and OpenAPI

An HTTP response carries a status code, headers, and optionally a body. The `Content-Type` header indicates the format of the actual body:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "title": "Spring Boot Fundamentals"
}
```

In OpenAPI 3, response content is documented per status code and media type:

```yaml
responses:
  '200':
    description: Book found
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/BookResponse'
```

Each key in `content` is a media type the operation can return. Its value holds the schema and optionally `example`, `examples`, or appropriate encodings. A single response can advertise multiple media types.

| Component | Role |
| --- | --- |
| Response `Content-Type` | Format of the body the server actually sends |
| Request `Accept` | Response format the client wants to receive |
| `produces` in Spring mapping | Restricts the response media types the handler declares it supports |
| `responses.content` in OpenAPI | Describes response media types, schemas, and examples |
| `HttpMessageConverter` | Converts Java objects into response bodies according to media type |

Do not confuse `requestBody.content` with `responses.content`: the former describes data sent by clients, while the latter describes data returned by the server.

## 2. Plain Text Responses with `text/plain`

For an endpoint returning a plain text string, you can return `String` and declare `produces = MediaType.TEXT_PLAIN_VALUE`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping(path = "/api/status", produces = MediaType.TEXT_PLAIN_VALUE)
    @Operation(
        summary = "Get service status",
        responses = @ApiResponse(
            responseCode = "200",
            description = "Status in plain text",
            content = @Content(
                mediaType = MediaType.TEXT_PLAIN_VALUE,
                schema = @Schema(type = "string", example = "UP"),
                examples = @ExampleObject(value = "UP")
            )
        )
    )
    public ResponseEntity<String> status() {
        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .body("UP");
    }
}
```

The actual response has body `UP` and `Content-Type: text/plain`. In OpenAPI, the schema has type `string`. Do not describe this body as a JSON object.

Test with curl:

```bash
curl -i -H "Accept: text/plain" http://localhost:8080/api/status
```

If an endpoint returns `String` without declaring `produces` or a media type explicitly, converter selection and output format may differ from expectations. For public APIs, declare the media type explicitly and inspect the actual `Content-Type`.

## 3. JSON Responses Using DTOs

JSON is commonly used for structured responses. Return a DTO instead of assembling JSON strings manually:

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Book details returned to clients")
public record BookResponse(
    @Schema(description = "Book ID", example = "42")
    long id,

    @Schema(description = "Book title", example = "Spring Boot Fundamentals")
    String title
) {}
```

Controller:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BookQueryController {

    @GetMapping(path = "/api/books/42", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
        summary = "Get book details",
        responses = @ApiResponse(
            responseCode = "200",
            description = "Book details",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = BookResponse.class),
                examples = @ExampleObject(
                    name = "BookJson",
                    summary = "Book details in JSON",
                    value = "{\"id\":42,\"title\":\"Spring Boot Fundamentals\"}"
                )
            )
        )
    )
    public ResponseEntity<BookResponse> getBook() {
        return ResponseEntity.ok(new BookResponse(42L, "Spring Boot Fundamentals"));
    }
}
```

Spring Boot normally uses Jackson to convert DTOs into JSON. Springdoc can infer the schema from the return type; `@Schema` and `@ExampleObject` add descriptions and sample payloads for integrators.

Test request:

```bash
curl -i -H "Accept: application/json" http://localhost:8080/api/books/42
```

The response has `Content-Type: application/json` and a JSON object. Do not return a manually concatenated string like `"{\"id\":42}"` and expect it to behave like a DTO; `String` return types and object return types can be handled by different converters.

## 4. XML Responses and Message Converter Configuration

To return XML, the application needs an XML converter. With Spring Boot using Jackson, you can add the following dependency and let Spring Boot manage its version:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-xml</artifactId>
</dependency>
```

DTOs can use Jackson XML annotations to define the root element and property names:

```java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlProperty;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.media.XML;

@JacksonXmlRootElement(localName = "book")
@Schema(xml = @XML(name = "book"))
public class BookRepresentation {

    private long id;

    @JacksonXmlProperty(localName = "title")
    private String title;

    public BookRepresentation() {}

    public BookRepresentation(long id, String title) {
        this.id = id;
        this.title = title;
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
```

Controller:

```java
@GetMapping(path = "/api/books/42.xml", produces = MediaType.APPLICATION_XML_VALUE)
@Operation(
    summary = "Get book details in XML",
    responses = @ApiResponse(
        responseCode = "200",
        description = "Book details in XML",
        content = @Content(
            mediaType = MediaType.APPLICATION_XML_VALUE,
            schema = @Schema(implementation = BookRepresentation.class),
            examples = @ExampleObject(
                name = "BookXml",
                value = "<book><id>42</id><title>Spring Boot Fundamentals</title></book>"
            )
        )
    )
)
public ResponseEntity<BookRepresentation> getBookXml() {
    return ResponseEntity.ok(new BookRepresentation(42L, "Spring Boot Fundamentals"));
}
```

Sample XML response:

```xml
<book>
    <id>42</id>
    <title>Spring Boot Fundamentals</title>
</book>
```

Test request:

```bash
curl -i -H "Accept: application/xml" http://localhost:8080/api/books/42.xml
```

`produces = application/xml` and `@Content(mediaType = application/xml)` only describe the mapping and contract. If no XML converter is installed or configured, Spring cannot automatically serialize objects to XML. For XML with namespaces, attributes, or complex nesting, configure Jackson XML/JAXB and verify the actual body.

## 5. One Operation Returning JSON or XML

If a single operation supports both JSON and XML, declare both media types in `produces`. In OpenAPI, a single response can contain multiple `@Content` entries, each describing the schema and examples for one format:

```java
@GetMapping(
    path = "/api/books/42",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
@Operation(
    summary = "Get book details",
    responses = @ApiResponse(
        responseCode = "200",
        description = "Book details",
        content = {
            @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = BookRepresentation.class),
                examples = @ExampleObject(
                    name = "BookJson",
                    value = "{\"id\":42,\"title\":\"Spring Boot Fundamentals\"}"
                )
            ),
            @Content(
                mediaType = MediaType.APPLICATION_XML_VALUE,
                schema = @Schema(implementation = BookRepresentation.class),
                examples = @ExampleObject(
                    name = "BookXml",
                    value = "<book><id>42</id><title>Spring Boot Fundamentals</title></book>"
                )
            )
        }
    )
)
public ResponseEntity<BookRepresentation> getBookByNegotiation() {
    // The same DTO is serialized to JSON or XML based on Accept;
    // the XML converter uses the Jackson XML annotations on the DTO.
    return ResponseEntity.ok(new BookRepresentation(42L, "Spring Boot Fundamentals"));
}
```

The code above illustrates OpenAPI metadata for two representations. In practice, choose a DTO and converter that genuinely support both formats, or use response types fitting your API design. Do not declare `application/xml` if the converter cannot produce valid XML matching the schema and examples.

When using the same DTO for JSON and XML, inspect how Jackson JSON and Jackson XML serialize that DTO. If XML requires custom root element or field names, you can use Jackson XML annotations; verify those changes do not break the JSON response.

In OpenAPI, the output looks like:

```yaml
responses:
  '200':
    description: Book details
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/BookRepresentation'
        example:
          id: 42
          title: Spring Boot Fundamentals
      application/xml:
        schema:
          $ref: '#/components/schemas/BookRepresentation'
        example: <book><id>42</id><title>Spring Boot Fundamentals</title></book>
```

## 6. Content Negotiation with the `Accept` Header

Clients can send `Accept` to indicate the desired response format:

```http
GET /api/books/42 HTTP/1.1
Accept: application/xml
```

If the handler declares support for JSON and XML, Spring MVC selects the matching representation based on `Accept`, `produces`, and available converters. When a client requests an unsupported format, Spring can return `406 Not Acceptable`.

Example testing the same endpoint:

```bash
# Request JSON
curl -i -H "Accept: application/json" http://localhost:8080/api/books/42

# Request XML
curl -i -H "Accept: application/xml" http://localhost:8080/api/books/42

# Request an unsupported format
curl -i -H "Accept: text/csv" http://localhost:8080/api/books/42
```

When testing, inspect the actual response `Content-Type`. `Accept` is the client's preference; `Content-Type` is the format the server sent. If a request lists multiple media types with quality factors (`q`), Spring content negotiation picks an appropriate format based on priority and configuration. Never assume clients always receive the first type listed if mappings or converters do not support it.

## 7. Multiple Examples for the Same Media Type

If a response has only one media type but needs multiple examples, declare multiple `@ExampleObject` entries inside one `@Content`:

```java
@ApiResponse(
    responseCode = "200",
    description = "Product details",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ProductResponse.class),
        examples = {
            @ExampleObject(
                name = "AvailableProduct",
                summary = "Product in stock",
                value = "{\"id\":1,\"name\":\"Keyboard\",\"available\":true}"
            ),
            @ExampleObject(
                name = "UnavailableProduct",
                summary = "Product out of stock",
                value = "{\"id\":2,\"name\":\"Mouse\",\"available\":false}"
            )
        }
    )
)
```

Both examples belong to `application/json`; they are not two media types. If the response also supports XML, add a separate `@Content(mediaType = application/xml, ...)`.

Examples must conform to the schema and represent data the server can actually return. Never place personal data, tokens, session cookies, or real customer data into public examples.

## 8. Error Responses Also Need Media Types Described

Error responses usually have their own structure. For example, an application using an error DTO:

```java
public record ApiError(
    String code,
    String message
) {}
```

Can describe the error response using `@ApiResponse`:

```java
@ApiResponse(
    responseCode = "404",
    description = "Book not found",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ApiError.class),
        examples = @ExampleObject(
            value = "{\"code\":\"BOOK_NOT_FOUND\",\"message\":\"Book not found\"}"
        )
    )
)
```

If the exception handler returns errors as `application/problem+json`, publish that exact media type and the Problem Details schema. If errors are returned as `text/plain`, the schema must be `string`. Response metadata must match the `@RestControllerAdvice`, gateway, or error-handling mechanism in use.

Do not declare a response body for bodyless status codes. For example, `204 No Content` typically only needs status and description without `content`:

```java
@ApiResponse(responseCode = "204", description = "Deleted successfully")
```

## 9. Using `ResponseEntity` to Control Status and Headers

`ResponseEntity` lets the controller determine status code, headers, and body. This helps when an API returns multiple media types or needs an explicit `Content-Type`:

```java
return ResponseEntity.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .body(new BookResponse(42L, "Spring Boot Fundamentals"));
```

Or a text response:

```java
return ResponseEntity.ok()
    .contentType(MediaType.TEXT_PLAIN)
    .body("UP");
```

When using content negotiation, usually let Spring pick the media type from `Accept` and converters; avoid forcing a fixed `Content-Type` if the same operation must serve multiple representations. If code sets the content type explicitly, ensure the body matches that format.

`ResponseEntity` does not automatically generate OpenAPI documentation. Use `@ApiResponse` and `@Content` to describe the corresponding status, media type, and schema.

## 10. Roles of `@ApiResponse`, `@Content`, and `@Schema`

| Annotation | Role in response documentation |
| --- | --- |
| `@ApiResponse` | Describes an HTTP status code and the meaning of the response |
| `@ApiResponses` | Groups multiple response statuses for an operation |
| `@Content` | Describes content per media type |
| `@Schema` | Specifies the response data structure |
| `@ExampleObject` | Supplies a sample payload for a media type |
| `@Operation` | Attaches response metadata to an operation |

Springdoc can infer response schemas from controller return types. With `ResponseEntity<BookResponse>`, the library can read the body type `BookResponse`. Use explicit `@ApiResponse` annotations when you need to describe multiple statuses, media types, examples, or schemas differing from default inference.

Avoid duplicating complex metadata in multiple places when inferred results are already accurate. If explicit annotations override automatic inference, inspect the final document to ensure no responses or media types were lost.

## 11. Converter Configuration and Mapping Must Match Documentation

Spring MVC uses `HttpMessageConverter` to turn Java objects into response bodies. Common converters:

| Converter | Data typically handled |
| --- | --- |
| `StringHttpMessageConverter` | Plain text strings |
| `MappingJackson2HttpMessageConverter` | JSON via Jackson |
| `MappingJackson2XmlHttpMessageConverter` | XML via Jackson XML when dependency and converter are configured |
| `ByteArrayHttpMessageConverter` | Byte/binary data |

The actual converter list depends on dependencies, MVC configuration, and beans registered by the application. A media type listed in `produces` without a matching converter can still fail when writing the response.

When adding custom converters, check both ordering and supported media types. A converter may support multiple media types or take precedence for certain types; this is especially important when controllers return `String` or general types.

## 12. Inspecting Responses in OpenAPI and Swagger UI

After starting the application, open `/v3/api-docs` or `/v3/api-docs.yaml`. For each operation, verify:

1. Response codes (`200`, `201`, `204`, `400`, `404`, etc.) match controller behavior.
2. `responses.content` lists the right media types.
3. JSON/XML/text schemas reflect the actual body.
4. Examples are valid for their corresponding schema and media type.
5. Bodyless responses do not declare `content` erroneously.
6. Error responses match the format returned by exception handlers.

In Swagger UI, open the Responses section to review statuses and media types. Some UI versions display response examples, but Swagger UI does not prove the server actually returns those payloads. Send real requests and verify `Content-Type`, status code, and body.

Example verification commands:

```bash
# Plain text
curl -i -H "Accept: text/plain" http://localhost:8080/api/status

# JSON
curl -i -H "Accept: application/json" http://localhost:8080/api/books/42

# XML
curl -i -H "Accept: application/xml" http://localhost:8080/api/books/42
```

Adjust URLs to match actual mappings. If the same endpoint serves JSON and XML, call the same URL with different `Accept` headers and compare the returned `Content-Type`.

## 13. Common Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Response body is JSON while docs list XML | `@Content.mediaType` or `produces` mismatch | Synchronize mapping, metadata, and converters |
| XML request returns `406 Not Acceptable` | Client sent an `Accept` header not supported by the endpoint | Check `Accept` and `produces` |
| Unable to serialize XML | Missing XML converter or incompatible DTO | Add/configure Jackson XML or JAXB and check DTO |
| Unexpected response `Content-Type` | Unexpected converter selected or wrong header set in code | Check converters, `produces`, and actual responses |
| Swagger UI does not show media type | `responses.content` missing `@Content` or UI loaded stale docs | Inspect `/v3/api-docs` and reload UI |
| `String` response handled differently from JSON object | String converter and Jackson converter serialize differently | Use a DTO for JSON; declare `text/plain` explicitly for text |
| Docs advertise nonexistent error response | `@ApiResponse` out of sync with exception handler | Document actual error responses or update handler |
| `204` displays unnecessary body | `content` declared on a bodyless response | Remove `content` and keep only status/description |
| Client does not receive desired media type | Media type unsupported by converters or `Accept` mismatch | Check negotiation and runtime converters |

## 14. Checklist for Multi-Format Responses

- [ ] `produces` lists the exact media types the endpoint actually returns.
- [ ] `Accept` is treated as the client's requested response format.
- [ ] `responses.content` has an entry for each supported media type.
- [ ] JSON uses an appropriate DTO schema.
- [ ] XML has a configured and tested converter and XML mappings.
- [ ] Plain text uses `text/plain` and a `string` schema.
- [ ] Multiple examples of the same format live inside one `@Content`; multiple formats use multiple `@Content` entries.
- [ ] Error and success responses have accurate statuses, media types, and schemas.
- [ ] Bodyless responses such as `204` do not declare content.
- [ ] Checked OpenAPI JSON/YAML, Swagger UI, and actual HTTP responses.

Springdoc publishes response media types and schemas so clients know which formats the server can return. Spring MVC and its message converters determine the actual body. When `produces`, converters, `ResponseEntity`, and `@ApiResponse` stay aligned, an API can support plain text, JSON, XML, or multiple representations with documentation that accurately reflects behavior.
