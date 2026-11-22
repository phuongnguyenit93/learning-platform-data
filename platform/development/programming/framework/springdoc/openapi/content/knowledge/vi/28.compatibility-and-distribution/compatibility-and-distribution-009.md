# Tổng hợp tài liệu nhiều dịch vụ và xử lý URL máy chủ

Trong kiến trúc nhiều service, mỗi ứng dụng Spring Boot có thể sinh một tài liệu OpenAPI riêng. Nhóm phát triển thường muốn đặt các tài liệu đó trong một Swagger UI chung, đồng thời bảo đảm URL trong tài liệu trỏ tới endpoint public qua API gateway hoặc reverse proxy.

Với springdoc-openapi, cần phân biệt ba lớp:

1. **Nhiều nhóm tài liệu trong cùng một ứng dụng:** dùng GroupedOpenApi để tạo nhiều OpenAPI document từ một Spring Boot service.
2. **Nhiều tài liệu từ nhiều service:** dùng danh sách springdoc.swagger-ui.urls để Swagger UI cung cấp bộ chọn tài liệu.
3. **Một tài liệu OpenAPI hợp nhất:** cần một bước aggregation thực sự để kết hợp paths, schemas, security schemes và metadata từ nhiều document.

Swagger UI có thể hiển thị nhiều tài liệu trong cùng giao diện, nhưng bộ chọn tài liệu không tự hợp nhất các document thành một OpenAPI spec duy nhất. Đồng thời, server URL trong từng document phải phản ánh địa chỉ mà consumer có thể truy cập, không phải hostname nội bộ của container.

Bài này hướng dẫn thiết kế endpoint tài liệu, cấu hình Swagger UI nhiều service, xử lý URL qua gateway/proxy, khai báo servers, bảo vệ tài liệu, kiểm thử và phân phối spec.

## 1. Các mô hình tổ chức tài liệu

Có ba mô hình thường gặp:

| Mô hình | Nguồn tài liệu | Kết quả |
|---|---|---|
| Grouped documents | Nhiều nhóm controller trong một Spring Boot app | Nhiều URL OpenAPI trong cùng service |
| Multi-service Swagger UI | OpenAPI endpoint của nhiều service | Một Swagger UI có danh sách để chọn từng document |
| Merged OpenAPI | Nhiều document được parse và hợp nhất | Một OpenAPI document chứa paths/components của nhiều service |

GroupedOpenApi phù hợp khi một ứng dụng có nhiều nhóm API như public, admin và partner. Swagger UI multi-URL phù hợp khi một portal tài liệu cần hiển thị API của orders, catalog, identity hoặc payment service.

Merged OpenAPI phù hợp khi consumer hoặc công cụ downstream yêu cầu đúng một file spec chứa toàn bộ contract. Việc này cần giải quyết xung đột tên schema, operationId, security scheme, server và path.

Trước khi cấu hình, hãy xác định consumer cần một giao diện chọn nhiều tài liệu hay một document duy nhất. Hai nhu cầu này có kiến trúc và quy trình kiểm thử khác nhau.

## 2. GroupedOpenApi trong một service

GroupedOpenApi tạo các document độc lập từ controller trong cùng một Spring Boot application.

Ví dụ chia API public và admin:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiDocumentationGroups {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .build();
    }
}
~~~

Với cấu hình mặc định, các document có thể được tải tại:

~~~text
/v3/api-docs/public
/v3/api-docs/admin
~~~

Tên group trở thành phần cuối của endpoint tài liệu. Mỗi group có thể được cấu hình pathsToMatch, pathsToExclude, packagesToScan, packagesToExclude và customizer riêng.

Không dùng group để đại diện cho các service đang chạy ở host khác. GroupedOpenApi chỉ phân tích endpoint thuộc ApplicationContext hiện tại.

## 3. Chọn group theo package hoặc path

Nếu các controller được chia package:

~~~java
@Bean
GroupedOpenApi catalogApi() {
    return GroupedOpenApi.builder()
        .group("catalog")
        .packagesToScan("com.example.catalog.api")
        .build();
}
~~~

Nếu muốn lọc theo URL:

~~~java
@Bean
GroupedOpenApi orderApi() {
    return GroupedOpenApi.builder()
        .group("orders")
        .pathsToMatch("/api/orders/**")
        .pathsToExclude("/api/orders/internal/**")
        .build();
}
~~~

Chọn một tiêu chí ổn định phù hợp với cấu trúc source. Package filter hữu ích khi boundary được tổ chức theo module; path filter hữu ích khi boundary thể hiện qua route.

Sau khi tạo group, tải endpoint của từng group và xác minh không bị thiếu operation. Hai group có thể cùng chứa một operation nếu filter giao nhau; hãy chủ động quyết định đây có phải hành vi mong muốn hay không.

