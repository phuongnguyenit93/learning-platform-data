# Tạo yêu cầu multipart gồm tệp và thông tin JSON

Một API upload thường cần nhận cả nội dung tệp và metadata mô tả tệp đó trong cùng một HTTP request. Ví dụ, client gửi một file tài liệu cùng JSON chứa tiêu đề, loại tài liệu và mã hồ sơ liên quan. HTTP multipart/form-data cho phép chia request body thành nhiều part, mỗi part có tên, header và nội dung riêng.

Với Spring Boot, có thể dùng Spring MVC MultipartFile hoặc Spring WebFlux FilePart để nhận file. Phần metadata JSON được bind thành DTO bằng RequestPart. Springdoc-openapi cần mô tả request body là multipart/form-data, trong đó part file có schema dạng string/binary và part metadata tham chiếu đến JSON schema của DTO.

## 1. Kết quả cần xây dựng

API thực hành có endpoint:

~~~text
POST /api/documents
Content-Type: multipart/form-data
~~~

Request gồm hai part:

| Tên part | Content-Type | Nội dung |
|---|---|---|
| file | image/png, application/pdf hoặc loại file được hỗ trợ | Byte của tệp upload |
| metadata | application/json | JSON mô tả tệp |

Ví dụ metadata:

~~~json
{
  "title": "Hợp đồng dịch vụ",
  "category": "LEGAL",
  "referenceCode": "CASE-2026-015"
}
~~~

Response thành công trả mã tài liệu, tên file, loại nội dung và metadata đã lưu. Trong ví dụ này, endpoint trả HTTP 201 Created.

## 2. Vì sao dùng multipart/form-data?

multipart/form-data chia request body thành nhiều phần độc lập. Mỗi part có Content-Disposition chứa tên trường và có thể có Content-Type riêng.

Một request có thể gồm:

- Part file chứa byte của tệp.
- Part metadata chứa JSON.
- Các part khác nếu API cần thêm trường riêng.

Không nên chuyển file thành Base64 trong JSON nếu API không có yêu cầu đặc biệt. Base64 làm payload lớn hơn, tăng chi phí encode/decode và khiến client/server phải xử lý toàn bộ file như chuỗi JSON.

multipart/form-data phù hợp khi một operation cần nhận nhiều loại dữ liệu trong cùng request body.

## 3. Tạo DTO cho metadata

Metadata là JSON object nên nên mô hình hóa bằng DTO riêng:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

@Schema(
        name = "DocumentMetadata",
        description = "Thông tin mô tả tài liệu được tải lên"
)
public record DocumentMetadata(
        @Schema(
                description = "Tiêu đề tài liệu",
                example = "Hợp đồng dịch vụ"
        )
        @NotBlank
        @Size(max = 150)
        String title,

        @Schema(
                description = "Nhóm tài liệu",
                example = "LEGAL",
                allowableValues = {"LEGAL", "FINANCE", "OTHER"}
        )
        @NotBlank
        @Pattern(regexp = "LEGAL|FINANCE|OTHER")
        String category,

        @Schema(
                description = "Mã hồ sơ liên quan",
                example = "CASE-2026-015"
        )
        @NotBlank
        @Size(max = 50)
        String referenceCode
) {}
~~~

DTO có ba trường bắt buộc. Bean Validation kiểm tra dữ liệu khi request được bind; Schema mô tả ý nghĩa và ví dụ cho OpenAPI. Nếu category là miền giá trị cố định trong ứng dụng thật, có thể dùng enum thay cho String cùng Pattern.

## 4. Mô tả part file trong OpenAPI

Trong OpenAPI, file upload được biểu diễn bằng schema string với format binary. Metadata JSON được biểu diễn bằng schema object hoặc tham chiếu đến component schema.

Ví dụ schema tổng thể:

