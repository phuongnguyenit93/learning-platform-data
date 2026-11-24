# Tích hợp Spring Boot, Prometheus registry và endpoint được bảo vệ

Bài thực hành này xây dựng một ứng dụng Java dùng Micrometer để ghi nhận metrics, Spring Boot Actuator để expose dữ liệu và Prometheus để scrape. Endpoint `/actuator/prometheus` chạy trên management port riêng, yêu cầu danh tính `metrics-scraper` có role `METRICS`; Prometheus được cấu hình gửi Basic Auth khi scrape. API nghiệp vụ dùng một tài khoản khác để minh họa phân quyền độc lập.

Phạm vi thuộc module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`: sử dụng `Counter` và `Timer` để đo hoạt động tra cứu đơn hàng, tích hợp `micrometer-registry-prometheus`, quản lý cấu hình Spring Boot, kiểm soát quyền truy cập và xác minh đường đi từ meter tới Prometheus. Bài thực hành dùng Spring Boot 3.5.x, Java 21, Maven và Docker Compose làm môi trường mẫu. Khi áp dụng cho release train khác, để BOM của Spring Boot quản lý phiên bản Micrometer tương ứng.

## 1. Kết quả cần đạt

Sau bài thực hành, bạn có thể:

- Tạo ứng dụng Spring Boot có Actuator và Prometheus registry.
- Inject `MeterRegistry` và ghi nhận `Counter`, `Timer` từ code nghiệp vụ.
- Chạy Actuator trên management port riêng.
- Chỉ expose `health` và `prometheus`.
- Bảo vệ `/actuator/prometheus` bằng HTTP Basic và role `METRICS`.
- Cấp tài khoản API role `USER` riêng với tài khoản scrape.
- Để Prometheus scrape qua mạng Docker nội bộ bằng `password_file`.
- Kiểm thử trường hợp chưa xác thực, sai role và đúng role.
- Kiểm tra metric được nhận tại Prometheus UI và truy vấn được.

## 2. Kiến trúc lab

Ứng dụng mở hai cổng. Port `8080` phục vụ API; port `8081` dành cho Actuator và chỉ được các container trong mạng monitoring truy cập. Prometheus chạy trên port `9090` để người học mở giao diện cục bộ.

```mermaid
flowchart LR
    U[Developer / API client] -->|8080 + role USER| A[Spring Boot order-service]
    P[Prometheus] -->|8081 + Basic Auth role METRICS| M[/actuator/prometheus]
    M --> R[PrometheusMeterRegistry]
    A --> R
    P --> UI[Prometheus UI :9090]
```

Các ranh giới bảo vệ:

| Thành phần | Cổng | Quyền truy cập |
| --- | ---: | --- |
| Order API | 8080 | `api-user`, role `USER` |
| Actuator health | 8081 | Public trong lab, không trả chi tiết khi chưa được phép |
| Actuator Prometheus | 8081 | `metrics-scraper`, role `METRICS` |
| Prometheus UI | 9090 | Publish ra máy phát triển để kiểm tra lab |

Management port không được publish ra host trong Docker Compose. Prometheus kết nối tới `order-service:8081` bằng DNS nội bộ của Compose network. Đây là cấu hình lab; production cần đặt API sau TLS, giới hạn mạng, quản lý secret tập trung và áp dụng chính sách truy cập theo hạ tầng thực tế.

## 3. Chuẩn bị dự án Maven

Tạo một dự án với cấu trúc sau:

```text
micrometer-prometheus-lab/
├── pom.xml
├── Dockerfile
├── docker-compose.yml
├── prometheus.yml
└── src/
    ├── main/
    │   ├── java/com/example/observability/
    │   │   ├── OrderApplication.java
    │   │   ├── api/OrderController.java
    │   │   ├── api/OrderResponse.java
    │   │   ├── metrics/OrderMetrics.java
    │   │   ├── security/SecurityConfiguration.java
    │   │   └── service/OrderService.java
    │   └── resources/application.yml
    └── test/java/com/example/observability/
        └── PrometheusEndpointSecurityTest.java
