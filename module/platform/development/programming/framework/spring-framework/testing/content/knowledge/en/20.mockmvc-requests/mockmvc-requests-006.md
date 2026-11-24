# Multipart Requests with Files and Data Parts

Many APIs need to receive a file together with descriptive metadata in the same HTTP request. For example, a user uploads a document accompanied by a title, document type, or classification details. The protocol commonly used for this scenario is `multipart/form-data`: the request is split into multiple parts, each with its own name, headers, and content.

Spring MVC supports binding multipart requests into `MultipartFile`, `Part`, form parameters, and Java objects. Spring Test provides `MockMvcRequestBuilders.multipart(...)` to build simulated multipart requests. We can attach files using `MockMultipartFile`, add data parts using `MockPart`, and then send the request through `MockMvc` to verify that the controller processes each part as expected.

## 1. Structure of a Multipart Request

A `multipart/form-data` request contains multiple parts separated by a boundary. Each part has its own headers, typically including `Content-Disposition` with a field name and possibly a filename; a data part may also declare a `Content-Type`.

Conceptual structure example:

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----Boundary123

------Boundary123
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Q4 report","category":"FINANCE"}
------Boundary123
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

<binary file content>
------Boundary123--
```

The request has two parts:

- `metadata` contains JSON describing the document. Spring can convert this part into a DTO using an `HttpMessageConverter`.
- `file` contains the file content, original filename, and content type. Spring can bind it into a `MultipartFile`.

The part name is part of the HTTP contract. If the controller requires `@RequestPart("file")`, the part name in the test must be `file`. A wrong field name usually causes Spring to miss the required parameter and return a request error.

## 2. Creating a Multipart Request with `MockMvc`

Spring MVC Test provides the `multipart(...)` request builder. This builder creates a simulated multipart request to send via `MockMvc`.

Files are created using `MockMultipartFile`:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.mock.web.MockMultipartFile;
import org.springframework.http.MediaType;

MockMultipartFile file = new MockMultipartFile(
        "file",
        "report.pdf",
        MediaType.APPLICATION_PDF_VALUE,
        "PDF test content".getBytes(StandardCharsets.UTF_8)
);
```

The arguments in order are:

1. `name`: the part name the controller will receive, e.g., `file`.
2. `originalFilename`: the filename sent by the client, e.g., `report.pdf`.
3. `contentType`: the content type of the file, e.g., `application/pdf`.
4. `content`: the byte array containing the file content.

You can use the constructor accepting an `InputStream` when test data is read from a stream source. For small tests, a byte array keeps input contents clear and easy to control.

Then attach the file to the request:

```java
mockMvc.perform(multipart("/api/documents")
                .file(file)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk());
```

`multipart(...)` creates a POST multipart request by default. `file(...)` attaches a file part to the request. `MockMvc` passes the request through Spring MVC for the controller to handle without opening an HTTP server.

## 3. Controller Receiving Files with `MultipartFile`

`MultipartFile` is Spring's abstraction for working with the contents of a file parsed from a multipart request. Some commonly used methods:

| Method | Meaning |
| --- | --- |
| `getName()` | The field/part name in the form, such as `file`. |
| `getOriginalFilename()` | The original filename uploaded by the client. |
| `getContentType()` | The content type declared for the file. |
| `isEmpty()` | Indicates whether no file was sent or the file content is empty. |
| `getSize()` | Content size in bytes. |
| `getBytes()` | Reads the entire content into a byte array. |
| `getInputStream()` | Reads the content via a stream. |
| `transferTo(...)` | Writes the content to a storage destination. |

Example of a controller accepting a file and a text description field:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
class DocumentController {

