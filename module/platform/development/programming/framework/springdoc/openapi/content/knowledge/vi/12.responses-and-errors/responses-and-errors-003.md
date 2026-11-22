# Mô tả nhiều phản hồi thành công với nội dung khác nhau

Một operation HTTP có thể trả về nhiều loại phản hồi thành công tùy theo trạng thái xử lý hoặc định dạng mà client yêu cầu. Ví dụ, một lệnh tạo báo cáo có thể trả `200 OK` cùng kết quả nếu xử lý ngay, hoặc `202 Accepted` cùng thông tin tác vụ nếu cần xử lý nền. Một endpoint tải nội dung có thể trả cùng status `200 OK` nhưng body là JSON hoặc PDF tùy theo `Accept` header.

OpenAPI biểu diễn các trường hợp này trong `responses`: mỗi status code là một response riêng; bên trong response, `content` ánh xạ từng media type tới schema tương ứng. Với springdoc-openapi, có thể mô tả các response bằng `@ApiResponses`, `@ApiResponse`, `@Content`, `@Schema` và `@Header`.

Annotation chỉ mô tả hợp đồng. Controller vẫn phải trả đúng status, header, media type và body ở runtime. Vì vậy, sau khi khai báo nhiều phản hồi, cần kiểm tra cả `/v3/api-docs` lẫn các nhánh thực thi thật của endpoint.

## 1. Một operation có thể có nhiều phản hồi thành công

HTTP status code cho biết kết quả xử lý ở mức giao thức. Các mã 2xx không đồng nghĩa với cùng một kiểu body:

| Status | Ý nghĩa thường gặp | Body có thể có |
|---|---|---|
| `200 OK` | Request được xử lý thành công | DTO kết quả, danh sách hoặc nội dung tệp. |
| `201 Created` | Đã tạo tài nguyên | DTO tài nguyên vừa tạo; thường kèm `Location`. |
| `202 Accepted` | Đã tiếp nhận, xử lý chưa hoàn tất | DTO mô tả tác vụ, trạng thái hoặc URL theo dõi. |
| `204 No Content` | Thành công nhưng không trả representation | Không có response body. |

Không khai báo mọi mã 2xx chỉ vì chúng tồn tại trong HTTP. Chỉ mô tả status mà endpoint thực sự có thể trả về. Ví dụ, một thao tác xóa có thể trả `204`; một thao tác tạo có thể trả `201`; một tác vụ chạy nền có thể trả `202`.

OpenAPI cho phép một operation khai báo nhiều response code. Mỗi response code có mô tả, header và content riêng. Client có thể dựa vào status để chọn schema và cách xử lý tiếp theo.

## 2. Khai báo nhiều status code bằng `@ApiResponses`

Giả sử API tạo báo cáo có hai cách xử lý:

- Nếu báo cáo được tạo ngay, trả `200 OK` với `ReportResponse`.
- Nếu cần chạy nền, trả `202 Accepted` với `ReportJobResponse` để client theo dõi tiến trình.

Hai DTO:

```java
public record ReportResponse(
        UUID reportId,
        String downloadUrl,
        Instant generatedAt
) {}

public record ReportJobResponse(
        UUID jobId,
        String status,
        String statusUrl
) {}
```

Controller có thể mô tả rõ từng response:

```java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @PostMapping("/api/reports")
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Báo cáo được tạo ngay",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ReportResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "202",
            description = "Đã tiếp nhận yêu cầu; báo cáo sẽ được tạo ở chế độ nền",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ReportJobResponse.class)
            )
        )
    })
    ResponseEntity<?> createReport(@RequestBody CreateReportRequest request) {
        if (reportService.canGenerateImmediately(request)) {
            ReportResponse result = reportService.generate(request);
            return ResponseEntity.ok(result);
        }

        ReportJobResponse job = reportService.enqueue(request);
        return ResponseEntity.accepted().body(job);
    }
}
```

Trong ví dụ:

- `@ApiResponses` gom các phản hồi của operation.
- Mỗi `@ApiResponse` khai báo một status code và mô tả.
- `@Content` xác định media type của body.
- `@Schema(implementation = ...)` chỉ rõ DTO tương ứng với response đó.
- `ResponseEntity<?>` cho phép method trả các kiểu body khác nhau; `ResponseEntity` quyết định status thực tế ở từng nhánh.

Nếu method luôn trả một kiểu response cố định, không cần dùng wildcard chỉ để làm tài liệu phong phú hơn. Dùng kiểu trả về cụ thể và mô tả những status thực tế có thể xảy ra.

### 2.1. Phân biệt kiểu trả về suy luận và response được khai báo tường minh

