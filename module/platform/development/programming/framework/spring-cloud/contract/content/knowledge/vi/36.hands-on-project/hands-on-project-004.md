# Kiểm thử request multipart và trường hợp phản hồi lỗi

## 1. Mục tiêu dự án thực hành

Trong bài này, bạn sẽ xây dựng một luồng upload tài liệu nhỏ để thực hành **Spring Cloud Contract (SCC)** từ producer tới consumer. Producer cung cấp HTTP API nhận request `multipart/form-data`; consumer gửi file và metadata; SCC mô tả giao tiếp bằng Groovy contract, sinh producer verification tests và WireMock stubs; Stub Runner cung cấp stub cho consumer compatibility tests.

Dự án có một endpoint:

~~~http
POST /api/documents
Content-Type: multipart/form-data
Accept: application/json
~~~

Request gồm hai phần:

- `file`: nội dung tài liệu dạng file, có filename và media type.
- `description`: mô tả ngắn cho tài liệu.

Khi hợp lệ, producer trả HTTP 201 với metadata tài liệu. Khi không hợp lệ, producer trả lỗi có schema thống nhất và status phù hợp.

Bạn sẽ kiểm tra năm tình huống chính:

| Scenario | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Upload thành công | File `.txt`, media type `text/plain`, description hợp lệ | **201 Created** |
| Thiếu description | Chỉ gửi file | **400 Bad Request** |
| File quá lớn | Nội dung vượt giới hạn nghiệp vụ | **413 Content Too Large** |
| Media type không hỗ trợ | File part là `application/octet-stream` | **415 Unsupported Media Type** |
| Tên file không hợp lệ | File có phần mở rộng không được phép | **422 Unprocessable Content** |

Các giới hạn byte và tên file trong bài là fixture học tập. Một hệ thống thực cần chọn policy theo nghiệp vụ, bảo mật và hạ tầng lưu trữ.

### Kết quả cần đạt

Sau khi hoàn thành, bạn có thể:

1. Mô tả multipart request với file part và form field trong SCC Groovy DSL.
2. Sinh generated producer tests và kiểm tra chúng gọi Spring MVC application thật.
3. Kiểm tra status, error code và response body cho nhiều trường hợp lỗi.
4. Đóng gói stubs JAR và dùng Stub Runner trong consumer tests.
5. Kiểm tra raw multipart request, boundary, filename, part Content-Type và body.
6. Phân biệt business error với lỗi do WireMock không match request.
7. Chứng minh các lỗi như đổi tên part hoặc đổi kiểu dữ liệu làm test thất bại.
8. Tích hợp producer verification và consumer compatibility vào CI.

## 2. Kiến trúc và luồng kiểm thử

Dự án có hai ứng dụng:

- **document-service (producer):** nhận upload, kiểm tra dữ liệu, trả document metadata hoặc lỗi.
- **case-service (consumer):** gọi document-service qua HTTP client để đính kèm tài liệu vào hồ sơ.

SCC contract thuộc producer. Generated producer tests kiểm tra controller/service thật; generated stubs mô phỏng cùng giao diện cho consumer.

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

Hai loại test trả lời hai câu hỏi khác nhau:

| Bộ test | Thành phần thật | Thành phần giả lập | Bằng chứng |
|---|---|---|---|
| Producer contract verification | Controller, service, validation, exception handler | Adapter/test environment theo SCC | Producer code đáp ứng contract |
| Consumer compatibility | Consumer client, serializer, error handling | WireMock stubs từ producer candidate | Consumer hiểu request/response contract |
| End-to-end (tùy chọn) | Cả hai service và network | Có thể không dùng stub | Tích hợp trong môi trường thử |

**Không dùng consumer stub test để tuyên bố producer code đã đúng.** WireMock không thực thi controller của document-service.

## 3. Cấu trúc project đề xuất

Một cách tổ chức repository:

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

Tên package/path chỉ là ví dụ. Bạn có thể dùng Maven multi-module hoặc hai repository độc lập; điều quan trọng là **producer publish stubs candidate** và consumer test resolve đúng tọa độ artifact.

## 4. Chốt API contract trước khi viết code

### Multipart request

| Thành phần | Tên part/header | Quy tắc |
|---|---|---|
| File | `file` | Bắt buộc, filename kết thúc `.txt` |
| File content type | Part header `Content-Type` | `text/plain` |
| File content | Bytes của file | Không rỗng, tối đa 10 bytes trong lab |
| Description | Part `description` | Bắt buộc, không rỗng |
| Request Content-Type | `multipart/form-data; boundary=...` | Boundary do HTTP client sinh |
| Accept | `application/json` | Consumer yêu cầu JSON |

**Không hardcode multipart boundary** trong contract. Boundary được client sinh ở mỗi request; matcher nên kiểm tra multipart semantics và các part cần thiết, không so raw toàn bộ body theo một chuỗi boundary cố định.

### Success response

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

`documentId` là UUID động; `size` phụ thuộc số bytes thực. Các giá trị này cần matcher theo format/kiểu, còn filename, media type và status trong scenario fixture có thể kiểm chính xác.

### Error response

Các lỗi dùng cùng schema:

~~~json
{
  "code": "UNSUPPORTED_DOCUMENT_MEDIA_TYPE",
  "message": "Only text/plain documents are supported"
}
~~~

Mỗi error code phải được gắn với đúng HTTP status. Consumer nên phân biệt lỗi validation, lỗi media type, lỗi dung lượng và transport failure.

