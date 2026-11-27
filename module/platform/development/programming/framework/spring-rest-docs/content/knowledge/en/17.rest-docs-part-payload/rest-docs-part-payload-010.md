# Handling Multiple Request Parts of the Same Type in Spring REST Docs

## 1. The multiple files with the same part name pattern

An upload endpoint may receive multiple files within the same `multipart/form-data` request. For example, three attached images for an article are sent as three separate parts, all sharing the name `attachments`:

```http
Content-Disposition: form-data; name="attachments"; filename="front.png"
Content-Type: image/png

<front image bytes>
------boundary
Content-Disposition: form-data; name="attachments"; filename="side.png"
Content-Type: image/png

<side image bytes>
------boundary
Content-Disposition: form-data; name="attachments"; filename="back.png"
Content-Type: image/png

<back image bytes>
```

Each file is a **part occurrence** (one appearance in the body). Occurrences share the same **part name** while having their own filenames. RFC 7578 Section 4.3 specifies that multiple files for the same form field are sent as multiple separate parts using the same `name` parameter.

Spring REST Docs describes part names using `requestParts(...)` and `partWithName(...)`. The `request-parts.adoc` snippet is a table of parts supported by the resource; it does not represent the cardinality (number of repetitions) of the same name as separate rows. Therefore, document `attachments` once and explain that it is a multi-file field. Application tests must verify the count, filenames, content types, and rules for each file.

This lesson focuses on multiple files sharing a name, multiple file fields with different names yet the same media type, collection binding in Spring MVC, multipart builders in MockMvc/WebTestClient/REST Assured, and documentation integration into CI.

## 2. Distinguishing occurrence, part name, and media type

| Concept | Example | Meaning |
| --- | --- | --- |
| Part occurrence | First, second, and third files | One appearance in the multipart body |
| Part name | `attachments` | Multipart field name; multiple occurrences may share this name |
| Filename | `front.png` | Filename supplied by the client |
| Content-Type | `image/png` | Content type of each occurrence |

Having the same media type does not mean having the same part name. For example, `frontCover` and `backCover` may both be `image/png` yet remain two distinct fields:

```java
requestParts(
    partWithName("frontCover").description("Front cover image"),
    partWithName("backCover").description("Back cover image")
)
```

Conversely, multiple files for the `attachments` field share the same part name. Do not rename them to `attachments1`, `attachments2` if the API contract defines a repeating field.

## 3. Spring MVC binding multiple files with the same name

Spring MVC supports binding multiple files sharing the same parameter name into `List<MultipartFile>` or `MultipartFile[]`. For example:

```java
@PostMapping(
    value = "/articles/{articleId}/attachments",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<?> upload(
        @PathVariable String articleId,
        @RequestParam("attachments") List<MultipartFile> attachments) {
    // Validate collection and process each file.
}
```

`@RequestParam("attachments")` specifies the multipart field name. The collection represents the files sharing that name. Do not declare a single `MultipartFile` if the contract requires accepting all occurrences.

| Parameter type | When appropriate |
| --- | --- |
| `List<MultipartFile>` | Variable number of files; convenient for collection validation |
| `MultipartFile[]` | Want to process as an array |
| `MultipartFile` | Contract allows only a single file |
| `MultiValueMap<String, MultipartFile>` | Need access to multiple file groups by dynamic names |

With collections, decide clearly whether ordering is part of the contract. If order does not matter, avoid tests that depend on order. If order is meaningful, such as pages of a document, document and verify that rule.

## 4. Documenting repeating part names with Spring REST Docs

Use one descriptor for the part name:

```java
requestParts(
    partWithName("attachments")
        .description("List of image files; each file is sent as a separate part named attachments")
)
```

The descriptor references `name="attachments"`, not filenames. Do not create dummy descriptors for each occurrence. The snippet has one row for the part name, while the Description clarifies multiplicity.

**Limitation:** `requestParts` documents supported part names and checks parts according to strict/relaxed mode. It does not replace tests checking file count, minimum/maximum limits, size, or order. Those rules require separate validation/assertions.

### 4.1. File collection alongside JSON metadata

A request may contain a repeating `attachments` field and a `metadata` part:

```java
requestParts(
    partWithName("attachments")
        .description("Multiple image files; each file is a part with the same name"),
    partWithName("metadata")
        .description("Shared JSON metadata for the image group")
),
requestPartFields("metadata",
    fieldWithPath("caption").description("Shared caption"),
    fieldWithPath("source").description("Image source")
)
```

`requestPartFields` only describes the JSON metadata. Do not use this API to document image file bytes.

## 5. Complete MockMvc example

The example uses JUnit 5, Java 17+, MockMvc, and Spring REST Docs. The byte fixtures below are only for testing multipart binding; they are not valid PNG images for testing an image decoder.

```java
import java.util.List;
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
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
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
class MultipleAttachmentPartsDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new AttachmentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void uploadSeveralFilesWithOnePartName() throws Exception {
        MockMultipartFile front = new MockMultipartFile(
                "attachments", "front.png",
                MediaType.IMAGE_PNG_VALUE, new byte[] {1, 2, 3});
        MockMultipartFile side = new MockMultipartFile(
                "attachments", "side.png",
                MediaType.IMAGE_PNG_VALUE, new byte[] {4, 5, 6});
        MockMultipartFile back = new MockMultipartFile(
                "attachments", "back.png",
                MediaType.IMAGE_PNG_VALUE, new byte[] {7, 8, 9});

        this.mockMvc.perform(multipart("/articles/{id}/attachments", "42")
                        .file(front)
                        .file(side)
                        .file(back)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.count").value(3))
                .andExpect(jsonPath("$.files[0].filename").value("front.png"))
                .andExpect(jsonPath("$.files[1].filename").value("side.png"))
                .andExpect(jsonPath("$.files[2].filename").value("back.png"))
                .andDo(document("articles-attachments-upload",
                        requestParts(
                            partWithName("attachments")
                                .description("Multiple image files; each file is a part with the same name attachments")
                        )
                ));
    }

    @RestController
    static class AttachmentController {

        @PostMapping(
            value = "/articles/{id}/attachments",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        ResponseEntity<Map<String, Object>> upload(
                @PathVariable String id,
                @RequestParam("attachments") List<MultipartFile> attachments) {

            if (attachments.isEmpty() || attachments.size() > 3) {
                return ResponseEntity.badRequest().build();
            }

            List<Map<String, Object>> files = attachments.stream()
                    .map(file -> Map.<String, Object>of(
                            "filename", file.getOriginalFilename(),
                            "contentType", file.getContentType(),
                            "size", file.getSize()))
                    .toList();

            return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
                    "articleId", id,
                    "count", attachments.size(),
                    "files", files
            ));
        }
    }
}
```

All three `MockMultipartFile` instances share the name `attachments`, yet have distinct filenames. The controller binds them to `List<MultipartFile>`, enforces the 1–3 file limit, and returns metadata so the test verifies the count and filenames. `requestParts` generates the parts table; assertions verify the application's binding behavior and cardinality.

### 5.1. Why is the first parameter identical?

The signature `MockMultipartFile(name, originalFilename, contentType, content)` separates part name from filename. All three fixtures pass `attachments` as `name`, while `front.png`, `side.png`, and `back.png` are filenames. Changing `name` to `front`/`side`/`back` would create three distinct multipart fields.

## 6. Verifying count and per-file metadata

| Rule | How to verify |
| --- | --- |
| At least one file | Non-empty collection or return validation error |
| Maximum file count | Check `attachments.size()` |
| Size of each file | `MultipartFile.getSize()` |
| Content-Type | `getContentType()` and format verification if needed |
| Filename | Check empty names, length, characters, and normalization |
| File content | Parser, magic bytes, checksum, or business checks |
| Order | Assert only if ordering is part of the contract |
| Duplicate files | Check checksum or business identifier if needed |

With a limit of one to three files, create test cases for 0, 1, 3, and 4 files. If limits apply per file, check each size; if there is a total request limit, sum the sizes across the collection. Over-limit error tests should have a separate operation identifier if error documentation needs to be generated.

Do not assume ordering is part of the contract. If order does not matter, compare sets of metadata instead of relying on indices; if it is meaningful, define and test it explicitly.