```

Tạo `pom.xml`:

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

    <groupId>com.example</groupId>
    <artifactId>micrometer-prometheus-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
            <scope>runtime</scope>
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

Không pin version riêng cho `micrometer-core` hoặc registry. Spring Boot parent import dependency management để chọn các phiên bản Micrometer tương thích. Nếu dùng Spring Boot patch khác, thay version parent bằng patch đã được tổ chức phê duyệt và kiểm tra lại JDK baseline.

Tạo application class:

```java
package com.example.observability;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

## 4. Cấu hình Spring Boot và management endpoint

Tạo `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: order-service
  config:
    import: optional:configtree:/run/secrets/

server:
  port: 8080

management:
  server:
    port: 8081
    address: 0.0.0.0
  endpoints:
    web:
      exposure:
        include: health,prometheus
  endpoint:
    health:
      show-details: when-authorized
  metrics:
    tags:
      application: ${spring.application.name}
```

`management.server.port` tách Actuator khỏi cổng API. `management.server.address: 0.0.0.0` cho phép Prometheus trong container khác kết nối đến port 8081; Docker Compose sẽ giới hạn đường truy cập ở network nội bộ và không publish port này ra host.

`spring.config.import` nạp các file secret trong `/run/secrets/` thành property. Ví dụ file có tên `app.security.metrics-password` sẽ cung cấp property `${app.security.metrics-password}`. Khi chạy local không có thư mục secret, tiền tố `optional:` cho phép ứng dụng khởi động nếu các property được truyền bằng cấu hình khác.

Chỉ expose `health` và `prometheus`. Không dùng wildcard `*` trong production. Các endpoint như `env`, `configprops`, `heapdump`, `threaddump` và `shutdown` không thuộc phạm vi scrape của lab.

## 5. Tạo bean metrics và giữ meter để tái sử dụng

Tạo `metrics/OrderMetrics.java`:

```java
package com.example.observability.metrics;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.function.Supplier;

@Component
public class OrderMetrics {
    private final Counter lookups;
    private final Timer lookupDuration;

    public OrderMetrics(MeterRegistry registry) {
        this.lookups = Counter.builder("orders.lookups")
            .description("Number of order lookup requests")
            .register(registry);

        this.lookupDuration = Timer.builder("orders.lookup.duration")
            .description("Time spent looking up an order")
            .register(registry);
    }

    public void lookup() {
        lookups.increment();
    }

    public <T> T recordLookup(Supplier<T> operation) {
        return lookupDuration.record(operation);
    }
}
```

Spring Boot inject registry đã được auto-configure từ Prometheus dependency. Hai meter được đăng ký trong constructor của singleton bean và giữ ở field `final`; mỗi request chỉ cập nhật counter hoặc timer. `Timer.record(Supplier)` vẫn ghi nhận thời lượng khi supplier ném exception.

## 6. Tạo service và API tạo dữ liệu metrics

Tạo `api/OrderResponse.java`:

```java
package com.example.observability.api;

public record OrderResponse(
    String orderId,
    String customerId,
    String status
) {
}
```

Tạo `service/OrderService.java`:

```java
package com.example.observability.service;

import com.example.observability.api.OrderResponse;
import com.example.observability.metrics.OrderMetrics;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderMetrics metrics;

    public OrderService(OrderMetrics metrics) {
        this.metrics = metrics;
    }

    public OrderResponse find(String orderId) {
        return metrics.recordLookup(() -> {
            metrics.lookup();
            return new OrderResponse(orderId, "customer-demo", "FOUND");
        });
    }
}
```

Tạo `api/OrderController.java`:

```java
package com.example.observability.api;

import com.example.observability.service.OrderService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{orderId}")
    public OrderResponse find(@PathVariable String orderId) {
        return orderService.find(orderId);
    }
}
```

