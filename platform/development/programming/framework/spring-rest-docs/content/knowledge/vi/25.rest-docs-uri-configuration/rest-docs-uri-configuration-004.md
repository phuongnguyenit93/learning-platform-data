# MockMvc URI customization

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, ta tạo tài liệu REST API có thể kiểm chứng bằng các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào build và CI.

MockMvc chạy request trong môi trường kiểm thử Servlet mà không cần mở cổng HTTP thật. Vì vậy, URI ghi trong snippet cần được cấu hình để thể hiện địa chỉ mà người đọc tài liệu sẽ dùng. Spring REST Docs cung cấp cấu hình URI riêng cho MockMvc thông qua `MockMvcRestDocumentationConfigurer.uris()`.

Sau bài học, bạn có thể:

- Nhận biết giá trị mặc định của documented URI khi dùng MockMvc.
- Đặt scheme, host và port bằng `uris().withScheme().withHost().withPort()`.
- Hiểu port mặc định được lược khỏi URI snippet như thế nào.
- Cấu hình context path của request bằng `MockHttpServletRequestBuilder.contextPath(...)`.
- Phân biệt documented URI với request URI/context path của ứng dụng.
- Áp dụng cấu hình vào MockMvc standalone setup hoặc WebApplicationContext setup và xác nhận kết quả snippet.

## 2. URI mặc định của MockMvc trong Spring REST Docs

Khi dùng MockMvc, Spring REST Docs cấu hình documented URI mặc định như sau:

| Thành phần | Giá trị mặc định |
| --- | --- |
| Scheme | `http` |
| Host | `localhost` |
| Port | `8080` |

Ví dụ test:

~~~java
mockMvc.perform(get("/api/orders/42"))
    .andDo(document("orders/get"));
~~~

Request snippet có URI dạng:

~~~http
GET http://localhost:8080/api/orders/42 HTTP/1.1
~~~

Địa chỉ này là URI được dùng trong tài liệu hóa của MockMvc. MockMvc không thực hiện kết nối TCP tới `localhost:8080`; request được xử lý trong mock Servlet environment. Scheme/host/port trên snippet giúp request có dạng URL đầy đủ và dễ đọc.

Nếu tài liệu cần mô tả API sandbox hoặc public, URI mặc định có thể không đúng. Khi đó hãy thay đổi cấu hình documented URI trước khi dựng MockMvc.

## 3. Cấu hình bằng MockMvcRestDocumentationConfigurer.uris()

API `documentationConfiguration(restDocumentation)` trả về MockMvc configurer. Gọi `uris()` để lấy cấu hình URI documented:

~~~java
documentationConfiguration(restDocumentation)
    .uris()
        .withScheme("https")
        .withHost("api.example.com")
        .withPort(443)
~~~

Áp dụng khi dựng MockMvc:

~~~java
this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
    .apply(documentationConfiguration(restDocumentation).uris()
        .withScheme("https")
        .withHost("api.example.com")
        .withPort(443))
    .build();
~~~

Khi đó request snippet sẽ dùng địa chỉ `https://api.example.com/...`. Vì 443 là port mặc định của HTTPS, Spring REST Docs lược port khỏi URI được tạo.

Các phương thức:

| Phương thức | Chức năng |
| --- | --- |
| `withScheme("https")` | Đặt scheme trong documented URI. |
| `withHost("api.example.com")` | Đặt hostname trong documented URI. |
| `withPort(8443)` | Đặt port trong documented URI. |

Đây là cấu hình dành riêng cho MockMvc. Với MockMvc, thông thường nên đặt URI ngay trên `MockMvcRestDocumentationConfigurer` thay vì dùng request preprocessor `modifyUris()` để thay URI sau khi ghi nhận operation.

## 4. Chọn scheme và host

### 4.1. Scheme

Đặt scheme đúng với giao thức mà client sử dụng ở môi trường được tài liệu hướng dẫn:

~~~java
.uris()
    .withScheme("https")
~~~