~~~yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required:
          - file
          - metadata
        properties:
          file:
            type: string
            format: binary
            description: Tệp cần tải lên
          metadata:
            $ref: '#/components/schemas/DocumentMetadata'
~~~

Tên property trong schema phải khớp tên part mà controller nhận. Nếu controller dùng RequestPart("upload") nhưng OpenAPI mô tả property file, client sẽ gửi sai tên trường.

Part metadata có thể khai báo encoding để chỉ rõ content type:

~~~yaml
encoding:
  metadata:
    contentType: application/json
~~~

Thông tin này giúp consumer hiểu part metadata cần được gửi dưới dạng JSON, thay vì chuỗi text tùy ý.

## 5. Tạo schema request multipart để tái sử dụng

Có thể tạo một class chỉ dùng làm model tài liệu:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
        name = "UploadDocumentRequest",
        description = "Request gồm tệp và metadata JSON"
)
public record UploadDocumentRequest(
        @Schema(
                description = "Tệp cần tải lên",
                type = "string",
                format = "binary"
        )
        String file,

        @Schema(
                description = "Metadata JSON của tài liệu",
                implementation = DocumentMetadata.class
        )
        DocumentMetadata metadata
) {}
~~~

Class này mô tả cấu trúc multipart cho OpenAPI. Controller vẫn có thể nhận từng part thành MultipartFile và DocumentMetadata. Không cần serialize class tài liệu này thành JSON body thực tế.

Nếu springdoc tự suy luận đúng schema từ tham số controller, có thể không cần model tài liệu riêng. Khi output không thể hiện part metadata như mong muốn, dùng RequestBody annotation của Swagger Core để chỉ định schema multipart rõ ràng.

## 6. Cài dependency cho Spring MVC

Ứng dụng Spring MVC cần Web starter, validation và springdoc UI nếu muốn xem Swagger UI:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>2.x.y</version>
    </dependency>
</dependencies>
~~~

Thay 2.x.y bằng phiên bản springdoc v2 tương thích với Spring Boot của dự án. Nếu không cần Swagger UI, dùng starter WebMVC API tương ứng.

Spring Boot thường tự cấu hình multipart resolver cho Spring MVC. Có thể đặt giới hạn kích thước request bằng application properties.

## 7. Nhận multipart request bằng Spring MVC

Spring MVC dùng MultipartFile để nhận nội dung file:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/documents")
class DocumentController {

    private final DocumentService documentService;

    DocumentController(DocumentService documentService) {
        this.documentService = documentService;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(
            operationId = "uploadDocument",
            summary = "Tải tài liệu cùng metadata JSON",
            requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
                    required = true,
                    content = @Content(
                            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
                            schema = @Schema(
                                    implementation = UploadDocumentRequest.class
                            )
                    )
            )
    )
    @ApiResponse(
            responseCode = "201",
            description = "Tài liệu đã được tạo",
            content = @Content(
                    mediaType = MediaType.APPLICATION_JSON_VALUE,
                    schema = @Schema(implementation = DocumentResponse.class)
            )
    )
    ResponseEntity<DocumentResponse> upload(
            @RequestPart("file") MultipartFile file,
            @Valid @RequestPart("metadata") DocumentMetadata metadata) {
        // Kiểm tra file và lưu tài liệu trong service.
        return ResponseEntity.status(201).body(
                documentService.store(file, metadata));
    }
}
~~~

Trong ví dụ, RequestPart("file") nhận part file và RequestPart("metadata") nhận part JSON. Thuộc tính consumes giới hạn operation ở multipart/form-data.

RequestBody annotation trong Operation là annotation OpenAPI của Swagger Core, được viết đầy đủ package để tránh nhầm với RequestBody của Spring. Nó chỉ mô tả hợp đồng; RequestPart của Spring mới quyết định cách bind HTTP request.

## 8. Khai báo response DTO

Ví dụ response sau khi lưu tài liệu:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

