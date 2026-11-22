# Tránh đưa localhost vào tài liệu công khai với Spring REST Docs

## 1. Vì sao tài liệu API lại xuất hiện localhost?

Khi viết kiểm thử HTTP, môi trường test thường chạy ứng dụng trên địa chỉ cục bộ. Ví dụ, một request được ghi nhận như sau:

```http
GET http://localhost:8080/api/products/42 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

Địa chỉ localhost:8080 phù hợp với máy lập trình hoặc cấu hình MockMvc đang dùng, nhưng thường không phải địa chỉ mà khách hàng, đối tác hay hệ thống bên ngoài dùng để truy cập API đã triển khai. Nếu snippet http-request.adoc, curl-request.adoc hoặc ví dụ URL được công bố nguyên trạng, người đọc có thể sao chép một địa chỉ không thể truy cập từ môi trường của họ.

Tài liệu API nên phân biệt:

- **URI quan sát trong test:** địa chỉ do test client, mock server hoặc cấu hình test tạo ra.
- **Public base URL:** địa chỉ công bố cho người tích hợp, ví dụ https://api.example.com.
- **Path của operation:** phần đường dẫn thuộc API, ví dụ /api/products/{id}.
- **Environment URL:** host khác nhau theo dev, staging, production hoặc vùng triển khai.

Module **SPRING_REST_DOCS** tạo tài liệu REST API có thể kiểm chứng từ kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured; snippet được ghép vào Asciidoctor/Markdown và build/CI. Bài thuộc chương **URI configuration**, tập trung cấu hình URI trong snippet để tài liệu công khai không phụ thuộc localhost.

Sau bài học, bạn có thể:

1. Nhận diện nguồn tạo host, scheme và port trong snippet Spring REST Docs.
2. Cấu hình URI mặc định cho tài liệu MockMvc.
3. Phân biệt URI của test với base URL public và path của operation.
4. Dùng preprocessing hoặc cấu hình phù hợp để chuẩn hóa URI trong snippet.
5. Kiểm tra http-request và curl-request trước khi đưa tài liệu vào CI/publish.

## 2. URI gồm những thành phần nào?

Một absolute URI thường có dạng:

```text
https://api.example.com:443/api/v1/products/42?view=summary
```

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Scheme | https | Giao thức client dùng |
| Host | api.example.com | Tên miền public |
| Port | 443 | Cổng dịch vụ; có thể lược bỏ nếu là cổng mặc định |
| Base path | /api/v1 | Tiền tố triển khai API nếu có |
| Resource path | /products/42 | Đường dẫn tài nguyên |
| Query | view=summary | Tùy chọn/truy vấn của request |

Trong nhiều ví dụ Spring REST Docs với MockMvc, request URI được tạo trong môi trường test và snippet có thể dùng host/port mặc định cục bộ. Public base URL lại có thể đến từ gateway, load balancer, reverse proxy hoặc cấu hình triển khai. Không suy luận public URL từ port mà MockMvc hoặc server test đang dùng.

### 2.1. Tại sao localhost không dùng được cho mọi người?

localhost luôn trỏ về chính máy đang thực hiện request. Khi một người tích hợp chạy:

```bash
curl http://localhost:8080/api/products
```

request được gửi đến máy của họ, không phải server của tổ chức cung cấp API. Host local trong snippet vì vậy thường không phải base URL có thể chia sẻ.

### 2.2. Khi nào localhost vẫn hợp lệ?

Localhost có thể là hướng dẫn đúng nếu tài liệu nói về:

- Chạy ứng dụng demo trên máy cá nhân.
- Khởi động Docker Compose hoặc local development stack.
- Test service mock chỉ tồn tại trong máy lập trình.

Trong trường hợp đó, ghi rõ đây là endpoint local và hướng dẫn cách khởi động service. Với tài liệu API công khai, dùng placeholder hoặc hostname public phù hợp.

## 3. Cấu hình URI trong MockMvc REST Docs

MockMvc không cần chạy HTTP server thật để thực hiện test. Spring REST Docs tích hợp MockMvc cho phép cấu hình URI dùng khi tạo snippet thông qua RestDocumentationContextProvider.

Ví dụ cấu hình URI cho tài liệu:

```java
MockMvcRestDocumentationConfigurer config =
        MockMvcRestDocumentation.documentationConfiguration(restDocumentation);

config.uris()
        .withScheme("https")
        .withHost("api.example.com")
        .withPort(443);

MockMvc mockMvc = MockMvcBuilders.standaloneSetup(controller)
        .apply(config)
        .build();
