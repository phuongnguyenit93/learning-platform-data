# Cấu hình sampling, endpoint và thông tin xác thực

## 1. Ba quyết định phải tách riêng khi triển khai telemetry

Một ứng dụng Spring AI có thể gọi model nhiều lần, truy xuất tài liệu RAG, gọi công cụ nghiệp vụ và chạy qua nhiều service. Khi người dùng báo câu trả lời sai hoặc chậm, nhóm cần biết request đó đi qua đâu, dữ liệu nào đã được truy xuất, tool trả kết quả gì và model đã thực hiện bao nhiêu lượt gọi.

Để vận hành tracing an toàn, phải thiết kế ba lớp độc lập:

1. **Sampling:** chọn trace/span nào được ghi và xuất, với tỷ lệ và quy tắc nào.
2. **Endpoint:** xác định đúng địa chỉ, port, path và protocol của nơi nhận hoặc nơi scrape.
3. **Authentication/authorization:** xác định ai được gửi, ai được đọc và ai được thay đổi cấu hình; bảo vệ đường truyền bằng TLS/mTLS khi phù hợp.

Ba lớp này giải quyết các câu hỏi khác nhau. Sampling 10% không bảo vệ nội dung của 10% trace được giữ. Endpoint đúng không chứng minh client có quyền gửi. Có bearer token không làm cho một endpoint sai protocol trở thành đúng.

Trong module `SPRING_AI_EVALUATION_OBSERVABILITY`, telemetry phải hỗ trợ cả đánh giá chất lượng lẫn vận hành:

- **Relevance/factual correctness:** evaluator so câu trả lời với reference và bằng chứng.
- **RAG/tool correctness:** kiểm tra tài liệu đã lấy, quyền và tool events.
- **Metrics/traces:** phân tích lỗi, độ trễ, token usage và số lượt gọi.
- **Chi phí:** tính từ usage thực và bảng giá có hiệu lực, không suy đoán từ trace.

Trace giúp tìm nguyên nhân của một lần chạy; **trace không thay thế kết quả đánh giá**. Một ca FAIL vẫn phải được lưu nếu trace bị sampling loại, miễn runner đã giữ output, retrieved evidence và tool events theo hợp đồng dữ liệu.

### Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt trace sampling với Prometheus scrape interval và metric aggregation.
- Chọn head-based, parent-based hoặc tail-based sampling.
- Cấu hình tỷ lệ sampling cho local, staging và production.
- Phân biệt OTLP/HTTP, OTLP/gRPC, Prometheus scrape, trace ingest và query endpoints.
- Cấu hình bearer token, basic authentication, TLS/mTLS và phân quyền endpoint.
- Lưu secrets ngoài source code và kiểm tra cấu hình thực tế sau khi triển khai.
- Kiểm tra exporter, collector, backend và Grafana bằng các tình huống thành công/thất bại.
- Liên kết trace với `runId/caseId/attemptId` mà không tạo metric cardinality cao hoặc rò dữ liệu.

## 2. Kiến trúc và ranh giới tin cậy

Một tuyến tracing phổ biến:

~~~mermaid
flowchart LR
    U["User / Evaluation runner"] --> APP["Spring Boot + Spring AI"]
    APP --> R["Retriever / vector store"]
    APP --> M["Chat model"]
    APP --> T["Tools / APIs"]
    APP --> BR["Micrometer Tracing bridge"]
    BR --> EX["OTLP exporter"]
    EX -->|TLS + auth| COL["Collector receiver"]
    COL --> PROC["Batch / filter / tail sampling"]
    PROC --> BE["Tempo / Jaeger / trace backend"]
    APP --> MET["Micrometer MeterRegistry"]
    MET --> ACT["Actuator Prometheus endpoint"]
    PROM["Prometheus"] -->|scrape + auth| ACT
    PROM --> GF["Grafana"]
    BE --> GF
    APP --> EV["Evaluator: reference + rubric"]
    EV --> RS["Evaluation result store"]
    RS --> GF
~~~

| Thành phần | Vai trò | Ranh giới cần bảo vệ |
|---|---|---|
| Spring AI application | Phát sinh observations, meters, spans | Input, retrieved content, tool payload, secrets |
| Micrometer/Tracing bridge | Tạo và liên kết dữ liệu quan sát | Context propagation, attributes |
| OTLP exporter | Gửi spans đến receiver | Egress, endpoint, TLS, credentials |
| Collector | Nhận, lọc, sampling và chuyển tiếp | Receiver auth, memory, queue, pipeline |
| Trace backend | Lưu và truy vấn traces | Ingest/query ports, RBAC, retention |
| Actuator | Expose health/metrics theo cấu hình | HTTP exposure, security chain |
| Prometheus | Scrape và lưu metrics | Scrape identity, target network, retention |
| Grafana | Truy vấn và hiển thị data sources | User auth, data source credentials, RBAC |
| Evaluation result store | Lưu gold reference, score, trace reference | Quyền xem nhãn vàng và dữ liệu kiểm thử |

**Không dùng chung một URL cho mọi thành phần chỉ vì chúng đều nói đến telemetry.** Prometheus scrape endpoint của ứng dụng khác Prometheus query API. OTLP ingest của Tempo khác Tempo query API. Grafana UI không phải receiver cho spans.

## 3. Sampling: điều gì được lấy mẫu?

**Trace sampling** quyết định một trace có được ghi/xuất hay không. Sampling giúp điều tiết lượng spans, tài nguyên exporter, network và chi phí backend.

| Chiến lược | Quyết định khi nào? | Ưu điểm | Giới hạn |
|---|---|---|---|
| **Always-on** | Ghi mọi trace | Không bỏ sót trace do sampler | Tốn dung lượng, CPU và chi phí; vẫn có thể drop khi exporter/backend quá tải |
| **Always-off** | Không ghi trace | Giảm gần hết chi phí trace | Không điều tra được request cụ thể bằng trace |
| **Probability/ratio** | Chọn trace theo xác suất | Dễ cấu hình, ổn định tương đối theo lưu lượng | Có thể bỏ lỡ lỗi hiếm |
| **Parent-based** | Con tuân theo quyết định của parent | Giữ trace xuyên service nhất quán | Phụ thuộc propagation và quyết định của upstream |
| **Tail-based** | Chọn sau khi đã thu đủ spans của trace | Có thể ưu tiên trace lỗi/chậm | Cần Collector giữ trạng thái, route trace đúng và tài nguyên lớn hơn |

