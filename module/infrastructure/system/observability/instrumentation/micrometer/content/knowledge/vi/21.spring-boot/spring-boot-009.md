# Cho phép công bố /actuator/prometheus và bảo vệ đường truy cập

Spring Boot Actuator cung cấp endpoint `/actuator/prometheus` để Prometheus scrape metrics do Micrometer ghi nhận. Để endpoint hoạt động, ứng dụng cần có Prometheus registry, expose endpoint qua HTTP và thiết lập quyền truy cập phù hợp với mạng giám sát. Ba việc này là các lớp cấu hình khác nhau: có dependency không đồng nghĩa endpoint đã được expose, và expose endpoint cũng không đồng nghĩa mọi client đều được phép truy cập.

Metrics có thể tiết lộ tên service, route, trạng thái dependency, mức tải và cấu trúc hạ tầng. Vì vậy, endpoint Prometheus nên chỉ mở trong mạng quan sát được kiểm soát, đồng thời yêu cầu xác thực hoặc cơ chế bảo vệ tương đương khi phù hợp.

## 1. Ba lớp để endpoint Prometheus hoạt động

Một endpoint scrape cần ba điều kiện:

1. **Có registry và endpoint:** ứng dụng có Micrometer Prometheus registry để chuyển meter thành Prometheus exposition.
2. **Được expose qua HTTP:** Spring Boot cho phép endpoint `prometheus` xuất hiện trên web.
3. **Được phép truy cập:** Spring Security và lớp mạng xác định client nào có thể đọc endpoint.

Luồng request:

~~~text
Prometheus server
      |
      | HTTP(S) GET /actuator/prometheus
      | Authorization / client identity
      v
Network policy / firewall / ingress
      |
      v
Spring Security
      |
      v
Spring Boot Actuator endpoint
      |
      v
PrometheusMeterRegistry
      |
      v
Prometheus text / OpenMetrics payload
~~~

Nếu thiếu dependency, endpoint có thể không được tạo. Nếu endpoint chưa expose, request thường nhận 404. Nếu security policy yêu cầu xác thực nhưng request không đáp ứng, server thường trả 401 hoặc 403 tùy quy tắc. Nếu response 200 nhưng Prometheus vẫn không scrape được, cần kiểm tra kết nối, TLS, Content-Type và cấu hình scrape.

## 2. Thêm Actuator và Prometheus registry

Với Gradle, dependency thường dùng:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Spring Boot dependency management sẽ chọn phiên bản Micrometer tương thích với phiên bản Boot của dự án. Tránh tự ghim một phiên bản registry khác với BOM nếu chưa xác minh tương thích.

Actuator cung cấp endpoint quản trị và quan sát. Prometheus registry cung cấp implementation để chuyển meter sang định dạng Prometheus. Khi registry được phát hiện và cấu hình, Spring Boot có thể tạo endpoint Prometheus tương ứng.

Chỉ thêm dependency không có nghĩa endpoint tự động được mở ra bên ngoài. Cần cấu hình exposure và security riêng.

## 3. Expose endpoint /actuator/prometheus

Các endpoint Spring Boot Actuator được expose qua HTTP theo cấu hình. Ví dụ chỉ công bố health và Prometheus:

~~~properties
management.endpoints.web.exposure.include=health,prometheus
management.endpoint.health.show-details=never
~~~

Nếu cần thông tin khác, hãy thêm rõ từng endpoint vào danh sách. Không dùng `*` trong production nếu không có lý do cụ thể, vì nó có thể expose thêm nhiều endpoint quản trị.

Đường dẫn mặc định của Prometheus endpoint là:

~~~text
/actuator/prometheus
~~~

Có thể giữ base path mặc định hoặc thay đổi:

~~~properties
management.endpoints.web.base-path=/manage
~~~

Khi đổi base path, đường scrape sẽ đổi tương ứng thành `/manage/prometheus`. Nếu dùng path mapping riêng, Prometheus scrape config cũng phải dùng đường dẫn mới.

Phân biệt các thuộc tính:

| Cấu hình | Tác dụng |
|---|---|
| `management.endpoints.web.exposure.include` | Chọn endpoint được công bố qua HTTP |
| `management.endpoints.web.base-path` | Đổi tiền tố đường dẫn HTTP |
| `management.server.port` | Chọn cổng riêng cho management endpoint |
| Spring Security | Xác thực và phân quyền request |
| Firewall / NetworkPolicy | Giới hạn nguồn mạng được kết nối |

Exposure chỉ quyết định endpoint có được phục vụ qua web hay không. Nó không thay thế xác thực, phân quyền hoặc kiểm soát mạng.

## 4. Tách cổng management khỏi cổng ứng dụng

Trong môi trường production, có thể chạy management endpoint trên một cổng riêng:

~~~properties
server.port=8080
management.server.port=8081
management.endpoints.web.exposure.include=health,prometheus
~~~

Khi đó ứng dụng phục vụ request nghiệp vụ ở cổng 8080, còn Actuator phục vụ ở cổng 8081. Prometheus scrape:

~~~yaml
scrape_configs:
  - job_name: "orders-service"
    metrics_path: "/actuator/prometheus"
    static_configs:
      - targets:
          - "orders-service:8081"
~~~

Ví dụ scrape trên dùng HTTP mặc định. Nếu đặt `scheme: https` ở Prometheus, management endpoint phải thực sự phục vụ TLS hoặc request phải đi qua một reverse proxy kết thúc TLS. Chỉ đổi scheme trong scrape config không tự bật HTTPS cho Spring Boot. Khi dùng TLS trực tiếp, cấu hình certificate và private key cho management server theo phiên bản Boot; khi TLS kết thúc tại proxy, giới hạn đường từ proxy tới ứng dụng trong mạng tin cậy.

Tách cổng giúp cấu hình ingress, firewall hoặc Kubernetes Service riêng cho traffic quản trị. Tuy nhiên, một cổng riêng không tự động an toàn: nếu cổng đó vẫn được publish ra Internet hoặc mạng người dùng, endpoint vẫn có thể bị truy cập.

Có thể bind management server vào một địa chỉ mạng nội bộ:

~~~properties
management.server.address=10.20.0.15
~~~

Địa chỉ phải tồn tại trên interface của máy hoặc container. Nếu đặt `127.0.0.1`, chỉ tiến trình truy cập được loopback của cùng network namespace mới kết nối được. Prometheus chạy ở pod hoặc máy khác sẽ không scrape được loopback đó.

Với Kubernetes, thường tạo Service riêng cho management port và dùng NetworkPolicy để chỉ cho phép Prometheus namespace hoặc các scraper được chỉ định truy cập. Không expose management port qua public Ingress nếu không có yêu cầu rõ ràng.

## 5. Bảo vệ endpoint bằng Spring Security

Khi ứng dụng dùng Spring Security, hãy yêu cầu role riêng cho endpoint Prometheus. Có thể dùng `EndpointRequest` để match Actuator endpoint theo ID thay vì tự viết chuỗi path; cách này bền hơn khi base path thay đổi.

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers(EndpointRequest.to("prometheus"))
                .hasRole("METRICS")
            .requestMatchers(EndpointRequest.to("health"))
                .permitAll()
            .anyRequest()
                .authenticated()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Trong ví dụ:

- Request tới Prometheus endpoint cần authority `ROLE_METRICS`.
- Health endpoint được phép truy cập công khai theo chính sách ví dụ.
- Các request còn lại cần xác thực.
- HTTP Basic được bật để minh họa cách Prometheus gửi credentials.

`hasRole("METRICS")` tự kiểm tra authority có tiền tố `ROLE_`. User scrape cần được cấp `ROLE_METRICS` bởi user store, LDAP, OAuth2 resource server hoặc cơ chế xác thực mà ứng dụng sử dụng.

Nếu khai báo `SecurityFilterChain` tùy chỉnh, cấu hình bảo mật mặc định của Spring Boot Actuator có thể nhường chỗ cho cấu hình đó. Khi ấy, ứng dụng phải tự quy định quyền cho cả endpoint quản trị và các route nghiệp vụ. Không tạo một chain chỉ bảo vệ Prometheus rồi vô tình để các route còn lại không có quy tắc phù hợp.

Không cần tắt CSRF toàn cục chỉ để cho phép Prometheus scrape bằng GET. Nếu ứng dụng có form login hoặc các endpoint thay đổi trạng thái, hãy giữ chính sách CSRF phù hợp cho chúng.

## 6. Cấp credentials riêng cho Prometheus

Prometheus có thể gửi HTTP Basic credentials khi scrape:

~~~yaml
scrape_configs:
  - job_name: "orders-service"
    scheme: https
    metrics_path: "/actuator/prometheus"
    scrape_interval: 15s
    static_configs:
      - targets:
          - "orders-service.internal:8081"
    basic_auth:
      username: prometheus-scraper
      password_file: /etc/prometheus/secrets/orders-metrics-password
~~~

File password phải được mount từ secret store hoặc cơ chế quản lý secret của môi trường. Giới hạn quyền đọc file cho tiến trình Prometheus. Không commit password thật vào Git, không ghi credentials vào log và không dùng cùng một tài khoản quản trị có quyền rộng cho scrape.

HTTP Basic chỉ mã hóa credentials bằng Base64, không phải mã hóa đường truyền. Khi gửi credentials qua mạng, dùng HTTPS/TLS. Với hạ tầng có hỗ trợ, có thể dùng mutual TLS, service identity hoặc bearer token thay cho Basic Auth.