## 5. Chuẩn bị dependency và phiên bản

SCC phụ thuộc sự tương thích giữa **Spring Boot, Spring Cloud Release Train và Spring Cloud Contract**. Hãy dùng Spring Cloud BOM phù hợp với Spring Boot đang chọn; không sao chép một plugin version ngẫu nhiên từ project khác.

Producer cần các dependency theo vai trò:

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

Plugin Maven cần được cấu hình để:

- Discovery contract directory đúng module;
- Sinh producer tests;
- Dùng base class tương ứng;
- Đính kèm stubs artifact với classifier theo convention SCC;
- Chạy verification trong lifecycle thích hợp.

Ví dụ cấu hình ý tưởng:

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

Đây là **khung cấu hình**. Plugin version, test mode spelling, generated source paths và lifecycle phải đối chiếu reference của SCC release đang dùng.

Consumer cần `spring-cloud-starter-contract-stub-runner` trong test scope, cùng HTTP client dependency của ứng dụng. Không cần đưa Stub Runner vào production runtime chỉ để chạy compatibility tests.

## 6. Cấu hình giới hạn upload cho lab

Tạo `document-service/src/main/resources/application.yml`:

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

Có hai giới hạn khác nhau:

- Servlet multipart parser giới hạn kích thước request/file tối đa được nhận ở tầng framework.
- `documents.max-upload-bytes` là **giới hạn nghiệp vụ** do DocumentService kiểm tra sau khi multipart parser đã đọc file.

Trong lab, giới hạn nghiệp vụ 10 bytes giúp tạo fixture 11 bytes nhỏ và dễ kiểm tra 413. Không nên áp dụng giới hạn 10 bytes cho sản phẩm thực. Khi kiểm thử giới hạn ở tầng servlet/container, cần cấu hình và xử lý exception tương ứng vì controller có thể **chưa được gọi**.

## 7. Tạo response DTO và error DTO

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

Giữ error schema nhỏ và ổn định giúp consumer mapping rõ ràng. Không trả stack trace, filesystem path hoặc nội dung file trong error response.

## 8. Implement DocumentService

Ví dụ service kiểm tra file và trả metadata. Phần lưu trữ thực tế được lược giản để bài tập tập trung vào HTTP contract; dự án production nên đặt storage sau một interface riêng.

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

Bạn cần tạo thêm các exception class `InvalidDocumentException`, `UnsupportedDocumentMediaTypeException` và `DocumentTooLargeException` (có thể đặt trong package service). Ví dụ constructor:

~~~java
public class DocumentTooLargeException extends RuntimeException {
    public DocumentTooLargeException() {
        super("Document exceeds the configured size limit");
    }
}
~~~

Đối với `InvalidDocumentException`, giữ `code` và `message` để exception handler có thể trả error code theo scenario. Không dùng tên file để tạo đường dẫn lưu trực tiếp; nếu bổ sung persistence, cần xử lý path traversal, tên trùng và malware scanning.

## 9. Implement controller nhận multipart

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

`@RequestPart` buộc request có đúng tên part. Nếu consumer gửi `document` thay vì `file`, hoặc bỏ `description`, Spring MVC có thể từ chối request trước khi vào service. Đây là behavior cần được chuẩn hóa bằng exception handler.

## 10. Chuẩn hóa error handling

Tạo `ApiExceptionHandler`:

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

Ví dụ này giả định `InvalidDocumentException` có `getCode()` và các exception class nằm trong package được import. Khi hoàn thiện project, bổ sung constructor/accessor tương ứng và kiểm compile.

**Phân biệt 400 và 422 theo policy của API:** trong lab, 400 dành cho multipart part bắt buộc bị thiếu; 422 dành cho dữ liệu đã parse được nhưng không hợp lệ về nghiệp vụ. Một hệ thống có thể chọn quy ước khác, nhưng phải nhất quán giữa contract, producer và consumer.

## 11. Hoàn thiện exception classes

Tạo `InvalidDocumentException`:

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

Đặt class đúng package mà controller advice import. Nếu IDE không tìm thấy class, kiểm package declaration trước khi thay đổi exception mapping.

## 12. Base class cho generated producer tests

Tạo `ContractTestBase`:

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

Mục tiêu là generated test gọi **Spring MVC context**, đi qua controller, validation, service và exception advice. Không thay bằng fake controller trả sẵn body contract; nếu làm vậy, producer verification có thể xanh dù code thực sai.

Cấu hình plugin để dùng đúng fully-qualified class name `com.example.document.ContractTestBase`. Nếu project dùng WebFlux hoặc real HTTP port, chọn test adapter/base class tương ứng và xác minh bằng generated test source.

## 13. Contract thành công: multipart file + description

Tạo `upload-success.groovy` trong contract directory:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Upload file text thành công'

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

Trong ví dụ:

- `formParameter` mô tả form field `description`.
- `named` mô tả file part tên `file`.
- `fileName` và `contentType` ràng buộc metadata của file part.
- `producer('hello')` cung cấp nội dung mẫu 5 bytes cho generated producer test/stub.
- `consumer(anyNonBlankString())` diễn tả phía stub chấp nhận nội dung file không rỗng theo matcher.

**Lưu ý:** cách SCC áp dụng consumer/producer side của multipart matcher và API builder có thể thay đổi theo version. Sau generation, đọc Java test và WireMock mapping để xác nhận request được sinh và match đúng; đừng giả định chỉ nhìn Groovy source đã đủ.

