# Request Body Examples by Media Type

A REST API can accept multiple data formats. Clients indicate the request body format via the `Content-Type` header; Spring MVC selects the appropriate converter to read the data, while Springdoc describes those formats in OpenAPI. Each media type can use its own schema and examples, so the documentation must accurately reflect what the endpoint actually supports.

In Springdoc, the request body section is declared with `@io.swagger.v3.oas.annotations.parameters.RequestBody`. `@Content` entries inside specify media types; `@Schema` describes data structures; `@ExampleObject` provides sample payloads; `@Encoding` describes how individual parts of a multipart request are encoded. The controller still uses Spring annotations such as `@RequestBody`, `@ModelAttribute`, or `@RequestPart` to receive data at runtime.

## 1. Distinguishing `Content-Type` and `Accept`

Both headers frequently appear in requests, yet they carry different meanings:

- `Content-Type` describes the content format the client is sending to the server.
- `Accept` describes the response format the client wants back from the server.

Example:

```http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "title": "Spring Boot Fundamentals"
}
```

Here, `Content-Type` indicates that the body is JSON; `Accept` indicates that the client wants a JSON response. In Spring MVC, the `consumes` attribute of `@PostMapping` typically constrains the request media type, while `produces` constrains the response media type.

| Component | Role | Example |
| --- | --- | --- |
| `Content-Type` | Format of the incoming body | `application/json` |
| `Accept` | Desired response format | `application/json` |
| `consumes` | Media types the endpoint accepts | `application/json`, `application/xml` |
| `produces` | Media types the endpoint can return | `application/json` |
| `requestBody.content` | Media types advertised in OpenAPI | `application/json`, `multipart/form-data` |

If a client sends a `Content-Type` the endpoint does not accept, Spring typically returns `415 Unsupported Media Type`. If the server cannot produce a response matching `Accept`, `406 Not Acceptable` may occur. Documentation must list the exact implemented formats so clients construct valid requests.

## 2. Structure of multiple media types in OpenAPI

OpenAPI places supported formats inside `requestBody.content`. Each key is a media type, and each value contains the corresponding schema, examples, or encoding:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/BookRequest'
      example:
        title: Spring Boot Fundamentals
    application/xml:
      schema:
        $ref: '#/components/schemas/BookRequest'
      example: <BookRequest><title>Spring Boot Fundamentals</title></BookRequest>
```

Two media types can represent the same business data while using different payload syntax. JSON uses objects and properties; XML uses elements and attributes. Sharing a single schema is appropriate only when the data structures of both representations genuinely correspond.

## 3. `application/json`: DTO and `@RequestBody`

JSON is the standard format for REST APIs. Spring MVC uses `@RequestBody` to convert JSON into a DTO through an `HttpMessageConverter`, typically Jackson in Spring Boot Web applications.

Illustrative DTO:

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Details of the book to create")
public record BookRequest(
    @Schema(description = "Book title", example = "Spring Boot Fundamentals")
    String title,

    @Schema(description = "Publication year", example = "2025")
    Integer publicationYear
) {}
```

The controller can declare:

```java
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(
    summary = "Create book with JSON",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "JSON payload for the book",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = BookRequest.class),
            examples = @ExampleObject(
                name = "BookJson",
                summary = "Book with publication year",
                value = "{\"title\":\"Spring Boot Fundamentals\",\"publicationYear\":2025}"
            )
        )
    )
)
public BookResponse createJson(@RequestBody BookRequest request) {
    return new BookResponse(request.title(), request.publicationYear());
}
```

The code uses two `RequestBody` annotations: the Spring annotation on the method parameter reads the HTTP body; the OpenAPI annotation inside `@Operation` describes the contract. If Springdoc already infers the JSON schema accurately from the DTO, redeclaring the entire `@Content` is optional; explicit configuration is useful when specific descriptions, media types, or examples are needed.

Sample request:

```bash
curl -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"title":"Spring Boot Fundamentals","publicationYear":2025}'
```

## 4. `application/xml`: XML bodies and message converters