@Schema(name = "DocumentResponse", description = "Thông tin tài liệu đã lưu")
public record DocumentResponse(
        @Schema(description = "Mã tài liệu", format = "uuid")
        UUID id,

        @Schema(description = "Tên file gốc")
        String fileName,

        @Schema(description = "Loại nội dung của file")
        String contentType,

        @Schema(description = "Metadata đã lưu")
        DocumentMetadata metadata,

        @Schema(description = "Thời điểm tạo")
        Instant createdAt
) {}
~~~

Response không nên trả byte của file nếu API chỉ xác nhận upload thành công. Nếu client cần tải lại file, tạo endpoint download riêng và mô tả response binary của endpoint đó.

## 9. Xác thực và kiểm tra file

Không tin hoàn toàn tên file hoặc Content-Type do client gửi. Service nên kiểm tra:

- File có tồn tại và không rỗng.
- Kích thước không vượt giới hạn.
- Loại file nằm trong danh sách được chấp nhận.
- Nội dung thực tế phù hợp với loại file nếu yêu cầu nghiệp vụ cần kiểm tra signature.
- Tên file được chuẩn hóa trước khi lưu.
- Metadata hợp lệ và có quyền liên kết với hồ sơ tương ứng.

Ví dụ kiểm tra cơ bản trong service:

~~~java
void validateUpload(MultipartFile file) {
    if (file == null || file.isEmpty()) {
        throw new InvalidUploadException("Tệp không được để trống");
    }

    if (file.getSize() > 10L * 1024 * 1024) {
        throw new UploadTooLargeException("Tệp vượt quá 10 MB");
    }

    String contentType = file.getContentType();
    if (contentType == null ||
            !(contentType.equals("application/pdf")
                    || contentType.equals("image/png"))) {
        throw new UnsupportedUploadTypeException(
                "Chỉ chấp nhận PDF hoặc PNG");
    }
}
~~~

Đây là kiểm tra cơ bản dựa trên metadata request. Với yêu cầu bảo mật cao, cần kiểm tra nội dung file, quét malware và lưu file ngoài thư mục thực thi ứng dụng.

## 10. Cấu hình giới hạn multipart trong Spring MVC

Có thể đặt giới hạn file và toàn bộ request:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 12MB
      file-size-threshold: 1MB
~~~

max-file-size giới hạn một file; max-request-size giới hạn tổng multipart request gồm cả metadata và overhead. Chọn ngưỡng theo nghiệp vụ, bộ nhớ và cấu hình reverse proxy.

Giới hạn của proxy hoặc API gateway có thể thấp hơn giới hạn ứng dụng. Khi nhận 413 Payload Too Large, kiểm tra cả tầng proxy lẫn Spring Boot.

## 11. Biến thể nhận file bằng Spring WebFlux

Spring WebFlux dùng FilePart thay cho MultipartFile. FilePart cho phép xử lý nội dung theo hướng reactive và chuyển file đến đích mà không cần đọc toàn bộ vào byte array.

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/documents")
class ReactiveDocumentController {

    private final ReactiveDocumentService reactiveDocumentService;

    ReactiveDocumentController(ReactiveDocumentService reactiveDocumentService) {
        this.reactiveDocumentService = reactiveDocumentService;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(
            operationId = "uploadDocumentReactive",
            summary = "Tải tài liệu cùng metadata JSON",
            requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
                    required = true,
                    content = @Content(
                            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
                            schema = @Schema(
                                    implementation = UploadDocumentRequest.class
                            )
                    )
            )
    )
    Mono<ResponseEntity<DocumentResponse>> upload(
            @RequestPart("file") FilePart file,
            @Valid @RequestPart("metadata") Mono<DocumentMetadata> metadata) {
        return metadata.flatMap(value ->
                reactiveDocumentService.store(file, value))
                .map(response -> ResponseEntity.status(201).body(response));
    }
}
~~~

