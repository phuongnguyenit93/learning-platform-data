# Testing Multipart Requests and Error Response Cases

## 1. Hands-On Project Goals

In this lab, you will build a small document-upload workflow to practice **Spring Cloud Contract (SCC)** from producer to consumer. The producer exposes an HTTP API accepting `multipart/form-data` requests; the consumer sends a file and metadata; SCC specifies the interaction using Groovy contracts, generates producer verification tests and WireMock stubs; and Stub Runner supplies the stub for consumer compatibility tests.

The project exposes one endpoint:

~~~http
POST /api/documents
Content-Type: multipart/form-data
Accept: application/json
~~~

The request has two parts:

- `file`: the document file content, including a filename and media type.
- `description`: a short description for the document.

When valid, the producer returns HTTP 201 with document metadata. When invalid, the producer returns an error with a consistent schema and an appropriate status code.

You will verify five main scenarios:

| Scenario | Input | Expected result |
|---|---|---|
| Successful upload | `.txt` file, `text/plain` media type, valid description | **201 Created** |
| Missing description | File part only | **400 Bad Request** |
| File too large | Content exceeds business limit | **413 Content Too Large** |
| Unsupported media type | File part is `application/octet-stream` | **415 Unsupported Media Type** |
| Invalid filename | File has a disallowed extension | **422 Unprocessable Content** |

The byte and filename limits in this lab are learning fixtures. A real system must choose policies based on business rules, security, and storage infrastructure.

### Target Outcomes

Upon completion, you will be able to:

1. Specify a multipart request with a file part and form field in the SCC Groovy DSL.
2. Generate producer tests and verify they invoke a real Spring MVC application.
3. Assert status codes, error codes, and response bodies across multiple failure cases.
4. Package a stubs JAR and use Stub Runner in consumer tests.
5. Inspect raw multipart requests, boundaries, filenames, part Content-Types, and bodies.
6. Distinguish business errors from WireMock unmatched-request errors.
7. Prove that bugs like renaming a part or changing data types cause tests to fail.
8. Integrate producer verification and consumer compatibility into CI.

## 2. Architecture and Test Flow

The project consists of two applications:

- **document-service (producer):** receives uploads, validates inputs, and returns document metadata or an error.
- **case-service (consumer):** calls document-service over HTTP to attach documents to a case.

The SCC contracts belong to the producer. Generated producer tests verify the real controller and service; generated stubs emulate that same interface for the consumer.

~~~mermaid
flowchart LR
    C["case-service<br/>MultipartDocumentClient"] -->|"multipart/form-data"| W["Stub Runner / WireMock"]
    W -->|"candidate response"| C
    D["document-service<br/>Controller + Service"] --> P["Producer Contract Verifier"]
    K["Groovy contracts"] --> P
    K --> S["Generated WireMock stubs"]
    S --> W
    P --> G["Producer test report"]
    C --> R["Consumer compatibility report"]
~~~

The two test suites answer different questions:

| Test suite | Real components | Simulated components | Evidence |
|---|---|---|---|
| Producer contract verification | Controller, service, validation, exception handler | SCC test adapter/environment | Producer code satisfies the contract |
| Consumer compatibility | Consumer client, serializer, error handling | WireMock stubs from producer candidate | Consumer understands request/response contract |
| End-to-end (optional) | Both services and network | Possibly no stubs | Integration in a test environment |

**Never use a consumer stub test to claim the producer code is correct.** WireMock does not execute `document-service`'s controller.

## 3. Recommended Project Structure

One way to organize the repository:

~~~text
contract-multipart-lab/
├── pom.xml
├── document-service/
│   ├── pom.xml
│   └── src/
│       ├── main/java/com/example/document/
│       │   ├── DocumentApplication.java
│       │   ├── api/DocumentController.java
│       │   ├── api/ApiExceptionHandler.java
│       │   ├── api/ApiError.java
│       │   ├── api/DocumentResponse.java
│       │   └── service/DocumentService.java
│       ├── main/resources/application.yml
│       └── test/
│           ├── java/com/example/document/ContractTestBase.java
│           └── resources/contracts/document/
│               ├── upload-success.groovy
│               ├── upload-missing-description.groovy
│               ├── upload-too-large.groovy
│               ├── upload-unsupported-media-type.groovy
│               └── upload-invalid-filename.groovy
└── case-service/
    ├── pom.xml
    └── src/
        ├── main/java/com/example/caseapp/
        │   ├── CaseApplication.java
        │   └── client/MultipartDocumentClient.java
        └── test/java/com/example/caseapp/
            └── MultipartDocumentCompatibilityTest.java
~~~

Package and path names are examples. You can use a Maven multi-module build or two separate repositories; what matters is that **the producer publishes candidate stubs** and the consumer test resolves the exact artifact coordinates.

## 4. Finalizing the API Contract Before Writing Code

### Multipart Request

| Component | Part/header name | Rule |
|---|---|---|
| File | `file` | Required, filename ends with `.txt` |
| File content type | Part header `Content-Type` | `text/plain` |
| File content | File bytes | Non-empty, max 10 bytes in the lab |
| Description | Part `description` | Required, non-blank |
| Request Content-Type | `multipart/form-data; boundary=...` | Boundary generated by the HTTP client |
| Accept | `application/json` | Consumer requests JSON |

**Do not hardcode the multipart boundary** in the contract. Clients generate a fresh boundary on each request; matchers should verify multipart semantics and required parts rather than matching the entire raw body against a fixed boundary string.

### Success Response

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "documentId": "8c5e9d0a-1a2b-4f3c-8d9e-123456789abc",
  "filename": "note.txt",
  "contentType": "text/plain",
  "size": 5,
  "status": "UPLOADED"
}
~~~

`documentId` is a dynamic UUID; `size` depends on the actual byte count. These values need format/type matchers, while filename, media type, and status in the fixture scenario can be checked strictly.

### Error Response

Errors share a common schema:

~~~json
{
  "code": "UNSUPPORTED_DOCUMENT_MEDIA_TYPE",
  "message": "Only text/plain documents are supported"
}
~~~

Each error code must pair with the right HTTP status. The consumer should distinguish validation errors, media type errors, size errors, and transport failures.

## 5. Preparing Dependencies and Versions

SCC depends on compatibility across **Spring Boot, the Spring Cloud Release Train, and Spring Cloud Contract**. Use the Spring Cloud BOM aligned with your chosen Spring Boot version; do not copy a random plugin version from another project.