Nếu API sandbox/public yêu cầu HTTPS, snippet nên dùng HTTPS dù MockMvc test không chạy TLS thật. MockMvc không mở kết nối TLS; scheme chỉ mô tả địa chỉ documented.

Không đặt HTTPS chỉ vì muốn URL trông giống production. Kiểm tra gateway, TLS và môi trường tích hợp thực tế trước khi chọn scheme.

### 4.2. Host

Đặt hostname công khai:

~~~java
.uris()
    .withHost("sandbox-api.example.com")
~~~

Một số lựa chọn minh họa:

| Bộ tài liệu | Host |
| --- | --- |
| Local guide | `localhost` |
| Sandbox guide | `sandbox-api.example.com` |
| Public API guide | `api.example.com` |

Không dùng hostname nội bộ của CI hoặc hostname container trong tài liệu dành cho khách hàng. Hãy dùng tên miền client thực sự có thể phân giải và được phép truy cập.

## 5. Đặt port và quy tắc port mặc định

Dùng `withPort(...)` khi địa chỉ tài liệu cần port cụ thể:

~~~java
documentationConfiguration(restDocumentation).uris()
    .withScheme("https")
    .withHost("sandbox-api.example.com")
    .withPort(8443)
~~~

URI documented có dạng:

~~~text
https://sandbox-api.example.com:8443/api/orders/42
~~~

Nếu port được đặt trùng port mặc định của scheme, Spring REST Docs bỏ port khỏi snippet:

| Scheme | Port mặc định | Dạng URI được ghi |
| --- | ---: | --- |
| `http` | 80 | Không ghi `:80` |
| `https` | 443 | Không ghi `:443` |

Ví dụ cấu hình HTTPS port 443:

~~~java
.withScheme("https")
.withHost("api.example.com")
.withPort(443)
~~~

Snippet được ghi thành:

~~~text
https://api.example.com/api/orders/42
~~~

Với HTTP port 8080, đây không phải port mặc định, nên snippet vẫn hiển thị `:8080`. Chọn port dựa vào địa chỉ client được yêu cầu gọi, không dựa vào cổng bất kỳ mà CI sử dụng.

## 6. Cấu hình context path cho request

Documented URI và context path là hai phần cấu hình khác nhau:

- `uris().withScheme().withHost().withPort()` quyết định scheme, host và port được ghi vào snippet.
- `MockHttpServletRequestBuilder.contextPath(...)` thiết lập context path của request Servlet mà MockMvc xử lý.

Ví dụ ứng dụng được triển khai dưới context path `/shop`:

~~~java
mockMvc.perform(get("/api/orders/42")
        .contextPath("/shop"))
    .andExpect(status().isOk())
    .andDo(document("orders/get"));
~~~

Context path được đưa vào request URI mà MockMvc xử lý. Nó khác với việc đặt host hoặc port documented. Nếu ứng dụng không dùng context path, không cần thêm `.contextPath(...)`.

Khi cấu hình context path, đảm bảo các thành phần URI của request nhất quán với cấu hình Servlet test. Context path phải bắt đầu bằng `/`, không kết thúc bằng `/`, và request URI cần được xây dựng phù hợp với context path. Nếu gặp lỗi về path trong MockHttpServletRequestBuilder, kiểm tra URI, context path và servlet path trước khi sửa documented URI.

Không dùng `withHost(...)` để thêm context path, hoặc thêm `/shop` vào host. Host chỉ là tên máy chủ; context path thuộc phần path của request.

## 7. Ví dụ đầy đủ với JUnit 5 và WebApplicationContext

Ví dụ sau cấu hình MockMvc để các snippet dùng HTTPS và hostname sandbox:

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
class MockMvcUriDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = webAppContextSetup(this.context)
            .apply(documentationConfiguration(restDocumentation).uris()
                .withScheme("https")
                .withHost("sandbox-api.example.com")
                .withPort(8443))
            .build();
    }

    @Test
    void documentsOrderUsingSandboxUri() throws Exception {
        this.mockMvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andDo(document("orders/get"));
    }
}
~~~

