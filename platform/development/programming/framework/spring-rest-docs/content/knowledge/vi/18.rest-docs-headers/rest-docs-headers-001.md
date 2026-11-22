# Document request headers bằng requestHeaders

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, tài liệu REST API được tạo từ các bài kiểm thử HTTP có thể chạy lại và kiểm chứng. Test gửi request, xác nhận response, rồi Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Asciidoctor/Markdown ghép snippet thành tài liệu, sau đó build và CI kiểm tra tài liệu cùng mã nguồn.

Chương **Headers** tập trung vào metadata truyền trong HTTP. Request header cho biết client muốn nhận kiểu nội dung nào, gửi dữ liệu theo định dạng nào, xác thực ra sao hoặc cung cấp thông tin truy vết nào. Nếu tài liệu không giải thích rõ các header thuộc hợp đồng API, người dùng có thể gọi đúng URI nhưng vẫn nhận lỗi vì thiếu header hoặc gửi sai định dạng.

Bài học này hướng dẫn dùng `requestHeaders(...)` của Spring REST Docs để mô tả header phía request. Sau bài, bạn có thể:

- Khai báo header cần tài liệu hóa bằng `headerWithName(...)`.
- Dùng `requestHeaders(...)` trong `document(...)` để sinh `request-headers.adoc`.
- Hiểu cách descriptor kiểm tra header thực tế so với hợp đồng được mô tả.
- Mô tả header bắt buộc, header tùy chọn và header được bỏ khỏi bảng tài liệu.
- Kết hợp WebTestClient, JUnit 5 và Spring REST Docs trong một test hoàn chỉnh.
- Đưa snippet header vào trang Asciidoctor và bảo đảm CI tạo lại tài liệu từ test.

## 2. Request header là gì và vì sao cần tài liệu hóa?

HTTP request gồm phương thức, URI, header và có thể có body. Header truyền metadata ảnh hưởng cách server tiếp nhận hoặc xử lý request. Ví dụ:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Accept: application/json
Content-Type: application/json
X-Request-Id: req-001

{"productId":"BOOK-01","quantity":2}
~~~

Trong ví dụ:

| Header | Ý nghĩa |
| --- | --- |
| `Accept` | Các kiểu response client có thể nhận. |
| `Content-Type` | Kiểu dữ liệu của request body. |
| `X-Request-Id` | Header tùy chỉnh dùng để truy vết request. |
| `Authorization` | Thông tin xác thực nếu API yêu cầu. |
| `If-Match` | Điều kiện dựa trên ETag, thường dùng trong cập nhật có kiểm soát phiên bản. |

Không phải endpoint nào cũng cần mọi header. Tài liệu chỉ nên mô tả những header thuộc hợp đồng của operation: header bắt buộc, header tùy chọn và header có ý nghĩa đối với client.

Spring REST Docs dùng descriptor để định nghĩa header cần được mô tả. Khi test chạy, thư viện đối chiếu descriptor với request thực tế và sinh bảng header. Nhờ đó, tài liệu vừa là hướng dẫn sử dụng API vừa là một phần của kiểm thử hợp đồng.

## 3. `headerWithName(...)` và `requestHeaders(...)`

Hai API chính đến từ `HeaderDocumentation`:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
~~~

`headerWithName(name)` tạo descriptor cho một header. Gọi `.description(...)` để giải thích header phục vụ mục đích gì:

~~~java
headerWithName("X-Request-Id")
    .description("Mã duy nhất dùng để truy vết request");
~~~

`requestHeaders(...)` nhận một hoặc nhiều descriptor và đưa chúng vào `document(...)`:

~~~java
document("orders/create",
    requestHeaders(
        headerWithName("X-Request-Id")
            .description("Mã truy vết request"),
        headerWithName("Content-Type")
            .description("Định dạng JSON của request body")
    )
)
~~~

Khi test tạo snippet thành công, Spring REST Docs sinh tệp `request-headers.adoc` trong thư mục của operation. Bảng trong tệp thường có cột tên header và mô tả.

