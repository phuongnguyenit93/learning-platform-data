# request-part-fields and response-headers

## 1. Two Different Parts of the HTTP Contract

In the **Spring REST Docs (SPRING_REST_DOCS)** module under the **Default Snippets** chapter, HTTP tests generate snippets describing the requests and responses actually handled by the application. This lesson focuses on two descriptors:

| Descriptor | Snippet | Purpose |
| --- | --- | --- |
| `requestPartFields(partName, ...)` | `request-part-{part-name}-fields.adoc` | Document fields inside the payload of a multipart request part |
| `responseHeaders(...)` | `response-headers.adoc` | Document HTTP headers returned by the server |

`requestPartFields` does not document the entire multipart body or file bytes. It extracts the payload of a specific part and validates its fields against descriptors. `responseHeaders` documents metadata at the HTTP response level, such as `Location`, `ETag`, `Content-Type`, or `Cache-Control`.

Examples use **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, and MockMvc**. Spring REST Docs also supports request part fields with WebTestClient and REST Assured; how multipart requests are constructed varies by client.

## 2. Multipart Requests and Parts

A multipart request splits its body into multiple parts. Each part has its own name, headers, and content. A document upload endpoint might accept a `file` part containing a PDF and a `metadata` part containing JSON describing the title, document type, and publication status.

Example:

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----ExampleBoundary
Accept: application/json

------ExampleBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"API Guide","category":"manual"}
------ExampleBoundary
Content-Disposition: form-data; name="file"; filename="guide.pdf"
Content-Type: application/pdf

...binary file bytes...
------ExampleBoundary--
```

Different descriptors generate different snippets:

| Content | Descriptor | Snippet |
| --- | --- | --- |
| List of request parts | `requestParts(...)` | `request-parts.adoc` |
| Body of the metadata part | `requestPartBody("metadata")` | `request-part-metadata-body.adoc` |
| Fields inside JSON metadata | `requestPartFields("metadata", ...)` | `request-part-metadata-fields.adoc` |
| HTTP headers of the response | `responseHeaders(...)` | `response-headers.adoc` |

The `metadata` part has a JSON structure, making it a fit for `requestPartFields`. The `file` part consists of file bytes rather than a JSON object to describe with field paths. You can describe the file part using `requestParts(...)`; only use field descriptors for parts that have a structured payload.

## 3. Generating request-part-metadata-fields.adoc

Suppose the `metadata` part has the payload:

```json
{
  "title": "API Guide",
  "category": "manual",
  "published": true,
  "owner": {
    "team": "Platform",
    "email": "docs@example.test"
  }
}
```

Declaring field descriptors:

```java
requestPartFields("metadata",
    fieldWithPath("title")
        .description("Document title"),
    fieldWithPath("category")
        .description("Document category"),
    fieldWithPath("published")
        .description("Whether the document is published"),
    fieldWithPath("owner.team")
        .description("Responsible team"),
    fieldWithPath("owner.email")
        .description("Contact email")
)
```

REST Docs generates `request-part-metadata-fields.adoc`. The snippet filename is built from the part name: a `metadata` part produces `request-part-metadata-fields.adoc`; a `settings` part produces `request-part-settings-fields.adoc`. Therefore, the part name becomes part of the include path.

### Optional, Ignored, and Relaxed

If a valid field can be absent, mark it optional:

```java
fieldWithPath("description")
    .description("Additional description")
    .optional()
```

If a field appears without needing to be listed in the table:

```java
fieldWithPath("internalTraceId")
    .ignored()
```

`requestPartFields` in strict mode detects undocumented fields in the part and required descriptors missing from the payload. If you only want to document a subset of fields in a scenario, use `relaxedRequestPartFields(...)`. Relaxed mode ignores undocumented fields; only use it when the documentation scope is clearly defined to avoid masking contract changes.

## 4. MockMvc Multipart Upload Example

### 4.1. Creating Fixtures for Each Part

MockMvc uses `MockMultipartFile` to create mock parts. The `metadata` part contains JSON; the `file` part contains a small test-only file:

```java
MockMultipartFile metadata = new MockMultipartFile(
    "metadata",
    "",
    MediaType.APPLICATION_JSON_VALUE,
    """
    {
      "title": "API Guide",
      "category": "manual",
      "published": true
    }
    """.getBytes(StandardCharsets.UTF_8)
);

