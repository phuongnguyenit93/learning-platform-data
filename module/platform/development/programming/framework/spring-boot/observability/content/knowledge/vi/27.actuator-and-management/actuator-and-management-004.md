# Expose management endpoints trong Spring Boot

Expose management endpoints là cấu hình quyết định những endpoint quản trị của Spring Boot Actuator được công bố qua HTTP hoặc JMX. Đây là một phần quan trọng của observability: health, metrics, Prometheus và loggers hỗ trợ vận hành, nhưng các endpoint chẩn đoán cũng có thể tiết lộ cấu hình, environment variables, bean graph hoặc cho phép thay đổi hành vi runtime.

Trong module SPRING_BOOT_OBSERVABILITY, Actuator cung cấp bề mặt quản trị để kiểm tra trạng thái service và truy cập telemetry. Bài thuộc chương Actuator và management, tập trung vào endpoint exposure, enablement, web/JMX, management port/base path, security, Kubernetes probes, kiểm thử và troubleshooting.

## 1. Management endpoint là gì?

Actuator endpoint là điểm truy cập cung cấp thông tin hoặc thao tác quản trị trong ứng dụng Spring Boot. Các endpoint thường gặp:
- health: trạng thái ứng dụng và dependencies.
- info: thông tin ứng dụng được cấu hình công bố.
- metrics: measurements từ Micrometer registry.
- prometheus: metrics exposition cho Prometheus khi registry tương ứng có mặt.
- loggers: đọc hoặc thay đổi log level runtime.
- env/configprops: thông tin cấu hình và property binding.
- beans: danh sách Spring beans.
- threaddump/heapdump: dữ liệu chẩn đoán runtime.

Không phải endpoint nào cũng được expose mặc định. Spring Boot áp dụng chính sách exposure để giới hạn bề mặt truy cập.

### 1.1. Ba khái niệm cần phân biệt

1. **Endpoint enabled:** endpoint có được bật trong application context không.
2. **Exposure:** endpoint được công bố qua transport nào, ví dụ web hoặc JMX.
3. **Access control:** ai có thể truy cập endpoint và từ network/interface nào.

Expose endpoint không đồng nghĩa mọi người đều có quyền truy cập nếu security/network policy được cấu hình đúng. Endpoint không expose qua HTTP vẫn có thể khả dụng qua JMX nếu JMX exposure được bật.

## 2. Cấu hình web exposure

Spring Boot quản lý web exposure qua nhóm property management.endpoints.web.exposure.

Ví dụ chỉ công bố health, info và metrics:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - metrics
```

Nếu cần Prometheus scrape endpoint, thêm prometheus khi registry và endpoint tương ứng có mặt:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - prometheus
```

Tên endpoint là ID của Actuator endpoint, không phải tên URL tùy ý. Đường dẫn mặc định thường có dạng /actuator/{id}, nhưng base path và path mapping có thể thay đổi.

### 2.1. Exclude endpoint

Có thể khai báo danh sách exclude:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - "*"
        exclude:
          - env
          - configprops
          - beans
```

Exclude giới hạn endpoint được expose qua web khi dùng include rộng. Nên bắt đầu bằng allowlist include rõ ràng. Wildcard include có thể vô tình công bố endpoint mới được thêm trong lần nâng cấp Spring Boot sau này.

### 2.2. Wildcard trong YAML

Giá trị * là ký tự đặc biệt trong YAML, vì vậy cần đặt trong dấu nháy:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

Dù wildcard hợp lệ, chỉ nên dùng trong môi trường kiểm thử có kiểm soát. Production nên expose đúng endpoint cần thiết.

## 3. Web exposure và JMX exposure

Actuator hỗ trợ nhiều exposure technologies. Web exposure thường phục vụ HTTP; JMX exposure phục vụ quản trị qua JMX.

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - prometheus
    jmx:
      exposure:
        include:
          - health
          - metrics
```