Spring Boot tracing thường có cấu hình xác suất qua `management.tracing.sampling.probability`. Giá trị nằm trong khoảng 0.0–1.0. Tài liệu Spring Boot hiện hành mô tả mặc định 10% cho tracing để tránh làm quá tải backend; luôn kiểm tra mặc định theo version thực tế.

### Không nhầm sampling với metrics scrape

| Cơ chế | Áp dụng cho | Ý nghĩa |
|---|---|---|
| Trace sampling | Traces/spans | Chọn request nào được lưu dấu vết |
| Prometheus scrape interval | Metrics | Tần suất Prometheus đọc endpoint |
| Histogram buckets | Metrics | Cách tổng hợp phân phối thời gian |
| Log sampling/filter | Logs | Chọn hoặc lọc sự kiện log |
| Evaluation case selection | Dataset | Chọn tình huống kiểm thử; không phải telemetry sampling |

Giảm trace sampling không làm counter/metrics tự giảm theo cùng tỷ lệ. Prometheus vẫn scrape các meter được instrument, kể cả khi trace tương ứng không được lưu.

### Khi nào cần sampling cao?

- Local: có thể dùng 100% với dữ liệu giả, tải thấp để xem toàn bộ spans.
- Staging: tăng tỷ lệ cho ca regression quan trọng và xác minh propagation.
- Production: chọn tỷ lệ theo traffic, rủi ro, ngân sách, retention và nhu cầu điều tra; có thể dùng tail sampling để ưu tiên lỗi/chậm.

Không sao chép `1.0` từ local sang production mà chưa tính số spans/giây và chi phí lưu trữ.

## 4. Head-based và parent-based sampling

**Head-based sampling** quyết định sớm khi trace bắt đầu. Nếu trace bị loại, các spans tiếp theo thường không được ghi/export theo quyết định đó. Cách này giảm overhead từ đầu nhưng không biết request cuối cùng có lỗi hoặc chậm hay không.

**Parent-based sampling** giúp các service con giữ quyết định sampling của trace cha. Ví dụ service A tạo trace được sample rồi gọi service B; service B nhận context và tiếp tục trace. Nếu B tự quyết định ngẫu nhiên độc lập, một trace phân tán có thể bị đứt.

### Cấu hình xác suất cho Spring Boot 3.5

Ví dụ `application-local.yml`:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
      transport: http
      timeout: 10s
~~~

Giá trị 1.0 chỉ phù hợp local hoặc bài test có kiểm soát. Cấu hình exporter trong ví dụ dùng nhóm property của Spring Boot 3.5; không dùng nguyên văn cho Boot 4.x.

Ví dụ production:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

0.10 chỉ là điểm bắt đầu minh họa. Tỷ lệ cuối phải dựa trên số request, spans mỗi request, mức độ quan trọng của lỗi và khả năng backend. Nếu thay đổi sampling giữa các service, hãy bảo đảm parent context và propagation được xử lý thống nhất.

### Sampler cụ thể trong Spring Boot 4.x

Spring Boot 4.x có cấu hình sampler OpenTelemetry qua `management.opentelemetry.tracing.sampler` bên cạnh xác suất `management.tracing.sampling.probability`. Các lựa chọn được hỗ trợ trong tài liệu dòng 4.0 gồm:

| Sampler | Hành vi |
|---|---|
| `always-on` | Sample mọi trace |
| `always-off` | Không sample trace |
| `trace-id-ratio` | Chọn theo tỷ lệ trace ID |
| `parent-based-always-on` | Theo parent; nếu không có parent thì sample |
| `parent-based-always-off` | Theo parent; nếu không có parent thì loại |
| `parent-based-trace-id-ratio` | Theo parent; root trace chọn theo tỷ lệ |

Ví dụ dành riêng cho **Spring Boot 4.0**:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
~~~

Property và sampler phải được xác nhận trong metadata của đúng phiên bản Boot đang chạy. Không trộn sampler/property Boot 4.x với dependency/exporter Boot 3.5.

## 5. Tail-based sampling: chọn sau khi thấy kết quả của trace

Head sampling không biết request sẽ thành công hay timeout khi vừa bắt đầu. **Tail sampling** đưa quyết định về phía Collector sau khi nhận spans của trace, do đó có thể chọn theo:

- Trace có span trạng thái lỗi.
- Trace vượt ngưỡng độ trễ.
- Trace thuộc service/operation quan trọng.
- Một tỷ lệ nền của trace bình thường để quan sát xu hướng.

### Điều kiện bắt buộc

1. Ứng dụng upstream phải gửi đủ spans cần thiết đến Collector; nếu head sampler đã loại trace thì Collector không thể phục hồi spans chưa được gửi.
2. Các spans của cùng trace phải tới **cùng một tail-sampling processor instance** trong khoảng thời gian giữ trace.
3. Collector phải có đủ memory/CPU và thời gian chờ để nhận các spans đến muộn.
4. Cấu hình chính sách phải xét trace hoàn tất, không chỉ một span đơn lẻ.
5. Cần theo dõi số trace bị drop, buffer pressure và quyết định sampling.

### Ví dụ processor tail sampling

Đoạn sau là **mẫu cấu hình minh họa** cho một Collector distribution có `tail_sampling` processor:

~~~yaml
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
  tail_sampling:
    decision_wait: 10s
    num_traces: 20000
    expected_new_traces_per_sec: 500
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: keep-slow
        type: latency
        latency:
          threshold_ms: 2000
      - name: baseline
        type: probabilistic
        probabilistic:
          sampling_percentage: 5
  batch: {}
~~~

Các ngưỡng 10s, 2000ms, 5% và giới hạn buffer chỉ là ví dụ, cần sizing theo lưu lượng và version processor. Trong pipeline traces, thứ tự thường là nhận OTLP → memory limiter → tail sampling → batch → exporter. Nếu tail sampler chạy sau batch hoặc thiếu routing nhất quán, kết quả có thể không như mong đợi.