## 4. Swagger UI hiển thị nhiều tài liệu từ nhiều service

springdoc hỗ trợ cấu hình danh sách URL cho Swagger UI bằng springdoc.swagger-ui.urls.

Ví dụ một portal tài liệu truy cập ba service qua API gateway:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
    disable-swagger-default-url: true
    urls:
      - name: Orders
        url: /orders/v3/api-docs
      - name: Catalog
        url: /catalog/v3/api-docs
      - name: Identity
        url: /identity/v3/api-docs
    urls-primary-name: Orders
~~~

Khi mở /docs, Swagger UI hiển thị bộ chọn để người dùng chọn Orders, Catalog hoặc Identity. urls-primary-name chỉ định document được chọn khi UI khởi tạo.

Tên trong danh sách phải duy nhất; URL cũng phải duy nhất vì Swagger UI sử dụng chúng làm định danh các lựa chọn. Dùng tên ngắn, rõ ràng và thống nhất với tên service hoặc API domain.

Các URL tương đối như /orders/v3/api-docs thường thuận tiện khi portal và các service được đưa qua cùng một origin gateway. Browser tải tài liệu từ cùng host nên tránh được nhiều vấn đề CORS.

## 5. Cấu hình danh sách URL bằng application.properties

Có thể dùng application.properties thay cho YAML:

~~~properties
springdoc.swagger-ui.path=/docs
springdoc.swagger-ui.disable-swagger-default-url=true
springdoc.swagger-ui.urls[0].name=Orders
springdoc.swagger-ui.urls[0].url=/orders/v3/api-docs
springdoc.swagger-ui.urls[1].name=Catalog
springdoc.swagger-ui.urls[1].url=/catalog/v3/api-docs
springdoc.swagger-ui.urls[2].name=Identity
springdoc.swagger-ui.urls[2].url=/identity/v3/api-docs
springdoc.swagger-ui.urls-primary-name=Orders
~~~

Cấu hình danh sách URL nằm trong Swagger UI. Nó không tạo proxy route và cũng không làm service đích tự động mở endpoint tài liệu.

Bạn vẫn cần bảo đảm mỗi URL trả về OpenAPI JSON hợp lệ và portal có quyền truy cập URL đó.

## 6. Phân biệt url đơn với urls nhiều tài liệu

Swagger UI có thể cấu hình một URL spec duy nhất hoặc một danh sách URL:

| Property | Mục đích |
|---|---|
| springdoc.swagger-ui.url | Tải một OpenAPI document |
| springdoc.swagger-ui.urls | Hiển thị danh sách nhiều OpenAPI document |
| springdoc.swagger-ui.urls-primary-name | Chọn tên document ban đầu trong danh sách |
| springdoc.swagger-ui.configUrl | URL tải cấu hình Swagger UI |
| springdoc.swagger-ui.path | Đường dẫn trang HTML Swagger UI |

Nếu portal cần nhiều service, dùng urls. Nếu chỉ muốn thay spec mặc định bằng một file tĩnh hoặc URL khác, url có thể phù hợp.

Không cấu hình url và urls cùng lúc một cách tùy tiện. Hãy xác định nguồn document mà UI phải sử dụng và kiểm tra swagger-config được sinh ra.

## 7. Endpoint swagger-config và luồng tải tài liệu

Mặc định Swagger UI lấy cấu hình từ endpoint:

~~~text
/v3/api-docs/swagger-config
~~~

Khi cấu hình danh sách URLs, endpoint cấu hình sẽ cung cấp thông tin để Swagger UI dựng bộ chọn document.

Luồng tải thường là:

~~~text
Browser
  |
  v
/docs
  |
  v
Swagger UI JavaScript
  |
  v
/v3/api-docs/swagger-config
  |
  v
Danh sách Orders, Catalog, Identity
  |
  +----> /orders/v3/api-docs
  |
  +----> /catalog/v3/api-docs
  |
  +----> /identity/v3/api-docs
~~~

Nếu trang UI mở được nhưng danh sách trống, kiểm tra response của swagger-config và network request tải từng document. Lỗi có thể nằm ở cấu hình, reverse proxy, authentication hoặc CORS.

Nếu thay configUrl, phải bảo đảm endpoint cấu hình mới trả đúng định dạng mà Swagger UI mong đợi. Không nhầm configUrl với URL của OpenAPI JSON.

## 8. Gateway route cho nhiều service

Một API gateway có thể cung cấp prefix public cho từng service:

~~~text
https://api.example.com/orders/**
https://api.example.com/catalog/**
https://api.example.com/identity/**
~~~