Một endpoint có thể được expose trên web nhưng không expose qua JMX, hoặc ngược lại. Kiểm tra cả hai transports nếu ứng dụng bật JMX. JMX cũng cần được bảo vệ ở tầng runtime/network.

## 4. Endpoint enablement và exposure

Exposure không phải cách duy nhất điều khiển endpoint. Một số endpoint có thể bị disable bằng property management.endpoint.<id>.enabled; exposure chỉ quyết định endpoint enabled nào được công bố qua transport.

Ví dụ:

```yaml
management:
  endpoint:
    shutdown:
      enabled: false
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
```

Endpoint disabled sẽ không trở nên hoạt động chỉ vì thêm nó vào include. Default enabled state phụ thuộc endpoint và Spring Boot version. Kiểm tra reference documentation của đúng version.

## 5. Các endpoint thường dùng trong observability

| Endpoint | Mục đích | Lưu ý |
| --- | --- | --- |
| health | Trạng thái ứng dụng/dependencies | Có thể chứa component details |
| info | Thông tin service/build | Chỉ công bố field đã chọn |
| metrics | Đọc meter measurements | Chẩn đoán tại process |
| prometheus | Scrape metrics | Cần Prometheus registry |
| loggers | Xem/đổi log level | Thay đổi runtime |
| threaddump | Chẩn đoán thread state | Output có thể lớn |
| heapdump | Tải heap dump | Có thể chứa secrets/PII trong memory |
| env | Xem property sources | Có nguy cơ lộ secrets |
| configprops | Xem bound configuration | Có nguy cơ lộ cấu hình |
| beans | Liệt kê bean graph | Tiết lộ cấu trúc nội bộ |
| mappings | Liệt kê request mappings | Tiết lộ API surface |
| conditions | Auto-configuration report | Phục vụ debug |

Tên endpoint và hành vi phụ thuộc version/dependency. Chỉ expose endpoint mà nhóm vận hành thực sự sử dụng.

## 6. Health endpoint và health details

Health endpoint thường phục vụ orchestration và load balancer. Nó có thể tổng hợp trạng thái database, broker, disk space và custom health indicators.

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
  endpoint:
    health:
      show-details: when-authorized
```

Các giá trị show-details thường gồm never, when-authorized hoặc always tùy version. Production nên giới hạn details cho caller đã được authorize.

### 6.1. Liveness và readiness

Kubernetes phân biệt:
- **Liveness:** process có cần restart hay không.
- **Readiness:** instance có sẵn sàng nhận traffic hay không.

Spring Boot hỗ trợ health groups/probes trong các version phù hợp. Expose health không tự động bảo đảm liveness/readiness paths đã được cấu hình đúng. Kiểm tra health group IDs và deployment probe paths.

### 6.2. Không đưa dependency chậm vào liveness

Nếu liveness phụ thuộc database hoặc broker, dependency outage có thể khiến Kubernetes restart hàng loạt application instances. Liveness nên phản ánh khả năng process tiếp tục chạy; readiness có thể phản ánh dependency cần thiết để phục vụ traffic.

## 7. Metrics và Prometheus exposure

Endpoint metrics cho phép xem meter trong process:

```http
GET /actuator/metrics
GET /actuator/metrics/http.server.requests
```

Prometheus endpoint thường được expose riêng:

```http
GET /actuator/prometheus
```

Để endpoint Prometheus hoạt động, ứng dụng cần Micrometer Prometheus registry. Chỉ expose ID prometheus mà không có registry phù hợp sẽ không tạo metrics exposition.

Actuator metrics endpoint hữu ích để xác minh meter và measurement tại process. Dashboard, alerting, retention và query lịch sử thường do Prometheus hoặc observability backend đảm nhiệm.

Metrics có thể tiết lộ route names, service behavior, traffic volume và dependency details. Giới hạn truy cập bằng network policy, authentication nếu phù hợp và chỉ cho scraper/operator đáng tin cậy.

## 8. Loggers endpoint và runtime changes

Endpoint loggers cho phép đọc cấu hình logger và thay đổi log level runtime.

```http
GET /actuator/loggers/com.example.orders
```

```http
POST /actuator/loggers/com.example.orders
Content-Type: application/json

