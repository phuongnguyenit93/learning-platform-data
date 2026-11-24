# Representing JSON, Forms, Multipart, and Binary Data

An HTTP API can receive or return data in many formats: JSON, URL-encoded forms, multipart forms with file attachments, or a byte stream such as PDFs and images. With **springdoc-openapi**, the goal is for the OpenAPI document to accurately describe the data formats that the Spring Boot controller actually accepts and returns. When the contract is accurately documented, integrators know which **Content-Type** to send, what the body structure looks like, and how to read the response.

## 1. Media Types Determine How Data Is Represented

HTTP uses the **Content-Type** header to indicate the format of the body in a request or response. The **Accept** header indicates which formats the client wants to receive in the response. These two headers serve different roles:

- **Content-Type**: format of the data currently being sent.
- **Accept**: response format that the client can handle.
- **consumes** in Spring MVC: restricts the media types the endpoint accepts in the request.
- **produces** in Spring MVC: declares the media types the endpoint can return.

Some common media types:

| Media type | Representation | Common scenarios |
| --- | --- | --- |
| **application/json** | JSON object or array | Creating, updating, and querying resources via an API |
| **application/x-www-form-urlencoded** | **key=value** pairs encoded in the body | Simple forms such as login or submitting filters |
| **multipart/form-data** | Multiple data parts in one body, each with its own headers | Uploading files with metadata or multiple files |
| **application/octet-stream** | Raw byte sequence | Uploading or downloading binary data without multipart structure |
| **application/pdf**, **image/png** | Bytes of a specific format | Returning PDF documents or images |

Do not treat JSON, forms, and multipart as different ways of writing the same body. Each format has its own encoding rules, Spring binding mechanism, and OpenAPI schema.

## 2. JSON: Representing Structured Objects

JSON is suited for requests with multiple related data fields. Spring MVC typically uses **@RequestBody** to convert JSON into a DTO and uses **@ResponseBody** or **ResponseEntity** to write the result as JSON. In a REST controller, method return values are normally written to the response through Spring's message converters.

DTO example:

~~~java
public record CreateOrderRequest(
    @NotBlank
    @Schema(description = "Customer code")
    String customerCode,

    @Positive
    @Schema(description = "Product quantity")
    int quantity
) {}

public record OrderView(
    String id,
    String customerCode,
    int quantity,
    String status
) {}
~~~

Controller explicitly declaring media types:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @Operation(summary = "Create an order")
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Order created",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = OrderView.class)
            )
        ),
        @ApiResponse(
            responseCode = "400",
            description = "Invalid input data"
        )
    })
    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<OrderView> create(
        @Valid @RequestBody CreateOrderRequest request
    ) {
        OrderView result = new OrderView(
            "ORD-1001",
            request.customerCode(),
            request.quantity(),
            "CREATED"
        );
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }
}
~~~

Springdoc can infer the request body from **@RequestBody**, the DTO type, **consumes**, and the return type. Annotations **@Schema**, **@Operation**, **@ApiResponse**, and **@Content** add descriptions or explicitly define schemas when the contract needs finer detail.

Corresponding JSON request:

~~~json
{
  "customerCode": "CUS-100",
  "quantity": 2
}
~~~

In OpenAPI, the request body and responses are described separately. Abbreviated example:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
responses:
  '201':
    description: Order created
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/OrderView'
~~~

If an endpoint accepts JSON yet returns a different media type, document **consumes** and **produces** separately. Do not assume the response is always JSON merely because the request body is JSON.

## 3. URL-Encoded Forms: Simple Fields in the Body

**application/x-www-form-urlencoded** encodes fields as a string of key-value pairs, similar to the data after the question mark in a URL, but placed in the body. Example:

~~~text
username=linh&password=secret
~~~

Spring MVC can bind form-formatted data into an object using **@ModelAttribute**. If you want OpenAPI to show this as a request body with media type **application/x-www-form-urlencoded**, you can explicitly declare **requestBody** with OpenAPI annotations:

~~~java
public record LoginForm(
    @NotBlank
    @Schema(description = "Username")
    String username,

    @NotBlank
    @Schema(description = "Password", format = "password")
    String password
) {}

@PostMapping(
    value = "/api/sessions",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(
    summary = "Log in with form",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            schema = @Schema(implementation = LoginForm.class)
        )
    )
)
SessionView login(
    @Parameter(hidden = true) @ModelAttribute LoginForm form
) {
    // Authenticate credentials and create a session.
    return sessionService.login(form);
}
~~~

In the example, **SessionView** and **sessionService** represent the application's response type and business service. When springdoc also infers **@ModelAttribute** as separate parameters, inspect the generated document to avoid duplicating form fields in both query parameters and the request body; use **@Parameter(hidden = true)** on the binding parameter if needed and keep the request body schema explicit.

