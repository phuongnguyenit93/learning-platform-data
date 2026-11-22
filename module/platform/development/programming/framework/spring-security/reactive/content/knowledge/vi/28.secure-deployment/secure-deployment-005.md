# Bảo vệ Actuator, health endpoint, tài liệu API và điểm chẩn đoán trong Spring Security WebFlux

Chủ đề thuộc nhóm **Triển khai an toàn** của **Spring Security – reactive**. Ngoài API nghiệp vụ, dịch vụ WebFlux thường có các đường dẫn vận hành: Spring Boot Actuator, health probe, OpenAPI/Swagger UI và endpoint chẩn đoán tự viết. Nếu cấu hình sai, chúng có thể tiết lộ topology, cấu hình, số liệu, log, heap dump hoặc cho phép thay đổi trạng thái runtime. Mục tiêu là thiết kế và kiểm chứng chính sách truy cập cụ thể, an toàn khi thêm endpoint hoặc chuyển sang production.

Các ví dụ sử dụng **Java 17+, Spring Boot 3.3.13, Spring Security 6.3.x và Spring WebFlux**. Trong reactive stack dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `ServerWebExchangeMatcher`, không dùng `HttpSecurity`, `SecurityFilterChain` hay `OncePerRequestFilter` của Servlet.

## 1. Endpoint “tồn tại”, “expose” và “được phép” là ba chuyện khác nhau

Để một Actuator endpoint truy cập được qua HTTP, phải có đủ các điều kiện:

1. **Có endpoint** trong classpath và các điều kiện khởi tạo: chẳng hạn `prometheus` cần `micrometer-registry-prometheus`, `httpexchanges` cần `HttpExchangeRepository`.
2. **Enabled**: `management.endpoint.<id>.enabled` cho phép endpoint đó được tạo. Ví dụ `shutdown` bị tắt theo mặc định.
3. **Exposed** qua HTTP: `management.endpoints.web.exposure.include` chọn endpoint đưa lên web, `exclude` ưu tiên hơn `include`. Trong Spring Boot 3.3, mặc định chỉ `health` được expose qua HTTP.
4. **Authorized**: Security chain có matcher và quyền phù hợp. Ngoài ra firewall, ingress, service mesh và mạng quản trị phải cho phép kết nối.

