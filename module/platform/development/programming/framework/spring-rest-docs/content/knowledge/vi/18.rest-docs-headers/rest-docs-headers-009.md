# Xác nhận header được gửi và trả về đúng

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, tài liệu REST API được tạo từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào build và CI.

Chương **Headers** không chỉ mô tả tên header. Test cần chứng minh request gửi đúng metadata mà endpoint yêu cầu và server trả về đúng header trong hợp đồng. Bài học tập trung vào hai chiều:

- **Request headers**: kiểm tra header được đưa vào request và ghi nhận trong snippet.
- **Response headers**: dùng `expectHeader()` để xác nhận header có mặt, vắng mặt, khớp giá trị hoặc khớp biểu thức.

Sau bài học, bạn có thể dùng `requestHeaders(...)` để mô tả request header, phân biệt kiểm tra sự hiện diện với giá trị cụ thể, dùng `expectHeader()` xác nhận response, kết hợp assertion với descriptor REST Docs và tạo snippet trong JUnit 5/WebTestClient.

## 2. Hai chiều header cần xác nhận

Một HTTP exchange có request và response:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Request-Id: req-test-001

{"productId":"BOOK-01","quantity":2}
~~~

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/42
X-Request-Id: req-test-001
Cache-Control: no-store

{"id":42}
~~~

| Phía | Câu hỏi kiểm thử | Công cụ chính |
| --- | --- | --- |
| Request | Client đã gửi header nào? Header bắt buộc có mặt không? | Request builder, `requestHeaders(...)`, server-side probe nếu cần xác nhận giá trị |
| Response | Server có trả header không? Giá trị có đúng hợp đồng không? | `expectHeader()` |
| Tài liệu hóa | Header được mô tả trong snippet đúng phía chưa? | `requestHeaders(...)`, `responseHeaders(...)` |

~~~mermaid
flowchart TD
    A["WebTestClient request builder"] --> B["HTTP request"]
    B --> C["Endpoint nhận header"]
    C --> D["Endpoint tạo response"]
    D --> E["expectHeader() assertions"]
    B --> F["REST Docs requestHeaders descriptors"]
    D --> G["REST Docs responseHeaders descriptors"]
    F --> H["request-headers.adoc"]
    G --> I["response-headers.adoc"]
~~~

Điểm cần nhớ: `requestHeaders(...)` là descriptor REST Docs, không phải API assertion để so sánh một header request với chuỗi kỳ vọng tùy ý. Descriptor giúp kiểm tra header được mô tả có hiện diện trong operation và tạo bảng tài liệu. Nếu cần chứng minh giá trị header request thực sự đến endpoint, hãy kiểm tra ở phía nhận request, chẳng hạn qua tham số controller, filter hoặc test probe.

## 3. Xác nhận request header được gửi

### 3.1. Khai báo header trên WebTestClient

Header có thể được thiết lập theo từng request:

~~~java
client.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .header("X-Request-Id", "req-test-001")
    .bodyValue(Map.of("productId", "BOOK-01", "quantity", 2))
    .exchange();
~~~

`contentType(...)` đặt `Content-Type`; `accept(...)` đặt `Accept`; `header(name, value)` đặt header tùy chỉnh. Nếu nhiều test dùng header mặc định, có thể cấu hình `defaultHeader(...)` lúc xây dựng WebTestClient. Với header phụ thuộc từng operation, đặt trực tiếp trên request giúp nhìn thấy hợp đồng tại nơi sử dụng.

### 3.2. Dùng requestHeaders(...) để kiểm tra header có mặt và mô tả

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;

document("orders/create",
    requestHeaders(
        headerWithName("Content-Type")
            .description("Kiểu nội dung của request body; endpoint yêu cầu application/json."),
        headerWithName("Accept")
            .description("Media type client chấp nhận; endpoint trả application/json."),
        headerWithName("X-Request-Id")
            .description("Mã truy vết duy nhất của request.")
    )
)
~~~

Khi request được tài liệu hóa, REST Docs đối chiếu descriptor với header trong operation. Nếu descriptor bắt buộc không tìm thấy header tương ứng, quá trình tạo snippet có thể thất bại. Đây là cách kiểm tra header được mô tả có xuất hiện trong request ghi nhận.

Header tùy chọn có thể được đánh dấu `.optional()`:

~~~java
headerWithName("If-Match")
    .description("ETag được gửi khi client cập nhật tài nguyên có điều kiện.")
    .optional()
~~~

