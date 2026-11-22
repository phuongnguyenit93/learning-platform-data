# Documented URI và URI dùng trong tài liệu

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, tài liệu REST API được tạo từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào build và CI.

Một bài test có thể chạy ở nhiều môi trường: local, máy developer, CI hoặc container. Host, port và scheme của URL thực tế có thể khác nhau dù endpoint và hợp đồng API không đổi. Nếu ghi nguyên địa chỉ test vào snippet, người đọc có thể nhầm host test với địa chỉ public của API.

Bài học phân biệt URI request thực tế với URI được ghi trong Spring REST Docs, đồng thời hướng dẫn chuẩn hóa URI trong snippet bằng modifyUris(). Sau bài, bạn có thể phân biệt hai loại URI, giải thích scheme/host/port, dùng URI preprocessor theo từng operation hoặc mặc định, và bảo đảm URL tài liệu ổn định giữa các lần build.

## 2. URI thực tế và URI được ghi trong tài liệu

Giả sử test chạy server tại http://localhost:53127 và gọi:

~~~java
client.get()
    .uri("/api/orders/42")
    .exchange();
~~~

Request snippet ban đầu có thể ghi:

~~~http
GET http://localhost:53127/api/orders/42
~~~

Địa chỉ public của API có thể là:

~~~text
https://api.example.com/api/orders/42
~~~

Hai URI cùng trỏ tới endpoint trong ví dụ nhưng phục vụ hai mục đích:

| Khái niệm | Ví dụ | Mục đích |
| --- | --- | --- |
| URI dùng để gửi request | http://localhost:53127/api/orders/42 | Kết nối server đang chạy trong test. |
| URI được ghi trong snippet | https://api.example.com/api/orders/42 | Hướng dẫn client gọi API qua địa chỉ công khai. |

Spring REST Docs preprocessors có thể sửa bản operation dùng để tạo snippet. Chuẩn hóa URI trong tài liệu không đổi đích request mà WebTestClient, MockMvc hoặc REST Assured đã sử dụng.

~~~mermaid
flowchart TD
    A["Test cấu hình client và base URL"] --> B["Gửi HTTP request tới server test"]
    B --> C["Endpoint xử lý và trả response"]
    C --> D["REST Docs ghi nhận HTTP operation"]
    D --> E["Request preprocessor: modifyUris()"]
    E --> F["http-request.adoc với URL tài liệu"]
    F --> G["Asciidoctor / API documentation"]
~~~

Preprocessor chỉ chuẩn hóa dữ liệu tài liệu hóa. Nếu đổi base URL hoặc URI trong cấu hình client, request thực tế sẽ được gửi tới địa chỉ mới.

## 3. Cấu trúc URI và thành phần cần chuẩn hóa

Một URI HTTP có thể gồm scheme, authority, path và query:

~~~text
https://api.example.com:8443/api/orders/42?expand=items
~~~

| Thành phần | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| Scheme | https | Giao thức truy cập. |
| Host | api.example.com | Tên máy chủ hoặc tên miền. |
| Port | 8443 | Cổng server tiếp nhận kết nối. |
| Path | /api/orders/42 | Đường dẫn tới resource. |
| Query | expand=items | Tham số truy vấn. |

Khi chuẩn hóa snippet, thường chỉ thay scheme, host hoặc port để giữ path/query thực tế của operation. Không sửa path/query nếu chúng là một phần của hợp đồng cần tài liệu hóa.

Ví dụ host/port test có thể khác nhau:

- Developer A: http://localhost:8080/api/orders/42
- Developer B: http://localhost:52143/api/orders/42
- CI: http://127.0.0.1:39417/api/orders/42

Snippet nên thể hiện URL mẫu thống nhất: https://api.example.com/api/orders/42.

## 4. Chuẩn hóa URI bằng modifyUris()

Spring REST Docs cung cấp modifyUris() trong nhóm operation preprocessors. API này trả về URI modifier để thiết lập scheme, host, port hoặc loại port khỏi URI được ghi.

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
~~~

Ví dụ chuẩn hóa URL sang host public:

~~~java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("api.example.com")
        .removePort()
)
~~~

Khi dùng trong document():

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
                .host("api.example.com")
                .removePort()
        )
    ));
~~~