Springdoc thường suy luận response thành công mặc định từ kiểu trả về của controller. Ví dụ, method trả `ReportResponse` có thể tạo response `200` với schema `ReportResponse` mà không cần khai báo lại toàn bộ.

Khi một method có nhiều status hoặc nhiều body khác nhau, kiểu trả về Java có thể không thể hiện đủ hợp đồng. Khi đó, khai báo `@ApiResponses` với `responseCode`, `content` và `schema` giúp mô tả từng nhánh rõ ràng.

Nếu vừa dựa vào suy luận vừa khai báo annotation, hãy kiểm tra tài liệu cuối cùng để tránh response trùng, schema mặc định không mong muốn hoặc response code bị mô tả sai. Kết quả gộp annotation và kiểu trả về có thể phụ thuộc phiên bản springdoc/Swagger Core.

## 3. Một status code có nhiều media type

Nhiều trường hợp không cần nhiều status code. Cùng một response `200 OK` có thể có các representation khác nhau theo `Accept` header:

- `application/json`: trả metadata hoặc nội dung có cấu trúc.
- `application/pdf`: trả dữ liệu PDF dạng nhị phân.

Trong OpenAPI, đây là **một response code** với nhiều entry trong `content`. Không tạo hai response `200` riêng chỉ vì có hai media type.

Ví dụ khai báo:

```java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import java.util.UUID;

@GetMapping(
    path = "/api/reports/{id}/content",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_PDF_VALUE
    }
)
@ApiResponse(
    responseCode = "200",
    description = "Nội dung báo cáo theo định dạng được client chấp nhận",
    content = {
        @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ReportMetadata.class)
        ),
        @Content(
            mediaType = MediaType.APPLICATION_PDF_VALUE,
            schema = @Schema(type = "string", format = "binary")
        )
    }
)
ResponseEntity<?> getReportContent(@PathVariable UUID id,
                                   @RequestHeader(HttpHeaders.ACCEPT) String accept) {
    if (accept.contains(MediaType.APPLICATION_PDF_VALUE)) {
        byte[] pdf = reportService.renderPdf(id);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=report.pdf")
                .body(pdf);
    }

    ReportMetadata metadata = reportService.getMetadata(id);
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(metadata);
}
```

`produces` khai báo các media type mà handler có thể tạo ra. `@Content` mô tả schema tương ứng cho từng media type. Với PDF, schema `string` có `format: binary` biểu diễn nội dung tệp.

Trong ứng dụng thực tế, nên dùng content negotiation của Spring và xử lý `Accept` theo quy tắc media type thay vì so sánh chuỗi đơn giản như ví dụ rút gọn trên. Spring có thể trả `406 Not Acceptable` nếu client yêu cầu định dạng không được hỗ trợ.

### 3.1. Hình dạng OpenAPI tương ứng

Phần response trong tài liệu có cấu trúc tương tự:

```yaml
responses:
  '200':
    description: Nội dung báo cáo theo định dạng được client chấp nhận
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ReportMetadata'
      application/pdf:
        schema:
          type: string
          format: binary
```

Client gửi `Accept: application/json` để nhận JSON hoặc `Accept: application/pdf` để nhận PDF. Schema của mỗi media type cho biết cách đọc body sau khi nhận response.

## 4. Kết hợp nhiều status code và nhiều media type

Một operation có thể có cả hai chiều khác nhau:

- `200`: thành công đồng bộ, hỗ trợ JSON hoặc PDF.
- `202`: tác vụ đã được tiếp nhận, trả JSON chứa thông tin job.

Ví dụ cấu trúc OpenAPI:

```yaml
responses:
  '200':
    description: Báo cáo sẵn sàng
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ReportMetadata'
      application/pdf:
        schema:
          type: string
          format: binary
  '202':
    description: Báo cáo đang được tạo
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ReportJobResponse'
```

Annotation tương ứng có thể gom hai response code trong cùng `@ApiResponses`; response `200` chứa hai `@Content`, còn response `202` chứa một `@Content`:

```java
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Báo cáo sẵn sàng",
        content = {
            @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ReportMetadata.class)
            ),
            @Content(
                mediaType = "application/pdf",
                schema = @Schema(type = "string", format = "binary")
            )
        }
    ),
    @ApiResponse(
        responseCode = "202",
        description = "Báo cáo đang được tạo",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ReportJobResponse.class)
        )
    )
})
```

Cách tổ chức này giúp client phân biệt hai quyết định độc lập: status cho biết tiến trình xử lý, còn media type cho biết representation của response body.

## 5. Mô tả response `201 Created` và header `Location`