API trả dữ liệu demo nhưng vẫn tạo metrics thực tế. Mỗi lần gọi thành công làm `orders.lookups` tăng một đơn vị và ghi một mẫu vào `orders.lookup.duration`. Không đưa `orderId` vào tag; ID chỉ nằm trong path/response để tránh tạo time series theo từng đơn hàng.

## 7. Bảo vệ Actuator và API bằng các SecurityFilterChain riêng

Tạo `security/SecurityConfiguration.java`:

```java
package com.example.observability.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .requestMatchers(EndpointRequest.to("prometheus")).hasRole("METRICS")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasRole("USER"))
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain denyUnmatchedRequests(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize.anyRequest().denyAll())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder passwordEncoder,
            @Value("${app.security.api-password}") String apiPassword,
            @Value("${app.security.metrics-password}") String metricsPassword) {

        UserDetails apiUser = User.withUsername("api-user")
            .password(passwordEncoder.encode(apiPassword))
            .roles("USER")
            .build();

        UserDetails metricsUser = User.withUsername("metrics-scraper")
            .password(passwordEncoder.encode(metricsPassword))
            .roles("METRICS")
            .build();

        return new InMemoryUserDetailsManager(apiUser, metricsUser);
    }
}
```

Ba filter chain có thứ tự rõ ràng:

- Chain 1 chỉ áp dụng cho Actuator. Health được phép truy cập theo chính sách lab; Prometheus yêu cầu `ROLE_METRICS`; các endpoint Actuator khác bị từ chối.
- Chain 2 chỉ áp dụng cho `/api/**` và yêu cầu `ROLE_USER`.
- Chain 3 từ chối mọi request không khớp hai vùng trên.

`hasRole("METRICS")` tương ứng authority `ROLE_METRICS`. Tài khoản API không có role này nên không thể scrape metrics; tài khoản scraper cũng không có role `USER` nên không gọi được API. Các request dùng HTTP Basic trong lab; production phải bảo vệ đường truyền bằng HTTPS/mTLS và dùng identity/secret provider phù hợp.

## 8. Tạo secret cho local Docker Compose

Tạo thư mục `secrets/` và hai file:

```text
secrets/
├── app.security.api-password
└── app.security.metrics-password
```

Điền hai mật khẩu ngẫu nhiên dài, khác nhau, bằng password manager. Ghi file không có newline cuối để tránh mật khẩu bị thêm ký tự xuống dòng. Thêm vào `.gitignore`:

```gitignore
/secrets/
```

Không commit hai file này, không ghi mật khẩu trực tiếp vào `application.yml`, `prometheus.yml`, Dockerfile hoặc `docker-compose.yml`. Docker Compose sẽ mount file thành secret read-only trong container. Spring Boot config tree đọc secret của ứng dụng; Prometheus đọc cùng secret metrics qua `password_file`.

## 9. Cấu hình Prometheus scrape có xác thực

Tạo `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: order-service
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - order-service:8081
    basic_auth:
      username: metrics-scraper
      password_file: /run/secrets/app.security.metrics-password
```

Prometheus kết nối tới tên service `order-service` trong mạng Compose và management port 8081. `basic_auth` gửi đúng danh tính `metrics-scraper`; `password_file` đọc mật khẩu từ secret được mount. Không dùng API password ở đây và không cấp tài khoản admin cho scraper.

## 10. Đóng gói ứng dụng và chạy hai container

Tạo `Dockerfile`:

```dockerfile
FROM maven:3.9.9-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY pom.xml .
RUN mvn -B -q dependency:go-offline
COPY src ./src
RUN mvn -B -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/micrometer-prometheus-lab-1.0.0-SNAPSHOT.jar /app/app.jar
EXPOSE 8080 8081
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Tạo `docker-compose.yml`:

```yaml
services:
  order-service:
    build: .
    ports:
      - "8080:8080"
    expose:
      - "8081"
    secrets:
      - source: api_password
        target: app.security.api-password
      - source: metrics_password
        target: app.security.metrics-password
    networks:
      - monitoring

  prometheus:
    image: prom/prometheus:v3.5.0
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.path=/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
    secrets:
      - source: metrics_password
        target: app.security.metrics-password
    depends_on:
      - order-service
    networks:
      - monitoring

