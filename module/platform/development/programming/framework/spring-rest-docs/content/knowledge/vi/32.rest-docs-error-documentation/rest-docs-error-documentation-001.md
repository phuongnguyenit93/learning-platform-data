# Document cấu trúc lỗi và mã lỗi

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, ta tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào build và CI.

API cần mô tả cả trường hợp thành công lẫn thất bại. Khi request sai, người tích hợp cần biết HTTP status nào được trả về, cấu trúc body lỗi gồm những field nào, mã lỗi có ý nghĩa gì và có thể dùng thông tin nào để sửa request hoặc liên hệ bộ phận hỗ trợ. Nếu mỗi endpoint trả lỗi theo một định dạng khác nhau hoặc tài liệu chỉ ghi “400 Bad Request”, client rất khó xử lý lỗi một cách nhất quán.

Bài học này tập trung vào việc document cấu trúc lỗi và mã lỗi bằng Spring REST Docs. Sau bài, bạn có thể:

- Thiết kế một error response có cấu trúc và mã lỗi ổn định.
- Viết test xác nhận HTTP status, response headers và error payload.
- Dùng response field descriptors để mô tả field cấp cao, field lồng nhau và danh sách lỗi.
- Phân biệt mã lỗi nghiệp vụ với HTTP status.
- Tài liệu hóa nhiều nhóm lỗi mà không làm mờ khác biệt về nguyên nhân.
- Ghép error snippets vào Asciidoctor và chạy build trong CI.

## 2. Vì sao phải document lỗi?

Giả sử client gửi một đơn hàng thiếu địa chỉ giao:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "productId": "BOOK-01",
  "quantity": 2
}
~~~

API trả lỗi:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "code": "ORDER_SHIPPING_ADDRESS_REQUIRED",
  "message": "Shipping address is required.",
  "details": [
    {
      "field": "shippingAddress",
      "reason": "must not be blank"
    }
  ],
  "traceId": "req-7f3a91"
}
~~~

Client cần biết:

- HTTP 400 cho biết request không hợp lệ ở tầng giao thức/hợp đồng.
- ORDER_SHIPPING_ADDRESS_REQUIRED là mã lỗi máy có thể dùng để phân nhánh xử lý.
- message là thông điệp đọc được, không nên là chuỗi duy nhất mà client dùng để nhận diện lỗi.
- details mô tả field cần sửa.
- traceId hỗ trợ tra cứu log khi cần.

Một tài liệu lỗi tốt giúp người dùng API trả lời được ba câu hỏi: request đã sai ở đâu, cần xử lý theo quy tắc nào và cần cung cấp thông tin gì khi yêu cầu hỗ trợ.

## 3. Phân biệt HTTP status và mã lỗi ứng dụng

HTTP status và mã lỗi ứng dụng có vai trò khác nhau:

| Thành phần | Ví dụ | Mục đích |
| --- | --- | --- |
| HTTP status | 400, 401, 403, 404, 409, 500 | Phân loại kết quả HTTP để client, proxy và middleware hiểu. |
| Error code | ORDER_SHIPPING_ADDRESS_REQUIRED | Nhận diện chính xác trường hợp lỗi trong hợp đồng ứng dụng. |
| Message | Shipping address is required. | Giải thích cho người đọc hoặc log; có thể được bản địa hóa. |
| Details | field, reason | Cung cấp thông tin cụ thể về lỗi đầu vào hoặc trạng thái nghiệp vụ. |
| Trace/correlation ID | req-7f3a91 | Liên kết request với log và hệ thống quan sát. |

Không mã hóa toàn bộ nguyên nhân vào HTTP status. Nhiều lỗi validation khác nhau có thể cùng trả 400 nhưng có error code khác nhau. Tương tự, không dùng một status 200 cho mọi response chỉ vì body chứa cờ success/error; status HTTP phải phản ánh đúng ngữ nghĩa của kết quả.

HTTP status không thay thế error code. Error code cũng không thay thế status. Client thường kiểm tra status để quyết định nhóm xử lý chung, rồi kiểm tra code để xử lý trường hợp cụ thể.