The producer needs dependencies by role:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-contract-verifier</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

The Maven plugin must be configured to:

- Discover the contract directory in the right module;
- Generate producer tests;
- Use the corresponding base class;
- Attach the stubs artifact with the classifier per SCC convention;
- Run verification during the appropriate lifecycle phase.

Conceptual configuration example:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <extensions>true</extensions>
    <configuration>
        <baseClassForTests>
            com.example.document.ContractTestBase
        </baseClassForTests>
        <testMode>MockMvc</testMode>
    </configuration>
</plugin>
~~~

This is a **configuration skeleton**. Plugin version, test mode spelling, generated source paths, and lifecycle bindings must be verified against the reference docs for your SCC release.

The consumer needs `spring-cloud-starter-contract-stub-runner` in test scope along with its HTTP client dependency. Do not include Stub Runner in production runtime dependencies just to run compatibility tests.

## 6. Configuring Upload Limits for the Lab

Create `document-service/src/main/resources/application.yml`:

~~~yaml
spring:
  servlet:
    multipart:
      enabled: true
      max-file-size: 1MB
      max-request-size: 2MB

documents:
  max-upload-bytes: 10
~~~

There are two separate limits here:

- The servlet multipart parser bounds the maximum file/request size accepted at the framework layer.
- `documents.max-upload-bytes` is the **business limit** enforced by `DocumentService` after the multipart parser reads the file.

In this lab, a 10-byte business limit makes an 11-byte fixture small and easy to test for 413. Never apply a 10-byte limit to a real product. When testing limits at the servlet/container layer, configure and handle the corresponding exception explicitly because the controller may **never be invoked**.

## 7. Creating Response and Error DTOs

Success response:

~~~java
package com.example.document.api;

public record DocumentResponse(
    String documentId,
    String filename,
    String contentType,
    long size,
    String status
) {}
~~~

Error response:

~~~java
package com.example.document.api;

public record ApiError(
    String code,
    String message
) {}
~~~

Keeping the error schema small and stable makes consumer mapping clear. Never return stack traces, filesystem paths, or file contents in error responses.

## 8. Implementing DocumentService

Example service that validates the file and returns metadata. Actual persistence is simplified so the lab focuses on the HTTP contract; production projects should place storage behind a dedicated interface.

~~~java
package com.example.document.service;

import com.example.document.api.DocumentResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.util.Locale;
import java.util.UUID;

@Service
public class DocumentService {

    private final long maxUploadBytes;

    public DocumentService(
            @Value("${documents.max-upload-bytes:10}")
            long maxUploadBytes) {
        this.maxUploadBytes = maxUploadBytes;
    }

    public DocumentResponse upload(
            MultipartFile file,
            String description) {

        if (file == null || file.isEmpty()) {
            throw new InvalidDocumentException(
                "EMPTY_FILE", "File must not be empty");
        }

        if (description == null || description.isBlank()) {
            throw new InvalidDocumentException(
                "INVALID_DESCRIPTION",
                "Description must not be blank");
        }

        String mediaType = file.getContentType();
        if (mediaType == null
                || !mediaType.equalsIgnoreCase("text/plain")) {
            throw new UnsupportedDocumentMediaTypeException();
        }

        if (file.getSize() > maxUploadBytes) {
            throw new DocumentTooLargeException();
        }

        String filename = file.getOriginalFilename();
        if (filename == null
                || !filename.toLowerCase(Locale.ROOT).endsWith(".txt")) {
            throw new InvalidDocumentException(
                "INVALID_FILENAME",
                "Only .txt filenames are accepted");
        }

        return new DocumentResponse(
            UUID.randomUUID().toString(),
            filename,
            mediaType,
            file.getSize(),
            "UPLOADED"
        );
    }
}
~~~

You also need the exception classes `InvalidDocumentException`, `UnsupportedDocumentMediaTypeException`, and `DocumentTooLargeException` (which can live in the service package). Example constructor:

~~~java
public class DocumentTooLargeException extends RuntimeException {
    public DocumentTooLargeException() {
        super("Document exceeds the configured size limit");
    }
}
~~~

For `InvalidDocumentException`, retain `code` and `message` so the exception handler can emit scenario-specific error codes. Never use the uploaded filename directly to build a storage path; if you add persistence, address path traversal, filename collisions, and malware scanning.

## 9. Implementing the Multipart Controller

~~~java
package com.example.document.api;

import com.example.document.service.DocumentService;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService documentService;

    public DocumentController(DocumentService documentService) {
        this.documentService = documentService;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<DocumentResponse> upload(
            @RequestPart("file") MultipartFile file,
            @RequestPart("description") String description) {

        DocumentResponse response =
            documentService.upload(file, description);

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(response);
    }
}
~~~

`@RequestPart` enforces exact part names on the request. If a consumer sends `document` instead of `file`, or omits `description`, Spring MVC rejects the request before entering the service. That behavior should be standardized via an exception handler.

## 10. Standardizing Error Handling

Create `ApiExceptionHandler`:

~~~java
package com.example.document.api;

import com.example.document.service.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MissingServletRequestPartException;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MissingServletRequestPartException.class)
    ResponseEntity<ApiError> missingPart(
            MissingServletRequestPartException ex) {
        return ResponseEntity.badRequest().body(
            new ApiError(
                "MISSING_PART",
                "A required multipart part is missing"
            )
        );
    }

    @ExceptionHandler(DocumentTooLargeException.class)
    ResponseEntity<ApiError> tooLarge(
            DocumentTooLargeException ex) {
        return ResponseEntity.status(413).body(
            new ApiError(
                "DOCUMENT_TOO_LARGE",
                "Document exceeds the upload size limit"
            )
        );
    }

    @ExceptionHandler(UnsupportedDocumentMediaTypeException.class)
    ResponseEntity<ApiError> unsupportedMediaType(
            UnsupportedDocumentMediaTypeException ex) {
        return ResponseEntity.status(415).body(
            new ApiError(
                "UNSUPPORTED_DOCUMENT_MEDIA_TYPE",
                "Only text/plain documents are supported"
            )
        );
    }

    @ExceptionHandler(InvalidDocumentException.class)
    ResponseEntity<ApiError> invalidDocument(
            InvalidDocumentException ex) {
        return ResponseEntity.status(422).body(
            new ApiError(ex.getCode(), ex.getMessage())
        );
    }
}
~~~

