# Document resource có path parameters và header

## 1. Mục tiêu

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ test HTTP dùng MockMvc, WebTestClient hoặc REST Assured. Bài thực hành dùng MockMvc để document resource GET /orders/{orderId}, gồm path parameter, request headers và response headers; sau đó include snippets vào AsciiDoc.

Request mẫu:

```http
GET /orders/{orderId}
Accept: application/json
X-Request-Id: req-2026-0042
```

Response mẫu:

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-42-v3"
X-Request-Id: req-2026-0042

{"id":"42","status":"PAID","total":125000}
```

## 2. Phân biệt path parameter và header

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Path parameter | orderId trong /orders/{orderId} | Chọn resource |
| Request header | Accept | Media type client mong muốn |
| Request header | X-Request-Id | Correlation ID |
| Response header | Content-Type | Media type response body |
| Response header | ETag | Validator của representation |
| Response header | X-Request-Id | Correlation ID server phản hồi |

Path parameter là một phần URI template; header là metadata của HTTP message. Trong REST Docs, dùng pathParameters cho path variable, requestHeaders cho request header và responseHeaders cho response header. Không dùng requestParameters cho path variable.

## 3. Cấu hình test và REST Docs

Ví dụ giả định project đã cấu hình Spring REST Docs MockMvc, JUnit 5 và Spring Boot test. Dependency thường dùng là spring-restdocs-mockmvc ở test scope.

Test hoàn chỉnh:

```java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.PathParametersSnippet.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class OrderDocumentationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void getOrderDocumentsPathAndHeaders() throws Exception {
        mockMvc.perform(get("/orders/{orderId}", "42")
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", "req-2026-0042"))
            .andExpect(status().isOk())
            .andDo(document("orders-get",
                pathParameters(
                    parameterWithName("orderId")
                        .description("Mã định danh của đơn hàng")
                ),
                requestHeaders(
                    headerWithName("Accept")
                        .description("Media type client mong muốn"),
                    headerWithName("X-Request-Id")
                        .description("Mã dùng để truy vết request")
                ),
                responseHeaders(
                    headerWithName("Content-Type")
                        .description("Media type của response body"),
                    headerWithName("ETag")
                        .description("Validator của representation đơn hàng"),
                    headerWithName("X-Request-Id")
                        .description("Mã truy vết được server phản hồi")
                )
            ));
    }
}
```

Đoạn test minh họa descriptors. Ứng dụng phải thực sự trả về các response headers đã mô tả. Nếu ETag hoặc X-Request-Id không có trong response, snippet header documentation sẽ thất bại hoặc không phản ánh hành vi thật.

Các static imports có thể được IDE tự thêm. Nếu release REST Docs đang dùng đặt factory hoặc snippet type ở package khác, dùng API của đúng release và xác nhận bằng compiler.

## 4. Chuẩn bị endpoint và dữ liệu ổn định

Endpoint cần trả JSON ổn định và echo correlation ID. Phác thảo controller:

```java
@GetMapping(value = "/orders/{orderId}", produces = MediaType.APPLICATION_JSON_VALUE)
ResponseEntity<OrderResponse> getOrder(
        @PathVariable String orderId,
        @RequestHeader("X-Request-Id") String requestId) {
    OrderResponse order = orderService.findById(orderId);
    return ResponseEntity.ok()
            .eTag(order.etag())
            .header("X-Request-Id", requestId)
            .body(order);
}
```

OrderResponse và orderService thuộc domain của ứng dụng. Tạo fixture cố định cho order 42 để body và ETag không thay đổi qua mỗi lần chạy. Nếu X-Request-Id là header bắt buộc, kiểm tra cả validation khi header bị thiếu. Không dùng token, mật khẩu hoặc dữ liệu cá nhân thật trong ví dụ.

## 5. Document path parameter

Dùng pathParameters và parameterWithName:

```java
pathParameters(
    parameterWithName("orderId")
        .description("Mã định danh của đơn hàng")
)
```

Tên descriptor phải khớp placeholder trong URI template: {orderId}. Nếu test gọi /orders/{id} nhưng descriptor dùng orderId, REST Docs không thể ghép đúng parameter.

Với endpoint nhiều cấp như /customers/{customerId}/orders/{orderId}, mô tả cả hai variable trong cùng pathParameters snippet. Dùng URI template và truyền giá trị riêng:

```java
get("/customers/{customerId}/orders/{orderId}", "C-7", "42")
```

## 6. Document request headers

Dùng requestHeaders và headerWithName:

```java
requestHeaders(
    headerWithName("Accept").description("Media type client mong muốn"),
    headerWithName("X-Request-Id").description("Mã truy vết request")
)
```

Header name phải khớp header thực sự được gửi. HTTP header không phân biệt hoa thường, nhưng tài liệu nên dùng cách viết nhất quán.

Với header tùy chọn, có thể đánh dấu optional:

```java
headerWithName("X-Client-Version")
    .description("Phiên bản client nếu có")
    .optional()