### Tại sao không vừa head sample 10% vừa tail sample lỗi?

Nếu head sampler chỉ gửi 10% traces, 90% traces không tới Collector. Tail sampler chỉ có thể lựa chọn trong số 10% đã nhận; không thể giữ các lỗi nằm trong phần đã bị loại upstream.

Nếu mục tiêu là **giữ mọi trace lỗi**, cần gửi đủ trace tới tầng tail sampling (ví dụ upstream sampling 100% trong phạm vi đã tính tải) hoặc dùng kiến trúc sampling có khả năng tương ứng. Điều này có thể tốn nhiều tài nguyên; phải tính trước và thử tải.

### Tail sampling và nhiều Collector

Một trace có thể bị tách nếu spans của nó được load balancer gửi tới các Collector khác nhau. Khi dùng tail sampling phân tán, cần cơ chế routing theo trace ID (hoặc kiến trúc hỗ trợ phù hợp) để giữ các spans cùng trace trên cùng processor. Không chỉ scale số replicas rồi giả định tail sampling vẫn chính xác.
## 6. Chọn endpoint: xác định đúng nơi gửi, nơi scrape và nơi query

| Thành phần | Địa chỉ ví dụ | Dùng cho |
|---|---|---|
| Spring Boot Actuator | `http://app:8080/actuator/prometheus` | Prometheus scrape metrics |
| Prometheus server | `http://prometheus:9090` | Prometheus query API cho Grafana |
| OTLP/HTTP receiver | `http://collector:4318/v1/traces` | App gửi traces |
| OTLP/gRPC receiver | `collector:4317` | App gửi traces qua gRPC |
| OTLP metrics receiver HTTP | `http://collector:4318/v1/metrics` | App gửi metrics qua OTLP |
| Tempo OTLP ingest | Thường là `tempo:4318` trong topology đã bật receiver | Collector gửi spans tới Tempo |
| Tempo query API | Thường là `http://tempo:3200` | Grafana truy vấn traces |
| Grafana UI | `http://grafana:3000` | Người vận hành xem dashboard |
| Zipkin ingest | Ví dụ `http://zipkin:9411/api/v2/spans` | Reporter gửi spans theo Zipkin API |

Các port là quy ước thường gặp, có thể thay đổi. Endpoint thật phải lấy từ cấu hình deployment và receiver đang bật.

### OTLP/HTTP khác OTLP/gRPC

| Giao thức | Port quy ước | Cách đặt endpoint |
|---|---:|---|
| OTLP/HTTP | 4318 | Có signal path như `/v1/traces` hoặc `/v1/metrics` |
| OTLP/gRPC | 4317 | Dùng gRPC exporter/channel; không nối HTTP path như REST |

Một **base endpoint** như `http://collector:4318` có thể được framework tự thêm path tín hiệu. Một **signal-specific endpoint** như `http://collector:4318/v1/traces` thường được dùng nguyên vẹn. Kiểm tra semantics của property để tránh `/v1/traces/v1/traces` hoặc thiếu path.

### Ingest endpoint khác query endpoint

- App gửi spans đến OTLP receiver.
- Collector gửi spans đến trace backend ingest receiver.
- Grafana hỏi trace backend qua query API.

Không gửi spans đến Grafana UI, và không dùng cổng ingest của Tempo làm Grafana datasource nếu cổng đó không phục vụ query API.

## 7. Cấu hình endpoint và auth cho Spring Boot 3.5

Ví dụ sau nhắm tới **Spring Boot 3.5** dùng Micrometer Tracing bridge OpenTelemetry:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Ví dụ `application-prod.yml`:

~~~yaml
spring:
  application:
    name: spring-ai-quality-service

management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: https://otel-gateway.internal:4318/v1/traces
      transport: http
      timeout: 10s
      headers:
        Authorization: "Bearer REPLACE_WITH_SECRET_FROM_SECRET_STORE"
~~~

Các property `management.otlp.tracing.endpoint`, `transport`, `timeout` và `headers.*` thuộc nhóm cấu hình Spring Boot 3.5. Header ở đây minh họa bearer token; chuỗi `REPLACE_WITH_SECRET_FROM_SECRET_STORE` là placeholder, phải được thay bằng secret injection tại runtime và không được dùng như credential thật.

**Không commit token thật** vào Git, không ghi token vào log và không hiển thị toàn bộ environment qua Actuator. Nếu secret chưa được cấp, triển khai phải fail theo chính sách secret của ứng dụng; đừng thay bằng token giả có vẻ hợp lệ.

### Cấu hình Zipkin với Brave trên Boot 3.5

Nếu hệ thống đang dùng Brave + Zipkin thay cho OTel/OTLP:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-brave'
    runtimeOnly 'io.zipkin.reporter2:zipkin-reporter-brave'
}
~~~

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
  zipkin:
    tracing:
      endpoint: http://zipkin:9411/api/v2/spans
~~~

Đây là một nhánh lựa chọn khác, không thêm cả OTel bridge và Brave bridge vào cùng cấu hình một cách tùy tiện. Khi endpoint Zipkin cần auth, dùng khả năng reporter/proxy/network security được phiên bản hỗ trợ; không giả định mọi property OTLP headers áp dụng cho Zipkin.

## 8. Cấu hình endpoint và auth cho Spring Boot 4.0

Spring Boot 4.0 có starter OpenTelemetry riêng. Với cấu hình dòng 4.0, ví dụ dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

Ví dụ `application-prod.yml`:

~~~yaml
spring:
  application:
    name: spring-ai-quality-service

management:
  tracing:
    sampling:
      probability: 0.10
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: https://otel-gateway.internal:4318/v1/traces
          headers:
            Authorization: "Bearer REPLACE_WITH_SECRET_FROM_SECRET_STORE"
          timeout: 10s
~~~

Tên property signal-specific của traces ở dòng này là `management.opentelemetry.tracing.export.otlp.*`, khác Boot 3.5. Spring Boot 4.0 còn có cấu hình chung `management.opentelemetry.otlp.*` cho endpoint/headers/compression nhiều tín hiệu; signal-specific properties có thể ưu tiên khi được đặt. Đọc metadata đúng version trước khi chọn cấu hình chung hoặc riêng.