```

Đây là cách cấu hình URI defaults của MockMvc REST Docs. Trong test suite, thường nhận RestDocumentationContextProvider do RestDocumentationExtension cung cấp:

```java
@ExtendWith(RestDocumentationExtension.class)
class ProductDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        MockMvcRestDocumentationConfigurer config =
                MockMvcRestDocumentation.documentationConfiguration(restDocumentation);

        config.uris()
                .withScheme("https")
                .withHost("api.example.com")
                .withPort(443);

        mockMvc = MockMvcBuilders.standaloneSetup(new ProductController())
                .apply(config)
                .build();
    }
}
```

Sau cấu hình, snippet có thể thể hiện host public đã chọn thay vì localhost. Đảm bảo scheme/host/port thuộc môi trường tài liệu muốn công bố, không phải giá trị tùy tiện.

### 3.1. Chọn port và scheme

Nếu public API dùng HTTPS ở port mặc định 443, đặt https, hostname và port tương ứng. URI renderer có thể lược bỏ port mặc định tùy cách biểu diễn URI; điều quan trọng là scheme/authority chính xác.

Với dịch vụ public dùng port không mặc định, ví dụ 8443:

```java
config.uris()
        .withScheme("https")
        .withHost("partner-api.example.com")
        .withPort(8443);
```

Không đặt port 8080 chỉ vì local server chạy ở port đó nếu gateway public tiếp nhận HTTPS trên authority khác.

## 4. URI của operation và base URL public

Tài liệu nên định nghĩa base URL một lần, sau đó trình bày path của từng operation rõ ràng.

Ví dụ base URL:

```text
https://api.example.com/api/v1
```

Operation:

```text
GET /products/{productId}
POST /products
PATCH /products/{productId}
```

Đây là cách diễn đạt hữu ích vì người đọc có thể chọn môi trường host phù hợp, path operation không phụ thuộc máy chạy test và domain public có thể thay đổi mà route không đổi.

Ví dụ Asciidoctor có thể khai báo attribute:

```asciidoc
:api-base-url: https://api.example.com/api/v1

= Product API

Base URL: {api-base-url}

== Lấy sản phẩm

GET {api-base-url}/products/{productId}
```

Nếu project có nhiều môi trường, công bố base URL theo môi trường:

| Environment | Base URL |
| --- | --- |
| Sandbox | https://sandbox-api.example.com/api/v1 |
| Production | https://api.example.com/api/v1 |

Không đưa địa chỉ local vào phần public. Nếu local development có ích, đặt nó ở mục riêng tên “Chạy API cục bộ”.

## 5. Chuẩn hóa URI bằng operation preprocessors

Spring REST Docs hỗ trợ preprocessors áp dụng lên request/response trước khi tạo snippet. Với MockMvc, có thể dùng modifyUris(...) trong Preprocessors để thay scheme, host hoặc port của request URI.

Ví dụ:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

mockMvc.perform(get("/api/products/{id}", 42))
        .andDo(document("product-detail",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .port(443)
                )));
```

Preprocessor tác động lên operation dùng để sinh snippet. Cách này hữu ích khi chỉ một nhóm operation cần authority khác, test client tạo URI nội bộ nhưng tài liệu cần public URI, hoặc muốn giữ cấu hình MockMvc chung và áp dụng biến đổi ở từng document operation.

Có thể đặt default URI ở config và dùng preprocessor riêng ở những operation cần ngoại lệ. Tránh cấu hình cùng một giá trị ở quá nhiều nơi vì dễ gây bất nhất.

### 5.1. Cẩn thận với URI template và path

modifyUris() thay đổi phần URI theo cấu hình, nhưng không phải công cụ để sửa route contract tùy ý. Base path public như /gateway/api/v1 chỉ nên được thêm hoặc giữ nếu gateway thật sự expose path đó cho client.

Phân biệt:

- Host public khác local host: có thể cấu hình authority.
- Context path khác giữa triển khai và test: xác định path mà client public phải gọi.
- Reverse proxy rewrite path: document external path được gateway expose, không mặc định path nội bộ backend.
- API version: là một phần contract nếu client cần gửi trong path.

## 6. Reverse proxy, gateway và forwarded headers

Trong production, request có thể đi theo đường:

```text
Client
  |
  | https://api.example.com/api/v1/products
  v
API Gateway / Reverse Proxy
  |
  | http://product-service:8080/products
  v
Spring Application
```

Spring application phía sau proxy có thể thấy scheme http, host service nội bộ và port 8080, trong khi client bên ngoài dùng https://api.example.com. Proxy có thể truyền public authority bằng header Forwarded hoặc X-Forwarded-*, tùy hệ thống.

Spring Framework/Spring Boot có thể được cấu hình để xử lý forwarded headers, nhưng behavior phụ thuộc deployment và cấu hình server. Không bật xử lý forwarded headers một cách mù quáng; chỉ tin các header được proxy đáng tin cậy kiểm soát, vì client có thể tự gửi header giả nếu ứng dụng nhận trực tiếp từ internet.

