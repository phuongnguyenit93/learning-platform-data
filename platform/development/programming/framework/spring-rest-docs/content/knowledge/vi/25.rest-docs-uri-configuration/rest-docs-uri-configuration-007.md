# Base path, context path và servlet path

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, ta tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào build và CI.

Khi một API được triển khai sau API gateway, trong một web application có context path hoặc dưới một servlet mapping cụ thể, cùng một endpoint có thể có nhiều prefix. Nếu không phân biệt các phần này, MockMvc có thể tạo request sai, ứng dụng không match được controller hoặc `http-request.adoc` hiển thị URL thiếu hay lặp path.

Bài học này phân biệt base path, Servlet context path, servlet path và path info; sau đó áp dụng các giá trị này trong MockMvc và kiểm tra URI được Spring REST Docs ghi nhận.

Sau bài học, bạn có thể:

- Phân biệt base path công khai của API với context path của web application.
- Giải thích vai trò của `contextPath`, `servletPath` và `pathInfo` theo Servlet request.
- Xác định request URI hoàn chỉnh từ các thành phần đường dẫn.
- Cấu hình MockMvc request builder đúng với context path và servlet mapping.
- Tránh lặp prefix khi endpoint nằm sau gateway hoặc reverse proxy.
- Kiểm tra đường dẫn được sinh trong `http-request.adoc` và tích hợp vào CI.

## 2. Nhìn tổng thể các lớp path

Giả sử client gọi API công khai:

~~~text
https://api.example.com/store/api/orders/42
~~~

URL có thể được hình thành từ các phần:

| Phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Scheme/host | `https://api.example.com` | Giao thức và máy chủ công khai. |
| Gateway/base path | `/store` | Prefix do gateway hoặc cách triển khai ứng dụng công bố. |
| Servlet context path | `/store` | Đường dẫn gốc của web application trên Servlet container. |
| Servlet mapping path | `/api` | Prefix dùng để map request tới DispatcherServlet khi servlet được map theo `/api/*`. |
| Path info | `/orders/42` | Phần còn lại sau servlet mapping trong kiểu mapping path cụ thể. |

Trong ví dụ này, `/store` được dùng đồng thời làm public prefix và context path để minh họa trường hợp gateway chuyển tiếp nguyên prefix. Đây không phải quy tắc chung: gateway có thể rewrite hoặc loại prefix, còn context path do web application deployment quyết định. Hãy xác định nơi prefix được thêm vào trước khi mô phỏng request.

~~~mermaid
flowchart LR
    A["Public URL"] --> B["Gateway/base prefix"]
    B --> C["Servlet context path"]
    C --> D["Servlet mapping"]
    D --> E["Path info / endpoint path"]
    E --> F["Spring MVC controller"]
~~~

Không cộng tất cả prefix theo thói quen. Một proxy có thể loại bỏ `/store` trước khi chuyển request tới ứng dụng, trong khi container có thể nhận context path `/store`. Khi đó, request URI nhìn từ client và URI nhìn từ servlet application có thể khác nhau.

## 3. Base path là gì?

`Base path` thường được dùng trong tài liệu API để chỉ prefix chung đứng trước các endpoint. Nó có thể là:

- Prefix công khai do API gateway/reverse proxy thêm vào.
- Prefix triển khai của ứng dụng.
- Một phần path cố định được client dùng làm gốc cho các endpoint.

Ví dụ tài liệu API mô tả:

~~~text
https://api.example.com/v1/orders
https://api.example.com/v1/customers
https://api.example.com/v1/products
~~~

Ở đây `/v1` là base path chung của API. Trong Spring MVC, nó có thể được cấu hình trong mapping controller:

~~~java
@RequestMapping("/v1/orders")
@RestController
class OrderController {
    // Endpoint methods
}
~~~

Hoặc `/v1` có thể được gateway thêm vào trước khi chuyển tới ứng dụng. Hai cách triển khai này có thể tạo URL công khai giống nhau nhưng request path mà controller nhận được khác nhau.

Vì vậy, khi test MockMvc, cần dùng đúng path mà Servlet application thực sự nhận, không mặc định thêm prefix public nếu gateway đã loại prefix đó.

## 4. Servlet context path

Context path xác định web application đang được triển khai dưới prefix nào trên Servlet container. Nó bắt đầu bằng dấu `/`; ứng dụng được triển khai ở root context thường có context path rỗng.

Ví dụ:

| Kiểu triển khai | Context path |
| --- | --- |
| Root application | Chuỗi rỗng `""` |
| Application dưới `/store` | `/store` |
| Application dưới `/internal` | `/internal` |

Trong MockMvc, có thể đặt context path cho request:

~~~java
mockMvc.perform(get("/store/api/orders/42")
        .contextPath("/store"))
    .andExpect(status().isOk());
~~~

