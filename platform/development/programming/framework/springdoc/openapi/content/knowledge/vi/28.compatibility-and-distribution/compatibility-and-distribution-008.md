# Công bố nhiều phiên bản hoặc nhiều nhóm trên một giao diện

Một hệ thống Spring Boot có thể duy trì nhiều phiên bản API cùng lúc, chia tài liệu theo nhóm người dùng hoặc tổng hợp tài liệu từ nhiều service. Nếu mỗi tài liệu có một URL riêng, developer phải nhớ nhiều địa chỉ và chuyển qua lại giữa các trang. springdoc-openapi và Swagger UI hỗ trợ công bố các OpenAPI document riêng biệt trong cùng một giao diện, nơi người dùng chọn tài liệu cần xem từ danh sách.

Có hai phần cần phối hợp:

- **Tạo từng OpenAPI document:** dùng `GroupedOpenApi` hoặc `springdoc.group-configs` để giới hạn package, path và điều kiện mapping của từng nhóm.
- **Hiển thị các document:** Swagger UI nhận danh sách URL tài liệu và hiển thị bộ chọn ở thanh trên cùng. Với các group nội bộ do springdoc quản lý, các group được đăng ký vào cấu hình Swagger UI; với tài liệu ngoài hoặc file tĩnh, có thể khai báo danh sách `springdoc.swagger-ui.urls`.

Một giao diện có thể cho người dùng chọn nhiều document, nhưng mỗi lựa chọn vẫn tải một OpenAPI document riêng. Bộ chọn này không hợp nhất các API thành một đặc tả duy nhất. Nếu cần một file hợp đồng đã hợp nhất để phát hành hoặc sinh SDK, cần một bước merge riêng trong pipeline.

## 1. Phân biệt API version, OpenAPI version và group

Trước khi cấu hình, cần phân biệt các khái niệm thường bị gọi chung là version:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Phiên bản API | `/api/v1/orders`, `/api/v2/orders` | Phiên bản hợp đồng mà client sử dụng |
| Phiên bản OpenAPI Specification | `openapi: 3.1.1` | Phiên bản cú pháp và quy tắc của đặc tả OpenAPI |
| Phiên bản document | `info.version: 2.4.0` | Phiên bản của tài liệu API do nhóm phát hành |
| Group | `orders-v1`, `admin`, `partner` | Một góc nhìn hoặc tập operation được chọn để tạo thành document |
| Phiên bản springdoc | `2.x`, `3.x` | Phiên bản thư viện sinh tài liệu, phụ thuộc Spring Boot |

Group không tự tạo ra phiên bản API mới. Ví dụ, group `partner` có thể chứa các endpoint đối tác từ nhiều domain; group `orders-v1` có thể chứa riêng API đơn hàng phiên bản 1. Nhóm phát triển quyết định tên, phạm vi và vòng đời của từng group.

Trường `openapi` trong document cũng không phải phiên bản API. Hai document API v1 và v2 hoàn toàn có thể cùng dùng OpenAPI 3.1. Một document có thể đặt `info.version` là `1.8.0` trong khi API path chứa `/v1`.

## 2. Mô hình nhiều document trên một Swagger UI

Ví dụ ứng dụng có ba document:

| Tên hiển thị | Phạm vi | URL OpenAPI |
|---|---|---|
| Orders API v1 | Hợp đồng cũ cho client chưa nâng cấp | `/v3/api-docs/orders-v1` |
| Orders API v2 | Hợp đồng hiện tại | `/v3/api-docs/orders-v2` |
| Admin API | Operation dành cho quản trị viên | `/v3/api-docs/admin` |

Người dùng mở một trang Swagger UI, sau đó chọn document từ bộ chọn ở thanh trên cùng:

~~~mermaid
flowchart TD
    B[Developer mở /swagger-ui.html]
    U[Swagger UI và bộ chọn document]
    V1[/v3/api-docs/orders-v1]
    V2[/v3/api-docs/orders-v2]
    A[/v3/api-docs/admin]
    B --> U
    U -->|Chọn Orders v1| V1
    U -->|Chọn Orders v2| V2
    U -->|Chọn Admin| A