Đối với Spring REST Docs:

1. Dùng authority public đã được xác nhận để sinh snippet.
2. Không dựa vào host nội bộ/container name của backend.
3. Nếu public path có prefix do gateway thêm, thể hiện prefix trong base URL hoặc path operation.
4. Kiểm tra http-request.adoc và curl-request.adoc sau khi sinh.

## 7. Kiểm tra snippet thực tế

Sau khi test chạy, kiểm tra snippet trong output directory, thường là build/generated-snippets với Gradle hoặc target/generated-snippets với Maven.

| Snippet | Điều cần kiểm tra |
| --- | --- |
| http-request.adoc | Request line có host/scheme local không? |
| curl-request.adoc | URL trong lệnh curl có thể dùng bên ngoài không? |
| http-response.adoc | Header response có chứa host nội bộ hoặc thông tin môi trường không? |
| request-parameters/payload snippets | Nội dung operation có phản ánh contract không? |

Ví dụ lệnh curl công khai:

```bash
curl --request GET \
  'https://api.example.com/api/v1/products/42' \
  --header 'Accept: application/json'
```

Thay vì:

```bash
curl --request GET \
  'http://localhost:8080/api/products/42' \
  --header 'Accept: application/json'
```

Lệnh đầu chỉ phù hợp nếu hostname và path đó là endpoint public thật. Trong tài liệu dùng chung nhiều vùng hoặc môi trường, dùng biến/placeholder như $API_BASE_URL và hướng dẫn thiết lập biến trước khi chạy.

## 8. Không dùng preprocessing để che lỗi cấu hình

Preprocessor có thể thay authority trong snippet, nhưng không sửa được test thiết kế sai hoặc route contract không chính xác.

Ví dụ:

- Test gọi /internal/products nhưng public gateway expose /api/v1/products. Chỉ thay host thì path vẫn sai.
- Test chạy trên port 8080, public service dùng host và port khác. Cần xác nhận public endpoint thay vì đoán.
- Test ghi request qua proxy giả, snippet hiển thị URI mà client bên ngoài không thể gọi.
- Test tạo redirect URI trỏ localhost trong response Location. Chỉ đổi request URI không tự sửa URL trong response headers/body.

Đối với response có absolute URL hoặc Location, kiểm tra response snippet và xử lý riêng theo contract nếu cần. Đảm bảo preprocessing không vô tình làm thay đổi business payload hoặc che giấu lỗi.

## 9. WebTestClient và REST Assured

URI được tạo từ test client khác nhau theo cấu hình, nhưng nguyên tắc vẫn là tách test authority khỏi public authority.

### 9.1. WebTestClient

WebTestClient thường được bind với application hoặc server test. URI trong request test có thể dùng base URL cục bộ. Cấu hình URI cho snippet qua preprocessing:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri("/api/products/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("product-detail",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .port(443)
                )));
```

Đây là ví dụ cách gắn request preprocessor vào document snippet. WebTestClient phải được cấu hình REST Docs theo extension/configurer của dự án.

### 9.2. REST Assured

REST Assured có thể tạo request tới base URI test. Filter document cần dùng operation preprocessor tương ứng:

```java
given()
        .filter(documentationFilter(
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .port(443)
                )))
        .when()
        .get("/api/products/42")
        .then()
        .statusCode(200);
```

documentationFilter(...) ở đây là helper minh họa, không phải method universal có sẵn trong mọi cấu hình. Hãy gắn preprocessRequest(...) vào RestAssuredRestDocumentation.document(...) hoặc filter factory mà dự án đang dùng.

## 10. Tổ chức cấu hình để tránh hard-code

Nếu project có nhiều service hoặc environment, không rải hostname trong từng test. Có thể tập trung cấu hình trong test support:

```java
final class ApiDocumentationUris {

    static final String SCHEME = "https";
    static final String HOST = "api.example.com";
    static final int PORT = 443;

    private ApiDocumentationUris() {}

    static MockMvcRestDocumentationConfigurer configure(
            RestDocumentationContextProvider context) {
        MockMvcRestDocumentationConfigurer config =
                MockMvcRestDocumentation.documentationConfiguration(context);
        config.uris()
                .withScheme(SCHEME)
                .withHost(HOST)
                .withPort(PORT);
        return config;
    }
}
```

Dùng trong test:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider context) {
    mockMvc = MockMvcBuilders.standaloneSetup(new ProductController())
            .apply(ApiDocumentationUris.configure(context))
            .build();
}
```

Nếu tài liệu cần nhiều base URL, đưa cấu hình vào property/environment phù hợp với pipeline tài liệu. Tránh dùng production hostname trong test runtime nếu pipeline sinh tài liệu cho sandbox.

## 11. Build, Asciidoctor và CI

