# Kiểm thử tài liệu cho nhiều loại lỗi

## Mục tiêu học tập

Trong module **SPRING_REST_DOCS**, API không chỉ trả dữ liệu thành công. Client còn cần hiểu cách endpoint phản hồi khi dữ liệu không hợp lệ, chưa xác thực, không đủ quyền, resource không tồn tại, xung đột nghiệp vụ hoặc hệ thống tạm thời không khả dụng. Documentation test cho lỗi phải kiểm tra hành vi HTTP thực tế và sinh snippet mô tả đúng error contract.

Một error response tốt thường có cấu trúc nhất quán: mã lỗi ổn định, thông điệp có thể hiển thị, chi tiết theo field khi phù hợp và thông tin truy vết không nhạy cảm. Mỗi nhóm lỗi có status, header và nội dung riêng; không nên gom tất cả vào một response chung chung mà client không thể xử lý.

Sau bài này, bạn có thể:

- Phân loại các nhóm lỗi API và chọn tình huống cần tài liệu hóa.
- Thiết kế test cho validation, authentication, authorization, not found, conflict, rate limit và server/dependency error.
- Assert status, headers và body trước khi gọi REST Docs.
- Dùng operation ID riêng cho từng error scenario.
- Tái sử dụng descriptor cho error schema chung nhưng vẫn mô tả lỗi đặc thù.
- Dùng MockMvc và WebTestClient để sinh error snippets.
- Tránh đưa stack trace, token, dữ liệu cá nhân hoặc thông tin nội bộ vào tài liệu.

## 1. Vì sao cần tài liệu hóa nhiều loại lỗi?

Nếu tài liệu chỉ có happy path, người tích hợp không biết request thiếu field bắt buộc nhận status nào, token hết hạn khác người dùng không đủ quyền ra sao, resource không tồn tại có cấu trúc response nào, xung đột nghiệp vụ có thể xử lý thế nào, rate limit cung cấp thời điểm retry bằng header nào, hoặc lỗi phụ thuộc bên ngoài có nên retry không.

Tài liệu lỗi giúp client phân biệt lỗi có thể sửa từ request, lỗi quyền truy cập, lỗi trạng thái tài nguyên và lỗi tạm thời. Điều này quan trọng khi API được dùng bởi nhiều ứng dụng hoặc nhóm phát triển.

## 2. Phân loại lỗi theo hợp đồng HTTP

| Nhóm lỗi | Status thường gặp | Ví dụ | Client thường làm gì? |
| --- | --- | --- | --- |
| Validation | 400 hoặc 422 theo quy ước API | Thiếu name, email sai định dạng | Sửa dữ liệu gửi |
| Authentication | 401 Unauthorized | Thiếu token, token hết hạn | Đăng nhập hoặc làm mới credential |
| Authorization | 403 Forbidden | User đã xác thực nhưng không có quyền | Xin quyền hoặc dùng tài nguyên được phép |
| Not found | 404 Not Found | ID không tồn tại | Kiểm tra ID |
| Conflict | 409 Conflict | Trùng mã, trạng thái không cho phép | Tải lại trạng thái hoặc giải quyết xung đột |
| Rate limit | 429 Too Many Requests | Gửi quá nhiều request | Chờ theo retry policy |
| Dependency unavailable | 502/503/504 tùy kiến trúc | Dịch vụ phụ thuộc lỗi/timeout | Retry có giới hạn nếu an toàn |
| Internal error | 500 Internal Server Error | Lỗi không dự kiến | Báo lỗi, gửi correlation ID hỗ trợ |

Đây là các status phổ biến, không phải quy tắc bắt buộc cho mọi API. Exception handler, gateway và chính sách API có thể ánh xạ exception khác nhau. Documentation test phải kiểm tra response mà client thực sự nhận được.

## 3. Thiết kế error response nhất quán

