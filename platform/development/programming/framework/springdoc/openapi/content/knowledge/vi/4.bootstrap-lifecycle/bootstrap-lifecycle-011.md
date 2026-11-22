# Phân biệt đường dẫn API ứng dụng với đường dẫn tài liệu

Trong ứng dụng Spring Boot có springdoc-openapi, các URL của API nghiệp vụ, OpenAPI document và Swagger UI thường nằm cùng một host nhưng phục vụ những mục đích khác nhau. Nếu nhầm các loại đường dẫn này, ứng dụng có thể trả 404 khi client tải tài liệu, Swagger UI không tìm thấy JSON/YAML, hoặc OpenAPI document tạo ra server URL sai sau khi triển khai sau reverse proxy.

Hãy phân biệt ba lớp:

1. **Đường dẫn API ứng dụng** là mapping của controller, ví dụ `/api/orders/{id}`. Client gọi đường dẫn này để thực hiện nghiệp vụ.
2. **Đường dẫn tài liệu OpenAPI** là endpoint do springdoc cung cấp, mặc định là `/v3/api-docs` và `/v3/api-docs.yaml`. Client, API catalog hoặc SDK generator gọi endpoint này để lấy hợp đồng.
3. **Đường dẫn Swagger UI** là URL mở giao diện trình duyệt, mặc định thường bắt đầu ở `/swagger-ui.html` và chuyển tới tài nguyên giao diện Swagger UI. Giao diện tiếp tục tải OpenAPI document từ endpoint tài liệu.

Ba lớp có thể cùng chịu ảnh hưởng của context path, servlet mapping hoặc prefix reverse proxy, nhưng cấu hình của chúng không thay thế cho nhau. Đổi URL tải tài liệu không tự đổi mapping controller; đổi Swagger UI path không tự đổi API path; đổi API path cũng không tự đổi endpoint OpenAPI.

## 1. Nhận diện các URL mặc định

Với ứng dụng Spring MVC không đặt context path, không đổi springdoc path và có starter UI, các URL thường gặp:

| Mục đích | URL mặc định | Ai sử dụng? |
| --- | --- | --- |
| API nghiệp vụ | Do controller định nghĩa, ví dụ `/api/orders` | Ứng dụng frontend, service hoặc API client. |
| OpenAPI JSON mặc định | `/v3/api-docs` | API catalog, SDK generator, contract test và Swagger UI. |
| OpenAPI YAML mặc định | `/v3/api-docs.yaml` | Pipeline export, registry hoặc người cần file YAML. |
| OpenAPI JSON theo group | `/v3/api-docs/{group}` | Consumer của một document được nhóm riêng. |
| OpenAPI YAML theo group | `/v3/api-docs/{group}.yaml` | Consumer cần YAML của group. |
| Swagger UI entry point | `/swagger-ui.html` | Người phát triển mở giao diện tài liệu tương tác. |
| Swagger UI static resource | Thường là `/swagger-ui/index.html` | Trình duyệt tải HTML, JavaScript, CSS và các tài nguyên giao diện. |
| Swagger config | Mặc định thường là `/v3/api-docs/swagger-config` | Swagger UI đọc cấu hình và danh sách document. |

Các URL trên là mặc định phổ biến của springdoc 2.x với cấu hình tiêu chuẩn. Ứng dụng có thể thay đổi base path, group, context path, servlet mapping hoặc prefix proxy. Khi chẩn đoán, hãy kiểm tra URL thực tế ở môi trường đang chạy thay vì mặc định rằng mọi ứng dụng đều dùng đúng các path trên.

## 2. Đường dẫn API nghiệp vụ đến từ mapping của controller

Controller quyết định method và path của operation. Ví dụ:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    OrderResponse getOrder(@PathVariable String id) {
        return orderService.findById(id);
    }
}
~~~

`OrderService` và `OrderResponse` là các kiểu ứng dụng đã định nghĩa; constructor minh họa cách inject service vào controller.

Operation được công bố trong OpenAPI có path `/api/orders/{id}` và method `GET`. springdoc đọc mapping từ controller rồi đưa operation vào document; `/v3/api-docs` là nơi trả document chứa operation đó.

Nếu đổi mapping thành `/api/v2/orders/{id}`, API nghiệp vụ đổi path. Endpoint OpenAPI mặc định vẫn có thể là `/v3/api-docs`. Nếu chỉ đổi `springdoc.api-docs.path`, API nghiệp vụ vẫn giữ nguyên mapping.

