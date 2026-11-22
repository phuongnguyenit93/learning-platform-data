# Document lỗi xác thực, phân quyền và không tìm thấy

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt lỗi xác thực (401), phân quyền (403), không tìm thấy tài nguyên (404) và request không hợp lệ (400).
- Thiết kế error response nhất quán, có mã lỗi ổn định và thông tin hữu ích cho consumer.
- Dùng Spring Security để mô tả hành vi khi thiếu credential, credential không hợp lệ hoặc thiếu quyền.
- Dùng Spring REST Docs ghi lại error response bằng responseFields, responseHeaders và HTTP response snippet.
- Viết MockMvc documentation test cho các tình huống 401, 403, 404.
- Tổ chức document identifier riêng cho từng error scenario và include chúng vào Asciidoctor.
- Tránh đưa stack trace, token, session ID hoặc thông tin nội bộ vào tài liệu lỗi.

## 1. Vì sao cần document lỗi?

Tài liệu API không hoàn chỉnh nếu chỉ mô tả request thành công. Consumer cần biết server phản hồi thế nào khi:

- Không gửi credential.
- Gửi credential sai, hết hạn hoặc không còn hợp lệ.
- Đã xác thực nhưng không có quyền thực hiện thao tác.
- Resource không tồn tại hoặc caller không được phép biết resource đó có tồn tại.
- Request sai định dạng hoặc vi phạm validation.

Nếu tài liệu chỉ ghi “trả lỗi khi request không hợp lệ”, consumer không biết cần xử lý status nào, field nào có trong error body, mã lỗi nào có thể dùng để phân nhánh và khi nào nên yêu cầu người dùng đăng nhập lại.

Spring REST Docs tạo tài liệu từ HTTP exchange được test. Vì vậy, mỗi error document nên bắt đầu từ một test có assertion rõ ràng về status, header và body. Descriptor mô tả contract; nó không tự định nghĩa cách Spring Security hoặc controller xử lý lỗi.

## 2. Phân biệt 400, 401, 403 và 404

Các status này thể hiện những tình huống khác nhau:

| Status | Ý nghĩa | Consumer thường làm gì |
| --- | --- | --- |
| 400 Bad Request | Request không hợp lệ, thiếu/sai tham số hoặc payload không đạt validation | Sửa input và gửi lại |
| 401 Unauthorized | Request thiếu credential hợp lệ hoặc credential không được chấp nhận | Đăng nhập/cấp token mới rồi thử lại |
| 403 Forbidden | Caller đã được xác thực nhưng không có quyền thực hiện hành động | Kiểm tra role/scope hoặc yêu cầu cấp quyền |
| 404 Not Found | Resource không tồn tại hoặc API chủ động che giấu sự tồn tại của resource | Kiểm tra ID hoặc quyền truy cập theo chính sách API |

401 trong HTTP có nghĩa là request chưa được xác thực thành công. Với HTTP authentication scheme, response 401 thường cần header WWW-Authenticate để chỉ ra challenge phù hợp. Với Bearer token, resource server có thể trả WWW-Authenticate: Bearer cùng error parameter theo quy định.

403 thường biểu thị server hiểu request nhưng từ chối thực hiện vì quyền không đủ. Không nên dùng 401 và 403 thay thế tùy tiện vì consumer sẽ xử lý khác nhau.

404 không phải lúc nào cũng chứng minh resource chưa từng tồn tại. Một số hệ thống trả 404 thay vì 403 để tránh tiết lộ resource riêng tư. Đây phải là chính sách nhất quán, được test và công bố.

## 3. Thiết kế error response nhất quán

Một error response hữu ích thường có:

- type hoặc error code ổn định để máy có thể phân loại.
- title hoặc message ngắn gọn cho người đọc.
- status khớp HTTP status.
- detail giải thích lỗi ở mức an toàn.
- instance hoặc request identifier để tra cứu log khi cần.
- field errors nếu request có nhiều lỗi validation.

Ví dụ JSON theo phong cách Problem Details:

```json
{
  "type": "https://api.example.test/problems/insufficient-scope",
  "title": "Insufficient permission",
  "status": 403,
  "detail": "The caller does not have permission to read this order.",
  "instance": "/api/orders/42",
  "code": "ORDER_READ_FORBIDDEN"
}
```

