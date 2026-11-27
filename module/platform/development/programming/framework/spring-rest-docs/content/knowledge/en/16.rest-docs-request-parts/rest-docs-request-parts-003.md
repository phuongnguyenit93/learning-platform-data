# Required, Optional, and Absent Parts in Spring REST Docs

## 1. Determining Multipart Part Presence

A multipart request consists of multiple parts identified by their name in `Content-Disposition`. For example, a document upload operation might accept:

- `file`: the PDF file to upload.
- `metadata`: JSON containing the document title and category.
- `thumbnail`: preview image, sent only when the client has an image.

Part of the contract is defining which parts are **required**, which parts are **allowed to be absent**, and how the server responds when a required part is missing. In Spring REST Docs, `requestParts(...)` documents parts using `partWithName(...)`. By default, a descriptor requires the part to appear in the sample request; `.optional()` allows the documented part to be absent in the request used to generate the snippet.

Three layers of rules should be kept separate:

1. **Endpoint contract:** Is the client allowed to omit the part?
2. **Application validation:** How does the server handle a missing required part or an optional part with invalid content?
3. **Snippet contract:** Which descriptors can be missing from the sample request used to generate documentation without causing snippet generation to fail?

`.optional()` affects the third layer. It does not by itself make the endpoint accept requests missing that part.

This lesson belongs to the **Request parts** chapter of SPRING_REST_DOCS, where you practice generating snippets from HTTP tests using MockMvc, WebTestClient, or REST Assured, then integrating snippets with Asciidoctor/Markdown and build/CI.

After this lesson, you will be able to:

- Mark required and optional parts in `requestParts(...)`.
- Distinguish an absent part from a part that is present but empty or contains a zero-byte file.
- Test endpoint behavior when a part is missing.
- Understand the role of `@RequestPart(required = ...)` in Spring MVC.
- Combine strict/relaxed, ignored, and optional settings to accurately document a multipart contract.

## 2. Required and Optional in Descriptors

For example, the operation `POST /api/documents` accepts two parts:

- `file`: required PDF.
- `metadata`: required JSON.

An optional `preview` part:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("file")
        .description("PDF file to upload"),
    partWithName("metadata")
        .description("JSON metadata of the document"),
    partWithName("preview")
        .description("Preview image if provided by the client")
        .optional()
);
```

In strict mode, `file` and `metadata` are treated as required by default. `preview` is allowed to be absent in the sample request because its descriptor has `.optional()`.

Meaning table:

| Descriptor | Part present in sample request? | Expected result during snippet generation |
| --- | --- | --- |
| `partWithName("file")` | Yes | Validated and documented |
| `partWithName("file")` | No | Can fail snippet generation because a required part is missing |
| `partWithName("preview").optional()` | Yes | Validated and documented |
| `partWithName("preview").optional()` | No | Still able to document the part as optional |
| `partWithName("clientTrace").ignored()` | Yes | Acknowledged but not displayed in the table |
| `partWithName("clientTrace").optional().ignored()` | No | Allowed to be absent and omitted from the table |

### 2.1. Optional Does Not Mean Ignored

These two properties are independent:

- `.optional()` says the descriptor may be absent from the sample request.
- `.ignored()` says the descriptor must not be included as a row in the snippet.

For example, a `clientTrace` part that is optional and does not need to be published:

```java
partWithName("clientTrace")
    .description("Trace ID if provided by the client")
    .optional()
    .ignored();
```

If `clientTrace` is present, the descriptor acknowledges it without displaying it. If it is absent, `.optional()` allows snippet generation to proceed.

### 2.2. Optional Does Not Mean Empty Content Is Valid

```java
partWithName("preview")
    .description("Preview image if present")
    .optional();
```

The declaration above only states that the part may not appear. It does not define whether the following scenarios are valid:

- The `preview` part is present with zero bytes.
- The `preview` part has an unsupported content type.
- The `preview` part is an image with corrupted data.
- The `preview` part has a filename but no content.

Those rules belong to endpoint validation and require separate tests.

## 3. Distinguishing Absent, Empty Part, and Zero-Byte File

The following three cases can look similar when inspecting only the UI or summary logs, yet their HTTP meanings differ.

### 3.1. Absent Part

The request does not contain a `preview` part:

```text
Content-Disposition: form-data; name="file"; filename="report.pdf"
...
Content-Disposition: form-data; name="metadata"
...
```

There is no part with `name="preview"`. The client truly omitted this part.

### 3.2. Part Present with Empty Content

The request includes a `preview` part, but its content has zero bytes:

```http
Content-Disposition: form-data; name="preview"; filename="preview.png"
Content-Type: image/png