## 4. Thiết kế schema lỗi ổn định

Một schema đơn giản có thể dùng cho nhiều endpoint:

~~~json
{
  "code": "ORDER_SHIPPING_ADDRESS_REQUIRED",
  "message": "Shipping address is required.",
  "details": [
    {
      "field": "shippingAddress",
      "reason": "must not be blank"
    }
  ],
  "traceId": "req-7f3a91"
}
~~~

Ý nghĩa từng field:

| Field | Kiểu dữ liệu | Quy ước |
| --- | --- | --- |
| code | string | Mã ổn định, duy nhất trong phạm vi API hoặc domain được quy định. |
| message | string | Thông điệp giải thích, có thể thay đổi câu chữ hoặc ngôn ngữ. |
| details | array | Danh sách chi tiết bổ sung; có thể rỗng nếu lỗi không gắn với field đầu vào. |
| details[].field | string | Tên field hoặc đường dẫn tới field gây lỗi. |
| details[].reason | string | Lý do hoặc quy tắc không được đáp ứng. |
| traceId | string | Mã tương quan để truy vết, nếu API có cung cấp. |

Các quy ước quan trọng:

1. Error code phải ổn định giữa các lần phát hành; đừng dùng message làm định danh máy.
2. Message không nên chứa stack trace, SQL, tên class nội bộ hoặc thông tin bí mật.
3. Không trả dữ liệu nhạy cảm hoặc giá trị đầu vào không cần thiết trong details.
4. Các field tùy chọn phải được mô tả là có thể vắng mặt trong tài liệu.
5. traceId nên là mã tham chiếu an toàn để hỗ trợ tra cứu, không chứa token xác thực hoặc dữ liệu cá nhân.

Nếu dự án dùng định dạng chuẩn Problem Details của HTTP, có thể dùng các thuộc tính như type, title, status, detail, instance và extension members. Không trộn lẫn tùy tiện hai schema. Hãy chọn một định dạng làm hợp đồng chính và document đầy đủ các field mà API thực sự trả.

## 5. Tổ chức mã lỗi

Mã lỗi nên mô tả tình huống, không phụ thuộc câu chữ của message hoặc vị trí triển khai nội bộ.

Ví dụ:

| Error code | HTTP status | Khi nào trả về |
| --- | ---: | --- |
| REQUEST_VALIDATION_FAILED | 400 | Body hoặc query không đáp ứng validation. |
| ORDER_SHIPPING_ADDRESS_REQUIRED | 400 | Thiếu địa chỉ giao hàng bắt buộc. |
| AUTHENTICATION_REQUIRED | 401 | Request chưa được xác thực. |
| ACCESS_DENIED | 403 | Danh tính đã xác thực nhưng không đủ quyền. |
| ORDER_NOT_FOUND | 404 | Không tìm thấy đơn hàng được yêu cầu. |
| ORDER_STATE_CONFLICT | 409 | Trạng thái hiện tại không cho phép thao tác. |
| INTERNAL_ERROR | 500 | Lỗi không mong đợi phía server. |

Đây là bộ mã minh họa; dự án cần quy định danh sách mã thực tế, phạm vi uniqueness và chính sách tương thích. Khi đổi hoặc loại bỏ error code đã công bố, cần xem đó là thay đổi hợp đồng API.

Không tái sử dụng cùng một mã lỗi cho hai nguyên nhân khác nhau nếu client cần xử lý chúng khác nhau. Không tạo mã mới chỉ vì message được diễn đạt lại.

## 6. Sinh error response trong Spring application

Có thể tập trung chuyển exception thành error response bằng @RestControllerAdvice. Ví dụ sau dùng DTO đơn giản:

~~~java
import java.util.List;

public record ApiError(
    String code,
    String message,
    List<ErrorDetail> details,
    String traceId
) {
}

public record ErrorDetail(
    String field,
    String reason
) {
}
~~~

Exception và handler:

~~~java
public class MissingShippingAddressException extends RuntimeException {
}
~~~

