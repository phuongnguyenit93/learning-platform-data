# Đặt scheme, host và port cố định

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, ta tạo tài liệu REST API có thể kiểm chứng bằng các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào build và CI.

Khi test chạy trên máy developer hoặc CI, request có thể đi tới localhost, IP container và port được cấp tự động. Những địa chỉ này hữu ích cho test nhưng không phải lúc nào cũng là URL mà người dùng API nên gọi. Spring REST Docs cho phép chuẩn hóa URI được ghi trong snippet bằng cách đặt scheme, host và port cố định.

Sau bài học, bạn có thể:

- Chọn scheme, host và port đúng với môi trường API được tài liệu hóa.
- Dùng modifyUris() để thay các thành phần địa chỉ trong request snippet.
- Phân biệt port cố định, port mặc định và removePort().
- Áp dụng cấu hình cho một operation hoặc mặc định cho nhiều operation.
- Tổ chức cấu hình riêng cho sandbox và public API.
- Kiểm tra kết quả trong http-request.adoc và đưa quy tắc vào Gradle/CI.

## 2. Vì sao cần đặt scheme, host và port cố định?

Giả sử test khởi động ứng dụng trên port ngẫu nhiên:

~~~text
http://localhost:53127/api/orders/42
~~~

Lần chạy tiếp theo, port có thể khác:

~~~text
http://localhost:60418/api/orders/42
~~~

Nếu snippet giữ nguyên URL test, tài liệu được tạo ở mỗi máy có thể không giống nhau. Người đọc cũng có thể sao chép URL localhost hoặc port CI mà không thể truy cập từ môi trường của họ.

Giả sử API có địa chỉ sandbox cố định:

~~~text
https://sandbox-api.example.com/api/orders/42
~~~

REST Docs có thể ghi URL này trong snippet, trong khi test vẫn gọi server kiểm thử. Lợi ích:

| Vấn đề | Kết quả khi chuẩn hóa |
| --- | --- |
| Port test thay đổi | Snippet không phụ thuộc port ngẫu nhiên. |
| Host CI là IP nội bộ | Snippet dùng hostname dành cho người tích hợp. |
| Local test dùng HTTP | Snippet vẫn hướng dẫn HTTPS nếu API public yêu cầu HTTPS. |
| Developer và CI tạo snippet khác nhau | URL trong tài liệu ổn định giữa các môi trường. |

Phải chọn URL phản ánh môi trường mà tài liệu hướng dẫn. Không đặt hostname production nếu người đọc cần kết nối sandbox.

## 3. Cấu trúc scheme, host và port

Xét URI:

~~~text
https://sandbox-api.example.com:8443/api/orders/42
~~~

| Thành phần | Giá trị | Vai trò |
| --- | --- | --- |
| Scheme | https | Giao thức client dùng để kết nối. |
| Host | sandbox-api.example.com | Tên miền hoặc máy chủ API. |
| Port | 8443 | Cổng tiếp nhận kết nối. |
| Path | /api/orders/42 | Đường dẫn endpoint. |

Trong một URL đầy đủ, scheme và host xác định giao thức và máy chủ. Port có thể được ghi rõ hoặc được ngầm định theo scheme. Với HTTPS, port mặc định thường là 443; với HTTP, port mặc định thường là 80.

Phần path thuộc hợp đồng endpoint, vì vậy bài học này tập trung thay đổi scheme, host và port. Không dùng URI modifier để vô tình sửa path hoặc query parameter mà test đang kiểm chứng.

## 4. Sử dụng modifyUris()

Spring REST Docs cung cấp modifyUris() trong nhóm operation preprocessors. URI modifier có thể đặt scheme, hostname và port cho URI được ghi vào snippet.

Import:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
~~~

Ví dụ đặt HTTPS, hostname sandbox và port 8443:

~~~java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("sandbox-api.example.com")
        .port(8443)
)
~~~

Áp dụng trong document():

~~~java
client.get()
    .uri("/api/orders/{id}", 42)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders/get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("sandbox-api.example.com")
                .port(8443)
        )
    ));
~~~

Client vẫn gửi request đến server test. Preprocessor chỉnh URI trong bản operation dùng để sinh snippet. URL được ghi sẽ dùng scheme https, host sandbox-api.example.com và port 8443.

## 5. Đặt scheme

Dùng scheme(...) khi URL tài liệu cần giao thức cố định:

~~~java
modifyUris().scheme("https")
~~~

Chọn scheme theo cách client thật sự phải kết nối:

| Scheme trong tài liệu | Trường hợp sử dụng |
| --- | --- |
| https | API được công bố qua TLS/HTTPS. |
| http | Chỉ dùng khi môi trường hướng dẫn thực sự cho phép HTTP, ví dụ một endpoint local cô lập. |

Không ghi HTTPS chỉ để URL trông giống production nếu sandbox hoặc gateway thực tế không hỗ trợ TLS. Ngược lại, không để snippet dùng HTTP nếu hợp đồng yêu cầu client kết nối qua HTTPS.

Khi API nằm sau reverse proxy hoặc API gateway, hostname và scheme công khai có thể khác địa chỉ nội bộ mà ứng dụng nhận ở backend. URI trong tài liệu nên phản ánh địa chỉ mà client được yêu cầu sử dụng.

## 6. Đặt host

Dùng host(...) để thay hostname được ghi:

~~~java
modifyUris().host("api.example.com")
~~~

Các hostname thường gặp:

| Mục tiêu | Host trong snippet |
| --- | --- |
| API local | localhost |
| Sandbox | sandbox-api.example.com |
| Public API | api.example.com |

Trong test bind trực tiếp vào controller hoặc ApplicationContext, request builder có thể dùng URI tương đối. URI đầy đủ trong snippet có thể được chuẩn hóa bằng preprocessor.

Với server test thật, client có thể gọi localhost hoặc một hostname container. Việc đặt host trong modifyUris() không làm client kết nối tới hostname mới; nó chỉ thay host trong dữ liệu tài liệu hóa.

Không dùng hostname giả mà người đọc không thể phân giải. Các tên example.com trong bài là dữ liệu minh họa; dự án cần thay bằng domain sandbox/public đã được công bố.

## 7. Đặt port cố định

Dùng port(...) khi địa chỉ tài liệu cần một port cụ thể:

~~~java
modifyUris()
    .scheme("https")
    .host("sandbox-api.example.com")
    .port(8443)
~~~

Kết quả URL:

~~~text
https://sandbox-api.example.com:8443/api/orders/42
~~~

Port trong snippet cần là port mà client thực sự có thể truy cập. Không dùng port ngẫu nhiên của server test hoặc port do CI cấp.

### 7.1. Khi dùng port không mặc định

Nếu API sandbox được công bố qua port 8443, hãy giữ port trong tài liệu:

~~~java
modifyUris()
    .scheme("https")
    .host("sandbox-api.example.com")
    .port(8443)
~~~

Port này là một phần của địa chỉ tích hợp. Nếu gateway chuyển tiếp qua port nội bộ khác, tài liệu vẫn dùng port công khai mà client phải gọi.

### 7.2. Khi dùng port mặc định

Nếu API public dùng HTTPS trên port mặc định, URL thông thường có thể được viết mà không cần phần :443:

~~~text
https://api.example.com/api/orders/42
~~~

Có thể gọi removePort() để loại port khỏi URI được ghi:

~~~java
modifyUris()
    .scheme("https")
    .host("api.example.com")
    .removePort()
~~~

Không loại port nếu API public yêu cầu một cổng không mặc định. Hãy xem port là một phần của địa chỉ client cần dùng.

## 8. Chọn giữa port(), removePort() và giữ port

| Cấu hình | Kết quả mong muốn | Khi dùng |
| --- | --- | --- |
| port(8443) | Ghi port 8443 | API được công bố ở cổng riêng. |
| removePort() | Không ghi port | Địa chỉ public dùng cổng mặc định hoặc tài liệu không cần phần port. |
| Không gọi port modifier | Giữ port trong URI nguồn | Port nguồn đã là port cố định đúng với tài liệu. |

Lựa chọn ví dụ:

~~~java
// API public HTTPS trên cổng chuẩn
modifyUris().scheme("https").host("api.example.com").removePort();

// API sandbox HTTPS trên cổng 8443
modifyUris().scheme("https").host("sandbox-api.example.com").port(8443);
~~~

Không dùng đồng thời port(...) và removePort() trong cùng một cấu hình URI. Chọn một chính sách rõ ràng để người đọc snippet không phải suy đoán.

## 9. Cấu hình theo từng operation