<empty body>
```

The part is still present in the multipart body. It is not absent; it is a part with a content length of zero.

### 3.3. Part Present with Empty Filename or Unspecified Filename

Depending on the client and how the multipart request is constructed, a part may have `name="preview"` without a meaningful filename. The server must define how to interpret this case. Do not infer absence solely from `MultipartFile.isEmpty()`, because `isEmpty()` can return true for a zero-byte file or data with zero bytes.

| State | Part named `preview` present? | Content bytes present? | Meaning |
| --- | --- | --- | --- |
| Absent | No | N/A | Client did not send the part |
| Empty part | Yes | No | Client sent the part but the body is empty |
| Non-empty file | Yes | Yes | Client sent a file with data |
| Zero-byte file | Yes | No | File exists as a part, but size is 0 |

**Key takeaway:** `.optional()` describes the absence of a descriptor in the sample request. It must not be used to express "if the part exists, zero-byte content is allowed".

## 4. Designing Contract and Controller for Optional Parts

In Spring MVC, an `@RequestPart` parameter is required by default. When a part is truly optional, you can declare `required = false`.

Example:

```java
@PostMapping(
    path = "/api/documents",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public ResponseEntity<Void> upload(
        @RequestPart("file") MultipartFile file,
        @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart(value = "preview", required = false)
                MultipartFile preview) {

    // Validate file and metadata according to the contract.
    // preview may be null when the client does not send the part.
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

In this example:

- `file` is required because `@RequestPart` defaults to `required = true`.
- `metadata` is required because it is required by default.
- `preview` is optional because `required = false`.

The controller still needs validation for each part's content. For instance, `file` might be non-null yet zero-byte; `metadata` might deserialize into an object yet lack a title; `preview` might have the wrong MIME type.

### 4.1. Handling Required Files

```java
if (file.isEmpty()) {
    throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "file must contain data"
    );
}
```

`file.isEmpty()` checks whether the file is empty or contains no data according to the `MultipartFile` abstraction; it does not replace verifying that the file is in the right format. To validate a PDF, the system may need to check MIME type, file signature, or use an appropriate parser.

### 4.2. Handling Optional Parts

```java
if (preview != null && !preview.isEmpty()) {
    // Check content type and process the preview image.
}
```

In this example, the server ignores `preview` if the part is absent or empty. Another contract might distinguish those two cases and reject an empty part. Reflect that choice in both the API docs and tests.

## 5. MockMvc: Generating Snippets When an Optional Part Is Absent

Assume the `POST /api/documents` endpoint accepts required `file` and `metadata`, optional `preview`, and returns `201 Created` when data is valid.

### 5.1. Descriptor Set

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

private static final RequestPartDescriptor[] DOCUMENT_PARTS = {
        partWithName("file")
                .description("PDF file to upload"),
        partWithName("metadata")
                .description("JSON metadata of the document"),
        partWithName("preview")
                .description("Preview image if provided by the client")
                .optional()
};
```

### 5.2. Test Sending the Optional Part

```java
@Test
void documentUploadWithPreview() throws Exception {
    MockMultipartFile file = new MockMultipartFile(
            "file",
            "report.pdf",
            MediaType.APPLICATION_PDF_VALUE,
            validPdfBytes()
    );

    MockMultipartFile metadata = new MockMultipartFile(
            "metadata",
            "",
            MediaType.APPLICATION_JSON_VALUE,
            """
            {"title":"Quarterly Report","category":"FINANCE"}
            """.getBytes(StandardCharsets.UTF_8)
    );

    MockMultipartFile preview = new MockMultipartFile(
            "preview",
            "preview.png",
            MediaType.IMAGE_PNG_VALUE,
            validPngBytes()
    );

    mockMvc.perform(multipart("/api/documents")
                .file(file)
                .file(metadata)
                .file(preview))
            .andExpect(status().isCreated())
            .andDo(document("documents-upload-with-preview",
                    requestParts(DOCUMENT_PARTS)));
}
```

### 5.3. Test Without Sending the Optional Part

In this test, only the two required parts are sent:

```java
@Test
void documentUploadWithoutPreview() throws Exception {
    MockMultipartFile file = new MockMultipartFile(
            "file",
            "report.pdf",
            MediaType.APPLICATION_PDF_VALUE,
            validPdfBytes()
    );

    MockMultipartFile metadata = new MockMultipartFile(
            "metadata",
            "",
            MediaType.APPLICATION_JSON_VALUE,
            """
            {"title":"Quarterly Report","category":"FINANCE"}
            """.getBytes(StandardCharsets.UTF_8)
    );

    mockMvc.perform(multipart("/api/documents")
                .file(file)
                .file(metadata))
            .andExpect(status().isCreated())
            .andDo(document("documents-upload-without-preview",
                    requestParts(DOCUMENT_PARTS)));
}
```

The second test is a direct example of **absent**: the request builder does not add a part named `preview`. Because `preview`'s descriptor is optional, the snippet can be generated with this part documented as optional.

Two different operation IDs keep the snippets separate:

```text
build/generated-snippets/
├── documents-upload-with-preview/
│   └── request-parts.adoc
└── documents-upload-without-preview/
    └── request-parts.adoc
```

Other HTTP snippets depend on configuration. The `validPdfBytes()` and `validPngBytes()` fixtures represent valid files in test resources; use real data matching the application's validator.

## 6. Testing Absent Differently from Empty Part

To be sure tests accurately reflect the contract, write separate scenarios:

| Test case | Request builder | Goal |
| --- | --- | --- |
| Omit `preview` | Do not call `.file(preview)` | Verify absent optional part |
| Send zero-byte `preview` | `.file(new MockMultipartFile("preview", "preview.png", "image/png", new byte[0]))` | Verify behavior with empty part |
| Send valid non-empty `preview` | `.file(validPreview)` | Verify part with content |
| Send `preview` with wrong MIME type | `.file(wrongContentType)` | Verify format validation |

An illustrative zero-byte test:

```java
@Test
void rejectEmptyPreviewWhenPartIsPresent() throws Exception {
    MockMultipartFile file = new MockMultipartFile(
            "file", "report.pdf", MediaType.APPLICATION_PDF_VALUE, validPdfBytes()
    );
    MockMultipartFile metadata = new MockMultipartFile(
            "metadata", "", MediaType.APPLICATION_JSON_VALUE,
            """
            {"title":"Quarterly Report","category":"FINANCE"}
            """.getBytes(StandardCharsets.UTF_8)
    );
    MockMultipartFile preview = new MockMultipartFile(
            "preview", "preview.png", MediaType.IMAGE_PNG_VALUE, new byte[0]
    );

    mockMvc.perform(multipart("/api/documents")
                .file(file)
                .file(metadata)
                .file(preview))
            .andExpect(status().isBadRequest());
}
```

Expecting `400 Bad Request` here is only valid if the contract mandates that a present part must contain a non-empty file and the controller implements the corresponding validation. If the API allows an empty preview, adjust the assertion to match the published behavior.

To test absence at the controller layer, the `@RequestPart(value = "preview", required = false)` parameter normally receives `null` when the part is not sent. For documentation tests, omitting `.file(preview)` from the request builder is the clearest way to create an absent request.

## 7. Missing Required Part: Testing Endpoint Behavior

`requestParts(...)` can fail the documentation test if a required descriptor does not appear in the sample request. This is a Spring REST Docs check, not an HTTP response from the server.

To verify the server rejects a request missing `file`, write a dedicated HTTP test:

```java
@Test
void rejectRequestWithoutRequiredFile() throws Exception {
    MockMultipartFile metadata = new MockMultipartFile(
            "metadata",
            "",
            MediaType.APPLICATION_JSON_VALUE,
            """
            {"title":"Quarterly Report","category":"FINANCE"}
            """.getBytes(StandardCharsets.UTF_8)
    );

    mockMvc.perform(multipart("/api/documents")
                .file(metadata))
            .andExpect(status().isBadRequest());
}
```

With a controller using `@RequestPart("file") MultipartFile file`, Spring MVC treats this part as required by default. If the part is missing, the framework may return an error before the controller method is invoked. The exact status depends on exception handling and application configuration; `400` is a common expectation, though the test must reflect the actual response contract.

You can document error responses separately under a different operation ID, but you should not use a failing request as the sole example for the parts table of a successful request.

## 8. Strict, Relaxed, Ignored, and Optional

| Mechanism | When a documented part is not sent | When an undocumented part is present | Shown in snippet? |
| --- | --- | --- | --- |
| `requestParts(...)` | Required by default | Can cause test to fail | Yes |
| `.optional()` | Allows the part to be absent | Does not change extra-part checks | Yes when the part is sent |
| `.ignored()` | Does not make the part optional | Acknowledges declared part | No |
| `.optional().ignored()` | Allows absence and hides from display | Does not change strict mode | No |
| `relaxedRequestParts(...)` | Descriptor still required unless optional | Allows extra parts | Only non-ignored descriptors |

For example, `clientTrace` may be sent by some clients without needing to be published:

```java
requestParts(
    partWithName("file").description("PDF file"),
    partWithName("metadata").description("JSON metadata"),
    partWithName("clientTrace")
        .description("Trace ID if provided by the client")
        .optional()
        .ignored()
);
```

Use relaxed mode when an operation accepts unlisted extensible parts. In return, tests will no longer detect new undocumented parts. For stable public contracts, strict mode and explicit optional descriptors usually provide better change control.

## 9. Communicating Required/Optional in Asciidoctor Documentation

The `request-parts.adoc` snippet describes parts based on descriptors. Descriptions should state optional status clearly when readers need to know:

```java
partWithName("preview")
    .description("Preview image; may be omitted")
    .optional();
```

Asciidoctor source:

```adoc
= Document API
:toc: left

== Document Upload with Preview Image

include::{snippets}/documents-upload-with-preview/request-parts.adoc[]

== Document Upload Without Preview Image

include::{snippets}/documents-upload-without-preview/http-request.adoc[]
```

You can add a contract table to clarify business requirements:

| Part | Required | Notes |
| --- | --- | --- |
| `file` | Yes | Non-empty PDF file |
| `metadata` | Yes | JSON with title |
| `preview` | No | If sent, must be a valid image |

If a snippet template does not display a Required/Optional column, the description or a dedicated contract table can convey that information. Do not assume `.optional()` always produces a separate column in every template.

## 10. Build and CI

With Gradle and the Asciidoctor plugin configured:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
```

CI flow:

```text
Multipart HTTP tests
        |
        v
Verify server with absent / present / empty parts
        |
        v
Spring REST Docs checks requestParts descriptors
        |
        v
request-parts.adoc
        |
        v
Asciidoctor / Markdown export step
        |
        v
Verify and publish
```

Whenever the contract changes, tests should verify both snippet generation and endpoint behavior. If `preview` changes from optional to required, simultaneously update controller/validation, tests with and without the part, descriptors, and documentation.

Spring REST Docs generates AsciiDoc snippets by default. If Markdown is needed, configure a template or conversion step separately; there is no `request-parts.md` file by default.

## 11. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| REST Docs test reports missing part | Required descriptor was not sent in sample request | Add the part or `.optional()` per contract |
| Server rejects request even though descriptor is optional | Controller still requires the part | Update `@RequestPart(required = false)` if contract permits |
| Confusing zero-byte part with absent | Only checking `MultipartFile.isEmpty()` | Check part presence and content separately |
| Absent test sends an empty part | Request builder still calls `.file(...)` | Do not add the part to the request builder |
| New part breaks strict snippet | Missing descriptor | Document, intentionally ignore, or use relaxed per contract |
| Optional part still absent from table when present in request | Descriptor is marked ignored | Remove `.ignored()` if you want it displayed |
| Wrong MIME type still accepted | Description only documents rules, does not enforce validation | Add content-type checks and negative tests |
| Asciidoctor reports missing snippet | Included operation ID or snippet was not generated | Check operation name and task ordering |

## 12. Practice Exercise

With endpoint `POST /api/documents`:

1. Declare required `file` and `metadata`, and optional `preview` using `requestParts(...)`.
2. Build a request containing all three parts; verify the snippet documents all of them.
3. Build a request omitting `preview`; confirm this is absent rather than an empty part.
4. Send a zero-byte `preview` and verify the response matches the contract.
5. Remove `file` from the request; verify the server rejects it per contract and compare the HTTP error with the snippet failure when a descriptor is required.
6. Change `preview` from optional to required. Update controller, tests, descriptors, and documentation.
7. Send an optional and ignored `clientTrace` part; verify the part is still present on the request but omitted from the snippet.
8. Include snippets in Asciidoctor and ensure CI runs HTTP tests before rendering documentation.

### Self-Assessment Questions

- Is required in `requestParts(...)` the same as `required = true` on `@RequestPart`?
- Which step does `.optional()` affect and which step does it not affect?
- How does absent differ from an empty part and a zero-byte file?
- Why is `MultipartFile.isEmpty()` not enough to confirm a part is absent?
- When is `@RequestPart(required = false)` needed?
- How do you verify the server rejects a missing required part?
- Why should snippet generation tests and endpoint validation tests be considered two separate aspects?

**Remember:** `.optional()` tells Spring REST Docs that a part may be absent from the sample request used to generate snippets. `@RequestPart(required = false)` is what controls whether Spring MVC requires the part at the endpoint. An absent part differs from a present-but-empty part or a zero-byte file; document and test these cases according to the actual contract.

## References

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): `requestParts`, optional/ignored, and relaxed request parts.
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html): `partWithName`, `requestParts`, and `relaxedRequestParts`.
- [Spring Framework — `@RequestPart` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestPart.html): the `required` attribute when binding multipart parts to a controller.
