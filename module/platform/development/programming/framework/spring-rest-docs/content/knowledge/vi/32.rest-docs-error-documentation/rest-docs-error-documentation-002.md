# Response fields cho error payload

## 1. Vì sao cần tài liệu hóa error response?

Trong module **SPRING_REST_DOCS**, Spring REST Docs tạo tài liệu REST API từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Tài liệu cần mô tả cả response thành công lẫn lỗi xác thực, validation, không tìm thấy tài nguyên, conflict, rate limit và lỗi server.

Một error response có thể chứa status, mã lỗi ổn định, thông điệp, danh sách field validation, correlation ID và liên kết hỗ trợ. Nếu chỉ ghi 400 Bad Request mà không mô tả body, client phải đoán cấu trúc lỗi.

Ví dụ payload:

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request không hợp lệ",
  "status": 400,
  "detail": "Một hoặc nhiều field không đáp ứng quy tắc kiểm tra.",
  "instance": "/api/accounts",
  "code": "VALIDATION_ERROR",
  "violations": [
    {
      "field": "email",
      "code": "INVALID_FORMAT",
      "message": "Email không đúng định dạng."
    }
  ]
}
```

Spring REST Docs dùng responseFields(...) và fieldWithPath(...) để mô tả từng field. Khi test gọi document(...), REST Docs kiểm tra payload theo descriptor và sinh snippet response-fields.adoc. Nhờ vậy tài liệu lỗi được xác minh bằng response thực tế trong test.

## 2. Chọn cấu trúc error payload

Trước khi viết descriptor, xác định API dùng chuẩn lỗi chung hay schema riêng.

### 2.1. Problem Details theo RFC 9457

Problem Details cung cấp cấu trúc chuẩn cho lỗi HTTP:

| Field | Ý nghĩa |
| --- | --- |
| type | URI định danh loại vấn đề; mặc định có thể là about:blank |
| title | Tóm tắt loại vấn đề |
| status | HTTP status tương ứng |
| detail | Giải thích cụ thể cho lần xảy ra vấn đề |
| instance | URI tham chiếu tới lần xảy ra vấn đề |

Ứng dụng có thể thêm extension members như code, violations, traceId hoặc errors. Các extension phải được mô tả trong contract.

Ví dụ:

```json
{
  "type": "https://api.example.com/problems/not-found",
  "title": "Không tìm thấy tài nguyên",
  "status": 404,
  "detail": "Không tìm thấy đơn hàng ORD-42.",
  "instance": "/api/orders/ORD-42",
  "code": "ORDER_NOT_FOUND"
}
```

Không nhầm HTTP status line với field status trong body. Test cần kiểm tra cả hai nếu contract yêu cầu chúng đồng nhất. Không phải API nào cũng dùng mọi member hoặc extension; chỉ mô tả field thuộc response thực tế.

### 2.2. Schema lỗi riêng

API có thể dùng envelope riêng:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Dữ liệu gửi lên không hợp lệ.",
    "timestamp": "2026-11-17T08:30:00Z",
    "correlationId": "req-123"
  },
  "fieldErrors": [
    {
      "field": "email",
      "rejectedValue": "not-an-email",
      "reason": "INVALID_FORMAT"
    }
  ]
}
```

Schema này cũng được mô tả bằng responseFields(...). Dùng JSON path đúng với payload thật, không ép schema riêng thành Problem Details nếu server không triển khai chuẩn đó.

## 3. Khai báo responseFields cho error payload

Descriptor cho Problem Details response:

```java
responseFields(
    fieldWithPath("type").description("URI định danh loại vấn đề"),
    fieldWithPath("title").description("Tiêu đề ngắn mô tả loại lỗi"),
    fieldWithPath("status").description("HTTP status trong payload"),
    fieldWithPath("detail").description("Giải thích cho lần xảy ra lỗi"),
    fieldWithPath("instance").description("URI tham chiếu tới lần xảy ra lỗi"),
    fieldWithPath("code").description("Mã lỗi ổn định để client xử lý")
)
```

responseFields(...) mô tả body. Nó không tự mô tả status line hoặc header. Nếu client cần biết status, Content-Type, Retry-After hoặc WWW-Authenticate, dùng http-response.adoc và responseHeaders(...).

Mỗi descriptor phải phản ánh field có trong payload. Nếu response có extension field chưa khai báo, strict payload documentation sẽ báo lỗi khi test chạy.