Đường dẫn request phải phù hợp với context path được đặt. Với request URI `/store/api/orders/42`, phần path sau context path là `/api/orders/42`.

Context path không phải host và không phải servlet mapping. Không đặt `.contextPath("https://api.example.com")`; hostname thuộc URI/base URL, còn context path là phần path của web application.

Trong phần lớn test MVC, có thể bỏ context path khỏi request URI và không đặt `.contextPath(...)`, vì controller thường không phụ thuộc tên deployment của web application. Chỉ đặt context path khi cần kiểm tra ứng dụng dưới prefix đó hoặc khi muốn snippet thể hiện đúng cấu trúc triển khai.

## 5. Servlet path và path info

Servlet API phân tách path dùng để chọn servlet với phần path còn lại trong một số kiểu mapping.

- `servletPath`: phần path khớp mapping của servlet.
- `pathInfo`: phần path còn lại sau servlet mapping; có thể `null` nếu không có phần còn lại hoặc kiểu mapping không tạo path info.

Nếu không gọi `.pathInfo(...)`, MockMvc tự suy ra path info bằng cách loại context path và servlet path khỏi request URI rồi dùng phần còn lại. Đây thường là lựa chọn đơn giản hơn; chỉ đặt path info trực tiếp khi test cần xác nhận một giá trị cụ thể.

Ví dụ DispatcherServlet được map theo `/api/*` và ứng dụng có context path `/store`:

~~~text
Request URI: /store/api/orders/42
Context path: /store
Servlet path: /api
Path info: /orders/42
~~~

Các giá trị này mô tả ví dụ kiểu path mapping. Cách container phân loại path phụ thuộc servlet mapping thực tế; không tự đặt `servletPath` và `pathInfo` nếu ứng dụng dùng DispatcherServlet mapping mặc định `/`.

### 5.1. Ví dụ request builder

MockMvc có thể thiết lập context path, servlet path và path info:

~~~java
mockMvc.perform(get("/store/api/orders/42")
        .contextPath("/store")
        .servletPath("/api")
        .pathInfo("/orders/42"))
    .andExpect(status().isOk());
~~~

Request builder phải mô phỏng cùng một cấu trúc path mà Servlet container sẽ tạo ra. Nếu controller mapping là `/orders/{id}` và DispatcherServlet được map `/api/*`, cần bảo đảm cấu hình servlet test thực sự tương ứng với mapping này. Không áp dụng ví dụ trên cho mọi ứng dụng Spring MVC.

### 5.2. Trường hợp DispatcherServlet map ở root

Trong cấu hình phổ biến, DispatcherServlet được map theo `/`. Khi đó servlet path có thể chính là path của request sau context path và path info không cần thiết.

Ví dụ:

~~~text
Request URI: /store/orders/42
Context path: /store
Servlet path: /orders/42
Path info: null
~~~

Với trường hợp này, test MockMvc thường đơn giản:

~~~java
mockMvc.perform(get("/store/orders/42")
        .contextPath("/store"))
    .andExpect(status().isOk());
~~~

Giá trị cụ thể phải khớp Servlet mapping và request builder của dự án.

## 6. Phân biệt public base path với context path nội bộ

Reverse proxy hoặc API gateway có thể thêm, giữ nguyên hoặc loại bỏ prefix trước khi chuyển tiếp request. Vì vậy, đường dẫn client gọi không nhất thiết giống đường dẫn mà ứng dụng Spring nhận.

Ví dụ A — gateway giữ prefix:

~~~text
Client gọi:              /store/api/orders/42
Ứng dụng nhận:           /store/api/orders/42
Context path:            /store
Controller path:         /api/orders/42
~~~

Ví dụ B — gateway loại prefix:

~~~text
Client gọi:              /store/api/orders/42
Gateway chuyển tiếp:     /api/orders/42
Ứng dụng nhận:           /api/orders/42
Context path:            ""
Controller path:         /api/orders/42
~~~

Trong trường hợp B, không thêm `.contextPath("/store")` vào MockMvc chỉ vì tài liệu public có prefix `/store`. MockMvc test nội bộ cần mô phỏng request sau khi gateway đã chuyển tiếp. URL tài liệu public có thể được mô tả riêng ở phần base URL hoặc gateway configuration.

| Câu hỏi | Nơi xác định |
| --- | --- |
| Client bắt đầu gọi từ hostname/base path nào? | Tài liệu gateway/API public. |
| Gateway giữ hay bỏ prefix? | Cấu hình route/rewrite của gateway. |
| Servlet application có context path nào? | Cấu hình triển khai/container. |
| DispatcherServlet được map theo đường dẫn nào? | Servlet registration/mapping. |
| Controller xử lý endpoint path nào? | `@RequestMapping`, `@GetMapping` và các mapping liên quan. |

## 7. Cấu hình MockMvc request có context path