FilePart cung cấp tên file, headers và khả năng chuyển nội dung đến đích. Service reactive cần xử lý việc lưu file bất đồng bộ và không chặn event loop bằng thao tác I/O blocking.

Nếu cần gọi thư viện lưu trữ chỉ có API blocking, chuyển thao tác đó sang scheduler phù hợp hoặc dùng client reactive tương ứng. Không gọi trực tiếp thao tác đọc file blocking trên event loop.

## 12. Chọn RequestPart hay RequestParam?

RequestPart phù hợp khi một part có thể được giải mã bằng HttpMessageConverter, ví dụ JSON object:

~~~java
@RequestPart("metadata") DocumentMetadata metadata
~~~

RequestParam thường phù hợp với trường form đơn giản được bind thành String hoặc kiểu scalar:

~~~java
@RequestParam("description") String description
~~~

Không dùng RequestParam cho metadata JSON phức tạp nếu mục tiêu là deserialize part application/json thành DTO. Dùng RequestPart để Spring chọn message converter dựa trên Content-Type của part.

## 13. Gửi request bằng curl

Ví dụ gửi một file PDF cùng metadata JSON:

~~~bash
curl -i -X POST http://localhost:8080/api/documents \
  -F 'file=@./contract.pdf;type=application/pdf' \
  -F 'metadata={"title":"Hợp đồng dịch vụ","category":"LEGAL","referenceCode":"CASE-2026-015"};type=application/json'
~~~

Hai tham số -F tạo hai part riêng. Part file dùng tên file và content type của tệp. Part metadata khai báo type=application/json để Spring có thể chọn JSON message converter.

Không tự đặt header Content-Type tổng thể thành multipart/form-data trong curl nếu không tự tạo boundary. Curl tự tạo boundary và thêm vào Content-Type. Nếu tự ghi đè header mà thiếu boundary, server có thể không parse được multipart body.

## 14. Gửi request bằng Postman

Trong Postman:

1. Chọn method POST và URL /api/documents.
2. Mở tab Body và chọn form-data.
3. Thêm key file, đổi kiểu của key thành File và chọn tệp.
4. Thêm key metadata, để kiểu Text.
5. Nhập JSON metadata vào value của metadata.
6. Đặt Content-Type của part metadata là application/json nếu phiên bản Postman hỗ trợ cấu hình header riêng cho part.
7. Gửi request và kiểm tra status cùng response body.

Nếu Postman gửi metadata dưới dạng text/plain, controller nhận DTO qua RequestPart có thể trả 415 Unsupported Media Type hoặc lỗi chuyển đổi. Kiểm tra header của từng part, không chỉ header tổng thể của request.

## 15. Kiểm tra OpenAPI schema được sinh

Sau khi chạy ứng dụng, tải document:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Kiểm tra request body của operation:

~~~bash
jq '.paths["/api/documents"].post.requestBody.content["multipart/form-data"].schema' openapi.json
~~~

Schema cần có object với hai property file và metadata. Property file cần type string, format binary. Property metadata cần tham chiếu DocumentMetadata hoặc có inline schema tương đương.

Nếu dùng model UploadDocumentRequest trong Operation annotation, kiểm tra component:

~~~bash
jq '.components.schemas.UploadDocumentRequest' openapi.json
jq '.components.schemas.DocumentMetadata' openapi.json
~~~

Kiểm tra cả tên part trong schema và tên trong RequestPart. Hai nơi phải khớp để client sinh từ OpenAPI gửi đúng multipart fields.

## 16. Kiểm tra encoding của metadata part

Khi metadata là JSON, OpenAPI có thể mô tả encoding:

~~~yaml
requestBody:
  content:
    multipart/form-data:
      schema:
        $ref: '#/components/schemas/UploadDocumentRequest'
      encoding:
        metadata:
          contentType: application/json
~~~

