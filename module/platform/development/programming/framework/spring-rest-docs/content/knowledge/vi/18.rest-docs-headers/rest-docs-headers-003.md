# headerWithName và mô tả header

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, tài liệu REST API được tạo từ các bài kiểm thử HTTP có thể chạy lại. Test gửi request, xác nhận response và Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown, sau đó đưa vào build và CI để tài liệu luôn bám sát hành vi đã kiểm chứng.

Trong chương **Headers**, một bảng header hữu ích cần giải thích nhiều hơn tên header. Người dùng API cần biết header dùng để làm gì, giá trị có định dạng nào, khi nào phải gửi và điều gì xảy ra nếu thiếu hoặc gửi sai.

Bài học này tập trung vào `headerWithName(...)` và cách viết mô tả header trong Spring REST Docs. Sau bài, bạn có thể tạo descriptor, viết mô tả rõ mục đích/định dạng/điều kiện sử dụng, phân biệt request và response header, biểu đạt header bắt buộc/tùy chọn/ignored, rồi dùng các descriptor để sinh snippet có thể kiểm chứng.

## 2. Từ tên header đến hợp đồng mà client hiểu được

Một request tạo đơn hàng có thể chứa:

~~~http
POST /api/orders HTTP/1.1
Accept: application/json
Content-Type: application/json
X-Request-Id: 5f23c4a8-1b62-4af0-9f75-2ad6c2b19a40
Idempotency-Key: checkout-2026-00042

{"productId":"BOOK-01","quantity":2}
~~~

Chỉ liệt kê tên `X-Request-Id` và `Idempotency-Key` chưa giải thích người gọi phải tạo giá trị ra sao. Bảng tài liệu nên trả lời:

| Câu hỏi | Ví dụ thông tin cần mô tả |
| --- | --- |
| Header có mục đích gì? | Truy vết request hoặc tránh tạo đơn hàng trùng khi client thử lại. |
| Giá trị có dạng nào? | UUID, chuỗi định danh theo quy ước hoặc media type. |
| Khi nào gửi? | Mỗi request, chỉ khi cập nhật có điều kiện, hoặc khi retry thao tác tạo. |
| Có bắt buộc không? | Nếu thiếu, server từ chối hay tự tạo giá trị thay thế? |
| Có giới hạn nào? | Độ dài, tập ký tự, tính duy nhất và phạm vi duy nhất. |

Spring REST Docs dùng descriptor để định nghĩa header cần mô tả. Khi test chạy, thư viện đối chiếu descriptor với request thực tế và sinh bảng header. Nhờ đó, tài liệu vừa là hướng dẫn sử dụng API vừa là một phần của kiểm thử hợp đồng.

## 3. Cú pháp headerWithName(...)

Import tĩnh:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
~~~

Tạo descriptor cho một header:

~~~java
headerWithName("X-Request-Id")
    .description("Mã định danh dùng để truy vết request xuyên suốt các dịch vụ.");
~~~

`headerWithName(name)` tạo descriptor cho tên header đã cho. Gọi `.description(...)` để giải thích header phục vụ mục đích gì. Descriptor sau đó được truyền vào `requestHeaders(...)` hoặc `responseHeaders(...)` tùy chiều giao tiếp.

Ví dụ với header chuẩn:

~~~java
headerWithName("Content-Type")
    .description("Kiểu nội dung của request body; endpoint này yêu cầu application/json.");
~~~

Ví dụ với header tùy chỉnh:

~~~java
headerWithName("X-Tenant-Id")
    .description("Mã tenant xác định phạm vi dữ liệu mà request được phép truy cập.");
~~~

Mô tả tốt không chỉ dịch tên header sang tiếng Việt. Nó cung cấp ngữ cảnh mà người tích hợp cần để tạo request hợp lệ.

## 4. Quy tắc viết description có chất lượng

Một description nên ngắn nhưng đủ thông tin để người đọc dùng được header mà không phải đoán.

### 4.1. Nêu mục đích trước