Đánh dấu optional chỉ khi hợp đồng cho phép header vắng mặt; không dùng nó để né một request bị thiếu header bắt buộc.

### 3.3. Kiểm tra giá trị request header tại phía nhận

REST Docs descriptor không so sánh giá trị header request với một hằng số do bạn truyền vào. Nếu giá trị cụ thể là một phần của hành vi cần kiểm thử, xác nhận nó ở phía nhận request. Ví dụ controller nhận header bằng `@RequestHeader`:

~~~java
@RestController
static class ProbeController {

    @GetMapping("/test/probe")
    Map<String, String> probe(
            @RequestHeader("X-Request-Id") String requestId) {
        return Map.of("receivedRequestId", requestId);
    }
}
~~~

Test gửi và xác nhận giá trị controller nhận:

~~~java
client.get()
    .uri("/test/probe")
    .header("X-Request-Id", "req-test-001")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.receivedRequestId").isEqualTo("req-test-001");
~~~

Đây là test probe minh họa. Với hệ thống thật, có thể kiểm tra header trong filter, interceptor hoặc mock collaborator được controller gọi. Cách này hữu ích khi giá trị header được biến đổi hoặc xác thực trước khi sử dụng.

## 4. Xác nhận response header bằng expectHeader()

Sau `exchange()`, `expectHeader()` cho phép xác nhận header server trả về:

~~~java
client.get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().exists("ETag")
    .expectHeader().valueEquals("Cache-Control", "private, max-age=60");
~~~

Các phép kiểm tra thường dùng:

| Assertion | Điều kiện xác nhận |
| --- | --- |
| `exists(name)` | Header phải có mặt. |
| `doesNotExist(name)` | Header không được xuất hiện. |
| `valueEquals(name, value)` | Giá trị header phải bằng giá trị mong đợi. |
| `valueMatches(name, regex)` | Giá trị phải khớp biểu thức chính quy. |
| `values(name, consumer)` | Kiểm tra danh sách giá trị header bằng callback assertion. |
| `contentTypeCompatibleWith(mediaType)` | `Content-Type` tương thích với media type mong đợi. |

Chọn assertion cụ thể theo hợp đồng. Nếu chỉ kiểm tra `exists("Location")`, test chưa chứng minh URI là đúng. Nếu endpoint yêu cầu `Location: /api/orders/42`, hãy dùng `valueEquals(...)`.

### 4.1. Kiểm tra giá trị chính xác

~~~java
.expectHeader().valueEquals(HttpHeaders.LOCATION, "/api/orders/42")
~~~

Phù hợp với header có giá trị ổn định theo hợp đồng, như URI tương đối được endpoint quy định.

### 4.2. Kiểm tra bằng biểu thức chính quy

~~~java
.expectHeader().valueMatches("X-Request-Id", "req-[a-z0-9-]+")
~~~

Dùng regex khi giá trị có cấu trúc hợp lệ nhưng thay đổi giữa các lần chạy. Regex cần đủ chặt để phát hiện giá trị sai; `.*` thường quá rộng.

### 4.3. Kiểm tra nhiều giá trị

Ví dụ dưới đây dùng AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

.expectHeader().values("Vary", values ->
    assertThat(values).contains("Accept")
)
~~~

Ví dụ dùng AssertJ để xác nhận danh sách giá trị có chứa `Accept`. Nếu thứ tự hoặc tập giá trị đầy đủ được quy định, hãy kiểm tra chính xác quy tắc đó.

## 5. Kết hợp assertion và descriptor REST Docs

Assertion chứng minh giá trị server trả về đúng. Descriptor tạo bảng tài liệu và phát hiện header chưa được mô tả. Cùng một operation thường cần cả hai:

~~~java
client.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .header("X-Request-Id", "req-test-001")
    .bodyValue(Map.of("productId", "BOOK-01", "quantity", 2))
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().valueEquals(HttpHeaders.LOCATION, "/api/orders/42")
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectHeader().valueEquals("X-Request-Id", "req-test-001")
    .expectBody()
    .jsonPath("$.id").isEqualTo(42)
    .consumeWith(document("orders/create",
        requestHeaders(
            headerWithName(HttpHeaders.CONTENT_TYPE)
                .description("Kiểu nội dung của request body; endpoint yêu cầu application/json."),
            headerWithName(HttpHeaders.ACCEPT)
                .description("Media type client chấp nhận; endpoint trả application/json."),
            headerWithName("X-Request-Id")
                .description("Mã truy vết duy nhất của request.")
        ),
        responseHeaders(
            headerWithName(HttpHeaders.LOCATION)
                .description("URI tương đối của đơn hàng vừa tạo."),
            headerWithName(HttpHeaders.CONTENT_TYPE)
                .description("Kiểu representation của response; endpoint trả application/json."),
            headerWithName("X-Request-Id")
                .description("Mã truy vết được server phản hồi lại cho client.")
        )
    ));