Không thêm path tài liệu vào `@RequestMapping` của controller chỉ để làm Swagger UI hoạt động. Ví dụ `/v3/api-docs` không phải controller endpoint nghiệp vụ và không nên được khai báo lại bằng một controller riêng nếu springdoc đã quản lý nó.

## 3. Đổi endpoint OpenAPI bằng springdoc.api-docs.path

Property `springdoc.api-docs.path` thay đổi endpoint tải OpenAPI document. Ví dụ:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~

Sau cấu hình này, endpoint tài liệu mặc định chuyển từ `/v3/api-docs` sang `/openapi`; endpoint YAML tương ứng thường là `/openapi.yaml`. Các operation nghiệp vụ như `/api/orders/{id}` không đổi.

Nếu có group, group document được phục vụ dưới base path mới, ví dụ:

- JSON mặc định: `/openapi`
- YAML mặc định: `/openapi.yaml`
- JSON group `partner-v1`: `/openapi/partner-v1`
- YAML group `partner-v1`: `/openapi/partner-v1.yaml`

Sau khi đổi base path, cập nhật mọi nơi tải document: Swagger UI nếu có cấu hình URL tĩnh, API catalog, CI export, contract test, gateway route, monitoring và Spring Security matcher. Một số tích hợp dùng URL mặc định được springdoc cung cấp tự động; vẫn nên kiểm tra request thực tế thay vì đoán cấu hình đã cập nhật hết.

Không nhầm `springdoc.api-docs.path` với `springdoc.swagger-ui.path`. Property thứ nhất đổi endpoint JSON/YAML; property thứ hai đổi entry point của giao diện.

## 4. Đổi URL mở Swagger UI bằng springdoc.swagger-ui.path

Nếu muốn người phát triển mở giao diện tại `/docs`, có thể cấu hình:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
~~~

`/docs` là URL entry point của giao diện. Nó không đổi API path trong document và cũng không tự đổi endpoint JSON. Tùy cấu hình static resource và phiên bản, entry point có thể redirect tới tài nguyên Swagger UI thực tế.

Ví dụ cấu hình cả hai loại endpoint:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
~~~

Kết quả mong muốn ở ứng dụng không có context path:

| Chức năng | URL |
| --- | --- |
| API nghiệp vụ | `/api/orders/{id}` |
| OpenAPI JSON | `/openapi` |
| OpenAPI YAML | `/openapi.yaml` |
| Swagger UI entry point | `/docs` |

Mở `/docs` chỉ chứng minh entry point giao diện có thể được truy cập. Swagger UI còn phải tải được swagger config và OpenAPI document. Nếu HTML mở thành công nhưng vùng API báo lỗi, hãy kiểm tra các request tiếp theo trong Network tab của trình duyệt.

## 5. Cấu hình Swagger UI dùng đúng document

Thông thường springdoc tự cung cấp URL OpenAPI cho Swagger UI. Khi dùng một document cụ thể hoặc nhiều group, có thể cấu hình danh sách URL:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
    urls:
      - name: public-v1
        url: /openapi/public-v1
      - name: partner-v1
        url: /openapi/partner-v1
~~~

Trong ví dụ, Swagger UI hiển thị lựa chọn document cho hai group. Các URL trong danh sách là URL tải OpenAPI document; chúng không phải URL operation nghiệp vụ.

Nếu chỉ dùng một document bên ngoài hoặc một file được publish riêng, `springdoc.swagger-ui.url` có thể trỏ đến URL specification đó. Nếu dùng `springdoc.swagger-ui.config-url`, Swagger UI lấy cấu hình từ endpoint được chỉ định. Các property này điều khiển nguồn document/config của giao diện; không thay đổi mapping của controller.

Khi cấu hình URL tuyệt đối, hãy xác nhận trình duyệt có thể truy cập host đó và chính sách CORS cho phép tải tài liệu nếu khác origin. Nếu URL tương đối, nó được phân giải theo origin/base path của trang đang mở; kiểm tra request URL thực tế sau khi triển khai sau proxy.

## 6. Group id tạo thêm đường dẫn tài liệu

Group được tạo bằng `GroupedOpenApi`:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroups {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-v1")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner-v1")
            .pathsToMatch("/api/partner/**")
            .build();
    }
}
~~~

Group id xuất hiện trong URL document. Với base path mặc định:

