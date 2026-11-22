# Bảo vệ Actuator, tài liệu API và các endpoint chẩn đoán

## 1. Vì sao endpoint vận hành cũng là bề mặt tấn công?

Trong ứng dụng Spring Boot, không chỉ API nghiệp vụ cần được bảo vệ. Một dịch vụ còn có thể công bố **Spring Boot Actuator** để giám sát, **OpenAPI/Swagger UI** để xem hợp đồng API, và những đường dẫn **chẩn đoán nội bộ** để kiểm trạng thái, tác vụ, cấu hình hay lỗi. Các đường dẫn này thường được nhóm phát triển sử dụng trong môi trường test, nhưng khi triển khai thật có thể vô tình đi qua ingress, reverse proxy, API gateway hoặc cổng quản trị mà không có kiểm soát.

Rủi ro không giới hạn ở việc “người lạ biết ứng dụng có những endpoint nào”. Một số đường dẫn có thể cho biết tên bean, cấu hình, mappings, logger, thông tin dependency, chi tiết health, stack trace, metrics, sự kiện HTTP hoặc cho phép **thay đổi trạng thái vận hành**. Tài liệu OpenAPI có thể bộc lộ các path/parameter nội bộ dù bản thân tài liệu không thể cấp quyền gọi chúng. Endpoint chẩn đoán tự viết có thể vô tình tạo thao tác reset cache, đổi cấu hình, chạy truy vấn hoặc truy xuất log.

Mục tiêu của bài trong nhóm **Triển khai** thuộc *Spring Security - fundamentals* là xây dựng chiến lược bảo vệ ba nhóm bề mặt này theo nhiều tầng:

1. **Không bật hoặc không expose những gì không cần**: giảm attack surface trước khi viết bất kỳ rule nào.
2. **Cấu hình HTTP security đúng**: health tối thiểu cho probes, role/authority cho management, docs và diagnostics; không giả định cấu hình mặc định còn giữ khi tự khai báo `SecurityFilterChain`.
3. **Giới hạn mạng và quyền vận hành**: management port, network policies, ingress, TLS, credentials/SSO, audit và quyền least privilege.
4. **Không để lộ dữ liệu nhạy cảm**: response body, health details, env values, log content, OpenAPI description và diagnostics.
5. **Kiểm thử thực tế**: anonymous/role khác/đúng role, đường dẫn chưa expose, CSRF, thay đổi cổng/path, ingress và production configuration.

**Nguyên tắc:** “Có authentication” chưa đủ. Một API ít ai biết nhưng được công khai, trả secrets hoặc cho phép thao tác nhạy cảm vẫn có rủi ro; một cổng management riêng mà ingress/network vẫn cho truy cập từ Internet cũng không an toàn.

## 2. Phân loại tài nguyên theo độ nhạy

| Nhóm | URL điển hình (tùy cấu hình) | Dữ liệu/chức năng | Mức mở hợp lý |
| --- | --- | --- | --- |
| Liveness/readiness | `/actuator/health/liveness`, `/actuator/health/readiness` | Tín hiệu health cho orchestrator | Chỉ thông tin tối thiểu; network/probe caller được phép |
| Health tổng | `/actuator/health` | Trạng thái UP/DOWN, có thể có component details | Có thể public status tối thiểu; **không** public details |
| Info | `/actuator/info` | Thông tin build/app nếu cấu hình | Chỉ OPS hoặc thông tin đã duyệt |
| Metrics/Prometheus | `/actuator/metrics`, `/actuator/prometheus` | Thông số runtime, tên tài nguyên, tags | Monitoring identity/network; không public rộng |
| Env/configprops/beans/mappings | `/actuator/env`, `/actuator/configprops`, `/actuator/beans`, `/actuator/mappings` | Cấu hình, cấu trúc bean, mappings, metadata | Tốt nhất không expose trong production thường ngày |
| Loggers/logfile/threaddump/heapdump | `/actuator/loggers`, `/actuator/logfile`, `/actuator/threaddump`, `/actuator/heapdump` | Log, stack, bộ nhớ, có thể chứa PII/secrets | Mặc định tắt; chỉ mở có kiểm soát nếu thực sự cần |
| Shutdown hoặc thao tác thay đổi | `/actuator/shutdown`, POST tới loggers hoặc endpoint custom | Thay trạng thái ứng dụng | Tắt trừ quy trình vận hành đặc biệt; nghiêm ngặt hơn GET |
| OpenAPI description | `/v3/api-docs`, `/v3/api-docs.yaml`, `/v3/api-docs/{group}` | Danh sách path, schemas, model, mô tả | Docs group/role hoặc tắt ở production |
| Swagger UI | `/swagger-ui.html`, `/swagger-ui/**` | Giao diện duyệt API và thử gọi API | Docs group/role, không công khai nhầm |
| Diagnostics tự viết | `/internal/diagnostics/**`, `/debug/**`, `/admin/**` | Trạng thái, thao tác hỗ trợ, thông tin nội bộ | OPS + network restriction; bỏ khỏi production nếu không cần |

**Không có nhãn “chẩn đoán” nào tự tạo security boundary.** `/internal`, `/admin`, `/debug` hoặc đường dẫn dài khó đoán vẫn là HTTP endpoint bình thường cho tới khi filter chain và mạng thực sự hạn chế truy cập.

**Đừng nhầm công bố tài liệu với cấp quyền cho API.** Swagger UI chỉ là client/documentation; backend endpoint vẫn phải có authentication, authorization và object-level checks độc lập. Ẩn một route khỏi OpenAPI không chặn việc gọi route đó.

## 3. Ba cổng quyết định Actuator có truy cập được hay không

Trong Spring Boot 3.5, cần phân biệt ba khái niệm khác nhau trước khi bảo vệ Actuator:

1. **Endpoint access/availability**: thuộc tính `management.endpoint.<id>.access`, `management.endpoints.access.default` và `management.endpoints.access.max-permitted` điều khiển endpoint/operation được phép hiện diện. Giá trị có thể là `none`, `read-only` hoặc `unrestricted` theo loại endpoint. Khi access là `none`, endpoint không còn khả dụng trong application context.
2. **Exposure**: `management.endpoints.web.exposure.include` và `exclude` quyết định endpoint khả dụng nào được đưa ra HTTP. JMX có exposure riêng. Một endpoint không expose qua HTTP không thể được mở lại chỉ bằng `permitAll()`.
3. **HTTP authorization**: Spring Security `SecurityFilterChain` quyết định request đã tới HTTP endpoint cần anonymous/authentication/role nào. Exposure **không thay thế** authorization.

```text
Actuator được gọi qua HTTP
  |
  +-- Endpoint có access khác none? -- Không --> không khả dụng
  |
  +-- ID nằm trong web.exposure.include
  |   và không nằm trong exclude? ------ Không --> không có HTTP handler
  |
  +-- Request qua đúng SecurityFilterChain?
  |      |
  |      +-- health tối thiểu / probe --> cho caller hợp lệ
  |      +-- metrics/info ----------- cần quyền OPS
  |      +-- còn lại -------------- từ chối
  |
  +-- Network / ingress / firewall có cho phép kết nối?
         |
         +-- Không --> chặn ở lớp mạng
         +-- Có ----> HTTP security vẫn phải kiểm quyền
```

**Mặc định quan trọng:** Spring Boot 3.5 chỉ expose `health` qua HTTP/JMX theo cấu hình mặc định, các endpoint khác không tự động xuất hiện chỉ vì thêm starter. Nếu Spring Security có trên classpath **và không có `SecurityFilterChain` do ứng dụng định nghĩa**, Boot có thể tự cấu hình bảo vệ phần lớn Actuator (ngoại trừ health). **Khi bạn định nghĩa một `SecurityFilterChain` custom, Boot back off khỏi cấu hình Actuator security tự động; bạn phải tự bảo vệ các endpoint đó.** Đây là nguồn sai sót phổ biến khi thêm một rule `permitAll()` cho API công khai rồi vô tình bỏ Actuator.

**Cảnh báo về phiên bản:** `management.endpoints.access.*` là API/property có trong dòng Boot 3.5. Khi bảo trì Boot cũ hoặc nâng lên Boot 4, hãy đối chiếu reference của phiên bản cụ thể; không sao chép package import/property mà không kiểm phiên bản.

## 4. Mẫu triển khai production: mặc định không mở rộng

Một cấu hình hạn chế cho môi trường production có thể là:

```yaml
management:
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,info,metrics"
  endpoint:
    health:
      access: read-only
      show-details: never
      show-components: never
      probes:
        enabled: true
    info:
      access: read-only
    metrics:
      access: read-only
```

Ý nghĩa:

- Mặc định **không cho phép các endpoint chưa liệt kê**. Chỉ health, info, metrics được cấp read-only access; chỉ ba ID ấy được expose qua HTTP.
- `max-permitted: read-only` làm trần quyền access; ngay cả khi một endpoint được đổi sang unrestricted ở nơi khác, cấu hình trần vẫn giới hạn các thao tác ghi. Dù vậy không dựa riêng vào property này để bảo vệ môi trường production.
- `health.show-details: never` và `show-components: never` không hiển thị chi tiết health indicator cho người gọi thông thường. Với hệ thống cần xem sâu hơn, dùng group/quyền/đường quản trị riêng và kiểm response thực tế.
- `probes.enabled: true` bật liveness/readiness paths trong môi trường không tự nhận Kubernetes. Khi chạy trên Kubernetes, Spring Boot có thể tự bật probes.
- `info` và `metrics` vẫn cần authentication/authorization và giới hạn mạng ở lớp khác.

Nếu dùng YAML `include: "*"`, nhớ **đặt dấu nháy** vì `*` là cú pháp đặc biệt của YAML. Trong production, tránh cấu hình rộng `management.endpoints.web.exposure.include=*` rồi cố dùng một danh sách `exclude` ngắn để bảo vệ, vì endpoint mới trong tương lai sẽ mặc nhiên được expose.

**Lưu ý theo môi trường:** cấu hình minh họa này không mở `prometheus`. Nếu thực sự scrape Prometheus, thêm dependency registry phù hợp, thêm `prometheus` vào access và exposure, rồi bảo vệ bằng service account/monitoring network; không tự mặc định mọi pod hoặc mọi Internet client được scrape.

## 5. Ví dụ chạy được: Spring Boot 3.5, Actuator, OpenAPI và diagnostics

Ví dụ dưới dùng **Java 17+, Maven, Spring Boot 3.5.16, Spring Security 6.x, Actuator và springdoc-openapi 2.10.0**. springdoc 2.x phù hợp với Boot 3.x; phiên bản 2.10.x tương thích Boot 3.5.x theo ma trận của dự án. Khi áp dụng vào hệ thống khác, kiểm lại các phiên bản đã được tổ chức phê duyệt.

Yêu cầu demo:

- Anonymous được đọc `GET /api/public` và `GET /actuator/health` (chỉ trạng thái tối thiểu).
- `GET /actuator/metrics` và `/actuator/info` chỉ dành cho `ROLE_OPS`.
- OpenAPI JSON và Swagger UI chỉ dành cho `ROLE_DOCS` hoặc OPS đã được gán DOCS.
- `GET /internal/diagnostics/ping` chỉ dành cho OPS, trả nội dung ngắn đã duyệt, không đọc env/log/secret.
- `/actuator/env` và các endpoint nguy hiểm khác **không expose**.
- Các route còn lại bị từ chối mặc định.

Cấu trúc:

```text
management-security-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/ManagementSecurityApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/demo/ManagementSecurityTests.java
```

### 5.1. Maven `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>management-security-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
            <version>2.10.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là dự án Maven độc lập với **đầy đủ wrapper `<plugin>...</plugin>`**. Starter Actuator thêm các endpoints và HTTP integration; springdoc tạo OpenAPI JSON cùng Swagger UI; Spring Security cấp `HttpSecurity`/filter chain; test dependencies có MockMvc và Spring Security Test.

### 5.2. `src/main/resources/application.yml`