Tài khoản scrape nên có quyền đọc metrics cần thiết và không có quyền thay đổi cấu hình, dữ liệu nghiệp vụ hoặc các endpoint quản trị khác.

## 7. Kết hợp xác thực với giới hạn mạng

Bảo vệ tốt thường có nhiều lớp:

- Chỉ bind management port trên interface nội bộ hoặc private network.
- Chỉ publish management port qua Service dành cho monitoring.
- Dùng firewall hoặc NetworkPolicy giới hạn nguồn là Prometheus scraper.
- Yêu cầu xác thực và role riêng tại Spring Security.
- Dùng TLS khi credentials hoặc metrics đi qua mạng.
- Theo dõi request bị từ chối và thay đổi cấu hình endpoint.

Mạng nội bộ không nên được xem là mặc định đáng tin cậy. Một pod khác trong cùng cluster có thể bị xâm nhập; nếu mọi workload đều truy cập được management port, endpoint vẫn có bề mặt tấn công đáng kể.

Nếu dùng reverse proxy, hãy bảo đảm proxy không mở đường truy cập thay thế bỏ qua Spring Security. Không dựa vào header IP do client tự gửi để xác định nguồn tin cậy nếu proxy chưa được cấu hình để xóa và ghi lại header đó.

## 8. Không đưa dữ liệu nhạy cảm vào metrics

Endpoint Prometheus thường chứa tên metric, tag, route, trạng thái dependency và các thông tin vận hành. Những dữ liệu này có thể giúp người ngoài suy ra cấu trúc hệ thống hoặc hành vi tải.

Không đưa các giá trị sau vào tag:

- Access token, API key, session ID.
- Email, số điện thoại hoặc dữ liệu cá nhân.
- User ID, order ID, request ID.
- URL đầy đủ chứa query string hoặc ID thực.
- Nội dung exception có thể chứa dữ liệu đầu vào.

Dùng route template và nhóm trạng thái có cardinality hữu hạn, ví dụ `uri=/orders/{id}` hoặc `outcome=success|failure`. Nếu cần phân tích request cụ thể, dùng tracing hoặc log có kiểm soát quyền truy cập và retention thay vì tag metrics.

Bảo vệ endpoint không thay thế việc giảm dữ liệu nhạy cảm trong chính payload metrics. Một scraper được xác thực vẫn có thể lưu trữ dữ liệu không phù hợp nếu instrumentation đã tạo tag sai.

## 9. Kiểm tra endpoint bằng curl

Có thể kiểm tra response từ máy có đường mạng tới management port.

Không gửi credentials:

~~~bash
curl -i https://orders-service.internal:8081/actuator/prometheus
~~~

Nếu endpoint yêu cầu xác thực, response dự kiến là `401 Unauthorized`.

Gửi credentials:

~~~bash
curl -i \
  --user prometheus-scraper \
  https://orders-service.internal:8081/actuator/prometheus
~~~

`curl` sẽ hỏi password tương tác nếu không truyền password trong command line. Cách này giúp tránh để password xuất hiện trong lịch sử shell. Trong môi trường tự động, dùng secret injection phù hợp và không in giá trị secret ra log.

Kiểm tra ba tình huống:

| Kết quả | Diễn giải |
|---|---|
| 401 Unauthorized | Thiếu credentials hoặc credentials không hợp lệ |
| 403 Forbidden | Đã xác thực nhưng thiếu role `METRICS` hoặc bị policy từ chối |
| 200 OK | Request được phép; tiếp tục kiểm tra body và Content-Type |

Nếu nhận 404, kiểm tra dependency Prometheus registry, exposure include, base path, management port và path mapping. Nếu nhận 200 nhưng body là HTML hoặc JSON, có thể request đang đi nhầm endpoint hoặc bị proxy/login page thay thế.

Payload hợp lệ thường có các dòng HELP, TYPE và sample. Tên metric cụ thể phụ thuộc meter và registry; xác minh payload thực tế trước khi viết PromQL.

## 10. Kiểm thử quyền truy cập