If the API needs to accept XML, declare `application/xml` in `consumes` and describe that media type in OpenAPI. Spring MVC must have an `HttpMessageConverter` supporting XML. With Spring Boot, a common choice is adding Jackson XML:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-xml</artifactId>
</dependency>
```

When using Spring Boot dependency management, let Boot manage the compatible Jackson version. Merely adding the media type to an OpenAPI annotation does not install a converter or enable the endpoint to read XML.

Example controller receiving the same DTO as XML:

```java
@PostMapping(
    path = "/api/books/xml",
    consumes = MediaType.APPLICATION_XML_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(
    summary = "Create book with XML",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "XML payload for the book",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_XML_VALUE,
            schema = @Schema(implementation = BookRequest.class),
            examples = @ExampleObject(
                name = "BookXml",
                summary = "Book in XML format",
                value = "<BookRequest><title>Spring Boot Fundamentals</title><publicationYear>2025</publicationYear></BookRequest>"
            )
        )
    )
)
public BookResponse createXml(@RequestBody BookRequest request) {
    return new BookResponse(request.title(), request.publicationYear());
}
```

XML examples must match the mapping rules of the converter and DTO. For XML with namespaces, attributes, wrappers, or custom element names, configure Jackson XML/JAXB accordingly and test real payloads. OpenAPI's JSON Schema format does not describe every XML detail automatically; if the XML structure has special rules, add appropriate XML metadata and inspect the generated docs.

Sample request:

```bash
curl -X POST http://localhost:8080/api/books/xml \
  -H "Content-Type: application/xml" \
  -H "Accept: application/json" \
  -d '<BookRequest><title>Spring Boot Fundamentals</title><publicationYear>2025</publicationYear></BookRequest>'
```

## 5. A single operation accepting both JSON and XML

If the same endpoint supports both formats, list both in `consumes` and include two separate `@Content` entries in the OpenAPI request body:

```java
@PostMapping(
    path = "/api/books/import",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    },
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(
    summary = "Import book using JSON or XML",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = {
            @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = BookRequest.class),
                examples = @ExampleObject(
                    name = "JsonPayload",
                    value = "{\"title\":\"Spring Boot Fundamentals\",\"publicationYear\":2025}"
                )
            ),
            @Content(
                mediaType = MediaType.APPLICATION_XML_VALUE,
                schema = @Schema(implementation = BookRequest.class),
                examples = @ExampleObject(
                    name = "XmlPayload",
                    value = "<BookRequest><title>Spring Boot Fundamentals</title><publicationYear>2025</publicationYear></BookRequest>"
                )
            )
        }
    )
)
public BookResponse importBook(@RequestBody BookRequest request) {
    return new BookResponse(request.title(), request.publicationYear());
}
```

Spring picks the converter based on the request's `Content-Type`. Both the JSON and XML converters must function at runtime. In Swagger UI, users can select the media type and its corresponding sample payload.

Do not declare multiple `@Content` entries solely to supply multiple examples. Multiple `@Content` entries represent multiple media types; multiple payloads for the same media type should use multiple `@ExampleObject` entries inside a single `@Content`.

## 6. `application/x-www-form-urlencoded`: simple form data

`application/x-www-form-urlencoded` is commonly used by HTML forms. Fields are transmitted as key/value pairs, for example:

```http
POST /api/contact HTTP/1.1
Content-Type: application/x-www-form-urlencoded

name=Lan&email=lan%40example.com&message=Hello
```

In Spring MVC, URL-encoded forms are typically read via request parameters and bound into `@ModelAttribute` or `@RequestParam` parameters. This fits the Servlet mechanism; avoid defaulting to `@RequestBody` to read raw form bodies in MVC applications.

Form DTO:

```java
public class ContactForm {
    private String name;
    private String email;
    private String message;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
}
```

Controller:

```java
@PostMapping(
    path = "/api/contact",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
@Operation(
    summary = "Submit contact form",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Contact form fields",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            schema = @Schema(implementation = ContactForm.class),
            examples = @ExampleObject(
                name = "ContactFormExample",
                value = "{\"name\":\"Lan\",\"email\":\"lan@example.com\",\"message\":\"Hello\"}"
            )
        )
    )
)
public ResponseEntity<Void> contact(@ModelAttribute ContactForm form) {
    // Process the form bound by Spring.
    return ResponseEntity.noContent().build();
}
```

In OpenAPI, the form schema is an object with matching properties. Field names must match DTO properties and Spring's binding. Springdoc may infer `@ModelAttribute` into parameters depending on version and configuration; when the contract needs to show an `application/x-www-form-urlencoded` request body, check `/v3/api-docs` and use explicit request body metadata as shown. Avoid documenting the same fields simultaneously as both query parameters and a form body unless that is the real behavior.

Sample request:

```bash
curl -X POST http://localhost:8080/api/contact \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Lan" \
  --data-urlencode "email=lan@example.com" \
  --data-urlencode "message=Hello"
```

## 7. `multipart/form-data`: files and metadata

`multipart/form-data` allows sending multiple parts in a single request, typically used when uploading files with metadata. Each part has a name and can carry its own content type. In Spring MVC, use `MultipartFile` to receive files and `@RequestPart` to receive specific parts.

DTO used to describe the multipart schema:

```java
import io.swagger.v3.oas.annotations.media.Encoding;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.web.multipart.MultipartFile;

