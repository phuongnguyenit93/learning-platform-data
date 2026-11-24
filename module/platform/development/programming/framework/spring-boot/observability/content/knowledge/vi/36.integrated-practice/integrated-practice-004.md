# Cấu hình Prometheus endpoint cho Spring Boot

Trong môi trường production, ứng dụng Spring Boot cần cung cấp một endpoint metrics để Prometheus có thể scrape định kỳ. Spring Boot Actuator kết hợp với Micrometer Prometheus registry tạo endpoint `/actuator/prometheus`, nơi ứng dụng xuất các meter dưới định dạng Prometheus có thể đọc. Bài thực hành này cấu hình dependency, endpoint, quyền truy cập và scrape job, sau đó xác minh dữ liệu đã xuất hiện trong Prometheus.

Bài này thuộc chương **Thực hành tổng hợp** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; bao gồm propagation ngữ cảnh, tag và cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực. Bài tập tập trung vào luồng metrics từ Spring Boot qua Actuator đến Prometheus.

## 1. Hiểu luồng scrape

Prometheus thường dùng mô hình pull: Prometheus chủ động gọi HTTP endpoint của ứng dụng theo chu kỳ và lưu các sample nhận được. Ứng dụng không cần chủ động gửi metric đến Prometheus.

```mermaid
flowchart LR
    A[HTTP request đến Spring Boot] --> B[Micrometer meters]
    B --> C[PrometheusMeterRegistry]
    C --> D[/actuator/prometheus]
    E[Prometheus server] -->|HTTP scrape định kỳ| D
    D -->|Prometheus exposition format| E
    E --> F[PromQL và dashboard]
```

Các thành phần có trách nhiệm riêng:

- **Spring Boot Actuator:** cung cấp endpoint quản trị và quan sát cho ứng dụng.
- **Micrometer:** thu thập, chuẩn hóa và quản lý các meter như Counter, Timer và Gauge.
- **Prometheus registry:** chuyển meter thành định dạng exposition mà Prometheus hiểu.
- **Prometheus server:** scrape endpoint, lưu time series và cho phép truy vấn bằng PromQL.

Endpoint `/actuator/metrics` và `/actuator/prometheus` phục vụ hai mục đích khác nhau. `/actuator/metrics` giúp kiểm tra meter qua API Actuator; `/actuator/prometheus` xuất dữ liệu theo định dạng scrape. Chỉ thêm Actuator mà thiếu Prometheus registry thì chưa đủ để có endpoint Prometheus.

## 2. Thêm dependency

Ứng dụng cần Actuator và Micrometer Prometheus registry. Dùng dependency management của Spring Boot để chọn phiên bản tương thích với phiên bản Spring Boot đang chạy.

### Gradle

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

### Maven

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Prometheus registry được nạp khi ứng dụng khởi động. Spring Boot auto-configuration sẽ tạo registry phù hợp nếu dependency có mặt và không bị cấu hình loại trừ. Tránh tự ghim phiên bản Micrometer khác với phiên bản được Spring Boot quản lý trừ khi có lý do tương thích rõ ràng.

## 3. Cấu hình endpoint trong Spring Boot

Khai báo tên ứng dụng và expose endpoint Prometheus trong `application.yml`:

```yaml
spring:
  application:
    name: orders-service

management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    tags:
      application: ${spring.application.name}
      environment: ${APP_ENV:local}
```

Giải thích:

- `spring.application.name` đặt tên logic của ứng dụng.
- `management.endpoints.web.exposure.include` cho phép endpoint `prometheus` được truy cập qua HTTP. Endpoint phải được expose thì Prometheus mới scrape được.
- `management.metrics.tags` thêm common tags vào các meter để phân tích theo ứng dụng và môi trường.

Mặc định, management endpoint dùng base path `/actuator`, nên URL scrape là `http://<host>:<port>/actuator/prometheus`. Có thể đổi base path bằng `management.endpoints.web.base-path`, nhưng khi đổi cần cập nhật `metrics_path` ở Prometheus tương ứng.