RFC 9457 định nghĩa Problem Details for HTTP APIs và thay thế RFC 7807. Nhiều hệ thống hiện hữu vẫn dùng tên gọi Problem Details/RFC 7807 trong tài liệu hoặc media type application/problem+json. Khi thiết kế mới, hãy tham chiếu RFC 9457; nếu API đang theo RFC 7807, mô tả đúng phiên bản contract đang triển khai.

Không phải mọi error response đều cần mọi field. Chọn một schema nhất quán và xác định field nào bắt buộc, tùy chọn hoặc được mở rộng.

### 3.1. Không đưa thông tin nội bộ vào detail

Thông báo lỗi không nên chứa:

- Stack trace hoặc tên class nội bộ.
- SQL query hoặc tên bảng database.
- Secret, token, cookie hoặc session identifier.
- Đường dẫn filesystem hoặc hostname nội bộ.
- Thông tin cá nhân của người dùng khác.

Log server có thể chứa chi tiết kỹ thuật theo chính sách bảo mật. API response nên đưa thông tin đủ để consumer xử lý và một request/correlation ID để đội vận hành tra cứu.

## 4. Xác định contract cho từng tình huống

Một API Orders có thể công bố:

| Scenario | HTTP status | Error code mẫu | Nguyên nhân |
| --- | --- | --- | --- |
| Thiếu Bearer token | 401 | AUTHENTICATION_REQUIRED | Không có credential |
| Token sai hoặc hết hạn | 401 | INVALID_ACCESS_TOKEN | Token không được chấp nhận |
| Thiếu scope đọc đơn hàng | 403 | ORDER_READ_FORBIDDEN | Đã xác thực nhưng thiếu quyền |
| Đơn hàng không tồn tại | 404 | ORDER_NOT_FOUND | Không tìm thấy resource |
| Payload tạo đơn sai | 400 | VALIDATION_FAILED | Input vi phạm contract |

Các mã trong bảng là ví dụ. Mã thực tế phải khớp error handler và response được test. Nếu chính sách che giấu resource trả 404 cho caller không có quyền, hãy mô tả rõ sự khác biệt giữa endpoint có thể tiết lộ và endpoint không tiết lộ sự tồn tại.

## 5. Cách Spring Security tạo 401 và 403

Trong Spring Security, hai điểm mở rộng quan trọng:

- AuthenticationEntryPoint xử lý request chưa được xác thực thành công và thường trả 401.
- AccessDeniedHandler xử lý trường hợp đã xác thực nhưng không đủ quyền và thường trả 403.

Với OAuth2 Resource Server, BearerTokenAuthenticationEntryPoint và BearerTokenAccessDeniedHandler có thể tạo response phù hợp với Bearer token protocol. Nếu ứng dụng dùng schema lỗi riêng, cần cấu hình handler tương ứng và kiểm tra header WWW-Authenticate không bị mất hoặc sai.

Ví dụ cấu hình ý tưởng:

```java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/admin/**").hasAuthority("SCOPE_ADMIN")
        .anyRequest().authenticated()
    )
    .exceptionHandling(exceptions -> exceptions
        .authenticationEntryPoint(problemAuthenticationEntryPoint)
        .accessDeniedHandler(problemAccessDeniedHandler)
    );
```

Đây là ví dụ cấu trúc; tên bean và DSL phụ thuộc Spring Security version, loại authentication và cách ứng dụng chuẩn hóa Problem Details.

Không nên viết controller riêng để bắt mọi lỗi xác thực nếu Spring Security filter chain đã xử lý request trước khi request tới controller. Documentation test phải chạy qua security filter chain thật để xác nhận behavior.

## 6. Document lỗi 401: thiếu hoặc không hợp lệ credential

Giả sử GET /api/orders/42 yêu cầu Bearer token. Khi không có token, API trả 401.