networks:
  monitoring:
    driver: bridge

secrets:
  api_password:
    file: ./secrets/app.security.api-password
  metrics_password:
    file: ./secrets/app.security.metrics-password
```

Chỉ port 8080 của API và port 9090 của Prometheus UI được publish ra host. Port 8081 chỉ được expose trong mạng Docker để Prometheus truy cập. Với Docker Compose local, file-backed secrets là cách tiện để thực hành; môi trường production nên dùng secret manager hoặc cơ chế secret của nền tảng triển khai.

## 11. Khởi động và gọi API để tạo metrics

Kiểm tra cấu hình Compose và Prometheus:

```powershell
docker compose config
docker compose run --rm prometheus promtool check config /etc/prometheus/prometheus.yml
```

Build và khởi động:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f order-service prometheus
```

Trong PowerShell, đọc mật khẩu API từ file secret và gọi endpoint:

```powershell
$apiPassword = Get-Content -Raw .\secrets\app.security.api-password
curl.exe -i -u "api-user:$apiPassword" http://localhost:8080/api/orders/order-100
```

Gọi lặp lại vài lần với các order ID khác nhau. Response JSON có dạng:

```json
{
  "orderId": "order-100",
  "customerId": "customer-demo",
  "status": "FOUND"
}
```

Mỗi request thành công tăng counter `orders.lookups` và ghi một mẫu vào `orders.lookup.duration`. ID thay đổi không tạo thêm tag hay time series.

## 12. Xác minh endpoint được bảo vệ

Test ở phần tiếp theo xác minh đủ ba trạng thái. Có thể dùng `curl.exe` khi management port được truy cập từ một máy trong network nội bộ; trong Compose lab, port 8081 không publish ra host nên Prometheus là client scrape trực tiếp.

| Request | Kết quả mong đợi | Giải thích |
| --- | ---: | --- |
| Không gửi credentials tới `/actuator/prometheus` | 401 | Chưa xác thực |
| Gửi `api-user` tới `/actuator/prometheus` | 403 | Đã xác thực nhưng thiếu role `METRICS` |
| Gửi `metrics-scraper` tới `/actuator/prometheus` | 200 | Đúng danh tính và role |
| Không credentials tới `/actuator/health` | 200 | Health được phép trong lab |
| Không credentials tới `/api/orders/order-100` | 401 | API yêu cầu role `USER` |
| Gửi `api-user` tới API | 200 | Tài khoản API hợp lệ |

Đừng publish port 8081 chỉ để kiểm tra từ host. Dùng integration test qua management port ngẫu nhiên hoặc chạy một client chẩn đoán trong cùng network khi cần xác minh trực tiếp.

## 13. Viết integration test cho 401, 403 và 200

Tạo `PrometheusEndpointSecurityTest.java`:

```java
package com.example.observability;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "management.server.port=0",
        "app.security.api-password=test-api-password",
        "app.security.metrics-password=test-metrics-password"
    }
)
class PrometheusEndpointSecurityTest {
    @LocalServerPort
    int applicationPort;

    @LocalManagementPort
    int managementPort;

    @Autowired
    TestRestTemplate rest;

    @Test
    void protectsPrometheusEndpointByRole() {
        String url = "http://localhost:" + managementPort + "/actuator/prometheus";

        ResponseEntity<String> anonymous = rest.getForEntity(url, String.class);
        assertThat(anonymous.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);

        ResponseEntity<String> apiUser = rest
            .withBasicAuth("api-user", "test-api-password")
            .getForEntity(url, String.class);
        assertThat(apiUser.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);

        ResponseEntity<String> scraper = rest
            .withBasicAuth("metrics-scraper", "test-metrics-password")
            .getForEntity(url, String.class);
        assertThat(scraper.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(scraper.getBody()).isNotBlank();
    }

    @Test
    void protectsApplicationApiWithDifferentRole() {
        String url = "http://localhost:" + applicationPort + "/api/orders/order-100";

        ResponseEntity<String> anonymous = rest.getForEntity(url, String.class);
        assertThat(anonymous.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);

        ResponseEntity<String> apiUser = rest
            .withBasicAuth("api-user", "test-api-password")
            .getForEntity(url, String.class);
        assertThat(apiUser.getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<String> scraper = rest
            .withBasicAuth("metrics-scraper", "test-metrics-password")
            .getForEntity(url, String.class);
        assertThat(scraper.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
    }
}
```

`management.server.port=0` yêu cầu Spring Boot chọn management port ngẫu nhiên cho test; `@LocalManagementPort` cung cấp port thực tế. Test override secret bằng mật khẩu giả lập, không đọc secret production. TestRestTemplate gọi endpoint qua HTTP thật trong test context, vì vậy xác minh cả authentication lẫn authorization trên management server riêng.

Chạy test:

```powershell
mvn test
```

Nếu test báo không tìm thấy `@LocalManagementPort`, kiểm tra Spring Boot test dependency và việc management server có thực sự chạy trên port riêng. Không đổi test thành MockMvc trên application port mà vẫn tuyên bố đã kiểm tra management port riêng.

## 14. Xác minh Prometheus đã scrape thành công

Mở Prometheus UI:

```text
http://localhost:9090/targets
```

Job `order-service` phải có trạng thái `UP`. Nếu target `DOWN`, mở scrape error để xem status hoặc lỗi kết nối. Tiếp theo, vào tab Graph và chạy các truy vấn:

```promql
up{job="order-service"}
```

Kết quả mong đợi là `1` khi scrape thành công.

```promql
orders_lookups_total
```

Counter phải tăng sau khi gọi API nhiều lần và được scrape ở chu kỳ tiếp theo.

```promql
rate(orders_lookups_total[5m])
```

Truy vấn tốc độ tra cứu trung bình mỗi giây trong cửa sổ 5 phút.

```promql
rate(orders_lookup_duration_seconds_sum[5m])
/
rate(orders_lookup_duration_seconds_count[5m])
```

Truy vấn thời lượng tra cứu trung bình trong cửa sổ. Tên metric là dạng Prometheus thường được tạo từ tên Micrometer; xác nhận tên thực tế trong tab Graph hoặc `/actuator/prometheus` nếu naming convention của phiên bản registry khác.

## 15. Kiểm tra và chẩn đoán từng lớp

| Triệu chứng | Kiểm tra | Hướng xử lý |
| --- | --- | --- |
| 404 `/actuator/prometheus` | Registry dependency, exposure và base path | Thêm Prometheus registry, expose endpoint và kiểm tra path |
| 401 từ Prometheus | Username/password file, file mount và nội dung secret | Xác nhận tên user, secret path, quyền đọc và không có newline thừa |
| 403 từ Prometheus | Role của user | Tài khoản scraper phải có role `METRICS` |
| Prometheus target `DOWN` với connection refused | Port, bind address, container network | Kiểm tra management port 8081 và `0.0.0.0` trong container |
| Prometheus target `DOWN` với timeout | Endpoint chậm hoặc mạng lỗi | Xem scrape duration, log app và network policy |
| Target `UP` nhưng không thấy counter | Chưa gọi API hoặc selector sai | Gọi API, đợi scrape cycle và tìm tên series thực tế |
| API trả 401 | Credentials API | Dùng `api-user`, không dùng scraper user |
| API trả 403 | Role API | API yêu cầu `USER`; scraper chỉ có `METRICS` |
| Spring không tạo được UserDetailsService | Secret property thiếu | Kiểm tra hai file config tree hoặc test properties |
| Secret không khớp | File có newline hoặc Compose mount sai target | Ghi file không newline và kiểm tra secret mount |

