# Authorization cho Actuator trong Spring Boot

Actuator cung cấp health, metrics và nhiều endpoint phục vụ vận hành. Những endpoint này có thể tiết lộ trạng thái database, topology nội bộ, route names, cấu hình ứng dụng hoặc dữ liệu chẩn đoán. Vì vậy, việc expose endpoint qua HTTP cần đi cùng authorization rõ ràng: health probe chỉ được đọc trạng thái cần thiết, monitoring agent được scrape metrics, còn endpoint quản trị chỉ dành cho operator có quyền phù hợp.

Trong Spring Boot, authorization cho Actuator thường được thực hiện bằng Spring Security kết hợp endpoint exposure và network controls. Ba lớp này giải quyết các câu hỏi khác nhau: endpoint có tồn tại không, endpoint có được đưa ra web không, và caller nào được phép truy cập. Chỉ cấu hình exposure không tạo authentication; chỉ có role trong Security cũng không làm một endpoint chưa expose tự xuất hiện.

Bài **Authorization cho actuator** thuộc chương **Security và privacy** của module **SPRING_BOOT_OBSERVABILITY**. Module tập trung thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt endpoint availability, exposure, authentication và authorization.
- Bảo vệ Actuator endpoints bằng Spring Security request matchers.
- Thiết kế quyền riêng cho health probes, metrics scraping và operator endpoints.
- Hiểu khác biệt giữa same-port và separate management port.
- Cấu hình health details theo quyền truy cập.
- Tránh mở rộng wildcard exposure hoặc cấp quyền quản trị quá rộng.
- Kiểm tra 401, 403, 404 và hành vi của monitoring clients.
- Kết hợp authorization với network isolation, TLS và secret management.

## 2. Bốn lớp kiểm soát Actuator

| Lớp | Câu hỏi | Cơ chế |
| --- | --- | --- |
| Availability | Endpoint có được tạo trong ứng dụng không? | Actuator dependency, auto-configuration, endpoint conditions |
| Exposure | Endpoint được đưa ra HTTP/JMX surface nào? | management.endpoints.web.exposure / JMX exposure |
| Authentication | Caller chứng minh danh tính bằng cách nào? | Basic auth, OAuth2 resource server, mTLS hoặc identity phù hợp |
| Authorization | Caller đã xác thực có được phép gọi endpoint này không? | Spring Security roles/authorities và request matchers |

Ví dụ: có Actuator dependency làm endpoint health khả dụng; web exposure đưa health ra HTTP; authentication xác định monitoring identity; authorization cho phép identity đó gọi health. Nếu một lớp chưa được cấu hình, kết quả truy cập có thể khác nhau.

## 3. Chỉ expose các endpoints cần thiết

Mặc định, không nên giả định mọi Actuator endpoint đều được expose qua HTTP. Hãy cấu hình allow-list theo nhu cầu:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Danh sách trên là ví dụ cho một service có health checks và metrics scraping. Không đưa env, configprops, beans, heapdump hoặc threaddump vào allow-list công khai nếu chưa đánh giá thông tin và chi phí mà chúng tiết lộ.

Exposure không thay thế security. Nếu endpoint được expose nhưng không có authentication/authorization phù hợp, nó có thể được truy cập bởi bất kỳ caller nào có network route tới ứng dụng.

### Endpoint-specific access

Actuator có endpoint access controls trong các phiên bản Spring Boot mới hơn, có thể giới hạn endpoint ở mức none/read-only/unrestricted theo tính năng/version. Đây là lớp kiểm soát bổ sung cho exposure và Spring Security. Kiểm tra property metadata của đúng Spring Boot version; không giả định mọi phiên bản hỗ trợ cùng tập access levels.

## 4. Bảo vệ Actuator bằng Spring Security