Ví dụ response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/authentication-required",
  "title": "Authentication required",
  "status": 401,
  "detail": "A valid access token is required.",
  "code": "AUTHENTICATION_REQUIRED"
}
```

Không phải mọi scheme đều dùng WWW-Authenticate: Bearer. Header phải phản ánh authentication scheme của API. Với Bearer error, nội dung challenge có thể chứa thêm error/error_description theo chuẩn Bearer token.

### 6.1. MockMvc test cho 401

Ví dụ test chạy qua Spring Security:

```java
@Test
void returnsUnauthorizedWhenBearerTokenIsMissing() throws Exception {
    mockMvc.perform(get("/api/orders/42")
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                    HttpHeaders.WWW_AUTHENTICATE,
                    startsWith("Bearer")
            ))
            .andExpect(jsonPath("$.status").value(401))
            .andExpect(jsonPath("$.code")
                    .value("AUTHENTICATION_REQUIRED"))
            .andDo(document("orders-get-unauthorized",
                    responseHeaders(
                            headerWithName(HttpHeaders.WWW_AUTHENTICATE)
                                    .description("Bearer authentication challenge")
                    ),
                    responseFields(
                            fieldWithPath("type").description("URI định danh loại problem"),
                            fieldWithPath("title").description("Tiêu đề lỗi"),
                            fieldWithPath("status").description("HTTP status"),
                            fieldWithPath("detail").description("Mô tả an toàn cho consumer"),
                            fieldWithPath("code").description("Mã lỗi ổn định")
                    )
            ));
}
```

Test này minh họa descriptor. Cần static imports, security test configuration và error handler phù hợp với dự án. Nếu ứng dụng trả body rỗng hoặc một schema khác, sửa test/document theo behavior thực tế thay vì ép response giả định.

### 6.2. Token sai hoặc hết hạn

Nên có scenario riêng nếu contract phân biệt token không hợp lệ:

```java
@Test
void returnsUnauthorizedForInvalidToken() throws Exception {
    mockMvc.perform(get("/api/orders/42")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-test-token")
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isUnauthorized())
            .andDo(document("orders-get-invalid-token",
                    responseFields(
                            fieldWithPath("status").description("HTTP status"),
                            fieldWithPath("code").description("Mã lỗi ổn định"),
                            fieldWithPath("detail").description("Thông tin xử lý an toàn")
                    )
            ));
}
```

Nếu resource server kiểm tra chữ ký JWT thật, chuỗi token giả có thể dẫn tới behavior khác. Dùng decoder/test key hoặc token fixture có chủ đích. Không tắt toàn bộ security filter chỉ để test trả 401.

## 7. Document lỗi 403: đã xác thực nhưng thiếu quyền

Ví dụ caller có token hợp lệ nhưng thiếu scope ORDER_READ:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/insufficient-scope",
  "title": "Insufficient permission",
  "status": 403,
  "detail": "The caller does not have permission to read this order.",
  "code": "ORDER_READ_FORBIDDEN"
}
```

Với Bearer token, WWW-Authenticate có thể được dùng để mô tả insufficient_scope theo protocol. Hãy kiểm tra response thực tế của Resource Server và handler tùy chỉnh; không thêm header minh họa nếu server không phát ra.

### 7.1. MockMvc test cho 403

```java
@Test
@WithMockUser(authorities = "SCOPE_PROFILE_READ")
void returnsForbiddenWhenScopeIsInsufficient() throws Exception {
    mockMvc.perform(get("/api/orders/42")
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.status").value(403))
            .andExpect(jsonPath("$.code").value("ORDER_READ_FORBIDDEN"))
            .andDo(document("orders-get-forbidden",
                    responseFields(
                            fieldWithPath("type").description("URI định danh loại problem"),
                            fieldWithPath("title").description("Tiêu đề lỗi"),
                            fieldWithPath("status").description("HTTP status"),
                            fieldWithPath("detail").description("Mô tả thiếu quyền"),
                            fieldWithPath("code").description("Mã lỗi ổn định")
                    )
            ));
}
```

@WithMockUser tạo principal test và không kiểm tra chữ ký Bearer JWT. Nếu cần kiểm chứng toàn bộ resource server authentication, dùng JWT test support hoặc token fixture được ký bằng test key. Mục tiêu của ví dụ là minh họa authorization failure sau khi principal đã được xác thực.

### 7.2. Phân biệt 401 và 403 trong test

| Test setup | Kết quả kỳ vọng thường gặp |
| --- | --- |
| Không có authentication | 401 |
| Authentication không hợp lệ | 401 |
| Authentication hợp lệ, authority thiếu | 403 |
| Authentication hợp lệ, authority đủ | Request đi tiếp đến controller |