~~~java
headerWithName("X-Request-Id")
    .description("Mã truy vết duy nhất của request, được ghi vào log của các dịch vụ xử lý request.");
~~~

Tránh mô tả chung chung như “Header request”, “Header tùy chỉnh” hoặc “Giá trị của request”. Những câu này không nói được vì sao client cần gửi header.

### 4.2. Mô tả định dạng và ví dụ

~~~java
headerWithName("X-Request-Id")
    .description("Mã truy vết dạng UUID; ví dụ: 5f23c4a8-1b62-4af0-9f75-2ad6c2b19a40.");
~~~

Với header mang media type:

~~~java
headerWithName("Accept")
    .description("Danh sách media type client có thể nhận; endpoint này hỗ trợ application/json.");
~~~

Ví dụ cần là dữ liệu giả, hợp lệ và không chứa token, cookie hay thông tin xác thực thật.

### 4.3. Nêu điều kiện gửi và tính bắt buộc

~~~java
headerWithName("If-Match")
    .description("ETag của phiên bản tài nguyên client đã đọc; gửi khi cập nhật có điều kiện để tránh ghi đè thay đổi mới hơn.")
    .optional();
~~~

Description giải thích ý nghĩa; `.optional()` biểu đạt header có thể vắng mặt trong operation. Nếu có quy tắc lỗi cụ thể khi header thiếu hoặc ETag không khớp, có thể mô tả thêm trong phần operation hoặc phần xử lý lỗi.

### 4.4. Không lặp lại điều người đọc đã biết

`Content-Type` vốn đã là header chỉ kiểu nội dung. Description nên chỉ rõ yêu cầu của endpoint, ví dụ JSON, thay vì chỉ viết “Loại nội dung”. Tương tự, `Authorization` không nên chỉ được mô tả “Thông tin xác thực”; cần dẫn người đọc tới cơ chế xác thực hoặc scheme được API hỗ trợ, nếu nội dung đó thuộc phạm vi tài liệu.

## 5. Mô tả request header bằng requestHeaders(...)

`headerWithName(...)` tạo descriptor; `requestHeaders(...)` đưa descriptor vào operation:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

document("orders/create",
    requestHeaders(
        headerWithName("Content-Type")
            .description("Kiểu nội dung của request body; endpoint yêu cầu application/json."),
        headerWithName("Accept")
            .description("Media type client chấp nhận; endpoint trả application/json."),
        headerWithName("X-Request-Id")
            .description("Mã truy vết duy nhất của request, dùng để đối chiếu log.")
    )
)
~~~

Đây là callback minh họa được truyền vào `consumeWith(document(...))` sau khi request đã được gửi và các assertion cần thiết đã chạy. Khi test thành công, Spring REST Docs tạo tệp `request-headers.adoc` trong thư mục snippet của operation.

~~~mermaid
flowchart LR
    A["headerWithName(name)"] --> B["description(...)"]
    B --> C["requestHeaders(...)"]
    C --> D["document(operation-id, ...)"]
    D --> E["consumeWith(...)"]
    E --> F["request-headers.adoc"]
~~~

`requestHeaders(...)` mô tả header client gửi tới server. Không đưa header chỉ xuất hiện trong response vào bảng này.

## 6. Mô tả response header bằng responseHeaders(...)

Với header do server trả về, dùng `responseHeaders(...)`:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;

responseHeaders(
    headerWithName("Location")
        .description("URI tương đối của đơn hàng vừa tạo; client có thể dùng URI này để truy vấn tài nguyên."),
    headerWithName("ETag")
        .description("Validator đại diện cho phiên bản hiện tại của tài nguyên.")
)
~~~

Một số header response thường gặp:

| Header | Nội dung description nên giải thích |
| --- | --- |
| `Location` | URI của tài nguyên được tạo hoặc đích chuyển hướng. |
| `ETag` | Validator của phiên bản representation và cách dùng với request có điều kiện. |
| `Cache-Control` | Chính sách cache mà client hoặc proxy cần tuân thủ. |
| `Retry-After` | Khoảng chờ hoặc thời điểm client nên thử lại, theo định dạng server trả về. |
| `Content-Type` | Kiểu representation trong response. |

