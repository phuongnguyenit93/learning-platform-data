# request-parts, request-part-name, and request-part-body

## Lesson Objectives

In the **SPRING_REST_DOCS** module, many APIs accept multipart/form-data, such as uploading an image alongside JSON metadata or sending multiple files in a single request. A multipart request is split into independent **parts**; each part has its own name, headers/content type, and body. Documentation needs to indicate which parts the client must send, what data each part contains, and what the body structure looks like.

Spring REST Docs supports three levels of documentation:

- **request-parts**: list of request parts and the meaning of each part.
- **request-part-body**: raw body content of a specifically named part.
- **request-part-fields**: fields inside a structured body (e.g., JSON) of a specifically named part.

After this lesson, you will be able to:

- Distinguish multipart requests from regular JSON request bodies.
- Use requestParts and partWithName to document the list of parts.
- Use requestPartBody to generate a body snippet for a part.
- Use requestPartFields to document fields of a JSON part.
- Understand how the part name is incorporated into the output snippet filename.
- Document file uploads and metadata with the appropriate content types.
- Choose strict/relaxed modes, optional, and ignored appropriately.
- Use MockMvc or WebTestClient to generate verifiable multipart snippets.

## 1. What Does a Multipart Request Contain?

An HTTP request with content type multipart/form-data is divided into multiple parts. Each part typically has:

| Component | Meaning |
| --- | --- |
| Part name | Identifier name of the part, e.g., image or metadata |
| Headers | Part-specific headers, typically Content-Disposition and Content-Type |
| Filename | Filename if the part represents a file upload |
| Content type | Data type of the part body, e.g., image/png or application/json |
| Body | Content of the part: file bytes, JSON, text, or other data |

Example of uploading an image with metadata:

```text
POST /images
Content-Type: multipart/form-data; boundary=...

--boundary
Content-Disposition: form-data; name="image"; filename="image.png"
Content-Type: image/png

<binary image bytes>
--boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Profile photo","version":"1.0"}
--boundary--
```

The two parts play different roles:

- image contains binary file content.
- metadata contains JSON describing the file.

API documentation should describe the names of both parts, their purpose, content type, and metadata structure. Merely stating that the endpoint accepts multipart/form-data leaves API consumers unaware of which parts to send and how to format each part.

## 2. Three Snippet Levels and Generated Filenames

Spring REST Docs provides the following snippets:

| Snippet-Generating API | Content | Snippet Name |
| --- | --- | --- |
| requestParts(...) | List of parts, names, and descriptions | request-parts.adoc |
| requestPartBody("metadata") | Body of the part named metadata | request-part-metadata-body.adoc |
| requestPartFields("metadata", ...) | Fields of the part named metadata | request-part-metadata-fields.adoc |

Specific filenames are generated according to the part name. For example:

- Part named image: requestPartBody("image") generates request-part-image-body.adoc.
- Part named metadata: requestPartBody("metadata") generates request-part-metadata-body.adoc.
- Part named metadata: requestPartFields("metadata", ...) generates request-part-metadata-fields.adoc.

**Naming note:** there is no generic output file named request-part-name.adoc or request-part-body.adoc. The part name segment is substituted into the snippet filename. For the metadata part, actual files take the form request-part-metadata-body.adoc or request-part-metadata-fields.adoc.

The three levels of description can be used independently or combined. For instance, request-parts lists image and metadata; request-part-body shows how the metadata body is sent; request-part-fields explains the meaning of each JSON field inside metadata.

## 3. request-parts: Documenting the List of Parts

### 3.1. Using requestParts and partWithName

Suppose an upload endpoint accepts one file whose part name is file:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

this.mockMvc.perform(multipart("/upload")
        .file("file", "example".getBytes()))
    .andExpect(status().isOk())
    .andDo(document("upload",
        requestParts(
            partWithName("file")
                .description("File to upload.")
        )));