Ví dụ ứng dụng được triển khai ở context `/store`, DispatcherServlet map root và controller xử lý `/api/orders/{id}`:

~~~java
@Test
void getsOrderUnderStoreContext() throws Exception {
    mockMvc.perform(get("/store/api/orders/{id}", 42)
            .contextPath("/store"))
        .andExpect(status().isOk())
        .andDo(document("orders/get"));
}
~~~

Request URI hoàn chỉnh được MockMvc mô phỏng là `/store/api/orders/42`. Tên miền/scheme documented được cấu hình riêng trong Spring REST Docs MockMvc URI configurer:

~~~java
MockMvcBuilders.webAppContextSetup(context)
    .apply(documentationConfiguration(restDocumentation).uris()
        .withScheme("https")
        .withHost("api.example.com")
        .withPort(443))
    .build();
~~~

Snippet có thể ghi:

~~~http
GET https://api.example.com/store/api/orders/42 HTTP/1.1
~~~

Ở đây scheme, host và port đến từ URI configurer; `/store` đến từ context path; `/api/orders/42` là phần path được DispatcherServlet/controller xử lý trong ví dụ. Port 443 là port mặc định của HTTPS nên Spring REST Docs lược nó khỏi URI snippet.

## 8. Cấu hình MockMvc cho servlet mapping /api/*

Khi DispatcherServlet được map theo `/api/*`, Servlet container phân tích request path theo mapping đó. Ví dụ:

~~~text
Request URI: /store/api/orders/42
Context path: /store
Servlet path: /api
Path info: /orders/42
~~~

MockMvc request có thể mô phỏng các thành phần:

~~~java
mockMvc.perform(get("/store/api/orders/42")
        .contextPath("/store")
        .servletPath("/api")
        .pathInfo("/orders/42"))
    .andExpect(status().isOk())
    .andDo(document("orders/get"));
~~~

Đây là ví dụ khi dự án thật sự đăng ký DispatcherServlet bằng `/api/*` và controller mapping tương ứng với path còn lại. Cần cấu hình servlet registration trong test sao cho phù hợp; chỉ đặt các thuộc tính request không tự thay đổi servlet mapping của ApplicationContext.

Nếu controller mapping thực tế là `/api/orders/{id}` trong DispatcherServlet root mapping `/`, không cấu hình `servletPath("/api")` và `pathInfo("/orders/42")`. Hãy dùng cấu hình root mapping ở mục trước.

## 9. Tài liệu hóa public path và internal path

Một hệ thống có thể có hai góc nhìn:

- **Public URL**: đường dẫn mà client tích hợp cần gọi qua gateway.
- **Internal servlet request**: đường dẫn ứng dụng nhận sau gateway rewrite và context deployment.

REST Docs MockMvc thường ghi URI từ mock request. Vì thế, nếu test mô phỏng internal request, snippet mặc định có thể không chứa public prefix. Có hai cách xử lý:

1. Mô phỏng request với public prefix nếu prefix thực sự được chuyển nguyên vẹn đến ứng dụng.
2. Giữ test theo internal mapping và mô tả public base path ở phần hướng dẫn gateway/API; dùng URI configuration cho scheme/host/port khi cần.

Không thêm prefix bằng cách sửa context path nếu gateway đã loại bỏ nó. Việc này sẽ kiểm tra một request khác với request ứng dụng thật sự nhận.

## 10. Ví dụ đầy đủ JUnit 5 và MockMvc

Ví dụ sau giả định root DispatcherServlet mapping, context path `/store` và controller route `/api/orders/{id}`. Test context chứa controller xử lý route này.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@ExtendWith(RestDocumentationExtension.class)
class ContextPathDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = webAppContextSetup(this.context)
            .apply(documentationConfiguration(restDocumentation).uris()
                .withScheme("https")
                .withHost("api.example.com")
                .withPort(443))
            .build();
    }

    @Test
    void documentsOrderWithContextPath() throws Exception {
        this.mockMvc.perform(get("/store/api/orders/{id}", 42)
                .contextPath("/store"))
            .andExpect(status().isOk())
            .andDo(document("orders/get"));
    }
}
~~~

Vì URI builder và context path đều chứa phần phù hợp, test mô phỏng đúng đường dẫn ứng dụng. Request snippet dự kiến:

~~~http
GET https://api.example.com/store/api/orders/42 HTTP/1.1
~~~

Nếu ứng dụng triển khai ở root context, bỏ `.contextPath("/store")` và bỏ `/store` khỏi request URI. Không để một prefix xuất hiện đồng thời như context path và một phần path endpoint nếu nó không tồn tại hai lần trong request thật.

## 11. Xác minh URI trong snippet

Sau test, mở:

~~~text
build/generated-snippets/orders/get/http-request.adoc
~~~

