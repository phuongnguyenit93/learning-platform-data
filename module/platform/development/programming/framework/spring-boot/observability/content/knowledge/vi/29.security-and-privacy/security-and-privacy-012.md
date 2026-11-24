# Kiểm tra quyền đọc metrics trong Spring Boot

> **Chương:** Security và privacy  
> **Bài:** Kiểm tra quyền đọc metrics  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vì sao cần kiểm tra quyền đọc metrics?

Metrics thường được xem là dữ liệu vận hành, nhưng chúng có thể tiết lộ topology, tên service nội bộ, route, dependency, traffic pattern, trạng thái lỗi và năng lực hệ thống. Một endpoint metrics mở cho mọi caller có thể giúp người ngoài suy ra cấu trúc ứng dụng hoặc thời điểm hệ thống đang gặp sự cố.

**Kiểm tra quyền đọc metrics** là xác minh chỉ những danh tính và network paths được phép mới có thể truy cập dữ liệu metrics. Việc này bao gồm nhiều lớp: listener/network exposure, TLS, authentication, authorization, endpoint exposure và chính sách dữ liệu.

Một lần scrape thành công cần đáp ứng đồng thời:
- Scraper kết nối được tới management listener.
- TLS và danh tính peer được xác minh khi dùng HTTPS/mTLS.
- Scraper xác thực bằng cơ chế được chọn.
- Identity có quyền đọc đúng endpoint.
- Endpoint đã được expose và registry/exporter tồn tại.
- Response không tiết lộ dữ liệu ngoài phạm vi được phép.

~~~mermaid
flowchart TD
  A["Prometheus / scraper"] --> B["Network policy / firewall"]
  B --> C["TLS listener"]
  C --> D["Authentication"]
  D --> E["Authorization"]
  E --> F["Actuator endpoint exposure"]
  F --> G["Prometheus registry"]
  G --> H["Metrics response"]
~~~

HTTP 200 chỉ chứng minh request cụ thể đã được chấp nhận. Nó không chứng minh policy tổng thể là an toàn. Cần kiểm tra cả caller hợp lệ, caller không hợp lệ và các đường truy cập khác như public ingress hoặc JMX.

## 2. Exposure khác authentication và authorization

Ba khái niệm này giải quyết các vấn đề khác nhau:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Exposure | Endpoint có được publish qua web/JMX không? | Expose prometheus |
| Authentication | Caller là ai? | Basic credentials, client certificate, token |
| Authorization | Caller được làm gì? | Role MONITORING được GET metrics |
| Network reachability | Caller có thể tới listener không? | Private subnet, NetworkPolicy |
| TLS | Kết nối và peer có được bảo vệ/xác minh không? | HTTPS, mutual TLS |

Cấu hình exposure không tự tạo authentication hoặc authorization. Ngược lại, một endpoint không exposed qua web có thể vẫn được expose qua JMX nếu JMX được cấu hình riêng.

Một endpoint exposed nhưng Spring Security từ chối caller vẫn không thể đọc dữ liệu. Một endpoint có authentication nhưng listener public và không giới hạn network vẫn có thể bị dò quét hoặc tấn công brute force.

## 3. Chỉ expose endpoint cần thiết

Với Prometheus registry, endpoint thường dùng là /actuator/prometheus. Cấu hình ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

Chỉ expose health và prometheus nếu đó là nhu cầu của ứng dụng. Không thêm env, configprops, heapdump, threaddump, logfile hoặc beans vào danh sách chỉ để tiện debug.

Nếu không dùng Prometheus, metrics endpoint tổng quát có thể là /actuator/metrics. Không nên expose cả metrics và prometheus nếu scraper chỉ cần một endpoint.

Exposure cần được đánh giá cùng management port và base path. Nếu management listener chạy riêng, hãy giới hạn đường mạng tới port đó; không đưa nó vào public ingress.

## 4. Tạo security policy riêng cho management endpoints

Khi Spring Security có mặt, Actuator endpoints có thể được bảo vệ bằng SecurityFilterChain. Nếu ứng dụng tự khai báo chain, hãy định tuyến management requests rõ ràng và đảm bảo thứ tự chain đúng.

Ví dụ cấu hình minh họa:

~~~java
@Configuration
@EnableWebSecurity
public class ManagementSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                EndpointRequest.to("health"))
                        .permitAll()
                        .requestMatchers(
                                EndpointRequest.to("prometheus"))
                        .hasRole("MONITORING")
                        .anyRequest()
                        .denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .build();
    }
}
~~~

