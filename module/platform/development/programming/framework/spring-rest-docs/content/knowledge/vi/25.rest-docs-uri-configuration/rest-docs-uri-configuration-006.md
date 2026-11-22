# WebTestClient URI customization

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, ta tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào build và CI.

Với WebTestClient, URI trong request snippet có một base URL mặc định. Nếu để nguyên, tài liệu thường ghi địa chỉ localhost, dù người đọc API cần gọi hostname sandbox hoặc public. Spring REST Docs hướng dẫn tùy chỉnh base URL được document bằng phương thức `baseUrl(String)` trên `WebTestClient.Builder`.

Sau bài học, bạn có thể:

- Nhận biết base URL mặc định của URI được WebTestClient ghi trong snippet.
- Cấu hình scheme, host và port bằng `configureClient().baseUrl(...)`.
- Hiểu mối quan hệ giữa bindToApplicationContext, bindToController, bindToServer và base URL.
- Phân biệt URL trong request builder, base URL để kết nối server và URI được ghi trong tài liệu.
- Dựng nhiều WebTestClient với địa chỉ local, sandbox hoặc public.
- Xác nhận URL cuối cùng trong http-request.adoc và tích hợp vào Asciidoctor/CI.

## 2. Base URL mặc định của WebTestClient

Khi dùng WebTestClient với Spring REST Docs, base URI mặc định được document là:

~~~text
http://localhost:8080
~~~

Ví dụ test gọi endpoint:

~~~java
webTestClient.get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders/get"));
~~~

Request snippet có thể ghi:

~~~http
GET http://localhost:8080/api/orders/42 HTTP/1.1
~~~

Địa chỉ này là base URL mặc định dùng cho URI được ghi trong snippet. Trong chế độ bind vào controller hoặc ApplicationContext, WebTestClient tạo request/response mô phỏng và không cần kết nối mạng tới localhost:8080. Khi tài liệu cần hướng dẫn client gọi một hostname khác, hãy đặt base URL phù hợp trước khi thực hiện test.

## 3. Cấu hình bằng baseUrl(String)

Spring REST Docs hướng dẫn dùng baseUrl(String) trên WebTestClient.Builder. Với client bind vào ApplicationContext, hãy gọi configureClient() trước, rồi đặt base URL và gắn REST Docs filter:

~~~java
this.webTestClient = WebTestClient.bindToApplicationContext(this.context)
    .configureClient()
    .baseUrl("https://api.example.com")
    .filter(documentationConfiguration(restDocumentation))
    .build();
~~~

Import tĩnh cho REST Docs:

~~~java
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;
~~~

Từ thời điểm này, request URI tương đối như /api/orders/42 được ghi với base URL https://api.example.com.

### 3.1. Đặt scheme

Scheme là phần http hoặc https của URL:

~~~java
.baseUrl("https://api.example.com")
~~~

Chọn https nếu client của API public hoặc sandbox phải kết nối qua TLS. Chỉ dùng http khi môi trường được tài liệu hóa thực sự cho phép HTTP, chẳng hạn một dịch vụ local cô lập.

### 3.2. Đặt host

Hostname là phần tên máy chủ trong base URL:

~~~java
.baseUrl("https://sandbox-api.example.com")
~~~

Dùng hostname đúng với bộ tài liệu đang tạo. Tránh để localhost, IP container hoặc tên máy CI xuất hiện trong hướng dẫn tích hợp dành cho client bên ngoài.

### 3.3. Đặt port

Nếu API được công bố qua port không mặc định, thêm port vào chuỗi base URL:

~~~java
.baseUrl("https://sandbox-api.example.com:8443")
~~~

Với HTTPS port mặc định, thông thường không cần ghi :443:

~~~java
.baseUrl("https://api.example.com")
~~~

baseUrl(String) nhận URL cơ sở đầy đủ. Không có các setter riêng như withScheme(), withHost() hoặc withPort() trong cấu hình WebTestClient này.

## 4. Xác định đúng vai trò của bind mode

WebTestClient hỗ trợ nhiều cách bind. Base URL có vai trò thực tế khác nhau tùy cách client giao tiếp với server:

| Cách bind | Cách hoạt động | Vai trò của baseUrl |
| --- | --- | --- |
| bindToController(...) | Test controller qua mock request/response, không cần server chạy thật. | Cung cấp base cho URI được ghi trong operation và cách phân giải URI tương đối của client. |
| bindToApplicationContext(...) | Test ứng dụng đã cấu hình trong ApplicationContext bằng mock server adapter. | Có thể đặt base URL để snippet dùng hostname/scheme mong muốn mà không gọi mạng tới hostname đó. |
| bindToRouterFunction(...) | Test WebFlux functional endpoint qua mock server. | Dùng như base URI của client trong operation được ghi nhận. |
| bindToServer() | Kết nối tới server đang chạy và gửi HTTP request thật. | Base URL là đích kết nối thật; phải trỏ tới server đang chạy. |

Điểm cần lưu ý: với mock server binding, hostname trong base URL chủ yếu giúp URI được ghi nhận có dạng mong muốn; nó không khởi chạy server ở hostname đó. Với bindToServer(), base URL phải là địa chỉ server thực tế có thể truy cập.

## 5. Ví dụ đầy đủ với bindToApplicationContext

Ví dụ sau cấu hình WebTestClient để snippet dùng URL sandbox:

~~~java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class WebTestClientUriDocumentationTest {

    @Autowired
    private ApplicationContext context;

    private WebTestClient webTestClient;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.webTestClient = WebTestClient.bindToApplicationContext(this.context)
            .configureClient()
            .baseUrl("https://sandbox-api.example.com:8443")
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsOrderWithSandboxBaseUrl() {
        this.webTestClient.get()
            .uri("/api/orders/{id}", 42)
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo(42)
            .consumeWith(document("orders/get",
                responseFields(
                    fieldWithPath("id").description("Mã đơn hàng"),
                    fieldWithPath("status").description("Trạng thái đơn hàng")
                )
            ));
    }

    @RestController
    static class OrderController {

        @GetMapping(
            path = "/api/orders/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        public Mono<Map<String, Object>> getOrder(
                @PathVariable("id") long id) {
            return Mono.just(Map.of(
                "id", id,
                "status", "PAID"
            ));
        }
    }
}
~~~

Ví dụ giả định ApplicationContext có controller GET /api/orders/{id} trả status 200. Request snippet dự kiến bắt đầu như sau:

~~~http
GET https://sandbox-api.example.com:8443/api/orders/42 HTTP/1.1
Accept: application/json
~~~

Test vẫn xử lý request bằng mock server adapter của WebTestClient. Nó không gửi kết nối mạng tới sandbox-api.example.com.

## 6. Ví dụ với bindToController

Khi chỉ cần kiểm tra một controller, có thể bind trực tiếp:

~~~java
WebTestClient webTestClient = WebTestClient.bindToController(new OrderController())
    .configureClient()
    .baseUrl("https://api.example.com")
    .filter(documentationConfiguration(restDocumentation))
    .build();
~~~

Sau đó gọi URI tương đối:

~~~java
webTestClient.get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders/get"));
~~~

Snippet sẽ dùng base URL https://api.example.com. Cách bind này phù hợp với bài test tập trung vào controller; nếu endpoint phụ thuộc filter, security, router hoặc bean cấu hình khác, nên dùng bindToApplicationContext(...) để test đúng hạ tầng cần thiết.

## 7. Ví dụ với bindToServer

Khi WebTestClient kết nối tới ứng dụng đang chạy, baseUrl(...) là địa chỉ kết nối thật:

~~~java
WebTestClient webTestClient = WebTestClient.bindToServer()
    .baseUrl("http://localhost:8080")
    .filter(documentationConfiguration(restDocumentation))
    .build();
~~~

Request được gửi qua mạng tới localhost:8080. Nếu đổi thành https://api.example.com, test sẽ cố kết nối server tại địa chỉ đó; đây không còn chỉ là thay đổi URL xuất hiện trong snippet.

Với integration test dùng server port ngẫu nhiên, hãy lấy port thực tế từ cấu hình test để kết nối. Nếu muốn tài liệu hiển thị hostname public cố định trong khi test kết nối local, cân nhắc dùng mock binding hoặc một cách tiền xử lý operation phù hợp với luồng tích hợp. Không đặt baseUrl public vào bindToServer() nếu server public không phải đích test thực tế.

