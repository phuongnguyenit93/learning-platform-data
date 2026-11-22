# Status code và header trong response lỗi

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, ta tạo tài liệu REST API có thể kiểm chứng bằng các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào quy trình build và CI.

Khi API trả lỗi, HTTP status và response headers là một phần của hợp đồng. Body có thể chứa error code và message, nhưng client vẫn cần status để phân loại kết quả và cần header để biết cách xác thực, thử lại, theo dõi request hoặc xử lý redirect. Tài liệu chỉ mô tả body mà bỏ status/header sẽ chưa đủ để tích hợp đúng.

Bài học này hướng dẫn kiểm thử và document status code cùng response headers của lỗi bằng Spring REST Docs. Sau bài, bạn có thể:

- Chọn HTTP status phù hợp với ngữ nghĩa của lỗi.
- Phân biệt status class với error code nghiệp vụ trong body.
- Kiểm thử status bằng MockMvc và để REST Docs ghi status vào HTTP response snippet.
- Document response headers bằng `responseHeaders(...)` và `headerWithName(...)`.
- Mô tả các header như `WWW-Authenticate`, `Retry-After`, `Location`, `Allow`, `Content-Type` và correlation ID.
- Xử lý header chỉ xuất hiện trong một số nhánh lỗi.
- Ghép error response snippets vào Asciidoctor và CI.

## 2. Status code là một phần của hợp đồng API

HTTP status mô tả kết quả của request ở tầng HTTP. Client, proxy, cache, gateway và middleware có thể dựa vào status để quyết định cách xử lý trước khi đọc error body.

Ví dụ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json
Retry-After: 5
X-Request-Id: req-91a7

{
  "code": "ORDER_STATE_CONFLICT",
  "message": "The order cannot be cancelled in its current state."
}
~~~

Trong response này:

- 409 Conflict cho biết request xung đột với trạng thái hiện tại của resource.
- ORDER_STATE_CONFLICT nhận diện tình huống cụ thể trong hợp đồng ứng dụng.
- Retry-After chỉ dẫn thời điểm/khoảng chờ nếu API định nghĩa retry cho trường hợp này.
- X-Request-Id cung cấp mã tham chiếu để tra cứu log.

Status không thay thế error code. Error code cũng không thay thế status. Một status có thể được dùng cho nhiều error code; body giải thích nguyên nhân cụ thể hơn.

## 3. Chọn status code theo ngữ nghĩa

Bảng sau là các trường hợp thường gặp trong API:

| Status | Tên | Ví dụ lỗi | Hướng dẫn cho client |
| ---: | --- | --- | --- |
| 400 | Bad Request | Body hoặc tham số không hợp lệ | Sửa request theo chi tiết validation. |
| 401 | Unauthorized | Thiếu hoặc credential không hợp lệ | Xác thực lại theo cơ chế API công bố. |
| 403 | Forbidden | Đã xác thực nhưng không đủ quyền | Kiểm tra quyền hoặc vai trò được cấp. |
| 404 | Not Found | Resource không tồn tại | Kiểm tra resource ID hoặc trạng thái truy cập. |
| 405 | Method Not Allowed | HTTP method không được endpoint hỗ trợ | Dùng method được API cho phép; xem header Allow nếu có. |
| 409 | Conflict | Trạng thái resource xung đột với thao tác | Đọc trạng thái hiện tại và quyết định bước tiếp theo. |
| 412 | Precondition Failed | Điều kiện như If-Match không thỏa mãn | Đọc lại resource hoặc cập nhật validator. |
| 415 | Unsupported Media Type | Content-Type request không được hỗ trợ | Gửi media type được endpoint công bố. |
| 422 | Unprocessable Content | Nội dung đúng cú pháp nhưng không thể xử lý theo quy tắc | Sửa nội dung theo chi tiết nghiệp vụ/validation. |
| 429 | Too Many Requests | Vượt giới hạn request | Tôn trọng chính sách retry và Retry-After nếu được trả. |
| 500 | Internal Server Error | Lỗi không mong đợi phía server | Thử lại theo chính sách an toàn và cung cấp trace ID khi liên hệ hỗ trợ. |
| 503 | Service Unavailable | Dịch vụ tạm thời không sẵn sàng | Có thể thử lại sau; xem Retry-After nếu có. |