```yaml
server:
  port: 8080

management:
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,info,metrics"
      discovery:
        enabled: false
  endpoint:
    health:
      access: read-only
      show-details: never
      show-components: never
      probes:
        enabled: true
    info:
      access: read-only
    metrics:
      access: read-only

springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
```

**Vì sao tắt Actuator discovery?** Endpoint link discovery `/actuator` thường liệt kê các Actuator endpoints đã expose. Trong demo, `management.endpoints.web.discovery.enabled=false` giảm phần thông tin liên kết được trả về. Điều này **không** thay security cho các đường `/actuator/health`, `/actuator/metrics` hoặc bất kỳ đường nào khác. Chính sách truy cập vẫn phụ thuộc exposure, access, filter chain và network.

**Vì sao bật swagger trong demo?** Để kiểm rule cấp tài liệu bằng role. Trong một hệ thống production không cần UI, có thể tắt hẳn `springdoc.api-docs.enabled=false` và `springdoc.swagger-ui.enabled=false` bằng profile/config; vẫn cần kiểm gateway không định tuyến tài liệu ở route khác.

### 5.3. `src/main/java/demo/ManagementSecurityApplication.java`

```java
package demo;

import java.util.Map;

import io.swagger.v3.oas.annotations.Hidden;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ManagementSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ManagementSecurityApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("viewer")
                        .password(encoder.encode("viewer-pass"))
                        .roles("USER")
                        .build(),
                User.withUsername("docs")
                        .password(encoder.encode("docs-pass"))
                        .roles("DOCS")
                        .build(),
                User.withUsername("ops")
                        .password(encoder.encode("ops-pass"))
                        .roles("OPS", "DOCS")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        // Chỉ health tối thiểu cho probe / anonymous.
                        .requestMatchers(EndpointRequest.to("health"))
                            .permitAll()

                        // Các Actuator endpoint đã được expose
                        // bắt buộc có ROLE_OPS.
                        .requestMatchers(EndpointRequest.toAnyEndpoint())
                            .hasRole("OPS")

                        // Fallback Actuator path cho discovery/unknown URL
                        // của demo; áp dụng kể cả khi endpoint không expose.
                        .requestMatchers("/actuator", "/actuator/**")
                            .hasRole("OPS")

                        // OpenAPI JSON, YAML và tài nguyên Swagger UI.
                        .requestMatchers(
                                "/v3/api-docs",
                                "/v3/api-docs/**",
                                "/v3/api-docs.yaml",
                                "/swagger-ui.html",
                                "/swagger-ui/**")
                            .hasRole("DOCS")

                        // Mọi diagnostic route phải khai báo riêng.
                        .requestMatchers("/internal/diagnostics/**")
                            .hasRole("OPS")

                        // Public business endpoint duy nhất của demo.
                        .requestMatchers("/api/public").permitAll()

                        // Không cho đường mới tự công khai.
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @RestController
    static class PublicController {
        @GetMapping("/api/public")
        Map<String, String> publicApi() {
            return Map.of("message", "public");
        }
    }

    @Hidden // Chỉ ẩn khỏi OpenAPI, KHÔNG thay authorization.
    @RestController
    static class DiagnosticController {
        @GetMapping("/internal/diagnostics/ping")
        Map<String, String> ping(Authentication authentication) {
            return Map.of("state", "ok");
        }
    }
}
```

#### Vì sao ví dụ dùng một `SecurityFilterChain`?

Với ứng dụng demo chạy chung cổng 8080, **một chain có thứ tự rõ ràng** làm bài học dễ kiểm tra:

- `EndpointRequest.to("health")` là matcher được Boot cung cấp, dựa trên Actuator endpoint chứ không chỉ một chuỗi hard-code. Nó có thể match health và các subpath của health; vì vậy giữ `show-details=never`, giới hạn health groups và kiểm thực tế. Nếu chỉ muốn public path chính xác, viết matcher riêng cho path/probe được duyệt và kiểm base path khi thay đổi.
- `EndpointRequest.toAnyEndpoint()` yêu cầu OPS với các endpoint Actuator hiện có. Fallback `/actuator/**` trong demo còn chặn việc anonymous tùy ý dò đường dẫn gần giống; nhưng nó không khiến một endpoint chưa expose đột nhiên hoạt động.
- Docs và Swagger UI có matcher **riêng**. Một người có `ROLE_OPS` trong demo cũng có `ROLE_DOCS` do được cấp cả hai lúc seed; role OPS không tự bao hàm role DOCS theo mặc định.
- `/internal/diagnostics/**` phải có OPS; controller trả đúng một giá trị vô hại. Không trả environment variables, stack trace, keys, request headers hoặc user data.
- `anyRequest().denyAll()` để một URL mới không được tự mở.
- Spring Boot back off khỏi Actuator security auto-configuration khi ứng dụng định nghĩa custom chain; chính bean này chịu trách nhiệm bảo vệ.

**Lưu ý về `@Hidden`:** annotation của OpenAPI giúp không đưa diagnostics vào tài liệu được sinh. Đây chỉ là **giảm khả năng tiết lộ qua docs**, không phải quyền truy cập. Bỏ `@Hidden` thì role OPS và network restrictions vẫn phải bảo vệ endpoint. Không làm ngược lại: dựa trên việc path không hiển thị để cho phép anonymous gọi.

**Lưu ý về user store:** ba mật khẩu trong bài chỉ để chạy local. Production không hard-code credentials, không dùng in-memory users cho vận hành, cần secret manager/identity provider, TLS, rate limiting, multi-factor cho nhóm đặc quyền khi phù hợp và audit có kiểm soát. Basic Auth phải đi qua HTTPS nếu dùng ngoài localhost.

### 5.4. Không nhầm `SecurityFilterChain` với việc bật endpoint

Dù OPS đã xác thực, `GET /actuator/env` vẫn **không có handler** trong demo, vì `env` không được cấp access và không nằm trong exposure. Kết quả dự kiến với OPS là **404**, không phải 200. Khi anonymous gọi một đường chưa expose nhưng khớp fallback security matcher, có thể nhận 401/403 **trước khi** đến bước kết luận HTTP handler không tồn tại; muốn xác nhận endpoint thực sự không expose, hãy gửi một request đã được cấp OPS hoặc kiểm endpoint mappings/config. Đừng kết luận chỉ dựa trên một status code từ anonymous.

