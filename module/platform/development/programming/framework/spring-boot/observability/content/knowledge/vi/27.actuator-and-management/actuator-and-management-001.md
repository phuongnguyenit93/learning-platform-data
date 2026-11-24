# Spring Boot Actuator

Trong chương **Actuator và management** của mô-đun **SPRING_BOOT_OBSERVABILITY**, Spring Boot Actuator cung cấp các tính năng quản lý và giám sát ứng dụng khi chạy. Actuator expose các endpoints để xem health, metrics, thông tin ứng dụng, cấu hình và trạng thái runtime. Khi kết hợp với Micrometer Observation và Micrometer Tracing, Actuator trở thành một phần quan trọng trong quy trình kiểm tra logs, metrics, traces và sức khỏe service ở môi trường thực.

Actuator không chỉ là một tập URL để mở ra internet. Mỗi endpoint có mục đích, mức độ nhạy cảm và yêu cầu bảo vệ khác nhau. Một số endpoint phù hợp cho health probes, một số dành cho operator có quyền cao, còn endpoint thay đổi cấu hình hoặc hiển thị environment cần giới hạn chặt chẽ. Cần phân biệt endpoint được **enable**, được **expose** qua HTTP/JMX và được **authorize** bởi security policy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích vai trò của Spring Boot Actuator trong vận hành ứng dụng.
2. Phân biệt endpoint enablement, exposure và authorization.
3. Cấu hình HTTP/JMX exposure theo nguyên tắc tối thiểu.
4. Sử dụng health, info, metrics và prometheus endpoints.
5. Hiểu rủi ro của env, configprops, loggers, threaddump và heapdump.
6. Thiết lập management port, base path và network boundary.
7. Cấu hình liveness/readiness health groups cho deployment platform.
8. Liên hệ Actuator với Micrometer metrics, Observation và tracing.
9. Viết kiểm thử cho health status, endpoint exposure và security.
10. Xây dựng runbook cho health probe fail, metrics missing và management access issues.

## 2. Actuator là gì?

Spring Boot Actuator cung cấp các tính năng production-ready để theo dõi và quản lý ứng dụng. Actuator tích hợp với ApplicationContext và các thành phần framework để expose thông tin qua các endpoints.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Spring Boot dependency management chọn phiên bản tương thích. Không tự thêm version riêng nếu dự án đang dùng Boot BOM/parent.

Sau khi thêm starter, endpoints có thể được auto-configure tùy dependencies, environment và version. Mặc định chỉ một số endpoints được expose qua HTTP; không có nghĩa tất cả endpoints đều public hoặc mọi thông tin đều được truy cập.

~~~mermaid
flowchart TD
    App["Spring Boot application"]
    App --> Actuator["Spring Boot Actuator"]
    Actuator --> Health["Health endpoints"]
    Actuator --> Metrics["Micrometer metrics"]
    Actuator --> Info["Application info"]
    Actuator --> Runtime["Runtime diagnostics"]
    Metrics --> Registry["MeterRegistry"]
    Registry --> Backend["Prometheus / metrics backend"]
    App --> Obs["Observation / Tracing"]
    Obs --> TraceBackend["Trace backend"]
    App --> Logs["Logging pipeline"]
    Logs --> LogBackend["Log backend"]
~~~

Actuator cung cấp giao diện truy cập health và metrics trong ứng dụng. Nó không thay thế metrics backend, tracing exporter hoặc log storage. Các tín hiệu có pipeline riêng nhưng có thể dùng cùng service identity để hỗ trợ correlation.

## 3. Endpoint enablement, exposure và authorization

Ba khái niệm cần phân biệt:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Enablement | Endpoint có được tạo/cho phép hoạt động không? | management.endpoint.health.enabled=true |
| Exposure | Endpoint được truy cập qua transport nào? | HTTP hoặc JMX. |
| Authorization | Người gọi có quyền truy cập endpoint không? | Spring Security role/operator. |

Một endpoint có thể enabled nhưng không exposed qua HTTP. Endpoint exposed vẫn có thể bị security layer chặn. Vì vậy, cấu hình expose endpoint không đồng nghĩa cho phép mọi người truy cập.

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Chỉ expose những endpoints cần cho monitoring. Tránh cấu hình wildcard trong production trừ khi có security boundary và threat model đã được kiểm chứng.

