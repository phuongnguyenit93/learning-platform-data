# Do not use form documentation for multipart parts in Spring REST Docs

## 1. Boundary between form parameters and multipart parts

Spring REST Docs provides distinct snippet groups to describe different HTTP structures. For **application/x-www-form-urlencoded** requests, data is sent as name/value pairs in the body and documented using `formParameters(...)`. For **multipart/form-data** requests, the body consists of multiple independent parts, each with its own headers and content. That case requires `requestParts(...)`, and `requestPartFields(...)` when a part contains structured JSON.

Choose snippets based on **Content-Type and wire structure**, not on whether a field happens to be called a "form field" in the UI:

| Request body | Structure | Spring REST Docs |
| --- | --- | --- |
| `application/x-www-form-urlencoded` | `name=value` pairs joined by `&` | `formParameters(...)` |
| `multipart/form-data; boundary=...` | Multiple parts, each with headers and payload | `requestParts(...)` |
| Multipart part containing JSON | JSON nested inside a part | `requestPartFields(...)` |
| JSON as the entire request body | Request-level JSON document | `requestFields(...)` |

In the **SPRING_REST_DOCS** module, HTTP tests using MockMvc, WebTestClient, or REST Assured generate snippets for requests, responses, payloads, parameters, and headers. Those snippets are assembled into Asciidoctor/Markdown and integrated into build/CI. Using `formParameters` to document a multipart upload is a structural mismatch: UI field names do not replace per-part metadata.

## 2. The two wire formats from an HTTP perspective

### 2.1. URL-encoded form

```http
POST /preferences HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

email=mai%40example.com&plan=pro&topics=java&topics=spring
```

The body contains name/value pairs. Parameter names can repeat to send multiple values. The content has no per-part headers, filenames, or boundaries. Use `formParameters(...)` to document `email`, `plan`, and `topics`.

### 2.2. Multipart form

```http
POST /documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----ExampleBoundary

------ExampleBoundary
Content-Disposition: form-data; name="title"

Course materials
------ExampleBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"category":"lesson","published":false}
------ExampleBoundary
Content-Disposition: form-data; name="attachments"; filename="lesson-a.txt"
Content-Type: text/plain

File A content
------ExampleBoundary--
```

Each part begins with a boundary. The `Content-Disposition` header identifies the part name and may include a filename; `Content-Type` can describe the part's content type. In this example:

- `title` is a text part.
- `metadata` is a JSON part.
- `attachments` is a file part.

All three are **multipart parts**. A text part does not become a URL-encoded form parameter simply because its content is a string. When the API contract specifies a multipart request, document part names and purposes using `requestParts(...)`.

The example is simplified for readability. Real multipart requests use the boundary declared in `Content-Type` and MIME-compliant delimiters with proper CRLF line endings. Do not hardcode boundaries in client code; let the HTTP client generate a boundary matching the body.

## 3. Why is `formParameters(...)` unsuitable for multipart?

`formParameters(...)` generates snippets for form parameters of a URL-encoded form. Multipart requests have dedicated documentation constructs:

- `requestParts(...)` describes parts present in a multipart request.
- `requestPartFields(...)` describes fields inside a part with a structured payload, such as JSON.
- `requestPartBody(...)` records the body content of a part when you want to document its raw payload.

Do not confuse `requestFields(...)` with `requestPartFields(...)`. The difference lies at the payload level:

| API | Data level documented | Example |
| --- | --- | --- |
| `formParameters` | Parameter name in a URL-encoded body | `topics=java` |
| `requestParts` | Part name in a multipart body | `attachments` part |
| `requestPartFields` | Field inside a single part's payload | `metadata.category` |
| `requestFields` | Field in the entire request JSON body | Request-level JSON document |

In multipart, `title` is also a part. Do not place `title` inside `formParameters(...)` just because it is text. Doing so mixes two body formats in the documentation and leaves clients unsure whether to send URL-encoded or multipart requests.

## 4. Spring MVC controller receiving multipart

Example endpoint accepting a title, JSON metadata, and up to two files:

```java
package example.docs;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/documents")
public class DocumentController {
    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<Void> create(
            @RequestPart("title") String title,
            @RequestPart("metadata") DocumentMetadata metadata,
            @RequestPart("attachments") List<MultipartFile> attachments) {
        if (title.isBlank() || attachments.isEmpty() || attachments.size() > 2) {
            return ResponseEntity.badRequest().build();
        }
        if (attachments.stream().anyMatch(MultipartFile::isEmpty)) {
            return ResponseEntity.badRequest().build();
        }
        // Example: metadata/file persistence omitted.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

The metadata part has the Java type:

```java
package example.docs;

public record DocumentMetadata(String category, boolean published) {
}
```

With `@RequestPart("metadata")`, Spring uses a message converter to deserialize a part with a matching media type (in this example, `application/json`) into `DocumentMetadata`. For uploaded files, `MultipartFile` represents the file's content and metadata.

Key notes:

- `@RequestPart` is appropriate when a part needs conversion via a message converter, especially JSON/XML.
- `@RequestParam` can also bind multipart elements in some Spring MVC cases, but it does not turn the request into a URL-encoded form.
- `consumes = MULTIPART_FORM_DATA_VALUE` declares the media type of the overall request.
- Clients must send the exact part names: `title`, `metadata`, and `attachments`. Multiple files sharing a name can bind into `List<MultipartFile>`.
- Production applications need size limits, content validation, filename handling, media-type checks, access control, and storage policies.

## 5. MockMvc: constructing multipart requests

### 5.1. Testing with text parts and file parts

`MockMultipartFile` creates test content without needing real files on disk:

```java
package example.docs;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(DocumentController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class DocumentMultipartDocumentationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentsMultipartRequestParts() throws Exception {
        MockMultipartFile title = new MockMultipartFile(
                "title", "", "text/plain",
                "Course materials".getBytes(StandardCharsets.UTF_8));
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata", "", MediaType.APPLICATION_JSON_VALUE,
                "{\"category\":\"lesson\",\"published\":false}"
                        .getBytes(StandardCharsets.UTF_8));
        MockMultipartFile attachment = new MockMultipartFile(
                "attachments", "lesson-a.txt", "text/plain",
                "File A content".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/documents")
                .file(title)
                .file(metadata)
                .file(attachment))
            .andExpect(status().isCreated())
            .andDo(document("documents/create-multipart",
                requestParts(
                    partWithName("title")
                        .description("Text document title"),
                    partWithName("metadata")
                        .description("Document JSON metadata"),
                    partWithName("attachments")
                        .description("Attached file; part with the same name may repeat")
                )
            ));
    }
}
```

`title` and `metadata` are constructed with `MockMultipartFile`, so they are also multipart parts. The first constructor argument is the part name; an empty filename represents a non-file part. `attachments` specifies a filename to represent an uploaded file.

### 5.2. Repeated part names

If the API accepts multiple files under the shared name `attachments`, create multiple `MockMultipartFile` instances:

```java
MockMultipartFile first = new MockMultipartFile(
        "attachments", "lesson-a.txt", "text/plain",
        "File A".getBytes(StandardCharsets.UTF_8));
MockMultipartFile second = new MockMultipartFile(
        "attachments", "lesson-b.txt", "text/plain",
        "File B".getBytes(StandardCharsets.UTF_8));

mockMvc.perform(multipart("/documents")
        .file(first)
        .file(second))
    .andExpect(status().isCreated());
```

A single `partWithName("attachments")` descriptor documents the **part name**. It does not generate two descriptors based on file count, nor does it check count limits automatically. Separate tests/assertions must verify file count, non-empty files, size, and content type.

### 5.3. Choosing the right descriptors

In a multipart test, do not use:

```java
formParameters(
    parameterWithName("title").description("Title"),
    parameterWithName("attachments").description("Attached files")
)
```

Instead, use:

```java
requestParts(
    partWithName("title").description("Text title"),
    partWithName("attachments").description("Attached files")
)
```

Matching field names do not make the two snippet types interchangeable. The HTTP contract is multipart, so the snippet table must document the part names properly.

## 6. Documenting JSON parts with requestPartFields(...)

`requestParts(...)` documents the presence and purpose of each part. When a part has a JSON structure, you can document it in deeper detail with `requestPartFields("metadata", ...)`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

mockMvc.perform(multipart("/documents")
        .file(title)
        .file(metadata)
        .file(attachment))
    .andExpect(status().isCreated())
    .andDo(document("documents/create-multipart-with-metadata",
        requestParts(
            partWithName("title").description("Text title"),
            partWithName("metadata").description("JSON metadata"),
            partWithName("attachments").description("Attached files")
        ),
        requestPartFields("metadata",
            fieldWithPath("category").description("Document category"),
            fieldWithPath("published").description("Publication status")
        )
    ));
```