~~~

Trong ví dụ, request builder thiết lập ba request header; `expectHeader()` xác nhận response có `Location`, `Content-Type` và `X-Request-Id` đúng giá trị; `requestHeaders(...)` mô tả header được gửi; `responseHeaders(...)` mô tả header được trả về; cuối cùng `consumeWith(document(...))` sinh snippet sau khi assertion quan trọng đạt.

Lưu ý: `expectHeader()` sau `exchange()` chỉ kiểm tra response. Nó không kiểm tra request mà client đã gửi. Nếu muốn xác nhận giá trị `X-Request-Id` ở request, dùng probe/controller/filter như mục 3.3; không suy luận điều đó từ assertion response, trừ khi endpoint được thiết kế rõ ràng để phản hồi lại header nhận được.

## 6. Phân biệt descriptor request và response

| Descriptor | Header được mô tả | Snippet |
| --- | --- | --- |
| `requestHeaders(...)` | Client gửi lên server | `request-headers.adoc` |
| `responseHeaders(...)` | Server trả cho client | `response-headers.adoc` |

~~~java
document("books/create",
    requestHeaders(
        headerWithName("Content-Type")
            .description("Kiểu nội dung của request body.")
    ),
    responseHeaders(
        headerWithName("Location")
            .description("URI của tài nguyên vừa được tạo."),
        headerWithName("ETag")
            .description("Validator của representation được trả về.")
    )
)
~~~

Không đưa `Location` vào `requestHeaders(...)` khi endpoint tạo nó trong response. Tương tự, `If-Match` là request header; `ETag` thường là response header. Khi một tên header có thể xuất hiện ở cả hai chiều như `Cache-Control` hoặc `Content-Type`, xác định rõ operation đang kiểm tra giá trị ở phía nào.

## 7. Kiểm tra header vắng mặt và header tùy chọn

Một API có thể cam kết không phát một header nội bộ hoặc không phát header cache trên một loại response:

~~~java
client.get()
    .uri("/api/private/export")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().doesNotExist("X-Debug-Only");
~~~

Với response header có thể không xuất hiện ở một nhánh, chỉ đặt `expectHeader().exists("ETag")` trong test mà hợp đồng cam kết ETag có mặt. Ở nhánh khác, kiểm tra `doesNotExist(...)` nếu việc vắng mặt là điều API quy định.

Phân biệt assertion với descriptor:

- `expectHeader().doesNotExist(...)` kiểm tra response thực tế không chứa header.
- `headerWithName(...).optional()` cho REST Docs biết header có thể vắng mặt trong operation được mô tả.
- `headerWithName(...).ignored()` loại header khỏi bảng mô tả theo chủ đích; không khẳng định header vắng mặt.

Không dùng `.optional()` hoặc `.ignored()` thay cho assertion về sự hiện diện/vắng mặt khi đó là hành vi cần kiểm chứng.

## 8. Ví dụ hoàn chỉnh với controller và WebTestClient

Ví dụ sau có endpoint POST nhận `X-Request-Id`, phản hồi lại giá trị đó và trả `Location`. Việc echo request ID chỉ nhằm minh họa cách kiểm tra giá trị đã đến controller; API thực tế có thể không cần phản hồi header này.