### OTLP common endpoint và headers trong Boot 4.0

Ví dụ cấu hình dùng chung:

~~~yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://otel-gateway.internal:4318
      compression: gzip
      headers:
        Authorization: "Bearer REPLACE_WITH_SECRET_FROM_SECRET_STORE"
~~~

Với OTLP/HTTP, khi dùng **common base endpoint** theo semantics của Spring Boot 4.0, framework có thể nối signal path như `v1/traces`, `v1/metrics` hoặc `v1/logs`. Nếu dùng signal-specific endpoint, thường phải ghi đường dẫn đầy đủ. Không đặt hai endpoint mâu thuẫn rồi đoán cái nào thắng.

Không hiểu rằng starter OpenTelemetry tự động xuất tất cả metrics/logs. Tracing, metrics registry và log exporter vẫn có các pipeline/điều kiện tương ứng. Kiểm tra từng loại tín hiệu.

## 9. Bảo vệ endpoint Prometheus scrape

Prometheus pull metrics từ Actuator endpoint của ứng dụng. Ví dụ cấu hình scrape với **Basic Authentication** và TLS:

~~~yaml
scrape_configs:
  - job_name: spring-ai
    scrape_interval: 15s
    metrics_path: /actuator/prometheus
    scheme: https
    basic_auth:
      username: prometheus-scraper
      password_file: /etc/prometheus/secrets/scrape-password
    tls_config:
      ca_file: /etc/prometheus/certs/ca.crt
      server_name: spring-ai.internal
      insecure_skip_verify: false
    static_configs:
      - targets: ["spring-ai.internal:8443"]
~~~

Đây là ví dụ cấu hình phía **Prometheus scraper**. Phía ứng dụng vẫn phải có SecurityFilterChain hoặc proxy/gateway chấp nhận đúng danh tính, đồng thời Actuator chỉ expose `health,metrics,prometheus` cần thiết. Đường dẫn file secret là ví dụ, phải được mount bằng cơ chế an toàn.

Nếu dùng bearer token, Prometheus cũng có cấu hình authorization/credentials file phù hợp phiên bản; chọn một cơ chế được hạ tầng hỗ trợ và không đưa secret trực tiếp vào repository. Basic auth chỉ an toàn trên TLS hoặc một mạng tin cậy đã được bảo vệ.

### Không nhầm xác thực scrape với xác thực Grafana

Có hai kết nối khác nhau:

1. Prometheus → Actuator: danh tính scraper được ứng dụng chấp nhận.
2. Grafana → Prometheus: Grafana dùng quyền query API của Prometheus.

Một credential cho scraper không tự động là credential của Grafana. Quản lý hai identity và quyền tối thiểu riêng.

## 10. Bảo vệ Actuator bằng Spring Security

Nếu ứng dụng dùng Spring Security, cần quy định rõ endpoint nào được phép công khai và endpoint nào cần role vận hành.

Ví dụ minh họa cho ứng dụng **Servlet, cùng management/application port**, dùng Spring Security 6:

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ActuatorSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().hasRole("OPS"))
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Đây không phải cấu hình production hoàn chỉnh.** Ứng dụng phải có identity provider/user store cấp role `OPS`; Basic auth phải được bảo vệ bằng TLS; ứng dụng WebFlux cần cấu hình reactive khác. Nếu management server chạy port riêng, security context và matcher cần được kiểm tra theo topology đó.

Khi tự khai báo `SecurityFilterChain`, không mặc định rằng bảo mật Actuator auto-configuration vẫn áp dụng như trước. Kiểm tra bằng request thực:

| Client | Endpoint | Kết quả mong đợi |
|---|---|---|
| Không credential | `/actuator/metrics` | 401 hoặc bị proxy từ chối |
| Credential không có role OPS | `/actuator/metrics` | 403 |
| Scraper có role phù hợp | `/actuator/prometheus` | 200 với exposition |
| Probe được phép | `/actuator/health` | Response tối thiểu |
| Người dùng cuối | `/actuator/env`, `heapdump` | Không truy cập được |

Không xử lý lỗi 401/403 bằng cách expose toàn bộ endpoint hoặc tắt security.

## 11. Bảo vệ Collector receiver và OTLP exporter

Collector thường nằm ở ranh giới giữa nhiều ứng dụng và trace backend. Cần bảo vệ cả:

- **Receiver:** ai được gửi dữ liệu vào Collector?
- **Exporter:** Collector được phép gửi tới backend nào?
- **Admin/telemetry endpoint:** ai được xem health, metrics nội bộ và cấu hình?

### Ví dụ bearer token receiver trong Collector

Mẫu sau minh họa extension xác thực bearer token trong một distribution Collector có component tương ứng:

~~~yaml
extensions:
  bearertokenauth/server:
    scheme: "Bearer"
    token: "REPLACE_WITH_SECRET_INJECTED_AT_RUNTIME"

receivers:
  otlp:
    protocols:
      http:
        endpoint: 127.0.0.1:4318
        auth:
          authenticator: bearertokenauth/server

processors:
  batch: {}

exporters:
  otlp_http/backend:
    endpoint: https://trace-backend.internal

service:
  extensions: [bearertokenauth/server]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp_http/backend]
~~~

Tên component, trường cấu hình và cách hỗ trợ auth phụ thuộc Collector distribution/version. `bearertokenauth` có thể yêu cầu distribution contrib hoặc component tương ứng; phải xác nhận component có trong binary thực tế. Token phải được inject qua secret mechanism, không hardcode. `127.0.0.1` phù hợp khi client cùng network namespace; nếu app ở container khác, cấu hình bind/network đúng và giới hạn nguồn truy cập.

### Client gửi bearer token

Với Spring Boot 3.5, tracing OTLP có thể nhận custom HTTP headers qua nhóm `management.otlp.tracing.headers.*`; Boot 4.0 dùng nhóm signal-specific `management.opentelemetry.tracing.export.otlp.headers.*` hoặc common OTLP headers. Dùng biến secret:

~~~yaml
# Minh họa Spring Boot 3.5
management:
  otlp:
    tracing:
      headers:
        Authorization: "Bearer REPLACE_WITH_SECRET_FROM_SECRET_STORE"
