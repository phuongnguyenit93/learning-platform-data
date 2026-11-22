# Tích hợp health check và quản lý quyền truy cập Actuator

## 1. Vai trò của Actuator trong ứng dụng Spring Data REST

Spring Data REST xuất repository thành REST resource, thường dưới một API base path như /api. Spring Boot Actuator cung cấp các endpoint vận hành để theo dõi trạng thái, metrics, cấu hình và thông tin runtime. Hai nhóm endpoint phục vụ mục đích khác nhau:

- Repository resource thuộc API nghiệp vụ, ví dụ /api/orders.
- Actuator endpoint thuộc management API, mặc định dùng prefix /actuator, ví dụ /actuator/health.

Việc cấu hình base path của Spring Data REST bằng RepositoryRestConfiguration.setBasePath("/api") không tự động chuyển Actuator thành /api/actuator. Actuator có cấu hình management riêng. Nếu thay management base path hoặc port, hãy cập nhật URL trong monitoring, ingress, probe và firewall tương ứng.

Actuator endpoint chỉ sẵn sàng khi endpoint được cho phép truy cập và được expose qua một công nghệ như HTTP hoặc JMX. Vì vậy, cần cấu hình cả việc expose endpoint và quyền truy cập.

## 2. Thêm dependency và bật endpoint cần thiết

Với Spring Boot, thêm Actuator starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Nếu ứng dụng cần xác thực và phân quyền endpoint bằng Spring Security, thêm starter tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
~~~

Mặc định, Spring Boot chỉ expose endpoint health qua HTTP và JMX. Không cần expose toàn bộ endpoint để có health check cơ bản. Cấu hình tối thiểu:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when-authorized
      roles: ACTUATOR_ADMIN
~~~

Các endpoint HTTP thường có dạng /actuator/{id}. Có thể kiểm tra health bằng:

~~~bash
curl -i http://localhost:8080/actuator/health
~~~

Chỉ thêm endpoint vào exposure.include khi đã xác định dữ liệu endpoint trả về và người dùng nào được phép truy cập. Ví dụ, env, configprops, beans, heapdump, logfile và mappings có thể tiết lộ thông tin nội bộ. Dấu * expose tất cả endpoint phù hợp, do đó không nên dùng tùy tiện trên môi trường có thể truy cập từ mạng.

## 3. Phân biệt expose, endpoint access và Spring Security

Ba lớp cấu hình có mục đích khác nhau:

| Lớp | Câu hỏi được giải quyết | Cấu hình / cơ chế |
|---|---|---|
| Endpoint access | Endpoint có được phép hoạt động hay không, có chỉ đọc hay không? | Các thuộc tính management.endpoint.*.access và management.endpoints.access.* ở các phiên bản Spring Boot hỗ trợ |
| Exposure | Endpoint được công bố qua HTTP hoặc JMX nào? | management.endpoints.web.exposure.include/exclude và management.endpoints.jmx.exposure.include/exclude |
| Security | Ai được gọi endpoint đã expose? | Spring Security SecurityFilterChain, RequestMatcher và role/authority |

Cấu hình exposure không thay thế xác thực. Một endpoint đã expose vẫn cần được bảo vệ bằng network policy, firewall hoặc Spring Security nếu nó không dành cho truy cập công khai. Tương tự, cấp quyền cho một endpoint không tự động expose endpoint đó ra HTTP.

Khi sử dụng thuộc tính endpoint access, kiểm tra tài liệu đúng phiên bản Spring Boot đang chạy vì tên thuộc tính và khả năng điều khiển đã thay đổi giữa các dòng phiên bản. Với Spring Boot 3.5, tài liệu Actuator mô tả rõ exposure và cấu hình Spring Security ở phần Endpoints.

## 4. Bảo vệ Actuator bằng SecurityFilterChain

Nếu Spring Security có mặt và ứng dụng chưa tự khai báo SecurityFilterChain, Spring Boot tự cấu hình bảo vệ các actuator endpoint ngoài health. Khi ứng dụng tự khai báo bất kỳ SecurityFilterChain nào, cấu hình security actuator mặc định của Boot sẽ lùi lại. Khi đó, cần tự viết rule cho Actuator và cho các request còn lại của ứng dụng.

Ví dụ dưới đây dành cho Spring Boot 3.5 với ứng dụng Servlet/MVC. Chain đầu chỉ match Actuator; health được phép truy cập không cần đăng nhập, các endpoint còn lại yêu cầu role ACTUATOR_ADMIN. Chain thứ hai bảo vệ API và các route còn lại.

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().hasRole("ACTUATOR_ADMIN")
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