~~~java
import java.net.URI;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class VerifyHeadersDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.client = WebTestClient.bindToController(new OrderController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void verifiesRequestAndResponseHeaders() {
        client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .header("X-Request-Id", "req-test-001")
            .bodyValue(Map.of("productId", "BOOK-01", "quantity", 2))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().valueEquals(HttpHeaders.LOCATION, "/api/orders/42")
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectHeader().valueEquals("X-Request-Id", "req-test-001")
            .expectBody()
            .jsonPath("$.id").isEqualTo(42)
            .consumeWith(document("orders/create",
                requestHeaders(
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Kiểu nội dung của request body; endpoint yêu cầu application/json."),
                    headerWithName(HttpHeaders.ACCEPT)
                        .description("Media type client chấp nhận; endpoint trả application/json."),
                    headerWithName("X-Request-Id")
                        .description("Mã truy vết duy nhất của request.")
                ),
                responseHeaders(
                    headerWithName(HttpHeaders.LOCATION)
                        .description("URI tương đối của đơn hàng vừa tạo."),
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Kiểu representation của response; endpoint trả application/json."),
                    headerWithName("X-Request-Id")
                        .description("Mã truy vết server phản hồi lại sau khi tiếp nhận request.")
                ),
                requestFields(
                    fieldWithPath("productId").description("Mã sản phẩm"),
                    fieldWithPath("quantity").description("Số lượng")
                ),
                responseFields(
                    fieldWithPath("id").description("Mã đơn hàng được tạo")
                )
            ));
    }

    @RestController
    static class OrderController {

        @PostMapping(
            path = "/api/orders",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        public Mono<ResponseEntity<Map<String, Object>>> create(
                @RequestHeader("X-Request-Id") String requestId,
                @RequestBody Map<String, Object> request) {
            Map<String, Object> body = Map.of(
                "id", 42,
                "productId", request.get("productId"),
                "quantity", request.get("quantity")
            );
            return Mono.just(
                ResponseEntity.created(URI.create("/api/orders/42"))
                    .header("X-Request-Id", requestId)
                    .body(Map.of("id", body.get("id")))
            );
        }
    }
}
~~~

Controller nhận `X-Request-Id` qua `@RequestHeader` và trả lại nó. Test dùng `expectHeader().valueEquals(...)` để xác nhận giá trị response; vì controller echo đúng giá trị nhận được, ví dụ cũng chứng minh controller đã nhận header như mong đợi.

Trong dự án thực tế, nếu không muốn endpoint echo header, hãy dùng filter hoặc mock collaborator ghi nhận giá trị đã nhận để assertion không làm thay đổi hợp đồng API công khai.

## 9. Mô tả và kiểm tra nhiều giá trị header

Một header như `Vary` có thể chứa nhiều giá trị; `Accept` trong request cũng có thể chứa nhiều media type. Dùng assertion `values(...)` nếu cần xác nhận nội dung danh sách:

~~~java
.expectHeader().values("Vary", values ->
    assertThat(values).contains("Accept")
)
~~~

Với request header, WebTestClient có thể gửi nhiều media type:

~~~java
client.get()
    .uri("/api/reports")
    .accept(MediaType.APPLICATION_JSON, MediaType.APPLICATION_XML)
    .exchange()
    .expectStatus().isOk();
~~~

Descriptor `headerWithName("Accept")` mô tả header theo tên. HTTP request snippet cung cấp giá trị client đã gửi; descriptor cung cấp ý nghĩa cho người đọc. Nếu API yêu cầu tập media type cụ thể, kiểm tra content negotiation và test từng representation được hỗ trợ.

## 10. Xử lý header biến đổi hoặc được tạo động

Một số response header không có giá trị cố định:

- `Date` thay đổi theo thời gian.
- `X-Request-Id` có thể được tạo mới cho mỗi request.
- `ETag` có thể phụ thuộc phiên bản hoặc nội dung representation.
- `Set-Cookie` có thể chứa thuộc tính bảo mật và session thay đổi theo lần chạy.

Không nên kiểm tra những header này bằng giá trị cố định nếu hợp đồng không yêu cầu. Có thể dùng `exists(...)`, `valueMatches(...)`, `values(...)` hoặc kiểm tra từng thuộc tính cần thiết. Với giá trị động, descriptor vẫn có thể mô tả ý nghĩa ổn định, trong khi snippet chứa ví dụ từ fixture test.

Nếu snippet không nên lưu giá trị động hoặc nhạy cảm, hãy chuẩn hóa bản ghi bằng REST Docs preprocessors như `modifyHeaders()` hoặc thay giá trị theo quy tắc rõ ràng. Preprocessor tác động đến bản ghi tài liệu hóa; assertion vẫn cần kiểm tra response thực tế trước khi ghi snippet.

## 11. Snippet header và Asciidoctor

Với operation identifier `orders/create`, REST Docs tạo các snippet tiêu biểu:

~~~text
build/generated-snippets/
└── orders/
    └── create/
        ├── http-request.adoc
        ├── request-headers.adoc
        ├── request-fields.adoc
        ├── http-response.adoc
        ├── response-headers.adoc
        └── response-fields.adoc
~~~

Asciidoctor có thể đưa request và response header vào phần tài liệu riêng:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Tạo đơn hàng

=== Request headers
include::{snippets}/orders/create/request-headers.adoc[]

=== HTTP request
include::{snippets}/orders/create/http-request.adoc[]

=== Response headers
include::{snippets}/orders/create/response-headers.adoc[]

=== HTTP response
include::{snippets}/orders/create/http-response.adoc[]
~~~

`request-headers.adoc` cho biết client cần gửi gì; `response-headers.adoc` cho biết server trả gì. Hai bảng cần khớp với assertion và descriptor trong test.

## 12. Tích hợp Gradle và CI

Khi plugin Asciidoctor và task `asciidoctor` đã được cấu hình, nối task dựng tài liệu với test sinh snippet:

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

Trong CI:

~~~bash
./gradlew clean test asciidoctor
~~~

Test xác nhận request/response header và kiểm tra descriptor; REST Docs sinh snippet; Asciidoctor ghép tài liệu. Khi header bắt buộc thiếu hoặc response trả sai giá trị, task test thất bại và ngăn bước dựng/publish tài liệu tiếp tục như thể hợp đồng vẫn đúng. Với Markdown thuần, cần bước riêng để nhúng hoặc liên kết snippet; cú pháp `include::` thuộc Asciidoctor.

## 13. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân và cách xử lý |
| --- | --- |
| Descriptor request header không tìm thấy header | Kiểm tra request builder có gửi header, tên header có đúng và operation được tài liệu hóa đúng không. |
| Nghĩ `requestHeaders(...)` kiểm tra giá trị cụ thể | Descriptor xác nhận header được mô tả và sinh snippet; xác nhận giá trị tại phía nhận request bằng probe/filter/controller. |
| `expectHeader().exists(...)` pass nhưng giá trị sai | Dùng `valueEquals(...)` hoặc `valueMatches(...)` khi hợp đồng quy định nội dung. |
| Dùng assertion response để suy ra request header | `expectHeader()` kiểm tra response; kiểm tra request tại endpoint hoặc collaborator nhận request. |
| Nhầm request header với response header | Chọn `requestHeaders(...)` cho client → server và `responseHeaders(...)` cho server → client. |
| Header tùy chọn làm test lỗi | Dùng descriptor `.optional()` nếu header được phép vắng mặt; không bỏ qua header bắt buộc. |
| Header động khiến test chập chờn | Kiểm tra cấu trúc hoặc sự hiện diện thay vì giá trị cố định; dùng fixture ổn định khi ghi snippet. |
| Snippet lộ cookie/token | Dùng dữ liệu giả và preprocessor để chuẩn hóa bản ghi; kiểm tra snippet trước khi chia sẻ. |
| Không có snippet header | Kiểm tra REST Docs filter, operation identifier và descriptor trong `document(...)`. |

## 14. Bài thực hành

1. Chạy test tích hợp và mở `request-headers.adoc` cùng `response-headers.adoc`.
2. Xóa header `X-Request-Id` khỏi request nhưng giữ descriptor bắt buộc; quan sát REST Docs phát hiện header không có trong request được ghi nhận.
3. Gửi sai `Location`, xác nhận `valueEquals(...)` làm test thất bại.
4. Đổi assertion `exists("ETag")` thành `valueMatches(...)` với định dạng ETag API quy định.
5. Dùng `@RequestHeader` trong probe để xác nhận giá trị request header cụ thể đã tới controller.
6. Thêm một response header tùy chọn, kiểm tra nhánh có header và nhánh không có header; dùng `.optional()` đúng với hợp đồng.
7. Ghép snippet vào Asciidoctor và cho CI chạy test trước khi dựng tài liệu.

## 15. Ghi nhớ

- Request builder thiết lập header client gửi; `requestHeaders(...)` mô tả header trong operation và kiểm tra sự hiện diện theo descriptor.
- Muốn xác nhận giá trị request header được endpoint tiếp nhận, hãy kiểm tra ở phía nhận request; đừng dùng `expectHeader()` để suy luận về request.
- `expectHeader()` xác nhận response header: có mặt, vắng mặt, bằng giá trị, khớp regex hoặc danh sách giá trị.
- `requestHeaders(...)` và `responseHeaders(...)` mô tả hai chiều giao tiếp khác nhau; đặt descriptor đúng phía.
- Kết hợp assertion với descriptor để test vừa kiểm chứng hành vi vừa sinh snippet dễ hiểu.
- Dùng dữ liệu test ổn định, tiền xử lý header nhạy cảm khi cần, rồi chạy test trước Asciidoctor/CI để tài liệu phản ánh giao dịch HTTP đã xác nhận.