| Group | JSON | YAML |
| --- | --- | --- |
| Mặc định | `/v3/api-docs` | `/v3/api-docs.yaml` |
| `public-v1` | `/v3/api-docs/public-v1` | `/v3/api-docs/public-v1.yaml` |
| `partner-v1` | `/v3/api-docs/partner-v1` | `/v3/api-docs/partner-v1.yaml` |

Nếu đổi `springdoc.api-docs.path` thành `/openapi`, các URL group cũng đổi base thành `/openapi/{group}`. Group id không đổi API operation path. Ví dụ `partner-v1` có thể chứa operation `GET /api/partner/orders` nhưng document được tải ở `/openapi/partner-v1`.

Group id là một phần URL discovery mà registry hoặc client có thể lưu. Đổi group id có thể làm hỏng nơi đang tải document, dù controller vẫn chạy bình thường.

## 7. Context path của ứng dụng thêm prefix cho mọi endpoint

Trong ứng dụng Servlet, `server.servlet.context-path` đặt context path cho toàn bộ ứng dụng:

~~~yaml
server:
  servlet:
    context-path: /store
~~~

Với cấu hình này, các URL truy cập từ bên ngoài thường có prefix `/store`:

| Endpoint trong ứng dụng | URL truy cập |
| --- | --- |
| API `GET /api/orders/{id}` | `/store/api/orders/{id}` |
| OpenAPI JSON `/v3/api-docs` | `/store/v3/api-docs` |
| Swagger UI `/swagger-ui.html` | `/store/swagger-ui.html` |

Context path không phải một phần của mapping controller. Controller vẫn khai báo `/api/orders/{id}`; container đặt toàn bộ ứng dụng dưới `/store`.

Với Spring WebFlux, cấu hình base path thường dùng:

~~~yaml
spring:
  webflux:
    base-path: /store
~~~

Đây là base path của ứng dụng reactive. Không dùng `server.servlet.context-path` để cấu hình base path cho ứng dụng WebFlux thuần. Chọn đúng thuộc tính theo web stack.

Khi ứng dụng có context path, hãy kiểm tra URL thực tế của cả API, document, Swagger UI và swagger config. Một URL hoạt động ở local root có thể cần prefix khi triển khai.

## 8. Phân biệt context path, servlet mapping và path của controller

Trong ứng dụng Servlet, URL request có thể được ghép từ nhiều phần:

~~~text
https://api.example.com/store/api/orders/42
                     |      |   |
                     |      |   +-- Mapping của controller
                     |      +------ Context path của ứng dụng
                     +------------- Host và scheme public
~~~

Một servlet mapping tùy chỉnh hoặc cấu hình gateway còn có thể ảnh hưởng cách request được chuyển đến DispatcherServlet. Vì vậy, khi một URL không khớp, hãy xác định request đã đến host, context path, servlet mapping và controller mapping nào.

Không tự thêm cùng một prefix vào cả `server.servlet.context-path` và `@RequestMapping` nếu ý định chỉ là đặt ứng dụng dưới một context. Nếu cả hai đều chứa `/store`, URL có thể trở thành `/store/store/...`.

Tương tự, không đặt prefix `/store` đồng thời trong proxy rewrite, context path và OpenAPI `servers.url` mà không xác định rõ lớp nào chịu trách nhiệm. Prefix bị lặp là nguyên nhân phổ biến khiến Swagger UI tạo URL sai.

## 9. Reverse proxy thêm prefix public

Trong production, ứng dụng có thể chạy ở root nội bộ nhưng được publish dưới một prefix. Ví dụ:

~~~text
Client:
  https://gateway.example.com/store/api/orders/42

Reverse proxy:
  bỏ prefix /store khi forward request

Spring Boot:
  nhận /api/orders/42
~~~

Nếu proxy bỏ prefix trước khi forward, backend có thể chỉ nhìn thấy path `/api/orders/42`. Khi đó, ứng dụng cần biết prefix public nếu springdoc phải tạo URL tuyệt đối hoặc Swagger UI cần gọi lại endpoint dưới `/store`.

Một cách triển khai là proxy gửi forwarded headers đáng tin cậy và Spring xử lý chúng. Ví dụ Spring Boot:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Proxy có thể truyền scheme, host và prefix public bằng các header forwarded tương ứng. Cấu hình chính xác phụ thuộc proxy và cách rewrite path. Chỉ tin các forwarded headers do proxy kiểm soát; không cho client Internet tự quyết định host hoặc prefix được phản ánh trong document.