Quy trình đề xuất:

1. Chọn public scheme/host/port và base path theo contract API chính thức.
2. Cấu hình URI defaults hoặc request preprocessor cho Spring REST Docs.
3. Chạy test để sinh snippet.
4. Kiểm tra http-request.adoc, curl-request.adoc, response Location và URL tuyệt đối.
5. Ghép snippet bằng Asciidoctor; nếu dùng Markdown, dùng template Markdown và quy trình ghép phù hợp.
6. Thêm bước CI rà soát host nội bộ/local trong thư mục snippet/tài liệu, nhưng cho phép localhost trong đúng mục hướng dẫn local nếu có.

Ví dụ kiểm tra thủ công trên output directory:

```bash
grep -RniE 'localhost|127\\.0\\.0\\.1|0\\.0\\.0\\.0' build/generated-snippets
```

Lệnh cần chạy tại workspace có output snippets. Kết quả tìm thấy không phải lúc nào cũng là lỗi: phân loại theo ngữ cảnh và bảo đảm tài liệu public không tham chiếu nhầm host local. Có thể thêm script CI riêng để kiểm tra vùng docs public.

Ví dụ build Gradle sau khi task đã được cấu hình:

```bash
./gradlew test asciidoctor
```

CI cần thất bại nếu snippet bắt buộc không được sinh hoặc Asciidoctor include file không tồn tại. Tài liệu render thành công nhưng vẫn chứa localhost có thể sai contract, do đó nên có bước kiểm tra URL riêng.

## 12. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| http-request.adoc hiển thị localhost:8080 | URI defaults đang dùng authority test | Cấu hình config.uris() hoặc modifyUris() theo public URL |
| curl-request.adoc gọi host local | Snippet được sinh từ request URI local | Kiểm tra URI preprocessor và output sau test |
| Host đúng nhưng path sai | Public gateway thêm hoặc rewrite context path | Xác nhận external path và cấu hình/ghi base path thích hợp |
| HTTPS public nhưng snippet hiển thị HTTP | Request test hoặc proxy dùng scheme nội bộ | Cấu hình public scheme; kiểm tra forwarded-header handling |
| Port 8080 xuất hiện trong tài liệu public | Nhầm port backend với port gateway | Dùng public port thực tế hoặc lược bỏ port mặc định |
| Response Location vẫn có localhost | Chỉ preprocessing request URI | Kiểm tra response header và URL do ứng dụng tạo |
| CI tìm thấy localhost trong hướng dẫn local | Rule scan không phân biệt docs public và local | Phân vùng tài liệu hoặc whitelist có kiểm soát |
| Nhiều test sinh host khác nhau | Cấu hình URI rải rác hoặc override không nhất quán | Tập trung config và chỉ dùng override có chủ đích |

## 13. Bài tập thực hành

Một service quản lý sản phẩm được chạy trong test bằng MockMvc, nhưng public API được expose ở:

```text
https://catalog.example.com/api/v2
```

Endpoint:

```text
GET /products/{productId}
```

Hãy thực hiện:

1. Tạo MockMvc documentation test cho GET /products/42.
2. Cấu hình Spring REST Docs với scheme https, host catalog.example.com và port phù hợp.
3. Sinh http-request.adoc và curl-request.adoc; xác nhận không có localhost.
4. Nếu gateway public thêm prefix /api/v2, thể hiện prefix trong base URL/path document và xác minh request mà client thật phải gọi.
5. Thêm một operation response có header Location để kiểm tra URL tuyệt đối trong response.
6. Tích hợp test và Asciidoctor vào CI, kèm bước rà soát host nội bộ trong tài liệu public.

**Tiêu chí hoàn thành:** Tài liệu phân biệt rõ URI test và public URL, host/scheme/port đúng, path không thiếu prefix gateway, curl có thể dùng từ máy ngoài môi trường test, và URL tuyệt đối trong response không trỏ về localhost.

## 14. Ghi nhớ

localhost trong snippet thường xuất phát từ URI của môi trường test, không phải public base URL. Cấu hình config.uris() trong MockMvc REST Docs hoặc dùng modifyUris() ở operation preprocessor để chuẩn hóa scheme, host và port cho snippet. Đồng thời xác minh path public, gateway prefix, Location và URL trong response. Kiểm tra output http-request/curl-request sau test và đưa bước rà soát vào CI để tài liệu công khai không hướng người tích hợp về máy local hoặc host backend nội bộ.

### Tài liệu tham khảo

- [Spring REST Docs — Configuring URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html)
- [Spring REST Docs — Operation Preprocessors](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses/preprocessors.html)
- [Spring REST Docs — MockMvc integration](https://docs.spring.io/spring-restdocs/reference/getting-started/using-mock-mvc.html)
- [Spring Framework — Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers)