Nếu đổi `management.endpoints.web.base-path`, đường cứng `/actuator/**` không còn bao trùm base path mới; `EndpointRequest` giúp tránh lệ thuộc một path cố định cho các endpoint do Actuator đăng ký. Với docs, nếu đổi `springdoc.api-docs.path` hoặc Swagger UI custom path, phải sửa request matchers và tests tương ứng.

## 6. Kiểm thử bằng Spring Security Test và MockMvc

Tạo `src/test/java/demo/ManagementSecurityTests.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class ManagementSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiIsAvailableAnonymously() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void healthIsPublicButLimited() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").exists())
                .andExpect(jsonPath("$.components").doesNotExist());
    }

    @Test
    void metricsRequiresOps() throws Exception {
        mvc.perform(get("/actuator/metrics"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/actuator/metrics")
                        .with(httpBasic("viewer", "viewer-pass")))
                .andExpect(status().isForbidden());

        mvc.perform(get("/actuator/metrics")
                        .with(httpBasic("ops", "ops-pass")))
                .andExpect(status().isOk());
    }

    @Test
    void unexposedEnvironmentStaysUnavailable() throws Exception {
        mvc.perform(get("/actuator/env")
                        .with(httpBasic("ops", "ops-pass")))
                .andExpect(status().isNotFound());
    }

    @Test
    void openApiRequiresDocsRole() throws Exception {
        mvc.perform(get("/v3/api-docs"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/v3/api-docs")
                        .with(httpBasic("viewer", "viewer-pass")))
                .andExpect(status().isForbidden());

        mvc.perform(get("/v3/api-docs")
                        .with(httpBasic("docs", "docs-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.openapi").exists());
    }

    @Test
    void diagnosticsAreOpsOnly() throws Exception {
        mvc.perform(get("/internal/diagnostics/ping"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/internal/diagnostics/ping")
                        .with(httpBasic("docs", "docs-pass")))
                .andExpect(status().isForbidden());

        mvc.perform(get("/internal/diagnostics/ping")
                        .with(httpBasic("ops", "ops-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("ok"));
    }
}
```

**Điểm cần kiểm trước khi coi test là bằng chứng:**

- `@AutoConfigureMockMvc(addFilters=true)` cần giữ Spring Security filters; `addFilters=false` có thể làm test authorization không còn giá trị.
- `httpBasic(...)` đặt credentials vào request và đi qua provider của test application context; **không** dùng `@WithMockUser` cho các test đang muốn kiểm mật khẩu.
- 401 = chưa có credentials hợp lệ, 403 = đã xác thực nhưng thiếu role (trong cấu hình Basic API này); các hệ thống dùng form login thường redirect 302 thay vì 401.
- Test `/actuator/env` dùng OPS để xác nhận 404 **sau khi vượt qua lớp role**; nếu chỉ anonymous, status 401 không đủ kết luận endpoint đã tắt.
- Test `/v3/api-docs` xác minh cả JSON OpenAPI thực sự được sinh và không thể truy cập bởi USER. Thêm test `/v3/api-docs.yaml` và `/swagger-ui/index.html` khi sử dụng các route đó trong deployment; nếu đổi path phải cập nhật test.
- Nếu docs library không khả dụng hoặc phiên bản không tương thích, test OpenAPI sẽ fail; không được “sửa” bằng `permitAll("/**")`. Kiểm dependency, base path và Spring Security matcher.

### Kiểm thử thủ công

Từ thư mục chứa `pom.xml`:

```bash
mvn -q test
mvn -q -DskipTests package
java -jar target/management-security-demo-0.0.1-SNAPSHOT.jar
```

Terminal khác:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i -u viewer:viewer-pass http://localhost:8080/actuator/metrics
curl -i -u ops:ops-pass http://localhost:8080/actuator/metrics
curl -i -u ops:ops-pass http://localhost:8080/actuator/env
curl -i http://localhost:8080/v3/api-docs
curl -i -u docs:docs-pass http://localhost:8080/v3/api-docs
curl -i -u docs:docs-pass http://localhost:8080/internal/diagnostics/ping
curl -i -u ops:ops-pass http://localhost:8080/internal/diagnostics/ping
```

Status mong đợi lần lượt: **200, 200, 401, 403, 200, 404, 401, 200, 403, 200**. `/actuator/health` trả ít nhất `{"status":"UP"}` khi các health indicators của demo đều ổn; giá trị health có thể thay đổi theo runtime, nên test tự động chỉ xác nhận field `status` tồn tại và không có `components`. `/internal/diagnostics/ping` chỉ trả:

```json
{
  "state": "ok"
}
```

Khi vào `http://localhost:8080/swagger-ui/index.html` bằng browser, HTTP Basic có thể yêu cầu nhập credentials docs/ops. Giao diện Swagger UI cũng cần tải JSON config, mô tả OpenAPI và các tài nguyên tĩnh nên chỉ bảo vệ một file `swagger-ui.html` là chưa đủ.

**Không được tuyên bố những lệnh này đã chạy thành công nếu bạn chưa thực thi chúng**; các status là kết quả dự kiến với đúng code/config nêu trên. Nếu kết quả khác, kiểm Spring Boot/springdoc version, management exposure và filter mapping thay vì tự mở public để làm pass.

## 7. Bảo vệ tài liệu OpenAPI và Swagger UI trong ứng dụng thật

OpenAPI/Swagger UI có giá trị cho developer nhưng mang rủi ro nhận diện bề mặt API và lộ ví dụ payload, schemas, error model, hidden/internal endpoints, mô tả role/permissions hoặc server URL. Cần ba lớp bảo vệ:

### 7.1. Route và asset đều được kiểm soát

Với springdoc-openapi trên Spring MVC, các path phổ biến:

- `/v3/api-docs` và `/v3/api-docs.yaml`: dữ liệu mô tả API.
- `/v3/api-docs/{group}`: nếu dùng grouped OpenAPI.
- `/swagger-ui.html`: entry path/redirect.
- `/swagger-ui/**`: trang, JS/CSS và các tài nguyên liên quan.

