# Sai URL máy chủ sau proxy hoặc khi dùng management port

Khi mở Swagger UI, trang HTML có thể tải thành công nhưng nút Try it out lại gọi nhầm host, scheme, port hoặc path. Một tình huống thường gặp là OpenAPI document chứa URL nội bộ như http://orders-service:8080, trong khi client bên ngoài phải gọi https://api.example.com/orders. Tình huống khác xảy ra khi Swagger UI và OpenAPI endpoint được chuyển sang Actuator management port, khiến servers trong document vô tình trỏ tới cổng quản trị thay vì cổng API nghiệp vụ.

Để chẩn đoán, cần tách ba URL:

1. **URL của Swagger UI:** browser mở trang giao diện.
2. **URL của OpenAPI document:** Swagger UI tải JSON/YAML.
3. **URL trong servers:** Swagger UI hoặc client generator dùng để gọi các operation.

Ba URL này có thể nằm trên các host, port và path khác nhau. Chỉ sửa URL trang Swagger UI không bảo đảm request API được gửi đúng.

Bài này hướng dẫn cách đọc URL được sinh, xử lý forwarded headers sau reverse proxy, cấu hình server URL, chẩn đoán management port, bật CORS đúng chỗ và kiểm tra đường đi từ browser tới API.

## 1. Phân biệt ba URL trong luồng Swagger UI

Ví dụ một service có:

~~~text
Swagger UI:
https://docs.example.com/orders/swagger-ui.html

OpenAPI document:
https://docs.example.com/orders/v3/api-docs

API server:
https://api.example.com/orders
~~~

Swagger UI tải document từ URL thứ hai. Sau đó, nó đọc servers trong document để tạo URL gọi operation.

Nếu document có:

~~~yaml
servers:
  - url: http://orders-service:8080
paths:
  /api/orders:
    get:
      responses:
        "200":
          description: Thành công
~~~

Try it out sẽ gọi:

~~~text
http://orders-service:8080/api/orders
~~~

Đây là hostname nội bộ, browser bên ngoài không truy cập được. URL document có thể đúng nhưng servers vẫn sai.

Khi điều tra, hãy kiểm tra riêng:

- Trang HTML có tải không?
- Swagger UI có tải được swagger-config và OpenAPI JSON không?
- Giá trị servers trong JSON là gì?
- URL cuối cùng của Try it out được ghép ra sao?

## 2. Hiểu cách springdoc tạo servers

Khi document không khai báo servers tường minh, springdoc có thể suy ra base URL từ request dùng để tải OpenAPI document. Host, port, scheme và context path của request có thể ảnh hưởng URL được tạo.

Điều này hoạt động tốt khi ứng dụng được truy cập trực tiếp. Sau reverse proxy, request mà Spring Boot nhìn thấy có thể khác request public mà browser gửi.

Ví dụ:

~~~text
Public request:
https://api.example.com/orders/v3/api-docs

Request tới upstream:
http://orders-service:8080/v3/api-docs
~~~

Nếu ứng dụng chỉ nhìn thấy request upstream, server URL được suy ra có thể dùng http, hostname orders-service và port 8080.

Theo FAQ của springdoc, nếu server annotations được khai báo thì các server đó được sử dụng thay cho URL tự động được suy ra. Đây là lựa chọn hữu ích khi public URL ổn định và đã biết.

## 3. Đọc servers trong OpenAPI JSON trước khi sửa cấu hình

Bắt đầu bằng cách tải document:

~~~bash
curl -fsS https://api.example.com/orders/v3/api-docs -o openapi.json
~~~

Xem servers:

~~~bash
jq '.servers' openapi.json
~~~

Xem path:

~~~bash
jq '.paths | keys' openapi.json
~~~

Xem version và metadata:

~~~bash
jq '{openapi, info, servers}' openapi.json
~~~

Nếu servers có hostname nội bộ, scheme sai hoặc port không đúng, hãy tập trung vào cách tạo server URL. Nếu servers đúng nhưng Try it out vẫn gọi sai, kiểm tra path của operation, server override ở Path Item/Operation và cấu hình Swagger UI.

Không suy luận URL từ thanh địa chỉ của Swagger UI. URL gọi API được xác định bởi servers kết hợp với path operation.

## 4. Phân biệt application port và management port

Spring Boot có thể chạy hai cổng:

- server.port: cổng nhận request API nghiệp vụ.
- management.server.port: cổng dành cho Actuator management endpoints.

Ví dụ:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /actuator
~~~

API nghiệp vụ vẫn ở cổng 8080. Actuator endpoints nằm dưới cổng 9090 và base path /actuator.

Nếu Swagger UI được expose trên management port, điều đó không có nghĩa API nghiệp vụ cũng chuyển sang cổng 9090. Servers trong OpenAPI phải trỏ tới cổng hoặc public route của API nghiệp vụ.

Đây là điểm quan trọng nhất khi điều tra lỗi Try it out sau khi bật use-management-port.

## 5. Bật springdoc trên Actuator management port

Để expose OpenAPI và Swagger UI trên management port, cấu hình:

~~~yaml
springdoc:
  use-management-port: true

management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include:
          - openapi
          - swagger-ui
~~~

Với base path mặc định /actuator, các endpoint được expose dưới management port:

~~~text
http://localhost:9090/actuator/openapi
http://localhost:9090/actuator/swagger-ui
~~~

management port phải khác application port để dùng tính năng này.

Nếu management.endpoints.web.base-path được đổi, các endpoint tài liệu sẽ nằm dưới base path mới. Ví dụ base path /manage sẽ làm endpoint thành /manage/openapi và /manage/swagger-ui.

Các endpoint này là Actuator endpoints, không phải đường dẫn /v3/api-docs và /swagger-ui.html mặc định trên application port.

## 6. Những springdoc path properties không còn áp dụng

Khi springdoc.use-management-port=true, các path properties thông thường của springdoc không áp dụng cho các endpoint được expose dưới management base path.

Ví dụ, không nên mong springdoc.api-docs.path hoặc springdoc.swagger-ui.path đổi tên các endpoint Actuator openapi và swagger-ui.

Tên endpoint dưới Actuator base path được springdoc quản lý. Hãy dùng management.endpoints.web.base-path để thay đổi base path Actuator, đồng thời kiểm tra đúng URL sau deploy.

Nếu muốn tiếp tục dùng /v3/api-docs và /swagger-ui.html trên application port, không bật use-management-port. Chọn một nơi expose tài liệu theo mục tiêu vận hành.

## 7. Phân biệt use-management-port với show-actuator

Hai property giải quyết hai nhu cầu khác nhau:

| Property | Tác dụng |
|---|---|
| springdoc.use-management-port | Expose OpenAPI và UI dưới Actuator management port |
| springdoc.show-actuator | Thêm các Actuator endpoints vào OpenAPI documentation |

Bật show-actuator không tự chuyển Swagger UI sang management port. Nếu chỉ bật show-actuator, UI có thể vẫn nằm trên application port.

Nếu management port khác application port và muốn UI gọi các Actuator endpoint ở cổng quản trị, CORS cho Actuator endpoints cũng có thể cần được cấu hình.

Đừng bật cả hai chỉ vì muốn nhìn thấy Actuator. Xác định rõ có cần di chuyển UI/document endpoint sang management port hay chỉ cần mô tả Actuator operations.

## 8. Vì sao Try it out gọi nhầm management port?

Giả sử:

~~~text
Application API:
http://localhost:8080/api/orders

Management docs:
http://localhost:9090/actuator/openapi

Management Swagger UI:
http://localhost:9090/actuator/swagger-ui
~~~

Browser tải Swagger UI và OpenAPI document từ cổng 9090. Nếu servers được suy ra từ request lấy document, URL được sinh có thể là http://localhost:9090.

Khi đó Try it out gọi:

~~~text
http://localhost:9090/api/orders
~~~

Nhưng API thực tế ở cổng 8080. Request sẽ trả 404, 401 hoặc không có route.

Cách sửa là khai báo servers trỏ tới application API URL:

~~~yaml
servers:
  - url: http://localhost:8080
    description: Application API
~~~

Trong production, dùng public URL hoặc gateway route tương ứng. Không dùng management port làm server cho API nghiệp vụ trừ khi API thực sự được phục vụ ở cổng đó.

## 9. Khai báo servers tường minh bằng @OpenAPIDefinition

Nếu API có public base URL ổn định, có thể khai báo:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://api.example.com/orders",
            description = "Public Orders API"
        )
    }
)
class OpenApiConfiguration {
}
~~~

Cách này tránh việc server URL bị suy ra từ request tải document trên management port hoặc từ địa chỉ upstream.

