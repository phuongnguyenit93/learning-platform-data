# Xác nhận URI sinh ra phù hợp môi trường triển khai

## 1. URI trong snippet phải phản ánh đúng nơi client gọi API

Một API có thể được triển khai ở nhiều môi trường:

| Môi trường | Base URL công bố |
| --- | --- |
| Local development | `http://localhost:8080` |
| Integration test | `http://api.test.internal:8080` |
| Staging | `https://staging-api.example.com` |
| Production | `https://api.example.com` |

Các môi trường có thể cùng phục vụ operation:

```http
GET /v1/orders/42 HTTP/1.1
Accept: application/json
```

Nhưng URI đầy đủ khác nhau. Snippet tài liệu được sinh từ test thường phản ánh cấu hình của test client. Nếu tài liệu staging lại chứa `localhost`, hostname nội bộ hoặc port ngẫu nhiên, người tích hợp sẽ gọi nhầm địa chỉ.

Module **SPRING_REST_DOCS** tạo tài liệu REST API có thể kiểm chứng từ kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Các test sinh snippet request, response, payload, parameter và header; sau đó biên soạn thành Asciidoctor/Markdown và đưa vào build/CI. Bài thuộc chương **URI configuration**, tập trung xác nhận URI cuối cùng trong snippet khớp với môi trường triển khai mà tài liệu đang mô tả.

Sau bài học, bạn có thể phân biệt URI chạy test với URI công bố, cấu hình scheme/host/port/context path/base URL theo test client, chọn môi trường mục tiêu rõ ràng, kiểm tra URL trong request/cURL/response Location và tự động phát hiện hostname/port không phù hợp trong CI.

## 2. Thành phần của URI triển khai

Ví dụ:

```text
https://staging-api.example.com:8443/platform/v1/orders/42?expand=items
```

| Thành phần | Giá trị | Cần xác nhận |
| --- | --- | --- |
| Scheme | https | Client dùng HTTP hay HTTPS |
| Host | staging-api.example.com | DNS public hay hostname nội bộ |
| Port | 8443 | Port công bố; có thể lược bỏ nếu mặc định |
| Context/base path | /platform | Prefix do ứng dụng hoặc gateway expose |
| API version | /v1 | Version thuộc contract hay do gateway thêm |
| Resource path | /orders/42 | Route của operation |
| Query string | expand=items | Parameter và encoding |

Một URI chỉ phù hợp khi các thành phần nhất quán. Đổi host từ localhost sang api.example.com vẫn chưa đủ nếu tài liệu thiếu /platform/v1 hoặc dùng sai scheme.

### 2.1. Tách base URL khỏi operation path

Base URL:

```text
https://api.example.com/platform/v1
```

Operation path:

```text
GET /orders/{orderId}
POST /orders
PATCH /orders/{orderId}
```

Cách tách này giúp đổi môi trường mà không phải viết lại từng route. Xác định prefix nào thuộc base URL và prefix nào thuộc resource path để tránh lặp hoặc bỏ sót.

### 2.2. Context path và proxy prefix là hai nguồn khác nhau

Ứng dụng có thể có context path /platform, trong khi gateway thêm /public. Khi đó URL client có thể là:

```text
https://api.example.com/public/platform/v1/orders/42
```

Nếu test đã gọi route chứa prefix đầy đủ, không thêm cùng prefix lần nữa khi cấu hình URI. Nếu test gọi backend trực tiếp, hãy xác nhận public route qua gateway trước khi tạo tài liệu. URI preprocessor thay authority không tự suy luận hay xác minh route public.

## 3. Chọn môi trường mục tiêu trước khi sinh snippet

| Artifact | URI nên dùng |
| --- | --- |
| Hướng dẫn chạy local | Local URL và hướng dẫn khởi động service |
| Tài liệu tích hợp sandbox | Sandbox/staging base URL |
| Tài liệu phát hành production | Production base URL đã công bố |
| Test contract nội bộ | URI test; không mặc định dùng làm public docs |