Nếu Swagger UI hoặc client generator không hiển thị đúng Content-Type cho part metadata, kiểm tra document có encoding.metadata.contentType hay chưa. Có thể cần tùy biến OpenAPI request body bằng annotation hoặc customizer theo phiên bản springdoc.

Đừng chỉ dựa vào giao diện Swagger UI. OpenAPI JSON là nguồn để xác nhận media type và schema mà consumer thực sự nhận.

## 17. Kiểm thử Spring MVC bằng MockMvc

Với ứng dụng Spring MVC, có thể tạo MockMultipartFile cho từng part:

~~~java
@Test
void uploadAcceptsFileAndJsonMetadata() throws Exception {
    MockMultipartFile file = new MockMultipartFile(
            "file",
            "contract.pdf",
            "application/pdf",
            "sample-pdf-content".getBytes(StandardCharsets.UTF_8));

    MockMultipartFile metadata = new MockMultipartFile(
            "metadata",
            "",
            "application/json",
            """
            {
              "title": "Hợp đồng dịch vụ",
              "category": "LEGAL",
              "referenceCode": "CASE-2026-015"
            }
            """.getBytes(StandardCharsets.UTF_8));

    mockMvc.perform(multipart("/api/documents")
                    .file(file)
                    .file(metadata))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.fileName").value("contract.pdf"))
            .andExpect(jsonPath("$.metadata.category").value("LEGAL"));
}
~~~

Đảm bảo test class đã cấu hình MockMvc và import các static matcher cần thiết. File content trong test chỉ là dữ liệu giả để kiểm tra binding; nếu service đọc nội dung PDF thực, dùng fixture PDF hợp lệ.

## 18. Kiểm thử WebFlux bằng WebTestClient

Với WebFlux, có thể gửi multipart body bằng MultipartBodyBuilder:

~~~java
@Test
void reactiveUploadAcceptsFileAndJsonMetadata() {
    MultipartBodyBuilder builder = new MultipartBodyBuilder();
    builder.part("file", new ByteArrayResource(
                    "sample-content".getBytes(StandardCharsets.UTF_8)) {
                @Override
                public String getFilename() {
                    return "contract.pdf";
                }
            })
            .contentType(MediaType.APPLICATION_PDF);

    builder.part("metadata", """
            {
              "title": "Hợp đồng dịch vụ",
              "category": "LEGAL",
              "referenceCode": "CASE-2026-015"
            }
            """)
            .contentType(MediaType.APPLICATION_JSON);

    webTestClient.post()
            .uri("/api/documents")
            .body(BodyInserters.fromMultipartData(builder.build()))
            .exchange()
            .expectStatus().isCreated();
}
~~~

Test này xác nhận WebFlux nhận được cả hai part với media type tương ứng. Trong ứng dụng thật, thêm assertion response và kiểm tra service lưu file đúng.

## 19. Xử lý lỗi và status code

Một API upload nên định nghĩa response lỗi nhất quán:

| Status | Tình huống |
|---|---|
| 201 Created | File và metadata đã được chấp nhận và lưu |
| 400 Bad Request | Thiếu part, JSON sai cú pháp hoặc validation thất bại |
| 401 Unauthorized | Thiếu thông tin xác thực |
| 403 Forbidden | Người gọi không có quyền upload vào hồ sơ |
| 413 Payload Too Large | File hoặc toàn bộ request vượt giới hạn |
| 415 Unsupported Media Type | Request hoặc part có Content-Type không được hỗ trợ |
| 422 Unprocessable Content | Nội dung file hoặc metadata không thỏa quy tắc nghiệp vụ |

Mô tả các response lỗi bằng ApiResponse để client biết cấu trúc error body. Không để lỗi multipart mặc định trả stack trace hoặc thông tin đường dẫn lưu file nội bộ.