OpenAPI example:

~~~yaml
requestBody:
  required: true
  content:
    application/x-www-form-urlencoded:
      schema:
        type: object
        required:
          - username
          - password
        properties:
          username:
            type: string
          password:
            type: string
            format: password
~~~

URL-encoded forms fit text-field data. When files must be sent, use **multipart/form-data** instead of trying to stuff file contents into a URL-encoded field.

## 4. Multipart: Combining Files and Metadata

**multipart/form-data** splits the body into multiple parts. Each part has its own name, headers, and content. A single request can contain a PDF file part, a JSON metadata part, and additional text parts.

Spring MVC typically uses **MultipartFile** to receive files and **@RequestPart** to read individual parts. **@RequestPart** is especially useful when a part needs conversion via a message converter, such as JSON metadata.

Defining the upload document schema:

~~~java
public record UploadMetadata(
    @NotBlank
    String title,
    String category
) {}

public record DocumentUpload(
    @Schema(
        description = "PDF file to upload",
        type = "string",
        format = "binary"
    )
    MultipartFile file,

    @Schema(description = "Document metadata")
    UploadMetadata metadata
) {}
~~~

Controller receiving each part and describing the overall schema:

~~~java
@PostMapping(
    value = "/api/documents",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(
    summary = "Upload a document",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
            schema = @Schema(implementation = DocumentUpload.class),
            encoding = {
                @Encoding(
                    name = "metadata",
                    contentType = MediaType.APPLICATION_JSON_VALUE
                ),
                @Encoding(
                    name = "file",
                    contentType = MediaType.APPLICATION_PDF_VALUE
                )
            }
        )
    )
)
DocumentView upload(
    @RequestPart("file") MultipartFile file,
    @Valid @RequestPart("metadata") UploadMetadata metadata
) {
    return documentService.store(file, metadata);
}
~~~

**@Schema(type = "string", format = "binary")** indicates that the **file** property holds binary data. **@Encoding** describes the media type of each part; the name in **@Encoding.name** must match the property name in the multipart schema. If the metadata part is JSON, the client must send that part with **Content-Type: application/json** so Spring selects the proper message converter.

The abbreviated OpenAPI representation looks like this:

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
          metadata:
            $ref: '#/components/schemas/UploadMetadata'
      encoding:
        metadata:
          contentType: application/json
        file:
          contentType: application/pdf
~~~

Points to verify when documenting multipart:

- Part names in the controller, schema property names, and encoding names must match.
- File fields must be represented with **type: string**, **format: binary**.
- JSON metadata must declare the right **contentType** if clients must send that part as JSON.
- With multiple files, clearly specify whether the API accepts a single file or a list of files so the schema reflects the right data type.
- Clients usually let the HTTP library generate the **Content-Type** header with its boundary. Do not manually set **multipart/form-data** without a boundary when sending requests via browsers or multipart-capable libraries.

## 5. Binary Data: Uploading and Downloading Byte Streams

When an API only transfers file content without extra metadata or multiple parts, you can use **application/octet-stream** or a specific media type such as **application/pdf** or **image/png**. In this case, the body is a raw sequence of bytes.

### Uploading Binary Data

Spring MVC can bind the body into **byte[]**, **Resource**, or another suitable type. Example using **byte[]**:

~~~java
@PutMapping(
    value = "/api/documents/{id}/content",
    consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
@Operation(
    summary = "Replace document content",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_OCTET_STREAM_VALUE,
            schema = @Schema(type = "string", format = "binary")
        )
    )
)
@ApiResponse(responseCode = "204", description = "Content replaced")
void replaceContent(
    @PathVariable String id,
    @RequestBody byte[] content
) {
    documentService.replaceContent(id, content);
}
~~~

For large files, consider streaming or using an appropriate **Resource** to avoid holding the entire content in memory. The chosen Java type should fit the application's size limits, storage approach, and processing capacity.

### Downloading Binary Data

Example endpoint returning a PDF:

~~~java
@GetMapping(
    value = "/api/documents/{id}/content",
    produces = MediaType.APPLICATION_PDF_VALUE
)
@Operation(summary = "Download PDF document content")
@ApiResponse(
    responseCode = "200",
    description = "PDF content",
    content = @Content(
        mediaType = MediaType.APPLICATION_PDF_VALUE,
        schema = @Schema(type = "string", format = "binary")
    )
)
ResponseEntity<Resource> download(@PathVariable String id) {
    Resource resource = documentService.loadAsResource(id);
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_PDF)
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            ContentDisposition.attachment()
                .filename(resource.getFilename())
                .build()
                .toString()
        )
        .body(resource);
}
~~~