Ví dụ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics"
```

Cấu hình này chỉ đưa `health`, `info` và `metrics` lên HTTP nếu có sẵn/đang enabled; **không tự cấp quyền truy cập**. Ngược lại, `hasRole("OPS")` không thể tạo một endpoint chưa expose. Không dùng `include: "*"` như một cách “bật cho tiện”, đặc biệt khi chưa kiểm soát hết quyền.

**Bẫy auto-configuration:** Khi tự khai báo `SecurityWebFilterChain`, ứng dụng chịu trách nhiệm cho chính sách truy cập, kể cả Actuator. Không giả định Boot tiếp tục tạo và áp toàn bộ các quy tắc security mặc định cho các endpoint quản trị. Khi dùng nhiều chain, phải bảo đảm Actuator và các route còn lại đều thực sự khớp một chain thích hợp.

## 2. Phân nhóm bề mặt và quyền truy cập

| Nhóm | Đường dẫn phổ biến | Cách bảo vệ |
| --- | --- | --- |
| Liveness | `GET /actuator/health/liveness` | Probe có thể gọi không đăng nhập, **chỉ qua mạng tin cậy**, trả dữ liệu tối giản |
| Readiness | `GET /actuator/health/readiness` | Giống liveness, thể hiện sẵn sàng nhận traffic |
| Health tổng hợp | `GET /actuator/health` | Operator, hoặc chỉ public phần trạng thái khi có lý do rõ ràng |
| Trạng thái/vận hành | `/actuator/info`, `/actuator/metrics`, `/actuator` | Operator/monitoring đã xác thực |
| Cấu hình và mapping | `/actuator/env`, `/actuator/configprops`, `/actuator/beans`, `/actuator/mappings` | Không expose nếu không cần; khi cần phải hạn chế quyền/mạng |
| Debug nhạy cảm | `/actuator/heapdump`, `/actuator/threaddump`, `/actuator/logfile`, `/actuator/loggers`, `/actuator/httpexchanges` | Hạn chế nghiêm ngặt; có thể chứa secret hoặc cho phép đổi log level |
| Tài liệu API | `/v3/api-docs`, `/v3/api-docs.yaml`, `/swagger-ui/**` | Nhóm DOCS đã xác thực, hoặc disable trong production |
| Chẩn đoán tự viết | `/internal/diagnostics/**`, `/debug/**` | Chỉ operator, log audit; cân nhắc loại khỏi bản production |
| API nghiệp vụ | `/api/**` | Chính sách riêng theo nghiệp vụ |

Những URL trong bảng là giá trị **mặc định** hoặc ví dụ. Chúng có thể thay đổi qua `management.endpoints.web.base-path`, `management.endpoints.web.path-mapping`, management port, context path, springdoc config, gateway rewrite.

### Health, liveness và readiness

- **Liveness** trả lời “instance này có cần khởi động lại không?”. Không nên coi lỗi phụ thuộc ngoài (database/queue) là nguyên nhân restart toàn bộ pod.
- **Readiness** trả lời “instance hiện nhận request được chưa?”. Trong startup, shutdown hay giai đoạn không sẵn sàng, readiness có thể DOWN trong khi liveness vẫn UP.
- **Health tổng hợp** có thể tính thêm trạng thái các dependency. Không nên mặc định biến nó thành endpoint công khai với đầy đủ component/details.

Trong Kubernetes, Boot có thể bật các health probe group tự động. Bật tường minh trong môi trường demo bằng `management.endpoint.health.probes.enabled=true`. Dùng `management.endpoint.health.show-details=never` và `management.endpoint.health.show-components=never` để không đưa thông tin phụ thuộc ra response. Nếu muốn operator xem chi tiết, dùng `when-authorized` cùng `management.endpoint.health.roles` và **đồng thời** kiểm tra chính sách Spring Security cho URL: quyền xem chi tiết và quyền gọi endpoint là hai kiểm soát riêng.

## 3. Chính sách ít quyền nhất và thứ tự matcher

Giả sử có ba loại người dùng đăng nhập: `USER` (API nghiệp vụ), `DOCS` (tài liệu), `OPS` (quản trị). Trong ví dụ, operator được cấp cả `OPS` và `DOCS`. Spring Security `hasRole("OPS")` kiểm tra authority `ROLE_OPS`; nếu hệ thống danh tính trả claim/scope khác thì cần ánh xạ hoặc dùng `hasAuthority(...)`.

Một chính sách rõ ràng:

```text
GET /actuator/health/liveness  -> permitAll
GET /actuator/health/readiness -> permitAll
Actuator endpoints còn lại     -> ROLE_OPS
/v3/api-docs*, /swagger-ui*    -> ROLE_DOCS
/internal/diagnostics/**      -> ROLE_OPS
GET /api/public/ping           -> permitAll
mọi request còn lại           -> authenticated
```

Để bảo vệ Actuator, Spring Boot 3.3 cung cấp `org.springframework.boot.actuate.autoconfigure.security.reactive.EndpointRequest`. `EndpointRequest.toAnyEndpoint()` tạo `ServerWebExchangeMatcher` theo endpoint Actuator, gồm cả trang links `/actuator`, thay vì phụ thuộc hoàn toàn vào literal `/actuator/**`. Tuy nhiên hai probe trong ví dụ dùng literal path để chỉ cho phép đúng đường dẫn mong muốn; khi đổi base path phải sửa và kiểm thử.

**Matcher cụ thể phải đứng trước matcher bao quát**; không đặt `anyExchange()` trước các quy tắc cần thực thi. Không cho phép toàn bộ `/actuator/**` chỉ vì Kubernetes cần health. Đồng thời `permitAll()` không thể xác minh request đến từ kubelet: muốn hạn chế nguồn phải có network policy/firewall/ingress phù hợp.

## 4. Ví dụ đầy đủ Spring Boot WebFlux

Ví dụ sử dụng HTTP Basic và tài khoản trong bộ nhớ **chỉ ở profile `demo`**. Production cần identity provider, service account, TLS/mTLS hoặc cơ chế đã được phê duyệt. Với Spring Boot 3.3.x dùng springdoc **2.6.x** theo compatibility matrix của dự án.

### 4.1. Khai báo dependencies

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactive-endpoint-security</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
            <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
            <version>2.6.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

### 4.2. Exposure và health response

Tạo `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics"
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
      show-components: never
    env:
      show-values: never
    configprops:
      show-values: never

springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
```

Không expose `env`, `configprops`, `loggers`, `mappings`, `heapdump`, `threaddump`, `shutdown` trong bài thực hành. `show-values: never` là lớp giảm thiểu lộ dữ liệu nếu sau này cấu hình exposure thay đổi, **không** bật endpoint đó. Cấu hình `springdoc.*.enabled` quyết định endpoint tài liệu có tồn tại, không quyết định ai được gọi.

### 4.3. Ứng dụng và controller

Tạo `src/main/java/com/example/endpointsecurity/EndpointSecurityApplication.java`:

```java
package com.example.endpointsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class EndpointSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointSecurityApplication.class, args);
    }
}

@RestController
class DemoController {

    @GetMapping("/api/public/ping")
    Mono<String> publicPing() {
        return Mono.just("pong");
    }

    @GetMapping("/api/hello")
    Mono<String> hello() {
        return Mono.just("hello");
    }

    // Chỉ minh họa route chẩn đoán; không đọc secret hay trạng thái nhạy cảm.
    @GetMapping("/internal/diagnostics/ping")
    Mono<String> diagnosticPing() {
        return Mono.just("diagnostic-ok");
    }
}
```

### 4.4. Spring Security reactive

Tạo `src/main/java/com/example/endpointsecurity/EndpointSecurityConfig.java`:

```java
package com.example.endpointsecurity;

import org.springframework.boot.actuate.autoconfigure.security.reactive.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class EndpointSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        // Chỉ mở GET liveness và readiness, không mở health gốc.
                        .pathMatchers(HttpMethod.GET,
                                "/actuator/health/liveness",
                                "/actuator/health/readiness").permitAll()

                        // Matcher reactive bao gồm các Actuator và trang links.
                        .matchers(EndpointRequest.toAnyEndpoint())
                                .hasRole("OPS")

                        // Bảo vệ cả OpenAPI schema, Swagger config và UI assets.
                        .pathMatchers(
                                "/v3/api-docs",
                                "/v3/api-docs.yaml",
                                "/v3/api-docs/**",
                                "/swagger-ui.html",
                                "/swagger-ui/**",
                                "/webjars/swagger-ui/**")
                                .hasRole("DOCS")

                        .pathMatchers("/internal/diagnostics/**")
                                .hasRole("OPS")

                        .pathMatchers(HttpMethod.GET, "/api/public/ping")
                                .permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                // Giữ CSRF mặc định; demo chỉ khai báo các GET endpoint.
                .build();
    }

    @Bean
    @Profile("demo")
    MapReactiveUserDetailsService demoUsers() {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        UserDetails viewer = User.withUsername("viewer")
                .password(encoder.encode("viewer123"))
                .roles("USER")
                .build();
        UserDetails docs = User.withUsername("docs")
                .password(encoder.encode("docs123"))
                .roles("DOCS")
                .build();
        UserDetails ops = User.withUsername("ops")
                .password(encoder.encode("ops123"))
                .roles("OPS", "DOCS")
                .build();
        return new MapReactiveUserDetailsService(viewer, docs, ops);
    }
}
```

**Điểm quan trọng của đoạn mã:**

1. `EndpointRequest` được import từ `...security.reactive`; Servlet cũng có lớp cùng tên nhưng kiểu matcher khác.
2. Hai probe được permit **trước** matcher tất cả Actuator. Còn health gốc, metrics, info, links và mọi endpoint Actuator mới được expose sẽ yêu cầu `ROLE_OPS`.
3. JSON ở `/v3/api-docs`, YAML, `/v3/api-docs/swagger-config`, HTML và JS/CSS Swagger UI phải được bảo vệ nhất quán. Nếu đổi `springdoc.api-docs.path` hay `springdoc.swagger-ui.path`, phải cập nhật matcher và test theo URL thực tế.
4. `/internal/diagnostics/**` được áp role OPS. Nếu tạo route mới ngoài pattern này, `anyExchange().authenticated()` vẫn bắt login nhưng **chưa** đủ nếu route cần role OPS; phải mở rộng policy theo tên route và chức năng.
5. Ví dụ không vô hiệu hóa CSRF toàn cục. GET không làm thay đổi trạng thái; nếu bổ sung endpoint POST/PUT/DELETE phục vụ diagnostics, phải có chính sách CSRF thích hợp, authorization, audit và chống lạm dụng.
6. HTTP Basic và password mẫu chỉ dành cho local demo; không lưu thông tin đăng nhập mẫu vào cấu hình production. Với JWT/OIDC, ánh xạ role/authority của IdP phải được kiểm chứng thay vì giả định token có `ROLE_OPS`.

## 5. Chạy thử và bảng quyết định 200/401/403

Dùng JDK 17+ và Maven trong thư mục có `pom.xml`:

```bash
mvn spring-boot:run -Dspring-boot.run.profiles=demo
```

Ở terminal khác (chỉ dùng mật khẩu mẫu trên localhost):

```bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i -u viewer:viewer123 http://localhost:8080/actuator/metrics
curl -i -u ops:ops123 http://localhost:8080/actuator/metrics

curl -i http://localhost:8080/v3/api-docs
curl -i -u viewer:viewer123 http://localhost:8080/v3/api-docs
curl -i -u docs:docs123 http://localhost:8080/v3/api-docs

curl -i http://localhost:8080/internal/diagnostics/ping
curl -i -u viewer:viewer123 http://localhost:8080/internal/diagnostics/ping
curl -i -u ops:ops123 http://localhost:8080/internal/diagnostics/ping

curl -i http://localhost:8080/api/public/ping
curl -i http://localhost:8080/api/hello
curl -i -u viewer:viewer123 http://localhost:8080/api/hello
```

Bảng **status dự kiến** khi dịch vụ đã ready, các probe trạng thái UP:

| Endpoint | Anonymous | USER | DOCS | OPS + DOCS |
| --- | --- | --- | --- | --- |
| `GET /actuator/health/liveness` | 200 | 200 | 200 | 200 |
| `GET /actuator/health/readiness` | 200 | 200 | 200 | 200 |
| `GET /actuator/health` | 401 | 403 | 403 | 200 |
| `GET /actuator/metrics` | 401 | 403 | 403 | 200 |
| `GET /v3/api-docs` | 401 | 403 | 200 | 200 |
| `GET /swagger-ui.html` | 401 | 403 | Được phép, có thể trả 302 redirect | Được phép, có thể trả 302 |
| `GET /internal/diagnostics/ping` | 401 | 403 | 403 | 200 |
| `GET /api/public/ping` | 200 | 200 | 200 | 200 |
| `GET /api/hello` | 401 | 200 | 200 | 200 |

**401** thường biểu thị thiếu xác thực; **403** thường biểu thị đã xác thực nhưng không đủ quyền. `404` có thể vì endpoint chưa expose, chưa enabled, sai base path, thiếu dependency hoặc request đã đi theo route khác; một HTTP 404 không chứng minh chính sách authorization đang an toàn. Health khi DOWN có thể trả `503`; đây là **sức khỏe dịch vụ**, không phải lỗi security. Swagger UI có thể redirect từ `/swagger-ui.html` tới `/swagger-ui/index.html`; chỉ kiểm tra response đầu chưa đủ, phải xác nhận schema và assets thật sự tải được với role DOCS và bị chặn với USER.

Không truyền mật khẩu production trong lệnh curl `-u` trên command line: có nguy cơ lộ trong shell history/process list. Gọi API production bằng HTTPS và cơ chế xác thực đã được quản lý.

## 6. Kiểm thử hồi quy với WebTestClient

Để phát hiện accidental exposure sau khi thêm dependency/route, có thể chạy test tích hợp. Tạo `src/test/java/com/example/endpointsecurity/EndpointSecurityIntegrationTest.java`:

```java
package com.example.endpointsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("demo")
class EndpointSecurityIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void probesAreOpenButMetricsAreNot() {
        client.get().uri("/actuator/health/liveness")
                .exchange().expectStatus().isOk();
        client.get().uri("/actuator/metrics")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void regularUserCannotReadAdminEndpointsOrDocs() {
        client.get().uri("/actuator/metrics")
                .headers(h -> h.setBasicAuth("viewer", "viewer123"))
                .exchange().expectStatus().isForbidden();
        client.get().uri("/v3/api-docs")
                .headers(h -> h.setBasicAuth("viewer", "viewer123"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void docsRoleCannotReadDiagnostics() {
        client.get().uri("/v3/api-docs")
                .headers(h -> h.setBasicAuth("docs", "docs123"))
                .exchange().expectStatus().isOk();
        client.get().uri("/internal/diagnostics/ping")
                .headers(h -> h.setBasicAuth("docs", "docs123"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void operatorCanUseProtectedRoutes() {
        client.get().uri("/actuator/metrics")
                .headers(h -> h.setBasicAuth("ops", "ops123"))
                .exchange().expectStatus().isOk();
        client.get().uri("/internal/diagnostics/ping")
                .headers(h -> h.setBasicAuth("ops", "ops123"))
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("diagnostic-ok");
    }
}
```

Chạy `mvn test`. Kiểm thử này xác nhận policy trong một runtime WebFlux, **không** chứng minh network policy, ingress, reverse proxy hoặc management port ngoài JVM đã đúng. Khi triển khai cần kiểm tra thêm `/actuator` links, `/actuator/info`, `/v3/api-docs.yaml`, `/v3/api-docs/swagger-config`, Swagger UI assets, các alternate path và các diagnostics đã tạo.

## 7. Management port, base path và network boundary

Nếu muốn tách Actuator ra cổng quản trị riêng, cấu hình thay thế:

```yaml
management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: "health,info,metrics"
```

Đây là **phương án triển khai khác**, không gộp vào file demo rồi dùng lại lệnh curl cũ. Khi áp dụng, URL Actuator có thể trở thành `http://localhost:9090/manage/health`; kiểm tra chính xác cổng, context và proxy route. Chuyển sang cổng riêng **không tự tạo tường lửa**, phải dùng security group, network policy, private listener, firewall hay ingress restriction. Không giả định web security chain được áp y hệt trên mọi management context khi management server chạy ở port riêng: cần test trực tiếp đường mạng thật.

Matcher `EndpointRequest` nhận biết metadata của Actuator; literal `/actuator/health/liveness`/`readiness` trong ví dụ **phải đổi** khi thay base path. Tương tự, nếu gateway rewrite URL ở mép mạng, kiểm thử phải bắt đầu tại địa chỉ public và internal đúng vai trò, thay vì chỉ thử URL localhost.

Khi Kubernetes gọi health qua management port riêng, tiến trình quản trị có thể vẫn đáp ứng trong khi web server chính không nhận traffic. Spring Boot hỗ trợ:

```properties
management.endpoint.health.probes.add-additional-paths=true
```

Tùy chọn này đưa liveness và readiness lên cổng ứng dụng chính tại `/livez` và `/readyz`. Nếu sử dụng, phải cấu hình **quyền riêng** cho hai đường dẫn đó và giới hạn nguồn truy cập phù hợp. Tránh gắn kiểm tra database/queue chia sẻ vào liveness; readiness nên phản ánh khả năng nhận traffic thực tế, tránh sự cố lan rộng khi một dependency chung bị lỗi.

## 8. Bảo vệ OpenAPI và Swagger UI đúng cách

Springdoc WebFlux cung cấp nhiều tài nguyên phục vụ cùng một UI:

- `/v3/api-docs`: OpenAPI JSON; `/v3/api-docs.yaml`: YAML.
- `/v3/api-docs/swagger-config`: cấu hình Swagger UI.
- `/swagger-ui.html`: đường dẫn truy cập UI, thường redirect.
- `/swagger-ui/**` và một số static resources liên quan như `/webjars/swagger-ui/**`.

Chặn mỗi `/swagger-ui.html` **không** ngăn client đọc OpenAPI JSON/YAML. Chặn schema nhưng mở HTML có thể khiến UI tải lỗi hoặc lộ thông tin một phần. Với custom path/group của springdoc, cần bảo vệ đúng mọi URL được tạo và kiểm tra bằng browser/network trace hoặc integration test. Nếu muốn công bố docs public, phải rà soát schema có chứa endpoint nội bộ, host, server URL, sample credential hay mô tả nhạy cảm hay không; group API public/private chỉ có giá trị khi cấu hình lọc đúng thực tế.

Nếu môi trường production không cần công bố tài liệu runtime:

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
```

Có thể phát hành tài liệu dạng tệp tĩnh đã duyệt qua pipeline riêng. Đừng dùng việc “ẩn Swagger” làm biện pháp bảo vệ API nghiệp vụ: quyền được kiểm tra ở chính HTTP API, kể cả khi không có UI.

## 9. Điểm chẩn đoán và Actuator nhạy cảm

**Nguyên tắc:** Chỉ expose thứ cần vận hành, chỉ cấp quyền cho đúng đối tượng, đồng thời giới hạn đường mạng và log audit. Ngay cả `ROLE_OPS` cũng không có nghĩa người đó cần truy cập mọi loại dữ liệu nhạy cảm.

- `env`, `configprops`: Spring Boot sanitize những giá trị có thể nhạy cảm, nhưng tên thuộc tính và cấu trúc vẫn có thể tiết lộ hạ tầng. Không đặt `show-values=always` khi không có kiểm soát đặc biệt.
- `heapdump`, `threaddump`, `logfile`, `httpexchanges`: có thể tiết lộ token/secret trong heap, log, headers hay nội dung request. Nên tắt bình thường, chỉ bật theo quy trình có hạn mức và kiểm toán.
- `loggers` và `shutdown`: có thể thay đổi trạng thái/runtime; `shutdown` disable mặc định. POST/PUT/DELETE còn chịu ảnh hưởng CSRF nếu ứng dụng sử dụng phiên/cookie; với non-browser API, phải quyết định CSRF theo mô hình đe dọa thay vì disable tùy tiện.
- `/internal/diagnostics/**`: route tự viết không thuộc `EndpointRequest`. Phải có matcher riêng và kiểm tra cả subpath, phương thức HTTP, nhiều security chain và mọi URL alias.
- Endpoint chẩn đoán tốn CPU/bộ nhớ hoặc thực hiện I/O blocking có thể gây DoS ngay cả khi người có quyền gọi. Trong WebFlux, không chạy blocking operation trên event loop; giới hạn concurrency, timeout, quota và dùng scheduler phù hợp nếu buộc phải gọi API blocking.
- Cấu hình Actuator qua `management.endpoints.web.exposure` chỉ chi phối HTTP; JMX có chính sách expose/quyền mạng riêng, không tự bị rule WebFlux bảo vệ.

Khi ghi log audit, giữ các field có ích như principal đã xác thực, loại thao tác, tài nguyên, thời điểm, quyết định và correlation ID; không log Authorization header, JWT nguyên văn, mật khẩu, heap dump hay dữ liệu cá nhân không cần thiết. Metric nên dùng nhãn hữu hạn như endpoint class, policy và status, không gắn token, request ID hoặc path động làm nhãn gây cardinality cao.

## 10. Những lỗi thường gặp và cách phòng tránh

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Expose toàn bộ `*` trong khi chỉ bảo vệ `/api/**` | Endpoint vận hành có thể lộ | Exposure allowlist + `EndpointRequest` với role OPS |
| Permit `/actuator/**` vì cần health | Cấp quyền cho cả Actuator khác | Chỉ permit liveness/readiness cụ thể |
| Chặn UI nhưng quên `/v3/api-docs` | Schema vẫn bị tải không phép | Giữ cùng policy cho schema, UI config, HTML/JS/CSS |
| Áp `HttpSecurity`/`SecurityFilterChain` Servlet vào WebFlux | Security matcher sai stack | Dùng `ServerHttpSecurity`/`SecurityWebFilterChain` reactive |
| Đặt `anyExchange()` trước route đặc quyền | Matcher sau không bao giờ được dùng | Cụ thể trước, bao quát cuối |
| Mọi 401/403/404 đều được xem là “đã bảo vệ” | Che lấp lỗi exposure, thiếu handler hoặc matcher | Test cả authorized 200, denied 403 và anonymous 401; xác minh body |
| `show-details=always` với health public | Lộ dependency status/detail | `never` hoặc `when-authorized` có role thích hợp |
| Đổi management port/path nhưng dùng nguyên config cũ | Có thể mở port hoặc phá probe | Test đường mạng và matcher thực, giới hạn port bằng ACL |
| Bật loggers/heapdump trong production rồi quên tắt | Lộ dữ liệu/chỉnh trạng thái | Disabled bình thường, chỉ bật theo quy trình và audit |
| Dùng tài khoản Basic demo trong production | Credential cố định dễ lộ | Chỉ kích hoạt profile demo tại local, thay bằng IdP/TLS |

## 11. Checklist kiểm chứng khi triển khai

1. **Inventory:** Liệt kê endpoint đang enabled và HTTP exposed theo profile/dependency thực tế, không dựa vào file cấu hình của môi trường khác.
2. **Probe:** Liveness/readiness trả payload tối giản, đúng status khi UP/DOWN, được mạng orchestration gọi; mạng ngoài bị hạn chế nếu không cần.
3. **Actuator:** Anonymous và USER không xem được metrics/info/links; operator xem được đúng endpoint đã expose; heapdump/loggers/env không tự xuất hiện.
4. **Docs:** JSON, YAML, swagger-config, UI và static assets áp cùng policy; role DOCS vào được toàn bộ, USER không đọc được.
5. **Diagnostics:** Mọi HTTP method và alias của route chẩn đoán đều yêu cầu đúng role; endpoint nguy hiểm có audit, rate limit, timeout.
6. **Network & regression:** Test ở cả WebTestClient và địa chỉ ingress/management port thật; kiểm tra khi đổi base path, profile, identity provider, thêm Actuator hoặc nâng phiên bản Spring Boot.

Đạt yêu cầu khi quyền mặc định không mở nhầm tài nguyên mới, health probe hoạt động mà không tiết lộ chi tiết không cần thiết, và các endpoint vận hành hoặc tài liệu chỉ khả dụng cho đúng principal, từ đúng vùng mạng, với kiểm thử có thể lặp lại.

### Tài liệu tham khảo

- Spring Boot 3.3 Actuator – Enabling, Exposing, Security, Health Groups và Kubernetes Probes: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 reactive `EndpointRequest`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/reactive/EndpointRequest.html
- Spring Security WebFlux configuration và multiple chains: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security reactive HTTP authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Springdoc OpenAPI v2 – Boot compatibility (Boot 3.3.x dùng springdoc 2.6.x): https://springdoc.org/v2/faq.html
- Springdoc v2 – WebFlux API/Swagger UI: https://springdoc.org/v2/modules.html