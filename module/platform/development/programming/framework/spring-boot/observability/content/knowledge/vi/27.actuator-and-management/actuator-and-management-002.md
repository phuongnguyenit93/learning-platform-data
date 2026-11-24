# Management server trong Spring Boot

Một ứng dụng Spring Boot phục vụ traffic người dùng trên cổng 8080, đồng thời expose health checks, metrics và thông tin vận hành. Nếu các management endpoints dùng chung listener với API công khai, chúng có thể chịu cùng network exposure và traffic policy. Spring Boot cho phép cấu hình **management server** để điều khiển cách các Actuator endpoints được phục vụ: dùng chung web server với ứng dụng hoặc chạy trên cổng riêng, với địa chỉ, base path và SSL policy phù hợp.

Management server là phần web infrastructure phục vụ Actuator endpoints. Nó không phải metrics backend hay tracing Collector. Cấu hình management server quyết định nơi các endpoints như /actuator/health, /actuator/metrics và /actuator/prometheus có thể được truy cập; endpoint nào thực sự tồn tại và được expose còn phụ thuộc dependencies, endpoint exposure và security configuration.

Bài **Management server** thuộc chương **Actuator và management** của module **SPRING_BOOT_OBSERVABILITY**. Module tập trung thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của management server trong Spring Boot Actuator.
- Phân biệt management endpoints dùng chung application port và chạy trên port riêng.
- Cấu hình management port, address, base path và SSL theo nhu cầu.
- Hiểu endpoint availability, exposure và authorization là ba lớp khác nhau.
- Thiết kế management network boundary để chỉ hệ thống vận hành truy cập.
- Cấu hình health/readiness/liveness endpoints cho môi trường triển khai.
- Kiểm tra metrics endpoints mà không expose quá mức.
- Chẩn đoán lỗi bind port, 404, 401/403 và health check thất bại.

## 2. Management server là gì?

Spring Boot Actuator cung cấp endpoints cho health, metrics, environment, beans, mappings và nhiều thông tin vận hành khác. Management server là HTTP server surface mà các endpoints này được expose.

Trong cấu hình mặc định, Actuator endpoints thường dùng cùng web server/port với ứng dụng, dưới base path /actuator. Ví dụ:

```text
Application API:       http://localhost:8080/api/orders
Management health:     http://localhost:8080/actuator/health
Management metrics:    http://localhost:8080/actuator/metrics
```

Nếu cấu hình management port riêng, endpoints có thể được phục vụ trên listener khác:

```text
Application API:       http://localhost:8080/api/orders
Management health:     http://localhost:8081/actuator/health
Management metrics:    http://localhost:8081/actuator/metrics
```

Port và path trên chỉ là ví dụ. Management server có thể dùng web server riêng hoặc listener riêng tùy cấu hình và web application type.

## 3. Dùng chung port hay port riêng?

| Mô hình | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| Same port | Actuator endpoints cùng listener với application endpoints | Hệ thống đơn giản, đã có gateway/security/network controls |
| Separate management port | Management endpoints phục vụ trên cổng riêng | Cần network boundary và routing policy riêng cho vận hành |
| Separate management address | Listener management bind vào interface/address cụ thể | Host có nhiều network interfaces và cần giới hạn interface |

Port riêng không tự động làm endpoint an toàn. Nếu firewall/security group cho phép internet truy cập port đó, management endpoints vẫn có thể bị lộ. Kết hợp bind address, firewall, Kubernetes NetworkPolicy, service routing và Spring Security.

### Khi nào không cần port riêng?

Một số môi trường dùng service mesh hoặc ingress policy có thể bảo vệ cùng application port bằng route allow-list. Khi đó management endpoints chỉ được truy cập từ internal network hoặc monitoring agents. Điều quan trọng là boundary thực tế và policy được kiểm chứng, không phải chỉ con số port.

## 4. Cấu hình management port

Đặt management port riêng:

```yaml
server:
  port: 8080
management:
  server:
    port: 8081
```