Khi tạo một tài nguyên mới, `201 Created` thường là status phù hợp. Response có thể chứa DTO tài nguyên và header `Location` trỏ tới URI của tài nguyên vừa tạo.

```java
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import java.net.URI;
import java.util.UUID;

@PostMapping("/api/documents")
@ApiResponse(
    responseCode = "201",
    description = "Tài liệu đã được tạo",
    headers = @Header(
        name = HttpHeaders.LOCATION,
        description = "URI của tài liệu mới",
        schema = @Schema(type = "string", format = "uri")
    ),
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = DocumentResponse.class)
    )
)
ResponseEntity<DocumentResponse> createDocument(
        @RequestBody CreateDocumentRequest request) {
    DocumentResponse created = documentService.create(request);
    URI location = URI.create("/api/documents/" + created.id());
    return ResponseEntity.created(location).body(created);
}
```

`ResponseEntity.created(location)` tạo status `201` và header `Location`. Annotation `@Header` chỉ mô tả header trong OpenAPI; header thực tế phải được method trả về.

Nếu API chỉ trả `201` với body tài nguyên, không cần khai báo thêm `200` chỉ vì springdoc thường suy luận status mặc định. Hãy mô tả đúng status thực tế mà client sẽ nhận.

## 6. Mô tả `204 No Content`

`204 No Content` biểu thị thao tác thành công nhưng không có response body. Không gắn schema JSON cho response này:

```java
@DeleteMapping("/api/documents/{id}")
@ApiResponse(
    responseCode = "204",
    description = "Tài liệu đã được xóa",
    content = @Content
)
ResponseEntity<Void> deleteDocument(@PathVariable UUID id) {
    documentService.delete(id);
    return ResponseEntity.noContent().build();
}
```

`ResponseEntity<Void>` thể hiện method không trả body. `content = @Content` làm rõ response không có representation trong tài liệu. Không khai báo `application/json` cùng `schema` cho response `204`.

Một số method có thể trả `200` với body trạng thái thay vì `204`. Hãy chọn một hợp đồng nhất quán; client cần biết có body để parse hay không.

## 7. Mô tả response dạng danh sách, wrapper hoặc dữ liệu nhị phân

### 7.1. Response là mảng

Nếu response là danh sách, schema có thể là array của một DTO:

```java
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;

@ApiResponse(
    responseCode = "200",
    description = "Danh sách tài liệu",
    content = @Content(
        mediaType = "application/json",
        array = @ArraySchema(
            schema = @Schema(implementation = DocumentResponse.class)
        )
    )
)
```

Với method trả `List<DocumentResponse>`, springdoc thường có thể suy luận schema mảng từ generic. Khai báo `@ArraySchema` tường minh khi cần kiểm soát tài liệu hoặc kiểu trả về Java quá tổng quát.

### 7.2. Response là wrapper phân trang

Nếu ứng dụng trả `PageResponse<DocumentResponse>`, hãy mô tả wrapper và kiểu phần tử cụ thể. Tránh dùng raw `Page` hoặc `Object` nếu consumer cần biết cấu trúc `items`, `page`, `size` và `totalElements`.

```java
public record PageResponse<T>(
        List<T> items,
        int page,
        int size,
        long totalElements
) {}
```

Với generic phức tạp, có thể dùng `@Schema(implementation = ...)` trên response hoặc định nghĩa DTO cụ thể như `DocumentPageResponse`. Schema cụ thể giúp client generator tạo model ổn định hơn.

### 7.3. Response là file

File tải xuống thường được mô tả bằng media type cụ thể và schema nhị phân:

```java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;

@ApiResponse(
    responseCode = "200",
    description = "Tệp PDF đã được tạo",
    content = @Content(
        mediaType = "application/pdf",
        schema = @Schema(type = "string", format = "binary")
    )
)
```

Nếu trả file, kiểm tra `Content-Type` và `Content-Disposition` ở runtime. Nếu cần mô tả `Content-Disposition`, có thể khai báo response header bằng `@Header`.

## 8. Mô tả ví dụ cho từng response

Khi hai response có schema khác nhau, ví dụ mẫu giúp người dùng hiểu cấu trúc cụ thể. Có thể dùng `@ExampleObject` trong `@Content`:

```java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;

@ApiResponse(
    responseCode = "202",
    description = "Đã tiếp nhận yêu cầu tạo báo cáo",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ReportJobResponse.class),
        examples = @ExampleObject(
            name = "reportQueued",
            summary = "Tác vụ đang chờ xử lý",
            value = """
                {
                  "jobId": "b9a8d0c2-4b42-4ad1-91f5-6a6d8d8e1001",
                  "status": "QUEUED",
                  "statusUrl": "/api/report-jobs/b9a8d0c2-4b42-4ad1-91f5-6a6d8d8e1001"
                }
                """
        )
    )
)
```