~~~

Không đưa token vào span attributes, baggage, log hoặc dashboard. Khi dùng mTLS, cấu hình certificate/key/trust theo exporter/proxy được hỗ trợ; không giả định chỉ đặt HTTPS URL là đã thiết lập client certificate.

### TLS và mTLS

| Cơ chế | Ý nghĩa | Khi phù hợp |
|---|---|---|
| TLS server-side | Mã hóa kết nối và xác minh server | Kết nối app → collector qua mạng |
| mTLS | Cả client và server đều xác minh certificate | Giao tiếp service-to-service có danh tính máy |
| Bearer token | Credential trong HTTP authorization header | API receiver có token auth |
| Basic auth | Username/password qua HTTP auth | Scrape hoặc backend hỗ trợ, luôn bảo vệ transport |
| Network policy | Giới hạn nguồn/đích kết nối | Cô lập receiver, Actuator và query API |

TLS/mTLS không thay authorization ở tầng ứng dụng. Một client có certificate hợp lệ vẫn cần đúng quyền đối với endpoint hoặc tenant.

## 12. Quản lý endpoint và secret qua môi trường

Tách cấu hình **không nhạy cảm** và **bí mật**:

| Giá trị | Có thể lưu trong config/version control? | Nơi phù hợp |
|---|---|---|
| Service name | Có, nếu đã duyệt | Application config |
| Sampling probability | Có, theo profile và review | Profile/ConfigMap |
| OTLP endpoint nội bộ | Có thể, nếu không chứa credential | ConfigMap/secret-free deployment config |
| Bearer token/API key | Không | Secret manager/Kubernetes Secret/Vault |
| Client private key | Không | Secret store/volume mount được bảo vệ |
| CA certificate công khai | Tùy chính sách | Trust bundle/secret/config mount |
| Prometheus scrape password | Không | Secret file hoặc credential provider |
| Grafana data source password/token | Không | Secure provisioning/environment secret |

### Ví dụ biến môi trường

~~~text
TRACE_SAMPLING_PROBABILITY=0.10
OTLP_TRACES_ENDPOINT=https://otel-gateway.internal:4318/v1/traces
OTLP_TRACES_TOKEN=<inject-from-secret-store>
~~~

Đây là tên biến ví dụ để minh họa cách tách cấu hình; ứng dụng chỉ nhận biến nào nếu property placeholder hoặc environment mapping tương ứng đã được cấu hình. Không đặt giá trị token thật trong tài liệu, Git, ticket hoặc command history.

### Local và production phải khác nhau

~~~yaml
# application-local.yml: dùng dữ liệu giả và receiver local
management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

~~~yaml
# application-prod.yml: endpoint nội bộ và secret injection
management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: https://otel-gateway.internal:4318/v1/traces
      headers:
        Authorization: "Bearer REPLACE_WITH_SECRET_FROM_SECRET_STORE"
      timeout: 10s
~~~

Hai ví dụ trên nhắm tới **Boot 3.5**. Production không nên có fallback về endpoint localhost nếu biến endpoint bị thiếu; cần kiểm tra fail-fast hoặc validation config. Với Boot 4.x, thay bằng nhóm property tương ứng.
## 13. Bảo vệ Grafana và data source credentials

Grafana có ít nhất hai nhóm quyền:

1. **Người xem dashboard:** đọc panel đã được cấp, không mặc định có quyền quản trị data source.
2. **Quản trị/nhóm observability:** quản lý data sources, credentials, provisioning và dashboard.

### Data source URL và credentials

| Data source | URL mẫu | Credential |
|---|---|---|
| Prometheus | `http://prometheus:9090` | Service identity/query token nếu backend yêu cầu |
| Tempo | `http://tempo:3200` | Query credential theo backend/proxy |

Đây là URL query, không phải endpoint ingest. Credentials được cấu hình bằng secure settings/provisioning secret hoặc secret manager. Tránh lưu password/token dạng plain text trong dashboard JSON, datasource YAML công khai hoặc Git.

### Nguyên tắc bảo vệ

- Bật xác thực người dùng Grafana và phân quyền theo team/role.
- Chỉ cấp quyền xem traces có dữ liệu nhạy cảm cho người cần điều tra.
- Không dùng chung tài khoản admin cho datasource và người xem.
- Bảo vệ provisioning secrets, API keys và session secrets.
- Giới hạn network access đến Grafana, Prometheus và Tempo query endpoints.
- Có audit/retention phù hợp cho thao tác thay đổi datasource và quyền.

Một dashboard được chia sẻ cho nhiều người có thể làm lộ labels/attributes dù Actuator đã được bảo vệ. Hãy kiểm tra cả **quyền truy vấn backend** và **quyền xem Grafana**.

## 14. Endpoint và authentication: ma trận kiểm thử

Không chỉ kiểm tra bằng một request 200. Cần thử cả client hợp lệ và không hợp lệ:

| Client | Đích | Kết quả mong đợi | Nếu khác |
|---|---|---|---|
| Prometheus có identity | Actuator Prometheus | 200 + metric exposition | Kiểm tra TLS/auth/path/exposure |
| Prometheus không credential | Actuator Prometheus | 401/403 hoặc network deny | Nếu 200, endpoint có thể đang mở quá rộng |
| Spring AI app có OTLP token | Collector receiver | Accepted/response thành công theo protocol | Kiểm tra token, path, protocol, clock/TLS |
| App token sai | Collector receiver | 401/403 | Nếu nhận, xác thực chưa được áp dụng |
| Grafana service identity | Prometheus query API | Truy vấn được dữ liệu theo quyền | Kiểm tra datasource credential/URL |
| Grafana service identity | Tempo query API | Tìm được trace trong retention | Kiểm tra query endpoint/RBAC |
| User không có quyền | Tempo query API | Bị từ chối theo policy | Kiểm tra proxy và tenant isolation |
| Người dùng cuối | Actuator env/heapdump | Bị từ chối | Thu hẹp exposure và kiểm tra security |

Một số proxy có thể trả 404 thay cho 401/403 để ẩn sự tồn tại của endpoint. Đánh giá theo **chính sách bảo mật đã định**, không chỉ dựa mã HTTP.