MockMultipartFile file = new MockMultipartFile(
    "file",
    "guide.pdf",
    MediaType.APPLICATION_PDF_VALUE,
    "fake-pdf-content".getBytes(StandardCharsets.UTF_8)
);
```

The file data here is just a minimal fixture. Real tests should use a minimal dummy file suitable for the application's format validation.

### 4.2. Recording Part Fields

```java
mockMvc.perform(
        multipart("/api/documents")
            .file(metadata)
            .file(file)
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isCreated())
    .andDo(document("documents-upload",
        requestPartFields("metadata",
            fieldWithPath("title").description("Document title"),
            fieldWithPath("category").description("Document category"),
            fieldWithPath("published").description("Publication status")
        )
    ));
```

`document("documents-upload", ...)` records an operation. `requestPartFields("metadata", ...)` extracts JSON from the metadata part and builds the field table. If you need to document both parts at the multipart level, add `requestParts(...)`; the two descriptors have different responsibilities.

Example:

```java
requestParts(
    partWithName("metadata")
        .description("Document JSON metadata"),
    partWithName("file")
        .description("Uploaded file content")
)
```

The `request-parts.adoc` snippet describes the parts. The `request-part-metadata-fields.adoc` snippet describes the internal structure of metadata. Documentation typically needs both so readers know which parts the request contains and what fields JSON metadata includes.

## 5. response-headers.adoc

### 5.1. Role of Response Headers

Response headers are metadata sent by the server alongside the status and response body. Several headers commonly belong to the API contract:

| Header | Common Meaning |
| --- | --- |
| `Content-Type` | Media type of the response body |
| `Location` | URI referencing the newly created resource |
| `ETag` | Validator representing a version of a representation |
| `Cache-Control` | Response caching rules |
| `Retry-After` | Timestamp or wait duration before retrying |
| `X-RateLimit-Limit` | Request quota within a window |
| `X-RateLimit-Remaining` | Remaining requests in the current window |
| `X-RateLimit-Reset` | Information on when the quota resets |

For example, a POST endpoint returns `201 Created` and `Location` so the client knows the new resource URI. A GET endpoint has `ETag` so clients can perform conditional requests. A rate-limited endpoint may provide headers indicating limits and wait times.

### 5.2. Declaring responseHeaders

Use `responseHeaders(...)` together with `headerWithName(...)`:

```java
responseHeaders(
    headerWithName("Location")
        .description("URI of the newly created document"),
    headerWithName("ETag")
        .description("Representation validator"),
    headerWithName("Content-Type")
        .description("Response body media type")
)
```

REST Docs generates `response-headers.adoc`, containing a header description table. Do not confuse it with `requestHeaders(...)`, which generates `request-headers.adoc` to describe headers sent by the client.

### 5.3. Strict Validation and Optional Headers

Documented headers must exist in the actual response. If a descriptor names a nonexistent header, snippet generation fails and the test fails. This mechanism prevents documentation from publishing a header that the endpoint does not return.

If a header can be absent according to the contract, mark it optional:

```java
headerWithName("ETag")
    .description("Representation validator")
    .optional()
```

Only mark optional if the API truly permits the header to be absent. Do not use optional to hide an implementation bug causing a required header not to be returned.

## 6. Combining Multipart Fields and Response Headers in One Operation

Suppose the upload endpoint returns:

```http
HTTP/1.1 201 Created
Location: /api/documents/501
ETag: "doc-v1"
Content-Type: application/json

{"id":501,"title":"API Guide"}
```

A single `document(...)` call can generate the corresponding snippets:

```java
document("documents-upload",
    requestParts(
        partWithName("metadata").description("JSON metadata"),
        partWithName("file").description("Document file")
    ),
    requestPartFields("metadata",
        fieldWithPath("title").description("Title"),
        fieldWithPath("category").description("Document category"),
        fieldWithPath("published").description("Publication status")
    ),
    responseHeaders(
        headerWithName("Location").description("New document URI"),
        headerWithName("ETag").description("Document validator"),
        headerWithName("Content-Type").description("Media type")
    )
)
```

The test only passes if the response actually contains the documented headers. If the controller does not yet set ETag, remove that descriptor or implement the proper behavior per API design; do not assume headers appear automatically.

## 7. Output Structure and Inclusion in Asciidoctor

With operation ID `documents-upload` and root snippet directory `build/generated-snippets`, the relevant files look like:

```text
build/generated-snippets/
  documents-upload/
    request-parts.adoc
    request-part-metadata-fields.adoc
    response-headers.adoc
    http-request.adoc
    http-response.adoc