## 14. Contract 400: thiếu multipart part bắt buộc

Tạo `upload-missing-description.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Từ chối upload khi thiếu description'

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

Request chỉ có file part, không có `description`. Spring MVC sẽ từ chối binding `@RequestPart("description")` trước khi gọi service; `ApiExceptionHandler` chuẩn hóa lỗi thành 400.

Đây là một scenario khác với “description rỗng”: nếu part có mặt nhưng nội dung rỗng, controller có thể được gọi và service trả 422 theo logic đã viết. Hãy giữ hai trường hợp tách biệt nếu API cam kết semantics khác nhau.

## 15. Contract 413: file vượt giới hạn nghiệp vụ

Tạo `upload-too-large.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Từ chối file vượt giới hạn upload nghiệp vụ'

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

File mẫu `01234567890` có 11 ký tự ASCII, tương ứng 11 bytes; giới hạn nghiệp vụ trong lab là 10 bytes. Matcher consumer giới hạn nội dung file theo một pattern đủ dài cho scenario này. Regex/multipart matcher phải được kiểm tra ở generated mapping của SCC version đang dùng.

**Phân biệt hai loại giới hạn:**

- Nếu `documents.max-upload-bytes` chặn file sau khi parse, controller/service có thể trả 413 như ví dụ.
- Nếu `spring.servlet.multipart.max-file-size` hoặc proxy chặn trước controller, exception có thể là `MaxUploadSizeExceededException` hoặc lỗi ở tầng gateway. Cần contract/integration setup riêng để xác minh chính xác status/body ở tầng đó.

Không hạ multipart parser limit xuống 10 bytes trong khi muốn test business check 10 bytes; parser có thể chặn trước và scenario 413 của service không được thực thi.

## 16. Contract 415: file part có media type không hỗ trợ

Tạo `upload-unsupported-media-type.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Từ chối file part có media type không hỗ trợ'

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

Đây là policy của **file part media type**. Request tổng thể vẫn là `multipart/form-data`; đừng nhầm với lỗi request Content-Type tổng thể không được endpoint hỗ trợ.

Khi debug, xem header Content-Type **ở từng MIME part**. Một client có thể gửi multipart đúng nhưng file part thiếu media type hoặc bị thư viện mặc định thành `application/octet-stream`.

## 17. Contract 422: filename không được hỗ trợ

Tạo `upload-invalid-filename.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Từ chối filename có phần mở rộng không được phép'

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

Media type được giữ là `text/plain` để service đi qua bước kiểm media type và kiểm tra phần mở rộng. Nếu vừa đổi filename vừa gửi `application/octet-stream`, thứ tự validation có thể làm kết quả là 415 thay vì 422.

Điều này minh họa một nguyên tắc quan trọng: **một test scenario nên cô lập điều kiện cần kiểm**. Nếu nhiều điều kiện cùng sai, kết quả phụ thuộc thứ tự validation và khó chẩn đoán.

## 18. Bảng tổng hợp contract scenarios

| Contract | Request multipart | Expected status | Error code / response |
|---|---|---:|---|
| `upload-success` | file `note.txt`, `text/plain`, 5 bytes + description | 201 | `documentId`, `filename`, `size`, `UPLOADED` |
| `upload-missing-description` | Chỉ có file part | 400 | `MISSING_PART` |
| `upload-too-large` | File 11 bytes, `text/plain` | 413 | `DOCUMENT_TOO_LARGE` |
| `upload-unsupported-media-type` | File `application/octet-stream` | 415 | `UNSUPPORTED_DOCUMENT_MEDIA_TYPE` |
| `upload-invalid-filename` | Filename `payload.exe`, `text/plain` | 422 | `INVALID_FILENAME` |

Mỗi contract là một scenario producer verification độc lập. Tránh tạo một contract “upload” khổng lồ với matcher quá rộng, vì nó khó chỉ ra điều kiện nào tạo ra lỗi.

## 19. Chạy producer verification

Tại thư mục project, chạy producer module theo wrapper và build lifecycle đã cấu hình:

~~~bash
./mvnw -pl document-service -am clean verify
~~~

Nếu producer và consumer là hai repository riêng, chạy lệnh trong repository document-service. Nếu dùng một multi-module project, xác nhận `-pl` trỏ đúng module và `-am` build các dependency cần thiết.

Sau build, kiểm tra:

1. Contract files được plugin discovery.
2. Generated producer tests được tạo cho cả năm scenarios.
3. Generated test sources compile.
4. Test report có **executed count > 0**.
5. Không có generated contract tests bị skip ngoài chủ đích.
6. Success scenario trả 201 và response đúng schema.
7. Error scenarios trả đúng 400/413/415/422 và error code.
8. Stubs JAR được đóng gói với classifier đúng.
9. JAR chứa mappings tương ứng năm scenarios.

**Không chỉ nhìn dòng BUILD SUCCESS.** Nếu contract tests không được discovery hoặc số test thực thi bằng 0, producer chưa được contract-verified.

## 20. Đọc generated producer tests

Tìm generated source trong output directory do plugin log ra. Các đường dẫn thường gặp có thể nằm dưới `target/generated-test-sources`, nhưng cần xác minh cấu hình thực tế.

Với từng test, đọc:

- Test method liên hệ contract scenario nào?
- Request multipart có field `file` và `description` không?
- File part có filename `note.txt` và media type `text/plain` không?
- Nội dung file được sinh có đúng sample hay không?
- Error scenario có thật sự bỏ part/đổi media type/tăng kích thước/đổi filename không?
- Assertions kiểm status và error body ra sao?
- Base test có dùng Spring MVC context thật không?

Đặc biệt, **generated source là bằng chứng về test được tạo; test report là bằng chứng về test đã chạy**. Cần cả hai.

Nếu generated request không gửi đúng part hoặc plugin version không hỗ trợ cú pháp multipart như ví dụ, kiểm reference DSL của version đã pin và chỉnh contract theo syntax được hỗ trợ. Không thay bằng một test controller tự viết trả sẵn response rồi gọi nó là generated producer verification.

## 21. Kiểm generated WireMock mappings và stubs JAR

SCC sinh WireMock mappings từ cùng contract. Mở mapping thực tế cho success và từng error scenario. Kiểm tra:

- Request method/path;
- Multipart form parameter matching;
- Tên file part và filename;
- Part Content-Type;
- File content matcher;
- Response status, headers và body/error code;
- Mapping priority và khả năng overlap.

Cú pháp mapping cụ thể có thể được biểu diễn bằng JSON body patterns hoặc multipart matchers khác nhau theo WireMock/SCC version. **Không tự viết lại mapping bằng tay trong generated output** nếu mục tiêu là kiểm contract source.

Kiểm JAR:

~~~bash
jar tf document-service/target/document-service-1.0.0-SNAPSHOT-stubs.jar
~~~

Tên/version file cần thay bằng output thật. Xác nhận mapping và mọi resource body file mà mapping tham chiếu đều nằm trong JAR. Nếu build tạo classifier artifact khác, dùng tọa độ thực từ Maven output.

## 22. Tạo consumer multipart client

Trong case-service, dùng HTTP client thật. Ví dụ dùng `RestTemplate` với `ByteArrayResource` để giữ filename:

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

`DocumentResponse` là DTO success của consumer, có thể dùng cùng cấu trúc JSON với producer response. Cần khai báo bean `RestTemplate`/client trong ứng dụng và inject base URL bằng configuration. Không hardcode URL production trong source.

Thư viện HTTP client sẽ tự sinh multipart boundary. Không tự đặt header `Content-Type: multipart/form-data` kèm boundary giả; để message converter tạo boundary đồng nhất với request body.

## 23. Cấu hình Stub Runner cho consumer

Consumer test cần dependency Stub Runner trong test scope và tọa độ stubs artifact đúng candidate. Ví dụ:

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
    // Inject MultipartDocumentClient thật.
}
~~~

`example.invalid` là URL minh họa. Với `StubsMode.LOCAL`, artifact phải được install vào local Maven repository mà consumer test process sử dụng. Với REMOTE, cấu hình repository credentials/mirror theo môi trường CI.

**Port 18081** trong ví dụ phải khớp URL client. Nếu Stub Runner cấp dynamic port, inject port thực vào client thay vì giữ giá trị tĩnh.

Không mock `MultipartDocumentClient` trong compatibility test; nếu mock chính client, multipart request không bao giờ tới WireMock.

## 24. Test consumer: upload thành công

Ví dụ test gọi client thật:

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

Đây là phần thân test minh họa; thêm imports, bean wiring và test class annotations phù hợp project. `documentId` có thể động, nên test không nên so sánh với một UUID cố định từ stub nếu contract chỉ cam kết format.

Khi chạy, xác nhận WireMock nhận request multipart. Nếu status 404, xem mapping và request journal trước khi kết luận producer trả business 404.

## 25. Test consumer cho các phản hồi lỗi

`RestTemplate` mặc định ném `HttpClientErrorException` với status 4xx. Test có thể kiểm status và error code trong body:

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

`catchThrowableOfType` là helper thường gặp trong AssertJ, cần đúng phiên bản và static import. Có thể thay bằng try/catch JUnit thông thường. Mục tiêu là **assert cả HTTP status và error code**, không chỉ bắt một exception chung.

Viết các tests tương tự:

- Thiếu description → 400 + `MISSING_PART`;
- File quá lớn → 413 + `DOCUMENT_TOO_LARGE`;
- Media type không hỗ trợ → 415 + `UNSUPPORTED_DOCUMENT_MEDIA_TYPE`;
- Filename sai → 422 + `INVALID_FILENAME`.

Consumer có thể chuyển những lỗi này thành domain exceptions riêng. Hãy test mapping đó nếu consumer business logic phụ thuộc.

## 26. Negative test: đổi tên multipart part

Contract yêu cầu part `file`, nhưng client bị sửa nhầm thành `document`.

Một test đối chứng có thể dùng client test-only gửi sai part name. Kỳ vọng:

- Request không match happy-path mapping;
- WireMock không trả nhầm 201 success;
- Test nhận unmatched response hoặc fallback chẩn đoán;
- Request journal cho thấy part name không đúng.

Không nhất thiết response phải là 400/422, vì WireMock có thể trả unmatched 404 trước khi request tới producer. Điều quan trọng là **không nhận nhầm response success của contract**.

Sau đó khôi phục tên part `file` và chạy lại success test. Đây là negative test chứng minh request matcher có ràng buộc.

## 27. Negative test: đổi kiểu dữ liệu và media type

Thử lần lượt:

| Mutation | Request wire | Kỳ vọng |
|---|---|---|
| Quantity-like metadata chuyển thành string (nếu API có field này) | JSON string thay number | Matcher/schema phải phân biệt |
| File part đổi media type | `application/octet-stream` | Match scenario 415, không match 201 |
| Filename đổi `.txt` thành `.exe` | Filename khác | Match scenario 422 |
| File content rỗng | 0 bytes | Match scenario invalid/empty file nếu contract khai báo |
| Thiếu description | Không có part | Match scenario 400 |
| Đổi part name | `document` thay `file` | Không match happy path |

Trong project này quantity không nằm trong multipart request; ví dụ “string thay number” chỉ áp dụng nếu bạn mở rộng API thêm metadata JSON part. Đừng đưa một mutation không thuộc schema hiện tại vào test suite rồi kết luận contract sai.

## 28. Kiểm raw multipart request

Khi consumer test thất bại, thu các dữ liệu sau từ đúng WireMock server hoặc HTTP client logging đã sanitize:

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

Đây là **mô hình đọc request**, không phải wire bytes cố định. Boundary sẽ thay đổi theo request; header có thể có charset; part order có thể khác nhau nếu contract không yêu cầu thứ tự.

So các thuộc tính quan trọng:

- Tên part có đúng `file` và `description`?
- Filename có bị client bỏ mất không?
- Content-Type của file part có đúng không?
- File body có bị encode thành Base64/string ngoài ý muốn không?
- Multipart boundary ở header có khớp body không?
- Request Content-Type tổng thể có bị đặt thành `application/json`?
- Description có được gửi thành form field hay bị nhét vào JSON body?

**Không log nội dung tài liệu production**. Dùng fixture giả, log size/hash hoặc metadata an toàn khi điều tra.

## 29. Debug 404 từ Stub Runner

Một HTTP 404 trong bài lab có thể là:

1. **Artifact resolution 404:** Stub Runner không tải được stubs JAR từ repository.
2. **WireMock unmatched 404:** server đã chạy nhưng request không match mapping.
3. **Business 404:** producer contract thực sự mô tả tài liệu không tồn tại.

Cách phân biệt:

| Dấu hiệu | Loại lỗi |
|---|---|
| Stub Runner startup log báo artifact not found | Resolution/repository |
| Stub Runner start thành công, client request nhận 404 | Có thể unmatched mapping |
| Body chứa mã lỗi contract như `DOCUMENT_NOT_FOUND` | Có thể business 404 |
| Request journal có near miss về part name/header/body | Multipart mismatch |

Không đổi error contract thành 404 chỉ để làm test xanh. Đọc response body, startup logs và request journal để biết lỗi ở thời điểm nào.

## 30. Multipart body matcher và boundary

Multipart request không giống một JSON body đơn giản. WireMock/SCC có thể chuyển DSL multipart thành các điều kiện matching cho form parameters và file parts. Khi kiểm generated mapping:

- Tìm part name `file` và `description`;
- Xác nhận filename/content type có được match;
- Xem file content được so exact, regex hay type;
- Xác nhận body matcher không chứa boundary cố định;
- Kiểm request sai không match success;
- Kiểm mapping error scenario không chồng lấn quá rộng với success.

Nếu mapping generated chỉ kiểm method/path mà bỏ qua các part quan trọng, hãy xem contract syntax và version. Đừng tự sửa file trong `target`; sửa DSL rồi regenerate.

## 31. Tránh để các error scenarios chồng lấn

Một request có thể đồng thời sai nhiều điều kiện. Ví dụ filename `.exe` và media type `application/octet-stream` có thể match cả error scenarios 415 và 422 nếu request matcher không tách điều kiện.

Để tránh ambiguity:

1. Thiết kế mỗi scenario sai **một điều kiện chính**.
2. Giữ các điều kiện còn lại hợp lệ.
3. Đặt matcher request đủ rõ cho scenario.
4. Kiểm mapping priority nếu nhiều mapping cùng match.
5. Thử các input kết hợp sai để xác định behavior khi có nhiều lỗi.
6. Document thứ tự validation của producer nếu thứ tự ấy ảnh hưởng status/error code.

Trong lab, scenario 422 giữ `text/plain` để media type hợp lệ; scenario 415 giữ filename hợp lệ để chỉ media type sai. Đây là cách cô lập nguyên nhân.
## 32. Kiểm producer test cho từng error scenario

Sau khi generated tests chạy, lập bảng so expected/actual:

| Scenario | Expected status | Expected error code | Assertion cần kiểm |
|---|---:|---|---|
| Thiếu description | 400 | `MISSING_PART` | Part thiếu được phát hiện trước service |
| File 11 bytes | 413 | `DOCUMENT_TOO_LARGE` | Business size limit được thực thi |
| Part `application/octet-stream` | 415 | `UNSUPPORTED_DOCUMENT_MEDIA_TYPE` | File part media type được đọc đúng |
| Filename `.exe` | 422 | `INVALID_FILENAME` | Validation filename chạy sau các điều kiện trước |

Nếu status đúng nhưng error code sai, contract vẫn cần phát hiện. Ví dụ 415 với body `INVALID_FILENAME` là một behavior khác với cam kết.

Nếu test 413 trả 500, kiểm exception handler có được đăng ký trong Spring context không. Nếu request không vào controller vì servlet multipart parser chặn trước, kiểm multipart parser limit và exception type; đừng sửa contract service-level để che lỗi tầng parser.

## 33. Cấu hình consumer client bean

Ví dụ wiring đơn giản:

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