## 7. Multiple part names with the same file type

If an endpoint accepts two fixed image roles, the part names differ even though both have `Content-Type` `image/png`:

```java
@PostMapping(value = "/products", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
ResponseEntity<?> uploadProductImages(
        @RequestPart("frontCover") MultipartFile frontCover,
        @RequestPart("backCover") MultipartFile backCover) {
    // ...
}
```

Document with two descriptors:

```java
requestParts(
    partWithName("frontCover").description("Front cover image"),
    partWithName("backCover").description("Back cover image")
)
```

Do not use an `attachments` collection if the API defines two fixed roles. Both controller and documentation must accurately reflect the contract, not merely the fact that both files share a media type.

## 8. WebTestClient sending multiple parts with the same name

`MultiValueMap<String, Object>` allows multiple values per key. Call `add` multiple times:

```java
MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();

Resource front = new ByteArrayResource(new byte[] {1, 2, 3}) {
    @Override
    public String getFilename() {
        return "front.png";
    }
};
Resource side = new ByteArrayResource(new byte[] {4, 5, 6}) {
    @Override
    public String getFilename() {
        return "side.png";
    }
};

parts.add("attachments", front);
parts.add("attachments", side);

webTestClient.post()
    .uri("/articles/42/attachments")
    .body(BodyInserters.fromMultipartData(parts))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("articles-attachments-upload",
        requestParts(
            partWithName("attachments")
                .description("List of files; multiple occurrences sharing the name attachments")
        )
    ));
```

Using `set` can replace the previous value. WebTestClient must have the REST Docs documentation filter attached on the builder before building. Integration tests should verify the server binds all files.

## 9. REST Assured sending multiple parts with the same name

REST Assured allows calling `multiPart` multiple times with the same part name:

```java
given(this.spec)
    .filter(document("articles-attachments-upload",
        requestParts(
            partWithName("attachments")
                .description("List of image files; each file is a part with the same name")
        )
    ))
    .multiPart("attachments", new File("front.png"), "image/png")
    .multiPart("attachments", new File("side.png"), "image/png")
    .multiPart("attachments", new File("back.png"), "image/png")
    .when()
    .post("/articles/42/attachments")
    .then()
    .statusCode(201);
```

Each call adds one occurrence. Use fixture files inside the project rather than referencing arbitrary paths on a developer's machine. `spec` and the REST Docs filter must be configured according to your project's test framework.

## 10. Snippet names and Asciidoctor documentation

With the operation identifier `articles-attachments-upload`, the primary snippets are typically located at:

```text
build/generated-snippets/
└── articles-attachments-upload/
    ├── request-parts.adoc
    ├── http-request.adoc
    └── http-response.adoc
```

Authoring example:

```asciidoc
== POST /articles/{id}/attachments

The `attachments` field accepts one to three image files.
Clients send each file as a separate part; all parts in the group
use the same name `attachments`. `filename` is per-file metadata.

=== Multipart parts

include::{snippets}/articles-attachments-upload/request-parts.adoc[]

=== Collection rules

* Part name: `attachments`.
* Count: 1 to 3 files.
* Media type: image formats supported by the endpoint.
* Each file has its own filename and content.
* Ordering is meaningful only if explicitly specified by the contract.
```

The `request-parts` table documents the part name and Description. Cardinality, media type, and ordering must be explained per contract and tested separately; do not infer maximum counts from a single snippet row.

## 11. Optional, ignored, and relaxed

`optional()` on a descriptor allows the entire multipart field to be absent per contract; it does not define maximum occurrences. If the API allows 0–3 files, document that clearly and validate collection size from 0 to 3.

`ignored()` is used for a known part intentionally excluded from the snippet. `relaxedRequestParts(...)` allows undocumented part names to appear without failing the test. Relaxed mode does not check cardinality, size, or bytes.

| Need | Implementation |
| --- | --- |
| `attachments` field required | `partWithName("attachments")` without `optional` |
| Entire field may be absent | Mark descriptor `optional()` |
| Limit of 1–3 files | Validation/assertions on the collection |
| Skip a technical part | `ignored()` |
| Document a subset of part names | `relaxedRequestParts(...)` |
| Check media type of each file | Iterate collection and validate each `MultipartFile` |