### Lỗi TLS phổ biến

- Certificate hết hạn hoặc hostname không khớp SAN.
- App thiếu CA trust bundle.
- Collector yêu cầu client certificate nhưng app không gửi.
- Proxy terminate TLS nhưng upstream app/collector lại yêu cầu TLS khác.
- Container có clock lệch khiến certificate chưa hợp lệ hoặc đã hết hạn.

Không dùng `insecure_skip_verify=true` làm giải pháp lâu dài. Cấu hình trust chain và hostname đúng.

## 15. Endpoint sai, timeout và backpressure

Telemetry không nên làm request AI chính bị treo vô hạn. Exporter cần timeout, batch và queue có giới hạn phù hợp.

| Triệu chứng | Khả năng | Cách xử lý |
|---|---|---|
| HTTP 404 | Sai path/base URL hoặc receiver không có route | Phân biệt common endpoint và signal-specific endpoint |
| HTTP 401/403 | Token/role không hợp lệ | Cấp lại identity qua secret store |
| HTTP 429 | Receiver rate limit | Điều chỉnh throughput, batch, queue hoặc quota |
| HTTP 500/503 | Collector/backend lỗi hoặc quá tải | Kiểm tra pipeline, capacity, retries |
| TLS handshake failure | Trust/certificate/protocol sai | Kiểm tra CA, SAN, expiry, mTLS |
| Connection refused | Host/port/network sai hoặc receiver chưa chạy | Kiểm tra service DNS và listener |
| Export timeout | Network/backend chậm | Cấu hình timeout/queue có giới hạn, giám sát drop |
| Queue đầy | Exporter/collector không theo kịp | Scale/limit, batch, sampling phù hợp |

### Nguyên tắc bảo vệ ứng dụng

- Đặt timeout hữu hạn cho exporter.
- Giới hạn queue và batch size để tránh tăng bộ nhớ vô hạn.
- Theo dõi export failures/dropped spans.
- Không retry vô hạn đồng bộ trên request người dùng.
- Đặt circuit/backpressure phù hợp để telemetry outage không kéo sập ứng dụng.
- Có alert khi pipeline quan sát mất dữ liệu, để dashboard trống không bị hiểu nhầm là không có lỗi.

Các thuộc tính cụ thể như queue size, batch size, schedule delay và exporter timeout phụ thuộc Spring Boot/OTel version. Dùng metadata property chính thức, không chép cấu hình của phiên bản khác.

## 16. Bảo vệ dữ liệu trong trace của Spring AI

Một trace AI có thể chứa nội dung nhạy cảm ở nhiều nơi:

| Vị trí | Ví dụ | Quy tắc |
|---|---|---|
| HTTP request | User message, headers | Không ghi Authorization/Cookie; cân nhắc không ghi raw body |
| Model observation | Prompt, completion, model metadata | Chỉ bật content capture khi có mục đích và quyền rõ |
| RAG retriever | Tài liệu nội bộ, đoạn chunk | Ưu tiên source ID/version, hạn chế full text |
| Tool call | Arguments, response, customer/order data | Ghi tool name, outcome, duration và mã lỗi đã chuẩn hóa |
| Baggage | Metadata truyền xuyên service | Không truyền secrets, PII hoặc mã giao dịch không cần thiết |
| Exception | Stack trace/message chứa URL hoặc token | Lọc/redact trước export |
| Collector debug | Nội dung span in ra stdout | Chỉ local với dữ liệu tổng hợp |

Không mặc định mọi phiên bản Spring AI đều có cùng cấu hình bật/tắt prompt/completion observation. Kiểm tra property đúng version và **xác nhận payload thật** ở Collector/backend. Không đưa gold answer hoặc reference evaluator vào runtime trace nếu không cần thiết.

### Sampling không thay thế redaction

Nếu trace được sample, nội dung nhạy cảm vẫn có thể xuất hiện trong những trace được giữ. Giảm sampling từ 100% xuống 10% chỉ giảm volume, không bảo đảm dữ liệu còn lại an toàn.

### Trace ID không phải credential

Trace ID và `traceparent` là metadata tương quan, không chứng minh người gọi có quyền truy cập đơn hàng. Không sử dụng trace ID thay access token, cũng không gắn token xác thực vào baggage.

## 17. Kết hợp sampling với đánh giá RAG và tool calling

Giả sử bộ đánh giá có 100 ca:

- 40 ca RAG thông thường.
- 20 ca không có bằng chứng.
- 20 ca boundary về điều kiện chính sách.
- 20 ca tool calling, trong đó có một số hard gates về quyền và side effect.

Trong staging, có thể lấy mẫu cao để điều tra mọi ca regression. Production có thể dùng xác suất thấp hơn và tail sampling ưu tiên error/slow traces. Tuy nhiên:

| Dữ liệu | Cách giữ | Có được phụ thuộc trace sampling không? |
|---|---|---|
| Evaluation PASS/FAIL | Result store cho mọi case/attempt | **Không** |
| Tool events và trạng thái fixture trong benchmark | Runner lưu theo case | **Không** |
| Gold reference/rubric | Kho evaluator có phân quyền | **Không** |
| Metrics tổng hợp | Registry/backend metrics | Không phụ thuộc trace sampling |
| Trace chi tiết | Theo sampling/retention policy | Có |
| Raw prompt/completion | Chỉ khi thật sự cần và được phép | Không nên mặc định thu |

### Ví dụ liên kết một ca FAIL

~~~yaml
evaluationResult:
  runId: eval-prompt-b-2026-11-27
  caseId: return-missing-delivery-time-014
  attemptId: 2
  datasetVersion: "1.4.0"
  rubricVersion: "rubric-v3"
  result:
    factualCorrectness: 0.0
    noUnsupportedClaim: false
    hardGatePassed: true
  observability:
    traceId: "opaque-trace-id-if-sampled"
    latencyMs: 2480
    inputTokens: null
    outputTokens: null
    estimatedCost: null
~~~

Schema và giá trị chỉ là minh họa. `null` nghĩa là chưa có nguồn usage/price đủ tin cậy. Nếu trace không được lưu, result vẫn giữ FAIL và các tool/retrieval events tối thiểu theo chính sách.