Ví dụ phải khớp với schema và JSON runtime. Không đưa giá trị giả định như token, ID thật hoặc dữ liệu nhạy cảm vào tài liệu công khai.

## 9. Tách response mô tả khỏi logic runtime

Các annotation `@ApiResponse` và `@ApiResponses` không điều khiển status code mà Spring trả về. Chúng chỉ tạo metadata cho OpenAPI.

Để thực thi nhiều response, controller cần trả đúng kết quả. Các lựa chọn thường gặp:

| Cách triển khai | Khi phù hợp |
|---|---|
| `ResponseEntity<T>` | Cần điều khiển status, header và body cho từng nhánh. |
| `ResponseEntity<?>` hoặc `ResponseEntity<Object>` | Một method thực sự trả các kiểu body khác nhau tùy điều kiện. |
| `@ResponseStatus` | Status cố định cho một method hoặc exception handler. |
| `ResponseEntity<Void>` | Response không có body, ví dụ `204`. |
| `HttpMessageConverter`/content negotiation | Chọn representation dựa trên media type được client chấp nhận. |

Nếu controller luôn trả `ReportResponse` nhưng OpenAPI khai báo `202 ReportJobResponse`, tài liệu sẽ không phản ánh runtime. Ngược lại, nếu method trả `ResponseEntity<?>`, springdoc không thể luôn suy ra đầy đủ từng kiểu body từ generic wildcard; hãy khai báo schema tường minh.

### 9.1. `produces` và `@Content` phải nhất quán

`produces` trên `@GetMapping` hoặc `@RequestMapping` là điều kiện mapping theo media type. `@Content(mediaType = ...)` mô tả representation trong tài liệu. Hai phần phải tương thích:

- Nếu OpenAPI mô tả `application/pdf`, handler phải có khả năng trả PDF với `Content-Type: application/pdf`.
- Nếu handler chỉ `produces = application/json`, không nên mô tả thêm `application/pdf` trong `@Content`.
- Nếu hỗ trợ JSON và PDF, khai báo cả hai trong `produces` và `content`.
- Nếu client yêu cầu media type không được hỗ trợ, có thể trả `406 Not Acceptable`; cân nhắc mô tả response lỗi này nếu đó là hành vi công khai cần tài liệu.

## 10. Kiểm tra tài liệu OpenAPI được sinh ra

Sau khi thêm annotation, mở `/v3/api-docs` hoặc đường dẫn đã cấu hình. Tìm operation tương ứng và kiểm tra:

1. Mỗi status code xuất hiện đúng một lần trong `responses`.
2. Mô tả của từng response đúng với ý nghĩa status.
3. Schema của từng response đúng với DTO hoặc representation runtime.
4. Media type nằm dưới đúng response code.
5. Binary response dùng schema phù hợp, ví dụ `string`/`binary`.
6. Response không body như `204` không có content.
7. Header như `Location` hoặc `Content-Disposition` được mô tả nếu client cần dùng.
8. Không còn response mặc định được suy luận sai hoặc schema không mong muốn.

Ví dụ JSON OpenAPI rút gọn:

```json
{
  "responses": {
    "200": {
      "description": "Báo cáo được tạo ngay",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ReportResponse"
          }
        }
      }
    },
    "202": {
      "description": "Báo cáo sẽ được tạo ở chế độ nền",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ReportJobResponse"
          }
        }
      }
    }
  }
}
```

Tên component có thể khác tùy `@Schema(name = ...)` và cấu hình model. Hãy kiểm tra `$ref` trỏ tới component thực sự tồn tại.

## 11. Kiểm thử tất cả nhánh phản hồi ở runtime

Tài liệu OpenAPI không chứng minh mọi nhánh controller đã hoạt động. Cần viết integration test cho từng status/body quan trọng.