Khi chỉ một số endpoint cần địa chỉ khác nhau, đặt modifier trong document(...) của operation:

~~~java
client.get()
    .uri("/api/orders/{id}", 42)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders/get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("sandbox-api.example.com")
                .port(8443)
        )
    ));
~~~

Operation khác có thể dùng hostname public:

~~~java
client.get()
    .uri("/api/catalog")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("catalog/list",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort()
        )
    ));
~~~

Cấu hình theo operation làm rõ snippet nào dùng hostname nào. Cách này phù hợp nếu tài liệu mô tả nhiều API gateway, nhiều tenant endpoint hoặc một số route có domain riêng.

## 10. Cấu hình mặc định cho nhiều operation

Nếu tất cả operation trong một bộ tài liệu dùng chung scheme, host và port, đặt preprocessor mặc định khi cấu hình REST Docs filter:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

WebTestClient client = WebTestClient.bindToController(new OrderController())
    .configureClient()
    .filter(documentationConfiguration(restDocumentation)
        .operationPreprocessors()
            .withRequestDefaults(
                modifyUris()
                    .scheme("https")
                    .host("sandbox-api.example.com")
                    .port(8443)
            )
    )
    .build();
~~~

withRequestDefaults(...) áp dụng URI modifier mặc định cho các request operation được tài liệu hóa qua client này. Những operation dùng cùng endpoint base có thể chia sẻ một cấu hình và giảm lặp code.

Nếu một operation có địa chỉ đặc biệt, truyền preprocessor riêng vào document(...) của operation đó. Sau khi cấu hình mặc định và cấu hình riêng cùng được dùng, hãy mở snippet thực tế để xác nhận quy tắc được áp dụng theo đúng kỳ vọng của dự án và phiên bản REST Docs.

### 10.1. Mặc định cho request và response

URI trong HTTP request snippet là trường hợp cần chuẩn hóa phổ biến nhất. REST Docs cũng có response preprocessors để xử lý nội dung response. Nếu cần cấu hình mặc định response, dùng withResponseDefaults(...) cho các response preprocessors phù hợp. Không áp dụng URI request modifier cho response body; chỉ dùng ở vị trí xử lý URI của operation.

## 11. Ví dụ hoàn chỉnh với WebTestClient

Ví dụ sau bind vào controller để test không cần mở cổng mạng. Request builder dùng URI tương đối, còn snippet được ghi bằng địa chỉ sandbox cố định.