`requestPartFields` reads the payload of the named part and generates a dedicated fields snippet. Field names in the descriptors are relative paths inside the JSON metadata, not the part name itself.

| Level | Descriptor | Interpretation |
| --- | --- | --- |
| Part name | `partWithName("metadata")` | A part named `metadata` exists |
| JSON field in part | `fieldWithPath("category")` | Metadata contains the `category` field |
| Another JSON field | `fieldWithPath("published")` | Metadata contains the `published` field |

If the JSON metadata has nested objects, use paths such as `owner.name` or `labels[]`. Descriptors must match the actual payload in the part. If a part is a binary file, never apply `requestPartFields` to the file's content as though it were a JSON object.

### 6.1. requestPartBody(...) for raw payloads

When you want to capture a part's body without describing individual fields, you can use the request part body snippet:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

mockMvc.perform(multipart("/documents")
        .file(title)
        .file(metadata)
        .file(attachment))
    .andDo(document("documents/metadata-body",
        requestParts(
            partWithName("metadata").description("JSON metadata")
        ),
        requestPartBody("metadata")
    ));
```

Choose the right approach: `requestPartFields` for JSON contracts with a well-defined schema; `requestPartBody` for raw body examples. You can combine either with `requestParts` to explain the part's role.

## 7. Distinguishing from a top-level JSON body

**Full-body JSON request:**

```http
POST /documents HTTP/1.1
Content-Type: application/json

{"title":"Document","category":"lesson"}
```

Use `requestFields(...)`.

**Multipart with a JSON part:**

```http
POST /documents HTTP/1.1
Content-Type: multipart/form-data; boundary=...

--boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"category":"lesson"}
--boundary--
```

Use `requestParts(...)` and `requestPartFields("metadata", ...)`.

**URL-encoded form:**

```http
POST /documents HTTP/1.1
Content-Type: application/x-www-form-urlencoded

title=Document&category=lesson
```

Use `formParameters(...)`.

Do not choose `requestFields` simply because a multipart request contains a JSON part. `requestFields` targets a JSON document that makes up the entire request payload; a JSON part is nested inside multipart and requires `requestPartFields`.

## 8. WebTestClient and REST Assured

### 8.1. WebTestClient

WebTestClient can construct multipart requests using a multipart inserter. Overview example for a WebFlux test:

```java
MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("title", "Course materials")
    .contentType(MediaType.TEXT_PLAIN);
builder.part("metadata", new DocumentMetadata("lesson", false))
    .contentType(MediaType.APPLICATION_JSON);
builder.part("attachments", new ByteArrayResource(
        "File A content".getBytes(StandardCharsets.UTF_8)))
    .filename("lesson-a.txt")
    .contentType(MediaType.TEXT_PLAIN);

webTestClient.post()
    .uri("/documents")
    .body(BodyInserters.fromMultipartData(builder.build()))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("documents/webtestclient-multipart",
        requestParts(
            partWithName("title").description("Document title"),
            partWithName("metadata").description("JSON metadata"),
            partWithName("attachments").description("Attached files")
        )
    ));
```

This example assumes WebTestClient is integrated with Spring REST Docs and the application has a WebFlux handler accepting multipart. Multipart handling in WebFlux differs from Spring MVC: you may use `@RequestPart`, `FilePart`, `Part`, or `ServerWebExchange` depending on the contract and data types.

### 8.2. REST Assured

With REST Assured, the multipart API lets you send individual parts:

```java
given(specification)
    .filter(document("documents/rest-assured-multipart",
        requestParts(
            partWithName("title").description("Title"),
            partWithName("metadata").description("JSON metadata"),
            partWithName("attachments").description("Attached files")
        )))
    .multiPart("title", "Course materials", "text/plain")
    .multiPart("metadata",
        "{\"category\":\"lesson\",\"published\":false}",
        "application/json")
    .multiPart("attachments", new File("src/test/resources/lesson-a.txt"))
    .when()
    .post("/documents")
    .then()
    .statusCode(201);