Ví dụ Nginx minh họa việc strip prefix và gửi prefix gốc:

~~~nginx
location /store/ {
    proxy_pass http://spring-app/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Prefix /store;
}
~~~

Đây là cấu hình minh họa. Kiểm tra Nginx location, dấu slash của `proxy_pass`, path rewrite và forwarded header thực tế của hệ thống. Nếu proxy giữ nguyên prefix thay vì strip prefix, backend phải được cấu hình để nhận đúng path đó; không áp dụng đồng thời hai chiến lược.

## 10. OpenAPI servers URL không phải URL tải document

OpenAPI có trường `servers` để mô tả base URL mà client dùng khi gọi các operation. Nó không phải endpoint nơi tải OpenAPI document.

Ví dụ document có:

~~~yaml
servers:
  - url: https://api.example.com/store
paths:
  /api/orders/{id}:
    get:
      operationId: getOrderById
~~~

Client kết hợp server URL với path operation để gọi:

`https://api.example.com/store/api/orders/42`

Trong khi đó, OpenAPI document có thể được tải tại:

`https://api.example.com/store/v3/api-docs`

Không đưa `/v3/api-docs` vào `servers.url`; đó là URL discovery/document. Không thêm `/api` vào server URL nếu path operation đã bắt đầu bằng `/api`, vì client có thể tạo URL lặp prefix.

Nếu public API có base URL cố định, có thể khai báo rõ bằng annotation:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://api.example.com/store",
            description = "Public API"
        )
    }
)
class PublicServerConfiguration {
}
~~~

Nếu local, staging và production có host khác nhau, không hard-code một host production cho mọi môi trường. Dùng cấu hình theo profile/biến môi trường hoặc để server URL được xác định theo forwarded headers đã được tin cậy. Kiểm tra document ở từng môi trường để bảo đảm URL không trỏ tới hostname nội bộ.

## 11. Bảo vệ đúng đường dẫn bằng Spring Security

Đường dẫn tài liệu và Swagger UI thường có chính sách truy cập khác API nghiệp vụ. Ví dụ:

- API nghiệp vụ yêu cầu access token và scope.
- OpenAPI document chỉ cho đội phát triển hoặc API registry nội bộ tải.
- Swagger UI chỉ mở trong môi trường dev/staging hoặc cho người đã đăng nhập.

Khi đổi docs path hoặc UI path, cập nhật security matcher tương ứng. Ví dụ các matcher cho cấu hình mặc định:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(
        "/v3/api-docs",
        "/v3/api-docs/**",
        "/v3/api-docs.yaml"
    ).hasAuthority("docs.read")
    .requestMatchers(
        "/swagger-ui.html",
        "/swagger-ui/**"
    ).hasAuthority("docs.ui")
    .anyRequest().authenticated()
);
~~~

Đây là các rule minh họa để ghép vào `SecurityFilterChain` hiện có. Nếu `springdoc.api-docs.path` là `/openapi` và `springdoc.swagger-ui.path` là `/docs`, thay matcher bằng các path mới và bao gồm JSON, YAML, group, swagger-config cùng static resource thực tế.

Ví dụ với docs base path đã đổi, các URL cần xét gồm `/openapi`, `/openapi.yaml`, `/openapi/{group}`, `/openapi/{group}.yaml` và swagger config thực tế. Pattern `/openapi/**` bao phủ group và swagger config nằm dưới base path, nhưng không thay thế matcher chính xác cho sibling `/openapi.yaml`.

Lưu ý matcher cho `/v3/api-docs/**` không nhất thiết bao phủ endpoint sibling `/v3/api-docs.yaml`; cần kiểm tra rõ URL YAML. Nếu chỉ bảo vệ UI entry point mà để JSON công khai, người dùng vẫn có thể tải document trực tiếp. Ngược lại, bảo vệ document mà không cho Swagger UI gọi được config/spec sẽ làm giao diện báo lỗi xác thực.

Không mở tài liệu nội bộ ra Internet chỉ để Swagger UI hoạt động. Có thể bảo vệ document bằng cùng cơ chế đăng nhập/token, hoặc không publish UI ở môi trường không cần.

## 12. Kiểm tra endpoint bằng curl

Khi chẩn đoán, gọi từng loại URL riêng:

~~~bash
# API nghiệp vụ
curl -i http://localhost:8080/api/orders/42