EndpointRequest.toAnyEndpoint() giới hạn chain đầu vào các actuator endpoint, còn EndpointRequest.to("health") match endpoint health và các subpath của nó. Role được khai báo bằng hasRole("ACTUATOR_ADMIN") tương ứng authority ROLE_ACTUATOR_ADMIN trong Spring Security.

Nếu dùng form login, OAuth2 Resource Server hoặc một cơ chế xác thực khác, thay httpBasic bằng cấu hình phù hợp với hệ thống. Nếu ứng dụng có nhiều chain, đặt @Order rõ ràng và kiểm tra request matcher của từng chain; chain đầu tiên khớp request sẽ quyết định rule được áp dụng.

Không bỏ qua chain của ứng dụng sau khi thêm chain cho Actuator. Nếu chỉ có chain actuator, request tới Spring Data REST như /api/orders có thể không còn được bảo vệ theo cấu hình mong muốn.

### 4.1. Ẩn health detail khỏi người dùng không có quyền

Có thể cho phép probe gọi health mà không cần credential, đồng thời chỉ hiển thị chi tiết cho người dùng đã được xác thực với role phù hợp:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: ACTUATOR_ADMIN
~~~

Giá trị thường dùng cho show-details và show-components:

- never: không trả chi tiết hoặc component.
- when-authorized: chỉ trả chi tiết khi người gọi có role được cấu hình.
- always: luôn trả chi tiết.

Giữ never hoặc when-authorized cho production. Chi tiết health có thể tiết lộ hostname, database, tên dịch vụ hoặc topology nội bộ. Nếu health endpoint được permitAll, người gọi ẩn danh chỉ nên nhận trạng thái tổng quát.

## 5. HealthIndicator tùy chỉnh cho thành phần nghiệp vụ

Spring Boot tự cấu hình một số HealthIndicator khi phát hiện dependency tương ứng, ví dụ DataSource health indicator khi có datasource. Có thể bổ sung health indicator cho thành phần đặc thù của ứng dụng bằng interface HealthIndicator.

Ví dụ kiểm tra một thành phần catalog:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class CatalogStoreHealthIndicator implements HealthIndicator {

    private final CatalogStore catalogStore;

    public CatalogStoreHealthIndicator(CatalogStore catalogStore) {
        this.catalogStore = catalogStore;
    }

    @Override
    public Health health() {
        boolean available = catalogStore.isAvailable();

        if (available) {
            return Health.up()
                    .withDetail("component", "catalog-store")
                    .build();
        }

        return Health.down()
                .withDetail("component", "catalog-store")
                .build();
    }
}
~~~

Tên bean tạo ra health component theo quy tắc đặt tên Spring; trong ví dụ, component có thể xuất hiện dưới tên catalogStore. Chỉ trả các detail cần thiết cho vận hành. Không đưa password, token, connection string hoặc dữ liệu nghiệp vụ vào health response.

Health check cần nhanh, có timeout và không tạo tải lớn. Tránh gọi một chuỗi API bên ngoài hoặc thực hiện truy vấn nặng mỗi lần probe. Nếu cần kiểm tra hệ thống phụ thuộc, xác định rõ kiểm tra đó thuộc readiness hay chỉ là tín hiệu monitoring.

## 6. Liveness và readiness cho triển khai container

Spring Boot cung cấp health group cho Kubernetes:

- /actuator/health/liveness cho biết process có còn hoạt động để tiếp tục chạy hay cần restart.
- /actuator/health/readiness cho biết instance đã sẵn sàng nhận traffic hay chưa.

Có thể bật rõ ràng các probe group:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db,catalogStore
~~~

Trong môi trường Kubernetes, các group probe được Spring Boot tự cấu hình khi phát hiện môi trường phù hợp; cấu hình probes.enabled giúp bật chủ động khi cần kiểm soát rõ ràng. Điều chỉnh danh sách include theo tên component thật của ứng dụng.

Không đưa database, broker hoặc dịch vụ bên ngoài vào liveness. Nếu database tạm thời lỗi mà liveness cũng DOWN, Kubernetes có thể restart hàng loạt instance và tạo ra sự cố dây chuyền. Readiness có thể kiểm tra dependency cần thiết để xử lý request; liveness nên phản ánh trạng thái bên trong process.

Ví dụ cấu hình probe:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
~~~

Nếu management port tách riêng bằng management.server.port, probe phải gọi đúng port đó. Cần cân nhắc thêm health group path trên application port nếu hạ tầng yêu cầu probe đánh giá cả đường phục vụ traffic thực tế.

## 7. Tách management port và giới hạn bề mặt mạng

Có thể tách Actuator khỏi cổng public của API:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Cổng riêng giúp áp dụng firewall, service network policy hoặc ingress riêng cho management traffic. Khi bind management.address vào loopback, chỉ tiến trình hoặc proxy cùng host có thể truy cập; hãy chắc rằng monitoring agent thực sự chạy ở vị trí có thể kết nối.