```

The file path is an illustrative fixture; the project must supply the file in test resources. When sending multipart requests, do not manually set a boundary. The HTTP client must synchronize the boundary in the header with the delimiter in the body.

## 9. Organizing snippets and Asciidoctor

If the test uses the `documents/create-multipart-with-metadata` identifier, the output directory may contain:

```text
build/generated-snippets/
└── documents/
    └── create-multipart-with-metadata/
        ├── http-request.adoc
        ├── http-response.adoc
        ├── request-parts.adoc
        ├── request-part-metadata-fields.adoc
        └── ...
```

The exact snippet filenames depend on the configured operations and Spring REST Docs version; check the actual output after running tests to write accurate includes. Asciidoctor template:

```adoc
= Documents API

== Create multipart document

=== HTTP request
include::{snippets}/documents/create-multipart-with-metadata/http-request.adoc[]

=== Request parts
include::{snippets}/documents/create-multipart-with-metadata/request-parts.adoc[]

=== Metadata fields
include::{snippets}/documents/create-multipart-with-metadata/request-part-metadata-fields.adoc[]

=== HTTP response
include::{snippets}/documents/create-multipart-with-metadata/http-response.adoc[]
```

The `snippets` attribute must point to the root directory, such as `build/generated-snippets`. The `include::...[]` syntax is Asciidoctor; standard Markdown renderers do not interpret it automatically. If your primary documentation uses Markdown, link to rendered HTML or use a controlled conversion step.

With Gradle Groovy DSL, assuming the Asciidoctor plugin is installed:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.absolutePath
}
```

CI runs:

```bash
./gradlew test asciidoctor
```

If part descriptors change, documentation tests re-verify part names and fields. When tests fail or snippets are not generated, the documentation build should fail rather than keeping stale snippets from a previous build.

## 10. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Used `formParameters` for uploads | Confused text part with URL-encoded parameter | Use `requestParts(partWithName(...))` |
| Used `requestFields` for a JSON part | Confused full-request payload with part-nested payload | Use `requestPartFields("metadata", ...)` |
| Filename missing from parts table | Descriptor only lists part name and description | Include `http-request.adoc` to show sample request/filename/headers |
| Multipart request returns 415 | Endpoint `consumes` does not accept multipart or client sent wrong media type | Use `multipart/form-data` and verify mapping |
| Server cannot read JSON metadata | Part lacks or has wrong `Content-Type: application/json` | Attach the media type to the metadata part and check converters |
| `requestPartFields` cannot find field | JSON payload differs from descriptors or part name is wrong | Compare JSON payload and part name |
| Empty or oversized file passes tests | Only documented part name without verifying business rules | Add assertions for file size, content, and count limits |
| Constructed boundary manually | Header and body delimiter out of sync | Let the multipart builder/HTTP client generate the boundary |
| Asciidoctor cannot find request-part snippet | Include filename does not match actual output | Check `generated-snippets` directory after running tests |

## 11. Practice exercise

Build `POST /assignments` accepting multipart:

| Part | Content | Rule |
| --- | --- | --- |
| `title` | Text | Required, non-blank |
| `metadata` | JSON | Contains `courseId`, `visibility` |
| `files` | File | 1 to 3 files, sharing the same part name |

Steps:

1. Create a Spring MVC controller receiving text, JSON metadata, and `List<MultipartFile>`.
2. Write a MockMvc test using `MockMultipartFile` for all three part types.
3. Use `requestParts(...)` to document the parts; use `requestPartFields("metadata", ...)` for the JSON metadata.
4. Write tests for missing `title`, invalid metadata, zero files, and more than three files. Assert error statuses/responses separately.
5. Create an equivalent test using WebTestClient or REST Assured.
6. Embed HTTP request, request-parts, metadata fields, and response in Asciidoctor; run tests before rendering in CI.

**Pass criteria:** documentation accurately describes the multipart body; text, file, and JSON items are all recognized as parts; the JSON part has its own schema; clients can construct valid requests from the documentation.

## References

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html)
- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring Framework — Multipart Forms](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework — MockMultipartHttpServletRequestBuilder API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/web/servlet/request/MockMultipartHttpServletRequestBuilder.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
