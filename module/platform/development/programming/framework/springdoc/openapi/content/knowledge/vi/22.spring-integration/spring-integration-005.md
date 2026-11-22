# Management port khác cổng ứng dụng và tác động đến giao diện

Spring Boot có thể chạy API nghiệp vụ trên một cổng và các endpoint quản trị Actuator trên một cổng riêng. Khi dùng springdoc-openapi, Swagger UI và tài liệu OpenAPI cũng có thể được đưa lên management port. Cách triển khai này giúp tách bề mặt quản trị khỏi cổng phục vụ người dùng, nhưng làm thay đổi URL của tài liệu, cách trình duyệt gọi API và yêu cầu CORS.

Ví dụ một ứng dụng chạy API trên cổng 8080, management server trên cổng 9090:

- API nghiệp vụ: http://localhost:8080/api/orders.
- OpenAPI JSON: http://localhost:9090/actuator/openapi.
- Swagger UI: http://localhost:9090/actuator/swagger-ui.

Để đạt kết quả đó, cần cấu hình management server có cổng khác cổng ứng dụng, bật Actuator endpoint exposure cho các endpoint do springdoc đăng ký và bật springdoc.use-management-port. Nếu giao diện trên management port gọi API ở application port, trình duyệt xem hai địa chỉ là hai origin khác nhau và áp dụng CORS.

## 1. Phân biệt application port và management port

Spring Boot có hai nhóm cấu hình cổng:

| Thuộc tính | Chức năng | Ví dụ |
| --- | --- | --- |
| **server.port** | Cổng HTTP phục vụ controller và API nghiệp vụ | 8080 |
| **management.server.port** | Cổng riêng cho management server và các Actuator endpoint | 9090 |
| **management.server.address** | Địa chỉ mạng mà management server lắng nghe | 127.0.0.1 |
| **management.endpoints.web.base-path** | Prefix URL cho Actuator web endpoints | /actuator |
| **springdoc.use-management-port** | Đưa Swagger UI và OpenAPI endpoint của springdoc lên management port | true |

Nếu không cấu hình management.server.port, Actuator thường dùng cùng web server với ứng dụng. Khi đặt một cổng khác, Spring Boot tạo management server riêng. Vì vậy, hai nhóm endpoint có thể có địa chỉ mạng, TLS, context path và chính sách truy cập khác nhau.

management.server.address chỉ có thể khác địa chỉ của application server khi management port khác application port. Ví dụ, bind management server vào 127.0.0.1 giúp chỉ tiến trình trên cùng máy truy cập được cổng quản trị. Nếu muốn truy cập từ mạng vận hành, hãy dùng địa chỉ mạng nội bộ phù hợp và giới hạn bằng firewall hoặc network policy.

Không nhầm việc đổi port với việc bảo vệ endpoint. Cổng 9090 vẫn có thể được truy cập từ bên ngoài nếu server lắng nghe trên mọi interface và mạng cho phép kết nối.

## 2. Thêm Actuator và springdoc UI dependency

Để đưa giao diện và đặc tả lên management port, ứng dụng cần có Spring Boot Actuator và starter springdoc phù hợp với web stack.

Ví dụ Gradle cho Spring MVC:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:2.10.0")
}
~~~

Nếu ứng dụng dùng WebFlux, thay starter MVC bằng:

~~~groovy
implementation("org.springdoc:springdoc-openapi-starter-webflux-ui:2.10.0")
~~~

Ví dụ dùng springdoc v2.10.0 cho Spring Boot 3.x. Hãy chọn phiên bản springdoc tương thích với dòng Spring Boot đang dùng và quản lý phiên bản tập trung bằng BOM hoặc version catalog nếu dự án có nhiều module. Không ghép tùy ý starter của các major version khác nhau.

Nếu chỉ cần OpenAPI JSON/YAML mà không cần Swagger UI, có thể dùng starter API tương ứng. Tuy nhiên, bài học này cần starter UI vì mục tiêu là truy cập giao diện Swagger UI trên management port.

## 3. Cấu hình management port và springdoc

Ví dụ application.yml:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
    # Chỉ lắng nghe trên máy local trong ví dụ này.
    # Bỏ hoặc thay bằng địa chỉ mạng quản trị khi cần truy cập từ xa.
    address: 127.0.0.1
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: "health,info,openapi,swagger-ui"

springdoc:
  use-management-port: true
~~~