Sau khi cấu hình, ứng dụng API tiếp tục nghe trên port 8080, còn management server dùng port 8081. Nếu management.server.port không được đặt, management endpoints thường dùng application web server.

### Bind management address

Ví dụ chỉ bind management listener vào loopback:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
```

Địa chỉ loopback chỉ phù hợp nếu management client chạy cùng host/network namespace. Trong container/Kubernetes, bind 127.0.0.1 có thể khiến kubelet, sidecar hoặc monitoring agent bên ngoài container không truy cập được. Chọn address theo network topology thực tế.

### Management base path

Có thể đổi base path:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
```

Khi đó health endpoint có thể là /manage/health trên management port. Base path thay đổi URL; nó không thay thế authentication hoặc network restriction.

## 5. Management server SSL

Nếu management server chạy trên port riêng, có thể cấu hình SSL riêng theo property hỗ trợ của Spring Boot version:

```yaml
server:
  port: 8080
management:
  server:
    port: 8443
    ssl:
      enabled: true
      key-store: classpath:management-keystore.p12
      key-store-type: PKCS12
      key-store-password: $MANAGEMENT_KEYSTORE_PASSWORD$
```

Ví dụ minh họa cấu hình TLS; property details và khả năng dùng SSL riêng phụ thuộc Spring Boot version. Không commit keystore password hoặc private key vào source control. Dùng secret management và certificate rotation phù hợp.

Nếu management endpoints được terminate TLS tại ingress/proxy, xác minh traffic giữa proxy và application cũng được bảo vệ theo threat model. TLS ở edge không tự bảo vệ mọi network hop bên trong cluster.

## 6. Endpoint availability, exposure và security

Ba khái niệm này khác nhau:

1. **Availability:** endpoint có tồn tại hay không, thường phụ thuộc dependency/auto-configuration.
2. **Exposure:** endpoint được đưa ra web/JMX surface nào.
3. **Authorization:** caller nào được phép truy cập endpoint.

Ví dụ chỉ expose một số web endpoints:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Danh sách endpoint cần expose phụ thuộc mục đích và registry. Không dùng wildcard * trong production nếu chưa đánh giá từng endpoint. Một số endpoints như env, configprops, beans, heapdump hoặc threaddump có thể tiết lộ thông tin nhạy cảm hoặc tiêu tốn tài nguyên.

### Exposure không phải authentication

Việc thêm metrics vào exposure list chỉ làm endpoint có thể được phục vụ qua web; nó không tự yêu cầu login. Bảo vệ endpoints bằng Spring Security hoặc network access controls.