Ví dụ giả định Spring test context có endpoint `GET /api/orders/42` trả status 200. URI trong snippet sẽ có dạng:

~~~http
GET https://sandbox-api.example.com:8443/api/orders/42 HTTP/1.1
~~~

MockMvc vẫn xử lý request trong môi trường test; scheme, host và port đã cấu hình chỉ điều chỉnh URI documented.

## 8. Ví dụ standalone setup

Nếu test dùng `standaloneSetup(...)`, vẫn áp dụng configurer vào MockMvc builder:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class StandaloneMockMvcUriTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
            .standaloneSetup(new OrderController())
            .apply(documentationConfiguration(restDocumentation).uris()
                .withScheme("https")
                .withHost("api.example.com")
                .withPort(443))
            .build();
    }

    @Test
    void documentsOrder() throws Exception {
        this.mockMvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andDo(document("orders/get"));
    }
}
~~~

Nếu controller có dependency, hãy cung cấp dependency cần thiết hoặc dùng WebApplicationContext setup theo cấu hình ứng dụng.

Với port 443 và scheme HTTPS, snippet sẽ không hiển thị `:443`.

## 9. Context path trong tài liệu hóa

Giả sử API triển khai dưới prefix `/store`. Request builder cần mô phỏng đúng đường dẫn ứng dụng tiếp nhận:

~~~java
mockMvc.perform(get("/api/orders/42")
        .contextPath("/store"))
    .andExpect(status().isOk())
    .andDo(document("orders/get"));
~~~

Khi có context path, request URI được tài liệu hóa sẽ thể hiện phần prefix của ứng dụng. Ví dụ minh họa URI:

~~~text
https://api.example.com/store/api/orders/42
~~~

Scheme/host/port đến từ URI configurer; `/store` đến từ context path của MockMvc request. Nhờ tách bạch hai cấu hình, có thể mô tả API đứng sau servlet context hoặc gateway prefix.

Nếu hệ thống dùng `servletPath` hoặc `pathInfo` riêng, cần cấu hình request builder và servlet mapping tương ứng. Không thêm prefix vào cả context path lẫn endpoint path nếu ứng dụng không thực sự định tuyến theo cấu trúc đó, vì có thể tạo đường dẫn lặp.

## 10. Cấu hình mặc định và thay đổi theo môi trường

URI configurer được áp dụng khi dựng MockMvc. Vì vậy, mọi operation được tài liệu hóa qua instance đó sẽ dùng cùng scheme, host và port.

Bộ tài liệu sandbox:

~~~java
.uris()
    .withScheme("https")
    .withHost("sandbox-api.example.com")
    .withPort(8443)
~~~

Bộ tài liệu public:

~~~java
.uris()
    .withScheme("https")
    .withHost("api.example.com")
    .withPort(443)
~~~

Nếu cần hai bộ tài liệu, có thể tạo hai MockMvc instance hoặc hai test configuration có URI settings riêng và ghi snippet vào output directory riêng. Tránh dùng chung operation identifier và thư mục output nếu hai bộ có địa chỉ khác nhau; một bộ có thể ghi đè snippet của bộ kia.

## 11. Phân biệt MockMvc URI configuration và request preprocessors

Spring REST Docs có `modifyUris()` trong nhóm operation preprocessors. Tuy nhiên, tài liệu hướng dẫn URI phân biệt cách cấu hình theo loại client:

| Kiểu test | Cách cấu hình documented URI |
| --- | --- |
| MockMvc | Dùng `documentationConfiguration(...).uris()` với `withScheme`, `withHost`, `withPort`. |
| WebTestClient không bind server | Đặt base URL trong cấu hình builder bằng `baseUrl(String)`. |
| WebTestClient bind server | Có thể dùng URI preprocessor để thay URI xuất hiện trong tài liệu khi test server local. |
| REST Assured | Dùng REST Assured integration/preprocessor phù hợp vì test thực hiện HTTP request thật. |