@Schema(description = "Book file and metadata to upload")
public record UploadBookRequest(
    @Schema(type = "string", format = "binary", description = "Book cover file")
    MultipartFile file,

    @Schema(description = "Book metadata in JSON format")
    CreateBookRequest metadata
) {}
```

Controller:

```java
import io.swagger.v3.oas.annotations.media.Encoding;

@PostMapping(
    path = "/api/books/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
@Operation(
    summary = "Upload book file with metadata",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Cover file and book metadata",
        required = true,
        content = @Content(
            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
            schema = @Schema(implementation = UploadBookRequest.class),
            encoding = {
                @Encoding(name = "file", contentType = "image/png, image/jpeg"),
                @Encoding(name = "metadata", contentType = MediaType.APPLICATION_JSON_VALUE)
            }
        )
    )
)
public ResponseEntity<Void> uploadBook(
        @RequestPart("file") MultipartFile file,
        @RequestPart("metadata") CreateBookRequest metadata) {
    // Validate the file and process metadata.
    return ResponseEntity.accepted().build();
}
```

`@Encoding` describes the content type of each part. Files are typically represented in the schema as `type: string`, `format: binary`; JSON metadata is an object matching the `CreateBookRequest` schema. Part names in the schema and `@RequestPart` must match. Spring Boot's multipart configuration and file size limits must also suit deployment requirements.

Sample request:

```bash
curl -X POST http://localhost:8080/api/books/upload \
  -F "file=@cover.jpg;type=image/jpeg" \
  -F 'metadata={"title":"Spring Boot Fundamentals","publicationYear":2025};type=application/json'
```

Do not manually set the `Content-Type: multipart/form-data` header in curl when using `-F`; curl needs to generate the boundary and append it to the header. Manually setting the header without a boundary can prevent the server from separating the parts.

## 8. `text/plain`: plain text content

An endpoint can accept a plain text string, such as note content or a simple message. Spring uses `@RequestBody String` and the `text/plain` media type:

```java
@PostMapping(
    path = "/api/notes",
    consumes = MediaType.TEXT_PLAIN_VALUE
)
@Operation(
    summary = "Create text note",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Note content in plain text",
        required = true,
        content = @Content(
            mediaType = MediaType.TEXT_PLAIN_VALUE,
            schema = @Schema(type = "string", example = "Call the customer back tomorrow")
        )
    )
)
public ResponseEntity<Void> createNote(@RequestBody String note) {
    return ResponseEntity.accepted().build();
}
```

Sample request:

```bash
curl -X POST http://localhost:8080/api/notes \
  -H "Content-Type: text/plain; charset=UTF-8" \
  --data "Call the customer back tomorrow"
```

The body schema is `string`, not a JSON object. If the string contains structured data following specific rules, consider defining an explicit format or using JSON instead of leaving clients to guess how to parse it.

## 9. `application/octet-stream`: binary data

When an endpoint accepts raw binary content—such as a file without multipart—you can use `byte[]` or an appropriate stream type. OpenAPI typically represents this payload with a `type: string`, `format: binary` schema:

```java
@PostMapping(
    path = "/api/archive",
    consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
@Operation(
    summary = "Upload binary data",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Binary file content",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_OCTET_STREAM_VALUE,
            schema = @Schema(type = "string", format = "binary")
        )
    )
)
public ResponseEntity<Void> uploadArchive(@RequestBody byte[] content) {
    return ResponseEntity.accepted().build();
}
```

For large files, consider streaming or stream-based storage rather than loading the entire file into `byte[]` to avoid excessive memory usage. Size limits, file type checks, and upload permissions still must be enforced on the server.

## 10. Vendor-specific media types

An API can use an organization-specific media type, such as `application/vnd.example.book+json`. The `+json` suffix indicates JSON syntax, while the custom media type can convey versioning or specialized contract semantics.

```java
public static final String BOOK_MEDIA_TYPE = "application/vnd.example.book+json";

