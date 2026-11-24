# Creating a Multipart Request with a File and JSON Information

An upload API often needs to receive both a file's contents and metadata describing that file within the same HTTP request. For example, a client sends a document file together with JSON containing the title, document type, and related case reference code. HTTP multipart/form-data allows splitting a request body into multiple parts, each with its own name, headers, and content.

With Spring Boot, you can use Spring MVC MultipartFile or Spring WebFlux FilePart to receive the file. The JSON metadata part is bound into a DTO using RequestPart. Springdoc-openapi needs to describe the request body as multipart/form-data, where the file part has a string/binary schema and the metadata part references the DTO's JSON schema.

## 1. Target outcome

The practice API exposes the endpoint:

~~~text
POST /api/documents
Content-Type: multipart/form-data
~~~

The request consists of two parts:

| Part name | Content-Type | Content |
|---|---|---|
| file | image/png, application/pdf, or supported file type | Bytes of the uploaded file |
| metadata | application/json | JSON describing the file |

Example metadata:

~~~json
{
  "title": "Service Agreement",
  "category": "LEGAL",
  "referenceCode": "CASE-2026-015"
}
~~~

A successful response returns the document ID, file name, content type, and saved metadata. In this example, the endpoint returns HTTP 201 Created.

## 2. Why use multipart/form-data?

multipart/form-data splits the request body into multiple independent sections. Each part has a Content-Disposition containing the field name and may have its own Content-Type.

A request can contain:

- A file part containing the file bytes.
- A metadata part containing JSON.
- Additional parts if the API requires extra separate fields.

Do not convert files into Base64 inside JSON unless the API has a specific requirement. Base64 inflates payload size, increases encoding/decoding overhead, and forces both client and server to process the entire file as a JSON string.

multipart/form-data is suitable when a single operation must receive multiple data types in the same request body.

## 3. Creating a DTO for metadata

Metadata is a JSON object, so it should be modeled using a dedicated DTO:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

@Schema(
        name = "DocumentMetadata",
        description = "Metadata describing the uploaded document"
)
public record DocumentMetadata(
        @Schema(
                description = "Document title",
                example = "Service Agreement"
        )
        @NotBlank
        @Size(max = 150)
        String title,

        @Schema(
                description = "Document category",
                example = "LEGAL",
                allowableValues = {"LEGAL", "FINANCE", "OTHER"}
        )
        @NotBlank
        @Pattern(regexp = "LEGAL|FINANCE|OTHER")
        String category,

        @Schema(
                description = "Related case reference code",
                example = "CASE-2026-015"
        )
        @NotBlank
        @Size(max = 50)
        String referenceCode
) {}
~~~

The DTO has three required fields. Bean Validation checks the data when the request is bound; Schema describes the meaning and examples for OpenAPI. If category has a fixed value domain in a real application, you can use an enum instead of String with Pattern.

## 4. Describing the file part in OpenAPI

In OpenAPI, a file upload is represented by a string schema with format binary. JSON metadata is represented by an object schema or a reference to a component schema.

Overall schema example:

~~~yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required:
          - file
          - metadata
        properties:
          file:
            type: string
            format: binary
            description: File to upload
          metadata:
            $ref: '#/components/schemas/DocumentMetadata'
~~~

Property names in the schema must match the part names accepted by the controller. If the controller uses RequestPart("upload") while OpenAPI documents a file property, clients will send the wrong field name.

The metadata part can declare encoding to explicitly specify its content type:

~~~yaml
encoding:
  metadata:
    contentType: application/json
~~~

This information helps consumers understand that the metadata part must be sent as JSON rather than an arbitrary plain-text string.

## 5. Creating a reusable multipart request schema

You can create a class used solely as a documentation model:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
        name = "UploadDocumentRequest",
        description = "Request containing a file and JSON metadata"
)
public record UploadDocumentRequest(
        @Schema(
                description = "File to upload",
                type = "string",
                format = "binary"
        )
        String file,

        @Schema(
                description = "Document JSON metadata",
                implementation = DocumentMetadata.class
        )
        DocumentMetadata metadata
) {}
~~~

This class describes the multipart structure for OpenAPI. The controller can still accept each part as MultipartFile and DocumentMetadata. There is no need to serialize this documentation class as an actual JSON body.

If springdoc already infers the right schema from controller parameters, a separate documentation model may not be needed. When the output does not render the metadata part as intended, use Swagger Core's RequestBody annotation to explicitly specify the multipart schema.

## 6. Installing dependencies for Spring MVC

A Spring MVC application needs the Web starter, validation, and springdoc UI if you want Swagger UI:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>2.x.y</version>
    </dependency>
</dependencies>
~~~

Replace 2.x.y with the springdoc v2 version compatible with your project's Spring Boot version. If Swagger UI is not needed, use the corresponding WebMVC API starter.