## 4. Required, optional và nullable

Không phải field nào cũng luôn có mặt. Spring REST Docs cho phép đánh dấu field optional:

```java
responseFields(
    fieldWithPath("type").description("URI định danh loại vấn đề"),
    fieldWithPath("title").description("Tiêu đề loại vấn đề"),
    fieldWithPath("status").description("HTTP status"),
    fieldWithPath("detail").description("Giải thích lỗi"),
    fieldWithPath("instance").optional()
        .description("URI tham chiếu tới lần xảy ra lỗi, nếu có")
)
```

Phân biệt:
- **Required:** key phải xuất hiện trong JSON.
- **Optional:** key có thể vắng mặt.
- **Nullable:** key xuất hiện nhưng giá trị có thể là JSON null.
- **Empty:** key có giá trị chuỗi rỗng, array rỗng hoặc object rỗng tùy schema.

optional() nói về việc field có thể không xuất hiện. Nó không đồng nghĩa nullable. Nếu field bắt buộc nhưng cho phép null, mô tả semantics và test trường hợp null; không đánh dấu optional chỉ để làm test qua.

## 5. Mô tả nested field errors

Validation error thường có danh sách lỗi theo từng field. Dùng JSON path của array:

```java
responseFields(
    fieldWithPath("code").description("Mã lỗi tổng thể"),
    fieldWithPath("violations").description("Danh sách vi phạm validation"),
    fieldWithPath("violations[].field").description("Tên field không hợp lệ"),
    fieldWithPath("violations[].code").description("Mã lỗi ổn định của field"),
    fieldWithPath("violations[].message").description("Thông điệp giải thích lỗi")
)
```

| Path | Ý nghĩa |
| --- | --- |
| violations | Danh sách vi phạm |
| violations[].field | Tên field |
| violations[].code | Mã lỗi |
| violations[].message | Thông điệp cho client/người dùng |

Object lồng nhiều cấp dùng path đầy đủ như error.code, error.message hoặc violations[].arguments[].name. Path descriptor là path JSON, không phải tên property Java nếu serializer đổi tên.

Nếu array có thể rỗng, descriptor vẫn mô tả phần tử khi xuất hiện. Nên có test với ít nhất một phần tử để REST Docs xác minh nested paths; test riêng có thể xác minh array rỗng là response hợp lệ.

## 6. rejectedValue và dữ liệu nhạy cảm

Error payload đôi khi trả rejectedValue để client hiển thị lỗi. Điều này hữu ích với dữ liệu vô hại nhưng nguy hiểm nếu field là password, token hoặc secret.

Payload an toàn hơn:

```json
{
  "field": "email",
  "code": "INVALID_FORMAT",
  "message": "Email không đúng định dạng."
}
```

Nếu contract có rejectedValue, quyết định field nào được phép phản hồi. Không trả password hoặc token đã nhập. Test HTTP cần xác minh dữ liệu nhạy cảm thực sự vắng khỏi response; chỉ mask trong snippet là chưa đủ.

Với field được phép trả, dùng fixture giả ổn định:

```java
fieldWithPath("violations[].rejectedValue").optional()
    .description("Giá trị bị từ chối nếu contract cho phép hiển thị")
```

Tài liệu nên nói rõ client không nên phụ thuộc rejectedValue nếu server có thể bỏ field hoặc che giá trị theo loại dữ liệu.

## 7. Kết hợp responseFields với responseHeaders

Error contract không chỉ có body. Một số header ảnh hưởng cách client xử lý lỗi:

- Content-Type: định dạng error representation, ví dụ application/problem+json.
- Retry-After: thời điểm hoặc khoảng chờ trước khi retry.
- WWW-Authenticate: challenge xác thực khi nhận 401.
- X-Request-Id hoặc Trace-Id: mã truy vết.
- Location: URI liên quan nếu contract quy định.

Ví dụ:

```java
.andDo(document("orders-not-found",
    responseHeaders(
        headerWithName("Content-Type")
            .description("Media type của error response"),
        headerWithName("X-Request-Id").optional()
            .description("Mã truy vết request nếu được cung cấp")
    ),
    responseFields(
        fieldWithPath("type").description("URI loại vấn đề"),
        fieldWithPath("title").description("Tiêu đề lỗi"),
        fieldWithPath("status").description("HTTP status"),
        fieldWithPath("detail").description("Chi tiết lỗi"),
        fieldWithPath("code").description("Mã lỗi ứng dụng")
    )
))
```