## 8. Query parameters và path khi đặt base URL

baseUrl(...) chỉ đặt phần nền của URL. Path và query của mỗi operation vẫn do request builder xác định:

~~~java
webTestClient.get()
    .uri("/api/orders/{id}?expand={expand}", 42, "items")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders/get-expanded"));
~~~

Với base URL https://api.example.com, URI được ghi có dạng:

~~~text
https://api.example.com/api/orders/42?expand=items
~~~

Đảm bảo path không lặp prefix. Ví dụ nếu base URL đã chứa /gateway, không thêm /gateway lần nữa vào request URI trừ khi endpoint thật sự có hai đoạn prefix.

Query parameter và path variable vẫn là một phần của hợp đồng API. Không xóa hoặc thay đổi chúng chỉ để URL snippet ngắn hơn.

## 9. Base URL dùng chung và nhiều môi trường

Nếu tất cả operation trong một bộ tài liệu cùng sử dụng một địa chỉ, cấu hình base URL một lần trong phương thức dựng WebTestClient:

~~~java
this.webTestClient = WebTestClient.bindToApplicationContext(this.context)
    .configureClient()
    .baseUrl("https://sandbox-api.example.com")
    .filter(documentationConfiguration(restDocumentation))
    .build();
~~~

Nếu cần tài liệu riêng cho local, sandbox và public, tạo cấu hình/client hoặc test profile tương ứng:

| Bộ tài liệu | Cấu hình base URL |
| --- | --- |
| Local | http://localhost:8080 |
| Sandbox | https://sandbox-api.example.com |
| Sandbox qua port riêng | https://sandbox-api.example.com:8443 |
| Public | https://api.example.com |

Không dùng chung output directory hoặc operation ID nếu các bộ tài liệu được sinh riêng và có URI khác nhau. Nếu dùng chung, snippet của một bộ có thể ghi đè snippet của bộ kia.

## 10. Kiểm tra URI được ghi trong snippet

Sau khi test chạy, mở tệp:

~~~text
build/generated-snippets/orders/get/http-request.adoc
~~~

Với base URL sandbox trong ví dụ, URI đầu request cần có dạng:

~~~http
GET https://sandbox-api.example.com:8443/api/orders/42 HTTP/1.1
Accept: application/json
~~~

Kiểm tra:

1. Scheme có đúng https không.
2. Host có đúng hostname được công bố cho sandbox không.
3. Port có được ghi khi API dùng port không mặc định không.
4. Path variable có được thay bằng giá trị test không.
5. Query string có còn đầy đủ và được encode đúng không.

Nếu snippet vẫn ghi http://localhost:8080, kiểm tra client đang chạy có thực sự gọi baseUrl(...) sau configureClient() không, REST Docs filter có được gắn lên đúng client không, và tệp snippet đang xem có thuộc lần chạy mới nhất không.

## 11. Phân biệt baseUrl(...) và URI preprocessors

Với WebTestClient, cách tùy chỉnh documented URI tiêu chuẩn trong Spring REST Docs là đặt base URL trên builder:

~~~java
WebTestClient.bindToApplicationContext(context)
    .configureClient()
    .baseUrl("https://api.example.com")
    .filter(documentationConfiguration(restDocumentation))
    .build();
~~~

Khác biệt:

| Cách | Tác dụng |
| --- | --- |
| baseUrl(...) | Đặt base URI trong WebTestClient builder; với mock binding nó điều chỉnh URI request được ghi nhận, với bind-to-server nó cũng là đích kết nối. |
| preprocessRequest(...) | Biến đổi bản request operation dùng để tạo snippet sau khi request đã được thực hiện. |

Nếu chỉ cần hostname/scheme thống nhất cho WebTestClient, ưu tiên baseUrl(...). Preprocessor hữu ích khi cần biến đổi request đã ghi nhận theo quy tắc riêng, chẳng hạn chuẩn hóa URI sau khi gửi request thật hoặc loại header nhạy cảm khỏi snippet.