This example assumes `InvalidDocumentException` exposes `getCode()` and the exception classes live in the imported package. When completing the project, add the corresponding constructors/accessors and verify compilation.

**Distinguish 400 and 422 per API policy:** in this lab, 400 is for a missing required multipart part; 422 is for parsed data that fails business validation. A system may pick a different convention, but it must be consistent across contracts, producer, and consumer.

## 11. Completing the Exception Classes

Create `InvalidDocumentException`:

~~~java
package com.example.document.service;

public class InvalidDocumentException extends RuntimeException {

    private final String code;

    public InvalidDocumentException(String code, String message) {
        super(message);
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
~~~

`UnsupportedDocumentMediaTypeException`:

~~~java
package com.example.document.service;

public class UnsupportedDocumentMediaTypeException
        extends RuntimeException {
    public UnsupportedDocumentMediaTypeException() {
        super("Only text/plain documents are supported");
    }
}
~~~

`DocumentTooLargeException`:

~~~java
package com.example.document.service;

public class DocumentTooLargeException extends RuntimeException {
    public DocumentTooLargeException() {
        super("Document exceeds the configured size limit");
    }
}
~~~

Place these classes in the package imported by the controller advice. If the IDE cannot resolve them, verify the package declarations before altering exception mappings.

## 12. Base Class for Generated Producer Tests

Create `ContractTestBase`:

~~~java
package com.example.document;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class ContractTestBase {

    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void configureMockMvc() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

The goal is for generated tests to exercise the **Spring MVC context**, traversing the controller, validation, service, and exception advice. Never substitute a fake controller returning hardcoded contract bodies; doing so lets producer verification pass even when real code is broken.

Configure the plugin with the exact fully-qualified class name `com.example.document.ContractTestBase`. If your project uses WebFlux or a real HTTP port, select the corresponding test adapter and base class and verify against generated test sources.

## 13. Success Contract: Multipart File + Description

Create `upload-success.groovy` in the contract directory:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Successful text file upload'

    request {
        method POST()
        url '/api/documents'
        headers {
            header('Accept', 'application/json')
        }
        multipart(
            formParameter('description', 'Quarterly report'),
            named(
                'file',
                $(consumer(anyNonBlankString()), producer('hello'))
            ).fileName('note.txt').contentType('text/plain')
        )
    }

    response {
        status CREATED()
        headers {
            contentType(applicationJson())
        }
        body(
            documentId: '8c5e9d0a-1a2b-4f3c-8d9e-123456789abc',
            filename: 'note.txt',
            contentType: 'text/plain',
            size: 5,
            status: 'UPLOADED'
        )
        bodyMatchers {
            jsonPath('$.documentId',
                byRegex('[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'))
            jsonPath('$.size', byType())
            jsonPath('$.filename', byEquality())
            jsonPath('$.status', byEquality())
        }
    }
}
~~~

In this example:

- `formParameter` declares the `description` form field.
- `named` declares the `file` file part.
- `fileName` and `contentType` constrain the file part's metadata.
- `producer('hello')` provides the 5-byte sample content for the generated producer test/stub.
- `consumer(anyNonBlankString())` specifies that the stub accepts non-blank file content per the matcher.

**Note:** how SCC applies the consumer/producer sides of multipart matchers and builder APIs can vary by version. After generation, inspect the Java tests and WireMock mappings to verify requests are generated and matched properly; never assume reading the Groovy source alone is enough.

## 14. Contract 400: Missing Required Multipart Part

Create `upload-missing-description.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Reject upload when description is missing'

    request {
        method POST()
        url '/api/documents'
        headers {
            header('Accept', 'application/json')
        }
        multipart(
            named(
                'file',
                $(consumer(anyNonBlankString()), producer('hello'))
            ).fileName('note.txt').contentType('text/plain')
        )
    }

    response {
        status BAD_REQUEST()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'MISSING_PART',
            message: 'A required multipart part is missing'
        )
    }
}
~~~

The request includes only the `file` part, omitting `description`. Spring MVC rejects binding `@RequestPart("description")` before calling the service; `ApiExceptionHandler` normalizes the error to 400.

This scenario differs from an “empty description”: if the part is present with blank content, the controller is invoked and the service returns 422 per its logic. Keep the two cases separate if the API commits to distinct semantics.

## 15. Contract 413: File Exceeds Business Size Limit

Create `upload-too-large.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Reject file exceeding business upload limit'

    request {
        method POST()
        url '/api/documents'
        headers {
            header('Accept', 'application/json')
        }
        multipart(
            formParameter('description', 'Large sample'),
            named(
                'file',
                $(consumer(regex('(?s).{11,}')), producer('01234567890'))
            ).fileName('large.txt').contentType('text/plain')
        )
    }

    response {
        status 413
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'DOCUMENT_TOO_LARGE',
            message: 'Document exceeds the upload size limit'
        )
    }
}
~~~

The sample `01234567890` has 11 ASCII characters (11 bytes); the lab's business limit is 10 bytes. The consumer matcher constrains file content using a length pattern tailored for this scenario. Always inspect regex/multipart matchers in the generated mappings for your SCC version.

**Distinguish the two types of limits:**

- If `documents.max-upload-bytes` rejects the file after parsing, the controller/service returns 413 as shown.
- If `spring.servlet.multipart.max-file-size` or a proxy rejects it before the controller, the error may be `MaxUploadSizeExceededException` or a gateway error. A dedicated contract/integration setup is needed to verify status and body at that layer.

Do not lower the servlet multipart parser limit to 10 bytes while trying to test the 10-byte business check; the parser would intercept the request first and the service's 413 path would never execute.

## 16. Contract 415: File Part Has Unsupported Media Type

Create `upload-unsupported-media-type.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Reject file part with unsupported media type'

    request {
        method POST()
        url '/api/documents'
        headers {
            header('Accept', 'application/json')
        }
        multipart(
            formParameter('description', 'Binary attachment'),
            named(
                'file',
                $(consumer(anyNonBlankString()), producer('hello'))
            ).fileName('payload.bin').contentType('application/octet-stream')
        )
    }

    response {
        status 415
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'UNSUPPORTED_DOCUMENT_MEDIA_TYPE',
            message: 'Only text/plain documents are supported'
        )
    }
}
~~~

This enforces a **file part media type** policy. The overall request remains `multipart/form-data`; do not confuse this with an unsupported top-level request Content-Type.

When debugging, inspect the `Content-Type` header **on each MIME part**. A client can send a valid multipart request yet omit the file part's media type or have its library default it to `application/octet-stream`.

## 17. Contract 422: Unsupported Filename

Create `upload-invalid-filename.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Reject filename with disallowed extension'

    request {
        method POST()
        url '/api/documents'
        headers {
            header('Accept', 'application/json')
        }
        multipart(
            formParameter('description', 'Unexpected file type'),
            named(
                'file',
                $(consumer(anyNonBlankString()), producer('hello'))
            ).fileName('payload.exe').contentType('text/plain')
        )
    }

    response {
        status 422
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'INVALID_FILENAME',
            message: 'Only .txt filenames are accepted'
        )
    }
}
~~~