Nếu đổi path theo cấu hình springdoc hoặc triển khai qua context path/gateway, matcher phải khớp **path thực sau routing**. Tối thiểu phải test anonymous, user không có quyền docs và người có quyền docs cho **cả JSON và UI**. Bảo vệ JS/CSS riêng không thay quyền truy cập spec JSON; ngược lại, chặn spec nhưng public UI cũng không phải một thiết kế có kiểm soát nhất quán.

### 7.2. Tắt hoàn toàn khi không cần

Ở production không cho phép docs online, cân nhắc:

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
```

Đây là một **profile/config thay thế** cho các dòng `enabled: true` trong demo, không được dán đè thành hai block mâu thuẫn. Khi tắt, kiểm bằng HTTP test rằng docs và UI không còn handler và gateway/CDN không cache bản cũ. Việc tắt OpenAPI không ngăn backend API hoạt động; các endpoint vẫn cần security policy riêng.

### 7.3. Swagger UI không tự cấp quyền backend

Ngay cả khi Swagger UI chỉ mở cho DOCS, nút “Try it out” vẫn gửi HTTP request tới API và phải tuân thủ quyền của identity/token dùng cho request đó. Cấu hình OpenAPI security scheme chỉ mô tả kiểu credentials cho tài liệu, không thực hiện authentication/authorization thay Spring Security. Với OAuth2 trong Swagger UI, bảo vệ client IDs/secrets và redirect URI; không gắn token production, refresh token hay secrets vào static config, logs hoặc ví dụ JSON.

**Không dùng `@Hidden` để thay việc chặn một route.** Annotation chỉ quyết định tài liệu có liệt kê endpoint hay không. Bất kỳ người dùng nào biết URL vẫn có thể gửi HTTP request trực tiếp; Spring Security và service policy mới quyết định kết quả.

## 8. Management port, ingress và network policy

Đưa Actuator ra cổng management riêng có thể hữu ích:

```yaml
server:
  port: 8080

management:
  server:
    port: 9001
    address: 127.0.0.1