~~~java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class FixedUriDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.client = WebTestClient.bindToController(new OrderController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsOrderWithFixedSandboxAddress() {
        client.get()
            .uri("/api/orders/{id}", 42)
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo(42)
            .consumeWith(document("orders/get",
                preprocessRequest(
                    modifyUris()
                        .scheme("https")
                        .host("sandbox-api.example.com")
                        .port(8443)
                ),
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

Trong test, request đi tới controller test và path thực tế là /api/orders/42. Snippet được chuẩn hóa thành:

~~~http
GET https://sandbox-api.example.com:8443/api/orders/42 HTTP/1.1
Accept: application/json
~~~

Thay đổi scheme, host và port chỉ tác động bản operation REST Docs dùng để tạo snippet. Request builder vẫn không kết nối tới sandbox-api.example.com.

## 12. Xác minh URL cuối cùng trong snippet

Sau khi test chạy, mở:

~~~text
build/generated-snippets/orders/get/http-request.adoc
~~~

Với cấu hình ví dụ, URL mong đợi là:

~~~text
https://sandbox-api.example.com:8443/api/orders/42
~~~

Kiểm tra các điểm:

1. Scheme là https.
2. Host là sandbox-api.example.com.
3. Port là 8443.
4. Path vẫn là /api/orders/42.
5. Query parameter (nếu có) vẫn giữ nguyên và được encode đúng.

Nếu URI snippet không đúng, kiểm tra request preprocessor đã được truyền vào đúng document(...) chưa, client có REST Docs filter hay chưa và operation identifier đang xem có thuộc lần chạy gần nhất không.

## 13. Tổ chức cấu hình cho nhiều môi trường

Một dự án có thể tạo bộ tài liệu local, sandbox và public. Mỗi bộ tài liệu nên có địa chỉ cố định riêng:

| Bộ tài liệu | Scheme | Host | Port |
| --- | --- | --- | --- |
| Local | http | localhost | 8080 hoặc port hướng dẫn cố định |
| Sandbox | https | sandbox-api.example.com | 8443 |
| Public | https | api.example.com | Mặc định HTTPS, bỏ port khỏi URL |

Nếu cần nhiều bộ snippet, dùng profile hoặc task riêng để chọn preprocessor. Dùng thư mục output và operation identifier riêng biệt để tránh tài liệu của môi trường này ghi đè tài liệu môi trường khác.

Không lấy port ngẫu nhiên của test làm port trong tài liệu. Địa chỉ ghi trong snippet cần được xác nhận với cấu hình gateway, DNS và TLS của môi trường tương ứng.

## 14. Tích hợp Asciidoctor, Gradle và CI

Asciidoctor có thể include request snippet đã chuẩn hóa:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Lấy đơn hàng

include::{snippets}/orders/get/http-request.adoc[]
include::{snippets}/orders/get/http-response.adoc[]
include::{snippets}/orders/get/response-fields.adoc[]
~~~

Giả sử plugin Asciidoctor và task asciidoctor đã được cấu hình:

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

CI tạo snippet mới từ test trước khi dựng tài liệu. Khi scheme, hostname hoặc port công khai thay đổi, cập nhật cấu hình preprocessors và review URL trong snippet cùng thay đổi hạ tầng. Với Markdown thuần, cần bước build riêng để nhúng hoặc liên kết snippet; include:: là cú pháp của Asciidoctor.

## 15. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân và hướng xử lý |
| --- | --- |
| Snippet vẫn có localhost | Chưa áp dụng modifyUris() cho operation hoặc client chưa dùng REST Docs filter. |
| Snippet vẫn có port ngẫu nhiên | Chọn port(...) cố định hoặc removePort() theo địa chỉ công khai. |
| URL chứa HTTPS nhưng gateway chỉ hỗ trợ HTTP | Scheme tài liệu không phản ánh endpoint public; kiểm tra cấu hình gateway/TLS. |
| Host sandbox bị thay bằng public host | Kiểm tra cấu hình default và preprocessor riêng của operation. |
| URL không có port dù API cần cổng 8443 | Không dùng removePort(); đặt port(8443). |
| URL có :443 dù muốn dạng HTTPS mặc định | Dùng removePort() và xác nhận gateway cho phép truy cập qua cổng mặc định. |
| Request thực tế bị gửi tới host tài liệu | Đã sửa base URL của client thay vì chỉ sửa bản ghi bằng preprocessor. |
| Path bị thay đổi | Chỉ sửa scheme/host/port; không viết lại URI path nếu endpoint không thay đổi. |
| Asciidoctor lấy snippet cũ | Chạy clean và bảo đảm test hoàn tất trước task asciidoctor. |

## 16. Bài thực hành

1. Chạy test WebTestClient bind controller và mở http-request.adoc trước khi thêm URI modifier.
2. Cấu hình scheme https, host sandbox-api.example.com và port 8443; chạy lại test và so sánh URL.
3. Thay port(8443) bằng removePort(); kiểm tra phần port trong snippet.
4. Tạo một operation public dùng api.example.com và bỏ port mặc định.
5. Chuyển cấu hình sandbox thành withRequestDefaults(...) cho client; xác nhận các operation dùng chung địa chỉ.
6. Tạo hai task/profile snippet sandbox và public, lưu output ở hai thư mục riêng.
7. Chạy Gradle/CI và kiểm tra không snippet nào chứa hostname hoặc port test ngẫu nhiên.

## 17. Ghi nhớ

- modifyUris() đặt scheme, host và port trong URI được ghi vào REST Docs snippet.
- scheme("https") và host("...") giúp URL tài liệu ổn định giữa local, container và CI.
- port(8443) giữ port công khai không mặc định; removePort() bỏ port khỏi snippet khi địa chỉ dùng cổng mặc định.
- Không dùng port test ngẫu nhiên làm port tài liệu và không đặt hostname production nếu tài liệu dành cho sandbox.
- Cấu hình trong document(...) cho ngoại lệ; withRequestDefaults(...) cho các operation dùng chung một địa chỉ.
- URI preprocessor không đổi đích request thực tế; hãy xác minh URL cuối cùng trong http-request.adoc.
- Chạy test trước Asciidoctor trong CI để tài liệu luôn được tạo từ snippet mới.