~~~mermaid
flowchart LR
    A["WebTestClient gửi request"] --> B["REST Docs nhận HTTP operation"]
    B --> C["requestHeaders descriptors"]
    C --> D["Đối chiếu header thực tế"]
    D --> E["request-headers.adoc"]
    E --> F["Asciidoctor / API guide"]
~~~

`requestHeaders(...)` phải được truyền vào callback `document(...)` của request cần mô tả. Chỉ import hoặc khai báo descriptor mà không gọi callback thì chưa tạo snippet.

## 4. Ví dụ đầy đủ với WebTestClient và JUnit 5

Giả sử endpoint `POST /api/orders` nhận JSON, yêu cầu header `X-Request-Id`, rồi trả về status 201. Test dưới đây gửi header thật, kiểm tra response và sinh bảng request header.

Dependency Gradle Groovy DSL trong dự án Spring Boot WebFlux:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-webtestclient'
}
~~~

Ví dụ test:

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
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class OrderRequestHeadersDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.client = WebTestClient.bindToController(new OrderController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsCreateOrderRequestHeaders() {
        client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .header("X-Request-Id", "doc-test-001")
            .bodyValue(Map.of(
                "productId", "BOOK-01",
                "quantity", 2
            ))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.id").isEqualTo(42)
            .consumeWith(document("orders/create",
                requestHeaders(
                    headerWithName("X-Request-Id")
                        .description("Mã dùng để truy vết request"),
                    headerWithName("Content-Type")
                        .description("Định dạng của request body"),
                    headerWithName("Accept")
                        .description("Kiểu response client chấp nhận")
                ),
                requestFields(
                    fieldWithPath("productId").description("Mã sản phẩm"),
                    fieldWithPath("quantity").description("Số lượng")
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
                @RequestBody Map<String, Object> request) {
            Map<String, Object> result = Map.of(
                "id", 42,
                "productId", request.get("productId"),
                "quantity", request.get("quantity")
            );
            return Mono.just(
                ResponseEntity.created(URI.create("/api/orders/42"))
                    .body(result)
            );
        }
    }
}
~~~

Các bước trong test:

1. `@ExtendWith(RestDocumentationExtension.class)` tích hợp Spring REST Docs vào JUnit 5.
2. `documentationConfiguration(restDocumentation)` thêm REST Docs filter vào WebTestClient.
3. `contentType(...)`, `accept(...)` và `header(...)` tạo header của request gửi tới endpoint.
4. `exchange()` thực hiện request; `expectStatus()` và JSONPath xác nhận kết quả.
5. `consumeWith(document("orders/create", ...))` gọi callback tài liệu hóa. `requestHeaders(...)` mô tả ba header; `requestFields(...)` mô tả JSON body.

Ví dụ dùng giá trị header xác định để snippet có thể tái tạo. `X-Request-Id` trong hệ thống thật có thể là giá trị khác nhau ở mỗi request; tài liệu hóa mô tả vai trò và định dạng header, không nên phụ thuộc vào một mã truy vết ngẫu nhiên.

## 5. Header bắt buộc và header tùy chọn

Mặc định, descriptor mô tả một header như một phần của hợp đồng. Nếu header chỉ xuất hiện trong một số trường hợp hợp lệ, dùng `.optional()`:

~~~java
requestHeaders(
    headerWithName("X-Request-Id")
        .description("Mã truy vết request"),
    headerWithName("If-Match")
        .description("ETag của phiên bản tài nguyên client đã đọc")
        .optional()
)
~~~

Ví dụ phù hợp với endpoint cập nhật tài nguyên: client có thể gửi `If-Match` để yêu cầu cập nhật có điều kiện, nhưng không phải mọi luồng gọi đều bắt buộc dùng header này.

`.optional()` biểu đạt rằng header được phép vắng mặt trong operation. Nếu header xuất hiện trong request, descriptor vẫn mô tả ý nghĩa của nó. Không đánh dấu optional chỉ để làm test pass khi API thực sự yêu cầu header.

Khi header được đánh dấu bắt buộc nhưng request không gửi, quá trình tạo snippet sẽ thất bại. Đây là tín hiệu để kiểm tra một trong hai việc: test đang thiếu header cần thiết hay hợp đồng API mô tả sai.

## 6. Bỏ header khỏi bảng tài liệu bằng `.ignored()`

Một request có thể chứa header hạ tầng mà tài liệu API không cần trình bày, chẳng hạn header nội bộ của môi trường test. Descriptor hỗ trợ `.ignored()`:

~~~java
requestHeaders(
    headerWithName("X-Request-Id")
        .description("Mã truy vết request"),
    headerWithName("Host")
        .ignored()
)
~~~

`.ignored()` cho biết header được nhận diện trong quá trình tài liệu hóa nhưng không cần xuất hiện như một mục mô tả trong bảng. Đây không phải cách để xóa header khỏi HTTP request thật.

Phân biệt:

| Cách khai báo | Ý nghĩa |
| --- | --- |
| Không khai báo descriptor | Header không nằm trong hợp đồng được mô tả; với snippet nghiêm ngặt, header không được mô tả có thể khiến test thất bại. |
| `.optional()` | Header được phép vắng mặt, nhưng vẫn được mô tả nếu có. |
| `.ignored()` | Header được xử lý nhưng không đưa vào bảng tài liệu. |

Chỉ bỏ qua header khi có lý do rõ ràng. Nếu client cần biết phải gửi `Content-Type`, `Accept`, `If-Match` hoặc một custom header, hãy mô tả nó thay vì đánh dấu ignored.

## 7. Header descriptor và kiểm tra hợp đồng request

`requestHeaders(...)` không đơn thuần tạo một bảng văn bản. Descriptor giúp REST Docs phát hiện sự khác biệt giữa request thực tế với những header đã khai báo.

Ví dụ descriptor:

~~~java
requestHeaders(
    headerWithName("X-Request-Id")
        .description("Mã truy vết request"),
    headerWithName("Content-Type")
        .description("Kiểu nội dung request body")
)
~~~

Nếu request phát sinh một header mới mà snippet nghiêm ngặt chưa mô tả, việc tạo snippet có thể thất bại. Khi đó:

1. Kiểm tra header mới có thuộc hợp đồng công khai không.
2. Nếu client cần biết header đó, thêm `headerWithName(...).description(...)`.
3. Nếu header là tùy chọn, thêm `.optional()` theo đúng quy tắc API.
4. Nếu header chỉ là chi tiết nội bộ, cân nhắc `.ignored()` và giải thích lý do trong code review.

Ngược lại, nếu test khai báo header bắt buộc nhưng request không gửi, REST Docs cũng phát hiện descriptor không khớp. Vì vậy, descriptor làm rõ chính xác các header test đang chứng minh.

## 8. Phân biệt request header với response header

`requestHeaders(...)` mô tả header client gửi tới server. Header server trả về được mô tả bằng `responseHeaders(...)`.

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;

document("orders/create",
    requestHeaders(
        headerWithName("X-Request-Id")
            .description("Mã truy vết request")
    ),
    responseHeaders(
        headerWithName("Location")
            .description("URI của tài nguyên vừa tạo")
    )
)
~~~

| Phía HTTP | API REST Docs | Tệp snippet |
| --- | --- | --- |
| Client → Server | `requestHeaders(...)` | `request-headers.adoc` |
| Server → Client | `responseHeaders(...)` | `response-headers.adoc` |

Không dùng `requestHeaders(...)` để mô tả `Location`, `ETag` hoặc `Cache-Control` do server trả về. Chọn đúng phía giúp tài liệu thể hiện chính xác ai phải gửi hoặc ai tạo ra header đó.

## 9. Nhiều header, header tùy chỉnh và chuẩn hóa tên

### 9.1. Header có nhiều giá trị

Một số header có thể mang nhiều giá trị hoặc danh sách giá trị. Ví dụ `Accept` có thể chứa nhiều media type:

~~~java
client.get()
    .uri("/api/orders")
    .accept(
        MediaType.APPLICATION_JSON,
        MediaType.APPLICATION_XML
    )
    .exchange()
    .expectStatus().isOk();
~~~

Descriptor nên mô tả ý nghĩa của header, đồng thời request snippet thể hiện giá trị thực tế đã gửi. Khi hợp đồng yêu cầu một giá trị cụ thể, hãy kiểm thử cách server xử lý lựa chọn media type tương ứng.

### 9.2. Header tùy chỉnh

Tên header riêng nên có tiền tố rõ nghĩa theo quy ước API của tổ chức:

~~~java
requestHeaders(
    headerWithName("X-Tenant-Id")
        .description("Mã tenant dùng để xác định phạm vi dữ liệu"),
    headerWithName("X-Request-Id")
        .description("Mã truy vết xuyên suốt các dịch vụ")
)
~~~

Tài liệu cần giải thích định dạng, khi nào gửi và ý nghĩa của giá trị. Tránh mô tả mơ hồ như “header tùy chỉnh” nếu client cần hiểu cách tạo giá trị.

### 9.3. Tên header không phân biệt chữ hoa/chữ thường

Tên header HTTP không phân biệt chữ hoa và chữ thường. Dù vậy, nên thống nhất cách viết trong descriptor và tài liệu (thường dùng cách viết chuẩn của API) để người đọc dễ tra cứu. Không dựa vào khác biệt chữ hoa/chữ thường để tạo hai header có ý nghĩa riêng.

## 10. Tiền xử lý dữ liệu header trước khi sinh snippet

Request có thể mang header dùng cho xác thực hoặc nội bộ. Không ghi bí mật thật vào fixture. Với trường hợp test phải gửi một credential giả, có thể loại header nhạy cảm khỏi request snippet bằng preprocessor:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

consumeWith(document("orders/get",
    preprocessRequest(
        modifyHeaders()
            .remove("Authorization")
            .remove("Cookie")
    ),
    requestHeaders(
        headerWithName("X-Request-Id")
            .description("Mã truy vết request")
    )
))
~~~

Preprocessor điều chỉnh bản ghi được dùng để tạo snippet; nó không bỏ header khỏi request đã gửi đến endpoint. Ví dụ trên không mô tả `Authorization` trong bảng header. Nếu API công khai yêu cầu người dùng gửi Authorization, hãy giải thích cơ chế xác thực ở phần tài liệu bảo mật thích hợp và trình bày một giá trị placeholder an toàn theo chiến lược tài liệu của dự án. Không đưa token thật, session cookie hay khóa bí mật vào snippet.

Hãy kiểm tra kết quả `request-headers.adoc` và `http-request.adoc` sau tiền xử lý. Nếu descriptor yêu cầu một header nhưng preprocessor xóa nó khỏi operation trước khi tạo snippet, hãy điều chỉnh thiết kế để header được xử lý nhất quán; đừng giả định descriptor và preprocessor luôn độc lập.

## 11. Đưa `request-headers.adoc` vào Asciidoctor

Sau khi test `orders/create` chạy thành công, Spring REST Docs tạo snippet dưới thư mục operation, thường là:

~~~text
build/generated-snippets/
└── orders/
    └── create/
        ├── http-request.adoc
        ├── request-headers.adoc
        ├── request-fields.adoc
        ├── http-response.adoc
        └── response-body.adoc
~~~

Danh sách trên là các tệp tiêu biểu; tệp thực tế phụ thuộc request, response và descriptor được dùng.

Trong tài liệu Asciidoctor:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Tạo đơn hàng

=== Request headers
include::{snippets}/orders/create/request-headers.adoc[]

=== Request payload
include::{snippets}/orders/create/request-fields.adoc[]

=== HTTP request
include::{snippets}/orders/create/http-request.adoc[]

=== HTTP response
include::{snippets}/orders/create/http-response.adoc[]
~~~

`:snippets:` cần trỏ tới thư mục đúng theo cấu hình build và vị trí file Asciidoctor. Có thể truyền thuộc tính này từ Gradle để tránh hard-code đường dẫn rời rạc.

## 12. Tích hợp vào Gradle và CI

Khi dùng plugin Asciidoctor đã được cấu hình và có task `asciidoctor`, nối task tài liệu với test:

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

`test` sinh snippet và kiểm tra descriptor; `asciidoctor` ghép snippet vào tài liệu. Nếu header bắt buộc thiếu hoặc header mới chưa được mô tả, test tài liệu thất bại và CI không nên tiếp tục xuất bản tài liệu cũ như kết quả mới.

Với Markdown thuần, cú pháp `include::` của Asciidoctor không được xử lý tự động. Cần bước build riêng để chèn nội dung snippet hoặc liên kết đến các tệp đã sinh.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân và hướng giải quyết |
| --- | --- |
| Không tìm thấy `request-headers.adoc` | Kiểm tra test đã gọi `consumeWith(document(..., requestHeaders(...)))` và REST Docs filter đã được thêm vào đúng client. |
| Test lỗi vì thiếu header | Header được mô tả như bắt buộc nhưng request chưa gửi; kiểm tra request builder hoặc đánh dấu optional nếu hợp đồng cho phép. |
| Có header mới khiến snippet thất bại | Bổ sung descriptor cho header công khai hoặc đánh dấu ignored với lý do rõ ràng. |
| Header không cần thiết xuất hiện trong bảng | Xem xét `.ignored()` hoặc thiết kế preprocessor nếu header cần loại khỏi toàn bộ bản ghi. |
| Dùng nhầm `requestHeaders` cho `Location` | `Location` là response header; chuyển sang `responseHeaders(...)`. |
| Header xác thực xuất hiện trong snippet | Dùng credential giả và tiền xử lý bản request trước khi ghi; kiểm tra tệp kết quả trước khi chia sẻ. |
| Mô tả header không đủ rõ | Giải thích mục đích, định dạng, tính bắt buộc và điều kiện gửi header. |
| Asciidoctor không tìm được snippet | Kiểm tra operation identifier, đường dẫn `generated-snippets` và task test phải chạy trước. |

## 14. Bài thực hành

1. Chạy test `OrderRequestHeadersDocumentationTest` và mở `orders/create/request-headers.adoc`.
2. Xóa `.header("X-Request-Id", "doc-test-001")` nhưng giữ descriptor bắt buộc; quan sát test và REST Docs phát hiện request không khớp hợp đồng.
3. Khôi phục header và thêm `If-Match` với descriptor `.optional()`. Chạy test một lần có gửi và một lần không gửi header để kiểm tra hai trường hợp.
4. Thêm một header nội bộ, mô tả bằng `.ignored()` và kiểm tra header đó không xuất hiện trong bảng tài liệu.
5. Thêm descriptor `responseHeaders(...)` cho `Location`, phân biệt nội dung request header và response header.
6. Ghép snippet vào Asciidoctor và cho CI chạy test trước khi dựng tài liệu.

## 15. Ghi nhớ

- `headerWithName(...)` tạo descriptor; `requestHeaders(...)` đưa các descriptor request header vào `document(...)`.
- Mỗi descriptor cần có mô tả cụ thể để client hiểu khi nào và vì sao phải gửi header.
- Header bắt buộc, tùy chọn và bị bỏ khỏi bảng có ý nghĩa khác nhau; dùng `.optional()` và `.ignored()` đúng với hợp đồng API.
- `requestHeaders(...)` mô tả chiều client → server; `responseHeaders(...)` mô tả chiều server → client.
- Descriptor giúp phát hiện request thiếu header hoặc phát sinh header chưa được mô tả; sửa tài liệu và test cùng lúc khi hợp đồng thay đổi.
- Kiểm tra snippet sau tiền xử lý để bảo đảm không lộ bí mật và CI luôn dựng tài liệu từ test vừa chạy thành công.