Các cấu hình quan trọng:

- server.port: 8080 giữ API nghiệp vụ trên application server.
- management.server.port: 9090 tạo management server trên cổng khác.
- management.server.address giới hạn interface lắng nghe. Với ví dụ này, chỉ máy local truy cập được.
- management.endpoints.web.exposure.include cho phép các Actuator endpoint được truy cập qua HTTP.
- springdoc.use-management-port: true đăng ký OpenAPI và Swagger UI dưới management endpoint base path.

Nếu cần truy cập management port từ máy khác, không dùng 127.0.0.1; hãy bind vào interface nội bộ cần thiết, cấu hình TLS và giới hạn nguồn truy cập ở tầng mạng.

Trong application.properties, các thuộc tính tương đương:

~~~properties
server.port=8080
management.server.port=9090
management.server.address=127.0.0.1
management.endpoints.web.base-path=/actuator
management.endpoints.web.exposure.include=health,info,openapi,swagger-ui
springdoc.use-management-port=true
~~~

Mặc định, Spring Boot chỉ expose một số Actuator endpoint giới hạn qua HTTP, thường có health. Khi đặt danh sách include, chỉ những endpoint được liệt kê mới được expose qua HTTP. Không dùng management.endpoints.web.exposure.include=* chỉ để Swagger UI hoạt động. Chỉ expose những endpoint thực sự cần thiết.

## 4. Các URL khi bật use-management-port

Với cấu hình trên, springdoc đăng ký endpoint dưới Actuator base path:

| Tài nguyên | URL |
| --- | --- |
| Actuator base path (các link discovery tùy cấu hình) | http://localhost:9090/actuator |
| OpenAPI definition | http://localhost:9090/actuator/openapi |
| Swagger UI | http://localhost:9090/actuator/swagger-ui |

Đường dẫn openapi và swagger-ui là các Actuator endpoint ID do springdoc đăng ký. Nếu đổi management.endpoints.web.base-path thành /manage, các URL tương ứng trở thành:

- http://localhost:9090/manage/openapi
- http://localhost:9090/manage/swagger-ui

Tên hai endpoint do springdoc tạo dưới Actuator base path hiện không được tùy biến bằng các thuộc tính path thông thường của springdoc.

Điểm cần nhớ: khi springdoc.use-management-port=true, các thuộc tính đường dẫn springdoc như springdoc.api-docs.path và springdoc.swagger-ui.path không áp dụng cho các endpoint được expose trên management port. Hãy điều chỉnh management.endpoints.web.base-path nếu muốn thay đổi prefix Actuator.

Các URL thông thường như /v3/api-docs hoặc /swagger-ui.html thuộc cách phục vụ trên application web server. Khi dùng management port, hãy truy cập endpoint dưới Actuator base path theo cấu hình, không suy ra URL từ cấu hình Swagger UI mặc định.

## 5. Expose endpoint không đồng nghĩa với cấp quyền

management.endpoints.web.exposure.include quyết định endpoint nào được công bố qua HTTP. Thuộc tính này không xác định người dùng nào được phép truy cập.

Hai lớp cấu hình cần được xem riêng:

1. **Exposure:** endpoint có được đăng ký và truy cập qua HTTP hay không.
2. **Security:** người gọi có được phép xem hoặc sử dụng endpoint hay không.

OpenAPI definition có thể tiết lộ tên endpoint, cấu trúc dữ liệu, mô hình lỗi và thông tin triển khai. Swagger UI còn cho phép gửi request đến API. Vì vậy, management port cần có chính sách truy cập phù hợp với tài liệu mà nó phục vụ.

