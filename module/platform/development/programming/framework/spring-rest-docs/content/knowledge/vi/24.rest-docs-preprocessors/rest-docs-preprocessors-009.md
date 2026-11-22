# Modifying URIs và documented URI

## 1. Vì sao URI trong snippet có thể khác URI test?

Trong module **SPRING_REST_DOCS**, các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured vừa xác minh hành vi API vừa tạo generated snippets. Test chạy cục bộ có thể dùng địa chỉ:

```text
http://localhost:8080/api/orders/42
```

Trong khi địa chỉ client tích hợp cần gọi là:

```text
https://api.example.com/api/orders/42
```

Ứng dụng production có thể nằm sau reverse proxy, ingress hoặc API gateway. Test không nhất thiết phải chạy trên hostname public và port TLS chỉ để tạo tài liệu. Spring REST Docs cho phép chuẩn hóa URI được ghi trong snippet bằng cấu hình URI mặc định hoặc operation preprocessor.

Cần phân biệt:

- **URI thực của test:** địa chỉ HTTP client dùng để tạo exchange.
- **Documented URI:** URI được trình bày cho người đọc trong generated snippet.
- **Path và query:** phần resource/query thuộc API contract.
- **Host header:** header HTTP riêng, không đồng nhất với authority của URI.

Đổi URI cho tài liệu không thay đổi endpoint server, DNS, TLS, gateway routing hoặc request thực tế. Chỉ chuẩn hóa khi biết public base URI đúng và vẫn giữ path/query khớp contract.

## 2. Hai cách cấu hình documented URI

| Cách | API | Phạm vi |
| --- | --- | --- |
| Cấu hình URI mặc định | `.uris().withScheme(...).withHost(...).withPort(...)` | Nhiều operation dùng chung public base URI |
| Preprocessor theo operation | `modifyUris()` | Một operation cần override riêng |

Với MockMvc, cấu hình mặc định được gắn vào configurer khi tạo client:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(documentationConfiguration(documentation)
                .uris()
                .withScheme("https")
                .withHost("api.example.com")
                .withPort(443))
        .build();
```

Các test có thể tiếp tục gọi path tương đối như `/api/orders/42`; documented request URI dùng scheme, host và port đã cấu hình.

Khi chỉ một operation cần URI khác, dùng `modifyUris()` trong `document(...)`:

```java
.andDo(document("orders-get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.com")
            .removePort()
    )
))
```

Cấu hình mặc định thích hợp với base URI chung; preprocessor thích hợp khi cần quy tắc cục bộ.

## 3. Scheme, host và port

| Thành phần | Local | Public |
| --- | --- | --- |
| Scheme | `http` | `https` |
| Host | `localhost` | `api.example.com` |
| Port | `8080` | `443` hoặc port public khác |
| Path | `/api/orders/42` | `/api/orders/42` |
| Query | `?expand=items` | `?expand=items` |

### 3.1. Thay scheme

```java
preprocessRequest(
    modifyUris().scheme("https")
)
```

Dùng HTTPS nếu đó là giao thức client public phải sử dụng. Không đổi scheme chỉ để snippet trông giống production khi API đích không hỗ trợ HTTPS.

### 3.2. Thay host

```java
preprocessRequest(
    modifyUris().host("api.example.com")
)
```

Dùng domain chính thức hoặc domain mẫu được tổ chức công bố. Tránh hostname máy developer hoặc tên service nội bộ như `order-service.default.svc.cluster.local` trong tài liệu consumer.

### 3.3. Đặt hoặc bỏ port

Nếu public endpoint có port riêng:

```java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("api.example.com")
        .port(8443)
)
```

Nếu không muốn hiển thị port tường minh:

```java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("api.example.com")
        .removePort()
)
```

Không nhầm port nội bộ của ứng dụng với port public gateway. Ứng dụng có thể lắng nghe `8080` trong container trong khi ingress tiếp nhận HTTPS ở `443`; documented URI nên phản ánh địa chỉ consumer gọi được.

## 4. Cấu hình URI mặc định cho MockMvc

Ví dụ JUnit Jupiter với standalone MockMvc:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class PublicUriDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(documentation)
                        .uris()
                        .withScheme("https")
                        .withHost("api.example.com")
                        .withPort(443))
                .build();
    }

    @Test
    void getOrderDocumentsPublicUri() throws Exception {
        mockMvc.perform(get("/api/orders/42")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andDo(document("orders-get"));
    }

    @RestController
    static class OrderController {
        @GetMapping(value = "/api/orders/42",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        OrderResponse getOrder() {
            return new OrderResponse("ORD-42", "CONFIRMED");
        }
    }

    record OrderResponse(String orderId, String status) {}
}
```

Test vẫn thực hiện request qua MockMvc; URI public là cấu hình cho documentation configurer. Controller mapping và path không thay đổi.

Với application context thật, có thể cấu hình tương tự:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(documentationConfiguration(documentation)
                .uris()
                .withScheme("https")
                .withHost("api.example.com")
                .withPort(443))
        .build();