The media type stays `text/plain` so the service passes media-type validation and reaches extension validation. If you change both the filename and send `application/octet-stream`, validation order would return 415 instead of 422.

This illustrates an important rule: **each test scenario should isolate the condition being tested**. If multiple conditions fail simultaneously, the result depends on validation order and becomes harder to diagnose.

## 18. Summary Table of Contract Scenarios

| Contract | Multipart request | Expected status | Error code / response |
|---|---|---:|---|
| `upload-success` | file `note.txt`, `text/plain`, 5 bytes + description | 201 | `documentId`, `filename`, `size`, `UPLOADED` |
| `upload-missing-description` | File part only | 400 | `MISSING_PART` |
| `upload-too-large` | 11-byte file, `text/plain` | 413 | `DOCUMENT_TOO_LARGE` |
| `upload-unsupported-media-type` | File `application/octet-stream` | 415 | `UNSUPPORTED_DOCUMENT_MEDIA_TYPE` |
| `upload-invalid-filename` | Filename `payload.exe`, `text/plain` | 422 | `INVALID_FILENAME` |

Each contract is an independent producer verification scenario. Avoid writing a single giant “upload” contract with overly broad matchers, as that obscures which condition triggers which error.

## 19. Running Producer Verification

In the project directory, run the producer module using your configured wrapper and build lifecycle:

~~~bash
./mvnw -pl document-service -am clean verify
~~~

If producer and consumer live in separate repositories, run the command inside the `document-service` repository. In a multi-module project, confirm `-pl` points to the right module and `-am` builds required dependencies.

After the build, verify:

1. Contract files were discovered by the plugin.
2. Generated producer tests were created for all five scenarios.
3. Generated test sources compiled.
4. Test reports show **executed count > 0**.
5. No generated contract tests were unintentionally skipped.
6. The success scenario returns 201 and matches the response schema.
7. Error scenarios return exact 400/413/415/422 statuses and error codes.
8. The stubs JAR was packaged with the expected classifier.
9. The JAR contains mappings for all five scenarios.

**Do not stop at the `BUILD SUCCESS` line.** If contract tests were not discovered or executed counts are 0, the producer is not contract-verified.

## 20. Inspecting Generated Producer Tests

Locate the generated sources in the output directory logged by the plugin. Common paths sit under `target/generated-test-sources`, though you should verify your actual configuration.

For each test, examine:

- Which contract scenario does the test method correspond to?
- Does the multipart request include both `file` and `description` fields?
- Does the file part carry filename `note.txt` and media type `text/plain`?
- Does the generated file content match the sample?
- Do error scenarios genuinely omit the part, change the media type, increase size, or change the filename?
- How do assertions check status and error body?
- Does the base test use the real Spring MVC context?

In particular, **generated sources prove tests were generated; test reports prove they actually executed**. Both are required.

If generated requests do not emit the expected parts or your plugin version does not support the multipart syntax shown here, consult the DSL reference for your pinned version and adjust the contract accordingly. Never replace verification with a hand-written test controller returning canned responses and call it generated producer verification.

## 21. Inspecting Generated WireMock Mappings and the Stubs JAR

SCC generates WireMock mappings from the same contracts. Open the actual mappings for success and each error scenario. Check:

- Request method and path;
- Multipart form parameter matching;
- File part name and filename;
- Part `Content-Type`;
- File content matcher;
- Response status, headers, and body/error code;
- Mapping priority and potential overlap.

Specific mapping syntax can be expressed via JSON body patterns or multipart matchers depending on the WireMock/SCC version. **Do not hand-edit generated mappings in build output** when your goal is testing contract sources.

Inspect the JAR:

~~~bash
jar tf document-service/target/document-service-1.0.0-SNAPSHOT-stubs.jar
~~~

Substitute the actual filename/version from your build output. Verify that the mappings and any body resource files they reference are inside the JAR. If your build produces a different artifact classifier, use the actual coordinates from Maven output.

## 22. Creating the Consumer Multipart Client

In `case-service`, use a real HTTP client. Example using `RestTemplate` with `ByteArrayResource` to preserve the filename:

~~~java
package com.example.caseapp.client;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.*;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;

import java.util.List;

public class MultipartDocumentClient {

    private final RestTemplate restTemplate;
    private final String documentServiceUrl;

    public MultipartDocumentClient(
            RestTemplate restTemplate,
            String documentServiceUrl) {
        this.restTemplate = restTemplate;
        this.documentServiceUrl = documentServiceUrl;
    }

    public ResponseEntity<DocumentResponse> upload(
            byte[] bytes,
            String filename,
            String description,
            MediaType fileMediaType) {

        ByteArrayResource fileResource =
            new ByteArrayResource(bytes) {
                @Override
                public String getFilename() {
                    return filename;
                }
            };

        HttpHeaders fileHeaders = new HttpHeaders();
        fileHeaders.setContentType(fileMediaType);

        HttpEntity<ByteArrayResource> filePart =
            new HttpEntity<>(fileResource, fileHeaders);

        MultiValueMap<String, Object> parts =
            new LinkedMultiValueMap<>();
        parts.add("file", filePart);
        parts.add("description", description);

        HttpHeaders requestHeaders = new HttpHeaders();
        requestHeaders.setContentType(MediaType.MULTIPART_FORM_DATA);
        requestHeaders.setAccept(
            List.of(MediaType.APPLICATION_JSON));

        HttpEntity<MultiValueMap<String, Object>> request =
            new HttpEntity<>(parts, requestHeaders);

        return restTemplate.postForEntity(
            documentServiceUrl + "/api/documents",
            request,
            DocumentResponse.class
        );
    }
}
~~~