Trong file cấu hình consumer test, URL trỏ tới Stub Runner:

~~~yaml
document-service:
  url: http://localhost:18081
~~~

Ở production profile, URL trỏ service discovery/API gateway theo môi trường. Không commit địa chỉ Stub Runner vào cấu hình production.

## 34. Consumer error assertions: status và code phải đi cùng nhau

Một helper test có thể gom kiểm tra error response:

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

Sau đó:

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

`uploadWithoutDescription` là helper test-only cần triển khai bằng cùng HTTP client nhưng chỉ thêm file part. Không gọi service producer trực tiếp, vì mục tiêu là kiểm tra **consumer request qua Stub Runner**.

Viết assertions tương tự cho 413, 415 và 422. Khi consumer translate API errors thành domain exceptions, thêm test mapping đó.

## 35. Một consumer test phải gửi đúng multipart bytes

Với `RestTemplate`, `ByteArrayResource.getFilename()` rất quan trọng. Nếu không override filename, multipart converter có thể tạo file part không có filename hoặc dùng tên mặc định. Điều đó có thể làm WireMock matcher không khớp dù content bytes đúng.

Kiểm tra:

- `Content-Disposition` có `name="file"` không?
- Có `filename="note.txt"` không?
- `Content-Type` của file part là `text/plain` không?
- Description là một form part tên `description` không?
- Request Content-Type tổng thể có boundary do converter tạo không?
- Multipart bytes có đúng nội dung UTF-8/ASCII sample không?

Nếu client dùng WebClient, Feign hoặc RestClient thay cho RestTemplate, cách tạo resource/part headers khác nhau. Hãy kiểm raw request thay vì cho rằng mọi client serialize giống nhau.

## 36. Cô lập validation order

Service trong bài kiểm tra theo thứ tự:

1. File null/empty;
2. Description null/blank;
3. File media type;
4. File size;
5. Filename extension.

Vì vậy nếu một request vừa có media type sai vừa quá lớn, nó có thể trả 415 trước khi xét size. Nếu vừa filename sai vừa media type sai, nó trả 415 trước 422.

Đây là một phần của behavior thực tế. Để chẩn đoán deterministic:

- Mỗi scenario sai chỉ làm sai **một điều kiện chính**.
- Các phần khác phải hợp lệ.
- Thêm một scenario riêng cho combination nếu thứ tự lỗi là điều consumer phụ thuộc.
- Không yêu cầu producer trả nhiều error codes cùng lúc.
- Ghi thứ tự validation nếu thứ tự ấy ảnh hưởng status/error code.

Một API có thể chọn thứ tự khác, nhưng generated tests và implementation phải thống nhất.

## 37. Cẩn trọng với file upload security

Multipart contract tests kiểm giao tiếp; chúng không tự chứng minh file upload an toàn. Dự án production cần xem xét thêm:

- Giới hạn request size ở reverse proxy, servlet container và service;
- Kiểm tra MIME type thực tế, không tin duy nhất filename hoặc client-supplied Content-Type;
- File signature/content sniffing theo loại tài liệu;
- Malware scanning/quarantine nếu nghiệp vụ yêu cầu;
- Filename normalization, path traversal và Unicode confusables;
- Lưu trữ ngoài web root, quyền truy cập và encryption;
- Không trả filesystem path hoặc file contents trong API response;
- Rate limiting, authentication/authorization và tenant isolation;
- Cleanup file tạm khi upload lỗi hoặc client disconnect;
- Audit metadata mà không ghi PII/secrets.

Không nên nhét toàn bộ security policy vào một contract matcher. Contract bảo vệ **giao diện và error semantics**; security integration tests kiểm các lớp bảo vệ khác.

## 38. Build và publish stubs candidate

Producer verification phải đạt trước khi consumer dùng stubs. Với local multi-module lab, một quy trình có thể là:

~~~bash
./mvnw -pl document-service -am clean install
~~~

Sau đó chạy consumer tests:

~~~bash
./mvnw -pl case-service test
~~~

Lệnh và module selection cần điều chỉnh theo cấu trúc project thực. `install` đưa artifact vào local Maven repository; trong CI tách repository, producer pipeline thường publish một **candidate version duy nhất** vào repository dành cho build/test.

Không dùng `latest` hoặc một SNAPSHOT mutable không kiểm soát cho compatibility release gate. Candidate nên gắn producer commit/build ID để consumer test chứng minh đã dùng đúng mappings.

## 39. Xác minh artifact mà Stub Runner thực sự resolve

Ghi tối thiểu:

~~~text
producerCommit: <producer commit>
contractRevision: <contract commit/hash>
stubCoordinates: com.example:document-service:<candidate>:stubs
producerTestCount: <executed count>
producerResult: PASS
stubJarSha256: <digest sau packaging>

consumerCommit: <consumer commit>
resolvedStubCoordinates: <coordinates thực tế>
resolvedStubSha256: <digest JAR tải được>
stubRunnerPort: <port thực>
consumerTestCount: <executed count>
consumerResult: PASS/FAIL
~~~

Các trường `<...>` là placeholder. So digest producer/consumer để tránh test với stubs JAR cũ. Nếu dùng LOCAL, kiểm local repository của đúng agent/container; nếu REMOTE, kiểm repository metadata/proxy.

**Đừng nhầm file mapping mới trong workspace với mapping đang được Stub Runner phục vụ.** WireMock server đã start có thể giữ mappings đã load từ trước khi artifact được publish.