Ví dụ, chỉ cho phép người có role OPS truy cập các Actuator endpoint, trong khi health có thể được mở cho probe:

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ManagementSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain managementSecurity(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health"))
                    .permitAll()
                .anyRequest()
                    .hasRole("OPS")
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là ví dụ cho servlet stack. Ứng dụng thực tế cần có cơ chế xác thực phù hợp và filter chain riêng cho API nghiệp vụ nếu cần. Khi khai báo nhiều SecurityFilterChain, đặt matcher Actuator ở thứ tự ưu tiên phù hợp để quy tắc quản trị không bị một chain tổng quát bắt trước.

Nếu Spring Security tự cấu hình mặc định, việc khai báo một SecurityFilterChain tùy chỉnh có thể khiến cấu hình bảo mật mặc định lùi lại. Hãy xác định rõ các chain bảo vệ management endpoint, Swagger UI và API nghiệp vụ.

## 6. Management port có thể dùng TLS và địa chỉ riêng

Management server có các thuộc tính SSL riêng dưới prefix management.server.ssl. Chúng không tự động giống cấu hình server.ssl.

Ví dụ application server và management server cùng dùng HTTPS:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:application-keystore.p12
    key-store-password: ${APP_KEYSTORE_PASSWORD}
    key-store-type: PKCS12

management:
  server:
    port: 9443
    ssl:
      enabled: true
      key-store: classpath:management-keystore.p12
      key-store-password: ${MANAGEMENT_KEYSTORE_PASSWORD}
      key-store-type: PKCS12
~~~

Ví dụ chỉ minh họa hai cấu hình TLS độc lập; keystore và mật khẩu cần được cung cấp an toàn theo môi trường. Không commit mật khẩu thật vào source control.

Spring Boot cũng cho phép management server dùng cấu hình SSL khác application server. Điều đó có thể hữu ích trong mạng quản trị nội bộ, nhưng không nên để management traffic nhạy cảm chạy HTTP không mã hóa trên mạng không tin cậy.

Nếu không muốn cung cấp management HTTP endpoints, có thể đặt management.server.port=-1 hoặc loại endpoint khỏi web exposure. Việc tắt HTTP exposure không nhất thiết đồng nghĩa mọi hình thức quản trị khác, chẳng hạn JMX, cũng bị tắt.

## 7. Phân biệt use-management-port và show-actuator

Hai thuộc tính springdoc có mục đích khác nhau:

| Thuộc tính | Mục đích |
| --- | --- |
| springdoc.use-management-port | Đưa OpenAPI endpoint và giao diện Swagger UI/Scalar lên management port |
| springdoc.show-actuator | Thêm tài liệu cho các Actuator endpoint vào OpenAPI/Swagger UI |

Có thể kết hợp cả hai:

~~~yaml
springdoc:
  use-management-port: true
  show-actuator: true
~~~

Khi bật show-actuator, springdoc có thể thêm một group riêng cho Actuator endpoint. Nếu ứng dụng chưa có group nào, springdoc có thể tạo group mặc định cho API ứng dụng.

Nếu chỉ bật show-actuator=true mà không bật use-management-port, Swagger UI vẫn được phục vụ trên application port. Khi management port khác application port, giao diện trên application port muốn gọi các Actuator endpoint ở management port thì cần CORS cho các Actuator endpoint đó.

Ngược lại, khi bật use-management-port=true, UI và OpenAPI endpoint nằm dưới Actuator base path. Nếu UI gọi API nghiệp vụ trên application port, CORS cần được cấu hình ở application server.

## 8. Tác động đến Try it out và CORS

Giả sử:

- Swagger UI được tải từ http://localhost:9090/actuator/swagger-ui.
- API nghiệp vụ chạy tại http://localhost:8080/api/orders.

Hai URL có cùng hostname nhưng khác port nên là hai origin khác nhau. Khi người dùng bấm Try it out, trình duyệt gửi request từ origin http://localhost:9090 đến http://localhost:8080. Nếu không có CORS policy phù hợp, browser có thể chặn request hoặc không cho JavaScript đọc response.

Ví dụ cấu hình CORS cho application API:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class ApiCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("http://localhost:9090")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "X-Request-Id"
            )
            .maxAge(3600);
    }
}
~~~

Nếu dùng cookie session hoặc credentials cross-origin, cần bật allowCredentials(true) và chỉ định origin cụ thể. Không kết hợp credentials với wildcard origin *. Cũng cần cấu hình thuộc tính credentials ở client nếu Swagger UI/request mechanism yêu cầu.

Khi dùng Spring Security, CORS phải được xử lý trước khi authorization từ chối preflight OPTIONS. Cấu hình CORS trong Spring MVC có thể được tích hợp với Spring Security qua http.cors(...) hoặc cấu hình tương ứng của ứng dụng.

Nếu API và Swagger UI được phục vụ cùng scheme, host và port qua reverse proxy, browser có thể xem chúng là same-origin và không cần CORS. Khi đó, proxy phải route đúng request API đến application server và route tài liệu đến management server.

## 9. Đảm bảo OpenAPI server URL trỏ đến application port