Ví dụ test tạo tài nguyên:

~~~java
client.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("productId", "BOOK-01", "quantity", 2))
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().valueEquals("Location", "/api/orders/42")
    .expectBody()
    .consumeWith(document("orders/create",
        responseHeaders(
            headerWithName("Location")
                .description("URI tương đối của đơn hàng mới được tạo; có thể dùng để truy vấn đơn hàng.")
        )
    ));
~~~

Ví dụ giả định endpoint trả status 201 và `Location` đúng như assertion. Description nói rõ ý nghĩa của URI để client biết nên làm gì tiếp theo.

## 7. Header bắt buộc, tùy chọn và ignored

### 7.1. Header bắt buộc

Descriptor không có `.optional()` biểu đạt header là một phần bắt buộc của request được mô tả:

~~~java
requestHeaders(
    headerWithName("X-Tenant-Id")
        .description("Mã tenant mà client đã được cấp quyền truy cập.")
)
~~~

Nếu request không có header được mô tả là bắt buộc, bước tạo snippet có thể thất bại. Khi đó hãy kiểm tra request builder và hợp đồng API.

### 7.2. Header tùy chọn

Dùng `.optional()` nếu header có thể vắng mặt hợp lệ:

~~~java
headerWithName("If-Match")
    .description("ETag dùng để cập nhật tài nguyên có điều kiện.")
    .optional()
~~~

Không đánh dấu optional chỉ để làm test pass khi endpoint thực sự yêu cầu header. Nếu header được gửi, descriptor vẫn định nghĩa cách mô tả header đó.

### 7.3. Header không cần trình bày trong bảng

Dùng `.ignored()` cho header cần được nhận diện nhưng không cần xuất hiện như một dòng mô tả:

~~~java
headerWithName("Host").ignored()
~~~

`.ignored()` không xóa header khỏi request HTTP thực tế. Nếu cần loại header nhạy cảm khỏi cả bản request trong snippet, hãy đánh giá request preprocessor. Hai lựa chọn giải quyết hai mục đích khác nhau: ignored điều chỉnh bảng descriptor; preprocessor điều chỉnh dữ liệu tài liệu hóa.

## 8. Mô tả header tùy chỉnh theo hợp đồng API

Header tùy chỉnh có thể dùng tiền tố riêng theo quy ước của tổ chức. Dù tên thế nào, description cần giải thích ngữ nghĩa mà client phải tuân theo.

~~~java
requestHeaders(
    headerWithName("X-Tenant-Id")
        .description("Mã tenant xác định phạm vi dữ liệu; giá trị phải thuộc tenant mà client được cấp quyền."),
    headerWithName("X-Request-Id")
        .description("Mã truy vết cho một lần gọi API; nên giữ nguyên mã này khi chuyển tiếp request qua các dịch vụ."),
    headerWithName("Idempotency-Key")
        .description("Khóa chống xử lý trùng cho thao tác tạo đơn; client gửi lại cùng khóa khi retry cùng một thao tác.")
)
~~~

Đây là ví dụ về quy ước API giả định. Khi dùng trong hệ thống thật, hãy mô tả đúng cơ chế thực tế, đặc biệt là phạm vi duy nhất, thời gian lưu khóa, cách server xử lý khóa trùng và phản hồi khi tái sử dụng khóa với payload khác.

Không tự suy đoán hành vi chỉ từ tên header. Tên `X-Tenant-Id` không chứng minh server dùng giá trị đó như cơ chế phân quyền; description phải dựa vào hợp đồng thật của API.

## 9. Mô tả header có giá trị dạng danh sách

Một số header có thể có nhiều giá trị hoặc danh sách media type:

~~~java
client.get()
    .uri("/api/reports")
    .accept(
        MediaType.APPLICATION_JSON,
        MediaType.APPLICATION_XML
    )
    .exchange()
    .expectStatus().isOk();
~~~