Một số cấu hình có thể trả status khác theo entry point, exception translation hoặc chính sách che giấu tài nguyên. Hãy assert theo contract đã chọn.

## 8. Document lỗi 404: không tìm thấy resource

Ví dụ:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order exists with the supplied identifier.",
  "code": "ORDER_NOT_FOUND"
}
```

Không đưa ID nhạy cảm hoặc dữ liệu của resource khác vào detail. Nếu API có chính sách che giấu resource khi caller thiếu quyền, cùng một status 404 có thể được dùng cho cả không tồn tại và không được phép biết sự tồn tại. Contract phải nhất quán và tránh side channel qua message/timing.

### 8.1. MockMvc test cho 404

```java
@Test
@WithMockUser(authorities = "SCOPE_ORDER_READ")
void returnsNotFoundForUnknownOrder() throws Exception {
    mockMvc.perform(get("/api/orders/{id}", 999999)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
            .andDo(document("orders-get-not-found",
                    responseFields(
                            fieldWithPath("type").description("URI định danh loại problem"),
                            fieldWithPath("title").description("Tiêu đề lỗi"),
                            fieldWithPath("status").description("HTTP status"),
                            fieldWithPath("detail").description("Mô tả không tìm thấy"),
                            fieldWithPath("code").description("Mã lỗi ổn định")
                    )
            ));
}
```

Dữ liệu ID 999999 cần chắc chắn không tồn tại trong test database. Reset database hoặc dùng fixture có namespace để test không phụ thuộc dữ liệu còn sót.

## 9. Document lỗi 400 và validation

Lỗi 400 thường xảy ra khi payload sai định dạng, thiếu field bắt buộc hoặc giá trị không đạt validation.

Ví dụ response có danh sách field errors:

```json
{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Validation failed",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "customerEmail",
      "code": "Email",
      "message": "must be a well-formed email address"
    }
  ]
}
```

Trong REST Docs, mô tả nested field:

```java
responseFields(
    fieldWithPath("type").description("URI định danh problem"),
    fieldWithPath("title").description("Tiêu đề lỗi"),
    fieldWithPath("status").description("HTTP status"),
    fieldWithPath("code").description("Mã lỗi"),
    fieldWithPath("fieldErrors").description("Danh sách lỗi theo field"),
    fieldWithPath("fieldErrors[].field").description("Tên field không hợp lệ"),
    fieldWithPath("fieldErrors[].code").description("Mã validation"),
    fieldWithPath("fieldErrors[].message").description("Thông báo validation")
)
```

Nếu API dùng Problem Details extension member, mô tả rõ phần mở rộng fieldErrors. Không nhầm status HTTP với status trong JSON; hai giá trị phải nhất quán theo contract.

## 10. Tổ chức error descriptor dùng chung

Nhiều error response có schema giống nhau. Có thể tạo helper để tránh lặp descriptor:

```java
static FieldDescriptor[] problemFields() {
    return new FieldDescriptor[] {
        fieldWithPath("type").description("URI định danh loại problem"),
        fieldWithPath("title").description("Tiêu đề ngắn"),
        fieldWithPath("status").description("HTTP status"),
        fieldWithPath("detail").description("Mô tả an toàn"),
        fieldWithPath("code").description("Mã lỗi ổn định")
    };
}
```

Dùng helper:

```java
document("orders-get-not-found",
    responseFields(problemFields())
)
```

Đây là ví dụ helper; cần import FieldDescriptor và các static descriptor tương ứng. Nếu một scenario có extension member riêng, bổ sung descriptor riêng cho scenario đó. Không dùng relaxedResponseFields chỉ để né field chưa được mô tả nếu field đó là contract quan trọng.

## 11. Document identifier cho error scenario

Mỗi error exchange nên có identifier riêng:

| Scenario | Document identifier |
| --- | --- |
| Thiếu credential | orders-get-unauthorized |
| Token không hợp lệ | orders-get-invalid-token |
| Thiếu scope | orders-get-forbidden |
| Không tìm thấy đơn hàng | orders-get-not-found |
| Validation thất bại | orders-create-validation-error |

Không dùng chung identifier orders-get cho cả success và 404 nếu chúng là exchange khác nhau. Snippet có cùng tên có thể ghi đè hoặc làm nội dung tài liệu không rõ scenario.

## 12. Nhúng error snippet vào Asciidoctor

Một trang operation có thể nhóm response thành success và error:

```asciidoc
[[orders-get]]
=== Lấy thông tin đơn hàng