Đây là hướng dẫn tổng quát, không phải quy tắc bắt buộc cho mọi API. Chọn status theo semantics của endpoint và chuẩn HTTP mà hệ thống cam kết. Không dùng 200 cho lỗi chỉ vì body có success=false; cũng không dùng 500 cho lỗi đầu vào mà client có thể sửa.

### 3.1. Phân biệt 401 và 403

- 401 cho biết request chưa được xác thực hợp lệ; response thường có WWW-Authenticate khi endpoint dùng HTTP authentication scheme.
- 403 cho biết server hiểu request nhưng từ chối thực hiện do quyền truy cập hoặc chính sách.

Không trả 401 và 403 thay thế nhau tùy tiện. Client có thể cần luồng xử lý khác nhau: cập nhật credential so với yêu cầu cấp quyền.

### 3.2. Phân biệt 404 và 409

- 404 phù hợp khi resource được yêu cầu không được tìm thấy hoặc API chọn không tiết lộ sự tồn tại của resource.
- 409 phù hợp khi request xung đột với trạng thái hiện tại của resource.

Ví dụ, mã đơn hàng không tồn tại có thể là 404; đơn hàng tồn tại nhưng đã giao nên không thể hủy có thể là 409.

## 4. HTTP response snippet ghi lại status và headers

Spring REST Docs sinh http-response.adoc từ response mà test nhận được. Snippet này chứa status line, response headers và body:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json
Retry-After: 5
X-Request-Id: req-91a7

{
  "code": "ORDER_STATE_CONFLICT",
  "message": "The order cannot be cancelled in its current state."
}
~~~

REST Docs không yêu cầu một descriptor riêng để ghi status line. Test xác nhận status bằng assertion, còn http-response.adoc thể hiện status thực tế của response đã được document. responseHeaders(...) tạo thêm bảng mô tả ý nghĩa của các header mà client cần hiểu.

Hai phần bổ trợ nhau:

1. HTTP response snippet cho thấy response cụ thể đã xảy ra.
2. Response headers snippet giải thích header nào là một phần của hợp đồng và ý nghĩa của chúng.

## 5. Kiểm thử status bằng MockMvc

Dùng status matcher để xác nhận status mong đợi trước khi sinh snippet:

~~~java
mockMvc.perform(delete("/api/orders/{id}", 42))
    .andExpect(status().isConflict())
    .andExpect(jsonPath("$.code").value("ORDER_STATE_CONFLICT"))
    .andDo(document("orders/cancel-conflict"));
~~~

Một số matcher thường dùng:

~~~java
status().isBadRequest();          // 400
status().isUnauthorized();       // 401
status().isForbidden();          // 403
status().isNotFound();            // 404
status().isMethodNotAllowed();    // 405
status().isConflict();            // 409
status().isTooManyRequests();     // 429
status().isInternalServerError(); // 500
status().isServiceUnavailable();  // 503
~~~

Nếu matcher tiện ích không có trong phiên bản Spring Test của dự án, có thể dùng status().is(409) hoặc status().isEqualTo(HttpStatus.CONFLICT.value()). Chọn API có trong phiên bản dependency thực tế.

Không chỉ assertion status rồi dừng lại. Nên assertion error code và field quan trọng trong body để xác nhận status gắn với đúng nguyên nhân.

## 6. Document response headers

Spring REST Docs dùng responseHeaders(...) và headerWithName(...) để mô tả response headers:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
~~~

Ví dụ:

~~~java
responseHeaders(
    headerWithName("Content-Type")
        .description("Media type của error response."),
    headerWithName("X-Request-Id")
        .description("Mã request để tra cứu log hỗ trợ.")
)
~~~