{
  "configuredLevel": "DEBUG"
}
```

Runtime override có thể chỉ tồn tại trong process và mất khi restart. Endpoint này cần authorization chặt chẽ vì DEBUG/TRACE có thể tăng log volume và nguy cơ lộ dữ liệu. Sau điều tra, hoàn nguyên level và ghi nhận thay đổi.

## 9. Management port và base path

Mặc định Actuator web endpoints thường nằm dưới base path /actuator trên cùng server port. Có thể cấu hình management port riêng:

```yaml
management:
  server:
    port: 9001
  endpoints:
    web:
      base-path: /manage
      exposure:
        include:
          - health
          - prometheus
```

Khi đó endpoint có thể nằm dưới /manage thay vì /actuator. Port/path chính xác phụ thuộc cấu hình ứng dụng.

Management port riêng giúp tách traffic quản trị khỏi traffic ứng dụng, nhưng không tự bảo vệ endpoint. Cần bind vào interface phù hợp, firewall/network policy và authentication/authorization.

### 9.1. Bind address và network boundary

Nếu management server bind trên tất cả network interfaces, endpoint có thể reachable từ nhiều network segments hơn dự kiến. Kiểm tra deployment network, container ports, service definitions và ingress rules. Không expose management port qua public ingress nếu không có kiến trúc bảo vệ rõ ràng.

## 10. Spring Security cho management endpoints

Khi Spring Security có mặt, cấu hình authorization phù hợp với endpoint:
- health/info: có thể cho phép truy cập hẹp hoặc public tùy thông tin trả về.
- prometheus: chỉ scraper được phép.
- metrics: operator/monitoring identity.
- loggers: operator có quyền thay đổi runtime.
- env/configprops/heapdump: quyền quản trị đặc biệt hoặc không expose.

SecurityFilterChain phụ thuộc ứng dụng và Spring Security version. Kiểm tra endpoint paths, management port và các filter chains khác trước khi áp dụng matcher.

### 10.1. Authentication và authorization

Authentication xác định caller là ai. Authorization quyết định caller được phép gọi endpoint nào và thực hiện thao tác gì. Có authentication mà mọi authenticated users đều được gọi heapdump/loggers vẫn là policy quá rộng.

### 10.2. CSRF và thao tác endpoint

Một số Actuator endpoints hỗ trợ POST hoặc thay đổi state. Xem xét CSRF policy và loại client truy cập. Không disable CSRF toàn ứng dụng chỉ để gọi một management endpoint; cấu hình phạm vi hẹp theo use case.

## 11. Endpoint nhạy cảm và data exposure

Một số endpoint tiết lộ thông tin nội bộ hoặc dữ liệu trong memory.

Thận trọng với:
- env/configprops: property values, endpoint URLs, credentials nếu redaction không đúng.
- heapdump: object graph, tokens, secrets, personal data.
- threaddump: thread names, stack traces, class names và request context.
- beans/mappings/conditions: cấu trúc ứng dụng và dependency details.
- loggers: khả năng thay đổi runtime logging.
- shutdown: khả năng tắt ứng dụng nếu endpoint được bật và expose.

Không expose các endpoint này công khai. Dùng allowlist, authorization theo vai trò, network segmentation và audit.

## 12. Cấu hình theo environment

application.yml:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
```

application-local.yml:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - "*"
```

application-prod.yml:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - prometheus
  endpoint:
    health:
      show-details: when-authorized
```

Local có thể expose nhiều endpoint để debug trên máy developer. Production nên công bố endpoint cần cho health checks và metrics scraping, còn endpoint chẩn đoán chỉ mở theo quy trình có kiểm soát.