==== Success response
include::{snippets}/orders-get/http-response.adoc[]
include::{snippets}/orders-get/response-fields.adoc[]

==== Authentication required
include::{snippets}/orders-get-unauthorized/http-response.adoc[]
include::{snippets}/orders-get-unauthorized/response-fields.adoc[]

==== Insufficient permission
include::{snippets}/orders-get-forbidden/http-response.adoc[]
include::{snippets}/orders-get-forbidden/response-fields.adoc[]

==== Order not found
include::{snippets}/orders-get-not-found/http-response.adoc[]
include::{snippets}/orders-get-not-found/response-fields.adoc[]
```

Chỉ include file snippet mà test thực sự tạo. Nếu một test không sinh response-fields.adoc, Asciidoctor sẽ báo include lỗi. Hãy kiểm tra generated-snippets sau khi chạy test và đồng bộ tên include.

### 12.1. Trang Error Responses dùng chung

Nếu nhiều resource dùng cùng error schema, có thể tạo trang tổng quan:

```asciidoc
= Error Responses

[[errors-authentication]]
== Authentication errors

Thiếu hoặc không hợp lệ credential thường trả 401.

[[errors-forbidden]]
== Authorization errors

Caller đã xác thực nhưng không đủ quyền thường nhận 403.

[[errors-not-found]]
== Resource not found

Resource không tồn tại hoặc bị che giấu theo chính sách API trả 404.

[[errors-validation]]
== Validation errors