Có thể loại trừ endpoint cụ thể:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
        exclude: env,configprops,heapdump,threaddump
~~~

Danh sách endpoint và property semantics có thể thay đổi theo version. Kiểm tra reference docs của Spring Boot minor version đang dùng.

## 4. Health endpoint

/actuator/health cung cấp trạng thái tổng thể và có thể tổng hợp health indicators từ ứng dụng, database, disk space, broker hoặc dependency khác.

~~~http
GET /actuator/health
~~~

Response minh họa:

~~~json
{
  "status": "UP"
}
~~~

Khi được phép hiển thị components/details, response có thể chứa thông tin chi tiết:

~~~json
{
  "status": "UP",
  "components": {
    "db": { "status": "UP" },
    "diskSpace": { "status": "UP" },
    "ping": { "status": "UP" }
  }
}
~~~

Không expose health details công khai nếu chúng tiết lộ topology, database type, dependency names hoặc thông tin nội bộ. Dùng role phù hợp để operator xem details; health probes có thể chỉ cần status.

### Readiness và liveness

Spring Boot hỗ trợ health groups cho liveness và readiness:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
        liveness:
          include: livenessState
~~~

Cấu hình include chỉ là ví dụ; có nên đưa database vào readiness hay không phụ thuộc kiến trúc. Nếu database tạm thời mất kết nối khiến tất cả replicas bị đánh dấu unready, traffic có thể bị loại khỏi toàn bộ service trong khi ứng dụng vẫn xử lý được một số requests khác. Đừng đưa dependency bên ngoài vào liveness: liveness nên phản ánh process có cần restart hay không, tránh restart loop do dependency outage.

- **Liveness**: process có còn sống và có thể tiếp tục chạy không?
- **Readiness**: instance đã sẵn sàng nhận traffic chưa?
- **Startup probe**: dành cho platform cần thời gian khởi động dài trước khi áp dụng liveness.

Kubernetes hoặc nền tảng deployment có thể gọi các health group endpoints. Bảo đảm probe path, port và access policy khớp cấu hình cluster.

## 5. Info endpoint

/actuator/info cung cấp thông tin ứng dụng được cấu hình qua InfoContributor, build metadata, git metadata hoặc custom contributors.

~~~http
GET /actuator/info
~~~

~~~yaml
info:
  app:
    name: order-service
    description: Order processing API
    version: 2.4.0
~~~

Không đưa secrets, environment variables, private repository URLs hoặc thông tin nhạy cảm vào info. Version/build metadata nên hữu ích cho vận hành nhưng không tiết lộ chi tiết nội bộ không cần thiết.

## 6. Metrics và Prometheus endpoints

Actuator metrics endpoint cho phép xem meter đã đăng ký:

~~~http
GET /actuator/metrics
GET /actuator/metrics/http.server.requests
~~~

Endpoint có thể trả measurements và available tag values. Nó phù hợp để debug meter trong một instance; metrics backend phù hợp để lưu trữ, aggregate và truy vấn theo thời gian.

Nếu dùng Prometheus registry, thêm dependency:

~~~groovy
dependencies {
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

Prometheus scrape endpoint thường là:

~~~http
GET /actuator/prometheus
~~~

Prometheus server scrape URL của từng instance hoặc service discovery target. Bảo vệ endpoint khỏi truy cập không được phép; metrics có thể tiết lộ tên service, route, dependency và hoạt động nội bộ.

Metrics không phải trace. /actuator/metrics không phải nơi xem distributed trace. Cần tracing bridge/exporter và trace backend riêng để truy vấn spans.

## 7. Các endpoints runtime và diagnostics

| Endpoint | Mục đích | Rủi ro/chú ý |
| --- | --- | --- |
| env | Xem Environment properties. | Có thể lộ cấu hình và secrets nếu sanitization/access sai. |
| configprops | Xem bound configuration properties. | Có thể lộ cấu hình nhạy cảm; cần sanitization. |
| loggers | Xem/đổi logging levels runtime. | Có thể tăng log volume hoặc bật log dữ liệu nhạy cảm. |
| threaddump | Chụp thread state/stack. | Có thể lộ tên class, arguments hoặc nội dung nội bộ; payload lớn. |
| heapdump | Tạo heap dump. | Có thể chứa secrets, tokens, PII và dữ liệu trong memory. |
| conditions | Xem auto-configuration conditions. | Tiết lộ cấu trúc ứng dụng và dependencies. |
| beans | Liệt kê Spring beans. | Tiết lộ nội bộ application context. |
| mappings | Liệt kê handler mappings. | Tiết lộ API routes. |
| scheduledtasks | Liệt kê scheduled tasks. | Tiết lộ tên job và lịch thực thi. |

Không expose các endpoints này rộng rãi. Heap dump đặc biệt nhạy cảm: coi file dump như dữ liệu production bí mật, giới hạn nơi lưu, thời gian tồn tại và người có thể tải xuống.

### Loggers endpoint

/actuator/loggers có thể xem logger levels và trong một số cấu hình cho phép thay đổi mức log runtime. Nếu operator tăng DEBUG/TRACE để điều tra, cần authorization role riêng, audit thay đổi logger level, thời hạn bật và quy trình khôi phục, rà soát output tránh secrets/PII và giới hạn log volume/storage.

## 8. Management port và base path

Mặc định Actuator web endpoints thường được phục vụ cùng application port dưới base path /actuator. Có thể thay đổi:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
~~~

Có thể dùng management port riêng:

~~~yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
~~~

Ví dụ chỉ phù hợp khi process và monitoring agent có thể truy cập loopback. Trong container/Kubernetes, bind loopback có thể khiến probe từ node hoặc sidecar không truy cập được. Chọn address/interface theo network architecture.

Management port riêng có thể tạo management web server context riêng và có khác biệt về SSL, base path và security. Không giả định management port tự động an toàn: vẫn cần firewall, network policy, authentication và authorization.

Khi health endpoint chạy ở management port, probe phải gọi đúng port/path. Nếu management context không khởi động hoặc bị firewall chặn, platform có thể đánh dấu instance unhealthy dù application port vẫn xử lý request. Kiểm thử từ đúng network namespace/agent sẽ dùng trong production.

## 9. Bảo vệ Actuator bằng Spring Security

Trong production, chỉ expose endpoints cần thiết và bảo vệ bằng Spring Security hoặc network-level controls. Ví dụ SecurityFilterChain:

~~~java
@Configuration(proxyBeanMethods = false)
class ActuatorSecurityConfiguration {

    @Bean
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(EndpointRequest.to("health", "info"))
                        .permitAll()
                        .anyRequest().hasRole("OPS"))
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

Đây là ví dụ minh họa cho ứng dụng có authentication phù hợp. Nếu health details chứa thông tin nội bộ, có thể cần role riêng cho details. Nếu ứng dụng đã có security chains khác, kiểm tra order và matcher để tránh chain Actuator vô tình chiếm toàn bộ requests.

Nguyên tắc:
- Chỉ mở health status tối thiểu cho probe.
- Metrics/prometheus chỉ cho monitoring system được phép.
- env/configprops/heapdump/threaddump/loggers chỉ cho operator có quyền cao và có audit.
- Dùng TLS khi đi qua network không tin cậy.
- Không nhúng credentials trong URL hoặc script log.
- Áp dụng network policy/firewall song song với application authorization.

## 10. Health contributors và custom health indicator

Ứng dụng có thể thêm HealthIndicator để kiểm tra dependency hoặc subsystem riêng:

~~~java
@Component
class SearchHealthIndicator implements HealthIndicator {

    private final SearchClient searchClient;

    SearchHealthIndicator(SearchClient searchClient) {
        this.searchClient = searchClient;
    }

    @Override
    public Health health() {
        try {
            searchClient.ping();
            return Health.up().withDetail("service", "search").build();
        } catch (Exception ex) {
            return Health.down()
                    .withDetail("service", "search")
                    .withDetail("error", ex.getClass().getSimpleName())
                    .build();
        }
    }
}
~~~

Health check nên có timeout ngắn và rõ ràng, không thực hiện truy vấn nặng/scan dữ liệu, không trả credentials hoặc exception messages đầy đủ, phân biệt readiness/liveness và tránh cascading failures khi dependency outage.

Một health check gọi hàng loạt downstream service mỗi giây có thể làm sự cố nặng hơn. Dùng lightweight ping/cache hoặc health signal do client quản lý khi phù hợp.

## 11. Metrics, tracing và Actuator integration

~~~mermaid
flowchart LR
    App["Spring Boot"]
    App --> Actuator["Actuator endpoints"]
    App --> Metrics["Micrometer meters"]
    App --> Obs["Observation / Tracing"]
    Metrics --> Registry["MeterRegistry"]
    Registry --> MetricsBackend["Prometheus / metrics backend"]
    Obs --> TraceExporter["Tracing exporter"]
    TraceExporter --> TraceBackend["OTLP / Zipkin backend"]
    Actuator --> Operator["Authorized operator / probe"]
~~~

Điều cần nhớ:
- Expose /actuator/metrics không tự bật exporter.
- Có /actuator/prometheus cần Prometheus registry dependency.
- Có trace spans cần tracing bridge/exporter và sampling phù hợp.
- Health UP không đảm bảo mọi business operation đều hoạt động.
- Một metric không xuất hiện ở Actuator có thể do meter chưa được tạo, registry filter hoặc endpoint access; không nhất thiết do exporter backend.

## 12. Cấu hình production tham khảo

~~~yaml
management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
  server:
    port: 9091
~~~

Cấu hình này giả định security/network policy đã bảo vệ management port. Không dùng show-details: always trên endpoint public. Với Prometheus, chỉ cho scrape target được tin cậy truy cập. Nếu muốn dùng metrics endpoint trong nội bộ để debug, cân nhắc expose có kiểm soát thay vì mở tất cả.

~~~yaml
info:
  app:
    name: order-service
    version: "2.4.0"
    environment: production
~~~

Không đưa secret hoặc environment dump vào info.

## 13. Kiểm thử Actuator endpoints

Có thể dùng Spring Boot test và MockMvc để xác minh endpoint:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ActuatorEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void healthEndpointIsAvailable() throws Exception {
        mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}
~~~

Test cần đúng security configuration và endpoint exposure của ứng dụng. Nếu health indicator phản ánh database hoặc dependency thật, mock/replace dependency trong test.

Các test quan trọng:
1. Health endpoint trả status đúng khi dependency healthy/unhealthy.
2. Readiness/liveness groups không kéo dependency không cần thiết.
3. Endpoint nhạy cảm bị từ chối với anonymous/non-operator.
4. Prometheus endpoint chỉ được monitoring identity truy cập.
5. Base path và management port khớp deployment config.
6. Health details được ẩn hoặc chỉ hiển thị khi authorized.
7. Loggers endpoint có audit và không cho role không phù hợp đổi level.
8. Heapdump/threaddump không được expose ngoài operator boundary.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| /actuator/health trả 404 | Health endpoint không enabled/exposed hoặc base path khác. | Kiểm tra dependency, endpoint enablement và base-path. |
| Endpoint enabled nhưng không truy cập được | Không exposed qua HTTP/JMX hoặc security chặn. | Kiểm tra exposure và SecurityFilterChain. |
| Prometheus endpoint không tồn tại | Thiếu registry dependency hoặc chưa expose endpoint. | Kiểm tra runtime dependency và exposure include. |
| Health DOWN nhưng app vẫn nhận request | Health indicator kiểm tra dependency không thiết yếu hoặc readiness/liveness mapping sai. | Xem component details và health group membership. |
| Kubernetes probe fail | Sai management port/path/address hoặc security policy chặn probe. | Curl từ network context tương đương probe. |
| Health details không hiển thị | show-details policy yêu cầu authorization. | Kiểm tra authenticated role và health settings. |
| Metrics endpoint không có meter | Meter chưa được tạo, filter loại bỏ hoặc registry khác. | Tạo hoạt động, kiểm tra MeterRegistry và availableTags. |
| Heapdump download bị từ chối | Endpoint không enabled/exposed hoặc access policy. | Chỉ bật tạm thời cho operator theo quy trình. |
| Actuator port không kết nối được | Bind address/firewall/network policy sai. | Kiểm tra listener và route từ monitoring system. |
| Log level không đổi | Security hoặc endpoint exposure; logger name sai. | Kiểm tra authorization và logger configuration. |

## 15. Runbook: Actuator không truy cập được

1. Xác nhận starter actuator có trong runtime classpath.
2. Xác định Boot version và endpoint property semantics.
3. Kiểm tra endpoint enabled state.
4. Kiểm tra HTTP/JMX exposure include/exclude.
5. Xác nhận base path, management port và bind address.
6. Kiểm tra SecurityFilterChain, role và authentication.
7. Gọi endpoint từ đúng network namespace của probe/monitoring agent.
8. Với health fail, kiểm tra component status và readiness/liveness group.
9. Với metrics missing, xác nhận meter được tạo và registry không filter.
10. Với Prometheus, kiểm tra registry dependency, scrape target và response format.
11. Rà soát audit/logs cho access denied hoặc config binding warnings.
12. Chỉ expose diagnostics endpoints tạm thời theo quy trình operator và thu hồi sau điều tra.

## 16. Bài tập tự kiểm tra

### Bài 1 — Endpoint enablement

Bạn đặt management.endpoints.web.exposure.include=health,info. Vì sao /actuator/metrics không truy cập được?

**Đáp án:** Metrics không nằm trong danh sách HTTP exposure. Endpoint có thể được enable nhưng chưa expose qua HTTP.

### Bài 2 — Health UP

/actuator/health trả UP. Có thể kết luận mọi business operation đang hoạt động bình thường không?

**Đáp án:** Không. Health chỉ phản ánh health indicators đã cấu hình. Nó không chứng minh mọi route, queue, query hoặc business workflow đều khỏe.

### Bài 3 — Liveness và database

Database tạm thời unavailable. Có nên đưa DB vào liveness group để Kubernetes restart pod không?

**Đáp án:** Thường không. Liveness nên phản ánh process cần restart hay không; dependency outage có thể ảnh hưởng toàn cluster và gây restart loop. Readiness có thể xem xét tùy service semantics.

### Bài 4 — Prometheus endpoint

Actuator có /actuator/metrics nhưng không có /actuator/prometheus. Nguyên nhân thường gặp?

**Đáp án:** Chưa có Prometheus registry dependency hoặc endpoint chưa được expose qua HTTP.

### Bài 5 — Management port

Actuator chạy ở port 9091 nhưng Kubernetes probe gọi port 8080. Điều gì xảy ra?

**Đáp án:** Probe gọi sai port nếu endpoint chỉ lắng nghe ở management port. Cần đồng bộ probe port/path với management server config và network policy.

### Bài 6 — Heapdump

Có nên expose heapdump cho toàn bộ developer để tiện debug?

**Đáp án:** Không. Heap dump có thể chứa tokens, passwords, PII và dữ liệu trong memory. Chỉ operator có quyền phù hợp mới được truy cập theo quy trình kiểm soát.

## 17. Checklist triển khai

- [ ] Actuator dependency được quản lý theo Spring Boot BOM.
- [ ] Endpoint enablement, exposure và authorization được cấu hình riêng.
- [ ] Chỉ expose health/info/metrics/prometheus theo nhu cầu.
- [ ] Health details chỉ hiển thị với caller được phép.
- [ ] Liveness không phụ thuộc vào dịch vụ ngoài không thiết yếu.
- [ ] Readiness phản ánh đúng khả năng nhận traffic của instance.
- [ ] Management port/base path/bind address khớp network và probes.
- [ ] env/configprops/heapdump/threaddump/loggers được bảo vệ nghiêm ngặt.
- [ ] Prometheus registry dependency và scrape endpoint đã được xác minh.
- [ ] Metrics endpoint được bảo vệ khỏi truy cập không được phép.
- [ ] Tracing exporter được cấu hình riêng; Actuator không thay thế trace backend.
- [ ] Custom HealthIndicators có timeout và không tạo cascading failures.
- [ ] SecurityFilterChain có role/operator policy rõ ràng.
- [ ] Integration tests kiểm tra endpoint status, exposure và authorization.
- [ ] Có audit cho thay đổi logger levels và truy cập diagnostics.
- [ ] Có runbook và quy trình tắt exposure tạm thời sau sự cố.

**Ghi nhớ:** Spring Boot Actuator cung cấp giao diện quản lý health, metrics, info và runtime diagnostics. Hãy phân biệt endpoint được enable, được expose và được authorize; chỉ mở những gì monitoring/operator thực sự cần. Liveness/readiness phải phản ánh đúng semantics của deployment, management port phải khớp network probes, còn metrics/traces/logs vẫn cần registry/exporter/backend tương ứng. Bảo vệ endpoint diagnostics như một phần của security boundary production.