Gateway chuyển tiếp các route đến service tương ứng. Ví dụ cấu hình minh họa với Spring Cloud Gateway:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://orders-service:8080
          predicates:
            - Path=/orders/**
          filters:
            - StripPrefix=1
        - id: catalog
          uri: http://catalog-service:8080
          predicates:
            - Path=/catalog/**
          filters:
            - StripPrefix=1
~~~

Khi browser yêu cầu /orders/v3/api-docs, gateway bỏ prefix /orders và chuyển tiếp /v3/api-docs đến orders-service.

Đây chỉ là ví dụ route. Cấu hình thực tế còn cần timeout, TLS, authentication, rate limit, health check và quy tắc forwarded headers.

Swagger UI portal có thể dùng URL cùng origin:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Orders
        url: /orders/v3/api-docs
      - name: Catalog
        url: /catalog/v3/api-docs
~~~

Gateway phải cho phép truy cập cả tài liệu lẫn API operation mà người dùng gọi bằng nút Try it out.

## 9. URL trong OpenAPI server object có ý nghĩa gì?

Trong OpenAPI, servers xác định base URL mà consumer dùng để gọi operation. Path của operation được nối vào server URL.

Ví dụ document có:

~~~yaml
servers:
  - url: https://api.example.com/orders
paths:
  /api/orders:
    get:
      responses:
        "200":
          description: Thành công
~~~

URL được gọi là:

~~~text
https://api.example.com/orders/api/orders
~~~

Nếu server URL là https://orders-service:8080 thì client bên ngoài có thể cố gọi hostname nội bộ và thất bại.

Server URL phải là địa chỉ mà consumer mục tiêu truy cập được. Với tài liệu public qua gateway, hãy dùng public hostname và prefix public hoặc một URL tương đối phù hợp.

## 10. Dùng server URL tương đối khi portal cùng origin

OpenAPI cho phép server URL tương đối. Ví dụ:

~~~yaml
servers:
  - url: /orders
    description: Orders service qua API gateway
~~~

Nếu document được tải từ https://api.example.com/orders/v3/api-docs, server URL /orders được browser giải quyết trên cùng origin:

~~~text
https://api.example.com/orders
~~~

Operation path /api/orders sẽ trở thành:

~~~text
https://api.example.com/orders/api/orders
~~~

Cách này hữu ích khi cùng một API được triển khai ở nhiều domain nhưng giữ nguyên prefix path. Consumer dùng host của document hiện tại và không phải hard-code hostname môi trường.

Hãy kiểm tra cách công cụ client generator xử lý relative server URL. Một số client được sinh có thể cần base URL được truyền qua cấu hình runtime.

## 11. Khai báo server cố định bằng @OpenAPIDefinition

Nếu service có một public base path cố định, có thể khai báo server trong annotation:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "/orders",
            description = "Orders service qua API gateway"
        )
    }
)
class OpenApiServerConfiguration {
}
~~~

Khi server annotations hiện diện, springdoc sử dụng server được khai báo thay cho URL được suy ra tự động từ request.

Đây là lựa chọn đơn giản khi một service có một public path ổn định. Nếu cần URL khác nhau theo môi trường, dùng cấu hình hoặc OpenAPI bean/customizer để tránh phải thay source code khi deploy.

## 12. Khai báo servers bằng OpenAPI bean

Có thể tạo OpenAPI bean:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class OpenApiServerBeanConfiguration {

    @Bean
    OpenAPI openAPI() {
        return new OpenAPI()
            .servers(List.of(
                new Server()
                    .url("/orders")
                    .description("Public gateway route"),
                new Server()
                    .url("https://staging.example.com/orders")
                    .description("Staging")
            ));
    }
}
~~~

OpenAPI bean có thể cung cấp metadata dùng chung trong document. Nếu một ứng dụng có nhiều GroupedOpenApi và mỗi group có server khác nhau, cần kiểm tra phạm vi áp dụng và dùng customizer gắn đúng group khi cần.

Không đưa hostname nội bộ như orders-service:8080 vào document public. Địa chỉ nội bộ có thể thay đổi theo container, cluster hoặc service discovery.

## 13. Nhiều server cho production và staging

OpenAPI cho phép liệt kê nhiều server:

~~~yaml
servers:
  - url: https://api.example.com/orders
    description: Production
  - url: https://staging-api.example.com/orders
    description: Staging
~~~

Swagger UI có thể hiển thị lựa chọn server cho operation. Người dùng có thể chọn môi trường để thực hiện Try it out nếu CORS và authentication cho phép.

Chỉ công bố server mà người xem tài liệu được phép sử dụng. Không thêm dev URL, localhost hoặc endpoint quản trị nội bộ vào tài liệu public.

Nếu staging dùng credential khác production, hãy làm rõ trong hướng dẫn và bảo đảm Swagger UI không tự gửi credential production sang host khác.

## 14. Dùng server variables cho môi trường

Nếu hostname hoặc version path có quy ước, server variables có thể giảm lặp:

~~~yaml
servers:
  - url: https://{environment}.example.com/{service}
    description: API theo môi trường
    variables:
      environment:
        default: api
        enum:
          - api
          - staging-api
      service:
        default: orders
        enum:
          - orders
          - catalog
~~~

Server variables phù hợp khi các giá trị thuộc một tập có kiểm soát. Không dùng biến để cho phép nhập URL tùy ý nếu có thể dẫn tới gọi nhầm host hoặc gửi credential đến endpoint không tin cậy.

Với các service có domain và security policy khác nhau, document riêng theo service thường rõ ràng hơn việc dùng một server variable chung.

## 15. Xử lý reverse proxy và forwarded headers

Khi ứng dụng chạy sau reverse proxy, request đến Spring Boot có thể mang host, scheme, port hoặc prefix nội bộ. Client bên ngoài lại truy cập bằng public URL.

Ví dụ:

~~~text
Client
  |
  | https://api.example.com/orders
  v
Reverse proxy / API gateway
  |
  | http://orders-service:8080
  v
Spring Boot service
~~~

Proxy có thể gửi các header mô tả request ban đầu:

- Forwarded theo RFC 7239.
- X-Forwarded-Host.
- X-Forwarded-Port.
- X-Forwarded-Proto.
- X-Forwarded-Prefix.
- X-Forwarded-For.

Spring Boot cần được cấu hình để xử lý forwarded headers nếu muốn framework suy ra public URL chính xác.

## 16. Cấu hình server.forward-headers-strategy

Với Spring Boot, property thường dùng là:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

FRAMEWORK sử dụng cơ chế ForwardedHeaderFilter của Spring Framework để xử lý forwarded headers. NATIVE giao cho web server xử lý theo khả năng của server; cần xem tài liệu server đang dùng và header được proxy gửi.

Chọn strategy phù hợp với hạ tầng. Không đồng thời đăng ký filter thủ công và cấu hình strategy theo cách khiến filter bị áp dụng hai lần.

Nếu proxy có prefix public, cần bảo đảm X-Forwarded-Prefix được gửi đúng. Ví dụ public path /orders có thể được chuyển tiếp đến ứng dụng ở root path /.

Sau cấu hình, kiểm tra cả URL của Swagger UI, swagger-config, OpenAPI document và servers trong document. Chỉ thấy trang HTML mở được chưa chứng minh server URL đã đúng.

## 17. Cấu hình X-Forwarded-Prefix

Giả sử gateway nhận:

~~~text
https://api.example.com/orders/v3/api-docs
~~~

nhưng chuyển tiếp đến upstream:

~~~text
http://orders-service:8080/v3/api-docs
~~~

Gateway có thể gửi:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
X-Forwarded-Prefix: /orders
~~~

Khi Spring xử lý forwarded headers đúng cách, URL bên ngoài có thể được phản ánh trong các link được tạo từ request.

Nếu gateway đã giữ prefix trong upstream path thay vì strip, không thêm prefix lần nữa qua X-Forwarded-Prefix. Phải xác định chính xác gateway đã rewrite path như thế nào để tránh URL bị lặp /orders/orders.

## 18. Bảo vệ forwarded headers tại proxy boundary

Forwarded headers ảnh hưởng host và scheme mà ứng dụng tin cậy. Nếu client bên ngoài có thể tự gửi X-Forwarded-Host hoặc X-Forwarded-Proto và proxy chuyển nguyên trạng vào ứng dụng, attacker có thể làm ứng dụng tạo URL sai host hoặc scheme.

Tại trust boundary, proxy nên xóa header forwarded do client gửi và ghi đè bằng giá trị mà proxy xác định từ request thực tế.

Ngoài ra:

- Chỉ cho ứng dụng nhận traffic từ proxy tin cậy nếu có thể.
- Không dùng forwarded host để tạo link public nếu chưa xác thực nguồn.
- Kiểm tra scheme luôn là HTTPS ở môi trường public.
- Không để hostname nội bộ xuất hiện trong spec.
- Kiểm tra redirect, link và server URL trong document sau triển khai.

Forwarded headers là dữ liệu đầu vào của hạ tầng, không phải metadata luôn đáng tin từ browser.

## 19. Dùng ServerBaseUrlCustomizer khi cần điều chỉnh URL sinh tự động

springdoc cung cấp ServerBaseUrlCustomizer để điều chỉnh base URL được suy ra từ request.

Ví dụ một ứng dụng có một public base URL cố định:

~~~java
import org.springdoc.core.customizers.ServerBaseUrlCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class PublicServerUrlConfiguration {

    @Bean
    ServerBaseUrlCustomizer serverBaseUrlCustomizer(
        Environment environment
    ) {
        String publicBaseUrl =
            environment.getRequiredProperty("api.public-base-url");
        return ignoredServerBaseUrl -> publicBaseUrl;
    }
}
~~~

Cấu hình:

~~~yaml
api:
  public-base-url: https://api.example.com/orders
~~~

Customizer này thay URL được suy ra bằng public URL đã cấu hình. Dùng cách này khi service có một base URL public ổn định và không cần suy ra theo từng request.

Nếu có nhiều group hoặc mỗi group có server riêng, customizer toàn service có thể quá rộng. Hãy đặt servers theo group bằng OpenApiCustomizer phù hợp.

Nếu document đã khai báo servers tường minh bằng @OpenAPIDefinition hoặc OpenAPI bean, hãy kiểm tra cách khai báo đó tương tác với quá trình suy ra URL. Không thêm customizer chỉ để sửa một URL vốn đã được cố định chính xác.

## 20. Đặt server riêng cho từng group

Một ứng dụng có thể phục vụ nhiều API group với prefix public khác nhau:

~~~java
import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class GroupServerConfiguration {

    @Bean
    GroupedOpenApi ordersGroup() {
        OpenApiCustomizer serverCustomizer = openApi ->
            openApi.setServers(List.of(
                new Server()
                    .url("/orders")
                    .description("Orders qua gateway")
            ));

        return GroupedOpenApi.builder()
            .group("orders")
            .pathsToMatch("/api/orders/**")
            .addOpenApiCustomizer(serverCustomizer)
            .build();
    }

    @Bean
    GroupedOpenApi catalogGroup() {
        OpenApiCustomizer serverCustomizer = openApi ->
            openApi.setServers(List.of(
                new Server()
                    .url("/catalog")
                    .description("Catalog qua gateway")
            ));

        return GroupedOpenApi.builder()
            .group("catalog")
            .pathsToMatch("/api/catalog/**")
            .addOpenApiCustomizer(serverCustomizer)
            .build();
    }
}
~~~

Mỗi group có server riêng nên consumer gọi đúng prefix public. Hãy tải /v3/api-docs/orders và /v3/api-docs/catalog để kiểm tra server của từng document.

Nếu metadata phải áp dụng cho tất cả group, cân nhắc GlobalOpenApiCustomizer hoặc OpenAPI bean. Nếu chỉ một group có server khác, customizer gắn vào group giúp giới hạn phạm vi thay đổi.

## 21. CORS khi tài liệu nằm ở origin khác

Nếu Swagger UI chạy tại:

~~~text
https://docs.example.com
~~~

nhưng tài liệu service nằm tại:

~~~text
https://orders.example.net/v3/api-docs
~~~

browser xem đây là cross-origin request. CORS cần được cấu hình để docs portal có thể tải OpenAPI JSON. Nếu người dùng bấm Try it out, API endpoint cũng cần cho phép origin của Swagger UI.

Cần kiểm tra CORS cho cả hai luồng:

1. Swagger UI tải document.
2. Swagger UI gửi request thử tới API server.

Ví dụ Spring MVC CORS:

~~~java
@Configuration
class CorsConfiguration {

    @Bean
    WebMvcConfigurer corsConfigurer() {
        return new WebMvcConfigurer() {
            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/**")
                    .allowedOrigins("https://docs.example.com")
                    .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
                    .allowedHeaders("Authorization", "Content-Type", "Accept")
                    .allowCredentials(true);
            }
        };
    }
}
~~~

Nếu dùng Spring Security, CORS phải được bật và phối hợp với security filter chain. Với credentials, không dùng wildcard origin. Chỉ cho phép origin portal thực sự cần truy cập.

Cấu hình CORS phải đặt ở service hoặc gateway nhận request cross-origin. CORS trên portal không tự cho phép browser tải tài liệu từ service khác.

## 22. Authentication cho tài liệu và Try it out

Có thể bảo vệ endpoint tài liệu bằng Spring Security. Khi đó phải quyết định:

- Ai được mở Swagger UI?
- Ai được tải swagger-config?
- Ai được tải OpenAPI document của từng service?
- Ai được dùng Try it out trên API?
- Credential nào được dùng cho mỗi service?

Nếu portal tải spec của orders và catalog, người dùng có thể có quyền đọc orders docs nhưng không có quyền đọc admin docs. Không nên công khai toàn bộ document chỉ vì portal cần hiển thị một số API.

Khi mỗi service có security scheme khác nhau, giữ cấu hình security trong từng OpenAPI document. Swagger UI đọc security scheme theo document đang chọn.

Không đặt client secret production trực tiếp trong swagger-ui.oauth.clientSecret. Đây là thông tin nhạy cảm được đưa vào cấu hình giao diện; dùng Authorization Code với PKCE hoặc cơ chế phù hợp với môi trường và chính sách bảo mật.

## 23. Swagger UI nhiều tài liệu không phải một spec đã hợp nhất

Cấu hình urls chỉ tạo danh sách document để chọn. Khi chọn Orders, Swagger UI tải document Orders; khi chọn Catalog, nó tải document Catalog.

Điều đó không tạo một document có:

~~~yaml
paths:
  /orders:
  /catalog:
components:
  schemas:
~~~

Nếu client generator cần một file chứa tất cả paths, danh sách urls không đáp ứng yêu cầu. Cần một bước merge riêng.

Đây là khác biệt quan trọng khi thiết kế API portal:

| Yêu cầu | Cách làm |
|---|---|
| Một UI chọn từng service | Swagger UI urls |
| Một spec cho từng domain | OpenAPI document riêng theo service/group |
| Một file cho toàn tổ chức | Aggregator hợp nhất document |
| SDK riêng theo service | Sinh SDK từ spec của từng service |
| SDK chung nhiều domain | Hợp nhất có kiểm soát hoặc thiết kế API facade |

## 24. Các vấn đề khi thực sự hợp nhất OpenAPI documents

Khi merge nhiều spec, không thể chỉ nối object paths và components. Cần giải quyết:

- Trùng component schema name, ví dụ Error hoặc PageResponse.
- Trùng security scheme name nhưng định nghĩa khác nhau.
- Trùng operationId.
- Trùng path và HTTP method.
- Khác OpenAPI version.
- Khác server URL.
- Trùng tag nhưng description khác.
- External $ref không còn truy cập được.
- Khác naming convention và response envelope.
- Khác security requirement và OAuth scope.

Ví dụ hai service đều có schema Customer nhưng ý nghĩa khác nhau. Nếu merge không đổi tên, một schema có thể ghi đè schema còn lại hoặc reference trỏ nhầm.

Một aggregator cần parse từng document, tạo namespace cho component, cập nhật tất cả $ref liên quan và kiểm tra lại spec sau merge. Không dùng regex thay tên text vì có thể sửa nhầm description hoặc example.

## 25. Đặt namespace khi merge component

Một quy ước có thể dùng prefix service:

~~~text
Orders_Order
Orders_ApiError
Catalog_Product
Catalog_ApiError
Identity_User
Identity_ApiError
~~~

Khi đổi tên component, phải cập nhật reference:

~~~yaml
$ref: '#/components/schemas/Orders_ApiError'
~~~

Cũng cần xử lý reference trong requestBody, responses, parameters, headers, callbacks, examples, securitySchemes, links và nested schemas.

Nếu aggregator không thể bảo đảm rewrite reference đầy đủ, giữ document tách biệt trong Swagger UI an toàn hơn.

## 26. Xử lý server khi merge document

Mỗi service có thể có server riêng:

~~~yaml
servers:
  - url: https://api.example.com/orders
~~~

và:

~~~yaml
servers:
  - url: https://api.example.com/catalog
~~~

Khi merge, một server list ở root không thể đại diện đúng cho mọi path nếu từng service có base path khác nhau. Có thể đặt servers ở cấp Path Item hoặc Operation nếu cần biểu diễn server riêng theo nhóm path.

Một lựa chọn khác là chuẩn hóa paths để chứa prefix service và dùng một root server chung:

~~~yaml
servers:
  - url: https://api.example.com
paths:
  /orders/api/orders:
    get:
      responses:
        "200":
          description: Thành công
  /catalog/api/products:
    get:
      responses:
        "200":
          description: Thành công
~~~

Chỉ làm vậy khi aggregator có quy tắc path rõ ràng và mọi $ref vẫn hợp lệ. Đừng vừa thêm prefix vào path vừa giữ prefix trong server URL, vì request cuối cùng sẽ lặp prefix.

## 27. Dùng external OpenAPI files trong portal

Nếu service phát hành spec tĩnh thay vì cung cấp endpoint động, Swagger UI có thể tải file qua URL.

Ví dụ một file tĩnh nằm trong static resources của portal:

~~~text
src/main/resources/static/openapi/orders.json
src/main/resources/static/openapi/catalog.yaml
~~~

Cấu hình một document:

~~~yaml
springdoc:
  swagger-ui:
    url: /openapi/orders.json
~~~

Cấu hình nhiều document:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Orders
        url: /openapi/orders.json
      - name: Catalog
        url: /openapi/catalog.yaml
~~~

Các file phải là OpenAPI document hợp lệ và được phân phối cùng ứng dụng. Nếu tài liệu được phát hành theo version, có thể dùng path bất biến như /openapi/orders/2.1.0/openapi.json.

Không ghi đè file của release cũ nếu consumer cần tái lập SDK hoặc audit contract.

## 28. Quản lý version và URL tài liệu

Trong hệ thống nhiều service, mỗi service có thể release độc lập. Hãy xác định quy ước URL tài liệu:

~~~text
/orders/v3/api-docs
/catalog/v3/api-docs
/identity/v3/api-docs
~~~

Đây là URL tài liệu hiện tại của mỗi service. Nếu cần tài liệu bất biến theo release, có thể phân phối artifact theo version:

~~~text
/openapi/orders/2.1.0/openapi.json
/openapi/catalog/4.0.0/openapi.json
/openapi/identity/1.8.2/openapi.json
~~~

Phân biệt API version trong info.version với OpenAPI specification version trong trường openapi. Không dùng springdoc library version làm API version.

Portal có thể hiển thị tài liệu hiện tại và liên kết tới release archive. Khi service thay đổi contract, CI nên tạo artifact mới, validate và lưu theo version.

## 29. Kiểm tra swagger-config và danh sách URLs

Có thể tải cấu hình Swagger UI:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/swagger-config
~~~

Xác minh response có danh sách urls và URL/name đúng:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/swagger-config \
  | jq '.urls'
~~~

Kiểm tra từng document:

~~~bash
curl -fsS http://localhost:8080/orders/v3/api-docs -o orders.json
curl -fsS http://localhost:8080/catalog/v3/api-docs -o catalog.json
~~~

Kiểm tra version và server:

~~~bash
jq '{openapi, info, servers}' orders.json
jq '{openapi, info, servers}' catalog.json
~~~

Nếu portal chạy qua gateway, chạy các lệnh với public gateway URL để kiểm tra đúng trải nghiệm của browser. Kiểm tra localhost nội bộ không chứng minh public route hoạt động.

## 30. Kiểm thử GroupedOpenApi trong ứng dụng

Có thể dùng WebTestClient kiểm tra endpoint group:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ApiDocumentationGroupsTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void exposesOrdersDocument() {
        webTestClient.get()
            .uri("/v3/api-docs/orders")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.openapi").exists()
            .jsonPath("$.paths['/api/orders']").exists();
    }
}
~~~

Test thêm group catalog và xác minh không lẫn path của orders. Nếu group có custom server, kiểm tra servers[0].url đúng public prefix.

Đối với portal multi-service, test swagger-config và test tải từng spec. Có thể dùng WebTestClient khi các route nằm trong cùng hệ thống test hoặc dùng HTTP integration test qua gateway.

## 31. Kiểm thử URL qua reverse proxy

Một bài kiểm thử triển khai nên gửi request qua đúng gateway public path:

~~~bash
curl -fsS https://api.example.com/orders/v3/api-docs -o orders.json
~~~

Trong môi trường thực, gateway tự ghi đè Forwarded và X-Forwarded-* headers. Không dùng lệnh từ browser hoặc client để tự giả mạo các header này rồi coi đó là bằng chứng cấu hình proxy đúng.

Kiểm tra document trả về:

- servers không chứa hostname nội bộ.
- Scheme là HTTPS nếu public endpoint dùng HTTPS.
- Prefix service không bị mất hoặc lặp.
- Path operation không bị thêm prefix hai lần.
- Swagger UI document URL vẫn tải được.
- Try it out gọi đúng public endpoint.

Nếu dùng explicit servers, kiểm tra chúng có đúng với gateway path và không bị forwarded prefix thêm lần nữa.

## 32. Kiểm tra Swagger UI bằng browser

Sau khi mở portal:

1. Xác nhận trang Swagger UI tải thành công.
2. Mở bộ chọn document.
3. Chọn từng service.
4. Xác minh title, version và tags đúng service.
5. Kiểm tra schema, request body và response.
6. Xem network request tải OpenAPI JSON.
7. Thử một operation an toàn trong môi trường test.
8. Xác minh request đi qua gateway public URL.
9. Kiểm tra authentication và CORS.
10. Kiểm tra browser console khi có lỗi.

Trang UI có thể mở thành công trong khi một hoặc nhiều spec URL trả 401, 404 hoặc CORS error. Vì vậy, cần kiểm tra từng tài liệu trong danh sách.

## 33. Tắt Swagger UI hoặc API docs ở service không cần public

Một số service chỉ cần xuất spec cho pipeline nội bộ, không cần cung cấp Swagger UI public.

Có thể tắt UI:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
~~~

Có thể tắt API docs endpoint:

~~~yaml
springdoc:
  api-docs:
    enabled: false
~~~

Nếu tắt API docs ở service, portal không thể tải document từ endpoint đó. Khi đó, cần phân phối spec tĩnh hoặc build artifact từ CI rồi cung cấp cho portal.

Một service có thể bật API docs trong profile nội bộ và tắt trong production nếu chính sách yêu cầu. Hãy bảo đảm profile CI có thể export contract trước khi endpoint bị tắt.

## 34. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI chỉ hiện một service | Dùng url thay vì urls hoặc swagger-config không chứa danh sách |
| Bộ chọn có tên nhưng tài liệu không tải | URL sai, service không reachable hoặc authentication chặn |
| Tải document được nhưng Try it out lỗi | servers trỏ sai host/prefix hoặc CORS API chưa cấu hình |
| URL có hostname container | Forwarded headers chưa được xử lý hoặc servers chưa khai báo public |
| URL bị lặp prefix /orders/orders | Gateway strip prefix và app/proxy cùng thêm prefix |
| URL mất prefix gateway | Thiếu X-Forwarded-Prefix hoặc server URL không khai báo prefix |
| Scheme là HTTP trong khi public dùng HTTPS | X-Forwarded-Proto không được xử lý |
| Browser báo CORS khi tải spec | Origin portal chưa được phép trên docs endpoint |
| Browser báo CORS khi gọi API | API endpoint chưa cho phép origin portal |
| Một group chứa path của group khác | pathsToMatch/pathsToExclude giao nhau ngoài ý muốn |
| Custom server chỉ xuất hiện ở document mặc định | Customizer chưa được gắn vào group phù hợp |
| Merged spec mất schema | Component name collision hoặc $ref chưa được rewrite |
| Security scheme bị ghi đè | Trùng tên scheme nhưng định nghĩa khác |
| Client generator gọi sai URL | Server URL và operation path ghép thành route sai |
| Swagger UI không lấy config | configUrl sai hoặc security chặn swagger-config |

## 35. Quy trình triển khai portal nhiều service

Một quy trình có thể áp dụng:

1. Xác định service nào được công bố trong portal.
2. Chọn public route cho OpenAPI document của từng service.
3. Cấu hình gateway route và rewrite path.
4. Cấu hình server URL trong từng document.
5. Bật forwarded-header strategy nếu cần suy ra URL từ request.
6. Cấu hình springdoc.swagger-ui.urls.
7. Chọn urls-primary-name.
8. Bảo đảm docs endpoint có authentication/CORS phù hợp.
9. Tải swagger-config và từng OpenAPI document.
10. Kiểm tra servers, paths, security và schema.
11. Kiểm thử Try it out qua gateway.
12. Lưu contract artifact theo service/version.
13. Theo dõi lỗi tải tài liệu sau mỗi lần deploy.

Nếu cần một document hợp nhất, thêm bước aggregation riêng và validate mọi reference sau khi merge. Không coi Swagger UI multi-URL là bước merge.

## 36. Checklist trước khi phát hành

- [ ] Đã xác định cần GroupedOpenApi, multi-service UI hay merged spec.
- [ ] Tên group trong cùng service là duy nhất và có ý nghĩa.
- [ ] Mỗi service có OpenAPI endpoint public hoặc artifact tĩnh.
- [ ] Danh sách springdoc.swagger-ui.urls có tên và URL duy nhất.
- [ ] urls-primary-name trỏ tới document phù hợp.
- [ ] swagger-config trả đúng danh sách URL.
- [ ] Gateway route đến từng service hoạt động.
- [ ] Server URL phản ánh public hostname và prefix.
- [ ] Không có hostname nội bộ hoặc port container trong spec public.
- [ ] Forwarded headers được proxy ghi đè từ nguồn tin cậy.
- [ ] X-Forwarded-Prefix không bị mất hoặc áp dụng hai lần.
- [ ] server.forward-headers-strategy phù hợp với web server.
- [ ] CORS cho phép portal tải spec và gọi API khi cross-origin.
- [ ] Authentication cho UI, docs endpoint và Try it out được kiểm tra.
- [ ] Group-specific customizer đặt server đúng document.
- [ ] Merged spec xử lý component collision và mọi $ref.
- [ ] OpenAPI artifacts được version hóa và lưu bất biến.
- [ ] Browser smoke test đã chọn và tải từng service document.
- [ ] Try it out gọi đúng route public.
- [ ] CI kiểm tra swagger-config và từng OpenAPI document.

## 37. Nguồn tra cứu

- [springdoc-openapi – Configuration Properties](https://springdoc.org/properties.html)
- [springdoc-openapi FAQ – Aggregating external OpenAPI endpoints](https://springdoc.org/faq.html)
- [springdoc-openapi FAQ – Reverse proxy and forwarded headers](https://springdoc.org/faq.html)
- [springdoc-openapi FAQ – GroupedOpenApi and customizers](https://springdoc.org/faq.html)
- [Spring Boot – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Framework – ForwardedHeaderFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html)
- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)

Tổng hợp tài liệu nhiều service cần tách rõ nhóm document, danh sách tài liệu trong Swagger UI và một spec được hợp nhất thực sự. Dùng GroupedOpenApi cho nhiều nhóm trong cùng service; dùng springdoc.swagger-ui.urls để portal chọn document từ nhiều service; chỉ xây dựng aggregator khi consumer cần một OpenAPI file duy nhất. Với URL máy chủ, hãy công bố public host/prefix, xử lý forwarded headers đúng trust boundary, kiểm tra CORS và xác minh Try it out qua gateway trước khi phát hành.