    @PostMapping(
            path = "/api/documents",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    UploadResponse upload(
            @RequestParam("description") String description,
            @RequestParam("file") MultipartFile file
    ) {
        return new UploadResponse(
                description,
                file.getOriginalFilename(),
                file.getContentType(),
                file.getSize()
        );
    }
}

record UploadResponse(
        String description,
        String filename,
        String contentType,
        long size
) {
}
```

`consumes = MediaType.MULTIPART_FORM_DATA_VALUE` restricts the endpoint to requests with the `multipart/form-data` content type. `@RequestParam` binds the `description` form field and the `file` part into their respective parameters.

## 4. Sending a File with Text Form Fields

When descriptive data consists only of simple text fields, `.param(...)` can be used on the multipart request builder:

```java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void shouldUploadFileWithDescription() throws Exception {
    MockMultipartFile file = new MockMultipartFile(
            "file",
            "report.pdf",
            MediaType.APPLICATION_PDF_VALUE,
            "PDF test content".getBytes(StandardCharsets.UTF_8)
    );

    mockMvc.perform(multipart("/api/documents")
                    .file(file)
                    .param("description", "Quarterly report")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.description").value("Quarterly report"))
            .andExpect(jsonPath("$.filename").value("report.pdf"))
            .andExpect(jsonPath("$.contentType").value("application/pdf"))
            .andExpect(jsonPath("$.size").value(16));
}
```

`param("description", ...)` sets a parameter value in the simulated request. This is a concise way to test a controller receiving form fields via `@RequestParam`. In a real multipart form, text fields are also represented as form parts and placed into the request parameter map by servlet multipart processing.

If you want to test a data part as an actual `Part`, especially when the part has its own headers or content type, create a `MockPart` and attach it with `.part(...)`.

## 5. Sending JSON Metadata Alongside a File Using `MockPart`

An API often receives structured metadata such as a title, category, or access control info. When the metadata part has content type `application/json`, `@RequestPart` can be used so Spring converts the JSON into a DTO.

Metadata DTO:

```java
public record DocumentMetadata(String title, String category) {
}
```

Controller:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
class DocumentController {

    @PostMapping(
            path = "/api/documents",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    UploadResponse upload(
            @RequestPart("metadata") DocumentMetadata metadata,
            @RequestPart("file") MultipartFile file
    ) {
        return new UploadResponse(
                metadata.title(),
                metadata.category(),
                file.getOriginalFilename(),
                file.getContentType(),
                file.getSize()
        );
    }
}

record UploadResponse(
        String title,
        String category,
        String filename,
        String contentType,
        long size
) {
}
```

Creating the JSON part with `MockPart`:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.mock.web.MockPart;

MockPart metadataPart = new MockPart(
        "metadata",
        "{\"title\":\"Q4 report\",\"category\":\"FINANCE\"}"
                .getBytes(StandardCharsets.UTF_8)
);
metadataPart.getHeaders().setContentType(MediaType.APPLICATION_JSON);
```

The name `metadata` matches `@RequestPart("metadata")`. The header `Content-Type: application/json` tells Spring that this part must be read using the JSON message converter. If the content type is missing or misdeclared, Spring may fail to pick an appropriate converter to deserialize the part into `DocumentMetadata`.

Combining metadata and file in the same request:

```java
MockMultipartFile filePart = new MockMultipartFile(
        "file",
        "quarterly-report.pdf",
        MediaType.APPLICATION_PDF_VALUE,
        "sample pdf bytes".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/documents")
                .file(filePart)
                .part(metadataPart)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.title").value("Q4 report"))
        .andExpect(jsonPath("$.category").value("FINANCE"))
        .andExpect(jsonPath("$.filename").value("quarterly-report.pdf"));
```

In this example:

- `MockMultipartFile` represents the file part with filename, content type, and byte content.
- `MockPart` represents the metadata part with its own `Content-Type` header.
- `multipart(...).file(...).part(...)` builds a request containing both parts.
- `@RequestPart` asks Spring to resolve each part by parameter type. For `MultipartFile`, Spring provides the file abstraction; for the metadata DTO, Spring uses `HttpMessageConverter` based on the part's content type.

This test verifies both multipart binding and conversion of the JSON part into an object. For the JSON part to work, the test needs a matching JSON converter, typically Jackson when using Spring Boot's web starter.

## 6. Distinguishing `@RequestParam`, `@RequestPart`, and `Part`

These annotations can coexist on a multipart endpoint, yet their binding purposes are not identical.

| Way to receive data | Common usage | Key behavior |
| --- | --- | --- |
| `@RequestParam("description") String description` | Text form fields or request parameters. | Retrieves parameter value by name from the request parameter map. |
| `@RequestParam("file") MultipartFile file` | File upload by field name. | Spring resolves the file part into a `MultipartFile`. |
| `@RequestPart("metadata") Metadata metadata` | JSON/XML or data with a content type requiring a message converter. | Reads the part content and converts it according to its content type. |
| `@RequestPart("file") MultipartFile file` | File upload in a multi-part endpoint. | Resolves the file part into a `MultipartFile`. |
| `Part` or `@RequestPart("file") Part file` | When needing to work close to the Servlet Part API. | Accesses part name, headers, size, stream, and part operations. |

With `@RequestParam`, Spring mainly treats the value as a request parameter. With `@RequestPart`, Spring inspects the part's content and uses `HttpMessageConverter` when the parameter type requires conversion, similar to how `@RequestBody` works. Therefore, `@RequestPart` is especially helpful when metadata is JSON alongside a binary file.

If the controller accepts a form object via `@ModelAttribute`, Spring can bind form fields and `MultipartFile` into object properties. This is convenient for forms with many simple fields. When structured JSON metadata and an independent file are needed, `@RequestPart` makes the boundary of each part explicit.

## 7. Testing Multiple Files in the Same Request

A form can upload multiple files under the same field name, such as `attachments`. The controller can accept a `List<MultipartFile>`:

```java
@PostMapping(
        path = "/api/documents/attachments",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
UploadBatchResponse uploadMany(
        @RequestParam("attachments") List<MultipartFile> attachments
) {
    List<String> filenames = attachments.stream()
            .map(MultipartFile::getOriginalFilename)
            .toList();
    return new UploadBatchResponse(filenames);
}

record UploadBatchResponse(List<String> filenames) {
}
```

In the test, call `.file(...)` multiple times with the same part name:

```java
MockMultipartFile first = new MockMultipartFile(
        "attachments", "one.txt", MediaType.TEXT_PLAIN_VALUE,
        "first".getBytes(StandardCharsets.UTF_8)
);
MockMultipartFile second = new MockMultipartFile(
        "attachments", "two.txt", MediaType.TEXT_PLAIN_VALUE,
        "second".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/documents/attachments")
                .file(first)
                .file(second)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.filenames[0]").value("one.txt"))
        .andExpect(jsonPath("$.filenames[1]").value("two.txt"));
```

The part name must match the name in `@RequestParam` or `@RequestPart`. If the controller accepts `List<MultipartFile>` but the test sends two different part names, binding may not assemble the list as expected.

## 8. Testing Missing Files, Empty Files, and Invalid Metadata

Multipart testing should not cover only the happy path. Upload APIs usually enforce rules for required parts, minimum size, format, or metadata.

### Empty Files

`MockMultipartFile` can be constructed with an empty byte array:

```java
MockMultipartFile emptyFile = new MockMultipartFile(
        "file",
        "empty.txt",
        MediaType.TEXT_PLAIN_VALUE,
        new byte[0]
);
```

The controller can check `file.isEmpty()` and return an appropriate error. The test sends an empty file and verifies the status and error response per the API contract. This tests application logic that handles empty content.

### Missing Required Parts

If the controller declares `@RequestPart("file") MultipartFile file` with the default `required = true`, a request lacking the `file` part will not satisfy the required parameter. You can test this by sending a request with only metadata or a multipart request without the file.

```java
mockMvc.perform(multipart("/api/documents")
                .part(metadataPart))
        .andExpect(status().isBadRequest());
```

The exact status may vary if the application has a `@ControllerAdvice` translating binding errors into a custom response. Tests should assert the error contract the application actually publishes.

### Invalid Metadata

If the DTO uses Bean Validation:

```java
public record DocumentMetadata(
        @NotBlank String title,
        @NotBlank String category
) {
}
```

The controller can declare `@Valid @RequestPart("metadata") DocumentMetadata metadata`. The test sends metadata missing `title` or with an empty `title`, then verifies the validation error. For validation to run, the test needs a Bean Validation provider and corresponding validator configuration. When using standalone MockMvc, register an appropriate validator on the builder.

## 9. Verifying File Contents and Service Interactions

An assertion checking only `originalFilename` or `size` does not prove the controller forwarded the exact byte content down to the business layer. If the controller calls a service to store the file, Mockito `ArgumentCaptor` or `verify` can be used to inspect the passed data.

For example, suppose the service has the method:

```java
public interface DocumentStorageService {
    void store(String title, MultipartFile file);
}
```

After sending the request, the test can capture the file argument and compare its content:

```java
ArgumentCaptor<MultipartFile> fileCaptor =
        ArgumentCaptor.forClass(MultipartFile.class);

verify(documentStorageService).store(
        eq("Q4 report"),
        fileCaptor.capture()
);

assertThat(fileCaptor.getValue().getOriginalFilename())
        .isEqualTo("quarterly-report.pdf");
assertThat(fileCaptor.getValue().getBytes())
        .containsExactly("sample pdf bytes".getBytes(StandardCharsets.UTF_8));
```

The snippet above requires static imports for `eq` and AssertJ's `assertThat`. If the service reads a stream or invokes `transferTo`, the test can verify that behavior using a fake storage service or an appropriate mock. The goal is to check that multipart data passes intact across the controller/service boundary.

## 10. Limitations of Multipart Requests in MockMvc

`MockMvcRequestBuilders.multipart(...)` creates a `MockMultipartHttpServletRequest` with files/parts already attached. This request helps verify how Spring MVC binds and processes multipart data once it is represented as parts.

It does not send raw HTTP multipart bytes over a socket and does not require a servlet container to parse an actual boundary. Accordingly, MockMvc tests are well-suited for checking:

- Whether the controller receives the right part names and parameter types.
- Whether JSON metadata is converted by a message converter.
- Whether the file has the expected name, content type, size, and content in the simulated request.
- How application logic reacts to empty files, missing parts, or invalid metadata.

These tests do not directly verify:

- Whether the servlet container parses multipart boundaries and headers accurately from a raw HTTP body.
- How container `max-file-size` or `max-request-size` limits are enforced.
- How temporary files are written to disk, cleaned up, or lifecycle-managed.
- Whether reverse proxies, gateways, or the network transport large files properly.

When container-dependent behavior needs verification, add integration tests that start a real server and send HTTP multipart requests via clients such as `TestRestTemplate`, an appropriate `WebTestClient`, or another HTTP client. In Spring Boot, `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` can run the server on a random port. Then the multipart request travels through the application's real HTTP stack.

## 11. Security and File Validation Notes

Filename, extension, and content type sent by the client are all untrusted input data. Do not treat `getOriginalFilename()` or `getContentType()` as reliable proof that the file content is safe. Applications should validate per business requirements, enforce size limits, inspect content when necessary, and generate safe storage names on the server.

In controller tests, you can create a mock file with a name like `../../outside.txt` or a content type that disagrees with the content to test filename and file-type handling rules. These checks should focus on application behavior such as rejecting or normalizing data. Testing the parser, upload limits, and real storage requires integration tests tailored to the infrastructure.

If the endpoint is protected by Spring Security, POST requests may require a CSRF token when the filter chain is active in `MockMvc`. With the Spring Security Test dependency, `.with(csrf())` can be added to the request builder. If the filter chain is not integrated in a standalone test, the CSRF filter may not run; be clear about whether a test covers only the controller or also the security layer.

## 12. Common Mistakes When Writing Multipart Tests

**Part name does not match the controller parameter.**

If the controller uses `@RequestPart("metadata")`, the test must add a part named `metadata`. For files, the name passed to `MockMultipartFile` must match the binding name.

**Using `.file(...)` for JSON data without declaring a content type.**

`MockMultipartFile` represents a file part. If metadata is JSON that needs to be converted into a DTO, use `MockPart` and set `Content-Type: application/json`, then bind with `@RequestPart`.

**Using `.param(...)` and expecting a part to have its own headers.**

`.param(...)` adds a request parameter to the simulated request; it does not create a `Part` with its own headers. When you need to check content type or headers of individual parts, use `.part(...)` with `MockPart`.

**Forgetting the JSON message converter.**

`@RequestPart` with a DTO requires a corresponding converter. If a standalone setup lacks the Jackson converter, Spring cannot convert the JSON part into an object. Add the converter or use a context with proper MVC configuration.

**Checking the file only by name.**

A filename does not prove the byte content is right. When the controller forwards the file to a service, verify byte content or stream reading behavior if that is a requirement to prove.

**Assuming MockMvc tests server upload limits.**

Mock multipart requests do not run through the servlet container's multipart parser. Use tests against a real server when verifying size limits, boundary handling, temp file storage, or infrastructure behavior.

## 13. Multipart Testing Workflow with MockMvc

A multipart test can follow this sequence:

1. Identify the endpoint contract: part names, data types, content types, required parts, and expected response.
2. Create a `MockMultipartFile` for each file, specifying the right name, original filename, content type, and byte content.
3. Create a `MockPart` for data with custom headers or content types, such as JSON metadata.
4. Use `multipart("/path")` to construct the request, then attach `.file(...)`, `.part(...)`, or `.param(...)` as needed.
5. Perform the request via `mockMvc.perform(...)`.
6. Verify status, response content type, body, and service interactions.
7. Add negative cases such as missing parts, empty files, invalid metadata, or multiple files.
8. Use a real server if the goal covers multipart parsing and servlet container upload limits.

## Conclusion

To test endpoints that accept files and multipart data, use `MockMvcRequestBuilders.multipart(...)` combined with `MockMultipartFile` for files and `MockPart` for parts with custom headers or content types. `@RequestParam` suits form fields and standard file binding; `@RequestPart` suits converting part contents such as JSON into a DTO.

MockMvc helps verify binding, message conversion, and controller logic inside a simulated servlet environment. When you need to verify raw multipart parsing, size limits, temporary files, or servlet container behavior, an integration test sending requests through a real server is necessary.