Có thể kiểm thử security rule bằng Spring Boot test và Spring Security Test. Ví dụ sau giả sử Actuator và Prometheus registry có trong test runtime, endpoint được expose trên cùng cổng ứng dụng và SecurityFilterChain ở trên đang hoạt động.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "management.endpoints.web.exposure.include=prometheus"
})
@AutoConfigureMockMvc
class PrometheusEndpointSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void unauthenticatedRequestIsRejected() throws Exception {
        mvc.perform(get("/actuator/prometheus"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "USER")
    void authenticatedUserWithoutMetricsRoleIsForbidden()
            throws Exception {
        mvc.perform(get("/actuator/prometheus"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "METRICS")
    void metricsRoleCanReadEndpoint() throws Exception {
        mvc.perform(get("/actuator/prometheus"))
            .andExpect(status().isOk());
    }
}
~~~

Cần thêm dependency test tương ứng, thường là `spring-security-test` cùng `spring-boot-starter-test`. Nếu management server chạy cổng riêng, MockMvc của application port không đại diện đầy đủ cho management server; hãy dùng integration test qua HTTP tới management port thật.

Ngoài test authorization, nên kiểm tra từ network boundary:

- Host không thuộc mạng monitoring không thể kết nối management port.
- Prometheus scraper hợp lệ có thể kết nối và xác thực.
- Scraper không có role nhận 403.
- TLS certificate được xác minh đúng.
- Endpoint không bị expose qua public ingress ngoài dự kiến.

## 11. Cấu hình ví dụ hoàn chỉnh

Một cấu hình tối thiểu cho ứng dụng dùng cổng management riêng:

~~~properties
server.port=8080

management.server.port=8081
management.endpoints.web.base-path=/actuator
management.endpoints.web.exposure.include=health,prometheus
management.endpoint.health.show-details=never
management.metrics.tags.application=orders-service
~~~

Dependency:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-security")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

SecurityFilterChain giới hạn Prometheus endpoint cho role `METRICS`. Prometheus scrape management port qua HTTPS với tài khoản riêng và password được mount từ secret. Firewall hoặc NetworkPolicy chỉ cho phép scraper truy cập cổng 8081.

Đây là cấu hình mẫu; địa chỉ, TLS termination, user store, role provisioning và property cần điều chỉnh theo phiên bản Spring Boot cũng như hạ tầng triển khai.

## 12. Các lỗi thường gặp

- **Thêm dependency nhưng quên expose endpoint:** registry có thể tồn tại nhưng HTTP endpoint không truy cập được.
- **Expose endpoint nhưng không có Prometheus registry:** endpoint có thể không được tạo hoặc không có dữ liệu mong muốn.
- **Dùng wildcard cho mọi endpoint:** vô tình công bố nhiều chức năng quản trị hơn cần thiết.
- **Cho rằng cổng management riêng đã đủ an toàn:** cổng vẫn có thể được truy cập từ mạng không mong muốn.
- **Dùng `permitAll()` cho Prometheus trong production:** bất kỳ client nào tới được endpoint đều có thể đọc metrics.
- **Dùng tài khoản scrape có quyền quản trị:** tăng phạm vi ảnh hưởng nếu credentials bị lộ.
- **Dùng HTTP Basic qua HTTP không mã hóa:** credentials có thể bị nghe lén trên đường truyền.
- **Chỉ bảo vệ ở proxy:** route nội bộ hoặc đường truy cập khác có thể bỏ qua proxy.
- **Custom SecurityFilterChain nhưng quên các route khác:** cấu hình tùy chỉnh thay đổi hành vi security auto-configuration.
- **Bind management vào loopback khi Prometheus ở máy/pod khác:** scraper không thể kết nối.
- **Đưa ID hoặc dữ liệu cá nhân vào label:** endpoint được bảo vệ vẫn có thể phát tán dữ liệu nhạy cảm tới hệ thống lưu metrics.
- **Không kiểm tra 401, 403 và 200:** khó phân biệt lỗi xác thực, phân quyền và kết nối.

## 13. Checklist triển khai production

- [ ] Có `spring-boot-starter-actuator` và Prometheus registry tương thích.
- [ ] Chỉ expose `prometheus` cùng các endpoint thật sự cần thiết.
- [ ] Xác nhận đúng path, base path và management port.
- [ ] Tách management port hoặc management network khi phù hợp.
- [ ] Chỉ cho phép Prometheus scraper kết nối qua firewall/NetworkPolicy.
- [ ] Bảo vệ endpoint bằng authentication và role riêng.
- [ ] Dùng HTTPS/TLS hoặc mutual TLS khi đi qua mạng.
- [ ] Lưu credentials trong secret store, không commit vào repository.
- [ ] Không đưa dữ liệu nhạy cảm hoặc ID duy nhất vào tag.
- [ ] Kiểm tra request không credentials trả 401.
- [ ] Kiểm tra user thiếu role trả 403.
- [ ] Kiểm tra scraper hợp lệ nhận 200 và payload metrics.
- [ ] Kiểm tra endpoint không đi qua public ingress ngoài dự kiến.
- [ ] Theo dõi scrape failure, access denied và thay đổi cấu hình.

Endpoint `/actuator/prometheus` cần được công bố có chủ đích và giới hạn cho hệ thống giám sát. Kết hợp dependency đúng, HTTP exposure tối thiểu, Spring Security, TLS và network policy sẽ giúp Prometheus lấy được metrics mà không mở rộng quyền đọc dữ liệu vận hành cho các client không cần thiết.