Ví dụ giả định client đã được cấu hình REST Docs filter. HTTP request vẫn đến server test, nhưng URL trong request snippet được ghi theo scheme/host public và không có port.

### 4.1. Chọn scheme

~~~java
modifyUris().scheme("https")
~~~

Thích hợp khi tài liệu mô tả API public dùng HTTPS, trong khi test local có thể dùng HTTP. Chỉ đặt https nếu đó là giao thức client phải dùng khi gọi API public.

### 4.2. Chọn host

~~~java
modifyUris().host("api.example.com")
~~~

Host trong snippet không còn phụ thuộc localhost, IP container hoặc hostname CI. Dùng hostname thuộc môi trường mà tài liệu hướng dẫn; không mặc định dùng hostname production nếu tài liệu dành riêng cho sandbox.

### 4.3. Đặt port cố định

~~~java
modifyUris().port(8443)
~~~

Dùng khi API được công bố qua port không mặc định và người dùng cần nhìn thấy port đó. Port trong snippet là port được mô tả cho client, không phải cổng ngẫu nhiên để chạy test.

### 4.4. Loại port

~~~java
modifyUris().removePort()
~~~

Dùng khi muốn URI tài liệu không hiển thị port, ví dụ địa chỉ public dùng cổng HTTPS mặc định. Nếu API bắt buộc chạy ở cổng khác, bỏ port có thể làm hướng dẫn sai.

## 5. Kết hợp scheme, host và port

Chọn cấu hình dựa trên URL người dùng API thực sự cần gọi:

| Mục tiêu tài liệu | Cấu hình gợi ý |
| --- | --- |
| HTTPS trên hostname public, port chuẩn | scheme("https"), host("api.example.com"), removePort() |
| HTTPS trên cổng riêng | scheme("https"), host("api.example.com"), port(8443) |
| Host sandbox | scheme("https"), host("sandbox-api.example.com"), removePort() |
| Chỉ thay hostname | host("api.example.com") |

Ví dụ:

~~~java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("sandbox-api.example.com")
        .port(8443)
)
~~~

Snippet sẽ dùng hostname và port dành cho sandbox. Đảm bảo địa chỉ này có thể truy cập và được hỗ trợ trong môi trường sandbox.

Không đặt host production theo thói quen nếu người đọc cần tài liệu sandbox. Hãy xác định đối tượng tài liệu trước khi chọn scheme, host và port.

## 6. Áp dụng preprocessors cho một operation

Khi chỉ một endpoint có yêu cầu URI đặc biệt, cấu hình ngay trong document():

~~~java
client.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("productId", "BOOK-01", "quantity", 2))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("orders/create",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort()
        )
    ));
~~~

Ưu điểm là quy tắc nằm gần operation và dễ nhận biết endpoint nào có URL tài liệu riêng. Nhược điểm là cấu hình có thể lặp lại khi có nhiều operation.

Có thể kết hợp nhiều request preprocessors, ví dụ chuẩn hóa URI đồng thời loại header nội bộ:

~~~java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("api.example.com")
        .removePort(),
    modifyHeaders()
        .remove("X-Internal-Token")
)
~~~

Mỗi preprocessor xử lý một phần bản request dùng trong snippet. Không dùng URI preprocessor để thay đổi request thật hoặc thay thế assertion kiểm tra endpoint.

## 7. Cấu hình URI mặc định cho nhiều operation

Nếu toàn API dùng chung hostname và scheme tài liệu, tránh lặp cấu hình cho từng document(). Có thể khai báo request preprocessor mặc định trên REST Docs configuration filter:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

WebTestClient client = WebTestClient.bindToController(new OrderController())
    .configureClient()
    .filter(documentationConfiguration(restDocumentation)
        .operationPreprocessors()
            .withRequestDefaults(
                modifyUris()
                    .scheme("https")
                    .host("api.example.com")
                    .removePort(),
                prettyPrint()
            )
    )
    .build();
~~~

withRequestDefaults(...) áp dụng preprocessors cho request operation được tài liệu hóa qua client này. Ví dụ cũng thêm prettyPrint() để chuẩn hóa JSON request body. Có thể cấu hình response defaults riêng bằng withResponseDefaults(...) khi cần.