Không expose tất cả endpoint bằng `include: "*"` chỉ để bật Prometheus. Các endpoint quản trị như `env`, `configprops`, `beans` hoặc `heapdump` có thể tiết lộ thông tin nhạy cảm. Chỉ expose endpoint cần dùng và áp dụng chính sách bảo vệ phù hợp.

### 3.1. Phân biệt expose và enable

Expose quyết định endpoint có được đưa ra qua transport web hay không. Enable quyết định endpoint có được bật hay không. Một endpoint bị disable sẽ không hoạt động dù đã nằm trong danh sách exposure. Prometheus endpoint thường được auto-configure khi registry có mặt; nếu dự án đã tùy chỉnh `management.endpoint.*` hoặc tắt endpoint, hãy kiểm tra cấu hình đó.

### 3.2. Dùng management port riêng

Trong môi trường production, có thể tách management endpoint khỏi cổng phục vụ request:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Khi cấu hình này có hiệu lực, Prometheus phải scrape cổng `8081`, không phải cổng ứng dụng `8080`. Có thể kết hợp firewall, Kubernetes NetworkPolicy hoặc mạng nội bộ để chỉ Prometheus được truy cập cổng management. Cấu hình địa chỉ bind và Service cần phù hợp với môi trường chạy; đừng bind management port vào loopback nếu Prometheus chạy ở container hoặc máy khác.

## 4. Bảo vệ Prometheus endpoint

Endpoint metrics có thể tiết lộ tên service, route, trạng thái dependency và các chi tiết vận hành. Trong production, chỉ cho phép Prometheus hoặc hệ thống giám sát được truy cập. Có thể dùng private network, firewall, network policy, reverse proxy hoặc Spring Security.

Nếu ứng dụng dùng Spring Security, tích hợp quy tắc cho endpoint scrape vào `SecurityFilterChain` hiện có. Ví dụ sau minh họa một tài khoản có role riêng cho scraper; cần điều chỉnh matcher và các quy tắc còn lại theo chính sách xác thực của ứng dụng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/actuator/prometheus").hasRole("METRICS_SCRAPER")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Tạo credential scraper bằng cơ chế quản lý người dùng và secret của hệ thống. Không ghi password production vào source code, Git hoặc image container. Nếu ứng dụng dùng management port riêng, kiểm tra cấu hình security matcher và management security context để bảo đảm endpoint trên cổng đó được bảo vệ như mong muốn.

Prometheus hỗ trợ Basic Authentication trong scrape config. Ví dụ dùng file secret được mount vào Prometheus:

```yaml
scrape_configs:
  - job_name: orders-service
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["orders-service:8080"]
    basic_auth:
      username: prometheus
      password_file: /etc/prometheus/secrets/orders-service-password
```

Tài khoản và mật khẩu trong ví dụ phải khớp với credential đã cấu hình ở ứng dụng. Đường dẫn `password_file` là đường dẫn bên trong môi trường chạy Prometheus; mount secret với quyền đọc tối thiểu. Nếu dùng management port riêng, đổi target thành cổng management. Nếu hệ thống dùng TLS hoặc reverse proxy, khai báo scheme và các thiết lập xác thực tương ứng.

## 5. Cấu hình Prometheus scrape job

Trong `prometheus.yml`, khai báo target và endpoint path:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: orders-service
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets:
          - orders-service:8080
        labels:
          environment: production