```

Optional chỉ nói header có thể vắng mặt trong request được document; nó không thay thế validation và không tự gửi header. Nếu document Authorization, dùng placeholder và không để bearer token thật trong snippet.

## 7. Document response headers

Dùng responseHeaders và headerWithName:

```java
responseHeaders(
    headerWithName("Content-Type").description("Media type response"),
    headerWithName("ETag").description("Validator của representation"),
    headerWithName("X-Request-Id").description("Mã truy vết request")
)
```

Có thể xác minh response thực tế:

```java
.andExpect(header().exists("ETag"))
.andExpect(header().string("X-Request-Id", "req-2026-0042"))
```

Content-Type thường được framework thiết lập khi controller trả JSON. ETag phải do ứng dụng hoặc hạ tầng tạo ra. Không thêm descriptor ETag nếu endpoint không phát hành ETag.

## 8. Kết hợp với payload snippets

Một operation có thể sinh nhiều loại snippet. Nếu response JSON có fields, thêm responseFields:

```java
responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn hàng"),
    fieldWithPath("total").description("Tổng tiền")
)
```

Đoạn này cần static imports responseFields và fieldWithPath. Chỉ include response-fields khi test đã yêu cầu sinh snippet. Nếu muốn document body thô, include http-request và http-response snippets mặc định.

## 9. Sinh và kiểm tra snippets

Chạy test sạch:

```bash
./mvnw clean test
```

Hoặc Gradle:

```bash
./gradlew clean test
```

Output phụ thuộc cấu hình build. Maven phổ biến dùng target/generated-snippets; Gradle thường dùng build/generated-snippets.

Với operation ID orders-get, các file dự kiến có thể gồm:

```text
orders-get/
├── curl-request.adoc
├── http-request.adoc
├── http-response.adoc
├── path-parameters.adoc
├── request-headers.adoc
└── response-headers.adoc
```

Danh sách thực tế phụ thuộc snippet handler được bật. Nếu thêm responseFields, có thể có response-fields.adoc. Không giả định file xuất hiện nếu test chưa yêu cầu snippet tương ứng.

Kiểm tra:

- Có đúng thư mục orders-get không?
- Path parameter snippet có orderId không?
- Request header snippet có Accept và X-Request-Id không?
- Response header snippet có Content-Type, ETag và X-Request-Id không?
- Dữ liệu nhạy cảm đã được loại bỏ chưa?
- Output có được tạo mới sau clean build không?

## 10. Biên soạn AsciiDoc

Tạo src/docs/asciidoc/orders.adoc hoặc thêm section vào index.adoc:

```asciidoc
== Get order

Truy vấn một đơn hàng theo mã định danh.

=== HTTP request
include::{snippets}/orders-get/http-request.adoc[]