~~~

Mỗi URL trả về một OpenAPI document độc lập. Khi chọn document khác, Swagger UI tải đặc tả tương ứng và render các operation của document đó. Các URL document có thể nằm trong cùng ứng dụng hoặc đến từ service khác.

## 3. Tạo group theo phiên bản bằng GroupedOpenApi

Cách trực tiếp trong Java là khai báo một bean `GroupedOpenApi` cho mỗi nhóm. Mỗi group cần một tên duy nhất và có thể lọc theo path, package hoặc cả hai.

Giả sử controller được tổ chức theo URL:

~~~text
/api/v1/orders/**
/api/v2/orders/**
/admin/**
~~~

Khai báo:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi ordersV1Api() {
        return GroupedOpenApi.builder()
            .group("orders-v1")
            .pathsToMatch("/api/v1/orders/**")
            .build();
    }

    @Bean
    GroupedOpenApi ordersV2Api() {
        return GroupedOpenApi.builder()
            .group("orders-v2")
            .pathsToMatch("/api/v2/orders/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .packagesToScan("com.acme.api.admin")
            .pathsToMatch("/admin/**")
            .build();
    }
}
~~~

Springdoc tạo URL mặc định:

| Group | URL |
|---|---|
| `orders-v1` | `/v3/api-docs/orders-v1` |
| `orders-v2` | `/v3/api-docs/orders-v2` |
| `admin` | `/v3/api-docs/admin` |

Tên group trở thành một phần của URL document. Nên dùng tên ổn định, dễ đọc, không chứa thông tin thay đổi theo môi trường như hostname hoặc port. Nếu một group lọc đồng thời package và path, operation phải thuộc package được quét và path phù hợp.

Các group nội bộ do springdoc đăng ký sẽ xuất hiện trong cấu hình Swagger UI để người dùng chọn. Không cần khai báo lại các URL group nội bộ bằng `springdoc.swagger-ui.urls` chỉ để tạo thêm một bộ chọn giống hệt.

## 4. Tạo group bằng application.yml

Nếu muốn quản lý group trong cấu hình Spring Boot, dùng `springdoc.group-configs`. Khi cấu hình theo cách này, không cần khai báo bean `GroupedOpenApi` tương ứng cho cùng group.

~~~yaml
springdoc:
  group-configs:
    - group: orders-v1
      display-name: Orders API v1
      paths-to-match:
        - /api/v1/orders/**

    - group: orders-v2
      display-name: Orders API v2
      paths-to-match:
        - /api/v2/orders/**

    - group: admin
      display-name: Admin API
      packages-to-scan:
        - com.acme.api.admin
      paths-to-match:
        - /admin/**
      paths-to-exclude:
        - /admin/internal/**
~~~

`group` là định danh được dùng trong URL document. `display-name` là nhãn hiển thị của group trong giao diện nếu phiên bản springdoc đang dùng hỗ trợ thuộc tính này. `paths-to-match`, `paths-to-exclude`, `packages-to-scan` và `packages-to-exclude` giới hạn operation của group.

Có thể dùng danh sách cấu hình theo profile nếu môi trường cần công bố các nhóm khác nhau. Tuy nhiên, không nên để tài liệu production phụ thuộc vào một profile chỉ có trên máy developer; hãy xác định rõ nhóm nào là contract được phát hành.

### Chọn Java bean hay YAML?

| Nhu cầu | Cách phù hợp |
|---|---|
| Phạm vi group cố định, cần customizer bằng Java | `GroupedOpenApi` bean |
| Danh sách group chủ yếu là package/path và thay đổi theo cấu hình | `springdoc.group-configs` |
| Cần thêm metadata hoặc tùy biến document theo từng group | `GroupedOpenApi` kết hợp `OpenApiCustomizer` |
| Chỉ cần đưa tài liệu của service ngoài vào Swagger UI | `springdoc.swagger-ui.urls` |

Chọn một nguồn cấu hình rõ ràng cho từng group. Không khai báo cùng group name bằng cả bean và YAML nếu không có lý do cụ thể, vì người bảo trì sẽ khó xác định cấu hình nào đang điều khiển document.

## 5. Gắn metadata riêng cho từng phiên bản

Hai API version nên có tiêu đề và `info.version` dễ phân biệt. Có thể dùng `OpenApiCustomizer` gắn với từng `GroupedOpenApi`:

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class VersionedOpenApiConfiguration {

    @Bean
    GroupedOpenApi ordersV1Api() {
        return GroupedOpenApi.builder()
            .group("orders-v1")
            .pathsToMatch("/api/v1/orders/**")
            .addOpenApiCustomizer(openApi -> {
                if (openApi.getInfo() == null) {
                    openApi.setInfo(new Info());
                }
                openApi.getInfo()
                    .title("Orders API")
                    .version("1.8.0")
                    .description("Hợp đồng API đơn hàng phiên bản 1.");
            })
            .build();
    }

    @Bean
    GroupedOpenApi ordersV2Api() {
        return GroupedOpenApi.builder()
            .group("orders-v2")
            .pathsToMatch("/api/v2/orders/**")
            .addOpenApiCustomizer(openApi -> {
                if (openApi.getInfo() == null) {
                    openApi.setInfo(new Info());
                }
                openApi.getInfo()
                    .title("Orders API")
                    .version("2.4.0")
                    .description("Hợp đồng API đơn hàng phiên bản 2.");
            })
            .build();
    }
}
~~~

Customizer trong ví dụ được gắn trực tiếp vào group tương ứng nên metadata của v1 và v2 độc lập. Nếu dùng `OpenAPI` bean hoặc customizer dùng chung cho toàn ứng dụng, hãy kiểm tra phạm vi áp dụng để không vô tình ghi đè `info` của các group khác.

`info.version` nên theo quy tắc phát hành tài liệu của nhóm. Nó có thể là semantic version như `2.4.0`; không bắt buộc phải trùng tên group hoặc path segment `v2`.

## 6. Đưa nhiều document vào Swagger UI bằng urls

Khi cần kiểm soát tường minh danh sách document, đặc biệt khi tài liệu đến từ service ngoài hoặc file OpenAPI tĩnh, dùng `springdoc.swagger-ui.urls`.

~~~yaml
springdoc:
  swagger-ui:
    path: /swagger-ui.html
    urls:
      - name: Customer API v1
        url: https://customer-api.example.com/v3/api-docs/v1
      - name: Customer API v2
        url: https://customer-api.example.com/v3/api-docs/v2
      - name: Billing API
        url: https://billing-api.example.com/v3/api-docs
    urls-primary-name: Customer API v2
~~~

Các thuộc tính có ý nghĩa:

- `urls`: danh sách tài liệu mà Swagger UI có thể tải và hiển thị trong bộ chọn.
- `urls[].name`: tên duy nhất của tài liệu trong giao diện.
- `urls[].url`: URL mà trình duyệt gọi để lấy OpenAPI document; các URL trong danh sách phải duy nhất.
- `urls-primary-name`: tên document được chọn mặc định khi Swagger UI tải.
- `path`: đường dẫn trang HTML Swagger UI, mặc định là `/swagger-ui.html`.

Nếu cấu hình `urls`, thuộc tính đơn `springdoc.swagger-ui.url` sẽ bị bỏ qua. Không khai báo cả `url` và `urls` với kỳ vọng hai cấu hình được ghép lại.

### Khi nào cần khai báo urls thủ công?

| Nguồn document | Cách cấu hình |
|---|---|
| Group nội bộ được tạo bằng `GroupedOpenApi` | Springdoc đăng ký group trong cấu hình Swagger UI |
| Group nội bộ được tạo bằng `springdoc.group-configs` | Springdoc đăng ký group trong cấu hình Swagger UI |
| OpenAPI endpoint từ service khác | Khai báo URL tuyệt đối trong `springdoc.swagger-ui.urls` |
| File OpenAPI tĩnh được phục vụ bởi ứng dụng | Khai báo URL file trong `springdoc.swagger-ui.urls` |
| Chỉ có một file OpenAPI tĩnh | Có thể dùng `springdoc.swagger-ui.url` |

Nếu tự khai báo danh sách `urls` cho cả group nội bộ và tài liệu ngoài, hãy bảo đảm mỗi document chỉ xuất hiện một lần và tên/URL không trùng nhau.

## 7. Tổng hợp tài liệu từ nhiều microservice

Một developer portal có thể chạy Swagger UI riêng và tải tài liệu từ nhiều service:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Identity
        url: https://identity.example.com/v3/api-docs
      - name: Catalog
        url: https://catalog.example.com/v3/api-docs
      - name: Orders
        url: https://orders.example.com/v3/api-docs
      - name: Payments
        url: https://payments.example.com/v3/api-docs
    urls-primary-name: Catalog
~~~

Trong mô hình này:

- Developer portal phục vụ trang Swagger UI.
- Mỗi microservice vẫn chịu trách nhiệm tạo và phát hành OpenAPI document của chính nó.
- Swagger UI tải một document theo lựa chọn của người dùng.
- Mỗi document có thể có `servers` riêng trỏ đến API host tương ứng.

Đây là cách tổng hợp nhiều tài liệu vào một giao diện. Nó không tạo một OpenAPI document hợp nhất và không thay thế API gateway.

### Cấu hình CORS trên service cung cấp tài liệu

Nếu Swagger UI và OpenAPI endpoint ở khác origin, trình duyệt sẽ áp dụng CORS. Service cung cấp tài liệu cần cho phép origin của developer portal đọc endpoint OpenAPI.

Ví dụ cấu hình Spring MVC trên service cung cấp document:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class OpenApiCorsConfiguration {

    @Bean
    WebMvcConfigurer openApiCorsConfigurer() {
        return new WebMvcConfigurer() {
            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/v3/api-docs/**")
                    .allowedOrigins("https://developer.example.com")
                    .allowedMethods("GET")
                    .allowedHeaders("Accept", "Authorization");
            }
        };
    }
}
~~~

Đặt cấu hình CORS ở phía server thực sự trả OpenAPI document. Nếu người dùng còn cần bấm Try it out để gọi API từ browser, endpoint business cũng cần chính sách CORS phù hợp. CORS cho tài liệu và CORS cho API operations là hai luồng request khác nhau.

Không mở CORS cho mọi origin trong production chỉ để Swagger UI hoạt động. Chỉ cho phép origin developer portal đã biết, các method và header cần thiết; phối hợp CORS với authentication và authorization.

## 8. Phục vụ file OpenAPI tĩnh cùng giao diện

Có trường hợp nhóm phát hành tài liệu đã được build và kiểm tra trong CI, không muốn Swagger UI phụ thuộc vào endpoint sinh tài liệu lúc runtime. Có thể đặt file OpenAPI vào static resources:

~~~text
src/main/resources/
└── static/
    └── openapi/
        ├── orders-v1.yaml
        ├── orders-v2.yaml
        └── billing-v3.yaml
~~~

Khi ứng dụng phục vụ static resource, các file có thể được truy cập qua:

~~~text
/openapi/orders-v1.yaml
/openapi/orders-v2.yaml
/openapi/billing-v3.yaml
~~~

Đăng ký trong Swagger UI:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Orders API v1
        url: /openapi/orders-v1.yaml
      - name: Orders API v2
        url: /openapi/orders-v2.yaml
      - name: Billing API v3
        url: /openapi/billing-v3.yaml
    urls-primary-name: Orders API v2
~~~

File tĩnh phải là OpenAPI document hợp lệ và URL phải truy cập được từ browser. Nếu ứng dụng chạy dưới context path, reverse proxy hoặc prefix riêng, URL trong `urls` phải bao gồm đường dẫn public tương ứng.

Với chỉ một file tĩnh, có thể dùng:

~~~yaml
springdoc:
  swagger-ui:
    url: /openapi/orders-v2.yaml
~~~

Chỉ dùng `url` đơn khi không cấu hình `urls`.

## 9. Phân biệt URL lấy document và server URL trong document

Hai URL sau thường bị nhầm:

- `springdoc.swagger-ui.urls[].url`: nơi Swagger UI tải file OpenAPI.
- `servers[].url` trong OpenAPI document: base URL của API mà người dùng gọi bằng Try it out hoặc client.

Ví dụ, Swagger UI lấy tài liệu từ portal:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Orders v2
        url: https://docs.example.com/specs/orders-v2.yaml
~~~

Trong file `orders-v2.yaml`, server có thể là:

~~~yaml
openapi: 3.1.1
info:
  title: Orders API
  version: 2.4.0
servers:
  - url: https://api.example.com/api/v2
paths:
  /orders:
    get:
      responses:
        '200':
          description: Danh sách đơn hàng
~~~

Swagger UI tải document từ `docs.example.com`, nhưng request Try it out gửi đến `api.example.com`. Hai host có thể khác nhau và cần cấu hình truy cập, CORS, TLS, authentication riêng.

Khi triển khai sau reverse proxy, kiểm tra `servers` trong từng document có trỏ đến public URL mà browser truy cập được. Đừng dùng URL nội bộ trong mạng container nếu developer truy cập Swagger UI từ bên ngoài.

## 10. Phiên bản API dùng chung path hoặc header

Nhiều hệ thống version API bằng path như `/api/v1/**` và `/api/v2/**`; đây là cách dễ tách group nhất vì mỗi phiên bản có URL rõ ràng.

Một số hệ thống dùng header để chọn phiên bản:

~~~java
@GetMapping(
    path = "/api/orders",
    headers = "X-API-Version=v1"
)
public List<OrderV1Response> listV1() {
    return orderService.listV1();
}

@GetMapping(
    path = "/api/orders",
    headers = "X-API-Version=v2"
)
public List<OrderV2Response> listV2() {
    return orderService.listV2();
}
~~~

Trong trường hợp này, có thể tách tài liệu bằng header condition của group:

~~~java
@Bean
GroupedOpenApi ordersV1Api() {
    return GroupedOpenApi.builder()
        .group("orders-v1")
        .pathsToMatch("/api/orders")
        .headersToMatch("X-API-Version=v1")
        .build();
}

@Bean
GroupedOpenApi ordersV2Api() {
    return GroupedOpenApi.builder()
        .group("orders-v2")
        .pathsToMatch("/api/orders")
        .headersToMatch("X-API-Version=v2")
        .build();
}
~~~

Mỗi group có thể mô tả cùng path và HTTP method nhưng schema khác nhau trong document riêng. Tuy nhiên, header condition của Spring mapping không tự bảo đảm header được hiển thị như một request parameter trong OpenAPI. Nếu consumer phải gửi header phiên bản, hãy mô tả nó rõ ràng bằng `@RequestHeader` hoặc `@Parameter(in = ParameterIn.HEADER)` và xác minh trong document.

Trong một OpenAPI document, một cặp path + HTTP method chỉ có một operation. Không thể biểu diễn hai handler method khác schema cho cùng path/method chỉ bằng cách tạo hai overload trong cùng một document. Hãy tách thành hai group hoặc dùng path version riêng.

## 11. Tổ chức group theo consumer và quyền truy cập

Group có thể đại diện cho phiên bản, domain hoặc đối tượng sử dụng:

| Group | Nội dung | Consumer |
|---|---|---|
| `public-v2` | API công khai phiên bản 2 | Khách hàng và đối tác |
| `partner` | Endpoint dành riêng cho đối tác tích hợp | Partner developers |
| `admin` | Endpoint quản trị | Đội vận hành |
| `internal` | Endpoint giữa các service | Developer nội bộ |

Chỉ đưa operation cần thiết vào từng document. Dùng package/path filter để tránh tài liệu public vô tình chứa endpoint nội bộ.

Group không phải security boundary. Ẩn một document khỏi Swagger UI không ngăn người dùng gọi endpoint nếu runtime không bảo vệ endpoint đó. Nếu document nội bộ không được public, hãy bảo vệ cả trang Swagger UI lẫn endpoint `/v3/api-docs/{group}` bằng Spring Security, API gateway hoặc cơ chế truy cập của tổ chức.

Nếu portal tổng hợp tài liệu từ service khác, mỗi service vẫn phải kiểm soát quyền đọc document của mình. CORS chỉ quyết định browser có được đọc response cross-origin; nó không xác thực người dùng và không thay thế authorization.

## 12. Duy trì nhiều phiên bản trong vòng đời API

Khi công bố v1 và v2 cùng lúc, cần có chính sách vòng đời rõ ràng:

1. Giữ document v1 ổn định cho client chưa nâng cấp.
2. Công bố v2 với group name và `info.version` riêng.
3. Đánh dấu operation cũ deprecated khi bắt đầu lộ trình ngừng hỗ trợ.
4. Ghi rõ ngày dự kiến kết thúc hỗ trợ trong mô tả hoặc tài liệu phát hành.
5. Theo dõi consumer còn sử dụng v1 trước khi gỡ endpoint và document.
6. Giữ lại artifact OpenAPI của bản phát hành cũ để đối chiếu và hỗ trợ client hiện tại.

Ví dụ đánh dấu operation cũ:

~~~java
@Operation(
    summary = "Lấy đơn hàng phiên bản cũ",
    deprecated = true
)
@GetMapping("/api/v1/orders/{id}")
public OrderV1Response getOrderV1(@PathVariable long id) {
    return orderService.getV1(id);
}
~~~

`deprecated = true` giúp công cụ tiêu thụ nhận biết operation không nên dùng cho tích hợp mới. Nó không tự tắt endpoint và không tự thông báo cho client; nhóm vẫn cần kế hoạch migration và thông báo phát hành.

## 13. Kiểm tra Swagger UI và từng document

Sau khi cấu hình, kiểm tra riêng từng URL thay vì chỉ mở trang Swagger UI.

Lấy document v1:

~~~bash
curl -i http://localhost:8080/v3/api-docs/orders-v1
~~~

Lấy document v2:

~~~bash
curl -i http://localhost:8080/v3/api-docs/orders-v2
~~~

Kiểm tra cấu hình Swagger UI mà springdoc cung cấp:

~~~bash
curl -s http://localhost:8080/v3/api-docs/swagger-config
~~~

Với danh sách URL khai báo tường minh, response cấu hình cần chứa đúng tên và URL của các document. Sau đó mở:

~~~text
http://localhost:8080/swagger-ui.html
~~~

Kiểm tra:

- Bộ chọn hiển thị đúng tên các document.
- Document mặc định là phiên bản mong muốn.
- Chọn v1 chỉ thấy operation của v1.
- Chọn v2 chỉ thấy operation của v2.
- Mỗi document render thành công, schema và security scheme hiển thị đúng.
- Try it out gọi đúng `servers` của document đang chọn.

Nếu dùng context path, ví dụ `/shop`, các URL public sẽ có prefix tương ứng như `/shop/v3/api-docs/orders-v1` và `/shop/swagger-ui.html`. Khi cấu hình `urls` thủ công, phải dùng URL mà browser thực sự truy cập được sau khi đi qua proxy.

## 14. Kiểm thử danh sách group và phạm vi operation

Có thể dùng integration test để xác minh từng group trả document đúng:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiGroupsTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void ordersV1DocumentContainsOnlyV1Paths() throws Exception {
        mockMvc.perform(get("/v3/api-docs/orders-v1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/v1/orders']").exists())
            .andExpect(jsonPath("$.paths['/api/v2/orders']").doesNotExist());
    }

    @Test
    void ordersV2DocumentContainsOnlyV2Paths() throws Exception {
        mockMvc.perform(get("/v3/api-docs/orders-v2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/v2/orders']").exists())
            .andExpect(jsonPath("$.paths['/api/v1/orders']").doesNotExist());
    }
}
~~~

Nếu nhóm dùng chung path và header version, assertion cần kiểm tra đúng operation, parameter header và schema của từng document. Không chỉ kiểm tra endpoint tài liệu trả `200`; document có thể hợp lệ về cú pháp nhưng chứa nhầm operation.

Đối với cấu hình `urls` thủ công, kiểm tra response `/v3/api-docs/swagger-config` hoặc dùng smoke test browser để xác nhận topbar nhận đúng danh sách. Test API document và test giao diện là hai kiểm tra bổ sung cho nhau.

## 15. Phát hành OpenAPI artifact theo phiên bản

Với API quan trọng, nên lưu OpenAPI document như một artifact của release:

~~~text
openapi/
├── orders/
│   ├── v1/
│   │   └── openapi.yaml
│   └── v2/
│       └── openapi.yaml
└── billing/
    └── v3/
        └── openapi.yaml
~~~

Pipeline có thể:

1. Khởi động ứng dụng hoặc dùng công cụ build-time để lấy OpenAPI document.
2. Tải document của từng group.
3. Validate cú pháp và OpenAPI version.
4. Chạy lint rule và contract diff với artifact của release trước.
5. Lưu file theo API version bất biến.
6. Cập nhật danh sách Swagger UI để trỏ tới artifact cần công bố.

Nên giữ URL phát hành cũ ổn định trong suốt thời gian hỗ trợ client. Có thể có alias như `latest` hoặc `current`, nhưng alias cần được cập nhật có kiểm soát và không thay thế artifact có version cụ thể.

Nếu tài liệu được lấy từ microservice ngoài, portal cần xử lý trường hợp service chưa sẵn sàng hoặc URL tạm thời lỗi. Không để việc một service không khả dụng làm mất toàn bộ tài liệu đã lưu trữ của các service khác.

## 16. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Swagger UI chỉ hiển thị một document | Chỉ cấu hình một `url`, hoặc group chưa được đăng ký | Tạo `GroupedOpenApi`/`group-configs` hoặc cấu hình danh sách `urls` |
| `/v3/api-docs/{group}` trả 404 | Group name sai hoặc group chưa được tạo | Kiểm tra tên group, bean scan và cấu hình group |
| Hai document có cùng tên trong bộ chọn | Trùng `group` hoặc `urls[].name` | Đặt tên group và nhãn URL duy nhất |
| URL document bị trùng | Nhiều mục `urls` trỏ cùng một URL | Mỗi URL trong danh sách cần là một định danh duy nhất |
| Chọn v1 nhưng thấy endpoint v2 | `paths-to-match` quá rộng hoặc package filter không đúng | Thu hẹp path/package và kiểm tra JSON document |
| Group rỗng | Path/package không khớp mapping thực tế | So sánh request mapping và bộ lọc của group |
| `urls` ngoài domain không tải được | CORS chưa cho phép origin của Swagger UI hoặc URL không public | Cấu hình CORS ở service cung cấp document và kiểm tra URL từ browser |
| Tài liệu tải được nhưng Try it out lỗi CORS | API server chưa cho phép origin portal gọi business endpoint | Cấu hình CORS riêng cho API operations |
| Swagger UI vẫn mở document cũ | `urls-primary-name` không khớp hoặc browser/cache giữ cấu hình cũ | Kiểm tra `/v3/api-docs/swagger-config`, URL và cache |
| `springdoc.swagger-ui.url` không có tác dụng | Đang cấu hình `springdoc.swagger-ui.urls` | Chỉ dùng `url` khi không có danh sách `urls` |
| Document hiển thị nhưng request gọi sai host | `servers[].url` trong OpenAPI không đúng public API URL | Cập nhật server URL hoặc cấu hình proxy/forwarded headers |
| Swagger UI không render một document | UI hiện tại không hỗ trợ OpenAPI version hoặc feature mà document dùng | Kiểm tra tương thích Swagger UI và validator với từng document |
| Tài liệu nội bộ vẫn truy cập được trực tiếp | Chỉ ẩn group trong UI, chưa bảo vệ endpoint tài liệu | Áp dụng authentication/authorization cho UI và `/v3/api-docs/**` |
| Cấu hình có cả bean và YAML khó dự đoán | Một group được khai báo ở nhiều nguồn | Chọn một nguồn cấu hình cho mỗi group |
| Nâng v2 làm client v1 bị lỗi | Controller/schema v1 bị thay đổi cùng lúc | Tách implementation và artifact theo version, giữ contract cũ trong thời gian hỗ trợ |

## 17. Quy trình thiết kế một giao diện tài liệu nhiều phiên bản

Thực hiện theo trình tự:

1. Liệt kê các API version, domain và consumer cần công bố.
2. Quyết định group đại diện cho version, consumer hay domain.
3. Chọn path hoặc package để phân chia operation rõ ràng.
4. Tạo từng document bằng `GroupedOpenApi` hoặc `springdoc.group-configs`.
5. Đặt `info.title`, `info.version`, mô tả và `servers` phù hợp cho mỗi document.
6. Kiểm tra URL `/v3/api-docs/{groupName}` và phạm vi operation.
7. Dùng Swagger UI group selector cho các group nội bộ; dùng `springdoc.swagger-ui.urls` cho tài liệu ngoài hoặc file tĩnh.
8. Chọn document mặc định bằng `urls-primary-name` khi dùng danh sách URL tường minh.
9. Kiểm tra CORS, authentication, context path và public URL nếu có service ngoài hoặc reverse proxy.
10. Validate từng document, chạy contract diff và lưu artifact theo release.
11. Kiểm tra vòng đời version cũ, deprecation và ngày kết thúc hỗ trợ.

Giữ cấu hình đơn giản theo số lượng document thực sự cần công bố. Một group quá rộng có thể trộn các hợp đồng không liên quan; quá nhiều group nhỏ làm bộ chọn khó sử dụng. Tên group nên thể hiện rõ domain và version.

## 18. Checklist trước khi công bố

- [ ] Mỗi group có tên duy nhất và URL document xác định.
- [ ] Bộ lọc package/path phản ánh đúng phạm vi operation của group.
- [ ] Các phiên bản API có `info.version` và metadata rõ ràng.
- [ ] Phiên bản OpenAPI Specification được phân biệt với phiên bản API.
- [ ] Group nội bộ và group YAML không khai báo trùng nguồn.
- [ ] Swagger UI hiển thị đúng các group cần thiết.
- [ ] Danh sách `urls` có tên và URL duy nhất.
- [ ] `urls-primary-name` chọn đúng document mặc định nếu dùng `urls`.
- [ ] URL document và `servers[].url` được kiểm tra riêng.
- [ ] Tài liệu ngoài có CORS phù hợp ở phía cung cấp document.
- [ ] API operations có CORS phù hợp nếu Try it out gọi cross-origin.
- [ ] Tài liệu và Swagger UI được bảo vệ theo chính sách truy cập.
- [ ] Mỗi document được validate và contract diff trước khi phát hành.
- [ ] Artifact version cũ được lưu trong thời gian hỗ trợ.
- [ ] API cũ có kế hoạch deprecation và migration cho consumer.

## 19. Tài liệu tham khảo chính thức

- [springdoc-openapi FAQ — Multiple OpenAPI definitions](https://springdoc.org/faq.html) — tạo nhiều `GroupedOpenApi`, URL `/v3/api-docs/{groupName}` và cấu hình group bằng YAML.
- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html) — `springdoc.group-configs`, `springdoc.swagger-ui.urls`, `urlsPrimaryName`, `url`, `configUrl` và các thuộc tính Swagger UI.
- [springdoc-openapi Getting Started](https://springdoc.org/getting-started.html) — dependency tích hợp Swagger UI và endpoint JSON/YAML.
- [Swagger UI Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/) — cấu hình danh sách URL và topbar của Swagger UI.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html) — cấu hình CORS cho Spring MVC.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html) — cấu trúc `info`, `servers`, `paths` và các thành phần của OpenAPI document.

Một Swagger UI có thể làm giao diện chung cho nhiều API version, group hoặc service. Hãy tạo document độc lập và có tên ổn định, cấu hình bộ chọn phù hợp, rồi kiểm tra URL tải tài liệu, server URL, CORS và quyền truy cập. Cách này giúp developer chuyển giữa các hợp đồng trong một giao diện mà vẫn giữ ranh giới và vòng đời của từng API rõ ràng.