Quy trình debug nên đi từ trong ra ngoài: kiểm tra ứng dụng khởi động và registry bean; kiểm tra endpoint trên management server; kiểm tra authentication/authorization; kiểm tra kết nối từ Prometheus; cuối cùng kiểm tra query. Nếu registry đã có meter nhưng target vẫn `DOWN`, vấn đề nằm ở endpoint/network/authentication chứ không phải Counter hoặc Timer.

## 16. Kiểm tra cardinality và quyền truy cập dữ liệu

Trong lab, `orders.lookups` không có tag `orderId`. Nếu thêm `orderId` vào tag, mỗi đơn hàng có thể tạo một time series riêng. Điều này làm tăng bộ nhớ registry, scrape payload và chi phí lưu trữ backend.

Metrics endpoint cũng có thể tiết lộ tên service, trạng thái runtime và nhãn tùy chỉnh. Vì vậy:

- Không gắn token, email, customer ID, order ID hoặc URL thô vào metric tag.
- Dùng role `METRICS` riêng cho scraper.
- Không expose endpoint quản trị chỉ để Prometheus scrape.
- Không đưa management port vào public ingress.
- Dùng secret file hoặc secret manager, không ghi credential vào Git.
- Trong production, dùng HTTPS/mTLS giữa scraper và management endpoint.

## 17. Tiêu chí hoàn thành và dọn dẹp

Lab hoàn thành khi tất cả điều kiện sau đúng:

- [ ] Ứng dụng Spring Boot khởi động với Prometheus registry.
- [ ] API `GET /api/orders/{orderId}` yêu cầu role `USER`.
- [ ] `/actuator/health` trả 200 theo cấu hình lab.
- [ ] `/actuator/prometheus` trả 401 khi không có credentials.
- [ ] `api-user` nhận 403 khi gọi Prometheus endpoint.
- [ ] `metrics-scraper` nhận 200 khi gọi Prometheus endpoint.
- [ ] Management port 8081 không được publish ra host trong Compose.
- [ ] Prometheus target `order-service` ở trạng thái `UP`.
- [ ] Counter và Timer xuất hiện trong Prometheus sau khi gọi API.
- [ ] Integration tests cho 401/403/200 chạy thành công.
- [ ] Secret không nằm trong source control.

Dừng và xóa container/network của lab:

```powershell
docker compose down
```

Giữ file secret local nếu muốn chạy lại lab; xóa chúng bằng password manager/quy trình quản lý secret khi không còn cần. Không dùng lại các mật khẩu lab trong môi trường khác.

## 18. Mở rộng sau bài thực hành

Khi hoàn thành luồng scrape cơ bản, có thể mở rộng theo các hướng:

1. Bật histogram cho Timer và truy vấn p95/p99.
2. Thêm `MeterFilter` để giới hạn hoặc chuẩn hóa tag.
3. Thêm `ObservationRegistry` để kết nối metrics với tracing.
4. Chạy Prometheus trong namespace riêng và áp dụng Kubernetes NetworkPolicy chỉ cho phép scraper truy cập management port.
5. Thay Basic Auth bằng mTLS hoặc identity của service mesh.
6. Tạo alert cho scrape target down, request rate và latency.

Khi thay đổi registry hoặc Spring Boot release, giữ dependency theo BOM, kiểm tra dependency graph và chạy lại integration test. Nếu endpoint, authentication hoặc metric naming thay đổi, cập nhật scrape config và dashboard cùng lần nâng cấp.

## Tài liệu tham khảo

- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Spring Boot Endpoint Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.security)
- [Micrometer Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [Prometheus Configuration: Basic Authentication](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#basic_auth)
- [Docker Compose Secrets](https://docs.docker.com/compose/how-tos/use-secrets/)