# OpenAPI JSON
curl -i http://localhost:8080/v3/api-docs

# OpenAPI YAML
curl -i http://localhost:8080/v3/api-docs.yaml

# OpenAPI document của group
curl -i http://localhost:8080/v3/api-docs/partner-v1

# Swagger UI entry point
curl -i http://localhost:8080/swagger-ui.html
~~~

Nếu ứng dụng có context path `/store`, thêm `/store` vào các URL truy cập. Nếu proxy publish prefix `/store`, kiểm tra URL qua proxy chứ không chỉ gọi trực tiếp backend.

Đối với endpoint được bảo vệ, thêm token hoặc cookie hợp lệ. Phân biệt:

- `404`: path, prefix, group id hoặc route không tồn tại ở URL đã gọi.
- `401`: thiếu hoặc không hợp lệ thông tin xác thực.
- `403`: đã xác thực nhưng không có quyền.
- `302`/`3xx`: có redirect; kiểm tra `Location` để biết UI chuyển tới đâu.
- `200` nhưng body là HTML login: request đã bị chuyển tới trang đăng nhập thay vì nhận JSON/YAML.

## 13. Kiểm thử URL tài liệu bằng MockMvc

Có thể kiểm tra endpoint OpenAPI và Swagger UI route bằng Spring Boot test. Ví dụ cho ứng dụng Spring MVC:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentationPathTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void servesOpenApiJsonAtConfiguredPath() throws Exception {
        mockMvc.perform(get("/openapi"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith("application/json"));
    }

    @Test
    void servesOpenApiYamlAtConfiguredPath() throws Exception {
        mockMvc.perform(get("/openapi.yaml"))
            .andExpect(status().isOk())
            .andExpect(content().string(org.hamcrest.Matchers.containsString("openapi:")));
    }
}
~~~

Ví dụ giả định ứng dụng cấu hình `springdoc.api-docs.path: /openapi`. Nếu dùng base path mặc định, thay hai URL trong test tương ứng. Nếu security bảo vệ docs, thêm authentication/authority test thay vì tắt security.

Test endpoint UI có thể kiểm tra status hoặc redirect theo phiên bản và cấu hình static resource. Không nên phụ thuộc cứng vào một mã redirect nếu ứng dụng tùy biến resource handler; kiểm tra header `Location` hoặc truy cập tài nguyên Swagger UI thực tế theo cấu hình đã chọn.

## 14. Kiểm tra document sinh ra có path đúng