@PostMapping(
    path = "/api/books/vendor",
    consumes = BOOK_MEDIA_TYPE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(
    summary = "Create book using vendor media type",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = BOOK_MEDIA_TYPE,
            schema = @Schema(implementation = BookRequest.class),
            examples = @ExampleObject(
                value = "{\"title\":\"Spring Boot Fundamentals\",\"publicationYear\":2025}"
            )
        )
    )
)
public BookResponse createVendor(@RequestBody BookRequest request) {
    return new BookResponse(request.title(), request.publicationYear());
}
```

Clients must send the exact published `Content-Type`. Check message converter and content negotiation configuration in your application to verify the custom media type is accepted as expected; the `+json` suffix does not guarantee every converter or gateway accepts it automatically.

## 11. Choosing the right Spring annotation for each body type

| Media type | Common Spring MVC mechanism | Data shape |
| --- | --- | --- |
| `application/json` | `@RequestBody` | DTO or object |
| `application/xml` | `@RequestBody` with XML converter | DTO or object |
| `application/x-www-form-urlencoded` | `@ModelAttribute`, `@RequestParam` | Form fields |
| `multipart/form-data` | `@RequestPart`, `MultipartFile`, sometimes `@RequestParam` | Multiple parts, files, and metadata |
| `text/plain` | `@RequestBody String` | Plain text string |
| `application/octet-stream` | `@RequestBody byte[]` or stream type | Binary data |
| Vendor media type `+json` | `@RequestBody` with compatible converter | DTO or JSON object |

Springdoc can infer many request bodies from controller signatures. When Spring's binding does not map directly to an OpenAPI request body—such as `form-urlencoded` with `@ModelAttribute`—document it explicitly and inspect the generated output. Never let OpenAPI metadata describe a body that the controller does not actually accept.

## 12. Inspecting request bodies in OpenAPI and Swagger UI

After starting the application, open `/v3/api-docs` or `/v3/api-docs.yaml` and inspect the corresponding operation. For each request body, verify:

1. `requestBody.required` accurately reflects whether the body is required.
2. `requestBody.content` lists the exact media types the endpoint supports.
3. Each media type has a schema matching the actual payload.
4. Examples are valid against the syntax and schema of the media type.
5. For multipart, part names and `encoding` match `@RequestPart`.
6. For XML or vendor media types, actual converters support the published format.

In Swagger UI, open the operation and select the appropriate media type in the Request body section. Verify the sample payload displays accurately. When using **Try it out**, send a request to a test environment and inspect the `Content-Type` header and body in the Network tab to confirm the UI sends the right format.

Quick curl verification examples:

```bash
# JSON
curl -H "Content-Type: application/json" -d '{"title":"Book"}' http://localhost:8080/api/books

# XML
curl -H "Content-Type: application/xml" -d '<BookRequest><title>Book</title></BookRequest>' http://localhost:8080/api/books/xml

# Plain text
curl -H "Content-Type: text/plain" --data "A note" http://localhost:8080/api/notes
```

Adjust URLs and payloads to match your application's actual mappings. Curl only verifies requests against the server; OpenAPI documentation must still be checked separately.

## 13. Common errors

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| `415 Unsupported Media Type` | `Content-Type` not in `consumes` or missing converter | Synchronize media types and converter configuration |
| `406 Not Acceptable` | Server cannot return the format requested via `Accept` | Check `produces` and response converters |
| XML advertised yet XML requests fail | XML message converter not installed or configured | Add and configure Jackson XML/JAXB properly |
| Form fields appear as query parameters | Springdoc inferred `@ModelAttribute` as parameters | Inspect OpenAPI; explicitly describe form request body when contract requires |
| Multipart missing part or wrong content type | `@RequestPart` name, schema, or `@Encoding` mismatch | Synchronize part names and inspect actual requests |
| Multipart reports missing boundary | Client manually set `Content-Type` header without boundary | Let browser or curl generate the boundary |
| Large files cause high memory usage | Reading entire payload into `byte[]` or multipart limits too low | Use streaming/streamed storage and configure sensible limits |
| Swagger UI shows only one format | `requestBody.content` has only one media type or UI loaded stale docs | Inspect OpenAPI JSON and reload UI |
| Vendor media type rejected | Converter or gateway does not accept custom media type | Check content negotiation and converter settings |

## 14. Checklist for examples by media type

- [ ] Endpoint `consumes` matches the request body media types.
- [ ] `Content-Type` is clearly distinguished from `Accept` and `produces`.
- [ ] Every media type in `requestBody.content` has an accurate schema.
- [ ] Payload examples are syntactically valid for JSON, XML, form, or their respective formats.
- [ ] JSON/XML are accepted via appropriate converters.
- [ ] `form-urlencoded` is bound properly via `@ModelAttribute` or `@RequestParam`.
- [ ] Multipart has accurate part names, file schemas, and `@Encoding`.
- [ ] Text and binary use their corresponding schemas (`string` or `string/binary`).
- [ ] Vendor media types are genuinely supported at runtime.
- [ ] Verified `/v3/api-docs`, Swagger UI, and real requests.

Each media type is a contract for how clients transmit data. Spring MVC determines how payloads are received and converted; Springdoc describes the formats, schemas, and examples for client integration. When both parts remain synchronized, Swagger UI guides users to pick the right format and send valid requests for every operation.