```

Đây là **một biến thể deployment**, không phải phần cấu hình của ví dụ chạy chung cổng ở mục 5. Khi port management khác port ứng dụng, `management.server.address` có thể giới hạn interface lắng nghe. `127.0.0.1` chỉ phù hợp khi monitoring agent cùng network namespace/host truy cập được loopback; với container/Kubernetes, probe từ kubelet hoặc service monitoring bên ngoài có thể **không** truy cập được. Thay bằng binding và NetworkPolicy/firewall phù hợp với kiến trúc thực, không copy localhost một cách máy móc.

Một cổng riêng là **phân tách hạ tầng**, chưa phải phân quyền:

- Chặn management port ở load balancer/ingress công khai, security group và firewall.
- Chỉ cho phép nguồn monitoring/operations đã xác định.
- Có TLS/mTLS, service identity hoặc SSO phù hợp khi request đi qua mạng có thể bị nghe trộm.
- Không tạo rule gateway như `/actuator/** -> public`, không lộ đường thông qua alternate hostname, direct node IP hoặc service mesh route.
- Kiểm xem management endpoints dùng context/HTTP security chain nào trên **cổng riêng**. Test trên port 8080 không chứng minh cổng 9001 cũng an toàn. Khi đổi management port hoặc tạo management context riêng, chạy thêm integration/network tests đúng cổng và kiểm mọi filter/security bean thực sự áp dụng.
- Cân nhắc tắt HTTP management exposure hoàn toàn nếu chỉ dùng JMX hoặc agent đặc thù; JMX cũng có security/network configuration riêng.

**Cảnh báo về health trên cổng riêng:** đôi khi management server khỏe trong khi main connector bị lỗi; do đó Kubernetes liveness/readiness chỉ trên management port có thể không phát hiện mọi lỗi phục vụ HTTP chính. Spring Boot cung cấp tùy chọn bổ sung đường health probes trên main server port để cải thiện tính đại diện, ví dụ `management.endpoint.health.probes.add-additional-paths=true` (tạo `/livez`, `/readyz` theo cấu hình). Khi bật, phải kiểm **security và exposure của cả hai cổng**.

## 9. Health/liveness/readiness: cho probe hoạt động mà không lộ dữ liệu

Một health endpoint thường phải trả thông tin đủ để orchestrator quyết định routing/restart, không phải để người ngoài xem môi trường và cấu trúc hệ thống.

**Phân biệt:**

- **Liveness:** process có còn khả năng sống/tiếp tục hoạt động không? Đừng gắn mọi phụ thuộc bên ngoài vào liveness, kẻo lỗi DB chung làm orchestrator restart hàng loạt instance.
- **Readiness:** instance hiện có nên nhận traffic không? Có thể xét phụ thuộc thiết yếu theo chiến lược ứng dụng.
- **Health tổng:** thường chứa nhiều indicators hơn; nếu public phải tránh details và component names.

Ví dụ Spring Boot khi bật probes:

```text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
```

Không giả định health luôn **200**: một component DOWN có thể làm endpoint trả status HTTP phù hợp như 503. Bộ test bảo mật nên phân biệt **được truy cập không bị yêu cầu login** với **health hệ thống thật UP/DOWN**. Nếu dùng role để bảo vệ health details, chú ý `management.endpoint.health.show-details=when-authorized` và `management.endpoint.health.roles` là một lớp policy **cho chi tiết health**, không thay security filter cho các URL khác.

Khi health response thay đổi theo profile/Kubernetes, xác minh rằng các fields chứa URI, hostnames, dependency names, message/stack trace không được công bố cho anonymous. `show-details=always` là một lựa chọn nguy hiểm nếu health endpoint public.

## 10. Metrics và logging: giá trị chẩn đoán cũng có thể nhạy cảm

Metrics thường chứa tên application, routes, status codes, cache names, database pools và tags. Nếu labels được tạo từ user ID, token, email, raw URI hoặc request query, metrics có thể trở thành nơi lộ dữ liệu hoặc tạo cardinality bùng nổ. Không tạo tag từ thông tin nhạy cảm chưa được chuẩn hóa; bảo vệ monitoring endpoint và backend lưu trữ metrics.

Các endpoint cần đặc biệt thận trọng:

- `/actuator/env`, `/actuator/configprops`: có cơ chế sanitize giá trị nhạy cảm, nhưng **sanitization không phải lời bảo đảm** không thể suy luận cấu hình hoặc để lộ metadata. Đừng bật `show-values=always` trên môi trường công khai.
- `/actuator/beans`, `/actuator/conditions`, `/actuator/mappings`: giúp reconnaissance về kiến trúc, tên bean và URL.
- `/actuator/logfile`, `/actuator/httpexchanges`: có thể chứa request paths, headers, user information, lỗi và dữ liệu vận hành. Đừng log raw Authorization, cookies hoặc payloads riêng tư.
- `/actuator/threaddump` và `/actuator/heapdump`: có thể mang dữ liệu cực nhạy cảm như token/secret trong bộ nhớ; kiểm cả khả năng tải file lớn và đường lưu artifact.
- `/actuator/loggers`: có thể cho phép điều chỉnh log level; việc bật DEBUG/TRACE quá rộng làm tăng rủi ro lộ dữ liệu, tải hệ thống và chi phí log.
- `/actuator/shutdown` và endpoint ghi custom: thay đổi trạng thái, không nên bật chỉ để thử nghiệm.

Spring Boot 3.5 cho phép giới hạn access `read-only` và đặt `max-permitted`, nhưng vẫn phải kiểm chức năng cụ thể của endpoint, mạng và role. Những endpoint nguy hiểm có thể mặc định bị disabled; đừng tự mở chúng trong production để chạy một lệnh chẩn đoán nhất thời mà không có quy trình đóng lại.

**Khuyến nghị thực tế:** khi cần chẩn đoán sâu cho sự cố, dùng workflow break-glass có phê duyệt, thời hạn, audit và khả năng rollback; đừng lưu lâu một `ROLE_ADMIN` dùng chung trên endpoint xuất Internet.

## 11. Custom diagnostics: thiết kế an toàn hơn từ đầu

Nếu bắt buộc tạo endpoint riêng như `GET /internal/diagnostics/ping`:

1. **Chỉ trả dữ liệu tối thiểu:** state/latency tổng hợp hoặc mã tình trạng không chứa hostnames, SQL, stack traces, request headers, secrets, user IDs.
2. **Không gộp read và write:** hoạt động đọc trạng thái và thay đổi trạng thái phải là endpoint/HTTP method riêng, với permission hạt mịn và audit. Không tạo `GET /debug/clear-cache` có side effect.
3. **Đặt policy ở cả HTTP và service:** route cần OPS, service action còn cần environment, tenant hoặc approval theo nghiệp vụ; background job không được bypass invariant.
4. **Rate limit và timeout:** diagnostic query có thể nặng, làm cạn thread/connection pool hoặc tăng tải DB; dùng bounds, pagination và async job có kiểm soát khi phù hợp.
5. **Định dạng response:** dùng response DTO allowlist và error handling không leak stacktrace; tránh trả raw `Exception.toString()` hoặc `System.getenv()`.
6. **Audit có kiểm soát:** ghi actor đã xác minh, action, resource và result, không dump token, cookie hoặc mật khẩu.
7. **Feature flag/environment:** route không cần ở production thì đừng register nó, hoặc chặn access theo profile bằng cấu hình có kiểm thử. Chỉ đổi tên `/debug` thành `/private` không giải quyết rủi ro.

### Ví dụ phản-pattern: không sao chép

```java
@GetMapping("/debug/config")
Map<String, String> debugConfig() {
    return System.getenv(); // Không đưa toàn bộ ENV ra HTTP!
}
```

Đây là **phản ví dụ** để nhận diện lỗi, không phải phần của ứng dụng runnable mục 5. `System.getenv()` có thể chứa database credentials, cloud tokens và secrets. Không làm dịu bằng cách “chỉ bật khi có role USER”; nếu thực sự cần tra trạng thái cấu hình, xây DTO chỉ có thông tin đã duyệt và yêu cầu OPS/secure network.

## 12. CSRF, CORS và method của các endpoint quản trị

**CSRF:** Spring Security bảo vệ unsafe HTTP methods theo cấu hình mặc định. Nếu mở endpoint ghi như `loggers`, `shutdown` hoặc custom POST/PUT/DELETE, request có credentials hợp lệ vẫn có thể nhận **403 vì thiếu CSRF token**. Đừng giải quyết bằng cách `csrf.disable()` trên toàn ứng dụng chỉ để Postman/curl thao tác thành công. Thiết kế cơ chế credentials: browser cookie/Basic có nguy cơ tự gửi credentials; bearer-only API có mô hình khác. Nếu thực sự cần miễn trừ CSRF cho một nhóm management client không dựa vào browser, giới hạn matcher rất hẹp, dùng authentication, network và audit phù hợp, rồi viết negative tests.

**CORS:** trình duyệt thực thi CORS, nhưng không thực hiện authentication thay backend. Actuator có cấu hình CORS riêng như `management.endpoints.web.cors.allowed-origins`; chỉ bật nếu cần client từ origin được tin cậy, tránh wildcard kèm credentials. CLI curl vẫn có thể gửi HTTP dù browser CORS chặn; do đó CORS không phải firewall.

**HTTP methods:** chọn GET/HEAD cho read-only operations, POST/PUT/DELETE cho thay đổi có kiểm soát. Property `management.endpoints.access.max-permitted=read-only` giúp hạn chế các Actuator write operations ở cấp ứng dụng, nhưng các custom controllers như `/internal/**` không tự chịu giới hạn đó; chúng vẫn cần rule riêng.

**Response caching:** health, metrics, docs và diagnostics có thể thay đổi liên tục hoặc chứa thông tin riêng. Cân nhắc `Cache-Control` và proxy/CDN caching theo audience; một response docs/diagnostics đã bị cache public có thể tiếp tục tồn tại ngay cả sau khi sửa security rule.

## 13. Giữ bảo vệ khi thay đổi đường dẫn hoặc framework

Có vài tình huống cần rà lại matcher:

- Đổi `management.endpoints.web.base-path` từ `/actuator` sang `/manage`: một rule hard-code `/actuator/**` có thể bỏ sót; `EndpointRequest` cho Actuator endpoints giúp giảm rủi ro. Test URL thực sau đổi path.
- Có nhiều `SecurityFilterChain`: chain có `@Order` ưu tiên và `securityMatcher` riêng. Nếu chain management chỉ match Actuator, vẫn cần chain khác bao phủ business API/docs/diagnostics. **Không để đường rơi ra ngoài mọi chain.**
- Dùng management port riêng: phải kiểm chain/context và ingress trên **port quản trị**, không chỉ app port.
- Spring MVC → WebFlux: dùng `SecurityWebFilterChain`, `ServerHttpSecurity` và reactive Actuator matcher thay cho servlet `HttpSecurity` và `EndpointRequest` package servlet. Đừng gắn servlet filter vào Netty WebFlux.
- Dùng springdoc grouped API, custom Swagger UI path hoặc API gateway rewrite: cập nhật matcher cho `/v3/api-docs/**`, YAML, UI assets, redirect và config URLs. Đường đi bên ngoài và đường vào Servlet có thể khác nhau.
- Spring Boot 3 → Boot 4: package auto-configuration và dependencies có thể đổi; nạp tài liệu theo version, không copy import mà không compile/test.

**Lỗi phổ biến:** một chain chỉ có `.securityMatcher(EndpointRequest.toAnyEndpoint())` bảo vệ Actuator nhưng không có chain ứng dụng khác. Spring Boot docs nhắc rằng khi đã tự khai báo custom chain, default security backing off; đừng ngầm cho rằng API còn được bảo vệ.

## 14. Kiểm thử theo từng lớp bảo vệ

### Ma trận API/role

| Request | Anonymous | ROLE_USER | ROLE_DOCS | ROLE_OPS (được seed thêm DOCS) |
| --- | --- | --- | --- | --- |
| `GET /api/public` | 200 | 200 | 200 | 200 |
| `GET /actuator/health` | 200 nếu health UP | 200 | 200 | 200 |
| `GET /actuator/metrics` | 401 | 403 | 403 | 200 |
| `GET /actuator/env` | 401 do fallback | 403 do fallback | 403 do fallback | 404 chưa expose |
| `GET /v3/api-docs` | 401 | 403 | 200 | 200 |
| `GET /internal/diagnostics/ping` | 401 | 403 | 403 | 200 |

Bảng này là **kỳ vọng cho cấu hình demo** khi endpoint health UP; nó không là quy tắc chung của mọi Spring Security deployment. Status 401 có thể là 302 trong form login, hoặc 404 thay 401 nếu gateway chặn route trước khi request tới ứng dụng.

### Bộ test deployment bổ sung

- **Endpoint inventory:** xác nhận URL nào thực sự được expose, không chỉ những URL được ghi trong tài liệu.
- **Custom security regression:** thêm một `SecurityFilterChain` và chạy lại test Actuator; kiểm Boot auto-configuration backoff không làm lộ.
- **Multiple chains/path rewrites:** thay base path, management port, context path, API gateway prefix và nhóm OpenAPI.
- **Management network:** từ nguồn public Internet không kết nối được cổng 9001; monitoring agent được phép truy cập. Test các route qua ingress và direct pod/node nếu phù hợp.
- **Secrets:** `env/configprops/heapdump/logfile` không được expose; Swagger spec không chứa secret/example nhạy cảm; diagnostics không leak error stack.
- **Health details:** public chỉ thấy status; probes hoạt động mà không lộ tên dependency; trạng thái DOWN/OUT_OF_SERVICE được trả phù hợp.
- **Write methods:** thiếu role/CSRF hoặc access `read-only` phải chặn thay đổi logger/shutdown, có audit với thao tác được phép.
- **Token/SSO:** nếu thay Basic bằng OAuth2/JWT, kiểm token hợp lệ, expired, signature sai, issuer/audience sai, scope thiếu và service-account permission.
- **Monitoring:** scrape endpoint thành công với identity và network được phép; labels không chứa user IDs, tokens hoặc query nhạy cảm.

Mỗi lần kiểm thử cần ghi rõ **phạm vi**. `MockMvc` kiểm filter, handler trong Spring test context nhưng không chứng minh firewall/ingress/TLS production. `@WithMockUser` cấp principal giả, không kiểm password. Khi cần kiểm mạng, dùng HTTP client tới cổng thực; khi cần kiểm browser/CORS, dùng Playwright/Selenium qua origin thật.

## 15. Những lỗi triển khai thường gặp

1. **Expose tất cả Actuator:** `management.endpoints.web.exposure.include=*` mở rộng bề mặt không cần thiết, đặc biệt khi không có network policy.
2. **Định nghĩa custom `SecurityFilterChain` nhưng tin Actuator vẫn được Boot bảo vệ tự động.** Boot backoff khiến giả định đó sai.
3. **Chỉ bảo vệ `/actuator/**` nhưng bỏ docs/diagnostics hoặc base path đã đổi.**
4. **Đổi cổng management nhưng vẫn publish nó ra ingress public.** Port khác không tự là firewall.
5. **Coi CORS là authentication.** Curl vẫn gọi được, và credential/authorization vẫn phải kiểm phía server.
6. **Tắt CSRF toàn bộ để POST loggers/shutdown trả 200.** Thiết kế credential và CSRF theo loại client.
7. **Public health details:** `show-details=always` có thể lộ dependency/status/hostname dù chỉ là “health”.
8. **Dùng `show-values=always` cho env/configprops.** Sanitization không phải policy chia sẻ tất cả config.
9. **Cho user thường xem metrics/logfile/heapdump.** Observability data có thể lộ metadata, PII hoặc tokens.
10. **Bật shutdown hoặc debug write operation chỉ để tiện hỗ trợ.** Dùng workflow break-glass có hạn thời gian và audit.
11. **Bảo vệ Swagger UI nhưng quên `/v3/api-docs` hoặc các group/YAML/config paths.**
12. **Coi `@Hidden` là bảo mật.** Nó không chặn HTTP request.
13. **Viết endpoint GET có side effect** như clear-cache hoặc toggle-logging.
14. **Trả nguyên `System.getenv()`, request headers hoặc stacktrace trong diagnostics.**
15. **Lưu mật khẩu Basic, JWT hoặc cookie trong log, screenshots, support tickets và OpenAPI examples.**
16. **Chỉ test status 401 anonymous cho endpoint chưa expose.** Fallback security có thể che việc endpoint vẫn tồn tại; test OPS để phân biệt 404/200.
17. **Không kiểm JMX exposure:** HTTP và JMX là hai kênh khác nhau; khóa HTTP không tự khóa JMX.
18. **Chạy probe chỉ trên management server và quên main listener.** Management khỏe không bảo đảm app xử lý traffic chính.
19. **Không giới hạn request rate hoặc độ lớn heapdump/logfile** khiến thao tác chẩn đoán trở thành DoS/cạn bộ nhớ.
20. **Mở docs/diagnostics ở mọi profile vì “chỉ developer mới biết URL”.** URL secrecy không phải authorization.
21. **Dùng role OPS chung cho mọi ứng dụng/tenant** mà thiếu scope, MFA, credential rotation và audit.
22. **Coi một test local xanh là chứng minh production an toàn.** Cần kiểm ingress, TLS, IAM, config/runtime và mạng thật.

## 16. Checklist trước khi phát hành

- [ ] Có danh mục đầy đủ Actuator, OpenAPI, Swagger UI và custom diagnostics đang tồn tại.
- [ ] Mỗi Actuator endpoint chỉ được cấp access/exposure tối thiểu; ưu tiên allowlist.
- [ ] Health chỉ trả dữ liệu cần cho probes, không lộ details/components công khai.
- [ ] Custom `SecurityFilterChain` bao phủ cả management, docs và diagnostics; có fallback cho mọi API.
- [ ] Đường docs JSON, YAML, grouped specs, UI, assets/config/redirect đều yêu cầu quyền phù hợp hoặc bị tắt hoàn toàn.
- [ ] Management port và ingress/firewall/NetworkPolicy chỉ cho nguồn được phép.
- [ ] Quyền OPS/DOCS được cấp từ nguồn tin cậy, không hard-code demo credentials trong production.
- [ ] Chẩn đoán không trả env vars, token, mật khẩu, raw log, stacktrace hoặc dữ liệu người dùng.
- [ ] Write operations/CSRF/access restrictions được kiểm; không dùng GET gây side effect.
- [ ] Không tự mở heapdump, logfile, env, loggers và shutdown ngoài quy trình được phê duyệt.
- [ ] Test anonymous/USER/DOCS/OPS và URL đã tắt để tránh false sense of security.
- [ ] Thay base path/management port/proxy route vẫn giữ authorization; regression tests phản ánh URL thực.
- [ ] Giới hạn metrics labels, logging/trace và artifact chứa thông tin nhạy cảm.
- [ ] Có cơ chế audit, credential rotation, emergency revoke và break-glass time-bound.
- [ ] Trong staging, kiểm thử từ cả public network và operations network trước khi triển khai.

## 17. Câu hỏi thực hành

1. Tại sao thêm `spring-boot-starter-actuator` không đồng nghĩa mọi Actuator endpoint đều được expose qua HTTP?
2. Phân biệt `management.endpoint.<id>.access`, `web.exposure.include` và `SecurityFilterChain`. Tầng nào khiến endpoint hoàn toàn không có handler?
3. Vì sao một custom `SecurityFilterChain` với `anyRequest().permitAll()` nguy hiểm hơn nhiều khi có Actuator trên classpath?
4. Tại sao `GET /actuator/env` trả 401 cho anonymous chưa đủ chứng minh endpoint không expose? Bạn cần thử thêm gì?
5. Khi nào health được public? Vì sao phải kết hợp `show-details=never`, network/probes và test?
6. Vì sao `ROLE_OPS` không tự bao gồm `ROLE_DOCS`? Trong demo OPS mở docs bằng cách nào?
7. Bảo vệ mỗi `/swagger-ui.html` đã đủ chưa? Kể tên thêm các path OpenAPI cần bảo vệ.
8. `@Hidden` có ngăn client gọi `/internal/diagnostics/ping` không? Thành phần nào thực sự ngăn?
9. Management port 9001 có tự an toàn nếu ingress vẫn mở đến Internet không?
10. Tại sao liveness check không nên phụ thuộc mọi database/external service?
11. Với `loggers`/`shutdown`, CSRF và `read-only` giúp giảm những loại rủi ro nào? Có thay IAM không?
12. Nếu dùng JWT Resource Server thay Basic, bạn phải test signature/issuer/audience, role/scope mapping và gateway như thế nào?
13. Nếu đổi `management.endpoints.web.base-path` thành `/manage`, những matcher/test nào phải được xem lại?
14. Một endpoint chẩn đoán trả toàn bộ stacktrace nhưng yêu cầu role USER: còn những rủi ro gì?
15. Hãy thiết kế access matrix cho health, metrics, docs, diagnostics theo bốn audience: anonymous, developer, monitoring service account, operations engineer.

## 18. Tài liệu chính thức và liên kết đối chiếu

- [Spring Boot 3.5 — Actuator Endpoints, Exposure and Security](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.5 — Spring Security Integration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Testing Spring MVC with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [springdoc-openapi v2 — Spring Boot 3.x, Getting Started and Compatibility](https://springdoc.org/v2/)
- [springdoc-openapi v2 — Swagger UI and OpenAPI paths](https://springdoc.org/v2/getting-started.html)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)

**Điểm ghi nhớ:** hãy bảo vệ Actuator và diagnostics từ **giai đoạn bật endpoint**, không chỉ tới lúc viết `hasRole`. Giới hạn access/exposure, áp Spring Security cho đúng chain, che dữ liệu nhạy cảm, tách management network, kiểm đầy đủ Docs/UI và test bằng role/đường mạng thực. An toàn khi triển khai là giao của nhiều lớp kiểm soát, không phải một đường dẫn tên “internal”.