Ví dụ security matcher cần được điều chỉnh theo Spring Security version và yêu cầu ứng dụng:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/actuator/health/**").permitAll()
            .requestMatchers("/actuator/**").hasRole("OPS")
            .anyRequest().authenticated()
        )
        .build();
}
```

Ví dụ minh họa authorization policy cho same-port setup. Nếu management port riêng và có security chain riêng, cần matcher/chain order và actuator request matcher đúng. Không mở toàn bộ endpoints chỉ để health probe truy cập.

## 7. Health, readiness và liveness

Health endpoints giúp platform xác định trạng thái ứng dụng. Với Spring Boot Actuator, các health groups có thể phục vụ probe riêng:

- **Liveness:** process có còn hoạt động và có thể tiếp tục chạy không?
- **Readiness:** instance có sẵn sàng nhận traffic mới không?
- **Overall health:** các health indicators được cấu hình đang báo trạng thái gì?

Ví dụ cấu hình probes:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
```

Các paths thường gặp trong môi trường hỗ trợ probes:

```text
/actuator/health/liveness
/actuator/health/readiness
```

Probe endpoints có thể được expose theo cấu hình và Spring Boot version. Kiểm tra chúng trong application runtime thay vì giả định chỉ bật property là đủ.

### Không đưa mọi dependency vào liveness

Nếu database hoặc Kafka tạm thời mất kết nối, liveness check phụ thuộc các dịch vụ đó có thể đánh dấu process là dead và khiến orchestrator restart liên tục. Liveness nên phản ánh khả năng process tự phục hồi; readiness có thể phản ánh instance hiện có nhận traffic được không. Chọn health indicators và groups theo failure semantics của ứng dụng.

### Management port riêng và health probes

Nếu Kubernetes probe được cấu hình gọi port 8081, management server phải bind vào interface có thể truy cập từ kubelet/container network. Nếu bind loopback hoặc TLS mismatch, probe có thể fail dù application port vẫn khỏe. Kiểm tra probe scheme, port, path, headers và certificate policy.

## 8. Metrics và Prometheus endpoint

Management server có thể expose Actuator metrics và Prometheus scrape endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Prometheus registry dependency phải có trong application. Endpoint thường là:

```text
/actuator/prometheus
```

Nếu management port riêng, scrape target phải dùng management port và base path tương ứng. Prometheus scrape thành công chỉ chứng minh metrics endpoint trả dữ liệu; nó không chứng minh tracing exporter hoặc logs pipeline hoạt động.

### Không expose metrics công khai

Metrics có thể tiết lộ route names, dependency topology, throughput, error rates và internal service behavior. Hạn chế truy cập endpoint bằng internal network, authenticated scrape hoặc service monitor policy. Chỉ expose các endpoints cần thiết cho monitoring.

## 9. Environment-specific management configuration

Management server thường có cấu hình khác nhau theo môi trường:

```yaml
spring:
  config:
    activate:
      on-profile: local
management:
  server:
    port: 8081
    address: 127.0.0.1
```

Trong production, port/address có thể được cấp qua environment variables hoặc deployment configuration. Ví dụ:

```text
MANAGEMENT_SERVER_PORT=8081
MANAGEMENT_SERVER_ADDRESS=0.0.0.0
MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=health,metrics,prometheus
```

Các environment variables tuân theo relaxed binding của Spring Boot. Nếu dùng profile-specific files, profile có thể override base configuration; kiểm tra effective configuration trong runtime mà không in secrets.

## 10. Management server và các web application types

Spring Boot có thể chạy Servlet-based web application hoặc reactive WebFlux application. Management web infrastructure và việc tạo separate management context/server phụ thuộc application type, classpath và version.

Không giả định management port riêng luôn tạo một process riêng. Thông thường vẫn là cùng JVM/process nhưng có listener/context riêng. Nếu dùng custom embedded server, reverse proxy hoặc management context configuration, kiểm tra thực tế các listeners và ports đang mở.

### Port collision

Nếu management port đã được process khác sử dụng, startup có thể thất bại với bind exception. Kiểm tra port bị chiếm, host networking/replica collisions, container targetPort, management address và TLS keystore.

## 11. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| /actuator/health trả 404 | Actuator thiếu, base path khác hoặc endpoint không được expose | Kiểm tra dependency, base-path và exposure |
| Management port không listen | management.server.port chưa bind hoặc startup fail | Đọc startup logs và effective config |
| Port bind exception | Port đã được dùng hoặc address không tồn tại | Kiểm tra process/port mapping và bind address |
| API port khỏe nhưng management port fail | Listener management riêng bị lỗi hoặc network policy chặn | Kiểm tra listener, firewall và service routing |
| Health probe timeout | Sai port/path/scheme hoặc bind address không reachable | Kiểm tra probe từ đúng network namespace |
| Health readiness DOWN | Health indicator báo dependency chưa sẵn sàng | Xem component details và readiness policy |
| Liveness restart loop | Liveness phụ thuộc external service không ổn định | Tách liveness khỏi dependency checks phù hợp |
| /actuator/metrics 401/403 | Security policy yêu cầu role/auth | Kiểm tra credentials và matcher |
| Prometheus scrape 404 | Endpoint chưa expose hoặc registry thiếu | Kiểm tra dependency và exposure |
| Prometheus scrape timeout | Network route hoặc management server quá tải | Kiểm tra service monitor, port và resource |
| TLS handshake failure | Certificate, trust chain, hostname hoặc scheme sai | Kiểm tra TLS client/server configuration |
| Endpoint nhạy cảm bị lộ | Exposure quá rộng hoặc network boundary sai | Thu hẹp include list và access policy |

### Checklist triển khai

1. Chọn same port hay separate management port dựa trên network boundary.
2. Xác định management address có thể truy cập từ probe/monitoring agent.
3. Cấu hình base path và SSL theo môi trường.
4. Chỉ expose endpoints cần thiết.
5. Bảo vệ endpoints bằng authentication/authorization và network controls.
6. Tách readiness/liveness theo đúng failure semantics.
7. Cập nhật Kubernetes probes/service monitor tới đúng port/path.
8. Kiểm tra port listeners, TLS, status codes và scrape output sau deploy.

## 12. Thực hành: tách management server khỏi application API

**Bối cảnh:** order-service phục vụ API trên port 8080. Monitoring agent cần scrape metrics và Kubernetes cần health probes. Nhóm muốn management server trên port 8081 và chỉ internal network truy cập được.

### Phần A — Chuẩn bị

1. Thêm Spring Boot Actuator và Prometheus registry.
2. Đặt application port 8080 và management port 8081.
3. Cấu hình management address theo network namespace phù hợp.
4. Expose health, metrics và prometheus.
5. Bảo vệ management endpoints theo policy.
6. Cấu hình liveness/readiness probes tới management port.

### Phần B — Kiểm chứng

| Ca | Thao tác | Kết quả cần quan sát |
| --- | --- | --- |
| A — Application | Gọi API trên port 8080 | API vẫn phục vụ request |
| B — Health | Gọi /actuator/health trên port 8081 | Health endpoint trả trạng thái |
| C — Metrics | Gọi /actuator/metrics với quyền phù hợp | Meter list có thể truy cập |
| D — Prometheus | Scrape /actuator/prometheus | Metrics exposition được trả |
| E — Unauthorized | Gọi endpoint bảo vệ không credentials | Nhận 401/403 theo policy |
| F — Network boundary | Thử truy cập từ network không được phép | Kết nối bị chặn |
| G — Probe | Chạy readiness/liveness checks | Probe tới đúng scheme/port/path |
| H — Port conflict | Dùng management port đang bị chiếm trong test | Startup báo bind failure rõ ràng |

### Phần C — Câu hỏi tự đánh giá

1. Management server khác application server ở vai trò nào?
2. Vì sao port riêng không tự động bảo vệ Actuator endpoints?
3. Availability, exposure và authorization khác nhau như thế nào?
4. Khi nào nên bind management server vào loopback?
5. Vì sao liveness không nên phụ thuộc mọi external dependencies?
6. Nếu Prometheus scrape target vẫn dùng port 8080 sau khi chuyển management port sang 8081, điều gì xảy ra?
7. Vì sao cần kiểm tra base path sau khi thay đổi?
8. Management SSL khác TLS termination ở ingress như thế nào?
9. Làm thế nào để health probes truy cập management port trong container?
10. Những endpoints nào cần cân nhắc kỹ trước khi expose công khai?

## 13. Ghi nhớ

**Management server** quyết định Actuator endpoints được phục vụ ở đâu và qua listener nào. Spring Boot có thể dùng chung application port hoặc cấu hình management port riêng bằng management.server.port; address, base path và SSL có thể được điều chỉnh theo network topology và version.

Endpoint availability, web exposure và security authorization là ba lớp riêng. Port riêng không thay thế authentication, firewall hoặc network policy. Chỉ expose health/metrics endpoints cần thiết, bảo vệ thông tin vận hành và cấu hình probes tới đúng port/path. Phân biệt liveness với readiness để dependency outage không gây restart loop. Sau triển khai, xác minh listeners, TLS, status codes, access policy và Prometheus scrape từ đúng network boundary. Quản lý management server đúng cách giúp quan sát Spring Boot an toàn mà vẫn hỗ trợ health checks, metrics và vận hành production.