Spring Boot usually auto-configures the multipart resolver for Spring MVC. You can set request size limits using application properties.

## 7. Receiving multipart requests with Spring MVC

Spring MVC uses MultipartFile to receive file contents:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/documents")
class DocumentController {

    private final DocumentService documentService;

    DocumentController(DocumentService documentService) {
        this.documentService = documentService;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(
            operationId = "uploadDocument",
            summary = "Upload a document with JSON metadata",
            requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
                    required = true,
                    content = @Content(
                            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
                            schema = @Schema(
                                    implementation = UploadDocumentRequest.class
                            )
                    )
            )
    )
    @ApiResponse(
            responseCode = "201",
            description = "Document created",
            content = @Content(
                    mediaType = MediaType.APPLICATION_JSON_VALUE,
                    schema = @Schema(implementation = DocumentResponse.class)
            )
    )
    ResponseEntity<DocumentResponse> upload(
            @RequestPart("file") MultipartFile file,
            @Valid @RequestPart("metadata") DocumentMetadata metadata) {
        // Validate the file and store the document in the service.
        return ResponseEntity.status(201).body(
                documentService.store(file, metadata));
    }
}
~~~

In the example, RequestPart("file") receives the file part and RequestPart("metadata") receives the JSON part. The consumes attribute restricts the operation to multipart/form-data.

The RequestBody annotation inside Operation is Swagger Core's OpenAPI annotation, written with its full package name to avoid confusion with Spring's RequestBody. It only describes the contract; Spring's RequestPart is what controls how the HTTP request is bound.

## 8. Declaring the response DTO

Example response after saving the document:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

@Schema(name = "DocumentResponse", description = "Saved document information")
public record DocumentResponse(
        @Schema(description = "Document ID", format = "uuid")
        UUID id,

        @Schema(description = "Original file name")
        String fileName,

        @Schema(description = "File content type")
        String contentType,

        @Schema(description = "Saved metadata")
        DocumentMetadata metadata,

        @Schema(description = "Creation timestamp")
        Instant createdAt
) {}
~~~

The response should not return file bytes if the API only confirms a successful upload. If clients need to download the file later, create a separate download endpoint and document its binary response.

## 9. Authenticating and validating the file

Do not blindly trust the file name or Content-Type sent by the client. The service should check:

- The file exists and is not empty.
- The size does not exceed the limit.
- The file type is in the list of accepted types.
- The actual contents match the file type if business rules require signature inspection.
- The file name is sanitized before saving.
- The metadata is valid and the caller has permission to attach it to the corresponding case.

Example basic check in the service:

~~~java
void validateUpload(MultipartFile file) {
    if (file == null || file.isEmpty()) {
        throw new InvalidUploadException("File must not be empty");
    }

    if (file.getSize() > 10L * 1024 * 1024) {
        throw new UploadTooLargeException("File exceeds 10 MB");
    }

    String contentType = file.getContentType();
    if (contentType == null ||
            !(contentType.equals("application/pdf")
                    || contentType.equals("image/png"))) {
        throw new UnsupportedUploadTypeException(
                "Only PDF or PNG is accepted");
    }
}
~~~

This is a basic check based on request metadata. For high security requirements, inspect file contents, scan for malware, and store files outside the application execution directory.

## 10. Configuring multipart limits in Spring MVC

You can set limits per file and for the entire request:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 12MB
      file-size-threshold: 1MB
~~~

max-file-size limits a single file; max-request-size limits the total multipart request including metadata and overhead. Choose thresholds based on business needs, memory, and reverse proxy configuration.

Proxy or API gateway limits may be lower than the application's limits. When receiving 413 Payload Too Large, inspect both the proxy layer and Spring Boot.

## 11. Variant for receiving files with Spring WebFlux

Spring WebFlux uses FilePart instead of MultipartFile. FilePart enables reactive processing of contents and transferring files to their destination without loading everything into a byte array.

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/documents")
class ReactiveDocumentController {

    private final ReactiveDocumentService reactiveDocumentService;

    ReactiveDocumentController(ReactiveDocumentService reactiveDocumentService) {
        this.reactiveDocumentService = reactiveDocumentService;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(
            operationId = "uploadDocumentReactive",
            summary = "Upload a document with JSON metadata",
            requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
                    required = true,
                    content = @Content(
                            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
                            schema = @Schema(
                                    implementation = UploadDocumentRequest.class
                            )
                    )
            )
    )
    Mono<ResponseEntity<DocumentResponse>> upload(
            @RequestPart("file") FilePart file,
            @Valid @RequestPart("metadata") Mono<DocumentMetadata> metadata) {
        return metadata.flatMap(value ->
                reactiveDocumentService.store(file, value))
                .map(response -> ResponseEntity.status(201).body(response));
    }
}
~~~