Nếu cần để Kubernetes probe truy cập qua management port, cấu hình port và network policy phù hợp. Không cho rằng tách port tự nó thay thế xác thực; nếu cổng có thể truy cập từ mạng, vẫn cần rule security.

## 8. Kiểm thử quyền truy cập và health response

Nên kiểm thử qua HTTP layer bằng MockMvc để xác nhận SecurityFilterChain, endpoint exposure và response thực tế.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ActuatorSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void healthIsPublic() throws Exception {
        mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
    }

    @Test
    void metricsRequiresActuatorAdmin() throws Exception {
        mockMvc.perform(get("/actuator/metrics"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "ACTUATOR_ADMIN")
    void actuatorAdminCanReadMetricsWhenExposed() throws Exception {
        mockMvc.perform(get("/actuator/metrics"))
                .andExpect(status().isOk());
    }
}
~~~

Ví dụ giả định endpoint metrics đã được expose trong cấu hình test. Nếu ứng dụng dùng xác thực khác HTTP Basic hoặc entry point trả 403 thay vì 401, điều chỉnh assertion theo security contract thực tế. Cần thêm spring-security-test vào test scope nếu dùng @WithMockUser.

Ngoài test trên, kiểm tra:

1. Health response không tiết lộ detail cho anonymous user.
2. Người có role ACTUATOR_ADMIN nhận được detail theo cấu hình.
3. Request repository như /api/orders vẫn đi qua chain bảo vệ ứng dụng.
4. Endpoint chưa expose trả 404 hoặc không được đăng ký theo cấu hình phiên bản, thay vì giả định security rule có thể mở nó.
5. Readiness chuyển DOWN khi dependency bắt buộc không sẵn sàng; liveness không DOWN chỉ vì dependency ngoài bị gián đoạn.
6. Khi management port tách riêng, kiểm thử health qua đúng port và path.

## 9. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| /actuator/health trả 404 | Thiếu Actuator dependency, endpoint bị vô hiệu hóa hoặc path/port sai | Kiểm tra starter, management base path, port và exposure |
| /actuator/metrics trả 404 | Metrics chưa được expose hoặc endpoint không có sẵn | Thêm metrics vào exposure.include; kiểm tra dependency registry nếu cần Prometheus |
| Nhận 401 hoặc 403 | SecurityFilterChain yêu cầu xác thực hoặc role không khớp | Kiểm tra matcher, authentication và ROLE_ACTUATOR_ADMIN |
| API Spring Data REST bất ngờ không còn bảo vệ | Chain tùy chỉnh cho Actuator làm Boot security auto-configuration lùi lại, nhưng chưa có chain cho ứng dụng | Thêm chain riêng cho application request và sắp xếp @Order |
| Health trả UP nhưng ứng dụng không nhận traffic | Readiness chưa phản ánh dependency hoặc startup state cần thiết | Kiểm tra health group readiness và probe path/port |
| Kubernetes liên tục restart instance khi database lỗi | Database bị đưa vào liveness | Chuyển dependency sang readiness hoặc monitoring riêng |
| Health detail không xuất hiện | show-details đang là never hoặc người gọi không có role được cấu hình | Kiểm tra show-details, health.roles và quyền của principal |
| Tách management port nhưng probe thất bại | Probe gọi nhầm port, bind address hoặc network policy | Kiểm tra management.server.port/address và cấu hình probe |
| Lộ thông tin nhạy cảm qua Actuator | Expose endpoint rộng hoặc show-details=always | Thu hẹp exposure, bảo vệ bằng Spring Security/network và ẩn detail |

## 10. Checklist triển khai

1. Thêm spring-boot-starter-actuator và xác nhận endpoint health hoạt động.
2. Giữ exposure ở mức cần thiết; không expose * trên mạng public.
3. Phân biệt exposure, endpoint access và authorization.
4. Nếu khai báo SecurityFilterChain, cấu hình cả actuator chain lẫn application chain.
5. Chỉ cho phép health công khai ở mức summary; giới hạn health detail bằng role.
6. Tạo HealthIndicator cho dependency đặc thù với timeout và detail an toàn.
7. Cấu hình liveness/readiness theo đúng mục đích; không đưa dependency ngoài vào liveness.
8. Nếu tách management port, cập nhật probe, firewall, monitoring và network policy.
9. Dùng MockMvc kiểm tra quyền anonymous, quyền admin và API nghiệp vụ.

## Tài liệu chính thức

- [Spring Boot 3.5 – Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot – Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot – Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
- [Spring Boot – Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Multiple SecurityFilterChain instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Data REST – Reference](https://docs.spring.io/spring-data/rest/reference/)