In OpenAPI, binary responses also use schema **type: string**, **format: binary**. The **Content-Disposition** header tells clients whether the content should be displayed inline or downloaded as a file. If the API returns multiple formats, declare each media type in response **content** and ensure the controller actually supports them.

## 6. How springdoc Generates Request Bodies and Responses

Springdoc reads Spring mappings and annotations to generate the OpenAPI specification. The primary signals include:

| Spring element | Meaning in the OpenAPI contract |
| --- | --- |
| Spring's **@RequestBody** | Request body converted from the HTTP content |
| **@RequestPart** | A part within a multipart request |
| **@ModelAttribute** | Data bound into an object from request parameters or form fields |
| **consumes** | Accepted media types for the request body |
| **produces** | Response media types |
| **@Schema** | Describes schemas, fields, data types, formats, and constraints |
| **@Operation** and OpenAPI **@RequestBody** | Adds descriptions or declares the request body explicitly |
| **@ApiResponse**, **@Content** | Describes response status codes and content |

Springdoc normally infers schemas for DTOs and media types from controllers automatically. Use explicit OpenAPI annotations when Java types are insufficient to express the contract, when documenting multiple media types, when form binding produces unintended documentation, or when declaring binary formats and multipart encodings.

In source code, two annotations share the name **RequestBody**: Spring's **org.springframework.web.bind.annotation.RequestBody** for binding data, and **io.swagger.v3.oas.annotations.parameters.RequestBody** for documenting the OpenAPI contract. The examples above spell out the full OpenAPI class name in **@Operation.requestBody** to avoid confusion.

## 7. Adding Examples and Checking the Generated Document

Examples help integrators understand how to send bodies, especially for forms and multipart requests. **@ExampleObject** inside **@Content** can provide JSON examples or appropriate illustrative payloads. Examples must match the operation's schema and media type.

After starting the application, inspect the JSON document at the default OpenAPI endpoint **/v3/api-docs** or your configured path. For each operation, confirm:

1. **requestBody.content** contains the exact media types accepted by the endpoint.
2. JSON schemas include all expected fields, data types, required properties, and constraints.
3. URL-encoded forms appear under the request body instead of being mistaken for query parameters.
4. Multipart has an object schema, exact part names, and file fields marked **format: binary**.
5. Binary requests use the proper media type and binary schema.
6. **responses** accurately describe status codes, media types, schemas, or returned binary data.
7. Important headers such as **Content-Disposition** are documented when clients need them.

Opening Swagger UI to test requests is also helpful, though UI rendering alone does not prove the entire contract is right. Inspect the OpenAPI JSON directly, especially for forms and multipart, as these are cases where springdoc may need extra annotations to distinguish request bodies from parameters.

## 8. Common Issues

**Documentation shows form fields as query parameters.** Check how the controller binds **@ModelAttribute** or **@RequestParam**. If the contract requires a form body, declare **requestBody.content** with **application/x-www-form-urlencoded** and adjust parameter inference to avoid duplicate entries.

**Swagger UI does not show a file picker button.** Verify that the file field's schema has **type: string** and **format: binary**, the operation uses **multipart/form-data** or an appropriate binary media type, and property names match part names.

**Metadata part fails to parse into an object.** Ensure the client sends the proper **Content-Type** for that part, such as **application/json**, and the controller uses **@RequestPart** so Spring selects the matching message converter.

**Documentation claims the API returns JSON while it actually returns a file.** Declare **produces** with the actual media type, such as **application/pdf**, and document the response with a binary schema. Check the actual **Content-Type** in the response as well.

**Large file uploads cause high memory usage or size errors.** Check Spring Boot and deployment server multipart limits, API business limits, and how files are read and stored. The OpenAPI specification documents the contract but does not enforce upload limits for the application by itself.

## 9. Summary of Choices

| Need | Recommended media type | Spring MVC binding | OpenAPI schema representation |
| --- | --- | --- | --- |
| Send structured objects | **application/json** | **@RequestBody** with DTO | Object and properties |
| Send simple form fields | **application/x-www-form-urlencoded** | **@ModelAttribute** or appropriate form binding | Object inside request body |
| Send files with metadata | **multipart/form-data** | **@RequestPart**, **MultipartFile** | Object with binary and metadata properties |
| Send or receive raw bytes | **application/octet-stream** or specific media type | **@RequestBody byte[]** / **Resource** | **type: string**, **format: binary** |

Choose the media type according to the endpoint's actual data, document requests and responses separately, and verify the generated OpenAPI document. That is how to ensure Swagger UI and OpenAPI-generated clients share an accurate understanding of the application's HTTP contract.