Endpoint tài liệu trả JSON thành công chưa chứng minh path nghiệp vụ trong document là chính xác. Có thể kiểm tra trường `paths`:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiApplicationPathTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void documentContainsBusinessPathWithoutDocsPrefix() throws Exception {
        String body = mockMvc.perform(get("/openapi"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode document = objectMapper.readTree(body);
        assertThat(document.path("paths")
            .has("/api/orders/{id}")).isTrue();
        assertThat(document.path("paths")
            .has("/openapi")).isFalse();
    }
}
~~~

Test này minh họa nguyên tắc: `paths` chứa operation nghiệp vụ; `/openapi` là nơi tải document và không nên tự xuất hiện như một operation của ứng dụng trừ khi ứng dụng thật sự có controller mapping như vậy.

Nếu dùng context path, `MockMvc` có thể được cấu hình khác nhau tùy test setup. Hãy kiểm tra URL request trong môi trường tích hợp tương ứng và phân biệt path bên trong application với URL public qua proxy.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `/api/orders` chạy nhưng `/v3/api-docs` trả 404 | Chưa thêm springdoc starter hoặc API docs bị tắt/đổi path | Kiểm tra starter và `springdoc.api-docs.path`, `springdoc.api-docs.enabled`. |
| `/docs` trả 404 | Chưa cấu hình `springdoc.swagger-ui.path` hoặc đang gọi sai context path | Kiểm tra UI starter, property và URL public đầy đủ. |
| Swagger UI mở nhưng không tải document | Swagger config/spec URL cũ, 401/403 hoặc proxy rewrite sai | Xem Network tab, swagger-config và endpoint JSON/YAML. |
| JSON hoạt động nhưng YAML trả 404 | Chưa gọi đúng hậu tố `.yaml` hoặc matcher/proxy chưa route | Kiểm tra URL YAML tương ứng với base path và group. |
| Group document trả 404 | Group id sai hoặc group chưa được đăng ký | Kiểm tra `GroupedOpenApi.group(...)` và URL `/base-path/{group}`. |
| URL public lặp `/store/store` | Prefix bị thêm ở proxy, context path hoặc server URL nhiều lần | Chỉ định rõ lớp chịu trách nhiệm prefix và loại bỏ phần trùng. |
| Swagger UI gọi host nội bộ | Forwarded headers không được xử lý hoặc server URL bị hard-code | Cấu hình proxy headers đáng tin cậy hoặc `servers` theo môi trường. |
| OpenAPI paths chứa prefix proxy không mong muốn | Nhầm prefix public với path operation hoặc proxy rewrite | Kiểm tra forwarded prefix và path thực tế backend nhận. |
| Security bảo vệ UI nhưng JSON vẫn công khai | Chỉ matcher UI, chưa bảo vệ docs endpoint | Bổ sung matcher cho JSON, YAML, group và swagger-config. |
| Security bảo vệ JSON nhưng Swagger UI lỗi | Chưa cho UI tải config/spec bằng quyền phù hợp | Kiểm tra cả static resource và docs endpoint. |
| Local chạy được nhưng production lỗi | Context path, proxy prefix, scheme hoặc host khác | Test qua public ingress và kiểm tra `Location`, request URL, `servers`. |
| Document có `/openapi` trong `paths` | Có controller mapping trùng URL docs hoặc document được tùy biến sai | Kiểm tra controller mapping và customizer; không nhầm docs endpoint với operation. |

## 16. Checklist khi thay đổi đường dẫn

Trước khi đổi path API, docs hoặc UI, kiểm tra:

1. Đường dẫn API nghiệp vụ trong controller có thay đổi không?
2. `springdoc.api-docs.path` có thay đổi không?
3. `springdoc.swagger-ui.path` có thay đổi không?
4. Group id và URL JSON/YAML của từng group có giữ nguyên không?
5. Context path hoặc WebFlux base path có được áp dụng không?
6. Reverse proxy đang strip prefix hay giữ prefix?
7. Forwarded headers có được thiết lập bởi proxy đáng tin cậy không?
8. OpenAPI `servers.url` có chứa đúng public base URL và không lặp prefix không?
9. Swagger UI có tải đúng swagger-config và OpenAPI document không?
10. Spring Security matcher có bao phủ UI, JSON, YAML, group và config endpoint không?
11. CI export, API catalog, monitoring và contract test có dùng URL cũ không?
12. Test đã chạy qua ingress/public URL chưa, hay chỉ kiểm tra localhost?

## 17. Nguyên tắc áp dụng

- Giữ riêng API operation path, OpenAPI document path và Swagger UI path.
- Dùng mapping controller cho API nghiệp vụ; dùng `springdoc.api-docs.path` cho JSON/YAML.
- Dùng `springdoc.swagger-ui.path` để đổi entry point giao diện.
- Nhớ rằng group id tạo thêm URL document dưới base path của API docs.
- Phân biệt context path của ứng dụng với mapping controller và prefix reverse proxy.
- Với WebFlux, dùng base path của WebFlux; với Servlet, dùng context path của Servlet.
- Không đặt cùng prefix đồng thời ở proxy rewrite, context path và `servers.url` nếu sẽ tạo URL lặp.
- Giữ OpenAPI `servers.url` là base URL của API operation, không phải URL tải document.
- Cập nhật security matcher cho cả Swagger UI, swagger-config, JSON, YAML và group.
- Kiểm tra URL public qua proxy, không chỉ kiểm tra backend localhost.

Đường dẫn API ứng dụng xác định nơi client thực hiện nghiệp vụ; đường dẫn OpenAPI xác định nơi consumer tải hợp đồng; đường dẫn Swagger UI xác định nơi người phát triển mở giao diện. Context path và reverse proxy có thể thêm prefix cho các URL này, còn `servers.url` mô tả base URL để gọi operation. Khi tách đúng các vai trò, cập nhật đồng bộ cấu hình, security matcher và test qua URL public, ứng dụng có thể đổi cách publish tài liệu mà không vô tình làm thay đổi API nghiệp vụ.

## Tài liệu tham khảo

- [Springdoc OpenAPI FAQ – API docs path và Swagger UI path](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – Core Properties](https://springdoc.org/core-properties.html)
- [Spring Boot – Servlet Web Applications: Context Path](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Framework – Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object)