Khi truyền descriptor vào document(...), REST Docs kiểm tra header được mô tả có tồn tại trong response thực tế. Nếu response có header chưa được mô tả, REST Docs có thể báo undocumented header tùy cấu hình snippet và phiên bản.

Không thêm header vào descriptor chỉ vì muốn nó xuất hiện trong tài liệu. Test phải thực sự trả header đó. Nếu header là tùy chọn, đánh dấu optional theo hợp đồng.

## 7. Các response headers thường gặp trong lỗi

### 7.1. Content-Type

Cho client biết định dạng error body:

~~~http
Content-Type: application/json
~~~

Nếu API dùng Problem Details, media type thường là:

~~~http
Content-Type: application/problem+json
~~~

Document Content-Type giúp client chọn parser phù hợp. Test nên kiểm tra media type tương ứng với body.

### 7.2. WWW-Authenticate

401 response có thể chỉ ra authentication scheme:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api"
Content-Type: application/json
~~~

Document header:

~~~java
headerWithName("WWW-Authenticate")
    .description("Authentication challenge mà client phải đáp ứng.")
~~~

Không đưa access token hoặc credential vào ví dụ. Header challenge mô tả scheme/realm; client tự gửi credential hợp lệ theo cơ chế được công bố.

### 7.3. Retry-After

Một số response 429 hoặc 503 có thể trả:

~~~http
Retry-After: 30
~~~

Giá trị có thể biểu thị số giây cần chờ hoặc HTTP date theo cú pháp của HTTP. Tài liệu cần giải thích cách API sử dụng header và client phải tôn trọng nó như thế nào.

~~~java
headerWithName("Retry-After")
    .description("Thời gian hoặc thời điểm client nên chờ trước khi thử lại.")
~~~

Không suy ra rằng mọi 429/503 đều phải có Retry-After. Chỉ document header khi API thực sự phát ra và cam kết hành vi đó.

### 7.4. Location

Location có thể xuất hiện trong response redirect hoặc một số response tạo resource:

~~~http
HTTP/1.1 201 Created
Location: /api/orders/42
~~~

Nếu API trả Location trong một error response cụ thể, hãy mô tả đúng ý nghĩa riêng của endpoint đó. Không mặc định Location luôn là header lỗi.

~~~java
headerWithName("Location")
    .description("URI tham chiếu tới resource liên quan theo hợp đồng endpoint.")
~~~

### 7.5. Allow

405 Method Not Allowed có thể trả danh sách method được hỗ trợ:

~~~http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD
~~~

Document header:

~~~java
headerWithName("Allow")
    .description("Các HTTP method được endpoint hỗ trợ.")
~~~

Header này giúp client chọn method phù hợp thay vì thử ngẫu nhiên.

### 7.6. Correlation ID

API có thể trả một header như X-Request-Id hoặc Traceparent để liên kết request với hệ thống quan sát:

~~~http
X-Request-Id: req-91a7
~~~

Document đúng tên header thực tế của hệ thống:

~~~java
headerWithName("X-Request-Id")
    .description("Mã tương quan để bộ phận hỗ trợ tra cứu request.")
~~~

Giá trị ví dụ nên ổn định để snippet dễ đọc. Không đưa token, session ID hoặc dữ liệu định danh nhạy cảm vào header mẫu.

## 8. Header bắt buộc và header tùy chọn

Một số header chỉ xuất hiện trong nhánh lỗi nhất định. Ví dụ:

| Header | 401 | 403 | 409 | 429 | 503 |
| --- | --- | --- | --- | --- | --- |
| Content-Type | Thường có nếu có body | Thường có nếu có body | Thường có nếu có body | Thường có nếu có body | Thường có nếu có body |
| WWW-Authenticate | Có thể có theo auth scheme | Thường không dùng làm challenge | Không thường dùng | Không thường dùng | Không thường dùng |
| Retry-After | Theo chính sách riêng | Theo chính sách riêng | Có thể có nếu API quy định | Có thể có | Có thể có |
| X-Request-Id | Theo cấu hình tracing | Theo cấu hình tracing | Theo cấu hình tracing | Theo cấu hình tracing | Theo cấu hình tracing |