`DocumentResponse` is the consumer's success DTO and can mirror the JSON structure of the producer response. Declare the `RestTemplate` and client beans in the application and inject the base URL via configuration. Never hardcode production URLs in source code.

The HTTP client library generates the multipart boundary automatically. Do not manually set a `Content-Type: multipart/form-data` header with a fake boundary; let the message converter generate a boundary consistent with the request body.

## 23. Configuring Stub Runner for the Consumer

Consumer tests require the Stub Runner dependency in test scope and the exact candidate stub coordinates. Example:

~~~java
@SpringBootTest(properties = {
    "document-service.url=http://localhost:18081"
})
@AutoConfigureStubRunner(
    ids = "com.example:document-service:1.0.0-rc1:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/candidates"
)
class MultipartDocumentCompatibilityTest {
    // Inject real MultipartDocumentClient.
}
~~~

`example.invalid` is an illustrative URL. With `StubsMode.LOCAL`, the artifact must be installed in the local Maven repository used by the consumer test process. With `REMOTE`, configure repository credentials and mirrors per your CI environment.

**Port 18081** in the example must match the client URL. If Stub Runner allocates a dynamic port, inject the actual port into the client instead of keeping a static value.

Never mock `MultipartDocumentClient` in compatibility tests; mocking the client means multipart requests never reach WireMock.

## 24. Consumer Test: Successful Upload

Example test invoking the real client:

~~~java
@SpringBootTest(properties = {
    "document-service.url=http://localhost:18081"
})
@AutoConfigureStubRunner(
    ids = "com.example:document-service:1.0.0-rc1:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/candidates"
)
class MultipartDocumentCompatibilityTest {

    @Autowired
    MultipartDocumentClient client;

    @Test
    void uploadsTextDocument() {
        ResponseEntity<DocumentResponse> response =
            client.upload(
                "hello".getBytes(StandardCharsets.UTF_8),
                "note.txt",
                "Quarterly report",
                MediaType.TEXT_PLAIN
            );

        assertThat(response.getStatusCode())
            .isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().filename())
            .isEqualTo("note.txt");
        assertThat(response.getBody().contentType())
            .isEqualTo("text/plain");
        assertThat(response.getBody().size()).isEqualTo(5);
        assertThat(response.getBody().status())
            .isEqualTo("UPLOADED");
    }
}
~~~

This is an illustrative test body; add imports, bean wiring, and test class annotations fitting your project. `documentId` can be dynamic, so tests should not assert equality against a hardcoded stub UUID when the contract only promises format.

When running, confirm WireMock receives the multipart request. If you get status 404, inspect mappings and the request journal before assuming the producer returned a business 404.

## 25. Consumer Tests for Error Responses

`RestTemplate` throws `HttpClientErrorException` on 4xx statuses by default. Tests can verify both status and error code in the body:

~~~java
@Test
void rejectsUnsupportedFileMediaType() throws Exception {
    HttpClientErrorException ex =
        catchThrowableOfType(
            () -> client.upload(
                "hello".getBytes(StandardCharsets.UTF_8),
                "payload.bin",
                "Binary attachment",
                MediaType.APPLICATION_OCTET_STREAM
            ),
            HttpClientErrorException.class
        );

    assertThat(ex.getStatusCode())
        .isEqualTo(HttpStatus.UNSUPPORTED_MEDIA_TYPE);

    ApiError error = objectMapper.readValue(
        ex.getResponseBodyAsString(),
        ApiError.class
    );
    assertThat(error.code())
        .isEqualTo("UNSUPPORTED_DOCUMENT_MEDIA_TYPE");
}
~~~

`catchThrowableOfType` is a common AssertJ helper requiring a compatible version and static import. You can substitute standard JUnit try/catch if preferred. The goal is to **assert both the HTTP status and error code**, not merely catch a generic exception.

Write matching tests for:

- Missing description → 400 + `MISSING_PART`;
- File too large → 413 + `DOCUMENT_TOO_LARGE`;
- Unsupported media type → 415 + `UNSUPPORTED_DOCUMENT_MEDIA_TYPE`;
- Invalid filename → 422 + `INVALID_FILENAME`.

The consumer may translate these errors into domain-specific exceptions. Test that mapping as well if consumer business logic depends on it.

## 26. Negative Test: Renaming a Multipart Part

Suppose the contract requires part `file`, but the client is accidentally changed to send `document`.

A control test can use a test-only client sending the wrong part name. Expected results:

- The request fails to match the happy-path mapping;
- WireMock does not erroneously return 201 success;
- The test receives an unmatched response or diagnostic fallback;
- The request journal shows the wrong part name.

The response does not have to be 400/422, since WireMock can return an unmatched 404 before a request ever reaches a producer. What matters is **never falsely receiving a contract success response**.

Afterward, restore part name `file` and re-run the success test. This negative test proves the request matcher enforces constraints.

## 27. Negative Test: Changing Data Types and Media Types

Try each mutation in turn:

| Mutation | Wire request | Expectation |
|---|---|---|
| Quantity-like metadata sent as string (if API adds this field) | JSON string instead of number | Matcher/schema must distinguish |
| File part media type changed | `application/octet-stream` | Matches 415 scenario, not 201 |
| Filename changed from `.txt` to `.exe` | Different filename | Matches 422 scenario |
| Empty file content | 0 bytes | Matches empty/invalid file scenario if declared in contract |
| Missing description | Part omitted | Matches 400 scenario |
| Part name changed | `document` instead of `file` | Does not match happy path |

In this project, quantity is not part of the multipart request; the “string instead of number” example applies only if you extend the API with a JSON metadata part. Do not add mutations outside the current schema and conclude the contract is broken.

## 28. Inspecting Raw Multipart Requests

When consumer tests fail, collect the following from the right WireMock server or sanitized HTTP client logging:

~~~text
POST /api/documents
Content-Type: multipart/form-data; boundary=----client-boundary

Part: description
Content-Disposition: form-data; name="description"
Value: Quarterly report

Part: file
Content-Disposition: form-data; name="file"; filename="note.txt"
Content-Type: text/plain
Bytes: 5
Body: hello
~~~

This is a **conceptual view of the request**, not fixed wire bytes. Boundaries vary per request; headers may include charsets; part order may vary unless the contract enforces ordering.

Check these key properties:

- Are part names exactly `file` and `description`?
- Did the client omit the filename?
- Is the file part's `Content-Type` right?
- Was the file body unintentionally Base64-encoded or stringified?
- Does the multipart boundary in the header match the body?
- Was the top-level request `Content-Type` accidentally set to `application/json`?
- Was `description` sent as a form field or stuffed inside a JSON body?

