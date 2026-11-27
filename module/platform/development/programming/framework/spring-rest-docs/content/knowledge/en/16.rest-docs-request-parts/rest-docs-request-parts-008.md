# Validating Multipart Requests with MockMvc

## 1. Why Test Multipart Requests?

An upload operation typically accepts multiple content types in a single HTTP request: a binary file, JSON metadata, and sometimes text fields or preview files. With `multipart/form-data`, each piece is sent as a separate **part** with its own name and potentially its own `Content-Type`, filename, and headers.

For example, `POST /api/products/42/assets` accepts:

- `image`: PNG or JPEG image file.
- `metadata`: JSON describing the image.
- `caption`: optional text.

MockMvc lets you construct multipart requests in a Spring MVC test suite without opening a real HTTP port. You can verify that the controller binds parts accurately, check response status/body, test validation, and use that exact request to generate Spring REST Docs snippets.

In the **SPRING_REST_DOCS** module, these tests serve as the source of truth for REST API documentation. `requestParts(...)` documents part names and roles; `requestPartFields(...)` documents fields inside JSON parts; `requestPartBody(...)` includes a sample body of a part in the documentation.

After this lesson, you will be able to:

- Build multipart requests using `MockMvcRequestBuilders.multipart(...)`.
- Use `MockMultipartFile` for files and `MockPart` for general parts like JSON.
- Attach proper Content-Types to individual parts and verify binding results.
- Test required, optional, absent, empty parts, and zero-byte files.
- Combine MockMvc with `requestParts`, `requestPartFields`, and `requestPartBody`.
- Recognize the limitations of MockMvc compared to testing against a real servlet container.
- Integrate tests and snippets into build/CI.

## 2. Multipart Requests in MockMvc

A multipart request has two structural layers:

```text
HTTP request
Content-Type: multipart/form-data; boundary=...

  Part "image"
    Content-Disposition: form-data; name="image"; filename="cover.png"
    Content-Type: image/png
    Body: <binary bytes>

  Part "metadata"
    Content-Disposition: form-data; name="metadata"
    Content-Type: application/json
    Body: {"title":"Book Cover"}
```

Content-Type at the request level is `multipart/form-data`; the boundary separates parts. Each part can have its own Content-Type such as `image/png` or `application/json`.

In MockMvc, the `multipart(...)` builder constructs a simulated multipart request for Spring MVC. This builder creates a mock request; you add parts using `.file(...)` or `.part(...)`.

```java
mockMvc.perform(multipart("/api/products/{id}/assets", 42)
        .file(imageFile)
        .part(metadataPart))
    .andExpect(status().isCreated());
```

Key points to remember:

- Use `.file(...)` when building a `MultipartFile` with filename, content type, and bytes.
- Use `.part(...)` when representing a general part and configuring headers directly.
- Part names must match what the controller expects via `@RequestPart` or `@RequestParam`.
- Do not set `image/png` as the Content-Type of the entire request; that is the Content-Type of the image part.
- The multipart builder constructs the overall request automatically. Do not write boundaries manually when using the builder.

## 3. Building a File Part with `MockMultipartFile`

`MockMultipartFile` is a Spring Test utility for creating a file part inside a test suite.

```java
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile image = new MockMultipartFile(
        "image",                    // Part name
        "cover.png",                // Filename sent by client
        MediaType.IMAGE_PNG_VALUE,  // Content-Type of the part
        imageBytes                  // File content
);
```

The commonly used constructor takes four values:

| Parameter | Example | Meaning |
| --- | --- | --- |
| `name` | `image` | Part name in the multipart request |
| `originalFilename` | `cover.png` | Filename sent by the client |
| `contentType` | `image/png` | Content-Type of the part |
| `content` | `byte[]` | File bytes |

Part name and filename are two different values. `partWithName("image")` uses `name`, whereas `cover.png` is the filename passed in `Content-Disposition`.

### 3.1. Using Fixture Files in Test Resources

If the endpoint inspects file signatures or parses images, do not use a few arbitrary bytes. Place a small, valid PNG file in `src/test/resources/fixtures/cover.png`, then read its bytes:

```java
byte[] imageBytes;

try (InputStream input = getClass()
        .getResourceAsStream("/fixtures/cover.png")) {
    if (input == null) {
        throw new IllegalStateException("Missing PNG test fixture");
    }
    imageBytes = input.readAllBytes();
}

MockMultipartFile image = new MockMultipartFile(
        "image",
        "cover.png",
        MediaType.IMAGE_PNG_VALUE,
        imageBytes
);
```

Fixtures must match the application's validator. A file with a `.png` extension and `image/png` header can still contain non-PNG bytes.

### 3.2. Creating a Zero-Byte File Part

To test an empty file:

```java
MockMultipartFile emptyImage = new MockMultipartFile(
        "image",
        "empty.png",
        MediaType.IMAGE_PNG_VALUE,
        new byte[0]
);
```

This part is still present in the request, just with no content. It differs from the case where the client does not send the `image` part at all.

## 4. Building a JSON Part with `MockPart`

When metadata is JSON, `MockPart` lets you configure a dedicated Content-Type header:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockPart;

String json = """
        {
          "title": "Book Cover",
          "description": "Cover image for the new edition",
          "displayOrder": 1
        }
        """;

MockPart metadata = new MockPart(
        "metadata",
        json.getBytes(StandardCharsets.UTF_8)
);
metadata.getHeaders().setContentType(MediaType.APPLICATION_JSON);
```

The name `metadata` must match the part name expected by the controller. Content-Type `application/json` helps Spring MVC choose the JSON `HttpMessageConverter` to convert the body into a DTO when using `@RequestPart`.

Without the right Content-Type, the converter may fail to determine how to read the body or return a media type error. Tests should send the exact Content-Type that real clients use.

### 4.1. When to Use `MockMultipartFile` vs. `MockPart`?

| Scenario | Suitable Tool |
| --- | --- |
| File upload with filename, content type, and bytes | `MockMultipartFile` |
| JSON part needing `application/json` header | `MockPart` |
| Simple text part | `MockPart` |
| Testing uploaded file's filename | `MockMultipartFile` |
| Customizing multiple headers on a part | `MockPart` |

You can use `MockMultipartFile` for JSON metadata if desired by setting content type `application/json`; `MockPart` expresses intent more clearly when the part is not a file.

## 5. Sample Controller for Testing Binding

Suppose the endpoint accepts a file and metadata:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

record AssetMetadata(
        @NotBlank
        @Size(max = 120)
        String title,
        @Size(max = 1000)
        String description,
        Integer displayOrder
) {}
```

Illustrative controller:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
class ProductAssetController {

