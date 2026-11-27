# Matching Content-Disposition and Part Names

## 1. Distinguishing name and filename

In a `multipart/form-data` request, each part has its own headers. The key header for identifying a form field is `Content-Disposition`. For a file upload, for example:

```http
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

<binary bytes>
```

The two parameters in the header have different meanings:

- `name="file"` is the **field/part name** in the multipart form. The server uses this name to locate the right data section.
- `filename="report.pdf"` is the **filename supplied by the client**. It is neither the part name nor the server storage path.

In Spring, `MultipartFile.getName()` returns the multipart parameter name, while `getOriginalFilename()` returns the original filename sent by the client. See the [MultipartFile Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html).

This lesson guides you through matching `Content-Disposition` with part names in Spring MVC and Spring REST Docs, verifying them with tests, writing accurate documentation, and avoiding unsafe filename handling.

## 2. Content-Disposition structure in multipart/form-data

A request may contain a file and JSON metadata:

```http
POST /documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----boundary42

------boundary42
Content-Disposition: form-data; name="file"; filename="handbook.pdf"
Content-Type: application/pdf

<file bytes>
------boundary42
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Employee handbook","category":"POLICY"}
------boundary42--
```

According to [RFC 7578, Section 4.2](https://www.rfc-editor.org/rfc/rfc7578.html#section-4.2), each part must have a `Content-Disposition` header with disposition type `form-data` and a `name` parameter. For file data, `filename` should be supplied if a name is available and meaningful, though it is not mandatory in every scenario. Each part may have a `Content-Type`; if omitted, it defaults to `text/plain`. For files, an appropriate media type should be used when known; otherwise, `application/octet-stream` can be used. See also RFC 7578 Section 4.4.

### 2.1. name identifies the part; filename describes the file

| Header | Meaning |
| --- | --- |
| `Content-Disposition: form-data` | Identifies the part as belonging to a multipart form |
| `name="attachment"` | Part/field name used by controller binding |
| `filename="invoice.pdf"` | Filename declared by the client |
| `Content-Type: application/pdf` | Media type declared for the part's body |

When `filename` changes from `invoice.pdf` to `invoice-final.pdf`, the part can still carry the name `attachment`. The controller still receives the same part; only the filename metadata changes. Conversely, changing `name` from `attachment` to `file` is a request contract change and requires aligning both controller and client.

### 2.2. Non-file parts may omit filename

Text or JSON parts typically look like:

```http
Content-Disposition: form-data; name="metadata"
Content-Type: application/json
```

This part does not need a `filename` because it contains JSON data, not a file selected by the client. Do not require every part in a multipart request to have a `filename`.

### 2.3. Multiple files under the same field name

When one field accepts multiple files, RFC 7578 specifies sending each file in its own part while reusing the same `name` parameter. Multiple files for the `attachments` field all carry `name="attachments"`, with each part having its own `filename`. Spring can bind them into `List<MultipartFile>` or `MultipartFile[]`. See RFC 7578 Section 4.3.

## 3. Mapping in Spring MVC

The controller declares the part name via `@RequestPart`:

```java
@PostMapping(
    value = "/documents",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> upload(@RequestPart("file") MultipartFile file) {
    // ...
}
```

From `MultipartFile`, you can read:

```java
String partName = file.getName();
String originalFilename = file.getOriginalFilename();
String contentType = file.getContentType();
long size = file.getSize();
```

| Multipart | MultipartFile | Meaning |
| --- | --- | --- |
| `name="file"` | `getName()` | Part name |
| `filename="report.pdf"` | `getOriginalFilename()` | Original filename sent by client |
| Part Content-Type | `getContentType()` | Declared media type |
| Body bytes | `getBytes()` / `getInputStream()` | File content |

`getOriginalFilename()` may contain path information, an empty string, or no value. Spring warns against using client-supplied filenames directly; strip directory information, check for unusual characters, and prefer generating server-controlled storage names. See the [MultipartFile Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html).

Example controller to observe both values separately:

```java
@RestController
class DocumentController {

    @PostMapping(
        value = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<Map<String, Object>> upload(
            @RequestPart("file") MultipartFile uploadedFile) {

        String storageKey = UUID.randomUUID().toString();

        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
            "partName", uploadedFile.getName(),
            "originalFilename", uploadedFile.getOriginalFilename() == null
                    ? "" : uploadedFile.getOriginalFilename(),
            "contentType", uploadedFile.getContentType() == null
                    ? "" : uploadedFile.getContentType(),
            "size", uploadedFile.getSize(),
            "storageKey", storageKey
        ));
    }
}
```

This is an illustrative example. In a real application, usually only the document ID or storage key is returned rather than exposing the raw original filename unnecessarily.

## 4. Spring REST Docs describes the part name, not automatically the filename

Use `requestParts(...)` with `partWithName(...)` to document parts:

```java
requestParts(
    partWithName("file")
        .description("PDF file to upload"),
    partWithName("metadata")
        .description("JSON metadata of the document")
)
```

The generated snippet is `request-parts.adoc`. `partWithName("file")` targets the **part name**, corresponding to `name="file"` in `Content-Disposition`. It does not target `filename="report.pdf"`.

Spring REST Docs verifies whether documented parts appear in the request; parts that appear without being documented also cause strict tests to fail. You can use `optional()`, `ignored()`, or `relaxedRequestParts(...)` per contract. See [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html).

The `request-parts` snippet does not automatically generate separate columns for filename, Content-Type, size, or file content verification results. If those attributes matter to clients, explain them in prose and verify them with dedicated assertions. Do not describe it as if `requestParts` automatically validates those values.

## 5. MockMvc: verifying name and filename separately

`MockMultipartFile` takes the part name and filename as its first two arguments:

```java
MockMultipartFile file = new MockMultipartFile(
    "file",              // part name: name
    "report.pdf",        // filename: filename
    MediaType.APPLICATION_PDF_VALUE,
    pdfFixtureBytes
);
```

If you swap the two parameters, the part name becomes `report.pdf` and the filename becomes `file`. A controller declaring `@RequestPart("file")` will not receive the part under the expected name.

### 5.1. Complete MockMvc test

The example uses JUnit 5, Java 17+, MockMvc, and Spring REST Docs. The byte fixture below is only for testing multipart binding/metadata; if testing a PDF parser, use a valid PDF file in test resources.

```java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.multipart;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class DocumentContentDispositionTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new DocumentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void uploadSeparatesPartNameAndFilename() throws Exception {
        byte[] bytes = new byte[] {
            0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34
        };

        MockMultipartFile file = new MockMultipartFile(
                "file", "report.pdf",
                MediaType.APPLICATION_PDF_VALUE, bytes
        );

        this.mockMvc.perform(multipart("/documents")
                        .file(file)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.partName").value("file"))
                .andExpect(jsonPath("$.originalFilename").value("report.pdf"))
                .andExpect(jsonPath("$.contentType")
                        .value(MediaType.APPLICATION_PDF_VALUE))
                .andExpect(jsonPath("$.size").value(bytes.length))
                .andDo(document("documents-upload",
                        requestParts(
                            partWithName("file")
                                .description("PDF file; part name is file")
                        )
                ));
    }

    @RestController
    static class DocumentController {

        @PostMapping(
            value = "/documents",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        ResponseEntity<Map<String, Object>> upload(
                @RequestPart("file") MultipartFile file) {

            return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
                "partName", file.getName(),
                "originalFilename",
                    file.getOriginalFilename() == null ? "" : file.getOriginalFilename(),
                "contentType",
                    file.getContentType() == null ? "" : file.getContentType(),
                "size", file.getSize()
            ));
        }
    }
}
```

The test verifies part name, filename, media type, and byte count separately. `requestParts` only generates the parts table; assertions confirm Spring bound the multipart request to the controller as expected.

### 5.2. JSON metadata is a separate part

The `metadata` part typically has `name="metadata"`, `Content-Type: application/json`, and needs no `filename`. Use `requestParts(partWithName("metadata"))` to describe it, `requestPartBody("metadata")` to display the JSON, and `requestPartFields("metadata", ...)` to document the inner schema.

## 6. Mapping table from wire format to documentation

| On the multipart wire | Spring MVC | Spring REST Docs |
| --- | --- | --- |
| `name="file"` | `@RequestPart("file")` / `MultipartFile.getName()` | `partWithName("file")` |
| `filename="report.pdf"` | `MultipartFile.getOriginalFilename()` | Descriptive prose and dedicated assertions |
| Part Content-Type | `MultipartFile.getContentType()` | Descriptive prose and dedicated assertions |
| Body bytes | `getBytes()` / `getInputStream()` | Do not use JSON field descriptors for binary bytes |
| `name="metadata"` | `@RequestPart("metadata")` | `partWithName("metadata")` |
| Metadata JSON | DTO/Map via message converter | `requestPartFields` and optionally `requestPartBody` |

If you need to inspect actual part headers, add appropriate tests at the multipart parser/binding layer or integration tests. Do not conclude `filename` is documented merely because the `request-parts` table has a `file` row.

## 7. Safety rules for filename

`filename` is client-supplied data and is untrusted. RFC 7578 notes that receivers must not blindly use the filename, must validate it, and must ignore any directory information that may appear in the filename. Spring likewise warns that the name may contain path information or sequences such as `..`.

Principles for upload APIs:

1. **Never use directly as a storage path.** Generate a server-managed storage key or internal filename.
2. **Strip path information.** Never let a string like `../../secret.txt` determine where a file is written.
3. **Validate length and characters.** Define rules for control characters, empty names, and extensions.
4. **Do not trust extensions.** `report.pdf` does not prove the bytes are a PDF.
5. **Do not trust client-supplied Content-Type.** Verify the content according to the application's actual requirements.
6. **Do not log sensitive filenames or put them in public docs.** Use dummy fixtures for snippets and examples.

### 7.1. filename is not always mandatory

RFC 7578 states that `filename` should be supplied for file content when a name is available and meaningful; `filename` is not required when the name is unavailable, meaningless, or private.

### 7.2. Do not confuse filename* with filename

RFC 7578 specifies that the `filename*` parameter encoding from RFC 5987 must not be used in `multipart/form-data`. Do not mechanically apply `filename*` rules from HTTP response `Content-Disposition` headers to individual part `Content-Disposition` headers. See [RFC 7578 Section 4.2](https://www.rfc-editor.org/rfc/rfc7578.html#section-4.2).

### 7.3. Multiple files with the same part name

When sending multiple images under the `attachments` field, each file is a separate part carrying the same `name="attachments"`; each part has its own `filename`. The controller can bind them to `List<MultipartFile>` or `MultipartFile[]`. RFC 7578 describes this mechanism in Section 4.3.

## 8. Documenting in Asciidoctor

With the operation identifier `documents-upload`, `requestParts` creates `request-parts.adoc` in the operation folder:

```text
build/generated-snippets/
└── documents-upload/
    ├── request-parts.adoc
    ├── http-request.adoc
    └── http-response.adoc
```

You can explain `name` and `filename` alongside the snippet:

```asciidoc
= Document API

== POST /documents

The request uses multipart/form-data. The file part has name "file".
Clients may send filename in Content-Disposition. Filename is
client-supplied metadata and is never used directly as a storage path.

=== Parts

include::{snippets}/documents-upload/request-parts.adoc[]

=== File part rules

* Part name is `file`.
* `filename` is the original filename declared by the client; it may be absent in some flows.
* `Content-Type` is the media type declared for the part.
* The server validates format and size according to the upload policy.
```

REST Docs does not automatically generate a separate table for the `filename` parameter from `requestParts`. Explanations are manually authored content; test assertions verify actual behavior.

## 9. WebTestClient and REST Assured

### 9.1. WebTestClient

Multipart bodies can be built using `BodyInserters.fromMultipartData`. A `Resource` must provide a filename when you want the client to construct a part with `filename`:

```java
Resource resource = new ByteArrayResource(pdfBytes) {
    @Override
    public String getFilename() {
        return "report.pdf";
    }
};

HttpHeaders partHeaders = new HttpHeaders();
partHeaders.setContentType(MediaType.APPLICATION_PDF);
HttpEntity<Resource> filePart = new HttpEntity<>(resource, partHeaders);

MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("file", filePart);

webTestClient.post()
    .uri("/documents")
    .body(BodyInserters.fromMultipartData(parts))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("documents-upload",
        requestParts(
            partWithName("file").description("PDF file; part name is file")
        )
    ));
```

WebTestClient must be configured with the Spring REST Docs documentation filter on the builder before building. Verify that the filename is included in the request by the resource/client as expected.

### 9.2. REST Assured

REST Assured supports sending file parts via `multiPart`:

```java
RestAssured.given(this.spec)
    .filter(document("documents-upload",
        requestParts(
            partWithName("file").description("PDF file; part name is file")
        )
    ))
    .multiPart("file", new File("report.pdf"), "application/pdf")
    .when()
    .post("/documents")
    .then()
    .statusCode(201);
```

The name `file` passed to `multiPart` is the part name; `report.pdf` is the filename. `spec` must be configured with the endpoint and REST Docs filter according to the project. Use a deterministic test fixture file rather than referencing an arbitrary path on a developer's machine.

## 10. Common errors

| Symptom | Cause | How to fix |
| --- | --- | --- |
| `@RequestPart("file")` does not receive the file | Multipart `name` differs from `file` | Align `name` across client, test, and controller |
| `getOriginalFilename()` returns unexpected name | Filename put in the `name` argument or client did not send filename | Check both `MockMultipartFile` arguments and raw part |
| Assuming `partWithName("report.pdf")` is right | Confusing filename with part name | Use `partWithName("file")` if the name is `file` |
| `request-parts.adoc` does not display filename | Snippet describes part names, does not auto-create filename column | Explain filename in prose and verify via assertions |
| Filename contains a path | Client sent a name with directory info | Normalize name, strip path, and generate safe storage key |
| Content-Type says PDF yet parser fails | Client-declared media type does not match bytes | Verify actual content with a parser/validator |
| JSON metadata fails to bind | Wrong name, media type, or JSON part | Check `@RequestPart`, Content-Type, and JSON body |
| Unicode names get mangled | Encoding mismatch between client/server | Consult RFC, client, and actual container; write compatibility tests |
| Multiple files only receive one | Client uses different part names or controller binds single file | Send each file as a separate part with the same `name` and bind a collection |

## 11. Build and CI

With Gradle Groovy DSL, assuming tests write snippets to `build/generated-snippets` and the project has configured the Asciidoctor plugin:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir
}
```

Run:

```bash
./gradlew clean test asciidoctor
```

In CI, verify:

1. Tests send the exact part name and filename described in the contract.
2. Tests separately verify `getName()` and `getOriginalFilename()`.
3. Media type and file content are validated according to endpoint policy.
4. `requestParts` documents all supported parts completely.
5. Asciidoctor includes snippets with the right operation identifier.
6. Fixtures and generated snippets contain no real filenames or sensitive data.

Passing documentation tests do not replace upload security testing. Tests for filename path traversal, spoofed files, oversized files, and access permissions should be separated; only generate public snippets for necessary cases.

## 12. Hands-on exercise

Create `DocumentContentDispositionTest`:

1. Create `MockMultipartFile("file", "report.pdf", "application/pdf", bytes)`.
2. Assert that `getName()` is `file` and `getOriginalFilename()` is `report.pdf`.
3. Change filename to `annual-report.pdf` while keeping the part name unchanged; verify the controller still receives the right part.
4. Change the part name to `attachment`; update `@RequestPart` and `partWithName` per contract.
5. Create a JSON metadata part without a filename; verify it remains valid according to endpoint design.
6. Test a filename containing a path like `../../report.pdf`; verify the application does not use that value directly as a path.
7. Create multiple file parts sharing the name `attachments` and bind a collection.
8. Include `request-parts.adoc` in Asciidoctor, add filename explanations, and run `./gradlew clean test asciidoctor`.

**Completion criteria:** explain the difference between `name` and `filename`, trace them via `MultipartFile`, understand what the `request-parts` snippet documents, and use assertions to verify attributes the snippet does not describe on its own.

## 13. Self-check questions

**1. In Content-Disposition with `name="file"; filename="report.pdf"`, which value is the part name?**

`name="file"` is the part name. `filename="report.pdf"` is the filename sent by the client.

**2. Where does Spring MultipartFile expose these two values?**

`getName()` returns the part name; `getOriginalFilename()` returns the original filename.

**3. Does `partWithName("file")` document the filename?**

No. It selects the part by `name` and creates the part description. The filename needs to be explained in prose and verified by tests.

**4. Can filename be trusted to construct a file storage path?**

No. Client-supplied filenames may contain paths or dangerous sequences. Normalize, validate, and generate a server-managed storage name.

**5. Must every file part have a filename?**

No. RFC 7578 states that filename should be supplied when available and meaningful; in some workflows the filename may be absent or inappropriate to disclose.

## References

- [RFC 7578 — multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578.html): `Content-Disposition`, `name`, `filename`, multiple files for the same field, and per-part `Content-Type`.
- [Spring Framework — MultipartFile Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html): meanings of `getName()`, `getOriginalFilename()`, `getContentType()`, and filename warnings.
- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): documenting request parts and strict/relaxed behavior.