Không dựa vào profile name để bảo vệ network. Deployment config và security policy vẫn phải được áp dụng.

## 13. Kiểm thử endpoint exposure

Kiểm thử nên xác minh endpoint được công bố và endpoint không được công bố. Có thể dùng Spring Boot integration test với MockMvc hoặc WebTestClient tùy application stack.

```java
@SpringBootTest
@AutoConfigureMockMvc
class ActuatorExposureTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void healthEndpointIsExposed() throws Exception {
        mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
    }
}
```

Ví dụ giả định web base path mặc định và security policy cho phép test caller. Nếu app dùng management port riêng hoặc WebFlux, cấu hình test client tương ứng.

### 13.1. Kiểm tra endpoint bị ẩn

Gửi request tới endpoint không nằm trong include allowlist và xác nhận không thể truy cập qua web. Response có thể là 404 hoặc status khác tùy security/routing configuration.

### 13.2. Kiểm tra authorization

Test caller không có role operator không thể gọi loggers POST hoặc endpoint nhạy cảm. Caller có role phù hợp chỉ được thực hiện thao tác đã cấp.

## 14. Troubleshooting management endpoint exposure

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Endpoint trả 404 | Chưa expose, endpoint disabled hoặc base path khác | Kiểm tra include, enabled và base path |
| Endpoint trả 401 | Chưa authenticate | Kiểm tra authentication |
| Endpoint trả 403 | Caller thiếu quyền | Kiểm tra authorization/role |
| prometheus không tồn tại | Thiếu registry hoặc chưa expose | Kiểm tra dependency và web exposure |
| Health details không xuất hiện | show-details policy không cho caller | Kiểm tra health config và role |
| Endpoint hoạt động local nhưng mất ở prod | Profile/config override | Kiểm tra effective properties |
| Management port không reachable | Port chưa publish, bind/network policy | Kiểm tra container/service/firewall |
| Endpoint public ngoài dự kiến | Ingress hoặc bind address quá rộng | Kiểm tra network path và deployment |
| Endpoint include nhưng không hoạt động | Endpoint disabled hoặc dependency thiếu | Kiểm tra endpoint availability |
| JMX truy cập được dù web đã ẩn | JMX exposure độc lập | Kiểm tra JMX include/exclude |
| Metrics không có dữ liệu | Chưa có meter hoặc registry | Tạo request và kiểm tra MeterRegistry |
| Security config không áp dụng | Filter chain/matcher khác hoặc management context riêng | Kiểm tra security chains và port |
| Endpoint nhạy cảm lộ thông tin | Exposure rộng hoặc role quá permissive | Thu hẹp allowlist và quyền |

### Quy trình điều tra

1. Xác định URL, port và management base path thực tế.
2. Kiểm tra endpoint có enabled không.
3. Kiểm tra web/JMX exposure riêng.
4. Kiểm tra dependency cần cho endpoint, ví dụ Prometheus registry.
5. Kiểm tra authentication và authorization.
6. Kiểm tra management server bind address, ingress và network policy.
7. Kiểm tra profile và property source precedence.
8. Kiểm tra endpoint response có chứa thông tin nhạy cảm không.
9. Kiểm tra logs startup để biết endpoint mapping.
10. Thêm integration tests cho endpoint cần expose và endpoint phải ẩn.

## 15. Bài thực hành: expose Actuator an toàn

Mục tiêu là công bố health và metrics cho monitoring, đồng thời giới hạn endpoint chẩn đoán.

### Chuẩn bị

- Spring Boot application có Actuator.
- MeterRegistry phù hợp.
- Spring Security nếu cần authorization.
- Môi trường local và profile production-like.
- HTTP client hoặc integration test.

### Bước 1 — Chỉ expose health/info

Cấu hình web exposure allowlist gồm health và info. Khởi động ứng dụng và xác minh hai endpoint hoạt động.

### Bước 2 — Expose metrics