**Never log production document contents.** Use synthetic fixtures and log safe sizes, hashes, or metadata when investigating.

## 29. Debugging 404s from Stub Runner

An HTTP 404 in this lab can mean one of three things:

1. **Artifact resolution 404:** Stub Runner failed to download the stubs JAR from the repository.
2. **WireMock unmatched 404:** the server is running, but the request did not match any mapping.
3. **Business 404:** a producer contract explicitly defines a document-not-found response.

How to distinguish them:

| Clue | Error category |
|---|---|
| Stub Runner startup log reports artifact not found | Resolution / repository |
| Stub Runner starts cleanly, client request gets 404 | Likely unmatched mapping |
| Body contains a contract error code like `DOCUMENT_NOT_FOUND` | Likely business 404 |
| Request journal shows near-miss on part name/header/body | Multipart mismatch |

Never change an error contract to 404 just to make a test pass. Inspect the response body, startup logs, and request journal to pinpoint where the failure occurred.

## 30. Multipart Body Matchers and Boundaries

A multipart request is not like a simple JSON body. WireMock/SCC converts multipart DSL into matching rules for form parameters and file parts. When inspecting generated mappings:

- Look for part names `file` and `description`;
- Confirm whether filename and content type are matched;
- Check whether file content is matched by exact equality, regex, or type;
- Confirm body matchers do not contain a hardcoded boundary;
- Confirm invalid requests do not match success;
- Confirm error scenario mappings do not overlap too broadly with success.

If generated mappings only check method and path while ignoring critical parts, inspect the contract syntax and SCC version. Do not edit files in `target`; fix the DSL and regenerate.

## 31. Preventing Error Scenarios from Overlapping

A single request can violate multiple rules at once. For instance, a `.exe` filename combined with `application/octet-stream` could match both 415 and 422 error scenarios if request matchers do not isolate conditions.

To prevent ambiguity:

1. Design each failure scenario to violate **one primary condition**.
2. Keep all other conditions valid.
3. Make request matchers specific enough for that scenario.
4. Check mapping priorities when multiple mappings could match.
5. Test combined invalid inputs to clarify behavior when multiple errors occur.
6. Document producer validation order whenever that order determines status/error codes.

In this lab, the 422 scenario keeps `text/plain` so media type is valid; the 415 scenario keeps a valid filename so only media type fails. This cleanly isolates root causes.
## 32. Checking Producer Tests for Each Error Scenario

After generated tests run, compare expected vs. actual results in a table:

| Scenario | Expected status | Expected error code | Assertion to verify |
|---|---:|---|---|
| Missing description | 400 | `MISSING_PART` | Missing part caught before service |
| 11-byte file | 413 | `DOCUMENT_TOO_LARGE` | Business size limit enforced |
| Part `application/octet-stream` | 415 | `UNSUPPORTED_DOCUMENT_MEDIA_TYPE` | File part media type read properly |
| Filename `.exe` | 422 | `INVALID_FILENAME` | Filename validation runs after earlier checks |

If the status is right but the error code is wrong, the contract must still fail. Returning 415 with body `INVALID_FILENAME`, for example, breaks the commitment.

If the 413 test returns 500, verify that the exception handler is registered in the Spring context. If requests never reach the controller because the servlet multipart parser rejects them first, inspect the parser limit and exception type; do not alter service-level contracts to mask parser-layer errors.

## 33. Configuring the Consumer Client Bean

Simple wiring example:

~~~java
@Configuration
public class DocumentClientConfiguration {

    @Bean
    RestTemplate documentRestTemplate(
            RestTemplateBuilder builder) {
        return builder.build();
    }

    @Bean
    MultipartDocumentClient multipartDocumentClient(
            RestTemplate documentRestTemplate,
            @Value("${document-service.url}") String baseUrl) {
        return new MultipartDocumentClient(
            documentRestTemplate, baseUrl);
    }
}
~~~

In consumer test configuration, point the URL to Stub Runner:

~~~yaml
document-service:
  url: http://localhost:18081
~~~

In production profiles, point the URL to environment-specific service discovery or an API gateway. Never commit Stub Runner addresses into production configuration.

## 34. Consumer Error Assertions: Status and Code Must Go Together

A test helper can bundle error-response assertions:

~~~java
private ApiError expectHttpError(
        ThrowingCallable action,
        HttpStatus expectedStatus) throws Exception {

    HttpClientErrorException ex =
        catchThrowableOfType(
            action,
            HttpClientErrorException.class
        );

    assertThat(ex.getStatusCode()).isEqualTo(expectedStatus);

    return objectMapper.readValue(
        ex.getResponseBodyAsString(),
        ApiError.class
    );
}
~~~

Then:

~~~java
@Test
void missingDescriptionReturns400() throws Exception {
    ApiError error = expectHttpError(
        () -> client.uploadWithoutDescription(
            "hello".getBytes(StandardCharsets.UTF_8),
            "note.txt",
            MediaType.TEXT_PLAIN
        ),
        HttpStatus.BAD_REQUEST
    );

    assertThat(error.code()).isEqualTo("MISSING_PART");
}
~~~

`uploadWithoutDescription` is a test-only helper implemented with the same HTTP client that adds only the file part. Never call the producer service directly, because the goal is testing **the consumer request through Stub Runner**.

Write matching assertions for 413, 415, and 422. When the consumer translates API errors into domain exceptions, add tests for those mappings too.

## 35. Consumer Tests Must Send the Right Multipart Bytes

With `RestTemplate`, `ByteArrayResource.getFilename()` is critical. Without overriding the filename, the multipart converter may omit the filename or use a default name. That can cause WireMock matchers to miss even when content bytes match.

Check:

- Does `Content-Disposition` include `name="file"`?
- Does it include `filename="note.txt"`?
- Is the file part's `Content-Type` set to `text/plain`?
- Is description sent as a form part named `description`?
- Does the overall request `Content-Type` include a converter-generated boundary?
- Do the multipart bytes match the UTF-8/ASCII sample content?

If a client uses WebClient, Feign, or RestClient instead of RestTemplate, how resources and part headers are built differs. Inspect the raw request instead of assuming every client serializes identically.

## 36. Isolating Validation Order

The service in this lab validates in the following order:

1. Null/empty file;
2. Null/blank description;
3. File media type;
4. File size;
5. Filename extension.

Thus, a request that both has an unsupported media type and exceeds the size limit returns 415 before checking size. A request with both a bad filename and an unsupported media type returns 415 before 422.

This is real application behavior. To keep diagnostics deterministic:

- Each error scenario should violate **one primary condition**.
- Keep all other parts valid.
- Add a dedicated scenario for combinations if error precedence is something the consumer relies on.
- Do not expect the producer to return multiple error codes simultaneously.
- Document validation precedence if that order affects status or error codes.

An API may choose a different order, as long as generated tests and the implementation agree.

## 37. Mind File Upload Security

Multipart contract tests verify the wire interface; they do not prove file uploads are secure. Production projects must also address:

- Request size limits at the reverse proxy, servlet container, and service layers;
- Inspecting actual MIME types rather than trusting filenames or client-supplied `Content-Type` headers alone;
- File signature / content sniffing appropriate to supported document types;
- Malware scanning and quarantine if required by policy;
- Filename normalization, path traversal prevention, and Unicode confusables;
- Storing files outside the web root with proper access controls and encryption;
- Never returning filesystem paths or raw file contents in API responses;
- Rate limiting, authentication/authorization, and tenant isolation;
- Cleaning up temporary files on upload failure or client disconnect;
- Auditing metadata without logging PII or secrets.

Do not stuff an entire security policy into contract matchers. Contracts protect **interface and error semantics**; security integration tests verify the remaining defense layers.

## 38. Building and Publishing Candidate Stubs

Producer verification must pass before the consumer uses stubs. In a local multi-module lab, a workflow can look like:

~~~bash
./mvnw -pl document-service -am clean install
~~~

Then run consumer tests:

~~~bash
./mvnw -pl case-service test
~~~

Adjust commands and module flags to match your real project layout. `install` places the artifact into the local Maven repository; in separate-repository CI, the producer pipeline typically publishes a **unique candidate version** to a build/test repository.

Never use `latest` or an uncontrolled mutable SNAPSHOT for compatibility release gates. Candidates should be tied to a producer commit/build ID so consumer tests prove they ran against exact mappings.

## 39. Verifying the Exact Artifact Resolved by Stub Runner

Record at a minimum:

~~~text
producerCommit: <producer commit>
contractRevision: <contract commit/hash>
stubCoordinates: com.example:document-service:<candidate>:stubs
producerTestCount: <executed count>
producerResult: PASS
stubJarSha256: <digest after packaging>

consumerCommit: <consumer commit>
resolvedStubCoordinates: <actual coordinates>
resolvedStubSha256: <downloaded JAR digest>
stubRunnerPort: <actual port>
consumerTestCount: <executed count>
consumerResult: PASS/FAIL
~~~

`<...>` fields are placeholders. Compare producer and consumer digests to avoid testing against a stale stubs JAR. When using `LOCAL`, inspect the local repository of the exact runner/container; when using `REMOTE`, inspect repository metadata and proxies.

**Do not confuse newly edited mapping files in your workspace with mappings currently served by Stub Runner.** An already-started WireMock server may still hold mappings loaded prior to artifact publication.

## 40. CI Pipeline for Multipart Contracts

~~~mermaid
flowchart TD
    A["Producer source + multipart contracts"] --> B["Generate Contract Verifier tests"]
    B --> C["Run producer tests on real Spring context"]
    C --> D{"Executed > 0 and PASS?"}
    D -- "No" --> X["BLOCK"]
    D -- "Yes" --> E["Package stubs JAR candidate"]
    E --> F["Inspect mappings + body resources"]
    F --> G["Publish immutable candidate + digest"]
    G --> H["Consumer resolves exact stubs"]
    H --> I["Run multipart client tests"]
    I --> J["Run negative and error scenarios"]
    J --> K{"Consumer compatibility PASS?"}
    K -- "No" --> X
    K -- "Yes" --> L["Evaluate release policy"]
~~~

Producer CI must verify:

- All contract scenarios were discovered;
- Generated producer tests have executed count > 0;
- No policy-violating skips occurred;
- Error statuses and body assertions passed;
- The stubs JAR contains complete mappings and body resources.

Consumer CI must verify:

- Exact candidate artifact, version, and digest;
- Stub Runner server started cleanly;
- The real client sent multipart requests with the right part names, filenames, and media types;
- Both success and error scenarios executed;
- Negative requests did not falsely receive success;
- Test reports link back to the consumer commit.

## 41. Troubleshooting Matrix

| Symptom | Common cause | Evidence to inspect |
|---|---|---|
| No generated tests produced | Wrong contract directory or plugin config | Plugin logs, contract discovery |
| Multipart DSL fails to parse | Syntax differs in your SCC version | DSL reference for exact version |
| Test sends request missing file part | Contract `named(...)` or generated adapter | Generated Java test |
| Producer receives file with null filename | Client resource did not supply filename | Raw `Content-Disposition` |
| File part becomes `application/octet-stream` | Client did not set part `Content-Type` | Raw MIME headers |
| Consumer sends JSON instead of multipart | Wrong converter or request headers | Request `Content-Type` and body |
| Success test returns 404 | Unmatched mapping or stale stub | Request journal, resolved JAR |
| 415 returned instead of 422 | Multiple invalid conditions, validation order | Service order, actual part `Content-Type` |
| 413 never reaches service | Servlet/proxy limit blocked before controller | Multipart parser/proxy logs |
| 413 turns into 500 | Missing exception handler or different parser exception | Stack trace / exception type |
| Producer tests green with 0 tests run | Test runner skip or discovery issue | Surefire/Gradle report |
| Consumer test always passes even with wrong part name | Overly broad matcher or 201 fallback | Generated mapping, priority |
| Artifact resolution 404 | Wrong classifier, version, or repository | Stub Runner startup log |
| Tests pass against stale SNAPSHOT | Cache, proxy, or server loaded old mappings | Timestamp, digest, startup time |
| Error body has right status but wrong code | Inconsistent exception advice mapping | Raw response body |

## 42. Extended Exercise: Adding an Empty-File Scenario

Add a contract for a present-but-empty file:

- Part name stays `file`;
- Filename stays `note.txt`;
- Media type stays `text/plain`;
- File content has 0 bytes;
- Expected status 422;
- Error code `EMPTY_FILE`.