responseHeaders(...) và responseFields(...) tạo snippet riêng. Tài liệu nên include cả hai nếu client cần header và body để xử lý lỗi.

## 8. Strict và relaxed response field documentation

Mặc định responseFields(...) kiểm tra payload nghiêm ngặt: field trong payload cần được mô tả và descriptor phải khớp nội dung thực tế. Đây là lựa chọn tốt để phát hiện field mới hoặc schema thay đổi mà tài liệu chưa cập nhật.

Dùng relaxedResponseFields(...) khi chỉ muốn mô tả một phần payload và chấp nhận field khác chưa liệt kê:

```java
relaxedResponseFields(
    fieldWithPath("type").description("URI loại vấn đề"),
    fieldWithPath("title").description("Tiêu đề lỗi"),
    fieldWithPath("status").description("HTTP status")
)
```

Relaxed mode hữu ích với envelope lớn hoặc khi tài liệu chỉ tập trung một phần. Nhưng nếu dùng cho toàn bộ error contract, field mới có thể xuất hiện mà không được mô tả. Ưu tiên strict descriptors cho response public ổn định; dùng relaxed có chủ đích và nói rõ snippet chỉ bao phủ một phần.

Phân biệt relaxedResponseFields với subsectionWithPath: subsection mô tả một vùng object/array như một khối; relaxed mode cho phép bỏ qua field không liệt kê.

## 9. Ví dụ MockMvc: document validation error

Ví dụ dùng controller advice ánh xạ validation exception thành payload có code và violations. Test gửi request không hợp lệ, kiểm tra HTTP response gốc rồi sinh response fields snippet.

```java
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ValidationErrorDocumentationTest {
    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new AccountController())
                .setControllerAdvice(new ApiErrorAdvice())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void documentsInvalidEmailResponse() throws Exception {
        mockMvc.perform(post("/api/accounts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                            {"email":"not-an-email"}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.violations[0].field").value("email"))
                .andDo(document("accounts-create-validation-error",
                        responseFields(
                                fieldWithPath("code").description("Mã lỗi tổng thể"),
                                fieldWithPath("message").description("Thông điệp tổng quát"),
                                fieldWithPath("violations").description("Danh sách field vi phạm"),
                                fieldWithPath("violations[].field").description("Tên field"),
                                fieldWithPath("violations[].code").description("Mã lỗi validation"),
                                fieldWithPath("violations[].message").description("Mô tả lỗi của field")
                        )
                ));
    }

    record CreateAccountRequest(@NotBlank @Email String email) {}

    @RestController
    static class AccountController {
        @PostMapping("/api/accounts")
        ResponseEntity<Void> create(@Valid @RequestBody CreateAccountRequest request) {
            return ResponseEntity.noContent().build();
        }
    }

    @RestControllerAdvice
    static class ApiErrorAdvice {
        @ExceptionHandler(MethodArgumentNotValidException.class)
        ResponseEntity<Map<String, Object>> invalid(
                MethodArgumentNotValidException exception) {
            List<Map<String, String>> violations =
                    exception.getBindingResult().getFieldErrors().stream()
                            .map(error -> Map.of(
                                    "field", error.getField(),
                                    "code", "INVALID_FORMAT",
                                    "message", "Giá trị không hợp lệ"))
                            .toList();

            return ResponseEntity.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of(
                            "code", "VALIDATION_ERROR",
                            "message", "Request không hợp lệ",
                            "violations", violations
                    ));
        }
    }
}
```

Đây là ví dụ minh họa. Trong dự án thật, error code nên được ánh xạ theo constraint/domain thay vì gán cứng INVALID_FORMAT cho mọi lỗi. Có thể dùng FieldError.getCode() hoặc mã domain ổn định. Cần dependency Bean Validation provider để @Valid được thực thi.

Với Spring Boot application context, nên test controller advice và validation configuration thực tế. Standalone MockMvc cần đăng ký advice và bảo đảm validator được cấu hình nếu setup không tự phát hiện provider.

## 10. Document nhiều loại error response

Một API thường có nhiều nhóm lỗi:

| Scenario | HTTP status | Ví dụ error code |
| --- | --- | --- |
| JSON không parse được | 400 | MALFORMED_JSON |
| Field validation thất bại | 400 hoặc 422 theo contract | VALIDATION_ERROR |
| Chưa xác thực | 401 | UNAUTHENTICATED |
| Không đủ quyền | 403 | FORBIDDEN |
| Không tìm thấy resource | 404 | RESOURCE_NOT_FOUND |
| Conflict trạng thái | 409 | STATE_CONFLICT |
| Quá nhiều request | 429 | RATE_LIMITED |
| Lỗi server | 500 | INTERNAL_ERROR |
| Dịch vụ tạm không sẵn sàng | 503 | SERVICE_UNAVAILABLE |

Dùng snippet identifier riêng:

```java
document("accounts-create-validation-error")
document("accounts-get-unauthenticated")
document("orders-get-not-found")
document("orders-cancel-conflict")
document("orders-get-rate-limited")
```

Không gom mọi lỗi vào một snippet nếu payload hoặc header khác nhau. Tách theo outcome giúp client thấy status, code, field và retry behavior đúng từng trường hợp.

## 11. Tổ chức error snippets trong Asciidoctor

Generated snippet cho operation accounts-create-validation-error có thể include:

```adoc
= Account API

== Lỗi khi tạo tài khoản

=== HTTP response
include::${snippets}/accounts-create-validation-error/http-response.adoc[]

=== Error response fields
include::${snippets}/accounts-create-validation-error/response-fields.adoc[]
```

Tiêu đề section nên nói rõ status và outcome, ví dụ “400 — Request không hợp lệ”, thay vì chỉ ghi “Error”.

Khi schema lỗi dùng chung, mô tả envelope một lần và include snippet cụ thể cho từng operation. Mỗi operation vẫn cần ghi status, code và field khác biệt.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| responseFields báo undocumented field | Payload có field chưa khai báo | Thêm descriptor hoặc relaxed có chủ đích |
| Snippet thiếu nested violation | Chưa khai báo JSON path array | Dùng violations[].field và path con |
| Field optional bị coi là required | Quên optional() | Đánh dấu optional đúng contract |
| Dùng optional cho nullable | Nhầm key vắng với key null | Mô tả/test nullable riêng |
| Dùng request descriptor cho error body | Nhầm chiều payload | Dùng responseFields |
| Chỉ tài liệu hóa status, bỏ body | Không mô tả error schema | Include response-fields.adoc |
| Dùng relaxed cho mọi lỗi | Không phát hiện field mới | Ưu tiên strict với contract public |
| status body khác HTTP status | Mapping exception không nhất quán | Assert cả status line và body |
| rejectedValue làm lộ dữ liệu | Trả password/token trong error | Loại khỏi response và test absence |
| Error code thay đổi theo exception class | Dùng mã framework không ổn định | Ánh xạ sang domain code ổn định |
| Error response sai Content-Type | Advice không đặt media type | Kiểm tra header và contract |
| Snippet cũ còn trong docs | Test không chạy trước Asciidoctor | Thiết lập task dependency |

## 13. Bài thực hành

Dùng endpoint POST /api/accounts và GET /api/orders/{id}:

1. Tạo validation error response có code, message và violations.
2. Dùng responseFields(...) mô tả envelope và các path violations[].
3. Bỏ một field khỏi descriptor để quan sát strict mode báo undocumented field.
4. Đánh dấu instance optional; test cả trường hợp có và không có key.
5. Tạo trường hợp JSON null để phân biệt nullable với optional.
6. Thêm response header Content-Type và X-Request-Id bằng responseHeaders(...).
7. Tạo Problem Details response cho 404 và mô tả member chuẩn cùng extension code.
8. Tạo 401, 403, 409 và 429; dùng snippet identifier riêng theo operation/outcome.
9. Thêm rejectedValue giả, sau đó xác nhận password/token không xuất hiện trong HTTP response thật.
10. Include error response và response fields vào Asciidoctor; chạy documentation tests trước render.

**Tiêu chí hoàn thành:** bạn mô tả được error payload bằng responseFields, khai báo nested JSON paths, phân biệt required/optional/nullable, chọn strict hoặc relaxed có chủ đích, kiểm chứng HTTP status/header/body và tổ chức snippets lỗi theo từng operation/outcome.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): responseFields, field descriptors và relaxed payload documentation.
- [Spring REST Docs — Response Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/headers.html): mô tả response headers.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): cấu trúc Problem Details và extension members.
- [Spring Framework — @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): ánh xạ exception thành HTTP error response.