Một schema lỗi minh họa:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request không hợp lệ",
  "details": [
    {
      "field": "name",
      "reason": "must not be blank"
    }
  ],
  "traceId": "test-trace-001"
}
```

| Field | Vai trò | Lưu ý hợp đồng |
| --- | --- | --- |
| code | Mã lỗi ổn định cho máy xử lý | Không phụ thuộc ngôn ngữ hiển thị |
| message | Thông điệp thân thiện | Có thể được bản địa hóa |
| details | Chi tiết theo field hoặc nguyên nhân | Cấu trúc thay đổi theo loại lỗi |
| traceId | Mã truy vết hỗ trợ | Không chứa stack trace hoặc bí mật |

API cũng có thể dùng RFC 9457 Problem Details với media type application/problem+json. Các field chuẩn gồm type, title, status, detail và instance; extension members có thể bổ sung code hoặc errors. Hãy tài liệu hóa đúng format ứng dụng thực sự dùng, không trộn hai schema.

### 3.1. Error code nên ổn định

Client nên dựa vào code máy đọc được thay vì phân tích message tự nhiên. Ví dụ: VALIDATION_ERROR, UNAUTHENTICATED, ACCESS_DENIED, PRODUCT_NOT_FOUND, PRODUCT_ALREADY_EXISTS, RATE_LIMIT_EXCEEDED và DEPENDENCY_UNAVAILABLE. Dự án nên duy trì danh mục code nhất quán.

## 4. Test validation error

Giả sử endpoint tạo sản phẩm nhận name bắt buộc:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "name": " ",
                  "price": 129.90
                }
                """))
    .andExpect(status().isBadRequest())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
    .andExpect(jsonPath("$.details[*].field").value(hasItem("name")))
    .andDo(document("products-create-validation-error",
        responseFields(
            fieldWithPath("code").description("Mã lỗi validation."),
            fieldWithPath("message").description("Thông điệp lỗi."),
            fieldWithPath("details").description("Danh sách chi tiết lỗi."),
            fieldWithPath("details[].field").description("Field không hợp lệ."),
            fieldWithPath("details[].reason").description("Lý do field không hợp lệ."),
            fieldWithPath("traceId").description("Mã truy vết request.")
        )));
```

Test kiểm tra status, Content-Type, error code và chi tiết chỉ ra field name. Descriptor phải khớp payload thật. Nếu ứng dụng trả violations[].message thay vì details[].reason, dùng path thực tế.

## 5. Test authentication error

Request chưa được xác thực hợp lệ có thể trả 401:

```java
this.mockMvc.perform(get("/api/me"))
    .andExpect(status().isUnauthorized())
    .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"))
    .andDo(document("profile-unauthenticated",
        responseFields(
            fieldWithPath("code").description("Mã lỗi xác thực."),
            fieldWithPath("message").description("Thông điệp lỗi."),
            fieldWithPath("traceId").description("Mã truy vết.")
        )));
```

Nếu authentication scheme yêu cầu challenge header, kiểm tra nó:

```java
.andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        startsWith("Bearer")
))
```

401 biểu thị request chưa được xác thực hợp lệ. Đừng dùng 403 cho mọi lỗi token nếu hợp đồng phân biệt authentication và authorization. Không dùng token thật trong test hoặc snippet.

## 6. Test authorization error

Người dùng đã đăng nhập nhưng không có quyền thường nhận 403:

```java
this.mockMvc.perform(get("/api/admin/reports")
        .with(user("reader").roles("USER")))
    .andExpect(status().isForbidden())
    .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
    .andDo(document("admin-reports-forbidden",
        responseFields(
            fieldWithPath("code").description("Mã lỗi phân quyền."),
            fieldWithPath("message").description("Thông điệp lỗi.")
        )));
```

Test nên tạo principal có quyền xác định, không phụ thuộc user thật hoặc role của môi trường. Nếu API cố ý không tiết lộ resource có tồn tại hay không, status có thể là 404 theo chính sách; tài liệu phải phản ánh đúng hành vi đã chọn.

## 7. Test not found