```

requestParts instructs REST Docs to generate a snippet describing the parts. partWithName("file") selects the part named file; description explains the part's purpose to the client.

The request-parts.adoc snippet typically contains a table of part names and descriptions. It helps readers know which components the request must include.

### 3.2. Documenting Multiple Parts

For uploading an image with metadata:

```java
this.mockMvc.perform(multipart("/images")
        .file(image)
        .file(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("image-upload",
        requestParts(
            partWithName("image")
                .description("Image file to upload."),
            partWithName("metadata")
                .description("Image description metadata in JSON format.")
        )));
```

Each part has its own name. The name in the descriptor must match the exact part name sent by the client. For example, metadata differs from meta-data; REST Docs does not automatically infer or normalize names.

### 3.3. Strict Behavior of requestParts

In default mode, requestParts checks the correspondence between descriptors and the actual request:

- A part appearing in the request without a descriptor can fail the test.
- A documented part missing from the request also fails the test, unless the descriptor is marked optional.
- A part marked ignored does not appear in the snippet table but is still handled when validating the request.

Thanks to this, if the API adds a new part, the documentation test can require the author to update the description.

### 3.4. Optional and Ignored Parts

A part may not be required:

```java
requestParts(
    partWithName("image")
        .description("Primary image file."),
    partWithName("thumbnail")
        .optional()
        .description("Thumbnail image; may be omitted.")
)
```

If a part does not need to appear in the documentation table while still being present in the test request, you can use ignored():

```java
requestParts(
    partWithName("image")
        .description("Primary image file."),
    partWithName("clientTrace")
        .ignored()
)
```

optional and ignored have different meanings:

- optional allows a documented part to be absent from the request.
- ignored handles a part present in the request without placing it in the description table.

Do not use optional to mask a required part that the endpoint actually needs.

### 3.5. relaxedRequestParts Mode

When you want to focus on documenting only certain parts of a large request, you can use relaxedRequestParts:

```java
relaxedRequestParts(
    partWithName("image")
        .description("Image file to upload.")
)
```

Relaxed mode allows other unlisted parts to appear without failing the test. This is a suitable option when documentation describes only a sub-scenario or a key subset of parts.

Do not use relaxedRequestParts for every endpoint. If documentation needs to reflect the full multipart contract, default requestParts helps detect new or missing parts more clearly.

## 4. request-part-body: Documenting a Part's Body

### 4.1. When to Use requestPartBody?

requestPartBody(partName) generates a snippet containing the body of the selected part. It is useful when you need to display the content of:

- A JSON part.
- An XML part.
- A text part.
- The body of a structured part that you want stored as a separate snippet.

For large binary files such as images or PDFs, a body snippet may not be a good presentation for readers. Prefer describing the file type, content type, size limits, and upload conditions in request-parts or explanatory prose; only generate a body snippet when the representation is meaningful and safe to include in documentation.

### 4.2. MockMvc Example

Create two MockMultipartFile instances:

```java
MockMultipartFile image = new MockMultipartFile(
        "image",
        "image.png",
        "image/png",
        imageBytes
);

MockMultipartFile metadata = new MockMultipartFile(
        "metadata",
        "",
        "application/json",
        """
        {
          "title": "Profile photo",
          "version": "1.0"
        }
        """.getBytes(StandardCharsets.UTF_8)
);
```

Generate the body snippet for the metadata part:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

this.mockMvc.perform(multipart("/images")
        .file(image)
        .file(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("image-upload",
        requestPartBody("metadata")
    ));
```

Generated snippet:

```text
build/generated-snippets/
└── image-upload/
    └── request-part-metadata-body.adoc
```

The snippet contains the body extracted by REST Docs from the metadata part. The snippet name is based on the part name passed to requestPartBody.

### 4.3. Body Snippets Do Not Replace request-parts

requestPartBody only describes the body content of the selected part. It does not replace the table listing all parts and their meanings. Complete documentation typically includes:

```asciidoc
== Multipart request
include::{snippets}/image-upload/request-parts.adoc[]

== Metadata body
include::{snippets}/image-upload/request-part-metadata-body.adoc[]
```

request-parts answers the question "which parts does the request contain?". request-part-metadata-body shows "what does the metadata body contain?".

### 4.4. Notes on Binary Bodies

Do not assume binary file bodies can be represented as text. For image/png, application/pdf, or other binary formats:

- Do not dump raw bytes into documentation if they are unreadable.
- Use dummy/small data in tests.
- Prefer documenting filename, content type, and size rules.
- Do not use files containing personal information or secrets as fixtures.
- If the template or snippet cannot display the body usefully, document only part metadata and describe the file in prose.

## 5. request-part-fields: Documenting Fields Inside a Part

requestPartFields fits when a part contains a structured payload, such as JSON metadata:

```json
{
  "title": "Profile photo",
  "version": "1.0",
  "visibility": "PRIVATE"
}
```

Declaring field descriptors:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

this.mockMvc.perform(multipart("/images")
        .file(image)
        .file(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("image-upload",
        requestPartFields("metadata",
            fieldWithPath("title")
                .description("Image title."),
            fieldWithPath("version")
                .description("Metadata version."),
            fieldWithPath("visibility")
                .description("Image visibility scope.")
        )));
```

Generated snippet:

```text
build/generated-snippets/
└── image-upload/
    └── request-part-metadata-fields.adoc
```

requestPartFields documents the fields of the body of the part named metadata; it does not document fields of the entire multipart request.

### 5.1. Validating Fields Inside a Part

Default requestPartFields applies strict payload validation just like requestFields:

- An actual field in the JSON part without a descriptor fails the test.
- A descriptor pointing to a field absent from the part body fails the test, unless optional.
- ignored can be used to handle a field without displaying it in the snippet.
- Nested field paths still need to be documented with appropriate paths.

For example, a JSON part gains a new checksum field while descriptors have not been updated; the test can detect the mismatch. This mechanism keeps part metadata documentation synchronized with the actual payload.

### 5.2. Relaxed Part Fields

If documenting only part of a part's body, you can use relaxedRequestPartFields:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedRequestPartFields;

relaxedRequestPartFields("metadata",
    fieldWithPath("title")
        .description("Image title.")
)
```

Relaxed mode allows other unlisted fields. Use it when intentionally documenting only part of a JSON part; if full documentation is needed, prefer default requestPartFields.

## 6. Combining All Three Snippet Types in One Operation

An image upload test can generate all three levels of documentation:

```java
this.mockMvc.perform(multipart("/images")
        .file(image)
        .file(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("image-upload",
        requestParts(
            partWithName("image")
                .description("PNG image file to upload."),
            partWithName("metadata")
                .description("Image JSON metadata.")
        ),
        requestPartBody("metadata"),
        requestPartFields("metadata",
            fieldWithPath("title")
                .description("Image title."),
            fieldWithPath("version")
                .description("Metadata version.")
        )
    ));
```

The snippets are generated in the same operation directory:

```text
build/generated-snippets/
└── image-upload/
    ├── request-parts.adoc
    ├── request-part-metadata-body.adoc
    └── request-part-metadata-fields.adoc
```

In AsciiDoc:

```asciidoc
== Upload image

=== Request parts
include::{snippets}/image-upload/request-parts.adoc[]

=== Metadata body
include::{snippets}/image-upload/request-part-metadata-body.adoc[]

=== Metadata fields
include::{snippets}/image-upload/request-part-metadata-fields.adoc[]
```

It is not necessary to generate both a body snippet and a fields snippet for every part. If JSON metadata only needs a field table, requestPartFields may suffice. If a complete sample body needs to be included in documentation, add requestPartBody. For binary files, usually only request-parts and prose descriptions are needed.

## 7. Content-Type and Choosing Snippets

Each part can have its own content type. Choose the documentation approach based on payload type:

| Part Content-Type | Example | Suggested Documentation Approach |
| --- | --- | --- |
| application/json | Metadata object | requestPartBody and/or requestPartFields |
| text/plain | Plain text notes | requestPartBody |
| application/xml | XML metadata | requestPartBody; field documentation requires appropriate XML handling |
| image/png, image/jpeg | Image file | request-parts and filename/content type description; consider avoiding body snippet |
| application/pdf | PDF file | request-parts and file description; typically do not include raw bytes |
| application/octet-stream | Binary data | Document part and data transfer rules |

REST Docs extracts a part's body by name. Ensure part names are correct and the test request actually sends a representative content type/body. If a JSON part is sent as text/plain or lacks an appropriate content type, server parsing and snippet output may differ from expectations.

## 8. WebTestClient Example

WebTestClient also supports creating multipart requests using MultiValueMap and BodyInserters:

```java
MultiValueMap<String, Object> multipartData = new LinkedMultiValueMap<>();
multipartData.add("image", imageResource);
multipartData.add("metadata", Map.of(
        "title", "Profile photo",
        "version", "1.0"
));

this.webTestClient.post()
    .uri("/images")
    .body(BodyInserters.fromMultipartData(multipartData))
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("image-upload",
        requestParts(
            partWithName("image")
                .description("Image file to upload."),
            partWithName("metadata")
                .description("Image JSON metadata.")
        ),
        requestPartBody("metadata")
    ));
```

For Resource uploads, you can override getFilename() to set the filename for the part:

```java
Resource imageResource = new ByteArrayResource(imageBytes) {
    @Override
    public String getFilename() {
        return "image.png";
    }
};
```

WebTestClient APIs and how multipart serialization behaves depend on the Spring WebFlux/client version. Verify that the actual request has Content-Disposition, filename, and Content-Type as expected.

## 9. Part Names Must Be Consistent Across Controller, Test, and Documentation

The part name is part of the API contract. Example controller accepting parts:

```java
@PostMapping(
        path = "/images",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> upload(
        @RequestPart("image") MultipartFile image,
        @RequestPart("metadata") CreateImageMetadata metadata) {
    // Process upload
    return ResponseEntity.accepted().build();
}
```

The name in the test:

```java
multipart("/images")
    .file(image)
    .file(metadata)
```

and the name in REST Docs descriptors must match consistently:

```java
requestParts(
    partWithName("image").description("Image file."),
    partWithName("metadata").description("JSON metadata.")
)
```

If the controller changes @RequestPart("metadata") to @RequestPart("details"), while the test still sends metadata, the test may fail during binding. If the test also changes while descriptors do not, REST Docs will report mismatched parts. Update the controller, test, descriptors, and AsciiDoc include paths in sync.

## 10. Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| request-parts reports undocumented part | Request has a new part without a part descriptor | Add partWithName or use relaxedRequestParts intentionally |
| Descriptor reports part not found | Wrong part name or test request did not send the part | Cross-check @RequestPart, multipart names, and descriptors |
| request-part-metadata-body.adoc not generated | requestPartBody("metadata") not called or part does not exist | Add the snippet to the right operation and verify the multipart request |
| request-part-metadata-fields.adoc not generated | requestPartFields not called or wrong part name passed | Check PayloadDocumentation and part name |
| Field in JSON part is undocumented | Strict requestPartFields and descriptor missing field | Add descriptor, ignored, or relaxed when appropriate |
| Body snippet is unreadable | Part is binary or encoding/content type is unsuitable | Do not include raw binary; describe the file in prose |
| Metadata parsed as text instead of JSON | Part Content-Type is missing or wrong | Assign application/json to the metadata part |
| Filename blank/incorrect | Resource or MockMultipartFile lacks filename | Declare the proper filename in the test |
| Test passes yet docs lack part body | Only requestParts used without adding requestPartBody | Add the body snippet for the part needing illustration |
| Include snippet name mismatch | Confusing pattern placeholder with output name containing part-name | Use exact request-part-<part-name>-body.adoc or fields.adoc |
| Using relaxed hides schema changes | New parts/fields do not fail the test | Prefer strict if full contract verification is desired |

## 11. Hands-on Exercise

1. Create a POST /images endpoint accepting image and metadata parts.
2. Create a MockMultipartFile for image with filename image.png and content type image/png.
3. Create a MockMultipartFile metadata with content type application/json and body containing title, version.
4. Use requestParts to document both parts; inspect request-parts.adoc.
5. Use requestPartBody("metadata"); inspect request-part-metadata-body.adoc.
6. Use requestPartFields("metadata", ...) to document title and version; inspect request-part-metadata-fields.adoc.
7. Add a new field to metadata without updating descriptors yet; observe strict requestPartFields failing the test.
8. Try relaxedRequestPartFields and explain the trade-off.
9. (Advanced) Use WebTestClient to send the same multipart request and compare snippets.

**Self-assessment questions**

1. What information about a multipart request does requestParts document?
2. Which part is identified by partWithName?
3. What snippet name does requestPartBody("metadata") generate?
4. How does requestPartFields differ from requestPartBody?
5. Why should a JSON part have Content-Type application/json?
6. How do optional and ignored differ for parts?
7. When are relaxedRequestParts or relaxedRequestPartFields appropriate?
8. Why should you avoid including bytes of image/PDF files in body snippets?

## Official References

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): requestParts, requestPartBody, requestPartFields, and generated snippet names.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field descriptors, optional, ignored, and relaxed payload documentation.
- [RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html): requestParts, relaxedRequestParts, and partWithName.
- [PayloadDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html): requestPartBody, requestPartFields, and relaxedRequestPartFields.
- [Spring Framework — Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html): handling multipart requests in Spring MVC.

**Practical conclusion:** Use requestParts to list and explain each part; use requestPartBody when you need to display a part's body content; use requestPartFields when a part body is structured and requires field-by-field documentation. Body/fields snippet names always embed the specific part name, so keep names synchronized across controller, tests, descriptors, and AsciiDoc includes. Run tests with realistic multipart requests so documentation accurately reflects the structure accepted by the API.