Request không đạt contract trả 400 cùng chi tiết field errors.
```

Từ operation có thể liên kết đến phần lỗi chung bằng xref/cross-reference. Tuy nhiên, vẫn nên đặt snippet exchange cụ thể dưới operation identifier của endpoint để bảo đảm tài liệu phản ánh response đã test.

## 13. Kiểm tra header và media type của lỗi

Error response cũng có header contract:

| Header | Khi nào cần mô tả |
| --- | --- |
| Content-Type | Khi API trả application/problem+json hoặc media type lỗi riêng |
| WWW-Authenticate | Khi authentication scheme yêu cầu challenge |
| Retry-After | Khi lỗi có thể thử lại sau một khoảng thời gian |
| X-Request-Id | Khi consumer cần cung cấp mã truy vết cho hỗ trợ |
| Cache-Control | Khi response lỗi không nên được cache hoặc có chính sách cache cụ thể |

Ví dụ descriptor:

```java
responseHeaders(
    headerWithName(HttpHeaders.CONTENT_TYPE)
        .description("Media type của error response"),
    headerWithName(HttpHeaders.WWW_AUTHENTICATE)
        .description("Authentication challenge khi trả 401")
)
```

Không mô tả WWW-Authenticate trong mọi error response nếu server không phát header đó. REST Docs strict descriptor sẽ giúp test phát hiện response thay đổi; hãy chỉ khai báo header thực sự thuộc scenario.

## 14. Bảo vệ dữ liệu và thông tin lỗi

Trước khi phát hành snippet lỗi:

- Dùng ID và payload giả.
- Không ghi token hoặc cookie thật trong request snippet.
- Không đưa stack trace, SQL, filesystem path hoặc hostname nội bộ vào detail.
- Không để response chứa email/điện thoại thật của người khác.
- Che request/correlation identifier nếu chúng chứa thông tin định danh nội bộ.
- Kiểm tra cả http-response.adoc và response-fields.adoc sau preprocess.

Một error example tốt cho consumer biết cách xử lý mà không tiết lộ cách hệ thống nội bộ được triển khai.

## 15. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Thiếu token nhưng nhận 403 | Entry point/security chain cấu hình sai hoặc test principal còn tồn tại | Chạy test không authentication qua filter chain thật |
| Token hợp lệ nhưng thiếu scope lại nhận 401 | Authentication converter/authority mapping sai | Kiểm tra claim scope và mapping authority |
| 404 không sinh error body | Exception handler không xử lý exception hoặc container trả error mặc định | Chuẩn hóa exception mapping và test response |
| REST Docs báo thiếu field | Response thực tế khác descriptor | Đối chiếu JSON body và cập nhật contract/test |
| WWW-Authenticate không có trong snippet | Handler không phát header hoặc preprocessor đã xóa | Kiểm tra response thực tế và security entry point |
| Error code thay đổi giữa môi trường | Message/exception mapping phụ thuộc locale hoặc cấu hình | Dùng code ổn định, tách message hiển thị |
| Snippet lỗi ghi đè snippet thành công | Dùng chung document identifier | Đặt identifier riêng cho từng scenario |
| Error detail lộ stack trace | Trả exception message trực tiếp | Dùng Problem Details an toàn, log chi tiết phía server |
| Test 404 thất bại lúc chạy cả suite | ID tưởng là không tồn tại nhưng fixture khác đã tạo | Cô lập/reset database và dùng ID xác định |

## 16. Checklist document lỗi

- [ ] Có phân biệt rõ 400, 401, 403 và 404.
- [ ] Error schema và error code ổn định.
- [ ] JSON status khớp HTTP status.
- [ ] 401 mô tả challenge phù hợp authentication scheme.
- [ ] 403 thể hiện principal đã xác thực nhưng thiếu quyền.
- [ ] 404 theo đúng chính sách công bố/che giấu resource.
- [ ] Có MockMvc test cho từng scenario quan trọng qua security filter chain.
- [ ] Response fields và headers được mô tả bằng REST Docs.
- [ ] Mỗi error exchange có document identifier riêng.
- [ ] Asciidoctor include đúng snippet đã được sinh.
- [ ] Không có token, PII, stack trace hoặc chi tiết nội bộ trong artifact.
- [ ] CI chạy test và render tài liệu để phát hiện contract drift.

## 17. Bài tập thực hành

API Orders có endpoint GET /api/orders/{id}, yêu cầu scope ORDER_READ. Hãy tạo tài liệu cho bốn scenario:

1. Không gửi token: 401 với code AUTHENTICATION_REQUIRED.
2. Token hợp lệ nhưng thiếu scope: 403 với code ORDER_READ_FORBIDDEN.
3. Có scope nhưng order ID không tồn tại: 404 với code ORDER_NOT_FOUND.
4. Request tạo order thiếu customerEmail: 400 với code VALIDATION_FAILED và fieldErrors.

Thực hiện:

- Viết MockMvc test chạy qua security filter chain.
- Dùng test principal/JWT fixture phù hợp cho từng scenario.
- Assert status, Content-Type, WWW-Authenticate nếu có và error code.
- Dùng responseFields(...) mô tả Problem Details cùng extension member.
- Dùng responseHeaders(...) mô tả header thực tế.
- Đặt document identifier riêng cho từng exchange.
- Include các snippet vào phần Error responses trong Asciidoctor.
- Chạy test và kiểm tra snippet không chứa token, stack trace hoặc dữ liệu thật.

**Câu hỏi tự kiểm tra:** Vì sao không nên trả 401 khi người dùng đã đăng nhập nhưng thiếu quyền đọc đơn hàng? Vì consumer cần phân biệt yêu cầu đăng nhập/cấp lại credential với yêu cầu cấp quyền. 401 báo authentication chưa thành công; 403 báo caller đã được xác thực nhưng không được phép thực hiện hành động. Chính sách che giấu resource có thể dùng 404, nhưng cần được thiết kế và công bố nhất quán.

## Kết luận

Document lỗi xác thực, phân quyền và không tìm thấy cần phản ánh chính xác behavior HTTP mà consumer sẽ gặp. Phân biệt 401 cho authentication failure, 403 cho authorization denial, 404 cho resource không tồn tại hoặc được che giấu và 400 cho request không hợp lệ. Chuẩn hóa error schema, mã lỗi ổn định và header phù hợp; dùng Spring Security entry point/access denied handler để tạo response nhất quán. Viết MockMvc test qua filter chain thật, mô tả body/header bằng Spring REST Docs và đặt document identifier riêng cho từng scenario. Cuối cùng, include snippet lỗi vào Asciidoctor và rà soát dữ liệu nhạy cảm để tài liệu giúp consumer xử lý lỗi mà không tiết lộ nội bộ.