## 12. Tích hợp snippet với Asciidoctor

Spring REST Docs tạo http-request.adoc từ request đã ghi nhận. Asciidoctor có thể include snippet vào tài liệu:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Lấy đơn hàng

include::{snippets}/orders/get/http-request.adoc[]
include::{snippets}/orders/get/http-response.adoc[]
include::{snippets}/orders/get/response-fields.adoc[]
~~~

URL trong request snippet phải phản ánh base URL đã chọn. Nhờ đó, tài liệu cuối cùng chứa địa chỉ sandbox/public ổn định thay vì localhost:8080 ngoài ý muốn.

## 13. Tích hợp Gradle và CI

Giả sử plugin Asciidoctor và task asciidoctor đã được cấu hình, nối task dựng tài liệu với test sinh snippet:

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

Test chạy với base URL được cấu hình, REST Docs sinh snippet và Asciidoctor ghép tài liệu. Khi địa chỉ sandbox/public thay đổi, cập nhật cấu hình base URL cùng thay đổi tài liệu API để tránh snippet cũ.

Với Markdown thuần, cú pháp include:: của Asciidoctor không được xử lý tự động; cần bước build riêng để nhúng snippet hoặc liên kết tới tệp được sinh.

## 14. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân và hướng xử lý |
| --- | --- |
| Snippet vẫn có localhost:8080 | Chưa gọi baseUrl(...), gọi trên builder khác hoặc tệp snippet đang xem là output cũ. |
| Base URL không áp dụng | Với client bind mock, gọi configureClient() trước baseUrl(); gắn REST Docs filter lên đúng builder. |
| Test bind-to-server không kết nối được | baseUrl() là đích mạng thật; kiểm tra server đã chạy và host/port có thể truy cập. |
| Request URI lặp path prefix | Kiểm tra base URL và path truyền vào uri(); không lặp gateway/context prefix. |
| Snippet có hostname CI | Base URL chưa được đặt cố định cho client dùng để tài liệu hóa. |
| Port bị thiếu hoặc sai | Kiểm tra port trong base URL; port chỉ nên được ghi khi địa chỉ public cần port đó. |
| Một số snippet dùng base URL khác | Nhiều WebTestClient instance hoặc test profile đang dùng cấu hình khác nhau. |
| Snippet không được tạo | Kiểm tra REST Docs filter, consumeWith(document(...)), output directory và test result. |

## 15. Bài thực hành

1. Tạo WebTestClient bind ApplicationContext và chạy test khi chưa đặt base URL; mở http-request.adoc.
2. Thêm baseUrl("https://sandbox-api.example.com") sau configureClient() và xác nhận snippet thay hostname.
3. Thử baseUrl("https://sandbox-api.example.com:8443") và kiểm tra port trong URI.
4. Thêm path variable và query parameter; xác nhận base URL không làm thay đổi path/query.
5. Tạo client bindToController(...) và bindToServer() để so sánh base URL có vai trò thế nào với mock request và kết nối HTTP thật.
6. Dựng hai bộ snippet sandbox và public với output directory riêng.
7. Chạy Gradle/CI và kiểm tra URL trong snippet không phụ thuộc hostname/port máy build.

## 16. Ghi nhớ

- Base URI được Spring REST Docs document cho WebTestClient mặc định là http://localhost:8080.
- Dùng configureClient().baseUrl(String) để đặt scheme, host và port cho URI được ghi nhận.
- bindToApplicationContext, bindToController và bindToRouterFunction dùng mock server adapter; hostname base URL trong snippet không mở kết nối mạng tới hostname đó.
- Với bindToServer(), base URL là địa chỉ server thật cần kết nối.
- Path và query của operation vẫn do uri(...) xác định; kiểm tra để tránh lặp prefix.
- Dùng client/configuration riêng cho sandbox và public nếu sinh nhiều bộ tài liệu.
- Chạy test trước Asciidoctor trong CI để tài liệu luôn được dựng từ snippet mới.

## 17. Tài liệu tham khảo

- [Spring REST Docs — Documented URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html): phần WebTestClient URI Customization và cách cấu hình baseUrl(String).
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): các kiểu bind và cấu hình client.