```

`orders-service:8080` là ví dụ về DNS/service name mà Prometheus có thể phân giải trong cùng mạng triển khai. Nếu Prometheus chạy trực tiếp trên máy phát triển và ứng dụng chạy local, target có thể là `localhost:8080`. Nếu hai tiến trình chạy trong hai container riêng, `localhost` của Prometheus trỏ về chính container Prometheus; hãy dùng tên service hoặc địa chỉ có thể truy cập từ mạng của Prometheus.

Nếu endpoint được bảo vệ, thêm `basic_auth` như phần trước. Nếu dùng management port riêng, ví dụ `8081`, target phải là `orders-service:8081`. Nếu base path hoặc endpoint path đã được tùy chỉnh, cập nhật `metrics_path` tương ứng.

Sau khi thay đổi cấu hình, reload Prometheus theo cơ chế triển khai đang dùng hoặc khởi động lại tiến trình nếu reload chưa được bật. Đảm bảo YAML hợp lệ trước khi áp dụng vào production.

## 6. Chạy thử và xác minh endpoint

Khởi động ứng dụng với profile cần kiểm tra. Dùng `curl` gọi endpoint:

```bash
curl -i http://localhost:8080/actuator/prometheus
```

Nếu endpoint được bảo vệ bằng Basic Authentication, có thể kiểm tra bằng:

```bash
curl -i -u prometheus:"$METRICS_PASSWORD" \
  http://localhost:8080/actuator/prometheus
```

Không truyền mật khẩu thật trực tiếp trong lệnh lưu vào shell history hoặc log chia sẻ. Với môi trường production, dùng secret manager và cách gọi an toàn theo quy trình vận hành của tổ chức.

Khi cấu hình đúng, response thường có HTTP `200` và nội dung Prometheus exposition, ví dụ:

```text
# HELP jvm_memory_used_bytes The amount of used memory
# TYPE jvm_memory_used_bytes gauge
jvm_memory_used_bytes{area="heap",id="...",application="orders-service",environment="production"} ...
```

Tên metric và tag thực tế phụ thuộc phiên bản, registry và meter đã được đăng ký. Ví dụ trên chỉ minh họa cấu trúc; không yêu cầu mọi ứng dụng phải có chính xác các nhãn đó.

### 6.1. Kiểm tra các nhóm metric

Tìm một số nhóm meter thường có trong ứng dụng Spring Boot:

- JVM: `jvm_memory_used_bytes`, `jvm_gc_pause_seconds`.
- HTTP server: `http_server_requests_seconds_count`, `http_server_requests_seconds_sum` và histogram bucket nếu đã bật.
- Process: `process_cpu_usage`, `process_uptime`.
- System: `system_cpu_usage` hoặc các meter hệ thống tương ứng.

Các meter có thể chưa xuất hiện cho đến khi tính năng tương ứng được khởi tạo hoặc có hoạt động. Hãy tạo một vài request HTTP để phát sinh meter request trước khi kết luận endpoint thiếu dữ liệu.

## 7. Xác minh target trong Prometheus

Mở giao diện Prometheus, thường là `http://localhost:9090/targets`, rồi kiểm tra job `orders-service`:

- **UP:** lần scrape gần nhất thành công.
- **DOWN:** Prometheus không kết nối được hoặc endpoint trả lỗi; xem cột error để biết chi tiết.
- **Target không xuất hiện:** kiểm tra `prometheus.yml`, reload, service discovery và cấu hình target.

Trong trang query, chạy các truy vấn sau:

```promql
up{job="orders-service"}
```

Giá trị `1` nghĩa là Prometheus scrape target thành công; `0` nghĩa là lần scrape thất bại. Tiếp theo, kiểm tra metric JVM:

```promql
jvm_memory_used_bytes{application="orders-service"}
```

Sau khi gửi request tới API, kiểm tra số request đã được ghi nhận:

```promql
sum(rate(http_server_requests_seconds_count{
  application="orders-service"
}[5m]))
```

Nếu common tag `application` không có trong dữ liệu, bỏ matcher hoặc dùng nhãn thực tế mà endpoint xuất ra. Tên metric và label phải được xác nhận từ exposition trước khi viết dashboard và alert.

## 8. Thêm common tags và kiểm soát cardinality

Common tags giúp phân tích dữ liệu theo service và môi trường. Có thể khai báo thêm các tag có tập giá trị nhỏ:

```yaml
management:
  metrics:
    tags:
      application: ${spring.application.name}
      environment: ${APP_ENV:local}
      region: ${APP_REGION:local}
```