Nếu có nhiều môi trường, nên lấy server URL từ cấu hình deployment hoặc dùng OpenAPI bean/customizer. Không hard-code production URL vào source nếu cùng artifact phải chạy ở nhiều môi trường.

## 10. Khai báo servers bằng OpenAPI bean

Có thể đọc URL từ Environment:

~~~yaml
api:
  public-base-url: https://api.example.com/orders
~~~

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

import java.util.List;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI openAPI(Environment environment) {
        String publicBaseUrl =
            environment.getRequiredProperty("api.public-base-url");

        return new OpenAPI()
            .servers(List.of(
                new Server()
                    .url(publicBaseUrl)
                    .description("Public API")
            ));
    }
}
~~~

OpenAPI bean phù hợp khi metadata servers dùng chung cho document trong ứng dụng. Nếu nhiều group có public prefix khác nhau, dùng customizer riêng cho group hoặc thiết kế bean phù hợp với từng document.

Sau khi cấu hình, tải JSON và xác nhận servers thực sự có giá trị mong muốn. Không chỉ kiểm tra bean đã được tạo.

## 11. Dùng ServerBaseUrlCustomizer khi cần chỉnh URL tự động

springdoc cung cấp ServerBaseUrlCustomizer để điều chỉnh base URL được suy ra từ request.

Ví dụ:

~~~java
import org.springdoc.core.customizers.ServerBaseUrlCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class PublicBaseUrlConfiguration {

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

Cấu hình này phù hợp khi một ứng dụng có một public base URL ổn định. Nếu URL phải khác nhau theo group hoặc request, cần thiết kế logic riêng và kiểm thử từng trường hợp.

ServerBaseUrlCustomizer điều chỉnh URL tự động được suy ra. Nếu document đã khai báo servers tường minh bằng annotation hoặc model, hãy kiểm tra cách cấu hình đó được áp dụng trước khi thêm customizer.

## 12. Kiểm tra Forwarded và X-Forwarded headers

Reverse proxy có thể chuyển tiếp request tới Spring Boot với host, port và scheme nội bộ. Để framework nhận biết request public, proxy có thể gửi:

- Forwarded theo RFC 7239.
- X-Forwarded-Host.
- X-Forwarded-Port.
- X-Forwarded-Proto.
- X-Forwarded-Prefix.
- X-Forwarded-For.

Ví dụ public request:

~~~text
https://api.example.com/orders/v3/api-docs
~~~

Proxy chuyển tới:

~~~text
http://orders-service:8080/v3/api-docs
~~~

Các header forwarded có thể thông báo cho ứng dụng rằng request gốc dùng HTTPS, host api.example.com và prefix /orders.

Nếu ứng dụng không xử lý các header này, server URL tự động có thể phản ánh địa chỉ nội bộ.

## 13. Cấu hình server.forward-headers-strategy

Spring Boot cung cấp property:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Các lựa chọn chính:

| Giá trị | Cách hoạt động |
|---|---|
| NONE | Không áp dụng xử lý forwarded headers |
| NATIVE | Để web server xử lý theo khả năng native |
| FRAMEWORK | Dùng ForwardedHeaderFilter của Spring Framework |

Nếu proxy gửi các header phổ biến như X-Forwarded-For và X-Forwarded-Proto, NATIVE có thể đủ tùy web server. Nếu cần xử lý thêm header như X-Forwarded-Prefix hoặc native behavior không đáp ứng, FRAMEWORK là lựa chọn cần xem xét.

Kiểm tra tài liệu của embedded server và Spring Boot version đang dùng. Không giả định mọi server xử lý tất cả header giống nhau.

## 14. Xử lý X-Forwarded-Prefix

X-Forwarded-Prefix quan trọng khi gateway thêm prefix public nhưng strip prefix trước khi gửi request tới upstream.

Ví dụ:

~~~text
Public:
https://api.example.com/orders/v3/api-docs

Upstream:
http://orders-service:8080/v3/api-docs
~~~

Gateway có thể gửi:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
X-Forwarded-Prefix: /orders
~~~

Khi Spring xử lý header này, framework có thể tạo URL chứa prefix public.

Nếu thiếu X-Forwarded-Prefix, document có thể chứa server URL không có /orders. Khi đó Try it out gọi route không tồn tại ở gateway.

Nếu gateway không strip prefix mà chuyển tiếp nguyên path /orders/..., không thêm lại prefix một lần nữa. Xác định chính xác route rewrite để tránh URL bị lặp.

## 15. Reverse proxy phải ghi đè forwarded headers

Không tin forwarded headers do browser hoặc client gửi trực tiếp.

Nếu proxy giữ nguyên X-Forwarded-Host từ client, người dùng có thể làm ứng dụng tạo URL theo host tùy ý. Điều này có thể gây link sai hoặc làm lộ thông tin không mong muốn.

Tại proxy boundary:

1. Xóa các forwarded headers do client gửi.
2. Tạo lại Forwarded hoặc X-Forwarded-* từ request thực tế.
3. Chỉ cho phép upstream nhận traffic từ proxy tin cậy.
4. Bảo đảm scheme public được xác định đúng.
5. Không cho phép client trực tiếp truy cập upstream nếu không cần thiết.

Forwarded headers chỉ đáng tin khi được proxy tin cậy tạo và bảo vệ.

## 16. Phân biệt context path và proxy prefix

Có hai loại prefix thường bị nhầm:

- server.servlet.context-path: context path thực sự của ứng dụng Spring Boot.
- X-Forwarded-Prefix: prefix public do proxy thêm hoặc đại diện.

Ví dụ ứng dụng có context path /app, còn gateway public prefix /orders. URL public có thể chứa cả hai tùy cách gateway rewrite:

~~~text
https://api.example.com/orders/app/v3/api-docs
~~~

Nếu gateway strip /orders nhưng upstream vẫn phục vụ dưới /app, Spring phải hiểu đúng context path và forwarded prefix.

Không khai báo cùng một prefix ở context path, proxy route và OpenAPI servers mà không tính cách chúng được ghép. Nếu prefix xuất hiện hai lần trong URL cuối cùng, hãy kiểm tra từng lớp thay vì sửa ngẫu nhiên servers.

## 17. Tắt cache khi URL phải được tính theo từng request

springdoc mặc định tính OpenAPI description rồi cache kết quả. Điều này có thể gây vấn đề nếu cùng một ứng dụng được truy cập qua nhiều proxy hoặc host khác nhau và server URL phải thay đổi theo request.

Có thể tắt cache:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Hoặc:

~~~properties
springdoc.cache.disabled=true
~~~

Tắt cache khiến document được tính lại theo request, phù hợp khi URL thực sự phụ thuộc host hoặc forwarded headers của từng request.

Nếu servers đã được khai báo tường minh và ổn định, thường không cần tắt cache chỉ để sửa URL. Tắt cache không thay thế cấu hình proxy đúng và có thể làm tăng chi phí tạo document.

Nếu dùng cache bật, hãy nhớ rằng document đã tính toán có thể được tái sử dụng. Đừng mong mỗi request khác host sẽ tự sinh một servers khác nhau khi cache đang giữ kết quả cũ.

## 18. CORS khi Swagger UI và API nằm trên hai port

Origin của browser bao gồm scheme, host và port. Vì vậy:

~~~text
http://localhost:9090
http://localhost:8080
~~~

là hai origin khác nhau.

Khi Swagger UI chạy trên management port 9090 nhưng Try it out gọi application API ở port 8080, browser cần CORS cho phép origin của UI truy cập API.

Cấu hình CORS ở application API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class ApiCorsConfiguration {

    @Bean
    WebMvcConfigurer corsConfigurer() {
        return new WebMvcConfigurer() {
            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/api/**")
                    .allowedOrigins("https://docs.example.com")
                    .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
                    .allowedHeaders("Authorization", "Content-Type", "Accept")
                    .allowCredentials(true);
            }
        };
    }
}
~~~

Nếu dùng Spring Security, bật và cấu hình CORS trong security filter chain. Chỉ cho phép origin cần thiết; không dùng wildcard khi gửi credentials.

CORS của management endpoint và CORS của application API là hai phạm vi riêng. Swagger UI có thể tải document thành công nhưng vẫn bị browser chặn khi gọi API.

Nếu portal ở origin khác cần tải OpenAPI document từ Actuator management endpoint, có thể cấu hình CORS cho Actuator:

~~~yaml
management:
  endpoints:
    web:
      cors:
        allowed-origins: https://docs.example.com
        allowed-methods: GET,OPTIONS
        allowed-headers: Authorization,Content-Type,Accept
~~~

Khi Swagger UI và OpenAPI endpoint cùng được phục vụ từ management port và cùng origin, browser không cần CORS cho hai request nội bộ đó. CORS vẫn có thể cần cho Try it out gọi application API ở port khác.

## 19. Bảo vệ management port

Management port thường chứa health, metrics, environment và các endpoint vận hành. Nếu bật springdoc.use-management-port, OpenAPI document và Swagger UI cũng xuất hiện trên cổng này.

Không vì muốn có tài liệu API mà mở toàn bộ management port ra Internet.

Hãy kiểm tra:

- management.server.address có bind vào interface phù hợp không.
- Firewall hoặc network policy chỉ cho phép mạng quản trị.
- Spring Security bảo vệ Actuator endpoints.
- management.endpoints.web.exposure.include chỉ chứa endpoint cần thiết.
- Swagger UI có cần public access hay chỉ dành cho developer nội bộ.
- OpenAPI document có chứa operation nội bộ hoặc thông tin nhạy cảm không.

Exposure trong Actuator chỉ làm endpoint có thể được expose; nó không thay thế authorization và network controls.

## 20. Cấu hình management port hoàn chỉnh

Ví dụ application API chạy ở 8080 và tài liệu quản trị chạy ở 9090:

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework

management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include:
          - health
          - info
          - openapi
          - swagger-ui

springdoc:
  use-management-port: true

api:
  public-base-url: https://api.example.com/orders
~~~

OpenAPI và UI được expose dưới management base path:

~~~text
http://localhost:9090/actuator/openapi
http://localhost:9090/actuator/swagger-ui
~~~

Servers trong OpenAPI cần dùng application API public URL:

~~~yaml
servers:
  - url: https://api.example.com/orders
~~~

Không để servers dùng http://localhost:9090 hoặc /actuator. Đó là nơi phục vụ tài liệu, không phải nơi phục vụ operation nghiệp vụ.

## 21. CORS khi management port khác application port

Nếu Swagger UI được phục vụ ở management port và API ở application port, browser gọi API qua một origin khác. Cần bật CORS cho application endpoints.

Nếu portal bên ngoài và management port cũng khác origin, cần CORS cho cả đường tải document và đường gọi API.

Có thể giảm độ phức tạp bằng cách đặt một reverse proxy public cùng origin cho UI, docs và API. Gateway có thể route /docs và /actuator/openapi tới management service, còn /orders/** tới application service.

Dù chọn cách nào, servers phải trỏ tới route API public, không trỏ vào route management.

## 22. Khi nào dùng show-actuator?

Nếu mục tiêu là đưa Actuator operations vào tài liệu API, dùng:

~~~yaml
springdoc:
  show-actuator: true
~~~

Property này thêm group cho Actuator endpoints vào OpenAPI. Nó không đồng nghĩa Swagger UI sẽ chuyển sang management port.

Nếu management port khác application port và muốn gọi Actuator operations từ UI, cần kiểm tra CORS cho Actuator endpoints. Nếu muốn cả UI và OpenAPI endpoint được expose dưới management base path, dùng use-management-port theo cấu hình Actuator.

## 23. Kiểm tra URL sau khi bật management port

Dùng curl kiểm tra endpoint tài liệu:

~~~bash
curl -i http://localhost:9090/actuator/openapi
~~~

Kiểm tra servers:

~~~bash
curl -fsS http://localhost:9090/actuator/openapi \
  | jq '.servers'
~~~

Kiểm tra path operation:

~~~bash
curl -fsS http://localhost:9090/actuator/openapi \
  | jq '.paths | keys'
~~~

Nếu servers chứa port 9090 hoặc /actuator, hãy cấu hình server URL cho application API.

Kiểm tra Swagger UI:

~~~bash
curl -I http://localhost:9090/actuator/swagger-ui
~~~

Nếu endpoint tài liệu hoạt động nhưng UI không tải được API spec, kiểm tra browser network và URL được cấu hình trong Swagger UI.

## 24. Kiểm tra URL qua reverse proxy

Luôn kiểm tra từ public URL mà người dùng thực sự truy cập:

~~~bash
curl -fsS https://api.example.com/orders/v3/api-docs -o openapi.json
~~~

Sau đó:

~~~bash
jq '.servers' openapi.json
~~~

Nếu document được expose qua management route:

~~~bash
curl -fsS https://ops.example.com/orders/actuator/openapi -o openapi.json
~~~

Dù document tải từ ops.example.com, servers vẫn có thể trỏ tới https://api.example.com/orders.

Không dùng hostname upstream trong kiểm thử public. Kiểm tra trực tiếp container chỉ giúp chẩn đoán một lớp; nó không xác nhận proxy đã tạo đúng URL.

## 25. Dùng OpenApiCustomizer cho server riêng của group

Nếu ứng dụng có nhiều group với public prefix khác nhau:

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
    GroupedOpenApi ordersApi() {
        OpenApiCustomizer serverCustomizer = openApi ->
            openApi.setServers(List.of(
                new Server()
                    .url("https://api.example.com/orders")
                    .description("Orders public API")
            ));

        return GroupedOpenApi.builder()
            .group("orders")
            .pathsToMatch("/api/orders/**")
            .addOpenApiCustomizer(serverCustomizer)
            .build();
    }
}
~~~

Customizer gắn với group giúp server URL chỉ áp dụng cho document đó. Nếu mọi group đều dùng cùng server, có thể dùng OpenAPI bean hoặc GlobalOpenApiCustomizer.

Kiểm tra từng endpoint group sau khi cấu hình. Không giả định customizer cho document mặc định tự áp dụng cho mọi group.

## 26. Chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
|---|---|---|
| servers dùng hostname container | Proxy headers không được xử lý | X-Forwarded-Host và Forwarded |
| servers dùng HTTP thay vì HTTPS | Scheme public không được chuyển tiếp | X-Forwarded-Proto |
| servers thiếu prefix gateway | Proxy strip prefix nhưng không gửi prefix | X-Forwarded-Prefix |
| servers có prefix lặp hai lần | Context path và forwarded prefix cùng thêm | So sánh public path với upstream path |
| Try it out gọi management port | Document sinh servers từ request management | Kiểm tra servers và khai báo app API URL |
| OpenAPI endpoint 404 trên management port | Chưa expose Actuator endpoint | management.endpoints.web.exposure.include |
| Swagger UI 404 khi use-management-port | Dùng nhầm /swagger-ui.html | Dùng /actuator/swagger-ui |
| Đổi springdoc.swagger-ui.path không tác dụng | Đang dùng management port | Kiểm tra quy tắc use-management-port |
| UI tải spec nhưng API call bị CORS | UI và API khác origin | CORS trên application API |
| URL thay đổi theo proxy nhưng document giữ URL cũ | Cache giữ kết quả trước đó | Kiểm tra springdoc.cache.disabled |
| UI tải được nhưng API 401 | Security policy của API | Authentication và token |
| URL đúng nhưng path sai | Server URL và operation path ghép sai | Kiểm tra servers cùng paths |

## 27. Quy trình điều tra từng bước

Khi nhận lỗi URL sai, thực hiện theo thứ tự:

1. Ghi lại URL browser dùng để mở Swagger UI.
2. Xác định URL thực tế của OpenAPI document.
3. Tải document và đọc servers.
4. Ghép servers với path operation để tính URL cuối.
5. Xác định request đi qua proxy nào và proxy có strip prefix không.
6. Kiểm tra Forwarded và X-Forwarded-* headers tại upstream.
7. Kiểm tra server.forward-headers-strategy.
8. Xác định UI/document có chạy trên management port không.
9. Nếu dùng management port, kiểm tra servers có trỏ tới application API không.
10. Kiểm tra CORS và security.
11. Tắt cache tạm thời chỉ khi URL cần tính theo request.
12. Kiểm tra lại qua public gateway URL.

Thực hiện từng bước giúp xác định URL sai ở lớp nào. Không thay đồng thời proxy, server annotation, context path và cache trước khi có bằng chứng.

## 28. Kiểm tra trong integration test

Có thể kiểm tra servers của OpenAPI document bằng WebTestClient:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OpenApiServerUrlTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publishesPublicApiServerUrl() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.servers[0].url")
            .isEqualTo("https://api.example.com/orders");
    }
}
~~~

Nếu dùng use-management-port, test endpoint theo management context/port và xác minh servers vẫn trỏ tới application API. Cách khởi tạo test phụ thuộc cấu hình Actuator và management port của project.

Test thêm path và operation để chắc chắn URL cuối không bị lặp prefix. Unit test customizer không thay thế kiểm thử qua reverse proxy thật.

## 29. Kiểm tra sau deploy

Sau mỗi lần thay đổi ingress, gateway, context path hoặc management port:

- Tải Swagger UI qua public route.
- Tải swagger-config nếu UI sử dụng config endpoint.
- Tải OpenAPI JSON.
- Kiểm tra servers.
- Kiểm tra scheme, host, port và prefix.
- Thử operation read-only an toàn.
- Xác nhận browser không báo CORS.
- Xác nhận management endpoint không bị public ngoài ý muốn.

Nên tự động hóa các kiểm tra này trong smoke test deployment. Proxy configuration có thể thay đổi độc lập với code Spring Boot và làm URL tài liệu sai dù ứng dụng không đổi.

## 30. Những lỗi thường gặp

| Lỗi cấu hình | Hậu quả |
|---|---|
| Không xử lý forwarded headers | URL chứa host/port nội bộ |
| Proxy không gửi X-Forwarded-Prefix | Mất public path prefix |
| Proxy không ghi đè forwarded headers | Có thể tin host/scheme do client giả mạo |
| Dùng management port làm servers | Try it out gọi nhầm cổng |
| Bật use-management-port nhưng vẫn dùng /v3/api-docs | Endpoint tài liệu trả 404 |
| Quên expose openapi và swagger-ui trong Actuator | Endpoint không xuất hiện |
| Dùng springdoc path properties khi management mode | Đường dẫn không thay đổi như mong đợi |
| Không cấu hình CORS giữa hai port | Browser chặn request |
| Tắt cache nhưng không kiểm soát URL | Mỗi request có thể sinh server khác nhau |
| Khai báo server tường minh và customizer mâu thuẫn | Khó dự đoán server cuối cùng |
| Mở management port công khai | Lộ endpoint vận hành |
| Thêm prefix ở cả proxy và servers | URL bị lặp path |

## 31. Checklist trước khi phát hành

- [ ] Đã phân biệt URL Swagger UI, OpenAPI document và servers.
- [ ] Đã xác định application port và management port.
- [ ] Nếu dùng management port, port đó khác application port.
- [ ] Đã expose openapi và swagger-ui trong Actuator.
- [ ] Đã dùng endpoint /actuator/openapi và /actuator/swagger-ui khi management mode.
- [ ] Không dựa vào springdoc path properties khi use-management-port=true.
- [ ] Servers trỏ tới application API public URL.
- [ ] Forwarded headers được proxy tạo và ghi đè an toàn.
- [ ] X-Forwarded-Proto phản ánh scheme public.
- [ ] X-Forwarded-Host phản ánh public host.
- [ ] X-Forwarded-Prefix phản ánh prefix sau khi rewrite.
- [ ] server.forward-headers-strategy phù hợp với embedded server.
- [ ] Context path và proxy prefix không bị áp dụng hai lần.
- [ ] CORS được cấu hình cho cả docs và API khi cross-origin.
- [ ] Management port được bảo vệ bằng network policy và security.
- [ ] ServerBaseUrlCustomizer chỉ thay URL khi cần.
- [ ] Cache được cân nhắc nếu URL phụ thuộc request.
- [ ] Đã kiểm tra servers bằng curl và jq.
- [ ] Đã thử Try it out qua public route.
- [ ] Smoke test được chạy sau deploy.

## 32. Nguồn tra cứu

- [springdoc-openapi v2 – Actuator support](https://springdoc.org/v2/)
- [springdoc-openapi FAQ – Reverse proxy and forwarded headers](https://springdoc.org/faq.html)
- [springdoc-openapi FAQ – Server URL generation](https://springdoc.org/faq.html)
- [springdoc-openapi FAQ – Disable OpenAPI cache](https://springdoc.org/faq.html)
- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html)
- [Spring Boot – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Framework – ForwardedHeaderFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html)
- [Spring Boot Actuator – Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)

Sai URL máy chủ thường xuất phát từ việc nhầm URL tải tài liệu với URL gọi API. Sau reverse proxy, hãy xử lý Forwarded và X-Forwarded-* headers đúng trust boundary, đặc biệt là scheme, host và prefix. Khi dùng management port, OpenAPI/UI nằm dưới Actuator base path nhưng servers vẫn phải trỏ tới application API. Kiểm tra JSON servers, CORS, security và Try it out qua public route trước khi kết luận sự cố đã được xử lý.