Ví dụ với MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsImmediateReportWhenGenerationIsFast() throws Exception {
        mockMvc.perform(post("/api/reports")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                { "reportType": "SUMMARY", "async": false }
                                """))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.reportId").exists());
    }

    @Test
    void returnsJobWhenGenerationIsQueued() throws Exception {
        mockMvc.perform(post("/api/reports")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                { "reportType": "FULL", "async": true }
                                """))
                .andExpect(status().isAccepted())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.jobId").exists())
                .andExpect(jsonPath("$.status").value("QUEUED"));
    }
}
```

Các request mẫu cần được điều chỉnh theo DTO và logic thực tế của ứng dụng. Nếu dùng mock service, cấu hình rõ từng nhánh để test xác nhận đúng status và schema body.

Với endpoint content negotiation, gửi riêng `Accept: application/json` và `Accept: application/pdf`, rồi kiểm tra `Content-Type` và body. Với `204`, kiểm tra status và xác nhận body rỗng.

## 12. Những lỗi thường gặp

- **Khai báo nhiều `@ApiResponse` cùng response code để mô tả nhiều media type**: một status nên có một response object; đặt nhiều `@Content` bên trong response đó.
- **Dùng nhiều status nhưng schema giống nhau theo kiểu sao chép mặc định**: chỉ rõ `schema = @Schema(implementation = ...)` cho từng response khi body khác nhau.
- **Dựa vào `ResponseEntity<?>` để springdoc tự đoán mọi body**: wildcard không thể hiện đầy đủ kiểu; khai báo schema tường minh.
- **Mô tả `204` có JSON body**: `204 No Content` không có response body.
- **Khai báo `application/pdf` nhưng runtime trả JSON**: đồng bộ `produces`, `Content-Type` và body.
- **Chỉ khai báo annotation mà không đổi controller**: OpenAPI không làm method tự trả `201`, `202` hoặc `204`.
- **Không mô tả header `Location`**: client có thể cần URI tài nguyên mới sau `201`.
- **Quên kiểm tra response mặc định do springdoc suy luận**: đối chiếu JSON cuối cùng để phát hiện schema hoặc status thừa.
- **Chỉ kiểm tra Swagger UI**: đọc `/v3/api-docs` và kiểm thử HTTP runtime.

## 13. Quy trình thiết kế nhiều response thành công

1. **Liệt kê nhánh xử lý**: xác định status code thật sự có thể trả về.
2. **Xác định body cho từng status**: DTO, array, wrapper, binary hoặc không có body.
3. **Xác định media type**: nếu cùng status có nhiều representation, liệt kê từng media type trong `content`.
4. **Khai báo annotation**: dùng `@ApiResponses`, mỗi `@ApiResponse` ứng với một status code; dùng nhiều `@Content` khi một response có nhiều media type.
5. **Mô tả header và ví dụ**: thêm `@Header` hoặc `@ExampleObject` khi cần.
6. **Triển khai controller**: dùng `ResponseEntity` hoặc cơ chế phù hợp để trả đúng status, header và body.
7. **Kiểm tra `/v3/api-docs`**: xác nhận status, schema, media type và header.
8. **Kiểm thử runtime**: bao phủ từng nhánh status và từng định dạng được hỗ trợ.

## 14. Checklist review

- [ ] Mỗi status code mô tả một kết quả thực tế của operation.
- [ ] Mỗi response có description rõ ràng.
- [ ] Schema được khai báo đúng với body của status tương ứng.
- [ ] Một status có nhiều media type được mô tả bằng nhiều `@Content` trong cùng `@ApiResponse`.
- [ ] `produces` khớp với các media type được công bố.
- [ ] Binary response có schema phù hợp và runtime trả đúng content type.
- [ ] Response `201` có `Location` nếu hợp đồng yêu cầu.
- [ ] Response `204` không có body/content.
- [ ] Response wildcard/generic được mô tả schema tường minh khi cần.
- [ ] `/v3/api-docs` không có response trùng hoặc response suy luận sai.
- [ ] Integration test xác minh status, content type, header và body cho từng nhánh.

## 15. Tài liệu tham khảo

- [OpenAPI Specification 3.1.2 – Responses Object](https://spec.openapis.org/oas/v3.1.2.html#responses-object)
- [OpenAPI Specification 3.1.2 – Response Object](https://spec.openapis.org/oas/v3.1.2.html#response-object)
- [OpenAPI Specification 3.1.2 – Media Type Object](https://spec.openapis.org/oas/v3.1.2.html#media-type-object)
- [Swagger Annotations – `@ApiResponse`](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/io/swagger/v3/oas/annotations/responses/ApiResponse.html)
- [Swagger Annotations – `@Content`](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/io/swagger/v3/oas/annotations/media/Content.html)
- [Spring Framework – ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [springdoc-openapi documentation](https://springdoc.org/)

Một operation có thể có nhiều kết quả thành công, nhưng mỗi status và representation phải phản ánh đúng hành vi HTTP thực tế. Dùng một `@ApiResponse` cho mỗi status code, nhiều `@Content` khi response đó hỗ trợ nhiều media type, và kiểm thử mọi nhánh controller để bảo đảm OpenAPI, Swagger UI và client tích hợp cùng hiểu một hợp đồng.