Ví dụ policy cho ứng dụng dùng chung application port:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/actuator/health/**").permitAll()
                .requestMatchers("/actuator/prometheus")
                    .hasAuthority("SCOPE_metrics.read")
                .requestMatchers("/actuator/**").hasRole("OPS")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Đây là ví dụ policy dùng JWT resource server. Ứng dụng cần cấu hình issuer/JWK hoặc JWT decoder phù hợp và ánh xạ authorities tương ứng. Nếu dùng Basic authentication, mTLS hoặc service identity khác, thay authentication mechanism theo môi trường.

### Thứ tự request matchers rất quan trọng

Spring Security áp dụng matcher theo thứ tự khai báo. Quy tắc cụ thể nên đứng trước quy tắc tổng quát:

1. Health endpoints được probe truy cập theo policy.
2. Prometheus endpoint yêu cầu authority riêng cho metrics scraper.
3. Các Actuator endpoints còn lại yêu cầu operator role.
4. Các application routes áp dụng authentication/authorization nghiệp vụ.

Nếu đặt matcher /actuator/** trước matcher Prometheus, request Prometheus có thể bị xử lý bởi OPS rule trước và không bao giờ tới rule metrics-specific.

## 5. Health probes và health details

Kubernetes hoặc platform probe thường cần biết instance UP/DOWN. Probe thường không cần đọc database hostname, exception message hoặc component details.

Ví dụ:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
```

Property cụ thể cần khớp Spring Boot version. Với cấu hình này, health status có thể được trả cho caller không có quyền, trong khi details chỉ hiện khi caller được authorize theo policy. Hãy kiểm tra response thực tế và security chain.

Không permit mọi health subpath một cách mù quáng. Rule /actuator/health/** có thể bao gồm health groups và component-specific paths. Nếu các subpaths trả nhiều details hơn dự kiến, thu hẹp matchers hoặc chỉ expose group cần thiết. Một lựa chọn là tạo health group dành riêng cho probes, chỉ trả status và không chứa chi tiết nội bộ.

## 6. Metrics scraper và operator là hai identity khác nhau

Monitoring agent thường chỉ cần đọc metrics. Operator có thể cần truy cập thêm các endpoints phục vụ chẩn đoán. Dùng hai authorities riêng giúp giới hạn quyền:

| Identity | Quyền phù hợp | Không nên mặc định cấp |
| --- | --- | --- |
| Kubernetes probe | Đọc health status cần thiết | env, configprops, heapdump |
| Prometheus scraper | Đọc /actuator/prometheus | Thay đổi log levels hoặc shutdown |
| Operations engineer | Các endpoints diagnostics đã phê duyệt | Mọi endpoint unrestricted |
| Application user | Business API theo vai trò nghiệp vụ | Actuator management endpoints |

Nếu metrics endpoint chỉ truy cập được qua internal network, vẫn nên dùng identity/service authentication phù hợp. Network location không tự chứng minh caller đáng tin cậy.

### Không dùng cùng credential cho mọi monitoring workloads

Credential riêng cho scraper và operator giúp revoke hoặc rotate một quyền mà không ảnh hưởng toàn bộ hệ thống. Dùng secret manager hoặc workload identity; tránh hardcode token trong ConfigMap, source control, Docker image hoặc log output.

## 7. Separate management port và security chains

Khi management server chạy trên port riêng, có thể áp dụng security policy riêng tùy Spring Boot/Spring Security configuration. Điều này giúp tách route application và management, nhưng cần kiểm tra request matcher và filter chain thực tế.

Ví dụ:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
```

Port 8081 vẫn thuộc cùng process trong cấu hình thông thường. Firewall, Kubernetes NetworkPolicy hoặc service routing nên chỉ cho phép probe/monitoring network truy cập management port.

### SecurityFilterChain riêng

Nếu cấu hình nhiều SecurityFilterChain, phải chọn matcher phù hợp cho management port và đảm bảo chain order không vô tình bắt application traffic hoặc bỏ qua Actuator requests. Cách match theo management port/context phụ thuộc Spring Boot/Security version; kiểm tra framework request matcher có sẵn thay vì tự dựa vào header Host do client kiểm soát.

Đừng tạo chain management có permitAll cho toàn bộ port nếu port đó vẫn reachable từ network không tin cậy. Network isolation và authorization phải cùng tồn tại.

## 8. 401, 403 và 404 có ý nghĩa gì?

| HTTP status | Diễn giải thường gặp | Kiểm tra |
| --- | --- | --- |
| 401 Unauthorized | Caller chưa authenticate hoặc credentials không hợp lệ | Token, Basic credentials, issuer/JWK, certificate |
| 403 Forbidden | Caller đã authenticate nhưng thiếu authority/role | Role mapping, matcher order, granted authorities |
| 404 Not Found | Endpoint không tồn tại, chưa expose hoặc path sai | Dependency, exposure, base path, management port |
| 200 OK | Request được xử lý thành công | Xác minh response chỉ chứa dữ liệu caller được phép xem |

Security configuration có thể cố ý trả 404 thay cho 403 để giảm tiết lộ endpoint. Vì vậy cần xem logs/security events và endpoint configuration trước khi kết luận.

## 9. CSRF, CORS và management endpoints

CSRF và CORS giải quyết vấn đề khác authorization:

- CSRF bảo vệ một số browser-based authenticated requests khỏi cross-site request forgery.
- CORS quyết định browser JavaScript từ origin nào được phép đọc response.
- Authentication/authorization xác định caller là ai và được làm gì.

Prometheus scraper hoặc Kubernetes probe thường không phải browser client. Không tắt CSRF toàn ứng dụng chỉ để scrape metrics; nếu cần miễn CSRF cho một endpoint machine-to-machine, giới hạn matcher cụ thể và đánh giá authentication mechanism.

CORS không phải access control cho server-to-server callers. Một client không phải browser có thể gọi endpoint bất kể CORS response headers.

## 10. Bảo vệ thông tin và dữ liệu observability

Actuator không phải nguồn duy nhất có thể làm lộ dữ liệu. Metrics, logs, traces, baggage và health details đều cần policy:

| Tín hiệu | Rủi ro | Kiểm soát |
| --- | --- | --- |
| Health details | Hostnames, dependency state, exception detail | show-details theo quyền, group tối giản |
| Metrics | Route names, traffic patterns, internal topology | Authenticated scrape, network isolation |
| Logs | Tokens, SQL bind values, personal data | Redaction, structured logging, access control |
| Traces | Span attributes, baggage, URLs và exception data | Attribute allow-list, sampling/retention, redaction |
| Environment/config endpoints | Secrets và configuration values | Không expose công khai; quyền operator tối thiểu |

Không ghi Authorization headers, cookies, passwords, API keys hoặc full request payload vào logs/traces. Tránh dùng user ID, email, order ID hoặc trace ID làm metric tags vì cardinality và privacy risk.

## 11. TLS, network policy và secret rotation

Authorization ở application layer nên được củng cố bằng transport/network controls:

1. Dùng HTTPS/TLS cho management traffic đi qua network.
2. Hạn chế management port bằng firewall/security groups/NetworkPolicy.
3. Chỉ publish management Service nội bộ nếu deployment platform hỗ trợ.
4. Dùng service identity hoặc workload identity cho scraper/operator automation.
5. Rotate credentials/certificates và thu hồi identity không còn sử dụng.
6. Audit truy cập management endpoints theo policy.

Nếu dùng TLS termination ở ingress, đánh giá cả hop từ ingress tới application. Nếu cần mTLS, xác thực client certificate và mapping identity sang authority; đừng chỉ kiểm tra sự hiện diện của một header tự khai báo.

## 12. Kiểm thử authorization cho Actuator

Không chỉ kiểm thử rằng endpoint trả 200 với admin. Cần kiểm tra từng identity:

| Test case | Caller | Kết quả mong đợi |
| --- | --- | --- |
| Health probe | Probe identity/anonymous theo policy | Chỉ status cần thiết được đọc |
| Metrics scrape | Metrics authority | Đọc được Prometheus endpoint |
| Metrics without role | Authenticated user không có metrics scope | 403 hoặc policy denial |
| Operator endpoint | OPS role | Chỉ endpoints được expose và cho phép |
| Anonymous operator access | Không credentials | 401/403 |
| Application user | Business role | Không tự có quyền Actuator |
| Sensitive details | Caller không được phép | Details bị ẩn hoặc request bị từ chối |
| Unknown endpoint | Bất kỳ caller | 404 theo endpoint availability/exposure |

### Ví dụ integration test

Với Spring Security Test, có thể kiểm tra request authorization:

```java
@Test
void metricsRequiresMetricsAuthority() throws Exception {
    mockMvc.perform(get("/actuator/prometheus")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_metrics.read")
            )))
        .andExpect(status().isOk());
}

@Test
void ordinaryUserCannotReadMetrics() throws Exception {
    mockMvc.perform(get("/actuator/prometheus")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("ROLE_USER")
            )))
        .andExpect(status().isForbidden());
}
```

Ví dụ cần Spring Security Test, MockMvc và JWT test support được cấu hình. Nếu endpoint chưa expose, kết quả có thể là 404; test cần cấu hình Actuator endpoint trong application context thật để kiểm tra authorization layer.

## 13. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Scraper nhận 401 | Thiếu token/credentials hoặc authentication config sai | Kiểm tra workload identity, issuer và credentials |
| Scraper nhận 403 | Token hợp lệ nhưng thiếu authority | Kiểm tra scope/role mapping và matcher order |
| Endpoint trả 404 | Chưa expose, thiếu dependency hoặc sai management base path/port | Kiểm tra endpoint availability và exposure |
| Health probe nhận 401 | Probe endpoint bị yêu cầu authentication | Thiết kế probe identity hoặc rule tối thiểu |
| Health details lộ cho anonymous | show-details hoặc security policy quá rộng | Giới hạn details và matcher |
| Operator bị chặn dù có role | Authority prefix hoặc matcher order sai | Kiểm tra ROLE_ prefix, scopes và SecurityFilterChain |
| Application routes bị áp dụng management rules | Nhiều filter chains match sai | Kiểm tra chain order và request matchers |
| Port riêng vẫn truy cập từ internet | Firewall/Service/NetworkPolicy mở quá rộng | Thu hẹp network route và listener exposure |
| CORS được bật nhưng endpoint vẫn bị gọi | CORS không ngăn server-to-server requests | Dùng authentication/authorization |
| Token xuất hiện trong logs | Logging interceptor ghi headers | Redact Authorization/Cookie headers |
| TLS handshake fail | Trust chain, hostname hoặc client cert sai | Kiểm tra TLS/mTLS configuration |
| Credential cũ vẫn hoạt động | Rotation/revocation chưa hoàn tất | Kiểm tra secret lifecycle và identity revocation |

### Checklist review trước production

1. Liệt kê endpoints thực sự cần expose.
2. Xác định identity riêng cho probes, scraper và operator.
3. Viết matcher cụ thể trước matcher tổng quát.
4. Kiểm tra health details không lộ topology/exception nhạy cảm.
5. Bảo vệ management port bằng TLS và network policy.
6. Kiểm thử 401, 403, 404 và 200 cho từng loại caller.
7. Kiểm tra logs không ghi credentials hoặc raw headers.
8. Xác nhận secret rotation, audit và revoke process.

## 14. Thực hành: phân quyền Actuator cho ba nhóm caller

**Bối cảnh:** order-service expose health, metrics và Prometheus. Kubernetes cần health status; Prometheus cần scrape metrics; operator cần quyền xem các endpoint diagnostics đã phê duyệt.

### Phần A — Thiết kế policy

1. Expose health, metrics và prometheus; không bật wildcard.
2. Cho probe đọc status health tối thiểu.
3. Cấp authority SCOPE_metrics.read cho scraper.
4. Cấp role OPS cho operator qua identity provider.
5. Cấu hình health details chỉ hiện khi authorized.
6. Giới hạn management port trong internal network.

### Phần B — Kiểm chứng

| Ca | Caller | Kết quả cần quan sát |
| --- | --- | --- |
| A — Probe | Kubelet/probe identity | Đọc được readiness/liveness status |
| B — Scraper | Metrics scope | Đọc được /actuator/prometheus |
| C — User thường | ROLE_USER | Không đọc được metrics/operator endpoints |
| D — Operator | OPS role | Chỉ đọc được endpoints được phép |
| E — Anonymous | Không credentials | Không truy cập diagnostics |
| F — Details | Caller không đủ quyền | Health details bị ẩn |
| G — Network | Caller ngoài internal network | Management port không reachable |
| H — Rotation | Thu hồi token cũ, cấp token mới | Credential cũ bị từ chối |

### Phần C — Câu hỏi tự đánh giá

1. Endpoint availability khác exposure và authorization như thế nào?
2. Vì sao expose metrics không có nghĩa endpoint đã được bảo vệ?
3. Vì sao matcher cụ thể cần đứng trước /actuator/**?
4. Probe, scraper và operator nên có những quyền khác nhau nào?
5. 401 khác 403 và 404 ra sao?
6. Vì sao health status có thể public trong khi health details phải restricted?
7. CORS có thay thế authentication cho Prometheus scraper không?
8. Khi management port riêng, cần thêm network controls nào?
9. Những dữ liệu observability nào có thể chứa PII/secrets?
10. Làm thế nào kiểm thử credential rotation và quyền bị thu hồi?

## 15. Ghi nhớ

**Authorization cho Actuator** cần kết hợp endpoint availability, exposure, authentication và authorization. Spring Boot Actuator quyết định endpoint nào có mặt; exposure đưa endpoint ra HTTP/JMX; Spring Security xác thực caller và kiểm tra authorities/roles. Network isolation và TLS bổ sung lớp bảo vệ cho management traffic.

Thiết kế quyền riêng cho health probes, metrics scraper và operator. Chỉ expose endpoints cần thiết, đặt matcher cụ thể trước matcher tổng quát và kiểm tra health details theo quyền. Test đủ các kết quả 200, 401, 403 và 404; đừng coi CORS hoặc port riêng là biện pháp authorization. Bảo vệ credentials, redact logs/traces và giới hạn metrics dimensions để tránh lộ PII, secrets hoặc topology. Policy được kiểm thử theo từng identity giúp observability endpoints hỗ trợ vận hành mà không mở rộng quyền quản trị ngoài nhu cầu.