### Không gắn từng caseId vào metric labels

Để theo dõi số ca FAIL, dùng metric tổng hợp như `task_type=rag`, `severity=P1`, `outcome=fail`. Không dùng `caseId` duy nhất của từng ca làm nhãn Prometheus. Liên kết chi tiết qua result store và trace ID được phân quyền.
## 18. Cấu hình tham khảo cho ba môi trường

| Môi trường | Sampling | Endpoint | Authentication |
|---|---|---|---|
| Local | 1.0 với dữ liệu giả | Collector local OTLP/HTTP | Có thể không cần token nếu loopback/private local |
| Staging | Cao hơn production theo mục tiêu QA | Collector staging và Prometheus staging | Token test, TLS theo topology |
| Production | Theo budget/risk; có thể tail sample | Collector/receiver nội bộ, Prometheus scrape riêng | TLS/mTLS, bearer/basic auth, secret store, RBAC |

### Cấu hình cần version hóa

- Spring Boot/Spring AI/Micrometer/OTel version.
- Sampling probability và sampler type.
- OTLP protocol, base endpoint hoặc signal-specific endpoint.
- Timeout, queue, batch và export interval.
- Receiver auth mode, CA trust và identity name (không phải secret value).
- Prometheus scrape path, TLS/auth, interval.
- Collector receiver/processor/exporter và routing.
- Trace backend ingest/query endpoint.
- Retention, privacy filters và RBAC.

Khi đổi endpoint hoặc token, cần rollout theo cách có thể rollback. Nếu token bị thu hồi trước khi ứng dụng dùng credential mới, exporter có thể ngừng gửi; hãy lập kế hoạch overlap/rotation theo cơ chế identity của tổ chức.

## 19. Quy trình xác minh đầu-cuối

Dùng request giả lập và đi lần lượt qua từng tầng:

1. **Preflight version:** xác nhận Spring Boot version và property namespace đúng.
2. **Sampler:** tạo một request test và xác nhận tỷ lệ sample như dự định.
3. **Endpoint:** kiểm tra hostname, port, protocol, path, DNS và network namespace.
4. **Authentication:** thử credential hợp lệ và không hợp lệ; xác nhận receiver từ chối token sai.
5. **TLS:** kiểm tra certificate chain, SAN, expiry và client certificate nếu mTLS.
6. **Exporter:** xem lỗi export, timeout, queue/drop metrics.
7. **Collector:** xác nhận receiver nhận traces và pipeline tương ứng được bật.
8. **Tail sampler:** nếu dùng, xác nhận các spans của một trace đến cùng processor instance.
9. **Backend:** xác nhận trace đã được lưu và query được.
10. **Grafana:** xác nhận datasource dùng query endpoint, không dùng ingest endpoint.
11. **Evaluation:** chạy ca RAG/tool, chấm bằng reference và lưu trace ID nếu có.
12. **Privacy:** kiểm tra raw prompt, PII, secrets, headers và tool payload đã được lọc.
13. **Failure test:** thử endpoint sai, token sai, receiver tạm dừng và xác nhận app không bị treo vô hạn.

### Ma trận kết quả thử nghiệm

| Tình huống | Kết quả cần quan sát |
|---|---|
| Endpoint đúng, token đúng | Export được và trace query thấy ở backend |
| Endpoint đúng, token sai | Receiver từ chối; có dấu hiệu export failure |
| Endpoint sai path | HTTP lỗi; xác định đúng signal endpoint |
| Port HTTP gửi gRPC | Kết nối/protocol thất bại, không sửa bằng đổi path |
| TLS certificate không hợp lệ | Handshake thất bại |
| Collector mất kết nối | Export retry/queue có giới hạn; app vẫn phục vụ theo thiết kế |
| Trace bị head-sampled out | Không có trace backend; metrics/evaluation result vẫn có |
| Trace được tail sampler giữ do lỗi | Backend có trace đầy đủ nếu pipeline/routing đúng |
| User không có quyền đọc Tempo | Query bị chặn |
| Ca tool vi phạm hard gate nhưng trace bị sample out | Evaluation vẫn FAIL từ tool events/fixture state |

## 20. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có trace ở backend | Sampling loại, exporter chưa bật, sai endpoint | Kiểm tra sampler → exporter → receiver → backend |
| Có trace HTTP nhưng không có model/tool span | Instrumentation thiếu hoặc context đứt | Kiểm tra Spring AI version và client builders |
| Trace bị đứt qua service | Propagation header không được inject/extract | Kiểm tra W3C/B3 và proxy |
| OTLP trả 401 | Bearer token sai/thiếu | Kiểm tra secret injection và header name |
| OTLP trả 403 | Auth hợp lệ nhưng thiếu quyền | Kiểm tra authorization/tenant |
| OTLP trả 404 | Sai path, base URL hoặc receiver không bật | Kiểm tra `/v1/traces` và signal-specific config |
| OTLP trả 415/400 | Payload/protocol/content type không đúng | Kiểm tra HTTP vs gRPC, exporter và receiver version |
| OTLP trả 429 | Receiver giới hạn tốc độ | Điều chỉnh batch, capacity, quota |
| TLS handshake error | CA/SAN/expiry/mTLS sai | Kiểm tra certificate và trust store |
| Collector nhận trace nhưng backend không có | Exporter/pipeline/backend auth sai | Kiểm tra pipeline traces và backend ingest |
| Grafana không tìm thấy trace | Sai query URL, retention hoặc time range | Dùng query API, xác minh backend |
| Tail sampling không giữ trace lỗi | Trace không tới collector, status không được đánh dấu ERROR, policy sai | Kiểm tra upstream sampling, routing, span status |
| Tail sampling giữ thiếu spans | Các spans cùng trace tới nhiều collector | Route theo trace ID |
| Queue đầy, spans bị drop | Backend chậm hoặc capacity thấp | Sizing, queue/batch, sampling và alert |
| App bị chậm khi exporter lỗi | Export đồng bộ/timeout quá lớn | Timeout hữu hạn và export async phù hợp |
| Metric p95 không khớp trace durations | Khác scope hoặc sampled trace bias | Dùng histogram cho phân phối và trace để giải thích |
| Secret xuất hiện trong trace | Raw capture/headers/baggage | Ngăn phát sinh, redaction, xử lý bản đã lưu |