    @PostMapping(
        path = "/api/products/{productId}/assets",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    ResponseEntity<UploadResult> upload(
            @PathVariable Long productId,
            @RequestPart("image") MultipartFile image,
            @Valid @RequestPart("metadata") AssetMetadata metadata) {

        if (image.isEmpty()) {
            throw new IllegalArgumentException("Image must not be empty");
        }

        UploadResult result = new UploadResult(
                productId,
                image.getOriginalFilename(),
                metadata.title()
        );

        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }
}

record UploadResult(Long productId, String filename, String title) {}
```

In a real application, use dedicated exceptions and `@ControllerAdvice` to map errors into a stable response contract. The example above only illustrates request binding and results so tests can verify the controller received the right values.

`@RequestPart("image")` binds the file to `MultipartFile`; `@RequestPart("metadata")` uses a message converter to turn JSON into `AssetMetadata`. `@Valid` triggers Bean Validation if the project has the appropriate validation dependency.

## 6. Your First MockMvc Test

The test below verifies a valid multipart request returns `201 Created`, while checking the values received by the controller through the response.

```java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.mock.web.MockPart;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductAssetMultipartMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void acceptsImageAndJsonMetadata() throws Exception {
        MockMultipartFile image = new MockMultipartFile(
                "image",
                "cover.png",
                MediaType.IMAGE_PNG_VALUE,
                TestFixtures.validPng()
        );

        String metadataJson = """
                {
                  "title": "Book Cover",
                  "description": "Cover image for the new edition",
                  "displayOrder": 1
                }
                """;

        MockPart metadata = new MockPart(
                "metadata",
                metadataJson.getBytes(StandardCharsets.UTF_8)
        );
        metadata.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        mockMvc.perform(multipart("/api/products/{productId}/assets", 42)
                    .file(image)
                    .part(metadata)
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.productId").value(42))
                .andExpect(jsonPath("$.filename").value("cover.png"))
                .andExpect(jsonPath("$.title").value("Book Cover"));
    }
}
```

`TestFixtures.validPng()` is an illustrative helper reading a valid image fixture from test resources. Replace the helper with your project's fixture. The `jsonPath` assertions check the response built from data received by the controller; if the controller does not echo these fields back, you can use `ArgumentCaptor` to verify the service was called with the right filename, bytes, or metadata.

### 6.1. Verifying the Service Receives the Right Data

In tests using a mock service, you can capture arguments passed in with Mockito:

```java
ArgumentCaptor<AssetMetadata> metadataCaptor =
        ArgumentCaptor.forClass(AssetMetadata.class);

verify(assetService).upload(
        eq(42L),
        any(MultipartFile.class),
        metadataCaptor.capture()
);

assertEquals("Book Cover", metadataCaptor.getValue().title());
```

For files, you can capture `MultipartFile` and inspect `getOriginalFilename()`, `getContentType()`, `getSize()`, and bytes. This approach is helpful when the endpoint response does not echo back the bound data.

## 7. Validating Required and Optional Parts

MockMvc tests can construct different multipart variants. For example, an optional `thumbnail`:

```java
@PostMapping(
    path = "/api/products/{productId}/assets",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> upload(
        @PathVariable Long productId,
        @RequestPart("image") MultipartFile image,
        @RequestPart("metadata") AssetMetadata metadata,
        @RequestPart(value = "thumbnail", required = false)
                MultipartFile thumbnail) {
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

Test without sending `thumbnail`:

```java
mockMvc.perform(multipart("/api/products/{id}/assets", 42)
        .file(image)
        .part(metadata))
    .andExpect(status().isCreated());
```

Test with `thumbnail`:

```java
MockMultipartFile thumbnail = new MockMultipartFile(
        "thumbnail",
        "preview.jpg",
        MediaType.IMAGE_JPEG_VALUE,
        TestFixtures.validJpeg()
);

mockMvc.perform(multipart("/api/products/{id}/assets", 42)
        .file(image)
        .part(metadata)
        .file(thumbnail))
    .andExpect(status().isCreated());
```

When an optional part is absent, the controller parameter can receive `null` if declared `@RequestPart(required = false)`. In Spring REST Docs, the corresponding descriptor also needs `.optional()` so the snippet can be generated from a sample request omitting that part.

**Both places must stay consistent:** `required = false` controls binding in the controller; `.optional()` controls descriptor checks during snippet generation. One does not automatically change the other.

## 8. Testing Absent, Empty Parts, and Zero-Byte Files

Three scenarios should be tested separately:

| Case | How to build request | Meaning |
| --- | --- | --- |
| Absent | Do not call `.file(...)` or `.part(...)` for that name | Client did not send the part |
| Empty text part | Send `MockPart` with `new byte[0]` | Part is present, but body is empty |
| Zero-byte file | Send `MockMultipartFile` with `new byte[0]` | File part is present, size is 0 |

Example testing a zero-byte `image` part:

```java
MockMultipartFile emptyImage = new MockMultipartFile(
        "image",
        "empty.png",
        MediaType.IMAGE_PNG_VALUE,
        new byte[0]
);

mockMvc.perform(multipart("/api/products/{id}/assets", 42)
        .file(emptyImage)
        .part(metadata))
    .andExpect(status().isBadRequest());
```

Expecting `400` is only valid if the endpoint implements a rule rejecting empty files and the exception handler returns that status. Do not infer server behavior from REST Docs descriptors.

For missing required parts, a controller with `@RequestPart("image")` requires the part by default. Spring MVC normally returns `400 Bad Request` when this part is absent, though the final result also depends on exception handling. Write assertions matching your application's actual response contract.

## 9. Verifying Content-Type of Individual Parts

The overall request must be `multipart/form-data`; each part has its own media type. In MockMvc:

```java
MockMultipartFile image = new MockMultipartFile(
        "image",
        "cover.png",
        MediaType.IMAGE_PNG_VALUE,
        TestFixtures.validPng()
);

MockPart metadata = new MockPart(
        "metadata",
        metadataJson.getBytes(StandardCharsets.UTF_8)
);
metadata.getHeaders().setContentType(MediaType.APPLICATION_JSON);
```

Negative tests can send a file with an unsupported Content-Type:

```java
MockMultipartFile wrongType = new MockMultipartFile(
        "image",
        "cover.txt",
        MediaType.TEXT_PLAIN_VALUE,
        "not an image".getBytes(StandardCharsets.UTF_8)
);
```

If the endpoint only accepts PNG/JPEG, tests should confirm the server rejects it per contract, such as status `415` or `400` depending on how the application maps errors.

Content-Type is a client-declared value. If `image/png` is sent with text bytes, checking the header alone is insufficient. For file uploads, inspect the actual content with a file signature detector or appropriate parser if product requirements demand it.

## 10. Combining MockMvc with Spring REST Docs

MockMvc verifies HTTP behavior; Spring REST Docs uses the tested request itself to generate snippets. You can attach documentation to the passing test:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

mockMvc.perform(multipart("/api/products/{productId}/assets", 42)
        .file(image)
        .part(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isCreated())
    .andDo(document("products-upload-asset",
        requestParts(
            partWithName("image")
                .description("Product image; PNG or JPEG"),
            partWithName("metadata")
                .description("JSON metadata of the image")
        ),
        requestPartBody("metadata"),
        requestPartFields("metadata",
            fieldWithPath("title")
                .description("Image title"),
            fieldWithPath("description")
                .description("Image description")
                .optional(),
            fieldWithPath("displayOrder")
                .description("Image display order")
                .optional()
        )
    ));
```

Three APIs cover three levels of information:

| API | Snippet Content |
| --- | --- |
| `requestParts(...)` | Names and descriptions of parts |
| `requestPartBody("metadata")` | Sample JSON body of the metadata part |
| `requestPartFields("metadata", ...)` | Fields inside the JSON part |

Descriptors inside `requestPartFields(...)` use paths relative to the JSON part; for example `title`, not `metadata.title`.

If there is an optional part, declare `.optional()` on the descriptor when the sample request omits that part. If there is a technical field you do not want displayed, use `.ignored()` per contract. `relaxedRequestParts(...)` should only be used when the operation intentionally allows undocumented parts.

## 11. Separating Behavior Tests and Documentation Tests

A single test can both assert status/response and generate snippets. Still, keep their goals distinct:

- **Behavior tests:** verify the endpoint accepts/rejects files, metadata, MIME types, and sizes.
- **Documentation tests:** use a representative request to generate `request-parts.adoc`, body, and field snippets.
- **Negative tests:** verify responses when required parts are missing, JSON is invalid, or files are invalid.

It is not necessary to generate snippets for every error case. API docs generally need a representative successful request and can add error response snippets if the error contract needs to be published.

A passing documentation test does not prove the endpoint handles all invalid cases; a passing validation test does not guarantee snippets document every part.

## 12. Limitations and Caveats of MockMvc

MockMvc runs requests through the mock Spring MVC infrastructure. It is useful for testing mapping, binding, validation, controller advice, and Spring REST Docs integration, but it is not an HTTP client calling a real servlet container over a socket.

Therefore:

- MockMvc does not verify reverse proxies, TLS termination, or gateway configuration.
- Mock request multipart parsing does not replace testing upload limits on a real container.
- It does not verify network behavior when streaming large files or when clients disconnect.
- Integration tests running the application against a real server may be needed to test multipart parsing, max file size, max request size, and infrastructure configuration.

Use MockMvc for fast feedback at the MVC layer; add integration tests against a real server when upload is a critical feature and container limits affect the contract.

## 13. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Controller does not receive file | Builder part name differs from `@RequestPart` | Synchronize part names |
| Metadata fails to deserialize into DTO | Missing `application/json` Content-Type | Set header on `MockPart` |
| Using `.file()` for JSON and forgetting filename/content type | Builder creates a file part differently than intended | Use `MockPart` or set all `MockMultipartFile` params |
| Absent test accidentally sends empty file | Request builder still calls `.file(...)` | Do not add the part to the builder |
| Zero-byte file passes | Missing `isEmpty()` validation or content check | Add validation rule and test |
| Optional part causes binding error | Controller still has `required = true` | Use `@RequestPart(required = false)` if contract permits |
| REST Docs reports missing part | Required descriptor was omitted by fixture | Add the part or mark `.optional()` |
| REST Docs reports undocumented part | New part exists but strict descriptor not updated | Add descriptor, ignore, or relax per contract |
| Wrong Content-Type still passes | Endpoint lacks media type check | Add validation and negative test |
| Tests pass but large real-world files fail | MockMvc does not replace container/network tests | Add integration test with real server |
| Snippet missing metadata fields | Only `requestParts(...)` was called | Add `requestPartFields(...)` |
| Asciidoctor reports missing include | Test did not generate snippet or operation name is wrong | Check operation ID and task dependencies |

## 14. Asciidoctor and Build/CI

The document source can include snippets generated by tests:

```adoc
= Product Asset API
:toc: left

== Product Image Upload

=== HTTP Request
include::{snippets}/products-upload-asset/http-request.adoc[]

=== Parts
include::{snippets}/products-upload-asset/request-parts.adoc[]

=== JSON Metadata
include::{snippets}/products-upload-asset/request-part-metadata-body.adoc[]

=== Metadata Fields
include::{snippets}/products-upload-asset/request-part-metadata-fields.adoc[]
```

With Gradle and the Asciidoctor plugin configured, the documentation task must depend on the snippet-generating tests:

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
MockMvc multipart tests
        |
        +--> Test binding and response
        |
        +--> Test validation / negative cases
        |
        +--> Spring REST Docs generates snippets
        |
        v
Asciidoctor / Markdown conversion step
        |
        v
Verify and publish documentation
```

When changing part names, Content-Types, or metadata DTOs, update controller, fixtures, descriptors, and documentation together. Do not edit generated snippets manually to make the build green. Spring REST Docs generates AsciiDoc by default; Markdown requires a project-configured template or conversion step.

## 15. Practice Exercise

With the `POST /api/products/{productId}/assets` endpoint:

1. Build the `image` file part using `MockMultipartFile` and the `metadata` JSON part using `MockPart`.
2. Attach `image/png` to the file and `application/json` to metadata. Verify the controller binds successfully.
3. Assert status and response containing filename and metadata title.
4. Send metadata missing `title`; confirm Bean Validation rejects the request per the error contract.
5. Omit the `image` part completely; confirm how the server handles a missing required part.
6. Send a zero-byte file; compare with a request without the part.
7. Send MIME `text/plain` and non-image bytes; verify validation.
8. Add `requestParts`, `requestPartBody`, and `requestPartFields` to generate snippets.
9. Use a test omitting an optional part and add `.optional()` to its descriptor.
10. Run snippet-generating tests before Asciidoctor in CI; verify every include exists.

### Self-Assessment Questions

- When should you use `MockMultipartFile` versus `MockPart`?
- How does a part name differ from a filename?
- Why does a JSON part need `Content-Type: application/json`?
- What kind of request does `multipart(...)` create in MockMvc?
- How does an absent part differ from a zero-byte file?
- Does `.optional()` in REST Docs make the controller accept a missing part?
- Which levels do `requestParts`, `requestPartBody`, and `requestPartFields` describe?
- Which aspects of uploads over a real servlet container can MockMvc not verify?

**Remember:** Use `multipart(...)` to build the request, `MockMultipartFile` to simulate files, and `MockPart` to create general parts such as JSON. Verify binding, responses, and validation with MockMvc; then use that same passing request to generate `requestParts`, `requestPartBody`, and `requestPartFields`. Keep absent parts distinct from empty parts, and add real-server tests when you need to verify container limits or network file transfers.

## References

- [Spring Framework — MockMvc multipart requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html): building HTTP requests with MockMvc and the multipart builder.
- [Spring Framework — `MockMultipartFile` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/mock/web/MockMultipartFile.html): creating file parts in tests.
- [Spring Framework — `MockPart` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/mock/web/MockPart.html): creating general multipart parts and setting headers.
- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): `requestParts` and multipart documentation.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): body and fields of JSON parts.