Descriptor `Accept` nên nói rõ những representation endpoint có hỗ trợ, theo đúng cấu hình server:

~~~java
headerWithName("Accept")
    .description("Danh sách media type client có thể nhận; endpoint hỗ trợ application/json và application/xml.")
~~~

Không ghi một danh sách media type trong description nếu server thực tế không hỗ trợ chúng. Test nên xác nhận lựa chọn content negotiation quan trọng với hợp đồng API.

Header có nhiều giá trị không nhất thiết cần một descriptor cho mỗi giá trị. `headerWithName(...)` mô tả tên header; phần mô tả giải thích cách diễn giải giá trị của header đó.

## 10. Ví dụ hoàn chỉnh: viết description có ích và sinh snippet

Ví dụ dưới đây minh họa endpoint tạo đơn hàng. Header `X-Request-Id` được client gửi lên; server trả về `Location`. Các description nói rõ vai trò thay vì chỉ lặp lại tên.

~~~java
import java.net.URI;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
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
class OrderHeaderDescriptionDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        client = WebTestClient.bindToController(new OrderController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsOrderHeaders() {
        client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .header("X-Request-Id", "doc-test-001")
            .bodyValue(Map.of("productId", "BOOK-01", "quantity", 2))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().valueEquals("Location", "/api/orders/42")
            .expectBody()
            .jsonPath("$.id").isEqualTo(42)
            .consumeWith(document("orders/create",
                requestHeaders(
                    headerWithName("Content-Type")
                        .description("Kiểu nội dung của request body; endpoint yêu cầu application/json."),
                    headerWithName("Accept")
                        .description("Media type client chấp nhận; endpoint trả application/json."),
                    headerWithName("X-Request-Id")
                        .description("Mã truy vết duy nhất của request, dùng để đối chiếu log.")
                ),
                responseHeaders(
                    headerWithName("Location")
                        .description("URI tương đối của đơn hàng vừa tạo; có thể dùng để truy vấn đơn hàng.")
                ),
                requestFields(
                    fieldWithPath("productId").description("Mã sản phẩm"),
                    fieldWithPath("quantity").description("Số lượng")
                ),
                responseFields(
                    fieldWithPath("id").description("Mã đơn hàng vừa tạo"),
                    fieldWithPath("productId").description("Mã sản phẩm trong đơn hàng"),
                    fieldWithPath("quantity").description("Số lượng sản phẩm")
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
                @RequestBody Map<String, Object> input) {
            Map<String, Object> body = Map.of(
                "id", 42,
                "productId", input.get("productId"),
                "quantity", input.get("quantity")
            );
            return Mono.just(
                ResponseEntity.created(URI.create("/api/orders/42"))
                    .body(body)
            );
        }
    }
}
~~~

Luồng thực thi:

1. WebTestClient gửi `Content-Type`, `Accept` và `X-Request-Id` cùng JSON body.
2. `exchange()` chuyển request đến controller; test kiểm tra status 201, `Location` và field `id`.
3. `document("orders/create", ...)` gắn descriptor của request header và response header vào operation.
4. Spring REST Docs kiểm tra header thực tế và sinh snippet `request-headers.adoc` cùng `response-headers.adoc`.

Controller trả `ResponseEntity.created(...)`, vì vậy status và `Location` nhất quán với assertion. Các giá trị cố định làm ví dụ dễ lặp lại; ứng dụng thực tế cần fixture/test double theo hợp đồng của mình.

## 11. Những lỗi thường gặp khi viết description

| Mô tả hoặc cách dùng | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| “Header request” | Không nói header làm gì. | Nêu mục đích và hệ thống sử dụng giá trị. |
| “Giá trị tùy chỉnh” | Client không biết phải tạo giá trị nào. | Nêu định dạng và ví dụ giả hợp lệ. |
| Mô tả `If-Match` mà không nói điều kiện | Không rõ khi nào gửi và tác dụng khi ETag không khớp. | Giải thích cập nhật có điều kiện và quy tắc phiên bản. |
| Đánh dấu `.optional()` cho header bắt buộc | Làm yếu kiểm tra hợp đồng. | Giữ descriptor bắt buộc hoặc sửa test/API theo hợp đồng đúng. |
| Dùng `requestHeaders(...)` cho `Location` | Nhầm chiều request và response. | Dùng `responseHeaders(...)`. |
| Đưa token thật vào ví dụ | Có nguy cơ lộ thông tin xác thực. | Dùng placeholder/credential giả và tiền xử lý snippet khi cần. |
| Tên descriptor không khớp header gửi thật | REST Docs không tìm được header phù hợp hoặc test thất bại. | Đối chiếu chính tả; lưu ý HTTP header không phân biệt hoa thường. |

## 12. Sinh và biên soạn snippet

Với operation `orders/create`, REST Docs thường tạo các tệp tiêu biểu trong:

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

Trang Asciidoctor có thể đưa các bảng header vào phần mô tả operation:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Tạo đơn hàng

=== Request headers
include::{snippets}/orders/create/request-headers.adoc[]

=== Request fields
include::{snippets}/orders/create/request-fields.adoc[]

=== HTTP request
include::{snippets}/orders/create/http-request.adoc[]

=== Response headers
include::{snippets}/orders/create/response-headers.adoc[]

=== Response fields
include::{snippets}/orders/create/response-fields.adoc[]
~~~

Đường dẫn `:snippets:` phải khớp với vị trí build tạo snippet và cách Asciidoctor resolve file. Tên operation trong `document("orders/create", ...)` phải nhất quán với đường dẫn trong `include::`.

## 13. Tích hợp Gradle và CI

Sau khi cấu hình plugin Asciidoctor và task `asciidoctor`, khai báo phụ thuộc vào test:

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

Trong CI, chạy:

~~~bash
./gradlew clean test asciidoctor
~~~

Test xác nhận header thực tế có khớp descriptor và sinh snippet. Asciidoctor ghép bảng header vào tài liệu cuối. Khi header bắt buộc bị thiếu hoặc header mới chưa được mô tả, test tài liệu thất bại; CI nên dừng trước bước publish. Với Markdown thuần, cần bước build riêng để nhúng hoặc liên kết các snippet; cú pháp `include::` thuộc Asciidoctor.

## 14. Bài thực hành

1. Chạy `OrderHeaderDescriptionDocumentationTest` và mở `orders/create/request-headers.adoc`, `response-headers.adoc`.
2. Viết lại description của `X-Request-Id` để nêu mục đích, định dạng và cách dùng để đối chiếu log.
3. Thử đổi mô tả `Content-Type` thành câu chung chung, sau đó cải thiện để nói rõ endpoint yêu cầu `application/json`.
4. Thêm `If-Match` vào operation cập nhật, đánh dấu `.optional()` nếu hợp đồng cho phép và viết rõ điều kiện gửi.
5. Thêm response header `ETag` vào endpoint đọc tài nguyên; mô tả cách client dùng nó trong request cập nhật có điều kiện.
6. Dựng Asciidoctor và xác nhận các bảng header trong tài liệu phản ánh descriptor mới nhất.

## 15. Ghi nhớ

- `headerWithName(...)` tạo descriptor cho một header; `.description(...)` giải thích ý nghĩa đối với client hoặc người đọc response.
- Description hữu ích cần nêu mục đích, định dạng, điều kiện gửi và tính bắt buộc khi những thông tin đó thuộc hợp đồng.
- Dùng `requestHeaders(...)` cho header client gửi và `responseHeaders(...)` cho header server trả về.
- `.optional()` biểu đạt header có thể vắng mặt; `.ignored()` loại header khỏi bảng mô tả theo chủ đích.
- Descriptor giúp Spring REST Docs đối chiếu header thực tế với hợp đồng được khai báo và tạo snippet có thể kiểm chứng.
- Dùng ví dụ giả, tránh credential thật, rồi chạy test trước Asciidoctor/CI để tài liệu được cập nhật từ giao dịch HTTP đã xác nhận.