Một dự án có thể phát hành bản tài liệu riêng cho sandbox và production. Nếu chỉ có một bản, chọn base URL chính thức và ghi rõ môi trường trong phần giới thiệu.

### 3.1. Dùng test property thay vì rải hostname

Quản lý mục tiêu document bằng property:

```yaml
docs:
  api:
    scheme: https
    host: staging-api.example.com
    port: 443
    base-path: /platform/v1
```

Đây là cấu hình dành cho bộ tài liệu staging. Khi build production docs, dùng profile/property riêng đã được review:

```yaml
docs:
  api:
    scheme: https
    host: api.example.com
    port: 443
    base-path: /platform/v1
```

Tránh lấy host và port từ biến môi trường không được kiểm soát rồi publish artifact mà không xác minh. Pipeline cần ghi rõ profile nào tạo tài liệu.

## 4. Cấu hình URI cho MockMvc

Theo cấu hình mặc định của Spring REST Docs, URI được document bởi MockMvc dùng:

| Setting | Default |
| --- | --- |
| Scheme | http |
| Host | localhost |
| Port | 8080 |

Thay đổi các giá trị này thông qua `MockMvcRestDocumentationConfigurer.uris()`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
                .apply(documentationConfiguration(restDocumentation).uris()
                        .withScheme("https")
                        .withHost("staging-api.example.com")
                        .withPort(443))
                .build();
    }
}
```

Khi port là mặc định của scheme — 80 cho HTTP hoặc 443 cho HTTPS — port được lược bỏ khỏi URI trong snippet. HTTPS trên port 443 thường hiển thị là `https://staging-api.example.com/...`.

### 4.1. Context path

MockMvc cho phép đặt context path trên request builder:

```java
mockMvc.perform(get("/orders/{id}", 42)
        .contextPath("/platform")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("order-detail"));
```

Đảm bảo context path phản ánh cách ứng dụng được expose trong môi trường tài liệu. Đừng đưa API version vào context path nếu version đó đã có trong route hoặc base URL.

### 4.2. Dùng Spring Boot AutoConfigureRestDocs

Trong test tích hợp Spring Boot, `@AutoConfigureRestDocs` có thể cấu hình host, scheme và port xuất hiện trong documented URIs:

```java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(
        uriScheme = "https",
        uriHost = "staging-api.example.com",
        uriPort = 443)
class OrderDocumentationTest {
    // Inject MockMvc and document requests.
}
```

Nếu cần kiểm soát nhiều hơn, Spring Boot cung cấp `RestDocsMockMvcConfigurationCustomizer`. Chọn một cơ chế cấu hình chính để tránh annotation và customizer ghi đè nhau ngoài ý muốn.

## 5. Cấu hình URI cho WebTestClient