~~~java
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MissingShippingAddressException.class)
    ResponseEntity<ApiError> handleMissingShippingAddress() {
        ApiError error = new ApiError(
            "ORDER_SHIPPING_ADDRESS_REQUIRED",
            "Shipping address is required.",
            List.of(new ErrorDetail(
                "shippingAddress",
                "must not be blank"
            )),
            "req-test-001"
        );

        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(error);
    }
}
~~~

Trong ứng dụng thực tế, traceId nên được lấy từ cơ chế correlation ID của request, chẳng hạn request attribute hoặc tracing context, thay vì đặt một hằng số. Ví dụ dùng hằng số để snippet ổn định và dễ đọc.

Không trả stack trace qua ApiError. Stack trace thuộc log nội bộ; tài liệu API chỉ nên mô tả thông tin client được phép nhận.

## 7. Kiểm thử HTTP status và error body

REST Docs sinh snippet từ operation đã được test. Trước khi document lỗi, test phải kiểm tra status và những field quan trọng:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "productId": "BOOK-01",
              "quantity": 2
            }
            """))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.code")
        .value("ORDER_SHIPPING_ADDRESS_REQUIRED"))
    .andExpect(jsonPath("$.details[0].field")
        .value("shippingAddress"));
~~~

Assertion status xác nhận HTTP contract; assertion code xác nhận trường hợp lỗi; assertion details xác nhận client nhận được thông tin sửa request. Chỉ sau khi các assertion đạt mới gắn REST Docs document() để sinh snippet.

Nếu status đúng nhưng code sai, test phải thất bại. Nếu code đúng nhưng server trả status 200 thay vì 400, test cũng phải thất bại.

## 8. Document error response bằng responseFields

Spring REST Docs dùng responseFields(...) để mô tả body của response. Với schema ở trên:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
~~~

Descriptors:

~~~java
responseFields(
    fieldWithPath("code")
        .description("Mã lỗi ổn định để client nhận diện trường hợp lỗi."),
    fieldWithPath("message")
        .description("Thông điệp giải thích lỗi dành cho người đọc."),
    fieldWithPath("details")
        .description("Danh sách chi tiết về các field hoặc điều kiện không hợp lệ."),
    fieldWithPath("details[].field")
        .description("Tên field gây lỗi."),
    fieldWithPath("details[].reason")
        .description("Lý do field không đáp ứng quy tắc."),
    fieldWithPath("traceId")
        .description("Mã tương quan dùng để tra cứu log hỗ trợ.")
)
~~~

Đường dẫn details[] mô tả field bên trong mỗi phần tử của mảng. Descriptor cần khớp cấu trúc JSON thực tế. Nếu JSON trả object thay vì array, path phải đổi tương ứng.

### 8.1. Document field tùy chọn

Nếu traceId không phải lúc nào cũng có, đánh dấu optional:

~~~java
fieldWithPath("traceId")
    .description("Mã tương quan để tra cứu log, nếu được cấp.")
    .optional()
~~~

Optional cho REST Docs biết field có thể vắng mặt trong response. Không đánh dấu optional chỉ để làm test qua khi API đang thiếu một field bắt buộc theo hợp đồng.

### 8.2. Document cấu trúc lồng nhau

Nếu details chứa nhiều thuộc tính hoặc object phức tạp, khai báo rõ từng field:

~~~java
responseFields(
    fieldWithPath("code").description("Mã lỗi."),
    fieldWithPath("message").description("Thông điệp lỗi."),
    fieldWithPath("details").description("Danh sách chi tiết lỗi."),
    fieldWithPath("details[].field").description("Đường dẫn field lỗi."),
    fieldWithPath("details[].reason").description("Lý do validation thất bại."),
    fieldWithPath("traceId").description("Mã truy vết.")
)
~~~

Nếu chỉ cần document cả một object con như details mà không mô tả từng field trong nó ở cùng bảng, dùng subsectionWithPath("details") với description phù hợp. Khi đó tài liệu giải thích có một subsection nhưng không liệt kê schema con tại bảng hiện tại; có thể tạo bảng riêng cho subsection nếu người tích hợp cần chi tiết.

## 9. Ví dụ hoàn chỉnh: document lỗi validation

Ví dụ dưới đây giả định test application có controller và ApiExceptionHandler ở các mục trước, đồng thời MockMvc đã được cấu hình REST Docs:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderErrorDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentsMissingShippingAddress() throws Exception {
        this.mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "productId": "BOOK-01",
                      "quantity": 2
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("ORDER_SHIPPING_ADDRESS_REQUIRED"))
            .andExpect(jsonPath("$.details[0].field")
                .value("shippingAddress"))
            .andDo(document("orders/create-validation-error",
                responseFields(
                    fieldWithPath("code")
                        .description("Mã lỗi ổn định để client nhận diện nguyên nhân."),
                    fieldWithPath("message")
                        .description("Thông điệp mô tả lỗi."),
                    fieldWithPath("details")
                        .description("Danh sách chi tiết validation."),
                    fieldWithPath("details[].field")
                        .description("Tên field không hợp lệ."),
                    fieldWithPath("details[].reason")
                        .description("Lý do validation thất bại."),
                    fieldWithPath("traceId")
                        .description("Mã tương quan để tra cứu log.")
                )
            ));
    }
}
~~~

Operation identifier create-validation-error thể hiện rõ đây là phản hồi lỗi validation của thao tác tạo đơn hàng. Tên snippet nên có ý nghĩa, tránh dùng tên chung như error-1 hoặc failed.

Sau khi test chạy, REST Docs tạo các snippet tương ứng, trong đó có:

~~~text
build/generated-snippets/
└── orders/
    └── create-validation-error/
        ├── http-request.adoc
        ├── http-response.adoc
        └── response-fields.adoc
~~~

Tên thư mục thực tế được quyết định bởi operation identifier; ví dụ trên minh họa cấu trúc đường dẫn dự kiến nếu identifier được dùng đúng như vậy.

## 10. Document nhiều nhóm lỗi

Một endpoint có thể trả nhiều loại lỗi khác nhau. Nên viết test riêng cho từng trường hợp có status hoặc error code khác nhau:

| Operation ID | HTTP status | Error code | Trường hợp |
| --- | ---: | --- | --- |
| orders/create-validation-error | 400 | ORDER_SHIPPING_ADDRESS_REQUIRED | Thiếu field bắt buộc. |
| orders/get-not-found | 404 | ORDER_NOT_FOUND | Không tìm thấy đơn hàng. |
| orders/cancel-conflict | 409 | ORDER_STATE_CONFLICT | Trạng thái đơn hàng không cho phép hủy. |
| orders/admin-forbidden | 403 | ACCESS_DENIED | Người dùng không đủ quyền. |

Mỗi test nên xác nhận:

1. HTTP status mong đợi.
2. Error code cụ thể.
3. Những field bắt buộc trong error body.
4. Header lỗi cần thiết nếu API có quy định, ví dụ WWW-Authenticate cho một số phản hồi xác thực.
5. Nội dung response không để lộ thông tin nội bộ.

Nếu schema lỗi dùng chung, có thể tái sử dụng descriptors nhưng mỗi operation vẫn nên kiểm tra error code riêng. Không gộp mọi lỗi thành một test có nhiều nhánh rồi chỉ document nhánh đầu tiên.

## 11. Lỗi nghiệp vụ, validation và lỗi hệ thống

Các nhóm lỗi có thể có payload chung nhưng cần giải thích rõ khác biệt:

| Nhóm | Ví dụ | Hướng document |
| --- | --- | --- |
| Validation | Field thiếu, sai định dạng hoặc vượt giới hạn | Nêu field, reason và cách sửa request. |
| Authentication | Token thiếu, hết hạn hoặc không hợp lệ | Nêu status, error code và cách client xác thực lại. Không ghi token vào snippet. |
| Authorization | Người dùng không có quyền thao tác | Giải thích quyền cần thiết ở mức client được phép biết. |
| Not found | Resource không tồn tại hoặc không thể truy cập | Giải thích mã lỗi và resource identifier liên quan. |
| Conflict | Trạng thái hiện tại không cho phép thao tác | Nêu điều kiện nghiệp vụ cần thỏa mãn hoặc thao tác tiếp theo. |
| Server error | Lỗi không mong đợi | Cung cấp mã tham chiếu/trace ID; không công bố stack trace hoặc thông tin nội bộ. |

Lỗi 401 và 403 có ngữ nghĩa khác nhau; 404 và 409 cũng không thể thay thế nhau chỉ để thống nhất xử lý. Status và mã lỗi phải phản ánh hợp đồng API thực tế.

## 12. Sử dụng Problem Details khi dự án chọn chuẩn đó

Một số API chọn định dạng Problem Details thay cho schema tùy biến. Payload ví dụ:

~~~json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "instance": "/api/orders",
  "code": "ORDER_SHIPPING_ADDRESS_REQUIRED",
  "errors": [
    {
      "field": "shippingAddress",
      "reason": "must not be blank"
    }
  ]
}
~~~

Các thuộc tính cốt lõi mô tả loại vấn đề, tiêu đề, HTTP status, chi tiết và instance liên quan. Thuộc tính mở rộng như code và errors thuộc hợp đồng riêng của API. Document tất cả field mà server thực sự trả, đồng thời giải thích field extension do API định nghĩa.

Content type của Problem Details thường là application/problem+json. Test nên xác nhận cả status và content type nếu API cam kết định dạng đó:

~~~java
.andExpect(status().isBadRequest())
.andExpect(content().contentTypeCompatibleWith("application/problem+json"))
~~~

Không document payload tùy biến như Problem Details nếu response không theo cấu trúc và media type tương ứng. Tên gọi của schema không thay thế việc kiểm chứng response thật.

## 13. Gắn response headers vào tài liệu lỗi

Ngoài body, error response có thể có headers quan trọng:

- Content-Type: kiểu dữ liệu của error body.
- WWW-Authenticate: thông tin challenge trong phản hồi 401 theo cơ chế xác thực.
- Retry-After: thời điểm hoặc khoảng chờ trước khi thử lại, khi API dùng cơ chế phù hợp.
- X-Request-Id hoặc trace header: mã tham chiếu để hỗ trợ tra cứu.

Có thể mô tả bằng responseHeaders(...):

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;

responseHeaders(
    headerWithName("Content-Type")
        .description("Media type của error response."),
    headerWithName("X-Request-Id")
        .description("Mã request để tra cứu log hỗ trợ.")
)
~~~

Chỉ mô tả header thực sự được response trả về. Nếu header chỉ có ở một nhánh lỗi, dùng descriptor optional khi snippet chung được dùng cho operation có thể thiếu header đó; nếu mỗi lỗi có operation riêng, mô tả theo đúng response tương ứng.

## 14. Đưa error snippets vào Asciidoctor

Sau khi test sinh snippet, có thể tạo một phần tài liệu riêng cho lỗi:

~~~asciidoc
== Errors

=== Tạo đơn hàng: thiếu địa chỉ giao hàng

HTTP response:

include::{snippets}/orders/create-validation-error/http-response.adoc[]

Response fields:

include::{snippets}/orders/create-validation-error/response-fields.adoc[]
~~~

Có thể tạo bảng danh mục error code ở phần tổng quan:

~~~asciidoc
[cols="2,1,3", options="header"]
|===
| Error code | HTTP status | Ý nghĩa

| ORDER_SHIPPING_ADDRESS_REQUIRED
| 400
| Thiếu địa chỉ giao hàng

| ORDER_NOT_FOUND
| 404
| Không tìm thấy đơn hàng

| ORDER_STATE_CONFLICT
| 409
| Trạng thái đơn hàng không cho phép thao tác
|===
~~~

Bảng tổng hợp giúp tra cứu nhanh; response-fields snippet cung cấp schema chính xác được test xác nhận. Không để bảng mã lỗi thủ công mâu thuẫn với operation snippet.

## 15. Tích hợp Gradle và CI

Giả sử plugin Asciidoctor đã được cấu hình, nối task tạo tài liệu với test sinh snippet:

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

Chạy:

~~~bash
./gradlew clean test asciidoctor
~~~

Nếu test assertion error status hoặc error code thất bại, task test không đạt và bước build tài liệu không nên tạo artifact được xem là hợp lệ. CI vì vậy kiểm tra đồng thời hành vi lỗi và nội dung tài liệu sinh ra.

Với Markdown thuần, cú pháp include:: thuộc Asciidoctor không được xử lý tự động; cần bước riêng để nhúng snippet hoặc tạo liên kết tới tệp snippet.

## 16. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân và cách xử lý |
| --- | --- |
| Chỉ có snippet HTTP response, không có bảng field | Chưa truyền responseFields(...) vào document(...) hoặc descriptor không khớp payload. |
| REST Docs báo undocumented payload field | JSON response có field chưa được mô tả; thêm descriptor hoặc xử lý field có chủ đích theo hợp đồng. |
| Test pass dù error code sai | Chưa assertion vào field code; bổ sung jsonPath/value hoặc assertion tương đương. |
| Status đúng nhưng body lỗi không nhất quán | Exception handler trả schema khác nhau; chuẩn hóa DTO và mapping exception. |
| details là array nhưng descriptor dùng object path | Dùng path theo cấu trúc thực tế, ví dụ details[].field. |
| Field có thể vắng mặt làm document thất bại | Đánh dấu optional() khi hợp đồng cho phép field vắng mặt. |
| Error response lộ stack trace | Điều chỉnh exception handler/serializer; chỉ trả thông tin client cần thiết. |
| Trace ID thay đổi khiến snippet khó đọc | Dùng fixture ổn định hoặc preprocessor để chuẩn hóa giá trị khi tạo snippet; test vẫn phải xác nhận header/body trace ID có mặt nếu hợp đồng yêu cầu. |
| Bảng error code lệch so với payload | Xem test-generated snippet là nguồn kiểm chứng và đồng bộ bảng tổng hợp với danh sách mã lỗi đã được quản lý. |

## 17. Bài thực hành

1. Tạo ApiError DTO có code, message, details và traceId.
2. Viết @RestControllerAdvice chuyển MissingShippingAddressException thành HTTP 400.
3. Viết MockMvc test xác nhận status, error code và details[0].field.
4. Thêm responseFields(...) để mô tả toàn bộ schema lỗi và sinh response-fields.adoc.
5. Đánh dấu traceId optional nếu hợp đồng cho phép vắng mặt; kiểm thử cả nhánh có và không có field.
6. Thêm test 404 và 409, dùng operation identifier riêng và mã lỗi riêng.
7. Nếu API dùng Problem Details, viết test xác nhận content type, status và các extension fields.
8. Include error snippets vào phần Errors của Asciidoctor và chạy Gradle/CI.

## 18. Ghi nhớ

- HTTP status phân loại kết quả ở tầng HTTP; error code nhận diện trường hợp lỗi cụ thể của API.
- Error schema nên ổn định, có field bắt buộc/tùy chọn rõ ràng và không làm lộ thông tin nội bộ.
- Kiểm tra status, error code và các field quan trọng trước khi gọi document(...).
- Dùng responseFields(...) và fieldWithPath(...) để document body; dùng subsectionWithPath(...) khi chỉ mô tả một object con ở mức tổng quan.
- Mỗi nhóm lỗi cần status/code đúng và ví dụ operation riêng khi hành vi khác nhau.
- Document response headers nếu chúng là một phần của hợp đồng lỗi.
- Asciidoctor ghép HTTP response và response-fields snippets; CI chạy test trước khi tạo tài liệu.

## 19. Tài liệu tham khảo

- [Spring REST Docs — Documenting HTTP Responses](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): cách document response và payload bằng snippets.
- [Spring REST Docs — Payload Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/payloads.html): field descriptors, nested paths, optional fields và subsection documentation.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): định dạng chuẩn để biểu diễn lỗi HTTP nếu API lựa chọn áp dụng.