Distinguish this from the 400 missing-part contract. One case is **a missing part**, while the other is **a present part with zero bytes**. The producer controller/service may handle them differently, and the consumer needs the right error code.

After adding the contract, verify the generated request actually sends an empty file with a filename and content type rather than accidentally omitting the part altogether.

## 43. Extended Exercise: Testing Limits at the Servlet Parser Layer

In the main lab, 413 comes from the business size limit after parsing. Extend the lab to test limits at the parser layer:

1. Lower `spring.servlet.multipart.max-file-size` to a small value in a dedicated test profile.
2. Send a file exceeding the parser limit.
3. Observe whether the exception occurs before or after the controller.
4. Standardize the exception to 413 if the API commits to that status.
5. Verify whether `@RestControllerAdvice` can return an error body under your container/test adapter.
6. Write an integration test against a real embedded server if MockMvc does not faithfully model parser/container behavior.
7. Keep the business size-limit test and parser-limit test as two separate scenarios.

Do not merge both 413 types into one test if they traverse different processing layers.

## 44. Extended Exercise: Consumer Domain-Level Error Handling

In `case-service`, map error codes:

| API error code | Example domain behavior |
|---|---|
| `MISSING_PART` | Client request construction bug |
| `DOCUMENT_TOO_LARGE` | Display upload size limit to user |
| `UNSUPPORTED_DOCUMENT_MEDIA_TYPE` | Prompt user to select a supported format |
| `INVALID_FILENAME` | Prompt user to rename the file |
| Transport timeout | Retry per policy; do not confuse with validation |
| Unmatched WireMock 404 | Compatibility test failure, not business not-found |

Write unit/consumer tests for this mapping. Do not collapse every 4xx into the same generic exception if the application needs distinct responses.

## 45. Project Completion Checklist

- [ ] Producer endpoint accepts `multipart/form-data`.
- [ ] Part names `file` and `description` match the contract.
- [ ] File part carries a filename and `Content-Type`.
- [ ] Multipart boundary is client-generated, never hardcoded.
- [ ] `DocumentService` validates empty file, description, media type, size, and filename.
- [ ] Exception handler returns a uniform error schema.
- [ ] Success contract 201 exists.
- [ ] Error contracts 400, 413, 415, and 422 exist.
- [ ] Generated producer tests invoke the real Spring MVC context.
- [ ] Generated tests have executed count > 0 and are not skipped.
- [ ] Assertions verify status, body, and error codes.
- [ ] Generated mappings were verified against your exact SCC version.
- [ ] Stubs JAR contains required mappings and resources.
- [ ] Consumer Stub Runner resolves the exact candidate version.
- [ ] Consumer real HTTP client sends multipart requests.
- [ ] Success and error consumer tests run against WireMock.
- [ ] Negative test changing part name does not falsely receive success.
- [ ] Negative test changing media type/filename matches the expected error scenario.
- [ ] Request journals/logs are sanitized of sensitive data.
- [ ] Producer/consumer test evidence records commit, version, and digest.
- [ ] CI blocks if generated tests equal 0 or the stubs artifact is stale.
- [ ] Business errors, unmatched WireMock errors, and artifact resolution errors are distinguished.
- [ ] Lab limitations and required additional security/integration tests are documented.

## 46. Self-Check Questions

**1. Why shouldn't a multipart boundary be hardcoded in a contract?**

Because boundaries are generated per request by the client; contracts should verify multipart fields and file parts semantically rather than locking a random boundary string.

**2. What is the difference between a missing file part and an empty file?**

A missing part is a binding/request structure error; an empty file means the part is present with zero bytes. The API can return different error codes for each.

**3. Why is a 413 from a business limit different from a 413 from the servlet parser?**

The business limit is checked after the controller/service receives the file; the parser limit can reject the request before reaching the controller. Test adapters and exception handling can differ.

**4. Why must each file part's Content-Type be checked?**

The top-level request is `multipart/form-data`, but the file part has its own media type; the producer can reject unsupported part types with 415.

**5. Why doesn't a consumer stub test prove the producer code is right?**

Stub Runner serves responses from WireMock mappings without executing `DocumentController` or `DocumentService`. Producer generated tests provide separate proof.

**6. If the consumer receives 404, can you conclude the document does not exist?**

No. It could be an unmatched WireMock request due to mismatched part names, headers, or bodies, or an artifact download failure. Check startup logs, response bodies, and the request journal.

**7. Why must tests assert error codes in addition to HTTP status?**

Multiple errors can share a status or fall back to a default status; the error code identifies the exact semantics the consumer must handle.

**8. What if producer generated tests PASS with an executed count of 0?**

There is no proof of producer verification. Fix test discovery, runner, or skip configuration and re-run.

**9. Why must Stub Runner use the exact candidate artifact?**

So the consumer tests against mappings generated from the exact producer contract revision, avoiding false passes from stale stubs or mutable SNAPSHOTs.

**10. What does an upload contract test not prove on its own?**

Malware scanning, authorization, storage durability, path traversal protection, proxy limits, and performance all require dedicated security and integration tests.

## 47. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, generated tests, stubs, and Stub Runner.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy DSL, request/response, and matchers.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): HTTP request/response contract details.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): stub resolution and consumer testing.
- [Spring Framework — Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html): multipart handling in Spring MVC.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestTemplate` and HTTP clients.
- [Spring Boot — Servlet Web](https://docs.spring.io/spring-boot/reference/web/servlet.html): servlet multipart configuration.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): request matching and diagnostics.
- [WireMock — Verifying](https://wiremock.org/docs/verifying/): request journal and verification.
- [RFC 7578 — multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578): multipart form-data specification.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status codes and HTTP semantics.

**Version note:** Multipart DSL, generated test adapters, WireMock mappings, and Stub Runner configuration depend on your Spring Boot, Spring Cloud Contract, and WireMock versions. The snippets provide a hands-on skeleton to align with your actual dependency BOM; several test classes need complete imports, bean wiring, and helpers before compiling. The 10-byte limit is a small illustrative fixture, not a production setting. This authoring step did not execute Maven/Gradle builds or dedicated Content QA.

---

**Key takeaway:** A solid multipart contract project protects both **request structure** (part names, filenames, media types, content) and **success/error outcomes**. Generated producer tests must run against the real controller/service; consumer tests must use a real HTTP client against the exact candidate stubs version. When errors happen, trace contract → generated test → mapping → raw multipart request/response to fix the right layer, rather than loosening matchers or assuming every 404 is a business error.