## 20. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| 415 khi gửi metadata | Part metadata là text/plain thay vì application/json | Đặt Content-Type của part thành application/json |
| 400 thiếu part | Tên field client gửi không khớp RequestPart | Đồng bộ tên file/metadata |
| OpenAPI chỉ có file, không có metadata | Springdoc không suy luận đúng part DTO | Mô tả requestBody multipart bằng Schema hoặc customizer |
| Swagger UI không cho nhập JSON metadata | Schema hoặc encoding của multipart chưa rõ | Kiểm tra requestBody schema và encoding |
| 413 dù file dưới giới hạn ứng dụng | Proxy/gateway có giới hạn thấp hơn | Kiểm tra toàn bộ tầng nhận request |
| File rỗng | Client gửi sai field hoặc part không có filename/content | Kiểm tra multipart body và tên part |
| Metadata bind thành String | Dùng RequestParam hoặc sai Content-Type | Dùng RequestPart và application/json |
| MVC chạy nhưng WebFlux lỗi | Dùng MultipartFile trong reactive controller | Dùng FilePart và xử lý I/O reactive |
| WebFlux bị nghẽn khi upload | Thực hiện I/O blocking trên event loop | Dùng thao tác reactive hoặc scheduler phù hợp |
| OpenAPI hiển thị sai tên part | Annotation schema khác RequestPart | Đồng bộ property name và tên part |

## 21. Checklist hoàn tất

- [ ] Endpoint khai báo consumes multipart/form-data.
- [ ] Part file có tên ổn định và được nhận bằng MultipartFile hoặc FilePart.
- [ ] Part metadata có tên ổn định và được nhận thành DTO JSON.
- [ ] Metadata part được gửi với Content-Type application/json.
- [ ] DTO có Bean Validation và schema description phù hợp.
- [ ] OpenAPI requestBody có hai property file và metadata.
- [ ] File schema dùng type string và format binary.
- [ ] Metadata schema tham chiếu đúng component.
- [ ] curl hoặc Postman gửi request thành công.
- [ ] Integration test kiểm tra binding của cả hai part.
- [ ] Kích thước, loại file và quyền upload được kiểm tra.
- [ ] Các response lỗi 400, 413 và 415 được mô tả.

## 22. Nguyên tắc thiết kế

- Dùng multipart/form-data khi request chứa cả file và metadata.
- Dùng RequestPart cho JSON part cần deserialize thành DTO.
- Dùng MultipartFile trong Spring MVC và FilePart trong Spring WebFlux.
- Đặt tên part rõ ràng và đồng bộ giữa controller, OpenAPI schema và client.
- Mô tả file bằng string/binary và metadata bằng JSON schema.
- Gửi đúng Content-Type riêng cho từng part.
- Không tự đặt boundary multipart khi dùng curl hoặc HTTP client.
- Kiểm tra kích thước, loại file, nội dung và quyền truy cập trước khi lưu.
- Với WebFlux, tránh I/O blocking trên event loop.
- Test cả OpenAPI document và request runtime.

## Kết luận

Để tạo request multipart gồm tệp và thông tin JSON, khai báo operation nhận multipart/form-data với hai part có tên ổn định: file và metadata. Spring MVC dùng MultipartFile; Spring WebFlux dùng FilePart. Dùng RequestPart để deserialize metadata part có Content-Type application/json thành DTO, còn schema OpenAPI mô tả file là string/binary và metadata là component schema. Kiểm tra request bằng curl hoặc Postman, xác minh OpenAPI JSON, test binding ở runtime và xử lý giới hạn dung lượng cùng lỗi media type. Khi tài liệu và tên part thống nhất, client có thể tạo request đúng mà không phải suy đoán cấu trúc multipart.

## Tài liệu tham khảo

- [Spring Framework: Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html)
- [Spring Framework: Multipart Content in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html)
- [OpenAPI Specification: Multipart Requests](https://spec.openapis.org/oas/latest.html#special-considerations-for-multipart-content)
- [springdoc-openapi documentation](https://springdoc.org/)