Với MockMvc, hãy ưu tiên `MockMvcRestDocumentationConfigurer.uris()` để cấu hình documented URI. Dùng preprocessors khi cần xử lý nội dung operation theo mục đích khác, ví dụ chuẩn hóa header hoặc body. Không nhầm URI documented với base URL dùng để gửi request HTTP thực tế.

## 12. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân và cách xử lý |
| --- | --- |
| Snippet vẫn ghi `http://localhost:8080` | Configurer chưa được áp dụng bằng `.apply(documentationConfiguration(...).uris()...)` vào MockMvc instance đang dùng. |
| Host thay đổi nhưng port không đúng | Kiểm tra `withPort(...)`; nhớ rằng port mặc định 80/443 được lược khỏi snippet. |
| Snippet không hiện port 443 | Đây là hành vi bình thường vì 443 là port mặc định của HTTPS. |
| Context path bị thiếu | Thiết lập `.contextPath(...)` trên MockHttpServletRequestBuilder nếu ứng dụng có context path. |
| Context path xuất hiện hai lần | Kiểm tra request URI và context path; không lặp prefix trong cả hai phần. |
| Request lỗi trước khi tài liệu hóa | Kiểm tra context path, servlet path và URI được xây dựng nhất quán trong MockMvc request builder. |
| Một số snippet dùng URL cũ | Có test đang sử dụng MockMvc instance khác hoặc cấu hình URI chưa được áp dụng cho builder đó. |
| Snippet sandbox ghi hostname public | Kiểm tra URI configurer của MockMvc instance và test class đang chạy. |

## 13. Tích hợp Asciidoctor và CI

Sau khi MockMvc test sinh snippet, Asciidoctor có thể include request và response:

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

URL snippet ổn định vì MockMvc URI configurer dùng scheme/host/port đã chọn, không phụ thuộc cổng mạng ngẫu nhiên. Khi hostname hoặc port công khai thay đổi, cập nhật cấu hình URI và review snippet cùng thay đổi tài liệu API.

## 14. Bài thực hành

1. Chạy MockMvc test với URI mặc định và mở `http-request.adoc`; ghi lại scheme, host và port.
2. Dùng `.uris().withScheme("https").withHost("sandbox-api.example.com").withPort(8443)` rồi chạy lại test.
3. Đổi port thành 443, quan sát port mặc định HTTPS được lược khỏi snippet.
4. Thiết lập `.contextPath("/store")` trên request builder và kiểm tra prefix xuất hiện trong URI.
5. Tạo MockMvc instance thứ hai với hostname public; ghi snippets vào thư mục riêng.
6. Chạy Gradle/CI và xác nhận mọi snippet dùng URI đã chọn thay vì địa chỉ mặc định.

## 15. Ghi nhớ

- MockMvc documented URI mặc định là `http://localhost:8080`.
- Dùng `MockMvcRestDocumentationConfigurer.uris()` để cấu hình URI snippet bằng `withScheme(...)`, `withHost(...)` và `withPort(...)`.
- Port mặc định 80 của HTTP và 443 của HTTPS được lược khỏi URI snippet.
- Dùng `MockHttpServletRequestBuilder.contextPath(...)` để mô phỏng context path của request; không dùng host configurer để thêm path.
- URI documented chỉ điều chỉnh địa chỉ ghi trong snippet; MockMvc vẫn xử lý request trong môi trường test.
- Dùng cấu hình riêng khi tạo tài liệu sandbox và public, đồng thời tách output để tránh ghi đè snippet.
- Chạy test trước Asciidoctor trong CI để tài liệu được tạo từ giao dịch đã kiểm chứng.

## 16. Tài liệu tham khảo

- [Spring REST Docs — Documented URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html): cấu hình URI documented cho MockMvc và WebTestClient.
- [MockMvcRestDocumentationConfigurer API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/mockmvc/MockMvcRestDocumentationConfigurer.html): API của MockMvc configurer, bao gồm phương thức `uris()`.