## 12. Common errors

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Only one file received | Controller binds to a single `MultipartFile` | Use `List<MultipartFile>` or an array |
| Files become separate fields | Client sends names front/side/back | Send the same `attachments` name with separate filenames |
| `request-parts` table has only one row | Confusing part-name snippet with an occurrence table | Explain multiplicity and assert collection size |
| WebTestClient sends only the last file | Used `set` instead of `add` | Call `add` multiple times with the same key |
| REST Assured sends wrong parts | Inconsistent name passed to `multiPart` | Use the same name across all calls |
| Test passes despite exceeding file count | Only documenting part name without validating collection | Add cardinality assertions/validation |
| Order assertions are flaky | Contract does not guarantee ordering | Compare sets or define ordering explicitly |
| Only the first file's media type is checked | Validation does not iterate the collection | Validate every file |
| Duplicate filenames cause overwrites | Using client filename as storage name | Generate server-managed storage keys |
| Asciidoctor missing snippet | Wrong operation ID or test didn't generate files | Check output directory and task dependencies |

## 13. Build and CI

With Gradle Groovy DSL, assuming the project already has REST Docs and Asciidoctor configured:

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

CI should verify:

1. Tests send the expected number of occurrences for repeating parts.
2. Controller binds all files into a collection or array.
3. Assertions verify count limits.
4. Each file is verified for filename, content type, size, and content per contract.
5. `requestParts` documents the part name and Asciidoctor includes the exact operation.
6. Tests cover 0, 1, maximum, and over-limit counts.
7. Fixtures are small, deterministic, synthetic, and contain no sensitive data.

With Maven, snippets are typically in `target/generated-snippets`; the documentation build step runs after the tests generating snippets.

## 14. Hands-on exercise

Extend the `POST /articles/{id}/attachments` endpoint:

1. Switch the controller to `List<MultipartFile>` and send three parts sharing the name `attachments`.
2. Use a single `partWithName("attachments")` whose Description explains that each file is an occurrence sharing the same name.
3. Create tests for 0, 1, 3, and 4 files; verify the 1–3 limit.
4. Assert filename and Content-Type for each file; add an empty-file test case.
5. Decide whether ordering is part of the contract; if so, assert it; if not, avoid relying on index positions.
6. Call `MultiValueMap.add("attachments", ...)` twice in WebTestClient.
7. Call `multiPart("attachments", ...)` multiple times in REST Assured.
8. Create another endpoint accepting `frontCover` and `backCover` to distinguish part names from media types.
9. Include `request-parts.adoc` and state cardinality rules in Asciidoctor.
10. Run `./gradlew clean test asciidoctor` in the configured project.

**Completion criteria:** distinguish occurrence, part name, and media type; send multiple files sharing a name; document the part name accurately; verify cardinality via application tests; and explain the contract in documentation.

## 15. Self-check questions

**1. How are multiple files for the same field represented?**

Each file is a separate part, while the parts share the same `name` parameter; each part has its own `filename`.

**2. Which types does Spring MVC use to bind multiple files sharing a name?**

You can use `List<MultipartFile>` or `MultipartFile[]`.

**3. Do you need to create descriptors attachments1, attachments2, and attachments3?**

No. If the wire format uses the same `name="attachments"`, document a single `partWithName("attachments")` descriptor and explain that the field accepts multiple files.

**4. Does the request-parts snippet validate the number of files?**

No. It describes supported part names. Cardinality must be checked via validation/assertions.

**5. If frontCover and backCover are both PNGs, should they use a single descriptor?**

No, if their part names differ. Use a separate descriptor for each `name` and describe its role.

**6. How does MultiValueMap send multiple parts sharing the same name?**

Call `add("attachments", value)` multiple times; `set` can overwrite the value previously bound to the key.

## References

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): request parts, strict/relaxed documentation, and snippets.
- [RFC 7578 — Section 4.3](https://www.rfc-editor.org/rfc/rfc7578.html#section-4.3): multiple files for one form field.
- [Spring Framework — Multipart forms](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): binding multiple files with the same parameter name into a `MultipartFile` List/array.