Đối chiếu:

| Nội dung | Kỳ vọng trong ví dụ |
| --- | --- |
| Scheme | `https` |
| Host | `api.example.com` |
| Port | Không hiển thị vì 443 là port HTTPS mặc định |
| Context path | `/store` |
| Endpoint path | `/api/orders/42` |
| URI hoàn chỉnh | `https://api.example.com/store/api/orders/42` |

Nếu thiếu `/store`, kiểm tra request builder có `.contextPath("/store")` và URI request có được dựng đúng hay không. Nếu `/store` xuất hiện hai lần, kiểm tra prefix trong endpoint path và context path. Nếu host/scheme sai, kiểm tra `documentationConfiguration(...).uris()` trên MockMvc instance thực sự dùng trong test.

## 12. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân và cách xử lý |
| --- | --- |
| MockMvc trả 404 sau khi thêm context path | URI request và `.contextPath(...)` không nhất quán hoặc mapping của controller/servlet không khớp. |
| Snippet thiếu public prefix | Gateway có thể thêm prefix trước khi vào ứng dụng; quyết định xem prefix đó có xuất hiện trong mock request nội bộ không. |
| Snippet lặp `/store/store` | Prefix được đặt cả trong request path và context path theo cách không khớp request mong muốn. |
| Controller không được gọi khi đặt servletPath | Servlet mapping hoặc request builder không khớp với cách DispatcherServlet được đăng ký. |
| `pathInfo` không đúng | Kiểu servlet mapping không tạo phần path info như giả định; kiểm tra mapping và request URI. |
| Context path được dùng như host | Đặt nhầm thành phần URI; hostname cấu hình qua documented URI configurer, context path nằm trong request path. |
| Test pass nhưng tài liệu sai prefix | Test đang mô phỏng internal path trong khi tài liệu yêu cầu public gateway path; tách hai góc nhìn và mô tả gateway rõ ràng. |
| Một số test có prefix, một số không | Dựng helper/request builder chung hoặc cấu hình test riêng cho từng cách triển khai. |

## 13. Tích hợp Asciidoctor và CI

Asciidoctor có thể include request snippet đã được sinh:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Lấy đơn hàng

include::{snippets}/orders/get/http-request.adoc[]
include::{snippets}/orders/get/http-response.adoc[]
~~~

Giả sử plugin Asciidoctor đã được cấu hình, nối task tài liệu với test:

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

Test xác nhận routing với context/servlet path mà ứng dụng thực sự dùng; REST Docs ghi URI tương ứng; Asciidoctor ghép snippet vào tài liệu. Khi gateway rewrite hoặc context path thay đổi, cập nhật test và phần hướng dẫn public path cùng lúc.

## 14. Bài thực hành

1. Chạy MockMvc test ở root context và mở `http-request.adoc`; ghi lại URI đầy đủ.
2. Thêm context path `/store`, điều chỉnh request URI và xác nhận snippet chứa prefix đúng một lần.
3. Thử bỏ `.contextPath("/store")` nhưng giữ request URI, quan sát khác biệt khi request được xử lý.
4. Mô phỏng servlet mapping `/api/*` bằng `servletPath("/api")` và `pathInfo("/orders/42")`; xác nhận cấu hình phù hợp với servlet registration của test.
5. So sánh hai kịch bản gateway giữ prefix `/store` và gateway loại prefix trước khi chuyển request.
6. Tách mô tả public URL và internal servlet path trong tài liệu khi hai đường dẫn khác nhau.
7. Chạy Gradle/CI và review URI snippet sau thay đổi context hoặc servlet mapping.

## 15. Ghi nhớ

- Base path thường là prefix chung của API; nó có thể đến từ gateway, ứng dụng hoặc quy ước versioning.
- Context path xác định gốc web application trong Servlet container; root context dùng chuỗi rỗng.
- Servlet path là phần khớp servlet mapping; path info là phần còn lại trong các kiểu mapping có path info.
- Dùng `.contextPath(...)`, `.servletPath(...)` và `.pathInfo(...)` trên MockMvc request builder theo đúng cấu trúc Servlet thực tế.
- URI public qua gateway có thể khác URI nội bộ mà Spring MVC nhận; không thêm prefix public vào MockMvc nếu gateway đã loại prefix.
- URI documented scheme/host/port cấu hình riêng với context path và servlet mapping.
- Kiểm tra `http-request.adoc` để phát hiện prefix thiếu/lặp, rồi chạy test trước Asciidoctor trong CI.

## 16. Tài liệu tham khảo

- [Spring Framework — MockHttpServletRequestBuilder Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/request/MockHttpServletRequestBuilder.html): quy tắc của `contextPath`, `servletPath` và `pathInfo`.
- [Spring REST Docs — Documented URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html): cấu hình scheme, host và port của URI được ghi trong snippet.