=== Path parameters
include::{snippets}/orders-get/path-parameters.adoc[]

=== Request headers
include::{snippets}/orders-get/request-headers.adoc[]

=== HTTP response
include::{snippets}/orders-get/http-response.adoc[]

=== Response headers
include::{snippets}/orders-get/response-headers.adoc[]

=== Response fields
include::{snippets}/orders-get/response-fields.adoc[]
```

Chỉ include response-fields nếu test đã sinh file. Mọi include path phải khớp operation ID và generated snippets directory.

Chạy Asciidoctor sau test:

```bash
./mvnw prepare-package
```

Hoặc Gradle:

```bash
./gradlew asciidoctor
```

## 11. Kiểm tra kết quả và xử lý lỗi

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Missing path parameter | Descriptor không khớp placeholder hoặc test không dùng URI template | Dùng /orders/{orderId} và descriptor orderId |
| Request header không được document | Header không được gửi hoặc handler chưa khai báo | Gửi header và thêm requestHeaders |
| Response header thiếu | Endpoint không trả header đã mô tả | Kiểm tra response; sửa contract hoặc descriptor |
| ETag không tồn tại | Ứng dụng chưa tạo ETag | Bỏ descriptor hoặc triển khai ETag đúng contract |
| Snippet không xuất hiện | Test không chạy hoặc thiếu snippet handler | Kiểm tra test và descriptors |
| AsciiDoc include lỗi | Operation ID/path sai hoặc file chưa sinh | Kiểm tra orders-get và build order |
| Header chứa token thật | Test dùng credential thật | Dùng fixture/placeholder và che dữ liệu nhạy cảm |

Đừng sửa include để trỏ sang snippet cũ chỉ để build thành công. Dùng clean build và xác minh test hiện tại tạo đủ output.

## 12. Bài tập mở rộng

1. Thêm GET /customers/{customerId}/orders/{orderId}; document cả hai path parameters.
2. Thêm X-Tenant-Id và mô tả required/optional theo API contract.
3. Thêm response header Cache-Control và kiểm tra giá trị thực tế.
4. Tạo test 404; document response headers của error response nếu chúng thuộc contract.
5. Document Authorization nhưng bảo đảm snippet không chứa bearer token thật.
6. Biên soạn hai operation vào cùng trang AsciiDoc và kiểm tra navigation.
7. Chạy clean build trong CI và kiểm tra danh sách snippets.

**Tiêu chí hoàn thành:** test document thành công; pathParameters khớp URI template; requestHeaders/responseHeaders mô tả header thực; snippets được sinh đúng operation ID; AsciiDoc include đúng file và HTML hiển thị đầy đủ.

## 13. Câu hỏi tự kiểm tra

**1. Dùng snippet nào để document path variable?**

pathParameters với parameterWithName.

**2. Dùng snippet nào cho request header?**

requestHeaders với headerWithName.

**3. Dùng snippet nào cho response header?**

responseHeaders với headerWithName.

**4. Tại sao descriptor phải khớp URI template?**

REST Docs đối chiếu tên path variable với placeholder trong request để tạo mô tả đúng.

**5. Có thể document ETag dù response không có ETag không?**

Không. Descriptor phải phản ánh response thật; nếu ETag thuộc contract thì endpoint phải tạo và test phải xác minh.

**6. Có cần document mọi header mặc định không?**

Không. Chọn header có ý nghĩa với contract và người dùng API; tránh làm tài liệu nhiễu bởi header hạ tầng không ổn định.

## Tài liệu tham khảo

- [Spring REST Docs — Request Parameters and Path Parameters](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/#documenting-your-api-request-parameters): document path parameters và request parameters.
- [Spring REST Docs — Headers](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/#documenting-your-api-headers): requestHeaders, responseHeaders và header descriptors.
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): cấu hình MockMvc và sinh snippets.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): kiểm thử Spring MVC bằng MockMvc.