Không thêm `userId`, `orderId`, email, session ID, trace ID hoặc URL chứa mã động vào metric tags. Mỗi giá trị tag mới có thể tạo thêm time series, làm tăng bộ nhớ và chi phí truy vấn Prometheus. Dùng log hoặc trace để điều tra theo request cụ thể; metric giữ nhãn ổn định như route template, method, status và nhóm nghiệp vụ.

Nếu triển khai nhiều replica, Prometheus sẽ scrape từng target. Giữ nhãn target như `instance` để điều tra theo replica; khi truy vấn SLI toàn service, tổng hợp qua các instance thay vì tính tỷ lệ riêng rồi lấy trung bình các tỷ lệ đó.

## 9. Những lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| HTTP 404 tại `/actuator/prometheus` | Thiếu Prometheus registry, endpoint chưa expose, base path đã đổi hoặc endpoint bị disable | Kiểm tra dependency, exposure, enable và URL thực tế |
| HTTP 401 | Endpoint yêu cầu xác thực nhưng Prometheus chưa gửi credential hoặc credential sai | Kiểm tra Basic Auth, secret mount và user ở ứng dụng |
| HTTP 403 | User đã xác thực nhưng thiếu quyền hoặc request bị chặn bởi security/network policy | Kiểm tra role và SecurityFilterChain đang áp dụng |
| Connection refused hoặc timeout | Sai host/port, management port riêng, bind address hoặc network policy | Kiểm tra target từ chính môi trường Prometheus và port đang lắng nghe |
| Prometheus target DOWN | Endpoint trả lỗi hoặc scrape path/timeout sai | Mở trang Targets, đọc scrape error và thử gọi URL từ Prometheus host/container |
| Target UP nhưng không thấy HTTP metric | Chưa có request, meter không được tạo, filter truy vấn sai hoặc metric name khác | Gửi request thử, xem raw endpoint và kiểm tra tên label |
| Có metric nhưng thiếu tag mong muốn | Common tag chưa cấu hình hoặc truy vấn dùng sai label | Kiểm tra `management.metrics.tags` và exposition thực tế |
| Scrape chậm hoặc timeout | Endpoint có quá nhiều time series, ứng dụng quá tải hoặc scrape timeout quá thấp | Kiểm soát cardinality, xem response size và điều chỉnh interval/timeout theo tải |

Không dùng cách expose mọi Actuator endpoint để xử lý lỗi 404. Trước tiên xác định endpoint nào đang thiếu và nguyên nhân là dependency, enable hay exposure. Sau khi khắc phục, xác minh lại quyền truy cập để không vô tình mở rộng bề mặt quản trị.

## 10. Checklist triển khai production

- [ ] Có `spring-boot-starter-actuator` và `micrometer-registry-prometheus` tương thích với Spring Boot.
- [ ] Endpoint `prometheus` được expose và không bị disable.
- [ ] `metrics_path` và target port trong Prometheus khớp với cấu hình Spring Boot.
- [ ] Prometheus scrape được endpoint từ đúng network namespace.
- [ ] Endpoint được giới hạn bằng private network, firewall, network policy hoặc xác thực phù hợp.
- [ ] Không expose toàn bộ Actuator endpoint nếu không có yêu cầu cụ thể.
- [ ] Common tags dùng giá trị ổn định, cardinality thấp.
- [ ] Prometheus target hiển thị `UP` và truy vấn được metric JVM/HTTP.
- [ ] Dashboard và alert dùng đúng tên metric, label đã xác minh.
- [ ] Có giám sát trạng thái scrape và xử lý khi target biến mất.

Khi hoàn thành, Spring Boot cung cấp metrics qua Actuator và Prometheus scrape chúng theo chu kỳ đã cấu hình. Hãy xác minh từ endpoint của ứng dụng đến trang Targets và truy vấn PromQL; chỉ khi cả ba bước hoạt động, pipeline metrics mới sẵn sàng cho dashboard và cảnh báo production.