Khi một operation có quy tắc riêng, truyền preprocessor cụ thể trong document(...) của operation đó. Kiểm tra snippet để xác nhận cách kết hợp default và operation preprocessors phù hợp phiên bản REST Docs dự án đang dùng.

## 8. Ví dụ đầy đủ với WebTestClient

Ví dụ bind vào controller để kiểm thử không cần mở cổng mạng. Client test dùng URI tương đối; preprocessor ghi hostname public vào snippet.

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
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class DocumentedUriTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.client = WebTestClient.bindToController(new OrderController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsOrderUriWithPublicHost() {
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
                        .host("api.example.com")
                        .removePort()
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
        public Mono<Map<String, Object>> getOrder() {
            return Mono.just(Map.of(
                "id", 42,
                "status", "PAID"
            ));
        }
    }
}
~~~

Test gọi /api/orders/42 trong môi trường controller test; request snippet được chuẩn hóa thành URL có https://api.example.com. Path vẫn phản ánh endpoint được test. Ví dụ minh họa URI, còn response descriptor mô tả hai field controller trả về.

## 9. Đối chiếu URI thực tế và snippet

Sau khi test chạy, mở build/generated-snippets/orders/get/http-request.adoc. Kết quả mong đợi có dạng:

~~~http
GET https://api.example.com/api/orders/42 HTTP/1.1
Accept: application/json
~~~

| Nơi quan sát | URI |
| --- | --- |
| Request builder | /api/orders/{id} với giá trị 42 |
| Server test nhận request | Đường dẫn /api/orders/42 trong môi trường bind của test |
| Request snippet | https://api.example.com/api/orders/42 |

Khi test bind bằng server thật, URL thực tế có thể là http://localhost:<port-ngẫu-nhiên>. Sau modifyUris(), snippet vẫn ghi URL public cố định.

Nếu snippet vẫn ghi localhost, kiểm tra:

1. Preprocessor có được truyền vào đúng document(...) không.
2. Đang dùng preprocessRequest(...) cho request snippet hay nhầm sang preprocessResponse(...).
3. Client đã gắn REST Docs filter chưa.
4. Có test nào dùng client khác và bỏ qua default preprocessor không.
5. Tên operation và snippet đang mở có đúng lần chạy mới nhất không.

## 10. URI trong MockMvc và REST Assured

Nguyên tắc tách URI thực tế với URI được tài liệu hóa cũng áp dụng cho các tích hợp khác của Spring REST Docs.

### 10.1. MockMvc

MockMvc tạo request trong môi trường test Servlet; không cần mở cổng HTTP. Có thể áp dụng request preprocessor trong document():

~~~java
mockMvc.perform(get("/api/orders/{id}", 42))
    .andExpect(status().isOk())
    .andDo(document("orders/get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort()
        )
    ));
~~~

Đoạn này giả định mockMvc đã gắn REST Docs MockMvc configuration và các static import get, status, document, preprocessRequest, modifyUris đã được khai báo.

### 10.2. REST Assured

Với REST Assured integration, truyền preprocessor vào callback tài liệu hóa tương ứng:

~~~java
given()
    .accept("application/json")
    .filter(document("orders/get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort()
        )
    ))
    .when()
    .get("/api/orders/42")
    .then()
    .statusCode(200);
~~~

Đoạn minh họa vị trí áp dụng request preprocessor; test thực tế cần REST Docs RestAssuredRestDocumentation filter và cấu hình RestAssured phù hợp. Không trộn filter của WebTestClient với MockMvc/REST Assured.

## 11. Quyết định URI tài liệu cho nhiều môi trường

Một dự án có thể có local, sandbox và production. Không nên để URI trong snippet phụ thuộc môi trường đang chạy test. Chọn một địa chỉ tài liệu rõ ràng:

| Bộ tài liệu | Scheme | Host | Port |
| --- | --- | --- | --- |
| Hướng dẫn local | http | localhost | Port local được quy định trong hướng dẫn |
| Hướng dẫn sandbox | https | sandbox-api.example.com | Bỏ port nếu dùng cổng HTTPS mặc định |
| Hướng dẫn public | https | api.example.com | Bỏ port nếu dùng cổng HTTPS mặc định |