## 40. CI pipeline cho multipart contracts

~~~mermaid
flowchart TD
    A["Producer source + multipart contracts"] --> B["Generate Contract Verifier tests"]
    B --> C["Run producer tests trên Spring context thật"]
    C --> D{"Executed > 0 và PASS?"}
    D -- "Không" --> X["BLOCK"]
    D -- "Có" --> E["Package stubs JAR candidate"]
    E --> F["Inspect mappings + body resources"]
    F --> G["Publish immutable candidate + digest"]
    G --> H["Consumer resolves exact stubs"]
    H --> I["Run multipart client tests"]
    I --> J["Run negative and error scenarios"]
    J --> K{"Consumer compatibility PASS?"}
    K -- "Không" --> X
    K -- "Có" --> L["Evaluate release policy"]
~~~

Producer CI cần kiểm:

- Tất cả contract scenarios được discovery;
- Generated producer tests executed count > 0;
- Không có skip ngoài policy;
- Error status và body assertions đạt;
- Stubs JAR có mapping/body resources đầy đủ.

Consumer CI cần kiểm:

- Đúng candidate artifact/version/digest;
- Stub Runner server start thành công;
- Client thật gửi multipart đúng tên part, filename, media type;
- Success và error scenarios đều được chạy;
- Negative request không nhận nhầm success;
- Test report được liên kết với consumer commit.

## 41. Troubleshooting matrix

| Triệu chứng | Nguyên nhân thường gặp | Bằng chứng cần xem |
|---|---|---|
| Generated test không được sinh | Contract directory/plugin sai | Plugin logs, contract discovery |
| Multipart DSL parse fail | Syntax khác SCC version | DSL reference đúng version |
| Test gửi request thiếu file part | Contract `named(...)` hoặc generated adapter | Generated Java test |
| Producer nhận file nhưng filename null | Client resource không cung cấp filename | Raw Content-Disposition |
| File part thành `application/octet-stream` | Client không set part Content-Type | Raw MIME headers |
| Consumer gửi JSON thay multipart | Request converter/header sai | Request Content-Type và body |
| Success test trả 404 | Mapping không match hoặc stub cũ | Request journal, resolved JAR |
| 415 bị trả thay 422 | Nhiều điều kiện sai, validation order | Service order, actual part Content-Type |
| 413 không đi qua service | Servlet/proxy limit chặn trước controller | Multipart parser/proxy logs |
| 413 thành 500 | Exception handler thiếu hoặc parser exception khác | Stack trace/type exception |
| Producer tests xanh với tests run 0 | Test runner skip/discovery | Surefire/Gradle report |
| Consumer test luôn xanh dù part name sai | Matcher quá rộng/fallback 201 | Generated mapping, priority |
| Artifact resolution 404 | Sai classifier/version/repository | Stub Runner startup log |
| Test pass với SNAPSHOT cũ | Cache/proxy/server đã load mapping cũ | Timestamp, digest, startup time |
| Error body đúng status nhưng sai code | Exception advice mapping chưa thống nhất | Raw response body |

## 42. Bài thực hành mở rộng: thêm scenario file rỗng

Thêm contract cho file có mặt nhưng rỗng:

- Part name vẫn là `file`;
- Filename vẫn `note.txt`;
- Media type vẫn `text/plain`;
- File content có 0 bytes;
- Expected status 422;
- Error code `EMPTY_FILE`.

Phân biệt với contract 400 thiếu file part. Một trường hợp là **không có part**, trường hợp kia là **có part nhưng content rỗng**. Producer controller/service có thể xử lý khác nhau; consumer cũng cần nhận đúng error code.

Sau khi thêm contract, kiểm generated request thực sự tạo file rỗng có filename và content type, không vô tình bỏ hẳn part.

## 43. Bài thực hành mở rộng: kiểm tra giới hạn ở servlet parser

Trong lab chính, 413 đến từ business size limit sau khi parse. Mở rộng bài để kiểm tra limit ở tầng parser:

1. Hạ `spring.servlet.multipart.max-file-size` xuống một giá trị nhỏ trong profile test riêng.
2. Gửi file vượt parser limit.
3. Quan sát exception xảy ra trước hay sau controller.
4. Chuẩn hóa exception thành 413 nếu API cam kết status đó.
5. Xác định response body có thể được trả qua `@RestControllerAdvice` trong container/test adapter đang dùng hay không.
6. Viết integration test chạy trên đúng embedded server nếu MockMvc không mô phỏng chính xác parser/container behavior.
7. Giữ business size-limit test và parser-limit test là hai scenarios riêng.

Không gộp hai loại 413 thành một bài nếu chúng đi qua các tầng xử lý khác nhau.

## 44. Bài thực hành mở rộng: consumer xử lý lỗi theo domain

Trong case-service, ánh xạ error code:

| API error code | Domain behavior ví dụ |
|---|---|
| `MISSING_PART` | Client request construction bug |
| `DOCUMENT_TOO_LARGE` | Hiển thị giới hạn upload cho người dùng |
| `UNSUPPORTED_DOCUMENT_MEDIA_TYPE` | Yêu cầu chọn định dạng được hỗ trợ |
| `INVALID_FILENAME` | Yêu cầu đổi tên file |
| Transport timeout | Retry theo policy, không nhầm validation |
| Unmatched WireMock 404 | Compatibility test failure, không phải business not-found |