Bảng chỉ minh họa khả năng xuất hiện; hợp đồng cụ thể của API mới là căn cứ cuối cùng.

Nếu một descriptor dùng cho response mà header có thể vắng mặt, đánh dấu optional:

~~~java
headerWithName("Retry-After")
    .description("Thời gian chờ trước khi thử lại, nếu được cung cấp.")
    .optional()
~~~

Optional có nghĩa header có thể không xuất hiện trong response được document. Không dùng optional để che lỗi khi header bắt buộc theo hợp đồng bị thiếu; hãy để test hoặc REST Docs phát hiện vi phạm.

Nếu mỗi nhóm lỗi có operation riêng, thường nên mô tả đúng các header thực sự có ở operation đó thay vì tạo một bảng header quá rộng và đánh dấu hầu hết là optional.

## 9. Ví dụ hoàn chỉnh: document 409 Conflict

Giả sử hủy đơn hàng đã giao sẽ trả 409 cùng error code và hai response headers:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json
Retry-After: 5
X-Request-Id: req-test-409

{
  "code": "ORDER_STATE_CONFLICT",
  "message": "The order cannot be cancelled in its current state."
}
~~~

MockMvc test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderConflictDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentsCancelConflict() throws Exception {
        this.mockMvc.perform(delete("/api/orders/{id}", 42))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value("ORDER_STATE_CONFLICT"))
            .andDo(document("orders/cancel-conflict",
                responseHeaders(
                    headerWithName("Content-Type")
                        .description("Media type của error response."),
                    headerWithName("Retry-After")
                        .description("Số giây client nên chờ trước khi thử lại."),
                    headerWithName("X-Request-Id")
                        .description("Mã request để tra cứu log hỗ trợ.")
                ),
                responseFields(
                    fieldWithPath("code")
                        .description("Mã lỗi ổn định của xung đột trạng thái đơn hàng."),
                    fieldWithPath("message")
                        .description("Giải thích vì sao không thể hủy đơn hàng.")
                )
            ));
    }
}
~~~

Ví dụ giả định MockMvc đã được cấu hình REST Docs filter và endpoint trả status/header/body như mô tả. Nếu ứng dụng không trả Retry-After cho 409, bỏ descriptor đó hoặc đánh dấu optional nếu header thực sự có thể xuất hiện tùy điều kiện.

REST Docs tạo các snippet:

~~~text
build/generated-snippets/orders/cancel-conflict/
├── http-request.adoc
├── http-response.adoc
├── response-headers.adoc
└── response-fields.adoc
~~~

http-response.adoc thể hiện status line và header thực tế; response-headers.adoc giải thích ý nghĩa header; response-fields.adoc mô tả body.

## 10. Document 401 Unauthorized và WWW-Authenticate

Ví dụ test xác nhận challenge header:

~~~java
mockMvc.perform(get("/api/profile"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().exists("WWW-Authenticate"))
    .andDo(document("profile/unauthorized",
        responseHeaders(
            headerWithName("WWW-Authenticate")
                .description("Authentication scheme mà client cần sử dụng."),
            headerWithName("Content-Type")
                .description("Media type của error response.")
        )
    ));
~~~

Header matcher xác nhận challenge thực sự tồn tại. Response headers descriptor giải thích ý nghĩa cho người đọc. Cần bổ sung assertion body/error code nếu API có quy định error payload.

Nếu hệ thống dùng Bearer token, không đưa token mẫu có vẻ hợp lệ vào tài liệu. Hãy mô tả cách lấy credential ở phần authentication của API.

## 11. Document 429 Too Many Requests và Retry-After

429 thường được dùng khi client vượt giới hạn request. Nếu API trả Retry-After, tài liệu nên nói rõ client cần đợi trước khi gửi lại.

~~~java
mockMvc.perform(get("/api/reports"))
    .andExpect(status().isTooManyRequests())
    .andExpect(header().string("Retry-After", "30"))
    .andDo(document("reports/rate-limited",
        responseHeaders(
            headerWithName("Retry-After")
                .description("Số giây client phải chờ trước lần thử tiếp theo."),
            headerWithName("X-Request-Id")
                .description("Mã request để tra cứu sự kiện giới hạn lưu lượng.")
        )
    ));
~~~

Nếu giá trị Retry-After thay đổi theo thời điểm, dùng test fixture hoặc clock cố định để snippet ổn định. Không làm giả giá trị trong assertion: test vẫn cần xác nhận response tuân thủ chính sách thực tế.

## 12. Document 405 Method Not Allowed và Allow

405 cho biết method được dùng không được hỗ trợ cho resource. Header Allow liệt kê method được phép:

~~~java
mockMvc.perform(post("/api/orders/42"))
    .andExpect(status().isMethodNotAllowed())
    .andExpect(header().string("Allow", "GET, HEAD"))
    .andDo(document("orders/method-not-allowed",
        responseHeaders(
            headerWithName("Allow")
                .description("Danh sách HTTP method được resource hỗ trợ.")
        )
    ));
~~~

Giá trị Allow cụ thể phụ thuộc mapping và framework/application. Hãy assertion theo hợp đồng thực tế, tránh hard-code danh sách method nếu cấu hình endpoint thay đổi có chủ đích.

## 13. Document Location và các header định tuyến liên quan

Một số response liên quan tới resource hoặc redirect có Location. Với 201 Created, header này thường trỏ tới resource mới:

~~~http
HTTP/1.1 201 Created
Location: /api/orders/42
~~~

Test và document:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content(validOrderJson))
    .andExpect(status().isCreated())
    .andExpect(header().string("Location", "/api/orders/42"))
    .andDo(document("orders/create",
        responseHeaders(
            headerWithName("Location")
                .description("URI của đơn hàng vừa được tạo.")
        )
    ));
~~~

Đây là ví dụ response thành công để minh họa Location. Nếu một error response có Location theo hợp đồng riêng, document tại operation lỗi tương ứng và giải thích rõ ý nghĩa.

## 14. Kết hợp response headers và response fields

Một error response thường cần cả hai nhóm descriptors:

~~~java
document("orders/cancel-conflict",
    responseHeaders(
        headerWithName("Content-Type")
            .description("Media type của response."),
        headerWithName("X-Request-Id")
            .description("Mã tham chiếu để tra cứu log.")
    ),
    responseFields(
        fieldWithPath("code")
            .description("Mã lỗi nghiệp vụ."),
        fieldWithPath("message")
            .description("Thông điệp giải thích lỗi.")
    )
)
~~~

Không nhầm:

- responseHeaders(...) mô tả metadata của HTTP response.
- responseFields(...) mô tả các field trong response body.
- status() assertion xác nhận status code.
- http-response.adoc ghi status line, headers và body của response thực tế.

Tách các trách nhiệm này giúp tài liệu vừa cho thấy một response cụ thể vừa giải thích hợp đồng của nó.

## 15. Tổ chức tài liệu theo nhóm status

Có thể tổ chức chương lỗi theo status class hoặc theo nghiệp vụ:

| Cách tổ chức | Ví dụ mục | Khi phù hợp |
| --- | --- | --- |
| Theo status | 4xx Client Errors, 5xx Server Errors | API có nhiều endpoint và cần tra cứu status chung. |
| Theo nghiệp vụ | Order errors, Authentication errors, Rate limits | Client thường tích hợp theo domain/luồng nghiệp vụ. |
| Kết hợp | Tổng quan status rồi liên kết tới operation snippets | Tài liệu lớn cần cả tra cứu nhanh và ví dụ thực tế. |

Nên có một bảng tổng hợp status/error code/header quan trọng, sau đó include snippet từ từng test. Bảng tổng hợp không thay thế response snippet đã được test kiểm chứng.

## 16. Tích hợp Asciidoctor và CI

Asciidoctor có thể include HTTP response và header snippets:

~~~asciidoc
== Hủy đơn hàng: xung đột trạng thái