FilePart provides the filename, headers, and the ability to transfer contents to a destination. The reactive service must handle saving the file asynchronously and avoid blocking the event loop with blocking I/O operations.

If you need to call a storage library that only provides a blocking API, offload that operation to an appropriate scheduler or use a reactive client. Never perform blocking file reads directly on the event loop.

## 12. Choosing RequestPart or RequestParam?

RequestPart is suitable when a part can be decoded by an HttpMessageConverter, such as a JSON object:

~~~java
@RequestPart("metadata") DocumentMetadata metadata
~~~

RequestParam is typically suitable for simple form fields bound to a String or scalar type:

~~~java
@RequestParam("description") String description
~~~

Do not use RequestParam for complex JSON metadata if the goal is to deserialize an application/json part into a DTO. Use RequestPart so Spring chooses the message converter based on the part's Content-Type.

## 13. Sending requests with curl

Example sending a PDF file with JSON metadata:

~~~bash
curl -i -X POST http://localhost:8080/api/documents \
  -F 'file=@./contract.pdf;type=application/pdf' \
  -F 'metadata={"title":"Service Agreement","category":"LEGAL","referenceCode":"CASE-2026-015"};type=application/json'
~~~

The two -F flags create two separate parts. The file part uses the file's name and content type. The metadata part declares type=application/json so Spring can select the JSON message converter.

Do not manually set the overall Content-Type header to multipart/form-data in curl without specifying a boundary yourself. Curl generates a boundary automatically and appends it to Content-Type. Overriding the header without a boundary can prevent the server from parsing the multipart body.

## 14. Sending requests with Postman

In Postman:

1. Select method POST and URL /api/documents.
2. Open the Body tab and choose form-data.
3. Add key file, change the key type to File, and select a file.
4. Add key metadata, leaving the type as Text.
5. Enter the JSON metadata into the value of metadata.
6. Set the Content-Type of the metadata part to application/json if your Postman version supports per-part headers.
7. Send the request and inspect the status and response body.

If Postman sends metadata as text/plain, a controller accepting a DTO via RequestPart may return 415 Unsupported Media Type or a conversion error. Check the headers of each individual part, not just the overall request headers.

## 15. Inspecting the generated OpenAPI schema

After running the application, download the document:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Inspect the operation's request body:

~~~bash
jq '.paths["/api/documents"].post.requestBody.content["multipart/form-data"].schema' openapi.json
~~~

The schema must have an object with two properties: file and metadata. The file property must have type string, format binary. The metadata property must reference DocumentMetadata or have an equivalent inline schema.

If using the UploadDocumentRequest model in the Operation annotation, check the components:

~~~bash
jq '.components.schemas.UploadDocumentRequest' openapi.json
jq '.components.schemas.DocumentMetadata' openapi.json
~~~

Check both the part names in the schema and the names in RequestPart. Both places must match so clients generated from OpenAPI send the right multipart fields.

## 16. Checking encoding of the metadata part

When metadata is JSON, OpenAPI can describe encoding:

~~~yaml
requestBody:
  content:
    multipart/form-data:
      schema:
        $ref: '#/components/schemas/UploadDocumentRequest'
      encoding:
        metadata:
          contentType: application/json
~~~

If Swagger UI or a client generator does not display the right Content-Type for the metadata part, check whether the document has encoding.metadata.contentType. You may need to customize the OpenAPI request body via annotations or a customizer depending on the springdoc version.

Do not rely solely on the Swagger UI interface. OpenAPI JSON is the source to confirm the media type and schema consumers actually receive.

## 17. Testing Spring MVC with MockMvc

For Spring MVC applications, you can create a MockMultipartFile for each part:

~~~java
@Test
void uploadAcceptsFileAndJsonMetadata() throws Exception {
    MockMultipartFile file = new MockMultipartFile(
            "file",
            "contract.pdf",
            "application/pdf",
            "sample-pdf-content".getBytes(StandardCharsets.UTF_8));

    MockMultipartFile metadata = new MockMultipartFile(
            "metadata",
            "",
            "application/json",
            """
            {
              "title": "Service Agreement",
              "category": "LEGAL",
              "referenceCode": "CASE-2026-015"
            }
            """.getBytes(StandardCharsets.UTF_8));

    mockMvc.perform(multipart("/api/documents")
                    .file(file)
                    .file(metadata))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.fileName").value("contract.pdf"))
            .andExpect(jsonPath("$.metadata.category").value("LEGAL"));
}
~~~

Ensure the test class configures MockMvc and imports the required static matchers. File content in the test is dummy data to test binding; if the service reads actual PDF content, use a valid PDF fixture.

## 18. Testing WebFlux with WebTestClient

With WebFlux, you can send a multipart body using MultipartBodyBuilder:

~~~java
@Test
void reactiveUploadAcceptsFileAndJsonMetadata() {
    MultipartBodyBuilder builder = new MultipartBodyBuilder();
    builder.part("file", new ByteArrayResource(
                    "sample-content".getBytes(StandardCharsets.UTF_8)) {
                @Override
                public String getFilename() {
                    return "contract.pdf";
                }
            })
            .contentType(MediaType.APPLICATION_PDF);

    builder.part("metadata", """
            {
              "title": "Service Agreement",
              "category": "LEGAL",
              "referenceCode": "CASE-2026-015"
            }
            """)
            .contentType(MediaType.APPLICATION_JSON);

    webTestClient.post()
            .uri("/api/documents")
            .body(BodyInserters.fromMultipartData(builder.build()))
            .exchange()
            .expectStatus().isCreated();
}
~~~

This test confirms WebFlux receives both parts with their corresponding media types. In a real application, add response assertions and verify that the service stores the file properly.

## 19. Error handling and status codes

An upload API should define consistent error responses:

| Status | Situation |
|---|---|
| 201 Created | File and metadata were accepted and stored |
| 400 Bad Request | Missing part, malformed JSON, or validation failure |
| 401 Unauthorized | Missing authentication credentials |
| 403 Forbidden | Caller lacks permission to upload to the case |
| 413 Payload Too Large | File or total request exceeds limit |
| 415 Unsupported Media Type | Request or part has an unsupported Content-Type |
| 422 Unprocessable Content | File contents or metadata violate business rules |

Document error responses with ApiResponse so clients know the error body structure. Never let default multipart errors return stack traces or internal storage path information.

## 20. Common mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| 415 when sending metadata | Metadata part is text/plain instead of application/json | Set the part's Content-Type to application/json |
| 400 missing part | Field name sent by client does not match RequestPart | Align file/metadata names |
| OpenAPI shows only file, not metadata | Springdoc failed to infer the DTO part properly | Document multipart requestBody with Schema or a customizer |
| Swagger UI does not allow entering JSON metadata | Multipart schema or encoding is unclear | Inspect requestBody schema and encoding |
| 413 even though file is below app limit | Proxy/gateway has a lower limit | Inspect all layers receiving the request |
| Empty file | Client sent wrong field or part lacks filename/content | Check multipart body and part names |
| Metadata bound as String | Used RequestParam or wrong Content-Type | Use RequestPart and application/json |
| MVC works but WebFlux fails | Used MultipartFile in reactive controller | Use FilePart and reactive I/O handling |
| WebFlux blocked during upload | Performed blocking I/O on the event loop | Use reactive operations or an appropriate scheduler |
| OpenAPI shows wrong part name | Schema annotation differs from RequestPart | Align property names and part names |

## 21. Completion checklist

- [ ] Endpoint declares consumes multipart/form-data.
- [ ] File part has a stable name and is received via MultipartFile or FilePart.
- [ ] Metadata part has a stable name and is received as a JSON DTO.
- [ ] Metadata part is sent with Content-Type application/json.
- [ ] DTO has Bean Validation and appropriate schema descriptions.
- [ ] OpenAPI requestBody has both file and metadata properties.
- [ ] File schema uses type string and format binary.
- [ ] Metadata schema references the right component.
- [ ] curl or Postman sends the request successfully.
- [ ] Integration test verifies binding of both parts.
- [ ] Size, file type, and upload permissions are validated.
- [ ] Error responses 400, 413, and 415 are documented.

## 22. Design principles

- Use multipart/form-data when a request contains both files and metadata.
- Use RequestPart for a JSON part that needs to be deserialized into a DTO.
- Use MultipartFile in Spring MVC and FilePart in Spring WebFlux.
- Give parts clear names and keep them synchronized across controller, OpenAPI schema, and client.
- Describe files as string/binary and metadata as a JSON schema.
- Send the right per-part Content-Type.
- Do not manually set the multipart boundary when using curl or HTTP clients.
- Validate size, file type, contents, and access permissions before saving.
- With WebFlux, avoid blocking I/O on the event loop.
- Test both the OpenAPI document and runtime requests.

## Conclusion

To build a multipart request containing a file and JSON information, declare an operation accepting multipart/form-data with two stably named parts: file and metadata. Spring MVC uses MultipartFile; Spring WebFlux uses FilePart. Use RequestPart to deserialize the application/json metadata part into a DTO, while the OpenAPI schema describes file as string/binary and metadata as a component schema. Test requests with curl or Postman, verify OpenAPI JSON, test binding at runtime, and handle size limits as well as media type errors. When documentation and part names align, clients can build valid requests without guessing the multipart structure.

## References

- [Spring Framework: Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html)
- [Spring Framework: Multipart Content in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html)
- [OpenAPI Specification: Multipart Requests](https://spec.openapis.org/oas/latest.html#special-considerations-for-multipart-content)
- [springdoc-openapi documentation](https://springdoc.org/)