```java
this.mockMvc.perform(get("/api/products/{id}", 9999))
    .andExpect(status().isNotFound())
    .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"))
    .andExpect(jsonPath("$.message").isNotEmpty())
    .andDo(document("products-get-not-found",
        responseFields(
            fieldWithPath("code").description("Mã lỗi không tìm thấy sản phẩm."),
            fieldWithPath("message").description("Thông điệp lỗi."),
            fieldWithPath("traceId").description("Mã truy vết request.")
        )));
```

Không chỉ kiểm tra status. Error code giúp client phân biệt product không tồn tại với các lỗi 404 khác nếu ứng dụng dùng chung status cho nhiều nguyên nhân.

## 8. Test conflict và lỗi trạng thái nghiệp vụ

Ví dụ SKU đã tồn tại:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "sku": "KB-001",
                  "name": "Keyboard"
                }
                """))
    .andExpect(status().isConflict())
    .andExpect(jsonPath("$.code").value("PRODUCT_ALREADY_EXISTS"))
    .andDo(document("products-create-conflict",
        responseFields(
            fieldWithPath("code").description("Mã lỗi xung đột."),
            fieldWithPath("message").description("Thông điệp lỗi.")
        )));
```

Conflict thường có thể được giải quyết bằng cách tải lại trạng thái hoặc chọn dữ liệu khác. Error message nên hướng dẫn đủ để client hiểu vấn đề nhưng không tiết lộ dữ liệu nội bộ.

## 9. Test rate limit và retry headers

Nếu API áp dụng giới hạn request, response 429 có thể kèm Retry-After:

```java
this.mockMvc.perform(get("/api/reports")
        .header("X-Test-Rate-Limit", "exceeded"))
    .andExpect(status().isTooManyRequests())
    .andExpect(header().exists(HttpHeaders.RETRY_AFTER))
    .andExpect(jsonPath("$.code").value("RATE_LIMIT_EXCEEDED"))
    .andDo(document("reports-rate-limited",
        responseHeaders(
            headerWithName(HttpHeaders.RETRY_AFTER)
                .description("Thời điểm hoặc khoảng thời gian client nên chờ trước khi thử lại.")
        ),
        responseFields(
            fieldWithPath("code").description("Mã lỗi giới hạn request."),
            fieldWithPath("message").description("Thông điệp lỗi.")
        )));
```

Retry-After có thể biểu diễn số giây hoặc HTTP-date. Test nên xác minh format/giá trị mà API cam kết. Header X-Test-Rate-Limit chỉ là cách giả lập test, không nên trở thành production contract.

## 10. Test lỗi server và dependency

Lỗi không dự kiến thường trả 500; lỗi gateway hoặc dependency có thể được ánh xạ sang 502, 503 hoặc 504 tùy kiến trúc.

```java
when(inventoryClient.findStock(501))
    .thenThrow(new InventoryUnavailableException());

this.mockMvc.perform(get("/api/products/{id}/availability", 501))
    .andExpect(status().isServiceUnavailable())
    .andExpect(jsonPath("$.code").value("DEPENDENCY_UNAVAILABLE"))
    .andDo(document("product-availability-unavailable",
        responseFields(
            fieldWithPath("code").description("Mã lỗi dependency."),
            fieldWithPath("message").description("Thông điệp lỗi."),
            fieldWithPath("traceId").description("Mã truy vết.")
        )));
```

Test nên xác minh exception handler che giấu chi tiết nội bộ. Không đưa hostname nội bộ, câu SQL, stack trace hoặc credential vào error body được tài liệu hóa.

## 11. Dùng RFC 9457 Problem Details

Nếu ứng dụng chuẩn hóa lỗi bằng Problem Details:

```json
{
  "type": "https://api.example.test/problems/product-not-found",
  "title": "Product not found",
  "status": 404,
  "detail": "Không tìm thấy sản phẩm được yêu cầu.",
  "instance": "/api/products/9999",
  "code": "PRODUCT_NOT_FOUND"
}
```

Test:

```java
this.mockMvc.perform(get("/api/products/{id}", 9999))
    .andExpect(status().isNotFound())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(jsonPath("$.status").value(404))
    .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"))
    .andDo(document("products-get-not-found",
        responseFields(
            fieldWithPath("type").description("URI định danh loại vấn đề."),
            fieldWithPath("title").description("Tiêu đề ngắn của vấn đề."),
            fieldWithPath("status").description("HTTP status của vấn đề."),
            fieldWithPath("detail").description("Giải thích cụ thể cho lần xảy ra này."),
            fieldWithPath("instance").description("URI tham chiếu lần xảy ra."),
            fieldWithPath("code").description("Mã lỗi ổn định của API.")
        )));
```

Ví dụ có extension member code. Nếu payload có field mở rộng hoặc field tùy chọn khác, descriptor phải phản ánh schema thật; không sao chép ví dụ mà chưa kiểm tra response.

## 12. Tái sử dụng descriptor cho error schema chung

Nhiều operation có thể dùng chung cấu trúc error response:

```java
private static final FieldDescriptor[] BASIC_ERROR_FIELDS = {
    fieldWithPath("code").description("Mã lỗi ổn định."),
    fieldWithPath("message").description("Thông điệp lỗi."),
    fieldWithPath("traceId").description("Mã truy vết request.")
};
```

Dùng cho operation not found:

```java
responseFields(BASIC_ERROR_FIELDS)
```

Validation error có thể mở rộng descriptor:

```java
responseFields(
    fieldWithPath("code").description("Mã lỗi."),
    fieldWithPath("message").description("Thông điệp lỗi."),
    fieldWithPath("traceId").description("Mã truy vết."),
    fieldWithPath("details").description("Danh sách lỗi theo field."),
    fieldWithPath("details[].field").description("Field không hợp lệ."),
    fieldWithPath("details[].reason").description("Lý do không hợp lệ.")
)
```

Không tái sử dụng một descriptor array cho mọi loại lỗi nếu schema thực tế khác nhau. Strict REST Docs sẽ phát hiện sự khác biệt; hãy tách base descriptor và phần mở rộng theo loại response.

## 13. Operation ID riêng cho từng loại lỗi

Mỗi response có status/schema khác nhau nên có operation ID riêng:

| Loại lỗi | Operation ID gợi ý |
| --- | --- |
| Validation | products-create-validation-error |
| Unauthenticated | profile-unauthenticated |
| Forbidden | admin-reports-forbidden |
| Not found | products-get-not-found |
| Conflict | products-create-conflict |
| Rate limit | reports-rate-limited |
| Dependency unavailable | product-availability-unavailable |

Ví dụ include:

```asciidoc
== Lấy sản phẩm thành công
include::{snippets}/products-get/http-response.adoc[]
include::{snippets}/products-get/response-fields.adoc[]

== Không tìm thấy sản phẩm
include::{snippets}/products-get-not-found/http-response.adoc[]
include::{snippets}/products-get-not-found/response-fields.adoc[]
```

Không dùng chung operation ID cho success 200 và not found 404. Các file http-response.adoc hoặc response-fields.adoc có thể bị ghi đè.

## 14. Dùng WebTestClient cho reactive error

WebFlux endpoint có thể phát lỗi từ publisher:

```java
when(productService.findById(9999))
    .thenReturn(Mono.error(new ProductNotFoundException(9999)));

this.webTestClient.get()
    .uri("/api/products/{id}", 9999)
    .exchange()
    .expectStatus().isNotFound()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.code").isEqualTo("PRODUCT_NOT_FOUND")
    .consumeWith(document("products-get-not-found",
        responseFields(
            fieldWithPath("code").description("Mã lỗi."),
            fieldWithPath("message").description("Thông điệp lỗi.")
        )));
```

WebTestClient đợi response từ publisher và cho phép assert status/header/body trước khi document. Error response thông thường nên là body hữu hạn.

## 15. An toàn dữ liệu trong error snippets

Trước khi lưu snippet, kiểm tra:

- Không có access token, refresh token, session ID hoặc cookie thật.
- Không có password, API key, secret hoặc authorization header thật.
- Không có stack trace, câu SQL, đường dẫn file nội bộ hoặc hostname nội bộ.
- Không có email, số điện thoại, địa chỉ hoặc dữ liệu cá nhân thật nếu không cần thiết.
- Trace ID trong fixture là giá trị giả.
- Error message không tiết lộ sự tồn tại của tài khoản hoặc resource ngoài chính sách bảo mật.

REST Docs ghi lại exchange đã kiểm thử; nó không tự động che mọi dữ liệu nhạy cảm. Dùng fixture giả và kiểm tra snippet output trước khi publish.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Error test nhận 200 thay vì 400 | Validation chưa bật hoặc exception handler xử lý sai | Kiểm tra @Valid, provider và controller advice |
| 401 và 403 bị dùng lẫn | Nhầm authentication với authorization | Xác định trạng thái principal và hợp đồng security |
| Error code không ổn định | Dùng message để client suy luận | Công bố code máy đọc được |
| Descriptor error không khớp | Response schema khác ví dụ | Đối chiếu payload thực tế và sửa field path |
| Error response chứa stack trace | Exception handler trả chi tiết nội bộ | Chuẩn hóa public error body |
| Rate-limit test phụ thuộc thời gian | Dùng limiter thật hoặc clock không cố định | Mock policy/clock hoặc dùng test configuration |
| Snippet lỗi bị ghi đè | Nhiều error case dùng cùng operation ID | Tách operation ID |
| Test chỉ kiểm tra status | Không xác minh code/details/header | Assert error body và metadata quan trọng |
| Tài liệu có token thật | Fixture lấy từ môi trường thật | Thay bằng dữ liệu giả và rà snippet |
| 503 bị coi là retry vô hạn | Không có retry policy rõ ràng | Tài liệu retry limit/backoff và idempotency |

## 17. Bài thực hành

1. Tạo error response schema thống nhất với code, message và traceId.
2. Viết documentation test validation error cho POST /api/products; assert 400 và field lỗi.
3. Viết test 401 cho request thiếu token và 403 cho user không đủ role.
4. Viết test 404 cho product ID không tồn tại.
5. Viết test 409 cho SKU trùng.
6. Viết test 429 có Retry-After nếu API hỗ trợ rate limit.
7. Viết test 503 cho dependency unavailable và xác minh error body không lộ chi tiết nội bộ.
8. Dùng operation ID riêng cho từng error scenario và include snippet vào phần Error responses.
9. Kiểm tra generated snippets để chắc chắn không có credential hoặc dữ liệu cá nhân.

**Câu hỏi tự đánh giá**

1. Validation error khác business conflict như thế nào?
2. Khi nào nên trả 401 và khi nào nên trả 403?
3. Vì sao error code ổn định hữu ích hơn việc client phân tích message?
4. Retry-After hỗ trợ client xử lý 429 như thế nào?
5. Vì sao không dùng chung operation ID cho success và error response?
6. Khi nào RFC 9457 Problem Details phù hợp?
7. Những thông tin nào không nên xuất hiện trong error snippet?
8. Vì sao cần assertion error body bên cạnh status assertion?

## Tài liệu tham khảo chính thức

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): tạo snippet từ HTTP test.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): mô tả error response fields.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): xử lý lỗi REST và Problem Details.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): định dạng response lỗi chuẩn hóa.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ý nghĩa status code và HTTP headers.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): kiểm thử authentication và authorization trong Spring Security.

**Kết luận thực hành:** Tài liệu hóa các loại lỗi công khai mà client cần xử lý: validation, authentication, authorization, not found, conflict, rate limit và lỗi dependency/server. Mỗi test phải assert status, header và error body theo hợp đồng trước khi REST Docs tạo snippet. Dùng error code ổn định, operation ID riêng, descriptor đúng schema và fixture không chứa bí mật để tài liệu lỗi có thể dùng an toàn trong tích hợp thực tế.