Một điểm dễ nhầm khi UI chạy trên management port là URL gốc của API. Tài liệu OpenAPI được tải từ management server, nhưng các controller nghiệp vụ vẫn chạy trên application server.

Hãy kiểm tra trường servers trong OpenAPI JSON. Nếu URL server là relative hoặc trỏ nhầm đến management port, Try it out có thể gửi request đến 9090 thay vì 8080.

Với môi trường local, có thể khai báo server URL rõ ràng:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "http://localhost:8080",
            description = "Application API"
        )
    }
)
class OpenApiServerConfiguration {}
~~~

Nếu ứng dụng có context path /shop, URL server cần bao gồm context path, ví dụ http://localhost:8080/shop. Với production, dùng URL API bên ngoài mà client thực sự truy cập, chẳng hạn https://api.example.com; không đưa localhost hoặc management port nội bộ vào tài liệu công khai.

Trong hệ thống nhiều môi trường, hãy externalize server URL bằng cấu hình theo profile hoặc tạo OpenAPI bean đọc giá trị từ configuration. Không hardcode một URL local cho mọi môi trường.

## 10. Reverse proxy và context path

Trong production, management port thường không được mở trực tiếp ra Internet. Một reverse proxy hoặc mạng quản trị có thể route đường dẫn công khai đến management server.

Ví dụ:

~~~text
https://ops.example.com/manage/openapi
        |
        v
Reverse proxy
        |
        v
management server :9090
~~~

Khi cấu hình proxy:

- Route đúng Actuator base path đến management port.
- Giữ nguyên hoặc ánh xạ đúng prefix đường dẫn.
- Cấu hình external host, scheme và port đúng nếu ứng dụng sinh redirect URL.
- Chỉ tin Forwarded hoặc X-Forwarded-* từ proxy đáng tin cậy.
- Không công khai trực tiếp cổng quản trị nếu kiến trúc chỉ yêu cầu truy cập qua VPN hoặc mạng vận hành.

Application context path và management endpoint base path là hai phạm vi riêng. Ví dụ API có context path /shop, còn management endpoint có base path /actuator; không giả định một prefix tự động áp dụng cho cả hai server.

Khi thay đổi management.endpoints.web.base-path, các Actuator endpoint sẽ chuyển sang prefix mới. Nếu management port được cấu hình riêng, base path được tính theo cấu hình management server tương ứng. Kiểm tra tài liệu Spring Boot đúng phiên bản khi ứng dụng có management context path riêng.

## 11. Kiểm tra endpoint sau khi khởi động

Sau khi ứng dụng chạy, kiểm tra từng server riêng:

~~~bash
# API nghiệp vụ trên application port
curl -i http://localhost:8080/api/orders

# OpenAPI definition trên management port
curl -i http://localhost:9090/actuator/openapi

# Swagger UI endpoint trên management port
curl -i http://localhost:9090/actuator/swagger-ui
~~~

Nếu management port được bind vào 127.0.0.1, chỉ chạy các lệnh từ cùng máy. Nếu endpoint yêu cầu xác thực, thêm thông tin xác thực theo cơ chế đã cấu hình; không đưa mật khẩu thật vào shell history hoặc log chia sẻ.

Trong trình duyệt:

1. Mở http://localhost:9090/actuator/swagger-ui.
2. Kiểm tra Swagger UI tải được JavaScript, CSS và OpenAPI definition.
3. Mở Network panel và xác định request tải tài liệu đi đến management port.
4. Kiểm tra trường servers trong OpenAPI definition.
5. Thực hiện Try it out và xác nhận request nghiệp vụ đi đến application port.
6. Nếu request bị chặn, kiểm tra OPTIONS preflight và CORS response.
7. Kiểm tra xác thực và quyền truy cập trên cả management endpoint lẫn API nghiệp vụ.

Không kết luận cấu hình đã đúng chỉ vì trang Swagger UI hiển thị. UI có thể tải thành công trong khi OpenAPI server URL hoặc CORS khiến Try it out không gọi được API.

## 12. Lỗi thường gặp

**/actuator/swagger-ui trả 404.** Kiểm tra có Actuator dependency, springdoc UI starter, springdoc.use-management-port=true và endpoint ID swagger-ui có nằm trong management.endpoints.web.exposure.include hay không.

**/actuator/openapi trả 404.** Kiểm tra endpoint openapi có được expose. Nếu đã đổi management.endpoints.web.base-path, dùng prefix mới thay cho /actuator.