Spring REST Docs sử dụng base URI mặc định `http://localhost:8080` khi document WebTestClient. Có thể tùy chỉnh base bằng `baseUrl(String)` trên `WebTestClient.Builder`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class ReactiveOrderDocumentationTest {

    private WebTestClient webTestClient;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.webTestClient = WebTestClient.bindToApplicationContext(context)
                .configureClient()
                .baseUrl("https://staging-api.example.com/platform/v1")
                .filter(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

`baseUrl(...)` cấu hình base được dùng trong URI đã document. Khi bind với mock server hoặc application context, nó không có nghĩa request thật đi qua DNS/public gateway. Nếu cần xác minh mạng, TLS termination hoặc gateway routing, hãy có integration test gửi qua môi trường tương ứng.

### 5.1. Khi test dùng server random port

Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, server thật lắng nghe một port được chọn khi test chạy. WebTestClient có thể kết nối server đó. Cần phân biệt:

- Port random là đích gửi request của test.
- Base URL trong snippet là địa chỉ được document.

Đừng công bố port random như một phần API contract. Với test chạy server thật, cấu hình client sao cho request vẫn đi đúng server trong test, còn tài liệu phát hành có base URL ổn định theo môi trường.

## 6. Cấu hình URI cho REST Assured

REST Assured thực hiện HTTP request thật. `baseURI`, `port` và `basePath` quyết định địa chỉ đích:

```java
RequestSpecification testApi = new RequestSpecBuilder()
        .setBaseUri("http://localhost")
        .setPort(53142)
        .setBasePath("/internal-api")
        .build();
```

Nếu URI trong snippet cần khác URI test, áp dụng REST-Assured-specific preprocessor sau khi operation đã được thực hiện nhưng trước khi document:

```java
given(testApi)
        .filter(document("order-detail",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("staging-api.example.com")
                                .removePort()
                )))
        .when()
        .get("/orders/42")
        .then()
        .statusCode(200);
```

Preprocessor chỉ thay URI được ghi trong snippet, không đổi đích gửi request. Nếu test gọi /internal-api/orders/42, snippet sau khi đổi authority vẫn có path /internal-api/orders/42. Chỉ document path đó nếu nó đúng public route.

## 7. Kiểm tra response URL và Location

Không chỉ request line mới chứa absolute URI. API có thể trả header Location hoặc link trong JSON:

```http
HTTP/1.1 201 Created
Location: https://staging-api.example.com/platform/v1/orders/42
Content-Type: application/json

{
  "id": "42",
  "self": "https://staging-api.example.com/platform/v1/orders/42"
}
```

Kiểm tra các URL này có cùng scheme, host và base path với môi trường tài liệu. Một request snippet đúng host nhưng response Location vẫn chứa hostname nội bộ là tài liệu không nhất quán.

Với REST Assured hoặc tích hợp khác, nếu response URL cần chuẩn hóa cho snippet, dùng response preprocessor thích hợp. Nhưng nếu ứng dụng production thực sự tạo URL sai, đừng chỉ sửa snippet để che lỗi. Hãy sửa cấu hình proxy/URL generation rồi kiểm thử response runtime.

## 8. Ma trận kiểm chứng URI theo môi trường

Trước khi phát hành tài liệu, tạo bảng expected URI:

| Thành phần | Local | Staging | Production |
| --- | --- | --- | --- |
| Scheme | http | https | https |
| Host | localhost | staging-api.example.com | api.example.com |
| Port | 8080 | 443 | 443 |
| Base path | / | /platform/v1 | /platform/v1 |
| Operation | /orders/42 | /orders/42 | /orders/42 |

Sau khi test sinh snippet, đối chiếu URL thực tế với cột môi trường đang build. Kiểm tra riêng:

1. `http-request.adoc` — request line và Host header.
2. `curl-request.adoc` — URL người dùng sẽ sao chép.
3. `http-response.adoc` — Location hoặc header URI khác.
4. `response-body.adoc` — absolute links trong payload nếu có.
5. Trang Asciidoctor/Markdown — base URL và hướng dẫn chọn môi trường.

## 9. Tự động hóa xác nhận URI trong CI

Một bước kiểm tra đơn giản có thể rà soát output snippets sau khi chạy test:

```bash
grep -RniE 'localhost|127\\.0\\.0\\.1|0\\.0\\.0\\.0|:8080|internal-api' build/generated-snippets
```

Lệnh trên chỉ tìm dấu hiệu cần review. Kết quả có thể hợp lệ với test local, nên CI cho staging/production cần so khớp allowlist/denylist với environment đang build thay vì cấm chuỗi tuyệt đối.

Ví dụ các điều kiện cho build staging:

- Host document phải là `staging-api.example.com`.
- URI scheme phải là `https`.
- Port 443 không xuất hiện tường minh nếu snippet lược bỏ port mặc định.
- Public base path phải có `/platform/v1`.
- Không có localhost, host service nội bộ hoặc port random.
- Location và absolute link trong response phải cùng public authority.

Nếu dự án có nhiều bộ tài liệu, lưu artifact riêng theo môi trường hoặc gắn nhãn rõ trong pipeline. Không ghi đè staging docs bằng production docs từ build không phân biệt.

### 9.1. Asciidoctor và Markdown

Với Asciidoctor, tập trung base URL thành attribute:

```asciidoc
:api-base-url: https://staging-api.example.com/platform/v1

= Order API

Base URL: {api-base-url}

== Lấy đơn hàng

GET {api-base-url}/orders/{orderId}

include::{snippets}/order-detail/http-request.adoc[]
include::{snippets}/order-detail/http-response.adoc[]
```

Khi build production, thay attribute bằng giá trị production đã được phê duyệt. Với Markdown, dùng template format Markdown của Spring REST Docs và cơ chế ghép snippet của dự án; giữ cùng nguyên tắc cấu hình một base URL rõ ràng.

## 10. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Snippet staging có localhost | MockMvc/WebTestClient chưa override default URI | Cấu hình .uris() hoặc .baseUrl() |
| Snippet dùng sai port | Nhầm port test server với public port | Document port của môi trường mục tiêu |
| Host đúng nhưng URL 404 | Thiếu hoặc lặp context/base path | Xác minh route qua gateway |
| HTTP xuất hiện trong tài liệu HTTPS | Scheme chưa được cấu hình | Đặt scheme HTTPS cho URI documented |
| Request đúng nhưng Location sai | Response tạo absolute URL từ request nội bộ | Kiểm tra proxy handling và URL generation |
| Mỗi máy developer sinh hostname khác nhau | Lấy URI từ cấu hình cục bộ không ổn định | Dùng profile/property được kiểm soát |
| Tài liệu production bị ghi bằng staging URL | Pipeline không phân biệt artifact theo environment | Tách task/profile/output và kiểm tra URI trước publish |
| REST Assured test gọi nhầm server | Đã thay baseURI khi chỉ muốn thay URI snippet | Giữ test destination; dùng REST Docs preprocessor |

## 11. Bài tập thực hành

Một API quản lý đơn hàng có ba môi trường:

```text
Local:      http://localhost:8080
Staging:    https://staging-api.example.com/platform/v1
Production: https://api.example.com/platform/v1
```

Operation:

```text
GET /orders/{orderId}
POST /orders
```

Hãy thực hiện:

1. Tạo MockMvc test cho GET /orders/42, cấu hình scheme/host/port và context path phù hợp.
2. Tạo WebTestClient test và cấu hình baseUrl(...) cho staging docs.
3. Tạo REST Assured test dùng local random port nhưng document URI staging bằng preprocessor.
4. Với POST /orders, kiểm tra header Location và absolute link trong response body.
5. Sinh http-request, curl-request, http-response và response body snippets.
6. Tạo ma trận URI expected cho staging, thêm bước CI xác nhận host, scheme, port và base path.
7. Render Asciidoctor/Markdown và kiểm tra mọi URL người tích hợp có thể sao chép.

**Tiêu chí hoàn thành:** Mỗi test gửi request đến đúng server test; snippet thể hiện đúng môi trường mục tiêu; scheme/host/port/base path nhất quán; URL trong response không rò hostname nội bộ; CI phát hiện URI sai trước khi publish.

## 12. Ghi nhớ

URI trong snippet phải khớp với môi trường mà tài liệu mô tả. MockMvc có default `http://localhost:8080` và hỗ trợ `.uris()` để cấu hình scheme/host/port; WebTestClient dùng `.baseUrl()`; REST Assured cần preprocessor riêng vì nó gửi request thật. Context path, gateway prefix và resource path cần được xác nhận độc lập. Kiểm tra request line, cURL, Location và absolute links trong response; dùng profile/property ổn định và ma trận URI trong CI để ngăn tài liệu local, staging và production bị trộn lẫn.

### Tài liệu tham khảo

- [Spring REST Docs — Documented URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html)
- [Spring REST Docs — Configuration and Operation Preprocessors](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
- [Spring Boot — Auto-configured Spring REST Docs Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