## 21. Bài thực hành: sampling và credential cho trợ lý RAG

Giả sử một dịch vụ Spring AI:

- Nhận câu hỏi về chính sách hoàn trả.
- Truy xuất tài liệu RAG từ index nội bộ.
- Gọi tool `get_order_status` chỉ đọc.
- Gửi traces tới Collector staging, sau đó tới Tempo.
- Prometheus scrape metrics từ Actuator.
- Grafana query Prometheus và Tempo.

**Yêu cầu:**

1. Chọn sampling 100% cho local dữ liệu giả và tỷ lệ thấp hơn cho production; giải thích trade-off.
2. Viết cấu hình OTLP/HTTP endpoint có signal path chính xác.
3. Cấu hình bearer token cho app → Collector, lấy secret từ secret store.
4. Bảo vệ Actuator bằng Spring Security hoặc network policy; chỉ scraper được đọc Prometheus endpoint.
5. Cấu hình Prometheus scrape dùng TLS và credential file.
6. Dùng Tempo ingest endpoint cho Collector, Tempo query endpoint cho Grafana.
7. Nếu cần giữ mọi trace lỗi, thiết kế tail sampling và route theo trace ID.
8. Tạo một ca có tool `NOT_FOUND` và một ca model hallucinate khi thiếu timestamp.
9. Đảm bảo evaluation result được lưu dù trace bị sample out.
10. Kiểm tra trace attributes không chứa raw user message, mã đơn thật, Authorization header hoặc API key.
11. Giả lập token sai, endpoint sai và Collector down; ghi kết quả HTTP/export.
12. Chạy prompt A/B trên cùng dataset/rubric; xem quality, p95 latency, token usage và chi phí có nguồn.

### Câu hỏi tự kiểm

**Câu 1:** Giảm sampling từ 100% xuống 10% có làm trace an toàn hơn không?

**Không.** Nó giảm số lượng, không làm nội dung trace được giữ trở nên ít nhạy cảm.

**Câu 2:** Collector tail sampler có thể giữ lỗi trong trace mà app head sampler đã loại không?

**Không.** Collector không thể khôi phục spans chưa được gửi.

**Câu 3:** OTLP/HTTP dùng port quy ước nào và signal path traces là gì?

**4318**, thường là `/v1/traces`; OTLP/gRPC thường dùng 4317 và exporter gRPC riêng.

**Câu 4:** App gửi bearer token đúng nhưng vẫn 403. Nguyên nhân có thể là gì?

Identity đã được xác thực nhưng thiếu quyền/tenant; kiểm tra authorization policy.

**Câu 5:** Trace không xuất hiện nhưng evaluator ghi nhận tool gọi sai. Có đổi FAIL thành PASS không?

**Không.** Hard gate dựa trên tool events/state đã lưu; trace chỉ hỗ trợ điều tra.

## 22. Checklist trước khi triển khai production

- [ ] Đã tách quyết định sampling, endpoint và authentication.
- [ ] Trace sampling không bị nhầm với metrics scrape interval hoặc evaluation case selection.
- [ ] Tỷ lệ sampling phù hợp traffic, rủi ro, retention và ngân sách.
- [ ] Nếu dùng tail sampling, upstream gửi đủ spans và các spans cùng trace được route nhất quán.
- [ ] Không dùng p95 sampled traces thay cho phân phối metrics tổng thể khi mẫu bị thiên lệch.
- [ ] Endpoint phân biệt rõ OTLP/HTTP, OTLP/gRPC, Prometheus scrape, Tempo/Jaeger ingest và query.
- [ ] Boot 3.5 và Boot 4.x dùng dependency/property đúng version, không trộn namespace.
- [ ] Endpoint có TLS và xác thực khi đi qua mạng không tin cậy.
- [ ] Bearer/basic credentials, private keys và passwords không nằm trong Git hoặc logs.
- [ ] Collector receiver có authentication, network ACL và pipeline đúng tín hiệu.
- [ ] Prometheus scraper dùng identity/quyền tối thiểu; Actuator không expose quá rộng.
- [ ] Grafana data sources dùng query API và secrets được provision an toàn.
- [ ] SecurityFilterChain, mTLS, TLS trust và RBAC được thử bằng client hợp lệ/không hợp lệ.
- [ ] Exporter có timeout, batch/queue giới hạn và metrics theo dõi dropped/failed exports.
- [ ] Không có raw prompt, PII, API key, tool payload nhạy cảm hoặc secrets trong spans/tags/baggage.
- [ ] Metrics labels có cardinality thấp; trace/case IDs nằm trong kho truy vấn phù hợp.
- [ ] Evaluation results, hard gates và tool events tồn tại độc lập với sampling.
- [ ] Token usage và estimated cost chỉ dùng số liệu/bảng giá xác minh.
- [ ] Có smoke test endpoint, auth, trace storage/query và kế hoạch rollback/rotation credentials.

### Tài liệu chính thức để đối chiếu theo phiên bản

- Spring Boot 3.5 Tracing: https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html
- Spring Boot 3.5 Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 4.0 Tracing: https://docs.spring.io/spring-boot/4.0/reference/actuator/tracing.html
- Spring Boot 4.0 Observability và OTLP: https://docs.spring.io/spring-boot/4.0/reference/actuator/observability.html
- OpenTelemetry Collector configuration: https://opentelemetry.io/docs/collector/configuration/
- OpenTelemetry tail sampling processor: https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor

**Kết luận:** sampling giúp kiểm soát lượng trace, endpoint xác định đúng nơi gửi/nhận/truy vấn, còn authentication và TLS bảo vệ ai được phép trao đổi dữ liệu. Ba lớp cần được cấu hình và kiểm tra độc lập. Khi kết hợp chúng với metrics, trace storage và evaluation results có provenance, nhóm phát triển Spring AI có thể điều tra lỗi RAG/tool, theo dõi token/chi phí/độ trễ và so sánh các phiên bản mà không biến telemetry thành một kênh rò rỉ dữ liệu hoặc điểm yếu vận hành.