**Management server không khởi động ở cổng riêng.** Kiểm tra management.server.port khác server.port, cổng chưa bị tiến trình khác chiếm và địa chỉ bind hợp lệ.

**Swagger UI vẫn nằm trên application port.** Kiểm tra springdoc.use-management-port có bật đúng profile và đúng file cấu hình được nạp không. Phân biệt với springdoc.show-actuator, thuộc tính này chỉ thêm tài liệu Actuator vào giao diện.

**Các thuộc tính springdoc.api-docs.path hoặc springdoc.swagger-ui.path không có tác dụng.** Khi springdoc.use-management-port=true, các springdoc path properties thông thường không áp dụng cho các Actuator endpoint. Hãy dùng management.endpoints.web.base-path.

**Trang UI mở được nhưng Try it out bị CORS.** UI và API đang khác origin. Cho phép chính xác origin của Swagger UI ở application server, đúng method/header và credentials nếu cần.

**Try it out gửi đến management port thay vì application port.** Kiểm tra trường servers trong OpenAPI definition. Đặt URL server trỏ đến application API và bao gồm context path cần thiết.

**UI không truy cập được Actuator endpoint khi dùng show-actuator=true.** Nếu UI chạy trên application port còn Actuator chạy ở management port khác, cần CORS cho Actuator endpoint.

**Management endpoint bị truy cập công khai.** Kiểm tra management.server.address, firewall, network policy, TLS, Spring Security và danh sách exposure. Port riêng không tự tạo ranh giới bảo mật.

**Sau khi thay base path, proxy trả 404.** Đồng bộ management.endpoints.web.base-path với route của reverse proxy và URL mà người vận hành truy cập.

**Tài liệu dùng HTTP trong khi application API dùng HTTPS.** Kiểm tra management.server.ssl.* và external proxy scheme. Không để credential hoặc token đi qua HTTP trên mạng không tin cậy.

## 13. Checklist triển khai

- [ ] Có Actuator và springdoc UI starter phù hợp với MVC/WebFlux.
- [ ] Chọn management.server.port khác server.port khi muốn tách management server.
- [ ] Cấu hình management.server.address theo phạm vi mạng cần truy cập.
- [ ] Expose tối thiểu openapi và swagger-ui qua Actuator.
- [ ] Bật springdoc.use-management-port=true.
- [ ] Dùng URL dưới Actuator base path để truy cập OpenAPI và Swagger UI.
- [ ] Không dựa vào springdoc.api-docs.path hoặc springdoc.swagger-ui.path khi dùng management port.
- [ ] Phân biệt use-management-port với show-actuator.
- [ ] Bảo vệ OpenAPI và Swagger UI bằng xác thực, phân quyền và network policy.
- [ ] Cấu hình TLS riêng cho management server nếu cần.
- [ ] Kiểm tra servers trong OpenAPI trỏ đến application API.
- [ ] Cấu hình CORS ở đúng server khi UI và API khác origin.
- [ ] Đồng bộ context path và reverse proxy route.
- [ ] Kiểm tra URL bằng curl và Browser Network panel.

## 14. Kết luận

Management port tách endpoint quản trị khỏi cổng API nghiệp vụ. Với springdoc, bật springdoc.use-management-port=true và expose hai Actuator endpoint openapi cùng swagger-ui để đưa tài liệu lên management server. Giao diện sẽ có URL dưới Actuator base path, còn controller nghiệp vụ vẫn chạy trên application port. Vì vậy, cần kiểm tra OpenAPI server URL, cấu hình CORS khi hai port tạo thành hai origin, và bảo vệ management port bằng xác thực, TLS cùng network policy. Việc tách cổng giúp tổ chức bề mặt truy cập rõ ràng; bảo mật thực tế vẫn phụ thuộc vào exposure, security và cấu hình mạng.

## 15. Nguồn tham khảo

- [Spring Boot — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html): management port, address, base path, SSL và web exposure.
- [springdoc-openapi v2 — Actuator support](https://springdoc.org/v2/#actuator-support): springdoc.use-management-port, endpoint IDs openapi/swagger-ui, Actuator base path, show-actuator và yêu cầu CORS.
- [springdoc-openapi v2 — Core Properties](https://springdoc.org/v2/core-properties.html): cấu hình springdoc.use-management-port.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure và cách truy cập Actuator endpoints.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): cấu hình CORS cho request cross-origin trong Spring MVC.