=== HTTP response
include::{snippets}/orders/cancel-conflict/http-response.adoc[]

=== Response headers
include::{snippets}/orders/cancel-conflict/response-headers.adoc[]

=== Response fields
include::{snippets}/orders/cancel-conflict/response-fields.adoc[]
~~~

Giả sử plugin Asciidoctor đã được cấu hình, nối task tài liệu với test:

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

Chạy trong CI:

~~~bash
./gradlew clean test asciidoctor
~~~

Test xác nhận status/header/body; REST Docs sinh snippet; Asciidoctor ghép tài liệu từ output mới. Nếu status hoặc header không đúng hợp đồng, test thất bại và CI không nên phát hành tài liệu mới.

Với Markdown thuần, cú pháp include:: của Asciidoctor không tự được xử lý. Dùng bước build riêng để nhúng snippet hoặc liên kết tới tệp đã sinh.

## 17. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân và cách xử lý |
| --- | --- |
| HTTP response snippet có status sai | Test chưa assertion status hoặc endpoint mapping trả sai status; thêm status matcher cụ thể. |
| Response headers snippet không được tạo | Chưa truyền responseHeaders(...) vào document(...). |
| REST Docs báo thiếu header | Descriptor mô tả header không có trong response; kiểm tra response thực tế hoặc optional theo hợp đồng. |
| Header xuất hiện nhưng ý nghĩa không rõ | Description quá chung; giải thích client phải làm gì với header. |
| 401 không có WWW-Authenticate | Kiểm tra authentication mechanism và hợp đồng challenge của API. |
| 429 không có Retry-After | API có thể không cam kết header này; đừng document như header bắt buộc nếu response không trả. |
| 405 thiếu Allow | Kiểm tra method mapping và response được framework/application tạo ra. |
| Snippet chứa trace ID ngẫu nhiên | Dùng fixture/clock ổn định hoặc preprocessor phù hợp; vẫn assertion sự hiện diện của header. |
| Bảng status và response snippet mâu thuẫn | Dùng test-generated snippets làm căn cứ, đồng bộ bảng tổng hợp theo hợp đồng hiện hành. |

## 18. Bài thực hành

1. Tạo endpoint hủy đơn hàng trả 409 khi trạng thái không cho phép hủy.
2. Viết MockMvc test assertion status 409 và error code ORDER_STATE_CONFLICT.
3. Document Content-Type và X-Request-Id bằng responseHeaders(...).
4. Tạo endpoint yêu cầu xác thực; kiểm thử 401 và WWW-Authenticate.
5. Tạo endpoint giới hạn lưu lượng; kiểm thử 429 và Retry-After.
6. Thử một endpoint dùng sai method; kiểm tra 405 và Allow.
7. Tạo response 503 có Retry-After nếu hợp đồng dịch vụ quy định.
8. Include http-response, response-headers và response-fields snippets vào Asciidoctor.
9. Chạy Gradle/CI và kiểm tra status/header trong artifact được sinh.

## 19. Ghi nhớ

- HTTP status là phần bắt buộc cần hiểu của error contract; chọn status theo semantics chứ không theo tiện lợi.
- Error code trong body bổ sung nguyên nhân cụ thể mà status không thể hiện.
- http-response.adoc ghi status line, response headers và body của response thực tế.
- Dùng responseHeaders(...) và headerWithName(...) để mô tả header; dùng optional() khi hợp đồng cho phép header vắng mặt.
- WWW-Authenticate, Retry-After, Allow, Location, Content-Type và correlation ID có ý nghĩa khác nhau; chỉ document header mà API thực sự trả.
- Kết hợp status assertion, response header descriptors và response field descriptors để kiểm chứng toàn bộ error response.
- Chạy test trước Asciidoctor trong CI để tài liệu phản ánh status và header đã được xác nhận.

## 20. Tài liệu tham khảo

- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/headers.html): mô tả request/response headers bằng snippets.
- [Spring REST Docs — Documenting HTTP Responses](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): cách sinh HTTP response snippets.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): định nghĩa status codes và semantics của các HTTP headers.