Đây là ví dụ khung. Cần dependency Actuator/Security, authentication provider, matcher và endpoint IDs phù hợp phiên bản Spring Boot. Nếu health probe cần truy cập không xác thực, chỉ permit health path/group cần thiết. Không permit toàn bộ /actuator/**.

Một chain riêng giúp tránh vô tình áp dụng rule API nghiệp vụ cho management endpoints hoặc ngược lại. Kiểm thử thực tế để xác nhận request đi vào chain dự kiến.

## 5. Tạo identity riêng cho scraper

Prometheus scraper nên có identity dành riêng cho nhiệm vụ đọc metrics. Không dùng tài khoản administrator, tài khoản người vận hành hoặc credentials của ứng dụng nghiệp vụ.

Một identity monitoring nên:
- Chỉ được GET endpoint metrics cần thiết.
- Không được gọi POST/DELETE hoặc endpoint thay đổi trạng thái.
- Không có quyền đọc env/configprops/heapdump.
- Có credential riêng theo môi trường hoặc workload identity.
- Có chu kỳ rotation và quy trình thu hồi.
- Được ghi nhận trong secret manager và audit policy.

Ví dụ in-memory user chỉ phù hợp local/test:

~~~java
@Bean
UserDetailsService monitoringUsers(PasswordEncoder encoder) {
    UserDetails scraper = User.withUsername("metrics-scraper")
            .password(encoder.encode("replace-with-secret"))
            .roles("MONITORING")
            .build();

    return new InMemoryUserDetailsManager(scraper);
}
~~~

Không commit password minh họa vào source control. Production nên lấy credentials từ secret management hoặc tích hợp identity provider phù hợp. Nếu nhiều replicas, identity và rotation phải được triển khai nhất quán.

## 6. Quyền GET không đồng nghĩa quyền quản trị

Metrics scraping thường chỉ cần HTTP GET. Policy nên giới hạn method và endpoint thay vì cấp một role quản trị rộng.

Ví dụ policy mong muốn:

| Caller | GET health | GET prometheus | GET env | POST shutdown |
| --- | --- | --- | --- | --- |
| Kubelet probe | Cho phép theo network/policy | Từ chối | Từ chối | Từ chối |
| Metrics scraper | Theo policy | Cho phép | Từ chối | Từ chối |
| Operator | Theo role | Theo role | Có thể bị hạn chế | Từ chối mặc định |
| Public client | Chỉ khi thiết kế cho phép | Từ chối | Từ chối | Từ chối |

Nếu endpoint metrics chỉ hỗ trợ GET, không có lý do cấp write permission. Nếu dùng role MONITORING, không tái sử dụng role này cho các endpoint nhạy cảm khác.

## 7. Basic authentication, token và mTLS

Có nhiều cách xác thực scraper:

### 7.1. HTTP Basic authentication

Prometheus có thể gửi username/password qua HTTPS. Basic auth đơn giản nhưng credentials cần được bảo vệ trong secret và rotation. Không gửi Basic credentials qua HTTP không mã hóa.

### 7.2. Bearer token

Một reverse proxy, service mesh hoặc authentication layer có thể xác minh bearer token. Cần kiểm tra issuer, audience, expiry, signature và rotation. Không tự viết filter xác minh JWT nếu framework/security platform đã cung cấp cơ chế chuẩn.

### 7.3. Mutual TLS

mTLS xác minh client certificate ở tầng TLS. Có thể giới hạn certificate issuer/SAN và map client identity vào authorization policy. mTLS bảo vệ kết nối và xác thực peer; vẫn cần xác định certificate đó được phép đọc endpoint nào.

Không bật nhiều cơ chế chồng chéo mà không xác định trách nhiệm. Ví dụ proxy terminate mTLS nhưng application tin mọi header identity từ bất kỳ nguồn nào sẽ tạo lỗ hổng nếu backend có thể truy cập trực tiếp.

## 8. Prometheus scrape configuration và secret handling

Prometheus hỗ trợ cấu hình xác thực cho scrape target. Ví dụ Basic auth minh họa:

~~~yaml
scrape_configs:
  - job_name: order-service
    metrics_path: /actuator/prometheus
    scheme: https
    static_configs:
      - targets:
          - order-service.internal:8081
    basic_auth:
      username: metrics-scraper
      password_file: /etc/prometheus/secrets/order-service-password
    tls_config:
      ca_file: /etc/prometheus/certs/internal-ca.pem
      server_name: order-service.internal
~~~

Ví dụ cần được điều chỉnh theo Prometheus version, deployment và certificate topology. Dùng password_file/secret mount hoặc secret integration, không ghi password trực tiếp vào file cấu hình được commit.

Bảo vệ cả:
- Prometheus configuration và generated config.
- Secret files và file permissions.
- Backup/snapshot của Prometheus.
- Admin API và UI của Prometheus.
- Remote write credentials và telemetry backend.
- Logs có thể vô tình chứa Authorization header.

Scrape credentials là secret có thể đọc dữ liệu vận hành. Rotation cần cập nhật cả scraper và target theo quy trình có thể kiểm thử.

## 9. Management port và network isolation

Tách management port giúp giới hạn đường truy cập nhưng không tự bảo vệ port. Ví dụ:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

Application traffic đi qua 8080; management traffic qua 8081. Trong Kubernetes, public Service có thể chỉ target 8080; Prometheus dùng Pod discovery hoặc internal-only Service tới 8081.

Network controls nên:
- Chỉ cho phép Prometheus/monitoring namespace hoặc subnet được truy cập management port.
- Chặn public ingress tới management listener.
- Giới hạn egress/ingress theo service identity khi platform hỗ trợ.
- Tránh bind loopback nếu scraper ở network namespace khác.
- Kiểm tra NodePort/LoadBalancer/Ingress không vô tình expose management port.

Network isolation bổ sung cho application authentication. Nếu network policy bị cấu hình sai, authorization vẫn là lớp bảo vệ tiếp theo.

## 10. TLS termination và reverse proxy

Nếu reverse proxy terminate TLS, cần xác định:
- Proxy có xác thực scraper hay không.
- Kết nối proxy tới application có được mã hóa hoặc nằm trong trusted network không.
- Backend management port có thể bị truy cập trực tiếp không.
- Forwarded headers/identity headers có được proxy ghi đè và bảo vệ không.
- Proxy có log Authorization header hay không.

Không tin header như X-Remote-User từ mọi client. Chỉ tin identity header khi backend chỉ nhận traffic từ proxy được xác thực và proxy luôn loại bỏ header do client tự gửi trước khi đặt giá trị đã xác minh.

Nếu có thể, dùng mTLS giữa proxy và backend hoặc workload identity. Không tắt hostname verification để giải quyết certificate mismatch.

## 11. Metrics cũng có thể chứa dữ liệu nhạy cảm

Ngay cả khi endpoint được bảo vệ, nội dung metrics cần được thiết kế an toàn.

Rủi ro có thể đến từ:
- Label chứa user/customer/order ID.
- URI chứa identifier hoặc query string.
- Exception message hoặc SQL text thành tag.
- Tên tenant/customer có tính nhạy cảm.
- Metric name tiết lộ tính năng nội bộ hoặc dependency.
- Label values cho biết trạng thái bảo mật hoặc hoạt động của một nhóm nhỏ.

Ưu tiên labels có cardinality thấp: service, operation, method, outcome, status class và route template. Không dùng metrics làm kho lưu từng sự kiện hoặc từng giao dịch.

Kiểm tra cả dữ liệu trước khi export và dữ liệu đã lưu trong Prometheus/remote backend. Một label bị lộ vẫn có thể tồn tại trong retention, snapshot và bản sao lưu sau khi sửa code.

## 12. Kiểm tra quyền đọc bằng ma trận test

Cần test nhiều identity và trạng thái, không chỉ thử scraper hợp lệ.

| Test | Kết quả mong đợi |
| --- | --- |
| Scraper có credentials hợp lệ, GET prometheus | 200 |
| Không gửi credentials | 401 nếu endpoint yêu cầu authentication |
| Credentials sai | 401 |
| Identity hợp lệ nhưng thiếu role | 403 |
| Monitoring role gọi endpoint env | 403 hoặc endpoint không exposed/404 theo policy |
| Monitoring role gửi POST tới metrics | 403/405 |
| Public network truy cập management port | Không kết nối được theo network policy |
| Certificate không tin cậy | TLS handshake bị từ chối |
| Certificate hợp lệ nhưng không được authorize | Bị từ chối ở authorization |
| Scraper dùng path sai | 404 |

Status code cụ thể phụ thuộc security chain, endpoint exposure và proxy. Mục tiêu là caller chỉ đọc được dữ liệu đúng phạm vi.

### 12.1. Test bằng curl trong môi trường kiểm thử

Ví dụ gọi endpoint có Basic auth:

~~~bash
curl --fail --user metrics-scraper \
  https://order-service.internal:8081/actuator/prometheus
~~~

curl sẽ hỏi password nếu không truyền password trên command line. Tránh ghi secret trực tiếp trong shell history hoặc process arguments. Với production, dùng secret injection của môi trường vận hành và công cụ phù hợp.

Kiểm tra negative cases bằng request không credentials, sai credentials và role không đủ quyền. Không dùng tài khoản operator để test scraper permission.

## 13. Audit và rotation

Quyền đọc metrics cần được vận hành như một access path có vòng đời:
- Ai sở hữu scraper identity?
- Credential được lưu ở đâu?
- Khi nào rotate?
- Làm thế nào revoke một target bị xâm phạm?
- Có audit log cho failed/successful access không?
- Có cảnh báo brute force hoặc scrape bất thường không?
- Credentials có xuất hiện trong logs, traces hoặc crash dumps không?

Scrape thường xuyên có thể tạo nhiều access logs. Dùng log policy phù hợp: ghi identity, endpoint, status và source metadata cần thiết; tránh ghi Authorization header hoặc token.

Rotation nên có thể triển khai không làm gián đoạn monitoring quá lâu. Với nhiều replicas, đảm bảo mọi instance nhận policy mới và old credential được thu hồi sau khi scraper chuyển đổi.

## 14. Troubleshooting quyền đọc metrics

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| 404 | Endpoint không exposed, registry thiếu hoặc path sai | Exposure config, dependency, base path |
| 401 | Thiếu/sai credentials | Scraper secret, authentication provider |
| 403 | Identity xác thực nhưng thiếu authority | Role mapping, matcher, chain order |
| 200 nhưng không có metrics mong đợi | Meter chưa đăng ký hoặc filter/export config | Registry, meter filters, instrumentation |
| Scrape timeout | Network path, TLS, management server quá tải | Connectivity, server metrics |
| TLS handshake failure | CA/SAN/protocol mismatch | Trust chain và server name |
| Scraper truy cập được env | Matcher quá rộng hoặc role dùng chung | Security chain, endpoint-specific authorization |
| Public caller đọc được metrics | Management port/ingress mở rộng | Service, ingress, firewall, NetworkPolicy |
| Scrape lỗi sau rotation | Secret target và scraper lệch version | Rollout/rotation procedure |
| Backend thấy credentials trong log | Proxy/app log headers | Redact Authorization và kiểm tra log pipeline |
| Metrics tiết lộ identifiers | Labels cardinality cao hoặc nhạy cảm | Meter tags, URI convention, redaction |
| Một số replicas trả 401/403 | Config/secret rollout không đồng nhất | Pod configuration và mounted secret version |

### Quy trình điều tra

1. Kiểm tra target URL, scheme, port và path.
2. Xác nhận network route tới management listener.
3. Kiểm tra TLS certificate, CA và hostname.
4. Xác minh scraper identity và authentication method.
5. Kiểm tra authorization rule, endpoint matcher và filter-chain order.
6. Xác nhận endpoint exposure và registry/exporter.
7. Thử positive/negative access matrix.
8. Kiểm tra labels/response không lộ dữ liệu ngoài phạm vi.
9. Đối chiếu logs nhưng không in secret.

## 15. Tình huống thực tế: chỉ Prometheus được đọc metrics

**Bối cảnh:** order-service chạy trong Kubernetes. API public phục vụ port 8080; management port 8081 cung cấp health và Prometheus metrics. Đội vận hành muốn Prometheus scrape metrics nhưng không cho public clients đọc.

### Bước 1 — tách management listener

Cấu hình management.server.port là 8081. Public Service chỉ target application port 8080.

### Bước 2 — giới hạn exposure

Expose health và prometheus. Không expose env, configprops hoặc các endpoint quản trị khác.

### Bước 3 — tạo scraper identity

Tạo identity metrics-scraper có authority MONITORING. Lưu credentials trong secret store và mount vào Prometheus theo cơ chế được platform hỗ trợ.

### Bước 4 — authorization

SecurityFilterChain chỉ cho role MONITORING GET prometheus. Health probe được permit theo policy cụ thể. Các management endpoints còn lại bị deny hoặc không exposed.

### Bước 5 — network isolation và TLS

NetworkPolicy chỉ cho phép Prometheus namespace tới port 8081. Scrape dùng HTTPS với CA tin cậy. Không tạo public ingress tới management listener.

### Bước 6 — kiểm thử

- Prometheus có credentials: scrape thành công.
- Caller không credentials: bị từ chối.
- Identity thiếu role: bị từ chối.
- Public network: không kết nối tới management port.
- Metrics response không chứa ID hoặc secret trong labels.
- Rotation credential không làm scrape gián đoạn ngoài cửa sổ dự kiến.

**Kết quả mong muốn:** chỉ scraper có danh tính và network path hợp lệ đọc được metrics; application API vẫn phục vụ traffic bình thường.

## 16. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — phân biệt các lớp bảo vệ

Vẽ luồng từ Prometheus tới /actuator/prometheus. Đánh dấu network policy, TLS, authentication, authorization, endpoint exposure và registry. Xác định lỗi 401/403/404/timeout ở lớp nào.

### Bài tập B — SecurityFilterChain

Tạo chain riêng cho Actuator. Permit health probe theo policy và yêu cầu role MONITORING cho prometheus. Deny các endpoint khác. Test đúng thứ tự chain và method.

### Bài tập C — negative access tests

Gửi request không credentials, credentials sai, role không đủ quyền và POST tới metrics. Xác nhận không caller nào ngoài policy đọc được response.

### Bài tập D — Prometheus secret

Cấu hình scrape bằng password file/secret mount và TLS CA. Kiểm tra secret không nằm trong source control, logs hoặc command history. Thực hiện rotation trong môi trường test.

### Bài tập E — network isolation

Trong Kubernetes, public Service chỉ expose application port. Tạo management access nội bộ cho Prometheus. Kiểm tra NetworkPolicy và Pod discovery từ đúng namespace.

### Bài tập F — metrics privacy review

Kiểm tra meter names và tag values. Loại bỏ user/order IDs, raw URI, SQL text và exception message. Kiểm tra response scrape và dữ liệu lưu ở backend.

### Câu hỏi tự kiểm tra

1. Endpoint exposure khác authentication và authorization thế nào?
2. Vì sao management port riêng không tự bảo vệ metrics?
3. Scraper cần quyền tối thiểu nào?
4. 401 và 403 thường biểu thị điều gì?
5. Khi nào 404 là dấu hiệu endpoint chưa exposed?
6. Basic authentication cần được bảo vệ bằng lớp nào?
7. mTLS xác thực peer nhưng vì sao vẫn cần authorization?
8. Làm sao tránh tin identity headers do client tự gửi?
9. Prometheus nên lưu credentials ở đâu?
10. Vì sao không nên expose env/configprops cùng metrics?
11. Metric labels có thể tiết lộ dữ liệu gì?
12. Làm thế nào kiểm tra quyền đọc bằng positive và negative tests?
13. Khi rotate scraper credentials cần phối hợp những thành phần nào?
14. Vì sao cần bảo vệ cả Prometheus UI, API và remote write?
15. Làm sao phân biệt lỗi network, TLS, authentication, authorization và registry?

**Tiêu chí hoàn thành:** phân biệt exposure/authentication/authorization/network; cấu hình quyền GET metrics tối thiểu; bảo vệ scraper credentials; dùng TLS/mTLS phù hợp; giới hạn management port; test 200/401/403/404; kiểm tra metrics labels và audit/rotation.

## 17. Ghi nhớ

- Metrics là dữ liệu vận hành có thể tiết lộ topology, route, dependency và traffic patterns.
- Endpoint exposure chỉ publish endpoint; nó không tự xác thực hoặc cấp quyền.
- Dùng identity riêng cho scraper và chỉ cấp quyền GET endpoint metrics cần thiết.
- Bảo vệ scrape bằng TLS; dùng mTLS hoặc token khi phù hợp với platform.
- Management port riêng cần network isolation và authorization; không phải security boundary tự động.
- Không expose env, configprops, heapdump hoặc endpoint quản trị cho role MONITORING.
- Prometheus credentials phải nằm trong secret management, được rotate và không xuất hiện trong logs.
- Kiểm tra positive và negative access cases: hợp lệ, thiếu credentials, sai credentials, thiếu role, method/path ngoài policy.
- Labels cần low-cardinality và không chứa identifiers, PII, SQL text hoặc exception message.
- Bảo vệ cả metrics endpoint, Prometheus server, UI/API, remote write và dữ liệu lưu trữ.
- Dùng audit/monitoring access để phát hiện scrape bất thường và xử lý rotation/revocation.

## Tài liệu tham khảo

- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Reference — Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.security)
- [Spring Boot Reference — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
- [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Prometheus — Configuration and Scrape Authentication](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [OpenTelemetry — Data Security](https://opentelemetry.io/docs/security/)