Viết unit/consumer tests cho mapping này. Không dùng cùng một exception chung cho mọi 4xx nếu ứng dụng cần phản hồi khác nhau.

## 45. Checklist hoàn thành project

- [ ] Producer endpoint nhận `multipart/form-data`.
- [ ] Part names `file` và `description` đúng contract.
- [ ] File part có filename và Content-Type.
- [ ] Multipart boundary do client tạo, không hardcode.
- [ ] DocumentService kiểm file rỗng, description, media type, size và filename.
- [ ] Exception handler trả error schema thống nhất.
- [ ] Có success contract 201.
- [ ] Có error contracts 400, 413, 415 và 422.
- [ ] Generated producer tests gọi Spring MVC context thật.
- [ ] Generated tests executed count > 0, không bị skip.
- [ ] Assertions kiểm status, body và error code.
- [ ] Generated mappings được kiểm tra từ đúng SCC version.
- [ ] Stubs JAR có mappings và resources cần thiết.
- [ ] Consumer Stub Runner resolve đúng candidate version.
- [ ] Consumer HTTP client thật gửi multipart request.
- [ ] Success và error consumer tests chạy qua WireMock.
- [ ] Negative test đổi part name không nhận nhầm success.
- [ ] Negative test đổi media type/filename match đúng error scenario.
- [ ] Request journal/log đã sanitize dữ liệu nhạy cảm.
- [ ] Producer/consumer test evidence có commit, version, digest.
- [ ] CI block nếu generated tests bằng 0 hoặc stubs artifact stale.
- [ ] Đã phân biệt business error, unmatched WireMock và artifact resolution error.
- [ ] Đã ghi rõ phần giới hạn lab và các test security/integration bổ sung.

## 46. Câu hỏi tự kiểm tra

**1. Vì sao multipart boundary không nên hardcode trong contract?**

Vì boundary do client sinh theo từng request; contract nên kiểm multipart fields và file parts theo semantics, không khóa một chuỗi boundary ngẫu nhiên.

**2. Khác nhau giữa thiếu file part và file rỗng là gì?**

Thiếu part là lỗi binding/request structure; file rỗng là part tồn tại nhưng không có bytes. API có thể trả error code khác nhau.

**3. Vì sao 413 từ business limit khác 413 từ servlet parser?**

Business limit được kiểm sau khi controller/service nhận file; parser limit có thể chặn trước controller. Test adapter và exception handling có thể khác.

**4. Vì sao phải kiểm Content-Type của từng file part?**

Request tổng thể là multipart/form-data nhưng file part có media type riêng; producer có thể từ chối part không hỗ trợ bằng 415.

**5. Vì sao consumer stub test không chứng minh producer code đúng?**

Stub Runner trả response từ WireMock mapping, không thực thi DocumentController/DocumentService. Producer generated tests là bằng chứng riêng.

**6. Nếu consumer nhận 404, có thể kết luận document không tồn tại không?**

Không. Đó có thể là unmatched WireMock do part name/header/body không khớp, hoặc lỗi tải artifact. Cần xem startup log, response body và request journal.

**7. Tại sao test phải assert error code ngoài HTTP status?**

Nhiều lỗi có thể cùng status hoặc status mặc định; error code xác định semantics mà consumer cần xử lý.

**8. Nếu producer generated test PASS nhưng executed count bằng 0 thì sao?**

Chưa có bằng chứng producer verification. Cần sửa discovery/runner/skip configuration và chạy lại.

**9. Vì sao Stub Runner phải dùng exact candidate artifact?**

Để consumer test với mappings được sinh từ đúng producer contract revision, tránh false PASS do stubs cũ/SNAPSHOT mutable.

**10. Những gì contract test upload không tự chứng minh?**

Malware scanning, authorization, storage durability, path traversal protection, proxy limits và hiệu năng cần security/integration tests phù hợp.

## 47. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, generated tests, stubs và Stub Runner.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy DSL, request/response và matchers.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): HTTP request/response contract details.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): resolve stubs và consumer testing.
- [Spring Framework — Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html): xử lý multipart trong Spring MVC.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestTemplate và các HTTP client.
- [Spring Boot — Servlet Web](https://docs.spring.io/spring-boot/reference/web/servlet.html): servlet multipart configuration.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): request matching và diagnostics.
- [WireMock — Verifying](https://wiremock.org/docs/verifying/): request journal và verification.
- [RFC 7578 — multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578): định dạng multipart form data.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status codes và HTTP semantics.

**Lưu ý phiên bản:** Multipart DSL, generated test adapter, WireMock mapping và Stub Runner configuration phụ thuộc phiên bản Spring Boot/Spring Cloud Contract/WireMock. Các snippet là khung thực hành cần đối chiếu với dependency BOM thực tế; một số test class cần imports, bean wiring và helper hoàn chỉnh trước khi compile. Giới hạn 10 bytes là fixture nhỏ để minh họa, không phải cấu hình production. Bước biên soạn không chạy Maven/Gradle hoặc Content QA chuyên sâu.

---

**Điểm cần nhớ:** Một project multipart contract tốt bảo vệ cả **cấu trúc request** (part names, filename, media type, content) lẫn **các kết quả thành công và lỗi**. Producer generated tests phải chạy trên controller/service thật; consumer tests phải dùng HTTP client thật với stubs candidate đúng version. Khi lỗi xảy ra, đối chiếu contract → generated test → mapping → raw multipart request/response để sửa đúng lớp, không nới matcher hoặc coi mọi 404 là business error.