Thêm metrics. Gửi request và đọc http.server.requests qua metrics endpoint.

### Bước 3 — Thêm Prometheus registry

Thêm registry phù hợp và expose prometheus. Xác minh endpoint trả exposition format.

### Bước 4 — Thử endpoint bị ẩn

Gọi env, configprops, heapdump và loggers khi chúng không nằm trong allowlist. Xác minh không truy cập được qua web.

### Bước 5 — Thử management port riêng

Cấu hình port/base path riêng. Xác minh application traffic và management traffic đi đúng listener.

### Bước 6 — Cấu hình security

Giới hạn metrics cho scraper/operator. Giới hạn loggers cho operator có quyền thay đổi runtime. Kiểm tra caller không có quyền nhận response phù hợp.

### Bước 7 — Kiểm tra health details

Đặt show-details theo authorization. Xác minh caller thường không thấy dependency details và operator được phép mới thấy.

### Bước 8 — Kiểm tra Kubernetes probes

Cấu hình liveness/readiness paths phù hợp và đảm bảo liveness không phụ thuộc nhầm vào dependency bên ngoài.

### Bước 9 — Kiểm tra network exposure

Xác minh management port không được public ingress route nếu không có yêu cầu và lớp bảo vệ tương ứng.

### Bước 10 — Nghiệm thu

Kiểm tra allowlist, security, port, path, metrics registry và endpoint response. Ghi lại endpoint dành cho scraper, operator và health probes.

### Checklist nghiệm thu

| Điều cần chứng minh | Kết quả mong đợi |
| --- | --- |
| Enablement | Biết endpoint nào enabled |
| Web exposure | Chỉ expose endpoint allowlist |
| JMX exposure | Chính sách riêng, không nhầm với web |
| Metrics | Registry và endpoint phù hợp |
| Prometheus | Endpoint hoạt động khi registry có mặt |
| Security | Authentication/authorization đúng vai trò |
| Management port | Bind/path/network được kiểm soát |
| Health | Details và probes theo policy |
| Sensitive endpoints | env/heapdump/loggers được bảo vệ |
| Profiles | Local và production có exposure phù hợp |
| Testing | Endpoint cần có và endpoint phải ẩn đều được test |
| Operations | Có quy trình thay đổi và audit |

## 16. Những nguyên tắc cần ghi nhớ

1. **Enablement, exposure và authorization là ba lớp khác nhau.** Endpoint enabled chưa chắc được expose; exposed chưa có nghĩa caller được phép.
2. **Ưu tiên allowlist include rõ ràng.** Wildcard có thể công bố endpoint mới trong lần nâng cấp.
3. **Web và JMX exposure độc lập.** Kiểm tra cả hai transports.
4. **Metrics/Prometheus cần registry phù hợp.** Expose endpoint ID không tự tạo exporter.
5. **Management port riêng không tự bảo vệ endpoint.** Network policy, bind address và security vẫn cần thiết.
6. **Health details cần giới hạn.** Phân biệt liveness với readiness và tránh dependency outage gây restart loop.
7. **Bảo vệ endpoint nhạy cảm.** env, configprops, heapdump, threaddump, beans và loggers có thể tiết lộ hoặc thay đổi trạng thái ứng dụng.
8. **Authentication không thay authorization.** Cấp quyền theo endpoint và thao tác cụ thể.
9. **Cấu hình theo environment có kiểm chứng.** Kiểm tra effective properties và deployment routing.
10. **Test cả endpoint được expose lẫn endpoint bị ẩn.** Kiểm tra response và quyền caller.

Expose management endpoints đúng cách giúp monitoring và operator truy cập tín hiệu cần thiết mà vẫn giới hạn bề mặt quản trị. Khi phân biệt enablement, transport exposure và access control, dùng allowlist, tách management network hợp lý và kiểm thử theo role, Spring Boot Actuator có thể hỗ trợ observability production mà không công bố quá nhiều thông tin nội bộ.