```

Chọn standalone hay application context theo mục đích test. URI configuration không thay thế routing, security hoặc converter cần thiết trong integration test.

## 5. Dùng modifyUris() cho từng operation

Một số API có endpoint trên nhiều host, ví dụ upload qua object storage. Có thể ghi URI khác cho operation upload:

```java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andDo(document("orders-get",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort()
                )));
```

Một operation khác:

```java
.andDo(document("documents-upload",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("uploads.example.com")
            .removePort()
    )
))
```

Chỉ dùng host riêng khi public contract thực sự yêu cầu. Không dùng operation preprocessor để che lỗi định tuyến hoặc làm public URL có vẻ đúng trong khi gateway cấu hình sai.

Nếu cấu hình mặc định và preprocessor theo operation cùng áp dụng, hãy kiểm tra snippet cuối để xác nhận URI đúng. Tập trung cấu hình base URI ở một nơi; chỉ override ngoại lệ có chủ đích.

## 6. Giữ path và query đúng contract

Khi chuẩn hóa base URI, thường cần giữ nguyên resource path và query:

```text
Local:
http://localhost:8080/api/orders/42?expand=items

Documented:
https://api.example.com/api/orders/42?expand=items
```

Path và query mang ý nghĩa API. Không xóa hoặc viết lại chúng nếu chưa có quyết định thay đổi contract.

```java
mockMvc.perform(get("/api/orders/{id}", 42)
                .queryParam("expand", "items"))
        .andExpect(status().isOk())
        .andDo(document("orders-get-expanded",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort()
                )));
```

Nếu public gateway thêm context path như `/gateway`, xác định đó có phải một phần base path consumer cần gọi hay chỉ là chi tiết triển khai. Chỉ đưa prefix vào documented URI khi client thật sự phải sử dụng nó.

## 7. URI và Host header là hai thông tin khác nhau

HTTP request có URI/authority và header `Host` (hoặc `:authority` trong HTTP/2). Chúng liên quan nhưng không phải cùng một field:

- URI preprocessing thay đổi URI được thể hiện trong operation.
- Header preprocessing thay đổi header trong recorded request.
- `modifyUris()` không thay thế mọi header.
- Để tài liệu hóa Host header, dùng header descriptor hoặc header preprocessor phù hợp.

Ví dụ chỉnh cả URI và header trong bản ghi tài liệu:

```java
.andDo(document("orders-get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.com")
            .removePort(),
        modifyHeaders()
            .set("Host", "api.example.com")
    )
))
```

Chỉ chỉnh Host nếu header đó có trong recorded request và tài liệu cần chuẩn hóa nó. Với một số HTTP client/protocol, authority được biểu diễn theo quy tắc riêng; hãy xác minh snippet thay vì giả định có thể đặt header giống HTTP/1.1.

## 8. Reverse proxy, gateway và context path

Ứng dụng sau reverse proxy có thể nhận request nội bộ:

```text
http://order-service:8080/api/orders/42
```

Trong khi client public gọi:

```text
https://api.example.com/store/api/orders/42
```

Khác biệt có thể gồm scheme, host, port và prefix path. Xác định prefix `/store` có thuộc public base path hay không. Nếu prefix luôn có trên mọi endpoint, cần quy ước tài liệu thống nhất; nếu chỉ một operation có route riêng, xử lý ngoại lệ rõ ràng.

Proxy thường truyền thông tin gốc qua `Forwarded` hoặc `X-Forwarded-*`. Những header này có thể ảnh hưởng đến absolute links hoặc redirect do framework tạo, nhưng không tự động cấu hình documented URI trong REST Docs.

Ví dụ mô phỏng request qua proxy, khi ứng dụng được cấu hình tin cậy forwarded headers:

```java
mockMvc.perform(get("/api/orders/42")
        .header("X-Forwarded-Proto", "https")
        .header("X-Forwarded-Host", "api.example.com")
        .header("X-Forwarded-Prefix", "/store"))
    .andExpect(status().isOk())
    .andDo(document("orders-get"));
```

Đây là ví dụ test, không phải khuyến nghị tin forwarded headers do mọi client gửi. Trong production, proxy/gateway phải loại header giả do client cung cấp và thiết lập giá trị đáng tin cậy; ứng dụng chỉ xử lý forwarded headers theo cấu hình an toàn.

## 9. WebTestClient và REST Assured

### 9.1. WebTestClient

Có thể đặt URI defaults trên documentation configurer khi tạo client:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider documentation) {
    webTestClient = WebTestClient.bindToController(new OrderController())
            .configureClient()
            .filter(documentationConfiguration(documentation)
                    .uris()
                    .withScheme("https")
                    .withHost("api.example.com")
                    .withPort(443))
            .build();
}
```

Tùy loại bind và phiên bản, vị trí cấu hình filter có thể khác. Giữ test client target phù hợp với môi trường test; documented URI không phải lý do để gửi request thật tới public production host.

### 9.2. REST Assured

Cấu hình URI defaults trong REST Docs filter:

```java
RequestSpecification spec = new RequestSpecBuilder()
        .addFilter(documentationConfiguration(documentation)
                .uris()
                .withScheme("https")
                .withHost("api.example.com")
                .withPort(443))
        .build();
```

Test sử dụng specification đó:

```java
given(spec)
    .filter(document("orders-get"))
    .when()
    .get("/api/orders/42")
    .then()
    .statusCode(200);
```

Import và overload phụ thuộc integration/version. Dùng API đúng artifact của dự án và xác minh generated request snippet sau khi chạy.

## 10. URI trong response headers và links

Chuẩn hóa request URI không tự động sửa mọi absolute URI trong response. Ví dụ response header:

```http
Location: http://localhost:8080/api/orders/42
```

Hoặc body:

```json
{
  "self": "http://localhost:8080/api/orders/42"
}
```

Nếu API thực tế trả public URI, application/proxy phải tạo URI đó đúng theo base URL và forwarded-header configuration. Nếu đây chỉ là fixture/test URI không phù hợp tài liệu, dùng preprocessor riêng cho response header/body.

Không giả định `modifyUris()` thay mọi chuỗi URL trong JSON hoặc mọi giá trị Location. Nó xử lý URI của operation request; header và body là nội dung riêng.

## 11. Asciidoctor và build/CI

Generated snippets dùng documented URI có thể include như bình thường:

```adoc
= Order API
:snippets: build/generated-snippets

== Lấy đơn hàng

=== HTTP request
include::{snippets}/orders-get/http-request.adoc[]

=== HTTP response
include::{snippets}/orders-get/http-response.adoc[]
```

Build cần chạy documentation tests trước Asciidoctor. Trong code review, kiểm tra domain public, scheme, port, path/query, gateway prefix, Host header và các URL Location/link trong response. Đảm bảo test không vô tình gọi production host khi chỉ muốn tạo snippets.

Nếu local, staging và production có hostname khác nhau, tài liệu public nên dùng base URI đã xác định cho audience; không để hostname máy developer hoặc CI lọt vào artifact.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Snippet hiện localhost | Chưa cấu hình documented URI | Dùng `.uris()` hoặc `modifyUris()` |
| Scheme vẫn là http | Chỉ thay host | Cấu hình scheme theo endpoint public |
| Port nội bộ xuất hiện | Dùng port test server làm port public | Đặt port public hoặc `removePort()` |
| Mất gateway prefix | Nhầm prefix triển khai với public base path | Xác định prefix có thuộc contract không |
| Host header chưa đổi | Chỉ dùng URI processor | Dùng header processor nếu cần |
| Location vẫn chứa localhost | Nhầm operation URI với response header | Xử lý response header hoặc cấu hình application |
| Link trong JSON vẫn là URL local | `modifyUris()` không rewrite chuỗi body | Dùng processor body có chủ đích hoặc sửa fixture |
| Mỗi operation dùng host khác nhau | URI overrides rải rác | Tập trung default và chỉ override ngoại lệ |
| Test gọi nhầm production host | Nhầm documented URI với target HTTP client | Giữ test target local; rewrite bản ghi docs |
| CI và local khác URI | Phụ thuộc host/port runtime | Cấu hình URI cố định cho tài liệu |

## 13. Bài thực hành

Dùng operation `GET /api/orders/42`:

1. Chạy test MockMvc chưa cấu hình URI; quan sát localhost và port trong `http-request.adoc`.
2. Cấu hình URI mặc định bằng `.uris().withScheme("https").withHost("api.example.com").withPort(443)`.
3. Chạy lại và xác nhận scheme/host/port đổi nhưng path vẫn đúng.
4. Dùng `modifyUris()` riêng cho operation upload với host `uploads.example.com`.
5. Thử `removePort()` khi tài liệu không muốn hiển thị port.
6. Thêm query `expand=items`; xác nhận query vẫn có trong documented URI.
7. Mô phỏng gateway prefix `/store`; quyết định nó thuộc public path hay route nội bộ.
8. Tạo response Location chứa localhost; xác định vì sao URI request preprocessor không tự sửa header này.
9. Include snippet vào Asciidoctor và kiểm tra không còn domain local ngoài ý muốn.
10. Đảm bảo test vẫn gửi request tới test target, không gọi production host chỉ vì documented URI dùng domain public.

**Tiêu chí hoàn thành:** bạn phân biệt URI thực của test với documented URI; cấu hình base URI bằng `.uris()`; dùng `modifyUris()` cho operation riêng; hiểu scheme/host/port/path/query và Host header; xử lý reverse proxy/context path; và kiểm tra generated snippets/Asciidoctor phản ánh đúng public API.

## Tài liệu tham khảo

- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessing.html): chuẩn hóa URI trong recorded operation request.
- [Spring REST Docs — MockMvc API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/mockmvc/MockMvcRestDocumentation.html): cấu hình documentation với MockMvc.
- [Spring REST Docs — UriModifyingOperationPreprocessor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/UriModifyingOperationPreprocessor.html): phương thức chỉnh scheme, host, port và URI.
- [Spring Framework — HTTP Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): xử lý thông tin forwarded từ proxy/gateway.