Nếu cần sinh nhiều bộ snippet cho các môi trường, tạo task/test profile riêng với preprocessor riêng. Dùng operation identifier khác nhau hoặc output directory tách biệt để tránh một bộ tài liệu ghi đè snippet của bộ khác.

Địa chỉ xuất hiện trong tài liệu là một cam kết hướng dẫn tích hợp. Kiểm tra nó với cấu hình gateway, DNS, TLS và môi trường người đọc được phép truy cập.

## 12. Tích hợp snippet vào Asciidoctor và CI

Asciidoctor tham chiếu snippet đã được chuẩn hóa:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Lấy đơn hàng

include::{snippets}/orders/get/http-request.adoc[]
include::{snippets}/orders/get/http-response.adoc[]
include::{snippets}/orders/get/response-fields.adoc[]
~~~

Giả sử plugin Asciidoctor đã được cấu hình, có thể nối task tài liệu với test:

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

CI chạy test và tạo snippet mới trước khi dựng tài liệu. Do preprocessor đặt host/scheme/port cố định, URL trong snippet không phụ thuộc port ngẫu nhiên của CI. Khi hostname public thay đổi, cập nhật cấu hình tài liệu cùng quy trình review API.

Với Markdown thuần, include:: không được xử lý tự động. Hãy dùng bước build riêng để nhúng snippet hoặc liên kết tới tệp đã sinh.

## 13. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân và hướng xử lý |
| --- | --- |
| Snippet chứa localhost | Chưa cấu hình modifyUris() hoặc chưa áp dụng preprocessor vào operation đúng. |
| Snippet chứa port ngẫu nhiên | Dùng removePort() hoặc đặt port(...) theo địa chỉ public được công bố. |
| Snippet có HTTPS nhưng API chỉ hỗ trợ HTTP | Scheme tài liệu đặt sai; điều chỉnh theo hợp đồng và gateway thực tế. |
| Request thực tế đi tới sai host sau khi chỉnh tài liệu | Đã đổi base URL/client thay vì chỉ tiền xử lý operation; khôi phục target test và đặt modifyUris() trong REST Docs. |
| Path hoặc query bị thay ngoài ý muốn | Kiểm tra preprocessor và URI builder; chỉ chuẩn hóa thành phần môi trường, giữ path/query của operation. |
| Một số snippet đã chuẩn hóa, một số chưa | Có client/test chưa dùng default preprocessor hoặc operation chưa truyền preprocessor riêng. |
| Asciidoctor hiển thị URL cũ | Chạy clean và bảo đảm task test chạy trước Asciidoctor. |
| Nhiều môi trường ghi đè snippet | Tách output directory hoặc operation identifier theo bộ tài liệu. |

## 14. Bài thực hành

1. Tạo test WebTestClient bind controller; ghi lại request snippet trước khi chuẩn hóa.
2. Thêm modifyUris().scheme("https").host("api.example.com").removePort() và chạy lại test.
3. Đối chiếu URL snippet với URI trong request builder; xác nhận path và query không đổi.
4. Thử port(8443) rồi removePort() và so sánh kết quả snippet.
5. Cấu hình withRequestDefaults(...) cho client để chuẩn hóa URI ở nhiều operation; kiểm tra mọi request snippet.
6. Tạo bộ snippet sandbox và public với hostname khác nhau, dùng output directory riêng.
7. Chạy ./gradlew clean test asciidoctor trong CI và xác nhận URL không chứa hostname/port ngẫu nhiên.

## 15. Ghi nhớ

- URI thực tế dùng để gửi request tới server test; URI documented là địa chỉ được ghi vào snippet để hướng dẫn client.
- modifyUris() chuẩn hóa URI trong bản operation REST Docs dùng để tạo snippet; nó không đổi đích request thực tế.
- Dùng scheme(...), host(...), port(...) hoặc removePort() theo địa chỉ public/sandbox mà tài liệu hướng dẫn.
- Áp dụng preprocessor theo từng operation khi có ngoại lệ; dùng request defaults khi nhiều operation chia sẻ quy tắc.
- Đối chiếu scheme/host/port với môi trường người đọc sẽ gọi; giữ nguyên path và query của endpoint.
- Build/CI chạy test trước Asciidoctor để tài liệu được tạo từ snippet mới với URI ổn định.