```

Include in documentation:

```asciidoc
== Upload document

=== Multipart parts
include::{snippets}/documents-upload/request-parts.adoc[]

=== Metadata fields
include::{snippets}/documents-upload/request-part-metadata-fields.adoc[]

=== Response headers
include::{snippets}/documents-upload/response-headers.adoc[]

=== HTTP response
include::{snippets}/documents-upload/http-response.adoc[]
```

`{snippets}` must point to the root directory containing operations. The path after it must match the operation ID and generated snippet filename. When changing a part name in `requestPartFields`, update the include filename as well.

## 8. Build and CI

With Gradle, ensure tests generate snippets before Asciidoctor includes them:

```groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.named('test') {
    useJUnitPlatform()
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.get().asFile
}
```

Run the build:

```bash
./gradlew clean test asciidoctor
```

CI should use small, deterministic dummy fixture files independent of developer machines. After the build, verify output contains `request-part-...-fields.adoc` and `response-headers.adoc` before publishing. If tests fail due to mismatched header/field descriptors, fix the implementation or descriptors per contract rather than ignoring the failure.

## 9. Data Protection and Reliability

Multipart requests may contain files, metadata, or personal data. Response headers may contain cookies, server information, or tokens. Before publishing snippets:

- Use small, mocked fixture files containing no customer data.
- Do not put access tokens, passwords, session cookies, or API keys into metadata.
- Do not record real authentication headers in request snippets.
- Document only public response headers meaningful to clients.
- Avoid documenting internal headers such as debug traces or topology if they are not part of the public contract.
- If sensitive headers must be removed or replaced in snippets, use an operation preprocessor; remember preprocessors only alter documentation records, not runtime behavior.

Descriptors are also a form of contract validation. If a required header disappears or a new field appears in metadata without being documented, the test should fail so the team intentionally updates both API and documentation.

## 10. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Missing request-part-metadata-fields.adoc | requestPartFields("metadata", ...) not called or operation did not run. | Check test, operation ID, and descriptors. |
| Part fields cannot find field | metadata part is not the JSON expected by descriptors or path is wrong. | Check part Content-Type, body, and field path. |
| Test reports undocumented field | metadata has a field not documented in strict mode. | Add descriptor or use relaxed mode intentionally. |
| File part described as JSON fields | Confusing file part with metadata part. | Use requestParts for files; requestPartFields for structured parts. |
| Missing response-headers.adoc | responseHeaders(...) not declared. | Add descriptors to the operation. |
| Test fails due to missing response header | Documented header not returned by server. | Fix implementation or mark optional if contract allows. |
| Asciidoctor cannot find snippet | Wrong outputDir, operation ID, or part name in include path. | Inspect directory tree after tests. |
| Documentation leaks sensitive data | Fixture or response headers contain real values. | Use dummy data and preprocess/redact before writing. |

## 11. Hands-on Exercise

Build a `POST /api/documents` endpoint accepting multipart:

1. Part `metadata` containing JSON with `title`, `category`, and `published`.
2. Part `file` containing a small dummy PDF file.
3. Response returns 201 Created with `Location`, `ETag`, and `Content-Type` headers.
4. Write a MockMvc test with two `MockMultipartFile` instances.
5. Use `requestParts(...)` to document both parts.
6. Use `requestPartFields("metadata", ...)` to generate the metadata field table.
7. Use `responseHeaders(...)` to document the three response headers.
8. Include request parts, part fields, and response headers in Asciidoctor; run clean test and build the documentation.
9. Intentionally rename a field or omit a response header to observe strict validation, then update the implementation/descriptors per contract.
10. Audit the output to ensure no real files or sensitive headers appear.

**Completion criteria:** explain how request parts differ from fields within a part; understand how snippet filenames are constructed from part names; document response headers with accurate descriptors; understand strict/optional/relaxed validation; generate and include snippets in documentation built from tests.

## 12. References

- [Spring REST Docs — Request Parts](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-parts.html)
- [Spring REST Docs — Request Part Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-part-payloads.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [Spring REST Docs 3.0.6 — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring REST Docs 3.0.6 — HeaderDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/headers/HeaderDocumentation.html)
